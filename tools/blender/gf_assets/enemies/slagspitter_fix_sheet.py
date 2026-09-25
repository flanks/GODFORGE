"""Before / after sheet for the slagspitter art-review fixes (review 6/10, two must-fix items).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/slagspitter_fix_sheet.py -- --before BEFORE_DIR

Run after enemies/slagspitter.py. BEFORE_DIR holds the pre-fix GLB:
  slagspitter.glb        the GLB of commit eae8522 (git show eae8522:assets/models/enemies/slagspitter.glb | git lfs smudge)
AFTER is the shipped assets/models/enemies/slagspitter.glb. Both GLBs (and the shipped cinderling, the swarm the
review confused it with) are imported with Blender's glTF importer and posed from their own actions, then rendered
through the game camera at TRUE 1080p pixel size (55 deg, 49.1 px/m) on the Cinder floor #3A2C24 - single views,
close-ups and the seeded horde of slagspitter.horde_render() (the same layout, poses and yaws for both GLBs; the
pre-fix crowd render had every copy facing one way). Measured on the 1x renders:
  * outline: silhouette height / width and fill (silhouette area / its bounding box: a round mound fills ~0.75+,
    a spire with a neck less);
  * figure / ground (the review's metric): the body pixels (not floor, not the molten glow, not the teal) -
    their median L*, and the share within +-7 L* of the floor (the review measured 22.6 and 36 %).

Writes art/enemies/slagspitter/reports/slagspitter_review_fix.png (+ work/fix/fix_metrics.json).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402
import slagspitter as SS  # noqa: E402

PPM = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
FLOOR = (0x3A, 0x2C, 0x24)
# (tag, label, yaw deg, clip, frame) - the game camera looks from -Y; yaw 0 = facing the camera
VIEWS = [("face", "facing, rest", -30.0, None, 0),
         ("right", "yaw 60, rest", 60.0, None, 0),
         ("away", "turned away, rest", 150.0, None, 0),
         ("left", "yaw 240, move", 240.0, "move@loop", 4),
         ("windup", "wind-up (loaded)", -30.0, "windup", 18)]
CROP = 96                        # px, the 1x crop round the creature
TARGET = (0.0, 0.05, 0.45)
HORDE_BOX = (260, 110, 640, 430)    # the same box of the 1x horde render (heroes, clinkers, slagspitters), shown 2x


def import_glb(path, tag, key):
    """Import one GLB; its actions are keyed by clip name (a second import of the same key gets .001 names)."""
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers))
    for o in new:
        if o.type in ("MESH", "EMPTY") and o is not mesh:
            o.hide_render = True
    arm.name, mesh.name = tag + "_ARM", tag + "_MESH"
    acts = {}
    for act in bpy.data.actions:
        if act in acts0:
            continue
        for c in SPEC.ENEMY_CLIPS_REQUIRED:
            if act.name.split(".")[0] == "%s_%s" % (key, c):
                act.use_fake_user = True
                acts[c] = act
    missing = set(SPEC.ENEMY_CLIPS_REQUIRED) - set(acts)
    if missing:
        raise RuntimeError("%s has no clips %s" % (path, sorted(missing)))
    arm.animation_data_clear()
    return {"key": tag, "arm": arm, "mesh": mesh, "acts": acts}


def load_rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return (px.reshape(h, w, 4)[::-1, :, :3] * 255.0).astype(np.float64)       # top-left origin, sRGB 0..255


def lab(a):
    c = a / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def figure_ground(color_path):
    a = load_rgb(color_path)
    L = lab(a)
    fl = float(lab(np.array(FLOOR, dtype=np.float64))[0])
    creature = np.abs(a - np.array(FLOOR)).sum(-1) > 12
    glow = (L[..., 1] > 25) & (L[..., 0] > 40)               # the molten orange / hot red
    teal = L[..., 1] < -12
    body = creature & ~glow & ~teal
    lb = L[..., 0][body]
    return {"median_L": float(np.median(lb)), "within7": float(100.0 * (np.abs(lb - fl) <= 7).mean()),
            "brighter": float(100.0 * (lb > fl + 7).mean()), "floor_L": fl, "body_px": int(body.sum())}


def outline(sil_path):
    a = load_rgb(sil_path)
    m = a.mean(-1) < 90
    ys, xs = np.nonzero(m)
    h, w = int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)
    return {"h": h, "w": w, "fill": float(m.sum() / (h * w)), "aspect": float(h / w)}


def render_views(v, work, views=VIEWS):
    out = {}
    for tag, label, yaw, clip, f in views:
        made = list(SS.spawn(v, (0.0, 0.0, 0.0), math.radians(yaw), clip, f))
        bpy.context.view_layer.update()
        meshes = [o for o in made if o.type == "MESH"]
        stem = os.path.join(work, "%s_%s" % (v["key"], tag))
        SS.game_render(meshes, {}, stem + ".png", CROP, CROP, TARGET, sil_path=stem + "_sil.png", ink=0.01,
                       samples=16)
        SS.clear_copies(made)
        out[tag] = {"color": stem + ".png", "sil": stem + "_sil.png", "label": label,
                    "fg": figure_ground(stem + ".png"), "ol": outline(stem + "_sil.png")}
    return out


def close_up(vs, work, size=520):
    """3/4 front toon close-ups of each GLB at rest, at ONE scale (the taller asset sets the frame)."""
    scene = bpy.context.scene
    d = Vector((0.62, -0.72, 0.42))
    made = {}
    for v in vs:
        made[v["key"]] = list(SS.spawn(v, (0.0, 0.0, 0.0), 0.0))
    bpy.context.view_layer.update()
    exts, cents = [], []
    for k, objs in made.items():
        meshes = [o for o in objs if o.type == "MESH"]
        for o in meshes:
            o.hide_render = True
        c, w, h = R.frame(R._points(meshes), d)
        exts.append(max(w, h))
        cents.append(c)
    ext = max(exts) * 1.1
    out = {}
    R.setup_cycles(scene, 16)
    for (k, objs), c in zip(made.items(), cents):
        meshes = [o for o in objs if o.type == "MESH"]
        for o in meshes:
            o.hide_render = False
        with R.toon_preview(meshes, ink=0.006):
            R.aim(scene, c, d, ext)
            out[k] = R.render(scene, os.path.join(work, "%s_close.png" % k), size)
        for o in meshes:
            o.hide_render = True
    for objs in made.values():
        SS.clear_copies(objs)
    return out


def crop_png(src, dst, box):
    """Crop (x0, y0, x1, y1) in top-left pixel coordinates, pixel for pixel."""
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    top = px.reshape(h, w, 4)[::-1]
    x0, y0, x1, y1 = box
    sub = np.ascontiguousarray(top[y0:y1, x0:x1][::-1])
    o = bpy.data.images.new("gfa_crop", x1 - x0, y1 - y0, alpha=False)
    o.pixels.foreach_set(sub.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(img)
    bpy.data.images.remove(o)
    return dst


def main():
    argv = C.script_args()
    before_dir = C.opt(argv, "--before", None, str)
    if not before_dir:
        raise SystemExit("usage: ... -- --before BEFORE_DIR")
    C.reset_scene(fps=SS.FPS)
    pack = C.pack_dir("enemy", SS.KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "fix"))
    reports = os.path.join(pack, "reports")
    old = import_glb(os.path.join(before_dir, "slagspitter.glb"), "before", SS.KEY)
    new = import_glb(C.model_path("enemy", SS.KEY), "after", SS.KEY)
    cin = import_glb(C.model_path("enemy", "cinderling"), "cinderling", "cinderling")
    for i, v in enumerate((old, new, cin)):
        v["arm"].location = (100.0 + 10 * i, 100.0, 0.0)
    bpy.context.view_layer.update()
    views = {"before": render_views(old, work), "after": render_views(new, work),
             "cinderling": render_views(cin, work, [("face", "facing, rest", -30.0, None, 0),
                                                    ("windup", "wind-up (loaded)", -30.0, "windup", 15)])}
    close = close_up([old, new], work)
    cl = [SS.import_glb(k) for k in SS.CLINKERS]
    for i, v in enumerate(cl):
        v["arm"].location = (100.0 + 10 * i, 120.0, 0.0)
    bpy.context.view_layer.update()
    horde = {}
    for tag, v in (("before", old), ("after", new)):
        h = SS.horde_render(v, cl, work, stem="%s_horde" % tag, four_player=False)
        box = crop_png(h["crowd"], os.path.join(work, "%s_horde_crop.png" % tag), HORDE_BOX)
        horde[tag] = SS.upscale(box, os.path.join(work, "%s_horde_crop2x.png" % tag), 2)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])

    def mean(tag, grp, key, tags=("face", "right", "away", "left")):
        return float(np.mean([views[tag][t][grp][key] for t in tags]))

    def row(tag, what):
        vs = views[tag]
        if what == "color":
            return [{"path": vs[t]["color"], "scale": 3,
                     "label": "%s | body L* %.0f, %.0f %% near floor" % (vs[t]["label"], vs[t]["fg"]["median_L"],
                                                                         vs[t]["fg"]["within7"])} for t, *_ in VIEWS]
        return [{"path": vs[t]["sil"], "scale": 3,
                 "label": "%s | %dx%d px, fill %.2f" % (vs[t]["label"], vs[t]["ol"]["w"], vs[t]["ol"]["h"],
                                                       vs[t]["ol"]["fill"])} for t, *_ in VIEWS]
    cv = views["cinderling"]
    b_l, a_l = mean("before", "fg", "median_L"), mean("after", "fg", "median_L")
    b_n, a_n = mean("before", "fg", "within7"), mean("after", "fg", "within7")
    b_b, a_b = mean("before", "fg", "brighter"), mean("after", "fg", "brighter")
    b_f, a_f = mean("before", "ol", "fill"), mean("after", "ol", "fill")
    b_a, a_a = mean("before", "ol", "aspect"), mean("after", "ol", "aspect")
    layout = {
        "title": "Slagspitter - art review fixes (6/10), before and after",
        "subtitle": "same cameras and poses, both GLBs imported and posed from their own clips; game camera 55 deg, "
                    "%.1f px/m on the Cinder floor #3A2C24, TRUE 1080p pixels shown 3x nearest" % PPM,
        "width": 1600,
        "sections": [
            {"label": "BEFORE (eae8522): a squat cone, 0.84 m tall on a 1.1 m skirt - from every side a round mound; "
                      "the slag body sits on the floor's value, only the crater reads", "height": None,
             "images": row("before", "color")},
            {"label": "BEFORE silhouettes (1x shown 3x): fill %.2f, height/width %.2f" % (b_f, b_a), "height": None,
             "images": row("before", "sil")},
            {"label": "AFTER: a leaning slag chimney, 1.05 m, off-centre mortar muzzle on a narrow skirt; top planes "
                      "lifted, bold light lip strokes round the muzzle", "height": None,
             "images": row("after", "color")},
            {"label": "AFTER silhouettes: fill %.2f, height/width %.2f" % (a_f, a_a), "height": None,
             "images": row("after", "sil")},
            {"label": "Not a cinderling: the cinderling's wind-up (its lid open over the white-hot maw) beside the "
                      "slagspitter's, before and after - 1x shown 3x", "height": None,
             "images": [{"path": cv["windup"]["color"], "label": "cinderling wind-up", "scale": 3},
                        {"path": cv["windup"]["sil"], "label": "cinderling: fill %.2f" % cv["windup"]["ol"]["fill"],
                         "scale": 3},
                        {"path": views["before"]["windup"]["sil"],
                         "label": "slagspitter before: fill %.2f" % views["before"]["windup"]["ol"]["fill"], "scale": 3},
                        {"path": views["after"]["windup"]["sil"],
                         "label": "slagspitter after: fill %.2f" % views["after"]["windup"]["ol"]["fill"], "scale": 3}]},
            {"label": "3/4 close-up at rest, toon preview of the shipped textures, one scale: before | after",
             "height": 460, "images": [{"path": close["before"], "label": "before"},
                                       {"path": close["after"], "label": "after"}]},
            {"label": "The horde (slagspitters at lob range among clinkers round two heroes; the same seeded layout, "
                      "poses and yaws), 1x shown 2x nearest: before | after", "height": None,
             "images": [{"path": horde["before"], "label": "before"}, {"path": horde["after"], "label": "after"}]},
        ],
        "notes": [
            "Must-fix 1 (outline): the skirt radius 0.555 -> 0.41 m pinches into a 0.165 m chimney that curves 0.30 m "
            "off-centre to the right and flares into a mortar muzzle; 0.845 -> 1.05 m tall.",
            "  Silhouette fill (area / bounding box, 4 yaws) %.2f -> %.2f, height/width %.2f -> %.2f. Footprint with the "
            "toes about 1.09 x 1.06 m (collider r 0.48 -> 2.2-3 x r)." % (b_f, a_f, b_a, a_a),
            "  Limit: where the chimney leans toward the camera (about 3 of 8 facings, like yaw 60 here) the neck "
            "overlaps the skirt and the outline is a crowned clump with the muzzle glow on top. A sweep of",
            "  smaller leans and lower / narrower skirts did not change those facings, so the lean keeps its 0.30 m for "
            "the strong diagonal at the others.",
            "Must-fix 2 (figure/ground): body median L* %.1f -> %.1f (floor %.1f); body pixels within +-7 L* of the floor "
            "%.0f %% -> %.0f %%; brighter than that band %.0f %% -> %.0f %% (4 yaws, 1x)."
            % (b_l, a_l, views["after"]["face"]["fg"]["floor_L"], b_n, a_n, b_b, a_b),
            "  Up-facing slag / crust planes lifted toward #654838 / #704F3E (per-plate value steps, long cooled-flow "
            "streaks), a bold #C8A07A lip stroke on every plate's top edge.",
            "Skeleton, clip names, socket names and file names are unchanged. Status: %s." % SPEC.STATUS_AI_FINAL,
        ],
    }
    out = R.contact_sheet(layout, os.path.join(reports, "slagspitter_review_fix.png"), work)
    C.write_json(os.path.join(work, "fix_metrics.json"),
                 {t: {k: {"fg": v["fg"], "ol": v["ol"]} for k, v in views[t].items()} for t in views})
    C.log("DONE slagspitter fix sheet", out,
          "L* %.1f -> %.1f, near floor %.0f -> %.0f %%, fill %.2f -> %.2f" % (b_l, a_l, b_n, a_n, b_f, a_f))


if __name__ == "__main__":
    main()
