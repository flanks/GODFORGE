"""Stage 2, Valdris: the armour, beard and cape around the conformed under-suit body (s2_valdris_body.py).

Built procedurally from art/characters/valdris/stage2_parts.json (every number measured on the resolved hero front
and the stage-1 blockout; see its _doc keys), never copied from the blockout. Every part is closed; rigid pieces are
separate connected pieces so stage 3 can weight each one 100 % to one bone (the suggested bone of every piece is in
the report, and the face attribute gf_piece indexes it). Paint zones: s2_valdris_geom.ZONES (face material index).

Objects:
  BODY        the under-suit (mail), skin on the head and neck, the leather glove, the eyeballs (eye)
  BEARD       lofted beard block, moustache, five braids with gold rings and steel caps
  PAULDRONS   main blocks, ember slots, two lower lames, upright plates, rivets (both sides)
  ANVIL       top slab (flat top face, square heel on his right, horn on his left) over the waisted body with feet
  CUIRASS     shingled chest / ribs / belly bands, the belt with its buckle, the gorget
  HIPS        tassets (two lames per side) and the chevron fauld
  LOINCLOTH   war-red cloth behind the fauld with tattered strips
  ARMS        rerebraces with gold bands, couters with cops, vambraces with two gold cuffs, gauntlet cuffs
  GAUNTLETS   back-of-hand plates, knuckle guards with studs, one lame per finger phalanx
  LEGS        cuisses, poleyns (knee cops), greaves
  SABATONS    blocky boots: foot shell with a gold ankle band and a sole, two-lame toe caps
  CAPE        the cape (grid with folds and a tattered hem) and the high collar behind the head

  blender -b -P tools/blender/gf_hero/s2_valdris_parts.py -- <body.blend> <retopo_start.blend> <parts.json> \
          <fit.json> <mh_landmarks.json> <out.blend> [--report <json>]
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import s2_valdris_geom as VG  # noqa: E402
from s2lib import (connected_parts, get_co, get_collection, hex_rgb, log, mesh_stats, opt, read_json, save_blend,  # noqa: E402
                   script_args, srgb_to_linear, write_json)

argv = script_args(__doc__)
if len(argv) < 6:
    raise SystemExit(__doc__)
BODY, REF, CFG, FIT, MHLM, OUT = (os.path.abspath(a) for a in argv[:6])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(CFG)
fit = read_json(FIT)
mh = read_json(MHLM)
rng = random.Random(cfg.get("seed", 11))
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
dg = bpy.context.evaluated_depsgraph_get()
body_bvh = BVHTree.FromObject(body, dg)
body_co = get_co(body.data)
report = {"parts": {}, "pieces": {}}
col = get_collection("VALDRIS_stage2")
if body.name not in col.objects:
    col.objects.link(body)
Zn = VG.Z


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---- zone preview materials (palette base tones; the texture step replaces them with the atlas) --------------
pal = {s["key"]: s["tones"] for s in read_json(os.path.join(os.path.dirname(CFG), "palette.json"))["swatches"]}
zone_hex = {"skin": "#7C5A4A", "beard": "#48413C", "eye": "#F8AA5D", "plate": "#312C27", "iron": "#1E1A17",
            "gold": "#CF9F66", "seam": "#FF6B1A", "cape": "#7A1F1F", "mail": "#2A2624", "leather": "#3A2A22",
            "steel": "#6F6862", "anvil": "#3A3430"}
mats = []
for zname in VG.ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    c = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    m.diffuse_color = c
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = c
    if zname in ("eye", "seam"):
        bsdf.inputs["Emission Color"].default_value = c
        bsdf.inputs["Emission Strength"].default_value = 3.0
    mats.append(m)

PIECE_LAYER = "gf_piece"
piece_table = []


def new_bm():
    bm = bmesh.new()
    VG.ensure_mask(bm)
    bm.faces.layers.int.new(PIECE_LAYER)
    return bm


def reg(bm, faces, name, bone):
    """Register the faces just built as one rigid piece (index into piece_table)."""
    lay = bm.faces.layers.int.get(PIECE_LAYER)
    pid = len(piece_table)
    for f in faces:
        if f.is_valid:
            f[lay] = pid
    piece_table.append({"id": pid, "name": name, "bone": bone})
    return pid


def build_mirrored(builder, name, bone_fmt):
    """builder(bm, sd) builds the LEFT (sd=+1) piece set into bm; the right is its x-mirror."""
    bm_l = new_bm()
    builder(bm_l, 1)
    return bm_l


def finish(bm, name, mirror_from=None):
    """Mirror (optional), clean, make an object with the zone materials. mirror_from: bmesh of left pieces to
    mirror in; their piece ids are duplicated with _L -> _R names."""
    if mirror_from is not None:
        lay_s = mirror_from.faces.layers.int.get(PIECE_LAYER)
        lay_d = bm.faces.layers.int.get(PIECE_LAYER)
        # copy left pieces as they are, then their mirror with new piece ids
        mask_s = mirror_from.verts.layers.float_color.get(VG.G0.MASK_LAYER)
        mask_d = VG.ensure_mask(bm)
        idmap = {}
        for side in (1, -1):
            vmap = {}
            for v in mirror_from.verts:
                nv_ = bm.verts.new((v.co.x * side, v.co.y, v.co.z))
                if mask_s is not None:
                    nv_[mask_d] = v[mask_s]
                vmap[v] = nv_
            for f in mirror_from.faces:
                vs = [vmap[v] for v in (f.verts if side > 0 else reversed(f.verts))]
                g = bm.faces.new(vs)
                g.material_index = f.material_index
                pid = f[lay_s]
                if side < 0:
                    if pid not in idmap:
                        src = piece_table[pid]
                        nid = len(piece_table)
                        piece_table.append({"id": nid, "name": src["name"].replace("_L", "_R"),
                                            "bone": src["bone"].replace("_L", "_R").replace("_l", "_r")})
                        idmap[pid] = nid
                    pid = idmap[pid]
                g[lay_d] = pid
        mirror_from.free()
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lay = bm.verts.layers.float_color.get(VG.G0.MASK_LAYER)
    for v in bm.verts:
        if v[lay][3] < 0.5:
            v[lay] = (0.5, 0.5, 0.5, 1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    for m in mats:
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = False
    col.objects.link(ob)
    st = mesh_stats(ob)
    report["parts"][name] = st
    pl = me.attributes.get(PIECE_LAYER)
    if pl is not None:
        ids = np.empty(len(me.polygons), dtype=np.int32)
        pl.data.foreach_get("value", ids)
        report["pieces"][name] = sorted({piece_table[i]["name"] + " -> " + piece_table[i]["bone"] for i in set(ids.tolist())})
    log("%-11s %6d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d" % (
        name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"]))
    return ob


# ==============================================================================================================
# body sampling
# ==============================================================================================================
tor = fit["conform"]["torso"]
TAB = np.array(tor["slabs"], dtype=np.float64)


def torso_cy(z):
    return float((np.interp(z, TAB[:, 0], TAB[:, 2]) + np.interp(z, TAB[:, 0], TAB[:, 3])) / 2)


def ray_out(origin, d, maxd=0.8):
    loc, n, i, dist = body_bvh.ray_cast(Vector(origin), Vector(d), maxd)
    return dist if loc is not None else None


def body_radius_grid(axis_fn, thetas, ss, frame_fn, maxd=0.8, fallback=None):
    """R[s, theta]: first body hit from the axis point outward. frame_fn(s) -> (C, U, V): theta measured from U
    toward V. Missing hits: fallback(s, theta) or the row median."""
    R = np.full((len(ss), len(thetas)), np.nan)
    for i, s in enumerate(ss):
        C, U, V = frame_fn(s)
        for j, t in enumerate(thetas):
            d = U * math.cos(t) + V * math.sin(t)
            r = ray_out(C, d, maxd)
            if r is not None:
                R[i, j] = r
            elif fallback is not None:
                R[i, j] = fallback(s, t)
    for i in range(len(ss)):
        row = R[i]
        if np.isnan(row).all():
            R[i] = np.nanmedian(R) if not np.isnan(R).all() else 0.1
        else:
            R[i] = np.where(np.isnan(row), np.nanmedian(row), row)
    return R


def gauss_rows(R, sig_s, sig_t, periodic_t=True):
    out = R.copy()
    for ax, sig, per in ((0, sig_s, False), (1, sig_t, periodic_t)):
        if sig <= 0:
            continue
        r = max(1, int(3 * sig))
        w = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        w /= w.sum()
        acc = np.zeros_like(out)
        n = out.shape[ax]
        for wk, d in zip(w, range(-r, r + 1)):
            if per:
                acc += wk * np.roll(out, d, axis=ax)
            else:
                acc += wk * np.take(out, np.clip(np.arange(n) + d, 0, n - 1), axis=ax)
        out = acc
    return out


# ---- TPS replica: MakeHuman joints -> this body (finger joints for the gauntlet lames) ------------------------
def mh_point(key):
    if "." in key:
        b, e = key.split(".")
        return mh["joints"][b][e]
    return mh[key]


pairs = []
for key, dst in fit["landmarks"].items():
    if key.startswith("_"):
        continue
    pairs.append((mh_point(key), dst))
    if "_l" in key:
        q = list(dst)
        q[0] = -q[0]
        pairs.append((mh_point(key.replace("_l", "_r")), q))
S_ = np.array([p[0] for p in pairs])
D_ = np.array([p[1] for p in pairs])
n_ = len(S_)
K_ = np.linalg.norm(S_[:, None] - S_[None], axis=2)
P_ = np.hstack([np.ones((n_, 1)), S_])
A_ = np.zeros((n_ + 4, n_ + 4))
A_[:n_, :n_] = K_ + 1e-6 * np.eye(n_)
A_[:n_, n_:] = P_
A_[n_:, :n_] = P_.T
rhs = np.zeros((n_ + 4, 3))
rhs[:n_] = D_
sol = np.linalg.solve(A_, rhs)


def tps(X):
    X = np.atleast_2d(X)
    U = np.linalg.norm(X[:, None] - S_[None], axis=2)
    return U @ sol[:n_] + np.hstack([np.ones((len(X), 1)), X]) @ sol[n_:]


lr = fit["fit"]["limb_radial"]


def hand_warp(p):
    """The limb_radial hand scale about the arm axis (applied past hand_from_abs_x by s2_body_fit.py)."""
    p = np.array(p, dtype=np.float64)
    k = np.clip((abs(p[0]) - lr["hand_from_abs_x"]) / 0.03, 0, 1)
    s = 1 + (lr["hand_scale"] - 1) * k
    p[1] = lr["axis_y"] + (p[1] - lr["axis_y"]) * s
    p[2] = lr["axis_z"] + (p[2] - lr["axis_z"]) * s
    return p


def joint(name):
    return hand_warp(tps(np.array(mh["joints"][name]["head"]))[0]), hand_warp(tps(np.array(mh["joints"][name]["tail"]))[0])


# ==============================================================================================================
# CUIRASS: shingled bands, belt + buckle, gorget
# ==============================================================================================================
tc = cfg["torso"]
NU = tc["u"]
TH = np.arange(NU) * 2 * math.pi / NU                # 0 = front (-Y), pi/2 = his left (+X)


def tdir(t):
    return np.array([math.sin(t), -math.cos(t), 0.0])


def torso_frame(z):
    return (np.array([0.0, torso_cy(z), z]), np.array([0.0, -1.0, 0.0]), np.array([1.0, 0.0, 0.0]))


ZS_T = np.arange(1.14, 2.1, 0.02)
R_T = body_radius_grid(None, TH, ZS_T, torso_frame, maxd=0.7)
# the arm roots: above the armpit the side rays exit through the barrel into the arm; clamp to the barrel table
hw_tab = np.interp(ZS_T, TAB[:, 0], TAB[:, 1])
R_T = np.minimum(R_T, (hw_tab + 0.02)[:, None] * np.ones((1, NU)) / np.maximum(np.abs(np.sin(TH))[None, :], 0.35))
R_T = gauss_rows(R_T, 1.5, 1.0)


def R_torso(t, z):
    zc = np.clip(z, ZS_T[0], ZS_T[-1])
    fz = (zc - ZS_T[0]) / 0.02
    i0 = int(min(max(math.floor(fz), 0), len(ZS_T) - 2))
    tz = fz - i0
    ft = (t % (2 * math.pi)) / (2 * math.pi / NU)
    j0 = int(math.floor(ft)) % NU
    j1 = (j0 + 1) % NU
    tt = ft - math.floor(ft)
    a = R_T[i0, j0] * (1 - tt) + R_T[i0, j1] * tt
    b = R_T[i0 + 1, j0] * (1 - tt) + R_T[i0 + 1, j1] * tt
    return a * (1 - tz) + b * tz


def band_z_top(b, t):
    c = abs(math.cos(t))
    if math.cos(t) >= 0:
        return b["z_top_side"] + (b["z_top_front"] - b["z_top_side"]) * c ** 0.7
    return b["z_top_side"] + (b["z_top_back"] - b["z_top_side"]) * c ** 0.7


bm = new_bm()
RIM = cfg.get("rim_m", 0.016)
for b in tc["bands"]:
    nrow = 6
    S = np.zeros((NU, nrow, 3))
    for i, t in enumerate(TH):
        zt = band_z_top(b, t)
        zr = VG.rim_rows(b["z_bottom"], zt, RIM, 2)
        for j, z in enumerate(zr):
            v = (z - b["z_bottom"]) / (zt - b["z_bottom"])
            r = R_torso(t, z) + b["offset"] + b["bulge"] * math.sin(math.pi * v) - (0.005 if j in (0, nrow - 1) else 0.0)
            C = np.array([0.0, torso_cy(z), z])
            S[i, j] = C + tdir(t) * r
    rows = list(range(nrow))
    zone = b.get("zone", "plate")

    def zf(i, j, b=b, zone=zone):
        if j == 0:
            return b["rim_bottom"]
        if j == len(rows) - 2:
            return b["rim_top"]
        return zone
    fs, vo, vi = VG.grid_solid(bm, S, b["thick"], zf, periodic_u=True,
                               out_ref=lambda p: np.array([p[0], p[1] - torso_cy(p[2]), 0.0]),
                               wall_zone=("iron", "iron", "iron", "iron"), rand=rng.random(), simple_inner=True)
    reg(bm, fs, b["name"], {"CHEST": "spine_03", "RIBS": "spine_02", "BELLY": "spine_01", "BELT": "pelvis"}[b["name"]])
# buckle: gold plate with an ember core at the belt front (shows in the notch between the anvil's feet)
bk = tc["buckle"]
belt = [b for b in tc["bands"] if b["name"] == "BELT"][0]
yb = torso_cy(bk["z"]) - (R_torso(0.0, bk["z"]) + belt["offset"] + belt["bulge"])
poly = [(-bk["half"][0], bk["z"] - bk["half"][1]), (bk["half"][0], bk["z"] - bk["half"][1]),
        (bk["half"][0], bk["z"] + bk["half"][1]), (-bk["half"][0], bk["z"] + bk["half"][1])]
fs = VG.prism(bm, poly, (0, yb, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), -0.01, bk["thick"], 0.008,
              {"front": "gold", "side": "gold", "chamfer": "gold", "back": "iron"}, rand=rng.random())
core = [(-bk["core"][0], bk["z"] - bk["core"][1]), (bk["core"][0], bk["z"] - bk["core"][1]),
        (bk["core"][0], bk["z"] + bk["core"][1]), (-bk["core"][0], bk["z"] + bk["core"][1])]
fs += VG.prism(bm, core, (0, yb, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0.0, bk["thick"] + 0.006, 0.006,
               {"front": "seam", "side": "gold", "chamfer": "seam", "back": "iron"}, rand=rng.random())
reg(bm, fs, "BUCKLE", "pelvis")
# gorget: two lames around the neck base (under the beard, framed by the pauldrons)
gc = tc["gorget"]
ZS_N = np.linspace(gc["z"][0], gc["z"][1], 8)


def neck_frame(z):
    return (np.array([0.0, -0.03, z]), np.array([0.0, -1.0, 0.0]), np.array([1.0, 0.0, 0.0]))


R_N = gauss_rows(body_radius_grid(None, TH, ZS_N, neck_frame, maxd=0.5), 1.0, 1.0)
zc_ = np.linspace(gc["z"][0], gc["z"][1], gc["lames"] + 1)
for k in range(gc["lames"]):
    z0, z1 = zc_[k] - 0.01, zc_[k + 1] + 0.012
    zr = VG.rim_rows(z0, z1, RIM, 0)
    rows = zr
    S = np.zeros((NU, len(rows), 3))
    for i, t in enumerate(TH):
        for j, z in enumerate(zr):
            v = (z - z0) / (z1 - z0)
            r = float(np.interp(z, ZS_N, R_N[:, i])) + gc["offset"] + 0.012 * (gc["lames"] - 1 - k) - (0.004 if v in (0, 1) else 0)
            S[i, j] = np.array([0.0, -0.03, z]) + tdir(t) * r
    fs, _, _ = VG.grid_solid(bm, S, gc["thick"], lambda i, j: "gold" if j == len(rows) - 2 else "plate", periodic_u=True,
                             out_ref=lambda p: np.array([p[0], p[1] + 0.03, 0.0]), rand=rng.random(), simple_inner=True)
    reg(bm, fs, "GORGET_%d" % (k + 1), "spine_03" if k == 0 else "neck_01")
finish(bm, "CUIRASS")

# ==============================================================================================================
# ANVIL
# ==============================================================================================================
ac = cfg["anvil"]
bm = new_bm()
hx = ac["horn_taper_from_x"]


def slab_depth(i, a, b):
    back, front = -ac["slab_depth"]["back"], -ac["slab_depth"]["front"]
    k = float(smoothstep(hx, 0.445, a))
    mid = (back + front) / 2
    return mid + (back - mid) * (1 - 0.82 * k), mid + (front - mid) * (1 - 0.82 * k)


# prism() extrudes along Nd = -Y from `back` to `front` distances; depths are distances along -Y (positive = forward)
def slab_depth_d(i, a, b):
    bk, fr = slab_depth(i, a, b)
    return -bk, -fr


fs = VG.prism(bm, ac["slab"], (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0, 0, ac["chamfer"],
              {"front": "anvil", "side": "anvil", "chamfer": "anvil", "back": "iron"}, depth_fn=slab_depth_d, rand=0.3)
reg(bm, fs, "ANVIL_SLAB", "spine_03")
bd = ac["body_depth"]


def body_depth_d(i, a, b):
    t = float(np.clip((b - 1.3) / 0.405, 0, 1))
    back = bd["back_bottom"] + (bd["back_top"] - bd["back_bottom"]) * t
    front = bd["front_bottom"] + (bd["front_top"] - bd["front_bottom"]) * t
    return back, front


fs = VG.prism(bm, ac["body"], (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0, 0, ac["chamfer"],
              {"front": "anvil", "side": "anvil", "chamfer": "anvil", "back": "iron"}, depth_fn=body_depth_d, rand=0.6)
reg(bm, fs, "ANVIL_BODY", "spine_03")
finish(bm, "ANVIL")

# ==============================================================================================================
# PAULDRONS
# ==============================================================================================================
pc = cfg["pauldron"]


def pauldron(bm, sd):
    # main block: profile in x-z, extruded along +Y (from y0 to y1); chamfer both ends (gold rims)
    prof = pc["block_profile"]
    n = len(prof)

    def side_zone(i):
        # top corner chamfers are gold; the rest plate
        a, b = prof[i], prof[(i + 1) % n]
        if (a[1] > 2.12 and b[1] > 2.12 and (abs(a[0] - b[0]) < 0.05)) or (i in (1, 4)):
            return "gold"
        return "plate"
    y0, y1 = pc["block_y"]
    fs = VG.prism(bm, prof, (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), y0, y1, pc["block_chamfer"],
                  {"front": "plate", "side": side_zone, "chamfer": "gold", "back": "plate", "chamfer_back": "gold"},
                  chamfer_back=pc["block_chamfer"], rand=rng.random())
    reg(bm, fs, "PAULDRON_BLOCK_L", "clavicle_l")
    # ember slot under the block
    sl = pc["slot"]
    poly = [(sl["x"][0], sl["z"][0]), (sl["x"][1] - sl["inset"], sl["z"][0]), (sl["x"][1] - sl["inset"], sl["z"][1]), (sl["x"][0], sl["z"][1])]
    fs = VG.prism(bm, poly, (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), sl["y"][0] + sl["inset"], sl["y"][1] - sl["inset"], 0.003,
                  {"front": "seam", "side": "seam", "chamfer": "seam", "back": "seam"}, rand=0.5)
    reg(bm, fs, "PAULDRON_SLOT_L", "clavicle_l")
    for k, lm in enumerate(pc["lames"]):
        fs = VG.prism(bm, lm["profile"], (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), lm["y"][0], lm["y"][1], lm["chamfer"],
                      {"front": "plate", "side": lambda i, L=lm: "gold" if i in L.get("gold_sides", ()) else "plate",
                       "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, chamfer_back=lm["chamfer"], rand=rng.random())
        reg(bm, fs, "PAULDRON_LAME%d_L" % (k + 1), "clavicle_l" if k == 0 else "upperarm_l")
    # upright plate: profile in y-z, extruded along x, tilted outward about the y axis
    up = pc["upright"]
    x0, x1 = up["x"]
    tilt = math.radians(up["tilt_deg"])
    Nd = np.array([math.cos(tilt), 0.0, -math.sin(tilt)])
    Bz = np.array([math.sin(tilt), 0.0, math.cos(tilt)])
    base_z = up["profile_yz"][0][1]
    prof_yz = [(p[0], p[1] - base_z) for p in up["profile_yz"]]
    O = np.array([x0, 0.0, base_z])
    fs = VG.prism(bm, prof_yz, O, (0, 1, 0), Bz, Nd, 0.0, x1 - x0, up["chamfer"],
                  {"front": "plate", "side": "plate", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"},
                  chamfer_back=up["chamfer"], rand=rng.random())
    reg(bm, fs, "PAULDRON_UPRIGHT_L", "clavicle_l")
    for r in pc["rivets"]:
        fs = VG.stud(bm, r[:3], r[3:], pc["rivet_r"], pc["rivet_r"] * 0.8, "gold", 6)
        reg(bm, fs, "PAULDRON_RIVET_L", "clavicle_l")


bml = new_bm()
pauldron(bml, 1)
finish(new_bm(), "PAULDRONS", mirror_from=bml)

# ==============================================================================================================
# ARMS: rerebrace, couter, vambrace, gauntlet cuff
# ==============================================================================================================
arm = cfg["arm"]
AY, AZ = arm["axis"]
TH_A = np.arange(28) * 2 * math.pi / 28


def arm_frame(x):
    # theta 0 = up (+Z), pi/2 = front (-Y) for the left arm
    return (np.array([x, AY, AZ]), np.array([0.0, 0.0, 1.0]), np.array([0.0, -1.0, 0.0]))


XS_A = np.arange(0.36, 1.0, 0.01)
R_A = gauss_rows(body_radius_grid(None, TH_A, XS_A, arm_frame, maxd=0.4), 1.0, 0.8)


def R_arm(t, x):
    xc = np.clip(x, XS_A[0], XS_A[-1])
    i = np.clip((xc - XS_A[0]) / 0.01, 0, len(XS_A) - 1.001)
    i0 = int(i)
    ti = i - i0
    ft = (t % (2 * math.pi)) / (2 * math.pi / len(TH_A))
    j0 = int(ft) % len(TH_A)
    j1 = (j0 + 1) % len(TH_A)
    tt = ft - int(ft)
    a = R_A[i0, j0] * (1 - tt) + R_A[i0, j1] * tt
    b = R_A[i0 + 1, j0] * (1 - tt) + R_A[i0 + 1, j1] * tt
    return a * (1 - ti) + b * ti


def arm_tube(bm, xs_rows, r_fn, n, thick, zone_fn, name, bone, exponent=2.0, rand=None):
    thetas = np.arange(n) * 2 * math.pi / n + math.pi / n
    S = np.zeros((n, len(xs_rows), 3))
    for i, t in enumerate(thetas):
        for j, x in enumerate(xs_rows):
            r = r_fn(t, x, j)
            k = superellipse_k(t, exponent)
            S[i, j] = np.array([x, AY - math.sin(t) * r * k, AZ + math.cos(t) * r * k])
    fs, _, _ = VG.grid_solid(bm, S, thick, zone_fn, periodic_u=True,
                             out_ref=lambda p: np.array([0.0, p[1] - AY, p[2] - AZ]), rand=rand, simple_inner=True)
    reg(bm, fs, name, bone)
    return fs


def superellipse_k(t, n):
    """Scale that turns a circle of radius r into a superellipse |y|^n+|z|^n=r^n (boxy-round), normalised so the
    diagonal stays at r * 0.97^... (keeps the area close)."""
    if n == 2.0:
        return 1.0
    return float(VG.superellipse(t, 1.0, 1.0, n)) * 0.96


def arms(bm, sd):
    rb = arm["rerebrace"]
    xs = [rb["x"][0], rb["x"][0] + 0.012, 0.47, rb["band"][0] - 0.004, rb["band"][0], rb["band"][1], rb["band"][1] + 0.004, rb["x"][1] - 0.012, rb["x"][1]]

    def r_rere(t, x, j):
        base = float(np.interp(x, [rb["x"][0], (rb["x"][0] + rb["x"][1]) / 2, rb["x"][1]], rb["r"]))
        base = max(base, R_arm(t, x) + 0.012)
        if rb["band"][0] <= x <= rb["band"][1]:
            base += rb["band_lift"]
        if j in (0, len(xs) - 1):
            base -= 0.006
        return base
    arm_tube(bm, xs, r_rere, rb["n"], rb["thick"], lambda i, j: "gold" if j == 4 else "plate",
             "REREBRACE_L", "upperarm_l", rb["exponent"], rng.random())
    cu = arm["couter"]
    xs = [cu["x"][0], cu["x"][0] + 0.01, (cu["x"][0] + cu["x"][1]) / 2, cu["x"][1] - 0.01, cu["x"][1]]

    def r_cout(t, x, j):
        base = max(cu["r"], R_arm(t, x) + 0.012) + 0.01 * math.sin(math.pi * (x - cu["x"][0]) / (cu["x"][1] - cu["x"][0]))
        return base - (0.006 if j in (0, len(xs) - 1) else 0)
    arm_tube(bm, xs, r_cout, cu["n"], cu["thick"], "plate", "COUTER_L", "lowerarm_l",
             2.2, rng.random())
    # the cop: an octagonal disc plate on the back of the elbow (+Y), gold rim, a central stud
    cp = cu["cop"]
    yc = AY + max(cu["r"], float(R_arm(-math.pi / 2, cp["x"]))) + cp["lift"] - 0.02
    poly = [(cp["x"] + math.cos(a) * cp["r"], AZ + math.sin(a) * cp["r"]) for a in np.arange(8) * math.pi / 4 + math.pi / 8]
    fs = VG.prism(bm, poly, (0, yc, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), -0.03, 0.012, 0.01,
                  {"front": "plate", "side": "gold", "chamfer": "gold", "back": "iron"}, rand=rng.random())
    fs += VG.stud(bm, (cp["x"], yc + 0.012, AZ), (0, 1, 0), 0.016, 0.014, "gold", 6)
    reg(bm, fs, "COUTER_COP_L", "lowerarm_l")
    va = arm["vambrace"]
    xs = [va["x"][0], va["x"][0] + 0.01]
    for c0, c1 in va["cuffs"]:
        xs += [c0 - 0.004, c0, c1, c1 + 0.004]
    xs += [va["x"][1] - 0.01, va["x"][1]]
    xs = sorted(set(round(x, 4) for x in xs))
    cuff_rows = [k for k, x in enumerate(xs) if any(c0 <= x < c1 for c0, c1 in va["cuffs"])]

    def r_vamb(t, x, j):
        base = R_arm(t, x) + va["clear"] + va["thick"]
        base = max(base, 0.074)
        if any(c0 <= x <= c1 for c0, c1 in va["cuffs"]):
            base += va["cuff_lift"]
        if j in (0, len(xs) - 1):
            base -= 0.005
        return min(base, va["max_r"])
    arm_tube(bm, xs, r_vamb, va["n"], va["thick"], lambda i, j: "gold" if j in cuff_rows else "plate", "VAMBRACE_L", "lowerarm_l",
             va["exponent"], rng.random())
    cf = arm["cuff"]
    xs = [cf["x"][0], cf["x"][0] + 0.008, (cf["x"][0] + cf["x"][1]) / 2, cf["x"][1] - 0.008, cf["x"][1]]

    def r_cuff(t, x, j):
        base = R_arm(t, x) + cf["clear"] + cf["thick"] + cf["flare"] * (x - cf["x"][0]) / (cf["x"][1] - cf["x"][0])
        base = max(base, 0.07)
        return min(base - (0.004 if j in (0, len(xs) - 1) else 0), cf["max_r"])
    arm_tube(bm, xs, r_cuff, cf["n"], cf["thick"], lambda i, j: "gold" if j == len(xs) - 2 else "plate", "GAUNTLET_CUFF_L", "hand_l",
             2.6, rng.random())


bml = new_bm()
arms(bml, 1)
finish(new_bm(), "ARMS", mirror_from=bml)

# ==============================================================================================================
# GAUNTLETS: back plate, knuckle guard, finger lames
# ==============================================================================================================
gc_ = cfg["gauntlet"]


def hand_top_z(x, y):
    """Top (+Z) surface of the body's hand at (x, y): a ray from above."""
    loc, n, i, d = body_bvh.ray_cast(Vector((x, y, AZ + 0.25)), Vector((0, 0, -1)), 0.3)
    return loc.z if loc is not None else None


def hand_y_extent(x):
    m = (np.abs(body_co[:, 0] - x) < 0.01) & (body_co[:, 2] > 1.6) & (body_co[:, 0] > 0)
    q = body_co[m]
    return (float(q[:, 1].min()), float(q[:, 1].max())) if len(q) else (-0.05, 0.05)


fingers = {"thumb": ["thumb_01_l", "thumb_02_l", "thumb_03_l"], "index": ["index_01_l", "index_02_l", "index_03_l"],
           "middle": ["middle_01_l", "middle_02_l", "middle_03_l"], "ring": ["ring_01_l", "ring_02_l", "ring_03_l"],
           "pinky": ["pinky_01_l", "pinky_02_l", "pinky_03_l"]}
finger_joints = {}
for fname, bones in fingers.items():
    finger_joints[fname] = [joint(b) for b in bones]
report["finger_joints_L"] = {f: [[round(float(v), 4) for v in h] + [round(float(v), 4) for v in t] for h, t in js]
                             for f, js in finger_joints.items()}


def gauntlets(bm, sd):
    bp = gc_["back_plate"]
    xs = np.linspace(bp["x"][0], bp["x"][1], 5)
    # y span of the back plate: the hand minus the thumb side
    ys_l, ys_h = [], []
    for x in xs:
        lo, hi = hand_y_extent(x)
        ys_l.append(max(lo, -0.058))
        ys_h.append(hi)
    NUy = 6
    S = np.zeros((NUy, len(xs), 3))
    for j, x in enumerate(xs):
        for i in range(NUy):
            f = i / (NUy - 1)
            y = ys_l[j] + (ys_h[j] - ys_l[j]) * (0.06 + 0.88 * f)
            zt = hand_top_z(x, y) or (AZ + 0.02)
            S[i, j] = (x, y, zt + bp["clear"] + bp["thick"] + 0.006 * math.sin(math.pi * f))
    fs, _, _ = VG.grid_solid(bm, S, bp["thick"], "plate",
                             out_ref=lambda p: np.array([0, 0, 1.0]), rand=rng.random(), lip=0.002)
    reg(bm, fs, "GAUNTLET_BACK_L", "hand_l")
    # knuckle guard: a raised bar across the knuckles with a gold stud per knuckle
    kn = gc_["knuckle"]
    xs = np.linspace(kn["x"][0], kn["x"][1], 3)
    S = np.zeros((NUy, len(xs), 3))
    for j, x in enumerate(xs):
        lo, hi = hand_y_extent(x)
        lo = max(lo, -0.062)
        for i in range(NUy):
            f = i / (NUy - 1)
            y = lo + (hi - lo) * (0.04 + 0.92 * f)
            zt = hand_top_z(x, y) or (AZ + 0.015)
            S[i, j] = (x, y, zt + kn["clear"] + kn["thick"] + 0.008 * math.sin(math.pi * j / (len(xs) - 1)))
    fs, _, _ = VG.grid_solid(bm, S, kn["thick"], "plate", out_ref=lambda p: np.array([0, 0, 1.0]), rand=rng.random(), lip=0.003)
    for fn in ("index", "middle", "ring", "pinky"):
        h, t = finger_joints[fn][0]
        zt = hand_top_z((kn["x"][0] + kn["x"][1]) / 2, h[1]) or AZ
        fs += VG.stud(bm, ((kn["x"][0] + kn["x"][1]) / 2, h[1], zt + kn["clear"] + kn["thick"] + 0.006), (0, 0, 1), 0.009, 0.008, "gold", 6)
    reg(bm, fs, "GAUNTLET_KNUCKLE_L", "hand_l")
    # finger lames: a curved plate over the top of each phalanx
    fc = gc_["finger"]
    span = math.radians(fc["span_deg"]) / 2
    for fn, js in finger_joints.items():
        for k, (h, t) in enumerate(js):
            h, t = np.array(h), np.array(t)
            if k == 0 and fn != "thumb":
                h = h + (t - h) * 0.45          # the knuckle guard covers the first part of the proximal phalanx
            d = t - h
            L = np.linalg.norm(d)
            d /= L
            up = np.array([0.0, 0.0, 1.0]) if fn != "thumb" else np.array([0.0, -0.4, 1.0])
            _, u, v = VG.frame_axes(d, up)
            s0 = -fc["gap"] if k > 0 else 0.0
            s1 = L + fc["overlap"]
            cols = [-span, 0.0, span]
            rows = [s0, (s0 + s1) / 2, s1]
            S = np.zeros((len(cols), len(rows), 3))
            for i, a in enumerate(cols):
                dirv = u * math.cos(a) + v * math.sin(a)
                for j, s in enumerate(rows):
                    c = h + d * s
                    r = ray_out(c, dirv, 0.06)
                    r = r if r is not None else 0.012
                    S[i, j] = c + dirv * (r + fc["clear"] + fc["thick"] * (1.0 + 0.3 * math.cos(a)))
            fs, _, _ = VG.grid_solid(bm, S, fc["thick"], lambda i, j: "gold" if (j == 0 and k == 0) else "plate",
                                     out_ref=lambda p, c=h, d_=d: (p - c) - d_ * ((p - c) @ d_), rand=rng.random())
            reg(bm, fs, "FINGER_%s_%d_L" % (fn.upper(), k + 1), "%s_%02d_l" % (fn, k + 1))


bml = new_bm()
gauntlets(bml, 1)
finish(new_bm(), "GAUNTLETS", mirror_from=bml)

# ==============================================================================================================
# LEGS: cuisse, poleyn, greave (around each leg's section centre line)
# ==============================================================================================================
lc = cfg["legs"]
ZS_L = np.arange(0.12, 1.14, 0.02)
LEG_C = np.zeros((len(ZS_L), 2))
for i, z in enumerate(ZS_L):
    m = (body_co[:, 0] > 0.02) & (np.abs(body_co[:, 2] - z) < 0.02) & (body_co[:, 0] < 0.6)
    LEG_C[i] = body_co[m][:, :2].mean(0) if m.any() else LEG_C[i - 1]
LEG_C = gauss_rows(LEG_C, 2.0, 0.0, periodic_t=False)
TH_L = np.arange(32) * 2 * math.pi / 32           # 0 = front (-Y), pi/2 = +X (lateral for the left leg)


def leg_frame(z):
    c = np.array([np.interp(z, ZS_L, LEG_C[:, 0]), np.interp(z, ZS_L, LEG_C[:, 1]), z])
    return c, np.array([0.0, -1.0, 0.0]), np.array([1.0, 0.0, 0.0])


R_L = gauss_rows(body_radius_grid(None, TH_L, ZS_L, leg_frame, maxd=0.35), 1.2, 1.0)


def R_leg(t, z):
    zc = np.clip(z, ZS_L[0], ZS_L[-1])
    fz = (zc - ZS_L[0]) / 0.02
    i0 = int(min(max(math.floor(fz), 0), len(ZS_L) - 2))
    tz = fz - i0
    ft = (t % (2 * math.pi)) / (2 * math.pi / 32)
    j0 = int(ft) % 32
    j1 = (j0 + 1) % 32
    tt = ft - int(ft)
    a = R_L[i0, j0] * (1 - tt) + R_L[i0, j1] * tt
    b = R_L[i0 + 1, j0] * (1 - tt) + R_L[i0 + 1, j1] * tt
    return a * (1 - tz) + b * tz


def leg_pt(t, z, r):
    c, U, V = leg_frame(z)
    return c + (U * math.cos(t) + V * math.sin(t)) * r


def leg_out(p):
    return np.array([p[0] - np.interp(p[2], ZS_L, LEG_C[:, 0]), p[1] - np.interp(p[2], ZS_L, LEG_C[:, 1]), 0.0])


def legs(bm, sd):
    cu = lc["cuisse"]
    ths = np.radians(np.linspace(cu["theta_deg"][0], cu["theta_deg"][1], cu["u"]))
    zs = np.linspace(cu["z"][0], cu["z"][1], cu["v"])
    S = np.array([[leg_pt(t, z, R_leg(t, z) + cu["clear"] + cu["thick"] + 0.012 * math.sin(math.pi * (z - zs[0]) / (zs[-1] - zs[0])))
                   for z in zs] for t in ths])
    fs, _, _ = VG.grid_solid(bm, S, cu["thick"], "plate", out_ref=leg_out, rand=rng.random(), lip=0.005, simple_inner=True)
    reg(bm, fs, "CUISSE_L", "thigh_l")
    po = lc["poleyn"]
    ths = np.radians(np.linspace(po["theta_deg"][0], po["theta_deg"][1], po["u"]))
    zs = VG.rim_rows(po["z"][0], po["z"][1], RIM, po["v"] - 4)
    zc = (zs[0] + zs[-1]) / 2

    def pr(t, z, j):
        base = R_leg(t, z) + po["clear"] + po["thick"]
        bul = po["bulge"] * max(0.0, math.cos(t)) ** 1.5 * max(0.0, 1 - ((z - zc) / (zs[-1] - zc)) ** 2)
        wing = po["wing"] * smoothstep(0.55, 0.95, abs(math.sin(t))) * max(0.0, 1 - abs(z - zc) / (zs[-1] - zc))
        return base + bul + wing
    S = np.array([[leg_pt(t, z, pr(t, z, j)) for j, z in enumerate(zs)] for t in ths])
    fs, _, _ = VG.grid_solid(bm, S, po["thick"], lambda i, j: "gold" if j in (0, len(zs) - 2) else "plate",
                             out_ref=leg_out, rand=rng.random(), lip=0.005, simple_inner=True)
    reg(bm, fs, "POLEYN_L", "calf_l")
    gr = lc["greave"]
    ths = np.arange(gr["u"]) * 2 * math.pi / gr["u"]
    zs = [gr["z"][0], gr["z"][0] + RIM, gr["z"][0] + RIM + 0.012, gr["z"][0] + 2 * RIM + 0.012] + \
        list(np.linspace(gr["z"][0] + 0.09, gr["z"][1] - 0.06, gr["v"] - 3)) + [gr["z"][1] - 0.02, gr["z"][1]]

    def gr_r(t, z, j):
        base = max(R_leg(t, z) + gr["clear"] + gr["thick"], 0.1)
        base += gr["front_ridge"] * max(0.0, math.cos(t)) ** 8
        if j in (1, 2, 3):
            base += 0.006
        if j in (0, len(zs) - 1):
            base -= 0.005
        k = float(VG.superellipse(t, 1.0, 1.0, gr["exponent"])) * 0.95
        return base * k
    S = np.array([[leg_pt(t, z, gr_r(t, z, j)) for j, z in enumerate(zs)] for t in ths])
    fs, _, _ = VG.grid_solid(bm, S, gr["thick"], lambda i, j: "gold" if j in (0, 2) else "plate", periodic_u=True,
                             out_ref=leg_out, rand=rng.random(), simple_inner=True)
    reg(bm, fs, "GREAVE_L", "calf_l")


bml = new_bm()
legs(bml, 1)
finish(new_bm(), "LEGS", mirror_from=bml)

# ==============================================================================================================
# SABATONS
# ==============================================================================================================
sc = cfg["sabaton"]


def sab_section(y, hw, top, n, x0):
    """Rounded-box cross-section (x-z) at y: bottom z 0 .. top, half width hw, points CCW around (x0, top/2)."""
    pts = []
    for k in range(n):
        a = k * 2 * math.pi / n + math.pi / n
        r = float(VG.superellipse(a, hw, top / 2, sc["exponent"]))
        pts.append((x0 + math.cos(a) * r, y, top / 2 + math.sin(a) * r))
    return pts


def sabatons(bm, sd):
    x0 = sc["centre_x"]
    n = sc["u"]

    def shell(sections, name, bone, gold_rows, extra_end=None):
        S = np.array([sab_section(y, hw, top, n, x0) for (y, hw, top) in sections])      # (v, u, 3)
        S = np.transpose(S, (1, 0, 2))                                                      # (u, v, 3)
        # the sole: points in the bottom band are flat at z 0 and slightly wider
        S[:, :, 2] = np.maximum(S[:, :, 2], 0.0)
        cen = lambda p: np.array([p[0] - x0, 0.0, p[2] - 0.12])  # noqa: E731
        zonef = lambda i, j: ("gold" if j in gold_rows else ("iron" if S[i, j, 2] < sc["sole"] + 0.003 and S[(i + 1) % n, j, 2] < sc["sole"] + 0.003 else "plate"))  # noqa: E731
        fs = VG.loft_solid(bm, S, zonef, rand=rng.random())
        reg(bm, fs, name, bone)
        return fs
    secs = sc["sections"]
    # the tube closes at both ends: an end section shrunk to a small rounded nub (the heel back, the toe tip)
    heel_end = (secs[0][0] + 0.022, secs[0][1] * 0.45, secs[0][2] * 0.55)
    shell([heel_end] + secs + [(secs[-1][0] - 0.02, secs[-1][1] * 0.5, secs[-1][2] * 0.6)], "SABATON_FOOT_L", "foot_l", [])
    toe = np.array(sc["toe_sections"], dtype=np.float64)
    sp = sc["toe_split_y"]

    def toe_at(y, scale=1.0, lift=0.0):
        yy = toe[:, 0][::-1]
        return (y, float(np.interp(y, yy, toe[:, 1][::-1])) * scale + lift * 0.6, float(np.interp(y, yy, toe[:, 2][::-1])) * scale + lift)
    y0t, y1t = toe[0, 0], toe[-1, 0]
    # lame 1 over the instep end, lame 2 (the toe cap) tucked under it; each closes at its ends; a thin gold rim
    # band runs across the back edge of each lame
    l1 = [toe_at(y0t + 0.012, 0.9, 0.012), toe_at(y0t, 1, 0.012), toe_at(y0t - RIM, 1, 0.012), toe_at((y0t + sp) / 2, 1, 0.012),
          toe_at(sp - 0.02, 1, 0.012), toe_at(sp - 0.035, 0.9, 0.012)]
    l2 = [toe_at(sp + 0.03, 0.9), toe_at(sp + 0.018), toe_at(sp + 0.018 - RIM), toe_at((sp + y1t) / 2), toe_at(y1t + 0.02),
          (y1t, toe[-1, 1] * 0.55, toe[-1, 2] * 0.7)]
    shell(l1, "SABATON_TOE1_L", "ball_l", [1])
    shell(l2, "SABATON_TOE2_L", "ball_l", [1])
    # ankle cuff: a boxy tube around the leg over the ankle, a thin gold rim at the top
    ac_ = sc["ankle_cuff"]
    zs = [ac_["z"][0], ac_["z"][0] + 0.02] + list(np.linspace(ac_["z"][0] + 0.05, ac_["z"][1] - 0.04, 2)) + [ac_["z"][1] - RIM, ac_["z"][1]]
    ths = np.arange(sc["u"]) * 2 * math.pi / sc["u"]
    S = np.zeros((len(ths), len(zs), 3))
    for i, t in enumerate(ths):
        for j, z in enumerate(zs):
            c = np.array([sc["centre_x"], ac_["y"], z])
            a_, b_ = ac_["half"]
            r = float(VG.superellipse(t, b_, a_, sc["exponent"]))
            r *= 1.0 + ac_["flare"] * (z - zs[0]) / (zs[-1] - zs[0])
            if j in (0, len(zs) - 1):
                r -= 0.006
            S[i, j] = c + np.array([math.sin(t), -math.cos(t), 0.0]) * r
    fs, _, _ = VG.grid_solid(bm, S, 0.016, lambda i, j: "gold" if j == len(zs) - 2 else "plate", periodic_u=True,
                             out_ref=lambda p: np.array([p[0] - sc["centre_x"], p[1] - ac_["y"], 0.0]), rand=rng.random(), simple_inner=True)
    reg(bm, fs, "SABATON_CUFF_L", "foot_l")


bml = new_bm()
sabatons(bml, 1)
finish(new_bm(), "SABATONS", mirror_from=bml)

# ==============================================================================================================
# HIPS: tassets + fauld
# ==============================================================================================================
hc = cfg["hips"]


def hip_radius(t, z):
    """Outermost body / cuisse radius from the torso axis at angle t, height z (for the tasset stand-off)."""
    C = np.array([0.0, torso_cy(max(z, 1.1)), z])
    d = tdir(t)
    best = 0.0
    o = C + d * 0.9
    loc, n, i, dist = body_bvh.ray_cast(Vector(o), Vector(-d), 0.9)
    if loc is not None:
        best = 0.9 - dist
    return best


def hips(bm, sd):
    ta = hc["tasset"]
    th0, th1 = math.radians(ta["theta_deg"][0]), math.radians(ta["theta_deg"][1])
    ths = np.array(VG.rim_rows(th0, th1, RIM / 0.42, ta["u"] - 4))
    for k, (zt, zb) in enumerate(ta["lames"]):
        zs = VG.rim_rows(zt, zb, RIM, ta["v"] - 4)
        S = np.zeros((len(ths), len(zs), 3))
        for i, t in enumerate(ths):
            for j, z in enumerate(zs):
                f = (j / (len(zs) - 1))
                zz = z - ta["slant"] * f * (i / (len(ths) - 1))
                r = hip_radius(t, zz) + ta["stand_off"] + ta["flare"] * f + 0.018 * k + 0.012 * math.sin(math.pi * i / (len(ths) - 1))
                C = np.array([0.0, torso_cy(max(zz, 1.1)), zz])
                S[i, j] = C + tdir(t) * r
        fs, _, _ = VG.grid_solid(bm, S, ta["thick"], lambda i, j: "gold" if (j in (0, len(zs) - 2) or i in (0, len(ths) - 2)) else "plate",
                                 out_ref=lambda p: np.array([p[0], p[1] - torso_cy(max(p[2], 1.1)), 0.0]), rand=rng.random(), lip=0.004,
                                 simple_inner=True)
        reg(bm, fs, "TASSET%d_L" % (k + 1), "pelvis" if k == 0 else "thigh_l")


bml = new_bm()
hips(bml, 1)
bm = new_bm()
# fauld: chevron lames (centred, not mirrored)
fa = hc["fauld"]
zt = fa["top_z"]
for k in range(fa["lames"]):
    L = fa["len"][k]
    w = fa["width"][k] / 2
    vee = fa["vee"]
    last = k == fa["lames"] - 1
    zb = zt - L
    if last:
        poly = [(-w, zt), (0.0, zt - vee), (w, zt), (w * 0.55, zb + L * 0.35), (0.0, zb - 0.02), (-w * 0.55, zb + L * 0.35)]
    else:
        poly = [(-w, zt), (0.0, zt - vee), (w, zt), (w, zb + vee * 0.2), (0.0, zb - vee * 0.6), (-w, zb + vee * 0.2)]
    f_ = (k + 0.5) / fa["lames"]
    y = fa["y_top"] + (fa["y_bottom"] - fa["y_top"]) * f_ - 0.01 * k
    fs = VG.prism(bm, poly, (0, y, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), 0.0, fa["thick"], 0.011,
                  {"front": "plate", "side": "gold", "chamfer": "gold", "back": "iron"}, rand=rng.random())
    reg(bm, fs, "FAULD_%d" % (k + 1), "pelvis" if k < 2 else "x_fauld_01")
    zt = zb + fa["overlap"]
finish(bm, "HIPS", mirror_from=bml)

# ==============================================================================================================
# LOINCLOTH (war-red cloth behind the fauld)
# ==============================================================================================================
lo = cfg["loin"]
bm = new_bm()
NUl, NVl = lo["u"], lo["v"]
S = np.zeros((NUl, NVl, 3))
tears = [rng.uniform(*lo["tear"]) if i % 2 == 0 else rng.uniform(0.0, lo["tear"][0]) for i in range(NUl)]
for i in range(NUl):
    u = -1 + 2 * i / (NUl - 1)
    for j in range(NVl):
        f = j / (NVl - 1)
        z = lo["z"][0] + (lo["z"][1] - lo["z"][0]) * f
        if j == NVl - 1:
            z -= tears[i]
        hw = lo["half_width"][0] + (lo["half_width"][1] - lo["half_width"][0]) * f
        y = lo["y"][0] + (lo["y"][1] - lo["y"][0]) * f + 0.02 * (1 - u * u) * f + 0.006 * math.sin(u * 7.0 + f * 3.0) * f
        S[i, j] = (u * hw, y, z)
fs, _, _ = VG.grid_solid(bm, S, lo["thick"], "cape", out_ref=lambda p: np.array([0, -1.0, 0]), zone_in="cape",
                         wall_zone=("cape", "cape", "cape", "cape"), rand=0.5)
reg(bm, fs, "LOINCLOTH", "x_loin_C_01")
finish(bm, "LOINCLOTH")

# ==============================================================================================================
# CAPE + collar
# ==============================================================================================================
cc = cfg["cape"]
bm = new_bm()
rows = np.array(cc["rows"], dtype=np.float64)
NUc = cc["u"]
NR = len(rows)
tat = [rng.uniform(*cc["tatter"]["long"]) if i % 2 == 0 else rng.uniform(*cc["tatter"]["short"]) for i in range(NUc)]
S = np.zeros((NUc, NR, 3))
for i in range(NUc):
    u = -1 + 2 * i / (NUc - 1)
    for j in range(NR):
        z, hw, yc, ys = rows[j]
        f = j / (NR - 1)
        amp = cc["folds"]["amp_top"] + (cc["folds"]["amp_hem"] - cc["folds"]["amp_top"]) * f ** 1.4
        fold = amp * math.sin(u * math.pi * cc["folds"]["count"] + 0.6)
        y = ys + (yc - ys) * (1 - u * u) + fold
        if j == NR - 1:
            z = z - tat[i] * (0.6 + 0.4 * (1 - abs(u)))
        S[i, j] = (u * hw, y, z)
fs, _, _ = VG.grid_solid(bm, S, cc["thick"], "cape", out_ref=lambda p: np.array([p[0] * 0.3, 1.0, 0.0]), zone_in="cape",
                         wall_zone=("cape", "cape", "cape", "cape"), rand=0.5)
reg(bm, fs, "CAPE", "x_cape_C_01")
co_ = cc["collar"]
ths = np.linspace(-1, 1, 9)
S = np.zeros((len(ths), 3, 3))
for i, u in enumerate(ths):
    for j, f in enumerate((0.0, 0.5, 1.0)):
        z = co_["z"][0] + (co_["z"][1] - co_["z"][0]) * f
        y = co_["y"][0] + (co_["y"][1] - co_["y"][0]) * (1 - u * u) + co_["flare"] * f
        S[i, j] = (u * co_["half_width"] * (1 + 0.15 * f), y, z - 0.03 * u * u * f)
fs, _, _ = VG.grid_solid(bm, S, co_["thick"], "cape", out_ref=lambda p: np.array([0, 1.0, 0]), zone_in="cape",
                         wall_zone=("gold", "gold", "cape", "cape"), rand=0.5)
reg(bm, fs, "CAPE_COLLAR", "spine_03")
finish(bm, "CAPE")

# ==============================================================================================================
# BEARD: block, moustache, braids
# ==============================================================================================================
bc = cfg["beard"]
bm = new_bm()
eye = fit["landmarks"]["eye_l"]
head_c = np.array([0.0, fit["landmarks"]["head.head"][1] + 0.01, 0.0])
ths = np.radians(np.linspace(bc["theta_deg"][0], bc["theta_deg"][1], bc["u"]))
rows_z = bc["rows_z"]
th_tab = np.array(bc["thickness"], dtype=np.float64)


def beard_thick(tdeg, z):
    a = abs(tdeg)
    w = np.clip(a / 90.0, 0, 1)
    f0 = th_tab[th_tab[:, 0] == 0.0]
    f9 = th_tab[th_tab[:, 0] == 90.0]
    t0 = np.interp(z, f0[:, 1][::-1], f0[:, 2][::-1])
    t9 = np.interp(z, f9[:, 1][::-1], f9[:, 2][::-1])
    return float(t0 * (1 - w) + t9 * w)


tz_top = np.array(bc["top_z"], dtype=np.float64)
tz_bot = np.array(bc["bottom_z"], dtype=np.float64)


def face_r(t, z):
    """Distance from the head axis (x 0, y head_c) to the body surface (face / neck) at angle t, height z."""
    C = np.array([0.0, head_c[1], z])
    d = tdir(t)
    loc, n, i, dist = body_bvh.ray_cast(Vector(C + d * 0.4), Vector(-d), 0.4)
    return 0.4 - dist if loc is not None else 0.1


NV_B = 7
S = np.zeros((len(ths), NV_B, 3))
I = np.zeros_like(S)
for i, t in enumerate(ths):
    tdeg = math.degrees(t)
    ztop = float(np.interp(abs(tdeg), tz_top[:, 0], tz_top[:, 1]))
    zbot = float(np.interp(abs(tdeg), tz_bot[:, 0], tz_bot[:, 1]))
    r_prev = None
    for j in range(NV_B):
        f = j / (NV_B - 1)
        z = ztop + (zbot - ztop) * f
        fr = face_r(t, z)
        th = beard_thick(tdeg, z)
        # below the chin the face surface falls back to the neck: keep the beard's outer surface full (a bib)
        ro = fr + th
        if r_prev is not None:
            ro = max(ro, r_prev - 0.012)
        r_prev = ro
        ri = min(fr - 0.012, ro - 0.02)
        d = tdir(t)
        S[i, j] = np.array([0.0, head_c[1], z]) + d * ro
        I[i, j] = np.array([0.0, head_c[1], z]) + d * ri
fs, _, _ = VG.grid_solid(bm, S, 0.0, "beard", inner=I, zone_in="beard", wall_zone=("beard", "beard", "beard", "beard"), rand=0.4,
                         out_ref=lambda p: np.array([p[0], p[1] - head_c[1], 0.0]))
reg(bm, fs, "BEARD_BLOCK", "head")
# chunky locks over the base shell: cheeks sweep down and forward, chin locks flow into the braid roots
import s2_geom as G0  # noqa: E402


def lock(bm, root, nrm, d0, bend, L, w, t, name):
    fs = G0.lock(bm, root, nrm, np.asarray(d0) / np.linalg.norm(d0), np.asarray(bend) / np.linalg.norm(bend), L, w, t, rng, "beard", 6)
    VG.tag(fs, "beard")
    reg(bm, fs, name, "head")


def beard_surface(tdeg, z):
    t = math.radians(tdeg)
    r = face_r(t, z) + beard_thick(tdeg, z)
    return np.array([0.0, head_c[1], z]) + tdir(t) * r, tdir(t)


for lk in bc["locks"]:
    for sdl in ((1,) if lk.get("centre") else (1, -1)):
        root, nrm = beard_surface(sdl * lk["theta"], lk["z"])
        d0 = np.array([sdl * lk["dir"][0], lk["dir"][1], lk["dir"][2]])
        lock(bm, root, nrm, d0 + nrm * 0.3, np.array([sdl * lk["dir"][0] * 0.5, lk["dir"][1] * 0.6, -1.0]), lk["len"], lk["w"], lk["t"], "BEARD_LOCK")
# moustache: two heavy locks from under the nose drooping past the mouth corners
mo = bc["moustache"]
for sdm in (1, -1):
    root, nrm = beard_surface(sdm * 4.0, mo["root_z"])
    root = root + nrm * 0.004
    tip = np.array([sdm * mo["tip"][0], 0.0, mo["tip"][2]])
    tip_s, tip_n = beard_surface(math.degrees(math.atan2(tip[0], 0.2)), mo["tip"][2])
    d0 = np.array([sdm * 0.9, -0.15, -0.35])
    bend = np.array([sdm * 0.25, -0.1, -1.0])
    L = float(np.linalg.norm(tip_s - root)) * 1.15
    lock(bm, root, nrm, d0, bend, L, mo["width"], mo["thick"], "MOUSTACHE")
# braids: overlapping plait lobes (alternating tilt), a gold ring and a steel cap
br = bc["braids"]
for bi, x in enumerate(br["x"]):
    r0 = np.array([x, br["y_root"], br["root_z"][bi]])
    r1 = np.array([x * br["splay"], br["y_end"], br["end_z"][bi]])
    ring_len, cap_len = 0.022, br["cap"][1]
    axis = (r1 - r0) / np.linalg.norm(r1 - r0)
    lobe_end = r1 - axis * (ring_len + cap_len)
    nl = br["lobes"]
    Lb = np.linalg.norm(lobe_end - r0) / nl
    side = np.cross(axis, [0.0, -1.0, 0.0])
    side /= np.linalg.norm(side)
    fwd = np.cross(side, axis)
    for k in range(nl):
        c = r0 + axis * Lb * (k + 0.5)
        tilt = 0.42 * (1 if k % 2 == 0 else -1)
        ax = axis * math.cos(tilt) + side * math.sin(tilt)
        fs = VG.lobe(bm, c, ax, side, br["lobe"][0] * (1 - 0.07 * k), br["lobe"][1] * (1 - 0.05 * k), Lb * 0.95, "beard", 6, rng.random())
        reg(bm, fs, "BRAID%d_LOBE" % (bi + 1), "x_beard_%d_01" % (bi + 1) if k < nl // 2 else "x_beard_%d_02" % (bi + 1))
    fs = VG.cylinder(bm, lobe_end - axis * 0.006, lobe_end + axis * ring_len, br["ring"][0], br["ring"][0], "gold", 8, bevel=0.004,
                     up=fwd)
    fs += VG.cylinder(bm, lobe_end + axis * ring_len - axis * 0.002, r1, br["cap"][0], br["cap"][0] * 0.82, "steel", 8, bevel=0.006,
                      up=fwd)
    reg(bm, fs, "BRAID%d_CAP" % (bi + 1), "x_beard_%d_02" % (bi + 1))
finish(bm, "BEARD")

# ==============================================================================================================
# BODY zones: skin on the head and neck, glove hands, eyeballs, mail elsewhere
# ==============================================================================================================
for m in mats:
    body.data.materials.append(m)
bmb = bmesh.new()
bmb.from_mesh(body.data)
parts_b = sorted(connected_parts(bmb), key=len)
eyes = set(f for pv in parts_b[:-1] for v in pv for f in v.link_faces)
bz = cfg.get("body_zones", {"skin_z": 2.02, "glove_abs_x": 0.9})
for f in bmb.faces:
    c = f.calc_center_median()
    if f in eyes:
        f.material_index = Zn["eye"]
    elif c.z > bz["skin_z"] and abs(c.x) < bz.get("skin_abs_x", 0.2):
        f.material_index = Zn["skin"]
    elif abs(c.x) > bz["glove_abs_x"] and c.z > 1.5:
        f.material_index = Zn["leather"]
    else:
        f.material_index = Zn["mail"]
bmb.to_mesh(body.data)
bmb.free()
report["parts"]["BODY"] = mesh_stats(body)

bpy.data.objects.remove(bpy.data.objects["REF_blockout"]) if "REF_blockout" in bpy.data.objects else None
report["triangles_total"] = sum(v["triangles"] for v in report["parts"].values())
report["piece_table"] = piece_table
log("total triangles", report["triangles_total"])
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
