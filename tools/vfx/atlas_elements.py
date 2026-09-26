"""Element flipbooks (VFX_STYLE sections 4, 13, 16, 17, 19).

  atlas/vfx_bolt_strips.png  8 lightning strips (1024 x 64): stretch one strip from node to node,
                             endpoints at v = 0.5; swap strips at 30 Hz for the strobe
  atlas/vfx_storm.png        4 Lichtenberg scorch decals + 4 micro-arc crackles, 256 px cells
  atlas/vfx_void_swirl.png   16-frame loop: ink spiral arms turning inward (Well, implosions, Eclipse)
  atlas/vfx_plague.png       bubble swell-and-pop, drip, ground splat, spore drift; 8 frames, 128 px
  atlas/vfx_radiant.png      cross flare, ray fan, halo arcs, ground sunburst; 8 frames, 256 px
  atlas/vfx_sparkfx.png      radial spark burst, cone spray, gold spark shower, ember/ash drift; 8 frames
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, bolt_points, kite, norm, pmap, rot,
                    streak_poly, tapered_path)


# ---- storm ---------------------------------------------------------------------------------------
def zigzag(p0, p1, rng, amp, n_seg, lo, hi, fine=3.0):
    """Anime lightning: a few long straight legs with hard corners (alternating sides), then a fine jitter."""
    xs = np.sort(rng.uniform(0.04, 0.96, n_seg - 1))
    xs = np.concatenate([[0.0], xs, [1.0]])
    pts = []
    side = 1 if rng.random() < 0.5 else -1
    for k, t in enumerate(xs):
        x = p0[0] + (p1[0] - p0[0]) * t
        if k == 0 or k == len(xs) - 1:
            y = p0[1] + (p1[1] - p0[1]) * t
        else:
            y = p0[1] + (p1[1] - p0[1]) * t + side * amp * rng.uniform(0.35, 1.0)
            side = -side if rng.random() < 0.8 else side
        pts.append((x, min(max(y, lo), hi)))
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        for t in (0.33, 0.66):
            out.append((a[0] + (b[0] - a[0]) * t + rng.uniform(-fine, fine) * 0.5,
                        min(max(a[1] + (b[1] - a[1]) * t + rng.uniform(-fine, fine), lo), hi)))
        out.append(b)
    return out


def bolt_strip(i, seed, w=1024, h=64):
    c = Cell(w, h, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    p0, p1 = (6.0, h / 2), (w - 6.0, h / 2)
    thin = i >= 6
    main = zigzag(p0, p1, rng, amp=19 if not thin else 14, n_seg=int(rng.integers(9, 15)), lo=11, hi=h - 11)
    paths = [(main, 4.6 if not thin else 3.2)]
    nb = [1, 2, 2, 1, 3, 2, 1, 2][i]
    for _ in range(nb):
        k = int(rng.integers(2, len(main) - 3))
        s = main[k]
        up = -1 if s[1] > h / 2 else 1
        Lb = rng.uniform(50, 150)
        e = (s[0] + Lb * (1 if rng.random() < 0.75 else -0.7), s[1] + up * rng.uniform(8, 18))
        br = zigzag(s, e, rng, amp=6, n_seg=3, lo=7, hi=h - 7, fine=1.5)
        paths.append((br, 2.4))
    P.paint_bolt(c, paths, ink=2.5, body=1.7, core=0.6, taper=True)
    # glow knots on a few corners
    knots = []
    for k in range(3):
        x, y = main[int(rng.integers(3, len(main) - 3))]
        knots.append((x, y, 3.6))
    c.paint(c.dots(knots), V_HOT, order=0.9)
    ero = 0.25 + 0.75 * c.nz_streak(c.X * 0.02 + i * 9, c.Y * 0.002)
    return c.pack(ero=ero)


def lichtenberg(i, seed, s=256):
    """A branching scorch decal from the centre (ground plane)."""
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    C = (s / 2, s / 2)
    R = s * 0.44
    ink, core = [], []

    def branch(p, a, L, w, depth):
        if depth == 0 or L < 6 or w < 0.6:
            return
        e = (p[0] + math.cos(a) * L, p[1] + math.sin(a) * L)
        pts = bolt_points(p, e, rng, jag=0.12, depth=3)
        ink.append((pts, w))
        if w > 1.6:
            core.append((pts, w * 0.32))
        n = 2 if rng.random() < 0.7 else 3
        for k in range(n):
            branch(e, a + rng.uniform(-0.75, 0.75), L * rng.uniform(0.55, 0.78), w * rng.uniform(0.55, 0.72), depth - 1)

    n0 = [5, 6, 4, 7][i]
    for k in range(n0):
        a = math.tau * k / n0 + rng.uniform(-0.3, 0.3)
        branch(C, a, R * rng.uniform(0.28, 0.4), rng.uniform(4.5, 6.5), 5)
    m = c.lines([(p, w) for p, w in ink])
    c.paint(c.dots([(C[0], C[1], s * 0.07)]), V_INK, order=0.8)
    c.paint(m, V_INK, order=0.5)
    c.paint(c.lines([(p, w) for p, w in core]), V_LIGHT, order=0.7)
    c.paint(c.dots([(C[0], C[1], s * 0.03)]), V_BODY, order=0.9)
    r, _ = c.polar(C)
    ero = np.clip(1.0 - r / R, 0.02, 1) * 0.7 + 0.3 * c.nz(c.X * 0.3, c.Y * 0.3)
    return c.pack(ero=ero)


def crackle(i, seed, s=256):
    """Micro-arcs: short forked bolts licking between nearby points (Shock status, beam edges)."""
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    C = (s / 2, s / 2)
    paths = []
    n = [3, 4, 2, 5][i]
    for k in range(n):
        a = rng.uniform(0, math.tau)
        b = a + rng.uniform(0.8, 2.2)
        r0, r1 = s * rng.uniform(0.12, 0.3), s * rng.uniform(0.18, 0.38)
        p0 = (C[0] + math.cos(a) * r0, C[1] + math.sin(a) * r0)
        p1 = (C[0] + math.cos(b) * r1, C[1] + math.sin(b) * r1)
        paths += P.bolt_paths(p0, p1, rng, 2.4, branches=1, jag=0.18, depth=4, branch_len=(0.2, 0.35))
    P.paint_bolt(c, paths, ink=2.8, body=1.8, core=0.65)
    return c.pack()


# ---- void ----------------------------------------------------------------------------------------
def void_swirl(f, seed, s=256, frames=16):
    c = Cell(s, s, seed=seed + f)
    rng = np.random.default_rng(seed)
    C = (s / 2, s / 2)
    R = s * 0.44
    arms = 4
    phase = (f / frames) * (math.tau / arms)  # one arm-spacing per loop -> seamless
    ink_polys, rim_polys, hot_polys = [], [], []
    for k in range(arms):
        a0 = k * math.tau / arms + phase + rng.uniform(-0.05, 0.05)
        pts, wid = [], []
        n = 28
        for j in range(n):
            t = j / (n - 1)  # 0 outer head -> 1 inner tail
            r = R * (1 - t * 0.86)
            ang = a0 + 2.3 * t ** 0.85
            pts.append((C[0] + math.cos(ang) * r, C[1] + math.sin(ang) * r))
            wid.append(R * 0.26 * math.sin(math.pi * min(1.0, 0.1 + t * 1.05)) ** 0.8 * (1 - 0.5 * t) + 0.6)
        ink_polys.append(tapered_path(pts, wid))
        # the bright rim rides the leading (outer) edge near the head
        rp = []
        rw = []
        for j in range(3, 14):
            x, y = pts[j]
            d = norm((x - C[0], y - C[1]))
            off = wid[j] * 0.36
            rp.append((x + d[0] * off, y + d[1] * off))
            rw.append(wid[j] * 0.26 * math.sin(math.pi * (j - 3) / 10))
        rim_polys.append(tapered_path(rp, rw))
        hot_polys.append(tapered_path(rp[2:7], [w * 0.4 for w in rw[2:7]]))
    m = c.ragged(c.polys(ink_polys), 1.0, 0.4)
    c.paint(m, V_INK, order=0.4)
    c.paint(c.polys(rim_polys), V_BODY, order=0.6)
    c.paint(c.polys(hot_polys), V_LIGHT, order=0.7)
    # the pulsing ink core with a thin deep lip
    pulse = 1 + 0.12 * math.sin(math.tau * f / frames * 2)
    core = c.ragged(c.dots([(C[0], C[1], R * 0.2 * pulse)]), 1.2, 0.5)
    c.paint(c.sdf(core) > -2.0, V_DEEP, order=0.8)
    c.paint(core, V_INK, order=0.9)
    # debris motes (hex diamonds) sliding inward along the arms, periodic in the loop
    motes = []
    for k in range(9):
        t = ((k / 9.0) + f / frames) % 1.0
        r = R * (1.02 - t * 0.8)
        ang = (k * 2.39) + phase + 2.3 * t
        p = (C[0] + math.cos(ang) * r, C[1] + math.sin(ang) * r)
        d = norm((C[0] - p[0], C[1] - p[1]))
        sz = 7 * (1 - t * 0.6)
        motes.append(kite(p, d, sz, sz * 0.5, back=0.8))
    c.paint(c.polys(motes), V_LIGHT, order=0.2)
    return c.pack()


# ---- plague --------------------------------------------------------------------------------------
def plague_cell(row, f, seed, s=128):
    c = Cell(s, s, seed=seed + row * 16 + f)
    rng = np.random.default_rng(seed + row)
    C = (s / 2, s / 2)
    if row == 0:  # bubble swells (f0-4), pops (f5), droplets fall (f6-7)
        if f <= 4:
            r = s * (0.12 + 0.07 * f) * (1 + 0.04 * math.sin(f * 2))
            b = c.ragged(c.ellipse((C[0], C[1] + s * 0.1 - r * 0.3), r * 1.04, r * 0.96), 0.8, 0.5)
            c.paint(c.sdf(b) > -1.8, V_INK, order=0.3)
            c.paint(b, V_BODY, order=0.5)
            c.paint(b & ~c.ellipse((C[0] + r * 0.2, C[1] + s * 0.1 - r * 0.2), r * 0.95, r * 0.9), V_LIGHT, order=0.7)
            c.paint(c.dots([(C[0] - r * 0.42, C[1] + s * 0.1 - r * 0.72, r * 0.14)]), V_HOT, order=0.9)
            low = b & ~c.ellipse((C[0] - r * 0.12, C[1] + s * 0.1 - r * 0.42), r * 1.02, r * 0.95)
            c.paint(low, V_DEEP, order=0.4)
        else:
            k = f - 5
            r = s * 0.42
            cy = C[1] + s * 0.1 - r * 0.3
            arcs = []
            for j in range(5):
                a0 = j * math.tau / 5 + rng.uniform(-0.2, 0.2)
                pts = [(C[0] + math.cos(a) * r * (0.8 + 0.3 * k), cy + math.sin(a) * r * (0.8 + 0.3 * k))
                       for a in np.linspace(a0, a0 + 0.55, 6)]
                arcs.append(tapered_path(pts, [0.5, 3.0 - k, 3.4 - k, 3.0 - k, 2.0, 0.5]))
            c.paint(c.polys(arcs), V_BODY if k < 2 else V_DEEP, order=0.3)
            P.paint_drops(c, (C[0], cy), rng, 7, r * (0.5 + 0.3 * k), r * (0.9 + 0.35 * k), 4.5 - k,
                          gravity=10 * (k + 1) ** 2, order=0.4)
            if k == 0:
                c.paint(c.dots([(C[0], cy, r * 0.3)]), V_LIGHT, order=0.9)
    elif row == 1:  # a drip forms, stretches, falls
        top = s * 0.12
        if f <= 3:
            r = 6 + 2.4 * f
            L = 6 + 10 * f
            body = [(C[0] - r * 0.9, top), (C[0] + r * 0.9, top)] + \
                   [(C[0] + math.cos(a) * r, top + L + math.sin(a) * r) for a in np.linspace(0, math.pi, 12)]
            m = c.polys([body])
        else:
            k = f - 4
            y = top + 46 + 16 * k * k
            m = c.polys([P.teardrop((C[0], y), (0, 1), 9, 20 + 6 * k)])
            if k < 3:
                neck = tapered_path([(C[0], top), (C[0], top + 10 + 4 * k)], [8 - 2 * k, 1])
                m |= c.polys([neck])
        c.paint(c.sdf(m) > -1.6, V_INK, order=0.3)
        c.paint(m, V_BODY, order=0.5)
        hi = c.dots([(C[0] - 3, (top + 20 + 6 * f) if f <= 3 else top + 40 + 16 * (f - 4) ** 2, 3)])
        c.paint(hi & m, V_LIGHT, order=0.8)
    elif row == 2:  # ground splat: impact, crown droplets, settle into a puddle stain
        base = (C[0], s * 0.62)
        if f == 0:
            m = c.ellipse(base, s * 0.16, s * 0.07)
            c.paint(c.sdf(m) > -1.6, V_INK, order=0.3)
            c.paint(m, V_LIGHT, order=0.6)
        else:
            pud = c.ragged(c.ellipse(base, s * (0.2 + 0.03 * f), s * (0.09 + 0.012 * f)), 1.2, 0.4)
            c.paint(pud, V_DEEP if f > 4 else V_BODY, order=0.2)
            c.paint(pud & ~c.ellipse((base[0] + 3, base[1] + 2), s * (0.17 + 0.03 * f), s * (0.07 + 0.012 * f)),
                    V_LIGHT if f < 5 else V_BODY, order=0.3)
            if f <= 5:
                drops = []
                for j in range(7):
                    a = math.pi + j * math.pi / 6
                    rr = s * (0.12 + 0.05 * f)
                    h = s * 0.18 * math.sin(min(1.0, f / 4.0) * math.pi) * (0.6 + 0.4 * ((j * 7) % 3) / 2)
                    p = (base[0] + math.cos(a) * rr * 1.2, base[1] + math.sin(a) * rr * 0.4 - h)
                    drops.append(P.teardrop(p, (math.cos(a) * 0.3, -1 if f < 3 else 1), 3.4, 7))
                c.paint(c.polys(drops), V_BODY, order=0.5)
    else:  # spore drift loop
        spores = []
        for j in range(7):
            ph = math.tau * f / 8 + j * 1.7
            x = C[0] + math.cos(j * 2.1) * s * 0.25 + math.sin(ph) * 5
            y = C[1] + math.sin(j * 1.3) * s * 0.22 + math.cos(ph * 1.0) * 4
            r = (4.5 + 2.5 * ((j * 5) % 3)) * (1 + 0.15 * math.sin(ph))
            spores.append((x, y, r))
        m = c.dots(spores)
        m = c.ragged(m, 0.7, 0.6)
        c.paint(c.sdf(m) > -1.4, V_INK, order=0.2)
        c.paint(m, V_BODY, order=0.5)
        c.paint(c.dots([(x + r * 0.2, y + r * 0.25, r * 0.45) for x, y, r in spores]) & m, V_DEEP, order=0.6)
        c.paint(m & ~c.dots([(x + r * 0.25, y + r * 0.3, r * 0.95) for x, y, r in spores]), V_LIGHT, order=0.8)
    return c.pack()


# ---- radiant -------------------------------------------------------------------------------------
def radiant_cell(row, f, seed, s=256):
    c = Cell(s, s, seed=seed + row * 16 + f)
    rng = np.random.default_rng(seed + row)
    C = (s / 2, s / 2)
    R = s * 0.44
    if row == 0:  # cross flare: pops white, snaps 15 deg at f3, thins out
        rotn = 0.0 if f < 3 else math.radians(15)
        grow = [0.7, 1.0, 1.05, 1.0, 0.95, 0.85, 0.7, 0.55][f]
        thin = [1.3, 1.0, 0.9, 0.75, 0.6, 0.48, 0.38, 0.3][f]
        sp = [(rotn + k * math.pi / 2, R * grow * (1.0 if k % 2 == 0 else 0.7), 0.13 * thin) for k in range(4)]
        sp += [(rotn + math.pi / 4 + k * math.pi / 2, R * grow * 0.3, 0.14 * thin) for k in range(4)]
        m, rel = c.star(C, sp, R * 0.06 * grow, p=2.6)
        c.paint(c.sdf(m) > -2.2, V_INK, order=0.2)
        if f == 0:
            c.paint(m, np.where(rel < 0.8, V_HOT, V_LIGHT), order=0.8)
        else:
            hot_e = [0.6, 0.45, 0.3, 0.2, 0.12, 0.05, 0.0, 0.0][f]
            c.paint(m, np.where(rel < hot_e, V_HOT, np.where(rel < 0.62, V_LIGHT, V_BODY)),
                    order=np.clip(1 - rel, 0, 1))
    elif row == 1:  # ray fan: thin straight rays shoot out and retract (rigid, ordered)
        n = 12
        ext = [0.35, 0.8, 1.0, 1.0, 0.95, 0.85, 0.7, 0.5][f]
        start = [0.08, 0.12, 0.18, 0.3, 0.42, 0.55, 0.66, 0.76][f]
        rays_b, rays_l = [], []
        for k in range(n):
            a = k * math.tau / n + (0.0 if f < 4 else math.tau / (2 * n))
            L = R * ext * (1.0 if k % 2 == 0 else 0.7)
            r0 = R * start
            if L <= r0 + 4:
                continue
            p0 = (C[0] + math.cos(a) * r0, C[1] + math.sin(a) * r0)
            p1 = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
            w = (3.2 if k % 2 == 0 else 2.2) * (1.0 if f < 5 else 0.7)
            rays_b.append(tapered_path([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1], [w * 0.8, w * 1.6, 0.3]))
            rays_l.append(tapered_path([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1], [w * 0.3, w * 0.6, 0.1]))
        mb = c.polys(rays_b)
        c.paint(c.sdf(mb) > -1.8, V_INK, order=0.2)
        c.paint(mb, V_BODY, order=0.5)
        c.paint(c.polys(rays_l), V_HOT if f < 3 else V_LIGHT, order=0.8)
        if f < 3:
            core = [(k * math.pi / 2, R * 0.18, 0.3) for k in range(4)]
            m, rel = c.star(C, core, R * 0.05, p=2.0)
            c.paint(m, V_HOT, order=1.0)
    elif row == 2:  # halo arcs: broken concentric arcs sliding round
        arcs_b, arcs_l = [], []
        for k, (rr, span, speed, w) in enumerate([(0.95, 1.9, 0.18, 4.2), (0.78, 1.3, -0.26, 3.2), (0.62, 2.4, 0.3, 2.6)]):
            for g in range(2 if k != 1 else 3):
                a0 = g * math.tau / (2 if k != 1 else 3) + speed * f + k
                pts = [(C[0] + math.cos(a) * R * rr, C[1] + math.sin(a) * R * rr)
                       for a in np.linspace(a0, a0 + span * (1 - 0.06 * f), 24)]
                ww = w * (1 - 0.08 * f)
                arcs_b.append(tapered_path(pts, [0.4] + [ww] * 22 + [0.4]))
                arcs_l.append(tapered_path(pts[4:20], [0.2] + [ww * 0.35] * 14 + [0.2]))
        mb = c.polys(arcs_b)
        c.paint(c.sdf(mb) > -1.6, V_INK, order=0.2)
        c.paint(mb, V_BODY, order=0.5)
        c.paint(c.polys(arcs_l), V_LIGHT, order=0.8)
    else:  # ground sunburst: alternating wedges, a slow 8-frame rotation loop
        n = 16
        rotn = f / 8.0 * (math.tau / (n / 2))
        wl, ws = [], []
        for k in range(n):
            a = rotn + k * math.tau / n
            L = R * (1.0 if k % 2 == 0 else 0.68)
            hw = math.tau / n * (0.42 if k % 2 == 0 else 0.3)
            r0 = R * 0.22
            pts = [(C[0] + math.cos(a - hw) * r0, C[1] + math.sin(a - hw) * r0),
                   (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L),
                   (C[0] + math.cos(a + hw) * r0, C[1] + math.sin(a + hw) * r0)]
            (wl if k % 2 == 0 else ws).append(pts)
        c.paint(c.polys(wl), V_BODY, order=0.4)
        c.paint(c.polys(ws), V_DEEP, order=0.3)
        ring = c.dots([(C[0], C[1], R * 0.2)]) & ~c.dots([(C[0], C[1], R * 0.14)])
        c.paint(ring, V_LIGHT, order=0.6)
    return c.pack()


# ---- spark flipbooks -----------------------------------------------------------------------------
def sparkfx_cell(row, f, seed, s=256):
    c = Cell(s, s, seed=seed + row * 16 + f)
    rng = np.random.default_rng(seed + row)
    C = (s / 2, s / 2)
    R = s * 0.45
    t = f / 7.0
    if row == 0:  # radial burst: out fast, decelerate, shrink
        prog = 1 - (1 - t) ** 2.2
        n = 16
        heads, bodies = [], []
        for k in range(n):
            a = k * math.tau / n + rng.uniform(-0.2, 0.2)
            sp = rng.uniform(0.55, 1.0)
            r1 = R * (0.12 + 0.88 * prog) * sp
            ln = R * (0.35 * (1 - t) ** 1.5 + 0.04) * sp
            r0 = max(R * 0.05, r1 - ln)
            g = 10 * t * t * sp
            p1 = (C[0] + math.cos(a) * r1, C[1] + math.sin(a) * r1 + g)
            p0 = (C[0] + math.cos(a) * r0, C[1] + math.sin(a) * r0)
            w = (8.0 * (1 - 0.6 * t)) * rng.uniform(0.7, 1.2)
            bodies.append(streak_poly(p1, p0, w, 0))
            heads.append(streak_poly(p1, (p1[0] * 0.6 + p0[0] * 0.4, p1[1] * 0.6 + p0[1] * 0.4), w * 0.6, 0))
        mb = c.polys(bodies)
        c.paint(mb, V_BODY if f < 5 else V_DEEP, order=0.3)
        c.paint(c.polys(heads), V_HOT if f < 3 else (V_LIGHT if f < 6 else V_BODY), order=0.6)
        if f < 2:
            m, _ = c.star(C, [(k * math.pi / 2 + 0.4, R * 0.2, 0.35) for k in range(4)], R * 0.05)
            c.paint(m, V_HOT, order=1.0)
    elif row == 1:  # cone spray toward +u with gravity
        prog = 1 - (1 - t) ** 2
        o = (s * 0.12, s * 0.5)
        heads, bodies = [], []
        for k in range(12):
            a = rng.uniform(-0.55, 0.55)
            sp = rng.uniform(0.5, 1.0)
            r1 = s * 0.8 * (0.1 + 0.9 * prog) * sp
            ln = s * (0.25 * (1 - t) ** 1.4 + 0.03) * sp
            r0 = max(2, r1 - ln)
            g1 = 34 * (t * sp) ** 2
            p1 = (o[0] + math.cos(a) * r1, o[1] + math.sin(a) * r1 + g1)
            p0 = (o[0] + math.cos(a) * r0, o[1] + math.sin(a) * r0 + g1 * 0.7)
            w = 7.5 * (1 - 0.5 * t) * rng.uniform(0.7, 1.2)
            bodies.append(streak_poly(p1, p0, w, 0))
            heads.append(streak_poly(p1, (p1[0] * 0.6 + p0[0] * 0.4, p1[1] * 0.6 + p0[1] * 0.4), w * 0.6, 0))
        c.paint(c.polys(bodies), V_BODY if f < 5 else V_DEEP, order=0.3)
        c.paint(c.polys(heads), V_HOT if f < 3 else V_LIGHT, order=0.6)
    elif row == 2:  # gold spark shower: thrown up from the base, arcing and falling
        o = (C[0], s * 0.78)
        heads, bodies, dots = [], [], []
        for k in range(18):
            a = -math.pi / 2 + rng.uniform(-0.75, 0.75)
            v = rng.uniform(0.55, 1.0) * s * 1.35
            tt = t * 0.9 + 0.05
            g = s * 1.6
            x = o[0] + math.cos(a) * v * tt
            y = o[1] + math.sin(a) * v * tt + 0.5 * g * tt * tt
            vx, vy = math.cos(a) * v, math.sin(a) * v + g * tt
            d = norm((vx, vy))
            ln = 22 * (1 - 0.5 * t)
            p1 = (x, y)
            p0 = (x - d[0] * ln, y - d[1] * ln)
            if not (8 < y < s - 8):
                continue
            w = 6.4 * rng.uniform(0.7, 1.2) * (1 - 0.4 * t)
            bodies.append(streak_poly(p1, p0, w, 0))
            heads.append(streak_poly(p1, (p1[0] * 0.5 + p0[0] * 0.5, p1[1] * 0.5 + p0[1] * 0.5), w * 0.6, 0))
        c.paint(c.polys(bodies), V_BODY, order=0.3)
        c.paint(c.polys(heads), V_HOT if f < 4 else V_LIGHT, order=0.6)
        if f < 2:
            m, _ = c.star(o, [(-math.pi / 2 + k * math.pi / 2, s * 0.06 * (1.5 - f * 0.5), 0.4) for k in range(4)], 4)
            c.paint(m, V_HOT, order=0.9)
    else:  # ember / ash drift loop: embers rise and flicker, ash flakes tumble
        polys_e, hot, ash = [], [], []
        for k in range(10):
            ph = (k / 10.0 + f / 8.0) % 1.0
            x = C[0] + math.sin(k * 2.7) * s * 0.3 + math.sin(ph * math.tau + k) * 6
            y = s * 0.9 - ph * s * 0.8
            fl = 0.6 + 0.4 * abs(math.sin(ph * math.tau * 3 + k))
            sz = (6.0 + 3.5 * ((k * 3) % 2)) * fl * (1 - ph * 0.5)
            if k % 3 == 2:
                ang = ph * 8 + k
                pts = [(x + math.cos(ang + j * 2.1) * sz * 1.6, y + math.sin(ang + j * 2.1) * sz * 0.7) for j in range(3)]
                ash.append(pts)
            else:
                polys_e.append(tapered_path([(x, y + sz * 3), (x, y)], [0.5, sz * 1.6]))
                hot.append((x, y, sz * 0.45))
        c.paint(c.polys(ash), V_INK, order=0.2)
        c.paint(c.polys(polys_e), V_BODY, order=0.4)
        c.paint(c.dots(hot), V_HOT, order=0.8)
    return c.pack()


def _call2(fn, args):
    return fn(*args)


def build():
    out = []
    b = Atlas("vfx_bolt_strips", 1, 8, 1024, 64, intended="lightning strips for chain hops, Arc Nova, "
              "Railshock / Judgment variants, storm strikes: stretch u between the two nodes")
    for k, cell in enumerate(pmap(bolt_strip, [(i, 1000) for i in range(8)])):
        b.put(0, k, cell)
    b.seq("bolt", 0, 8, fps=30, loop=True, pivot=(0.0, 0.5), axis="column", note="frames run down the column (row = "
          "frame); swap 2 strips at 30 Hz for the strobe; strips 6-7 are thinner (branches, micro-arcs)",
          endpoints=[[0.006, 0.5], [0.994, 0.5]])
    b.save(fps=30)
    out.append(b)

    st = Atlas("vfx_storm", 4, 2, 256, 256, intended="Storm ground scorch and crackle")
    jobs = [(lichtenberg, (i, 1100)) for i in range(4)] + [(crackle, (i, 1200)) for i in range(4)]
    for k, cell in enumerate(pmap(_call2, jobs)):
        st.put(k % 4, k // 4, cell)
    st.seq("lichtenberg", 0, 4, pivot=(0.5, 0.5), intended="Lichtenberg scorch decals (2 s, cool the light core)",
           radius_in_cell=0.88, plane="ground")
    st.seq("crackle", 1, 4, fps=20, pivot=(0.5, 0.5), intended="micro-arcs: Shock status, Storm edge crackle, "
           "Static Charge; swap at 20 Hz")
    st.save()
    out.append(st)

    v = Atlas("vfx_void_swirl", 4, 4, 256, 256, intended="Void spiral: GravityWell hazard, implosions, Eclipse, "
              "Gravity Chain nodes")
    for k, cell in enumerate(pmap(void_swirl, [(f, 1300) for f in range(16)])):
        v.put(k % 4, k // 4, cell)
    v.seq("swirl", 0, 16, fps=16, loop=True, pivot=(0.5, 0.5), radius_in_cell=0.88, plane="ground",
          note="frames run row-major across the 4x4 grid")
    v.save(fps=16)
    out.append(v)

    pl = Atlas("vfx_plague", 8, 4, 128, 128, intended="Plague secondaries")
    for k, cell in enumerate(pmap(plague_cell, [(r, f, 1400) for r in range(4) for f in range(8)])):
        pl.put(k % 8, k // 8, cell)
    pl.seq("bubble", 0, 8, fps=15, pivot=(0.5, 0.6), intended="bubble swells f0-4, pops f5, droplets fall")
    pl.seq("drip", 1, 8, fps=15, pivot=(0.5, 0.12), intended="a drip forms under a surface and falls")
    pl.seq("splat", 2, 8, fps=20, pivot=(0.5, 0.62), intended="droplet lands: crown splash, puddle")
    pl.seq("spores", 3, 8, fps=8, loop=True, pivot=(0.5, 0.5), intended="spore cloud drift loop")
    pl.save(fps=15)
    out.append(pl)

    ra = Atlas("vfx_radiant", 8, 4, 256, 256, intended="Radiant flares: rigid, straight, snapping")
    for k, cell in enumerate(pmap(radiant_cell, [(r, f, 1500) for r in range(4) for f in range(8)])):
        ra.put(k % 8, k // 8, cell)
    ra.seq("cross_flare", 0, 8, fps=30, pivot=(0.5, 0.5), intended="4-point cross glint: crits, Radiant hits, "
           "prism tip; snaps 15 deg at f3")
    ra.seq("ray_fan", 1, 8, fps=30, pivot=(0.5, 0.5), intended="straight rays out and back: Radiant bursts, "
           "Judgment Bolt nodes")
    ra.seq("halo_arcs", 2, 8, fps=20, pivot=(0.5, 0.5), intended="broken halo arcs: Seraph Lance accents, "
           "Eclipse corona, Purge")
    ra.seq("sunburst", 3, 8, fps=8, loop=True, pivot=(0.5, 0.5), plane="ground", intended="ground sunburst "
           "wedges: Solar Flare, Godforged loot base, recipe discovered")
    ra.save(fps=30)
    out.append(ra)

    sf = Atlas("vfx_sparkfx", 8, 4, 256, 256, intended="spark flipbooks")
    for k, cell in enumerate(pmap(sparkfx_cell, [(r, f, 1600) for r in range(4) for f in range(8)])):
        sf.put(k % 8, k // 8, cell)
    sf.seq("radial_burst", 0, 8, fps=24, pivot=(0.5, 0.5), intended="radial spark burst: impacts, kills, forge "
           "hammer strikes")
    sf.seq("cone_spray", 1, 8, fps=24, pivot=(0.12, 0.5), intended="sparks sprayed along a surface normal (+u): "
           "plated / boss hits, ricochet, pierce exit")
    sf.seq("shower", 2, 8, fps=20, pivot=(0.5, 0.78), intended="gold spark shower: forge actions, anvil, coin "
           "fountain, Sabbath of Sparks")
    sf.seq("ember_drift", 3, 8, fps=10, loop=True, pivot=(0.5, 0.9), intended="ember and ash drift loop: heat "
           "columns, Meltdown, burning ground")
    sf.save(fps=24)
    out.append(sf)
    return out


if __name__ == "__main__":
    build()
