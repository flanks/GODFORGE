"""Corner clusters of the combat HUD (designer B): Hearth, Arsenal, Party, Wayfinder."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from gf import *
import icons as I
from hud import M, framed_slot, slot_shape
RGEM = gem_at


def corner_pool(cv, corner, rx, ry, a=0.55):
    """A soft pool of shadow anchored in a screen corner, so HUD text reads over lava without a box."""
    w, h = int(P(rx * 2)), int(P(ry * 2))
    g = radial_img(max(2, w // 3), max(2, h // 3), rgba('#050302', a), rgba('#050302', 0), power=1.6).resize((w, h), Image.BILINEAR)
    x = {'bl': -rx, 'br': RW - rx, 'tl': -rx, 'tr': RW - rx}[corner]
    y = {'bl': RH - ry, 'br': RH - ry, 'tl': -ry, 'tr': -ry}[corner]
    cv.put(g, P(x), P(y))


# ───────────────────────── bottom-left: the Hearth ─────────────────────────
def hearth(cv, hp=262, hp_max=380, ghost=300, armor=4, armor_max=6, shield=0, dash=2, dash_max=3, ult=0.72,
           q_cd=None, e_cd=(3.4, 0.42), od=0.64, aim='AUTO', aim_note='−10% dmg', portrait='valdris', player='p1',
           kit=('bulwark_slam', 'siege_stance'), passive='armor_passive', pool=True, alpha=1.0):
    base_y = RH - M
    if pool:
        corner_pool(cv, 'bl', 640, 250, 0.62)
    R = 64
    mcx, mcy = M + R, base_y - R - 6
    hx0 = mcx + R + 18
    hw = 360
    hy = base_y - 128
    # gilt rail: the medallion is the pommel, the HP bar the blade
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

    # medallion: portrait + ultimate charge ring
    d = int(P(R) * 2)
    outer = circle_mask(d)
    X, Y = P(mcx) - d / 2, P(mcy) - d / 2
    shadow(cv, outer, X, Y, blur=P(10), off=(0, P(4)), alpha=0.8)
    if ult >= 1.0:
        glow(cv, outer, X, Y, '#FFB23A', blur=P(14), alpha=0.95, spread=P(3))
    fill_mask(cv, outer, X, Y, gold_fill(d, d))
    fill_mask(cv, ring_of(outer, max(1, P(0.9))), X, Y, rgba('gold_sh'))
    trough = circle_mask(int(P(R - 4.5) * 2))
    tX, tY = P(mcx) - trough.width / 2, P(mcy) - trough.height / 2
    fill_mask(cv, trough, tX, tY, rgba('#140C08'))
    cm = ImageChops.multiply(conic_mask(trough.width, min(ult, 1.0)), trough)
    fill_mask(cv, cm, tX, tY, radial_img(trough.width, trough.height, rgba('#FFF0B8'), rgba('#FF9A2E'), power=0.7))
    tk = Image.new('L', trough.size, 0)
    tdd = ImageDraw.Draw(tk)
    c0 = trough.width / 2
    for i in range(10):
        a = math.radians(-90 + i * 36)
        tdd.line([(c0 + c0 * 0.84 * math.cos(a), c0 + c0 * 0.84 * math.sin(a)), (c0 + c0 * math.cos(a), c0 + c0 * math.sin(a))],
                 fill=255, width=max(1, int(P(1.3))))
    fill_mask(cv, ImageChops.multiply(tk, trough), tX, tY, rgba('#140C08', 0.85))
    inner = circle_mask(int(P(R - 12) * 2))
    iX, iY = P(mcx) - inner.width / 2, P(mcy) - inner.height / 2
    fill_mask(cv, grow(inner, P(1.8)), iX, iY, gold_fill(inner.width, inner.height, GOLD_SOFT))
    fill_mask(cv, inner, iX, iY, radial_img(inner.width, inner.height, '#5A3E27', '#120B08', cy=0.38, power=1.1))
    band = ring_of(shrink(inner, P(2.4)), max(1, P(2.4)))
    fill_mask(cv, band, iX, iY, rgba(player, 0.95))
    place_icon(cv, I.get(portrait), mcx, mcy - 1, (R - 12) * 1.5)
    keycap(cv, mcx, base_y - 5, 'R', h=21)
    framed_slot(cv, mcx + R * 0.76, mcy - R * 0.76, 34, 'circle', passive, icon_scale=0.66, rim_w=1.3)

    # HP bar + numerals (a leaf finial caps the blade)
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
    f_num = cinzel(18, 800)
    f_max = cinzel(14, 700)
    tw = text_w(f' / {hp_max}', f_max)
    draw_text(cv, hx0 + hw - 8, hy + 17, f' / {hp_max}', f_max, fill='parch_dim', anchor='r', shadow_a=0.95)
    draw_text(cv, hx0 + hw - 8 - tw, hy + 17.5, f'{hp}', f_num, fill='#FFF8EA', anchor='r', shadow_a=0.95, stroke=0.8)
    # armour plates (left) + dash pips (right), sitting on the rail
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
            rim = ring_of(circle_mask(d2), max(1, P(1.4)))
            fill_mask(cv, ImageChops.multiply(rim, conic_mask(d2, 0.6)), P(px_) - d2 / 2, P(ay + 4.5) - d2 / 2, rgba('gold_lt', 0.9))

    # ability row
    ry = base_y - 38
    q_x = hx0 + 30
    e_x = q_x + 72
    v_x = e_x + 80
    for (x, key, icon, cd) in ((q_x, 'Q', kit[0], q_cd), (e_x, 'E', kit[1], e_cd)):
        if cd:
            framed_slot(cv, x, ry, 60, 'ability', icon, icon_scale=0.74, state='cooldown', frac_cd=cd[1],
                        cd_text=f'{cd[0]:.1f}'.rstrip('0').rstrip('.'))
        else:
            framed_slot(cv, x, ry, 60, 'ability', icon, icon_scale=0.74, glow_color='#FFC24A')
        keycap(cv, x, ry + 31, key, h=20)
    # overdrive (team meter): a hexagon filling with molten gold
    s = 68
    m = slot_shape('hex', P(s))
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
    fill_mask(cv, fl, X, Y, grad_img(m.width, m.height, [(0, '#FFE9A0'), (0.5, '#F5A93A'), (1, '#A8521A')]))
    surf = Image.new('L', m.size, 0)
    ImageDraw.Draw(surf).line(pts[1:-1], fill=255, width=max(1, int(P(1.4))))
    fill_mask(cv, ImageChops.multiply(surf, shrink(m, P(2))), X, Y, rgba('#FFF6D0', 0.9))
    # the emblem is stamped into the metal: dark while charging, lit when ready
    if od >= 1:
        place_icon(cv, I.get('overdrive'), v_x, ry - 2, 40)
    else:
        place_icon(cv, I.get('overdrive'), v_x, ry - 1, 40, tint='#3A2210', alpha=0.9)
        place_icon(cv, I.get('overdrive'), v_x, ry - 2, 38, tint='#2A1608', alpha=0.95)
    fill_mask(cv, ring_of(m, max(1, P(2))), X, Y, gold_fill(m.width, m.height))
    keycap(cv, v_x, ry + 31, 'V', h=20)
    # aim chip
    ax = v_x + 46
    place_icon(cv, I.get('aim_auto'), ax + 13, ry - 8, 26)
    draw_text(cv, ax + 32, ry - 3, aim, cinzel(14, 800), fill='parch', tracking=0.1)
    draw_text(cv, ax + 32, ry + 15, aim_note, body(15, 'Medium'), fill='parch_dim')
    return (M, hy - 12, hx0 + hw, base_y)


# ───────────────────────── bottom-right: the Arsenal ─────────────────────────
def arsenal(cv, parts=(('core', 'stormcore', 'rare'), ('mech', 'ricochet', 'epic'), ('relic', 'nyctian_eye', 'rare'),
                       ('sigil', 'sigil_anvilheart', 'godforged')), chassis='colossus_cannon', element='el_storm',
            element_color='storm', shards=46, ember=69, pool=True):
    base_y = RH - M
    if pool:
        corner_pool(cv, 'br', 520, 210, 0.6)
    cx = RW - M - 50
    cy = base_y - 50
    s = 100
    m = slot_shape('hexflat', P(s))
    X, Y = P(cx) - m.width / 2, P(cy) - m.height / 2
    shadow(cv, m, X, Y, blur=P(10), off=(0, P(4)), alpha=0.85)
    glow(cv, m, X, Y, element_color, blur=P(10), alpha=0.4)
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#36271B'), (1, '#110B08')]))
    fill_mask(cv, shrink(m, P(3)), X, Y, radial_img(m.width, m.height, rgba(element_color, 0.3), rgba('#000000', 0), power=1.2))
    place_icon(cv, I.get(chassis), cx, cy, 66)
    fill_mask(cv, ring_of(m, max(1, P(2.4))), X, Y, gold_fill(m.width, m.height))
    fill_mask(cv, ring_of(shrink(m, P(4.5)), max(1, P(0.9))), X, Y, rgba('gold_dk', 0.85))
    framed_slot(cv, cx - 38, cy + 34, 30, 'circle', element, icon_scale=0.72, rim_w=1.3)
    xs = [cx - 88 - i * 60 for i in range(4)][::-1]
    for (kind, icon, rar), x in zip(parts, xs):
        y = cy + 8
        framed_slot(cv, x, y, 52, kind, icon, icon_scale=0.64, rim_w=1.5)
        RGEM(cv, x, y + 32, 5.4, rar, glow_a=0.6)
    place_icon(cv, I.get('lock'), xs[3] + 20, cy - 13, 16)
    wy = cy - 58
    xr = RW - M
    f = cinzel(20, 800)
    t1 = f'{ember}'
    w1 = text_w(t1, f)
    draw_text(cv, xr, wy, t1, f, fill='parch', anchor='r')
    place_icon(cv, I.get('ember'), xr - w1 - 16, wy - 7, 26)
    t2 = f'{shards}'
    x2 = xr - w1 - 46
    w2 = text_w(t2, f)
    draw_text(cv, x2, wy, t2, f, fill='parch', anchor='r')
    place_icon(cv, I.get('godshard'), x2 - w2 - 14, wy - 8, 28)
    return (xs[0] - 30, wy - 24, RW - M, base_y)


# ───────────────────────── top-left: party ─────────────────────────
def party(cv, allies, pool=True):
    """allies: [(slot colour, name, portrait, hp_frac, state, extra)]"""
    if pool:
        corner_pool(cv, 'tl', 420, 250, 0.55)
    y = M
    for (pc, name, portrait, hp, state, extra) in allies:
        cx, cy = M + 23, y + 23
        d = int(P(46))
        cm = circle_mask(d)
        X, Y = P(cx) - d / 2, P(cy) - d / 2
        shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.85)
        if state == 'downed':
            glow(cv, cm, X, Y, 'danger', blur=P(8), alpha=0.95, spread=P(1.5))
        fill_mask(cv, cm, X, Y, gold_fill(d, d, GOLD_SOFT))
        inner = shrink(cm, P(2.2))
        fill_mask(cv, inner, X, Y, radial_img(d, d, '#4A3322', '#100A07', cy=0.4))
        fill_mask(cv, ring_of(inner, max(1, P(2.6))), X, Y, rgba(pc) if state != 'downed' else rgba('danger'))
        place_icon(cv, I.get(portrait if state != 'downed' else 'skull'), cx, cy, 30)
        tx = cx + 33
        fn = body(18, 'Bold')
        draw_text(cv, tx, cy - 4, name, fn, fill='parch')
        nw = text_w(name, fn)
        if state == 'downed':
            draw_text(cv, tx + nw + 10, cy - 5, 'DOWNED', cinzel(14, 800), fill='danger', tracking=0.1)
            bar(cv, tx, cy + 5, 170, 8, extra, [(0, '#FFFFFF'), (1, '#FFB0A8')], r=3, rim=0.5, sheen=False)
            draw_text(cv, tx + 178, cy + 13, f'{int(extra * 20)}s', cinzel(14, 800), fill='parch')
        else:
            bar(cv, tx, cy + 5, 170, 8, hp, [(0, 'hp_lt'), (1, 'hp_dk')], r=3, rim=0.6, sheen=False)
            if extra == 'ult':
                place_icon(cv, I.get('overdrive'), tx + nw + 14, cy - 10, 16)
        y += 54
    return (0, 0, 330, y)


# ───────────────────────── top-right: the Wayfinder ─────────────────────────
def chevron(cv, x, y, bearing, size=16, color='gold_lt'):
    chev = Image.new('L', (int(P(size)), int(P(size))), 0)
    c = chev.width / 2
    a = math.radians(bearing - 90)
    pts = [(c + c * 0.95 * math.cos(a), c + c * 0.95 * math.sin(a)),
           (c + c * 0.72 * math.cos(a + 2.5), c + c * 0.72 * math.sin(a + 2.5)),
           (c + c * 0.2 * math.cos(a + math.pi), c + c * 0.2 * math.sin(a + math.pi)),
           (c + c * 0.72 * math.cos(a - 2.5), c + c * 0.72 * math.sin(a - 2.5))]
    ImageDraw.Draw(chev).polygon(pts, fill=255)
    shadow(cv, chev, P(x) - c, P(y) - c, blur=P(1.5), off=(0, P(1)), alpha=0.9)
    fill_mask(cv, chev, P(x) - c, P(y) - c, rgba(color))


def wayfinder(cv, map_img=None, seals=3, req=7, timer='07:32', threat=2, warlord=False, gate='sealed',
              objectives=(('poi_anvil', 'Anvil', 38, 46), ('poi_shrine', 'Shrine of Zephyros', 250, 102)), biome='CINDER WASTES',
              minimap=True, pool=True):
    xr = RW - M
    if pool:
        corner_pool(cv, 'tr', 470, 460, 0.58)
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
        for (cx_, cy_, fx, fy) in [(x0, y, 1, 1), (xr, y, -1, 1), (x0, y + h, 1, -1), (xr, y + h, -1, -1)]:
            corner_flourish(cv, cx_, cy_, fx, fy, size=14)
        gem_at(cv, x0 + w / 2, y + 1, 6, '#FFE7A6', glow_a=0.45)
        y += h + 16
    f_lab = cinzel(14, 800)
    ft = cinzel(24, 800)
    draw_text(cv, xr, y + 20, timer, ft, fill='#FFF8EA', anchor='r')
    tw = text_w(timer, ft)
    place_icon(cv, I.get('hourglass'), xr - tw - 14, y + 11, 18, alpha=0.85)
    draw_text(cv, xr - tw - 30, y + 18, biome, f_lab, fill='parch_dim', anchor='r', tracking=0.16)
    y += 36
    sx = xr
    txt = f'{seals}/{req}'
    fs = cinzel(19, 800)
    draw_text(cv, sx, y + 14, txt, fs, fill='gold_lt', anchor='r')
    sx -= text_w(txt, fs) + 18
    for i in range(req)[::-1]:
        if i < seals:
            place_icon(cv, I.get('seal'), sx, y + 7, 26)
        else:
            d = int(P(17))
            cm = circle_mask(d)
            fill_mask(cv, cm, P(sx) - d / 2, P(y + 7) - d / 2, rgba('#0E0907', 0.92))
            fill_mask(cv, ring_of(cm, max(1, P(1.3))), P(sx) - d / 2, P(y + 7) - d / 2, rgba('gold_dk'))
        sx -= 24
    y += 34
    gx = xr
    gate_word = {'sealed': 'SEALED', 'open': 'GATE OPEN', 'gathering': 'GATHER 6'}[gate]
    draw_text(cv, gx, y + 13, gate_word, f_lab, fill='parch_dim' if gate == 'sealed' else 'gold_lt', anchor='r', tracking=0.1)
    gx -= text_w(gate_word, f_lab, 0.1) + 16
    place_icon(cv, I.get('poi_gate'), gx, y + 7, 22, desat=0.7 if gate == 'sealed' else 0, dark=0.25 if gate == 'sealed' else 0)
    gx -= 30
    ww = 'SLAIN' if warlord else 'WARLORD'
    draw_text(cv, gx, y + 13, ww, f_lab, fill='parch_dim', anchor='r', tracking=0.1)
    gx -= text_w(ww, f_lab, 0.1) + 16
    place_icon(cv, I.get('poi_warlord'), gx, y + 7, 22)
    y += 32
    tx = xr
    for i in range(5)[::-1]:
        lit = i < threat
        pw, ph = 15, 11
        m = poly_mask(P(pw), P(ph), [(0, 0), (P(pw) - P(5), 0), (P(pw) - 1, P(ph) / 2), (P(pw) - P(5), P(ph) - 1), (0, P(ph) - 1), (P(5), P(ph) / 2)])
        X_, Y_ = P(tx - pw), P(y + 2)
        if lit:
            col = mix('#FFB347', '#FF3B30', i / 4)
            glow(cv, m, X_, Y_, col, blur=P(3), alpha=0.7)
            fill_mask(cv, m, X_, Y_, col)
        else:
            fill_mask(cv, m, X_, Y_, rgba('#231914', 0.95))
            fill_mask(cv, ring_of(m, 1), X_, Y_, rgba('#5A4232'))
        tx -= pw + 1
    draw_text(cv, tx - 8, y + 12, 'THREAT', f_lab, fill='parch_dim', anchor='r', tracking=0.12)
    y += 34
    for icon, name, bearing, dist in objectives:
        dt = f'{dist} m'
        fd = cinzel(15, 800)
        draw_text(cv, xr, y + 13, dt, fd, fill='parch', anchor='r')
        bx = xr - text_w(dt, fd) - 13
        chevron(cv, bx, y + 8, bearing)
        fb = body(17, 'Medium')
        draw_text(cv, bx - 14, y + 13, name, fb, fill='parch_dim', anchor='r')
        nx = bx - 14 - text_w(name, fb) - 15
        place_icon(cv, I.get(icon), nx, y + 7, 22)
        y += 28
    return y
