"""Stage 2, step 3: fit the reduced hm08 body (s2_body_base.py) to the hero's sculpt reference.

This is the automated equivalent of wrapping a base topology onto a sculpt (the way Wrap-style tools
conform a clean mesh to a scan): the topology never changes, only vertex positions do.

  1. Landmark warp: a 3D thin-plate spline (kernel r) maps the MakeHuman landmarks (T-posed joint
     heads/tails, eyes, nose tip, skull top, heels, toes) onto the hero's measured landmarks
     (art/characters/<key>/stage2_fit.json). This sets the proportions: limb lengths, shoulder and
     hip width, neck length, head size, stance.
  2. Surface fit (non-rigid ICP), by body band (stage2_fit.json "fit.bands"): each vertex looks for the
     sculpt surface along its normal (both ways) and at its nearest point, and only accepts a surface
     that faces the same way (normal dot > 0.3). The displacements are smoothed over the mesh graph
     (so unfitted regions follow their neighbours), applied in damped steps with tangential
     relaxation (keeps the quads even) and mirrored every step (the mesh stays exactly symmetric).
     Hair, beard and brows on the sculpt are recognised by their dark sampled colour (src_col): there
     the skull/jaw is only kept a few centimetres inside the surface (the hair and beard are separate
     meshes on top), elsewhere on the head the face is pulled halfway to the sculpt.
  3. The forearms and hands are removed: they sit inside the rigid gauntlets (separate meshes), so the
     body ends in a capped ring inside the elbow band.
  4. Low-poly eyeballs (separate closed parts of the body mesh) sit in the eye sockets; they carry the
     emissive amber of the concept.

  blender -b -P tools/blender/gf_hero/s2_body_fit.py -- <base.blend> <mh_landmarks.json> <fit.json> \
          <retopo_start.blend> <out.blend> [--report <json>]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from s2lib import (get_co, get_edges, get_normals, log, mesh_stats, mirror_map, opt, read_json, save_blend,  # noqa: E402
                   script_args, select_only, set_co, smooth_field, symmetrize, tangential_relax, write_json)

argv = script_args(__doc__)
if len(argv) < 5:
    raise SystemExit(__doc__)
BASE, MH_LM, FIT, REF, OUT = (os.path.abspath(a) for a in argv[:5])
REPORT = opt(argv, "--report", None, str)

cfg = read_json(FIT)
mh = read_json(MH_LM)
bpy.ops.wm.open_mainfile(filepath=BASE)
scene = bpy.context.scene
body = bpy.data.objects["BODY_base_hm08"]
with bpy.data.libraries.load(REF, link=False) as (src, dst):
    dst.objects = ["REF_blockout"]
ref = dst.objects[0]
scene.collection.objects.link(ref)
report = {"base": os.path.basename(BASE), "reference": os.path.basename(REF)}


# ---- 1. thin-plate-spline landmark warp ------------------------------------------------------------
def mh_point(key):
    if "." in key:
        bone, end = key.split(".")
        return mh["joints"][bone][end]
    return mh[key]


pairs = []
for key, dst_p in cfg["landmarks"].items():
    if key.startswith("_"):
        continue
    pairs.append((mh_point(key), dst_p))
    for a, b in (("_l", "_r"),):
        if a in key:
            k2 = key.replace(a, b)
            q = list(dst_p)
            q[0] = -q[0]
            pairs.append((mh_point(k2), q))
S = np.array([p[0] for p in pairs], dtype=np.float64)
D = np.array([p[1] for p in pairs], dtype=np.float64)
n = len(S)
K = np.linalg.norm(S[:, None, :] - S[None, :, :], axis=2)
P = np.hstack([np.ones((n, 1)), S])
A = np.zeros((n + 4, n + 4))
A[:n, :n] = K + 1e-6 * np.eye(n)
A[:n, n:] = P
A[n:, :n] = P.T
rhs = np.zeros((n + 4, 3))
rhs[:n] = D
sol = np.linalg.solve(A, rhs)
W, Aff = sol[:n], sol[n:]


def tps(X):
    U = np.linalg.norm(X[:, None, :] - S[None, :, :], axis=2)
    return U @ W + np.hstack([np.ones((len(X), 1)), X]) @ Aff


me = body.data
co = tps(get_co(me))
set_co(me, co)
eyes = tps(np.array([mh["eye_l"], mh["eye_r"]]))
eye_scale = np.cbrt(abs(np.linalg.det(Aff[1:4])))
report["tps"] = {"landmarks": n, "residual_max_m": float(np.abs(tps(S) - D).max()), "global_scale": round(float(eye_scale), 4)}
log("TPS: %d landmarks, residual %.2e m, global scale %.3f" % (n, report["tps"]["residual_max_m"], eye_scale))

# ---- 2. surface fit ------------------------------------------------------------------------------------
dg = bpy.context.evaluated_depsgraph_get()
bvh = BVHTree.FromObject(ref, dg)
rme = ref.data
# per-face darkness of the sampled TRELLIS colour (hair / beard / brows are near-black on the concept)
lc = np.empty(len(rme.loops) * 4, dtype=np.float32)
rme.color_attributes["src_col"].data.foreach_get("color", lc)
lum_loop = lc.reshape(-1, 4)[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
ls = np.empty(len(rme.polygons), dtype=np.int64)
rme.polygons.foreach_get("loop_start", ls)
face_lum = (lum_loop[ls] + lum_loop[ls + 1] + lum_loop[ls + 2]) / 3.0
fc = np.empty(len(rme.polygons) * 3)
rme.polygons.foreach_get("center", fc)
fc = fc.reshape(-1, 3)
head_faces = face_lum[(fc[:, 2] > 1.85) & (np.abs(fc[:, 0]) < 0.2)]
# Otsu threshold on the head faces: skin vs hair/beard
hist, edges_h = np.histogram(head_faces, bins=64)
mids = (edges_h[:-1] + edges_h[1:]) / 2
best, thr = -1, float(np.median(head_faces))
for i in range(1, 64):
    w0, w1 = hist[:i].sum(), hist[i:].sum()
    if w0 == 0 or w1 == 0:
        continue
    m0, m1 = (hist[:i] * mids[:i]).sum() / w0, (hist[i:] * mids[i:]).sum() / w1
    v = w0 * w1 * (m0 - m1) ** 2
    if v > best:
        best, thr = v, mids[i]
face_dark = face_lum < thr
report["head_dark_threshold"] = round(float(thr), 4)
log("head colour threshold (Otsu) %.3f: %.0f%% of head faces dark" % (thr, 100 * (head_faces < thr).mean()))

bands = cfg["fit"]["bands"]
arm_max = cfg["fit"]["arm_fit_max_abs_x"]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def band_params(p):
    """weight, inset, contain, skin_only per vertex, blended 1.5 cm across band edges."""
    z = p[:, 2]
    wsum = np.zeros(len(p))
    out = {k: np.zeros(len(p)) for k in ("weight", "inset", "contain", "skin_only", "ignore_dark")}
    for b in bands:
        m = smoothstep(b["z"][0] - 0.015, b["z"][0] + 0.015, z) * (1 - smoothstep(b["z"][1] - 0.015, b["z"][1] + 0.015, z))
        if b is bands[0]:
            m = 1 - smoothstep(b["z"][1] - 0.015, b["z"][1] + 0.015, z)
        if b is bands[-1]:
            m = smoothstep(b["z"][0] - 0.015, b["z"][0] + 0.015, z)
        wsum += m
        for k in out:
            val = float(b.get(k, 0.0))
            if k == "weight" and "y_min" in b:
                val = val * smoothstep(b["y_min"] - 0.02, b["y_min"], p[:, 1])
            out[k] += m * val
    for k in out:
        out[k] /= np.maximum(wsum, 1e-9)
    ax = np.abs(p[:, 0])
    arm = (ax > 0.22) & (z > 1.5)
    out["weight"] = np.where(arm, out["weight"] * (1 - smoothstep(arm_max, arm_max + 0.06, ax)), out["weight"])
    return out


def query(p, nrm, dmax):
    """Sculpt surface along each vertex normal: (target, hit_normal, face, signed_depth, ok).
    signed_depth > 0 means the vertex is inside the sculpt by that much.
    TRELLIS.2 output is a thin double-walled shell (an outer wall facing out and an inner wall facing
    in, millimetres apart), so a nearest-point query or a backward ray from inside can land on the
    FAR side's inner wall, whose normal agrees with the vertex, and drag it across the body. Rule:
    the first hit ahead (+n, either wall) within dmax means the vertex is inside; only when nothing is
    ahead does a same-facing hit behind (-n) mean it is outside."""
    tgt = p.copy()
    hn = nrm.copy()
    face = np.full(len(p), -1, dtype=np.int64)
    depth = np.zeros(len(p))
    ok = np.zeros(len(p), bool)
    for i in range(len(p)):
        v = Vector(p[i])
        nv = Vector(nrm[i])
        loc, hnrm, idx, dist = bvh.ray_cast(v + nv * 1e-5, nv, dmax)
        sgn = 1.0
        if loc is None:
            loc, hnrm, idx, dist = bvh.ray_cast(v - nv * 1e-5, -nv, dmax)
            sgn = -1.0
            if loc is not None and hnrm.dot(nv) < 0.3:
                loc = None
        if loc is None:
            continue
        if hnrm.dot(nv) < 0:
            hnrm = -hnrm
        tgt[i] = loc
        hn[i] = hnrm
        face[i] = idx
        depth[i] = dist * sgn
        ok[i] = True
    return tgt, hn, face, depth, ok


co_tps = get_co(me)
edges = get_edges(me)
nv = len(me.vertices)
mm = mirror_map(get_co(me), tol=1e-4)
report["mirror_pairs_missing"] = int((mm < 0).sum())
co0 = get_co(me)
bp = band_params(co0)
# near-rigid regions (head, feet): per-axis scale + translation fitted by weighted least squares, so the
# small dense features (eye and mouth loops, ears, toes) keep their shape; blended in over a ramp
rig_cfg = cfg["fit"]["rigid"]
z0 = co0[:, 2]
s_head = smoothstep(rig_cfg["head"]["z_min"] - rig_cfg["head"]["ramp"], rig_cfg["head"]["z_min"], z0)
s_feet = 1 - smoothstep(rig_cfg["feet"]["z_max"], rig_cfg["feet"]["z_max"] + rig_cfg["feet"]["ramp"], z0)
s_rigid = np.clip(s_head + s_feet, 0, 1)
bp["weight"] *= (1 - s_rigid)


def scale_fit(co, goal, w, mask):
    """Per-axis scale about the region centroid + translation minimising sum w |S(p-c)+c+t - g|^2."""
    idx = np.nonzero(mask & (w > 0))[0]
    if len(idx) < 12:
        return co
    c = np.average(co[mask], axis=0)
    out = co.copy()
    Sx = np.ones(3)
    T = np.zeros(3)
    for a in range(3):
        X = co[idx, a] - c[a]
        Y = goal[idx, a] - c[a]
        ww = w[idx]
        M = np.array([[np.sum(ww * X * X), np.sum(ww * X)], [np.sum(ww * X), np.sum(ww)]])
        r = np.array([np.sum(ww * X * Y), np.sum(ww * Y)])
        sa, ta = np.linalg.solve(M + 1e-9 * np.eye(2), r)
        Sx[a], T[a] = np.clip(sa, 0.7, 1.4), ta
    out[mask] = (co[mask] - c) * Sx + c + T
    return out, Sx, T


schedule = [(0.12, 0.5, 24, 0.35)] * 8 + [(0.08, 0.5, 14, 0.3)] * 10 + [(0.05, 0.6, 8, 0.2)] * 10 + [(0.035, 0.9, 3, 0.1)] * 6
rigid_log = {}
for it, (dmax, alpha, sm, relax) in enumerate(schedule):
    me.update()
    co = get_co(me)
    nrm = get_normals(me)
    tgt, hn, face, depth, ok = query(co, nrm, dmax)
    dark = np.zeros(nv, bool)
    dark[ok] = face_dark[face[ok]]
    # -- free-form fit of the body bands
    w = np.where(ok, bp["weight"], 0.0)
    goal = tgt - hn * bp["inset"][:, None]
    # bands with `contain`: dark sculpt (beard / hair over the neck) keeps the skin that far inside it
    cont = (bp["contain"] > 0) & ok & dark
    shallow = cont & (depth < bp["contain"])
    goal = np.where(shallow[:, None], tgt - hn * bp["contain"][:, None], goal)
    w = np.where(cont & ~shallow, 0.0, w)
    w = np.where((bp["ignore_dark"] > 0.5) & dark, 0.0, w)
    d = (goal - co) * w[:, None]
    d = smooth_field(d, edges, sm, pin_w=w * 2.0)
    new = co + alpha * d * (1 - s_rigid)[:, None]
    new = tangential_relax(new, nrm, edges, iters=1, amount=relax)
    new = co + (new - co) * (1 - s_rigid)[:, None]
    # -- near-rigid head: face skin -> surface, skull/jaw under hair/beard -> `contain` inside it
    hc = rig_cfg["head"]
    hm = s_head > 0.5
    g = co.copy()
    wh = np.zeros(nv)
    skin = ok & ~dark & hm & (co[:, 1] < hc["face_front_y"])
    g[skin] = tgt[skin]
    wh[skin] = 1.0
    hair = ok & dark & hm
    shallow = hair & (depth < hc["contain"])
    g[shallow] = tgt[shallow] - hn[shallow] * hc["contain"]
    wh[shallow] = 1.0
    wh[hair & ~shallow] = hc["keep_weight"]
    res = scale_fit(co, g, wh, s_head > 0.01) if hc.get("mode") != "landmarks_only" else None
    if isinstance(res, tuple):
        fitted_head, Sh, Th = res
        new = new + (fitted_head - co) * s_head[:, None] * alpha
        rigid_log["head"] = {"scale": np.round(Sh, 4).tolist(), "translate_m": np.round(Th, 4).tolist()}
    # -- near-rigid feet, one fit per foot (the mirror step keeps them symmetric)
    fc_ = rig_cfg["feet"]
    for side in (1, -1):
        fm = (s_feet > 0.01) & (co[:, 0] * side > 0)
        gf = tgt - hn * fc_["inset"]
        wf = np.where(ok & fm, 1.0, 0.0)
        res = scale_fit(co, gf, wf, fm)
        if isinstance(res, tuple):
            fitted_foot, Sf, Tf = res
            new = new + (fitted_foot - co) * s_feet[:, None] * alpha
            rigid_log["foot_%s" % ("L" if side > 0 else "R")] = {"scale": np.round(Sf, 4).tolist(), "translate_m": np.round(Tf, 4).tolist()}
    co = symmetrize(new, mm)
    set_co(me, co)
    if it % 6 == 0 or it == len(schedule) - 1:
        fitted = ok & (bp["weight"] > 0.5)
        err = np.abs(depth)[fitted]
        log("fit it %2d dmax %.3f: %d/%d verts hit, body |dist| mean %.4f p95 %.4f, head %s" % (
            it, dmax, ok.sum(), nv, err.mean() if len(err) else 0, np.percentile(err, 95) if len(err) else 0, rigid_log.get("head")))
me.update()
co = get_co(me)
nrm = get_normals(me)
tgt, hn, face, depth, ok = query(co, nrm, 0.05)
fitted = ok & (bp["weight"] > 0.5)
err = np.abs(depth + bp["inset"])[fitted]
report["fit"] = {"iterations": len(schedule), "free_form_fitted_verts": int(fitted.sum()),
                 "mean_abs_dist_m": round(float(err.mean()), 5), "p95_abs_dist_m": round(float(np.percentile(err, 95)), 5),
                 "max_abs_dist_m": round(float(err.max()), 5), "rigid_regions": rigid_log}
log("fit result", report["fit"])

for ps in cfg["fit"].get("post_smooth", []):
    co = get_co(me)
    m = (smoothstep(ps["z"][0] - 0.03, ps["z"][0] + 0.02, co[:, 2]) * (1 - smoothstep(ps["z"][1] - 0.02, ps["z"][1] + 0.03, co[:, 2]))
         * (1 - smoothstep(ps["abs_x_max"] - 0.03, ps["abs_x_max"] + 0.02, np.abs(co[:, 0])))
         * (1 - smoothstep(ps["y_max"] - 0.03, ps["y_max"] + 0.02, co[:, 1])))
    deg = np.bincount(edges.ravel(), minlength=nv).astype(np.float64)
    for _ in range(ps["iters"]):
        acc = np.zeros_like(co)
        np.add.at(acc, edges[:, 0], co[edges[:, 1]])
        np.add.at(acc, edges[:, 1], co[edges[:, 0]])
        co = co + (acc / np.maximum(deg, 1)[:, None] - co) * (ps["amount"] * m)[:, None]
    co = symmetrize(co, mm)
    set_co(me, co)
    report.setdefault("post_smooth_verts", []).append(int((m > 0.05).sum()))

# eyes ride along with the surrounding head surface (mean displacement of the 24 nearest vertices)
disp = get_co(me) - co_tps
for k in range(len(eyes)):
    near = np.argsort(np.linalg.norm(co_tps - eyes[k], axis=1))[:24]
    eyes[k] = eyes[k] + disp[near].mean(0)

# ---- extra deformation loops (knees): split the edge ring that crosses each plane z = const ------------------
loops_added = []
for lp in cfg["fit"].get("extra_loops", []):
    bm = bmesh.new()
    bm.from_mesh(me)
    ring = [e for e in bm.edges
            if (e.verts[0].co.z - lp["z"]) * (e.verts[1].co.z - lp["z"]) < 0
            and min(abs(e.verts[0].co.x), abs(e.verts[1].co.x)) > lp["abs_x_min"]
            and max(e.verts[0].co.z, e.verts[1].co.z) < lp["z"] + 0.15]
    res = bmesh.ops.subdivide_edges(bm, edges=ring, cuts=1, use_grid_fill=True)
    # where the ring crosses a triangle the split leaves an n-gon: triangulate those, then pair triangles back into quads
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        tri = bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")
        bmesh.ops.join_triangles(bm, faces=tri["faces"], angle_face_threshold=math.radians(60),
                                 angle_shape_threshold=math.radians(70))
    bm.to_mesh(me)
    bm.free()
    me.update()
    loops_added.append({"z": lp["z"], "edges_split": len(ring)})
report["extra_loops"] = loops_added
log("extra loops", loops_added)
mm = mirror_map(get_co(me), tol=1e-4)          # the loops added vertices

# ---- 3. arms: thicken the landmark-warped forearms/hands (the sculpt has gauntlets there), or cut them ----------
lr = cfg["fit"].get("limb_radial")
if lr:
    co = get_co(me)
    sm_ = lr.get("smooth")  # smooth first (removes the warped MakeHuman forearm bumps), then enforce the radius profile
    if sm_:
        e_ = get_edges(me)
        dg_ = np.bincount(e_.ravel(), minlength=len(co)).astype(np.float64)
        axx = np.abs(co[:, 0])
        wgt = ((co[:, 2] > 1.5) & (axx > sm_["abs_x"][0]) & (axx < sm_["abs_x"][1])).astype(np.float64)
        wgt *= np.clip((axx - sm_["abs_x"][0]) / 0.04, 0, 1) * np.clip((sm_["abs_x"][1] - axx) / 0.03, 0, 1)
        for _ in range(sm_["iters"]):
            acc_ = np.zeros_like(co)
            np.add.at(acc_, e_[:, 0], co[e_[:, 1]])
            np.add.at(acc_, e_[:, 1], co[e_[:, 0]])
            co = co + (acc_ / np.maximum(dg_, 1)[:, None] - co) * (sm_["amount"] * wgt)[:, None]
    ax = np.abs(co[:, 0])
    axis = np.array([lr["axis_y"], lr["axis_z"]])
    yz = co[:, 1:3] - axis
    r = np.linalg.norm(yz, axis=1)
    arm = (co[:, 2] > 1.5) & (ax > lr["blend_from_abs_x"])
    # current mean radius per 1 cm slab along the arm, smoothed, vs the target profile
    xs = np.arange(lr["blend_from_abs_x"], lr["hand_from_abs_x"] + 0.011, 0.01)
    cur = np.array([r[arm & (np.abs(ax - x) < 0.012)].mean() if (arm & (np.abs(ax - x) < 0.012)).any() else np.nan for x in xs])
    cur = np.where(np.isnan(cur), np.nanmean(cur), cur)
    cur = np.convolve(np.pad(cur, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    tgt = np.interp(xs, lr["abs_x"], lr["radius_m"])
    fac = tgt / cur
    fac[xs < lr["abs_x"][1]] = 1.0 + (fac[xs < lr["abs_x"][1]] - 1.0) * np.clip((xs[xs < lr["abs_x"][1]] - lr["blend_from_abs_x"]) / (lr["abs_x"][1] - lr["blend_from_abs_x"]), 0, 1)
    sc = np.interp(ax, xs, fac)
    hand_ramp = np.clip((ax - lr["hand_from_abs_x"]) / 0.03, 0, 1)
    sc = sc * (1 - hand_ramp) + lr["hand_scale"] * hand_ramp
    co[arm, 1:3] = axis + yz[arm] * sc[arm, None]
    co = symmetrize(co, mm)
    set_co(me, co)
    report["limb_radial"] = {"verts": int(arm.sum()), "slab_scale_min_max": [round(float(fac.min()), 3), round(float(fac.max()), 3)],
                             "radius_before_m": [round(float(v), 4) for v in cur[::5]], "radius_target_m": [round(float(v), 4) for v in tgt[::5]]}
    log("limb radial", report["limb_radial"])
cut = cfg["fit"].get("arm_cut_abs_x")
if cut:
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    arm_faces = [f for f in bm.faces if all(abs(v.co.x) > cut and v.co.z > 1.5 for v in f.verts)]
    bmesh.ops.delete(bm, geom=arm_faces, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    caps = 0
    for side in (1, -1):
        ring = [e for e in bm.edges if e.is_boundary and e.verts[0].co.x * side > 0.3]
        if ring:
            res = bmesh.ops.holes_fill(bm, edges=ring, sides=0)
            for f in res["faces"]:
                bmesh.ops.poke(bm, faces=[f])
                caps += 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    report["arm_cut"] = {"abs_x": cut, "faces_removed": len(arm_faces), "caps": caps}
    log("arm cut at |x| > %.2f: %d faces removed, %d caps" % (cut, len(arm_faces), caps))

# ---- weapon attach frame per hand (palm centre, +Y along the fingers, +Z out of the back of the hand) ---------
hf = cfg["fit"].get("hand_frame")
if hf:
    co = get_co(me)

    def jpt(key):
        bone, end = key.split(".")
        return tps(np.array([mh["joints"][bone][end]]))[0]
    wx = abs(jpt(hf["wrist_joint"])[0])
    kx = abs(jpt(hf["knuckle_joint"])[0])
    frames = {}
    for side, sd in (("L", 1), ("R", -1)):
        m = (co[:, 0] * sd > wx) & (co[:, 0] * sd < kx) & (co[:, 2] > 1.5)
        o = co[m].mean(0)
        y_ax = np.array([sd, 0.0, 0.0])
        z_ax = np.array([0.0, 0.0, 1.0])
        x_ax = np.cross(y_ax, z_ax)
        frames[side] = {"origin": [round(float(v), 5) for v in o], "x_axis": x_ax.tolist(), "y_axis": y_ax.tolist(),
                        "z_axis": z_ax.tolist(), "wrist_abs_x": round(float(wx), 4), "knuckle_abs_x": round(float(kx), 4),
                        "hand_verts": int(m.sum())}
    report["hand_frames"] = frames
    log("hand frames", frames)

# ---- 4. eyeballs -----------------------------------------------------------------------------------------
eye_r = mh["eye_radius"] * eye_scale * 0.62
bm = bmesh.new()
bm.from_mesh(me)
for c in eyes:
    geom = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=eye_r)
    for v in geom["verts"]:
        v.co += Vector(c)
    ev = geom["verts"]
    for f in {f for v in ev for f in v.link_faces}:
        f.smooth = True
bm.to_mesh(me)
bm.free()
report["eyes"] = {"centres": [[round(float(x), 4) for x in e] for e in eyes], "radius_m": round(float(eye_r), 4)}

body.name = "BODY"
me.name = "BODY"
for p in me.polygons:
    p.use_smooth = True
st = mesh_stats(body)
report["stats"] = st
log("body", st)
ref.hide_render = True
ref.hide_set(True)
bpy.data.objects.remove(ref)
save_blend(OUT)
if REPORT:
    write_json(REPORT, report)
