"""Measurements for Valdris's stage-3 rig (imported by s3_valdris_poses.py and s3_valdris_limits.py; headless Blender).

Every armour piece is a separate CLOSED mesh, rigid on one bone (or one blended row), so "piece A cuts piece B" is exact:
a vertex of A inside B (ray parity, deeper than 3 mm; see inside()). The count that matters is what a pose ADDS to
the rest pose (shingled lames already overlap at rest by design). Pairs are sorted into
  * clipping: pieces of DIFFERENT regions (an arm plate in a pauldron, a gauntlet in the anvil, a braid in the chest, a
    thigh plate in a tasset...): the defects to fix;
  * sliding: two lames of the SAME region moving against each other (couter over vambrace, cuisse under tasset, greave
    into the sabaton cuff, cuirass bands): how real plate articulates; reported, and looked at in the close-ups;
  * suit: a plate inside the under-suit BODY, i.e. the mail pushing out through a plate (hands excluded: the glove
    fingers sit inside the lames by construction).
Regions: torso (cuirass, gorget, anvil), hips (fauld, tassets), shoulder_<S> (the pauldron stack with its arm lame),
arm_<S> (rerebraces to the gauntlet cuff), hand_<S> (back, knuckle guard, finger lames), leg_<S> (cuisses to shin
plate), foot_<S> (sabaton), beard, body.

The cannon (a sleeve weapon; open lathes, so no inside test) is tested with rays: a point is inside it when all 8 rays
perpendicular to the barrel axis (grip Y) hit it. Right-arm vertices enclosed with a fist at rest are the covered set;
a pose's poke-through is the covered vertices it uncovers; its cuts are vertices of other pieces it encloses.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import gf_hero_rig as R
from s2lib import get_co, get_edges, read_json
from s3lib import WeightMatrix, components, evaluated_co
from s3_valdris_cloth import Pieces

CLOTH = ("CAPE", "LOINCLOTH")
TOL = 0.003
PARITY_DIRS = [Vector((0.5377, 0.2869, 0.7929)).normalized(), Vector((-0.3571, -0.8012, 0.4804)).normalized()]


def inside(bvh, p):
    """p is inside the closed mesh and deeper than TOL: an odd number of crossings along BOTH of two fixed oblique rays
    (parity is exact for a closed mesh; two rays guard against a ray grazing an edge) and the nearest face farther than
    TOL. The nearest face's normal alone is not used: at the corners of the boxy plates it flips sign."""
    loc, _n, _fi, dist = bvh.find_nearest(p)
    if loc is None or dist < TOL:
        return False
    for d in PARITY_DIRS:
        o, n = p, 0
        for _k in range(64):
            hit = bvh.ray_cast(o, d)
            if hit[0] is None:
                break
            n += 1
            o = hit[0] + d * 1e-5
        if n % 2 == 0:
            return False
    return True


def region(pname):
    """Region of a piece 'OBJECT:PIECE_NAME'."""
    obj, _, n = pname.partition(":")
    if obj == "BODY":
        return "body"
    s = n[-1] if n[-2:] in ("_L", "_R") else ""
    if obj in ("CUIRASS", "ANVIL"):
        return "torso"
    if obj == "HIPS":
        return "hips"
    if obj == "BEARD":
        return "beard"
    if obj == "PAULDRONS":
        return "shoulder_" + s
    if obj == "ARMS":
        return "arm_" + s
    if obj == "GAUNTLETS":
        return "hand_" + s
    if obj == "LEGS":
        return "leg_" + s
    if obj == "SABATONS":
        return "foot_" + s
    return obj.lower()


class Checker:
    def __init__(self, arm, piece_table_path, cannon=None):
        self.arm = arm
        scene = bpy.context.scene
        self.body = bpy.data.objects["BODY"]
        self.parts = {o.name: o for o in scene.objects if o.type == "MESH" and o.parent == arm and o is not self.body}
        self.solid = [self.body] + [o for n, o in self.parts.items() if n not in CLOTH]
        self.cannon = cannon
        table = {p["id"]: p["name"] for p in read_json(piece_table_path)["piece_table"]}
        self.pieces = Pieces(self.solid)
        self.name, self.row, self.reg = [], [], []
        for name, idx, _faces in self.pieces.items:
            ob = bpy.data.objects[name]
            if name == "BODY":
                self.name.append("BODY" if len(idx) > 500 else "BODY_eye")
                self.row.append(None)
                self.reg.append("body")
                continue
            me = ob.data
            fp = np.empty(len(me.polygons), dtype=np.int32)
            me.attributes["gf_piece"].data.foreach_get("value", fp)
            v0 = int(idx[0])
            pid = next(int(fp[p.index]) for p in me.polygons if v0 in p.vertices)
            pn = "%s:%s" % (name, table[pid])
            self.name.append(pn)
            gn = {g.index: g.name for g in ob.vertex_groups}
            self.row.append(tuple(sorted((gn[g.group], round(g.weight, 3)) for g in me.vertices[v0].groups)))
            self.reg.append(region(pn))
        self.body_i = self.name.index("BODY")
        bones = [vg.name for vg in self.body.vertex_groups]
        Wb = WeightMatrix.read(self.body, bones).W
        self.dom = np.array([bones[j] for j in Wb.argmax(axis=1)])
        self.body_r_arm = np.isin(self.dom, [b for b in bones if b.endswith("_R") and b.split("_")[0] in
                                             ("lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky")])
        self.r_arm_pieces = {a for a, n in enumerate(self.name) if n.split(":")[-1].endswith("_R") and any(
            k in n for k in ("VAMBRACE", "WRIST_CUFF", "GAUNTLET_", "FINGER_"))}
        if cannon is not None:
            cme = cannon.data
            co = get_co(cme)
            self.ctree = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(p.vertices) for p in cme.polygons])
            self.clo, self.chi = co.min(0) - 0.01, co.max(0) + 0.01
            self.rays = [Vector((math.cos(a), 0.0, math.sin(a))) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
        # under-suit mesh data
        me = self.body.data
        lab = components(me)
        self.main = lab == np.bincount(lab).argmax()
        self.rest = get_co(me)
        ed = get_edges(me)
        self.ed = ed[self.main[ed[:, 0]] & self.main[ed[:, 1]]]
        self.rest_len = np.linalg.norm(self.rest[self.ed[:, 0]] - self.rest[self.ed[:, 1]], axis=1)
        tris = []
        for p in me.polygons:
            if self.main[p.vertices[0]]:
                vs = list(p.vertices)
                for i in range(1, len(vs) - 1):
                    tris.append((vs[0], vs[i], vs[i + 1]))
        self.tris = np.array(tris)
        self.rest_area = self._vert_area(self.rest)
        self.rest_vol = self._volume(self.rest)
        self.shoulder = {s: np.isin(self.dom, ["clavicle_" + s, "upperarm_" + s, "upperarm_twist_" + s]) for s in ("L", "R")}
        self.in_rest = None
        self.cov_ref = None
        self.cut_ref = {}

    # -- posed state -------------------------------------------------------------------------------------------------------
    def posed(self):
        out = {o.name: evaluated_co(o) for o in self.solid}
        for n in CLOTH:
            if n in self.parts:
                out[n] = evaluated_co(self.parts[n])
        return out

    def set_rest_reference(self, co_by):
        self.in_rest = self._inside_sets(co_by, self.pieces.build(co_by))

    def set_cannon_reference(self, co_by):
        self.cov_ref, self.cut_ref = self._cannon_sets(co_by)

    # -- plates ---------------------------------------------------------------------------------------------------------------
    def _inside_sets(self, co_by, built):
        lo = np.array([b[0] for b in built])
        hi = np.array([b[1] for b in built])
        out = {}
        for a, (name, idx, _f) in enumerate(self.pieces.items):
            if a == self.body_i or self.name[a] == "BODY_eye":
                continue
            pa = co_by[name][idx]
            alo, ahi = pa.min(0), pa.max(0)
            over = np.nonzero(np.all((lo <= ahi) & (hi >= alo), axis=1))[0]
            for b in over:
                if b == a or self.name[b] == "BODY_eye" or (self.row[b] is not None and self.row[b] == self.row[a]):
                    continue
                blo, bhi, bvh, _lab = built[b]
                cand = np.nonzero(np.all((pa > blo + TOL) & (pa < bhi - TOL), axis=1))[0]
                hit = set()
                for i in cand:
                    if inside(bvh, Vector(pa[i])):
                        hit.add(int(i))
                if hit:
                    out[(a, int(b))] = hit
        return out

    def kind(self, a, b):
        if b == self.body_i:
            return "suit"
        return "sliding" if self.reg[a] == self.reg[b] else "clipping"

    def plates_raw(self, co_by):
        """[(piece a, piece b, kind, new vertices, region a, region b)] for the pairs a pose adds."""
        ins = self._inside_sets(co_by, self.pieces.build(co_by))
        out = []
        for key, s in ins.items():
            d = s - self.in_rest.get(key, set())
            if not d:
                continue
            a, b = key
            k = self.kind(a, b)
            if k == "suit" and self.reg[a].startswith("hand"):
                continue
            out.append((self.name[a].split(":")[-1], self.name[b].split(":")[-1], k, len(d), self.reg[a], self.reg[b]))
        return out

    def plates(self, co_by, raw=None):
        cat = {"clipping": {}, "sliding": {}, "suit": {}}
        for na, nb, k, n, _ra, _rb in (raw if raw is not None else self.plates_raw(co_by)):
            nm = "%s -> %s" % (na, nb)
            cat[k][nm] = cat[k].get(nm, 0) + n
        out = {}
        for k, d in cat.items():
            out[k] = int(sum(d.values()))
            out[k + "_worst"] = sorted(d.items(), key=lambda kv: -kv[1])[:6]
        return out

    # -- cannon ---------------------------------------------------------------------------------------------------------------
    def enclosed(self, pts_world):
        G = R.grip_matrix(self.arm, "weapon_R")
        inv = np.array(G.inverted())
        q = pts_world @ inv[:3, :3].T + inv[:3, 3]
        out = np.zeros(len(q), bool)
        for i in np.nonzero(np.all((q > self.clo) & (q < self.chi), axis=1))[0]:
            v = Vector(q[i])
            out[i] = all(self.ctree.ray_cast(v, d, 0.7)[0] is not None for d in self.rays)
        return out

    def _cannon_sets(self, co_by):
        cov, cut = set(), {}
        for a, (name, idx, _f) in enumerate(self.pieces.items):
            pa = co_by[name][idx]
            e = self.enclosed(pa)
            if a == self.body_i:
                for i in np.nonzero(e & self.body_r_arm[idx])[0]:
                    cov.add((a, int(i)))
                n_cut = int((e & ~self.body_r_arm[idx]).sum())
            elif a in self.r_arm_pieces:
                for i in np.nonzero(e)[0]:
                    cov.add((a, int(i)))
                continue
            else:
                n_cut = int(e.sum())
            if n_cut:
                cut[self.name[a].split(":")[-1]] = n_cut
        return cov, cut

    def cannon_check(self, co_by):
        cov, cut = self._cannon_sets(co_by)
        poke = self.cov_ref - cov
        pk = {}
        for a, _i in poke:
            k = self.name[a].split(":")[-1]
            pk[k] = pk.get(k, 0) + 1
        new_cut = {k: v - self.cut_ref.get(k, 0) for k, v in cut.items() if v - self.cut_ref.get(k, 0) > 0}
        return {"poke_through": len(poke), "poke_by_piece": sorted(pk.items(), key=lambda kv: -kv[1])[:5],
                "cuts": int(sum(new_cut.values())), "cuts_by_piece": sorted(new_cut.items(), key=lambda kv: -kv[1])[:6]}

    # -- under-suit -----------------------------------------------------------------------------------------------------------
    def _vert_area(self, co):
        t = self.tris
        a = 0.5 * np.linalg.norm(np.cross(co[t[:, 1]] - co[t[:, 0]], co[t[:, 2]] - co[t[:, 0]]), axis=1)
        out = np.zeros(len(co))
        for k in range(3):
            np.add.at(out, t[:, k], a)
        return out

    def _volume(self, co):
        t = self.tris
        return float(np.einsum("ij,ij->i", co[t[:, 0]], np.cross(co[t[:, 1]], co[t[:, 2]])).sum() / 6.0)

    def body_check(self, co):
        ed = self.ed
        Ln = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
        dmm = (Ln - self.rest_len) * 1000.0
        rel = np.where(self.rest_len > 0.005, Ln / np.maximum(self.rest_len, 1e-9) - 1.0, 0.0)
        area = self._vert_area(co) / np.maximum(self.rest_area, 1e-12)
        col = (area < 0.4) & self.main
        r = {"stretch_mm_p99_9": round(float(np.percentile(dmm, 99.9)), 1), "stretch_mm_max": round(float(dmm.max()), 1),
             "edges_over_40pct": int((rel > 0.4).sum()), "edges_under_minus40pct": int((rel < -0.4).sum()),
             "collapsed_verts_area_lt_0_4": int(col.sum()), "volume_ratio": round(self._volume(co) / self.rest_vol, 4),
             "collapsed_shoulder_L_R": [int((col & self.shoulder["L"]).sum()), int((col & self.shoulder["R"]).sum())]}
        if col.any():
            h = {}
            for i in np.nonzero(col)[0]:
                h[str(self.dom[i])] = h.get(str(self.dom[i]), 0) + 1
            r["collapsed_by_bone"] = sorted(h.items(), key=lambda kv: -kv[1])[:5]
        return r


def piece_table_path(P):
    return os.path.join(P["A"], "reports", "stage2", "parts.json")
