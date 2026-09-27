"""Stage 4, Selene: key-frame renders of every clip for the one stage-4 review board, and the two-hand grip audit.

  blender -b -P tools/blender/gf_hero/s4_selene_render.py

Opens production/selene_anim.blend (never saved here): for each clip (reports/anim/clips.json order) four frames - the
first, the event / key frames in between and the last (a loop's middle instead of its seam) - rendered with the Cycles
CPU emission toon (selene_render.make_toon, s2_selene_review's look), front three-quarter from her right, one fixed
scale so sizes compare, the thundercoil_launcher preview on weapon_R. Every frame of every clip is also read for the
grip: the left palm (weapon_L) against the launcher's grip_L (from the posed weapon_R frame) - near zero wherever a clip
holds the foregrip, large where the left hand is free by design (ping, Arc Nova, carry, kit poses).
Also the stage-5 review shots (s5_selene.REVIEW_SHOTS) as work/renders/stage4/<clip>/f<NNN>_front.png, the
"stage 4 source" column of the shared s5_sheets.py. Outputs: work/renders/stage4/, reports/anim/render_checks.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import s5_selene as S5  # noqa: E402
import selene_render as SR  # noqa: E402
from s2lib import log, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

KEY = "selene"
P = hero_paths(KEY)
OUT = SR.ensure(os.path.join(P["W"], "renders", "stage4"))
MAN = json.load(open(os.path.join(P["A"], "reports", "anim", "clips.json"), encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=os.path.join(P["A"], "production", "%s_anim.blend" % KEY))
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm]
weapon = bpy.data.objects.get("PREVIEW_thundercoil_launcher")
SR.setup(scene, samples=6)
SR.toon_all(parts + ([weapon] if weapon else []))
S2G = Matrix(R.SOCKET_TO_GRIP)
GRIP_L = Vector((0.0, 0.441, 0.052))
for tr in arm.animation_data.nla_tracks:
    tr.mute = True


def pick(info):
    n = info["frames"]
    ks = sorted(set([0] + [int(k) for k in info.get("key_frames", [])] + list(info.get("events", {}).values()) + [n]))
    if info["loop"]:
        ks = [k for k in ks if k < n]
    if len(ks) <= 4:
        out = ks
    else:
        out = [ks[0], ks[len(ks) // 3], ks[(2 * len(ks)) // 3], ks[-1]]
    while len(out) < 4:
        out.append(n // 2 if n // 2 not in out else min(n, out[-1] + 1))
    return sorted(set(out))[:4]


checks = {"hero": KEY, "view": "front three-quarter from her right (az -30, el 12), ortho 2.6 m, 220 x 280 px",
          "renderer": "Cycles CPU emission toon", "clips": {}}
for clip in MAN["order"]:
    info = MAN["clips"][clip]
    act = bpy.data.actions[info["action"]]
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    errs = []
    for f in range(info["frames"] + 1):
        scene.frame_set(f)
        G = arm.matrix_world @ arm.pose.bones["weapon_R"].matrix @ S2G
        palm = arm.matrix_world @ arm.pose.bones["weapon_L"].matrix.translation
        errs.append((G @ GRIP_L - palm).length)
    frames = pick(info)
    for f in frames:
        scene.frame_set(f)
        SR.shoot(scene, os.path.join(OUT, "%s_f%02d.png" % (clip, f)), Vector((0.0, 0.0, 1.05)), SR.az_dir(-30.0, 12.0),
                 2.6, 220, 280)
    for rc, rf in S5.REVIEW_SHOTS:          # the stage-5 sheet's "stage 4 source" column: work/renders/stage4/<clip>/f<NNN>_front.png
        if rc.replace("@loop", "") == clip:
            scene.frame_set(rf)
            SR.shoot(scene, os.path.join(SR.ensure(os.path.join(OUT, clip)), "f%03d_front.png" % rf), Vector((0.0, 0.0, 1.05)),
                     SR.az_dir(-30.0, 12.0), 2.6, 380, 480)
    held = [e for e in errs if e < 0.05]
    checks["clips"][clip] = {"frames_rendered": frames, "grip_L_error_mm": {
        "min": round(1000 * min(errs), 1), "max": round(1000 * max(errs), 1),
        "frames_on_grip": len(held), "frames": len(errs)}}
    log("%-24s frames %s grip on %d/%d frames (min %.1f mm)" % (clip, frames, len(held), len(errs), 1000 * min(errs)))
arm.animation_data.action = None
write_json(os.path.join(P["A"], "reports", "anim", "render_checks.json"), checks)
