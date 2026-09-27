"""Selene's review-render helpers for stages 3 and 4 (headless Blender; never EEVEE, the GPU is shared).

The toon look is s2_selene_review.py's (a copy of its make_toon, which stays unchanged): a Cycles-CPU EMISSION shader that
computes its own lighting (key + fill N.L through the tangent normal map -> constant bands x base colour, a cool lifted
shadow band, a rim, + emissive), so a few samples give a clean frame. Cameras are orthographic; the in-game view is the
client's 55 degree pitch at true 1080p pixel size (FixedVertical 22 m).
"""
import math
import os

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from s2lib import aim_ortho, render_still

KEY_DIR = Vector((-0.45, -0.55, 0.70)).normalized()
FILL_DIR = Vector((0.6, 0.45, 0.35)).normalized()
GAME_DIR = Vector((0.0, -math.cos(math.radians(55.0)), math.sin(math.radians(55.0))))


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
    if tb is None:
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
    els[0].position, els[0].color = 0.0, (0.40, 0.37, 0.46, 1)
    els[1].position, els[1].color = 0.22, (0.70, 0.67, 0.68, 1)
    e3 = els.new(0.55)
    e3.color = (1.0, 0.96, 0.9, 1)
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


def toon_all(objs):
    """Swap every material of objs for its toon copy (in place, the file is never saved by a review script)."""
    done = {}
    for o in objs:
        for s in o.material_slots:
            m = s.material
            if m is None:
                continue
            if m.name not in done:
                done[m.name] = make_toon(m)
            s.material = done[m.name]
    return done


def setup(scene, bg=(0.16, 0.16, 0.18), samples=8):
    world = bpy.data.worlds.new("review")
    world.use_nodes = True
    b = world.node_tree.nodes["Background"]
    b.inputs["Color"].default_value = (*bg, 1)
    b.inputs["Strength"].default_value = 1.0
    scene.world = world
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.cycles.transparent_max_bounces = 8
    scene.cycles.use_adaptive_sampling = False
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    return world


def ground(scene, col=(0.12, 0.10, 0.09), size=6.0):
    me = bpy.data.meshes.new("review_floor")
    me.from_pydata([(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("review_floor", me)
    m = bpy.data.materials.new("review_floor")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*col, 1)
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    me.materials.append(m)
    scene.collection.objects.link(ob)
    return ob


def az_dir(az_deg, elev_deg=0.0):
    a, e = math.radians(az_deg), math.radians(elev_deg)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def shoot(scene, path, target, direction, scale, res_x, res_y=None):
    aim_ortho(scene, target, direction, scale)
    for attempt in range(3):
        try:
            return render_still(scene, path, res_x, res_y)
        except RuntimeError as ex:
            print("render retry", path, ex)
    raise SystemExit("render failed: " + path)


def ingame(scene, path, target_z=1.1, view_h=22.0, px=200):
    """The client's camera: orthographic, 55 deg pitch, FixedVertical view_h metres on a 1080 px screen, px square crop."""
    return shoot(scene, path, Vector((0.0, 0.0, target_z)), GAME_DIR, view_h * px / 1080.0, px, px)


def project(scene, pts):
    """World points -> pixel coordinates (x right, y down) of the current camera and resolution."""
    cam = scene.camera
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    out = []
    for p in pts:
        c = world_to_camera_view(scene, cam, Vector(p))
        out.append((round(c.x * rx, 1), round((1.0 - c.y) * ry, 1)))
    return out


def ensure(path):
    os.makedirs(path, exist_ok=True)
    return path
