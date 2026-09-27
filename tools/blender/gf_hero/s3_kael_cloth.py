"""Kael's cloth chains posed clear of his body: the numpy cloth library of the stage-4 cloth pass (s4_kael_cloth.py).

A copy of s3_valdris_cloth.py (Valdris's cape / loincloth / braid library, unchanged code) so that Kael's chain never
depends on another hero's files. For a pose it does what a cloth spring settles to, deterministically:

  1. hang: each chain bone, top-down, turns from the direction it has when it simply rides its posed parent toward its
     REST world direction by `gravity`, ramped in along the chain;
  2. clear: the cloth's own skinned vertices (numpy linear-blend skinning, the same as glTF / Bevy) are tested against
     the posed obstacle pieces (every closed piece its own BVH, signed distance from the nearest face) and the ground;
     every vertex closer than `margin` pushes the chain bones it is weighted to (least-squares small rotations, clamped,
     damped), for up to `iters` rounds; the best round is kept.
Kael's groups: the duster's skirt (x_coat, 6 x 4), the ghost-flame tatters (x_wisp, 5 x 3) and the loin cloth
(x_loin, 3 x 3).
"""
import math

import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from s2lib import get_co
from s3lib import components


def ortho(R3):
    """The nearest rotation (polar decomposition). Blender hands out float32 matrices; using a transpose as the inverse of
    one that is only nearly orthonormal compounds the error down a chain and, iterated, overflows."""
    U, _s, Vt = np.linalg.svd(R3)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] = -U[:, -1]
        R = U @ Vt
    return R


def np_mat(m):
    """A 4x4 rigid matrix from Blender, its rotation made exactly orthonormal in float64."""
    M = np.array([list(r) for r in m], dtype=np.float64)
    M[:3, :3] = ortho(M[:3, :3])
    return M


def rot_between(a, b):
    """3x3 rotation taking unit a to unit b (minimal)."""
    v = np.cross(a, b)
    c = float(a @ b)
    s = float(np.linalg.norm(v))
    if s < 1e-9:
        return np.eye(3)
    k = v / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    ang = math.atan2(s, c)
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


def axis_angle(axis, ang):
    k = axis / max(np.linalg.norm(axis), 1e-12)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)


class Pieces:
    """Closed pieces (connected components) of skinned objects, for inside / signed-distance tests on a posed state."""

    def __init__(self, objs, min_verts=8):
        self.items = []            # (object name, vertex idx, faces (local idx))
        for ob in objs:
            me = ob.data
            lab = components(me)
            polys = [tuple(p.vertices) for p in me.polygons]
            by = {}
            for p in polys:
                by.setdefault(int(lab[p[0]]), []).append(p)
            for k in range(int(lab.max()) + 1):
                idx = np.nonzero(lab == k)[0]
                if len(idx) < min_verts:
                    continue
                remap = {int(v): i for i, v in enumerate(idx)}
                faces = [tuple(remap[v] for v in p) for p in by.get(k, [])]
                self.items.append((ob.name, idx, faces))

    def build(self, co_by_obj):
        """Posed BVHs: [(lo, hi, bvh, label)]."""
        out = []
        for name, idx, faces in self.items:
            c = co_by_obj[name][idx]
            out.append((c.min(0), c.max(0), BVHTree.FromPolygons([tuple(p) for p in c], faces), "%s:%d" % (name, int(idx[0]))))
        return out


def signed_depth(points, built, margin, ground=None):
    """Per point: (depth = how far inside margin of the nearest obstacle surface or the ground, >0 needs a push; push unit
    vector). Only pieces whose box (+ margin) holds the point are tested."""
    n = len(points)
    depth = np.full(n, -1e9)
    push = np.zeros((n, 3))
    for lo, hi, bvh, _lab in built:
        cand = np.nonzero(np.all((points > lo - margin) & (points < hi + margin), axis=1))[0]
        for i in cand:
            loc, nrm, _fi, dist = bvh.find_nearest(Vector(points[i]))
            if loc is None:
                continue
            s = (Vector(points[i]) - loc).dot(nrm)
            sd = dist if s >= 0 else -dist
            d = margin - sd
            if d > depth[i]:
                depth[i] = d
                push[i] = np.array(nrm)
    if ground is not None:
        d = ground + margin - points[:, 2]
        m = d > depth
        depth[m] = d[m]
        push[m] = (0.0, 0.0, 1.0)
    return depth, push


class ClothGroup:
    """A cloth part on chains: the object, its vertices to solve, the chains (bone names top -> bottom)."""

    def __init__(self, arm, ob, chains, vmask=None, gravity=0.5, margin=0.01, ground=0.0, iters=24, step_deg=8.0,
                 max_turn_deg=70.0, gravity_ramp=2):
        self.arm, self.ob, self.chains = arm, ob, chains
        self.gravity, self.margin, self.ground, self.iters, self.step = gravity, margin, ground, iters, math.radians(step_deg)
        self.max_turn = math.radians(max_turn_deg)
        self.ramp = gravity_ramp         # bones over which gravity ramps in (0: full from the first bone, e.g. braids)
        self.turn_cost = 0.02            # metres of summed penetration one radian of extra turn is worth
        self.bones = [b for c in chains for b in c]
        me = ob.data
        co = get_co(me)
        self.vidx = np.arange(len(co)) if vmask is None else np.nonzero(vmask)[0]
        self.rest_co = co[self.vidx]
        names = {g.index: g.name for g in ob.vertex_groups}
        rows = []
        for i in self.vidx:
            v = me.vertices[int(i)]
            rows.append([(names[g.group], g.weight) for g in v.groups if g.weight > 0])
        self.rows = rows
        self.all_bones = sorted({b for r in rows for b, _w in r})
        self.bi = {b: j for j, b in enumerate(self.all_bones)}
        self.W = np.zeros((len(rows), len(self.all_bones)))
        for i, r in enumerate(rows):
            for b, w in r:
                self.W[i, self.bi[b]] = w
        self.rest = {b.name: np_mat(b.matrix_local) for b in arm.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        self.rel = {b: np.linalg.inv(self.rest[self.parent[b]]) @ self.rest[b] for b in self.bones}
        self.rest_inv = {b: np.linalg.inv(self.rest[b]) for b in self.all_bones}

    # -- FK / skinning -----------------------------------------------------------------------------------------------
    def fk(self, Mext, basis):
        M = dict(Mext)
        for c in self.chains:
            for b in c:
                B = np.eye(4)
                B[:3, :3] = basis[b]
                M[b] = M[self.parent[b]] @ self.rel[b] @ B
        return M

    def skin(self, M):
        out = np.zeros((len(self.rest_co), 3))
        h = np.hstack([self.rest_co, np.ones((len(self.rest_co), 1))])
        for b, j in self.bi.items():
            w = self.W[:, j]
            m = w > 0
            if not m.any():
                continue
            S = M[b] @ self.rest_inv[b]
            out[m] += w[m, None] * (h[m] @ S.T)[:, :3]
        return out

    # -- the solve -------------------------------------------------------------------------------------------------------
    def solve(self, built):
        pb = self.arm.pose.bones
        Mext = {b: np_mat(pb[b].matrix) for b in self.all_bones if b not in self.bones}
        for c in self.chains:
            Mext[self.parent[c[0]]] = np_mat(pb[self.parent[c[0]]].matrix)
        basis = {b: np.eye(3) for b in self.bones}
        # 1. hang: the gravity share ramps in along the chain (none on the first bone, full from the third), so the rows
        # pinned to the torso are never dragged into it
        for c in self.chains:
            for k, b in enumerate(c):
                g = self.gravity * (min(1.0, k / float(self.ramp)) if self.ramp else 1.0)
                M = self.fk(Mext, basis)
                A = (M[self.parent[b]] @ self.rel[b])[:3, :3]
                d_f = A[:, 1] / np.linalg.norm(A[:, 1])
                d_r = self.rest[b][:3, 1] / np.linalg.norm(self.rest[b][:3, 1])
                d = (1 - g) * d_f + g * d_r
                d /= np.linalg.norm(d)
                basis[b] = ortho(A.T @ rot_between(d_f, d) @ A)
        hist = []
        # only vertices the chains can move: those mostly on chain bones (the pinned top row rides the torso)
        wc = self.W[:, [self.bi[b] for b in self.bones]].sum(1)
        movable = wc >= 0.35
        acc = {b: 0.0 for b in self.bones}
        best = None
        for it in range(self.iters + 1):
            M = self.fk(Mext, basis)
            q = self.skin(M)
            depth, push = signed_depth(q, built, self.margin, self.ground)
            # only a vertex INSIDE an obstacle (or under the ground) steers the chains; its push asks for `margin` of clearance.
            # The score is the summed penetration plus a cost per radian turned, so a chain never swings far to trade one
            # contact for another; the best round is kept
            inside = (depth > self.margin + 0.001) & movable
            bad = inside
            score = float(np.maximum(depth[movable] - self.margin, 0).sum() + self.turn_cost * sum(acc.values()))
            hist.append(int(bad.sum()))
            if best is None or score < best[0] - 1e-9:
                best = (score, {b: basis[b].copy() for b in self.bones})
            if not bad.any() or it == self.iters:
                break
            P = push * np.maximum(depth, 0)[:, None]
            for c in self.chains:
                for b in c:
                    w = self.W[:, self.bi[b]]
                    sel = bad & (w > 0.05)
                    if not sel.any() or acc[b] >= self.max_turn:
                        continue
                    h = M[b][:3, 3]
                    r = q[sel] - h
                    tq = (w[sel, None] * np.cross(r, P[sel])).sum(0)
                    if np.linalg.norm(tq) < 1e-9:
                        continue
                    ax = tq / np.linalg.norm(tq)
                    lever = np.cross(ax, r) * w[sel, None]          # a vertex moves by its weight on the bone (LBS)
                    ang = float((lever * P[sel]).sum() / max((lever * lever).sum(), 1e-9))
                    ang = min(self.step, self.max_turn - acc[b], max(0.0, 0.7 * ang))
                    acc[b] += ang
                    Wr = M[b][:3, :3]
                    A = Wr @ basis[b].T                   # the bone's frame with an identity basis
                    basis[b] = ortho(A.T @ axis_angle(ax, ang) @ Wr)
        basis = best[1]
        M = self.fk(Mext, basis)
        q = self.skin(M)
        depth, _p = signed_depth(q, built, 0.0, self.ground)
        for b in self.bones:
            p = pb[b]
            p.rotation_mode = "XYZ"
            p.rotation_euler = Matrix(basis[b].tolist()).to_euler("XYZ")
        return {"iterations": len(hist), "violations_per_iteration": hist, "inside_after_mm_gt3": int((depth > 0.003).sum()),
                "deepest_mm": round(float(max(depth.max(), 0.0)) * 1000, 1)}
