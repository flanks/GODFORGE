"""Stage 3, Valdris: finish his GF_Hero_v1 landmark file after the shared s3_landmarks.py (headless Blender).

  blender -b art/characters/valdris/production/valdris_stage2.blend -P tools/blender/gf_hero/s3_valdris_landmarks.py

The shared step derives every contract joint from the stage-2 fit (the MakeHuman joints through the thin-plate spline, the
x1.6 glove hand scale) and the sockets from the stage-2 hand frames. Valdris is an armoured hero, so three things change
(the landmark JSON is the whole contract, docs/art/GF_HERO_SKELETON.md section 5: "a hero built another way writes the
same JSON by any means"):

  1. Fingers: the shared step moves each finger joint to the centre of the GLOVE finger's cross-section. Valdris's
     visible fingers are the box-section gauntlet lames, built by s2_valdris_parts.py around the warped joints it recorded
     (reports/stage2/parts.json finger_joints_L). The finger bones must pivot where the lames were built, or the lames
     open gaps and overlap when the fist closes, so the joints are set back to those (mirrored for the right hand; the
     gauntlets are exact mirrors). The palm normal and the thumb curl are recomputed with the shared formulas. The hand
     bone's tail is the middle knuckle projected onto the forearm axis (1.2 cm), so the hand twist of the sleeve-weapon
     rule keeps the colossus_cannon coaxial with the forearm.
  2. chest_sigil: his chest emblem is the ANVIL, 0.35 m in front of the under-suit the shared step ray-casts. The socket
     sits on the anvil's front face at x = 0, forward = that face's normal.
  3. extra_bones: his x_ helpers and cloth chains (stage3_skin.json "rig"): x_pauldron_L/R, x_elbow_L/R, x_knee_L/R,
     x_tasset_L/R, x_fauld_01 (driven), x_cape_* (5 x 5), x_loin_* (3 x 3), x_beard_*_01..02 (5 x 2).

Then gf_hero_rig.validate_landmarks, work/valdris_landmarks.json (committed) and reports/stage3/landmarks.json (the shared
diagnostics plus a "valdris" section).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import get_co, log, read_json, rel, write_json  # noqa: E402
from s3lib import components, hero_paths  # noqa: E402

KEY = "valdris"
P = hero_paths(KEY)
LM = read_json(P["landmarks"])
CFG = read_json(P["skin_cfg"])["rig"]
PARTS_CFG = read_json(os.path.join(P["A"], "stage2_parts.json"))
PARTS_REP = read_json(os.path.join(P["A"], "reports", "stage2", "parts.json"))
PIECE_NAME = {p["id"]: p["name"] for p in PARTS_REP["piece_table"]}
MX = np.array([-1.0, 1.0, 1.0])
diag = {"generated_by": "tools/blender/gf_hero/s3_valdris_landmarks.py (after the shared s3_landmarks.py)"}


def world_co(ob):
    mw = np.array(ob.matrix_world)
    return get_co(ob.data) @ mw[:3, :3].T + mw[:3, 3]


def piece_vertices(ob):
    """{piece name: [vertex index arrays, one per connected component]} from the face attribute gf_piece."""
    me = ob.data
    fp = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["gf_piece"].data.foreach_get("value", fp)
    vp = np.full(len(me.vertices), -1)
    for poly, pid in zip(me.polygons, fp):
        vp[list(poly.vertices)] = pid
    lab = components(me)
    out = {}
    for k in range(int(lab.max()) + 1):
        idx = np.nonzero(lab == k)[0]
        out.setdefault(PIECE_NAME[int(vp[idx[0]])], []).append(idx)
    return out


# ---- 1. finger joints on the gauntlet lames --------------------------------------------------------------------------
fj = PARTS_REP["finger_joints_L"]
moved = {}
for f in R.FINGERS:
    segs = fj[f]
    pts = [np.array(s[:3]) for s in segs] + [np.array(segs[-1][3:])]
    keys = ["%s_L_%02d" % (f, i) for i in (1, 2, 3)] + ["%s_L_tip" % f]
    for k, p in zip(keys, pts):
        moved[k] = round(float(np.linalg.norm(p - np.array(LM[k]))), 4)
        LM[k] = [round(float(v), 5) for v in p]
        kr = k.replace("_L_", "_R_")
        LM[kr] = [round(float(v), 5) for v in p * MX]
# the hand bone's tail: the middle knuckle projected onto the forearm axis (elbow -> wrist). The colossus_cannon is a
# SLEEVE weapon coaxial with the forearm (stage-2 hand frames on the forearm axis), and the sleeve rule keeps the wrist
# straight and only twists the hand about its own Y: with the tail 1.2 cm off the axis that twist would tilt the barrel
# off the forearm by up to 12 degrees and push the massive vambrace (already inside the sleeve wall) out of it.
for s in ("L", "R"):
    e, w = np.array(LM["elbow_" + s]), np.array(LM["wrist_" + s])
    ax = (w - e) / np.linalg.norm(w - e)
    k = np.array(LM["middle_%s_01" % s])
    tip = w + ax * ((k - w) @ ax)
    diag.setdefault("hand_tip_on_forearm_axis_m", {})[s] = round(float(np.linalg.norm(tip - k)), 4)
    LM["hand_%s_tip" % s] = [round(float(v), 5) for v in tip]
body_fit = read_json(P["body_fit"])
for s in ("L", "R"):
    V = {k: np.array(LM[k]) for k in LM if isinstance(LM[k], list) and len(LM[k]) == 3 and not isinstance(LM[k][0], list)}
    across = V["index_%s_01" % s] - V["pinky_%s_01" % s]
    along = V["middle_%s_01" % s] - V["wrist_" + s]
    n = np.cross(across, along) if s == "L" else np.cross(along, across)
    n /= np.linalg.norm(n)
    if n @ np.array(body_fit["hand_frames"][s]["z_axis"]) > 0:
        n = -n
    LM["palm_normal_" + s] = [round(float(v), 5) for v in n]
    palm = 0.5 * (V["wrist_" + s] + V["middle_%s_01" % s]) + n * 0.03
    t_ax = V["thumb_%s_tip" % s] - V["thumb_%s_01" % s]
    t_ax /= np.linalg.norm(t_ax)
    cv = palm - V["thumb_%s_02" % s]
    cv = cv - t_ax * (cv @ t_ax)
    LM["thumb_curl_" + s] = [round(float(v), 5) for v in cv / np.linalg.norm(cv)]
diag["fingers"] = {"source": "reports/stage2/parts.json finger_joints_L (the joints the gauntlet lames were built on), mirrored",
                   "moved_from_shared_m": moved, "max_move_m": max(moved.values())}
log("finger joints set to the lame joints; largest move %.1f mm" % (1000 * max(moved.values())))

# ---- 2. chest_sigil on the anvil ---------------------------------------------------------------------------------------
anvil = bpy.data.objects["ANVIL"]
aco = world_co(anvil)
body_piece = piece_vertices(anvil)["ANVIL_BODY"][0]
z_sig = round(float(0.5 * (aco[body_piece, 2].min() + aco[body_piece, 2].max())), 4)
bvh = BVHTree.FromPolygons([tuple(c) for c in aco], [tuple(p.vertices) for p in anvil.data.polygons])
hit, nrm, _fi, _d = bvh.ray_cast(Vector((0.0, -2.0, z_sig)), Vector((0.0, 1.0, 0.0)), 4.0)
if hit is None:
    raise SystemExit("chest_sigil: no anvil surface at z = %.3f" % z_sig)
nrm = Vector((0.0, nrm.y, nrm.z)).normalized()
if nrm.y > 0:
    nrm = -nrm
up = (Vector((0, 0, 1)) - nrm * nrm.z).normalized()
LM["sockets"]["chest_sigil"] = {"origin": [0.0, round(hit.y, 5), z_sig], "forward": [0.0, round(nrm.y, 5), round(nrm.z, 5)],
                                "up": [0.0, round(up.y, 5), round(up.z, 5)],
                                "source": "the ANVIL's front face at x = 0, half-way up the anvil body (his chest emblem; "
                                          "s3_valdris_landmarks.py)"}
diag["chest_sigil"] = LM["sockets"]["chest_sigil"]

# ---- 3. extra bones ---------------------------------------------------------------------------------------------------
extra = []
P3 = lambda k: np.array(R.point(LM, k))  # noqa: E731


def add(name, parent, head, tail):
    extra.append([name, parent, [round(float(v), 5) for v in head], [round(float(v), 5) for v in tail]])


def along(a, b):
    d = P3(b) - P3(a)
    return d / np.linalg.norm(d)


H = CFG["helpers"]
for s, sx in (("L", 1.0), ("R", -1.0)):
    m = np.array([sx, 1.0, 1.0])
    piv = np.array(H["pauldron"]["pivot"]) * m
    add("x_pauldron_" + s, "clavicle_" + s, piv, piv + along("shoulder_" + s, "elbow_" + s) * H["pauldron"]["length"])
    add("x_elbow_" + s, "upperarm_" + s, P3("elbow_" + s), P3("elbow_" + s) + along("elbow_" + s, "wrist_" + s) * H["elbow"]["length"])
    add("x_knee_" + s, "thigh_" + s, P3("knee_" + s), P3("knee_" + s) + along("knee_" + s, "ankle_" + s) * H["knee"]["length"])
    piv = np.array(H["tasset"]["pivot"]) * m
    add("x_tasset_" + s, "pelvis", piv, piv + along("hip_" + s, "knee_" + s) * H["tasset"]["length"])
add("x_fauld_01", "pelvis", H["fauld"]["head"], H["fauld"]["tail"])


def chain(prefix, parent, pts):
    """A chain of len(pts) - 1 bones prefix_01.. through the points."""
    par = parent
    for i in range(len(pts) - 1):
        name = "%s_%02d" % (prefix, i + 1)
        add(name, par, pts[i], pts[i + 1])
        par = name


# the cape: points on the mid-surface of the stage-2 rows (z, half_width, y_centre, y_side)
rows = np.array(PARTS_CFG["cape"]["rows"], dtype=np.float64)[::-1]       # ascending z for np.interp
cthick = PARTS_CFG["cape"]["thick"]
cc = CFG["cape"]
cape_pts = {}
for u, nm in zip(cc["columns_u"], cc["names"]):
    pts = []
    for z in cc["joints_z"]:
        hw = np.interp(z, rows[:, 0], rows[:, 1])
        yc = np.interp(z, rows[:, 0], rows[:, 2])
        ys = np.interp(z, rows[:, 0], rows[:, 3])
        pts.append(np.array([u * hw, ys + (yc - ys) * (1 - u * u) + 0.5 * cthick, z]))
    cape_pts[nm] = pts
    chain("x_cape_" + nm, "spine_03", pts)
lo = PARTS_CFG["loin"]
lc = CFG["loin"]
for u, nm in zip(lc["columns_u"], lc["names"]):
    pts = []
    for z in lc["joints_z"]:
        f = (lo["z"][0] - z) / (lo["z"][0] - lo["z"][1])
        hw = lo["half_width"][0] + (lo["half_width"][1] - lo["half_width"][0]) * f
        y = lo["y"][0] + (lo["y"][1] - lo["y"][0]) * f + 0.02 * (1 - u * u) * f
        pts.append(np.array([u * hw, y - 0.5 * lo["thick"], z]))
    chain("x_loin_" + nm, "pelvis", pts)
# the braids: root (stage2_parts.json beard.braids) -> between plait lobes 2 and 3 -> the bottom of the cap
beard = bpy.data.objects["BEARD"]
bco = world_co(beard)
bp = piece_vertices(beard)
bb = PARTS_CFG["beard"]["braids"]
braid_pts = {}
for k in range(5):
    lobes = sorted(bp["BRAID%d_LOBE" % (k + 1)], key=lambda idx: -bco[idx, 2].mean())
    cap = np.concatenate(bp["BRAID%d_CAP" % (k + 1)])
    root = np.array([bb["x"][k], bb["y_root"], bb["root_z"][k]])
    mid = 0.5 * (bco[lobes[1]].mean(0) + bco[lobes[2]].mean(0))
    low = bco[cap]
    end = low[low[:, 2] < low[:, 2].min() + 0.01].mean(0)
    braid_pts[k + 1] = [root, mid, end]
    chain("x_beard_%d" % (k + 1), "head", [root, mid, end])
LM["extra_bones"] = extra
diag["extra_bones"] = {"count": len(extra), "helpers_driven": [e[0] for e in extra if e[0].split("_")[1] in ("pauldron", "elbow", "knee", "tasset", "fauld")],
                       "chains": {"cape": "5 x 5", "loin": "3 x 3", "beard": "5 x 2"}}
meta = LM.get("_meta", {})
meta["generator"] = "tools/blender/gf_hero/s3_landmarks.py (shared) + tools/blender/gf_hero/s3_valdris_landmarks.py"
meta["inputs_valdris"] = {rel(p): "read" for p in (os.path.join(P["A"], "stage2_parts.json"), os.path.join(P["A"], "reports", "stage2", "parts.json"), P["skin_cfg"])}
LM["_meta"] = meta
LM["_doc"] = LM["_doc"].replace("Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit",
                                "Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit, finished by "
                                "s3_valdris_landmarks.py (lame finger joints, chest_sigil on the anvil, x_ extras)")
problems = R.validate_landmarks(LM)
if problems:
    raise SystemExit("landmark problems: " + "; ".join(problems))
write_json(P["landmarks"], LM)
lp = os.path.join(P["S3"], "landmarks.json")
d = read_json(lp)
d["valdris"] = diag
write_json(lp, d)
log("valdris landmarks OK: %d extras" % len(extra))
