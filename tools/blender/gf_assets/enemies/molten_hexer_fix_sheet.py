"""Before / after sheet for the molten_hexer art-review fixes (review 6.5/10, two must-fix items).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P tools/blender/gf_assets/enemies/molten_hexer_fix_sheet.py -- --before BEFORE_DIR

Run after enemies/molten_hexer.py. BEFORE_DIR holds the pre-fix files of commit 4a12556 (LFS files smudged):
  molten_hexer.glb           git show 4a12556:assets/models/enemies/molten_hexer.glb | git lfs smudge
  molten_hexer_emissive.png  git show 4a12556:art/enemies/molten_hexer/textures/molten_hexer_emissive.png | git lfs smudge
AFTER is the shipped assets/models/enemies/molten_hexer.glb and textures/molten_hexer_emissive.png.

Stage 1 (Blender): each GLB is imported into a fresh scene, posed from its own clips and rendered with the toon
preview of its own textures: a front / 3/4 / right-side turnaround at one fixed scale, the five poses of the art
review through the game camera at TRUE 1080p pixels (transparent: the floor-value numbers), a frame on the Cinder
flagstones (true pixels, a 2.2 m hero mannequin), and the crucible (a close-up, and the melt seen from straight
above in emission only: the rendered ramp from the core out to the rim).
Stage 2 (this file again, run by stage 1 under ComfyUI's python for PIL): the numbers, the masks and the sheet
art/enemies/molten_hexer/reports/molten_hexer_review_fix.png (+ work/fix/fix_metrics.json).

The floor numbers are the review's: the share of the hexer's pixels within +-7 L* of the flagstone gaps (#2C0603)
and of the dark stones (#44200F); the gold numbers: emissive texels within dE 20 (CIE76) of the player gold
#FFC940, and the rendered pixels in that band.
"""
import json
import math
import os
import sys

try:
    import bpy  # noqa: F401
except ImportError:          # stage 2 (PIL) runs outside Blender
    bpy = None

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
KEY = "molten_hexer"
PACK = os.path.join(ROOT, "art", "enemies", KEY)
WORK = os.path.join(PACK, "work", "fix")
PLAYER_GOLD = "#FFC940"
GAP, DARK_STONE = "#2C0603", "#44200F"          # the Cinder floor's flagstone gaps and dark stones
STONES = ["#361809", "#44200F", "#4E2616", "#5D2B16", "#603320", "#6A3C2B", "#774F43", "#86604F"]
# (tag, label, yaw deg, clip, normalised time) - the art review's five game-camera poses
POSES = [("rest_toward", "idle, facing the camera", 0.0, "idle@loop", 0.0),
         ("rest_34", "idle, 3/4", 40.0, "idle@loop", 0.3),
         ("move_side", "glide, side on", 90.0, "move@loop", 0.5),
         ("away", "glide, walking away", 180.0, "move@loop", 0.2),
         ("windup", "windup (loaded)", 25.0, "windup", 1.0)]
TURN = [("front", "front", (0.0, -1.0, 0.08)), ("34", "3/4 front", (0.62, -1.0, 0.36)),
        ("side", "its right side (the slag arm)", (-1.0, -0.05, 0.1))]
GAME_PX = 160               # game-pose frames: 160 px = 3.26 m of world at 1080p
FLAG_W, FLAG_H = 300, 180   # the flagstone frame, true pixels
MELT_M, MELT_PX = 0.56, 224  # the melt from above: 0.56 m in 224 px (400 px/m)
MELT_R = 0.228               # the melt's radius (build_crucible)


# ================================================ stage 1: Blender ================================================

def _blender_imports():
    sys.path.insert(0, os.path.join(HERE, ".."))
    import gfa_common as C
    import gfa_render as R
    import gfa_spec as SPEC
    return C, R, SPEC


def import_glb(path):
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in objs0]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers))
    for o in new:
        if o is not mesh and o.type in ("MESH", "EMPTY"):
            o.hide_render = True
    acts = {}
    for act in bpy.data.actions:
        if act in acts0:
            continue
        act.use_fake_user = True
        acts[act.name.split(".")[0][len(KEY) + 1:]] = act
    arm.animation_data_clear()
    q0 = arm.rotation_quaternion.copy() if arm.rotation_mode == "QUATERNION" else arm.rotation_euler.to_quaternion()
    return {"arm": arm, "mesh": mesh, "acts": acts, "q0": q0}


def pose(v, yaw_deg, clip, t, loc=(0.0, 0.0, 0.0)):
    from mathutils import Quaternion
    arm = v["arm"]
    arm.location = loc
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
    bpy.context.view_layer.update()


def spawn_copy(v, loc, yaw_deg, clip, t):
    """A posed copy of the imported hexer (the flagstone frame shows two at once)."""
    from mathutils import Quaternion
    col = bpy.context.scene.collection
    a2 = v["arm"].copy()
    col.objects.link(a2)
    a2.animation_data_clear()
    m2 = v["mesh"].copy()
    m2.data = v["mesh"].data.copy()
    m2.hide_render = False          # the original is hidden while the copies render
    col.objects.link(m2)
    m2.parent = a2
    m2.matrix_parent_inverse = v["mesh"].matrix_parent_inverse.copy()
    for mod in m2.modifiers:
        if mod.type == "ARMATURE":
            mod.object = a2
    a2.location = loc
    a2.rotation_mode = "QUATERNION"
    a2.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), math.radians(yaw_deg)) @ v["q0"]
    for pb in a2.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    act = v["acts"][clip]
    f0, f1 = act.frame_range
    a2.pose.apply_pose_from_action(act, evaluation_time=f0 + (f1 - f0) * t)
    return a2, m2


def flagstone_mat(C):
    """The Cinder Wastes floor of the art review: warped voronoi flagstones in eight mauve-brown values with
    oxblood gaps and a soft mottle (emission only, so it renders at its painted value)."""
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
    cells, edges = N("ShaderNodeTexVoronoi"), N("ShaderNodeTexVoronoi")
    cells.feature, edges.feature = "F1", "DISTANCE_TO_EDGE"
    for vn in (cells, edges):
        vn.inputs["Scale"].default_value = 0.72
        vn.inputs["Randomness"].default_value = 0.85
        L(warp.outputs[0], vn.inputs["Vector"])
    sep = N("ShaderNodeSeparateColor")
    L(cells.outputs["Color"], sep.inputs[0])
    cr = N("ShaderNodeValToRGB")
    cr.color_ramp.interpolation = "CONSTANT"
    els = cr.color_ramp.elements
    els[0].position, els[0].color = 0.0, C.hex_linear(STONES[0])
    els[1].position, els[1].color = 1.0 / len(STONES), C.hex_linear(STONES[1])
    for i in range(2, len(STONES)):
        els.new(i / float(len(STONES))).color = C.hex_linear(STONES[i])
    L(sep.outputs[0], cr.inputs["Fac"])
    nz2 = N("ShaderNodeTexNoise")
    nz2.inputs["Scale"].default_value = 2.2
    L(tc.outputs["Object"], nz2.inputs["Vector"])
    mott = N("ShaderNodeMapRange")
    L(nz2.outputs["Fac"], mott.inputs["Value"])
    mott.inputs["To Min"].default_value = 0.86
    mott.inputs["To Max"].default_value = 1.12
    comb = N("ShaderNodeCombineColor")
    for i in range(3):
        L(mott.outputs[0], comb.inputs[i])
    mul = N("ShaderNodeMix")
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(cr.outputs["Color"], mul.inputs[6])
    L(comb.outputs[0], mul.inputs[7])
    gapf = N("ShaderNodeMapRange")
    L(edges.outputs["Distance"], gapf.inputs["Value"])
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


def blob_shadow(loc, radius):
    n = 40
    me = bpy.data.meshes.new("FIX_SHADOW")
    me.from_pydata([(0, 0, 0)] + [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), 0) for i in range(n)],
                   [], [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)])
    m = bpy.data.materials.new("FIX_SHADOW")
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out, mx = N("ShaderNodeOutputMaterial"), N("ShaderNodeMixShader")
    tr, em = N("ShaderNodeBsdfTransparent"), N("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.02 ** 2.2, 0.015 ** 2.2, 0.04 ** 2.2, 1)
    tc, gr, mr = N("ShaderNodeTexCoord"), N("ShaderNodeTexGradient"), N("ShaderNodeMapRange")
    gr.gradient_type = "SPHERICAL"
    L(tc.outputs["Object"], gr.inputs["Vector"])
    L(gr.outputs["Fac"], mr.inputs["Value"])
    mr.inputs["From Max"].default_value = 0.7
    mr.inputs["To Max"].default_value = 0.6
    L(mr.outputs[0], mx.inputs["Fac"])
    L(tr.outputs[0], mx.inputs[1])
    L(em.outputs[0], mx.inputs[2])
    L(mx.outputs[0], out.inputs[0])
    me.materials.append(m)
    o = bpy.data.objects.new("FIX_SHADOW", me)
    o.location = (loc[0], loc[1], 0.012)
    o.scale = (radius * 1.25, radius * 1.25, 1)
    bpy.context.scene.collection.objects.link(o)
    return o


def emissive_only(R, obj):
    """Swap the materials for emission-only ones (the emissive texture at strength 1) and return the originals."""
    saved = [s.material for s in obj.material_slots]
    made = []
    for s in obj.material_slots:
        img = R._tex_of(s.material, "Emission Color")
        mm = bpy.data.materials.new("FIX_EMO")
        nt = mm.node_tree
        nt.nodes.clear()
        out, em = nt.nodes.new("ShaderNodeOutputMaterial"), nt.nodes.new("ShaderNodeEmission")
        if img is not None:
            tx = nt.nodes.new("ShaderNodeTexImage")
            tx.image = img
            nt.links.new(tx.outputs[0], em.inputs["Color"])
        else:
            em.inputs["Color"].default_value = (0, 0, 0, 1)
        nt.links.new(em.outputs[0], out.inputs[0])
        s.material = mm
        made.append(mm)
    return saved, made


def game_dir(SPEC):
    from mathutils import Vector
    p = math.radians(SPEC.GAME_PITCH_DEG)
    return Vector((0.0, -math.cos(p), math.sin(p)))


def render_one(tag, glb, C, R, SPEC):
    from mathutils import Vector
    C.reset_scene(fps=30)
    scene = bpy.context.scene
    out_dir = C.ensure_dir(os.path.join(WORK, tag))
    v = import_glb(glb)
    mesh = v["mesh"]
    rec = {"turn": {}, "game": {}}
    view_h = SPEC.GAME_VIEW_HEIGHTS[0]
    # the turnaround: rest pose, one fixed orthographic scale for both builds
    pose(v, 0.0, "idle@loop", 0.0)
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh], ink=0.011):
        for t, _label, d in TURN:
            R.aim(scene, Vector((0.0, -0.1, 1.38)), Vector(d).normalized(), 3.3)
            rec["turn"][t] = R.render(scene, os.path.join(out_dir, "turn_%s.png" % t), 330)
    # the review's five poses at the game camera, TRUE pixels, transparent (the floor-value numbers)
    for t, _label, yaw, clip, tt in POSES:
        pose(v, yaw, clip, tt)
        R.setup_cycles(scene, 10, bg=R.FLOOR)
        scene.render.film_transparent = True
        scene.render.image_settings.color_mode = "RGBA"
        with R.toon_preview([mesh], ink=0.012):
            R.aim(scene, Vector((0.0, 0.0, 1.13)), game_dir(SPEC), view_h * GAME_PX / SPEC.SCREEN_H, dist=150.0)
            rec["game"][t] = R.render(scene, os.path.join(out_dir, "game_%s.png" % t), GAME_PX)
        scene.render.film_transparent = False
        scene.render.image_settings.color_mode = "RGB"
    # the crucible: a close-up (game direction, idle) and the melt from straight above in emission only
    pose(v, 0.0, "idle@loop", 0.0)
    arm = v["arm"]
    melt = arm.matrix_world @ arm.pose.bones["molten"].head
    R.setup_cycles(scene, 16)
    with R.toon_preview([mesh], ink=0.008):
        R.aim(scene, melt + Vector((0.0, -0.08, -0.05)), game_dir(SPEC), 1.15)
        rec["crucible"] = R.render(scene, os.path.join(out_dir, "crucible.png"), 280)
    saved, made = emissive_only(R, mesh)
    R.setup_cycles(scene, 8, bg="#000000")
    R.aim(scene, Vector((melt.x, melt.y, melt.z)), Vector((0.0, 0.0, 1.0)), MELT_M)
    rec["melt_top"] = R.render(scene, os.path.join(out_dir, "melt_top.png"), MELT_PX)
    for s, mm in zip(mesh.material_slots, saved):
        s.material = mm
    for mm in made:
        bpy.data.materials.remove(mm)
    # the Cinder flagstones, TRUE pixels: idle (3/4 toward the camera) + windup + a 2.2 m hero mannequin
    fl = bpy.data.meshes.new("FIX_FLOOR")
    fl.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("FIX_FLOOR", fl)
    scene.collection.objects.link(floor)
    fl.materials.append(flagstone_mat(C))
    mesh.hide_render = True
    made_objs = list(spawn_copy(v, (-1.3, 0.0, 0.0), -25.0, "idle@loop", 0.0))
    made_objs += list(spawn_copy(v, (1.5, 0.3, 0.0), 20.0, "windup", 1.0))
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0), name="FIX_HERO")
    man.location = (-3.4, -1.2, 0.0)
    shadows = [blob_shadow((-1.3, 0.0), 0.682), blob_shadow((1.5, 0.3), 0.682), blob_shadow((-3.4, -1.2), 0.45)]
    bpy.context.view_layer.update()
    copies = [o for o in made_objs if o.type == "MESH"]
    R.setup_cycles(scene, 12, bg=R.FLOOR)
    with R.toon_preview(copies + [man], ink=0.012, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, Vector((-0.85, 0.0, 0.9)), game_dir(SPEC), view_h * FLAG_W / SPEC.SCREEN_H, dist=150.0)
        rec["flag"] = R.render(scene, os.path.join(out_dir, "flag_1x.png"), FLAG_W, FLAG_H)
    return rec


def stage1(before_dir):
    C, R, SPEC = _blender_imports()
    C.ensure_dir(WORK)
    rec = {
        "before": render_one("before", os.path.join(before_dir, KEY + ".glb"), C, R, SPEC),
        "after": render_one("after", C.model_path("enemy", KEY), C, R, SPEC),
        "emissive": {"before": os.path.join(before_dir, KEY + "_emissive.png"),
                     "after": os.path.join(PACK, "textures", KEY + "_emissive.png")},
        "ppm": SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0],
        "status": SPEC.STATUS_AI_FINAL,
    }
    spec = os.path.join(WORK, "fix_renders.json")
    C.write_json(spec, rec, quiet=True)
    C.run_comfy_python(os.path.join("enemies", os.path.basename(__file__)), "--compose", spec)
    C.log("DONE molten_hexer fix sheet")


# ================================================ stage 2: PIL ====================================================

def _lab(rgb):
    import numpy as np
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def floor_numbers(path):
    """The review's floor-value numbers for one transparent game-camera frame."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64)
    fig = a[..., 3] > 0.6 * 255
    L = _lab(a[..., :3])[..., 0]
    lg, ld = float(_lab(_hex(GAP))[0]), float(_lab(_hex(DARK_STONE))[0])
    near_g = (np.abs(L - lg) < 7.0) & fig
    near_d = (np.abs(L - ld) < 7.0) & fig
    n = max(1, int(fig.sum()))
    de = np.linalg.norm(_lab(a[..., :3]) - _lab(_hex(PLAYER_GOLD)), axis=-1)
    return {"px": n, "gap": 100.0 * near_g.sum() / n, "dark": 100.0 * near_d.sum() / n,
            "either": 100.0 * (near_g | near_d).sum() / n, "Lmed": float(np.median(L[fig])),
            "gold": 100.0 * ((de < 20) & fig).sum() / n}, (near_g | near_d), fig


def texel_gold(path):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    lit = a.max(-1) > 30
    de = np.linalg.norm(_lab(a) - _lab(_hex(PLAYER_GOLD)), axis=-1)
    return {"texels": int(lit.sum()), "share_de20": 100.0 * float(((de < 20) & lit).sum()) / max(1, int(lit.sum())),
            "min_de": float(de[lit].min())}, (de < 20) & lit, a


def melt_ramp(path, n=13):
    """The rendered melt from its centre (the image centre) out to its rim: the median colour of each ring."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - (w - 1) / 2.0, yy - (h - 1) / 2.0)
    rmax = MELT_R * MELT_PX / MELT_M
    lit = a.max(-1) > 40
    out = []
    for k in range(n):
        r0 = rmax * k / n
        r1 = rmax * (k + 1) / n
        m = (r >= r0) & (r < r1) & lit
        if m.sum() < 3:
            continue
        out.append((tuple(int(round(v)) for v in np.median(a[m], axis=0)), (r0 + r1) / 2.0 / rmax))
    return out


def stage2(spec_path):
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.join(ROOT, "tools", "comfy"))
    import gf_img as G
    rec = json.load(open(spec_path, encoding="utf-8"))
    BG, PANEL, INK, SUB, HEAD, MARK = (30, 27, 33), (40, 36, 44), (232, 226, 212), (160, 152, 140), (242, 193, 78), \
        (255, 0, 255)
    W, pad = 1600, 16
    gold_lab = _lab(_hex(PLAYER_GOLD))

    # ---- numbers ----
    num = {"floor": {}, "texels": {}, "ramp": {}}
    masks = {}
    for tag in ("before", "after"):
        num["floor"][tag] = {}
        for t, *_ in POSES:
            nums, mk, fig = floor_numbers(rec[tag]["game"][t])
            num["floor"][tag][t] = nums
            masks[(tag, t)] = (mk, fig)
        num["texels"][tag], gmask, emis = texel_gold(rec["emissive"][tag])
        masks[(tag, "tex")] = (gmask, emis)
        num["ramp"][tag] = melt_ramp(rec[tag]["melt_top"])

    def mean(tag, k):
        return sum(num["floor"][tag][t][k] for t, *_ in POSES) / len(POSES)

    # ---- helpers ----
    def up(im, s):
        return im.resize((im.width * s, im.height * s), Image.NEAREST)

    def fit_h(im, h):
        return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)

    def masked_game(tag, t, s):
        a = np.asarray(Image.open(rec[tag]["game"][t]).convert("RGBA")).astype(np.float64)
        mk, fig = masks[(tag, t)]
        rgb = a[..., :3] * (a[..., 3:4] / 255.0) + np.array(_hex("#3A2C24"), dtype=np.float64) * (1 - a[..., 3:4] / 255.0)
        rgb[mk] = MARK
        return up(Image.fromarray(rgb.astype(np.uint8)), s)

    def gold_texture(tag, size=250):
        gm, a = masks[(tag, "tex")]
        # dilate the gold texels so they survive the downscale, then mark them over a dimmed texture
        g = gm.copy()
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                g |= np.roll(np.roll(gm, dy, 0), dx, 1)
        b = a * 0.55
        b[g] = MARK
        return Image.fromarray(b.astype(np.uint8)).resize((size, size), Image.BOX)

    blocks = []    # (height, draw fn(sheet, draw, y))

    def section(title, lines, body_h, body):
        h = 34 + 21 * len(lines) + body_h + 12

        def draw(sheet, d, y):
            d.rectangle((6, y + 2, W - 6, y + h - 4), fill=PANEL)
            G.text(d, (pad, y + 8), title, 19, True, HEAD)
            yy = y + 36
            for ln in lines:
                G.text(d, (pad, yy), ln, 14, False, INK)
                yy += 21
            body(sheet, d, yy)
        blocks.append((h, draw))

    def paste_row(sheet, d, x, y, items, gap=14, label_size=13):
        """items: [(image, label)], pasted left to right with labels under them; returns the next x."""
        for im, lb in items:
            sheet.paste(im, (x, y))
            if lb:
                G.text(d, (x + 2, y + im.height + 4), lb, label_size, False, SUB)
            x += im.width + gap
        return x

    # ---- section 1: the cake ----
    th = 236
    turns = {tag: [(fit_h(Image.open(rec[tag]["turn"][t]).convert("RGB"), th), "%s: %s" % (tag, lb))
                   for t, lb, _d in TURN] for tag in ("before", "after")}

    def body1(sheet, d, y):
        x = paste_row(sheet, d, pad, y, turns["before"], gap=10)
        d.line((x + 2, y, x + 2, y + th), fill=HEAD, width=2)
        paste_row(sheet, d, x + 16, y, turns["after"], gap=10)
    section("1  THE TIERED CAKE -> three uneven tiers (the same fixed orthographic scale, rest pose)",
            ["BEFORE: a cape over three stacked, near-symmetric skirts with parallel hems - a tiered cake / pagoda.",
             "AFTER: two skirts merged into ONE long overrobe that slumps toward the heavy slag arm: its hem is a diagonal, "
             "torn long at the right-front,",
             "hitched short over the left-back (the underskirt shows there as a wedge leaning the other way); the cape is "
             "short, broad and longer under the slag arm.",
             "Two bold molten fissures split the overrobe from its torn hem, so the one long tier stays cooling slag, "
             "not cloth."], th + 24, body1)

    # ---- section 2: the dark floor ----
    fb = [Image.open(rec[tag]["flag"]).convert("RGB") for tag in ("before", "after")]
    mk_poses = ("rest_34", "windup")
    ms = 2

    def body2(sheet, d, y):
        x = paste_row(sheet, d, pad, y, [(up(fb[0], 2), "before, 2x nearest"), (up(fb[1], 2), "after, 2x nearest")])
        sheet.paste(fb[0], (x, y))
        G.text(d, (x + 2, y + FLAG_H + 3), "before 1x (true size)", 12, False, SUB)
        sheet.paste(fb[1], (x, y + FLAG_H + 22))
        G.text(d, (x + 2, y + 2 * FLAG_H + 25), "after 1x", 12, False, SUB)
        y2 = y + 2 * FLAG_H + 50
        items = []
        for t in mk_poses:
            label = next(lb for tt, lb, *_ in POSES if tt == t)
            for tag in ("before", "after"):
                f = num["floor"][tag][t]
                items.append((masked_game(tag, t, ms), "%s, %s: %.0f %% magenta" % (tag, label, f["either"])))
        x2 = paste_row(sheet, d, pad, y2, items[:2], gap=10)
        paste_row(sheet, d, x2 + 30, y2, items[2:], gap=10)
        y3 = y2 + GAME_PX * ms + 30
        G.text(d, (pad, y3), "pose (game camera, true pixels)", 14, True, INK)
        cols = (330, 610, 890, 1170)
        for c, lb in zip(cols, ("within +-7 L* of the gaps", "... of the dark stones", "either", "median L*")):
            G.text(d, (c, y3), lb, 14, True, INK)
        yy = y3 + 22
        for t, lb, *_ in POSES:
            b, a = num["floor"]["before"][t], num["floor"]["after"][t]
            G.text(d, (pad, yy), lb, 14, False, SUB)
            for c, k, fmt in zip(cols, ("gap", "dark", "either", "Lmed"), ("%.0f %% -> %.1f %%",) * 3 + ("%.0f -> %.0f",)):
                G.text(d, (c, yy), fmt % (b[k], a[k]), 14, False, INK)
            yy += 20
    section("2  LOST IN THE DARK FLOOR -> a coal robe and pale ash tops that clear the Cinder flagstones",
            ["The review measured 30-35 %% of the hexer's pixels within +-7 L* of the flagstone gaps (L* %.0f) and the "
             "dark stones (L* %.0f); magenta marks those pixels below."
             % (_lab(_hex(GAP))[0], _lab(_hex(DARK_STONE))[0]),
             "AFTER: the slag body is a cool coal (#3E3234, a hue off the warm floor) lightening up the overrobe, the "
             "underskirt a lighter cooled crust, the up-facing crust ash (#6E625C),",
             "and the cape and the shoulder boulder - the planes the 55 deg camera sees first - the palest ash "
             "(#877A72), above every floor stone. No near-black slag is left."],
            2 * FLAG_H + 50 + GAME_PX * ms + 30 + 22 + 20 * len(POSES) + 6, body2)

    # ---- section 3: the melt ramp ----
    tb, ta = num["texels"]["before"], num["texels"]["after"]
    gb, ga = mean("before", "gold"), mean("after", "gold")
    crus = [(Image.open(rec[tag]["crucible"]).convert("RGB"), "%s: the crucible (toon preview)" % tag)
            for tag in ("before", "after")]
    gtex = [(gold_texture(tag), "%s: emissive map, gold texels" % tag) for tag in ("before", "after")]
    chip, cgap = 92, 8

    def body3(sheet, d, y):
        x = paste_row(sheet, d, pad, y, crus + gtex)
        G.text(d, (x, y + 4), "emissive texels within dE 20", 14, True, INK)
        G.text(d, (x, y + 24), "of #FFC940: %.1f %% -> %.1f %%" % (tb["share_de20"], ta["share_de20"]), 14, False, INK)
        G.text(d, (x, y + 52), "closest texel: dE %.1f -> %.1f" % (tb["min_de"], ta["min_de"]), 14, False, INK)
        G.text(d, (x, y + 80), "rendered gold pixels, five", 14, True, INK)
        G.text(d, (x, y + 100), "game poses: %.2f %% -> %.2f %%" % (gb, ga), 14, False, INK)
        yy = y + 280 + 26
        G.text(d, (pad, yy), "the rendered melt from its white-hot centre out to its rim (seen from straight above, "
                             "emission only; dE to #FFC940 under each chip, magenta frame = the gold band, dE < 20)",
               14, True, INK)
        yy += 26
        for tag in ("before", "after"):
            G.text(d, (pad, yy + 14), tag, 16, True, HEAD if tag == "after" else SUB)
            x = pad + 80
            for col, _r in num["ramp"][tag]:
                de = float(np.linalg.norm(_lab(col) - gold_lab))
                d.rectangle((x, yy, x + chip, yy + 40), fill=col)
                if de < 20:
                    d.rectangle((x - 3, yy - 3, x + chip + 3, yy + 43), outline=MARK, width=3)
                G.text(d, (x, yy + 44), "#%02X%02X%02X  %.0f" % (col + (de,)), 12, False, SUB)
                x += chip + cgap
            yy += 70
    section("3  THE MELT RAMP -> white-hot, peach, orange: no forge-gold band",
            ["BEFORE: the crucible's melt ran white-hot core -> forge gold #FFC24B -> orange; #FFC24B sits dE 5 from the "
             "player gold #FFC940, and the rune core lines were white-gold.",
             "AFTER: white-hot #FFF3D6 -> peach #FFC4A0 -> molten orange #FF6B1A -> rim #C8400C; the rune cores are "
             "peach-white; the pour drip glows orange over a half-value base",
             "(with the glow colour as its base, the toon key light plus the x1.6 emission washed it to gold)."],
            280 + 26 + 26 + 140, body3)

    # ---- sheet ----
    title_h = 76
    notes = ["Before = commit 4a12556, after = this fix; both GLBs imported with Blender's glTF importer and posed from "
             "their own clips; toon preview of their own textures; game camera 55 deg, %.1f px/m (1080p)." % rec["ppm"],
             "Skeleton (GF_MoltenHexer_v1), clips, sockets, the crucible and the rune crown are unchanged. "
             "Status: %s." % rec["status"]]
    H = title_h + sum(h for h, _ in blocks) + 22 * len(notes) + 24
    sheet, d = G.new_sheet(W, H, BG)
    G.text(d, (pad, 12), "Molten Hexer - art review fixes (6.5/10), before and after", 30, True, HEAD)
    G.text(d, (pad, 50), "must-fix 1: the tiered-cake robe lost in the dark floor | must-fix 2: the melt ramp through "
                         "forge gold", 15, False, SUB)
    y = title_h
    for h, fn in blocks:
        fn(sheet, d, y)
        y += h
    for n in notes:
        G.text(d, (pad, y + 6), n, 14, False, INK)
        y += 22
    out = os.path.join(PACK, "reports", KEY + "_review_fix.png")
    scale = 1.0
    while True:
        im = sheet if scale == 1.0 else sheet.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
        im.save(out, optimize=True)
        if os.path.getsize(out) <= 1_900_000 or scale < 0.5:
            break
        scale *= 0.9
    num["ramp"] = {k: [["#%02X%02X%02X" % c, round(r, 3)] for c, r in v] for k, v in num["ramp"].items()}
    with open(os.path.join(WORK, "fix_metrics.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(num, fh, indent=1)
    print("[fix_sheet] wrote %s (%dx%d, %.2f MB)" % (out, im.width, im.height, os.path.getsize(out) / 1e6))
    for tag in ("before", "after"):
        print("[fix_sheet] %s: floor either %.1f %% (gap %.1f, dark %.1f), rendered gold %.2f %%, texels %s"
              % (tag, mean(tag, "either"), mean(tag, "gap"), mean(tag, "dark"), mean(tag, "gold"),
                 json.dumps({k: round(v, 2) for k, v in num["texels"][tag].items()})))


def main():
    if bpy is None:
        stage2(sys.argv[sys.argv.index("--compose") + 1])
        return
    import gfa_common as C  # noqa: F401 - path set up below
    argv = C.script_args()
    before_dir = C.opt(argv, "--before", None, str)
    if not before_dir:
        raise SystemExit("usage: ... -- --before BEFORE_DIR")
    stage1(before_dir)


if __name__ == "__main__":
    if bpy is not None:
        sys.path.insert(0, os.path.join(HERE, ".."))
    main()
