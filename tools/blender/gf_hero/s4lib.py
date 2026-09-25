"""GODFORGE stage 4: the GF_Hero_v1 pose solver and clip baker (Blender 5.2 mathutils; bpy only to read the rest pose
and to write actions).

Adapted from the user's Ashen Covenant clip scripts (D:/Ashen_Covenant/tools/blender/ac_player_rig/p05_animations.py,
ironwarden_m_gameplay_anims.py and ac_humanoid_enemy/ac_pose.py): FK in degrees on the bone-local axes, IK for wrist and
ankle placement, key poses merged from shared bases, fist curls, one action per clip stashed on its own NLA track.
GODFORGE changes:
  * the IK is analytic (two bones, the hinge on the lower bone's local X, the bend plane from a pole point), so a clip
    is solved per FRAME in plain Python instead of per key with temporary Blender constraints. Every frame is baked
    (LINEAR keys), the way the glTF exporter samples it anyway;
  * key poses are interpolated in PARAMETER space (FK angles, effector targets, foot placements, pelvis offset) with a
    Kochanek-Bartels (tension) Hermite spline, cyclic for loops. A foot whose parameters do not change is planted
    exactly; a loop's last frame IS its first frame; locomotion feet move at exactly the design speed;
  * the sleeve-weapon rule is built in: the hand only twists (the wrist never bends) unless a pose sets "rot" on it;
  * targets are defined from the hero's landmark file and scaled by its leg / arm length (Kit), so the library fits
    every hero on GF_Hero_v1.

Pose dict (one key pose; every value may be omitted, a missing value holds the previous key's value):
  "pelvis":   {"loc": (x, y, z) hero-space offset of the pelvis head (m at Brax scale, x leg scale),
               "rot": (fwd, yaw, side) world degrees: fwd tilts the top forward, yaw turns the front toward the hero's
               left (+X), side leans the top toward the hero's left}
  "<bone>":   {"rot": (x, y, z)} local Euler XYZ degrees (spine, neck, head, clavicles, upper / lower arms, feet...)
              or {"wrot": (fwd, yaw, side)} a WORLD orientation relative to the rest pose (the head stabilised), with
              "ww" 0..1 blending from "rot" (0) to "wrot" (1)
  "arm_L/R":  {"fist" | "wrist": (x, y, z) offset from the REST shoulder (m at Brax scale, x arm scale),
               "pole": (x, y, z) same frame, where the elbow points, "back": the direction the back of the hand faces
               (the hand twist is solved from it, the wrist stays straight), "twist": extra hand twist (deg),
               "space": "chest" (default: the offsets ride on the posed spine_03) | "hero" (fixed in hero space) |
               "abs" (absolute hero-space points, leg scale: lying and kneeling poses)}
  "foot_L/R": {"ball": (x, y) ground position of the ball joint (m, x leg scale), "lift": m, "yaw": deg (toes out
               for + on the left foot), "heel": deg (heel raised, pivot at the ball), "toe": deg (toes bent up),
               "knee": (x, y, z) extra knee direction}
  "fingers_L/R": fist amount 0..1 (1 = the anvil_gauntlets fist, s3_pose_set.fist)
Mirror a left-side dict with mirror(): rot (x, -y, -z), points / poles (-x, y, z), yaw and twist negated.
"""
import math

from mathutils import Euler, Matrix, Quaternion, Vector

import gf_hero_rig as R

FPS = 30
IDQ = Quaternion()
FINGERS = ("index", "middle", "ring", "pinky")

# Brax is the reference build the library numbers are written at (the first hero on GF_Hero_v1).
REF_LEG = 1.0823     # hip -> knee -> ankle
REF_ARM = 0.7910     # shoulder -> elbow -> wrist -> middle knuckle


# ---- pose-dict helpers -------------------------------------------------------------------------------------------
def fist(side, amount=1.0):
    """The fist of s3_pose_set.fist (the anvil_gauntlets fist variant's hand), scaled by amount."""
    d = {}
    for f in FINGERS:
        d["%s_01_%s" % (f, side)] = {"rot": (80 * amount, 0, 0)}
        d["%s_02_%s" % (f, side)] = {"rot": (95 * amount, 0, 0)}
        d["%s_03_%s" % (f, side)] = {"rot": (60 * amount, 0, 0)}
    z = -30 if side == "L" else 30
    d["thumb_01_%s" % side] = {"rot": (40 * amount, 0, z * amount)}
    d["thumb_02_%s" % side] = {"rot": (45 * amount, 0, 0)}
    d["thumb_03_%s" % side] = {"rot": (35 * amount, 0, 0)}
    return d


def merge(*ps):
    out = {}
    for p in ps:
        if not p:
            continue
        for b, tr in p.items():
            if isinstance(tr, dict):
                out.setdefault(b, {}).update(tr)
            else:
                out[b] = tr
    return out


def _mirror_entry(k, v):
    if k == "rot":
        return (v[0], -v[1], -v[2])
    if k in ("fist", "wrist", "pole", "knee", "back"):
        return (-v[0], v[1], v[2])
    if k == "ball":
        return (-v[0], v[1])
    if k in ("yaw", "twist"):
        return -v
    return v


def side_swap(name):
    if name.endswith("_L"):
        return name[:-2] + "_R"
    if name.endswith("_R"):
        return name[:-2] + "_L"
    return name


def mirror(pose, only_left=True):
    """Right-side copy of the left-side entries (only_left) or a full left/right mirror of a pose (only_left=False:
    centre bones get (x, -y, -z) and the pelvis yaw / side flip too)."""
    out = {}
    for b, tr in pose.items():
        if only_left and not b.endswith("_L"):
            continue
        nb = side_swap(b)
        if not isinstance(tr, dict):
            out[nb] = tr
            continue
        t = {}
        for k, v in tr.items():
            if nb == "pelvis" and k == "rot":
                t[k] = (v[0], -v[1], -v[2])
            elif nb == "pelvis" and k == "loc":
                t[k] = (-v[0], v[1], v[2])
            else:
                t[k] = _mirror_entry(k, v)
        out[nb] = t
    return out


def both(pose_l):
    out = dict(pose_l)
    out.update(mirror(pose_l))
    return out


def mirror_clip_keys(keys):
    return [(f, mirror(p, only_left=False), o) for f, p, o in keys]


# ---- the hero kit: landmarks -> measurements ---------------------------------------------------------------------
class Kit:
    def __init__(self, lm, move_speed=6.2):
        P = lambda k: Vector(R.point(lm, k))  # noqa: E731
        self.lm = lm
        self.P = P
        self.leg = (P("knee_L") - P("hip_L")).length + (P("ankle_L") - P("knee_L")).length
        self.arm = (P("elbow_L") - P("shoulder_L")).length + (P("wrist_L") - P("elbow_L")).length + (P("hand_L_tip") - P("wrist_L")).length
        self.ls = self.leg / REF_LEG
        self.as_ = self.arm / REF_ARM
        self.height = float(lm["sockets"]["head_top"]["origin"][2])
        self.move_speed = move_speed

    def lv(self, v):
        return Vector(v) * self.ls

    def av(self, v):
        return Vector(v) * self.as_


# ---- the rest rig ------------------------------------------------------------------------------------------------
class Bone:
    __slots__ = ("name", "parent", "rest", "rest3", "rel", "length", "head", "tail")


class Rig:
    """Rest data of an armature (armature object at the origin, identity)."""

    def __init__(self, arm):
        self.b = {}
        for bb in arm.data.bones:
            x = Bone()
            x.name = bb.name
            x.parent = bb.parent.name if bb.parent else None
            x.rest = bb.matrix_local.copy()
            x.rest3 = x.rest.to_3x3()
            x.length = bb.length
            x.head = bb.head_local.copy()
            x.tail = bb.tail_local.copy()
            self.b[bb.name] = x
        for x in self.b.values():
            x.rel = (self.b[x.parent].rest.inverted() @ x.rest) if x.parent else x.rest.copy()
        self.order = []
        seen = set()

        def visit(n):
            if n in seen:
                return
            p = self.b[n].parent
            if p:
                visit(p)
            seen.add(n)
            self.order.append(n)
        for n in self.b:
            visit(n)
        twist = set(R.twist_bone_names())
        socks = set(R.SOCKET_NAMES)
        # the bones a clip keys: everything but root, the driven twist bones and the sockets
        self.keyed = [n for n in self.order if n != "root" and n not in twist and n not in socks]
        # lowerarm-local effector of the fist (the middle knuckle, i.e. hand tail with the wrist straight)
        self.fist_eff = {}
        for s in ("L", "R"):
            la, h = self.b["lowerarm_" + s], self.b["hand_" + s]
            self.fist_eff[s] = (la.rest.inverted() @ h.tail).copy()

    def world_of_identity(self, M, n):
        x = self.b[n]
        return (M[x.parent] @ x.rel) if x.parent else x.rest.copy()


def soft_reach(d, lmax, start=0.985, end=0.9995):
    """Soft IK: the chain never snaps straight (d beyond start*lmax is eased toward end*lmax)."""
    s = start * lmax
    if d <= s:
        return d
    span = (end - start) * lmax
    return s + span * (1.0 - math.exp(-(d - s) / span))


def soft_fold(d, dmin, band=0.03):
    """Soft IK at the other end: a target closer than dmin (the reach at the hinge's maximum flexion) is eased toward
    dmin instead of folding the limb flat (C1-continuous at dmin + band)."""
    s = dmin + band
    if d >= s:
        return d
    return dmin + band * math.exp(-(s - d) / band)


# The deepest elbow the clips may ask for: the stage-3 validation set's bare maximum (docs/art/GF_HERO_SKELETON.md
# section 7; the weights are only validated up to it). Folding further puts a sleeve weapon inside the upper arm,
# shoulder or head (review of stages 3-5, art/characters/brax/reports/review_stage3_5.md).
ELBOW_MAX_DEG = 145.0
# The deepest knee: a real knee stops at about 150-160 deg with the calf against the thigh; linear-blend skinning
# crushes the calf into the thigh long before that (get_up folded the right knee to 172 deg: a flattened lump). The
# stage-3 weights are validated to 135 deg; 135-150 is the documented knee soft spot (kneels and tucks).
KNEE_MAX_DEG = 150.0


def fold_reach(L1, L2, max_flex_deg):
    """Shoulder-to-effector distance at the given hinge flexion (0 = straight)."""
    g = math.radians(180.0 - max_flex_deg)
    return math.sqrt(max(L1 * L1 + L2 * L2 - 2.0 * L1 * L2 * math.cos(g), 0.0))


def two_bone(S, T, pole, L1, L2, sign, max_flex_deg=None):
    """Upper-bone frame (3x3: X hinge, Y along the bone) + lower direction for a two-bone chain from S reaching T, bending
    toward pole. sign = +1 for arms (elbow flexion is +X), -1 for legs (knee flexion is -X). max_flex_deg: the deepest
    hinge flexion allowed (a softer, closer target is eased out to it)."""
    dv = T - S
    d = max(dv.length, 1e-6)
    w = dv / d
    d = min(soft_reach(d, L1 + L2), L1 + L2 - 1e-5)
    if max_flex_deg is not None:
        d = soft_fold(d, fold_reach(L1, L2, max_flex_deg))
    d = max(d, abs(L1 - L2) + 1e-4)
    p = pole - S
    pp = p - w * p.dot(w)
    if pp.length < 1e-6:
        pp = Vector((0.0, 0.0, -1.0)) if sign > 0 else Vector((0.0, -1.0, 0.0))
        pp = pp - w * pp.dot(w)
    pp.normalize()
    ca = max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))
    a = math.acos(ca)
    du = (w * math.cos(a) + pp * math.sin(a)).normalized()
    mid = S + du * L1
    dl = (S + w * d - mid).normalized()
    n = du.cross(dl)
    if n.length < 1e-7:
        n = pp.cross(w)
    X = n.normalized() * sign
    Y = du
    Z = X.cross(Y).normalized()
    X = Y.cross(Z).normalized()
    F = Matrix((X, Y, Z)).transposed()
    return F, dl, mid


def rot_world(fwd=0.0, yaw=0.0, side=0.0):
    """World rotation: yaw about Z (front toward the hero's left), fwd about X (top toward the front), side about Y
    (top toward the hero's left)."""
    return (Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(fwd), 3, "X")
            @ Matrix.Rotation(math.radians(-side), 3, "Y"))


class KeepOut:
    """The arm keep-out (added by the review of stages 3-5, art/characters/brax/reports/review_stage3_5.md): the rigid
    volume a hand carries (a sleeve weapon such as the anvil_gauntlets, or the bare forearm and fist) must not pass
    through the hero's own body. Effector targets are written as points; nothing in the IK knows how thick a
    38 cm gauntlet is, so kneeling, tucked and wind-up poses drove it through thighs, knees, the chest and the skirt.

    shape[side]: a star-shaped radial map of that volume around the grip frame's +Y axis (the forearm / fingers
    direction): rmax[iy, ith] = the largest radius of the volume's vertices in slab iy (y0 + iy*dy) and sector ith, in
    the grip frame (docs/art/GF_HERO_SKELETON.md section 3). A point is inside when its radius is under the map.
    body: every skinned vertex at rest (armature space) with its top-4 skin weights; own[side] marks the vertices that
    can never be obstacles for that arm (its own upper arm (the known cuff overlap, handled by ELBOW_MAX_DEG), forearm,
    hand and fingers, and the other arm's forearm and hand: gauntlet-on-gauntlet contact is a pose's intent).

    resolve() pushes the fist target out, perpendicular to the forearm, by the deepest overlap, and re-solves the arm
    (a few iterations per frame); bake() smooths the per-frame pushes over time. A frame with no overlap is untouched,
    so clean poses (the guard, the jabs) do not change."""

    def __init__(self, bones, rest_inv, verts, joints, weights, own, shape, lengths, margin=0.006, step_max=0.06, iters=6):
        import numpy as np
        self.np = np
        self.bones = list(bones)
        self.lengths = np.asarray(lengths, dtype=np.float64)
        self.rest_inv = np.array([np.array(m) for m in rest_inv])          # (nb, 4, 4)
        self.V = np.asarray(verts, dtype=np.float64)
        self.J = np.asarray(joints, dtype=np.int64)
        self.W = np.asarray(weights, dtype=np.float64)
        self.own = {s: np.asarray(own[s], dtype=bool) for s in ("L", "R")}
        self.dom = self.J[np.arange(len(self.J)), self.W.argmax(1)]      # each vertex's dominant bone
        self.shape = shape
        self.margin = margin
        self.step_max = step_max
        self.iters = iters
        self.g2s = np.array(Matrix(R.SOCKET_TO_GRIP))

    def skin(self, M):
        np = self.np
        S = np.array([np.array(M[b]) for b in self.bones]) @ self.rest_inv
        blend = (S[self.J] * self.W[:, :, None, None]).sum(1)
        return np.einsum("vij,vj->vi", blend[:, :3, :3], self.V) + blend[:, :3, 3]

    def overlap(self, s, M, pts):
        """-> (push Vector in armature space or None, overlapping vertex count, deepest overlap m)."""
        np = self.np
        sh = self.shape[s]
        G = np.array(M["weapon_" + s]) @ self.g2s
        loc = (pts - G[:3, 3]) @ G[:3, :3]
        x = loc[:, 0] - sh["cx"]
        z = loc[:, 2] - sh["cz"]
        iy = np.floor((loc[:, 1] - sh["y0"]) / sh["dy"]).astype(np.int64)
        ok = (~self.own[s]) & (iy >= 0) & (iy < sh["ny"])
        if not ok.any():
            return None, 0, 0.0
        r = np.hypot(x, z)
        ith = np.floor((np.arctan2(z, x) + math.pi) / (2 * math.pi) * sh["nth"]).astype(np.int64) % sh["nth"]
        rm = np.where(ok, sh["rmax"][np.clip(iy, 0, sh["ny"] - 1), ith], 0.0)
        depth = rm + self.margin - r
        hit = ok & (depth > 0)
        n = int(hit.sum())
        if n == 0:
            return None, 0, 0.0
        d = depth[hit]
        mag = float(d.max())
        # the way out is the body's own outward normal at the overlap: from the axis of each overlapping vertex's
        # dominant bone out through the vertex (a fist crossing the chest slides out in front of it, a fist planted on
        # a knee slides off to the side of the leg), weighted by depth
        Mb = np.array([np.array(M[self.bones[i]]) for i in self.dom[hit]])
        a = Mb[:, :3, 3]
        ax = Mb[:, :3, 1] * self.lengths[self.dom[hit]][:, None]
        t = np.clip(((pts[hit] - a) * ax).sum(1) / np.maximum((ax * ax).sum(1), 1e-12), 0.0, 1.0)
        nb = pts[hit] - (a + ax * t[:, None])
        nb /= np.maximum(np.linalg.norm(nb, axis=1), 1e-9)[:, None]
        away = (nb * d[:, None]).sum(0)
        if np.linalg.norm(away) < 1e-6 * d.sum():
            # normals cancel (between two limbs): away from the overlapping vertices, across the forearm
            u = np.stack([x[hit], z[hit]], 1) / np.maximum(r[hit], 1e-6)[:, None]
            aw = -(u * d[:, None]).sum(0)
            away = G[:3, :3] @ np.array([aw[0], 0.0, aw[1]])
        nrm = np.linalg.norm(away)
        if nrm < 1e-9:
            return None, n, mag
        push = away / nrm * mag
        return Vector(push.tolist()), n, mag

    def resolve(self, solver, pose, M, info):
        """Per-frame pushes {side: Vector} (armature space) that clear the arm volumes out of the body."""
        off = {}
        sides = [s for s in ("L", "R") if ("arm_" + s) in pose and ("target_" + s) in info]
        cur = M
        for _it in range(self.iters):
            pts = self.skin(cur)
            moved = False
            for s in sides:
                push, n, _deep = self.overlap(s, cur, pts)
                if push is None:
                    continue
                if push.length > self.step_max:
                    push = push * (self.step_max / push.length)
                T = info["target_" + s] + off.get(s, Vector())
                if T.z < 0.25 * solver.K.ls and push.z < 0.0:     # a planted / low fist is never pushed into the ground
                    push.z = 0.0
                off[s] = off.get(s, Vector()) + push
                moved = True
            if not moved:
                break
            _l, cur, _i = solver.solve(pose, arm_target={s: info["target_" + s] + v for s, v in off.items()})
        return off

    def residual(self, M):
        pts = self.skin(M)
        return {s: self.overlap(s, M, pts)[1] for s in ("L", "R")}


class Solver:
    def __init__(self, rig, kit):
        self.rig = rig
        self.K = kit
        b = rig.b
        self.sh_rest = {s: b["upperarm_" + s].head.copy() for s in ("L", "R")}
        self.ankle_rest = {s: b["foot_" + s].head.copy() for s in ("L", "R")}
        self.ball_rest = {s: b["toe_" + s].head.copy() for s in ("L", "R")}
        self.len = {n: x.length for n, x in b.items()}
        # the heel's ground point (under and behind the ankle) and the toe tip
        self.heel_rest = {s: Vector((self.ankle_rest[s].x, self.ankle_rest[s].y + 0.09 * kit.ls, 0.0)) for s in ("L", "R")}
        self.toe_tip_z = {s: b["toe_" + s].tail.z for s in ("L", "R")}
        self.elbow_max = ELBOW_MAX_DEG
        self.knee_max = KNEE_MAX_DEG
        self.keepout = None          # a KeepOut (s4_anim builds it from the hero's skinned parts and signature weapon)

    def solve(self, pose, arm_target=None):
        """pose -> (local {bone: (Quaternion, Vector)}, armature-space matrices {bone: Matrix}). arm_target {side: point}
        replaces an arm's effector target (the keep-out's corrected fist)."""
        rig, K = self.rig, self.K
        local = {}
        M = {}
        info = {}

        def setM(n, q, t=None):
            t = t if t is not None else Vector()
            local[n] = (q, t)
            basis = Matrix.Translation(t) @ q.to_matrix().to_4x4()
            M[n] = rig.world_of_identity(M, n) @ basis

        def local_from_world3(n, F3):
            P3 = rig.world_of_identity(M, n).to_3x3()
            return (P3.inverted() @ F3).to_quaternion()

        for n in rig.order:
            if n in M:
                continue
            x = rig.b[n]
            spec = pose.get(n, {}) if isinstance(pose.get(n, {}), dict) else {}
            if n == "root":
                setM(n, IDQ.copy())
                continue
            if n == "pelvis":
                pl = pose.get("pelvis", {})
                t = x.rest3.inverted() @ K.lv(pl.get("loc", (0, 0, 0)))
                Rw = rot_world(*pl.get("rot", (0, 0, 0)))
                q = (x.rest3.inverted() @ Rw @ x.rest3).to_quaternion()
                setM(n, q, t)
                continue
            if n in ("upperarm_L", "upperarm_R") and ("arm_" + n[-1]) in pose:   # not the twist bones
                self._arm(n[-1], pose["arm_" + n[-1]], M, local, setM, info,
                          T=(arm_target or {}).get(n[-1]))
                continue
            if n in ("thigh_L", "thigh_R") and ("foot_" + n[-1]) in pose:
                self._leg(n[-1], pose["foot_" + n[-1]], M, local, setM, info)
                continue
            if n.startswith("hand_") and n.count("_") == 1:
                arm = pose.get("arm_" + n[-1])
                if "rot" in spec:
                    q = Euler([math.radians(a) for a in spec["rot"]], "XYZ").to_quaternion()
                else:
                    tw = math.radians(arm.get("twist", 0.0)) if arm else 0.0
                    if arm and "back" in arm:
                        tw += self._back_twist(n[-1], arm, M)
                    q = Quaternion((0.0, 1.0, 0.0), tw)
                setM(n, q)
                info["twist_" + n[-1]] = math.degrees(2 * math.atan2(q.y, q.w))
                continue
            if "wrot" in spec:
                F = rot_world(*spec["wrot"]) @ x.rest3
                qw = local_from_world3(n, F)
                ww = spec.get("ww", 1.0)
                if ww < 1.0:     # blend a world-stabilised bone (e.g. the head) toward its FK rotation (limp in falls)
                    qf = Euler([math.radians(a) for a in spec.get("rot", (0, 0, 0))], "XYZ").to_quaternion()
                    if qf.dot(qw) < 0:
                        qw.negate()
                    qw = qf.slerp(qw, max(0.0, ww))
                setM(n, qw)
                continue
            if "rot" in spec:
                setM(n, Euler([math.radians(a) for a in spec["rot"]], "XYZ").to_quaternion())
                continue
            setM(n, IDQ.copy())
        return local, M, info

    # -- arms --------------------------------------------------------------------------------------------------------
    def _back_twist(self, s, spec, M):
        """Hand twist (radians) that turns the back of the hand (the grip frame's up) toward spec["back"] (a direction
        in the arm's space), the wrist kept straight."""
        rig = self.rig
        h = "hand_" + s
        H0 = rig.world_of_identity(M, h).to_3x3()
        back_local = rig.b[h].rest3.inverted() @ rig.b["weapon_" + s].rest3.col[1]
        d = self.arm_world(s, spec, M)[2]
        y = H0.col[1].normalized()
        cur = H0 @ back_local
        cur = (cur - y * cur.dot(y))
        des = (d - y * d.dot(y))
        if cur.length < 1e-6 or des.length < 1e-6:
            return 0.0
        cur.normalize()
        des.normalize()
        return math.atan2(cur.cross(des).dot(y), cur.dot(des))

    def arm_world(self, s, spec, M):
        """World (hero-space) effector target, pole point and back-of-hand direction of an arm spec, given the posed
        spine_03 in M."""
        rig, K = self.rig, self.K
        space = spec.get("space", "chest")
        sh = self.sh_rest[s]
        off = spec["fist"] if "fist" in spec else spec["wrist"]
        tgt_rest = sh + K.av(off)
        pole_rest = sh + K.av(spec.get("pole", (0.2 if s == "L" else -0.2, 0.25, -0.6)))
        d = Vector(spec.get("back", (0.0, 0.0, 1.0)))
        if space == "chest":
            C = M["spine_03"] @ rig.b["spine_03"].rest.inverted()
            return C @ tgt_rest, C @ pole_rest, C.to_3x3() @ d
        if space == "abs":           # absolute hero-space points (m at Brax scale, x leg scale): lying / kneeling poses
            return K.lv(off), K.lv(spec.get("pole", (0.0, 0.0, 3.0))), d
        return tgt_rest, pole_rest, d

    def to_hero_space(self, s, spec, M):
        """The same arm spec re-expressed in "hero" space (offsets from the rest shoulder), so keys that mix spaces can
        be interpolated."""
        T, Pp, d = self.arm_world(s, spec, M)
        sh = self.sh_rest[s]
        out = dict(spec)
        key = "fist" if "fist" in spec else "wrist"
        out[key] = tuple((T - sh) / self.K.as_)
        out["pole"] = tuple((Pp - sh) / self.K.as_)
        if "back" in spec:
            out["back"] = tuple(d)
        out["space"] = "hero"
        return out

    def _arm(self, s, spec, M, local, setM, info, T=None):
        rig = self.rig
        up, lo = "upperarm_" + s, "lowerarm_" + s
        eff = rig.fist_eff[s] if "fist" in spec else Vector((0.0, self.len[lo], 0.0))
        T0, Pp, _d = self.arm_world(s, spec, M)
        T = T0 if T is None else T
        # upper arm head, with the clavicle already posed
        Mu0 = rig.world_of_identity(M, up)
        S = Mu0.translation.copy()
        L1 = self.len[up]
        L2 = eff.length
        F, dl, mid = two_bone(S, T, Pp, L1, L2, +1, max_flex_deg=self.elbow_max)
        qu = (Mu0.to_3x3().inverted() @ F).to_quaternion()
        setM(up, qu)
        Ml0 = rig.world_of_identity(M, lo)
        c = (Ml0.to_3x3() @ eff).normalized()
        qw = c.rotation_difference(dl)
        P3 = Ml0.to_3x3()
        ql = (P3.inverted() @ qw.to_matrix() @ P3).to_quaternion()
        setM(lo, ql)
        info["reach_" + s] = (T - S).length / (L1 + L2)
        info["target_" + s] = T
        info["target0_" + s] = T0          # as written (before a keep-out push)
        # the target sits inside the fold zone: the elbow limit eased the fist out (usually an in-between frame whose
        # interpolated effector path passes close to the shoulder), not a pose that asks for more than the arm reaches
        info["fold_eased_" + s] = (T - S).length < fold_reach(L1, L2, self.elbow_max) + 0.03

    # -- legs --------------------------------------------------------------------------------------------------------
    def foot_frame(self, s, spec):
        """(foot rotation, ball position, ankle target, yaw, heel). heel > 0 raises the heel about the ball; heel < 0
        raises the toes about the heel point (a heel strike), so the sole never goes under the ground."""
        K = self.K
        yaw = spec.get("yaw", 0.0)
        heel = spec.get("heel", 0.0)
        Rz = Matrix.Rotation(math.radians(yaw), 3, "Z")
        Rf = Rz @ Matrix.Rotation(math.radians(heel), 3, "X")
        br = self.ball_rest[s]
        bx, by = spec.get("ball", (br.x / K.ls, br.y / K.ls))
        B = Vector((bx * K.ls, by * K.ls, br.z + max(0.0, spec.get("lift", 0.0)) * K.ls))
        if heel >= 0.0:
            A = B + Rf @ (self.ankle_rest[s] - br)
        else:
            hr = self.heel_rest[s]
            Hp = B + Rz @ (hr - br)
            A = Hp + Rf @ (self.ankle_rest[s] - hr)
            B = Hp + Rf @ (br - hr)
        return Rf, B, A, yaw, heel

    def _leg(self, s, spec, M, local, setM, info):
        rig = self.rig
        th, sn, ft, toe = "thigh_" + s, "shin_" + s, "foot_" + s, "toe_" + s
        Rf, B, A, yaw, heel = self.foot_frame(s, spec)
        Mt0 = rig.world_of_identity(M, th)
        S = Mt0.translation.copy()
        L1, L2 = self.len[th], self.len[sn]
        fwd = Matrix.Rotation(math.radians(yaw), 3, "Z") @ Vector((0.0, -1.0, 0.0))
        out = Vector((1.0 if s == "L" else -1.0, 0.0, 0.0))
        kn = Vector(spec.get("knee", (0.0, 0.0, 0.0)))
        pole = (S + A) * 0.5 + fwd * 1.0 + out * 0.12 + kn
        # the knee limit: a target closer than the reach at KNEE_MAX_DEG is eased out HORIZONTALLY (the ankle keeps its
        # height, so a kneeling foot never goes into the ground); straight under the hip, along the hip-ankle line
        cap = self.knee_max
        h = A - S
        de = soft_fold(h.length, fold_reach(L1, L2, self.knee_max))
        hor = Vector((h.x, h.y, 0.0))
        if de > h.length + 1e-9 and hor.length > 1e-3 and de * de > h.z * h.z:
            A = S + hor.normalized() * math.sqrt(de * de - h.z * h.z) + Vector((0.0, 0.0, h.z))
            cap = None
        F, dl, mid = two_bone(S, A, pole, L1, L2, -1, max_flex_deg=cap)
        setM(th, (Mt0.to_3x3().inverted() @ F).to_quaternion())
        Ms0 = rig.world_of_identity(M, sn)
        c = (Ms0.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
        qw = c.rotation_difference(dl)
        P3 = Ms0.to_3x3()
        setM(sn, (P3.inverted() @ qw.to_matrix() @ P3).to_quaternion())
        Ff = Rf @ rig.b[ft].rest3
        P3 = rig.world_of_identity(M, ft).to_3x3()
        setM(ft, (P3.inverted() @ Ff).to_quaternion())
        lift = max(0.0, spec.get("lift", 0.0))
        flat = max(0.0, min(1.0, 1.0 - lift / 0.10))
        tp = heel * (1.0 - flat) - spec.get("toe", 0.0)
        # ground clamp: the toe tip never dips under its rest height
        tl = self.len[toe]
        room = (B.z - self.toe_tip_z[s] + 0.002) / tl
        if room < 1.0:
            tp = min(tp, math.degrees(math.asin(max(-1.0, room))))
        Ft = Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(tp), 3, "X") @ rig.b[toe].rest3
        P3 = rig.world_of_identity(M, toe).to_3x3()
        setM(toe, (P3.inverted() @ Ft).to_quaternion())
        info["reach_leg_" + s] = (A - S).length / (L1 + L2)
        info["knee_eased_" + s] = h.length < fold_reach(L1, L2, self.knee_max) + 0.03


def expand_pose(pose):
    """fingers_L / fingers_R amounts -> finger rotations (explicit finger 'rot' entries win)."""
    out = {}
    for s in ("L", "R"):
        k = "fingers_" + s
        if k in pose:
            out.update(fist(s, pose[k]))
    for b, tr in pose.items():
        if b.startswith("fingers_"):
            continue
        if isinstance(tr, dict) and b in out:
            out[b] = dict(out[b], **tr)
        else:
            out[b] = tr
    return out


# ---- parameter-space interpolation -----------------------------------------------------------------------------
def flatten(pose):
    """{(bone, field): value} with scalars / tuples; strings kept."""
    out = {}
    for b, tr in pose.items():
        if isinstance(tr, dict):
            for k, v in tr.items():
                out[(b, k)] = v
        else:
            out[(b, None)] = tr
    return out


def unflatten(flat):
    out = {}
    for (b, k), v in flat.items():
        if k is None:
            out[b] = v
        else:
            out.setdefault(b, {})[k] = v
    return out


FIELD_DEFAULT = {"rot": (0.0, 0.0, 0.0), "loc": (0.0, 0.0, 0.0), "lift": 0.0, "yaw": 0.0, "heel": 0.0, "toe": 0.0,
                 "twist": 0.0, "knee": (0.0, 0.0, 0.0), "wrot": (0.0, 0.0, 0.0), "ww": 1.0}


def fill_keys(keys):
    """Forward-fill then back-fill the flattened key poses so every key has every field (hold semantics)."""
    flats = [flatten(expand_pose(p)) for _f, p, _o in keys]
    fields = []
    for fl in flats:
        for k in fl:
            if k not in fields:
                fields.append(k)
    for k in fields:
        last = None
        for fl in flats:
            if k in fl:
                last = fl[k]
            elif last is not None:
                fl[k] = last
        # before a field's first key: its rest default when it has one (angles, weights), else the first value
        # (effector targets have no neutral value)
        nxt = FIELD_DEFAULT.get(k[1]) if k[1] in FIELD_DEFAULT else None
        if nxt is None:
            for fl in reversed(flats):
                if k in fl:
                    nxt = fl[k]
                elif nxt is not None:
                    fl[k] = nxt
        else:
            for fl in flats:
                if k in fl:
                    break
                fl[k] = nxt
        for fl in flats:
            if k not in fl:
                fl[k] = FIELD_DEFAULT.get(k[1], 0.0)
    return fields, flats


def _vec(v):
    return [float(x) for x in v] if isinstance(v, (tuple, list)) else [float(v)]


def interp_keys(keys, length, loop):
    """keys: [(frame, pose, opts)] -> per-frame pose dicts (frames 0..length). opts: t (tension 0..1, 1 = the pose is
    held: zero velocity), lin (the segment AFTER this key is linear), ease ('in' / 'out': tension on one side only)."""
    keys = sorted(keys, key=lambda k: k[0])
    if loop:
        if keys[-1][0] != length:
            keys = keys + [(length, keys[0][1], keys[0][2])]
    fields, flats = fill_keys(keys)
    num = [k for k in fields if not isinstance(flats[0][k], str)]
    strs = [k for k in fields if isinstance(flats[0][k], str)]
    T = [float(k[0]) for k in keys]
    V = [sum((_vec(fl[k]) for k in num), []) for fl in flats]
    dims = [len(_vec(flats[0][k])) for k in num]
    n = len(keys)
    opts = [k[2] or {} for k in keys]

    def held(i):
        """Per value: True when it holds (does not change) into or out of key i. Such a value is at rest at the key,
        so a planted foot (or any held channel) never drifts on the spline's overshoot."""
        out = []
        for d in range(len(V[i])):
            prev_i = i - 1 if i > 0 else (n - 2 if loop else None)
            next_i = i + 1 if i < n - 1 else (1 if loop else None)
            h = (prev_i is not None and abs(V[prev_i][d] - V[i][d]) < 1e-9) or                 (next_i is not None and abs(V[next_i][d] - V[i][d]) < 1e-9)
            out.append(h)
        return out

    HELD = [held(i) for i in range(n)]

    def tangent(i, side):
        t = _tangent(i, side)
        return [0.0 if HELD[i][d] else t[d] for d in range(len(t))]

    def _tangent(i, side):
        """Tangent (value per frame) at key i; side 'in' or 'out'."""
        o = opts[i]
        ten = o.get("t", 0.0)
        if o.get("ease") == "in" and side == "in":
            ten = 1.0
        if o.get("ease") == "out" and side == "out":
            ten = 1.0
        if o.get("lin_in") and side == "in":
            return [(V[i][d] - V[i - 1][d]) / (T[i] - T[i - 1]) for d in range(len(V[i]))]
        if side == "out" and o.get("lin"):
            return [(V[i + 1][d] - V[i][d]) / (T[i + 1] - T[i]) for d in range(len(V[i]))]
        if side == "in" and i > 0 and opts[i - 1].get("lin"):
            return [(V[i][d] - V[i - 1][d]) / (T[i] - T[i - 1]) for d in range(len(V[i]))]
        if loop:
            ip = i - 1 if i > 0 else n - 2
            inn = i + 1 if i < n - 1 else 1
            tp = T[ip] - (length if i == 0 else 0.0)
            tn = T[inn] + (length if i == n - 1 else 0.0)
        else:
            if i == 0 or i == n - 1:
                return [0.0] * len(V[i])
            ip, inn, tp, tn = i - 1, i + 1, T[i - 1], T[i + 1]
        return [(1.0 - ten) * (V[inn][d] - V[ip][d]) / (tn - tp) for d in range(len(V[i]))]

    out = []
    for f in range(length + 1):
        i = 0
        while i < n - 2 and f > T[i + 1]:
            i += 1
        t0, t1 = T[i], T[i + 1]
        h = t1 - t0
        s = 0.0 if h <= 0 else max(0.0, min(1.0, (f - t0) / h))
        if opts[i].get("lin"):
            vals = [V[i][d] + (V[i + 1][d] - V[i][d]) * s for d in range(len(V[i]))]
        else:
            m0, m1 = tangent(i, "out"), tangent(i + 1, "in")
            h00 = 2 * s ** 3 - 3 * s ** 2 + 1
            h10 = s ** 3 - 2 * s ** 2 + s
            h01 = -2 * s ** 3 + 3 * s ** 2
            h11 = s ** 3 - s ** 2
            vals = [h00 * V[i][d] + h10 * h * m0[d] + h01 * V[i + 1][d] + h11 * h * m1[d] for d in range(len(V[i]))]
        flat = {}
        c = 0
        for k, dm in zip(num, dims):
            flat[k] = vals[c] if dm == 1 and not isinstance(flats[0][k], (tuple, list)) else tuple(vals[c:c + dm])
            c += dm
        for k in strs:
            flat[k] = flats[0][k]
        out.append(unflatten(flat))
    return out


# ---- clips -------------------------------------------------------------------------------------------------------
class Clip:
    """One clip. Either keys [(frame, pose, opts)] or fn(frame) -> pose (procedural, e.g. locomotion)."""

    def __init__(self, clip, length, keys=None, fn=None, loop=False, layer="full", weapon="fist", travel=(0.0, 0.0),
                 purpose="", maps_to="", events=None, speed=None, notes="", render_frames=None, family="shared",
                 slide_exempt=False, grounded=True):
        self.clip = clip
        self.length = int(length)
        self.keys = keys
        self.fn = fn
        self.loop = loop
        self.layer = layer
        self.weapon = weapon
        self.travel = travel
        self.purpose = purpose
        self.maps_to = maps_to
        self.events = events or {}
        self.speed = speed
        self.notes = notes
        self.render_frames = render_frames
        self.family = family
        self.slide_exempt = slide_exempt
        self.grounded = grounded

    def action_name(self, key):
        return "%s_%s%s" % (key, self.clip, "@loop" if self.loop else "")

    def key_frames(self):
        if self.render_frames:
            return list(self.render_frames)
        if self.keys:
            fr = sorted({int(k[0]) for k in self.keys if 0 <= k[0] <= self.length})
            if self.loop and self.length in fr:
                fr.remove(self.length)
            return fr
        step = max(1, self.length // 6)
        return list(range(0, self.length, step))[:8]

    def poses(self, solver=None):
        if self.fn is not None:
            return [expand_pose(self.fn(f)) for f in range(self.length + 1)]
        keys = self.keys
        if solver is not None:
            keys = canonical_arm_spaces(solver, keys)
        return interp_keys(keys, self.length, self.loop)


def canonical_arm_spaces(solver, keys):
    """Arm effectors may be written in different spaces on different keys (chest-relative guard, a fist planted on the
    ground in absolute space). An arm whose keys mix spaces is re-expressed in hero space on every key (solved with
    that key's torso), so the interpolation runs in one space and every key still lands exactly where it was written."""
    out = [(f, expand_pose(p), o) for f, p, o in keys]
    for s in ("L", "R"):
        k = "arm_" + s
        spaces = {p[k].get("space", "chest") for _f, p, _o in out if k in p}
        if len(spaces) <= 1:
            continue
        for f, p, o in out:
            if k in p:
                _local, M, _info = solver.solve(p)
                p[k] = solver.to_hero_space(s, p[k], M)
    return out


def _smooth_pushes(offs, loop):
    """Per-side push sequences, dilated by one frame (the peak survives) then smoothed [1, 2, 1] / 4; cyclic for a loop
    (its last frame is its first), clip ends pinned otherwise (an upper-layer clip starts and ends on the idle_combat
    pose, whose own push is computed from the same pose)."""
    n = len(offs)
    out = [dict() for _ in range(n)]
    for s in ("L", "R"):
        seq = [o.get(s, Vector()) for o in offs]
        if all(v.length == 0.0 for v in seq):
            continue

        def at(i):
            if loop:
                return seq[i % (n - 1)] if n > 1 else seq[0]
            return seq[max(0, min(n - 1, i))]
        dil = []
        for i in range(n):
            dil.append(max((at(i - 1), at(i), at(i + 1)), key=lambda v: v.length))

        def dat(i):
            if loop:
                return dil[i % (n - 1)] if n > 1 else dil[0]
            return dil[max(0, min(n - 1, i))]
        for i in range(n):
            v = (dat(i - 1) + dat(i) * 2.0 + dat(i + 1)) * 0.25
            if not loop and i in (0, n - 1):
                v = seq[i]
            if v.length > 1e-6:
                out[i][s] = v
    if loop and n > 1:
        out[-1] = dict(out[0])
    return out


def bake(solver, clip):
    """-> list per frame of (local, M, info, pose). With solver.keepout, the arms are cleared out of the body (KeepOut):
    per-frame pushes, smoothed over time, then the final solve."""
    poses = clip.poses(solver)
    first = [solver.solve(pose) for pose in poses]
    KO = solver.keepout
    if KO is None:
        return [(l_, M, i_, p) for (l_, M, i_), p in zip(first, poses)]
    raw = [KO.resolve(solver, p, M, i_) for (_l, M, i_), p in zip(first, poses)]
    pushes = _smooth_pushes(raw, clip.loop)
    out = []
    for (l_, M, i_), p, off in zip(first, poses, pushes):
        if off:
            l_, M, i_ = solver.solve(p, arm_target={s: i_["target_" + s] + v for s, v in off.items()})
            for s, v in off.items():
                i_["keepout_" + s] = v.length
        out.append((l_, M, i_, p))
    return out


def to_eulers(frames, bones):
    """Per bone, per frame XYZ Euler (radians) with compatibility to the previous frame (no 360 degree flips)."""
    res = {b: [] for b in bones}
    for b in bones:
        prev = None
        for local, _M, _i, _p in frames:
            q = local.get(b, (IDQ, None))[0]
            e = q.to_euler("XYZ", prev) if prev is not None else q.to_euler("XYZ")
            res[b].append(e)
            prev = e
    return res


def write_action(bpy, arm, name, frames, bones, loop):
    """Bake the frames into a new action (LINEAR keys on rotation_euler for every keyed bone, location on the pelvis)."""
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    slot = act.slots.new(id_type="OBJECT", name=arm.name)
    arm.animation_data.action_slot = slot
    n = len(frames)
    eul = to_eulers(frames, bones)
    lin = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    for b in bones:
        pb = arm.pose.bones[b]
        pb.rotation_mode = "XYZ"
        for i in range(3):
            fc = act.fcurve_ensure_for_datablock(arm, 'pose.bones["%s"].rotation_euler' % b, index=i, group_name=b)
            fc.keyframe_points.add(n)
            co = []
            for f in range(n):
                co += [float(f), eul[b][f][i]]
            fc.keyframe_points.foreach_set("co", co)
            fc.keyframe_points.foreach_set("interpolation", [lin] * n)
            fc.update()
        if b == "pelvis":
            for i in range(3):
                fc = act.fcurve_ensure_for_datablock(arm, 'pose.bones["%s"].location' % b, index=i, group_name=b)
                fc.keyframe_points.add(n)
                co = []
                for f in range(n):
                    co += [float(f), frames[f][0][b][1][i]]
                fc.keyframe_points.foreach_set("co", co)
                fc.keyframe_points.foreach_set("interpolation", [lin] * n)
                fc.update()
    act.use_frame_range = True
    act.frame_start = 0
    act.frame_end = n - 1
    act.use_cyclic = bool(loop)
    return act, eul
