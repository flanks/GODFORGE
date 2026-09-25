"""Stage 2, step 5: UVs, baked data maps, hand-painted NPR textures and the final material.

  blender -b -P tools/blender/gf_hero/s2_texture.py -- <parts.blend> <retopo_start.blend> <texture.json> \
          <body_fit_report.json> <out.blend> <texture_dir> [--size 2048] [--report <json>]

  1. shading: the body and the cloth/hair shells smooth, hard-surface parts with sharp edges above 35 deg;
  2. UVs (s2_uv.py): one 2048 atlas, one texel density, hidden faces packed small;
  3. bakes with Cycles (1 sample, EMIT) into float images: world position, world normal, paint zone,
     object index, coverage; plus the sculpt's concavity transferred onto the body (selected-to-active
     from the stage-1 reference) so anatomy lines follow the approved sculpt;
  4. paints base colour + emissive in numpy (s2_paint.py), dilates the gutters, writes sRGB PNGs;
  5. one material M_brax (base colour + emissive textures) on every part; the paint zone stays on
     the faces as the integer attribute `gf_zone` so the textures can be repainted later.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import s2_geom as G  # noqa: E402
import s2_paint as PT  # noqa: E402
import s2_uv as UV  # noqa: E402
from s2lib import (ROOT, get_co, get_edges, log, mesh_stats, opt, read_json, rel, save_blend, script_args,  # noqa: E402
                   select_only, write_json)

argv = script_args(__doc__)
if len(argv) < 6:
    raise SystemExit(__doc__)
PARTS, REF, CFG, FITREP, OUT, TEXDIR = (os.path.abspath(a) for a in argv[:6])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(CFG)
SIZE = opt(argv, "--size", cfg.get("size", 2048), int)
fitrep = read_json(FITREP) if os.path.isfile(FITREP) else None
pal_path = os.path.join(ROOT, cfg["palette"]) if "palette" in cfg else os.path.join(os.path.dirname(CFG), "palette.json")
pal = {s["key"]: s["tones"] for s in read_json(pal_path)["swatches"]}
report = {"size": SIZE}
T0 = time.time()

bpy.ops.wm.open_mainfile(filepath=PARTS)
scene = bpy.context.scene
for o in list(scene.objects):
    if o.name.startswith("REF"):
        bpy.data.objects.remove(o)
bpy.data.orphans_purge(do_recursive=True)
objs = [bpy.data.objects[n] for n in cfg["objects"]]
copies = {bpy.data.objects[t]: bpy.data.objects[s_] for t, s_ in cfg.get("uv_copy", {}).items()}
body = bpy.data.objects[cfg["body_object"]] if cfg.get("body_object") else None

# ---- 1. shading ---------------------------------------------------------------------------------------
for o in objs + list(copies):
    me = o.data
    me.shade_smooth()
    if o is not body:
        me.set_sharp_from_angle(angle=math.radians(cfg["sharp_angle_deg"]))

# ---- 2. UVs -------------------------------------------------------------------------------------------
if body is not None:
    counts, cuts = UV.body_seams(body, dict(cfg["uv"]["body"], eye_zone=G.Z["eye"]))
    report["uv_body_regions"] = counts
    report["uv_body_cuts"] = cuts
bvh_all = UV.build_bvh_all(objs)
for name in cfg.get("shell_objects", []):
    o = bpy.data.objects[name]
    UV.shell_seams(o, bvh_all)
    # open closed bands with a cut down the back (x = 0, behind the body)
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for e in bm.edges:
        a, b = e.verts
        if abs(a.co.x) < 1e-5 and abs(b.co.x) < 1e-5 and a.co.y > 0.0 and b.co.y > 0.0:
            e.seam = True
    bm.to_mesh(me)
    bm.free()
smart = [bpy.data.objects[n] for n in cfg.get("smart_objects", [])]
hidden_faces = UV.unwrap_all(objs, body, smart, [], density_hidden=cfg["uv"]["hidden_density"], margin_px=cfg["uv"]["margin_px"], size=SIZE)
for t, s_ in copies.items():
    # same construction order (e.g. the fist variant of a gauntlet) -> identical loops -> copy the UVs
    if len(t.data.loops) != len(s_.data.loops):
        raise SystemExit("uv_copy: %s and %s differ in topology" % (t.name, s_.name))
    uv = np.empty(len(s_.data.loops) * 2, dtype=np.float32)
    s_.data.uv_layers.active.data.foreach_get("uv", uv)
    while t.data.uv_layers:
        t.data.uv_layers.remove(t.data.uv_layers[0])
    t.data.uv_layers.new(name="UVMap").data.foreach_set("uv", uv)
report["uv_copied"] = {t.name: s_.name for t, s_ in copies.items()}
report["uv_hidden_faces_packed_small"] = hidden_faces
report["texel_density_px_per_m"] = UV.texel_density(objs, SIZE)
report["uv_zero_area_faces"] = UV.zero_area_faces(objs)
log("UVs done (%.0fs): density %s" % (time.time() - T0, report["texel_density_px_per_m"]["_all"]))

# ---- 3. bakes -------------------------------------------------------------------------------------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.cycles.use_denoising = False
scene.render.bake.margin = 0
scene.render.bake.use_clear = True
for i, o in enumerate(objs):
    o.pass_index = i + 1
co_all = np.concatenate([get_co(o.data) @ np.array(o.matrix_world)[:3, :3].T + np.array(o.matrix_world)[:3, 3] for o in objs])
LO = co_all.min(0) - 0.01
HI = co_all.max(0) + 0.01
zone_mats = [bpy.data.materials["Z_" + z] for z in G.ZONES]
img = bpy.data.images.new("gf_bake", SIZE, SIZE, alpha=True, float_buffer=True)
img.colorspace_settings.name = "Non-Color"


def set_pass(kind):
    for zi, m in enumerate(zone_mats):
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
        if kind == "pos":
            g = nt.nodes.new("ShaderNodeNewGeometry")
            sub = nt.nodes.new("ShaderNodeVectorMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = tuple(LO)
            div = nt.nodes.new("ShaderNodeVectorMath")
            div.operation = "DIVIDE"
            div.inputs[1].default_value = tuple(HI - LO)
            nt.links.new(g.outputs["Position"], sub.inputs[0])
            nt.links.new(sub.outputs[0], div.inputs[0])
            nt.links.new(div.outputs[0], em.inputs["Color"])
        elif kind == "nrm":
            g = nt.nodes.new("ShaderNodeNewGeometry")
            ma = nt.nodes.new("ShaderNodeVectorMath")
            ma.operation = "MULTIPLY_ADD"
            ma.inputs[1].default_value = (0.5, 0.5, 0.5)
            ma.inputs[2].default_value = (0.5, 0.5, 0.5)
            nt.links.new(g.outputs["Normal"], ma.inputs[0])
            nt.links.new(ma.outputs[0], em.inputs["Color"])
        elif kind == "zone":
            v = (zi + 1) / 32.0
            em.inputs["Color"].default_value = (v, v, v, 1.0)
        elif kind == "mask":
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_name = "gf_mask"
            nt.links.new(at.outputs["Color"], em.inputs["Color"])
        elif kind == "obj":
            oi = nt.nodes.new("ShaderNodeObjectInfo")
            dv = nt.nodes.new("ShaderNodeMath")
            dv.operation = "DIVIDE"
            dv.inputs[1].default_value = 32.0
            nt.links.new(oi.outputs["Object Index"], dv.inputs[0])
            nt.links.new(dv.outputs[0], em.inputs["Color"])


def bake(kind, targets):
    set_pass(kind)
    for o in scene.objects:
        o.select_set(False)
    for o in targets:
        o.select_set(True)
    bpy.context.view_layer.objects.active = targets[0]
    bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
    px = np.empty(SIZE * SIZE * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(SIZE, SIZE, 4)


maps_img = {}
for kind in ("zone", "pos", "nrm", "obj", "mask"):
    t = time.time()
    maps_img[kind] = bake(kind, objs)
    log("baked %s (%.0fs)" % (kind, time.time() - t))

# sculpt concavity -> body (anatomy lines)
maps_img["cav"] = np.zeros((SIZE, SIZE, 4), dtype=np.float32)
if body is not None and cfg.get("cav") and os.path.isfile(REF):
    with bpy.data.libraries.load(REF, link=False) as (src, dst):
        dst.objects = ["REF_blockout"]
    ref = dst.objects[0]
    scene.collection.objects.link(ref)
    ref.hide_select = False
    ref.hide_viewport = False
    ref.hide_render = False
    ref.hide_set(False)
    rme = ref.data
    rco = get_co(rme)
    redges = get_edges(rme)
    nv = len(rco)
    deg = np.bincount(redges.ravel(), minlength=nv).astype(np.float64)
    acc = np.zeros_like(rco)
    np.add.at(acc, redges[:, 0], rco[redges[:, 1]])
    np.add.at(acc, redges[:, 1], rco[redges[:, 0]])
    lap = acc / np.maximum(deg, 1)[:, None] - rco
    rme.update()
    rn = np.empty(nv * 3)
    rme.vertices.foreach_get("normal", rn)
    rn = rn.reshape(-1, 3)
    elen = np.linalg.norm(rco[redges[:, 0]] - rco[redges[:, 1]], axis=1).mean()
    cav = (lap * rn).sum(1) / elen
    for _ in range(cfg["cav"]["smooth_iters"]):
        a2 = np.zeros(nv)
        np.add.at(a2, redges[:, 0], cav[redges[:, 1]])
        np.add.at(a2, redges[:, 1], cav[redges[:, 0]])
        cav = 0.5 * cav + 0.5 * a2 / np.maximum(deg, 1)
    lo_, hi_ = np.percentile(cav, [2, 98])
    cavn = np.clip((cav - lo_) / (hi_ - lo_), 0, 1).astype(np.float32)
    ca = rme.color_attributes.new("cav", "FLOAT_COLOR", "POINT")
    ca.data.foreach_set("color", np.repeat(cavn, 4).reshape(-1, 4).ravel())
    rmat = bpy.data.materials.new("REF_cav")
    rmat.use_nodes = True
    nt = rmat.node_tree
    nt.nodes.clear()
    o_ = nt.nodes.new("ShaderNodeOutputMaterial")
    e_ = nt.nodes.new("ShaderNodeEmission")
    at_ = nt.nodes.new("ShaderNodeAttribute")
    at_.attribute_name = "cav"
    nt.links.new(at_.outputs["Color"], e_.inputs["Color"])
    nt.links.new(e_.outputs["Emission"], o_.inputs["Surface"])
    rme.materials.clear()
    rme.materials.append(rmat)
    set_pass("zone")
    t = time.time()
    # selected-to-active: REF emits its concavity into the body's atlas
    for m in zone_mats:
        nt = m.node_tree
        for n_ in nt.nodes:
            if n_.type == "TEX_IMAGE":
                nt.nodes.active = n_
    for o in scene.objects:
        o.select_set(False)
    ref.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.bake(type="EMIT", use_selected_to_active=True, cage_extrusion=cfg["cav"]["cage"],
                        max_ray_distance=cfg["cav"]["max_ray"], margin=0, use_clear=True)
    px = np.empty(SIZE * SIZE * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    maps_img["cav"] = px.reshape(SIZE, SIZE, 4)
    log("baked sculpt concavity onto the body (%.0fs)" % (time.time() - t))
    bpy.data.objects.remove(ref)

# ---- 4. paint -------------------------------------------------------------------------------------------
zone_f = maps_img["zone"][..., 0] * 32.0 - 1.0
valid = zone_f > -0.5
zi = np.rint(zone_f[valid]).astype(np.int64)
pos = maps_img["pos"][..., :3][valid] * (HI - LO) + LO
nrm = maps_img["nrm"][..., :3][valid] * 2 - 1
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
obj = np.rint(maps_img["obj"][..., 0][valid] * 32.0).astype(np.int64)
cavv = maps_img["cav"][..., 0][valid]
maps = {"pos": pos.astype(np.float32), "nrm": nrm.astype(np.float32), "zone": zi, "obj": obj,
        "cav": np.where(obj == (objs.index(body) + 1 if body is not None else -1), cavv, 0.0).astype(np.float32), "mask": maps_img["mask"][..., 0][valid].astype(np.float32)}
report["atlas_coverage"] = round(float(valid.mean()), 4)
pc = dict(cfg["paint"])
if fitrep and "eyes" in fitrep:
    eyes = fitrep["eyes"]["centres"]
    pc["eye_x"] = abs(eyes[0][0])
    pc["eye_y"] = eyes[0][1]
    pc["eye_z"] = eyes[0][2]
lips = body.vertex_groups.get("lips") if body is not None else None
if lips:
    bco = get_co(body.data)
    lz = [bco[v.index][2] for v in body.data.vertices if any(g.group == lips.index and g.weight > 0.5 for g in v.groups)]
    pc["mouth_z"] = float(np.mean(lz))
t = time.time()
base, emis = PT.paint(maps, G.Z, pal, pc, log=log)
log("painted %d texels (%.0fs)" % (len(pos), time.time() - t))
B = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
E = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
B[valid] = base
E[valid] = emis
B = PT.dilate(B, valid, cfg["uv"]["margin_px"] + 8)
E = PT.dilate(E, valid, cfg["uv"]["margin_px"] + 8)
os.makedirs(TEXDIR, exist_ok=True)


def save_png(arr, name):
    im = bpy.data.images.new(name, SIZE, SIZE, alpha=False)
    rgba = np.concatenate([arr, np.ones((SIZE, SIZE, 1), dtype=np.float32)], axis=2)
    im.pixels.foreach_set(rgba.ravel())          # 8-bit image: pixels are the stored (sRGB) values
    path = os.path.join(TEXDIR, name + ".png")
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    im = bpy.data.images.load(path)
    im.filepath = bpy.path.relpath(path, start=os.path.dirname(OUT))
    return im


img_base = save_png(B, cfg["texture_names"]["base_color"])
img_emis = save_png(E, cfg["texture_names"]["emissive"])
report["textures"] = {k: rel(os.path.join(TEXDIR, v + ".png")) for k, v in cfg["texture_names"].items()}
log("textures written", report["textures"])

# ---- 5. material + zone attribute -------------------------------------------------------------------------
M = bpy.data.materials.new(cfg["material_name"])
M.use_nodes = True
nt = M.node_tree
bsdf = nt.nodes["Principled BSDF"]
tb = nt.nodes.new("ShaderNodeTexImage")
tb.image = img_base
te = nt.nodes.new("ShaderNodeTexImage")
te.image = img_emis
nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(te.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = cfg["emission_strength"]
bsdf.inputs["Roughness"].default_value = 0.85
bsdf.inputs["Metallic"].default_value = 0.0
for o in objs + list(copies):
    me = o.data
    zones = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("material_index", zones)
    attr = me.attributes.get("gf_zone") or me.attributes.new("gf_zone", "INT", "FACE")
    attr.data.foreach_set("value", zones.astype(np.int32))
    me.materials.clear()
    me.materials.append(M)
for m in zone_mats:
    bpy.data.materials.remove(m)
bpy.data.images.remove(img)
bpy.data.orphans_purge(do_recursive=True)
scene.render.engine = "BLENDER_EEVEE"
report["stats"] = {o.name: mesh_stats(o) for o in objs + list(copies)}
report["triangles_total"] = sum(report["stats"][o.name]["triangles"] for o in objs)
report["triangles_variants"] = {o.name: report["stats"][o.name]["triangles"] for o in copies}
log("total triangles", report["triangles_total"])
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
log("done in %.0fs" % (time.time() - T0))
