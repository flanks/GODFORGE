"""Stage 2, step 5: UVs, baked data maps, hand-painted NPR textures and the final material.

  blender -b -P tools/blender/gf_hero/s2_texture.py -- <parts.blend> <retopo_start.blend> <texture.json> \
          <body_fit_report.json> <out.blend> <texture_dir> [--size 2048] [--report <json>]

  1. shading: the body and the cloth/hair shells smooth, hard-surface parts with sharp edges above 35 deg;
  2. UVs (s2_uv.py): one 2048 atlas, one texel density, hidden faces packed small;
  3. bakes with Cycles (1 sample, EMIT) into float images: world position, world normal, paint zone,
     object index, coverage; plus the sculpt's concavity transferred onto the body (selected-to-active
     from the stage-1 reference) so anatomy lines follow the approved sculpt;
  3b. high-to-low from the sculpt source (hi_lo in the texture config; the stage-1 blockout for the hero,
     its radially scaled gauntlet copies for the weapon; never shipped): selected-to-active with a cage,
     a tangent-space NORMAL bake, the source's concavity + Cycles AO (vertex colours) and its hit position.
     Bake artifacts are cleaned: texels whose hit lies too far from the low-poly surface fade to flat,
     only the listed zones and regions take detail, the normals are blurred by a normalised convolution
     inside the valid area and clamped; plus a self-AO bake of the assembled low-poly parts;
  4. paints base colour + emissive in numpy (s2_paint.py; AO and cavity folded into the painted colour),
     dilates the gutters, writes sRGB PNGs and the Non-Color tangent-space normal map (OpenGL / +Y, the
     glTF and Bevy StandardMaterial convention);
  5. one material M_<key> (base colour + emissive + normal map) on every part; the paint zone stays on
     the faces as the integer attribute `gf_zone` so the textures can be repainted later.
"""
import importlib
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
# per-hero hooks (absent for Brax, whose defaults are the s2_geom zones and the s2_paint painter): "zones" = the
# paint-zone list its parts script used for the material slots, "painter" = the module with paint() / dilate()
ZONES = cfg.get("zones", G.ZONES)
ZI = {n: i for i, n in enumerate(ZONES)}
if "painter" in cfg:
    PT = importlib.import_module(cfg["painter"])
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
sh = cfg.get("shading", {})
for o in objs + list(copies):
    me = o.data
    me.shade_smooth()
    if o is not body and o.name not in sh.get("smooth", []):
        me.set_sharp_from_angle(angle=math.radians(sh.get("per_object_deg", {}).get(o.name, cfg["sharp_angle_deg"])))

# ---- 2. UVs -------------------------------------------------------------------------------------------
if body is not None:
    counts, cuts = UV.body_seams(body, dict(cfg["uv"]["body"], eye_zone=ZI["eye"]))
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
hidden_faces = UV.unwrap_all(objs, body, smart, [], density_hidden=cfg["uv"]["hidden_density"], margin_px=cfg["uv"]["margin_px"], size=SIZE,
                             hidden_reach=cfg["uv"].get("hidden_reach", 0.03), hidden_start=cfg["uv"].get("hidden_start", 1e-4))
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
zone_mats = [bpy.data.materials["Z_" + z] for z in ZONES]
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

# ---- 3b. high-to-low: tangent normals, cavity and AO from the sculpt reference; self-AO of the parts --------
def enable_gpu():
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = kind
            except TypeError:
                continue
            prefs.get_devices()
            devs = [d for d in prefs.devices if d.type == kind]
            if devs:
                for d in prefs.devices:
                    d.use = d.type == kind
                scene.cycles.device = "GPU"
                return kind
    except Exception as ex:  # noqa: BLE001 - CPU fallback is fine
        log("GPU not available (%s), baking on CPU" % ex)
    scene.cycles.device = "CPU"
    return "CPU"


# "bake_device": "CPU" keeps the bakes off a GPU that other jobs share (default: the GPU when there is one)
report["bake_device"] = enable_gpu() if cfg.get("bake_device", "GPU") != "CPU" else "CPU"
if report["bake_device"] == "CPU":
    scene.cycles.device = "CPU"
log("bake device", report["bake_device"])
if scene.world is None:
    scene.world = bpy.data.worlds.new("bake_world")


def emit_mat(name, kind, attr=None):
    """Emission material for a high-poly source: its colour attribute `attr`, or its normalised world position."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    if kind == "attr":
        at = nt.nodes.new("ShaderNodeAttribute")
        at.attribute_name = attr
        nt.links.new(at.outputs["Color"], em.inputs["Color"])
    else:
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
    return m


def fill_img(rgba):
    img.pixels.foreach_set(np.tile(np.asarray(rgba, dtype=np.float32), SIZE * SIZE))


def read_img():
    px = np.empty(SIZE * SIZE * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(SIZE, SIZE, 4)


def select_pair(target, source):
    for o in scene.objects:
        o.select_set(False)
    source.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target


def vertex_ao(src, distance, samples):
    """Cycles AO of the source mesh alone, baked into a point colour attribute (the low-poly parts are hidden)."""
    hidden = [o for o in scene.objects if o is not src and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    me = src.data
    ca = me.color_attributes.get("gf_ao") or me.color_attributes.new("gf_ao", "FLOAT_COLOR", "POINT")
    me.color_attributes.active_color = ca
    scene.world.light_settings.distance = distance
    scene.cycles.samples = samples
    for o in scene.objects:
        o.select_set(False)
    src.select_set(True)
    bpy.context.view_layer.objects.active = src
    bpy.ops.object.bake(type="AO", target="VERTEX_COLORS")
    for o in hidden:
        o.hide_render = False
    scene.cycles.samples = 1
    v = np.empty(len(me.vertices) * 4, dtype=np.float32)
    ca.data.foreach_get("color", v)
    return v.reshape(-1, 4)[:, 0]


def concavity(src, iters):
    me = src.data
    rco = get_co(me)
    redges = get_edges(me)
    nv = len(rco)
    deg = np.bincount(redges.ravel(), minlength=nv).astype(np.float64)
    acc = np.zeros_like(rco)
    np.add.at(acc, redges[:, 0], rco[redges[:, 1]])
    np.add.at(acc, redges[:, 1], rco[redges[:, 0]])
    lap = acc / np.maximum(deg, 1)[:, None] - rco
    me.update()
    rn = np.empty(nv * 3)
    me.vertices.foreach_get("normal", rn)
    rn = rn.reshape(-1, 3)
    elen = np.linalg.norm(rco[redges[:, 0]] - rco[redges[:, 1]], axis=1).mean()
    cav = (lap * rn).sum(1) / elen
    for _ in range(iters):
        a2 = np.zeros(nv)
        np.add.at(a2, redges[:, 0], cav[redges[:, 1]])
        np.add.at(a2, redges[:, 1], cav[redges[:, 0]])
        cav = 0.5 * cav + 0.5 * a2 / np.maximum(deg, 1)
    lo_, hi_ = np.percentile(cav, [2, 98])
    return np.clip((cav - lo_) / (hi_ - lo_), 0, 1).astype(np.float32)


pairs = []
for hl in cfg.get("hi_lo", []):
    if hl["source"] == "REF":
        if not os.path.isfile(REF):
            continue
        with bpy.data.libraries.load(REF, link=False) as (src_, dst_):
            dst_.objects = ["REF_blockout"]
        src = dst_.objects[0]
        scene.collection.objects.link(src)
    else:
        src = bpy.data.objects[hl["source"]]
    src.hide_select = False
    src.hide_viewport = False
    src.hide_render = False
    src.hide_set(False)
    pairs.append((hl, src, [bpy.data.objects[t] for t in hl["targets"]]))
hi_maps = {}
if pairs:
    t = time.time()
    for hl, src, tg in pairs:
        me = src.data
        nv = len(me.vertices)
        cav = concavity(src, hl.get("cavity_smooth", 6)) if hl.get("cavity") else np.zeros(nv, np.float32)
        ao = vertex_ao(src, hl["ao_distance"], hl["ao_samples"]) if hl.get("ao") else np.ones(nv, np.float32)
        hi = np.stack([cav, ao, np.zeros(nv, np.float32), np.ones(nv, np.float32)], 1)
        ca = me.color_attributes.get("gf_hi") or me.color_attributes.new("gf_hi", "FLOAT_COLOR", "POINT")
        ca.data.foreach_set("color", hi.ravel())
        src["_mat_hi"] = emit_mat("HI_" + src.name, "attr", "gf_hi").name
        src["_mat_pos"] = emit_mat("POS_" + src.name, "pos").name
    log("high-poly cavity / AO prepared (%.0fs)" % (time.time() - t))
    set_pass("zone")          # every target material has the bake image as its active node
    for kind in ("hi", "hitpos", "normal"):
        t = time.time()
        fill_img((0.5, 0.5, 1.0, 0.0) if kind == "normal" else (0.0, 0.0, 0.0, 0.0))
        for hl, src, tg in pairs:
            src.data.materials.clear()
            if kind != "normal":
                src.data.materials.append(bpy.data.materials[src["_mat_hi" if kind == "hi" else "_mat_pos"]])
            for target in tg:
                select_pair(target, src)
                if kind == "normal":
                    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", use_selected_to_active=True,
                                        cage_extrusion=hl["cage"], max_ray_distance=hl["max_ray"], margin=0, use_clear=False)
                else:
                    bpy.ops.object.bake(type="EMIT", use_selected_to_active=True, cage_extrusion=hl["cage"],
                                        max_ray_distance=hl["max_ray"], margin=0, use_clear=False)
        hi_maps[kind] = read_img()
        log("baked %s high-to-low (%.0fs)" % (kind, time.time() - t))
    for hl, src, tg in pairs:
        if hl["source"] == "REF":
            bpy.data.objects.remove(src)
# self-AO of the assembled low-poly parts (belt over the waist, plates over the skirt, hair over the scalp...)
sa = cfg.get("self_ao")
if sa:
    t = time.time()
    for o in scene.objects:
        if o.type == "MESH" and o not in objs:
            o.hide_render = True
    scene.world.light_settings.distance = sa["distance"]
    scene.cycles.samples = sa["samples"]
    set_pass("zone")
    for o in scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.bake(type="AO", margin=0, use_clear=True)
    maps_img["ao_self"] = read_img()
    scene.cycles.samples = 1
    log("baked self-AO (%.0fs)" % (time.time() - t))
for o in list(scene.objects):
    if o.name.startswith("BAKESRC"):
        bpy.data.objects.remove(o)

# ---- 4. paint -------------------------------------------------------------------------------------------
zone_f = maps_img["zone"][..., 0] * 32.0 - 1.0
valid = zone_f > -0.5
zi = np.rint(zone_f[valid]).astype(np.int64)
pos = maps_img["pos"][..., :3][valid] * (HI - LO) + LO
nrm = maps_img["nrm"][..., :3][valid] * 2 - 1
nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
obj = np.rint(maps_img["obj"][..., 0][valid] * 32.0).astype(np.int64)
maps = {"pos": pos.astype(np.float32), "nrm": nrm.astype(np.float32), "zone": zi, "obj": obj,
        "mask": maps_img["mask"][..., 0][valid].astype(np.float32), "prand": maps_img["mask"][..., 1][valid].astype(np.float32)}
if "ao_self" in maps_img:
    maps["ao_self"] = maps_img["ao_self"][..., 0][valid].astype(np.float32)


def blur(a, sig):
    """Separable Gaussian blur of an image array (axes 0, 1)."""
    r = max(1, int(3 * sig))
    w = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    w /= w.sum()
    for ax in (0, 1):
        a = sum(wk * np.roll(a, k, axis=ax) for wk, k in zip(w, range(-r, r + 1)))
    return a


NM = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
NM[..., 2] = 1.0
if hi_maps:
    Pf = maps_img["pos"][..., :3] * (HI - LO) + LO
    Hp = hi_maps["hitpos"][..., :3] * (HI - LO) + LO
    dist = np.linalg.norm(Hp - Pf, axis=2)
    Of = np.rint(maps_img["obj"][..., 0] * 32.0).astype(np.int64)
    Wv = np.zeros((SIZE, SIZE), dtype=np.float32)
    Ws = np.zeros((SIZE, SIZE), dtype=np.float32)
    Tz = np.zeros((SIZE, SIZE), dtype=bool)
    for hl, src, tg in pairs:
        m = valid & np.isin(Of, [objs.index(o) + 1 for o in tg]) & np.isin(np.rint(zone_f).astype(np.int64), [ZI[z] for z in hl["zones"]])
        for ex in hl.get("exclude", []):
            e = np.ones_like(m)
            if "abs_x_min" in ex:
                e &= np.abs(Pf[..., 0]) > ex["abs_x_min"]
            if "abs_x_max" in ex:
                e &= np.abs(Pf[..., 0]) < ex["abs_x_max"]
            if "z_min" in ex:
                e &= Pf[..., 2] > ex["z_min"]
            if "z_max" in ex:
                e &= Pf[..., 2] < ex["z_max"]
            if "y_max" in ex:
                e &= Pf[..., 1] < ex["y_max"]
            m &= ~e
        Tz |= m
        vd = np.clip((hl["valid_dist"][1] - dist) / (hl["valid_dist"][1] - hl["valid_dist"][0]), 0, 1)
        vd = vd * vd * (3 - 2 * vd)
        Wv = np.where(m, vd, Wv)
        Ws = np.where(m, vd * hl["normal_strength"], Ws)
        blur_px = hl.get("blur_px", 1.5)
    n_raw = hi_maps["normal"][..., :3] * 2 - 1
    wb = blur(Ws, blur_px)
    nb = blur(n_raw * Ws[..., None], blur_px) / np.maximum(wb, 1e-4)[..., None]
    k = np.clip(Ws, 0, 1)[..., None]
    NM = NM * (1 - k) + nb * k
    NM /= np.linalg.norm(NM, axis=2, keepdims=True) + 1e-9
    NM[..., 2] = np.maximum(NM[..., 2], 0.3)
    NM /= np.linalg.norm(NM, axis=2, keepdims=True) + 1e-9
    mt = cfg.get("normal_max_tilt_deg")
    if mt:
        # bad-bake filter: where the sculpt surface is not the low-poly surface (a plate edge that the blockout
        # rounds off, a strand of the fused cape) the baked normal tilts far from the face; fade those texels to flat
        c0, c1 = math.cos(math.radians(mt[1])), math.cos(math.radians(mt[0]))
        kf = np.clip((NM[..., 2] - c0) / (c1 - c0), 0, 1)[..., None]
        NM = NM * kf + np.array([0.0, 0.0, 1.0], dtype=np.float32) * (1 - kf)
        NM /= np.linalg.norm(NM, axis=2, keepdims=True) + 1e-9
        report["normal_tilt_filter"] = {"deg": mt, "texels_faded": int(((kf[..., 0] < 0.99) & (Ws > 0.05)).sum())}
    maps["hi_w"] = Wv[valid]
    maps["cav"] = (hi_maps["hi"][..., 0] * Wv)[valid].astype(np.float32)
    maps["ao_hi"] = hi_maps["hi"][..., 1][valid].astype(np.float32)
    report["normal_bake"] = {"texels_with_detail": int((Ws > 0.05).sum()), "valid_fraction_of_target_zones":
                             round(float((Wv > 0.5).sum()) / max(1, int(Tz.sum())), 4), "blur_px": blur_px}
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
    lp = bco[[v.index for v in body.data.vertices if any(g.group == lips.index and g.weight > 0.5 for g in v.groups)]]
    inner = lp[lp[:, 1] > np.percentile(lp[:, 1], 70)]
    pc["mouth_z"] = float(np.mean(lp[:, 2]))
    pc["mouth"] = {"slit_z": float(np.median(inner[:, 2])), "half_w": float(np.abs(lp[:, 0]).max()),
                   "y_inner": float(np.median(inner[:, 1]))}
t = time.time()
base, emis = PT.paint(maps, ZI, pal, pc, log=log)
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
img_nrm = None
if "normal" in cfg["texture_names"]:
    NMc = PT.dilate((NM * 0.5 + 0.5).astype(np.float32), valid, cfg["uv"]["margin_px"] + 8)
    img_nrm = save_png(NMc, cfg["texture_names"]["normal"])
    img_nrm.colorspace_settings.name = "Non-Color"
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
if img_nrm is not None:
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = img_nrm
    nm_node = nt.nodes.new("ShaderNodeNormalMap")
    nm_node.space = "TANGENT"
    nm_node.uv_map = "UVMap"
    nt.links.new(tn.outputs["Color"], nm_node.inputs["Color"])
    nt.links.new(nm_node.outputs["Normal"], bsdf.inputs["Normal"])
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
