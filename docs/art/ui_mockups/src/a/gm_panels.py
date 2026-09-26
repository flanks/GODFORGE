"""GILDED MYTHIC panels: buttons, rarity tiles, Forge slot rows, boon cards."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import gmkit as K
import hud_v2 as H
import gm_icons as I
from gmkit import SS, TOK, blank, clip_to, down, draw_text, gem, glow, lacquer, metal_from_mask, mix, rgba, sans, cinzel, to_img
from gmorn import corner_v2_mask, crest_img, inner_shadow, leaf, lattice, ornate_panel

RARITY_NAME = {"common": "COMMON", "rare": "RARE", "epic": "EPIC", "godforged": "GODFORGED"}


def delta_arrow(up: bool, size: int = 12) -> Image.Image:
    m = Image.new("L", (size * SS, size * SS), 0)
    S = size * SS
    if up:
        ImageDraw.Draw(m).polygon([(S / 2, S * 0.12), (S * 0.92, S * 0.84), (S * 0.08, S * 0.84)], fill=255)
    else:
        ImageDraw.Draw(m).polygon([(S / 2, S * 0.88), (S * 0.92, S * 0.16), (S * 0.08, S * 0.16)], fill=255)
    img = blank(size, size, rgba(TOK["ichor"] if up else TOK["ash_rose"]))
    img.putalpha(down(m, size, size))
    return img


def delta_text(dst, xy, pct: float, font=None):
    font = font or sans(18, "Bold")
    up = pct >= 0
    a = delta_arrow(up, 13)
    dst.alpha_composite(a, (int(xy[0]), int(xy[1] - 11)))
    return draw_text(dst, (xy[0] + 17, xy[1]), f"{pct:+.0f}%", font, fill=TOK["ichor"] if up else TOK["ash_rose"],
                     shadow=0.9, shadow_off=(0, 1), shadow_blur=1.2)


def button(w: int, h: int, label: str, icon: str | None = None, state: str = "idle", sub: str | None = None,
           key: str | None = None, sub_color: str | None = None) -> Image.Image:
    """Gilded chamfer button. state: idle | hover | primary | disabled | pressed."""
    pad = 14
    img = blank(w + pad * 2, h + pad * 2)
    top, bot = {"idle": ("#2C2119", "#120C09"), "hover": ("#3E2E20", "#1A120C"), "primary": ("#4A3320", "#1C120A"),
                "disabled": ("#1A1512", "#0E0B09"), "pressed": ("#140E0B", "#1E1510")}[state]
    m = K.chamfer_mask(w, h, 9)
    body = lacquer(w, h, top=top, bot=bot, alpha=0.97, edge_dark=0.25, sheen=0.12 if state != "pressed" else 0.0)
    layer = blank(w, h)
    layer.alpha_composite(clip_to(body, down(m, w, h)))
    ring = ImageChops.subtract(m, K.chamfer_mask(w, h, 9, inset=2.2))
    stops = K.GOLD_RAMP if state != "disabled" else K.BRONZE_RAMP
    rim = metal_from_mask(ring, w, h, bevel=1.3, stops=stops, rough=0.0,
                          base=0.3 if state in ("hover", "primary") else 0.12)
    layer.alpha_composite(rim)
    if state in ("primary", "hover"):
        glow(img, layer, (pad, pad), TOK["ichor_glow"], blur=8, opacity=0.55 if state == "primary" else 0.35, spread=1)
    img.alpha_composite(layer, (pad, pad))
    x = pad + 16
    tc = TOK["parch"] if state != "disabled" else TOK["parch_faint"]
    if icon:
        ic = I.render_icon(icon, h - 18, tint="#D9B56C" if state != "disabled" else "#6E604E", outline=1.1, pad=0.04,
                           dim=1.0 if state != "disabled" else 0.6)
        img.alpha_composite(ic, (x, pad + 9))
        x += h - 18 + 10
    f = cinzel(17, 700)
    ty = pad + (h / 2 + 1 if not sub else h / 2 - 7)
    draw_text(img, (x, ty), label, f, fill=tc, tracking=1.6, valign="middle", shadow=0.9, shadow_off=(0, 1),
              shadow_blur=1.2)
    if sub:
        draw_text(img, (x, pad + h / 2 + 13), sub, sans(15, "Medium"), fill=sub_color or TOK["parch_dim"], valign="middle",
                  shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
    if key:
        kc = K.keycap(key, 24, 13)
        img.alpha_composite(kc, (pad + w - kc.width - 12, pad + (h - kc.height) // 2 + 1))
    return img


def rarity_frame(w: int, h: int, rarity: str | None, selected: bool = False, r: int = 8) -> Image.Image:
    """A tile/card frame with the rarity treatment: common plain bronze, rare blue gems, epic violet corner
    gems + filigree, godforged radiant gold with rays. Returns a transparent frame layer (+ glow)."""
    pad = 16
    img = blank(w + pad * 2, h + pad * 2)
    layer = blank(w, h)
    stops = K.BRONZE_RAMP if rarity in (None, "common") else K.GOLD_RAMP
    frame = 2.4 if rarity in (None, "common") else 3.0
    ring = K.ring_mask(w, h, r, frame)
    layer.alpha_composite(metal_from_mask(ring, w, h, bevel=frame * 0.55, stops=stops, rough=0.02))
    if rarity and rarity != "common":
        col = K.RARITY[rarity]
        # enamel hairline inside the frame
        hl = K.ring_mask(w, h, max(0, r - 2), 1.6, inset=frame + 1.5)
        e = blank(w, h, rgba(col, 0.9))
        e.putalpha(down(hl, w, h).point(lambda v: int(v * 0.9)))
        layer.alpha_composite(e)
        gs = 14 if rarity == "rare" else 13
        g = gem(gs, col)
        if rarity == "rare":
            for (x, y) in ((w // 2 - gs // 2, -gs // 2 + 1), (w // 2 - gs // 2, h - gs // 2 - 1)):
                layer.alpha_composite(g, (x, y))
        else:
            for (x, y) in ((-3, -3), (w - gs + 3, -3), (-3, h - gs + 3), (w - gs + 3, h - gs + 3)):
                layer.alpha_composite(g, (x, y))
        if rarity == "godforged":
            cr = crest_img(34, col)
            layer.alpha_composite(cr, (w // 2 - cr.width // 2, -int(cr.height * 0.62)))
    if selected:
        sel = K.ring_mask(w + 8, h + 8, r + 4, 2.4)
        s_img = blank(w + 8, h + 8, rgba(TOK["ichor"]))
        s_img.putalpha(down(sel, w + 8, h + 8))
        glow(img, s_img, (pad - 4, pad - 4), TOK["ichor_glow"], blur=8, opacity=0.8, spread=1)
        img.alpha_composite(s_img, (pad - 4, pad - 4))
    img.alpha_composite(layer, (pad, pad))
    return img, pad


def part_tile(size: int, name: str, slot_icon: str, rarity: str | None, element: str | None = None,
              selected: bool = False, empty: bool = False, recipe: bool = False) -> Image.Image:
    fr, pad = rarity_frame(size, size + 22, None if empty else rarity, selected)
    W, Hh = fr.size
    img = blank(W, Hh)
    body_top = "#2A1F18" if not empty else "#120D0A"
    body = lacquer(size, size + 22, top=body_top, bot="#0B0706", alpha=0.95, edge_dark=0.4, sheen=0.1)
    m = down(K.rrect_mask(size, size + 22, 8), size, size + 22)
    if not empty and rarity and rarity != "common":
        rg = K.radial_glow(size, size, K.RARITY[rarity], opacity=0.34 if rarity != "godforged" else 0.6, falloff=1.4)
        body.alpha_composite(rg, (0, -10))
    if not empty and rarity == "godforged":
        sb = K.sunburst(size, size // 2 + 10)
        sb.putalpha(sb.split()[3].point(lambda v: int(v * 0.55)))
        body.alpha_composite(sb, (0, 8))
    img.alpha_composite(clip_to(body, m), (pad, pad))
    if selected:
        sb = blank(size, size + 22, rgba(TOK["ichor_glow"], 0.08))
        img.alpha_composite(clip_to(sb, m), (pad, pad))
    if not empty:
        tint = mix(K.RARITY[rarity or "common"], "#E8D8B8", 0.45)
        ic = I.render_icon(slot_icon, int(size * 0.56), tint=tint, light="#FFF8EA", outline=1.4, pad=0.04)
        img.alpha_composite(ic, (pad + (size - ic.width) // 2, pad + 10))
        if element:
            eg = gem(22, K.ELEMENT[element], "round")
            img.alpha_composite(eg, (pad + size - 28, pad + 6))
        f = sans(14, "Medium")
        nm = name if K.text_size(name, f)[0] < size - 12 else name[: max(3, int(len(name) * (size - 18) / K.text_size(name, f)[0]))] + "…"
        draw_text(img, (pad + size / 2, pad + size + 10), nm, f, fill=K.RARITY[rarity or "common"] if rarity != "common" else TOK["parch"],
                  anchor="m", shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
        if recipe:
            rb = I.render_icon("radiant", 20, tint=TOK["ichor"], light="#FFFFFF", outline=0.8, pad=0.0,
                               glow_color=TOK["ichor_glow"], glow_amt=0.8)
            img.alpha_composite(rb, (pad - 4, pad - 4))
    else:
        dm = I.render_icon("godshard", 26, tint="#3A2E24", light="#4A3C30", outline=0.6, pad=0.1)
        img.alpha_composite(dm, (pad + size // 2 - 13, pad + size // 2 - 4))
    img.alpha_composite(fr)
    return img


def section_header(text: str, W: int, right: str | None = None) -> Image.Image:
    img = blank(W, 30)
    f = cinzel(15, 700)
    draw_text(img, (2, 20), text, f, fill=TOK["parch_dim"], tracking=3, shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
    tw = K.text_size(text, f, 3)[0]
    dv = K.divider(W - tw - 30 - (K.text_size(right, sans(16, "Bold"))[0] + 16 if right else 0), 10)
    img.alpha_composite(dv, (tw + 16, 12))
    if right:
        draw_text(img, (W - 2, 20), right, sans(16, "Bold"), fill=TOK["parch_dim"], anchor="r", shadow=0.9,
                  shadow_off=(0, 1), shadow_blur=1)
    return img


def slot_row(W: int, slot_label: str, slot_icon: str, name: str, rarity: str | None, desc: str,
             element: str | None = None, locked: bool = False, action: Image.Image | None = None,
             highlight: str | None = None) -> Image.Image:
    Hh = 96
    img = blank(W, Hh)
    # soft plate
    pl = lacquer(W, Hh - 8, top="#211813", bot="#130D0A", alpha=0.72, edge_dark=0.2, sheen=0.06)
    img.alpha_composite(clip_to(pl, down(K.rrect_mask(W, Hh - 8, 8), W, Hh - 8)), (0, 4))
    if highlight:
        hl = K.ring_mask(W, Hh - 8, 8, 1.6)
        h_img = blank(W, Hh - 8, rgba(highlight, 0.9))
        h_img.putalpha(down(hl, W, Hh - 8))
        img.alpha_composite(h_img, (0, 4))
    ps = H.part_socket(70, slot_icon, rarity, locked)
    img.alpha_composite(ps, (10, (Hh - ps.height) // 2))
    if rarity in ("rare", "epic", "godforged"):
        pass
    x = 96
    draw_text(img, (x, 30), slot_label, cinzel(12, 700), fill=TOK["parch_faint"], tracking=2.4, shadow=0.8,
              shadow_off=(0, 1), shadow_blur=1)
    lw = K.text_size(slot_label, cinzel(12, 700), 2.4)[0]
    if rarity:
        rg = gem(11, K.RARITY[rarity])
        img.alpha_composite(rg, (x + lw + 10, 20))
        draw_text(img, (x + lw + 26, 30), RARITY_NAME[rarity], cinzel(11, 700), fill=K.RARITY[rarity], tracking=1.8,
                  shadow=0.8, shadow_off=(0, 1), shadow_blur=1)
    col = K.RARITY[rarity] if rarity and rarity != "common" else TOK["parch"]
    draw_text(img, (x, 56), name, cinzel(21, 700), fill=col, shadow=0.9, shadow_off=(0, 2), shadow_blur=1.5)
    if element:
        nw = K.text_size(name, cinzel(21, 700))[0]
        eg = gem(18, K.ELEMENT[element], "round")
        img.alpha_composite(eg, (x + nw + 8, 40))
    draw_text(img, (x, 80), desc, sans(16, "Italic"), fill=TOK["parch_dim"], shadow=0.9, shadow_off=(0, 1), shadow_blur=1)
    if locked:
        lk = I.render_icon("lock", 20, tint="#B9A98C", outline=1.0, pad=0.02)
        img.alpha_composite(lk, (W - 104, 26))
        draw_text(img, (W - 80, 42), "LOCKED", cinzel(12, 700), fill=TOK["parch_faint"], tracking=1.8,
                  shadow=0.8, shadow_off=(0, 1), shadow_blur=1)
        draw_text(img, (W - 100, 62), "for this run", sans(13, "Italic"), fill=TOK["parch_faint"], shadow=0.8)
    elif action is not None:
        img.alpha_composite(action, (W - action.width + 6, (Hh - action.height) // 2))
    return img


# ───────────────────────────── boon cards ─────────────────────────────
def god_medallion(size: int, gods: list[str], kind: str = "Standard") -> Image.Image:
    img = blank(size + 40, size + 40)
    o = 20
    so = K.socket(size, "round", frame=5.5)
    inner = down(H.disc(size, 5.5), size, size)
    if len(gods) == 1:
        name, c1, c2, _ = K.GODS[gods[0]]
        en = H.enamel_disc(size, mix(c1, "#000000", 0.55), 5.5, light=0.25, dark=0.6)
        so.alpha_composite(en)
        rg = K.radial_glow(size, size, c1, opacity=0.55, falloff=1.6)
        so.alpha_composite(clip_to(rg, inner))
        ic = I.render_icon(gods[0], int(size * 0.66), tint=c1, light=mix(c1, "#FFFFFF", 0.7), outline=1.6, pad=0.02)
        so.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    else:
        # duo: split medallion, each half its god
        for i, gk in enumerate(gods[:2]):
            name, c1, c2, _ = K.GODS[gk]
            half = Image.new("L", (size, size), 0)
            ImageDraw.Draw(half).rectangle([0 if i == 0 else size // 2, 0, size // 2 if i == 0 else size, size], fill=255)
            en = H.enamel_disc(size, mix(c1, "#000000", 0.5), 5.5, light=0.25, dark=0.6)
            so.alpha_composite(clip_to(en, half))
            ic = I.render_icon(gk, int(size * 0.44), tint=c1, light=mix(c1, "#FFFFFF", 0.7), outline=1.4, pad=0.02)
            so.alpha_composite(ic, (int(size * (0.26 if i == 0 else 0.74) - ic.width / 2), (size - ic.height) // 2))
        ln = Image.new("L", (size * SS, size * SS), 0)
        K.taper_stroke(ImageDraw.Draw(ln), [(size * SS / 2, y) for y in range(0, size * SS, 2)], 1.4 * SS, 1.4 * SS)
        so.alpha_composite(metal_from_mask(ln, size, size, bevel=0.8))
    ring = ImageChops.subtract(H.disc(size), H.disc(size, 5.5))
    so.alpha_composite(metal_from_mask(ring, size, size, bevel=2.6, rough=0.03))
    if kind == "Legendary":
        cr = crest_img(int(size * 0.5), "#FFB82E")
        img.alpha_composite(cr, (o + size // 2 - cr.width // 2, o - int(cr.height * 0.55)))
    K.paste_shadowed(img, so, (o, o), blur=6, offset=(0, 4), opacity=0.8)
    return img


def rich_desc(dst, cx, y, text: str, W: int, size: int = 19):
    """Centered description; tokens wrapped in [] render in ichor bold (numbers, keywords).
    Punctuation right after a token stays glued to it (no stray space)."""
    f = sans(size, "Regular")
    fb = sans(size, "Bold")
    # words are lists of runs [(text, bold)] rendered without spaces between runs
    words: list[list[tuple[str, bool]]] = []
    glue = False
    for part in text.replace("[", "\x00[").replace("]", "]\x00").split("\x00"):
        if not part:
            continue
        bold = part.startswith("[")
        body = part.strip("[]") if bold else part
        toks = body.split(" ")
        for k, tkn in enumerate(toks):
            if tkn == "":
                glue = False
                continue
            if k == 0 and glue and words:
                words[-1].append((tkn, bold))
            else:
                words.append([(tkn, bold)])
            glue = True
        glue = not body.endswith(" ")

    def wlen(word):
        return sum(K.text_size(t, fb if b else f)[0] for t, b in word)

    sp = K.text_size(" ", f)[0] + 3
    lines, cur, cw = [], [], 0
    for w in words:
        ww = wlen(w) + sp
        if cw + ww > W and cur:
            lines.append(cur)
            cur, cw = [], 0
        cur.append(w)
        cw += ww
    if cur:
        lines.append(cur)
    lh = int(size * 1.32)
    for li, line in enumerate(lines):
        total = sum(wlen(w) for w in line) + sp * (len(line) - 1)
        x = cx - total / 2
        for w in line:
            for t, b in w:
                draw_text(dst, (x, y + li * lh), t, fb if b else f, fill=TOK["ichor"] if b else TOK["parch"], shadow=0.8,
                          shadow_off=(0, 1), shadow_blur=1)
                x += K.text_size(t, fb if b else f)[0] + (1 if b else 0)
            x += sp
    return y + len(lines) * lh


def boon_card(gods: list[str], name: str, rarity: str, kind: str, desc: str, key: str, footer: str | None = None,
              W: int = 330, Hh: int = 480, hover: bool = False) -> Image.Image:
    c1 = K.GODS[gods[0]][1]
    c2 = K.GODS[gods[-1]][1]
    rc = K.RARITY[rarity]
    tint = mix(c1, "#000000", 0.7)
    panel, (ox, oy) = ornate_panel(W, Hh, r=10, frame=3.2 if rarity != "common" else 2.6, corner=58,
                                   gem_color=rc if rarity != "common" else None, top=mix(c1, "#1A120E", 0.9),
                                   bot="#0B0706", alpha=0.97, pattern=True,
                                   frame_stops=K.GOLD_RAMP if rarity != "common" else K.BRONZE_RAMP,
                                   corner_stops=K.GOLD_RAMP if rarity != "common" else K.BRONZE_RAMP)
    pad_top = 60
    img = blank(panel.width + 40, panel.height + pad_top + 40)
    px, py = 20, pad_top + 20
    # god-colour aura behind the card (hover lift)
    if hover:
        aura = blank(panel.width, panel.height)
        aura.alpha_composite(panel)
        glow(img, aura, (px, py), c1, blur=22, opacity=0.55, spread=4)
    img.alpha_composite(panel, (px, py))
    cx = px + ox + W / 2
    top = py + oy
    # god-colour light pooling from the medallion
    rg = K.radial_glow(W - 20, 260, c1, opacity=0.32, falloff=1.5)
    img.alpha_composite(clip_to(rg, down(K.rrect_mask(W - 20, 260, 8), W - 20, 260)), (int(cx - (W - 20) / 2), top + 4))
    # engraved god sigil watermark in the lower half
    wm = I.render_icon(gods[0], int(W * 0.62), tint=c1, light=mix(c1, "#FFFFFF", 0.3), outline=0, pad=0.0)
    wm.putalpha(wm.split()[3].point(lambda v: int(v * 0.07)))
    img.alpha_composite(wm, (int(cx - wm.width / 2), top + Hh - wm.height - 40))
    # enamel inner border in the god colour(s)
    en_m = K.ring_mask(W, Hh, 8, 1.8, inset=7.5)
    grad = np.zeros((Hh, W, 4), np.float32)
    t = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    grad[..., :3] = np.array(K.rgb(c1), np.float32) * (1 - t) + np.array(K.rgb(c2), np.float32) * t
    grad[..., 3] = 255
    gi = to_img(grad)
    gi.putalpha(ImageChops.multiply(gi.split()[3], down(en_m, W, Hh)).point(lambda v: int(v * 0.8)))
    img.alpha_composite(gi, (px + ox, top))
    # medallion breaking the top edge
    med = god_medallion(104, gods, kind)
    img.alpha_composite(med, (int(cx - med.width / 2), top - 52 - 20))
    # god ribbon
    gname = " & ".join(K.GODS[g][0] for g in gods).upper()
    gy = top + 94
    draw_text(img, (cx, gy), gname, cinzel(14, 700), fill=mix(c1, "#FFFFFF", 0.35), anchor="m", tracking=3.2,
              shadow=0.9, shadow_off=(0, 1), shadow_blur=1.2)
    gw = K.text_size(gname, cinzel(14, 700), 3.2)[0]
    for sgn in (-1, 1):
        ln = K.divider(70, 8)
        la = np.asarray(ln.split()[3], np.float32)
        ramp = np.linspace(0, 1, 70) if sgn < 0 else np.linspace(1, 0, 70)
        ln.putalpha(Image.fromarray((la * ramp[None, :]).astype(np.uint8)))
        img.alpha_composite(ln, (int(cx + sgn * (gw / 2 + 12) - (70 if sgn < 0 else 0)), gy - 9))
    # boon name
    nf = cinzel(27, 700)
    for sz in (27, 25, 23, 21, 20):
        nf = cinzel(sz, 700)
        if K.text_size(name, nf)[0] <= W - 56:
            break
    draw_text(img, (cx, top + 138), name, nf, fill=rc if rarity != "common" else TOK["parch"], anchor="m",
              gradient=None if rarity != "godforged" else ("#FFF6D8", "#FFB82E"), shadow=0.95, shadow_off=(0, 2),
              shadow_blur=2, glow_color=rc if rarity in ("epic", "godforged") else None, glow_amt=0.35, glow_blur=10)
    # rarity / kind ribbon
    label = RARITY_NAME[rarity] + ("" if kind == "Standard" else f" · {kind.upper()}")
    rf = cinzel(12, 700)
    rw = K.text_size(label, rf, 2.2)[0]
    rib = K.gilded_panel(rw + 50, 24, r=4, frame=1.4, corners=0, keyline=False, alpha=0.9, chamfer=True)
    img.alpha_composite(rib, (int(cx - (rw + 50) / 2), top + 156))
    g = gem(13, rc)
    img.alpha_composite(g, (int(cx - (rw + 50) / 2 + 9), top + 162))
    draw_text(img, (cx + 8, top + 173), label, rf, fill=rc if rarity != "common" else TOK["parch_dim"], anchor="m",
              tracking=2.2, shadow=0.8, shadow_off=(0, 1), shadow_blur=1)
    # divider
    img.alpha_composite(K.divider(W - 90, 12, rc if rarity != "common" else None), (int(cx - (W - 90) / 2), top + 200))
    # description
    rich_desc(img, cx, top + 250, desc, W - 60, 19)
    # footer
    if footer:
        draw_text(img, (cx, top + Hh - 56), footer, sans(15, "Italic"), fill=TOK["parch_dim"], anchor="m", shadow=0.8,
                  shadow_off=(0, 1), shadow_blur=1)
    kc = K.keycap(key, 28, 15)
    img.alpha_composite(kc, (int(cx - kc.width / 2), top + Hh - 22))
    return img
