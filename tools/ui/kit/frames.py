"""Frames: 9-slice panel and card rims, buttons, keycaps, pills, chips, ribbons, tooltips, the
minimap frame and the shrine-niche boon card layers (UI_STYLE §7, §8.1, §8.2).

9-slice rule: anything inside a stretched segment is invariant along the stretch direction. Metal
streaks therefore follow the SDF (they run along the frame), lacquer streaks depend on y only, and
there is no 2D grain in sliced textures.
"""
from __future__ import annotations

import math

import numpy as np

from .core import (BRONZE, GOLD, RARITY, Cv, band, chamfer_pts, edge_line, gem_lozenge, h_bead, inner_shadow, lacquer_col, lattice_lines, mixc, noise_of, rgb, sd_poly,
                   sd_rrect, shade, smoothstep)
from . import ornaments as orn


def _bead_ring(cv, sd, a, b, stops=GOLD, amp=None, groove=0.0, seed=1, streak_amt=0.035, edge_out=0.7,
               edge_in=0.45, alpha=1.0, **kw):
    """A bevelled metal ring on the band [a, b] of a shape, brushed along its length."""
    h = h_bead(sd, a, b, groove=groove)
    st = noise_of(cv, sd, 0.12, seed)
    col = shade(cv, h, amp if amp is not None else (b - a) * 0.55, stops=stops, streak=st, streak_amt=streak_amt,
                **kw)
    sdb = band(sd, a, b)
    if edge_out:
        col = edge_line(col, sd + a, edge_out)            # the outer boundary of the band
    if edge_in:
        col = edge_line(col, -(sd + b), edge_in, amount=0.6)  # the inner boundary
    cv.over(col, cv.cov(sdb), alpha)
    return sdb


# ───────────────────────────── gilt panel (Forge, help, detail card, tooltip, door) ─────────────────────────────
def gilt_panel(bronze: bool = False):
    """192x192 @2x, slice 48 (24 logical). A 3.2 px bevelled ring with an engraved groove, a 4 px
    gap, a 1 px bronze keyline, r 10, a baked 10 px inner shadow and a gold_sh edge. Centre clear."""
    cv = Cv(96, 96)
    R, W = 10.0, 3.2
    sd = sd_rrect(cv, 0, 0, 96, 96, R)
    # directional inner shadow (the frame shades the lacquer, more at the top)
    s_off = 1.6
    sd_sh = sd_rrect(cv, W, W + s_off, 96 - W, 96 - W + s_off * 0.35, R - W)
    a = inner_shadow(cv, sd_sh, 10.0, 0.62, power=1.7)
    a = np.maximum(a, np.clip((sd + W) * cv.k + 0.5, 0, 1) * 0.62)  # solid under the ring edge
    cv.over(rgb("ink"), a * cv.cov(sd))
    # a whisper of warm bounce light just inside the keyline, lifts the lacquer edge
    stops = BRONZE if bronze else GOLD
    # keyline: 1 px bronze at inset 7.2
    sd_k = sd_rrect(cv, W + 4.0, W + 4.0, 96 - W - 4.0, 96 - W - 4.0, 4.0)
    _bead_ring(cv, sd_k, 0.0, 1.0, stops=BRONZE, amp=0.5, streak_amt=0.0, edge_out=0.0, edge_in=0.0,
               alpha=0.92, base=0.22, gain=0.66, vgrad=0.08)
    # the gilt ring
    _bead_ring(cv, sd, 0.0, W, stops=stops, amp=1.25, groove=0.42, seed=5, vgrad=0.08)
    return cv.image()


# ───────────────────────────── rarity card rims ─────────────────────────────
def _enamel_line(cv, sd, a, b, color, alpha=1.0, lift=0.38, drop=0.32):
    """A glassy enamel line: the colour, lighter on its upper edge, deeper below, with a hot core."""
    h = h_bead(sd, a, b)
    c = rgb(color)
    t = shade(cv, h, (b - a) * 0.6, stops=[(0.0, mixc(c, "#000000", drop)), (0.45, c), (0.8, mixc(c, "#FFFFFF", lift)),
                                           (1.0, mixc(c, "#FFFFFF", 0.7))], vgrad=0.0, spec=0.35, shin=18)
    cv.over(t, cv.cov(band(sd, a, b)), alpha)


def gilt_card(rarity: str):
    """96x96 @2x, slice 24 (12 logical), r 8. Common: parchment-grey line. Rare: rarity line with
    bright corner arcs. Epic: + inner 0.8 px line and small corner gems. Godforged: a 2.2 px metal-gold
    ring with an inner gold line."""
    cv = Cv(48, 48)
    R = 8.0
    sd = sd_rrect(cv, 0, 0, 48, 48, R)
    col = RARITY[rarity]
    # a dark separation line outside-in so the rim reads on any backdrop
    cv.over(rgb("ink"), cv.cov(band(sd, 0.0, 0.6)), 0.75)
    if rarity == "godforged":
        _bead_ring(cv, sd, 0.2, 2.4, stops=GOLD, amp=0.9, seed=11, vgrad=0.06)
        sdi = sd_rrect(cv, 3.6, 3.6, 44.4, 44.4, R - 3.6 + 0.8)
        cv.over(np.array(rgb("gold_lt")), cv.cov(band(sdi, 0.0, 0.8)), 0.58)
        # corner sparks: tiny 4-point stars on the rounded corners
        for cx, cy in ((2.6, 2.6), (45.4, 2.6), (2.6, 45.4), (45.4, 45.4)):
            orn.star4(cv, cx, cy, 3.0, 0.8, "#FFF2C8", alpha=0.95)
        return cv.image()
    # the rarity line: full-length at a quieter alpha, brightened into corner arcs
    base_alpha = {"common": 0.78, "rare": 0.62, "epic": 0.66}[rarity]
    _enamel_line(cv, sd, 0.3, 1.7, col, alpha=base_alpha)
    # corner accents: the same line again, bright, masked to the corner arcs (inside the slice corner)
    cx = np.minimum(cv.x, 48 - cv.x)
    cy = np.minimum(cv.y, 48 - cv.y)
    m = (1 - smoothstep(9.0, 11.5, np.maximum(cx, cy)))
    c2 = Cv(48, 48)
    _enamel_line(c2, sd, 0.3, 1.9, col, alpha=1.0, lift=0.5)
    cv.px = cv.px * (1 - (c2.px[..., 3] * m)[..., None]) + c2.px * m[..., None]
    if rarity == "epic":
        sdi = sd_rrect(cv, 3.4, 3.4, 44.6, 44.6, R - 3.4 + 0.6)
        _enamel_line(cv, sdi, 0.0, 0.8, col, alpha=0.55, lift=0.3)
        for gx, gy in ((2.2, 2.2), (45.8, 2.2), (2.2, 45.8), (45.8, 45.8)):
            gem_lozenge(cv, gx, gy, 2.6, 2.6, col, setting_w=0.55)
    return cv.image()


def card_selected():
    """112x112 @2x, slice 28 (14 logical). The 2.2 px metal-gold selection ring, 5 px outside the
    card (ring radius 13 = card r 8 + 5), with a faint ready-glow haze baked into the gap."""
    cv = Cv(56, 56)
    sd = sd_rrect(cv, 0, 0, 56, 56, 13.0)
    # warm haze in the gap, strongest against the ring
    t = np.clip((-sd - 2.2) / 5.0, 0, 1)
    cv.over(rgb("ready_glow"), (1 - t) ** 1.5 * 0.42 * cv.cov(sd + 2.2))
    _bead_ring(cv, sd, 0.0, 2.2, stops=GOLD, amp=1.0, seed=17, base=0.24, gain=0.7, vgrad=0.08)
    return cv.image()


# ───────────────────────────── buttons, chips, keycaps, pills, ribbons ─────────────────────────────
def _chamfer_sd(cv, w, h, c, inset=0.0):
    return sd_poly(cv, chamfer_pts(inset, inset, w - inset, h - inset, max(0.0, c - inset * 0.414)), exact=True)


def _gold_body(cv, sd, h_total, bright=0.0, pressed=False, seed=21):
    """A gold ingot face: the §8.2 primary gradient (#FFE7A0 -> #E8B04E -> #9A6224) with a rolled
    bevel at the rim (lit top-left, shaded bottom-right), horizontal brushing (y only, slice-safe)
    and a fine inner highlight line. Pressed inverts the gradient and the bevel."""
    ty = np.clip(cv.y / h_total, 0, 1)
    stops = [(0.0, "#FFE7A0"), (0.5, "#E8B04E"), (1.0, "#9A6224")]
    if pressed:
        stops = [(0.0, "#A87230"), (0.5, "#D59E46"), (1.0, "#EFC56E")]
    base = np.stack([np.interp(ty, [s[0] for s in stops], [rgb(s[1])[i] for s in stops]) for i in range(3)], -1)
    n = np.repeat(np.interp(cv.y[:, 0], np.linspace(0, h_total, 200),
                            np.random.default_rng(seed).standard_normal(200) * 0.022)[:, None], cv.W, axis=1)
    base = np.clip(base * (1.0 + n[..., None] + bright), 0, 1)
    # rolled bevel over the outer 2.6 px: the SDF gradient gives the facing of each edge
    bw = 2.6
    p = np.clip(-sd / bw, 0, 1)
    gy, gx = np.gradient(sd)
    gl = np.hypot(gx, gy) + 1e-9
    nx, ny = gx / gl, gy / gl                     # the outward edge normal
    facing = -(nx * -0.55 + ny * -0.85)           # < 0 on edges facing the light (top-left)
    facing = -facing if not pressed else facing
    w = (1 - p) ** 1.4 * (p > 0)
    hi = np.array(rgb("#FFF6D8"))
    lo = np.array(rgb("#6A3E14"))
    up = np.clip(facing, 0, 1)[..., None] * w[..., None]
    dn = np.clip(-facing, 0, 1)[..., None] * w[..., None]
    base = base * (1 - up * 0.75) + hi * up * 0.75
    base = base * (1 - dn * 0.6) + lo * dn * 0.6
    return np.clip(base, 0, 1)


def button(kind: str, state: str = "normal"):
    """128x96 @2x, slice 32 (16 logical), chamfer 9 (64x48 logical).
    kind: primary | secondary | disabled; state: normal | hover | pressed."""
    W, H, C = 64.0, 48.0, 9.0
    cv = Cv(W, H)
    sd = _chamfer_sd(cv, W, H, C)
    if kind == "primary":
        bright = {"normal": 0.0, "hover": 0.07, "pressed": -0.08}[state]
        face = _gold_body(cv, sd, H, bright=bright, pressed=(state == "pressed"))
        cv.over(face, cv.cov(sd))
        if state != "pressed":   # the top sheen band
            sh = np.clip(1 - cv.y / (H * 0.42), 0, 1) ** 2 * (0.30 if state == "hover" else 0.22)
            cv.over(np.array([1.0, 0.98, 0.9], np.float32), sh * cv.cov(sd + 1.6))
        # the dark #3A2208 rim with a lighter inner hairline
        cv.over(rgb("#3A2208"), cv.cov(band(sd, 0.0, 1.2)))
        cv.over(rgb("#FFF1C4"), cv.cov(band(sd, 1.2, 1.9)), 0.5 if state != "pressed" else 0.18)
        return cv.image()
    if kind == "disabled":
        col = lacquer_col(cv, "#221A15", "#1A1411", sdf=sd, edge_dark=0.25, edge_w=10, streak=3.0, sheen=0.0,
                          slice_safe=True, seed=31)
        cv.over(col, cv.cov(sd))
        cv.over(rgb("#4E4034"), cv.cov(band(sd, 0.0, 1.3)))
        cv.over(rgb("#0A0706"), cv.cov(band(sd, 1.3, 1.9)), 0.5)
        return cv.image()
    # secondary: lacquer with a soft gold rim
    top, bot = {"normal": ("lac2", "lac1"), "hover": ("#3C2B1F", "#1B130E"), "pressed": ("#120C09", "#241A13")}[state]
    col = lacquer_col(cv, top, bot, sdf=sd, edge_dark=0.3, edge_w=12, streak=4.0,
                      sheen=0.0 if state == "pressed" else (0.10 if state == "hover" else 0.07), slice_safe=True,
                      seed=33)
    cv.over(col, cv.cov(sd))
    if state == "hover":   # a warm inner glow along the rim
        t = np.clip(-sd / 7.0, 0, 1)
        cv.over(rgb("ichor_glow"), (1 - t) ** 2 * 0.22 * cv.cov(sd))
    _bead_ring(cv, sd, 0.0, 1.8, stops=GOLD, amp=0.8, seed=35, streak_amt=0.02,
               base=0.30 if state == "hover" else (0.08 if state == "pressed" else 0.18),
               gain=0.72 if state != "pressed" else 0.5, vgrad=0.08)
    # top inner highlight hairline (fades out by 35 % of the height)
    hl = np.clip(1 - cv.y / (H * 0.35), 0, 1) * (0.28 if state != "pressed" else 0.0)
    cv.over(rgb("gold_hi"), hl * cv.cov(band(sd, 1.8, 2.5)))
    return cv.image()


def chip(state: str = "normal"):
    """64x52 @2x, slice 16 (8 logical), chamfer 6: the small 26-tall chip (REROLL, filter chips)."""
    W, H, C = 32.0, 26.0, 6.0
    cv = Cv(W, H)
    sd = _chamfer_sd(cv, W, H, C)
    if state == "disabled":
        cv.over(lacquer_col(cv, "#1E1713", "#15100D", sdf=sd, edge_dark=0.2, edge_w=6, streak=2.0, sheen=0.0,
                            slice_safe=True, seed=41), cv.cov(sd))
        cv.over(rgb("#4E4034"), cv.cov(band(sd, 0.0, 1.1)))
        return cv.image()
    top, bot = ("#3A2A1E", "#1A120D") if state == "hover" else ("#2C2018", "#140E0A")
    cv.over(lacquer_col(cv, top, bot, sdf=sd, edge_dark=0.25, edge_w=7, streak=3.0,
                        sheen=0.09 if state == "hover" else 0.06, slice_safe=True, seed=43), cv.cov(sd))
    _bead_ring(cv, sd, 0.0, 1.3, stops=GOLD, amp=0.6, seed=45, streak_amt=0.0,
               base=0.28 if state == "hover" else 0.14, vgrad=0.08)
    return cv.image()


def keycap(pressed: bool = False):
    """48x48 @2x, slice 16 (8 logical), r 4: #3A2B1E -> #16100B face, a 1 px soft gold rim and a 3 px
    bottom lip at 0.45 black. Text sits centred on the face (1.5 px above the node centre)."""
    S = 24.0
    cv = Cv(S, S)
    lip = 1.2 if pressed else 3.0
    sd = sd_rrect(cv, 0, 0, S, S, 4.0)
    # the key body (its side shows as the lip)
    body = lacquer_col(cv, "#241A12", "#120C08", sdf=sd, edge_dark=0.2, edge_w=6, streak=0, grain=0, sheen=0.0,
                       slice_safe=True)
    cv.over(body, cv.cov(sd))
    cv.over(rgb("#000000"), cv.cov(sd) * (cv.y > S - lip - 0.8), 0.45)
    # the face
    top_off = 1.8 if pressed else 0.0
    sdf_face = sd_rrect(cv, 0.0, top_off, S, S - lip, 4.0)
    face = lacquer_col(cv, "#3A2B1E" if not pressed else "#2E2218", "#16100B", y0=top_off, y1=S - lip, sdf=sdf_face,
                       edge_dark=0.18, edge_w=5, streak=2.0, grain=0, sheen=0.10 if not pressed else 0.03,
                       slice_safe=True, seed=51)
    cv.over(face, cv.cov(sdf_face))
    # soft gold rim around the face, brightest on top
    ring = band(sdf_face, 0.0, 1.0)
    ty = np.clip((cv.y - top_off) / (S - lip - top_off), 0, 1)
    rc = np.stack([np.interp(ty, [0, 0.5, 1], [rgb(c)[i] for c in ("gold_lt", "gold_md", "gold_dk")]) for i in range(3)],
                  -1)
    cv.over(rc, cv.cov(ring), 0.9 if not pressed else 0.7)
    cv.over(rgb("#FFF4D6"), cv.cov(band(sdf_face, 1.0, 1.5)) * np.clip(1 - ty / 0.3, 0, 1), 0.35)
    # outer dark edge for separation
    cv.over(rgb("ink"), cv.cov(band(sd, 0.0, 0.5)), 0.8)
    return cv.image()


def pill(outline: bool = False):
    """64x36 @2x, slice 18 (9 logical): a gold pill (kind pills, REPLACE tab). `outline`: a lacquer
    pill with a soft gold rim (filter chips)."""
    W, H = 32.0, 18.0
    cv = Cv(W, H)
    sd = sd_rrect(cv, 0, 0, W, H, 9.0)
    if outline:
        cv.over(lacquer_col(cv, "#2A1E16", "#120C09", sdf=sd, edge_dark=0.2, edge_w=5, streak=2.0, sheen=0.06,
                            slice_safe=True, seed=61), cv.cov(sd))
        _bead_ring(cv, sd, 0.0, 1.2, stops=GOLD, amp=0.6, seed=63, streak_amt=0.0, base=0.2, vgrad=0.1)
        return cv.image()
    face = _gold_body(cv, sd, H, bright=0.04)
    cv.over(face, cv.cov(sd))
    sh = np.clip(1 - cv.y / (H * 0.45), 0, 1) ** 2 * 0.25
    cv.over(np.array([1.0, 0.98, 0.9], np.float32), sh * cv.cov(sd + 1.2))
    cv.over(rgb("#3A2208"), cv.cov(band(sd, 0.0, 1.0)))
    cv.over(rgb("#FFF1C4"), cv.cov(band(sd, 1.0, 1.5)), 0.45)
    return cv.image()


def ribbon(metal_kind: str = "gilt"):
    """64x44 @2x, slice 22/10 (11 x 5 logical): the 22-tall chamfered rarity ribbon plaque (§7.2) in
    gilt or bronze: a lacquer plaque with a bevelled metal rim and small end notches."""
    W, H, C = 32.0, 22.0, 6.0
    cv = Cv(W, H)
    sd = _chamfer_sd(cv, W, H, C)
    stops = GOLD if metal_kind == "gilt" else BRONZE
    cv.over(lacquer_col(cv, "#2C2018", "#0F0A07", sdf=sd, edge_dark=0.3, edge_w=6, streak=2.5, sheen=0.07,
                        slice_safe=True, seed=71), cv.cov(sd))
    _bead_ring(cv, sd, 0.0, 1.5, stops=stops, amp=0.7, seed=73, streak_amt=0.0, base=0.2, vgrad=0.1)
    # a thin inner keyline
    sdi = _chamfer_sd(cv, W, H, C, inset=2.6)
    cv.over(rgb("gold_dk" if metal_kind == "gilt" else "#6E5234"), cv.cov(band(sdi, 0.0, 0.6)), 0.7)
    return cv.image()


def pchip():
    """60x36 @2x, fixed 30x18: the P chip, a lozenge plaque (pointed ends) with a gilt rim; the
    `P2`..`P4` label is text in the player colour, drawn by code."""
    W, H = 30.0, 18.0
    cv = Cv(W, H)
    pts = [(0.4, H / 2), (7.0, 0.4), (W - 7.0, 0.4), (W - 0.4, H / 2), (W - 7.0, H - 0.4), (7.0, H - 0.4)]
    sd = sd_poly(cv, pts, exact=True)
    cv.over(lacquer_col(cv, "#1E150F", "#080504", sdf=sd, edge_dark=0.25, edge_w=5, streak=2.0, sheen=0.05,
                        seed=81), cv.cov(sd))
    _bead_ring(cv, sd, 0.0, 1.5, stops=GOLD, amp=0.7, seed=83, streak_amt=0.0, base=0.2, vgrad=0.1)
    return cv.image()


# ───────────────────────────── tooltip and dashed outline ─────────────────────────────
def tooltip():
    """96x96 @2x, slice 32 (16 logical), r 6: a lighter gilt frame for hover tooltips and small
    detail cards (1.6 px bevelled ring, 3 px gap, a 0.8 px keyline, 6 px inner shadow, tiny corner
    lozenges). Centre clear; the code lacquer body sits under it."""
    cv = Cv(48, 48)
    R, W = 6.0, 1.6
    sd = sd_rrect(cv, 0, 0, 48, 48, R)
    sd_sh = sd_rrect(cv, W, W + 1.0, 48 - W, 48 - W + 0.3, R - W)
    cv.over(rgb("ink"), inner_shadow(cv, sd_sh, 6.0, 0.55) * cv.cov(sd))
    sd_k = sd_rrect(cv, W + 3.0, W + 3.0, 48 - W - 3.0, 48 - W - 3.0, 2.5)
    _bead_ring(cv, sd_k, 0.0, 0.8, stops=BRONZE, amp=0.4, streak_amt=0.0, edge_out=0.0, edge_in=0.0, alpha=0.8,
               base=0.2, vgrad=0.08)
    _bead_ring(cv, sd, 0.0, W, stops=GOLD, amp=0.8, seed=91, vgrad=0.08, edge_in=0.3)
    for cx, cy in ((W + 3.4, W + 3.4), (48 - W - 3.4, W + 3.4), (W + 3.4, 48 - W - 3.4), (48 - W - 3.4, 48 - W - 3.4)):
        gem_lozenge(cv, cx, cy, 1.9, 1.9, "gold_lt", setting=False, glint=0.5)
    return cv.image()


def dashed_outline():
    """90x90 @2x, slice 30 (15 logical), sides TILED: the §7.1 ONE PART AWAY outline, a 1.6 px white
    dash (9 on, 6 off; period 15 = one side tile) on a r 6 plate. Tint with `ichor` in code."""
    S, T = 45.0, 15.0          # texture side and slice/tile size (logical)
    cv = Cv(S, S)
    R, inset = 6.0, 0.8
    sd = sd_rrect(cv, inset, inset, S - inset, S - inset, R)
    line = band(sd, -0.8, 0.8)
    x, y = cv.x, cv.y

    def on(s, a, b):           # 1 inside the dash [a, b] of an arc-length coordinate s
        return np.clip(np.minimum(s - a, b - s) * cv.k + 0.5, 0, 1)

    # straight side tiles: one 9 px dash centred in each 15 px tile (gaps 3 + 3 = 6 across tiles)
    mid_x = (x >= T) & (x <= S - T)
    mid_y = (y >= T) & (y <= S - T)
    dash = np.where(mid_x, on(x - T, 3.0, 12.0), 0.0)
    dash = np.where(mid_y, on(y - T, 3.0, 12.0), dash)
    # corners: arc length from where the top side enters the corner to where the left side leaves it
    # (mirrored for the other corners). Pattern: 3 gap, 7.4 dash, 5 gap, 7.4 dash, 3 gap.
    xm, ym = np.minimum(x, S - x), np.minimum(y, S - y)
    c = inset + R
    straight = T - c
    arc = math.pi / 2 * R
    s = np.where((xm >= c) & (ym < c), T - xm,
                 np.where((ym >= c) & (xm < c), straight + arc + (ym - c),
                          straight + R * np.arctan2(c - xm, c - ym)))
    total = 2 * straight + arc
    dc = np.maximum(on(s, 3.0, 3.0 + 7.4), on(s, total - 3.0 - 7.4, total - 3.0))
    corner = (xm < T) & (ym < T)
    dash = np.where(corner, dc, dash)
    cv.over(np.array([1.0, 1.0, 1.0], np.float32), cv.cov(line) * dash)
    return cv.image()


# ───────────────────────────── minimap frame (phase-3 hook) ─────────────────────────────
def minimap_frame():
    """572x364 @2x, fixed 286x182 logical = the 280x176 MinimapFrame (r 10) plus 3 px on each side for
    the horn spurs. A 2.8 px gilt rim, a 0.9 px gold_dk inner line, 30 px forge-horn corners and
    the north gem (r 6, #FFE7A6) at the top centre. Content is inset 3 (MinimapContent)."""
    M = 3.0
    W, H = 280.0, 176.0
    cv = Cv(W + 2 * M, H + 2 * M)
    sd = sd_rrect(cv, M, M, M + W, M + H, 10.0)
    # a soft inner vignette over the map content (ink), so the sepia map sinks under the rim
    sd_c = sd_rrect(cv, M + 2.8, M + 2.8, M + W - 2.8, M + H - 2.8, 7.2)
    cv.over(rgb("ink"), inner_shadow(cv, sd_c, 9.0, 0.55, power=2.0))
    sdi = sd_rrect(cv, M + 3.6, M + 3.6, M + W - 3.6, M + H - 3.6, 6.4)
    cv.over(rgb("gold_dk"), cv.cov(band(sdi, 0.0, 0.9)), 0.9)
    _bead_ring(cv, sd, 0.0, 2.8, stops=GOLD, amp=1.1, groove=0.3, seed=95, vgrad=0.06, y0=M, y1=M + H)
    orn.horn_corners(cv, M, M, W, H, 30.0)
    # north gem on a small lozenge boss straddling the top rim
    orn.boss_lozenge(cv, M + W / 2, M + 1.4, 9.0, 7.0)
    gem_lozenge(cv, M + W / 2, M + 1.4, 6.0, 6.0, "gem_ivory", setting=False)
    return cv.image()


# ───────────────────────────── the shrine-niche boon card (§7.2) ─────────────────────────────
NICHE_W, NICHE_H, NICHE_ARCH, NICHE_CHAM = 300.0, 420.0, 112.0, 14.0


def niche_pts(inset: float = 0.0, n: int = 160):
    """The niche silhouette: straight sides, a chamfered foot (14) and an ogee arch 112 tall whose
    shoulders swell out, then draw in to a small pointed cusp at the apex."""
    W, H, A, C = NICHE_W, NICHE_H, NICHE_ARCH, NICHE_CHAM
    i = inset
    pts = [(i, H - C - i * 0.414), (i, A)]
    for k in range(1, n):
        t = k / n
        s = abs(2 * t - 1)            # 1 at the springers, 0 at the apex
        # ogee: a round shoulder (circle-ish) that turns concave into the cusp near the top
        shoulder = math.sqrt(max(0.0, 1 - s ** 2.1))
        cusp = (1 - s) ** 3.2 * 0.10
        y = A - (A - i) * min(1.0, 0.94 * shoulder + cusp + 0.06 * (1 - s) ** 0.5)
        x = i + (W - 2 * i) * t
        pts.append((x, y))
    pts += [(W - i, A), (W - i, H - C - i * 0.414), (W - C - i * 0.414, H - i), (C + i * 0.414, H - i)]
    return pts


def _niche_sd(cv, inset=0.0):
    return sd_poly(cv, niche_pts(inset), exact=False)


def niche_frame(rarity: str):
    """600x840 @2x, stretched to a fixed 300x420: rim (Common: bronze 3.4 px, else gilt 4.2 px), a
    bronze keyline at inset 11.2-12.4 and forge-horn foot corners (60). No springer gems (gem nodes).
    Epic and Godforged add engraved leaf flourishes at the springers; Godforged adds a fine inner
    gilt line and radiating ticks along the arch."""
    cv = Cv(NICHE_W, NICHE_H)
    sd = _niche_sd(cv)
    common = rarity == "common"
    stops = BRONZE if common else GOLD
    fw = 3.4 if common else 4.2
    # inner shadow cast by the rim onto the body
    cv.over(rgb("ink"), inner_shadow(cv, sd + fw - 1.2 * 0 + 0.0, 9.0, 0.55, power=1.8) * cv.cov(sd + fw * 0.5))
    # the bronze keyline (11.2 - 12.4)
    _bead_ring(cv, sd, 11.2, 12.4, stops=BRONZE, amp=0.5, streak_amt=0.0, edge_out=0.0, edge_in=0.0, alpha=0.9,
               base=0.22, vgrad=0.1)
    if rarity == "godforged":
        cv.over(rgb("gold_lt"), cv.cov(band(sd, 14.2, 14.9)), 0.5)
        # radiating ticks just inside the arch
        ang = np.arctan2(cv.y - 150.0, cv.x - 150.0)
        ph = ((ang / (2 * np.pi)) * 120.0) % 1.0
        ticks = np.clip((0.12 - np.abs(ph - 0.5)) * (2 * np.pi * 150.0 / 120.0) * cv.k + 0.5, 0, 1)
        ticks = ticks * (cv.y < NICHE_ARCH - 6)
        cv.over(rgb("gold_lt"), cv.cov(band(sd, 16.0, 18.6)) * ticks, 0.5)
    # the rim
    _bead_ring(cv, sd, 0.0, fw, stops=stops, amp=fw * 0.5, groove=0.35, seed=101, vgrad=0.08)
    # foot horns (no outward spur: the knee lozenge fills the chamfered corner)
    orn.forgehorn_into(cv, 0.0, NICHE_H, 60.0, flip_x=False, flip_y=True, stops=stops, spur=False, margin=0.0,
                       socket=False)
    orn.forgehorn_into(cv, NICHE_W, NICHE_H, 60.0, flip_x=True, flip_y=True, stops=stops, spur=False, margin=0.0,
                       socket=False)
    if rarity in ("epic", "godforged"):
        for sx in (0.0, NICHE_W):
            orn.springer_flourish(cv, sx, NICHE_ARCH, flip=(sx > 0), stops=stops, big=(rarity == "godforged"))
    return cv.image()


def niche_body():
    """600x840 @2x greyscale lacquer + lattice in the niche shape, tinted by the god colour through
    ImageNode.color (multiply): bright enough under the arch that the tint reads, near black at the foot."""
    cv = Cv(NICHE_W, NICHE_H)
    sd = _niche_sd(cv, inset=1.0)
    col = lacquer_col(cv, "#424242", "#0C0C0C", y0=0.0, y1=NICHE_H, sdf=sd, edge_dark=0.5, edge_w=70, streak=5.0,
                      grain=2.0, sheen=0.0, seed=111)
    # a softer mid-card fall-off: most of the value sits under the arch
    ty = np.clip(cv.y / NICHE_H, 0, 1)
    col = col * (0.55 + 0.45 * (1 - smoothstep(0.1, 0.95, ty)))[..., None]
    lat = lattice_lines(cv, 22.0, 0.55) * 0.025
    col = np.clip(col + lat[..., None], 0, 1)
    g = col.mean(axis=2, keepdims=True)
    cv.over(np.repeat(g, 3, axis=2), cv.cov(sd))
    return cv.image()


def niche_hairline():
    """600x840 @2x white hairline mask at inset 6.2-7.8, tinted by the god colour (Duo: two nodes,
    each clipped to its half). A faint enamel shading keeps it glassy after tinting."""
    cv = Cv(NICHE_W, NICHE_H)
    sd = _niche_sd(cv)
    h = h_bead(sd, 6.2, 7.8)
    v = 0.78 + 0.22 * h
    ty = np.clip(cv.y / NICHE_H, 0, 1)
    v = v * (1.0 - 0.12 * ty)
    cv.over(np.repeat(v[..., None], 3, axis=2), cv.cov(band(sd, 6.2, 7.8)))
    return cv.image()


def niche_glow():
    """600x840 @2x white radial light pooling under the arch from the apex medallion (150, 56), clipped
    to the niche; tint with the god colour at ~0.4 in code (Duo: a second node on the right half)."""
    cv = Cv(NICHE_W, NICHE_H)
    sd = _niche_sd(cv, inset=4.0)
    r = np.hypot((cv.x - 150.0) / 190.0, (cv.y - 70.0) / 230.0)
    a = np.clip(1 - r, 0, 1) ** 1.5
    a = a * np.clip(-sd / 10.0, 0, 1)
    cv.over(np.array([1.0, 1.0, 1.0], np.float32), a)
    return cv.image()
