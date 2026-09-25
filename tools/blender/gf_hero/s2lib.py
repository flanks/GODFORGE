"""Shared helpers for the GODFORGE stage-2 production-mesh scripts (headless Blender 5.2, bpy + numpy).

Adapted from Ashen Covenant tools/blender/ac_humanoid_enemy/ac_common.py (log / json / selection /
collection / save helpers). GODFORGE additions: numpy mesh accessors, topology checks (non-manifold,
boundary, face-size histogram, parts), Laplacian field smoothing for the surface fit, and a
wireframe overlay that works in background renders (Workbench draws no overlays in a final render,
so the wire is a Wireframe-modifier copy drawn on top of the shaded mesh).

Conventions (docs/ART_PIPELINE.md section 5): 1 unit = 1 m, Z up, the hero faces -Y, +X is the
hero's LEFT, feet on z = 0.
"""
import json
import math
import os
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
_T0 = time.time()


def log(*args):
    print("[s2 %6.1fs]" % (time.time() - _T0), *args, flush=True)


def rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


def absp(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path.replace("/", os.sep))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    log("wrote", rel(path))


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def script_args(doc):
    argv = __import__("sys").argv
    a = argv[argv.index("--") + 1:] if "--" in argv else []
    return a


def opt(argv, name, default, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = "METERS"
    return scene


def select_only(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def move_to_collection(obj, col):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


def save_blend(path):
    ensure_dir(os.path.dirname(path))
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)
    log("saved", rel(path), "(%.1f MB)" % (os.path.getsize(path) / 1e6))


def apply_transforms(obj):
    select_only(obj)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


# ---- numpy mesh access ---------------------------------------------------------------------------

def get_co(me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_co(me, co):
    me.vertices.foreach_set("co", np.asarray(co, dtype=np.float64).ravel())
    me.update()


def get_normals(me):
    n = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("normal", n)
    return n.reshape(-1, 3)


def get_edges(me):
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def connected_parts(bm):
    """Lists of BMVerts, one per connected piece (union-find over edges)."""
    bm.verts.ensure_lookup_table()
    parent = list(range(len(bm.verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
    parts = {}
    for v in bm.verts:
        parts.setdefault(find(v.index), []).append(v)
    return list(parts.values())


# Some bmesh ops order the faces and edges they make, or the slots they free (which later faces refill), by memory
# address: bmesh.ops.create_uvsphere (Blender 5.2, its internal weld) and bmesh.ops.bevel. The vertices and the faces
# themselves come out the same every run, only their order changes, and that changed the mesh's face-corner order on
# every rebuild, and with it the UV unwrap and (the packer is chaotic in face order) sometimes the whole atlas.
# sort_new_faces / sort_new_edges / canonical_edge_verts put those elements in an order of their vertex indices.

def sort_new_faces(bm, first):
    """Faces from index `first` on (the ones made since len(bm.faces) was `first`) in the order of their vertex index
    lists. Earlier faces, all vertices and each face's own loop order stay as they are."""
    bm.verts.index_update()
    bm.faces.index_update()
    keys = {f: [v.index for v in f.verts] for f in bm.faces if f.index >= first}
    rank = {f: i for i, f in enumerate(sorted(keys, key=keys.get))}
    bm.faces.sort(key=lambda f: first + rank[f] if f in rank else f.index)
    bm.faces.index_update()


def sort_new_edges(bm, first):
    """Edges from index `first` on in the order of their (sorted) vertex index pairs; earlier edges stay put."""
    bm.verts.index_update()
    bm.edges.index_update()
    keys = {e: sorted(v.index for v in e.verts) for e in bm.edges if e.index >= first}
    rank = {e: i for i, e in enumerate(sorted(keys, key=keys.get))}
    bm.edges.sort(key=lambda e: first + rank[e] if e in rank else e.index)
    bm.edges.index_update()


def canonical_edge_verts(me, first=0):
    """Store the edges of mesh me from index `first` on as (lower, higher) vertex index. Which end an edge lists
    first means nothing to Blender (each loop keeps its own vertex and edge) and changes no UV, but the weld inside
    bmesh.ops.create_uvsphere picks it by memory address, so the saved edges differed from run to run."""
    ev = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    ev[first:] = np.sort(ev[first:], axis=1)
    me.edges.foreach_set("vertices", ev.ravel())
    me.update()


def mesh_stats(obj):
    """Triangles, face-size histogram and topology defects of a mesh object (base mesh, no modifiers)."""
    me = obj.data
    hist = {}
    for p in me.polygons:
        n = len(p.vertices)
        hist[n] = hist.get(n, 0) + 1
    bm = bmesh.new()
    bm.from_mesh(me)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    nonman = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    wire = sum(1 for e in bm.edges if e.is_wire)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    parts = len(connected_parts(bm))
    bm.free()
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    return {"name": obj.name, "vertices": len(me.vertices), "faces": len(me.polygons), "triangles": tris,
            "quads": hist.get(4, 0), "tri_faces": hist.get(3, 0), "ngons": sum(v for k, v in hist.items() if k > 4),
            "quad_ratio": round(hist.get(4, 0) / max(1, len(me.polygons)), 3),
            "boundary_edges": boundary, "nonmanifold_edges": nonman, "wire_edges": wire, "loose_verts": loose_v,
            "degenerate_faces": degenerate, "parts": parts,
            "uv_layers": [u.name for u in me.uv_layers], "materials": [m.name if m else None for m in me.materials]}


def smooth_field(field, edges, iters, pin_w=None, fixed=None):
    """Jacobi smoothing of a per-vertex field (n,) or (n,k) over the edge graph.
    pin_w (n,) >= 0: data term, each step f = (w*orig + neighbour_mean) / (w + 1).
    fixed (n,) bool: values kept exactly."""
    n = field.shape[0]
    f = field.astype(np.float64).copy()
    orig = f.copy()
    deg = np.bincount(edges.ravel(), minlength=n).astype(np.float64)
    deg[deg == 0] = 1.0
    for _ in range(iters):
        acc = np.zeros_like(f)
        np.add.at(acc, edges[:, 0], f[edges[:, 1]])
        np.add.at(acc, edges[:, 1], f[edges[:, 0]])
        mean = acc / (deg[:, None] if f.ndim == 2 else deg)
        if pin_w is not None:
            w = pin_w[:, None] if f.ndim == 2 else pin_w
            f = (w * orig + mean) / (w + 1.0)
        else:
            f = mean
        if fixed is not None:
            f[fixed] = orig[fixed]
    return f


def tangential_relax(co, normals, edges, iters=1, amount=0.5, fixed=None):
    """Move vertices toward their neighbour mean, but only within their tangent plane (evens out the quads
    without shrinking the surface)."""
    n = co.shape[0]
    deg = np.bincount(edges.ravel(), minlength=n).astype(np.float64)
    deg[deg == 0] = 1.0
    c = co.copy()
    for _ in range(iters):
        acc = np.zeros_like(c)
        np.add.at(acc, edges[:, 0], c[edges[:, 1]])
        np.add.at(acc, edges[:, 1], c[edges[:, 0]])
        d = acc / deg[:, None] - c
        d -= normals * (d * normals).sum(1)[:, None]
        if fixed is not None:
            d[fixed] = 0
        c += amount * d
    return c


def mirror_map(co, tol=1e-4):
    """Index of each vertex's mirror partner across x = 0 (-1 when none within tol)."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(p, i)
    kd.balance()
    out = np.full(len(co), -1, dtype=np.int64)
    for i, p in enumerate(co):
        q, j, d = kd.find((-p[0], p[1], p[2]))
        if d is not None and d < tol:
            out[i] = j
    return out


def symmetrize(co, mm):
    """Average each vertex with its mirror partner (x mirrored)."""
    c = co.copy()
    ok = mm >= 0
    p = co[mm[ok]].copy()
    p[:, 0] *= -1
    c[ok] = 0.5 * (co[ok] + p)
    c[np.abs(c[:, 0]) < 1e-7, 0] = 0.0
    centre = ok & (mm == np.arange(len(co)))
    c[centre, 0] = 0.0
    return c


# ---- review rendering (Workbench / EEVEE, background-safe) ---------------------------------------

def setup_workbench(scene, color_type="MATERIAL", bg=(0.20, 0.21, 0.23), cavity=False, light="STUDIO"):
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = light
    sh.color_type = color_type
    sh.show_cavity = cavity
    sh.cavity_type = "BOTH"
    sh.show_shadows = False
    sh.show_object_outline = False
    sh.show_backface_culling = False
    sh.background_type = "VIEWPORT"
    sh.background_color = bg
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = bg
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False


def camera(scene):
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("CAM_review", bpy.data.cameras.new("CAM_review"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.data.type = "ORTHO"
    return cam


def aim_ortho(scene, target, direction, ortho_scale, dist=30.0, clip_start=0.01):
    cam = camera(scene)
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    cam.data.ortho_scale = ortho_scale
    cam.data.clip_start = clip_start
    cam.data.clip_end = dist + 50.0
    return cam


def render_still(scene, path, res_x, res_y=None):
    scene.render.resolution_x, scene.render.resolution_y = res_x, res_y or res_x
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    ensure_dir(os.path.dirname(path))
    bpy.ops.render.render(write_still=True)
    return path


def add_wire_overlay(objs, thickness=0.0016, color=(0.03, 0.03, 0.05, 1.0)):
    """Wireframe-modifier copies of objs (drawn as geometry, so a Workbench render shows the edges)."""
    wires = []
    for o in objs:
        w = o.copy()
        w.data = o.data.copy()
        w.name = "WIRE_" + o.name
        w.modifiers.clear()
        w.parent = None
        w.matrix_world = o.matrix_world
        m = w.modifiers.new("wire", "WIREFRAME")
        m.thickness = thickness
        m.use_replace = True
        m.use_even_offset = True
        w.color = color
        for c in o.users_collection:
            c.objects.link(w)
        wires.append(w)
    return wires


def remove_objects(objs):
    for o in objs:
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def az_dir(az_deg, elev_deg=0.0):
    """Camera direction for azimuth az (0 = in front of the hero, who faces -Y; 90 = his left side)."""
    a, e = math.radians(az_deg), math.radians(elev_deg)
    return (math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))
