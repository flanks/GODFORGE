"""Stage 3, Valdris: validation poses on GF_Hero_v1 with the colossus_cannon on weapon_R (headless Blender).

  blender -b -P tools/blender/gf_hero/s3_valdris_poses.py -- [--no-render] [--quick] [--only <pose,...>]

Valdris is a plate juggernaut: 168 rigid armour pieces over a MakeHuman under-suit, a protruding anvil on the chest,
pauldrons level with his crown, a cape, a braided beard resting on the anvil, and a sleeve cannon. So besides the
under-suit's deformation (the shared stage-3 numbers: stretch, collapsed 1-rings, volume) every pose is judged on what can
go wrong with rigid armour:
  * plates (s3_valdris_check.py): vertices of one piece that end up inside another piece in the pose but were not at rest
    (the pieces are closed, so "inside" is exact: ray parity, 3 mm deep), sorted into clipping (different regions),
    sliding (lames of one region) and suit (a plate inside the under-suit);
  * shoulders: collapsed under-suit 1-rings at the shoulders and anything cutting the pauldron stack or the head;
  * cloth: the cape, loincloth and braids are posed by s3_valdris_cloth.py (hang + clear, as the engine's spring would
    settle), then their vertices inside any body or armour piece or under the ground are counted;
  * the cannon (a sleeve weapon, rigid on weapon_R by the identity attach): right-arm vertices that leave its sleeve
    (visible poke-through: the 8 radial rays around the barrel axis no longer all hit it) and vertices of other pieces
    enclosed by it (the cannon cutting the anvil, a pauldron, a thigh).
The poses are written with the stage-4 solver (s4lib.Solver: analytic two-bone IK, the sleeve rule, foot placements), so
stage 4 inherits the same arm space. They come from the hero's own landmarks:
  bind, A-pose, cannon aimed forward, guard, Siege Stance brace, deep squat, lunge, torso twist, two head turns, the
  Bulwark Slam raise (both fists up in front of the face: straight overhead is blocked by the pauldrons, which sit right
  above the shoulder joints - reports/stage3/limits.json), forearm twist (the left fist), and the bare elbow 145 + knee 135
  stress pose. Arm poses stay inside the ranges the sweeps measured (s3_valdris_limits.py).
Selected poses are also measured with the driven helpers muted, which is the case for them.

Outputs: work/renders/stage3/pose_<nn>_<name>_<view>.png, reports/stage3/poses.json, the action GF_ValidationPoses stashed
(muted) in production/valdris_rig.blend with one marker per pose.
"""
import ast
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import s4lib as L  # noqa: E402
from s2lib import aim_ortho, az_dir, log, read_json, render_still, save_blend, script_args, setup_workbench, write_json  # noqa: E402
from s3lib import cycles_cpu, fcurves, hero_paths, make_toon_cycles, new_action, push_to_nla  # noqa: E402
from s3_valdris_check import Checker, inside, piece_table_path  # noqa: E402
from s3_valdris_cloth import ClothGroup, Pieces  # noqa: E402

KEY = "valdris"
argv = script_args(__doc__)
RENDER = "--no-render" not in argv
QUICK = "--quick" in argv
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
OUT = P["renders"]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=P["rig"])
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
body = bpy.data.objects["BODY"]
parts = {o.name: o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not body}
cannon = bpy.data.objects.get("PREVIEW_colossus_cannon_R")
LM = read_json(P["landmarks"])
SKIN = read_json(P["skin_cfg"])
report = {"hero": KEY, "poses": {}}
T0 = time.time()
if arm.animation_data:
    arm.animation_data.action = None
    for tr in list(arm.animation_data.nla_tracks):
        if tr.name == "GF_ValidationPoses":
            arm.animation_data.nla_tracks.remove(tr)

# ---- solver + pose set -------------------------------------------------------------------------------------------------
CK = Checker(arm, piece_table_path(P), cannon)
solid_objs = CK.solid
RIG = L.Rig(arm)
K = L.Kit(LM)
SOL = L.Solver(RIG, K)
HELPERS = [b.name for b in arm.data.bones if b.name.startswith(("x_pauldron", "x_elbow", "x_knee", "x_tasset", "x_fauld"))]
V = lambda k: Vector(R.point(LM, k))  # noqa: E731
SH = {s: V("shoulder_" + s) for s in ("L", "R")}
L1 = RIG.b["upperarm_L"].length
L2 = RIG.fist_eff["R"].length


def d(el, az, side):
    """Direction with elevation el above the horizontal and azimuth az from out-to-the-side (0) toward the front (90)."""
    sx = 1.0 if side == "L" else -1.0
    e, a = math.radians(el), math.radians(az)
    return Vector((sx * math.cos(e) * math.cos(a), -math.cos(e) * math.sin(a), math.sin(e)))


def arm_spec(side, fist, pole, back=(0.0, 0.0, 1.0), space="chest", twist=0.0):
    s = SH[side]
    return {"arm_" + side: {"fist": tuple((Vector(fist) - s) / K.as_), "pole": tuple((Vector(pole) - s) / K.as_),
                            "back": tuple(back), "space": space, "twist": twist}}


def arm_dirs(side, upper, fore, back=(0.0, 0.0, 1.0), twist=0.0):
    """An arm from its upper-arm direction and forearm direction ((elevation, azimuth) each, in the rest chest frame):
    the stage-4 effector (the middle knuckle on the forearm axis), the pole beyond the elbow. The right arm's back of the
    hand (0, 0, 1) keeps the colossus_cannon upright."""
    du, df = d(*upper, side), d(*fore, side)
    E = SH[side] + du * L1
    return arm_spec(side, E + df * L2, E + du * 0.25, back=back, twist=twist)


def feet(ball_l, ball_r=None, yaw=0.0, heel_l=0.0, heel_r=0.0, yaw_r=None):
    br = ball_r if ball_r is not None else (-ball_l[0], ball_l[1])
    return {"foot_L": {"ball": (ball_l[0] / K.ls, ball_l[1] / K.ls), "yaw": yaw, "heel": heel_l},
            "foot_R": {"ball": (br[0] / K.ls, br[1] / K.ls), "yaw": -(yaw if yaw_r is None else yaw_r), "heel": heel_r}}


def pelvis(loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
    return {"pelvis": {"loc": tuple(v / K.ls for v in loc), "rot": rot}}


BALL = (float(V("ball_L").x), float(V("ball_L").y))
FISTS = {"fingers_L": 1.0, "fingers_R": 1.0}
APOSE = {"upperarm_L": {"rot": (4, 0, -48)}, "lowerarm_L": {"rot": (12, 0, 0)},
         "upperarm_R": {"rot": (4, 0, 48)}, "lowerarm_R": {"rot": (12, 0, 0)}}
STANCE = L.merge(pelvis((0, 0, -0.05)), feet((BALL[0] + 0.03, BALL[1]), yaw=8))
# the cannon forward: upper arm out and a little forward and down, elbow ~33 deg (the clean range with the sleeve, limits.json
# "cannon"), the waist turned 14 deg to his left so the barrel points ahead; the head turned back to the front
AIM = L.merge(arm_dirs("R", (-18, 38), (-8, 70)), {"spine_01": {"rot": (2, 10, 0)}, "spine_02": {"rot": (0, 4, 0)},
                                                   "neck": {"rot": (0, -8, 0)}, "head": {"rot": (0, -6, 0)}})
LOW_FIST = arm_dirs("L", (-50, 25), (-15, 80), back=(0.5, -0.2, 1.0))

# (name, pose, cannon shown, also measured with the driven helpers off)
POSES = [
    ("bind", {}, True, False),
    ("apose", L.merge(APOSE, FISTS), True, True),
    ("cannon_aim", L.merge(STANCE, AIM, LOW_FIST, FISTS), True, False),
    ("guard", L.merge(STANCE, AIM, {"arm_R": arm_dirs("R", (-30, 35), (-20, 72))["arm_R"]},
                      arm_dirs("L", (-8, 25), (22, 80), back=(0.7, -0.4, 0.4)), {"spine_01": {"rot": (5, 10, 0)}}, FISTS), True, False),
    ("siege_brace", L.merge(pelvis((0, 0.06, -0.24), (6, 0, 0)), feet((0.55, -0.18), yaw=20),
                            {"spine_01": {"rot": (6, 12, 0)}, "spine_02": {"rot": (3, 4, 0)}, "neck": {"rot": (-6, -8, 0)},
                             "head": {"rot": (-6, -6, 0)}},
                            arm_dirs("R", (-15, 40), (-2, 72)),
                            arm_spec("L", (0.55, -0.42, 0.98), (0.95, 0.15, 1.3), back=(0.4, -0.3, 1.0), space="hero"), FISTS),
     True, True),
    ("deep_squat", L.merge(pelvis((0, 0.14, -0.44), (16, 0, 0)), feet((0.40, BALL[1]), yaw=14),
                           {"spine_01": {"rot": (8, 0, 0)}, "spine_02": {"rot": (6, 0, 0)}, "neck": {"rot": (-14, 0, 0)},
                            "head": {"rot": (-10, 0, 0)}},
                           arm_dirs("R", (-35, 35), (-20, 72)), arm_dirs("L", (-40, 40), (-10, 85), back=(0.4, -0.3, 1.0)), FISTS),
     True, True),
    ("lunge", L.merge(pelvis((0, -0.12, -0.25), (4, -6, 0)), feet((0.30, -0.75), (-0.36, 0.40), yaw=4, yaw_r=-10, heel_r=12),
                      {"spine_01": {"rot": (4, 14, 0)}, "spine_02": {"rot": (2, 6, 0)}, "neck": {"rot": (0, -10, 0)},
                       "head": {"rot": (0, -6, 0)}},
                      arm_dirs("R", (-18, 38), (-8, 70)), arm_dirs("L", (-65, -10), (0, 80), back=(0.6, 0.0, 1.0)), FISTS),
     True, True),
    ("torso_twist", L.merge(STANCE, {"spine_01": {"rot": (0, 24, 0)}, "spine_02": {"rot": (0, 10, 0)},
                                     "spine_03": {"rot": (0, 6, 0)}, "neck": {"rot": (0, -12, 0)}},
                            arm_dirs("R", (-18, 38), (-8, 70)), LOW_FIST, FISTS), True, False),
    ("head_left_down", L.merge(APOSE, {"neck": {"rot": (4, 10, 0)}, "head": {"rot": (6, 15, 3)}}, FISTS), True, False),
    ("head_right_up", L.merge(APOSE, {"neck": {"rot": (-6, -10, 0)}, "head": {"rot": (-10, -15, -3)}}, FISTS), True, False),
    ("bulwark_raise", L.merge(pelvis((0, 0, -0.06)), {"spine_01": {"rot": (-4, 0, 0)}, "spine_02": {"rot": (-3, 0, 0)},
                                                     "neck": {"rot": (-6, 0, 0)}},
                              arm_dirs("L", (15, 70), (30, 100), back=(0.2, 0.6, 0.4)), arm_dirs("R", (15, 70), (30, 100)), FISTS),
     True, True),
    ("forearm_twist", L.merge(STANCE, AIM, arm_dirs("L", (-10, 40), (0, 80), twist=-100), FISTS), True, False),
    ("elbow_knee_max", L.merge({"upperarm_L": {"rot": (30, 0, -65)}, "lowerarm_L": {"rot": (145, 0, 0)},
                                "upperarm_R": {"rot": (30, 0, 65)}, "lowerarm_R": {"rot": (145, 0, 0)},
                                "thigh_L": {"rot": (112, 0, 8)}, "shin_L": {"rot": (-135, 0, 0)}, "foot_L": {"rot": (-10, 0, 0)}},
                               FISTS), False, False),
]
if ONLY:
    POSES = [p for p in POSES if p[0] in ONLY or p[0] == "bind"]


def apply(pose):
    """Solve a pose dict with the stage-4 solver and write it to the armature (cloth chains back to rest)."""
    local, _M, info = SOL.solve(L.expand_pose(pose))
    for pb in arm.pose.bones:
        if pb.name == "x_fauld_01":
            continue                      # driven (rotation_euler.x)
        q, t = local.get(pb.name, (L.IDQ, Vector()))
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = q.to_euler("XYZ")
        pb.location = t if pb.name == "pelvis" else Vector()
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    return info


def set_helpers(on, only=None):
    """Mute (on=False) the driven helpers, all of them or those whose name starts with `only` (e.g. "x_knee")."""
    for n in HELPERS:
        if only and not n.startswith(only):
            continue
        for c in arm.pose.bones[n].constraints:
            c.mute = not on
    fc = arm.animation_data.drivers.find('pose.bones["x_fauld_01"].rotation_euler', index=0) if arm.animation_data else None
    if fc is not None and (not only or only == "x_fauld"):
        fc.mute = not on
        if not on:
            arm.pose.bones["x_fauld_01"].rotation_euler[0] = 0.0
    bpy.context.view_layer.update()


# ---- cloth groups --------------------------------------------------------------------------------------------------------
def chains(prefix, names, n):
    return [["%s%s_%02d" % (prefix, nm, i + 1) for i in range(n)] for nm in names]


def group_mask(ob, prefix):
    names = {g.index: g.name for g in ob.vertex_groups}
    return np.array([any(names[g.group].startswith(prefix) for g in v.groups) for v in ob.data.vertices])


rig_cfg = SKIN["rig"]
cape_ob, loin_ob, beard_ob = parts["CAPE"], parts["LOINCLOTH"], parts["BEARD"]
GROUPS = {
    "cape": ClothGroup(arm, cape_ob, chains("x_cape_", rig_cfg["cape"]["names"], len(rig_cfg["cape"]["joints_z"]) - 1),
                       vmask=group_mask(cape_ob, "x_cape"), gravity=0.55, margin=0.012, ground=0.0),
    "loin": ClothGroup(arm, loin_ob, chains("x_loin_", rig_cfg["loin"]["names"], len(rig_cfg["loin"]["joints_z"]) - 1),
                       gravity=0.7, margin=0.008, ground=0.0, max_turn_deg=45.0),
    "braids": ClothGroup(arm, beard_ob, chains("x_beard_", [str(k) for k in range(1, 6)], 2), vmask=group_mask(beard_ob, "x_beard"),
                         gravity=0.5, margin=0.006, ground=0.0, iters=40, step_deg=12.0, max_turn_deg=80.0, gravity_ramp=0),
}
OBST = {"cape": Pieces([o for o in solid_objs if o.name != "BEARD"]),
        "loin": Pieces([o for o in solid_objs if o.name in ("BODY", "LEGS", "HIPS", "SABATONS")]),
        "braids": Pieces([o for o in solid_objs if o.name in ("BODY", "ANVIL", "CUIRASS", "PAULDRONS", "ARMS", "GAUNTLETS")])}


def cloth_pose(co_by):
    out = {}
    for g, grp in GROUPS.items():
        out[g] = grp.solve(OBST[g].build(co_by))
    bpy.context.view_layer.update()
    return out


def cloth_check(co_by):
    """Cloth vertices inside a solid piece (> 3 mm, the same parity test as the plates) or under the ground."""
    out = {}
    for g, grp in GROUPS.items():
        built = OBST[g].build(co_by)
        q = co_by[grp.ob.name][grp.vidx]
        hit = np.zeros(len(q), bool)
        by = {}
        for lo, hi, bvh, lab in built:
            for i in np.nonzero(np.all((q > lo + 0.003) & (q < hi - 0.003), axis=1) & ~hit)[0]:
                if inside(bvh, Vector(q[i])):
                    hit[i] = True
                    by[lab.split(":")[0]] = by.get(lab.split(":")[0], 0) + 1
        out[g] = {"inside_gt3mm": int(hit.sum()), "under_ground": int((q[:, 2] < -0.003).sum()), "inside_by_part": by}
    return out


# ---- rest references -------------------------------------------------------------------------------------------------------
apply({})
CO_REST = CK.posed()
CK.set_rest_reference(CO_REST)
report["cloth_at_rest"] = cloth_check(CO_REST)
if cannon is not None:
    apply(FISTS)
    CK.set_cannon_reference(CK.posed())
    report["cannon_reference"] = {"right_arm_vertices_in_sleeve_with_fist": len(CK.cov_ref), "cuts_at_rest": CK.cut_ref}
    apply({})
log("rest: cloth %s" % report["cloth_at_rest"])


# ---- rendering ---------------------------------------------------------------------------------------------------------------
render_objs = [body] + list(parts.values()) + ([cannon] if cannon else [])
TOON, ORIG = {}, {}
for o in render_objs:
    M = o.material_slots[0].material if o.material_slots else None
    if M is None:
        continue
    if M.name not in TOON:
        TOON[M.name] = make_toon_cycles(M)
    ORIG[o.name] = [s.material for s in o.material_slots]
    for s in o.material_slots:
        s.link = "OBJECT"
floor = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
floor.data.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new("ground")
fm.use_nodes = True
for n in list(fm.node_tree.nodes):
    fm.node_tree.nodes.remove(n)
em = fm.node_tree.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.075, 0.032, 0.018, 1)
fm.node_tree.links.new(em.outputs[0], fm.node_tree.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
floor.data.materials.append(fm)
scene.collection.objects.link(floor)
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1)
H = 2.33


for o in render_objs:                    # toon copies of every slot material (the cannon has one)
    for m in ORIG.get(o.name, []):
        if m.name not in TOON:
            TOON[m.name] = make_toon_cycles(m)


def use_mat(kind):
    for o in render_objs:
        for s, m in zip(o.material_slots, ORIG.get(o.name, [])):
            s.material = TOON[m.name] if kind == "toon" else m


def clay():
    for o in render_objs:
        o.color = (0.30, 0.37, 0.55, 1) if o is cannon else ((0.76, 0.67, 0.60, 1) if o is body else (
            (0.62, 0.30, 0.26, 1) if o.name in ("CAPE", "LOINCLOTH") else (0.55, 0.52, 0.50, 1)))


def render_pose(i, name, show_cannon):
    tag = "pose_%02d_%s" % (i, name)
    if cannon:
        cannon.hide_render = not show_cannon
    use_mat("toon")
    cycles_cpu(scene, samples=6)
    floor.hide_render = True
    for view, az in (("full", 32), ("back", 150)):
        aim_ortho(scene, (0, 0.0, H * 0.5), az_dir(az, 8), H * 1.55)
        render_still(scene, os.path.join(OUT, "%s_%s.png" % (tag, view)), 560, 640)
        if QUICK:
            break
    if QUICK:
        return
    floor.hide_render = False
    pitch = math.radians(55.0)
    for yaw in (0, 35):
        d = Vector((math.sin(math.radians(yaw)) * math.cos(pitch), -math.cos(math.radians(yaw)) * math.cos(pitch), math.sin(pitch)))
        aim_ortho(scene, (0, 0, H * 0.45), d, 22.0 * 176 / 1080.0)
        render_still(scene, os.path.join(OUT, "%s_ingame%d.png" % (tag, yaw)), 176)
    floor.hide_render = True
    use_mat("orig")
    setup_workbench(scene, "OBJECT", cavity=True, bg=(0.16, 0.16, 0.18))
    clay()
    pb = arm.pose.bones
    sh = pb["upperarm_L"].head
    el = pb["lowerarm_L"].head
    kn = pb["shin_L"].head
    hd = pb["head"].head
    pel = pb["pelvis"].head
    shots = {"shoulder_front": (sh + Vector((-0.15, -0.1, 0.1)), az_dir(28, 18), 1.3),
             "shoulder_back": (sh + Vector((-0.15, 0.1, 0.1)), az_dir(155, 25), 1.3),
             "elbow": (el, az_dir(40, 25), 1.0),
             "knee": (kn, az_dir(55, 12), 1.1),
             "hips": (pel + Vector((0.0, -0.1, -0.15)), az_dir(20, 10), 1.25),
             "head": (hd + Vector((0.0, -0.08, -0.15)), az_dir(25, 10), 0.95),
             "cape": (pel + Vector((0.0, 0.2, -0.25)), az_dir(160, 10), 2.6)}
    if cannon is not None and show_cannon:
        g = R.grip_matrix(arm, "weapon_R")
        shots["cannon"] = (g.translation + g.to_3x3().col[1] * 0.1, az_dir(-60, 25), 1.6)
    for k, (tgt, d, sc) in shots.items():
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "%s_%s.png" % (tag, k)), 420)


# ---- run ---------------------------------------------------------------------------------------------------------------------
SNAP = []
for i, (name, pose, show_cannon, helpers_off) in enumerate(POSES, start=1):
    t = time.time()
    info = apply(pose)
    cl = cloth_pose(CK.posed())
    co = CK.posed()
    raw = CK.plates_raw(co)
    r = {"solver": {k: (round(v, 3) if isinstance(v, float) else bool(v)) for k, v in info.items()
                    if not k.startswith(("target", "twist"))},
         "body": CK.body_check(co["BODY"]), "plates": CK.plates(co, raw), "cloth_solve": cl, "cloth": cloth_check(co)}
    if cannon is not None and show_cannon:
        r["cannon"] = CK.cannon_check(co)
        # the cannon's off-hand brace handle (its grip_L socket, in the grip frame): can the left fist reach it?
        gl = Vector(ast.literal_eval(cannon["gf_weapon_sockets"])["grip_L"]["origin"])
        p_gl = R.grip_matrix(arm, "weapon_R") @ gl
        sh_l = arm.matrix_world @ arm.pose.bones["upperarm_L"].head
        r["cannon"]["grip_L_from_left_shoulder_m"] = round((p_gl - sh_l).length, 3)
        r["cannon"]["left_arm_reach_m"] = round(RIG.b["upperarm_L"].length + RIG.fist_eff["L"].length, 3)
    if helpers_off:
        set_helpers(False)
        r["helpers_off"] = {"plates": CK.plates(CK.posed()), "one_muted": {}}
        set_helpers(True)
        for h in ("x_pauldron", "x_elbow", "x_knee", "x_tasset", "x_fauld"):
            set_helpers(False, h)
            m = CK.plates(CK.posed())
            r["helpers_off"]["one_muted"][h] = {"clipping": m["clipping"], "sliding": m["sliding"], "suit": m["suit"]}
            set_helpers(True, h)
    SNAP.append({pb.name: (pb.rotation_euler.copy(), pb.location.copy()) for pb in arm.pose.bones})
    report["poses"][name] = r
    pl = r["plates"]
    log("%-15s clip %4d slide %4d suit %4d | cloth %s | cannon %s | suit collapse %d sh %s%s" % (
        name, pl["clipping"], pl["sliding"], pl["suit"], {k: (v["inside_gt3mm"], v["under_ground"]) for k, v in r["cloth"].items()},
        (r["cannon"]["poke_through"], r["cannon"]["cuts"]) if "cannon" in r else "-",
        r["body"]["collapsed_verts_area_lt_0_4"], r["body"]["collapsed_shoulder_L_R"],
        ("  | helpers off: clip %d slide %d" % (r["helpers_off"]["plates"]["clipping"], r["helpers_off"]["plates"]["sliding"])) if helpers_off else ""))
    log("    clip:", pl["clipping_worst"][:4], " suit:", pl["suit_worst"][:3], " cannon:", r.get("cannon", {}).get("cuts_by_piece", ""))
    if RENDER:
        render_pose(i, name, show_cannon)
    r["seconds"] = round(time.time() - t, 1)

# ---- skeleton, weights and the sleeve section (for the sheets) --------------------------------------------------------------
if RENDER and ONLY is None and not QUICK:
    apply({})
    bpy.context.view_layer.update()
    if cannon:
        cannon.hide_render = True
    mk = []

    def marker(p, rad, col):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=rad, location=p, segments=10, ring_count=6)
        o = bpy.context.active_object
        o.color = col
        mk.append(o)

    def stick(a, b, rad, col):
        dv = b - a
        bpy.ops.mesh.primitive_cylinder_add(radius=rad, depth=max(dv.length, 1e-4), location=(a + b) * 0.5, vertices=8)
        o = bpy.context.active_object
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = dv.to_track_quat("Z", "Y")
        o.color = col
        mk.append(o)

    COL = {"core": (1.0, 0.15, 0.1, 1), "twist": (1.0, 0.35, 1.0, 1), "finger": (0.2, 0.95, 0.3, 1), "root": (0.2, 0.9, 1.0, 1),
           "helper": (1.0, 0.6, 0.05, 1), "cloth": (0.45, 0.45, 1.0, 1), "braid": (0.75, 1.0, 0.2, 1)}
    for b in arm.data.bones:
        n = b.name
        if n in R.SOCKET_NAMES:
            continue
        k = ("twist" if "twist" in n else "finger" if n.split("_")[0] in R.FINGERS else "root" if n == "root" else
             "helper" if n.startswith(("x_pauldron", "x_elbow", "x_knee", "x_tasset", "x_fauld")) else
             "braid" if n.startswith("x_beard") else "cloth" if n.startswith(("x_cape", "x_loin")) else "core")
        small = k in ("finger", "braid")
        a, c = b.head_local.copy(), b.tail_local.copy()
        marker(a, 0.006 if small else 0.02, COL[k])
        stick(a, c, 0.003 if small else (0.008 if k in ("twist", "cloth") else 0.011), COL[k])
    for sname in R.SOCKET_NAMES:
        G = R.grip_matrix(arm, sname, pose=False)
        o = G.translation
        marker(o, 0.012, (1, 0.85, 0.1, 1))
        for kk, col in ((0, (0.95, 0.1, 0.1, 1)), (1, (0.1, 0.85, 0.1, 1)), (2, (0.15, 0.35, 1.0, 1))):
            stick(o, o + G.to_3x3().col[kk].normalized() * 0.14, 0.004, col)
    for o in mk:
        o.show_in_front = True
    setup_workbench(scene, "OBJECT", bg=(0.16, 0.16, 0.18))
    use_mat("orig")
    for o in render_objs:
        o.color = (0.72, 0.66, 0.62, 1)
    # two passes per view, composited by the sheets script: the body alone, then the bones alone on a transparent film
    # (a Workbench render has no "in front", and x-ray would fade the bones with the body)
    for view, dd, tgt, sc, res in (("front", az_dir(0, 2), (0, 0, H * 0.5), H * 1.2, (820, 900)),
                                   ("back", az_dir(180, 2), (0, 0, H * 0.5), H * 1.2, (820, 900)),
                                   ("side", az_dir(90, 2), (0, 0.05, H * 0.5), H * 1.05, (700, 900)),
                                   ("head", az_dir(30, 8), (0.0, -0.15, 2.02), 0.75, (700, 700)),
                                   ("hand", (0.25, -0.35, 1.0), tuple(V("hand_L_tip") + Vector((-0.03, 0, 0))), 0.42, (700, 700))):
        aim_ortho(scene, tgt, dd, sc)
        for o in mk:
            o.hide_render = True
        render_still(scene, os.path.join(OUT, "skeleton_%s_body.png" % view), *res)
        for o in mk:
            o.hide_render = False
        for o in render_objs:
            o.hide_render = True
        scene.render.film_transparent = True
        render_still(scene, os.path.join(OUT, "skeleton_%s_bones.png" % view), *res)
        scene.render.film_transparent = False
        for o in render_objs:
            o.hide_render = False
        if cannon:
            cannon.hide_render = True
    for o in mk:
        me_ = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me_)
    # dominant bone per vertex, every skinned part (a rigid plate shows as one flat colour)
    rng = np.random.default_rng(11)
    pal = {b.name: tuple(rng.uniform(0.2, 1.0, 3)) + (1.0,) for b in arm.data.bones}
    cas = []
    for o in [body] + list(parts.values()):
        gn = {g.index: g.name for g in o.vertex_groups}
        cols = []
        for v in o.data.vertices:
            gs = max(((g.weight, gn[g.group]) for g in v.groups), default=(0, "root"))
            cols.append(pal[gs[1]])
        ca = o.data.color_attributes.new("dominant_bone", "BYTE_COLOR", "POINT")
        ca.data.foreach_set("color", np.array(cols, dtype=np.float32).ravel())
        o.data.color_attributes.active_color = ca
        cas.append((o, ca))
    setup_workbench(scene, "VERTEX", bg=(0.16, 0.16, 0.18), light="FLAT")
    for view, az in (("front", 0), ("back", 180), ("side", 90)):
        aim_ortho(scene, (0, 0, H * 0.5), az_dir(az, 3), H * 1.2)
        render_still(scene, os.path.join(OUT, "weights_dominant_%s.png" % view), 700, 760)
    setup_workbench(scene, "VERTEX", bg=(0.16, 0.16, 0.18), light="STUDIO")
    for view, tgt, dd, sc in (("shoulder", tuple(V("shoulder_L") + Vector((-0.05, 0, 0.15))), az_dir(35, 25), 0.95),
                              ("hand", tuple(V("hand_L_tip")), (0.2, -0.3, 1.0), 0.42),
                              ("cape", (0.0, 0.3, 1.2), az_dir(180, 5), 2.2)):
        aim_ortho(scene, tgt, dd, sc)
        render_still(scene, os.path.join(OUT, "weights_dominant_%s.png" % view), 600, 600)
    for o, ca in cas:
        o.data.color_attributes.remove(ca)
    # the sleeve section: the cannon and the right arm cut along the barrel axis (the camera's near plane on the axis)
    if cannon:
        cannon.hide_render = False
        setup_workbench(scene, "OBJECT", cavity=False, bg=(0.16, 0.16, 0.18))
        clay()
        for sname, spose in (("rest_fist", FISTS), ("cannon_aim", POSES[[p[0] for p in POSES].index("cannon_aim")][1])):
            apply(spose)
            G = R.grip_matrix(arm, "weapon_R")
            g3 = G.to_3x3().normalized()
            up = g3.col[2]
            cam = aim_ortho(scene, G.translation + g3.col[1] * 0.12, tuple(up), 1.45, dist=10.0)
            # the barrel (grip Y) left to right in the image: camera X = grip Y, camera Y = -grip X, looking down grip Z
            from mathutils import Matrix as _M
            cam.rotation_quaternion = _M((tuple(g3.col[1]), tuple(-g3.col[0]), tuple(up))).transposed().to_quaternion()
            cam.data.clip_start = 10.0
            render_still(scene, os.path.join(OUT, "sleeve_section_%s.png" % sname), 900, 560)
            cam.data.clip_start = 0.01
        apply({})
    for o in render_objs:
        o.color = (1, 1, 1, 1)

# ---- save ----------------------------------------------------------------------------------------------------------------------
apply({})
if ONLY is None and not QUICK:
    use_mat("orig")
    for o in render_objs:
        for s in o.material_slots:
            s.link = "DATA"
    bpy.data.objects.remove(floor)
    act = new_action(arm, "GF_ValidationPoses", 1, len(POSES))
    for i, snap in enumerate(SNAP, start=1):
        for pb in arm.pose.bones:
            pb.rotation_euler, pb.location = snap[pb.name]
        for pb in arm.pose.bones:
            if pb.name != "x_fauld_01":
                pb.keyframe_insert("rotation_euler", frame=i)
            pb.keyframe_insert("location", frame=i)
        act.pose_markers.new(POSES[i - 1][0]).frame = i
    for fc in fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    push_to_nla(arm, act, "GF_ValidationPoses")
    arm.animation_data.action = None
    apply({})
    if cannon:
        cannon.hide_render = False
    scene.frame_set(1)
    save_blend(P["rig"])
    report["seconds"] = round(time.time() - T0, 1)
    write_json(os.path.join(P["S3"], "poses.json"), report)
else:
    write_json(os.path.join(P["W"], "poses_partial.json"), report)
