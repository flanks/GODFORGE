"""Brax's unique clip set (stage 4): 10 clips on GF_Hero_v1, exported as brax_<clip>[@loop] next to the shared library.

Kit (assets/content/kits.ron, content/sheets/characters.csv row brax; brief.md section 8):
  * anvil_gauntlets (Fist, 3.0 strikes/s): the chassis' "fire" is a punch. brax_jab_l / brax_jab_r alternate (10 frames
    each, so a 3/s string never waits on a clip) and brax_hook is the heavy third strike / the Heat-max strike. They are
    upper-layer clips: spine_01 and its children layer over locomotion, the first and last frame are the idle_combat
    reference pose, and hit-stop, shake and recoil stay procedural (ARCHITECTURE section 9).
  * Cinder Uppercut (active 1): Nova (launch, stun 0.8, knockback 3) then Field (flame geysers). One clip: the launch
    uppercut, a hang, the double-fist slam that spawns the geysers (events "launch" and "slam").
  * Furnace Rush (active 2): Rush 8 m in 0.4 s with drag. brax_furnace_rush@loop plays while the rush moves (12 frames =
    0.4 s), brax_furnace_rush_end brakes and shoves the dragged line away (event "release").
  * Meltdown (ultimate): 8 s of molten fists. brax_meltdown_start (the ignition roar and the gauntlet clash), then
    brax_meltdown@loop replaces idle_combat while the buff lasts.
  * Heat Gauge (passive): brax_heat_vent when the gauge hits max (the body vents; the emissive VFX ride on chest_sigil).
  * brax_idle_signature@loop: the long idle variant (shoulder rolls, neck crack, gauntlet knocks).
Numbers use the helpers and conventions of s4_clips.py (left-side terms, Brax scale).
"""
from s4_clips import (ARMS_HANG, CL, CR, HOLD, LIN, arm, clav, combat, combat_guard, fists, foot, guard, head,
                      locomotion, merge, pelvis, relaxed, spine)
from s4lib import Clip


def unique_clips(K):
    C = []

    # -- signature idle ----------------------------------------------------------------------------------------------------
    def sig(r=(0.0, 0.0, -3.0), l=(0.0, 0.0, -3.0), hd=(0.0, 0.0, 0.0), lean=0.0, sway=0.0, fists_in=None):
        base = merge(relaxed(sway=sway, lean=lean), ARMS_HANG, fists(1.0), head(*hd, neck=(-4.0, hd[1] * 0.4, hd[2] * 0.3)),
                     clav(l, r))
        if fists_in is not None:
            gap = fists_in
            base = merge(base, arm("L", (-0.07 + gap, -0.44, -0.34), pole=(0.9, 0.2, -0.3), back=(0.0, 0.0, 1.0)),
                         arm("R", (-0.07 + gap, -0.44, -0.34), pole=(0.9, 0.2, -0.3), back=(0.0, 0.0, 1.0)))
        return base
    C.append(Clip("idle_signature", 120, loop=True, family="brax", keys=[
        (0, sig(), {}),
        (10, sig(r=(10.0, 0.0, 3.0), hd=(0.0, -6.0, 0.0), sway=-0.4), {}),
        (18, sig(r=(4.0, 0.0, 14.0), hd=(-4.0, -8.0, 4.0), sway=-0.6), {}),
        (26, sig(r=(-10.0, 0.0, 8.0), hd=(-2.0, -6.0, 2.0), sway=-0.5), {}),
        (34, sig(r=(0.0, 0.0, -4.0), l=(10.0, 0.0, 3.0), hd=(0.0, 4.0, 0.0), sway=0.2), {}),
        (42, sig(l=(4.0, 0.0, 14.0), hd=(-4.0, 8.0, -4.0), sway=0.6), {}),
        (50, sig(l=(-10.0, 0.0, 8.0), hd=(-2.0, 6.0, -2.0), sway=0.5), {}),
        (58, sig(hd=(4.0, 0.0, -14.0)), {}),
        (66, sig(hd=(-10.0, 0.0, 0.0), lean=-2.0), {}),
        (74, sig(hd=(4.0, 0.0, 14.0)), {}),
        (82, sig(hd=(10.0, 0.0, 0.0), lean=4.0, fists_in=0.10), {}),
        (86, sig(hd=(12.0, 0.0, 0.0), lean=5.0, fists_in=0.0), LIN),
        (88, sig(hd=(12.0, 0.0, 0.0), lean=5.0, fists_in=0.05), {}),
        (92, sig(hd=(12.0, 0.0, 0.0), lean=5.0, fists_in=0.0), LIN),
        (94, sig(hd=(10.0, 0.0, 0.0), lean=5.0, fists_in=0.06), {}),
        (106, sig(r=(-3.0, 0.0, -6.0), l=(-3.0, 0.0, -6.0), hd=(-3.0, 0.0, 0.0), lean=-2.0), {})],
        purpose="signature idle: rolls each shoulder, cracks the neck side to side, knocks the gauntlets together twice",
        maps_to="alive and idle for 6 s or more (out of combat); in the hub and the character select",
        events={"knock_1": 86, "knock_2": 92}))

    # -- strikes (upper layer) ---------------------------------------------------------------------------------------------
    JL_EXT = merge(combat(twist=-14.0, lean=4.0, heel_r=10.0), guard(dr=(0.0, 0.06, 0.04)),
                   arm("L", (0.16, -0.74, 0.22), pole=(0.5, 0.3, -0.8), back=(0.25, 0.1, 1.0)), clav((14.0, 0.0, 0.0), (4.0, 0.0, 2.0)),
                   head(4.0, -4.0))
    C.append(Clip("jab_l", 10, layer="upper", family="brax", keys=[
        (0, combat_guard(), {}), (1, merge(combat(twist=4.0), guard(dl=(0.02, 0.05, -0.02))), LIN), (3, JL_EXT, {}),
        (4, merge(JL_EXT, arm("L", (0.15, -0.70, 0.21), pole=(0.5, 0.3, -0.8), back=(0.25, 0.1, 1.0))), {}),
        (10, combat_guard(), {})],
        purpose="lead jab: the left gauntlet snaps straight down the aim line and back",
        maps_to="anvil_gauntlets strike (fire_rate 3/s), alternating with jab_r; the strike lands on frame 3",
        events={"hit": 3}))
    JR_EXT = merge(combat(twist=20.0, lean=6.0, hip_yaw=12.0, heel_r=32.0), guard(dl=(0.02, 0.12, 0.04)),
                   arm("R", (0.14, -0.76, 0.24), pole=(0.5, 0.3, -0.8), back=(0.25, 0.1, 1.0)), clav((2.0, 0.0, 2.0), (16.0, 0.0, 0.0)),
                   head(4.0, 6.0))
    C.append(Clip("jab_r", 10, layer="upper", family="brax", keys=[
        (0, combat_guard(), {}), (1, merge(combat(twist=-6.0), guard(dr=(0.02, 0.06, -0.04))), LIN), (3, JR_EXT, {}),
        (4, merge(JR_EXT, arm("R", (0.13, -0.72, 0.23), pole=(0.5, 0.3, -0.8), back=(0.25, 0.1, 1.0))), {}),
        (10, combat_guard(), {})],
        purpose="rear straight: hips and the rear heel turn, the right gauntlet drives down the aim line",
        maps_to="anvil_gauntlets strike (fire_rate 3/s), alternating with jab_l; the strike lands on frame 3",
        events={"hit": 3}))
    HK_LOAD = merge(combat(twist=14.0, hip_yaw=6.0, lean=4.0), guard(dr=(0.0, 0.04, 0.04)),
                    arm("L", (0.26, -0.34, 0.10), pole=(0.8, 0.3, 0.0), back=(0.5, 0.3, 0.8)), clav((-6.0, 0.0, 4.0), (4.0, 0.0, 2.0)), head(6.0))
    HK_HIT = merge(combat(twist=-30.0, hip_yaw=-14.0, lean=6.0, heel_l=18.0), guard(dr=(0.08, 0.14, 0.04)),
                   arm("L", (-0.22, -0.52, 0.16), pole=(0.9, -0.1, 0.35), back=(0.2, 0.2, 1.0)), clav((12.0, 0.0, 6.0), (0.0, 0.0, 2.0)),
                   head(6.0, -8.0))
    HK_FOLLOW = merge(combat(twist=-38.0, hip_yaw=-16.0, lean=8.0, heel_l=20.0), guard(dr=(0.10, 0.16, 0.04)),
                      arm("L", (-0.28, -0.42, 0.12), pole=(0.9, -0.2, 0.3), back=(0.2, 0.2, 1.0)), clav((14.0, 0.0, 4.0), (0.0, 0.0, 2.0)),
                      head(6.0, -10.0))
    C.append(Clip("hook", 16, layer="upper", family="brax", keys=[
        (0, combat_guard(), {}), (3, HK_LOAD, HOLD), (6, HK_HIT, LIN), (8, HK_FOLLOW, {}), (16, combat_guard(), {})],
        purpose="lead hook: load to the left, the torso whips through, the left gauntlet sweeps across at head height",
        maps_to="every third strike of a held string, and every strike at max Heat (ignite + stagger); lands on frame 6",
        events={"hit": 6}))

    # -- Cinder Uppercut ------------------------------------------------------------------------------------------------------
    UC_LOAD = merge(combat(dz=-0.22, lean=16.0, twist=-16.0, hip_yaw=-10.0), guard(),
                    arm("R", (0.04, -0.34, -0.60), pole=(0.6, 0.4, -0.5), back=(0.5, -0.4, 0.7)), head(10.0), clav((0.0, 0.0, 2.0), (6.0, 0.0, -4.0)))
    UC_RISE = merge(combat(dz=0.0, lean=-6.0, twist=16.0, hip_yaw=8.0, heel_l=25.0, heel_r=40.0), guard(dl=(0.04, 0.08, -0.06)),
                    arm("R", (-0.06, -0.42, 0.38), pole=(0.6, 0.3, -0.7), back=(0.2, 0.8, 0.4)), head(-10.0, 4.0))
    UC_TOP = merge(combat(dz=0.04, lean=-12.0, twist=18.0, hip_yaw=10.0, heel_l=35.0, heel_r=45.0),
                   arm("L", (0.14, -0.20, -0.30), pole=(0.6, 0.4, -0.5), back=(0.6, 0.2, 0.7)),
                   arm("R", (-0.04, -0.26, 0.72), pole=(0.8, 0.2, -0.2), back=(0.2, 0.9, 0.3)), fists(1.0),
                   head(-22.0, 6.0), clav((-4.0, 0.0, 4.0), (-4.0, 0.0, 16.0)))
    UC_HANG = merge(UC_TOP, combat(dz=0.03, lean=-10.0, twist=16.0, hip_yaw=8.0, heel_l=30.0, heel_r=40.0), head(-18.0, 4.0))
    UC_WIND = merge(combat(dz=0.02, lean=-18.0, twist=0.0, heel_l=10.0, heel_r=14.0),
                    arm("L", (-0.05, -0.10, 0.70), pole=(0.8, 0.3, 0.0), back=(0.0, 0.9, 0.3)),
                    arm("R", (-0.05, -0.10, 0.70), pole=(0.8, 0.3, 0.0), back=(0.0, 0.9, 0.3)), fists(1.0),
                    head(-20.0), clav((-8.0, 0.0, 16.0)))
    UC_SLAM = merge(combat(dz=-0.50, lean=44.0, twist=0.0),
                    arm("L", (0.22, -0.62, 0.24), pole=(1.0, 0.0, 1.2), back=(0.1, -0.9, 0.4), space="abs"),
                    arm("R", (0.22, -0.62, 0.24), pole=(1.0, 0.0, 1.2), back=(0.1, -0.9, 0.4), space="abs"), fists(1.0),
                    head(20.0), clav((10.0, 0.0, 0.0)))
    UC_REB = merge(UC_SLAM, combat(dz=-0.46, lean=40.0),
                   arm("L", (0.22, -0.60, 0.32), pole=(1.0, 0.0, 1.2), back=(0.1, -0.9, 0.4), space="abs"),
                   arm("R", (0.22, -0.60, 0.32), pole=(1.0, 0.0, 1.2), back=(0.1, -0.9, 0.4), space="abs"))
    C.append(Clip("uppercut", 48, family="brax", keys=[
        (0, combat_guard(), {}), (5, UC_LOAD, HOLD), (8, UC_RISE, LIN), (10, UC_TOP, {}), (15, UC_HANG, {}),
        (21, UC_WIND, HOLD), (25, UC_SLAM, {"lin_in": True}), (30, UC_REB, {}),
        (38, merge(combat(dz=-0.10, lean=10.0), guard(dl=(0.04, 0.0, -0.12), dr=(0.04, 0.0, -0.12))), {}), (48, combat_guard(), {})],
        purpose="Cinder Uppercut: coil low, a rising uppercut that launches, a hang, a double-fist slam into the ground",
        maps_to="kits.ron brax active1 Cinder Uppercut: Nova (launch) on 'launch', Field (flame geysers) on 'slam'",
        events={"launch": 10, "slam": 25}))

    # -- Furnace Rush -----------------------------------------------------------------------------------------------------------
    def ram(p, c1):
        return merge(arm("L", (-0.02, -0.60 + 0.03 * c1, 0.02), pole=(0.6, 0.3, -0.6), back=(0.3, 0.2, 1.0)),
                     arm("R", (-0.02, -0.58 - 0.03 * c1, 0.00), pole=(0.6, 0.3, -0.6), back=(0.3, 0.2, 1.0)), fists(1.0),
                     head(10.0), clav((10.0, 0.0, 0.0)))
    rush_fn = locomotion(12, 8.0, duty=0.30, stance_half=0.14, lift=0.26, lift_peak=0.38, heel_off=40.0, heel_land=6.0,
                         heel_swing=55.0, shift=-0.10, match=0.6, bob=0.03, drop=0.17, sway=0.02, pelvis_fwd=24.0,
                         pelvis_twist=6.0, spine_fwd=18.0, spine_counter=4.0, upper=ram, phase0=0.30)
    C.append(Clip("furnace_rush", 12, loop=True, fn=rush_fn, family="brax", travel=(0.0, -20.0), speed=20.0, slide_exempt=True,
                  purpose="Furnace Rush: head down behind both gauntlets like a ram, legs churning, very low",
                  maps_to="kits.ron brax active2 Furnace Rush while the Rush moves (8 m in 0.4 s = 12 frames); the enemy drag is sim-side",
                  notes="stylised: the rush moves at 20 m/s, the legs churn at an 8 m/s stride (a skid-charge), so the feet slide by design"))
    R0 = rush_fn(0)
    RE_PLANT = merge(combat(dz=-0.20, lean=24.0, fr=(0.25, 0.30), heel_r=40.0),
                     arm("L", (-0.02, -0.58, 0.04), back=(0.3, 0.2, 1.0)), arm("R", (-0.02, -0.56, 0.02), back=(0.3, 0.2, 1.0)),
                     fists(1.0), head(8.0), clav((8.0, 0.0, 0.0)))
    RE_SHOVE = merge(combat(dz=-0.12, lean=10.0, fr=(0.25, 0.30), heel_r=50.0),
                     arm("L", (-0.01, -0.78, 0.18), pole=(0.6, 0.3, -0.8), back=(0.3, 0.2, 1.0)),
                     arm("R", (-0.01, -0.76, 0.16), pole=(0.6, 0.3, -0.8), back=(0.3, 0.2, 1.0)), fists(1.0), head(0.0), clav((16.0, 0.0, 0.0)))
    HOP = merge(RE_PLANT, foot("L", (0.27, -0.34), 10.0, lift=0.06, heel=10.0), foot("R", (0.25, 0.36), 22.0, lift=0.08, heel=30.0))
    C.append(Clip("furnace_rush_end", 18, family="brax", keys=[
        (0, R0, {}), (2, HOP, {}), (3, RE_PLANT, {"t": 0.5}), (5, RE_SHOVE, {}), (9, merge(RE_SHOVE, combat(dz=-0.08, lean=4.0, fr=(0.25, 0.30), heel_r=30.0),
                                                                         guard(dl=(0.0, -0.10, 0.0), dr=(0.0, -0.10, 0.0))), {}),
        (12, merge(combat(dz=-0.06, fr=(0.25, 0.20), lift_r=0.08), guard()), {}), (15, merge(combat(dz=-0.02), guard()), {"t": 0.8}),
        (18, combat_guard(), {})],
        purpose="the brake: the lead foot plants in a skid, both gauntlets shove the dragged line away, back to the guard",
        maps_to="Furnace Rush ends (after 0.4 s): the drag releases on 'release'",
        events={"plant": 3, "release": 5}))

    # -- Meltdown -----------------------------------------------------------------------------------------------------------
    def melt(b, sh):
        return merge(combat(dz=-0.16 - 0.03 * b, lean=14.0 + 3.0 * b), guard(dl=(0.0, -0.06, 0.04 - 0.02 * b), dr=(0.0, -0.04, 0.06 - 0.02 * b)),
                     clav((4.0 + 5.0 * sh, 0.0, 2.0 + 2.0 * b), (4.0 - 5.0 * sh, 0.0, 2.0 + 2.0 * b)), head(2.0 * b, neck=(-10.0, 0.0, 0.0)))
    M_GATHER = merge(combat(dz=-0.16, lean=24.0), arm("L", (-0.04, -0.44, -0.42), pole=(0.7, 0.3, -0.4), back=(0.4, -0.3, 0.8)),
                     arm("R", (-0.04, -0.44, -0.42), pole=(0.7, 0.3, -0.4), back=(0.4, -0.3, 0.8)), fists(1.0), head(26.0), clav((10.0, 0.0, -4.0)))
    M_ROAR = merge(combat(dz=0.0, lean=-16.0), arm("L", (0.56, -0.10, -0.36), pole=(0.4, 0.6, -0.6), back=(0.7, 0.3, 0.6)),
                   arm("R", (0.56, -0.10, -0.36), pole=(0.4, 0.6, -0.6), back=(0.7, 0.3, 0.6)), fists(1.0), head(-24.0),
                   clav((-12.0, 0.0, 12.0)))
    M_ROAR2 = merge(M_ROAR, combat(dz=-0.02, lean=-18.0), arm("L", (0.58, -0.08, -0.34), pole=(0.4, 0.6, -0.6), back=(0.7, 0.3, 0.6)),
                    arm("R", (0.58, -0.08, -0.34), pole=(0.4, 0.6, -0.6), back=(0.7, 0.3, 0.6)), head(-28.0))
    M_CLASH = merge(combat(dz=-0.10, lean=8.0), arm("L", (-0.07, -0.50, 0.12), pole=(0.8, 0.2, -0.5), back=(0.0, 0.2, 1.0)),
                    arm("R", (-0.07, -0.50, 0.12), pole=(0.8, 0.2, -0.5), back=(0.0, 0.2, 1.0)), fists(1.0), head(-4.0), clav((10.0, 0.0, 0.0)))
    C.append(Clip("meltdown_start", 40, family="brax", keys=[
        (0, combat_guard(), {}), (6, M_GATHER, HOLD), (13, M_ROAR, {}), (21, M_ROAR2, HOLD), (25, merge(M_CLASH, arm("L", (0.0, -0.46, 0.16), back=(0.1, 0.3, 1.0)),
                                                                                                 arm("R", (0.0, -0.46, 0.16), back=(0.1, 0.3, 1.0))), LIN),
        (27, M_CLASH, {}), (33, merge(melt(1, 0), head(0.0)), {}), (40, melt(0, 0), {})],
        purpose="Meltdown ignition: gather low, a chest-out roar with the arms flung wide, the gauntlets slam together",
        maps_to="kits.ron brax ultimate Meltdown cast: the buff starts on 'ignite', the clash is the shockwave VFX cue",
        events={"ignite": 13, "clash": 27}))
    C.append(Clip("meltdown", 24, loop=True, family="brax", keys=[
        (0, melt(0, 0), {}), (6, melt(1, 1), {}), (12, melt(0, 0), {}), (18, melt(1, -1), {})],
        purpose="Meltdown stance: lower and wider, fists forward, a fast bounce and rolling shoulders",
        maps_to="replaces idle_combat while the Meltdown buff lasts (8 s); strikes layer on top as usual"))

    # -- Heat vent ----------------------------------------------------------------------------------------------------------------
    VENT = merge(combat(lean=-14.0), arm("L", (0.40, 0.08, -0.56), pole=(0.3, 0.6, -0.5), back=(0.8, 0.2, 0.4)),
                 arm("R", (0.40, 0.08, -0.56), pole=(0.3, 0.6, -0.5), back=(0.8, 0.2, 0.4)), fists(1.0), head(-22.0),
                 clav((-14.0, 0.0, 12.0)))
    C.append(Clip("heat_vent", 30, layer="upper", family="brax", keys=[
        (0, combat_guard(), {}), (6, VENT, {}), (14, merge(VENT, head(-26.0), clav((-16.0, 0.0, 14.0))), HOLD),
        (22, merge(combat(lean=2.0), guard(dl=(0.06, 0.08, -0.12), dr=(0.06, 0.08, -0.12)), clav((6.0, 0.0, 0.0))), {}),
        (30, combat_guard(), {})],
        purpose="Heat vent: shoulders thrown back, arms dropped wide, chest out, head back as the cracks vent",
        maps_to="the Heat Gauge passive reaches max (attacks start to ignite); the steam / ember VFX sit on chest_sigil",
        events={"vent": 6}))
    return C
