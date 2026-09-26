"""Ornaments: the forge-horn corner, the sun-crest, the ember-knot divider, finials, the boss-bar
horn, the end-screen sunburst, chrome gems and small bosses (UI_STYLE §8.2, §8.3).

All shapes are original GODFORGE designs. Each ornament is modelled as SDF primitives, turned into
a height field (a rounded dome per stroke, engraved grooves subtracted), lit as polished metal from
the top-left and given a gold_sh edge line. Ornaments that are never flipped bake a soft contact
shadow; per-corner variants are lit and shadowed for their own corner.
"""
from __future__ import annotations

import math

import numpy as np

from .core import (GOLD, IRON, LIGHT, Cv, band, bezier, drop_shadow_px, edge_line, flame_leaf, gem_lozenge,
                   h_bead, h_dome, rgb, sd_circle, sd_leaf, sd_poly, sd_polyline, sd_rrect,
                   shade, spiral_pts, u_union)


def _shade_ornament(cv, sd, bevel, stops=GOLD, grooves=None, groove_depth=0.45, light=LIGHT, vgrad=0.07, edge=0.55,
                    spec=0.55, base=0.16, gain=0.72, hammer_amt=0.03, seed=0, vflip=False):
    """Light a union SDF as cast-and-chased metal. `grooves` is an SDF of engraved lines (their
    centre lines, positive distance) that are cut into the height field."""
    h = h_dome(sd, bevel)
    if grooves is not None:
        g = np.exp(-(np.maximum(grooves, 0) / max(bevel * 0.28, 0.12)) ** 2)
        h = h - groove_depth * g * (h > 0.2)
    rng = np.random.default_rng(seed)
    from scipy import ndimage
    ham = ndimage.gaussian_filter(rng.standard_normal(h.shape).astype(np.float32), 0.6 * cv.k)
    ham /= (np.abs(ham).max() + 1e-6)
    col = shade(cv, h, bevel * 0.9, stops=stops, light=light, vgrad=(-vgrad if vflip else vgrad), spec=spec,
                base=base, gain=gain, hammer=ham, hammer_amt=hammer_amt)
    col = edge_line(col, sd, edge)
    return col


def _paste(dst: Cv, src: Cv, ox: float, oy: float, flip_x=False, flip_y=False, shadow=None):
    """Composite a local canvas into dst at logical offset (ox, oy), optionally flipped; `shadow` =
    (dx, dy, blur, alpha) bakes a contact shadow of the pasted coverage into dst first."""
    px = src.px
    if flip_x:
        px = px[:, ::-1]
    if flip_y:
        px = px[::-1]
    x0, y0 = int(round(ox * dst.k)), int(round(oy * dst.k))
    h, w = px.shape[:2]
    X0, Y0 = max(0, x0), max(0, y0)
    X1, Y1 = min(dst.W, x0 + w), min(dst.H, y0 + h)
    if X1 <= X0 or Y1 <= Y0:
        return
    sub = px[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]
    if shadow is not None:
        full = np.zeros((dst.H, dst.W), np.float32)
        full[Y0:Y1, X0:X1] = sub[..., 3]
        dst.over_px(drop_shadow_px(dst, full, *shadow))
    region = dst.px[Y0:Y1, X0:X1]
    dst.px[Y0:Y1, X0:X1] = sub + region * (1.0 - sub[..., 3:])


# ───────────────────────────── the forge-horn corner ─────────────────────────────
def _horn_parts(cv, s, m_units, spur=True, detail=2):
    """Build the forge-horn in a local canvas. Units: the box is 120 units = s logical; the panel
    corner sits at (m_units, m_units). Returns (union sdf, groove sdf, socket centre, socket r)."""
    u = s / 120.0
    o = m_units

    def P(x, y):
        return ((x + o) * u, (y + o) * u)

    def R(r):
        return max(r * u, 0.42)

    parts = []
    grooves = []
    for horiz in (True, False):
        def Q(x, y, horiz=horiz):
            return P(x, y) if horiz else P(y, x)
        # the arm: a tapering bar, a pinched neck, and a lozenge spear head
        arm = [Q(0, -2.2), Q(53, -1.5), Q(58.0, 0.7), Q(58.0, 4.5), Q(53, 6.7), Q(0, 7.4)]
        parts.append(sd_poly(cv, arm, exact=True))
        parts.append(sd_poly(cv, [Q(56.5, 2.6), Q(65.5, -2.6), Q(78.0, 2.6), Q(65.5, 7.8)], exact=True))
        grooves.append(sd_polyline(cv, [Q(22, 2.6), Q(51, 2.6)], 0.0))
        grooves.append(sd_polyline(cv, [Q(60.5, 2.6), Q(74, 2.6)], 0.0))
        if detail >= 1:
            for t in (35.0, 42.0):      # collar bands
                a, b = Q(t, -4.4), Q(t + 3.4, 9.6)
                parts.append(sd_rrect(cv, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]),
                                      R(0.9)))
        # the volute: a C-scroll leaving the knee and curling back under the arm
        tend = bezier(Q(22, 8), Q(27, 18.5), Q(38, 21.5), Q(47.5, 15.5), 40)
        parts.append(sd_polyline(cv, tend, R(2.9), R(2.0)))
        if detail >= 2:
            sp = spiral_pts(45.6, 20.2, 5.4, 0.9, 0.95, -math.pi / 2 + 0.25, 70, direction=1)
            parts.append(sd_polyline(cv, [Q(*p) for p in sp], R(2.0), R(1.1)))
            tail = bezier(Q(47.5, 15.5), Q(55, 11.0), Q(62, 13.0), Q(67, 18.5), 30)
            parts.append(sd_polyline(cv, tail, R(1.6), R(0.55)))
            parts.append(sd_circle(cv, *Q(67.3, 19.6), R(1.45)))
        else:
            parts.append(sd_circle(cv, *Q(46.0, 18.0), R(3.4)))
    # the palmette: three flame leaves fanning from the knee into the panel
    parts.append(flame_leaf(cv, bezier(P(18, 18), P(28, 28), P(40, 40), P(51, 51), 30), 6.6 * u, bulge=0.32))
    grooves.append(sd_polyline(cv, [P(23, 23), P(43, 43)], 0.0))
    if detail >= 1:
        parts.append(flame_leaf(cv, bezier(P(19, 17), P(30, 21), P(40, 24), P(48, 30), 30), 4.0 * u, bulge=0.3))
        parts.append(flame_leaf(cv, bezier(P(17, 19), P(21, 30), P(24, 40), P(30, 48), 30), 4.0 * u, bulge=0.3))
    # the knee boss with a lozenge socket
    if spur:
        bc, br = (11.0, 11.0), 16.5
    else:
        bc, br = (11.5, 11.5), 11.5
    boss = [P(bc[0], bc[1] - br), P(bc[0] + br, bc[1]), P(bc[0], bc[1] + br), P(bc[0] - br, bc[1])]
    parts.append(sd_poly(cv, boss, exact=True))
    if spur:   # the outward spur: a flame thorn off the corner
        parts.append(flame_leaf(cv, [P(3.0, 3.0), P(-4.0, -4.0), P(-11.0, -11.0)], 3.8 * u, bulge=0.25))
    sd = u_union(*parts)
    gsd = u_union(*grooves) if grooves else None
    sock_c = P(*bc)
    sock_r = (br - 4.4 if spur else br - 3.4) * u
    return sd, gsd, sock_c, sock_r


def forgehorn_local(s: float, flip_x=False, flip_y=False, stops=GOLD, spur=True, margin=0.1, seed=7, socket=True):
    """Render a forge-horn corner of size s (logical) into its own canvas, lit so that it reads
    lit-from-the-top-left *after* the flips are applied. Returns the local canvas (unflipped).
    socket=False gives a solid boss with an engraved lozenge instead of the gem socket."""
    cv = Cv(s, s)
    detail = 2 if s >= 44 else (1 if s >= 34 else 0)
    sd, gsd, (scx, scy), sr = _horn_parts(cv, s, margin * 120.0, spur=spur, detail=detail)
    if not socket:
        eng = np.abs(sd_poly(cv, [(scx, scy - sr * 0.8), (scx + sr * 0.8, scy), (scx, scy + sr * 0.8),
                                  (scx - sr * 0.8, scy)], exact=True))
        gsd = eng if gsd is None else np.minimum(gsd, eng)
    light = (LIGHT[0] * (-1 if flip_x else 1), LIGHT[1] * (-1 if flip_y else 1), LIGHT[2])
    bevel = max(0.55, s * 0.022)
    col = _shade_ornament(cv, sd, bevel, stops=stops, grooves=gsd, light=light, vflip=flip_y, seed=seed,
                          edge=min(0.6, 0.35 + s * 0.004))
    cv.over(col, cv.cov(sd))
    if socket:
        # the socket: a dark recess with a bronze lip, where the gem node (19 % of s) sits
        sock = sd_poly(cv, [(scx, scy - sr), (scx + sr, scy), (scx, scy + sr), (scx - sr, scy)], exact=True)
        rec = np.clip(-sock / (sr * 0.45), 0, 1)
        cv.over(rgb("#0A0604"), cv.cov(sock))
        cv.over(rgb("#4A3016"), cv.cov(sock) * (1 - rec) * 0.8)
    cv.socket = (scx, scy, sr)   # the gem is drawn after any flip, so its facets stay lit from the top-left
    return cv


def forgehorn_into(cv: Cv, cx: float, cy: float, s: float, flip_x=False, flip_y=False, stops=GOLD, spur=True,
                   margin=0.1, gem=None, shadow=True, socket=True):
    """Draw a forge-horn with its panel corner at (cx, cy) of an existing canvas."""
    loc = forgehorn_local(s, flip_x, flip_y, stops, spur, margin, socket=socket)
    m = margin * s
    ox = cx - (s - m if flip_x else m)
    oy = cy - (s - m if flip_y else m)
    _paste(cv, loc, ox, oy, flip_x, flip_y, shadow=(0.5, 0.9, 0.9, 0.7) if shadow else None)
    if gem and socket:
        _horn_gem(cv, loc, ox, oy, s, flip_x, flip_y, gem)


def horn_corners(cv: Cv, x, y, w, h, s, stops=GOLD, gem="#FFB82E"):
    for fx, fy in ((False, False), (True, False), (False, True), (True, True)):
        forgehorn_into(cv, x + (w if fx else 0), y + (h if fy else 0), s, fx, fy, stops=stops, gem=gem)


def forgehorn_texture(s: float, corner: str = "tl", stops=GOLD, gem=None):
    """A standalone corner texture of size s: the panel corner sits 10 % in from the outer corner.
    corner: tl | tr | bl | br (lit and shadowed for that corner)."""
    fx, fy = corner[1] == "r", corner[0] == "b"
    out = Cv(s, s)
    loc = forgehorn_local(s, fx, fy, stops, True, 0.1)
    _paste(out, loc, 0.0, 0.0, fx, fy, shadow=(0.45, 0.8, 0.8, 0.6))
    if gem:
        _horn_gem(out, loc, 0.0, 0.0, s, fx, fy, gem)
    return out.image()


def _horn_gem(dst: Cv, loc: Cv, ox, oy, s, flip_x, flip_y, gem):
    scx, scy, sr = loc.socket
    gx = ox + (s - scx if flip_x else scx)
    gy = oy + (s - scy if flip_y else scy)
    gem_lozenge(dst, gx, gy, sr * 0.97, sr * 0.97, gem, setting=False, glint=0.95)


# ───────────────────────────── springer flourish (niche cards, Epic+) ─────────────────────────────
def springer_flourish(cv: Cv, x, y, flip=False, stops=GOLD, big=False):
    """Chased flame-leaves sprouting inward from the rim at the arch springer (x, y), clear of the
    r 8 springer gem node: a collar on the rim, two curved leaves up and down, and (Godforged) a
    third leaf straight in with a bead."""
    s = 46.0 if big else 38.0
    loc = Cv(s, s)
    cy = s / 2
    L = s - 6.0
    parts = [flame_leaf(loc, bezier((5.0, cy - 1.0), (13.0, cy - 3.0), (L * 0.7, cy - 6.0), (L, cy - 15.0 * s / 38), 30),
                        3.2, bulge=0.3),
             flame_leaf(loc, bezier((5.0, cy + 1.0), (13.0, cy + 3.0), (L * 0.7, cy + 6.0), (L, cy + 15.0 * s / 38), 30),
                        3.2, bulge=0.3),
             sd_rrect(loc, 0.0, cy - 5.5, 4.4, cy + 5.5, 1.0)]
    grooves = [sd_polyline(loc, bezier((9.0, cy - 2.0), (14.0, cy - 3.5), (L * 0.62, cy - 6.0), (L * 0.85, cy - 11.0),
                                       20), 0.0),
               sd_polyline(loc, bezier((9.0, cy + 2.0), (14.0, cy + 3.5), (L * 0.62, cy + 6.0), (L * 0.85, cy + 11.0),
                                       20), 0.0)]
    if big:
        parts.append(flame_leaf(loc, [(6.0, cy), (20.0, cy), (L + 2.0, cy)], 2.6, bulge=0.3))
        parts.append(sd_circle(loc, 11.0, cy, 2.2))
    sd = u_union(*parts)
    light = (LIGHT[0] * (-1 if flip else 1), LIGHT[1], LIGHT[2])
    col = _shade_ornament(loc, sd, 0.9, stops=stops, grooves=u_union(*grooves), groove_depth=0.4, light=light, seed=13)
    loc.over(col, loc.cov(sd))
    _paste(cv, loc, x - (s - 1.5 if flip else 1.5), y - cy, flip_x=flip, flip_y=False, shadow=(0.4, 0.7, 0.8, 0.6))


def boss_lozenge(cv: Cv, cx, cy, rx, ry, stops=GOLD):
    sd = sd_poly(cv, [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)], exact=True)
    col = _shade_ornament(cv, sd, 1.4, stops=stops, seed=3)
    cv.over_px(drop_shadow_px(cv, cv.cov(sd), 0.4, 0.8, 0.8, 0.6))
    cv.over(col, cv.cov(sd))


def star4(cv: Cv, cx, cy, r_long, r_thin, color, alpha=1.0, diag=0.45):
    """A four-point star (sparks): long cardinal rays and short diagonals."""
    pts = []
    for k in range(8):
        a = -math.pi / 2 + k * math.pi / 4
        r = r_long if k % 2 == 0 else r_long * diag
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        a2 = a + math.pi / 8
        pts.append((cx + r_thin * math.cos(a2), cy + r_thin * math.sin(a2)))
    sd = sd_poly(cv, pts, exact=True)
    cv.over(rgb(color), cv.cov(sd), alpha)


# ───────────────────────────── the sun-crest ─────────────────────────────
def suncrest(h_log: float = 80.0, gem="#FFB82E"):
    """The sun-crest, aspect 2.6:1 (416x160 @2x at 80 tall): 11 concave-sided rays (long and short
    alternating) rising from a half-sun plate, curved flame-wings sweeping out and up on both sides,
    a lozenge boss holding an amber gem, and a flame pendant. The boss centre sits at 62 % of the
    height: place the crest so that point lies on the panel's top edge."""
    H = h_log
    W = H * 2.6
    cv = Cv(W, H)
    cx, cy = W / 2, H * 0.62
    parts, grooves = [], []
    r0 = H * 0.27
    for i in range(11):
        a = math.pi + (i + 0.5) / 11 * math.pi
        long = i % 2 == 0
        L = H * (0.605 if long else 0.46)
        w0 = H * (0.050 if long else 0.036)
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa, ca

        def at(r, off, ca=ca, sa=sa, px=px, py=py):
            return (cx + ca * r + px * off, cy + sa * r + py * off)
        rm = r0 + (L - r0) * 0.55
        parts.append(sd_poly(cv, [at(r0, -w0), at(rm, -w0 * 0.42), at(L, 0.0), at(rm, w0 * 0.42), at(r0, w0)],
                             exact=True))
        if long:
            grooves.append(sd_polyline(cv, [at(r0 + H * 0.03, 0.0), at(L - H * 0.08, 0.0)], 0.0))
    # the half-sun plate with an engraved rim line
    dist = np.hypot(cv.x - cx, cv.y - cy)
    parts.append(np.maximum(dist - H * 0.30, cv.y - cy - H * 0.05))
    grooves.append(np.abs(dist - H * 0.255) + np.maximum(cv.y - cy + H * 0.03, 0) * 10)
    # flame-wings: three curved leaves per side, the main one curling up at its tip
    for sgn in (-1, 1):
        def Wp(x, y, sgn=sgn):
            return (cx + sgn * x * H, cy + y * H)
        parts.append(flame_leaf(cv, bezier(Wp(0.20, 0.02), Wp(0.55, 0.03), Wp(0.88, -0.02), Wp(1.12, -0.24), 40),
                                H * 0.070, bulge=0.28))
        grooves.append(sd_polyline(cv, bezier(Wp(0.30, 0.02), Wp(0.55, 0.025), Wp(0.80, 0.0), Wp(0.95, -0.10), 30),
                                   0.0))
        parts.append(flame_leaf(cv, bezier(Wp(0.22, -0.08), Wp(0.44, -0.16), Wp(0.66, -0.28), Wp(0.80, -0.47), 40),
                                H * 0.052, bulge=0.3))
        parts.append(flame_leaf(cv, bezier(Wp(0.22, 0.09), Wp(0.42, 0.16), Wp(0.62, 0.17), Wp(0.78, 0.10), 40),
                                H * 0.045, bulge=0.3))
    # the boss and the pendant
    r = H * 0.29
    parts.append(sd_poly(cv, [(cx, cy - r), (cx + r * 0.86, cy), (cx, cy + r), (cx - r * 0.86, cy)], exact=True))
    parts.append(flame_leaf(cv, [(cx, cy + r * 0.80), (cx, cy + r * 1.05), (cx, cy + r * 1.30)], H * 0.05, bulge=0.3))
    sd = u_union(*parts)
    gr = u_union(*grooves)
    col = _shade_ornament(cv, sd, max(0.8, H * 0.019), grooves=gr, groove_depth=0.38, seed=19, edge=0.55)
    cv.over_px(drop_shadow_px(cv, cv.cov(sd), 0.0, H * 0.018, H * 0.02, 0.75))
    cv.over(col, cv.cov(sd))
    # the socket and the gem
    sr = r * 0.70
    sock = sd_poly(cv, [(cx, cy - sr), (cx + sr * 0.86, cy), (cx, cy + sr), (cx - sr * 0.86, cy)], exact=True)
    rec = np.clip(-sock / (sr * 0.3), 0, 1)
    cv.over(rgb("#0A0604"), cv.cov(sock))
    cv.over(rgb("#4A3016"), cv.cov(sock) * (1 - rec) * 0.8)
    gem_lozenge(cv, cx, cy, sr * 0.80, sr * 0.93, gem, setting=False, glint=0.95)
    return cv.image()


# ───────────────────────────── the ember-knot divider ─────────────────────────────
def emberknot_rule():
    """512x28 @2x (256x14 logical), 3-slice: the left 480 px stretch, the right 32 px is the point.
    A hairline tapering from 1.5 px at the knot end, then a slender spear terminal. Flip for the
    left side of a divider."""
    cv = Cv(256.0, 14.0)
    cy = 7.0
    parts = [sd_polyline(cv, [(0.0, cy), (240.5, cy)], 0.76, 0.46)]
    tip = [(239.0, cy), (244.5, cy - 1.35), (255.4, cy), (244.5, cy + 1.35)]
    parts.append(sd_poly(cv, tip, exact=True))
    sd = u_union(*parts)
    h = h_dome(sd, 0.8)
    col = shade(cv, h, 0.7, stops=GOLD, vgrad=0.0, base=0.2, gain=0.7)
    col = edge_line(col, sd, 0.3, amount=0.5)
    cv.over(col, cv.cov(sd))
    return cv.image()


def emberknot_knot():
    """112x28 @2x, fixed 56x14: twin curls around a centre lozenge setting (the gem is a node,
    ~9x9 logical, centred at (28, 7)). The rule meets it at 1.5 px on both ends."""
    cv = Cv(56.0, 14.0)
    cx, cy = 28.0, 7.0
    parts = [sd_polyline(cv, [(0.0, cy), (56.0, cy)], 0.76)]
    for sgn in (-1, 1):
        arc = bezier((cx + sgn * 6.0, cy - 0.4), (cx + sgn * 10.5, cy - 5.6), (cx + sgn * 17.0, cy - 5.8),
                     (cx + sgn * 19.8, cy - 2.4), 30)
        parts.append(sd_polyline(cv, arc, 0.72, 0.62))
        sp = spiral_pts(cx + sgn * 18.1, cy - 1.5, 1.9, 0.3, 0.85, 0.35 if sgn > 0 else math.pi - 0.35, 36,
                        direction=sgn)
        parts.append(sd_polyline(cv, sp, 0.62, 0.36))
        low = bezier((cx + sgn * 6.0, cy + 0.4), (cx + sgn * 9.5, cy + 4.6), (cx + sgn * 13.0, cy + 4.6),
                     (cx + sgn * 14.8, cy + 2.6), 24)
        parts.append(sd_polyline(cv, low, 0.6, 0.4))
        parts.append(sd_circle(cv, cx + sgn * 24.5, cy, 1.05))   # a bead on the line
    setting = [(cx, cy - 6.4), (cx + 6.4, cy), (cx, cy + 6.4), (cx - 6.4, cy)]
    parts.append(sd_poly(cv, setting, exact=True))
    sd = u_union(*parts)
    col = _shade_ornament(cv, sd, 0.75, seed=23, edge=0.3, vgrad=0.0, hammer_amt=0.0)
    cv.over(col, cv.cov(sd))
    sock = sd_poly(cv, [(cx, cy - 4.6), (cx + 4.6, cy), (cx, cy + 4.6), (cx - 4.6, cy)], exact=True)
    cv.over(rgb("#070403"), cv.cov(sock))
    return cv.image()


# ───────────────────────────── finials ─────────────────────────────
def finial_leaf():
    """44x44 @2x, fixed 22: the HP bar's right cap. A collar with two small back-leaves and a
    chased leaf blade pointing right; the bar's end tucks under the collar (x 0-5)."""
    cv = Cv(22.0, 22.0)
    cy = 11.0
    parts = [sd_rrect(cv, 2.0, 2.4, 5.6, 19.6, 0.9),
             sd_leaf(cv, (4.5, cy), (21.6, cy), 5.4),
             sd_leaf(cv, (4.0, 3.4), (0.6, 0.6), 1.3),
             sd_leaf(cv, (4.0, 18.6), (0.6, 21.4), 1.3)]
    sd = u_union(*parts)
    gr = sd_polyline(cv, [(7.5, cy), (18.5, cy)], 0.0)
    col = _shade_ornament(cv, sd, 1.1, grooves=gr, groove_depth=0.5, seed=29, edge=0.45)
    cv.over_px(drop_shadow_px(cv, cv.cov(sd), 0.3, 0.7, 0.7, 0.6))
    cv.over(col, cv.cov(sd))
    return cv.image()


def finial_lozenge():
    """20x20 @2x, fixed 10: the gilt rail's end, a faceted lozenge."""
    cv = Cv(10.0, 10.0)
    sd = sd_poly(cv, [(5.0, 1.0), (9.4, 5.0), (5.0, 9.0), (0.6, 5.0)], exact=True)
    col = _shade_ornament(cv, sd, 1.6, seed=31, edge=0.35, hammer_amt=0.0)
    cv.over(col, cv.cov(sd))
    return cv.image()


def boss_horn():
    """68x60 @2x, fixed 34x30: the boss bar's left end (flip for the right). An iron horn-crest: a
    spike pointing out and two horns sweeping back and curling, set in a gilt collar that clasps
    the bar end (x 26-34, y 9-21)."""
    cv = Cv(34.0, 30.0)
    cy = 15.0
    iron = [sd_poly(cv, [(1.0, cy), (12.0, cy - 5.2), (27.0, cy - 4.0), (27.0, cy + 4.0), (12.0, cy + 5.2)], exact=True)]
    for sgn in (-1, 1):
        horn = bezier((24.0, cy + sgn * 3.0), (18.0, cy + sgn * 13.5), (9.0, cy + sgn * 14.0), (5.5, cy + sgn * 9.0), 40)
        iron.append(sd_polyline(cv, horn, 2.6, 0.7))
    sd_i = u_union(*iron)
    gold = [sd_rrect(cv, 24.5, cy - 7.4, 29.0, cy + 7.4, 1.0), sd_rrect(cv, 29.0, cy - 5.6, 34.0, cy + 5.6, 0.8)]
    sd_g = u_union(*gold)
    both = np.minimum(sd_i, sd_g)
    cv.over_px(drop_shadow_px(cv, cv.cov(both), 0.3, 0.8, 0.8, 0.65))
    gr = sd_polyline(cv, [(4.5, cy), (22.0, cy)], 0.0)
    ci = _shade_ornament(cv, sd_i, 1.3, stops=IRON, grooves=gr, groove_depth=0.4, seed=37, edge=0.5, spec=0.7)
    cv.over(ci, cv.cov(sd_i))
    # a thin gilt edge line on the iron (keeps it in the gilt family)
    cv.over(rgb("gold_md"), cv.cov(band(sd_i, 0.0, 0.45)), 0.75)
    cg = _shade_ornament(cv, sd_g, 1.2, seed=41, edge=0.4)
    cv.over(cg, cv.cov(sd_g))
    return cv.image()


# ───────────────────────────── sunburst ─────────────────────────────
def sunburst16():
    """520x520 @2x, fixed 260: the end-screen crest rays. 16 blades (long to r 122, short to 96)
    with chased ridges, rising from under the Ø116 medallion; the gold ramp at 0.9."""
    cv = Cv(260.0, 260.0)
    c = 130.0
    parts = []
    for i in range(16):
        a = -math.pi / 2 + i * 2 * math.pi / 16
        long = i % 2 == 0
        L = 122.0 if long else 96.0
        wd = 0.085 if long else 0.07
        r0 = 50.0
        p1 = (c + math.cos(a - wd) * r0, c + math.sin(a - wd) * r0)
        p2 = (c + math.cos(a) * L, c + math.sin(a) * L)
        p3 = (c + math.cos(a + wd) * r0, c + math.sin(a + wd) * r0)
        parts.append(sd_poly(cv, [p1, p2, p3], exact=True))
    ring = np.abs(np.hypot(cv.x - c, cv.y - c) - 62.5) - 2.2
    parts.append(ring)
    sd = u_union(*parts)
    # ridge profile: the height rises linearly to each blade's medial axis
    h = h_dome(sd, 3.2, profile="ridge")
    col = shade(cv, h, 2.4, stops=GOLD, vgrad=0.08, spec=0.6, base=0.14)
    col = edge_line(col, sd, 0.6)
    cv.over(col, cv.cov(sd), 0.9)
    return cv.image()


# ───────────────────────────── chrome gems ─────────────────────────────
def gem_texture(color: str, size: float = 16.0, setting: bool = True):
    """A chrome lozenge gem (horn bosses, the sun-crest, notches, the north gem): size logical."""
    cv = Cv(size, size)
    c = size / 2
    gem_lozenge(cv, c, c, c - 0.4, c - 0.4, color, setting=setting, setting_w=size * 0.1)
    return cv.image()


def gem_socket(shape: str = "lozenge", size: float = 16.0):
    """An empty gilt setting with a dark recess, where a gem node sits (rarity gems, notches)."""
    cv = Cv(size, size)
    c = size / 2
    if shape == "round":
        sd = sd_circle(cv, c, c, c - 0.5)
    else:
        sd = sd_poly(cv, [(c, 0.5), (size - 0.5, c), (c, size - 0.5), (0.5, c)], exact=True)
    cv.over(rgb("#060403"), cv.cov(sd))
    rw = size * 0.13
    cv.over(rgb("#000000"), np.clip(1 - (-sd - rw) / (size * 0.18), 0, 1) * cv.cov(sd + rw) * 0.6)
    h = h_bead(sd, 0.0, rw)
    col = shade(cv, h, rw * 0.8, stops=GOLD, vgrad=0.05)
    col = edge_line(col, sd, 0.35)
    cv.over(col, cv.cov(band(sd, 0.0, rw)))
    return cv.image()


def hearth_rail():
    """780x12 @2x, stretch to 390x6 (x 146-536, y 952-958): the Hearth's gilt rail, 3.6 px at the
    medallion tapering to 2.4 px, in the soft ramp with a bead ridge."""
    cv = Cv(390.0, 6.0)
    sd = sd_polyline(cv, [(0.0, 3.0), (390.0, 3.0)], 1.8, 1.2)
    h = h_dome(sd, 1.2)
    col = shade(cv, h, 1.0, stops=GOLD, vgrad=0.0, base=0.2)
    col = edge_line(col, sd, 0.4, amount=0.7)
    cv.over(col, cv.cov(sd))
    return cv.image()
