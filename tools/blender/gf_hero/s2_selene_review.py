"""Stage 2 review renders for Selene (headless Blender; the sheets are composed by s2_selene_sheets.py).

  blender -b -P tools/blender/gf_hero/s2_selene_review.py -- <selene_stage2.blend> <out_dir> --launcher <thundercoil_launcher.glb>
          --fit <body_fit.json> [--report <review.json>] [--only <group,...>]

A copy of s2_valdris_review.py (which stays unchanged) with Selene's shots. Same camera conventions as s2_review.py
(Brax): the hero faces -Y, azimuth 0 = front, the in-game camera is orthographic at 55 deg pitch with FixedVertical
22 m / 28 m view heights and true 1080p pixel size. Nothing renders with EEVEE (the GPU is shared): the toon review is
a Cycles-CPU EMISSION shader that computes the lighting itself (key + fill N.L through the tangent normal map ->
constant bands -> x base colour, cool shadow band, rim, + emissive); clay / albedo / wire / silhouettes are Workbench.
"toonP1" adds the client's hero rim in the P1 colour. The signature weapon is the thundercoil_launcher GLB (the weapon
track's file), attached with an identity transform at the recorded right-hand frame (body_fit.json hand_frames.R).
Selene's blockout stands in the T-pose, so there is no review pose.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

from s2lib import (add_wire_overlay, aim_ortho, az_dir, get_co, log, opt, remove_objects, render_still,  # noqa: E402
                   script_args, setup_workbench, write_json)

argv = script_args(__doc__)
SRC, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
REF = opt(argv, "--ref", None, str)
CANNON = opt(argv, "--launcher", None, str)
FIT = opt(argv, "--fit", None, str)
REPORT = opt(argv, "--report", None, str)
ONLY = set(opt(argv, "--only", "", str).split(",")) - {""}
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=SRC)
scene = bpy.context.scene
prod = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith(("REF", "WIRE"))]
body = bpy.data.objects["BODY"]
fit = json.load(open(FIT)) if FIT else None
metrics = {"source": os.path.basename(SRC)}


def want(g):
    return not ONLY or g in ONLY


def wco(o):
    m = np.array(o.matrix_world)
    return get_co(o.data) @ m[:3, :3].T + m[:3, 3]


co = np.concatenate([wco(o) for o in prod])
lo, hi = co.min(0), co.max(0)
H = float(hi[2] - lo[2])
metrics.update({"bounds_m": {"min": lo.round(4).tolist(), "max": hi.round(4).tolist()}, "height_m": round(H, 4),
                "span_m": round(float(hi[0] - lo[0]), 4)})

# ---- the launcher on the right-hand frame -----------------------------------------------------------------------
armed = []
weapon_root = None
M_R = None
if CANNON and fit:
    before = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(CANNON))
    new = [o for o in scene.objects if o not in before]
    weapon_root = [o for o in new if o.parent is None][0]
    fr = fit["hand_frames"]["R"]
    M_R = Matrix.Identity(4)
    for i, a in enumerate(("x_axis", "y_axis", "z_axis")):
        for r in range(3):
            M_R[r][i] = fr[a][r]
    for r in range(3):
        M_R[r][3] = fr["origin"][r]
    weapon_root.matrix_world = M_R
    bpy.context.view_layer.update()
    armed = [o for o in new if o.type == "MESH"]
    metrics["launcher"] = {"glb": os.path.basename(CANNON), "attached_at": "hand_frames.R (identity)", "frame": fr}

# ---- toon review material (Cycles emission; lighting computed in the node tree) ----------------------------------
KEY_DIR = Vector((-0.45, -0.55, 0.70)).normalized()     # toward the key light: upper front-left (warm)
FILL_DIR = Vector((0.6, 0.45, 0.35)).normalized()       # toward the fill: back-right (cool)


def make_toon(M, rim_col=(0.5, 0.42, 0.34), rim_str=0.15, emis_str=2.2, name_suffix="_toon"):
    T = M.copy()
    T.name = M.name + name_suffix
    nt = T.node_tree
    texs = [n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image is not None]

    def find(key):
        for n in texs:
            if key in n.image.name.lower() or key in (n.image.filepath or "").lower():
                return n
        return None
    tb, te, tn = find("basecolor") or find("base"), find("emissive"), find("normal")
    if tb is None:          # glTF import: base colour texture feeds the Principled BSDF
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED" and n.inputs["Base Color"].links:
                tb = n.inputs["Base Color"].links[0].from_node
            if n.type == "BSDF_PRINCIPLED" and n.inputs["Emission Color"].links:
                te = n.inputs["Emission Color"].links[0].from_node
    keep = {tb, te, tn} - {None}
    for n in list(nt.nodes):
        if n not in keep:
            nt.nodes.remove(n)
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    if tn is not None:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.space = "TANGENT"
        nm.uv_map = "UVMap"
        L(tn.outputs["Color"], nm.inputs["Color"])
        N = nm.outputs["Normal"]
    else:
        N = geo.outputs["Normal"]

    def lambert(d, k):
        dp = nt.nodes.new("ShaderNodeVectorMath")
        dp.operation = "DOT_PRODUCT"
        L(N, dp.inputs[0])
        dp.inputs[1].default_value = tuple(d)
        mx = nt.nodes.new("ShaderNodeMath")
        mx.operation = "MAXIMUM"
        L(dp.outputs["Value"], mx.inputs[0])
        mx.inputs[1].default_value = 0.0
        mu = nt.nodes.new("ShaderNodeMath")
        mu.operation = "MULTIPLY"
        L(mx.outputs[0], mu.inputs[0])
        mu.inputs[1].default_value = k
        return mu.outputs[0]
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    L(lambert(KEY_DIR, 1.0), add.inputs[0])
    L(lambert(FILL_DIR, 0.35), add.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.40, 0.37, 0.46, 1)        # shadow band (lifted, cool: toon.wesl lift 0.35)
    els[1].position, els[1].color = 0.22, (0.70, 0.67, 0.68, 1)
    e3 = els.new(0.55)
    e3.color = (1.0, 0.96, 0.9, 1)                                      # warm key
    e4 = els.new(0.92)
    e4.color = (1.18, 1.12, 1.02, 1)
    L(add.outputs[0], ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(ramp.outputs["Color"], mul.inputs["A"])
    if tb is not None:
        L(tb.outputs["Color"], mul.inputs["B"])
    # rim: 1 - |N.V| through a smooth step (toon.wesl: smoothstep(1 - w, 1 - 0.45 w, 1 - ndv), w = 0.42)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    L(N, lw.inputs["Normal"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value = 0.58
    mr.inputs["From Max"].default_value = 0.81
    L(lw.outputs["Facing"], mr.inputs["Value"])
    rimc = nt.nodes.new("ShaderNodeMix")
    rimc.data_type = "RGBA"
    rimc.blend_type = "MULTIPLY"
    rimc.inputs["Factor"].default_value = 1.0
    L(mr.outputs["Result"], rimc.inputs["A"])
    rimc.inputs["B"].default_value = (rim_col[0] * rim_str, rim_col[1] * rim_str, rim_col[2] * rim_str, 1)
    a1 = nt.nodes.new("ShaderNodeMix")
    a1.data_type = "RGBA"
    a1.blend_type = "ADD"
    a1.inputs["Factor"].default_value = 1.0
    L(mul.outputs["Result"], a1.inputs["A"])
    L(rimc.outputs["Result"], a1.inputs["B"])
    fin = a1.outputs["Result"]
    if te is not None:
        em = nt.nodes.new("ShaderNodeMix")
        em.data_type = "RGBA"
        em.blend_type = "MULTIPLY"
        em.inputs["Factor"].default_value = 1.0
        L(te.outputs["Color"], em.inputs["A"])
        em.inputs["B"].default_value = (emis_str, emis_str, emis_str, 1)
        a2 = nt.nodes.new("ShaderNodeMix")
        a2.data_type = "RGBA"
        a2.blend_type = "ADD"
        a2.inputs["Factor"].default_value = 1.0
        L(fin, a2.inputs["A"])
        L(em.outputs["Result"], a2.inputs["B"])
        fin = a2.outputs["Result"]
    emn = nt.nodes.new("ShaderNodeEmission")
    L(fin, emn.inputs["Color"])
    L(emn.outputs[0], out.inputs["Surface"])
    return T


ALL = prod + armed
ORIG = {o.name: [s.material for s in o.material_slots] for o in ALL}
TOON, TOONP1 = {}, {}
P1 = (1.0, 0.788, 0.25)          # game.ron P1 ring #FFC940 (the hero rim takes the player colour)
for o in ALL:
    for m in ORIG[o.name]:
        if m is not None and m.name not in TOON:
            TOON[m.name] = make_toon(m)
            TOONP1[m.name] = make_toon(m, P1, 1.0, name_suffix="_toonP1")


def use_material(kind):
    for o in ALL:
        for i, m in enumerate(ORIG[o.name]):
            if m is None:
                continue
            o.material_slots[i].material = {"toon": TOON, "toonP1": TOONP1}.get(kind, {}).get(m.name, m)


world = bpy.data.worlds.new("review")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
scene.world = world
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sun.data.angle = math.radians(1.0)
sun.rotation_euler = (-KEY_DIR).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(sun)
floor = bpy.data.objects.new("floor", bpy.data.meshes.new("floor"))
floor.data.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.11, 0.06, 0.035, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
floor.data.materials.append(fm)
scene.collection.objects.link(floor)
floor.hide_render = True


def cycles(bg_col=(0.16, 0.16, 0.18), samples=12, transparent=False):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 2
    scene.cycles.transparent_max_bounces = 8
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = transparent
    bg.inputs["Color"].default_value = (*bg_col, 1)
    bg.inputs["Strength"].default_value = 1.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


def show(objs, with_floor=False):
    for o in scene.objects:
        if o.type == "MESH":
            o.hide_render = o not in objs and not (with_floor and o is floor)


def render(name, res, res_y=None):
    for attempt in range(3):
        try:
            return render_still(scene, os.path.join(OUT, name), res, res_y)
        except RuntimeError as ex:              # device errors on a shared machine: retry
            log("render retry", name, ex)
    raise SystemExit("render failed: " + name)


VIEWS = {"front": 0, "front34L": 35, "front34R": -35, "sideL": 90, "back": 180, "back34R": 215, "back34L": 145, "sideR": 270}
size_turn = max(hi[0] - lo[0], H) * 1.06
centre = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))

def turnaround(objs, prefix, views, looks=("toon", "albedo", "clay"), res=900):
    show(objs)
    c_ = np.concatenate([wco(o) for o in objs])
    l_, h_ = c_.min(0), c_.max(0)
    ctr = Vector(((l_ + h_) / 2).tolist())
    size = max(h_[0] - l_[0], h_[2] - l_[2]) * 1.06
    for look in looks:
        if look in ("toon", "toonP1"):
            use_material(look)
            cycles()
        elif look == "albedo":
            use_material("orig")
            setup_workbench(scene, "TEXTURE", light="FLAT")
        else:
            use_material("orig")
            setup_workbench(scene, "SINGLE", cavity=True)
            scene.display.shading.single_color = (0.62, 0.58, 0.54)
        for name in views:
            aim_ortho(scene, ctr, az_dir(VIEWS[name], 4), size)
            render("%s%s_%s.png" % (prefix, look, name), res)


def closeups(objs, prefix, shots, res=700):
    show(objs)
    use_material("toon")
    cycles()
    for name, (tgt, d, sc) in shots.items():
        aim_ortho(scene, tgt, d, sc)
        render("%sclose_%s.png" % (prefix, name), res)


wmat = bpy.data.materials.new("wire_dark")
wmat.diffuse_color = (0.03, 0.03, 0.04, 1)
cmat = bpy.data.materials.new("clay_body")
cmat.diffuse_color = (0.72, 0.64, 0.58, 1)


def wireframes(shots):
    setup_workbench(scene, "OBJECT")
    for name, (objs, tgt, d, sc) in shots.items():
        for o in ALL:
            for s in o.material_slots:
                s.material = cmat
            o.color = (0.72, 0.64, 0.58, 1)
        show(objs)
        wires = add_wire_overlay(objs, thickness=0.0011 if sc < 0.7 else 0.0017)
        for w in wires:
            for s in w.material_slots:
                s.material = wmat
            w.color = (0.03, 0.03, 0.04, 1)
            w.hide_render = False
        aim_ortho(scene, tgt, d, sc)
        render("wire_%s.png" % name, 900)
        remove_objects(wires)
    use_material("orig")


def silhouette(objs, name):
    setup_workbench(scene, "SINGLE", light="FLAT")
    scene.display.shading.single_color = (1, 1, 1)
    scene.render.film_transparent = True
    show(objs)
    c = np.concatenate([wco(o) for o in objs])
    l_, h_ = c.min(0), c.max(0)
    w, h = h_[0] - l_[0], h_[2] - l_[2]
    aim_ortho(scene, Vector(((l_ + h_) / 2).tolist()), az_dir(0, 0), max(w, h))
    render(name, 1200 if w >= h else int(1200 * w / h), 1200 if h >= w else int(1200 * h / w))
    scene.render.film_transparent = False


def ingame(objs, prefix, looks=(("toon", 0), ("toonP1", 0), ("sil", 0), ("toon34", 35))):
    """True 1080p pixel scale, orthographic 55 deg, FixedVertical 22 m / 28 m, on a Cinder-Wastes-like floor."""
    root = bpy.data.objects.new("turn", None)
    scene.collection.objects.link(root)
    parents = {o: o.parent for o in objs}
    mats = {o: o.matrix_world.copy() for o in objs}
    movers = [o for o in objs if o.parent is None or o.parent not in objs]
    extra = [weapon_root] if weapon_root is not None and any(o in armed for o in objs) else []
    for o in [m for m in movers if m not in armed] + extra:
        mw = o.matrix_world.copy()
        o.parent = root
        o.matrix_world = mw
    game_dir = (0.0, -math.cos(math.radians(55.0)), math.sin(math.radians(55.0)))
    px = 256
    for vh in (22.0, 28.0):
        for look, yaw in looks:
            root.rotation_euler = Euler((0, 0, math.radians(yaw)))
            bpy.context.view_layer.update()
            if look == "sil":
                setup_workbench(scene, "SINGLE", light="FLAT", bg=(0.55, 0.5, 0.45))
                scene.display.shading.single_color = (0.02, 0.02, 0.02)
                show(objs)
            else:
                use_material("toonP1" if look == "toonP1" else "toon")
                cycles((0.02, 0.02, 0.02), samples=16)
                bg.inputs["Strength"].default_value = 0.35
                show(objs, with_floor=True)
            aim_ortho(scene, (0, 0, H * 0.5), game_dir, vh * px / 1080.0)
            render("%singame_%d_%s.png" % (prefix, int(vh), look), px)
    root.rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()
    for o in [m for m in movers if m not in armed] + extra:
        mw = o.matrix_world.copy()
        o.parent = parents.get(o)
        o.matrix_world = mw
    bpy.data.objects.remove(root)
    floor.hide_render = True


def px_tall(objs):
    c = np.concatenate([wco(o) for o in objs])
    g = np.array([0.0, -math.cos(math.radians(55.0)), math.sin(math.radians(55.0))])
    up = np.cross(np.cross(g, [0.0, 0.0, 1.0]), g)
    up /= np.linalg.norm(up)
    s = c @ up
    right = np.array([1.0, 0.0, 0.0])
    return {str(vh): {"tall_px": round(float(np.ptp(s)) * 1080 / vh, 1), "wide_px": round(float(np.ptp(c @ right)) * 1080 / vh, 1)} for vh in (22, 28)}


# =====================================================================================================================
if want("turn"):
    turnaround(prod, "", ("front", "front34L", "sideL", "back", "back34R", "sideR"))
if want("close"):
    closeups(prod, "", {"head_front": ((0, -0.03, 2.02), az_dir(0, 6), 0.5), "head_34": ((0, -0.03, 2.02), az_dir(35, 12), 0.5),
                        "head_side": ((0, 0.0, 2.02), az_dir(90, 6), 0.52), "crown_top": ((0, 0.0, 2.0), az_dir(20, 60), 0.62),
                        "torso_front": ((0, -0.1, 1.58), az_dir(0, 10), 0.75), "collar_34": ((0, -0.08, 1.74), az_dir(30, 15), 0.4),
                        "arm_34": ((0.45, 0.0, 1.72), az_dir(25, 35), 0.62), "hand_top": ((0.86, 0.0, 1.71), (0.0, -0.35, 1.0), 0.34),
                        "hips_34": ((0, -0.1, 1.2), az_dir(30, 12), 0.8), "legs_34": ((0.02, -0.05, 0.45), az_dir(30, 10), 0.95),
                        "boot_34": ((0.05, -0.08, 0.14), az_dir(40, 20), 0.45), "cape_back": ((0, 0.2, 1.1), az_dir(180, 8), 2.1),
                        "cape_34": ((0, 0.15, 1.1), az_dir(145, 10), 2.1), "cloth_front": ((0, -0.05, 0.95), az_dir(15, 5), 1.6)})
if want("wire"):
    by = lambda *names: [o for o in prod if o.name in names]  # noqa: E731
    wireframes({"body_front": ([body], (0, 0, 1.1), az_dir(0, 4), 2.3),
                "body_back": ([body], (0, 0, 1.1), az_dir(180, 4), 2.3),
                "shoulder": ([body], (0.2, 0.0, 1.7), az_dir(25, 20), 0.5),
                "elbow_forearm": ([body], (0.6, 0.0, 1.72), az_dir(15, -30), 0.55),
                "hand": ([body], (0.88, 0.0, 1.71), (0.0, -0.3, 1.0), 0.32),
                "hip_knee": ([body], (0.08, -0.02, 0.85), az_dir(25, 5), 1.1),
                "knee": ([body], (0.07, -0.02, 0.63), az_dir(20, 8), 0.4),
                "face": ([body], (0, -0.08, 1.93), az_dir(15, 5), 0.3),
                "hair_crown": (by("HAIR", "CROWN"), (0, 0.0, 2.03), az_dir(30, 15), 0.6),
                "collar_belt": (by("COLLAR", "BELT", "SHOULDERS"), (0, -0.05, 1.56), az_dir(30, 12), 0.9),
                "gauntlet": (by("GAUNTLETS"), (0.8, 0.0, 1.71), az_dir(30, 30), 0.45),
                "legs_plates": (by("GREAVES", "SABATONS"), (0.05, -0.05, 0.42), az_dir(30, 10), 0.95),
                "cloth": (by("CAPES", "MANTLES", "PANELS", "TABARD"), (0, 0.0, 1.05), az_dir(30, 8), 2.2),
                "cloth_back": (by("CAPES", "TABARD"), (0, 0.1, 1.05), az_dir(160, 8), 2.2)})
if want("sil"):
    silhouette(prod, "frontsil.png")
    if armed:
        silhouette(prod + armed, "armed_frontsil.png")
if want("ingame"):
    ingame(prod, "")
    metrics["ingame_px_bare_tpose"] = px_tall(prod)
    if armed:
        ingame(prod + armed, "armed_")
        metrics["ingame_px_armed_tpose"] = px_tall(prod + armed)
if want("armed") and armed:
    turnaround(prod + armed, "armed_", ("front", "front34R", "sideR", "back34L"), looks=("toon",))
    closeups(prod + armed, "armed_", {"launcher_34": ((-0.95, -0.05, 1.72), az_dir(-40, 20), 0.9),
                                      "launcher_top": ((-0.95, 0.0, 1.72), (0.0, -0.3, 1.0), 0.9),
                                      "upper_34": ((0, -0.1, 1.65), az_dir(-30, 15), 2.0)})

# UV layout as line segments (drawn by the sheet tool)
segs = []
for o in prod:
    me = o.data
    uvl = me.uv_layers.active.data
    for p in me.polygons:
        idx = list(p.loop_indices)
        for a, b in zip(idx, idx[1:] + idx[:1]):
            segs.append((*uvl[a].uv, *uvl[b].uv))
np.save(os.path.join(OUT, "uv_segments.npy"), np.array(segs, dtype=np.float32))
metrics["ingame"] = {"pitch_deg": 55.0, "view_heights_m": [22.0, 28.0], "screen_px": 1080, "renderer": "Cycles CPU emission toon"}
prev = json.load(open(os.path.join(OUT, "review_metrics.json"))) if os.path.isfile(os.path.join(OUT, "review_metrics.json")) else {}
prev.update(metrics)
write_json(os.path.join(OUT, "review_metrics.json"), prev)
if REPORT:
    write_json(REPORT, prev)
log("review renders written to", OUT)
