"""Before / after sheet for the kindlejack art-review fixes (review 5/10, two must-fix items).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/kindlejack_fix_sheet.py -- --before BEFORE_DIR

Run after enemies/kindlejack.py. BEFORE_DIR holds the pre-fix build of commit 3836fda:
  kindlejack.glb      git show 3836fda:assets/models/enemies/kindlejack.glb | git lfs smudge > BEFORE_DIR/kindlejack.glb
  work/kindlejack/    the pre-fix art/enemies/kindlejack/work/kindlejack/ (toon turnaround and clip frames; optional)
AFTER is the shipped assets/models/enemies/kindlejack.glb and the current work/kindlejack/ renders.

Both GLBs are imported with Blender's glTF importer and posed from their own actions, next to the shipped clinker
and the other shipped Cinder swarms, and rendered through the game camera (55 deg, 22 m = 1080 px) at TRUE pixel
size. Measured on the 1x renders:
  * screen area: the pixels of the 1x silhouette (the review: about 540 px against a clinker's 960);
  * the spark: the white / white-teal hot pixels (L* >= 85, a* < 1.5, b* < 3: not the warm ash) within 8 px of the
    projected fx_fuse socket, rest pose;
  * brightness: glow pixels (L* >= 80, or a saturated glow: L* >= 60 and chroma >= 40, so an orange throat counts)
    of a PRIMED kindlejack (every primed@loop frame) against the brightest windup frame of every other shipped
    Cinder swarm - "the brightest swarm on screen for its 0.9 s fuse";
  * the footprint: the rest-pose mesh extents on the ground plane.
A seeded horde (12 kindlejacks, 3 of them primed, among 24 clinkers around a hero) is rendered twice, with the
before and the after GLB in the same slots, poses and facings.

Writes art/enemies/kindlejack/reports/kindlejack_review_fix.png (+ work/fix/fix_metrics.json, not committed).
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402
import clinker as K  # noqa: E402
import clinker_crowd as CC  # noqa: E402
import kindlejack as KJ  # noqa: E402

PPM = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
KJ_CLIPS = list(SPEC.ENEMY_CLIPS_REQUIRED) + ["primed@loop"]
CROP = 100                                    # px, a single creature at 1x
TARGET = (0.0, 0.0, 0.68)
# (tag, label, yaw deg, clip, frame): the game camera looks from -Y, yaw -35 = the 3/4 approach
VIEWS = [("rest", "rest, 3/4 facing", -35.0, None, 0),
         ("toward", "sprinting at the camera (move f3)", -35.0, "move@loop", 3),
         ("away", "sprinting away (move f9)", 145.0, "move@loop", 9),
         ("peak", "PRIMED: primed@loop f3", -35.0, "primed@loop", KJ.PRIMED_PEAK),
         ("low", "PRIMED: primed@loop f8", -35.0, "primed@loop", KJ.PRIMED_LOW)]
RIVALS = ["clinker", "cinderling", "ashrunner", "emberwisp", "slagspitter"]
SPARK_R_M = {"before": 0.044, "after": 0.07}  # the spark sphere's radius in the two builds (kindlejack.py fuse())
BRIGHT_L = 80.0


# ---- import / pose ------------------------------------------------------------------------------------------------

def import_glb(path, tag, key, clips):
    """Import one GLB; returns {key, arm, mesh, acts, sockets}. A second import of the same key gets .001 action
    names, so the actions are matched by their base name among the ones this import added. The skinned mesh is
    picked (the importer also adds a bone-display icosphere), and the socket empties' rest positions are kept in the
    armature's frame."""
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm = next(o for o in new if o.type == "ARMATURE")
    meshes = [o for o in new if o.type == "MESH"]
    mesh = next(o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers))
    extra = [o for o in meshes if o is not mesh]
    arm.name, mesh.name = tag + "_ARM", tag + "_MESH"
    acts = {}
    for act in bpy.data.actions:
        if act in acts0:
            continue
        for c in clips:
            if act.name.split(".")[0] == "%s_%s" % (key, c):
                act.use_fake_user = True
                acts[c] = act
    missing = set(clips) - set(acts)
    if missing:
        raise RuntimeError("%s has no clips %s" % (path, sorted(missing)))
    arm.animation_data_clear()
    for pb in arm.pose.bones:
        pb.custom_shape = None
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    inv = arm.matrix_world.inverted()
    sockets = {o.name.split(".")[0]: inv @ o.matrix_world.translation for o in new if o.type == "EMPTY"}
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    C.remove_objects(extra)
    return {"key": tag, "arm": arm, "mesh": mesh, "acts": acts, "sockets": sockets}


def footprint(v):
    """Rest-pose extents of the skinned mesh on the ground plane (x across, y along the facing), in m."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = v["mesh"].evaluated_get(dg)
    me = ev.to_mesh()
    inv = v["arm"].matrix_world.inverted()
    pts = np.array([tuple(inv @ (ev.matrix_world @ p.co)) for p in me.vertices])
    ev.to_mesh_clear()
    ext = pts.max(0) - pts.min(0)
    return float(ext[0]), float(ext[1]), float(pts[:, 2].max())


def game(v, clip, frame, yaw, stem, work, w=CROP, h=CROP, target=TARGET, sil=True):
    made = list(KJ.spawn(v, (0.0, 0.0, 0.0), math.radians(yaw), clip, frame))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    path = os.path.join(work, stem + ".png")
    sil_path = os.path.join(work, stem + "_sil.png") if sil else None
    CC.game_render(meshes, {}, path, w, h, target, sil_path=sil_path, samples=16)
    out = {"color": path, "sil": sil_path}
    if "fx_fuse" in v["sockets"] and clip is None:
        a2 = next(o for o in made if o.type == "ARMATURE")
        p = a2.matrix_world @ v["sockets"]["fx_fuse"]
        scene = bpy.context.scene
        q = world_to_camera_view(scene, scene.camera, p)
        out["spark_px"] = (float(q.x * w), float((1.0 - q.y) * h))
    CC.clear_copies(made)
    return out


# ---- pixel metrics (the PNGs are 8-bit sRGB; Image.pixels gives the stored values) -------------------------------

def load_rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, :3].astype(np.float64)       # top row first


def lab(c):
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def sil_mask(path):
    a = load_rgb(path)
    return (a @ np.array([0.3, 0.59, 0.11])) < 0.35


def area_px(r):
    return int(sil_mask(r["sil"]).sum())


def bright_px(r):
    """Glow pixels on the creature: light (L* >= 80) or a saturated glow (L* >= 60, chroma >= 40)."""
    lb = lab(load_rgb(r["color"]))
    m = sil_mask(r["sil"]) if r.get("sil") else np.ones(lb.shape[:2], dtype=bool)
    chroma = np.hypot(lb[..., 1], lb[..., 2])
    return int((((lb[..., 0] >= BRIGHT_L) | ((lb[..., 0] >= 60.0) & (chroma >= 40.0))) & m).sum())


def spark_px(r, rad=8):
    """White-teal hot pixels within rad px of the projected spark, and the hot cluster's width in px."""
    x0, y0 = r["spark_px"]
    lb = lab(load_rgb(r["color"]))
    h, w = lb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    near = (xx + 0.5 - x0) ** 2 + (yy + 0.5 - y0) ** 2 <= rad * rad
    hot = near & (lb[..., 0] >= 85.0) & (lb[..., 1] < 1.5) & (lb[..., 2] < 3.0)        # white / white-teal, not ash
    if not hot.any():
        return 0, 0
    cols = np.nonzero(hot.any(0))[0]
    rows = np.nonzero(hot.any(1))[0]
    return int(hot.sum()), int(max(cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1))


def crop_png(src, dst, cx, cy, rw, rh=None):
    """A (2 rw x 2 rh) crop around (cx, cy) in top-left pixel coordinates, pixel for pixel (edges clamped)."""
    rh = rw if rh is None else rh
    a = load_rgb(src)
    h, w = a.shape[:2]
    ys = np.clip(np.arange(2 * rh) + int(round(cy)) - rh, 0, h - 1)
    xs = np.clip(np.arange(2 * rw) + int(round(cx)) - rw, 0, w - 1)
    out = a[ys][:, xs]
    o = bpy.data.images.new("gfa_crop", 2 * rw, 2 * rh, alpha=False)
    rgba = np.concatenate([out[::-1], np.ones((2 * rh, 2 * rw, 1))], -1).astype(np.float32)
    o.pixels.foreach_set(rgba.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    return dst


# ---- the seeded horde -----------------------------------------------------------------------------------------------

def horde(kj, clinkers, path, seed=31, n_kj=12, n_cl=24):
    """The same slots, clips, frames and facings for any kindlejack GLB: the three kindlejack slots nearest the hero
    are PRIMED (primed@loop at the throb's peak, middle and low), the rest sprint in; the clinkers skitter or idle."""
    rng = random.Random(seed)
    hero = Vector((0.0, 0.4, 0.0))
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = hero
    pts, tries = [], 0
    while len(pts) < n_kj + n_cl and tries < 40000:
        tries += 1
        p = Vector((rng.uniform(-5.4, 5.4), rng.uniform(-3.0, 4.2), 0.0))
        if (p - hero).length < 1.05 or any((p - q).length < 0.74 for q in pts):
            continue
        pts.append(p)
    pts.sort(key=lambda p: (p - hero).length)
    kj_slots = {0, 1, 3} | set(rng.sample(range(4, len(pts)), n_kj - 3))
    primed_frames = [float(KJ.PRIMED_PEAK), 5.0, float(KJ.PRIMED_LOW)]
    made = []
    for i, p in enumerate(pts):
        yaw = CC.face_yaw(p, hero) + math.radians(rng.uniform(-25, 25))
        f = rng.random()
        if i in kj_slots:
            if i in (0, 1, 3):
                clip, fr = "primed@loop", primed_frames.pop(0)
            else:
                clip, fr = "move@loop", f * KJ.MOVE_FRAMES
            made += list(KJ.spawn(kj, p, yaw, clip, fr))
        else:
            v = clinkers[i % len(clinkers)]
            mv = v["V"]["motion"]
            clip, fr = ("move@loop", f * mv["move_frames"]) if rng.random() < 0.75 else ("idle@loop", f * mv["idle_frames"])
            made += list(KJ.spawn(v, p, yaw, clip, fr))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    CC.game_render(meshes + [man], {man.name: R.MANNEQUIN}, path, 560, 390, (0.0, 0.55, 0.3), samples=16)
    CC.clear_copies(made)
    C.remove_objects([man])
    return path


# ---- main -----------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    before_dir = C.opt(argv, "--before", None, str)
    if not before_dir:
        raise SystemExit("usage: ... -- --before BEFORE_DIR")
    C.reset_scene(fps=KJ.FPS)
    pack = C.pack_dir("enemy", KJ.KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "fix"))
    reports = os.path.join(pack, "reports")
    kjs = {"before": import_glb(os.path.join(before_dir, "kindlejack.glb"), "before", KJ.KEY, KJ_CLIPS),
           "after": import_glb(C.model_path("enemy", KJ.KEY), "after", KJ.KEY, KJ_CLIPS)}
    clinkers = []
    for vk in ("base", "v1", "v2", "v3"):
        key = K.VARIANTS[vk]["key"]
        v = import_glb(C.model_path("enemy", key), key, key, SPEC.ENEMY_CLIPS_REQUIRED)
        v["V"] = K.VARIANTS[vk]
        clinkers.append(v)
    rivals = {"clinker": clinkers[0]}
    for key in RIVALS[1:]:
        rivals[key] = import_glb(C.model_path("enemy", key), key, key, SPEC.ENEMY_CLIPS_REQUIRED)
    parked = list(kjs.values()) + clinkers + [rivals[k] for k in RIVALS[1:]]
    for i, v in enumerate(parked):
        v["arm"].location = (100.0 + 6.0 * i, 100.0, 0.0)
    bpy.context.view_layer.update()
    met = {"footprint_m": {t: footprint(v) for t, v in kjs.items()}}

    # 1. size and signal: the same views, before and after, with the clinker as the yardstick
    views = {}
    for t, v in kjs.items():
        views[t] = {}
        for tag, label, yaw, clip, f in VIEWS:
            r = game(v, clip, f, yaw, "%s_%s" % (t, tag), work)
            r["area"], r["bright"] = area_px(r), bright_px(r)
            views[t][tag] = r
        views[t]["rest"]["spark"] = spark_px(views[t]["rest"])
    cl = game(clinkers[0], None, 0, -35.0, "clinker_rest", work)
    cl_area = area_px(cl)
    cl_move = game(clinkers[0], "move@loop", 3, -35.0, "clinker_move", work)
    cl_move_area = area_px(cl_move)

    # 2. the primed read: every primed@loop frame, against every other swarm's brightest windup frame
    primed = {}
    for t, v in kjs.items():
        n = int(round(v["acts"]["primed@loop"].frame_range[1] - v["acts"]["primed@loop"].frame_range[0]))
        rows = []
        for f in range(n):
            r = game(v, "primed@loop", f, -35.0, "%s_primed_%02d" % (t, f), work)
            rows.append((f, bright_px(r), area_px(r), r))
        primed[t] = rows
    rival_best = {}
    for key in RIVALS:
        v = rivals[key]
        a0, a1 = v["acts"]["windup"].frame_range
        best = None
        for k in range(6):
            f = a0 + (a1 - a0) * k / 5.0
            r = game(v, "windup", f, -35.0, "rival_%s_windup_%d" % (key, k), work)
            b = bright_px(r)
            if best is None or b > best[1]:
                best = (f, b, area_px(r), r)
        rival_best[key] = best

    # 3. the seeded horde, before and after in the same slots
    hordes = {t: horde(kjs[t], clinkers, os.path.join(work, "horde_%s.png" % t)) for t in kjs}
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])

    # 4. the spark, 1x pixels around the projected socket; the horde's middle, around the hero
    spark_crops = {t: crop_png(views[t]["rest"]["color"], os.path.join(work, "%s_spark.png" % t),
                               *views[t]["rest"]["spark_px"], 9) for t in kjs}
    horde_mid = {t: crop_png(hordes[t], os.path.join(work, "horde_%s_mid.png" % t), 280, 175, 170, 110) for t in kjs}

    b, a = views["before"], views["after"]
    fb, fa = met["footprint_m"]["before"], met["footprint_m"]["after"]
    sb, sa = b["rest"]["spark"], a["rest"]["spark"]
    pmin = {t: min(x[1] for x in primed[t]) for t in primed}
    pmax = {t: max(x[1] for x in primed[t]) for t in primed}
    top_rival = max(rival_best, key=lambda k: rival_best[k][1])
    top_glow = rival_best[top_rival][1]
    short = {"rest": "rest 3/4", "toward": "sprint at camera", "away": "sprint away"}

    def row(t):
        vs = views[t]
        out = [{"path": vs[tag]["color"], "label": "%s: %s, %d px" % (t, short[tag], vs[tag]["area"]), "scale": 3}
               for tag, *_ in VIEWS[:3]]
        out.append({"path": vs["rest"]["sil"], "label": "%s: rest silhouette %d px" % (t, vs["rest"]["area"]), "scale": 3})
        return out
    yard = [{"path": cl["color"], "label": "clinker: rest 3/4, %d px" % cl_area, "scale": 3},
            {"path": cl["sil"], "label": "clinker: silhouette %d px" % cl_area, "scale": 3},
            {"path": cl_move["color"], "label": "clinker: skitter f3, %d px" % cl_move_area, "scale": 3}]
    primed_row = []
    for t in ("before", "after"):
        for f, br, ar, r in primed[t]:
            if f in (0, KJ.PRIMED_PEAK, 5, KJ.PRIMED_LOW):
                primed_row.append({"path": r["color"], "label": "%s f%d: %d glow px" % (t, f, br), "scale": 3})
    rival_row = [{"path": rival_best[k][3]["color"], "label": "%s windup f%.0f: %d" % (k, rival_best[k][0], rival_best[k][1]),
                  "scale": 3} for k in RIVALS]
    bw = os.path.join(before_dir, "work", "kindlejack")
    aw = os.path.join(pack, "work", "kindlejack")
    close = []
    for lab_, bp, ap in (("rest 3/4 front", "kindlejack_turn_34_front.png", "kindlejack_turn_34_front.png"),
                         ("PRIMED", "kindlejack_clip_kindlejack_primed_loop_01.png",
                          "kindlejack_clip_kindlejack_primed_loop_01.png")):
        if os.path.exists(os.path.join(bw, bp)):
            close.append({"path": os.path.join(bw, bp), "label": "before: " + lab_})
        close.append({"path": os.path.join(aw, ap), "label": "after: " + lab_})
    layout = {
        "title": "Kindlejack - art review fixes (5/10), before and after",
        "subtitle": "both GLBs imported and posed from their own clips | game camera 55 deg, %.1f px/m, TRUE 1080p pixels "
                    "shown 3x nearest | before = 3836fda, after = this fix" % PPM,
        "width": 1600,
        "sections": [
            {"label": "MUST-FIX 1, BEFORE: lost among the clinkers - %d px at rest (clinker %d), a %.2f x %.2f m footprint, "
                      "teal slits, a %d px spark" % (b["rest"]["area"], cl_area, fb[0], fb[1], sb[1]),
             "height": None, "images": row("before")},
            {"label": "MUST-FIX 1, AFTER: fills its collider (%.2f x %.2f m), %d px at rest, a pale ash torch head, "
                      "a %d px white-teal spark" % (fa[0], fa[1], a["rest"]["area"], sa[1]),
             "height": None, "images": row("after")},
            {"label": "The yardstick (the shipped clinker, same camera) | the spark at 1x, 6x nearest: %d -> %d hot px, "
                      "%d -> %d px across" % (sb[0], sa[0], sb[1], sa[1]), "height": None,
             "images": yard + [{"path": spark_crops["before"], "label": "before spark", "scale": 6},
                               {"path": spark_crops["after"], "label": "after spark", "scale": 6}]},
            {"label": "MUST-FIX 2, PRIMED@LOOP at 1x (glow px: L* >= 80, or L* >= 60 with chroma >= 40): before %d-%d, "
                      "after %d-%d through the throb" % (pmin["before"], pmax["before"], pmin["after"], pmax["after"]),
             "height": None, "images": primed_row},
            {"label": "...against the brightest windup frame of every other shipped Cinder swarm: at most %d (the %s)"
                      % (top_glow, top_rival), "height": None, "images": rival_row},
            {"label": "Close-up (toon preview of the final textures): before | after", "height": 300, "images": close},
            {"label": "Seeded horde: 12 kindlejacks (the 3 nearest the hero PRIMED) in 24 clinkers, same slots, poses, "
                      "facings - TRUE 1x: before | after", "height": None,
             "images": [{"path": hordes["before"], "label": "before (3836fda), 1x"},
                        {"path": hordes["after"], "label": "after, 1x"}]},
            {"label": "The same hordes around the hero, 2x nearest: before | after", "height": None,
             "images": [{"path": horde_mid["before"], "label": "before", "scale": 2},
                        {"path": horde_mid["after"], "label": "after", "scale": 2}]},
        ],
        "notes": [
            "Must-fix 1: screen area at rest %d -> %d px (clinker %d), sprinting at the camera %d -> %d px (clinker skitter %d); "
            "footprint %.2f x %.2f -> %.2f x %.2f m; %.2f -> %.2f m tall." % (
                b["rest"]["area"], a["rest"]["area"], cl_area, b["toward"]["area"], a["toward"]["area"], cl_move_area,
                fb[0], fb[1], fa[0], fa[1], fb[2], fa[2]),
            "Spark: a %.2f -> %.2f m white-teal core (%.1f -> %.1f px at 1x) in six 0.12-0.15 m rays. Torch head: 14 stick ends, "
            "burnt at the collar, pale ash above; the core behind the sticks banked dark." % (
                2 * SPARK_R_M["before"], 2 * SPARK_R_M["after"], 2 * SPARK_R_M["before"] * PPM, 2 * SPARK_R_M["after"] * PPM),
            "Must-fix 2: primed@loop throbs the torch-head fire (bone head) three times a second at about 2 x: %d-%d glow px "
            "(before %d-%d); the most of any other swarm's windup is %d (%s)." % (
                pmin["after"], pmax["after"], pmin["before"], pmax["before"], top_glow, top_rival),
            ("Even at the bottom of its throb a primed kindlejack is the brightest swarm on screen. " if pmin["after"] > top_glow
             else "") + "Rig: head = the fire, tail = the fuse (GF_Swarm_v1, the 7 clips unchanged). %d tris. Status: %s." % (
                int(C.read_json(os.path.splitext(C.model_path("enemy", KJ.KEY))[0] + ".meta.json")["tris"]),
                SPEC.STATUS_AI_FINAL),
        ],
    }
    out = R.contact_sheet(layout, os.path.join(reports, "kindlejack_review_fix.png"), work)
    met.update({
        "area_px": {t: {tag: views[t][tag]["area"] for tag, *_ in VIEWS} for t in views},
        "glow_px": {t: {tag: views[t][tag]["bright"] for tag, *_ in VIEWS} for t in views},
        "clinker_area_px": {"rest": cl_area, "move_f3": cl_move_area},
        "spark": {t: {"hot_px": views[t]["rest"]["spark"][0], "width_px": views[t]["rest"]["spark"][1],
                      "core_d_m": 2 * SPARK_R_M[t]} for t in views},
        "primed_glow_px": {t: {str(f): br for f, br, _, _ in primed[t]} for t in primed},
        "primed_area_px": {t: {str(f): ar for f, _, ar, _ in primed[t]} for t in primed},
        "rival_windup_glow_px": {k: {"frame": rival_best[k][0], "glow": rival_best[k][1], "area": rival_best[k][2]}
                                 for k in RIVALS},
    })
    C.write_json(os.path.join(work, "fix_metrics.json"), met)
    C.log("DONE kindlejack fix sheet", out)


if __name__ == "__main__":
    main()
