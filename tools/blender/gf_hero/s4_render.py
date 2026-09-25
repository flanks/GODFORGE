"""Stage 4, step 2: key-frame renders and mesh checks of every clip (headless Blender 5.2, Cycles CPU + Workbench).

  blender -b -P tools/blender/gf_hero/s4_render.py -- <key> [--only clip,clip] [--no-render]

Opens production/<key>_anim.blend (s4_anim.py) and, for each clip's key frames (clips.json key_frames, the loop's
frame 0 and last frame included for the seam):
  * close-ups: the Cycles CPU toon review (s3lib.make_toon_cycles: the stage-2 textures, no EEVEE, the GPU is shared)
    from the front three-quarter and from the side, framed on the whole clip so motion reads against the ground grid;
  * the client camera: orthographic, 55 deg pitch, FixedVertical 22 m = 1080 px (true pixel size, 160 px crops), the
    hero facing the camera (yaw 0) and turned 90 deg;
  * mesh checks at those frames: lowest vertex of the body set against the ground, the anvil_gauntlets (fist or open
    variant, as the clip's fingers say) cutting into the body (vertices inside weapon material, the weapon's own arm
    excluded) and into each other.
Renders go to work/renders/stage4/<clip>/, numbers to reports/anim/render_checks.json.
"""
import json
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
from s2lib import aim_ortho, get_co, log, render_still, script_args, setup_workbench, write_json  # noqa: E402
from s3lib import components, cycles_cpu, evaluated_co, hero_paths, make_toon_cycles  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
RENDER = "--no-render" not in argv
P = hero_paths(KEY)
A = P["A"]
OUT = os.path.join(A, "work", "renders", "stage4")
MAN = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=os.path.join(A, "production", "%s_anim.blend" % KEY))
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
body = bpy.data.objects["BODY"]
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not body]
weapons = [o for o in scene.objects if o.name.startswith("PREVIEW_")]
W_OPEN = {o.name[-1]: o for o in weapons if "FIST" not in o.name}
W_FIST = {o.name[-1]: o for o in weapons if "FIST" in o.name}
for o in weapons:
    o.hide_viewport = False
for tr in arm.animation_data.nla_tracks:
    tr.mute = True
T0 = time.time()

# ---- materials, ground ------------------------------------------------------------------------------------------------
TOON, ORIG = {}, {}
render_objs = [body] + parts + weapons
for o in render_objs:
    M = o.material_slots[0].material if o.material_slots else None
    if M is None:
        continue
    if M.name not in TOON:
        TOON[M.name] = make_toon_cycles(M)
    ORIG[o.name] = M
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = TOON[M.name]


def emission_mat(name, rgba=None, checker=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n_ in list(nt.nodes):
        nt.nodes.remove(n_)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if checker:
        ck = nt.nodes.new("ShaderNodeTexChecker")
        ck.inputs["Scale"].default_value = checker[2]
        ck.inputs["Color1"].default_value = checker[0]
        ck.inputs["Color2"].default_value = checker[1]
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
        nt.links.new(ck.outputs["Color"], em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = rgba
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def plane(name, half, mat):
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    ob.data.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
    ob.data.materials.append(mat)
    scene.collection.objects.link(ob)
    return ob


# close-up ground: 0.5 m checker so foot sliding and travel read; in-game ground: the dark biome floor
grid = plane("GRID", 6.0, emission_mat("grid", checker=((0.11, 0.075, 0.06, 1), (0.16, 0.115, 0.09, 1), 12.0)))
floor = plane("GROUND", 30.0, emission_mat("ground", rgba=(0.075, 0.032, 0.018, 1)))
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1)
for o in list(scene.objects):
    if o.type == "MESH" and o not in render_objs and o not in (grid, floor):
        o.hide_render = True


def show_weapons(fist_l, fist_r):
    for s, fist in (("L", fist_l), ("R", fist_r)):
        if s in W_FIST:
            W_FIST[s].hide_render = not fist
        if s in W_OPEN:
            W_OPEN[s].hide_render = fist


def set_action(name):
    act = bpy.data.actions[name]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]


# ---- mesh checks -------------------------------------------------------------------------------------------------------
BONES = [vg.name for vg in body.vertex_groups]
Wd = np.zeros((len(body.data.vertices), len(BONES)))
for v in body.data.vertices:
    for g in v.groups:
        Wd[v.index, g.group] = g.weight
gname = {vg.index: vg.name for vg in body.vertex_groups}
dom = np.array([gname[j] for j in Wd.argmax(axis=1)])
lab = components(body.data)
main = lab == np.bincount(lab).argmax()
side_bones = {s: {b for b in BONES if b.endswith("_" + s) and b.split("_")[0] in ("lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky")}
              for s in ("L", "R")}
REST_ZMIN = min(float(get_co(o.data)[:, 2].min()) for o in [body] + parts)


def weapon_pieces(ob):
    me_ = ob.data
    co = get_co(me_)
    polys = [tuple(p.vertices) for p in me_.polygons]
    lab_ = components(me_)
    out = []
    for k in range(int(lab_.max()) + 1):
        pp = [p for p in polys if lab_[p[0]] == k]
        idx = np.nonzero(lab_ == k)[0]
        out.append((co[idx].min(0) - 0.002, co[idx].max(0) + 0.002, BVHTree.FromPolygons([tuple(c) for c in co], pp)))
    return out


PIECES = {o.name: weapon_pieces(o) for o in weapons}


def inside(ob, pts_world, depth=0.004):
    inv = np.array(R.grip_matrix(arm, "weapon_" + ob.name[-1]).inverted())
    q = pts_world @ inv[:3, :3].T + inv[:3, 3]
    hit = np.zeros(len(q), bool)
    for lo, hi, tree in PIECES[ob.name]:
        cand = np.nonzero(np.all((q > lo) & (q < hi), axis=1) & ~hit)[0]
        for i in cand:
            loc, nrm, _f, _d = tree.find_nearest(Vector(q[i]))
            if loc is not None and (Vector(q[i]) - loc).dot(nrm) < -depth:
                hit[i] = True
    return hit


def weapon_world_co(ob):
    G = np.array(R.grip_matrix(arm, "weapon_" + ob.name[-1]))
    co = get_co(ob.data)
    return co @ G[:3, :3].T + G[:3, 3]


def mesh_checks(fist_l, fist_r):
    r = {}
    cloth = {"SKIRT_PLATES", "SASH", "SKIRT_CLOTH"}
    zb = min(float(evaluated_co(o)[:, 2].min()) for o in [body] + parts if o.name not in cloth)
    zc = min([float(evaluated_co(o)[:, 2].min()) for o in parts if o.name in cloth] or [zb])
    r["lowest_vertex_z_mm"] = round(zb * 1000, 1)
    r["lowest_cloth_z_mm"] = round(zc * 1000, 1)
    co = evaluated_co(body)
    wob = {"L": (W_FIST if fist_l else W_OPEN).get("L"), "R": (W_FIST if fist_r else W_OPEN).get("R")}
    by_bone = {}
    for s, ob in wob.items():
        if ob is None:
            continue
        o = np.array(R.grip_matrix(arm, "weapon_" + s).translation)
        near = np.nonzero((np.linalg.norm(co - o, axis=1) < 0.8) & main & ~np.isin(dom, list(side_bones[s])))[0]
        cut = near[inside(ob, co[near])]
        r["gauntlet_%s_cuts_body" % s] = int(len(cut))
        for i in cut:
            by_bone[str(dom[i])] = by_bone.get(str(dom[i]), 0) + 1
    if by_bone:
        r["cuts_by_bone"] = sorted(by_bone.items(), key=lambda kv: -kv[1])[:4]
    if wob["L"] is not None and wob["R"] is not None:
        wl = weapon_world_co(wob["L"])
        r["gauntlets_touch"] = int(inside(wob["R"], wl).sum())
    return r


# ---- cameras -------------------------------------------------------------------------------------------------------------
def view_dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def frame_box(clip, d, aspect):
    """Centre + ortho scale that fits the clip's whole motion (bone extent + 0.25 m for the gauntlets / mesh)."""
    lo, hi = Vector(clip["_lo"]), Vector(clip["_hi"])
    fwd = -d.normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()
    xs, ys = [], []
    for i in range(8):
        c = Vector((lo.x if i & 1 else hi.x, lo.y if i & 2 else hi.y, lo.z if i & 4 else hi.z))
        xs.append(c.dot(right))
        ys.append(c.dot(up))
    w = max(xs) - min(xs) + 0.5
    h = max(ys) - min(ys) + 0.5
    centre = (lo + hi) * 0.5
    return centre, max(h, w / aspect)


CLOSE = [("front", 28, 10), ("side", 100, 8)]
CW, CH = 250, 300
INGAME_PX = 160
checks = {}
ck_path = os.path.join(A, "reports", "anim", "render_checks.json")
if ONLY and os.path.exists(ck_path):
    checks = json.load(open(ck_path, encoding="utf-8")).get("clips", {})

for name in MAN["order"]:
    info = MAN["clips"][name]
    if ONLY and name not in ONLY:
        continue
    t = time.time()
    set_action(info["action"])
    frames = list(info["key_frames"])
    if info["loop"] and info["frames"] not in frames:
        frames.append(info["frames"])           # the seam: the last frame must equal frame 0
    # motion bounds from the evaluated bones over every frame
    lo = Vector((1e9, 1e9, 0.0))
    hi = Vector((-1e9, -1e9, -1e9))
    for f in range(0, info["frames"] + 1, max(1, info["frames"] // 24)):
        scene.frame_set(f)
        for pb in arm.pose.bones:
            for p in (pb.head, pb.tail):
                w = arm.matrix_world @ p
                lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
                hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
    lo.z = 0.0
    hi.z = max(hi.z, 2.0)
    info["_lo"], info["_hi"] = tuple(lo), tuple(hi)
    variants = info["metrics"]["weapon_variant"]
    rows = {}
    d_ = os.path.join(OUT, name)
    os.makedirs(d_, exist_ok=True)
    for f in frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        fist = {}
        for s in ("L", "R"):
            v = variants[s]
            state = v["start"] == "fist"
            for sw in v["swap_frames"]:
                if f >= sw:
                    state = not state
            fist[s] = state
        show_weapons(fist["L"], fist["R"])
        rows[str(f)] = mesh_checks(fist["L"], fist["R"])
        if not RENDER:
            continue
        cycles_cpu(scene, samples=5)
        floor.hide_render = True
        grid.hide_render = False
        for view, az, el in CLOSE:
            d = view_dir(az, el)
            c, sc = frame_box(info, d, CW / CH)
            aim_ortho(scene, c, d, sc)
            render_still(scene, os.path.join(d_, "f%03d_%s.png" % (f, view)), CW, CH)
        grid.hide_render = True
        floor.hide_render = False
        pitch = math.radians(55.0)
        # the client camera looks at the clip's motion centre (lying / kneeling clips sit lower and further out)
        cx, cy = (info["_lo"][0] + info["_hi"][0]) * 0.5, (info["_lo"][1] + info["_hi"][1]) * 0.5
        cz = min(0.95, max(0.45, info["_hi"][2] * 0.43))
        for yaw in (0, 90):
            dd = Vector((math.sin(math.radians(yaw)) * math.cos(pitch), -math.cos(math.radians(yaw)) * math.cos(pitch), math.sin(pitch)))
            aim_ortho(scene, (cx, cy, cz), dd, 22.0 * INGAME_PX / 1080.0)
            render_still(scene, os.path.join(d_, "f%03d_ingame%d.png" % (f, yaw)), INGAME_PX)
    checks[name] = rows
    worst_cut = max((v.get("gauntlet_L_cuts_body", 0) + v.get("gauntlet_R_cuts_body", 0)) for v in rows.values())
    low = min(v["lowest_vertex_z_mm"] for v in rows.values())
    log("%-22s %d frames rendered, lowest vertex %.1f mm, worst gauntlet cut %d verts (%.1fs)" % (name, len(frames), low, worst_cut, time.time() - t))

write_json(ck_path, {"hero": KEY, "rest_lowest_vertex_z_mm": round(REST_ZMIN * 1000, 1), "clips": checks})
log("done in %.0fs" % (time.time() - T0))
