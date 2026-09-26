"""Stage 4, Valdris: key-frame renders and the every-frame audit of each clip (headless Blender 5.2, Cycles CPU).

  blender -b -P tools/blender/gf_hero/s4_valdris_render.py -- [--only clip,clip] [--no-render] [--no-audit]

Adapted from s4_render.py (Brax: the anvil_gauntlets fist / open variants and the body-in-gauntlet test) for a plate
juggernaut whose weapon is the colossus_cannon on weapon_R. Opens production/valdris_anim.blend (s4_anim.py + the cloth
pass s4_valdris_cloth.py) and per clip:

  * renders at the key frames (clips.json key_frames; a loop's last frame too, the seam): Cycles CPU toon close-ups
    (s3lib.make_toon_cycles, the stage-2 textures) from the front three-quarter and the side, framed on the clip's whole
    motion over a 0.5 m ground grid, and the 55 deg client camera (orthographic, 22 m = 1080 px, true pixels) with the
    hero facing the camera (yaw 0) and turned 90 deg, at game size (160 px);
  * the audit on EVERY frame (the review of Brax's stages 3-5 found defects between key frames that a key-frame check
    never saw), with the stage-3 measures of s3_valdris_check.py:
      - plates: vertices of one armour piece inside another that the rest pose does not have (clipping = different
        regions, sliding = lames of one region, suit = a plate in the under-suit), and the worst pairs;
      - the cannon: right-arm vertices poking out of its sleeve, other pieces it encloses;
      - cloth: cape / loincloth / braid vertices inside a solid piece (> 3 mm) or under the ground;
      - ground: the lowest vertex of the solid parts and of the cloth;
      - sole slip: while a sabaton's sole touches the ground (vertices within 6 mm of it), how far those vertices move
        in the world between frames (the design travel added back): a planted or rolling foot does not slip.
Renders -> work/renders/stage4/<clip>/ (local), numbers -> reports/anim/render_checks.json.
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

import gf_hero_rig as R  # noqa: E402
from s2lib import aim_ortho, log, render_still, script_args, write_json  # noqa: E402
from s3lib import cycles_cpu, hero_paths, make_toon_cycles  # noqa: E402
from s3_valdris_check import CLOTH, Checker, inside, piece_table_path  # noqa: E402
from s3_valdris_cloth import Pieces  # noqa: E402

KEY = "valdris"
argv = script_args(__doc__)
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
RENDER = "--no-render" not in argv
AUDIT = "--no-audit" not in argv
P = hero_paths(KEY)
A = P["A"]
OUT = os.path.join(A, "work", "renders", "stage4")
MAN = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=os.path.join(A, "production", "%s_anim.blend" % KEY))
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
body = bpy.data.objects["BODY"]
parts = {o.name: o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not body}
cannon = bpy.data.objects.get("PREVIEW_colossus_cannon_R")
for tr in arm.animation_data.nla_tracks:
    tr.mute = True
T0 = time.time()


def rest_pose():
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()


# ---- the checker (stage 3's), rest and cannon references ---------------------------------------------------------------
rest_pose()
CK = Checker(arm, piece_table_path(P), cannon)
CK.set_rest_reference(CK.posed())
import s4lib as L  # noqa: E402
for s in ("L", "R"):
    for b, tr in L.fist(s).items():
        arm.pose.bones[b].rotation_euler = [math.radians(a) for a in tr["rot"]]
bpy.context.view_layer.update()
CK.set_cannon_reference(CK.posed())
rest_pose()
SOLID = [o for o in CK.solid]
CLOTH_OBST = {"CAPE": Pieces([o for o in SOLID if o.name != "BEARD"]),
              "LOINCLOTH": Pieces([o for o in SOLID if o.name in ("BODY", "LEGS", "HIPS", "SABATONS")])}
_bn = {g.index: g.name for g in parts["BEARD"].vertex_groups}
BRAID_V = np.nonzero(np.array([any(_bn[g.group].startswith("x_beard") for g in v.groups) for v in parts["BEARD"].data.vertices]))[0]
BRAID_OBST = Pieces([o for o in SOLID if o.name in ("BODY", "ANVIL", "CUIRASS", "PAULDRONS", "ARMS", "GAUNTLETS")])
# the soles: SABATON_SOLE_<S> vertices (the rigid plate under each foot)
_sab = parts["SABATONS"]
_fp = np.empty(len(_sab.data.polygons), dtype=np.int32)
_sab.data.attributes["gf_piece"].data.foreach_get("value", _fp)
_table = {p["id"]: p["name"] for p in json.load(open(piece_table_path(P), encoding="utf-8"))["piece_table"]}
SOLE = {"L": set(), "R": set()}
for poly in _sab.data.polygons:
    nm = _table[int(_fp[poly.index])]
    if nm.startswith("SABATON_SOLE_") or nm.startswith("SABATON_TOE3_"):
        SOLE[nm[-1]].update(poly.vertices)
SOLE = {s: np.array(sorted(v)) for s, v in SOLE.items()}


def cloth_inside(co_by):
    out = {}
    for name, obst, idx in (("cape", CLOTH_OBST["CAPE"], None), ("loin", CLOTH_OBST["LOINCLOTH"], None), ("braids", BRAID_OBST, BRAID_V)):
        ob = {"cape": "CAPE", "loin": "LOINCLOTH", "braids": "BEARD"}[name]
        q = co_by[ob] if idx is None else co_by[ob][idx]
        built = obst.build(co_by)
        hit = np.zeros(len(q), bool)
        for lo, hi, bvh, _lab in built:
            for i in np.nonzero(np.all((q > lo + 0.003) & (q < hi - 0.003), axis=1) & ~hit)[0]:
                if inside(bvh, Vector(q[i])):
                    hit[i] = True
        out[name] = int(hit.sum())
        out[name + "_under_ground"] = int((q[:, 2] < -0.003).sum())
    return out


def audit_frame(co):
    raw = CK.plates_raw(co)
    pl = CK.plates(co, raw)
    r = {"clipping": pl["clipping"], "sliding": pl["sliding"], "suit": pl["suit"], "clipping_worst": pl["clipping_worst"][:4]}
    if cannon is not None:
        c = CK.cannon_check(co)
        r["cannon_poke"] = c["poke_through"]
        r["cannon_cuts"] = c["cuts"]
        r["cannon_cuts_by"] = c["cuts_by_piece"][:3]
    zs = min(float(co[o.name][:, 2].min()) for o in SOLID)
    zc = min(float(co[n][:, 2].min()) for n in CLOTH if n in co)
    r["lowest_solid_mm"] = round(zs * 1000, 1)
    r["lowest_cloth_mm"] = round(zc * 1000, 1)
    return r


# ---- rendering setup ------------------------------------------------------------------------------------------------
render_objs = [body] + list(parts.values()) + ([cannon] if cannon else [])
TOON = {}
for o in render_objs:
    for sl in o.material_slots:
        m = sl.material
        if m is None:
            continue
        if m.name not in TOON:
            TOON[m.name] = make_toon_cycles(m)
        sl.link = "OBJECT"
        sl.material = TOON[m.name]


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


grid = plane("GRID", 6.0, emission_mat("grid", checker=((0.11, 0.075, 0.06, 1), (0.16, 0.115, 0.09, 1), 12.0)))
floor = plane("GROUND", 30.0, emission_mat("ground", rgba=(0.075, 0.032, 0.018, 1)))
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1)
for o in list(scene.objects):
    if o.type == "MESH" and o not in render_objs and o not in (grid, floor):
        o.hide_render = True


def set_action(name):
    act = bpy.data.actions[name]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]


def view_dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def frame_box(lo, hi, d, aspect):
    fwd = -d.normalized()
    right = fwd.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(fwd).normalized()
    xs, ys = [], []
    for i in range(8):
        c = Vector((lo.x if i & 1 else hi.x, lo.y if i & 2 else hi.y, lo.z if i & 4 else hi.z))
        xs.append(c.dot(right))
        ys.append(c.dot(up))
    w = max(xs) - min(xs) + 0.7
    h = max(ys) - min(ys) + 0.6
    return (lo + hi) * 0.5, max(h, w / aspect)


CLOSE = [("front", 28, 10), ("side", 100, 8)]
CW, CH = 250, 300
INGAME_PX = 160
ck_path = os.path.join(A, "reports", "anim", "render_checks.json")
checks = {}
if ONLY and os.path.exists(ck_path):
    checks = json.load(open(ck_path, encoding="utf-8")).get("clips", {})

for name in MAN["order"]:
    info = MAN["clips"][name]
    if ONLY and name not in ONLY:
        continue
    t = time.time()
    set_action(info["action"])
    n = info["frames"] + 1
    travel = Vector((info["travel_mps"][0], info["travel_mps"][1], 0.0))
    frames = list(info["key_frames"])
    if info["loop"] and info["frames"] not in frames:
        frames.append(info["frames"])
    # motion bounds from the evaluated bones
    lo = Vector((1e9, 1e9, 0.0))
    hi = Vector((-1e9, -1e9, -1e9))
    for f in range(0, n, max(1, info["frames"] // 24)):
        scene.frame_set(f)
        for pb in arm.pose.bones:
            for p in (pb.head, pb.tail):
                lo = Vector((min(lo.x, p.x), min(lo.y, p.y), min(lo.z, p.z)))
                hi = Vector((max(hi.x, p.x), max(hi.y, p.y), max(hi.z, p.z)))
    lo.z = 0.0
    hi.z = max(hi.z, 2.35)
    rows, per_frame = {}, []
    d_ = os.path.join(OUT, name)
    os.makedirs(d_, exist_ok=True)
    prev_sole = None
    slip = {"L": [0.0, 0.0], "R": [0.0, 0.0]}      # [max per frame, max over a contact interval]
    run_ = {"L": 0.0, "R": 0.0}
    for f in range(n):
        need_render = RENDER and f in frames
        if not (AUDIT or f in frames):
            continue
        scene.frame_set(f)
        bpy.context.view_layer.update()
        co = CK.posed()
        r = audit_frame(co)
        if f in frames or AUDIT:
            r.update(cloth_inside(co) if (f in frames or f % 2 == 0) else {})
        # sole slip (world, the design travel added back)
        sab = co["SABATONS"]
        cur = {}
        for s in ("L", "R"):
            pts = sab[SOLE[s]]
            contact = pts[:, 2] < 0.006
            cur[s] = (contact, pts[:, :2] + np.array([travel.x, travel.y]) * (f / L.FPS))
            if prev_sole is not None:
                both = contact & prev_sole[s][0]
                if both.sum() >= 3:
                    dmm = float(np.median(np.linalg.norm(cur[s][1][both] - prev_sole[s][1][both], axis=1)) * 1000)
                    slip[s][0] = max(slip[s][0], dmm)
                    run_[s] += dmm
                    slip[s][1] = max(slip[s][1], run_[s])
                else:
                    run_[s] = 0.0
        prev_sole = cur
        r["frame"] = f
        per_frame.append(r)
        if f in frames:
            rows[str(f)] = r
        if not need_render:
            continue
        cycles_cpu(scene, samples=5)
        floor.hide_render = True
        grid.hide_render = False
        for view, az, el in CLOSE:
            dv = view_dir(az, el)
            c, sc = frame_box(lo, hi, dv, CW / CH)
            aim_ortho(scene, c, dv, sc)
            render_still(scene, os.path.join(d_, "f%03d_%s.png" % (f, view)), CW, CH)
        grid.hide_render = True
        floor.hide_render = False
        pitch = math.radians(55.0)
        cx, cy = (lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5
        cz = min(1.0, max(0.5, hi.z * 0.42))
        for yaw in (0, 90):
            dd = Vector((math.sin(math.radians(yaw)) * math.cos(pitch), -math.cos(math.radians(yaw)) * math.cos(pitch), math.sin(pitch)))
            aim_ortho(scene, (cx, cy, cz), dd, 22.0 * INGAME_PX / 1080.0)
            render_still(scene, os.path.join(d_, "f%03d_ingame%d.png" % (f, yaw)), INGAME_PX)
    summ = {}
    if per_frame:
        def mx(k):
            return max((p.get(k, 0) for p in per_frame), default=0)
        worst = max(per_frame, key=lambda p: p["clipping"])
        summ = {"frames_audited": len(per_frame), "clipping_max": worst["clipping"], "clipping_max_frame": worst["frame"],
                "clipping_worst_pairs": worst["clipping_worst"], "sliding_max": mx("sliding"), "suit_max": mx("suit"),
                "cannon_poke_max": mx("cannon_poke"), "cannon_cuts_max": mx("cannon_cuts"),
                "cape_inside_max": mx("cape"), "loin_inside_max": mx("loin"), "braids_inside_max": mx("braids"),
                "cloth_under_ground_max": max(mx("cape_under_ground"), mx("loin_under_ground"), mx("braids_under_ground")),
                "lowest_solid_mm": min(p["lowest_solid_mm"] for p in per_frame),
                "lowest_cloth_mm": min(p["lowest_cloth_mm"] for p in per_frame),
                "sole_slip_mm_per_frame_max": {s: round(slip[s][0], 1) for s in "LR"},
                "sole_slip_mm_per_contact_max": {s: round(slip[s][1], 1) for s in "LR"},
                "clipping_median": float(np.median([p["clipping"] for p in per_frame]))}
    checks[name] = {"key_frames": rows, "audit": summ, "bounds": [tuple(lo), tuple(hi)]}
    log("%-22s %d key frames, audit %d frames: clip max %s (f%s) median %.0f, cannon %s/%s, cloth %s/%s/%s, lowest %s / %s mm, sole slip %s (%.1fs)" % (
        name, len(frames), summ.get("frames_audited", 0), summ.get("clipping_max"), summ.get("clipping_max_frame"),
        summ.get("clipping_median", 0), summ.get("cannon_poke_max"), summ.get("cannon_cuts_max"), summ.get("cape_inside_max"),
        summ.get("loin_inside_max"), summ.get("braids_inside_max"), summ.get("lowest_solid_mm"), summ.get("lowest_cloth_mm"),
        summ.get("sole_slip_mm_per_contact_max"), time.time() - t))

rest = {"clipping": 0}
write_json(ck_path, {"hero": KEY, "doc": "s4_valdris_render.py: key-frame numbers and the every-frame audit per clip "
                                         "(plates / cannon / cloth / ground / sole slip, stage-3 measures)",
                     "clips": checks})
log("done in %.0fs" % (time.time() - T0))
