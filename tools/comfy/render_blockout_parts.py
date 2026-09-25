"""Per-hero close-ups, cut sections and region metrics for a raw TRELLIS.2 blockout (stage 1).

A Blender script (despite living in tools/comfy/, next to blockout_sheets.py, which consumes its
output). It complements tools/blender/gf_hero/render_blockout.py, whose close-ups are fixed to
Brax's parts (head, two gauntlets, skirt + legs): here the parts, views and body regions come from
a per-hero JSON spec (art/characters/<key>/blockout_views.json), so a hero with a cannon arm, a
cape or pauldrons gets the views its silhouette needs. The import and the normalisation are the
same as render_blockout.py (same height, yaw, lights, engines and camera conventions), so the
files land beside render_blockout.py's output with the same naming and the same scale.

  blender -b -P tools/comfy/render_blockout_parts.py -- <in.glb> <out_dir> <stem> <views.json>
          [--height H] [--yaw DEG] [--size 640]

  --height  defaults to the spec's height_m (else 2.2); pass the same value to render_blockout.py
  --yaw     extra rotation about +Z so the hero faces Blender -Y (as in render_blockout.py)

Spec (see art/characters/valdris/blockout_views.json):
  parts.<part>.box    {"x": [a, b], "y": [a, b], "z": [a, b]}: x / y as fractions of span / depth
                      from the bbox centre (-0.5..0.5), z as a fraction of height from the feet
  parts.<part>.views  [{"name", "az", "el"} | {"name", "dir": [x, y, z]}] plus optional
                      "clip": "core" with "core": {box}  (render only what lies behind the nearest
                      point of the core, e.g. the head seen past a pauldron), or
                      "section_x" / "section_y" / "section_z": f  (cut the mesh at that fraction and
                      look at the cut face; the camera direction must point to the removed side)
  regions             ordered [{"name", "x", "z"}] boxes; each welded vertex goes to the first match.
                      Components, open boundary loops and non-manifold edges are counted per region.

Writes into <out_dir>:
  <stem>_close_<part>_<view>.png, <stem>_closeclay_<part>_<view>.png   (EEVEE lit / Workbench clay)
  <stem>_parts_metrics.json   hero dims at the spec height, per-region topology, per-part bboxes
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
if len(argv) < 4:
    raise SystemExit(__doc__)
SRC, OUT, STEM, SPEC_PATH = os.path.abspath(argv[0]), os.path.abspath(argv[1]), argv[2], os.path.abspath(argv[3])
SPEC = json.load(open(SPEC_PATH, encoding="utf-8"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rel_root(path):
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:          # another drive
        return path.replace("\\", "/")


def opt(name, default, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


HEIGHT = opt("--height", float(SPEC.get("height_m", 2.2)))
YAW = opt("--yaw", 0.0)
SIZE = opt("--size", 640, int)
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in scene.objects if o.type == "MESH"]
if not meshes:
    raise SystemExit("no mesh in " + SRC)

# ---- normalise exactly like render_blockout.py: yaw, feet on the floor, centred, HEIGHT tall ----
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
print("[parts] %s: normalised to %.2f m, bounds %.2f x %.2f x %.2f" % (os.path.basename(SRC), HEIGHT, *dims))


def frac(p):
    """World points -> spec fractions (x, y from the centre in span/depth units, z from the feet)."""
    return np.stack([p[:, 0] / dims[0], p[:, 1] / dims[1], (p[:, 2] - lo[2]) / dims[2]], axis=1)


VF = frac(V)


def in_box(fr, box):
    sel = np.ones(len(fr), bool)
    for i, k in enumerate("xyz"):
        if k in box:
            a, b = box[k]
            sel &= (fr[:, i] >= a) & (fr[:, i] <= b)
    return sel


# ---- region topology (vertices welded by position: glTF splits them at UV seams) ----------------
faces_all, offset, tris = [], 0, 0
for o in meshes:
    me = o.data
    me.calc_loop_triangles()
    t = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", t)
    faces_all.append(t.reshape(-1, 3) + offset)
    offset += len(me.vertices)
    tris += len(me.loop_triangles)
F = np.concatenate(faces_all)
_, weld = np.unique(np.round(V / (HEIGHT * 1e-6)).astype(np.int64), axis=0, return_inverse=True)
weld = weld.ravel()
Fw = weld[F]
E = np.sort(np.concatenate([Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]]), axis=1)
E = E[E[:, 0] != E[:, 1]]
Eu, ecount = np.unique(E, axis=0, return_counts=True)
nv = int(weld.max()) + 1
wpos = np.zeros((nv, 3))
wpos[weld[::-1]] = V[::-1]
WF = frac(wpos)


def propagate(edges, n):
    lab = np.arange(n)
    while True:
        m = np.minimum(lab[edges[:, 0]], lab[edges[:, 1]])
        new = lab.copy()
        np.minimum.at(new, edges[:, 0], m)
        np.minimum.at(new, edges[:, 1], m)
        new = new[new]
        new = new[new]
        if np.array_equal(new, lab):
            return lab
        lab = new


lab = propagate(Eu, nv)
used = np.unique(Fw.ravel())
comp, comp_size = np.unique(lab[used], return_counts=True)
order = np.argsort(-comp_size)
comp, comp_size = comp[order], comp_size[order]

regions = SPEC.get("regions") or [{"name": "all", "x": [-0.5, 0.5], "z": [0, 1]}]
region_of = np.full(nv, len(regions) - 1)
unassigned = np.ones(nv, bool)
for i, r in enumerate(regions):
    sel = unassigned & in_box(WF, r)
    region_of[sel] = i
    unassigned &= ~sel
names = [r["name"] for r in regions]

boundary = Eu[ecount == 1]
holes_by_region, hole_sizes, largest_holes = {}, [], []
if len(boundary):
    bl = propagate(boundary, nv)
    bverts = np.unique(boundary.ravel())
    hid, hs = np.unique(bl[bverts], return_counts=True)
    hole_sizes = sorted((int(x) for x in hs), reverse=True)[:10]
    for h in hid:
        c = WF[bverts[bl[bverts] == h]].mean(0)
        r = next((n for n, rr in zip(names, regions) if in_box(c[None], rr)[0]), names[-1])
        holes_by_region[r] = holes_by_region.get(r, 0) + 1
    for h in hid[np.argsort(-hs)][:5]:
        pts = wpos[bverts[bl[bverts] == h]]
        c = WF[bverts[bl[bverts] == h]].mean(0)
        largest_holes.append({"verts": int(len(pts)), "region": next((n for n, rr in zip(names, regions) if in_box(c[None], rr)[0]), names[-1]),
                              "centre_m": [round(float(x), 3) for x in pts.mean(0)],
                              "extent_m": round(float(np.ptp(pts, axis=0).max()), 3)})
nm = Eu[ecount > 2]
nm_by_region = {}
for i, n in enumerate(names):
    k = int((region_of[nm[:, 0]] == i).sum()) if len(nm) else 0
    if k:
        nm_by_region[n] = k
comp_details = []
for cid, n in zip(comp[:8], comp_size[:8]):
    idx = used[lab[used] == cid]
    fr = WF[idx]
    counts = np.bincount(region_of[idx], minlength=len(regions))
    share = {names[i]: round(float(c) / len(idx), 3) for i, c in enumerate(counts) if c >= 0.02 * len(idx)}
    comp_details.append({"verts": int(n), "bbox_frac_min": [round(float(x), 3) for x in fr.min(0)],
                         "bbox_frac_max": [round(float(x), 3) for x in fr.max(0)], "regions": share})
small = {}
for cid, n in zip(comp[1:], comp_size[1:]):
    if n < 0.01 * len(used):
        c = WF[used[lab[used] == cid]].mean(0)
        r = next((nn for nn, rr in zip(names, regions) if in_box(c[None], rr)[0]), names[-1])
        small[r] = small.get(r, 0) + 1

def height_bands():
    """Per 5 % height band: full width (x) and depth (y), and the depth and front of the core
    (|x| < 0.15 span, i.e. without the arms), in metres (-Y is the front)."""
    out = {}
    for b in range(0, 100, 5):
        sel = (VF[:, 2] >= b / 100) & (VF[:, 2] <= (b + 5) / 100)
        core = sel & (np.abs(VF[:, 0]) < 0.15)
        out["%02d-%02d%%" % (b, b + 5)] = {
            "width": round(float(np.ptp(V[sel, 0])), 3) if sel.any() else 0.0,
            "depth": round(float(np.ptp(V[sel, 1])), 3) if sel.any() else 0.0,
            "core_depth": round(float(np.ptp(V[core, 1])), 3) if core.any() else 0.0,
            "core_front_y": round(float(V[core, 1].min()), 3) if core.any() else None}
    return out


metrics = {
    "source": SRC.replace("\\", "/"), "stem": STEM, "spec": rel_root(SPEC_PATH),
    "height_m": HEIGHT, "yaw_applied_deg": YAW,
    "dims_m": {"span_x": round(float(dims[0]), 3), "depth_y": round(float(dims[1]), 3), "height_z": round(float(dims[2]), 3)},
    "span_over_height": round(float(dims[0] / dims[2]), 3),
    "triangles": int(tris), "vertices_welded": int(len(used)), "components": int(len(comp_size)),
    "largest_components": [int(x) for x in comp_size[:8]], "component_details": comp_details,
    "small_components_by_region": small, "boundary_loops_holes": int(sum(holes_by_region.values())),
    "largest_hole_loops_verts": hole_sizes, "largest_holes": largest_holes, "holes_by_region": holes_by_region,
    "nonmanifold_edges": int(len(nm)), "nonmanifold_edges_by_region": nm_by_region,
    "regions": regions, "parts": {},
    "bands": height_bands(),
}
print("[parts] %d components %s, %d holes %s, %d non-manifold edges"
      % (len(comp_size), comp_size[:5].tolist(), metrics["boundary_loops_holes"], holes_by_region, len(nm)))

# ---- scene: the same lights, world and engines as render_blockout.py -------------------------------
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


add_sun("key", 4.5, (50, 0, -35), (1.0, 0.96, 0.9))
add_sun("fill", 1.6, (65, 0, 140), (0.85, 0.9, 1.0))
add_sun("rim", 2.0, (-60, 0, 180), (1.0, 0.8, 0.6))

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
    if kind == "eevee":
        scene.render.engine = "BLENDER_EEVEE"
        scene.display_settings.display_device = "sRGB"
    else:
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "SINGLE"
        sh.single_color = (0.62, 0.58, 0.54)
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.show_object_outline = False
        sh.show_shadows = False
        sh.show_backface_culling = False
        sh.background_type = "VIEWPORT"
        sh.background_color = (0.20, 0.21, 0.23)
        world.color = (0.20, 0.21, 0.23)


def aim(direction, target, dist=40.0):
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")


def frame(pts, direction, pad=1.12):
    d = Vector(direction).normalized()
    up = Vector((0, 0, 1))
    right = d.cross(up).normalized() if abs(d.z) < 0.999 else Vector((1, 0, 0))
    up2 = right.cross(d).normalized()
    R, U = np.array(right), np.array(up2)
    pr, pu = pts @ R, pts @ U
    c = ((pr.max() + pr.min()) / 2) * R + ((pu.max() + pu.min()) / 2) * U
    return Vector(c), max(pr.max() - pr.min(), pu.max() - pu.min()) * pad


def az_dir(az_deg, elev_deg=0.0):
    a, e = math.radians(az_deg), math.radians(elev_deg)
    return (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))


def render(path):
    scene.render.resolution_x = scene.render.resolution_y = SIZE
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


plan = []
for part, spec in SPEC["parts"].items():
    sel = in_box(VF, spec["box"])
    pts = V[sel]
    if len(pts) < 50:
        print("[parts] %s: only %d vertices in its box, skipped" % (part, len(pts)))
        continue
    metrics["parts"][part] = {"verts": int(sel.sum()), "bbox_m_min": [round(float(x), 3) for x in pts.min(0)],
                              "bbox_m_max": [round(float(x), 3) for x in pts.max(0)]}
    for view in spec["views"]:
        d = Vector(view["dir"]).normalized() if "dir" in view else Vector(az_dir(view.get("az", 0), view.get("el", 0)))
        if view.get("clip") == "core":
            core = V[in_box(VF, view["core"])]
            c, sc = frame(core, d, 1.6)
            near = float((core @ np.array(d)).max())
            plan.append((part, view["name"], d, c + d * near, 1.0, 0.97, sc))
            continue
        c, sc = frame(pts, d)
        cut = [(k, view["section_" + k]) for k in "xyz" if "section_" + k in view]
        if cut:
            k, f = cut[0]
            i = "xyz".index(k)
            p = np.zeros(3)
            p[i] = f * dims[i] + (lo[2] if k == "z" else 0.0)
            plane_depth = float(np.array(d) @ p)
            plan.append((part, view["name"], d, c + d * plane_depth, 1.0, 1.0, sc))
        else:
            plan.append((part, view["name"], d, c, 20.0, 0.01, sc))

for kind in ("eevee", "clay"):
    set_engine(kind)
    tag = "close" if kind == "eevee" else "closeclay"
    for part, vname, d, target, dist, clip, sc in plan:
        aim(d, target, dist)
        cam.data.clip_start = clip
        cam.data.ortho_scale = sc
        render(os.path.join(OUT, "%s_%s_%s_%s.png" % (STEM, tag, part, vname)))
cam.data.clip_start = 0.01

with open(os.path.join(OUT, "%s_parts_metrics.json" % STEM), "w", newline="\n") as f:
    json.dump(metrics, f, indent=1)
    f.write("\n")
print("[parts] wrote %d close-ups x2 + parts metrics to %s" % (len(plan), OUT))
