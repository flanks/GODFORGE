"""Billboard projectile bodies, charge cues and ring bands (VFX_STYLE sections 6, 7.2, 15.2, 16, 18).

  atlas/vfx_bodies.png  128 px cells, head / forward = +u:
      row 0  orb loop (8): ink core disc, light-facing rim crescent, white pin, surface crackles (Thundercoil,
             Sundial)
      row 1  globe loop (8): a heavy wobbling blob with an inner swirl and drips (Gravemaw, Voidheart, Plaguebloom)
      row 2  enemy shot (4-frame flicker: magenta core, pink rim, ink shell, thin pale outer edge), needle sliver,
             pellet diamond, bolt kite, slug head
      row 3  charge core stages (ink dot -> body disc -> hot pin -> release glint), charge ring tightening (4)
  trails/vfx_bands.png  tileable ring bands for meshes/vfx_ring_*.glb (1024 x 64 rows): dust wall, shock front,
                        Still Field tick ring (one tick per tile: repeat 12), hex shield band
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, bolt_points, kite, pmap, tapered_path)

S = 128


def orb(f, seed=5000):
    c = Cell(S, S, seed=seed + f)
    rng = np.random.default_rng(seed + f * 7)
    C = (S / 2, S / 2)
    R = S * 0.3
    core = c.ragged(c.dots([(C[0], C[1], R)]), 0.6, 0.6)
    c.paint(c.sdf(core) > -2.0, V_INK, order=0.4)
    c.paint(core, V_INK, order=0.5)
    # the rim crescent faces the light (up-left) and slides a little each frame
    a = -2.3 + 0.08 * math.sin(f / 8 * math.tau)
    off = (math.cos(a) * R * 0.28, math.sin(a) * R * 0.28)
    rim = core & ~c.dots([(C[0] - off[0], C[1] - off[1], R * 0.95)])
    c.paint(rim, V_BODY, order=0.6)
    rim2 = core & ~c.dots([(C[0] - off[0] * 1.5, C[1] - off[1] * 1.5, R * 0.97)])
    c.paint(rim2, V_LIGHT, order=0.7)
    # three surface crackles, new each frame
    paths = []
    for k in range(3):
        b = rng.uniform(0, math.tau)
        p0 = (C[0] + math.cos(b) * R * 0.35, C[1] + math.sin(b) * R * 0.35)
        p1 = (C[0] + math.cos(b + 0.4) * R * 1.12, C[1] + math.sin(b + 0.4) * R * 1.12)
        paths.append((bolt_points(p0, p1, rng, 0.25, 3), 2.0))
    c.paint(c.lines(paths), V_LIGHT, order=0.8)
    c.paint(c.dots([(C[0] + off[0] * 0.3, C[1] + off[1] * 0.3, R * 0.2)]), V_HOT, order=1.0)
    return c.pack()


def globe(f, seed=5100):
    """A heavy blob: an ink body with an event-horizon rim, a lit crescent, a turning inner swirl, drips."""
    c = Cell(S, S, seed=seed + f)
    C = (S / 2, S * 0.46)
    R = S * 0.3
    ph = f / 8 * math.tau
    sx = 1 + 0.08 * math.sin(ph)
    sy = 1 - 0.08 * math.sin(ph)
    b = c.ragged(c.ellipse(C, R * sx, R * sy), 0.8, 0.5)
    drips = c.polys([P.teardrop((C[0] - R * 0.35 + 9 * k, C[1] + R * sy + 5 + 6 * ((f + 3 * k) % 8) / 8), (0, 1),
                                2.4 + k * 0.5, 6) for k in range(3)])
    c.paint(c.sdf(b | drips) > -1.8, V_INK, order=0.3)
    c.paint(b | drips, V_INK, order=0.4)
    rim = b & (c.inside_dist(b) < 3.2)
    c.paint(rim, V_BODY, order=0.5)
    arms = []
    for k in range(3):
        a0 = k * math.tau / 3 + ph * 0.5
        pts = [(C[0] + math.cos(a0 + 2.4 * t) * R * (0.8 - 0.65 * t) * sx, C[1] + math.sin(a0 + 2.4 * t) * R * (0.8 - 0.65 * t) * sy)
               for t in np.linspace(0, 1, 16)]
        arms.append(tapered_path(pts, [0.4 + 4.2 * math.sin(math.pi * t) for t in np.linspace(0, 1, 16)]))
    c.paint(c.polys(arms) & b & ~rim, V_DEEP, order=0.55)
    lit = b & ~c.ellipse((C[0] + R * 0.22, C[1] + R * 0.26), R * sx * 0.97, R * sy * 0.95)
    c.paint(lit, V_LIGHT, order=0.6)
    c.paint(c.dots([(C[0] - R * 0.42, C[1] - R * 0.48, R * 0.11)]), V_HOT, order=0.9)
    c.paint(c.dots([(C[0], C[1], R * 0.12)]), V_BODY, order=0.7)
    return c.pack()


def enemy_shot(f, seed=5200):
    c = Cell(S, S, seed=seed + f)
    C = (S * 0.6, S / 2)
    r = S * 0.15 * (1 + 0.05 * math.sin(f * 1.7))
    L = r * 2.6 * (1 + 0.06 * math.cos(f * 2.3))
    outer = c.polys([P.teardrop(C, (1, 0), r * 1.32, L * 1.25)])
    shell = c.polys([P.teardrop(C, (1, 0), r * 1.16, L * 1.12)])
    body = c.polys([P.teardrop((C[0] + 1, C[1]), (1, 0), r * 0.86, L * 0.85)])
    core = c.polys([P.teardrop((C[0] + 3, C[1]), (1, 0), r * 0.45, L * 0.4)])
    c.paint(outer, V_LIGHT, order=0.2)
    c.paint(shell, V_INK, order=0.4)
    c.paint(body, V_BODY, order=0.6)
    c.paint(core, V_HOT, order=0.9)
    # a short dark streak trails it
    c.paint(c.polys([tapered_path([(C[0] - L * 1.1, C[1]), (C[0] - L * 2.0, C[1])], [r * 0.9, 0.5])]), V_INK, order=0.1)
    return c.pack()


def misc_body(k, seed=5300):
    c = Cell(S, S, seed=seed + k)
    C = (S / 2, S / 2)
    if k == 0:  # needle sliver: a hot sliver inside an ink sliver
        ink = c.polys([[(S * 0.08, C[1]), (S * 0.6, C[1] - 5), (S * 0.92, C[1]), (S * 0.6, C[1] + 5)]])
        hot = c.polys([[(S * 0.25, C[1]), (S * 0.62, C[1] - 2), (S * 0.88, C[1]), (S * 0.62, C[1] + 2)]])
        c.paint(c.sdf(ink) > -1.5, V_INK, order=0.3)
        c.paint(hot, V_HOT, order=0.8)
        c.paint(ink & ~hot & (c.X > S * 0.4), V_BODY, order=0.5)
    elif k == 1:  # pellet: a small diamond with a short straight streak
        d = c.polys([kite((S * 0.7, C[1]), (1, 0), 14, 8, back=0.9)])
        c.paint(c.polys([tapered_path([(S * 0.08, C[1]), (S * 0.6, C[1])], [0.5, 7])]), V_BODY, order=0.2)
        c.paint(c.sdf(d) > -1.6, V_INK, order=0.3)
        c.paint(d, V_LIGHT, order=0.6)
        c.paint(c.polys([kite((S * 0.72, C[1]), (1, 0), 8, 3.5, back=0.8)]), V_HOT, order=0.9)
    elif k == 2:  # bolt kite: short thick crossbow bolt, hot tip, ink shaft
        shaft = c.polys([tapered_path([(S * 0.1, C[1]), (S * 0.62, C[1])], [7, 7])])
        head = c.polys([kite((S * 0.66, C[1]), (1, 0), S * 0.26, 11, back=0.35)])
        fins = c.polys([[(S * 0.1, C[1]), (S * 0.2, C[1] - 12), (S * 0.28, C[1] - 3)], [(S * 0.1, C[1]), (S * 0.2, C[1] + 12), (S * 0.28, C[1] + 3)]])
        c.paint(c.sdf(shaft | head | fins) > -1.6, V_INK, order=0.2)
        c.paint(fins, V_DEEP, order=0.3)
        c.paint(head, V_LIGHT, order=0.6)
        c.paint(c.polys([kite((S * 0.74, C[1]), (1, 0), S * 0.17, 4, back=0.2)]), V_HOT, order=0.9)
    else:  # slug head: a long thin tracer head (the trail supplies the length)
        m = c.polys([tapered_path([(S * 0.05, C[1]), (S * 0.7, C[1]), (S * 0.9, C[1])], [0.5, 8, 5])])
        c.paint(c.sdf(m) > -1.5, V_INK, order=0.3)
        c.paint(m, V_LIGHT, order=0.6)
        c.paint(c.polys([tapered_path([(S * 0.3, C[1]), (S * 0.85, C[1])], [0.5, 3.4])]), V_HOT, order=0.9)
    return c.pack()


def charge_core(f, seed=5400):
    c = Cell(S, S, seed=seed + f)
    C = (S / 2, S / 2)
    if f == 0:
        c.paint(c.ragged(c.dots([(C[0], C[1], 9)]), 0.8, 0.6), V_INK, order=0.5)
        c.paint(c.dots([(C[0], C[1], 3)]), V_DEEP, order=0.6)
    elif f == 1:
        d = c.ragged(c.dots([(C[0], C[1], 17)]), 0.8, 0.6)
        c.paint(c.sdf(d) > -2.4, V_INK, order=0.4)
        c.paint(d, V_BODY, order=0.5)
        c.paint(d & ~c.dots([(C[0] + 4, C[1] + 4, 16)]), V_LIGHT, order=0.6)
    elif f == 2:
        d = c.ragged(c.dots([(C[0], C[1], 21)]), 0.8, 0.6)
        c.paint(c.sdf(d) > -2.4, V_INK, order=0.4)
        c.paint(d, V_BODY, order=0.5)
        c.paint(c.dots([(C[0], C[1], 12)]), V_LIGHT, order=0.7)
        c.paint(c.dots([(C[0], C[1], 6)]), V_HOT, order=0.9)
    else:  # the 1-frame "release now" glint
        m, rel = c.star(C, [(k * math.pi / 2, S * (0.46 if k % 2 == 0 else 0.3), 0.2) for k in range(4)], 6, p=2.2)
        c.paint(c.sdf(m) > -2.0, V_INK, order=0.3)
        c.paint(m, np.where(rel < 0.5, V_HOT, V_LIGHT), order=0.8)
    return c.pack()


def charge_ring(f, seed=5500):
    """The broken ring round the weapon tightening (1.3 m -> 0.35 m in-engine by scale; the frames add the
    tightening gaps and a white flash on the last frame)."""
    c = Cell(S, S, seed=seed + f)
    C = (S / 2, S / 2)
    R = S * (0.44 - 0.07 * f)
    gaps = 3
    polys = []
    for k in range(gaps):
        a0 = k * math.tau / gaps + f * 0.35
        span = math.tau / gaps * (0.62 + 0.08 * f)
        pts = [(C[0] + math.cos(a) * R, C[1] + math.sin(a) * R) for a in np.linspace(a0, a0 + span, 20)]
        w = 2.4 + 0.8 * f
        polys.append(tapered_path(pts, [0.4] + [w] * 18 + [0.4]))
    m = c.polys(polys)
    c.paint(c.sdf(m) > -1.5, V_INK, order=0.3)
    c.paint(m, V_HOT if f == 3 else (V_LIGHT if f == 2 else V_BODY), order=0.6)
    return c.pack()


def band(i, seed=5600, W=1024, h=64):
    """Tileable ring bands (painted on a 3-tile canvas, the middle tile kept)."""
    c = Cell(W * 3, h, seed=seed + i)
    u = (c.X / W) % 1.0
    v = c.Y / h
    rng = np.random.default_rng(seed + i)
    if i == 0:  # dust wall: puffs lit from the blast; painted on a quarter-width tile, stretched 4x along u
        return dust_band(seed)
    elif i == 1:  # shock front: a bright broken band with speed ticks
        hw = 0.12 + 0.04 * np.sin(u * math.tau * 3)
        m = (np.abs(v - 0.5) < hw) & (c.nz(c.X * 0.03125, c.Y * 0) > 0.25)
        c.paint(m, np.where(np.abs(v - 0.5) < hw * 0.4, V_HOT, V_LIGHT), order=0.6)
        ticks = []
        for k in range(18):
            x = k / 18 * W + rng.uniform(0, 20)
            for o in (0, W, 2 * W):
                ticks.append(tapered_path([(x + o, h * 0.2), (x + o - 8, h * 0.4)], [0.5, 3]))
        c.paint(c.polys(ticks), V_BODY, order=0.4)
        ero = 0.3 + 0.7 * c.nz(c.X * 0.0625, c.Y * 0.1)
    elif i == 2:  # tick ring: one tick and one arc segment per tile (repeat 12 round the Still Field)
        arc = (np.abs(v - 0.62) < 0.06) & (u > 0.06) & (u < 0.94)
        tick = (np.abs(u - 0.5) < 0.012) & (v > 0.2) & (v < 0.66)
        c.paint(arc, V_BODY, order=0.5)
        c.paint(tick, V_LIGHT, order=0.7)
        c.paint((np.abs(u - 0.5) < 0.006) & (v > 0.3) & (v < 0.6), V_HOT, order=0.8)
        ero = np.clip(1 - np.abs(u - 0.5), 0.02, 1)
    else:  # hex band: forge-shield ripple
        cells = 16
        uu = u * cells
        k = np.floor(uu)
        fx = uu - k - 0.5
        fy = (v - 0.5) * 2
        hexd = np.maximum(np.abs(fx) * 1.0 + np.abs(fy) * 0.35, np.abs(fy) * 0.9)
        wall = (hexd > 0.38) & (hexd < 0.46) & (np.abs(v - 0.5) < 0.42)
        c.paint(wall, V_LIGHT, order=0.6)
        c.paint((hexd <= 0.38) & (np.abs(v - 0.5) < 0.42), V_DEEP, order=0.3)
        ero = 0.3 + 0.7 * c.nz(c.X * 0.0625, c.Y * 0.2)
    return c.pack(ero=ero)[:, W:2 * W]


def dust_band(seed, W=1024, h=64):
    """Ring tiles span ~4x their height on screen, so the dust lobes are painted round on a 256-wide tile and
    the packed tile is stretched to 1024 (they read round again once wrapped onto the ring)."""
    from PIL import Image
    w = W // 4
    c = Cell(w * 3, h, seed=seed)
    rng = np.random.default_rng(seed)
    lobes = []
    for k in range(7):
        x = (k + 0.5) / 7 * w + rng.uniform(-5, 5)
        y = h * rng.uniform(0.5, 0.6)
        r = h * rng.uniform(0.2, 0.3)
        for o in (0, w, 2 * w):
            lobes.append((x + o, y, r))
    for k in range(5):
        x = rng.uniform(0, w)
        for o in (0, w, 2 * w):
            lobes.append((x + o, h * rng.uniform(0.38, 0.46), h * rng.uniform(0.12, 0.18)))
    lobes.sort(key=lambda l: -l[1])
    P.puff_cluster(c, lobes, light=(0, 1), rim=0.3, mid=0.62, v_rim=V_LIGHT, v_mid=V_DEEP, rough=0.25)
    ero = 0.3 + 0.7 * c.nz(c.X * 0.25, c.Y * 0.2)
    tile = c.pack(ero=ero)[:, w:2 * w]
    return np.stack([np.asarray(Image.fromarray(tile[..., k]).resize((W, h), Image.BILINEAR)) for k in range(3)], -1)


def _call2(fn, args):
    return fn(*args)


def build():
    a = Atlas("vfx_bodies", 8, 4, S, S, intended="billboard projectile bodies and charge cues (the meshes cover "
              "Shell, Arrow, Boulder, Coin, Blade, Javelin, Harpoon)")
    jobs = [(orb, (f,)) for f in range(8)] + [(globe, (f,)) for f in range(8)] + \
           [(enemy_shot, (f,)) for f in range(4)] + [(misc_body, (k,)) for k in range(4)] + \
           [(charge_core, (f,)) for f in range(4)] + [(charge_ring, (f,)) for f in range(4)]
    for k, cell in enumerate(pmap(_call2, jobs)):
        a.put(k % 8, k // 8, cell)
    a.seq("orb", 0, 8, fps=12, loop=True, pivot=(0.5, 0.5), intended="Orb body (Thundercoil, Sundial); rotate so the "
          "rim faces the light", radius_in_cell=0.6)
    a.seq("globe", 1, 8, fps=10, loop=True, pivot=(0.5, 0.46), intended="Globe body: void / plague / iron by ramp",
          radius_in_cell=0.6)
    a.seq("enemy_shot", 2, 4, fps=15, loop=True, pivot=(0.6, 0.5), ramp="enemy_shot", intended="EnemyShot / boss "
          "Radial teardrop, head at +u; stretch 1.6x along velocity; never an element colour")
    a.seq("small_bodies", 2, 4, col0=4, pivot=(0.6, 0.5), names=["needle", "pellet", "bolt", "slug"],
          intended="billboard bodies for small or distant projectiles, head at +u")
    a.seq("charge_core", 3, 4, pivot=(0.5, 0.5), intended="charge: ink dot -> body disc -> hot pin -> release glint "
          "(PlayerView.charge 0..1; the glint is 1 frame)")
    a.seq("charge_ring", 3, 4, col0=4, pivot=(0.5, 0.5), intended="the broken charge ring tightening; the last frame "
          "flashes white at full charge")
    a.save()
    b = Atlas("vfx_bands", 1, 4, 1024, 64, sub="trails", kind="strip_packed", intended="tileable ring bands for "
              "meshes/vfx_ring_*.glb (u round the ring, v across the profile)")
    for k, cell in enumerate(pmap(band, [(i,) for i in range(4)])):
        b.put(0, k, cell)
    for k, (name, intent) in enumerate([("dust_wall", "painterly dust wall riding the shock front (ring_wall), lit "
                                         "from the blast"), ("shock_front", "bright broken shock band with speed "
                                         "ticks (ring_flat / ring_crown)"), ("tick_ring", "Still Field: one tick per "
                                         "tile, repeat 12"), ("hex_band", "forge-shield hex ripple band")]):
        b.seq(name, k, 1, tileable_u=True, pivot=(0.5, 0.5), intended=intent)
    b.save()
    return [a, b]


if __name__ == "__main__":
    build()
