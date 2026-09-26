"""Boon offer cards (designer B)."""
import math
from PIL import Image, ImageDraw, ImageChops, ImageFilter
from gf import *
import icons as I
from hud import framed_slot
from panels import button

GODS = {
    'zephyros': ('ZEPHYROS', '#3FD8FF', '#F2FBFF', 'god_zephyros', 'Storm, Sky'),
    'nyctia': ('NYCTIA', '#7B3FE0', '#141018', 'god_nyctia', 'Shadow, Silence'),
    'pyra': ('PYRA', '#E0312B', '#FFC23D', 'god_pyra', 'Flame, Wrath'),
}


def rich_wrap(cv, x, y, width, tokens, size=18, lh=23, anchor='m'):
    """tokens: [(text, style)] with style in {'n','num','kw:<color>'}; wraps on spaces, centre-aligned lines."""
    words = []
    for t, st in tokens:
        for i, wd in enumerate(t.split(' ')):
            if wd == '':
                continue
            words.append((wd, st))
    fonts = {'n': body(size, 'Medium'), 'num': body(size, 'Bold'), 'kw': body(size, 'Bold')}
    lines, cur, cw = [], [], 0
    sp = text_w(' ', fonts['n'])
    for wd, st in words:
        f = fonts[st.split(':')[0]]
        ww = text_w(wd, f)
        if cur and cw + sp + ww > width:
            lines.append((cur, cw))
            cur, cw = [], 0
        cw += (sp if cur else 0) + ww
        cur.append((wd, st, ww))
    if cur:
        lines.append((cur, cw))
    for li, (ln, lw) in enumerate(lines):
        xx = x - lw / 2 if anchor == 'm' else x
        for j, (wd, st, ww) in enumerate(ln):
            kind = st.split(':')[0]
            col = 'parch' if kind == 'n' else 'gold_lt' if kind == 'num' else st.split(':')[1]
            draw_text(cv, xx, y + li * lh, wd, fonts[kind], fill=col, shadow_a=0.8)
            xx += ww + sp
    return len(lines)


def boon_card(cv, x, y, w, h, gods, rarity, name, icon, desc_tokens, kind='Standard', key='1', selected=False,
              tag='NEW', level=None):
    g1 = GODS[gods[0]]
    g2 = GODS[gods[1]] if len(gods) > 1 else None
    lift = 12 if selected else 0
    y -= lift
    X, Y = P(x), P(y)
    m = rr_mask(P(w), P(h), P(12))
    shadow(cv, m, X, Y, blur=P(22 if selected else 14), off=(0, P(10 if selected else 6)), alpha=0.85)
    if selected:
        glow(cv, m, X, Y, g1[1], blur=P(18), alpha=0.55, spread=P(2))
    # lacquer body
    body_ = grad_img(m.width, m.height, [(0, '#241A14'), (0.5, '#16100C'), (1, '#0E0907')])
    fill_mask(cv, m, X, Y, body_)
    # god light from the crest
    gl = radial_img(m.width, m.height, rgba(g1[1], 0.34), rgba(g1[1], 0), cx=0.5 if not g2 else 0.3, cy=0.0, rx=0.9, ry=0.55, power=1.2)
    fill_mask(cv, m, X, Y, gl)
    if g2:
        gl2 = radial_img(m.width, m.height, rgba(g2[1], 0.5), rgba(g2[1], 0), cx=0.72, cy=0.0, rx=0.8, ry=0.55, power=1.2)
        fill_mask(cv, m, X, Y, gl2)
    # faint engraved pattern: concentric arcs behind the icon
    pat = Image.new('L', m.size, 0)
    pd = ImageDraw.Draw(pat)
    cx0, cy0 = m.width / 2, P(150)
    for r in range(int(P(60)), int(P(170)), int(P(16))):
        pd.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], outline=255, width=max(1, int(P(0.8))))
    fill_mask(cv, ImageChops.multiply(pat, shrink(m, P(6))), X, Y, rgba('gold_md', 0.10))
    # frame by rarity
    rc = rgba(rarity)
    fill_mask(cv, ring_of(m, P(3.2)), X, Y, gold_fill(m.width, m.height))
    fill_mask(cv, ring_of(m, max(1, P(0.8))), X, Y, rgba('gold_sh'))
    inner = shrink(m, P(7))
    if rarity == 'common':
        fill_mask(cv, ring_of(inner, max(1, P(0.9))), X, Y, rgba('gold_dk', 0.9))
    else:
        fill_mask(cv, ring_of(inner, max(1, P(1.4))), X, Y, rgba(rc, 0.95))
        glow(cv, ring_of(inner, max(1, P(1.4))), X, Y, rarity, blur=P(4), alpha=0.5)
    if rarity in ('epic', 'godforged'):
        inner2 = shrink(m, P(11))
        fill_mask(cv, ring_of(inner2, max(1, P(0.8))), X, Y, rgba(rc, 0.55))
        for (cx, cy) in [(x + 14, y + 14), (x + w - 14, y + 14), (x + 14, y + h - 14), (x + w - 14, y + h - 14)]:
            gem_at(cv, cx, cy, 4.2, rarity, glow_a=0.6)
    if rarity == 'godforged':
        for (cx, cy, fx, fy) in [(x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)]:
            corner_flourish(cv, cx, cy, fx, fy, size=24)
    if selected:
        fill_mask(cv, ring_of(m, P(3.2)), X, Y, gold_fill(m.width, m.height, [(0, '#FFFBE8'), (0.5, '#FFD978'), (1, '#C9933E')]))
    # crest medallion straddling the top edge
    ccx, ccy, R = x + w / 2, y + 2, 42
    d = int(P(R * 2))
    cm = circle_mask(d)
    cX, cY = P(ccx) - d / 2, P(ccy) - d / 2
    shadow(cv, cm, cX, cY, blur=P(6), off=(0, P(3)), alpha=0.85)
    glow(cv, cm, cX, cY, g1[1], blur=P(10), alpha=0.55)
    fill_mask(cv, cm, cX, cY, gold_fill(d, d))
    innerc = shrink(cm, P(4))
    if g2:
        split = Image.new('L', cm.size, 0)
        ImageDraw.Draw(split).polygon([(0, 0), (d, 0), (0, d)], fill=255)
        a_ = ImageChops.multiply(innerc, split)
        b_ = ImageChops.subtract(innerc, split)
        fill_mask(cv, a_, cX, cY, radial_img(d, d, mix(g1[1], '#000000', 0.35), mix(g1[1], '#000000', 0.8)))
        fill_mask(cv, b_, cX, cY, radial_img(d, d, mix(g2[1], '#000000', 0.2), mix(g2[1], '#000000', 0.8)))
        ln = Image.new('L', cm.size, 0)
        ImageDraw.Draw(ln).line([(d, 0), (0, d)], fill=255, width=max(1, int(P(1.6))))
        fill_mask(cv, ImageChops.multiply(ln, innerc), cX, cY, rgba('gold_lt'))
        place_icon(cv, I.get(g1[3]), ccx - 13, ccy - 12, 36)
        place_icon(cv, I.get(g2[3]), ccx + 13, ccy + 12, 36)
    else:
        fill_mask(cv, innerc, cX, cY, radial_img(d, d, mix(g1[1], '#000000', 0.45), mix(g1[1], '#000000', 0.85), cy=0.4))
        place_icon(cv, I.get(g1[3]), ccx, ccy, 54)
    fill_mask(cv, ring_of(innerc, max(1, P(1))), cX, cY, rgba('gold_dk'))
    gem_at(cv, ccx, ccy + R - 1, 6.5, rarity, glow_a=0.7)
    # god line
    gline = g1[0] if not g2 else f'{g1[0]}  &  {g2[0]}'
    draw_text(cv, x + w / 2, y + 72, gline, cinzel(13, 800), fill=g1[1] if not g2 else 'parch', anchor='m', tracking=0.2)
    if kind != 'Standard':
        kt = kind.upper()
        f = cinzel(11, 800)
        tw = text_w(kt, f, 0.2) + 20
        km = rr_mask(P(tw), P(20), P(10))
        kX, kY = P(x + w / 2 - tw / 2), P(y + 82)
        fill_mask(cv, km, kX, kY, grad_img(km.width, km.height, [(0, '#FFE7A0'), (1, '#B98030')]))
        draw_text(cv, x + w / 2, y + 97, kt, f, fill='ink_text', anchor='m', tracking=0.2, shadow_a=0)
    # icon on a halo
    icy = y + 150
    hd = int(P(104))
    hm = circle_mask(hd)
    glow(cv, hm, P(x + w / 2) - hd / 2, P(icy) - hd / 2, g1[1], blur=P(20), alpha=0.35)
    fill_mask(cv, hm, P(x + w / 2) - hd / 2, P(icy) - hd / 2, radial_img(hd, hd, rgba('#000000', 0.55), rgba('#000000', 0.0), power=0.9))
    fill_mask(cv, ring_of(hm, max(1, P(1))), P(x + w / 2) - hd / 2, P(icy) - hd / 2, rgba('gold_md', 0.5))
    place_icon(cv, I.get(icon), x + w / 2, icy, 84)
    # name + rarity
    ny = y + 236
    draw_text(cv, x + w / 2, ny, name, cinzel(25, 800), anchor='m', tracking=0.05,
              grad=[rgba('#FFF8E6'), rgba('#F4E6C8'), rgba('#D9C6A0')], stroke=0.6, stroke_color='#120A05')
    rn = {'common': 'COMMON', 'rare': 'RARE', 'epic': 'EPIC', 'godforged': 'GODFORGED'}[rarity]
    draw_text(cv, x + w / 2, ny + 22, rn, cinzel(12, 800), fill=rarity if rarity != 'common' else 'parch_dim', anchor='m', tracking=0.24)
    filigree_rule(cv, x + w / 2, ny + 38, w / 2 - 44, 0.75)
    rich_wrap(cv, x + w / 2, ny + 66, w - 44, desc_tokens, size=18, lh=23)
    # footer: key + tag
    fy = y + h - 26
    keycap(cv, x + w / 2, fy, key, h=24)
    if tag:
        f = cinzel(11, 800)
        draw_text(cv, x + 22, fy + 5, tag, f, fill='gold_lt' if tag == 'NEW' else 'parch_dim', tracking=0.2)
    if level:
        for i in range(level[1]):
            gem_at(cv, x + w - 26 - i * 14, fy, 3.6, '#FFE7A6' if i < level[0] else '#2A1F18', glow_a=0.4 if i < level[0] else 0)


def spotlight_dim(cv, cx, cy, r, a=0.58):
    """Dim the world except a soft hole around the local hero (you still see what hits you)."""
    w, h = cv.img.size
    small = radial_img(w // 8, h // 8, rgba('#07040A', 0), rgba('#07040A', a), cx=cx / RW, cy=cy / RH,
                       rx=r / RW, ry=r / RH, power=1.6)
    cv.img.alpha_composite(small.resize((w, h), Image.BILINEAR))
