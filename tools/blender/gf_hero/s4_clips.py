"""The GF_Hero_v1 shared clip library (stage 4): one definition for every hero, baked per hero at the hero's own
proportions (s4lib.Kit scales every offset by the hero's leg / arm length) and move speed.

Poses are s4lib pose dicts (see s4lib.py). Numbers are written at Brax's build (the reference: leg 1.08 m, arm 0.79 m,
2.2 m tall). Conventions (docs/art/GF_HERO_SKELETON.md section 1): the hero faces -Y, +X is his LEFT, Z up. The arm() and
foot() helpers take LEFT-side terms for both sides (x = outward from that side), so one number means the same thing on
either arm.

Style: strong readable poses for a 55 degree top-down camera at 65-86 px: every action has an anticipation, a contact
and a follow-through; weight shows in the pelvis (drop on contact, rise on push-off); the head stabilises (world-space
head orientation) so the face keeps reading while the body works, and goes limp (FK) in falls. Clips are in place (the
engine moves the entity): locomotion feet travel under the body at exactly the design speed; everything else keeps
planted feet planted. Upper-layer clips ("layer": "upper") keep the lower body on the combat stance, so spine_01 and
its children can be layered over locomotion; their first and last frames are the idle_combat reference pose.

Adapted in spirit from the user's Ashen Covenant clip tables (p05_animations.py IDLE / RUN / HS / DODGE,
ironwarden_m_gameplay_anims.py PLAYER_DEATH / HIT_REACTION / ATTACK_1H): pose tables merged from shared bases, fist
curls, breath / sway variations, the impact / absorb / rebound / settle arc of hits.
"""
import math

from s4lib import FPS, Clip, _mirror_entry, merge

HOLD = {"t": 1.0}          # a held key: zero velocity (anticipation peaks, holds)
LIN = {"lin": True}        # the segment after this key is linear (a snap into contact)


# ---- helpers ---------------------------------------------------------------------------------------------------------
def spine(fwd=0.0, twist=0.0, side=0.0, w=(0.36, 0.34, 0.30)):
    """A bend spread over spine_01..03 (local degrees; fwd bends forward, twist turns the chest to the hero's left,
    side leans toward the hero's right)."""
    return {"spine_0%d" % (i + 1): {"rot": (fwd * w[i], twist * w[i], side * w[i])} for i in range(3)}


def arm(side, fist, pole=(0.40, 0.15, -0.80), back=(0.30, 0.30, 0.90), space="chest"):
    """An arm effector in LEFT-side terms (x outward from the shoulder, y back, z up), mirrored for the right arm."""
    spec = {"fist": tuple(fist), "pole": tuple(pole), "back": tuple(back), "space": space}
    if side == "R":
        spec = {k: _mirror_entry(k, v) for k, v in spec.items()}
    return {"arm_" + side: spec}


def arms(fist, **kw):
    return merge(arm("L", fist, **kw), arm("R", fist, **kw))


def foot(side, ball, yaw=8.0, **kw):
    """A foot in LEFT-side terms: ball (x outward, y), yaw (+ toes out), heel / lift / toe / knee."""
    spec = {"ball": (ball[0] if side == "L" else -ball[0], ball[1]), "yaw": yaw if side == "L" else -yaw}
    for k, v in kw.items():
        spec[k] = (-v[0], v[1], v[2]) if (k == "knee" and side == "R") else v
    return {"foot_" + side: spec}


def fists(a=1.0, b=None):
    return {"fingers_L": a, "fingers_R": a if b is None else b}


def head(fwd=0.0, yaw=0.0, side=0.0, ww=1.0, neck=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
    """The head stabilised in world space (ww=1) or limp on FK (ww=0: rot is the local head rotation)."""
    return {"head": {"wrot": (fwd, yaw, side), "ww": ww, "rot": rot}, "neck": {"rot": neck}}


def pelvis(loc=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
    return {"pelvis": {"loc": tuple(loc), "rot": tuple(rot)}}


def clav(l=(0.0, 0.0, 0.0), r=None):
    r = r if r is not None else l
    return {"clavicle_L": {"rot": tuple(l)}, "clavicle_R": {"rot": (r[0], -r[1], -r[2])}}


# ---- stances -----------------------------------------------------------------------------------------------------------
def relaxed(dz=0.0, sway=0.0, lean=0.0):
    """Relaxed stance: feet a little inside the shoulders, toes out, soft knees, a slight brute hunch."""
    return merge(pelvis((sway * 0.022, 0.0, -0.012 + dz), (3.0 + lean * 0.3, 0.0, -sway * 1.2)),
                 foot("L", (0.28, -0.13), 14.0), foot("R", (0.28, -0.13), 14.0),
                 spine(4.0 + lean, sway * 1.5), head(neck=(-4.0, 0.0, 0.0)), clav((0.0, 0.0, -3.0)))


ARMS_HANG = arms((0.31, -0.07, -0.70), pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.20))

# the combat stance positions (left foot a half step forward)
CL = (0.27, -0.26)
CR = (0.25, 0.10)


def combat(dz=0.0, lean=0.0, twist=0.0, hip_yaw=0.0, heel_l=0.0, heel_r=0.0, fl=CL, fr=CR, lift_l=0.0, lift_r=0.0,
           py=0.0):
    """Combat stance: wide and low, the torso over the knees, the pelvis turned a little so the lead shoulder leads."""
    return merge(pelvis((0.0, 0.03 + py, -0.11 + dz), (8.0 + lean * 0.4, -8.0 + hip_yaw, 0.0)),
                 foot("L", fl, 10.0, heel=heel_l, lift=lift_l), foot("R", fr, 22.0, heel=heel_r, lift=lift_r),
                 spine(10.0 + lean * 0.6, 6.0 + twist), head(neck=(-8.0, 0.0, 0.0)), clav((4.0, 0.0, 2.0)))


def guard(dl=(0.0, 0.0, 0.0), dr=(0.0, 0.0, 0.0), f=1.0):
    """The guard: gauntlets up by the chin, knuckles forward and up, forearms parallel, elbows down (the two
    gauntlets frame the face from the 55 deg camera instead of crossing in front of the chest); the lead (left) fist a
    little forward. dl / dr offset each fist (left-side terms)."""
    return merge(arm("L", (0.05 + dl[0], -0.50 + dl[1], 0.30 + dl[2]), pole=(0.12, 0.10, -1.0), back=(0.35, 0.55, 0.75)),
                 arm("R", (0.02 + dr[0], -0.42 + dr[1], 0.34 + dr[2]), pole=(0.12, 0.10, -1.0), back=(0.35, 0.55, 0.75)), fists(f))


def combat_guard(**kw):
    return merge(combat(**kw), guard())


# ---- locomotion generator -----------------------------------------------------------------------------------------
def smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def locomotion(length, speed, direction=(0.0, -1.0), duty=0.5, stance_half=0.14, hip_yaw=0.0, foot_yaw=6.0,
               lift=0.18, lift_peak=0.45, heel_off=30.0, heel_land=0.0, heel_swing=35.0, shift=0.0, match=1.0,
               bob=0.03, drop=0.06, sway=0.025, pelvis_fwd=6.0, pelvis_twist=6.0, spine_fwd=6.0, spine_counter=8.0,
               upper=None, knee_out=0.0, phase0=0.0, base_y=-0.10):
    """Per-frame pose function of an in-place gait cycle.

    Phase 0 is the left foot's touch-down; frame 0 sits at phase `phase0` (the loop seam goes in the flight / passing
    phase). During contact the feet move under the body at exactly `speed` (m/s at Brax scale; Kit scales it to the
    hero) against `direction` (the travel direction in hero space: x = hero's left, y = back). The swing is a Hermite
    curve whose end tangents match `match` x the ground speed (1 = the foot lands and leaves at ground speed, no
    velocity step). bob > 0 puts the pelvis lowest at mid-stance (run), bob < 0 highest (walk). upper(p, c1) adds
    the arms / chest (p = phase, c1 = cos(2 pi p): +1 left leg forward). Returns fn(frame) -> pose."""
    dx, dy = direction
    n = math.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    T = length / FPS
    Lc = speed * duty * T
    cyaw = math.cos(math.radians(hip_yaw))
    syaw = math.sin(math.radians(hip_yaw))
    m = -Lc * (1.0 - duty) / duty * match
    a_, b_ = lift_peak * 3.0, (1.0 - lift_peak) * 3.0
    norm = (lift_peak ** a_) * ((1.0 - lift_peak) ** b_)

    def foot_at(ph, s):
        sgn = 1.0 if s == "L" else -1.0
        bx0, by0 = sgn * stance_half, base_y
        bx = bx0 * cyaw - by0 * syaw
        by = bx0 * syaw + by0 * cyaw
        yaw = hip_yaw + sgn * foot_yaw
        if ph < duty:
            u = ph / duty
            d = Lc * (0.5 - u) + shift
            h = heel_land * (1.0 - smooth(u / 0.3)) + heel_off * smooth((u - 0.55) / 0.45)
            return {"ball": (bx + dx * d, by + dy * d), "lift": 0.0, "yaw": yaw, "heel": h}
        u = (ph - duty) / (1.0 - duty)
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        d = h00 * (-Lc * 0.5) + h10 * m + h01 * (Lc * 0.5) + h11 * m + shift
        ht = lift * (u ** a_) * ((1.0 - u) ** b_) / norm
        h = heel_off + (heel_swing - heel_off) * smooth(u / 0.35)
        h = h * (1.0 - smooth((u - 0.45) / 0.45)) + heel_land * smooth((u - 0.6) / 0.4)
        return {"ball": (bx + dx * d, by + dy * d), "lift": max(0.0, ht), "yaw": yaw, "heel": h}

    def fn(f):
        p = ((f % length) / length + phase0) % 1.0
        c1 = math.cos(2 * math.pi * p)
        z = -drop - bob * math.cos(4 * math.pi * (p - duty * 0.5))
        x = sway * math.cos(2 * math.pi * (p - duty * 0.5))
        pose = {"pelvis": {"loc": (x * cyaw, x * syaw, z), "rot": (pelvis_fwd, hip_yaw - pelvis_twist * c1, 0.0)},
                "foot_L": foot_at(p, "L"), "foot_R": foot_at((p + 0.5) % 1.0, "R")}
        pose.update(spine(spine_fwd, -hip_yaw * 0.8 + spine_counter * c1))
        pose.update(head(neck=(-spine_fwd * 0.5, 0.0, 0.0)))
        if knee_out:
            pose["foot_L"]["knee"] = (knee_out, 0.0, 0.0)
            pose["foot_R"]["knee"] = (-knee_out, 0.0, 0.0)
        if upper:
            pose = merge(pose, upper(p, c1))
        return pose
    return fn


def pump_arms(fwd=0.20, up=0.10, base=(0.08, -0.37, -0.34)):
    """Brawler arm pump for runs: fists in front of the ribs, opposite to the legs (p=0: left leg forward, so the
    right arm is forward)."""
    def upper(p, c1):
        return merge(arm("L", (base[0], base[1] + fwd * c1, base[2] - up * c1), pole=(0.55, 0.35, -0.45), back=(0.4, 0.1, 0.9)),
                     arm("R", (base[0], base[1] - fwd * c1, base[2] + up * c1), pole=(0.55, 0.35, -0.45), back=(0.4, 0.1, 0.9)),
                     fists(1.0), clav((6.0 * c1, 0.0, 0.0), (-6.0 * c1, 0.0, 0.0)))
    return upper


def swing_arms(amp=0.15):
    """Walk: heavy gauntlets swinging at the sides, opposite to the legs."""
    def upper(p, c1):
        return merge(arm("L", (0.31, -0.07 + amp * c1, -0.69 + 0.04 * abs(c1)), pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.2)),
                     arm("R", (0.31, -0.07 - amp * c1, -0.69 + 0.04 * abs(c1)), pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.2)),
                     fists(1.0))
    return upper


def guard_bounce(amp=0.03):
    def upper(p, c1):
        c2 = math.cos(4 * math.pi * p)
        return guard(dl=(0.0, 0.0, amp * c2), dr=(0.0, 0.0, amp * c2))
    return upper


# ---- the shared library --------------------------------------------------------------------------------------------
def shared_clips(K):
    v = K.move_speed / K.ls          # the generator works at Brax scale; Kit scales the stride back to the hero
    C = []

    # -- idles -------------------------------------------------------------------------------------------------------
    def idle_key(breath, sway, look):
        return merge(relaxed(dz=-0.006 * breath, sway=sway, lean=-breath * 2.0), ARMS_HANG, fists(1.0),
                     head(-1.5 * breath, look * 7.0, 0.0, neck=(-4.0 - breath, look * 3.0, 0.0)),
                     clav((-breath * 1.5, 0.0, -3.0 + breath * 2.5)))
    C.append(Clip("idle", 90, loop=True, keys=[
        (0, idle_key(0, 0, 0), {}), (24, idle_key(1, 0.7, 0.4), {}), (45, idle_key(0.2, 1.0, 1.0), {}),
        (68, idle_key(-0.6, 0.2, -0.3), {})],
        purpose="relaxed breathing stance, weight drifting between the feet",
        maps_to="alive, not moving, out of combat (no enemy near, no attack for 2 s; hub)"))

    def combat_key(b, tw):
        return merge(combat(dz=-0.025 * b, lean=3.0 * b, hip_yaw=tw, twist=-tw), guard(dl=(0, 0, -0.02 * b), dr=(0, 0, -0.02 * b)),
                     head(neck=(-8.0 - 2.0 * b, 0.0, 0.0)))
    C.append(Clip("idle_combat", 32, loop=True, keys=[
        (0, combat_key(0, 0), {}), (8, combat_key(1, 2), {}), (16, combat_key(0, 0), {}), (24, combat_key(1, -2), {})],
        purpose="combat-ready stance: guard up, a light bounce on the knees",
        maps_to="alive, not moving, in combat (enemies near or an attack in the last 2 s). Frame 0 is the reference "
                "pose of every upper-layer clip"))

    # -- locomotion ----------------------------------------------------------------------------------------------------
    walk_v = 1.8
    C.append(Clip("walk", 28, loop=True, travel=(0.0, -walk_v * K.ls), speed=round(walk_v * K.ls, 3),
                  fn=locomotion(28, walk_v, duty=0.62, stance_half=0.15, lift=0.10, lift_peak=0.4, heel_off=22.0,
                                heel_land=-10.0, heel_swing=12.0, bob=-0.02, drop=0.085, sway=0.03, pelvis_fwd=4.0,
                                pelvis_twist=6.0, spine_fwd=6.0, spine_counter=7.0, upper=swing_arms(0.15), phase0=0.16),
                  purpose="heavy walk, gauntlets swinging at the sides",
                  maps_to="moving at under about 55 %% of move speed (stick partly pushed, slows); playback rate = speed / "
                          "%.2f m/s" % (walk_v * K.ls)))
    C.append(Clip("run", 20, loop=True, travel=(0.0, -K.move_speed), speed=K.move_speed,
                  fn=locomotion(20, v, duty=0.25, stance_half=0.12, lift=0.32, lift_peak=0.38, heel_off=45.0,
                                heel_land=4.0, heel_swing=60.0, shift=-0.12, match=0.6, bob=0.04, drop=0.085, sway=0.02,
                                pelvis_fwd=16.0, pelvis_twist=9.0, spine_fwd=13.0, spine_counter=11.0,
                                upper=pump_arms(), phase0=0.30),
                  purpose="brawler run: forward lean, gauntlets pumping in front of the ribs",
                  maps_to="moving within 45 deg of the aim at move speed; playback rate = speed / %.1f m/s" % K.move_speed))
    strafe = dict(duty=0.24, stance_half=0.15, foot_yaw=4.0, lift=0.22, lift_peak=0.40, heel_off=35.0, heel_land=0.0,
                  heel_swing=40.0, match=0.6, bob=0.035, drop=0.13, sway=0.0, pelvis_fwd=10.0, pelvis_twist=5.0,
                  spine_fwd=8.0, spine_counter=5.0, upper=guard_bounce(), phase0=0.30)
    C.append(Clip("strafe_left", 20, loop=True, travel=(K.move_speed, 0.0), speed=K.move_speed,
                  fn=locomotion(20, v, direction=(1.0, 0.0), hip_yaw=38.0, **strafe),
                  purpose="side run to the hero's left, hips opened toward the travel, chest and guard kept on the aim",
                  maps_to="moving 45-135 deg to the left of the aim; playback rate = speed / %.1f m/s" % K.move_speed))
    C.append(Clip("strafe_right", 20, loop=True, travel=(-K.move_speed, 0.0), speed=K.move_speed,
                  fn=locomotion(20, v, direction=(-1.0, 0.0), hip_yaw=-38.0, **strafe),
                  purpose="side run to the hero's right (the mirror of strafe_left)",
                  maps_to="moving 45-135 deg to the right of the aim; playback rate = speed / %.1f m/s" % K.move_speed))
    C.append(Clip("backpedal", 18, loop=True, travel=(0.0, K.move_speed), speed=K.move_speed,
                  fn=locomotion(18, v, direction=(0.0, 1.0), duty=0.30, stance_half=0.15, foot_yaw=8.0, lift=0.17,
                                lift_peak=0.45, heel_off=8.0, heel_land=24.0, heel_swing=30.0, match=0.6, bob=0.03,
                                drop=0.14, sway=0.015, pelvis_fwd=12.0, pelvis_twist=5.0, spine_fwd=9.0, spine_counter=5.0,
                                upper=guard_bounce(0.025), phase0=0.30, base_y=-0.14),
                  purpose="backpedal on the balls of the feet, guard up, weight forward",
                  maps_to="moving more than 135 deg away from the aim; playback rate = speed / %.1f m/s" % K.move_speed))

    # -- dash --------------------------------------------------------------------------------------------------------------
    # the dash is shoulder-led: the lead gauntlet drives forward like a ram, the rear one trails low, so one gauntlet
    # always leads the silhouette whichever way the camera sees the dash
    DASH = merge(pelvis((0.0, -0.04, -0.22), (26.0, -10.0, 0.0)), spine(16.0, -16.0), head(14.0, neck=(-12.0, 0.0, 0.0)),
                 foot("L", (0.13, -0.50), 4.0, lift=0.30, heel=25.0), foot("R", (0.12, 0.55), 4.0, lift=0.24, heel=70.0),
                 arm("L", (0.02, -0.60, 0.20), pole=(0.35, 0.10, -1.0), back=(0.35, 0.45, 0.8)),
                 arm("R", (0.14, 0.26, -0.50), pole=(0.6, 0.4, -0.3), back=(0.7, 0.3, 0.4)),
                 fists(1.0), clav((10.0, 0.0, 0.0), (-6.0, 0.0, -2.0)))
    DASH2 = merge(DASH, pelvis((0.0, -0.05, -0.23), (28.0, -10.0, 0.0)), foot("L", (0.13, -0.53), 4.0, lift=0.26, heel=20.0),
                  foot("R", (0.12, 0.60), 4.0, lift=0.26, heel=75.0),
                  arm("L", (0.02, -0.64, 0.20), pole=(0.35, 0.10, -1.0), back=(0.35, 0.45, 0.8)))
    C.append(Clip("dash", 8, keys=[(0, combat_guard(), {}), (2, DASH, {}), (8, DASH2, {})],
                  purpose="the dash burst: a low shoulder-led lunge-glide, the lead gauntlet driving forward, the rear one trailing",
                  maps_to="the 0.16 s dash (MoverState.dash_left > 0); the client faces the hero along the dash for its duration",
                  events={"launch": 1}, grounded=False))
    LAND = merge(combat(dz=-0.13, lean=18.0, lift_r=0.10, fr=(0.22, 0.30), heel_r=40.0),
                 guard(dl=(0.06, -0.06, -0.20), dr=(0.10, 0.0, -0.22)), head(8.0, neck=(-12.0, 0.0, 0.0)))
    C.append(Clip("dash_recover", 14, keys=[
        (0, DASH2, {}), (3, LAND, {"t": 0.6}), (6, merge(combat(dz=-0.10, lean=12.0), guard(dl=(0.03, -0.03, -0.12), dr=(0.05, 0.0, -0.12))), {"t": 0.7}),
        (10, merge(combat(dz=-0.02, lean=2.0), guard()), {}), (14, combat_guard(), {})],
        purpose="landing out of the dash: the lead foot plants, a heavy absorb, back to the guard",
        maps_to="the first 0.45 s after a dash ends when the hero is not moving on (else blend into locomotion)",
        events={"land": 3}))

    # -- fire (upper layer, additive-friendly: first and last frame = idle_combat frame 0) ----------------------------
    FL_EXT = merge(combat(twist=16.0, lean=2.0), guard(),
                   arm("R", (-0.04, -0.72, 0.30), pole=(0.35, 0.3, -0.85), back=(0.2, 0.2, 1.0)), clav((4.0, 0.0, 2.0), (12.0, 0.0, -2.0)))
    C.append(Clip("fire_light", 8, layer="upper", keys=[
        (0, combat_guard(), {}), (2, FL_EXT, LIN), (3, merge(FL_EXT, arm("R", (-0.04, -0.66, 0.30), pole=(0.35, 0.3, -0.85), back=(0.2, 0.2, 1.0))), {}),
        (8, combat_guard(), {})],
        purpose="generic light shot: the weapon hand thrusts along the aim and snaps back (recoil stays procedural)",
        maps_to="each primary shot of a light chassis (fire_rate >= 2/s); Brax plays brax_jab_l / brax_jab_r instead",
        events={"shot": 2}))
    FH_LOAD = merge(combat(twist=-10.0, lean=-4.0), guard(dl=(0.02, 0.10, -0.02), dr=(0.02, 0.16, -0.04)), clav((-6.0, 0.0, 4.0)))
    FH_EXT = merge(combat(twist=4.0, lean=8.0), arm("L", (0.02, -0.74, 0.22), back=(0.3, 0.2, 1.0)),
                   arm("R", (0.02, -0.70, 0.18), back=(0.3, 0.2, 1.0)), fists(1.0), clav((14.0, 0.0, 0.0)), head(4.0))
    C.append(Clip("fire_heavy", 16, layer="upper", keys=[
        (0, combat_guard(), {}), (5, FH_LOAD, HOLD), (7, FH_EXT, {}), (9, merge(FH_EXT, combat(twist=2.0, lean=0.0),
                                                                              clav((6.0, 0.0, 0.0))), {}),
        (16, combat_guard(), {})],
        purpose="generic heavy shot: load back, both arms drive forward, the body takes the kick",
        maps_to="a heavy / charged release (fire_rate < 1/s, charge release, splash chassis)",
        events={"shot": 7}))

    def charge_key(k):
        return merge(combat(dz=-0.03, twist=-12.0 - 2 * k, lean=4.0), guard(dl=(0.02, -0.04, 0.0),
                     dr=(0.12, 0.12 + 0.02 * k, -0.24)), clav((-4.0, 0.0, 4.0 + 2 * k)), head(2.0))
    C.append(Clip("fire_charge", 24, loop=True, layer="upper", keys=[
        (0, charge_key(0), {}), (6, charge_key(1), {}), (12, charge_key(0), {}), (18, charge_key(1), {})],
        purpose="holding a charge: rear hand loaded at the hip, braced, trembling with stored power",
        maps_to="fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy)"))

    # -- hits ----------------------------------------------------------------------------------------------------------------
    HL = merge(combat(twist=-12.0, lean=-8.0), guard(dl=(0.10, 0.12, -0.02), dr=(0.02, 0.10, 0.10)),
               head(-12.0, 10.0, 6.0, neck=(6.0, 0.0, 0.0)), clav((0.0, 0.0, 6.0)))
    C.append(Clip("hit_light", 12, layer="upper", keys=[
        (0, combat_guard(), {}), (2, HL, {}), (5, merge(combat(twist=-4.0, lean=4.0), guard(dl=(0.04, 0.04, -0.04)), head(4.0)), {}),
        (12, combat_guard(), {})],
        purpose="a flinch: head snaps, the guard is knocked back, absorb, recover",
        maps_to="PlayerFlags::HIT on a light hit (damage < 10 % max HP), layered over whatever plays",
        events={"impact": 1}))
    HH1 = merge(combat(dz=0.02, lean=-18.0, twist=12.0, hip_yaw=8.0, py=0.08, fl=(0.25, -0.16), lift_l=0.12, heel_r=10.0),
                arm("L", (0.34, 0.05, 0.12), pole=(0.3, 0.6, -0.5), back=(0.7, 0.3, 0.6)),
                arm("R", (0.30, -0.08, 0.26), pole=(0.3, 0.5, -0.6), back=(0.7, 0.3, 0.6)), fists(1.0),
                head(-22.0, 12.0, 0.0), clav((-4.0, 0.0, 8.0)))
    HH2 = merge(combat(dz=-0.08, lean=0.0, twist=6.0, hip_yaw=4.0, py=0.06, fl=(0.27, 0.00)), guard(dl=(0.10, 0.10, -0.10), dr=(0.12, 0.05, -0.08)),
                head(-4.0))
    HH3 = merge(combat(dz=-0.20, lean=16.0, twist=-4.0, py=0.05, fl=(0.27, 0.00)), guard(dl=(0.04, 0.02, -0.14), dr=(0.06, 0.0, -0.12)),
                head(6.0))
    HH4 = merge(combat(dz=-0.10, lean=6.0, py=0.03, fl=(0.27, -0.14), lift_l=0.06), guard(), head(0.0))
    C.append(Clip("hit_heavy", 26, keys=[
        (0, combat_guard(), {}), (3, HH1, {}), (8, HH2, {"t": 0.8}), (13, HH3, {}), (19, HH4, {}), (22, merge(HH4, combat(dz=-0.08, lean=4.0, fl=CL)), {"t": 0.8}),
        (26, combat_guard(), {})],
        purpose="a big stagger: blown back, the lead foot steps back, absorb low, step back in",
        maps_to="PlayerFlags::HIT on a heavy hit (damage >= 10 % max HP or a stun); interrupts upper-layer clips",
        events={"impact": 1}))

    # -- knockdown / get up -----------------------------------------------------------------------------------------------
    KD1 = merge(combat(dz=0.0, lean=-24.0, twist=10.0, py=0.10, fl=(0.25, -0.15), lift_l=0.15, heel_r=25.0),
                arm("L", (0.30, -0.40, 0.16), pole=(0.5, 0.5, -0.5), back=(0.5, 0.3, 0.8)),
                arm("R", (0.26, -0.44, 0.10), pole=(0.5, 0.5, -0.5), back=(0.5, 0.3, 0.8)), fists(1.0),
                head(-26.0, 10.0, 0.0), clav((6.0, 0.0, 6.0)))
    KD2 = merge(pelvis((0.0, 0.34, -0.58), (-52.0, 6.0, 0.0)), spine(-10.0, 6.0), head(0.0, ww=0.0, neck=(12.0, 0.0, 0.0), rot=(14.0, 0.0, 0.0)),
                foot("L", (0.24, -0.42), 6.0, lift=0.40, heel=-20.0, knee=(0.0, 0.0, 1.0)),
                foot("R", (0.22, -0.05), 6.0, lift=0.14, heel=-10.0, knee=(0.0, 0.0, 1.0)),
                arm("L", (0.55, 0.05, 0.25), pole=(0.3, 0.8, -0.2), back=(0.5, 0.6, 0.6)),
                arm("R", (0.50, 0.12, 0.30), pole=(0.3, 0.8, -0.2), back=(0.5, 0.6, 0.6)), fists(1.0), clav((-4.0, 0.0, 6.0)))
    LYING = merge(pelvis((0.0, 0.42, -0.99), (-84.0, 2.0, 0.0)), spine(-4.0, 0.0), head(0.0, ww=0.0, neck=(8.0, 0.0, 0.0), rot=(6.0, 12.0, 0.0)),
                  foot("L", CL, 10.0, knee=(0.4, 0.0, 2.0)),
                  foot("R", (0.24, -0.80), 10.0, heel=-78.0, knee=(0.0, 0.0, 2.0)),
                  arm("L", (0.86, 0.55, 0.14), pole=(0.9, 0.9, 1.5), back=(0.0, 0.2, 1.0), space="abs"),
                  arm("R", (0.80, 0.70, 0.14), pole=(0.9, 0.9, 1.5), back=(0.0, 0.2, 1.0), space="abs"),
                  fists(0.7), clav((0.0, 0.0, 4.0)))
    LY_BOUNCE = merge(LYING, pelvis((0.0, 0.41, -0.95), (-80.0, 3.0, 0.0)), foot("L", (0.28, -0.30), 10.0, lift=0.10, knee=(0.4, 0.0, 2.0)),
                      foot("R", (0.24, -0.78), 10.0, heel=-60.0, lift=0.08, knee=(0.0, 0.0, 2.0)), head(0.0, ww=0.0, neck=(16.0, 0.0, 0.0), rot=(10.0, 8.0, 0.0)))
    C.append(Clip("knockdown", 30, keys=[
        (0, combat_guard(), {}), (3, KD1, {}), (9, KD2, {}), (14, LY_BOUNCE, {}), (20, LYING, {"t": 0.8}), (30, LYING, HOLD)],
        purpose="blown off the feet: impact, a backward fall, the bounce, lying on the back",
        maps_to="a knockback / launch strong enough to floor the hero (stun >= 0.8 s); holds its last frame until get_up",
        events={"impact": 1, "ground": 14}))
    GU1 = merge(pelvis((0.0, 0.40, -0.97), (-30.0, 0.0, 0.0)), spine(14.0), head(10.0, ww=0.6, neck=(4.0, 0.0, 0.0)),
                foot("L", CL, 10.0, knee=(0.4, 0.0, 2.0)), foot("R", (0.24, -0.76), 10.0, heel=-60.0, lift=0.03, knee=(0.0, 0.0, 2.0)),
                arm("L", (0.42, 0.80, 0.14), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"),
                arm("R", (0.40, 0.84, 0.14), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"), fists(1.0))
    GU2 = merge(pelvis((0.0, 0.22, -0.72), (22.0, -12.0, 0.0)), spine(18.0, 6.0), head(8.0),
                foot("L", CL, 10.0), foot("R", (0.22, 0.42), 14.0, heel=72.0),
                arm("L", (0.10, -0.50, -0.30), pole=(0.6, 0.2, -0.6), back=(0.4, 0.3, 0.8)),
                arm("R", (0.32, -0.22, 0.22), pole=(0.8, -0.2, 1.4), back=(-0.2, -0.8, 0.4), space="abs"), fists(1.0))
    GU_TUCK = merge(pelvis((0.0, 0.34, -0.90), (-6.0, -6.0, 0.0)), spine(22.0, 4.0), head(10.0),
                    foot("L", CL, 10.0, knee=(0.4, 0.0, 1.0)), foot("R", (0.22, -0.20), 12.0, lift=0.16, heel=30.0, knee=(0.0, 0.0, 1.0)),
                    arm("L", (0.38, 0.55, 0.16), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"),
                    arm("R", (0.36, 0.55, 0.16), pole=(0.9, 1.4, 1.2), back=(0.0, 0.6, 0.8), space="abs"), fists(1.0))
    GU3 = merge(pelvis((0.0, 0.12, -0.40), (26.0, -10.0, 0.0)), spine(20.0, 4.0), head(4.0),
                foot("L", CL, 10.0), foot("R", (0.22, 0.42), 18.0, heel=45.0), guard(dl=(0.06, 0.04, -0.20), dr=(0.10, 0.0, -0.22)))
    C.append(Clip("get_up", 36, keys=[
        (0, LYING, {}), (7, GU1, {}), (12, GU_TUCK, {}), (16, GU2, {"t": 0.8}), (23, GU3, {}),
        (27, merge(combat(dz=-0.12, lean=10.0, fr=(0.24, 0.24), lift_r=0.10), guard()), {}),
        (30, merge(combat(dz=-0.06, lean=4.0), guard()), {"t": 0.8}), (36, combat_guard(), {})],
        purpose="from the back: sit up on the hands, roll onto one knee, push up into the guard",
        maps_to="the knockdown's stun ends",
        events={"stand": 30}))

    # -- death / downed / revive / reforge ------------------------------------------------------------------------------
    D1 = merge(combat(dz=-0.02, lean=-16.0, twist=10.0, py=0.04), guard(dl=(0.14, 0.14, 0.0), dr=(0.10, 0.12, 0.06)),
               head(-26.0, 8.0, 0.0), clav((-4.0, 0.0, 8.0)))
    D2 = merge(combat(dz=-0.40, lean=26.0, twist=4.0), head(0.0, ww=0.3, neck=(14.0, 0.0, 0.0), rot=(12.0, 6.0, 0.0)),
               arm("L", (0.18, -0.20, -0.62), pole=(0.4, 0.5, -0.2), back=(0.7, 0.2, 0.3)),
               arm("R", (0.16, -0.16, -0.64), pole=(0.4, 0.5, -0.2), back=(0.7, 0.2, 0.3)), fists(0.8))
    KNEEL = merge(pelvis((0.0, -0.02, -0.56), (10.0, -8.0, 4.0)), spine(18.0, 0.0, 6.0), head(0.0, ww=0.0, neck=(20.0, 0.0, 0.0), rot=(16.0, 8.0, 0.0)),
                  foot("L", CL, 10.0), foot("R", CR, 22.0, heel=75.0),
                  arm("L", (0.22, -0.04, -0.66), pole=(0.4, 0.6, -0.1), back=(0.8, 0.1, 0.2)),
                  arm("R", (0.20, -0.02, -0.66), pole=(0.4, 0.6, -0.1), back=(0.8, 0.1, 0.2)), fists(0.7))
    TOPPLE = merge(pelvis((0.0, -0.16, -0.72), (48.0, 0.0, 8.0)), spine(24.0, 0.0, 8.0), head(0.0, ww=0.0, neck=(16.0, 10.0, 0.0), rot=(10.0, 14.0, 0.0)),
                   foot("L", (0.26, 0.10), 10.0, heel=70.0, lift=0.10), foot("R", (0.24, 0.40), 14.0, heel=95.0, lift=0.08),
                   arm("L", (0.46, -0.72, 0.16), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"),
                   arm("R", (0.40, -0.58, 0.20), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"), fists(0.7))
    PRONE = merge(pelvis((0.0, -0.18, -0.945), (84.0, 0.0, 3.0)), spine(4.0, 0.0, 2.0), head(0.0, ww=0.0, neck=(-12.0, 34.0, 0.0), rot=(-6.0, 20.0, 0.0)),
                  foot("L", (0.26, 0.86), 12.0, heel=112.0, lift=0.06), foot("R", (0.22, 0.90), 14.0, heel=116.0, lift=0.06),
                  arm("L", (0.62, -1.02, 0.13), pole=(1.2, -0.6, 1.4), back=(0.2, 0.2, 1.0), space="abs"),
                  arm("R", (0.50, -0.06, 0.13), pole=(1.0, 0.4, 1.4), back=(0.4, 0.0, 1.0), space="abs"), fists(0.6))
    C.append(Clip("death", 48, keys=[
        (0, combat_guard(), {}), (4, D1, {}), (12, D2, {}), (20, KNEEL, {"t": 0.5}), (25, merge(KNEEL, pelvis((0.0, -0.03, -0.58), (14.0, -8.0, 6.0))), {}),
        (31, TOPPLE, {}), (36, PRONE, {}),
        (39, merge(PRONE, pelvis((0.0, -0.18, -0.925), (82.0, 0.0, 3.0))), {}), (48, PRONE, HOLD)],
        purpose="the fatal blow: head snaps back, knees buckle to the ground, topples face down",
        maps_to="LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look)",
        events={"impact": 1, "knee": 20, "ground": 36}))

    def wraith(b, sw, arm_d):
        return merge(pelvis((0.0, 0.02, -0.26 + 0.05 * b), (24.0, 4.0 * sw, 3.0 * sw)), spine(34.0, -3.0 * sw, 4.0 * sw),
                     head(0.0, ww=0.0, neck=(14.0, 0.0, 0.0), rot=(18.0, 6.0 * sw, 0.0)),
                     foot("L", (0.16, 0.34 + 0.03 * b), 8.0, lift=0.36 + 0.05 * b, heel=100.0, knee=(0.0, -1.0, 0.0)),
                     foot("R", (0.15, 0.42 - 0.03 * b), 10.0, lift=0.30 + 0.05 * b, heel=108.0, knee=(0.0, -1.0, 0.0)),
                     arm("L", (0.24, 0.06 + 0.05 * arm_d, -0.72), pole=(0.3, 0.6, -0.1), back=(0.8, 0.1, 0.2)),
                     arm("R", (0.22, 0.10 - 0.05 * arm_d, -0.72), pole=(0.3, 0.6, -0.1), back=(0.8, 0.1, 0.2)),
                     fists(1.0), clav((8.0, 0.0, -6.0)))
    C.append(Clip("downed", 60, loop=True, keys=[
        (0, wraith(0, 0, 0), {}), (15, wraith(1, 0.6, 1), {}), (30, wraith(0.2, 0, 0), {}), (45, wraith(0.9, -0.6, -1), {})],
        purpose="the wraith drift: slumped, floating 0.35 m off the ground, limbs trailing, a slow bob",
        maps_to="LifeState::Downed (the Soul-Tether wraith; moves at 45 % speed with no gait, the client adds the ghost material)",
        grounded=False))
    RV1 = merge(pelvis((0.0, 0.0, -0.12), (-10.0, 0.0, 0.0)), spine(-16.0), head(-22.0),
                foot("L", (0.24, -0.10), 10.0, lift=0.30, heel=60.0), foot("R", (0.22, 0.20), 16.0, lift=0.26, heel=70.0),
                arm("L", (0.60, 0.10, 0.08), pole=(0.3, 0.6, -0.6), back=(0.4, 0.6, 0.7)),
                arm("R", (0.58, 0.12, 0.10), pole=(0.3, 0.6, -0.6), back=(0.4, 0.6, 0.7)), fists(1.0), clav((-8.0, 0.0, 10.0)))
    RV2 = merge(combat(dz=-0.24, lean=22.0), guard(dl=(0.08, 0.06, -0.26), dr=(0.10, 0.02, -0.26)), head(12.0))
    C.append(Clip("revive", 40, keys=[
        (0, wraith(0, 0, 0), {}), (6, RV1, {}), (12, RV2, {"t": 0.8}), (22, merge(combat(dz=-0.08, lean=6.0), guard(dl=(0.02, 0.0, -0.06))), {}),
        (30, combat_guard(), {}), (34, merge(combat(), guard(), head(0.0, 6.0, 3.0)), {}), (40, combat_guard(), {})],
        purpose="pulled back into the body: a jolt, the feet slam down, crouch, rise into the guard",
        maps_to="an ally completes the Soul-Tether revive (Downed -> Alive)",
        events={"jolt": 6, "land": 12}))
    SUPER = merge(pelvis((0.0, 0.10, -0.66), (34.0, -12.0, 0.0)), spine(20.0, 6.0), head(24.0),
                  foot("L", CL, 10.0), foot("R", (0.22, 0.48), 14.0, heel=74.0),
                  arm("R", (0.34, -0.36, 0.20), pole=(0.8, 0.2, 1.4), back=(0.0, -1.0, 0.1), space="abs"),
                  arm("L", (0.46, 0.34, -0.34), pole=(0.6, 0.6, -0.4), back=(0.6, 0.4, 0.6)), fists(1.0), clav((-4.0, 0.0, 4.0)))
    CLASH = merge(combat(dz=-0.04, lean=0.0), arm("L", (-0.07, -0.50, 0.12), pole=(0.8, 0.2, -0.5), back=(0.0, 0.2, 1.0)),
                  arm("R", (-0.07, -0.50, 0.12), pole=(0.8, 0.2, -0.5), back=(0.0, 0.2, 1.0)), fists(1.0), head(-6.0), clav((8.0, 0.0, 0.0)))
    C.append(Clip("reforge_in", 45, keys=[
        (0, SUPER, {}), (10, merge(SUPER, pelvis((0.0, 0.10, -0.68), (35.0, -12.0, 0.0))), HOLD),
        (18, merge(pelvis((0.0, 0.06, -0.34), (18.0, -8.0, 0.0)), spine(12.0, 4.0), head(4.0), foot("L", CL, 10.0),
                   foot("R", (0.22, 0.48), 14.0, heel=40.0), guard(dl=(0.10, 0.10, -0.24), dr=(0.10, 0.06, -0.26))), {}),
        (22, merge(combat(dz=-0.08, fr=(0.24, 0.26), lift_r=0.10), guard(dl=(0.0, 0.10, -0.10), dr=(0.0, 0.10, -0.10))), {}),
        (26, merge(CLASH, combat(dz=-0.04)), {"lin": True, "t": 0.6}), (28, CLASH, {}), (36, merge(combat(), guard(), head(-2.0)), {}), (45, combat_guard(), {})],
        purpose="forged anew: rises from a one-knee landing (fist planted), clashes the gauntlets, takes the guard",
        maps_to="LifeState::Reforging ends: the hero reappears next to an ally",
        events={"clash": 28}))

    # -- victory / social / world -------------------------------------------------------------------------------------------
    V_LOAD = merge(combat(dz=-0.10, lean=10.0, twist=-8.0), guard(dl=(0.12, 0.04, -0.34), dr=(0.12, 0.02, -0.34)), head(18.0))
    V_UP = merge(combat(dz=-0.01, lean=-14.0, twist=12.0), head(-26.0, 10.0),
                 arm("R", (0.10, -0.12, 0.76), pole=(0.8, 0.2, 0.4), back=(0.2, 0.9, 0.3)),
                 arm("L", (0.34, -0.18, -0.20), pole=(0.6, 0.3, -0.6), back=(0.8, 0.2, 0.5)), fists(1.0), clav((-4.0, 0.0, 10.0), (-2.0, 0.0, 16.0)))
    V_HOLD = merge(V_UP, combat(dz=-0.03, lean=-10.0, twist=10.0), arm("R", (0.08, -0.14, 0.72), pole=(0.8, 0.2, 0.4), back=(0.2, 0.9, 0.3)), head(-18.0, 8.0))
    C.append(Clip("victory", 60, keys=[
        (0, combat_guard(), {}), (10, V_LOAD, HOLD), (17, V_UP, {}), (24, V_HOLD, {}),
        (42, merge(V_HOLD, combat(dz=-0.04, lean=-9.0, twist=10.0)), {}), (60, V_HOLD, HOLD)],
        purpose="the roar: a crouch, then one gauntlet thrust to the sky, chest out; holds the pose",
        maps_to="the run is won (GameEvent victory / boss down, results screen); holds its last frame",
        events={"roar": 17}))
    PING = merge(combat(twist=14.0), guard(), arm("R", (-0.04, -0.74, 0.34), pole=(0.3, 0.3, -0.9), back=(0.0, 0.3, 1.0)),
                 {"fingers_R": 0.0}, head(-8.0, 4.0), clav((4.0, 0.0, 2.0), (10.0, 0.0, 4.0)))
    C.append(Clip("ping", 20, layer="upper", keys=[
        (0, combat_guard(), {}), (2, merge(combat(twist=6.0), guard(dr=(0.0, 0.06, 0.08))), {}), (5, PING, {}),
        (14, merge(PING, arm("R", (-0.04, -0.72, 0.36), pole=(0.3, 0.3, -0.9), back=(0.0, 0.3, 1.0))), HOLD),
        (17, merge(combat(twist=4.0), guard(dr=(0.0, 0.04, 0.06)), {"fingers_R": 1.0}), {}), (20, combat_guard(), {})],
        purpose="a ping: the right arm points along the aim with the hand open, the head follows",
        maps_to="the ping / marker input (party callout); the open gauntlet variant shows while the hand is open",
        events={"ping": 5}))
    I_REACH = merge(relaxed(dz=-0.10, lean=26.0), pelvis((0.0, -0.04, -0.12), (10.0, 0.0, 0.0)), head(26.0, neck=(4.0, 0.0, 0.0)),
                    arm("L", (0.20, -0.60, 1.10), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"),
                    arm("R", (0.20, -0.60, 1.10), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"), fists(1.0))
    I_PRESS = merge(I_REACH, relaxed(dz=-0.14, lean=30.0), pelvis((0.0, -0.06, -0.15), (12.0, 0.0, 0.0)),
                    arm("L", (0.20, -0.60, 1.05), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"),
                    arm("R", (0.20, -0.60, 1.05), pole=(1.2, 0.2, 1.4), back=(0.2, -0.9, 0.3), space="abs"), clav((6.0, 0.0, -6.0)))
    C.append(Clip("interact", 40, keys=[
        (0, idle_key(0, 0, 0), {}), (9, I_REACH, {}), (12, I_PRESS, LIN), (14, I_PRESS, HOLD), (26, I_PRESS, HOLD),
        (40, idle_key(0, 0, 0), {})],
        purpose="work the anvil: lean over and press both gauntleted fists onto it (knuckles down), then straighten",
        maps_to="the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s",
        events={"contact": 12, "release": 26}))

    def hammer(p):
        """p: 0 raised overhead, 1 strike contact."""
        return merge(pelvis((0.0, 0.05, -0.10 - 0.05 * p), (10.0 + 6.0 * p, -6.0 + 8.0 * p, 0.0)),
                     foot("L", (0.30, -0.18), 15.0), foot("R", (0.28, 0.04), 25.0),
                     spine(4.0 + 22.0 * p, -14.0 + 20.0 * p), head(14.0 + 10.0 * p), clav((0.0, 0.0, 8.0 - 8.0 * p), (0.0, 0.0, 14.0 - 16.0 * p)),
                     arm("L", (0.31, -0.56, 1.07), pole=(1.2, 0.0, 1.2), back=(0.2, -0.9, 0.3), space="abs"), fists(1.0))
    HAMMER_TOP = merge(hammer(0), arm("R", (0.06, 0.02, 0.70), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3)))
    HAMMER_DOWN = merge(hammer(0.6), arm("R", (0.00, -0.50, 0.12), pole=(0.8, 0.4, -0.4), back=(0.1, 0.4, 0.9)))
    HAMMER_HIT = merge(hammer(1.0), arm("R", (0.10, -0.60, 1.07), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"))
    HAMMER_REB = merge(hammer(0.85), arm("R", (0.10, -0.58, 1.18), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"))
    HAMMER_UP = merge(hammer(0.35), arm("R", (0.06, -0.26, 0.40), pole=(0.8, 0.4, -0.2), back=(0.2, 0.6, 0.7)))
    C.append(Clip("forge_hammer", 36, loop=True, keys=[
        (0, HAMMER_TOP, HOLD), (6, HAMMER_DOWN, LIN), (8, HAMMER_HIT, {}), (11, HAMMER_REB, {}), (20, HAMMER_UP, {}),
        (30, merge(HAMMER_TOP, arm("R", (0.07, 0.00, 0.64), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3))), {})],
        purpose="hammering the anvil with the right fist, the left fist bracing the work",
        maps_to="the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil)",
        events={"hammer_hit": 8}))
    return C
