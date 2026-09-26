"""GILDED MYTHIC ornaments v2: forge-horn corners, title crest, ornate panels, inner shadow, lattice."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from gmkit import (BRONZE_RAMP, GOLD_RAMP, SS, TOK, bezier, blank, clip_to, down, gem, lacquer, metal_from_mask,
                   rgba, ring_mask, rrect_mask, spiral, taper_stroke, to_img)


def leaf(d, base, tip, width, fill=255, n=40):
    """Pointed leaf / flame tongue between base and tip (two mirrored beziers, filled)."""
    bx, by = base
    tx, ty = tip
    dx, dy = tx - bx, ty - by
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    c1 = (bx + dx * 0.35 + nx * width, by + dy * 0.35 + ny * width)
    c2 = (bx + dx * 0.75 + nx * width * 0.5, by + dy * 0.75 + ny * width * 0.5)
    c3 = (bx + dx * 0.35 - nx * width, by + dy * 0.35 - ny * width)
    c4 = (bx + dx * 0.75 - nx * width * 0.5, by + dy * 0.75 - ny * width * 0.5)
    a = bezier(base, c1, c2, tip, n)
    b = bezier(tip, c4, c3, base, n)
    d.polygon(a + b, fill=fill)


def corner_v2_mask(s: int, margin: float = 0.1):
    """'Forge-horn' corner v2 in an s x s px box. The panel corner sits at (margin*s, margin*s) so a
    spur can project outside the panel. Returns (supersampled mask, offset px of the panel corner)."""
    S = s * SS
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    u = S / 120.0
    o = margin * 120

    def P(x, y):
        return ((x + o) * u, (y + o) * u)

    for horiz in (True, False):
        pts = [(0, -1.5), (62, -1.5), (74, 2.5), (62, 6.5), (0, 6.5)]
        if not horiz:
            pts = [(y, x) for (x, y) in pts]
        d.polygon([P(*q) for q in pts], fill=255)
    for t in (40, 48):
        d.polygon([P(t, -3.5), P(t + 3, -3.5), P(t + 3, 8.5), P(t, 8.5)], fill=255)
        d.polygon([P(-3.5, t), P(8.5, t), P(8.5, t + 3), P(-3.5, t + 3)], fill=255)
    cx, cy, r = 10, 10, 15
    d.polygon([P(cx, cy - r), P(cx + r, cy), P(cx, cy + r), P(cx - r, cy)], fill=255)
    d.polygon([P(-2, 3), P(-13, -13), P(3, -2)], fill=255)
    for flip in (False, True):
        def Q(x, y, flip=flip):
            return P(y, x) if flip else P(x, y)
        pts = bezier((22, 6), (28, 16), (40, 18), (48, 13), 40)
        taper_stroke(d, [Q(*q) for q in pts], 2.6 * u, 1.6 * u)
        sp = spiral(46.5, 18.5, 5.6, 1.0, 0.9, -math.pi / 2 + 0.3, 60, direction=1)
        taper_stroke(d, [Q(*q) for q in sp], 1.6 * u, 0.9 * u)
        pts = bezier((48, 13), (56, 9), (62, 12), (66, 17), 30)
        taper_stroke(d, [Q(*q) for q in pts], 1.4 * u, 0.4 * u)
    leaf(d, P(18, 18), P(46, 46), 5.5 * u)
    leaf(d, P(18, 18), P(40, 26), 3.2 * u)
    leaf(d, P(18, 18), P(26, 40), 3.2 * u)
    taper_stroke(d, [P(20 + i * 0.5, 20 + i * 0.5) for i in range(40)], 0.7 * u, 0.2 * u, fill=0)
    return m, int(round(o * s / 120.0))


def inner_shadow(w, h, r, blur, opacity):
    small = down(rrect_mask(w, h, r), w, h)
    inv = Image.eval(small, lambda v: 255 - v)
    pad = int(blur * 2)
    big = Image.new("L", (w + pad * 2, h + pad * 2), 255)
    big.paste(inv, (pad, pad))
    big = big.filter(ImageFilter.GaussianBlur(blur)).crop((pad, pad, pad + w, pad + h))
    a = ImageChops.multiply(big, small).point(lambda v: int(v * opacity))
    out = Image.new("RGBA", (w, h), rgba(TOK["ink"]))
    out.putalpha(a)
    return out


def lattice(img: Image.Image, alpha: float = 0.04, step: int = 22) -> Image.Image:
    """Faint tooled lozenge lattice in the lacquer (reads as texture, not pattern)."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.abs(((xx + yy) % step) - step / 2) < 0.6
    b = np.abs(((xx - yy) % step) - step / 2) < 0.6
    lines = (a | b).astype(np.float32)
    arr = np.asarray(img, np.float32).copy()
    arr[..., :3] += lines[..., None] * 255 * alpha * np.array([1.0, 0.82, 0.55])
    return to_img(arr)


def crest_img(size: int, gem_color: str = "#FFB82E", wings: float = 1.0) -> Image.Image:
    """Title crest: a sun-fan of tapered rays over flame-wings, a lozenge boss with a gem."""
    w, h = int(size * 2.6 * wings), size
    S = SS
    m = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(m)
    cx, cy = w * S / 2, h * S * 0.62
    R = h * S * 0.58
    for i in range(11):
        a = math.pi + (i + 0.5) / 11 * math.pi
        L = R * (1.0 if i % 2 == 0 else 0.74)
        wd = 0.085 if i % 2 == 0 else 0.06
        d.polygon([(cx + math.cos(a - wd) * R * 0.3, cy + math.sin(a - wd) * R * 0.3), (cx + math.cos(a) * L, cy + math.sin(a) * L),
                   (cx + math.cos(a + wd) * R * 0.3, cy + math.sin(a + wd) * R * 0.3)], fill=255)
    for sgn in (-1, 1):
        for dy, ln, wd in ((0.0, 1.0, 1.0), (-0.16, 0.8, 0.8), (0.16, 0.62, 0.7)):
            base = (cx + sgn * h * S * 0.18, cy + dy * h * S)
            tip = (cx + sgn * w * S * 0.48 * ln, cy + dy * h * S * 1.6 - h * S * 0.05)
            leaf(d, base, tip, h * S * 0.075 * wd)
    r = h * S * 0.3
    d.polygon([(cx, cy - r), (cx + r * 0.85, cy), (cx, cy + r), (cx - r * 0.85, cy)], fill=255)
    d.polygon([(cx - r * 0.25, cy + r * 0.9), (cx + r * 0.25, cy + r * 0.9), (cx, cy + r * 1.45)], fill=255)
    img = metal_from_mask(m, w, h, bevel=1.4, rough=0.03)
    g = gem(int(h * 0.36), gem_color)
    img.alpha_composite(g, (w // 2 - g.width // 2, int(h * 0.62) - g.height // 2))
    return img


def ornate_panel(w: int, h: int, r: int = 8, frame: float = 3.0, alpha: float = 0.93, corner: int = 64,
                 gem_color: str | None = "#FFB82E", tint: str | None = None, tint_amt: float = 0.0,
                 top="#241A14", bot="#0E0A08", keyline: bool = True, seed: int = 1, crest: int = 0,
                 crest_gem: str = "#FFB82E", pattern: bool = True, frame_stops=GOLD_RAMP,
                 corner_stops=None, inner_shadow_px: int = 10):
    """Big gilded panel with v2 corners (spurs overhang). Returns (image, (ox, oy)) where the panel's
    own top-left sits at (ox, oy) inside the returned image."""
    cm, off = corner_v2_mask(corner)
    pad = off + 2
    top_pad = pad + (int(crest * 0.62) if crest else 0)
    W, H = w + pad * 2, h + pad + top_pad
    img = blank(W, H)
    body_mask = down(rrect_mask(w, h, r), w, h)
    body = lacquer(w, h, top=top, bot=bot, alpha=alpha, tint=tint, tint_amt=tint_amt, seed=seed)
    if pattern:
        body = lattice(body, alpha=0.03)
    img.alpha_composite(clip_to(body, body_mask), (pad, top_pad))
    if inner_shadow_px:
        img.alpha_composite(inner_shadow(w, h, r, inner_shadow_px, 0.6), (pad, top_pad))
    ring = ring_mask(w, h, r, frame)
    img.alpha_composite(metal_from_mask(ring, w, h, bevel=frame * 0.55, seed=seed, stops=frame_stops), (pad, top_pad))
    if keyline:
        k = ring_mask(w, h, max(0, r - 3), 1.0, inset=frame + 4)
        img.alpha_composite(metal_from_mask(k, w, h, bevel=0.5, stops=BRONZE_RAMP, rough=0.0), (pad, top_pad))
    cimg = metal_from_mask(cm, corner, corner, bevel=1.5, seed=seed + 7, stops=corner_stops or frame_stops)
    gs = max(8, int(corner * 0.19))
    g = gem(gs, gem_color) if gem_color else None
    gc = int(round(corner * (10 + 12) / 120.0))
    for fx, fy in ((False, False), (True, False), (False, True), (True, True)):
        c = cimg
        if fx:
            c = c.transpose(Image.FLIP_LEFT_RIGHT)
        if fy:
            c = c.transpose(Image.FLIP_TOP_BOTTOM)
        x = pad - off if not fx else pad + w + off - corner
        y = top_pad - off if not fy else top_pad + h + off - corner
        img.alpha_composite(c, (x, y))
        if g is not None:
            gx = x + (gc if not fx else corner - gc) - gs // 2
            gy = y + (gc if not fy else corner - gc) - gs // 2
            img.alpha_composite(g, (gx, gy))
    if crest:
        cr = crest_img(crest, crest_gem)
        img.alpha_composite(cr, (pad + w // 2 - cr.width // 2, top_pad - int(cr.height * 0.62)))
    return img, (pad, top_pad)
