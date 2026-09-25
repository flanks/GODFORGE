"""UV layout for the stage-2 hero: one atlas, one texel density (s2_texture.py drives it).

Body: seams from face regions (head, torso, arm L/R, arm caps, leg L/R, foot L/R, sole L/R, ears, eyes)
plus one shortest-path cut per region so each island opens flat: back of the head, back of the torso,
underside of each arm, inside of each leg, back of each heel, one meridian per eyeball. Organic shells
(hair, beard, sash, belt, cloth, wraps) are split into their visible outer surface and their hidden
inner wall; faceted rigid parts (gauntlet pieces, skirt plates) are smart-projected by angle, the usual
choice for hard surface. Faces nobody can see (inner walls, plate undersides, caps inside rings) are
found by a ray along each face normal and packed at low density.
"""
import heapq
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from s2lib import log, select_only


def _face_regions_body(bm, cfg):
    """Region id per face of the body (see module doc)."""
    ears = set()
    ears_layer = None
    reg = {}
    dl = bm.verts.layers.deform.active
    ear_group = cfg.get("_ear_group_index")
    for f in bm.faces:
        c = f.calc_center_median()
        ax = abs(c.x)
        side = "L" if c.x > 0 else "R"
        in_ear = ear_group is not None and dl is not None and all(ear_group in v[dl] and v[dl][ear_group] > 0.5 for v in f.verts)
        if f.material_index == cfg["eye_zone"]:
            r = "eye_" + side
        elif in_ear:
            r = "ear_" + side
        elif ax > cfg.get("arm_cap_x", 9.0) and c.z > 1.5:
            r = "armcap_" + side
        elif ax > cfg.get("hand_x", 9.0) and c.z > 1.5:
            # hands: back-of-hand and palm islands (split along the sides of the fingers)
            r = ("handtop_" if f.normal.z >= 0.0 else "handpalm_") + side
        elif ax > cfg["arm_x"] and c.z > cfg["arm_min_z"]:
            r = "arm_" + side
        elif c.z > (cfg["head_z_front"] if c.y < 0.03 else cfg["head_z_back"]) and ax < 0.2:
            r = "head"
        elif c.z < cfg["sole_z"] and f.normal.z < -0.5:
            r = "sole_" + side
        elif c.z < cfg["foot_z"]:
            r = "foot_" + side
        elif c.z < cfg["leg_z"]:
            r = "leg_" + side
        else:
            r = "torso"
        reg[f.index] = r
    return reg


def _shortest_path(bm, start, goal, allowed):
    """Edge path (list of BMEdge) between two verts through allowed verts (Dijkstra on edge length)."""
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start.index, start)]
    seen = set()
    while heap:
        d, _, v = heapq.heappop(heap)
        if v in seen:
            continue
        seen.add(v)
        if v is goal:
            break
        for e in v.link_edges:
            w = e.other_vert(v)
            if w not in allowed or w in seen:
                continue
            nd = d + e.calc_length()
            if nd < dist.get(w, 1e9):
                dist[w] = nd
                prev[w] = (v, e)
                heapq.heappush(heap, (nd, w.index, w))
    if goal not in prev and goal is not start:
        return []
    path = []
    v = goal
    while v is not start:
        pv, e = prev[v]
        path.append(e)
        v = pv
    return path


def body_seams(obj, cfg):
    """Mark seams on the body object; returns {region: face count} and the cut lengths."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    eg = obj.vertex_groups.get("ears")
    cfg = dict(cfg)
    cfg["_ear_group_index"] = eg.index if eg else None
    reg = _face_regions_body(bm, cfg)
    for e in bm.edges:
        e.seam = False
        fs = e.link_faces
        if len(fs) == 2 and reg[fs[0].index] != reg[fs[1].index]:
            e.seam = True
    counts = {}
    for r in reg.values():
        counts[r] = counts.get(r, 0) + 1
    region_verts = {}
    for f in bm.faces:
        region_verts.setdefault(reg[f.index], set()).update(f.verts)
    # the same verts in index order: min() / max() below keep the first of equal keys, and a set's order
    # follows memory addresses, so a tie would pick a different cut end on every run
    region_list = {r: sorted(vs, key=lambda v: v.index) for r, vs in region_verts.items()}
    cuts = {}

    def boundary_verts(rname):
        return [v for v in region_list[rname] if any(e.seam or e.is_boundary for e in v.link_edges
                                                     if any(reg[f.index] == rname for f in e.link_faces))]

    def cut(rname, start_key, goal_key, goal_on_boundary=True):
        vs = region_verts.get(rname)
        if not vs:
            return
        bnd = boundary_verts(rname)
        s = min(bnd, key=start_key)
        cand = bnd if goal_on_boundary else region_list[rname]
        cand = [v for v in cand if v is not s]
        g = min(cand, key=goal_key)
        path = _shortest_path(bm, s, g, vs)
        for e in path:
            e.seam = True
        cuts[rname] = len(path)

    # head: from the back of the neck opening up over the back of the skull to the crown
    cut("head", lambda v: (abs(v.co.x) > 1e-4) * 10 - v.co.y, lambda v: -v.co.z, goal_on_boundary=False)
    # torso: back centre line, neck opening to the waist cut
    cut("torso", lambda v: (abs(v.co.x) > 1e-4) * 10 - v.co.z - v.co.y, lambda v: (abs(v.co.x) > 1e-4) * 10 + v.co.z - v.co.y)
    for sd, side in ((1, "L"), (-1, "R")):
        # arm: underside, shoulder opening to the cap ring
        cut("arm_" + side, lambda v: v.co.z + abs(abs(v.co.x) - cfg["arm_x"]) * 2, lambda v: v.co.z - abs(v.co.x) * 2)
        # leg: inside of the leg, top cut to the ankle
        cut("leg_" + side, lambda v: sd * v.co.x - v.co.z * 0.2, lambda v: sd * v.co.x + v.co.z * 0.5)
        # foot top: back of the heel, ankle opening to the sole edge
        cut("foot_" + side, lambda v: -v.co.y - v.co.z * 0.1, lambda v: -v.co.y + v.co.z * 0.5)
        # eyeball: meridian from the top pole to the bottom pole
        ev = region_verts.get("eye_" + side)
        if ev:
            top = max(region_list["eye_" + side], key=lambda v: v.co.z)
            bot = min(region_list["eye_" + side], key=lambda v: v.co.z)
            for e in _shortest_path(bm, top, bot, ev):
                e.seam = True
    bm.to_mesh(me)
    bm.free()
    return counts, cuts


def shell_seams(obj, bvh_all):
    """Organic shells: seams between the visible outer surface and the hidden inner wall / rim, found by
    face normals facing the body (the inner wall faces inward). Returns the number of seam edges."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    hidden = face_hidden(bm, bvh_all)
    n = 0
    for e in bm.edges:
        fs = e.link_faces
        e.seam = bool(len(fs) == 2 and hidden[fs[0].index] != hidden[fs[1].index])
        n += e.seam
    bm.to_mesh(me)
    bm.free()
    return n


def face_hidden(bm, bvh_all, reach=0.03, start=1e-4):
    """True for a face whose normal ray hits other geometry within `reach` (inner walls, undersides). The ray starts
    `start` metres off the face, so a face in a shallow concave crease does not count its own neighbours."""
    bm.faces.ensure_lookup_table()
    out = np.zeros(len(bm.faces), bool)
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        loc, nn, idx, dist = bvh_all.ray_cast(c + n * start, n, reach)
        out[f.index] = loc is not None
    return out


def build_bvh_all(objs):
    verts, polys = [], []
    off = 0
    for o in objs:
        me = o.data
        m = o.matrix_world
        verts.extend(m @ v.co for v in me.vertices)
        polys.extend([tuple(i + off for i in p.vertices) for p in me.polygons])
        off += len(me.vertices)
    return BVHTree.FromPolygons(verts, polys)


def unwrap_all(objs, body, smart_objs, shell_objs, density_hidden=0.3, margin_px=8, size=2048, hidden_reach=0.03,
               hidden_start=1e-4):
    """Unwrap every object into a fresh 'UVMap', equalise texel density, shrink hidden islands, pack.
    hidden_reach: how far (m) along its normal a face may find other geometry and still count as hidden."""
    for o in objs:
        me = o.data
        while me.uv_layers:
            me.uv_layers.remove(me.uv_layers[0])
        me.uv_layers.new(name="UVMap")
    for o in objs:
        select_only(o)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        if o in smart_objs:
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, area_weight=0.0,
                                     correct_aspect=True, scale_to_bounds=False)
        else:
            bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, correct_aspect=True, margin=0.0)
        bpy.ops.object.mode_set(mode="OBJECT")
    # equal texel density over all objects, then shrink the hidden faces' islands
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    bvh = build_bvh_all(objs)
    hidden_faces = 0
    for o in objs:
        me = o.data
        bm = bmesh.new()
        bm.from_mesh(me)
        hid = face_hidden(bm, bvh, reach=hidden_reach, start=hidden_start)
        uvl = bm.loops.layers.uv.active
        # islands through non-seam, uv-connected edges: shrink an island when most of it is hidden
        parent = list(range(len(bm.faces)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for e in bm.edges:
            fs = e.link_faces
            if len(fs) != 2 or e.seam:
                continue
            a, b = fs
            la = [l for l in a.loops if l.vert in e.verts]
            lb = [l for l in b.loops if l.vert in e.verts]
            ok = all(any((la_.vert is lb_.vert) and (la_[uvl].uv - lb_[uvl].uv).length < 1e-5 for lb_ in lb) for la_ in la)
            if ok:
                parent[find(a.index)] = find(b.index)
        isl = {}
        for f in bm.faces:
            isl.setdefault(find(f.index), []).append(f)
        for fl in isl.values():
            if np.mean([hid[f.index] for f in fl]) > 0.6:
                uvs = [l[uvl].uv for f in fl for l in f.loops]
                c = sum((u.copy() for u in uvs), Vector((0, 0))) / len(uvs)
                for f in fl:
                    for l in f.loops:
                        l[uvl].uv = c + (l[uvl].uv - c) * density_hidden
                hidden_faces += len(fl)
        bm.to_mesh(me)
        bm.free()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(udim_source="CLOSEST_UDIM", rotate=True, rotate_method="ANY", scale=True,
                            merge_overlap=False, margin_method="FRACTION", margin=margin_px / size,
                            pin=False, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return hidden_faces


def texel_density(objs, size):
    """Texel density per object in pixels per metre: median and 10th/90th percentile over its faces
    (islands shrunk on purpose because nobody sees them show up in the low tail)."""
    out = {}
    allv = []
    for o in objs:
        me = o.data
        uvl = me.uv_layers.active.data
        d = []
        for p in me.polygons:
            if p.area < 1e-8:
                continue
            uv = [uvl[i].uv for i in p.loop_indices]
            s = 0.0
            for k in range(1, len(uv) - 1):
                s += abs((uv[k].x - uv[0].x) * (uv[k + 1].y - uv[0].y) - (uv[k + 1].x - uv[0].x) * (uv[k].y - uv[0].y)) / 2
            d.append(size * math.sqrt(s / p.area))
        d = np.array(d)
        allv.append(d)
        out[o.name] = {"median": round(float(np.median(d)), 1), "p10": round(float(np.percentile(d, 10)), 1),
                       "p90": round(float(np.percentile(d, 90)), 1)}
    a = np.concatenate(allv)
    out["_all"] = {"median": round(float(np.median(a)), 1), "p10": round(float(np.percentile(a, 10)), 1),
                   "p90": round(float(np.percentile(a, 90)), 1)}
    return out


def zero_area_faces(objs):
    """Faces whose UV area is ~0 (a failed unwrap) per object, with where they are."""
    out = {}
    for o in objs:
        me = o.data
        uvl = me.uv_layers.active.data
        bad = []
        for p in me.polygons:
            uv = [uvl[i].uv for i in p.loop_indices]
            s = 0.0
            for k in range(1, len(uv) - 1):
                s += abs((uv[k].x - uv[0].x) * (uv[k + 1].y - uv[0].y) - (uv[k + 1].x - uv[0].x) * (uv[k].y - uv[0].y)) / 2
            if s < 1e-10 and p.area > 1e-7:
                bad.append([round(c, 3) for c in p.center])
        if bad:
            out[o.name] = {"count": len(bad), "first": bad[:5]}
    return out
