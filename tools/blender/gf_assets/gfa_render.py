"""gf_assets review renders (headless Blender 5.2; Cycles on the CPU or Workbench, never EEVEE).

  * toon preview: every mesh gets an emission-only Cycles material that imitates the engine's look
    (crates/gf_client/src/shaders/toon.wesl): the base-colour texture under a posterised warm key
    light from the game's key direction, a cool fill, a warm rim, the emissive texture on top, and an
    inverted-hull ink outline (the backfacing trick, so Cycles needs no backface culling). No lamps,
    so renders take seconds and have no sampling noise;
  * turnaround(): the asset from several directions at ONE shared scale;
  * silhouette(): flat black on a light ground (Workbench), optionally at in-game pixel size;
  * ingame(): the game camera (orthographic, 55 deg pitch, yaw 0, FixedVertical view height, true
    1080p pixel size) with a 2.2 m hero mannequin holding the weapon / standing next to the enemy;
  * contact_sheet(): writes a JSON layout and calls gfa_sheet.py with ComfyUI's python (PIL).

The in-game camera and the 1080p pixel scale follow tools/blender/gf_hero/render_blockout.py
(adapted from Ashen Covenant tools/trellis/render_glb.py).
"""
import math
import os
from contextlib import contextmanager

import bmesh
import bpy
from mathutils import Matrix, Vector

import gfa_common as C
import gfa_model as M
import gfa_spec as SPEC

KEY_DIR = Vector(SPEC.KEY_LIGHT_FROM).normalized()
FILL_DIR = Vector(SPEC.FILL_LIGHT_FROM).normalized()
BG_REVIEW = "#34303A"
BG_SIL = "#C9C2B6"
FLOOR = "#3A2C24"           # Cinder Wastes flagstone mid-tone (value check against the real ground)
MANNEQUIN = "#7A8494"

# views: name -> camera direction FROM the asset (asset space)
WEAPON_VIEWS = {
    "side_R": (1.0, 0.0, 0.08), "34_front": (0.75, 0.55, 0.38), "top": (0.0, 0.0001, 1.0),
    "side_L": (-1.0, 0.0, 0.08), "front": (0.0, 1.0, 0.1), "34_back": (-0.7, -0.6, 0.4),
}
CREATURE_VIEWS = {
    "front": (0.0, -1.0, 0.12), "34_front": (0.7, -0.7, 0.3), "side": (1.0, 0.0, 0.1),
    "back": (0.0, 1.0, 0.12), "34_back": (-0.7, 0.7, 0.3), "top": (0.0, -0.0001, 1.0),
}


# ---- materials -------------------------------------------------------------------------------------

def _tex_of(mat, socket):
    """Image feeding a Principled BSDF input (None when absent)."""
    if mat is None:
        return None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            for l in n.inputs[socket].links:
                if l.from_node.type == "TEX_IMAGE":
                    return l.from_node.image
    return None


def toon_material(name, base_img=None, emis_img=None, flat_hex=None, rim=0.35, emis_gain=1.6):
    """Emission-only Cycles material imitating the engine's toon ramp (see module doc)."""
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    out = N("ShaderNodeOutputMaterial")
    em = N("ShaderNodeEmission")
    L(em.outputs["Emission"], out.inputs["Surface"])
    if base_img is not None:
        tb = N("ShaderNodeTexImage")
        tb.image = base_img
        tb.interpolation = "Linear"
        base = tb.outputs["Color"]
    else:
        rgb = N("ShaderNodeRGB")
        rgb.outputs[0].default_value = C.hex_linear(flat_hex or MANNEQUIN)
        base = rgb.outputs[0]
    geo = N("ShaderNodeNewGeometry")

    def dot(vec_out, d):
        vm = N("ShaderNodeVectorMath")
        vm.operation = "DOT_PRODUCT"
        L(vec_out, vm.inputs[0])
        vm.inputs[1].default_value = tuple(d)
        return vm.outputs["Value"]

    def ramp(value, stops, interp="EASE"):
        cr = N("ShaderNodeValToRGB")
        cr.color_ramp.interpolation = interp
        els = cr.color_ramp.elements
        while len(els) > 1:
            els.remove(els[-1])
        els[0].position, els[0].color = stops[0][0], (stops[0][1],) * 3 + (1,)
        for pos, v in stops[1:]:
            e = els.new(pos)
            e.color = (v, v, v, 1)
        L(value, cr.inputs["Fac"])
        return cr.outputs["Color"]

    # remap N.L from -1..1 to 0..1 for the ramp
    def remap(v):
        m = N("ShaderNodeMath")
        m.operation = "MULTIPLY_ADD"
        L(v, m.inputs[0])
        m.inputs[1].default_value = 0.5
        m.inputs[2].default_value = 0.5
        return m.outputs[0]

    key = ramp(remap(dot(geo.outputs["Normal"], KEY_DIR)), [(0.0, 0.0), (0.44, 0.0), (0.47, 0.55), (0.62, 0.55), (0.65, 1.0)])
    fill = ramp(remap(dot(geo.outputs["Normal"], FILL_DIR)), [(0.0, 0.0), (0.5, 0.0), (0.56, 1.0)])

    def mulc(a, col):
        m = N("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MULTIPLY"
        m.inputs["Factor"].default_value = 1.0
        L(a, m.inputs[6])
        m.inputs[7].default_value = col
        return m.outputs[2]

    def add(a, b):
        m = N("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "ADD"
        m.inputs["Factor"].default_value = 1.0
        L(a, m.inputs[6])
        L(b, m.inputs[7])
        return m.outputs[2]

    def mul(a, b):
        m = N("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MULTIPLY"
        m.inputs["Factor"].default_value = 1.0
        L(a, m.inputs[6])
        L(b, m.inputs[7])
        return m.outputs[2]

    light = add(add(mulc(key, (1.0, 0.93, 0.80, 1)), mulc(fill, (0.16, 0.19, 0.30, 1))), _const(nt, (0.30, 0.27, 0.33, 1)))
    lit = mul(base, light)
    # rim: warm, only near grazing angles
    lw = N("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    rim_m = ramp(lw.outputs["Facing"], [(0.0, 0.0), (0.62, 0.0), (0.8, rim)])
    col = add(lit, mulc(rim_m, (1.0, 0.82, 0.6, 1)))
    if emis_img is not None:
        te = N("ShaderNodeTexImage")
        te.image = emis_img
        col = add(col, mulc(te.outputs["Color"], (emis_gain, emis_gain, emis_gain, 1)))
    L(col, em.inputs["Color"])
    return mat


def _const(nt, rgba):
    n = nt.nodes.new("ShaderNodeRGB")
    n.outputs[0].default_value = rgba
    return n.outputs[0]


def ink_material():
    mat = bpy.data.materials.get("GFA_ink_preview")
    if mat:
        return mat
    mat = bpy.data.materials.new("GFA_ink_preview")
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mixs = nt.nodes.new("ShaderNodeMixShader")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = C.hex_linear("#120C10")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    # hull faces seen from behind (between camera and asset) are transparent; the far side is ink
    nt.links.new(geo.outputs["Backfacing"], mixs.inputs["Fac"])
    nt.links.new(em.outputs["Emission"], mixs.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mixs.inputs[2])
    nt.links.new(mixs.outputs["Shader"], out.inputs["Surface"])
    return mat


def add_ink_hull(obj, thickness):
    """Inverted hull: a copy pushed out along the vertex normals, faces flipped, ink material."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * thickness
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(obj.name + "_INK")
    bm.to_mesh(me)
    bm.free()
    me.materials.clear()
    me.materials.append(ink_material())
    for p in me.polygons:
        p.material_index = 0
    hull = bpy.data.objects.new(obj.name + "_INK", me)
    for c in obj.users_collection:
        c.objects.link(hull)
    hull.parent = obj
    hull.matrix_parent_inverse = Matrix.Identity(4)
    for vg in obj.vertex_groups:
        hull.vertex_groups.new(name=vg.name)
    for mod in obj.modifiers:
        if mod.type == "ARMATURE":
            m2 = hull.modifiers.new(mod.name, "ARMATURE")
            m2.object = mod.object
    hull["gfa_preview"] = True
    return hull


@contextmanager
def toon_preview(objs, ink=0.006, flat=None):
    """Swap the objects' materials for toon previews (+ ink hulls) inside the with-block.
    flat: {obj_name: hex} renders those objects in one flat colour (mannequin)."""
    saved = {}
    hulls = []
    made = []
    flat = flat or {}
    for o in objs:
        if o.type != "MESH":
            continue
        saved[o.name] = [s.material for s in o.material_slots]
        for i, s in enumerate(o.material_slots):
            if o.name in flat:
                pm = toon_material("PREVIEW_%s_%d" % (o.name, i), flat_hex=flat[o.name], rim=0.25)
            else:
                pm = toon_material("PREVIEW_%s_%d" % (o.name, i), _tex_of(s.material, "Base Color"),
                                   _tex_of(s.material, "Emission Color"))
            made.append(pm)
            s.material = pm
        if ink > 0:
            hulls.append(add_ink_hull(o, ink))
    try:
        yield hulls
    finally:
        for o in objs:
            if o.name in saved:
                for s, m in zip(o.material_slots, saved[o.name]):
                    s.material = m
        C.remove_objects(hulls)
        for m in made:
            bpy.data.materials.remove(m)


# ---- scene / camera ----------------------------------------------------------------------------------

def setup_cycles(scene, samples=12, bg=BG_REVIEW):
    C.use_cpu(scene)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.max_bounces = 2
    scene.cycles.transparent_max_bounces = 8
    scene.render.filter_size = 1.2
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    w = scene.world
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bgn = nt.nodes.new("ShaderNodeBackground")
    bgn.inputs["Color"].default_value = C.hex_linear(bg)
    nt.links.new(bgn.outputs["Background"], out.inputs["Surface"])
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def setup_workbench_flat(scene, color="#0E0B0C", bg=BG_SIL):
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = C.hex_linear(color)[:3]
    sh.show_cavity = False
    sh.show_shadows = False
    sh.show_object_outline = False
    sh.background_type = "VIEWPORT"
    sh.background_color = C.hex_linear(bg)[:3]
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def camera(scene):
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("GFA_CAM", bpy.data.cameras.new("GFA_CAM"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.type = "ORTHO"
    return cam


def aim(scene, target, direction, ortho_scale, dist=40.0):
    cam = camera(scene)
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_mode = "QUATERNION"
    up = "Y"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", up)
    if abs(d.z) > 0.999:
        cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    cam.data.ortho_scale = ortho_scale
    cam.data.clip_start = 0.01
    cam.data.clip_end = dist * 2 + 50
    return cam


def _points(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        pts.extend(mw @ v.co for v in me.vertices)
        ev.to_mesh_clear()
    return pts


def frame(pts, direction, up_hint=(0, 0, 1)):
    """Centre and (width, height) of points projected on the view plane of `direction`."""
    d = Vector(direction).normalized()
    q = (-d).to_track_quat("-Z", "Y")
    R = q.to_matrix()
    right, up = R.col[0], R.col[1]
    xs = [p.dot(right) for p in pts]
    ys = [p.dot(up) for p in pts]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    depth = sum(p.dot(d) for p in pts) / len(pts)
    c = right * cx + up * cy + d * depth
    return c, max(xs) - min(xs), max(ys) - min(ys)


def render(scene, path, w, h=None):
    scene.render.resolution_x, scene.render.resolution_y = w, h or w
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    C.ensure_dir(os.path.dirname(path))
    bpy.ops.render.render(write_still=True)
    return path


# ---- review sets ---------------------------------------------------------------------------------------

def turnaround(objs, out_dir, stem, views=None, size=512, pad=1.12, ink=None, samples=12):
    """Toon-preview renders of objs from each view at one shared scale. Returns {view: path}."""
    scene = bpy.context.scene
    views = views or WEAPON_VIEWS
    pts = _points(objs)
    ext = max(max(frame(pts, d)[1:]) for d in views.values())
    diag = (max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts),
            max(p.z for p in pts) - min(p.z for p in pts))
    ink = ink if ink is not None else max(0.0025, 0.006 * max(diag))
    setup_cycles(scene, samples)
    out = {}
    with toon_preview(objs, ink=ink):
        for name, d in views.items():
            c, _, _ = frame(pts, d)
            aim(scene, c, d, ext * pad)
            out[name] = render(scene, os.path.join(out_dir, "%s_turn_%s.png" % (stem, name)), size)
    return out


def silhouette(objs, path, direction, px_per_m=None, size=512, pad=1.1):
    """Flat black silhouette. px_per_m given -> true pixel scale (game size), else fitted to `size`."""
    scene = bpy.context.scene
    setup_workbench_flat(scene)
    pts = _points(objs)
    c, w, h = frame(pts, direction)
    if px_per_m:
        wpx = max(8, int(math.ceil(max(w, h) * pad * px_per_m)))
        aim(scene, c, direction, wpx / px_per_m)
        return render(scene, path, wpx)
    aim(scene, c, direction, max(w, h) * pad)
    return render(scene, path, size)


# ---- mannequin + in-game camera --------------------------------------------------------------------------

def mannequin(height=SPEC.HERO_HEIGHT, aim_dir=(0.0, -1.0, 0.0), grip_r=None, grip_l=None, name="GFA_MANNEQUIN",
              col=None):
    """A neutral 2.2 m hero-scale figure at the origin facing aim_dir (built facing -Y, right hand = -X,
    then turned). grip_r / grip_l: WORLD points the hands reach; None = the arm hangs."""
    s = height / 2.2
    a = Vector(aim_dir)
    a.z = 0
    ang = math.atan2(a.y, a.x) - math.atan2(-1.0, 0.0)
    to_local = Matrix.Rotation(-ang, 3, "Z")
    grip_r = None if grip_r is None else to_local @ Vector(grip_r)
    grip_l = None if grip_l is None else to_local @ Vector(grip_l)
    hip_z, sh_z = 1.02 * s, 1.72 * s
    asm = M.Assembly(name, ["skin"])
    for sx in (-1, 1):
        asm.add(M.tube([(sx * 0.13 * s, 0, 0.1 * s), (sx * 0.15 * s, 0, hip_z)], [0.1 * s, 0.14 * s], sides=8), "skin", shading="smooth")
        f = M.box((0.15 * s, 0.3 * s, 0.1 * s), bevel=0.02 * s)
        M.xform(f, loc=(sx * 0.13 * s, -0.06 * s, 0.05 * s))
        asm.add(f, "skin")
    torso = M.box((0.56 * s, 0.34 * s, 0.78 * s), bevel=0.06 * s, segments=2, taper=(1.25, 1.05))
    M.xform(torso, loc=(0, 0, hip_z + 0.36 * s))
    asm.add(torso, "skin", shading="smooth")
    head = M.sphere(0.15 * s, 10, 8, scale=(1, 1.05, 1.15))
    M.xform(head, loc=(0, -0.02 * s, sh_z + 0.26 * s))
    asm.add(head, "skin", shading="smooth")
    for sx, grip in ((-1, grip_r), (1, grip_l)):
        shoulder = Vector((sx * 0.36 * s, 0, sh_z - 0.02 * s))
        if grip is None:
            hand = shoulder + Vector((sx * 0.08 * s, 0.02 * s, -0.72 * s))
        else:
            hand = Vector(grip)
        elbow = shoulder.lerp(hand, 0.5) + Vector((sx * 0.06 * s, 0.05 * s, -0.12 * s))
        asm.add(M.tube([shoulder, elbow, hand], [0.085 * s, 0.07 * s, 0.06 * s], sides=8), "skin", shading="smooth")
        fist = M.sphere(0.065 * s, 8, 6)
        M.xform(fist, loc=hand)
        asm.add(fist, "skin", shading="smooth")
    obj = asm.to_object(col)
    obj.rotation_euler = (0.0, 0.0, ang)
    return obj


def weapon_hold_matrix(aim_dir=(1.0, 0.0, 0.0), height=SPEC.HERO_HEIGHT):
    """World matrix of the grip frame for a mannequin at the origin aiming along aim_dir (horizontal):
    the right hand sits in front of the right side of the chest; weapon +Y = aim, +Z = up."""
    s = height / 2.2
    a = Vector(aim_dir)
    a.z = 0
    a.normalize()
    right = a.cross(Vector((0, 0, 1)))       # aim x up = the figure's right
    grip = right * 0.2 * s + a * 0.42 * s + Vector((0, 0, 1.2 * s))
    return C.frame_from_axes(grip, a, (0, 0, 1))


def ingame(asset_objs, out_dir, stem, hold=None, px=220, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
           mannequin_obj=None, extra_objs=(), samples=16, target=None, ink=0.012, silhouette_too=True):
    """Render through the game camera at true 1080p pixel size (px x px crop). The caller places the
    asset (and the mannequin). Returns {'color': path, 'sil': path, 'px_per_m': ..}."""
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / view_height
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    d = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
    floor = bpy.data.objects.get("GFA_FLOOR")
    if floor is None:
        me = bpy.data.meshes.new("GFA_FLOOR")
        me.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
        floor = bpy.data.objects.new("GFA_FLOOR", me)
        scene.collection.objects.link(floor)
        fm = bpy.data.materials.new("GFA_FLOOR")
        nt = fm.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = C.hex_linear(FLOOR)
        nt.links.new(e.outputs[0], o.inputs[0])
        me.materials.append(fm)
    objs = list(asset_objs) + list(extra_objs) + ([mannequin_obj] if mannequin_obj else [])
    pts = _points(objs)
    if target is None:
        c, _, _ = frame(pts, d)
    else:
        c = Vector(target)
    out = {"px_per_m": round(ppm, 2), "view_height": view_height}
    setup_cycles(scene, samples, bg=FLOOR)
    floor.hide_render = False
    flat = {mannequin_obj.name: MANNEQUIN} if mannequin_obj else {}
    with toon_preview(objs, ink=ink, flat=flat):
        aim(scene, c, d, view_height * px / SCREEN_H_F())
        out["color"] = render(scene, os.path.join(out_dir, "%s_ingame_%s.png" % (stem, int(view_height))), px)
    if silhouette_too:
        setup_workbench_flat(scene)
        floor.hide_render = True
        aim(scene, c, d, view_height * px / SCREEN_H_F())
        out["sil"] = render(scene, os.path.join(out_dir, "%s_ingame_%s_sil.png" % (stem, int(view_height))), px)
        floor.hide_render = False
    return out


def SCREEN_H_F():
    return float(SPEC.SCREEN_H)


def contact_sheet(layout, out_path, layout_dir=None):
    """Write the layout JSON (into layout_dir, default next to out_path) and build the PNG with
    gfa_sheet.py (PIL). Keep the layout out of committed folders: it holds absolute local paths."""
    spec = os.path.join(layout_dir or os.path.dirname(out_path),
                        os.path.splitext(os.path.basename(out_path))[0] + "_layout.json")
    layout = dict(layout)
    layout["out"] = out_path
    C.write_json(spec, layout, quiet=True)
    C.run_comfy_python("gfa_sheet.py", spec)
    return out_path


# ---- standard review packs ------------------------------------------------------------------------------

def _thumb_texture(src, dst, size=256):
    img = bpy.data.images.load(src, check_existing=True)
    tmp = img.copy()
    tmp.scale(size, size)
    tmp.filepath_raw = dst
    tmp.file_format = "PNG"
    C.ensure_dir(os.path.dirname(dst))
    tmp.save()
    bpy.data.images.remove(tmp)
    return dst


def _thumbs(textures, work_dir):
    """[(thumbnail path, 'basecolor 1024 px'), ...] for the sheet."""
    out = []
    for t in textures or []:
        img = bpy.data.images.load(t, check_existing=True)
        label = "%s  %d x %d px" % (os.path.splitext(os.path.basename(t))[0].rsplit("_", 1)[-1], img.size[0], img.size[1])
        out.append((_thumb_texture(t, os.path.join(work_dir, "thumb_" + os.path.basename(t)), 240), label))
    return out


def review_weapon(key, root, mesh, out_dir, work_dir, title, subtitle, swatches=(), notes=(), textures=None,
                  aims=((1.0, 0.0, 0.0), (0.6, -0.8, 0.0)), px=150, view_height=SPEC.GAME_VIEW_HEIGHTS[0]):
    """The standard weapon review: turnaround, silhouettes (fitted + game size), in-game camera with the
    mannequin for each aim direction, texture thumbnails, contact sheet <out_dir>/<key>_review.png.
    root: the grip-frame empty (moved for the in-game shots, restored after). Returns {name: path}."""
    scene = bpy.context.scene
    out = {}
    turn = turnaround([mesh], work_dir, key, WEAPON_VIEWS, size=420)
    out.update({"turn_" + k: v for k, v in turn.items()})
    out["sil_side"] = silhouette([mesh], os.path.join(work_dir, "%s_sil_side.png" % key), (1, 0, 0), size=280)
    out["sil_top"] = silhouette([mesh], os.path.join(work_dir, "%s_sil_top.png" % key), (0, 0.0001, 1), size=280)
    saved = root.matrix_world.copy()
    sockets = {c.name: c for c in root.children if c.type == "EMPTY"}
    ing = []
    for i, a in enumerate(aims):
        root.matrix_world = weapon_hold_matrix(a)
        bpy.context.view_layer.update()
        gl = sockets["grip_L"].matrix_world.translation.copy() if "grip_L" in sockets else None
        man = mannequin(aim_dir=a, grip_r=root.matrix_world.translation, grip_l=gl)
        r = ingame([mesh], work_dir, "%s_aim%d" % (key, i), px=px, view_height=view_height, mannequin_obj=man,
                   target=(0.0, 0.0, 1.0))
        ing.append(r)
        C.remove_objects([man])
    root.matrix_world = saved
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    tex = _thumbs(textures, work_dir)
    ppm = SCREEN_H_F() / view_height
    layout = {
        "title": title, "subtitle": subtitle, "width": 1600,
        "sections": [
            {"label": "Turnaround - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k.replace("turn_", "")} for k, v in out.items() if k.startswith("turn_")]},
            {"label": "In-game camera: orthographic, 55 deg pitch, view height %.0f m = 1080 px (%.1f px/m), 2.2 m hero mannequin"
                      " - 1x true size, then 3x nearest" % (view_height, ppm),
             "height": None, "images": sum([[{"path": r["color"], "label": "aim %d, 1x" % i},
                                             {"path": r["color"], "label": "aim %d, 3x" % i, "scale": 3}]
                                            for i, r in enumerate(ing)], [])},
            {"label": "Silhouette: flat side / top, and the game-size silhouettes (3x)",
             "height": None, "images": [{"path": out["sil_side"], "label": "side"}, {"path": out["sil_top"], "label": "top"}]
                + [{"path": r["sil"], "label": "aim %d game size, 3x" % i, "scale": 3} for i, r in enumerate(ing)]},
            {"label": "Textures (base colour, emissive)", "height": 240,
             "images": [{"path": p, "label": lb} for p, lb in tex]},
        ],
        "swatches": [{"hex": h, "label": n} for n, h in swatches],
        "notes": list(notes),
    }
    for i, r in enumerate(ing):
        out["ingame_%d" % i] = r["color"]
        out["ingame_sil_%d" % i] = r["sil"]
    out["sheet"] = contact_sheet(layout, os.path.join(out_dir, "%s_review.png" % key), work_dir)
    return out


def review_enemy(key, arm, mesh, out_dir, work_dir, title, subtitle, clips=(), swatches=(), notes=(),
                 textures=None, px=160, view_height=SPEC.GAME_VIEW_HEIGHTS[0], strip_frames=4):
    """The standard enemy review: rest-pose turnaround, a pose strip per clip, in-game camera next to the
    mannequin (1x + 3x), game-size silhouette, textures, contact sheet <out_dir>/<key>_review.png."""
    import gfa_rig as RIG
    out = {}
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    turn = turnaround([mesh], work_dir, key, CREATURE_VIEWS, size=420)
    out.update({"turn_" + k: v for k, v in turn.items()})
    # clip strips: evaluate each clip at a few frames, rendered from the 3/4 front
    strips = []
    scene = bpy.context.scene
    pts = _points([mesh])
    d = CREATURE_VIEWS["34_front"]
    c, w, h = frame(pts, d)
    ext = max(w, h) * 1.6
    setup_cycles(scene, 10)
    with toon_preview([mesh], ink=max(0.003, 0.006 * ext)):
        for clip in clips:
            ad = arm.animation_data
            tr = ad.nla_tracks.get(clip)
            if tr is None:
                continue
            a = tr.strips[0].action
            f0, f1 = int(a.frame_start), int(a.frame_end)
            for k in range(strip_frames):
                f = f0 + round((f1 - f0) * k / max(1, strip_frames - 1 if not clip.endswith("@loop") else strip_frames))
                RIG.pose_at(arm, clip, f)
                aim(scene, c, d, ext)
                p = os.path.join(work_dir, "%s_clip_%s_%02d.png" % (key, clip.replace("@", "_"), k))
                strips.append((clip, f, render(scene, p, 200)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    # in-game: the enemy at the origin facing the camera 3/4, mannequin to its left
    man = mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-1.1 - 0.6 * max(w, h), 0.3, 0.0)
    bpy.context.view_layer.update()
    r = ingame([mesh], work_dir, key, px=max(px, int(SCREEN_H_F() / view_height * (max(w, h) * 2 + 2.5))),
               view_height=view_height, mannequin_obj=man)
    C.remove_objects([man])
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    tex = _thumbs(textures, work_dir)
    layout = {
        "title": title, "subtitle": subtitle, "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures", "height": 250,
             "images": [{"path": v, "label": k.replace("turn_", "")} for k, v in out.items() if k.startswith("turn_")]},
            {"label": "Clips (3/4 front, evenly spaced frames)", "height": 150,
             "images": [{"path": p, "label": "%s f%d" % (cl.replace(key + "_", ""), f)} for cl, f, p in strips]},
            {"label": "In-game camera (55 deg, %.1f px/m, 2.2 m mannequin): 1x, 3x, silhouette 3x" % (SCREEN_H_F() / view_height),
             "height": None, "images": [{"path": r["color"], "label": "1x"}, {"path": r["color"], "label": "3x", "scale": 3},
                                        {"path": r["sil"], "label": "silhouette 3x", "scale": 3}]},
            {"label": "Textures (base colour, emissive)", "height": 240,
             "images": [{"path": p, "label": lb} for p, lb in tex]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in swatches],
        "notes": list(notes),
    }
    out["ingame"] = r["color"]
    out["ingame_sil"] = r["sil"]
    out["sheet"] = contact_sheet(layout, os.path.join(out_dir, "%s_review.png" % key), work_dir)
    return out
