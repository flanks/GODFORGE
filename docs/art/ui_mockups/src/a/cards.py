"""Shrine-niche boon cards: an arched card whose apex holds the god medallion (original GODFORGE form)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy import ndimage

import gmkit as K
import hud_v2 as H
import gm_icons as I
import gm_panels as P
from gmkit import SS, TOK, blank, clip_to, down, draw_text, gem, glow, lacquer, metal_from_mask, mix, rgba, sans, cinzel, to_img
from gmorn import corner_v2_mask, crest_img, lattice, leaf


def niche_poly(w, h, arch, inset=0.0, cham=14.0, n=90):
    """Outline of the niche: straight sides, chamfered foot, an ogee arch with a small cusp at the apex."""
    i = inset
    pts = [(i, h - cham - i * 0.4), (i, arch)]
    for k in range(n + 1):
        t = k / n
        x = i + (w - 2 * i) * t
        base = math.sin(math.pi * t) ** 0.72
        cusp = max(0.0, 1 - abs(t - 0.5) / 0.07) ** 1.6 * 0.16
        y = arch - (arch - i) * min(1.0, base + cusp * (1 - 0.0))
        pts.append((x, y))
    pts += [(w - i, arch), (w - i, h - cham - i * 0.4), (w - cham - i * 0.4, h - i), (cham + i * 0.4, h - i)]
    return pts


def niche_mask(w, h, arch, inset=0.0):
    m = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(m).polygon([(x * SS, y * SS) for x, y in niche_poly(w, h, arch, inset)], fill=255)
    return m


def niche_card(gods: list[str], name: str, rarity: str, kind: str, desc: str, key: str, footer: str | None = None,
               W: int = 330, Hh: int = 470, hover: bool = False) -> Image.Image:
    c1 = K.GODS[gods[0]][1]
    c2 = K.GODS[gods[-1]][1]
    rc = K.RARITY[rarity]
    ARCH = 118
    pad = 40
    img = blank(W + pad * 2, Hh + pad * 2)
    ox, oy = pad, pad
    frame_stops = K.BRONZE_RAMP if rarity == "common" else K.GOLD_RAMP
    outer = niche_mask(W, Hh, ARCH)
    body_m = niche_mask(W, Hh, ARCH, inset=4.0)
    # hover aura / legendary radiance
    if hover or rarity == "godforged":
        aura = blank(W, Hh, rgba(c1 if hover else rc))
        aura.putalpha(down(outer, W, Hh))
        glow(img, aura, (ox, oy), c1 if hover else rc, blur=24, opacity=0.5 if hover else 0.35, spread=4)
    # drop shadow
    sh = blank(W, Hh, rgba("#000000"))
    sh.putalpha(down(outer, W, Hh))
    s2, sp = K.shadow_of(sh, blur=14, offset=(0, 12), opacity=0.8)
    img.alpha_composite(s2, (ox - sp, oy - sp))
    # body: god-tinted lacquer, darker toward the foot
    body = lacquer(W, Hh, top=mix(c1, "#140E0B", 0.8), bot="#090605", alpha=0.97, edge_dark=0.5, sheen=0.04, seed=4)
    body = lattice(body, alpha=0.025)
    rg = K.radial_glow(W + 80, 300, c1, opacity=0.42, falloff=1.5)
    body.alpha_composite(rg, (-40, -40))
    if rarity == "godforged":
        sb = K.sunburst(W - 40, 150)
        sb.putalpha(sb.split()[3].point(lambda v: int(v * 0.45)))
        body.alpha_composite(sb, (20, 0))
    # watermark sigil
    wm = I.render_icon(gods[0], int(W * 0.7), tint=c1, light=mix(c1, "#FFFFFF", 0.3), outline=0, pad=0.0)
    wm.putalpha(wm.split()[3].point(lambda v: int(v * 0.06)))
    body.alpha_composite(wm, (int(W / 2 - wm.width / 2), Hh - wm.height - 44))
    img.alpha_composite(clip_to(body, down(body_m, W, Hh)), (ox, oy))
    # inner shadow under the frame
    inv = ImageChops.invert(down(body_m, W, Hh)).filter(ImageFilter.GaussianBlur(9))
    ish = blank(W, Hh, rgba("#000000"))
    ish.putalpha(ImageChops.multiply(inv, down(body_m, W, Hh)).point(lambda v: int(v * 0.7)))
    img.alpha_composite(ish, (ox, oy))
    # double gilt frame + god enamel hairline
    fw = 4.2 if rarity != "common" else 3.4
    ring = ImageChops.subtract(outer, niche_mask(W, Hh, ARCH, inset=fw))
    img.alpha_composite(metal_from_mask(ring, W, Hh, bevel=fw * 0.55, stops=frame_stops, rough=0.03), (ox, oy))
    en = ImageChops.subtract(niche_mask(W, Hh, ARCH, inset=fw + 2.0), niche_mask(W, Hh, ARCH, inset=fw + 3.6))
    grad = np.zeros((Hh, W, 4), np.float32)
    t = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    grad[..., :3] = np.array(K.rgb(c1), np.float32) * (1 - t) + np.array(K.rgb(c2), np.float32) * t
    grad[..., 3] = 255
    gi = to_img(grad)
    gi.putalpha(down(en, W, Hh).point(lambda v: int(v * 0.85)))
    img.alpha_composite(gi, (ox, oy))
    kl = ImageChops.subtract(niche_mask(W, Hh, ARCH, inset=fw + 7), niche_mask(W, Hh, ARCH, inset=fw + 8.2))
    img.alpha_composite(metal_from_mask(kl, W, Hh, bevel=0.5, stops=K.BRONZE_RAMP, rough=0.0), (ox, oy))
    # bottom corner flourishes
    cs = 64
    cm, off = corner_v2_mask(cs)
    cimg = metal_from_mask(cm, cs, cs, bevel=1.5, stops=frame_stops)
    bl = cimg.transpose(Image.FLIP_TOP_BOTTOM)
    br = cimg.transpose(Image.ROTATE_180)
    img.alpha_composite(bl, (ox - off, oy + Hh + off - cs))
    img.alpha_composite(br, (ox + W + off - cs, oy + Hh + off - cs))
    # rarity gems at the arch springers (+ epic/godforged at the foot)
    if rarity != "common":
        g = gem(18, rc, glow_amt=0.6 if rarity in ("epic", "godforged") else 0.0)
        gw = g.width
        for sx in (0, W):
            img.alpha_composite(g, (int(ox + sx - gw / 2), int(oy + ARCH - gw / 2)))
    cx = ox + W / 2
    # medallion in the arch
    med = P.god_medallion(108, gods, kind)
    img.alpha_composite(med, (int(cx - med.width / 2), oy + 6 - 20 + (0 if kind != "Legendary" else 0)))
    # god ribbon
    gname = " & ".join(K.GODS[g][0] for g in gods).upper()
    gy = oy + 152
    draw_text(img, (cx, gy), gname, cinzel(14, 700), fill=mix(c1, "#FFFFFF", 0.4), anchor="m", tracking=3.2, shadow=0.9,
              shadow_off=(0, 1), shadow_blur=1.2)
    gwid = K.text_size(gname, cinzel(14, 700), 3.2)[0]
    for sgn in (-1, 1):
        ln = K.divider(62, 8)
        la = np.asarray(ln.split()[3], np.float32)
        ramp = np.linspace(0, 1, 62) if sgn < 0 else np.linspace(1, 0, 62)
        ln.putalpha(Image.fromarray((la * ramp[None, :]).astype(np.uint8)))
        img.alpha_composite(ln, (int(cx + sgn * (gwid / 2 + 10) - (62 if sgn < 0 else 0)), gy - 9))
    # boon name (auto-fit)
    for sz in (27, 25, 23, 21, 20):
        nf = cinzel(sz, 700)
        if K.text_size(name, nf)[0] <= W - 50:
            break
    draw_text(img, (cx, oy + 194), name, nf, fill=rc if rarity != "common" else TOK["parch"], anchor="m",
              gradient=None if rarity != "godforged" else ("#FFF6D8", "#FFB82E"), shadow=0.95, shadow_off=(0, 2),
              shadow_blur=2, glow_color=rc if rarity in ("epic", "godforged", "rare") else None,
              glow_amt=0.3, glow_blur=10)
    # rarity ribbon
    label = P.RARITY_NAME[rarity] + ("" if kind == "Standard" else f" · {kind.upper()}")
    rf = cinzel(12, 700)
    rw = K.text_size(label, rf, 2.2)[0]
    rib = K.gilded_panel(rw + 50, 24, r=4, frame=1.4, corners=0, keyline=False, alpha=0.9, chamfer=True)
    img.alpha_composite(rib, (int(cx - (rw + 50) / 2), oy + 212))
    gg = gem(13, rc)
    img.alpha_composite(gg, (int(cx - (rw + 50) / 2 + 9), oy + 218))
    draw_text(img, (cx + 8, oy + 229), label, rf, fill=rc if rarity != "common" else TOK["parch_dim"], anchor="m",
              tracking=2.2, shadow=0.8, shadow_off=(0, 1), shadow_blur=1)
    img.alpha_composite(K.divider(W - 96, 12, rc if rarity != "common" else None), (int(cx - (W - 96) / 2), oy + 252))
    P.rich_desc(img, cx, oy + 300, desc, W - 56, 19)
    if footer:
        draw_text(img, (cx, oy + Hh - 46), footer, sans(15, "Italic"), fill=TOK["parch_dim"], anchor="m", shadow=0.8,
                  shadow_off=(0, 1), shadow_blur=1)
    # plinth foot with the key
    kc = K.keycap(key, 30, 16)
    img.alpha_composite(kc, (int(cx - kc.width / 2), oy + Hh - 15))
    return img
