"""GILDED MYTHIC HUD components (1080p UI px). Each builder returns an RGBA image."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import busts  # noqa: F401  (registers bust glyphs)
import gmkit as K
import gm_icons as I
from gmkit import (GOLD_RAMP, GOLD_TEXT, SS, STEEL_RAMP, TOK, blank, clip_to, down, draw_text, gem, glow, lacquer,
                   metal_from_mask, mix, rgb, rgba, sans, cinzel, to_img)
from gmorn import crest_img, inner_shadow, leaf, ornate_panel


def disc(size, inset=0.0):
    m = Image.new("L", (size * SS, size * SS), 0)
    i = inset * SS
    ImageDraw.Draw(m).ellipse([i, i, size * SS - 1 - i, size * SS - 1 - i], fill=255)
    return m


def diamond(size, inset=0.0):
    S = size * SS
    m = Image.new("L", (S, S), 0)
    k = inset * SS * 1.42
    c = S / 2
    ImageDraw.Draw(m).polygon([(c, k), (S - 1 - k, c), (c, S - 1 - k), (k, c)], fill=255)
    return m


def enamel_disc(size, color, inset, light=0.35, dark=0.45):
    """Glossy enamel fill (radial) in `color`, masked by a disc inset."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    r = np.sqrt((xx - c) ** 2 + (yy - c + size * 0.12) ** 2) / (size * 0.6)
    base = np.array(rgb(color), np.float32)
    hi = np.array(rgb(mix(color, "#FFFFFF", light)), np.float32)
    lo = np.array(rgb(mix(color, "#000000", dark)), np.float32)
    t = np.clip(r, 0, 1)[..., None]
    col = hi * (1 - t) + lo * t
    col = col * 0.5 + base * 0.5 * (1 - t * 0.5)
    img = to_img(np.dstack([col, np.full((size, size), 255, np.float32)]))
    return clip_to(img, down(disc(size, inset), size, size))


# ───────────────────────────── medallions ─────────────────────────────
def medallion(size: int, bust: str, pcolor: str | None, bezel: float = 6.0, band: float = 3.0,
              studs: int = 8, glow_col: str = "#5A3A20", arc: tuple[float, str] | None = None) -> Image.Image:
    img = blank(size, size)
    # portrait window
    inner_inset = bezel + (band if pcolor else 0)
    win = down(disc(size, inner_inset), size, size)
    body = lacquer(size, size, top="#2B2019", bot="#0B0706", alpha=1.0, edge_dark=0.7, sheen=0.12)
    rg = K.radial_glow(size, size, glow_col, opacity=0.55, falloff=1.4)
    body.alpha_composite(rg, (0, -int(size * 0.12)))
    bi = I.render_icon(bust, int(size * 0.86), tint="#B8925A", light="#F6E7C8", outline=1.4, pad=0.04)
    body.alpha_composite(bi, ((size - bi.width) // 2, int(size * 0.2)))
    img.alpha_composite(clip_to(body, win))
    img.alpha_composite(inner_shadow(size, size, size // 2, size * 0.08, 0.7).crop((0, 0, size, size)) if False else blank(1, 1))
    # player-colour band
    if pcolor:
        band_m = ImageChops.subtract(disc(size, bezel - 0.5), disc(size, bezel + band))
        en = enamel_disc(size, pcolor, 0, light=0.45, dark=0.35)
        img.alpha_composite(clip_to(en, down(band_m, size, size)))
    # optional arc meter (passive)
    if arc:
        frac, col = arc
        am = Image.new("L", (size * SS, size * SS), 0)
        d = ImageDraw.Draw(am)
        i = (bezel + band + 1.5) * SS
        d.arc([i, i, size * SS - 1 - i, size * SS - 1 - i], start=-90, end=-90 + 360 * frac, fill=255, width=int(3 * SS))
        a_img = blank(size, size, rgba(col))
        a_img.putalpha(down(am, size, size))
        img.alpha_composite(a_img)
    # bezel ring
    ring = ImageChops.subtract(disc(size), disc(size, bezel))
    rimg = metal_from_mask(ring, size, size, bevel=bezel * 0.5, rough=0.03)
    img.alpha_composite(rimg)
    # studs
    for k in range(studs):
        a = k * 2 * math.pi / studs + math.pi / studs
        r = size / 2 - bezel / 2
        x = size / 2 + math.cos(a) * r
        y = size / 2 + math.sin(a) * r
        s = max(5, int(bezel * 1.1))
        st = gem(s, "#E9D3A0", "lozenge", dim=0.85)
        img.alpha_composite(st, (int(x - s / 2), int(y - s / 2)))
    return img


def pchip(slot: int, size: int = 26) -> Image.Image:
    """'P2' plaque: a small lozenge-ended lacquer chip with the player numeral in its colour."""
    col = K.PLAYER[slot]
    f = cinzel(int(size * 0.5), 800)
    w = int(size * 1.7)
    h = size
    img = blank(w, h)
    m = Image.new("L", (w * SS, h * SS), 0)
    S = SS
    ImageDraw.Draw(m).polygon([(h * 0.45 * S, 0), (w * S - h * 0.45 * S, 0), (w * S - 1, h * S / 2),
                               (w * S - h * 0.45 * S, h * S - 1), (h * 0.45 * S, h * S - 1), (0, h * S / 2)], fill=255)
    body = lacquer(w, h, top="#2A1F18", bot="#0B0706", alpha=0.97)
    img.alpha_composite(clip_to(body, down(m, w, h)))
    inner = Image.new("L", (w * SS, h * SS), 0)
    k = 2.0 * S
    ImageDraw.Draw(inner).polygon([(h * 0.45 * S + k * 0.4, k), (w * S - h * 0.45 * S - k * 0.4, k), (w * S - 1 - k * 1.2, h * S / 2),
                                   (w * S - h * 0.45 * S - k * 0.4, h * S - 1 - k), (h * 0.45 * S + k * 0.4, h * S - 1 - k), (k * 1.2, h * S / 2)], fill=255)
    img.alpha_composite(metal_from_mask(ImageChops.subtract(m, inner), w, h, bevel=1.0, rough=0.0))
    draw_text(img, (w / 2, h / 2 + 1), f"P{slot + 1}", f, fill=col, anchor="m", valign="middle", shadow=0.8,
              shadow_off=(0, 1), shadow_blur=0.8, tracking=0.5)
    return img


# ───────────────────────────── vitals ─────────────────────────────
def armor_plates(n: int, filled: float, w: int = 28, h: int = 8, gap: int = 3) -> Image.Image:
    W = n * w + (n - 1) * gap
    img = blank(W, h)
    for i in range(n):
        x = i * (w + gap)
        f = max(0.0, min(1.0, filled * n - i))
        m = K.chamfer_mask(w, h, 2.5)
        if f > 0:
            pl = metal_from_mask(m, w, h, bevel=1.4, stops=STEEL_RAMP, rough=0.03)
            if f < 1:
                pl = pl.crop((0, 0, int(w * f), h))
            img.alpha_composite(pl, (x, 0))
        if f < 1:
            rec = lacquer(w, h, top="#0A0706", bot="#15100C", alpha=0.85, edge_dark=0, sheen=0)
            rec = clip_to(rec, down(m, w, h))
            if f > 0:
                rec = rec.crop((int(w * f), 0, w, h))
                img.alpha_composite(rec, (x + int(w * f), 0))
            else:
                img.alpha_composite(rec, (x, 0))
                ring = ImageChops.subtract(m, K.chamfer_mask(w, h, 2.5, inset=1))
                r_img = metal_from_mask(ring, w, h, bevel=0.5, stops=K.BRONZE_RAMP, rough=0.0)
                r_img.putalpha(r_img.split()[3].point(lambda v: int(v * 0.7)))
                img.alpha_composite(r_img, (x, 0))
    return img


def dash_pip(frac: float, w: int = 18, h: int = 24) -> Image.Image:
    img = blank(w, h)
    S = SS
    m = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(m).polygon([(w * S / 2, 0), (w * S - 1, h * S / 2), (w * S / 2, h * S - 1), (0, h * S / 2)], fill=255)
    inner = Image.new("L", (w * S, h * S), 0)
    k = 2.6 * S
    ImageDraw.Draw(inner).polygon([(w * S / 2, k * 1.3), (w * S - 1 - k, h * S / 2), (w * S / 2, h * S - 1 - k * 1.3), (k, h * S / 2)], fill=255)
    ins = down(inner, w, h)
    rec = lacquer(w, h, top="#060403", bot="#15100C", alpha=0.95, edge_dark=0, sheen=0)
    img.alpha_composite(clip_to(rec, ins))
    if frac > 0:
        yy = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
        col = K.ramp(yy, [(0, TOK["molten_hi"]), (0.5, TOK["ichor"]), (1.0, TOK["molten_lo"])])
        a = np.clip((yy - (1 - frac)) * h + 0.5, 0, 1) * 255
        fill = to_img(np.dstack([col, a]))
        if frac >= 1:
            g = blank(w, h)
            img.alpha_composite(clip_to(fill, ins))
        else:
            fa = np.asarray(fill, np.float32).copy()
            fa[..., :3] *= 0.62
            img.alpha_composite(clip_to(to_img(fa), ins))
    img.alpha_composite(metal_from_mask(ImageChops.subtract(m, inner), w, h, bevel=1.1, rough=0.0))
    return img


def buff_icon(name: str, frac_left: float, secs: str, size: int = 30, tint: str = "#D9B56C") -> Image.Image:
    img = blank(size, size + 14)
    so = K.socket(size, "round", frame=2.2)
    img.alpha_composite(so)
    ic = I.render_icon(name, int(size * 0.78), tint=tint, outline=1.0, pad=0.1)
    img.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    # remaining-time ring (bright arc)
    am = Image.new("L", (size * SS, size * SS), 0)
    i = 1 * SS
    ImageDraw.Draw(am).arc([i, i, size * SS - 1 - i, size * SS - 1 - i], start=-90, end=-90 + 360 * frac_left,
                           fill=255, width=int(2.2 * SS))
    ar = blank(size, size, rgba(TOK["ichor"]))
    ar.putalpha(down(am, size, size))
    img.alpha_composite(ar)
    draw_text(img, (size / 2, size + 11), secs, sans(12, "Bold"), fill=TOK["parch"], anchor="m", shadow=0.9,
              shadow_off=(0, 1), shadow_blur=0.8, outline=1)
    return img


def hero_cluster(st: dict) -> Image.Image:
    """Bottom-left: medallion + HP (armour plates, shield overlay) + dash pips + buffs."""
    W, H = 560, 160
    img = blank(W, H)
    M = 116
    mx, my = 6, H - M - 6
    bar_x, bar_w, bar_h = mx + M - 16, 336, 26
    bar_y = my + M // 2 - 4
    # armour plates above the bar
    if st.get("armor_max", 0) > 0:
        pl = armor_plates(10, st["armor"] / st["armor_max"])
        img.alpha_composite(pl, (bar_x + 22, bar_y - 13))
    hp = st["hp"] / st["max_hp"]
    b = K.blade_bar(bar_w, bar_h, hp, st.get("ghost", hp), TOK["hp_lo"], TOK["hp_mid"], TOK["hp_hi"], TOK["hp_ghost"],
                    frame=2.4, label=f'{int(st["hp"])} / {int(st["max_hp"])}', label_font=sans(17, "Bold"))
    K.paste_shadowed(img, b, (bar_x, bar_y), blur=4, offset=(0, 3), opacity=0.7)
    # dash pips + buffs row under the bar
    x = bar_x + 22
    y = bar_y + bar_h + 5
    for i in range(st["max_dash"]):
        f = 1.0 if i < st["dash"] else st.get("dash_recharge", 0.0) if i == st["dash"] else 0.0
        p = dash_pip(f)
        img.alpha_composite(p, (x, y))
        x += 22
    if st.get("buffs"):
        x += 12
        for (name, frac, secs) in st["buffs"]:
            bi = buff_icon(name, frac, secs, 28)
            img.alpha_composite(bi, (x, y - 3))
            x += 36
    med = medallion(M, st["bust"], K.PLAYER[st["slot"]], arc=st.get("passive_arc"))
    K.paste_shadowed(img, med, (mx, my), blur=6, offset=(0, 4), opacity=0.75)
    ch = pchip(st["slot"], 22)
    img.alpha_composite(ch, (mx + M // 2 - ch.width // 2, my + M - ch.height + 6))
    return img


# ───────────────────────────── arsenal hand ─────────────────────────────
def ability_socket(size: int, icon: str, key: str, cd_left: float = 0.0, cd_max: float = 1.0, ult: float | None = None,
                   ready: bool = False, tint: str = "#D9B56C", pad_key: str | None = None) -> Image.Image:
    padd = 22
    W = H = size + padd * 2
    img = blank(W, H + 8)
    so = K.socket(size, "diamond", frame=3.2 if size > 84 else 2.8)
    inner = down(diamond(size, 3.4), size, size)
    layer = blank(size, size)
    layer.alpha_composite(so)
    icon_img = I.render_icon(icon, int(size * 0.62), tint=tint, outline=1.4, pad=0.06)
    cooling = cd_left > 0.05 or (ult is not None and ult < 1.0)
    if ult is not None and ult < 1.0:
        # molten charge rising inside the mould
        yy = np.linspace(0, 1, size, dtype=np.float32)[:, None] * np.ones((1, size), np.float32)
        col = K.ramp(yy, [(0, TOK["molten_hi"]), (0.3, TOK["molten_mid"]), (1.0, TOK["molten_lo"])])
        lvl = 1 - (0.1 + 0.8 * ult)
        xx = np.linspace(0, 1, size, dtype=np.float32)[None, :] * np.ones((size, 1), np.float32)
        wave = np.sin(xx * 12.0) * 0.012
        a = np.clip((yy - lvl - wave) * size * 1.2, 0, 1) * 230
        mol = to_img(np.dstack([col, a]))
        layer.alpha_composite(clip_to(mol, inner))
        # meniscus glow line
        ml = np.clip(1 - np.abs(yy - lvl - wave) * size / 1.6, 0, 1) * 255
        me = to_img(np.dstack([np.full_like(yy, 255), np.full_like(yy, 244), np.full_like(yy, 214), ml]))
        layer.alpha_composite(clip_to(me, inner))
    if cooling:
        ia = np.asarray(icon_img, np.float32).copy()
        lum = ia[..., :3].mean(2, keepdims=True)
        ia[..., :3] = (ia[..., :3] * 0.35 + lum * 0.65) * 0.55
        icon_img = to_img(ia)
    layer.alpha_composite(icon_img, ((size - icon_img.width) // 2, (size - icon_img.height) // 2))
    if cd_left > 0.05:
        sweep = K.conic_sweep(size, cd_left / max(cd_max, 0.01), alpha=0.62)
        layer.alpha_composite(clip_to(sweep, inner))
        f = sans(int(size * 0.3), "Bold")
        draw_text(layer, (size / 2, size / 2 + 1), f"{cd_left:.0f}" if cd_left >= 1 else f"{cd_left:.1f}", f,
                  fill=TOK["parch"], anchor="m", valign="middle", shadow=0.95, shadow_off=(0, 2), shadow_blur=1.5,
                  outline=1)
    if ready:
        glow(img, so, (padd, padd), TOK["ichor_glow"], blur=size * 0.12, opacity=0.8, spread=2)
    img.alpha_composite(layer, (padd, padd))
    if ready:
        # brighter rim
        rim = ImageChops.subtract(diamond(size), diamond(size, 3.4))
        r_img = metal_from_mask(rim, size, size, bevel=1.5, base=0.35, gain=0.8)
        img.alpha_composite(r_img, (padd, padd))
    kc = K.keycap(key, 24, 14) if not pad_key else K.keycap(pad_key, 26, 12, style="pad")
    img.alpha_composite(kc, (W // 2 - kc.width // 2, padd + size - kc.height // 2 - 2))
    return img


def part_socket(size: int, slot_icon: str, rarity: str | None, locked: bool = False) -> Image.Image:
    img = blank(size + 6, size + 6)
    o = 3
    if rarity:
        col = K.RARITY[rarity]
        en = enamel_disc(size, mix(col, "#000000", 0.25), 2.0, light=0.35, dark=0.6)
        img.alpha_composite(en, (o, o))
        if rarity in ("epic", "godforged", "rare"):
            glow(img, en, (o, o), col, blur=size * 0.18, opacity=0.35 if rarity == "rare" else 0.55, spread=1)
            img.alpha_composite(en, (o, o))
        ic = I.render_icon(slot_icon, int(size * 0.74), tint=mix(col, "#FFFFFF", 0.3), light="#FFFBF0", outline=1.0, pad=0.08)
    else:
        rec = lacquer(size, size, top="#0B0706", bot="#1A130F", alpha=0.95, edge_dark=0, sheen=0)
        img.alpha_composite(clip_to(rec, down(disc(size, 2.0), size, size)), (o, o))
        ic = I.render_icon(slot_icon, int(size * 0.74), tint="#6E604E", light="#8D7E68", outline=0.8, pad=0.08)
    img.alpha_composite(ic, (o + (size - ic.width) // 2, o + (size - ic.height) // 2))
    ring = ImageChops.subtract(disc(size), disc(size, 2.2))
    img.alpha_composite(metal_from_mask(ring, size, size, bevel=1.1, rough=0.0), (o, o))
    if locked:
        lk = I.render_icon("lock", 13, tint="#B9A98C", outline=1.0, pad=0.02)
        img.alpha_composite(lk, (size - 6, size - 8))
    return img


def weapon_medallion(size: int, chassis_icon: str, element: str, parts: list[tuple[str, str | None, bool]]) -> Image.Image:
    """Chassis medallion with a crown of four part sockets (Core, Mechanism, Relic, Sigil)."""
    ps = 32
    R = size / 2 + ps * 0.62
    W = int(size + ps * 2 + 24)
    H = int(size + ps * 1.4 + 20)
    img = blank(W, H)
    cx, cy = W - size / 2 - 4, H - size / 2 - 4
    so = K.socket(size, "round", frame=6)
    rg = K.radial_glow(size, size, "#6A4424", opacity=0.45, falloff=1.2)
    so.alpha_composite(clip_to(rg, down(disc(size, 6), size, size)))
    K.paste_shadowed(img, so, (int(cx - size / 2), int(cy - size / 2)), blur=6, offset=(0, 4), opacity=0.7)
    ic = I.render_icon(chassis_icon, int(size * 0.74), tint=K.mix(K.ELEMENT[element], "#C9A86A", 0.5), outline=1.6, pad=0.04)
    img.alpha_composite(ic, (int(cx - ic.width / 2), int(cy - ic.height / 2)))
    # element cabochon (lower-right of bezel)
    eg = gem(26, K.ELEMENT[element], "round")
    a = math.radians(-35)
    img.alpha_composite(eg, (int(cx + math.cos(a) * size * 0.43 - 13), int(cy - math.sin(a) * size * 0.43 - 13)))
    # crown of part sockets
    angles = [70, 96, 122, 148]
    for (icon, rarity, locked), ang in zip(parts, angles):
        t = math.radians(ang)
        x = cx + math.cos(t) * R
        y = cy - math.sin(t) * R
        p = part_socket(ps, icon, rarity, locked)
        K.paste_shadowed(img, p, (int(x - p.width / 2), int(y - p.height / 2)), blur=3, offset=(0, 2), opacity=0.8)
    return img


def overdrive_socket(size: int, frac: float, ready: bool = False) -> Image.Image:
    pad = 16
    img = blank(size + pad * 2, size + pad * 2 + 8)
    so = K.socket(size, "round", frame=3.5)
    inner = down(disc(size, 3.5), size, size)
    yy = np.linspace(0, 1, size, dtype=np.float32)[:, None] * np.ones((1, size), np.float32)
    col = K.ramp(yy, [(0, TOK["molten_hi"]), (0.35, TOK["molten_mid"]), (1.0, TOK["molten_lo"])])
    lvl = 1 - frac
    a = np.clip((yy - lvl) * size, 0, 1) * 200
    so.alpha_composite(clip_to(to_img(np.dstack([col, a])), inner))
    ml = np.clip(1 - np.abs(yy - lvl) * size / 1.4, 0, 1) * 255
    so.alpha_composite(clip_to(to_img(np.dstack([np.full_like(yy, 255), np.full_like(yy, 240), np.full_like(yy, 210), ml])), inner))
    ic = I.render_icon("crucible", int(size * 0.66), tint="#D9B56C", outline=1.3, pad=0.04, dim=1.0 if ready else 0.7)
    so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    if ready:
        glow(img, so, (pad, pad), TOK["ichor_glow"], blur=10, opacity=0.8, spread=2)
    img.alpha_composite(so, (pad, pad))
    kc = K.keycap("V", 22, 13)
    img.alpha_composite(kc, (pad + size // 2 - kc.width // 2, pad + size - kc.height // 2))
    return img


def value_chip(icon: str, value: str, tint: str, size: int = 22) -> Image.Image:
    f = sans(19, "Bold")
    tw, _ = K.text_size(value, f)
    img = blank(size + 8 + tw + 6, size + 4)
    ic = I.render_icon(icon, size, tint=tint, outline=1.1, pad=0.02)
    img.alpha_composite(ic, (0, 2))
    draw_text(img, (size + 6, size / 2 + 3), value, f, fill=TOK["parch"], valign="middle", shadow=0.9,
              shadow_off=(0, 1), shadow_blur=1.2, outline=1)
    return img


def aim_chip(mode: str, note: str) -> Image.Image:
    so = K.socket(30, "round", frame=2.0)
    ic = I.render_icon({"AUTO": "aim_auto", "ASSISTED": "aim_assisted", "MANUAL": "aim_manual"}[mode], 24,
                       tint="#D9B56C", outline=1.0, pad=0.04)
    so.alpha_composite(ic, (3, 3))
    f = cinzel(13, 700)
    f2 = sans(14, "Medium")
    tw, _ = K.text_size(mode, f, 0.6)
    nw, _ = K.text_size(note, f2)
    img = blank(34 + max(tw, nw) + 8, 34)
    img.alpha_composite(so, (0, 2))
    draw_text(img, (36, 14), mode, f, fill=TOK["parch"], tracking=0.6, shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
    draw_text(img, (36, 30), note, f2, fill=TOK["parch_dim"], shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
    return img


def arsenal_hand(st: dict) -> Image.Image:
    W, H = 640, 250
    img = blank(W, H)
    wm = weapon_medallion(118, st["chassis_icon"], st["element"], st["parts"])
    wx, wy = W - wm.width - 2, H - wm.height - 2
    img.alpha_composite(wm, (wx, wy))
    med_cx = wx + wm.width - 118 / 2 - 4
    med_cy = wy + wm.height - 118 / 2 - 4
    # ability row, bottom aligned to the medallion bottom
    base_y = med_cy + 59
    x_right = med_cx - 59 - 10
    sockets = []
    r = ability_socket(94, st["r_icon"], "R", ult=st["ult"], ready=st["ult"] >= 1.0)
    e = ability_socket(80, st["e_icon"], "E", st["cd"][1], st["cdmax"][1], ready=st["cd"][1] <= 0)
    q = ability_socket(80, st["q_icon"], "Q", st["cd"][0], st["cdmax"][0], ready=st["cd"][0] <= 0)
    x = x_right
    for s, size in ((r, 94), (e, 80), (q, 80)):
        x -= s.width - 22 * 2 + 12
        img.alpha_composite(s, (int(x - 22), int(base_y - size - 22)))
        sockets.append(x)
    od = overdrive_socket(64, st["overdrive"], st["overdrive"] >= 1)
    x -= 64 + 16
    img.alpha_composite(od, (int(x - 16), int(base_y - 64 - 16)))
    # info line: aim + wallet, right-aligned above the Q/E row
    chips = [aim_chip(st["aim"], st["aim_note"]), value_chip("godshard", str(st["shards"]), "#BFE8FF"),
             value_chip("ember", str(st["ember"]), "#FFB36B")]
    cx = x - 10
    y = int(base_y - 94 - 60)
    for c in chips:
        img.alpha_composite(c, (int(cx), y + (34 - c.height) // 2))
        cx += c.width + 14
    return img


# ───────────────────────────── party frames ─────────────────────────────
def party_frame(slot: int, name: str, char: str, bust: str, hp: float, ghost: float | None = None,
                ult_ready: bool = False, state: str | None = None, timer: str = "") -> Image.Image:
    W, H = 300, 58
    img = blank(W, H)
    # backdrop: lacquer fading to the right
    bd = lacquer(W, 48, top="#1E1611", bot="#0C0806", alpha=0.78, edge_dark=0.0, sheen=0.05)
    xa = np.clip(1.25 - np.linspace(0, 1, W, dtype=np.float32) * 1.25, 0, 1) ** 0.9
    a = np.asarray(bd.split()[3], np.float32) * xa[None, :]
    bd.putalpha(Image.fromarray(a.astype(np.uint8)))
    img.alpha_composite(bd, (20, 5))
    rule = K.divider(230, 8)
    ra = np.asarray(rule.split()[3], np.float32) * np.clip(1.4 - np.linspace(0, 1.4, 230), 0, 1)[None, :]
    rule.putalpha(Image.fromarray(ra.astype(np.uint8)))
    med = medallion(52, bust, K.PLAYER[slot], bezel=3.5, band=2.5, studs=6)
    K.paste_shadowed(img, med, (2, 3), blur=3, offset=(0, 2), opacity=0.7)
    draw_text(img, (62, 22), name, sans(17, "Medium"), fill=TOK["parch"], shadow=0.9, shadow_off=(0, 1), shadow_blur=1.2)
    nw, _ = K.text_size(name, sans(17, "Medium"))
    draw_text(img, (62 + nw + 8, 22), char.upper(), cinzel(11, 700), fill=TOK["parch_dim"], tracking=1.2, shadow=0.8,
              shadow_off=(0, 1), shadow_blur=1)
    b = K.blade_bar(188, 11, hp, ghost, TOK["hp_lo"], TOK["hp_mid"], TOK["hp_hi"], TOK["hp_ghost"], frame=1.6, point=5)
    img.alpha_composite(b, (60, 31))
    pc = pchip(slot, 18)
    img.alpha_composite(pc, (27 - pc.width // 2 + 2, 44))
    if ult_ready:
        st = I.render_icon("radiant", 18, tint=TOK["ichor"], light="#FFFFFF", outline=0.8, pad=0.0,
                           glow_color=TOK["ichor_glow"], glow_amt=0.8)
        img.alpha_composite(st, (60 + 188 + 4 - 9, 27 - 9))
    if state == "downed":
        sk = I.render_icon("skull", 22, tint="#FF3B30", light="#FFFFFF", outline=1.0, pad=0.0)
        img.alpha_composite(sk, (60 + 190, 26))
    return img


# ───────────────────────────── tracker ─────────────────────────────
def seal_sockets(n: int, filled: int, size: int = 16, gap: int = 4) -> Image.Image:
    W = n * size + (n - 1) * gap + 8
    img = blank(W, size + 8)
    for i in range(n):
        x = 4 + i * (size + gap)
        if i < filled:
            g = gem(size, "#FFD27A", "lozenge")
            glow(img, g, (x, 4), TOK["ichor_glow"], blur=4, opacity=0.6, spread=1)
            img.alpha_composite(g, (x, 4))
        else:
            g = gem(size, "#3A2C20", "lozenge", dim=0.8)
            img.alpha_composite(g, (x, 4))
    return img


def threat_pips(n: int, lit: int, size: int = 16) -> Image.Image:
    img = blank(n * (size - 3) + 8, size + 6)
    for i in range(n):
        if i < lit:
            col = ["#E8A040", "#E88838", "#E0703A", "#D8502E", "#C83024"][i]
            ic = I.render_icon("threat", size, tint=col, light="#FFE3B0", outline=0.9, pad=0.02)
        else:
            ic = I.render_icon("threat", size, tint="#3A2C22", light="#4A3A2C", outline=0.9, pad=0.02)
        img.alpha_composite(ic, (2 + i * (size - 3), 3))
    return img


def bearing_arrow(deg: float, size: int = 14, color: str = TOK["parch_dim"]) -> Image.Image:
    ic = I.render_icon("arrow", size, tint=color, light=K.mix(color, "#FFFFFF", 0.3), outline=0.8, pad=0.05)
    return ic.rotate(-deg, resample=Image.BICUBIC, expand=False)


def tracker_row(icon: str, tint: str, label: str, right: str, deg: float | None = None, W: int = 300,
                sub: str | None = None, progress: float | None = None, bright: bool = False) -> Image.Image:
    H = 30 if not progress else 40
    img = blank(W, H)
    ic = I.render_icon(icon, 22, tint=tint, outline=1.1, pad=0.02, glow_color=tint if bright else None,
                       glow_amt=0.6 if bright else 0)
    img.alpha_composite(ic, (W - 22 - (11 if bright else 0) - (0 if not bright else 0), 4 - (11 if bright else 0)) if False else (W - 24 if not bright else W - 35, 4 if not bright else -7))
    f = sans(16, "Medium")
    draw_text(img, (W - 32, 20), label, f, fill=TOK["parch"] if bright else TOK["parch_dim"], anchor="r",
              shadow=0.95, shadow_off=(0, 1), shadow_blur=1.4, outline=1)
    lw, _ = K.text_size(label, f)
    xr = W - 32 - lw - 10
    if right:
        f2 = sans(15, "Bold")
        draw_text(img, (xr, 20), right, f2, fill=TOK["ichor"] if bright else TOK["parch_dim"], anchor="r", shadow=0.95,
                  shadow_off=(0, 1), shadow_blur=1.2, outline=1)
        rw, _ = K.text_size(right, f2)
        xr -= rw + 6
    if deg is not None:
        ar = bearing_arrow(deg, 15, TOK["ichor"] if bright else TOK["parch_dim"])
        img.alpha_composite(ar, (int(xr - 15), 6))
    if progress is not None:
        b = K.blade_bar(170, 8, progress, None, TOK["molten_lo"], TOK["molten_mid"], TOK["molten_hi"], TOK["hp_ghost"],
                        frame=1.4, point=4)
        img.alpha_composite(b, (W - 32 - 170, 28))
    return img


def minimap(w: int = 256, h: int = 161, content: Image.Image | None = None, me_xy=(0.5, 0.5), allies=()) -> Image.Image:
    panel, (ox, oy) = ornate_panel(w, h, r=6, frame=2.6, corner=44, gem_color="#FFB82E", alpha=0.96,
                                   inner_shadow_px=8, pattern=False)
    if content is not None:
        c = content.resize((w - 10, h - 10), Image.LANCZOS).convert("RGBA")
        ca = np.asarray(c, np.float32).copy()
        # parchment-ink grade: desaturate + warm, vignette edges (fog of war feel)
        lum = ca[..., :3].mean(2, keepdims=True)
        ca[..., :3] = (ca[..., :3] * 0.55 + lum * 0.45) * np.array([1.0, 0.86, 0.66]) * 0.85
        yy, xx = np.mgrid[0:h - 10, 0:w - 10].astype(np.float32)
        vx = np.minimum(xx, w - 11 - xx) / 30
        vy = np.minimum(yy, h - 11 - yy) / 30
        v = np.clip(np.minimum(vx, vy), 0, 1)
        ca[..., :3] *= (0.35 + 0.65 * v)[..., None]
        c = to_img(ca)
        m = down(K.rrect_mask(w - 10, h - 10, 4), w - 10, h - 10)
        panel.alpha_composite(clip_to(c, m), (ox + 5, oy + 5))
        panel.alpha_composite(inner_shadow(w - 10, h - 10, 4, 6, 0.7), (ox + 5, oy + 5))
        # re-draw frame ring over content
        ring = K.ring_mask(w, h, 6, 2.6)
        panel.alpha_composite(metal_from_mask(ring, w, h, bevel=1.4), (ox, oy))
    # me marker + allies
    for (ax, ay, slot) in allies:
        d = I.render_icon("arrow", 14, tint=K.PLAYER[slot], light=K.mix(K.PLAYER[slot], "#FFFFFF", 0.4), outline=1.0, pad=0.0)
        panel.alpha_composite(d, (int(ox + ax * w - 7), int(oy + ay * h - 7)))
    me = I.render_icon("arrow", 18, tint=K.PLAYER[0], light="#FFFFFF", outline=1.2, pad=0.0, glow_color=K.PLAYER[0], glow_amt=0.6)
    panel.alpha_composite(me, (int(ox + me_xy[0] * w - me.width / 2), int(oy + me_xy[1] * h - me.height / 2)))
    # north gem
    ng = gem(14, "#F2E6CE", "lozenge")
    panel.alpha_composite(ng, (ox + w // 2 - 7, oy - 8))
    return panel, (ox, oy)


# ───────────────────────────── callouts, toasts, prompts ─────────────────────────────
def callout(text: str, count: int, elems: list[str], size: int = 36) -> Image.Image:
    f = cinzel(size, 900)
    tw, th = K.text_size(text, f, 3)
    W = tw + 220
    H = size * 2 + 20
    img = blank(W, H)
    cx = W / 2 - 24
    col = K.ELEMENT[elems[0]]
    draw_text(img, (cx, H / 2), text, f, tracking=3, anchor="m", valign="middle", gradient=("#FFFBEF", mix(col, "#FFE3A8", 0.35)),
              outline=2, outline_color="#1A0C06", shadow=0.9, shadow_off=(0, 3), shadow_blur=3,
              glow_color=col, glow_amt=0.75, glow_blur=14)
    # element cabochons flanking with filigree tails
    for i, e in enumerate(elems[:2]):
        g = gem(24, K.ELEMENT[e], "round")
        x = cx - tw / 2 - 40 if i == 0 else cx + tw / 2 + 16
        img.alpha_composite(g, (int(x), int(H / 2 - 12)))
    # count badge
    if count > 1:
        bf = cinzel(22, 800)
        s = f"×{count}"
        bw, _ = K.text_size(s, bf)
        bx = cx + tw / 2 + 50
        plate = blank(bw + 26, 34)
        m = Image.new("L", ((bw + 26) * SS, 34 * SS), 0)
        ImageDraw.Draw(m).polygon([(12 * SS, 0), ((bw + 14) * SS, 0), ((bw + 26) * SS - 1, 17 * SS), ((bw + 14) * SS, 34 * SS - 1),
                                   (12 * SS, 34 * SS - 1), (0, 17 * SS)], fill=255)
        pl = lacquer(bw + 26, 34, top="#3A2A1C", bot="#120C08", alpha=0.95)
        plate.alpha_composite(clip_to(pl, down(m, bw + 26, 34)))
        inner = Image.new("L", ((bw + 26) * SS, 34 * SS), 0)
        k = 2 * SS
        ImageDraw.Draw(inner).polygon([(12 * SS + k, k), ((bw + 14) * SS - k, k), ((bw + 26) * SS - 1 - k * 1.4, 17 * SS),
                                       ((bw + 14) * SS - k, 34 * SS - 1 - k), (12 * SS + k, 34 * SS - 1 - k), (k * 1.4, 17 * SS)], fill=255)
        plate.alpha_composite(metal_from_mask(ImageChops.subtract(m, inner), bw + 26, 34, bevel=1.2))
        draw_text(plate, ((bw + 26) / 2, 18), s, bf, fill=TOK["ichor"], anchor="m", valign="middle", shadow=0.8,
                  shadow_off=(0, 1), shadow_blur=1)
        img.alpha_composite(plate, (int(bx), int(H / 2 - 17)))
    return img


def toast(icon: str, tint: str, parts: list[tuple[str, str]], W: int = 380, accent: str = "#D9B56C") -> Image.Image:
    H = 40
    img = blank(W, H)
    bd = lacquer(W, H - 4, top="#231A14", bot="#0E0A08", alpha=0.82, edge_dark=0.1, sheen=0.08)
    xa = np.clip(1.5 - np.linspace(0, 1.5, W, dtype=np.float32), 0, 1) ** 0.8
    bd.putalpha(Image.fromarray((np.asarray(bd.split()[3], np.float32) * xa[None, :]).astype(np.uint8)))
    img.alpha_composite(bd, (0, 2))
    # left accent: a thin gilt bar with a lozenge
    bar = K.chamfer_mask(4, H - 8, 1.5)
    img.alpha_composite(metal_from_mask(bar, 4, H - 8, bevel=0.8), (0, 4))
    ic = I.render_icon(icon, 26, tint=tint, outline=1.0, pad=0.02)
    img.alpha_composite(ic, (12, 7))
    x = 46
    for s, style in parts:
        f = sans(17, "Bold" if style == "b" else "Regular")
        c = TOK["parch"] if style == "b" else TOK["parch_dim"]
        if style.startswith("#"):
            c = style
            f = sans(17, "Bold")
        draw_text(img, (x, 26), s, f, fill=c, shadow=0.9, shadow_off=(0, 1), shadow_blur=1.2)
        x += K.text_size(s + " ", f)[0] + 1
    return img


def prompt_plate(key: str, verb: str, sub: str | None = None, progress: float | None = None) -> Image.Image:
    fv = cinzel(22, 700)
    vw, _ = K.text_size(verb, fv, 2)
    W = vw + 90
    H = 60 if sub else 48
    img = blank(W + 20, H + 20)
    pan = K.gilded_panel(W, 44, r=6, frame=2.0, corners=0, keyline=False, alpha=0.86)
    K.paste_shadowed(img, pan, (10, 10), blur=6, offset=(0, 3), opacity=0.7)
    kc = K.keycap(key, 28, 16)
    img.alpha_composite(kc, (22, 18))
    if progress is not None:
        am = Image.new("L", (40 * SS, 40 * SS), 0)
        ImageDraw.Draw(am).arc([SS, SS, 39 * SS, 39 * SS], start=-90, end=-90 + 360 * progress, fill=255, width=int(3 * SS))
        a = blank(40, 40, rgba(TOK["ichor"]))
        a.putalpha(down(am, 40, 40))
        img.alpha_composite(a, (16, 12))
    draw_text(img, (64, 40), verb, fv, fill=TOK["parch"], tracking=2, gradient=("#FFF8E8", "#E8CF9C"), shadow=0.9,
              shadow_off=(0, 2), shadow_blur=1.5)
    if sub:
        draw_text(img, (W / 2 + 10, 72), sub, sans(15, "Italic"), fill=TOK["parch_dim"], anchor="m", shadow=0.9,
                  shadow_off=(0, 1), shadow_blur=1.2, outline=1)
    return img


# ───────────────────────────── world-space ─────────────────────────────
def ally_tag(slot: int, hp: float, name: str | None = None) -> Image.Image:
    ch = pchip(slot, 20)
    W = max(ch.width, 60) + (0 if not name else 90)
    img = blank(W + 10, 36)
    x = (W + 10 - ch.width) // 2 if not name else 4
    img.alpha_composite(ch, (x, 0))
    if name:
        draw_text(img, (x + ch.width + 5, 15), name, sans(15, "Medium"), fill=K.PLAYER[slot], shadow=0.95,
                  shadow_off=(0, 1), shadow_blur=1.2, outline=1)
    b = K.blade_bar(48, 7, hp, None, TOK["hp_lo"], TOK["hp_mid"], TOK["hp_hi"], TOK["hp_ghost"], frame=1.2, point=3, sheen=False)
    img.alpha_composite(b, ((W + 10) // 2 - 24 if not name else x + 2, 24))
    return img


def damage_number(value: str, color: str = "#F4E3C1", crit: bool = False) -> Image.Image:
    f = cinzel(34, 900) if crit else sans(24, "Bold")
    tw, _ = K.text_size(value, f)
    img = blank(tw + 60, 70)
    if crit:
        # ichor starburst behind
        sb = I.render_icon("radiant", 44, tint=TOK["ichor_glow"], light="#FFFFFF", outline=0, pad=0.0)
        sb.putalpha(sb.split()[3].point(lambda v: int(v * 0.55)))
        img.alpha_composite(sb, (int(tw / 2 + 30 - 22 + tw / 2 - 6), 4))
        draw_text(img, (30 + tw / 2, 44), value, f, anchor="m", gradient=("#FFFFFF", TOK["ichor_glow"]), outline=2,
                  outline_color="#2A1206", shadow=0.8, shadow_off=(0, 2), shadow_blur=2, glow_color=TOK["ichor_glow"],
                  glow_amt=0.6, glow_blur=8)
    else:
        draw_text(img, (30 + tw / 2, 44), value, f, anchor="m", fill=color, outline=2, outline_color="#140A06",
                  shadow=0.7, shadow_off=(0, 2), shadow_blur=1.5)
    return img


def offscreen_marker(icon: str, tint: str, label: str, dist: str, deg: float, kind: str = "poi") -> Image.Image:
    size = 40
    W, H = 200, 110
    img = blank(W, H)
    cx, cy = W / 2, 40
    # arrow head on the rim pointing toward the target
    ar = I.render_icon("arrow", 22, tint=tint, light=K.mix(tint, "#FFFFFF", 0.5), outline=1.2, pad=0.0)
    ar = ar.rotate(-deg, resample=Image.BICUBIC, expand=True)
    t = math.radians(deg)
    ax = cx + math.sin(t) * (size / 2 + 8)
    ay = cy - math.cos(t) * (size / 2 + 8)
    img.alpha_composite(ar, (int(ax - ar.width / 2), int(ay - ar.height / 2)))
    so = K.socket(size, "round", frame=2.6)
    if kind == "ally":
        band = ImageChops.subtract(disc(size, 2.2), disc(size, 4.6))
        en = enamel_disc(size, tint, 0)
        so.alpha_composite(clip_to(en, down(band, size, size)))
    ic = I.render_icon(icon, int(size * 0.74), tint=tint, outline=1.0, pad=0.02)
    so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2 + (2 if kind == "ally" else 0)))
    K.paste_shadowed(img, so, (int(cx - size / 2), int(cy - size / 2)), blur=3, offset=(0, 2), opacity=0.8)
    draw_text(img, (cx, cy + size / 2 + 20), label, sans(15, "Medium"), fill=TOK["parch"] if kind != "ally" else tint,
              anchor="m", shadow=0.95, shadow_off=(0, 1), shadow_blur=1.3, outline=1)
    draw_text(img, (cx, cy + size / 2 + 37), dist, sans(14, "Bold"), fill=TOK["parch_dim"], anchor="m", shadow=0.95,
              shadow_off=(0, 1), shadow_blur=1.2, outline=1)
    return img
