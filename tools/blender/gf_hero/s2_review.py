"""Stage 2 review renders of the production mesh (headless Blender; sheets are composed by
tools/comfy/stage2_sheets.py).

  blender -b -P tools/blender/gf_hero/s2_review.py -- <stage2.blend> <out_dir> [--ref <retopo_start.blend>]

Adapted from tools/blender/gf_hero/render_blockout.py (same camera conventions: hero faces -Y, azimuth 0 =
front, the in-game camera is orthographic at 55 deg pitch with FixedVertical 22 m / 28 m view heights and
true 1080p pixel size). GODFORGE stage-2 additions:
  * a toon review material (Diffuse -> Shader to RGB -> 3-band constant ramp x base colour + emissive,
    warm key / cool fill, rim) that approximates the in-game toon.wesl banding - the exported material
    stays the plain M_brax;
  * wireframe overlays of the joint topology on the body alone (shoulder, elbow end, hip, knee, neck,
    face) and on the parts;
  * the front silhouette for the IoU against the approved concept, and the UV layout as line data.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

from s2lib import (add_wire_overlay, aim_ortho, az_dir, get_co, log, opt, remove_objects, render_still,  # noqa: E402
                   script_args, setup_workbench, write_json)

argv = script_args(__doc__)
if len(argv) < 2:
    raise SystemExit(__doc__)
SRC, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
REF = opt(argv, "--ref", None, str)
ATTACH = opt(argv, "--attach", None, str)
ATTACH = os.path.abspath(ATTACH) if ATTACH else None
REF = os.path.abspath(REF) if REF else None
WEAPON = "--weapon" in argv
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=SRC)
scene = bpy.context.scene
prod = [o for o in scene.objects if o.type == "MESH" and not o.name.startswith(("REF", "WIRE"))]
armed = []
if ATTACH:
    with bpy.data.libraries.load(ATTACH, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("GAUNTLET_") and "FIST" not in n]
    for o in dst.objects:
        scene.collection.objects.link(o)
        armed.append(o)
if WEAPON:
    fists = [o for o in prod if "FIST" in o.name]
    opens = [o for o in prod if "FIST" not in o.name]
    body = None
else:
    body = bpy.data.objects["BODY"]
def wco(o):
    m = np.array(o.matrix_world)
    return get_co(o.data) @ m[:3, :3].T + m[:3, 3]


co = np.concatenate([wco(o) for o in (opens if WEAPON else prod)])
lo, hi = co.min(0), co.max(0)
H = hi[2] - lo[2]
metrics = {"source": os.path.basename(SRC), "bounds_m": {"min": lo.round(4).tolist(), "max": hi.round(4).tolist()},
           "height_m": round(float(H), 4), "span_m": round(float(hi[0] - lo[0]), 4)}
ref = None
if REF:
    with bpy.data.libraries.load(REF, link=False) as (src, dst):
        dst.objects = ["REF_blockout"]
    ref = dst.objects[0]
    scene.collection.objects.link(ref)
    ref.hide_render = True

# ---- toon review material (one per atlas material) ---------------------------------------------------------
def make_toon(M):
    T = M.copy()
    T.name = M.name + "_toon_review"
    nt = T.node_tree
    tex_b = [n for n in nt.nodes if n.type == "TEX_IMAGE" and "basecolor" in n.image.name][0]
    tex_e = [n for n in nt.nodes if n.type == "TEX_IMAGE" and "emissive" in n.image.name][0]
    tex_n = ([n for n in nt.nodes if n.type == "TEX_IMAGE" and "normal" in n.image.name] or [None])[0]
    for n in list(nt.nodes):
        if n not in (tex_b, tex_e, tex_n):
            nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
    dif.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.34, 0.30, 0.36, 1)      # cool shadow band
    els[1].position, els[1].color = 0.18, (0.68, 0.64, 0.64, 1)
    e3 = els.new(0.55)
    e3.color = (1.0, 0.97, 0.92, 1)
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.25
    rimr = nt.nodes.new("ShaderNodeValToRGB")
    rimr.color_ramp.interpolation = "CONSTANT"
    rimr.color_ramp.elements[0].position = 0.0
    rimr.color_ramp.elements[0].color = (0, 0, 0, 1)
    rimr.color_ramp.elements[1].position = 0.72
    rimr.color_ramp.elements[1].color = (0.35, 0.22, 0.12, 1)
    add1 = nt.nodes.new("ShaderNodeMix")
    add1.data_type = "RGBA"
    add1.blend_type = "ADD"
    add1.inputs["Factor"].default_value = 1.0
    add2 = nt.nodes.new("ShaderNodeMix")
    add2.data_type = "RGBA"
    add2.blend_type = "ADD"
    add2.inputs["Factor"].default_value = 1.0
    emm = nt.nodes.new("ShaderNodeMix")
    emm.data_type = "RGBA"
    emm.blend_type = "MULTIPLY"
    emm.inputs["Factor"].default_value = 1.0
    emm.inputs["B"].default_value = (2.2, 2.2, 2.2, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    L = nt.links.new
    if tex_n is not None:        # the tangent-space normal map drives the toon bands, as in the game
        nmn = nt.nodes.new("ShaderNodeNormalMap")
        nmn.space = "TANGENT"
        nmn.uv_map = "UVMap"
        L(tex_n.outputs["Color"], nmn.inputs["Color"])
        L(nmn.outputs["Normal"], dif.inputs["Normal"])
        L(nmn.outputs["Normal"], lw.inputs["Normal"])
    L(dif.outputs[0], s2r.inputs[0])
    L(s2r.outputs["Color"], bw.inputs[0])
    L(bw.outputs[0], ramp.inputs["Fac"])
    L(ramp.outputs["Color"], mul.inputs["A"])
    L(tex_b.outputs["Color"], mul.inputs["B"])
    L(lw.outputs["Facing"], rimr.inputs["Fac"])
    L(mul.outputs["Result"], add1.inputs["A"])
    L(rimr.outputs["Color"], add1.inputs["B"])
    L(tex_e.outputs["Color"], emm.inputs["A"])
    L(add1.outputs["Result"], add2.inputs["A"])
    L(emm.outputs["Result"], add2.inputs["B"])
    L(add2.outputs["Result"], em.inputs["Color"])
    L(em.outputs[0], out.inputs["Surface"])
    return T


ALL = prod + armed
ORIG = {o.name: o.data.materials[0] for o in ALL}
TOON = {}
for o in ALL:
    M = ORIG[o.name]
    if M.name not in TOON:
        TOON[M.name] = make_toon(M)


def use_material(kind):
    for o in ALL:
        o.data.materials[0] = TOON[ORIG[o.name].name] if kind == "toon" else ORIG[o.name]


world = bpy.data.worlds.new("review")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
bg.inputs["Strength"].default_value = 0.0
scene.world = world


def sun(name, energy, rot, color):
    ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
    ob.data.energy = energy
    ob.data.color = color
    ob.rotation_euler = tuple(math.radians(a) for a in rot)
    scene.collection.objects.link(ob)
    return ob


key = sun("key", 4.0, (45, 0, -35), (1.0, 0.93, 0.85))
fill = sun("fill", 1.2, (70, 0, 150), (0.75, 0.82, 1.0))


def eevee(bg_col=(0.16, 0.16, 0.18)):
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    bg.inputs["Color"].default_value = (*bg_col, 1)
    bg.inputs["Strength"].default_value = 1.0
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


VIEWS = {"front": 0, "front34L": 35, "sideL": 90, "back": 180, "back34R": 215, "sideR": 270}
size_turn = max(hi[0] - lo[0], H) * 1.06
centre = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2))


def show(objs):
    for o in scene.objects:
        if o.type == "MESH":
            o.hide_render = o not in objs


wmat = bpy.data.materials.new("wire_dark")
wmat.diffuse_color = (0.03, 0.03, 0.04, 1)
cmat = bpy.data.materials.new("clay_body")
cmat.diffuse_color = (0.72, 0.64, 0.58, 1)
floor = bpy.data.objects.new("floor", bpy.data.meshes.new("floor"))
floor.data.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.17, 0.07, 0.03, 1)
floor.data.materials.append(fm)
scene.collection.objects.link(floor)
floor.hide_render = True


def turnaround(objs, prefix, views, looks=("toon", "albedo", "clay")):
    show(objs)
    for look in looks:
        if look == "toon":
            use_material("toon")
            eevee()
        elif look == "albedo":
            use_material("orig")
            setup_workbench(scene, "TEXTURE", light="FLAT")
        else:
            use_material("orig")
            setup_workbench(scene, "SINGLE", cavity=True)
            scene.display.shading.single_color = (0.62, 0.58, 0.54)
        for name in views:
            aim_ortho(scene, centre, az_dir(VIEWS[name], 4), size_turn)
            render_still(scene, os.path.join(OUT, "%s%s_%s.png" % (prefix, look, name)), 900)


def closeups(objs, prefix, shots):
    show(objs)
    use_material("toon")
    eevee()
    for name, (tgt, d, sc) in shots.items():
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "%sclose_%s.png" % (prefix, name)), 700)


def wireframes(shots, prefix=""):
    setup_workbench(scene, "OBJECT")
    for name, (objs, tgt, d, sc) in shots.items():
        for o in ALL:
            o.data.materials[0] = cmat
            o.color = (0.72, 0.64, 0.58, 1)
        show(objs)
        wires = add_wire_overlay(objs, thickness=0.0012 if sc < 0.7 else 0.0018)
        for w in wires:
            w.data.materials[0] = wmat
            w.color = (0.03, 0.03, 0.04, 1)
            w.hide_render = False
        aim_ortho(scene, tgt, d, sc)
        render_still(scene, os.path.join(OUT, "%swire_%s.png" % (prefix, name)), 900)
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
    render_still(scene, os.path.join(OUT, name), 1200 if w >= h else int(1200 * w / h), 1200 if h >= w else int(1200 * h / w))
    scene.render.film_transparent = False


def ingame(objs, prefix, looks=(("toon", 0), ("sil", 0), ("toon34", 35))):
    """True 1080p pixel scale, orthographic 55 deg, FixedVertical 22 m / 28 m, on a lit Cinder-Wastes-like floor."""
    root = bpy.data.objects.new("turn", None)
    scene.collection.objects.link(root)
    parents = {o: o.parent for o in objs}
    mats = {o: o.matrix_world.copy() for o in objs}
    for o in objs:
        o.parent = root
        o.matrix_world = mats[o]
    show(objs)
    PITCH = 55.0
    game_dir = (0.0, -math.cos(math.radians(PITCH)), math.sin(math.radians(PITCH)))
    px = 256
    for vh in (22.0, 28.0):
        for look, yaw in looks:
            root.rotation_euler = Euler((0, 0, math.radians(yaw)))
            bpy.context.view_layer.update()
            if look == "sil":
                setup_workbench(scene, "SINGLE", light="FLAT", bg=(0.55, 0.5, 0.45))
                scene.display.shading.single_color = (0.02, 0.02, 0.02)
                floor.hide_render = True
            else:
                use_material("toon")
                eevee((0.02, 0.02, 0.02))
                floor.hide_render = False
                key.rotation_euler = (math.radians(40), 0, math.radians(-30))
            aim_ortho(scene, (0, 0, H * 0.5), game_dir, vh * px / 1080.0)
            render_still(scene, os.path.join(OUT, "%singame_%d_%s.png" % (prefix, int(vh), look)), px)
    root.rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()
    for o in objs:
        o.parent = parents[o]
        o.matrix_world = mats[o]
    bpy.data.objects.remove(root)
    floor.hide_render = True
    key.rotation_euler = (math.radians(45), 0, math.radians(-35))


def axes_gizmo(obj, length=0.2, r=0.007):
    """Three arrows at the object's origin along its local X (red), Y (green), Z (blue)."""
    import bmesh
    out = []
    for i, col in enumerate(((0.9, 0.1, 0.1, 1), (0.1, 0.8, 0.1, 1), (0.15, 0.35, 1.0, 1))):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r, radius2=r, depth=length * 0.8)
        for v in bm.verts:
            v.co.z += length * 0.4
        g = bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=r * 2.5, radius2=0.0, depth=length * 0.2)
        for v in g["verts"]:
            v.co.z += length * 0.9
        me = bpy.data.meshes.new("axis%d" % i)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("GIZMO_%s_%d" % (obj.name, i), me)
        rot = {0: Euler((0, math.radians(90), 0)), 1: Euler((math.radians(-90), 0, 0)), 2: Euler((0, 0, 0))}[i]
        ob.matrix_world = obj.matrix_world @ rot.to_matrix().to_4x4()
        ob.color = col
        m = bpy.data.materials.new("gz%d" % i)
        m.diffuse_color = col
        me.materials.append(m)
        scene.collection.objects.link(ob)
        out.append(ob)
    return out


if WEAPON:
    gl = [o for o in opens if o.name.endswith("_L")][0]
    fl = [o for o in fists if o.name.endswith("_L")][0]
    ctr_l = Vector(wco(gl).mean(0).tolist())
    ctr_f = Vector(wco(fl).mean(0).tolist())
    size_g = float(np.ptp(wco(gl), axis=0).max()) * 1.15
    closeups(opens, "w_", {"open_front": (ctr_l, az_dir(0, 5), size_g), "open_top": (ctr_l, (0.0, -0.3, 1.0), size_g),
                           "open_34": (ctr_l, az_dir(40, 25), size_g), "open_back34": (ctr_l, az_dir(200, 20), size_g),
                           "open_under": (ctr_l, (0.2, -0.3, -1.0), size_g), "pair_front": (centre, az_dir(0, 10), size_turn)})
    closeups(fists, "w_", {"fist_front": (ctr_f, az_dir(0, 5), size_g), "fist_34": (ctr_f, az_dir(40, 25), size_g),
                           "fist_knuckles": (ctr_f + Vector((0.2, 0, 0)), az_dir(90, 10), size_g * 0.8), "fist_top": (ctr_f, (0.0, -0.3, 1.0), size_g)})
    wireframes({"open": ([gl], ctr_l, az_dir(40, 25), size_g), "fist": ([fl], ctr_f, az_dir(40, 25), size_g),
                "open_under": ([gl], ctr_l, (0.2, -0.3, -1.0), size_g)}, prefix="w_")
    gz = axes_gizmo(gl) + axes_gizmo(fl)
    setup_workbench(scene, "OBJECT")
    for o in (gl, fl):
        o.data.materials[0] = cmat
        o.color = (0.6, 0.56, 0.52, 1)
    scene.display.shading.show_xray = True          # the socket origin sits inside the hand block
    scene.display.shading.xray_alpha = 0.15
    show([gl] + gz[:3])
    aim_ortho(scene, ctr_l, az_dir(40, 25), size_g)
    render_still(scene, os.path.join(OUT, "w_frame_open.png"), 900)
    show([fl] + gz[3:])
    aim_ortho(scene, ctr_f, az_dir(40, 25), size_g)
    render_still(scene, os.path.join(OUT, "w_frame_fist.png"), 900)
    scene.display.shading.show_xray = False
    remove_objects(gz)
    use_material("orig")
    uv_objs = opens
else:
    turnaround(prod, "", ("front", "front34L", "sideL", "back", "back34R", "sideR"))
    closeups(prod, "", {"head_front": ((0, -0.02, 2.02), az_dir(0, 6), 0.42), "head_34": ((0, -0.02, 2.02), az_dir(35, 10), 0.42),
                        "head_side": ((0, 0.0, 2.02), az_dir(90, 6), 0.42), "torso_front": ((0, -0.05, 1.62), az_dir(0, 8), 0.95),
                        "arm_34": ((0.75, 0.03, 1.75), az_dir(30, 30), 0.85), "hand_34": ((1.04, 0.0, 1.74), az_dir(50, 35), 0.4),
                        "skirt_34": ((0, 0, 1.05), az_dir(35, 15), 0.95), "skirt_back": ((0, 0, 1.05), az_dir(180, 10), 0.95),
                        "legs_34": ((0.3, 0, 0.35), az_dir(30, 10), 0.8)})
    wireframes({"body_front": ([body], (0, 0, 1.1), az_dir(0, 4), size_turn),
                "body_back": ([body], (0, 0, 1.1), az_dir(180, 4), size_turn),
                "shoulder": ([body], (0.3, -0.02, 1.78), az_dir(25, 20), 0.62),
                "elbow_forearm": ([body], (0.7, 0.03, 1.74), az_dir(15, -30), 0.7),
                "hand": ([body], (1.04, 0.03, 1.74), (0.0, -0.3, 1.0), 0.36),
                "hip_knee": ([body], (0.2, -0.02, 0.8), az_dir(25, 5), 1.0),
                "knee": ([body], (0.28, -0.03, 0.6), az_dir(20, 8), 0.45),
                "neck_face": ([body], (0, -0.03, 1.98), az_dir(30, 8), 0.45),
                "face": ([body], (0, -0.06, 2.03), az_dir(15, 5), 0.24),
                "skirt": ([o for o in prod if o.name.startswith(("SKIRT", "BELT", "SASH"))], (0, 0, 1.05), az_dir(35, 15), 1.0),
                "head_parts": ([o for o in prod if o.name in ("HAIR", "BEARD", "BODY")], (0, -0.02, 2.02), az_dir(35, 10), 0.42),
                "legs_parts": ([o for o in prod if o.name in ("WRAPS", "BODY")], (0.3, 0, 0.3), az_dir(30, 10), 0.7)})
    silhouette(prod, "frontsil.png")
    ingame(prod, "")
    if armed:
        turnaround(prod + armed, "armed_", ("front", "front34L", "sideL", "back"), looks=("toon",))
        closeups(prod + armed, "armed_", {"gauntlet_34": ((0.95, 0.04, 1.75), az_dir(40, 25), 0.9),
                                          "gauntlet_top": ((0.95, 0.04, 1.75), (0.0, -0.3, 1.0), 0.9),
                                          "upper_34": ((0, -0.02, 1.7), az_dir(30, 15), 1.5)})
        silhouette(prod + armed, "armed_frontsil.png")
        ingame(prod + armed, "armed_")
    uv_objs = prod
metrics["ingame"] = {"pitch_deg": 55.0, "view_heights_m": [22.0, 28.0], "screen_px": 1080}

# UV layout as line segments (drawn by the sheet tool)
segs = []
for o in uv_objs:
    me = o.data
    uvl = me.uv_layers.active.data
    for p in me.polygons:
        idx = list(p.loop_indices)
        for a, b in zip(idx, idx[1:] + idx[:1]):
            segs.append((*uvl[a].uv, *uvl[b].uv))
np.save(os.path.join(OUT, "uv_segments.npy"), np.array(segs, dtype=np.float32))
write_json(os.path.join(OUT, "review_metrics.json"), metrics)
log("review renders written to", OUT)
