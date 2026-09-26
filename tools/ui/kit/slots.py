"""Slots and medallions (UI_STYLE §6.1, §6.2, §8.1, §8.2).

Shape = category: Core round, Mechanism octagon, Relic arch, Sigil lozenge, ability chamfered
square, Overdrive pointy hex, chassis flat hex. Each shape ships as a fill (lacquer recess), a rim
(gilt bevel + gold_dk inner line, clear inside), a mask (white shape, for glow tint, clip-reveal and
the molten material), and two extras: a soft glow halo (ready state) and a top sheen.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .core import (GOLD, STEEL, Cv, band, chamfer_pts, edge_line, gem_lozenge, h_bead, inner_shadow, lacquer_col, noise_of, rgb, sd_circle, sd_poly, shade, smoothstep)

SHAPES = ("round", "octagon", "arch", "lozenge", "chamfer", "hex_pointy", "hex_flat")
SHAPE_USE = {
    "round": "Core parts, buffs, element cabochons, pins",
    "octagon": "Mechanism parts",
    "arch": "Relic parts",
    "lozenge": "Sigil parts",
    "chamfer": "Abilities Q / E (chamfer 12 at 60 px; sweep child radius = 1.71 x chamfer)",
    "hex_pointy": "Team Overdrive V (68 px)",
    "hex_flat": "The chassis (100 px)",
}


def shape_sd(cv: Cv, shape: str, x0: float, y0: float, s: float) -> np.ndarray:
    """SDF of a slot shape filling the square [x0, x0+s]^2."""
    c = (x0 + s / 2, y0 + s / 2)
    r = s / 2
    if shape == "round":
        return sd_circle(cv, c[0], c[1], r)
    if shape == "octagon":
        return sd_poly(cv, chamfer_pts(x0, y0, x0 + s, y0 + s, s * 0.293), exact=True)
    if shape == "chamfer":
        return sd_poly(cv, chamfer_pts(x0, y0, x0 + s, y0 + s, s * 0.2), exact=True)
    if shape == "lozenge":
        return sd_poly(cv, [(c[0], y0), (x0 + s, c[1]), (c[0], y0 + s), (x0, c[1])], exact=True)
    if shape == "arch":
        pts = [(x0, y0 + s - s * 0.06), (x0, c[1])]
        for k in range(1, 48):
            a = math.pi + math.pi * k / 48
            pts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
        pts += [(x0 + s, c[1]), (x0 + s, y0 + s - s * 0.06), (x0 + s - s * 0.06, y0 + s), (x0 + s * 0.06, y0 + s)]
        return sd_poly(cv, pts, exact=True)
    if shape == "hex_pointy":
        return sd_poly(cv, [(c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)))
                            for a in range(-90, 270, 60)], exact=True)
    if shape == "hex_flat":
        return sd_poly(cv, [(c[0] + r * math.cos(math.radians(a)), c[1] + r * 0.92 * math.sin(math.radians(a)))
                            for a in range(0, 360, 60)], exact=True)
    raise ValueError(shape)


def slot_fill(shape: str):
    """128x128 @2x: the recess. Lacquer #35261A -> #110B08, an inner radial pool #6A4A2A at 0.35
    (icons sit in a pool of light) and a soft rim shadow so the floor reads sunk under the rim."""
    cv = Cv(64, 64)
    sd = shape_sd(cv, shape, 0, 0, 64)
    col = lacquer_col(cv, "#35261A", "#110B08", sdf=sd, edge_dark=0.3, edge_w=14, streak=3.0, grain=1.6, sheen=0.0,
                      seed=31 + 17 * SHAPES.index(shape))
    r = np.hypot((cv.x - 32) / 30.0, (cv.y - 30) / 30.0)
    pool = np.clip(1 - r, 0, 1) ** 1.4 * 0.35
    col = col * (1 - pool[..., None]) + rgb("#6A4A2A")[None, None, :] * pool[..., None]
    cv.over(col, cv.cov(sd))
    # the rim casts a soft shadow onto the floor, deeper at the top-left
    sd_sh = shape_sd(cv, shape, 1.2, 1.8, 64 - 2.4) if shape != "round" else sd_circle(cv, 32.6, 33.0, 31.0)
    cv.over(rgb("ink"), inner_shadow(cv, sd_sh, 7.0, 0.5, power=1.8) * cv.cov(sd))
    return cv.image()


def slot_rim(shape: str):
    """128x128 @2x: a 1.6 px (at 64) gold bevel ring with a gold_sh edge and a 0.7 px gold_dk inner
    line 1.6 px inside it. Transparent inside."""
    cv = Cv(64, 64)
    sd = shape_sd(cv, shape, 0, 0, 64)
    cv.over(rgb("gold_dk"), cv.cov(band(sd, 3.2, 3.9)), 0.9)
    h = h_bead(sd, 0.0, 1.6)
    st = noise_of(cv, sd, 0.12, 7)
    col = shade(cv, h, 0.9, stops=GOLD, streak=st, streak_amt=0.03, base=0.14, vgrad=0.08)
    col = edge_line(col, sd, 0.5)
    cv.over(col, cv.cov(band(sd, 0.0, 1.6)))
    return cv.image()


def slot_mask(shape: str):
    cv = Cv(64, 64)
    sd = shape_sd(cv, shape, 0, 0, 64)
    cv.over(np.ones(3, np.float32), cv.cov(sd))
    return cv.image()


def slot_glow(shape: str):
    """192x192 @2x (96 logical, place centred on a 64-sized slot at 1.5x its size): the white ready
    halo, a 7 px blur of the shape with a 1 px spread, hollow under the slot floor; tint `ready_glow`."""
    cv = Cv(96, 96)
    sd = shape_sd(cv, shape, 16, 16, 64)
    cov = cv.cov(sd - 1.0)
    g = ndimage.gaussian_filter(cov, 3.5 * cv.k)
    g = np.clip(g * 1.25, 0, 1) * (1.0 - cv.cov(sd + 2.5))   # hollow: nothing under the slot's own floor
    cv.over(np.ones(3, np.float32), g)
    return cv.image()


def slot_sheen(shape: str):
    """128x128 @2x: the ready sheen, white 0.16 at the top fading out by 45 % of the height,
    inset 2 px from the rim."""
    cv = Cv(64, 64)
    sd = shape_sd(cv, shape, 0, 0, 64)
    a = np.clip(1 - cv.y / (64 * 0.45), 0, 1) ** 1.3 * 0.16
    cv.over(np.ones(3, np.float32), cv.cov(sd + 2.0) * a)
    return cv.image()


# ───────────────────────────── medallions ─────────────────────────────
def _studs(cv, cx, cy, r, n, size, offset_deg, color="stud"):
    """Lozenge studs on a bezel mid-line: each a raised bronze-ivory pyramid (lit from the top-left)
    seated in a dark gold_sh collar so it reads against the gold. Oriented along the radius."""
    base = rgb(color)
    for k in range(n):
        a = math.radians(offset_deg + k * 360.0 / n - 90.0)
        ux, uy = math.cos(a), math.sin(a)          # radial
        vx, vy = -uy, ux                           # tangential
        x, y = cx + r * ux, cy + r * uy
        hr, ht = size * 0.62, size * 0.46          # half-extent along the radius / the tangent
        outer = [(x + ux * (hr + 0.55), y + uy * (hr + 0.55)), (x + vx * (ht + 0.55), y + vy * (ht + 0.55)),
                 (x - ux * (hr + 0.55), y - uy * (hr + 0.55)), (x - vx * (ht + 0.55), y - vy * (ht + 0.55))]
        cv.over(rgb("gold_sh"), cv.cov(sd_poly(cv, outer, exact=True)), 0.95)
        tip = [(x + ux * hr, y + uy * hr), (x + vx * ht, y + vy * ht), (x - ux * hr, y - uy * hr),
               (x - vx * ht, y - vy * ht)]
        for i in range(4):   # four facets meeting at the apex, shaded by their facing
            p, q = tip[i], tip[(i + 1) % 4]
            mx, my = (p[0] + q[0]) / 2 - x, (p[1] + q[1]) / 2 - y
            L = math.hypot(mx, my) or 1.0
            lit = (-0.55 * mx - 0.85 * my) / L
            k_ = 0.86 + 0.3 * lit
            cv.over(np.clip(base * k_ + (0.1 if lit > 0.3 else 0.0), 0, 1),
                    cv.cov(sd_poly(cv, [p, q, (x, y)], exact=True)))


def medallion_hearth():
    """256x256 @2x -> 128: the Hearth medallion's metal. Outside in: a 4.5 px gilt bezel with a
    gold_sh edge and 8 lozenge studs (5.2 px, #E9D3A0) on its mid-line offset 22.5 deg; the 5 px ult
    trough left CLEAR (the conic molten fill shows through) with ten tick marks at every 10 % from
    12 o'clock (#140C08 at 0.85) and a baked recess shadow; a 1.8 px inner gilt rim. Clear inside
    r 52.7 (the P band and the portrait window are code)."""
    cv = Cv(128, 128)
    c = 64.0
    sd = sd_circle(cv, c, c, 64.0)
    d = np.hypot(cv.x - c, cv.y - c)
    ang = (np.degrees(np.arctan2(cv.x - c, -(cv.y - c))) + 360.0) % 360.0   # 0 at 12 o'clock, clockwise
    # trough recess: shadow from the bezel (offset down-right) and from the inner rim
    trough = (d <= 59.5) & (d >= 54.5)
    sh_out = np.clip(1 - (59.5 - np.hypot(cv.x - c - 0.6, cv.y - c - 0.9)) / 1.9, 0, 1) ** 1.6 * 0.5
    sh_in = np.clip(1 - (np.hypot(cv.x - c + 0.3, cv.y - c + 0.5) - 54.5) / 1.1, 0, 1) ** 1.5 * 0.3
    tr_cov = cv.cov(np.maximum(d - 59.5, 54.5 - d))
    cv.over(rgb("ink"), np.maximum(sh_out, sh_in) * tr_cov)
    # ticks
    tick = np.minimum(np.abs(((ang + 18.0) % 36.0) - 18.0) * (math.pi / 180.0) * d, 9.0)   # arc distance to a tick
    cv.over(rgb("#140C08"), np.clip(0.5 - (tick - 0.45) * cv.k, 0, 1) * tr_cov * trough, 0.85)
    # inner shadow falling onto the P band / portrait window from the inner rim
    win = np.clip(1 - (52.7 - np.hypot(cv.x - c - 0.4, cv.y - c - 0.8)) / 3.2, 0, 1) ** 2 * 0.45
    cv.over(rgb("ink"), win * cv.cov(d - 52.7))
    # inner gilt rim
    h = h_bead(sd, 64 - 54.5, 64 - 52.7)
    col = shade(cv, h, 0.9, stops=GOLD, base=0.18, vgrad=0.06)
    col = edge_line(col, band(sd, 64 - 54.5, 64 - 52.7), 0.35, amount=0.6)
    cv.over(col, cv.cov(band(sd, 64 - 54.5, 64 - 52.7)))
    # the bezel
    h = h_bead(sd, 0.0, 4.5, groove=0.16, groove_at=0.74, groove_w=0.05)
    st = noise_of(cv, sd, 0.12, 71)
    col = shade(cv, h, 2.0, stops=GOLD, streak=st, streak_amt=0.03, base=0.14, vgrad=0.08)
    col = edge_line(col, sd, 0.9)
    col = edge_line(col, -(sd + 4.5), 0.5, amount=0.6)
    cv.over(col, cv.cov(band(sd, 0.0, 4.5)))
    _studs(cv, c, c, 61.75, 8, 5.2, 22.5)
    return cv.image()


def medallion_rim(size: float = 64.0, rim: float = 3.0, studs: int = 0, groove: float = 0.16):
    """A plain gilt medallion rim (party, pins, crest, cards): a bevelled ring `rim` px wide with a
    gold_sh edge and a soft inner shadow on the window. Transparent inside."""
    cv = Cv(size, size)
    c = size / 2
    sd = sd_circle(cv, c, c, c)
    d = np.hypot(cv.x - c - 0.3, cv.y - c - 0.6)
    ish = np.clip(1 - (c - rim - d) / max(2.4, rim * 0.9), 0, 1) ** 2 * 0.5
    cv.over(rgb("ink"), ish * cv.cov(sd + rim - 0.2))
    h = h_bead(sd, 0.0, rim, groove=groove if rim >= 3.0 else 0.0, groove_at=0.72, groove_w=0.05)
    st = noise_of(cv, sd, 0.1, int(size * 7))
    col = shade(cv, h, rim * 0.5, stops=GOLD, streak=st, streak_amt=0.03, base=0.14, vgrad=0.08)
    col = edge_line(col, sd, min(0.7, rim * 0.3))
    col = edge_line(col, -(sd + rim), min(0.45, rim * 0.2), amount=0.55)
    cv.over(col, cv.cov(band(sd, 0.0, rim)))
    if studs:
        _studs(cv, c, c, c - rim / 2, studs, max(3.6, rim * 1.1), 22.5)
    return cv.image()


def enamel_disc(size: float = 100.0):
    """A greyscale enamel disc (the boon-card apex medallion, the boon chip, shrine pins): bright at
    the upper centre falling to 50 % at the rim, with a glassy highlight crescent. Tint with the god
    colour through ImageNode.color; the icon and the rim sit on top."""
    cv = Cv(size, size)
    c = size / 2
    sd = sd_circle(cv, c, c, c)
    r = np.hypot((cv.x - c) / c, (cv.y - c * 0.82) / c)
    v = 1.0 - 0.5 * np.clip(r, 0, 1) ** 1.3
    col = np.repeat(v[..., None], 3, axis=2)
    cv.over(col, cv.cov(sd))
    # a glassy crescent highlight near the top-left rim
    hl = np.hypot(cv.x - c + c * 0.1, cv.y - c + c * 0.14)
    cres = np.clip(1 - np.abs(hl - c * 0.80) / (c * 0.07), 0, 1) * np.clip((c * 0.5 - (cv.y - c * 0.2)) / (c * 0.5), 0, 1)
    ang = np.arctan2(cv.y - c, cv.x - c)
    cres *= smoothstep(-2.9, -2.3, ang) * (1 - smoothstep(-1.2, -0.6, ang))
    cv.over(np.ones(3, np.float32), cres * 0.35 * cv.cov(sd))
    return cv.image()


# ───────────────────────────── dash lozenges, armour plates, gem sockets ─────────────────────────────
def dash_lozenge(state: str):
    """36x36 @2x (18 logical, the cut lozenge r 7.2 centred): full = a lit #FFE7A6 cut gem in a thin
    gilt setting; empty = a dark #2A1F18 recess in the same setting (the refill arc is code);
    mask = the white lozenge (clip-reveal for the refill)."""
    cv = Cv(18, 18)
    c = 9.0
    r = 7.2
    pts = [(c, c - r), (c + r * 0.8, c), (c, c + r), (c - r * 0.8, c)]
    sd = sd_poly(cv, pts, exact=True)
    if state == "mask":
        cv.over(np.ones(3, np.float32), cv.cov(sd))
        return cv.image()
    if state == "full":
        gem_lozenge(cv, c, c, r * 0.8, r, "#FFE7A6", setting=True, setting_w=1.1, glint=1.0)
        return cv.image()
    col = lacquer_col(cv, "#2A1F18", "#0E0907", sdf=sd, edge_dark=0.4, edge_w=3, streak=0, grain=1.0, sheen=0.0,
                      seed=5)
    cv.over(col, cv.cov(sd))
    h = h_bead(sd, 0.0, 1.1)
    cv.over(edge_line(shade(cv, h, 0.6, stops=GOLD, base=0.08, gain=0.6, vgrad=0.0), sd, 0.3),
            cv.cov(band(sd, 0.0, 1.1)))
    return cv.image()


def armor_plate(full: bool):
    """24x18 @2x (12x9 logical), 3-slice: left/right 8 px (4 logical) hold the 3 px-skewed ends, the
    middle stretches to any plate width. Full: the steel ramp; empty: #1A1512 with a steel_dk line."""
    cv = Cv(12, 9)
    pts = [(3.0, 0.3), (11.7, 0.3), (9.0, 8.7), (0.3, 8.7)]
    sd = sd_poly(cv, pts, exact=True)
    if full:
        h = np.clip(-sd / 1.2, 0, 1)
        h = np.sin(h * np.pi / 2)
        col = shade(cv, h, 1.0, stops=STEEL, base=0.2, gain=0.65, vgrad=0.18, spec=0.6)
        col = edge_line(col, sd, 0.4, color="#1B1F24", amount=0.9)
        cv.over(col, cv.cov(sd))
    else:
        cv.over(rgb("#1A1512"), cv.cov(sd))
        cv.over(rgb("#4E5660"), cv.cov(band(sd, 0.0, 0.6)), 0.9)
    return cv.image()
