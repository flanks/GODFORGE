"""Stage 3, step 1: the hero's GF_Hero_v1 landmark file from the stage-2 fit (headless Blender).

  blender -b art/characters/<key>/production/<key>_stage2.blend -P tools/blender/gf_hero/s3_landmarks.py -- <key>

Adapted from the Ashen Covenant make_landmarks_*.py pattern (a compact, reproducible landmark block per character;
D:/Ashen_Covenant/tools/blender/ac_player_rig/make_landmarks_ironwarden_m.py). Here nothing is typed by hand: the
stage-2 fit already measured the hero, so the joints are re-derived from it.

  1. Joints: the MakeHuman game_engine joints recorded by s2_body_base.py (work/<key>_s2_mh_landmarks.json) mapped
     through the stage-2 thin-plate spline (stage2_fit.json "landmarks" - the hand-measured joints of the sculpt,
     which the spline reproduces exactly) plus the fit's radial hand scale.
  2. Refinement on the fitted mesh (production/<key>_stage2.blend, BODY):
       * elbow, wrist and knee stay on the hand-measured stage-2 joints (the line between the two limb axes);
         the centroid of the body's edge ring there is only reported (the elbow ring bulges forward, so its
         centroid sits 3.6 cm in front of the hinge line on Brax);
       * every finger and thumb joint: centroid of that finger's cross-section at the joint, the tip 40 % of the
         finger radius inside the fingertip;
       * palm normal from the knuckle line, thumb curl toward the palm.
  3. Sockets: weapon_L / weapon_R = the stage-2 hand frames (reports/stage2/body_fit.json "hand_frames") that the
     weapon models were authored in; head_top = top of the head parts; chest_sigil = the chest surface at the
     sigil centre (stage2_texture.json paint.sigil.centre_z, else 60 % up spine_03).
  4. Checks (gf_hero_rig.validate_landmarks: every key, symmetry, socket frames), then
     art/characters/<key>/work/<key>_landmarks.json (committed) and reports/stage3/landmarks.json (diagnostics).
"""
import datetime
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import get_co, log, read_json, rel, script_args, write_json  # noqa: E402
from s3lib import hero_paths, tps_from_fit  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
P = hero_paths(KEY)
fit = read_json(P["fit"])
mh = read_json(P["mh"])
body_fit = read_json(P["body_fit"])
tps = tps_from_fit(fit, mh)
body = bpy.data.objects["BODY"]
co = get_co(body.data) @ np.array(body.matrix_world)[:3, :3].T + np.array(body.matrix_world)[:3, 3]
diag = {"hero": KEY}


def J(bone, end="head"):
    return tps(np.array([mh["joints"][bone][end]]))[0]


# ---- 1. joints through the stage-2 warp -------------------------------------------------------------------------
lr = fit["fit"].get("limb_radial", {})
axis_yz = np.array([lr.get("axis_y", 0.0), lr.get("axis_z", 0.0)])


def hand_scaled(p):
    """The fit's radial hand scale (s2_body_fit.py limb_radial): y/z about the arm axis past hand_from_abs_x."""
    if not lr:
        return p
    q = np.array(p, dtype=np.float64)
    ramp = np.clip((abs(q[0]) - lr["hand_from_abs_x"]) / 0.03, 0.0, 1.0)
    s = 1.0 + (lr["hand_scale"] - 1.0) * ramp
    q[1:3] = axis_yz + (q[1:3] - axis_yz) * s
    return q


L = {}
L["root"], L["root_tip"] = np.array([0.0, 0.0, 0.0]), np.array([0.0, -0.25, 0.0])
L["pelvis"] = J("pelvis")
L["spine_01"], L["spine_02"], L["spine_03"] = J("spine_01"), J("spine_02"), J("spine_03")
L["neck"], L["head"] = J("neck_01"), J("head")
skull = tps(np.array([mh["skull_top"]]))[0]
L["head_tip"] = np.array([0.0, L["head"][1], skull[2]])
for s, m in (("L", "l"), ("R", "r")):
    L["clavicle_" + s] = J("clavicle_" + m)
    L["shoulder_" + s] = J("upperarm_" + m)
    L["elbow_" + s] = J("lowerarm_" + m)
    L["wrist_" + s] = J("hand_" + m)
    L["hip_" + s] = J("thigh_" + m)
    L["knee_" + s] = J("calf_" + m)
    L["ankle_" + s] = J("foot_" + m)
    L["ball_" + s] = J("ball_" + m)
    L["toe_%s_tip" % s] = tps(np.array([mh["toe_" + m]]))[0] + np.array([0.0, 0.012, 0.0])   # just inside the toe cap
    for f in R.FINGERS:
        for i in (1, 2, 3):
            L["%s_%s_%02d" % (f, s, i)] = hand_scaled(J("%s_%02d_%s" % (f, i, m)))
        L["%s_%s_tip" % (f, s)] = hand_scaled(J("%s_03_%s" % (f, m), "tail"))
tps_joints = {k: v.copy() for k, v in L.items()}

# the spine chain must meet the neck: spine_03 runs to the neck joint (connected, as in AC_Player_Humanoid_v1)
for k in list(L):
    L[k] = np.array(L[k], dtype=np.float64)


# ---- 2. refinement on the fitted mesh ---------------------------------------------------------------------------------
def ring_centroid(axis, value, side, near, radius, width=0.006):
    """Centroid (full 3D) of the body vertices within `width` of the plane |x| = value (axis 'x') or z = value
    (axis 'z') on one side, within `radius` of `near`."""
    if axis == "x":
        m = (np.abs(np.abs(co[:, 0]) - value) < width) & (co[:, 0] * side > 0)
    else:
        m = (np.abs(co[:, 2] - value) < width) & (co[:, 0] * side > 0)
    m &= np.linalg.norm(co - near, axis=1) < radius
    if m.sum() < 6:
        return None, int(m.sum())
    c = co[m].mean(0)
    if axis == "x":
        c[0] = side * value
    else:
        c[2] = value
    return c, int(m.sum())


refine = {}
for s, sd in (("L", 1), ("R", -1)):
    for key, axis, rad in (("elbow_" + s, "x", 0.16), ("wrist_" + s, "x", 0.12), ("knee_" + s, "z", 0.18)):
        val = abs(L[key][0]) if axis == "x" else L[key][2]
        c, n = ring_centroid(axis, val, sd, L[key], rad)
        if c is not None:
            refine[key] = {"joint": np.round(L[key], 4).tolist(), "ring_centroid_reported_only": np.round(c, 4).tolist(),
                           "ring_verts": n, "offset_m": round(float(np.linalg.norm(c - L[key])), 4)}

# fingers: each vertex beyond the wrist belongs to the chain it is nearest to; each joint moves to the centroid of its
# finger's slab perpendicular to the chain
hand_rows = {}
for s, sd in (("L", 1), ("R", -1)):
    wx = abs(L["wrist_" + s][0])
    hv = np.nonzero((co[:, 0] * sd > wx + 0.01) & (co[:, 2] > 1.3))[0]
    chains = {f: [L["%s_%s_%02d" % (f, s, i)] for i in (1, 2, 3)] + [L["%s_%s_tip" % (f, s)]] for f in R.FINGERS}
    dists = []
    for f in R.FINGERS:
        pts = chains[f]
        best = np.full(len(hv), np.inf)
        for a, b in zip(pts[:-1], pts[1:]):
            d = b - a
            t = np.clip(((co[hv] - a) @ d) / (d @ d), 0, 1)
            best = np.minimum(best, np.linalg.norm(co[hv] - (a + t[:, None] * d), axis=1))
        dists.append(best)
    dists = np.stack(dists, axis=1)
    owner = dists.argmin(axis=1)
    hand_rows[s] = (hv, owner, dists.min(axis=1))
    for fi, f in enumerate(R.FINGERS):
        mine = hv[(owner == fi) & (dists.min(axis=1) < 0.03)]
        pts = [p.copy() for p in chains[f]]
        new = []
        radii = []
        for j, p in enumerate(pts):
            d = (pts[min(j + 1, 3)] - pts[max(j - 1, 0)])
            d /= np.linalg.norm(d)
            if j == 0 and f != "thumb":
                new.append(p)          # knuckle (MCP) heads stay on the palm line of the warp; the slab there is palm
                continue
            along = (co[mine] - p) @ d
            if j == 3:                 # tip: 40 % of the finger radius inside the farthest point
                far = along.max() if len(along) else 0.0
                sl = mine[np.abs(along - (far - 0.012)) < 0.006]
                r = np.linalg.norm((co[sl] - co[sl].mean(0)) - np.outer((co[sl] - co[sl].mean(0)) @ d, d), axis=1).mean() if len(sl) >= 4 else 0.008
                c = co[sl].mean(0) if len(sl) >= 4 else p
                c = c + d * ((far - 0.012) - (c - p) @ d)      # on the chain line's projection of the tip slab
                c = c + d * (0.012 - 0.4 * r)
                new.append(c)
                radii.append(float(r))
                continue
            sl = mine[np.abs(along) < 0.005]
            if len(sl) >= 5:
                c = co[sl].mean(0)
                c = c - d * ((c - p) @ d)      # keep the joint's position along the chain, move it across
                radii.append(float(np.linalg.norm(co[sl] - c, axis=1).mean()))
                new.append(c)
            else:
                new.append(p)
        for j, key in enumerate(["%s_%s_%02d" % (f, s, i) for i in (1, 2, 3)] + ["%s_%s_tip" % (f, s)]):
            refine[key] = {"moved_m": round(float(np.linalg.norm(new[j] - L[key])), 4)}
            L[key] = new[j]
        refine["%s_%s_radius_m" % (f, s)] = round(float(np.mean(radii)) if radii else 0.0, 4)
    L["hand_%s_tip" % s] = L["middle_%s_01" % s].copy()

# exact symmetry: the body is an exact mirror, so average each L/R pair
for k in list(L):
    if k.endswith("_L") or "_L_" in k:
        k2 = k[:-2] + "_R" if k.endswith("_L") else k.replace("_L_", "_R_")
        a, b = L[k], L[k2]
        m = 0.5 * (a + b * np.array([-1, 1, 1]))
        L[k], L[k2] = m, m * np.array([-1, 1, 1])
for k in ("root", "root_tip", "pelvis", "spine_01", "spine_02", "spine_03", "neck", "head", "head_tip"):
    L[k][0] = 0.0

# palm normal (away from the back of the hand) and thumb curl (toward the palm centre)
for s, sd in (("L", 1), ("R", -1)):
    across = L["index_%s_01" % s] - L["pinky_%s_01" % s]
    along = L["middle_%s_01" % s] - L["wrist_" + s]
    n = np.cross(across, along) if sd > 0 else np.cross(along, across)
    n /= np.linalg.norm(n)
    back = np.array(body_fit["hand_frames"][s]["z_axis"], dtype=np.float64)
    if n @ back > 0:
        n = -n
    L["palm_normal_" + s] = n
    palm = 0.5 * (L["wrist_" + s] + L["middle_%s_01" % s]) + n * 0.03
    t_ax = L["thumb_%s_tip" % s] - L["thumb_%s_01" % s]
    t_ax /= np.linalg.norm(t_ax)
    cv = palm - L["thumb_%s_02" % s]
    cv = cv - t_ax * (cv @ t_ax)
    L["thumb_curl_" + s] = cv / np.linalg.norm(cv)

# ---- 3. sockets ----------------------------------------------------------------------------------------------------
sockets = {}
for s in ("L", "R"):
    hf = body_fit["hand_frames"][s]
    sockets["weapon_" + s] = {"origin": hf["origin"], "forward": hf["y_axis"], "up": hf["z_axis"],
                              "source": "reports/stage2/body_fit.json hand_frames.%s (the weapon authoring frame)" % s}
head_parts = [o for o in bpy.data.objects if o.type == "MESH" and o.name in ("HAIR", "BODY", "BEARD")]
top = -1.0
for o in head_parts:
    c = get_co(o.data) @ np.array(o.matrix_world)[:3, :3].T + np.array(o.matrix_world)[:3, 3]
    c = c[np.abs(c[:, 0]) < 0.25]
    top = max(top, float(c[:, 2].max()))
sockets["head_top"] = {"origin": [0.0, round(float(L["head"][1]), 5), round(top, 5)], "forward": [0.0, -1.0, 0.0], "up": [0.0, 0.0, 1.0],
                       "source": "top of HAIR/BODY/BEARD above the head joint"}
tex_cfg_path = os.path.join(P["A"], "stage2_texture.json")
sig_z = None
if os.path.exists(tex_cfg_path):
    sig_z = read_json(tex_cfg_path).get("paint", {}).get("sigil", {}).get("centre_z")
if sig_z is None:
    sig_z = float(L["spine_03"][2] + 0.6 * (L["neck"][2] - L["spine_03"][2]))
dg = bpy.context.evaluated_depsgraph_get()
bvh = BVHTree.FromObject(body, dg)
hit, nrm, _fi, _d = bvh.ray_cast(Vector((0.0, -2.0, sig_z)), Vector((0.0, 1.0, 0.0)), 4.0)
if hit is None:
    raise SystemExit("chest_sigil: no chest surface at z = %.3f" % sig_z)
nrm = Vector((0.0, nrm.y, nrm.z)).normalized()
if nrm.y > 0:
    nrm = -nrm
up = Vector((0, 0, 1)) - nrm * nrm.z
sockets["chest_sigil"] = {"origin": [0.0, round(hit.y, 5), round(sig_z, 5)], "forward": [0.0, round(nrm.y, 5), round(nrm.z, 5)],
                          "up": [0.0, round(up.normalized().y, 5), round(up.normalized().z, 5)],
                          "source": "BODY surface at x = 0, z = %.3f (stage2_texture.json paint.sigil.centre_z)" % sig_z}

# ---- 4. write --------------------------------------------------------------------------------------------------------
out = {"_doc": "GF_Hero_v1 landmarks for %s (docs/art/GF_HERO_SKELETON.md). Rest pose = the stage-2 T-pose. Metres, Blender "
               "axes: Z up, the hero faces -Y, +X = his left, feet on z = 0. Points are bone heads/tails; palm_normal_* and "
               "thumb_curl_* are unit vectors; sockets are frames (origin, forward, up). Generated by "
               "tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit - rerun it rather than editing by hand." % KEY}
for k in R.POINT_KEYS:
    out[k] = [round(float(v), 5) for v in L[k]]
for k in R.VECTOR_KEYS:
    out[k] = [round(float(v), 5) for v in L[k]]
out["sockets"] = sockets
out["extra_bones"] = []


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


out["_meta"] = {"hero": KEY, "contract": "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION), "generated": datetime.date.today().isoformat(),
                "inputs": {rel(p): sha(p) for p in (P["fit"], P["body_fit"], P["stage2"])} | {rel(P["mh"]): sha(P["mh"]) + " (local, regenerated by run_stage2.py base)"}}
problems = R.validate_landmarks(out)
if problems:
    raise SystemExit("landmark problems: " + "; ".join(problems))
write_json(P["landmarks"], out)
bone_len = {}
for b in R.CORE_BONES:
    bone_len[b[0]] = round(float(np.linalg.norm(np.array(R.point(out, b[3])) - np.array(R.point(out, b[2])))), 4)
diag.update({"refinement": refine, "tps_joint_delta_m": {k: round(float(np.linalg.norm(L[k] - tps_joints[k])), 4) for k in tps_joints if k in L},
             "core_bone_lengths_m": bone_len, "sockets": sockets, "height_m": round(float(co[:, 2].max()), 4)})
write_json(os.path.join(P["S3"], "landmarks.json"), diag)
log("landmarks OK:", len(R.POINT_KEYS), "points,", len(sockets), "sockets")
