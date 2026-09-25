"""Stage 2 review renders for Valdris (headless Blender; the sheets are composed by s2_valdris_sheets.py).

  blender -b -P tools/blender/gf_hero/s2_valdris_review.py -- <valdris_stage2.blend> <out_dir> --ref <retopo_start.blend>
          --cannon <colossus_cannon.glb> --fit <body_fit.json> [--report <review.json>] [--only <group,...>]

Same camera conventions as s2_review.py (Brax): the hero faces -Y, azimuth 0 = front, the in-game camera is
orthographic at 55 deg pitch with FixedVertical 22 m / 28 m view heights and true 1080p pixel size. Differences:
  * the GPU is shared, so nothing renders with EEVEE: the toon review is a Cycles-CPU EMISSION shader that computes
    the lighting itself (key + fill N.L through the tangent normal map -> constant bands -> x base colour, cool
    shadow band, rim, + emissive), so it is noise-free at 8-16 samples; the floor is a diffuse plane under a sun, so
    the hero still casts a shadow; clay / albedo / wire / silhouettes are Workbench;
  * two rims: "toon" has a subtle neutral rim (judges the model), "toonP1" adds the client's hero rim in the P1
    colour (crates/gf_client/src/materials.rs ToonStyle::hero: rim width 0.42, strength 1; shaders/toon.wesl);
  * the signature weapon is the colossus_cannon GLB (the weapon track's file), attached with an identity transform
    at the recorded right-hand frame (body_fit.json hand_frames.R); the sleeve fit is measured (penetration of the
    right forearm, gauntlet and hand into the sleeve's free radius) and shown in a cutaway;
  * "pose45": a REVIEW-ONLY pose (not a rig) with both arms swung 45 deg forward about the shoulder joints, the
    blockout's own pose, so the in-game column compares like with like.
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
CANNON = opt(argv, "--cannon", None, str)
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

# ---- the cannon on the right-hand frame -----------------------------------------------------------------------
armed = []
cannon_root = None
M_R = None
if CANNON and fit:
    before = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.abspath(CANNON))
    new = [o for o in scene.objects if o not in before]
    cannon_root = [o for o in new if o.parent is None][0]
    fr = fit["hand_frames"]["R"]
    M_R = Matrix.Identity(4)
    for i, a in enumerate(("x_axis", "y_axis", "z_axis")):
        for r in range(3):
            M_R[r][i] = fr[a][r]
    for r in range(3):
        M_R[r][3] = fr["origin"][r]
    cannon_root.matrix_world = M_R
    bpy.context.view_layer.update()
    armed = [o for o in new if o.type == "MESH"]
    metrics["cannon"] = {"glb": os.path.basename(CANNON), "attached_at": "hand_frames.R (identity)", "frame": fr}

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

# ---- review pose: arms 45 deg forward (the blockout's pose), review only ------------------------------------------
SHOULDER = {1: Vector((0.37, 0.0, 1.78)), -1: Vector((-0.37, 0.0, 1.78))}
POSE_OBJS = [o for o in prod if o.name in ("BODY", "ARMS", "GAUNTLETS")]
_saved = {o.name: get_co(o.data).copy() for o in POSE_OBJS}


def set_pose(deg):
    for o in POSE_OBJS:
        c = _saved[o.name].copy()
        if deg:
            for sd in (1, -1):
                a = math.radians(-deg * sd)
                R = np.array(Matrix.Rotation(a, 3, "Z"))
                sh = np.array(SHOULDER[sd])
                ax = c[:, 0] * sd
                if o.name == "BODY":
                    w = np.clip((ax - 0.3) / 0.12, 0, 1) * (c[:, 2] > 1.45)
                    w = w * w * (3 - 2 * w)
                else:
                    w = (ax > 0.3).astype(np.float64)
                rot = (c - sh) @ R.T + sh
                c = c + (rot - c) * w[:, None]
        o.data.vertices.foreach_set("co", c.ravel())
        o.data.update()
    if cannon_root is not None:
        cannon_root.matrix_world = (Matrix.Translation(SHOULDER[-1]) @ Matrix.Rotation(math.radians(deg), 4, "Z")
                                    @ Matrix.Translation(-SHOULDER[-1]) @ M_R) if deg else M_R
    bpy.context.view_layer.update()


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
    extra = [cannon_root] if cannon_root is not None and any(o in armed for o in objs) else []
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


# ---- sleeve fit: the right forearm, gauntlet and hand inside the colossus_cannon ------------------------------------
if armed and M_R is not None and want("fit"):
    Minv = np.array(M_R.inverted())
    rows = []
    for o in prod:
        if o.name not in ("BODY", "ARMS", "GAUNTLETS"):
            continue
        c = wco(o)
        c = c[c[:, 0] < -0.5]
        loc = c @ Minv[:3, :3].T + Minv[:3, 3]
        y = loc[:, 1]
        r = np.hypot(loc[:, 0], loc[:, 2])
        free = np.where(y < -0.30, 0.0944, np.where(y <= 0.06, 0.0983, 0.181))
        inside = (y > -0.345) & (y < 0.40)
        bar = (np.abs(y) < 0.021) & (np.abs(loc[:, 0]) < 0.021)
        pen = np.where(inside & ~bar, r - free, -1.0)
        # the sleeve's rear cuff hoop (inner 0.096, outer 0.172, y -0.353 .. -0.313) vs the couter / vambrace
        hoop = (y > -0.353) & (y < -0.313) & (r > 0.096) & (r < 0.172)
        rows.append({"object": o.name, "verts_in_cannon_span": int(inside.sum()),
                     "penetrating_verts": int((pen > 0).sum()), "max_penetration_m": round(float(max(pen.max(), 0.0)), 4),
                     "min_clearance_m": round(float(-pen[inside & ~bar].max()) if (inside & ~bar).any() else 0.0, 4),
                     "verts_in_rear_cuff_hoop": int(hoop.sum())})
    metrics["sleeve_fit"] = {"free_radius_m": {"rear_cuff_y<-0.30": 0.0944, "sleeve": 0.0983, "drum_y>0.06": 0.181},
                             "note": "grip frame of the cannon (y = barrel); the inner handle bar (|y|, |x| < 0.021) is the grip itself and not counted",
                             "objects": rows}
    log("sleeve fit", rows)

# =====================================================================================================================
if want("turn"):
    turnaround(prod, "", ("front", "front34L", "sideL", "back", "back34R", "sideR"))
if want("close"):
    closeups(prod, "", {"head_front": ((0, -0.12, 2.12), az_dir(0, 6), 0.46), "head_34": ((0, -0.12, 2.12), az_dir(35, 12), 0.46),
                        "torso_front": ((0, -0.3, 1.72), az_dir(0, 10), 1.0),
                        "anvil_34": ((0, -0.4, 1.6), az_dir(40, 25), 0.9), "pauldron_34": ((0.45, 0, 2.02), az_dir(35, 25), 0.85),
                        "arm_34": ((0.72, 0.0, 1.78), az_dir(30, 30), 0.8), "hand_top": ((1.0, 0.0, 1.78), (0.0, -0.35, 1.0), 0.36),
                        "hips_34": ((0, -0.2, 1.0), az_dir(35, 12), 1.0), "legs_34": ((0.28, -0.05, 0.45), az_dir(30, 10), 1.0),
                        "boot_34": ((0.29, -0.1, 0.14), az_dir(40, 20), 0.6), "cape_back": ((0, 0.3, 1.2), az_dir(180, 8), 2.2),
                        "cape_34": ((0, 0.25, 1.2), az_dir(150, 10), 2.2)})
    # the head in profile: the pauldron would hide it, so it is left out of this one shot
    closeups([o for o in prod if o.name != "PAULDRONS"], "", {"head_side": ((0, -0.08, 2.12), az_dir(90, 6), 0.5)})
if want("wire"):
    wireframes({"body_front": ([body], (0, 0, 1.15), az_dir(0, 4), size_turn),
                "body_back": ([body], (0, 0, 1.15), az_dir(180, 4), size_turn),
                "shoulder": ([body], (0.36, 0.0, 1.85), az_dir(25, 20), 0.6),
                "elbow_forearm": ([body], (0.7, 0.0, 1.78), az_dir(15, -30), 0.7),
                "hand": ([body], (1.02, 0.0, 1.78), (0.0, -0.3, 1.0), 0.36),
                "hip_knee": ([body], (0.22, -0.02, 0.85), az_dir(25, 5), 1.2),
                "knee": ([body], (0.26, -0.03, 0.62), az_dir(20, 8), 0.5),
                "neck_face": ([body], (0, -0.1, 2.12), az_dir(30, 8), 0.5),
                "face": ([body], (0, -0.14, 2.17), az_dir(15, 5), 0.28),
                "pauldron": ([o for o in prod if o.name == "PAULDRONS"], (0.45, 0, 2.05), az_dir(35, 25), 0.9),
                "anvil_torso": ([o for o in prod if o.name in ("ANVIL", "CUIRASS")], (0, -0.2, 1.6), az_dir(35, 15), 1.2),
                "arm_plates": ([o for o in prod if o.name in ("ARMS", "GAUNTLETS")], (0.75, 0, 1.78), az_dir(30, 30), 0.85),
                "legs_plates": ([o for o in prod if o.name in ("LEGS", "SABATONS", "HIPS")], (0.28, -0.05, 0.55), az_dir(30, 10), 1.3),
                "beard": ([o for o in prod if o.name in ("BEARD", "BODY")], (0, -0.18, 2.03), az_dir(30, 8), 0.5),
                "cape": ([o for o in prod if o.name in ("CAPE", "LOINCLOTH")], (0, 0.2, 1.2), az_dir(150, 10), 2.3)})
if want("sil"):
    silhouette(prod, "frontsil.png")
    if armed:
        silhouette(prod + armed, "armed_frontsil.png")
        set_pose(45)
        silhouette(prod + armed, "pose45_armed_frontsil.png")
        set_pose(0)
if want("ingame"):
    ingame(prod, "")
    metrics["ingame_px_bare_tpose"] = px_tall(prod)
    if armed:
        ingame(prod + armed, "armed_")
        metrics["ingame_px_armed_tpose"] = px_tall(prod + armed)
        set_pose(45)
        ingame(prod + armed, "pose45_armed_")
        metrics["ingame_px_armed_pose45"] = px_tall(prod + armed)
        set_pose(0)
if want("armed") and armed:
    turnaround(prod + armed, "armed_", ("front", "front34R", "sideR", "back34L"), looks=("toon",))
    closeups(prod + armed, "armed_", {"cannon_34": ((-1.15, -0.05, 1.8), az_dir(-40, 20), 1.4),
                                      "cannon_top": ((-1.15, 0.0, 1.8), (0.0, -0.3, 1.0), 1.4),
                                      "upper_34": ((0, -0.1, 1.75), az_dir(-30, 15), 2.0)})
    set_pose(45)
    turnaround(prod + armed, "pose45_armed_", ("front", "front34R", "front34L"), looks=("toon",))
    set_pose(0)
    # section: the cannon cut along its axis plane (the grip frame's X-Y plane, the upper half removed), so the right
    # forearm, the vambrace, the wrist cuff and the hand show lying in the sleeve; seen from above and at 3/4
    zc = np.array(M_R.col[2][:3])
    oc = np.array(M_R.col[3][:3])
    cut = []
    for o in armed:
        c2 = o.copy()
        c2.data = o.data.copy()
        c2.parent = None
        c2.matrix_world = o.matrix_world.copy()
        scene.collection.objects.link(c2)
        Mi = np.array(c2.matrix_world.inverted())
        bm = bmesh.new()
        bm.from_mesh(c2.data)
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=tuple(Mi[:3, :3] @ oc + Mi[:3, 3]),
                               plane_no=tuple(Mi[:3, :3] @ zc), clear_outer=True)
        bm.to_mesh(c2.data)
        bm.free()
        for i, s_ in enumerate(c2.material_slots):
            s_.material = TOON[ORIG[o.name][i].name]
        cut.append(c2)
    use_material("toon")
    cycles()
    show(prod + cut)
    for name, d in (("section_top", (0.0, -0.02, 1.0)), ("section_34", az_dir(-30, 50)), ("section_front", az_dir(0, 35))):
        aim_ortho(scene, Vector((-1.05, 0.0, 1.78)), d, 1.3)
        render("armed_%s.png" % name, 900)
    for c2 in cut:
        bpy.data.objects.remove(c2)
    use_material("orig")

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
