"""Ashrunner horde review: the ashrunner beside the clinker, and 40 ashrunners (hunting in pairs) mixed with 20
clinkers through the game camera at TRUE 1080p pixel size.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/ashrunner_crowd.py

Run after tools/blender/gf_assets/enemies/ashrunner.py. This script IMPORTS the shipped GLBs
(assets/models/enemies/ashrunner.glb and the four clinker looks), so it also proves the exported file loads, skins
and animates in a glTF importer: every copy is posed from the GLB's own actions.

Writes art/enemies/ashrunner/reports/ashrunner_crowd_review.png (lineup, the mixed horde at 1x + its silhouette +
the four-player view, the horde 2x, the gallop through the crowd), ashrunner_crowd.png (the horde, 2x nearest)
and art/enemies/ashrunner/status.json.
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
from mathutils import Quaternion, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402
import ashrunner as A  # noqa: E402

CLIPS = SPEC.ENEMY_CLIPS_REQUIRED
CLINKERS = ("clinker", "clinker_v1", "clinker_v2", "clinker_v3")
VIEW_H = SPEC.GAME_VIEW_HEIGHTS[0]          # 22 m = 1080 px (one hero); the 4-player view is 28 m
PPM = SPEC.SCREEN_H / VIEW_H


def import_glb(key):
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
    meta = C.read_json(os.path.splitext(C.model_path("enemy", key))[0] + ".meta.json")
    frames = {c: int(round(a.frame_range[1])) for c, a in acts.items()}
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts, "meta": meta, "frames": frames}


def spawn(v, loc, yaw, clip=None, frame=0.0):
    """A posed copy of an imported model (armature data shared, pose per copy)."""
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
    # the glTF importer leaves its objects in QUATERNION mode (rotation_euler would be ignored): turn the
    # imported rest rotation about world Z
    q0 = v["arm"].rotation_quaternion.copy() if v["arm"].rotation_mode == "QUATERNION" else \
        v["arm"].rotation_euler.to_quaternion()
    a2.rotation_mode = "QUATERNION"
    a2.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), yaw) @ q0
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
        me.materials.append(A._emit_mat("GFA_FLOOR", R.FLOOR))
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
    C.reset_scene(fps=A.FPS)
    pack = C.pack_dir("enemy", A.KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "crowd"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    hound = import_glb(A.KEY)
    clinkers = [import_glb(k) for k in CLINKERS]
    for i, v in enumerate([hound] + clinkers):
        v["arm"].location = (100.0 + 5 * i, 100.0, 0.0)          # originals parked off-screen
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    out = {}

    # 1. lineup: the ashrunner beside the clinker and the hero, 3/4 front (rest pose), then the game camera
    made = list(spawn(hound, (0.35, 0.0, 0.0), math.radians(-24)))
    made += list(spawn(clinkers[0], (-0.75, 0.15, 0.0), math.radians(-18)))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-1.75, 0.35, 0.0)
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 14)
    with R.toon_preview(meshes + [man], ink=0.006, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (-0.62, 0.0, 1.08), (0.28, -0.85, 0.36), 4.5)
        out["lineup"] = R.render(scene, os.path.join(work, "ashrunner_lineup.png"), 1100, 620)
    out["lineup_game"] = game_render(meshes + [man], {man.name: R.MANNEQUIN}, os.path.join(work, "ashrunner_lineup_game.png"),
                                     200, 110, (-0.6, 0.1, 0.5))
    clear_copies(made)
    C.remove_objects([man])

    # 2. the horde: 20 pairs of ashrunners (they hunt in pairs) and 20 clinkers converging on two heroes;
    # mixed facings and clip phases
    rng = random.Random(11)
    heroes = [Vector((-1.0, -0.2, 0.0)), Vector((1.2, 0.6, 0.0))]
    mans = []
    for hp, aim in zip(heroes, ((0.4, 0.9, 0.0), (0.9, 0.4, 0.0))):
        m = R.mannequin(aim_dir=aim)
        m.location = hp
        mans.append(m)
    placed = []            # (pos, radius)

    def free(p, r):
        return all((p - q).length > r + rq for q, rq in placed) and all((p - h).length > 1.0 + r for h in heroes)

    made, phases, kinds = [], [], []
    mf = hound["frames"]["move@loop"]
    tries = 0
    pairs = 0
    while pairs < 20 and tries < 40000:
        tries += 1
        tgt = heroes[rng.randrange(2)]
        ang = rng.uniform(-0.35 * math.pi, 1.25 * math.pi)
        r = rng.uniform(1.6, 6.8)
        p = tgt + Vector((math.cos(ang) * r * 1.2, math.sin(ang) * r, 0.0))
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-18, 18))
        side = Vector((math.cos(yaw), math.sin(yaw), 0.0))          # the creature's left (+X turned by yaw)
        fwd = Vector((math.sin(yaw), -math.cos(yaw), 0.0))
        p2 = p + side * rng.uniform(0.5, 0.65) + fwd * rng.uniform(-0.3, 0.3)
        if not (free(p, 0.52) and free(p2, 0.52)) or (p - p2).length < 0.45:
            continue
        placed.extend([(p, 0.52), (p2, 0.52)])
        pairs += 1
        u = rng.random()
        f0 = rng.uniform(0, mf)
        for k, q in enumerate((p, p2)):
            near = (q - tgt).length < 2.4
            if near and u < 0.5:
                clip, f = ("windup", 15.0) if k == 0 else ("attack", 5.0)
            elif u < 0.88 or near:
                clip, f = "move@loop", (f0 + k * mf * rng.uniform(0.25, 0.45)) % mf
            else:
                clip, f = "idle@loop", rng.uniform(0, hound["frames"]["idle@loop"])
            phases.append(clip)
            kinds.append("ashrunner")
            made += list(spawn(hound, q, yaw + math.radians(rng.uniform(-6, 6)), clip, f))
    n_cl = 0
    tries = 0
    while n_cl < 20 and tries < 40000:
        tries += 1
        tgt = heroes[rng.randrange(2)]
        ang = rng.uniform(-0.35 * math.pi, 1.25 * math.pi)
        r = rng.uniform(1.2, 6.5)
        p = tgt + Vector((math.cos(ang) * r * 1.2, math.sin(ang) * r, 0.0))
        if not free(p, 0.33):
            continue
        placed.append((p, 0.33))
        v = clinkers[n_cl % 4]
        n_cl += 1
        clip, f = ("move@loop", rng.uniform(0, v["frames"]["move@loop"])) if rng.random() < 0.8 else \
            ("idle@loop", rng.uniform(0, v["frames"]["idle@loop"]))
        phases.append(clip)
        kinds.append("clinker")
        made += list(spawn(v, p, face_yaw(p, tgt) + math.radians(rng.uniform(-28, 28)), clip, f))
    C.log("horde: %d ashrunners (%d pairs), %d clinkers" % (kinds.count("ashrunner"), pairs, n_cl))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    tgt = (0.1, 0.8, 0.3)
    out["crowd"] = game_render(meshes + mans, flat, os.path.join(work, "ashrunner_crowd_1x.png"), 760, 560, tgt,
                               sil_path=os.path.join(work, "ashrunner_crowd_1x_sil.png"))
    out["crowd_sil"] = os.path.join(work, "ashrunner_crowd_1x_sil.png")
    out["crowd28"] = game_render(meshes + mans, flat, os.path.join(work, "ashrunner_crowd_1x_28.png"), 600, 440, tgt,
                                 view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    clear_copies(made)
    C.remove_objects(mans)

    # 3. a pair galloping across the screen, every frame of the stride, at game size
    strip = []
    for f in range(mf):
        made = list(spawn(hound, (0.0, 0.0, 0.0), math.radians(90), "move@loop", f))
        made += list(spawn(hound, (0.1, 0.62, 0.0), math.radians(90), "move@loop", (f + 3) % mf))
        bpy.context.view_layer.update()
        p = os.path.join(work, "ashrunner_pair_f%02d.png" % f)
        game_render([o for o in made if o.type == "MESH"], {}, p, 90, 70, (0.0, 0.3, 0.3), samples=12)
        clear_copies(made)
        strip.append((f, p))

    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = upscale(out["crowd"], os.path.join(reports, "ashrunner_crowd.png"), 2)
    lineup = os.path.join(reports, "ashrunner_lineup.png")
    shutil.copyfile(out["lineup"], lineup)
    counts = {c: phases.count(c) for c in set(phases)}
    sections = [
        {"label": "The ashrunner beside the clinker (both Cinder Wastes Unmade swarm) and the 2.2 m hero (rest pose, toon preview "
                  "of the shipped GLBs)", "height": 400,
         "images": [{"path": out["lineup"], "label": "hero | clinker (SKITTER: a dark dome, a pale club, teal) | "
                                                    "ashrunner (SPRINT: a pale arrow with a burning ribcage)"}]},
        {"label": "The same three through the game camera (55 deg, %.1f px/m): TRUE size 1x, then 3x nearest" % PPM,
         "height": None, "images": [{"path": out["lineup_game"], "label": "1x"},
                                    {"path": out["lineup_game"], "label": "3x", "scale": 3}]},
        {"label": "HORDE READ: %d ashrunners in %d hunting pairs + %d clinkers (%s) around two 2.2 m heroes, TRUE 1080p pixel "
                  "size (1x)" % (kinds.count("ashrunner"), pairs, n_cl,
                                 ", ".join("%d %s" % (n, c) for c, n in sorted(counts.items(), key=lambda t: -t[1]))),
         "height": None,
         "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px)"},
                    {"path": out["crowd_sil"], "label": "1x silhouette"},
                    {"path": out["crowd28"], "label": "1x, four-player view (28 m = 1080 px)"}]},
        {"label": "The same horde, 2x nearest", "height": None, "images": [{"path": out["crowd"], "label": "2x", "scale": 2}]},
        {"label": "A hunting pair galloping across the screen: every frame of move@loop (the partner a third of a stride "
                  "behind), true pixels 3x nearest", "height": None,
         "images": [{"path": p, "label": "f%d" % f, "scale": 3} for f, p in strip]},
    ]
    notes = ["ashrunner: %s tris, textures %s, %.2f m tall, move_cycle_m %.2f (%.1f strides/s at 5.2 m/s)" % (
        hound["meta"]["tris"], "+".join("%d" % t["px"][0] for t in hound["meta"]["textures"]), hound["meta"]["size_m"],
        hound["meta"]["move_cycle_m"], 5.2 / hound["meta"]["move_cycle_m"]),
        "clinker looks: %s" % ", ".join("%s %s tris" % (v["key"], v["meta"]["tris"]) for v in clinkers),
        "Every copy here is posed from the actions inside the shipped GLBs (imported with Blender's glTF importer)."]
    layout = {"title": "Ashrunner horde read  (Swarm Hound, The Unmade)",
              "subtitle": "content key ashrunner | Swarm, Cinder Wastes | Swarmer(jitter 0.6), packs of 2-4 | verb SPRINT | "
                          "status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "swatches": [{"hex": h, "label": n} for n, h in A.PALETTE], "notes": notes}
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "ashrunner_crowd_review.png"), work)

    key = A.KEY
    outputs = [C.rel(C.model_path("enemy", key)), C.rel(os.path.splitext(C.model_path("enemy", key))[0] + ".meta.json"),
               "art/enemies/ashrunner/source/ashrunner.blend", "art/enemies/ashrunner/textures/ashrunner_basecolor.png",
               "art/enemies/ashrunner/textures/ashrunner_emissive.png", "art/enemies/ashrunner/reports/ashrunner_review.png",
               C.rel(out["sheet"]), C.rel(crowd2x), C.rel(lineup)]
    C.write_pack_status("enemy", key, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/ashrunner.py and reviewed by "
                        "enemies/ashrunner_crowd.py (40 ashrunners in pairs mixed with 20 clinkers at true game size).",
                        tier="swarm", extra={"skeleton": SPEC.SWARM_SKELETON, "faction": "unmade", "verb": "SPRINT"})
    C.log("DONE ashrunner crowd", out["sheet"])


if __name__ == "__main__":
    main()
