"""Kael's stage-4 clips on GF_Hero_v1: the shared set re-posed for a ghost gunslinger, and his kit (8 clips).

Kael, The Wraithshot (content/sheets/characters.csv row kael, assets/content/kits.ron, brief.md section 8) is a lean
2.1 m MakeHuman body with nothing that limits his joints (no plate), so his shared set keeps the whole timing, foot work,
pelvis and spine of the library (s4_clips.py, Brax's numbers scaled by s4lib.Kit to his 1.106 m leg and 0.786 m arm)
and changes what his hands do. He never lets go of the serpent_smg (the weapon track's one-handed GLB on weapon_R):

  * the guard is the AIM: the right arm reaches down the aim line at shoulder height, in HERO space so the chest's
    bounce and twist never swing the muzzle; the left (ghost) hand hangs low and loose by his hip, fingers open;
  * the stance is the library's, lighter: higher (7 cm instead of 11 cm down), squarer (no lead-shoulder yaw), a little
    more chest turn toward the gun side;
  * idle, walk and run carry the gun low and forward (the muzzle down, clear of the open coat), the ghost arm swings;
  * the right hand stays curled round the grip (0.8 of the fist) in every frame; the ghost hand is loose (0.35);
  * the shared clips whose hands mean a brawler's fists are re-posed: fire_light / fire_heavy / fire_charge (a snap
    shot, a two-handed braced shot with the ghost hand under the gun, a two-handed held charge), ping (the ghost hand
    points), interact (the ghost hand pressed on the anvil), forge_hammer (the ghost fist hammers, the gun hand low),
    reforge_in (the ghost hand planted in the landing, a gun flourish instead of the gauntlet clash).

The library's clip bodies are built by s4_clips.shared_clips itself with Kael's stance / hand vocabulary in place of
Brax's (the helpers it calls by name are swapped for the call and restored after), so names, loops, layers, events
and timing stay the contract's; the re-posed clips above replace theirs by name.

Unique clips (brief.md section 8, kits.ron kael): idle_signature@loop (the gun flourish), fan_of_blades (active 1),
shadow_roll (active 2, a real forward roll), ghost_step (the passive's refreshed dash), bullet_ballet_start /
bullet_ballet@loop (ultimate: the twin-pistol stance), fire_r (the serpent_smg's rapid shot), fire_twin (the Bullet
Ballet twin shot, upper layer over bullet_ballet@loop). Conventions of s4_clips.py: left-side terms, Brax scale.
"""
import math

from mathutils import Matrix, Vector

import s4_clips
from s4_clips import CL, CR, HOLD, LIN, arm, clav, foot, head, merge, pelvis, spine
from s4lib import Clip, mirror, rot_world

KEY = "kael"
GRIP = 0.8          # the right hand's curl round the serpent_smg grip (s4lib fist amount)
LOOSE = 0.35        # the ghost hand, relaxed
_COAT = ["x_coat_%s_%02d" % (c, k) for c in ("LF", "LS", "LB", "RB", "RS", "RF") for k in range(1, 5)]
# the arm keep-out (s4_anim.build_keepout): the loin cloth and the tatters hang and swing; the coat's skirt rides its
# x_coat chains (posed by the cloth pass), so its vertices never steer an arm; the yoke, cuffs and collar do
KEEPOUT_LOOSE_PARTS = ("LOINCLOTH", "WISPS")
KEEPOUT_OWN_BONES = {"L": tuple(_COAT), "R": tuple(_COAT)}


# ---- Kael's vocabulary (the names s4_clips.shared_clips calls) ----------------------------------------------------------
def kfists(a=1.0, b=None):
    """The gun hand never opens; the ghost hand stays loose (a lying pose relaxes it further)."""
    return {"fingers_L": LOOSE * min(1.0, a), "fingers_R": GRIP}


def kcombat(dz=0.0, lean=0.0, twist=0.0, hip_yaw=0.0, heel_l=0.0, heel_r=0.0, fl=CL, fr=CR, lift_l=0.0, lift_r=0.0, py=0.0):
    """The duelist's stance: the library's foot work (left foot a half step forward), higher and squarer than Brax's."""
    return merge(pelvis((0.0, 0.02 + py, -0.07 + dz), (5.0 + lean * 0.4, 0.0 + hip_yaw, 0.0)),
                 foot("L", fl, 12.0, heel=heel_l, lift=lift_l), foot("R", fr, 18.0, heel=heel_r, lift=lift_r),
                 spine(6.0 + lean * 0.6, 8.0 + twist), head(neck=(-5.0, 0.0, 0.0)), clav((2.0, 0.0, 0.0)))


AIM_R = (-0.10, -0.82, -0.12)       # the gun fist from the rest right shoulder (left-side terms: x outward), hero space
LOW_L = (0.18, -0.16, -0.66)        # the ghost fist, low and loose by the left hip (chest space)
LOW_REACH = 0.74                    # the library's guard offsets were written for a fist by the chin: the low ghost hand
                                    # is clamped to this reach from the shoulder (Brax scale) so a dropped guard stays reachable


def aim(dl=(0.0, 0.0, 0.0), dr=(0.0, 0.0, 0.0), f=1.0):
    """The guard: the serpent_smg down the aim line at shoulder height, the back of the hand (the gun's top) up."""
    lv = Vector((LOW_L[0] + dl[0], LOW_L[1] + dl[1], LOW_L[2] + dl[2]))
    if lv.length > LOW_REACH:
        lv *= LOW_REACH / lv.length
    return merge(arm("R", (AIM_R[0] + dr[0], AIM_R[1] + dr[1], AIM_R[2] + dr[2]), pole=(0.30, 0.25, -0.90),
                     back=(0.08, 0.0, 1.0), space="hero"), {"arm_R": {"twist": 0.0}},
                 arm("L", tuple(lv), pole=(0.45, 0.55, -0.35), back=(0.75, 0.25, 0.30)),
                 kfists())


def hand_twist(side, deg):
    """An extra twist of the hand about the forearm (degrees, as s4lib applies it; the serpent_smg spins with it)."""
    return {"arm_" + side: {"twist": deg}}


def kcombat_guard(**kw):
    return merge(kcombat(**kw), aim())


def krelaxed(dz=0.0, sway=0.0, lean=0.0):
    """Relaxed: the weight drifting between the feet, upright, no hunch."""
    return merge(pelvis((sway * 0.022, 0.0, -0.010 + dz), (1.5 + lean * 0.3, 0.0, -sway * 1.4)),
                 foot("L", (0.25, -0.12), 13.0), foot("R", (0.25, -0.12), 13.0),
                 spine(1.5 + lean, sway * 1.8), head(neck=(-3.0, 0.0, 0.0)), clav((0.0, 0.0, -2.0)))


# idle arms: the gun low and forward, muzzle down, in the coat's opening; the ghost arm hanging clear of the coat
ARMS_LOW = merge(arm("R", (0.05, -0.30, -0.60), pole=(0.35, 0.45, -0.45), back=(0.70, 0.0, 0.60)),
                 arm("L", (0.24, -0.06, -0.71), pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.20)))


def kswing(amp=0.15):
    """Walk: the gun carried low and forward, the ghost arm swinging opposite the left leg."""
    def upper(p, c1):
        return merge(arm("R", (0.06, -0.30 - 0.04 * c1, -0.57), pole=(0.35, 0.40, -0.60), back=(0.70, 0.0, 0.70)),
                     arm("L", (0.24, -0.06 + amp * c1, -0.70 + 0.04 * abs(c1)), pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.20)),
                     kfists())
    return upper


def kpump(fwd=0.22, up=0.08):
    """Run: the gun forward at the waist (muzzle ahead and down), the ghost arm pumping loose and low."""
    def upper(p, c1):
        return merge(arm("R", (0.02, -0.46 - 0.05 * c1, -0.38 + 0.02 * c1), pole=(0.45, 0.35, -0.55), back=(0.45, 0.0, 0.90)),
                     arm("L", (0.14, -0.20 + fwd * c1, -0.46 - up * c1), pole=(0.50, 0.40, -0.45), back=(0.50, 0.10, 0.80)),
                     kfists(), clav((5.0 * c1, 0.0, 0.0), (-3.0 * c1, 0.0, 0.0)))
    return upper


def kbounce(amp=0.03):
    """Strafe / backpedal: the aim held, the ghost hand bobbing with the stride."""
    def upper(p, c1):
        c2 = math.cos(4 * math.pi * p)
        return aim(dl=(0.0, 0.0, amp * c2), dr=(0.0, 0.0, 0.25 * amp * c2))
    return upper


_SWAP = {"combat": kcombat, "guard": aim, "combat_guard": kcombat_guard, "relaxed": krelaxed, "ARMS_HANG": ARMS_LOW,
         "fists": kfists, "pump_arms": kpump, "swing_arms": kswing, "guard_bounce": kbounce}


# ---- the shared set ---------------------------------------------------------------------------------------------------
def _reposed(K):
    """Kael's versions of the shared clips whose hands mean a brawler's fists (same names, loops and layers), and the
    side runs and backpedal with shorter cycles: at his 7.2 m/s (Brax 6.2) the library's 20 / 18-frame strides
    over-reach his leg (IK misses of 64-78 mm), so they cycle faster at the same speed."""
    C = []
    G0 = kcombat_guard()
    v = K.move_speed / K.ls
    strafe = dict(duty=0.24, stance_half=0.15, foot_yaw=4.0, lift=0.22, lift_peak=0.40, heel_off=35.0, heel_land=0.0,
                  heel_swing=40.0, match=0.6, bob=0.035, drop=0.13, sway=0.0, pelvis_fwd=10.0, pelvis_twist=5.0,
                  spine_fwd=8.0, spine_counter=5.0, upper=kbounce(), phase0=0.30)
    C.append(Clip("strafe_left", 18, loop=True, travel=(K.move_speed, 0.0), speed=K.move_speed,
                  fn=s4_clips.locomotion(18, v, direction=(1.0, 0.0), hip_yaw=38.0, **strafe),
                  purpose="side run to the hero's left, hips opened toward the travel, chest and gun kept on the aim",
                  maps_to="moving 45-135 deg to the left of the aim; playback rate = speed / %.1f m/s" % K.move_speed))
    C.append(Clip("strafe_right", 18, loop=True, travel=(-K.move_speed, 0.0), speed=K.move_speed,
                  fn=s4_clips.locomotion(18, v, direction=(-1.0, 0.0), hip_yaw=-38.0, **strafe),
                  purpose="side run to the hero's right (the mirror of strafe_left)",
                  maps_to="moving 45-135 deg to the right of the aim; playback rate = speed / %.1f m/s" % K.move_speed))
    C.append(Clip("backpedal", 16, loop=True, travel=(0.0, K.move_speed), speed=K.move_speed,
                  fn=s4_clips.locomotion(16, v, direction=(0.0, 1.0), duty=0.30, stance_half=0.15, foot_yaw=8.0, lift=0.17,
                                         lift_peak=0.45, heel_off=8.0, heel_land=24.0, heel_swing=30.0, match=0.6, bob=0.03,
                                         drop=0.14, sway=0.015, pelvis_fwd=12.0, pelvis_twist=5.0, spine_fwd=9.0,
                                         spine_counter=5.0, upper=kbounce(0.025), phase0=0.40, base_y=-0.14),
                  purpose="backpedal on the balls of the feet, the gun on the aim, weight forward",
                  maps_to="moving more than 135 deg away from the aim; playback rate = speed / %.1f m/s" % K.move_speed))
    # death: the library's fall with the gun arm flung out to the side when he lands face down (the library's prone
    # right fist by the hip put the 0.6 m gun into his thigh)
    D1 = merge(kcombat(dz=-0.02, lean=-16.0, twist=10.0, py=0.04), aim(dl=(0.14, 0.14, 0.0), dr=(0.10, 0.12, 0.06)),
               head(-26.0, 8.0, 0.0), clav((-4.0, 0.0, 8.0)))
    D2 = merge(kcombat(dz=-0.40, lean=26.0, twist=4.0), head(0.0, ww=0.3, neck=(14.0, 0.0, 0.0), rot=(12.0, 6.0, 0.0)),
               arm("L", (0.18, -0.20, -0.62), pole=(0.4, 0.5, -0.2), back=(0.7, 0.2, 0.3)),
               arm("R", (0.16, -0.16, -0.64), pole=(0.4, 0.5, -0.2), back=(0.7, 0.2, 0.3)), kfists(0.8))
    KNEEL = merge(pelvis((0.0, -0.02, -0.56), (10.0, -8.0, 4.0)), spine(18.0, 0.0, 6.0), head(0.0, ww=0.0, neck=(20.0, 0.0, 0.0), rot=(16.0, 8.0, 0.0)),
                  foot("L", CL, 10.0), foot("R", CR, 22.0, heel=75.0),
                  arm("L", (0.22, -0.04, -0.66), pole=(0.4, 0.6, -0.1), back=(0.8, 0.1, 0.2)),
                  arm("R", (0.26, -0.02, -0.64), pole=(0.4, 0.6, -0.1), back=(0.8, 0.1, 0.2)), kfists(0.7))
    TOPPLE = merge(pelvis((0.0, -0.16, -0.72), (48.0, 0.0, 8.0)), spine(24.0, 0.0, 8.0), head(0.0, ww=0.0, neck=(16.0, 10.0, 0.0), rot=(10.0, 14.0, 0.0)),
                   foot("L", (0.26, 0.10), 10.0, heel=70.0, lift=0.10), foot("R", (0.24, 0.40), 14.0, heel=95.0, lift=0.08),
                   arm("L", (0.46, -0.72, 0.16), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"),
                   arm("R", (0.56, -0.50, 0.20), pole=(1.0, -0.4, 1.4), back=(0.3, 0.3, 0.9), space="abs"), kfists(0.7))
    PRONE = merge(pelvis((0.0, -0.18, -0.945), (84.0, 0.0, 3.0)), spine(4.0, 0.0, 2.0), head(0.0, ww=0.0, neck=(-12.0, 34.0, 0.0), rot=(-6.0, 20.0, 0.0)),
                  foot("L", (0.26, 0.86), 12.0, heel=112.0, lift=0.06), foot("R", (0.22, 0.90), 14.0, heel=116.0, lift=0.06),
                  arm("L", (0.62, -1.02, 0.13), pole=(1.2, -0.6, 1.4), back=(0.2, 0.2, 1.0), space="abs"),
                  arm("R", (0.78, -0.42, 0.13), pole=(1.2, 0.2, 1.4), back=(0.4, 0.0, 1.0), space="abs"), kfists(0.6))
    C.append(Clip("death", 48, keys=[
        (0, G0, {}), (4, D1, {}), (12, D2, {}), (20, KNEEL, {"t": 0.5}), (25, merge(KNEEL, pelvis((0.0, -0.03, -0.58), (14.0, -8.0, 6.0))), {}),
        (31, TOPPLE, {}), (36, PRONE, {}),
        (39, merge(PRONE, pelvis((0.0, -0.18, -0.925), (82.0, 0.0, 3.0))), {}), (48, PRONE, HOLD)],
        purpose="the fatal blow: head snaps back, knees buckle to the ground, topples face down, the gun arm flung out",
        maps_to="LifeState::Downed begins (GameEvent::Downed); holds its last frame, then downed@loop (wraith look)",
        events={"impact": 1, "knee": 20, "ground": 36}))
    FL_SHOT = merge(kcombat(twist=3.0), aim(dr=(0.0, -0.03, 0.01)), clav((2.0, 0.0, 0.0), (6.0, 0.0, 0.0)))
    FL_KICK = merge(kcombat(twist=-1.0, lean=-1.0), aim(dr=(0.0, 0.05, 0.07)), clav((2.0, 0.0, 0.0), (-6.0, 0.0, 4.0)), head(-2.0))
    C.append(Clip("fire_light", 8, layer="upper", keys=[(0, G0, {}), (1, FL_SHOT, LIN), (2, FL_KICK, {}), (8, G0, {})],
                  purpose="a snap shot: the gun arm locks out down the aim line, the muzzle kicks up and settles",
                  maps_to="each primary shot of a light chassis (fire_rate >= 2/s); Kael's serpent_smg plays kael_fire_r",
                  events={"shot": 1}))

    def two_hand(dr=(0.0, 0.0, 0.0), dz=0.0, lean=0.0, twist=6.0):
        """Both hands on the gun: the ghost hand cupped under the gun hand (palm up), elbows in."""
        return merge(kcombat(dz=dz, lean=lean, twist=twist), aim(dr=dr),
                     arm("L", (-0.28 + dr[0], -0.64 + dr[1], -0.13 + dr[2]), pole=(0.30, 0.20, -0.90), back=(0.10, 0.0, -1.0),
                         space="hero"), {"fingers_L": 0.5})
    FH_LOAD = merge(two_hand(dr=(0.0, 0.08, 0.04), dz=-0.02, lean=-3.0), clav((-4.0, 0.0, 2.0)))
    FH_SHOT = merge(two_hand(dr=(0.0, -0.04, 0.0), dz=-0.05, lean=8.0), clav((8.0, 0.0, 0.0)), head(3.0))
    FH_KICK = merge(two_hand(dr=(0.0, 0.10, 0.16), dz=-0.03, lean=-6.0), clav((-6.0, 0.0, 6.0)), head(-6.0))
    C.append(Clip("fire_heavy", 16, layer="upper", keys=[
        (0, G0, {}), (5, FH_LOAD, HOLD), (7, FH_SHOT, LIN), (9, FH_KICK, {}), (12, two_hand(dr=(0.0, 0.02, 0.03)), {}), (16, G0, {})],
        purpose="a braced heavy shot: the ghost hand cups the gun hand, a load, the shot, a big muzzle kick into the chest",
        maps_to="a heavy / charged release (fire_rate < 1/s, charge release, splash chassis)",
        events={"shot": 7}))

    def charge_key(k):
        return merge(two_hand(dr=(0.0, 0.02 * k, 0.01 * k), dz=-0.03, lean=3.0, twist=4.0 + 2 * k), clav((-2.0, 0.0, 2.0 + 2 * k)), head(2.0))
    C.append(Clip("fire_charge", 24, loop=True, layer="upper", keys=[
        (0, charge_key(0), {}), (6, charge_key(1), {}), (12, charge_key(0), {}), (18, charge_key(1), {})],
        purpose="holding a charge: both hands on the gun, braced, the aim trembling",
        maps_to="fire held on a Charge chassis (FireKind::Charge) until release (then fire_heavy)"))

    PING = merge(kcombat(twist=-6.0), aim(), arm("L", (-0.06, -0.72, 0.30), pole=(0.3, 0.3, -0.9), back=(0.0, 0.3, 1.0)),
                 {"fingers_L": 0.0}, head(-8.0, -4.0), clav((10.0, 0.0, 4.0), (2.0, 0.0, 0.0)))
    C.append(Clip("ping", 20, layer="upper", keys=[
        (0, G0, {}), (2, merge(kcombat(twist=-2.0), aim(dl=(0.0, -0.10, 0.20))), {}), (5, PING, {}),
        (14, merge(PING, arm("L", (-0.06, -0.70, 0.32), pole=(0.3, 0.3, -0.9), back=(0.0, 0.3, 1.0))), HOLD),
        (17, merge(kcombat(twist=4.0), aim(dl=(0.0, -0.06, 0.10))), {}), (20, G0, {})],
        purpose="a ping: the ghost hand points along the aim, open, the head follows; the gun stays on the aim",
        maps_to="the ping / marker input (party callout)",
        events={"ping": 5}))

    def idle0():
        return merge(krelaxed(), ARMS_LOW, kfists(), head(neck=(-3.0, 0.0, 0.0)))
    I_REACH = merge(krelaxed(dz=-0.08, lean=24.0), pelvis((0.0, -0.04, -0.10), (10.0, -8.0, 0.0)), head(24.0, neck=(4.0, 0.0, 0.0)),
                    arm("L", (0.10, -0.62, 1.10), pole=(1.2, 0.2, 1.4), back=(0.0, 0.1, 1.0), space="abs"),
                    arm("R", (0.10, -0.26, -0.58), pole=(0.35, 0.45, -0.45), back=(0.70, 0.0, 0.60)),
                    {"fingers_L": 0.0, "fingers_R": GRIP})
    I_PRESS = merge(I_REACH, krelaxed(dz=-0.12, lean=28.0), pelvis((0.0, -0.06, -0.13), (12.0, -8.0, 0.0)),
                    arm("L", (0.10, -0.62, 1.05), pole=(1.2, 0.2, 1.4), back=(0.0, 0.1, 1.0), space="abs"), clav((6.0, 0.0, -6.0)))
    C.append(Clip("interact", 40, keys=[
        (0, idle0(), {}), (9, I_REACH, {}), (12, I_PRESS, LIN), (14, I_PRESS, HOLD), (26, I_PRESS, HOLD), (40, idle0(), {})],
        purpose="work the anvil: lean over and press the open ghost hand flat onto it, the gun held low, then straighten",
        maps_to="the interact input at an anvil / forge / shrine POI (PoiState use); 1.3 s",
        events={"contact": 12, "release": 26}))

    def hammer(p):
        """p: 0 raised overhead, 1 strike contact. Brax's hammering mirrored: the ghost fist hammers, the gun hand low."""
        brax_side = merge(pelvis((0.0, 0.05, -0.10 - 0.05 * p), (10.0 + 6.0 * p, -6.0 + 8.0 * p, 0.0)),
                          foot("L", (0.30, -0.18), 15.0), foot("R", (0.28, 0.04), 25.0),
                          spine(4.0 + 22.0 * p, -14.0 + 20.0 * p), head(14.0 + 10.0 * p),
                          clav((0.0, 0.0, 8.0 - 8.0 * p), (0.0, 0.0, 14.0 - 16.0 * p)))
        return merge(mirror(brax_side, only_left=False),
                     arm("R", (0.12, -0.24, -0.56), pole=(0.35, 0.45, -0.45), back=(0.70, 0.0, 0.60)),
                     {"fingers_L": 1.0, "fingers_R": GRIP})
    H_TOP = merge(hammer(0), arm("L", (0.06, 0.02, 0.70), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3)))
    H_DOWN = merge(hammer(0.6), arm("L", (0.00, -0.50, 0.12), pole=(0.8, 0.4, -0.4), back=(0.1, 0.4, 0.9)))
    H_HIT = merge(hammer(1.0), arm("L", (0.10, -0.60, 1.07), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"))
    H_REB = merge(hammer(0.85), arm("L", (0.10, -0.58, 1.18), pole=(0.9, 0.3, 1.8), back=(0.2, -0.9, 0.3), space="abs"))
    H_UP = merge(hammer(0.35), arm("L", (0.06, -0.26, 0.40), pole=(0.8, 0.4, -0.2), back=(0.2, 0.6, 0.7)))
    C.append(Clip("forge_hammer", 36, loop=True, keys=[
        (0, H_TOP, HOLD), (6, H_DOWN, LIN), (8, H_HIT, {}), (11, H_REB, {}), (20, H_UP, {}),
        (30, merge(H_TOP, arm("L", (0.07, 0.00, 0.64), pole=(0.8, 0.4, 0.2), back=(0.2, 0.9, 0.3))), {})],
        purpose="hammering the anvil with the ghost fist, the gun hand held low at his side",
        maps_to="the forge / hub anvil upgrade (Forge screen open, hub idle at the anvil)",
        events={"hammer_hit": 8}))

    # reforge: Brax's one-knee landing (his foot work), the ghost fist planted by the front foot instead of the right
    # gauntlet, the gun arm out behind; then a flourish instead of the gauntlet clash
    SUPER_B = merge(pelvis((0.0, 0.10, -0.66), (34.0, -12.0, 0.0)), spine(20.0, 6.0), head(24.0),
                    foot("L", CL, 10.0), foot("R", (0.22, 0.48), 14.0, heel=74.0), clav((-4.0, 0.0, 4.0)))
    SUPER = merge(SUPER_B,
                  arm("L", (0.34, -0.36, 0.20), pole=(0.8, 0.2, 1.4), back=(0.0, -1.0, 0.1), space="abs"),
                  arm("R", (0.46, 0.34, -0.34), pole=(0.6, 0.6, -0.4), back=(0.6, 0.4, 0.6)), {"fingers_L": 1.0, "fingers_R": GRIP})
    RISE_B = merge(pelvis((0.0, 0.06, -0.34), (18.0, -8.0, 0.0)), spine(12.0, 4.0), head(4.0), foot("L", CL, 10.0),
                   foot("R", (0.22, 0.48), 14.0, heel=40.0))
    FLOURISH = merge(kcombat(dz=-0.04), arm("R", (-0.16, -0.30, 0.18), pole=(0.5, 0.3, -0.8), back=(-0.3, -0.9, 0.3)),
                     arm("L", LOW_L, pole=(0.45, 0.55, -0.35), back=(0.75, 0.25, 0.30)), kfists(), head(-4.0, -6.0), clav((0.0, 0.0, 0.0), (-4.0, 0.0, 6.0)))
    C.append(Clip("reforge_in", 45, keys=[
        (0, SUPER, {}), (10, merge(SUPER, pelvis((0.0, 0.10, -0.68), (35.0, -12.0, 0.0))), HOLD),
        (18, merge(RISE_B, aim(dl=(0.10, 0.10, -0.10), dr=(0.10, 0.20, -0.30))), {}),
        (22, merge(kcombat(dz=-0.08, fr=(0.24, 0.26), lift_r=0.10), aim(dr=(0.04, 0.12, -0.10))), {}),
        (26, merge(FLOURISH, kcombat(dz=-0.05)), {"t": 0.6}), (30, merge(FLOURISH, arm("R", (-0.16, -0.30, 0.18), pole=(0.5, 0.3, -0.8),
                                                                                  back=(-0.3, -0.9, 0.3)), hand_twist("R", -150.0)), {}),
        (36, merge(kcombat(), aim(), head(-2.0)), {}), (45, G0, {})],
        purpose="forged anew: rises from a one-knee landing (the ghost fist planted), flips the gun up past his face, aims",
        maps_to="LifeState::Reforging ends: the hero reappears next to an ally",
        events={"flourish": 28}))
    return C


def shared_clips(K):
    saved = {k: getattr(s4_clips, k) for k in _SWAP}
    try:
        for k, v in _SWAP.items():
            setattr(s4_clips, k, v)
        clips = s4_clips.shared_clips(K)
    finally:
        for k, v in saved.items():
            setattr(s4_clips, k, v)
    mine = {c.clip: c for c in _reposed(K)}
    out = []
    for c in clips:
        n = mine.get(c.clip, c)
        if n.loop != c.loop or n.layer != c.layer:
            raise SystemExit("re-posed %s changed its loop / layer" % c.clip)
        out.append(n)
    return out


# ---- the kit ------------------------------------------------------------------------------------------------------------
def roll_key(K, a, pz, py=0.0, curl=1.0):
    """The shadow roll at pelvis pitch a (deg, forward over): the pelvis head at height pz and py (m, + = back), legs
    tucked to the chest in the pelvis frame (ankles computed in hero space, knees toward the pelvis front), the spine
    curled, the head tucked (FK), the gun held across the chest, the ghost hand tucked."""
    pel = K.P("pelvis")
    loc = Vector((0.0, py, pz - pel.z))
    Rp = rot_world(a, 0.0, 0.0)
    fwd_p = Rp @ Vector((0.0, -1.0, 0.0))
    out = merge(pelvis((0.0, py / K.ls, (pz - pel.z) / K.ls), (a, 0.0, 0.0)), spine(34.0 * curl),
                head(0.0, ww=0.0, neck=(18.0 * curl, 0.0, 0.0), rot=(24.0 * curl, 0.0, 0.0)),
                arm("L", (0.00, -0.30, -0.28), pole=(0.6, 0.2, -0.6), back=(0.7, 0.1, 0.5)),
                arm("R", (0.00, -0.34, -0.24), pole=(0.6, 0.2, -0.6), back=(0.5, 0.0, 0.8)), kfists())
    for s, sx in (("L", 1.0), ("R", -1.0)):
        hip = K.P("hip_" + s)
        H = pel + loc + Rp @ (hip - pel)
        A = H + Rp @ Vector((sx * 0.08, -0.30 * curl, -0.30 - 0.05 * (1 - curl)))
        heel = a + 45.0
        Rf = Matrix.Rotation(math.radians(heel), 3, "X")
        B = A - Rf @ (K.P("ankle_" + s) - K.P("ball_" + s))
        kn = fwd_p * 2.0 - Vector((0.0, -1.0, 0.0))
        out["foot_" + s] = {"ball": (B.x / K.ls, B.y / K.ls), "lift": max(0.0, (B.z - K.P("ball_" + s).z) / K.ls),
                            "yaw": 0.0, "heel": heel, "toe": 0.0, "knee": tuple(kn)}
    return out


def plus360(pose):
    """The same pose after a full forward turn (the pelvis pitch keeps counting, so the spline never unwinds)."""
    p = dict(pose)
    r = p["pelvis"]["rot"]
    p["pelvis"] = dict(p["pelvis"], rot=(r[0] + 360.0, r[1], r[2]))
    return p


def unbent(pose):
    """Feet back on the ground's own knee rule after the roll's tucked keys (s4lib holds a field a later key leaves out)."""
    p = dict(pose)
    for s in ("L", "R"):
        if "foot_" + s in p:
            p["foot_" + s] = dict(p["foot_" + s], knee=(0.0, 0.0, 0.0), toe=0.0)
    return p


def unique_clips(K):
    C = []
    G0 = kcombat_guard()

    # -- signature idle: the gun flourish ----------------------------------------------------------------------------------
    def rel(sway=0.0, lean=0.0, hd=(0.0, 0.0, 0.0)):
        return merge(krelaxed(sway=sway, lean=lean), head(*hd, neck=(-3.0, hd[1] * 0.4, hd[2] * 0.3)))
    LOWR = dict(pole=(0.35, 0.45, -0.45), back=(0.70, 0.0, 0.60))
    HANG_L = dict(pole=(0.35, 0.45, -0.35), back=(0.55, 0.15, 0.20))
    I0 = merge(rel(), ARMS_LOW, kfists())
    UP = merge(rel(sway=-0.3, hd=(-6.0, -10.0, 0.0)), arm("R", (-0.10, -0.26, 0.16), pole=(0.5, 0.3, -0.8), back=(-0.3, -0.9, 0.3)),
               arm("L", (0.24, -0.06, -0.71), **HANG_L), kfists(), clav((0.0, 0.0, 0.0), (-4.0, 0.0, 6.0)))
    OUT = merge(rel(sway=-0.5, hd=(0.0, -20.0, 0.0)), arm("R", (0.40, -0.46, -0.02), pole=(0.3, 0.6, -0.6), back=(0.1, 0.0, 1.0)),
                arm("L", (0.24, -0.06, -0.71), **HANG_L), kfists(), clav((0.0, 0.0, 0.0), (4.0, 0.0, 2.0)))

    def flip(tw, dz=0.0):
        return merge(OUT, arm("R", (0.40, -0.46, -0.02 + dz), pole=(0.3, 0.6, -0.6), back=(0.1, 0.0, 1.0)), hand_twist("R", tw))
    GLANCE = merge(rel(sway=0.4, hd=(8.0, 12.0, 0.0)), arm("R", (0.05, -0.30, -0.60), **LOWR),
                   arm("L", (-0.02, -0.44, -0.10), pole=(0.6, 0.2, -0.7), back=(-0.1, -0.9, 0.4)), {"fingers_L": 0.0, "fingers_R": GRIP},
                   clav((6.0, 0.0, 2.0), (0.0, 0.0, 0.0)))
    GRASP = merge(GLANCE, arm("L", (-0.02, -0.44, -0.08), pole=(0.6, 0.2, -0.7), back=(-0.1, -0.9, 0.4)), {"fingers_L": 0.9})
    C.append(Clip("idle_signature", 120, loop=True, family=KEY, keys=[
        (0, I0, {}), (10, UP, {}), (18, merge(UP, head(-10.0, -6.0, 0.0)), HOLD), (26, OUT, {}),
        (29, flip(-160.0, 0.04), LIN), (32, flip(0.0, 0.06), LIN), (35, flip(-160.0, 0.04), LIN), (38, flip(0.0, 0.02), {}),
        (48, merge(UP, arm("R", (-0.08, -0.28, 0.12), pole=(0.5, 0.3, -0.8), back=(-0.3, -0.9, 0.3))), {}),
        (58, I0, {}), (70, GLANCE, {}), (78, GRASP, LIN), (82, GLANCE, {}), (86, GRASP, {}), (96, GLANCE, {}), (108, I0, {})],
        purpose="signature idle: brings the serpent_smg up past his face, spins it on his hand, lowers it, then flexes "
                "the ghost hand in front of him and watches it glow",
        maps_to="alive and idle for 6 s or more (out of combat); in the hub and the character select",
        events={"spin": 29, "grasp": 78}, render_frames=[0, 18, 29, 35, 48, 70, 86]))

    # -- Fan of Blades (active 1): the ghost hand fans across the gun, the spectral cone bursts -----------------------------
    FB_LOAD = merge(kcombat(twist=16.0, lean=-2.0), arm("R", (0.02, -0.36, -0.40), pole=(0.40, 0.40, -0.60), back=(0.45, 0.0, 0.90)),
                    arm("L", (0.30, -0.36, 0.10), pole=(0.6, 0.2, -0.6), back=(0.6, 0.3, 0.7)), {"fingers_L": 0.0, "fingers_R": GRIP},
                    clav((0.0, 0.0, 6.0), (0.0, 0.0, 0.0)), head(2.0))
    FB_FAN = merge(kcombat(twist=-18.0, lean=8.0, dz=-0.04), arm("R", (0.02, -0.40, -0.38), pole=(0.40, 0.40, -0.60), back=(0.45, 0.0, 0.90)),
                   arm("L", (-0.36, -0.46, -0.30), pole=(0.6, 0.2, -0.7), back=(0.2, -0.2, 1.0)), {"fingers_L": 0.2, "fingers_R": GRIP},
                   clav((10.0, 0.0, 0.0), (4.0, 0.0, 0.0)), head(6.0))
    FB_FOLLOW = merge(kcombat(twist=-24.0, lean=6.0, dz=-0.05), arm("R", (0.02, -0.34, -0.32), pole=(0.40, 0.40, -0.60), back=(0.45, 0.0, 0.90)),
                      arm("L", (-0.48, -0.30, -0.42), pole=(0.6, 0.3, -0.6), back=(0.3, -0.3, 0.9)), {"fingers_L": 0.35, "fingers_R": GRIP},
                      clav((12.0, 0.0, 0.0), (-4.0, 0.0, 4.0)), head(4.0))
    C.append(Clip("fan_of_blades", 30, layer="upper", family=KEY, keys=[
        (0, G0, {}), (5, FB_LOAD, HOLD), (8, FB_FAN, LIN), (11, FB_FOLLOW, {}), (18, merge(kcombat(twist=-6.0), aim(dl=(0.0, 0.0, 0.08), dr=(0.0, 0.10, -0.12))), {}),
        (30, G0, {})],
        purpose="Fan of Blades: the gun drops to the hip, the open ghost hand winds up high and fans across the gun's back; "
                "the spectral shotgun burst leaves the muzzle on the fan",
        maps_to="kits.ron kael active1 Fan of Blades (Cone 6.5 m, 70 deg, Mark) on 'burst'; upper layer, so it fires on the move",
        events={"burst": 8}))

    # -- Shadow Roll (active 2): a real forward roll -------------------------------------------------------------------------
    DIVE = merge(kcombat(dz=-0.30, lean=36.0, heel_r=40.0), arm("L", (0.06, -0.40, -0.30), pole=(0.6, 0.2, -0.6), back=(0.7, 0.1, 0.5)),
                 arm("R", (0.02, -0.40, -0.26), pole=(0.6, 0.2, -0.6), back=(0.5, 0.0, 0.8)), kfists(), head(20.0))
    LAND = plus360(unbent(merge(kcombat(dz=-0.46, lean=34.0, heel_r=60.0), aim(dl=(0.06, -0.06, 0.06), dr=(0.10, 0.28, -0.30)),
                                head(10.0))))
    RISE = plus360(unbent(merge(kcombat(dz=-0.14, lean=10.0, heel_r=20.0), aim(dr=(0.02, 0.06, -0.06)), head(2.0))))
    C.append(Clip("shadow_roll", 24, family=KEY, keys=[
        (0, G0, {}), (2, DIVE, {}), (4, roll_key(K, 80.0, 0.66, -0.06), {}), (5, roll_key(K, 140.0, 0.60, -0.04), {}),
        (6, roll_key(K, 200.0, 0.62, 0.0), {}), (7, roll_key(K, 260.0, 0.56, 0.02), {}), (8, roll_key(K, 320.0, 0.52, 0.02, 0.85), {}),
        (10, LAND, {}), (15, RISE, {}), (24, plus360(unbent(G0)), {})],
        purpose="Shadow Roll: a low dive into a tight forward roll (the coat wraps), lands crouched with the gun already "
                "coming up, rises into the aim",
        maps_to="kits.ron kael active2 Shadow Roll (Rush 5 m in 0.22 s, i-frames): the roll plays while the Rush moves "
                "(frames 2-9), then the recovery",
        events={"roll": 2, "land": 10}, grounded=False, render_frames=[0, 2, 4, 6, 8, 10, 15]))

    # -- Ghost Step (passive): the refreshed dash -------------------------------------------------------------------------
    GS1 = merge(pelvis((0.0, -0.05, -0.30), (28.0, 6.0, 0.0)), spine(14.0, 10.0), head(16.0, neck=(-10.0, 0.0, 0.0)),
                foot("L", (0.13, -0.46), 4.0, lift=0.26, heel=25.0), foot("R", (0.12, 0.58), 4.0, lift=0.24, heel=80.0),
                aim(dr=(0.0, 0.04, -0.06)), arm("L", (0.22, 0.46, -0.44), pole=(0.4, 0.6, -0.2), back=(0.7, 0.3, 0.3)),
                {"fingers_L": 0.0, "fingers_R": GRIP}, clav((0.0, 0.0, 0.0), (8.0, 0.0, 0.0)))
    GS2 = merge(GS1, pelvis((0.0, -0.06, -0.32), (30.0, 6.0, 0.0)), foot("L", (0.13, -0.50), 4.0, lift=0.22, heel=20.0),
                foot("R", (0.12, 0.62), 4.0, lift=0.26, heel=85.0), arm("L", (0.20, 0.52, -0.40), pole=(0.4, 0.6, -0.2), back=(0.7, 0.3, 0.3)))
    GS_LAND = merge(kcombat(dz=-0.12, lean=16.0, lift_r=0.08, fr=(0.22, 0.28), heel_r=40.0), aim(dl=(0.04, 0.12, 0.04)), head(6.0))
    C.append(Clip("ghost_step", 16, family=KEY, keys=[
        (0, G0, {}), (2, GS1, {}), (7, GS2, {}), (10, GS_LAND, {"t": 0.6}), (16, G0, {})],
        purpose="Ghost Step: the refreshed dash, a low gliding lean with the gun still on the aim and the ghost arm trailing "
                "behind, then a light landing back on the aim",
        maps_to="the dash Ghost Step refreshes (passive dash_refund / a kill): plays instead of dash + dash_recover",
        events={"launch": 1, "land": 10}, grounded=False))

    # -- Bullet Ballet (ultimate): the twin-pistol stance ----------------------------------------------------------------
    def twin(b=0.0, sw=0.0, dl=(0.0, 0.0, 0.0), dr=(0.0, 0.0, 0.0)):
        """Both arms raised down the aim (the left one mirrors the gun arm: the spectral twin rides weapon_L), weight on
        the balls of the feet, heels up."""
        return merge(kcombat(dz=-0.04 - 0.025 * b, lean=4.0, twist=0.0 + 3.0 * sw, heel_l=16.0, heel_r=22.0),
                     arm("R", (AIM_R[0] + 0.02 + dr[0], AIM_R[1] + 0.02 + dr[1], AIM_R[2] + 0.02 + dr[2]), pole=(0.30, 0.25, -0.90),
                         back=(0.08, 0.0, 1.0), space="hero"),
                     arm("L", (AIM_R[0] + 0.02 + dl[0], AIM_R[1] + 0.02 + dl[1], AIM_R[2] + 0.02 + dl[2]), pole=(0.30, 0.25, -0.90),
                         back=(0.08, 0.0, 1.0), space="hero"),
                     {"fingers_L": 0.7, "fingers_R": GRIP}, clav((4.0, 0.0, 2.0)), head(neck=(-4.0, 0.0, 0.0)))
    BB_CROSS = merge(kcombat(dz=-0.16, lean=18.0), arm("R", (-0.30, -0.30, -0.20), pole=(0.6, 0.2, -0.7), back=(0.4, 0.0, 0.9)),
                     arm("L", (-0.30, -0.26, -0.16), pole=(0.6, 0.2, -0.7), back=(0.4, 0.0, 0.9)), {"fingers_L": 0.7, "fingers_R": GRIP},
                     head(20.0), clav((10.0, 0.0, 0.0)))
    BB_SPREAD = merge(kcombat(dz=0.0, lean=-10.0), arm("R", (0.62, -0.06, 0.06), pole=(0.2, 0.6, -0.6), back=(0.0, 0.0, 1.0)),
                      arm("L", (0.62, -0.06, 0.06), pole=(0.2, 0.6, -0.6), back=(0.0, 0.0, 1.0)), {"fingers_L": 0.7, "fingers_R": GRIP},
                      head(-14.0), clav((-8.0, 0.0, 8.0)))
    C.append(Clip("bullet_ballet_start", 30, family=KEY, keys=[
        (0, G0, {}), (6, BB_CROSS, HOLD), (12, BB_SPREAD, {}), (16, merge(BB_SPREAD, head(-10.0)), {}),
        (22, twin(0.6, 0.0, dl=(0.0, 0.04, 0.03), dr=(0.0, 0.04, 0.03)), {}), (30, twin(), {})],
        purpose="Bullet Ballet: arms crossed low, then flung wide as the spectral twin forms in the ghost hand, both guns "
                "swing onto the aim",
        maps_to="kits.ron kael ultimate Bullet Ballet cast: the twin pistol (VFX on weapon_L) appears on 'twin'",
        events={"twin": 12}))
    C.append(Clip("bullet_ballet", 24, loop=True, family=KEY, keys=[
        (0, twin(), {}), (6, twin(1.0, 1.0), {}), (12, twin(0.0, 0.0), {}), (18, twin(1.0, -1.0), {})],
        purpose="Bullet Ballet stance: both arms up down the aim, on the balls of the feet, a quick bounce and a sway",
        maps_to="replaces idle_combat while the Bullet Ballet buff lasts (6 s); kael_fire_twin layers on top"))
    TW = twin()
    C.append(Clip("fire_twin", 10, layer="upper", family=KEY, base="bullet_ballet", keys=[
        (0, TW, {}), (1, twin(dr=(0.0, -0.03, 0.0), dl=(0.0, 0.02, 0.02)), LIN), (2, twin(dr=(0.0, 0.05, 0.07)), {}),
        (4, twin(dr=(0.0, 0.02, 0.02), dl=(0.0, -0.03, 0.0)), LIN), (5, twin(dl=(0.0, 0.05, 0.07)), {}), (10, TW, {})],
        purpose="the Bullet Ballet twin shot: the gun hand, then the spectral twin in the ghost hand, each kicks up",
        maps_to="each shot while Bullet Ballet lasts (the twin copies the Mechanism), layered over kael_bullet_ballet@loop",
        events={"shot_r": 1, "shot_l": 4}))

    # -- the serpent_smg's rapid shot -------------------------------------------------------------------------------------------
    FR_SHOT = merge(kcombat(twist=2.0), aim(dr=(0.0, -0.02, 0.0)), clav((2.0, 0.0, 0.0), (4.0, 0.0, 0.0)))
    FR_KICK = merge(kcombat(twist=0.0), aim(dr=(0.0, 0.03, 0.04)), clav((2.0, 0.0, 0.0), (-3.0, 0.0, 2.0)))
    C.append(Clip("fire_r", 6, layer="upper", family=KEY, keys=[(0, G0, {}), (1, FR_SHOT, LIN), (2, FR_KICK, {}), (6, G0, {})],
                  purpose="the serpent_smg's rapid shot: a short lock-out and a small muzzle kick, short enough for its fire rate",
                  maps_to="each primary shot of the serpent_smg (rapid); the recoil shake stays procedural",
                  events={"shot": 1}))
    return C
