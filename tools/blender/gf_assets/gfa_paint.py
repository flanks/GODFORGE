"""gf_assets hand-painted NPR texturing: UV unwrap, Cycles CPU bakes of data maps, numpy painting,
base-colour + emissive PNGs and the final export material.

Painting rules (Hades II-inspired NPR; the engine adds its own toon ramp, rim light, ink edge and a
faint brush noise at runtime, crates/gf_client/src/shaders/toon.wesl):
  * flat painted VALUE PLANES per material slot (zone): every flat plane (quantised face normal) and
    every part gets its own small value shift - no light direction is baked, no gradient shading;
  * CAVITY DARKS painted into the colour: concave sharp edges get a dark line, contact areas (baked
    ambient occlusion, blurred and thresholded) a painted shadow shape in the zone's shadow hue;
  * BRUSHY EDGE HIGHLIGHTS: convex sharp edges get a light stroke whose width wobbles and breaks up
    like a brush (never a clean CG bevel line);
  * low-frequency brush noise only (grunge reads as mud at 6-8 % screen height);
  * optional gradient along an axis, stroke streaks (grain, drips), spots (soot, verdigris);
  * EMISSIVE is a separate texture: glow zones (flat / radial / along an axis) and line decals
    (runes, cracks, channels) carry emission; the base colour under a glow is a pale painted version.

Pipeline (paint_asset() does all of it):
  unwrap() -> bake_maps() [Cycles, CPU: zone, object position, true + shading normal, part id,
  ambient occlusion] -> edge_distances() [mesh sharp edges, KD-tree] -> paint() [numpy] ->
  dilate gutters -> save PNGs -> apply_final_material() (one material: base colour + emissive).

Noise / voronoi / dilate helpers adapted from GODFORGE tools/blender/gf_hero/s2_paint.py; the bake
pass swapping adapted from gf_hero/s2_texture.py.
"""
import colorsys
import math
import os
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

import gfa_common as C

# ---- zone recipe defaults ------------------------------------------------------------------------
ZONE_DEFAULTS = {
    "base": "#808080",
    "shadow": None,          # None -> derived (darker, more saturated, hue leaning warm-red / cool-violet)
    "light": None,           # None -> derived (lighter, slightly desaturated)
    "planes": 0.05,          # +- value per flat plane (quantised true normal)
    "parts": 0.05,           # +- value per part (gfa_part)
    "brush": 0.035,          # +- low-frequency value noise
    "brush_freq": 7.0,       # noise cycles per metre
    "stroke": None,          # (x, y, z): direction of painted streaks (wood grain, drips, cloth)
    "stroke_amount": 0.0,    # 0..1 how much the streaks pull toward light / shadow
    "stroke_freq": (60.0, 6.0),   # (across, along) cycles per metre
    "cavity": 0.7,           # concave sharp edges: strength of the dark line
    "cavity_width": 0.006,   # m
    "ao": 0.55,              # contact shadows (baked AO): strength
    "ao_range": (0.25, 0.7), # occlusion (1 - AO) mapped through smoothstep(lo, hi)
    "edge": 0.75,            # convex sharp edges: strength of the light stroke
    "edge_width": 0.005,     # m (the stroke wobbles between 0.35x and 1.45x of this)
    "edge_breakup": 0.4,     # fraction of the edge length left unpainted (0 = continuous, 0.8 = sparse dabs)
    "gradient": None,        # {"axis": (x,y,z) | "center": (x,y,z) [+ "axis": line], "range": (a, b),
                             #  "color": hex|"light"|"shadow", "amount": 0.3}: planar, radial or cylindrical
    "spots": None,           # {"color": hex, "amount": 0.4, "freq": 12.0, "threshold": (0.6, 0.72)}
    "emit": None,            # {"color": rim hex, "hot": hex, "core": hex, "mode": flat|radial|axis|plane,
                             #  "center": (x,y,z), "axis": (x,y,z), "radius": r, "range": (a,b), "base_mix": 0.3,
                             #  "fade": (d0, d1) emission only beyond d0 (normalised distance), "strength": 1}
}


def zone(**kw):
    """A zone recipe = defaults updated with kw (unknown keys are an error)."""
    bad = set(kw) - set(ZONE_DEFAULTS)
    if bad:
        raise KeyError("unknown zone keys: %s" % sorted(bad))
    z = dict(ZONE_DEFAULTS)
    z.update(kw)
    return z


def decal_lines(lines, frame, width, zones=None, color=None, rim=None, rim_width=None, emit=None,
                facing=0.35, depth=(-0.02, 0.02), mapping="planar", radius=None):
    """A line decal: 2D polylines (metres) drawn in `frame`'s XY plane and projected along its +Z.
    mapping 'cylinder': frame Z = cylinder axis, u = angle * radius (radius required), v = height;
    lines are then (u, v) around the cylinder, u = 0 on the frame's +X side.
    color: painted line colour (hex) | rim: darker halo (hex) | emit: {"color", "core"} for glowing lines."""
    return {"lines": lines, "frame": [list(r) for r in Matrix(frame)], "width": width, "zones": zones,
            "color": color, "rim": rim, "rim_width": rim_width or width * 2.5, "emit": emit,
            "facing": facing, "depth": list(depth), "mapping": mapping, "radius": radius}


# ---- colour helpers (sRGB space: painting is done in display values, like a painter) ----------------

def hex3(h):
    return np.array(C.hex_rgb(h), dtype=np.float32)


def derive_shadow(base):
    r, g, b = [float(x) for x in base]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    # lean toward red-violet (warm hues) or blue-violet (cool hues): painted shadows, never grey
    target = 0.97 if (h < 0.17 or h > 0.8) else 0.72
    dh = ((target - h + 0.5) % 1.0) - 0.5
    h = (h + dh * 0.12) % 1.0
    return np.array(colorsys.hsv_to_rgb(h, min(1.0, s * 1.15 + 0.08), v * 0.42), dtype=np.float32)


def derive_light(base):
    r, g, b = [float(x) for x in base]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return np.array(colorsys.hsv_to_rgb(h, s * 0.75, min(1.0, v * 1.45 + 0.08)), dtype=np.float32)


def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


# ---- noise (numpy, deterministic) ------------------------------------------------------------------

def _hash(ix, iy, iz, seed=0):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = h & 0xFFFFFFFF
    h = (h ^ (h >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    h = (h ^ (h >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def hash01(ints, seed=0):
    ints = np.asarray(ints, dtype=np.int64)
    return _hash(ints, ints * 7 + 3, ints * 13 + 5, seed)


def value_noise(p, freq, seed=0):
    q = p * freq
    i = np.floor(q)
    f = q - i
    u = f * f * (3 - 2 * f)
    ix, iy, iz = i[:, 0], i[:, 1], i[:, 2]
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[:, 0] if dx else 1 - u[:, 0]) * (u[:, 1] if dy else 1 - u[:, 1]) * (u[:, 2] if dz else 1 - u[:, 2])
                out = out + w * _hash(ix + dx, iy + dy, iz + dz, seed)
    return out


def fbm(p, freq, octaves=3, seed=0):
    out, amp, tot = 0.0, 0.5, 0.0
    for o in range(octaves):
        out = out + amp * value_noise(p, freq * (2.0 ** o), seed + o * 17)
        tot += amp
        amp *= 0.5
    return out / tot


def anisotropic(p, direction, f_across, f_along, seed=0):
    """Noise stretched along `direction` (streaks: grain, drips, brush strokes)."""
    d = np.asarray(direction, dtype=np.float32)
    d = d / (np.linalg.norm(d) + 1e-9)
    along = (p * d).sum(1, keepdims=True)
    q = (p - d * along) * f_across + d * along * f_along
    return value_noise(q, 1.0, seed) * 0.65 + value_noise(q * 2.3 + 11.0, 1.0, seed + 5) * 0.35


def voronoi(p, freq, seed=0, jitter=0.9):
    """F1 distance, edge distance (F2 - F1) and a cell hash (cells = painted facets / cracked plates)."""
    q = p * freq
    i = np.floor(q)
    f1 = np.full(len(q), 9.0, dtype=np.float32)
    f2 = np.full(len(q), 9.0, dtype=np.float32)
    cid = np.zeros(len(q), dtype=np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cx, cy, cz = i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz
                fx = cx + 0.5 + (_hash(cx, cy, cz, seed) - 0.5) * jitter
                fy = cy + 0.5 + (_hash(cx, cy, cz, seed + 1) - 0.5) * jitter
                fz = cz + 0.5 + (_hash(cx, cy, cz, seed + 2) - 0.5) * jitter
                d = np.sqrt((q[:, 0] - fx) ** 2 + (q[:, 1] - fy) ** 2 + (q[:, 2] - fz) ** 2).astype(np.float32)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                cid = np.where(closer, _hash(cx, cy, cz, seed + 3), cid)
                f1 = np.where(closer, d, f1)
    return f1, f2 - f1, cid


def spread01(n, gain=3.2):
    """Stretch a noise that clusters around 0.5 (fbm) to cover ~0..1."""
    return np.clip((n - 0.5) * gain + 0.5, 0.0, 1.0)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t, dtype=np.float32)
    if t.ndim == 1:
        t = t[:, None]
    return a * (1 - t) + b * t


# ---- UVs ------------------------------------------------------------------------------------------

def unwrap(obj, size=1024, margin_px=6, angle_limit=60.0):
    """Smart-project + equal texel density + pack into one atlas. Returns texel density stats (px/m)."""
    me = obj.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    C.select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit), island_margin=0.0, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, rotate_method="ANY", scale=True,
                            merge_overlap=False, margin_method="FRACTION", margin=margin_px / size,
                            pin=False, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return texel_density(obj, size)


def texel_density(obj, size):
    me = obj.data
    uvl = me.uv_layers.active.data
    d = []
    for p in me.polygons:
        if p.area < 1e-9:
            continue
        uv = [uvl[i].uv for i in p.loop_indices]
        s = 0.0
        for k in range(1, len(uv) - 1):
            s += abs((uv[k].x - uv[0].x) * (uv[k + 1].y - uv[0].y) - (uv[k + 1].x - uv[0].x) * (uv[k].y - uv[0].y)) / 2
        d.append(size * math.sqrt(s / p.area))
    d = np.array(d)
    return {"median": round(float(np.median(d)), 1), "p10": round(float(np.percentile(d, 10)), 1),
            "p90": round(float(np.percentile(d, 90)), 1)}


# ---- Cycles bakes ------------------------------------------------------------------------------------

def _set_pass(mats, kind, img, lo, hi, ao_distance, ao_node_samples):
    for zi, m in enumerate(mats):
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
        L = nt.links.new
        if kind == "zone":
            v = (zi + 1) / 64.0
            em.inputs["Color"].default_value = (v, v, v, 1.0)
        elif kind == "pos":
            tc = nt.nodes.new("ShaderNodeTexCoord")
            sub = nt.nodes.new("ShaderNodeVectorMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = tuple(lo)
            div = nt.nodes.new("ShaderNodeVectorMath")
            div.operation = "DIVIDE"
            div.inputs[1].default_value = tuple(hi - lo)
            L(tc.outputs["Object"], sub.inputs[0])
            L(sub.outputs[0], div.inputs[0])
            L(div.outputs[0], em.inputs["Color"])
        elif kind in ("tnrm", "snrm"):
            g = nt.nodes.new("ShaderNodeNewGeometry")
            vt = nt.nodes.new("ShaderNodeVectorTransform")
            vt.vector_type = "NORMAL"
            vt.convert_from = "WORLD"
            vt.convert_to = "OBJECT"
            ma = nt.nodes.new("ShaderNodeVectorMath")
            ma.operation = "MULTIPLY_ADD"
            ma.inputs[1].default_value = (0.5, 0.5, 0.5)
            ma.inputs[2].default_value = (0.5, 0.5, 0.5)
            L(g.outputs["True Normal" if kind == "tnrm" else "Normal"], vt.inputs["Vector"])
            L(vt.outputs["Vector"], ma.inputs[0])
            L(ma.outputs[0], em.inputs["Color"])
        elif kind == "part":
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_type = "GEOMETRY"
            at.attribute_name = "gfa_part"
            ad = nt.nodes.new("ShaderNodeMath")
            ad.operation = "ADD"
            ad.inputs[1].default_value = 1.0
            dv = nt.nodes.new("ShaderNodeMath")
            dv.operation = "DIVIDE"
            dv.inputs[1].default_value = 4096.0
            L(at.outputs["Fac"], ad.inputs[0])
            L(ad.outputs[0], dv.inputs[0])
            L(dv.outputs[0], em.inputs["Color"])
        elif kind == "ao":
            ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
            ao.samples = ao_node_samples
            ao.only_local = True
            ao.inside = False
            ao.inputs["Distance"].default_value = ao_distance
            L(ao.outputs["AO"], em.inputs["Color"])
        elif kind.startswith("attr:"):
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_type = "GEOMETRY"
            at.attribute_name = kind[5:]
            L(at.outputs["Fac"], em.inputs["Color"])


def bake_maps(obj, size=1024, ao_distance=0.05, ao_samples=16, extra_attrs=()):
    """Bake data maps of `obj` (UVs + GFA_<zone> material slots required) with Cycles on the CPU.
    Returns dict of (size, size, 4) float32 arrays: zone, pos (object space, 0..1 in bounds lo..hi),
    tnrm, snrm (object space, 0..1 encoded), part, ao, attr:<name>; plus 'lo', 'hi'."""
    scene = bpy.context.scene
    C.use_cpu(scene)
    scene.render.engine = "CYCLES"
    scene.cycles.use_denoising = False
    scene.render.bake.margin = 0
    scene.render.bake.use_clear = True
    hidden = []
    for o in scene.objects:
        if o is not obj and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    co = np.array([v.co[:] for v in obj.data.vertices], dtype=np.float64)
    lo = Vector((co.min(0) - 0.01).tolist())
    hi = Vector((co.max(0) + 0.01).tolist())
    mats = [s.material for s in obj.material_slots]
    img = bpy.data.images.new("gfa_bake", size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    out = {"lo": np.array(lo[:]), "hi": np.array(hi[:])}
    kinds = ["zone", "pos", "tnrm", "snrm", "part", "ao"] + ["attr:" + a for a in extra_attrs]
    C.select_only(obj)
    for kind in kinds:
        t = time.time()
        scene.cycles.samples = ao_samples if kind == "ao" else 1
        _set_pass(mats, kind, img, lo, hi, ao_distance, 8)
        bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True, target="IMAGE_TEXTURES")
        px = np.empty(size * size * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        out[kind] = px.reshape(size, size, 4).copy()
        C.log("baked %-6s %.1fs" % (kind, time.time() - t))
    bpy.data.images.remove(img)
    for o in hidden:
        o.hide_render = False
    return out


# ---- mesh-edge distance maps ------------------------------------------------------------------------

def edge_points(obj, spacing=0.002, min_angle=20.0, sharp_only_below=60.0):
    """Sample points along the sharp edges of obj, split into convex and concave lists.
    An edge counts when it is marked sharp (flat-shaded crease) and bends more than min_angle, or
    when it bends more than sharp_only_below regardless of marking."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    convex, concave = [], []
    lim, big = math.radians(min_angle), math.radians(sharp_only_below)
    for e in bm.edges:
        if not e.is_manifold:
            continue
        ang = e.calc_face_angle_signed(0.0)
        a = abs(ang)
        if a < lim or (e.smooth and a < big):
            continue
        p0, p1 = e.verts[0].co.copy(), e.verts[1].co.copy()
        n = max(1, int((p1 - p0).length / spacing))
        pts = [p0.lerp(p1, (i + 0.5) / n) for i in range(n)]
        (convex if ang > 0 else concave).extend(pts)
    bm.free()
    return convex, concave


def _kd_dist(points, queries, cap):
    d = np.full(len(queries), cap, dtype=np.float32)
    if not points:
        return d
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(p, i)
    kd.balance()
    find = kd.find
    out = np.empty(len(queries), dtype=np.float32)
    for i, q in enumerate(queries.tolist()):
        r = find(q)
        out[i] = r[2]
    return np.minimum(out, cap)


def edge_distances(obj, pos, spacing=0.002, min_angle=20.0, cap=0.05):
    """Distance (m) from each position (N, 3 object space) to the nearest convex / concave sharp edge."""
    convex, concave = edge_points(obj, spacing, min_angle)
    t = time.time()
    dv = _kd_dist(convex, pos, cap)
    dc = _kd_dist(concave, pos, cap)
    C.log("edge distances: %d convex / %d concave edge samples, %d texels (%.1fs)" % (
        len(convex), len(concave), len(pos), time.time() - t))
    return dv, dc


# ---- image utilities -------------------------------------------------------------------------------

def masked_blur(img, valid, radius=2, passes=2):
    """Box blur restricted to covered texels (island borders do not pull in the empty gutter)."""
    a = img * valid[..., None] if img.ndim == 3 else img * valid
    w = valid.astype(np.float32)
    for _ in range(passes):
        acc = np.zeros_like(a)
        wacc = np.zeros_like(w)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                acc += np.roll(np.roll(a, dy, 0), dx, 1)
                wacc += np.roll(np.roll(w, dy, 0), dx, 1)
        a = acc / np.maximum(wacc if a.ndim == 2 else wacc[..., None], 1e-6)
        a = a * (valid[..., None] if a.ndim == 3 else valid)
    return a


def dilate(img, valid, iters=16):
    """Grow painted texels into the empty gutter (mips and bilinear filtering never pick up black)."""
    img = img.copy()
    v = valid.copy()
    for _ in range(iters):
        acc = np.zeros_like(img)
        cnt = np.zeros(v.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            sv = np.roll(np.roll(v, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sv[..., None]
            cnt += sv
        grow = (~v) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        v = v | grow
    return img


def save_png(path, rgb, name=None):
    """Write an sRGB 8-bit PNG from an (H, W, 3) float array in 0..1 (row 0 = bottom, Blender order)."""
    h, w = rgb.shape[:2]
    img = bpy.data.images.new(name or os.path.basename(path), w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = np.clip(rgb, 0, 1)
    img.pixels.foreach_set(px.ravel())
    C.ensure_dir(os.path.dirname(path))
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return img


# ---- the painter -------------------------------------------------------------------------------------

def _polyline_dist(uv, lines):
    """Distance from 2D points (N, 2) to a list of polylines."""
    d = np.full(len(uv), 9.0, dtype=np.float32)
    for ln in lines:
        P = np.asarray(ln, dtype=np.float32)
        for a, b in zip(P[:-1], P[1:]):
            ab = b - a
            L2 = float(ab @ ab)
            if L2 < 1e-12:
                continue
            t = np.clip(((uv - a) @ ab) / L2, 0, 1)
            proj = a + t[:, None] * ab
            d = np.minimum(d, np.linalg.norm(uv - proj, axis=1))
    return d


def _decal_masks(dec, P, Nt):
    """(line mask, rim mask) for decal `dec` over texels P (N, 3) with true normals Nt."""
    M = Matrix(dec["frame"])
    Mi = np.array(M.inverted(), dtype=np.float32)
    q = P @ Mi[:3, :3].T + Mi[:3, 3]
    ax = np.array(M.to_3x3(), dtype=np.float32)
    zdir = ax[:, 2] / np.linalg.norm(ax[:, 2])
    if dec["mapping"] == "cylinder":
        r = dec["radius"]
        ang = np.arctan2(q[:, 1], q[:, 0])
        uv = np.stack([ang * r, q[:, 2]], 1)
        radial = np.stack([np.cos(ang), np.sin(ang), np.zeros_like(ang)], 1) @ ax.T
        facing = (Nt * radial).sum(1)
        depth_ok = np.ones(len(P), dtype=bool)
    else:
        uv = q[:, :2]
        facing = Nt @ zdir
        depth_ok = (q[:, 2] >= dec["depth"][0]) & (q[:, 2] <= dec["depth"][1])
    ok = (facing > dec["facing"]) & depth_ok
    allpts = np.concatenate([np.asarray(ln, dtype=np.float32) for ln in dec["lines"]])
    pad = dec["rim_width"] * 1.5
    lo, hi = allpts.min(0) - pad, allpts.max(0) + pad
    ok &= (uv[:, 0] > lo[0]) & (uv[:, 0] < hi[0]) & (uv[:, 1] > lo[1]) & (uv[:, 1] < hi[1])
    line = np.zeros(len(P), dtype=np.float32)
    rim = np.zeros(len(P), dtype=np.float32)
    idx = np.nonzero(ok)[0]
    if len(idx):
        d = _polyline_dist(uv[idx], dec["lines"])
        w = dec["width"]
        line[idx] = smoothstep(w * 0.5, w * 0.2, d)
        rim[idx] = smoothstep(dec["rim_width"], w * 0.5, d)
    return line, rim


def _field(p, g):
    """Scalar field over points: distance to a line (center + axis), to a point (center) or the
    projection on an axis (axis only)."""
    if "center" in g:
        v = p - np.asarray(g["center"], dtype=np.float32)
        if g.get("axis") is not None:
            ax = np.asarray(g["axis"], dtype=np.float32)
            ax = ax / np.linalg.norm(ax)
            return np.linalg.norm(v - (v @ ax)[:, None] * ax, axis=1)
        return np.linalg.norm(v, axis=1)
    ax = np.asarray(g["axis"], dtype=np.float32)
    return p @ (ax / np.linalg.norm(ax))


def paint(maps, zones_order, recipes, dist_convex, dist_concave, decals=(), seed=0):
    """Paint every covered texel. maps: dict of flat arrays over covered texels (pos in metres, tnrm,
    snrm, part, ao, zone index). Returns (base, emissive) (N, 3) sRGB 0..1."""
    P, Nt, Ns = maps["pos"], maps["tnrm"], maps["snrm"]
    Z, part, ao = maps["zone"], maps["part"], maps["ao"]
    N = len(P)
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    # plane id: quantised true normal (every flat plane gets one value), part id hash
    qn = np.round(Nt * 2.5).astype(np.int64)
    plane_h = _hash(qn[:, 0], qn[:, 1], qn[:, 2], seed + 101) * 2 - 1
    part_h = hash01(part, seed + 202) * 2 - 1
    # fbm clusters around 0.5: stretch it to ~0..1 so wobble and break-up actually vary
    wobble = spread01(fbm(P, 30.0, 2, seed=seed + 5))    # edge stroke width wobble
    dabs = spread01(fbm(P, 11.0, 2, seed=seed + 6))      # edge stroke break-up (long strokes, gaps)
    for zi, zname in enumerate(zones_order):
        m = Z == zi
        if not m.any():
            continue
        r = recipes[zname]
        b0 = hex3(r["base"])
        sh = hex3(r["shadow"]) if r["shadow"] else derive_shadow(b0)
        li = hex3(r["light"]) if r["light"] else derive_light(b0)
        p, nt = P[m], Nt[m]
        n = m.sum()
        c = np.repeat(b0[None], n, 0)
        # flat value planes + per-part values
        c = c * (1 + r["planes"] * plane_h[m][:, None]) * (1 + r["parts"] * part_h[m][:, None])
        # gradient along an axis
        g = r["gradient"]
        if g:
            t = smoothstep(g["range"][0], g["range"][1], _field(p, g))
            gc = li if g["color"] == "light" else sh if g["color"] == "shadow" else hex3(g["color"])
            c = mix(c, gc, t * g.get("amount", 0.3))
        # low-frequency brush noise
        c = c * (1 + r["brush"] * (fbm(p, r["brush_freq"], 3, seed=seed + zi * 11) * 2 - 1))[:, None]
        # painted streaks
        if r["stroke"] is not None and r["stroke_amount"] > 0:
            st = anisotropic(p, r["stroke"], r["stroke_freq"][0], r["stroke_freq"][1], seed=seed + 31 + zi)
            c = mix(c, li, smoothstep(0.58, 0.8, st) * r["stroke_amount"])
            c = mix(c, sh, smoothstep(0.42, 0.22, st) * r["stroke_amount"])
        # spots (soot, verdigris, wet sheen)
        s = r["spots"]
        if s:
            sp = smoothstep(s["threshold"][0], s["threshold"][1], fbm(p, s["freq"], 3, seed=seed + 41 + zi))
            c = mix(c, hex3(s["color"]), sp * s["amount"])
        # contact shadows from AO: a painted shape, not a gradient
        occ = 1 - ao[m]
        k = smoothstep(r["ao_range"][0], r["ao_range"][1], occ + (dabs[m] - 0.5) * 0.1)
        c = mix(c, sh, k * r["ao"])
        # cavity lines on concave sharp edges
        cw = r["cavity_width"]
        k = smoothstep(cw, cw * 0.25, dist_concave[m])
        c = mix(c, sh * 0.85, k * r["cavity"])
        # brushy highlights on convex sharp edges
        ew = r["edge_width"] * (0.35 + 1.1 * wobble[m])
        k = smoothstep(ew, ew * 0.3, dist_convex[m])
        brk = smoothstep(r["edge_breakup"] - 0.12, r["edge_breakup"] + 0.12, dabs[m])
        c = mix(c, li, k * brk * r["edge"])
        # emission
        e = r["emit"]
        if e:
            rim_c = hex3(e["color"])
            hot = hex3(e.get("hot", e["color"]))
            core = hex3(e.get("core", e.get("hot", e["color"])))
            mode = e.get("mode", "flat")
            if mode == "radial":
                d = _field(p, {"center": e["center"]}) / e["radius"]
            elif mode == "axis":
                d = _field(p, {"center": e["center"], "axis": e["axis"]}) / e["radius"]
            elif mode == "plane":
                d = smoothstep(e["range"][0], e["range"][1], _field(p, {"axis": e["axis"]}))
            else:
                d = np.full(n, 0.5, dtype=np.float32)
            em = mix(mix(np.repeat(core[None], n, 0), hot, smoothstep(0.0, 0.55, d)), rim_c, smoothstep(0.55, 1.0, d))
            em = em * (1 + 0.06 * (fbm(p, 20.0, 2, seed=seed + 77) * 2 - 1))[:, None]
            f = smoothstep(e["fade"][0], e["fade"][1], d) if e.get("fade") else np.ones(n, dtype=np.float32)
            # emission only beyond fade[0] (fully on at fade[1]): glowing tips, hot rims
            emis[m] = em * (f * e.get("strength", 1.0))[:, None]
            c = mix(c, mix(em, np.ones(3, dtype=np.float32), e.get("base_mix", 0.25)), f)
        base[m] = c
    # decals: painted lines, burnt rims, glowing channels
    for dec in decals:
        target = np.ones(N, dtype=bool) if not dec["zones"] else np.isin(Z, [zones_order.index(z) for z in dec["zones"]])
        idx = np.nonzero(target)[0]
        line, rimm = _decal_masks(dec, P[idx], Nt[idx])
        if dec["rim"]:
            base[idx] = mix(base[idx], hex3(dec["rim"]), rimm * 0.75)
        if dec["color"]:
            base[idx] = mix(base[idx], hex3(dec["color"]), line)
        if dec["emit"]:
            ec = hex3(dec["emit"]["color"])
            core = hex3(dec["emit"].get("core", dec["emit"]["color"]))
            glow = mix(np.repeat(ec[None], len(idx), 0), core, smoothstep(0.5, 1.0, line))
            emis[idx] = np.maximum(emis[idx], glow * np.maximum(line, rimm * 0.25)[:, None])
    return np.clip(base, 0, 1), np.clip(emis, 0, 1)


# ---- final material ----------------------------------------------------------------------------------

def apply_final_material(obj, name, base_png, emis_png, roughness=0.85):
    """Replace the zone slots with ONE material: base colour + emissive textures (what the engine reads).
    The zone index survives as the face attribute gfa_zone (repaints), zone names in obj['gfa_zones']."""
    me = obj.data
    zones = [s.material.name[4:] if s.material and s.material.name.startswith("GFA_") else "" for s in obj.material_slots]
    zi = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", zi)
    if "gfa_zone" in me.attributes:
        me.attributes.remove(me.attributes["gfa_zone"])
    me.attributes.new("gfa_zone", "INT", "FACE").data.foreach_set("value", zi)
    obj["gfa_zones"] = ",".join(zones)
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tb = nt.nodes.new("ShaderNodeTexImage")
    tb.image = bpy.data.images.load(base_png, check_existing=True)
    tb.image.colorspace_settings.name = "sRGB"
    te = nt.nodes.new("ShaderNodeTexImage")
    te.image = bpy.data.images.load(emis_png, check_existing=True)
    te.image.colorspace_settings.name = "sRGB"
    nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(te.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = True       # glTF doubleSided = false: closed game meshes, half the fragments
    tb.location, te.location, bsdf.location, out.location = (-500, 200), (-500, -150), (-150, 0), (200, 0)
    me.materials.clear()
    me.materials.append(mat)
    me.polygons.foreach_set("material_index", np.zeros(len(me.polygons), dtype=np.int32))
    me.update()
    return mat


# ---- one call -----------------------------------------------------------------------------------------

def paint_asset(obj, key, recipes, tex_dir, size=1024, decals=(), ao_distance=0.05, ao_samples=16,
                edge_min_angle=20.0, margin_px=6, seed=0, uv_angle=60.0, preview_dir=None):
    """Unwrap, bake, paint, write <tex_dir>/<key>_basecolor.png + <key>_emissive.png and assign the final
    material M_<key>. recipes: {zone: zone(...)} for every GFA_<zone> slot on obj. Returns a report."""
    t0 = time.time()
    zones_order = [s.material.name[4:] for s in obj.material_slots]
    missing = [z for z in zones_order if z not in recipes]
    if missing:
        raise KeyError("no paint recipe for zones %s" % missing)
    dens = unwrap(obj, size, margin_px, uv_angle)
    C.log("unwrapped: %.0f px/m median" % dens["median"])
    mp = bake_maps(obj, size, ao_distance, ao_samples)
    zone_img = mp["zone"][..., 0]
    valid = zone_img > 0.5 / 64
    ao_img = masked_blur(mp["ao"][..., 0], valid, radius=2, passes=2)
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
    dv, dc = edge_distances(obj, flat["pos"], min_angle=edge_min_angle)
    base, emis = paint(flat, zones_order, recipes, dv, dc, decals, seed)
    B = np.zeros((size, size, 3), dtype=np.float32)
    E = np.zeros((size, size, 3), dtype=np.float32)
    B[valid] = base
    E[valid] = emis
    B = dilate(B, valid, 12)
    E = dilate(E, valid, 12)
    C.ensure_dir(tex_dir)
    bp = os.path.join(tex_dir, "%s_basecolor.png" % key)
    ep = os.path.join(tex_dir, "%s_emissive.png" % key)
    save_png(bp, B, "%s_basecolor" % key)
    save_png(ep, E, "%s_emissive" % key)
    if preview_dir:
        save_png(os.path.join(preview_dir, "%s_ao.png" % key), np.repeat(ao_img[..., None], 3, 2), "%s_ao_dbg" % key)
    apply_final_material(obj, "M_%s" % key, bp, ep)
    rep = {"size": size, "texel_density_px_per_m": dens, "coverage": round(float(valid.mean()), 3),
           "zones": zones_order, "decals": len(decals), "basecolor": C.rel(bp), "emissive": C.rel(ep),
           "emissive_texels": int((E.max(2) > 0.02).sum()), "seconds": round(time.time() - t0, 1)}
    C.log("painted %s in %.0fs (coverage %.0f%%)" % (key, rep["seconds"], 100 * rep["coverage"]))
    return rep


# ---- faction presets (gfa_spec.FACTIONS: the user's enemy pack) --------------------------------------------

def faction_zone(faction, material, glow=False, **kw):
    """Zone recipe from a faction material: base / shadow / light from gfa_spec.FACTIONS, and for glow
    materials (those with rim / hot / core) an emission rule (default flat; pass emit=... to override).
        faction_zone("unmade", "obsidian", planes=0.1)
        faction_zone("unmade", "ichor", glow=True)
        faction_zone("godworks", "cold_gold_glow", glow=True, emit={..., "mode": "radial", ...})"""
    import gfa_spec as SPEC
    m = SPEC.FACTIONS[faction]["materials"][material]
    z = {"base": m["base"], "shadow": m["shadow"], "light": m["light"]}
    if glow:
        if "rim" not in m:
            raise KeyError("%s.%s has no glow tones" % (faction, material))
        z["emit"] = {"color": m["rim"], "hot": m["hot"], "core": m["core"], "mode": "flat"}
        z.update(edge=0.0, cavity=0.0, ao=0.0)
    z.update(kw)
    return zone(**z)
