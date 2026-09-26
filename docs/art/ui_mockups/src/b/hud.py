"""Combat HUD components (designer B). All coordinates in 1080p reference px."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from gf import *
import icons as I

M = 24  # safe margin


# ───────────────────────── shared small parts ─────────────────────────
def ink_smear(cv, x, y, w, h, side='left', a=0.62):
    """Soft ink backing that fades away from the screen edge (legibility without a box)."""
    X, Y = P(x), P(y)
    g = grad_img(int(P(w)), int(P(h)), [(0, rgba('#070504', a)), (0.55, rgba('#070504', a * 0.7)), (1, rgba('#070504', 0))],
                 horizontal=True)
    if side == 'right':
        g = g.transpose(Image.FLIP_LEFT_RIGHT)
    v = grad_img(g.width, g.height, [(0, (255, 255, 255, 0)), (0.2, (255, 255, 255, 255)), (0.8, (255, 255, 255, 255)), (1, (255, 255, 255, 0))])
    g = mask_mul(g, v.split()[3])
    cv.put(g, X, Y)


def slot_shape(kind, s):
    """Mask of a slot frame shape, s = size in canvas px."""
    s = int(s)
    n = s * 2
    m = Image.new('L', (n, n), 0)
    d = ImageDraw.Draw(m)
    if kind == 'core':
        d.ellipse([0, 0, n - 1, n - 1], fill=255)
    elif kind == 'mech':
        c = n * 0.29
        d.polygon(chamfer_poly(n - 1, n - 1, c), fill=255)
    elif kind == 'relic':
        d.rectangle([0, n * 0.42, n - 1, n - 1], fill=255)
        d.ellipse([0, 0, n - 1, n * 0.84], fill=255)
    elif kind == 'sigil':
        d.polygon([(n / 2, 0), (n - 1, n / 2), (n / 2, n - 1), (0, n / 2)], fill=255)
    elif kind == 'ability':
        d.polygon(chamfer_poly(n - 1, n - 1, n * 0.2), fill=255)
    elif kind == 'hex':
        pts = [(n / 2 + n / 2 * math.cos(math.radians(a)), n / 2 + n / 2 * math.sin(math.radians(a))) for a in range(-90, 270, 60)]
        d.polygon(pts, fill=255)
    elif kind == 'hexflat':
        pts = [(n / 2 + n / 2 * math.cos(math.radians(a)), n / 2 + n / 2 * 0.92 * math.sin(math.radians(a))) for a in range(0, 360, 60)]
        d.polygon(pts, fill=255)
    elif kind == 'circle':
        d.ellipse([0, 0, n - 1, n - 1], fill=255)
    return m.resize((s, s), Image.LANCZOS)


def framed_slot(cv, cx, cy, size, kind, icon=None, icon_scale=0.66, rim='gold', rim_w=1.6, fill_a=0.9, state='ready',
                frac_cd=0.0, cd_text=None, glow_color=None, icon_alpha=1.0, inner_line=True, sheen=True):
    s = P(size)
    m = slot_shape(kind, s)
    X, Y = P(cx) - m.width / 2, P(cy) - m.height / 2
    shadow(cv, m, X, Y, blur=P(5), off=(0, P(2.5)), alpha=0.75)
    if glow_color:
        glow(cv, m, X, Y, glow_color, blur=P(7), alpha=0.75, spread=P(1))
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, rgba('#35261A', fill_a)), (1, rgba('#110B08', fill_a))]))
    # soft inner radial so icons sit in a pool of light
    fill_mask(cv, shrink(m, P(2)), X, Y, radial_img(m.width, m.height, rgba('#6A4A2A', 0.35 if state == 'ready' else 0.1), rgba('#000000', 0), power=1.4))
    if icon is not None:
        if state == 'cooldown':
            place_icon(cv, I.get(icon), cx, cy, size * icon_scale, desat=0.75, dark=0.45, alpha=icon_alpha)
        elif state == 'disabled':
            place_icon(cv, I.get(icon), cx, cy, size * icon_scale, desat=1.0, dark=0.3, alpha=0.5 * icon_alpha)
        else:
            place_icon(cv, I.get(icon), cx, cy, size * icon_scale, alpha=icon_alpha)
    if frac_cd > 0:
        cm = conic_mask(m.width, frac_cd)
        fill_mask(cv, ImageChops.multiply(cm, shrink(m, P(1.5))), X, Y, rgba('#050302', 0.55))
        # sweep edge line
        a = math.radians(-90 + 360 * frac_cd)
        e = Image.new('L', m.size, 0)
        ImageDraw.Draw(e).line([(m.width / 2, m.height / 2), (m.width / 2 + m.width * math.cos(a), m.height / 2 + m.width * math.sin(a))],
                               fill=255, width=max(1, int(P(1.4))))
        fill_mask(cv, ImageChops.multiply(e, shrink(m, P(1.5))), X, Y, rgba('gold_lt', 0.8))
    if rim:
        ring = ring_of(m, max(1, P(rim_w)))
        if rim == 'gold':
            fill_mask(cv, ring, X, Y, gold_fill(m.width, m.height))
        else:
            fill_mask(cv, ring, X, Y, rgba(rim))
        if inner_line:
            ir = ring_of(shrink(m, P(rim_w + 1.6)), max(1, P(0.7)))
            fill_mask(cv, ir, X, Y, rgba('gold_dk', 0.8))
    if sheen and state == 'ready':
        sh = grad_img(m.width, m.height, [(0, rgba('#FFFFFF', 0.16)), (0.45, rgba('#FFFFFF', 0.0)), (1, rgba('#FFFFFF', 0))])
        fill_mask(cv, shrink(m, P(2)), X, Y, sh)
    if cd_text:
        draw_text(cv, cx, cy + size * 0.16, cd_text, cinzel(size * 0.36, 800), fill='parch', anchor='m', stroke=1.2, shadow_a=0.9)
    return m


# ───────────────────────── bottom-left: the Hearth (my vitals + kit) ─────────────────────────
def hearth(cv, hp=262, hp_max=380, ghost=300, armor=4, armor_max=6, shield=0, dash=2, dash_max=3, ult=0.72,
           q_cd=None, e_cd=(3.4, 0.42), od=0.64, aim='AUTO', aim_note='−10%', portrait='valdris', player='p1',
           kit=('bulwark_slam', 'siege_stance'), low=False):
    base_y = RH - M
    # medallion (portrait + ultimate charge ring)
    mcx, mcy, R = M + 58, base_y - 60, 58
    Rp = P(R)
    d = int(Rp * 2)
    outer = circle_mask(d)
    X, Y = P(mcx) - d / 2, P(mcy) - d / 2
    shadow(cv, outer, X, Y, blur=P(10), off=(0, P(4)), alpha=0.75)
    if ult >= 1.0:
        glow(cv, outer, X, Y, '#FFB23A', blur=P(12), alpha=0.9, spread=P(2))
    fill_mask(cv, outer, X, Y, gold_fill(d, d))                                        # gilt outer rim
    fill_mask(cv, ring_of(outer, max(1, P(0.8))), X, Y, rgba('gold_sh'))
    trough = circle_mask(int(P(R - 4) * 2))
    tX, tY = P(mcx) - trough.width / 2, P(mcy) - trough.height / 2
    fill_mask(cv, trough, tX, tY, rgba('#140C08'))
    cm = ImageChops.multiply(conic_mask(trough.width, ult), trough)
    ultfill = radial_img(trough.width, trough.height, rgba('#FFE08A'), rgba('#FF9A2E'), power=0.8)
    fill_mask(cv, cm, tX, tY, ultfill)
    # tick marks every 10 %
    tk = Image.new('L', trough.size, 0)
    tdd = ImageDraw.Draw(tk)
    c0 = trough.width / 2
    for i in range(10):
        a = math.radians(-90 + i * 36)
        tdd.line([(c0 + c0 * 0.86 * math.cos(a), c0 + c0 * 0.86 * math.sin(a)), (c0 + c0 * math.cos(a), c0 + c0 * math.sin(a))],
                 fill=255, width=max(1, int(P(1.2))))
    fill_mask(cv, ImageChops.multiply(tk, trough), tX, tY, rgba('#140C08', 0.8))
    # inner portrait disc
    inner = circle_mask(int(P(R - 11) * 2))
    iX, iY = P(mcx) - inner.width / 2, P(mcy) - inner.height / 2
    fill_mask(cv, grow(inner, P(1.6)), iX, iY, gold_fill(inner.width, inner.height, GOLD_SOFT))
    fill_mask(cv, inner, iX, iY, radial_img(inner.width, inner.height, '#4A3322', '#120B08', cy=0.4, power=1.1))
    # player colour band
    band = ring_of(shrink(inner, P(2)), max(1, P(2.2)))
    fill_mask(cv, band, iX, iY, rgba(player, 0.9))
    place_icon(cv, I.get(portrait), mcx, mcy - 2, (R - 11) * 1.45)
    # ult pip + key
    keycap(cv, mcx, base_y - 3, 'R', h=20)
    if ult >= 1.0:
        pass
    # passive badge (upper right of medallion)
    bx, by = mcx + R * 0.74, mcy - R * 0.74
    framed_slot(cv, bx, by, 30, 'circle', 'armor_passive', icon_scale=0.62, rim_w=1.2)

    # HP row
    hx0 = mcx + R + 14
    hw = 336
    hy = base_y - 112
    frac = hp / hp_max
    bar(cv, hx0, hy, hw, 20, frac, [(0, 'hp_lt'), (0.5, 'hp'), (1, 'hp_dk')], ghost=ghost / hp_max, r=4, rim=0.85)
    if shield:
        sf = min(1.0, (hp + shield) / hp_max)
        hatch = Image.new('L', (int(P(hw)), int(P(20))), 0)
        hd = ImageDraw.Draw(hatch)
        for xx in range(-int(P(20)), hatch.width, int(P(5))):
            hd.line([(xx, hatch.height), (xx + hatch.height, 0)], fill=255, width=max(1, int(P(1.6))))
        clip = Image.new('L', hatch.size, 0)
        ImageDraw.Draw(clip).rectangle([P(hw) * frac, P(2), P(hw) * sf, P(18)], fill=255)
        fill_mask(cv, ImageChops.multiply(hatch, clip), P(hx0), P(hy), rgba('ward', 0.9))
    # numerals inside the bar
    f_num = cinzel(15, 800)
    tw = text_w(f' / {hp_max}', cinzel(12, 700))
    draw_text(cv, hx0 + hw - 8, hy + 15.5, f' / {hp_max}', cinzel(12, 700), fill='parch_dim', anchor='r', shadow_a=0.9)
    draw_text(cv, hx0 + hw - 8 - tw, hy + 15.5, f'{hp}', f_num, fill='parch', anchor='r', shadow_a=0.95)
    # armour plates + dash pips
    ay = hy + 26
    aw = 238
    seg_w = (aw - (armor_max - 1) * 3) / armor_max
    for i in range(armor_max):
        sx = hx0 + i * (seg_w + 3)
        m = poly_mask(P(seg_w), P(8), [(P(3), 0), (P(seg_w), 0), (P(seg_w) - P(3), P(8) - 1), (0, P(8) - 1)])
        shadow(cv, m, P(sx), P(ay), blur=P(2), off=(0, P(1)), alpha=0.7)
        if i < armor:
            fill_mask(cv, m, P(sx), P(ay), grad_img(m.width, m.height, [(0, '#E9EEF2'), (0.5, 'steel'), (1, 'steel_dk')]))
        else:
            fill_mask(cv, m, P(sx), P(ay), rgba('#1A1512', 0.85))
            fill_mask(cv, ring_of(m, 1), P(sx), P(ay), rgba('steel_dk', 0.8))
    for i in range(dash_max):
        px_ = hx0 + hw - 8 - (dash_max - 1 - i) * 24
        full = i < dash
        gem_at(cv, px_, ay + 4, 6.2, '#FFE7A6' if full else '#2A1F18', facet=full, glow_a=0.45 if full else 0)
        if not full:
            # refill sweep for the next pip
            pass

    # ability row
    ry = base_y - 30
    q_x = hx0 + 28
    e_x = q_x + 66
    v_x = e_x + 72
    for (x, key, icon, cd) in ((q_x, 'Q', kit[0], q_cd), (e_x, 'E', kit[1], e_cd)):
        if cd:
            framed_slot(cv, x, ry - 4, 54, 'ability', icon, state='cooldown', frac_cd=cd[1], cd_text=f'{cd[0]:.1f}'.rstrip('0').rstrip('.'))
        else:
            framed_slot(cv, x, ry - 4, 54, 'ability', icon, glow_color='#FFC24A')
        keycap(cv, x, ry + 25, key, h=18)
    # overdrive (team) : molten fill hexagon
    s = 60
    m = slot_shape('hex', P(s))
    X, Y = P(v_x) - m.width / 2, P(ry - 6) - m.height / 2
    shadow(cv, m, X, Y, blur=P(6), off=(0, P(3)), alpha=0.8)
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#2B1F16'), (1, '#0E0907')]))
    fl = Image.new('L', m.size, 0)
    lvl = m.height * (1 - od)
    pts = [(0, m.height)] + [(xx, lvl + math.sin(xx / m.width * math.pi * 3) * P(2.2)) for xx in range(0, m.width + 1, 4)] + [(m.width, m.height)]
    ImageDraw.Draw(fl).polygon(pts, fill=255)
    fl = ImageChops.multiply(fl, shrink(m, P(2)))
    fill_mask(cv, fl, X, Y, grad_img(m.width, m.height, [(0, '#FFE9A0'), (0.5, '#F5A93A'), (1, '#A8521A')]))
    place_icon(cv, I.get('overdrive'), v_x, ry - 6, 34, alpha=0.95 if od >= 1 else 0.8, desat=0 if od >= 1 else 0.2)
    fill_mask(cv, ring_of(m, max(1, P(1.8))), X, Y, gold_fill(m.width, m.height))
    keycap(cv, v_x, ry + 25, 'V', h=18)
    draw_text(cv, v_x + 36, ry - 22, f'{int(od * 100)}%', cinzel(12, 800), fill='gold_lt', anchor='l', shadow_a=0.9)
    # aim chip
    ax = v_x + 38
    place_icon(cv, I.get('aim_auto'), ax + 12, ry + 8, 24)
    draw_text(cv, ax + 28, ry + 7, aim, cinzel(12, 800), fill='parch', tracking=0.08)
    draw_text(cv, ax + 28, ry + 21, aim_note, body(13, 'Medium'), fill='parch_dim')
    return (M, hy - 12, hx0 + hw, base_y)


# ───────────────────────── bottom-right: the Arsenal (forged weapon + wallet) ─────────────────────────
def arsenal(cv, parts=(('core', 'stormcore', 'rare'), ('mech', 'ricochet', 'epic'), ('relic', 'nyctian_eye', 'rare'),
                       ('sigil', 'sigil_anvilheart', 'godforged')), chassis='colossus_cannon', element='el_storm',
            element_color='storm', shards=46, ember=69, dim=False):
    base_y = RH - M
    cx = RW - M - 44
    cy = base_y - 44
    # chassis medallion (hexagon, element glow)
    s = 88
    m = slot_shape('hexflat', P(s))
    X, Y = P(cx) - m.width / 2, P(cy) - m.height / 2
    shadow(cv, m, X, Y, blur=P(10), off=(0, P(4)), alpha=0.8)
    glow(cv, m, X, Y, element_color, blur=P(9), alpha=0.35)
    fill_mask(cv, m, X, Y, grad_img(m.width, m.height, [(0, '#36271B'), (1, '#110B08')]))
    fill_mask(cv, shrink(m, P(3)), X, Y, radial_img(m.width, m.height, rgba(element_color, 0.28), rgba('#000000', 0), power=1.2))
    place_icon(cv, I.get(chassis), cx, cy, 58)
    fill_mask(cv, ring_of(m, max(1, P(2.2))), X, Y, gold_fill(m.width, m.height))
    fill_mask(cv, ring_of(shrink(m, P(4)), max(1, P(0.8))), X, Y, rgba('gold_dk', 0.8))
    # element badge
    framed_slot(cv, cx - 34, cy + 30, 26, 'circle', element, icon_scale=0.7, rim_w=1.2)
    # part slots to the left
    xs = [cx - 76 - i * 52 for i in range(4)][::-1]
    for (kind, icon, rar), x in zip(parts, xs):
        y = cy + 6
        framed_slot(cv, x, y, 44, kind, icon, icon_scale=0.62, rim_w=1.4, glow_color=None)
        gem_at(cv, x, y + 27, 4.6, rar, glow_a=0.55)
    # locked sigil marker
    place_icon(cv, I.get('lock'), xs[3] + 16, cy - 12, 14)
    # wallet above
    wy = cy - 50
    xr = RW - M
    f = cinzel(17, 800)
    t1 = f'{ember}'
    w1 = text_w(t1, f)
    draw_text(cv, xr, wy, t1, f, fill='parch', anchor='r')
    place_icon(cv, I.get('ember'), xr - w1 - 14, wy - 6, 22)
    t2 = f'{shards}'
    x2 = xr - w1 - 40
    w2 = text_w(t2, f)
    draw_text(cv, x2, wy, t2, f, fill='parch', anchor='r')
    place_icon(cv, I.get('godshard'), x2 - w2 - 12, wy - 7, 24)
    return (xs[0] - 26, wy - 20, RW - M, base_y)


# ───────────────────────── top-left: party ─────────────────────────
def party(cv, allies):
    """allies: [(slot 'p2', name, portrait, hp_frac, state, extra)]"""
    y = M + 2
    ink_smear(cv, 0, 0, 330, 34 + 48 * len(allies), 'left', a=0.5)
    for (pc, name, portrait, hp, state, extra) in allies:
        cx, cy = M + 20, y + 20
        d = int(P(40))
        cm = circle_mask(d)
        X, Y = P(cx) - d / 2, P(cy) - d / 2
        shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.8)
        if state == 'downed':
            glow(cv, cm, X, Y, 'danger', blur=P(7), alpha=0.9, spread=P(1))
        fill_mask(cv, cm, X, Y, gold_fill(d, d, GOLD_SOFT))
        inner = shrink(cm, P(2.2))
        fill_mask(cv, inner, X, Y, radial_img(d, d, '#3E2B1D', '#100A07', cy=0.4))
        fill_mask(cv, ring_of(inner, max(1, P(2.4))), X, Y, rgba(pc) if state != 'downed' else rgba('danger'))
        place_icon(cv, I.get(portrait), cx, cy, 26, desat=0.8 if state == 'downed' else 0, dark=0.3 if state == 'downed' else 0)
        tx = cx + 28
        if state == 'downed':
            draw_text(cv, tx, cy - 3, name, body(16, 'Bold'), fill='parch')
            nw = text_w(name, body(16, 'Bold'))
            draw_text(cv, tx + nw + 8, cy - 3, 'DOWNED', cinzel(12, 800), fill='danger', tracking=0.1)
            bar(cv, tx, cy + 5, 150, 7, extra, [(0, '#FFFFFF'), (1, '#FFB0A8')], r=3, rim=0.5, sheen=False)
            draw_text(cv, tx + 158, cy + 12, f'{int(extra * 20)}s', cinzel(12, 800), fill='parch', anchor='l')
            place_icon(cv, I.get('tether'), tx + 190, cy + 1, 18)
        else:
            draw_text(cv, tx, cy - 3, name, body(16, 'Bold'), fill='parch')
            bar(cv, tx, cy + 5, 150, 7, hp, [(0, 'hp_lt'), (1, 'hp_dk')], r=3, rim=0.55, sheen=False)
            if extra == 'ult':
                nw = text_w(name, body(16, 'Bold'))
                gem_at(cv, tx + nw + 10, cy - 8, 4.2, '#FFD36B', glow_a=0.8)
        y += 48
    return (0, 0, 330, y)


# ───────────────────────── top-right: the Wayfinder (minimap slot + objective tracker) ─────────────────────────
def wayfinder(cv, map_img=None, seals=3, req=7, timer='07:32', threat=2, warlord=False, gate='sealed',
              objectives=(('poi_anvil', 'Anvil', 38, 46), ('poi_shrine', 'Shrine of Zephyros', 250, 102)), biome='CINDER WASTES',
              minimap=True):
    xr = RW - M
    top = M
    y = top
    if minimap:
        w, h = 264, 166
        x0 = xr - w
        X, Y = P(x0), P(y)
        m = rr_mask(P(w), P(h), P(10))
        shadow(cv, m, X, Y, blur=P(10), off=(0, P(4)), alpha=0.75)
        fill_mask(cv, m, X, Y, rgba('#0C0806', 0.92))
        if map_img is not None:
            mi = map_img.resize((m.width, m.height), Image.LANCZOS).convert('RGBA')
            # fog: dark outside a revealed blob
            fog = radial_img(m.width, m.height, rgba('#000000', 0), rgba('#0C0806', 0.96), cx=0.52, cy=0.55, rx=0.5, ry=0.62, power=2.4)
            mi.alpha_composite(fog)
            fill_mask(cv, shrink(m, P(3)), X, Y, with_alpha(mi, 0.95))
        # frame
        fill_mask(cv, ring_of(m, P(2.6)), X, Y, gold_fill(m.width, m.height))
        fill_mask(cv, ring_of(shrink(m, P(4)), max(1, P(0.8))), X, Y, rgba('gold_dk', 0.9))
        # north gem
        gem_at(cv, x0 + w / 2, y + 1, 5.5, '#FFE7A6', glow_a=0.4)
        draw_text(cv, x0 + w / 2, y + 22, 'N', cinzel(11, 800), fill='parch_dim', anchor='m', shadow_a=0.9)
        y += h + 14
    # tracker (right-aligned, ink smear)
    ink_smear(cv, xr - 330, y - 6, 354, 180, 'right', a=0.55)
    # line 1: biome + timer
    draw_text(cv, xr, y + 18, timer, cinzel(20, 800), fill='parch', anchor='r')
    tw = text_w(timer, cinzel(20, 800))
    place_icon(cv, I.get('hourglass'), xr - tw - 14, y + 11, 16, alpha=0.8)
    draw_text(cv, xr - tw - 30, y + 17, biome, cinzel(12, 700), fill='parch_dim', anchor='r', tracking=0.16)
    y += 34
    # line 2: seals
    sx = xr
    txt = f'{seals}/{req}'
    draw_text(cv, sx, y + 12, txt, cinzel(16, 800), fill='gold_lt', anchor='r')
    sx -= text_w(txt, cinzel(16, 800)) + 16
    for i in range(req)[::-1]:
        filled = i < seals
        if filled:
            place_icon(cv, I.get('seal'), sx, y + 6, 22)
        else:
            d = int(P(15))
            cm = circle_mask(d)
            fill_mask(cv, cm, P(sx) - d / 2, P(y + 6) - d / 2, rgba('#0E0907', 0.9))
            fill_mask(cv, ring_of(cm, max(1, P(1.2))), P(sx) - d / 2, P(y + 6) - d / 2, rgba('gold_dk'))
        sx -= 21
    y += 30
    # line 3: warlord + gate (icons with state words)
    f = cinzel(12, 800)
    gx = xr
    gate_word = {'sealed': 'SEALED', 'open': 'OPEN', 'gathering': 'GATHER 6'}[gate]
    draw_text(cv, gx, y + 12, gate_word, f, fill='parch_dim' if gate == 'sealed' else 'gold_lt', anchor='r', tracking=0.1)
    gx -= text_w(gate_word, f, 0.1) + 14
    place_icon(cv, I.get('poi_gate'), gx, y + 7, 20, desat=0.6 if gate == 'sealed' else 0, dark=0.2 if gate == 'sealed' else 0)
    gx -= 28
    ww = 'SLAIN' if warlord else 'WARLORD'
    draw_text(cv, gx, y + 12, ww, f, fill='parch_dim', anchor='r', tracking=0.1)
    gx -= text_w(ww, f, 0.1) + 14
    place_icon(cv, I.get('poi_warlord'), gx, y + 7, 20)
    if warlord:
        place_icon(cv, I.get('check'), gx + 8, y + 12, 12)
    y += 30
    # line 4: threat
    tx = xr
    for i in range(5)[::-1]:
        lit = i < threat
        pts_w, pts_h = 13, 9
        m = poly_mask(P(pts_w), P(pts_h), [(0, 0), (P(pts_w) - P(4), 0), (P(pts_w) - 1, P(pts_h) / 2), (P(pts_w) - P(4), P(pts_h) - 1), (0, P(pts_h) - 1), (P(4), P(pts_h) / 2)])
        X_, Y_ = P(tx - pts_w), P(y + 2)
        if lit:
            col = mix('#FFB347', '#FF3B30', i / 4)
            glow(cv, m, X_, Y_, col, blur=P(3), alpha=0.6)
            fill_mask(cv, m, X_, Y_, col)
        else:
            fill_mask(cv, m, X_, Y_, rgba('#231914', 0.95))
            fill_mask(cv, ring_of(m, 1), X_, Y_, rgba('#5A4232'))
        tx -= pts_w + 1
    draw_text(cv, tx - 8, y + 11, 'THREAT', f, fill='parch_dim', anchor='r', tracking=0.12)
    tx2 = tx - 8 - text_w('THREAT', f, 0.12) - 12
    place_icon(cv, I.get('threat'), tx2, y + 6, 16)
    y += 30
    # objectives (nearest), with a bearing chevron
    for icon, name, bearing, dist in objectives:
        dt = f'{dist} m'
        draw_text(cv, xr, y + 12, dt, cinzel(13, 800), fill='parch', anchor='r')
        bx = xr - text_w(dt, cinzel(13, 800)) - 12
        chev = Image.new('L', (int(P(14)), int(P(14))), 0)
        c = chev.width / 2
        a = math.radians(bearing - 90)
        pts = [(c + c * 0.95 * math.cos(a), c + c * 0.95 * math.sin(a)),
               (c + c * 0.7 * math.cos(a + 2.5), c + c * 0.7 * math.sin(a + 2.5)),
               (c + c * 0.2 * math.cos(a + math.pi), c + c * 0.2 * math.sin(a + math.pi)),
               (c + c * 0.7 * math.cos(a - 2.5), c + c * 0.7 * math.sin(a - 2.5))]
        ImageDraw.Draw(chev).polygon(pts, fill=255)
        fill_mask(cv, chev, P(bx) - c, P(y + 7) - c, rgba('gold_lt'))
        draw_text(cv, bx - 12, y + 12, name, body(15, 'Medium'), fill='parch_dim', anchor='r')
        nx = bx - 12 - text_w(name, body(15, 'Medium')) - 13
        place_icon(cv, I.get(icon), nx, y + 6, 20)
        y += 26
    return y


# ───────────────────────── transient: toasts, callouts, banners ─────────────────────────
def toast(cv, y, icon, parts, a=1.0):
    x = M
    ink_smear(cv, 0, y - 18, 420, 30, 'left', a=0.6 * a)
    place_icon(cv, I.get(icon), x + 11, y - 5, 20, alpha=a)
    xx = x + 28
    for t, f, col in parts:
        draw_text(cv, xx, y, t, f, fill=col, alpha=a)
        xx += text_w(t, f)


def callout(cv, cx, y, name, count=None, stops=('#FFF7DA', '#FFD36B', '#3FD8FF'), sub=None):
    f = cinzel(38, 900)
    w = text_w(name, f, 0.06)
    # soft dark halo for legibility
    hw_, hh_ = int(P(w + 260)), int(P(120))
    halo = radial_img(hw_ // 3, hh_ // 3, rgba('#050302', 0.62), rgba('#050302', 0), power=1.5).resize((hw_, hh_), Image.BILINEAR)
    cv.put(halo, P(cx) - hw_ / 2, P(y - 14) - hh_ / 2)
    draw_text(cv, cx, y, name, f, anchor='m', tracking=0.06, grad=[rgba(s) for s in stops], stroke=1.4,
              stroke_color='#1A0E06', glow_color=stops[2], glow_a=0.55, shadow_a=0.8)
    if count:
        draw_text(cv, cx + w / 2 + 10, y - 2, f'×{count}', body(26, 'Bold'), fill='gold_lt', stroke=1.2, shadow_a=0.9)
    filigree_rule(cv, cx, y + 14, w / 2 + 30, 0.9)
    if sub:
        draw_text(cv, cx, y + 36, sub, body(15, 'Italic'), fill='parch_dim', anchor='m')


def region_banner(cv, name, sub, y=250):
    f = cinzel(44, 700)
    w = text_w(name, f, 0.08)
    hw_, hh_ = int(P(w + 420)), int(P(170))
    halo = radial_img(hw_ // 3, hh_ // 3, rgba('#050302', 0.66), rgba('#050302', 0), power=1.5).resize((hw_, hh_), Image.BILINEAR)
    cv.put(halo, P(RW / 2) - hw_ / 2, P(y - 12) - hh_ / 2)
    filigree_rule(cv, RW / 2, y - 52, w / 2 + 90, 0.95, gem='#FFE7A6')
    draw_text(cv, RW / 2, y, name, f, anchor='m', tracking=0.08, grad=[rgba('#FFF4D0'), rgba('#F2C667'), rgba('#B07A30')],
              stroke=1.0, stroke_color='#1A0E06', shadow_a=0.9)
    draw_text(cv, RW / 2, y + 30, sub, body(18, 'Italic'), fill='parch_dim', anchor='m')


# ───────────────────────── world-anchored ─────────────────────────
def ally_tag(cv, cx, cy, name, pc, hp, show_name=True):
    """cx,cy = head point in ref px."""
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


def elite_bar(cv, cx, cy, frac, w=54):
    bar(cv, cx - w / 2, cy, w, 6, frac, [(0, '#F06A4A'), (1, '#9A1E1A')], r=1.5, rim=0.0, sheen=False, trough='#0B0706')
    # a thin danger crown tick marks it as elite (red, allowed: enemy danger)
    m = poly_mask(P(10), P(6), [(0, P(6)), (P(2.5), 0), (P(5), P(4)), (P(7.5), 0), (P(10), P(6))])
    fill_mask(cv, m, P(cx - 5), P(cy - 7), rgba('danger'))


def world_prompt(cv, cx, cy, key, verb, what, hold=None, pad_btn=None):
    """Plate above an interactable: [key] VERB, small subject line, optional hold ring around the key."""
    fv = cinzel(16, 800)
    fw = body(14, 'Medium')
    w = max(text_w(verb, fv, 0.08), text_w(what, fw)) + 62
    h = 44
    x0 = cx - w / 2
    y0 = cy - h
    quiet_plate(cv, x0, y0, w, h, r=6, alpha=0.8, rim=0.7)
    # tail
    tail = poly_mask(P(14), P(8), [(0, 0), (P(14), 0), (P(7), P(8))])
    fill_mask(cv, tail, P(cx - 7), P(cy - 1), rgba('lac_bot', 0.8))
    kx = x0 + 22
    ky = y0 + h / 2
    if hold is not None:
        d = int(P(30))
        cm = circle_mask(d)
        ring = ring_of(cm, max(1, P(2.4)))
        fill_mask(cv, ring, P(kx) - d / 2, P(ky) - d / 2, rgba('#000000', 0.6))
        fill_mask(cv, ImageChops.multiply(ring, conic_mask(d, hold)), P(kx) - d / 2, P(ky) - d / 2, rgba('gold_lt'))
    if pad_btn:
        pad_button(cv, kx, ky, pad_btn, r=10)
    else:
        keycap(cv, kx, ky, key, h=20)
    draw_text(cv, x0 + 42, y0 + 20, verb, fv, fill='gold_lt', tracking=0.08)
    draw_text(cv, x0 + 42, y0 + 37, what, fw, fill='parch_dim')


def dmg(cv, x, y, n, kind='normal', color=None):
    if kind == 'crit':
        f = cinzel(24, 900)
        draw_text(cv, x, y, str(n), f, fill=color or '#FFE9B0', anchor='m', stroke=1.6, stroke_color='#1A0B04',
                  glow_color='#FFB347', glow_a=0.6)
        w = text_w(str(n), f)
        s = I.get('el_kinetic')
        place_icon(cv, s, x + w / 2 + 8, y - 16, 14)
    else:
        f = cinzel(17, 800)
        draw_text(cv, x, y, str(n), f, fill=color or 'parch', anchor='m', stroke=1.2, stroke_color='#1A0B04')


def edge_pin(cv, x, y, icon, color, label, dist, angle_deg, a=1.0, pulse=False):
    """Off-screen marker: a medallion with an outward nub; label + distance tucked inward."""
    r = 17
    d = int(P(r * 2))
    cm = circle_mask(d)
    X, Y = P(x) - d / 2, P(y) - d / 2
    # nub pointing outward
    nub = Image.new('L', (d * 2, d * 2), 0)
    c = d
    ang = math.radians(angle_deg - 90)
    tip = (c + (d / 2 + P(11)) * math.cos(ang), c + (d / 2 + P(11)) * math.sin(ang))
    l = (c + d / 2 * 0.8 * math.cos(ang + 0.55), c + d / 2 * 0.8 * math.sin(ang + 0.55))
    rr = (c + d / 2 * 0.8 * math.cos(ang - 0.55), c + d / 2 * 0.8 * math.sin(ang - 0.55))
    ImageDraw.Draw(nub).polygon([tip, l, rr], fill=255)
    shadow(cv, cm, X, Y, blur=P(4), off=(0, P(2)), alpha=0.8 * a)
    if pulse:
        glow(cv, cm, X, Y, color, blur=P(8), alpha=0.9, spread=P(2))
    fill_mask(cv, nub, X - d / 2, Y - d / 2, rgba(color, a))
    fill_mask(cv, cm, X, Y, with_alpha(radial_img(d, d, '#3A291C', '#0D0806'), 0.92 * a))
    fill_mask(cv, ring_of(cm, max(1, P(2))), X, Y, rgba(color, a))
    place_icon(cv, I.get(icon), x, y, 22, alpha=a)
    return


def pin_label(cv, x, y, label, dist, anchor='m'):
    draw_text(cv, x, y, dist, cinzel(12, 800), fill='parch', anchor=anchor, shadow_a=0.95, stroke=1.0)
    if label:
        draw_text(cv, x, y + 15, label, body(13, 'Medium'), fill='parch_dim', anchor=anchor, shadow_a=0.95, stroke=0.8)
