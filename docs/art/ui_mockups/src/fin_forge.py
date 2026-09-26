"""The Forge drawer (final): kit-A ornate shell (forge-horn corners, sun-crest) around kit-B's body."""
from fin import *  # noqa: F401,F403
import fin as F
from panels import card, section_label, delta_chip, button, RNAME

DRAWER = (1008, 64, 888, 976)   # x, y, w, h at 1920x1080


def dashed_rect(cv, x, y, w, h, color, dash=9, gap=6, width=1.6, inset=1.0):
    """A dashed ichor outline (explicit dashes along each edge): 'not yet yours'."""
    m = Image.new('L', (int(P(w)) + 2, int(P(h)) + 2), 0)
    d = ImageDraw.Draw(m)
    t = P(width)
    i = P(inset)
    xx = i
    while xx < P(w) - i:
        x1 = min(xx + P(dash), P(w) - i)
        d.rectangle([xx, i, x1, i + t], fill=255)
        d.rectangle([xx, P(h) - i - t, x1, P(h) - i], fill=255)
        xx += P(dash + gap)
    yy = i
    while yy < P(h) - i:
        y1 = min(yy + P(dash), P(h) - i)
        d.rectangle([i, yy, i + t, y1], fill=255)
        d.rectangle([P(w) - i - t, yy, P(w) - i, y1], fill=255)
        yy += P(dash + gap)
    glow(cv, m, P(x), P(y), '#FFC873', blur=P(3), alpha=0.5)
    fill_mask(cv, m, P(x), P(y), rgba(color, 0.95))


def forge_header(cv, x0, y0, w, heat=19, heat_max=25, charges=2, charges_max=3, shards=56):
    cx = x0 + w / 2
    draw_text(cv, cx, y0 + 70, 'THE FORGE', cinzel(36, 800), anchor='m', tracking=0.14,
              grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')], stroke=0.8, stroke_color='#1A0E06', glow_color='#FF9A2E',
              glow_a=0.25)
    draw_text(cv, cx, y0 + 96, 'The Chainyard anvil burns hot', body(17, 'Italic'), fill='parch_dim', anchor='m')
    # left block: the heat ring (time left in the Hot window) and the strike charges
    rx, ry_ = x0 + 72, y0 + 62
    d = int(P(56))
    cm = circle_mask(d)
    X, Y = P(rx) - d / 2, P(ry_) - d / 2
    shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.8)
    fill_mask(cv, cm, X, Y, rgba('#120B08'))
    ring = ring_of(cm, P(6))
    fill_mask(cv, ring, X, Y, rgba('#2A1C14'))
    fill_mask(cv, ImageChops.multiply(ring, conic_mask(d, heat / heat_max)), X, Y, grad_img(d, d, [(0, '#FFF6DA'), (0.5, '#FFC95A'), (1, '#E8942E')]))
    fill_mask(cv, ring_of(cm, max(1, P(1.2))), X, Y, gold_fill(d, d, GOLD_SOFT))
    draw_text(cv, rx, ry_ + 8, f'{heat}', cinzel(22, 800), fill='parch', anchor='m')
    draw_text(cv, rx, ry_ + 46, 'HEAT', cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.15)
    hx = x0 + 136
    for i in range(charges_max):
        lit = i < charges
        place_icon(cv, I.get('hammer'), hx + 15 + i * 30, y0 + 58, 30, desat=0 if lit else 1.0, dark=0 if lit else 0.55,
                   alpha=1 if lit else 0.6)
    draw_text(cv, hx + 45, y0 + 108, 'CHARGES', cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.15)
    # right block: godshards
    f = cinzel(26, 800)
    draw_text(cv, x0 + w - 40, y0 + 70, f'{shards}', f, fill='parch', anchor='r')
    place_icon(cv, I.get('godshard'), x0 + w - 40 - text_w(f'{shards}', f) - 18, y0 + 60, 32)
    draw_text(cv, x0 + w - 40, y0 + 108, 'SHARDS', cinzel(12, 800), fill='parch_dim', anchor='r', tracking=0.15)
    F.ember_knot(cv, cx, y0 + 128, w - 120, gem_color='#FFE7A6')


def forge_body(cv, x0, y0, w, h, hx):
    y = y0 + 158
    section_label(cv, hx, y, 'THE WEAPON')
    y += 14
    RH_ = 180
    card(cv, hx, y, 196, RH_, 'common', r=8)
    cc = hx + 98
    glow(cv, circle_mask(int(P(80))), P(cc) - P(40), P(y + 72) - P(40), '#3FD8FF', blur=P(18), alpha=0.35)
    place_icon(cv, I.get('colossus_cannon'), cc, y + 72, 100)
    draw_text(cv, cc, y + 140, 'COLOSSUS CANNON', cinzel(15, 800), fill='parch', anchor='m', tracking=0.06)
    place_icon(cv, I.get('el_storm'), cc - 30, y + 158, 18)
    draw_text(cv, cc - 18, y + 164, 'STORM', cinzel(13, 800), fill='storm', tracking=0.12)
    sockets = [('CORE', 'core', 'stormcore', 'Stormcore', 'rare', False, False),
               ('MECHANISM', 'mech', 'ricochet', 'Ricochet', 'epic', False, False),
               ('RELIC', 'relic', 'nyctian_eye', 'Nyctian Eye', 'rare', False, True),
               ('SIGIL', 'sigil', 'sigil_anvilheart', 'Anvilheart', 'godforged', True, False)]
    sx = hx + 196 + 16
    for (lab, kind, icon, name, rar, locked, target) in sockets:
        cw = 138
        card(cv, sx, y, cw, RH_, rar, r=8)
        if target:
            tm = rr_mask(P(cw + 8), P(RH_ + 8), P(11))
            glow(cv, ring_of(tm, max(1, P(1.6))), P(sx - 4), P(y - 4), '#FFC873', blur=P(6), alpha=0.7)
            fill_mask(cv, ring_of(tm, max(1, P(2.0))), P(sx - 4), P(y - 4), rgba(ICHOR, 0.95))
            tg = rr_mask(P(84), P(20), P(10))
            fill_mask(cv, tg, P(sx + cw / 2 - 42), P(y - 14), grad_img(tg.width, tg.height, [(0, '#FFF6DA'), (1, '#FFC873')]))
            draw_text(cv, sx + cw / 2, y + 1, 'REPLACE', cinzel(11, 800), fill='ink_text', anchor='m', tracking=0.14, shadow_a=0)
        else:
            draw_text(cv, sx + cw / 2, y + 22, lab, cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.16)
        H.framed_slot(cv, sx + cw / 2, y + 70, 74, kind, icon, icon_scale=0.64, rim_w=2.0,
                      glow_color=rgba(rar) if rar in ('epic', 'godforged') else None)
        F.rarity_gem(cv, sx + cw / 2, y + 110, 6, rar, glow_a=0.6)
        draw_text(cv, sx + cw / 2, y + 136, name, body(16, 'Bold'), fill=rar if rar != 'common' else 'parch', anchor='m')
        if locked:
            place_icon(cv, I.get('lock'), sx + cw / 2 - 30, y + 159, 16)
            draw_text(cv, sx + cw / 2 - 18, y + 164, 'LOCKED', cinzel(12, 800), fill='parch_mute', tracking=0.14)
        else:
            bxm = poly_mask(P(108), P(26), chamfer_poly(P(108) - 1, P(26) - 1, P(6)))
            bX, bY = P(sx + cw / 2 - 54), P(y + 146)
            fill_mask(cv, bxm, bX, bY, rgba('#140E0A', 0.95))
            fill_mask(cv, ring_of(bxm, max(1, P(1))), bX, bY, rgba('gold_dk'))
            place_icon(cv, I.get('dice'), sx + cw / 2 - 38, y + 159, 17)
            draw_text(cv, sx + cw / 2 - 26, y + 164, 'REROLL', cinzel(11, 800), fill='parch_dim', tracking=0.1)
            draw_text(cv, sx + cw / 2 + 48, y + 164, '6', body(14, 'Bold'), fill='parch', anchor='r')
            place_icon(cv, I.get('godshard'), sx + cw / 2 + 32, y + 159, 13)
        sx += cw + 12
    y += RH_ + 22
    # live DPS: current → preview (the real apply_action on a copy)
    fbig = cinzel(38, 800)
    draw_text(cv, hx, y + 30, '1,284', fbig, fill='#FFF8EA')
    wv = text_w('1,284', fbig)
    draw_text(cv, hx + wv + 8, y + 30, 'DPS', cinzel(15, 800), fill='parch_dim', tracking=0.14)
    ax = hx + wv + 60
    am = poly_mask(P(34), P(14), [(0, P(5)), (P(24), P(5)), (P(24), 0), (P(34), P(7)), (P(24), P(14)), (P(24), P(9)), (0, P(9))])
    fill_mask(cv, am, P(ax), P(y + 14), rgba(ICHOR))
    draw_text(cv, ax + 44, y + 30, '1,592', fbig, fill=ICHOR, glow_color='#FFC873', glow_a=0.35)
    w2 = text_w('1,592', fbig)
    delta_chip(cv, ax + 44 + w2 + 14, y + 29, 24, anchor='l', size=20)
    draw_text(cv, x0 + w - 40, y + 18, 'Chain 2  ·  Ricochet 2  ·  Crit 17%', body(16, 'Medium'), fill='parch_dim', anchor='r')
    draw_text(cv, x0 + w - 40, y + 38, '+ Doom: bursts at 8 stacks', body(16, 'Bold'), fill=ICHOR, anchor='r')
    y += 50
    # recipe hint: ONE PART AWAY (dashed ichor border = 'not yet yours')
    pw_ = w - (hx - x0) * 2
    quiet_plate(cv, hx, y, pw_, 64, r=6, alpha=0.85, rim=0)
    dashed_rect(cv, hx, y, pw_, 64, ICHOR)
    place_icon(cv, I.get('seal'), hx + 32, y + 32, 36)
    draw_text(cv, hx + 62, y + 20, 'ONE PART AWAY', cinzel(11, 800), fill=ICHOR, tracking=0.2)
    draw_text(cv, hx + 62, y + 41, 'THE ENDLESS ARGUMENT', cinzel(17, 800), fill='gold_lt', tracking=0.08)
    draw_text(cv, hx + 62, y + 58, '+1 chain, +10% damage · Doomstack is in your bag', body(15, 'Medium'), fill='parch_dim')
    ix = x0 + w - 64
    for i, (ic, have) in enumerate([('doomstack', False), ('ricochet', True), ('stormcore', True)]):
        H.framed_slot(cv, ix - i * 42, y + 32, 34, 'circle', ic, icon_scale=0.62, rim='gold' if have else ICHOR, rim_w=1.4,
                      glow_color='#FFC873' if not have else None)
        if have:
            place_icon(cv, I.get('check'), ix - i * 42 + 12, y + 44, 14)
    y += 64 + 20
    F.ember_knot(cv, x0 + w / 2, y, w - 160, alpha=0.8)
    y += 26
    section_label(cv, hx, y + 6, 'THE BAG', right='6 / 8')
    fx = x0 + w - 40
    for lab, on in [('RELIC', False), ('MECH', False), ('CORE', False), ('ALL', True)]:
        f = cinzel(12, 800)
        tw = text_w(lab, f, 0.12) + 22
        m = rr_mask(P(tw), P(24), P(12))
        X, Y = P(fx - tw), P(y - 10)
        fill_mask(cv, m, X, Y, rgba('#3A2A1C' if on else '#140E0A', 0.95))
        fill_mask(cv, ring_of(m, max(1, P(1))), X, Y, rgba('gold_lt' if on else 'gold_dk'))
        draw_text(cv, fx - tw / 2, y + 7, lab, f, fill='parch' if on else 'parch_dim', anchor='m', tracking=0.12, shadow_a=0)
        fx -= tw + 8
    y += 22
    bag = [('doomstack', 'relic', 'Doomstack', 'epic', 24, True, 'seal'),
           ('volatile_heart', 'relic', 'Volatile Heart', 'godforged', 15, False, None),
           ('stormcore', 'core', 'Stormcore', 'common', 9, False, 'fuse'),
           ('multishot', 'mech', 'Multishot', 'rare', -6, False, None),
           ('embercore', 'core', 'Embercore', 'rare', 2, False, None),
           ('vampire', 'relic', 'Vampire', 'common', -3, False, None)]
    cw, ch, gap = 194, 82, 10
    for i in range(8):
        cx_ = hx + (i % 4) * (cw + gap)
        cy_ = y + (i // 4) * (ch + gap)
        if i >= len(bag):
            m = rr_mask(P(cw), P(ch), P(7))
            fill_mask(cv, m, P(cx_), P(cy_), rgba('#0C0806', 0.6))
            fill_mask(cv, ring_of(m, max(1, P(1))), P(cx_), P(cy_), rgba('gold_sh', 0.9))
            draw_text(cv, cx_ + cw / 2, cy_ + ch / 2 + 6, 'EMPTY', cinzel(12, 800), fill='parch_mute', anchor='m', tracking=0.2, shadow_a=0)
            continue
        icon, kind, name, rar, dps, sel, badge = bag[i]
        card(cv, cx_, cy_, cw, ch, rar, selected=sel)
        H.framed_slot(cv, cx_ + 42, cy_ + ch / 2, 56, kind, icon, icon_scale=0.66, rim_w=1.6,
                      glow_color=rgba(rar) if rar in ('epic', 'godforged') else None)
        draw_text(cv, cx_ + 80, cy_ + 34, name, body(17, 'Bold'), fill='parch')
        draw_text(cv, cx_ + 80, cy_ + 56, RNAME[rar], cinzel(12, 800), fill=rar, tracking=0.12)
        delta_chip(cv, cx_ + cw - 12, cy_ + ch - 10, dps, size=15)
        if badge:
            H.framed_slot(cv, cx_ + cw - 18, cy_ + 18, 24, 'circle', badge, icon_scale=0.7, rim_w=1.1)
    y += 2 * ch + gap + 16
    ph = y0 + h - 64 - y
    pw = w - (hx - x0) * 2
    quiet_plate(cv, hx, y, pw, ph, r=8, alpha=0.9, rim=0.85)
    H.framed_slot(cv, hx + 60, y + ph / 2 - 8, 92, 'relic', 'doomstack', icon_scale=0.66, rim_w=2.2, glow_color='epic')
    F.rarity_gem(cv, hx + 60, y + ph / 2 + 46, 6.5, 'epic')
    tx = hx + 124
    draw_text(cv, tx, y + 40, 'DOOMSTACK', cinzel(26, 800), fill='epic', tracking=0.06, glow_color='#B865FF', glow_a=0.25)
    draw_text(cv, tx, y + 62, 'EPIC RELIC  ·  REPLACES NYCTIAN EYE', cinzel(12, 800), fill='parch_dim', tracking=0.12)
    from boons import rich_wrap
    rich_wrap(cv, tx, y + 90, 380, [('Every hit stacks', 'n'), ('Doom;', 'num'), ('eight', 'num'), ('stacks burst for heavy damage.', 'n'),
                                    ('Completes', 'n'), ('The Endless Argument.', 'kw:#FFE9B0')], size=17, lh=21, anchor='l')
    bx = hx + pw - 232
    bw_ = 214
    button(cv, bx, y + 14, bw_, 46, 'EQUIP', 'primary', chip=lambda xx, yy: delta_chip(cv, xx, yy, 24, size=17, ink=True))
    button(cv, bx, y + 68, bw_, 40, 'FUSE', 'disabled',
           chip=lambda xx, yy: draw_text(cv, xx, yy - 1, 'no twin', body(15, 'Italic'), fill='parch_mute', anchor='r'))
    button(cv, bx, y + 116, bw_, 40, 'SALVAGE', 'secondary',
           chip=lambda xx, yy: (draw_text(cv, xx, yy - 1, '+12', body(16, 'Bold'), fill='parch', anchor='r'),
                                place_icon(cv, I.get('godshard'), xx - 36, yy - 7, 18)))


def forge_drawer(cv):
    x0, y0, w, h = DRAWER
    F.ornate_panel(cv, x0, y0, w, h, corner=76, crest=0, r=10, alpha=0.95)
    F.sun_crest(cv, x0 + w / 2, y0, size=62)
    forge_header(cv, x0, y0, w)
    hx = x0 + 40
    forge_body(cv, x0, y0, w, h, hx)
    fy = y0 + h - 30
    xx = hx
    for key, lab in [('LMB', 'SELECT'), ('Tab', 'CLOSE')]:
        kw = keycap(cv, xx + 14, fy - 5, key, h=20)
        draw_text(cv, xx + kw + 10, fy + 1, lab, cinzel(12, 800), fill='parch_dim', tracking=0.14)
        xx += kw + 22 + text_w(lab, cinzel(12, 800), 0.14) + 16
    draw_text(cv, x0 + w - 40, fy + 1, 'Forge focus: time slows while every player forges', body(15, 'Italic'), fill='parch_mute', anchor='r')
