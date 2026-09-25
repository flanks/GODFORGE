"""Stage 2, Valdris only: conform the fitted hm08 body (s2_body_fit.py) into an UNDER-SUIT that fills his armour.

Valdris's stage-1 blockout is plate armour, not a body: its legs are hollow double-walled shells (a fit along the
normal lands on their inner wall) and its torso is the anvil, the pauldrons, the tassets and the fused cape. So the
shared fit only sets the proportions (landmark warp) and this step sets the girth:

  1. legs: per side, the blockout's OUTER envelope E(theta, z) around the leg's own section centre is sampled with
     rays from outside toward the axis (inside the cape and the loin cloth), median-filtered and smoothed; each leg
     vertex moves radially to E - inset(z) (clamped), blended out at the ankle (the foot keeps the landmark warp
     inside the sabaton) and at the crotch; the medial side never crosses the centre line;
  2. torso: per 2 cm slab the body's current half-width, front and back are mapped piecewise-linearly onto a target
     table (stage2_fit.json conform.torso, measured on the blockout's plate faces beside the anvil and under the
     cape, minus the plate thickness), blended out into the arms, the neck and the thighs;
  3. a light tangential relax of the moved region evens the quads; the mesh stays exactly symmetric.

  blender -b -P tools/blender/gf_hero/s2_valdris_body.py -- <body.blend> <retopo_start.blend> <stage2_fit.json> \
          <out.blend> [--report <json>]
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from s2lib import (connected_parts, get_co, get_edges, get_normals, log, mesh_stats, mirror_map, opt, read_json,  # noqa: E402
                   save_blend, script_args, set_co, symmetrize, tangential_relax, write_json)

argv = script_args(__doc__)
if len(argv) < 4:
    raise SystemExit(__doc__)
BODY, REF, FIT, OUT = (os.path.abspath(a) for a in argv[:4])
REPORT = opt(argv, "--report", None, str)
cfg = read_json(FIT)["conform"]
bpy.ops.wm.open_mainfile(filepath=BODY)
scene = bpy.context.scene
body = bpy.data.objects["BODY"]
me = body.data
with bpy.data.libraries.load(REF, link=False) as (src, dst):
    dst.objects = ["REF_blockout"]
ref = dst.objects[0]
scene.collection.objects.link(ref)
bvh = BVHTree.FromObject(ref, bpy.context.evaluated_depsgraph_get())
report = {"body": os.path.basename(BODY)}


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def gauss1d(a, sig, axis, periodic):
    r = max(1, int(3 * sig))
    w = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    w /= w.sum()
    n = a.shape[axis]
    out = np.zeros_like(a)
    for wk, d in zip(w, range(-r, r + 1)):
        if periodic:
            out += wk * np.roll(a, d, axis=axis)
        else:
            idx = np.clip(np.arange(n) + d, 0, n - 1)
            out += wk * np.take(a, idx, axis=axis)
    return out


co = get_co(me)
nv = len(co)
# the body proper (not the eyeballs)
import bmesh  # noqa: E402
bm = bmesh.new()
bm.from_mesh(me)
parts = sorted(connected_parts(bm), key=len)
main = np.zeros(nv, bool)
main[[v.index for v in parts[-1]]] = True
bm.free()
mm = mirror_map(co, tol=1e-4)
report["mirror_pairs_missing"] = int((mm[main] < 0).sum())
new = co.copy()

# ---- 1. legs ----------------------------------------------------------------------------------------------
lc = cfg["legs"]
ZS = np.arange(lc["z"][0], lc["z"][1] + 1e-9, lc["dz"])
TH = np.radians(np.arange(0.0, 360.0, lc["dtheta_deg"]))
leg_rep = {}
for side, sd in (("L", 1), ("R", -1)):
    legv = main & (co[:, 0] * sd > 0.0) & (co[:, 2] < lc["z"][1] + 0.08)
    # section centre per slab from the landmark-warped body
    C = np.zeros((len(ZS), 2))
    for i, z in enumerate(ZS):
        m = legv & (np.abs(co[:, 2] - z) < lc["dz"])
        C[i] = co[m][:, :2].mean(0) if m.any() else (C[i - 1] if i else (sd * 0.25, 0.0))
    C = np.stack([gauss1d(C[:, 0], 2.0, 0, False), gauss1d(C[:, 1], 2.0, 0, False)], 1)
    # the blockout's own leg centre per slab (the stance may be set wider than the blockout's: the envelope is
    # sampled around the blockout's leg and applied around ours)
    CB = C.copy()
    if lc.get("blockout_offset_x"):
        # a known stance difference (ours minus the blockout's, lateral, per height), from the landmarks
        ox = np.array(lc["blockout_offset_x"], dtype=np.float64)
        CB[:, 0] = C[:, 0] - sd * np.interp(ZS, ox[:, 0], ox[:, 1])
    elif lc.get("centre_from_blockout"):
        rco = get_co(ref.data)
        win = (rco[:, 0] * sd > 0.03) & (rco[:, 0] * sd < 0.62) & (rco[:, 1] < lc.get("blockout_y_max", 0.22)) & (rco[:, 1] > -0.5)
        for i, z in enumerate(ZS):
            m = win & (np.abs(rco[:, 2] - z) < lc["dz"])
            if m.sum() > 20:
                q = rco[m]
                CB[i] = ((np.percentile(q[:, 0], 3) + np.percentile(q[:, 0], 97)) / 2, (np.percentile(q[:, 1], 3) + np.percentile(q[:, 1], 97)) / 2)
        CB = np.stack([gauss1d(CB[:, 0], 3.0, 0, False), gauss1d(CB[:, 1], 3.0, 0, False)], 1)
    E = np.full((len(ZS), len(TH)), np.nan)
    for i, z in enumerate(ZS):
        for j, t in enumerate(TH):
            d = Vector((math.sin(t), -math.cos(t), 0.0))          # theta 0 = front (-Y), 90 = +X
            r0 = lc["ray_start"]
            if d.x * sd < -1e-3:                                  # medial: start on this leg's side of the centre line
                r0 = min(r0, (abs(CB[i, 0]) - 0.01) / abs(d.x))
            o = Vector((CB[i, 0], CB[i, 1], z)) + d * r0
            loc, n, idx, dist = bvh.ray_cast(o, -d, r0)
            if loc is not None:
                E[i, j] = r0 - dist
    raw_ok = float(np.isfinite(E).mean())
    E = np.where(np.isfinite(E), E, np.nanmedian(E, axis=1, keepdims=True))
    # median across theta (+-1) and z (+-2) drops plate lips, bolts and cloth strands; then smooth
    stack = [np.roll(np.take(E, np.clip(np.arange(len(ZS)) + dz, 0, len(ZS) - 1), axis=0), dt, axis=1)
             for dz in range(-2, 3) for dt in (-1, 0, 1)]
    E = np.median(np.stack(stack), axis=0)
    E = gauss1d(gauss1d(E, lc["smooth_z_cells"], 0, False), lc["smooth_theta_cells"], 1, True)
    inset = np.interp(ZS, [p[0] for p in lc["inset"]], [p[1] for p in lc["inset"]])
    rmin = np.interp(ZS, [p[0] for p in lc["r_min"]], [p[1] for p in lc["r_min"]])
    rmax = np.interp(ZS, [p[0] for p in lc["r_max"]], [p[1] for p in lc["r_max"]])
    R = np.clip(E * lc.get("radius_scale", 1.0) - inset[:, None], rmin[:, None], rmax[:, None])
    idx = np.nonzero(legv)[0]
    p = co[idx]
    zc = np.clip(p[:, 2], ZS[0], ZS[-1])
    cx = np.interp(zc, ZS, C[:, 0])
    cy = np.interp(zc, ZS, C[:, 1])
    dx, dy = p[:, 0] - cx, p[:, 1] - cy
    th = np.arctan2(dx, -dy) % (2 * math.pi)
    fz = (zc - ZS[0]) / lc["dz"]
    i0 = np.clip(np.floor(fz).astype(int), 0, len(ZS) - 2)
    tz = fz - i0
    ft = th / (TH[1] - TH[0])
    j0 = np.floor(ft).astype(int) % len(TH)
    j1 = (j0 + 1) % len(TH)
    tt = ft - np.floor(ft)
    Rv = (R[i0, j0] * (1 - tt) + R[i0, j1] * tt) * (1 - tz) + (R[i0 + 1, j0] * (1 - tt) + R[i0 + 1, j1] * tt) * tz
    r = np.hypot(dx, dy) + 1e-9
    w = smoothstep(lc["blend_bottom"][0], lc["blend_bottom"][1], p[:, 2]) * (1 - smoothstep(lc["blend_top"][0], lc["blend_top"][1], p[:, 2]))
    k = 1 + (Rv / r - 1) * w
    q = p.copy()
    q[:, 0] = cx + dx * k
    q[:, 1] = cy + dy * k
    q[:, 0] = sd * np.maximum(q[:, 0] * sd, lc["medial_min_abs_x"])
    new[idx] = q
    leg_rep[side] = {"blockout_centre_offset_x_m": [round(float(v), 3) for v in (C[::10, 0] - CB[::10, 0])],
                     "rays_hit_fraction": round(raw_ok, 3), "radius_m_by_z": {"%.2f" % z: [round(float(R[i].min()), 3), round(float(R[i].max()), 3)]
                                                                              for i, z in enumerate(ZS) if i % 5 == 0},
                     "verts": int(len(idx))}
report["legs"] = leg_rep

# ---- 2. torso ----------------------------------------------------------------------------------------------
tc = cfg["torso"]
tab = np.array(tc["slabs"], dtype=np.float64)           # z, half_width, front_y, back_y
arm_w = np.where(co[:, 2] > tc["arm_from_z"], 1 - smoothstep(tc["arm_abs_x"][0], tc["arm_abs_x"][1], np.abs(co[:, 0])), 1.0)
zw = smoothstep(tc["blend_bottom"][0], tc["blend_bottom"][1], co[:, 2]) * (1 - smoothstep(tc["blend_top"][0], tc["blend_top"][1], co[:, 2]))
tv = main & (zw > 0) & (arm_w > 0)
dzs = 0.02
ZT = np.arange(tab[0, 0], tab[-1, 0] + 1e-9, dzs)
cur = np.zeros((len(ZT), 3))
core = main & (arm_w > 0.95)
for i, z in enumerate(ZT):
    m = core & (np.abs(co[:, 2] - z) < dzs)
    if m.sum() < 6:
        cur[i] = cur[i - 1] if i else (0.2, -0.1, 0.1)
        continue
    q = co[m]
    cur[i] = (np.percentile(np.abs(q[:, 0]), 98), np.percentile(q[:, 1], 2), np.percentile(q[:, 1], 98))
cur = gauss1d(cur, 1.5, 0, False)
tgt = np.stack([np.interp(ZT, tab[:, 0], tab[:, k]) for k in (1, 2, 3)], 1)
idx = np.nonzero(tv)[0]
p = new[idx].copy()
zc = np.clip(p[:, 2], ZT[0], ZT[-1])
hw_c, fr_c, bk_c = (np.interp(zc, ZT, cur[:, k]) for k in range(3))
hw_t, fr_t, bk_t = (np.interp(zc, ZT, tgt[:, k]) for k in range(3))
cy_c, cy_t = (fr_c + bk_c) / 2, (fr_t + bk_t) / 2
if tc.get("mode") == "barrel":
    # every vertex onto a superellipse |x/a|^n + |y/b|^n = 1 (b = front or back depth) at its own angle around
    # the slab centre: a smooth barrel, the under-suit's shape under the cuirass (MakeHuman's muscle bumps would
    # only print through as lumps)
    ex = tc["exponent"]
    ang = np.arctan2(p[:, 1] - cy_c, p[:, 0])
    ca, sa = np.cos(ang), np.sin(ang)
    b = np.where(sa < 0, cy_t - fr_t, bk_t - cy_t)
    rr = 1.0 / (np.abs(ca / hw_t) ** ex + np.abs(sa / b) ** ex) ** (1.0 / ex)
    xq = rr * ca
    yq = cy_t + rr * sa
else:
    xq = p[:, 0] * hw_t / hw_c
    yq = np.where(p[:, 1] < cy_c, cy_t + (p[:, 1] - cy_c) * (cy_t - fr_t) / (cy_c - fr_c), cy_t + (p[:, 1] - cy_c) * (bk_t - cy_t) / (bk_c - cy_c))
ww = (zw * arm_w)[idx]
p[:, 0] += (xq - p[:, 0]) * ww
p[:, 1] += (yq - p[:, 1]) * ww
new[idx] = p
report["torso"] = {"verts": int(len(idx)), "current_by_z": {"%.2f" % z: [round(float(v), 3) for v in cur[i]] for i, z in enumerate(ZT) if i % 5 == 0},
                   "target_by_z": {"%.2f" % z: [round(float(v), 3) for v in tgt[i]] for i, z in enumerate(ZT) if i % 5 == 0}}

# ---- 2b. forearms: centre each slab on the arm axis and set its radius (the right forearm lies in the cannon
#          sleeve, whose axis is the grip frame's; hm08's forearm bulges above the axis near the elbow) -------
fa = cfg.get("forearm")
if fa:
    axis = np.array([fa["axis_y"], fa["axis_z"]])
    xs = np.arange(fa["abs_x"][0], fa["abs_x"][1] + 1e-9, 0.01)
    armv = main & (co[:, 2] > 1.5) & (np.abs(new[:, 0]) > fa["abs_x"][0] - 0.03) & (np.abs(new[:, 0]) < fa["abs_x"][1] + 0.03)
    rep_fa = {}
    for sd in (1, -1):
        m = armv & (new[:, 0] * sd > 0)
        idx = np.nonzero(m)[0]
        ax_ = np.abs(new[idx, 0])
        cen = np.zeros((len(xs), 2))
        rad = np.zeros(len(xs))
        for i, x in enumerate(xs):
            s = np.abs(ax_ - x) < 0.012
            q = new[idx[s]][:, 1:3]
            cen[i] = (q.max(0) + q.min(0)) / 2 if s.any() else axis
            rad[i] = np.linalg.norm(q - cen[i], axis=1).mean() if s.any() else fa["radius_m"][0]
        cen = np.stack([gauss1d(cen[:, 0], 1.5, 0, False), gauss1d(cen[:, 1], 1.5, 0, False)], 1)
        rad = gauss1d(rad, 1.5, 0, False)
        rt = np.interp(xs, fa["radius_x"], fa["radius_m"])
        w = smoothstep(fa["blend_in"][0], fa["blend_in"][1], ax_) * (1 - smoothstep(fa["blend_out"][0], fa["blend_out"][1], ax_))
        c_v = np.stack([np.interp(ax_, xs, cen[:, 0]), np.interp(ax_, xs, cen[:, 1])], 1)
        k = np.interp(ax_, xs, rt / rad)
        q = new[idx][:, 1:3]
        tgt_q = axis + (q - c_v) * k[:, None]
        new[idx, 1:3] = q + (tgt_q - q) * w[:, None]
        rep_fa["L" if sd > 0 else "R"] = {"centre_offset_before_m": [round(float(v), 4) for v in (cen[len(xs) // 3] - axis)],
                                         "mean_radius_before_m": [round(float(v), 4) for v in rad[::6]],
                                         "mean_radius_target_m": [round(float(v), 4) for v in rt[::6]]}
    report["forearm"] = rep_fa

# ---- 3. relax + symmetry ------------------------------------------------------------------------------------
moved = np.linalg.norm(new - co, axis=1) > 1e-5
set_co(me, symmetrize(new, mm))
me.update()
edges = get_edges(me)
rel = cfg.get("relax", {"iters": 4, "amount": 0.4})
fixed = ~(main & moved)
c2 = tangential_relax(get_co(me), get_normals(me), edges, iters=rel["iters"], amount=rel["amount"], fixed=fixed)
set_co(me, symmetrize(c2, mm))
report["moved_verts"] = int(moved.sum())
report["max_move_m"] = round(float(np.linalg.norm(get_co(me) - co, axis=1).max()), 4)
report["stats"] = mesh_stats(body)
log("conform", {k: v for k, v in report.items() if k in ("moved_verts", "max_move_m")})

# ---- 4. weapon attach frame on the forearm axis -------------------------------------------------------------
# s2_body_fit.py puts the frame origin at the mean of the hand vertices; the thumb hangs below the palm, so that
# mean sits ~2 cm under the forearm axis. The colossus_cannon's sleeve axis runs through its grip (the origin), so
# for Valdris the origin is the palm centre's x ON the forearm axis; the vertex mean is kept for reference.
hf = cfg.get("hand_frame_on_axis")
fitrep_path = opt(argv, "--fit-report", None, str)
if hf and fitrep_path:
    fr = read_json(fitrep_path)
    if "hand_frames_vertex_mean" not in fr:
        fr["hand_frames_vertex_mean"] = json.loads(json.dumps(fr["hand_frames"]))     # a copy, not an alias
    for side, f in fr["hand_frames_vertex_mean"].items():
        g = dict(f)
        g["origin"] = [f["origin"][0], hf["axis_y"], hf["axis_z"]]
        g["note"] = "origin = palm centre x on the forearm axis (s2_valdris_body.py); vertex mean in hand_frames_vertex_mean"
        fr["hand_frames"][side] = g
    write_json(fitrep_path, fr)
    report["hand_frames"] = fr["hand_frames"]
bpy.data.objects.remove(ref)
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
