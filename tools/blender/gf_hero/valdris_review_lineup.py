"""Valdris review of stages 2-5: the game-size read (headless Blender 5.2, Cycles on the CPU, never EEVEE).

  blender -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/valdris_review_lineup.py -- \
          [--out art/characters/valdris/work/review]

Every subject is a SHIPPED file posed at one frame and frozen (the evaluated mesh), shaded with the pipeline's toon
preview (s3lib.make_toon_cycles: a 3-band N.L ramp x base colour + rim + emissive, output as emission):
  lineup.png   the 55 deg client camera (yaw 0, orthographic) at true 1080p pixels for a 22 m view height (49.1 px/m):
               a greybox capsule (2.3 m, r 0.55: his collider), brax.glb (+ anvil_gauntlets on weapon_R / weapon_L),
               valdris.glb (+ colossus_cannon on weapon_R) in idle_combat, walk, fire_light, bulwark_slam (launch and
               land), siege_stance, death (its last frame) and downed, and the six Cinder Wastes swarm enemies at their
               idle; the near row (bottom of the frame) faces the camera, the far row faces screen-right. Transparent film: the sheet composites it on the
               ground.
  horde.png    a full 1920 x 1080 frame at the 22 m view height: Valdris in the Siege Stance brace among 140 swarm
               enemies (the six cinder_wastes swarm files, non-overlapping at their collision radii, crowding him as the
               taunt makes them), Brax 5 m to the left of the frame; on the cinder ground.
  lineup.json  per subject: its pixel box and the mean / 10th percentile / 90th percentile CIE L* of its pixels, and the
               share of gold-hued and glowing pixels (the brief's reads: darker than every swarm enemy, gold trim and
               the anvil's top visible).
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import validate_glb as V  # noqa: E402
from s2lib import aim_ortho  # noqa: E402
from s3lib import cycles_cpu, make_toon_cycles  # noqa: E402

ROOT = V.ROOT
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.path.join(ROOT, "art", "characters", "valdris", "work", "review")
os.makedirs(OUT, exist_ok=True)
PX_PER_M = 1080.0 / 22.0
PITCH = math.radians(55.0)
C = Matrix(R.SOCKET_TO_GRIP)
CI = C.inverted()
SWARM = ["cinderling", "ashrunner", "clinker", "emberwisp", "slagspitter", "kindlejack"]
RADIUS = {"cinderling": 0.42, "ashrunner": 0.36, "clinker": 0.26, "emberwisp": 0.34, "slagspitter": 0.48, "kindlejack": 0.40}

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = 30, 1.0
LIB = bpy.data.collections.new("LIB")          # imported rigs, never rendered
scene.collection.children.link(LIB)
TOON = {}
SKIP = set()          # meshes never frozen (the gauntlets' open variants)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path, disable_bone_shape=True, import_shading="NORMALS")
    objs = [o for o in bpy.data.objects if o not in before]
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        LIB.objects.link(o)
    return objs


def attach(arm, root, sock, g):
    gw = V.world_matrices(g)
    gi = {n: i for i, n in enumerate(g.names)}
    root.parent, root.parent_type, root.parent_bone = arm, "BONE", sock
    bpy.context.view_layer.update()
    root.matrix_world = CI @ Matrix([list(r) for r in gw[gi[sock]]]) @ C
    bpy.context.view_layer.update()


def rest_pose(arm):
    arm.animation_data_create()
    arm.animation_data.action = None
    for tr in arm.animation_data.nla_tracks:
        tr.mute = True
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def toon_of(m):
    if m.name not in TOON:
        TOON[m.name] = make_toon_cycles(m)
    return TOON[m.name]


def freeze(objs, M, name):
    """Static copies of the evaluated meshes, re-placed by the 4x4 M (Blender world), toon-shaded."""
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in objs:
        if o.type != "MESH" or o.name in SKIP:
            continue
        e = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(e, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        me.transform(M)
        ob = bpy.data.objects.new("%s_%s" % (name, o.name), me)
        for i, s in enumerate(ob.material_slots):
            if s.material is not None:
                ob.material_slots[i].link = "DATA"
                me.materials[i] = toon_of(s.material)
        scene.collection.objects.link(ob)
        out.append(ob)
    return out


def pose(arm, action, frame):
    arm.animation_data.action = bpy.data.actions[action]
    arm.animation_data.action_slot = bpy.data.actions[action].slots[0]
    scene.frame_set(frame)
    bpy.context.view_layer.update()


def place(x, y, yaw_deg):
    return Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(math.radians(yaw_deg), 4, "Z")


# ---- load the shipped files ---------------------------------------------------------------------------------------------
A = os.path.join(ROOT, "assets", "models")
vobjs = import_glb(os.path.join(A, "characters", "valdris.glb"))
varm = [o for o in vobjs if o.type == "ARMATURE"][0]
rest_pose(varm)
cobjs = import_glb(os.path.join(A, "weapons", "colossus_cannon.glb"))
attach(varm, [o for o in cobjs if o.name == "colossus_cannon"][0], "weapon_R", V.Glb(os.path.join(A, "characters", "valdris.glb")))
VAL = [o for o in vobjs + cobjs if o.type == "MESH"]
bobjs = import_glb(os.path.join(A, "characters", "brax.glb"))
barm = [o for o in bobjs if o.type == "ARMATURE"][0]
rest_pose(barm)
gobjs = import_glb(os.path.join(A, "weapons", "anvil_gauntlets.glb"))
bg = V.Glb(os.path.join(A, "characters", "brax.glb"))
attach(barm, [o for o in gobjs if o.name == "anvil_gauntlets"][0], "weapon_R", bg)
off = [o for o in gobjs if o.name == "offhand"]
if off:
    attach(barm, off[0], "weapon_L", bg)
for o in gobjs:
    if o.type == "MESH" and "_open_" in o.name:
        SKIP.add(o.name)
BRAX = [o for o in bobjs + gobjs if o.type == "MESH"]
EN = {}
for k in SWARM:
    eo = import_glb(os.path.join(A, "enemies", "%s.glb" % k))
    ea = [o for o in eo if o.type == "ARMATURE"]
    if ea:
        rest_pose(ea[0])
        act = "%s_idle@loop" % k
        if act in bpy.data.actions:
            pose(ea[0], act, 0)
    EN[k] = [o for o in eo if o.type == "MESH"]


def capsule(M, name):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.55, depth=2.3 - 1.1, location=(0, 0, 1.15))
    cyl = bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.55, location=(0, 0, 0.55))
    s1 = bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.55, location=(0, 0, 2.3 - 0.55))
    s2 = bpy.context.active_object
    for o in (cyl, s1, s2):
        o.matrix_world = M @ o.matrix_world
        m = bpy.data.materials.new("grey")
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        geo, ramp, em, out = (nt.nodes.new(t) for t in ("ShaderNodeNewGeometry", "ShaderNodeValToRGB", "ShaderNodeEmission", "ShaderNodeOutputMaterial"))
        dot = nt.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = Vector((-0.45, -0.55, 0.70)).normalized()
        nt.links.new(geo.outputs["Normal"], dot.inputs[0])
        nt.links.new(dot.outputs["Value"], ramp.inputs["Fac"])
        ramp.color_ramp.interpolation = "CONSTANT"
        els = ramp.color_ramp.elements
        els[0].position, els[0].color = 0.0, (0.36 * 0.21, 0.32 * 0.21, 0.40 * 0.21, 1)
        els[1].position, els[1].color = 0.12, (0.70 * 0.21, 0.66 * 0.21, 0.66 * 0.21, 1)
        e3 = els.new(0.52)
        e3.color = (0.21, 0.21, 0.21, 1)
        nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        o.data.materials.append(m)
        o.name = name
    return [cyl, s1, s2]


# ---- the lineup ---------------------------------------------------------------------------------------------------------
subjects = []   # (label, x, y)
x = 0.0
row_y = {0: 0.0, 1: 4.2}
HERO_SHOTS = [("brax idle_combat", "brax", "brax_idle_combat@loop", 0),
              ("valdris idle_combat", "valdris", "valdris_idle_combat@loop", 0),
              ("walk f7", "valdris", "valdris_walk@loop", 7),
              ("fire_light f1 (shot)", "valdris", "valdris_fire_light", 1),
              ("bulwark launch f8", "valdris", "valdris_bulwark_slam", 8),
              ("bulwark land f21", "valdris", "valdris_bulwark_slam", 21),
              ("siege_stance", "valdris", "valdris_siege_stance@loop", 0),
              ("death (last frame)", "valdris", "valdris_death", 56),
              ("downed f0", "valdris", "valdris_downed@loop", 0)]
for row, yaw in ((0, 0.0), (1, 90.0)):
    x = 0.0
    capsule(place(x, row_y[row], yaw), "capsule_%d" % row)
    if row == 0:
        subjects.append(("greybox capsule 2.3 m r0.55", x, row_y[row]))
    x += 2.4
    for label, who, act, f in HERO_SHOTS:
        arm = varm if who == "valdris" else barm
        pose(arm, act, f)
        freeze(VAL if who == "valdris" else BRAX, place(x, row_y[row], yaw), "%s_%d_%s" % (who, row, act))
        if row == 0:
            subjects.append((label, x, row_y[row]))
        x += 2.9
    for k in SWARM:
        freeze(EN[k], place(x, row_y[row], yaw), "%s_%d" % (k, row))
        if row == 0:
            subjects.append((k, x, row_y[row]))
        x += 1.7
XMAX = x
LIB.hide_render = True
for o in LIB.objects:
    o.hide_render = True

cycles_cpu(scene, samples=8)
scene.render.film_transparent = True
scene.world = bpy.data.worlds.new("W")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
d = Vector((0.0, -math.cos(PITCH), math.sin(PITCH)))
up = Vector((0.0, math.sin(PITCH), math.cos(PITCH)))            # the camera's screen-up in world space
v_lo, v_hi = -1.6 * math.sin(PITCH), (row_y[1] + 1.4) * math.sin(PITCH) + 2.6 * math.cos(PITCH)
wm = XMAX + 1.2
W = int(round(wm * PX_PER_M))
H = int(round((v_hi - v_lo) * PX_PER_M))
cx = XMAX / 2 - 1.2 + 0.6
vc = (v_lo + v_hi) / 2
# the target must project to (cx, vc): the point (cx, y, z) with y*sin + z*cos = vc on the camera ray through it
target = Vector((cx, vc * math.sin(PITCH), vc * math.cos(PITCH)))
aim_ortho(scene, target, d, max(W, H) / PX_PER_M, dist=40.0)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = W, H, 100
scene.render.filepath = os.path.join(OUT, "lineup_raw.png")
bpy.ops.render.render(write_still=True)


def proj(p):
    """world point -> pixel (x right, y down) in the lineup render."""
    rel = Vector(p) - target
    right = Vector((1.0, 0.0, 0.0))
    return (W / 2 + rel.dot(right) * PX_PER_M, H / 2 - rel.dot(up) * PX_PER_M)


boxes = []
for label, sx, sy in subjects:
    wide = 0.85 if label in SWARM else 1.45
    x0, _ = proj((sx - wide, sy, 0.0))
    x1, _ = proj((sx + wide, sy, 0.0))
    _, y0 = proj((sx, sy + 1.5, 3.0))
    _, y1 = proj((sx, sy - 1.5, 0.0))
    boxes.append({"label": label, "box": [int(max(0, x0)), int(max(0, y0)), int(min(W, x1)), int(min(H, y1))]})
json.dump({"px_per_m": PX_PER_M, "size": [W, H], "subjects": boxes}, open(os.path.join(OUT, "lineup_boxes.json"), "w"), indent=1)
print("[lineup] rendered", W, H, flush=True)

# ---- the horde frame ----------------------------------------------------------------------------------------------------
for o in list(scene.collection.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
rng = random.Random(7)
pose(varm, "valdris_siege_stance@loop", 0)
freeze(VAL, place(0.0, 0.0, -25.0), "valdris_h")
pose(barm, "brax_idle_combat@loop", 0)
freeze(BRAX, place(-5.0, 1.0, 20.0), "brax_h")
placed = [(0.0, 0.0, 0.9), (-5.0, 1.0, 0.6)]
tries = 0
count = 0
while count < 140 and tries < 20000:
    tries += 1
    k = rng.choice(SWARM)
    r = RADIUS[k]
    # 55 % crowd him (taunt), the rest fill the view
    if rng.random() < 0.55:
        a, dist = rng.uniform(0, 2 * math.pi), rng.uniform(1.3, 4.5)
        px, py = dist * math.cos(a), dist * math.sin(a)
    else:
        px, py = rng.uniform(-18, 18), rng.uniform(-9, 13)
    if any((px - qx) ** 2 + (py - qy) ** 2 < (r + qr) ** 2 for qx, qy, qr in placed):
        continue
    placed.append((px, py, r))
    yaw = math.degrees(math.atan2(-px, py)) + 180.0 + rng.uniform(-35, 35)     # facing roughly toward him
    freeze(EN[k], place(px, py, yaw), "h_%s_%d" % (k, count))
    count += 1
ground = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
ground.data.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
gm = bpy.data.materials.new("cinder_ground")
gm.use_nodes = True
nt = gm.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
e, o_, ck, tc = (nt.nodes.new(t) for t in ("ShaderNodeEmission", "ShaderNodeOutputMaterial", "ShaderNodeTexNoise", "ShaderNodeTexCoord"))
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.inputs["A"].default_value = (0.060, 0.030, 0.020, 1)
mix.inputs["B"].default_value = (0.105, 0.060, 0.040, 1)
ck.inputs["Scale"].default_value = 0.35
nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
nt.links.new(ck.outputs["Fac"], mix.inputs["Factor"])
nt.links.new(mix.outputs["Result"], e.inputs["Color"])
nt.links.new(e.outputs[0], o_.inputs["Surface"])
ground.data.materials.append(gm)
scene.collection.objects.link(ground)
scene.render.film_transparent = False
target = Vector((0.0, 1.0, 0.9))
aim_ortho(scene, target, d, 22.0 * 1920 / 1080.0, dist=40.0)
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.filepath = os.path.join(OUT, "horde_raw.png")
bpy.ops.render.render(write_still=True)
json.dump({"enemies": count, "view_height_m": 22.0, "size": [1920, 1080]}, open(os.path.join(OUT, "horde.json"), "w"), indent=1)
print("[lineup] horde rendered with", count, "enemies", flush=True)
