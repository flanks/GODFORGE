"""Smoke puffs, sparks / shards / droplets / motes, and flame tongues (VFX_STYLE sections 2, 4, 11).

  atlas/vfx_smoke_puff.png     8 silhouettes x 4 ages, 256 px cells, lit from +v up (rotate the quad so
                               the cell's top faces the light: the blast core, the fire)
  atlas/vfx_sparks_shards.png  8 spark streaks, 8 shard kites, 4 teardrops, 4 coin frames, 4 glints and
                               4 element motes (ember, spore, hex, ash), 128 px cells
  atlas/vfx_flame_tongue.png   8-frame loops: narrow, medium, clump, licks; 128 x 256 cells, base at the
                               bottom centre
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, kite, pmap, tapered_path, streak_poly)

PUFF_VARIANTS = ["round", "wide", "column", "lean_left", "lean_right", "tight", "billow", "wisp"]
PUFF_AGES = [0, 1, 2, 3]


def smoke_puff(variant, age, seed, size=256):
    c = Cell(size, size, seed=seed * 31 + age)
    rng = np.random.default_rng(seed)
    cx, cy = size / 2, size * 0.53
    R = size * 0.34
    k = [1.0, 1.13, 1.24, 1.32][age]
    name = PUFF_VARIANTS[variant]
    if name == "round":
        lobes = P.cumulus(rng, cx, cy, R, n=6)
    elif name == "wide":
        lobes = P.cumulus(rng, cx, cy + R * 0.15, R * 1.05, n=8, flat=0.7)
    elif name == "column":
        lobes = P.cumulus(rng, cx, cy + R * 0.1, R * 0.82, n=7, tall=0.75)
    elif name == "lean_left":
        lobes = P.cumulus(rng, cx + R * 0.1, cy, R, n=6, lean=-0.9)
    elif name == "lean_right":
        lobes = P.cumulus(rng, cx - R * 0.1, cy, R, n=6, lean=0.9)
    elif name == "tight":
        lobes = P.cumulus(rng, cx, cy, R * 0.72, n=4, spread=0.7)
    elif name == "billow":
        lobes = P.cumulus(rng, cx, cy, R * 1.08, n=10, spread=1.1)
    else:  # wisp: a horizontal trail of shrinking lobes
        lobes = []
        for i in range(6):
            t = i / 5
            lobes.append((cx - R * 1.0 + t * R * 2.0, cy + math.sin(t * 5 + seed) * R * 0.08, R * (0.5 - 0.3 * t)))
        lobes.sort(key=lambda l: l[2])
    # grow about the base as it ages, lift a little
    lobes = [(cx + (x - cx) * k, cy + (y - cy) * k - R * 0.06 * age, r * k * (1 - 0.04 * age)) for x, y, r in lobes]
    v_rim = [V_LIGHT, V_LIGHT, V_BODY, V_DEEP][age]
    v_mid = [V_DEEP, V_DEEP, V_DEEP, V_INK][age]
    rim = [0.26, 0.2, 0.17, 0.14][age]
    mid = [0.72, 0.66, 0.58, 0.4][age]
    P.puff_cluster(c, lobes, light=(0.0, -1.0), rim=rim, mid=mid, v_rim=v_rim, v_mid=v_mid, rough=0.2 + 0.05 * age,
                   seed_off=seed)
    if age >= 1:
        # the puff opens up: holes eat in from the edge
        din = c.inside_dist(c.cov)
        dn = np.clip(din / (R * 0.5), 0, 1)
        n = c.nz(c.X * 0.12 + seed, c.Y * 0.12)
        thr = [0, 0.93, 0.78, 0.6][age]
        c.erase(c.cov & (n + (1 - dn) * 0.35 > thr + 0.35))
    if age >= 2:
        # torn-off mini puffs drift above
        bits = []
        for i in range(2 + age):
            a = rng.uniform(math.pi * 1.15, math.pi * 1.85)
            rr = R * k * rng.uniform(0.95, 1.15)
            bits.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr - R * 0.1, R * rng.uniform(0.07, 0.13)))
        P.puff_cluster(c, bits, rim=0.3, mid=0.7, v_rim=v_rim, v_mid=v_mid, rough=0.25, order0=0.1, order1=0.2,
                       seed_off=seed + 50)
    return c.pack()


# ---- 128 px particles ----------------------------------------------------------------------------
def spark_cell(i, seed, s=128):
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    y = s / 2
    kinds = [(0.86, 5.0, 0.0), (0.6, 7.0, 0.0), (0.9, 3.2, 0.0), (0.5, 9.0, 0.0), (0.8, 5.0, 0.16), (0.8, 5.0, -0.16),
             (0.7, 4.0, 0.0), (0.4, 6.0, 0.0)]
    Lr, w, bend = kinds[i]
    x1 = s * 0.9
    x0 = x1 - s * Lr * 0.85
    pts = [(x0 + (x1 - x0) * t, y + bend * s * (1 - t) ** 2 * 1.0) for t in np.linspace(0, 1, 12)]
    wid = [w * (0.05 + 0.95 * t ** 1.3) for t in np.linspace(0, 1, 12)]
    body = tapered_path(pts, wid)
    c.paint(c.polys([body]), V_BODY, order=0.2)
    c.paint(c.polys([tapered_path(pts[5:], [ww * 0.7 for ww in wid[5:]])]), V_LIGHT, order=0.5)
    c.paint(c.dots([(pts[-1][0] - w * 0.2, pts[-1][1], w * 0.42)]), V_HOT, order=1.0)
    if i == 6:  # a double spark: a small satellite
        c.paint(c.polys([streak_poly((x1 - s * 0.4, y + 9), (x1 - s * 0.62, y + 11), 3.2, 0)]), V_LIGHT, order=0.3)
    if i == 7:  # a chunky ember spark with an ink edge
        m = c.polys([body])
        grow = c.ragged(m, 1.4, 0.4)
        c.paint(grow & ~m, V_INK, order=0.1)
    # B: the tail erodes first
    return c.pack(ero=np.clip((c.X - x0) / (x1 - x0), 0.02, 1.0) * 0.8 + 0.2 * c.nz(c.X * 0.5, c.Y * 0.5))


def shard_cell(i, seed, s=128):
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    C = (s / 2, s / 2)
    props = [(0.42, 0.34, 0.45), (0.38, 0.22, 0.3), (0.3, 0.3, 0.6), (0.44, 0.16, 0.25), (0.34, 0.4, 0.7),
             (0.4, 0.26, 0.2), (0.28, 0.2, 0.5), (0.46, 0.2, 0.55)]
    Lr, wr, back = props[i]
    a = rng.uniform(-0.5, 0.5) - 0.6
    d = (math.cos(a), math.sin(a))
    L = s * Lr
    p = (C[0] - d[0] * L * (0.5 - back * 0.5), C[1] - d[1] * L * (0.5 - back * 0.5))
    k, facet = P.shard_polys(p, d, L, L * wr, back=back)
    if i % 3 == 1:  # a chipped kite: one extra notch
        k = k[:2] + [((k[1][0] + k[2][0]) / 2 + d[1] * 4, (k[1][1] + k[2][1]) / 2 - d[0] * 4)] + k[2:]
    m = c.polys([k])
    ink = c.ragged(m, 1.2, 0.3) | m
    grow = c.sdf(ink) > -1.6
    c.paint(grow, V_INK, order=0.2)
    c.paint(m, V_DEEP, order=0.5)
    c.paint(c.polys([facet]) & m, V_LIGHT, order=0.7)
    c.paint(c.dots([(k[0][0] - d[0] * 3, k[0][1] - d[1] * 3, 2.2)]) & m, V_HOT, order=0.9)
    return c.pack()


def drop_cell(i, seed, s=128):
    c = Cell(s, s, seed=seed + i)
    C = (s * 0.62, s / 2)
    r, st = [(14, 2.4), (11, 3.4), (17, 1.6), (9, 4.4)][i]
    body = P.teardrop(C, (1, 0), r, r * st)
    m = c.polys([body])
    c.paint(c.sdf(m) > -1.5, V_INK, order=0.2)
    c.paint(m, V_BODY, order=0.5)
    c.paint(c.polys([P.teardrop((C[0] + r * 0.2, C[1] - r * 0.3), (1, 0), r * 0.38, r * 0.9)]), V_LIGHT, order=0.8)
    c.paint(c.dots([(C[0] + r * 0.35, C[1] - r * 0.38, r * 0.16)]), V_HOT, order=1.0)
    return c.pack(ero=np.clip((c.X - (C[0] - r * st)) / (r * st + r), 0.02, 1) * 0.8 + 0.2 * c.nz(c.X, c.Y))


def coin_cell(i, seed, s=128):
    """Coin spin frames: face-on, three-quarter, edge-on, glint."""
    c = Cell(s, s, seed=seed + i)
    C = (s / 2, s / 2)
    R = s * 0.3
    if i < 3:
        sx = [1.0, 0.55, 0.12][i]
        outer = c.ellipse(C, R * sx + 0.8, R)
        c.paint(c.sdf(outer) > -1.6, V_INK, order=0.2)
        c.paint(outer, V_DEEP, order=0.4)
        inner = c.ellipse((C[0] - R * sx * 0.06, C[1] - R * 0.04), R * sx * 0.78, R * 0.78)
        c.paint(inner, V_BODY, order=0.6)
        if i < 2:
            # a stamped mark and a lit crescent
            lit = inner & ~c.ellipse((C[0] + R * sx * 0.18, C[1] + R * 0.16), R * sx * 0.8, R * 0.8)
            c.paint(lit, V_LIGHT, order=0.8)
            mark = c.polys([kite((C[0], C[1] + R * 0.25), (0, -1), R * 0.5, R * sx * 0.2, back=0.1)])
            c.paint(mark & inner, V_DEEP, order=0.7)
        else:
            c.paint(c.ellipse(C, R * sx * 0.4, R * 0.9), V_LIGHT, order=0.8)
    else:
        sp = [(0, R * 1.3, 0.2), (math.pi / 2, R * 1.3, 0.2), (math.pi, R * 1.3, 0.2), (-math.pi / 2, R * 1.3, 0.2)]
        sp += [(math.pi / 4 + k * math.pi / 2, R * 0.5, 0.25) for k in range(4)]
        m, rel = c.star(C, sp, R * 0.3, p=2.2)
        c.paint(m, np.where(rel < 0.45, V_HOT, V_LIGHT), order=0.5)
    return c.pack()


def glint_cell(i, seed, s=128):
    c = Cell(s, s, seed=seed + i)
    C = (s / 2, s / 2)
    R = s * 0.4
    if i == 0:
        sp = [(k * math.pi / 2, R * (1.0 if k % 2 == 0 else 0.62), 0.2) for k in range(4)]
    elif i == 1:
        sp = [(k * math.pi / 2, R * 0.55, 0.42) for k in range(4)]
    elif i == 2:
        sp = [(k * math.pi / 4, R * (1.0 if k % 2 == 0 else 0.45), 0.24) for k in range(8)]
    else:
        sp = [(0.3, R, 0.2), (0.3 + math.pi, R * 0.5, 0.25), (0.3 + math.pi / 2, R * 0.4, 0.3), (0.3 - math.pi / 2, R * 0.7, 0.22)]
    m, rel = c.star(C, sp, R * 0.1, p=2.0)
    c.paint(c.sdf(m) > -1.4, V_INK, order=0.2)
    c.paint(m, np.where(rel < 0.35, V_HOT, np.where(rel < 0.7, V_LIGHT, V_BODY)), order=np.clip(1 - rel, 0, 1))
    return c.pack()


def mote_cell(i, seed, s=128):
    """Element secondary motes: ember (Flame), spore (Plague), hex (Void), ash flake (smoke / Kinetic)."""
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    C = (s / 2, s / 2)
    if i == 0:  # ember: a hot kernel with a short flicker tail (upwards)
        body = tapered_path([(C[0], C[1] + 30), (C[0] + 3, C[1] + 10), (C[0], C[1] - 12)], [0.5, 9, 14])
        m = c.ragged(c.polys([body]) | c.dots([(C[0], C[1] - 12, 9)]), 1.0, 0.5)
        c.paint(c.sdf(m) > -1.5, V_INK, order=0.1)
        c.paint(m, V_BODY, order=0.4)
        c.paint(c.dots([(C[0] + 0.5, C[1] - 11, 6)]), V_LIGHT, order=0.7)
        c.paint(c.dots([(C[0] + 1, C[1] - 12, 3.2)]), V_HOT, order=1.0)
    elif i == 1:  # spore: round-ish, dark core, bright rim on the lit side
        m = c.ragged(c.dots([(C[0], C[1], 20)]), 1.4, 0.35)
        c.paint(c.sdf(m) > -1.5, V_INK, order=0.1)
        c.paint(m, V_BODY, order=0.4)
        c.paint(c.dots([(C[0] + 3, C[1] + 3, 12)]) & m, V_DEEP, order=0.6)
        c.paint(c.dots([(C[0] + 5, C[1] + 5, 6)]), V_INK, order=0.8)
        c.paint(m & ~c.dots([(C[0] + 4, C[1] + 5, 19)]), V_LIGHT, order=0.9)
    elif i == 2:  # hex mote: a small hex diamond with an ink core
        pts = [(C[0] + math.cos(a) * 22 * (1.0 if k % 3 == 0 else 0.72), C[1] + math.sin(a) * 22 * 1.25)
               for k, a in enumerate(np.linspace(0, math.tau, 7)[:-1] + math.pi / 2)]
        m = c.polys([pts])
        c.paint(c.sdf(m) > -1.6, V_INK, order=0.1)
        c.paint(m, V_BODY, order=0.4)
        inner = [(C[0] + (x - C[0]) * 0.55, C[1] + (y - C[1]) * 0.55) for x, y in pts]
        c.paint(c.polys([inner]), V_INK, order=0.6)
        c.paint(c.polys([[pts[0], pts[1], inner[1], inner[0]]]), V_LIGHT, order=0.8)
    else:  # ash flake: an irregular dark flake with a lit edge
        pts = []
        for k in range(7):
            a = math.tau * k / 7 + rng.uniform(-0.25, 0.25)
            r = rng.uniform(14, 26)
            pts.append((C[0] + math.cos(a) * r * 1.3, C[1] + math.sin(a) * r * 0.7))
        m = c.ragged(c.polys([pts]), 1.0, 0.6)
        c.paint(m, V_INK, order=0.3)
        lit = m & ~c.polys([[(x + 2, y + 4) for x, y in pts]])
        c.paint(lit, V_DEEP, order=0.6)
    return c.pack()


# ---- flames --------------------------------------------------------------------------------------
FLAME_ROWS = ["narrow", "medium", "clump", "licks"]


def flame_cell(row, i, seed, w=128, h=256):
    c = Cell(w, h, seed=seed + row * 10 + i)
    ph = math.tau * i / 8
    base = (w / 2, h - 10)
    kind = FLAME_ROWS[row]
    flick = 1 + 0.07 * math.sin(2 * ph) + 0.04 * math.sin(3 * ph + 1)
    if kind == "narrow":
        P.paint_tongue(c, base, h * 0.8 * flick, w * 0.36, ph, lean=0.0, curl=0.45, tip_curl=0.6)
        frag = ((i / 8.0 + 0.1) % 1.0)
        fy = base[1] - h * (0.8 + 0.14 * frag)
        if frag < 0.75:
            fr = tapered_path([(base[0] + 8 * math.sin(ph), fy + 14), (base[0] + 6 * math.sin(ph + 1), fy),
                               (base[0] + 10 * math.sin(ph + 2), fy - 16)], [0.5, 9 * (1 - frag), 0.5])
            c.paint(c.polys([fr]), V_BODY, order=0.2)
    elif kind == "medium":
        P.paint_tongue(c, base, h * 0.7 * flick, w * 0.5, ph, lean=0.0, curl=0.35, tip_curl=0.5)
        P.paint_tongue(c, (base[0] + 14, base[1] - 4), h * 0.4 * (2 - flick), w * 0.26, ph + 2.0, curl=0.5,
                       vals=(V_BODY, V_LIGHT, None))
    elif kind == "clump":
        for k, (dx, hh, ww, dph) in enumerate([(-26, 0.5, 0.36, 1.3), (24, 0.55, 0.36, 2.6), (0, 0.78, 0.52, 0.0)]):
            ff = 1 + 0.08 * math.sin(2 * ph + dph * 2)
            P.paint_tongue(c, (base[0] + dx, base[1] - 2), h * hh * ff, w * ww, ph + dph, curl=0.38,
                           lean=0.12 * np.sign(dx), order=0.3 + 0.2 * k)
    else:  # licks: short, fast
        for k, (dx, hh, ww, dph) in enumerate([(-22, 0.3, 0.3, 0.9), (20, 0.36, 0.3, 2.2), (0, 0.44, 0.4, 0.0)]):
            ff = 1 + 0.18 * math.sin(2 * ph + dph * 3)
            P.paint_tongue(c, (base[0] + dx, base[1] - 2), h * hh * ff, w * ww, 2 * ph + dph, curl=0.55,
                           tip_curl=0.8, order=0.3 + 0.2 * k)
    # B: the tip erodes first (tongues burn out from the top down)
    ero = np.clip((c.Y - h * 0.08) / (h * 0.92), 0.02, 1.0) * 0.75 + 0.25 * c.nz(c.X * 0.3, c.Y * 0.3)
    return c.pack(ero=ero)


def build():
    a = Atlas("vfx_smoke_puff", 8, 4, 256, 256, intended="smoke and dust puffs: explosion crowns, muzzle smoke, "
              "trails, dust walls; rotate so +v up faces the light (the blast core); cool the value with age")
    jobs = [(v, age, 70 + v) for age in PUFF_AGES for v in range(8)]
    for k, cell in enumerate(pmap(smoke_puff, jobs)):
        a.put(k % 8, k // 8, cell)
    for age in PUFF_AGES:
        a.seq(f"age{age}", age, 8, fps=None, pivot=(0.5, 0.53), variants=PUFF_VARIANTS, radius_in_cell=0.68,
              intended=["young puff: dense, strong rim (f2-8)", "grown (f8-16)", "opening, rim cools (f16-28)",
                        "last wisps (f28-40)"][age])
    a.save(fps=None, note="a puff is one silhouette (column) played through its 4 ages (rows), or aged with B")

    s = Atlas("vfx_sparks_shards", 8, 4, 128, 128, intended="secondary particles, one sprite each")
    jobs = [(spark_cell, (i, 300)) for i in range(8)] + [(shard_cell, (i, 400)) for i in range(8)] + \
           [(drop_cell, (i, 500)) for i in range(4)] + [(coin_cell, (i, 600)) for i in range(4)] + \
           [(glint_cell, (i, 700)) for i in range(4)] + [(mote_cell, (i, 800)) for i in range(4)]
    cells = pmap(_call2, [(fn, args) for fn, args in jobs])
    for k, cell in enumerate(cells):
        s.put(k % 8, k // 8, cell)
    s.seq("spark", 0, 8, pivot=(0.9, 0.5), intended="spark streaks, head at +u (hot); stretch along velocity")
    s.seq("shard", 1, 8, pivot=(0.5, 0.5), intended="shard kites: shrapnel, obsidian, plate breaks, crystals")
    s.seq("teardrop", 2, 4, pivot=(0.62, 0.5), intended="droplets: plague, ichor, bleed, water; head at +u")
    s.seq("coin", 2, 4, col0=4, fps=15, loop=True, pivot=(0.5, 0.5), intended="coin spin: face, 3/4, edge, glint")
    s.seq("glint", 3, 4, pivot=(0.5, 0.5), intended="4-point glints: radiant motes, seeker glints, ting")
    s.seq("mote", 3, 4, col0=4, pivot=(0.5, 0.5), intended="element motes: ember (flame), spore (plague), hex (void), "
          "ash flake (smoke)", names=["ember", "spore", "hex", "ash"])
    s.save()

    f = Atlas("vfx_flame_tongue", 8, 4, 128, 256, intended="flame tongues: burning ground, Flame impacts, "
              "Meltdown fists, burn status, geysers; base at the bottom centre")
    jobs = [(r, i, 900) for r in range(4) for i in range(8)]
    for k, cell in enumerate(pmap(flame_cell, jobs)):
        f.put(k % 8, k // 8, cell)
    for r, name in enumerate(FLAME_ROWS):
        f.seq(name, r, 8, fps=12 if name != "licks" else 16, loop=True, pivot=(0.5, 0.96),
              intended={"narrow": "a single tall tongue (geysers, Meltdown fists)", "medium": "burning ground, burn "
                        "patches", "clump": "flame clusters (Flame impacts, Blightburn, fields)",
                        "licks": "short licks: burn status, beam edge crackle"}[name])
    f.save(fps=12)
    return [a, s, f]


def _call2(fn, args):
    return fn(*args)


if __name__ == "__main__":
    build()
