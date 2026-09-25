"""gf_assets helpers for elites, mini-bosses and bosses (headless Blender 5.2): dedicated rigs, rigid
skinning on any bone set, hidden-face culling, painting big assets at a paint scale, clip aliases, and
the boss review renders (true-pixel in-game frame, size comparison, clip key-frame strips, crowd-free).

Added by the slag_king stage as a NEW module (docs/art/ENEMIES.md section 6); the shared modules are
unchanged, so every swarm / weapon script keeps working. Elite and boss scripts may reuse all of it.

  * build_rig(name, bones)           a dedicated armature (GF_<PascalKey>_v1). Bones point straight up
                                     with roll 0 unless a direction is given, so they share the creature
                                     frame of GF_Swarm_v1: local X = the creature's left, Y = up,
                                     Z = forward (gfa_rig.py module doc). Every bone deforms.
  * skin_rigid(mesh, arm)            one bone per vertex at weight 1.0 (gfa_model.Assembly(bones=...)).
  * cull_hidden_faces(asm, ids)      deletes faces buried inside a closed "container" part that rides
                                     the SAME bone (the overlap never opens up in animation): fewer
                                     triangles and more texels for the faces you can see.
  * paint_scaled(obj, ..., scale)    gfa_paint.paint_asset() tuned for metre-scale features: the mesh is
                                     painted at `scale` (e.g. 1/8), so the painter's fixed stroke
                                     wobble, dab and emission-noise frequencies (tuned for 0.1-1 m
                                     weapons) become boss-sized brush strokes. Recipes and decals stay
                                     in real metres; they are converted here.
  * alias_clip(arm, key, alias, clip) a second NLA track (= a second glTF animation) that plays the same
                                     action under another name.
  * ingame_frame / size_compare / clip_frames / flat_views: review renders (Cycles CPU or Workbench).

Rig-table and clip conventions adapt Ashen Covenant tools/blender/ac_humanoid_enemy/ac_rig_base.py
(table-driven armature) and ac_pose.py (pose dicts, NLA stashing); see also gfa_rig.py.
"""
import math
import os
from collections import defaultdict

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import gfa_common as C
import gfa_paint as P
import gfa_render as R
import gfa_rig as RIG
import gfa_spec as SPEC


# ---- dedicated rigs ----------------------------------------------------------------------------------

def build_rig(name, bones, col=None, bone_len=0.35):
    """bones: [(name, parent|None, head (x, y, z), direction|None), ...] in creature space (metres, faces -Y).
    direction None = straight up (+Z), roll 0: the bone's local frame is the creature frame (X left, Y up,
    Z forward). A direction tilts the bone (a crown that spins about its own tilted axis, for example)."""
    arm_data = bpy.data.armatures.new(name)
    arm = bpy.data.objects.new(name, arm_data)
    (col or bpy.context.scene.collection).objects.link(arm)
    C.select_only(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for spec in bones:
        bname, parent, head = spec[0], spec[1], Vector(spec[2])
        d = Vector(spec[3]).normalized() if len(spec) > 3 and spec[3] is not None else Vector((0, 0, 1))
        b = eb.new(bname)
        b.head = head
        b.tail = head + d * bone_len
        b.roll = 0.0
        b.use_deform = True
        if parent:
            b.parent = eb[parent]
            b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    arm_data.display_type = "STICK"
    arm.show_in_front = True
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    return arm


def skin_rigid(mesh_obj, arm):
    """Armature modifier + parent; every vertex must sit 100 % on one bone of `arm`. Returns a report."""
    me = mesh_obj.data
    bone_names = {b.name for b in arm.data.bones}
    names = {vg.index: vg.name for vg in mesh_obj.vertex_groups}
    bad = [n for n in names.values() if n not in bone_names]
    if bad:
        raise ValueError("vertex groups %s are not bones of %s" % (bad, arm.name))
    unweighted, multi = 0, 0
    per_bone = defaultdict(int)
    for v in me.vertices:
        g = [x for x in v.groups if x.weight > 0]
        if not g:
            unweighted += 1
        elif len(g) > 1:
            multi += 1
        else:
            per_bone[names[g[0].group]] += 1
    if unweighted:
        raise ValueError("%d vertices have no bone" % unweighted)
    mesh_obj.parent = arm
    mesh_obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = mesh_obj.modifiers.get("Armature") or mesh_obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mod.use_vertex_groups = True
    return {"vertices": len(me.vertices), "multi_bone": multi, "per_bone": dict(per_bone)}


def alias_clip(arm, key, alias, clip):
    """Export the action of clip `{key}_{clip}` a second time as `{key}_{alias}` (another NLA track)."""
    ad = arm.animation_data
    src = ad.nla_tracks.get(RIG.clip_name(key, clip))
    if src is None:
        raise KeyError("no clip %s" % RIG.clip_name(key, clip))
    act = src.strips[0].action
    name = RIG.clip_name(key, alias)
    tr = ad.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, int(act.frame_start), act)
    st.name = name
    tr.mute = True
    return tr


# ---- hidden-face culling -------------------------------------------------------------------------------

def _inside(tree, p, eps, ray_dirs):
    loc, nrm, _i, _d = tree.find_nearest(p)
    if loc is None or (p - loc).dot(nrm) > -eps:
        return False
    for d in ray_dirs:                      # parity: an odd number of crossings = inside
        hits, o = 0, p.copy()
        for _ in range(64):
            h = tree.ray_cast(o, d)
            if h[0] is None:
                break
            hits += 1
            o = h[0] + d * 1e-4
        if hits % 2 == 0:
            return False
    return True


def cull_hidden_faces(asm, containers, eps=0.02):
    """Delete Assembly faces whose vertices and centre all lie inside one of the `containers` (part ids of
    closed parts), when the face's part rides the same bone as the container. Returns the faces removed."""
    bm = asm.bm
    layer = asm.part_layer
    bm.normal_update()
    bone_of = {p["id"]: p["bone"] for p in asm.parts}
    by_part = defaultdict(list)
    for f in bm.faces:
        by_part[f[layer]].append(f)
    trees = []
    for cid in containers:
        fs = by_part.get(cid)
        if not fs:
            continue
        vid, verts, polys = {}, [], []
        for f in fs:
            poly = []
            for v in f.verts:
                if v not in vid:
                    vid[v] = len(verts)
                    verts.append(v.co.copy())
                poly.append(vid[v])
            polys.append(poly)
        lo = Vector((min(v.x for v in verts), min(v.y for v in verts), min(v.z for v in verts)))
        hi = Vector((max(v.x for v in verts), max(v.y for v in verts), max(v.z for v in verts)))
        trees.append((cid, BVHTree.FromPolygons(verts, polys), lo, hi))
    rays = [Vector((0.31, 0.47, 0.83)).normalized(), Vector((-0.62, 0.21, -0.75)).normalized()]
    kill = []
    for f in bm.faces:
        pid = f[layer]
        pts = [v.co for v in f.verts] + [f.calc_center_median()]
        for cid, tree, lo, hi in trees:
            if cid == pid or bone_of.get(cid) != bone_of.get(pid):
                continue
            if any(p.x < lo.x or p.y < lo.y or p.z < lo.z or p.x > hi.x or p.y > hi.y or p.z > hi.z for p in pts):
                continue
            if all(_inside(tree, p, eps, rays) for p in pts):
                kill.append(f)
                break
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="FACES")
    return len(kill)


# ---- painting at a paint scale ---------------------------------------------------------------------------

def _scale_recipe(r, s):
    r = dict(r)
    r["edge_width"] = r["edge_width"] * s
    r["cavity_width"] = r["cavity_width"] * s
    r["brush_freq"] = r["brush_freq"] / s
    r["stroke_freq"] = (r["stroke_freq"][0] / s, r["stroke_freq"][1] / s)
    if r.get("spots"):
        sp = dict(r["spots"])
        sp["freq"] = sp.get("freq", 12.0) / s
        r["spots"] = sp
    if r.get("gradient"):
        g = dict(r["gradient"])
        if "center" in g:
            g["center"] = tuple(c * s for c in g["center"])
        g["range"] = (g["range"][0] * s, g["range"][1] * s)
        r["gradient"] = g
    if r.get("emit"):
        e = dict(r["emit"])
        if "center" in e:
            e["center"] = tuple(c * s for c in e["center"])
        if "radius" in e:
            e["radius"] = e["radius"] * s
        if "range" in e:
            e["range"] = (e["range"][0] * s, e["range"][1] * s)
        r["emit"] = e
    return r


def paint_scaled(obj, key, recipes, tex_dir, scale=0.125, size=2048, decals=(), ao_distance=0.6, ao_samples=16,
                 seed=0, margin_px=8, uv_angle=60.0, edge_min_angle=20.0, uv_small_islands=None):
    """gfa_paint.paint_asset() with the mesh temporarily scaled by `scale` (paint before skinning). Recipe
    lengths (edge_width, cavity_width, gradient / emit centres, radii and ranges), frequencies and decal
    frames are given in real metres and converted. Returns the painter's report (densities in real px/m)."""
    S = Matrix.Scale(scale, 4)
    rec = {z: _scale_recipe(r, scale) for z, r in recipes.items()}
    dec = []
    for d in decals:
        d = dict(d)
        d["frame"] = [list(r) for r in (S @ Matrix(d["frame"]))]
        dec.append(d)
    kw = {}
    if uv_small_islands:
        import inspect
        if "uv_small_islands" in inspect.signature(P.paint_asset).parameters:
            # (area m2, factor): islands smaller than the area are shrunk; the area is converted to paint scale
            kw["uv_small_islands"] = (uv_small_islands[0] * scale * scale, uv_small_islands[1])
        else:
            C.log("paint_scaled: this gfa_paint has no uv_small_islands; packing every island at full size")
    obj.data.transform(S)
    obj.data.update()
    try:
        rep = P.paint_asset(obj, key, rec, tex_dir, size=size, decals=dec, ao_distance=ao_distance * scale,
                            ao_samples=ao_samples, edge_min_angle=edge_min_angle, margin_px=margin_px, seed=seed,
                            uv_angle=uv_angle, **kw)
    finally:
        obj.data.transform(S.inverted())
        obj.data.update()
    dens = rep.get("texel_density_px_per_m", {})
    rep["texel_density_px_per_m"] = {k: round(v * scale, 1) for k, v in dens.items()}
    rep["paint_scale"] = scale
    return rep


# ---- review renders ------------------------------------------------------------------------------------

def flat_views(objs, out_dir, stem, zone_colors, views, size=520, pad=1.08):
    """Quick Workbench renders with one flat colour per GFA_<zone> material (modelling iterations)."""
    scene = bpy.context.scene
    for o in objs:
        for s in getattr(o, "material_slots", []):
            if s.material and s.material.name.startswith("GFA_"):
                s.material.diffuse_color = C.hex_linear(zone_colors.get(s.material.name[4:], "#808080"))
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_shadows = False
    sh.show_object_outline = True
    sh.object_outline_color = (0.02, 0.01, 0.01)
    sh.background_type = "VIEWPORT"
    sh.background_color = C.hex_linear("#4A4450")[:3]
    scene.view_settings.view_transform = "Standard"
    pts = R._points(objs)
    ext = max(max(R.frame(pts, d)[1:]) for d in views.values())
    out = {}
    for name, d in views.items():
        c, _, _ = R.frame(pts, d)
        R.aim(scene, c, d, ext * pad, dist=80.0)
        out[name] = R.render(scene, os.path.join(out_dir, "%s_flat_%s.png" % (stem, name)), size)
    return out


def _floor(scene, half=60.0):
    floor = bpy.data.objects.get("GFA_FLOOR")
    if floor is None:
        me = bpy.data.meshes.new("GFA_FLOOR")
        me.from_pydata([(-half, -half, 0), (half, -half, 0), (half, half, 0), (-half, half, 0)], [], [(0, 1, 2, 3)])
        floor = bpy.data.objects.new("GFA_FLOOR", me)
        scene.collection.objects.link(floor)
        fm = bpy.data.materials.new("GFA_FLOOR")
        nt = fm.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = C.hex_linear(R.FLOOR)
        nt.links.new(e.outputs[0], o.inputs[0])
        me.materials.append(fm)
    return floor


def game_dir():
    """Direction from the scene toward the game camera (Blender space): 55 deg pitch, yaw 0."""
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    return Vector((0.0, -math.cos(pitch), math.sin(pitch)))


def ingame_frame(objs, path, w=1600, h=900, view_height=SPEC.GAME_VIEW_HEIGHTS[0], target=(0, 0, 0),
                 mannequins=(), ink=0.03, samples=8, silhouette_path=None, extra_flat=None):
    """The game camera (orthographic, 55 deg pitch, FixedVertical view height = 1080 px) at TRUE pixel size:
    a w x h crop of the 1080p frame centred on `target`. Mannequins render flat grey. Optional flat
    black silhouette of the same framing (no floor) at `silhouette_path`."""
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / view_height
    d = game_dir()
    floor = _floor(scene)
    R.setup_cycles(scene, samples, bg=R.FLOOR)
    floor.hide_render = False
    flat = {m.name: R.MANNEQUIN for m in mannequins}
    flat.update(extra_flat or {})
    allo = list(objs) + list(mannequins)
    ortho = max(w, h) / ppm
    with R.toon_preview(allo, ink=ink, flat=flat):
        R.aim(scene, Vector(target), d, ortho, dist=90.0)
        R.render(scene, path, w, h)
    out = {"color": path, "px_per_m": round(ppm, 2), "view_height": view_height}
    if silhouette_path:
        R.setup_workbench_flat(scene)
        floor.hide_render = True
        R.aim(scene, Vector(target), d, ortho, dist=90.0)
        R.render(scene, silhouette_path, w, h)
        floor.hide_render = False
        out["sil"] = silhouette_path
    return out


def size_compare(objs, path, mannequin_obj, w=1200, h=900, pad=1.1, samples=8, ink=0.04, pole_height=None):
    """Front orthographic view of the asset beside a 2.2 m hero mannequin and a measuring pole (1 m bands,
    every 5 m marked light) on a flat ground line."""
    scene = bpy.context.scene
    made = []
    if pole_height:
        import gfa_model as M
        asm = M.Assembly("GFA_POLE", ["dark", "light"])
        for i in range(int(math.ceil(pole_height))):
            b = M.box((0.25, 0.25, 1.0))
            M.xform(b, loc=(0, 0, i + 0.5))
            asm.add(b, "light" if (i % 5 == 4) else ("dark" if i % 2 == 0 else "light"))
        pole = asm.to_object()
        pole.location = mannequin_obj.location + Vector((1.2, 0, 0))
        made.append(pole)
    floor = _floor(scene)
    floor.hide_render = False
    R.setup_cycles(scene, samples, bg="#2E2A33")
    allo = list(objs) + [mannequin_obj] + made
    flat = {mannequin_obj.name: R.MANNEQUIN}
    for m in made:
        flat[m.name] = "#D8CFC0"
    d = Vector((0.0, -1.0, 0.0))
    pts = R._points(allo)
    c, fw, fh = R.frame(pts, d)
    ortho = max(fw * pad, fh * pad * w / h)
    with R.toon_preview(allo, ink=ink, flat=flat):
        R.aim(scene, c + Vector((0, 0, 0.0)), d, ortho, dist=90.0)
        R.render(scene, path, w, h)
    C.remove_objects(made)
    return path


def clip_frames(arm, objs, clips, work_dir, key, frames=5, size=200, direction=(0.72, -0.62, 0.32), ext=None,
                samples=6, ink=0.04, center=None, after_pose=None, frame_lists=None):
    """Render `frames` evenly spaced frames of each clip (track name) with the toon preview from one
    direction at one shared scale; frame_lists {track: [frames]} picks the frames instead (key poses).
    after_pose(clip, frame) may tweak the pose (review-only spin, etc.). Returns [(clip, frame, path), ...]."""
    scene = bpy.context.scene
    d = Vector(direction).normalized()
    pts = R._points(objs)
    c, fw, fh = R.frame(pts, d)
    if center is not None:
        c = Vector(center)
    ext = ext or max(fw, fh) * 1.45
    R.setup_cycles(scene, samples)
    out = []
    with R.toon_preview(objs, ink=ink):
        for clip in clips:
            tr = arm.animation_data.nla_tracks.get(clip)
            if tr is None:
                continue
            a = tr.strips[0].action
            f0, f1 = int(a.frame_start), int(a.frame_end)
            loop = clip.endswith("@loop")
            fl = (frame_lists or {}).get(clip)
            if not fl:
                fl = [f0 + round((f1 - f0) * k / (frames if loop else max(1, frames - 1))) for k in range(frames)]
            for k, f in enumerate(fl):
                RIG.pose_at(arm, clip, f)
                if after_pose:
                    after_pose(clip, f)
                    bpy.context.view_layer.update()
                R.aim(scene, c, d, ext, dist=90.0)
                p = os.path.join(work_dir, "%s_clip_%s_%02d.png" % (key, clip.replace("@", "_"), k))
                out.append((clip, f, R.render(scene, p, size)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out
