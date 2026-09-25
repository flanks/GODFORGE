"""Stage 2 for a chassis weapon: the anvil_gauntlets pair (s2_gauntlet.py), open and closed-fist variants.

  blender -b -P tools/blender/gf_hero/s2_weapon.py -- <hero_body.blend> <stage2_weapon.json> <hero body_fit.json> \
          <out.blend> [--report <json>]

2026-09-25 user decision: weapons are separate models per chassis, attached to hand sockets, so any hero can
wield any chassis. The gauntlets are built around the hero they were designed on (Brax: the elbow ring and
the lava core clear his fitted forearm, the hand block and rock fingers enclose his bare hand), then each
mesh is re-expressed in that hand's weapon socket frame from the hero's body_fit report:
  origin = palm centre, +Y along the fingers, +Z out of the back of the hand, +X = Y x Z.
The object sits at that frame in the hero's T-pose (so review renders line up); its mesh data is in socket
space, so stage 3 parents it to weapon_L / weapon_R with an identity local transform.

Objects: GAUNTLET_L, GAUNTLET_R (open, like the approved concept), GAUNTLET_FIST_L, GAUNTLET_FIST_R.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import s2_gauntlet as GA  # noqa: E402
import s2_geom as G  # noqa: E402
from s2lib import (ROOT, get_co, get_collection, hex_rgb, log, mesh_stats, opt, read_json, save_blend,  # noqa: E402
                   script_args, srgb_to_linear, write_json)

argv = script_args(__doc__)
if len(argv) < 4:
    raise SystemExit(__doc__)
BODY, CFG, FITREP, OUT = (os.path.abspath(a) for a in argv[:4])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(CFG)
fit = read_json(FITREP)
frames = fit["hand_frames"]
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
body_co = get_co(body.data)
gc = cfg["gauntlet"]
YC, ZC = gc["axis_y"], gc["axis_z"]
report = {"weapon": cfg["weapon"], "designed_on": cfg["designed_on"], "objects": {}}

pal = {s["key"]: s["tones"] for s in read_json(os.path.join(ROOT, cfg["palette"]))["swatches"]}
zone_hex = {z: "#808080" for z in G.ZONES}
zone_hex.update({"rock": pal["gauntlet_rock"]["base"], "lava": pal["lava_glow"]["hot"], "bronze": pal["bronze"]["base"]})
mats = []
for zname in G.ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    c = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    m.diffuse_color = c
    mats.append(m)


def arm_radius(x0, x1):
    """Largest distance of the wearer's arm/hand surface from the gauntlet axis between |x| = x0 .. x1."""
    m = (np.abs(body_co[:, 0]) > x0) & (np.abs(body_co[:, 0]) < x1) & (body_co[:, 2] > 1.5)
    p = body_co[m]
    return float(np.sqrt((p[:, 1] - YC) ** 2 + (p[:, 2] - ZC) ** 2).max()) if len(p) else 0.1


def arm_extent(x0, x1):
    """Half-extents of the wearer's arm/hand about the gauntlet axis along Y and Z between |x| = x0 .. x1."""
    m = (np.abs(body_co[:, 0]) > x0) & (np.abs(body_co[:, 0]) < x1) & (body_co[:, 2] > 1.5)
    p = body_co[m]
    if not len(p):
        return 0.05, 0.05
    return float(np.abs(p[:, 1] - YC).max()), float(np.abs(p[:, 2] - ZC).max())


col = get_collection("WEAPON_%s" % cfg["weapon"])
for variant in ("open", "fist"):
    for side, sd in (("L", 1), ("R", -1)):
        bm = bmesh.new()
        G.ensure_mask(bm)
        rep = GA.build(bm, gc, sd, arm_radius, random.Random(cfg["seed"]), {}, variant=variant, arm_extent_fn=arm_extent)
        lay = bm.verts.layers.float_color.get(G.MASK_LAYER)
        G.set_mask(bm, [v for v in bm.verts if v[lay][3] < 0.5], 0.5)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        # the Voronoi plate caps are planar convex n-gons: triangulate them so the source is quads + tris only
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method="BEAUTY", ngon_method="BEAUTY")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        # socket frame (T-pose world) -> mesh data in socket space
        fr = frames[side]
        M = Matrix.Identity(4)
        for i, a in enumerate(("x_axis", "y_axis", "z_axis")):
            for r in range(3):
                M[r][i] = fr[a][r]
        for r in range(3):
            M[r][3] = fr["origin"][r]
        bm.transform(M.inverted())
        name = "GAUNTLET_%s%s" % ("FIST_" if variant == "fist" else "", side)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(name, me)
        ob.matrix_world = M
        for m in mats:
            me.materials.append(m)
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
        ob["gf_socket"] = "weapon_%s" % side
        ob["gf_variant"] = variant
        ob["gf_attach_frame"] = "origin = palm centre, +Y along the fingers, +Z out of the back of the hand"
        col.objects.link(ob)
        st = mesh_stats(ob)
        report["objects"][name] = {"stats": st, "socket": "weapon_%s" % side, "variant": variant, "build": rep,
                                   "socket_frame_tpose": fr}
        log("%-18s %5d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d" % (
            name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"]))
# only the weapon goes into this file
for o in list(bpy.data.objects):
    if not o.name.startswith("GAUNTLET"):
        bpy.data.objects.remove(o)
bpy.data.orphans_purge(do_recursive=True)
report["triangles_pair_open"] = sum(report["objects"]["GAUNTLET_%s" % s]["stats"]["triangles"] for s in "LR")
report["triangles_pair_fist"] = sum(report["objects"]["GAUNTLET_FIST_%s" % s]["stats"]["triangles"] for s in "LR")
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
