"""Stage 4, Selene: the cloth and crown pass - bake her cloth chains and crown shards into every clip (headless Blender).

  blender -b -P tools/blender/gf_hero/s4_selene_cloth.py -- [--only clip,clip]

Runs after s4_anim.py (which re-creates the actions without them). Her x_cape / x_mantle / x_panel / x_tabard / x_back
chains ride their parents rigidly unless something moves them, and the client has no cloth spring yet, so a clip without
them shows the capes like boards and the legs striding through the tabard. This pass is her secondary-motion layer (as
Valdris's s4_valdris_cloth.py is his): it keys ONLY the x_ cloth chains and the x_crown shards (the shared library never
keys an x_ bone, docs/art/GF_HERO_SKELETON.md section 2; an engine spring may later replace these channels).

Per clip (selene_cloth.solve_clip): each chain bone's hang direction (its rest direction turned with the body's heading,
blended with riding its parent), the forces of the clip's design travel and the pin's own motion and acceleration, a
first-order lag (cyclic for loops: the last frame is the first), then every frame the sheet's sample points pushed out of
capsules round her legs, arms, hips and torso and above the ground. Upper-layer one-shots start from and settle back into
idle_combat's frame-0 cloth state, so their first and last frames equal that reference pose for every bone. The crown
shards bob out of phase (selene_cloth.crown_angles); in Heaven's Verdict they lift and sway round the head.
Written as LINEAR keys on rotation_euler. Output: the actions in production/selene_anim.blend, reports/anim/cloth.json.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler, Matrix  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import selene_cloth as SCL  # noqa: E402
from s2lib import log, save_blend, script_args, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

KEY = "selene"
argv = script_args(__doc__)
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
BLEND = os.path.join(P["A"], "production", "%s_anim.blend" % KEY)
MAN_P = os.path.join(P["A"], "reports", "anim", "clips.json")
OUT_P = os.path.join(P["A"], "reports", "anim", "cloth.json")
FPS = 30
T0 = time.time()

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
MAN = json.load(open(MAN_P, encoding="utf-8"))
parts = {o.name: o for o in scene.objects if o.type == "MESH" and o.parent == arm}
cloth = SCL.SeleneCloth(arm, [parts[n] for n in ("CAPES", "MANTLES", "PANELS", "TABARD")])
CHAIN = cloth.bones
CROWN = SCL.CROWN
MINE = set(CHAIN) | set(CROWN)
READ = [b.name for b in arm.data.bones if b.name not in MINE]
for pb in arm.pose.bones:
    if pb.name in MINE:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)


def channelbag(act):
    for layer in act.layers:
        for strip in layer.strips:
            cb = strip.channelbag(act.slots[0])
            if cb is not None:
                return cb
    return None


def set_action(act):
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]


def sample(act, n):
    set_action(act)
    out = []
    for f in range(n):
        scene.frame_set(f)
        out.append({b: SCL.np_mat(arm.pose.bones[b].matrix) for b in READ})
    return out


def write(act, per_frame):
    """per_frame: [{bone: 3x3 local rotation}] -> LINEAR rotation_euler keys (Euler-compatible frame to frame)."""
    cb = channelbag(act)
    if cb is not None:
        for fc in list(cb.fcurves):
            if any(fc.data_path == 'pose.bones["%s"].rotation_euler' % b for b in per_frame[0]):
                cb.fcurves.remove(fc)
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    n = len(per_frame)
    for b in per_frame[0]:
        prev = None
        eul = []
        for fr in per_frame:
            e = Matrix(fr[b].tolist()).to_euler("XYZ", prev) if prev is not None else Matrix(fr[b].tolist()).to_euler("XYZ")
            eul.append(e)
            prev = e
        for i in range(3):
            fc = act.fcurve_ensure_for_datablock(arm, 'pose.bones["%s"].rotation_euler' % b, index=i, group_name=b)
            fc.keyframe_points.add(n)
            co = []
            for f in range(n):
                co += [float(f), eul[f][i]]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [lin] * n)
            fc.update()


def crown_mats(n, loop, verdict):
    ang = SCL.crown_angles(n, FPS, loop, verdict)
    out = []
    for row in ang:
        d = {}
        for k, b in enumerate(CROWN):
            bob, spin, orbit = row[k]
            d[b] = SCL.axis_angle((1.0, 0.0, 0.0), orbit) @ SCL.axis_angle((0.0, 1.0, 0.0), spin) @ SCL.axis_angle((0.0, 0.0, 1.0), bob)
        out.append(d)
    return out


order = list(MAN["order"])
order.remove("idle_combat")
order.insert(0, "idle_combat")          # its frame 0 is the reference cloth state of the upper-layer one-shots
report = {"hero": KEY, "method": "tools/blender/gf_hero/selene_cloth.py (hang + forces + lag + capsule clear)",
          "chains": {k: v for k, v in cloth.chains.items()}, "crown": CROWN, "groups": SCL.GROUPS, "clips": {}}
old = json.load(open(OUT_P, encoding="utf-8"))["clips"] if (ONLY and os.path.exists(OUT_P)) else {}
report["clips"].update(old)
REF = None
for clip in order:
    info = MAN["clips"][clip]
    if ONLY and clip not in ONLY and clip != "idle_combat":
        continue
    t = time.time()
    act = bpy.data.actions[info["action"]]
    n = info["frames"] + 1
    frames = sample(act, n)
    upper_oneshot = info["layer"] == "upper" and not info["loop"]
    ref = REF if upper_oneshot else None
    start_dirs = None
    if ref is not None:
        # the reference state's world directions at this clip's frame 0 (the same pose), for the lag's start
        M0 = dict(frames[0])
        start_dirs = {}
        for pre, bones in cloth.chains.items():
            dl = []
            for b in bones:
                Mb = M0[cloth.parent[b]] @ cloth.rel[b] @ SCL._h(ref[b])
                M0[b] = Mb
                dl.append(Mb[:3, 1] / np.linalg.norm(Mb[:3, 1]))
            start_dirs[pre] = dl
    res, st = SCL.solve_clip(cloth, frames, FPS, travel=tuple(info.get("travel_mps") or (0.0, 0.0)), loop=info["loop"],
                             start=ref, end=ref, start_dirs=start_dirs)
    if clip == "idle_combat":
        REF = dict(res[0])
    verdict = 0.0
    if clip == "heavens_verdict":
        verdict = 1.0
    elif clip == "heavens_verdict_start":
        verdict = [max(0.0, min(1.0, (f - 14) / 14.0)) for f in range(n)]
        verdict = [v * v * (3 - 2 * v) for v in verdict]
    cm = crown_mats(n, info["loop"], verdict)
    per = [dict(res[f], **cm[f]) for f in range(n)]
    if clip in (ONLY or {clip}) or ONLY is None:
        write(act, per)
    report["clips"][clip] = {"frames": n, "inside_bone_frames": st["inside_frames"],
                             "max_turn_per_frame_deg": round(st["max_turn_per_frame_deg"], 1),
                             "reference_start_end": "idle_combat frame 0" if upper_oneshot else None,
                             "crown_verdict": clip.startswith("heavens_verdict"), "seconds": round(time.time() - t, 2)}
    log("%-24s %3d f cloth inside %3d bone-frames, max turn %.1f deg/frame (%.1fs)" % (
        clip, n, st["inside_frames"], st["max_turn_per_frame_deg"], time.time() - t))
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.rotation_euler = (0.0, 0.0, 0.0)
    pb.location = (0.0, 0.0, 0.0)
scene.frame_set(0)
report["seconds"] = round(time.time() - T0, 1)
save_blend(BLEND)
write_json(OUT_P, report)
log("cloth pass done in %.0fs" % (time.time() - T0))
