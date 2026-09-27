"""Kael variant of tools/blender/gf_hero/render_blockout.py (verbatim copy; one change): the lit ("tex", "close",
in-game) renders use Cycles on the CPU at low samples instead of EEVEE, because the GPU is shared with the TRELLIS.2
jobs and the review-render rule is Cycles CPU or Workbench, never EEVEE. Output names and framing are unchanged, so
tools/comfy/blockout_sheets.py reads them as it reads Brax's and Valdris's. GF_CYCLES_SAMPLES overrides the 24 samples.
"""
"""Review renders + mesh metrics for a raw TRELLIS.2 hero blockout (pipeline stage 1).

Adapted from Ashen Covenant tools/trellis/render_glb.py (four ortho views of a generated GLB,
framed by its bounds). GODFORGE additions: the mesh is normalised to the in-game hero height
(feet on z=0, 2.2 m by default), turnarounds are rendered twice (EEVEE with the baked texture, and
Workbench clay so the texture cannot hide the shape), close-ups frame the head, both gauntlets and
the skirt/legs, the in-game view reproduces the client camera (orthographic, 55 degree pitch, yaw 0,
FixedVertical 22 m / 28 m, pixels at 1080p scale), and a metrics JSON records topology defects.

  blender -b -P tools/blender/gf_hero/render_blockout.py -- <in.glb> <out_dir> <stem>
          [--height 2.2] [--yaw DEG] [--size 800]

  --yaw   extra rotation about +Z applied after import so the hero faces Blender -Y
          (= glTF/Bevy +Z, toward the game camera). Check the front render and pass it if needed.

Writes into <out_dir>:
  <stem>_tex_<view>.png, <stem>_clay_<view>.png   views: front, front34L, sideL, back, back34R, sideR
  <stem>_close_<part>_<view>.png                  parts: head, gauntletR, gauntletL, legs
  <stem>_ingame_<vh>_<look>.png                   256 px, true 1080p pixel scale; looks: tex, sil, tex34
  <stem>_frontsil.png                             flat front silhouette (alpha) for the concept IoU
  <stem>_metrics.json
Nothing is written back to the GLB. A SCULPT REFERENCE is judged here, never shipped.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 3:
    raise SystemExit(__doc__)
SRC, OUT, STEM = os.path.abspath(argv[0]), os.path.abspath(argv[1]), argv[2]


def opt(name, default, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


HEIGHT = opt("--height", 2.2)
YAW = opt("--yaw", 0.0)
SIZE = opt("--size", 800, int)
GAME_PITCH = 55.0                   # assets/content/game.ron camera.pitch_deg
GAME_VIEW_HEIGHTS = (22.0, 28.0)    # camera.view_height for 1 and 4 players (metres, FixedVertical)
SCREEN_H = 1080                     # judge at 1080p
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no mesh in " + SRC)

# ---- normalise: yaw, feet on the floor, centred, HEIGHT tall ---------------------------------
root = bpy.data.objects.new("hero_root", None)
scene.collection.objects.link(root)
for o in scene.objects:
    if o.parent is None and o is not root:
        o.parent = root
bpy.context.view_layer.update()


def world_verts():
    pts = []
    for o in meshes:
        m = np.array(o.matrix_world)
        co = np.empty(len(o.data.vertices) * 3, dtype=np.float64)
        o.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        pts.append(co @ m[:3, :3].T + m[:3, 3])
    return np.concatenate(pts)


raw = world_verts()
raw_lo, raw_hi = raw.min(0), raw.max(0)
root.rotation_euler = Euler((0, 0, math.radians(YAW)))
bpy.context.view_layer.update()
v = world_verts()
lo, hi = v.min(0), v.max(0)
s = HEIGHT / (hi[2] - lo[2])
root.scale = (s, s, s)
bpy.context.view_layer.update()
v = world_verts()
lo, hi = v.min(0), v.max(0)
root.location = (-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2])
bpy.context.view_layer.update()
V = world_verts()
lo, hi = V.min(0), V.max(0)
dims = hi - lo
print("[blockout] %s: normalised to %.2f m, bounds %.2f x %.2f x %.2f (scale %.3f)" % (os.path.basename(SRC), HEIGHT, *dims, s))

# ---- topology metrics (vertices welded by position: glTF splits them at UV seams) -------------
tris = 0
faces_all = []
offset = 0
for o in meshes:
    me = o.data
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", t)
    faces_all.append(t.reshape(-1, 3) + offset)
    offset += len(me.vertices)
    tris += len(me.loop_triangles)
F = np.concatenate(faces_all)
key = np.round(V / (HEIGHT * 1e-6)).astype(np.int64)
_, weld = np.unique(key, axis=0, return_inverse=True)
weld = weld.ravel()
Fw = weld[F]
degenerate = int(((Fw[:, 0] == Fw[:, 1]) | (Fw[:, 1] == Fw[:, 2]) | (Fw[:, 0] == Fw[:, 2])).sum())
E = np.sort(np.concatenate([Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]]), axis=1)
E = E[E[:, 0] != E[:, 1]]
Eu, ecount = np.unique(E, axis=0, return_counts=True)
boundary = Eu[ecount == 1]
nonmanifold = int((ecount > 2).sum())
nv = int(weld.max()) + 1

# connected components by label propagation with pointer jumping
lab = np.arange(nv)
while True:
    a, b = lab[Eu[:, 0]], lab[Eu[:, 1]]
    m = np.minimum(a, b)
    new = lab.copy()
    np.minimum.at(new, Eu[:, 0], m)
    np.minimum.at(new, Eu[:, 1], m)
    new = new[new]
    new = new[new]
    if np.array_equal(new, lab):
        break
    lab = new
used = np.unique(Fw.ravel())
comp, comp_size = np.unique(lab[used], return_counts=True)
order = np.argsort(-comp_size)
comp, comp_size = comp[order], comp_size[order]
# where each welded vertex sits (first split vertex that maps to it)
wpos = np.zeros((nv, 3))
wpos[weld[::-1]] = V[::-1]


def region(p):
    """Coarse body region of a point on the normalised hero (feet on z=0, facing -Y, his right = -X)."""
    zf = (p[2] - lo[2]) / dims[2]
    xf = p[0] / dims[0]
    if abs(xf) > 0.22:
        return "gauntlet/forearm %s" % ("R" if xf < 0 else "L")
    if abs(xf) > 0.12 and zf > 0.70:
        return "upper arm/shoulder %s" % ("R" if xf < 0 else "L")
    if zf > 0.86:
        return "head/hair"
    if zf > 0.62:
        return "torso"
    if zf > 0.30:
        return "belt/skirt/sash"
    if zf > 0.08:
        return "legs/wraps"
    return "feet"


comp_info = []
for cid, n in zip(comp[:6], comp_size[:6]):
    pts = wpos[used[lab[used] == cid]]
    b0, b1 = pts.min(0), pts.max(0)
    comp_info.append({"verts": int(n), "bbox_min": [round(float(x), 3) for x in b0], "bbox_max": [round(float(x), 3) for x in b1],
                      "region": region((b0 + b1) / 2)})
small_regions = {}
for cid, n in zip(comp[1:], comp_size[1:]):
    if n < 0.01 * len(used):
        r = region(wpos[used[lab[used] == cid]].mean(0))
        small_regions[r] = small_regions.get(r, 0) + 1

# boundary loops (holes): components of the boundary-edge graph
holes = 0
hole_sizes = []
hole_regions = {}
if len(boundary):
    bl = np.arange(nv)
    while True:
        m = np.minimum(bl[boundary[:, 0]], bl[boundary[:, 1]])
        new = bl.copy()
        np.minimum.at(new, boundary[:, 0], m)
        np.minimum.at(new, boundary[:, 1], m)
        new = new[new]
        if np.array_equal(new, bl):
            break
        bl = new
    bverts = np.unique(boundary.ravel())
    hid, hs = np.unique(bl[bverts], return_counts=True)
    holes = int(len(hs))
    hole_sizes = sorted((int(x) for x in hs), reverse=True)[:10]
    hole_regions = {}
    for h in hid:
        r = region(wpos[bverts[bl[bverts] == h]].mean(0))
        hole_regions[r] = hole_regions.get(r, 0) + 1
nm_regions = {}
for e in Eu[ecount > 2]:
    r = region(wpos[e[0]])
    nm_regions[r] = nm_regions.get(r, 0) + 1

# silhouette proportions from the vertices (front = X/Z plane)
z = V[:, 2]
def width_at(z0, z1):
    sel = V[(z >= z0) & (z < z1)]
    return float(sel[:, 0].max() - sel[:, 0].min()) if len(sel) else 0.0


images = [{"name": im.name, "size": list(im.size)} for im in bpy.data.images if im.size[0] > 0]
metrics = {
    "source": SRC.replace("\\", "/"), "stem": STEM, "yaw_applied_deg": YAW,
    "raw_bounds_m": {"min": [round(float(x), 4) for x in raw_lo], "max": [round(float(x), 4) for x in raw_hi]},
    "normalised_height_m": HEIGHT, "scale_factor": round(float(s), 4),
    "dims_m": {"span_x": round(float(dims[0]), 3), "depth_y": round(float(dims[1]), 3), "height_z": round(float(dims[2]), 3)},
    "span_over_height": round(float(dims[0] / dims[2]), 3),
    "width_bands_m": {"%d-%d%%" % (p0, p1): round(width_at(lo[2] + dims[2] * p0 / 100, lo[2] + dims[2] * p1 / 100), 3)
                      for p0, p1 in ((0, 10), (10, 30), (30, 45), (45, 55), (55, 62), (62, 72), (72, 80), (80, 88), (88, 100))},
    "mesh_objects": len(meshes), "materials": len(bpy.data.materials), "images": images,
    "triangles": int(tris), "vertices_split": int(len(V)), "vertices_welded": int(len(used)),
    "degenerate_tris": degenerate, "components": int(len(comp_size)),
    "largest_components": [int(x) for x in comp_size[:8]], "component_details": comp_info,
    "small_components_by_region": small_regions, "holes_by_region": hole_regions, "nonmanifold_edges_by_region": nm_regions,
    "small_components_lt_1pct": int((comp_size < 0.01 * len(used)).sum()),
    "boundary_edges": int(len(boundary)), "boundary_loops_holes": holes, "largest_hole_loops_verts": hole_sizes,
    "nonmanifold_edges": nonmanifold,
}
print("[blockout] %d tris, %d welded verts, %d components (%s), %d boundary edges in %d loops, %d non-manifold edges"
      % (tris, len(used), len(comp_size), comp_size[:5].tolist(), len(boundary), holes, nonmanifold))

# ---- scene: lights, world, camera ---------------------------------------------------------------
world = bpy.data.worlds.new("w")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.20, 0.21, 0.23, 1.0)
bg.inputs["Strength"].default_value = 1.0
scene.world = world


def add_sun(name, energy, rot, color=(1, 1, 1)):
    ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
    ob.data.energy = energy
    ob.data.color = color
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    scene.collection.objects.link(ob)
    return ob


key_l = add_sun("key", 4.5, (50, 0, -35), (1.0, 0.96, 0.9))
fill_l = add_sun("fill", 1.6, (65, 0, 140), (0.85, 0.9, 1.0))
rim_l = add_sun("rim", 2.0, (-60, 0, 180), (1.0, 0.8, 0.6))

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.clip_start = 0.01
cam.data.clip_end = 200
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = False


def set_engine(kind):
    if kind == "eevee":   # kael variant: the lit renders use Cycles on the CPU (the GPU is shared), never EEVEE
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = int(os.environ.get("GF_CYCLES_SAMPLES", "24"))
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.use_denoising = True
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        if hasattr(scene.cycles, "denoising_use_gpu"):
            scene.cycles.denoising_use_gpu = False
        scene.cycles.max_bounces = 4
        scene.display_settings.display_device = "sRGB"
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "TEXTURE" if kind == "albedo" else "SINGLE"
        sh.single_color = (0.62, 0.58, 0.54) if kind == "clay" else (1, 1, 1)
        sh.show_cavity = kind == "clay"
        sh.cavity_type = "BOTH"
        sh.show_object_outline = False
        sh.show_shadows = False
        sh.background_type = "VIEWPORT"
        sh.background_color = (0.20, 0.21, 0.23)
        world.color = (0.20, 0.21, 0.23)      # a Workbench *render* takes its background from the world colour
        if kind in ("flat", "albedo"):
            sh.light = "FLAT"


def aim(direction, target, dist=40.0):
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")


def frame(pts, direction, pad=1.08):
    """Ortho scale + centre that fit pts seen along -direction."""
    d = Vector(direction).normalized()
    up = Vector((0, 0, 1))
    right = d.cross(up).normalized() if abs(d.z) < 0.999 else Vector((1, 0, 0))
    up2 = right.cross(d).normalized()
    R, U = np.array(right), np.array(up2)
    pr, pu = pts @ R, pts @ U
    c = ((pr.max() + pr.min()) / 2) * R + ((pu.max() + pu.min()) / 2) * U
    w, h = pr.max() - pr.min(), pu.max() - pu.min()
    return Vector(c), max(w, h) * pad, w, h


def render(path, res_x, res_y):
    scene.render.resolution_x, scene.render.resolution_y = res_x, res_y
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def az_dir(az_deg, elev_deg=0.0):
    a, e = math.radians(az_deg), math.radians(elev_deg)
    return (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))


# hero faces -Y; his left is +X. Camera azimuth 90 = his left side.
VIEWS = {"front": 0, "front34L": 45, "sideL": 90, "back": 180, "back34R": 225, "sideR": 270}

# one common ortho scale for the turnaround so all views share a scale
common = max(frame(V, az_dir(a))[1] for a in VIEWS.values())
for kind in ("eevee", "clay", "albedo"):
    set_engine(kind)
    tag = {"eevee": "tex", "clay": "clay", "albedo": "albedo"}[kind]
    for name, az in VIEWS.items():
        if kind == "albedo" and name not in ("front", "front34L", "back"):
            continue            # unlit base colour: enough to judge the baked palette against the concept
        d = az_dir(az, 5.0)
        c, _, _, _ = frame(V, d)
        c = Vector((c.x, c.y, (lo[2] + hi[2]) / 2))
        aim(d, c)
        cam.data.ortho_scale = common
        render(os.path.join(OUT, "%s_%s_%s.png" % (STEM, tag, name)), SIZE, SIZE)

# ---- close-ups ------------------------------------------------------------------------------------
H = dims[2]
parts = {
    "head": V[(V[:, 2] > lo[2] + 0.80 * H) & (np.abs(V[:, 0]) < 0.12 * dims[0])],
    "gauntletR": V[V[:, 0] < lo[0] + 0.30 * dims[0]],     # his right hand = -X
    "gauntletL": V[V[:, 0] > hi[0] - 0.30 * dims[0]],
    "legs": V[(V[:, 2] < lo[2] + 0.50 * H) & (np.abs(V[:, 0]) < 0.25 * dims[0])],
}
close_views = {"head": {"front": 0, "34L": 35, "side": 90}, "gauntletR": {"front": 0, "34": -35, "top": None},
               "gauntletL": {"front": 0, "34": 35}, "legs": {"front": 0, "34L": 35, "back": 180}}
# the head's side view is hidden behind the T-pose arm: clip everything nearer to the camera than
# the head core (ortho clip_start), so the close-up shows the head, not the gauntlet
head_core = V[(V[:, 2] > lo[2] + 0.86 * H) & (np.abs(V[:, 0]) < 0.07 * dims[0])]
clip_to = {("head", "side"): head_core}
for kind in ("eevee", "clay"):
    set_engine(kind)
    tag = "close" if kind == "eevee" else "closeclay"
    for part, pts in parts.items():
        if len(pts) < 50:
            continue
        for vname, az in close_views[part].items():
            d = (0.0, -0.25, 1.0) if az is None else az_dir(az, 8.0)
            core = clip_to.get((part, vname))
            c, sc, _, _ = frame(pts if core is None else core, d, 1.15 if core is None else 1.6)
            if core is None:
                aim(d, c, 20.0)
                cam.data.clip_start = 0.01
            else:
                near = float((core @ np.array(Vector(d).normalized())).max())
                aim(d, c + Vector(d).normalized() * near, 1.0)
                cam.data.clip_start = 0.97
            cam.data.ortho_scale = sc
            render(os.path.join(OUT, "%s_%s_%s_%s.png" % (STEM, tag, part, vname)), 640, 640)
cam.data.clip_start = 0.01

# ---- diagnostics: connected components in colour, and mid-plane sections ---------------------------
# largest component light grey, 2nd red, 3rd blue, 4th green, every smaller one yellow; the sections cut
# the mesh at its mid-depth / mid-width (ortho clip_start) to show interior shells and hidden gaps
palette = {0: (0.75, 0.75, 0.75), 1: (0.85, 0.15, 0.1), 2: (0.1, 0.35, 0.9), 3: (0.1, 0.7, 0.2)}
rank = {int(cid): i for i, cid in enumerate(comp)}
col_of_welded = np.tile(np.array([0.95, 0.8, 0.1]), (nv, 1))
for cid, i in rank.items():
    if i in palette:
        col_of_welded[lab == cid] = palette[i]
start = 0
for o in meshes:
    n = len(o.data.vertices)
    cols = np.concatenate([col_of_welded[weld[start:start + n]], np.ones((n, 1))], axis=1).astype(np.float32)
    attr = o.data.color_attributes.new("gf_components", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", cols.ravel())
    o.data.color_attributes.active_color = attr
    start += n
set_engine("clay")
scene.display.shading.color_type = "VERTEX"
scene.display.shading.show_cavity = False
for name, az, section in (("front", 0, False), ("back", 180, False), ("sectionFront", 0, True), ("sectionSide", 90, True)):
    d = Vector(az_dir(az, 0.0))
    c, sc, _, _ = frame(V, d, 1.06)
    c = Vector((c.x, c.y, (lo[2] + hi[2]) / 2))
    if section:
        aim(d, c, 1.0)                       # c sits on the mid-plane (depth 0 through the centred mesh)
        cam.data.clip_start = 1.0
    else:
        aim(d, c)
        cam.data.clip_start = 0.01
    cam.data.ortho_scale = common if az == 0 or az == 180 else sc
    render(os.path.join(OUT, "%s_diag_%s.png" % (STEM, name)), SIZE, SIZE)
cam.data.clip_start = 0.01

# ---- front silhouette for the concept IoU ----------------------------------------------------------
set_engine("flat")
scene.display.shading.single_color = (1, 1, 1)
scene.render.film_transparent = True
d = az_dir(0, 0)
c, sc, w, h = frame(V, d, 1.0)
aim(d, c)
cam.data.ortho_scale = sc
res = 1200
render(os.path.join(OUT, "%s_frontsil.png" % STEM), res if w >= h else int(res * w / h), res if h >= w else int(res * h / w))
scene.render.film_transparent = False

# ---- in-game camera: ortho, 55 deg pitch, yaw 0, true 1080p pixel scale ----------------------------
floor = bpy.data.objects.new("floor", bpy.data.meshes.new("floor"))
floor.data.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.045, 0.035, 0.03, 1)
floor.data.materials.append(fm)
scene.collection.objects.link(floor)
key_l.rotation_euler = (math.radians(40), 0, math.radians(-30))
game_dir = (0.0, -math.cos(math.radians(GAME_PITCH)), math.sin(math.radians(GAME_PITCH)))
px = 256
target = (0, 0, H * 0.5)
for vh in GAME_VIEW_HEIGHTS:
    for look in ("tex", "sil", "tex34"):
        if look == "sil":
            set_engine("flat")
            scene.display.shading.single_color = (0.02, 0.02, 0.02)
            scene.display.shading.background_color = (0.55, 0.5, 0.45)
            world.color = (0.55, 0.5, 0.45)
            floor.hide_render = True
        else:
            set_engine("eevee")
            floor.hide_render = False
        root.rotation_euler = Euler((0, 0, math.radians(YAW + (35 if look == "tex34" else 0))))
        bpy.context.view_layer.update()
        aim(game_dir, target)
        cam.data.ortho_scale = vh * px / SCREEN_H     # FixedVertical: vh metres = 1080 px
        render(os.path.join(OUT, "%s_ingame_%d_%s.png" % (STEM, int(vh), look)), px, px)
root.rotation_euler = Euler((0, 0, math.radians(YAW)))
floor.hide_render = True
metrics["ingame"] = {"pitch_deg": GAME_PITCH, "view_heights_m": list(GAME_VIEW_HEIGHTS), "screen_px": SCREEN_H,
                     "hero_px_tall_estimate": {str(int(vh)): round(SCREEN_H * (H * math.cos(math.radians(GAME_PITCH)) + dims[1] * math.sin(math.radians(GAME_PITCH))) / vh, 1)
                                               for vh in GAME_VIEW_HEIGHTS}}
with open(os.path.join(OUT, "%s_metrics.json" % STEM), "w", newline="\n") as f:
    json.dump(metrics, f, indent=1)
    f.write("\n")
print("[blockout] wrote renders + metrics to", OUT)
