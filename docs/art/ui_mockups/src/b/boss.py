"""Boss bar, surge flash, downed marker (designer B)."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from gf import *
import icons as I


def boss_bar(cv, name, phase_roman, phase_name, frac, ghost, notches, y=24, w=620, kind='WARLORD'):
    cx = RW / 2
    # legibility halo
    hw_, hh_ = int(P(w + 360)), int(P(170))
    halo = radial_img(hw_ // 3, hh_ // 3, rgba('#050302', 0.7), rgba('#050302', 0), cy=0.3, power=1.4).resize((hw_, hh_), Image.BILINEAR)
    cv.put(halo, P(cx) - hw_ / 2, P(y - 30))
    # kind label + name
    draw_text(cv, cx, y + 14, kind, cinzel(12, 800), fill='#FF8A70', anchor='m', tracking=0.4)
    fn = cinzel(30, 800)
    draw_text(cv, cx, y + 48, name, fn, anchor='m', tracking=0.12,
              grad=[rgba('#FFF4E0'), rgba('#FFD2A0'), rgba('#E8783A')], stroke=0.9, stroke_color='#1A0703',
              glow_color='#FF5A2A', glow_a=0.3)
    nw = text_w(name, fn, 0.12)
    filigree_rule(cv, cx - nw / 2 - 64, y + 38, 46, 0.9, gap=0)
    filigree_rule(cv, cx + nw / 2 + 64, y + 38, 46, 0.9, gap=0)
    # the bar
    by = y + 62
    bh = 18
    x0 = cx - w / 2
    # finials (iron horns) at both ends
    for side in (-1, 1):
        fm = Image.new('L', (int(P(34)), int(P(30))), 0)
        fd = ImageDraw.Draw(fm)
        W_, H_ = fm.size
        pts = [(W_ * 0.05, H_ * 0.5), (W_ * 0.55, H_ * 0.12), (W_ * 0.62, H_ * 0.32), (W_ * 1.0, H_ * 0.3),
               (W_ * 1.0, H_ * 0.7), (W_ * 0.62, H_ * 0.68), (W_ * 0.55, H_ * 0.88)]
        fd.polygon(pts, fill=255)
        if side > 0:
            fm = fm.transpose(Image.FLIP_LEFT_RIGHT)
        fx = (x0 - 30) if side < 0 else (x0 + w - 4)
        FX, FY = P(fx), P(by + bh / 2) - fm.height / 2
        shadow(cv, fm, FX, FY, blur=P(3), off=(0, P(2)), alpha=0.85)
        fill_mask(cv, grow(fm, max(1, P(0.8))), FX, FY, rgba('gold_sh'))
        fill_mask(cv, fm, FX, FY, gold_fill(fm.width, fm.height))
    bar(cv, x0, by, w, bh, frac, [(0, '#FF7A4A'), (0.45, '#C8261E'), (1, '#5E0A08')], ghost=ghost, ghost_color='#F7C98A',
        r=3, rim=0.0, ticks=notches)
    m = rr_mask(P(w), P(bh), P(3))
    fill_mask(cv, ring_of(m, max(1, P(2))), P(x0), P(by), gold_fill(m.width, m.height))
    for t in notches:
        gem_at(cv, x0 + w * t, by - 2, 4.6, '#FFE7A6', glow_a=0.5)
    # crest gem at the top centre of the bar
    gem_at(cv, cx, by + bh + 1, 5.5, 'danger', glow_a=0.7)
    # phase line
    draw_text(cv, cx, by + bh + 26, f'{phase_roman}  ·  {phase_name.upper()}', cinzel(14, 800), fill='#FFB08A', anchor='m', tracking=0.24)


def surge_flash(cv, side='right', text='SURGE', sub='from the east'):
    """Danger telegraph at a screen edge: red-white is allowed here (it IS danger)."""
    w = 180
    x0 = RW - w if side == 'right' else 0
    g = grad_img(int(P(w)), int(P(RH)), [(0, rgba('#FF3B30', 0)), (0.7, rgba('#FF3B30', 0.22)), (1, rgba('#FF6A50', 0.55))], horizontal=True)
    if side == 'left':
        g = g.transpose(Image.FLIP_LEFT_RIGHT)
    v = grad_img(g.width, g.height, [(0, (255, 255, 255, 0)), (0.3, (255, 255, 255, 255)), (0.7, (255, 255, 255, 255)), (1, (255, 255, 255, 0))])
    g = mask_mul(g, v.split()[3])
    cv.put(g, P(x0), 0)
    cy = RH * 0.5
    ax = RW - 40 if side == 'right' else 40
    for i in range(3):
        m = poly_mask(P(22), P(34), [(0, 0), (P(10), 0), (P(22), P(17)), (P(10), P(34)), (0, P(34)), (P(12), P(17))])
        X = P(ax - 64 + i * 20) if side == 'right' else P(ax + 44 - i * 20)
        a = 0.45 + 0.25 * i
        glow(cv, m, X, P(cy - 17), '#FF3B30', blur=P(6), alpha=0.8 * a)
        fill_mask(cv, m, X, P(cy - 17), rgba('#FFFFFF', a))
    draw_text(cv, ax - 40, cy + 50, text, cinzel(20, 900), fill='#FFFFFF', anchor='m', tracking=0.24, stroke=1.2,
              stroke_color='#5A0A06', glow_color='#FF3B30', glow_a=0.8)
    draw_text(cv, ax - 40, cy + 72, sub, body(16, 'Bold'), fill='#FFD8D0', anchor='m', stroke=1.0, stroke_color='#3A0604')


def downed_marker(cv, x, y, secs, frac):
    """Over a downed ally: tether glyph in a danger ring counting down."""
    d = int(P(44))
    cm = circle_mask(d)
    X, Y = P(x) - d / 2, P(y) - d / 2
    glow(cv, cm, X, Y, 'danger', blur=P(10), alpha=0.9, spread=P(2))
    fill_mask(cv, cm, X, Y, rgba('#1A0806', 0.85))
    ring = ring_of(cm, max(1, P(3)))
    fill_mask(cv, ring, X, Y, rgba('#5A1410'))
    fill_mask(cv, ImageChops.multiply(ring, conic_mask(d, frac)), X, Y, rgba('#FFFFFF'))
    place_icon(cv, I.get('tether'), x, y - 2, 26)
    draw_text(cv, x, y + 40, f'{secs}', cinzel(18, 900), fill='#FFFFFF', anchor='m', stroke=1.2, stroke_color='#3A0604')
