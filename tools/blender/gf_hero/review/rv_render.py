"""Review renders of a shipped hero GLB, posed by the independent numpy FK + LBS (gltf_fk.py): exactly the file's data,
the weapon variants as identity children of the sockets (the offhand node on weapon_L), no Blender importer involved.

  blender -b --factory-startup -P rv_render.py -- <hero.glb> <weapon.glb> <jobs.json> <out_dir>

Close-ups and strips render in Workbench, the 55 deg client camera in Cycles on the CPU (the GPU is shared).

jobs.json: {"closeups": [{"clip", "frame", "tag"}],
            "strips": [{"clip", "frames": [...], "views": {"name": [dx, dy, dz]}}],
            "ingame": [{"clip", "frame", "tag"}], "ingame_views": [{"H": 22, "yaw": 0, "crop": 190, "silhouette": true}],
            "greybox": {"radius": <characters.csv stats.radius>, "color": <characters.csv color>}}
H is the client's view height in metres over 1080 px (assets/content/game.ron camera.view_height: 22 for one player,
28 for four). The greybox is the client's fallback hero (crates/gf_client/src/scene.rs spawn_rig: a capsule r 0.5,
length 1.0, scaled (2r, 0.85, 2r) at 0.85 m, a head sphere r*0.62 at 1.82 m), placed 1.6 m to the hero's screen right.
"""
import json
import math
import os
import sys
import tempfile

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gltf_fk import GLB  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
HERO, WEAP, JOBS, OUT = [os.path.abspath(a) for a in argv[:4]]
os.makedirs(OUT, exist_ok=True)
jobs = json.load(open(JOBS, encoding="utf-8"))
g = GLB(HERO)
w = GLB(WEAP)
meta = json.load(open(HERO.replace(".glb", ".meta.json"), encoding="utf-8"))
C3 = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64)   # glTF (x, y, z) -> Blender (x, -z, y)

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
scene = bpy.context.scene
TMP = tempfile.mkdtemp(prefix="rv35_")


def load_image(gl, tex_index, name, srgb=True):
    t = gl.j["textures"][tex_index]
    data, mime = gl.image_bytes(t["source"])
    p = os.path.join(TMP, name + (".png" if "png" in (mime or "png") else ".jpg"))
    open(p, "wb").write(data)
    im = bpy.data.images.load(p)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    return im


def toon_material(gl, name, key_dir=(-0.45, -0.55, 0.70)):
    """3-band toon on N.L of a fixed key light, x base colour, + emissive x strength, output as Emission (Cycles, few
    samples). The base-colour image node is left active so Workbench TEXTURE mode shows it too."""
    mj = gl.j["materials"][0]
    pbr = mj.get("pbrMetallicRoughness", {})
    M = bpy.data.materials.new(name)
    M.use_nodes = True
    nt = M.node_tree
    nt.nodes.clear()
    L = nt.links.new
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    base = nt.nodes.new("ShaderNodeTexImage")
    base.image = load_image(gl, pbr["baseColorTexture"]["index"], name + "_base")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    ld = nt.nodes.new("ShaderNodeCombineXYZ")
    v = Vector(key_dir).normalized()
    for i in range(3):
        ld.inputs[i].default_value = v[i]
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    L(geo.outputs["Normal"], dot.inputs[0])
    L(ld.outputs[0], dot.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.36, 0.32, 0.40, 1)
    els[1].position, els[1].color = 0.12, (0.70, 0.66, 0.66, 1)
    e3 = els.new(0.52)
    e3.color = (1.0, 0.97, 0.92, 1)
    L(dot.outputs["Value"], ramp.inputs["Fac"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    L(ramp.outputs["Color"], mul.inputs["A"])
    L(base.outputs["Color"], mul.inputs["B"])
    col = mul.outputs["Result"]
    if "emissiveTexture" in mj:
        em = nt.nodes.new("ShaderNodeTexImage")
        em.image = load_image(gl, mj["emissiveTexture"]["index"], name + "_emissive")
        strength = mj.get("extensions", {}).get("KHR_materials_emissive_strength", {}).get("emissiveStrength", 1.0)
        f = mj.get("emissiveFactor", [1, 1, 1])
        sc = nt.nodes.new("ShaderNodeMix")
        sc.data_type = "RGBA"
        sc.blend_type = "MULTIPLY"
        sc.inputs["Factor"].default_value = 1.0
        L(em.outputs["Color"], sc.inputs["A"])
        sc.inputs["B"].default_value = (f[0] * strength * 0.8, f[1] * strength * 0.8, f[2] * strength * 0.8, 1)
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        add.inputs["Factor"].default_value = 1.0
        L(col, add.inputs["A"])
        L(sc.outputs["Result"], add.inputs["B"])
        col = add.outputs["Result"]
    emi = nt.nodes.new("ShaderNodeEmission")
    L(col, emi.inputs["Color"])
    L(emi.outputs["Emission"], out.inputs["Surface"])
    nt.nodes.active = base
    return M


def flat_material(name, rgb, emit=True):
    M = bpy.data.materials.new(name)
    M.use_nodes = True
    nt = M.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission" if emit else "ShaderNodeBsdfDiffuse")
    e.inputs["Color"].default_value = (rgb[0], rgb[1], rgb[2], 1)
    nt.links.new(e.outputs[0], out.inputs["Surface"])
    M.diffuse_color = (rgb[0], rgb[1], rgb[2], 1)
    return M


def make_mesh(name, pos_gl, tri, uv, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata((pos_gl @ C3.T).tolist(), [], tri.tolist())
    me.update()
    if uv is not None:
        layer = me.uv_layers.new(name="UVMap")
        u = uv[tri.reshape(-1)].astype(np.float64).copy()
        u[:, 1] = 1.0 - u[:, 1]
        layer.data.foreach_set("uv", u.ravel())
    me.materials.append(mat)
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def set_mesh(ob, pos_gl, nrm_gl=None):
    me = ob.data
    me.vertices.foreach_set("co", (pos_gl @ C3.T).astype(np.float32).ravel())
    me.update()
    if nrm_gl is not None:
        n = nrm_gl @ C3.T
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        me.normals_split_custom_set_from_vertices(n.tolist())


# ---- hero + weapon objects --------------------------------------------------------------------------------------------
mi = g.skinned_mesh()
md = g.mesh_data(g.nodes[mi]["mesh"])
joints, ibm = g.skin(0)
HPOS = md["POSITION"].astype(np.float64)
HNRM = md["NORMAL"].astype(np.float64)
HJ = md["JOINTS_0"].astype(np.int64)
HW = md["WEIGHTS_0"].astype(np.float64)
hero_mat = toon_material(g, "M_hero_review")
HERO_OB = make_mesh("hero", HPOS, md["indices"], md.get("TEXCOORD_0"), hero_mat)
weap_mat = toon_material(w, "M_weapon_review")
wroot = w.names[w.j["scenes"][0]["nodes"][0]]
WOB = {}
for i, nd in enumerate(w.nodes):
    if "mesh" in nd:
        d = w.mesh_data(nd["mesh"])
        nm = w.names[i]                      # <chassis>_<fist|open>_<L|R>
        var, side = nm.split("_")[-2], nm.split("_")[-1]
        WOB[(var, side)] = (make_mesh(nm, d["POSITION"].astype(np.float64), d["indices"], d.get("TEXCOORD_0"), weap_mat),
                            d["POSITION"].astype(np.float64), d["NORMAL"].astype(np.float64))

CLIPS = {}


def clip_world(an):
    if an not in CLIPS:
        ai = g.anim_names().index(an)
        times, T, R, S, _ = g.sample(ai)
        CLIPS[an] = g.world(T, R, S)
    return CLIPS[an]


def variant_at(an, s, fr):
    wv = meta["clip_info"][an].get("weapon_variant") or {s: {"start": "fist", "swap_frames": []}}
    v = wv[s]["start"]
    for sf in wv[s]["swap_frames"]:
        if fr >= sf:
            v = "open" if v == "fist" else "fist"
    return v


def pose(an, fr):
    W = clip_world(an)[fr]
    Mj = W[joints] @ ibm
    blend = (Mj[HJ] * HW[:, :, None, None]).sum(1)
    p = np.einsum("vij,vj->vi", blend[:, :3, :3], HPOS) + blend[:, :3, 3]
    n = np.einsum("vij,vj->vi", blend[:, :3, :3], HNRM)
    set_mesh(HERO_OB, p, n)
    for (var, side), (ob, wp, wn) in WOB.items():
        S = W[g.idx["weapon_" + side]]
        show = var == variant_at(an, side, fr)
        ob.hide_render = not show
        if show:
            set_mesh(ob, wp @ S[:3, :3].T + S[:3, 3], wn @ S[:3, :3].T)
    return W


def jpos(W, name):
    return Vector((W[g.idx[name], :3, 3] @ C3.T).tolist())


# ---- cameras / render -------------------------------------------------------------------------------------------------
cam = bpy.data.objects.new("CAM", bpy.data.cameras.new("CAM"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"


def aim(target, direction, ortho, dist=20.0):
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_mode = "QUATERNION"
    up = "Y" if abs(d.z) < 0.98 else "X"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", up if up == "Y" else "X")
    cam.data.ortho_scale = ortho
    cam.data.clip_start = 0.01
    cam.data.clip_end = dist + 30


def workbench():
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE"
    sh.show_cavity = False
    sh.show_shadows = False
    sh.show_object_outline = False
    sh.show_backface_culling = False
    sh.background_type = "VIEWPORT"
    sh.background_color = (0.22, 0.23, 0.25)
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_border = False


def render(path, rx, ry=None):
    scene.render.resolution_x, scene.render.resolution_y = rx, ry or rx
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    for attempt in range(3):
        try:
            bpy.ops.render.render(write_still=True)
            return path
        except RuntimeError as e:          # shared GPU (Workbench): retry on device errors
            print("render retry", attempt, e)
    raise SystemExit("render failed: " + path)


# ground grid for the close-ups (z = 0)
gme = bpy.data.meshes.new("ground")
N = 12
vs, fs = [], []
for i in range(N + 1):
    for j in range(N + 1):
        vs.append(((i - N / 2) * 0.25, (j - N / 2) * 0.25, 0.0))
for i in range(N):
    for j in range(N):
        a = i * (N + 1) + j
        fs.append((a, a + N + 1, a + N + 2, a + 1))
gme.from_pydata(vs, [], fs)
ground = bpy.data.objects.new("ground", gme)
scene.collection.objects.link(ground)
gmats = [flat_material("g0", (0.30, 0.31, 0.33)), flat_material("g1", (0.40, 0.41, 0.43))]
for m in gmats:
    gme.materials.append(m)
gme.polygons.foreach_set("material_index", [(i + j) % 2 for i in range(N) for j in range(N)])

HERO_FRONT = Vector((0, -1, 0))   # the hero faces -Y in Blender (+Z in glTF)


def limb_view(a, b, c, torso, fallback):
    """camera direction perpendicular to the limb's bend plane, on the outside (away from the torso)."""
    n = (b - a).cross(c - b)
    if n.length < 1e-3:
        n = fallback.copy()
    n.normalize()
    if n.dot(b - torso) < 0:
        n = -n
    return (n * 0.85 + HERO_FRONT * 0.25 + Vector((0, 0, 0.25))).normalized()


done = []
if jobs.get("closeups"):
    workbench()
    for jb in jobs["closeups"]:
        an, fr, tag = jb["clip"], jb["frame"], jb.get("tag", "")
        W = pose(an, fr)
        chest = jpos(W, "spine_03")
        pel = jpos(W, "pelvis")
        base = os.path.join(OUT, "%s_f%03d" % (an.replace("@", "_"), fr))
        views = []
        # full body: front 3/4 and the hero's right side
        mid = (jpos(W, "head") + Vector((jpos(W, "pelvis").x, jpos(W, "pelvis").y, 0.0))) * 0.5
        mid.z = max(mid.z, 0.9)
        views.append(("body34", mid, (-0.55, -1.0, 0.35), 2.7))
        views.append(("bodyside", mid, (-1.0, 0.0, 0.15), 2.7))
        for s, side_dir in (("L", Vector((1, 0, 0))), ("R", Vector((-1, 0, 0)))):
            sh, el, wr = jpos(W, "upperarm_" + s), jpos(W, "lowerarm_" + s), jpos(W, "hand_" + s)
            d = limb_view(sh, el, wr, chest, side_dir)
            views.append(("arm" + s, (sh + el + wr) / 3, d, 1.0))
        for s, side_dir in (("L", Vector((1, 0, 0))), ("R", Vector((-1, 0, 0)))):
            hp, kn, ak = jpos(W, "thigh_" + s), jpos(W, "shin_" + s), jpos(W, "foot_" + s)
            d = limb_view(hp, kn, ak, pel, side_dir)
            views.append(("leg" + s, (hp + kn + ak) / 3, d, 1.25))
        # hips / skirt from the front and behind
        views.append(("hips_front", pel + Vector((0, 0, -0.15)), (0.0, -1.0, 0.2), 1.1))
        views.append(("hips_back", pel + Vector((0, 0, -0.15)), (0.0, 1.0, 0.2), 1.1))
        for vn, tgt, d, osc in views:
            aim(tgt, d, osc)
            p = render(base + "_" + vn + ".png", 300)
            done.append({"clip": an, "frame": fr, "tag": tag, "view": vn, "png": p})
        print("closeups", an, fr, tag, flush=True)

if jobs.get("strips"):
    workbench()
    for st in jobs["strips"]:
        an = st["clip"]
        Wc = clip_world(an)
        pel = Wc[:, g.idx["pelvis"], :3, 3] @ C3.T
        tgt = Vector((float(pel[:, 0].mean()), float(pel[:, 1].mean()), 0.95))
        for vn, d in st.get("views", {"body34": (-0.55, -1.0, 0.35)}).items():
            for fr in st["frames"]:
                pose(an, fr)
                aim(tgt, d, st.get("ortho", 2.9))
                p = render(os.path.join(OUT, "strip_%s_%s_f%03d.png" % (an.replace("@", "_"), vn, fr)), st.get("px", 240))
                done.append({"clip": an, "frame": fr, "view": vn, "png": p, "strip": True})
        print("strip", an, flush=True)

if jobs.get("ingame"):
    # the client camera: orthographic, 55 deg pitch, FixedVertical view height H = 1080 px (assets/content/game.ron)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.cycles.max_bounces = 0
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.filter_width = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = False
    scene.world.color = (0.0, 0.0, 0.0)
    # arena ground: dark ash
    for m in gmats:
        m.node_tree.nodes["Emission"].inputs["Color"].default_value = (0.055, 0.045, 0.042, 1)
    ground.scale = (4, 4, 1)
    # the greybox hero (crates/gf_client/src/scene.rs spawn_rig: capsule r=0.5 len 1.0 scaled (2r, 0.85, 2r) at y 0.85,
    # head sphere r*0.62 at 1.82, in the character colour) 1.6 m to the hero's left
    gb = jobs.get("greybox", {"radius": 0.52, "color": "#FF7A3D"})
    r = gb["radius"]
    hx = gb["color"].lstrip("#")
    rgb = [((int(hx[i:i + 2], 16) / 255.0 + 0.055) / 1.055) ** 2.4 for i in (0, 2, 4)]
    gm = bpy.data.materials.new("greybox")
    gm.use_nodes = True
    nt = gm.node_tree
    nt.nodes.clear()
    o_ = nt.nodes.new("ShaderNodeOutputMaterial")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    ld = nt.nodes.new("ShaderNodeCombineXYZ")
    for i, x in enumerate(Vector((-0.45, -0.55, 0.70)).normalized()):
        ld.inputs[i].default_value = x
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    nt.links.new(ld.outputs[0], dot.inputs[1])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].color = (rgb[0] * 0.4, rgb[1] * 0.4, rgb[2] * 0.4, 1)
    ramp.color_ramp.elements[1].position = 0.12
    ramp.color_ramp.elements[1].color = (rgb[0], rgb[1], rgb[2], 1)
    nt.links.new(dot.outputs["Value"], ramp.inputs["Fac"])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], o_.inputs["Surface"])
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5, location=(0, 0, 0))
    cap_top = bpy.context.active_object
    # build the capsule as cylinder + two hemispheres (radius 0.5, cylinder length 1.0), then scale like the client
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.5, depth=1.0, location=(0, 0, 0))
    cyl = bpy.context.active_object
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.5, location=(0, 0, -0.5))
    cap_bot = bpy.context.active_object
    cap_top.location = (0, 0, 0.5)
    for o in (cap_top, cyl, cap_bot):
        o.data.materials.append(gm)
    GB_X = 1.6
    empty = bpy.data.objects.new("greybox", None)
    scene.collection.objects.link(empty)
    for o in (cap_top, cyl, cap_bot):
        o.parent = empty
    empty.location = (GB_X, 0, 0.85)
    empty.scale = (2 * r, 2 * r, 0.85)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=r * 0.62, location=(GB_X, 0, 1.82))
    head = bpy.context.active_object
    head.data.materials.append(gm)
    greybox_objs = [cap_top, cyl, cap_bot, head]
    for jb in jobs["ingame"]:
        an, fr, tag = jb["clip"], jb["frame"], jb.get("tag", "")
        W = pose(an, fr)
        pel = jpos(W, "pelvis")
        for v in jobs["ingame_views"]:
            H, yaw = v["H"], v["yaw"]
            pitch = math.radians(55.0)
            d = Vector((math.sin(math.radians(yaw)) * math.cos(pitch), -math.cos(math.radians(yaw)) * math.cos(pitch), math.sin(pitch)))
            # crop: 1080 px = H metres on the view's vertical; render a CROP x CROP window at that scale
            crop = v.get("crop", 150)
            right = Vector((math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0))   # screen right
            gpos = Vector((pel.x, pel.y, 0.0)) + right * GB_X
            empty.location = (gpos.x, gpos.y, 0.85)
            head.location = (gpos.x, gpos.y, 1.82)
            tgt = Vector((pel.x, pel.y, 1.0)) + right * (GB_X * 0.5)
            aim(tgt, d, H * crop / 1080.0)
            scene.render.use_border = False
            p = render(os.path.join(OUT, "ig_%s_f%03d_H%d_y%03d.png" % (an.replace("@", "_"), fr, H, yaw)), crop)
            done.append({"clip": an, "frame": fr, "tag": tag, "H": H, "yaw": yaw, "png": p})
            # silhouette split: gauntlets vs everything else, flat colours (the silhouette read)
            if v.get("silhouette"):
                saved = {}
                gmat = flat_material("sil_g", (1.0, 0.45, 0.05))
                bmat = flat_material("sil_b", (0.25, 0.25, 0.25))
                for ob in [HERO_OB] + [x[0] for x in WOB.values()] + greybox_objs:
                    saved[ob.name] = list(ob.data.materials)
                    for k in range(len(ob.data.materials)):
                        ob.data.materials[k] = gmat if ob in [x[0] for x in WOB.values()] else bmat
                gsave = [m.node_tree.nodes["Emission"].inputs["Color"].default_value[:] for m in gmats]
                for o in greybox_objs:
                    o.hide_render = True
                for m in gmats:
                    m.node_tree.nodes["Emission"].inputs["Color"].default_value = (0, 0, 0, 1)
                p = render(os.path.join(OUT, "sil_%s_f%03d_H%d_y%03d.png" % (an.replace("@", "_"), fr, H, yaw)), crop)
                done.append({"clip": an, "frame": fr, "tag": tag, "H": H, "yaw": yaw, "png": p, "silhouette": True})
                for ob in [HERO_OB] + [x[0] for x in WOB.values()] + greybox_objs:
                    for k, m in enumerate(saved[ob.name]):
                        ob.data.materials[k] = m
                for m, c in zip(gmats, gsave):
                    m.node_tree.nodes["Emission"].inputs["Color"].default_value = c
                for o in greybox_objs:
                    o.hide_render = False
        print("ingame", an, fr, tag, flush=True)

json.dump(done, open(os.path.join(OUT, "renders.json"), "w"), indent=1)
print("RENDERS_DONE", len(done))
