"""Selene's stage-4 clips on GF_Hero_v1: the shared set re-posed for a slender two-handed launcher gunner, and her kit.

Selene, The Stormcaller (content/sheets/characters.csv row selene, assets/content/kits.ron, brief.md sections 7-8) is a
2.2 m sorceress on heeled sabatons with the thundercoil_launcher (a two-handed weapon on weapon_R; its grip_L, the left
palm, sits 0.441 m up the barrel and 0.052 m above the right palm). Brax's library (s4_clips.py) is a brawler with two
fists; she keeps its contract (names, loops, layers, events, timing structure) and gets her own poses:

  * the HOLD: the launcher at her right hip along the aim, the body bladed (hips and chest turned right, the left foot
    leading), the right forearm along the barrel (the wrist is straight, so the barrel is the forearm), the left hand on
    the foregrip. The left hand is placed per frame from the SOLVED right-hand grip frame (SClip.poses: solve, read
    weapon_R, put the left palm on grip_L, re-solve), blended by the pose's "hold" weight, so recoil, bobs and turns
    carry both hands and a clip can let go of the foregrip (ping, Arc Nova, Static Charge);
  * the CARRY (idle, walk, interact): the launcher low in the right hand, the barrel angled down and forward, the left
    hand free and open (her claws), a lighter, more upright stance;
  * her gait: long, light, upright (move 7.0 m/s), the launcher held at the hip in the run and the strafes;
  * her kit (brief section 7.1): idle_signature@loop (a hover sway, the claws crackling), arc_nova (a two-handed snap
    forward and apart), blink_out / blink_in (a lean into the teleport; an arrival that settles), heavens_verdict_start /
    heavens_verdict@loop (arms raised, the storm called, hovering), static_charge (the left fist clenched and crackling).
Arms are given as (elevation, azimuth) directions of the upper arm and forearm in the rest chest frame (as Valdris's V.arm:
azimuth 0 = straight out to the side, 90 = forward), interpolated by direction. Clips are in place, 30 fps; the numbers
are metres and degrees (SV converts them to s4lib pose dicts, whose offsets are Brax-scale x the hero's leg / arm scale).
Her cloth, the crown bob and the knee helpers are not keyed here: s4_selene_cloth.py (cloth + crown) and the rig's
constraints (x_knee) add them.
"""
import math

from mathutils import Matrix, Vector

import gf_hero_rig as R
import s4_clips as SC
from s4_clips import HOLD, LIN, merge
from s4lib import FPS, Clip

# the arm keep-out (s4_anim.build_keepout): the cloth hangs and swings, the crown shards float (never obstacles)
KEEPOUT_LOOSE_PARTS = ("CAPES", "MANTLES", "PANELS", "TABARD", "CROWN")
KEEPOUT_OWN_BONES = {"R": ("pelvis", "spine_01")}
# (the launcher's stock rests against her right hip in the hold: the belt, hip plate and belt ring there never push the
# right hand; everything else on her body still does)
# thundercoil_launcher.glb: grip_L in the grip frame (glTF (0, 0.052, -0.441) -> grip (x, -z, y))
GRIP_L = Vector((0.0, 0.441, 0.052))
SOCKET_TO_GRIP = Matrix(R.SOCKET_TO_GRIP)
GRIP_CURL_R = 0.72         # the right hand round the pistol grip
GRIP_CURL_L = 0.45         # the left hand over the foregrip
OPEN = 0.18                # a free hand: the claws relaxed


class SV:
    """Selene's pose vocabulary (metres and degrees -> s4lib pose dicts)."""

    def __init__(self, K):
        self.K = K
        P = K.P
        self.sh = {s: P("shoulder_" + s) for s in "LR"}
        self.L1 = (P("elbow_L") - P("shoulder_L")).length
        self.L2 = (P("hand_L_tip") - P("elbow_L")).length

    @staticmethod
    def d(el, az, side):
        sx = 1.0 if side == "L" else -1.0
        e, a = math.radians(el), math.radians(az)
        return Vector((sx * math.cos(e) * math.cos(a), -math.cos(e) * math.sin(a), math.sin(e)))

    def arm(self, side, upper, fore, back=(0.0, 0.0, 1.0), twist=0.0, space="chest"):
        du, df = self.d(*upper, side), self.d(*fore, side)
        E = self.sh[side] + du * self.L1
        T = E + df * self.L2
        Pp = E + du * 0.25
        b = Vector(back)
        if side == "R":
            b.x = -b.x
        s = self.sh[side]
        return {"arm_" + side: {"fist": tuple((T - s) / self.K.as_), "pole": tuple((Pp - s) / self.K.as_),
                                "back": tuple(b), "space": space, "twist": twist,
                                "_dirs": (float(upper[0]), float(upper[1]), float(fore[0]), float(fore[1]))}}

    def arm_from_dirs(self, side, spec):
        el_u, az_u, el_f, az_f = spec["_dirs"]
        du, df = self.d(el_u, az_u, side), self.d(el_f, az_f, side)
        E = self.sh[side] + du * self.L1
        s = self.sh[side]
        out = dict(spec)
        out["fist"] = tuple(((E + df * self.L2) - s) / self.K.as_)
        out["pole"] = tuple(((E + du * 0.25) - s) / self.K.as_)
        return out

    def arm_abs(self, side, target, pole, back=(0.0, 0.0, 1.0)):
        sx = 1.0 if side == "L" else -1.0
        T = Vector((sx * target[0], target[1], target[2]))
        Pp = Vector((sx * pole[0], pole[1], pole[2]))
        b = Vector((sx * back[0], back[1], back[2]))
        return {"arm_" + side: {"fist": tuple(T / self.K.ls), "pole": tuple(Pp / self.K.ls), "back": tuple(b),
                                "space": "abs"}}

    # -- the launcher ------------------------------------------------------------------------------------------------------
    def hold(self, psi, upper=(-74.0, 12.0), dfore=(13.0, 0.0), twist=0.0, h=1.0, fl=GRIP_CURL_L):
        """The two-handed hold: the right arm with its forearm (= the barrel) along the aim for a chest turned psi degrees
        (+ = to her left; the bladed stance turns it right, psi < 0), the left hand on grip_L (weight h, SClip)."""
        fore = (dfore[0], 90.0 - psi + dfore[1])
        return merge(self.arm("R", upper, fore, back=(0.0, 0.0, 1.0), twist=twist),
                     {"hold": h, "fingers_R": GRIP_CURL_R, "fingers_L": fl})

    def carry(self, upper=(-80.0, 25.0), fore=(-38.0, 78.0), twist=0.0):
        """The launcher low in the right hand, the barrel angled down and forward along the forearm."""
        return merge(self.arm("R", upper, fore, back=(0.25, 0.0, 1.0), twist=twist), {"fingers_R": GRIP_CURL_R})

    def free_l(self, upper=(-78.0, 12.0), fore=(-70.0, 40.0), f=OPEN, back=(1.0, 0.2, 0.0)):
        """The free left arm (open claws), no hold."""
        return merge(self.arm("L", upper, fore, back=back), {"fingers_L": f})

    # -- body ------------------------------------------------------------------------------------------------------------------
    def pelvis(self, loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
        return {"pelvis": {"loc": tuple(v / self.K.ls for v in loc), "rot": tuple(rot)}}

    def foot(self, side, ball, yaw=8.0, **kw):
        """ball (x outward, y) in metres, left-side terms; lift in metres; heel / toe in degrees."""
        spec = {"ball": ((ball[0] if side == "L" else -ball[0]) / self.K.ls, ball[1] / self.K.ls),
                "yaw": yaw if side == "L" else -yaw, "lift": 0.0, "heel": 0.0, "toe": 0.0}
        for k, v in kw.items():
            if k == "knee":
                v = (v[0] if side == "L" else -v[0], v[1], v[2])
            if k == "lift":
                v = v / self.K.ls
            spec[k] = v
        return {"foot_" + side: spec}

    @staticmethod
    def spine(fwd=0.0, twist=0.0, side=0.0):
        w = (0.34, 0.33, 0.33)
        return {"spine_0%d" % (i + 1): {"rot": (fwd * w[i], twist * w[i], side * w[i])} for i in range(3)}

    @staticmethod
    def head(nod=0.0, yaw=0.0, tilt=0.0, ww=1.0, neck=(0.0, 0.0, 0.0)):
        """The head held in world space (ww 1: nod / yaw / tilt from the rest, so the face keeps reading) or FK (ww 0)."""
        return {"head": {"wrot": (nod, yaw, tilt), "ww": ww, "rot": (nod * 0.6, yaw * 0.6, tilt * 0.6)},
                "neck": {"rot": (neck[0], neck[1], neck[2])}}

    @staticmethod
    def clav(l=(0.0, 0.0, 0.0), r=None):
        r = r if r is not None else l
        return {"clavicle_L": {"rot": tuple(l)}, "clavicle_R": {"rot": (r[0], -r[1], -r[2])}}


class SClip(Clip):
    """A Clip whose chest-space arms interpolate by DIRECTION (Valdris's VClip rule) and whose left hand is put on the
    launcher's grip_L frame by frame (weight: the pose's "hold")."""

    def __init__(self, v, *a, **kw):
        super().__init__(*a, **kw)
        self.v = v

    def poses(self, solver=None):
        out = super().poses(solver)
        if self.keys:
            keys = sorted(self.keys, key=lambda k: k[0])
            if self.loop and keys[-1][0] != self.length:
                keys = keys + [(self.length, keys[0][1], keys[0][2])]
            T = [k[0] for k in keys]
            for side in "LR":
                nm = "arm_" + side
                state, cur = [], None
                for _f, p, _o in keys:
                    if nm in p:
                        cur = "_dirs" in p[nm] and p[nm].get("space", "chest") == "chest"
                    state.append(cur)
                for f, pose in enumerate(out):
                    spec = pose.get(nm)
                    if not spec or "_dirs" not in spec or spec.get("space", "chest") != "chest":
                        continue
                    i = 0
                    while i < len(T) - 2 and f > T[i + 1]:
                        i += 1
                    if state[i] and state[min(i + 1, len(T) - 1)]:
                        pose[nm] = self.v.arm_from_dirs(side, spec)
        else:
            for pose in out:
                for side in "LR":
                    spec = pose.get("arm_" + side)
                    if spec and "_dirs" in spec and spec.get("space", "chest") == "chest":
                        pose["arm_" + side] = self.v.arm_from_dirs(side, spec)
        if solver is not None:
            out = [apply_hold(solver, p) for p in out]
        return out


def apply_hold(solver, pose, iters=3):
    """Put the left palm (weapon_L) on the launcher's grip_L, read from the solved right-hand grip frame, blended by
    pose["hold"] (0 = the pose's own left arm, 1 = on the foregrip); the reach is capped at 96 % of the arm (the palm
    then stops short along the line to the grip instead of the IK snapping straight)."""
    h = max(0.0, min(1.0, float(pose.get("hold", 0.0))))
    if h <= 1e-4 or "arm_L" not in pose:
        return pose
    rig, K = solver.rig, solver.K
    pose = dict(pose)
    _l, M, _i = solver.solve(pose)
    G = M["weapon_R"] @ SOCKET_TO_GRIP
    G3 = G.to_3x3()
    want = G @ GRIP_L
    up = G3.col[2].normalized()
    T0, Pp, back0 = solver.arm_world("L", pose["arm_L"], M)
    sh = solver.sh_rest["L"]
    S = M["upperarm_L"].translation.copy()
    reach = rig.b["upperarm_L"].length + rig.fist_eff["L"].length

    def cap(t):
        d = t - S
        return S + d.normalized() * 0.96 * reach if d.length > 0.96 * reach else t
    spec = {k: v for k, v in pose["arm_L"].items() if k != "_dirs"}
    spec["space"] = "hero"
    spec["pole"] = tuple((Pp - sh) / K.as_)
    spec["back"] = tuple(up)
    tgt = want + G3.col[1].normalized() * 0.035 + up * 0.02
    for _ in range(iters):
        tgt = cap(tgt)
        spec["fist"] = tuple((tgt - sh) / K.as_)
        pose["arm_L"] = dict(spec)
        _l, M2, _i = solver.solve(pose)
        tgt = tgt + (want - M2["weapon_L"].translation)
    tgt = cap(tgt)
    if h < 1.0:
        tgt = T0.lerp(tgt, h)
        b = back0.normalized().lerp(up, h)
        spec["back"] = tuple(b.normalized()) if b.length > 1e-6 else tuple(up)
    spec["fist"] = tuple((tgt - sh) / K.as_)
    pose["arm_L"] = spec
    return pose


# ---- the clips ---------------------------------------------------------------------------------------------------------
UP = (-76.0, 2.0)            # the right upper arm of the hold (down along the side, a little forward)
PSI = -40.0                  # the bladed chest yaw of the combat hold (+ = to her left)
CLs, CRs = (0.17, -0.25), (0.17, 0.12)      # her combat feet (Brax units, left-side terms): narrower than Brax's


def build(K):
    v = SV(K)
    C = []

    def clip(*a, **kw):
        c = SClip(v, *a, **kw)
        C.append(c)
        return c

    def gun(psi, lean, de=0.0, da=0.0, h=1.0, upper=UP, fl=GRIP_CURL_L):
        """The launcher on the aim for a chest turned psi and leaned `lean` degrees in total (the hold's forearm is set in
        the chest frame, so it is pitched back up by the lean), the left hand on grip_L by h."""
        return merge(v.free_l(), v.hold(psi, upper=upper, dfore=(1.0 + lean + de, da), h=h, fl=fl))

    def combat(dz=0.0, lean=0.0, twist=0.0, hy=0.0, heel_l=0.0, heel_r=0.0, fl=CLs, fr=CRs, lift_l=0.0, lift_r=0.0,
               py=0.0):
        """The bladed gunner stance: the left foot leading, hips and chest turned right (chest yaw PSI + hy + twist)."""
        return merge(SC.pelvis((0.0, 0.02 + py, -0.06 + dz), (7.0 + lean * 0.4, PSI * 0.5 + hy, 0.0)),
                     SC.foot("L", fl, 12.0, heel=heel_l, lift=lift_l), SC.foot("R", fr, 34.0, heel=heel_r, lift=lift_r),
                     SC.spine(6.0 + lean * 0.6, PSI * 0.5 + twist), SC.head(neck=(-4.0, 0.0, 0.0)), SC.clav((2.0, 0.0, 0.0)))

    def ready(dz=0.0, lean=0.0, twist=0.0, hy=0.0, de=0.0, da=0.0, h=1.0, upper=UP, **kw):
        return merge(combat(dz, lean, twist, hy, **kw), gun(PSI + twist + hy, 13.0 + lean, de, da, h, upper))

    def carry_l(breath=0.0, sw=0.0):
        return merge(v.carry(), v.free_l(upper=(-79.0 + breath, 10.0 + 4 * sw), fore=(-68.0 + 3 * breath, 38.0)), {"hold": 0.0})

    # -- idles ---------------------------------------------------------------------------------------------------------------
    def idle_key(breath, sway, look):
        return merge(SC.pelvis((sway * 0.02, 0.0, -0.012 - 0.006 * breath), (2.0 - breath * 0.6, -4.0 + 2.0 * sway, 1.5 - 1.5 * sway)),
                     SC.foot("L", (0.12, -0.14), 10.0), SC.foot("R", (0.13, -0.07), 20.0),
                     SC.spine(2.0 - breath * 2.0, 3.0 + sway * 1.5, sway * 1.0),
                     SC.head(-1.5 * breath, look * 8.0, sway * 2.0, neck=(-2.0 - breath, look * 3.0, 0.0)),
                     SC.clav((-breath * 1.5, 0.0, -4.0 + breath * 2.5)), carry_l(breath, sway))
    clip("idle", 90, loop=True, keys=[
        (0, idle_key(0, 0, 0), {}), (24, idle_key(1, 0.7, 0.4), {}), (45, idle_key(0.2, 1.0, 1.0), {}),
        (68, idle_key(-0.6, 0.2, -0.3), {})],
        purpose="relaxed breathing stance, the launcher low in the right hand, the left hand loose, weight drifting",
        maps_to="alive, not moving, out of combat (no enemy near, no attack for 2 s; hub)")

    def combat_key(b, tw):
        return merge(ready(dz=-0.02 * b, lean=2.0 * b, twist=-tw * 0.5, hy=tw * 0.5, de=-1.0 * b), SC.head(neck=(-4.0 - 2.0 * b, 0.0, 0.0)))
    clip("idle_combat", 32, loop=True, keys=[
        (0, combat_key(0, 0), {}), (8, combat_key(1, 2), {}), (16, combat_key(0, 0), {}), (24, combat_key(1, -2), {})],
        purpose="the combat hold: bladed, the launcher at the right hip on the aim, the left hand on the foregrip, a light "
                "bounce on the knees",
        maps_to="alive, not moving, in combat (enemies near or an attack in the last 2 s). Frame 0 is the reference pose "
                "of every upper-layer clip")

    # -- locomotion (s4_clips.locomotion with her arms and chest) ----------------------------------------------------------
    vb = K.move_speed / K.ls

    def walk_arms(p, c1):
        return merge(v.carry(upper=(-80.0, 22.0 + 8.0 * c1), fore=(-40.0, 76.0)),
                     v.free_l(upper=(-78.0, 12.0 - 22.0 * c1), fore=(-66.0, 40.0 - 18.0 * c1)), {"hold": 0.0})

    def hold_arms(psi, pel_twist, lean, hip_yaw=0.0, da=0.0, bounce=0.0, pel_fwd=0.0):
        """Locomotion upper body: the chest held at psi against the pelvis' own swing (spine twist = psi - pelvis yaw)."""
        def upper(p, c1):
            c2 = math.cos(4 * math.pi * p)
            return merge(SC.spine(lean, psi - (hip_yaw - pel_twist * c1)),
                         gun(psi, lean + pel_fwd, de=-bounce * c2, da=da), SC.clav((1.0, 0.0, 0.0)))
        return upper

    walk_v = 1.8
    clip("walk", 28, loop=True, travel=(0.0, -walk_v * K.ls), speed=round(walk_v * K.ls, 3),
         fn=SC.locomotion(28, walk_v, duty=0.62, stance_half=0.11, foot_yaw=5.0, lift=0.10, lift_peak=0.4, heel_off=14.0,
                          heel_land=-6.0, heel_swing=12.0, bob=-0.018, drop=0.07, sway=0.035, pelvis_fwd=3.0,
                          pelvis_twist=7.0, spine_fwd=3.0, spine_counter=6.0, upper=walk_arms, phase0=0.16),
         purpose="a light, upright walk, hips swaying, the launcher carried low, the left arm swinging",
         maps_to="moving at under about 55 %% of move speed (stick partly pushed, slows); playback rate = speed / "
                 "%.2f m/s" % (walk_v * K.ls))
    clip("run", 18, loop=True, travel=(0.0, -K.move_speed), speed=K.move_speed,
         fn=SC.locomotion(18, vb, duty=0.22, stance_half=0.10, foot_yaw=4.0, lift=0.30, lift_peak=0.38, heel_off=24.0,
                          heel_land=4.0, heel_swing=58.0, shift=-0.10, match=0.6, bob=0.035, drop=0.13, sway=0.018,
                          pelvis_fwd=12.0, pelvis_twist=8.0, spine_fwd=10.0, spine_counter=0.0,
                          upper=hold_arms(-34.0, 8.0, 10.0, da=5.0, bounce=1.5, pel_fwd=12.0), phase0=0.30),
         purpose="a long, light run leaning into the move, the launcher held at the hip on the aim with both hands",
         maps_to="moving within 45 deg of the aim at move speed; playback rate = speed / %.1f m/s" % K.move_speed)
    strafe = dict(duty=0.25, stance_half=0.13, foot_yaw=4.0, lift=0.20, lift_peak=0.40, heel_off=18.0, heel_land=0.0,
                  heel_swing=40.0, match=0.9, bob=0.03, drop=0.15, sway=0.0, pelvis_fwd=8.0, pelvis_twist=5.0,
                  spine_fwd=6.0, spine_counter=0.0, phase0=0.30)
    strafe["drop"] = 0.18
    clip("strafe_left", 16, loop=True, travel=(K.move_speed, 0.0), speed=K.move_speed,
         fn=SC.locomotion(16, vb, direction=(1.0, 0.0), hip_yaw=10.0,
                          upper=hold_arms(-34.0, 5.0, 6.0, hip_yaw=10.0, da=5.0, pel_fwd=8.0), **strafe),
         purpose="side run to her left, hips opened toward the travel, the chest and the launcher kept on the aim",
         maps_to="moving 45-135 deg to the left of the aim; playback rate = speed / %.1f m/s" % K.move_speed)
    clip("strafe_right", 16, loop=True, travel=(-K.move_speed, 0.0), speed=K.move_speed,
         fn=SC.locomotion(16, vb, direction=(-1.0, 0.0), hip_yaw=-38.0,
                          upper=hold_arms(-40.0, 5.0, 6.0, hip_yaw=-38.0, pel_fwd=8.0), **strafe),
         purpose="side run to her right, the hips turned into the travel, the launcher kept on the aim",
         maps_to="moving 45-135 deg to the right of the aim; playback rate = speed / %.1f m/s" % K.move_speed)
    clip("backpedal", 16, loop=True, travel=(0.0, K.move_speed), speed=K.move_speed,
         fn=SC.locomotion(16, vb, direction=(0.0, 1.0), duty=0.25, stance_half=0.12, foot_yaw=8.0, lift=0.15,
                          lift_peak=0.45, heel_off=6.0, heel_land=10.0, heel_swing=30.0, match=0.9, bob=0.025, drop=0.18,
                          sway=0.015, pelvis_fwd=8.0, pelvis_twist=5.0, spine_fwd=6.0, spine_counter=0.0,
                          upper=hold_arms(-38.0, 5.0, 6.0, bounce=1.0, pel_fwd=8.0), phase0=0.30, base_y=-0.12),
         purpose="backpedal on the balls of her feet, the launcher up on the aim",
         maps_to="moving more than 135 deg away from the aim; playback rate = speed / %.1f m/s" % K.move_speed)

    # -- dash --------------------------------------------------------------------------------------------------------------------
    DASH = merge(SC.pelvis((0.0, -0.04, -0.20), (24.0, -16.0, 0.0)), SC.spine(14.0, -24.0), SC.head(10.0, neck=(-10.0, 0.0, 0.0)),
                 SC.foot("L", (0.13, -0.50), 4.0, lift=0.28, heel=25.0), SC.foot("R", (0.12, 0.55), 4.0, lift=0.22, heel=70.0),
                 gun(-40.0, 38.0, de=-6.0, h=0.45, fl=OPEN), SC.clav((6.0, 0.0, 0.0)))
    DASH2 = merge(DASH, SC.pelvis((0.0, -0.05, -0.21), (26.0, -16.0, 0.0)), SC.foot("L", (0.13, -0.53), 4.0, lift=0.24, heel=20.0),
                  SC.foot("R", (0.12, 0.60), 4.0, lift=0.24, heel=75.0))
    clip("dash", 8, keys=[(0, ready(), {}), (2, DASH, {}), (8, DASH2, {})],
         purpose="the dash burst: a low lunge-glide leaning into the move, the launcher tucked on the aim in the right hand (the "
                 "left lets go of the foregrip for the lunge), the capes streaming",
         maps_to="the 0.16 s dash (MoverState.dash_left > 0); the client faces the hero along the dash for its duration",
         events={"launch": 1}, grounded=False)
    LAND = ready(dz=-0.12, lean=16.0, lift_r=0.10, fr=(0.18, 0.30), heel_r=40.0, de=-4.0, h=0.7)
    clip("dash_recover", 14, keys=[
        (0, DASH2, {}), (3, merge(LAND, SC.head(8.0, neck=(-10.0, 0.0, 0.0))), {"t": 0.6}),
        (6, ready(dz=-0.09, lean=10.0), {"t": 0.7}), (10, ready(dz=-0.02, lean=2.0), {}), (14, ready(), {})],
        purpose="landing out of the dash: the lead foot plants, a soft absorb, back into the hold",
        maps_to="the first 0.45 s after a dash ends when the hero is not moving on (else blend into locomotion)",
        events={"land": 3})

    # -- fire (upper layer: first and last frame = idle_combat frame 0) ----------------------------------------------------------
    KICK = ready(twist=3.0, lean=-4.0, de=11.0, upper=(-74.0, -4.0))
    clip("fire_light", 8, layer="upper", keys=[
        (0, ready(), {}), (1, ready(twist=-1.0, lean=1.0, de=-2.0), LIN), (3, KICK, {}), (8, ready(), {})],
        purpose="one orb shot: a snap forward, the launcher kicks up and back, the body rides it (recoil stays procedural)",
        maps_to="each primary shot of a light chassis (fire_rate >= 2/s: the thundercoil_launcher fires 3.5/s)",
        events={"shot": 1})
    FH_LOAD = ready(dz=-0.03, lean=6.0, twist=-4.0, de=-3.0)
    FH_KICK = merge(ready(dz=-0.01, lean=-10.0, twist=7.0, de=22.0, upper=(-70.0, -8.0)), SC.head(-6.0, neck=(-2.0, 0.0, 0.0)))
    clip("fire_heavy", 16, layer="upper", keys=[
        (0, ready(), {}), (5, FH_LOAD, HOLD), (7, FH_KICK, {}), (10, ready(lean=-3.0, twist=2.0, de=7.0), {}),
        (16, ready(), {})],
        purpose="a charged shot: brace into the aim, release, the launcher bucks up and the body rocks back",
        maps_to="a heavy / charged release (fire_rate < 1/s, charge release, splash chassis)",
        events={"shot": 7})

    def charge_key(k):
        return merge(ready(dz=-0.03, lean=4.0, twist=-3.0 - 1.5 * k, de=-2.0 + 1.5 * k), SC.head(2.0, neck=(-4.0, 0.0, 0.0)))
    clip("fire_charge", 24, loop=True, layer="upper", keys=[
        (0, charge_key(0), {}), (6, charge_key(1), {}), (12, charge_key(0), {}), (18, charge_key(1), {})],
        purpose="holding a charge: braced low behind the launcher, trembling with the stored storm",
        maps_to="fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy)")

    # -- hits ------------------------------------------------------------------------------------------------------------------------
    HL = merge(ready(twist=-10.0, lean=-8.0, de=14.0, upper=(-72.0, -6.0)), SC.head(-12.0, 10.0, 6.0, neck=(4.0, 0.0, 0.0)))
    clip("hit_light", 12, layer="upper", keys=[
        (0, ready(), {}), (2, HL, {}), (5, merge(ready(twist=-3.0, lean=4.0, de=-3.0), SC.head(4.0)), {}), (12, ready(), {})],
        purpose="a flinch: the head snaps, the launcher is knocked up, absorb, recover",
        maps_to="PlayerFlags::HIT on a light hit (damage < 10 % max HP), layered over whatever plays",
        events={"impact": 1})
    HH1 = merge(ready(dz=0.02, lean=-18.0, twist=12.0, hy=8.0, py=0.08, fl=(0.16, -0.16), lift_l=0.12, heel_r=10.0,
                      de=26.0, h=0.55, upper=(-66.0, -12.0)), SC.head(-22.0, 12.0, 0.0), {"fingers_L": 0.2})
    HH2 = merge(ready(dz=-0.08, twist=6.0, hy=4.0, py=0.06, fl=(0.17, 0.0), de=8.0, h=0.8), SC.head(-4.0))
    HH3 = merge(ready(dz=-0.18, lean=14.0, twist=-4.0, py=0.05, fl=(0.17, 0.0), de=-4.0), SC.head(6.0))
    HH4 = merge(ready(dz=-0.10, lean=6.0, py=0.03, fl=(0.17, -0.14), lift_l=0.06), SC.head(0.0))
    clip("hit_heavy", 26, keys=[
        (0, ready(), {}), (3, HH1, {}), (8, HH2, {"t": 0.8}), (13, HH3, {}), (19, HH4, {}),
        (22, ready(dz=-0.07, lean=4.0), {"t": 0.8}), (26, ready(), {})],
        purpose="a big stagger: blown back, the left hand torn off the foregrip, the lead foot steps back, absorb, step back in",
        maps_to="PlayerFlags::HIT on a heavy hit (damage >= 10 % max HP or a stun); interrupts upper-layer clips",
        events={"impact": 1})

    # -- knockdown / get up --------------------------------------------------------------------------------------------------------
    KD1 = merge(ready(lean=-24.0, twist=10.0, py=0.10, fl=(0.16, -0.15), lift_l=0.15, heel_r=25.0, de=30.0, h=0.3,
                      upper=(-50.0, -10.0)), SC.head(-26.0, 10.0, 0.0), {"fingers_L": 0.15}, SC.clav((6.0, 0.0, 6.0)))
    KD2 = merge(SC.pelvis((0.0, 0.34, -0.58), (-52.0, 6.0, 0.0)), SC.spine(-10.0, 6.0),
                SC.head(0.0, ww=0.0, neck=(12.0, 0.0, 0.0), rot=(14.0, 0.0, 0.0)),
                SC.foot("L", (0.20, -0.42), 6.0, lift=0.40, heel=-20.0, knee=(0.0, 0.0, 1.0)),
                SC.foot("R", (0.18, -0.05), 6.0, lift=0.14, heel=-10.0, knee=(0.0, 0.0, 1.0)),
                SC.arm("L", (0.55, 0.05, 0.25), pole=(0.3, 0.8, -0.2), back=(0.5, 0.6, 0.6)),
                SC.arm("R", (0.50, 0.12, 0.30), pole=(0.3, 0.8, -0.2), back=(0.5, 0.6, 0.6)),
                {"hold": 0.0, "fingers_L": 0.15, "fingers_R": GRIP_CURL_R}, SC.clav((-4.0, 0.0, 6.0)))
    LYING = merge(SC.pelvis((0.0, 0.42, -0.99), (-84.0, 2.0, 0.0)), SC.spine(-4.0, 0.0),
                  SC.head(0.0, ww=0.0, neck=(8.0, 0.0, 0.0), rot=(6.0, 12.0, 0.0)),
                  SC.foot("L", CLs, 10.0, knee=(0.4, 0.0, 2.0)), SC.foot("R", (0.20, -0.80), 10.0, heel=-78.0, knee=(0.0, 0.0, 2.0)),
                  SC.arm("L", (0.70, 0.50, 0.14), pole=(0.9, 0.9, 1.5), back=(0.0, 0.2, 1.0), space="abs"),
                  SC.arm("R", (0.68, 0.60, 0.14), pole=(0.9, 0.9, 1.5), back=(0.0, 0.2, 1.0), space="abs"),
                  {"hold": 0.0, "fingers_L": 0.3, "fingers_R": GRIP_CURL_R}, SC.clav((0.0, 0.0, 4.0)))
    LY_BOUNCE = merge(LYING, SC.pelvis((0.0, 0.41, -0.95), (-80.0, 3.0, 0.0)),
                      SC.foot("L", (0.22, -0.30), 10.0, lift=0.10, knee=(0.4, 0.0, 2.0)),
                      SC.foot("R", (0.20, -0.78), 10.0, heel=-60.0, lift=0.08, knee=(0.0, 0.0, 2.0)),
                      SC.head(0.0, ww=0.0, neck=(16.0, 0.0, 0.0), rot=(10.0, 8.0, 0.0)))
    clip("knockdown", 30, keys=[
        (0, ready(), {}), (3, KD1, {}), (9, KD2, {}), (14, LY_BOUNCE, {}), (20, LYING, {"t": 0.8}), (30, LYING, HOLD)],
        purpose="blown off her feet: impact, a backward fall, the bounce, lying on her back with the capes spread",
        maps_to="a knockback / launch strong enough to floor the hero (stun >= 0.8 s); holds its last frame until get_up",
        events={"impact": 1, "ground": 14})
    GU1 = merge(SC.pelvis((0.0, 0.40, -0.97), (-30.0, 0.0, 0.0)), SC.spine(14.0), SC.head(10.0, ww=0.6, neck=(4.0, 0.0, 0.0)),
                SC.foot("L", CLs, 10.0, knee=(0.4, 0.0, 2.0)), SC.foot("R", (0.20, -0.76), 10.0, heel=-60.0, lift=0.03, knee=(0.0, 0.0, 2.0)),
                SC.arm("L", (0.40, 0.66, 0.14), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"),
                SC.arm("R", (0.46, 0.62, 0.20), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"),
                {"hold": 0.0, "fingers_L": 0.3, "fingers_R": GRIP_CURL_R})
    GU_TUCK = merge(SC.pelvis((0.0, 0.34, -0.90), (-6.0, -6.0, 0.0)), SC.spine(22.0, 4.0), SC.head(10.0),
                    SC.foot("L", CLs, 10.0, knee=(0.4, 0.0, 1.0)), SC.foot("R", (0.20, -0.20), 12.0, lift=0.16, heel=30.0, knee=(0.0, 0.0, 1.0)),
                    SC.arm("L", (0.34, 0.42, 0.26), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"),
                    SC.arm("R", (0.46, 0.20, 0.34), pole=(0.9, 0.4, 1.2), back=(0.0, 0.0, 1.0), space="abs"),
                    {"hold": 0.0})
    GU2 = merge(SC.pelvis((0.0, 0.22, -0.72), (22.0, -12.0, 0.0)), SC.spine(18.0, -8.0), SC.head(8.0),
                SC.foot("L", CLs, 10.0), SC.foot("R", (0.20, 0.42), 14.0, heel=72.0),
                SC.arm("L", (0.30, -0.42, -0.10), pole=(0.8, 0.2, -0.6), back=(0.4, 0.3, 0.8)),
                SC.arm("R", (0.36, -0.20, 0.40), pole=(0.8, -0.2, 1.4), back=(0.0, 0.0, 1.0), space="abs"), {"hold": 0.0})
    GU3 = merge(SC.pelvis((0.0, 0.12, -0.40), (26.0, -16.0, 0.0)), SC.spine(20.0, -18.0), SC.head(4.0),
                SC.foot("L", CLs, 10.0), SC.foot("R", (0.20, 0.42), 18.0, heel=45.0), gun(-34.0, 46.0, de=-8.0, h=0.7))
    clip("get_up", 36, keys=[
        (0, LYING, {}), (7, GU1, {}), (12, GU_TUCK, {}), (16, GU2, {"t": 0.8}), (23, GU3, {}),
        (27, ready(dz=-0.12, lean=10.0, fr=(0.18, 0.24), lift_r=0.10), {}),
        (30, ready(dz=-0.06, lean=4.0), {"t": 0.8}), (36, ready(), {})],
        purpose="from her back: up on the left hand, roll onto one knee with the launcher gathered in, rise into the hold",
        maps_to="the knockdown's stun ends",
        events={"stand": 30})

    # -- death / downed / revive / reforge -------------------------------------------------------------------------------------
    hang_r = v.carry(upper=(-84.0, 14.0), fore=(-72.0, 40.0))
    D1 = merge(ready(dz=-0.02, lean=-16.0, twist=10.0, py=0.04, de=18.0, h=0.4), SC.head(-26.0, 8.0, 0.0), {"fingers_L": 0.15})
    D2 = merge(combat(dz=-0.38, lean=24.0, twist=4.0), SC.head(0.0, ww=0.3, neck=(14.0, 0.0, 0.0), rot=(12.0, 6.0, 0.0)),
               hang_r, v.free_l(upper=(-80.0, 20.0), fore=(-75.0, 40.0), f=0.3), {"hold": 0.0})
    KNEEL = merge(SC.pelvis((0.0, -0.02, -0.56), (10.0, -8.0, 4.0)), SC.spine(18.0, 0.0, 6.0),
                  SC.head(0.0, ww=0.0, neck=(20.0, 0.0, 0.0), rot=(16.0, 8.0, 0.0)),
                  SC.foot("L", CLs, 10.0), SC.foot("R", CRs, 22.0, heel=75.0), hang_r,
                  v.free_l(upper=(-84.0, 16.0), fore=(-80.0, 30.0), f=0.35), {"hold": 0.0})
    TOPPLE = merge(SC.pelvis((0.0, -0.16, -0.72), (48.0, 0.0, 8.0)), SC.spine(24.0, 0.0, 8.0),
                   SC.head(0.0, ww=0.0, neck=(16.0, 10.0, 0.0), rot=(10.0, 14.0, 0.0)),
                   SC.foot("L", (0.22, 0.10), 10.0, heel=70.0, lift=0.10), SC.foot("R", (0.20, 0.40), 14.0, heel=95.0, lift=0.08),
                   SC.arm("L", (0.46, -0.72, 0.16), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"),
                   SC.arm("R", (0.40, -0.58, 0.20), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"), {"hold": 0.0})
    PRONE = merge(SC.pelvis((0.0, -0.18, -0.945), (84.0, 0.0, 3.0)), SC.spine(4.0, 0.0, 2.0),
                  SC.head(0.0, ww=0.0, neck=(-12.0, 34.0, 0.0), rot=(-6.0, 20.0, 0.0)),
                  SC.foot("L", (0.22, 0.86), 12.0, heel=112.0, lift=0.06), SC.foot("R", (0.18, 0.90), 14.0, heel=116.0, lift=0.06),
                  SC.arm("L", (0.62, -1.02, 0.13), pole=(1.2, -0.6, 1.4), back=(0.2, 0.2, 1.0), space="abs"),
                  SC.arm("R", (0.50, -0.06, 0.16), pole=(1.0, 0.4, 1.4), back=(0.4, 0.0, 1.0), space="abs"),
                  {"hold": 0.0, "fingers_L": 0.3})
    clip("death", 48, keys=[
        (0, ready(), {}), (4, D1, {}), (12, D2, {}), (20, KNEEL, {"t": 0.5}),
        (25, merge(KNEEL, SC.pelvis((0.0, -0.03, -0.58), (14.0, -8.0, 6.0))), {}), (31, TOPPLE, {}), (36, PRONE, {}),
        (39, merge(PRONE, SC.pelvis((0.0, -0.18, -0.925), (82.0, 0.0, 3.0))), {}), (48, PRONE, HOLD)],
        purpose="the fatal blow: the head snaps back, the launcher sags, the knees buckle, she topples face down",
        maps_to="LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look)",
        events={"impact": 1, "knee": 20, "ground": 36})

    def wraith(b, sw, ad):
        return merge(SC.pelvis((0.0, 0.02, -0.24 + 0.05 * b), (24.0, 4.0 * sw, 3.0 * sw)), SC.spine(30.0, -3.0 * sw, 4.0 * sw),
                     SC.head(0.0, ww=0.0, neck=(12.0, 0.0, 0.0), rot=(16.0, 6.0 * sw, 0.0)),
                     SC.foot("L", (0.14, 0.34 + 0.03 * b), 8.0, lift=0.36 + 0.05 * b, heel=100.0, knee=(0.0, -1.0, 0.0)),
                     SC.foot("R", (0.13, 0.42 - 0.03 * b), 10.0, lift=0.30 + 0.05 * b, heel=108.0, knee=(0.0, -1.0, 0.0)),
                     v.carry(upper=(-84.0, 12.0 + 6.0 * ad), fore=(-78.0, 36.0)),
                     v.free_l(upper=(-82.0, 14.0 - 6.0 * ad), fore=(-76.0, 30.0), f=0.35), {"hold": 0.0}, SC.clav((8.0, 0.0, -6.0)))
    clip("downed", 60, loop=True, keys=[
        (0, wraith(0, 0, 0), {}), (15, wraith(1, 0.6, 1), {}), (30, wraith(0.2, 0, 0), {}), (45, wraith(0.9, -0.6, -1), {})],
        purpose="the wraith drift: slumped, floating 0.35 m off the ground, the launcher trailing from a limp hand, a slow bob",
        maps_to="LifeState::Downed (the Soul-Tether wraith; moves at 45 % speed with no gait, the client adds the ghost material)",
        grounded=False)
    RV1 = merge(SC.pelvis((0.0, 0.0, -0.12), (-10.0, 0.0, 0.0)), SC.spine(-16.0), SC.head(-22.0),
                SC.foot("L", (0.20, -0.10), 10.0, lift=0.30, heel=60.0), SC.foot("R", (0.18, 0.20), 16.0, lift=0.26, heel=70.0),
                v.arm("L", (-15.0, 10.0), (-5.0, 20.0), back=(0.0, 1.0, 0.3)), v.carry(upper=(-20.0, -5.0), fore=(-10.0, 20.0)),
                {"hold": 0.0, "fingers_L": 0.05}, SC.clav((-8.0, 0.0, 10.0)))
    RV2 = merge(ready(dz=-0.22, lean=20.0, de=-6.0, h=0.8), SC.head(12.0))
    clip("revive", 40, keys=[
        (0, wraith(0, 0, 0), {}), (6, RV1, {}), (12, RV2, {"t": 0.8}), (22, ready(dz=-0.08, lean=6.0), {}),
        (30, ready(), {}), (34, merge(ready(), SC.head(0.0, 6.0, 3.0)), {}), (40, ready(), {})],
        purpose="pulled back into the body: a jolt with the arms flung wide, the feet slam down, crouch, rise into the hold",
        maps_to="an ally completes the Soul-Tether revive (Downed -> Alive)",
        events={"jolt": 6, "land": 12})
    SUPER = merge(SC.pelvis((0.0, 0.10, -0.64), (32.0, -14.0, 0.0)), SC.spine(18.0, -6.0), SC.head(22.0),
                  SC.foot("L", CLs, 10.0), SC.foot("R", (0.20, 0.48), 14.0, heel=74.0),
                  SC.arm("L", (0.30, -0.40, 0.14), pole=(0.8, 0.2, 1.4), back=(0.0, -1.0, 0.1), space="abs"),
                  v.carry(upper=(-40.0, -20.0), fore=(-25.0, 0.0)), {"hold": 0.0, "fingers_L": 0.1},
                  SC.clav((-4.0, 0.0, 4.0)))
    FLOURISH = merge(ready(dz=-0.04, lean=-2.0, de=10.0, twist=4.0), SC.head(-6.0))
    clip("reforge_in", 45, keys=[
        (0, SUPER, {}), (10, merge(SUPER, SC.pelvis((0.0, 0.10, -0.66), (33.0, -14.0, 0.0))), HOLD),
        (18, merge(SC.pelvis((0.0, 0.06, -0.34), (18.0, -14.0, 0.0)), SC.spine(12.0, -14.0), SC.head(4.0), SC.foot("L", CLs, 10.0),
                   SC.foot("R", (0.20, 0.48), 14.0, heel=40.0), gun(-28.0, 30.0, de=-10.0, h=0.5)), {}),
        (22, ready(dz=-0.08, fr=(0.18, 0.26), lift_r=0.10, de=-4.0), {}),
        (26, merge(FLOURISH, combat(dz=-0.04)), {"lin": True, "t": 0.6}), (28, FLOURISH, {}),
        (36, merge(ready(), SC.head(-2.0)), {}), (45, ready(), {})],
        purpose="forged anew: rises from a one-knee landing (the left claws on the ground), snaps the launcher up, takes the hold",
        maps_to="LifeState::Reforging ends: the hero reappears next to an ally",
        events={"clash": 28})

    # -- victory / social / world ----------------------------------------------------------------------------------------------
    V_LOAD = merge(ready(dz=-0.10, lean=10.0, twist=-8.0, de=-8.0), SC.head(18.0))
    V_UP = merge(combat(dz=-0.01, lean=-14.0, twist=12.0), SC.head(-24.0, 10.0),
                 v.arm("R", (72.0, 25.0), (44.0, 62.0), back=(0.0, 0.0, 1.0)),
                 v.arm("L", (-30.0, 0.0), (5.0, 25.0), back=(0.0, 0.2, -1.0)),
                 {"hold": 0.0, "fingers_L": 0.02, "fingers_R": GRIP_CURL_R}, SC.clav((-4.0, 0.0, 10.0), (-2.0, 0.0, 16.0)))
    V_HOLD = merge(V_UP, combat(dz=-0.03, lean=-10.0, twist=10.0), v.arm("R", (70.0, 25.0), (46.0, 60.0)), SC.head(-18.0, 8.0))
    clip("victory", 60, keys=[
        (0, ready(), {}), (10, V_LOAD, HOLD), (17, V_UP, {}), (24, V_HOLD, {}),
        (42, merge(V_HOLD, combat(dz=-0.04, lean=-9.0, twist=10.0)), {}), (60, V_HOLD, HOLD)],
        purpose="the storm answers: a crouch, then the launcher thrust to the sky, the left hand open wide; holds the pose",
        maps_to="the run is won (GameEvent victory / boss down, results screen); holds its last frame",
        events={"roar": 17})
    PING = merge(ready(twist=10.0, h=0.0), v.arm("L", (8.0, 70.0), (12.0, 84.0), back=(0.0, 0.0, 1.0)),
                 {"fingers_L": 0.0}, SC.head(-8.0, 4.0))
    clip("ping", 20, layer="upper", keys=[
        (0, ready(), {}), (2, ready(twist=4.0, h=0.6), {}), (5, PING, {}),
        (14, merge(PING, v.arm("L", (9.0, 72.0), (13.0, 85.0), back=(0.0, 0.0, 1.0))), HOLD),
        (17, ready(twist=3.0, h=0.7), {}), (20, ready(), {})],
        purpose="a ping: the left hand leaves the foregrip and points along the aim, open, the head follows",
        maps_to="the ping / marker input (party callout)",
        events={"ping": 5})
    I_REACH = merge(idle_key(0, 0, 0), SC.pelvis((0.0, -0.04, -0.12), (10.0, 0.0, 0.0)), SC.spine(26.0), SC.head(26.0, neck=(4.0, 0.0, 0.0)),
                    SC.arm("L", (0.18, -0.58, 1.10), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"),
                    v.carry(upper=(-70.0, 10.0), fore=(-60.0, 40.0)), {"fingers_L": 0.05})
    I_PRESS = merge(I_REACH, SC.pelvis((0.0, -0.06, -0.15), (12.0, 0.0, 0.0)), SC.spine(30.0),
                    SC.arm("L", (0.18, -0.58, 1.05), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"),
                    SC.clav((6.0, 0.0, -6.0)), {"fingers_L": 0.25})
    clip("interact", 40, keys=[
        (0, idle_key(0, 0, 0), {}), (9, I_REACH, {}), (12, I_PRESS, LIN), (14, I_PRESS, HOLD), (26, I_PRESS, HOLD),
        (40, idle_key(0, 0, 0), {})],
        purpose="work the anvil: lean over and press the left claws onto it (the launcher kept low in the right hand), straighten",
        maps_to="the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s",
        events={"contact": 12, "release": 26})

    def hammer(p):
        """p: 0 raised, 1 strike contact. Her LEFT hand strikes (the right keeps the launcher)."""
        return merge(SC.pelvis((0.0, 0.05, -0.08 - 0.05 * p), (10.0 + 6.0 * p, 6.0 - 8.0 * p, 0.0)),
                     SC.foot("R", (0.24, -0.18), 15.0), SC.foot("L", (0.22, 0.04), 25.0),
                     SC.spine(4.0 + 20.0 * p, 14.0 - 20.0 * p), SC.head(14.0 + 10.0 * p),
                     SC.clav((0.0, 0.0, 14.0 - 16.0 * p), (0.0, 0.0, 8.0 - 8.0 * p)),
                     v.carry(upper=(-80.0, 20.0), fore=(-45.0, 70.0)), {"hold": 0.0})
    H_TOP = merge(hammer(0), SC.arm("L", (0.06, 0.02, 0.70), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3)), {"fingers_L": 0.05})
    H_DOWN = merge(hammer(0.6), SC.arm("L", (0.00, -0.50, 0.12), pole=(0.8, 0.4, -0.4), back=(0.1, 0.4, 0.9)))
    H_HIT = merge(hammer(1.0), SC.arm("L", (0.10, -0.60, 1.07), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"),
                  {"fingers_L": 0.25})
    H_REB = merge(hammer(0.85), SC.arm("L", (0.10, -0.58, 1.18), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"))
    H_UP = merge(hammer(0.35), SC.arm("L", (0.06, -0.26, 0.40), pole=(0.8, 0.4, -0.2), back=(0.2, 0.6, 0.7)), {"fingers_L": 0.05})
    clip("forge_hammer", 36, loop=True, keys=[
        (0, H_TOP, HOLD), (6, H_DOWN, LIN), (8, H_HIT, {}), (11, H_REB, {}), (20, H_UP, {}),
        (30, merge(H_TOP, SC.arm("L", (0.07, 0.00, 0.64), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3))), {})],
        purpose="charging the anvil: the left palm raised, slammed down onto the work in a crackle, again",
        maps_to="the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil)",
        events={"hammer_hit": 8})
    shared = list(C)

    # -- her kit (brief section 7.1) -------------------------------------------------------------------------------------------
    C.clear()

    def hover(b, sw, look=0.0):
        return merge(SC.pelvis((0.018 * sw, 0.0, 0.05 + 0.025 * b), (1.0 + 1.5 * b, -4.0 + 4.0 * sw, 2.0 * sw)),
                     SC.foot("L", (0.11, -0.10 + 0.02 * b), 8.0, lift=0.07 + 0.025 * b, heel=34.0, knee=(0.0, -0.5, 0.0)),
                     SC.foot("R", (0.12, -0.02 - 0.02 * b), 16.0, lift=0.05 + 0.025 * b, heel=40.0, knee=(0.0, -0.5, 0.0)),
                     SC.spine(-1.0 + 2.0 * b, 3.0 * sw, 1.5 * sw), SC.head(-2.0 + 2.0 * b, 6.0 * look, 3.0 * sw),
                     v.carry(upper=(-78.0, 18.0 + 4.0 * sw), fore=(-44.0, 72.0)),
                     v.free_l(upper=(-64.0 + 6.0 * b, 20.0 - 6.0 * sw), fore=(-34.0 + 8.0 * b, 58.0), back=(0.2, 0.0, -1.0),
                              f=0.08 + 0.3 * abs(sw)),
                     {"hold": 0.0}, SC.clav((0.0, 0.0, -2.0 + 2.0 * b)))
    clip("idle_signature", 90, loop=True, family="selene", keys=[
        (0, hover(0, 0, 0), {}), (22, hover(1, 0.8, 0.5), {}), (45, hover(0.3, 0.1, 1.0), {}), (68, hover(0.9, -0.8, -0.4), {})],
        purpose="lightning in human shape, barely touching the ground: a slow hover sway a hand's breadth up, the left claws "
                "flexing (the crackle; the vein pulse is an emissive VFX), the cloth breathing, the crown bobbing",
        maps_to="standing out of combat for 6 s (then back to idle on any input)", grounded=False)
    NOVA_WIND = merge(ready(dz=-0.04, lean=4.0, twist=-8.0, de=-6.0, h=0.2), v.arm("L", (-50.0, 70.0), (-5.0, 140.0), back=(0.0, 1.0, 0.0)),
                      {"fingers_L": 0.85})
    NOVA = merge(ready(dz=-0.02, lean=8.0, twist=8.0, de=2.0, h=0.0, upper=(-40.0, 40.0)),
                 v.arm("L", (4.0, 50.0), (6.0, 62.0), back=(0.0, -0.3, 1.0)), {"fingers_L": 0.0}, SC.head(4.0),
                 SC.clav((10.0, 0.0, 4.0)))
    NOVA2 = merge(NOVA, ready(dz=-0.02, lean=6.0, twist=7.0, de=3.0, h=0.0, upper=(-42.0, 38.0)),
                  v.arm("L", (4.0, 50.0), (6.0, 62.0), back=(0.0, -0.3, 1.0)), {"fingers_L": 0.0})
    clip("arc_nova", 18, layer="upper", family="selene", keys=[
        (0, ready(), {}), (4, NOVA_WIND, HOLD), (6, NOVA, LIN), (10, NOVA2, HOLD), (14, ready(twist=2.0, h=0.6), {}),
        (18, ready(), {})],
        purpose="Arc Nova: gather (the left claws clenched at the chest), then both hands snap forward and apart, the claws "
                "spread, the launcher thrust out: the chain burst leaves her",
        maps_to="active1 Arc Nova cast (chain-lightning burst); upper layer, so she keeps moving", events={"cast": 6})
    B_CROUCH = merge(ready(dz=-0.16, lean=18.0, twist=-2.0, heel_r=30.0, de=-4.0), SC.head(10.0))
    B_GO = merge(ready(dz=-0.10, lean=30.0, twist=-2.0, heel_l=20.0, heel_r=60.0, lift_r=0.06, de=-8.0, h=0.45), SC.head(14.0))
    clip("blink_out", 10, family="selene", keys=[(0, ready(), {}), (4, B_CROUCH, {}), (8, B_GO, LIN), (10, B_GO, HOLD)],
         purpose="Blink, out: a crouch and a lean into the move; the model is hidden from the 'vanish' frame (storm trail VFX)",
         maps_to="active2 Blink starts (the 7 m teleport through enemies); the client hides the model at 'vanish'",
         events={"vanish": 8})
    B_ARR = merge(ready(dz=-0.12, lean=20.0, twist=-2.0, lift_r=0.08, heel_r=45.0, de=-6.0, h=0.6), SC.head(8.0))
    clip("blink_in", 14, family="selene", keys=[
        (0, B_ARR, {}), (3, merge(ready(dz=-0.19, lean=14.0, de=-4.0), SC.head(6.0)), {"t": 0.6}),
        (8, ready(dz=-0.06, lean=4.0), {}), (14, ready(), {})],
        purpose="Blink, in: she arrives leaning out of the jump, lands soft on the lead foot and settles into the hold",
        maps_to="active2 Blink ends (the model reappears at the target point)", events={"appear": 0, "land": 3})

    def verdict(b, sw):
        return merge(SC.pelvis((0.02 * sw, 0.0, 0.07 + 0.025 * b), (-4.0, 4.0 * sw, 3.0 * sw)), SC.spine(-8.0, -3.0 * sw, 2.0 * sw),
                     SC.head(-20.0 + 3.0 * b, 6.0 * sw, 0.0),
                     SC.foot("L", CLs, 12.0, lift=0.07 + 0.02 * b, heel=36.0, knee=(0.0, -0.4, 0.0)),
                     SC.foot("R", CRs, 34.0, lift=0.06 + 0.02 * b, heel=40.0, knee=(0.0, -0.4, 0.0)),
                     v.arm("R", (66.0 + 3.0 * b, 28.0 + 5.0 * sw), (50.0, 58.0), back=(0.0, 0.0, 1.0)),
                     v.arm("L", (64.0 + 3.0 * b, 22.0 - 5.0 * sw), (78.0, 34.0), back=(0.0, -1.0, 0.0)),
                     {"hold": 0.0, "fingers_L": 0.04, "fingers_R": GRIP_CURL_R}, SC.clav((-2.0, 0.0, 12.0)))
    GATHER = merge(combat(dz=-0.12, lean=10.0), SC.head(16.0), v.carry(upper=(-70.0, 40.0), fore=(-30.0, 100.0)),
                   v.arm("L", (-55.0, 60.0), (-5.0, 145.0), back=(0.0, 1.0, 0.0)), {"hold": 0.0, "fingers_L": 0.9})
    RISE = merge(SC.pelvis((0.0, 0.0, 0.0), (-2.0, -6.0, 0.0)), SC.spine(-4.0, -4.0), SC.head(-10.0),
                 SC.foot("L", CLs, 12.0, heel=24.0), SC.foot("R", CRs, 34.0, heel=28.0),
                 v.arm("R", (35.0, 22.0), (40.0, 50.0), back=(0.0, 0.0, 1.0)), v.arm("L", (38.0, 18.0), (55.0, 28.0), back=(0.0, -1.0, 0.0)),
                 {"hold": 0.0, "fingers_L": 0.3})
    clip("heavens_verdict_start", 36, family="selene", keys=[
        (0, ready(), {}), (8, GATHER, HOLD), (16, RISE, {}), (22, verdict(1.0, 0.0), {}), (30, verdict(0.2, 0.0), {}),
        (36, verdict(0.0, 0.0), {})],
        purpose="Heaven's Verdict, the call: gather low, sweep both arms up, head back, lifted off the ground as the storm "
                "front is called ('call'); ends on the verdict loop's frame 0",
        maps_to="ultimate Heaven's Verdict cast (the storm front placed at the aim point)", events={"call": 22},
        grounded=False)
    clip("heavens_verdict", 60, loop=True, family="selene", keys=[
        (0, verdict(0.0, 0.0), {}), (15, verdict(1.0, 0.6), {}), (30, verdict(0.2, 0.0), {}), (45, verdict(0.9, -0.6), {})],
        purpose="Heaven's Verdict, sustained: hovering with both arms raised to the storm, a slow sway, the crown swaying "
                "wide round the head (the shard bones), the cloth lifted",
        maps_to="while the Heaven's Verdict cast lasts (the client may cut back to locomotion when she moves)",
        grounded=False)
    CH = merge(ready(dz=-0.03, lean=6.0, twist=-4.0, h=0.0), v.arm("L", (-48.0, 55.0), (4.0, 150.0), back=(0.0, 1.0, 0.2)),
               {"fingers_L": 1.0}, SC.head(8.0, -6.0))

    def tremble(k):
        return merge(CH, v.arm("L", (-48.0 + 2.0 * k, 55.0 - 2.0 * k), (4.0 + 3.0 * k, 150.0 + 3.0 * k), back=(0.0, 1.0, 0.2)))
    clip("static_charge", 24, layer="upper", family="selene", keys=[
        (0, ready(), {}), (4, CH, {}), (8, tremble(1), {}), (10, tremble(-1), {}), (12, tremble(1), {}), (14, tremble(-1), {}),
        (18, ready(h=0.6), {}), (24, ready(), {})],
        purpose="Static Charge full: the left hand leaves the foregrip and clenches in front of her chest, trembling, a "
                "crackle; back to the foregrip",
        maps_to="passive Static Charge reaches its cap (+60 %): played once in the upper layer", events={"crackle": 12})
    unique = list(C)
    return shared, unique


_CACHE = {}


def _built(K):
    k = id(K)
    if k not in _CACHE:
        _CACHE[k] = build(K)
    return _CACHE[k]


def shared_clips(K):
    return _built(K)[0]


def unique_clips(K):
    return _built(K)[1]
