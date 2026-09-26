"""GODFORGE final UI mockups: shared components (UI art director synthesis).

Backbone: designer B ("Readable Chaos") layout, clusters and widgets (lib `b/`).
Grafts: designer A ("Gilded Mythic") ornament, portraits, niche cards and god medallions (lib `a/`).
All coordinates are 1920x1080 logical px (UiScale 1.0), exactly the numbers in docs/art/UI_STYLE.md.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, 'b'), os.path.join(HERE, 'a')]

import numpy as np  # noqa: E402
from PIL import Image, ImageChops, ImageDraw, ImageFilter  # noqa: E402

from gf import *  # noqa: E402,F401,F403
import gf  # noqa: E402
import icons as I  # noqa: E402
import hud as H  # noqa: E402
import hud_corners as HC  # noqa: E402
import panels as PN  # noqa: E402

import gmkit as GK  # noqa: E402
import gmorn as GO  # noqa: E402
import gm_icons as GI  # noqa: E402
import busts  # noqa: E402,F401  (registers bust glyphs)
import sigils  # noqa: E402,F401  (registers the other god sigils)

M = 24
PLAYER = {'p1': '#FFC940', 'p2': '#3FD8FF', 'p3': '#B06CFF', 'p4': '#5BE37D'}
GODS = {k: v for k, v in GK.GODS.items()}
ICHOR = '#FFE9B0'


# ───────────────────────── bridges between the two kits ─────────────────────────
def hexs(c):
    """Any colour (token name, hex, RGBA tuple) -> '#RRGGBB' for kit A."""
    if isinstance(c, str):
        if c.startswith('#'):
            return c[:7]
        c = rgba(c)
    return '#%02X%02X%02X' % tuple(int(v) for v in c[:3])


def put1x(cv, img, x, y):
    """Composite a 1x (final-size) RGBA image from kit A at logical (x, y)."""
    big = img.resize((max(1, img.width * SS), max(1, img.height * SS)), Image.BICUBIC)
    cv.put(big, P(x), P(y))


def a_icon(cv, name, cx, cy, size, tint='#E6CFA0', light='#FFF7E6', outline=1.4, pad=0.08, alpha=1.0, style='enamel',
           clip=None, dim=1.0):
    """Kit-A glyph rendered natively at canvas resolution, centred on (cx, cy)."""
    s = int(P(size))
    tint, light = hexs(tint), hexs(light)
    im = GI.render_icon(name, s, tint=tint, light=light, outline=outline * SS, pad=pad, style=style, dim=dim)
    if alpha < 1:
        im = with_alpha(im, alpha)
    X, Y = P(cx) - s / 2, P(cy) - s / 2
    if clip is not None:
        m, mx, my = clip
        crop = Image.new('L', im.size, 0)
        crop.paste(m, (int(mx - X), int(my - Y)))
        im = mask_mul(im, crop)
    cv.put(im, X, Y)


def studs(cv, cx, cy, r, n=8, size=6.0, color='#E9D3A0'):
    for k in range(n):
        a = k * 2 * math.pi / n + math.pi / n
        g = GK.gem(int(P(size)), color, 'lozenge', dim=0.9)
        cv.put(g, P(cx + math.cos(a) * r) - g.width / 2, P(cy + math.sin(a) * r) - g.height / 2)


def horn_corners(cv, x, y, w, h, size=44, gem_color='#FFB82E', stops=None):
    """Forge-horn corners (kit A v2) at the four corners of a rect, spurs overhanging by 10 %."""
    cs = int(P(size))
    cm, off = GO.corner_v2_mask(cs)
    cimg = GK.metal_from_mask(cm, cs, cs, bevel=1.5 * SS, stops=stops or GK.GOLD_RAMP)
    gs = max(8, int(cs * 0.19))
    g = GK.gem(gs, gem_color) if gem_color else None
    gc = int(round(cs * 22 / 120.0))
    for fx, fy in ((False, False), (True, False), (False, True), (True, True)):
        c = cimg
        if fx:
            c = c.transpose(Image.FLIP_LEFT_RIGHT)
        if fy:
            c = c.transpose(Image.FLIP_TOP_BOTTOM)
        X = P(x) - off if not fx else P(x + w) + off - cs
        Y = P(y) - off if not fy else P(y + h) + off - cs
        sh = c.split()[3]
        shadow(cv, sh, X, Y, blur=P(2), off=(0, P(1.5)), alpha=0.8)
        cv.put(c, X, Y)
        if g is not None:
            gx = X + (gc if not fx else cs - gc) - gs / 2
            gy = Y + (gc if not fy else cs - gc) - gs / 2
            cv.put(g, gx, gy)


def sun_crest(cv, cx, top_y, size=64, gem='#FFB82E'):
    """Sun-crest centred on a panel's top edge (62 % of it above the edge)."""
    cr = GO.crest_img(int(P(size)), gem)
    X = P(cx) - cr.width / 2
    Y = P(top_y) - cr.height * 0.62
    shadow(cv, cr.split()[3], X, Y, blur=P(3), off=(0, P(2)), alpha=0.8)
    cv.put(cr, X, Y)


def ember_knot(cv, cx, cy, w, gem_color=None, alpha=1.0):
    """The ember-knot divider (kit A): hairline tapering to points, twin curls and a centre lozenge."""
    d = GK.divider(int(w), 14, gem_color)
    if alpha < 1:
        d = with_alpha(d, alpha)
    shadow(cv, d.resize((d.width * SS, d.height * SS)).split()[3], P(cx - w / 2), P(cy - 7), blur=P(1.5), off=(0, P(1)),
           alpha=0.7 * alpha)
    put1x(cv, d, cx - w / 2, cy - 7)


def ornate_panel(cv, x, y, w, h, corner=64, crest=0, r=10, alpha=0.95, gem_color='#FFB82E', top='#241A14', bot='#0E0A08',
                 tint=None, tint_amt=0.0, frame_stops=None, shadow_a=0.75):
    """Kit A ornate panel (lacquer + lattice + gilt rim + keyline + forge-horn corners + optional sun-crest)."""
    img, (ox, oy) = GO.ornate_panel(int(w), int(h), r=r, frame=3.2, alpha=alpha, corner=corner, gem_color=gem_color, top=top,
                                    bot=bot, tint=tint, tint_amt=tint_amt, crest=crest, frame_stops=frame_stops or GK.GOLD_RAMP)
    m = rr_mask(P(w), P(h), P(r))
    shadow(cv, m, P(x), P(y), blur=P(18), off=(0, P(8)), alpha=shadow_a)
    put1x(cv, img, x - ox, y - oy)


def gilt_card(cv, x, y, w, h, rarity='common', r=8, alpha=0.95, corner=34, gem_color=None, top='#2A1F18', bot='#100B08'):
    """End-screen / detail card: kit A gilded panel with small horn corners (bronze for common)."""
    stops = GK.BRONZE_RAMP if rarity == 'common' else GK.GOLD_RAMP
    img = GK.gilded_panel(int(w), int(h), r=r, frame=2.6, alpha=alpha, corners=corner, top=top, bot=bot,
                          corner_gems=gem_color, frame_stops=stops)
    m = rr_mask(P(w), P(h), P(r))
    shadow(cv, m, P(x), P(y), blur=P(14), off=(0, P(6)), alpha=0.75)
    put1x(cv, img, x, y)


def pchip(cv, cx, cy, slot):
    """Lozenge plaque with the P numeral in the player colour (kit A)."""
    import hud_parts as HP
    chip = HP.pchip(slot, 18)
    put1x(cv, chip, cx - chip.width / 2, cy - chip.height / 2)


def keycap(cv, cx, cy, label, h=20, **kw):
    return gf.keycap(cv, cx, cy, label, h=h, **kw)


def medallion_disc(cv, cx, cy, R, pc, bust, band=2.6, rim=2.2, studs_n=0, glow_c=None, bust_scale=1.0, dim=1.0,
                   downed=False):
    """A round portrait medallion: gilt rim, lacquer window, player-colour enamel band, bust crest (clipped)."""
    d = int(P(R) * 2)
    cm = circle_mask(d)
    X, Y = P(cx) - d / 2, P(cy) - d / 2
    shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.85)
    if glow_c:
        glow(cv, cm, X, Y, glow_c, blur=P(8), alpha=0.95, spread=P(1.5))
    fill_mask(cv, cm, X, Y, gold_fill(d, d))
    fill_mask(cv, ring_of(cm, max(1, P(0.8))), X, Y, rgba('gold_sh'))
    inner = shrink(cm, P(rim))
    fill_mask(cv, inner, X, Y, radial_img(d, d, '#5A3E27', '#100A07', cy=0.36, power=1.1))
    win = shrink(inner, P(band + 1.0))
    a_icon(cv, bust, cx, cy + R * 0.16, R * 2 * 0.9 * bust_scale, tint='#B08A52', light='#F8EBD0', outline=1.2, pad=0.02,
           clip=(win, X, Y), dim=dim)
    if downed:
        fill_mask(cv, win, X, Y, rgba('#1A0606', 0.55))
    band_m = ring_of(inner, max(1, P(band)))
    fill_mask(cv, band_m, X, Y, rgba(pc))
    fill_mask(cv, ring_of(shrink(inner, P(band)), max(1, P(0.9))), X, Y, rgba('#140B06', 0.9))
    if studs_n:
        studs(cv, cx, cy, R - rim / 2 - 0.5, studs_n, size=max(4.5, rim * 1.9))


# ───────────────────────── combat HUD: the Hearth (bottom-left) ─────────────────────────
def hearth(cv, hp=262, hp_max=380, ghost=300, armor=4, armor_max=6, shield=0, dash=2, dash_max=3, ult=0.72,
           q_cd=None, e_cd=(3.4, 0.42), od=0.64, aim='AUTO', aim_note='−10% dmg', bust='bust_valdris', player='p1',
           kit=('bulwark_slam', 'siege_stance'), passive='armor_passive', buffs=(('siege_stance', 0.62, '6'),), low=False):
    base_y = RH - M                      # 1056
    HC.corner_pool(cv, 'bl', 640, 250, 0.62)
    R = 64
    mcx, mcy = M + R, base_y - R - 12    # (88, 980)
    hx0 = mcx + R + 18                   # 170
    hw = 360
    hy = base_y - 128                    # 928
    # gilt rail: pommel (medallion) → blade (HP bar)
    rail_y = hy + 27
    rm = Image.new('L', (int(P(hw + 44)), int(P(8))), 0)
    rd = ImageDraw.Draw(rm)
    rd.polygon([(0, P(3)), (P(hw + 30), P(2.4)), (P(hw + 30), P(5.6)), (0, P(5))], fill=255)
    q = P(4)
    cxr = P(hw + 34)
    rd.polygon([(cxr - q, P(4)), (cxr, P(4) - q), (cxr + q, P(4)), (cxr, P(4) + q)], fill=255)
    X, Y = P(mcx + R - 6), P(rail_y - 4)
    shadow(cv, rm, X, Y, blur=P(2), off=(0, P(1.2)), alpha=0.8)
    fill_mask(cv, rm, X, Y, gold_fill(rm.width, rm.height, GOLD_SOFT))

    # medallion: 8-stud gilt bezel → molten ult trough (conic) → inner rim → P band → bust window
    d = int(P(R) * 2)
    outer = circle_mask(d)
    X, Y = P(mcx) - d / 2, P(mcy) - d / 2
    shadow(cv, outer, X, Y, blur=P(10), off=(0, P(4)), alpha=0.8)
    if ult >= 1.0:
        glow(cv, outer, X, Y, '#FFB23A', blur=P(14), alpha=0.95, spread=P(3))
    fill_mask(cv, outer, X, Y, gold_fill(d, d))
    fill_mask(cv, ring_of(outer, max(1, P(0.9))), X, Y, rgba('gold_sh'))
    trough = circle_mask(int(P(R - 5) * 2))
    tX, tY = P(mcx) - trough.width / 2, P(mcy) - trough.height / 2
    fill_mask(cv, trough, tX, tY, rgba('#140C08'))
    cm = ImageChops.multiply(conic_mask(trough.width, min(ult, 1.0)), trough)
    fill_mask(cv, cm, tX, tY, radial_img(trough.width, trough.height, rgba('#FFF6DA'), rgba('#E8942E'), power=0.55))
    # meniscus glint at the pour front
    a = math.radians(-90 + 360 * min(ult, 1.0))
    e = Image.new('L', trough.size, 0)
    c0 = trough.width / 2
    ImageDraw.Draw(e).line([(c0, c0), (c0 + c0 * math.cos(a), c0 + c0 * math.sin(a))], fill=255, width=max(1, int(P(1.6))))
    fill_mask(cv, ImageChops.multiply(e, trough), tX, tY, rgba('#FFFBEA', 0.9))
    tk = Image.new('L', trough.size, 0)
    tdd = ImageDraw.Draw(tk)
    for i in range(10):
        aa = math.radians(-90 + i * 36)
        tdd.line([(c0 + c0 * 0.84 * math.cos(aa), c0 + c0 * 0.84 * math.sin(aa)), (c0 + c0 * math.cos(aa), c0 + c0 * math.sin(aa))],
                 fill=255, width=max(1, int(P(1.3))))
    fill_mask(cv, ImageChops.multiply(tk, trough), tX, tY, rgba('#140C08', 0.85))
    studs(cv, mcx, mcy, R - 2.4, 8, size=5.2)
    inner = circle_mask(int(P(R - 12) * 2))
    iX, iY = P(mcx) - inner.width / 2, P(mcy) - inner.height / 2
    fill_mask(cv, grow(inner, P(1.8)), iX, iY, gold_fill(inner.width, inner.height, GOLD_SOFT))
    fill_mask(cv, inner, iX, iY, radial_img(inner.width, inner.height, '#5E4129', '#120B08', cy=0.34, power=1.1))
    win = shrink(inner, P(3.6))
    a_icon(cv, bust, mcx, mcy + 9, (R - 12) * 2 * 0.95, tint='#B08A52', light='#F8EBD0', outline=1.3, pad=0.02,
           clip=(win, iX, iY))
    band = ring_of(inner, max(1, P(2.6)))
    fill_mask(cv, band, iX, iY, rgba(player, 0.95))
    fill_mask(cv, ring_of(shrink(inner, P(2.6)), max(1, P(0.9))), iX, iY, rgba('#140B06', 0.9))
    keycap(cv, mcx, base_y - 10, 'R', h=21)
    H.framed_slot(cv, mcx + R * 0.76, mcy - R * 0.76, 34, 'circle', passive, icon_scale=0.66, rim_w=1.3)

    # buffs: round Ø28 sockets above the HP bar with a draining ichor ring
    bx = hx0 + 14
    for (icon, frac, secs) in buffs:
        if icon.startswith('a:'):
            H.framed_slot(cv, bx, hy - 22, 28, 'circle', None, rim_w=1.1)
            a_icon(cv, icon[2:], bx, hy - 22, 21, tint='#D9B56C', outline=0.8)
        else:
            H.framed_slot(cv, bx, hy - 22, 28, 'circle', icon, icon_scale=0.7, rim_w=1.1)
        dd = int(P(32))
        rim_ = ring_of(circle_mask(dd), max(1, P(1.8)))
        fill_mask(cv, ImageChops.multiply(rim_, conic_mask(dd, frac)), P(bx) - dd / 2, P(hy - 22) - dd / 2, rgba(ICHOR, 0.95))
        draw_text(cv, bx + 18, hy - 13, secs, body(14, 'Bold'), fill='parch', stroke=0.8)
        bx += 40

    # HP bar (crimson, pale-amber ghost, leaf finial) + numerals
    fin = Image.new('L', (int(P(22)), int(P(22))), 0)
    fd = ImageDraw.Draw(fin)
    c = fin.width / 2
    fd.polygon([(0, c), (c * 0.9, c - P(6)), (fin.width - 1, c), (c * 0.9, c + P(6))], fill=255)
    fX, fY = P(hx0 + hw - 4), P(hy + 11) - c
    shadow(cv, fin, fX, fY, blur=P(2), off=(0, P(1)), alpha=0.8)
    fill_mask(cv, fin, fX, fY, gold_fill(fin.width, fin.height))
    frac = hp / hp_max
    bar(cv, hx0, hy, hw, 22, frac, [(0, 'hp_lt'), (0.5, 'hp'), (1, 'hp_dk')], ghost=ghost / hp_max, r=4, rim=0.9)
    if shield:
        sf = min(1.0, (hp + shield) / hp_max)
        hatch = Image.new('L', (int(P(hw)), int(P(22))), 0)
        hd = ImageDraw.Draw(hatch)
        for xx in range(-int(P(22)), hatch.width, int(P(5))):
            hd.line([(xx, hatch.height), (xx + hatch.height, 0)], fill=255, width=max(1, int(P(1.6))))
        clip = Image.new('L', hatch.size, 0)
        ImageDraw.Draw(clip).rectangle([P(hw) * frac, P(2), P(hw) * sf, P(20)], fill=255)
        fill_mask(cv, ImageChops.multiply(hatch, clip), P(hx0), P(hy), rgba('ward', 0.9))
    f_num = body(19, 'Bold')
    f_max = body(15, 'Bold')
    tw = text_w(f' / {hp_max}', f_max)
    draw_text(cv, hx0 + hw - 8, hy + 17, f' / {hp_max}', f_max, fill='parch_dim', anchor='r', shadow_a=0.95)
    draw_text(cv, hx0 + hw - 8 - tw, hy + 17.5, f'{hp}', f_num, fill='#FFF8EA', anchor='r', shadow_a=0.95, stroke=0.8)
    # armour plates (left) + dash lozenges (right), on the rail
    ay = hy + 34
    if armor_max:
        aw = 230
        seg_w = (aw - (armor_max - 1) * 3) / armor_max
        for i in range(armor_max):
            sx = hx0 + i * (seg_w + 3)
            m = poly_mask(P(seg_w), P(9), [(P(3), 0), (P(seg_w), 0), (P(seg_w) - P(3), P(9) - 1), (0, P(9) - 1)])
            shadow(cv, m, P(sx), P(ay), blur=P(2), off=(0, P(1)), alpha=0.8)
            if i < armor:
                fill_mask(cv, m, P(sx), P(ay), grad_img(m.width, m.height, [(0, '#EEF2F5'), (0.5, 'steel'), (1, 'steel_dk')]))
            else:
                fill_mask(cv, m, P(sx), P(ay), rgba('#1A1512', 0.9))
                fill_mask(cv, ring_of(m, 1), P(sx), P(ay), rgba('steel_dk', 0.9))
    for i in range(dash_max):
        px_ = hx0 + hw - 6 - (dash_max - 1 - i) * 26
        full = i < dash
        gem_at(cv, px_, ay + 4.5, 7.2, '#FFE7A6' if full else '#2A1F18', facet=full, glow_a=0.5 if full else 0)
        if not full:
            d2 = int(P(22))
            rim_ = ring_of(circle_mask(d2), max(1, P(1.4)))
            fill_mask(cv, ImageChops.multiply(rim_, conic_mask(d2, 0.6)), P(px_) - d2 / 2, P(ay + 4.5) - d2 / 2, rgba('gold_lt', 0.9))

    # kit row: Q / E chamfered squares, V overdrive hex, aim chip
    ry = base_y - 44                     # 1012
    q_x = hx0 + 30
    e_x = q_x + 72
    v_x = e_x + 80
    for (x, key, icon, cd) in ((q_x, 'Q', kit[0], q_cd), (e_x, 'E', kit[1], e_cd)):
        if cd:
            H.framed_slot(cv, x, ry, 60, 'ability', icon, icon_scale=0.74, state='cooldown', frac_cd=cd[1],
                          cd_text=f'{cd[0]:.1f}'.rstrip('0').rstrip('.'))
        else:
            H.framed_slot(cv, x, ry, 60, 'ability', icon, icon_scale=0.74, glow_color='#FFC24A')
        keycap(cv, x, ry + 31, key, h=20)
    s = 68
    m = H.slot_shape('hex', P(s))
    X, Y = P(v_x) - m.width / 2, P(ry - 2) - m.height / 2
    shadow(cv, m, X, Y, blur=P(6), off=(0, P(3)), alpha=0.85)
    if od >= 1:
        glow(cv, m, X, Y, '#FFC940', blur=P(10), alpha=0.9, spread=P(2))
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#2B1F16'), (1, '#0E0907')]))
    fl = Image.new('L', m.size, 0)
    lvl = m.height * (1 - min(od, 1))
    pts = [(0, m.height)] + [(xx, lvl + math.sin(xx / m.width * math.pi * 3) * P(2.2)) for xx in range(0, m.width + 1, 4)] + [(m.width, m.height)]
    ImageDraw.Draw(fl).polygon(pts, fill=255)
    fl = ImageChops.multiply(fl, shrink(m, P(2)))
    fill_mask(cv, fl, X, Y, grad_img(m.width, m.height, [(0, '#FFF6DA'), (0.35, '#FFC95A'), (0.7, '#E8942E'), (1, '#7A3E12')]))
    surf = Image.new('L', m.size, 0)
    ImageDraw.Draw(surf).line(pts[1:-1], fill=255, width=max(1, int(P(1.4))))
    fill_mask(cv, ImageChops.multiply(surf, shrink(m, P(2))), X, Y, rgba('#FFFBEA', 0.9))
    if od >= 1:
        place_icon(cv, I.get('overdrive'), v_x, ry - 2, 40)
    else:
        place_icon(cv, I.get('overdrive'), v_x, ry - 1, 40, tint='#3A2210', alpha=0.9)
        place_icon(cv, I.get('overdrive'), v_x, ry - 2, 38, tint='#2A1608', alpha=0.95)
    fill_mask(cv, ring_of(m, max(1, P(2))), X, Y, gold_fill(m.width, m.height))
    keycap(cv, v_x, ry + 31, 'V', h=20)
    ax = v_x + 46
    place_icon(cv, I.get('aim_auto' if aim == 'AUTO' else 'aim_manual' if aim == 'MANUAL' else 'aim_assisted'), ax + 13, ry - 8, 26)
    draw_text(cv, ax + 32, ry - 3, aim, cinzel(14, 800), fill='parch', tracking=0.1)
    draw_text(cv, ax + 32, ry + 15, aim_note, body(15, 'Medium'), fill='parch_dim')


# ───────────────────────── top-left: party frames ─────────────────────────
def party(cv, allies):
    """allies: [(slot 1..3 as P number, name, character, bust, hp, state, extra)]"""
    HC.corner_pool(cv, 'tl', 420, 250, 0.55)
    y = M
    for (pn, name, char, bust, hp, state, extra) in allies:
        pc = PLAYER[f'p{pn}']
        cx, cy = M + 23, y + 23
        downed = state == 'downed'
        medallion_disc(cv, cx, cy, 23, rgba('danger') if downed else pc, 'skull' if downed else bust, band=2.6, rim=2.2,
                       glow_c='danger' if downed else None, bust_scale=0.95 if not downed else 0.8)
        pchip(cv, cx, cy + 23, pn - 1)
        tx = cx + 34
        fn = body(18, 'Bold')
        draw_text(cv, tx, cy - 4, name, fn, fill='parch')
        nw = text_w(name, fn)
        if downed:
            draw_text(cv, tx + nw + 10, cy - 5, 'DOWNED', cinzel(13, 800), fill='danger', tracking=0.12)
            bar(cv, tx, cy + 5, 170, 8, extra, [(0, '#FFFFFF'), (1, '#FFB0A8')], r=3, rim=0.5, sheen=False)
            draw_text(cv, tx + 178, cy + 13, f'{int(extra * 20)} s', body(15, 'Bold'), fill='parch')
        else:
            draw_text(cv, tx + nw + 9, cy - 5, char.upper(), cinzel(12, 800), fill='parch_dim', tracking=0.14)
            bar(cv, tx, cy + 5, 170, 8, hp, [(0, 'hp_lt'), (1, 'hp_dk')], ghost=min(1, hp + (0.12 if pn == 3 else 0)), r=3, rim=0.6,
                sheen=False)
            if extra == 'ult':
                place_icon(cv, I.get('overdrive'), tx + 184, cy + 9, 16)
        y += 54


def toast(cv, y, icon, parts, a=1.0, a_glyph=None):
    x = M
    H.ink_smear(cv, 0, y - 18, 440, 30, 'left', a=0.6 * a)
    acc = Image.new('L', (max(1, int(P(2))), int(P(22))), 255)
    fill_mask(cv, acc, P(x - 8), P(y - 16), with_alpha(gold_fill(acc.width, acc.height), a))
    if a_glyph:
        a_icon(cv, a_glyph[0], x + 11, y - 5, 22, tint=a_glyph[1], light=mix(a_glyph[1], '#FFFFFF', 0.6), alpha=a, outline=1.1)
    else:
        place_icon(cv, I.get(icon), x + 11, y - 5, 20, alpha=a)
    xx = x + 28
    for t, f, col in parts:
        draw_text(cv, xx, y, t, f, fill=col, alpha=a)
        xx += text_w(t, f)


# ───────────────────────── top-right: the Wayfinder ─────────────────────────
def wayfinder(cv, map_img=None, seals=3, req=7, timer='07:32', threat=3, warlord=False, gate='sealed',
              objectives=(('poi_shrine', 'Shrine of Pyra', 250, 58), ('poi_reliquary', 'Reliquary', 160, 96)),
              event=('poi_anvil', 'ANVIL · KINDLING', 0.92), surge=None, biome='CINDER WASTES', minimap=True, map_dots=None):
    xr = RW - M
    HC.corner_pool(cv, 'tr', 470, 500, 0.64)
    y = M
    if minimap:
        w, h = 280, 176
        x0 = xr - w
        X, Y = P(x0), P(y)
        m = rr_mask(P(w), P(h), P(10))
        shadow(cv, m, X, Y, blur=P(10), off=(0, P(4)), alpha=0.8)
        fill_mask(cv, m, X, Y, rgba('#0C0806', 0.94))
        if map_img is not None:
            mi = map_img.resize((m.width, m.height), Image.LANCZOS).convert('RGBA')
            fog = radial_img(m.width, m.height, rgba('#000000', 0), rgba('#0C0806', 0.97), cx=0.5, cy=0.55, rx=0.46, ry=0.6, power=2.2)
            mi.alpha_composite(fog)
            fill_mask(cv, shrink(m, P(3)), X, Y, with_alpha(mi, 0.95))
        fill_mask(cv, ring_of(m, P(2.8)), X, Y, gold_fill(m.width, m.height))
        fill_mask(cv, ring_of(shrink(m, P(4.4)), max(1, P(0.9))), X, Y, rgba('gold_dk', 0.9))
        horn_corners(cv, x0, y, w, h, size=30, gem_color=None)
        gem_at(cv, x0 + w / 2, y + 1, 6, '#FFE7A6', glow_a=0.45)
        if map_dots:
            map_dots(x0, y)
        y += h + 18
    f_lab = cinzel(14, 800)
    ft = cinzel(24, 800)
    draw_text(cv, xr, y + 20, timer, ft, fill='#FFF8EA', anchor='r')
    tw = text_w(timer, ft)
    place_icon(cv, I.get('hourglass'), xr - tw - 14, y + 11, 18, alpha=0.85)
    draw_text(cv, xr - tw - 30, y + 18, biome, f_lab, fill='parch_dim', anchor='r', tracking=0.16)
    ember_knot(cv, xr - 140, y + 34, 280)
    y += 46
    sx = xr
    txt = f'{seals}/{req}'
    fs = cinzel(19, 800)
    draw_text(cv, sx, y + 14, txt, fs, fill='gold_lt', anchor='r')
    sx -= text_w(txt, fs) + 18
    for i in range(req)[::-1]:
        if i < seals:
            place_icon(cv, I.get('seal'), sx, y + 7, 26)
        else:
            dd = int(P(17))
            cm = circle_mask(dd)
            fill_mask(cv, cm, P(sx) - dd / 2, P(y + 7) - dd / 2, rgba('#0E0907', 0.92))
            fill_mask(cv, ring_of(cm, max(1, P(1.3))), P(sx) - dd / 2, P(y + 7) - dd / 2, rgba('gold_dk'))
        sx -= 24
    y += 34
    gx = xr
    gate_word = {'sealed': 'SEALED', 'open': 'GATE OPEN', 'gathering': 'GATHER 6'}[gate]
    draw_text(cv, gx, y + 13, gate_word, f_lab, fill='parch_dim' if gate == 'sealed' else 'gold_lt', anchor='r', tracking=0.1)
    gx -= text_w(gate_word, f_lab, 0.1) + 16
    place_icon(cv, I.get('poi_gate'), gx, y + 7, 22, desat=0.7 if gate == 'sealed' else 0, dark=0.25 if gate == 'sealed' else 0)
    gx -= 30
    ww = 'SLAIN' if warlord is True else 'IN BATTLE' if warlord == 'engaged' else 'WARLORD'
    draw_text(cv, gx, y + 13, ww, f_lab, fill='parch_dim' if warlord is not True else 'parch_mute', anchor='r', tracking=0.1)
    gx -= text_w(ww, f_lab, 0.1) + 16
    a_icon(cv, 'warlord', gx, y + 7, 24, tint='#FF7A5A', light='#FFD8C8', outline=1.1)
    y += 32
    tx = xr
    for i in range(5)[::-1]:
        lit = i < threat
        pw, ph = 15, 11
        m = poly_mask(P(pw), P(ph), [(0, 0), (P(pw) - P(5), 0), (P(pw) - 1, P(ph) / 2), (P(pw) - P(5), P(ph) - 1), (0, P(ph) - 1), (P(5), P(ph) / 2)])
        X_, Y_ = P(tx - pw), P(y + 2)
        if lit:
            col = mix('#FFC95A', '#E8602E', i / 4)
            glow(cv, m, X_, Y_, col, blur=P(3), alpha=0.7)
            fill_mask(cv, m, X_, Y_, col)
        else:
            fill_mask(cv, m, X_, Y_, rgba('#231914', 0.95))
            fill_mask(cv, ring_of(m, 1), X_, Y_, rgba('#5A4232'))
        tx -= pw + 1
    roman = ['I', 'II', 'III', 'IV', 'V'][max(0, threat - 1)]
    draw_text(cv, tx - 8, y + 12, f'THREAT {roman}', f_lab, fill='parch_dim', anchor='r', tracking=0.12)
    y += 32
    if surge:
        side, secs, frac = surge
        draw_text(cv, xr, y + 13, f'{secs} s', cinzel(15, 800), fill='parch', anchor='r')
        draw_text(cv, xr - 40, y + 13, f'SURGE · {side}', f_lab, fill='#FFD2C0', anchor='r', tracking=0.1)
        bar(cv, xr - 262, y + 22, 262, 6, frac, [(0, '#FFB08A'), (1, '#E8602E')], r=3, rim=0.5, sheen=False)
        y += 38
    if event:
        icon, lab, frac = event
        draw_text(cv, xr, y + 13, f'{frac * 100:.0f}%', cinzel(15, 800), fill=ICHOR, anchor='r')
        draw_text(cv, xr - 50, y + 13, lab, f_lab, fill=ICHOR, anchor='r', tracking=0.1)
        place_icon(cv, I.get(icon), xr - 50 - text_w(lab, f_lab, 0.1) - 16, y + 7, 22)
        bar(cv, xr - 262, y + 22, 262, 6, frac, [(0, '#FFF6DA'), (0.5, '#FFC95A'), (1, '#E8942E')], r=3, rim=0.5, sheen=False)
        y += 38
    for icon, name, bearing, dist in objectives:
        dt = f'{dist} m'
        fd = body(16, 'Bold')
        draw_text(cv, xr, y + 13, dt, fd, fill='parch', anchor='r')
        bx = xr - text_w(dt, fd) - 13
        HC.chevron(cv, bx, y + 8, bearing)
        fb = body(17, 'Medium')
        draw_text(cv, bx - 14, y + 13, name, fb, fill='parch_dim', anchor='r')
        nx = bx - 14 - text_w(name, fb) - 15
        place_icon(cv, I.get(icon), nx, y + 7, 22)
        y += 28
    return y


# ───────────────────────── transients ─────────────────────────
def callout(cv, cx, y, name, count=None, stops=('#FFF7DA', '#FFD36B', '#3FD8FF'), elems=None):
    f = cinzel(38, 900)
    w = text_w(name, f, 0.06)
    hw_, hh_ = int(P(w + 300)), int(P(124))
    halo = radial_img(hw_ // 3, hh_ // 3, rgba('#050302', 0.62), rgba('#050302', 0), power=1.5).resize((hw_, hh_), Image.BILINEAR)
    cv.put(halo, P(cx) - hw_ / 2, P(y - 14) - hh_ / 2)
    draw_text(cv, cx, y, name, f, anchor='m', tracking=0.06, grad=[rgba(s) for s in stops], stroke=1.4,
              stroke_color='#1A0E06', glow_color=stops[2], glow_a=0.55, shadow_a=0.8)
    if elems:
        for sgn, el in ((-1, elems[0]), (1, elems[1])):
            ex = cx + sgn * (w / 2 + 30)
            H.framed_slot(cv, ex, y - 13, 30, 'circle', el, icon_scale=0.72, rim_w=1.3)
    if count:
        draw_text(cv, cx + w / 2 + (58 if elems else 10), y - 2, f'×{count}', body(26, 'Bold'), fill='gold_lt', stroke=1.2, shadow_a=0.9)
    ember_knot(cv, cx, y + 16, w + 80)


def region_banner(cv, name, sub, y=236):
    f = cinzel(44, 700)
    w = text_w(name, f, 0.08)
    hw_, hh_ = int(P(w + 420)), int(P(170))
    halo = radial_img(hw_ // 3, hh_ // 3, rgba('#050302', 0.66), rgba('#050302', 0), power=1.5).resize((hw_, hh_), Image.BILINEAR)
    cv.put(halo, P(RW / 2) - hw_ / 2, P(y - 12) - hh_ / 2)
    ember_knot(cv, RW / 2, y - 54, w + 180, gem_color='#FFE7A6')
    draw_text(cv, RW / 2, y, name, f, anchor='m', tracking=0.08, grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')],
              stroke=1.0, stroke_color='#1A0E06', shadow_a=0.9)
    draw_text(cv, RW / 2, y + 30, sub, body(18, 'Italic'), fill='parch_dim', anchor='m')


def dmg(cv, x, y, n, kind='normal', color=None):
    if kind == 'crit':
        f = body(28, 'Bold')
        draw_text(cv, x, y, str(n), f, fill=color or ICHOR, anchor='m', stroke=1.6, stroke_color='#1A0B04',
                  glow_color='#FFB347', glow_a=0.6)
        w = text_w(str(n), f)
        a_icon(cv, 'radiant', x + w / 2 + 9, y - 17, 16, tint='#FFC873', light='#FFFBEA', outline=0.8)
    else:
        f = body(21, 'Bold')
        draw_text(cv, x, y, str(n), f, fill=color or 'kinetic', anchor='m', stroke=1.2, stroke_color='#1A0B04')


def edge_pin(cv, x, y, glyph, ring, label, dist, angle_deg, tint='#E6CFA0', pulse=False, a=1.0):
    """Off-screen marker: Ø34 medallion + outward gilt nub; distance (+ name for top-3) tucked inward."""
    r = 17
    d = int(P(r * 2))
    cm = circle_mask(d)
    X, Y = P(x) - d / 2, P(y) - d / 2
    nub = Image.new('L', (d * 2, d * 2), 0)
    c = d
    ang = math.radians(angle_deg - 90)
    tip = (c + (d / 2 + P(11)) * math.cos(ang), c + (d / 2 + P(11)) * math.sin(ang))
    l_ = (c + d / 2 * 0.8 * math.cos(ang + 0.55), c + d / 2 * 0.8 * math.sin(ang + 0.55))
    r_ = (c + d / 2 * 0.8 * math.cos(ang - 0.55), c + d / 2 * 0.8 * math.sin(ang - 0.55))
    ImageDraw.Draw(nub).polygon([tip, l_, r_], fill=255)
    shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.8 * a)
    if pulse:
        glow(cv, cm, X, Y, ring, blur=P(8), alpha=0.9, spread=P(2))
    fill_mask(cv, nub, X - d / 2, Y - d / 2, gold_fill(nub.width, nub.height) if ring == 'gold' else rgba(ring, a))
    fill_mask(cv, cm, X, Y, with_alpha(radial_img(d, d, '#3A291C', '#0D0806'), 0.92 * a))
    fill_mask(cv, ring_of(cm, max(1, P(2))), X, Y, gold_fill(d, d) if ring == 'gold' else rgba(ring, a))
    a_icon(cv, glyph, x, y, 24, tint=tint, light=mix(tint, '#FFFFFF', 0.6), outline=1.0, alpha=a)


def pin_label(cv, x, y, label, dist, anchor='m'):
    draw_text(cv, x, y, dist, body(14, 'Bold'), fill='parch', anchor=anchor, shadow_a=0.95, stroke=1.0)
    if label:
        draw_text(cv, x, y + 16, label, body(14, 'Medium'), fill='parch_dim', anchor=anchor, shadow_a=0.95, stroke=0.8)


def ally_tag(cv, cx, cy, pn, name, hp, show_name=False):
    pc = PLAYER[f'p{pn}']
    if show_name:
        f = body(14, 'Bold')
        w = text_w(name, f)
        m = rr_mask(P(w + 22), P(19), P(9.5))
        X, Y = P(cx - (w + 22) / 2), P(cy - 30)
        shadow(cv, m, X, Y, blur=P(3), off=(0, P(1)), alpha=0.7)
        fill_mask(cv, m, X, Y, rgba('#0C0806', 0.72))
        pip = circle_mask(int(P(7)))
        fill_mask(cv, pip, X + P(7), Y + P(6), rgba(pc))
        draw_text(cv, cx - (w + 22) / 2 + 16, cy - 16, name, f, fill='parch', shadow_a=0)
    bar(cv, cx - 23, cy - 8, 46, 6, hp, [(0, 'hp_lt'), (1, 'hp_dk')], r=3, rim=0.0, sheen=False, trough='#0B0706')
    tip = poly_mask(P(8), P(5), [(0, 0), (P(8), 0), (P(4), P(5))])
    fill_mask(cv, tip, P(cx - 4), P(cy - 1), rgba(pc))


def boon_chip(cv, god='pyra', waiting=1, y=880, key='Tab'):
    """Non-blocking boon offer, docked in the Arsenal cluster above the wallet (never in the E approach lane):
    [Tab] PYRA OFFERS / a boon · 1 waiting, then the god medallion at the screen edge."""
    name, c1, c2, _ = GODS[god]
    R = 30
    cx = RW - M - R
    d = int(P(R * 2))
    cm = circle_mask(d)
    X, Y = P(cx) - d / 2, P(y) - d / 2
    H.ink_smear(cv, RW - 340, y - 30, 340, 60, 'right', a=0.55)
    glow(cv, cm, X, Y, c1, blur=P(12), alpha=0.5, spread=P(2))
    shadow(cv, cm, X, Y, blur=P(6), off=(0, P(3)), alpha=0.85)
    fill_mask(cv, cm, X, Y, gold_fill(d, d))
    inner = shrink(cm, P(3.6))
    fill_mask(cv, inner, X, Y, radial_img(d, d, mix(c1, '#000000', 0.25), mix(c1, '#000000', 0.8), cy=0.4, power=1.2))
    a_icon(cv, god, cx, y, 40, tint=c2 if god in ('pyra', 'umbra_rex') else c1, light=mix(c2, '#FFFFFF', 0.5), outline=1.2)
    tx = cx - R - 14
    f1 = cinzel(14, 800)
    t1 = f'{name.upper()} OFFERS'
    draw_text(cv, tx, y - 3, t1, f1, fill=c2 if god in ('pyra', 'umbra_rex') else mix(c1, '#FFFFFF', 0.4), anchor='r', tracking=0.14)
    draw_text(cv, tx, y + 18, f'a boon · {waiting} waiting', body(16, 'Medium'), fill='parch_dim', anchor='r')
    kw = max(text_w(t1, f1, 0.14), text_w(f'a boon · {waiting} waiting', body(16, 'Medium')))
    keycap(cv, tx - kw - 30, y + 3, key, h=22)


def save_png(cv, path):
    """Downsample and save with 6-bit channels (visually lossless) so each PNG stays well under 2 MB."""
    out = cv.img.resize((gf.W, gf.H), Image.LANCZOS).convert('RGB')
    a = np.asarray(out)
    q = ((a >> 2) << 2) | 2
    Image.fromarray(q.astype(np.uint8)).save(path, optimize=True)
    return path


def pad_stud(cv, cx, cy, pos='south', r=10, alpha=1.0):
    """Generic gamepad face button: a dark round stud with four position dots, the pressed one lit (no colours, no letters)."""
    R = P(r)
    m = Image.new('L', (int(R * 2) + 2, int(R * 2) + 2), 0)
    ImageDraw.Draw(m).ellipse([0, 0, R * 2, R * 2], fill=255)
    X, Y = P(cx) - R, P(cy) - R
    shadow(cv, m, X, Y, blur=P(2), off=(0, P(1.5)), alpha=0.8 * alpha)
    fill_mask(cv, m, X, Y, with_alpha(grad_img(m.width, m.height, [(0, '#3A2B1E'), (1, '#140E0A')]), alpha))
    fill_mask(cv, ring_of(m, max(1, P(1.2))), X, Y, with_alpha(gold_fill(m.width, m.height, GOLD_SOFT), alpha))
    offs = {'north': (0, -1), 'south': (0, 1), 'west': (-1, 0), 'east': (1, 0)}
    for k, (dx, dy) in offs.items():
        dd = int(P(r * (0.42 if k == pos else 0.3)))
        dm = circle_mask(max(2, dd))
        px_, py_ = cx + dx * r * 0.48, cy + dy * r * 0.48
        fill_mask(cv, dm, P(px_) - dm.width / 2, P(py_) - dm.height / 2,
                  rgba('#FFE9B0', alpha) if k == pos else rgba('#6E5A44', 0.9 * alpha))


def rarity_gem(cv, cx, cy, r, rarity, glow_a=0.55):
    """Rarity gem whose CUT is the colour-blind backup: Common round cabochon, Rare lozenge, Epic hexagon step-cut,
    Godforged eight-point star."""
    col = rgba(rarity)
    R = P(r) * 2
    n = int(R * 2 + 8)
    m = Image.new('L', (n, n), 0)
    d = ImageDraw.Draw(m)
    c = n / 2
    if rarity == 'common':
        d.ellipse([c - R * 0.86, c - R * 0.86, c + R * 0.86, c + R * 0.86], fill=255)
    elif rarity == 'rare':
        d.polygon([(c, c - R), (c + R * 0.9, c), (c, c + R), (c - R * 0.9, c)], fill=255)
    elif rarity == 'epic':
        d.polygon([(c + R * math.cos(math.radians(a)), c + R * math.sin(math.radians(a))) for a in range(-90, 270, 60)], fill=255)
    else:
        pts = []
        for i in range(16):
            rr = R if i % 2 == 0 else R * 0.5
            a = math.radians(-90 + i * 22.5)
            pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
        d.polygon(pts, fill=255)
    m = m.resize((n // 2, n // 2), Image.LANCZOS)
    X, Y = P(cx) - m.width / 2, P(cy) - m.height / 2
    if glow_a:
        glow(cv, m, X, Y, col, blur=P(r * 0.9), alpha=glow_a)
    fill_mask(cv, grow(m, max(1, P(0.9))), X, Y, rgba('gold_sh'))
    g = grad_img(m.width, m.height, [(0, mix(col, '#FFFFFF', 0.55)), (0.45, col), (1, mix(col, '#000000', 0.45))])
    fill_mask(cv, m, X, Y, g)
    f = Image.new('L', m.size, 0)
    c2 = m.width / 2
    rr = c2 * 0.5
    ImageDraw.Draw(f).polygon([(c2 - rr * 0.1, c2 - rr), (c2 + rr * 0.55, c2 - rr * 0.1), (c2 - rr * 0.1, c2 - rr * 0.1)], fill=200)
    fill_mask(cv, f, X, Y, rgba('#FFFFFF', 0.7))
HC.RGEM = rarity_gem
