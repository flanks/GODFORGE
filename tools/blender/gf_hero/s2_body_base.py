"""Stage 2, step 2: the base body topology - MakeHuman hm08 (CC0) through MPFB, T-posed and reduced to game
density with its edge loops intact.

Why hm08: it is a production human topology (quad-only, closed, edge loops around every joint, eye and
mouth loops) released as CC0 in 2020 (header of MPFB's data/3dobjs/base.obj). MPFB (GPL-3.0 add-on,
installed in the user's Blender) is used here only as a TOOL to load it, apply the CC0 macro targets and
the CC0 game_engine rig weights for the T-pose; no MPFB code or data file ships. The shape of Brax comes
from the fit to the approved stage-1 sculpt reference (s2_body_fit.py), not from MakeHuman.

Steps:
  1. MPFB create_human (male, max muscle, heavy, ideal proportions, tall), macro targets baked;
  2. game_engine rig with its weights: upper arm, forearm, hand and fingers aimed straight along +-X
     (T-pose, like the approved concept), armature applied, rig deleted;
  3. landmarks recorded (joint heads/tails, eye centres from the helper joint cubes, skull top, nose
     tip, heels) for the landmark warp in s2_body_fit.py;
  4. helpers deleted (eyeballs, lashes, teeth, tongue, tights/skirt/hair proxies, joint cubes);
  5. topology reduced 4x with two un-subdivide passes (vertex checkerboard twice = every second loop in
     both directions), then made symmetric: the reduction has one parity seam, so the clean half
     (x <= 0, his right) is kept, its cut is snapped to x = 0 and mirrored; triangle pairs are joined
     back into quads.

  blender -b -P tools/blender/gf_hero/s2_body_base.py -- <out.blend> <landmarks.json> [--config <stage2_fit.json>]

The hero config's "base" block sets the MPFB macros and any CC0 MakeHuman targets (face shape: brow,
jaw, nose...) applied before the targets are baked.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from s2lib import get_co, log, mesh_stats, opt, read_json, reset_scene, save_blend, script_args, select_only, write_json  # noqa: E402

argv = script_args(__doc__)
if len(argv) < 2:
    raise SystemExit(__doc__)
OUT, LM_OUT = (os.path.abspath(a) for a in argv[:2])

from bl_ext.blender_org.mpfb.services.humanservice import HumanService  # noqa: E402
from bl_ext.blender_org.mpfb.services.targetservice import TargetService  # noqa: E402

CONFIG = opt(argv, "--config", None, str)
base_cfg = read_json(CONFIG).get("base", {}) if CONFIG else {}
MACRO = base_cfg.get("macro", {"gender": 1.0, "age": 0.5, "muscle": 1.0, "weight": 0.75, "proportions": 1.0, "height": 1.0})
TARGETS = {k: v for k, v in base_cfg.get("targets", {}).items() if not k.startswith("_")}

scene = reset_scene()
macro = TargetService.get_default_macro_info_dict()
macro.update(MACRO)
body = HumanService.create_human(mask_helpers=False, detailed_helpers=True, extra_vertex_groups=True,
                                 feet_on_ground=True, scale=0.1, macro_detail_dict=macro)
rig = HumanService.add_builtin_rig(body, "game_engine", import_weights=True)
log("MPFB human", body.name, len(body.data.vertices), "verts; rig", len(rig.data.bones), "bones")

# ---- extra CC0 targets (face shape), then bake everything -------------------------------------------
for tname, w in TARGETS.items():
    path = TargetService.target_full_path(tname)
    if path is None:
        raise SystemExit("MakeHuman target not found: " + tname)
    TargetService.load_target(body, path, weight=float(w), name=tname)
log("targets applied:", TARGETS)
select_only(body)
body.shape_key_add(name="mix", from_mix=True)
co = np.empty(len(body.data.vertices) * 3)
body.data.shape_keys.key_blocks["mix"].data.foreach_get("co", co)
body.shape_key_clear()
body.data.vertices.foreach_set("co", co)
body.data.update()

# ---- T-pose -----------------------------------------------------------------------------------------
select_only(rig)
bpy.ops.object.mode_set(mode="POSE")


def aim_bone(name, target_dir):
    pb = rig.pose.bones[name]
    bpy.context.view_layer.update()
    m = pb.matrix.copy()
    head = m.to_translation()
    q = (pb.tail - pb.head).normalized().rotation_difference(Vector(target_dir).normalized())
    pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ m
    bpy.context.view_layer.update()


for side, sx in (("l", 1), ("r", -1)):
    for b in ("upperarm", "lowerarm", "hand"):
        aim_bone("%s_%s" % (b, side), (sx, 0, 0))
    for f in ("index", "middle", "ring", "pinky"):
        for i in (1, 2, 3):
            aim_bone("%s_%02d_%s" % (f, i, side), (sx, 0, 0))
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.update()
joints = {pb.name: {"head": list(rig.matrix_world @ pb.head), "tail": list(rig.matrix_world @ pb.tail)} for pb in rig.pose.bones}
select_only(body)
for m in list(body.modifiers):
    if m.type == "ARMATURE":
        bpy.ops.object.modifier_apply(modifier=m.name)
bpy.data.objects.remove(rig)

# ---- landmarks from the helpers and the surface (before the helpers go) --------------------------------
me = body.data
co = get_co(me)
vg = {g.name: g.index for g in body.vertex_groups}


def group_verts(name):
    gi = vg[name]
    return np.array([v.index for v in me.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)], dtype=np.int64)


body_idx = group_verts("body")
lm = {"joints": joints}
for side in ("l", "r"):
    ev = co[group_verts("helper-%s-eye" % side)]
    lm["eye_%s" % side] = ev.mean(0).tolist()
    lm["eye_radius"] = float(np.linalg.norm(ev - ev.mean(0), axis=1).max())
bc = co[body_idx]
lm["skull_top"] = bc[np.argmax(bc[:, 2])].tolist()
head = bc[bc[:, 2] > joints["head"]["head"][2]]
lm["nose_tip"] = head[np.argmin(head[:, 1])].tolist()
ear = co[group_verts("ears")]
lm["ear_l"] = ear[np.argmax(ear[:, 0])].tolist()
lm["ear_r"] = ear[np.argmin(ear[:, 0])].tolist()
eye_z = lm["eye_l"][2]
band = head[np.abs(head[:, 2] - (eye_z + 0.02)) < 0.01]
lm["skull_back"] = band[np.argmax(band[:, 1])].tolist()
prof = bc[(np.abs(bc[:, 0]) < 0.004) & (bc[:, 1] < lm["nose_tip"][1] + 0.12) & (bc[:, 2] < lm["nose_tip"][2]) & (bc[:, 2] > lm["nose_tip"][2] - 0.25)]
# chin: the most forward point of the front profile below the mouth (lowest third of nose->throat)
low = prof[prof[:, 2] < lm["nose_tip"][2] - 0.09]
lm["chin"] = low[np.argmin(low[:, 1])].tolist()
for side, sx in (("l", 1), ("r", -1)):
    foot = bc[(bc[:, 2] < 0.12) & (bc[:, 0] * sx > 0)]
    lm["heel_%s" % side] = foot[np.argmax(foot[:, 1])].tolist()
    lm["toe_%s" % side] = foot[np.argmin(foot[:, 1])].tolist()
lm["height"] = float(bc[:, 2].max())

# ---- keep the body, reduce, symmetrise -----------------------------------------------------------------
keep = np.zeros(len(me.vertices), bool)
keep[body_idx] = True
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(~keep)[0]], context="VERTS")
for v in bm.verts:
    if abs(v.co.x) < 2e-4:
        v.co.x = 0.0
bm.to_mesh(me)
bm.free()
for g in list(body.vertex_groups):
    if g.name not in ("scalp", "lips", "ears", "nipple", "fingernails", "toenails"):
        body.vertex_groups.remove(g)
full = mesh_stats(body)
log("hm08 body", full["faces"], "quads", full["triangles"], "tris")

m = body.modifiers.new("unsubdivide", "DECIMATE")
m.decimate_type = "UNSUBDIV"
m.iterations = 2
bpy.ops.object.modifier_apply(modifier=m.name)

bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x > 1e-5], context="VERTS")
far = []
for v in bm.verts:
    if v.is_boundary:
        if v.co.x > -0.045:
            v.co.x = 0.0
        else:
            far.append(tuple(v.co))
if far:
    log("WARNING boundary verts left off the centre plane:", far)
# a face lying flat in the mirror plane (the navel pit after the snap) would be doubled by the mirror
flat = [f for f in bm.faces if all(abs(v.co.x) < 1e-6 for v in f.verts)]
log("faces flat in the mirror plane removed:", len(flat))
bmesh.ops.delete(bm, geom=flat, context="FACES_ONLY")
bmesh.ops.mirror(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], merge_dist=1e-5, axis="X")
bmesh.ops.remove_doubles(bm, verts=[v for v in bm.verts if abs(v.co.x) < 1e-6], dist=1e-5)
# a centre-plane snap can fold a face onto its neighbour: dissolve faces that became degenerate and edges
# shared by more than two faces
bad = [f for f in bm.faces if f.calc_area() < 1e-9]
if bad:
    bmesh.ops.delete(bm, geom=bad, context="FACES")
nm = [e for e in bm.edges if len(e.link_faces) > 2]
log("non-manifold edges after mirror:", len(nm), [tuple(round(c, 3) for c in ((e.verts[0].co + e.verts[1].co) / 2)) for e in nm][:6])
# the navel pit folds into a fin on the centre plane: keep the two largest faces of such an edge
extra = set()
for e in nm:
    fs = sorted(e.link_faces, key=lambda f: f.calc_area(), reverse=True)
    extra.update(fs[2:])
bmesh.ops.delete(bm, geom=list(extra), context="FACES")
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
holes = [e for e in bm.edges if e.is_boundary]
if holes:
    bmesh.ops.holes_fill(bm, edges=holes, sides=4)
log("removed %d fin faces, %d loose verts, filled %d hole edges" % (len(extra), len(loose), len(holes)))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me)
bm.free()
select_only(body)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.tris_convert_to_quads(face_threshold=math.radians(60), shape_threshold=math.radians(70))
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")
body.name = "BODY_base_hm08"
me.name = "BODY_base_hm08"
for p in me.polygons:
    p.use_smooth = True
st = mesh_stats(body)
log("reduced body", st)
lm["reduced_stats"] = st
lm["hm08_full_stats"] = {k: full[k] for k in ("faces", "triangles", "quads")}
lm["macro"] = MACRO
lm["targets"] = TARGETS
write_json(LM_OUT, lm)
save_blend(OUT)
