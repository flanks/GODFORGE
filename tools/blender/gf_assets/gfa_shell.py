"""gf_assets hollow-shell modelling: THICK PATCHES from parametric surfaces (bmesh).

A thick patch is a closed plate built from a surface function S(u, v): the outer skin, an inner skin offset
along the surface normal by the plate thickness, and rim faces wherever the grid ends, so holes, broken
edges and jagged tears all get a real plate thickness. The inner skin comes back as its OWN bmesh, so an
Assembly can give it a different paint zone: hollow armour (Fallen Godworks), eggshells, carapaces, open
greaves and helmets whose dark inside shows through the gaps.

    outer, inner = thick_patch(rev_fn([(0.36, 1.58), (0.5, 1.82), (0.22, 2.08)], -90 + 20, 270 - 20),
                               nu=16, nv=6, thickness=0.035, keep=lambda i, j: not (i == 3 and j == 2))
    asm.add(outer, "bronze", bone="spine_03")
    asm.add(inner, "void", bone="spine_03")

Surface helpers: rev_fn (surface of revolution of an (r, z) profile over an angle range, optionally
elliptical and oriented by a matrix), cap_fn (spherical / elliptical dome), and keep-mask helpers for
torn edges (jagged_keep) and bites (bite_keep).

Added for the forge_warden elite (GODFORGE gf_assets, enemy stage). Pure bmesh + mathutils, no bpy
operators, so it runs in any Blender 4.4+ build.
"""
import math

import bmesh
from mathutils import Matrix, Vector


# ---- surface functions ---------------------------------------------------------------------------

def _interp_profile(profile, smooth):
    """Return f(v) -> (r, z) along the polyline profile by arc length (v in 0..1). smooth: Catmull-Rom
    subdivision count per segment (0 = linear)."""
    pts = [Vector((r, z)) for r, z in profile]
    if smooth and len(pts) > 2:
        dense = []
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[i - 1] if i > 0 else pts[i] * 2 - pts[i + 1]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < n else pts[i + 1] * 2 - pts[i]
            for s in range(smooth):
                t = s / smooth
                t2, t3 = t * t, t * t * t
                dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
        dense.append(pts[-1])
        pts = dense
    L = [0.0]
    for a, b in zip(pts[:-1], pts[1:]):
        L.append(L[-1] + (b - a).length)
    tot = L[-1] or 1.0

    def f(v):
        s = min(max(v, 0.0), 1.0) * tot
        for k in range(len(L) - 1):
            if s <= L[k + 1] or k == len(L) - 2:
                seg = (L[k + 1] - L[k]) or 1.0
                t = (s - L[k]) / seg
                p = pts[k].lerp(pts[k + 1], min(max(t, 0.0), 1.0))
                return p.x, p.y
        return pts[-1].x, pts[-1].y
    return f


def rev_fn(profile, theta0=0.0, theta1=360.0, sx=1.0, sy=1.0, matrix=None, smooth=0, r_fn=None):
    """Surface of revolution about local +Z: profile = [(radius, z), ...] (v runs along it), u runs over
    the angle theta0 -> theta1 (degrees; 0 = +X, -90 = -Y = a creature's front). sx / sy squash the
    section into an ellipse; r_fn(u, v) -> multiplier on the radius (bulges, flutes); matrix places the
    result. Returns fn(u, v) -> Vector.
    Orientation: with theta increasing and the profile running UP (+z), dS/du x dS/dv points away from
    the axis (the outer skin is fn itself). A profile running down (hanging skirts) needs
    thick_patch(..., flip=True)."""
    prof = _interp_profile(profile, smooth)
    M = Matrix(matrix) if matrix is not None else Matrix.Identity(4)

    def fn(u, v):
        r, z = prof(v)
        if r_fn is not None:
            r *= r_fn(u, v)
        th = math.radians(theta0 + (theta1 - theta0) * u)
        return M @ Vector((r * sx * math.cos(th), r * sy * math.sin(th), z))
    return fn


def cap_fn(radius, depth, theta0=0.0, theta1=360.0, v0=0.0, v1=1.0, sx=1.0, sy=1.0, matrix=None):
    """Elliptical dome about local +Z: radius (base), depth (height of the dome), top at z = depth, base
    ring at z = 0. v runs from the base rim (v = 0) up to the top (v = 1), so dS/du x dS/dv points out of
    the dome; the polar angle spans v1 (rim, 1 = the equator) .. v0 (top, 0 = the pole: > 0 leaves a hole)."""
    M = Matrix(matrix) if matrix is not None else Matrix.Identity(4)

    def fn(u, v):
        a = (v1 - (v1 - v0) * v) * math.pi / 2
        th = math.radians(theta0 + (theta1 - theta0) * u)
        r = radius * math.sin(a)
        z = depth * math.cos(a)
        return M @ Vector((r * sx * math.cos(th), r * sy * math.sin(th), z))
    return fn


def grid_fn(width, height, bend_x=0.0, bend_y=0.0, matrix=None, taper=1.0):
    """Curved rectangular plate in the local XY plane (normal +Z), centred on the origin. bend_x / bend_y:
    sagitta (m) of a cylindrical bend across X / Y (positive bows toward +Z). taper scales the width at
    v = 1 (the +Y end)."""
    M = Matrix(matrix) if matrix is not None else Matrix.Identity(4)

    def fn(u, v):
        w = width * (1.0 + (taper - 1.0) * v)
        x = (u - 0.5) * w
        y = (v - 0.5) * height
        z = bend_x * (1 - (2 * u - 1) ** 2) + bend_y * (1 - (2 * v - 1) ** 2)
        return M @ Vector((x, y, z))
    return fn


# ---- keep masks (holes, torn edges) ---------------------------------------------------------------

def _h(i, j, seed):
    x = (i * 73856093) ^ (j * 19349663) ^ (seed * 83492791)
    x &= 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    x = ((x ^ (x >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    return ((x ^ (x >> 16)) & 0xFFFF) / 65535.0


def jagged_keep(nu, nv, edges=("v1",), depth=2, seed=0, prob=0.55, base=None):
    """Keep-mask that tears the listed grid borders ('u0', 'u1', 'v0', 'v1') into a jagged edge: each
    border column / row loses 0..depth cells at random (a broken plate edge). base: another keep to AND."""
    cut = {}
    salt = {"u0": 11, "u1": 23, "v0": 37, "v1": 53}      # deterministic (str hash() is salted per process)
    for e in edges:
        n = nv if e in ("u0", "u1") else nu
        cut[e] = [sum(1 for k in range(depth) if _h(t, k, seed + salt[e]) < prob) for t in range(n)]

    def keep(i, j):
        if base is not None and not base(i, j):
            return False
        for e, c in cut.items():
            if e == "v1" and j >= nv - c[i]:
                return False
            if e == "v0" and j < c[i]:
                return False
            if e == "u1" and i >= nu - c[j]:
                return False
            if e == "u0" and i < c[j]:
                return False
        return True
    return keep


def bite_keep(nu, nv, u_center, u_half, depth_cells, seed=0, jag=1, base=None, from_edge="v1"):
    """Keep-mask with a jagged bite taken out of one border (from_edge 'v1' / 'v0'): cells within u_half
    (in cells) of u_center lose up to depth_cells rows, tapering to the bite's ends, +-jag cells noise."""
    def keep(i, j):
        if base is not None and not base(i, j):
            return False
        du = min(abs(i - u_center), abs(i - u_center + nu), abs(i - u_center - nu))
        if du > u_half:
            return True
        d = depth_cells * (1 - (du / (u_half + 1e-6)) ** 2)
        d += (_h(i, 7, seed) - 0.5) * 2 * jag
        k = j if from_edge == "v0" else nv - 1 - j
        return k >= d
    return keep


# ---- the thick patch --------------------------------------------------------------------------------------

def thick_patch(fn, nu, nv, thickness, keep=None, wrap_u=False, eps=1e-4, flip=False, weld_dist=1e-5,
                inner=True):
    """Closed plate from the surface fn(u, v) (u, v in 0..1) sampled on an nu x nv cell grid.
    thickness: metres (scalar or fn(u, v)); the inner skin is offset along -normal, where the normal is
    dS/du x dS/dv (flip=True reverses it: use it when the inside ends up outside). keep(i, j) -> bool
    drops cells (holes, torn borders); every exposed cell edge gets a rim quad, so the plate stays closed.
    wrap_u: u is periodic (a full ring: no rim at u = 0/1). Returns (outer_bm, inner_bm): outer skin +
    rims, and the inner skin (the hollow side) as a separate bmesh (None when inner=False: then the
    inner skin is merged into outer_bm)."""
    nu_pts = nu if wrap_u else nu + 1
    nv_pts = nv + 1
    us = [i / nu for i in range(nu_pts)]
    vs = [j / nv for j in range(nv_pts)]
    P = [[Vector(fn(u, v)) for v in vs] for u in us]

    def normal(i, j):
        u, v = us[i], vs[j]
        u0, u1 = (u - eps, u + eps) if wrap_u else (max(0.0, u - eps), min(1.0, u + eps))
        v0, v1 = max(0.0, v - eps), min(1.0, v + eps)
        du = Vector(fn(u1, v)) - Vector(fn(u0, v))
        dv = Vector(fn(u, v1)) - Vector(fn(u, v0))
        n = du.cross(dv)
        if n.length < 1e-12:            # pole (a dome's apex): point away from the ring next to it
            acc = Vector((0, 0, 0))
            jj = 1 if j == 0 else nv_pts - 2
            for ii in range(nu_pts):
                acc += Vector(fn(us[ii], vs[jj])) - P[i][j]
            n = -acc
            if n.length < 1e-12:
                n = Vector((0, 0, 1))
            return n.normalized()          # already outward: flip does not apply at a pole
        n.normalize()
        return -n if flip else n

    def thick(i, j):
        return thickness(us[i], vs[j]) if callable(thickness) else thickness

    Q = [[P[i][j] - normal(i, j) * thick(i, j) for j in range(nv_pts)] for i in range(nu_pts)]

    def kept(i, j):
        if j < 0 or j >= nv:
            return False
        if wrap_u:
            i %= nu
        elif i < 0 or i >= nu:
            return False
        return True if keep is None else bool(keep(i, j))

    bm = bmesh.new()
    lay = bm.faces.layers.int.new("gfa_inner")
    vo, vi = {}, {}

    def V(store, grid, i, j):
        i = i % nu_pts if wrap_u else i
        k = (i, j)
        if k not in store:
            store[k] = bm.verts.new(grid[i][j])
        return store[k]

    def face(vs_, inner_flag):
        try:
            f = bm.faces.new(vs_)
        except ValueError:
            return None
        f[lay] = 1 if inner_flag else 0
        return f

    for i in range(nu):
        for j in range(nv):
            if not kept(i, j):
                continue
            i1 = i + 1
            a, b, c, d = V(vo, P, i, j), V(vo, P, i1, j), V(vo, P, i1, j + 1), V(vo, P, i, j + 1)
            face((a, b, c, d), False)
            ai, bi, ci, di = V(vi, Q, i, j), V(vi, Q, i1, j), V(vi, Q, i1, j + 1), V(vi, Q, i, j + 1)
            face((ai, di, ci, bi), True)
            # rims on exposed edges (winding: outer edge forward, inner edge back)
            if not kept(i, j - 1):
                face((b, a, ai, bi), False)
            if not kept(i, j + 1):
                face((d, c, ci, di), False)
            if not kept(i - 1, j):
                face((a, d, di, ai), False)
            if not kept(i + 1, j):
                face((c, b, bi, ci), False)
    if weld_dist > 0:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=weld_dist)
    # degenerate faces (poles) collapse to triangles or vanish
    bad = [f for f in bm.faces if f.calc_area() < 1e-12]
    if bad:
        bmesh.ops.delete(bm, geom=bad, context="FACES_ONLY")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    if not inner:
        bm.faces.layers.int.remove(lay)
        return bm, None
    ib = bm.copy()
    li = ib.faces.layers.int.get("gfa_inner")
    bmesh.ops.delete(ib, geom=[f for f in ib.faces if f[li] == 0], context="FACES")
    ob = bm
    lo = ob.faces.layers.int.get("gfa_inner")
    bmesh.ops.delete(ob, geom=[f for f in ob.faces if f[lo] == 1], context="FACES")
    for b_ in (ob, ib):
        b_.faces.layers.int.remove(b_.faces.layers.int.get("gfa_inner"))
    return ob, ib


def split_by(bm, pred):
    """Split a bmesh into (faces where pred(face) is True, the rest) as two new bmeshes."""
    a = bm.copy()
    b = bm.copy()
    bmesh.ops.delete(a, geom=[f for f in a.faces if not pred(f)], context="FACES")
    bmesh.ops.delete(b, geom=[f for f in b.faces if pred(f)], context="FACES")
    return a, b
