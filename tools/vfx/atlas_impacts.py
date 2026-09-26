"""Impact stars and muzzle flashes (VFX_STYLE sections 2, 5, 8, 10).

  atlas/vfx_impact_star.png        8 frames x 4 variants (4/5/7/9 points), 256 px cells
  atlas/vfx_petal_flash.png        4 frames x 4 kinds (forward fan, sunburst wedges, cross, inward star)
  atlas/vfx_muzzle_directional.png 4 frames x 4 kinds (rapid flicker, precise spike, rail, petal bloom)
"""
import math

import numpy as np

from vfxlib import (V_DEEP, V_BODY, V_HOT, V_INK, V_LIGHT, Atlas, Cell, band_value, kite, pmap, tapered_path)

# The impact is painted at these 60 fps frames: f0-1 impact frame, f2-5 peak, f6-14 collapse.
STAR_TIMES = [0, 1, 2, 4, 6, 8, 11, 14]


def spike_set(rng, n, R, long_short=True, jitter=0.22, hw=0.2, a0=None):
    a0 = rng.uniform(0, math.tau) if a0 is None else a0
    out = []
    for i in range(n):
        a = a0 + math.tau * i / n + rng.uniform(-0.22, 0.22) * math.tau / n
        long = (i % 2 == 0) or not long_short
        if n % 2 == 1 and i == n - 1:
            long = False
        ln = R * (1.0 if long else 0.58) * (1 + rng.uniform(-jitter, jitter))
        out.append([a, ln, hw * (1 + rng.uniform(-0.3, 0.3)) * (1.0 if long else 0.8)])
    return out


def impact_star(n_points, f, seed, size=256):
    """One frame of the banded impact star at 60 fps frame f (0..14): a bold pinwheel star with nested
    body / light / hot stars (f0 is the white impact frame); from f6 on it breaks into curling petals."""
    c = Cell(size, size, seed=seed * 101 + int(f * 10))
    rng = np.random.default_rng(seed)
    C = (size / 2, size / 2)
    R = size * 0.4
    spacing = math.tau / n_points
    hw = spacing * {4: 0.34, 5: 0.42, 7: 0.5, 9: 0.52}[n_points]
    a0 = rng.uniform(0, math.tau)
    spikes = []
    for i in range(n_points):
        a = a0 + spacing * i + rng.uniform(-0.12, 0.12) * spacing
        long = i % 2 == 0 and not (n_points % 2 == 1 and i == n_points - 1)
        ln = R * (1.0 if long else 0.64) * (1 + rng.uniform(-0.1, 0.1))
        spikes.append((a, ln, hw * (1.0 if long else 0.82) * (1 + rng.uniform(-0.12, 0.12))))
    T = [0, 1, 2, 4, 6, 8, 11, 14]
    grow = float(np.interp(f, T, [1.12, 1.03, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]))
    wmul = float(np.interp(f, T, [0.62, 0.98, 1.06, 1.1, 0.95, 0.72, 0.46, 0.3]))
    twist = 0.05 + 0.02 * f
    skew = 0.38
    j = (c.nz(c.X * 0.3, c.Y * 0.3) - 0.5) * 0.1
    if f <= 4:
        sp = [(a, ln * grow, h * wmul) for a, ln, h in spikes]
        r_in = R * float(np.interp(f, [0, 1, 2, 4], [0.3, 0.4, 0.4, 0.38]))
        mo, relo = c.star(C, sp, r_in, p=1.25, twist=twist, rough=0.05, skew=skew)
        if f >= 2:
            # dry-brush streaks break the spike tips
            r, th = c.polar(C)
            db = 0.14 + 0.05 * f
            st = c.nz_streak(th * 55, r * 0.07)
            mo &= ~((relo > 1 - db) & (st < (relo - (1 - db)) / db * 0.7))
        mo = c.ragged(mo, amp=0.7, freq=0.5)
        if f == 0:
            c.paint(mo, np.where(relo + j > 0.9, V_LIGHT, V_HOT), order=np.clip(1.1 - relo, 0, 1))
        else:
            c.paint(mo, np.where(relo + j > 0.87, V_DEEP, V_BODY), order=np.clip(1.1 - relo, 0, 1) * 0.6)
            ms = float(np.interp(f, [1, 2, 4], [0.8, 0.66, 0.54]))
            mm, relm = c.star(C, [(a + 0.06, ln * 0.8, h * 0.72) for a, ln, h in sp], r_in * 0.8, p=1.5,
                              twist=twist * 1.3, skew=skew)
            c.paint(mm & (relm + j < ms), V_LIGHT, order=0.75)
            hs = float(np.interp(f, [1, 2, 4], [0.8, 0.62, 0.42]))
            mh, relh = c.star(C, [(a + 0.03, ln * 0.62, h * 0.46) for a, ln, h in sp], r_in * 0.42, p=2.0,
                              twist=twist * 1.5)
            c.paint(mh & (relh + j * 0.6 < hs), V_HOT, order=1.0)
    else:
        # the break-up: every spike is now a leaf-shaped petal drifting out and curling
        hole = float(np.interp(f, [6, 8, 11, 14], [0.3, 0.44, 0.56, 0.66]))
        drift = float(np.interp(f, [6, 8, 11, 14], [0.06, 0.13, 0.2, 0.26]))
        curl = 0.12 + 0.03 * (f - 6)
        body, light, deep = [], [], []
        for i, (a, ln, h) in enumerate(spikes):
            r0 = R * hole * (0.9 + 0.2 * rng.random())
            r1 = ln * (1 + drift) * float(np.interp(f, [6, 8, 11, 14], [1.0, 0.98, 0.94, 0.9]))
            r0 = max(r0, r1 - (r1 - r0) * float(np.interp(f, [6, 8, 11, 14], [1.0, 0.9, 0.7, 0.5])))
            if r1 - r0 < R * 0.12:
                r1 = r0 + R * 0.12
            n = 16
            pts, wid = [], []
            wmax = 2 * (r0 + (r1 - r0) * 0.3) * math.sin(h * 0.55) * wmul
            for k in range(n):
                t = k / (n - 1)
                rr = r0 + (r1 - r0) * t
                aa = a + twist + curl * t * t
                pts.append((C[0] + math.cos(aa) * rr, C[1] + math.sin(aa) * rr))
                prof = math.sin(min(1.0, t / 0.32) * math.pi / 2) if t < 0.32 else (1 - (t - 0.32) / 0.68) ** 0.8
                wid.append(max(0.3, wmax * prof))
            body.append(tapered_path(pts, wid))
            m = n // 2
            light.append(tapered_path(pts[:m + 2], [w * 0.5 for w in wid[:m + 2]]))
            deep.append(tapered_path(pts[int(n * 0.72):], wid[int(n * 0.72):]))
        mb = c.ragged(c.polys(body), amp=0.6, freq=0.6)
        vb = V_BODY if f < 11 else V_DEEP
        c.paint(mb, vb, order=0.5)
        c.paint(c.polys(deep) & mb, V_DEEP, order=0.25)
        if f < 11:
            c.paint(c.polys(light) & mb, V_LIGHT if f == 6 else V_BODY, order=0.8)
    # satellite flecks beyond some spike tips
    if 1 <= f <= 11:
        polys = []
        frng = np.random.default_rng(seed + 7)
        for a, ln, h in spikes:
            if frng.random() < 0.6:
                aa = a + frng.uniform(-0.15, 0.15) + twist
                rr = ln * (1.1 + 0.035 * f) + frng.uniform(0, R * 0.1)
                Lf = R * frng.uniform(0.09, 0.16) * float(np.interp(f, [1, 11], [1.0, 0.55]))
                p = (C[0] + math.cos(aa) * rr, C[1] + math.sin(aa) * rr)
                polys.append(kite(p, (math.cos(aa), math.sin(aa)), Lf, Lf * 0.32, back=0.7))
        if polys:
            c.paint(c.polys(polys), V_LIGHT if f < 4 else (V_BODY if f < 8 else V_DEEP), order=0.15)
    return c.pack()


def petal(o, a, L, w, bulge=0.38, tip=0.0, n=14):
    """A leaf-shaped petal from the origin o along angle a: widest at `bulge` of its length."""
    d = (math.cos(a), math.sin(a))
    pts, wid = [], []
    for i in range(n):
        t = i / (n - 1)
        pts.append((o[0] + d[0] * L * t, o[1] + d[1] * L * t))
        k = t / bulge if t < bulge else (1 - t) / (1 - bulge)
        wid.append(w * (math.sin(min(1.0, k) * math.pi / 2) ** (0.7 if t < bulge else 1.3)) + tip)
    return tapered_path(pts, wid)


def paint_petals(c, o, petals, frame, split=0.0, cool=0):
    """petals = [(angle, length, width)]. Nested bands: body petal, light petal, hot core near o."""
    body, light, hot = [], [], []
    for a, L, w in petals:
        oo = (o[0] + math.cos(a) * L * split, o[1] + math.sin(a) * L * split)
        LL = L * (1 - split * 0.6)
        body.append(petal(oo, a, LL, w))
        light.append(petal(oo, a + 0.02, LL * 0.58, w * 0.4))
        hot.append(petal(oo, a, LL * 0.3, w * 0.2))
    vals = [(body, [V_BODY, V_BODY, V_DEEP, V_DEEP][cool]), (light, [V_LIGHT, V_LIGHT, V_BODY, V_DEEP][cool]),
            (hot, [V_HOT, V_HOT, V_LIGHT, V_BODY][cool])]
    for i, (polys, v) in enumerate(vals):
        m = c.polys(polys)
        if i == 0:
            m = c.ragged(m, amp=0.7, freq=0.6)
        c.paint(m, v, order=0.3 + 0.3 * i)


def core_star(c, o, r, v=V_HOT, n=4, a0=0.0, hw=0.35):
    sp = [(a0 + math.tau * i / n, r * (1.0 if i % 2 == 0 else 0.6), hw) for i in range(n)]
    m, _ = c.star(o, sp, r * 0.25, p=1.6)
    c.paint(m, v, order=1.0)


def forward_fan(f, seed, size=256, n=5, cone=0.55, belch=False):
    c = Cell(size, size, seed=seed + f)
    rng = np.random.default_rng(seed)
    o = (size * 0.3, size * 0.5)
    Lmax = size * 0.64
    if f == 0:
        core_star(c, o, size * 0.1, a0=0.0)
        return c.pack()
    base = []
    for i in range(n):
        k = (2 * i / (n - 1) - 1)
        a = k * cone + rng.uniform(-0.05, 0.05)
        L = Lmax * (1.0 - 0.42 * abs(k) ** 1.4) * rng.uniform(0.9, 1.05)
        w = L * (0.26 if belch else 0.2)
        base.append((a, L, w))
    # two short recoil petals backwards
    for s in (-1, 1):
        base.append((math.pi + s * 0.55, Lmax * 0.2, Lmax * 0.06))
    if f == 1:
        paint_petals(c, o, base, f)
        core_star(c, o, size * 0.07)
    elif f == 2:
        paint_petals(c, o, [(a, L * 1.05, w * 0.8) for a, L, w in base], f, split=0.16, cool=1)
    else:
        paint_petals(c, o, [(a, L * 1.08, w * 0.5) for a, L, w in base[:n]], f, split=0.45, cool=2)
    return c.pack()


def sunburst(f, seed, size=256, n=9, cone=0.46):
    c = Cell(size, size, seed=seed + f)
    rng = np.random.default_rng(seed)
    o = (size * 0.18, size * 0.5)
    Lmax = size * 0.78
    if f == 0:
        core_star(c, o, size * 0.08)
        return c.pack()
    wedges = []
    for i in range(n):
        k = 2 * i / (n - 1) - 1
        a = k * cone
        L = Lmax * (1.0 if i % 2 == 0 else 0.62) * rng.uniform(0.92, 1.04)
        wedges.append((a, L))
    split = {1: 0.0, 2: 0.18, 3: 0.5}[f]
    body, light = [], []
    for a, L in wedges:
        d = (math.cos(a), math.sin(a))
        nrm = (-d[1], d[0])
        oo = (o[0] + d[0] * L * split, o[1] + d[1] * L * split)
        LL = L * (1 - split * 0.55)
        w = LL * (0.085 if f < 3 else 0.05)
        body.append([(oo[0] + nrm[0] * w, oo[1] + nrm[1] * w), (oo[0] + d[0] * LL, oo[1] + d[1] * LL),
                     (oo[0] - nrm[0] * w, oo[1] - nrm[1] * w)])
        w2 = w * 0.32
        LL2 = LL * 0.7
        light.append([(oo[0] + nrm[0] * w2, oo[1] + nrm[1] * w2), (oo[0] + d[0] * LL2, oo[1] + d[1] * LL2),
                      (oo[0] - nrm[0] * w2, oo[1] - nrm[1] * w2)])
    c.paint(c.ragged(c.polys(body), 0.5, 0.8), V_BODY if f < 3 else V_DEEP, order=0.3)
    c.paint(c.polys(light), V_LIGHT if f < 3 else V_BODY, order=0.6)
    if f == 1:
        # the pointed white core
        c.paint(c.polys([kite(o, (1, 0), size * 0.2, size * 0.05, back=0.4)]), V_HOT, order=1.0)
    elif f == 2:
        c.paint(c.polys([kite(o, (1, 0), size * 0.12, size * 0.03, back=0.3)]), V_LIGHT, order=1.0)
    return c.pack()


def cross(f, seed, size=256):
    c = Cell(size, size, seed=seed + f)
    o = (size * 0.42, size * 0.5)
    L = size * 0.5
    grow = {0: 0.45, 1: 1.0, 2: 1.12, 3: 1.2}[f]
    thin = {0: 1.0, 1: 1.0, 2: 0.6, 3: 0.35}[f]
    main = [(0.0, L * grow, 0.2 * thin), (math.pi, L * 0.36 * grow, 0.22 * thin),
            (math.pi / 2, L * 0.55 * grow, 0.2 * thin), (-math.pi / 2, L * 0.55 * grow, 0.2 * thin)]
    diag = [(math.pi / 4 + k * math.pi / 2, L * 0.24 * grow, 0.16 * thin) for k in range(4)]
    m, rel = c.star(o, main + diag, L * 0.07, p=2.4)
    v = band_value(rel, (0.35 if f < 2 else 0.1, 0.62, 0.9), (V_HOT, V_LIGHT, V_BODY, V_DEEP))
    if f == 3:
        v = band_value(rel, (0.0, 0.3, 0.7), (V_HOT, V_LIGHT, V_BODY, V_DEEP))
        hole = c.polar(o)[0] < L * 0.22
        m &= ~hole
    c.paint(m, v, order=np.clip(1 - rel, 0, 1))
    return c.pack()


def inward_star(f, seed, size=256, n=7):
    """Void muzzle / implosion cue: the points aim at the core (f0-1), then flip out (f2), then fade."""
    c = Cell(size, size, seed=seed + f)
    rng = np.random.default_rng(seed)
    o = (size * 0.5, size * 0.5)
    R = size * 0.4
    a0 = rng.uniform(0, math.tau)
    if f in (0, 1):
        Ro = R * (1.0 if f == 0 else 0.78)
        polys, rims = [], []
        for i in range(n):
            a = a0 + math.tau * i / n + (0.06 if f else 0)
            d = (math.cos(a), math.sin(a))
            nrm = (-d[1], d[0])
            base = (o[0] + d[0] * Ro, o[1] + d[1] * Ro)
            w = Ro * 0.3
            tip_r = Ro * (0.3 if f == 0 else 0.14)
            tip = (o[0] + d[0] * tip_r, o[1] + d[1] * tip_r)
            outer = (o[0] + d[0] * Ro * 1.08, o[1] + d[1] * Ro * 1.08)
            polys.append([(base[0] + nrm[0] * w, base[1] + nrm[1] * w), outer,
                          (base[0] - nrm[0] * w, base[1] - nrm[1] * w), tip])
            rims.append([(base[0] + nrm[0] * w * 0.35, base[1] + nrm[1] * w * 0.35), tip,
                         (base[0] - nrm[0] * w * 0.35, base[1] - nrm[1] * w * 0.35)])
        c.paint(c.ragged(c.polys(polys), 0.8, 0.5), V_INK, order=0.4)
        c.paint(c.polys(rims), V_BODY, order=0.6)
        c.paint(c.dots([(o[0], o[1], R * (0.1 if f == 0 else 0.06))]), V_LIGHT if f == 0 else V_HOT, order=1.0)
    else:
        grow = 1.0 if f == 2 else 1.15
        sp = [(a0 + math.pi / n + math.tau * i / n, R * grow * (1.0 if i % 2 == 0 else 0.62), 0.24 if f == 2 else 0.14)
              for i in range(n)]
        ink = [(a + 0.1, ln * 1.18, h * 1.3) for a, ln, h in sp]
        mi, _ = c.star(o, ink, R * 0.3, p=1.6, twist=0.1)
        c.paint(c.ragged(mi, 1.0, 0.4), V_INK, order=0.3)
        m, rel = c.star(o, sp, R * 0.22, p=1.8, twist=0.1)
        if f == 3:
            m &= c.polar(o)[0] > R * 0.3
        v = band_value(rel, (0.3 if f == 2 else 0.0, 0.55, 0.85), (V_HOT, V_LIGHT, V_BODY, V_DEEP))
        c.paint(m, v, order=np.clip(1 - rel, 0, 1))
    return c.pack()


# ---- directional flashes (256 x 128 cells, the muzzle at the left) ------------------------------
def flicker3(f, seed, w=256, h=128):
    c = Cell(w, h, seed=seed + f)
    o = (w * 0.06, h * 0.5)
    L = w * 0.62
    if f == 0:
        core_star(c, o, h * 0.14)
        return c.pack()
    k = {1: 1.0, 2: 1.06, 3: 1.1}[f]
    petals = [(0.0, L * k, h * 0.2), (0.62, L * 0.42 * k, h * 0.14), (-0.62, L * 0.42 * k, h * 0.14)]
    paint_petals(c, o, petals, f, split={1: 0.0, 2: 0.2, 3: 0.5}[f], cool={1: 0, 2: 1, 3: 2}[f])
    if f == 1:
        core_star(c, o, h * 0.1)
    return c.pack()


def spike(f, seed, w=256, h=128):
    c = Cell(w, h, seed=seed + f)
    o = (w * 0.05, h * 0.5)
    L = w * 0.9
    if f == 0:
        core_star(c, o, h * 0.14)
        return c.pack()
    grow = {1: 1.0, 2: 1.04, 3: 1.06}[f]
    thin = {1: 1.0, 2: 0.6, 3: 0.35}[f]
    sp = [(0.0, L * grow, 0.07 * thin), (1.25, h * 0.3, 0.3 * thin), (-1.25, h * 0.3, 0.3 * thin),
          (math.pi, h * 0.16, 0.4 * thin)]
    m, rel = c.star(o, sp, h * 0.08, p=1.4)
    # the long spike is thin: band by rel on the angle-scaled field
    v = band_value(rel, (0.4 if f == 1 else 0.1, 0.7, 0.92), (V_HOT, V_LIGHT, V_BODY, V_DEEP))
    if f == 3:
        m &= c.X > o[0] + L * 0.25
    c.paint(m, v, order=np.clip(1 - rel, 0, 1))
    # the pressure wave: 2 thin cone lines
    if f in (1, 2):
        lines = []
        for s in (-1, 1):
            a = s * 0.2
            r0, r1 = L * (0.22 if f == 1 else 0.35), L * (0.55 if f == 1 else 0.72)
            p0 = (o[0] + math.cos(a) * r0, o[1] + math.sin(a) * r0)
            p1 = (o[0] + math.cos(a) * r1, o[1] + math.sin(a) * r1)
            lines.append(tapered_path([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1], [0.4, 2.6, 0.4]))
        c.paint(c.polys(lines), V_LIGHT if f == 1 else V_BODY, order=0.3)
    return c.pack()


def rail(f, seed, w=256, h=128):
    c = Cell(w, h, seed=seed + f)
    o = (w * 0.05, h * 0.5)
    L = w * 0.88
    if f == 0:
        core_star(c, o, h * 0.16)
        return c.pack()
    off = h * 0.13
    polys = []
    dash = f >= 2
    for s in (-1, 1):
        y = o[1] + s * off * (1 + 0.15 * (f - 1))
        if not dash:
            polys.append(tapered_path([(o[0] + 6, y), (o[0] + L * 0.5, y), (o[0] + L * 0.82, y)], [1.0, 4.4, 0.6]))
        else:
            rng = np.random.default_rng(seed + s)
            x = o[0] + 10 + (f - 2) * 20
            while x < o[0] + L * 0.85:
                ln = rng.uniform(14, 34) * (0.7 if f == 3 else 1.0)
                polys.append(tapered_path([(x, y), (x + ln / 2, y), (x + ln, y)], [0.5, 3.2 - f * 0.6, 0.5]))
                x += ln + rng.uniform(6, 18)
    c.paint(c.polys(polys), V_LIGHT if f == 1 else V_BODY, order=0.4)
    if f < 3:
        sp = [(0.0, L * (1.0 if f == 1 else 0.7), 0.06), (math.pi, h * 0.14, 0.3), (1.5, h * 0.22, 0.25),
              (-1.5, h * 0.22, 0.25)]
        m, rel = c.star(o, sp, h * 0.08, p=1.4)
        c.paint(m, band_value(rel, (0.45 if f == 1 else 0.15, 0.75, 0.95), (V_HOT, V_LIGHT, V_BODY, V_DEEP)),
                order=np.clip(1 - rel, 0, 1))
    return c.pack()


def bloom(f, seed, w=256, h=128):
    """Plaguebloom nozzle: petals open like a flower along the aim, then drop."""
    c = Cell(w, h, seed=seed + f)
    rng = np.random.default_rng(seed)
    o = (w * 0.06, h * 0.5)
    open_ = {0: 0.15, 1: 0.55, 2: 1.0, 3: 1.1}[f]
    n = 5
    polys_b, polys_l = [], []
    for i in range(n):
        k = 2 * i / (n - 1) - 1
        a = k * 1.1 * open_ + rng.uniform(-0.05, 0.05)
        L = h * (0.62 - 0.12 * abs(k)) * (0.7 + 0.3 * open_) * (1.15 if i == n // 2 else 1.0)
        W = L * 0.55
        drop = (0, 0) if f < 3 else (L * 0.25, h * 0.08 * (1 if k >= 0 else -1))
        oo = (o[0] + drop[0], o[1] + drop[1])
        polys_b.append(petal(oo, a, L, W, bulge=0.62))
        polys_l.append(petal(oo, a, L * 0.7, W * 0.45, bulge=0.6))
    c.paint(c.ragged(c.polys(polys_b), 0.6, 0.5), V_DEEP if f == 3 else V_BODY, order=0.4)
    c.paint(c.polys(polys_l), V_BODY if f == 3 else V_LIGHT, order=0.6)
    if f in (1, 2):
        # droplets thrown out along the aim
        drops = []
        for i in range(5 if f == 2 else 2):
            a = rng.uniform(-0.35, 0.35)
            r = h * rng.uniform(0.7, 1.4) * (1 if f == 2 else 0.7)
            drops.append((o[0] + math.cos(a) * r, o[1] + math.sin(a) * r, h * rng.uniform(0.03, 0.06)))
        c.paint(c.dots(drops), V_LIGHT, order=0.2)
    c.paint(c.dots([(o[0], o[1], h * 0.07)]), V_HOT if f < 3 else V_LIGHT, order=1.0)
    return c.pack()


def build():
    a = Atlas("vfx_impact_star", 8, 4, 256, 256, intended="banded impact stars: plain hits, blasts, kills, "
              "impact frames (ink backing = the same frame drawn with value 0.06, 1.3x, rotated 5-8 deg)")
    jobs = [(n, f, 40 + row * 13) for row, n in enumerate((4, 5, 7, 9)) for f in STAR_TIMES]
    for k, cell in enumerate(pmap(impact_star, jobs)):
        a.put(k % 8, k // 8, cell)
    for row, n in enumerate((4, 5, 7, 9)):
        a.seq(f"star{n}", row, 8, fps=30, pivot=(0.5, 0.5), frame_times_60=STAR_TIMES, radius_in_cell=0.78,
              ink_backing_frames=[0, 1, 2, 3, 4],
              intended={4: "crit / radiant hits, small precise hits", 5: "plain hits (0.3-0.6 m)",
                        7: "the layered-burst blast star at R", 9: "big blasts, elites, boss hits"}[n])
    a.save(fps=30)

    p = Atlas("vfx_petal_flash", 4, 4, 256, 256, intended="muzzle flashes, 4 frames: f0 core, f1 full, f2 break-up, "
              "f3 remnants (optional); forward = +u; rotate +-15 deg per shot")
    for i in range(4):
        p.put(i, 0, forward_fan(i, 11))
        p.put(i, 1, sunburst(i, 12))
        p.put(i, 2, cross(i, 13))
        p.put(i, 3, inward_star(i, 14))
    p.seq("forward_fan", 0, 4, fps=60, pivot=(0.3, 0.5), intended="heavy: colossus_cannon (5 petals, 1.0 m), "
          "thundercoil (4), gravemaw belch, pendulum 2-4 petals")
    p.seq("sunburst", 1, 4, fps=60, pivot=(0.18, 0.5), intended="spread: sunspike_shotgun wedges across the spread")
    p.seq("cross", 2, 4, fps=60, pivot=(0.42, 0.5), intended="radiant cross: seraph_lance prism, dawnbreaker, "
          "coin ting, precision glint")
    p.seq("inward_star", 3, 4, fps=60, pivot=(0.5, 0.5), intended="void: voidheart_singularity (points aim in "
          "f0-1, flip out f2), Collapsing Star / Void implosion cue")
    p.save(fps=60)

    d = Atlas("vfx_muzzle_directional", 4, 4, 256, 128, intended="long directional muzzle flashes, muzzle at "
              "u = 0.06, forward = +u")
    for i in range(4):
        d.put(i, 0, flicker3(i, 21))
        d.put(i, 1, spike(i, 22))
        d.put(i, 2, rail(i, 23))
        d.put(i, 3, bloom(i, 24))
    d.seq("flicker3", 0, 4, fps=60, pivot=(0.06, 0.5), intended="rapid: serpent_smg, coinshooter (small), "
          "Bullet Ballet pistols")
    d.seq("spike", 1, 4, fps=60, pivot=(0.05, 0.5), intended="precise: godsbane_rifle long spike + side spikes + "
          "pressure-wave lines")
    d.seq("rail", 2, 4, fps=60, pivot=(0.05, 0.5), intended="longstrider_rail / Piercing Comet: parallel rail "
          "lines + white spike")
    d.seq("petal_bloom", 3, 4, fps=30, pivot=(0.06, 0.5), intended="plaguebloom_sprayer nozzle petals, "
          "tidecaller droplet spray")
    d.save(fps=60)
    return [a, p, d]


if __name__ == "__main__":
    build()
