"""Procedural hard-surface helpers for the stage-2 hero parts (bmesh + numpy, no add-ons).

Every builder appends closed geometry to a bmesh and tags each new face with a paint zone (face material
index into ZONES), so the parts stay manifold and the texture painter (s2_paint.py) knows what each face is.
"""
import math

import bmesh
import numpy as np
from mathutils import Matrix, Vector

# paint zones = material slots, in this order, on every stage-2 object
ZONES = ["skin", "hair", "beard", "eye", "rock", "lava", "bronze", "plates", "leather", "cloth", "sash", "wraps", "linen", "teeth"]
Z = {n: i for i, n in enumerate(ZONES)}


def tag(faces, zone):
    zi = Z[zone]
    for f in faces:
        f.material_index = zi


def faces_of(verts):
    return list({f for v in verts for f in v.link_faces})


def ring_points(center, axis_u, axis_v, ru, rv, n, phase=0.0):
    """n points of an ellipse (ru along axis_u, rv along axis_v) around center."""
    c, u, v = (np.asarray(a, dtype=np.float64) for a in (center, axis_u, axis_v))
    t = phase + np.arange(n) * 2 * math.pi / n
    return c + np.outer(np.cos(t) * ru, u) + np.outer(np.sin(t) * rv, v)


def loft(bm, rings, zone, cap_start=True, cap_end=True, close_ring=True, cap_zone=None):
    """Quads between consecutive rings (lists of points with equal count); fan-free n-gon caps
    are poked into triangles. Returns all new faces."""
    vrings = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    faces = []
    n = len(rings[0])
    for a, b in zip(vrings[:-1], vrings[1:]):
        for i in range(n if close_ring else n - 1):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    tag(faces, zone)
    caps = []
    if cap_start:
        caps.append(bm.faces.new(list(reversed(vrings[0]))))
    if cap_end:
        caps.append(bm.faces.new(vrings[-1]))
    for f in caps:
        f.material_index = Z[cap_zone or zone]
        faces.append(f)
    return faces, vrings


def revolve_profile(bm, profile, center_fn, frame_fn, n, zone, ey=1.0, ez=1.0, phase=0.0):
    """Closed profile [(x, r), ...] revolved around the local x axis: frame_fn(x) -> (C, U, V) gives the
    centre and the two cross-section axes at that x. Produces a closed torus-like tube (ring, band);
    n = 6 with phase 0 gives a hexagonal band with flat faces on top and bottom."""
    rings = []
    for (x, r) in profile:
        C, U, V = frame_fn(x)
        t = phase + np.arange(n) * 2 * math.pi / n
        rings.append(C + np.outer(np.cos(t) * r * ey, U) + np.outer(np.sin(t) * r * ez, V))
    vrings = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    faces = []
    m = len(vrings)
    for k in range(m):
        a, b = vrings[k], vrings[(k + 1) % m]
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    tag(faces, zone)
    return faces


def box(bm, M, half, zone, bevel=0.0, taper_end=1.0, end_zone=None, start_zone=None):
    """Box with half extents `half` in the local frame M (4x4: columns = local axes, translation = centre).
    taper_end scales the +x end face in local y/z. bevel chamfers every edge (one segment).
    start_zone / end_zone retag the -x / +x end faces (e.g. glowing joint faces)."""
    hx, hy, hz = half
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                k = taper_end if sx > 0 else 1.0
                pts.append(Vector((sx * hx, sy * hy * k, sz * hz * k)))
    vs = [bm.verts.new(M @ p) for p in pts]
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    fs = [bm.faces.new([vs[i] for i in q]) for q in idx]
    tag(fs, zone)
    if start_zone:
        fs[0].material_index = Z[start_zone]
    if end_zone:
        fs[1].material_index = Z[end_zone]
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    if bevel > 0:
        edges = list({e for f in fs for e in f.edges})
        res = bmesh.ops.bevel(bm, geom=edges + vs, offset=bevel, offset_type="OFFSET", segments=1, profile=0.5,
                              affect="EDGES", clamp_overlap=True)
        for f in res["faces"]:
            f.material_index = Z[zone]
        fs = [f for f in faces_of(set(v for f in fs if f.is_valid for v in f.verts))]
    return fs


def frame_from(x_axis, up_hint=(0, 0, 1)):
    x = Vector(x_axis).normalized()
    up = Vector(up_hint)
    y = up.cross(x)
    if y.length < 1e-6:
        y = Vector((0, 1, 0)).cross(x)
    y.normalize()
    z = x.cross(y).normalized()
    return x, y, z


def matrix(origin, x, y, z):
    M = Matrix.Identity(4)
    for i, a in enumerate((x, y, z)):
        M[0][i], M[1][i], M[2][i] = a
    M[0][3], M[1][3], M[2][3] = origin
    return M


def gear(bm, center, axis, r_out, r_in, teeth, thick, zone):
    """Toothed disk (cog) with its face normal along axis."""
    a = Vector(axis).normalized()
    u = a.orthogonal().normalized()
    v = a.cross(u).normalized()
    n = teeth * 2
    ring = []
    for i in range(n * 2):
        t = i * math.pi / n
        r = r_out if (i // 2) % 2 == 0 else r_in
        ring.append(np.array(center) + (math.cos(t) * u + math.sin(t) * v) * r)
    back = [p - np.array(a) * thick for p in ring]
    faces, _ = loft(bm, [back, ring], zone)
    return faces


def voronoi_cells_periodic(seeds, period_s, x_range):
    """Voronoi cells of 2D seeds (s, x), periodic in s, clipped to x_range. Returns a list of polygons
    (list of (s, x)) in the same order as seeds. Brute-force half-plane clipping (n is small)."""
    s = np.asarray(seeds, dtype=np.float64)
    ext = np.concatenate([s, s + [period_s, 0], s - [period_s, 0]])
    cells = []
    x0, x1 = x_range
    for i, p in enumerate(s):
        poly = [(p[0] - period_s / 2, x0), (p[0] + period_s / 2, x0), (p[0] + period_s / 2, x1), (p[0] - period_s / 2, x1)]
        for j, q in enumerate(ext):
            if j == i:
                continue
            d = q - p
            dd = d @ d
            if dd < 1e-12 or dd > (period_s * 0.6) ** 2 + (x1 - x0) ** 2:
                continue
            m = (p + q) / 2
            new = []
            L = len(poly)
            for k in range(L):
                A, B = np.array(poly[k]), np.array(poly[(k + 1) % L])
                ia, ib = (A - m) @ d <= 0, (B - m) @ d <= 0
                if ia:
                    new.append(tuple(A))
                if ia != ib:
                    t = ((m - A) @ d) / ((B - A) @ d)
                    new.append(tuple(A + (B - A) * t))
            poly = new
            if len(poly) < 3:
                break
        cells.append(poly)
    return cells


def inset_polygon(poly, amount):
    """Shrink a convex polygon toward its centroid so that edges move `amount` inward (approx.)."""
    P = np.asarray(poly, dtype=np.float64)
    c = P.mean(0)
    out = []
    n = len(P)
    for k in range(n):
        a, b, cc = P[k - 1], P[k], P[(k + 1) % n]
        e1 = b - a
        e2 = cc - b
        n1 = np.array([e1[1], -e1[0]])
        n2 = np.array([e2[1], -e2[0]])
        n1 /= np.linalg.norm(n1) + 1e-12
        n2 /= np.linalg.norm(n2) + 1e-12
        if (c - b) @ n1 < 0:
            n1, n2 = -n1, -n2
        bis = n1 + n2
        bis /= np.linalg.norm(bis) + 1e-12
        cosh = max(0.3, bis @ n1)
        out.append(b + bis * amount / cosh)
    return out


MASK_LAYER = "gf_mask"


def ensure_mask(bm):
    """Create the gf_mask layer BEFORE making vertices you keep references to (adding a layer invalidates them)."""
    return bm.verts.layers.float_color.get(MASK_LAYER) or bm.verts.layers.float_color.new(MASK_LAYER)


def set_mask(bm, verts, value, rand=None):
    """Per-vertex paint mask (float colour attribute gf_mask): R = 0 plate outline / edge .. 1 plate centre /
    ridge (the painter darkens outlines and lifts ridges with it), G = a per-piece random value (per-plate
    tone variation; = R when not given), A = 1 once set."""
    lay = bm.verts.layers.float_color.get(MASK_LAYER) or bm.verts.layers.float_color.new(MASK_LAYER)
    g = value if rand is None else rand
    for v in verts:
        v[lay] = (value, g, value, 1.0)


def prism_plate(bm, base_pts, top_pts, top_inner_pts, zone_top, zone_side):
    """A plate: bottom polygon base_pts, side walls up to top_pts, a chamfer ring from top_pts to
    top_inner_pts and a flat top. All lists share the vertex count and winding (counter-clockwise
    seen from outside)."""
    n = len(base_pts)
    ensure_mask(bm)
    B = [bm.verts.new(tuple(p)) for p in base_pts]
    T = [bm.verts.new(tuple(p)) for p in top_pts]
    I = [bm.verts.new(tuple(p)) for p in top_inner_pts]
    faces = []
    side = []
    cham = []
    for i in range(n):
        j = (i + 1) % n
        side.append(bm.faces.new((B[i], B[j], T[j], T[i])))
        cham.append(bm.faces.new((T[i], T[j], I[j], I[i])))
    top = bm.faces.new(I)
    bot = bm.faces.new(list(reversed(B)))
    tag(side, zone_side)
    tag(cham + [top], zone_top)
    bot.material_index = Z[zone_side]
    faces = side + cham + [top, bot]
    set_mask(bm, B, 0.0)
    set_mask(bm, T, 0.25)
    set_mask(bm, I, 1.0)
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    return faces


def rock_chunk(bm, pts, nrm, hs, rng, cfg, zone="rock", plate_rand=None, base_sink=0.004):
    """A stylised hand-sculpted rock plate on a surface: base polygon pts (counter-clockwise seen from
    outside) with outward normals nrm and per-vertex heights hs. Side walls rise to an irregular shoulder
    ring, a bevel runs in to a top ring and the top closes in a fan to an off-centre peak, so every plate
    is a few big facets (flat-shaded by the sharp-edge angle). Closed; gf_mask R: 0 base .. 1 peak."""
    ensure_mask(bm)
    P = [np.asarray(p, dtype=np.float64) for p in pts]
    N = [np.asarray(n, dtype=np.float64) for n in nrm]
    n = len(P)
    c = np.mean(P, axis=0)
    nc = np.mean(N, axis=0)
    nc /= np.linalg.norm(nc) + 1e-12
    hm = float(np.mean(hs))
    edge = float(np.mean([np.linalg.norm(P[i] - P[(i + 1) % n]) for i in range(n)]))
    B, Sh, T = [], [], []
    for i in range(n):
        toc = c - P[i]
        dist = np.linalg.norm(toc) + 1e-12
        B.append(P[i] - N[i] * base_sink)
        sh_in = min(cfg["shoulder_inset"], 0.3 * dist) / dist
        Sh.append(P[i] + toc * sh_in + N[i] * hs[i] * rng.uniform(*cfg["shoulder_h"]))
        T.append(P[i] + toc * rng.uniform(*cfg["top_inset"]) + N[i] * hs[i] * rng.uniform(*cfg["top_h"]))
    tang = rng.uniform(-1, 1) * (P[0] - c) + rng.uniform(-1, 1) * (P[n // 2] - c)
    tang = tang - nc * (tang @ nc)
    peak = c + nc * hm * rng.uniform(*cfg["peak_h"]) + tang / (np.linalg.norm(tang) + 1e-9) * cfg["peak_offset"] * edge * 0.5
    vB = [bm.verts.new(tuple(p)) for p in B]
    vS = [bm.verts.new(tuple(p)) for p in Sh]
    vT = [bm.verts.new(tuple(p)) for p in T]
    vP = bm.verts.new(tuple(peak))
    fs = []
    for i in range(n):
        j = (i + 1) % n
        fs.append(bm.faces.new((vB[i], vB[j], vS[j], vS[i])))
        fs.append(bm.faces.new((vS[i], vS[j], vT[j], vT[i])))
        fs.append(bm.faces.new((vT[i], vT[j], vP)))
    fs.append(bm.faces.new(list(reversed(vB))))
    tag(fs, zone)
    set_mask(bm, vB, 0.0, plate_rand)
    set_mask(bm, vS, 0.3, plate_rand)
    set_mask(bm, vT, 0.75, plate_rand)
    set_mask(bm, [vP], 1.0, plate_rand)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def rock_block(bm, center, xdir, zdir, lx, ly, lz, rng, zone="rock", facets=None):
    """A chunky faceted rock block (knuckle): an irregular octagon base on the plane (center, zdir) with
    extents lx (along xdir) x ly, closed by rock_chunk with height lz."""
    x = np.asarray(xdir, dtype=np.float64)
    x /= np.linalg.norm(x)
    z = np.asarray(zdir, dtype=np.float64)
    z /= np.linalg.norm(z)
    y = np.cross(z, x)
    pts = []
    for k in range(8):
        a = (k + 0.5) * math.pi / 4
        r = rng.uniform(0.88, 1.0)
        pts.append(np.asarray(center, dtype=np.float64) + x * math.cos(a) * lx / 2 * r + y * math.sin(a) * ly / 2 * r)
    cfg = facets or {"shoulder_inset": 0.008, "shoulder_h": [0.5, 0.7], "top_inset": [0.3, 0.42], "top_h": [0.88, 1.0],
                     "peak_h": [1.02, 1.12], "peak_offset": 0.3}
    return rock_chunk(bm, pts, [z] * 8, np.full(8, lz), rng, cfg, zone=zone, plate_rand=rng.random(), base_sink=0.01)


def rock_segment(bm, pos, d, up, L, wid, hgt, rng, zone="rock", joint_start=False, joint_end=False, taper=0.92,
                 jitter=0.1, sides=6):
    """A faceted rock finger segment: a hexagonal prism (flattened underside, a ridge on top) from pos along
    d, length L, irregular per-vertex radii, inset ends. Joint end faces are lava (they glow between the
    segments); a free end closes in a blunt rock tip."""
    ensure_mask(bm)
    d = Vector(d).normalized()
    xa, ya, za = frame_from(d, up_hint=tuple(up))
    p0 = Vector(tuple(pos))
    angs = [math.pi / 2 + k * 2 * math.pi / sides for k in range(sides)]
    jit = [1.0 + rng.uniform(-jitter, jitter) for _ in range(sides)]

    def ring(sv, scale, ridge=0.0):
        c = p0 + d * sv
        out = []
        for k, a in enumerate(angs):
            ca, sa = math.cos(a), math.sin(a)
            r = scale * jit[k] * (1.0 + (ridge if k == 0 else 0.0))
            zz = sa * hgt / 2 * r
            if sa < -0.3:
                zz *= 0.8                         # flatter underside
            out.append(c + ya * (ca * wid / 2 * r) + za * zz)
        return out
    rings = (ring(0.0, 0.8), ring(L * 0.14, 1.0, 0.1), ring(L * 0.78, taper, 0.06), ring(L, 0.78 if joint_end else 0.62))
    vr = [[bm.verts.new(tuple(p)) for p in r] for r in rings]
    fs = []
    for a, b in zip(vr[:-1], vr[1:]):
        for i in range(sides):
            j = (i + 1) % sides
            fs.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    tag(fs, zone)
    cap0 = bm.faces.new(list(reversed(vr[0])))
    cap0.material_index = Z["lava" if joint_start else zone]
    if joint_end:
        cap1 = bm.faces.new(vr[3])
        cap1.material_index = Z["lava"]
        caps = [cap1]
    else:
        vt = bm.verts.new(tuple(p0 + d * (L + hgt * 0.12)))
        caps = [bm.faces.new((vr[3][i], vr[3][(i + 1) % sides], vt)) for i in range(sides)]
        tag(caps, zone)
        set_mask(bm, [vt], 0.9)
    set_mask(bm, vr[0] + vr[3], 0.25)
    set_mask(bm, vr[1] + vr[2], 0.8)
    all_f = fs + [cap0] + caps
    bmesh.ops.recalc_face_normals(bm, faces=all_f)
    return all_f


def stud(bm, c, d, r, h, zone="bronze", sides=6):
    """A low bronze dome (rivet) on direction d."""
    ensure_mask(bm)
    d = np.asarray(d, dtype=np.float64)
    d /= np.linalg.norm(d)
    u = np.cross(d, [0.0, 0.0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
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
    set_mask(bm, vb, 0.2)
    set_mask(bm, vm + [vt], 0.9)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def lock(bm, root, nrm, d0, bend, L, w, t, rng, zone, sides=6):
    """A chunky stylised hair / beard clump: a tapered lens-section loft from root (sunk into the shell)
    along d0, bending toward bend, closing in a point. gf_mask R rises from root (0.3) to tip (1)."""
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
    for A, B in zip(vr[:-1], vr[1:]):
        for i in range(sides):
            j = (i + 1) % sides
            fs.append(bm.faces.new((A[i], A[j], B[j], B[i])))
    for i in range(sides):
        fs.append(bm.faces.new((vr[-1][i], vr[-1][(i + 1) % sides], vt)))
    fs.append(bm.faces.new(list(reversed(vr[0]))))
    tag(fs, zone)
    for k, m in enumerate((0.3, 0.55, 0.8)):
        set_mask(bm, vr[k], m)
    set_mask(bm, [vt], 1.0)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs
