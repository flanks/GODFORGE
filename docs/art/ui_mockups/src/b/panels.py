"""Premium panels (designer B): Forge, boon cards, end screen, help. Logical px."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from gf import *
import icons as I
from hud import framed_slot, slot_shape, M

RARITY = {'common': 'common', 'rare': 'rare', 'epic': 'epic', 'godforged': 'godforged'}
RNAME = {'common': 'COMMON', 'rare': 'RARE', 'epic': 'EPIC', 'godforged': 'GODFORGED'}


def tri(cv, x, y, s, up=True, color='up'):
    m = Image.new('L', (int(P(s)) + 2, int(P(s)) + 2), 0)
    n = P(s)
    pts = [(n / 2, 0), (n, n * 0.8), (0, n * 0.8)] if up else [(0, n * 0.2), (n, n * 0.2), (n / 2, n)]
    ImageDraw.Draw(m).polygon(pts, fill=255)
    fill_mask(cv, m, P(x), P(y), rgba(color))


def delta_chip(cv, x, y, pct, anchor='r', size=15, ink=False):
    """Gain is bright gold with an up-chevron; loss is ash with a down-chevron (value, not hue, carries it)."""
    up = pct > 0.5
    down = pct < -0.5
    txt = f'{abs(pct):.0f}%' if (up or down) else '±0%'
    f = cinzel(size, 800)
    w = text_w(txt, f) + (size * 0.9 if (up or down) else 0)
    x0 = x - w if anchor == 'r' else x
    col = 'up' if up else 'down' if down else 'parch_mute'
    if ink:
        col = '#3A2208'
    if up or down:
        tri(cv, x0, y - size * 0.72, size * 0.7, up=up, color=col)
        x0 += size * 0.9
    draw_text(cv, x0, y, txt, f, fill=col, shadow_a=0 if ink else 0.9)
    return w


def card(cv, x, y, w, h, rarity='common', selected=False, target=False, r=7, fill_a=0.95, dim=False):
    X, Y = P(x), P(y)
    m = rr_mask(P(w), P(h), P(r))
    shadow(cv, m, X, Y, blur=P(8 if selected else 5), off=(0, P(4 if selected else 2.5)), alpha=0.8)
    if selected:
        glow(cv, m, X, Y, '#FFC24A', blur=P(10), alpha=0.75, spread=P(1.5))
    top = '#2E2119' if not dim else '#1C1510'
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, rgba(top, fill_a)), (1, rgba('#120C09', fill_a))]))
    rc = rgba(rarity)
    # rarity wash from the top edge
    fill_mask(cv, shrink(m, P(1)), X, Y, grad_img(m.width, m.height, [(0, rgba(rc, 0.20)), (0.45, rgba(rc, 0.0)), (1, rgba(rc, 0))]))
    ring = ring_of(m, max(1, P(1.4)))
    if rarity == 'godforged':
        fill_mask(cv, ring_of(m, max(1, P(2.2))), X, Y, gold_fill(m.width, m.height))
    else:
        fill_mask(cv, ring, X, Y, rgba(rc, 0.95))
    if rarity in ('epic', 'godforged'):
        ir = ring_of(shrink(m, P(3.2)), max(1, P(0.8)))
        fill_mask(cv, ir, X, Y, rgba(rc, 0.6))
    if selected:
        outer = grow(pad_mask(m, int(P(5))), P(3.2))
        o_ring = ring_of(outer, max(1, P(2.2)))
        fill_mask(cv, o_ring, X - int(P(5)), Y - int(P(5)), gold_fill(o_ring.width, o_ring.height))
    return m


def button(cv, x, y, w, h, label, kind='secondary', icon=None, sub=None, key=None, pad_btn=None, chip=None):
    X, Y = P(x), P(y)
    m = poly_mask(P(w), P(h), chamfer_poly(P(w) - 1, P(h) - 1, P(9)))
    shadow(cv, m, X, Y, blur=P(5), off=(0, P(3)), alpha=0.85)
    if kind == 'primary':
        glow(cv, m, X, Y, '#FFB23A', blur=P(8), alpha=0.45)
        fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#FFE7A0'), (0.45, '#E8B04E'), (1, '#9A6224')]))
        fill_mask(cv, ring_of(m, max(1, P(1.4))), X, Y, rgba('#3A2208'))
        hl = grad_img(m.width, m.height, [(0, rgba('#FFFFFF', 0.45)), (0.4, rgba('#FFFFFF', 0)), (1, rgba('#FFFFFF', 0))])
        fill_mask(cv, shrink(m, P(1.5)), X, Y, hl)
        tc, sc = 'ink_text', '#4A2E10'
    elif kind == 'disabled':
        fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#221A15'), (1, '#140F0C')]))
        fill_mask(cv, ring_of(m, max(1, P(1.2))), X, Y, rgba('#4E4034'))
        tc, sc = 'parch_mute', 'parch_mute'
    else:
        fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#3A2A1D'), (1, '#18100B')]))
        fill_mask(cv, ring_of(m, max(1, P(1.4))), X, Y, gold_fill(m.width, m.height, GOLD_SOFT))
        hl = grad_img(m.width, m.height, [(0, rgba('#FFE7A8', 0.14)), (0.4, rgba('#FFFFFF', 0)), (1, rgba('#FFFFFF', 0))])
        fill_mask(cv, shrink(m, P(1.5)), X, Y, hl)
        tc, sc = 'parch', 'parch_dim'
    cx = x + 16
    if key:
        kw = keycap(cv, cx + 12, y + h / 2, key, h=20, alpha=0.5 if kind == 'disabled' else 1.0)
        cx += kw + 12
    if icon:
        place_icon(cv, I.get(icon), cx + 12, y + h / 2, 26, desat=1.0 if kind == 'disabled' else 0,
                   alpha=0.5 if kind == 'disabled' else 1.0, tint='#3A2208' if kind == 'primary' else None)
        cx += 30
    f = cinzel(17, 800)
    ty = y + h / 2 + (6 if not sub else -1)
    draw_text(cv, cx, ty, label, f, fill=tc, tracking=0.08, shadow_a=0 if kind == 'primary' else 0.8)
    if sub:
        draw_text(cv, cx, y + h / 2 + 17, sub, body(15, 'Medium'), fill=sc, shadow_a=0 if kind == 'primary' else 0.8)
    if chip is not None:
        chip(x + w - 14, y + h / 2 + 6)


def section_label(cv, x, y, text, right=None):
    draw_text(cv, x, y, text, cinzel(15, 800), fill='gold_lt', tracking=0.18)
    if right:
        draw_text(cv, x + text_w(text, cinzel(15, 800), 0.18) + 12, y, right, cinzel(15, 700), fill='parch_dim', tracking=0.05)


# ───────────────────────── the Forge ─────────────────────────
def forge_panel(cv):
    w, h = 880, RH - 2 * M
    x0, y0 = RW - M - w, M
    gilt_frame(cv, x0, y0, w, h, r=10, fill_alpha=0.93, thick=3.2)
    # header
    hx = x0 + 36
    framed_slot(cv, hx + 30, y0 + 52, 70, 'circle', 'poi_anvil', icon_scale=0.66, rim_w=2.2, glow_color='#FF9A2E')
    draw_text(cv, hx + 80, y0 + 60, 'THE FORGE', cinzel(36, 800), tracking=0.1,
              grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')], stroke=0.8, stroke_color='#1A0E06')
    draw_text(cv, hx + 82, y0 + 84, 'The Chainyard anvil burns hot', body(17, 'Italic'), fill='parch_dim')
    # heat ring
    rx, ry_ = x0 + w - 238, y0 + 54
    d = int(P(56))
    cm = circle_mask(d)
    X, Y = P(rx) - d / 2, P(ry_) - d / 2
    shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.8)
    fill_mask(cv, cm, X, Y, rgba('#120B08'))
    ring = ring_of(cm, P(6))
    fill_mask(cv, ring, X, Y, rgba('#2A1C14'))
    fill_mask(cv, ImageChops.multiply(ring, conic_mask(d, 19 / 25)), X, Y, grad_img(d, d, [(0, '#FFE08A'), (1, '#FF7A2A')]))
    fill_mask(cv, ring_of(cm, max(1, P(1.2))), X, Y, gold_fill(d, d, GOLD_SOFT))
    draw_text(cv, rx, ry_ + 8, '19', cinzel(22, 800), fill='parch', anchor='m')
    draw_text(cv, rx, ry_ + 44, 'HEAT', cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.15)
    # charges
    cx = x0 + w - 176
    for i in range(3):
        lit = i < 2
        place_icon(cv, I.get('hammer'), cx + i * 30, y0 + 50, 30, desat=0 if lit else 1.0, dark=0 if lit else 0.55,
                   alpha=1 if lit else 0.6)
    draw_text(cv, cx + 30, y0 + 98, 'CHARGES', cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.15)
    # shards
    f = cinzel(24, 800)
    draw_text(cv, x0 + w - 36, y0 + 60, '56', f, fill='parch', anchor='r')
    place_icon(cv, I.get('godshard'), x0 + w - 36 - text_w('56', f) - 18, y0 + 50, 32)
    draw_text(cv, x0 + w - 36, y0 + 98, 'SHARDS', cinzel(12, 800), fill='parch_dim', anchor='r', tracking=0.15)
    filigree_rule(cv, x0 + w / 2, y0 + 116, w / 2 - 40, 0.95, gem='#FFE7A6')

    from forge_body import forge_body
    forge_body(cv, x0, y0, w, h, hx)
    # footer key hints
    fy = y0 + h - 26
    xx = hx
    for key, lab in [('Tab', 'CLOSE'), ('LMB', 'SELECT'), ('F', 'EQUIP'), ('X', 'SALVAGE')]:
        kw = keycap(cv, xx + 14, fy - 5, key, h=20)
        draw_text(cv, xx + kw + 10, fy + 1, lab, cinzel(12, 800), fill='parch_dim', tracking=0.14)
        xx += kw + 22 + text_w(lab, cinzel(12, 800), 0.14) + 16
    draw_text(cv, x0 + w - 36, fy + 1, 'Forge focus: time slows while every player forges', body(15, 'Italic'), fill='parch_mute', anchor='r')
