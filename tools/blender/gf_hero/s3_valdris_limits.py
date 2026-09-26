"""Stage 3, Valdris: range-of-motion sweeps of the rig, with and without the driven helpers (headless Blender).

  blender -b -P tools/blender/gf_hero/s3_valdris_limits.py -- [--only <sweep,...>] [--follows 0,0.5,...] [--pivot x,y,z]

(--follows: the pauldron follow factors of the shoulder sweep; --pivot: try another pauldron hinge for this run only,
nothing is saved. A run with --only writes work/limits_partial.json instead of the report.)

Rigid armour this massive limits how far each joint can turn before one plate cuts another, so the numbers that decide
the helpers' follow factors and the animation ranges (stage 4) are measured here, one joint at a time, from the rest
pose (s3_valdris_check.py counts new vertices of one piece inside another; "clipping" = pieces of different regions):

  shoulder   the left upper arm aimed over a grid of elevation (-75..+75 deg) x azimuth (0 = out to the side, 45, 80 =
             forward); pauldron follow 0 / 0.3 / 0.45 / 0.6 / 0.8. Counts: clipping that involves the pauldron stack or
             the head, the arm into the torso / anvil
  elbow      left elbow flexion 0..150 with the upper arm down 45 and forward 30; x_elbow at 0 (couter rigid on the
             forearm) or 0.5 (half the bend). Right arm the same with the colossus_cannon: its cuts and poke-through
  knee       knee flexion 0..135 (thigh still); x_knee 0 / 0.5
  ankle      foot flexion -30..+40 relative to the shin (the sabaton's cuff and instep lame ride the shin; stage3_skin.json
             _doc_sabaton has the three assignments this sweep compared)
  hip        thigh flexion 0..110 (the knee bending with it), torso upright or leaning 12 deg; tasset follow 0 / 0.25 / 0.4
             / 0.65, the fauld driver on / off
  head       neck + head yaw 0..60 and yaw 30 with a 20 deg nod: the beard, braids and head against the pauldrons
             and the anvil (braids at rest on the head, no cloth solve)
  twist      torso twist 0..60 (spine_01..03 each a third)
  cannon     the right elbow flexion 0..120 with the cannon arm aimed forward (upper arm out 30, down 20): cuts, pokes

Output: reports/stage3/limits.json (every sample) and a summary of the clean ranges.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import log, read_json, script_args, write_json  # noqa: E402
from s3lib import aim_bone, hero_paths  # noqa: E402
from s3_valdris_check import Checker, piece_table_path  # noqa: E402

KEY = "valdris"
argv = script_args(__doc__)
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
bpy.ops.wm.open_mainfile(filepath=P["rig"])
arm = bpy.data.objects[R.RIG_NAME]
if arm.animation_data:
    arm.animation_data.action = None
cannon = bpy.data.objects.get("PREVIEW_colossus_cannon_R")
if "--pivot" in argv:                   # try another pauldron hinge (edit-mode move of both helpers; nothing is saved)
    px, py, pz = (float(v) for v in argv[argv.index("--pivot") + 1].split(","))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for s_, sx in (("L", 1.0), ("R", -1.0)):
        eb = arm.data.edit_bones["x_pauldron_" + s_]
        d = eb.tail - eb.head
        eb.head = Vector((sx * px, py, pz))
        eb.tail = eb.head + d
    bpy.ops.object.mode_set(mode="OBJECT")
CK = Checker(arm, piece_table_path(P), cannon)
T0 = time.time()


def reset():
    for pb in arm.pose.bones:
        if pb.name != "x_fauld_01":
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)


def fist():
    for s in ("L", "R"):
        for f in ("index", "middle", "ring", "pinky"):
            for i, a in ((1, 80), (2, 95), (3, 60)):
                arm.pose.bones["%s_%02d_%s" % (f, i, s)].rotation_euler = (math.radians(a), 0, 0)
        z = -30 if s == "L" else 30
        for i, rot in ((1, (40, 0, z)), (2, (45, 0, 0)), (3, (35, 0, 0))):
            arm.pose.bones["thumb_%02d_%s" % (i, s)].rotation_euler = Euler([math.radians(v) for v in rot])


def influence(helper, value):
    """Set a helper's follow factor: a Copy Rotation's influence, a Transformation's output range, or the fauld driver."""
    for n in (helper + "_L", helper + "_R") if helper != "x_fauld_01" else ():
        for c in arm.pose.bones[n].constraints:
            if c.type == "TRANSFORM":
                lim = math.radians(150.0)
                if n.endswith("_L"):
                    c.to_min_z_rot, c.to_max_z_rot = 0.0, lim * value
                else:
                    c.to_min_z_rot, c.to_max_z_rot = -lim * value, 0.0
            else:
                c.influence = value
    if helper == "x_fauld_01":
        fc = arm.animation_data.drivers.find('pose.bones["x_fauld_01"].rotation_euler', index=0)
        fc.mute = value <= 0
        if value <= 0:
            arm.pose.bones["x_fauld_01"].rotation_euler[0] = 0.0


CFG = read_json(P["skin_cfg"])["rig"]["helpers"]
DEFAULT = {"x_pauldron": CFG["pauldron"]["follow"], "x_knee": CFG["knee"]["follow"], "x_tasset": CFG["tasset"]["follow"]}


def restore():
    for h, v in DEFAULT.items():
        influence(h, v)
    for s in ("L", "R"):
        for c in arm.pose.bones["x_elbow_" + s].constraints:
            c.influence = CFG["elbow"].get("follow_" + s, CFG["elbow"]["follow"])
    influence("x_fauld_01", 1.0)


reset()
bpy.context.view_layer.update()
CK.set_rest_reference(CK.posed())
reset()
fist()
bpy.context.view_layer.update()
CK.set_cannon_reference(CK.posed())


def measure(filter_fn=None):
    bpy.context.view_layer.update()
    co = CK.posed()
    raw = CK.plates_raw(co)
    out = {"clipping": 0, "sliding": 0, "suit": 0}
    worst = {"clipping": {}, "sliding": {}, "suit": {}}
    for na, nb, k, n, ra, rb in raw:
        if filter_fn is not None and not filter_fn(na, nb, k, ra, rb):
            continue
        out[k] += n
        key = "%s -> %s" % (na, nb)
        worst[k][key] = worst[k].get(key, 0) + n
    for k in worst:
        out[k + "_worst"] = sorted(worst[k].items(), key=lambda kv: -kv[1])[:3]
    return out, co


def arm_dir(el, az, side="L"):
    """Upper-arm world direction: elevation el above horizontal, azimuth az from out-to-the-side toward the front."""
    sx = 1.0 if side == "L" else -1.0
    e, a = math.radians(el), math.radians(az)
    return (sx * math.cos(e) * math.cos(a), -math.cos(e) * math.sin(a), math.sin(e))


report = {"hero": KEY, "sweeps": {}}
sweeps = report["sweeps"]


def left_or_head(na, nb, k, ra, rb):
    return ra in ("shoulder_L", "arm_L", "hand_L") or rb in ("shoulder_L", "arm_L", "hand_L")


# ---- shoulder --------------------------------------------------------------------------------------------------------------
if ONLY is None or "shoulder" in ONLY:
    rows = []
    follows = [float(v) for v in argv[argv.index("--follows") + 1].split(",")] if "--follows" in argv else (0.0, 0.35, 0.5, 0.6, 0.8)
    for follow in follows:
        influence("x_pauldron", follow)
        for az in (0, 45, 80):
            for el in range(-75, 76, 15):
                reset()
                fist()
                aim_bone(arm, arm.pose.bones["upperarm_L"], arm_dir(el, az))
                m, _co = measure(left_or_head)
                rows.append({"follow": follow, "az": az, "el": el, **m})
        log("shoulder follow %.2f done" % follow)
    restore()
    sweeps["shoulder"] = rows

# ---- elbow -----------------------------------------------------------------------------------------------------------------
if ONLY is None or "elbow" in ONLY:
    rows = []
    for follow in (0.0, 0.5):
        influence("x_elbow", follow)
        for a in range(0, 151, 15):
            reset()
            fist()
            aim_bone(arm, arm.pose.bones["upperarm_L"], arm_dir(-45, 30))
            arm.pose.bones["lowerarm_L"].rotation_euler = (math.radians(a), 0, 0)
            m, _co = measure(left_or_head)
            rows.append({"follow": follow, "flex": a, **m})
    restore()
    sweeps["elbow"] = rows

# ---- cannon arm: elbow flexion with the cannon aimed --------------------------------------------------------------------------
if cannon is not None and (ONLY is None or "cannon" in ONLY):
    rows = []
    for a in range(0, 121, 10):
        reset()
        fist()
        aim_bone(arm, arm.pose.bones["upperarm_R"], arm_dir(-20, 30, "R"))
        arm.pose.bones["lowerarm_R"].rotation_euler = (math.radians(a), 0, 0)
        m, co = measure(lambda na, nb, k, ra, rb: "R" in ra[-1:] + rb[-1:])
        c = CK.cannon_check(co)
        rows.append({"flex": a, **m, "cannon_cuts": c["cuts"], "cannon_poke": c["poke_through"], "cuts_by_piece": c["cuts_by_piece"][:4]})
    for tw in range(-90, 91, 30):
        reset()
        fist()
        aim_bone(arm, arm.pose.bones["upperarm_R"], arm_dir(-20, 30, "R"))
        arm.pose.bones["lowerarm_R"].rotation_euler = (math.radians(20), 0, 0)
        arm.pose.bones["hand_R"].rotation_euler = (0, math.radians(tw), 0)
        m, co = measure(lambda na, nb, k, ra, rb: "R" in ra[-1:] + rb[-1:])
        c = CK.cannon_check(co)
        rows.append({"hand_twist": tw, **m, "cannon_cuts": c["cuts"], "cannon_poke": c["poke_through"], "cuts_by_piece": c["cuts_by_piece"][:4]})
    sweeps["cannon"] = rows

# ---- knee -------------------------------------------------------------------------------------------------------------------
if ONLY is None or "knee" in ONLY:
    rows = []
    for follow in (0.0, 0.5):
        influence("x_knee", follow)
        for a in range(0, 136, 15):
            reset()
            arm.pose.bones["shin_L"].rotation_euler = (math.radians(-a), 0, 0)
            m, _co = measure(lambda na, nb, k, ra, rb: ra in ("leg_L", "foot_L") or rb in ("leg_L", "foot_L"))
            rows.append({"follow": follow, "flex": a, **m})
    restore()
    sweeps["knee"] = rows

# ---- ankle ------------------------------------------------------------------------------------------------------------------
if ONLY is None or "ankle" in ONLY:
    rows = []
    for a in range(-30, 41, 10):                       # + = toes up relative to the shin (the shin tilting over a planted foot)
        reset()
        arm.pose.bones["foot_L"].rotation_euler = (math.radians(a), 0, 0)
        m, _co = measure(lambda na, nb, k, ra, rb: ra in ("leg_L", "foot_L") or rb in ("leg_L", "foot_L"))
        rows.append({"dorsiflex": a, **m})
    sweeps["ankle"] = rows

# ---- hip ---------------------------------------------------------------------------------------------------------------------
if ONLY is None or "hip" in ONLY:
    rows = []
    for follow in (0.0, 0.25, 0.5, 0.65):
        influence("x_tasset", follow)
        for fauld in (0.0, 1.0):
            influence("x_fauld_01", fauld)
            for lean in (0, 12):                       # the torso upright, or leaning 12 deg (a brace): the anvil comes down
                for a in range(0, 111, 15):
                    reset()
                    arm.pose.bones["spine_01"].rotation_euler = (math.radians(lean), 0, 0)
                    arm.pose.bones["thigh_L"].rotation_euler = (math.radians(a), 0, 0)
                    arm.pose.bones["shin_L"].rotation_euler = (math.radians(-min(a, 90)), 0, 0)
                    m, _co = measure(lambda na, nb, k, ra, rb: ra in ("leg_L", "hips") or rb in ("leg_L", "hips"))
                    rows.append({"follow": follow, "fauld": fauld, "lean": lean, "flex": a, **m})
    restore()
    sweeps["hip"] = rows

# ---- head -------------------------------------------------------------------------------------------------------------------
if ONLY is None or "head" in ONLY:
    rows = []
    for nod in (0, 20):
        for yaw in range(0, 61, 10):
            reset()
            arm.pose.bones["neck"].rotation_euler = (math.radians(0.4 * nod), math.radians(0.4 * yaw), 0)
            arm.pose.bones["head"].rotation_euler = (math.radians(0.6 * nod), math.radians(0.6 * yaw), 0)
            m, _co = measure(lambda na, nb, k, ra, rb: "beard" in (ra, rb) or (k == "suit" and ra.startswith(("shoulder", "torso"))))
            rows.append({"nod": nod, "yaw": yaw, **m})
    sweeps["head"] = rows

# ---- torso twist -------------------------------------------------------------------------------------------------------------
if ONLY is None or "twist" in ONLY:
    rows = []
    for tw in range(0, 61, 10):
        reset()
        for b in ("spine_01", "spine_02", "spine_03"):
            arm.pose.bones[b].rotation_euler = (0, math.radians(tw / 3.0), 0)
        m, _co = measure()
        rows.append({"twist": tw, **m})
    sweeps["twist"] = rows

reset()
bpy.context.view_layer.update()
report["seconds"] = round(time.time() - T0, 1)
out = os.path.join(P["S3"], "limits.json") if ONLY is None else os.path.join(P["W"], "limits_partial.json")
write_json(out, report)
