"""Stage 2, step 4: Brax's separate production parts, built procedurally around the fitted body and
measured on the stage-1 sculpt reference (never copied from it).

Parts (each a closed mesh, faces tagged with paint zones - s2_geom.ZONES):
  (the rock forge-gauntlets are the anvil_gauntlets WEAPON model since the 2026-09-25 user decision:
   tools/blender/gf_hero/s2_weapon.py + s2_gauntlet.py, art/weapons/anvil_gauntlets/)
  BELT                     leather belt + bronze buckle ring
  SASH                     teal waist wrap, knot, two frayed front tails and one back tail
  SKIRT_CLOTH              torn brown underskirt (flared, jagged hem), with thickness
  SKIRT_PLATES             three tiers of overlapping bronze leaf plates (rigid pieces)
  WRAPS                    teal ankle wraps (sleeves with thickness) + instep straps + short wrist wraps
  HAIR / BEARD             shells over the scalp / jaw: the body's own quad layout there, pushed out to the
                           sculpt's hair and beard surface, closed with a rim; plus spiky hair clumps

  blender -b -P tools/blender/gf_hero/s2_parts.py -- <body.blend> <retopo_start.blend> <parts.json> <out.blend>
          [--report <json>]
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

import s2_geom as G  # noqa: E402
from s2lib import (connected_parts, get_co, get_collection, hex_rgb, log, mesh_stats, opt, read_json, save_blend,  # noqa: E402
                   script_args, srgb_to_linear, write_json)

argv = script_args(__doc__)
if len(argv) < 4:
    raise SystemExit(__doc__)
BODY, REF, CFG, OUT = (os.path.abspath(a) for a in argv[:4])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(CFG)
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
with bpy.data.libraries.load(REF, link=False) as (src, dst):
    dst.objects = ["REF_blockout"]
ref = dst.objects[0]
scene.collection.objects.link(ref)
dg = bpy.context.evaluated_depsgraph_get()
ref_bvh = BVHTree.FromObject(ref, dg)
body_bvh = BVHTree.FromObject(body, dg)
body_co = get_co(body.data)
report = {"parts": {}}
rng = random.Random(cfg.get("seed", 7))
col = get_collection("BRAX_stage2")

# ---- zone materials (preview colours = palette base tones; the painter replaces them with the atlas) ---
pal = {s["key"]: s["tones"] for s in read_json(os.path.join(os.path.dirname(CFG), "palette.json"))["swatches"]}
zone_hex = {"skin": pal["skin"]["base"], "hair": pal["hair_beard"]["base"], "beard": pal["hair_beard"]["base"],
            "eye": pal["eye_glow"]["hot"], "rock": pal["gauntlet_rock"]["base"], "lava": pal["lava_glow"]["hot"],
            "bronze": pal["bronze"]["base"], "plates": pal["scale_plates"]["base"], "leather": pal["belt_leather"]["base"],
            "cloth": pal["torn_cloth"]["base"], "sash": pal["teal_sash"]["base"], "wraps": pal["ankle_wraps"]["base"],
            "linen": pal["wrap_linen"]["base"]}
mats = []
for zname in G.ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    c = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    m.diffuse_color = c
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = c
    if zname in ("eye", "lava"):
        bsdf.inputs["Emission Color"].default_value = c
        bsdf.inputs["Emission Strength"].default_value = 3.0
    mats.append(m)


def finish(bm, name, zone_default=None):
    lay = bm.verts.layers.float_color.get(G.MASK_LAYER)
    if lay is None:
        G.set_mask(bm, bm.verts, 0.5)
    else:
        G.set_mask(bm, [v for v in bm.verts if v[lay][3] < 0.5], 0.5)   # alpha 0 = never set
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
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
    log("%-14s %6d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d" % (
        name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"]))
    return ob


# assign the body's zones: skin everywhere, eyeballs = eye
for m in mats:
    body.data.materials.append(m)
bmb = bmesh.new()
bmb.from_mesh(body.data)
parts_b = sorted(connected_parts(bmb), key=len)
for pv in parts_b[:-1]:          # the two small pieces are the eyeballs
    for f in {f for v in pv for f in v.link_faces}:
        f.material_index = G.Z["eye"]
bmb.to_mesh(body.data)
bmb.free()


# ======================================================================================================
# sculpt envelope R(theta, z): distance from the skirt axis to the outermost sculpt surface
# (theta 0 = front (-Y), 90 = his left (+X))
# ======================================================================================================
env_cfg = cfg["envelope"]
AY = env_cfg["axis_y"]
TH = np.radians(np.arange(0, 360, env_cfg["dtheta_deg"]))
ZS = np.arange(env_cfg["z"][0], env_cfg["z"][1] + 1e-6, env_cfg["dz"])


def dvec(t):
    return np.array([math.sin(t), -math.cos(t), 0.0])


RAW = np.zeros((len(ZS), len(TH)))
for zi, z in enumerate(ZS):
    for ti, t in enumerate(TH):
        d = Vector(dvec(t))
        o = Vector((0.0, AY, z)) + d * 0.9
        loc, n_, idx, dist = ref_bvh.ray_cast(o, -d, 0.9)
        RAW[zi, ti] = 0.9 - dist if loc is not None else np.nan
RAW = np.where(np.isnan(RAW), np.nanmedian(RAW), RAW)
ENV = RAW.copy()
for zi in range(len(ZS)):
    for ti in range(len(TH)):
        blk = RAW[max(0, zi - 1):zi + 2][:, [(ti - 1) % len(TH), ti, (ti + 1) % len(TH)]]
        ENV[zi, ti] = np.median(blk)


def R(t, z):
    """Envelope radius at angle t (radians) and height z (bilinear, periodic in t)."""
    t = t % (2 * math.pi)
    fi = t / (TH[1] - TH[0])
    i0 = int(math.floor(fi)) % len(TH)
    i1 = (i0 + 1) % len(TH)
    ft = fi - math.floor(fi)
    zc = min(max(z, ZS[0]), ZS[-1])
    fz = (zc - ZS[0]) / (ZS[1] - ZS[0])
    j0 = min(int(math.floor(fz)), len(ZS) - 2)
    fz -= j0
    a = ENV[j0, i0] * (1 - ft) + ENV[j0, i1] * ft
    b = ENV[j0 + 1, i0] * (1 - ft) + ENV[j0 + 1, i1] * ft
    return a * (1 - fz) + b * fz


def P(t, z, r):
    return np.array([0.0, AY, z]) + dvec(t) * r


def body_r(t, z, band=0.03):
    """Largest radius of the body (hips / thighs) around angle t at height z (from the skirt axis)."""
    m = np.abs(body_co[:, 2] - z) < band
    q = body_co[m] - np.array([0.0, AY, 0.0])
    if not len(q):
        return 0.0
    ang = np.arctan2(q[:, 0], -q[:, 1]) % (2 * math.pi)
    da = np.abs((ang - t + math.pi) % (2 * math.pi) - math.pi)
    sel = da < math.radians(12)
    return float(np.hypot(q[sel, 0], q[sel, 1]).max()) if sel.any() else 0.0


def closed_loop(bm, loop, zone):
    """Closed tube from a loop of rings (each ring = list of points, all the same count): ring k joins
    ring k+1 and the last joins the first."""
    vr = [[bm.verts.new(tuple(p)) for p in r] for r in loop]
    faces = []
    n = len(loop[0])
    for k in range(len(vr)):
        a, b = vr[k], vr[(k + 1) % len(vr)]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    G.tag(faces, zone)
    return faces


# ---- BELT + buckle -------------------------------------------------------------------------------------
bc_ = cfg["belt"]
bm = bmesh.new()
n = bc_["segments"]
ts = np.arange(n) * 2 * math.pi / n
z0, z1 = bc_["z"]
ch = bc_["chamfer"]
outer = [[P(t, z1, R(t, z1) + bc_["out"] - ch) for t in ts], [P(t, z1 - ch, R(t, z1 - ch) + bc_["out"]) for t in ts],
         [P(t, z0 + ch, R(t, z0 + ch) + bc_["out"]) for t in ts], [P(t, z0, R(t, z0) + bc_["out"] - ch) for t in ts]]
inner = [[P(t, z0, R(t, z0) - bc_["depth"]) for t in ts], [P(t, z1, R(t, z1) - bc_["depth"]) for t in ts]]
closed_loop(bm, outer + inner, "leather")
bk = bc_["buckle"]
zb = (z0 + z1) / 2
cen = P(0.0, zb, R(0.0, zb) + bc_["out"] + bk["standoff"])
nseg = bk["segments"]
rings = []
for (rr, dy) in [(bk["r"] - bk["w"], -bk["t"]), (bk["r"] - bk["w"], bk["t"]), (bk["r"], bk["t"]), (bk["r"], -bk["t"])]:
    tt = np.arange(nseg) * 2 * math.pi / nseg
    rings.append([np.array([cen[0] + math.cos(a) * rr, cen[1] + dy, cen[2] + math.sin(a) * rr]) for a in tt])
closed_loop(bm, rings, "bronze")
boss = [np.array([cen[0] + math.cos(a) * bk["boss"], cen[1], cen[2] + math.sin(a) * bk["boss"]]) for a in np.arange(8) * math.pi / 4]
G.loft(bm, [[p + np.array([0, bk["t"] * 0.5, 0]) for p in boss], [p + np.array([0, -bk["t"] * 1.4, 0]) for p in boss]], "bronze")
finish(bm, "BELT")

# ---- SASH: waist wrap, knot, tails ----------------------------------------------------------------------
sc = cfg["sash"]
bm = bmesh.new()
n = sc["wrap_segments"]
ts = np.arange(n) * 2 * math.pi / n
z0, z1 = sc["wrap_z"]
zm = (z0 + z1) / 2
wo = sc["wrap_out"]
outer = [[P(t, z1, R(t, z1) + wo - 0.006) for t in ts], [P(t, z1 - 0.012, R(t, z1 - 0.012) + wo) for t in ts],
         [P(t, zm, R(t, zm) + wo + 0.004) for t in ts],
         [P(t, z0 + 0.012, R(t, z0 + 0.012) + wo) for t in ts], [P(t, z0, R(t, z0) + wo - 0.006) for t in ts]]
inner = [[P(t, z0, R(t, z0) - 0.02) for t in ts], [P(t, z1, R(t, z1) - 0.02) for t in ts]]
closed_loop(bm, outer + inner, "sash")
kn = sc["knot"]
kt = math.radians(kn["theta_deg"])
kc = P(kt, kn["z"], R(kt, kn["z"]) + kn["standoff"])
geom = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=1.0)
for v in geom["verts"]:
    v.co = Vector((v.co.x * kn["size"][0] + kc[0], v.co.y * kn["size"][1] + kc[1], v.co.z * kn["size"][2] + kc[2]))
G.tag(G.faces_of(geom["verts"]), "sash")


def tail(bm, spec):
    """Hanging ribbon with thickness: centreline from the knot down, in front of the skirt, frayed V end."""
    zt, zb_ = spec["z"]
    rows = max(4, int((zt - zb_) / spec["row"]))
    th0 = math.radians(spec["theta_deg"])
    cols = [[], [], []]
    for k in range(rows + 1):
        f = k / rows
        z = zt + (zb_ - zt) * f
        x = spec["x"][0] + (spec["x"][1] - spec["x"][0]) * f + math.sin(f * 7.0 + spec["phase"]) * spec["sway"]
        hb = spec["hang_below"]
        r = R(th0, max(z, hb)) + spec["standoff"] + max(0.0, hb - z) * spec["forward_below"]
        yv = AY - r * math.cos(th0)
        w = spec["width"][0] + (spec["width"][1] - spec["width"][0]) * f
        tw = math.sin(f * 5.0 + spec["phase"]) * spec["twist"]
        c = np.array([x, yv, z])
        side = np.array([math.cos(tw), math.sin(tw) * 0.4, 0.0])
        cols[0].append(c - side * w / 2)
        cols[1].append(c + np.array([0, -spec["belly"], 0]))
        cols[2].append(c + side * w / 2)
    cols[1][-1] = cols[1][-1] + np.array([0, 0, -spec["fray"]])
    cols[0][-1] = cols[0][-1] + np.array([0, 0, spec["fray"] * 0.3])
    cols[2][-1] = cols[2][-1] + np.array([0, 0, spec["fray"] * 0.5])
    th = spec["thick"]
    vf = [[bm.verts.new(tuple(p)) for p in c] for c in cols]
    vb = [[bm.verts.new(tuple(p + np.array([0, th, 0]))) for p in c] for c in cols]
    fs = []
    for k in range(rows):
        for c in range(2):
            fs.append(bm.faces.new((vf[c][k], vf[c][k + 1], vf[c + 1][k + 1], vf[c + 1][k])))
            fs.append(bm.faces.new((vb[c + 1][k], vb[c + 1][k + 1], vb[c][k + 1], vb[c][k])))
        fs.append(bm.faces.new((vf[0][k + 1], vf[0][k], vb[0][k], vb[0][k + 1])))
        fs.append(bm.faces.new((vf[2][k], vf[2][k + 1], vb[2][k + 1], vb[2][k])))
    for c in range(2):
        fs.append(bm.faces.new((vf[c][0], vf[c + 1][0], vb[c + 1][0], vb[c][0])))
        fs.append(bm.faces.new((vf[c + 1][rows], vf[c][rows], vb[c][rows], vb[c + 1][rows])))
    G.tag(fs, "sash")
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


for tspec in sc["tails"]:
    tail(bm, tspec)
finish(bm, "SASH")

# ---- SKIRT CLOTH ---------------------------------------------------------------------------------------
cc = cfg["skirt_cloth"]
bm = bmesh.new()
n = cc["segments"]
ts = np.arange(n) * 2 * math.pi / n
hem = []
for i, t in enumerate(ts):
    front = math.cos(t) > math.cos(math.radians(cc["front_deg"]))
    base = cc["hem_front"] if front else cc["hem"]
    hem.append(base - (rng.uniform(*cc["tear_long"]) if i % 2 == 0 else rng.uniform(*cc["tear_short"])))
pushes = [0]


def cloth_r(t, z):
    zr = max(z, cc["flare_from_z"])
    r = R(t, zr) - cc["under"]
    if z < cc["flare_from_z"]:
        r += (cc["flare_from_z"] - z) * cc["flare"]
    rb = body_r(t, z) + cc["clear"]
    if rb > r:
        pushes[0] += 1
        r = rb
    return r


outer = []
for zz in cc["rows_z"]:
    outer.append([P(t, zz, cloth_r(t, zz)) for t in ts])
outer.append([P(t, hem[i], cloth_r(t, hem[i])) for i, t in enumerate(ts)])
inner = [[p - dvec(t) * cc["thick"] for p, t in zip(rr, ts)] for rr in outer]
closed_loop(bm, outer + inner[::-1], "cloth")
report["skirt_cloth_pushed_out_samples"] = pushes[0]
finish(bm, "SKIRT_CLOTH")

# ---- SKIRT PLATES ----------------------------------------------------------------------------------------
pc = cfg["skirt_plates"]
bm = bmesh.new()
G.ensure_mask(bm)
gap_lo, gap_hi = (math.radians(a) for a in pc["front_gap_deg"])
count = 0
for ti_, tier in enumerate(pc["tiers"]):
    zt, L, w = tier["z_top"], tier["length"], tier["width"]
    r_mid = R(math.pi / 2, zt - L / 2)
    nplate = max(8, int(round(2 * math.pi * r_mid / tier["spacing"])))
    dt = 2 * math.pi / nplate
    off = dt * 0.5 * (ti_ % 2)
    for i in range(nplate):
        t = off + i * dt + rng.uniform(-0.08, 0.08) * dt
        ang = (t + math.pi) % (2 * math.pi) - math.pi
        if gap_lo < ang < gap_hi:
            continue
        zb_ = zt - L * rng.uniform(0.94, 1.06)
        Pt = P(t, zt, max(R(t, zt), cloth_r(t, zt) + 0.012) + pc["top_out"] + (i % 2) * pc["stagger"])
        Pb = P(t, zb_, max(R(t, zb_), cloth_r(t, zb_) + 0.012) + pc["tip_out"] + (i % 2) * pc["stagger"])
        vdir = (Pb - Pt) / np.linalg.norm(Pb - Pt)
        tang = np.array([math.cos(t), math.sin(t), 0.0])
        nrm = np.cross(tang, vdir)
        if nrm @ dvec(t) < 0:
            nrm = -nrm
        tang = np.cross(vdir, nrm)
        Lp = float(np.linalg.norm(Pb - Pt))
        wp = w * rng.uniform(0.92, 1.08)
        ridge = pc["ridge"]

        def at(u, v, lift):
            return Pt + tang * u + vdir * v + nrm * lift
        top = [at(-wp / 2, 0, -0.002), at(0, 0, ridge * 0.6), at(wp / 2, 0, -0.002), at(wp / 2, 0.58 * Lp, -0.003),
               at(0, Lp, ridge * 0.5), at(-wp / 2, 0.58 * Lp, -0.003), at(0, 0.58 * Lp, ridge)]
        bot = [p - nrm * pc["thick"] for p in top]
        vt = [bm.verts.new(tuple(p)) for p in top]
        vb = [bm.verts.new(tuple(p)) for p in bot]
        TLi, TMi, TRi, MRi, TIPi, MLi, MCi = range(7)
        G.set_mask(bm, vb, 0.0)
        G.set_mask(bm, [vt[TLi], vt[TRi], vt[MRi], vt[MLi]], 0.0)
        G.set_mask(bm, [vt[TIPi]], 0.35)
        G.set_mask(bm, [vt[TMi]], 0.7)
        G.set_mask(bm, [vt[MCi]], 1.0)
        fs = []
        for q in [(TLi, MLi, MCi, TMi), (TMi, MCi, MRi, TRi), (MLi, TIPi, MCi), (MCi, TIPi, MRi)]:
            fs.append(bm.faces.new([vt[k] for k in q]))
            fs.append(bm.faces.new([vb[k] for k in reversed(q)]))
        outline = [TLi, TMi, TRi, MRi, TIPi, MLi]
        for k in range(len(outline)):
            a, b = outline[k], outline[(k + 1) % len(outline)]
            fs.append(bm.faces.new((vt[b], vt[a], vb[a], vb[b])))
        G.tag(fs, "plates")
        bmesh.ops.recalc_face_normals(bm, faces=fs)
        count += 1
report["skirt_plates"] = count
finish(bm, "SKIRT_PLATES")

# ---- WRAPS (ankle sleeves + instep straps) --------------------------------------------------------------
_bedges = np.empty(len(body.data.edges) * 2, dtype=np.int64)
body.data.edges.foreach_get("vertices", _bedges)
_bedges = _bedges.reshape(-1, 2)


def body_section_centre(z, sd):
    """Centre of the body's cross-section with the plane z = const on one side (edge crossings)."""
    a, b = body_co[_bedges[:, 0]], body_co[_bedges[:, 1]]
    cross = (a[:, 2] - z) * (b[:, 2] - z) < 0
    t = (z - a[cross, 2]) / (b[cross, 2] - a[cross, 2])
    pts = a[cross] + (b[cross] - a[cross]) * t[:, None]
    pts = pts[pts[:, 0] * sd > 0.05]
    if len(pts) < 4:
        raise SystemExit("wraps: no leg section at z=%.3f" % z)
    c = pts.mean(0)
    c[2] = z
    return c


wc = cfg["wraps"]
bm = bmesh.new()
for sd in (1, -1):
    rings_o, rings_i = [], []
    nseg = wc["segments"]
    for zi, z in enumerate(wc["rows_z"]):
        c = body_section_centre(z, sd)
        ro, ri = [], []
        lip = wc["lip"] if zi in (0, len(wc["rows_z"]) - 1) else 0.0
        for k in range(nseg):
            a = k * 2 * math.pi / nseg
            d = np.array([math.sin(a), -math.cos(a), 0.0])
            o = Vector(c) + Vector(d) * 0.3
            loc, nn, idx, dist = body_bvh.ray_cast(o, Vector(-d), 0.3)
            r = (0.3 - dist) if loc is not None else 0.06
            ro.append(c + d * (r + wc["thick"] + lip))
            ri.append(c + d * (r - wc["inset"]))
        rings_o.append(ro)
        rings_i.append(ri)
    closed_loop(bm, rings_o + rings_i[::-1], "wraps")
    st = wc["strap"]
    c = np.array([sd * st["center"][0], st["center"][1], st["center"][2]])
    nrm = np.array(st["normal"], dtype=np.float64)
    nrm /= np.linalg.norm(nrm)
    u = np.array([1.0, 0.0, 0.0])
    u = u - nrm * (u @ nrm)
    u /= np.linalg.norm(u)
    v = np.cross(nrm, u)
    ro, ri = [], []
    for k in range(st["segments"]):
        a = k * 2 * math.pi / st["segments"]
        d = math.cos(a) * u + math.sin(a) * v
        o = Vector(c) + Vector(d) * 0.25
        loc, nn, idx, dist = body_bvh.ray_cast(o, Vector(-d), 0.25)
        r = (0.25 - dist) if loc is not None else 0.05
        ro.append(c + d * (r + wc["thick"]))
        ri.append(c + d * (r - wc["inset"]))
    half = st["width"] / 2
    closed_loop(bm, [[p + nrm * half for p in ro], [p - nrm * half for p in ro],
                     [p - nrm * half for p in ri], [p + nrm * half for p in ri]], "wraps")
# wrist wraps: short teal sleeves like the ankle wraps, around the arm axis (the gauntlets are a separate weapon)
ww = cfg.get("wrist_wraps")
if ww:
    for sd in (1, -1):
        rings_o, rings_i = [], []
        for si, xw in enumerate(ww["abs_x"]):
            a_, b_ = body_co[_bedges[:, 0]], body_co[_bedges[:, 1]]
            cross = ((a_[:, 0] - sd * xw) * (b_[:, 0] - sd * xw) < 0) & (a_[:, 2] > 1.5) & (b_[:, 2] > 1.5)
            t_ = (sd * xw - a_[cross, 0]) / (b_[cross, 0] - a_[cross, 0])
            pts = a_[cross] + (b_[cross] - a_[cross]) * t_[:, None]
            c = pts.mean(0)
            ro, ri = [], []
            lip = ww["lip"] if si in (0, len(ww["abs_x"]) - 1) else 0.0
            for k in range(ww["segments"]):
                a = k * 2 * math.pi / ww["segments"]
                d = np.array([0.0, math.cos(a), math.sin(a)])
                o = Vector(c) + Vector(d) * 0.3
                loc, nn, idx, dist = body_bvh.ray_cast(o, Vector(-d), 0.3)
                r = (0.3 - dist) if loc is not None else 0.06
                ro.append(c + d * (r + ww["thick"] + lip))
                ri.append(c + d * (r - ww["inset"]))
            rings_o.append(ro)
            rings_i.append(ri)
        closed_loop(bm, rings_o + rings_i[::-1], "wraps")
finish(bm, "WRAPS")

# ---- HAIR and BEARD shells ------------------------------------------------------------------------------
hc_ = cfg["hair"]
bme = body.data
bme.update()
bco = get_co(bme)
bno = np.empty(len(bme.vertices) * 3)
bme.vertices.foreach_get("normal", bno)
bno = bno.reshape(-1, 3)
rme = ref.data
lc = np.empty(len(rme.loops) * 4, dtype=np.float32)
rme.color_attributes["src_col"].data.foreach_get("color", lc)
lum = lc.reshape(-1, 4)[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
ls = np.empty(len(rme.polygons), dtype=np.int64)
rme.polygons.foreach_get("loop_start", ls)
face_lum = (lum[ls] + lum[ls + 1] + lum[ls + 2]) / 3
hit_pt = np.full((len(bco), 3), np.nan)
hit_dark = np.zeros(len(bco), bool)
for i in np.nonzero(bco[:, 2] > hc_["z_min"])[0]:
    v, nv_ = Vector(bco[i]), Vector(bno[i])
    loc, nn, idx, dist = ref_bvh.ray_cast(v + nv_ * 1e-4, nv_, hc_["max_dist"])
    if loc is not None:
        hit_pt[i] = loc
        hit_dark[i] = face_lum[idx] < hc_["dark_lum"]
lips = np.zeros(len(bco), bool)
vg_lips = body.vertex_groups.get("lips")
if vg_lips:
    for v in bme.vertices:
        for g in v.groups:
            if g.group == vg_lips.index and g.weight > 0.5:
                lips[v.index] = True
ears = np.zeros(len(bco), bool)
vg_ears = body.vertex_groups.get("ears")
if vg_ears:
    for v in bme.vertices:
        for g in v.groups:
            if g.group == vg_ears.index and g.weight > 0.5:
                ears[v.index] = True
# hair / beard regions from lines around the head (angle phi: 0 = front, 90 = side, 180 = back; symmetric)
phi = np.degrees(np.abs(np.arctan2(bco[:, 0], -(bco[:, 1] - hc_["head_cy"]))))
zc_ = bco[:, 2]
head = (zc_ > hc_["z_min"]) & (np.abs(bco[:, 0]) < 0.16)
hl = np.interp(phi, hc_["hairline"]["phi"], hc_["hairline"]["z"])
bt = np.interp(phi, hc_["beard_top"]["phi"], hc_["beard_top"]["z"])
bb = np.interp(phi, hc_["beard_bottom"]["phi"], hc_["beard_bottom"]["z"])
is_hair = head & (zc_ > hl) & ~ears
is_beard = head & (zc_ < bt) & (zc_ > bb) & (phi <= hc_["beard_max_phi"]) & ~lips & ~ears & ~is_hair
bedges = np.empty(len(bme.edges) * 2, dtype=np.int64)
bme.edges.foreach_get("vertices", bedges)
bedges = bedges.reshape(-1, 2)


def clean_face_region(vmask):
    """Faces fully inside vmask, then cleaned: faces with < 2 edge-neighbours in the region are dropped
    (no bow-ties or dangling faces, so the shell rim stays manifold) and pinholes are filled."""
    polys = bme.polygons
    inside = np.array([all(vmask[k] for k in p.vertices) for p in polys])
    # face adjacency through shared edges
    edge_faces = {}
    for p in polys:
        for ek in p.edge_keys:
            edge_faces.setdefault(ek, []).append(p.index)
    nbrs = [[] for _ in polys]
    for fl in edge_faces.values():
        if len(fl) == 2:
            nbrs[fl[0]].append(fl[1])
            nbrs[fl[1]].append(fl[0])
    for _ in range(4):
        cnt = np.array([sum(inside[j] for j in nbrs[i]) for i in range(len(polys))])
        add = ~inside & (cnt >= 3)
        drop = inside & (cnt < 2)
        inside = (inside | add) & ~drop
    # a vertex where the region touches itself only through that vertex (bow-tie) -> drop one fan side
    for _ in range(3):
        bad = False
        vfaces = {}
        for i in np.nonzero(inside)[0]:
            for k in polys[i].vertices:
                vfaces.setdefault(k, []).append(i)
        for k, fl in vfaces.items():
            # connected components of fl through shared edges
            fl_set = set(fl)
            seen, comps = set(), 0
            for f0 in fl:
                if f0 in seen:
                    continue
                comps += 1
                stack = [f0]
                while stack:
                    f = stack.pop()
                    if f in seen:
                        continue
                    seen.add(f)
                    stack.extend(j for j in nbrs[f] if j in fl_set and j not in seen and k in polys[j].vertices)
            if comps > 1:
                for f in fl[1:]:
                    inside[f] = False
                bad = True
        if not bad:
            break
    return [int(i) for i in np.nonzero(inside)[0]]


def shell(name, vmask, zone, min_off, max_off, spikes=None):
    fidx = clean_face_region(vmask)
    bm = bmesh.new()
    edge_count = {}
    for fi in fidx:
        vs = list(bme.polygons[fi].vertices)
        for a, b in zip(vs, vs[1:] + vs[:1]):
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
    bnd = {k for e, c in edge_count.items() if c == 1 for k in e}
    used = sorted({k for fi in fidx for k in bme.polygons[fi].vertices})
    vo, vi = {}, {}
    for k in used:
        p, nrm = bco[k], bno[k]
        off = float(np.clip((hit_pt[k] - p) @ nrm + 0.002, min_off, max_off)) if not np.isnan(hit_pt[k, 0]) else min_off
        if k in bnd:
            off = min_off * 0.35
        vo[k] = bm.verts.new(tuple(p + nrm * off))
        vi[k] = bm.verts.new(tuple(p - nrm * 0.004))
    fo = []
    for fi in fidx:
        vs = list(bme.polygons[fi].vertices)
        fo.append(bm.faces.new([vo[k] for k in vs]))
        bm.faces.new([vi[k] for k in reversed(vs)])
    for (a, b), c in edge_count.items():
        if c == 1:
            bm.faces.new((vo[a], vo[b], vi[b], vi[a]))
    for f in bm.faces:
        f.material_index = G.Z[zone]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    nsp = 0
    if spikes:
        cand = [f for f in fo if f.is_valid and f.calc_center_median().z > spikes["z_min"] and len(f.verts) == 4]
        rng.shuffle(cand)
        chosen = []
        for f in cand:
            c = f.calc_center_median()
            if all((c - g.calc_center_median()).length > spikes["spacing"] for g in chosen):
                chosen.append(f)
            if len(chosen) >= spikes["count"]:
                break
        for f in chosen:
            nrm = f.normal.copy()
            c = f.calc_center_median()
            back = Vector((0.0, 1.0, 0.7)).normalized()
            side = Vector((1.0 if c.x > 0 else -1.0, 0.0, 0.0)) * (0.25 if abs(c.x) > 0.03 else 0.0)
            d = (nrm * 0.65 + back * spikes["sweep"] + side).normalized()
            res = bmesh.ops.extrude_discrete_faces(bm, faces=[f])
            nf = res["faces"][0]
            L = spikes["length"] * rng.uniform(0.6, 1.25)
            for v in nf.verts:
                v.co = c + (v.co - c) * spikes["tip_scale"] + d * L
            nsp += 1
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    report.setdefault("shells", {})[name] = {"faces_from_body": len(fidx), "spikes": nsp}
    return finish(bm, name)


shell("HAIR", is_hair, "hair", hc_["min_off"], hc_["max_off"], spikes=hc_["spikes"])
shell("BEARD", is_beard, "beard", hc_["beard_min_off"], hc_["beard_max_off"], spikes=hc_.get("beard_spikes"))
report["hair_verts"] = int(is_hair.sum())
report["beard_verts"] = int(is_beard.sum())


ref.hide_render = True
ref.hide_viewport = True
ref.hide_set(True)
# keep the reference in the file for review, in its own collection
refc = get_collection("REF_sculpt_reference")
for c in list(ref.users_collection):
    c.objects.unlink(ref)
refc.objects.link(ref)
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
