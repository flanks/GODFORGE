"""gf_assets modelling helpers (bmesh): chunky stylised game parts built from code.

Every primitive returns a NEW bmesh.types.BMesh in its own local frame (documented per function).
Move it with xform(), then hand it to an Assembly, which merges all parts into ONE mesh object with
one material slot per paint zone, a per-face part id (`gfa_part`, so the painter can give each plate
its own value) and, for rigged assets, one vertex group per bone (rigid skinning, gfa_rig.py).

Shape language (docs/art/WEAPONS.md, ENEMIES.md): big readable masses, chunky 1-2 segment bevels
(bevel width ~4-8 % of the part's smallest dimension), exaggerated tapers, few but bold details.
Tri cost guide: box with 1-segment bevel = 44 tris, 2 segments = 108; 12-sided capped cylinder = 44;
stud (6 sides) = 18; spike (4 sides) = 6.

Line generators (crack_lines, rune_glyph, rune_band, sunburst) return 2D polylines. Use them as
painted decals (gfa_paint Decal) or as raised inlay geometry (ribbon()).

Parts of this module adapt GODFORGE tools/blender/gf_hero/s2_geom.py ideas (mask/zone layers) and
Ashen Covenant tools/blender/ac_env_props (bmesh prop kits).
"""
import math
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Quaternion, Vector, noise

AXES = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1)),
        "-X": Vector((-1, 0, 0)), "-Y": Vector((0, -1, 0)), "-Z": Vector((0, 0, -1))}


# ---- transforms -------------------------------------------------------------------------------

def trs(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    """4x4 from location, Euler XYZ degrees (or a Quaternion / Matrix) and scale (scalar or 3)."""
    if isinstance(rot, Quaternion):
        R = rot.to_matrix().to_4x4()
    elif isinstance(rot, Matrix):
        R = rot.to_4x4()
    else:
        R = Euler([math.radians(a) for a in rot], "XYZ").to_matrix().to_4x4()
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    S = Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    return Matrix.Translation(Vector(loc)) @ R @ S


def xform(bm, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), matrix=None):
    """Transform all verts in place (matrix applied after loc/rot/scale when both given). Returns bm.
    Negative scales flip the winding, so normals are recalculated."""
    M = trs(loc, rot, scale)
    if matrix is not None:
        M = Matrix(matrix) @ M
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts[:])
    if M.to_3x3().determinant() < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return bm


def aim_matrix(direction, up=(0, 0, 1), from_axis="Z"):
    """Rotation turning local `from_axis` onto `direction` (roll chosen so local up follows `up`)."""
    d = Vector(direction).normalized()
    track = {"Z": "Z", "Y": "Y", "X": "X", "-Z": "-Z", "-Y": "-Y", "-X": "-X"}[from_axis]
    upax = "Y" if track in ("Z", "-Z", "X", "-X") else "Z"
    q = d.to_track_quat(track, upax)
    return q.to_matrix().to_4x4()


def orient(origin, z_dir, x_hint=(1, 0, 0)):
    """4x4 placing a part built along +Z: local Z -> z_dir, local X as close to x_hint as possible
    (e.g. a flattened spike's wide side), origin -> origin."""
    z = Vector(z_dir).normalized()
    x = Vector(x_hint) - z * Vector(x_hint).dot(z)
    if x.length < 1e-6:
        x = Vector((0, 1, 0)) - z * z.y
    x.normalize()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def copy(bm):
    return bm.copy()


def merge(*bms):
    """Concatenate several bmeshes into a new one (no welding)."""
    out = bmesh.new()
    for b in bms:
        _append_raw(out, b)
    return out


def _append_raw(dst, src):
    vmap = {}
    for v in src.verts:
        vmap[v] = dst.verts.new(v.co)
    for f in src.faces:
        try:
            nf = dst.faces.new([vmap[v] for v in f.verts])
            nf.smooth = f.smooth
            nf.material_index = f.material_index
        except ValueError:
            pass
    dst.edges.ensure_lookup_table()
    for e in src.edges:
        if not e.smooth:
            ne = dst.edges.get([vmap[e.verts[0]], vmap[e.verts[1]]])
            if ne is not None:
                ne.smooth = False
    return vmap


def recalc(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def weld(bm, dist=1e-5):
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    return bm


# ---- primitives -------------------------------------------------------------------------------

def _bevel_edges(bm, edges, width, segments, profile=0.5):
    if width <= 0 or not edges:
        return bm
    bmesh.ops.bevel(bm, geom=list(edges), offset=width, offset_type="OFFSET", segments=segments,
                    profile=profile, affect="EDGES", clamp_overlap=True, harden_normals=False)
    return bm


def box(size, bevel=0.0, segments=1, taper=(1.0, 1.0), shear=(0.0, 0.0), profile=0.5):
    """Box centred on the origin, `size` = (x, y, z) metres. taper = (x, y) scale of the TOP (+Z) face
    (wedges, trapezoids); shear = (x, y) offset of the top face in metres. bevel = chamfer width (m)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
        if v.co.z > 0:
            v.co.x = v.co.x * taper[0] + shear[0]
            v.co.y = v.co.y * taper[1] + shear[1]
    _bevel_edges(bm, bm.edges[:], bevel, segments, profile)
    return recalc(bm)


def loft_rect(sections, bevel=0.0, segments=1, cap=True):
    """Box lofted through rectangular sections along +Y: sections = [(y, width_x, height_z, cx, cz), ...].
    Stocks, blades, tapered limbs, horns with a square section, armour plates. Returns the bmesh."""
    bm = bmesh.new()
    rings = []
    for y, w, h, cx, cz in sections:
        rings.append([bm.verts.new((cx - w / 2, y, cz - h / 2)), bm.verts.new((cx + w / 2, y, cz - h / 2)),
                      bm.verts.new((cx + w / 2, y, cz + h / 2)), bm.verts.new((cx - w / 2, y, cz + h / 2))])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    if cap:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    recalc(bm)
    if bevel > 0:
        sharp = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0) > math.radians(50)]
        _bevel_edges(bm, sharp, bevel, segments)
    return recalc(bm)


def cylinder(radius, depth, sides=12, radius_top=None, bevel=0.0, segments=1, cap=True, axis="Z"):
    """Capped cylinder / cone frustum centred on the origin along `axis` (default Z)."""
    bm = bmesh.new()
    r2 = radius if radius_top is None else radius_top
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=sides, radius1=radius,
                          radius2=max(r2, 1e-5), depth=depth)
    if r2 <= 1e-5:
        weld(bm, 1e-4)
    if bevel > 0 and cap:
        h = depth / 2
        rim = [e for e in bm.edges if all(abs(abs(v.co.z) - h) < 1e-5 for v in e.verts)]
        _bevel_edges(bm, rim, bevel, segments)
    _orient_axis(bm, axis)
    return recalc(bm)


def _orient_axis(bm, axis):
    if axis == "Z":
        return
    rot = {"X": Euler((0, math.radians(90), 0)), "Y": Euler((math.radians(-90), 0, 0)),
           "-X": Euler((0, math.radians(-90), 0)), "-Y": Euler((math.radians(90), 0, 0)),
           "-Z": Euler((math.radians(180), 0, 0))}[axis]
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=rot.to_matrix(), verts=bm.verts[:])


def sphere(radius, segments=12, rings=8, scale=(1, 1, 1)):
    """UV sphere (squash it with `scale` for pods, eggs, domes)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    return recalc(bm)


def ico(radius, subdivisions=1, scale=(1, 1, 1)):
    """Icosphere: faceted rocks, shards, orbs (subdivisions 1 = 80 tris)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
    return recalc(bm)


def lathe(profile, sides=16, angle=360.0, axis="Z", cap=True, start_angle=0.0):
    """Surface of revolution (the screw/spin tool). profile = [(radius, height), ...] from bottom to top
    (a radius of 0 closes the end to a point). Revolved about `axis`; partial angles give arcs."""
    bm = bmesh.new()
    a0 = math.radians(start_angle)
    verts = [bm.verts.new((r * math.cos(a0), r * math.sin(a0), z)) for r, z in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    full = abs(angle) >= 359.999
    steps = sides if full else max(1, int(round(sides * abs(angle) / 360.0)))
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1), dvec=(0, 0, 0),
                   angle=math.radians(angle), steps=steps, use_merge=full, use_duplicate=False)
    weld(bm, 1e-6)
    if cap and full:
        bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
    _orient_axis(bm, axis)
    return recalc(bm)


def ring(r_inner, r_outer, height, sides=16, bevel=0.0, segments=1, axis="Z", angle=360.0, start_angle=0.0):
    """Thick washer / band (or an arc segment when angle < 360), centred on z = 0 along `axis`."""
    h = height / 2
    prof = [(r_inner, -h), (r_outer, -h), (r_outer, h), (r_inner, h), (r_inner, -h)]
    full = abs(angle) >= 359.999
    bm = lathe(prof, sides=sides, angle=angle, axis="Z", cap=False, start_angle=start_angle)
    if not full:
        bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=4)
    recalc(bm)
    if bevel > 0:
        sharp = [e for e in bm.edges if e.is_manifold and e.calc_face_angle(0) > math.radians(60)]
        _bevel_edges(bm, sharp, bevel, segments)
    _orient_axis(bm, axis)
    return recalc(bm)


def spike(base_radius, length, sides=4, tip=(0.0, 0.0), base_scale=(1.0, 1.0), cap=True, rot_offset=45.0):
    """Pyramid / cone spike along +Z from z = 0 to z = length; tip offset (x, y) bends it."""
    bm = bmesh.new()
    ring_v = []
    for i in range(sides):
        a = math.radians(rot_offset) + 2 * math.pi * i / sides
        ring_v.append(bm.verts.new((math.cos(a) * base_radius * base_scale[0], math.sin(a) * base_radius * base_scale[1], 0)))
    t = bm.verts.new((tip[0], tip[1], length))
    for i in range(sides):
        bm.faces.new((ring_v[i], ring_v[(i + 1) % sides], t))
    if cap:
        bm.faces.new(list(reversed(ring_v)))
    return recalc(bm)


def horn(points, r0, r1=0.0, sides=6, cap=True):
    """Tapered tube ending in a point: horns, claws, curved spikes. points = centre-line (>= 2)."""
    n = len(points)
    radii = [r0 + (r1 - r0) * i / (n - 1) for i in range(n)]
    return tube(points, radii, sides=sides, cap=cap)


# ---- sweeps -------------------------------------------------------------------------------------

def catmull(points, per_segment=4):
    """Smooth a polyline with a Catmull-Rom spline (per_segment samples between input points)."""
    P = [Vector(p) for p in points]
    if len(P) < 3 or per_segment <= 1:
        return P
    out = []
    for i in range(len(P) - 1):
        p0 = P[i - 1] if i > 0 else P[i] * 2 - P[i + 1]
        p1, p2 = P[i], P[i + 1]
        p3 = P[i + 2] if i + 2 < len(P) else P[i + 1] * 2 - P[i]
        for s in range(per_segment):
            t = s / per_segment
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-1])
    return out


def _frames(P, up=(0, 0, 1)):
    """Parallel-transport frames (tangent, normal, binormal) along a polyline."""
    n = len(P)
    T = []
    for i in range(n):
        a = P[max(0, i - 1)]
        b = P[min(n - 1, i + 1)]
        t = (b - a)
        T.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))
    upv = Vector(up)
    N0 = upv - T[0] * upv.dot(T[0])
    if N0.length < 1e-5:
        N0 = Vector((1, 0, 0)) - T[0] * T[0].x
    N = [N0.normalized()]
    for i in range(1, n):
        q = T[i - 1].rotation_difference(T[i])
        N.append((q @ N[-1]).normalized())
    B = [T[i].cross(N[i]).normalized() for i in range(n)]
    return T, N, B


def tube(points, radius, sides=8, closed=False, cap=True, profile=None, twist=0.0, up=(0, 0, 1), scale_xy=None):
    """Sweep a profile along a centre-line. radius: scalar or one per point (0 = pointed end).
    profile: 2D polygon [(x, y), ...] in unit size (default: circle with `sides`); x follows the frame
    normal (toward `up`), y the binormal. scale_xy: per-point (sx, sy) for flattened sections.
    closed: loop the path (rings, wreaths). Returns the bmesh."""
    P = [Vector(p) for p in points]
    n = len(P)
    R = list(radius) if isinstance(radius, (list, tuple)) else [radius] * n
    if profile is None:
        profile = [(math.cos(2 * math.pi * i / sides), math.sin(2 * math.pi * i / sides)) for i in range(sides)]
    m = len(profile)
    T, N, B = _frames(P + ([P[0]] if closed else []), up)
    bm = bmesh.new()
    rings = []
    for i in range(n):
        tw = math.radians(twist) * i / max(1, n - 1)
        c, s = math.cos(tw), math.sin(tw)
        sx, sy = scale_xy[i] if scale_xy else (1.0, 1.0)
        if R[i] <= 1e-6:
            rings.append([bm.verts.new(P[i])])
            continue
        rv = []
        for (px, py) in profile:
            x, y = px * c - py * s, px * s + py * c
            rv.append(bm.verts.new(P[i] + N[i] * (x * R[i] * sx) + B[i] * (y * R[i] * sy)))
        rings.append(rv)
    segs = n if closed else n - 1
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % n]
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(m):
            if len(a) == 1:
                bm.faces.new((a[0], b[k], b[(k + 1) % m]))
            elif len(b) == 1:
                bm.faces.new((a[k], a[(k + 1) % m], b[0]))
            else:
                bm.faces.new((a[k], a[(k + 1) % m], b[(k + 1) % m], b[k]))
    if cap and not closed:
        if len(rings[0]) > 2:
            bm.faces.new(list(reversed(rings[0])))
        if len(rings[-1]) > 2:
            bm.faces.new(rings[-1])
    return recalc(bm)


def band(points, width, thickness, closed=False, cap=True, up=(0, 0, 1)):
    """Flat strap swept along points (belts, straps, bands): rectangle width x thickness.
    The strap's width follows the frame normal (toward `up`)."""
    prof = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    sc = [(width, thickness)] * len(points)
    bm = tube(points, 1.0, profile=prof, closed=closed, cap=cap, up=up, scale_xy=sc)
    for e in bm.edges:
        e.smooth = False
    return bm


def arc_points(radius, a0, a1, n, z=0.0, center=(0, 0)):
    """Points on a circular arc in the XY plane (degrees)."""
    return [Vector((center[0] + radius * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
                    center[1] + radius * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))), z)) for i in range(n)]


# ---- details --------------------------------------------------------------------------------------

def stud(radius, height, sides=6):
    """Low dome rivet / stud standing on z = 0 along +Z (open bottom: it sits on a surface)."""
    bm = bmesh.new()
    r0 = [bm.verts.new((radius * math.cos(2 * math.pi * i / sides), radius * math.sin(2 * math.pi * i / sides), 0)) for i in range(sides)]
    r1 = [bm.verts.new((0.72 * radius * math.cos(2 * math.pi * (i + 0.5) / sides), 0.72 * radius * math.sin(2 * math.pi * (i + 0.5) / sides), height * 0.7)) for i in range(sides)]
    top = bm.verts.new((0, 0, height))
    for i in range(sides):
        j = (i + 1) % sides
        bm.faces.new((r0[i], r0[j], r1[i]))
        bm.faces.new((r1[i], r0[j], r1[j]))
        bm.faces.new((r1[i], r1[j], top))
    return recalc(bm)


def studs(positions, normals, radius, height, sides=6, sink=0.002):
    """Many studs in one bmesh: one per (position, outward normal)."""
    out = bmesh.new()
    for p, nrm in zip(positions, normals):
        s = stud(radius, height, sides)
        nv = Vector(nrm).normalized()
        xform(s, matrix=Matrix.Translation(Vector(p) - nv * sink) @ aim_matrix(nv, from_axis="Z"))
        _append_raw(out, s)
        s.free()
    return out


def rivet_row(p0, p1, count, normal, radius=0.008, height=0.006, sides=6, inset=0.0):
    """`count` studs evenly spaced between p0 and p1 (inset = fraction trimmed at both ends)."""
    a, b = Vector(p0), Vector(p1)
    pts = [a.lerp(b, inset + (1 - 2 * inset) * (i / max(1, count - 1))) for i in range(count)]
    return studs(pts, [normal] * count, radius, height, sides)


def panel_grid(width, height, nu, nv, gap, thickness, bevel=0.0, segments=1, rng=None, jitter=0.0, taper=1.0):
    """Plates with gaps in the local XY plane (thickness along +Z, back face on z = 0), centred on the
    origin. Returns a list of bmeshes (one per plate: the painter gives each its own value).
    jitter: random extra thickness / tilt (0..1) for hand-made plates."""
    rng = rng or random.Random(0)
    pw = (width - gap * (nu - 1)) / nu
    ph = (height - gap * (nv - 1)) / nv
    plates = []
    for i in range(nu):
        for j in range(nv):
            cx = -width / 2 + pw / 2 + i * (pw + gap)
            cy = -height / 2 + ph / 2 + j * (ph + gap)
            t = thickness * (1 + jitter * (rng.random() - 0.5))
            b = box((pw, ph, t), bevel=bevel, segments=segments, taper=(taper, taper))
            tilt = (jitter * (rng.random() - 0.5) * 6, jitter * (rng.random() - 0.5) * 6, 0)
            xform(b, loc=(cx, cy, t / 2), rot=tilt)
            plates.append(b)
    return plates


def plate_ring(radius, height, count, gap_deg, thickness, bevel=0.0, segments=1, sides_per_plate=3, z=0.0, start_angle=0.0):
    """Curved armour plates around +Z (bands on limbs, barrels, pillars): `count` arc segments with
    `gap_deg` between them, inner radius `radius`. Returns a list of bmeshes."""
    span = 360.0 / count
    out = []
    for i in range(count):
        a0 = start_angle + i * span + gap_deg / 2
        b = ring(radius, radius + thickness, height, sides=sides_per_plate * count, bevel=bevel, segments=segments,
                 angle=span - gap_deg, start_angle=a0)
        xform(b, loc=(0, 0, z))
        out.append(b)
    return out


# ---- surface operations -------------------------------------------------------------------------

def symmetrize(bm, direction="-X", dist=1e-4):
    """Mirror one half onto the other (direction '-X' copies +X onto -X, like the Symmetrize tool)."""
    bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction=direction, dist=dist)
    return recalc(bm)


def mirrored(bm, axis="X"):
    """A mirrored COPY of bm (for left/right pairs that are separate parts)."""
    out = bm.copy()
    s = {"X": (-1, 1, 1), "Y": (1, -1, 1), "Z": (1, 1, -1)}[axis]
    xform(out, scale=s)
    return out


def chip_corners(bm, rng, count=3, depth=(0.01, 0.03), tilt=25.0, min_valence=3):
    """Slice random corners off with planes (clean painterly chips on stone, bronze, obsidian).
    depth: (min, max) metres cut into the corner; tilt: random deviation of the cut plane (deg)."""
    for _ in range(count):
        bm.verts.ensure_lookup_table()
        cands = [v for v in bm.verts if len(v.link_edges) >= min_valence and v.is_manifold]
        if not cands:
            break
        v = rng.choice(cands)
        nrm = v.normal.copy()
        if nrm.length < 1e-6:
            continue
        axis = Vector((rng.random() - 0.5, rng.random() - 0.5, rng.random() - 0.5)).normalized()
        nrm = (Quaternion(axis, math.radians(rng.uniform(-tilt, tilt))) @ nrm).normalized()
        d = rng.uniform(*depth)
        co = v.co - nrm * d
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6,
                                     plane_co=co, plane_no=nrm, clear_outer=True)
        cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if cut:
            try:
                bmesh.ops.edgeloop_fill(bm, edges=cut)
            except Exception:  # noqa: BLE001 - open cut (plane grazed a thin part): fill holes instead
                bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
    return recalc(bm)


def noise_displace(bm, amount, freq=6.0, seed=0, along_normal=True, mask=None):
    """Coherent (Perlin) displacement: lumpy slag, organic shells, worn stone. mask(v) -> 0..1."""
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    bm.normal_update()
    moves = []
    for v in bm.verts:
        w = 1.0 if mask is None else mask(v)
        if w <= 0:
            moves.append(None)
            continue
        p = v.co * freq + off
        if along_normal:
            moves.append(v.normal * (noise.noise(p) * amount * w))
        else:
            moves.append(noise.noise_vector(p) * amount * w)
    for v, m in zip(bm.verts, moves):
        if m is not None:
            v.co += m
    return bm


def jitter(bm, rng, amount):
    """Small random vertex offsets (breaks machine-perfect symmetry on organic parts)."""
    for v in bm.verts:
        v.co += Vector((rng.uniform(-amount, amount), rng.uniform(-amount, amount), rng.uniform(-amount, amount)))
    return bm


def mark_sharp(bm, angle_deg=35.0, all_edges=False):
    """Mark edges sharper than angle (or all) as sharp: faceted, flat-painted planes."""
    lim = math.radians(angle_deg)
    for e in bm.edges:
        if all_edges or (e.is_manifold and e.calc_face_angle(0) > lim) or e.is_boundary:
            e.smooth = False
    return bm


# ---- line generators (2D polylines) ------------------------------------------------------------

def crack_lines(rng, start=(0.0, 0.0), direction=0.0, length=0.3, step=0.02, jag=0.45, branches=2,
                branch_len=0.45, branch_angle=40.0, depth=2):
    """Jagged crack (random walk) with recursive branches. direction in degrees. Returns polylines."""
    lines = []

    def walk(p, ang, L, d):
        pts = [p]
        n = max(2, int(L / step))
        a = ang
        for _ in range(n):
            a += rng.uniform(-jag, jag)
            a = ang + max(-0.9, min(0.9, a - ang))
            s = step * rng.uniform(0.7, 1.3)
            p = (p[0] + math.cos(a) * s, p[1] + math.sin(a) * s)
            pts.append(p)
        lines.append(pts)
        if d > 0:
            for _ in range(branches):
                k = rng.randint(1, len(pts) - 1)
                side = rng.choice((-1, 1))
                walk(pts[k], ang + side * math.radians(branch_angle * rng.uniform(0.6, 1.3)), L * branch_len, d - 1)

    walk(tuple(start), math.radians(direction), length, depth)
    return lines


_RUNE_GRID = [(x, y) for y in range(4) for x in range(3)]


def rune_glyph(rng, size=0.05, strokes=3, broken=0.0):
    """Angular rune: a stem plus 1-3 diagonal / hooked strokes on a 3x4 grid, `size` tall, centred.
    broken (0..1) drops stroke ends (the Godworks' broken runes)."""
    w, h = size * 0.6, size
    X = lambda i: (i / 2.0 - 0.5) * w  # noqa: E731
    Y = lambda j: (j / 3.0 - 0.5) * h  # noqa: E731
    lines = []
    sx = rng.choice((0, 1, 2)) if rng.random() < 0.3 else 1
    lines.append([(X(sx), Y(0)), (X(sx), Y(3))])
    for _ in range(max(0, strokes - 1)):
        a = (rng.choice((0, 1, 2)), rng.choice((0, 1, 2, 3)))
        b = (rng.choice((0, 1, 2)), rng.choice((0, 1, 2, 3)))
        if a == b:
            b = ((a[0] + 1) % 3, (a[1] + 2) % 4)
        pts = [(X(a[0]), Y(a[1])), (X(b[0]), Y(b[1]))]
        if rng.random() < 0.35:
            c = (rng.choice((0, 2)), rng.choice((0, 3)))
            pts.append((X(c[0]), Y(c[1])))
        lines.append(pts)
    if broken > 0:
        out = []
        for ln in lines:
            if rng.random() < broken and len(ln) >= 2:
                t = rng.uniform(0.35, 0.7)
                a, b = ln[0], ln[1]
                ln = [a, (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)]
            out.append(ln)
        lines = out
    return lines


def rune_band(rng, count=5, size=0.05, spacing=1.4, strokes=3, broken=0.0, origin=(0.0, 0.0)):
    """A row of runes along +x starting at origin (centred on y = origin.y)."""
    out = []
    for i in range(count):
        cx = origin[0] + i * size * 0.6 * spacing
        for ln in rune_glyph(rng, size, strokes, broken):
            out.append([(p[0] + cx, p[1] + origin[1]) for p in ln])
    return out


def sunburst(n=8, r0=0.02, r1=0.06, r1_alt=None, center=(0.0, 0.0), start_deg=90.0):
    """Radial rays (sun / halo motif): n segments from r0 to r1 (alternate rays to r1_alt)."""
    out = []
    for i in range(n):
        a = math.radians(start_deg + 360.0 * i / n)
        r = r1 if (r1_alt is None or i % 2 == 0) else r1_alt
        out.append([(center[0] + math.cos(a) * r0, center[1] + math.sin(a) * r0),
                    (center[0] + math.cos(a) * r, center[1] + math.sin(a) * r)])
    return out


def ribbon(polylines, width, height, frame=None, cap=True):
    """Raised strips (inlays, weld seams, rune channels) from 2D polylines in the frame's XY plane,
    standing `height` along the frame's +Z. frame: 4x4 (default identity). Returns one bmesh."""
    out = bmesh.new()
    M = Matrix(frame) if frame is not None else Matrix.Identity(4)
    for ln in polylines:
        if len(ln) < 2:
            continue
        pts = [Vector((p[0], p[1], height / 2)) for p in ln]
        b = tube(pts, 1.0, profile=[(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)], cap=cap,
                 up=(0, 0, 1), scale_xy=[(height, width)] * len(pts))
        xform(b, matrix=M)
        _append_raw(out, b)
        b.free()
    return out


# ---- the assembly --------------------------------------------------------------------------------

class Assembly:
    """Collects parts into one mesh: material slot per zone, face attribute gfa_part (int id per
    part), optional vertex groups per bone (rigid skin), per-part shading.

        asm = Assembly("sunspike_shotgun", ["bronze", "iron", "glow"])
        asm.add(box((0.1, 0.3, 0.1), bevel=0.01), "bronze")
        obj = asm.to_object()
    """

    def __init__(self, name, zones, bones=()):
        self.name = name
        self.zones = list(zones)
        self.bones = list(bones)
        self.bm = bmesh.new()
        self.part_layer = self.bm.faces.layers.int.new("gfa_part")
        self.deform = self.bm.verts.layers.deform.verify() if self.bones else None
        self.parts = []          # (name, zone, bone, faces)
        self._next = 0

    def zone_index(self, zone):
        if zone not in self.zones:
            raise KeyError("zone %r not in %s" % (zone, self.zones))
        return self.zones.index(zone)

    def add(self, bm, zone, bone=None, name=None, shading="auto", sharp_angle=35.0, free=True, part=None):
        """Append a part. shading: 'auto' (sharp above sharp_angle), 'flat' (all edges sharp), 'smooth'
        (sharp only above 60 deg: round sides, crisp caps).
        part: reuse an existing part id (e.g. studs that belong to a plate). Returns the part id."""
        zi = self.zone_index(zone)
        if bone is not None and bone not in self.bones:
            raise KeyError("bone %r not declared (%s)" % (bone, self.bones))
        if shading == "flat":
            mark_sharp(bm, all_edges=True)
        elif shading == "auto":
            mark_sharp(bm, sharp_angle)
        elif shading == "smooth":
            mark_sharp(bm, 60.0)        # smooth sides, but caps and real creases stay crisp
        pid = self._next if part is None else part
        if part is None:
            self._next += 1
        vmap = _append_raw(self.bm, bm)
        new_faces = set()
        for f in bm.faces:
            nf = None
            try:
                nf = self.bm.faces.get([vmap[v] for v in f.verts])
            except (ValueError, KeyError):
                nf = None
            if nf is not None:
                nf.material_index = zi
                nf[self.part_layer] = pid
                nf.smooth = True
                new_faces.add(nf)
        if bone is not None:
            bi = self.bones.index(bone)
            for v in vmap.values():
                v[self.deform][bi] = 1.0
        self.parts.append({"id": pid, "name": name or "%s_%d" % (zone, pid), "zone": zone, "bone": bone,
                           "faces": len(new_faces)})
        if free:
            bm.free()
        return pid

    def tris(self):
        return sum(len(f.verts) - 2 for f in self.bm.faces)

    def to_object(self, col=None, weld_dist=0.0):
        """Build the mesh object `name` with material slots GFA_<zone> (created if missing)."""
        if weld_dist > 0:
            weld(self.bm, weld_dist)
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        obj = bpy.data.objects.new(self.name, me)
        (col or bpy.context.scene.collection).objects.link(obj)
        for z in self.zones:
            m = bpy.data.materials.get("GFA_" + z) or bpy.data.materials.new("GFA_" + z)
            me.materials.append(m)
        for b in self.bones:
            obj.vertex_groups.new(name=b)
        # smooth shading everywhere; the sharp edges marked per part give the flat planes
        for p in me.polygons:
            p.use_smooth = True
        obj["gfa_parts"] = len(self.parts)
        return obj
