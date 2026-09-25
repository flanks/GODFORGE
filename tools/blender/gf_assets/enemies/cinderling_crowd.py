"""Cinderling horde review: the cinderling beside the clinker and the hero, and a 40-cinderling horde mixed
with 20 clinkers through the game camera at TRUE 1080p pixel size.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/cinderling_crowd.py

Run after tools/blender/gf_assets/enemies/cinderling.py. This script IMPORTS the shipped GLBs
(assets/models/enemies/cinderling.glb and the four clinker looks), so it also proves the exported file loads,
skins and animates in a glTF importer: every copy is posed from the GLB's own actions.

Writes art/enemies/cinderling/reports/cinderling_crowd_review.png (lineup, lineup at game size, the horde at
1x + silhouette + value only + the four-player view, the horde 2x, the hop cycle at game size),
cinderling_crowd.png (the horde, 2x nearest) and art/enemies/cinderling/status.json.

Helpers adapted from enemies/clinker_crowd.py (copied, so the two reviews never depend on each other).
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "cinderling"
LOOKS = ("cinderling", "cinderling_v1", "cinderling_v2")
CLINKERS = ("clinker", "clinker_v1", "clinker_v2", "clinker_v3")
CLIPS = SPEC.ENEMY_CLIPS_REQUIRED
VIEW_H = SPEC.GAME_VIEW_HEIGHTS[0]          # 22 m = 1080 px (one hero); the 4-player view is 28 m
PPM = SPEC.SCREEN_H / VIEW_H
FLOOR_HEX = R.FLOOR


def import_glb(key):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=C.model_path("enemy", key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH")
    arm.name, mesh.name = key + "_ARM", key + "_MESH"
    acts = {}
    for a in bpy.data.actions:
        if a.name.startswith(key + "_"):
            clip = a.name[len(key) + 1:]
            if clip in CLIPS or clip == "spawn":
                a.use_fake_user = True
                acts[clip] = a
    missing = [c for c in CLIPS if c not in acts]
    if missing:
        raise RuntimeError("%s.glb is missing clips %s" % (key, missing))
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    meta = C.read_json(os.path.splitext(C.model_path("enemy", key))[0] + ".meta.json")
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts, "meta": meta}


def spawn(v, loc, yaw, clip=None, frame=0.0):
    """A posed copy of an imported GLB (armature data shared, pose per copy)."""
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


def emit_mat(name, hexc):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = C.hex_linear(hexc)
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def floor():
    f = bpy.data.objects.get("GFA_FLOOR")
    if f is None:
        me = bpy.data.meshes.new("GFA_FLOOR")
        me.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
        f = bpy.data.objects.new("GFA_FLOOR", me)
        bpy.context.scene.collection.objects.link(f)
        me.materials.append(emit_mat("GFA_FLOOR", FLOOR_HEX))
    return f


def glow_faces(mesh):
    """Indices of the faces whose emissive texel (at the face's UV centre) is a bright orange glow: the
    cinderling's maw. Used to keep the preview's inverted-hull ink out of the concave throat (the engine's
    N.V ink edge draws nothing there; see cinderling.ink_hull_without_maw)."""
    mat = mesh.material_slots[0].material if mesh.material_slots else None
    img = None
    if mat:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for lk in n.inputs["Emission Color"].links:
                    if lk.from_node.type == "TEX_IMAGE":
                        img = lk.from_node.image
    if img is None or not mesh.data.uv_layers:
        return set()
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    uvl = mesh.data.uv_layers.active.data
    out = set()
    for p in mesh.data.polygons:
        u = sum(uvl[i].uv.x for i in p.loop_indices) / p.loop_total
        v = sum(uvl[i].uv.y for i in p.loop_indices) / p.loop_total
        c = px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int((u % 1.0) * w)))]
        if c[0] > 0.45 and c[2] < 0.35:
            out.add(p.index)
    return out


def install_ink_filter(skip):
    """Wrap gfa_render.add_ink_hull for this review: meshes named in `skip` ({mesh data name: face ids}) lose
    the hull faces over those faces."""
    orig = R.add_ink_hull

    def add_ink_hull(obj, thickness):
        hull = orig(obj, thickness)
        ids = skip.get(obj.get("gfa_src", ""), set())
        if ids:
            bm = bmesh.new()
            bm.from_mesh(hull.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in ids if i < len(bm.faces)], context="FACES")
            bm.to_mesh(hull.data)
            bm.free()
        return hull
    R.add_ink_hull = add_ink_hull


def game_render(objs, flat, path, w, h, target, sil_path=None, ink=0.012, samples=16, view_h=VIEW_H):
    """Game camera (orthographic, 55 deg pitch, yaw 0) at TRUE 1080p pixel size, a w x h crop."""
    scene = bpy.context.scene
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    d = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
    fl = floor()
    R.setup_cycles(scene, samples, bg=FLOOR_HEX)
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


def _load_px(src):
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4), w, h


def _save_px(px, dst):
    h, w = px.shape[:2]
    o = bpy.data.images.new("gfa_px", w, h, alpha=False)
    o.pixels.foreach_set(px.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    return dst


def upscale(src, dst, k):
    """Nearest-neighbour k x enlargement (game pixels stay visible)."""
    px, w, h = _load_px(src)
    return _save_px(px.repeat(k, 0).repeat(k, 1), dst)


def value_only(src, dst):
    """The same image as luminance only (Rec. 601): does the horde read by value?"""
    px, w, h = _load_px(src)
    y = px[..., 0] * 0.299 + px[..., 1] * 0.587 + px[..., 2] * 0.114
    out = px.copy()
    out[..., 0] = out[..., 1] = out[..., 2] = y
    return _save_px(out, dst)


def main():
    C.reset_scene(fps=30)
    pack = C.pack_dir("enemy", KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "crowd"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    looks = [import_glb(k) for k in LOOKS if os.path.exists(C.model_path("enemy", k))]
    cin = looks[0]
    clinkers = [import_glb(k) for k in CLINKERS if os.path.exists(C.model_path("enemy", k))]
    for i, v in enumerate(looks + clinkers):
        v["arm"].location = (100.0 + 5 * i, 100.0, 0.0)          # originals parked off-screen
        v["mesh"]["gfa_src"] = v["key"]
    skip = {v["key"]: glow_faces(v["mesh"]) for v in looks}
    C.log("maw faces without preview ink:", {k: len(x) for k, x in skip.items()})
    install_ink_filter(skip)
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    out = {}

    # 1. lineup: hero, the three cinderling looks at rest, the base loaded (wind-up), two clinker looks
    made = []
    for i, v in enumerate(looks):
        made += list(spawn(v, (1.1 * i, 0.0, 0.0), math.radians(-20)))
    made += list(spawn(cin, (1.1 * len(looks) + 0.05, 0.0, 0.0), math.radians(-20), "windup", 15.0))
    for i, v in enumerate(clinkers[:2]):
        made += list(spawn(v, (1.1 * len(looks) + 1.15 + 0.95 * i, 0.05, 0.0), math.radians(-25)))
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-1.15, 0.3, 0.0)
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    R.setup_cycles(scene, 14)
    with R.toon_preview(meshes + [man], ink=0.006, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (2.2, 0.1, 0.62), (0.25, -0.85, 0.45), 7.4)
        out["lineup"] = R.render(scene, os.path.join(work, "cinderling_lineup.png"), 1500, 560)
    out["lineup_game"] = game_render(meshes + [man], {man.name: R.MANNEQUIN}, os.path.join(work, "cinderling_lineup_game.png"),
                                     380, 130, (2.2, 0.15, 0.45))
    clear_copies(made)
    C.remove_objects([man])

    # 2. the horde: 40 cinderlings + 20 clinkers (5 of each look) converging on two heroes
    rng = random.Random(11)
    heroes = [Vector((-0.8, -0.3, 0.0)), Vector((0.9, 0.4, 0.0))]
    mans = []
    for hp, aim in zip(heroes, ((0.4, 0.9, 0.0), (0.9, 0.4, 0.0))):
        m = R.mannequin(aim_dir=aim)
        m.location = hp
        mans.append(m)
    placed = []                                   # (position, radius)

    def place(n, r_self, r_min, r_max):
        pts, tries = [], 0
        while len(pts) < n and tries < 40000:
            tries += 1
            c = heroes[rng.randrange(2)]
            r = rng.uniform(r_min, r_max)
            ang = rng.uniform(-0.3 * math.pi, 1.2 * math.pi)       # they pour in from the top and the sides
            p = c + Vector((math.cos(ang) * r * 1.25, math.sin(ang) * r, 0.0))
            if any((p - q).length < r_self + rq for q, rq in placed) or any((p - hh).length < 0.9 + r_self for hh in heroes):
                continue
            placed.append((p, r_self))
            pts.append(p)
        return pts
    cin_pts = place(40, 0.46, 1.2, 5.2)
    clk_pts = place(20, 0.27, 1.0, 5.0)
    made, phases = [], {}

    def pick(v, is_cin):
        u = rng.random()
        if u < 0.66:
            return "move@loop", rng.uniform(0, v["acts"]["move@loop"].frame_range[1])
        if u < 0.8:
            return "idle@loop", rng.uniform(0, 40)
        if u < 0.9:
            return "windup", 15.0
        if u < 0.96:
            return "attack", rng.choice((3.0, 5.0))
        return "hit", 2.0
    for i, p in enumerate(cin_pts + clk_pts):
        is_cin = i < len(cin_pts)
        v = looks[i % len(looks)] if is_cin else clinkers[(i - len(cin_pts)) % max(1, len(clinkers))]
        tgt = min(heroes, key=lambda hh: (hh - p).length)
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-25, 25))
        clip, f = pick(v, is_cin)
        phases.setdefault("cinderling" if is_cin else "clinker", []).append(clip)
        a2, m2 = spawn(v, p, yaw, clip, f)
        m2["gfa_src"] = v["key"]
        made += [a2, m2]
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    tgt = (0.1, 0.9, 0.3)
    out["crowd"] = game_render(meshes + mans, flat, os.path.join(work, "cinderling_crowd_1x.png"), 740, 540, tgt,
                               sil_path=os.path.join(work, "cinderling_crowd_1x_sil.png"))
    out["crowd_sil"] = os.path.join(work, "cinderling_crowd_1x_sil.png")
    out["crowd_val"] = value_only(out["crowd"], os.path.join(work, "cinderling_crowd_1x_value.png"))
    out["crowd28"] = game_render(meshes + mans, flat, os.path.join(work, "cinderling_crowd_1x_28.png"), 580, 420, tgt,
                                 view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    clear_copies(made)
    C.remove_objects(mans)

    # 3. the hop cycle at game size: 6 frames of move@loop per look, 3/4 toward the camera
    hop = []
    for v in looks:
        n = v["acts"]["move@loop"].frame_range[1]
        for k in range(6):
            f = n * k / 6.0
            made = list(spawn(v, (0.0, 0.0, 0.0), math.radians(-30), "move@loop", f))
            bpy.context.view_layer.update()
            p = os.path.join(work, "%s_hop_%d.png" % (v["key"], k))
            game_render([o for o in made if o.type == "MESH"], {}, p, 64, 72, (0.0, -0.05, 0.40), samples=12)
            clear_copies(made)
            hop.append((v, k, f, p))

    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = upscale(out["crowd"], os.path.join(reports, "cinderling_crowd.png"), 2)
    counts = {k: {c: v.count(c) for c in set(v)} for k, v in phases.items()}
    cc = ", ".join("%d %s" % (n_, c) for c, n_ in sorted(counts.get("cinderling", {}).items(), key=lambda t: -t[1]))
    sections = [
        {"label": "The three cinderling looks, the base loaded (wind-up), two clinker looks and the 2.2 m hero: toon preview of the shipped GLBs",
         "height": 400, "images": [{"path": out["lineup"], "label": "hero | %s | cinderling wind-up | clinker | clinker_v1" % " | ".join(
             "%s (%s)" % (v["key"], v["meta"].get("variant_name", "")) for v in looks)}]},
        {"label": "Through the game camera (55 deg, %.1f px/m): the lineup at TRUE size, then 3x nearest" % PPM, "height": None,
         "images": [{"path": out["lineup_game"], "label": "1x"}, {"path": out["lineup_game"], "label": "3x", "scale": 3}]},
        {"label": "HORDE READ: 40 cinderlings (%d looks; %s) + %d clinkers (all four looks) around two 2.2 m heroes, TRUE 1080p pixel size"
                  % (len(looks), cc, len(clk_pts)), "height": None,
         "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px)"},
                    {"path": out["crowd_sil"], "label": "1x silhouette"},
                    {"path": out["crowd_val"], "label": "1x value only (luminance)"},
                    {"path": out["crowd28"], "label": "1x, four-player view (28 m = 1080 px)"}]},
        {"label": "The same horde, 2x nearest", "height": None, "images": [{"path": out["crowd"], "label": "2x", "scale": 2}]},
        {"label": "HOP at game size: move@loop, 6 frames per look, true pixels shown 3x nearest", "height": None,
         "images": [{"path": p, "label": "%s f%.0f" % (v["key"] if k == 0 else "", f), "scale": 3} for v, k, f, p in hop]},
    ]
    notes = ["; ".join("%s: %s tris, %s px, %.2f m tall, move_cycle_m %.2f" % (
        v["key"], v["meta"]["tris"], "+".join("%d" % t["px"][0] for t in v["meta"]["textures"]), v["meta"]["size_m"],
        v["meta"]["move_cycle_m"]) for v in looks),
        "clinker looks: " + ", ".join("%s %s tris" % (v["key"], v["meta"]["tris"]) for v in clinkers),
        "Every copy here is posed from the actions inside the shipped GLBs (imported with Blender's glTF importer). "
        "The two heroes are grey mannequins; the floor is the Cinder Wastes mid-tone #3A2C24.",
        "Read: cinderling = a round ash-grey lump with molten seams and a glowing grin (HOP); clinker = a long dark crawler "
        "with teal slits and one pale club arm (SKITTER)."]
    layout = {"title": "Cinderling horde read  (Swarm Blob, The Unmade)",
              "subtitle": "content key cinderling | Swarm, Cinder Wastes | Chaser, packs of 3-6 | verb HOP | status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "notes": notes}
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "cinderling_crowd_review.png"), work)

    outputs = []
    for v in looks:
        k = v["key"]
        outputs += [C.rel(C.model_path("enemy", k)), C.rel(os.path.splitext(C.model_path("enemy", k))[0] + ".meta.json"),
                    "art/enemies/cinderling/source/%s.blend" % k, "art/enemies/cinderling/textures/%s_basecolor.png" % k,
                    "art/enemies/cinderling/textures/%s_emissive.png" % k, "art/enemies/cinderling/reports/%s_review.png" % k,
                    "art/enemies/cinderling/reports/%s_build_report.json" % k]
    outputs += [C.rel(out["sheet"]), C.rel(crowd2x)]
    C.write_pack_status("enemy", KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/cinderling.py (--variant base|v1|v2) and reviewed "
                        "by enemies/cinderling_crowd.py (lineup with the clinker, 40-copy horde at true pixel size). Three "
                        "looks of the content key cinderling, one GLB each, identical GF_Swarm_v1, sockets and clip suffixes.",
                        tier="swarm", extra={"skeleton": SPEC.SWARM_SKELETON, "faction": "unmade",
                                             "variants": {v["key"]: v["meta"].get("variant_name") for v in looks}})
    C.log("DONE cinderling crowd", out["sheet"])


if __name__ == "__main__":
    main()
