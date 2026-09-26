"""Strip textures for Rust-generated ribbons and smears (VFX_STYLE sections 2, 6, 7, 21.4).

  trails/vfx_trails.png  16 rows of 1024 x 64: projectile trails, beams, loot beams, tethers, ring bands
  smears/vfx_smears.png  8 rows of 1024 x 128: crescent smears for melee, slashes, dashes, spins

Strip space: u = 0 at the tail (oldest end) .. 1 at the head (newest end); v = 0 .. 1 across (for
smears v = 0 is the inner edge, v = 1 the outer edge, where the bright blade lives). The texture
carries its own head-to-tail taper, so build ribbons at constant width (or a mild taper). Rows marked
tileable_u repeat seamlessly along u (beams, tethers, ring bands): scale u by length / tile length.
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, kite, pmap, streak_poly, tapered_path,
                    tongue_poly)

W = 1024
TRAILS = [
    ("tracer", False, "Slug: a hard straight 3-frame streak, white core in element rims"),
    ("dry_brush", False, "generic trail: body band, the tail breaks into dry-brush streaks (Bolt, Pellet, homing)"),
    ("ghost_smear", False, "Arrow: a wide ghost smear, dark core, bright rims, wisps peeling off"),
    ("smoke_trail", False, "Shell: ink smoke puffs that grow and thin toward the tail"),
    ("helix", False, "Orb: 2 thin strands coiled round the flight path (Storm), the Sundial dial arc"),
    ("dust_ribbon", False, "Boulder: a ragged dust ribbon"),
    ("zigzag", False, "Coin: a thin gold zig-zag (kink it at ricochets)"),
    ("flame_trail", False, "Flame projectiles, Furnace Rush: licks trailing off the ribbon"),
    ("drip_trail", False, "Globe: droplets / ink drips falling off behind"),
    ("glint_trail", False, "Shard, homing seeker: a trail of 4-point glints"),
    ("needle_streak", False, "Needle: a thin brass streak (the stream stitches into one line)"),
    ("beam_core", True, "beam core: white-hot line with streak noise; scroll u at 6 m/s"),
    ("beam_body", True, "beam body: element bands with a gentle wobble; scroll u"),
    ("loot_beam", True, "loot beam: a tall thin ribbon with a bright core and rising motes (never tier-dropped)"),
    ("tether_braid", True, "revive tether: a braided ribbon (P-colour tint in the shader)"),
    ("accent_ring", True, "broken accent ring band for ring meshes: one gap per tile, tapered ends"),
]
SMEARS = [
    ("melee_heavy", False, "melee crescent: ink body, bright blade on the outer leading 60 %, dry-brush tail"),
    ("slash_thin", False, "crit / execute / pierce slash: a thin bright cut over a wider ink cut"),
    ("dash_drybrush", False, "dash, roll, recoil smear: a streaky dry-brush stroke"),
    ("flame_smear", False, "Flame melee (Meltdown, Furnace Rush): tongues licking off the outer edge"),
    ("void_smear", False, "Void smear (Shadow Roll, Kael): ink-dominant, violet rim, 2 afterimage echoes"),
    ("storm_smear", False, "Storm smear (Stormlash, Blink): a jagged crackling outer edge"),
    ("whip", False, "whip-crack / string snap: a thin tapered S line with a crack flash at the head"),
    ("spin_disc", True, "spinning disc / orbit blade: one blade's circular smear per tile (map around a ring)"),
]


def tile_cell(h, seed):
    """A 3-tile-wide canvas for tileable rows: paint periodically, pack, keep the middle tile."""
    return Cell(W * 3, h, seed=seed)


def crop_mid(packed):
    return packed[:, W:2 * W]


def uv(c, w=None):
    return c.X / (w or c.w), c.Y / c.h


# ---- trails --------------------------------------------------------------------------------------
def taper_mask(c, u, v, head=0.995, w_head=0.36, w_tail=0.06, p=0.8, cap=0.03, rag=0.04):
    """A ribbon silhouette in strip space: half-width grows from the tail to the head, round head cap."""
    t = np.clip(u, 0, 1)
    hw = w_tail + (w_head - w_tail) * t ** p
    hw = hw * (1 + rag * (c.nz(c.X * 0.25, c.Y * 0.25) - 0.5) * 2)
    capk = np.clip((u - (head - cap)) / cap, 0, 1)
    hw = hw * np.sqrt(np.clip(1 - capk ** 2, 0, 1))
    return (np.abs(v - 0.5) < hw) & (u < head) & (u > 0.004), hw


def trail_cell(i, seed, h=64):
    name, tile, _ = TRAILS[i]
    if tile:
        c = tile_cell(h, seed + i)
        u = c.X / W  # 0..3
        uf = u % 1.0
    else:
        c = Cell(W, h, seed=seed + i)
        u = c.X / W
        uf = u
    v = c.Y / h
    rng = np.random.default_rng(seed + i)
    if name == "tracer":
        m, hw = taper_mask(c, u, v, w_head=0.2, w_tail=0.02, p=1.2, rag=0.0)
        d = np.abs(v - 0.5) / np.maximum(hw, 1e-3)
        c.paint(m, np.where(d < 0.3, V_HOT, np.where(d < 0.55, V_LIGHT, np.where(d < 0.85, V_BODY, V_INK))), order=0.5)
        ero = np.clip(u, 0.02, 1)
    elif name == "dry_brush":
        m, hw = taper_mask(c, u, v, w_head=0.3, w_tail=0.1, p=0.7)
        st = c.nz_streak(c.X * 0.02, c.Y * 0.35)
        m &= ~((u < 0.55) & (st < (0.55 - u) / 0.55 * 0.85))
        d = np.abs(v - 0.5) / np.maximum(hw, 1e-3)
        c.paint(m, np.where(d < 0.3, V_LIGHT, np.where(d < 0.75, V_BODY, V_DEEP)), order=0.5)
        c.paint(m & (d < 0.25) & (u > 0.85), V_HOT, order=0.8)
        ero = np.clip(u * 0.75 + 0.25 * st, 0.02, 1)
    elif name == "ghost_smear":
        m, hw = taper_mask(c, u, v, w_head=0.4, w_tail=0.14, p=0.6, rag=0.08)
        st = c.nz_streak(c.X * 0.02, c.Y * 0.3)
        m &= ~((u < 0.45) & (st < (0.45 - u) / 0.45 * 0.9))
        d = np.abs(v - 0.5) / np.maximum(hw, 1e-3)
        c.paint(m, np.where(d > 0.72, V_LIGHT, np.where(d > 0.55, V_BODY, V_INK)), order=0.5)
        # wisps peeling off near the fletching
        wisps = []
        for s in (-1, 1):
            pts = [(W * (0.62 - 0.4 * t), h * (0.5 + s * (0.3 + 0.18 * t + 0.05 * math.sin(t * 9)))) for t in np.linspace(0, 1, 16)]
            wisps.append(tapered_path(pts, [3.2 * (1 - t) + 0.3 for t in np.linspace(0, 1, 16)]))
        c.paint(c.polys(wisps), V_BODY, order=0.3)
        ero = np.clip(u * 0.8 + 0.2 * st, 0.02, 1)
    elif name == "smoke_trail":
        lobes = []
        for k in range(40):
            t = k / 39
            x = W * (0.03 + 0.92 * t)
            r = h * (0.42 - 0.22 * t) * rng.uniform(0.75, 1.1)
            lobes.append((x + rng.uniform(-8, 8), h * 0.5 + rng.uniform(-3, 3), r))
        P.puff_cluster(c, lobes, light=(0, -1), rim=0.26, mid=0.6, v_rim=V_BODY, v_mid=V_DEEP, rough=0.22)
        n = c.nz(c.X * 0.05, c.Y * 0.2)
        c.erase(c.cov & (n + (1 - u) * 0.6 > 1.15))
        c.paint(c.ellipse((W * 0.985, h / 2), 14, h * 0.18), V_HOT, order=1.0)
        c.paint(c.ellipse((W * 0.955, h / 2), 26, h * 0.22) & ~c.ellipse((W * 0.985, h / 2), 14, h * 0.18), V_LIGHT, order=0.9)
        ero = np.clip(u * 0.7 + 0.3 * n, 0.02, 1)
    elif name == "helix":
        strands = []
        for s in (0, math.pi):
            pts = [(W * t, h * (0.5 + 0.3 * math.sin(t * math.tau * 5 + s) * (0.4 + 0.6 * t))) for t in np.linspace(0.005, 0.99, 200)]
            strands.append(tapered_path(pts, [0.6 + 3.8 * t for t in np.linspace(0, 1, 200)]))
        m = c.polys(strands)
        c.paint(c.sdf(m) > -1.4, V_INK, order=0.3)
        c.paint(m, np.where(u > 0.7, V_LIGHT, V_BODY), order=0.5)
        ero = np.clip(u, 0.02, 1)
    elif name == "dust_ribbon":
        m, hw = taper_mask(c, u, v, w_head=0.36, w_tail=0.2, p=0.5, rag=0.3)
        m = c.ragged(m, 2.5, 0.2)
        n = c.nz(c.X * 0.04, c.Y * 0.15)
        m &= n + (1 - u) * 0.5 < 1.2
        c.paint(m, np.where(v < 0.42, V_BODY, np.where(v < 0.58, V_DEEP, V_INK)), order=0.5)
        ero = np.clip(u * 0.6 + 0.4 * n, 0.02, 1)
    elif name == "zigzag":
        pts = []
        x = 4.0
        s = 1
        while x < W - 6:
            pts.append((x, h * (0.5 + s * 0.22)))
            x += rng.uniform(40, 80)
            s = -s
        pts.append((W - 6, h * 0.5))
        n = len(pts)
        path = tapered_path(pts, [0.8 + 3.6 * k / (n - 1) for k in range(n)])
        m = c.polys([path])
        c.paint(c.sdf(m) > -1.3, V_INK, order=0.3)
        c.paint(m, np.where(u > 0.6, V_LIGHT, V_BODY), order=0.5)
        ero = np.clip(u, 0.02, 1)
    elif name == "flame_trail":
        m, hw = taper_mask(c, u, v, w_head=0.2, w_tail=0.06, p=0.8)
        c.paint(m, V_BODY, order=0.4)
        for k in range(14):
            t = k / 13
            x = W * (0.08 + 0.88 * t)
            hh = h * (0.16 + 0.3 * t)
            for s in (-1, 1):
                if rng.random() < 0.7:
                    base = (x, h / 2)
                    # a lick pointing out to the side and back toward the tail
                    poly = tongue_poly((0, 0), hh * 1.1, hh * 0.7, rng.uniform(0, 6), curl=0.4, tip_curl=0.4)
                    dx, dy = -0.6, s * 0.8
                    nx, ny = -dy, dx
                    pts = [(base[0] + (-py) * dx + px * nx, base[1] + (-py) * dy + px * ny) for px, py in poly]
                    c.paint(c.polys([pts]), V_DEEP if t < 0.4 else V_BODY, order=0.3)
        c.paint(m & (np.abs(v - 0.5) < hw * 0.45), V_LIGHT, order=0.6)
        c.paint(m & (np.abs(v - 0.5) < hw * 0.2) & (u > 0.8), V_HOT, order=0.8)
        ero = np.clip(u * 0.75 + 0.25 * c.nz(c.X * 0.1, c.Y * 0.1), 0.02, 1)
    elif name == "drip_trail":
        m, hw = taper_mask(c, u, v, w_head=0.28, w_tail=0.1, p=0.7, rag=0.1)
        drips = []
        for k in range(10):
            x = W * rng.uniform(0.05, 0.9)
            t = x / W
            drips.append(P.teardrop((x, h * (0.62 + 0.25 * (1 - t))), (0, 1), 3.5 + 3 * t, 10 + 8 * t))
        m |= c.polys(drips)
        c.paint(c.sdf(m) > -1.4, V_INK, order=0.3)
        c.paint(m, np.where(v < 0.45, V_BODY, V_DEEP), order=0.5)
        ero = np.clip(u * 0.8 + 0.2 * c.nz(c.X * 0.1, c.Y * 0.1), 0.02, 1)
    elif name == "glint_trail":
        polys = []
        x = W * 0.97
        k = 0
        while x > W * 0.04:
            t = x / W
            sz = h * (0.1 + 0.3 * t)
            p = (x, h / 2 + rng.uniform(-4, 4) * (1 - t))
            polys.append(kite(p, (1, 0), sz, sz * 0.3, back=1.0))
            polys.append(kite(p, (0, 1), sz * 0.7, sz * 0.25, back=1.0))
            x -= rng.uniform(40, 70)
            k += 1
        m = c.polys(polys)
        c.paint(c.sdf(m) > -1.4, V_INK, order=0.3)
        c.paint(m, np.where(u > 0.6, V_LIGHT, V_BODY), order=0.5)
        ero = np.clip(u, 0.02, 1)
    elif name == "needle_streak":
        m, hw = taper_mask(c, u, v, w_head=0.12, w_tail=0.015, p=1.0, rag=0.0)
        d = np.abs(v - 0.5) / np.maximum(hw, 1e-3)
        c.paint(m, np.where(d < 0.4, V_LIGHT, V_BODY), order=0.5)
        c.paint(m & (u > 0.9) & (d < 0.5), V_HOT, order=0.8)
        ero = np.clip(u, 0.02, 1)
    elif name == "beam_core":
        n = c.nz_streak(c.X * 0.125, c.Y * 0.5)
        hw = 0.14 + 0.05 * (c.nz(c.X * 0.0625, c.Y * 0.0) - 0.5)
        m = np.abs(v - 0.5) < hw
        d = np.abs(v - 0.5) / hw
        c.paint(m, np.where(d < 0.45 + 0.3 * (n - 0.5), V_HOT, V_LIGHT), order=0.6)
        ero = np.clip(0.3 + 0.7 * n, 0.02, 1)
    elif name == "beam_body":
        wob = 0.04 * np.sin(uf * math.tau * 3) + 0.03 * (c.nz(c.X * 0.0625, c.Y * 0) - 0.5)
        hw = 0.36 + wob
        n = c.nz_streak(c.X * 0.125, c.Y * 0.4)
        m = np.abs(v - 0.5) < hw
        m = c.ragged(m, 1.0, 0.125, streak=True)
        d = np.abs(v - 0.5) / hw
        c.paint(m, np.where(d < 0.3, V_LIGHT, np.where(d < 0.8 + 0.2 * (n - 0.5), V_BODY, V_DEEP)), order=0.5)
        ero = np.clip(0.3 + 0.7 * n, 0.02, 1)
    elif name == "loot_beam":
        hw = 0.2 + 0.03 * np.sin(uf * math.tau * 2)
        m = np.abs(v - 0.5) < hw
        d = np.abs(v - 0.5) / hw
        c.paint(m, np.where(d < 0.35, V_HOT, np.where(d < 0.7, V_LIGHT, V_BODY)), order=0.5)
        motes = []
        for k in range(12):
            x = rng.uniform(0, W)
            y = h * (0.5 + rng.uniform(-0.38, 0.38))
            r = rng.uniform(2.0, 4.0)
            for o in (0, W, 2 * W):
                motes.append((x + o, y, r))
        c.paint(c.dots(motes), V_LIGHT, order=0.7)
        ero = np.clip(1 - d * 0.6, 0.02, 1)
    elif name == "tether_braid":
        strands = []
        for s in (0, math.pi):
            pts = [(W * 3 * t, h * (0.5 + 0.26 * math.sin(t * 3 * math.tau * 4 + s))) for t in np.linspace(0, 1, 600)]
            strands.append((pts, 6.0))
        m0 = c.lines([strands[0]])
        m1 = c.lines([strands[1]])
        front = np.sin(u * math.tau * 4) > 0
        c.paint(c.sdf(m0 | m1) > -1.5, V_INK, order=0.3)
        c.paint(m1 & ~(m0 & front), V_BODY, order=0.5)
        c.paint(m0 & ~(m1 & ~front), V_LIGHT, order=0.6)
        ero = np.clip(0.5 + 0.5 * c.nz(c.X * 0.0625, c.Y * 0.2), 0.02, 1)
    else:  # accent_ring: one tapered segment per tile with a gap
        g0, g1 = 0.08, 0.92
        t = np.clip((uf - g0) / (g1 - g0), 0, 1)
        hw = 0.22 * np.clip(np.sin(np.pi * t), 0, 1) ** 0.6
        hw = hw * (1 + 0.15 * (c.nz(c.X * 0.0625, c.Y * 0) - 0.5))
        m = (np.abs(v - 0.5) < hw) & (uf > g0) & (uf < g1)
        d = np.abs(v - 0.5) / np.maximum(hw, 1e-3)
        c.paint(m, np.where(d < 0.35, V_LIGHT, V_BODY), order=0.5)
        ero = np.clip(np.sin(np.pi * t) * 0.8 + 0.2 * c.nz(c.X * 0.125, c.Y * 0.1), 0.02, 1)
    packed = c.pack(ero=ero)
    return crop_mid(packed) if tile else packed


# ---- smears --------------------------------------------------------------------------------------
def smear_cell(i, seed, h=128):
    name, tile, _ = SMEARS[i]
    if tile:
        c = tile_cell(h, seed + i)
        u = c.X / W
        uf = u % 1.0
    else:
        c = Cell(W, h, seed=seed + i)
        u = c.X / W
        uf = u
    v = c.Y / h
    rng = np.random.default_rng(seed + i)
    lo, hi = 0.07, 0.93
    vv = (v - lo) / (hi - lo)  # 0 inner .. 1 outer within the painted band
    st = c.nz_streak(c.X * 0.02, c.Y * 0.18)
    rag_in = 0.12 * (c.nz(c.X * 0.15, c.Y * 0.1) - 0.5)
    head = np.clip((u - 0.965) / 0.03, 0, 1)
    cap = np.sqrt(np.clip(1 - head ** 2, 0, 1))  # the rounded head
    if name == "melee_heavy":
        band = (vv > 0.02 + rag_in + (1 - cap) * 0.5) & (vv < 0.98 - (1 - cap) * 0.5) & (u > 0.003) & (u < 0.995)
        band &= ~((u < 0.4) & (st < (0.4 - u) / 0.4 * 0.95))  # dry-brush tail
        jn = (c.nz(c.X * 0.04, c.Y * 0.05) - 0.5) * 0.14
        blade_w = np.clip((u - 0.38 + jn) / 0.62, 0, 1) ** 0.7 * 0.55
        blade_w = blade_w * (1 + 0.25 * np.sin(u * 9.0) * np.clip(u - 0.4, 0, 1))
        blade = band & (vv > 1 - blade_w)
        c.paint(band, V_INK, order=0.4)
        c.paint(band & (vv > 1 - blade_w - 0.06) & (u > 0.35), V_DEEP, order=0.5)
        c.paint(blade, np.where(vv > 1 - blade_w * 0.45, V_LIGHT, V_BODY), order=0.6)
        c.paint(blade & (vv > 0.9) & (u > 0.7), V_HOT, order=0.9)
        ero = np.clip(u * 0.75 + 0.25 * st, 0.02, 1)
    elif name == "slash_thin":
        env = np.sin(np.pi * np.clip(u, 0, 1)) ** 0.6
        cut = np.abs(vv - 0.5) < 0.42 * env
        line = np.abs(vv - 0.5 - 0.06) < 0.1 * env
        c.paint(cut, V_INK, order=0.4)
        c.paint(line, V_LIGHT, order=0.7)
        c.paint(line & (np.abs(vv - 0.56) < 0.045 * env), V_HOT, order=0.9)
        ero = np.clip(env * 0.8 + 0.2 * st, 0.02, 1)
    elif name == "dash_drybrush":
        band = (vv > 0.05 + rag_in) & (vv < 0.95 - rag_in) & (u > 0.003) & (u < 0.995)
        bristle = c.nz_streak(c.X * 0.01, c.Y * 0.45)
        band &= bristle > 0.25 * (1 - u) + 0.08
        band &= ~((1 - cap) > 0.2)
        c.paint(band, np.where(bristle > 0.78, V_BODY, np.where(bristle > 0.5, V_DEEP, V_INK)), order=0.5)
        c.paint(band & (bristle > 0.9) & (u > 0.5), V_LIGHT, order=0.7)
        ero = np.clip(u * 0.6 + 0.4 * bristle, 0.02, 1)
    elif name == "flame_smear":
        jn = (c.nz(c.X * 0.03, c.Y * 0.06) - 0.5) * 0.3
        band = (vv > 0.04 + rag_in) & (vv < 0.6 + jn * 0.3) & (u > 0.003) & (u < 0.995 - (1 - cap) * 0.02)
        band &= ~((u < 0.35) & (st < (0.35 - u) / 0.35 * 0.9))
        c.paint(band, V_DEEP, order=0.3)
        x = W * 0.12
        while x < W * 0.97:
            t = x / W
            hh = h * (0.34 + 0.52 * t) * rng.uniform(0.55, 1.25)
            ww = h * (0.26 + 0.2 * t) * rng.uniform(0.8, 1.3)
            ph = rng.uniform(0, 6)
            base = (x, h * rng.uniform(0.5, 0.62))
            poly = tongue_poly(base, hh, ww, ph, lean=-0.75 * rng.uniform(0.7, 1.2), curl=0.5, tip_curl=0.7)
            m = c.ragged(c.polys([poly]), 0.8, 0.4)
            c.paint(m, V_DEEP if t < 0.3 else V_BODY, order=0.4)
            if rng.random() < 0.6:
                c.paint(c.polys([tongue_poly(base, hh * 0.42, ww * 0.34, ph + 0.3, lean=-0.75)]) & m,
                        V_LIGHT if t > 0.4 else V_BODY, order=0.6)
            x += W * rng.uniform(0.1, 0.17)
        c.paint(band & (vv + jn > 0.28) & (u + jn * 0.3 > 0.3), V_BODY, order=0.45)
        c.paint(band & (vv + jn > 0.44) & (u + jn * 0.3 > 0.55), V_LIGHT, order=0.65)
        c.paint(band & (vv + jn > 0.5) & (u > 0.82), V_HOT, order=0.9)
        ero = np.clip(u * 0.7 + 0.3 * c.nz(c.X * 0.08, c.Y * 0.08), 0.02, 1)
    elif name == "void_smear":
        band = (vv > 0.02 + rag_in) & (vv < 0.97 - (1 - cap) * 0.5) & (u > 0.003) & (u < 0.995)
        band &= ~((u < 0.45) & (st < (0.45 - u) / 0.45 * 0.9))
        c.paint(band, V_INK, order=0.4)
        rimw = 0.08 + 0.1 * np.clip(u, 0, 1)
        c.paint(band & (vv > 0.97 - rimw), np.where(vv > 0.97 - rimw * 0.4, V_LIGHT, V_BODY), order=0.6)
        for k, off in enumerate((0.22, 0.42)):
            echo = band & (np.abs(vv - (0.9 - off)) < 0.025 + 0.02 * u) & (u > 0.3 + 0.15 * k)
            c.paint(echo, V_DEEP, order=0.5)
        ero = np.clip(u * 0.8 + 0.2 * st, 0.02, 1)
    elif name == "storm_smear":
        jag = np.zeros_like(u)
        xs = np.linspace(0, 1, 40)
        ys = rng.uniform(-1, 1, 40)
        jag = np.interp(u, xs, ys)
        outer = 0.86 + 0.08 * jag
        band = (vv > 0.05 + rag_in) & (vv < outer - (1 - cap) * 0.4) & (u > 0.003) & (u < 0.995)
        band &= ~((u < 0.3) & (st < (0.3 - u) / 0.3 * 0.9))
        c.paint(band, V_INK, order=0.4)
        edge = band & (vv > outer - 0.16)
        c.paint(edge, V_BODY, order=0.6)
        c.paint(band & (vv > outer - 0.06) & (u > 0.4), V_HOT, order=0.9)
        paths = []
        for k in range(6):
            x0 = W * rng.uniform(0.3, 0.95)
            p0 = (x0, h * (lo + (hi - lo) * 0.8))
            p1 = (x0 - rng.uniform(30, 80), h * (lo + (hi - lo) * rng.uniform(0.3, 0.6)))
            paths += P.bolt_paths(p0, p1, rng, 2.0, branches=0, jag=0.2, depth=3)
        P.paint_bolt(c, paths, ink=0, body=1.6, core=0.6, order=0.7)
        ero = np.clip(u * 0.8 + 0.2 * st, 0.02, 1)
    elif name == "whip":
        env = np.clip(u, 0, 1) ** 0.7
        center = 0.5 + 0.18 * np.sin(u * math.tau * 1.0)
        m = (np.abs(vv - center) < 0.03 + 0.12 * env) & (u > 0.003) & (u < 0.96)
        c.paint(m, V_INK, order=0.4)
        c.paint(m & (np.abs(vv - center) < 0.06 * env + 0.01), V_LIGHT, order=0.6)
        sp = [(k * math.pi / 2 + 0.3, h * (0.42 if k % 2 == 0 else 0.25), 0.3) for k in range(4)]
        ms, rel = c.star((W * 0.955, h * (lo + (hi - lo) * (0.5 + 0.18 * math.sin(0.955 * math.tau)))), sp, 5, p=1.8)
        c.paint(ms, np.where(rel < 0.45, V_HOT, V_LIGHT), order=0.9)
        ero = np.clip(u, 0.02, 1)
    else:  # spin_disc: in each tile a blade's circular smear, bright at the leading end (u -> 1)
        t = uf
        wv = 0.25 + 0.6 * t ** 0.8
        band = (vv > 1 - wv + rag_in * 0.5) & (vv < 0.97)
        st2 = c.nz_streak(c.X * 0.0625, c.Y * 0.25)
        band &= ~((t < 0.5) & (st2 < (0.5 - t) / 0.5 * 0.9))
        jn = (c.nz(c.X * 0.0625, c.Y * 0.1) - 0.5) * 0.25 + (vv - 0.7) * 0.4
        c.paint(band, np.where(t + jn > 0.78, V_LIGHT, np.where(t + jn > 0.42, V_BODY, V_DEEP)), order=0.5)
        c.paint(band & (vv > 0.88) & (t > 0.85), V_HOT, order=0.9)
        ero = np.clip(t * 0.8 + 0.2 * st2, 0.02, 1)
    packed = c.pack(ero=ero)
    return crop_mid(packed) if tile else packed


def build():
    t = Atlas("vfx_trails", 1, 16, W, 64, sub="trails", kind="strip_packed", intended="ribbon strip textures, "
              "u = 0 tail .. 1 head, v across; one row per trail kind")
    for k, cell in enumerate(pmap(trail_cell, [(i, 3000) for i in range(16)])):
        t.put(0, k, cell)
    for k, (name, tile, intent) in enumerate(TRAILS):
        t.seq(name, k, 1, pivot=(1.0, 0.5), tileable_u=tile, intended=intent)
    t.save()
    s = Atlas("vfx_smears", 1, 8, W, 128, sub="smears", kind="strip_packed", intended="crescent smear strips: u = 0 "
              "tail .. 1 head along the sweep, v = 0 inner .. 1 outer edge; map onto meshes/vfx_arc_*.glb or Rust "
              "crescent strips")
    for k, cell in enumerate(pmap(smear_cell, [(i, 3100) for i in range(8)])):
        s.put(0, k, cell)
    for k, (name, tile, intent) in enumerate(SMEARS):
        s.seq(name, k, 1, pivot=(1.0, 1.0), tileable_u=tile, intended=intent,
              timing="8 frames: f0-2 the blade leads, f3-5 the body holds, f6-8 the tail erodes (t = age)" if not tile else None)
    s.save()
    return [t, s]


if __name__ == "__main__":
    build()
