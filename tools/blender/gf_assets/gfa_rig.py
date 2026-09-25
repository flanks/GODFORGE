"""GF_Swarm_v1: the shared swarm skeleton, rigid skinning and clip helpers (headless Blender 5.2).

SKELETON (gfa_spec.SWARM_BONES; every swarm GLB has exactly these six bones, unused ones stay
unweighted, so any swarm clip can drive any swarm scene - Bevy builds animation targets from the
bone-name path, docs/ART_PIPELINE.md section 2):

    GF_Swarm_v1 (armature object = glTF node; never rename it per enemy)
      root            ground pivot under the body centre (locomotion bob / death drop / turn)
        body          centre of mass: the shell / torso
          head        head, jaw, maw or front mass
          legs_a      gait group A: all limbs that move together in phase A (tripod gait: L1 + R2 + L3)
          legs_b      gait group B: the other limbs (phase B)
          tail        rear mass: abdomen, tail, back spikes, trailing ichor sac

Limbs are driven as RIGID GROUPS (one bone per gait group), which is exactly how a skittering swarm
reads at 6 % of screen height: alternate rocking of the two leg groups + a body bob. A creature with
no tail or no head simply leaves that bone unweighted.

REST ORIENTATION: every bone points straight up (+Z) from its pivot with roll 0, so all bones share one
local frame: local X = the creature's LEFT (+X), local Y = up (+Z), local Z = forward (-Y).
Pose rotations (degrees, XYZ Euler, in that local frame):
    +X  pitch nose-down / fold forward        (a leg group swings its feet backward)
    +Y  yaw toward the creature's left
    +Z  roll: the left side goes up
Pose locations (metres, local frame): +X left, +Y up, +Z forward.

CLIPS: {key}_{clip}, loops end in @loop (gfa_spec.ENEMY_CLIPS_REQUIRED:
idle@loop, move@loop, windup, attack, hit, death). Each clip is an action stashed as its own NLA track
named exactly like the clip; gfa_export writes one glTF animation per track. Loops are sampled every
frame from a periodic pose function (cycle_clip), so the first and last frames match and the loop has
no hitch; one-shots are Bezier-keyed poses (keyed_clip).

Adapted from Ashen Covenant tools/blender/ac_humanoid_enemy/ac_rig_base.py (table-driven armature
build + hierarchy validation), ac_crawler_rig.py (crawler pose vocabulary) and ac_pose.py
(pose dicts, keying, NLA stashing, Blender 4.4+ layered-action f-curve access).
"""
import math

import bpy
from mathutils import Euler, Matrix, Vector

import gfa_common as C
import gfa_spec as SPEC

RIG_NAME = SPEC.SWARM_SKELETON
BONE_NAMES = [b for b, _ in SPEC.SWARM_BONES]


# ---- armature -----------------------------------------------------------------------------------------

def build_swarm_rig(pivots, bone_len=0.08, name=RIG_NAME, col=None):
    """Create GF_Swarm_v1. pivots: {bone: (x, y, z)} creature-space pivot points (metres, the creature
    faces -Y, ground at z = 0); missing bones default to the body pivot (root defaults to the ground under
    it). bone_len: display length (the tail sits bone_len above the pivot)."""
    body = Vector(pivots.get("body", (0.0, 0.0, 0.3)))
    default = {"root": Vector((body.x, body.y, 0.0)), "body": body}
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    (col or bpy.context.scene.collection).objects.link(arm)
    C.select_only(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for bname, parent in SPEC.SWARM_BONES:
        p = Vector(pivots.get(bname, default.get(bname, body)))
        b = eb.new(bname)
        b.head = p
        b.tail = p + Vector((0.0, 0.0, bone_len))
        b.roll = 0.0
        b.use_deform = True
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    arm_data.display_type = "STICK"
    arm.show_in_front = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    return arm


def validate_rig(arm):
    """Problems (empty list = OK) comparing an armature with GF_Swarm_v1."""
    probs = []
    if arm.name != RIG_NAME:
        probs.append("armature object is %r, must be %r" % (arm.name, RIG_NAME))
    bones = arm.data.bones
    for bname, parent in SPEC.SWARM_BONES:
        if bname not in bones:
            probs.append("missing bone %s" % bname)
            continue
        ap = bones[bname].parent.name if bones[bname].parent else None
        if ap != parent:
            probs.append("%s parent is %s, expected %s" % (bname, ap, parent))
        if not bones[bname].use_deform:
            probs.append("%s must be a deform bone (the exporter drops non-deform bones)" % bname)
    extra = [b.name for b in bones if b.name not in BONE_NAMES]
    if extra:
        probs.append("extra bones %s (GF_Swarm_v1 has exactly six)" % extra)
    return probs


def skin_rigid(mesh_obj, arm):
    """Bind a mesh whose vertex groups are named after bones (gfa_model.Assembly(bones=...)) to the
    armature: Armature modifier + parent, every vertex 100 % on one bone. Returns a report."""
    me = mesh_obj.data
    names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    bad = [n for n in names.values() if n not in BONE_NAMES]
    if bad:
        raise ValueError("vertex groups %s are not GF_Swarm_v1 bones" % bad)
    unweighted, multi = 0, 0
    per_bone = {n: 0 for n in BONE_NAMES}
    for v in me.vertices:
        g = [x for x in v.groups if x.weight > 0]
        if not g:
            unweighted += 1
        elif len(g) > 1:
            multi += 1
        else:
            per_bone[names[g[0].group]] += 1
    mesh_obj.parent = arm
    mesh_obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = mesh_obj.modifiers.get("Armature") or mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    rep = {"vertices": len(me.vertices), "unweighted": unweighted, "multi_bone": multi, "per_bone": per_bone}
    if unweighted:
        raise ValueError("%d vertices have no bone (every part needs a bone in Assembly.add)" % unweighted)
    return rep


def add_socket(arm, bone, name, world_pos, size=0.04):
    """An empty parented to `bone` at a world position (exported as a child node of that joint)."""
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "SPHERE"
    e.empty_display_size = size
    for c in arm.users_collection:
        c.objects.link(e)
    e.parent = arm
    e.parent_type = "BONE"
    e.parent_bone = bone
    bpy.context.view_layer.update()
    e.matrix_world = Matrix.Translation(Vector(world_pos))
    return e


# ---- poses & clips ------------------------------------------------------------------------------------

def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def apply_pose(arm, pose):
    """pose: {bone: {"rot": (x, y, z) degrees, "loc": (x, y, z) m, "scale": s or (x, y, z)}} (local frame,
    see module doc). Bones not listed return to rest."""
    reset_pose(arm)
    for bname, tr in pose.items():
        pb = arm.pose.bones.get(bname)
        if pb is None:
            raise KeyError("pose names unknown bone %r" % bname)
        if "rot" in tr:
            pb.rotation_euler = Euler([math.radians(a) for a in tr["rot"]], "XYZ")
        if "loc" in tr:
            pb.location = Vector(tr["loc"])
        if "scale" in tr:
            s = tr["scale"]
            pb.scale = (s, s, s) if isinstance(s, (int, float)) else tuple(s)


def merge(*poses):
    out = {}
    for p in poses:
        for b, tr in p.items():
            out.setdefault(b, {}).update(tr)
    return out


def _fcurves(action):
    # Blender 4.4+ layered actions: f-curves live in action.layers[].strips[].channelbags[]
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    yield from cb.fcurves
    else:
        yield from action.fcurves


def _key_all(arm, frame):
    for pb in arm.pose.bones:
        pb.keyframe_insert("rotation_euler", frame=frame)
        pb.keyframe_insert("location", frame=frame)
        pb.keyframe_insert("scale", frame=frame)


def _new_action(arm, name, f0, f1):
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
    act.frame_start, act.frame_end = f0, f1
    act.use_fake_user = True
    return act


def _stash(arm, act, loop):
    ad = arm.animation_data
    tr = ad.nla_tracks.new()
    tr.name = act.name
    strip = tr.strips.new(act.name, int(act.frame_start), act)
    strip.name = act.name
    tr.mute = True
    ad.action = None
    act["gfa_loop"] = bool(loop)
    return tr


def clip_name(key, clip):
    return "%s_%s" % (key, clip)


def cycle_clip(arm, key, clip, frames, pose_fn):
    """Seamless loop: pose_fn(t) for t in [0, 1] (periodic: pose_fn(1) == pose_fn(0)) keyed on EVERY frame
    0..frames (linear), so the exported samples loop with no hitch. clip should end in '@loop'."""
    name = clip_name(key, clip)
    act = _new_action(arm, name, 0, frames)
    for f in range(frames + 1):
        apply_pose(arm, pose_fn(f / frames))
        _key_all(arm, f)
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    reset_pose(arm)
    _stash(arm, act, True)
    return act


def keyed_clip(arm, key, clip, keys, interpolation="BEZIER"):
    """One-shot clip from [(frame, pose), ...] (frames from 0). Bezier with auto-clamped handles eases
    in/out of every key; use 'CONSTANT' keys for snaps, 'LINEAR' for mechanical moves."""
    name = clip_name(key, clip)
    f0, f1 = keys[0][0], keys[-1][0]
    act = _new_action(arm, name, f0, f1)
    for f, pose in keys:
        apply_pose(arm, pose)
        _key_all(arm, f)
    for fc in _fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = interpolation
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
    reset_pose(arm)
    _stash(arm, act, clip.endswith("@loop"))
    return act


def clips_report(arm, fps=None):
    fps = fps or bpy.context.scene.render.fps
    out = []
    if not arm.animation_data:
        return out
    for tr in arm.animation_data.nla_tracks:
        for s in tr.strips:
            a = s.action
            out.append({"name": tr.name, "frames": [int(a.frame_start), int(a.frame_end)],
                        "seconds": round((a.frame_end - a.frame_start) / fps, 3), "loop": tr.name.endswith("@loop")})
    return out


def pose_at(arm, clip_track, frame):
    """Show one clip at one frame (review renders): unmute only that track, evaluate, return."""
    ad = arm.animation_data
    for tr in ad.nla_tracks:
        tr.mute = tr.name != clip_track
        tr.is_solo = False
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()


def unmute_none(arm):
    if arm.animation_data:
        for tr in arm.animation_data.nla_tracks:
            tr.mute = True
    reset_pose(arm)


# ---- a ready-made swarm clip set (tune the amplitudes per creature) ------------------------------------

def swarm_clip_set(arm, key, fps=30, scale=1.0, gait_deg=28.0, bob=0.03, speed=1.0, head_bite=35.0):
    """The six required clips for a skittering crawler on GF_Swarm_v1. scale: creature size (1 = 0.6 m
    long); gait_deg: leg-group swing; bob: body bounce (m); speed: loop tempo multiplier.
    Returns the list of clip names. Individual enemies may replace any clip with their own."""
    s = scale
    move_frames = max(8, int(round(12 / speed)))       # one full gait cycle: ~0.4 s -> reads as a SKITTER
    idle_frames = 48

    def idle(t):
        w = 2 * math.pi * t
        return {"body": {"loc": (0, bob * 0.25 * s * math.sin(w), 0), "rot": (2.5 * math.sin(w), 0, 1.5 * math.sin(w + 1))},
                "head": {"rot": (-4 * math.sin(w + 0.6), 6 * math.sin(w * 1.0 + 2.0), 0)},
                "legs_a": {"rot": (3 * math.sin(w), 0, 0)}, "legs_b": {"rot": (-3 * math.sin(w), 0, 0)},
                "tail": {"rot": (4 * math.sin(w + 1.3), 5 * math.sin(w + 0.4), 0)}}

    def move(t):
        w = 2 * math.pi * t
        a = gait_deg
        return {"root": {"loc": (0, bob * s * abs(math.sin(w)), 0)},
                "body": {"rot": (6.0, 0, 7 * math.sin(w)), "loc": (0, 0, 0.01 * s * math.sin(2 * w))},
                "head": {"rot": (-8 + 5 * math.sin(2 * w), 8 * math.sin(w), 0)},
                "legs_a": {"rot": (a * math.sin(w), 0, 6 * math.cos(w)), "loc": (0, 0.012 * s * max(0.0, math.cos(w)), 0)},
                "legs_b": {"rot": (-a * math.sin(w), 0, -6 * math.cos(w)), "loc": (0, 0.012 * s * max(0.0, -math.cos(w)), 0)},
                "tail": {"rot": (6 * math.sin(2 * w), 12 * math.sin(w + 0.5), 0)}}

    rest = {}
    crouch = {"root": {"loc": (0, -0.35 * bob * s, 0)}, "body": {"rot": (-14, 0, 0), "loc": (0, 0, -0.05 * s)},
              "head": {"rot": (-head_bite * 0.5, 0, 0)}, "legs_a": {"rot": (-12, 0, 0)}, "legs_b": {"rot": (-12, 0, 0)},
              "tail": {"rot": (18, 0, 0)}}
    lunge = {"root": {"loc": (0, 0.02 * s, 0.16 * s)}, "body": {"rot": (12, 0, 0), "loc": (0, 0, 0.08 * s)},
             "head": {"rot": (head_bite, 0, 0)}, "legs_a": {"rot": (30, 0, 0)}, "legs_b": {"rot": (22, 0, 0)},
             "tail": {"rot": (-15, 0, 0)}}
    flinch = {"body": {"rot": (-10, 8, -12), "loc": (0, 0.02 * s, -0.05 * s)}, "head": {"rot": (-18, -10, 0)},
              "legs_a": {"rot": (-10, 0, 8)}, "legs_b": {"rot": (8, 0, -8)}, "tail": {"rot": (12, 0, 0)}}
    dead = {"root": {"loc": (0, -0.5 * bob * s, 0)}, "body": {"rot": (8, 0, 38), "loc": (0, -0.06 * s, 0)},
            "head": {"rot": (30, 0, 12)}, "legs_a": {"rot": (-40, 0, -25)}, "legs_b": {"rot": (-40, 0, 25)},
            "tail": {"rot": (-20, 0, 10)}}
    names = []
    cycle_clip(arm, key, "idle@loop", idle_frames, idle)
    cycle_clip(arm, key, "move@loop", move_frames, move)
    keyed_clip(arm, key, "windup", [(0, rest), (9, crouch), (14, merge(crouch, {"body": {"rot": (-16, 0, 0)}}))])
    keyed_clip(arm, key, "attack", [(0, crouch), (4, lunge), (8, merge(lunge, {"head": {"rot": (head_bite * 0.3, 0, 0)}})), (16, rest)])
    keyed_clip(arm, key, "hit", [(0, rest), (3, flinch), (10, rest)])
    keyed_clip(arm, key, "death", [(0, rest), (4, merge(flinch, {"body": {"rot": (-20, 0, 10)}})), (12, dead), (20, dead)])
    for c in ("idle@loop", "move@loop", "windup", "attack", "hit", "death"):
        names.append(clip_name(key, c))
    return names
