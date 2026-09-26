"""Shared painting recipes on a vfxlib.Cell: smoke puffs, sparks, shards, droplets, tongues, bolts,
stars. Every recipe paints flat value bands (ink / deep / body / light / hot) and an erosion order.
"""
import math

import numpy as np

from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, bolt_points, kite, norm, rot, streak_poly,
                    tapered_path, tongue_poly, wrap)


# ---- smoke ---------------------------------------------------------------------------------------
def puff_cluster(c, lobes, light=(0.0, -1.0), rim=0.24, mid=0.52, v_rim=V_LIGHT, v_mid=V_DEEP, v_shadow=V_INK,
                 rough=0.22, order0=0.35, order1=0.75, seed_off=0.0, light_pt=None):
    """Union of noisy circles painted back to front. Each lobe gets three flat tones: a lit crescent
    facing the light (direction `light`, or the point `light_pt`), a mid crescent, and the ink shadow."""
    n = len(lobes)
    for i, (x, y, r) in enumerate(lobes):
        x0, x1 = int(max(0, (x - r * 1.4) * c.ss)), int(min(c.W, (x + r * 1.4) * c.ss))
        y0, y1 = int(max(0, (y - r * 1.4) * c.ss)), int(min(c.H, (y + r * 1.4) * c.ss))
        if x1 <= x0 or y1 <= y0:
            continue
        X = c.X[y0:y1, x0:x1]
        Y = c.Y[y0:y1, x0:x1]
        dx = X - x
        dy = Y - y
        th = np.arctan2(dy, dx)
        wob = rough * (c.nz((th + np.pi) * 3.0 + i * 7.7 + seed_off, np.full_like(th, i * 5.3 + seed_off)) - 0.5) * 2
        wob += rough * 0.35 * (c.nz((th + np.pi) * 11.0 + i * 3.1, np.full_like(th, i * 2.9 + 40)) - 0.5) * 2
        rn = r * (1 + wob)
        inside = np.hypot(dx, dy) <= rn
        if light_pt is not None:
            ld = norm((light_pt[0] - x, light_pt[1] - y))
        else:
            ld = norm(light)
        d_rim = np.hypot(dx + ld[0] * r * rim, dy + ld[1] * r * rim) / np.maximum(rn, 1e-3)
        d_mid = np.hypot(dx + ld[0] * r * mid, dy + ld[1] * r * mid) / np.maximum(rn, 1e-3)
        val = np.where(d_rim > 1.0, v_rim, np.where(d_mid > 1.0, v_mid, v_shadow)).astype(np.float32)
        m = np.zeros(c.cov.shape, bool)
        m[y0:y1, x0:x1] = inside
        v = np.zeros(c.cov.shape, np.float32)
        v[y0:y1, x0:x1] = val
        c.paint(m, v, order=order0 + (order1 - order0) * (i / max(1, n - 1)))


def cumulus(rng, cx, cy, R, n=7, flat=0.0, tall=0.0, lean=0.0, spread=1.0):
    """Lobe layout for a puff: a bulbous top, a flatter base; returns [(x, y, r)] back to front."""
    lobes = []
    for i in range(n):
        a = rng.uniform(0, math.tau)
        d = R * 0.42 * math.sqrt(rng.uniform(0.05, 1.0)) * spread
        x = cx + math.cos(a) * d * (1 + flat * 0.8) + lean * R * 0.3
        y = cy + math.sin(a) * d * (1 - flat * 0.5) * (1 + tall)
        r = R * rng.uniform(0.38, 0.58) * (1 - 0.25 * flat)
        lobes.append((x, y, r))
    # the crown lobe on top
    lobes.append((cx + lean * R * 0.2 + rng.uniform(-0.1, 0.1) * R, cy - R * (0.28 + 0.3 * tall), R * 0.5))
    lobes.sort(key=lambda l: -l[1])  # lower lobes first, upper lobes paint over them
    return lobes


# ---- sparks, shards, droplets ------------------------------------------------------------------
def spark_polys(center, rng, n, r0, r1, width, direction=None, spread=math.pi, gravity=0.0, length=None):
    """Streak polygons (round hot head at the far end) flying out of center. Returns (heads, bodies)."""
    heads, bodies = [], []
    for _ in range(n):
        if direction is None:
            a = rng.uniform(0, math.tau)
        else:
            a = math.atan2(direction[1], direction[0]) + rng.uniform(-spread, spread)
        rr1 = r1 * rng.uniform(0.6, 1.1)
        ln = (length if length is not None else (r1 - r0) * 0.45) * rng.uniform(0.6, 1.3)
        rr0 = max(r0, rr1 - ln)
        v = (math.cos(a), math.sin(a))
        g1 = gravity * (rr1 / max(r1, 1)) ** 2
        g0 = gravity * (rr0 / max(r1, 1)) ** 2
        p1 = (center[0] + v[0] * rr1, center[1] + v[1] * rr1 + g1)
        p0 = (center[0] + v[0] * rr0, center[1] + v[1] * rr0 + g0)
        w = width * rng.uniform(0.7, 1.3)
        bodies.append(streak_poly(p1, p0, w, 0.0))
        heads.append(streak_poly(p1, (p1[0] * 0.55 + p0[0] * 0.45, p1[1] * 0.55 + p0[1] * 0.45), w * 0.62, 0.0))
    return heads, bodies


def paint_sparks(c, center, rng, n, r0, r1, width, v_body=V_LIGHT, v_head=V_HOT, order=0.3, **kw):
    heads, bodies = spark_polys(center, rng, n, r0, r1, width, **kw)
    c.paint(c.polys(bodies), v_body, order=order)
    c.paint(c.polys(heads), v_head, order=order + 0.1)


def shard_polys(p, d, L, w, back=0.45):
    """A shard kite plus its lit facet (one side of the kite, from the tip to the waist)."""
    k = kite(p, d, L, w, back=back)
    facet = [k[0], k[1], (k[1][0] * 0.4 + k[2][0] * 0.6, k[1][1] * 0.4 + k[2][1] * 0.6),
             ((k[0][0] + k[2][0]) / 2, (k[0][1] + k[2][1]) / 2)]
    return k, facet


def paint_shards(c, center, rng, n, r0, r1, size, v_body=V_INK, v_edge=V_LIGHT, order=0.25, lift=0.0, spin=0.7,
                 sizes=None):
    bodies, facets = [], []
    for i in range(n):
        a = rng.uniform(0, math.tau)
        rr = rng.uniform(r0, r1)
        p = (center[0] + math.cos(a) * rr, center[1] + math.sin(a) * rr - lift * rng.uniform(0.3, 1.0))
        d = rot((math.cos(a), math.sin(a)), rng.uniform(-spin, spin))
        Ls = size * (rng.uniform(0.6, 1.3) if sizes is None else sizes[i % len(sizes)])
        k, f = shard_polys(p, d, Ls, Ls * rng.uniform(0.28, 0.42))
        bodies.append(k)
        facets.append(f)
    c.paint(c.ragged(c.polys(bodies), 0.4, 0.8), v_body, order=order)
    c.paint(c.polys(facets), v_edge, order=order + 0.05)


def teardrop(p, d, r, L, n=14):
    """A droplet: round head of radius r at p, tail of length L trailing opposite to d."""
    d = norm(d)
    nrm = (-d[1], d[0])
    pts = []
    for a in np.linspace(-math.pi / 2, math.pi / 2, n):
        v = (d[0] * math.cos(a) + nrm[0] * math.sin(a), d[1] * math.cos(a) + nrm[1] * math.sin(a))
        pts.append((p[0] + v[0] * r, p[1] + v[1] * r))
    tail = (p[0] - d[0] * L, p[1] - d[1] * L)
    return pts + [tail]


def paint_drops(c, center, rng, n, r0, r1, size, v_body=V_BODY, v_hi=V_LIGHT, gravity=0.0, order=0.3,
                direction=None, spread=math.pi, stretch=2.2):
    bodies, his = [], []
    for _ in range(n):
        if direction is None:
            a = rng.uniform(0, math.tau)
        else:
            a = math.atan2(direction[1], direction[0]) + rng.uniform(-spread, spread)
        rr = rng.uniform(r0, r1)
        g = gravity * (rr / max(r1, 1)) ** 2
        p = (center[0] + math.cos(a) * rr, center[1] + math.sin(a) * rr + g)
        vel = norm((math.cos(a), math.sin(a) + 2 * gravity / max(r1, 1) * (rr / max(r1, 1))))
        r = size * rng.uniform(0.6, 1.25)
        bodies.append(teardrop(p, vel, r, r * stretch))
        hp = (p[0] + vel[0] * r * 0.25 - vel[1] * r * 0.3, p[1] + vel[1] * r * 0.25 + vel[0] * r * 0.3)
        his.append(teardrop(hp, vel, r * 0.38, r * 0.8))
    c.paint(c.polys(bodies), v_body, order=order)
    c.paint(c.polys(his), v_hi, order=order + 0.1)


# ---- flames --------------------------------------------------------------------------------------
def paint_tongue(c, base, H, W, phase, lean=0.0, curl=0.35, order=0.5, vals=(V_BODY, V_LIGHT, V_HOT),
                 tip_curl=0.5, ragged=True, v_outer=V_DEEP):
    """Flame tongue as nested tongues: a deep outer tongue (it shows as the tip and a thin rim), the body,
    a light inner tongue and a hot core at the base."""
    outer = tongue_poly(base, H, W, phase, lean, curl, tip_curl=tip_curl)
    body = tongue_poly((base[0], base[1] - H * 0.005), H * 0.84, W * 0.8, phase + 0.12, lean, curl,
                       tip_curl=tip_curl * 0.85)
    mid = tongue_poly((base[0], base[1] - H * 0.01), H * 0.52, W * 0.46, phase + 0.25, lean, curl * 0.9,
                      tip_curl=tip_curl * 0.7)
    core = tongue_poly((base[0], base[1] - H * 0.02), H * 0.24, W * 0.22, phase + 0.5, lean * 0.8, curl * 0.6,
                       tip_curl=0.2)
    m = c.polys([outer])
    if ragged:
        m = c.ragged(m, 0.8, 0.5, streak=False)
    c.paint(m, v_outer if v_outer is not None else vals[0], order=order - 0.1)
    c.paint(c.polys([body]) & m, vals[0], order=order)
    if vals[1] is not None:
        c.paint(c.polys([mid]) & m, vals[1], order=order + 0.2)
    if vals[2] is not None:
        c.paint(c.polys([core]) & m, vals[2], order=order + 0.4)
    return m


# ---- bolts ---------------------------------------------------------------------------------------
def bolt_paths(p0, p1, rng, width, branches=2, jag=0.22, depth=5, branch_len=(0.2, 0.4)):
    main = bolt_points(p0, p1, rng, jag=jag, depth=depth)
    paths = [(main, width)]
    for _ in range(branches):
        i = int(rng.integers(len(main) // 5, max(len(main) // 5 + 1, len(main) * 4 // 5)))
        s = main[i]
        d = norm((p1[0] - p0[0], p1[1] - p0[1]))
        d = rot(d, rng.uniform(0.45, 0.95) * (1 if rng.random() < 0.5 else -1))
        Lb = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * rng.uniform(*branch_len)
        e = (s[0] + d[0] * Lb, s[1] + d[1] * Lb)
        paths.append((bolt_points(s, e, rng, jag=jag * 1.2, depth=max(2, depth - 1)), width * 0.55))
    return paths


def paint_bolt(c, paths, ink=2.6, body=1.7, core=0.6, order=0.5, v_core=V_HOT, v_body=V_BODY, taper=True):
    """Ink sheath (ink x width), coloured body (body x width), white core (core x width)."""
    def lines(k):
        out = []
        for pts, w in paths:
            if taper and len(pts) > 3:
                n = len(pts)
                wid = [w * k * (0.35 + 0.65 * math.sin(math.pi * min(1.0, 0.15 + 0.85 * i / (n - 1)))) for i in range(n)]
                out.append(tapered_path(pts, wid))
            else:
                out.append(tapered_path(pts, [w * k] * len(pts)))
        return out
    if ink:
        c.paint(c.polys(lines(ink)), V_INK, order=order - 0.2)
    c.paint(c.polys(lines(body)), v_body, order=order)
    c.paint(c.polys(lines(core)), v_core, order=order + 0.2)


# ---- stars ---------------------------------------------------------------------------------------
def spikes_even(rng, n, R, hw_frac=0.45, jitter=0.1, long_short=True, a0=None, short=0.62):
    spacing = math.tau / n
    a0 = rng.uniform(0, math.tau) if a0 is None else a0
    out = []
    for i in range(n):
        a = a0 + spacing * i + rng.uniform(-0.12, 0.12) * spacing
        long = (i % 2 == 0 and not (n % 2 == 1 and i == n - 1)) or not long_short
        ln = R * (1.0 if long else short) * (1 + rng.uniform(-jitter, jitter))
        out.append((a, ln, spacing * hw_frac * (1.0 if long else 0.82)))
    return out


def banded_star(c, C, sp, r_in, hot=0.6, light=0.75, rim=0.87, twist=0.06, skew=0.35, j=None, order=0.5,
                white=False, ragged=0.7, dry=0.0):
    """Body star with a deep rim, a nested light star and a thin hot star (VFX_STYLE 'Star')."""
    if j is None:
        j = (c.nz(c.X * 0.3, c.Y * 0.3) - 0.5) * 0.1
    mo, relo = c.star(C, sp, r_in, p=1.25, twist=twist, rough=0.05, skew=skew)
    if dry > 0:
        r, th = c.polar(C)
        st = c.nz_streak(th * 55, r * 0.07)
        mo &= ~((relo > 1 - dry) & (st < (relo - (1 - dry)) / dry * 0.7))
    if ragged:
        mo = c.ragged(mo, amp=ragged, freq=0.5)
    if white:
        c.paint(mo, np.where(relo + j > 0.9, V_LIGHT, V_HOT), order=order)
        return mo
    c.paint(mo, np.where(relo + j > rim, V_DEEP, V_BODY), order=order * 0.8)
    if light > 0:
        mm, relm = c.star(C, [(a + 0.06, ln * 0.8, h * 0.72) for a, ln, h in sp], r_in * 0.8, p=1.5,
                          twist=twist * 1.3, skew=skew)
        c.paint(mm & (relm + j < light) & mo, V_LIGHT, order=order + 0.2)
    if hot > 0:
        mh, relh = c.star(C, [(a + 0.03, ln * 0.62, h * 0.46) for a, ln, h in sp], r_in * 0.42, p=2.0,
                          twist=twist * 1.5)
        c.paint(mh & (relh + j * 0.6 < hot) & mo, V_HOT, order=order + 0.4)
    return mo


def speed_lines(c, C, rng, n, r0, r1, width, v=V_LIGHT, order=0.2):
    polys = []
    for i in range(n):
        a = math.tau * i / n + rng.uniform(-0.12, 0.12)
        a0 = r0 * rng.uniform(0.9, 1.3)
        a1 = r1 * rng.uniform(0.7, 1.0)
        p0 = (C[0] + math.cos(a) * a0, C[1] + math.sin(a) * a0)
        p1 = (C[0] + math.cos(a) * a1, C[1] + math.sin(a) * a1)
        w = width * rng.uniform(0.6, 1.2)
        polys.append(tapered_path([p0, ((p0[0] * 2 + p1[0]) / 3, (p0[1] * 2 + p1[1]) / 3), p1], [0.3, w, 0.2]))
    c.paint(c.polys(polys), v, order=order)
