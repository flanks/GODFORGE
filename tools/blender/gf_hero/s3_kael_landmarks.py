"""Stage 3, Kael: finish his GF_Hero_v1 landmark file after the shared s3_landmarks.py (headless Blender).

  blender -b art/characters/kael/production/kael_stage2.blend -P tools/blender/gf_hero/s3_kael_landmarks.py

The shared step derives every contract joint and socket from the stage-2 fit (Kael is an unarmoured MakeHuman hm08
body, so its joints, fingers and hand frames stand as they are). This step only adds his x_ extras
(stage3_skin.json "rig"), placed on the stage-2 mesh itself:

  x_coat_<col>_01..04   six chains down the duster's skirt (LF, LS, LB, RB, RS, RF), parent pelvis: at each column's
                        theta the joints sit on the skirt's mid-surface (mean radius of the skirt vertices round that
                        angle and height), the last joint at the column's hem;
  x_loin_{R,C,L}_01..03 three chains across the loin cloth, parent pelvis, on the cloth's mid-surface;
  x_wisp_<n>_01..03     one chain per ghost-flame tatter (WISP_1..5), from the hem to the tip along the tatter's centre
                        line, parent the last bone of the nearest coat column.

Then gf_hero_rig.validate_landmarks, work/kael_landmarks.json (committed with git add -f) and a "kael" section in
reports/stage3/landmarks.json.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import get_co, log, read_json, rel, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

KEY = "kael"
P = hero_paths(KEY)
LM = read_json(P["landmarks"])
CFG = read_json(P["skin_cfg"])["rig"]
PARTS_REP = read_json(os.path.join(P["A"], "reports", "stage2", "parts.json"))
PIECE_NAME = {p["id"]: p["name"] for p in PARTS_REP["piece_table"]}
diag = {"generated_by": "tools/blender/gf_hero/s3_kael_landmarks.py (after the shared s3_landmarks.py)"}


def world_co(ob):
    mw = np.array(ob.matrix_world)
    return get_co(ob.data) @ mw[:3, :3].T + mw[:3, 3]


def vertex_piece(ob):
    """Piece name per vertex, from the face attribute gf_piece (reports/stage2/parts.json piece_table)."""
    me = ob.data
    fp = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["gf_piece"].data.foreach_get("value", fp)
    vp = np.full(len(me.vertices), -1)
    for poly, pid in zip(me.polygons, fp):
        vp[list(poly.vertices)] = pid
    return np.array([PIECE_NAME.get(int(i), "") for i in vp])


def theta_of(co):
    return np.degrees(np.arctan2(co[:, 0], -co[:, 1])) % 360.0


def dtheta(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


extra = []


def add(name, parent, head, tail):
    extra.append([name, parent, [round(float(v), 5) for v in head], [round(float(v), 5) for v in tail]])


def chain(prefix, parent, pts):
    par = parent
    for i in range(len(pts) - 1):
        name = "%s_%02d" % (prefix, i + 1)
        add(name, par, pts[i], pts[i + 1])
        par = name


# ---- the coat skirt ---------------------------------------------------------------------------------------------------
coat = bpy.data.objects["COAT"]
cco = world_co(coat)
cpc = vertex_piece(coat)
sk = np.isin(cpc, ["COAT_SKIRT_L", "COAT_SKIRT_R"])
sco = cco[sk]
sth = theta_of(sco)
srad = np.hypot(sco[:, 0], sco[:, 1])
cc = CFG["coat"]
col_info = {}
for nm, th in zip(cc["names"], cc["theta_deg"]):
    near = np.abs(dtheta(sth, th)) < 6.0
    if near.sum() < 20:
        raise SystemExit("coat column %s: only %d skirt vertices near theta %.0f" % (nm, int(near.sum()), th))
    z_hem = max(cc["hem_floor_z"], float(np.percentile(sco[near, 2], 3)))
    pts = []
    for z in list(cc["joints_z"]) + [z_hem]:
        m = near & (np.abs(sco[:, 2] - z) < 0.035)
        if m.sum() < 4:
            m = near & (np.abs(sco[:, 2] - z) < 0.07)
        r = float(srad[m].mean())
        t = math.radians(th)
        pts.append(np.array([math.sin(t) * r, -math.cos(t) * r, z]))
    chain("x_coat_" + nm, "pelvis", pts)
    col_info[nm] = {"theta_deg": th, "hem_z": round(z_hem, 4), "radius_m": [round(float(np.hypot(p[0], p[1])), 4) for p in pts]}
diag["coat"] = col_info
log("coat chains:", {k: (v["hem_z"], v["radius_m"]) for k, v in col_info.items()})

# ---- the loin cloth ---------------------------------------------------------------------------------------------------
loin = bpy.data.objects["LOINCLOTH"]
lco = world_co(loin)
p2 = read_json(os.path.join(P["A"], "stage2_parts.json"))["loin"]
lc = CFG["loin"]


def loin_hw(z):
    f = np.clip((p2["z"][0] - z) / (p2["z"][0] - p2["z"][1]), 0.0, 1.0)
    return p2["half_width"][0] + (p2["half_width"][1] - p2["half_width"][0]) * f


for u, nm in zip(lc["columns_u"], lc["names"]):
    pts = []
    for z in lc["joints_z"]:
        x = u * 0.8 * loin_hw(z)
        for tol in (0.025, 0.05, 0.1):
            m = (np.abs(lco[:, 0] - x) < tol) & (np.abs(lco[:, 2] - z) < tol)
            if m.sum() >= 4:
                break
        pts.append(np.array([x, float(lco[m, 1].mean()), z]))
    chain("x_loin_" + nm, "pelvis", pts)

# ---- the ghost-flame tatters --------------------------------------------------------------------------------------------
wisps = bpy.data.objects["WISPS"]
wco = world_co(wisps)
wpc = vertex_piece(wisps)
winfo = {}
nb = CFG["wisps"]["bones"]
witems = read_json(os.path.join(P["A"], "stage2_parts.json"))["wisps"]["items"]
for k in range(1, 6):
    m = wpc == "WISP_%d" % k
    pw = wco[m]
    th = float(np.degrees(np.arctan2(pw[:, 0].mean(), -pw[:, 1].mean())) % 360.0)
    # the tatter's own geometry: it starts `root` above the local hem (s2_kael_parts.py), so the hem is its top minus root
    z_hem = float(pw[:, 2].max()) - witems[k - 1]["root"]
    below = pw[pw[:, 2] < z_hem + 0.01]
    z_tip = float(below[:, 2].min())
    kn = max(8, len(below) // 10)
    pts = []
    for j in range(nb + 1):
        z = z_hem + (z_tip - z_hem) * j / nb
        sel = below[np.argsort(np.abs(below[:, 2] - z))[:kn]]      # the slab of vertices nearest that height
        pts.append(sel.mean(0))
    if not np.isfinite(np.array(pts)).all():
        raise SystemExit("WISP_%d: no centre line" % k)
    col = min(zip(cc["names"], cc["theta_deg"]), key=lambda nt: abs(dtheta(th, nt[1])))[0]
    chain("x_wisp_%d" % k, "x_coat_%s_%02d" % (col, len(cc["joints_z"])), pts)
    winfo["WISP_%d" % k] = {"theta_deg": round(th, 1), "hem_z": round(z_hem, 4), "tip_z": round(z_tip, 4), "parent_column": col}
diag["wisps"] = winfo

LM["extra_bones"] = extra
diag["extra_bones"] = {"count": len(extra), "chains": {"coat": "6 x 4", "loin": "3 x 3", "wisps": "5 x %d" % nb}}
meta = LM.get("_meta", {})
meta["generator"] = "tools/blender/gf_hero/s3_landmarks.py (shared) + tools/blender/gf_hero/s3_kael_landmarks.py"
meta["inputs_kael"] = {rel(p): "read" for p in (os.path.join(P["A"], "stage2_parts.json"), os.path.join(P["A"], "reports", "stage2", "parts.json"), P["skin_cfg"])}
LM["_meta"] = meta
LM["_doc"] = LM["_doc"].replace("Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit",
                                "Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit, finished by "
                                "s3_kael_landmarks.py (the x_ cloth chains on the coat, loin cloth and tatters)")
problems = R.validate_landmarks(LM)
if problems:
    raise SystemExit("landmark problems: " + "; ".join(problems))
write_json(P["landmarks"], LM)
lp = os.path.join(P["S3"], "landmarks.json")
d = read_json(lp)
d["kael"] = diag
write_json(lp, d)
log("kael landmarks OK: %d extras" % len(extra))
