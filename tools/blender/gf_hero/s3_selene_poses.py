"""Stage 3, Selene: the validation poses, posed by the stage-4 solver with her cloth hung clear, and their renders.

  blender -b -P tools/blender/gf_hero/s3_selene_poses.py

Opens production/selene_rig.blend (never saved here) and poses GF_Hero_v1 with s4lib's solver in Selene's vocabulary
(s4_selene.SV): the bind T-pose, the relaxed carry, the two-handed launcher hold (THE weapon check pose: the
thundercoil_launcher GLB rides weapon_R as the identity attach, the left palm is put on its grip_L), a firing lunge, a
deep crouch, the Heaven's Verdict arms-up, a run stride and a twist with a head turn. Each pose: the cloth chains hung and
cleared by selene_cloth.solve_static, the knee helpers evaluated by their constraints, a toon render (Cycles CPU emission,
front three-quarter from her right), and metrics: limb flexions, the grip error, the weapon attach error against
gf_hero_rig.grip_matrix, cloth bones left touching the body. Also the bind pose's bone lines projected for the sheet, a
close-up of the hold and the 55 deg client camera at true pixel size.
Outputs: work/renders/stage3/*.png, reports/stage3/poses.json.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import s4lib as L  # noqa: E402
import s4_selene as S  # noqa: E402
import selene_cloth as SCL  # noqa: E402
import selene_render as SR  # noqa: E402
from s2lib import log, read_json, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

KEY = "selene"
P = hero_paths(KEY)
OUT = SR.ensure(os.path.join(P["W"], "renders", "stage3"))
bpy.ops.wm.open_mainfile(filepath=P["rig"])
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
LM = read_json(P["landmarks"])
K = L.Kit(LM, 7.0)
rig = L.Rig(arm)
sol = L.Solver(rig, K)
v = S.SV(K)
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm]
weapon = bpy.data.objects.get("PREVIEW_thundercoil_launcher")
cloth = SCL.SeleneCloth(arm, [o for o in parts if o.name in ("CAPES", "MANTLES", "PANELS", "TABARD")])
PSI = -40.0
m = lambda *a: L.expand_pose(L.merge(*a))  # noqa: E731


def combat(dz=0.0, lean=6.0, psi=PSI, fl=(0.13, -0.24), fr=(0.15, 0.13)):
    return L.merge(v.pelvis((0.0, 0.02, -0.07 + dz), (lean, psi * 0.5, 0.0)), v.spine(6.0, psi * 0.5),
                   v.foot("L", fl, 12.0), v.foot("R", fr, 34.0), v.head(neck=(-4.0, 0.0, 0.0)))


POSES = [
    ("bind", "the rest T-pose (the skeleton)", {}),
    ("relaxed", "relaxed carry: the launcher low in the right hand, the left hand free",
     m(v.pelvis((0.0, 0.0, -0.015), (2.0, -4.0, 2.0)), v.spine(2.0, 3.0), v.foot("L", (0.11, -0.13), 10.0),
       v.foot("R", (0.12, -0.08), 18.0), v.head(), v.carry(), v.free_l(), v.clav((0.0, 0.0, -4.0)))),
    ("hold", "the two-handed launcher hold (weapon check: the GLB on weapon_R, the left palm on grip_L)",
     m(combat(), v.free_l(), v.hold(PSI))),
    ("lunge_fire", "a firing lunge: the lead knee over the toes, the torso driven forward",
     m(combat(dz=-0.22, lean=16.0, fl=(0.15, -0.52), fr=(0.16, 0.34)), v.spine(12.0, PSI * 0.5), v.free_l(),
       v.hold(PSI, dfore=(20.0, 0.0)))),
    ("crouch", "a deep crouch, the hold kept",
     m(combat(dz=-0.46, lean=24.0, fl=(0.2, -0.2), fr=(0.2, 0.18)), v.spine(18.0, PSI * 0.5), v.free_l(),
       v.hold(PSI, dfore=(36.0, 0.0)))),
    ("verdict", "Heaven's Verdict: both arms raised, the head back, on her toes",
     m(v.pelvis((0.0, 0.03, 0.02), (-6.0, 0.0, 0.0)), v.spine(-10.0), v.foot("L", (0.12, -0.08), 8.0, heel=18.0),
       v.foot("R", (0.12, -0.08), 8.0, heel=18.0), v.head(-18.0), v.clav((0.0, 0.0, 14.0)),
       v.arm("R", (62.0, 30.0), (84.0, 60.0), back=(0.0, -1.0, 0.0)), v.arm("L", (60.0, 25.0), (75.0, 40.0), back=(0.0, -1.0, 0.0)),
       {"fingers_R": S.GRIP_CURL_R, "fingers_L": 0.05})),
    ("run_stride", "a run stride: the lead thigh high, the rear leg driving, the hold kept",
     m(v.pelvis((0.0, 0.02, -0.06), (14.0, PSI * 0.5, 0.0)), v.spine(10.0, PSI * 0.5), v.head(),
       v.foot("L", (0.1, -0.42), 6.0, lift=0.34, heel=10.0), v.foot("R", (0.1, 0.36), 6.0, heel=55.0),
       v.free_l(), v.hold(PSI))),
    ("twist_look", "the chest twisted left, the head turned right and down, the left arm out",
     m(v.pelvis((0.0, 0.0, -0.03), (4.0, 10.0, 0.0)), v.spine(8.0, 30.0, 6.0), v.foot("L", (0.13, -0.15), 12.0),
       v.foot("R", (0.13, -0.05), 18.0), v.head(14.0, -35.0, 10.0, ww=0.0), v.carry(), v.arm("L", (-20.0, 30.0), (-5.0, 70.0)),
       {"fingers_L": 0.05})),
]


def np_M(M):
    return {n: SCL.np_mat(x) for n, x in M.items()}


def apply(pose):
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    if not pose:
        bpy.context.view_layer.update()
        return None, {}, {}
    pose = S.apply_hold(sol, pose)
    local, M, info = sol.solve(pose)
    for n, (q, t) in local.items():
        if n in rig.keyed:
            pb = arm.pose.bones[n]
            pb.rotation_quaternion = q
            if n == "pelvis":
                pb.location = t
    Mn = np_M(M)
    basis, left = SCL.solve_static(cloth, Mn)
    for b, B3 in basis.items():
        pb = arm.pose.bones[b]
        from mathutils import Matrix
        pb.rotation_quaternion = Matrix(B3.tolist()).to_quaternion()
    bpy.context.view_layer.update()
    return pose, M, {"info": info, "cloth_bones_touching": left}


def angle(M, a, b):
    return round(math.degrees(M[a].to_3x3().col[1].angle(M[b].to_3x3().col[1])), 1)


SR.setup(scene, samples=8)
SR.toon_all(parts + ([weapon] if weapon else []))
report = {"hero": KEY, "renderer": "Cycles CPU emission toon (s2_selene_review.make_toon copy)", "poses": {}}
for name, what, pose in POSES:
    pose2, M, extra = apply(pose)
    rec = {"what": what}
    if M:
        info = extra["info"]
        rec.update({"elbow_deg": {s: angle(M, "upperarm_" + s, "lowerarm_" + s) for s in "LR"},
                    "knee_deg": {s: angle(M, "thigh_" + s, "shin_" + s) for s in "LR"},
                    "reach": {s: round(info.get("reach_" + s, 0.0), 3) for s in "LR"},
                    "cloth_bones_touching": extra["cloth_bones_touching"]})
        if pose2.get("hold", 0) > 0.5:
            G = M["weapon_R"] @ S.SOCKET_TO_GRIP
            rec["grip_L_error_m"] = round((G @ S.GRIP_L - M["weapon_L"].translation).length, 4)
    if weapon is not None:
        want = R.grip_matrix(arm, "weapon_R", pose=True)
        rec["weapon_attach_error"] = max(abs(a - b) for ra, rb in zip(want, weapon.matrix_world) for a, b in zip(ra, rb))
    weapon.hide_render = name == "bind" if weapon else True
    SR.shoot(scene, os.path.join(OUT, "pose_%s.png" % name), Vector((0.0, 0.0, 1.1)), SR.az_dir(-32.0, 8.0), 2.45, 460, 640)
    if name == "bind":
        bones = [(b.name, tuple(b.head_local), tuple(b.tail_local)) for b in arm.data.bones]
        pts = SR.project(scene, [p for _n, h, t in bones for p in (h, t)])
        rec["bone_lines_px"] = [[n, pts[2 * i], pts[2 * i + 1]] for i, (n, _h, _t) in enumerate(bones)]
    if name == "hold":
        SR.shoot(scene, os.path.join(OUT, "hold_closeup.png"), Vector((-0.08, -0.35, 1.38)), SR.az_dir(-40.0, 22.0), 1.05, 640, 460)
        SR.ingame(scene, os.path.join(OUT, "hold_ingame.png"), view_h=22.0, px=220)
    report["poses"][name] = rec
    log("pose %s: %s" % (name, {k: v for k, v in rec.items() if k != "bone_lines_px"}))
write_json(os.path.join(P["S3"], "poses.json"), report)
