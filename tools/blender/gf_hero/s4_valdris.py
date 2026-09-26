"""Valdris's stage-4 clips on GF_Hero_v1: the shared set re-posed for a plate juggernaut, and his kit (10 clips).

Valdris, The Anvil-Born (content/sheets/characters.csv row valdris, assets/content/kits.ron, brief.md section 8) wears
137 rigid armour pieces over a 0.225 m upper arm, an anvil that stands 0.35 m off his chest, pauldrons level with his
crown and a sleeve cannon (the colossus_cannon on weapon_R). His stage-3 rig report (reports/rig_report.md section 6)
measured the ranges his plate allows, and they rule out most of Brax's key poses:

  * Brax's guard folds the elbows to 93-102 deg; past 25 deg the cannon's rear cuff enters Valdris's upper-arm plate
    (107 vertices at 90 deg) and his left fist reaches the anvil past 75 deg. His arms live between -45 and +30 deg of
    elevation (+15 forward), the cannon elbow between 0 and ~33 deg, the head nods 5 deg;
  * his sabaton's instep lame and first toe lame ride the SHIN (stage 3: the ankle then stays clean), so a shin tipped
    forward over a flat foot drives them into the ground (9 deg = 4 cm). Every planted pose here keeps the shins at their
    rest lean: the hips go back instead of the knees forward (V.stance solves it with s4lib's own leg IK);
  * the greave drives into the sabaton's foot shell past about 20 deg of ankle flexion either way, so a foot in the air
    hangs in line with its shin (V.neutral_heel: the key's heel becomes a small offset; "heel_abs" keeps a written heel);
  * the torso twist stays low (spine_01 / 02), the head is FK (a world-stabilised head would nod it into the gorget).

So the shared set keeps the library's contract, names, loops, layers, events and timing structure (s4_clips.py), and
re-poses every key in his vocabulary: arms as (elevation, azimuth) directions of the upper arm and forearm inside the
measured ranges, planted feet with upright shins, a heavier and wider gait (vloco, adapted from s4_clips.locomotion),
and slower, deeper weight shifts. Clips are in place, 30 fps; the numbers are real metres and degrees (V converts them
to s4lib pose dicts, whose offsets are Brax-scale x the hero's leg / arm scale).

Conventions: the hero faces -Y, +X is his LEFT. Arm directions (elevation above the horizontal, azimuth from straight out
to the side (0) toward the front (90)) are in the rest chest frame and ride the posed chest. "Left-side terms" mirror
for the right side.
"""
import math

from mathutils import Matrix, Vector

import s4_clips
from s4_clips import HOLD, LIN, merge, smooth
from s4lib import FPS, Clip, rot_world, two_bone

# the arm keep-out (s4_anim.build_keepout): the cape and loincloth hang and swing (never obstacles); the couters and
# pauldron stacks ride driven helpers the solver does not evaluate (their plates are checked by s4_valdris_render.py)
KEEPOUT_LOOSE_PARTS = ("CAPE", "LOINCLOTH")
KEEPOUT_OWN_BONES = {"L": ("x_elbow_L", "x_pauldron_L"), "R": ("x_elbow_R", "x_pauldron_R")}
PAULDRONS = ["x_pauldron_L", "x_pauldron_R"]
# the front edge of the sabaton's sole relative to the ball joint (rest, either foot): SABATON_SOLE is one rigid plate on
# the FOOT bone that runs 0.273 m past the ball (y -0.473 against the ball at -0.200, its underside at z 0 against the
# ball joint's 0.035; reports/stage2/parts.json, measured on the stage-3 rig). A heel raised about the ball would drive
# that front 0.27 m into the ground (5 deg = 2.4 cm), so Valdris's feet roll about this edge instead (V.foot).
SOLE_TIP = Vector((0.0, -0.273, -0.035))
# ...and its rear edge (y +0.235): a heel strike (toes up) pivots there, not at s4lib's heel point 0.09 m behind the ankle,
# which would drive the sabaton's 0.2 m long heel into the ground
SOLE_HEEL = Vector((0.0, 0.435, -0.035))


def _solve(M, g):
    """Gauss-Jordan for a small dense system M d = g."""
    n = len(g)
    A = [list(M[i]) + [g[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda i: abs(A[i][c]))
        A[c], A[p] = A[p], A[c]
        if abs(A[c][c]) < 1e-15:
            continue
        for i in range(n):
            if i != c:
                f = A[i][c] / A[c][c]
                A[i] = [a - f * b for a, b in zip(A[i], A[c])]
    return [A[i][n] / A[i][i] if abs(A[i][i]) > 1e-15 else 0.0 for i in range(n)]


class V:
    """Valdris's pose vocabulary, in real metres and degrees (converted to the s4lib pose dict)."""

    def __init__(self, K):
        self.K = K
        P = K.P
        self.sh = {s: P("shoulder_" + s) for s in "LR"}
        self.L1 = (P("elbow_L") - P("shoulder_L")).length
        self.L2 = (P("hand_L_tip") - P("elbow_L")).length
        self.last_stance = {}

    # -- arms ------------------------------------------------------------------------------------------------------------
    @staticmethod
    def d(el, az, side):
        sx = 1.0 if side == "L" else -1.0
        e, a = math.radians(el), math.radians(az)
        return Vector((sx * math.cos(e) * math.cos(a), -math.cos(e) * math.sin(a), math.sin(e)))

    def arm(self, side, upper, fore, back=(0.0, 0.0, 1.0), twist=0.0, space="chest"):
        """An arm from its upper-arm direction and forearm direction ((elevation, azimuth), azimuth 0 = out to the side,
        90 = forward), in the rest chest frame (it rides the posed chest). back: the direction the back of the hand
        faces in left-side terms (mirrored for the right arm); the right hand's (0, 0, 1) keeps the cannon upright."""
        du, df = self.d(*upper, side), self.d(*fore, side)
        E = self.sh[side] + du * self.L1
        T = E + df * self.L2
        Pp = E + du * 0.25
        b = Vector(back)
        if side == "R":
            b.x = -b.x
        s = self.sh[side]
        # _dirs: the directions themselves, interpolated with the key (VClip re-solves the target from them per frame)
        return {"arm_" + side: {"fist": tuple((T - s) / self.K.as_), "pole": tuple((Pp - s) / self.K.as_),
                                "back": tuple(b), "space": space, "twist": twist,
                                "_dirs": (float(upper[0]), float(upper[1]), float(fore[0]), float(fore[1]))}}

    def arm_from_dirs(self, side, spec):
        """Re-solve an interpolated chest-space arm spec's target and pole from its interpolated directions."""
        el_u, az_u, el_f, az_f = spec["_dirs"]
        du, df = self.d(el_u, az_u, side), self.d(el_f, az_f, side)
        E = self.sh[side] + du * self.L1
        s = self.sh[side]
        out = dict(spec)
        out["fist"] = tuple(((E + df * self.L2) - s) / self.K.as_)
        out["pole"] = tuple(((E + du * 0.25) - s) / self.K.as_)
        return out

    def arm_abs(self, side, target, pole, back=(0.0, 0.0, 1.0)):
        """An arm effector at an absolute hero-space point (metres, left-side terms): a fist on the ground or the anvil."""
        sx = 1.0 if side == "L" else -1.0
        T = Vector((sx * target[0], target[1], target[2]))
        Pp = Vector((sx * pole[0], pole[1], pole[2]))
        b = Vector((sx * back[0], back[1], back[2]))
        return {"arm_" + side: {"fist": tuple(T / self.K.ls), "pole": tuple(Pp / self.K.ls), "back": tuple(b),
                                "space": "abs"}}

    # -- pelvis, feet ----------------------------------------------------------------------------------------------------
    def pelvis(self, loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
        return {"pelvis": {"loc": tuple(v / self.K.ls for v in loc), "rot": tuple(rot)}}

    def foot(self, side, ball, yaw=10.0, roll=True, **kw):
        """ball (x outward, y) in metres, left-side terms: where the ball joint sits with the foot FLAT. A foot on the
        ground (no lift) with a heel raise rolls about the front edge of its sole (roll, SOLE_TIP), as a rigid sabaton
        must: the ball joint rises and moves forward, and the toe bone turns with the foot."""
        spec = {"yaw": yaw if side == "L" else -yaw, "lift": 0.0, "heel": 0.0, "toe": 0.0}
        # every field explicit: s4lib holds a missing field at the previous key's value, so a foot left out of "lift"
        # after an airborne key would stay in the air
        for k, v in kw.items():
            if k == "knee":
                v = (v[0] if side == "L" else -v[0], v[1], v[2])
            if k == "lift":
                v = v / self.K.ls
            spec[k] = v
        B, lift, toe = self.roll_ball(side, ball, yaw, spec["heel"], spec["lift"] * self.K.ls) if roll else (None, 0.0, 0.0)
        if B is None:
            x = ball[0] if side == "L" else -ball[0]
            spec["ball"] = (x / self.K.ls, ball[1] / self.K.ls)
        else:
            spec["ball"] = (B.x / self.K.ls, B.y / self.K.ls)
            spec["lift"] = spec["lift"] + lift / self.K.ls
            spec["toe"] = spec["toe"] + toe
        return {"foot_" + side: spec}

    def roll_ball(self, side, ball, yaw, heel, lift=0.0, w=1.0):
        """(ball joint to write, extra lift, toe) of a foot rolled `heel` degrees about an edge of its rigid sole, for a
        flat ball position `ball` (metres, left-side terms): heel > 0 (heel up) about the sole's front edge, heel < 0
        (toes up, a heel strike) about its rear edge; w blends the roll's offset in (0 = s4lib's own pivots). None when
        the foot is flat."""
        if heel == 0.0 or w <= 0.0:
            return None, 0.0, 0.0
        P, K = self.K.P, self.K
        sx = 1.0 if side == "L" else -1.0
        Rz = rot_world(0.0, sx * yaw, 0.0)
        br = P("ball_" + side)
        B0 = Vector((sx * ball[0], ball[1], float(br.z)))
        Rx = Matrix.Rotation(math.radians(heel), 3, "X")
        if heel > 0.0:
            T = B0 + Rz @ SOLE_TIP
            B = T + Rz @ (Rx @ (-SOLE_TIP))            # s4lib pivots a heel raise about the ball: write the ball there
        else:
            T = B0 + Rz @ SOLE_HEEL
            Bd = T + Rz @ (Rx @ (-SOLE_HEEL))            # where the ball joint must end up
            # s4lib pivots toes-up about its heel point hr (0.09 m behind the ankle, on the ground): the ball it is
            # given ends up at B + Rz (hr - br) + Rz Rx (br - hr), so give it the ball that lands on Bd
            hr = Vector((P("ankle_" + side).x, P("ankle_" + side).y + 0.09 * K.ls, 0.0))
            B = Bd - Rz @ (hr - br) - Rz @ (Rx @ (br - hr))
        B = B0 + (B - B0) * w
        rise = B.z - B0.z
        # s4lib: the toe bone pitch is heel * (1 - flat) - toe with flat = 1 - lift / 0.10 (Brax units): make it follow
        # the foot (the sole and the toe cap are one rigid front)
        flat = max(0.0, min(1.0, 1.0 - (lift + rise) / K.ls / 0.10))
        return B, rise, -heel * flat * w

    def ankle_of(self, side, ball, yaw):
        """World ankle point of a flat foot whose ball sits at `ball` (metres, left-side terms), yawed toes-out."""
        P = self.K.P
        sx = 1.0 if side == "L" else -1.0
        B = Vector((sx * ball[0], ball[1], float(P("ball_" + side).z)))
        Rz = rot_world(0.0, sx * yaw, 0.0)
        return B + Rz @ (P("ankle_" + side) - P("ball_" + side)), Rz

    def ankle_from_spec(self, side, spec):
        """World ankle point of a solver foot spec (s4lib.Solver.foot_frame, replicated from the landmarks)."""
        K, P = self.K, self.K.P
        yaw, heel = spec.get("yaw", 0.0), spec.get("heel", 0.0)
        Rz = Matrix.Rotation(math.radians(yaw), 3, "Z")
        Rf = Rz @ Matrix.Rotation(math.radians(heel), 3, "X")
        br, ar = P("ball_" + side), P("ankle_" + side)
        bx, by = spec["ball"]
        B = Vector((bx * K.ls, by * K.ls, br.z + max(0.0, spec.get("lift", 0.0)) * K.ls))
        if heel >= 0.0:
            return B + Rf @ (ar - br), Rz
        hr = Vector((ar.x, ar.y + 0.09 * K.ls, 0.0))
        Hp = B + Rz @ (hr - br)
        return Hp + Rf @ (ar - hr), Rz

    def shin_lean(self, side, spec, loc, rot, phi=10.0):
        """(forward lean of the shin, its rest lean), degrees in the foot's sagittal plane, for a solver foot spec and a
        pelvis at loc (metres) / rot, the knee bent as knee_fill bends it (s4lib's two_bone and pole formula)."""
        P = self.K.P
        L1 = (P("knee_L") - P("hip_L")).length
        L2 = (P("ankle_L") - P("knee_L")).length
        pel = P("pelvis")
        sx = 1.0 if side == "L" else -1.0
        A, Rz = self.ankle_from_spec(side, spec)
        S = pel + Vector(loc) + rot_world(*rot) @ (P("hip_" + side) - pel)
        fwd = Rz @ Vector((0.0, -1.0, 0.0))
        lat = Rz @ Vector((sx, 0.0, 0.0))
        w = (A - S).normalized()
        f_ = (fwd - w * fwd.dot(w)).normalized()
        l_ = (lat - w * lat.dot(w)).normalized()
        n = f_ * math.cos(math.radians(phi)) + l_ * math.sin(math.radians(phi))
        _F, _dl, mid = two_bone(S, A, (S + A) * 0.5 + n, L1, L2, -1)
        sv = mid - A
        v0 = Rz @ (P("knee_" + side) - P("ankle_" + side))
        return math.degrees(math.atan2(sv.dot(fwd), sv.z)), math.degrees(math.atan2(v0.dot(fwd), v0.z))

    def neutral_heel(self, side, ball, yaw, lift, loc, rot, phi=10.0, offset=0.0, fallback=0.0):
        """The heel angle at which a lifted foot's ankle keeps its rest angle to the shin (+ offset: + = the toes point
        further down), for a pelvis at loc (metres) / rot: a sabaton's greave drives into its foot shell past about 20 deg
        of flexion either way (stage 3), so a foot in the air hangs in line with its shin. The heel moves the ankle (the
        ball is the IK target), so it is a root of h - (lean(h) - rest lean) - offset, bisected on [-30, 150]; with no
        root there (the shin past the horizontal behind him) the fallback heel is kept."""
        def g(h):
            sp = self.foot(side, ball, yaw, lift=lift, heel=h)["foot_" + side]
            lean, lean0 = self.shin_lean(side, sp, loc, rot, phi)
            return h - (lean - lean0) - offset
        lo, hi = -30.0, 150.0
        glo, ghi = g(lo), g(hi)
        if glo > 0.0 or ghi < 0.0:
            return fallback
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            gm = g(mid)
            if gm > 0.0:
                hi = mid
            else:
                lo = mid
            if hi - lo < 0.1:
                break
        return 0.5 * (lo + hi)

    def knee_fill(self, pose, phi=10.0, sides="LR"):
        """Give every foot of a solver-space pose a knee hint that bends the knee in the plane phi degrees out from the
        foot's forward (about the hip -> ankle line), as V.stance does; returns the pose."""
        P = self.K.P
        pl = pose.get("pelvis", {})
        loc = Vector(pl.get("loc", (0.0, 0.0, 0.0))) * self.K.ls
        Rw = rot_world(*pl.get("rot", (0.0, 0.0, 0.0)))
        pel = P("pelvis")
        for side in sides:
            spec = pose.get("foot_" + side)
            if not spec or "ball" not in spec:
                continue
            sx = 1.0 if side == "L" else -1.0
            A, Rz = self.ankle_from_spec(side, spec)
            S = pel + loc + Rw @ (P("hip_" + side) - pel)
            fwd = Rz @ Vector((0.0, -1.0, 0.0))
            lat = Rz @ Vector((sx, 0.0, 0.0))
            w = (A - S).normalized()
            f_ = (fwd - w * fwd.dot(w)).normalized()
            l_ = (lat - w * lat.dot(w)).normalized()
            n = f_ * math.cos(math.radians(phi)) + l_ * math.sin(math.radians(phi))
            spec["knee"] = tuple(n - fwd - Vector((sx * 0.12, 0.0, 0.0)))
        return pose

    def stance(self, dz, rot=(0.0, 0.0, 0.0), fl=None, fr=None, tilt=(0.0, 0.0), dx=0.0, dy=0.0, kneel=None):
        """Pelvis + both feet, the flat feet PLANTED with their shins at the rest lean (+ tilt degrees forward):
        Valdris's sabaton instep lame and toe cap ride the shin (stage 3), so a shin tipped forward over a flat foot drives
        them into the ground (9 deg = 4 cm), and a knee falling in or out tips the lame's edge down. fl / fr: dicts (ball
        (x outward, y) in metres, yaw, optional heel / lift / toe / phi); a foot with a heel or a lift is free.
        Solved with s4lib's own leg IK (two_bone, Solver._leg's pole formula): damped least squares on the pelvis x / y
        and, per planted leg, the angle phi of the knee's bend plane about the hip -> ankle line (0 = the knee over the
        toes, + = out), so each planted shin keeps its rest forward and sideways lean; a sideways pelvis shift and a knee
        turned far off the toes cost a little. The result is written as the foot's "knee" hint. dx / dy shift the pelvis
        afterwards (a weight shift: the shins then lean a little). kneel {side: z}: dz is solved instead, so that the
        free (heel-up) leg's knee joint sits at height z (a knee on the ground)."""
        P = self.K.P
        L1 = (P("knee_L") - P("hip_L")).length
        L2 = (P("ankle_L") - P("knee_L")).length
        pel = P("pelvis")
        Rw = rot_world(*rot)
        feet = {"L": fl, "R": fr}
        legs = {}
        for side, t in (("L", tilt[0]), ("R", tilt[1])):
            f = feet[side]
            if f is None or f.get("lift", 0.0) or (f.get("heel", 0.0) and not f.get("plant")):
                continue
            yaw = f.get("yaw", 10.0)
            sx = 1.0 if side == "L" else -1.0
            # a planted foot may roll up onto the ball a little ("plant": True + heel): the ankle rises with it, so the
            # shin may tip forward by about the same angle before the instep lame reaches the ground
            A, Rz = self.ankle_from_spec(side, self.foot(side, f["ball"], yaw, heel=f.get("heel", 0.0))["foot_" + side])
            fwd = Rz @ Vector((0.0, -1.0, 0.0))
            lat = Rz @ Vector((1.0 if side == "L" else -1.0, 0.0, 0.0))
            v0 = Rz @ (P("knee_" + side) - P("ankle_" + side))
            want = (math.degrees(math.atan2(v0.dot(fwd), v0.z)) + t, math.degrees(math.atan2(v0.dot(lat), v0.z)))
            legs[side] = (A, fwd, lat, want)
        order = list(legs)

        def hip(side, x, y, z):
            return pel + Vector((x, y, z)) + Rw @ (P("hip_" + side) - pel)

        def knee_n(side, S, phi):
            A, fwd, lat, _w = legs[side]
            w = (A - S).normalized()
            f_ = (fwd - w * fwd.dot(w)).normalized()
            l_ = (lat - w * lat.dot(w)).normalized()
            return f_ * math.cos(math.radians(phi)) + l_ * math.sin(math.radians(phi))

        def solve_xy(z):
            def res(u):
                x, y = u[0], u[1]
                out = [x / 0.03]                          # 1 deg of lean is worth 3 cm of sideways pelvis shift
                for n, side in enumerate(order):
                    A, fwd, lat, want = legs[side]
                    S = hip(side, x, y, z)
                    phi = u[2 + n]
                    _F, _dl, mid = two_bone(S, A, (S + A) * 0.5 + knee_n(side, S, phi), L1, L2, -1)
                    sv = mid - A
                    out.append(math.degrees(math.atan2(sv.dot(fwd), sv.z)) - want[0])
                    out.append(math.degrees(math.atan2(sv.dot(lat), sv.z)) - want[1])
                    out.append((phi - 10.0) / 15.0)       # 15 deg of knee turn off the toes cost 1 deg of lean
                return out
            u = [0.0, 0.0] + [10.0] * len(order)
            e = 1e-5
            lam = 1e-3
            for _ in range(100):
                if not order:
                    break
                r = res(u)
                c0 = sum(q * q for q in r)
                J = []
                for k in range(len(u)):
                    u2 = list(u)
                    u2[k] += e
                    J.append([(a - b) / e for a, b in zip(res(u2), r)])
                n = len(u)
                M = [[sum(J[a][q] * J[b][q] for q in range(len(r))) + (lam if a == b else 0.0) for b in range(n)] for a in range(n)]
                g = [sum(J[a][q] * r[q] for q in range(len(r))) for a in range(n)]
                d = _solve(M, g)
                u_new = [a - b for a, b in zip(u, d)]
                c1 = sum(q * q for q in res(u_new))
                if c1 < c0:
                    u, lam = u_new, max(lam * 0.3, 1e-9)
                    if c0 - c1 < 1e-10:
                        break
                else:
                    lam *= 10.0
                    if lam > 1e6:
                        break
            return u, (res(u) if order else [])

        def free_knee(side, x, y, z):
            f = feet[side]
            spec = self.foot(side, f["ball"], f.get("yaw", 10.0), heel=f.get("heel", 0.0), lift=f.get("lift", 0.0))["foot_" + side]
            A, Rz = self.ankle_from_spec(side, spec)
            S = hip(side, x, y, z)
            sx = 1.0 if side == "L" else -1.0
            fwd, lat = Rz @ Vector((0.0, -1.0, 0.0)), Rz @ Vector((sx, 0.0, 0.0))
            w = (A - S).normalized()
            f_ = (fwd - w * fwd.dot(w)).normalized()
            l_ = (lat - w * lat.dot(w)).normalized()
            phi = math.radians(f.get("phi", 10.0))
            _F, _dl, mid = two_bone(S, A, (S + A) * 0.5 + f_ * math.cos(phi) + l_ * math.sin(phi), L1, L2, -1)
            return mid
        if kneel:
            (ks, kz), = kneel.items()
            lo, hi = -1.0, 0.0
            for _ in range(40):
                zm = 0.5 * (lo + hi)
                u, _r = solve_xy(zm)
                if free_knee(ks, u[0], u[1], zm).z > kz:
                    hi = zm
                else:
                    lo = zm
            dz = 0.5 * (lo + hi)
        u, r = solve_xy(dz)
        x, y = u[0], u[1]
        for side in "LR":
            f = feet[side]
            if f is not None and f.get("lift", 0.0) > 0.0 and not f.get("heel_abs"):
                # a foot in the air hangs in line with its shin (a flexed ankle drives the greave into the foot shell);
                # the heel it was given is added as an offset, scaled down (the keys were first written as absolute heels)
                feet[side] = dict(f, heel=self.neutral_heel(side, f["ball"], f.get("yaw", 10.0), f["lift"], (x + dx, y + dy, dz),
                                                            rot, f.get("phi", 10.0), 0.25 * f.get("heel", 0.0),
                                                            fallback=f.get("heel", 0.0)))
        self.last_stance = {"pelvis": (round(x, 4), round(y, 4), round(dz, 4)), "residual": [round(q, 2) for q in r],
                            "phi": {sd: round(u[2 + k], 1) for k, sd in enumerate(order)}}
        out = self.pelvis((x + dx, y + dy, dz), rot)
        for side in "LR":
            f = feet[side]
            if f is None:
                continue
            kw = {k: f[k] for k in ("heel", "lift", "toe") if k in f}
            yaw = f.get("yaw", 10.0)
            sx = 1.0 if side == "L" else -1.0
            if side in legs:
                S = hip(side, x, y, dz)
                nd = knee_n(side, S, u[2 + order.index(side)])
                fwd = legs[side][1]
                kn = nd - fwd - Vector((sx * 0.12, 0.0, 0.0))
                kw["knee"] = (kn.x * sx, kn.y, kn.z)      # left-side terms (foot() mirrors x back)
                _F, _dl, kp = two_bone(S, legs[side][0], (S + legs[side][0]) * 0.5 + nd, L1, L2, -1)
            else:
                kp = free_knee(side, x, y, dz)
            self.last_stance["knee_" + side] = tuple(round(c, 4) for c in kp)
            self.last_stance["hip_" + side] = tuple(round(c, 4) for c in hip(side, x, y, dz))
            out.update(self.foot(side, f["ball"], yaw, **kw))
            if side not in legs:                         # a lifted / heel-up foot: the knee in the plane phi out
                self.knee_fill(out, f.get("phi", 10.0), sides=side)
        return out

    def genuflect(self, front, hip_z, rot=(0.0, 0.0, 0.0), knee_z=0.13, heel=None, rear_x=0.37, tilt=2.0, rear_ball=None):
        """Down on the RIGHT knee (built, not solved): the left sabaton flat at `front` (ball, left-side terms) with its
        shin upright, the hips at height hip_z behind the left knee, the right knee joint at knee_z (the poleyn on the
        ground) straight below-behind the right hip, the right sabaton's toes planted behind it (heel up `heel` deg).
        -> (pose fragment: pelvis + both feet with knee hints, info {pelvis, knee_L, knee_R, ball_R})."""
        P = self.K.P
        L1 = (P("knee_L") - P("hip_L")).length
        L2 = (P("ankle_L") - P("knee_L")).length
        pel = P("pelvis")
        Rw = rot_world(*rot)
        yaw_l, yaw_r = 12.0, 8.0
        A_L, Rz = self.ankle_of("L", front, yaw_l)
        v0 = Rz @ (P("knee_L") - P("ankle_L"))
        ax = Rz @ Vector((1.0, 0.0, 0.0))
        K_L = A_L + Matrix.Rotation(math.radians(tilt), 3, ax) @ v0
        # the left hip on the thigh's circle behind the knee at hip_z; x from the pelvis shape
        hl = Rw @ (P("hip_L") - pel)
        dzh = hip_z - K_L.z
        back = math.sqrt(max(L1 * L1 - dzh * dzh, 0.0))
        S_L = Vector((K_L.x - 0.02, K_L.y + back, hip_z))
        # pelvis head from the left hip; then the right hip
        pel_w = S_L - hl
        off = pel_w - pel
        S_R = pel_w + Rw @ (P("hip_R") - pel)
        # the right knee on the ground behind-below its hip, then the ankle and ball from the heel-up foot
        dzr = S_R.z - knee_z
        assert dzr < L1, "genuflect: hip_z %.3f is too high for the right knee to reach %.3f" % (hip_z, knee_z)
        K_R = Vector((S_R.x, S_R.y + math.sqrt(L1 * L1 - dzr * dzr), knee_z))
        # the heel-up foot rolled onto the front edge of its sole (V.foot): the ankle relative to the FLAT ball position.
        # heel=None: the roll that keeps the ankle at its rest angle to the shin (the toes tucked under, the sabaton
        # upright), iterated because the ankle's height follows the roll
        Rzr = rot_world(0.0, -yaw_r, 0.0)
        fwd_r = Rzr @ Vector((0.0, -1.0, 0.0))
        v0r = Rzr @ (P("knee_R") - P("ankle_R"))
        lean0 = math.degrees(math.atan2(v0r.dot(fwd_r), v0r.z))
        h = 80.0 if heel is None else heel
        for _ in range(8 if heel is None else 1):
            Rf = Rzr @ Matrix.Rotation(math.radians(h), 3, "X")
            rel = Rzr @ SOLE_TIP + Rf @ (P("ankle_R") - P("ball_R") - SOLE_TIP)     # ankle - flat ball
            # the ankle sits on the shin's circle behind the knee at height ball.z + rel.z
            az_ = float(P("ball_R").z) + rel.z
            dzs = K_R.z - az_
            run = math.sqrt(max(L2 * L2 - dzs * dzs, 0.0))
            A_R = Vector((K_R.x - 0.01, K_R.y + run, az_))
            sv = K_R - A_R
            h = min(100.0, max(40.0, math.degrees(math.atan2(sv.dot(fwd_r), sv.z)) - lean0))
        heel = h
        B_R = A_R - rel
        if rear_ball is not None:
            # keep a planted rear foot where an earlier kneel put it (a variant of the kneel must not slide it); the
            # knee then lands where the IK puts it, near knee_z
            B_R = Vector((-rear_ball[0], rear_ball[1], float(P("ball_R").z)))
            A_R = B_R + rel
        pose = self.pelvis(tuple(off), rot)
        kl = self.knee_hint_to(K_L, S_L, A_L, Rz, "L")
        kr = self.knee_hint_to(K_R, S_R, A_R, Rzr, "R")
        pose.update(self.foot("L", front, yaw_l, knee=kl))
        pose.update(self.foot("R", (-B_R.x, B_R.y), yaw_r, heel=heel, knee=kr))
        return pose, {"pelvis": tuple(off), "knee_L": tuple(K_L), "knee_R": tuple(K_R), "ball_R": (-B_R.x, B_R.y), "heel_R": heel,
                      "hip_L": tuple(S_L), "hip_R": tuple(S_R)}

    @staticmethod
    def knee_hint_to(Kp, S, A, Rz, side):
        """foot() knee hint (left-side terms) that bends the IK's knee toward the point Kp (Solver._leg's pole formula)."""
        sx = 1.0 if side == "L" else -1.0
        fwd = Rz @ Vector((0.0, -1.0, 0.0))
        mid = (S + A) * 0.5
        n = (Kp - mid)
        w = (A - S).normalized()
        n = (n - w * n.dot(w)).normalized()
        kn = n - fwd - Vector((sx * 0.12, 0.0, 0.0))
        return (kn.x * sx, kn.y, kn.z)

    # -- torso, head, hands -------------------------------------------------------------------------------------------------
    @staticmethod
    def spine(fwd=0.0, twist=0.0, side=0.0):
        """Bend forward over the three spine bones; the twist stays low (spine_01 / 02: rig_report section 6)."""
        wf, wt, ws = (0.40, 0.35, 0.25), (0.60, 0.40, 0.0), (0.40, 0.35, 0.25)
        return {"spine_0%d" % (i + 1): {"rot": (fwd * wf[i], twist * wt[i], side * ws[i])} for i in range(3)}

    @staticmethod
    def head(nod=0.0, yaw=0.0, tilt=0.0):
        """FK head: 40 % on the neck, 60 % on the head (nod + = chin down; <= 5 deg before the beard meets the gorget)."""
        return {"neck": {"rot": (nod * 0.4, yaw * 0.4, tilt * 0.4)},
                "head": {"rot": (nod * 0.6, yaw * 0.6, tilt * 0.6), "wrot": (0.0, 0.0, 0.0), "ww": 0.0}}

    @staticmethod
    def clav(l=(0.0, 0.0, 0.0), r=None):
        """Clavicles in left-side terms (x: forward, z: up); moving one shifts that shoulder, so the arm's elbow changes a
        little (the arm targets ride the chest)."""
        r = r if r is not None else l
        return {"clavicle_L": {"rot": tuple(l)}, "clavicle_R": {"rot": (r[0], -r[1], -r[2])}}

    @staticmethod
    def fists(l=1.0, r=1.0):
        return {"fingers_L": l, "fingers_R": r}

    @staticmethod
    def pauldrons(l=0.0, r=None):
        """Keyed lift of the pauldron helpers (degrees, on top of their drive), for overhead arms (unique clips only)."""
        r = l if r is None else r
        return {"x_pauldron_L": {"rot": (0.0, 0.0, l)}, "x_pauldron_R": {"rot": (0.0, 0.0, -r)}}


class VClip(Clip):
    """A Clip whose chest-space arms interpolate by DIRECTION: s4lib interpolates effector targets as points, so a swing
    from a low fist to a raised one cut a straight line past the shoulder and folded the elbow to 90-120 deg, where
    Valdris's cannon cuff enters his upper-arm plate. Between two keys that both give an arm by its directions
    (V.arm), each frame's target is re-solved from the interpolated directions; segments that touch an absolute-space
    key (a fist planted on the ground) keep the point interpolation."""

    def __init__(self, v, *a, **kw):
        super().__init__(*a, **kw)
        self.v = v

    def poses(self, solver=None):
        out = super().poses(solver)
        if self.fn is not None or not self.keys:
            return out
        keys = sorted(self.keys, key=lambda k: k[0])
        if self.loop and keys[-1][0] != self.length:
            keys = keys + [(self.length, keys[0][1], keys[0][2])]
        for side in "LR":
            nm = "arm_" + side
            state, cur = [], None
            for _f, p, _o in keys:
                if nm in p:
                    cur = "_dirs" in p[nm] and p[nm].get("space", "chest") == "chest"
                state.append(cur)
            T = [k[0] for k in keys]
            for f, pose in enumerate(out):
                spec = pose.get(nm)
                if not spec or "_dirs" not in spec or spec.get("space", "chest") != "chest":
                    continue
                i = 0
                while i < len(T) - 2 and f > T[i + 1]:
                    i += 1
                if state[i] and state[min(i + 1, len(T) - 1)]:
                    pose[nm] = self.v.arm_from_dirs(side, spec)
        return out


# ---- Valdris's gait (adapted from s4_clips.locomotion) ------------------------------------------------------------------
def vloco(v, length, speed, direction=(0.0, -1.0), duty=0.5, half=0.30, base_y=-0.20, hip_yaw=0.0, foot_yaw=8.0,
          lift=0.14, lift_peak=0.45, heel_off=25.0, heel_start=0.45, heel_land=0.0, heel_swing=30.0, shift=0.0, match=1.0,
          bob=0.03, drop=0.06, sway=0.03, roll=2.0, pelvis_fwd=4.0, pelvis_twist=5.0, spine_fwd=4.0, spine_counter=4.0,
          counter=0.8, upper=None, phase0=0.0, phi=10.0, head=(-2.0, -8.0, 0.0), toe_swing=0.0, allow=3.0,
          swing_hang=True):
    """Per-frame pose function of an in-place gait cycle, in real metres / m/s (s4_clips.locomotion's model: phase 0 is
    the left touch-down, the planted foot moves under the body at exactly `speed` against `direction`, the swing is a
    Hermite curve whose end tangents match `match` x the ground speed). Valdris's changes: the knee bends in the plane
    `phi` degrees out from the toes (V.knee_fill), the heel starts to roll off at `heel_start` of the contact (his shin
    must not tip forward over a flat sabaton: the instep lame rides it), a pelvis roll toward the stance leg (`roll`),
    the FK head, and the spine carries the hip counter-turn low (V.spine). And the rolling foot: while a sabaton is planted
    its heel rises at least as far as its shin tips forward past the rest lean (+ `allow` degrees), so the instep lame
    on the shin never reaches the ground; that heel curve is dilated and smoothed over the cycle so the roll is
    continuous into the swing."""
    dx, dy = direction
    n = math.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    T = length / FPS
    Lc = speed * duty * T
    cyaw, syaw = math.cos(math.radians(hip_yaw)), math.sin(math.radians(hip_yaw))
    m = -Lc * (1.0 - duty) / duty * match
    a_, b_ = lift_peak * 3.0, (1.0 - lift_peak) * 3.0
    norm = (lift_peak ** a_) * ((1.0 - lift_peak) ** b_)
    ls = v.K.ls

    def spec(s, x, y, yaw, heel, lift, w):
        """Solver foot spec; a raised heel rolls the sabaton about the front edge of its sole (V.roll_ball), blended by w."""
        sgn = 1.0 if s == "L" else -1.0
        B, rise, toe = v.roll_ball(s, (sgn * x, y), sgn * yaw, heel, lift, w)
        if B is None:
            return {"ball": (x / ls, y / ls), "lift": max(0.0, lift) / ls, "yaw": yaw, "heel": heel, "toe": 0.0}
        return {"ball": (B.x / ls, B.y / ls), "lift": (max(0.0, lift) + rise) / ls, "yaw": yaw, "heel": heel, "toe": toe}

    def foot_at(ph, s, hmin=None, hsw=None):
        sgn = 1.0 if s == "L" else -1.0
        bx0, by0 = sgn * half, base_y
        bx, by = bx0 * cyaw - by0 * syaw, bx0 * syaw + by0 * cyaw
        yaw = hip_yaw + sgn * foot_yaw
        if ph < duty:
            u = ph / duty
            d = Lc * (0.5 - u) + shift
            h = heel_land * (1.0 - smooth(u / 0.3)) + heel_off * smooth((u - heel_start) / (1.0 - heel_start))
            if hmin is not None and h >= 0.0:
                h = max(h, hmin)
            return spec(s, bx + dx * d, by + dy * d, yaw, h, 0.0, 1.0)
        u = (ph - duty) / (1.0 - duty)
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        d = h00 * (-Lc * 0.5) + h10 * m + h01 * (Lc * 0.5) + h11 * m + shift
        ht = lift * (u ** a_) * ((1.0 - u) ** b_) / norm
        h = heel_off + (heel_swing - heel_off) * smooth(u / 0.35)
        h = h * (1.0 - smooth((u - 0.45) / 0.45)) + heel_land * smooth((u - 0.6) / 0.4)
        if hmin is not None and hmin > h and u < 0.5:
            h = h + (hmin - h) * (1.0 - smooth(u / 0.5))
        if hmin is not None and hmin > h and u >= 0.5 and heel_land >= 0.0:
            h = h + (hmin - h) * smooth((u - 0.5) / 0.5)
        if hsw is not None:
            wmid = smooth(u / 0.3) * (1.0 - smooth((u - 0.6) / 0.35))
            h = h + (hsw - h) * wmid
        # the roll about the sole's edges carries on through the swing: the rigid sole never dips under the foot's lift
        sp = spec(s, bx + dx * d, by + dy * d, yaw, h, max(0.0, ht), 1.0)
        sp["toe"] = sp["toe"] + toe_swing * math.sin(math.pi * u)
        return sp

    def pelvis_at(f):
        p = ((f % length) / length + phase0) % 1.0
        c1 = math.cos(2 * math.pi * p)
        z = -drop - bob * math.cos(4 * math.pi * (p - duty * 0.5))
        x = sway * math.cos(2 * math.pi * (p - duty * 0.5))
        side_roll = roll * math.cos(2 * math.pi * (p - duty * 0.5))
        return p, c1, side_roll, (x * cyaw, x * syaw, z), (pelvis_fwd, hip_yaw - pelvis_twist * c1, -side_roll)

    # the heel each planted sabaton needs so its shin stays within `allow` of the rest lean (V.shin_lean, iterated: the
    # roll lifts the ankle), per frame of the cycle; then dilated by a frame and smoothed [1, 2, 1] / 4 twice, cyclic
    HMIN = {}
    for s in ("L", "R"):
        raw = []
        for f in range(length):
            p, _c1, _sr, loc, rot = pelvis_at(f)
            ph = p if s == "L" else (p + 0.5) % 1.0
            need = 0.0
            if ph < duty:
                h = 0.0
                for _ in range(6):
                    sp = foot_at(ph, s, h)
                    lean, lean0 = v.shin_lean(s, sp, loc, rot, phi)
                    nh = max(0.0, lean - lean0 - allow)
                    if nh <= h + 0.2:
                        break
                    h = nh
                need = h
            raw.append(need)
        dil = [max(raw[(f - 1) % length], raw[f], raw[(f + 1) % length]) for f in range(length)]
        for _ in range(2):
            dil = [(dil[(f - 1) % length] + 2.0 * dil[f] + dil[(f + 1) % length]) / 4.0 for f in range(length)]
        HMIN[s] = dil
    # ...and in the swing, the heel that keeps the ankle at its rest angle to the shin (the foot hangs in line with it)
    HSW = {}
    for s in ("L", "R"):
        seq = []
        for f in range(length):
            p, _c1, _sr, loc, rot = pelvis_at(f)
            ph = p if s == "L" else (p + 0.5) % 1.0
            if ph < duty or not swing_hang:
                seq.append(None)
                continue
            h = 20.0
            for _ in range(6):
                sp = foot_at(ph, s, HMIN[s][f], h)
                lean, lean0 = v.shin_lean(s, sp, loc, rot, phi)
                nh = max(-20.0, min(90.0, lean - lean0))
                if abs(nh - h) < 0.3:
                    h = nh
                    break
                h = nh
            seq.append(h)
        HSW[s] = seq

    def fn(f):
        p, c1, side_roll, loc, rot = pelvis_at(f)
        x, y_, z = loc
        pose = {"pelvis": {"loc": (x / ls, y_ / ls, z / ls), "rot": rot},
                "foot_L": foot_at(p, "L", HMIN["L"][f % length], HSW["L"][f % length]),
                "foot_R": foot_at((p + 0.5) % 1.0, "R", HMIN["R"][f % length], HSW["R"][f % length])}
        pose.update(V.spine(spine_fwd, -hip_yaw * counter + spine_counter * c1, side_roll * 0.6))
        pose.update(V.head(*head))
        v.knee_fill(pose, phi)
        if upper:
            pose = merge(pose, upper(p, c1))
        return pose
    return fn

# ---- the library ----------------------------------------------------------------------------------------------------------
def build(K):
    """-> (shared {clip: Clip}, unique [Clip]) at Valdris's proportions and move speed."""
    v = V(K)
    C = {}
    U = []

    def clip(*a, **kw):
        return VClip(v, *a, **kw)

    # ---- arms ------------------------------------------------------------------------------------------------------
    # the cannon down the aim: upper arm out 38 deg and down 18, elbow ~33 deg (the stage-3 aim pose: the sleeve's rear
    # cuff stays out of the upper-arm plate), the back of the hand up so the cannon's clamps face the sky
    def aim(du=0.0, dfore=0.0, az=0.0, twist=0.0):
        return v.arm("R", (-15 + du, 38 + az), (-3 + dfore, 70 + az), twist=twist)

    def fist_low(du=0.0, az=0.0, dfore=0.0, f=1.0):
        return merge(v.arm("L", (-44 + du, 30 + az), (-12 + dfore, 78 + az), back=(0.5, -0.2, 1.0)), {"fingers_L": f})

    def cannon_hang(du=0.0, az=0.0, dfore=0.0):
        return v.arm("R", (-40 + du, 12 + az), (-50 + du + dfore, 22 + az), back=(0.5, -0.5, 0.7))

    def fist_hang(du=0.0, az=0.0, f=1.0):
        return merge(v.arm("L", (-42 + du, 14 + az), (-38 + du, 36 + az), back=(0.8, -0.3, 0.5)), {"fingers_L": f})

    FL, FR = (0.39, -0.30), (0.39, -0.22)
    RISE = 0.0

    # ---- stances -------------------------------------------------------------------------------------------------------
    # An upright shin puts all of a knee bend into the hips going back (his pelvis sits 0.21 m behind the balls of his
    # feet at rest and 0.29-0.40 m behind them in these stances), so the feet stand forward of the root to keep the pelvis
    # over it (Brax's stances drift <= 30 mm; locomotion blends into them)
    RB0 = (0.38, -0.25)                                       # the relaxed stance's feet
    def relaxed(dz=0.0, sway=0.0, lean=0.0, look=0.0, nod=0.0):
        st = v.stance(-0.02 + dz, (2.0 + lean * 0.3, 0.0, -sway * 1.5), {"ball": RB0, "yaw": 10.0},
                      {"ball": RB0, "yaw": 10.0}, tilt=(2.0, 2.0), dx=sway * 0.03)
        return merge(st, v.spine(2.0 + lean, sway * 2.0, sway * 1.0), v.head(nod, look * 18.0, 0.0), v.fists())

    def combat(dz=0.0, lean=0.0, twist=0.0, hip_yaw=0.0, fl=FL, fr=FR, heel_l=0.0, heel_r=0.0, lift_l=0.0,
               lift_r=0.0, px=0.0, py=0.0, yaw_l=16.0, yaw_r=18.0, nod=-2.0, look=-8.0, rise=RISE, hang=True):
        """Combat stance: a wide square base, the weight a little onto the balls of the sabatons (rise deg: the heels
        lift so the shins may tip forward as much, V.stance), the waist turned left so the cannon points down the aim.
        A foot given a heel or a lift steps / pushes and is free; a lifted foot hangs in line with its shin, its heel an
        offset (V.stance), unless hang=False."""
        def ft(ball, yaw, heel, lift):
            if heel or lift:
                return {"ball": ball, "yaw": yaw, "heel": heel, "lift": lift, "heel_abs": not hang}
            return {"ball": ball, "yaw": yaw, "heel": rise, "plant": True}
        st = v.stance(-0.05 + dz, (5.0 + lean * 0.4, 3.0 + hip_yaw, 0.0), ft(fl, yaw_l, heel_l, lift_l),
                      ft(fr, yaw_r, heel_r, lift_r), tilt=(1.5 + rise * 1.1, 1.5 + rise * 1.1), dx=px, dy=py)
        return merge(st, v.spine(8.0 + lean * 0.6, 9.0 + twist), v.head(nod, look, 0.0), v.clav())

    READY = merge(combat(), aim(), fist_low(), v.fists())

    def ready(**kw):
        return merge(combat(**kw), aim(), fist_low(), v.fists())

    def kneel(front, hip_z, lean, knee_z=0.28, twist=0.0, yaw=-16.0, heel=None, rear=None):
        """Down on the right knee (V.genuflect): the pose fragment and its geometry (rear: keep that rear ball)."""
        pose, info = v.genuflect(front, hip_z, (6.0 + lean * 0.4, yaw, 0.0), knee_z=knee_z, heel=heel, rear_ball=rear)
        return merge(pose, v.spine(6.0 + lean * 0.6, twist)), info

    def on_knee(kn, hip=None, out=0.20, up=0.12, t=0.12):
        """The left fist resting on the outside of the left thigh, t of the way from the knee (joint kn) to the hip."""
        hp = hip if hip is not None else (kn[0], kn[1] + 0.5, kn[2])
        p = [kn[i] + (hp[i] - kn[i]) * t for i in range(3)]
        return v.arm_abs("L", (p[0] + out, p[1], p[2] + up), (p[0] + 0.70, p[1] + 0.20, p[2] + 0.80), back=(0.6, -0.1, 0.8))

    # ================================================================================================================
    # shared: idles
    # ================================================================================================================
    def idle_key(breath, sway, look):
        return merge(relaxed(dz=-0.012 * breath, sway=sway, lean=-breath * 2.0, look=look, nod=-breath * 1.5),
                     v.clav((-breath * 2.0, 0.0, breath * 2.5)), cannon_hang(du=breath * 2.0),
                     fist_hang(du=breath * 2.0, f=1.0 - 0.15 * max(breath, 0.0)))
    C["idle"] = clip("idle", 120, loop=True, keys=[
        (0, idle_key(0, 0, 0), {}), (30, idle_key(1, 0.6, 0.3), {}), (58, idle_key(0.2, 1.0, 1.0), {}),
        (90, idle_key(-0.5, 0.1, -0.4), {})],
        purpose="relaxed heavy stance: slow deep breaths lift the pauldrons, the weight rolls between the feet, a slow look around",
        maps_to="alive, not moving, out of combat (no enemy near, no attack for 2 s; hub)")

    def combat_key(b, tw):
        return merge(combat(dz=-0.03 * b, lean=2.0 * b, hip_yaw=tw * 0.5, twist=-tw * 0.5), aim(du=-2.0 * b, dfore=-1.0 * b),
                     fist_low(du=3.0 * b), v.fists(), v.clav((0.0, 0.0, 1.5 * b)))
    C["idle_combat"] = clip("idle_combat", 40, loop=True, keys=[
        (0, combat_key(0, 0), {}), (10, combat_key(1, 1.5), {}), (20, combat_key(0, 0), {}), (30, combat_key(1, -1.5), {})],
        purpose="combat stance: planted wide, the cannon down the aim, a heavy breathing sink on the knees",
        maps_to="alive, not moving, in combat (enemies near or an attack in the last 2 s). Frame 0 is the reference "
                "pose of every upper-layer clip")

    # ================================================================================================================
    # shared: locomotion
    # ================================================================================================================
    def walk_arms(p, c1):
        return merge(cannon_hang(du=2.0 * abs(c1), az=-10.0 * c1), fist_hang(du=2.0 * abs(c1), az=12.0 * c1),
                     v.clav((3.0 * c1, 0.0, 0.0), (-3.0 * c1, 0.0, 0.0)), v.fists())
    walk_v = 1.8 * K.ls
    C["walk"] = clip("walk", 28, loop=True, travel=(0.0, -walk_v), speed=round(walk_v, 3),
                     fn=vloco(v, 28, walk_v, duty=0.62, half=0.31, base_y=-0.20, foot_yaw=9.0, lift=0.11, lift_peak=0.4,
                              heel_off=22.0, heel_start=0.38, heel_land=-8.0, heel_swing=14.0, bob=-0.015, drop=0.05,
                              sway=0.05, roll=3.0, pelvis_fwd=3.0, pelvis_twist=5.0, spine_fwd=3.0, spine_counter=4.0,
                              upper=walk_arms, phase0=0.16, head=(-1.0, 0.0, 0.0), swing_hang=False),
                     purpose="heavy walk: a wide rolling gait, the weight dropping onto each sabaton, the cannon swinging low",
                     maps_to="moving at under about 55 %% of move speed (stick partly pushed, slows); playback rate = speed / "
                             "%.2f m/s" % walk_v)

    def run_arms(p, c1):
        s2 = math.sin(4 * math.pi * p)
        return merge(aim(du=-3.0 * s2, dfore=-2.0 * s2), v.arm("L", (-44 - 4 * c1, 30 + 22 * c1), (-14 + 6 * c1, 76 + 10 * c1),
                                                            back=(0.5, -0.2, 1.0)),
                     v.clav((0.0, 0.0, -2.5 * s2)), v.fists())
    C["run"] = clip("run", 20, loop=True, travel=(0.0, -K.move_speed), speed=K.move_speed,
                    fn=vloco(v, 20, K.move_speed, duty=0.28, half=0.29, base_y=-0.18, foot_yaw=7.0, lift=0.17,
                             lift_peak=0.40, heel_off=30.0, heel_start=0.35, heel_land=0.0, heel_swing=32.0, shift=-0.06,
                             match=0.6, bob=0.045, drop=0.10, sway=0.035, roll=2.5, pelvis_fwd=9.0, pelvis_twist=6.0,
                             spine_fwd=6.0, spine_counter=5.0, upper=run_arms, phase0=0.30, head=(-3.0, -8.0, 0.0)),
                    purpose="juggernaut run: low and heavy, the pelvis sinks on every footfall, the cannon held down the aim, the fist pumping",
                    maps_to="moving within 45 deg of the aim at move speed; playback rate = speed / %.1f m/s" % K.move_speed)

    def strafe_arms(p, c1):
        s2 = math.sin(4 * math.pi * p)
        return merge(aim(du=-2.5 * s2), fist_low(du=2.0 * s2), v.clav((0.0, 0.0, -2.0 * s2)), v.fists())
    strafe = dict(duty=0.25, half=0.33, base_y=-0.14, foot_yaw=5.0, lift=0.21, lift_peak=0.45, heel_off=24.0,
                  heel_start=0.35, heel_land=0.0, heel_swing=24.0, match=0.6, bob=0.04, drop=0.13, sway=0.0, roll=0.0,
                  pelvis_fwd=6.0, pelvis_twist=4.0, spine_fwd=6.0, spine_counter=3.0, counter=0.75, upper=strafe_arms,
                  phase0=0.30)
    C["strafe_left"] = clip("strafe_left", 18, loop=True, travel=(K.move_speed, 0.0), speed=K.move_speed,
                            fn=vloco(v, 18, K.move_speed, direction=(1.0, 0.0), hip_yaw=40.0, head=(-2.0, -14.0, 0.0), **strafe),
                            purpose="side run to his left: the hips open toward the travel, the chest and the cannon kept on the aim",
                            maps_to="moving 45-135 deg to the left of the aim; playback rate = speed / %.1f m/s" % K.move_speed)
    C["strafe_right"] = clip("strafe_right", 18, loop=True, travel=(-K.move_speed, 0.0), speed=K.move_speed,
                             fn=vloco(v, 18, K.move_speed, direction=(-1.0, 0.0), hip_yaw=-40.0, head=(-2.0, 0.0, 0.0), **strafe),
                             purpose="side run to his right (the chest and the cannon kept on the aim)",
                             maps_to="moving 45-135 deg to the right of the aim; playback rate = speed / %.1f m/s" % K.move_speed)
    C["backpedal"] = clip("backpedal", 18, loop=True, travel=(0.0, K.move_speed), speed=K.move_speed,
                          fn=vloco(v, 18, K.move_speed, direction=(0.0, 1.0), duty=0.27, half=0.30, base_y=-0.20,
                                   foot_yaw=9.0, lift=0.15, lift_peak=0.5, heel_off=12.0, heel_start=0.5, heel_land=16.0,
                                   heel_swing=24.0, match=0.6, bob=0.03, drop=0.13, sway=0.02, roll=1.5, pelvis_fwd=8.0,
                                   pelvis_twist=4.0, spine_fwd=6.0, spine_counter=3.0, upper=strafe_arms, phase0=0.30),
                          purpose="heavy backpedal: short driving steps, the weight forward over the cannon, the cannon on the aim",
                          maps_to="moving more than 135 deg away from the aim; playback rate = speed / %.1f m/s" % K.move_speed)

    # ================================================================================================================
    # shared: dash
    # ================================================================================================================
    # a bull rush: the body drops and drives behind the anvil and both pauldrons like a ram, the cannon held low and
    # forward, the fist tucked by the left tasset
    def rush(dz, lean, fl, fr, lift_l, lift_r, heel_l, heel_r, az=0.0):
        st = v.stance(dz, (10.0 + lean * 0.4, 0.0, 0.0), {"ball": fl, "yaw": 8.0, "lift": lift_l, "heel": heel_l, "heel_abs": True},
                      {"ball": fr, "yaw": 10.0, "lift": lift_r, "heel": heel_r, "heel_abs": True})
        return merge(st, v.spine(8.0 + lean * 0.5, 4.0), v.head(-6.0, -4.0, 0.0), v.clav((6.0, 0.0, 2.0)),
                     v.arm("R", (-20, 36 + az), (-10, 58 + az)), v.arm("L", (-30, 22 + az), (-16, 56 + az), back=(0.5, -0.3, 1.0)),
                     v.fists())
    DASH = rush(-0.16, 2.0, (0.35, -0.62), (0.33, 0.20), 0.06, 0.10, 10.0, 55.0)
    DASH2 = rush(-0.18, 4.0, (0.36, -0.56), (0.34, 0.18), 0.05, 0.14, 8.0, 60.0)
    C["dash"] = clip("dash", 8, keys=[(0, READY, {}), (2, DASH, {}), (8, DASH2, {})],
                     purpose="the dash burst: a low bull rush behind the anvil and both pauldrons, the cannon low and forward",
                     maps_to="the 0.16 s dash (MoverState.dash_left > 0); the client faces the hero along the dash for its duration",
                     events={"launch": 1}, grounded=False)
    LAND = merge(combat(dz=-0.14, lean=14.0, lift_r=0.12, heel_r=30.0, fr=(0.39, 0.04), hang=False),
                 aim(du=-4.0, dfore=-4.0, az=-12.0), fist_low(du=-2.0), v.head(-4.0, -6.0, 0.0), v.clav((4.0, 0.0, -2.0)))
    C["dash_recover"] = clip("dash_recover", 16, keys=[
        (0, DASH2, {}), (3, LAND, {"t": 0.6}),
        (7, merge(combat(dz=-0.12, lean=10.0), aim(du=-6.0, dfore=-8.0), fist_low()), {"t": 0.7}),
        (11, merge(combat(dz=-0.03, lean=2.0), aim(), fist_low()), {}), (16, READY, {})],
        purpose="out of the dash: the lead sabaton slams down, the rear one after it, a heavy absorb on both knees",
        maps_to="the first 0.5 s after a dash ends when the hero is not moving on (else blend into locomotion)",
        events={"land": 3})

    # ================================================================================================================
    # shared: fire (upper layer: first and last frame = idle_combat frame 0; the recoil itself is procedural in Bevy)
    # ================================================================================================================
    def kick(k, lean=0.0):
        """The cannon's kick: the muzzle rides up, the upper arm and the right shoulder are driven back."""
        return merge(combat(lean=-3.0 * k + lean, twist=-4.0 * k), aim(du=3.0 * k, dfore=10.0 * k, az=-6.0 * k),
                     fist_low(du=2.0 * k), v.clav((0.0, 0.0, 0.0), (-6.0 * k, 0.0, 3.0 * k)), v.head(-2.0 - 2.0 * k, -8.0, 0.0))
    C["fire_light"] = clip("fire_light", 8, layer="upper", keys=[
        (0, READY, {}), (1, kick(1.0), LIN), (3, kick(0.55), {}), (8, READY, {})],
        purpose="a cannon shot: the muzzle kicks up, the shoulder and chest take it, the weight settles back (recoil stays procedural)",
        maps_to="each primary shot of a light chassis (fire_rate >= 2/s): the colossus_cannon's 2.6 shots/s",
        events={"shot": 1})
    FH_BRACE = merge(combat(dz=-0.04, lean=8.0, twist=2.0), aim(du=-2.0, dfore=-2.0), fist_low(du=4.0, f=1.0),
                     v.clav((4.0, 0.0, -2.0)), v.head(-4.0, -8.0, 0.0))
    FH_KICK = merge(combat(dz=-0.02, lean=-10.0, twist=-8.0), aim(du=6.0, dfore=18.0, az=-10.0), fist_low(du=6.0),
                    v.clav((-4.0, 0.0, 3.0), (-10.0, 0.0, 6.0)), v.head(-6.0, -8.0, 0.0))
    C["fire_heavy"] = clip("fire_heavy", 18, layer="upper", keys=[
        (0, READY, {}), (5, FH_BRACE, HOLD), (6, FH_KICK, LIN), (9, merge(FH_KICK, combat(dz=-0.05, lean=-4.0, twist=-4.0),
                                                                          aim(du=4.0, dfore=10.0, az=-6.0)), {}),
        (18, READY, {})],
        purpose="a heavy shot: brace into it, the cannon bucks up and drives the shoulder back, a slow settle",
        maps_to="a heavy / charged release (fire_rate < 1/s, charge release, splash chassis)",
        events={"shot": 6})

    def charge_key(k):
        return merge(combat(dz=-0.05, lean=6.0, twist=2.0 + 1.0 * k), aim(du=-2.0 + 1.0 * k, dfore=-3.0 + 1.5 * k),
                     fist_low(du=5.0 - 1.0 * k), v.clav((3.0, 0.0, -1.0 + k)), v.head(-4.0, -8.0, 0.0))
    C["fire_charge"] = clip("fire_charge", 24, loop=True, layer="upper", keys=[
        (0, charge_key(0), {}), (6, charge_key(1), {}), (12, charge_key(0), {}), (18, charge_key(1), {})],
        purpose="holding a charge: braced into the cannon, the fist clenched, the barrel trembling with stored power",
        maps_to="fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy)")

    # ================================================================================================================
    # shared: hits
    # ================================================================================================================
    HL = merge(combat(lean=-7.0, twist=-6.0), aim(du=4.0, dfore=4.0, az=-6.0), fist_low(du=6.0, az=-6.0),
               v.clav((-4.0, 0.0, 4.0)), v.head(-6.0, 0.0, 4.0))
    C["hit_light"] = clip("hit_light", 12, layer="upper", keys=[
        (0, READY, {}), (2, HL, {}), (5, merge(combat(lean=3.0, twist=-2.0), aim(du=-2.0), fist_low(), v.head(0.0, -6.0, 0.0)), {}),
        (12, READY, {})],
        purpose="a flinch: the chest and pauldrons rock back, the cannon knocked off the aim, absorbed at once",
        maps_to="PlayerFlags::HIT on a light hit (damage < 10 % max HP), layered over whatever plays",
        events={"impact": 1})
    HH1 = merge(combat(dz=0.0, lean=-12.0, twist=-8.0, fl=(0.39, -0.24), lift_l=0.10),
                aim(du=10.0, dfore=16.0, az=-12.0), v.arm("L", (-30, 20), (-6, 50), back=(0.7, -0.2, 0.7)),
                v.clav((-6.0, 0.0, 6.0)), v.head(-8.0, -4.0, 0.0))
    HH2 = merge(combat(dz=-0.06, lean=-2.0, twist=-4.0, fl=(0.39, -0.14)), aim(du=4.0, dfore=6.0, az=-8.0),
                fist_low(du=4.0, az=-10.0), v.head(-4.0, -6.0, 0.0))
    HH3 = merge(combat(dz=-0.16, lean=14.0, twist=0.0, fl=(0.39, -0.14)), aim(du=-6.0, dfore=-10.0), fist_low(du=-2.0),
                v.clav((4.0, 0.0, -2.0)), v.head(-2.0, -8.0, 0.0))
    HH4 = merge(combat(dz=-0.08, lean=6.0, fl=(0.39, -0.22), lift_l=0.08), aim(du=-2.0), fist_low())
    C["hit_heavy"] = clip("hit_heavy", 30, keys=[
        (0, READY, {}), (3, HH1, {}), (8, HH2, {"t": 0.8}), (14, HH3, {}), (20, HH4, {}),
        (24, merge(HH4, combat(dz=-0.06, lean=3.0)), {"t": 0.8}), (30, READY, {})],
        purpose="a big stagger: rocked back, the lead sabaton steps back, a deep absorb on both knees, stepping back in",
        maps_to="PlayerFlags::HIT on a heavy hit (damage >= 10 % max HP or a stun); interrupts upper-layer clips",
        events={"impact": 1})

    # ================================================================================================================
    # shared: knockdown / get up (a juggernaut is floored to one knee, not onto his back: 137 plates and a 0.35 m anvil;
    # his 0.67 m arms cannot reach the ground from a kneel, so the fist rests on the knee and the cannon props him up)
    # ================================================================================================================
    # the knock: rocked back off the lead foot, a stagger step back with the right, then down onto the right knee. A
    # genuflection needs the feet about 1.1 m apart front to back, so the right sabaton steps well back (and the pelvis
    # travels back with it: he is knocked back)
    KDF = (0.39, -0.16)                                       # where the rocked-back lead foot lands
    KN, KNI = kneel(KDF, 0.74, 6.0)
    KNB, KNBI = kneel(KDF, 0.72, 9.0, knee_z=0.27, rear=KNI["ball_R"])
    RB = KNI["ball_R"]                                        # the right sabaton's toes, planted behind
    PROP = v.arm("R", (-46, 10), (-72, 14), back=(0.6, -0.5, 0.6))    # the cannon propped muzzle-down beside him
    KD1 = merge(combat(lean=-16.0, twist=-10.0, fl=(0.39, -0.22), lift_l=0.12), aim(du=12.0, dfore=20.0, az=-14.0),
                v.arm("L", (-26, 16), (-2, 40), back=(0.7, -0.2, 0.7)), v.clav((-6.0, 0.0, 8.0)), v.head(-8.0, 0.0, 0.0))
    KD2 = merge(combat(dz=-0.12, lean=-4.0, twist=-6.0, fl=KDF, fr=(RB[0], 0.5 * (RB[1] + FR[1])), lift_r=0.22, heel_r=65.0,
                       hang=False),
                aim(du=6.0, dfore=10.0, az=-10.0), v.arm("L", (-40, 22), (-30, 50), back=(0.7, -0.2, 0.7)),
                v.head(-4.0, 0.0, 0.0))
    KNEEL = merge(KN, PROP, on_knee(KNI["knee_L"], KNI["hip_L"]), v.clav((6.0, 0.0, -4.0)), v.head(3.0, 6.0, 0.0), v.fists())
    KNEEL_B = merge(KNB, PROP, on_knee(KNBI["knee_L"], KNBI["hip_L"]), v.clav((8.0, 0.0, -5.0)), v.head(4.0, 6.0, 0.0), v.fists())
    C["knockdown"] = clip("knockdown", 36, keys=[
        (0, READY, {}), (3, KD1, {}), (9, KD2, {}), (14, KNEEL_B, {"lin_in": True}), (18, KNEEL, {}),
        (26, merge(KNEEL, v.head(2.0, 8.0, 0.0)), {"t": 0.8}), (36, merge(KNEEL, v.head(2.0, 8.0, 0.0)), HOLD)],
        purpose="floored: rocked back off the lead foot, a stagger step back, then crashing down onto one knee, propped on the cannon",
        maps_to="a knockback / launch strong enough to floor the hero (stun >= 0.8 s); holds its last frame until get_up",
        events={"impact": 1, "ground": 14})
    GU1n, GU1i = kneel(KDF, 0.76, 10.0, knee_z=0.30, rear=KNI["ball_R"])
    GU1 = merge(GU1n, PROP, on_knee(GU1i["knee_L"], GU1i["hip_L"], up=0.16), v.clav((8.0, 0.0, -4.0)), v.head(2.0, 4.0, 0.0), v.fists())
    GU2 = merge(combat(dz=-0.24, lean=20.0, fl=KDF, fr=(RB[0], 0.5 * (RB[1] + FR[1])), lift_r=0.20, heel_r=65.0, rise=RISE,
                       hang=False),
                v.arm("R", (-44, 24), (-52, 40)), fist_low(du=-2.0), v.head(0.0, -4.0, 0.0))
    GU3 = merge(combat(dz=-0.14, lean=10.0, fl=KDF), aim(du=-6.0, dfore=-8.0), fist_low())
    GU4 = merge(combat(dz=-0.08, lean=6.0, fl=(0.39, -0.23), lift_l=0.10, heel_l=8.0), aim(du=-3.0), fist_low())
    C["get_up"] = clip("get_up", 40, keys=[
        (0, merge(KNEEL, v.head(2.0, 8.0, 0.0)), {}), (8, GU1, {"t": 0.6}), (15, GU2, {}), (20, GU3, {"lin_in": True}),
        (26, GU4, {}), (30, merge(combat(dz=-0.05, lean=3.0), aim(du=-2.0), fist_low()), {"lin_in": True}),
        (40, READY, {})],
        purpose="shoving up off the knee, the rear sabaton stamps forward under him, the lead foot resets, back into the stance",
        maps_to="the knockdown's stun ends",
        events={"stand": 30})

    # ================================================================================================================
    # shared: death / downed / revive / reforge
    # ================================================================================================================
    D1 = merge(combat(lean=-14.0, twist=-8.0, fl=(0.39, -0.22), lift_l=0.12), aim(du=10.0, dfore=18.0, az=-12.0),
               v.arm("L", (-30, 18), (-6, 44), back=(0.7, -0.2, 0.7)), v.clav((-6.0, 0.0, 8.0)), v.head(-8.0, 6.0, 0.0))
    D2 = merge(combat(dz=-0.16, lean=2.0, twist=-2.0, fl=KDF, fr=(RB[0], 0.5 * (RB[1] + FR[1])), lift_r=0.20, heel_r=65.0,
                      hang=False),
               v.arm("R", (-40, 26), (-54, 40), back=(0.6, -0.4, 0.6)),
               v.arm("L", (-44, 22), (-44, 40), back=(0.8, -0.3, 0.5)), v.fists(0.8), v.head(2.0, 4.0, 0.0))
    DKn, DKi = kneel(KDF, 0.74, 7.0)
    DSn, DSi = kneel(KDF, 0.71, 13.0, knee_z=0.27, twist=-6.0, rear=DKi["ball_R"])
    DKNEEL = merge(DKn, PROP, v.arm("L", (-46, 20), (-60, 40), back=(0.8, -0.3, 0.5)), v.fists(0.7),
                   v.head(4.0, 6.0, 0.0), v.clav((4.0, 0.0, -4.0)))
    DSLUMP = merge(DSn, v.arm("R", (-46, 6), (-74, 8), back=(0.6, -0.5, 0.6)), v.arm("L", (-46, 28), (-64, 48), back=(0.8, -0.3, 0.5)),
                   v.fists(0.6), v.head(5.0, 12.0, 5.0), v.clav((10.0, 0.0, -8.0)))
    C["death"] = clip("death", 56, keys=[
        (0, READY, {}), (4, D1, {}), (11, D2, {}), (17, DKNEEL, {"lin_in": True}), (21, merge(DKNEEL, DKn), {}),
        (32, DSLUMP, {"t": 0.4}), (38, merge(DSLUMP, kneel(KDF, 0.70, 14.0, knee_z=0.27, twist=-6.0, rear=DKi["ball_R"])[0]), {}),
        (56, DSLUMP, HOLD)],
        purpose="the fatal blow: rocked back, a knee gives and he crashes down onto it, then slumps over his knee and the cannon, a statue",
        maps_to="LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look)",
        events={"impact": 1, "knee": 17, "slump": 32})

    def wraith(b, sw, ad):
        st = v.stance(-0.26 + 0.05 * b, (18.0, 4.0 * sw, 3.0 * sw),
                      {"ball": (0.32, 0.36 + 0.03 * b), "yaw": 6.0, "lift": 0.18 + 0.05 * b, "heel": 64.0, "phi": 0.0, "heel_abs": True},
                      {"ball": (0.32, 0.44 - 0.03 * b), "yaw": 8.0, "lift": 0.14 + 0.05 * b, "heel": 70.0, "phi": 0.0, "heel_abs": True})
        return merge(st, v.spine(16.0, -3.0 * sw, 4.0 * sw), v.head(4.0, 8.0 * sw, 0.0),
                     v.arm("R", (-38, -4 + 4 * ad), (-52, 4 + 4 * ad), back=(0.6, -0.4, 0.6)),
                     v.arm("L", (-44, 8 - 4 * ad), (-52, 20 - 4 * ad), back=(0.8, -0.3, 0.5)), v.fists(0.8),
                     v.clav((6.0, 0.0, -6.0)))
    C["downed"] = clip("downed", 60, loop=True, keys=[
        (0, wraith(0, 0, 0), {}), (15, wraith(1, 0.6, 1), {}), (30, wraith(0.2, 0, 0), {}), (45, wraith(0.9, -0.6, -1), {})],
        purpose="the wraith drift: slumped, floating off the ground, the cannon and the fist hanging, a slow heavy bob",
        maps_to="LifeState::Downed (the Soul-Tether wraith; moves at 45 % speed with no gait, the client adds the ghost material)",
        grounded=False)
    RV1 = merge(v.stance(-0.10, (-6.0, 0.0, 0.0), {"ball": (0.37, -0.18), "yaw": 12.0, "lift": 0.24, "heel": 40.0},
                         {"ball": (0.37, 0.04), "yaw": 14.0, "lift": 0.20, "heel": 50.0}),
                v.spine(-8.0), v.head(-6.0, 0.0, 0.0), v.arm("R", (-20, 10), (-12, 20)),
                v.arm("L", (-20, 10), (-8, 24), back=(0.7, -0.2, 0.7)), v.clav((-6.0, 0.0, 8.0)), v.fists())
    RV2 = merge(combat(dz=-0.22, lean=16.0), aim(du=-10.0, dfore=-16.0), fist_low(du=-2.0), v.head(0.0, -8.0, 0.0))
    C["revive"] = clip("revive", 40, keys=[
        (0, wraith(0, 0, 0), {}), (6, RV1, {}), (12, RV2, {"t": 0.8, "lin_in": True}),
        (22, merge(combat(dz=-0.08, lean=6.0), aim(du=-3.0), fist_low()), {}),
        (30, READY, {}), (34, merge(ready(), v.head(-2.0, 4.0, 0.0)), {}), (40, READY, {})],
        purpose="dragged back into the body: a jolt, the sabatons slam down, a deep crouch, up into the stance",
        maps_to="an ally completes the Soul-Tether revive (Downed -> Alive)",
        events={"jolt": 6, "land": 12})
    # forged anew: he appears down on one knee (the lead foot back where the combat stance wants it after one step)
    SUn, SUi = kneel((0.39, -0.16), 0.74, 7.0)
    SUPER = merge(SUn, PROP, on_knee(SUi["knee_L"], SUi["hip_L"]), v.clav((6.0, 0.0, -4.0)), v.head(3.0, 0.0, 0.0), v.fists())
    SU2n, SU2i = kneel((0.39, -0.16), 0.75, 6.0, knee_z=0.29, rear=SUi["ball_R"])
    RB2 = SUi["ball_R"]
    FLARE = merge(combat(dz=-0.02, lean=-8.0), v.arm("R", (24, 12), (34, 18)), v.arm("L", (24, 12), (38, 20), back=(0.4, 0.4, 0.8)),
                  v.clav((-6.0, 0.0, 6.0)), v.head(-6.0, 0.0, 0.0), v.fists())
    C["reforge_in"] = clip("reforge_in", 46, keys=[
        (0, SUPER, {}), (9, merge(SUPER, SU2n, on_knee(SU2i["knee_L"], SU2i["hip_L"])), HOLD),
        (15, merge(combat(dz=-0.24, lean=18.0, fl=(0.39, -0.16), fr=(RB2[0], 0.5 * (RB2[1] + FR[1])), lift_r=0.20, heel_r=65.0, hang=False), v.arm("R", (-44, 24), (-50, 40)), fist_low(du=-2.0), v.head(0.0, -2.0, 0.0)), {}),
        (20, merge(combat(dz=-0.12, lean=6.0, fl=(0.39, -0.16)), aim(du=-6.0), fist_low()), {"lin_in": True}),
        (23, merge(combat(dz=-0.06, lean=0.0, fl=(0.39, -0.23), lift_l=0.10, heel_l=8.0), aim(du=-4.0), fist_low()), {}),
        (26, FLARE, {"lin_in": True}), (31, merge(FLARE, combat(dz=-0.04, lean=-10.0), v.head(-7.0, 0.0, 0.0)), HOLD),
        (39, merge(combat(), aim(du=-2.0), fist_low()), {}), (46, READY, {})],
        purpose="forged anew: rises off one knee (propped on the cannon), stamps in and throws both arms wide as the seams flare",
        maps_to="LifeState::Reforging ends: the hero reappears next to an ally",
        events={"stand": 20, "flare": 26})

    # ================================================================================================================
    # shared: victory / social / world
    # ================================================================================================================
    V_LOAD = merge(combat(dz=-0.12, lean=10.0), aim(du=-12.0, dfore=-16.0), fist_low(du=-2.0), v.head(2.0, -6.0, 0.0),
                   v.clav((4.0, 0.0, -3.0)))
    V_UP = merge(combat(dz=0.0, lean=-8.0, twist=-4.0), v.arm("R", (20, 32), (34, 44), back=(0.2, 0.6, 0.8)), v.arm("L", (18, 36), (36, 52), back=(0.2, 0.7, 0.6)),
                 v.clav((-6.0, 0.0, 7.0)), v.head(-8.0, 0.0, 0.0), v.fists())
    V_HOLD = merge(V_UP, combat(dz=-0.03, lean=-6.0, twist=-4.0), v.arm("R", (18, 32), (32, 44), back=(0.2, 0.6, 0.8)), v.head(-6.0, 4.0, 0.0))
    C["victory"] = clip("victory", 60, keys=[
        (0, READY, {}), (10, V_LOAD, HOLD), (17, V_UP, {}), (24, V_HOLD, {}),
        (42, merge(V_HOLD, combat(dz=-0.04, lean=-5.0, twist=-4.0)), {}), (60, V_HOLD, HOLD)],
        purpose="the roar: a crouch, then the cannon and the fist thrown up to the sky, chest out; holds the pose",
        maps_to="the run is won (GameEvent victory / boss down, results screen); holds its last frame",
        events={"roar": 17})
    PING = merge(combat(twist=-6.0), aim(du=-2.0), v.arm("L", (10, 34), (14, 60), back=(0.1, 0.1, 1.0)), {"fingers_L": 0.0},
                 v.head(-2.0, 6.0, 0.0), v.clav((4.0, 0.0, 2.0)))
    C["ping"] = clip("ping", 20, layer="upper", keys=[
        (0, READY, {}), (2, merge(ready(twist=-2.0), v.arm("L", (-24, 32), (-8, 66), back=(0.4, -0.2, 1.0))), {}), (5, PING, {}),
        (14, merge(PING, v.arm("L", (9, 34), (13, 60), back=(0.1, 0.1, 1.0))), HOLD),
        (17, merge(ready(twist=-2.0), v.arm("L", (-24, 32), (-8, 68), back=(0.4, -0.2, 1.0)), {"fingers_L": 1.0}), {}), (20, READY, {})],
        purpose="a ping: the left gauntlet thrusts out with the hand open, pointing ahead, the head follows",
        maps_to="the ping / marker input (party callout)",
        events={"ping": 5})
    # the shared anvil: its top at 1.07 m. His own anvil plate stands 0.35 m off his chest and his arms are short, so he
    # sinks low and presses the LEFT fist onto the near-left of it, outside his anvil's horn; the cannon braces at his side
    I_POINT = (0.70, -0.60, 1.07)
    IFL = (0.40, -0.56)                                       # the left sabaton steps in toward the anvil

    def anvil_stance(dz, lean, fl=IFL, lift=0.0, heel=0.0):
        st = v.stance(dz, (6.0 + lean * 0.3, -6.0, 0.0), {"ball": fl, "yaw": 10.0, "lift": lift, "heel": heel},
                      {"ball": RB0, "yaw": 10.0}, tilt=(2.0, 2.0))
        return merge(st, v.spine(4.0 + lean, -8.0), v.fists())
    I_STEP = merge(anvil_stance(-0.06, 6.0, fl=(0.39, -0.40), lift=0.14, heel=8.0), v.head(2.0, 8.0, 0.0), cannon_hang(du=2.0, az=10.0),
                   fist_hang(du=10.0, az=20.0), v.clav((2.0, 0.0, 0.0)))
    I_REACH = merge(anvil_stance(-0.12, 14.0), v.head(3.0, 10.0, 0.0), cannon_hang(du=2.0, az=10.0),
                    v.arm_abs("L", (0.72, -0.58, 1.18), (1.2, 0.2, 1.6), back=(0.2, -0.9, 0.3)), v.clav((6.0, 0.0, -2.0)))
    I_PRESS = merge(anvil_stance(-0.16, 18.0), v.head(4.0, 10.0, 0.0), cannon_hang(du=2.0, az=12.0),
                    v.arm_abs("L", I_POINT, (1.2, 0.2, 1.6), back=(0.2, -0.9, 0.3)), v.clav((8.0, 0.0, -4.0)))
    I_BACK = merge(relaxed(dz=-0.04), v.foot("L", (0.39, -0.33), 10.0, lift=0.12, heel=8.0), cannon_hang(), fist_hang(du=6.0, az=12.0),
                   v.clav((0.0, 0.0, 1.0)))
    C["interact"] = clip("interact", 40, keys=[
        (0, idle_key(0, 0, 0), {}), (4, I_STEP, {}),
        (7, merge(anvil_stance(-0.08, 8.0), v.head(2.0, 8.0, 0.0), cannon_hang(du=2.0, az=10.0), fist_hang(du=14.0, az=30.0)), {"lin_in": True}),
        (10, I_REACH, {}), (13, I_PRESS, LIN), (15, I_PRESS, HOLD), (26, I_PRESS, HOLD),
        (32, merge(anvil_stance(-0.08, 6.0), v.head(2.0, 6.0, 0.0), cannon_hang(du=2.0, az=10.0), fist_hang(du=12.0, az=26.0)), {}),
        (35, I_BACK, {}), (40, idle_key(0, 0, 0), {"lin_in": True})],
        purpose="work the anvil: a step in, lean over and press the plated fist down onto it, then step back",
        maps_to="the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s",
        events={"contact": 13, "release": 26})

    def hammer(p):
        """p: 0 raised, 1 the strike (at the anvil: the left sabaton stepped in, as interact)."""
        return merge(anvil_stance(-0.10 - 0.08 * p, 8.0 + 10.0 * p), v.spine(10.0 + 10.0 * p, -6.0 - 4.0 * p),
                     v.head(2.0 + 2.0 * p, 10.0, 0.0), cannon_hang(du=4.0, az=8.0), v.fists())
    HP = (0.70, -0.60, 1.07)
    HAMMER_TOP = merge(hammer(0.0), v.arm("L", (22, 42), (46, 62), back=(0.1, 0.8, 0.6)), v.clav((-4.0, 0.0, 6.0), (0.0, 0.0, 0.0)))
    HAMMER_DOWN = merge(hammer(0.6), v.arm("L", (-10, 48), (-24, 70), back=(0.2, -0.3, 1.0)), v.clav((4.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
    HAMMER_HIT = merge(hammer(1.0), v.arm_abs("L", HP, (1.2, 0.2, 1.6), back=(0.2, -0.9, 0.3)), v.clav((6.0, 0.0, -2.0), (0.0, 0.0, 0.0)))
    HAMMER_REB = merge(hammer(0.85), v.arm_abs("L", (HP[0], HP[1] + 0.02, HP[2] + 0.10), (1.2, 0.2, 1.6), back=(0.2, -0.9, 0.3)),
                       v.clav((4.0, 0.0, 0.0), (0.0, 0.0, 0.0)))
    HAMMER_UP = merge(hammer(0.35), v.arm("L", (6, 46), (26, 68), back=(0.2, 0.4, 0.9)), v.clav((0.0, 0.0, 3.0), (0.0, 0.0, 0.0)))
    C["forge_hammer"] = clip("forge_hammer", 36, loop=True, keys=[
        (0, HAMMER_TOP, HOLD), (6, HAMMER_DOWN, LIN), (8, HAMMER_HIT, {}), (11, HAMMER_REB, {}), (20, HAMMER_UP, {}),
        (30, merge(HAMMER_TOP, v.arm("L", (21, 42), (44, 62), back=(0.1, 0.8, 0.6))), {})],
        purpose="hammering the anvil with the plated left fist, the cannon arm braced at his side",
        maps_to="the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil)",
        events={"hammer_hit": 8})

    # ================================================================================================================
    # unique: Valdris's kit
    # ================================================================================================================
    # -- signature idle: a forge-deep breath that vents the pauldron slots, a look down the cannon, the fist flexing --------
    def sig(breath=0.0, sway=0.0, look=0.0, nod=0.0, cannon=None, f=1.0, sh=(0.0, 0.0)):
        return merge(relaxed(dz=-0.015 * breath, sway=sway, lean=-2.0 * breath, look=look, nod=nod),
                     v.clav((-2.0 * breath + sh[0], 0.0, 3.0 * breath), (-2.0 * breath + sh[1], 0.0, 3.0 * breath)),
                     cannon if cannon is not None else cannon_hang(du=2.0 * breath), fist_hang(du=2.0 * breath, f=f))
    LOOK = v.arm("R", (-22, 40), (-4, 68), back=(0.1, -0.2, 1.0))
    U.append(clip("idle_signature", 150, loop=True, family="valdris", keys=[
        (0, sig(), {}),
        (18, sig(breath=1.4, sway=0.2), HOLD),                   # a deep forge breath: the pauldrons rise
        (30, sig(breath=-0.8, sway=0.0, nod=3.0), {}),            # ...and vent: shoulders dropped, a slump
        (40, sig(breath=-0.2, sway=-0.3), {}),
        (52, sig(sway=-0.6, look=-0.8, cannon=LOOK), {}),         # lifts the cannon and looks down the barrel
        (62, sig(sway=-0.6, look=-0.9, nod=2.0, cannon=v.arm("R", (-20, 42), (-2, 70), back=(0.1, -0.2, 1.0), twist=-12.0)), {}),
        (72, sig(sway=-0.5, look=-0.8, cannon=v.arm("R", (-22, 40), (-4, 68), back=(0.1, -0.2, 1.0), twist=10.0)), {}),
        (84, sig(sway=-0.1, look=-0.2), {}),
        (94, sig(sway=0.4, look=0.5, f=0.15), {}),               # the fist opens, closes, opens, closes
        (100, sig(sway=0.5, look=0.6, f=1.0), LIN),
        (106, sig(sway=0.5, look=0.6, f=0.2), {}),
        (112, sig(sway=0.5, look=0.5, f=1.0), LIN),
        (126, sig(sway=0.2, look=0.0, sh=(3.0, -3.0)), {}),
        (138, sig(sway=0.0, look=-0.2), {})],
        purpose="signature idle: a forge-deep breath vents the pauldron slots, he lifts the cannon to look down the barrel, flexes the fist",
        maps_to="alive and idle for 6 s or more (out of combat); in the hub and the character select",
        events={"vent": 24, "flex": 100}))

    # -- Bulwark Slam: leap 7 m in 0.45 s (13.5 frames) -> Nova on landing -> Barricade 1.8 m in front ------------------------
    BS_LOAD = merge(combat(dz=-0.20, lean=16.0), v.arm("R", (-42, 14), (-46, 24)), v.arm("L", (-42, 14), (-36, 30), back=(0.7, -0.2, 0.7)),
                    v.head(0.0, -6.0, 0.0), v.clav((6.0, 0.0, -4.0)), v.pauldrons(0.0))
    BS_PUSH = merge(combat(dz=0.10, lean=-4.0, heel_l=30.0, heel_r=34.0), v.arm("R", (5, 52), (24, 82), back=(0.1, 0.6, 0.8)),
                    v.arm("L", (5, 54), (24, 84), back=(0.2, 0.5, 0.8)), v.head(-6.0, -4.0, 0.0), v.clav((-2.0, 0.0, 5.0)),
                    v.pauldrons(4.0))

    def air(z, lean, arms_up=1.0, tuck=0.0, pd=8.0):
        st = v.stance(z, (4.0 + lean * 0.4, 0.0, 0.0),
                      {"ball": (0.36, -0.30 + 0.10 * tuck), "yaw": 12.0, "lift": 0.20 + z * 0.8 + 0.12 * tuck, "heel": 30.0},
                      {"ball": (0.36, -0.20 + 0.14 * tuck), "yaw": 14.0, "lift": 0.18 + z * 0.8 + 0.14 * tuck, "heel": 40.0})
        return merge(st, v.spine(2.0 + lean * 0.6, 4.0), v.head(-6.0, -4.0, 0.0),
                     v.arm("R", (-10 + 26 * arms_up, 54), (10 + 26 * arms_up, 84), back=(0.1, 0.6, 0.8)),
                     v.arm("L", (-10 + 26 * arms_up, 56), (12 + 24 * arms_up, 86), back=(0.2, 0.6, 0.8)),
                     v.clav((-4.0, 0.0, 4.0 + 6.0 * arms_up)), v.pauldrons(pd * arms_up), v.fists())
    BS_SLAM = merge(combat(dz=-0.28, lean=9.0, rise=0.0),
                    v.arm("R", (-34, 10), (-62, 14)), v.arm("L", (-42, 22), (-32, 50), back=(0.6, -0.2, 0.9)),
                    v.head(2.0, -2.0, 0.0), v.clav((8.0, 0.0, -6.0)), v.pauldrons(0.0))
    BS_ABSORB = merge(BS_SLAM, combat(dz=-0.32, lean=11.0, rise=0.0), v.arm("R", (-36, 10), (-64, 14)))
    U.append(clip("bulwark_slam", 50, family="valdris", extra_keyed=PAULDRONS, keys=[
        (0, merge(READY, v.pauldrons(0.0)), {}), (5, BS_LOAD, HOLD), (8, BS_PUSH, LIN), (11, air(0.30, -4.0, 0.8, 0.5), {}),
        (15, air(0.50, -2.0, 1.0, 1.0), {}), (18, air(0.32, 12.0, 0.6, 0.6, 6.0), {}),
        (21, BS_SLAM, {"lin_in": True}), (25, BS_ABSORB, {}), (31, merge(BS_ABSORB, combat(dz=-0.28, lean=9.0, rise=0.0)), HOLD),
        (36, merge(combat(dz=-0.18, lean=9.0), v.arm("R", (-30, 12), (-34, 18)), v.arm("L", (-40, 24), (-28, 56), back=(0.6, -0.2, 0.9)),
                   v.pauldrons(0.0)), {}),
        (42, merge(combat(dz=-0.08, lean=6.0), aim(du=-6.0, dfore=-10.0), fist_low(), v.pauldrons(0.0)), {}),
        (50, merge(READY, v.pauldrons(0.0)), {})],
        purpose="Bulwark Slam: a deep crouch, a heavy leap with both arms raised overhead, the cannon slammed down on landing",
        maps_to="kits.ron valdris active1 Bulwark Slam: the 7 m / 0.45 s leap runs from 'launch' to 'land' (the sim moves "
                "the entity); Nova (r 3.4) on 'land', the forge Barricade on 'barricade'",
        events={"launch": 8, "land": 21, "barricade": 25}, grounded=False))

    # -- Siege Stance: rooted 6 s, fire x2.2, taunt -----------------------------------------------------------------------------
    SW_L, SW_R = (0.54, -0.36), (0.54, -0.24)

    def siege(b=0.0, dz=0.0, fist=True):
        st = v.stance(-0.22 - 0.02 * b + dz, (8.0 + 0.8 * b, 4.0, 0.0), {"ball": SW_L, "yaw": 22.0, "heel": 9.0, "plant": True},
                      {"ball": SW_R, "yaw": 24.0, "heel": 9.0, "plant": True}, tilt=(11.0, 11.0))
        return merge(st, v.spine(12.0 + 1.5 * b, 11.0), v.head(-6.0, -8.0, 0.0),
                     v.arm("R", (-15 + 1.0 * b, 40), (-2 + 0.5 * b, 72)),
                     v.arm("L", (-40 + 1.5 * b, 22), (-50 + 1.5 * b, 46), back=(0.8, -0.3, 0.5)) if fist else {},
                     v.clav((2.0, 0.0, -1.0 * b)), v.fists())
    SIEGE = siege()
    SE_LIFT = merge(combat(dz=-0.06, lean=4.0, lift_l=0.18, heel_l=10.0, fl=(0.46, -0.33)), aim(), fist_low(du=4.0))
    SE_STOMP = merge(combat(dz=-0.16, lean=8.0, fl=SW_L, fr=FR, rise=RISE), aim(du=-2.0), fist_low(du=-2.0), v.clav((4.0, 0.0, -2.0)))
    SE_LIFT_R = merge(combat(dz=-0.14, lean=6.0, fl=SW_L, fr=(0.48, -0.23), lift_r=0.16, heel_r=10.0, rise=RISE), aim(), fist_low())
    U.append(clip("siege_stance_enter", 26, family="valdris", keys=[
        (0, READY, {}), (5, SE_LIFT, {}), (8, SE_STOMP, {"lin_in": True}), (12, SE_LIFT_R, {}),
        (15, merge(siege(dz=0.04, fist=False), fist_low(du=2.0)), {"lin_in": True}),
        (19, siege(1.0, dz=-0.02), {}), (26, SIEGE, {})],
        purpose="Siege Stance: two stamping steps out into a wide low brace, the fist planted on the knee, the cannon locked on the aim",
        maps_to="kits.ron valdris active2 Siege Stance cast: rooted from 'anchor' (the anchor VFX / ground glyph); then siege_stance@loop",
        events={"stomp_l": 8, "anchor": 15}))
    U.append(clip("siege_stance", 40, loop=True, family="valdris", keys=[
        (0, SIEGE, {}), (10, siege(1.0), {}), (20, siege(0.0), {}), (30, siege(1.0, dz=-0.005), {})],
        purpose="the Siege Stance brace: rooted wide and low, the fist on the knee, heavy breaths, the cannon dead steady",
        maps_to="replaces idle_combat and locomotion for the 6 s Siege Stance (rooted); siege_fire layers the shots over it"))
    U.append(clip("siege_stance_exit", 20, family="valdris", keys=[
        (0, SIEGE, {}), (4, merge(siege(dz=0.03, fist=False), fist_low(du=2.0)), {}),
        (8, merge(combat(dz=-0.10, lean=6.0, fl=SW_L, fr=(0.48, -0.23), lift_r=0.12, heel_r=10.0, rise=RISE), aim(), fist_low()), {}),
        (11, merge(combat(dz=-0.08, lean=4.0, fl=SW_L, rise=RISE), aim(), fist_low()), {"lin_in": True}),
        (14, merge(combat(dz=-0.04, lean=2.0, fl=(0.46, -0.33), lift_l=0.12, heel_l=10.0), aim(), fist_low()), {}),
        (17, merge(combat(dz=-0.02), aim(), fist_low()), {"lin_in": True}), (20, READY, {})],
        purpose="out of the brace: he straightens and steps both sabatons back in under him",
        maps_to="Siege Stance ends (6 s): back to idle_combat / locomotion"))

    def siege_kick(k):
        return merge(SIEGE, v.arm("R", (-15 + 3.0 * k, 40 - 4.0 * k), (-2 + 8.0 * k, 72 - 4.0 * k)),
                     v.clav((2.0, 0.0, 0.0), (2.0 - 5.0 * k, 0.0, 2.0 * k)), v.spine(8.0 - 2.0 * k, 11.0 - 3.0 * k))
    U.append(clip("siege_fire", 5, layer="upper", family="valdris", base="siege_stance", keys=[
        (0, SIEGE, {}), (1, siege_kick(1.0), LIN), (2, siege_kick(0.7), {}), (5, SIEGE, {})],
        purpose="a Siege Stance shot: a short hard kick of the cannon and the right shoulder, braced (recoil stays procedural)",
        maps_to="each shot during Siege Stance (5.7 shots/s = one per 5.3 frames), layered over siege_stance@loop; "
                "first and last frame are siege_stance frame 0",
        events={"shot": 1}))

    # -- Mountainfall: 8 s at scale x1.8, boulder shots, a ground pound every 1.1 s ----------------------------------------------
    MW_L, MW_R = (0.48, -0.42), (0.48, -0.30)

    def mountain(b=0.0, sh=0.0):
        st = v.stance(-0.14 - 0.03 * b, (6.0 + 1.0 * b, 4.0, 0.0), {"ball": MW_L, "yaw": 18.0}, {"ball": MW_R, "yaw": 22.0},
                      tilt=(1.5, 1.5))
        return merge(st, v.spine(8.0 + 2.0 * b, 9.0 + 1.5 * sh), v.head(-3.0, -8.0, 0.0),
                     aim(du=-2.0 * b, dfore=-1.5 * b), v.arm("L", (-34 + 3.0 * b, 26), (-10 + 3.0 * b, 64), back=(0.6, -0.2, 0.9)),
                     v.clav((2.0 + 2.0 * sh, 0.0, 2.0 * b), (2.0 - 2.0 * sh, 0.0, 2.0 * b)), v.fists())
    MF = mountain()
    MF_GATHER = merge(combat(dz=-0.18, lean=9.0), v.arm("R", (-40, 16), (-44, 28)), v.arm("L", (-42, 18), (-40, 34), back=(0.7, -0.2, 0.7)),
                      v.head(2.0, -4.0, 0.0), v.clav((8.0, 0.0, -6.0)), v.pauldrons(0.0))
    MF_STEP = merge(MF_GATHER, combat(dz=-0.10, lean=8.0, fl=(0.44, -0.36), lift_l=0.14, heel_l=8.0),
                    v.arm("R", (-10, 20), (4, 30)), v.arm("L", (-10, 20), (6, 32), back=(0.3, 0.2, 0.9)), v.pauldrons(4.0))
    MF_RISE = merge(combat(dz=0.0, lean=-10.0, fl=MW_L), v.arm("R", (28, 10), (46, 20)), v.arm("L", (28, 10), (48, 22), back=(0.3, 0.4, 0.8)),
                    v.head(-8.0, 0.0, 0.0), v.clav((-8.0, 0.0, 8.0)), v.pauldrons(12.0))
    MF_LIFT = merge(MF_RISE, combat(dz=-0.02, lean=-8.0, fl=MW_L, fr=(0.46, -0.26), lift_r=0.24, heel_r=12.0), v.pauldrons(12.0))
    MF_STOMP = merge(combat(dz=-0.18, lean=10.0, fl=MW_L, fr=MW_R, rise=RISE), aim(du=-6.0, dfore=-8.0),
                     v.arm("L", (-40, 26), (-24, 60), back=(0.6, -0.2, 0.9)), v.head(-2.0, -6.0, 0.0), v.clav((6.0, 0.0, -4.0)),
                     v.pauldrons(0.0))
    U.append(clip("mountainfall_start", 46, family="valdris", extra_keyed=PAULDRONS, keys=[
        (0, merge(READY, v.pauldrons(0.0)), {}), (8, MF_GATHER, HOLD), (12, MF_STEP, {}), (16, MF_RISE, {"lin_in": True}),
        (22, merge(MF_RISE, v.head(-9.0, 0.0, 0.0)), HOLD),
        (26, MF_LIFT, {}), (30, MF_STOMP, {"lin_in": True}), (36, merge(MF_STOMP, combat(dz=-0.16, lean=8.0, fl=MW_L, fr=MW_R, rise=RISE)), {}),
        (46, merge(MF, v.pauldrons(0.0)), {})],
        purpose="Mountainfall: gathers low, steps wide and rises with both arms flung out and up as he grows, a ground-shaking stamp",
        maps_to="kits.ron valdris ultimate Mountainfall cast: the x1.8 scale ramps from 'grow', the first shockwave on 'stomp'; "
                "then mountainfall@loop",
        events={"grow": 16, "stomp": 30}))
    U.append(clip("mountainfall", 40, loop=True, family="valdris", keys=[
        (0, MF, {}), (10, mountain(1.0, 1.0), {}), (20, mountain(0.0, 0.0), {}), (30, mountain(1.0, -1.0), {})],
        purpose="the Mountainfall avatar stance: wider and lower, heavy slow breaths rolling the pauldrons, the cannon on the aim",
        maps_to="replaces idle_combat while Mountainfall lasts (8 s, model scale x1.8); shots and mountainfall_pound layer on top"))
    MP_UP = merge(MF, v.spine(-2.0, 6.0), v.arm("R", (16, 52), (36, 84), back=(0.1, 0.6, 0.8)), v.arm("L", (16, 54), (36, 86), back=(0.2, 0.6, 0.8)),
                  v.head(-6.0, -4.0, 0.0), v.clav((-4.0, 0.0, 6.0)), v.pauldrons(8.0))
    MP_HIT = merge(MF, v.spine(24.0, 4.0), v.arm("R", (-34, 10), (-60, 14)), v.arm("L", (-42, 20), (-46, 34), back=(0.6, -0.2, 0.9)),
                   v.head(2.0, -4.0, 0.0), v.clav((8.0, 0.0, -6.0)), v.pauldrons(0.0))
    U.append(clip("mountainfall_pound", 33, layer="upper", family="valdris", base="mountainfall", extra_keyed=PAULDRONS, keys=[
        (0, merge(MF, v.pauldrons(0.0)), {}), (8, MP_UP, HOLD), (11, merge(MP_UP, v.spine(-3.0, 6.0)), {}),
        (15, MP_HIT, {"lin_in": True}), (19, merge(MP_HIT, v.spine(20.0, 5.0)), {}), (33, merge(MF, v.pauldrons(0.0)), {})],
        purpose="the Mountainfall ground pound: both arms heaved overhead, then the cannon and the fist hammered down at the ground",
        maps_to="every 1.1 s during Mountainfall (33 frames = 1.1 s): the pound (r 4.5) on 'pound'; upper layer over "
                "mountainfall@loop or locomotion, first and last frame are mountainfall frame 0",
        events={"pound": 15}))

    # -- Reforged Flesh: the Armor breaks -> shockwave r 5.0 + a 3 s taunt ------------------------------------------------------
    AB_GATHER = merge(combat(dz=-0.06, lean=12.0, twist=4.0), v.arm("R", (-40, 50), (-40, 74)), v.arm("L", (-44, 46), (-36, 76), back=(0.5, -0.2, 1.0)),
                      v.clav((8.0, 0.0, -6.0)), v.head(0.0, -6.0, 0.0))
    AB_BREAK = merge(combat(dz=0.0, lean=-12.0, twist=-2.0), v.arm("R", (4, -6), (14, 0)), v.arm("L", (4, -6), (16, 2), back=(0.4, 0.3, 0.8)),
                     v.clav((-10.0, 0.0, 8.0)), v.head(-8.0, -4.0, 0.0))
    U.append(clip("armor_break", 32, layer="upper", family="valdris", keys=[
        (0, READY, {}), (4, AB_GATHER, HOLD), (7, AB_BREAK, LIN), (12, merge(AB_BREAK, v.head(-9.0, -2.0, 0.0)), {}),
        (18, merge(AB_BREAK, combat(dz=0.0, lean=-10.0), v.clav((-8.0, 0.0, 6.0))), HOLD),
        (25, merge(ready(lean=2.0), aim(du=-4.0)), {}), (32, READY, {})],
        purpose="Reforged Flesh break: hunched against the blow, then the chest and both arms thrown open in a roar as the plates blast off",
        maps_to="the Reforged Flesh passive when the Armor breaks: the shockwave (r 5.0) and the 3 s taunt start on 'break'; "
                "upper layer over anything",
        events={"break": 7, "roar": 12}))
    return C, U


_CACHE = {}


def _built(K):
    k = id(K)
    if k not in _CACHE:
        _CACHE[k] = build(K)
    return _CACHE[k]


def shared_clips(K):
    """The GF_Hero_v1 shared set (s4_contract.SHARED_CLIPS order, names, loops and layers) posed for Valdris."""
    C, _U = _built(K)
    return [C[c.clip] for c in s4_clips.shared_clips(K)]


def unique_clips(K):
    _C, U = _built(K)
    return list(U)
