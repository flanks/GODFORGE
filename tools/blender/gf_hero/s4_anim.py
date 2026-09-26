"""Stage 4, step 1: bake the clip library onto one hero (headless Blender 5.2).

  blender -b -P tools/blender/gf_hero/s4_anim.py -- <key> [--only clip,clip] [--print-keys]

Opens production/<key>_rig.blend, builds the shared GF_Hero_v1 library (s4_clips.py) plus the hero's unique set
(s4_<key>.py), solves every frame (s4lib), writes one action per clip named <key>_<clip>[@loop] (ARCHITECTURE section 9,
docs/art/GF_HERO_SKELETON.md section 8) on its own muted NLA track, and measures each clip from the solved skeleton:
  * loop seam: the last frame against the first (degrees / mm) and the velocity jump across the seam;
  * in place: the pelvis' horizontal drift; root, twist bones and sockets never keyed;
  * foot sliding: every contact interval of each foot's ball joint, in WORLD space (the design travel added back), and
    how far the ball drifts inside it; ground penetration of the ball / toe / heel points;
  * the sleeve-weapon rule: wrist swing (must be 0: the hand only twists), hand twist range, elbow flexion (the
    anvil_gauntlets cuff presses into the biceps past ~40 deg; the solver caps it at s4lib.ELBOW_MAX_DEG, the stage-3
    validated maximum), knee flexion, IK misses (soft reach; frames where the elbow cap eased the fist out of the fold
    zone are counted separately as elbow_fold_eased);
  * the solver against Blender: pose-bone matrices after frame_set vs the solver's (every clip, 3 frames).
Outputs: production/<key>_anim.blend (Git LFS: rig + skinned parts + the clips), reports/anim/clips.json.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import s4lib as L  # noqa: E402
from s2lib import ROOT, log, read_json, save_blend, script_args, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
PRINT_KEYS = "--print-keys" in argv
P = hero_paths(KEY)
OUT_BLEND = os.path.join(P["A"], "production", "%s_anim.blend" % KEY)
OUT_DIR = os.path.join(P["A"], "reports", "anim")
os.makedirs(OUT_DIR, exist_ok=True)
T0 = time.time()


def move_speed(key):
    import csv
    with open(os.path.join(ROOT, "content", "sheets", "characters.csv"), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["key"] == key:
                return float(row["stats.move_speed"])
    raise SystemExit("no characters.csv row for %s" % key)


try:
    HERO = __import__("s4_%s" % KEY)
except ImportError:
    HERO = None


def library(K):
    import s4_clips
    # a hero whose armour limits its joint ranges (Valdris) bakes the shared set from its own module:
    # s4_<key>.shared_clips(K), the same clip names, loop flags and layers (asserted against s4_contract below)
    if HERO is not None and hasattr(HERO, "shared_clips"):
        clips = HERO.shared_clips(K)
    else:
        clips = s4_clips.shared_clips(K)
    if HERO is not None:
        clips += HERO.unique_clips(K)
    else:
        log("no unique clip module s4_%s.py" % KEY)
    return clips


# a partial run (--only) updates the existing anim file; a full run starts from the stage-3 rig file
bpy.ops.wm.open_mainfile(filepath=OUT_BLEND if (ONLY and os.path.exists(OUT_BLEND)) else P["rig"])
scene = bpy.context.scene
scene.render.fps = L.FPS
scene.render.fps_base = 1.0
arm = bpy.data.objects[R.RIG_NAME]
assert arm.matrix_world == arm.matrix_world.Identity(4), "the armature object must sit at the origin"
LM = read_json(P["landmarks"])
K = L.Kit(LM, move_speed(KEY))
rig = L.Rig(arm)
solver = L.Solver(rig, K)


# parts that hang and swing (stage-2 part names): not obstacles for the arm keep-out; a hero module may add its own
# (s4_<key>.KEEPOUT_LOOSE_PARTS) and name extra bones whose vertices never block an arm (KEEPOUT_OWN_BONES[side])
LOOSE_CLOTH = {"SKIRT_PLATES", "SKIRT_CLOTH", "SASH"} | set(getattr(HERO, "KEEPOUT_LOOSE_PARTS", ()))
OWN_EXTRA = getattr(HERO, "KEEPOUT_OWN_BONES", {})


def build_keepout():
    """s4lib.KeepOut from this file: every skinned part at rest (top-4 weights), and per hand the rigid volume it
    carries - the signature weapon's fist + open meshes when it is a sleeve weapon (the PREVIEW objects stage 3 linked
    onto the sockets reach back past the wrist), else the hero's own forearm, hand and fingers."""
    import numpy as np
    bones = [b.name for b in arm.data.bones]
    bidx = {n: i for i, n in enumerate(bones)}
    V, J, W, dom = [], [], [], []
    for o in scene.objects:
        if o.type != "MESH" or o.name.startswith(("PREVIEW", "REF", "WIRE")) or not o.vertex_groups:
            continue
        if o.name in LOOSE_CLOTH:      # hanging cloth / plates move out of the way (secondary motion), they never steer an arm
            continue
        gname = {g.index: g.name for g in o.vertex_groups}
        mw = o.matrix_world
        for v in o.data.vertices:
            gs = sorted(((g.weight, gname[g.group]) for g in v.groups if g.weight > 0 and gname.get(g.group) in bidx), reverse=True)[:4]
            if not gs:
                continue
            tot = sum(w for w, _ in gs)
            V.append(tuple(mw @ v.co))
            J.append([bidx[n] for _, n in gs] + [0] * (4 - len(gs)))
            W.append([w / tot for w, _ in gs] + [0.0] * (4 - len(gs)))
            dom.append(gs[0][1])
    V = np.array(V)
    dom = np.array(dom)
    fingers = {s: {b[0] for b in R.finger_bones(s)} for s in ("L", "R")}

    def arm_set(s, upper=True):
        out = {"lowerarm_" + s, "lowerarm_twist_" + s, "hand_" + s} | fingers[s]
        if upper:
            out |= {"upperarm_" + s, "upperarm_twist_" + s}
        return out
    own = {s: np.isin(dom, list(arm_set(s) | arm_set("R" if s == "L" else "L", upper=False) | set(OWN_EXTRA.get(s, ()))))
           for s in ("L", "R")}

    def radial_map(pts, dy=0.02, nth=36):
        cx, cz = float(np.median(pts[:, 0])), float(np.median(pts[:, 2]))
        y0 = float(pts[:, 1].min())
        ny = int(math.ceil((pts[:, 1].max() - y0) / dy)) + 1
        x, z = pts[:, 0] - cx, pts[:, 2] - cz
        iy = np.clip(((pts[:, 1] - y0) / dy).astype(np.int64), 0, ny - 1)
        ith = np.floor((np.arctan2(z, x) + math.pi) / (2 * math.pi) * nth).astype(np.int64) % nth
        rm = np.zeros((ny, nth))
        np.maximum.at(rm, (iy, ith), np.hypot(x, z))
        for _ in range(nth):
            empty = rm == 0.0
            if not empty.any():
                break
            nb = np.maximum(np.roll(rm, 1, 1), np.roll(rm, -1, 1))
            rm[empty] = nb[empty]
        return {"cx": cx, "cz": cz, "y0": y0, "dy": dy, "ny": ny, "nth": nth, "rmax": rm}
    shape, used = {}, {}
    for s in ("L", "R"):
        G = R.grip_matrix(arm, "weapon_" + s, pose=False)
        wrist_y = (G.inverted() @ rig.b["hand_" + s].head).y
        prev = [o for o in scene.objects if o.type == "MESH" and o.name.startswith("PREVIEW") and o.name.endswith("_" + s)]
        pts = [tuple(v.co) for o in prev for v in o.data.vertices]      # mesh-local = the grip frame
        if pts and min(p[1] for p in pts) < wrist_y:
            shape[s] = radial_map(np.array(pts))
            used[s] = "sleeve weapon: " + ", ".join(sorted(o.name for o in prev))
        else:
            Gi = np.array(G.inverted())
            m = np.isin(dom, list(arm_set(s, upper=False)))
            loc = V[m] @ Gi[:3, :3].T + Gi[:3, 3]
            shape[s] = radial_map(loc)
            used[s] = "bare forearm, hand and fingers (%d vertices)" % int(m.sum())
    ko = L.KeepOut(bones, [rig.b[n].rest.inverted() for n in bones], V, J, W, own, shape,
                   [rig.b[n].length for n in bones], margin=0.003)
    return ko, {"vertices": int(len(V)), "volumes": used, "margin_m": ko.margin,
                "radius_p50_m": {s: round(float(np.median(shape[s]["rmax"])), 3) for s in shape}}


solver.keepout, KEEPOUT_INFO = build_keepout()
log("keep-out: %s" % KEEPOUT_INFO)
CLIPS = library(K)
names = [c.clip for c in CLIPS]
assert len(names) == len(set(names)), "duplicate clip names"
import s4_contract as SC  # noqa: E402
got = [(c.clip, c.loop, c.layer) for c in CLIPS if c.family == "shared"]
assert got == [tuple(x) for x in SC.SHARED_CLIPS], "the shared library and s4_contract.SHARED_CLIPS disagree"
if ONLY:
    CLIPS = [c for c in CLIPS if c.clip in ONLY]

# old clip tracks / actions of this hero go (the validation poses stay)
if arm.animation_data:
    arm.animation_data.action = None
    for tr in list(arm.animation_data.nla_tracks):
        if tr.name.startswith(KEY + "_"):
            arm.animation_data.nla_tracks.remove(tr)
for a in list(bpy.data.actions):
    if a.name.startswith(KEY + "_") and (ONLY is None or any(a.name == c.action_name(KEY) for c in CLIPS)):
        bpy.data.actions.remove(a)

BALL_Z = {s: solver.ball_rest[s].z for s in ("L", "R")}
HEEL_LOCAL = {}
for s in ("L", "R"):
    a = rig.b["foot_" + s]
    heel = Vector((a.head.x, a.head.y + 0.09 * K.ls, 0.0))
    HEEL_LOCAL[s] = a.rest.inverted() @ heel
TOE_Z = {s: rig.b["toe_" + s].tail.z for s in ("L", "R")}


def angle_between(a, b):
    return math.degrees(a.angle(b)) if a.length > 1e-9 and b.length > 1e-9 else 0.0


def clip_metrics(clip, frames, eul):
    n = len(frames)
    m = {}
    # loop seam (Euler channels + pelvis location) and the velocity jump across the seam
    if clip.loop:
        # the seam: the last frame must BE the first, and the motion through the seam (second difference with cyclic
        # neighbours) must be no rougher than anywhere inside the clip
        dmax = 0.0
        seam_acc = 0.0
        in_acc = 0.0
        L_ = n - 1
        for b, seq in eul.items():
            for i in range(3):
                x = [e[i] for e in seq]
                d = abs(x[-1] - x[0])
                dmax = max(dmax, min(d, abs(d - 2 * math.pi)))
                seam_acc = max(seam_acc, abs(x[1] - 2 * x[0] + x[L_ - 1]))
                for f in range(1, L_):
                    in_acc = max(in_acc, abs(x[f + 1] - 2 * x[f] + x[f - 1]))
        pl0 = frames[0][0]["pelvis"][1]
        pl1 = frames[-1][0]["pelvis"][1]
        m["loop_seam_deg"] = round(math.degrees(dmax), 4)
        m["loop_seam_pelvis_mm"] = round((pl1 - pl0).length * 1000, 3)
        m["seam_accel_deg"] = round(math.degrees(seam_acc), 3)
        m["interior_accel_max_deg"] = round(math.degrees(in_acc), 3)
        sp, ip = 0.0, 0.0
        for bn in ("hand_L", "hand_R", "toe_L", "toe_R", "head", "pelvis"):
            X = [fr[1][bn].translation for fr in frames]
            sp = max(sp, (X[1] - 2 * X[0] + X[L_ - 1]).length)
            for f in range(1, L_):
                ip = max(ip, (X[f + 1] - 2 * X[f] + X[f - 1]).length)
        m["seam_accel_mm"] = round(sp * 1000, 2)
        m["interior_accel_max_mm"] = round(ip * 1000, 2)
        m["seam_ok"] = bool(dmax < 1e-6 and seam_acc <= in_acc * 1.05 + 1e-4 and sp <= ip * 1.05 + 1e-5)
    # in place
    ph = [Vector((fr[1]["pelvis"].translation.x, fr[1]["pelvis"].translation.y)) for fr in frames]
    m["pelvis_horizontal_max_mm"] = round(max(p.length for p in ph) * 1000, 1)
    m["pelvis_z_range_m"] = [round(min(fr[1]["pelvis"].translation.z for fr in frames), 3),
                             round(max(fr[1]["pelvis"].translation.z for fr in frames), 3)]
    # feet: contacts in world space
    tx, ty = clip.travel
    feet = {}
    ground_min = 0.0
    for s in ("L", "R"):
        world = []
        grounded = []
        for f, fr in enumerate(frames):
            Mb = fr[1]
            ball = Mb["toe_" + s].translation
            t = f / L.FPS
            world.append(Vector((ball.x + tx * t, ball.y + ty * t)))
            grounded.append(ball.z < BALL_Z[s] + 0.004)
            heel = Mb["foot_" + s] @ HEEL_LOCAL[s]
            tip = Mb["toe_" + s] @ Vector((0.0, rig.b["toe_" + s].length, 0.0))
            ground_min = min(ground_min, ball.z - BALL_Z[s], tip.z - TOE_Z[s], heel.z)
        intervals = []
        f = 0
        while f < n:
            if grounded[f]:
                g = f
                while g + 1 < n and grounded[g + 1]:
                    g += 1
                intervals.append((f, g))
                f = g + 1
            else:
                f += 1
        # a loop's contact that runs through the seam is one interval (frame n-1 == frame 0)
        if clip.loop and len(intervals) >= 2 and intervals[0][0] == 0 and intervals[-1][1] == n - 1:
            a0, a1 = intervals.pop(0)
            b0, b1 = intervals.pop(-1)
            shift = Vector((tx, ty)) * ((n - 1) / L.FPS)
            pts = [world[i] for i in range(b0, b1 + 1)] + [world[i] + shift for i in range(a0, a1 + 1)]
            intervals.append((b0, a1 + n - 1, pts))
        slide = 0.0
        out = []
        for iv in intervals:
            pts = iv[2] if len(iv) == 3 else [world[i] for i in range(iv[0], iv[1] + 1)]
            d = max((p - pts[0]).length for p in pts)
            slide = max(slide, d)
            out.append([iv[0], iv[1], round(d * 1000, 1)])
        feet[s] = {"contact_intervals": out, "slide_max_mm": round(slide * 1000, 1),
                   "grounded_frames": int(sum(grounded)), "world_xy": [[round(p.x, 4), round(p.y, 4)] for p in world],
                   "ball_z": [round(fr[1]["toe_" + s].translation.z, 4) for fr in frames]}
    m["feet"] = feet
    m["foot_slide_max_mm"] = max(feet["L"]["slide_max_mm"], feet["R"]["slide_max_mm"])
    m["ground_penetration_mm"] = round(min(0.0, ground_min) * 1000, 1)
    # arms / legs
    wrist = 0.0
    tw = {"L": [], "R": []}
    elbow = {"L": 0.0, "R": 0.0}
    knee = {"L": 0.0, "R": 0.0}
    reach = 0.0
    miss = 0.0
    fold_ease, fold_frames = 0.0, 0
    knee_ease, knee_frames = 0.0, 0
    ko_short = 0.0
    for fr in frames:
        local, Mb, info, pose = fr
        for s in ("L", "R"):
            q = local["hand_" + s][0]
            # swing = rotation of the bone axis (twist-free part)
            wrist = max(wrist, angle_between(Vector((0, 1, 0)), q @ Vector((0, 1, 0))))
            tw[s].append(info.get("twist_" + s, 0.0))
            ua = Mb["upperarm_" + s].to_3x3().col[1]
            la = Mb["lowerarm_" + s].to_3x3().col[1]
            elbow[s] = max(elbow[s], angle_between(ua, la))
            ta = Mb["thigh_" + s].to_3x3().col[1]
            sa = Mb["shin_" + s].to_3x3().col[1]
            knee[s] = max(knee[s], angle_between(ta, sa))
            reach = max(reach, info.get("reach_" + s, 0.0), info.get("reach_leg_" + s, 0.0))
            if ("foot_" + s) in pose:
                _Rf, _B, A, _y, _h = solver.foot_frame(s, pose["foot_" + s])
                e = (Mb["shin_" + s] @ Vector((0.0, rig.b["shin_" + s].length, 0.0)) - A).length
                if info.get("knee_eased_" + s):      # the knee limit (s4lib.KNEE_MAX_DEG) moved the ankle out
                    knee_ease = max(knee_ease, e)
                    knee_frames += 1
                else:
                    miss = max(miss, e)
            if ("arm_" + s) in pose and "target_" + s in info:
                eff = Mb["lowerarm_" + s] @ (rig.fist_eff[s] if "fist" in pose["arm_" + s] else Vector((0.0, rig.b["lowerarm_" + s].length, 0.0)))
                e = (eff - info["target_" + s]).length
                if info.get("fold_eased_" + s):      # the elbow limit (s4lib.ELBOW_MAX_DEG) moved the fist out
                    fold_ease = max(fold_ease, e)
                    fold_frames += 1
                elif info.get("keepout_" + s):        # the keep-out pushed the fist target past the arm's reach
                    ko_short = max(ko_short, e)
                else:
                    miss = max(miss, e)
    m["wrist_swing_max_deg"] = round(wrist, 3)
    m["hand_twist_range_deg"] = {s: [round(min(v), 1), round(max(v), 1)] for s, v in tw.items()}
    m["elbow_flexion_max_deg"] = {s: round(v, 1) for s, v in elbow.items()}
    m["knee_flexion_max_deg"] = {s: round(v, 1) for s, v in knee.items()}
    m["ik_reach_max"] = round(reach, 4)
    m["ik_miss_max_mm"] = round(miss * 1000, 1)
    m["elbow_limit_deg"] = L.ELBOW_MAX_DEG
    m["elbow_fold_eased"] = {"arm_frames": fold_frames, "max_mm": round(fold_ease * 1000, 1)}
    m["knee_limit_deg"] = L.KNEE_MAX_DEG
    m["knee_fold_eased"] = {"leg_frames": knee_frames, "max_mm": round(knee_ease * 1000, 1)}
    # the arm keep-out (s4lib.KeepOut): how far fists were pushed out of the body, and what still overlaps
    ko = [max(fr[2].get("keepout_L", 0.0), fr[2].get("keepout_R", 0.0)) for fr in frames]
    m["keepout_push"] = {"frames": sum(1 for v in ko if v > 0), "max_mm": round(max(ko) * 1000, 1),
                         "reach_short_mm": round(ko_short * 1000, 1)}
    if solver.keepout is not None:
        res = [solver.keepout.residual(fr[1]) for fr in frames]
        m["keepout_residual_verts_max"] = {s: max(r[s] for r in res) for s in ("L", "R")}
    # fist curve (the anvil_gauntlets variant: fist when the fingers are curled past half)
    fc = {}
    for s in ("L", "R"):
        vals = [math.degrees(fr[0]["index_01_" + s][0].angle) / 80.0 for fr in frames]
        swaps = [i for i in range(1, n) if (vals[i] >= 0.5) != (vals[i - 1] >= 0.5)]
        fc[s] = {"start": "fist" if vals[0] >= 0.5 else "open", "swap_frames": swaps}
    m["weapon_variant"] = fc
    return m


# ---- build -----------------------------------------------------------------------------------------------------------
report = {"hero": KEY, "skeleton": "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION), "fps": L.FPS,
          "kit": {"leg_m": round(K.leg, 4), "arm_m": round(K.arm, 4), "leg_scale": round(K.ls, 4), "arm_scale": round(K.as_, 4),
                  "height_m": round(K.height, 3), "move_speed_mps": K.move_speed},
          "naming": "<key>_<clip> for one-shots, <key>_<clip>@loop for loops (docs/art/GF_HERO_SKELETON.md section 8)",
          "keyed_bones": rig.keyed, "keepout": KEEPOUT_INFO, "elbow_limit_deg": L.ELBOW_MAX_DEG, "knee_limit_deg": L.KNEE_MAX_DEG, "clips": {}}
old = {}
man_p = os.path.join(OUT_DIR, "clips.json")
if ONLY and os.path.exists(man_p):
    old = json.load(open(man_p, encoding="utf-8")).get("clips", {})
    report["clips"].update(old)
fk_err = 0.0
tracks = []
for clip in CLIPS:
    t = time.time()
    frames = L.bake(solver, clip)
    name = clip.action_name(KEY)
    act, eul = L.write_action(bpy, arm, name, frames, rig.keyed + clip.extra_keyed, clip.loop)
    for mk, fr_ in sorted(clip.events.items(), key=lambda kv: kv[1]):
        act.pose_markers.new(mk).frame = int(fr_)
    # the solver against Blender's own evaluation
    for f in sorted({0, clip.length // 2, clip.length}):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        for bn in rig.keyed:
            e = (arm.pose.bones[bn].matrix.translation - frames[f][1][bn].translation).length
            e2 = (arm.pose.bones[bn].matrix.to_3x3() - frames[f][1][bn].to_3x3())
            e2 = max(abs(v) for row in e2 for v in row)
            fk_err = max(fk_err, e, e2)
    m = clip_metrics(clip, frames, eul)
    info = {"action": name, "family": clip.family, "frames": clip.length, "samples": clip.length + 1,
            "duration_s": round(clip.length / L.FPS, 4), "loop": clip.loop, "layer": clip.layer, "weapon": clip.weapon,
            "purpose": clip.purpose, "maps_to": clip.maps_to, "events": clip.events, "notes": clip.notes,
            "design_speed_mps": clip.speed, "travel_mps": list(clip.travel), "key_frames": clip.key_frames(),
            "slide_exempt": clip.slide_exempt, "metrics": m}
    if clip.extra_keyed:
        info["extra_keyed"] = clip.extra_keyed
    if clip.base:
        info["base"] = clip.base
    report["clips"][clip.clip] = info
    tracks.append((name, act))
    log("%-24s %3d f %s slide %5.1f mm seam %s wrist %.2f elbow %s miss %.1f mm keep-out %s left %s (%.1fs)" % (
        name, clip.length, "loop" if clip.loop else "    ", m["foot_slide_max_mm"], m.get("seam_ok", "-"),
        m["wrist_swing_max_deg"], m["elbow_flexion_max_deg"], m["ik_miss_max_mm"], m["keepout_push"],
        m.get("keepout_residual_verts_max"), time.time() - t))
    if PRINT_KEYS:
        for f in clip.key_frames():
            local, Mb, inf, pose = frames[f]
            for sd in ("L", "R"):
                if ("arm_" + sd) in pose:
                    T, _pp, _d = solver.arm_world(sd, pose["arm_" + sd], Mb)
                    sh = Mb["upperarm_" + sd].translation
                    log("        arm %s shoulder %s target %s dist %.3f (max %.3f)" % (
                        sd, tuple(round(x, 2) for x in sh), tuple(round(x, 2) for x in T), (T - sh).length, K.arm))
            log("   f%3d reach %s" % (f, {k: round(v, 3) for k, v in inf.items() if k.startswith("reach")}),
                "elbow L %.0f R %.0f knee L %.0f R %.0f" % tuple(
                    angle_between(Mb[a + s].to_3x3().col[1], Mb[b + s].to_3x3().col[1])
                    for a, b in (("upperarm_", "lowerarm_"), ("thigh_", "shin_")) for s in ("L", "R")))

# NLA: one muted track per clip, in library order (the exporter writes one glTF animation per track)
arm.animation_data.action = None
for name, act in tracks:
    tr = arm.animation_data.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.name = name
    tr.mute = True
for pb in arm.pose.bones:
    pb.rotation_euler = (0, 0, 0)
    pb.location = (0, 0, 0)
scene.frame_start, scene.frame_end = 0, max(c.length for c in CLIPS)
scene.frame_set(0)
report["solver_vs_blender_max_error"] = max(fk_err, report.get("solver_vs_blender_max_error", 0.0))
report["order"] = [c for c in names if c in report["clips"]]
report["seconds"] = round(time.time() - T0, 1)
save_blend(OUT_BLEND)
write_json(man_p, report)
log("solver vs Blender max error %.2e; %d clips; %.0fs" % (fk_err, len(tracks), time.time() - T0))
