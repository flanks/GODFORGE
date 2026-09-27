"""Stage 4, Kael: the cloth pass - bake the duster's skirt, the loin cloth and the ghost-flame tatters into every clip
(headless Blender 5.2).

  blender -b -P tools/blender/gf_hero/s4_kael_cloth.py -- [--only clip,clip]

Runs after s4_anim.py (which re-creates the actions without them). Kael's x_coat (6 x 4), x_loin (3 x 3) and x_wisp
(5 x 3) chains ride the pelvis rigidly unless something moves them, and GODFORGE's client has no cloth spring yet, so a
clip without them shows a duster like a bell and legs striding through it. This pass is his per-hero secondary-motion
layer (the method of Valdris's s4_valdris_cloth.py, adapted to a coat that hangs all round the legs): it keys ONLY the
chain bones (the shared library never keys an x_ bone, docs/art/GF_HERO_SKELETON.md section 2).

Per clip and group, every frame:
  1. target: the direction a hanging chain takes under the apparent gravity at its pin (g minus the pin's acceleration)
     plus drag against the clip's design travel (the run streams the duster back), ramped in along the chain;
  2. lag: a damped spring on that direction, warmed up over three cycles for a loop and made exactly periodic;
  3. drape: the legs, boots, holster and the low-held gun stay on the body side of the skirt. Each coat chain has its
     own outward direction (the column's radial direction in the pelvis frame) and lateral band; each bone, top to
     bottom, turns outward just far enough that no leg point in its band lies outside it, like a rope laid over the
     legs; the loin cloth the same forward;
  4. clear: the cloth vertices inside a body, boot, gear or weapon piece (or under the ground) turn the chain bones out,
     least squares, per frame (s3_kael_cloth);
  5. smoothing of those corrections over time; upper-layer one-shots keep only their own cloth motion on top of their
     base clip's frame-0 cloth state and settle back into it (their first and last frames equal that reference pose);
  6. the tatters are solved last, on the coat's solved chains (each x_wisp chain hangs from the coat's last bone).
The Shadow Roll turns the body over: its chains follow the body more (gravity x ROLL_GRAVITY) so the duster wraps round
him instead of hanging through him. Keys are LINEAR on rotation_euler (a loop's last frame is its first). Output: the
actions in production/kael_anim.blend, reports/anim/cloth.json.
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import log, read_json, save_blend, script_args, write_json  # noqa: E402
from s3lib import evaluated_co, hero_paths  # noqa: E402
from s3_kael_cloth import ClothGroup, Pieces, axis_angle, np_mat, ortho, rot_between, signed_depth  # noqa: E402

KEY = "kael"
argv = script_args(__doc__)
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
BLEND = os.path.join(P["A"], "production", "%s_anim.blend" % KEY)
MAN_P = os.path.join(P["A"], "reports", "anim", "clips.json")
OUT_P = os.path.join(P["A"], "reports", "anim", "cloth.json")
FPS = 30.0
G = 9.81
ROLL_GRAVITY = {"shadow_roll": 0.35}
T0 = time.time()

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
MAN = json.load(open(MAN_P, encoding="utf-8"))
SKIN = read_json(P["skin_cfg"])
OB = {o.name: o for o in scene.objects if o.type == "MESH" and (o.parent == arm or o.name.startswith("PREVIEW_"))}
WEAPON = next((o for n, o in OB.items() if n.startswith("PREVIEW_")), None)
OBST = [OB["BODY"], OB["BOOTS"], OB["GEAR"]] + ([WEAPON] if WEAPON else [])


def chains(prefix, names, n):
    return [["%s%s_%02d" % (prefix, nm, i + 1) for i in range(n)] for nm in names]


def group_mask(ob, prefix):
    names = {g.index: g.name for g in ob.vertex_groups}
    return np.array([any(names[g.group].startswith(prefix) and g.weight > 0 for g in v.groups) for v in ob.data.vertices])


rig_cfg = SKIN["rig"]
cc = rig_cfg["coat"]
lc = rig_cfg["loin"]
# group -> (ClothGroup, obstacles, dynamics): f natural frequency (Hz) at the top / bottom of a chain, zeta damping, drag:
# how far the design travel streams it back (1/s), acc: share of the pin's acceleration it feels, cone: the largest angle
# from the rest direction (deg)
GROUPS = {
    "coat": (ClothGroup(arm, OB["COAT"], chains("x_coat_", cc["names"], len(cc["joints_z"])), vmask=group_mask(OB["COAT"], "x_coat"),
                        gravity=0.8, margin=0.012, ground=0.0, iters=16, max_turn_deg=70.0),
             Pieces(OBST),
             {"f": (1.9, 1.3), "zeta": 0.55, "drag": 1.0, "acc": 0.5, "cone": 50.0}),
    "loin": (ClothGroup(arm, OB["LOINCLOTH"], chains("x_loin_", lc["names"], len(lc["joints_z"]) - 1),
                        gravity=0.8, margin=0.008, ground=0.0, max_turn_deg=60.0, iters=16),
             Pieces([OB["BODY"], OB["BOOTS"], OB["GEAR"]]),
             {"f": (3.0, 2.0), "zeta": 0.6, "drag": 0.8, "acc": 0.5, "cone": 45.0}),
    "wisps": (ClothGroup(arm, OB["WISPS"], [["x_wisp_%d_%02d" % (k, i) for i in (1, 2, 3)] for k in range(1, 6)],
                         vmask=group_mask(OB["WISPS"], "x_wisp"), gravity=0.7, margin=0.006, ground=0.0, iters=16,
                         step_deg=12.0, max_turn_deg=75.0, gravity_ramp=0),
              Pieces([OB["BODY"], OB["BOOTS"]]),
              {"f": (3.2, 3.2), "zeta": 0.45, "drag": 1.1, "acc": 0.6, "cone": 60.0}),
}
COAT_BONES = [b for c in GROUPS["coat"][0].chains for b in c]
CHAIN_BONES = [b for g in GROUPS.values() for c in g[0].chains for b in c]
for _g in GROUPS.values():
    _g[0].length = {b: arm.data.bones[b].length for b in _g[0].bones}
for pb in arm.pose.bones:
    if pb.name in CHAIN_BONES:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)

# the drape obstacles: the leg vertices of the body (dominant bone on a leg), the boots, the gear below the belt, the gun
LEG_BONES = {"thigh_L", "thigh_R", "thigh_twist_L", "thigh_twist_R", "shin_L", "shin_R", "foot_L", "foot_R", "toe_L", "toe_R"}


def dominant_mask(ob, bones):
    names = {g.index: g.name for g in ob.vertex_groups}
    out = np.zeros(len(ob.data.vertices), bool)
    for v in ob.data.vertices:
        if v.groups:
            g = max(v.groups, key=lambda g_: g_.weight)
            out[v.index] = names[g.group] in bones
    return out


LEG_MASK = dominant_mask(OB["BODY"], LEG_BONES)
GEAR_LOW = np.array([v.co.z < 1.05 for v in OB["GEAR"].data.vertices])
th = np.radians(np.array(cc["theta_deg"]))
DRAPE = {  # group -> (frame bone, [(outward, lateral, band lo, band hi)] per chain (rest, Blender axes), margin)
    "coat": ("pelvis", [((math.sin(t), -math.cos(t), 0.0), (math.cos(t), math.sin(t), 0.0), -0.12, 0.12) for t in th], 0.035),
    "loin": ("pelvis", [((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), lo, hi) for lo, hi in ((-0.03, 0.07), (-0.07, 0.07), (-0.07, 0.03))], 0.02),
}
DRAPE_MAX_DEG = 75.0


def drape_points(g, co):
    if g not in DRAPE:
        return None
    pts = [co["BODY"][LEG_MASK], co["BOOTS"]]
    if g == "coat":
        pts.append(co["GEAR"][GEAR_LOW])
        if WEAPON is not None:
            w = co[WEAPON.name]
            pts.append(w[w[:, 2] < 1.2])
    else:
        pts.append(co["GEAR"][GEAR_LOW])
    return np.concatenate(pts)


def cone(d, axis, deg):
    c = float(np.clip(d @ axis, -1.0, 1.0))
    ang = math.acos(c)
    lim = math.radians(deg)
    if ang <= lim:
        return d
    perp = d - axis * c
    n = np.linalg.norm(perp)
    if n < 1e-9:
        return axis.copy()
    return axis * math.cos(lim) + perp / n * math.sin(lim)


def _turn(grp, Mext, basis, b, dn):
    M = grp.fk(Mext, basis)
    d = M[b][:3, 1] / np.linalg.norm(M[b][:3, 1])
    A = M[b][:3, :3]
    basis[b] = ortho(basis[b] @ (A.T @ rot_between(d, dn) @ A))


def drape(grp, g, Mext, basis, pts):
    """A rope laid over the legs, per chain with its own outward direction and lateral band (s4_valdris_cloth.drape
    generalised): each bone, top to bottom, keeps its hang unless a leg point in its band would lie outside the cloth
    line; then it turns outward just past that point (+ margin). Two passes: the second lifts each chain at least 0.75 x
    (0.45 x) as far as its neighbours one (two) chains away, so the cloth between chains never shears."""
    fb, specs, margin = DRAPE[g]
    Rt = Mext[fb][:3, :3] @ grp.rest[fb][:3, :3].T
    M0 = grp.fk(Mext, basis)
    D0 = {b: M0[b][:3, 1] / np.linalg.norm(M0[b][:3, 1]) for b in grp.bones}
    start = {b: basis[b].copy() for b in grp.bones}

    def need(j, b):
        out_r, lat_r, lo, hi = specs[j]
        out = Rt @ np.array(out_r)
        lat = Rt @ np.array(lat_r)
        M = grp.fk(Mext, basis)
        h = M[b][:3, 3]
        d = D0[b]
        r = pts - h
        u = r @ lat
        m = (u > lo) & (u < hi)
        e2 = out - d * float(out @ d)
        if not m.any() or np.linalg.norm(e2) < 0.35 or e2[2] < -0.5 * np.linalg.norm(e2):
            return 0.0, None
        e2 = e2 / np.linalg.norm(e2)
        a = r[m] @ d
        ccp = r[m] @ e2
        L = grp.length[b]
        sel = (a > 0.0) & (a < L + margin) & (ccp > -margin) & (ccp < 0.8)
        if not sel.any():
            return 0.0, e2
        R_ = np.hypot(a[sel], ccp[sel])
        phi = np.arctan2(ccp[sel], a[sel]) + np.arcsin(np.clip(margin / np.maximum(R_, margin), 0.0, 1.0))
        return min(float(phi.max()), math.radians(DRAPE_MAX_DEG)), e2

    def run(extra):
        got = {}
        for j, c in enumerate(grp.chains):
            out = Rt @ np.array(specs[j][0])
            for k, b in enumerate(c):
                ang, e2 = need(j, b)
                ang = max(ang, extra.get((j, k), 0.0))
                d = D0[b]
                if e2 is None:
                    e2 = out - d * float(out @ d)
                    e2 = e2 / np.linalg.norm(e2) if np.linalg.norm(e2) >= 0.35 and e2[2] >= -0.5 * np.linalg.norm(e2) else None
                if e2 is None:
                    ang = 0.0
                dn = d * math.cos(ang) + e2 * math.sin(ang) if ang > 1e-4 else d
                _turn(grp, Mext, basis, b, dn)
                got[(j, k)] = ang
        return got

    first = run({})
    if max(first.values(), default=0.0) <= 1e-4:
        for b in grp.bones:
            basis[b] = start[b]
        return 0.0
    lift = {}
    for (j, k), _a in first.items():
        nb = [0.75 * first.get((j + s_, k), 0.0) for s_ in (-1, 1)] + [0.45 * first.get((j + s_, k), 0.0) for s_ in (-2, 2)]
        lift[(j, k)] = max(nb)
    for b in grp.bones:
        basis[b] = start[b].copy()
    got = run(lift)
    return max(got.values())


def targets(grp, dyn, mats, travel, loop):
    """Per chain bone, per frame: the lagged world hang direction (s4_valdris_cloth.targets)."""
    n = len(mats)
    out = {}
    tv = np.array([travel[0], travel[1], 0.0])
    for c in grp.chains:
        parent = grp.parent[c[0]]
        pin = np.array([(mats[f][parent] @ grp.rel[c[0]])[:3, 3] for f in range(n)])

        def acc(f):
            if loop:
                a, b = pin[(f - 1) % (n - 1)], pin[(f + 1) % (n - 1)]
            else:
                a, b = pin[max(f - 1, 0)], pin[min(f + 1, n - 1)]
            return (a - 2.0 * pin[f] + b) * FPS * FPS
        A = np.array([acc(f) for f in range(n)])
        As = A.copy()
        for f in range(n):
            if loop:
                As[f] = (A[(f - 1) % (n - 1)] + 2 * A[f % (n - 1)] + A[(f + 1) % (n - 1)]) / 4.0
            else:
                As[f] = (A[max(f - 1, 0)] + 2 * A[f] + A[min(f + 1, n - 1)]) / 4.0
            m = np.linalg.norm(As[f])
            if m > G:
                As[f] *= G / m
        k = len(c)
        for i, b in enumerate(c):
            share = i / max(1.0, k - 1.0)
            fn = dyn["f"][0] + (dyn["f"][1] - dyn["f"][0]) * share
            w = 2.0 * math.pi * fn
            z = dyn["zeta"]
            rest_d = grp.rest[b][:3, 1] / np.linalg.norm(grp.rest[b][:3, 1])
            gv = rest_d * G - dyn["acc"] * As - dyn["drag"] * tv[None, :]
            gv /= np.linalg.norm(gv, axis=1)[:, None]
            gv = np.array([cone(g_, rest_d, dyn["cone"]) for g_ in gv])
            dt = 1.0 / FPS
            cycles = 3 if loop else 1
            d = gv[0].copy()
            vel = np.zeros(3)
            seq = np.zeros((n, 3))
            for _cyc in range(cycles):
                for f in range(n):
                    if loop and f == n - 1:
                        seq[f] = seq[0]
                        continue
                    t = gv[f]
                    for _sub in range(4):
                        h = dt / 4.0
                        vel += (w * w * (t - d) - 2.0 * z * w * vel) * h
                        d = d + vel * h
                        d /= np.linalg.norm(d)
                    seq[f] = cone(d, rest_d, dyn["cone"] + 15.0)
            if loop:
                res = seq[-2] + vel * dt - seq[0]
                for f in range(n):
                    seq[f] = seq[f] - res * (f / (n - 1.0))
                    seq[f] /= np.linalg.norm(seq[f])
                seq[-1] = seq[0]
            out[b] = seq
    return out


def ground_fold(grp, Mext, basis):
    """A chain bone whose tail would go under the ground folds up about its head to lie along it."""
    for c in grp.chains:
        for b in c:
            M = grp.fk(Mext, basis)
            h = M[b][:3, 3]
            d = M[b][:3, 1] / np.linalg.norm(M[b][:3, 1])
            L = grp.length[b]
            floor = grp.margin + 0.01
            if h[2] + L * d[2] >= floor:
                continue
            dz = max(-1.0, min(1.0, (floor - h[2]) / L))
            hz = np.array([d[0], d[1], 0.0])
            if np.linalg.norm(hz) < 1e-3:
                hz = np.array([0.0, 1.0, 0.0])
            hz /= np.linalg.norm(hz)
            dn = hz * math.sqrt(max(0.0, 1.0 - dz * dz)) + np.array([0.0, 0.0, dz])
            A = M[b][:3, :3]
            basis[b] = ortho(basis[b] @ (A.T @ rot_between(d, dn) @ A))


def clear(grp, built, Mext, basis):
    """Cloth vertices inside a piece or under the ground turn the chain bones out (least squares, capped per round); the
    best round is kept."""
    basis = {b: basis[b].copy() for b in grp.bones}
    wc = grp.W[:, [grp.bi[b] for b in grp.bones]].sum(1)
    movable = wc >= 0.35
    acc = {b: 0.0 for b in grp.bones}
    best = None
    for it in range(grp.iters + 1):
        M = grp.fk(Mext, basis)
        q = grp.skin(M)
        depth, push = signed_depth(q, built, grp.margin, grp.ground)
        bad = (depth > grp.margin + 0.001) & movable
        score = float(np.maximum(depth[movable] - grp.margin, 0).sum() + grp.turn_cost * sum(acc.values()))
        if best is None or score < best[0] - 1e-9:
            best = (score, {b: basis[b].copy() for b in grp.bones})
        if not bad.any() or it == grp.iters:
            break
        Pp = push * np.maximum(depth, 0)[:, None]
        for c in grp.chains:
            for b in c:
                w = grp.W[:, grp.bi[b]]
                sel = bad & (w > 0.05)
                if not sel.any() or acc[b] >= grp.max_turn:
                    continue
                h = M[b][:3, 3]
                r = q[sel] - h
                tq = (w[sel, None] * np.cross(r, Pp[sel])).sum(0)
                if np.linalg.norm(tq) < 1e-9:
                    continue
                ax = tq / np.linalg.norm(tq)
                lever = np.cross(ax, r) * w[sel, None]
                ang = float((lever * Pp[sel]).sum() / max((lever * lever).sum(), 1e-9))
                ang = min(grp.step, grp.max_turn - acc[b], max(0.0, 0.7 * ang))
                acc[b] += ang
                Wr = M[b][:3, :3]
                Aa = Wr @ basis[b].T
                basis[b] = ortho(Aa.T @ axis_angle(ax, ang) @ Wr)
    return best[1]


def solve_frame(grp, built, Mext, tdirs, fidx, gname, pts, gravity):
    basis = {b: np.eye(3) for b in grp.bones}
    for c in grp.chains:
        for k, b in enumerate(c):
            g = gravity * (min(1.0, k / float(grp.ramp)) if grp.ramp else 1.0)
            M = grp.fk(Mext, basis)
            A = (M[grp.parent[b]] @ grp.rel[b])[:3, :3]
            d_f = A[:, 1] / np.linalg.norm(A[:, 1])
            d_t = tdirs[b][fidx]
            d = (1 - g) * d_f + g * d_t
            d /= np.linalg.norm(d)
            basis[b] = ortho(A.T @ rot_between(d_f, d) @ A)
    ground_fold(grp, Mext, basis)
    hang = {b: basis[b].copy() for b in grp.bones}
    if pts is not None and drape(grp, gname, Mext, basis, pts) > 0.0:
        ground_fold(grp, Mext, basis)
    return clear(grp, built, Mext, basis), hang


def penetration(grp, built, Mext, basis):
    wc = grp.W[:, [grp.bi[b] for b in grp.bones]].sum(1)
    movable = wc >= 0.35
    q = grp.skin(grp.fk(Mext, basis))
    depth, _p = signed_depth(q, built, 0.0, grp.ground)
    return {"inside_gt3mm": int(((depth > 0.003) & movable).sum()), "deepest_mm": round(float(max(depth[movable].max(), 0.0)) * 1000, 1)}


def quat(Mx):
    return np.array(Matrix(Mx.tolist()).to_quaternion())


def qmat(q):
    from mathutils import Quaternion
    return np.array(Quaternion(q).normalized().to_matrix())


SMOOTH = {"coat": (2, 4), "loin": (2, 4), "wisps": (1, 2)}


def smooth_deltas(hangs, clears, bones, loop, dilate=1, passes=2):
    """The drape's and clear's correction per bone and frame, dilated and smoothed over time (a coat must not pop)."""
    n = len(hangs)
    out = [dict() for _ in range(n)]
    for b in bones:
        D = [quat(clears[f][b] @ hangs[f][b].T) for f in range(n)]
        for q in D:
            if q[0] < 0:
                q *= -1.0

        def at(seq, i):
            if loop:
                return seq[i % (n - 1)]
            return seq[max(0, min(n - 1, i))]
        ang = [2.0 * math.acos(min(1.0, abs(q[0]))) for q in D]
        dil = []
        for f in range(n):
            k = max(range(f - dilate, f + dilate + 1), key=lambda i: at(ang, i))
            dil.append(at(D, k))
        cur = dil
        for _ in range(passes):
            nxt = []
            for f in range(n):
                q = at(cur, f - 1) + 2.0 * at(cur, f) + at(cur, f + 1)
                nxt.append(q / np.linalg.norm(q))
            cur = nxt
        if loop:
            cur[-1] = cur[0]
        for f in range(n):
            out[f][b] = qmat(cur[f]) @ hangs[f][b]
    return out


def action_fcurves(act):
    for layer in act.layers:
        for strip in layer.strips:
            cb = strip.channelbag(act.slots[0])
            if cb is not None:
                return cb
    return None


def ref_bases(ref_clip):
    from mathutils import Euler
    cb = action_fcurves(bpy.data.actions[MAN["clips"][ref_clip]["action"]])
    out = {}
    for b in CHAIN_BONES:
        e = [0.0, 0.0, 0.0]
        for i in range(3):
            fc = cb.fcurves.find('pose.bones["%s"].rotation_euler' % b, index=i) if cb is not None else None
            if fc is not None:
                e[i] = fc.evaluate(0.0)
        out[b] = np.array(Euler(e, "XYZ").to_matrix())
    return out


def settle_on_reference(bases, bones, ref, n, compose=True):
    from mathutils import Quaternion
    k = max(2, min(8, (n - 1) // 2)) if compose else 2
    first = {b: bases[0][b].copy() for b in bones}
    for f in range(n):
        t = min(1.0, (n - 1 - f) / float(k)) if compose else min(1.0, f / float(k), (n - 1 - f) / float(k))
        w = t * t * (3.0 - 2.0 * t)
        for b in bones:
            own = ref[b] @ first[b].T @ bases[f][b] if compose else bases[f][b]
            qa = Matrix(ref[b].tolist()).to_quaternion()
            qb = Matrix(own.tolist()).to_quaternion()
            bases[f][b] = np.array(Quaternion(qa).slerp(qb, w).to_matrix())
    return bases


def write_keys(act, bones, eul_by_bone, n):
    cb = action_fcurves(act)
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    for b in bones:
        for i in range(3):
            path = 'pose.bones["%s"].rotation_euler' % b
            fc = cb.fcurves.find(path, index=i)
            if fc is not None:
                cb.fcurves.remove(fc)
            fc = act.fcurve_ensure_for_datablock(arm, path, index=i, group_name=b)
            fc.keyframe_points.add(n)
            co = []
            for f in range(n):
                co += [float(f), eul_by_bone[b][f][i]]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [lin] * n)
            fc.update()


report = {"hero": KEY, "doc": __doc__.split("\n\n")[1].strip(),
          "groups": {g: {"chains": grp.chains, "dynamics": dyn} for g, (grp, _o, dyn) in GROUPS.items()},
          "roll_gravity": ROLL_GRAVITY, "clips": {}}
if ONLY and os.path.exists(OUT_P):
    report["clips"] = json.load(open(OUT_P, encoding="utf-8")).get("clips", {})
ext_bones = sorted(({b for g in GROUPS.values() for b in g[0].all_bones if b not in g[0].bones} |
                    {g[0].parent[c[0]] for g in GROUPS.values() for c in g[0].chains}) - set(CHAIN_BONES))
OBJ_EVAL = sorted({o.name for o in OBST} | {"BODY", "BOOTS", "GEAR"})
for name in MAN["order"]:
    if ONLY and name not in ONLY:
        continue
    t = time.time()
    info = MAN["clips"][name]
    act = bpy.data.actions[info["action"]]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    cb = action_fcurves(act)
    for b in CHAIN_BONES:
        for i in range(3):
            fc = cb.fcurves.find('pose.bones["%s"].rotation_euler' % b, index=i)
            if fc is not None:
                cb.fcurves.remove(fc)
    for b in CHAIN_BONES:
        arm.pose.bones[b].rotation_euler = (0.0, 0.0, 0.0)
    n = info["frames"] + 1
    loop = info["loop"]
    travel = info.get("travel_mps", [0.0, 0.0])
    mats, cos = [], []
    for f in range(n):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        mats.append({b: np_mat(arm.pose.bones[b].matrix) for b in ext_bones})
        cos.append({nm: evaluated_co(bpy.data.objects[nm]) for nm in OBJ_EVAL})
    res = {}
    eul = {}
    for g, (grp, obst, dyn) in GROUPS.items():
        gravity = grp.gravity * ROLL_GRAVITY.get(name, 1.0)
        td = targets(grp, dyn, mats, travel, loop)
        worst, deepest, frames_bad = 0, 0.0, 0
        hangs, clears, builts = [], [], []
        for f in range(n):
            if loop and f == n - 1:
                hangs.append(hangs[0])
                clears.append(clears[0])
                builts.append(builts[0])
                continue
            built = obst.build(cos[f])
            bs, hg = solve_frame(grp, built, mats[f], td, f, g, drape_points(g, cos[f]), gravity)
            hangs.append(hg)
            clears.append(bs)
            builts.append(built)
        bases = smooth_deltas(hangs, clears, grp.bones, loop, *SMOOTH[g])
        if info.get("layer") == "upper" and not loop:
            bases = settle_on_reference(bases, grp.bones, ref_bases(info.get("base") or "idle_combat"), n, g != "wisps")
            if g != "wisps":
                def redo(f):
                    b0 = {b: bases[f][b].copy() for b in grp.bones}
                    pts = drape_points(g, cos[f])
                    if pts is not None and drape(grp, g, mats[f], b0, pts) > 0.0:
                        ground_fold(grp, mats[f], b0)
                    return clear(grp, builts[f], mats[f], b0)
                again = smooth_deltas(bases, [redo(f) for f in range(n)], grp.bones, False, *SMOOTH[g])
                from mathutils import Quaternion
                for f in range(n):
                    tt = min(1.0, f / 2.0, (n - 1 - f) / 2.0)
                    w = tt * tt * (3.0 - 2.0 * tt)
                    for b in grp.bones:
                        qa = Matrix(bases[f][b].tolist()).to_quaternion()
                        qb = Matrix(again[f][b].tolist()).to_quaternion()
                        bases[f][b] = np.array(Quaternion(qa).slerp(qb, w).to_matrix())
        for f in range(n):
            r = penetration(grp, builts[f], mats[f], bases[f])
            worst = max(worst, r["inside_gt3mm"])
            deepest = max(deepest, r["deepest_mm"])
            frames_bad += 1 if r["inside_gt3mm"] else 0
        if g == "coat":           # the tatters hang from the coat's solved chains
            for f in range(n):
                M = grp.fk(mats[f], bases[f])
                for b in COAT_BONES:
                    mats[f][b] = M[b]
        acc_max = 0.0
        for b in grp.bones:
            prev = None
            seq = []
            for f in range(n):
                e = Matrix(bases[f][b].tolist()).to_euler("XYZ", prev) if prev is not None else Matrix(bases[f][b].tolist()).to_euler("XYZ")
                seq.append(e)
                prev = e
            if loop:
                seq[-1] = seq[0].copy()
            eul[b] = seq
            for f in range(1, n - 1):
                acc_max = max(acc_max, max(abs(seq[f + 1][i] - 2 * seq[f][i] + seq[f - 1][i]) for i in range(3)))
        res[g] = {"inside_gt3mm_max": worst, "deepest_mm": round(deepest, 1), "frames_with_contact": frames_bad,
                  "accel_max_deg_per_frame2": round(math.degrees(acc_max), 2)}
    write_keys(act, CHAIN_BONES, eul, n)
    report["clips"][name] = {"action": info["action"], "frames": info["frames"], "loop": loop, "keyed_bones": len(CHAIN_BONES),
                             "groups": res, "seconds": round(time.time() - t, 1)}
    log("%-26s %s (%.1fs)" % (info["action"], " | ".join("%s in %d deep %.0f acc %.1f" % (
        g, r["inside_gt3mm_max"], r["deepest_mm"], r["accel_max_deg_per_frame2"]) for g, r in res.items()), time.time() - t))
arm.animation_data.action = None
for b in CHAIN_BONES:
    arm.pose.bones[b].rotation_euler = (0.0, 0.0, 0.0)
scene.frame_set(0)
report["cloth_keyed_bones"] = CHAIN_BONES
report["seconds"] = round(time.time() - T0, 1)
save_blend(BLEND)
write_json(OUT_P, report)
log("cloth pass done in %.0fs" % (time.time() - T0))
