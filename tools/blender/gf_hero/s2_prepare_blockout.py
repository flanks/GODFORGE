"""Stage 2, step 1: turn the picked stage-1 TRELLIS.2 blockout into the clean sculpt reference that the
production mesh is fitted to (and that an artist would open to retopologise by hand).

Adapted from Ashen Covenant tools/blender/ac_humanoid_enemy/03_build_game_mesh.py (scale / centre /
floor, weld UV-seam duplicates, drop micro-fragments, rename the generator's images). GODFORGE
changes: the hero is scaled to its in-game height (not a fixed factor), fragments are dropped by
share of the vertex count, the base-colour texture is sampled into a per-corner colour attribute
(`src_col`, used by the fit to tell hair/beard/wraps from skin; it is never shipped), and the
approved concept is placed behind the mesh as a front reference image.

  blender -b -P tools/blender/gf_hero/s2_prepare_blockout.py -- <blockout.glb> <out.blend> <concept.png>
          [--height 2.2] [--report <json>]

Result (Blender conventions: Z up, faces -Y, +X = his left, feet on z = 0, transforms applied):
  REF_blockout          the cleaned TRELLIS mesh (SCULPT REFERENCE ONLY - never shipped)
  REF_concept_front     image empty with the approved concept, scaled to the same height, at y = +0.9
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

from s2lib import (apply_transforms, connected_parts, get_co, get_collection, log, mesh_stats,  # noqa: E402
                       move_to_collection, rel, reset_scene, save_blend, set_co, write_json)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) < 3:
    raise SystemExit(__doc__)
SRC, OUT, CONCEPT = (os.path.abspath(a) for a in argv[:3])


def opt(name, default, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


HEIGHT = opt("--height", 2.2)
REPORT = opt("--report", None, str)
MIN_PART_SHARE = 0.01          # connected pieces below 1 % of the vertices are generator crumbs
# The approved concept (Brax's 1536x1024 front by default): figure from crown y=28 px to sole y=995 px, centred at
# x=768 px. Another hero's concept passes --concept-fig <crown_px>,<sole_px>,<centre_x_px>.
_cf = [float(v) for v in opt("--concept-fig", "28,995,768", str).split(",")]
CONCEPT_FIG = {"crown_px": _cf[0], "sole_px": _cf[1], "centre_x_px": _cf[2]}

report = {"source": rel(SRC), "height_m": HEIGHT}
scene = reset_scene()
bpy.ops.import_scene.gltf(filepath=SRC)
meshes = [o for o in scene.objects if o.type == "MESH"]
if len(meshes) != 1:
    raise SystemExit("expected one mesh in %s, got %d" % (SRC, len(meshes)))
ob = meshes[0]
for o in list(scene.objects):
    o.select_set(o is ob)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
for o in list(scene.objects):
    if o is not ob:
        bpy.data.objects.remove(o)
apply_transforms(ob)
me = ob.data
report["raw"] = {"vertices_split": len(me.vertices), "triangles": sum(len(p.vertices) - 2 for p in me.polygons)}

# ---- sample the base-colour texture into a corner colour (before welding moves loops around) ----
mat = me.materials[0]
base_img = None
for n in mat.node_tree.nodes:
    if n.type == "BSDF_PRINCIPLED":
        link = n.inputs["Base Color"].links
        if link and link[0].from_node.type == "TEX_IMAGE":
            base_img = link[0].from_node.image
if base_img is None:
    raise SystemExit("no base colour image on " + mat.name)
w, h = base_img.size
px = np.empty(w * h * 4, dtype=np.float32)
base_img.pixels.foreach_get(px)
px = px.reshape(h, w, 4)
uv = np.empty(len(me.loops) * 2, dtype=np.float32)
me.uv_layers.active.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
xi = np.clip((uv[:, 0] % 1.0) * w, 0, w - 1).astype(np.int64)
yi = np.clip((uv[:, 1] % 1.0) * h, 0, h - 1).astype(np.int64)
col = px[yi, xi].copy()          # linear (image pixels are scene-linear for sRGB images)
col[:, 3] = 1.0
attr = me.color_attributes.new("src_col", "FLOAT_COLOR", "CORNER")
attr.data.foreach_set("color", col.ravel())
del px
log("sampled", base_img.name, "%dx%d into src_col" % (w, h))

# ---- normalise: height, centre, feet on the floor ------------------------------------------------
co = get_co(me)
lo, hi = co.min(0), co.max(0)
s = HEIGHT / (hi[2] - lo[2])
co = (co - np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])) * s
set_co(me, co)
report["scale_factor"] = round(float(s), 5)

# ---- weld the glTF's UV-seam splits, drop crumbs --------------------------------------------------
bm = bmesh.new()
bm.from_mesh(me)
v0 = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=HEIGHT * 1e-6)
v_weld = len(bm.verts)
parts = sorted(connected_parts(bm), key=len, reverse=True)
total = sum(len(p) for p in parts)
kept, dropped = [], []
for p in parts:
    (kept if len(p) >= MIN_PART_SHARE * total else dropped).append(p)
drop_verts = [v for p in dropped for v in p]

bmesh.ops.delete(bm, geom=drop_verts, context="VERTS")
report["weld"] = {"verts_before": v0, "verts_after": v_weld}
report["parts_kept"] = [len(p) for p in kept]
report["parts_dropped"] = {"count": len(dropped), "verts": len(drop_verts), "largest": max((len(p) for p in dropped), default=0)}
bm.to_mesh(me)
bm.free()
me.update()
log("kept parts", report["parts_kept"], "dropped", report["parts_dropped"])

co = get_co(me)
lo, hi = co.min(0), co.max(0)
co[:, 2] -= lo[2]
set_co(me, co)
lo, hi = co.min(0), co.max(0)
report["bounds_m"] = {"min": [round(float(x), 4) for x in lo], "max": [round(float(x), 4) for x in hi]}
report["span_over_height"] = round(float((hi[0] - lo[0]) / (hi[2] - lo[2])), 4)

ob.name = "REF_blockout"
me.name = "REF_blockout"
mat.name = "MAT_REF_blockout_trellis"
for img in bpy.data.images:
    img.name = {"Image_0": "T_REF_blockout_basecolor", "Image_1": "T_REF_blockout_orm", "Image_2": "T_REF_blockout_normal"}.get(img.name, img.name)
    if img.packed_file is None and img.source == "FILE":
        img.pack()
for p in me.polygons:
    p.use_smooth = True
ref = get_collection("REF_sculpt_reference")
move_to_collection(ob, ref)
ob.hide_select = True
report["stats"] = mesh_stats(ob)

# ---- concept image behind the hero, same scale ------------------------------------------------------
img = bpy.data.images.load(CONCEPT)
img.pack()
iw, ih = img.size
m_per_px = HEIGHT / (CONCEPT_FIG["sole_px"] - CONCEPT_FIG["crown_px"])
emp = bpy.data.objects.new("REF_concept_front", None)
emp.empty_display_type = "IMAGE"
emp.data = img
emp.empty_display_size = max(iw, ih) * m_per_px
emp.empty_image_offset = (-0.5, -0.5)
emp.rotation_euler = (np.pi / 2, 0, 0)
emp.location = ((iw / 2 - CONCEPT_FIG["centre_x_px"]) * m_per_px, 0.9, (CONCEPT_FIG["sole_px"] - ih / 2) * m_per_px)
emp.empty_image_depth = "BACK"
emp.show_empty_image_perspective = False
ref.objects.link(emp)
report["concept"] = {"path": rel(CONCEPT), "m_per_px": round(m_per_px, 6)}

scene.unit_settings.length_unit = "METERS"
save_blend(OUT)
report["out"] = rel(OUT)
if REPORT:
    write_json(REPORT, report)
log("done", report["stats"])
