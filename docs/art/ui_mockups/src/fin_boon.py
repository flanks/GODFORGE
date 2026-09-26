"""Boon cards (final): kit-A shrine-niche silhouette carrying kit-B content (boon icon, kind pill, NEW/UPGRADE, pips)."""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from fin import *  # noqa: F401,F403
import fin as F
import gmkit as K
import gm_panels as GP
from cards import niche_mask
from gmorn import corner_v2_mask, crest_img, lattice

RNAME = {'common': 'COMMON', 'rare': 'RARE', 'epic': 'EPIC', 'godforged': 'GODFORGED'}


def god_socket(size, gods, icon_img, kind='Standard'):
    """Apex medallion: god-colour enamel (split for a Duo) holding the boon icon; gilt bezel; crest for Legendary."""
    pad = 30
    img = K.blank(size + pad * 2, size + pad * 2)
    so = K.socket(size, 'round', frame=5.0)
    import hud_parts as HP
    for i, gk in enumerate(gods[:2]):
        name, c1, c2, _ = K.GODS[gk]
        en = HP.enamel_disc(size, K.mix(c1, '#000000', 0.5), 5.0, light=0.3, dark=0.62)
        if len(gods) > 1:
            half = Image.new('L', (size, size), 0)
            ImageDraw.Draw(half).polygon([(0, 0), (size, 0), (0, size)] if i == 0 else [(size, 0), (size, size), (0, size)], fill=255)
            en = K.clip_to(en, half)
        so.alpha_composite(en)
        rg = K.radial_glow(size, size, c1, opacity=0.5, falloff=1.6)
        so.alpha_composite(K.clip_to(rg, HP.down(HP.disc(size, 5.0), size, size)))
    ic = icon_img.resize((int(size * 0.64), int(size * 0.64)), Image.LANCZOS)
    so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    ring = ImageChops.subtract(HP.disc(size), HP.disc(size, 5.0))
    so.alpha_composite(K.metal_from_mask(ring, size, size, bevel=2.6, rough=0.03))
    K.paste_shadowed(img, so, (pad, pad), blur=6, offset=(0, 4), opacity=0.8)
    if kind == 'Legendary':
        cr = crest_img(int(size * 0.5), '#FFB82E')
        img.alpha_composite(cr, (pad + size // 2 - cr.width // 2, pad - int(cr.height * 0.55)))
    return img, pad


def sigil_badge(size, god):
    import gm_icons as GI
    name, c1, c2, _ = K.GODS[god]
    img = K.socket(size, 'round', frame=2.4)
    import hud_parts as HP
    img.alpha_composite(HP.enamel_disc(size, K.mix(c1, '#000000', 0.55), 2.4, light=0.3, dark=0.6))
    tint = c2 if god in ('pyra', 'umbra_rex') else c1
    g = GI.render_icon(god, int(size * 0.74), tint=tint, light=K.mix(tint, '#FFFFFF', 0.6), outline=1.0, pad=0.04)
    img.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
    ring = ImageChops.subtract(HP.disc(size), HP.disc(size, 2.4))
    img.alpha_composite(K.metal_from_mask(ring, size, size, bevel=1.2, rough=0.03))
    return img


def niche_card(gods, name, rarity, kind, desc, key, icon, tag='NEW', level=None, W=300, Hh=420, hover=False):
    c1 = K.GODS[gods[0]][1]
    c2 = K.GODS[gods[-1]][1]
    rc = K.RARITY[rarity]
    ARCH = 112
    pad = 44
    img = K.blank(W + pad * 2, Hh + pad * 2)
    ox, oy = pad, pad
    frame_stops = K.BRONZE_RAMP if rarity == 'common' else K.GOLD_RAMP
    outer = niche_mask(W, Hh, ARCH)
    body_m = niche_mask(W, Hh, ARCH, inset=4.0)
    if hover or rarity == 'godforged':
        aura = K.blank(W, Hh, K.rgba(c1 if hover else rc))
        aura.putalpha(K.down(outer, W, Hh))
        K.glow(img, aura, (ox, oy), c1 if hover else rc, blur=24, opacity=0.55 if hover else 0.35, spread=4)
    sh = K.blank(W, Hh, K.rgba('#000000'))
    sh.putalpha(K.down(outer, W, Hh))
    s2, sp = K.shadow_of(sh, blur=14, offset=(0, 12), opacity=0.85)
    img.alpha_composite(s2, (ox - sp, oy - sp))
    # body: god-tinted lacquer (80 % toward lacquer black), darker at the foot; god light pool under the arch
    body = K.lacquer(W, Hh, top=K.mix(c1, '#140E0B', 0.8), bot='#090605', alpha=0.97, edge_dark=0.5, sheen=0.04, seed=4)
    body = lattice(body, alpha=0.025)
    rg = K.radial_glow(W + 80, 300, c1, opacity=0.4, falloff=1.5)
    body.alpha_composite(rg, (-40, -40))
    if len(gods) > 1:
        rg2 = K.radial_glow(W + 80, 300, c2, opacity=0.34, falloff=1.5)
        half = Image.new('L', rg2.size, 0)
        ImageDraw.Draw(half).rectangle([rg2.width // 2, 0, rg2.width, rg2.height], fill=255)
        body.alpha_composite(K.clip_to(rg2, half.filter(ImageFilter.GaussianBlur(40))), (-40, -40))
    # faint engraved sigil watermark in the lower half (6 %)
    import gm_icons as GI
    wm = GI.render_icon(gods[0], int(W * 0.62), tint=c1, light=K.mix(c1, '#FFFFFF', 0.3), outline=0, pad=0.0)
    wm.putalpha(wm.split()[3].point(lambda v: int(v * 0.06)))
    body.alpha_composite(wm, (int(W / 2 - wm.width / 2), Hh - wm.height - 36))
    if rarity == 'godforged':
        sb = K.sunburst(W - 40, 150)
        sb.putalpha(sb.split()[3].point(lambda v: int(v * 0.45)))
        body.alpha_composite(sb, (20, 0))
    img.alpha_composite(K.clip_to(body, K.down(body_m, W, Hh)), (ox, oy))
    inv = ImageChops.invert(K.down(body_m, W, Hh)).filter(ImageFilter.GaussianBlur(9))
    ish = K.blank(W, Hh, K.rgba('#000000'))
    ish.putalpha(ImageChops.multiply(inv, K.down(body_m, W, Hh)).point(lambda v: int(v * 0.7)))
    img.alpha_composite(ish, (ox, oy))
    # double gilt frame (bronze for Common) + god-enamel hairline (graded to the second god on a Duo) + bronze keyline
    fw = 4.2 if rarity != 'common' else 3.4
    ring = ImageChops.subtract(outer, niche_mask(W, Hh, ARCH, inset=fw))
    img.alpha_composite(K.metal_from_mask(ring, W, Hh, bevel=fw * 0.55, stops=frame_stops, rough=0.03), (ox, oy))
    en = ImageChops.subtract(niche_mask(W, Hh, ARCH, inset=fw + 2.0), niche_mask(W, Hh, ARCH, inset=fw + 3.6))
    grad = np.zeros((Hh, W, 4), np.float32)
    t = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    grad[..., :3] = np.array(K.rgb(c1), np.float32) * (1 - t) + np.array(K.rgb(c2), np.float32) * t
    grad[..., 3] = 255
    gi = K.to_img(grad)
    gi.putalpha(K.down(en, W, Hh).point(lambda v: int(v * 0.85)))
    img.alpha_composite(gi, (ox, oy))
    kl = ImageChops.subtract(niche_mask(W, Hh, ARCH, inset=fw + 7), niche_mask(W, Hh, ARCH, inset=fw + 8.2))
    img.alpha_composite(K.metal_from_mask(kl, W, Hh, bevel=0.5, stops=K.BRONZE_RAMP, rough=0.0), (ox, oy))
    cs = 60
    cm, off = corner_v2_mask(cs)
    cimg = K.metal_from_mask(cm, cs, cs, bevel=1.5, stops=frame_stops)
    img.alpha_composite(cimg.transpose(Image.FLIP_TOP_BOTTOM), (ox - off, oy + Hh + off - cs))
    img.alpha_composite(cimg.transpose(Image.ROTATE_180), (ox + W + off - cs, oy + Hh + off - cs))
    # rarity gems at the arch springers: the cut is the colour-blind backup (Rare lozenge, Epic hex, Godforged star)
    gems = []
    if rarity != 'common':
        for sx in (0, W):
            gems.append((sx, ARCH, 8.0))
    cx = ox + W / 2
    med, mpad = god_socket(100, gods, icon, kind)
    img.alpha_composite(med, (int(cx - med.width / 2), oy + 6 - mpad))
    # god sigil badges at the medallion's shoulders
    if len(gods) == 1:
        b = sigil_badge(34, gods[0])
        img.alpha_composite(b, (int(cx + 30), oy + 76))
    else:
        for i, gk in enumerate(gods[:2]):
            b = sigil_badge(32, gk)
            img.alpha_composite(b, (int(cx - 62 if i == 0 else cx + 30), oy + 78))
    gname = ' & '.join(K.GODS[g][0] for g in gods).upper()
    gy = oy + 146
    K.draw_text(img, (cx, gy), gname, K.cinzel(13, 800), fill=K.mix(c1, '#FFFFFF', 0.45) if len(gods) == 1 else K.TOK['parch'],
                anchor='m', tracking=3.0, shadow=0.9, shadow_off=(0, 1), shadow_blur=1.2)
    y = gy + 12
    if kind != 'Standard':
        kf = K.cinzel(11, 800)
        kw = K.text_size(kind.upper(), kf, 2.0)[0] + 20
        pill = K.gilded_panel(kw, 18, r=9, frame=1.2, corners=0, keyline=False, alpha=0.95, top='#F2D493', bot='#B08440')
        img.alpha_composite(pill, (int(cx - kw / 2), y))
        K.draw_text(img, (cx, y + 13), kind.upper(), kf, fill='#2A1606', anchor='m', tracking=2.0, shadow=0)
        y += 22
    for sz in (26, 24, 22, 20):
        nf = K.cinzel(sz, 800)
        if K.text_size(name, nf, 1.0)[0] <= W - 44:
            break
    K.draw_text(img, (cx, y + 36), name, nf, fill=rc if rarity != 'common' else K.TOK['parch'], anchor='m', tracking=1.0,
                gradient=None if rarity != 'godforged' else ('#FFF6D8', '#FFB82E'), shadow=0.95, shadow_off=(0, 2), shadow_blur=2,
                glow_color=rc if rarity in ('epic', 'godforged', 'rare') else None, glow_amt=0.3, glow_blur=10)
    y += 48
    rf = K.cinzel(11, 800)
    label = RNAME[rarity]
    rw = K.text_size(label, rf, 2.4)[0]
    rib = K.gilded_panel(rw + 46, 22, r=4, frame=1.3, corners=0, keyline=False, alpha=0.9, chamfer=True,
                         frame_stops=frame_stops)
    img.alpha_composite(rib, (int(cx - (rw + 46) / 2), y))
    if rarity != 'common':
        gems.append((cx - ox - (rw + 46) / 2 + 14, y - oy + 11, 5.2))
    K.draw_text(img, (cx + (7 if rarity != 'common' else 0), y + 16), label, rf,
                fill=rc if rarity != 'common' else K.TOK['parch_dim'], anchor='m', tracking=2.4, shadow=0.8, shadow_off=(0, 1),
                shadow_blur=1)
    y += 38
    img.alpha_composite(K.divider(W - 96, 12, rc if rarity != 'common' else None), (int(cx - (W - 96) / 2), y))
    GP.rich_desc(img, cx, y + 40, desc, W - 52, 18)
    # footer: NEW / UPGRADE (left), the pick key on the plinth, level pips (right)
    fy = oy + Hh - 34
    if tag:
        K.draw_text(img, (ox + 26, fy), tag, K.cinzel(11, 800), fill=K.TOK['ichor'] if tag == 'NEW' else K.TOK['parch_dim'],
                    tracking=2.2, shadow=0.8, shadow_off=(0, 1), shadow_blur=1)
    if level:
        for i in range(level[1]):
            g = K.gem(10, '#FFE9B0' if i < level[0] else '#3A2A1C', dim=1.0 if i < level[0] else 0.7)
            img.alpha_composite(g, (int(ox + W - 34 - i * 14), fy - 9))
    kc = K.keycap(key, 30, 16)
    img.alpha_composite(kc, (int(cx - kc.width / 2), oy + Hh - 15))
    return img, (ox, oy), gems, rarity


def place_card(cv, x, y, *a, **kw):
    img, (ox, oy), gems, rarity = niche_card(*a, **kw)
    F.put1x(cv, img, x - ox, y - oy)
    for gx, gy, r in gems:
        F.rarity_gem(cv, x + gx, y + gy, r, rarity, glow_a=0.6 if rarity in ('epic', 'godforged') else 0.3)
