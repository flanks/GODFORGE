"""Stage 4, Valdris: the cloth pass - bake the cape, loincloth and braids into every clip (headless Blender 5.2).

  blender -b -P tools/blender/gf_hero/s4_valdris_cloth.py -- [--only clip,clip]

Runs after s4_anim.py (which re-creates the actions without them). Valdris's x_cape (5 x 5), x_loin (3 x 3) and
x_beard (5 x 2) chains ride the torso rigidly unless something moves them, and GODFORGE's client has no cloth spring
yet, so a clip without them shows a cape like a board and legs striding through it. This pass is his per-hero
secondary-motion layer: it keys ONLY those chain bones (the shared library itself never keys an x_ bone,
docs/art/GF_HERO_SKELETON.md section 2; an engine spring may later replace these channels).

Per clip and chain bone, every frame:
  1. target: the direction a hanging chain takes under the apparent gravity at its pin (g minus the pin's acceleration,
     so a landing throws the cape forward and a jolt flips it up), plus drag against the clip's design travel (the run
     streams the cape back), ramped in along the chain from the torso-riding top row (as s3_valdris_cloth's hang);
  2. lag: a damped spring on that direction (natural frequency and damping per group: the heavy cape swings slowly,
     the braids quickly), warmed up over three cycles for a loop and made exactly periodic;
  3. clear: s3_valdris_cloth.ClothGroup's clear step on the posed mesh (every closed body and armour piece its own BVH):
     cloth vertices inside a piece or under the ground turn the chain bones out, least squares, per frame.
The chain bones' local rotations are written as LINEAR keys (a loop's last frame is its first). Output: the actions in
production/valdris_anim.blend, reports/anim/cloth.json (per clip: cloth vertices left inside after the clear, the
deepest, and how hard the chains move).
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
from s3_valdris_check import CLOTH  # noqa: E402
from s3_valdris_cloth import ClothGroup, Pieces, axis_angle, np_mat, ortho, rot_between, signed_depth  # noqa: E402

KEY = "valdris"
argv = script_args(__doc__)
ONLY = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
P = hero_paths(KEY)
BLEND = os.path.join(P["A"], "production", "%s_anim.blend" % KEY)
MAN_P = os.path.join(P["A"], "reports", "anim", "clips.json")
OUT_P = os.path.join(P["A"], "reports", "anim", "cloth.json")
FPS = 30.0
G = 9.81
T0 = time.time()

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
MAN = json.load(open(MAN_P, encoding="utf-8"))
SKIN = read_json(P["skin_cfg"])
body = bpy.data.objects["BODY"]
parts = {o.name: o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not body}
solid = [body] + [o for n, o in parts.items() if n not in CLOTH]


def chains(prefix, names, n):
    return [["%s%s_%02d" % (prefix, nm, i + 1) for i in range(n)] for nm in names]


def group_mask(ob, prefix):
    names = {g.index: g.name for g in ob.vertex_groups}
    return np.array([any(names[g.group].startswith(prefix) for g in v.groups) for v in ob.data.vertices])


rig_cfg = SKIN["rig"]
# group -> (ClothGroup, obstacles, dynamics): f natural frequency (Hz) at the top / bottom of a chain, zeta damping,
# drag: how far the design travel streams it back (1/s: tan(angle) = drag * speed / g), acc: share of the pin's
# acceleration it feels
GROUPS = {
    "cape": (ClothGroup(arm, parts["CAPE"], chains("x_cape_", rig_cfg["cape"]["names"], len(rig_cfg["cape"]["joints_z"]) - 1),
                        vmask=group_mask(parts["CAPE"], "x_cape"), gravity=0.8, margin=0.012, ground=0.0, iters=16),
             Pieces([o for o in solid if o.name != "BEARD"]),
             {"f": (2.4, 1.3), "zeta": 0.6, "drag": 0.9, "acc": 0.45, "cone": 40.0}),
    "loin": (ClothGroup(arm, parts["LOINCLOTH"], chains("x_loin_", rig_cfg["loin"]["names"], len(rig_cfg["loin"]["joints_z"]) - 1),
                        gravity=0.8, margin=0.008, ground=0.0, max_turn_deg=60.0, iters=16),
             Pieces([o for o in solid if o.name in ("BODY", "LEGS", "HIPS", "SABATONS")]),
             {"f": (3.2, 2.0), "zeta": 0.6, "drag": 0.8, "acc": 0.5, "cone": 45.0}),
    "braids": (ClothGroup(arm, parts["BEARD"], chains("x_beard_", [str(k) for k in range(1, 6)], 2),
                          vmask=group_mask(parts["BEARD"], "x_beard"), gravity=0.7, margin=0.006, ground=0.0, iters=24,
                          step_deg=12.0, max_turn_deg=80.0, gravity_ramp=0),
               Pieces([o for o in solid if o.name in ("BODY", "ANVIL", "CUIRASS", "PAULDRONS", "ARMS", "GAUNTLETS")]),
               {"f": (3.6, 3.6), "zeta": 0.6, "drag": 0.5, "acc": 0.6, "cone": 45.0}),
}
CHAIN_BONES = [b for g in GROUPS.values() for c in g[0].chains for b in c]
for _g in GROUPS.values():
    _g[0].length = {b: arm.data.bones[b].length for b in _g[0].bones}

# the meshes only need evaluating for the obstacles: keep the armature modifier on (evaluated_co reads it)
for pb in arm.pose.bones:
    if pb.name in CHAIN_BONES:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)


def clear_chain_fcurves(act):
    for b in CHAIN_BONES:
        for i in range(3):
            fc = act.fcurves.find('pose.bones["%s"].rotation_euler' % b, index=i) if hasattr(act, "fcurves") else None
            if fc is not None:
                act.fcurves.remove(fc)


def action_fcurves(act):
    """Blender 5.x layered actions: the channelbag of the armature slot."""
    for layer in act.layers:
        for strip in layer.strips:
            cb = strip.channelbag(act.slots[0])
            if cb is not None:
                return cb
    return None


def pin_points(grp, frames):
    """World head position of each chain's first bone per frame (the pin)."""
    return None


def cone(d, axis, deg):
    """d limited to within deg degrees of axis (a heavy cape never flips up over his back)."""
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


def targets(grp, dyn, mats, travel, loop):
    """Per chain bone, per frame: the lagged world hang direction.
    mats[f][bone] = armature-space 4x4 of the chain parents (and the chain bones riding at rest basis)."""
    n = len(mats)
    out = {}
    tv = np.array([travel[0], travel[1], 0.0])
    for c in grp.chains:
        parent = grp.parent[c[0]]
        # the pin: the first chain bone's head riding its parent
        pin = np.array([(mats[f][parent] @ grp.rel[c[0]])[:3, 3] for f in range(n)])

        def acc(f):
            if loop:
                a, b = pin[(f - 1) % (n - 1)], pin[(f + 1) % (n - 1)]
            else:
                a, b = pin[max(f - 1, 0)], pin[min(f + 1, n - 1)]
            return (a - 2.0 * pin[f] + b) * FPS * FPS
        A = np.array([acc(f) for f in range(n)])
        # smooth the acceleration a little (1-2-1) and cap it at 2 g
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
            # apparent gravity direction: hanging "down" is the rest direction at g; the pin's acceleration and drag
            # against the travel tilt it
            gv = rest_d * G - dyn["acc"] * As - dyn["drag"] * tv[None, :]
            gv /= np.linalg.norm(gv, axis=1)[:, None]
            gv = np.array([cone(g_, rest_d, dyn["cone"]) for g_ in gv])
            dt = 1.0 / FPS
            cycles = 3 if loop else 1
            d = gv[0].copy()
            vel = np.zeros(3)
            seq = np.zeros((n, 3))
            for cyc in range(cycles):
                for f in range(n):
                    if loop and f == n - 1:
                        seq[f] = seq[0]
                        continue
                    t = gv[f]
                    for _sub in range(4):                  # 4 sub-steps per frame for stability
                        h = dt / 4.0
                        vel += (w * w * (t - d) - 2.0 * z * w * vel) * h
                        d = d + vel * h
                        d /= np.linalg.norm(d)
                    seq[f] = cone(d, rest_d, dyn["cone"] + 15.0)
            if loop:
                # exactly periodic: the warmed-up cycle ends a hair away from where it starts; spread that residual
                # over the cycle so the last frame IS the first
                res = seq[-2] + vel * dt - seq[0]
                for f in range(n):
                    seq[f] = seq[f] - res * (f / (n - 1.0))
                    seq[f] /= np.linalg.norm(seq[f])
                seq[-1] = seq[0]
            out[b] = seq
    return out


def solve_frame(grp, built, Mext, tdirs, fidx):
    """ClothGroup's hang (toward the lagged target directions, ramped in along the chain) + its clear step, from the
    parent matrices Mext. -> ({bone: 3x3 local basis}, report)."""
    basis = {b: np.eye(3) for b in grp.bones}
    hang = None
    for c in grp.chains:
        for k, b in enumerate(c):
            g = grp.gravity * (min(1.0, k / float(grp.ramp)) if grp.ramp else 1.0)
            M = grp.fk(Mext, basis)
            A = (M[grp.parent[b]] @ grp.rel[b])[:3, :3]
            d_f = A[:, 1] / np.linalg.norm(A[:, 1])
            d_t = tdirs[b][fidx]
            d = (1 - g) * d_f + g * d_t
            d /= np.linalg.norm(d)
            basis[b] = ortho(A.T @ rot_between(d_f, d) @ A)
    # the ground: a chain bone whose tail would go under it folds up about its head to lie along it (a kneeling or
    # floating hero's 1.8 m cape trails on the floor instead of hanging through it); its heading keeps its horizontal part,
    # or trails backward
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
    hang = {b: basis[b].copy() for b in grp.bones}
    wc = grp.W[:, [grp.bi[b] for b in grp.bones]].sum(1)
    movable = wc >= 0.35
    acc = {b: 0.0 for b in grp.bones}
    best = None
    hist = []
    for it in range(grp.iters + 1):
        M = grp.fk(Mext, basis)
        q = grp.skin(M)
        depth, push = signed_depth(q, built, grp.margin, grp.ground)
        bad = (depth > grp.margin + 0.001) & movable
        score = float(np.maximum(depth[movable] - grp.margin, 0).sum() + grp.turn_cost * sum(acc.values()))
        hist.append(int(bad.sum()))
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
    return best[1], hang


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


def smooth_deltas(hangs, clears, bones, loop):
    """The clear's correction per bone and frame (delta = cleared @ hang^T), dilated by one frame (the largest turn of
    f-1, f, f+1 survives) and smoothed [1, 2, 1] / 4 twice over time (cyclic for a loop): the per-frame clear jumps
    between rounds, and a cape must not pop. -> smoothed cleared bases."""
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
            cand = [(f - 1), f, (f + 1)]
            k = max(cand, key=lambda i: at(ang, i))
            dil.append(at(D, k))
        cur = dil
        for _ in range(2):
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


report = {"hero": KEY, "doc": __doc__.split("\n\n")[1].strip(), "groups": {g: {"chains": grp.chains, "dynamics": dyn}
                                                                         for g, (grp, _o, dyn) in GROUPS.items()},
          "clips": {}}
if ONLY and os.path.exists(OUT_P):
    report["clips"] = json.load(open(OUT_P, encoding="utf-8")).get("clips", {})
ext_bones = sorted({b for g in GROUPS.values() for b in g[0].all_bones if b not in g[0].bones} |
                   {g[0].parent[c[0]] for g in GROUPS.values() for c in g[0].chains})
for name in MAN["order"]:
    if ONLY and name not in ONLY:
        continue
    t = time.time()
    info = MAN["clips"][name]
    act = bpy.data.actions[info["action"]]
    arm.animation_data.action = act
    arm.animation_data.action_slot = act.slots[0]
    cb = action_fcurves(act)
    for b in CHAIN_BONES:                                   # a re-run replaces this pass's keys
        for i in range(3):
            fc = cb.fcurves.find('pose.bones["%s"].rotation_euler' % b, index=i)
            if fc is not None:
                cb.fcurves.remove(fc)
    for b in CHAIN_BONES:
        arm.pose.bones[b].rotation_euler = (0.0, 0.0, 0.0)
    n = info["frames"] + 1
    loop = info["loop"]
    travel = info.get("travel_mps", [0.0, 0.0])
    # pass 1: the parents and obstacles per frame
    mats, cos = [], []
    for f in range(n):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        mats.append({b: np_mat(arm.pose.bones[b].matrix) for b in ext_bones})
        cos.append({o.name: evaluated_co(o) for o in solid})
    res = {}
    eul = {}
    for g, (grp, obst, dyn) in GROUPS.items():
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
            bs, hg = solve_frame(grp, built, mats[f], td, f)
            hangs.append(hg)
            clears.append(bs)
            builts.append(built)
        bases = smooth_deltas(hangs, clears, grp.bones, loop)
        for f in range(n):
            r = penetration(grp, builts[f], mats[f], bases[f])
            worst = max(worst, r["inside_gt3mm"])
            deepest = max(deepest, r["deepest_mm"])
            frames_bad += 1 if r["inside_gt3mm"] else 0
        # local Euler per bone with compatibility, and how hard the chain moves (the largest second difference)
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
    log("%-26s %s (%.1fs)" % (info["action"], " | ".join("%s in %d deep %.0f acc %.1f" % (g, r["inside_gt3mm_max"], r["deepest_mm"],
                                                                                         r["accel_max_deg_per_frame2"]) for g, r in res.items()),
                                  time.time() - t))
arm.animation_data.action = None
for b in CHAIN_BONES:
    arm.pose.bones[b].rotation_euler = (0.0, 0.0, 0.0)
scene.frame_set(0)
report["cloth_keyed_bones"] = CHAIN_BONES
report["seconds"] = round(time.time() - T0, 1)
save_blend(BLEND)
write_json(OUT_P, report)
log("cloth pass done in %.0fs" % (time.time() - T0))
