"""Stage 2 for a chassis weapon: the anvil_gauntlets pair (s2_gauntlet.py), open and closed-fist variants.

  blender -b -P tools/blender/gf_hero/s2_weapon.py -- <hero_body.blend> <stage2_weapon.json> <hero body_fit.json> \
          <retopo_start.blend> <out.blend> [--report <json>]

2026-09-25 user decision: weapons are separate models per chassis, attached to hand sockets, so any hero can
wield any chassis. The gauntlets are built on the stage-1 blockout's own gauntlets (the sculpt reference in
<retopo_start.blend>) and around the hero they were designed on:
  * per side, the blockout's radius E(theta, x) around the gauntlet axis is sampled (rays toward the axis),
    its bolts are median-filtered out, its smooth base B is taken, and the plate centres are the maxima of
    its lumps E - B, so the plates sit where the blockout's plates are;
  * the wearer's fitted forearm and hand set the clearances (elbow cuff, lava core, wrist band);
  * a copy of the blockout gauntlet, radially scaled like the build, is kept as BAKESRC_L / BAKESRC_R (the
    high-poly source of the tangent-space normal bake in s2_texture.py; never shipped).
Each mesh is then re-expressed in that hand's weapon socket frame from the hero's body_fit report:
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
from mathutils.bvhtree import BVHTree  # noqa: E402

import s2_gauntlet as GA  # noqa: E402
import s2_geom as G  # noqa: E402
from s2lib import (ROOT, get_co, get_collection, hex_rgb, log, mesh_stats, opt, read_json, save_blend,  # noqa: E402
                   script_args, srgb_to_linear, write_json)

argv = script_args(__doc__)
if len(argv) < 5:
    raise SystemExit(__doc__)
BODY, CFG, FITREP, REF, OUT = (os.path.abspath(a) for a in argv[:5])
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
report = {"weapon": cfg["weapon"], "designed_on": cfg["designed_on"], "objects": {}, "blockout_field": {}}
with bpy.data.libraries.load(REF, link=False) as (src, dst):
    dst.objects = ["REF_blockout"]
ref = dst.objects[0]
scene.collection.objects.link(ref)
dg = bpy.context.evaluated_depsgraph_get()
ref_bvh = BVHTree.FromObject(ref, dg)

pal = {s["key"]: s["tones"] for s in read_json(os.path.join(ROOT, cfg["palette"]))["swatches"]}
zone_hex = {z: "#808080" for z in G.ZONES}
zone_hex.update({"rock": pal["gauntlet_rock"]["base"], "lava": pal["lava_glow"]["hot"], "bronze": pal["bronze"]["base"]})
mats = []
for zname in G.ZONES:
    m = bpy.data.materials.get("Z_" + zname) or bpy.data.materials.new("Z_" + zname)
    m.diffuse_color = tuple(srgb_to_linear(hex_rgb(zone_hex[zname]))) + (1.0,)
    mats.append(m)


def arm_extent(x0, x1):
    """Half-extents of the wearer's arm/hand about the gauntlet axis along Y and Z between |x| = x0 .. x1."""
    m = (np.abs(body_co[:, 0]) > x0) & (np.abs(body_co[:, 0]) < x1) & (body_co[:, 2] > 1.5)
    p = body_co[m]
    if not len(p):
        return 0.05, 0.05
    return float(np.abs(p[:, 1] - YC - gc["build_offset"][0]).max()), float(np.abs(p[:, 2] - ZC - gc["build_offset"][1]).max())


# ---- the blockout gauntlet as a field ----------------------------------------------------------------------
bf = gc["blockout_field"]
THS = np.radians(np.arange(0.0, 360.0, bf["dtheta_deg"]))
XS = np.arange(bf["x"][0], bf["x"][1] + 1e-9, bf["dx"])


def shift_stack(A, ri, rj):
    """All shifts of A within +-ri (periodic, axis 0) and +-rj (edge-clamped, axis 1)."""
    out = []
    n = A.shape[1]
    for di in range(-ri, ri + 1):
        Ai = np.roll(A, di, axis=0)
        for dj in range(-rj, rj + 1):
            idx = np.clip(np.arange(n) + dj, 0, n - 1)
            out.append(Ai[:, idx])
    return np.stack(out)


def gauss(A, si, sj):
    def k(sig):
        r = max(1, int(3 * sig))
        w = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        return w / w.sum(), r
    w, r = k(si)
    A = sum(wk * np.roll(A, d, axis=0) for wk, d in zip(w, range(-r, r + 1)))
    w, r = k(sj)
    n = A.shape[1]
    return sum(wk * A[:, np.clip(np.arange(n) + d, 0, n - 1)] for wk, d in zip(w, range(-r, r + 1)))


def sample_field(sd):
    E = np.full((len(THS), len(XS)), np.nan)
    for j, x in enumerate(XS):
        for i, t in enumerate(THS):
            d = Vector((0.0, math.cos(t), math.sin(t)))
            o = Vector((sd * x, YC, ZC)) + d * 0.5
            loc, n, idx, dist = ref_bvh.ray_cast(o, -d, 0.5)
            if loc is not None:
                E[i, j] = 0.5 - dist
    col_med = np.nanmedian(E, axis=0)
    E = np.where(np.isnan(E), col_med[None, :], E)
    Em = np.median(shift_stack(E, bf["median"][0], bf["median"][1]), axis=0)      # bolts out
    B = gauss(Em, bf["base_sigma"][0], bf["base_sigma"][1])
    Ls = gauss(Em - B, bf["lump_sigma"][0], bf["lump_sigma"][1])
    # plate centres: local maxima of the lumps, greedy by height with a minimum spacing
    fp = gc["forearm_plates"]
    cand = []
    for i in range(len(THS)):
        for j in range(len(XS)):
            x = XS[j]
            if not (fp["seed_x"][0] <= x <= fp["seed_x"][1]) or Ls[i, j] <= 0:
                continue
            win = Ls[[(i - 1) % len(THS), i, (i + 1) % len(THS)]][:, max(0, j - 1):j + 2]
            if Ls[i, j] >= win.max():
                cand.append((Ls[i, j], THS[i], x))
    cand.sort(reverse=True)
    seeds = []
    Rf = fp["r_ref"]
    for h, t, x in cand:
        ok = True
        for (t2, x2) in seeds:
            dt = (t - t2 + math.pi) % (2 * math.pi) - math.pi
            if (dt * Rf) ** 2 + (x - x2) ** 2 < fp["seed_spacing"] ** 2:
                ok = False
                break
        if ok:
            seeds.append((t, x))
    return GA.Field(THS, XS, Em, B), seeds, float(np.abs(Em - B).max())


fields = {}
for side, sd in (("L", 1), ("R", -1)):
    f, seeds, amp = sample_field(sd)
    fields[side] = (f, seeds)
    report["blockout_field"][side] = {"plate_seeds": len(seeds), "lump_amplitude_m": round(amp, 4),
                                      "grid": [len(THS), len(XS)]}
    log("blockout field %s: %d plate seeds, lump amplitude %.3f m" % (side, len(seeds), amp))

# ---- bake sources: the blockout gauntlet, radially scaled like the build (never shipped) ------------------------
rs = gc["radial_scale"]
rco = get_co(ref.data)
for side, sd in (("L", 1), ("R", -1)):
    bm = bmesh.new()
    bm.from_mesh(ref.data)
    bm.verts.ensure_lookup_table()
    keep = (rco[:, 0] * sd > bf["bake_x_min"]) & (rco[:, 2] > 1.45)
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.nonzero(~keep)[0]], context="VERTS")
    oy, oz = gc["build_offset"]
    for v in bm.verts:
        k = float(np.interp(abs(v.co.x), rs["x"], rs["s"]))
        v.co.y = YC + oy + (v.co.y - YC) * k
        v.co.z = ZC + oz + (v.co.z - ZC) * k
    me = bpy.data.meshes.new("BAKESRC_" + side)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("BAKESRC_" + side, me)
    scene.collection.objects.link(ob)
    ob.hide_render = True
    report["blockout_field"][side]["bake_source_faces"] = len(me.polygons)

col = get_collection("WEAPON_%s" % cfg["weapon"])
for variant in ("open", "fist"):
    for side, sd in (("L", 1), ("R", -1)):
        bm = bmesh.new()
        G.ensure_mask(bm)
        field, seeds = fields[side]
        rep = GA.build(bm, gc, sd, field, seeds, random.Random(cfg["seed"]), {}, variant=variant, arm_extent_fn=arm_extent)
        lay = bm.verts.layers.float_color.get(G.MASK_LAYER)
        G.set_mask(bm, [v for v in bm.verts if v[lay][3] < 0.5], 0.5)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
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
        log("%-18s %5d tris  quads %.0f%%  parts %3d  boundary %d  non-manifold %d  %s" % (
            name, st["triangles"], 100 * st["quad_ratio"], st["parts"], st["boundary_edges"], st["nonmanifold_edges"],
            {k: v for k, v in rep.items() if k != "core_clearance_over_wearer_m"}))
# only the weapon (+ its bake sources) goes into this file
for o in list(bpy.data.objects):
    if not o.name.startswith(("GAUNTLET", "BAKESRC")):
        bpy.data.objects.remove(o)
bpy.data.orphans_purge(do_recursive=True)
report["triangles_pair_open"] = sum(report["objects"]["GAUNTLET_%s" % s]["stats"]["triangles"] for s in "LR")
report["triangles_pair_fist"] = sum(report["objects"]["GAUNTLET_FIST_%s" % s]["stats"]["triangles"] for s in "LR")
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
