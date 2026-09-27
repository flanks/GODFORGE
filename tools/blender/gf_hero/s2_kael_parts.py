"""Stage 2, Kael: the duster, the ghost-flame tatters, the gear, the boots and the hair around the fitted body.

Built procedurally from art/characters/kael/stage2_parts.json (every number measured on the approved front and the
recentred stage-1 blockout; see its _doc keys), never copied from the blockout. Every part is closed; each piece is
registered in a piece table with its suggested bone (the face attribute gf_piece indexes it), so stage 3 can weight
the rigid pieces 100 % to one bone and hang the cloth on x_ chains. Paint zones: s2_kael_geom.ZONES (the face
material index). Weapons are separate models: both hands stay empty.

Objects:
  BODY       the under-layer: skin (head, neck, the right hand's fingers), the fingerless glove, the ghost flesh on the
             LEFT arm below the bicep strap (emissive zone), black cloth (shirt, trousers), the eyeballs
  HAIR       the swept hair shell with chunky locks, a fringe, and the short chin beard
  SCARF      the black scarf round the neck with its drape
  GEAR       the upper belt with the oval buckle and the ghost gem, the lower slung belt and its buckle, the bandolier
             with six cartridges, the long holster on the right thigh with two straps, the left hip pouch, the left
             thigh strap, the right bracer with two straps and the glove cuff, the left bicep and wrist straps
  LOINCLOTH  the maroon torn cloth hanging from the lower belt
  BOOTS      tall boots: shaft, foot shell, pointed knee cuff, three strap bands with buckles (both sides)
  COAT       the duster: yoke and sleeves (the body's quads pushed out, the left sleeve rolled up), the flared skirt with
             the back vent and the torn hem, the high collar with two points, the lapels, the rolled cuffs
  WISPS      five ghost-flame tatters on the hem (emissive), each for a 3-bone x_wisp chain

  blender -b -P tools/blender/gf_hero/s2_kael_parts.py -- <body.blend> <retopo_start.blend> <parts.json> <fit.json> \
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

import s2_kael_geom as KG  # noqa: E402
from s2lib import (connected_parts, get_co, get_collection, get_normals, hex_rgb, log, mesh_stats, opt, read_json,  # noqa: E402
                   save_blend, script_args, set_co, srgb_to_linear, write_json)

argv = script_args(__doc__)
if len(argv) < 6:
    raise SystemExit(__doc__)
BODY, REF, CFG, FIT, MHLM, OUT = (os.path.abspath(a) for a in argv[:6])
REPORT = opt(argv, "--report", None, str)
FITREP = opt(argv, "--fit-report", None, str)
cfg = read_json(CFG)
fit = read_json(FIT)
fitrep = read_json(FITREP) if FITREP and os.path.isfile(FITREP) else {}
rng = random.Random(cfg.get("seed", 23))
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
with bpy.data.libraries.load(REF, link=False) as (src_, dst_):
    dst_.objects = ["REF_blockout"]
ref = dst_.objects[0]
scene.collection.objects.link(ref)
report = {"parts": {}, "pieces": {}}
col = get_collection("KAEL_stage2")
if body.name not in col.objects:
    col.objects.link(body)
Zn = KG.Z
LM = fit["landmarks"]


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v) + 1e-12)


# ---- zone preview materials (palette base tones; the texture step replaces them with the atlas) --------------
pal = {s["key"]: s["tones"] for s in read_json(os.path.join(os.path.dirname(CFG), "palette.json"))["swatches"]}
zone_hex = {"skin": pal["skin"]["base"], "hair": pal["hair"]["base"], "eye": pal["eye_glow"]["hot"],
            "cloth": pal["black_cloth"]["base"], "glove": pal["black_cloth"]["shadow"], "ghost": pal["ghost_arm"]["hot"],
            "coat": pal["coat_violet"]["base"], "lining": pal["tabard_maroon"]["shadow"], "coat_edge": pal["coat_violet"]["highlight"],
            "maroon": pal["tabard_maroon"]["base"], "leather": pal["leather"]["base"], "boot": pal["boot_leather"]["base"],
            "bronze": pal["bronze"]["base"], "gem": pal["gem_buckle"]["core"], "wisp": pal["ghost_arm"]["hot"],
            "cartridge": "#4A4A44"}
mats = []
for zname in KG.ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    c = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    m.diffuse_color = c
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = c
    if zname in ("eye", "ghost", "gem", "wisp"):
        bsdf.inputs["Emission Color"].default_value = c
        bsdf.inputs["Emission Strength"].default_value = 3.0
    mats.append(m)

PIECE_LAYER = "gf_piece"
piece_table = []


def new_bm():
    bm = bmesh.new()
    KG.ensure_mask(bm)
    bm.faces.layers.int.new(PIECE_LAYER)
    return bm


def reg(bm, faces, name, bone):
    """Register the faces just built as one piece (index into piece_table) with its suggested bone."""
    lay = bm.faces.layers.int.get(PIECE_LAYER)
    pid = len(piece_table)
    for f in faces:
        if f.is_valid:
            f[lay] = pid
    piece_table.append({"id": pid, "name": name, "bone": bone})
    return pid


def mirror_piece_id(pid):
    """A left piece's mirror: a new piece id with _L -> _R, _l -> _r."""
    src = piece_table[pid]
    nid = len(piece_table)
    name = src["name"][:-2] + "_R" if src["name"].endswith("_L") else src["name"] + "_R"
    bone = src["bone"][:-2] + "_r" if src["bone"].endswith("_l") else src["bone"]
    piece_table.append({"id": nid, "name": name, "bone": bone})
    return nid


def mirrored(bm_left, bm_dst):
    """Append bm_left and its x-mirror to bm_dst (the mirror gets new piece ids)."""
    idmap = {}

    def pm(pid):
        if pid not in idmap:
            idmap[pid] = mirror_piece_id(pid)
        return idmap[pid]
    lay_s = bm_left.verts.layers.float_color.get(KG.G0.MASK_LAYER)
    lay_d = KG.ensure_mask(bm_dst)
    pl_s = bm_left.faces.layers.int.get(PIECE_LAYER)
    pl_d = bm_dst.faces.layers.int.get(PIECE_LAYER)
    vmap = {}
    for v in bm_left.verts:
        nv_ = bm_dst.verts.new(v.co)
        nv_[lay_d] = v[lay_s]
        vmap[v] = nv_
    for f in bm_left.faces:
        g = bm_dst.faces.new([vmap[v] for v in f.verts])
        g.material_index = f.material_index
        g[pl_d] = f[pl_s]
    KG.mirror_into(bm_left, bm_dst, PIECE_LAYER, pm)
    bm_left.free()


def finish(bm, name):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lay = bm.verts.layers.float_color.get(KG.G0.MASK_LAYER)
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
    log("%-10s %6d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d" % (
        name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"]))
    return ob


def bvh_of(objs, extra_bms=()):
    verts, polys = [], []
    off = 0
    for o in objs:
        me = o.data
        verts.extend(tuple(o.matrix_world @ v.co) for v in me.vertices)
        polys.extend([tuple(i + off for i in p.vertices) for p in me.polygons])
        off += len(me.vertices)
    for bm in extra_bms:
        bm.verts.index_update()
        verts.extend(tuple(v.co) for v in bm.verts)
        polys.extend([tuple(v.index + off for v in f.verts) for f in bm.faces])
        off += len(bm.verts)
    return BVHTree.FromPolygons(verts, polys)


def r_out(bvh, c, d, reach=0.6):
    """Distance from c to the OUTERMOST surface along direction d (a ray from outside, c + d*reach, back toward c)."""
    c = np.asarray(c, dtype=np.float64)
    d = unit(d)
    loc, n_, i_, dist = bvh.ray_cast(Vector((c + d * reach).tolist()), Vector((-d).tolist()), reach)
    return None if loc is None else reach - dist


# ==============================================================================================================
# BODY: trouser volume, lifted soles, zones
# ==============================================================================================================
bcfg = cfg["body"]
bme = body.data
bme.update()
co = get_co(bme)
no = get_normals(bme)
z0, z1 = bcfg["trouser_z"]
w = smoothstep(z0, z0 + 0.06, co[:, 2]) * (1 - smoothstep(z1 - 0.06, z1, co[:, 2])) * (np.abs(co[:, 0]) < 0.45)
co += no * (bcfg["trouser_inflate"] * w)[:, None]
fl = co[:, 2] < bcfg["foot_lift_z"]
co[fl, 2] += bcfg["foot_lift"] * (1 - co[fl, 2] / bcfg["foot_lift_z"])
set_co(bme, co)
for m in mats:
    bme.materials.append(m)
bmb = bmesh.new()
bmb.from_mesh(bme)
parts_b = sorted(connected_parts(bmb), key=len)
eye_faces = set(f for pv in parts_b[:-1] for v in pv for f in v.link_faces)
zc = {}
for f in bmb.faces:
    c = f.calc_center_median()
    if f in eye_faces:
        z_ = "eye"
    elif c.z > 1.5 and c.x > bcfg["ghost_abs_x"]:
        z_ = "ghost"
    elif c.z > 1.5 and c.x < -bcfg["glove_abs_x"][0]:
        z_ = "skin" if c.x < -bcfg["glove_abs_x"][1] else "glove"
    elif c.z > bcfg["neck_skin_z"] and abs(c.x) < 0.2:
        z_ = "skin"
    else:
        z_ = "cloth"
    f.material_index = Zn[z_]
    zc[z_] = zc.get(z_, 0) + 1
bmb.to_mesh(bme)
bmb.free()
bme.update()
report["body_zones_faces"] = zc
report["body_conform"] = {"trouser_inflate_m": bcfg["trouser_inflate"], "foot_lift_m": bcfg["foot_lift"]}
dg = bpy.context.evaluated_depsgraph_get()
body_bvh = BVHTree.FromObject(body, dg)
ref_bvh = BVHTree.FromObject(ref, dg)
bco = get_co(bme)
bno = get_normals(bme)
bedges = np.empty(len(bme.edges) * 2, dtype=np.int64)
bme.edges.foreach_get("vertices", bedges)
bedges = bedges.reshape(-1, 2)
log("body conformed, zones", zc)


def section_centre(z, xsel, ysel=(-0.4, 0.4)):
    """Centre of the body's cross-section with the plane z = const, restricted by an x predicate."""
    a, b = bco[bedges[:, 0]], bco[bedges[:, 1]]
    cross = (a[:, 2] - z) * (b[:, 2] - z) < 0
    t = (z - a[cross, 2]) / (b[cross, 2] - a[cross, 2])
    pts = a[cross] + (b[cross] - a[cross]) * t[:, None]
    pts = pts[xsel(pts[:, 0]) & (pts[:, 1] > ysel[0]) & (pts[:, 1] < ysel[1])]
    if len(pts) < 4:
        raise SystemExit("no body section at z=%.3f" % z)
    c = (pts.min(0) + pts.max(0)) / 2
    c[2] = z
    return c


def ring_dirs(n, u, v, segs):
    angs = np.arange(segs) * 2 * math.pi / segs
    return angs, [unit(u * math.cos(a) + v * math.sin(a)) for a in angs]


def band(bm, bvh, c, n, u, h, thick, gap, segs, zone, sink=0.003, ch=None, stations=2, rand=None, reach=0.5,
         fill_concave=True):
    """A closed strap band round a limb / the torso: the cross-section plane through c with normal n (the band's
    height axis), angle 0 along u (u in the plane). The surface radius is sampled at `stations` heights (rays from
    outside); the outer skin stands gap + thick off it with chamfered edges, the inner skin sinks `sink` into it.
    Returns (faces, outer points at the middle, directions)."""
    n = unit(n)
    u = unit(np.asarray(u) - n * (np.asarray(u) @ n))
    v = np.cross(n, u)
    angs, dirs = ring_dirs(n, u, v, segs)
    ch = thick * 0.45 if ch is None else ch
    hs = np.linspace(-h / 2, h / 2, max(2, stations))
    R = np.zeros((len(hs), segs))
    for si, s in enumerate(hs):
        cc = np.asarray(c) + n * (s if stations > 1 else 0.0)
        for k, d in enumerate(dirs):
            r = r_out(bvh, cc, d, reach)
            R[si, k] = r if r is not None else np.nan
        row = R[si]
        R[si] = np.where(np.isnan(row), np.nanmedian(row) if not np.isnan(row).all() else 0.05, row)
        if fill_concave:     # a strap spans hollows: never below the mean of its neighbours
            nb = (np.roll(R[si], 1) + np.roll(R[si], -1)) / 2
            R[si] = np.maximum(R[si], nb)
    rings = []
    rt = thick + gap
    first, last = R[0], R[-1]
    rings.append([np.asarray(c) + n * hs[0] + d * (first[k] - sink) for k, d in enumerate(dirs)])
    rings.append([np.asarray(c) + n * hs[0] + d * (first[k] + rt - ch) for k, d in enumerate(dirs)])
    for si, s in enumerate(hs):
        ss = min(max(s, hs[0] + ch), hs[-1] - ch)
        rings.append([np.asarray(c) + n * ss + d * (R[si][k] + rt) for k, d in enumerate(dirs)])
    rings.append([np.asarray(c) + n * hs[-1] + d * (last[k] + rt - ch) for k, d in enumerate(dirs)])
    rings.append([np.asarray(c) + n * hs[-1] + d * (last[k] - sink) for k, d in enumerate(dirs)])
    masks = [0.0, 0.2] + [1.0] * len(hs) + [0.2, 0.0]
    fs = KG.closed_loop(bm, rings, zone, rand, masks=masks)
    mid = R[len(hs) // 2]
    outer = [np.asarray(c) + d * (mid[k] + rt) for k, d in enumerate(dirs)]
    return fs, outer, dirs


def buckle(bm, p, nrm, up, spec, zone="bronze", pin=True):
    """A rectangular bronze buckle frame standing on the strap at p (facing nrm), with a pin across it."""
    p = np.asarray(p, dtype=np.float64)
    nrm = unit(nrm)
    c = p + nrm * spec["depth"] * 0.5
    fs = KG.rect_ring(bm, c, nrm, up, spec["w"], spec["h"], spec["bar"], spec["depth"], zone, rand=rng.random())
    if pin:
        up_ = unit(np.asarray(up) - nrm * (np.asarray(up) @ nrm))
        fs += KG.cylinder(bm, c - up_ * (spec["h"] / 2 - spec["bar"] / 2), c + up_ * (spec["h"] / 2 - spec["bar"] / 2),
                          spec["bar"] * 0.28, spec["bar"] * 0.28, zone, sides=6)
    return fs


# ==============================================================================================================
# HAIR + chin beard (Brax's shell method on the body's own head quads)
# ==============================================================================================================
hc = cfg["hair"]
rme = ref.data
lc = np.empty(len(rme.loops) * 4, dtype=np.float32)
rme.color_attributes["src_col"].data.foreach_get("color", lc)
lum = lc.reshape(-1, 4)[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
ls = np.empty(len(rme.polygons), dtype=np.int64)
rme.polygons.foreach_get("loop_start", ls)
face_lum = (lum[ls] + lum[ls + 1] + lum[ls + 2]) / 3
hit_pt = np.full((len(bco), 3), np.nan)
for i in np.nonzero(bco[:, 2] > hc["z_min"])[0]:
    vv, nv_ = Vector(bco[i]), Vector(bno[i])
    loc, nn, idx, dist = ref_bvh.ray_cast(vv + nv_ * 1e-4, nv_, hc["max_dist"])
    if loc is not None and face_lum[idx] < hc["dark_lum"]:
        hit_pt[i] = loc


def vgroup_mask(name):
    m = np.zeros(len(bco), bool)
    g = body.vertex_groups.get(name)
    if g:
        for v in bme.vertices:
            for gg in v.groups:
                if gg.group == g.index and gg.weight > 0.5:
                    m[v.index] = True
    return m


lips = vgroup_mask("lips")
ears = vgroup_mask("ears")
phi = np.degrees(np.abs(np.arctan2(bco[:, 0], -(bco[:, 1] - hc["head_cy"]))))
zz = bco[:, 2]
is_eye = np.zeros(len(bco), bool)
for f in bme.polygons:
    if f.material_index == Zn["eye"]:
        is_eye[list(f.vertices)] = True
head = (zz > hc["z_min"]) & (np.abs(bco[:, 0]) < 0.16) & ~is_eye
hl = np.interp(phi, hc["hairline"]["phi"], hc["hairline"]["z"])
is_hair = head & (zz > hl) & ~ears
mouth_low = float(bco[lips, 2].min()) if lips.any() else LM["chin"][2] + 0.03
chin_z = float(LM["chin"][2])
is_beard = head & (zz < mouth_low - hc["beard_below_mouth"]) & (zz > chin_z - hc["beard_below_chin"]) & (phi <= hc["beard_phi_max"]) & ~lips
polys = bme.polygons
edge_faces = {}
for p in polys:
    for ek in p.edge_keys:
        edge_faces.setdefault(ek, []).append(p.index)
nbrs = [[] for _ in polys]
for fl_ in edge_faces.values():
    if len(fl_) == 2:
        nbrs[fl_[0]].append(fl_[1])
        nbrs[fl_[1]].append(fl_[0])


def clean_face_region(inside):
    """Faces of a region, cleaned: faces with < 2 edge-neighbours in the region are dropped, pinholes filled, and
    bow-tie vertices (the region touching itself through one vertex) split, so the shell rim stays manifold."""
    inside = inside.copy()
    for _ in range(4):
        cnt = np.array([sum(inside[j] for j in nbrs[i]) for i in range(len(polys))])
        inside = (inside | (~inside & (cnt >= 3))) & ~(inside & (cnt < 2))
    for _ in range(3):
        bad = False
        vfaces = {}
        for i in np.nonzero(inside)[0]:
            for k in polys[i].vertices:
                vfaces.setdefault(k, []).append(i)
        for k, fl_ in vfaces.items():
            fl_set = set(fl_)
            seen, comps = set(), 0
            for f0 in fl_:
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
                for f in fl_[1:]:
                    inside[f] = False
                bad = True
        if not bad:
            break
    return [int(i) for i in np.nonzero(inside)[0]]


def face_region(vmask):
    return clean_face_region(np.array([all(vmask[k] for k in p.vertices) for p in polys]))


def region_shell(bm, fidx, off, zone_out, zone_in, zone_rim, inner=None, thick=None, smooth=0, rim_off=None, mask_fn=None):
    """Closed shell over the body faces fidx: the outer skin at the per-vertex offset off[k] along the body normal
    (smoothed over the region `smooth` times; boundary vertices at rim_off when given), the inner skin at
    `inner` (m along the normal, may be negative: inside the body) or `thick` under the outer skin; rim walls on the
    boundary. Returns (faces, outer vert map, local offsets)."""
    edge_count = {}
    for fi in fidx:
        vs = list(polys[fi].vertices)
        for a, b in zip(vs, vs[1:] + vs[:1]):
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
    bnd = {k for e, c_ in edge_count.items() if c_ == 1 for k in e}
    used = sorted({k for fi in fidx for k in polys[fi].vertices})
    of = {k: float(off[k]) for k in used}
    nb = {k: set() for k in used}
    for (a, b) in edge_count:
        nb[a].add(b)
        nb[b].add(a)
    for _ in range(smooth):
        new = {}
        for k in used:
            if rim_off is not None and k in bnd:
                new[k] = rim_off
            else:
                new[k] = 0.5 * of[k] + 0.5 * np.mean([of[j] for j in nb[k]])
        of = new
    vo, vi = {}, {}
    for k in used:
        p, nrm = bco[k], bno[k]
        vo[k] = bm.verts.new(tuple(p + nrm * of[k]))
        din = inner if inner is not None else of[k] - thick
        vi[k] = bm.verts.new(tuple(p + nrm * din))
    fs = []
    for fi in fidx:
        vs = list(polys[fi].vertices)
        f = bm.faces.new([vo[k] for k in vs])
        f.material_index = Zn[zone_out]
        g = bm.faces.new([vi[k] for k in reversed(vs)])
        g.material_index = Zn[zone_in]
        fs += [f, g]
    for fi in fidx:
        vs = list(polys[fi].vertices)
        for a, b in zip(vs, vs[1:] + vs[:1]):
            if edge_count[(min(a, b), max(a, b))] == 1:
                f = bm.faces.new((vo[b], vo[a], vi[a], vi[b]))
                f.material_index = Zn[zone_rim]
                fs.append(f)
    for k in used:
        KG.set_mask(bm, [vo[k]], (0.0 if k in bnd else 1.0) if mask_fn is None else mask_fn(k, k in bnd))
        KG.set_mask(bm, [vi[k]], 0.0)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs, vo, of


def hair_off(vmask, lo, hi):
    off = np.full(len(bco), lo)
    for k in np.nonzero(vmask)[0]:
        if not np.isnan(hit_pt[k, 0]):
            off[k] = float(np.clip((hit_pt[k] - bco[k]) @ bno[k] + 0.002, lo, hi))
    return off


bm = new_bm()
fidx = face_region(is_hair)
fs, vo, ofs = region_shell(bm, fidx, hair_off(is_hair, hc["min_off"], hc["max_off"]), "hair", "hair", "hair", inner=-0.004,
                           smooth=hc["offset_smooth"], rim_off=hc["min_off"] * 0.35, mask_fn=lambda k, b: 0.1 if b else 0.35)
reg(bm, fs, "HAIR", "head")
# locks swept back over the skull (the concept's slicked-back mane): each lock lies along the scalp, lifted a little,
# pointing back (and down on the sides and the back of the head); longer from the front hairline, shorter behind
cl = hc["clumps"]
pts = np.array([np.array(vo[k].co) for k in vo])
nrms = np.array([bno[k] for k in vo])
sel = [i for i in range(len(pts)) if pts[i, 2] > cl["z_min"] and nrms[i, 2] > -0.35]
rng.shuffle(sel)
sel.sort(key=lambda i: pts[i, 1])                    # front roots first: they get their spacing
chosen = []
for i in sel:
    if all(np.linalg.norm(pts[i] - pts[j]) > cl["spacing"] for j in chosen):
        chosen.append(i)
    if len(chosen) >= cl["count"]:
        break


def along(g, n_):
    g = np.asarray(g, dtype=np.float64)
    return unit(g - n_ * (g @ n_))


n_lock = 0
for i in chosen:
    p, n_ = pts[i], nrms[i]
    top = float(smoothstep(1.97, 2.04, p[2]))
    sweep = along(np.array([0.1 * np.sign(p[0]), 1.0, 0.35 * top - 0.45 * (1 - top)]), n_)
    d0 = unit(sweep + n_ * cl.get("lift", 0.28))
    bend = along(np.array([0.08 * np.sign(p[0]), 0.65, -0.75]), n_)
    frontness = float(smoothstep(0.06, -0.08, p[1]))
    L = cl["length"] * (0.7 + 0.6 * frontness) * rng.uniform(0.85, 1.15)
    fs = KG.lock(bm, p, n_, d0, bend, L, cl["width"] * rng.uniform(0.85, 1.15), cl["thick"], rng, "hair")
    reg(bm, fs, "HAIR_LOCK_%d" % n_lock, "head")
    n_lock += 1
fr = hc["fringe"]
front = [i for i in range(len(pts)) if pts[i, 1] < -0.06 and pts[i, 2] > 2.0]
front.sort(key=lambda i: pts[i, 0])
picks = [front[int(len(front) * f)] for f in (0.18, 0.3, 0.42, 0.8)][:fr["count"]] if len(front) > 8 else []
for i in picks:
    p, n_ = pts[i], nrms[i]
    sx = -1.0 if p[0] < 0 else 1.0
    d0 = unit(np.array([sx * 0.25, -0.75, 0.35]) + n_ * 0.3)
    bend = unit(np.array([sx * 0.35, -0.35, -0.85]))
    fs = KG.lock(bm, p, n_, d0, bend, fr["length"] * rng.uniform(0.85, 1.15), fr["width"], fr["thick"], rng, "hair")
    reg(bm, fs, "HAIR_FRINGE", "head")
    n_lock += 1
bfidx = face_region(is_beard)
bfs, bvo, _ = region_shell(bm, bfidx, hair_off(is_beard, hc["beard_min_off"], hc["beard_max_off"]), "hair", "hair", "hair",
                           inner=-0.003, smooth=3, rim_off=hc["beard_min_off"] * 0.4, mask_fn=lambda k, b: 0.1 if b else 0.35)
reg(bm, bfs, "CHIN_BEARD", "head")
bc_ = hc["beard_clumps"]
bpts = sorted(((np.array(bvo[k].co), bno[k]) for k in bvo), key=lambda t: t[0][2])[:12]
used_b = []
for p, n_ in bpts:
    if len(used_b) >= bc_["count"]:
        break
    if all(np.linalg.norm(p - q) > bc_["spacing"] for q in used_b):
        used_b.append(p)
        fs = KG.lock(bm, p, n_, unit(n_ * 0.3 + np.array([0.0, -0.2, -0.9])), unit(np.array([0.0, -0.3, -0.9])),
                     bc_["length"], bc_["width"], bc_["thick"], rng, "hair")
        reg(bm, fs, "CHIN_BEARD_LOCK", "head")
report["hair"] = {"shell_faces": len(fidx), "locks": n_lock, "beard_faces": len(bfidx), "beard_locks": len(used_b),
                  "hair_verts_with_blockout_hit": int((~np.isnan(hit_pt[is_hair, 0])).sum()), "hair_verts": int(is_hair.sum())}
finish(bm, "HAIR")

# ==============================================================================================================
# SCARF (neck wrap + drape)
# ==============================================================================================================
sc = cfg["scarf"]
bm = new_bm()
zs_ = np.linspace(sc["z"][0], sc["z"][1], 4)
segs = sc["segments"]
rings_o, rings_i = [], []
for k, z in enumerate(zs_):
    c = section_centre(z, lambda x: np.abs(x) < 0.12)
    angs, dirs = ring_dirs(np.array([0, 0, 1.0]), np.array([0, -1.0, 0]), np.array([1.0, 0, 0]), segs)
    rr = [r_out(body_bvh, c, d, 0.25) or 0.06 for d in dirs]
    f = k / (len(zs_) - 1)
    bul = sc["bulge"] * math.sin(math.pi * f) + 0.003 * math.sin(f * 7.0)
    rings_o.append([c + d * (r + sc["out"] + bul + 0.002 * math.sin(3 * a + k)) for d, r, a in zip(dirs, rr, angs)])
    if k in (0, len(zs_) - 1):
        rings_i.append([c + d * (r - 0.004) for d, r in zip(dirs, rr)])
fs = KG.closed_loop(bm, rings_o + [rings_i[1], rings_i[0]], "cloth", masks=[0.2, 1.0, 1.0, 0.2, 0.0, 0.0])
reg(bm, fs, "SCARF", "neck_01")
dr = sc["drape"]
nu_, nv_ = 5, 5
ids, n_ids, quads, table = KG.grid_faces(nu_, nv_)
Pd = np.zeros((n_ids, 3))
for vid, i, j, side in table:
    f = j / (nv_ - 1)
    z = dr["z"][0] + (dr["z"][1] - dr["z"][0]) * f
    x = (-1 + 2 * i / (nu_ - 1)) * (dr["half_width"] * (1 - f) + 0.006)
    loc, n_, _, dist = body_bvh.ray_cast(Vector((x, -0.6, z)), Vector((0, 1.0, 0)), 1.0)
    y = (loc.y if loc is not None else -0.1) - dr["clear"] - 0.004 * (1 - (2 * i / (nu_ - 1) - 1) ** 2)
    Pd[vid] = (x, y, z)
fs, _, _ = KG.surface_solid(bm, Pd, quads, dr["thick"], "cloth", "cloth", "cloth", out_ref=lambda p: np.array([0, -1.0, 0]))
reg(bm, fs, "SCARF_DRAPE", "spine_03")
scarf_ob = finish(bm, "SCARF")

# ==============================================================================================================
# GEAR: belts, buckle + gem, bandolier + cartridges, holster, pouch, straps, bracer
# ==============================================================================================================
bm = new_bm()
bl = cfg["belts"]
up_z = np.array([0, 0, 1.0])
front_u = np.array([0, -1.0, 0])
ub = bl["upper"]
cU = section_centre(ub["z"], lambda x: np.abs(x) < 0.3)
fs, outer, dirs = band(bm, body_bvh, cU, up_z, front_u, ub["h"], ub["thick"], ub["gap"], ub["segments"], "leather", rand=rng.random())
reg(bm, fs, "BELT_UPPER", "spine_01")
bk = bl["buckle"]
bpos = outer[0] + np.array([0, -bk["out"], 0])
fs = KG.rect_ring(bm, bpos, np.array([0, -1.0, 0]), up_z, bk["w"], bk["h"], bk["bar"], bk["depth"], "bronze", corner=0.9, rand=0.4)
fs += KG.stud(bm, bpos + np.array([0, -bk["depth"] * 0.2, 0]), (0, -1.0, 0), bk["gem_r"], bk["gem_h"], "gem", sides=8)
reg(bm, fs, "BUCKLE_GEM", "spine_01")
lb = bl["lower"]
cL = section_centre(lb["z"], lambda x: np.abs(x) < 0.3)
nL = unit(np.array([-lb["slope"], 0, 1.0]))
fs, outer, dirs = band(bm, body_bvh, cL, nL, front_u, lb["h"], lb["thick"], lb["gap"], lb["segments"], "leather", rand=rng.random())
reg(bm, fs, "BELT_LOWER", "pelvis")
k_ = int(round((lb["buckle_theta_deg"] % 360) / 360 * lb["segments"])) % lb["segments"]
fs = buckle(bm, outer[k_], dirs[k_], nL, lb["buckle"])
reg(bm, fs, "BELT_LOWER_BUCKLE", "pelvis")
# bandolier: the band in the plane through the shoulder -> hip diagonal and the front axis
bd = cfg["bandolier"]
A_, B_ = np.array(bd["from"]), np.array(bd["to"])
nB = unit(np.cross(B_ - A_, [0, 1.0, 0]))
cB = (A_ + B_) / 2
fs, outer_b, dirs_b = band(bm, body_bvh, cB, nB, front_u, bd["h"], bd["thick"], bd["gap"], bd["segments"], "leather",
                           reach=0.75, rand=rng.random())
reg(bm, fs, "BANDOLIER", "spine_03")
ct = bd["cartridges"]
fronts = [k for k, d in enumerate(dirs_b) if -d[1] > 0.25]
for zt in np.linspace(ct["z"][0], ct["z"][1], ct["count"]):
    k = min(fronts, key=lambda kk: abs(outer_b[kk][2] - zt))
    d = dirs_b[k]
    nrm_c = unit(np.array([d[0] * 0.3, -1.0, d[2] * 0.15]))
    c = outer_b[k] + nrm_c * (ct["r"] + ct["stand"] * 0.3)
    ax = unit(nB - nrm_c * (nB @ nrm_c))
    fs = KG.cylinder(bm, c - ax * ct["len"] / 2, c + ax * ct["len"] / 2, ct["r"], ct["r"] * 0.92, "cartridge", sides=8, bevel=0.002)
    fs += KG.cylinder(bm, c + ax * (ct["len"] / 2 - 0.002), c + ax * (ct["len"] / 2 + ct["cap_len"]), ct["r"] * 1.06, ct["r"] * 0.7,
                      "bronze", sides=8, bevel=0.002)
    reg(bm, fs, "CARTRIDGE", "spine_03")
# holster on the front-outer face of the right thigh (flat side facing out along theta)
ho = cfg["holster"]
tho = math.radians(ho.get("theta_deg", 270))
dh = np.array([math.sin(tho), -math.cos(tho), 0.0])
th_ = np.array([math.cos(tho), math.sin(tho), 0.0])
rings = []
for zi, z in enumerate(ho["stations"]):
    c = section_centre(max(z, 0.8), lambda x: x < -0.03)
    r = r_out(body_bvh, c, dh, 0.4) or 0.1
    t_, w_ = ho["thick"][zi], ho["width"][zi]
    cc_ = c + dh * (r + ho["gap"] + t_ / 2)
    ring = []
    for a in np.arange(12) * 2 * math.pi / 12:
        ca, sa = math.cos(a), math.sin(a)
        ex = np.sign(ca) * abs(ca) ** 0.55
        ey = np.sign(sa) * abs(sa) ** 0.55
        p_ = cc_ + dh * ex * t_ / 2 + th_ * ey * w_ / 2
        ring.append((p_[0], p_[1], z))
    rings.append(ring)
S = np.array(rings).transpose(1, 0, 2)
fs = KG.loft_solid(bm, S, "leather", rand=rng.random())
reg(bm, fs, "HOLSTER", "thigh_r")
for z in ho["straps_z"]:
    c = section_centre(z, lambda x: x < -0.03)
    fs, outer_s, dirs_s = band(bm, body_bvh, c, up_z, front_u, ho["strap"]["h"], ho["strap"]["thick"], ho["strap"]["gap"], 18, "leather",
                               reach=0.3, rand=rng.random())
    reg(bm, fs, "THIGH_STRAP_R", "thigh_r")
# pouch on the left hip
po = cfg["pouch"]
loc, n_, _, dist = body_bvh.ray_cast(Vector((0.7, po["y"], po["z"])), Vector((-1.0, 0, 0)), 0.7)
xs = loc.x if loc is not None else 0.19
sx, sy, sz = po["size"]
rings = []
for xi, (x, sc_) in enumerate(((xs + 0.004, 1.0), (xs + sx * 0.5, 1.0), (xs + sx, 0.88))):
    ring = []
    for a in np.arange(12) * 2 * math.pi / 12:
        ca, sa = math.cos(a), math.sin(a)
        ey = np.sign(ca) * abs(ca) ** 0.5
        ez = np.sign(sa) * abs(sa) ** 0.5
        ring.append((x, po["y"] + ey * sy / 2 * sc_, po["z"] + ez * sz / 2 * sc_))
    rings.append(ring)
fs = KG.loft_solid(bm, np.array(rings).transpose(1, 0, 2), "leather", rand=rng.random())
flap = [[(xs + sx + 0.001, po["y"] + (-1 + 2 * i / 4) * sy * 0.52, po["z"] + sz / 2 + 0.004 - j * po["flap"]) for j in range(3)] for i in range(5)]
ids, n_ids, quads, table = KG.grid_faces(5, 3)
Pf = np.zeros((n_ids, 3))
for vid, i, j, side in table:
    Pf[vid] = flap[i][j]
    Pf[vid][0] += 0.004 * (1 - abs(-1 + 2 * i / 4)) + 0.002 * j
fs += KG.surface_solid(bm, Pf, quads, 0.005, "leather", "leather", "leather", out_ref=lambda p: np.array([1.0, 0, 0]))[0]
fs += KG.stud(bm, (xs + sx + 0.007, po["y"], po["z"] + sz / 2 - po["flap"] * 1.6), (1.0, 0, 0), 0.006, 0.005, "bronze")
reg(bm, fs, "POUCH", "pelvis")
# left thigh strap with its buckle
lt = cfg["left_thigh_strap"]
c = section_centre(lt["z"], lambda x: x > 0.03)
fs, outer_s, dirs_s = band(bm, body_bvh, c, up_z, front_u, lt["h"], lt["thick"], lt["gap"], 18, "leather", reach=0.3, rand=rng.random())
k_ = int(round(lt["buckle_theta_deg"] / 360 * 18)) % 18
fs += buckle(bm, outer_s[k_], dirs_s[k_], up_z, lt["buckle"])
reg(bm, fs, "THIGH_STRAP_L", "thigh_l")
# arms: right bracer + straps + glove cuff, left bicep and wrist straps
am = cfg["arms"]
ax_x = np.array([1.0, 0, 0])
AZ = LM["upperarm_l.head"][2]
AY = LM["upperarm_l.head"][1]
bx = am["bracer"]
cb = np.array([-(bx["abs_x"][0] + bx["abs_x"][1]) / 2, AY, AZ])
fs, _, _ = band(bm, body_bvh, cb, ax_x, front_u, bx["abs_x"][1] - bx["abs_x"][0], bx["thick"], bx["gap"], am["segments"], "leather",
                stations=4, reach=0.2, rand=rng.random())
reg(bm, fs, "BRACER_R", "lowerarm_r")
gear_bvh = bvh_of([], [bm])
for x in bx["straps_abs_x"]:
    fs, _, _ = band(bm, gear_bvh, np.array([-x, AY, AZ]), ax_x, front_u, bx["strap"]["h"], bx["strap"]["thick"], 0.0, am["segments"],
                    "leather", reach=0.2, sink=0.002, rand=rng.random())
    reg(bm, fs, "BRACER_STRAP_R", "lowerarm_r")
for key, sd, bone in (("glove_cuff", -1, "hand_r"), ("bicep_strap", 1, "upperarm_l"), ("wrist_strap", 1, "lowerarm_l")):
    s_ = am[key]
    fs, _, _ = band(bm, body_bvh, np.array([sd * s_["abs_x"], AY, AZ]), ax_x, front_u, s_["h"], s_["thick"], s_["gap"], am["segments"],
                    "leather", reach=0.2, rand=rng.random())
    reg(bm, fs, key.upper() + ("_L" if sd > 0 else "_R"), bone)
gear_ob = finish(bm, "GEAR")

# ==============================================================================================================
# LOINCLOTH (maroon, front)
# ==============================================================================================================
lo = cfg["loin"]
bm = new_bm()
under_bvh = bvh_of([body, gear_ob])
NU, NV = lo["u"], lo["v"]
slit_cols = sorted(rng.sample(range(1, NU - 1), min(lo["slits"], NU - 2)))
ids, n_ids, quads, table = KG.grid_faces(NU, NV, slits={i: NV - 4 for i in slit_cols})
tears = [rng.uniform(*lo["tear"]) if i % 2 == 0 else rng.uniform(0.0, lo["tear"][0]) for i in range(NU)]
colY = {}
Pl = np.zeros((n_ids, 3))
for i in range(NU):
    yprev = None
    for j in range(NV):
        f = j / (NV - 1)
        z = lo["z"][0] + (lo["z"][1] - lo["z"][0]) * f - (tears[i] if j == NV - 1 else 0.0)
        hw = lo["half_width"][0] + (lo["half_width"][1] - lo["half_width"][0]) * f
        u = -1 + 2 * i / (NU - 1)
        x = u * hw + 0.004 * math.sin(f * 5.0 + u * 2.0)
        loc, n_, _, dist = under_bvh.ray_cast(Vector((x, -0.7, z)), Vector((0, 1.0, 0)), 1.0)
        if j == 0:
            ybase = (loc.y + 0.006) if loc is not None else -0.1
            y = ybase
        else:
            y_hit = (loc.y - lo["clear"]) if loc is not None else None
            y = yprev if y_hit is None else min(yprev, y_hit)
            y = y - 0.004 * (1 - u * u) * f
        yprev = y if j > 0 else ybase - lo["clear"]
        colY[(i, j)] = (x, y, z)
for vid, i, j, side in table:
    x, y, z = colY[(i, j)]
    if side == 1:
        x += 0.005
    Pl[vid] = (x, y, z)
fs, _, _ = KG.surface_solid(bm, Pl, quads, lo["thick"], "maroon", "maroon", "maroon", out_ref=lambda p: np.array([0, -1.0, 0]), rand=rng.random())
reg(bm, fs, "LOINCLOTH", "x_loin_C_01")
loin_ob = finish(bm, "LOINCLOTH")

# ==============================================================================================================
# BOOTS (left built, right mirrored)
# ==============================================================================================================
bo = cfg["boots"]
bmL = new_bm()
segs = bo["segments"]
angs, dirs = ring_dirs(up_z, front_u, np.array([1.0, 0, 0]), segs)
shaft = []
leg_c = {}
for zi, z in enumerate(bo["shaft_z"]):
    c = section_centre(z, lambda x: x > 0.04)
    leg_c[z] = c
    rr = np.array([r_out(body_bvh, c, d, 0.3) or 0.06 for d in dirs])
    rr = np.maximum(rr, (np.roll(rr, 1) + np.roll(rr, -1)) / 2)
    shaft.append([c + d * (r + bo["off"][zi]) for d, r in zip(dirs, rr)])
ctop = leg_c[bo["shaft_z"][-1]]
top = np.array(shaft[-1])
inner_top = [ctop + (p - ctop) * (1 - bo["rim"] / max(np.linalg.norm((p - ctop)[:2]), 0.02)) for p in top]
inner_low = [p - np.array([0, 0, 0.05]) for p in inner_top]
S = np.array(shaft + [inner_top, inner_low]).transpose(1, 0, 2)
fs = KG.loft_solid(bmL, S, "boot", masks=[0.4] * len(shaft) + [0.1, 0.0], rand=rng.random())
reg(bmL, fs, "BOOT_SHAFT_L", "calf_l")
# foot shell: lofted along the foot axis round the (lifted) body foot
ft = bo["foot"]
fv = bco[(bco[:, 0] > 0.04) & (bco[:, 2] < 0.16)]
heel, toe = np.array(LM["heel_l"]), np.array(LM["toe_l"])
a_ = unit(np.array([toe[0] - heel[0], toe[1] - heel[1], 0.0]))
s_ = np.array([-a_[1], a_[0], 0.0])
if s_[0] < 0:
    s_ = -s_
tv = (fv[:, :2] - heel[:2]) @ a_[:2]
sv = (fv[:, :2] - heel[:2]) @ s_[:2]
t0, t1 = tv.min() - ft["margin_len"], tv.max() + ft["margin_len"]
ts = np.linspace(t0, t1, 9)
prof_h = np.interp((ts - t0) / (t1 - t0), [0.0, 0.3, 0.5, 0.75, 1.0], [ft["heel_h"], ft["ankle_h"], 0.12, ft["ball_h"], ft["toe_h"]])
rings = []
for k, t in enumerate(ts):
    m = np.abs(tv - t) < max(0.025, (t1 - t0) / 9)
    if m.any():
        smin, smax = sv[m].min(), sv[m].max()
        hmax = fv[m, 2].max()
    else:
        smin, smax, hmax = -0.04, 0.04, 0.05
    wv = (smax - smin) / 2 + ft["margin_side"]
    sc_ = (smax + smin) / 2
    h = max(prof_h[k], hmax + ft["margin_top"]) if k not in (0, len(ts) - 1) else prof_h[k]
    shrink = 0.62 if k == 0 else (0.45 if k == len(ts) - 1 else (0.9 if k in (1, len(ts) - 2) else 1.0))
    base = heel[:2] + a_[:2] * t + s_[:2] * sc_
    ring = []
    for q in np.arange(ft["segments"]) * 2 * math.pi / ft["segments"]:
        cq, sq = math.cos(q), math.sin(q)
        ex = np.sign(cq) * abs(cq) ** 0.6
        ez = np.sign(sq) * abs(sq) ** 0.75
        zq = max(0.0, h * 0.42 + ez * h * 0.58 * (shrink if k in (0, len(ts) - 1) else 1.0))
        ring.append((base[0] + s_[0] * ex * wv * shrink, base[1] + s_[1] * ex * wv * shrink, zq))
    rings.append(ring)
fs = KG.loft_solid(bmL, np.array(rings).transpose(1, 0, 2), "boot", rand=rng.random())
reg(bmL, fs, "BOOT_FOOT_L", "foot_l")
report["boot_foot"] = {"length_m": round(float(t1 - t0), 4), "axis": a_.round(3).tolist()}
# knee cuff: flared, pointed over the knee
cu = bo["cuff"]
NUc = cu["segments"]
cangs = np.arange(NUc) * 2 * math.pi / NUc
ids, n_ids, quads, table = KG.grid_faces(NUc, 3, periodic_u=True)
Pc = np.zeros((n_ids, 3))
for vid, i, j, side in table:
    a = cangs[i]
    fr_ = max(0.0, math.cos(a)) ** 1.6
    zb = cu["z_back"][0] + (cu["z_front"][0] - cu["z_back"][0]) * fr_
    zt = cu["z_back"][1] + (cu["z_front"][1] - cu["z_back"][1]) * fr_
    f = j / 2
    z = zb + (zt - zb) * f
    c = section_centre(min(z, 0.7), lambda x: x > 0.04)
    d = np.array([math.sin(a), -math.cos(a), 0.0])
    r = r_out(body_bvh, c, d, 0.3) or 0.06
    Pc[vid] = c + d * (r + 0.02 + cu["flare"] * f ** 1.3 * (1 + 0.6 * fr_))
    Pc[vid][2] = z
fs, _, _ = KG.surface_solid(bmL, Pc, quads, cu["thick"], "boot", "boot", "boot", out_ref=lambda p: np.array([p[0] - 0.24, p[1], 0.0]),
                            rand=rng.random())
reg(bmL, fs, "BOOT_CUFF_L", "calf_l")
boot_bvh = bvh_of([], [bmL])
st_ = bo["strap"]
for z, tilt in bo["straps"]:
    c = section_centre(z, lambda x: x > 0.04)
    n_ = unit(np.array([0.0, -math.sin(math.radians(tilt)), math.cos(math.radians(tilt))]))
    fs, outer_s, dirs_s = band(bmL, boot_bvh, c, n_, front_u, st_["h"], st_["thick"], st_["gap"], segs, "leather", reach=0.3,
                               sink=0.002, rand=rng.random())
    kb = int(round(0.25 * segs)) % segs          # theta 90: the outer side of the left leg
    fs += buckle(bmL, outer_s[kb], dirs_s[kb], n_, st_["buckle"])
    reg(bmL, fs, "BOOT_STRAP_L", "calf_l")
bm = new_bm()
mirrored(bmL, bm)
boots_ob = finish(bm, "BOOTS")

# ==============================================================================================================
# COAT: yoke + sleeves, skirt (vent, torn hem), collar, lapels, cuffs
# ==============================================================================================================
cc = cfg["coat"]
yk = cc["yoke"]
bm = new_bm()
fc = np.array([p.center for p in polys])
fz = np.array([p.material_index for p in polys])
wopen = np.interp(fc[:, 2], yk["open_z"], yk["open_half_width"])
inside = (fc[:, 2] > yk["z_cut"]) & (fz != Zn["eye"])
inside &= ~((np.hypot(fc[:, 0], fc[:, 1] - 0.01) < yk["neck_r"]) & (fc[:, 2] > yk["neck_z"]))
inside &= ~((fc[:, 1] < 0.0) & (np.abs(fc[:, 0]) < wopen))
inside &= ~(fc[:, 0] < -yk["sleeve_end_abs_x"]["R"]) & ~(fc[:, 0] > yk["sleeve_end_abs_x"]["L"])
inside &= fc[:, 2] < 1.95
yidx = clean_face_region(inside)
axv = np.abs(bco[:, 0])
off = np.interp(axv, [0.0, 0.16, 0.22, 0.3], [yk["off_torso"], yk["off_torso"], yk["off_shoulder"], yk["off_arm"]])
fs, yvo, yof = region_shell(bm, yidx, off, "coat", "lining", "coat_edge", thick=cc["thick"], smooth=yk["smooth"],
                            mask_fn=lambda k, b: 0.0 if b else 1.0)
reg(bm, fs, "COAT_YOKE", "spine_03 (skinned: spine, clavicles, upper arms)")
yoke_bvh = bvh_of([], [bm])
report["coat_yoke"] = {"body_faces": len(yidx)}
# rolled cuffs at the sleeve ends
cf = cc["cuffs"]
for side, sd, bone in (("R", -1, "lowerarm_r"), ("L", 1, "upperarm_l")):
    s_ = cf[side]
    fs, _, _ = band(bm, yoke_bvh, np.array([sd * s_["abs_x"], AY, AZ]), ax_x, front_u, s_["h"], s_["thick"], cf["gap"], cf["segments"],
                    "coat", stations=1, reach=0.25, sink=0.006, ch=s_["thick"] * 0.5, rand=rng.random())
    reg(bm, fs, "COAT_CUFF_" + side, bone)
# skirt
sk = cc["skirt"]
under_bvh = bvh_of([body, gear_ob, loin_ob, boots_ob])
NU, NV = sk["nu"], sk["nv"]
ztop = sk["z_top"]
hem_ref = 0.45


def th_open(z):
    f = np.clip((ztop - z) / (ztop - hem_ref), 0, 1)
    return math.radians(sk["theta_open_deg"][0] + (sk["theta_open_deg"][1] - sk["theta_open_deg"][0]) * f)


def hem_base(th):
    pb = abs(math.degrees(th) - 180.0)
    return float(np.interp(pb, [0, 90, 180], [sk["hem"]["back"], sk["hem"]["side"], sk["hem"]["front"]]))


def ell(th, z):
    t = ztop - z
    a = sk["a"][0] + sk["a"][1] * t
    b = (sk["bf"][0] + sk["bf"][1] * t) if math.cos(th) > 0 else (sk["bb"][0] + sk["bb"][1] * t)
    s, c = math.sin(th), math.cos(th)
    return 1.0 / math.sqrt((s / a) ** 2 + (c / b) ** 2)


ic = NU // 2
tears = []
for i in range(NU):
    if i in (0, NU - 1):
        tears.append(rng.uniform(0.0, 0.03))
    elif i == ic:
        tears.append(rng.uniform(*sk["tear_short"]))
    else:
        tears.append(rng.uniform(*sk["tear_long"]) if i % 2 == 0 else rng.uniform(*sk["tear_short"]))
u_ = np.linspace(0, 1, NU)
TH = np.zeros((NU, NV))
ZZ = np.zeros((NU, NV))
RR = np.zeros((NU, NV))
HEM = np.zeros(NU)
for i in range(NU):
    th_mid = th_open(0.9) + u_[i] * (2 * math.pi - 2 * th_open(0.9))
    HEM[i] = hem_base(th_mid) - tears[i]
    for j in range(NV):
        f = j / (NV - 1)
        z = ztop + (HEM[i] - ztop) * f ** 0.92
        th = th_open(z) + u_[i] * (2 * math.pi - 2 * th_open(z))
        TH[i, j], ZZ[i, j] = th, z
        d = np.array([math.sin(th), -math.cos(th), 0.0])
        if j == 0:
            RR[i, j] = (r_out(body_bvh, (0, 0, z), d, 0.8) or 0.18) + sk["top_off"]
        else:
            ru = r_out(under_bvh, (0, 0, z), d, 1.2) or 0.0
            clr = sk["clear"][0] + (sk["clear"][1] - sk["clear"][0]) * f
            RR[i, j] = max(ell(th, z), ru + clr)
floor_r = RR.copy()
for _ in range(3):                     # smooth round and down (the top row stays tucked in the yoke's wall)
    Rn = RR.copy()
    Rn[1:-1, 1:] = 0.5 * RR[1:-1, 1:] + 0.25 * (RR[:-2, 1:] + RR[2:, 1:])
    Rn[:, 1:-1] = 0.6 * Rn[:, 1:-1] + 0.2 * (Rn[:, :-2] + Rn[:, 2:])
    Rn[:, 0] = RR[:, 0]
    RR = np.maximum(Rn, floor_r * (np.arange(NV) > 0)[None, :] + RR * (np.arange(NV) == 0)[None, :] * 0)
    RR[:, 0] = floor_r[:, 0]
jv = int(np.argmax(ZZ[ic] <= sk["vent_z"]))
slits = {ic: max(1, jv - 1)}
for i in range(2, NU - 2):
    if i % sk["slit_every"] == 1 and abs(i - ic) > 1:
        slits[i] = NV - 1 - sk["slit_rows"]
ids, n_ids, quads, table = KG.grid_faces(NU, NV, slits=slits)
Ps = np.zeros((n_ids, 3))
Ms = np.zeros((n_ids, 2))
crand = [rng.random() for _ in range(NU)]
for vid, i, j, side in table:
    th = TH[i, j]
    if i in slits and j > slits[i]:
        gap_ = math.radians(1.3 if i == ic else 0.5) * min(1.0, (j - slits[i]) / 2.0)
        th += gap_ if side == 1 else -gap_
    r = RR[i, j]
    Ps[vid] = (math.sin(th) * r, -math.cos(th) * r, ZZ[i, j])
    Ms[vid] = (float(np.clip((ZZ[i, j] - HEM[i]) / 0.3, 0, 1)), crand[i])
fs, svo, svi = KG.surface_solid(bm, Ps, quads, cc["thick"], "coat", "lining", "coat_edge",
                                out_ref=lambda p: np.array([p[0], p[1], 0.0]), mask=Ms)
lay = bm.faces.layers.int.get(PIECE_LAYER)
pidL = reg(bm, [], "COAT_SKIRT_L", "x_coat_L_* (front / side / back chains by theta)")
pidR = reg(bm, [], "COAT_SKIRT_R", "x_coat_R_* (front / side / back chains by theta)")
for f in fs:
    if f.is_valid:
        f[lay] = pidL if f.calc_center_median().x > 0 else pidR
report["coat_skirt"] = {"nu": NU, "nv": NV, "vent_from_z": round(float(ZZ[ic, slits[ic]]), 3), "hem_z_min_max": [round(float(HEM.min()), 3), round(float(HEM.max()), 3)],
                        "half_width_at_z": {str(z): round(float(max(abs(p[0]) for p in Ps if abs(p[2] - z) < 0.05) if any(abs(p[2] - z) < 0.05 for p in Ps) else 0), 3)
                                            for z in (1.07, 0.86, 0.65, 0.5)},
                        "back_depth_at_hem": round(float(Ps[:, 1].max()), 3)}
# collar
co_ = cc["collar"]
NUc = co_["nu"]
ths = np.radians(np.linspace(co_["theta_deg"][0], co_["theta_deg"][1], NUc))
ids, n_ids, quads, table = KG.grid_faces(NUc, 4)
Pk = np.zeros((n_ids, 3))
scarf_bvh = bvh_of([body, scarf_ob])
cN = section_centre(1.74, lambda x: np.abs(x) < 0.12)
rb = np.array([(r_out(scarf_bvh, cN, np.array([math.sin(t), -math.cos(t), 0.0]), 0.3) or 0.08) + co_["base_out"] for t in ths])
rb = np.convolve(np.pad(rb, 2, mode="edge"), np.ones(5) / 5, mode="valid")
for vid, i, j, side in table:
    u = i / (NUc - 1)
    e = max(0.0, 1 - min(u, 1 - u) / 0.22)
    zt = co_["z_top"] + co_["tip_rise"] * e ** 2
    rows = [(co_["z_base"], rb[i]), (co_["z_base"] + 0.05, rb[i] + 0.008),
            ((co_["z_base"] + zt) / 2 + 0.01, rb[i] + co_["flare"] * 0.45), (zt, rb[i] + co_["flare"] + co_["tip_flare"] * e ** 2)]
    z, r = rows[j]
    Pk[vid] = (cN[0] + math.sin(ths[i]) * r, cN[1] - math.cos(ths[i]) * r, z)
fs, _, _ = KG.surface_solid(bm, Pk, quads, cc["thick"], "coat", "lining", "coat_edge",
                            out_ref=lambda p: np.array([p[0] - cN[0], p[1] - cN[1], 0.0]), rand=rng.random())
reg(bm, fs, "COAT_COLLAR", "neck_01")
# lapels (left built, right mirrored)
lp = cc["lapel"]
bml = new_bm()
nr = len(lp["z"])
ids, n_ids, quads, table = KG.grid_faces(3, nr)
Pp = np.zeros((n_ids, 3))
for vid, i, j, side in table:
    z = lp["z"][nr - 1 - j]
    wd = lp["width"][nr - 1 - j]
    x_in = float(np.interp(z, yk["open_z"], yk["open_half_width"])) - 0.014
    x = x_in + wd * i / 2
    ys = []
    for xx in (x, x + 0.01, x + 0.02, x + 0.03):
        loc, n_, _, dist = yoke_bvh.ray_cast(Vector((xx, -0.7, z)), Vector((0, 1.0, 0)), 1.0)
        if loc is not None:
            ys.append(loc.y)
            break
    y = (ys[0] if ys else -0.12) - (lp["lift_in"] if i == 0 else (lp["lift_out"] if i == 2 else 0.5 * (lp["lift_in"] + lp["lift_out"])))
    Pp[vid] = (x, y, z)
fs, _, _ = KG.surface_solid(bml, Pp, quads, lp["thick"], "coat", "lining", "coat_edge", out_ref=lambda p: np.array([0.2, -1.0, 0.0]),
                            rand=rng.random())
reg(bml, fs, "COAT_LAPEL_L", "spine_03")
mirrored(bml, bm)
coat_ob = finish(bm, "COAT")

# ==============================================================================================================
# WISPS: ghost-flame tatters on the hem
# ==============================================================================================================
wc = cfg["wisps"]
bm = new_bm()
col_theta = TH[:, -1]
for wi, it in enumerate(wc["items"]):
    th = math.radians(it["theta_deg"])
    i = int(np.argmin(np.abs(((TH[:, -2] - th + math.pi) % (2 * math.pi)) - math.pi)))
    zh = HEM[i] + 0.02
    rz = RR[i]
    zcol = ZZ[i]

    def r_at(z):
        return float(np.interp(z, zcol[::-1], rz[::-1]))
    rows, cols = wc["rows"], wc["cols"]
    ids, n_ids, quads, table = KG.grid_faces(cols, rows)
    Pw = np.zeros((n_ids, 3))
    Mw = np.zeros((n_ids, 2))
    d = np.array([math.sin(th), -math.cos(th), 0.0])
    tg = np.array([math.cos(th), math.sin(th), 0.0])
    for vid, ci, rj, side in table:
        s = rj / (rows - 1)
        z = zh + it["root"] - (it["root"] + it["length"]) * s
        if z >= zh:
            r = r_at(z) + wc["stand_off"]
        else:
            q = (zh - z) / it["length"]
            r = r_at(zh) + wc["stand_off"] + it["curl"] * q ** 1.6
            z += it["curl"] * 0.35 * q ** 2.2
        u = -1 + 2 * ci / (cols - 1)
        hw = it["width"] / 2 * max((1 - s) ** 0.75 * (1 + 0.2 * math.sin(2.6 * math.pi * s + wi)), 0.0) + 0.0025
        cpt = d * r + tg * it["flick"] * math.sin(math.pi * s * 1.2) + np.array([0, 0, z])
        Pw[vid] = cpt + tg * u * hw + d * 0.004 * (1 - u * u) + tg * 0.015 * math.sin(3.0 * s + u) * s
        Mw[vid] = (s, (wi + 0.5) / len(wc["items"]))
    fs, _, _ = KG.surface_solid(bm, Pw, quads, wc["thick"], "wisp", "wisp", "wisp", out_ref=lambda p: np.array([p[0], p[1], 0.0]), mask=Mw)
    reg(bm, fs, "WISP_%d" % (wi + 1), "x_wisp_%d_01..03" % (wi + 1))
finish(bm, "WISPS")

# ==============================================================================================================
bpy.data.objects.remove(bpy.data.objects["REF_blockout"]) if "REF_blockout" in bpy.data.objects else None
report["parts"]["BODY"] = mesh_stats(body)
report["triangles_total"] = sum(v["triangles"] for v in report["parts"].values())
report["piece_table"] = piece_table
report["hand_frames"] = fitrep.get("hand_frames")
log("total triangles", report["triangles_total"])
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
