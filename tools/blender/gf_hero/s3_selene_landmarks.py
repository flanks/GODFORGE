"""Stage 3, Selene: finish her GF_Hero_v1 landmark file after the shared s3_landmarks.py (headless Blender).

  blender -b art/characters/selene/production/selene_stage2.blend -P tools/blender/gf_hero/s3_selene_landmarks.py

The shared step derives every contract joint from the stage-2 fit and the sockets from the stage-2 hand frames. Her body
is the plain MakeHuman hand (fingerless gauntlets), so the shared finger joints stand. Two things are hers (the landmark
JSON is the whole contract, docs/art/GF_HERO_SKELETON.md section 5):

  1. chest_sigil: her chest emblem is the COLLAR GEM (the faceted diamond at the base of the high collar), not the
     bodysuit surface the shared step ray-casts. The socket sits on the gem's front face at x = 0, half-way up the gem,
     forward = that face's normal.
  2. extra_bones (stage3_skin.json "rig"):
       x_crown_01..06   one per storm-crystal shard (reports/stage2/parts.json CROWN_SHARD_01..06), parent head_top. The
                        head sits on the head's vertical axis at the shard's height and the tail on the shard's centre,
                        so a turn about the bone's local X orbits the shard round the head (the ultimate's slow spin), a
                        turn about its local Z bobs it (an arc), and about its own Y it spins in place. Clips may only
                        rotate joints (validate_glb: only the pelvis translates), which is why the pivot is off the shard.
       cloth chains     one chain down the middle column (u = 0.5) of each stage-2 cloth sheet, joints at even v stations
                        of the sheet's own (u, v) grid (the gf_mask colour: R = v, G = u), on the sheet's mid-surface:
                        x_cape_{L,R}_01..04 and x_mantle_{L,R}_01..02 (parent upperarm, the armlet the capes hang under),
                        x_panel_{L,R}_01..03, x_tabard_01..03, x_back_01..03 (parent pelvis).
       x_knee_L/R       driven helpers (parent thigh, the shin's rest direction): the knee cop and fin turn half the bend.

Then gf_hero_rig.validate_landmarks, work/selene_landmarks.json (committed with git add -f) and a "selene" section in
reports/stage3/landmarks.json.
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

KEY = "selene"
P = hero_paths(KEY)
LM = read_json(P["landmarks"])
CFG = read_json(P["skin_cfg"])["rig"]
PARTS_REP = read_json(os.path.join(P["A"], "reports", "stage2", "parts.json"))
PIECE_NAME = {p["id"]: p["name"] for p in PARTS_REP["piece_table"]}
diag = {"generated_by": "tools/blender/gf_hero/s3_selene_landmarks.py (after the shared s3_landmarks.py)"}


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


def uv_mask(ob):
    a = ob.data.attributes["gf_mask"]
    col = np.empty(len(a.data) * 4, dtype=np.float64)
    a.data.foreach_get("color", col)
    col = col.reshape(-1, 4)
    return col[:, 1], col[:, 0]          # u (G), v (R)


# ---- 1. chest_sigil on the collar gem ---------------------------------------------------------------------------------
collar = bpy.data.objects["COLLAR"]
cco = world_co(collar)
gem = piece_vertices(collar)["COLLAR_GEM"][0]
z_sig = round(float(0.5 * (cco[gem, 2].min() + cco[gem, 2].max())), 4)
polys = [tuple(p.vertices) for p in collar.data.polygons if set(p.vertices) <= set(gem.tolist())]
bvh = BVHTree.FromPolygons([tuple(c) for c in cco], polys)
hit, nrm, _fi, _d = bvh.ray_cast(Vector((0.0, -2.0, z_sig)), Vector((0.0, 1.0, 0.0)), 4.0)
if hit is None:
    raise SystemExit("chest_sigil: no collar-gem surface at z = %.3f" % z_sig)
nrm = Vector((0.0, nrm.y, nrm.z)).normalized()
if nrm.y > 0:
    nrm = -nrm
up = (Vector((0, 0, 1)) - nrm * nrm.z).normalized()
LM["sockets"]["chest_sigil"] = {"origin": [0.0, round(hit.y, 5), z_sig], "forward": [0.0, round(nrm.y, 5), round(nrm.z, 5)],
                                "up": [0.0, round(up.y, 5), round(up.z, 5)],
                                "source": "the COLLAR_GEM's front face at x = 0, half-way up the gem (her chest emblem; "
                                          "s3_selene_landmarks.py)"}
diag["chest_sigil"] = LM["sockets"]["chest_sigil"]
log("chest_sigil on the collar gem at z %.3f, y %.3f" % (z_sig, hit.y))

# ---- 2. extra bones ---------------------------------------------------------------------------------------------------
extra = []


def add(name, parent, head, tail):
    extra.append([name, parent, [round(float(v), 5) for v in head], [round(float(v), 5) for v in tail]])


# the crown: pivot on the head's vertical axis at the shard's height, tail on the shard's centre
crown = bpy.data.objects["CROWN"]
kco = world_co(crown)
kp = piece_vertices(crown)
axis_y = float(LM["sockets"]["head_top"]["origin"][1])
shards = {}
for k in range(1, 7):
    nm = "CROWN_SHARD_%02d" % k
    idx = np.concatenate(kp[nm])
    c = kco[idx].mean(0)
    add("x_crown_%02d" % k, "head_top", (0.0, axis_y, c[2]), c)
    shards[nm] = {"centre": np.round(c, 4).tolist(), "radius_m": round(float(np.hypot(c[0], c[1] - axis_y)), 4),
                  "vertices": int(len(idx))}
diag["crown"] = shards


def centreline(ob, idx, nbones, u_band=0.2):
    """Chain joints on the sheet's mid-surface down its middle column: v = 0, 1/n, ..., 1."""
    u, v = uv_mask(ob)
    co = world_co(ob)
    u, v, co = u[idx], v[idx], co[idx]
    pts = []
    dv = 0.5 / nbones
    for j in range(nbones + 1):
        vj = j / float(nbones)
        m = (np.abs(v - vj) <= min(dv, 0.06)) & (np.abs(u - 0.5) <= u_band)
        if m.sum() < 4:
            m = np.argsort(np.abs(v - vj) + np.abs(u - 0.5))[:8]
        pts.append(co[m].mean(0))
    return pts


def chain(prefix, parent, pts):
    par = parent
    for i in range(len(pts) - 1):
        name = "%s_%02d" % (prefix, i + 1)
        add(name, par, pts[i], pts[i + 1])
        par = name


chains_diag = {}
for obname, piece, prefix, parent in CFG["chains"]:
    ob = bpy.data.objects[obname]
    comps = piece_vertices(ob)[piece]
    idx = np.concatenate(comps)
    n = CFG["chain_bones"][prefix.split("_")[1]]
    pts = centreline(ob, idx, n)
    chain(prefix, parent, pts)
    chains_diag[prefix] = {"object": obname, "piece": piece, "parent": parent, "bones": n,
                           "points": [np.round(p, 4).tolist() for p in pts]}
diag["chains"] = chains_diag

# the driven knee helpers (x_knee_L/R: the knee cop and fin turn half the knee bend)
P3 = lambda k: np.array(R.point(LM, k))  # noqa: E731
kl = CFG["helpers"]["knee"]["length"]
for s in ("L", "R"):
    d = P3("ankle_" + s) - P3("knee_" + s)
    add("x_knee_" + s, "thigh_" + s, P3("knee_" + s), P3("knee_" + s) + d / np.linalg.norm(d) * kl)

LM["extra_bones"] = extra
diag["extra_bones"] = {"count": len(extra), "crown": 6, "knee_helpers": 2, "cloth": len(extra) - 8}
meta = LM.get("_meta", {})
meta["generator"] = "tools/blender/gf_hero/s3_landmarks.py (shared) + tools/blender/gf_hero/s3_selene_landmarks.py"
meta["inputs_selene"] = {rel(p): "read" for p in (os.path.join(P["A"], "reports", "stage2", "parts.json"), P["skin_cfg"])}
LM["_meta"] = meta
LM["_doc"] = LM["_doc"].replace("Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit",
                                "Generated by tools/blender/gf_hero/s3_landmarks.py from the stage-2 fit, finished by "
                                "s3_selene_landmarks.py (chest_sigil on the collar gem, x_ crown and cloth extras)")
problems = R.validate_landmarks(LM)
if problems:
    raise SystemExit("landmark problems: " + "; ".join(problems))
write_json(P["landmarks"], LM)
lp = os.path.join(P["S3"], "landmarks.json")
d = read_json(lp)
d["selene"] = diag
write_json(lp, d)
log("selene landmarks OK: %d extras" % len(extra))
