"""Hard-surface plate helpers for Valdris's stage-2 armour (bmesh + numpy, no add-ons).

Valdris's paint zones differ from Brax's (s2_geom.ZONES), so this module has its own ZONES / Z; the shared
per-vertex paint mask (gf_mask: R = 0 plate outline .. 1 plate centre, G = per-piece random, A = set) is reused
from s2_geom. Every builder appends CLOSED geometry to a bmesh and tags each new face with a zone (material index),
so each part stays manifold and the painter (s2_valdris_paint.py) knows what every face is.

Builders:
  grid_solid     a plate from an outer surface grid S[u, v] (periodic in u or not): outer quads, an inner surface
                 offset along -normal by the thickness, walls on the open borders. The workhorse for torso bands,
                 limb plates (tubes and partial tubes), tassets, the cape, the beard block.
  prism          a planar outline extruded along a direction with a chamfered front face (anvil, pauldron blocks,
                 upright plates, fauld chevrons): side walls, chamfer ring, front and back faces.
  lobe, cylinder, stud   small round pieces (braid lobes, braid rings and caps, rivets).
"""
import math

import bmesh
import numpy as np
from mathutils import Vector

import s2_geom as G0

ZONES = ["skin", "beard", "eye", "plate", "iron", "gold", "seam", "cape", "mail", "leather", "steel", "anvil", "lava"]
Z = {n: i for i, n in enumerate(ZONES)}
ensure_mask = G0.ensure_mask
set_mask = G0.set_mask


def tag(faces, zone):
    zi = Z[zone]
    for f in faces:
        f.material_index = zi


def _norm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def grid_normals(S, periodic_u, out_ref):
    """Per-point normals of a surface grid S (nu, nv, 3) from central differences, oriented along out_ref(p)."""
    nu, nv = S.shape[:2]
    if periodic_u:
        du = np.roll(S, -1, 0) - np.roll(S, 1, 0)
    else:
        du = np.zeros_like(S)
        du[1:-1] = S[2:] - S[:-2]
        du[0] = S[1] - S[0]
        du[-1] = S[-1] - S[-2]
    dv = np.zeros_like(S)
    dv[:, 1:-1] = S[:, 2:] - S[:, :-2]
    dv[:, 0] = S[:, 1] - S[:, 0]
    dv[:, -1] = S[:, -1] - S[:, -2]
    N = _norm(np.cross(du, dv))
    ref = np.array([[out_ref(S[i, j]) for j in range(nv)] for i in range(nu)])
    flip = (N * ref).sum(-1) < 0
    N[flip] *= -1
    return N


def grid_solid(bm, S, thick, zone_fn, periodic_u=False, out_ref=None, N=None, inner=None, zone_in="iron",
               wall_zone=("iron", "iron", "iron", "iron"), rand=None, edge_mask=True, lip=0.0, simple_inner=False):
    """Closed plate from the outer surface grid S (nu, nv, 3).
    zone_fn(i, j) -> zone of the outer cell (i, j) (i along u, j along v) or a zone name for all.
    inner: optional explicit inner grid; else S - N * thick (N from out_ref or given).
    wall_zone: zones of the walls at v=0, v=end, u=0, u=end (the last two only when not periodic).
    Mask: outer border vertices 0.0 (plate outline), one row in 0.35, the rest 1.0; inner 0.0.
    lip: the outer border vertices are pulled in along -N by this much (a chamfered, bevelled-looking edge).
    simple_inner: the inner surface keeps only the first and last v rows (it is hidden; saves triangles)."""
    ensure_mask(bm)
    S = np.asarray(S, dtype=np.float64)
    nu, nv = S.shape[:2]
    if N is None:
        N = grid_normals(S, periodic_u, out_ref)
    if simple_inner and inner is None and nv > 2:
        # the hidden inner wall needs no rows between the two edges: a straight strip, half the triangles
        return _grid_solid_simple(bm, S, N, thick, zone_fn, periodic_u, zone_in, wall_zone, rand, edge_mask, lip)
    I = np.asarray(inner, dtype=np.float64) if inner is not None else S - N * thick
    So = S.copy()
    if lip:
        border = np.zeros((nu, nv), bool)
        border[:, 0] = border[:, -1] = True
        if not periodic_u:
            border[0, :] = border[-1, :] = True
        So[border] -= N[border] * lip
    vo = [[bm.verts.new(tuple(So[i, j])) for j in range(nv)] for i in range(nu)]
    vi = [[bm.verts.new(tuple(I[i, j])) for j in range(nv)] for i in range(nu)]
    faces = []
    iu = range(nu) if periodic_u else range(nu - 1)
    for i in iu:
        i2 = (i + 1) % nu
        for j in range(nv - 1):
            f = bm.faces.new((vo[i][j], vo[i2][j], vo[i2][j + 1], vo[i][j + 1]))
            f.material_index = Z[zone_fn(i, j) if callable(zone_fn) else zone_fn]
            faces.append(f)
            g = bm.faces.new((vi[i][j + 1], vi[i2][j + 1], vi[i2][j], vi[i][j]))
            g.material_index = Z[zone_in]
            faces.append(g)
    # walls
    for i in iu:
        i2 = (i + 1) % nu
        f = bm.faces.new((vo[i][0], vi[i][0], vi[i2][0], vo[i2][0]))
        f.material_index = Z[wall_zone[0]]
        g = bm.faces.new((vo[i2][nv - 1], vi[i2][nv - 1], vi[i][nv - 1], vo[i][nv - 1]))
        g.material_index = Z[wall_zone[1]]
        faces += [f, g]
    if not periodic_u:
        for j in range(nv - 1):
            f = bm.faces.new((vo[0][j + 1], vi[0][j + 1], vi[0][j], vo[0][j]))
            f.material_index = Z[wall_zone[2]]
            g = bm.faces.new((vo[nu - 1][j], vi[nu - 1][j], vi[nu - 1][j + 1], vo[nu - 1][j + 1]))
            g.material_index = Z[wall_zone[3]]
            faces += [f, g]
    rnd = rand if rand is not None else None
    if edge_mask:
        for i in range(nu):
            for j in range(nv):
                bu = (not periodic_u) and (i == 0 or i == nu - 1)
                bu1 = (not periodic_u) and (i == 1 or i == nu - 2)
                if j == 0 or j == nv - 1 or bu:
                    m = 0.0
                elif j == 1 or j == nv - 2 or bu1:
                    m = 0.35
                else:
                    m = 1.0
                set_mask(bm, [vo[i][j]], m, rnd)
                set_mask(bm, [vi[i][j]], 0.0, rnd)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces, vo, vi


def _grid_solid_simple(bm, S, N, thick, zone_fn, periodic_u, zone_in, wall_zone, rand, edge_mask, lip):
    """grid_solid with an inner surface of two rows (v = 0 and v = end), each end offset by the thickness."""
    nu, nv = S.shape[:2]
    So = S.copy()
    if lip:
        border = np.zeros((nu, nv), bool)
        border[:, 0] = border[:, -1] = True
        if not periodic_u:
            border[0, :] = border[-1, :] = True
        So[border] -= N[border] * lip
    I0 = S[:, 0] - N[:, 0] * thick
    I1 = S[:, -1] - N[:, -1] * thick
    vo = [[bm.verts.new(tuple(So[i, j])) for j in range(nv)] for i in range(nu)]
    vi0 = [bm.verts.new(tuple(I0[i])) for i in range(nu)]
    vi1 = [bm.verts.new(tuple(I1[i])) for i in range(nu)]
    faces = []
    iu = range(nu) if periodic_u else range(nu - 1)
    for i in iu:
        i2 = (i + 1) % nu
        for j in range(nv - 1):
            f = bm.faces.new((vo[i][j], vo[i2][j], vo[i2][j + 1], vo[i][j + 1]))
            f.material_index = Z[zone_fn(i, j) if callable(zone_fn) else zone_fn]
            faces.append(f)
        g = bm.faces.new((vi1[i], vi1[i2], vi0[i2], vi0[i]))
        g.material_index = Z[zone_in]
        f = bm.faces.new((vo[i][0], vi0[i], vi0[i2], vo[i2][0]))
        f.material_index = Z[wall_zone[0]]
        h = bm.faces.new((vo[i2][nv - 1], vi1[i2], vi1[i], vo[i][nv - 1]))
        h.material_index = Z[wall_zone[1]]
        faces += [g, f, h]
    if not periodic_u:
        for i, side in ((0, 2), (nu - 1, 3)):
            ring = [vi0[i]] + [vo[i][j] for j in range(nv)] + [vi1[i]]
            f = bm.faces.new(ring if side == 3 else list(reversed(ring)))
            f.material_index = Z[wall_zone[side]]
            faces.append(f)
    if edge_mask:
        for i in range(nu):
            for j in range(nv):
                bu = (not periodic_u) and (i == 0 or i == nu - 1)
                bu1 = (not periodic_u) and (i == 1 or i == nu - 2)
                m = 0.0 if (j == 0 or j == nv - 1 or bu) else (0.35 if (j == 1 or j == nv - 2 or bu1) else 1.0)
                set_mask(bm, [vo[i][j]], m, rand)
        set_mask(bm, vi0 + vi1, 0.0, rand)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces, vo, None


def loft_solid(bm, S, zone_fn, rand=None, cap_zone=None):
    """A closed solid lofted through the rings S[u, v] (u around, periodic; v along): quads between rings, the first
    and last rings closed with a centre fan (no hollow ends). Mask: end rings 0.3, the rest 1.0."""
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
            set_mask(bm, [vv[i][j]], 0.3 if j in (0, nv - 1) else 1.0, rand)
    set_mask(bm, [c0, c1], 0.3, rand)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def rim_rows(a, b, rim, n_mid):
    """Stations from a to b: the two edges, a thin rim band (width rim) inside each edge, n_mid stations between."""
    s = 1.0 if b >= a else -1.0
    mid = list(np.linspace(a + s * rim, b - s * rim, n_mid + 2)) if n_mid > 0 else [a + s * rim, b - s * rim]
    return [a] + mid + [b]


def offset_polygon(poly, d):
    """Offset a simple 2D polygon (CCW or CW, convex or mildly concave) inward by d (miter joins, clamped)."""
    P = np.asarray(poly, dtype=np.float64)
    n = len(P)
    area = 0.5 * sum(P[k, 0] * P[(k + 1) % n, 1] - P[(k + 1) % n, 0] * P[k, 1] for k in range(n))
    s = 1.0 if area > 0 else -1.0          # CCW: inward normal of edge (a->b) is (-dy, dx)
    out = []
    for k in range(n):
        a, b, c = P[k - 1], P[k], P[(k + 1) % n]
        e1, e2 = _norm(b - a), _norm(c - b)
        n1 = s * np.array([-e1[1], e1[0]])
        n2 = s * np.array([-e2[1], e2[0]])
        m = _norm(n1 + n2)
        cosh = max(0.35, float(m @ n1))
        out.append(b + m * d / cosh)
    return out


def prism(bm, poly, origin, A, B, Nd, back, front, chamfer, zones, depth_fn=None, taper=1.0, rand=None,
          chamfer_back=0.0):
    """Outline poly [(a, b)] in the plane origin + a*A + b*B, extruded along Nd from `back` to `front`
    (distances along Nd), with a chamfer of size `chamfer` around the front face (and chamfer_back around the back).
    depth_fn(i, a, b) -> (back_i, front_i) overrides the depths per outline point (tapering horns).
    taper scales the front outline about its centroid.
    zones: dict with keys front, side, chamfer, back (zone names); side, chamfer and chamfer_back may be callables
    (i) for the wall / chamfer facet i->i+1 (gold trim on chosen edges only).
    Returns the faces. Closed."""
    ensure_mask(bm)
    O, A, B, Nd = (np.asarray(v, dtype=np.float64) for v in (origin, A, B, Nd))
    P = np.asarray(poly, dtype=np.float64)
    n = len(P)
    cen = P.mean(0)
    Pf = cen + (P - cen) * taper
    In = np.asarray(offset_polygon(Pf, chamfer)) if chamfer > 0 else Pf
    Ib = np.asarray(offset_polygon(P, chamfer_back)) if chamfer_back > 0 else P

    def pt(ab, d):
        return O + A * ab[0] + B * ab[1] + Nd * d
    vb, vbi, vt, vti = [], [], [], []
    for i in range(n):
        bk, fr = depth_fn(i, P[i, 0], P[i, 1]) if depth_fn else (back, front)
        vbi.append(bm.verts.new(tuple(pt(Ib[i], bk))))
        vb.append(bm.verts.new(tuple(pt(P[i], bk + chamfer_back))))
        vt.append(bm.verts.new(tuple(pt(Pf[i], fr - chamfer))))
        vti.append(bm.verts.new(tuple(pt(In[i], fr))))
    faces = []
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((vb[i], vb[j], vt[j], vt[i]))
        zs = zones["side"](i) if callable(zones["side"]) else zones["side"]
        f.material_index = Z[zs]
        faces.append(f)
        g = bm.faces.new((vt[i], vt[j], vti[j], vti[i]))
        zc = zones["chamfer"](i) if callable(zones["chamfer"]) else zones["chamfer"]
        g.material_index = Z[zc]
        faces.append(g)
        if chamfer_back > 0:
            h = bm.faces.new((vbi[j], vbi[i], vb[i], vb[j]))
            zb = zones.get("chamfer_back", zones["chamfer"])
            h.material_index = Z[zb(i) if callable(zb) else zb]
            faces.append(h)
    ff = bm.faces.new(vti)
    ff.material_index = Z[zones["front"]]
    fb = bm.faces.new(list(reversed(vbi)) if chamfer_back > 0 else list(reversed(vb)))
    fb.material_index = Z[zones.get("back", zones["side"] if not callable(zones["side"]) else "iron")]
    faces += [ff, fb]
    set_mask(bm, vb + vbi, 0.0, rand)
    set_mask(bm, vt, 0.3, rand)
    set_mask(bm, vti, 1.0, rand)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def chipped(poly, chips):
    """Heavy chipped edges: insert flat-bottomed notches into a planar outline. chips: [(edge, t, width, depth)], the
    notch centred at fraction t of edge i -> i+1, `width` long (m), cut `depth` inward. Returns (outline, src) where
    src[k] = the source edge index of new edge k -> k+1 (so per-edge zones keep working)."""
    P = [np.asarray(p, dtype=np.float64) for p in poly]
    n = len(P)
    area = 0.5 * sum(P[k][0] * P[(k + 1) % n][1] - P[(k + 1) % n][0] * P[k][1] for k in range(n))
    s = 1.0 if area > 0 else -1.0
    by_edge = {}
    for e, t, w, d in chips:
        by_edge.setdefault(int(e), []).append((t, w, d))
    out, src = [], []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        out.append(a)
        src.append(i)
        L = float(np.linalg.norm(b - a))
        if L < 1e-6:
            continue
        e = (b - a) / L
        inward = s * np.array([-e[1], e[0]])
        for t, w, d in sorted(by_edge.get(i, [])):
            h = min(w / L, 0.45) / 2
            t0, t1 = max(t - h, 0.02), min(t + h, 0.98)
            q = (t1 - t0) * 0.25
            for tt, dd in ((t0, 0.0), (t0 + q, d), (t1 - q, d * 0.8), (t1, 0.0)):
                out.append(a + (b - a) * tt + inward * dd)
                src.append(i)
    return [tuple(p) for p in out], src


def frame_axes(d, up=(0.0, 0.0, 1.0)):
    """Orthonormal (d, u, v) with u as close to `up` as possible."""
    d = _norm(d)
    up = np.asarray(up, dtype=np.float64)
    v = np.cross(d, up)
    if np.linalg.norm(v) < 1e-6:
        v = np.cross(d, [1.0, 0.0, 0.0])
    v = _norm(v)
    u = _norm(np.cross(v, d))
    return d, u, v


def superellipse(theta, a, b, n):
    """Radius of the superellipse |x/a|^n + |y/b|^n = 1 at angle theta (x = cos, y = sin)."""
    c, s = np.abs(np.cos(theta)), np.abs(np.sin(theta))
    return 1.0 / ((c / a) ** n + (s / b) ** n + 1e-12) ** (1.0 / n)


def lobe(bm, centre, axis, side, ra, rb, rl, zone, sides=6, rand=None):
    """A squashed ellipsoid lobe (braid segment): half-length rl along axis, radii ra (along side) and rb."""
    ensure_mask(bm)
    c = np.asarray(centre, dtype=np.float64)
    d = _norm(axis)
    s1 = _norm(np.asarray(side, dtype=np.float64) - d * (np.asarray(side) @ d))
    s2 = np.cross(d, s1)
    rings = []
    for t, k in ((-0.62, 0.72), (0.0, 1.0), (0.62, 0.72)):
        rings.append([c + d * rl * t + (s1 * math.cos(a) * ra + s2 * math.sin(a) * rb) * k
                      for a in np.arange(sides) * 2 * math.pi / sides])
    vr = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    v0 = bm.verts.new(tuple(c - d * rl))
    v1 = bm.verts.new(tuple(c + d * rl))
    fs = []
    for A_, B_ in zip(vr[:-1], vr[1:]):
        for i in range(sides):
            j = (i + 1) % sides
            fs.append(bm.faces.new((A_[i], A_[j], B_[j], B_[i])))
    for i in range(sides):
        j = (i + 1) % sides
        fs.append(bm.faces.new((vr[0][j], vr[0][i], v0)))
        fs.append(bm.faces.new((vr[-1][i], vr[-1][j], v1)))
    tag(fs, zone)
    set_mask(bm, vr[0] + vr[2] + [v0, v1], 0.25, rand)
    set_mask(bm, vr[1], 1.0, rand)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def cylinder(bm, p0, p1, r0, r1, zone, sides=8, cap0=True, cap1=True, zone_cap=None, bevel=0.0, rand=None, up=(0, 0, 1)):
    """A closed cylinder / frustum from p0 to p1 (radii r0, r1), optional chamfer `bevel` at both ends."""
    ensure_mask(bm)
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    d, u, v = frame_axes(p1 - p0, up)
    L = float(np.linalg.norm(p1 - p0))
    angs = np.arange(sides) * 2 * math.pi / sides + math.pi / sides

    def ring(t, r):
        c = p0 + d * t
        return [c + (u * math.cos(a) + v * math.sin(a)) * r for a in angs]
    stations = []
    if bevel > 0:
        stations = [(0.0, r0 - bevel), (bevel, r0), (L - bevel, r1), (L, r1 - bevel)]
    else:
        stations = [(0.0, r0), (L, r1)]
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


def stud(bm, c, d, r, h, zone="gold", sides=6, rand=None):
    """A low dome (rivet) on direction d."""
    ensure_mask(bm)
    d = _norm(d)
    u = _norm(np.cross(d, [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0]))
    v = np.cross(d, u)
    c = np.asarray(c, dtype=np.float64)
    angs = np.arange(sides) * 2 * math.pi / sides
    vb = [bm.verts.new(tuple(c - d * 0.004 + (math.cos(a) * u + math.sin(a) * v) * r)) for a in angs]
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


def mirror_x(bm_src, bm_dst):
    """Append the x-mirrored copy of bm_src (closed geometry) to bm_dst, keeping zones and the mask layer."""
    lay_s = bm_src.verts.layers.float_color.get(G0.MASK_LAYER)
    lay_d = ensure_mask(bm_dst)
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
        g.smooth = f.smooth
        fs.append(g)
    return fs
