"""FX overlays, bar pieces and world/edge markers (UI_STYLE §6, §8.2).

Bars are canonically built in code (trough -> ghost -> fill -> shine -> rim, §11.4). The bar
textures here are optional upgrades for the same stack: fills with a baked glassy sheen, a
leading-edge meniscus, and 9-slice trough/rim pieces with a real bevel.
"""
from __future__ import annotations

import math

import numpy as np

from .core import (GOLD, Cv, band, edge_line, h_bead, h_dome, inner_shadow, noise_of, ramp, rgb,
                   sd_circle, sd_poly, sd_rrect, shade, smoothstep)
from . import ornaments as orn


# ───────────────────────────── overlays ─────────────────────────────
def hatch_ward():
    """20x44 @2x (10x22 logical), `Tiled { tile_x: true, stretch_value: 1.0 }`: the ward hatch. 45 deg
    stripes in `ward` at 0.9, 3.4 px wide on a 10 px period, a touch brighter at the top. Seamless in x."""
    cv = Cv(10, 22)
    s = (cv.x + cv.y) % 10.0
    line = np.clip(np.minimum(s, 3.4 - s) * cv.k + 0.5, 0, 1) * (s < 3.4 + 1.0 / cv.k)
    line = np.maximum(line, np.clip((s - 10.0 + 0.5 / cv.k) * cv.k + 0.5, 0, 1))
    shade_v = 1.04 - 0.16 * (cv.y / 22.0)
    col = rgb("ward")[None, None, :] * shade_v[..., None]
    cv.over(np.clip(col, 0, 1), line, 0.9)
    return cv.image()


def sheen():
    """128x256 @2x (64x128 logical): a soft diagonal white band (Godforged sheen, ready gleam),
    tilted 24 deg, with a brighter thin core. Slide it across a node (clipped) in code."""
    cv = Cv(64, 128)
    ang = math.radians(24)
    u = (cv.x - 32) * math.cos(ang) + (cv.y - 64) * math.sin(ang)
    wide = np.exp(-(u / 9.0) ** 2) * 0.38
    core = np.exp(-(u / 2.2) ** 2) * 0.42
    fade = smoothstep(0, 18, cv.y) * smoothstep(0, 18, 128 - cv.y)
    cv.over(np.ones(3, np.float32), np.clip((wide + core) * fade, 0, 1))
    return cv.image()


def spark4():
    """64x64 @2x (32 logical, show at 16-24): the crit spark. A four-point star with long cardinal
    rays, short diagonals, a white-hot core and an ichor glow."""
    cv = Cv(32, 32)
    c = 16.0
    d = np.hypot(cv.x - c, cv.y - c)
    glow = np.exp(-(d / 6.5) ** 2) * 0.55
    cv.over(rgb("ichor_glow"), glow)
    orn.star4(cv, c, c, 15.0, 1.9, "ichor", diag=0.42)
    orn.star4(cv, c, c, 11.0, 1.1, "#FFFDF4", diag=0.36)
    cv.over(np.ones(3, np.float32), np.exp(-(d / 2.2) ** 2))
    return cv.image()


# ───────────────────────────── bars (optional texture path) ─────────────────────────────
BAR_FILLS = {
    "hp": [(0.0, "hp_lt"), (0.55, "hp"), (1.0, "hp_dk")],
    "ghost_hp": [(0.0, "#F7C79A"), (0.5, "hp_ghost"), (1.0, "#C98A52")],
    "boss": [(0.0, "#FF7A4A"), (0.5, "#C8261E"), (1.0, "#5E0A08")],
    "ghost_boss": [(0.0, "#FCDDA8"), (0.5, "#F7C98A"), (1.0, "#C9955A")],
    "elite": [(0.0, "#F06A4A"), (1.0, "#9A1E1A")],
    "molten": [(0.0, "#FFF6DA"), (0.3, "#FFC95A"), (0.7, "#E8942E"), (1.0, "#7A3E12")],
    "surge": [(0.0, "#FFB08A"), (1.0, "#E8602E")],
    "white": [(0.0, "#FFFFFF"), (1.0, "#C8C8C8")],
}


def bar_fill(kind: str):
    """16x44 @2x (8x22 logical), stretch: a vertical gradient with a glassy sheen band at 22 % of the
    height and a darker lower lip. `white` is for tinting (party share bars in player colour)."""
    cv = Cv(8, 22)
    t = cv.y / 22.0
    col = ramp(t, BAR_FILLS[kind])
    hl = np.exp(-((t - 0.22) / 0.10) ** 2) * 0.22
    col = col + hl[..., None]
    col = col * (1.0 - 0.18 * smoothstep(0.82, 1.0, t))[..., None]
    cv.over(np.clip(col, 0, 1), np.ones_like(t))
    return cv.image()


def bar_meniscus():
    """8x44 @2x (4x22 logical): the fill's leading edge, a 1.6 px #FFF4DC line with a soft falloff
    to the left; place its right edge on the fill's end."""
    cv = Cv(4, 22)
    d = 4.0 - 0.8 - cv.x
    a = np.clip(1 - np.abs(d) / 0.8, 0, 1) * 0.95 + np.exp(-(np.maximum(d, 0) / 1.4) ** 2) * 0.35
    fade = smoothstep(0, 3, cv.y) * smoothstep(0, 3, 22 - cv.y)
    cv.over(rgb("#FFF4DC"), np.clip(a * (0.6 + 0.4 * fade), 0, 1))
    return cv.image()


def bar_trough(thin: bool = False):
    """40x40 @2x (20 logical), slice 10 (5 logical): the recessed trough `#0E0907` at 0.88 with an
    inner shadow from the top; r 4. `thin`: 16x16 (8 logical), slice 3 logical, r 2, for 6-10 px bars."""
    S, R, B = (8.0, 2.0, 3.0) if thin else (20.0, 4.0, 5.0)
    cv = Cv(S, S)
    sd = sd_rrect(cv, 0, 0, S, S, R)
    cv.over(rgb("#0E0907"), cv.cov(sd), 0.88)
    sh = inner_shadow(cv, sd_rrect(cv, 0, 1.2 if not thin else 0.6, S, S + 2, R), 3.0 if not thin else 1.5, 0.6)
    cv.over(rgb("#000000"), sh * cv.cov(sd))
    return cv.image()


def bar_rim(thin: bool = False):
    """The bar's gilt rim, clear inside (goes on top of the fills). 40x40 @2x, slice 10 (5 logical),
    r 4, 1.4 px bevel. `thin`: 16x16 @2x, slice 3 logical, r 2, 0.8 px."""
    S, R, W = (8.0, 2.0, 0.8) if thin else (20.0, 4.0, 1.4)
    cv = Cv(S, S)
    sd = sd_rrect(cv, 0, 0, S, S, R)
    h = h_bead(sd, 0.0, W)
    st = noise_of(cv, sd, 0.1, 3)
    col = shade(cv, h, W * 0.6, stops=GOLD, streak=st, streak_amt=0.03, base=0.16, vgrad=0.1)
    col = edge_line(col, sd, 0.4 if not thin else 0.3)
    cv.over(col, cv.cov(band(sd, 0.0, W)))
    return cv.image()


# ───────────────────────────── markers ─────────────────────────────
def pin_frame(tint: bool):
    """112x112 @2x (56 logical): the edge-pin frame, a Ø34 ring (2 px) centred at (28, 28) with an
    outward nub (11 px) pointing UP; rotate the node about its centre to aim the nub at the target.
    `tint` = white (tint with the player colour or `danger`); else gilt."""
    cv = Cv(56, 56)
    c = 28.0
    ring = sd_circle(cv, c, c, 17.0)
    nub = sd_poly(cv, [(c, 1.2), (c + 5.2, 12.4), (c, 10.6), (c - 5.2, 12.4)], exact=True)
    nub_neck = sd_poly(cv, [(c - 3.2, 12.0), (c + 3.2, 12.0), (c + 2.2, 13.6), (c - 2.2, 13.6)], exact=True)
    if tint:
        cv.over(np.ones(3, np.float32), cv.cov(band(ring, 0.0, 2.0)))
        cv.over(np.ones(3, np.float32), cv.cov(np.minimum(nub, nub_neck)))
        cv.over(rgb("#9A9A9A"), cv.cov(band(np.minimum(nub, nub_neck), 0.0, 0.5)), 0.6)
        return cv.image()
    sd = np.minimum(np.minimum(nub, nub_neck), band(ring, 0.0, 2.0))
    h = np.maximum(h_bead(ring, 0.0, 2.0), h_dome(np.minimum(nub, nub_neck), 1.3))
    col = shade(cv, h, 1.0, stops=GOLD, base=0.16, vgrad=0.05)
    col = edge_line(col, sd, 0.45)
    cv.over(col, cv.cov(sd))
    return cv.image()


def pin_disc():
    """68x68 @2x (Ø34): the pin medallion body, a radial #3A291C -> #0D0806 disc at 0.92."""
    cv = Cv(34, 34)
    c = 17.0
    sd = sd_circle(cv, c, c, 17.0)
    r = np.clip(np.hypot(cv.x - c, cv.y - c * 0.8) / 17.0, 0, 1)
    col = ramp(r, [(0.0, "#3A291C"), (1.0, "#0D0806")])
    cv.over(col, cv.cov(sd), 0.92)
    return cv.image()


def ally_chevron():
    """16x10 @2x (8x5 logical): the ally tag's chevron pointing down, white (tint: player colour)."""
    cv = Cv(8, 5)
    sd = sd_poly(cv, [(0.2, 0.3), (4.0, 2.6), (7.8, 0.3), (4.0, 4.8)], exact=True)
    cv.over(np.ones(3, np.float32), cv.cov(sd))
    return cv.image()


def prompt_tail():
    """28x18 @2x (14x9 logical): the prompt plate's tail pointing down. Lacquer (lac1 at 0.8) with
    the soft-gold 1.1 px hairline on both slanted edges; its top edge (y 0-1) tucks under the plate."""
    cv = Cv(14, 9)
    pts = [(0.0, 0.0), (14.0, 0.0), (7.0, 8.4)]
    sd = sd_poly(cv, pts, exact=True)
    cv.over(rgb("lac1"), cv.cov(sd), 0.8)
    ty = np.clip(cv.y / 8.4, 0, 1)
    rc = ramp(ty, [(0.0, "gold_lt"), (0.5, "gold_md"), (1.0, "gold_dk")])
    edge = band(sd, 0.0, 1.1)
    cv.over(rc, cv.cov(edge) * (cv.y > 0.9), 0.55)
    return cv.image()


def threat_pip(lit: bool):
    """30x22 @2x (15x11 logical): a tracker threat chevron pip, lit in the ember `threat` ramp
    (#FFC95A -> #E8602E) or dark."""
    cv = Cv(15, 11)
    pts = [(0.6, 0.6), (8.0, 0.6), (14.4, 5.5), (8.0, 10.4), (0.6, 10.4), (6.6, 5.5)]
    sd = sd_poly(cv, pts, exact=True)
    if lit:
        col = ramp(cv.y / 11.0, [(0.0, "#FFD27A"), (0.5, "#FFC95A"), (1.0, "#E8602E")])
        h = h_dome(sd, 1.0)
        lit_t = shade(cv, h, 0.7, stops=[(0.0, "#000000"), (1.0, "#FFFFFF")], base=0.4, gain=0.5, vgrad=0.0,
                      spec=0.3)
        col = np.clip(col * (0.7 + 0.5 * lit_t), 0, 1)
        cv.over(col, cv.cov(sd))
        cv.over(rgb("#3A1606"), cv.cov(band(sd, 0.0, 0.5)), 0.8)
    else:
        cv.over(rgb("#1E1510"), cv.cov(sd), 0.9)
        cv.over(rgb("gold_dk"), cv.cov(band(sd, 0.0, 0.6)), 0.8)
    return cv.image()
