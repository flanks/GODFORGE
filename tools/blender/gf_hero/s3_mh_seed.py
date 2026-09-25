"""Stage 3, step 2: the MakeHuman CC0 skin weights as a seed for the hero's BODY (headless Blender + MPFB as a tool).

  blender -b -P tools/blender/gf_hero/s3_mh_seed.py -- <key>

The hero body is the MakeHuman hm08 base mesh (CC0) reduced by s2_body_base.py and fitted by s2_body_fit.py. The
fit never reorders vertices: BODY vertex i (i < the reduced base count) IS vertex i of work/<key>_s2_body_base.blend
(checked here: the base edges must survive in BODY). The weights MakeHuman ships for its game_engine rig
(MPFB data/rigs/standard/weights.game_engine.json, licence CC0) are keyed to the full hm08 mesh, so:

  1. MPFB builds the same human as s2_body_base.py (same macros and CC0 targets from stage2_fit.json "base") with
     the game_engine rig and its weights, T-posed exactly the same way (aim upper arm, lower arm, hand and the
     finger chains along +-X), armature applied: the full-res hm08 in the reduced base's space, with weights;
  2. each reduced-base vertex is matched to its hm08 vertex (the reduction only keeps vertices, so the match is
     exact up to float noise; the report records the largest distance);
  3. the game_engine bone names map onto GF_Hero_v1: pelvis, spine_01..03, neck_01 -> neck, head, clavicle,
     upperarm, lowerarm, hand, the 15 finger bones, thigh, calf -> shin, foot, ball -> toe (Root drops out);
  4. writes work/<key>_s3_mh_seed.npz (bones, weights for the base vertices, the base vertex count) and
     reports/stage3/mh_seed.json.

MPFB (GPL add-on in the user's Blender) is only used as a tool here; no MPFB code or data file is copied or shipped.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import get_co, log, read_json, reset_scene, script_args, select_only, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
P = hero_paths(KEY)

from bl_ext.blender_org.mpfb.services.humanservice import HumanService  # noqa: E402
from bl_ext.blender_org.mpfb.services.targetservice import TargetService  # noqa: E402

base_cfg = read_json(P["fit"]).get("base", {})
MACRO = base_cfg.get("macro", {"gender": 1.0, "age": 0.5, "muscle": 1.0, "weight": 0.75, "proportions": 1.0, "height": 1.0})
TARGETS = {k: v for k, v in base_cfg.get("targets", {}).items() if not k.startswith("_")}

# ---- 1. the same human as s2_body_base.py, weights kept --------------------------------------------------------------
reset_scene()
macro = TargetService.get_default_macro_info_dict()
macro.update(MACRO)
human = HumanService.create_human(mask_helpers=False, detailed_helpers=True, extra_vertex_groups=True,
                                  feet_on_ground=True, scale=0.1, macro_detail_dict=macro)
rig = HumanService.add_builtin_rig(human, "game_engine", import_weights=True)
for tname, w in TARGETS.items():
    TargetService.load_target(human, TargetService.target_full_path(tname), weight=float(w), name=tname)
select_only(human)
human.shape_key_add(name="mix", from_mix=True)
c = np.empty(len(human.data.vertices) * 3)
human.data.shape_keys.key_blocks["mix"].data.foreach_get("co", c)
human.shape_key_clear()
human.data.vertices.foreach_set("co", c)
human.data.update()
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
select_only(human)
for m in list(human.modifiers):
    if m.type == "ARMATURE":
        bpy.ops.object.modifier_apply(modifier=m.name)
bone_names = [b.name for b in rig.data.bones]
bpy.data.objects.remove(rig)
me = human.data
hco = get_co(me)
gidx = {g.name: g.index for g in human.vertex_groups}
body_gi = gidx["body"]
is_body = np.zeros(len(me.vertices), bool)
MAP = {"pelvis": "pelvis", "spine_01": "spine_01", "spine_02": "spine_02", "spine_03": "spine_03", "neck_01": "neck", "head": "head"}
for s, m in (("L", "l"), ("R", "r")):
    MAP.update({"clavicle_" + m: "clavicle_" + s, "upperarm_" + m: "upperarm_" + s, "lowerarm_" + m: "lowerarm_" + s,
                "hand_" + m: "hand_" + s, "thigh_" + m: "thigh_" + s, "calf_" + m: "shin_" + s, "foot_" + m: "foot_" + s,
                "ball_" + m: "toe_" + s})
    for f in R.FINGERS:
        for i in (1, 2, 3):
            MAP["%s_%02d_%s" % (f, i, m)] = "%s_%02d_%s" % (f, i, s)
GF = R.weight_bone_names()
col = {b: j for j, b in enumerate(GF)}
Wfull = np.zeros((len(me.vertices), len(GF)), dtype=np.float64)
unmapped = {}
gname = {g.index: g.name for g in human.vertex_groups}
for v in me.vertices:
    for g in v.groups:
        n = gname[g.group]
        if g.group == body_gi and g.weight > 0.5:
            is_body[v.index] = True
        if n in MAP:
            Wfull[v.index, col[MAP[n]]] += g.weight
        elif n in bone_names and g.weight > 0:
            unmapped[n] = unmapped.get(n, 0) + 1
log("hm08:", len(me.vertices), "verts,", int(is_body.sum()), "body; game_engine groups not mapped:", unmapped)

# ---- 2. match the reduced base vertices ---------------------------------------------------------------------------------
with bpy.data.libraries.load(P["base"], link=False) as (src, dst):
    dst.objects = ["BODY_base_hm08"]
base = dst.objects[0]
bco = get_co(base.data) @ np.array(base.matrix_world)[:3, :3].T + np.array(base.matrix_world)[:3, 3]
kd = KDTree(int(is_body.sum()))
body_ids = np.nonzero(is_body)[0]
for k, i in enumerate(body_ids):
    kd.insert(hco[i], k)
kd.balance()
match = np.empty(len(bco), dtype=np.int64)
dist = np.empty(len(bco))
for i, p in enumerate(bco):
    _c, k, d = kd.find(p)
    match[i] = body_ids[k]
    dist[i] = d
Wb = Wfull[match]
s = Wb.sum(axis=1)
Wb[s > 0] /= s[s > 0, None]
log("base verts %d matched: distance p50 %.2e, p99 %.2e, max %.2e m; %d with no weight" % (
    len(bco), np.median(dist), np.percentile(dist, 99), dist.max(), int((s == 0).sum())))

# the fit keeps the base vertex order: the base edges must still be edges of BODY (the extra loops split a few)
with bpy.data.libraries.load(P["stage2"], link=False) as (src, dst):
    dst.objects = ["BODY"]
bodyp = dst.objects[0]
be = set(tuple(sorted(e.vertices)) for e in base.data.edges)
pe = set(tuple(sorted(e.vertices)) for e in bodyp.data.edges)
kept = len(be & pe) / max(1, len(be))
log("base edges kept in BODY: %.3f" % kept)
if kept < 0.9:
    raise SystemExit("BODY does not keep the base vertex order (%.3f of the base edges) - rerun stage 2 or map by surface" % kept)

os.makedirs(P["W"], exist_ok=True)
np.savez_compressed(P["seed"], bones=np.array(GF), weights=Wb.astype(np.float32), n_base=np.int64(len(bco)))
write_json(os.path.join(P["S3"], "mh_seed.json"), {
    "source": "MakeHuman hm08 game_engine weights (CC0) via MPFB create_human + add_builtin_rig(import_weights=True), used as a tool",
    "macro": MACRO, "targets": TARGETS, "hm08_vertices": len(me.vertices), "hm08_body_vertices": int(is_body.sum()),
    "base_vertices": int(len(bco)), "match_distance_m": {"p50": float(np.median(dist)), "p99": float(np.percentile(dist, 99)), "max": float(dist.max())},
    "base_edges_kept_in_body": round(kept, 4), "unweighted_base_vertices": int((s == 0).sum()),
    "bone_map": MAP, "game_engine_groups_not_mapped": unmapped,
    "verts_per_bone": {b: int((Wb[:, j] > 0.01).sum()) for j, b in enumerate(GF)}})
log("seed written:", P["seed"])
