"""Effect recipes for the concept frames: the layered language of VFX_STYLE.md, painted."""
import math
import numpy as np
from vfxpaint import (K_ISO, Noise, Ramp, ribbon_field, blob_field, bolt_points, crescent, ellipse_field, flame_tongue, hx, kite,
                      norm, rand_spikes, ring, rot, soft, star, streak_poly, tapered_path)

INK = hx("#120A12")


def mixc(a, b, t):
    return np.asarray(a) * (1 - t) + np.asarray(b) * t


def light_spill(cv, c, rx, col, gain=1.0, ky=K_ISO, power=1.6):
    r = soft(cv, c, rx, rx * ky, power)
    if r:
        cv.light(r[0], r[1], col, gain)


def glow(cv, c, rx, col, gain=1.0, ky=1.0, power=2.2):
    r = soft(cv, c, rx, rx * ky, power)
    if r:
        cv.add(r[0], r[1], col, gain)


def impact_star(cv, c, size, ramp, rng, n=8, ink=True, ky=1.0, gain=1.4, core_gain=2.6, rotation=None,
                ink_scale=1.3, body=True, hw=0.2):
    a0 = rng.uniform(0, 6.28) if rotation is None else rotation
    sp = rand_spikes(rng, n, size, a0=a0, hw=hw)
    if ink:
        spi = [(a + 0.12, ln * ink_scale, h * 1.25) for a, ln, h in sp]
        r = star(cv, c, spi, size * 0.3 * ink_scale, ky=ky)
        if r:
            cv.over(r[0], r[1] * 0.92, ramp.ink)
    if body:
        r = star(cv, c, sp, size * 0.3, ky=ky)
        if r:
            sl, cov, core = r
            k = core[..., None]
            col = np.where(k > 0.5, ramp.hot * core_gain, np.where(k > 0.3, ramp.light * gain * 1.25,
                           np.where(k > 0.12, ramp.body * gain, ramp.deep * gain)))
            cv.over(sl, cov, col, bloom=0.45)
    else:
        spc = [(a, ln * 0.5, h * 0.9) for a, ln, h in sp]
        r = star(cv, c, spc, size * 0.18, ky=ky)
        if r:
            cv.over(r[0], r[1], ramp.hot * core_gain, bloom=1.0)


def sparks(cv, c, rng, n, r0, r1, ramp, width=2.2, dir=None, spread=math.pi, gain=2.0, ky=1.0, ink=False,
           gravity=0.0, hot_frac=0.5, hot=None, cool=None):
    polys_hot, polys_body, polys_ink = [], [], []
    for _ in range(n):
        if dir is None:
            a = rng.uniform(0, 2 * math.pi)
        else:
            a = math.atan2(dir[1], dir[0]) + rng.uniform(-spread, spread)
        rr0 = r0 * rng.uniform(0.7, 1.2)
        rr1 = r1 * rng.uniform(0.55, 1.15)
        v = (math.cos(a), math.sin(a) * ky)
        p0 = (c[0] + v[0] * rr0, c[1] + v[1] * rr0)
        p1 = (c[0] + v[0] * rr1, c[1] + v[1] * rr1 + gravity * (rr1 / max(r1, 1)) ** 2)
        w = width * rng.uniform(0.6, 1.3)
        poly = streak_poly(p1, p0, w, 0.0)
        if ink:
            polys_ink.append(streak_poly(p1, p0, w * 2.4, 0.0))
        (polys_hot if rng.random() < hot_frac else polys_body).append(poly)
    if polys_ink:
        r = cv.raster(polys=polys_ink)
        if r:
            cv.over(r[0], r[1] * 0.8, ramp.ink)
    for polys, col in ((polys_body, ramp.body if cool is None else cool), (polys_hot, ramp.light if hot is None else hot)):
        r = cv.raster(polys=polys)
        if r:
            cv.over(r[0], r[1], col * gain, bloom=0.8)


def shards(cv, c, rng, n, r0, r1, size, ramp, ky=K_ISO, lift=0.0, dark=None, edge=None, gain=1.0, spin=0.6):
    dark = ramp.deep if dark is None else dark
    edge = ramp.light if edge is None else edge
    bodies, edges = [], []
    for _ in range(n):
        a = rng.uniform(0, 2 * math.pi)
        rr = rng.uniform(r0, r1)
        p = (c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * ky - lift * rng.uniform(0.3, 1.0))
        d = rot((math.cos(a), math.sin(a) * ky), rng.uniform(-spin, spin))
        L = size * rng.uniform(0.6, 1.3)
        w = L * rng.uniform(0.28, 0.45)
        k = kite(p, d, L, w)
        bodies.append(k)
        edges.append([k[0], k[1], (k[1][0] * 0.55 + k[2][0] * 0.45, k[1][1] * 0.55 + k[2][1] * 0.45),
                      ((k[0][0] + k[2][0]) / 2, (k[0][1] + k[2][1]) / 2)])
    r = cv.raster(polys=bodies)
    if r:
        cv.over(r[0], r[1], dark)
    r = cv.raster(polys=edges)
    if r:
        cv.over(r[0], r[1], edge * gain, bloom=0.3 if gain > 1 else 0.0)


def smoke(cv, puffs, ramp, light_pt, alpha=0.92, rim=None, mid=None, seed=5, rim_gain=1.0, rough=0.24, ss=2):
    r = blob_field(cv, puffs, seed=seed, light_pt=light_pt, rough=rough, ss=ss)
    if not r:
        return
    sl, cov, tone = r
    rim = mixc(ramp.ink, ramp.body, 0.55) if rim is None else rim
    mid = mixc(ramp.ink, ramp.deep, 0.45) if mid is None else mid
    col = np.where((tone > 1.5)[..., None], rim * rim_gain, np.where((tone > 0.5)[..., None], mid, ramp.ink))
    cv.over(sl, cov * alpha, col, bloom=0.15 if rim_gain > 1 else 0.0)


def puff_ring(c, rng, n, R, r_min, r_max, ky=K_ISO, lift=0.0, ppm=32.0):
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
        rr = R * rng.uniform(0.75, 1.1)
        out.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * ky - lift * rng.uniform(0.4, 1.0),
                    rng.uniform(r_min, r_max)))
    return out


def scorch(cv, c, R, seed=2, alpha=0.6, ky=K_ISO, cracks=None, rng=None, crack_col=None):
    g = ellipse_field(cv, c, R * 1.35, R * 1.35 * ky, ss=2)
    if g:
        sl, X, Y, d, ss = g
        nz = Noise(seed)
        th = np.arctan2((Y - c[1]) / ky, X - c[0])
        n = nz((th + np.pi) * 3, d * 2, 3)
        edge = 0.72 + 0.5 * (n - 0.5)
        a = np.clip((edge - d) / 0.12, 0, 1) * (0.55 + 0.45 * nz(X * 0.08, Y * 0.08, 2))
        cv.darken(sl, cv.down(a.astype(np.float32), ss), alpha)
    if cracks and rng is not None:
        lines = []
        for i in range(cracks):
            a = 2 * math.pi * i / cracks + rng.uniform(-0.3, 0.3)
            p0 = (c[0] + math.cos(a) * R * 0.15, c[1] + math.sin(a) * R * 0.15 * ky)
            p1 = (c[0] + math.cos(a) * R * rng.uniform(0.7, 1.15), c[1] + math.sin(a) * R * rng.uniform(0.7, 1.15) * ky)
            lines.append((bolt_points(p0, p1, rng, jag=0.18, depth=3), 1.3))
        r = cv.raster(lines=lines)
        if r:
            cv.over(r[0], r[1], (crack_col if crack_col is not None else hx("#FF8A2A")) * 2.2, bloom=0.6)


def dust_ring(cv, c, R, thick, col, rng, alpha=0.85, ky=K_ISO, rim_col=None, rim_gain=2.0, seed=4, gaps=0.3):
    r = ring(cv, c, R, thick, ky=ky, seed=seed, gaps=gaps)
    if not r:
        return
    sl, cov, tt = r
    cv.over(sl, cov * alpha, col)
    if rim_col is not None:
        r2 = ring(cv, c, R + thick * 0.35, thick * 0.3, ky=ky, seed=seed, gaps=gaps + 0.08)
        if r2:
            cv.over(r2[0], r2[1], rim_col * rim_gain, bloom=0.5)


def smear(cv, c, R, a0, a1, width, ramp, seed=1, ky=K_ISO, rotation=0.0, ink=True, erode=0.75, gain=1.5,
          ink_offset=0.0, ink_scale=1.5, rim_gain=2.4, body=True, peak=0.72, ink_alpha=0.95, lead=0.62):
    """Hades-II slash: a long dark ink smear trailing behind, a bright blade only on the leading `lead` part."""
    span = a1 - a0
    if ink:
        r = crescent(cv, (c[0], c[1] + ink_offset), R - width * 0.18, a0 - 0.12 * span, a1 - 0.03 * span,
                     width * ink_scale, ky=ky, rotation=rotation, seed=seed + 11, erode=erode * 0.7, peak=peak - 0.05)
        if r:
            cv.over(r[0], r[1] * ink_alpha, ramp.ink)
            # a thin deep-tone lip on the ink's outer edge keeps it painted, not a hole
            cv.over(r[0], r[2] * ink_alpha * 0.8, ramp.deep * 1.1)
    if body:
        r = crescent(cv, c, R, a1 - lead * span, a1, width * 0.8, ky=ky, rotation=rotation, seed=seed, erode=erode,
                     peak=min(0.85, peak + 0.1), rim=0.3)
        if r:
            sl, cov, rimm, head = r
            col = mixc(ramp.body, ramp.light, np.clip(head, 0, 1)[..., None])
            cv.over(sl, cov * 0.95, col * gain, bloom=0.45)
            cv.over(sl, rimm, ramp.hot * rim_gain, bloom=0.9)


def bolt(cv, p0, p1, rng, ramp, width=2.5, branches=2, jag=0.22, gain=2.2, ink=True, depth=5, ink_w=3.0):
    main = bolt_points(p0, p1, rng, jag=jag, depth=depth)
    paths = [(main, width)]
    for _ in range(branches):
        i = rng.integers(len(main) // 5, max(len(main) // 5 + 1, len(main) * 4 // 5))
        s = main[i]
        d = norm((p1[0] - p0[0], p1[1] - p0[1]))
        d = rot(d, rng.uniform(0.5, 1.0) * (1 if rng.random() < 0.5 else -1))
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * rng.uniform(0.2, 0.4)
        e = (s[0] + d[0] * L, s[1] + d[1] * L)
        paths.append((bolt_points(s, e, rng, jag=jag * 1.2, depth=depth - 1), width * 0.55))
    if ink:
        r = cv.raster(lines=[(p, w * ink_w) for p, w in paths])
        if r:
            cv.over(r[0], r[1] * 0.85, ramp.ink)
    r = cv.raster(lines=[(p, w * 1.7) for p, w in paths])
    if r:
        cv.over(r[0], r[1], ramp.body * gain * 0.6, bloom=0.7)
    r = cv.raster(lines=[(p, w * 0.6) for p, w in paths])
    if r:
        cv.over(r[0], r[1], ramp.hot * gain * 1.3, bloom=1.0)
    return main


def strands(cv, pts, width, ramp, rng, n=4, gain=1.6, ink=True, ink_w=2.2, hot=True, ink_alpha=0.75,
            body_col=None):
    """A painterly trail: several tapered strands of different lengths along a path (head first)."""
    N = len(pts)
    body_col = ramp.body if body_col is None else body_col

    def sub(frac, off, w):
        m = max(2, int(N * frac))
        q = pts[:m]
        out = []
        for i, p in enumerate(q):
            a = q[max(0, i - 1)]
            b = q[min(m - 1, i + 1)]
            d = norm((b[0] - a[0], b[1] - a[1]))
            nn = (-d[1], d[0])
            t = i / (m - 1)
            o = off * (0.3 + 0.7 * t)
            out.append((p[0] + nn[0] * o, p[1] + nn[1] * o))
        ws = [w * (1 - i / (m - 1)) ** 0.8 + 0.3 for i in range(m)]
        return tapered_path(out, ws)

    if ink:
        r = cv.raster(polys=[sub(1.0, 0, width * ink_w)])
        if r:
            cv.over(r[0], r[1] * ink_alpha, ramp.ink)
    polys = [sub(rng.uniform(0.5, 1.0), rng.uniform(-width * 0.5, width * 0.5), width * rng.uniform(0.35, 0.7))
             for _ in range(n)]
    r = cv.raster(polys=polys)
    if r:
        cv.over(r[0], r[1], body_col * gain, bloom=0.5)
    if hot:
        r = cv.raster(polys=[sub(0.45, 0, width * 0.35)])
        if r:
            cv.over(r[0], r[1], ramp.hot * gain * 1.6, bloom=0.9)


def muzzle_flash(cv, p, d, size, ramp, rng, petals=5, cone=0.55, gain=1.8, ink=True, back=True):
    a = math.atan2(d[1], d[0])
    sp = []
    for i in range(petals):
        t = 2 * i / max(1, petals - 1) - 1
        ln = size * (1.0 - 0.45 * abs(t)) * rng.uniform(0.85, 1.15)
        sp.append((a + cone * t, ln, 0.28))
    if back:
        sp += [(a + math.pi / 2 + 0.3, size * 0.35, 0.3), (a - math.pi / 2 - 0.3, size * 0.35, 0.3)]
    if ink:
        r = star(cv, p, [(aa + 0.05, ln * 1.25, h * 1.3) for aa, ln, h in sp], size * 0.3)
        if r:
            cv.over(r[0], r[1] * 0.85, ramp.ink)
    r = star(cv, p, sp, size * 0.25)
    if r:
        sl, cov, core = r
        col = np.where((core > 0.4)[..., None], ramp.light, ramp.body)
        cv.over(sl, cov, col * gain, bloom=0.6)
    r = star(cv, p, [(aa, ln * 0.5, h) for aa, ln, h in sp], size * 0.16)
    if r:
        cv.over(r[0], r[1], ramp.hot * gain * 1.5, bloom=1.0)


def motes(cv, pts, r, col, gain=2.4, ink=None):
    if ink is not None:
        q = cv.raster(dots=[(x, y, r * 2.0) for x, y in pts])
        if q:
            cv.over(q[0], q[1] * 0.7, ink)
    q = cv.raster(dots=[(x, y, r) for x, y in pts])
    if q:
        cv.over(q[0], q[1], col * gain, bloom=1.0)


def diamond_glints(cv, pts, size, col, gain=2.6):
    polys = []
    for x, y in pts:
        s = size
        polys.append([(x, y - s), (x + s * 0.22, y), (x, y + s), (x - s * 0.22, y)])
        polys.append([(x - s * 0.7, y), (x, y + s * 0.16), (x + s * 0.7, y), (x, y - s * 0.16)])
    r = cv.raster(polys=polys)
    if r:
        cv.over(r[0], r[1], col * gain, bloom=1.0)


def ring_accent(cv, c, R, thick, col, gain=1.8, ky=K_ISO, gaps=0.45, seed=9, alpha=1.0):
    r = ring(cv, c, R, thick, ky=ky, seed=seed, gaps=gaps)
    if r:
        cv.over(r[0], r[1] * alpha, col * gain, bloom=0.7)


def flames(cv, bases, H, W, ramp, rng, gain=1.5, ink=True, lean=0.0, leans=None, core_k=0.36):
    outer, mid, core, inks = [], [], [], []
    for j, b in enumerate(bases):
        h = H * rng.uniform(0.5, 1.3)
        w = W * rng.uniform(0.7, 1.2)
        ln = (lean if leans is None else leans[j]) + rng.uniform(-0.15, 0.15)
        seed_state = rng.bit_generator.state
        outer.append(flame_tongue(b, h, w, rng, lean=ln))
        rng.bit_generator.state = seed_state
        inks.append(flame_tongue((b[0], b[1] + 1), h * 1.08, w * 1.35, rng, lean=ln))
        rng.bit_generator.state = seed_state
        mid.append(flame_tongue((b[0], b[1] - h * 0.02), h * 0.68, w * 0.6, rng, lean=ln))
        rng.bit_generator.state = seed_state
        core.append(flame_tongue((b[0], b[1] - h * 0.02), h * core_k, w * 0.3, rng, lean=ln))
    if ink:
        r = cv.raster(polys=inks)
        if r:
            cv.over(r[0], r[1] * 0.85, ramp.ink)
    for polys, col, g in ((outer, ramp.body, gain * 0.8), (mid, ramp.light, gain), (core, ramp.hot, gain * 1.4)):
        r = cv.raster(polys=polys)
        if r:
            cv.over(r[0], r[1], col * g, bloom=0.6)


def speed_lines(cv, c, rng, n, r0, r1, col, width=1.6, gain=1.5, alpha=0.8):
    polys = []
    for _ in range(n):
        a = rng.uniform(0, 2 * math.pi)
        p0 = (c[0] + math.cos(a) * r0 * rng.uniform(0.9, 1.3), c[1] + math.sin(a) * r0 * rng.uniform(0.9, 1.3))
        p1 = (c[0] + math.cos(a) * r1 * rng.uniform(0.8, 1.1), c[1] + math.sin(a) * r1 * rng.uniform(0.8, 1.1))
        polys.append(streak_poly(p1, p0, width * rng.uniform(0.7, 1.4), 0.0, cap=False))
    r = cv.raster(polys=polys)
    if r:
        cv.over(r[0], r[1] * alpha, col * gain, bloom=0.2)


def ellipse_poly(c, d, a, b, n=24):
    d = norm(d)
    nn = (-d[1], d[0])
    return [(c[0] + d[0] * a * math.cos(t) + nn[0] * b * math.sin(t),
             c[1] + d[1] * a * math.cos(t) + nn[1] * b * math.sin(t)) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]


def ground_dust(cv, c, R, rng, n, r_min, r_max, col_dark, col_lit, light_pt, alpha=0.8, ky=K_ISO, seed=17):
    """Low dust puffs kicked out along the ground at radius R: the painterly shockwave."""
    puffs = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.2, 0.2)
        rr = R * rng.uniform(0.9, 1.05)
        puffs.append((c[0] + math.cos(a) * rr, c[1] + math.sin(a) * rr * ky - r_max * 0.3, rng.uniform(r_min, r_max)))
    r = blob_field(cv, puffs, seed=seed, light_pt=light_pt, rough=0.12)
    if not r:
        return
    sl, cov, tone = r
    col = np.where((tone > 1.5)[..., None], col_lit, col_dark)
    cv.over(sl, cov * alpha, col)


def smoke_trail(cv, pts, r0, r1, ramp, rng, alpha0=0.8, alpha1=0.2, light_dir=(-0.45, -0.9), rim=None, seed=61,
                segs=4):
    """Continuous puff trail along pts (head first): puffs grow and thin with age."""
    rim = fx_rim(ramp) if rim is None else rim
    n = len(pts)
    for s in range(segs):
        i0 = int(n * s / segs)
        i1 = int(n * (s + 1) / segs)
        puffs = []
        for i in range(i0, i1, 2):
            t = i / max(1, n - 1)
            rr = r0 + (r1 - r0) * t
            puffs.append((pts[i][0] + rng.uniform(-1.5, 1.5) * rr * 0.2, pts[i][1] + rng.uniform(-1.5, 1.5) * rr * 0.2,
                          rr * rng.uniform(0.8, 1.15)))
        if not puffs:
            continue
        a = alpha0 + (alpha1 - alpha0) * (s + 0.5) / segs
        r = blob_field(cv, puffs[::-1], seed=seed + s, light_dir=norm(light_dir), rough=0.14)
        if r:
            sl, cov, lit = r
            col = np.where((lit > 1.5)[..., None], rim, np.where((lit > 0.5)[..., None],
                                                                 mixc(ramp.ink, ramp.deep, 0.5), ramp.ink))
            cv.over(sl, cov * a, col)


def fx_rim(ramp):
    return mixc(ramp.deep, ramp.light, 0.45)


def ribbon(cv, pts, widths, cols, alpha=1.0, fade=0.9, erode=0.0, seed=71, bloom=0.3, bands=None, ss=2):
    """Fill a ribbon (head first). cols: one colour, or a list of (s_threshold, colour) across bands from
    the centre out. Alpha fades toward the tail; erode breaks the tail into dry-brush streaks."""
    r = ribbon_field(cv, pts, widths, ss=ss)
    if not r:
        return
    sl, X, Y, inside, t, s, ss = r
    a = inside.astype(np.float32) * (1 - fade * t)
    if erode > 0:
        nz = Noise(seed)
        n = nz(t * 6, np.abs(s) * 5 + 3, 3)
        a = a * (n > erode * t ** 1.3)
    cov = cv.down(a, ss)
    if isinstance(cols, list):
        acc = np.zeros(cov.shape + (3,), np.float32)
        sa = cv.down(np.abs(s) * inside, ss) / np.maximum(cv.down(inside.astype(np.float32), ss), 1e-3)
        col = None
        for thr, c in sorted(cols, key=lambda q: -q[0]):
            col = np.where((sa <= thr)[..., None], np.asarray(c), acc if col is None else col)
        cv.over(sl, cov * alpha, col, bloom=bloom)
    else:
        cv.over(sl, cov * alpha, cols, bloom=bloom)
