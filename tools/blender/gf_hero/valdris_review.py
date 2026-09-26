"""Valdris: adversarial review of stages 2-5 on the SHIPPED files (headless Blender 5.2, Workbench close-ups only).

  blender -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/valdris_review.py -- \
          [--out art/characters/valdris/work/review] [--no-renders] [--clips run@loop,bulwark_slam] [--glb <other valdris.glb>]

Imports assets/models/characters/valdris.glb with Blender's own glTF importer and the weapon track's
assets/models/weapons/colossus_cannon.glb as the identity child of weapon_R (as the client attaches it), then plays
EVERY frame of EVERY clip and measures the skinned mesh itself, independently of the stage-4 audit
(tools/blender/gf_hero/s4_valdris_render.py) and of the stage-5 gate (validate_glb.py):
  * weights (rest): > 4 influences, sums, an influence > 0.1 on a bone more than 0.35 m away, left / right mirror pairs
    whose weights differ;
  * sockets: weapon_R against the right fist, chest_sigil against the anvil's front face, head_top against the crown;
  * per clip (the feet: sole vertices within 5 mm of the ground in both frames of a step): cloth jitter (cape,
    loincloth and braid vertices whose velocity reverses between frames at > 2 cm / frame), legs through the cape and
    the loincloth (leg-armour triangles cutting a cloth triangle, BVH overlap), loop seam (the last frame against the first, and the seam's second difference against the clip's), pops
    (the largest per-vertex second difference, solid and cloth apart), the lowest vertex, the feet: contact vertices'
    slip after the design travel is taken out (the best-anchored contact vertex and the median one), the joint ranges
    (knee, elbow, arm elevation, the right wrist's bend: the sleeve rule), the cannon (right-arm vertices out of its
    outer skin inside its length: poke; other vertices enclosed by it: cuts), and the upper-layer rule (first and last
    frame against idle_combat frame 0 or the clip's base in reports/anim/clips.json);
  * renders (unless --no-renders): per clip its lower-body extreme (max knee) and upper-body extreme (highest arm, else
    max elbow) frames as Workbench close-ups of the shoulders / pauldrons, the cannon elbow, the left elbow, the knees
    and the cape -> <out>/renders/<clip>_f<frame>_<view>.png, and the cape from behind where the legs meet it
    (CAPE_SHOTS) -> <out>/renders/cape_<clip>_f<frame>.png; tools/blender/gf_hero/valdris_review_sheets.py builds the
    sheets.
Writes <out>/review.json. Report: art/characters/valdris/reports/review_stage2_5.md.
"""
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import validate_glb as V  # noqa: E402

ROOT = V.ROOT
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


OUT = os.path.abspath(opt("--out", os.path.join(ROOT, "art", "characters", "valdris", "work", "review")))
GLB = os.path.abspath(opt("--glb", os.path.join(ROOT, "assets", "models", "characters", "valdris.glb")))
WGLB = os.path.join(ROOT, "assets", "models", "weapons", "colossus_cannon.glb")
CLIPS_JSON = os.path.join(ROOT, "art", "characters", "valdris", "reports", "anim", "clips.json")
RENDERS = "--no-renders" not in argv
ONLY = set((opt("--clips") or "").split(",")) - {""}
T0 = time.time()
os.makedirs(os.path.join(OUT, "renders"), exist_ok=True)


def log(*a):
    print("[vrev %6.1fs]" % (time.time() - T0), *a, flush=True)


def r4(x):
    return None if x is None else round(float(x), 4)


# ---- import the shipped files -------------------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = V.FPS, 1.0
g = V.Glb(GLB)
meta = json.load(open(GLB[:-4] + ".meta.json", encoding="utf-8"))
cj = json.load(open(CLIPS_JSON, encoding="utf-8"))["clips"]
cj = cj if isinstance(cj, dict) else {c["clip"]: c for c in cj}
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=GLB, disable_bone_shape=True, import_shading="NORMALS")
hero = [o for o in bpy.data.objects if o not in before]
arm = [o for o in hero if o.type == "ARMATURE"][0]
body = [o for o in hero if o.type == "MESH"][0]
arm.animation_data_create()
arm.animation_data.action = None
for tr in arm.animation_data.nla_tracks:
    tr.mute = True
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()

C = Matrix(R.SOCKET_TO_GRIP)
CI = C.inverted()
gw_rest = V.world_matrices(g)
gidx = {n: i for i, n in enumerate(g.names)}
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=WGLB, import_shading="NORMALS")
wobjs = {o.name: o for o in bpy.data.objects if o not in before}
croot = wobjs["colossus_cannon"]
croot.parent, croot.parent_type, croot.parent_bone = arm, "BONE", "weapon_R"
bpy.context.view_layer.update()
croot.matrix_world = CI @ Matrix([list(r) for r in gw_rest[gidx["weapon_R"]]]) @ C
bpy.context.view_layer.update()
cmeshes = [o for o in wobjs.values() if o.type == "MESH"]
log("imported", body.name, len(body.data.vertices), "verts;", arm.name, len(arm.data.bones), "bones; cannon",
    [o.name for o in cmeshes])

rep = {"glb": V.relpath(GLB), "glb_sha256": g.sha256, "weapon": V.relpath(WGLB), "blender": bpy.app.version_string}

# ---- rest data: weights, dominant bone, parts ---------------------------------------------------------------------------
NV = len(body.data.vertices)
Mb = np.array(body.matrix_world)
rest = np.empty(NV * 3)
body.data.vertices.foreach_get("co", rest)
rest = rest.reshape(-1, 3) @ Mb[:3, :3].T + Mb[:3, 3]
vgn = [vg.name for vg in body.vertex_groups]
infl = []
n_over4, sum_err = 0, 0.0
for v in body.data.vertices:
    gs = sorted(((gg.weight, vgn[gg.group]) for gg in v.groups if gg.weight > 0.0), reverse=True)
    n_over4 += len(gs) > 4
    sum_err = max(sum_err, abs(sum(w for w, _ in gs) - 1.0))
    infl.append(gs)
dom = np.array([gs[0][1] if gs else "" for gs in infl])
CLOTH_RE = re.compile(r"^x_(cape|loin|beard)_")
is_cloth = np.array([bool(CLOTH_RE.match(d)) for d in dom])
IS_CAPE = np.array([d.startswith("x_cape") for d in dom])
IS_LOIN = np.array([d.startswith("x_loin") for d in dom])
IS_BRAID = np.array([d.startswith("x_beard") for d in dom])
bones = arm.data.bones
Ma = arm.matrix_world
bhead = {b.name: np.array(Ma @ b.head_local) for b in bones}
btail = {b.name: np.array(Ma @ b.tail_local) for b in bones}


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


far = []
for i, gs in enumerate(infl):
    if len(gs) < 2:
        continue          # a rigid armour piece may sit far from its bone (the anvil on spine_03): only blends count
    for w, bn in gs:
        if w > 0.1 and bn in bhead:
            d = seg_dist(rest[i], bhead[bn], btail[bn])
            if d > 0.35:
                far.append((i, bn, round(w, 3), round(d, 3)))


def mirror_name(n):
    m = re.match(r"^x_beard_(\d)(.*)$", n)
    if m:
        return "x_beard_%d%s" % (6 - int(m.group(1)), m.group(2))
    return re.sub(r"_(L|R)(?=\d|_|$)", lambda mm: "_" + ("R" if mm.group(1) == "L" else "L"), n)


kd = KDTree(NV)
for i, p in enumerate(rest):
    kd.insert(p, i)
kd.balance()
pairs, mism = 0, []
for i, p in enumerate(rest):
    if p[0] < 0.005:
        continue
    co, j, dist = kd.find((-p[0], p[1], p[2]))
    if dist > 0.0005:
        continue
    pairs += 1
    a = {mirror_name(bn): w for w, bn in infl[i]}
    b = {bn: w for w, bn in infl[j]}
    diff = max(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in set(a) | set(b))
    if diff > 0.05:
        mism.append((i, j, round(diff, 3), dom[i], dom[j]))
by = {}
for m in mism:
    by[m[3]] = by.get(m[3], 0) + 1
rep["weights"] = {
    "vertices": NV, "over_4_influences": n_over4, "sum_error_max": sum_err,
    "blended_far_influences_gt_0p35m": len(far), "far_examples": far[:12],
    "far_by_bone": {bn: sum(1 for f in far if f[1] == bn) for bn in sorted({f[1] for f in far})},
    "mirror_pairs": pairs, "mirror_mismatch_gt_0p05": len(mism),
    "mirror_mismatch_by_dominant_bone": dict(sorted(by.items(), key=lambda kv: -kv[1])[:20]),
    "mirror_examples": mism[:10],
    "cloth_vertices": int(is_cloth.sum()),
}
log("weights:", {k: v for k, v in rep["weights"].items() if not isinstance(v, (list, dict))})

# the rig's own symmetry (contract bones and extras): head positions mirrored
asym = []
for b in bones:
    mn = mirror_name(b.name)
    if mn != b.name and mn in bhead and b.name < mn:
        h, hm = bhead[b.name], bhead[mn]
        asym.append((round(float(np.linalg.norm(h - hm * np.array([-1, 1, 1]))), 4), b.name))
asym.sort(reverse=True)
rep["skeleton_mirror_asymmetry_top"] = asym[:10]

# ---- sockets against the geometry ---------------------------------------------------------------------------------------
sock = {s: np.array(Ma @ bones[s].head_local) for s in R.SOCKET_NAMES}
hand_r = np.where(np.isin(dom, ["hand_R"] + [n for n in bhead if n.endswith("_R") and re.match(r"^(thumb|index|middle|ring|pinky)_", n)]))[0]
_polys = [tuple(p.vertices) for p in body.data.polygons]
rbvh = BVHTree.FromPolygons([tuple(x) for x in rest], _polys)
_hit = rbvh.find_nearest(Vector(sock["chest_sigil"]))
anvil_near = float(_hit[3])
head_v = np.where(np.isin(dom, ["head", "neck"]))[0]
rep["rest_legs_through_cloth_faces"] = None
rep["sockets"] = {
    "weapon_R_to_right_hand_centroid_m": r4(np.linalg.norm(rest[hand_r].mean(0) - sock["weapon_R"])),
    "weapon_R": [r4(x) for x in sock["weapon_R"]],
    "chest_sigil_to_surface_m": r4(anvil_near),
    "head_top_z": r4(sock["head_top"][2]),
    "head_mesh_top_z": r4(rest[head_v][:, 2].max()),
    "mesh_top_z": r4(rest[:, 2].max()),
    "mesh_top_bone": str(dom[int(np.argmax(rest[:, 2]))]),
}
log("sockets:", rep["sockets"])

# ---- the cannon: rest BVH, its axis and length --------------------------------------------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
cv, cf = [], []
for o in cmeshes:
    e = o.evaluated_get(dg)
    me = e.to_mesh()
    M = o.matrix_world
    base = len(cv)
    cv += [tuple(M @ v.co) for v in me.vertices]
    cf += [tuple(base + k for k in p.vertices) for p in me.polygons]
    e.to_mesh_clear()
cbvh = BVHTree.FromPolygons(cv, cf)
cv = np.array(cv)
grip = np.array(wobjs["grip_R"].matrix_world.translation) if "grip_R" in wobjs else np.array(croot.matrix_world.translation)
muz = np.array(wobjs["muzzle"].matrix_world.translation)
axis = (muz - grip) / np.linalg.norm(muz - grip)
tax = (cv - grip) @ axis
t_lo, t_hi = float(tax.min()), float(tax.max())
u = np.cross(axis, [0.0, 0.0, 1.0])
u = u / np.linalg.norm(u) if np.linalg.norm(u) > 1e-6 else np.array([1.0, 0.0, 0.0])
w_ = np.cross(axis, u)
RAYS = [Vector(tuple(math.cos(a) * u + math.sin(a) * w_)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
C_rest = np.array(croot.matrix_world)
rep["cannon"] = {"axis_len_m": r4(t_hi - t_lo), "rear_end_behind_grip_m": r4(-t_lo), "muzzle_ahead_of_grip_m": r4(t_hi)}
RIGHT_ARM = {"lowerarm_R", "lowerarm_twist_R", "hand_R", "upperarm_R", "upperarm_twist_R", "x_elbow_R"} | \
    {n for n in bhead if n.endswith("_R") and re.match(r"^(thumb|index|middle|ring|pinky)_", n)}
is_rarm = np.isin(dom, list(RIGHT_ARM))
is_rfore = np.isin(dom, list(RIGHT_ARM - {"upperarm_R", "upperarm_twist_R", "x_elbow_R"}))


def enclosed(p):
    """True when every radial ray from p (in the cannon's rest frame) hits the cannon within 0.6 m."""
    for d in RAYS:
        if cbvh.ray_cast(Vector(p), d, 0.6)[0] is None:
            return False
    return True


# ---- helpers per frame --------------------------------------------------------------------------------------------------
def mesh_co():
    e = body.evaluated_get(dg)
    me = e.to_mesh()
    co = np.empty(NV * 3)
    me.vertices.foreach_get("co", co)
    e.to_mesh_clear()
    M = np.array(body.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def heads():
    return {pb.name: np.array(Ma @ pb.head) for pb in arm.pose.bones}


def pose_mats():
    return {pb.name: np.array(Ma @ pb.matrix) for pb in arm.pose.bones}


def ang(a, b):
    c = np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def joints(H):
    o = {}
    for s in "LR":
        o["knee_" + s] = ang(H["shin_" + s] - H["thigh_" + s], H["foot_" + s] - H["shin_" + s])
        o["elbow_" + s] = ang(H["lowerarm_" + s] - H["upperarm_" + s], H["hand_" + s] - H["lowerarm_" + s])
        d = H["lowerarm_" + s] - H["upperarm_" + s]
        o["elev_" + s] = math.degrees(math.asin(d[2] / np.linalg.norm(d)))
        o["wrist_" + s] = ang(H["hand_" + s] - H["lowerarm_" + s], H["middle_01_" + s] - H["hand_" + s])
        o["thigh_" + s] = ang(np.array([0, 0, -1.0]), H["shin_" + s] - H["thigh_" + s])
    o["pelvis_z"] = float(H["pelvis"][2])
    o["pelvis_xy"] = float(np.linalg.norm(H["pelvis"][:2]))
    return o


POLYS = [tuple(p.vertices) for p in body.data.polygons]
_pdom = [dom[p[0]] for p in POLYS]
LEGB = re.compile(r"^(thigh|thigh_twist|shin|foot|toe|x_knee|x_tasset)_[LR]$")
P_CAPE = [p for p, d in zip(POLYS, _pdom) if d.startswith("x_cape")]
P_LOIN = [p for p, d in zip(POLYS, _pdom) if d.startswith("x_loin")]
P_LEG = [p for p, d in zip(POLYS, _pdom) if LEGB.match(d)]


def through(co, cloth_polys):
    """Leg faces (thighs, knees, shins, sabatons, tassets) that cut a cloth face (triangle-triangle overlap)."""
    pts = [tuple(x) for x in co]
    a = BVHTree.FromPolygons(pts, cloth_polys)
    b = BVHTree.FromPolygons(pts, P_LEG)
    return len({j for _i, j in a.overlap(b)})


REST_THROUGH = {"cape": through(rest, P_CAPE), "loin": through(rest, P_LOIN)}
CONTACT_Z = 0.005     # a sole vertex within 5 mm of the ground in two frames is in contact (1 cm also caught swings skimming it)
FOOT = {}
for s in "LR":
    FOOT[s] = np.where(np.isin(dom, ["foot_" + s, "toe_" + s]) | ((dom == "shin_" + s) & (rest[:, 2] < 0.25)))[0]
Hrest = heads()
J0 = joints(Hrest)
WRIST0 = {s: J0["wrist_" + s] for s in "LR"}


def set_clip(act, f):
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    scene.frame_set(f)


# ---- references for the upper-layer rule ---------------------------------------------------------------------------------
acts = {a["name"]: bpy.data.actions[a["name"]] for a in g.doc["animations"]}
key = "valdris"
REF, REF_CO = {}, {}
for base in ("idle_combat@loop", "siege_stance@loop", "mountainfall@loop"):
    set_clip(acts["%s_%s" % (key, base)], 0)
    REF[base.replace("@loop", "")] = pose_mats()
    REF_CO[base.replace("@loop", "")] = None       # filled once mesh_co exists

for _b in list(REF_CO):
    set_clip(acts["%s_%s@loop" % (key, _b)], 0)
    REF_CO[_b] = mesh_co()
UPPER_MASK = set()
_stack = ["spine_01"]
while _stack:
    _n = _stack.pop()
    UPPER_MASK.add(_n)
    _stack += [c.name for c in bones[_n].children]
in_mask = np.isin(dom, list(UPPER_MASK))

# ---- the clip pass ------------------------------------------------------------------------------------------------------
from s2lib import aim_ortho, render_still  # noqa: E402

ground = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
ground.data.from_pydata([(-8, -8, 0), (8, -8, 0), (8, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
gm = bpy.data.materials.new("ground")
gm.diffuse_color = (0.30, 0.27, 0.25, 1)
ground.data.materials.append(gm)
scene.collection.objects.link(ground)
for _m in body.data.materials:            # Workbench TEXTURE mode shows the ACTIVE image node: make it the base colour
    _t = [n for n in _m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and "basecolor" in n.image.name]
    if _t:
        _m.node_tree.nodes.active = _t[0]
for _o in cmeshes:
    for _m in _o.data.materials:
        _t = [n for n in _m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image and "basecolor" in n.image.name]
        if _t:
            _m.node_tree.nodes.active = _t[0]
scene.render.engine = "BLENDER_WORKBENCH"
sh = scene.display.shading
sh.light, sh.color_type = "STUDIO", "TEXTURE"
sh.show_cavity, sh.cavity_type = True, "BOTH"
sh.show_shadows = False
scene.display.render_aa = "8"
scene.render.film_transparent = False
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.color = (0.12, 0.12, 0.14)
scene.view_settings.view_transform = "Standard"


def view_dir(az_d, el_d):
    az, el = math.radians(az_d), math.radians(el_d)
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))


VIEWS = [  # name, target(H) -> point, azimuth, elevation, ortho scale; az 0 = from his front (-Y), +az toward his left
    ("shoulders", lambda H: (H["upperarm_L"] + H["upperarm_R"]) / 2 + np.array([0, 0, 0.05]), 25, 35, 1.7),
    ("cannon_elbow", lambda H: H["lowerarm_R"], -75, 15, 1.25),
    ("left_elbow", lambda H: H["lowerarm_L"], 75, 15, 1.1),
    ("knees", lambda H: (H["shin_L"] + H["shin_R"]) / 2 + np.array([0, 0, -0.05]), 30, 12, 1.5),
    ("cape", lambda H: np.array([H["pelvis"][0], H["pelvis"][1], 1.05]), 205, 12, 2.7),
]


def render_views(tag, H):
    out = []
    for name, tgt, az, el, sc in VIEWS:
        aim_ortho(scene, tuple(tgt(H)), view_dir(az, el), sc)
        p = os.path.join(OUT, "renders", "%s_%s.png" % (tag, name))
        render_still(scene, p, 320, 320)
        out.append(os.path.relpath(p, OUT).replace("\\", "/"))
    return out


clips = {}
names = [a["name"] for a in g.doc["animations"]]
for an in names:
    clip = an[len(key) + 1:]
    base_clip = clip.replace("@loop", "")
    if ONLY and clip not in ONLY and base_clip not in ONLY:
        continue
    act = acts[an]
    info = meta["clip_info"][an]
    N = int(round(act.frame_range[1]))
    loop = clip.endswith("@loop")
    trav = np.array(info.get("travel_mps") or [0.0, 0.0], float)
    planted_v = -trav / V.FPS                  # an in-place clip: a planted foot moves against the travel
    P = []
    J = []
    lowest = []
    cannon_poke, cannon_cuts, cut_bones = [], [], {}
    thr_cape, thr_loin = [], []
    cand_idx = np.where(np.linalg.norm(rest - grip, axis=1) < 1.5)[0]
    for f in range(N + 1):
        set_clip(act, f)
        co = mesh_co()
        H = heads()
        P.append(co)
        J.append(joints(H))
        lowest.append((float(co[:, 2].min()), str(dom[int(np.argmin(co[:, 2]))]), int((co[:, 2] < -0.02).sum())))
        # the cannon, in its rest frame
        Tm = C_rest @ np.linalg.inv(np.array(croot.matrix_world))     # posed world -> the cannon's rest frame
        loc = co @ Tm[:3, :3].T + Tm[:3, 3]
        rel = loc - grip
        ta = rel @ axis
        radial = np.linalg.norm(rel - np.outer(ta, axis), axis=1)
        inside_len = (ta > t_lo + 0.01) & (ta < t_hi - 0.01) & (radial < 0.35)
        poke = cuts = 0
        for i in np.where(inside_len & is_rfore)[0]:
            if not enclosed(loc[i]):
                poke += 1
        for i in np.where(inside_len & ~is_rfore & (radial < 0.25))[0]:
            if enclosed(loc[i]):
                cuts += 1
                cut_bones[dom[i]] = cut_bones.get(dom[i], 0) + 1
        cannon_poke.append(poke)
        cannon_cuts.append(cuts)
        thr_cape.append(through(co, P_CAPE))
        thr_loin.append(through(co, P_LOIN))
    P = np.array(P)
    # loop seam and pops (second differences per vertex)
    acc = np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=2) if N >= 2 else np.zeros((0, NV))
    solid_acc = acc[:, ~is_cloth].max(1) if len(acc) else np.zeros(0)
    cloth_acc = acc[:, is_cloth].max(1) if len(acc) else np.zeros(0)
    c = {"frames": N, "loop": loop}
    # cloth jitter: a vertex whose velocity reverses from one frame to the next while moving > 2 cm / frame both times
    V1 = P[1:] - P[:-1]
    spd = np.linalg.norm(V1, axis=2)
    rev = ((np.einsum("fvi,fvi->fv", V1[1:], V1[:-1]) < 0) & (spd[1:] > 0.02) & (spd[:-1] > 0.02)) if N >= 2 else np.zeros((0, NV), bool)
    c["jitter"] = {}
    for grp, sel in (("cape", IS_CAPE), ("loin", IS_LOIN), ("braids", IS_BRAID), ("solid", ~is_cloth)):
        c["jitter"][grp] = {"frames_with_reversals": int(rev[:, sel].any(1).sum()) if len(rev) else 0,
                            "reversal_vertex_frames": int(rev[:, sel].sum()) if len(rev) else 0,
                            "max_speed_mm_per_frame": r4(1000 * spd[:, sel].max()) if N else 0}
    if loop:
        seam = np.linalg.norm(P[1] - 2 * P[0] + P[N - 1], axis=1)
        c["loop_last_vs_first_mm"] = r4(1000 * np.linalg.norm(P[N] - P[0], axis=1).max())
        c["seam_acc_mm_solid"] = r4(1000 * seam[~is_cloth].max())
        c["seam_acc_mm_cloth"] = r4(1000 * seam[is_cloth].max())
    c["acc_max_mm_solid"] = r4(1000 * solid_acc.max()) if len(solid_acc) else 0
    c["acc_max_frame_solid"] = int(np.argmax(solid_acc)) + 1 if len(solid_acc) else 0
    c["acc_max_bone_solid"] = str(dom[~is_cloth][int(np.argmax(acc[int(np.argmax(solid_acc)), ~is_cloth]))]) if len(solid_acc) else ""
    c["acc_median_mm_solid"] = r4(1000 * np.median(solid_acc)) if len(solid_acc) else 0
    c["acc_max_mm_cloth"] = r4(1000 * cloth_acc.max()) if len(cloth_acc) else 0
    c["acc_max_frame_cloth"] = int(np.argmax(cloth_acc)) + 1 if len(cloth_acc) else 0
    # feet
    feet = {}
    for s in "LR":
        idx = FOOT[s]
        best, med, contacts, cur, cur_best = [], [], [], 0.0, 0.0
        per_contact = []
        for f in range(N):
            a, b = P[f][idx], P[f + 1][idx]
            m = (a[:, 2] < CONTACT_Z) & (b[:, 2] < CONTACT_Z)
            if m.sum() < 3:
                if cur_best > 0:
                    per_contact.append(cur_best)
                cur_best = 0.0
                continue
            d = np.linalg.norm((b[m, :2] - a[m, :2]) - planted_v, axis=1)
            best.append(float(d.min()))
            med.append(float(np.median(d)))
            cur_best += float(d.min())
        if cur_best > 0:
            per_contact.append(cur_best)
        feet[s] = {"contact_frames": len(best),
                   "anchor_slip_max_mm_per_frame": r4(1000 * max(best)) if best else 0,
                   "median_slip_max_mm_per_frame": r4(1000 * max(med)) if med else 0,
                   "anchor_slip_max_mm_per_contact": r4(1000 * max(per_contact)) if per_contact else 0}
    c["feet"] = feet
    # joints
    for k in ("knee_L", "knee_R", "elbow_L", "elbow_R", "thigh_L", "thigh_R"):
        c[k + "_max"] = r4(max(j[k] for j in J))
    for s in "LR":
        c["elev_%s_range" % s] = [r4(min(j["elev_" + s] for j in J)), r4(max(j["elev_" + s] for j in J))]
        c["wrist_%s_bend_max" % s] = r4(max(abs(j["wrist_" + s] - WRIST0[s]) for j in J))
    c["pelvis_z_min"] = r4(min(j["pelvis_z"] for j in J))
    c["pelvis_xy_max"] = r4(max(j["pelvis_xy"] for j in J))
    lo = min(lowest)
    c["lowest_z_mm"] = r4(1000 * lo[0])
    c["lowest_bone"] = lo[1]
    c["verts_below_minus_20mm_max"] = max(x[2] for x in lowest)
    c["legs_through_cape_faces_max"] = max(thr_cape)
    c["legs_through_cape_frame"] = int(np.argmax(thr_cape))
    c["legs_through_cape_frames"] = int(sum(1 for x in thr_cape if x > REST_THROUGH["cape"] + 5))
    c["legs_through_loin_faces_max"] = max(thr_loin)
    c["legs_through_loin_frames"] = int(sum(1 for x in thr_loin if x > REST_THROUGH["loin"] + 5))
    c["cannon_poke_max"] = max(cannon_poke)
    c["cannon_poke_frame"] = int(np.argmax(cannon_poke))
    c["cannon_cuts_max"] = max(cannon_cuts)
    c["cannon_cuts_frame"] = int(np.argmax(cannon_cuts))
    c["cannon_cut_bones"] = dict(sorted(cut_bones.items(), key=lambda kv: -kv[1])[:5])
    # upper-layer reference rule
    layer = info.get("layer")
    if layer == "upper":
        refname = (cj.get(base_clip) or {}).get("base") or "idle_combat"
        errs = []
        for f in (0, N):
            set_clip(act, f)
            pm = pose_mats()
            errs.append(max(float(np.abs(pm[b][:3, 3] - REF[refname][b][:3, 3]).max()) for b in pm))
        c["upper_reference"] = refname
        c["upper_first_last_vs_reference_m"] = [r4(e) for e in errs]
        c["upper_first_last_joint_err_m_by_group"] = {}
        for f in (0, N):
            set_clip(act, f)
            pm = pose_mats()
            for grp, sel in (("contract", lambda b: not b.startswith("x_")), ("cloth", lambda b: bool(CLOTH_RE.match(b))),
                             ("helpers", lambda b: b.startswith("x_") and not CLOTH_RE.match(b))):
                e = max(float(np.abs(pm[b][:3, :] - REF[refname][b][:3, :]).max()) for b in pm if sel(b))
                c["upper_first_last_joint_err_m_by_group"].setdefault(grp, []).append(r4(e))
        dv0 = np.linalg.norm(P[0] - REF_CO[refname], axis=1)
        dvN = np.linalg.norm(P[N] - REF_CO[refname], axis=1)
        c["upper_first_last_cloth_vertex_jump_mm"] = {
            "in_upper_mask (cape, beard)": [r4(1000 * dv0[is_cloth & in_mask].max()), r4(1000 * dvN[is_cloth & in_mask].max())],
            "loincloth (pelvis, outside the mask)": [r4(1000 * dv0[is_cloth & ~in_mask].max()), r4(1000 * dvN[is_cloth & ~in_mask].max())],
            "solid": [r4(1000 * dv0[~is_cloth].max()), r4(1000 * dvN[~is_cloth].max())]}
        if refname != "idle_combat":
            errs2 = []
            for f in (0, N):
                set_clip(act, f)
                pm = pose_mats()
                errs2.append(max(float(np.abs(pm[b][:3, 3] - REF["idle_combat"][b][:3, 3]).max()) for b in pm))
            c["upper_first_last_vs_idle_combat_m"] = [r4(e) for e in errs2]
    # the review frames
    kn = [max(j["knee_L"], j["knee_R"]) for j in J]
    el = [max(j["elev_L"], j["elev_R"]) for j in J]
    eb = [max(j["elbow_L"], j["elbow_R"]) for j in J]
    f_low = int(np.argmax(kn))
    f_up = int(np.argmax(el)) if max(el) > 20 else int(np.argmax(eb))
    if f_up == f_low:
        f_up = int(np.argmax(solid_acc)) + 1 if len(solid_acc) else N // 2
    c["review_frames"] = {"lower": f_low, "upper": f_up}
    if RENDERS:
        c["renders"] = {}
        for tagk, f in (("lower", f_low), ("upper", f_up)):
            set_clip(act, f)
            c["renders"][tagk] = render_views("%s_f%03d" % (base_clip, f), heads())
    clips[clip] = c
    log("   through cape %d (f%d, %d frames) loin %d (%d frames)" % (c["legs_through_cape_faces_max"], c["legs_through_cape_frame"],
        c["legs_through_cape_frames"], c["legs_through_loin_faces_max"], c["legs_through_loin_frames"]))
    log("%-22s N=%3d knee %5.1f elbowR %5.1f elevR %5.1f..%5.1f wristR %4.1f low %6.1f mm poke %d cuts %d slipL %s slipR %s acc %s mm" % (
        clip, N, c["knee_L_max"] if c["knee_L_max"] > c["knee_R_max"] else c["knee_R_max"], c["elbow_R_max"],
        c["elev_R_range"][0], c["elev_R_range"][1], c["wrist_R_bend_max"], c["lowest_z_mm"], c["cannon_poke_max"],
        c["cannon_cuts_max"], feet["L"]["anchor_slip_max_mm_per_contact"], feet["R"]["anchor_slip_max_mm_per_contact"],
        c["acc_max_mm_solid"]))
# the cape from behind in the poses where the legs meet it (the review's before / after sheet)
CAPE_SHOTS = [("downed@loop", 0), ("downed@loop", 45), ("knockdown", 14), ("knockdown", 36), ("death", 22), ("death", 56),
              ("get_up", 8), ("reforge_in", 12)]
if RENDERS and not ONLY:
    rep["cape_shots"] = []
    for clip, f in CAPE_SHOTS:
        set_clip(acts["%s_%s" % (key, clip)], f)
        H = heads()
        aim_ortho(scene, (float(H["pelvis"][0]), float(H["pelvis"][1]), 1.0), view_dir(205, 12), 2.8)
        pth = os.path.join(OUT, "renders", "cape_%s_f%03d.png" % (clip.replace("@loop", ""), f))
        render_still(scene, pth, 320, 320)
        rep["cape_shots"].append(os.path.relpath(pth, OUT).replace("\\", "/"))
arm.animation_data.action = None

# ---- the sidecar against the file ---------------------------------------------------------------------------------------
side = []
if sorted(meta.get("clips", [])) != sorted(names):
    side.append("sidecar clips != GLB animations")
for an in names:
    ci = meta["clip_info"].get(an) or {}
    for ev, x in (ci.get("events") or {}).items():
        if not (0 <= x["frame"] <= ci["frames"]):
            side.append("%s event %s at %d outside 0..%d" % (an, ev, x["frame"], ci["frames"]))
    b = (cj.get(ci.get("clip", "")) or {}).get("base")
    b_action = [a_ for a_, x in meta["clip_info"].items() if x.get("clip") == b]
    if b and ci.get("base") not in b_action:
        side.append("%s: the clip's reference pose is %s frame 0 (clips.json base) but the sidecar does not say so "
                    "(clip_info has no 'base'; playback.upper_layer says idle_combat frame 0)" % (an, b))
rep["sidecar_problems"] = side
rep["rest_legs_through_cloth_faces"] = REST_THROUGH
rep["clips"] = clips
with open(os.path.join(OUT, "review.json"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(rep, f, indent=1)
    f.write("\n")
log("wrote", os.path.join(OUT, "review.json"))
