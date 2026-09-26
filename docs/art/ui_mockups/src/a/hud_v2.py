"""HUD components v2: molten charge fills, bigger sockets, unifying gilt rails, corner shade."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import gmkit as K
import hud_parts as HP
import gm_icons as I
from gmkit import SS, TOK, blank, clip_to, down, draw_text, gem, glow, lacquer, metal_from_mask, mix, rgba, sans, cinzel, to_img
from hud_parts import *  # noqa: F401,F403
from hud_parts import diamond, disc, enamel_disc, part_socket, pchip, armor_plates, aim_chip, value_chip

MOLTEN = [(0.0, "#FFFBEA"), (0.1, "#FFEDB0"), (0.35, "#FFC95A"), (0.7, "#E8942E"), (1.0, "#7A3E12")]


def molten(size_w: int, size_h: int, frac: float, mask: Image.Image, wave: float = 0.012, glow_line: bool = True,
           lo: float = 0.08, hi: float = 0.92) -> Image.Image:
    """Molten white-gold rising in a mould: gradient body, bright meniscus, faint heat shimmer."""
    yy = np.linspace(0, 1, size_h, dtype=np.float32)[:, None] * np.ones((1, size_w), np.float32)
    xx = np.linspace(0, 1, size_w, dtype=np.float32)[None, :] * np.ones((size_h, 1), np.float32)
    lvl = 1 - (lo + (hi - lo) * frac)
    wv = np.sin(xx * 11.0 + 0.7) * wave + np.sin(xx * 23.0) * wave * 0.4
    depth = np.clip((yy - lvl - wv) / max(1e-3, 1 - lvl), 0, 1)
    col = K.ramp(depth, MOLTEN)
    # heat shimmer
    n = K.noise(size_h, size_w, 3.0, seed=5)
    col += (n * 16)[..., None]
    if frac < 1.0:
        col *= 0.8  # still charging: a deeper, cooler pour; full = white-hot
    a = np.clip((yy - lvl - wv) * size_h * 1.3, 0, 1) * 250
    out = to_img(np.dstack([col, a]))
    if glow_line:
        ml = np.clip(1 - np.abs(yy - lvl - wv) * size_h / 1.8, 0, 1) * 255
        me = to_img(np.dstack([np.full_like(yy, 255), np.full_like(yy, 250), np.full_like(yy, 232), ml]))
        out.alpha_composite(me)
    return clip_to(out, mask)


def corner_shade(w: int, h: int, corner: str, opacity: float = 0.55) -> Image.Image:
    """Soft radial shade behind a corner cluster (readability over lava / bright VFX)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = 0 if "l" in corner else w
    cy = h if "b" in corner else 0
    r = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    a = np.clip(1 - r, 0, 1) ** 1.6 * opacity * 255
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = K.rgb("#07040A")
    out[..., 3] = a
    return to_img(out)


def medallion(size: int, bust: str, pcolor: str | None, bezel: float = 6.0, band: float = 4.0,
              studs: int = 8, glow_col: str = "#5A3A20", arc=None) -> Image.Image:
    img = blank(size, size)
    inner_inset = bezel + (band + 1.2 if pcolor else 0)
    win = down(disc(size, inner_inset), size, size)
    body = lacquer(size, size, top="#2E231B", bot="#0B0706", alpha=1.0, edge_dark=0.7, sheen=0.12)
    rg = K.radial_glow(size, size, glow_col, opacity=0.6, falloff=1.3)
    body.alpha_composite(rg, (0, -int(size * 0.14)))
    bi = I.render_icon(bust, int(size * 0.92), tint="#B08A52", light="#F8EBD0", outline=1.4, pad=0.02)
    body.alpha_composite(bi, ((size - bi.width) // 2, int(size * 0.14)))
    img.alpha_composite(clip_to(body, win))
    # inner shadow ring on the window
    sh = ImageChops.subtract(disc(size, inner_inset), disc(size, inner_inset + 5))
    shi = blank(size, size, rgba("#000000"))
    shi.putalpha(down(sh, size, size).filter(ImageFilter.GaussianBlur(2)).point(lambda v: int(v * 0.7)))
    img.alpha_composite(clip_to(shi, win))
    if pcolor:
        band_m = ImageChops.subtract(disc(size, bezel - 0.5), disc(size, bezel + band))
        en = enamel_disc(size, pcolor, 0, light=0.5, dark=0.3)
        img.alpha_composite(clip_to(en, down(band_m, size, size)))
        sep = ImageChops.subtract(disc(size, bezel + band), disc(size, bezel + band + 1.2))
        sp = blank(size, size, rgba("#140B06"))
        sp.putalpha(down(sep, size, size))
        img.alpha_composite(sp)
    if arc:
        frac, col = arc
        am = Image.new("L", (size * SS, size * SS), 0)
        i = (inner_inset + 2) * SS
        ImageDraw.Draw(am).arc([i, i, size * SS - 1 - i, size * SS - 1 - i], start=-90, end=-90 + 360 * frac, fill=255,
                               width=int(3 * SS))
        a_img = blank(size, size, rgba(col))
        a_img.putalpha(down(am, size, size))
        img.alpha_composite(a_img)
    ring = ImageChops.subtract(disc(size), disc(size, bezel))
    img.alpha_composite(metal_from_mask(ring, size, size, bevel=bezel * 0.5, rough=0.03))
    for k in range(studs):
        a = k * 2 * math.pi / studs + math.pi / studs
        r = size / 2 - bezel / 2
        s = max(5, int(bezel * 1.1))
        st = gem(s, "#E9D3A0", "lozenge", dim=0.85)
        img.alpha_composite(st, (int(size / 2 + math.cos(a) * r - s / 2), int(size / 2 + math.sin(a) * r - s / 2)))
    return img


HP.medallion = medallion


def dash_pip(frac: float, w: int = 20, h: int = 26) -> Image.Image:
    pad = 6
    img = blank(w + pad * 2, h + pad * 2)
    S = SS
    m = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(m).polygon([(w * S / 2, 0), (w * S - 1, h * S / 2), (w * S / 2, h * S - 1), (0, h * S / 2)], fill=255)
    inner = Image.new("L", (w * S, h * S), 0)
    k = 2.6 * S
    ImageDraw.Draw(inner).polygon([(w * S / 2, k * 1.3), (w * S - 1 - k, h * S / 2), (w * S / 2, h * S - 1 - k * 1.3), (k, h * S / 2)], fill=255)
    ins = down(inner, w, h)
    layer = blank(w, h)
    layer.alpha_composite(clip_to(lacquer(w, h, top="#050302", bot="#140E0B", alpha=0.95, edge_dark=0, sheen=0), ins))
    if frac >= 1:
        f = molten(w, h, 1.0, ins, wave=0, glow_line=False, lo=0, hi=1)
        layer.alpha_composite(f)
    elif frac > 0:
        f = molten(w, h, frac, ins, wave=0, lo=0, hi=1)
        fa = np.asarray(f, np.float32).copy()
        fa[..., :3] *= 0.55
        layer.alpha_composite(to_img(fa))
    layer.alpha_composite(metal_from_mask(ImageChops.subtract(m, inner), w, h, bevel=1.1, rough=0.0))
    if frac >= 1:
        glow(img, layer, (pad, pad), TOK["ichor_glow"], blur=4, opacity=0.6, spread=1)
    img.alpha_composite(layer, (pad, pad))
    return img


def buff_icon(name: str, frac_left: float, secs: str, size: int = 36, tint: str = "#D9B56C") -> Image.Image:
    img = blank(size, size)
    so = K.socket(size, "round", frame=2.4)
    img.alpha_composite(so)
    ic = I.render_icon(name, int(size * 0.66), tint=tint, outline=1.0, pad=0.08, dim=0.8)
    img.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2 - 3))
    am = Image.new("L", (size * SS, size * SS), 0)
    i = 1.2 * SS
    ImageDraw.Draw(am).arc([i, i, size * SS - 1 - i, size * SS - 1 - i], start=-90, end=-90 + 360 * frac_left,
                           fill=255, width=int(2.4 * SS))
    ar = blank(size, size, rgba(TOK["ichor"]))
    ar.putalpha(down(am, size, size))
    img.alpha_composite(ar)
    draw_text(img, (size / 2, size - 7), secs, sans(12, "Bold"), fill=TOK["parch"], anchor="m", shadow=0.9,
              shadow_off=(0, 1), shadow_blur=0.8, outline=1)
    return img


def rail(w: int, h: int = 10) -> Image.Image:
    """A thin gilt rail with tapered ends tying a cluster together."""
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    cy = h * SS / 2
    K.taper_stroke(d, [(x, cy) for x in range(int(w * SS * 0.5), int(w * SS) - 2 * SS, 2)], 1.6 * SS, 0.3 * SS)
    K.taper_stroke(d, [(x, cy) for x in range(int(w * SS * 0.5), 2 * SS, -2)], 1.6 * SS, 0.3 * SS)
    return metal_from_mask(m, w, h, bevel=0.8, rough=0.0)


def hero_cluster(st: dict) -> Image.Image:
    W, H = 600, 176
    img = blank(W, H)
    M = 124
    mx, my = 8, H - M - 8
    bar_x, bar_w, bar_h = mx + M - 18, 350, 28
    bar_y = my + M // 2 - 6
    if st.get("armor_max", 0) > 0:
        pl = armor_plates(10, st["armor"] / st["armor_max"], w=29, h=9)
        img.alpha_composite(pl, (bar_x + 26, bar_y - 14))
    hp = st["hp"] / st["max_hp"]
    shield = st.get("shield", 0) / st["max_hp"]
    b = K.blade_bar(bar_w, bar_h, hp, st.get("ghost", hp), TOK["hp_lo"], TOK["hp_mid"], TOK["hp_hi"], TOK["hp_ghost"],
                    frame=2.6, label=f'{int(st["hp"])} / {int(st["max_hp"])}', label_font=sans(18, "Bold"))
    K.paste_shadowed(img, b, (bar_x, bar_y), blur=4, offset=(0, 3), opacity=0.75)
    x = bar_x + 20
    y = bar_y + bar_h - 1
    for i in range(st["max_dash"]):
        f = 1.0 if i < st["dash"] else st.get("dash_recharge", 0.0) if i == st["dash"] else 0.0
        p = dash_pip(f)
        img.alpha_composite(p, (x, y))
        x += 24
    if st.get("buffs"):
        x += 14
        for (name, frac, secs) in st["buffs"]:
            bi = buff_icon(name, frac, secs, 36)
            K.paste_shadowed(img, bi, (x, y + 2), blur=2, offset=(0, 1), opacity=0.7)
            x += 42
    med = medallion(M, st["bust"], K.PLAYER[st["slot"]], arc=st.get("passive_arc"))
    K.paste_shadowed(img, med, (mx, my), blur=7, offset=(0, 5), opacity=0.8)
    ch = pchip(st["slot"], 24)
    img.alpha_composite(ch, (mx + M // 2 - ch.width // 2, my + M - ch.height + 8))
    return img


def ability_socket(size: int, icon: str, key: str, cd_left: float = 0.0, cd_max: float = 1.0, ult: float | None = None,
                   ready: bool = False, tint: str = "#D9B56C", pad_key: str | None = None) -> Image.Image:
    padd = 24
    W = size + padd * 2
    img = blank(W, W + 8)
    frame = 3.4 if size > 90 else 3.0
    so = K.socket(size, "diamond", frame=frame)
    inner = down(diamond(size, frame + 0.2), size, size)
    layer = blank(size, size)
    layer.alpha_composite(so)
    rg = K.radial_glow(size, size, "#5A3A20", opacity=0.5, falloff=1.2)
    layer.alpha_composite(clip_to(rg, inner))
    icon_img = I.render_icon(icon, int(size * 0.6), tint=tint, outline=1.5, pad=0.04)
    cooling = cd_left > 0.05 or (ult is not None and ult < 1.0)
    if ult is not None and ult < 1.0:
        layer.alpha_composite(molten(size, size, ult, inner, lo=0.12, hi=0.88))
    if cooling:
        ia = np.asarray(icon_img, np.float32).copy()
        lum = ia[..., :3].mean(2, keepdims=True)
        ia[..., :3] = (ia[..., :3] * 0.3 + lum * 0.7) * (0.5 if ult is None else 0.62)
        icon_img = to_img(ia)
    layer.alpha_composite(icon_img, ((size - icon_img.width) // 2, (size - icon_img.height) // 2))
    if cd_left > 0.05:
        sweep = K.conic_sweep(size, cd_left / max(cd_max, 0.01), alpha=0.66, edge=None)
        layer.alpha_composite(clip_to(sweep, inner))
        # bright sweep edge
        done = 1 - cd_left / max(cd_max, 0.01)
        th = done * 2 * math.pi
        em = Image.new("L", (size * SS, size * SS), 0)
        c = size * SS / 2
        ImageDraw.Draw(em).line([(c, c), (c + math.sin(th) * size * SS, c - math.cos(th) * size * SS)], fill=255,
                                width=int(2.2 * SS))
        ed = blank(size, size, rgba(TOK["ichor"]))
        ed.putalpha(ImageChops.multiply(down(em, size, size), inner))
        layer.alpha_composite(ed)
        f = sans(int(size * 0.34), "Bold")
        draw_text(layer, (size / 2, size / 2 + 1), f"{cd_left:.0f}" if cd_left >= 1 else f"{cd_left:.1f}", f,
                  fill=TOK["parch"], anchor="m", valign="middle", shadow=0.95, shadow_off=(0, 2), shadow_blur=1.5,
                  outline=2)
    if ready:
        glow(img, so, (padd, padd), TOK["ichor_glow"], blur=size * 0.14, opacity=0.85, spread=2)
    img.alpha_composite(layer, (padd, padd))
    if ready:
        rim = ImageChops.subtract(diamond(size), diamond(size, frame))
        img.alpha_composite(metal_from_mask(rim, size, size, bevel=1.5, base=0.4, gain=0.8), (padd, padd))
    kc = K.keycap(key, 26, 15) if not pad_key else K.keycap(pad_key, 28, 12, style="pad")
    img.alpha_composite(kc, (W // 2 - kc.width // 2, padd + size - kc.height // 2 - 1))
    return img


def weapon_medallion(size: int, chassis_icon: str, element: str, parts, ps: int = 38) -> tuple[Image.Image, tuple[float, float]]:
    R = size / 2 + ps * 0.6
    W = int(size + ps * 2.2 + 24)
    H = int(size + ps * 1.5 + 20)
    img = blank(W, H)
    cx, cy = W - size / 2 - 6, H - size / 2 - 6
    so = K.socket(size, "round", frame=6.5)
    rg = K.radial_glow(size, size, "#6A4424", opacity=0.55, falloff=1.2)
    so.alpha_composite(clip_to(rg, down(disc(size, 6.5), size, size)))
    ic = I.render_icon(chassis_icon, int(size * 0.72), tint=mix(K.ELEMENT[element], "#C9A86A", 0.5), outline=1.6, pad=0.04)
    so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    K.paste_shadowed(img, so, (int(cx - size / 2), int(cy - size / 2)), blur=7, offset=(0, 5), opacity=0.8)
    eg = gem(28, K.ELEMENT[element], "round")
    a = math.radians(-40)
    img.alpha_composite(eg, (int(cx + math.cos(a) * size * 0.44 - 14), int(cy - math.sin(a) * size * 0.44 - 14)))
    angles = [72, 99, 126, 153]
    for (icon, rarity, locked), ang in zip(parts, angles):
        t = math.radians(ang)
        p = part_socket(ps, icon, rarity, locked)
        K.paste_shadowed(img, p, (int(cx + math.cos(t) * R - p.width / 2), int(cy - math.sin(t) * R - p.height / 2)),
                         blur=3, offset=(0, 2), opacity=0.8)
    return img, (cx, cy)


def overdrive_socket(size: int, frac: float, ready: bool = False) -> Image.Image:
    pad = 18
    img = blank(size + pad * 2, size + pad * 2 + 8)
    so = K.socket(size, "round", frame=3.6)
    inner = down(disc(size, 3.6), size, size)
    so.alpha_composite(molten(size, size, frac, inner, lo=0.0, hi=1.0))
    ic = I.render_icon("crucible", int(size * 0.64), tint="#C9A86A", outline=1.4, pad=0.04)
    if not ready:
        ia = np.asarray(ic, np.float32).copy()
        ia[..., :3] *= 0.8
        ic = to_img(ia)
    so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2 - 2))
    if ready:
        glow(img, so, (pad, pad), TOK["ichor_glow"], blur=12, opacity=0.9, spread=2)
    img.alpha_composite(so, (pad, pad))
    kc = K.keycap("V", 24, 14)
    img.alpha_composite(kc, (pad + size // 2 - kc.width // 2, pad + size - kc.height // 2))
    return img


def arsenal_hand(st: dict) -> Image.Image:
    W, H = 720, 280
    img = blank(W, H)
    wm, (mcx, mcy) = weapon_medallion(128, st["chassis_icon"], st["element"], st["parts"])
    wx, wy = W - wm.width - 2, H - wm.height - 2
    med_cx, med_cy = wx + mcx, wy + mcy
    base_y = med_cy + 64
    # gilt rail behind the row
    rl = rail(470, 12)
    img.alpha_composite(rl, (int(med_cx - 64 - 440), int(base_y - 50 - 6)))
    img.alpha_composite(wm, (wx, wy))
    x = med_cx - 64 - 6
    for icon, key, size, kw in (("R", "R", 104, dict(ult=st["ult"], ready=st["ult"] >= 1.0)),
                                ("E", "E", 86, dict(cd_left=st["cd"][1], cd_max=st["cdmax"][1], ready=st["cd"][1] <= 0)),
                                ("Q", "Q", 86, dict(cd_left=st["cd"][0], cd_max=st["cdmax"][0], ready=st["cd"][0] <= 0))):
        ic = {"R": st["r_icon"], "E": st["e_icon"], "Q": st["q_icon"]}[icon]
        s = ability_socket(size, ic, key, **kw)
        x -= size + 6
        img.alpha_composite(s, (int(x - 24), int(base_y - 50 - size / 2 - 24)))
    od = overdrive_socket(68, st["overdrive"], st["overdrive"] >= 1)
    x -= 68 + 14
    img.alpha_composite(od, (int(x - 18), int(base_y - 50 - 34 - 18)))
    chips = [aim_chip(st["aim"], st["aim_note"]), value_chip("godshard", str(st["shards"]), "#BFE8FF"),
             value_chip("ember", str(st["ember"]), "#FFB36B")]
    total = sum(c.width for c in chips) + 16 * (len(chips) - 1)
    cx = med_cx - 64 - 20 - total
    y = int(base_y - 50 - 52 - 50)
    for c in chips:
        img.alpha_composite(c, (int(cx), y + (34 - c.height) // 2))
        cx += c.width + 16
    return img
