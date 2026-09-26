"""Forge panel body below the header (weapon row, DPS, combo, bag, detail pane)."""
from gf import *
import icons as I
from hud import framed_slot
from panels import card, section_label, delta_chip, button, RNAME


def forge_body(cv, x0, y0, w, h, hx):
    y = y0 + 146
    section_label(cv, hx, y, 'THE WEAPON')
    y += 14
    RH_ = 180
    card(cv, hx, y, 196, RH_, 'common', r=8)
    cc = x0 + 36 + 98
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
            glow(cv, ring_of(tm, max(1, P(1.6))), P(sx - 4), P(y - 4), '#FFC24A', blur=P(6), alpha=0.7)
            fill_mask(cv, ring_of(tm, max(1, P(1.6))), P(sx - 4), P(y - 4), rgba('gold_lt', 0.95))
            tg = rr_mask(P(84), P(20), P(10))
            fill_mask(cv, tg, P(sx + cw / 2 - 42), P(y - 14), grad_img(tg.width, tg.height, [(0, '#FFE7A0'), (1, '#C98A34')]))
            draw_text(cv, sx + cw / 2, y + 1, 'REPLACE', cinzel(11, 800), fill='ink_text', anchor='m', tracking=0.14, shadow_a=0)
        else:
            draw_text(cv, sx + cw / 2, y + 22, lab, cinzel(12, 800), fill='parch_dim', anchor='m', tracking=0.16)
        framed_slot(cv, sx + cw / 2, y + 70, 74, kind, icon, icon_scale=0.64, rim_w=2.0,
                    glow_color=rgba(rar) if rar in ('epic', 'godforged') else None)
        gem_at(cv, sx + cw / 2, y + 110, 6, rar, glow_a=0.6)
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
            draw_text(cv, sx + cw / 2 + 48, y + 164, '6', cinzel(13, 800), fill='parch', anchor='r')
            place_icon(cv, I.get('godshard'), sx + cw / 2 + 32, y + 159, 13)
        sx += cw + 12
    y += RH_ + 22
    fbig = cinzel(38, 800)
    draw_text(cv, hx, y + 30, '1,284', fbig, fill='#FFF8EA')
    wv = text_w('1,284', fbig)
    draw_text(cv, hx + wv + 8, y + 30, 'DPS', cinzel(15, 800), fill='parch_dim', tracking=0.14)
    ax = hx + wv + 60
    am = poly_mask(P(34), P(14), [(0, P(5)), (P(24), P(5)), (P(24), 0), (P(34), P(7)), (P(24), P(14)), (P(24), P(9)), (0, P(9))])
    fill_mask(cv, am, P(ax), P(y + 14), rgba('gold_lt'))
    draw_text(cv, ax + 44, y + 30, '1,592', fbig, fill='up', glow_color='#FFB23A', glow_a=0.35)
    w2 = text_w('1,592', fbig)
    delta_chip(cv, ax + 44 + w2 + 14, y + 29, 24, anchor='l', size=20)
    draw_text(cv, x0 + w - 36, y + 18, 'Chain 2  ·  Ricochet 2  ·  Crit 17%', body(16, 'Medium'), fill='parch_dim', anchor='r')
    draw_text(cv, x0 + w - 36, y + 38, '+ Doom, bursts at 8 stacks', body(16, 'Bold'), fill='up', anchor='r')
    y += 52
    quiet_plate(cv, hx, y, w - 72, 56, r=6, alpha=0.85, rim=0.8)
    place_icon(cv, I.get('seal'), hx + 30, y + 28, 34)
    draw_text(cv, hx + 58, y + 25, 'THE ENDLESS ARGUMENT', cinzel(17, 800), fill='gold_lt', tracking=0.08)
    draw_text(cv, hx + 58, y + 45, 'Named combo · equip Doomstack to complete it: +1 chain, +10% damage', body(16, 'Medium'), fill='parch_dim')
    ix = x0 + w - 60
    for i, (ic, have) in enumerate([('doomstack', False), ('ricochet', True), ('stormcore', True)]):
        framed_slot(cv, ix - i * 40, y + 28, 32, 'circle', ic, icon_scale=0.62, rim='gold' if have else '#FFC24A', rim_w=1.4,
                    glow_color='#FFC24A' if not have else None)
        if have:
            place_icon(cv, I.get('check'), ix - i * 40 + 12, y + 40, 14)
    y += 56 + 20
    filigree_rule(cv, x0 + w / 2, y, w / 2 - 40, 0.8)
    y += 26
    section_label(cv, hx, y + 6, 'THE BAG', right='6 / 8')
    fx = x0 + w - 36
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
    bag = [('doomstack', 'relic', 'Doomstack', 'epic', 'RELIC', 24, True, None),
           ('volatile_heart', 'relic', 'Volatile Heart', 'godforged', 'RELIC', 15, False, None),
           ('stormcore', 'core', 'Stormcore', 'common', 'CORE', 9, False, 'fuse'),
           ('multishot', 'mech', 'Multishot', 'rare', 'MECH', -6, False, None),
           ('embercore', 'core', 'Embercore', 'rare', 'CORE', 2, False, None),
           ('vampire', 'relic', 'Vampire', 'common', 'RELIC', -3, False, None)]
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
        icon, kind, name, rar, slotname, dps, sel, badge = bag[i]
        card(cv, cx_, cy_, cw, ch, rar, selected=sel)
        framed_slot(cv, cx_ + 42, cy_ + ch / 2, 56, kind, icon, icon_scale=0.66, rim_w=1.6,
                    glow_color=rgba(rar) if rar in ('epic', 'godforged') else None)
        draw_text(cv, cx_ + 80, cy_ + 34, name, body(17, 'Bold'), fill='parch')
        draw_text(cv, cx_ + 80, cy_ + 56, RNAME[rar], cinzel(12, 800), fill=rar, tracking=0.12)
        delta_chip(cv, cx_ + cw - 12, cy_ + ch - 10, dps, size=15)
        if badge:
            framed_slot(cv, cx_ + cw - 18, cy_ + 18, 24, 'circle', badge, icon_scale=0.7, rim_w=1.1)
    y += 2 * ch + gap + 16
    # detail pane for the selected part: text left, actions stacked right
    ph = y0 + h - 60 - y
    pw = w - 72
    quiet_plate(cv, hx, y, pw, ph, r=8, alpha=0.9, rim=0.85)
    framed_slot(cv, hx + 60, y + ph / 2 - 8, 92, 'relic', 'doomstack', icon_scale=0.66, rim_w=2.2, glow_color='epic')
    gem_at(cv, hx + 60, y + ph / 2 + 46, 6.5, 'epic')
    tx = hx + 124
    draw_text(cv, tx, y + 40, 'DOOMSTACK', cinzel(26, 800), fill='epic', tracking=0.06, glow_color='#B865FF', glow_a=0.25)
    draw_text(cv, tx, y + 62, 'EPIC RELIC  ·  REPLACES NYCTIAN EYE', cinzel(12, 800), fill='parch_dim', tracking=0.12)
    lines = wrap('Every hit stacks doom; eight stacks burst for heavy damage. Completes The Endless Argument.', body(17, 'Medium'), 390)
    for i, ln in enumerate(lines[:3]):
        draw_text(cv, tx, y + 88 + i * 21, ln, body(17, 'Medium'), fill='parch')
    bx = hx + pw - 232
    bw_ = 214
    button(cv, bx, y + 14, bw_, 46, 'EQUIP', 'primary', key='F', chip=lambda xx, yy: delta_chip(cv, xx, yy, 24, size=17, ink=True))
    button(cv, bx, y + 68, bw_, 40, 'FUSE', 'disabled', key='G',
           chip=lambda xx, yy: draw_text(cv, xx, yy - 1, 'no twin', body(15, 'Italic'), fill='parch_mute', anchor='r'))
    button(cv, bx, y + 116, bw_, 40, 'SALVAGE', 'secondary', key='X',
           chip=lambda xx, yy: (draw_text(cv, xx, yy - 1, '+12', cinzel(15, 800), fill='parch', anchor='r'),
                                place_icon(cv, I.get('godshard'), xx - 40, yy - 7, 18)))
