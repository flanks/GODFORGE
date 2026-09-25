"""Before / after sheet for the anvil_brute art-review fixes (review 6.5/10, two must-fix items).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/anvil_brute_fix_sheet.py -- --before BEFORE_DIR

Run after enemies/anvil_brute.py. BEFORE_DIR holds the pre-fix files:
  anvil_brute.glb      the GLB of commit 24715c5 (git show 24715c5:assets/models/enemies/anvil_brute.glb | git lfs smudge)
  anvil_brute_34.png   the pre-fix reports/anvil_brute_34.png
AFTER comes from the shipped assets/models/enemies/anvil_brute.glb and the current reports/anvil_brute_34.png.

Both GLBs are imported with Blender's glTF importer, posed from their own clips, set to the intact plate state
(the joint scales the engine sets) and rendered through the game camera at TRUE 1080p pixel size (55 deg, view
height 22 m = 49.1 px/m) on the Cinder flagstones (the floor of the art review, sampled from the live game) and on
the spec floor #3A2C24. The value metric repeats the art review's: over the creature's pixels in a transparent
render, the median L* and the share within +-7 L* of the spec floor (#3A2C24, L* 19.3) and of the mid flagstone
(#603320, L* 28.6); the L* band map colours every creature pixel by those bands.

Writes art/enemies/anvil_brute/reports/anvil_brute_review_fix.png (and work/fix/fix_metrics.json).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Quaternion, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "anvil_brute"
PPM = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
GAME_DIR = Vector((0.0, -math.cos(math.radians(SPEC.GAME_PITCH_DEG)), math.sin(math.radians(SPEC.GAME_PITCH_DEG))))
# the Cinder floor of the art review (sampled from the live game): mauve-brown flagstones, dark oxblood gaps
STONES = ["#361809", "#44200F", "#4E2616", "#5D2B16", "#603320", "#6A3C2B", "#774F43", "#86604F"]
GAP = "#2C0603"
CAMO = {"spec floor #3A2C24": "#3A2C24", "mid stone #603320": "#603320"}
BANDS = [  # (upper L*, colour, label) for the band map: below the floor band, the floor band, the stone band, above
    (12.3, (40, 60, 200), "below 12 (black)"), (21.6, (200, 40, 40), "12-22 floor"),
    (26.3, (230, 110, 30), "22-26 floor + stones"), (35.6, (230, 210, 40), "26-36 mid stones"),
    (200.0, (60, 200, 90), "above 36")]
# (tag, label, yaw deg, clip, t, frame centre height m) - the art review's metric poses (yaw 0 = facing the camera)
POSES = [("rest_toward", "idle, facing the camera", 0.0, "idle@loop", 0.0, 1.35),
         ("rest_34", "idle, 3/4", 40.0, "idle@loop", 0.3, 1.35),
         ("windup", "windup (loaded, fists at 3.8 m)", 25.0, "windup", 1.0, 1.95)]
SHORT = {"rest_toward": "idle", "rest_34": "idle 3/4", "windup": "windup"}   # labels under the 1x images
PX = 200                   # the game-camera crops: 200 x 200 true pixels (4.1 m)


# ---- value metrics -------------------------------------------------------------------------------------------------

def lstar(rgb8):
    """CIE L* of sRGB 0..255 values (..., 3)."""
    c = np.asarray(rgb8, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    Y = lin @ np.array([0.2126, 0.7152, 0.0722])
    f = np.where(Y > 0.008856, np.cbrt(Y), 7.787 * Y + 16 / 116.0)
    return 116 * f - 16


def hex8(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def load_rgba(path):
    """Top-left-origin (h, w, 4) uint8 array of a PNG."""
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return (np.clip(px.reshape(h, w, 4)[::-1], 0, 1) * 255 + 0.5).astype(np.uint8)


def save_rgb(arr, path):
    h, w = arr.shape[:2]
    o = bpy.data.images.new("gfa_fix_out", w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = arr[..., :3].astype(np.float32) / 255.0
    o.pixels.foreach_set(np.ascontiguousarray(rgba[::-1]).ravel())
    o.filepath_raw = path
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    return path


def metrics(rgba_path):
    """The art review's value metric over the creature's pixels (alpha > 0.6) of a transparent render."""
    im = load_rgba(rgba_path)
    m = im[..., 3] > 153
    L = lstar(im[..., :3][m])
    out = {"px": int(m.sum()), "L_median": round(float(np.median(L)), 1),
           "L_p10": round(float(np.percentile(L, 10)), 1), "L_p90": round(float(np.percentile(L, 90)), 1)}
    for name, h in CAMO.items():
        Lf = float(lstar(hex8(h)))
        out["camo " + name] = round(100.0 * float((np.abs(L - Lf) < 7.0).mean()), 1)
    return out


def band_map(rgba_path, out_path, bg=(26, 24, 30)):
    """Every creature pixel coloured by its L* band (BANDS)."""
    im = load_rgba(rgba_path)
    m = im[..., 3] > 153
    L = lstar(im[..., :3])
    out = np.zeros(im.shape[:2] + (3,), dtype=np.uint8)
    out[:] = bg
    lo = -1.0
    for hi, col, _lab in BANDS:
        out[m & (L >= lo) & (L < hi)] = col
        lo = hi
    return save_rgb(out, out_path)


# ---- floors and the game camera ----------------------------------------------------------------------------------

def flagstone_mat():
    """Irregular flagstones (a warped Voronoi) in the sampled stone colours, dark gaps, soft mottling; unlit."""
    m = bpy.data.materials.get("FIX_FLAGSTONE")
    if m:
        return m
    m = bpy.data.materials.new("FIX_FLAGSTONE")
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    em = N("ShaderNodeEmission")
    L(em.outputs[0], out.inputs[0])
    tc = N("ShaderNodeTexCoord")
    nz = N("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.9
    nz.inputs["Detail"].default_value = 1.0
    L(tc.outputs["Object"], nz.inputs["Vector"])
    warp = N("ShaderNodeVectorMath")
    warp.operation = "MULTIPLY_ADD"
    L(nz.outputs["Color"], warp.inputs[0])
    warp.inputs[1].default_value = (0.35, 0.35, 0.0)
    L(tc.outputs["Object"], warp.inputs[2])
    v1 = N("ShaderNodeTexVoronoi")
    v1.feature = "F1"
    v1.inputs["Scale"].default_value = 0.72
    v1.inputs["Randomness"].default_value = 0.85
    L(warp.outputs[0], v1.inputs["Vector"])
    v2 = N("ShaderNodeTexVoronoi")
    v2.feature = "DISTANCE_TO_EDGE"
    v2.inputs["Scale"].default_value = 0.72
    v2.inputs["Randomness"].default_value = 0.85
    L(warp.outputs[0], v2.inputs["Vector"])
    sep = N("ShaderNodeSeparateColor")
    L(v1.outputs["Color"], sep.inputs[0])
    cr = N("ShaderNodeValToRGB")
    cr.color_ramp.interpolation = "CONSTANT"
    els = cr.color_ramp.elements
    els[0].position, els[0].color = 0.0, C.hex_linear(STONES[0])
    els[1].position, els[1].color = 1.0 / len(STONES), C.hex_linear(STONES[1])
    for i in range(2, len(STONES)):
        e = els.new(i / float(len(STONES)))
        e.color = C.hex_linear(STONES[i])
    L(sep.outputs[0], cr.inputs["Fac"])
    nz2 = N("ShaderNodeTexNoise")
    nz2.inputs["Scale"].default_value = 2.2
    L(tc.outputs["Object"], nz2.inputs["Vector"])
    mott = N("ShaderNodeMapRange")
    L(nz2.outputs["Fac"], mott.inputs["Value"])
    mott.inputs["To Min"].default_value = 0.86
    mott.inputs["To Max"].default_value = 1.12
    mul = N("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(cr.outputs["Color"], mul.inputs[6])
    comb = N("ShaderNodeCombineColor")
    for i in range(3):
        L(mott.outputs[0], comb.inputs[i])
    L(comb.outputs[0], mul.inputs[7])
    gapf = N("ShaderNodeMapRange")
    L(v2.outputs["Distance"], gapf.inputs["Value"])
    gapf.inputs["From Min"].default_value = 0.045
    gapf.inputs["From Max"].default_value = 0.07
    gapf.inputs["To Min"].default_value = 1.0
    gapf.inputs["To Max"].default_value = 0.0
    mix = N("ShaderNodeMix")
    mix.data_type = "RGBA"
    L(gapf.outputs[0], mix.inputs["Factor"])
    L(mul.outputs[2], mix.inputs[6])
    mix.inputs[7].default_value = C.hex_linear(GAP)
    L(mix.outputs[2], em.inputs["Color"])
    return m


def floor(kind):
    """The floor plane of `kind` ("flag" or "flat"), shown; the other one hidden. kind None hides both."""
    for k in ("flag", "flat"):
        name = "FIX_FLOOR_" + k
        f = bpy.data.objects.get(name)
        if f is None:
            me = bpy.data.meshes.new(name)
            s = 60.0
            me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
            f = bpy.data.objects.new(name, me)
            bpy.context.scene.collection.objects.link(f)
            if k == "flag":
                me.materials.append(flagstone_mat())
            else:
                fm = bpy.data.materials.new("FIX_FLAT")
                nt = fm.node_tree
                nt.nodes.clear()
                o = nt.nodes.new("ShaderNodeOutputMaterial")
                e = nt.nodes.new("ShaderNodeEmission")
                e.inputs["Color"].default_value = C.hex_linear(R.FLOOR)
                nt.links.new(e.outputs[0], o.inputs[0])
                me.materials.append(fm)
        f.hide_render = (k != kind)


def game_render(meshes, path, px, target, kind="flag", samples=16):
    """The game camera (55 deg, view height 22 m) at TRUE 1080p pixel size, px x px, on a floor or transparent
    (kind None: RGBA)."""
    scene = bpy.context.scene
    R.setup_cycles(scene, samples, bg=R.FLOOR)
    floor(kind)
    if kind is None:
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode = "RGBA"
    with R.toon_preview(meshes, ink=0.012):
        R.aim(scene, target, GAME_DIR, px / PPM, dist=60.0)
        R.render(scene, path, px)
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    return path


# ---- the two GLBs ---------------------------------------------------------------------------------------------------

def import_glb(path, tag, park):
    """Import one GLB; its clips are keyed by clip name (a second import of the same key gets .001 names)."""
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers))
    for o in new:
        if o is not mesh and o.type in ("MESH", "EMPTY"):
            o.hide_render = True
    arm.name, mesh.name = tag + "_ARM", tag + "_MESH"
    acts = {}
    for act in bpy.data.actions:
        if act not in acts0 and act.name.startswith(KEY + "_"):
            act.use_fake_user = True
            acts[act.name.split(".")[0][len(KEY) + 1:]] = act
    missing = set(SPEC.ENEMY_CLIPS_REQUIRED) - set(acts)
    if missing:
        raise RuntimeError("%s has no clips %s" % (path, sorted(missing)))
    arm.animation_data_clear()
    q0 = arm.rotation_quaternion.copy() if arm.rotation_mode == "QUATERNION" else arm.rotation_euler.to_quaternion()
    arm.location = park
    return {"tag": tag, "arm": arm, "mesh": mesh, "acts": acts, "q0": q0}


def pose(v, yaw_deg, clip, t, state="intact"):
    """Pose the imported rig at its park spot: yaw (0 = facing the camera), the clip at t (0..1), then the plate
    state the engine sets after its animation system (intact: plate_<p> 1, plate_<p>_crk ~0)."""
    arm = v["arm"]
    arm.rotation_mode = "QUATERNION"
    arm.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(yaw_deg)) @ v["q0"]
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    act = v["acts"][clip]
    f0, f1 = act.frame_range
    arm.pose.apply_pose_from_action(act, evaluation_time=f0 + (f1 - f0) * t)
    if state == "intact":
        for pb in arm.pose.bones:
            if pb.name.startswith("plate_") and pb.name.endswith("_crk"):
                pb.scale = (0.001, 0.001, 0.001)
    bpy.context.view_layer.update()


def main():
    argv = C.script_args()
    before_dir = C.opt(argv, "--before", None, str)
    if not before_dir:
        raise SystemExit("usage: ... -- --before BEFORE_DIR")
    C.reset_scene(fps=30)
    pack = C.pack_dir("enemy", KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "fix"))
    reports = os.path.join(pack, "reports")
    V = {"before": import_glb(os.path.join(before_dir, KEY + ".glb"), "before", (0.0, 0.0, 0.0)),
         "after": import_glb(C.model_path("enemy", KEY), "after", (0.0, 0.0, 0.0))}
    rows = {}
    met = {}
    for tag, v in V.items():
        other = V["after" if tag == "before" else "before"]
        other["mesh"].hide_render = True
        v["mesh"].hide_render = False
        rows[tag] = []
        met[tag] = {}
        for ptag, label, yaw, clip, t, zc in POSES:
            pose(v, yaw, clip, t)
            tgt = Vector((0.0, -0.1, zc))
            stem = os.path.join(work, "%s_%s" % (tag, ptag))
            flag = game_render([v["mesh"]], stem + "_flag.png", PX, tgt, "flag")
            flat = game_render([v["mesh"]], stem + "_flat.png", PX, tgt, "flat")
            tr = game_render([v["mesh"]], stem + "_rgba.png", PX, tgt, None)
            bands = band_map(tr, stem + "_bands.png")
            met[tag][ptag] = metrics(tr)
            rows[tag].append({"pose": ptag, "label": label, "flag": flag, "flat": flat, "bands": bands})
        v["mesh"].hide_render = True
    close = {"before": os.path.join(before_dir, KEY + "_34.png"), "after": os.path.join(reports, KEY + "_34.png")}

    def summary(tag):
        ms = met[tag]
        keys = [p[0] for p in POSES]
        return {k: round(sum(ms[p][k] for p in keys) / len(keys), 1)
                for k in ("L_median", "camo spec floor #3A2C24", "camo mid stone #603320")}
    sb, sa = summary("before"), summary("after")

    def game_row(tag, kind, scale=2):
        return [{"path": r[kind], "label": "%s: %s" % (tag, r["label"] if scale > 1 else SHORT[r["pose"]]),
                 "scale": scale} for r in rows[tag]]
    band_txt = " | ".join("%s = %s" % (lab, "rgb(%d,%d,%d)" % col) for _hi, col, lab in BANDS)
    layout = {
        "title": "Anvil Brute - art review fixes (6.5/10), before and after",
        "subtitle": "both GLBs imported and posed from their own clips, plates intact; game camera 55 deg, %.1f px/m, "
                    "TRUE 1080p pixels (shown 2x nearest in the first two rows)" % PPM,
        "width": 1600,
        "sections": [
            {"label": "BEFORE, on the Cinder flagstones: the plum body melts into the stones; the cuffs, domes and visor "
                      "are flat mid-grey blocks", "height": None, "images": game_row("before", "flag")},
            {"label": "AFTER: top planes in obsidian light #4B4658, light crest strokes; cuffs, domes and visor in iron "
                      "shadow with one top-edge stroke", "height": None, "images": game_row("after", "flag")},
            {"label": "On the spec floor #3A2C24 at 1x: before (first three) | after", "height": None,
             "images": game_row("before", "flat", 1) + game_row("after", "flat", 1)},
            {"label": "L* bands of the creature's pixels at 1x: before (first three) | after", "height": None,
             "images": game_row("before", "bands", 1) + game_row("after", "bands", 1)},
            {"label": "3/4 view, toon preview of the final textures: before | after (the anvil face is the one bright "
                      "metal)", "height": 560,
             "images": [{"path": close["before"], "label": "before"}, {"path": close["after"], "label": "after"}]},
        ],
        "notes": [
            "Value metric (the art review's, mean of the three poses): median L* %.1f -> %.1f; within +-7 L* of the spec "
            "floor %.0f %% -> %.0f %%, of the mid flagstone %.0f %% -> %.0f %%." % (
                sb["L_median"], sa["L_median"], sb["camo spec floor #3A2C24"], sa["camo spec floor #3A2C24"],
                sb["camo mid stone #603320"], sa["camo mid stone #603320"]),
            "Band map colours: %s." % band_txt,
            "Skeleton, clips, sockets, plate states and file names are unchanged. Status: %s." % SPEC.STATUS_AI_FINAL,
        ],
    }
    out = R.contact_sheet(layout, os.path.join(reports, KEY + "_review_fix.png"), work)
    C.write_json(os.path.join(work, "fix_metrics.json"), {"per_pose": met, "mean": {"before": sb, "after": sa}})
    C.log("DONE anvil_brute fix sheet", out, "before", sb, "after", sa)


if __name__ == "__main__":
    main()
