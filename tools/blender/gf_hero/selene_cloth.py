"""Selene's cloth and crown layer: her x_ cloth chains hung, lagged and kept off her body, and the crown shards' bob
(stage-3 validation poses and the stage-4 cloth pass; numpy + mathutils, reads the rest rig through bpy only once).

Her eight cloth sheets each hang on ONE chain down their middle (stage 3: x_cape_{L,R}_01..04, x_mantle_{L,R}_01..02 on
the upper arms; x_panel_{L,R}_01..03, x_tabard_01..03, x_back_01..03 on the pelvis). The shared clips never key them
(docs/art/GF_HERO_SKELETON.md section 2) and the client has no cloth spring yet, so this layer poses them per frame, the way
Valdris's cloth pass does, with lighter maths (her cloth is thin and her body slim, so analytic capsules replace his
per-piece BVHs):

  1. hang: each bone's direction when it simply rides its parent, blended by `gravity` toward its REST direction turned
     with the body's heading (yaw of the chest for the capes and drapes, of the pelvis for the skirts), so the flare of the
     stage-2 cut survives a turn and a lean hangs down instead of swinging the cloth into the body;
  2. forces: that hang direction x g, minus drag x the pin's velocity (the clip's design travel + the pin's own motion:
     the run streams the capes back) and a share of the pin's acceleration (a landing throws them forward), ramped in
     along the chain; the chain points along the resultant;
  3. lag: a first-order filter on each bone's direction (a longer time constant at the hem), cyclic for loops (three
     warm-up cycles; the last frame is the first), started from a reference state for one-shots;
  4. clear: sample points of the sheet (its inner and outer edge and middle at each bone's middle and tail, in the bone's
     rest frame) are pushed out of capsules round the thighs, shins, feet, arms, hips and torso and above the ground; each
     push turns the bone about its head (a few rounds per bone, top to bottom).
The crown: x_crown_0k bob about their local Z (an arc of about 1.5 cm), out of phase, and turn a little about their own
axis; loops close exactly (a whole number of bob cycles; every bob is zero at frame 0).
"""
import math

import numpy as np

G = 9.81

# capsules: (name, bone, head -> tail share (from, to), radius). Radii are Selene's measured body + her armour / cloth
CAPSULES = [
    ("thigh_L", "thigh_L", (0.0, 1.0), 0.085), ("thigh_R", "thigh_R", (0.0, 1.0), 0.085),
    ("shin_L", "shin_L", (0.0, 1.0), 0.068), ("shin_R", "shin_R", (0.0, 1.0), 0.068),
    ("foot_L", "foot_L", (0.0, 1.0), 0.055), ("foot_R", "foot_R", (0.0, 1.0), 0.055),
    ("toe_L", "toe_L", (0.0, 1.0), 0.04), ("toe_R", "toe_R", (0.0, 1.0), 0.04),
    ("upperarm_L", "upperarm_L", (0.1, 1.0), 0.052), ("upperarm_R", "upperarm_R", (0.1, 1.0), 0.052),
    ("lowerarm_L", "lowerarm_L", (0.0, 1.0), 0.045), ("lowerarm_R", "lowerarm_R", (0.0, 1.0), 0.045),
    ("hand_L", "hand_L", (0.0, 1.0), 0.04), ("hand_R", "hand_R", (0.0, 1.0), 0.04),
    ("belly", "spine_01", (0.0, 1.0), 0.115), ("chest", "spine_03", (0.0, 0.75), 0.12),
    ("waist", "spine_02", (0.0, 1.0), 0.11), ("hips", "pelvis", (-0.2, 1.0), 0.13),
]
GROUPS = {
    # gravity: share of the rest hang; tau: lag (s) at the top / hem; drag (1/s): tan(angle) = drag x speed / g;
    # acc: share of the pin's acceleration felt; margin: clearance (m); colliders
    "cape": {"gravity": 0.92, "tau": (0.07, 0.16), "drag": 1.05, "acc": 0.25, "margin": 0.025, "frame": "spine_03",
             "cols": ["thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R", "upperarm_L", "upperarm_R",
                      "lowerarm_L", "lowerarm_R", "hand_L", "hand_R", "belly", "waist", "chest", "hips"]},
    "mantle": {"gravity": 0.85, "tau": (0.05, 0.09), "drag": 0.6, "acc": 0.3, "margin": 0.02, "frame": "spine_03",
               "cols": ["upperarm_L", "upperarm_R", "lowerarm_L", "lowerarm_R", "chest", "waist"]},
    "panel": {"gravity": 0.88, "tau": (0.05, 0.11), "drag": 0.85, "acc": 0.25, "margin": 0.025, "frame": "pelvis",
              "cols": ["thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R", "hips", "hand_L", "hand_R",
                       "lowerarm_L", "lowerarm_R"]},
    "tabard": {"gravity": 0.9, "tau": (0.05, 0.11), "drag": 0.85, "acc": 0.25, "margin": 0.025, "frame": "pelvis",
               "cols": ["thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R", "hips", "hand_L", "hand_R"]},
    "back": {"gravity": 0.9, "tau": (0.06, 0.13), "drag": 0.95, "acc": 0.25, "margin": 0.025, "frame": "pelvis",
             "cols": ["thigh_L", "thigh_R", "shin_L", "shin_R", "foot_L", "foot_R", "hips", "belly"]},
}
CROWN = ["x_crown_%02d" % k for k in range(1, 7)]
CROWN_PHASE = [0.0, 2.1, 4.2, 1.05, 3.15, 5.25]


def ortho(R3):
    U, _s, Vt = np.linalg.svd(R3)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] = -U[:, -1]
        R = U @ Vt
    return R


def np_mat(m):
    M = np.array([list(r) for r in m], dtype=np.float64)
    M[:3, :3] = ortho(M[:3, :3])
    return M


def rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.clip(a @ b, -1.0, 1.0))
    s = float(np.linalg.norm(v))
    if s < 1e-10:
        if c > 0:
            return np.eye(3)
        p = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(p) < 1e-6:
            p = np.cross(a, [0.0, 1.0, 0.0])
        return axis_angle(p, math.pi)
    return axis_angle(v, math.atan2(s, c))


def axis_angle(axis, ang):
    k = np.asarray(axis, dtype=np.float64)
    k = k / max(np.linalg.norm(k), 1e-12)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def yaw_of(R3, rest3):
    """Heading change (radians about +Z) of a bone from its rest: where its rest forward (-Y) now points, in XY."""
    f = (R3 @ rest3.T) @ np.array([0.0, -1.0, 0.0])
    return math.atan2(f[0], -f[1]) if abs(f[0]) + abs(f[1]) > 1e-6 else 0.0


def cap_arrays(caps, names):
    A = np.array([caps[n][0] for n in names])
    C = np.array([caps[n][1] for n in names])
    r = np.array([caps[n][2] for n in names])
    return A, C - A, r


def penetration(P, A, AB, r, margin, ground=0.012):
    """Per sample: (depth inside the nearest capsule (+ margin) or under the ground, push vector of that depth)."""
    rel = P[:, None, :] - A[None, :, :]
    t = np.clip((rel * AB[None]).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-12)[None], 0.0, 1.0)
    D = rel - AB[None] * t[..., None]
    dist = np.linalg.norm(D, axis=-1)
    dep = r[None] + margin - dist
    j = dep.argmax(1)
    i = np.arange(len(P))
    depth = dep[i, j]
    n = D[i, j] / np.maximum(dist[i, j], 1e-9)[:, None]
    g = ground - P[:, 2]
    use_g = g > depth
    depth = np.where(use_g, g, depth)
    n[use_g] = (0.0, 0.0, 1.0)
    depth = np.maximum(depth, 0.0)
    return depth, n * depth[:, None]


def deepest(P, A, AB, r, margin, ground=0.012):
    """(depth, push vector, point) of the deepest sample inside a capsule (+ margin) or under the ground; depth <= 0: clear."""
    rel = P[:, None, :] - A[None, :, :]
    t = np.clip((rel * AB[None]).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-12)[None], 0.0, 1.0)
    D = rel - AB[None] * t[..., None]
    dist = np.linalg.norm(D, axis=-1)
    dep = r[None] + margin - dist
    i, j = np.unravel_index(int(np.argmax(dep)), dep.shape)
    best, push, at = float(dep[i, j]), None, P[i]
    if best > 0:
        n = D[i, j] / max(dist[i, j], 1e-9)
        push = n * best
    g = ground - P[:, 2]
    k = int(np.argmax(g))
    if g[k] > best:
        best, push, at = float(g[k]), np.array([0.0, 0.0, float(g[k])]), P[k]
    return best, push, at


class SeleneCloth:
    """The rest rig, the chains and their sheet samples. Built once from the armature and the skinned cloth objects."""

    def __init__(self, arm, objects):
        import bpy  # noqa: F401  (called inside Blender)
        self.rest = {b.name: np_mat(b.matrix_local) for b in arm.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        self.length = {b.name: b.length for b in arm.data.bones}
        self.rel = {n: (np.linalg.inv(self.rest[p]) @ self.rest[n]) if p else self.rest[n].copy()
                    for n, p in self.parent.items()}
        names = [b.name for b in arm.data.bones]
        self.chains = {}
        for n in names:
            if not n.startswith("x_") or n.startswith(("x_crown", "x_knee")):
                continue
            pre = n.rsplit("_", 1)[0]
            self.chains.setdefault(pre, []).append(n)
        for pre in self.chains:
            self.chains[pre].sort()
        self.kind = {pre: pre.split("_")[1] for pre in self.chains}
        self.bones = [b for c in self.chains.values() for b in c]
        # sheet samples per chain bone: vertices whose strongest chain weight is that bone, at u in {0, .5, 1} and at the
        # bone's middle and tail rows, in the bone's rest frame
        self.samples = {b: np.zeros((0, 3)) for b in self.bones}
        for ob in objects:
            gname = {g.index: g.name for g in ob.vertex_groups}
            if "gf_mask" not in ob.data.attributes:
                continue
            a = ob.data.attributes["gf_mask"]
            col = np.empty(len(a.data) * 4)
            a.data.foreach_get("color", col)
            col = col.reshape(-1, 4)
            co = np.array([tuple(v.co) for v in ob.data.vertices])
            own = {}
            for v in ob.data.vertices:
                best = max(((g.weight, gname[g.group]) for g in v.groups if gname[g.group] in self.samples), default=None)
                if best:
                    own.setdefault(best[1], []).append(v.index)
            for b, idx in own.items():
                idx = np.array(idx)
                u, vv = col[idx, 1], col[idx, 0]
                pick = []
                for uu in (0.0, 0.5, 1.0):
                    for q in (0.5, 1.0):
                        vt = vv.min() + q * (vv.max() - vv.min())
                        k = np.argmin(np.abs(u - uu) * 2.0 + np.abs(vv - vt))
                        pick.append(idx[k])
                P = co[np.unique(pick)]
                Ri = np.linalg.inv(self.rest[b])
                self.samples[b] = P @ Ri[:3, :3].T + Ri[:3, 3]
        self.rest_dir = {b: self.rest[b][:3, 1] / np.linalg.norm(self.rest[b][:3, 1]) for b in self.bones}

    # -- one frame ---------------------------------------------------------------------------------------------------
    def capsules(self, M):
        out = {}
        for name, bone, (s0, s1), r in CAPSULES:
            h = M[bone][:3, 3]
            t = M[bone] @ np.array([0.0, self.length[bone], 0.0, 1.0])
            t = t[:3]
            out[name] = (h + (t - h) * s0, h + (t - h) * s1, r)
        return out

    def hang_dirs(self, pre, M, B):
        """Target world directions of a chain's bones from the hang rule (no forces), with the chain above posed by B."""
        g = GROUPS[self.kind[pre]]
        fb = g["frame"]
        psi = yaw_of(M[fb][:3, :3], self.rest[fb][:3, :3])
        Rz = axis_angle((0.0, 0.0, 1.0), psi)
        out = []
        for k, b in enumerate(self.chains[pre]):
            par = self.parent[b]
            Mp = M[par] if par in M else None
            A = (Mp @ self.rel[b])[:3, :3]
            d_f = A[:, 1] / np.linalg.norm(A[:, 1])
            d_r = Rz @ self.rest_dir[b]
            gg = g["gravity"] * (0.8 if k == 0 else 1.0)
            d = (1 - gg) * d_f + gg * d_r
            out.append(d / np.linalg.norm(d))
            # ride on the hang direction for the next bone's parent frame
            Bk = ortho(A.T @ rot_between(d_f, out[-1]) @ A)
            M = dict(M)
            M[b] = Mp @ self.rel[b] @ _h(Bk)
            B[b] = Bk
        return out

    def pose_chain(self, pre, M, dirs, caps, margin, iters=6, clear=True):
        """FK down a chain with the bones pointing along dirs, each turned out of the capsules (caps: cap_arrays) and the
        ground by the least-squares small rotation of all its penetrating samples (damped, capped per round). The first
        bone of a shoulder-hung sheet (cape, drape) is pinned under the armlet and not cleared. Returns (basis {bone:
        3x3}, M updated with the chain, bones left with a sample inside, world directions)."""
        A_, AB, r = caps
        B = {}
        M = dict(M)
        inside = 0
        wdir = []
        skip0 = self.kind[pre] in ("cape", "mantle")
        for k, b in enumerate(self.chains[pre]):
            Mp = M[self.parent[b]]
            Mr = Mp @ self.rel[b]
            A = Mr[:3, :3]
            head = Mr[:3, 3]
            d_f = A[:, 1] / np.linalg.norm(A[:, 1])
            R = rot_between(d_f, dirs[k])
            S = self.samples[b]
            if clear and not (skip0 and k == 0):
                left = False
                for _it in range(iters):
                    pts = S @ (R @ A).T + head
                    dep, P = penetration(pts, A_, AB, r, margin)
                    bad = dep > 1e-4
                    if not bad.any():
                        left = False
                        break
                    left = True
                    rr = pts[bad] - head
                    pp = P[bad]
                    tq = np.cross(rr, pp).sum(0)
                    if np.linalg.norm(tq) < 1e-10:
                        break
                    ax = tq / np.linalg.norm(tq)
                    lever = np.cross(ax, rr)
                    ang = float((lever * pp).sum() / max((lever * lever).sum(), 1e-9))
                    ang = max(0.0, min(math.radians(20.0), 0.8 * ang + math.radians(0.5)))
                    R = axis_angle(ax, ang) @ R
                if left:
                    pts = S @ (R @ A).T + head
                    if penetration(pts, A_, AB, r, margin)[0].max() > 0.004:
                        inside += 1
            elif not clear and not (skip0 and k == 0):
                pts = S @ (R @ A).T + head
                if penetration(pts, A_, AB, r, margin)[0].max() > margin + 0.01:     # really inside (1 cm past the skin)
                    inside += 1
            Bk = ortho(A.T @ R @ A)
            B[b] = Bk
            M[b] = Mr @ _h(Bk)
            wdir.append((R @ A)[:, 1] / np.linalg.norm((R @ A)[:, 1]))
        return B, M, inside, wdir


def _h(R3):
    H = np.eye(4)
    H[:3, :3] = R3
    return H


def solve_static(cloth, M):
    """One pose with no motion: hang + clear. Returns {bone: 3x3 local basis}, bones left with a sample inside."""
    caps = cloth.capsules(M)
    out, left = {}, 0
    M = dict(M)
    for pre in cloth.chains:
        g = GROUPS[cloth.kind[pre]]
        dirs = cloth.hang_dirs(pre, M, {})
        B, M, ins, _w = cloth.pose_chain(pre, M, dirs, cap_arrays(caps, g["cols"]), g["margin"])
        out.update(B)
        left += ins
    return out, left


def solve_clip(cloth, frames_M, fps, travel=(0.0, 0.0), loop=False, start=None, end=None, end_blend=6, start_dirs=None):
    """Per frame {bone: 3x3 local basis} for every chain of a clip. frames_M: per frame {bone: 4x4 armature-space} of the
    non-chain bones. start / end: {bone: 3x3} reference states (an upper-layer clip starts from and settles back into its
    base clip's frame 0). Returns (list of dicts, stats)."""
    n = len(frames_M)
    dt = 1.0 / fps
    trav = np.array([travel[0], travel[1], 0.0])
    period = n - 1
    res = [dict() for _ in range(n)]
    stats = {"inside_frames": 0, "max_turn_per_frame_deg": 0.0}
    caps = [cloth.capsules(M) for M in frames_M]
    for pre, bones in cloth.chains.items():
        g = GROUPS[cloth.kind[pre]]
        nb = len(bones)
        root = cloth.parent[bones[0]]
        pin = np.array([(M[root] @ cloth.rel[bones[0]])[:3, 3] for M in frames_M])

        def at(i):
            if loop:
                return pin[i % period]
            return pin[max(0, min(n - 1, i))]
        vel = np.array([(at(i + 1) - at(i - 1)) / (2 * dt) for i in range(n)]) + trav
        acc = np.array([(at(i + 1) - 2 * at(i) + at(i - 1)) / (dt * dt) for i in range(n)])
        acc = np.clip(acc, -15.0, 15.0)
        if not loop:              # a one-shot's end frames have no neighbour on one side: no acceleration there
            acc[0] = acc[-1] = 0.0
        # raw targets per frame and bone
        T = np.zeros((n, nb, 3))
        for f in range(n):
            hang = cloth.hang_dirs(pre, frames_M[f], {})
            for k in range(nb):
                ramp = (k + 1) / float(nb)
                F = hang[k] * G - g["drag"] * ramp * vel[f] - g["acc"] * ramp * acc[f]
                T[f, k] = F / np.linalg.norm(F)
        # lag (first-order, per bone: tau grows toward the hem)
        taus = [g["tau"][0] + (g["tau"][1] - g["tau"][0]) * (k / max(nb - 1, 1)) for k in range(nb)]
        D = np.zeros_like(T)
        for k in range(nb):
            a = 1.0 - math.exp(-dt / taus[k])
            x = T[0, k].copy()
            if loop:
                for _cyc in range(3):                     # warm up: the filter settles onto its periodic orbit
                    for f in range(period):
                        x = x + a * (T[f, k] - x)
                        x /= np.linalg.norm(x)
                for f in range(period):
                    x = x + a * (T[f, k] - x)
                    x /= np.linalg.norm(x)
                    D[f, k] = x
                D[period, k] = D[0, k]
            else:
                if start_dirs is not None:
                    x = start_dirs[pre][k].copy()
                D[0, k] = x
                for f in range(1, n):
                    x = x + a * (T[f, k] - x)
                    x /= np.linalg.norm(x)
                    D[f, k] = x
        # pose + clear per frame, then smooth the cleared directions over time (cyclic for loops) and pose again without a
        # clear: the pushes differ from frame to frame, and a jittering cape reads far worse than a graze
        Wd = np.zeros_like(D)
        for f in range(n):
            _B, _M, _ins, wd = cloth.pose_chain(pre, frames_M[f], [D[f, k] for k in range(nb)], cap_arrays(caps[f], g["cols"]),
                                                g["margin"])
            Wd[f] = np.array(wd)
        for _pass in range(2):
            S_ = Wd.copy()
            for f in range(n):
                acc_ = np.zeros((nb, 3))
                for o, w in ((-2, 1.0), (-1, 4.0), (0, 6.0), (1, 4.0), (2, 1.0)):
                    if loop:
                        g_ = (f + o) % period
                    else:
                        g_ = max(0, min(n - 1, f + o))
                    acc_ += w * Wd[g_]
                S_[f] = acc_ / np.linalg.norm(acc_, axis=1)[:, None]
            if loop:
                S_[period] = S_[0]
            Wd = S_
        prev = None
        for f in range(n):
            B, _M, ins, wd = cloth.pose_chain(pre, frames_M[f], [Wd[f, k] for k in range(nb)], cap_arrays(caps[f], g["cols"]),
                                              g["margin"], clear=False)
            stats["inside_frames"] += ins
            res[f].update(B)
            if prev is not None:
                for k in range(nb):
                    c = float(np.clip(prev[k] @ wd[k], -1.0, 1.0))
                    stats["max_turn_per_frame_deg"] = max(stats["max_turn_per_frame_deg"], math.degrees(math.acos(c)))
            prev = wd
    # upper-layer one-shots: start and end exactly on the reference state
    if start is not None or end is not None:
        for f in range(n):
            ws = 0.0 if start is None else max(0.0, 1.0 - f / float(end_blend))
            we = 0.0 if end is None else max(0.0, 1.0 - (n - 1 - f) / float(end_blend))
            for b in cloth.bones:
                Rm = res[f][b]
                for ref, w in ((start, ws), (end, we)):
                    if ref is None or w <= 0.0:
                        continue
                    w = w * w * (3 - 2 * w)
                    Rm = slerp3(Rm, ref[b], w)
                res[f][b] = Rm
    if loop:
        res[-1] = dict(res[0])
    return res, stats


def slerp3(A, B, t):
    """Rotation interpolation between two 3x3 rotations."""
    Rr = A.T @ B
    c = float(np.clip((np.trace(Rr) - 1.0) / 2.0, -1.0, 1.0))
    ang = math.acos(c)
    if ang < 1e-8:
        return A.copy()
    ax = np.array([Rr[2, 1] - Rr[1, 2], Rr[0, 2] - Rr[2, 0], Rr[1, 0] - Rr[0, 1]])
    if np.linalg.norm(ax) < 1e-9:
        return A if t < 0.5 else B
    return ortho(A @ axis_angle(ax, ang * t))


def crown_angles(n, fps, loop, verdict=0.0):
    """Per frame per shard (bob about local Z, spin about local Y, orbit about local X) in radians. Loops close: a whole
    number of bob cycles and every oscillation is zero at frame 0; one-shots fade the bob in and out (zero at both ends).
    verdict (0..1, a constant or per frame): the ultimate's crown, raised up the arc and, in a loop, swaying round the head
    (the right shards' local X points the other way, so their orbit is negated)."""
    T = (n - 1) / float(fps)
    if loop:
        cyc = max(1, int(round(T * 0.5)))
        w = 2 * math.pi * cyc / T if T > 0 else 0.0
    else:
        w = 2 * math.pi * 0.5
    out = []
    for f in range(n):
        t = f / float(fps)
        env = 1.0 if loop else math.sin(math.pi * f / max(n - 1, 1))
        vf = verdict[f] if isinstance(verdict, (list, tuple)) else verdict
        row = []
        for k in range(6):
            ph = CROWN_PHASE[k]
            sgn = 1.0 if k < 3 else -1.0
            bob = math.radians(7.0) * (math.sin(w * t + ph) - math.sin(ph)) * env
            spin = math.radians(12.0) * (math.sin(w * t + 0.5 * ph) - math.sin(0.5 * ph)) * env
            orbit = sgn * vf * math.radians(22.0) * math.sin(w * t) if loop else 0.0
            lift = sgn * vf * math.radians(14.0)
            row.append((bob + lift, spin, orbit))
        out.append(row)
    return out
