"""Clinker family review: the four shipped looks side by side, and a 40-copy horde through the game camera.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/clinker_crowd.py

Run after tools/blender/gf_assets/enemies/clinker.py has built all four variants (base, v1, v2, v3). This
script IMPORTS the shipped GLBs (assets/models/enemies/clinker*.glb), so it also proves the exported files
load, skin and animate in a glTF importer: every copy is posed from the GLB's own actions.

Writes art/enemies/clinker/reports/clinker_family_review.png (lineup, in-game lineup, the 40-copy crowd at
TRUE 1080p pixel size + its silhouette, the skitter cycle at game size), clinker_crowd.png (the crowd, 2x
nearest), clinker_lineup.png and art/enemies/clinker/status.json.
"""
import math
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402
import clinker as K  # noqa: E402

ORDER = ("base", "v1", "v2", "v3")
CLIPS = SPEC.ENEMY_CLIPS_REQUIRED
VIEW_H = SPEC.GAME_VIEW_HEIGHTS[0]          # 22 m = 1080 px (one hero); the 4-player view is 28 m
PPM = SPEC.SCREEN_H / VIEW_H


def import_variant(key):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=C.model_path("enemy", key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH")
    arm.name, mesh.name = key + "_ARM", key + "_MESH"
    acts = {}
    for c in CLIPS:
        a = bpy.data.actions.get("%s_%s" % (key, c))
        if a is None:
            raise RuntimeError("%s.glb has no clip %s_%s" % (key, key, c))
        a.use_fake_user = True
        acts[c] = a
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts}


def spawn(v, loc, yaw, clip=None, frame=0.0):
    """A posed copy of an imported variant (armature data shared, pose per copy)."""
    col = bpy.context.scene.collection
    a2 = v["arm"].copy()
    col.objects.link(a2)
    a2.animation_data_clear()
    m2 = v["mesh"].copy()
    m2.data = v["mesh"].data.copy()       # own data: the preview swaps slot materials per object data
    col.objects.link(m2)
    m2.parent = a2
    m2.matrix_parent_inverse = v["mesh"].matrix_parent_inverse.copy()
    for mod in m2.modifiers:
        if mod.type == "ARMATURE":
            mod.object = a2
    a2.location = loc
    a2.rotation_euler = (0.0, 0.0, yaw)
    for pb in a2.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    if clip:
        a2.pose.apply_pose_from_action(v["acts"][clip], evaluation_time=frame)
    return a2, m2


def face_yaw(frm, to):
    d = Vector(to) - Vector(frm)
    return math.atan2(d.x, -d.y)          # creatures face -Y: yaw turns -Y onto d


def floor():
    f = bpy.data.objects.get("GFA_FLOOR")
    if f is None:
        me = bpy.data.meshes.new("GFA_FLOOR")
        me.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
        f = bpy.data.objects.new("GFA_FLOOR", me)
        bpy.context.scene.collection.objects.link(f)
        me.materials.append(K._emit_mat("GFA_FLOOR", R.FLOOR))
    return f


def game_render(objs, flat, path, w, h, target, sil_path=None, ink=0.012, samples=16, view_h=VIEW_H):
    """Game camera (orthographic, 55 deg pitch, yaw 0) at TRUE 1080p pixel size, a w x h crop."""
    scene = bpy.context.scene
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    d = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
    fl = floor()
    R.setup_cycles(scene, samples, bg=R.FLOOR)
    fl.hide_render = False
    with R.toon_preview(objs, ink=ink, flat=flat):
        R.aim(scene, target, d, view_h * max(w, h) / SPEC.SCREEN_H)
        R.render(scene, path, w, h)
    if sil_path:
        R.setup_workbench_flat(scene)
        fl.hide_render = True
        R.aim(scene, target, d, view_h * max(w, h) / SPEC.SCREEN_H)
        R.render(scene, sil_path, w, h)
        fl.hide_render = False
    return path


def clear_copies(objs):
    meshes = [o for o in objs if o.type == "MESH"]
    arms = [o for o in objs if o.type == "ARMATURE"]
    C.remove_objects(meshes)
    for o in arms:
        bpy.data.objects.remove(o)


def upscale(src, dst, k):
    """Nearest-neighbour k x enlargement (game pixels stay visible)."""
    import numpy as np
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    big = px.reshape(h, w, 4).repeat(k, 0).repeat(k, 1)
    o = bpy.data.images.new("gfa_up", w * k, h * k, alpha=False)
    o.pixels.foreach_set(big.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(img)
    bpy.data.images.remove(o)
    return dst


def main():
    C.reset_scene(fps=K.FPS)
    pack = C.pack_dir("enemy", K.CONTENT_KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "family"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    variants = []
    for i, vk in enumerate(ORDER):
        v = import_variant(K.VARIANTS[vk]["key"])
        v["vk"] = vk
        v["V"] = K.VARIANTS[vk]
        v["meta"] = C.read_json(os.path.splitext(C.model_path("enemy", v["key"]))[0] + ".meta.json")
        for o in (v["arm"],):
            o.location = (100.0 + 5 * i, 100.0, 0.0)          # originals parked off-screen
        variants.append(v)
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    out = {}

    # 1. lineup: the four looks at rest, 3/4 front, beside the mannequin
    made = []
    for i, v in enumerate(variants):
        made += list(spawn(v, (-0.3 + 0.95 * i, 0.0, 0.0), math.radians(-18)))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    R.setup_cycles(scene, 14)
    with R.toon_preview(meshes, ink=0.005):
        R.aim(scene, (1.12, 0.0, 0.26), (0.28, -0.85, 0.42), 3.95)
        out["lineup"] = R.render(scene, os.path.join(work, "clinker_family_lineup.png"), 1500, 520)
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-1.45, 0.25, 0.0)
    bpy.context.view_layer.update()
    # 1b. the same lineup through the game camera at true size
    out["lineup_game"] = game_render(meshes + [man], {man.name: R.MANNEQUIN}, os.path.join(work, "clinker_family_lineup_game.png"),
                                     250, 130, (0.55, 0.1, 0.4))
    clear_copies(made)
    C.remove_objects([man])

    # 2. the horde: 40 copies (10 of each look) converging on two heroes; mixed facings and clip phases
    rng = random.Random(7)
    heroes = [Vector((-0.7, -0.3, 0.0)), Vector((0.8, 0.35, 0.0))]
    mans = []
    for hp, aim in zip(heroes, ((0.4, 0.9, 0.0), (0.9, 0.4, 0.0))):
        m = R.mannequin(aim_dir=aim)
        m.location = hp
        mans.append(m)
    pts = []
    tries = 0
    while len(pts) < 40 and tries < 20000:
        tries += 1
        c = heroes[rng.randrange(2)]
        r = rng.uniform(0.95, 4.2)
        ang = rng.uniform(-0.25 * math.pi, 1.15 * math.pi)      # they pour in from the top and the sides
        p = c + Vector((math.cos(ang) * r * 1.15, math.sin(ang) * r, 0.0))
        if any((p - q).length < 0.62 for q in pts) or any((p - h).length < 0.85 for h in heroes):
            continue
        pts.append(p)
    made = []
    phases = []
    for i, p in enumerate(pts):
        v = variants[i % 4]
        tgt = min(heroes, key=lambda h: (h - p).length)
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-28, 28))
        u = rng.random()
        mv = v["V"]["motion"]
        if u < 0.68:
            clip, f = "move@loop", rng.uniform(0, mv["move_frames"])
        elif u < 0.82:
            clip, f = "idle@loop", rng.uniform(0, mv["idle_frames"])
        elif u < 0.9:
            clip, f = "windup", 15.0
        elif u < 0.96:
            clip, f = "attack", rng.choice((3.0, 5.0))
        else:
            clip, f = "hit", 2.0
        phases.append(clip)
        made += list(spawn(v, p, yaw, clip, f))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    out["crowd"] = game_render(meshes + mans, flat, os.path.join(work, "clinker_crowd_1x.png"), 560, 430, (0.1, 0.6, 0.3),
                               sil_path=os.path.join(work, "clinker_crowd_1x_sil.png"))
    out["crowd_sil"] = os.path.join(work, "clinker_crowd_1x_sil.png")
    # the 4-player view (28 m = 1080 px): the same horde a little smaller
    out["crowd28"] = game_render(meshes + mans, flat, os.path.join(work, "clinker_crowd_1x_28.png"), 440, 340, (0.1, 0.6, 0.3),
                                 view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    clear_copies(made)
    C.remove_objects(mans)

    # 3. the skitter cycle at game size, per look (one copy, 5 frames of move@loop, 3/4 toward the camera)
    skitter = []
    for v in variants:
        n = v["V"]["motion"]["move_frames"]
        row = []
        for k in range(5):
            f = n * k / 5.0
            made = list(spawn(v, (0.0, 0.0, 0.0), math.radians(-30), "move@loop", f))
            bpy.context.view_layer.update()
            p = os.path.join(work, "%s_skitter_%d.png" % (v["key"], k))
            game_render([o for o in made if o.type == "MESH"], {}, p, 50, 50, (0.0, -0.05, 0.2), samples=12)
            clear_copies(made)
            row.append((f, p))
        skitter.append((v, row))

    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = upscale(out["crowd"], os.path.join(reports, "clinker_crowd.png"), 2)
    lineup = os.path.join(reports, "clinker_lineup.png")
    shutil.copyfile(out["lineup"], lineup)

    counts = {c: phases.count(c) for c in set(phases)}
    sections = [
        {"label": "The clinker family: base + three shell variants, one GLB each (rest pose, toon preview of the shipped files)",
         "height": 400, "images": [{"path": out["lineup"], "label": "   ".join("%s = %s.glb" % (v["V"]["name"], v["key"]) for v in variants)}]},
        {"label": "Through the game camera (55 deg, %.1f px/m): the lineup at TRUE size, then 3x nearest" % PPM, "height": None,
         "images": [{"path": out["lineup_game"], "label": "1x"}, {"path": out["lineup_game"], "label": "3x", "scale": 3}]},
        {"label": "HORDE READ: 40 clinkers (10 of each look; %s) around two 2.2 m heroes, TRUE 1080p pixel size (1x)" % (
            ", ".join("%d %s" % (n, c) for c, n in sorted(counts.items(), key=lambda t: -t[1]))), "height": None,
         "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px)"},
                    {"path": out["crowd_sil"], "label": "1x silhouette"},
                    {"path": out["crowd28"], "label": "1x, four-player view (28 m = 1080 px)"}]},
        {"label": "The same horde, 2x nearest", "height": None, "images": [{"path": out["crowd"], "label": "2x", "scale": 2}]},
        {"label": "SKITTER at game size: move@loop, 5 frames per look, true pixels shown 3x nearest", "height": None,
         "images": sum([[{"path": p, "label": "%s f%.0f" % (v["V"]["name"] if k == 0 else "", f), "scale": 3}
                         for k, (f, p) in enumerate(row)] for v, row in skitter], [])},
    ]
    notes = ["%s: %s tris, textures %s, %.2f m tall, move_cycle_m %.2f, %s" % (
        v["key"], v["meta"]["tris"], "+".join("%d" % t["px"][0] for t in v["meta"]["textures"]),
        v["meta"]["size_m"], v["meta"]["move_cycle_m"], "mirrored (3 limbs right)" if v["meta"]["mirrored"] else "3 limbs left")
        for v in variants]
    notes.append("Every copy here is posed from the actions inside the shipped GLBs (imported with Blender's glTF importer).")
    layout = {"title": "Clinker family + horde read  (E1 Shardling, The Unmade)",
              "subtitle": "content key clinker | Swarm, Cinder Wastes | Swarmer(jitter 1.0), packs of 6-10 | verb SKITTER | "
                          "status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "swatches": [{"hex": h, "label": n} for n, h in K.PALETTE], "notes": notes}
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "clinker_family_review.png"), work)

    # pack status (all four looks)
    outputs = []
    for v in variants:
        key = v["key"]
        outputs += [C.rel(C.model_path("enemy", key)), C.rel(os.path.splitext(C.model_path("enemy", key))[0] + ".meta.json"),
                    "art/enemies/clinker/source/%s.blend" % key, "art/enemies/clinker/textures/%s_basecolor.png" % key,
                    "art/enemies/clinker/textures/%s_emissive.png" % key, "art/enemies/clinker/reports/%s_review.png" % key]
    outputs += [C.rel(out["sheet"]), C.rel(crowd2x), C.rel(lineup)]
    C.write_pack_status("enemy", K.CONTENT_KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/clinker.py (--variant base|v1|v2|v3) and reviewed "
                        "by enemies/clinker_crowd.py. Four looks of the content key clinker, one GLB each, identical "
                        "GF_Swarm_v1 skeleton, sockets and clip suffixes.", tier="swarm",
                        extra={"variants": {v["key"]: v["V"]["name"] for v in variants}, "skeleton": SPEC.SWARM_SKELETON})
    C.log("DONE clinker family", out["sheet"])


if __name__ == "__main__":
    main()
