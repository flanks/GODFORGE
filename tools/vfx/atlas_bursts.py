"""Baked element bursts: the layered burst of VFX_STYLE section 11 (and the faction deaths of 15.3) as
one 16-frame billboard flipbook per element. 256 px cells, 4 x 4 frames row-major, 1024 x 1024.

The frames are painted at front-loaded 60 fps times (T16) and play at a constant 24 fps, so the
flipbook is fast in, slow out: frame 0 is the impact frame (f0-1), frames 1-7 the blast peak and
collapse (f1.5-12.5), frames 8-15 the dissipation (f15-40). The gameplay radius R sits at
radius_in_cell = 0.55 of the half cell; smoke may reach 1.2 R and lifts above the cell centre.

The engine uses these for bursts that do not need the full layered recipe: enemy bombers and
wisps, allies' explosions, the Reduced tier, and as the blast layer of the full recipe.
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, ease_in, ease_out, kite, norm, pmap, rot,
                    streak_poly, tapered_path)

T16 = [0, 1.5, 3, 4.5, 6, 8, 10, 12.5, 15, 18, 21, 24.5, 28, 32, 36, 40]
SIZE = 256
RIC = 0.55  # radius_in_cell
ELEMENTS = ["kinetic", "flame", "storm", "void", "plague", "radiant", "unmade", "godworks"]
RAMP_OF = {"kinetic": "kinetic", "flame": "flame", "storm": "storm", "void": "void", "plague": "plague",
           "radiant": "radiant", "unmade": "unmade", "godworks": "godworks_gold"}


def frame_cell(seed, f):
    c = Cell(SIZE, SIZE, seed=seed * 17 + int(f * 4))
    C = (SIZE / 2, SIZE * 0.56)
    R = SIZE / 2 * RIC
    return c, C, R


# ---- shared layers -------------------------------------------------------------------------------
def impact_frame(c, C, R, lay, n=7, white_scale=1.15, speed=True, angular=False):
    sp = P.spikes_even(lay, n, R * white_scale, hw_frac=0.3 if angular else 0.38, short=0.58)
    ink = [(a + 0.12, ln * 1.34, h * 1.25) for a, ln, h in sp]
    m, _ = c.star(C, ink, R * 0.34, p=1.3, skew=0.3)
    c.paint(c.ragged(m, 1.0, 0.4), V_INK, order=0.3)
    P.banded_star(c, C, sp, R * (0.22 if angular else 0.3), white=True, skew=0.0 if angular else 0.35)
    if speed:
        P.speed_lines(c, C, np.random.default_rng(7), 14, R * 1.35, R * 1.78, 3.2, V_LIGHT, order=0.25)
    return sp


def blast(c, C, R, sp, f, f_end=14.0, ink=True, skew=0.35, hot0=0.6, light0=0.76):
    """The banded star at R: the hot core fades to light by f8, the star shrinks to nothing by f_end."""
    if f >= f_end:
        return
    k = (f - 2) / (f_end - 2)
    s = 1 - max(0.0, k) ** 1.4 * 0.92
    twist = 0.06 + 0.02 * f
    spk = [(a + 0.02 * f, ln * s, h * (1.05 - 0.25 * max(0, k))) for a, ln, h in sp]
    if ink:
        ik = [(a + 0.11, ln * 1.32, h * 1.22) for a, ln, h in spk]
        mi, _ = c.star(C, ik, R * 0.36 * s, p=1.3, skew=skew, twist=twist)
        if f > 6:
            mi &= c.nz(c.X * 0.15, c.Y * 0.15) > (f - 6) / (f_end - 6) * 0.8
        c.paint(c.ragged(mi, 1.0, 0.4), V_INK, order=0.3)
    hot = float(np.interp(f, [1.5, 4, 8], [hot0, hot0 * 0.6, 0.0]))
    light = float(np.interp(f, [1.5, 8, f_end], [light0, 0.6, 0.35]))
    P.banded_star(c, C, spk, R * 0.34 * s, hot=hot, light=light, rim=0.84, twist=twist, skew=skew,
                  dry=0.12 + 0.02 * max(0, f - 2), order=0.6)


def crown(c, C, R, lay, f, front, n=7, light_core=True, cool=(10, 22), v_hi=V_LIGHT, lift=0.6, spread=0.3,
          start=2.0, size=0.26, r0=0.72, front_from=6.0):
    """Smoke crown: n puffs round the core, lit from the core, lifting and cooling. front selects the
    lower half (drawn over the blast) or the upper half (drawn under it)."""
    if f < start:
        return
    prog = ease_out(min(1.0, (f - start) / 12.0), 2.2)
    lifted = ease_in(max(0.0, (f - 10) / 30.0), 1.3)
    shrink = float(np.interp(f, [start, 12, 24, 40], [0.45, 1.0, 1.0, 0.72]))
    lobes = []
    rng = np.random.default_rng(int(lay.integers(1 << 30)))
    for i in range(n):
        a = i * math.tau / n + rng.uniform(-0.3, 0.3)
        rr = R * (r0 + spread * prog) * rng.uniform(0.85, 1.1)
        x = C[0] + math.cos(a) * rr
        y = C[1] + math.sin(a) * rr * 0.7 - R * lift * lifted * rng.uniform(0.8, 1.2)
        pr = R * size * (1 + 0.5 * prog) * shrink * rng.uniform(0.85, 1.2)
        is_front = math.sin(a) > 0
        if is_front != front or (front and f < front_from):
            continue
        for j in range(3):
            b = rng.uniform(0, math.tau)
            lobes.append((x + math.cos(b) * pr * 0.45, y + math.sin(b) * pr * 0.35, pr * rng.uniform(0.6, 0.85)))
    if not lobes:
        return
    lobes.sort(key=lambda l: -l[1])
    v_rim = V_LIGHT if f < cool[0] else (V_BODY if f < cool[1] else V_DEEP)
    if v_hi != V_LIGHT and f < cool[0]:
        v_rim = v_hi
    v_mid = V_DEEP if f < cool[1] + 8 else V_INK
    lp = C if (light_core and f < 16) else None
    P.puff_cluster(c, lobes, light=(0, -1), light_pt=lp, rim=0.24, mid=0.62, v_rim=v_rim, v_mid=v_mid, rough=0.24,
                   order0=0.1, order1=0.45)
    if f > 22:
        din = c.inside_dist(c.cov)
        n_ = c.nz(c.X * 0.13, c.Y * 0.13)
        thr = float(np.interp(f, [22, 40], [1.2, 0.72]))
        c.erase(c.cov & (n_ + (1 - np.clip(din / (R * 0.25), 0, 1)) * 0.3 > thr) & (c.order < 0.5))


def shards(c, C, R, lay, f, n=7, size=0.2, v_body=V_INK, v_edge=V_LIGHT, speed=1.35, up=0.9, grav=1.3, start=2.0,
           end=40.0, ksize=None):
    if f < start or f > end:
        return
    rng = np.random.default_rng(int(lay.integers(1 << 30)))
    tt = (f - start) / 40.0
    bodies, facets = [], []
    for i in range(n):
        a = -math.pi / 2 + rng.uniform(-1.6, 1.6) * up + (0 if up > 0 else rng.uniform(0, math.tau))
        v = R * speed * rng.uniform(0.7, 1.2)
        drag = (1 - math.exp(-tt * 5)) / 5 * 40 / 40
        x = C[0] + math.cos(a) * v * drag * 5
        y = C[1] + math.sin(a) * v * drag * 5 + R * grav * tt * tt * 4
        spin = rng.uniform(-1, 1) * 8 * tt
        L = R * size * rng.uniform(0.7, 1.3) * float(np.interp(f, [start, 24, end], [1.0, 0.9, 0.35]))
        d = rot((math.cos(a), math.sin(a)), spin)
        k, fa = P.shard_polys((x, y), d, L, L * rng.uniform(0.28, 0.4))
        bodies.append(k)
        facets.append(fa)
    m = c.polys(bodies)
    c.paint(c.sdf(m) > -1.3, V_INK, order=0.2)
    c.paint(m, v_body, order=0.25)
    c.paint(c.polys(facets) & m, v_edge, order=0.35)


def sparks(c, C, R, lay, f, n=9, end=20.0, width=6.0, reach=1.5, grav=0.8, v_head=V_HOT, v_body=V_LIGHT, start=2.0,
           up=0.0):
    if f < start or f > end:
        return
    rng = np.random.default_rng(int(lay.integers(1 << 30)))
    k = (f - start) / (end - start)
    heads, bodies = [], []
    for i in range(n):
        a = rng.uniform(0, math.tau) if up == 0 else -math.pi / 2 + rng.uniform(-up, up)
        sp = rng.uniform(0.6, 1.0)
        r1 = R * reach * sp * (1 - math.exp(-(f - start) / 4.0))
        vel = math.exp(-(f - start) / 4.0)
        ln = R * 0.5 * sp * vel + R * 0.06
        g = R * grav * k * k
        p1 = (C[0] + math.cos(a) * r1, C[1] + math.sin(a) * r1 + g)
        p0 = (C[0] + math.cos(a) * max(0, r1 - ln), C[1] + math.sin(a) * max(0, r1 - ln) + g * 0.8)
        w = width * rng.uniform(0.7, 1.2) * (1 - 0.6 * k)
        bodies.append(streak_poly(p1, p0, w, 0))
        heads.append(streak_poly(p1, (p1[0] * 0.55 + p0[0] * 0.45, p1[1] * 0.55 + p0[1] * 0.45), w * 0.6, 0))
    c.paint(c.polys(bodies), v_body if k < 0.6 else V_BODY, order=0.4)
    c.paint(c.polys(heads), v_head if k < 0.5 else V_LIGHT, order=0.5)


def motes_up(c, C, R, lay, f, n=8, kind="ember", start=4.0, end=40.0, rise=1.3, size=5.0):
    if f < start or f > end:
        return
    rng = np.random.default_rng(int(lay.integers(1 << 30)))
    tt = (f - start) / (end - start)
    polys, hots, bodies = [], [], []
    for i in range(n):
        x0 = C[0] + rng.uniform(-0.9, 0.9) * R
        y0 = C[1] + rng.uniform(-0.4, 0.4) * R
        sp = rng.uniform(0.6, 1.1)
        x = x0 + math.sin(tt * 6 + i) * R * 0.1
        y = y0 - R * rise * sp * ease_out(tt, 1.5)
        s = size * rng.uniform(0.7, 1.3) * (1 - 0.6 * tt) * (0.6 + 0.4 * abs(math.sin(f * 1.7 + i)))
        if kind == "ember":
            bodies.append(tapered_path([(x, y + s * 2.6), (x, y)], [0.4, s * 1.5]))
            hots.append((x, y, s * 0.5))
        elif kind == "hex":
            polys.append(kite((x, y), (0, -1), s * 1.3, s * 0.7, back=0.9))
        elif kind == "glint":
            polys.append(kite((x, y), (0, -1), s * 1.6, s * 0.35, back=1.0))
            polys.append(kite((x, y), (1, 0), s * 1.0, s * 0.3, back=1.0))
        elif kind == "spore":
            hots.append((x, y, s * 0.9))
    if bodies:
        c.paint(c.polys(bodies), V_BODY, order=0.3)
    if polys:
        m = c.polys(polys)
        c.paint(c.sdf(m) > -1.2, V_INK, order=0.25)
        c.paint(m, V_LIGHT if tt < 0.6 else V_BODY, order=0.35)
    if hots:
        if kind == "spore":
            m = c.dots(hots)
            c.paint(c.sdf(m) > -1.3, V_INK, order=0.25)
            c.paint(m, V_BODY, order=0.3)
            c.paint(c.dots([(x + r * 0.2, y + r * 0.25, r * 0.45) for x, y, r in hots]), V_DEEP, order=0.35)
        else:
            c.paint(c.dots(hots), V_HOT if tt < 0.5 else V_LIGHT, order=0.5)


# ---- element recipes -----------------------------------------------------------------------------
def kinetic(f, seed=1):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    sp = P.spikes_even(lay, 7, R, hw_frac=0.44)
    lay_crown, lay_sh, lay_sp, lay_m = [np.random.default_rng(seed + k) for k in (10, 11, 12, 13)]
    if f < 1:
        impact_frame(c, C, R, lay)
        return c.pack()
    crown(c, C, R, np.random.default_rng(seed + 10), f, front=False)
    blast(c, C, R, sp, f)
    crown(c, C, R, np.random.default_rng(seed + 10), f, front=True)
    shards(c, C, R, lay_sh, f, n=7, size=0.2, v_body=V_DEEP)
    sparks(c, C, R, lay_sp, f, n=9)
    motes_up(c, C, R, lay_m, f, n=5, kind="ember", start=14)
    return c.pack()


def flame(f, seed=2):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    sp = P.spikes_even(lay, 6, R * 0.9, hw_frac=0.46)
    if f < 1:
        impact_frame(c, C, R, lay, n=6)
        return c.pack()
    # soot puffs lit orange from the fire, behind
    crown(c, C, R, np.random.default_rng(seed + 10), f, front=False, start=6, lift=0.9, cool=(16, 26), size=0.24)
    blast(c, C, R, sp, f, f_end=8.0)
    # the star breaks into 3-6 tongues that rise and curl
    if 1.5 <= f <= 30:
        rng = np.random.default_rng(seed + 20)
        k = (f - 1.5) / 28.5
        for i in range(5):
            a = -math.pi / 2 + (i - 2) * 0.62 + rng.uniform(-0.15, 0.15)
            grow = ease_out(min(1.0, (f - 1.5) / 6.0), 2.0)
            H = R * rng.uniform(1.1, 1.6) * grow * (1 - 0.5 * k)
            W = R * rng.uniform(0.4, 0.55) * (1 - 0.45 * k)
            rise = R * 0.9 * ease_in(k, 1.4)
            base = (C[0] + math.cos(a) * R * 0.25 * (1 + k), C[1] + math.sin(a) * R * 0.1 + R * 0.2 - rise)
            lean = math.cos(a) * 0.35
            if H > 6:
                vals = (V_BODY, V_LIGHT, V_HOT) if k < 0.3 else ((V_BODY, V_LIGHT, None) if k < 0.6 else (V_DEEP, V_BODY, None))
                P.paint_tongue(c, base, H, W, phase=f * 0.35 + i * 1.3, lean=lean, curl=0.45, vals=vals, order=0.5,
                               v_outer=V_DEEP if k < 0.6 else V_INK)
    crown(c, C, R, np.random.default_rng(seed + 10), f, front=True, start=6, lift=0.9, cool=(16, 26), size=0.22)
    motes_up(c, C, R, np.random.default_rng(seed + 13), f, n=12, kind="ember", start=3, rise=1.6, size=6)
    sparks(c, C, R, np.random.default_rng(seed + 12), f, n=6, end=16, up=1.2)
    return c.pack()


def storm(f, seed=3):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    if f < 1:
        impact_frame(c, C, R, lay, n=8, white_scale=1.2, angular=True)
        return c.pack()
    # a thin angular star, never round; strobes between two shapes
    strobe = int(f * 2) % 2
    sp = P.spikes_even(np.random.default_rng(seed + 100 + strobe), 8, R * 1.05, hw_frac=0.22, short=0.5, jitter=0.25)
    if f <= 10:
        s = 1 - ((f - 1.5) / 8.5) ** 1.2 * 0.85
        spk = [(a, ln * s, h) for a, ln, h in sp]
        ik = [(a + 0.08, ln * 1.3, h * 1.5) for a, ln, h in spk]
        mi, _ = c.star(C, ik, R * 0.2 * s, p=1.1)
        c.paint(mi, V_INK, order=0.3)
        m, rel = c.star(C, spk, R * 0.16 * s, p=1.15)
        hot = float(np.interp(f, [1.5, 6, 10], [0.5, 0.25, 0.0]))
        c.paint(m, np.where(rel < hot, V_HOT, np.where(rel < 0.7, V_LIGHT, V_BODY)), order=0.6)
    # 3-5 forked bolts out to R (the strobe swaps their shapes)
    if f <= 12.5:
        rng = np.random.default_rng(seed + 200 + int(f * 2))
        paths = []
        for i in range(4):
            a = i * math.tau / 4 + 0.4 + rng.uniform(-0.3, 0.3)
            L = R * rng.uniform(0.95, 1.35) * (1 if f < 8 else 0.7)
            p1 = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
            p0 = (C[0] + math.cos(a) * R * 0.12, C[1] + math.sin(a) * R * 0.12)
            paths += P.bolt_paths(p0, p1, rng, 3.4 if f < 8 else 2.4, branches=1, jag=0.2, depth=4)
        P.paint_bolt(c, paths, ink=2.4, body=1.7, core=0.6, order=0.7)
    elif f <= 28:
        # crackle remnants: micro-arcs that flicker and die
        rng = np.random.default_rng(seed + 300 + int(f))
        paths = []
        for i in range(2 if f < 20 else 1):
            a = rng.uniform(0, math.tau)
            r0, r1 = R * rng.uniform(0.3, 0.7), R * rng.uniform(0.3, 0.8)
            p0 = (C[0] + math.cos(a) * r0, C[1] + math.sin(a) * r0)
            p1 = (C[0] + math.cos(a + 0.9) * r1, C[1] + math.sin(a + 0.9) * r1)
            paths += P.bolt_paths(p0, p1, rng, 2.2, branches=0, jag=0.25, depth=3)
        P.paint_bolt(c, paths, ink=2.4, body=1.7, core=0.6, order=0.5)
    sparks(c, C, R, np.random.default_rng(seed + 12), f, n=8, end=18, width=4.5, reach=1.6, grav=0.3)
    return c.pack()


def void(f, seed=4):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    n = 7
    a0 = lay.uniform(0, math.tau)
    if f <= 4.5:
        # implosion: the points aim at the core and close in
        k = f / 4.5
        Ro = R * (1.2 - 0.55 * k)
        polys, rims = [], []
        for i in range(n):
            a = a0 + math.tau * i / n + 0.25 * k
            d = (math.cos(a), math.sin(a))
            nrm = (-d[1], d[0])
            base = (C[0] + d[0] * Ro, C[1] + d[1] * Ro)
            w = Ro * 0.34
            tip_r = Ro * (0.3 - 0.2 * k)
            tip = (C[0] + d[0] * tip_r, C[1] + d[1] * tip_r)
            out = (C[0] + d[0] * Ro * 1.12, C[1] + d[1] * Ro * 1.12)
            polys.append([(base[0] + nrm[0] * w, base[1] + nrm[1] * w), out, (base[0] - nrm[0] * w, base[1] - nrm[1] * w), tip])
            rims.append([(base[0] + nrm[0] * w * 0.3, base[1] + nrm[1] * w * 0.3), tip,
                         (base[0] - nrm[0] * w * 0.3, base[1] - nrm[1] * w * 0.3)])
        c.paint(c.ragged(c.polys(polys), 1.0, 0.5), V_INK, order=0.4)
        c.paint(c.polys(rims), V_BODY if f > 0 else V_LIGHT, order=0.6)
        core = c.dots([(C[0], C[1], R * (0.16 - 0.06 * k))])
        c.paint(core, V_HOT if f >= 3 else V_LIGHT, order=0.9)
    elif f <= 21:
        # flip out: an ink-dominant star with violet rims, then the ink slash star erodes
        k = (f - 6) / 15.0
        grow = ease_out(min(1.0, (f - 4.5) / 4.0), 2.5)
        sp = P.spikes_even(np.random.default_rng(seed + 5), n, R * 1.1 * grow, hw_frac=0.36, a0=a0 + math.pi / n)
        ik = [(a + 0.1, ln * 1.18, h * 1.3) for a, ln, h in sp]
        mi, _ = c.star(C, ik, R * 0.4 * grow, p=1.3, skew=0.4, twist=0.25)
        if f > 8:
            mi &= c.nz(c.X * 0.14, c.Y * 0.14) > max(0.0, k) * 0.95
        c.paint(c.ragged(mi, 1.2, 0.4), V_INK, order=0.35)
        if f < 15:
            m, rel = c.star(C, sp, R * 0.25 * grow, p=1.6, skew=0.4, twist=0.25)
            m &= c.polar(C)[0] > R * (0.2 + 0.5 * max(0.0, k))
            c.paint(m & (rel > 0.55), np.where(rel > 0.85, V_BODY, V_LIGHT), order=0.6)
        core = c.dots([(C[0], C[1], R * 0.12 * (1 - max(0.0, k)) + 1)])
        c.paint(core, V_HOT if f < 10 else V_LIGHT, order=0.9)
    else:
        # the ink stain shrinks to a point
        k = (f - 21) / 19.0
        rr = R * 0.55 * (1 - k) ** 1.3 + 2
        m = c.ragged(c.dots([(C[0], C[1], rr)]), 1.5 * (1 - k) + 0.3, 0.3)
        c.paint(c.sdf(m) > -2.0, V_DEEP, order=0.5)
        c.paint(m, V_INK, order=0.6)
    # hex motes spiral inward and wink out
    rng = np.random.default_rng(seed + 50)
    motes = []
    for i in range(10):
        t0 = rng.uniform(0, 12)
        life = 20
        tt = (f - t0) / life
        if 0 <= tt <= 1:
            ang = i * 2.4 + 2.5 * tt
            r = R * (1.3 - 1.1 * tt)
            p = (C[0] + math.cos(ang) * r, C[1] + math.sin(ang) * r)
            d = norm((C[0] - p[0], C[1] - p[1]))
            s = 6 * (1 - tt * 0.6)
            motes.append(kite(p, rot(d, 0.5), s * 1.3, s * 0.7, back=0.9))
    if motes:
        m = c.polys(motes)
        c.paint(c.sdf(m) > -1.2, V_INK, order=0.2)
        c.paint(m, V_LIGHT, order=0.3)
    return c.pack()


def plague(f, seed=5):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    if f <= 3:
        # the sac swells for 2 frames
        r = R * (0.62 + 0.14 * f / 3)
        b = c.ragged(c.ellipse(C, r * 1.06, r * 0.94), 1.0, 0.4)
        c.paint(c.sdf(b) > -2.4, V_INK, order=0.3)
        c.paint(b, V_BODY, order=0.5)
        c.paint(b & ~c.ellipse((C[0] - r * 0.1, C[1] - r * 0.4), r * 1.02, r * 0.95), V_DEEP, order=0.55)
        c.paint(b & ~c.ellipse((C[0] + r * 0.2, C[1] + r * 0.2), r * 0.98, r * 0.92), V_LIGHT, order=0.6)
        c.paint(c.dots([(C[0] - r * 0.4, C[1] - r * 0.5, r * 0.12)]), V_HOT, order=0.9)
        if f == 0:
            c.paint(c.dots([(C[0], C[1], r * 0.35)]), V_LIGHT, order=0.7)
    else:
        # splatter: a bulbous splash star, teardrop droplets arcing out and falling
        k = (f - 4.5) / 35.5
        if f <= 18:
            kk = (f - 4.5) / 13.5
            n = 8
            rng = np.random.default_rng(seed + 3)
            lobes = []
            for i in range(n):
                a = i * math.tau / n + rng.uniform(-0.2, 0.2)
                L = R * rng.uniform(0.75, 1.1) * (0.8 + 0.3 * ease_out(min(1, kk * 3)))
                w = R * 0.2 * (1 - 0.5 * kk)
                tip = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
                lobes.append(tapered_path([C, ((C[0] + tip[0]) / 2, (C[1] + tip[1]) / 2), tip], [w * 2.2, w * 1.1, w * 1.7]))
                lobes.append(None)
                lobes[-1] = (tip[0], tip[1], w * 1.05)
            polys = [l for l in lobes if isinstance(l, list)]
            dots = [l for l in lobes if isinstance(l, tuple)]
            m = c.polys(polys) | c.dots(dots) | c.dots([(C[0], C[1], R * 0.42 * (1 - 0.5 * kk))])
            m = c.ragged(m, 1.0, 0.5)
            if kk > 0.3:
                m &= c.nz(c.X * 0.12, c.Y * 0.12) > (kk - 0.3) * 0.9
            c.paint(c.sdf(m) > -2.0, V_INK, order=0.3)
            c.paint(m, V_BODY if kk < 0.6 else V_DEEP, order=0.45)
            hi = c.dots([(x - 2, y - 3, r * 0.45) for x, y, r in dots]) & m
            c.paint(hi, V_LIGHT if kk < 0.6 else V_BODY, order=0.55)
            if f < 8:
                c.paint(c.dots([(C[0], C[1], R * 0.2)]), V_HOT if f < 6 else V_LIGHT, order=0.8)
        if f <= 32:
            P.paint_drops(c, C, np.random.default_rng(seed + 7), 9, R * (0.5 + 0.9 * ease_out(min(1, k * 2.5))),
                          R * (0.7 + 1.1 * ease_out(min(1, k * 2.5))), 5.5 * (1 - 0.5 * k),
                          gravity=R * 1.6 * k * k, order=0.5)
        motes_up(c, C, R, np.random.default_rng(seed + 13), f, n=8, kind="spore", start=8, rise=0.6, size=5.5)
    return c.pack()


def radiant(f, seed=6):
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    rotn = 0.0 if f < 10 else math.radians(15)
    if f <= 15:
        grow = [1.25, 1.1, 1.0, 1.0, 0.95, 0.9, 0.82, 0.7, 0.55][min(8, T16.index(f) if f in T16 else 8)]
        thin = 1.0 if f < 4 else float(np.interp(f, [4, 15], [1.0, 0.45]))
        sp = [(rotn + k * math.pi / 2, R * grow * (1.1 if k % 2 == 0 else 0.8), 0.15 * thin) for k in range(4)]
        sp += [(rotn + math.pi / 4 + k * math.pi / 2, R * grow * 0.36, 0.16 * thin) for k in range(4)]
        m, rel = c.star(C, sp, R * 0.08 * grow, p=2.4)
        c.paint(c.sdf(m) > -2.6, V_INK, order=0.3)
        hot = float(np.interp(f, [0, 3, 10], [0.9, 0.45, 0.0]))
        c.paint(m, np.where(rel < hot, V_HOT, np.where(rel < 0.62, V_LIGHT, V_BODY)), order=0.6)
    # thin straight rays: out fast, retract, snap
    if 1.5 <= f <= 21:
        k = (f - 1.5) / 19.5
        ext = float(np.interp(f, [1.5, 4.5, 12.5, 21], [0.7, 1.15, 1.05, 0.6]))
        start = float(np.interp(f, [1.5, 6, 21], [0.15, 0.3, 0.85]))
        rays, cores = [], []
        for i in range(12):
            a = rotn + i * math.tau / 12 + math.tau / 24
            L = R * ext * (1.0 if i % 2 == 0 else 0.74)
            r0 = R * start
            if L < r0 + 4:
                continue
            p0 = (C[0] + math.cos(a) * r0, C[1] + math.sin(a) * r0)
            p1 = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
            w = 3.4 * (1 - 0.5 * k)
            rays.append(tapered_path([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1], [w, w * 1.3, 0.3]))
            cores.append(tapered_path([p0, p1], [w * 0.4, 0.2]))
        mr = c.polys(rays)
        c.paint(c.sdf(mr) > -1.4, V_INK, order=0.2)
        c.paint(mr, V_BODY, order=0.4)
        c.paint(c.polys(cores), V_LIGHT, order=0.5)
    # a broken halo arc at R
    if 3 <= f <= 28:
        k = (f - 3) / 25.0
        arcs = []
        for g in range(3):
            a0 = g * math.tau / 3 + 0.4 + 0.25 * k
            span = 1.3 * (1 - 0.7 * k)
            pts = [(C[0] + math.cos(a) * R * 1.02, C[1] + math.sin(a) * R * 1.02) for a in np.linspace(a0, a0 + span, 20)]
            arcs.append(tapered_path(pts, [0.4] + [4.2 * (1 - 0.5 * k)] * 18 + [0.4]))
        m = c.polys(arcs)
        c.paint(c.sdf(m) > -1.4, V_INK, order=0.2)
        c.paint(m, V_BODY if k < 0.5 else V_DEEP, order=0.4)
    motes_up(c, C, R, np.random.default_rng(seed + 13), f, n=10, kind="glint", start=6, rise=1.2, size=6)
    return c.pack()


def unmade(f, seed=7):
    """Unmade death: white flash on ink, obsidian shards, a teal ichor splash, ichor teardrops."""
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    if f < 2:
        impact_frame(c, C, R * 0.8, lay, n=6, speed=False)
        return c.pack()
    # black-teal ink puff behind
    crown(c, C, R * 0.8, np.random.default_rng(seed + 10), f, front=False, start=3, lift=0.5, size=0.3,
          light_core=False, cool=(4, 14))
    # the ichor splash star (bulbous spikes)
    if f <= 15:
        kk = (f - 2) / 13.0
        rng = np.random.default_rng(seed + 3)
        polys, dots = [], []
        for i in range(7):
            a = i * math.tau / 7 + rng.uniform(-0.25, 0.25)
            L = R * rng.uniform(0.7, 1.05) * (0.75 + 0.35 * ease_out(min(1, kk * 3)))
            w = R * 0.17 * (1 - 0.4 * kk)
            tip = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
            polys.append(tapered_path([C, tip], [w * 2.4, w * 0.8]))
            dots.append((tip[0], tip[1], w * 0.9))
        m = c.polys(polys) | c.dots(dots) | c.dots([(C[0], C[1], R * 0.38 * (1 - 0.4 * kk))])
        m = c.ragged(m, 1.0, 0.5)
        if kk > 0.35:
            m &= c.nz(c.X * 0.12, c.Y * 0.12) > (kk - 0.35) * 1.2
        c.paint(c.sdf(m) > -2.0, V_INK, order=0.3)
        c.paint(m, V_BODY if kk < 0.5 else V_DEEP, order=0.45)
        c.paint(c.dots([(x - 2, y - 2, r * 0.45) for x, y, r in dots]) & m, V_LIGHT, order=0.55)
        if f < 6:
            c.paint(c.dots([(C[0], C[1], R * 0.18)]), V_HOT, order=0.8)
    # obsidian shards: ink bodies with a light edge
    shards(c, C, R, np.random.default_rng(seed + 11), f, n=6, size=0.28, v_body=V_INK, v_edge=V_LIGHT, speed=1.2,
           up=1.0, grav=1.6, end=30)
    if f <= 24:
        k = (f - 3) / 21.0
        if k >= 0:
            P.paint_drops(c, C, np.random.default_rng(seed + 7), 8, R * (0.4 + 0.9 * ease_out(min(1, k * 2))),
                          R * (0.6 + 1.1 * ease_out(min(1, k * 2))), 5.0 * (1 - 0.4 * k), gravity=R * 1.8 * k * k,
                          order=0.5)
    return c.pack()


def godworks(f, seed=8):
    """Fallen Godworks death: cold-gold flash, porcelain and bronze plate shards, falling gold sparks,
    a dead-ember smoke puff, the mask cracking last."""
    c, C, R = frame_cell(seed, f)
    lay = np.random.default_rng(seed)
    if f < 2:
        impact_frame(c, C, R * 0.85, lay, n=5, speed=False)
        return c.pack()
    crown(c, C, R * 0.85, np.random.default_rng(seed + 10), f, front=False, start=3, lift=0.7, size=0.3, cool=(8, 18))
    sp = P.spikes_even(np.random.default_rng(seed + 1), 5, R * 0.8, hw_frac=0.4)
    blast(c, C, R * 0.8, sp, f, f_end=10.0)
    crown(c, C, R * 0.85, np.random.default_rng(seed + 10), f, front=True, start=3, lift=0.7, size=0.26, cool=(8, 18))
    # porcelain plates (light bodies) and bronze plates (deep bodies)
    shards(c, C, R, np.random.default_rng(seed + 11), f, n=5, size=0.3, v_body=V_LIGHT, v_edge=V_HOT, speed=1.1,
           grav=1.8, end=32)
    shards(c, C, R, np.random.default_rng(seed + 12), f, n=5, size=0.22, v_body=V_DEEP, v_edge=V_BODY, speed=1.4,
           grav=1.8, end=32)
    # cold-gold sparks fall with gravity
    sparks(c, C, R, np.random.default_rng(seed + 14), f, n=10, end=24, grav=2.0, width=5.0)
    # the mask cracks last: a porcelain pair of shards, late and heavy
    if 10 <= f <= 32:
        k = (f - 10) / 22.0
        for s in (-1, 1):
            p = (C[0] + s * R * (0.12 + 0.3 * k), C[1] - R * 0.2 + R * 1.3 * k * k)
            d = rot((0, -1), s * (0.3 + 1.2 * k))
            half = [p, (p[0] + d[0] * R * 0.34, p[1] + d[1] * R * 0.34),
                    (p[0] - s * R * 0.22 + d[0] * R * 0.1, p[1] + d[1] * R * 0.1 + R * 0.12),
                    (p[0] - s * R * 0.05, p[1] + R * 0.28)]
            m = c.polys([half])
            c.paint(c.sdf(m) > -1.6, V_INK, order=0.3)
            c.paint(m, V_LIGHT, order=0.4)
            c.paint(c.polys([[half[0], half[1], (half[0][0] * 0.5 + half[2][0] * 0.5, half[0][1] * 0.5 + half[2][1] * 0.5)]]) & m,
                    V_BODY, order=0.45)
    return c.pack()


RECIPES = {"kinetic": kinetic, "flame": flame, "storm": storm, "void": void, "plague": plague, "radiant": radiant,
           "unmade": unmade, "godworks": godworks}

INTENT = {
    "kinetic": "petal star, lit smoke crown, brass shards, chunky sparks (Kinetic explosions, Shrapnel Blaze)",
    "flame": "the star breaks into rising, curling tongues; embers; soot (Flame explosions, Blightburn)",
    "storm": "thin angular strobing star, forked bolts, crackle remnants (Storm explosions, Arc Nova nodes)",
    "void": "implodes f0-4, flips out as an ink star with violet rims, the stain shrinks to a point; hex motes "
            "(Void explosions, Collapsing Star)",
    "plague": "the sac swells, splatters: droplets arc out and fall, spores drift (Plague explosions)",
    "radiant": "4-point cross, straight rays, broken halo arc, rising glints (Radiant explosions, Judgment)",
    "unmade": "Unmade death: white flash on ink, teal ichor splash, obsidian shards, ichor teardrops "
              "(use ramp 'unmade')",
    "godworks": "Fallen Godworks death: cold-gold flash, porcelain and bronze plates, falling gold sparks, "
                "the mask cracks last (use ramp 'godworks_gold')",
}


def _burst(name, f):
    return RECIPES[name](f)


def build(only=None):
    out = []
    for name in ELEMENTS:
        if only and name not in only:
            continue
        a = Atlas(f"vfx_burst_{name}", 4, 4, SIZE, SIZE, intended=INTENT[name])
        for k, cell in enumerate(pmap(_burst, [(name, f) for f in T16])):
            a.put(k % 4, k // 4, cell)
        a.seq("burst", 0, 16, fps=24, pivot=(0.5, 0.56), frame_times_60=T16, radius_in_cell=RIC,
              ramp=RAMP_OF[name], note="frames run row-major across the 4x4 grid")
        a.save(fps=24)
        out.append(a)
    return out


if __name__ == "__main__":
    import sys
    build(sys.argv[1:] or None)
