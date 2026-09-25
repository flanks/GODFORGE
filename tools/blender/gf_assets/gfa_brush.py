"""gf_assets broad-plane painter: a few broad painted VALUE PLANES and tapered BRUSH STROKES on the edges.
It is an opt-in repaint for the zones you name, layered on gfa_paint. gfa_paint itself is unchanged, so
every asset that does not ask for it paints exactly as before.

Why it exists: in the colossus_cannon art review (2026-09-25), the gunmetal read as "procedural brushed
metal" up close. gfa_paint gives every quantised facet normal its own value and breaks the edge highlight
of every sharp edge into fbm dabs. On lathes (sleeves, barrels) and on long parallel bevels (drum staves)
both terms run along the part, so the metal fills with thin, regular, light streaks. For the zones it is
given, this painter replaces those two terms:

  * BROAD VALUE PLANES. Each part gets its own principal frame (a PCA of its vertices). A texel's normal
    is nudged by low-frequency noise, so the borders wobble like a brush edge, and then snaps to the
    dominant +-axis of that frame. A box face becomes one plane. A chamfer joins one of its two
    neighbours instead of becoming its own stripe. A lathe splits into four broad quarter planes. Every
    (part, plane) pair is hashed to one of a few value steps (mixed toward the zone's shadow or light
    colour). The steps are hashed, not lit, so no light direction is baked in.
  * BRUSH STROKES on convex sharp edges. A 3-D value noise sampled ON the edge line decides where the brush
    touches. Strokes are about `stroke_len` long. Their width and their paint load both taper to a point at
    the two ends, and they leave gaps. Each stroke belongs to its OWN part's edges, so an edge of a
    neighbouring part (a shell in a gap, a drum core) never paints across this part's face. Each part also
    reads the noise at its own random offset. The two edges of one chamfer lie close together, so they
    share the noise and merge into ONE broad stroke, but the staves on either side of a gap never line
    their strokes up into pinstripes. A thinner, lighter core (the glint) runs down the fattest strokes.
    Set GFA_BRUSH_DEBUG=1 in the environment to paint the strokes pure red while tuning.
  * The rest comes from the zone's gfa_paint recipe: base / shadow / light, the gradient, AO contact
    shadow shapes and cavity lines. The recipe's planes, parts, brush, stroke, spots and edge terms are
    ignored for broad zones.

    import gfa_brush as B
    rep = B.paint_asset(mesh, KEY, RECIPES, tex_dir, broad={"gunmetal": B.broad()}, decals=..., seed=7)

paint_asset() takes the same arguments as gfa_paint.paint_asset() plus `broad`, and it returns the same
report plus "broad_zones". The pipeline (unwrap, bakes, edge distances, dilation, final material) is
gfa_paint's, reused as it is. The decal pass is gfa_paint.paint()'s, copied so that it runs AFTER the
repaint. Only the texel loop for the broad zones is new. First used by
art/weapons/colossus_cannon/source/colossus_cannon_build.py (gunmetal and iron).
"""
import math
import os
import time

import bmesh
import numpy as np
from mathutils.kdtree import KDTree

import gfa_common as C
import gfa_paint as P

BROAD_DEFAULTS = {
    "levels": (-0.28, -0.1, 0.08, 0.24),  # value steps per plane: < 0 mixes toward the shadow, > 0 toward the light
    "wobble": 0.3,             # normal noise before snapping (the brushy border between two planes)
    "wobble_freq": 7.0,        # cycles per metre
    "inner": 0.035,            # +- soft value drift inside a plane (a painted plane is never perfectly flat)
    "inner_freq": 2.5,
    "stroke": 0.9,             # strength of the edge strokes (mixed toward the zone's light colour)
    "stroke_width": 0.009,     # m, half-width of the fattest part of a stroke
    "stroke_len": 0.14,        # m, the noise lattice along the edges (typical stroke + gap length)
    "stroke_cover": 0.5,       # fraction of the edge length the brush touches
    "stroke_taper": 0.22,      # how gradually a stroke thins to its tip (noise units)
    "glint": 0.55,             # strength of the lighter core along the fattest strokes
    "glint_color": None,       # None -> the light colour mixed halfway to white
    "edge_min_angle": None,    # None -> paint_asset's edge_min_angle
}


def broad(**kw):
    """A broad-zone recipe: BROAD_DEFAULTS updated with kw (unknown keys are an error)."""
    bad = set(kw) - set(BROAD_DEFAULTS)
    if bad:
        raise KeyError("unknown broad keys: %s" % sorted(bad))
    b = dict(BROAD_DEFAULTS)
    b.update(kw)
    return b


# ---- geometry data ---------------------------------------------------------------------------------------

def part_frames(obj):
    """{part id: 3x3 matrix whose columns are the part's principal axes} from the gfa_part face attribute.
    Rotationally symmetric parts (lathes) get an arbitrary but deterministic pair of cross axes."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = bm.faces.layers.int.get("gfa_part")
    groups = {}
    for f in bm.faces:
        pid = f[layer] if layer is not None else 0
        groups.setdefault(pid, set()).update(v.index for v in f.verts)
    co = np.array([v.co[:] for v in bm.verts], dtype=np.float64)
    bm.free()
    frames = {}
    for pid, vids in groups.items():
        pts = co[sorted(vids)]
        if len(pts) < 3:
            frames[pid] = np.eye(3)
            continue
        cov = np.cov((pts - pts.mean(0)).T)
        _, vec = np.linalg.eigh(cov)
        frames[pid] = vec[:, ::-1].copy()          # columns: longest -> shortest axis
    return frames


def edge_samples(obj, spacing=0.002, min_angle=20.0, sharp_only_below=60.0):
    """Samples along the CONVEX sharp edges as (points (N, 3) float32, part ids (N,) int64). The edge rule
    is gfa_paint.edge_points(): marked sharp and bending more than min_angle, or bending more than
    sharp_only_below whatever the marking."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = bm.faces.layers.int.get("gfa_part")
    lim, big = math.radians(min_angle), math.radians(sharp_only_below)
    pts, pids = [], []
    for e in bm.edges:
        if not e.is_manifold:
            continue
        ang = e.calc_face_angle_signed(0.0)
        if ang <= 0 or ang < lim or (e.smooth and ang < big):
            continue
        pid = e.link_faces[0][layer] if layer is not None else 0
        p0, p1 = e.verts[0].co, e.verts[1].co
        n = max(1, int((p1 - p0).length / spacing))
        for i in range(n):
            pts.append(p0.lerp(p1, (i + 0.5) / n)[:])
            pids.append(pid)
    bm.free()
    return np.array(pts, dtype=np.float32).reshape(-1, 3), np.array(pids, dtype=np.int64)


def own_edge_strokes(pos, part, pts, pids, weights):
    """For texels (pos, part): distance to the nearest convex edge sample OF THE SAME PART and that
    sample's stroke weight. A stroke belongs to its own part's edge, so an edge of a neighbouring part
    (a shell in the gap, the drum core) never paints a stripe across this part's face."""
    d = np.full(len(pos), 9.0, dtype=np.float32)
    w = np.zeros(len(pos), dtype=np.float32)
    for pid in np.unique(part):
        mt = np.nonzero(part == pid)[0]
        ms = np.nonzero(pids == pid)[0]
        if not len(ms):
            continue
        dd, ii = _kd_nearest(pts[ms], pos[mt])
        d[mt] = dd
        w[mt] = weights[ms][ii]
    return d, w


def _kd_nearest(points, queries):
    """(distance, index) of the nearest of `points` for every query (N, 3). Empty points -> (9.0, -1)."""
    if len(points) == 0:
        return np.full(len(queries), 9.0, dtype=np.float32), np.full(len(queries), -1, dtype=np.int64)
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(tuple(p), i)
    kd.balance()
    find = kd.find
    d = np.empty(len(queries), dtype=np.float32)
    idx = np.empty(len(queries), dtype=np.int64)
    for i, q in enumerate(queries.tolist()):
        _, j, dist = find(q)
        d[i] = dist
        idx[i] = j
    return d, idx


# ---- the broad painter ------------------------------------------------------------------------------------

def plane_keys(p, n, part, frames, wobble, wobble_freq, seed):
    """Plane id per texel: the dominant +-axis (0..5) of the noise-nudged normal in the part's frame."""
    nl = np.empty_like(n)
    for pid in np.unique(part):
        m = part == pid
        R = frames.get(int(pid), np.eye(3)).astype(np.float32)
        nl[m] = n[m] @ R
    if wobble > 0:
        w = np.stack([P.spread01(P.fbm(p, wobble_freq, 2, seed=seed + 300 + 7 * k)) for k in range(3)], 1)
        nl = nl + (w - 0.5) * 2.0 * wobble
    ax = np.abs(nl).argmax(1)
    sgn = nl[np.arange(len(nl)), ax] > 0
    return ax * 2 + sgn.astype(np.int64)


def repaint_broad(r, b, p, nt, part, ao, dist_concave, conv_d, conv_w, frames, seed):
    """Paint the texels of one broad zone. r: the zone's gfa_paint recipe; b: the broad() recipe;
    conv_d / conv_w: distance to the nearest convex edge sample and that sample's stroke weight (0..1).
    Returns (N, 3) sRGB 0..1."""
    n = len(p)
    b0 = P.hex3(r["base"])
    sh = P.hex3(r["shadow"]) if r["shadow"] else P.derive_shadow(b0)
    li = P.hex3(r["light"]) if r["light"] else P.derive_light(b0)
    c = np.repeat(b0[None], n, 0)
    # broad value planes
    key = plane_keys(p, nt, part, frames, b["wobble"], b["wobble_freq"], seed)
    lv = np.asarray(b["levels"], dtype=np.float32)
    h = P._hash(part, key, np.full_like(key, 5), seed + 404)
    lev = lv[np.minimum((h * len(lv)).astype(np.int64), len(lv) - 1)]
    c = P.mix(c, sh, np.clip(-lev, 0, 1))
    c = P.mix(c, li, np.clip(lev, 0, 1))
    # the zone gradient (e.g. darker toward the elbow)
    g = r["gradient"]
    if g:
        t = P.smoothstep(g["range"][0], g["range"][1], P._field(p, g))
        gc = li if g["color"] == "light" else sh if g["color"] == "shadow" else P.hex3(g["color"])
        c = P.mix(c, gc, t * g.get("amount", 0.3))
    # soft drift inside the planes
    if b["inner"] > 0:
        c = c * (1 + b["inner"] * (P.spread01(P.fbm(p, b["inner_freq"], 2, seed=seed + 505)) * 2 - 1))[:, None]
    # contact shadows (baked AO -> a painted shape) and cavity lines, as in gfa_paint
    dabs = P.spread01(P.fbm(p, 11.0, 2, seed=seed + 6))
    occ = 1 - ao
    k = P.smoothstep(r["ao_range"][0], r["ao_range"][1], occ + (dabs - 0.5) * 0.1)
    c = P.mix(c, sh, k * r["ao"])
    cw = r["cavity_width"]
    k = P.smoothstep(cw, cw * 0.25, dist_concave)
    c = P.mix(c, sh * 0.85, k * r["cavity"])
    # brush strokes on the convex edges: width AND paint load follow the stroke weight (tapered, fading
    # tips), with a small width wobble
    wob = 0.85 + 0.3 * P.spread01(P.fbm(p, 28.0, 2, seed=seed + 606))
    ew = b["stroke_width"] * (0.3 + 0.7 * np.sqrt(conv_w)) * wob
    k = P.smoothstep(ew, ew * 0.4, conv_d) * P.smoothstep(0.02, 0.4, conv_w)
    c = P.mix(c, li, k * b["stroke"])
    if os.environ.get("GFA_BRUSH_DEBUG"):
        c = P.mix(c, np.array([1.0, 0.0, 0.0], dtype=np.float32), k)
    if b["glint"] > 0:
        gl = P.hex3(b["glint_color"]) if b["glint_color"] else (li + 1.0) * 0.5
        kg = P.smoothstep(ew * 0.45, ew * 0.15, conv_d) * P.smoothstep(0.7, 0.95, conv_w)
        c = P.mix(c, gl, kg * b["glint"])
    return np.clip(c, 0, 1)


def stroke_weights(samples, b, seed, pids=None):
    """Stroke weight (0..1) at every convex edge sample: low-frequency 3-D noise thresholded to the
    requested coverage with a soft taper, so strokes fade to a point at both ends. With pids, every part
    reads the noise at its own random offset: the two edges of one chamfer still share their stroke, but
    neighbouring parts (the staves either side of a gap) never line their strokes up into pinstripes."""
    if len(samples) == 0:
        return np.zeros(0, dtype=np.float32)
    s = np.asarray(samples, dtype=np.float32)
    if pids is not None:
        off = np.stack([P.hash01(pids, seed + 808 + k) for k in range(3)], 1) * 37.0
        s = s + off.astype(np.float32)
    nz = P.spread01(P.fbm(s, 1.0 / b["stroke_len"], 2, seed=seed + 707), gain=2.6)
    thr = 1.0 - b["stroke_cover"]
    return P.smoothstep(thr, min(1.0, thr + b["stroke_taper"]), nz).astype(np.float32)


def apply_decals(base, emis, P_, Nt, Z, zones_order, decals):
    """gfa_paint.paint()'s decal pass, unchanged (painted lines, burnt rims, glowing channels)."""
    N = len(P_)
    for dec in decals:
        target = np.ones(N, dtype=bool) if not dec["zones"] else np.isin(Z, [zones_order.index(z) for z in dec["zones"]])
        idx = np.nonzero(target)[0]
        line, rimm = P._decal_masks(dec, P_[idx], Nt[idx])
        if dec["rim"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["rim"]), rimm * 0.75)
        if dec["color"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["color"]), line)
        if dec["emit"]:
            ec = P.hex3(dec["emit"]["color"])
            core = P.hex3(dec["emit"].get("core", dec["emit"]["color"]))
            glow = P.mix(np.repeat(ec[None], len(idx), 0), core, P.smoothstep(0.5, 1.0, line))
            emis[idx] = np.maximum(emis[idx], glow * np.maximum(line, rimm * 0.25)[:, None])
    return np.clip(base, 0, 1), np.clip(emis, 0, 1)


# ---- one call ---------------------------------------------------------------------------------------------

def paint_asset(obj, key, recipes, tex_dir, size=1024, decals=(), broad=None, ao_distance=0.05, ao_samples=16,
                edge_min_angle=20.0, margin_px=6, seed=0, uv_angle=60.0, preview_dir=None, uv_zone_scale=None,
                uv_small_islands=None):
    """gfa_paint.paint_asset() with the zones in `broad` ({zone: broad(...)}) repainted with broad value
    planes and brush strokes. Writes <tex_dir>/<key>_basecolor.png + <key>_emissive.png, assigns M_<key>
    and returns gfa_paint's report plus {"broad_zones": [...]}."""
    broad = broad or {}
    t0 = time.time()
    zones_order = [s.material.name[4:] for s in obj.material_slots]
    missing = [z for z in zones_order if z not in recipes]
    if missing:
        raise KeyError("no paint recipe for zones %s" % missing)
    unknown = [z for z in broad if z not in zones_order]
    if unknown:
        raise KeyError("broad zones not on the mesh: %s" % unknown)
    frames = part_frames(obj)
    dens = P.unwrap(obj, size, margin_px, uv_angle, zone_scale=uv_zone_scale, small_islands=uv_small_islands)
    C.log("unwrapped: %.0f px/m median" % dens["median"])
    mp = P.bake_maps(obj, size, ao_distance, ao_samples)
    zone_img = mp["zone"][..., 0]
    valid = zone_img > 0.5 / 64
    ao_img = P.masked_blur(mp["ao"][..., 0], valid, radius=2, passes=2)
    lo, hi = mp["lo"], mp["hi"]
    flat = {
        "zone": np.rint(zone_img[valid] * 64 - 1).astype(np.int64),
        "pos": (mp["pos"][..., :3][valid] * (hi - lo) + lo).astype(np.float32),
        "tnrm": mp["tnrm"][..., :3][valid] * 2 - 1,
        "snrm": mp["snrm"][..., :3][valid] * 2 - 1,
        "part": np.rint(mp["part"][..., 0][valid] * 4096 - 1).astype(np.int64),
        "ao": ao_img[valid].astype(np.float32),
    }
    for k in ("tnrm", "snrm"):
        flat[k] = flat[k] / (np.linalg.norm(flat[k], axis=1, keepdims=True) + 1e-9)
    # edge samples once: gfa_paint's distances for the ordinary zones, nearest-sample ids for the strokes
    t = time.time()
    convex, concave = P.edge_points(obj, 0.002, edge_min_angle)
    dv = P._kd_dist(convex, flat["pos"], 0.05)
    dc = P._kd_dist(concave, flat["pos"], 0.05)
    C.log("edge samples: %d convex / %d concave, %d texels (%.1fs)" % (len(convex), len(concave), len(dv),
                                                                       time.time() - t))
    base, emis = P.paint(flat, zones_order, recipes, dv, dc, decals=(), seed=seed)
    samples = {}
    for zname, b in broad.items():
        m = flat["zone"] == zones_order.index(zname)
        if not m.any():
            continue
        ang = b["edge_min_angle"] if b["edge_min_angle"] is not None else edge_min_angle
        if ang not in samples:
            samples[ang] = edge_samples(obj, 0.002, ang)
        pts, pids = samples[ang]
        w_s = stroke_weights(pts, b, seed, pids)
        d_z, cw = own_edge_strokes(flat["pos"][m], flat["part"][m], pts, pids, w_s)
        if len(w_s):
            C.log("broad zone %s strokes: %.0f%% of the edge length touched, %.0f%% at full load" % (
                zname, 100 * float((w_s > 0.02).mean()), 100 * float((w_s > 0.4).mean())))
        base[m] = repaint_broad(recipes[zname], b, flat["pos"][m], flat["tnrm"][m], flat["part"][m],
                                flat["ao"][m], dc[m], d_z, cw, frames, seed + 17 * zones_order.index(zname))
        C.log("broad zone %s: %d texels, %d parts" % (zname, int(m.sum()), len(np.unique(flat["part"][m]))))
    base, emis = apply_decals(base, emis, flat["pos"], flat["tnrm"], flat["zone"], zones_order, decals)
    B = np.zeros((size, size, 3), dtype=np.float32)
    E = np.zeros((size, size, 3), dtype=np.float32)
    B[valid] = base
    E[valid] = emis
    B = P.dilate(B, valid, 12)
    E = P.dilate(E, valid, 12)
    C.ensure_dir(tex_dir)
    bp = os.path.join(tex_dir, "%s_basecolor.png" % key)
    ep = os.path.join(tex_dir, "%s_emissive.png" % key)
    P.save_png(bp, B, "%s_basecolor" % key)
    P.save_png(ep, E, "%s_emissive" % key)
    if preview_dir:
        P.save_png(os.path.join(preview_dir, "%s_ao.png" % key), np.repeat(ao_img[..., None], 3, 2), "%s_ao_dbg" % key)
    P.apply_final_material(obj, "M_%s" % key, bp, ep)
    rep = {"size": size, "texel_density_px_per_m": dens, "coverage": round(float(valid.mean()), 3),
           "zones": zones_order, "broad_zones": sorted(broad), "decals": len(decals), "basecolor": C.rel(bp),
           "emissive": C.rel(ep), "emissive_texels": int((E.max(2) > 0.02).sum()),
           "seconds": round(time.time() - t0, 1)}
    C.log("painted %s in %.0fs (coverage %.0f%%, broad zones %s)" % (key, rep["seconds"], 100 * rep["coverage"],
                                                                     sorted(broad)))
    return rep
