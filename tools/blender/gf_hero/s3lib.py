"""Shared helpers for the GODFORGE stage-3 rig scripts (headless Blender 5.2, bpy + numpy).

  * tps_from_fit(): the stage-2 landmark warp (s2_body_fit.py step 1) as a function, so stage 3 maps MakeHuman
    joints and vertices onto the hero exactly as the body was fitted;
  * WeightMatrix: a dense (n_verts, n_bones) weight matrix with the clean / limit / normalise / write-back rules of
    the Ashen Covenant skinning helpers (D:/Ashen_Covenant/tools/blender/ac_player_rig/ac_skin.py, class Weights),
    adapted: named columns fixed to the GF_Hero_v1 deform set, numpy edge smoothing instead of the weight-paint
    operators (works on any object, no mode switches);
  * pose helpers (FK in degrees, aim, IK baked into the pose) adapted from ac_humanoid_enemy/ac_pose.py;
  * the review camera and a Cycles-CPU toon material (no EEVEE: the GPU is shared).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

from s2lib import ROOT, get_co, get_edges, log, read_json  # noqa: E402,F401


def hero_paths(key):
    A = os.path.join(ROOT, "art", "characters", key)
    return {"A": A, "W": os.path.join(A, "work"), "S3": os.path.join(A, "reports", "stage3"),
            "fit": os.path.join(A, "stage2_fit.json"), "mh": os.path.join(A, "work", "%s_s2_mh_landmarks.json" % key),
            "body_fit": os.path.join(A, "reports", "stage2", "body_fit.json"),
            "stage2": os.path.join(A, "production", "%s_stage2.blend" % key),
            "base": os.path.join(A, "work", "%s_s2_body_base.blend" % key),
            "landmarks": os.path.join(A, "work", "%s_landmarks.json" % key),
            "seed": os.path.join(A, "work", "%s_s3_mh_seed.npz" % key),
            "skin_cfg": os.path.join(A, "stage3_skin.json"),
            "rig": os.path.join(A, "production", "%s_rig.blend" % key),
            "renders": os.path.join(A, "work", "renders", "stage3")}


# ---- the stage-2 thin-plate-spline landmark warp ------------------------------------------------------------------

def tps_from_fit(fit_cfg, mh):
    """X (n,3) MakeHuman T-pose space -> hero space, the exact warp of s2_body_fit.py."""
    def mh_point(key):
        if "." in key:
            bone, end = key.split(".")
            return mh["joints"][bone][end]
        return mh[key]
    pairs = []
    for key, dst_p in fit_cfg["landmarks"].items():
        if key.startswith("_"):
            continue
        pairs.append((mh_point(key), dst_p))
        if "_l" in key:
            q = list(dst_p)
            q[0] = -q[0]
            pairs.append((mh_point(key.replace("_l", "_r")), q))
    S = np.array([p[0] for p in pairs], dtype=np.float64)
    D = np.array([p[1] for p in pairs], dtype=np.float64)
    n = len(S)
    K = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=2)
    P = np.hstack([np.ones((n, 1)), S])
    A = np.zeros((n + 4, n + 4))
    A[:n, :n] = K + 1e-6 * np.eye(n)
    A[:n, n:] = P
    A[n:, :n] = P.T
    rhs = np.zeros((n + 4, 3))
    rhs[:n] = D
    sol = np.linalg.solve(A, rhs)
    W, Aff = sol[:n], sol[n:]

    def tps(X):
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        U = np.linalg.norm(X[:, None, :] - S[None, :, :], axis=2)
        return U @ W + np.hstack([np.ones((len(X), 1)), X]) @ Aff
    return tps


# ---- weights ------------------------------------------------------------------------------------------------------

class WeightMatrix:
    """Dense weights for one mesh object over a fixed bone list."""

    def __init__(self, obj, bones):
        self.obj, self.me = obj, obj.data
        self.bones = list(bones)
        self.col = {b: j for j, b in enumerate(self.bones)}
        self.W = np.zeros((len(self.me.vertices), len(self.bones)), dtype=np.float64)
        self.co = get_co(self.me)
        self._edges = None

    def idx(self, names):
        return [self.col[n] for n in names if n in self.col]

    def own(self, names):
        return self.W[:, self.idx(names)].sum(axis=1)

    @property
    def edges(self):
        if self._edges is None:
            self._edges = get_edges(self.me)
        return self._edges

    def normalise(self):
        s = self.W.sum(axis=1)
        ok = s > 1e-12
        self.W[ok] /= s[ok, None]

    def limit(self, max_influences=4, threshold=0.01):
        """Drop weights under threshold (relative), keep the max_influences largest, renormalise."""
        self.normalise()
        W = self.W
        W[W < threshold] = 0.0
        if W.shape[1] > max_influences:
            drop = np.argsort(-W, axis=1)[:, max_influences:]
            np.put_along_axis(W, drop, 0.0, axis=1)
        self.normalise()

    def smooth(self, mask, iters=3, amount=0.5, cols=None):
        """Laplacian smoothing of the weight rows on `mask` over the mesh edges (all columns or `cols`)."""
        W = self.W
        e = self.edges
        n = W.shape[0]
        deg = np.bincount(e.ravel(), minlength=n).astype(np.float64)
        deg[deg == 0] = 1
        c = slice(None) if cols is None else cols
        for _ in range(iters):
            sub = W[:, c]
            acc = np.zeros_like(sub)
            np.add.at(acc, e[:, 0], sub[e[:, 1]])
            np.add.at(acc, e[:, 1], sub[e[:, 0]])
            new = sub + (acc / deg[:, None] - sub) * amount
            sub[mask] = new[mask]
            W[:, c] = sub
        self.normalise()

    def stats(self):
        infl = (self.W > 0).sum(axis=1)
        s = self.W.sum(axis=1)
        return {"vertices": int(self.W.shape[0]), "unweighted": int((s < 1e-9).sum()),
                "max_influences": int(infl.max()) if len(infl) else 0,
                "influence_histogram": {str(k): int((infl == k).sum()) for k in range(0, int(infl.max()) + 1)} if len(infl) else {},
                "max_abs_sum_error": float(np.abs(s - 1.0).max()) if len(s) else 0.0}

    def write(self):
        """Replace the object's vertex groups by the matrix (only non-zero columns get a group)."""
        ob = self.obj
        for vg in list(ob.vertex_groups):
            ob.vertex_groups.remove(vg)
        for j, b in enumerate(self.bones):
            rows = np.nonzero(self.W[:, j] > 0)[0]
            if not len(rows):
                continue
            vg = ob.vertex_groups.new(name=b)
            for i in rows:
                vg.add([int(i)], float(self.W[i, j]), "REPLACE")

    @staticmethod
    def read(obj, bones):
        wm = WeightMatrix(obj, bones)
        names = {vg.index: vg.name for vg in obj.vertex_groups}
        for v in obj.data.vertices:
            for g in v.groups:
                b = names.get(g.group)
                if b in wm.col and g.weight > 0:
                    wm.W[v.index, wm.col[b]] = g.weight
        return wm


def segment_param(p, a, b):
    """(t along a->b clamped to [0,1], unclamped t, distance to the segment) for points p (n,3)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    d = b - a
    L2 = float(d @ d)
    t_raw = ((p - a) @ d) / max(L2, 1e-12)
    t = np.clip(t_raw, 0.0, 1.0)
    dist = np.linalg.norm(p - (a + t[:, None] * d), axis=1)
    return t, t_raw, dist


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def components(me):
    """Connected-component label per vertex (union-find over edges)."""
    n = len(me.vertices)
    e = get_edges(me)
    parent = np.arange(n)

    def find(a):
        r = a
        while parent[r] != r:
            r = parent[r]
        while parent[a] != r:
            parent[a], a = r, parent[a]
        return r
    for a, b in e.tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    lab = np.array([find(i) for i in range(n)])
    _, lab = np.unique(lab, return_inverse=True)
    return lab


# ---- pose helpers (ac_pose.py) ----------------------------------------------------------------------------------------

def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def aim_bone(arm, pb, world_dir, twist_deg=0.0):
    """Rotate pb so it points along world_dir with the minimal swing from its rest direction, then twist it
    twist_deg about its own axis (its parents must already be posed)."""
    from mathutils import Quaternion
    bpy.context.view_layer.update()
    bone = pb.bone
    if pb.parent:
        rest_in_parent = pb.parent.bone.matrix_local.inverted() @ bone.matrix_local
        frame = (arm.matrix_world @ pb.parent.matrix @ rest_in_parent).to_3x3()
    else:
        frame = (arm.matrix_world @ bone.matrix_local).to_3x3()
    cur = frame @ Vector((0.0, 1.0, 0.0))
    q_world = cur.rotation_difference(Vector(world_dir).normalized())
    q_local = frame.inverted().to_quaternion() @ q_world @ frame.to_quaternion()
    q = q_local @ Quaternion((0.0, 1.0, 0.0), math.radians(twist_deg))
    pb.rotation_euler = q.to_euler("XYZ")


def solve_ik_pole(arm, tip_bone, target_world, pole_world, chain_count=2):
    """IK to target_world with the middle joint bending toward pole_world: tries the four pole angles and keeps the
    one whose joint ends nearest the pole side (Blender's pole angle depends on the chain's roll convention)."""
    best = None
    snap = {pb.name: pb.rotation_euler.copy() for pb in arm.pose.bones}
    for ang in (0.0, 90.0, -90.0, 180.0):
        for pb in arm.pose.bones:
            pb.rotation_euler = snap[pb.name].copy()
        solve_ik(arm, tip_bone, chain_count, target_world, pole_world, ang)
        mid = arm.matrix_world @ arm.pose.bones[tip_bone].head
        tip = arm.matrix_world @ arm.pose.bones[tip_bone].tail
        root = arm.matrix_world @ arm.pose.bones[arm.pose.bones[tip_bone].parent.name].head
        axis = (tip - root).normalized()
        off = (mid - root) - axis * (mid - root).dot(axis)
        want = (Vector(pole_world) - root) - axis * (Vector(pole_world) - root).dot(axis)
        score = off.normalized().dot(want.normalized()) if off.length > 1e-6 and want.length > 1e-6 else -2
        score -= (tip - Vector(target_world)).length * 10
        if best is None or score > best[0]:
            best = (score, ang, {pb.name: pb.rotation_euler.copy() for pb in arm.pose.bones})
    for pb in arm.pose.bones:
        pb.rotation_euler = best[2][pb.name]
    bpy.context.view_layer.update()
    return best[1]


def solve_ik(arm, tip_bone, chain_count, target_world, pole_world=None, pole_angle=0.0):
    """Reach target_world with the TAIL of tip_bone (temporary IK constraint, baked into the pose)."""
    scene = bpy.context.scene
    pb = arm.pose.bones[tip_bone]
    tgt = bpy.data.objects.new("IK_TMP_TARGET", None)
    scene.collection.objects.link(tgt)
    tgt.location = Vector(target_world)
    pole = None
    if pole_world is not None:
        pole = bpy.data.objects.new("IK_TMP_POLE", None)
        scene.collection.objects.link(pole)
        pole.location = Vector(pole_world)
    c = pb.constraints.new("IK")
    c.target = tgt
    c.chain_count = chain_count
    c.iterations = 500
    c.use_tail = True
    if pole is not None:
        c.pole_target = pole
        c.pole_angle = math.radians(pole_angle)
    bpy.context.view_layer.update()
    prev = bpy.context.view_layer.objects.active
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    for other in arm.pose.bones:
        other.select = False
    ch = pb
    for _ in range(chain_count):
        if ch is None:
            break
        ch.select = True
        ch = ch.parent
    bpy.ops.pose.visual_transform_apply()
    bpy.ops.object.mode_set(mode="OBJECT")
    pb.constraints.remove(c)
    bpy.data.objects.remove(tgt)
    if pole is not None:
        bpy.data.objects.remove(pole)
    bpy.context.view_layer.objects.active = prev
    bpy.context.view_layer.update()


def apply_pose(arm, pose):
    """pose: {bone: {"rot": (x, y, z) deg local | "loc": (x, y, z) local m | "aim": world dir |
    "ik": world target (+ "chain", "pole", "pole_angle") | "aim_after_ik": world dir}}. Twist bones are driven."""
    reset_pose(arm)
    for bname, tr in pose.items():
        pb = arm.pose.bones.get(bname)
        if pb is None:
            continue
        if "rot" in tr:
            pb.rotation_euler = Euler([math.radians(a) for a in tr["rot"]], "XYZ")
        if "loc" in tr:
            pb.location = Vector(tr["loc"])
        if "loc_world" in tr:     # a world-space offset of the bone head (parent at rest)
            pb.location = pb.bone.matrix_local.to_3x3().inverted() @ Vector(tr["loc_world"])
    for pb in arm.pose.bones:
        tr = pose.get(pb.name)
        if tr and "aim" in tr:
            aim_bone(arm, pb, tr["aim"], tr.get("twist", 0.0))
    for bname, tr in pose.items():
        if "ik" in tr:
            if tr.get("pole") is not None:
                solve_ik_pole(arm, bname, tr["ik"], tr["pole"], tr.get("chain", 2))
            else:
                solve_ik(arm, bname, tr.get("chain", 2), tr["ik"])
    for bname, tr in pose.items():
        if "aim_after_ik" in tr:
            d = tr["aim_after_ik"]
            if d == "parent":           # a straight joint: along the posed parent (e.g. the wrist of a sleeve weapon)
                bpy.context.view_layer.update()
                par = arm.pose.bones[bname].parent
                d = tuple((arm.matrix_world.to_3x3() @ par.matrix.to_3x3()).col[1])
            aim_bone(arm, arm.pose.bones[bname], d, tr.get("twist", 0.0))
    for bname, tr in pose.items():
        if "post_rot" in tr:     # extra local rotation after aims / IK (e.g. a hand twist)
            pb = arm.pose.bones[bname]
            e = pb.rotation_euler.copy()
            q = e.to_quaternion() @ Euler([math.radians(a) for a in tr["post_rot"]], "XYZ").to_quaternion()
            pb.rotation_euler = q.to_euler("XYZ")
    bpy.context.view_layer.update()


def fcurves(action):
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        yield fc
    else:
        for fc in action.fcurves:
            yield fc


def new_action(arm, name, frame_start, frame_end):
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    if hasattr(act, "slots"):
        slot = act.slots.new(id_type="OBJECT", name=arm.name)
        arm.animation_data.action_slot = slot
    act.use_frame_range = True
    act.frame_start = frame_start
    act.frame_end = frame_end
    return act


def key_current_pose(arm, frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_euler", frame=frame)
        pb.keyframe_insert("location", frame=frame)
    if arm.animation_data and arm.animation_data.action:
        for fc in fcurves(arm.animation_data.action):
            for kp in fc.keyframe_points:
                if abs(kp.co.x - frame) < 0.5:
                    kp.interpolation = "CONSTANT"


def push_to_nla(arm, action, track_name=None):
    ad = arm.animation_data
    track = ad.nla_tracks.new()
    track.name = track_name or action.name
    strip = track.strips.new(action.name, int(action.frame_start), action)
    strip.name = action.name
    track.mute = True
    return track


# ---- review rendering: Cycles CPU toon (no Shader-to-RGB, which Cycles lacks) -----------------------------------

def cycles_cpu(scene, samples=6):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.cycles.use_adaptive_sampling = False
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def make_toon_cycles(M, light_dir=(-0.45, -0.55, 0.70), emissive_gain=2.2):
    """Copy of an atlas material as a 3-band toon for Cycles: N.L of a fixed key direction (normal map included)
    -> constant ramp x base colour + rim + emissive, output as Emission (so it renders in a few samples)."""
    T = M.copy()
    T.name = M.name + "_toon_cycles"
    nt = T.node_tree
    imgs = {k: ([n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image and k in n.image.name] or [None])[0]
            for k in ("basecolor", "emissive", "normal")}
    for n in list(nt.nodes):
        if n not in imgs.values():
            nt.nodes.remove(n)
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nrm = geo.outputs["Normal"]
    if imgs["normal"] is not None:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.uv_map = "UVMap"
        L(imgs["normal"].outputs["Color"], nm.inputs["Color"])
        nrm = nm.outputs["Normal"]
    ld = nt.nodes.new("ShaderNodeCombineXYZ")
    v = Vector(light_dir).normalized()
    ld.inputs[0].default_value, ld.inputs[1].default_value, ld.inputs[2].default_value = v
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(nrm, dot.inputs[0])
    L(ld.outputs[0], dot.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.36, 0.32, 0.40, 1)
    els[1].position, els[1].color = 0.12, (0.70, 0.66, 0.66, 1)
    e3 = els.new(0.52)
    e3.color = (1.0, 0.97, 0.92, 1)
    L(dot.outputs["Value"], ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(ramp.outputs["Color"], mul.inputs["A"])
    if imgs["basecolor"] is not None:
        L(imgs["basecolor"].outputs["Color"], mul.inputs["B"])
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.25
    L(nrm, lw.inputs["Normal"])
    rim = nt.nodes.new("ShaderNodeValToRGB")
    rim.color_ramp.interpolation = "CONSTANT"
    rim.color_ramp.elements[0].color = (0, 0, 0, 1)
    rim.color_ramp.elements[1].position = 0.74
    rim.color_ramp.elements[1].color = (0.30, 0.20, 0.12, 1)
    L(lw.outputs["Facing"], rim.inputs["Fac"])
    add1 = nt.nodes.new("ShaderNodeMix")
    add1.data_type = "RGBA"
    add1.blend_type = "ADD"
    add1.inputs["Factor"].default_value = 1.0
    L(mul.outputs["Result"], add1.inputs["A"])
    L(rim.outputs["Color"], add1.inputs["B"])
    last = add1.outputs["Result"]
    if imgs["emissive"] is not None:
        em = nt.nodes.new("ShaderNodeMix")
        em.data_type = "RGBA"
        em.blend_type = "MULTIPLY"
        em.inputs["Factor"].default_value = 1.0
        em.inputs["B"].default_value = (emissive_gain, emissive_gain, emissive_gain, 1)
        L(imgs["emissive"].outputs["Color"], em.inputs["A"])
        add2 = nt.nodes.new("ShaderNodeMix")
        add2.data_type = "RGBA"
        add2.blend_type = "ADD"
        add2.inputs["Factor"].default_value = 1.0
        L(last, add2.inputs["A"])
        L(em.outputs["Result"], add2.inputs["B"])
        last = add2.outputs["Result"]
    emn = nt.nodes.new("ShaderNodeEmission")
    L(last, emn.inputs["Color"])
    L(emn.outputs[0], out.inputs["Surface"])
    return T


def flat_material(name, rgba):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = rgba
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    m.diffuse_color = rgba
    return m


def world_matrix_np(ob):
    return np.array(ob.matrix_world)


def evaluated_co(ob):
    """World-space evaluated (deformed) vertex positions of a mesh object."""
    dg = bpy.context.evaluated_depsgraph_get()
    e = ob.evaluated_get(dg)
    m = e.to_mesh()
    co = np.empty(len(m.vertices) * 3, dtype=np.float64)
    m.vertices.foreach_get("co", co)
    e.to_mesh_clear()
    mw = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def mat4(m):
    return Matrix([list(r) for r in m])
