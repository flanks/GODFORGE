"""Before / after sheet for the ashrunner art-review fixes (review 6/10, two must-fix items).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/ashrunner_fix_sheet.py -- --before BEFORE_DIR

Run after enemies/ashrunner.py and enemies/ashrunner_crowd.py. BEFORE_DIR holds the pre-fix files:
  ashrunner.glb        the GLB of commit 3069107 (git show 3069107:assets/models/enemies/ashrunner.glb | git lfs smudge)
  ashrunner_34.png     the pre-fix reports/ashrunner_34.png
  ashrunner_crowd.png  the pre-fix reports/ashrunner_crowd.png (the horde layout is seeded, so the crops match)
AFTER comes from the shipped assets/models/enemies/ashrunner.glb and the current reports. Both GLBs are imported
with Blender's glTF importer and posed from their own actions, then rendered through the game camera at TRUE
1080p pixel size. The head-on width is measured on the 1x silhouettes.

Writes art/enemies/ashrunner/reports/ashrunner_review_fix.png.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402
import ashrunner as A  # noqa: E402
import ashrunner_crowd as CR  # noqa: E402

PPM = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
# (tag, label, yaw deg, clip, frame, crop w, crop h) - the game camera looks from -Y: yaw 0 = running at it
VIEWS = [("head", "head-on, gallop f2", 0.0, "move@loop", 2, 64, 84),
         ("tail", "tail-on, gallop f7", 180.0, "move@loop", 7, 64, 84),
         ("across", "running across, gallop f2", 90.0, "move@loop", 2, 96, 64),
         ("face", "3/4 facing, rest", -35.0, None, 0, 84, 84)]


def import_glb(path, tag):
    """Import one GLB; its actions are keyed by clip name (a second import of the same key gets .001 names)."""
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH")
    arm.name, mesh.name = tag + "_ARM", tag + "_MESH"
    acts = {}
    for act in bpy.data.actions:
        if act in acts0:
            continue
        for c in SPEC.ENEMY_CLIPS_REQUIRED:
            if act.name.split(".")[0] == "%s_%s" % (A.KEY, c):
                act.use_fake_user = True
                acts[c] = act
    missing = set(SPEC.ENEMY_CLIPS_REQUIRED) - set(acts)
    if missing:
        raise RuntimeError("%s has no clips %s" % (path, sorted(missing)))
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    return {"key": tag, "arm": arm, "mesh": mesh, "acts": acts}


def sil_width(path):
    """Widest row of the 1x silhouette (dark pixels on the light Workbench background), in pixels."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    lum = px.reshape(h, w, 4)[:, :, :3] @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
    best = 0
    for row in lum < 0.35:
        idx = np.nonzero(row)[0]
        if len(idx):
            best = max(best, int(idx[-1] - idx[0] + 1))
    return best


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


def render_views(v, work):
    out = {}
    for tag, label, yaw, clip, f, w, h in VIEWS:
        made = list(CR.spawn(v, (0.0, 0.0, 0.0), math.radians(yaw), clip, f))
        bpy.context.view_layer.update()
        meshes = [o for o in made if o.type == "MESH"]
        stem = os.path.join(work, "%s_%s" % (v["key"], tag))
        CR.game_render(meshes, {}, stem + ".png", w, h, (0.0, 0.06, 0.32), sil_path=stem + "_sil.png", samples=16)
        CR.clear_copies(made)
        out[tag] = {"color": stem + ".png", "sil": stem + "_sil.png", "label": label,
                    "width_px": sil_width(stem + "_sil.png")}
    return out


def main():
    argv = C.script_args()
    before_dir = C.opt(argv, "--before", None, str)
    if not before_dir:
        raise SystemExit("usage: ... -- --before BEFORE_DIR")
    C.reset_scene(fps=A.FPS)
    pack = C.pack_dir("enemy", A.KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "fix"))
    reports = os.path.join(pack, "reports")
    old = import_glb(os.path.join(before_dir, "ashrunner.glb"), "before")
    new = import_glb(C.model_path("enemy", A.KEY), "after")
    old["arm"].location = (100.0, 100.0, 0.0)
    new["arm"].location = (110.0, 100.0, 0.0)
    bpy.context.view_layer.update()
    views = {"before": render_views(old, work), "after": render_views(new, work)}
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    # the same crops of the close-up and of the (seeded) horde, before and after
    crops = {}
    for tag, d in (("before", before_dir), ("after", reports)):
        crops[tag] = {
            "34": crop_png(os.path.join(d, "ashrunner_34.png"), os.path.join(work, "%s_34.png" % tag), (110, 150, 710, 560)),
            "horde": crop_png(os.path.join(d, "ashrunner_crowd.png"), os.path.join(work, "%s_horde.png" % tag),
                              (900, 330, 1500, 860)),
        }
    wb, wa = views["before"]["head"]["width_px"], views["after"]["head"]["width_px"]
    tb, ta = views["before"]["tail"]["width_px"], views["after"]["tail"]["width_px"]

    def row(tag):
        vs = views[tag]
        return [{"path": vs[t]["color"], "label": "%s: %s" % (tag, vs[t]["label"]), "scale": 4} for t, *_ in VIEWS] + \
               [{"path": vs["head"]["sil"], "label": "%s: head-on sil. %d px" % (tag, vs["head"]["width_px"]),
                 "scale": 4}]
    layout = {
        "title": "Ashrunner - art review fixes (6/10), before and after",
        "subtitle": "same cameras, same poses, both GLBs imported and posed from their own clips; game camera 55 deg, "
                    "%.1f px/m, TRUE 1080p pixels shown 4x nearest" % PPM,
        "width": 1600,
        "sections": [
            {"label": "BEFORE: head-on the body is a pale sliver (%d px at 1x); four black ribs with ember edge strokes "
                      "read as a wasp / barcode stripe" % wb, "height": None, "images": row("before")},
            {"label": "AFTER: a hyena-heavy wedge - shoulders 0.46 m, ash ruff to about 0.5 m, heavier skull and ears "
                      "(%d px head-on at 1x); ONE hot chest window framed by ONE rib bar" % wa,
             "height": None, "images": row("after")},
            {"label": "3/4 close-up, toon preview of the final textures: before | after", "height": 400,
             "images": [{"path": crops["before"]["34"], "label": "before: four ember-lined ribs"},
                        {"path": crops["after"]["34"], "label": "after: the hide burnt through in one window, one rib"}]},
            {"label": "The horde (40 ashrunners in pairs + 20 clinkers, the same seeded layout), 2x nearest: before | after",
             "height": 530,
             "images": [{"path": crops["before"]["horde"], "label": "before"},
                        {"path": crops["after"]["horde"], "label": "after"}]},
        ],
        "notes": [
            "Must-fix 1 (width): head-on silhouette %d -> %d px, tail-on %d -> %d px at 1x (widest row); the length is "
            "unchanged (1.44 m with the tail)." % (wb, wa, tb, ta),
            "Must-fix 2 (barcode): the four ribs and their eight ember edge strokes are gone. The hide is burnt through in "
            "one lens-shaped window (open down the left flank,",
            "framed by hide on the right): hot orange with one cooled-hot spot, a thin burnt rim with one ember line, and "
            "one black rib bar along its rear edge.",
            "Skeleton, clips, sockets and file names are unchanged. Status: %s." % SPEC.STATUS_AI_FINAL,
        ],
    }
    out = R.contact_sheet(layout, os.path.join(reports, "ashrunner_review_fix.png"), work)
    C.write_json(os.path.join(work, "fix_metrics.json"),
                 {t: {k: {"width_px": v["width_px"]} for k, v in views[t].items()} for t in views})
    C.log("DONE ashrunner fix sheet", out, "head-on %d -> %d px, tail-on %d -> %d px" % (wb, wa, tb, ta))


if __name__ == "__main__":
    main()
