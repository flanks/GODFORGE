"""Cloth, strap and trim helpers for Kael's stage-2 parts (bmesh + numpy, no add-ons).

Kael's paint zones differ from Brax's (s2_geom.ZONES) and Valdris's (s2_valdris_geom.ZONES), so this module has its
own ZONES / Z; the shared per-vertex paint mask (gf_mask: R = 0 outline .. 1 centre, G = per-piece random, A = set)
is reused from s2_geom. Every builder appends CLOSED geometry to a bmesh and tags each new face with a zone (the
face material index), so each part stays manifold and the painter (s2_kael_paint.py) knows what every face is.

Builders:
  surface_solid  an open quad surface (points + faces) given thickness: the outer faces, the inner faces offset along
                 -normal (the lining of a coat), and rim walls on every boundary edge (the worn edge of the cloth).
                 The workhorse for the duster's yoke and sleeves, the skirt panels with their vent and torn hem, the
                 collar, the lapels, the ghost-flame tatters and the loin cloth.
  grid_faces     the quad faces of a (nu, nv) grid with optional slits (duplicated columns below a given row: the back
                 vent and the torn hem points)
  closed_loop    a closed tube through a loop of rings (bands: belts, straps, cuffs)
  loft_solid     a closed solid lofted through rings (holster, pouch, boot shafts, cartridges)
  cylinder, stud small round pieces (cartridges, buckle pins, the gem)
"""
import math

import bmesh
import numpy as np

import s2_geom as G0

ZONES = ["skin", "hair", "eye", "cloth", "glove", "ghost", "coat", "lining", "coat_edge", "maroon", "leather", "boot",
         "bronze", "gem", "wisp", "cartridge"]
Z = {n: i for i, n in enumerate(ZONES)}
ensure_mask = G0.ensure_mask
set_mask = G0.set_mask


def tag(faces, zone):
    zi = Z[zone]
    for f in faces:
        f.material_index = zi


def norm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def grid_faces(nu, nv, periodic_u=False, slits=None, skip_cells=None):
    """Vertex ids and quads of a (nu, nv) grid (i along u, j along v). slits: {i: j0} duplicates the vertices of
    column i for rows j > j0 (the cells left of the column keep the original, the cells right of it use the copy), so
    the surface opens along that column below row j0. Returns (index table idx[i][j] -> (left_id, right_id)), the
    number of vertex ids, the quads [(a, b, c, d)] and the list (id, i, j, side) of every id."""
    slits = slits or {}
    ids = {}
    table = []
    n = 0
    for i in range(nu):
        col = []
        for j in range(nv):
            left = n
            n += 1
            table.append((left, i, j, 0))
            right = left
            if i in slits and j > slits[i]:
                right = n
                n += 1
                table.append((right, i, j, 1))
            col.append((left, right))
        ids[i] = col
    quads = []
    iu = range(nu) if periodic_u else range(nu - 1)
    for i in iu:
        i2 = (i + 1) % nu
        for j in range(nv - 1):
            if skip_cells and (i, j) in skip_cells:
                continue
            a = ids[i][j][1]
            b = ids[i2][j][0]
            c = ids[i2][j + 1][0]
            d = ids[i][j + 1][1]
            quads.append((a, b, c, d))
    return ids, n, quads, table


def surface_solid(bm, P, quads, thick, zone_out, zone_in, zone_rim, out_ref=None, rand=None, mask=None, thick_v=None):
    """Closed shell from an open surface: points P (n, 3), quads (index tuples), thickness along -normal (thick_v:
    per-point thickness). out_ref(p) -> a direction the outer normal must agree with (else the faces flip).
    zone_out / zone_in / zone_rim: the outer, inner and rim zones (zone_out may be a callable(face_index) -> zone).
    mask: per-point gf_mask value for the outer points (default: 0 on the boundary, 1 inside), or (n, 2) = (R, G)
    per point. Returns (faces,
    outer verts, inner verts)."""
    ensure_mask(bm)
    P = np.asarray(P, dtype=np.float64)
    n = len(P)
    # area-weighted vertex normals of the open surface
    Nv = np.zeros((n, 3))
    for q in quads:
        pts = P[list(q)]
        fn = np.cross(pts[2] - pts[0], pts[3 % len(q)] - pts[1]) if len(q) == 4 else np.cross(pts[1] - pts[0], pts[2] - pts[0])
        for k in q:
            Nv[k] += fn
    Nv = norm(Nv)
    if out_ref is not None:
        agree = np.array([Nv[k] @ out_ref(P[k]) for k in range(n)])
        if np.sum(agree) < 0:
            Nv = -Nv
            quads = [tuple(reversed(q)) for q in quads]
    t = np.full(n, thick) if thick_v is None else np.asarray(thick_v, dtype=np.float64)
    I = P - Nv * t[:, None]
    vo = [bm.verts.new(tuple(p)) for p in P]
    vi = [bm.verts.new(tuple(p)) for p in I]
    faces = []
    edge_use = {}
    for fi, q in enumerate(quads):
        f = bm.faces.new([vo[k] for k in q])
        zo = zone_out(fi) if callable(zone_out) else zone_out
        f.material_index = Z[zo]
        g = bm.faces.new([vi[k] for k in reversed(q)])
        g.material_index = Z[zone_in]
        faces += [f, g]
        for a, b in zip(q, q[1:] + q[:1]):
            key = (min(a, b), max(a, b))
            edge_use.setdefault(key, []).append((a, b))
    bnd = set()
    for key, uses in edge_use.items():
        if len(uses) == 1:
            a, b = uses[0]
            f = bm.faces.new((vo[b], vo[a], vi[a], vi[b]))
            f.material_index = Z[zone_rim]
            faces.append(f)
            bnd.update(key)
    for k in range(n):
        g = rand
        mi = 0.0
        if mask is not None and np.ndim(mask) == 2:          # per point (R, G), the inner skin the same (a lining
            m, g = float(mask[k][0]), float(mask[k][1])      # keeps its distance to the hem)
            mi = m
        else:
            m = mask[k] if mask is not None else (0.0 if k in bnd else 1.0)
        set_mask(bm, [vo[k]], float(m), g)
        set_mask(bm, [vi[k]], mi, g)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces, vo, vi


def closed_loop(bm, loop, zone, rand=None, masks=None):
    """Closed tube from a loop of rings (each ring a list of points, all the same count): ring k joins ring k+1 and the
    last joins the first (a band's cross-section going round). masks: gf_mask value per ring."""
    ensure_mask(bm)
    vr = [[bm.verts.new(tuple(p)) for p in r] for r in loop]
    faces = []
    n = len(loop[0])
    for k in range(len(vr)):
        a, b = vr[k], vr[(k + 1) % len(vr)]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    tag(faces, zone)
    for k, r in enumerate(vr):
        set_mask(bm, r, masks[k] if masks else 0.5, rand)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def loft_solid(bm, S, zone_fn, rand=None, cap_zone=None, masks=None):
    """A closed solid lofted through the rings S[u, v] (u around, periodic; v along): quads between rings, the first
    and last rings closed with a centre fan."""
    ensure_mask(bm)
    S = np.asarray(S, dtype=np.float64)
    nu, nv = S.shape[:2]
    vv = [[bm.verts.new(tuple(S[i, j])) for j in range(nv)] for i in range(nu)]
    c0 = bm.verts.new(tuple(S[:, 0].mean(0)))
    c1 = bm.verts.new(tuple(S[:, -1].mean(0)))
    faces = []
    for i in range(nu):
        i2 = (i + 1) % nu
        for j in range(nv - 1):
            f = bm.faces.new((vv[i][j], vv[i2][j], vv[i2][j + 1], vv[i][j + 1]))
            f.material_index = Z[zone_fn(i, j) if callable(zone_fn) else zone_fn]
            faces.append(f)
        for cv, j in ((c0, 0), (c1, nv - 1)):
            f = bm.faces.new((vv[i][j], vv[i2][j], cv))
            f.material_index = Z[cap_zone or (zone_fn(i, max(0, j - 1)) if callable(zone_fn) else zone_fn)]
            faces.append(f)
    for i in range(nu):
        for j in range(nv):
            set_mask(bm, [vv[i][j]], masks[j] if masks else (0.3 if j in (0, nv - 1) else 1.0), rand)
    set_mask(bm, [c0, c1], 0.3, rand)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def frame_axes(d, up=(0.0, 0.0, 1.0)):
    """Orthonormal (d, u, v) with u as close to `up` as possible."""
    d = norm(d)
    up = np.asarray(up, dtype=np.float64)
    v = np.cross(d, up)
    if np.linalg.norm(v) < 1e-6:
        v = np.cross(d, [1.0, 0.0, 0.0])
    v = norm(v)
    u = norm(np.cross(v, d))
    return d, u, v


def cylinder(bm, p0, p1, r0, r1, zone, sides=8, zone_cap=None, bevel=0.0, rand=None, up=(0, 0, 1)):
    """A closed cylinder / frustum from p0 to p1 (radii r0, r1), optional chamfer `bevel` at both ends."""
    ensure_mask(bm)
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    d, u, v = frame_axes(p1 - p0, up)
    L = float(np.linalg.norm(p1 - p0))
    angs = np.arange(sides) * 2 * math.pi / sides + math.pi / sides

    def ring(t, r):
        c = p0 + d * t
        return [c + (u * math.cos(a) + v * math.sin(a)) * r for a in angs]
    stations = [(0.0, r0 - bevel), (bevel, r0), (L - bevel, r1), (L, r1 - bevel)] if bevel > 0 else [(0.0, r0), (L, r1)]
    vr = [[bm.verts.new(tuple(p)) for p in ring(t, r)] for t, r in stations]
    fs = []
    for A_, B_ in zip(vr[:-1], vr[1:]):
        for i in range(sides):
            j = (i + 1) % sides
            fs.append(bm.faces.new((A_[i], A_[j], B_[j], B_[i])))
    tag(fs, zone)
    caps = [bm.faces.new(list(reversed(vr[0]))), bm.faces.new(vr[-1])]
    tag(caps, zone_cap or zone)
    fs += caps
    set_mask(bm, vr[0] + vr[-1], 0.2, rand)
    if len(vr) > 2:
        set_mask(bm, vr[1] + vr[2], 0.9, rand)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def stud(bm, c, d, r, h, zone, sides=6, rand=None):
    """A low faceted dome (a rivet, the gem) on direction d."""
    ensure_mask(bm)
    d = norm(d)
    u = norm(np.cross(d, [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0]))
    v = np.cross(d, u)
    c = np.asarray(c, dtype=np.float64)
    angs = np.arange(sides) * 2 * math.pi / sides
    vb = [bm.verts.new(tuple(c - d * 0.003 + (math.cos(a) * u + math.sin(a) * v) * r)) for a in angs]
    vm = [bm.verts.new(tuple(c + d * h * 0.55 + (math.cos(a) * u + math.sin(a) * v) * r * 0.78)) for a in angs]
    vt = bm.verts.new(tuple(c + d * h))
    fs = []
    for i in range(sides):
        j = (i + 1) % sides
        fs.append(bm.faces.new((vb[i], vb[j], vm[j], vm[i])))
        fs.append(bm.faces.new((vm[i], vm[j], vt)))
    fs.append(bm.faces.new(list(reversed(vb))))
    tag(fs, zone)
    set_mask(bm, vb, 0.2, rand)
    set_mask(bm, vm + [vt], 0.9, rand)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def rect_ring(bm, c, n, up, w, h, bar, depth, zone, rand=None, corner=0.3):
    """A rectangular buckle frame: outline w x h (in the plane normal to n, `up` = the h direction), bar = the frame's
    width, depth along n; the corners chamfered by `corner` x bar. Closed (a rectangular torus)."""
    n = norm(n)
    up = norm(np.asarray(up, dtype=np.float64) - n * (np.asarray(up) @ n))
    side = np.cross(up, n)
    c = np.asarray(c, dtype=np.float64)

    def outline(hw, hh, ch):
        pts = [(hw - ch, hh), (-hw + ch, hh), (-hw, hh - ch), (-hw, -hh + ch), (-hw + ch, -hh), (hw - ch, -hh), (hw, -hh + ch), (hw, hh - ch)]
        return pts
    o = outline(w / 2, h / 2, bar * corner * 2)
    i = outline(w / 2 - bar, h / 2 - bar, bar * corner)
    rings = []
    for ol, dd in ((o, depth / 2), (i, depth / 2), (i, -depth / 2), (o, -depth / 2)):
        rings.append([c + side * a + up * b + n * dd for a, b in ol])
    return closed_loop(bm, rings, zone, rand, masks=[0.8, 0.3, 0.1, 0.1])


def lock(bm, root, nrm, d0, bend, L, w, t, rng, zone, sides=6):
    """A chunky stylised hair / beard clump (s2_geom.lock with Kael's zones): a tapered lens-section loft from root
    (sunk into the shell) along d0, bending toward bend, closing in a point. gf_mask R rises from root to tip."""
    ensure_mask(bm)
    nrm = np.asarray(nrm, dtype=np.float64)
    d0 = np.asarray(d0, dtype=np.float64)
    bend = np.asarray(bend, dtype=np.float64)
    dirs = []
    for k in range(3):
        d = d0 * (1 - 0.35 * k) + bend * (0.35 * k)
        dirs.append(d / np.linalg.norm(d))
    c = [np.asarray(root, dtype=np.float64) - nrm * 0.008]
    for k, f in enumerate((0.3, 0.3)):
        c.append(c[-1] + dirs[k] * L * f)
    tip = c[-1] + dirs[2] * L * 0.4
    scales = (1.0, 0.8, 0.5)
    rings = []
    for k in range(3):
        T = dirs[min(k, 2)]
        a = np.cross(T, nrm)
        if np.linalg.norm(a) < 1e-6:
            a = np.cross(T, [1.0, 0.0, 0.0])
        a /= np.linalg.norm(a)
        b = np.cross(a, T)
        r = []
        for i in range(sides):
            th = i * 2 * math.pi / sides
            r.append(c[k] + a * math.cos(th) * w / 2 * scales[k] + b * math.sin(th) * t / 2 * scales[k] * rng.uniform(0.9, 1.1))
        rings.append(r)
    vr = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    vt = bm.verts.new(tuple(tip))
    fs = []
    for A_, B_ in zip(vr[:-1], vr[1:]):
        for i in range(sides):
            j = (i + 1) % sides
            fs.append(bm.faces.new((A_[i], A_[j], B_[j], B_[i])))
    for i in range(sides):
        fs.append(bm.faces.new((vr[-1][i], vr[-1][(i + 1) % sides], vt)))
    fs.append(bm.faces.new(list(reversed(vr[0]))))
    tag(fs, zone)
    for k, m in enumerate((0.3, 0.55, 0.8)):
        set_mask(bm, vr[k], m)
    set_mask(bm, [vt], 1.0)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def mirror_into(bm_src, bm_dst, piece_layer=None, piece_map=None):
    """Append the x-mirrored copy of bm_src (closed geometry) to bm_dst, keeping zones, the mask layer and (with
    piece_layer) the piece ids mapped through piece_map(old_id) -> new_id."""
    lay_s = bm_src.verts.layers.float_color.get(G0.MASK_LAYER)
    lay_d = ensure_mask(bm_dst)
    pl_s = bm_src.faces.layers.int.get(piece_layer) if piece_layer else None
    pl_d = (bm_dst.faces.layers.int.get(piece_layer) or bm_dst.faces.layers.int.new(piece_layer)) if piece_layer else None
    vmap = {}
    for v in bm_src.verts:
        nv_ = bm_dst.verts.new((-v.co.x, v.co.y, v.co.z))
        if lay_s is not None:
            nv_[lay_d] = v[lay_s]
        vmap[v] = nv_
    fs = []
    for f in bm_src.faces:
        g = bm_dst.faces.new([vmap[v] for v in reversed(f.verts)])
        g.material_index = f.material_index
        if pl_s is not None:
            g[pl_d] = piece_map(f[pl_s]) if piece_map else f[pl_s]
        fs.append(g)
    return fs
