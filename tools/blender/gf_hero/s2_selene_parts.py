"""Stage 2, Selene: the hair, the crystal crown, the outfit and the cloth around the fitted body (s2_body_fit.py).

Built procedurally from art/characters/selene/stage2_parts.json (every number measured on the approved front and the
recentred stage-1 blockout; see its _doc keys), never copied from the blockout. Every part is closed; rigid pieces are
separate connected pieces so stage 3 can weight each one 100 % to one bone, cloth pieces are regular grids (rows =
the suggested x_ chain links). The suggested bone / chain of every piece is in the report, and the face attribute
gf_piece indexes it. Paint zones: ZONES below (face material index). The two floating coils of the concept are
weapon / VFX and are not built; the hands are empty.

Objects:
  BODY       the fitted hm08 body (legs given the leggings' girth): skin (head, arms, fingers), suit (torso), legging
             (legs), glove (forearm and hand under the gauntlet), eyes; the painter blends skin / suit by the neckline
  HAIR       the swept-up hair shell over the scalp, the high bun (twisted knot) with a glowing band, face-framing strands
             and swept clumps rising to the bun
  CROWN      six storm-crystal shards (gold-rimmed), one rigid piece each on x_crown_01..06 (head_top children)
  COLLAR     the high collar (gold rims), the collar gem in its gold setting, the harness straps, the neckline trim, the
             waist straps
  BELT       the belt with gold rims, two big gold rings, the hip plates
  SHOULDERS  the shoulder ornaments: armlet band, gold ring, two pointed blades per side
  CAPES      the two deep storm-blue outer capes (cloth, x_cape_L/R chains)
  MANTLES    the two pale shoulder drapes in front of the capes (cloth, x_mantle chains)
  PANELS     the two hip panels hanging from the belt rings (cloth, x_panel chains)
  TABARD     the pale front tabard and the deep back panel (cloth, x_tabard / x_back chains)
  GAUNTLETS  bracers with a pointed top edge, back-of-hand plates, ten ice-blue claw caps
  GREAVES    greaves with a point at the front, pointed knee cops, leaf fins on the outside of the knees
  SABATONS   heeled pointed sabatons: ankle shaft, foot shell, heel block

  blender -b -P tools/blender/gf_hero/s2_selene_parts.py -- <body.blend> <retopo_start.blend> <parts.json> <fit.json> \
          <mh_landmarks.json> <out.blend> [--report <json>] [--fit-report <body_fit.json>]
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

import s2_geom as G0  # noqa: E402
import s2_valdris_geom as VG  # noqa: E402
from s2lib import (connected_parts, get_co, get_collection, hex_rgb, log, mesh_stats, mirror_map, opt, read_json,  # noqa: E402
                   save_blend, script_args, set_co, srgb_to_linear, symmetrize, write_json)

ZONES = ["skin", "hair", "eye", "suit", "legging", "glove", "gold", "plate", "cape", "panel", "tabard", "gem", "crystal", "claw"]
Z = {n: i for i, n in enumerate(ZONES)}
# the plate helpers of s2_valdris_geom look zones up in their module-level Z: point them at Selene's zones (this process
# only; the shared module is not edited, and every call below passes its zones explicitly)
VG.Z = Z
VG.ZONES = ZONES

argv = script_args(__doc__)
if len(argv) < 6:
    raise SystemExit(__doc__)
BODY, REF, CFG, FIT, MHLM, OUT = (os.path.abspath(a) for a in argv[:6])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(CFG)
fit = read_json(FIT)
mh = read_json(MHLM)
rng = random.Random(cfg.get("seed", 23))
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
report = {"parts": {}, "pieces": {}, "zones": ZONES}
col = get_collection("SELENE_stage2")
if body.name not in col.objects:
    col.objects.link(body)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def nrm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


# ==============================================================================================================
# BODY: leg girth (the leggings), then the sampling structures
# ==============================================================================================================
bc = cfg["body"]
me = body.data
co = get_co(me)
mm = mirror_map(co, tol=1e-4)
lr_tab = np.array(bc["leg_radius"], dtype=np.float64)
legs = (co[:, 2] < bc["leg_blend_top"][1]) & (np.abs(co[:, 0]) < 0.3)
leg_log = []
new = co.copy()
for sd in (1, -1):
    side = legs & (co[:, 0] * sd > 0)
    for z0 in np.arange(0.05, bc["leg_blend_top"][1] + 0.01, 0.01):
        sl = side & (np.abs(co[:, 2] - z0) < 0.006)
        if sl.sum() < 6:
            continue
        c = co[sl][:, :2].mean(0)
        r = np.linalg.norm(co[sl][:, :2] - c, axis=1).mean()
        tgt = float(np.interp(z0, lr_tab[:, 0], lr_tab[:, 1]))
        k = float(smoothstep(*bc["leg_blend_bottom"], z0) * (1 - smoothstep(*bc["leg_blend_top"], z0)))
        s = 1.0 + (np.clip(tgt / r, 0.8, 1.7) - 1.0) * k
        new[sl, :2] = c + (co[sl][:, :2] - c) * s
        if sd == 1 and abs(z0 * 100 - round(z0 * 100 / 10) * 10) < 0.5:
            leg_log.append([round(float(z0), 2), round(float(r), 4), round(tgt, 4), round(float(s), 3)])
new[:, 0] = np.where(legs & (np.abs(new[:, 0]) < 0.004) & (np.abs(co[:, 0]) > 1e-5), np.sign(co[:, 0]) * 0.004, new[:, 0])
new = symmetrize(new, mm)
set_co(me, new)
me.update()
report["leg_girth"] = {"z_r_before_target_scale": leg_log}
log("leg girth", leg_log)
dg = bpy.context.evaluated_depsgraph_get()
body_bvh = BVHTree.FromObject(body, dg)
co = get_co(me)


def ray(o, d, maxd=2.0):
    loc, n, i, dist = body_bvh.ray_cast(Vector(tuple(o)), Vector(tuple(d)), maxd)
    if loc is None:
        return None, None, None
    n = np.array(n)
    if n @ np.asarray(d) > 0:
        n = -n
    return np.array(loc), n, dist


def front_y(x, z, from_back=False):
    """y of the body's front (or back) surface at (x, z), None when the ray misses."""
    p, n, d = ray((x, 1.0 if from_back else -1.0, z), (0, -1.0 if from_back else 1.0, 0))
    return None if p is None else float(p[1])


def slab_centre(zc, mask_fn, win=0.03):
    """Centre of the body vertices near height zc (triangle-weighted window: the reduced hm08 has a ring every
    2-6 cm on the limbs)."""
    m = (np.abs(co[:, 2] - zc) < win) & mask_fn(co)
    if not m.any():
        return None
    w = 1.0 - np.abs(co[m, 2] - zc) / win
    c = (co[m] * w[:, None]).sum(0) / w.sum()
    c[2] = zc
    return c


LEG_TAB = {}
for _sd in (1, -1):
    _rows = []
    for _z in np.arange(0.02, 1.16, 0.005):
        _m = (np.abs(co[:, 2] - _z) < 0.004) & (co[:, 0] * _sd > 0) & (np.abs(co[:, 0]) < 0.25)
        if _m.sum() >= 5:
            _rows.append([_z] + co[_m][:, :2].mean(0).tolist())
    LEG_TAB[_sd] = np.array(_rows)


def leg_axis(z, sd):
    """The leg's centre at height z, interpolated between the body's own rings (the reduced hm08 leg has a ring
    every 2-14 cm)."""
    t = LEG_TAB[sd]
    return np.array([np.interp(z, t[:, 0], t[:, 1]), np.interp(z, t[:, 0], t[:, 2]), z])


def gauss2(R, sig_u, sig_v, periodic_u):
    out = R.copy()
    for ax, sig, per in ((0, sig_u, periodic_u), (1, sig_v, False)):
        if sig <= 0:
            continue
        r = max(1, int(3 * sig))
        w = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        w /= w.sum()
        n = out.shape[ax]
        acc = np.zeros_like(out)
        for wk, d in zip(w, range(-r, r + 1)):
            if per:
                acc += wk * np.roll(out, d, axis=ax)
            else:
                acc += wk * np.take(out, np.clip(np.arange(n) + d, 0, n - 1), axis=ax)
        out = acc
    return out


def radial_grid(nu, nv, cd_fn, periodic_u, sig=(1.0, 0.7), maxd=0.5, r_min=0.0):
    """Body distance along the ray cd_fn(i, j) -> (C, D) from an axis point outward (misses: column / grid median),
    smoothed. Returns C, D, R arrays."""
    C = np.zeros((nu, nv, 3))
    D = np.zeros((nu, nv, 3))
    R = np.full((nu, nv), np.nan)
    for i in range(nu):
        for j in range(nv):
            c, d = cd_fn(i, j)
            d = nrm(d)
            C[i, j], D[i, j] = c, d
            p, n, dist = ray(c, d, maxd)
            if p is not None:
                R[i, j] = dist
    for j in range(nv):
        colj = R[:, j]
        if np.isnan(colj).all():
            R[:, j] = np.nanmedian(R) if not np.isnan(R).all() else 0.05
        else:
            R[:, j] = np.where(np.isnan(colj), np.nanmedian(colj), colj)
    R = np.maximum(gauss2(R, sig[0], sig[1], periodic_u), r_min)
    return C, D, R


# ---- zone preview materials (palette base tones; the texture step replaces them with the atlas) --------------
zone_hex = {"skin": "#C6ABA1", "hair": "#ADB1BD", "eye": "#A9F0FC", "suit": "#1E252B", "legging": "#222C3F", "glove": "#303540",
            "gold": "#8F7D68", "plate": "#2C303B", "cape": "#213F6F", "panel": "#40648D", "tabard": "#3F5D8D", "gem": "#5BD4F4",
            "crystal": "#A4EFFA", "claw": "#98E8FC"}
mats = []
for zname in ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    c = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    m.diffuse_color = c
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = c
    if zname in ("eye", "gem", "crystal", "claw"):
        bsdf.inputs["Emission Color"].default_value = c
        bsdf.inputs["Emission Strength"].default_value = 2.0
    mats.append(m)

PIECE_LAYER = "gf_piece"
piece_table = []


def new_bm():
    bm = bmesh.new()
    VG.ensure_mask(bm)
    bm.faces.layers.int.new(PIECE_LAYER)
    return bm


def reg(bm, faces, name, bone, **extra):
    lay = bm.faces.layers.int.get(PIECE_LAYER)
    pid = len(piece_table)
    for f in faces:
        if f.is_valid:
            f[lay] = pid
    piece_table.append(dict({"id": pid, "name": name, "bone": bone}, **extra))
    return pid


def finish(bm, name):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lay = bm.verts.layers.float_color.get(VG.G0.MASK_LAYER)
    for v in bm.verts:
        if v[lay][3] < 0.5:
            v[lay] = (0.5, 0.5, 0.5, 1.0)
    me_ = bpy.data.meshes.new(name)
    bm.to_mesh(me_)
    bm.free()
    ob = bpy.data.objects.new(name, me_)
    for m in mats:
        me_.materials.append(m)
    for p in me_.polygons:
        p.use_smooth = False
    col.objects.link(ob)
    st = mesh_stats(ob)
    report["parts"][name] = st
    pl = me_.attributes.get(PIECE_LAYER)
    if pl is not None:
        ids = np.empty(len(me_.polygons), dtype=np.int32)
        pl.data.foreach_get("value", ids)
        report["pieces"][name] = sorted({piece_table[i]["name"] + " -> " + piece_table[i]["bone"] for i in set(ids.tolist())})
    log("%-10s %6d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d" % (
        name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"]))
    return ob


def torus(bm, c, axis, R, r, zone, nu=16, nv=6, rand=None):
    VG.ensure_mask(bm)
    d, u, v = VG.frame_axes(axis)
    c = np.asarray(c, dtype=np.float64)
    vs = []
    for i in range(nu):
        a = 2 * math.pi * i / nu
        row = []
        for j in range(nv):
            b = 2 * math.pi * j / nv
            p = c + (u * math.cos(a) + v * math.sin(a)) * (R + r * math.cos(b)) + d * r * math.sin(b)
            row.append(bm.verts.new(tuple(p)))
        vs.append(row)
    fs = []
    for i in range(nu):
        for j in range(nv):
            f = bm.faces.new((vs[i][j], vs[(i + 1) % nu][j], vs[(i + 1) % nu][(j + 1) % nv], vs[i][(j + 1) % nv]))
            fs.append(f)
    VG.tag(fs, zone)
    for i in range(nu):
        for j in range(nv):
            VG.set_mask(bm, [vs[i][j]], 0.35 + 0.65 * max(0.0, math.cos(2 * math.pi * j / nv)), rand)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def kite(bm, centre, length_dir, facing, L, w, depth, chamfer, zones, shape="hex", taper=0.8, widest=0.12, rand=None,
         back_chamfer=True):
    """A gold-rimmed pointed plate / crystal: an elongated hexagon (or a kite) in the plane spanned by length_dir and
    facing x length_dir, extruded along facing (depth, centred), chamfered on the front (and the back)."""
    Nd = nrm(facing)
    B = nrm(np.asarray(length_dir) - Nd * (np.asarray(length_dir) @ Nd))
    A = np.cross(B, Nd)
    if shape == "kite":
        poly = [(0.0, L / 2), (w / 2, L * widest), (0.0, -L / 2), (-w / 2, L * widest)]
    elif shape == "leaf":
        poly = [(0.0, L / 2), (w * 0.42, L * 0.22), (w / 2, -L * 0.1), (w * 0.3, -L * 0.38), (0.0, -L / 2),
                (-w * 0.3, -L * 0.38), (-w / 2, -L * 0.1), (-w * 0.42, L * 0.22)]
    else:
        poly = [(0.0, L / 2), (w / 2, L * widest), (w * 0.42, -L * 0.12), (0.0, -L / 2), (-w * 0.42, -L * 0.12), (-w / 2, L * widest)]
    fs = VG.prism(bm, poly, centre, A, B, Nd, -depth / 2, depth / 2, chamfer, zones, taper=taper, rand=rand,
                  chamfer_back=chamfer if back_chamfer else 0.0)
    return fs


def sheet(bm, S, thick, zone, out_ref, u_frac, v_frac, rand, edge_zone=None):
    """A closed cloth sheet from the outer surface grid S (nu, nv, 3): grid_solid, then the cloth mask
    (R = v, G = u) on every vertex so the painter can fade deep -> pale toward the hem."""
    lay = VG.ensure_mask(bm)
    nu, nv = S.shape[:2]
    N = VG.grid_normals(S, False, out_ref)
    zf = zone if edge_zone is None else (lambda i, j: edge_zone(i, j) or zone)
    fs, vo, vi = VG.grid_solid(bm, S, thick, zf, periodic_u=False, N=N, zone_in=zone, wall_zone=(zone, zone, zone, zone),
                               rand=rand, edge_mask=False)
    for i in range(nu):
        for j in range(nv):
            for vv in (vo[i][j], vi[i][j]):
                vv[lay] = (float(v_frac[i, j]), float(u_frac[i, j]), rand, 1.0)
    return fs


def interp_prof(v, vk, vals):
    return np.interp(v, vk, vals)


def hem_offset(u, tatters):
    t = np.array(tatters, dtype=np.float64)
    return np.interp(u, t[:, 0], t[:, 1])


# ---- TPS replica: MakeHuman joints -> this body (fingertips for the claws) ---------------------------------------
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
    p = np.array(p, dtype=np.float64)
    k = np.clip((abs(p[0]) - lr["hand_from_abs_x"]) / 0.03, 0, 1)
    s = 1 + (lr["hand_scale"] - 1) * k
    p[1] = lr["axis_y"] + (p[1] - lr["axis_y"]) * s
    p[2] = lr["axis_z"] + (p[2] - lr["axis_z"]) * s
    return p


def joint(name):
    return hand_warp(tps(np.array(mh["joints"][name]["head"]))[0]), hand_warp(tps(np.array(mh["joints"][name]["tail"]))[0])


LM = fit["landmarks"]
AX_Y, AX_Z = lr["axis_y"], lr["axis_z"]

# ==============================================================================================================
# HAIR: the shell over the scalp, the bun, the locks
# ==============================================================================================================
hc = cfg["hair"]
HC = np.array(hc["centre"])


def azimuth(p):
    """0 = the face (-Y), 90 = the side, 180 = the nape; |deg|"""
    return np.degrees(np.abs(np.arctan2(p[..., 0] - HC[0], -(p[..., 1] - HC[1]))))


bm = new_bm()
lay_mask = VG.ensure_mask(bm)
bmb = bmesh.new()
bmb.from_mesh(me)
bmb.verts.ensure_lookup_table()
bmb.faces.ensure_lookup_table()
parts_b = sorted(connected_parts(bmb), key=len)
eye_faces = set(f for pv in parts_b[:-1] for v in pv for f in v.link_faces)
dl = bmb.verts.layers.deform.active
eg = body.vertex_groups.get("ears")
ear_i = eg.index if eg else None


def is_ear(f):
    return ear_i is not None and dl is not None and sum(1 for v in f.verts if ear_i in v[dl] and v[dl][ear_i] > 0.3) >= 2


hz = lambda az: np.interp(az, hc["hairline_az"], hc["hairline_z"])  # noqa: E731
hair_faces = []
for f in bmb.faces:
    if f in eye_faces or is_ear(f):
        continue
    c = np.array(f.calc_center_median())
    if c[2] < 1.84 or abs(c[0]) > 0.14:
        continue
    if c[2] > hz(azimuth(c)):
        hair_faces.append(f)
hv = sorted({v for f in hair_faces for v in f.verts}, key=lambda v: v.index)
bmb.normal_update()
hv_idx = {v: k for k, v in enumerate(hv)}
P0 = np.array([tuple(v.co) for v in hv])
N0 = np.array([tuple(v.normal) for v in hv])
# boundary verts of the hair region
hair_set = set(hair_faces)
bnd = np.zeros(len(hv), bool)
for v in hv:
    if any(f not in hair_set for f in v.link_faces):
        bnd[hv_idx[v]] = True
# thickness: rim -> crown; distance from the rim over the mesh (in rings) makes the swell gradual
ring = np.where(bnd, 0, 99)
for it in range(1, 12):
    for v in hv:
        k = hv_idx[v]
        if ring[k] == 99 and any(ring[hv_idx[w]] == it - 1 for e in v.link_edges for w in [e.other_vert(v)] if w in hv_idx):
            ring[k] = it
ring = np.where(ring == 99, 11, ring)
az0 = azimuth(P0)
t_full = np.where(az0 > 120, hc["thick_back"], hc["thick_crown"])
t_full = t_full * (0.75 + 0.25 * smoothstep(1.98, 2.07, P0[:, 2]))
th = hc["thick_rim"] + (t_full - hc["thick_rim"]) * smoothstep(0, 4, ring)
outer = P0 + N0 * th[:, None]
inner = P0 - N0 * hc["inner"]
vo = [bm.verts.new(tuple(p)) for p in outer]
vi = [bm.verts.new(tuple(p)) for p in inner]
hfs = []
for f in hair_faces:
    ids = [hv_idx[v] for v in f.verts]
    hfs.append(bm.faces.new([vo[k] for k in ids]))
    hfs.append(bm.faces.new([vi[k] for k in reversed(ids)]))
for e in {e for f in hair_faces for e in f.edges}:
    if sum(1 for f in e.link_faces if f in hair_set) == 1:
        a, b = hv_idx[e.verts[0]], hv_idx[e.verts[1]]
        hfs.append(bm.faces.new((vo[a], vo[b], vi[b], vi[a])))
VG.tag(hfs, "hair")
for k in range(len(hv)):
    m = 0.3 + 0.5 * smoothstep(0, 5, ring[k])
    vo[k][lay_mask] = (m, 0.5, m, 1.0)
    vi[k][lay_mask] = (0.2, 0.5, 0.2, 1.0)
bmesh.ops.recalc_face_normals(bm, faces=hfs)
reg(bm, hfs, "HAIR_SHELL", "head")
bmb.free()
shell_top = float(outer[:, 2].max())
report["hair_shell"] = {"faces": len(hair_faces), "top_z": round(shell_top, 4), "rim_verts": int(bnd.sum())}

# the bun: a twisted lofted knot on the crown
bn = hc["bun"]
rt = np.array(bn["radius"], dtype=np.float64)
rings = []
for k in range(bn["rings"]):
    t = k / (bn["rings"] - 1)
    z = bn["z"][0] + (bn["z"][1] - bn["z"][0]) * t
    rr = float(np.interp(t, rt[:, 0], rt[:, 1]))
    row = []
    for s in range(bn["sides"]):
        a = 2 * math.pi * s / bn["sides"]
        mod = 1 + bn["lobe_amp"] * math.cos(bn["lobes"] * a + 2 * math.pi * bn["twist_turns"] * t) * math.sin(math.pi * min(1.0, t * 1.15))
        row.append((bn["centre"][0] + math.sin(a) * rr * mod, bn["centre"][1] - math.cos(a) * rr * mod * 0.92, z))
    rings.append(row)
S = np.array(rings).transpose(1, 0, 2)
fs = VG.loft_solid(bm, S, "hair", rand=0.6)
for f in fs:
    for v in f.verts:
        z = v.co.z
        t = (z - bn["z"][0]) / (bn["z"][1] - bn["z"][0])
        v[lay_mask] = (0.45 + 0.5 * math.sin(math.pi * min(1, max(0, t))), 0.6, 0.5, 1.0)
reg(bm, fs, "HAIR_BUN", "head")
fs = VG.cylinder(bm, (0, bn["centre"][1], bn["band_z"] - bn["band_h"] / 2), (0, bn["centre"][1], bn["band_z"] + bn["band_h"] / 2),
                 bn["band_r"], bn["band_r"] * 0.93, "gem", sides=16, bevel=0.002)
reg(bm, fs, "HAIR_BAND", "head")
# locks
nlocks = 0
for lk in hc["locks"]:
    for sd in ((1,) if lk.get("centre") else (1, -1)):
        root = np.array(lk["root"], dtype=np.float64) * [sd, 1, 1]
        p_s, n_s, _ = ray(HC + (root - HC) * 0.5, root - HC, 0.3)
        if p_s is None:
            p_s, n_s = root, nrm(root - HC)
        # face-framing strands start just under the shell; the swept clumps sit ON the shell (they break it into locks)
        base = p_s + n_s * (float(np.interp(azimuth(p_s), [0, 180], [hc["thick_crown"], hc["thick_back"]])) + 0.003
                            if lk.get("sweep") else 0.006)
        if lk.get("sweep"):
            to = np.array(lk["to"], dtype=np.float64) * [sd, 1, 1]
            d0 = nrm(to - base) + n_s * 0.25
            bend = nrm(to - base) - n_s * 0.1
        else:
            d0 = np.array(lk["dir"], dtype=np.float64) * [sd, 1, 1]
            bend = np.array(lk["bend"], dtype=np.float64) * [sd, 1, 1]
        fs = G0.lock(bm, base, n_s, nrm(d0), nrm(bend), lk["len"], lk["w"], lk["t"], rng, "skin", 6)
        VG.tag(fs, "hair")
        reg(bm, fs, "HAIR_LOCK", "head")
        nlocks += 1
report["hair_locks"] = nlocks
finish(bm, "HAIR")

# ==============================================================================================================
# CROWN: six shards, one bone each
# ==============================================================================================================
cr = cfg["crown"]
bm = new_bm()
k = 0
for sd in (1, -1):
    for sh in cr["shards"]:
        x, y, z, L, w, lean = sh
        c = np.array([sd * x, y, z])
        a = math.radians(lean) * sd
        length_dir = np.array([-math.sin(a), 0.0, math.cos(a)])
        radial = nrm([sd, 0.0, 0.0])
        facing = nrm(radial * (1 - cr["face_front"]) + np.array([0.0, -1.0, 0.0]) * cr["face_front"])
        k += 1
        fs = kite(bm, c, length_dir, facing, L, w, cr["depth"], cr["chamfer"],
                  {"front": "crystal", "side": "gold", "chamfer": "gold", "back": "crystal", "chamfer_back": "gold"},
                  shape="hex", taper=0.72, rand=rng.random())
        reg(bm, fs, "CROWN_SHARD_%02d" % k, "x_crown_%02d" % k, parent="head_top", rigid=True,
            centre=[round(float(v), 4) for v in c])
finish(bm, "CROWN")

# ==============================================================================================================
# COLLAR: collar tube, gem, straps, trims
# ==============================================================================================================
cc = cfg["collar"]
bm = new_bm()


def neck_centre(z):
    c = slab_centre(z, lambda p: (np.abs(p[:, 0]) < 0.09) & (p[:, 1] > -0.12))
    return np.array([0.0, c[1] if c is not None else 0.01, z])


NUc, NVc = 28, 6
thc = np.arange(NUc) * 2 * math.pi / NUc          # 0 = front (-Y), pi/2 = her left


def collar_z(th, v):
    front = math.cos(th)                           # 1 at the front, -1 at the back
    fz = lambda f, s, b: (f if front > 0 else b) * abs(front) ** 1.5 + s * (1 - abs(front) ** 1.5)  # noqa: E731
    zb = fz(cc["z_bottom_front"], (cc["z_bottom_front"] + cc["z_bottom_back"]) / 2 + 0.01, cc["z_bottom_back"])
    zt = fz(cc["z_top_front"], cc["z_top_side"], cc["z_top_back"])
    if front > 0.97:                               # the small V at the front of the top edge
        zt -= 0.012 * (front - 0.97) / 0.03
    return zb + (zt - zb) * v


def cd_collar(i, j):
    z = collar_z(thc[i], j / (NVc - 1))
    c = neck_centre(z)
    return c, np.array([math.sin(thc[i]), -math.cos(thc[i]), 0.0])


C, D, R = radial_grid(NUc, NVc, cd_collar, True, sig=(1.2, 0.6))
v_ = np.linspace(0, 1, NVc)[None, :]
Sg = C + D * (R + cc["gap"] + cc["thick"] + cc["flare"] * v_ ** 2)[..., None]
fs, _, _ = VG.grid_solid(bm, Sg, cc["thick"], lambda i, j: "gold" if j in (0, NVc - 2) else "suit", periodic_u=True,
                         out_ref=lambda p: np.array([p[0], p[1] - 0.01, 0.0]), zone_in="suit", wall_zone=("gold", "gold", "gold", "gold"),
                         rand=0.4)
reg(bm, fs, "COLLAR", "neck_01")
# the gem in its setting, at the collar base over the sternum
gm = cc["gem"]
yf = front_y(0.0, gm["z"])
gc = np.array([0.0, yf - 0.016, gm["z"]])
fs = kite(bm, gc + [0, -0.004, 0], (0, 0, 1), (0, -1, 0.15), gm["setting_len"], gm["setting_w"], 0.008, 0.003,
          {"front": "gold", "side": "gold", "chamfer": "gold", "back": "gold", "chamfer_back": "gold"}, shape="kite", taper=0.9,
          widest=0.1)
reg(bm, fs, "GEM_SETTING", "spine_03")
fs = kite(bm, gc + [0, -0.014, 0], (0, 0, 1), (0, -1, 0.15), gm["len"], gm["w"], gm["depth"], 0.005,
          {"front": "gem", "side": "gem", "chamfer": "gem", "back": "gem", "chamfer_back": "gem"}, shape="kite", taper=0.35,
          widest=0.1, back_chamfer=False)
reg(bm, fs, "COLLAR_GEM", "spine_03")


def densify(pts, step=0.012):
    pts = np.asarray(pts, dtype=np.float64)
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        for t in range(1, n + 1):
            out.append(a + (b - a) * t / n)
    return np.array(out)


def ribbon(bm, path_xz, width, th, off, zone, name, bone, from_back=False, rand=None):
    P = densify(path_xz)
    pts, ns = [], []
    for x, z in P:
        p, n, _ = ray((x, 1.0 if from_back else -1.0, z), (0, -1.0 if from_back else 1.0, 0))
        if p is None:
            continue
        pts.append(p)
        ns.append(n)
    if len(pts) < 2:
        return []
    pts, ns = np.array(pts), np.array(ns)
    for _ in range(2):
        ns[1:-1] = nrm(ns[:-2] + 2 * ns[1:-1] + ns[2:])
    T = np.gradient(pts, axis=0)
    Sd = nrm(np.cross(ns, T))
    S2 = np.stack([pts + ns * (off + th) - Sd * width / 2, pts + ns * (off + th) + Sd * width / 2], 1)
    N2 = np.stack([ns, ns], 1)
    fs, _, _ = VG.grid_solid(bm, S2, th, zone, periodic_u=False, N=N2, zone_in=zone, wall_zone=(zone,) * 4, rand=rand)
    reg(bm, fs, name, bone)
    return fs


for sd in (1, -1):
    for si, sp in enumerate(cc["straps"]):
        ribbon(bm, [(sd * x, z) for x, z in sp], cc["strap_w"], cc["ribbon_th"], cc["ribbon_off"], "gold",
               "HARNESS_STRAP_%d" % (si + 1), "spine_03", rand=0.3)
    ribbon(bm, [(sd * x, z) for x, z in cc["neckline"]], cc["trim_w"], cc["ribbon_th"], cc["ribbon_off"], "gold", "NECKLINE_TRIM",
           "spine_03", rand=0.35)
    for si, sp in enumerate(cc["waist_straps"]):
        ribbon(bm, [(sd * x, z) for x, z in sp], cc["strap_w"], cc["ribbon_th"], cc["ribbon_off"], "gold",
               "WAIST_STRAP_%d" % (si + 1), "spine_02", rand=0.3)
finish(bm, "COLLAR")

# ==============================================================================================================
# BELT: band, rings, hip plates
# ==============================================================================================================
be = cfg["belt"]
bm = new_bm()


def torso_centre(z):
    c = slab_centre(z, lambda p: np.abs(p[:, 0]) < 0.3)
    return np.array([0.0, c[1] if c is not None else 0.0, z])


NUb = 36
thb = np.arange(NUb) * 2 * math.pi / NUb
rows_b = [0.0, be["rim"], be["h"] - be["rim"], be["h"]]


def belt_zc(th):
    f = math.cos(th)
    zc = (be["z_front"] if f > 0 else be["z_back"]) * abs(f) ** 1.2 + be["z_side"] * (1 - abs(f) ** 1.2)
    if f > 0.9:
        zc -= 0.012 * (f - 0.9) / 0.1
    return zc


def cd_belt(i, j):
    z = belt_zc(thb[i]) - be["h"] / 2 + rows_b[j]
    return torso_centre(z), np.array([math.sin(thb[i]), -math.cos(thb[i]), 0.0])


C, D, R = radial_grid(NUb, 4, cd_belt, True, sig=(1.0, 1.0))
R[:] = R.max(axis=1, keepdims=True)
Sg = C + D * (R + be["gap"] + be["thick"])[..., None]
fs, _, _ = VG.grid_solid(bm, Sg, be["thick"], lambda i, j: "suit" if j == 1 else "gold", periodic_u=True,
                         out_ref=lambda p: np.array([p[0], p[1], 0.0]), zone_in="suit", wall_zone=("gold", "gold", "gold", "gold"),
                         rand=0.45)
reg(bm, fs, "BELT", "pelvis")
belt_front = {}
for sd in (1, -1):
    x = sd * be["ring_x"]
    yf = front_y(x, be["ring_z"])
    rc = np.array([x, yf - be["gap"] - be["thick"] - be["ring_r"] - 0.002, be["ring_z"]])
    fs = torus(bm, rc, (0, -1, 0), be["ring_R"], be["ring_r"], "gold", 18, 6, rand=0.7)
    reg(bm, fs, "BELT_RING_%s" % ("L" if sd > 0 else "R"), "pelvis")
    belt_front[sd] = rc
    hp = be["hip_plate"]
    hx = sd * hp["x"]
    p, n, _ = ray((hx * 2.2, torso_centre(hp["z"])[1] - 0.02, hp["z"]), (-sd, 0.0, 0.0))
    if p is None:
        p, n = np.array([hx, -0.02, hp["z"]]), np.array([sd, -0.3, 0.0])
    n = nrm(n * [1, 1, 0] + np.array([0, -0.35, 0]))
    fs = kite(bm, p + n * (be["gap"] + hp["depth"] / 2 + 0.004), (0, 0, 1), n, hp["h"], hp["w"], hp["depth"], hp["chamfer"],
              {"front": "plate", "side": "gold", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, shape="kite",
              taper=0.85, widest=0.34)
    reg(bm, fs, "HIP_PLATE_%s" % ("L" if sd > 0 else "R"), "pelvis")
finish(bm, "BELT")

# ==============================================================================================================
# SHOULDERS: armlet, ring, blades
# ==============================================================================================================
so = cfg["shoulders"]
bm = new_bm()
NUs, NVs = 20, 5
ths = np.arange(NUs) * 2 * math.pi / NUs           # around the arm: 0 = up, pi/2 = front (-Y)
for sd in (1, -1):
    xs = np.linspace(so["x"][0], so["x"][1], NVs)

    def cd_sh(i, j, sd=sd, xs=xs):
        c = np.array([sd * xs[j], AX_Y, AX_Z])
        return c, np.array([0.0, -math.sin(ths[i]), math.cos(ths[i])])
    C, D, R = radial_grid(NUs, NVs, cd_sh, True, sig=(1.0, 0.8))
    R[:] = R.max(axis=0, keepdims=True) * 0.6 + R * 0.4
    vv = np.linspace(0, 1, NVs)[None, :]
    Sg = C + D * (R + so["gap"] + so["thick"] + so["bulge"] * np.sin(math.pi * vv))[..., None]
    fs, _, _ = VG.grid_solid(bm, Sg, so["thick"], lambda i, j: "gold" if j in (0, NVs - 2) else "plate", periodic_u=True,
                             out_ref=lambda p, sd=sd: np.array([0.0, p[1] - AX_Y, p[2] - AX_Z]), zone_in="plate",
                             wall_zone=("gold", "gold", "gold", "gold"), rand=0.55)
    S_side = "L" if sd > 0 else "R"
    reg(bm, fs, "ARMLET_" + S_side, "upperarm_" + S_side.lower())
    r_out = float((R[:, NVs // 2]).max()) + so["gap"] + so["thick"] + so["bulge"]
    fs = torus(bm, (sd * (so["x"][0] + so["x"][1]) / 2, AX_Y - r_out - so["ring_r"], AX_Z - 0.004), (0, -1, 0), so["ring_R"],
               so["ring_r"], "gold", 16, 6, rand=0.7)
    reg(bm, fs, "ARMLET_RING_" + S_side, "upperarm_" + S_side.lower())
    for bi, bl in enumerate(so["blades"]):
        at = np.array(bl["at"]) * [sd, 1, 1]
        d = nrm(np.array(bl["dir"]) * [sd, 1, 1])
        fac = nrm(np.cross(d, [0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else [0.0, -1.0, 0.0])
        if fac @ np.array([0.0, -1.0, 0.0]) < 0 and bi == 0:
            fac = -fac
        fs = kite(bm, at + d * bl["len"] * 0.45, d, fac, bl["len"], bl["w"], 0.009, 0.0035,
                  {"front": "plate", "side": "gold", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, shape="kite",
                  taper=0.85, widest=-0.2)
        reg(bm, fs, "ARMLET_BLADE_%d_%s" % (bi + 1, S_side), "upperarm_" + S_side.lower())
finish(bm, "SHOULDERS")

# ==============================================================================================================
# CLOTH: capes, mantles, panels, tabard + back panel
# ==============================================================================================================
cl = cfg["cloth"]
TH = cl["thick"]


def chain_rows(chain, S_side):
    return [c.replace("{S}", S_side) for c in chain]


def side_sheet(sp, sd, kind):
    """Cape / mantle: a sheet hanging from the armlet, profiles by v, tatters on the hem, folds across u."""
    nu, nv = sp["nu"], sp["nv"]
    U = np.linspace(0, 1, nu)[:, None] * np.ones((1, nv))
    V = np.ones((nu, 1)) * np.linspace(0, 1, nv)[None, :]
    z_top = sp["z"][0]
    z_base = interp_prof(V, sp["v"], sp["z"])
    hem = hem_offset(U, sp["tatters"])
    ramp = smoothstep(0.55, 1.0, V)
    z = z_base + hem * ramp
    x_in = interp_prof(V, sp["v"], sp["x_in"])
    x_out = interp_prof(V, sp["v"], sp["x_out"])
    x_out = x_out + sp["edge_jag"] * np.sin(V * 23.0 + 1.3) * V * (U ** 3)
    x = x_in + (x_out - x_in) * U
    x = x + sp.get("curl_x", 0.0) * smoothstep(0.75, 1.0, U) * smoothstep(0.7, 1.0, V)
    y = interp_prof(V, sp["v"], sp["y"]) + sp["bulge"] * np.sin(math.pi * U) * V
    y = y + sp["fold_amp"] * np.sin(2 * math.pi * sp["fold_waves"] * U + 1.7 * V) * np.minimum(1.0, 2.5 * V)
    z[:, 0] = z_top
    S = np.stack([sd * x, y, z], -1)
    return S, U, V


def front_sheet(sp, sd, kind):
    """Hip panel: hangs from the belt ring over the front-outer thigh; y from the body's front depth (running min
    downward, so it hangs), wrapping back past the thigh's outer side."""
    nu, nv = sp["nu"], sp["nv"]
    U = np.linspace(0, 1, nu)[:, None] * np.ones((1, nv))
    V = np.ones((nu, 1)) * np.linspace(0, 1, nv)[None, :]
    z = interp_prof(V, sp["v"], sp["z"]) + hem_offset(U, sp["tatters"]) * smoothstep(0.55, 1.0, V)
    z[:, 0] = sp["z"][0]
    x = interp_prof(V, sp["v"], sp["x_in"]) + (interp_prof(V, sp["v"], sp["x_out"]) - interp_prof(V, sp["v"], sp["x_in"])) * U
    clear = interp_prof(V, sp["v"], sp["clear"])
    y = np.zeros_like(x)
    for i in range(nu):
        prev = None
        for j in range(nv):
            xs_ = x[i, j]
            yy, xb = None, xs_
            while yy is None and xb > 0.0:
                yy = front_y(sd * xb, z[i, j])
                if yy is None:
                    xb -= 0.01
            yy = (yy if yy is not None else -0.05) - clear[i, j]
            if prev is not None and j > 1:
                yy = min(yy, prev + 0.006)          # a hanging sheet never falls back onto the body faster than this
            prev = yy
            y[i, j] = yy + sp["wrap"] * max(0.0, xs_ - xb)
    y = y + sp["fold_amp"] * np.sin(2 * math.pi * sp["fold_waves"] * U + 2.1 * V) * np.minimum(1.0, 3 * V)
    S = np.stack([sd * x, y, z], -1)
    return S, U, V


def centre_sheet(sp, back=False):
    nu, nv = sp["nu"], sp["nv"]
    U = np.linspace(0, 1, nu)[:, None] * np.ones((1, nv))
    V = np.ones((nu, 1)) * np.linspace(0, 1, nv)[None, :]
    hw = interp_prof(V, sp["v"], sp["half_w"])
    x = (2 * U - 1) * hw
    z = interp_prof(V, sp["v"], sp["z"])
    if "hem_point" in sp:
        z = z + sp["hem_point"] * np.abs(2 * U - 1) * smoothstep(0.7, 1.0, V)
    if "tatters" in sp:
        z = z + hem_offset(U, sp["tatters"]) * smoothstep(0.6, 1.0, V)
    z[:, 0] = sp["z"][0]
    clear = interp_prof(V, sp["v"], sp["clear"])
    # the sheet hangs straight: per row, the most protruding body point over its width, running extreme downward
    prof = []
    for j in range(nv):
        best = None
        for xs_ in np.linspace(-hw[0, j] * 1.1, hw[0, j] * 1.1, 7):
            yy = front_y(xs_, z[nu // 2, j], from_back=back)
            if yy is None:
                continue
            best = yy if best is None else (max(best, yy) if back else min(best, yy))
        prof.append(best if best is not None else (prof[-1] if prof else (0.1 if back else -0.1)))
    prof = np.array(prof)
    y_row = np.zeros(nv)
    for j in range(nv):
        yy = prof[j] + (clear[0, j] if back else -clear[0, j])
        if j == 0:
            y_row[j] = yy
        else:
            y_row[j] = max(yy, y_row[j - 1] - 0.003) if back else min(yy, y_row[j - 1] + 0.003)
            if j == 1:
                y_row[j] = yy
    y = np.ones((nu, 1)) * y_row[None, :]
    y = y + (0.012 if back else -0.012) * np.cos(math.pi * (2 * U - 1)) * np.minimum(1.0, 3 * V) * 0.6
    S = np.stack([x, y, z], -1)
    return S, U, V


cloth_report = {}
for name, kind in (("CAPES", "cape"), ("MANTLES", "mantle"), ("PANELS", "panel")):
    sp = cl[kind]
    bm = new_bm()
    for sd in (1, -1):
        S_side = "L" if sd > 0 else "R"
        if kind == "panel":
            S, U, V = front_sheet(sp, sd, kind)
            out_ref = lambda p, sd=sd: np.array([sd * 0.6, -1.0, 0.0])  # noqa: E731
            zone = "panel"
            root = "pelvis"
        else:
            S, U, V = side_sheet(sp, sd, kind)
            out_ref = (lambda p: np.array([0.0, 1.0, 0.0])) if kind == "cape" else (lambda p, sd=sd: np.array([0.0, -1.0, -0.2]))
            zone = "cape" if kind == "cape" else "panel"
            root = "upperarm_" + S_side.lower()
        fs = sheet(bm, S, TH, zone, out_ref, U, V, rng.random())
        chain = chain_rows(sp["chain"], S_side)
        reg(bm, fs, "%s_%s" % (kind.upper(), S_side), chain[0], root=root, chain=chain, cloth=True, grid=[sp["nu"], sp["nv"]])
        cloth_report["%s_%s" % (kind, S_side)] = {"root": root, "chain": chain, "grid_u_v": [sp["nu"], sp["nv"]],
                                                  "hem_z_min": round(float(S[..., 2].min()), 3), "x_max": round(float(np.abs(S[..., 0]).max()), 3)}
    finish(bm, name)
bm = new_bm()
S, U, V = centre_sheet(cl["tabard"])
fs = sheet(bm, S, TH, "tabard", lambda p: np.array([0.0, -1.0, 0.0]), U, V, rng.random())
reg(bm, fs, "TABARD_FRONT", "x_tabard_01", root="pelvis", chain=cl["tabard"]["chain"], cloth=True)
cloth_report["tabard"] = {"root": "pelvis", "chain": cl["tabard"]["chain"], "hem_z_min": round(float(S[..., 2].min()), 3)}
S, U, V = centre_sheet(cl["back"], back=True)
fs = sheet(bm, S, TH, "cape", lambda p: np.array([0.0, 1.0, 0.0]), U, V, rng.random())
reg(bm, fs, "BACK_PANEL", "x_back_01", root="pelvis", chain=cl["back"]["chain"], cloth=True)
cloth_report["back_panel"] = {"root": "pelvis", "chain": cl["back"]["chain"], "hem_z_min": round(float(S[..., 2].min()), 3)}
finish(bm, "TABARD")
report["cloth"] = cloth_report

# ==============================================================================================================
# GAUNTLETS: bracers, hand plates, claws
# ==============================================================================================================
ga = cfg["gauntlets"]
bm = new_bm()
NUg, NVg = 18, 8
thg = np.arange(NUg) * 2 * math.pi / NUg           # around the forearm: 0 = up (+Z, the back of the hand side)
claw_log = []
for sd in (1, -1):
    S_side = "L" if sd > 0 else "R"

    def x_at(i, j):
        t = j / (NVg - 1)
        x0 = ga["bracer_x"][0] + ga["bracer_point"] * (1 - max(0.0, math.cos(thg[i])) ** 2)
        return x0 + (ga["bracer_x"][1] - x0) * t

    def cd_br(i, j, sd=sd):
        return np.array([sd * x_at(i, j), AX_Y, AX_Z - 0.006]), np.array([0.0, -math.sin(thg[i]), math.cos(thg[i])])
    C, D, R = radial_grid(NUg, NVg, cd_br, True, sig=(1.0, 0.8), maxd=0.2)
    Sg = C + D * (R + ga["gap"] + ga["thick"])[..., None]
    fs, _, _ = VG.grid_solid(bm, Sg, ga["thick"], lambda i, j: "gold" if j in (0, NVg - 2) else "glove", periodic_u=True,
                             out_ref=lambda p: np.array([0.0, p[1] - AX_Y, p[2] - AX_Z]), zone_in="glove",
                             wall_zone=("gold", "gold", "gold", "gold"), rand=0.5)
    reg(bm, fs, "BRACER_" + S_side, "lowerarm_" + S_side.lower())
    # back-of-hand plate
    nu_h, nv_h = 9, 5
    ang = np.radians(np.linspace(-ga["hand_plate_deg"], ga["hand_plate_deg"], nu_h))
    xh = np.linspace(ga["hand_plate_x"][0], ga["hand_plate_x"][1], nv_h)

    def cd_hp(i, j, sd=sd):
        return np.array([sd * xh[j], AX_Y, AX_Z - 0.02]), np.array([0.0, -math.sin(ang[i]), math.cos(ang[i])])
    C, D, R = radial_grid(nu_h, nv_h, cd_hp, False, sig=(0.8, 0.6), maxd=0.15)
    Sg = C + D * (R + 0.004 + 0.005)[..., None]
    fs, _, _ = VG.grid_solid(bm, Sg, 0.005, lambda i, j: "gold" if j == nv_h - 2 else "glove", periodic_u=False,
                             out_ref=lambda p: np.array([0.0, p[1] - AX_Y, p[2] - AX_Z + 0.02]), zone_in="glove",
                             wall_zone=("glove", "gold", "glove", "glove"), rand=0.5)
    reg(bm, fs, "HAND_PLATE_" + S_side, "hand_" + S_side.lower())
    # claws: a curved cone over each fingertip
    cw = ga["claw"]
    for fn in ("thumb", "index", "middle", "ring", "pinky"):
        jn = "%s_03_%s" % (fn, S_side.lower())
        h3, t3 = joint(jn)
        d = nrm(t3 - h3)
        down = nrm(np.cross(d, [0.0, 1.0, 0.0]) * (-sd)) if fn != "thumb" else nrm([0.0, 0.0, -1.0])
        if down[2] > 0:
            down = -down
        base = t3 - d * cw["sink"]
        rings_c = []
        for k_, (tt, rr) in enumerate(((0.0, cw["r"]), (0.45, cw["r"] * 0.8), (0.8, cw["r"] * 0.45))):
            cen = base + d * (cw["len"] * tt) + down * cw["curl"] * cw["len"] * tt * tt
            a_ = nrm(np.cross(d, down))
            b_ = nrm(np.cross(a_, d))
            rings_c.append([cen + (a_ * math.cos(q) + b_ * math.sin(q) * 0.8) * rr for q in np.arange(6) * math.pi / 3])
        tip = base + d * cw["len"] + down * cw["curl"] * cw["len"]
        vr = [[bm.verts.new(tuple(p)) for p in r] for r in rings_c]
        vt = bm.verts.new(tuple(tip))
        cfs = []
        for A_r, B_r in zip(vr[:-1], vr[1:]):
            for q in range(6):
                cfs.append(bm.faces.new((A_r[q], A_r[(q + 1) % 6], B_r[(q + 1) % 6], B_r[q])))
        for q in range(6):
            cfs.append(bm.faces.new((vr[-1][q], vr[-1][(q + 1) % 6], vt)))
        cfs.append(bm.faces.new(list(reversed(vr[0]))))
        VG.tag(cfs, "claw")
        VG.set_mask(bm, vr[0], 0.2, 0.5)
        VG.set_mask(bm, vr[1] + vr[2] + [vt], 0.9, 0.5)
        bmesh.ops.recalc_face_normals(bm, faces=cfs)
        reg(bm, cfs, "CLAW_%s_%s" % (fn.upper(), S_side), jn, rigid=True)
        if sd > 0:
            claw_log.append({"finger": fn, "tip": [round(float(v), 4) for v in tip]})
report["claws_L"] = claw_log
finish(bm, "GAUNTLETS")

# ==============================================================================================================
# GREAVES: shin plates, knee cops, fins
# ==============================================================================================================
lg = cfg["legs"]
bm = new_bm()
NUl, NVl = 15, 8
thl = np.radians(np.linspace(-lg["greave_deg"], lg["greave_deg"], NUl))   # 0 = front (-Y), + toward her outside
for sd in (1, -1):
    S_side = "L" if sd > 0 else "R"

    def z_at(i, j):
        t = j / (NVl - 1)
        top = lg["greave_z"][1] + lg["greave_point"] * max(0.0, math.cos(thl[i])) ** 6
        return lg["greave_z"][0] + (top - lg["greave_z"][0]) * t

    def cd_gr(i, j, sd=sd):
        z = z_at(i, j)
        c = leg_axis(z, sd)
        return c, np.array([sd * math.sin(thl[i]), -math.cos(thl[i]), 0.0])
    C, D, R = radial_grid(NUl, NVl, cd_gr, False, sig=(1.0, 0.8), maxd=0.2)
    Sg = C + D * (R + lg["gap"] + lg["thick"])[..., None]
    fs, _, _ = VG.grid_solid(bm, Sg, lg["thick"], lambda i, j: "gold" if j in (0, NVl - 2) else "plate", periodic_u=False,
                             out_ref=lambda p, sd=sd: np.array([p[0] - sd * 0.06, p[1], 0.0]), zone_in="plate",
                             wall_zone=("gold", "gold", "gold", "gold"), rand=0.5)
    reg(bm, fs, "GREAVE_" + S_side, "calf_" + S_side.lower())
    # knee cop
    kn = lg["knee"]
    zk = (kn["z"][0] + kn["z"][1]) / 2
    ca = leg_axis(zk, sd)
    p, n, _ = ray(ca, (sd * 0.15, -1.0, 0.0), 0.3)
    fs = kite(bm, p + nrm([sd * 0.15, -1.0, 0.0]) * (kn["depth"] / 2 + 0.006), (0, 0, 1), (sd * 0.15, -1.0, 0.0),
              kn["z"][1] - kn["z"][0], kn["w"], kn["depth"], kn["chamfer"],
              {"front": "plate", "side": "gold", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, shape="kite",
              taper=0.8, widest=-0.05)
    reg(bm, fs, "KNEE_COP_" + S_side, "calf_" + S_side.lower())
    fi = lg["fin"]
    zf = (fi["z"][0] + fi["z"][1]) / 2
    ca = leg_axis(zf, sd)
    p, n, _ = ray(ca, (sd, -0.25, 0.0), 0.3)
    fs = kite(bm, p + nrm([sd, -0.25, 0.0]) * (fi["depth"] / 2 + fi["out"]), (sd * 0.12, 0.0, 1.0), (sd, -0.25, 0.0),
              fi["z"][1] - fi["z"][0], fi["w"], fi["depth"], 0.004,
              {"front": "plate", "side": "gold", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, shape="leaf",
              taper=0.8)
    reg(bm, fs, "KNEE_FIN_" + S_side, "thigh_" + S_side.lower())
finish(bm, "GREAVES")

# ==============================================================================================================
# SABATONS: shaft, foot shell, heel block
# ==============================================================================================================
sb = cfg["sabatons"]
bm = new_bm()
sab_log = {}
for sd in (1, -1):
    S_side = "L" if sd > 0 else "R"
    # shaft round the ankle
    NUa, NVa = 18, 6
    tha = np.arange(NUa) * 2 * math.pi / NUa
    za = np.linspace(sb["shaft_z"][0], sb["shaft_z"][1], NVa)

    def cd_sh(i, j, sd=sd):
        c = leg_axis(max(za[j], 0.16), sd)
        c = np.array([c[0], c[1], za[j]])
        return c, np.array([math.sin(tha[i]), -math.cos(tha[i]), 0.0])
    C, D, R = radial_grid(NUa, NVa, cd_sh, True, sig=(1.2, 0.8), maxd=0.2)
    vv = np.linspace(0, 1, NVa)[None, :]
    Sg = C + D * (R + sb["shaft_gap"] + sb["thick"] + sb["shaft_flare"] * vv ** 3)[..., None]
    fs, _, _ = VG.grid_solid(bm, Sg, sb["thick"], lambda i, j: "gold" if j == NVa - 2 else "plate", periodic_u=True,
                             out_ref=lambda p, sd=sd: np.array([p[0] - sd * 0.05, p[1] - 0.03, 0.0]), zone_in="plate",
                             wall_zone=("plate", "gold", "plate", "plate"), rand=0.5)
    reg(bm, fs, "SABATON_SHAFT_" + S_side, "foot_" + S_side.lower())
    # foot shell: sections across the foot (x-z plane) along y
    st = np.array(sb["stations"], dtype=np.float64)
    foot = co[(co[:, 2] < 0.22) & (co[:, 0] * sd > 0) & (np.abs(co[:, 0]) < 0.2)]
    fx = float(np.median(foot[:, 0]))
    NS = 12
    rings_f = []
    for k_, (y0, zs, zt, hw) in enumerate(st):
        sl = foot[np.abs(foot[:, 1] - y0) < 0.012]
        cx = fx - sd * sb["toe_x_in"] * max(0.0, (-y0 - 0.1) / 0.165)
        if len(sl) > 3 and k_ < len(st) - 2:
            zs = min(zs, sl[:, 2].min() - sb["gap"] * 0.5)
            zt = max(zt, sl[:, 2].max() + sb["gap"])
            hw = max(hw, np.abs(sl[:, 0] - cx).max() + sb["gap"])
        zs = max(zs, 0.001)
        zc, hz_ = (zs + zt) / 2, (zt - zs) / 2
        row = []
        for q in range(NS):
            a = 2 * math.pi * q / NS
            c_, s_ = math.cos(a), math.sin(a)
            ex = 2.6
            rx = hw * np.sign(c_) * abs(c_) ** (2 / ex)
            rz = hz_ * np.sign(s_) * abs(s_) ** (2 / ex)
            if s_ > 0:                                   # a ridge along the top of the foot (pointed look)
                rz += hz_ * 0.18 * max(0.0, 1 - abs(c_) * 3) * min(1.0, k_ / 3)
            row.append((cx + rx, y0, zc + rz))
        rings_f.append(row)
    S = np.array(rings_f).transpose(1, 0, 2)
    fs = VG.loft_solid(bm, S, lambda i, j: "gold" if j == len(st) - 2 else "plate", rand=0.5, cap_zone="plate")
    reg(bm, fs, "SABATON_FOOT_" + S_side, "foot_" + S_side.lower())
    # heel block
    hb = sb["heel"]
    zs_heel = float(np.interp(hb["y"][1], st[::-1, 0], st[::-1, 1]))
    poly = [(hb["y"][1], zs_heel + 0.006), (hb["y"][0], zs_heel + 0.006), (hb["y_ground"][0], 0.0), (hb["y_ground"][1], 0.0)]
    fs = VG.prism(bm, poly, (fx, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), -hb["half_w"], hb["half_w"], 0.003,
                  {"front": "plate", "side": "plate", "chamfer": "gold", "back": "plate", "chamfer_back": "gold"}, chamfer_back=0.003)
    reg(bm, fs, "SABATON_HEEL_" + S_side, "foot_" + S_side.lower())
    if sd > 0:
        sab_log = {"foot_centre_x": round(fx, 4), "toe_tip": [round(float(v), 4) for v in S[:, -1].mean(0)]}
report["sabatons_L"] = sab_log
finish(bm, "SABATONS")

# ==============================================================================================================
# BODY zones
# ==============================================================================================================
bz = bc["zones"]
for m in mats:
    me.materials.append(m)
bmb = bmesh.new()
bmb.from_mesh(me)
parts_b = sorted(connected_parts(bmb), key=len)
eyes = set(f for pv in parts_b[:-1] for v in pv for f in v.link_faces)
counts = {}
for f in bmb.faces:
    c = f.calc_center_median()
    ax = abs(c.x)
    if f in eyes:
        zn = "eye"
    elif c.z > bz["head_z"] and ax < 0.13:
        zn = "skin"
    elif ax > bz["arm_x"] and c.z > 1.5:
        zn = "glove" if bz["glove_x"] < ax < bz["glove_end_x"] else "skin"
    elif c.z < bz["leg_z"]:
        zn = "legging"
    else:
        zn = "suit"
    f.material_index = Z[zn]
    counts[zn] = counts.get(zn, 0) + 1
bmb.to_mesh(me)
bmb.free()
report["body_zone_faces"] = counts
report["parts"]["BODY"] = mesh_stats(body)

if "REF_blockout" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["REF_blockout"])
report["triangles_total"] = sum(v["triangles"] for v in report["parts"].values())
report["piece_table"] = piece_table
report["rigid_pieces"] = sum(1 for p in piece_table if not p.get("cloth"))
report["cloth_pieces"] = sum(1 for p in piece_table if p.get("cloth"))
log("total triangles", report["triangles_total"])
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
