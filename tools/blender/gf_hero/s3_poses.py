"""Stage 3, step 4: validation poses on GF_Hero_v1, with the signature weapon on the sockets (headless Blender).

  blender -b -P tools/blender/gf_hero/s3_poses.py -- <key> [--no-render] [--only <pose,...>]

Adapted from Ashen Covenant p04_validation_poses.py (a keyed validation action, per-pose numeric stretch check, dominant
bone pairs on the worst edges, contact sheets). GODFORGE additions:
  * the pose set is the one every GF hero is judged on (defined from the hero's own landmarks, so it scales to any
    proportions): bind, A-pose, both-arms punch, guard, deep squat, lunge with a right cross, torso twist, two head
    turns, fist clench, uppercut, forearm twist (candy-wrapper test), elbow + knee maximum;
  * the weapon rides on weapon_L / weapon_R (Child Of, inverse = SOCKET_TO_GRIP, the identity attach); every pose but
    bind uses the closed-fist variant with the body's fingers clenched under it;
  * metrics per pose: edge stretch/compression, collapsed vertices (1-ring area), body volume, forearm cross-section
    under twist (candy wrapper), the weapon against the body: vertices inside weapon material and vertices that
    leave the weapon's enclosure (poke-through), measured in the weapon's own frame;
  * renders: full body (Cycles CPU toon), close-ups of shoulder / elbow / knee / hands (Workbench clay, the weapon in
    slate blue so any intersection shows) and the in-game camera at true 1080p pixel size.

Outputs: work/renders/stage3/pose_<nn>_<name>_<view>.png, reports/stage3/poses.json, the action GF_ValidationPoses stashed
(muted) in production/<key>_rig.blend.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s3_pose_set import build_poses  # noqa: E402
from s2lib import aim_ortho, az_dir, get_co, get_edges, log, read_json, render_still, save_blend, script_args, setup_workbench, write_json  # noqa: E402
from s3lib import (WeightMatrix, apply_pose, components, cycles_cpu, evaluated_co, hero_paths, key_current_pose, make_toon_cycles,  # noqa: E402
                   new_action, push_to_nla, reset_pose, segment_param)

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
RENDER = "--no-render" not in argv
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
OUT = P["renders"]
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=P["rig"])
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
body = bpy.data.objects["BODY"]
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not body]
weapons = [o for o in scene.objects if o.name.startswith("PREVIEW_")]
W_OPEN = {o.name[-1]: o for o in weapons if "FIST" not in o.name}
W_FIST = {o.name[-1]: o for o in weapons if "FIST" in o.name}
LM = read_json(P["landmarks"])
V = lambda k: Vector(R.point(LM, k))  # noqa: E731
report = {"hero": KEY, "poses": {}}
T0 = time.time()

# ---- the pose set (s3_pose_set.py, from the hero's own landmarks) -------------------------------------------------------
POSES, FISTS = build_poses(LM)
if ONLY:
    POSES = [p for p in POSES if p[0] in ONLY or p[0] == "bind"]

# ---- rest data for the metrics ---------------------------------------------------------------------------------------
me = body.data
lab = components(me)
main = lab == np.bincount(lab).argmax()
rest = get_co(me)
ed = get_edges(me)
ed = ed[main[ed[:, 0]] & main[ed[:, 1]]]
rest_len = np.linalg.norm(rest[ed[:, 0]] - rest[ed[:, 1]], axis=1)
tris = []
for p in me.polygons:
    if main[p.vertices[0]]:
        vs = list(p.vertices)
        for i in range(1, len(vs) - 1):
            tris.append((vs[0], vs[i], vs[i + 1]))
tris = np.array(tris)
BONES = [vg.name for vg in body.vertex_groups]
Wb = WeightMatrix.read(body, BONES).W
dom = np.array([BONES[j] for j in Wb.argmax(axis=1)])


def tri_area(co):
    return 0.5 * np.linalg.norm(np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]]), axis=1)


def vert_area(co):
    a = tri_area(co)
    out = np.zeros(len(co))
    for k in range(3):
        np.add.at(out, tris[:, k], a)
    return out


def volume(co):
    a, b, c = co[tris[:, 0]], co[tris[:, 1]], co[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


rest_area = vert_area(rest)
rest_vol = volume(rest)


# weapon pieces in their own frame: one BVH for the whole weapon (rays), one per closed piece (inside tests)
def weapon_local(ob):
    me_ = ob.data
    co = get_co(me_)
    polys = [tuple(p.vertices) for p in me_.polygons]
    lab_ = components(me_)
    pieces = []
    for k in range(int(lab_.max()) + 1):
        pp = [p for p in polys if lab_[p[0]] == k]
        idx = np.nonzero(lab_ == k)[0]
        pieces.append((co[idx].min(0) - 0.002, co[idx].max(0) + 0.002, BVHTree.FromPolygons([tuple(c) for c in co], pp)))
    return BVHTree.FromPolygons([tuple(c) for c in co], polys), pieces


WLOC = {s: weapon_local(o) for s, o in W_FIST.items()}
side_bones = {s: {b for b in BONES if b.endswith("_" + s) and b.split("_")[0] in ("lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky")}
              for s in ("L", "R")}
RAYS = [Vector((math.cos(a), 0.0, math.sin(a))) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]


def weapon_frame(side):
    return R.grip_matrix(arm, "weapon_" + side)


def enclosed(side, pts_world):
    """Per point: True when all 8 rays perpendicular to the weapon's axis (grip Y) hit the weapon."""
    tree = WLOC[side][0]
    inv = weapon_frame(side).inverted()
    out = np.zeros(len(pts_world), bool)
    for i, p in enumerate(pts_world):
        q = inv @ Vector(p)
        out[i] = all(tree.ray_cast(q, d, 0.6)[0] is not None for d in RAYS)
    return out


def inside_material(side, pts_world, depth=0.003):
    inv = np.array(weapon_frame(side).inverted())
    q = pts_world @ inv[:3, :3].T + inv[:3, 3]
    hit = np.zeros(len(q), bool)
    for lo, hi, tree in WLOC[side][1]:
        cand = np.nonzero(np.all((q > lo) & (q < hi), axis=1) & ~hit)[0]
        for i in cand:
            loc, nrm, _f, _d = tree.find_nearest(Vector(q[i]))
            if loc is not None and (Vector(q[i]) - loc).dot(nrm) < -depth:
                hit[i] = True
    return hit


def near_weapon(side, pts_world, radius=0.75):
    o = np.array(weapon_frame(side).translation)
    return np.linalg.norm(pts_world - o, axis=1) < radius


# reference coverage: the rest pose with clenched fists. The gauntlet core is a closed solid around the forearm and hand,
# so the wearer's arm is "covered" when it is inside weapon material OR enclosed by it (all radial rays hit).
apply_pose(arm, FISTS)
co_ref = evaluated_co(body)
COV_REF = {}
report["weapon_reference"] = {}
for s in W_FIST:
    cand = np.nonzero(np.isin(dom, list(side_bones[s])) & main)[0]
    cov = inside_material(s, co_ref[cand]) | enclosed(s, co_ref[cand])
    COV_REF[s] = cand[cov]
    report["weapon_reference"][s] = {"arm_hand_vertices": int(len(cand)), "covered_with_fist": int(cov.sum()),
                                     "uncovered_at_rest": int((~cov).sum())}
log("weapon reference", report["weapon_reference"])


def forearm_section(co, side):
    """Mean radius of the distal forearm (t 0.55-0.95 along the posed lowerarm) around the posed forearm axis."""
    pb = arm.pose.bones["lowerarm_" + side]
    h = np.array(arm.matrix_world @ pb.head)
    t_ = np.array(arm.matrix_world @ pb.tail)
    b = arm.data.bones["lowerarm_" + side]
    tr, _tr, _d = segment_param(rest, np.array(b.head_local), np.array(b.tail_local))
    m = np.isin(dom, ["lowerarm_" + side, "lowerarm_twist_" + side]) & (tr > 0.55) & (tr < 0.95)
    ax = (t_ - h) / np.linalg.norm(t_ - h)
    rel = co[m] - h
    r_pose = np.linalg.norm(rel - np.outer(rel @ ax, ax), axis=1)
    axr = (np.array(b.tail_local) - np.array(b.head_local))
    axr /= np.linalg.norm(axr)
    relr = rest[m] - np.array(b.head_local)
    r_rest = np.linalg.norm(relr - np.outer(relr @ axr, axr), axis=1)
    return float(r_pose.mean() / r_rest.mean()), float((r_pose / np.maximum(r_rest, 1e-6)).min())


def metrics(name, variant):
    co = evaluated_co(body)
    L = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
    dmm = (L - rest_len) * 1000.0
    big = rest_len > 0.005                     # relative change only on edges over 5 mm (tiny edges exaggerate it)
    rel = np.where(big, L / np.maximum(rest_len, 1e-9) - 1.0, 0.0)
    area = vert_area(co) / np.maximum(rest_area, 1e-12)
    r = {"stretch_mm_p99_9": round(float(np.percentile(dmm, 99.9)), 1), "stretch_mm_max": round(float(dmm.max()), 1),
         "stretch_rel_max": round(float(rel.max()), 3), "compress_rel_min": round(float(rel.min()), 3),
         "edges_over_40pct": int((rel > 0.4).sum()), "edges_under_minus40pct": int((rel < -0.4).sum()),
         "collapsed_verts_area_lt_0_4": int(((area < 0.4) & main).sum()), "volume_ratio": round(volume(co) / rest_vol, 4)}
    worst = np.argsort(-dmm)[:3]
    r["worst_stretch_edges"] = [{"mm": round(float(dmm[e_]), 1), "at_rest": np.round(rest[ed[e_, 0]], 3).tolist(),
                                 "bones": "|".join(sorted((str(dom[ed[e_, 0]]), str(dom[ed[e_, 1]]))))} for e_ in worst]
    bad = np.nonzero((rel > 0.4) | (rel < -0.4))[0]
    if len(bad):
        pairs = {}
        for e_ in bad:
            k = "|".join(sorted((dom[ed[e_, 0]], dom[ed[e_, 1]])))
            pairs[k] = pairs.get(k, 0) + 1
        r["worst_bone_pairs"] = sorted(pairs.items(), key=lambda kv: -kv[1])[:5]
    col = np.nonzero((area < 0.4) & main)[0]
    if len(col):
        h = {}
        for i in col:
            h[dom[i]] = h.get(dom[i], 0) + 1
        r["collapsed_by_bone"] = sorted(h.items(), key=lambda kv: -kv[1])[:5]
    for s in ("L", "R"):
        r["forearm_section_" + s] = [round(v, 3) for v in forearm_section(co, s)]
    if variant == "fist" and W_FIST:
        for s in W_FIST:
            ref = COV_REF[s]
            cov = inside_material(s, co[ref]) | enclosed(s, co[ref])
            others = np.setdiff1d(np.nonzero(near_weapon(s, co) & main)[0], np.nonzero(np.isin(dom, list(side_bones[s])))[0])
            cut = others[inside_material(s, co[others])]
            r["weapon_" + s] = {"poke_through": int((~cov).sum()), "covered_ref": int(len(ref)), "weapon_cuts_body": int(len(cut))}
            for key, rows in (("poke_by_bone", ref[~cov]), ("cuts_by_bone", cut)):
                if len(rows):
                    h = {}
                    for i in rows:
                        h[str(dom[i])] = h.get(str(dom[i]), 0) + 1
                    r["weapon_" + s][key] = sorted(h.items(), key=lambda kv: -kv[1])[:4]
    return r


# ---- rendering -----------------------------------------------------------------------------------------------------------
TOON = {}
ORIG = {}
render_objs = [body] + parts + weapons
for o in render_objs:
    M = o.material_slots[0].material if o.material_slots else None
    if M is None:
        continue
    if M.name not in TOON:
        TOON[M.name] = make_toon_cycles(M)
    ORIG[o.name] = M
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
floor = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
floor.data.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new("ground")
fm.use_nodes = True
nt = fm.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.075, 0.032, 0.018, 1)
nt.links.new(em.outputs[0], nt.nodes.new("ShaderNodeOutputMaterial").inputs["Surface"])
floor.data.materials.append(fm)
scene.collection.objects.link(floor)
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1)
H = max(get_co(o.data)[:, 2].max() for o in [body] + parts)


def show(variant, bare=False):
    for s, o in W_OPEN.items():
        o.hide_render = bare or variant != "open"
    for s, o in W_FIST.items():
        o.hide_render = bare or variant != "fist"


def use(kind):
    for o in render_objs:
        if o.name in ORIG:
            o.material_slots[0].material = TOON[ORIG[o.name].name] if kind == "toon" else ORIG[o.name]


def clay_colors():
    for o in render_objs:
        o.color = (0.30, 0.37, 0.55, 1) if o in weapons else ((0.76, 0.67, 0.60, 1) if o is body else (0.55, 0.52, 0.50, 1))


def render_pose(i, name, variant):
    tag = "pose_%02d_%s" % (i, name)
    show(variant)
    # full body, toon (Cycles CPU)
    use("toon")
    cycles_cpu(scene, samples=6)
    floor.hide_render = True
    aim_ortho(scene, (0, -0.1, H * 0.5), az_dir(32, 8), H * 1.22)
    render_still(scene, os.path.join(OUT, tag + "_full.png"), 560, 640)
    # in-game camera: orthographic, 55 deg pitch, FixedVertical 22 m -> 1080 px (true pixel size), yaw 0 and 35
    floor.hide_render = False
    pitch = math.radians(55.0)
    for yaw in (0, 35):
        d = Vector((math.sin(math.radians(yaw)) * math.cos(pitch), -math.cos(math.radians(yaw)) * math.cos(pitch), math.sin(pitch)))
        aim_ortho(scene, (0, 0, H * 0.45), d, 22.0 * 128 / 1080.0)
        render_still(scene, os.path.join(OUT, tag + "_ingame%d.png" % yaw), 128)
    floor.hide_render = True
    # clay close-ups (Workbench): shoulder, elbow, knee, hands - the weapon in slate blue
    use("orig")
    setup_workbench(scene, "OBJECT", cavity=True, bg=(0.16, 0.16, 0.18))
    clay_colors()
    pb = arm.pose.bones
    wm = arm.matrix_world
    sh = wm @ pb["upperarm_L"].head
    el = wm @ pb["lowerarm_L"].head
    kn = wm @ pb["shin_L"].head
    hL = weapon_frame("L").translation
    hR = weapon_frame("R").translation
    # elbow: perpendicular to the bend plane (the crease in profile), from above when that plane is flat
    fore = (wm @ pb["lowerarm_L"].tail - el).normalized()
    up_ = (sh - el).normalized()
    n = fore.cross(up_)
    if n.length < 0.15:                      # (nearly) straight arm: look from the front-outside
        n = Vector((0.6, -0.8, 0.3))
    n = n.normalized()
    if abs(n.z) > 0.6:
        n = n if n.z > 0 else -n
    elif n.dot(Vector((0.3, -1.0, 0.2))) < 0:
        n = -n
    hands_c = (hL + hR) * 0.5
    span = (hL - hR).length
    hd = wm @ pb["head"].head
    shots = {"shoulder_front": (sh + Vector((0.0, -0.05, 0.02)), az_dir(38, 22), 0.66),
             "shoulder_back": (sh + Vector((0.0, 0.06, 0.02)), az_dir(150, 28), 0.66),
             "elbow": (el, tuple((n + Vector((0, 0, 0.25))).normalized()), 0.62),
             "knee": (kn, az_dir(65, 10), 0.66),
             "head": (hd + Vector((0, -0.02, 0.04)), az_dir(30, 6), 0.52)}
    if span < 0.9:
        shots["hands"] = (hands_c, az_dir(18, 16), max(0.55, span + 0.45))
    else:
        shots["hands"] = (hL, az_dir(35, 20), 0.6)
    for k, (tgt, d, sc) in shots.items():
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "%s_%s.png" % (tag, k)), 420)
    if name in ("fist_clench", "forearm_twist", "guard"):
        show(variant, bare=True)
        tgt, d, sc = shots["hands"] if name != "forearm_twist" else (hL, az_dir(35, 20), 0.6)
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "%s_hands_bare.png" % tag), 420)
        if name == "forearm_twist":
            aim_ortho(scene, (el + (wm @ pb["lowerarm_L"].tail)) * 0.5, az_dir(20, 60), 0.62)
            render_still(scene, os.path.join(OUT, "%s_forearm_bare.png" % tag), 420)
        show(variant)


# ---- run --------------------------------------------------------------------------------------------------------------------
if arm.animation_data:
    arm.animation_data.action = None
    for tr in list(arm.animation_data.nla_tracks):
        if tr.name == "GF_ValidationPoses":
            arm.animation_data.nla_tracks.remove(tr)
SNAP = []
for i, (name, pose, variant) in enumerate(POSES, start=1):
    t = time.time()
    apply_pose(arm, pose)
    SNAP.append({pb.name: (pb.rotation_euler.copy(), pb.location.copy()) for pb in arm.pose.bones})
    r = metrics(name, variant)
    r["weapon_variant"] = variant
    report["poses"][name] = r
    log("%-15s %s" % (name, {k: v for k, v in r.items() if k in ("stretch_mm_max", "stretch_rel_max", "compress_rel_min", "collapsed_verts_area_lt_0_4", "volume_ratio",
                                                              "forearm_section_L", "weapon_L", "weapon_R")}))
    if RENDER:
        render_pose(i, name, variant)
    r["seconds"] = round(time.time() - t, 1)

# ---- weapon limits: how far each joint can bend before the rigid weapon cuts the body or the arm pokes out --------
def weapon_counts(side):
    co = evaluated_co(body)
    ref = COV_REF[side]
    cov = inside_material(side, co[ref]) | enclosed(side, co[ref])
    others = np.setdiff1d(np.nonzero(near_weapon(side, co) & main)[0], np.nonzero(np.isin(dom, list(side_bones[side])))[0])
    return int((~cov).sum()), int(inside_material(side, co[others]).sum())


if W_FIST and (ONLY is None or "limits" in ONLY):
    base = {"upperarm_L": {"rot": (4, 0, -47)}}
    base.update({k: v for k, v in FISTS.items() if k.endswith("_L")})
    sweeps = {"elbow_flexion": ("lowerarm_L", 0, range(0, 151, 10)),
              "wrist_extension(+)/flexion(-)": ("hand_L", 2, range(-40, 41, 5)),
              "wrist_radial(+)/ulnar(-)_deviation": ("hand_L", 0, range(-40, 41, 5)),
              "forearm_twist": ("hand_L", 1, range(-120, 121, 20))}
    limits = {}
    for key, (bone, axis, angles) in sweeps.items():
        rows = []
        for a in angles:
            rot = [0, 0, 0]
            rot[axis] = a
            pose = dict(base)
            pose[bone] = dict(pose.get(bone, {}), rot=tuple(rot))
            if bone == "hand_L":
                pose["lowerarm_L"] = {"rot": (30, 0, 0)}
            apply_pose(arm, pose)
            poke, cut = weapon_counts("L")
            rows.append((a, poke, cut))
        ok = [a for a, p_, c_ in rows if p_ <= 2 and c_ <= 2]
        clean = [a for a, p_, c_ in rows if p_ == 0 and c_ == 0]
        limits[key] = {"samples_deg_poke_cut": rows, "range_clean_deg": [min(clean), max(clean)] if clean else None,
                       "range_le2_verts_deg": [min(ok), max(ok)] if ok else None}
        log("weapon limit %-36s clean %s  <=2 verts %s" % (key, limits[key]["range_clean_deg"], limits[key]["range_le2_verts_deg"]))
    report["weapon_limits"] = {"weapon": "anvil_gauntlets fist variant on weapon_L", "arm": "upper arm in the A-pose, fist clenched; "
                               "wrist sweeps with the elbow at 30 deg", "limits": limits}

# bone-marker renders of the rest skeleton + socket axes (for the skeleton sheet)
if RENDER and (ONLY is None):
    reset_pose(arm)
    bpy.context.view_layer.update()
    show("none")
    mk = []

    def marker(p, rad, col):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=rad, location=p, segments=10, ring_count=6)
        o = bpy.context.active_object
        o.color = col
        o.show_in_front = True
        mk.append(o)
        return o

    def stick(a, b, rad, col):
        d = b - a
        bpy.ops.mesh.primitive_cylinder_add(radius=rad, depth=max(d.length, 1e-4), location=(a + b) * 0.5, vertices=8)
        o = bpy.context.active_object
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = d.to_track_quat("Z", "Y")
        o.color = col
        o.show_in_front = True
        mk.append(o)
    for b in arm.data.bones:
        n = b.name
        if n in R.SOCKET_NAMES:
            continue
        col = ((1.0, 0.35, 1.0, 1) if "twist" in n else (0.2, 0.95, 0.3, 1) if n.split("_")[0] in R.FINGERS
               else (0.2, 0.9, 1.0, 1) if n == "root" else (1.0, 0.15, 0.1, 1))
        small = n.split("_")[0] in R.FINGERS
        a, c = arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local
        marker(a, 0.0045 if small else 0.013, col)
        stick(a, c, 0.0022 if small else (0.005 if "twist" in n else 0.007), col)
    for sname in R.SOCKET_NAMES:
        G = R.grip_matrix(arm, sname, pose=False)
        o = G.translation
        marker(o, 0.012, (1, 0.85, 0.1, 1))
        for k, col in ((0, (0.95, 0.1, 0.1, 1)), (1, (0.1, 0.85, 0.1, 1)), (2, (0.15, 0.35, 1.0, 1))):
            ax = G.to_3x3().col[k].normalized()
            stick(o, o + ax * 0.13, 0.004, col)
    setup_workbench(scene, "OBJECT", bg=(0.16, 0.16, 0.18))
    use("orig")
    for o in render_objs:
        o.color = (0.72, 0.66, 0.62, 1)
    for o in mk:
        o.hide_render = False
    for view, d, tgt, sc, res in (("front", az_dir(0, 2), (0, 0, H * 0.5), H * 1.25, (900, 900)), ("side", az_dir(90, 2), (0, 0, H * 0.5), H * 1.05, (700, 900)),
                                  ("hand", (0.25, -0.35, 1.0), tuple(V("hand_L_tip") + Vector((-0.02, 0, 0))), 0.34, (700, 700)),
                                  ("hand_front", az_dir(8, 10), tuple(V("hand_L_tip") + Vector((-0.02, 0, 0))), 0.34, (700, 700)),
                                  ("head", az_dir(35, 5), (0, 0, 2.0), 0.6, (600, 600))):
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "skeleton_%s.png" % view), *res)
    for s_, o in W_FIST.items():           # the grip frame with the fist gauntlet on it
        o.hide_render = False
    aim_ortho(scene, tuple(R.grip_matrix(arm, "weapon_L", pose=False).translation), (0.55, -0.6, 0.6), 0.62)
    render_still(scene, os.path.join(OUT, "skeleton_socket_fist.png"), 700, 700)
    show("none")
    for o in mk:
        me_ = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me_)
    # dominant-bone colour map (front / back)
    rng = np.random.default_rng(7)
    pal = {b: tuple(rng.uniform(0.25, 1.0, 3)) + (1.0,) for b in BONES}
    ca = body.data.color_attributes.new("dominant_bone", "BYTE_COLOR", "POINT")
    ca.data.foreach_set("color", np.array([pal[d] for d in dom], dtype=np.float32).ravel())
    body.data.color_attributes.active_color = ca
    setup_workbench(scene, "VERTEX", bg=(0.16, 0.16, 0.18), light="FLAT")
    for o in parts + weapons:
        o.hide_render = True
    for view, az in (("front", 0), ("back", 180), ("side", 90)):
        aim_ortho(scene, (0, 0, H * 0.5), az_dir(az, 3), H * 1.25)
        render_still(scene, os.path.join(OUT, "weights_dominant_%s.png" % view), 700, 700)
    for view, tgt, d, sc in (("shoulder", tuple(V("shoulder_L")), az_dir(35, 25), 0.7), ("hand", tuple(V("hand_L_tip")), (0.2, -0.3, 1.0), 0.36)):
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "weights_dominant_%s.png" % view), 600, 600)
    body.data.color_attributes.remove(ca)
    for o in parts:
        o.hide_render = False

# ---- save -----------------------------------------------------------------------------------------------------------------
reset_pose(arm)
if ONLY is None:
    for o in render_objs:
        if o.name in ORIG:
            o.material_slots[0].material = ORIG[o.name]
            o.material_slots[0].link = "DATA"
    bpy.data.objects.remove(floor)
    act = new_action(arm, "GF_ValidationPoses", 1, len(POSES))
    for i, snap in enumerate(SNAP, start=1):
        for pb in arm.pose.bones:
            pb.rotation_euler, pb.location = snap[pb.name]
        key_current_pose(arm, i)
        act.pose_markers.new(POSES[i - 1][0]).frame = i
    push_to_nla(arm, act, "GF_ValidationPoses")
    arm.animation_data.action = None
    reset_pose(arm)
    show("fist")
    for o in weapons:
        o.hide_viewport = "FIST" not in o.name
    scene.frame_set(1)
    save_blend(P["rig"])
    report["seconds"] = round(time.time() - T0, 1)
    write_json(os.path.join(P["S3"], "poses.json"), report)
else:
    write_json(os.path.join(P["W"], "poses_partial.json"), report)
