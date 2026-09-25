"""Stage 3, step 3: build GF_Hero_v1 on the hero and skin every part (headless Blender).

  blender -b -P tools/blender/gf_hero/s3_skin.py -- <key>

Inputs: production/<key>_stage2.blend (the mesh), work/<key>_landmarks.json (s3_landmarks.py), work/<key>_s3_mh_seed.npz
(s3_mh_seed.py), stage3_skin.json (the hand-set numbers). Output: production/<key>_rig.blend and reports/stage3/skin.json.

The skinning follows the Ashen Covenant helpers (D:/Ashen_Covenant/tools/blender/ac_player_rig/ac_skin.py, p03_skin_apose.py:
heat weights, ownership corrections, max 4 influences, normalised, nothing unweighted), adapted to a MakeHuman body:
  BODY   first a rest-shape prep (positions only): the stage-2 extra knee / elbow / wrist loop vertices move from
         their edge chords onto the smooth profile. Weights: the MakeHuman CC0 game_engine weights, exact per vertex
         (the body is hm08); the extra-loop vertices take the mean of their neighbours; the eyeballs go 100 % to head;
         Blender's bone-heat automatic weights are computed on the same body, blended in per region as
         stage3_skin.json says, and fill anything the seed leaves empty; the twist bones take their share of each limb
         along the bone; then the hand-style fixes listed in stage3_skin.json (joint blend bands with the knee cap on
         the thigh and the olecranon on the forearm, Euclidean smoothing of folds at the jaw, shoulders and knees);
  parts  hair and beard (with the teeth) 100 % head; tight parts (wraps, belt band) copy the body's weights at the
         closest body point; skirt-style cloth (sash tails, underskirt, plates) copies the body at its top and below
         hangs from the pelvis while following the thigh on its side; small pieces (buckle, knot) and every skirt
         plate are rigid: one weight row for the whole piece.
Then every object: at most 4 influences, weights under 1 % dropped, normalised, checked (no unweighted vertex, nothing
on root or a socket), an Armature modifier, parented to GF_Hero_v1.

The signature weapon is linked (not copied) into a PREVIEW collection: local objects that use the weapon file's meshes,
held on weapon_L / weapon_R by Child Of constraints whose inverse is gf_hero_rig.SOCKET_TO_GRIP - the Blender form of
the identity attach. The stage-5 export selects the armature and the body parts only.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import log, read_json, rel, save_blend, script_args, select_only, write_json  # noqa: E402
from s3lib import WeightMatrix, components, hero_paths, segment_param, smoothstep  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
P = hero_paths(KEY)
LM = read_json(P["landmarks"])
CFG = read_json(P["skin_cfg"])
FIT = read_json(P["fit"])
bpy.ops.wm.open_mainfile(filepath=P["stage2"])
scene = bpy.context.scene
report = {"hero": KEY, "contract": "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION), "landmarks": rel(P["landmarks"])}
T0 = time.time()

# ---- armature ---------------------------------------------------------------------------------------------------------
hero_col = next((c for c in bpy.data.collections if c.name.endswith("_stage2")), scene.collection)
arm = R.build_armature(LM, collection=hero_col)
problems = R.validate_hierarchy(arm)
if problems:
    raise SystemExit("hierarchy: " + "; ".join(problems))
report["bones"] = {"total": len(arm.data.bones), "core": len(R.CORE_BONES), "twist": len(R.TWIST_BONES),
                   "fingers": len(R.FINGER_BONES), "sockets": len(R.SOCKET_BONES),
                   "extras": len([b for b in arm.data.bones if b.name.startswith(R.EXTRA_PREFIX)])}
log("armature", arm.name, report["bones"])
BONES = R.weight_bone_names() + [b.name for b in arm.data.bones if b.name.startswith(R.EXTRA_PREFIX)]
C = {b: j for j, b in enumerate(BONES)}
SEG = {b.name: (np.array(b.head_local), np.array(b.tail_local)) for b in arm.data.bones}
meshes = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith(("REF", "WIRE", "PREVIEW"))]
for o in meshes:                      # every body part in the hero collection (BODY sat in the scene root)
    if hero_col not in o.users_collection:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        hero_col.objects.link(o)
for o in meshes:
    if any(abs(v) > 1e-6 for v in (*o.location, *o.rotation_euler)) or any(abs(v - 1) > 1e-6 for v in o.scale):
        raise SystemExit("%s has an unapplied transform" % o.name)


# ---- heat (Blender bone-heat automatic weights) ---------------------------------------------------------------------
def heat_weights(obj, keep_mask, allowed):
    """Bone-heat weights for obj's vertices in keep_mask (others zero), only bones in `allowed` deform."""
    import bmesh
    dup = obj.copy()
    dup.data = obj.data.copy()
    scene.collection.objects.link(dup)
    attr = dup.data.attributes.new("orig_idx", "INT", "POINT")
    attr.data.foreach_set("value", np.arange(len(obj.data.vertices), dtype=np.int32))
    bm = bmesh.new()
    bm.from_mesh(dup.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[int(i)] for i in np.nonzero(~keep_mask)[0]], context="VERTS")
    bm.to_mesh(dup.data)
    bm.free()
    flags = {b.name: b.use_deform for b in arm.data.bones}
    for b in arm.data.bones:
        b.use_deform = b.name in allowed
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    dup.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    t = time.time()
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    for b in arm.data.bones:
        b.use_deform = flags[b.name]
    H = np.zeros((len(obj.data.vertices), len(BONES)))
    orig = np.empty(len(dup.data.vertices), dtype=np.int32)
    dup.data.attributes["orig_idx"].data.foreach_get("value", orig)
    names = {vg.index: vg.name for vg in dup.vertex_groups}
    for v in dup.data.vertices:
        for g in v.groups:
            n = names[g.group]
            if n in C and g.weight > 0:
                H[orig[v.index], C[n]] = g.weight
    bpy.data.objects.remove(dup)
    s = H.sum(axis=1)
    H[s > 0] /= s[s > 0, None]
    log("heat on %s: %d/%d verts weighted, %.1fs" % (obj.name, int((s > 0).sum()), int(keep_mask.sum()), time.time() - t))
    return H


# ---- BODY --------------------------------------------------------------------------------------------------------------
body = bpy.data.objects["BODY"]
relax_log = []


def resmooth_extra_loops(obj, first):
    """Stage 2 inserts its extra knee / elbow / wrist loops at edge midpoints (s2_body_fit.py, after the surface fit), so
    each new vertex sits on the chord, inside the curved profile: a groove ring that folds under flexion. Each such
    vertex is moved onto the 4-point subdivision curve along its longitudinal edge loop:
    p = (-a_prev + 9 a + 9 b - b_next) / 16, where a, b are its two neighbours across the loop and a_prev / b_next
    continue the edge loop beyond them. Returns (moved, max move in m)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    n0 = len(bm.verts)
    lab_ = components(obj.data)
    main_ = lab_ == np.bincount(lab_).argmax()

    def continue_loop(vert, from_edge):
        if len(vert.link_edges) != 4:
            return None
        faces = set(from_edge.link_faces)
        for e in vert.link_edges:
            if e is not from_edge and not (set(e.link_faces) & faces):
                return e.other_vert(vert)
        return None
    new_pos = {}
    for v in bm.verts:
        if v.index < first or not main_[v.index] or len(v.link_edges) != 4:
            continue
        nb = [e.other_vert(v) for e in v.link_edges]
        across = [(e, o) for e, o in zip(v.link_edges, nb) if o.index < first]
        if len(across) != 2:
            continue
        (ea, a), (eb, b) = across
        # a and b must be opposite around v (no shared face between the two edges)
        if set(ea.link_faces) & set(eb.link_faces):
            continue
        ap = continue_loop(a, ea)
        bn = continue_loop(b, eb)
        if ap is None or bn is None:
            continue
        new_pos[v.index] = (-ap.co + 9 * a.co + 9 * b.co - bn.co) / 16.0
    moves = []
    for i, p in new_pos.items():
        moves.append((bm.verts[i].co - p).length)
        bm.verts[i].co = p
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return len(new_pos), (max(moves) if moves else 0.0), n0


for rr in CFG["body"].get("rest_relax", []):    # deformation prep on the rest shape (positions only)
    if rr.get("mode") == "extra_loops_4pt":
        nb0 = int(np.load(P["seed"])["n_base"])
        moved, mx, _n = resmooth_extra_loops(body, nb0)
        relax_log.append({"name": rr["name"], "vertices_moved": moved, "max_move_m": round(float(mx), 4)})
        log("rest relax", relax_log[-1])
        continue
    raise SystemExit("unknown rest_relax mode %r" % rr.get("mode"))
bw = WeightMatrix(body, BONES)
seed = np.load(P["seed"])
if [str(b) for b in seed["bones"]] != R.weight_bone_names():
    raise SystemExit("seed bone list differs from the contract - rerun s3_mh_seed.py")
nb = int(seed["n_base"])
bw.W[:nb, :len(seed["bones"])] = seed["weights"]
lab = components(body.data)
main_lab = np.bincount(lab).argmax()
main = lab == main_lab
extra = main & (np.arange(len(main)) >= nb)
# the stage-2 extra loops: mean of the already weighted neighbours, ring by ring
e = bw.edges
todo = extra.copy()
for _ in range(20):
    if not todo.any():
        break
    have = bw.W.sum(axis=1) > 0
    acc = np.zeros_like(bw.W)
    cnt = np.zeros(len(bw.W))
    for a, b in ((0, 1), (1, 0)):
        ok = have[e[:, b]]
        np.add.at(acc, e[ok, a], bw.W[e[ok, b]])
        np.add.at(cnt, e[ok, a], 1)
    fill = todo & (cnt > 0)
    bw.W[fill] = acc[fill] / cnt[fill, None]
    todo &= ~fill
report["rest_relax"] = relax_log
report["body_seed"] = {"base_vertices": nb, "extra_loop_vertices": int(extra.sum()), "extra_left_unfilled": int(todo.sum()),
                       "separate_pieces_to_head": int((~main).sum())}
bw.W[~main] = 0.0
bw.W[~main, C["head"]] = 1.0

core_fingers = set(R.core_bone_names() + R.finger_bone_names()) - {"root"}
H = heat_weights(body, main, core_fingers)
seed_W = bw.W.copy()
bc = CFG["body"]
mix = np.full(len(bw.W), float(bc.get("heat_mix", {}).get("default", 0.0)))
for reg in bc.get("heat_mix", {}).get("regions", []):     # later regions win, blended in over the outer 40 % of the radius
    for bone in reg["bones"]:
        t, _t, d = segment_param(bw.co, *SEG[bone])
        f = 1.0 - smoothstep(reg["radius"] * 0.6, reg["radius"], d)
        mix = mix * (1 - f) + reg["mix"] * f
hs = H.sum(axis=1) > 0
bw.W[hs] = (1 - mix[hs, None]) * bw.W[hs] + mix[hs, None] * H[hs]
empty = (bw.W.sum(axis=1) <= 0) & hs
bw.W[empty] = H[empty]
bw.normalise()
agree = {}
for b in R.core_bone_names()[1:]:
    j = C[b]
    m = (seed_W[:, j] > 0.05) | (H[:, j] > 0.05)
    if m.any():
        agree[b] = round(float(np.abs(seed_W[m, j] - H[m, j]).mean()), 3)
report["body_heat"] = {"weighted_vertices": int(hs.sum()), "mix_min": float(mix.min()), "mix_max": float(mix.max()),
                       "seed_filled_by_heat": int(empty.sum()), "mean_abs_diff_seed_vs_heat_per_bone": agree}

# twist bones take their share of each limb along the bone
tw = bc["twist"]
for s in ("L", "R"):
    for cls, twist, fn in (("upperarm_" + s, "upperarm_twist_" + s, lambda t: 1 - smoothstep(0.0, tw["upperarm_fade_end"], t)),
                           ("thigh_" + s, "thigh_twist_" + s, lambda t: 1 - smoothstep(0.0, tw["thigh_fade_end"], t)),
                           ("lowerarm_" + s, "lowerarm_twist_" + s, lambda t: smoothstep(tw["lowerarm_fade_start"], 1.0, t))):
        t, _t, _d = segment_param(bw.co, *SEG[cls])
        share = fn(t)
        w = bw.W[:, C[cls]].copy()
        bw.W[:, C[twist]] += w * share
        bw.W[:, C[cls]] = w * (1 - share)

# joint fixes: a blend band across a joint (parent <-> child) and local smoothing, from stage3_skin.json
fixes = {}
for jb in bc.get("joint_blend", []):
    a_cls, b_cls = jb["parent_class"], jb["child_class"]
    a_idx, b_idx = bw.idx(a_cls), bw.idx(b_cls)
    head, tail = SEG[jb["axis_bone"]]
    axis = (tail - head) / np.linalg.norm(tail - head)
    d = (bw.co - head) @ axis
    near = np.linalg.norm((bw.co - head) - np.outer(d, axis), axis=1) < jb["radius"]
    pair = bw.W[:, a_idx].sum(axis=1) + bw.W[:, b_idx].sum(axis=1)
    rows = np.nonzero(near & (np.abs(d) < jb["half_width"] * 2.5 + abs(jb.get("offset_outer", 0.0))) & (pair > 0.02))[0]
    off = np.full(len(rows), jb.get("offset", 0.0))
    if "outer_dir" in jb:        # the band moves on the outside of the bend (knee cap stays with the thigh, olecranon with the forearm)
        rad = (bw.co[rows] - head) - np.outer(d[rows], axis)
        rad /= np.maximum(np.linalg.norm(rad, axis=1), 1e-9)[:, None]
        od = np.array(jb["outer_dir"], dtype=np.float64)
        od /= np.linalg.norm(od)
        side = np.clip(rad @ od, 0.0, 1.0)
        off = off + jb["offset_outer"] * side
    f = smoothstep(-jb["half_width"], jb["half_width"], d[rows] - off)
    for idx, share in ((a_idx, 1 - f), (b_idx, f)):
        cur = bw.W[np.ix_(rows, idx)]
        tot = cur.sum(axis=1)
        dist = np.where(tot[:, None] > 1e-9, cur / np.maximum(tot[:, None], 1e-9), 1.0 / len(idx))
        bw.W[np.ix_(rows, idx)] = dist * (pair[rows] * share)[:, None]
    fixes["joint_blend_" + jb["name"]] = int(len(rows))
for sm in bc.get("smooth", []):
    t, _t, d = segment_param(bw.co, *SEG[sm["bone"]])
    m = d < sm["radius"]
    if "t_range" in sm:
        m &= (t >= sm["t_range"][0]) & (t <= sm["t_range"][1])
    bw.smooth(m & main, iters=sm.get("iters", 3), amount=sm.get("amount", 0.5))
    fixes["smooth_" + sm["name"]] = int((m & main).sum())
for ss in bc.get("spatial_smooth", []):
    # folds (the jaw over the throat, the armpit): near-coincident vertices that are not edge neighbours must move
    # together, so the weights are averaged over a Euclidean Gaussian, not over the edge graph
    from mathutils.kdtree import KDTree
    t, _t, d = segment_param(bw.co, *SEG[ss["bone"]])
    region = np.nonzero((d < ss["radius"]) & main)[0]
    kd = KDTree(len(region))
    for k, i in enumerate(region):
        kd.insert(bw.co[i], k)
    kd.balance()
    nbrs = []
    for i in region:
        found = kd.find_range(bw.co[i], 2.5 * ss["sigma"])
        idx = np.array([region[k] for _c, k, _d in found])
        g = np.exp(-0.5 * (np.array([dd for _c, _k, dd in found]) / ss["sigma"]) ** 2)
        nbrs.append((idx, g / g.sum()))
    fade = 1.0 - smoothstep(ss["radius"] * 0.7, ss["radius"], d[region])
    for _ in range(ss.get("iters", 2)):
        new = np.array([g @ bw.W[idx] for idx, g in nbrs])
        bw.W[region] = bw.W[region] * (1 - fade[:, None]) + new * fade[:, None]
    bw.normalise()
    fixes["spatial_smooth_" + ss["name"]] = int(len(region))
report["body_fixes"] = fixes
bw.limit(4)
body_W = bw.W.copy()

# ---- parts ------------------------------------------------------------------------------------------------------------
bco = bw.co
bpolys = [p for p in body.data.polygons if main[p.vertices[0]]]
bvh = BVHTree.FromPolygons([tuple(c) for c in bco], [tuple(p.vertices) for p in bpolys])
poly_verts = [np.array(p.vertices) for p in bpolys]


def copy_from_body(points):
    out = np.zeros((len(points), len(BONES)))
    for i, p in enumerate(points):
        loc, _n, fi, _d = bvh.find_nearest(Vector(p))
        vids = poly_verts[fi]
        dd = np.linalg.norm(bco[vids] - np.array(loc), axis=1)
        w = 1.0 / (dd + 1e-4) ** 2
        out[i] = (w / w.sum()) @ body_W[vids]
    return out


HANG = CFG["parts"]["hang"]


def hang_weights(points, attach_z, copy_band):
    x, z = points[:, 0], points[:, 2]
    d = np.clip((attach_z - z) / (attach_z - HANG["knee_z"]), 0.0, 1.0)
    a = HANG["follow_max"] * smoothstep(0.0, 1.0, d)
    s_l = smoothstep(-HANG["side_blend_m"], HANG["side_blend_m"], x)
    Wh = np.zeros((len(points), len(BONES)))
    Wh[:, C["pelvis"]] = 1 - a
    Wh[:, C["thigh_L"]] = a * s_l
    Wh[:, C["thigh_R"]] = a * (1 - s_l)
    Wc = copy_from_body(points)
    b = smoothstep(0.0, copy_band, attach_z - z)[:, None]
    return (1 - b) * Wc + b * Wh


part_report = {}
for name, pc in CFG["parts"].items():
    if name in ("_doc", "hang"):
        continue
    ob = bpy.data.objects.get(name)
    if ob is None:
        raise SystemExit("stage3_skin.json names part %s, which the file does not have" % name)
    wm = WeightMatrix(ob, BONES)
    pl = components(ob.data)
    npieces = int(pl.max()) + 1
    if pc["mode"] == "head":
        wm.W[:, C["head"]] = 1.0
    elif pc["mode"] == "copy":
        wm.W = copy_from_body(wm.co)
    elif pc["mode"] == "hang":
        wm.W = hang_weights(wm.co, pc["attach_z"], pc["copy_band_m"])
    rigid = 0
    for k in range(npieces):
        m = pl == k
        diag = float(np.linalg.norm(wm.co[m].max(0) - wm.co[m].min(0)))
        if pc.get("rigid_pieces") or diag < pc.get("rigid_below_diag_m", 0.0):
            wm.W[m] = wm.W[m].mean(axis=0)
            rigid += 1
    wm.limit(4)
    if rigid:     # a rigid piece must stay one row after the limit: redo the mean on the limited rows
        for k in range(npieces):
            m = pl == k
            diag = float(np.linalg.norm(wm.co[m].max(0) - wm.co[m].min(0)))
            if pc.get("rigid_pieces") or diag < pc.get("rigid_below_diag_m", 0.0):
                wm.W[m] = wm.W[m].mean(axis=0)
    wm.normalise()
    part_report[name] = {"mode": pc["mode"], "pieces": npieces, "rigid_pieces": rigid}
    wm.write()
    part_report[name].update(wm.stats())
bw.W = body_W
bw.write()
part_report["BODY"] = {"mode": "seed+heat+fixes"} | bw.stats()
report["objects"] = part_report

# ---- bind + checks -----------------------------------------------------------------------------------------------------
bad = []
nonw = set(R.non_weight_bone_names())
for ob in meshes:
    ob.parent = arm
    ob.matrix_parent_inverse = Matrix.Identity(4)
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_deform_preserve_volume = False      # glTF / Bevy skinning is linear blend: review what ships
    mod.use_vertex_groups = True
    wm = WeightMatrix.read(ob, BONES)
    st = wm.stats()
    groups = [vg.name for vg in ob.vertex_groups]
    if st["unweighted"]:
        bad.append("%s: %d unweighted vertices" % (ob.name, st["unweighted"]))
    if st["max_influences"] > 4:
        bad.append("%s: %d influences" % (ob.name, st["max_influences"]))
    if st["max_abs_sum_error"] > 1e-4:
        bad.append("%s: weights not normalised (%.2e)" % (ob.name, st["max_abs_sum_error"]))
    for g in groups:
        if g in nonw:
            bad.append("%s: weights on %s" % (ob.name, g))
        if g not in arm.data.bones:
            bad.append("%s: group %s is not a bone" % (ob.name, g))
report["weight_check"] = {"ok": not bad, "problems": bad}
if bad:
    raise SystemExit("weight check: " + "; ".join(bad))
log("weights OK on", [o.name for o in meshes])

# ---- preview: the signature weapon on its sockets (linked meshes, identity attach) -------------------------------------
wkey = FIT.get("signature_weapon")
report["preview_weapon"] = None
if wkey:
    wpath = os.path.join(os.path.dirname(os.path.dirname(P["A"])), "weapons", wkey, "production", "%s_stage2.blend" % wkey)
    if os.path.exists(wpath):
        # the authored T-pose placement of each weapon object (it must equal the socket attach at rest)
        with bpy.data.libraries.load(wpath, link=False) as (src, dst2):
            dst2.objects = [n for n in src.objects if n.startswith("GAUNTLET_")]
        authored = {}
        for o in dst2.objects:
            authored[o.data.name] = o.matrix_basis.copy()      # no parent: basis = placement
            me = o.data
            bpy.data.objects.remove(o)
            bpy.data.meshes.remove(me)
        with bpy.data.libraries.load(wpath, link=True, relative=True) as (src, dst):
            dst.meshes = [n for n in src.meshes if n.startswith("GAUNTLET_")]
        pcol = bpy.data.collections.new("PREVIEW_%s (not exported)" % wkey)
        scene.collection.children.link(pcol)
        for me in dst.meshes:
            ob = bpy.data.objects.new("PREVIEW_" + me.name, me)
            pcol.objects.link(ob)
            side = me.name[-1]
            c = ob.constraints.new("CHILD_OF")
            c.target = arm
            c.subtarget = "weapon_" + side
            c.inverse_matrix = Matrix(R.SOCKET_TO_GRIP)
            fist = "FIST" in me.name
            ob.hide_viewport = ob.hide_render = not fist
        bpy.context.view_layer.update()
        err = 0.0
        for me in dst.meshes:
            ref = authored[me.name]
            want = R.grip_matrix(arm, "weapon_" + me.name[-1], pose=False)
            err = max(err, max(abs(x - y) for ra, rb in zip(want, ref) for x, y in zip(ra, rb)))
        report["preview_weapon"] = {"file": rel(wpath), "objects": ["PREVIEW_" + m.name for m in dst.meshes],
                                    "rest_attach_vs_authored_placement_max_abs": err}
        log("preview weapon linked; rest attach vs authored placement: %.2e" % err)
        if err > 1e-4:
            raise SystemExit("the weapon's authored placement does not match the socket frame (%.2e)" % err)

select_only(arm)
arm.data.pose_position = "POSE"
save_blend(P["rig"])
report["seconds"] = round(time.time() - T0, 1)
write_json(os.path.join(P["S3"], "skin.json"), report)
