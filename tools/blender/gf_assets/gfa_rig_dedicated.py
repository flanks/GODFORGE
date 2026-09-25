"""gf_assets DEDICATED rigs for elites, mini-bosses and bosses (docs/art/ENEMIES.md section 6).

Swarms share GF_Swarm_v1 (gfa_rig.py). Everything bigger gets its own armature `GF_<PascalKey>_v1`
built from a bone table, with the GF_Hero_v1 core names for humanoids (docs/ART_PIPELINE.md section 5), so
hero clips can be retargeted later. This module gives:

  * build_armature(name, table)  bones from (name, parent, head, tail) rows; every bone use_deform = True
    (the glTF exporter drops non-deform bones), not connected (so any bone may translate: floating plates),
    roll by the Ashen Covenant convention: local +Y along the bone, local +Z toward the creature's front
    (-Y), so +X rotation swings a limb forward / bends the spine forward on both sides. Bones that point
    almost straight forward (feet, toes, props) take +Z = up instead;
  * skin_rigid(mesh, arm)        rigid skinning of an Assembly(bones=...) mesh to ANY bone set;
  * world-space posing helpers   set_matrix / aim_bone / two_bone_ik / rigid_follow: poses are solved per
    frame in armature space (feet planted by IK, props driving the arms that hold them) and written back
    as ordinary local transforms;
  * Keys + bake_clip             pose-to-pose parameter keys with per-segment easing, sampled on EVERY frame
    and keyed linearly (loops: periodic functions), stashed as NLA tracks named {key}_{clip}[@loop] exactly
    like gfa_rig clips, so gfa_export / gfa_rig.pose_at / gfa_render.review_enemy work unchanged.

Rotation mode stays XYZ Euler (the toolkit convention; gfa_rig.reset_pose sets it) and each baked Euler is
made compatible with the previous frame's, so sampled keys never flip.

Adapted from Ashen Covenant tools/blender/ac_humanoid_enemy/ac_humanoid_rig.py (landmark table, forward
roll, hierarchy validation) and ac_pose.py (aim_bone, IK bake), and from gfa_rig.py (NLA stashing).
Added by the forge_warden build (GODFORGE gf_assets enemy stage); additive, no shared module changed.
"""
import math

import bpy
from mathutils import Euler, Vector

import gfa_common as C

FORWARD = Vector((0.0, -1.0, 0.0))

# GF_Hero_v1 core (docs/ART_PIPELINE.md section 5): (name, parent)
HERO_CORE = [
    ("root", None), ("pelvis", "root"), ("spine_01", "pelvis"), ("spine_02", "spine_01"), ("spine_03", "spine_02"),
    ("neck", "spine_03"), ("head", "neck"),
    ("clavicle_L", "spine_03"), ("upperarm_L", "clavicle_L"), ("lowerarm_L", "upperarm_L"), ("hand_L", "lowerarm_L"),
    ("clavicle_R", "spine_03"), ("upperarm_R", "clavicle_R"), ("lowerarm_R", "upperarm_R"), ("hand_R", "lowerarm_R"),
    ("thigh_L", "pelvis"), ("shin_L", "thigh_L"), ("foot_L", "shin_L"), ("toe_L", "foot_L"),
    ("thigh_R", "pelvis"), ("shin_R", "thigh_R"), ("foot_R", "shin_R"), ("toe_R", "foot_R"),
]


# ---- armature ------------------------------------------------------------------------------------------

def build_armature(name, table, col=None, forward=FORWARD, forward_limit=0.85):
    """table: [(bone, parent, head_xyz, tail_xyz), ...] in creature space (faces -Y, Z up), parents first."""
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    (col or bpy.context.scene.collection).objects.link(arm)
    C.select_only(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for bname, parent, head, tail in table:
        b = eb.new(bname)
        b.head = Vector(head)
        b.tail = Vector(tail)
        b.use_deform = True
        b.use_connect = False
        if parent:
            b.parent = eb[parent]
        d = (b.tail - b.head).normalized()
        b.align_roll(Vector((0, 0, 1)) if abs(d.dot(forward)) > forward_limit else forward)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm_data.display_type = "OCTAHEDRAL"
    arm.show_in_front = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    return arm


def validate_core(arm, core=HERO_CORE):
    """Problems (empty = OK): the humanoid core names and parents of GF_Hero_v1, deform flags."""
    probs = []
    bones = arm.data.bones
    for bname, parent in core:
        if bname not in bones:
            probs.append("missing core bone %s" % bname)
            continue
        ap = bones[bname].parent.name if bones[bname].parent else None
        if ap != parent:
            probs.append("%s parent is %s, expected %s" % (bname, ap, parent))
    for b in bones:
        if not b.use_deform:
            probs.append("%s is not a deform bone (the exporter drops it)" % b.name)
    return probs


def skin_rigid(mesh_obj, arm):
    """Armature modifier + parent; every vertex must sit 100 % on one bone (Assembly(bones=...))."""
    me = mesh_obj.data
    names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    bad = [n for n in names.values() if n not in arm.data.bones]
    if bad:
        raise ValueError("vertex groups %s are not bones of %s" % (bad, arm.name))
    per_bone = {}
    unweighted = multi = 0
    for v in me.vertices:
        g = [x for x in v.groups if x.weight > 0]
        if not g:
            unweighted += 1
        elif len(g) > 1:
            multi += 1
        else:
            n = names[g[0].group]
            per_bone[n] = per_bone.get(n, 0) + 1
    if unweighted:
        raise ValueError("%d vertices have no bone" % unweighted)
    mesh_obj.parent = arm
    mesh_obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = mesh_obj.modifiers.get("Armature") or mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    return {"vertices": len(me.vertices), "multi_bone": multi, "per_bone": per_bone}


# ---- world-space posing ------------------------------------------------------------------------------------

def update():
    bpy.context.view_layer.update()


def reset(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def rest(arm, bone):
    """Armature-space rest matrix of a bone."""
    return arm.data.bones[bone].matrix_local.copy()


def set_matrix(arm, bone, mat, upd=True):
    """Pose `bone` so its armature-space matrix equals `mat` (parents must be posed and updated)."""
    pb = arm.pose.bones[bone]
    pb.matrix = mat
    if upd:
        update()


def rest_frame_now(arm, bone):
    """Armature-space matrix the bone would have with an identity local transform (its posed parent
    carried over): the frame its local rotations / locations are expressed in."""
    b = arm.data.bones[bone]
    if b.parent is None:
        return b.matrix_local.copy()
    ppb = arm.pose.bones[b.parent.name]
    return ppb.matrix @ (b.parent.matrix_local.inverted() @ b.matrix_local)


def aim_bone(arm, bone, target, upd=True):
    """Rotate `bone` (minimal twist) so its +Y axis points from its posed head to `target` (armature space).
    The bone's own location offset (floating plates) is kept."""
    fr = rest_frame_now(arm, bone)
    pb = arm.pose.bones[bone]
    head = fr.translation + fr.to_3x3() @ Vector(pb.location)
    cur = fr.to_3x3() @ Vector((0, 1, 0))
    want = Vector(target) - head
    if want.length < 1e-9:
        return
    q = cur.rotation_difference(want.normalized())
    m = (q.to_matrix() @ fr.to_3x3()).to_4x4()
    m.translation = head
    set_matrix(arm, bone, m, upd)


def two_bone_ik(arm, upper, lower, target, hint, upd=True):
    """Place upper + lower so the lower bone's TAIL reaches `target` (clamped when out of reach), bending
    toward `hint` (a direction). Keeps each bone's rest length. Returns the reach error (m)."""
    fr = rest_frame_now(arm, upper)
    H = fr.translation.copy()
    bu, bl = arm.data.bones[upper], arm.data.bones[lower]
    L1 = (bl.head_local - bu.head_local).length          # hip -> knee (heads; bones are not connected)
    L2 = bl.length
    T = Vector(target)
    d = T - H
    dist = d.length
    reach = max(1e-4, min(dist, (L1 + L2) * 0.9995, ))
    reach = max(reach, abs(L1 - L2) + 1e-4)
    u = d.normalized()
    w = Vector(hint) - u * Vector(hint).dot(u)
    if w.length < 1e-6:
        w = Vector((0, -1, 0)) - u * (-u.y)
    w.normalize()
    ca = (L1 * L1 + reach * reach - L2 * L2) / (2 * L1 * reach)
    a = math.acos(max(-1.0, min(1.0, ca)))
    K = H + (u * math.cos(a) + w * math.sin(a)) * L1
    aim_bone(arm, upper, K, True)
    aim_bone(arm, lower, H + u * reach, upd)
    return max(0.0, dist - reach)


def rigid_follow(arm, bone, driver_now, driver_rest, upd=True):
    """Pose `bone` rigidly attached to a driver frame: rest relation kept (armature-space matrices)."""
    rel = driver_rest.inverted() @ rest(arm, bone)
    set_matrix(arm, bone, driver_now @ rel, upd)


def euler_deg(rot):
    return Euler([math.radians(a) for a in rot], "XYZ")


# ---- parameter keys ------------------------------------------------------------------------------------

def _ease(kind, t):
    t = max(0.0, min(1.0, t))
    if kind == "linear":
        return t
    if kind == "in":           # accelerate into the key (impacts)
        return t * t * t
    if kind == "out":          # burst out, decelerate into the key
        return 1 - (1 - t) ** 3
    if kind == "snap":         # most of the change early (anticipation release)
        return 1 - (1 - t) ** 5
    return t * t * (3 - 2 * t)  # "ease"


def _lerp_val(a, b, t):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * t
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    return b if t >= 0.5 else a


def _zero_like(v):
    if isinstance(v, (int, float)):
        return 0.0
    if isinstance(v, (tuple, list)):
        return tuple(0.0 for _ in v)
    return v


def _flat(pose):
    out = {}
    for k, d in pose.items():
        if isinstance(d, dict):
            for p, v in d.items():
                out[(k, p)] = v
        else:
            out[(k, None)] = d
    return out


def _unflat(flat):
    out = {}
    for (k, p), v in flat.items():
        if p is None:
            out[k] = v
        else:
            out.setdefault(k, {})[p] = v
    return out


DEFAULTS = {"scale": 1.0}


class Keys:
    """Pose-to-pose keys over parameter dicts {name: {param: value}}. Missing params count as their rest
    value (0 / (0,0,0) / scale 1). ease: per key, the curve of the segment that ENDS on that key
    ('ease' | 'in' | 'out' | 'snap' | 'linear')."""

    def __init__(self, keys):
        self.keys = sorted(keys, key=lambda k: k[0])
        names = set()
        for k in self.keys:
            names |= set(_flat(k[1]).keys())
        self.names = names
        self.frames = [k[0] for k in self.keys]
        self.poses = []
        for k in self.keys:
            f = _flat(k[1])
            full = {}
            for n in names:
                if n in f:
                    full[n] = f[n]
                else:
                    ref = next((_flat(kk[1])[n] for kk in self.keys if n in _flat(kk[1])), 0.0)
                    full[n] = DEFAULTS.get(n[1], _zero_like(ref)) if not isinstance(ref, str) else ref
            self.poses.append(full)
        self.eases = [k[2] if len(k) > 2 else "ease" for k in self.keys]

    @property
    def length(self):
        return self.frames[-1]

    def at(self, frame):
        F = self.frames
        if frame <= F[0]:
            return _unflat(self.poses[0])
        if frame >= F[-1]:
            return _unflat(self.poses[-1])
        for i in range(len(F) - 1):
            if F[i] <= frame <= F[i + 1]:
                t = (frame - F[i]) / max(1e-9, F[i + 1] - F[i])
                e = _ease(self.eases[i + 1], t)
                a, b = self.poses[i], self.poses[i + 1]
                return _unflat({n: _lerp_val(a[n], b[n], e) for n in self.names})
        return _unflat(self.poses[-1])


def merge(*poses):
    out = {}
    for p in poses:
        for k, v in p.items():
            if isinstance(v, dict):
                out.setdefault(k, {}).update(v)
            else:
                out[k] = v
    return out


# ---- baking clips --------------------------------------------------------------------------------------------

def _fcurves(action):
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    yield from cb.fcurves
    else:
        yield from action.fcurves


def clip_name(key, clip):
    return "%s_%s" % (key, clip)


def bake_clip(arm, key, clip, frames, pose_frame, mute_meshes=()):
    """Sample pose_frame(arm, f) for f in 0..frames (it must fully pose the armature, world-space solves
    included), then key rotation_euler / location / scale of EVERY bone on EVERY frame (linear) and stash
    the action as a muted NLA track named {key}_{clip}. Loops (clip ends in '@loop') must be periodic:
    pose(frames) == pose(0). Solving happens with no action assigned (so depsgraph updates never
    re-evaluate half-keyed animation over the solve); keys are written in a second pass. mute_meshes:
    skinned meshes whose Armature modifier is off while solving (only the armature has to evaluate)."""
    name = clip_name(key, clip)
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    ad.action = None
    for tr in ad.nla_tracks:
        tr.mute = True
    saved = []
    for m in mute_meshes:
        for mod in m.modifiers:
            if mod.type == "ARMATURE" and mod.show_viewport:
                mod.show_viewport = False
                saved.append(mod)
    samples = []
    prev = {}
    try:
        for f in range(frames + 1):
            pose_frame(arm, f)
            row = {}
            for pb in arm.pose.bones:
                e = pb.rotation_euler.copy()
                if pb.name in prev:
                    e.make_compatible(prev[pb.name])
                prev[pb.name] = e.copy()
                row[pb.name] = (tuple(e), tuple(pb.location), tuple(pb.scale))
            samples.append(row)
    finally:
        for mod in saved:
            mod.show_viewport = True
    act = bpy.data.actions.new(name)
    ad.action = act
    if hasattr(act, "slots"):
        slot = act.slots.new(id_type="OBJECT", name=arm.name)
        ad.action_slot = slot
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, frames
    act.use_fake_user = True
    for f, row in enumerate(samples):
        for pb in arm.pose.bones:
            e, loc, sc = row[pb.name]
            pb.rotation_euler = e
            pb.location = loc
            pb.scale = sc
            pb.keyframe_insert("rotation_euler", frame=f)
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("scale", frame=f)
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    ad.action = None
    reset(arm)
    tr = ad.nla_tracks.new()
    tr.name = name
    strip = tr.strips.new(name, 0, act)
    strip.name = name
    tr.mute = True
    act["gfa_loop"] = clip.endswith("@loop")
    update()
    return act
