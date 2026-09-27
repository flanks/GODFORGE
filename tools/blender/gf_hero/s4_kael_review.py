"""Kael, stages 3 and 4: the review renders for the record (headless Blender 5.2, Cycles on the CPU + Workbench).

  blender -b -P tools/blender/gf_hero/s4_kael_review.py -- --stage3     the rig: rest turnaround (toon, the serpent_smg on
                                                                          weapon_R), dominant-bone weights, the skeleton
                                                                          (bone heads / tails projected for the sheet), and
                                                                          the check poses (baked clip frames, cloth included)
  blender -b -P tools/blender/gf_hero/s4_kael_review.py -- --stage4     every clip at its key frames (front three-quarter
                                                                          toon over a 0.5 m grid) + the client camera
                                                                          (orthographic 55 deg, 22 m = 1080 px, true pixels)

Opens production/kael_anim.blend (s4_anim.py + s4_kael_cloth.py). The toon is s3lib.make_toon_cycles on the stage-2
atlas (and on the weapon GLB's own textures); the GPU is shared, so Cycles runs on the CPU at a few samples (the toon is
an emission shader). Renders -> work/renders/stage3|stage4/ (local); the stage-4 names (<clip>/fNNN_front.png) are
the ones s5_sheets.py reads for its "stage 4 source" column. The sheets: kael_review_sheets.py (PIL).
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import aim_ortho, az_dir, log, render_still, script_args, setup_workbench, write_json  # noqa: E402
from s3lib import cycles_cpu, hero_paths, make_toon_cycles  # noqa: E402

KEY = "kael"
argv = script_args(__doc__)
P = hero_paths(KEY)
A = P["A"]
MAN = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=os.path.join(A, "production", "%s_anim.blend" % KEY))
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm]
weapon = [o for o in scene.objects if o.type == "MESH" and o.name.startswith("PREVIEW_")]
for tr in arm.animation_data.nla_tracks:
    tr.mute = True
CLOSE = ((0.0, -0.05, 1.08), 2.75)


def rest():
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    scene.frame_set(0)
    bpy.context.view_layer.update()


def pose(clip, f):
    act = bpy.data.actions[MAN["clips"][clip]["action"]]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    scene.frame_set(f)
    bpy.context.view_layer.update()


def emission_mat(name, rgba):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e, o = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeOutputMaterial")
    e.inputs["Color"].default_value = rgba
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def setup_toon():
    toon = {}
    for o in parts + weapon:
        for sl in o.material_slots:
            M = sl.material
            if M is None:
                continue
            if M.name not in toon:
                toon[M.name] = make_toon_cycles(M)
            sl.link = "OBJECT"
            sl.material = toon[M.name]
    grid = bpy.data.objects.new("GRID", bpy.data.meshes.new("GRID"))
    grid.data.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new("grid")
    gm.use_nodes = True
    nt = gm.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em, outn, ck, tc = (nt.nodes.new(t) for t in ("ShaderNodeEmission", "ShaderNodeOutputMaterial", "ShaderNodeTexChecker", "ShaderNodeTexCoord"))
    ck.inputs["Scale"].default_value = 12.0
    ck.inputs["Color1"].default_value = (0.06, 0.06, 0.075, 1)
    ck.inputs["Color2"].default_value = (0.095, 0.09, 0.115, 1)
    nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
    nt.links.new(ck.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], outn.inputs["Surface"])
    grid.data.materials.append(gm)
    scene.collection.objects.link(grid)
    floor = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
    floor.data.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    floor.data.materials.append(emission_mat("ground", (0.030, 0.034, 0.030, 1)))
    scene.collection.objects.link(floor)
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.045, 1)
    cycles_cpu(scene, samples=6)
    return grid, floor


def ingame(path, yaw=0.0, px=160):
    p = math.radians(55.0)
    y = math.radians(yaw)
    d = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
    aim_ortho(scene, (0.0, 0.0, 0.9), d, 22.0 * px / 1080.0)
    render_still(scene, path, px)


def stage3():
    out = os.path.join(A, "work", "renders", "stage3")
    os.makedirs(out, exist_ok=True)
    info = {"views": {}, "poses": []}
    # 1. dominant-bone weights (Workbench, a colour per bone) and the skeleton, at rest
    rest()
    import colorsys
    import random
    bones = [b.name for b in arm.data.bones if b.use_deform]
    rnd = random.Random(7)
    col = {}
    for i, b in enumerate(bones):
        h = (i * 0.61803) % 1.0
        col[b] = colorsys.hsv_to_rgb(h, 0.55 + 0.35 * rnd.random(), 0.65 + 0.35 * rnd.random())
    for o in parts:
        names = {g.index: g.name for g in o.vertex_groups}
        me = o.data
        ca = me.color_attributes.new("gf_dom", "BYTE_COLOR", "POINT")
        for v in me.vertices:
            g = max(v.groups, key=lambda g_: g_.weight) if v.groups else None
            c = col.get(names[g.group], (0.5, 0.5, 0.5)) if g else (1, 0, 1)
            ca.data[v.index].color = (c[0], c[1], c[2], 1.0)
        me.color_attributes.active_color = ca
    for o in weapon:
        o.hide_render = True
    setup_workbench(scene, color_type="VERTEX", bg=(0.13, 0.13, 0.15))
    for view, az in (("front", 0), ("back", 180)):
        aim_ortho(scene, CLOSE[0], az_dir(az), CLOSE[1] * 1.05)
        render_still(scene, os.path.join(out, "weights_%s.png" % view), 420, 560)
    # skeleton: Workbench x-ray of the body, bone heads / tails projected to the image
    setup_workbench(scene, color_type="SINGLE", bg=(0.13, 0.13, 0.15))
    scene.display.shading.single_color = (0.55, 0.55, 0.6)
    scene.display.shading.show_xray = True
    scene.display.shading.xray_alpha = 0.35
    for view, az in (("front", 0), ("side", 90)):
        cam = aim_ortho(scene, CLOSE[0], az_dir(az), CLOSE[1] * 1.05)
        scene.render.resolution_x, scene.render.resolution_y = 420, 560
        bpy.context.view_layer.update()
        segs = []
        for b in arm.data.bones:
            h = world_to_camera_view(scene, cam, arm.matrix_world @ b.head_local)
            t = world_to_camera_view(scene, cam, arm.matrix_world @ b.tail_local)
            kind = "socket" if b.name in R.SOCKET_NAMES else ("extra" if b.name.startswith("x_") else
                                                               ("twist" if "twist" in b.name else "core"))
            segs.append({"bone": b.name, "kind": kind, "h": [h.x, 1 - h.y], "t": [t.x, 1 - t.y]})
        info["views"]["skeleton_" + view] = segs
        render_still(scene, os.path.join(out, "skeleton_%s.png" % view), 420, 560)
    scene.display.shading.show_xray = False
    for o in parts:
        o.data.color_attributes.remove(o.data.color_attributes["gf_dom"])
    for o in weapon:
        o.hide_render = False
    # 2. toon: the rest turnaround with the gun on weapon_R, and the check poses (baked stage-4 frames, cloth posed)
    grid, floor = setup_toon()
    grid.hide_render, floor.hide_render = False, True
    for view, az in (("front", 0), ("front34R", -35), ("side", -90), ("back", 180)):
        aim_ortho(scene, CLOSE[0], az_dir(az, 6), CLOSE[1])
        render_still(scene, os.path.join(out, "rest_%s.png" % view), 360, 440)
    checks = [("idle_combat", 0, "the aim: serpent_smg on weapon_R"), ("fire_heavy", 7, "two-handed shot"),
              ("fan_of_blades", 8, "the fan"), ("run", 5, "run stride"), ("shadow_roll", 6, "the roll, upside down"),
              ("get_up", 16, "kneeling push-up"), ("bullet_ballet", 0, "twin stance"), ("idle_signature", 70, "the ghost hand")]
    for clip, f, what in checks:
        pose(clip, f)
        tag = "%s_f%03d" % (clip, f)
        for view, az, el in (("front", 28, 10), ("right", -60, 8)):
            aim_ortho(scene, CLOSE[0], az_dir(az, el), CLOSE[1])
            render_still(scene, os.path.join(out, "pose_%s_%s.png" % (tag, view)), 300, 360)
        info["poses"].append({"clip": clip, "frame": f, "what": what, "tag": tag})
        log("stage 3 pose", tag)
    rest()
    write_json(os.path.join(out, "review.json"), info)


def stage4():
    out = os.path.join(A, "work", "renders", "stage4")
    os.makedirs(out, exist_ok=True)
    grid, floor = setup_toon()
    info = {}
    for clip in MAN["order"]:
        c = MAN["clips"][clip]
        frames = list(c["key_frames"])[:7]
        if c["loop"] and c["frames"] not in frames:
            frames = frames[:6] + [c["frames"]]
        grid.hide_render, floor.hide_render = False, True
        for f in frames:
            pose(clip, f)
            aim_ortho(scene, CLOSE[0], az_dir(28, 10), CLOSE[1])
            render_still(scene, os.path.join(out, clip, "f%03d_front.png" % f), 300, 360)
        grid.hide_render, floor.hide_render = True, False
        mid = frames[min(len(frames) - 1, max(1, len(frames) // 2))]
        pose(clip, mid)
        ingame(os.path.join(out, clip, "f%03d_ingame0.png" % mid))
        info[clip] = {"frames": frames, "ingame_frame": mid}
        log("stage 4 renders", clip, frames)
    rest()
    write_json(os.path.join(out, "review.json"), info)


if "--stage3" in argv:
    stage3()
if "--stage4" in argv:
    stage4()
