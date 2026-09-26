"""The contact sheet: docs/art/ui_mockups/kit_sheet.png.

Every composition here is built only from the kit textures plus what UI_STYLE says is code
(lacquer bodies, gradients, conic sweeps, text), sampled the way Bevy samples them (linear, no
mipmaps, @2x slices at max_corner_scale 0.5). Rows: boon cards, the Forge drawer and widget
states, the combat HUD over a real game frame, 2x close-ups (UiScale 2.0), and the raw kit.

Icons come from assets/ui/icons (lane I) when present, else from the mockup glyph library in
docs/art/ui_mockups/src/a, else they are left out. They only dress the demo; the kit never bakes them.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

from . import preview as pv
from .core import RARITY, rgb

ROOT = pv.ROOT
GODS = {"pyra": ("#E0312B", "#FFC23D"), "zephyros": ("#3FD8FF", "#F2FBFF"), "nyctia": ("#7B3FE0", "#141018"),
        "aeon": ("#C9D2DC", "#8A96A3"), "gaiaa": ("#4E9A3A", "#B07A3C"), "morwenn": ("#1FA39A", "#7FE36B"),
        "seraphel": ("#FFD86B", "#FFFFFF"), "umbra_rex": ("#8E1B1B", "#FF6A2A")}
PLAYER = ["#FFC940", "#3FD8FF", "#B06CFF", "#5BE37D"]
ELEM = {"kinetic": "#F4E3C1", "flame": "#FF7A1A", "storm": "#3FD8FF", "void": "#A45CFF", "plague": "#86E03A",
        "radiant": "#FFE27A"}


def c255(h):
    return tuple(int(v * 255) for v in rgb(h))


def c01(h):
    return rgb(h)


# ───────────────────────────── kit access ─────────────────────────────
class Kit:
    def __init__(self, out_dir):
        self.dir = out_dir
        man = json.load(open(os.path.join(out_dir, "ui_kit.json"), encoding="utf-8"))
        self.man = {t["file"][:-len("@2x.png")]: t for t in man["textures"]}
        self.cache = {}
        self.icache = {}
        self._gi = None

    def img(self, name):
        if name not in self.cache:
            self.cache[name] = Image.open(os.path.join(self.dir, name + "@2x.png")).convert("RGBA")
        return self.cache[name]

    def meta(self, name):
        return self.man[name]

    def icon(self, key, px, fallback=None, tint=None):
        """A premultiplied icon array px x px: lane I's master if present, else the mockup glyph."""
        k = (key, px, fallback, tint)
        if k in self.icache:
            return self.icache[k]
        arr = None
        p = os.path.join(self.dir, "icons", key + ".png")
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            # the runtime's box-filtered levels (128 -> 64 -> 32), then one bilinear tap
            while im.width >= px * 2 and im.width > 32:
                im = pv.unpremul(pv.premul(im).reshape(im.height // 2, 2, im.width // 2, 2, 4).mean(axis=(1, 3)))
            arr = pv.stretch(im, px, px)
        elif fallback is not None:
            gi = self._glyphs()
            if gi is not None and fallback in gi.GLYPHS:
                im = gi.render_icon(fallback, px, tint=tint or "#E6CFA0", pad=0.06, outline=1.2)
                arr = pv.premul(im)
        self.icache[k] = arr
        return arr

    def _glyphs(self):
        if self._gi is None:
            try:
                sys.path.insert(0, os.path.join(ROOT, "docs", "art", "ui_mockups", "src", "a"))
                import gm_icons  # noqa: F401
                import sigils  # noqa: F401  (registers the other god sigils)
                import busts  # noqa: F401
                self._gi = gm_icons
            except Exception:
                self._gi = False
        return self._gi or None


def put(b, K, name, x, y, w=None, h=None, S=1, flip_x=False, flip_y=False, tint=None, alpha=1.0):
    """Place a kit texture at logical (x, y) with logical size (w, h), the way its manifest says."""
    m = K.meta(name)
    img = K.img(name)
    if flip_x:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_y:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    lw, lh = m["logical_size"]
    w = lw if w is None else w
    h = lh if h is None else h
    W, H = int(round(w * S)), int(round(h * S))
    mode = m["mode"]
    if mode in ("nine_slice", "three_slice_h"):
        sl = m["slice"]
        border = (sl["left"], sl["top"], sl["right"], sl["bottom"])
        if flip_x:
            border = (border[2], border[1], border[0], border[3])
        arr = pv.nine_slice(img, border, W, H, 0.5 * S, tile_sides=(m.get("sides") == "tile"),
                            tile_px=(m.get("tile_logical", 0) * S) or None)
    elif mode == "tiled":
        tile = pv.stretch(img, int(round(lw * S)), H)
        reps = int(math.ceil(W / tile.shape[1])) + 1
        arr = np.tile(tile, (1, reps, 1))[:, :W]
    else:
        arr = pv.stretch(img, W, H)
    b.put(arr, int(round(x * S)), int(round(y * S)), alpha, None if tint is None else c01(tint))


def put_icon(b, K, key, cx, cy, size, S=1, fallback=None, tint=None, alpha=1.0, mul=None):
    arr = K.icon(key, int(round(size * S)), fallback, tint)
    if arr is None:
        return
    if mul is not None:
        arr = arr.copy()
        arr[..., :3] *= np.asarray(mul, np.float32)
    b.put(arr, int(round(cx * S - arr.shape[1] / 2)), int(round(cy * S - arr.shape[0] / 2)), alpha)


# ─────────────── code-side pieces (what Bevy draws without textures) ───────────────
def _grid(W, H):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    return x + 0.5, y + 0.5


def rrect_cov(W, H, r):
    x, y = _grid(W, H)
    qx = np.abs(x - W / 2) - (W / 2 - r)
    qy = np.abs(y - H / 2) - (H / 2 - r)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    return np.clip(0.5 - d, 0, 1)


def layer(cov, col, alpha=1.0):
    col = np.asarray(col, np.float32)
    out = np.zeros(cov.shape + (4,), np.float32)
    a = cov * alpha
    if col.ndim == 1:
        out[..., :3] = col[None, None, :] * a[..., None]
    else:
        out[..., :3] = col * a[..., None]
    out[..., 3] = a
    return out


def vgrad(H, W, top, bot):
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    return (c01(top)[None, None, :] * (1 - t) + c01(bot)[None, None, :] * t) * np.ones((1, W, 1), np.float32)


def box_shadow(b, x, y, w, h, r, S=1, dy=3, blur=9, alpha=0.55, color="#000000", spread=0):
    pad = int((blur * 2 + abs(dy) + spread + 2) * S)
    W, H = int(w * S) + pad * 2, int(h * S) + pad * 2
    cov = np.zeros((H, W), np.float32)
    inner = rrect_cov(int((w + 2 * spread) * S), int((h + 2 * spread) * S), (r + spread) * S)
    oy = pad + int(dy * S) - int(spread * S)
    ox = pad - int(spread * S)
    cov[oy:oy + inner.shape[0], ox:ox + inner.shape[1]] = inner
    cov = ndimage.gaussian_filter(cov, blur * S / 2)
    b.put(layer(cov, c01(color), alpha), int(x * S) - pad, int(y * S) - pad)


def body(b, x, y, w, h, r, S=1, top="lac2", bot="lac1", alpha=0.95):
    W, H = int(round(w * S)), int(round(h * S))
    b.put(layer(rrect_cov(W, H, r * S), vgrad(H, W, top, bot), alpha), int(round(x * S)), int(round(y * S)))


def radial(b, cx, cy, rx, ry, color, alpha, S=1, power=1.6):
    W, H = int(rx * 2 * S), int(ry * 2 * S)
    x, y = _grid(W, H)
    d = np.hypot((x - W / 2) / (W / 2), (y - H / 2) / (H / 2))
    b.put(layer(np.clip(1 - d, 0, 1) ** power, c01(color), alpha), int((cx - rx) * S), int((cy - ry) * S))


def disc(b, cx, cy, r, color, S=1, alpha=1.0):
    W = int(math.ceil(2 * r * S)) + 2
    x, y = _grid(W, W)
    d = np.hypot(x - W / 2, y - W / 2)
    b.put(layer(np.clip(0.5 - (d - r * S), 0, 1), c01(color) if isinstance(color, str) else color, alpha),
          int(round(cx * S - W / 2)), int(round(cy * S - W / 2)))


def conic_ring(b, cx, cy, r_out, r_in, frac, S=1, start_col="#7A3E12", end_col="#FFF6DA", empty="#140C08",
               meniscus=True):
    R = int(math.ceil(r_out * S)) + 2
    x, y = _grid(2 * R, 2 * R)
    dx, dy = x - R, y - R
    d = np.hypot(dx, dy) / S
    ang = (np.arctan2(dx, -dy) / (2 * math.pi)) % 1.0
    cov = np.clip(0.5 - (d - r_out) * S, 0, 1) * np.clip(0.5 + (d - r_in) * S, 0, 1)
    t = np.clip(ang / max(frac, 1e-6), 0, 1)
    if start_col == "#7A3E12":   # the molten ramp poured clockwise: dark amber -> orange -> gold -> white-hot front
        stops = [(0.0, "#7A3E12"), (0.45, "#E8942E"), (0.8, "#FFC95A"), (0.96, "#FFF6DA"), (1.0, "#FFFBEA")]
        col = np.stack([np.interp(t, [s_[0] for s_ in stops], [c01(s_[1])[i] for s_ in stops]) for i in range(3)], -1)
    else:
        col = c01(start_col)[None, None, :] * (1 - t[..., None]) + c01(end_col)[None, None, :] * t[..., None]
    mid = (r_out + r_in) / 2
    col = col * (0.82 + 0.25 * np.clip(1 - np.abs(d - mid) / ((r_out - r_in) / 2), 0, 1))[..., None]
    filled = ang <= frac
    col = np.where(filled[..., None], np.clip(col, 0, 1), c01(empty)[None, None, :])
    b.put(layer(cov, col), int(cx * S) - R, int(cy * S) - R)
    if meniscus and 0 < frac < 1:
        th = frac * 2 * math.pi
        ex, ey = math.sin(th), -math.cos(th)
        front = (dx * ex + dy * ey) > 0
        dist = np.where(front, np.abs(dx * ey - dy * ex), 1e9)
        line = np.clip(0.8 * S - dist + 0.5, 0, 1) * cov
        b.put(layer(line, c01("#FFFBEA")), int(cx * S) - R, int(cy * S) - R)


def sweep(b, K, shape, cx, cy, size, frac_left, S=1):
    """The §6.1a cooldown sweep: #050302 at 0.55 over the remaining fraction, clockwise from 12
    o'clock, with a 1.4 px gold_lt edge, clipped to the slot (the mask stands in for the radius rule)."""
    W = int(round(size * S))
    mask = pv.stretch(K.img(f"slots/slot_{shape}_mask"), W, W)[..., 3]
    x, y = _grid(W, W)
    dx, dy = x - W / 2, y - W / 2
    ang = (np.arctan2(dx, -dy) / (2 * math.pi)) % 1.0
    done = 1 - frac_left
    cov = (ang >= done).astype(np.float32) * mask
    cov = ndimage.gaussian_filter(cov, 0.5)
    b.put(layer(cov, c01("#050302"), 0.55), int(cx * S - W / 2), int(cy * S - W / 2))
    th = done * 2 * math.pi
    ex, ey = math.sin(th), -math.cos(th)
    front = (dx * ex + dy * ey) > 0
    dist = np.where(front, np.abs(dx * ey - dy * ex), 1e9)
    line = np.clip(0.7 * S - dist + 0.5, 0, 1) * mask
    b.put(layer(line, c01("gold_lt"), 0.9), int(cx * S - W / 2), int(cy * S - W / 2))


def text(b, x, y, s, f, S=1, fill="parch", anchor="ls", tracking=0.0, shadow=True):
    return pv.text(b, (x * S, y * S), s, f, fill=c255(fill), anchor=anchor, shadow=shadow, tracking=tracking * S) / S


def cz(px, S=1, w=800):
    return pv.cinzel(int(round(px * S)), w)


def al(px, S=1, face="Medium"):
    return pv.body(int(round(px * S)), face)


# ───────────────────────────── compositions ─────────────────────────────
def ember_knot(b, K, cx, cy, w, S=1, gem=None, gem_tint=None):
    half = (w - 56) / 2
    put(b, K, "ornaments/emberknot_rule", cx - w / 2, cy - 7, half, 14, S, flip_x=True)
    put(b, K, "ornaments/emberknot_knot", cx - 28, cy - 7, S=S)
    put(b, K, "ornaments/emberknot_rule", cx + 28, cy - 7, half, 14, S)
    if gem:
        put(b, K, f"ornaments/gem_{gem}", cx - 5, cy - 5, 10, 10, S, tint=gem_tint)


def rarity_gem(b, K, cx, cy, r, rarity, S=1):
    put_icon(b, K, f"rarity/gem_{rarity}", cx, cy, r * 2.4, S)


def slot(b, K, shape, cx, cy, size, S=1, icon=None, fallback=None, state="ready", glow=False, tint=None, sweep_left=0.0,
         cd_text=None):
    x, y = cx - size / 2, cy - size / 2
    box_shadow(b, x, y, size, size, size * 0.2, S, dy=2.5, blur=5, alpha=0.75 if shape != "round" else 0.6)
    if glow:
        put(b, K, f"slots/slot_{shape}_glow", cx - size * 0.75, cy - size * 0.75, size * 1.5, size * 1.5, S,
            tint="ready_glow", alpha=0.9)
    put(b, K, f"slots/slot_{shape}_fill", x, y, size, size, S)
    if icon:
        mul = (0.43, 0.40, 0.36) if state == "cooling" else ((0.55, 0.55, 0.55) if state == "disabled" else None)
        put_icon(b, K, icon, cx, cy, size * 0.74, S, fallback=fallback, tint=tint, mul=mul)
    if sweep_left:
        sweep(b, K, shape, cx, cy, size - 3, sweep_left, S)
    if state == "ready":
        put(b, K, f"slots/slot_{shape}_sheen", x, y, size, size, S)
    put(b, K, f"slots/slot_{shape}_rim", x, y, size, size, S)
    if cd_text:
        text(b, cx, cy + size * 0.13, cd_text, cz(size * 0.36, S), S, fill="numeral", anchor="ms")


def keycap(b, K, cx, cy, label, h=20, S=1, pressed=False):
    f = al(h * 0.62, S, "Bold")
    tw = f.getlength(label) / S
    w = max(h, tw + 12)
    put(b, K, "frames/keycap_pressed" if pressed else "frames/keycap", cx - w / 2, cy - h / 2, w, h, S)
    text(b, cx, cy + h * 0.22 - (1.5 if not pressed else -0.4) * h / 24, label, f, S, fill="parch", anchor="ms",
         shadow=False)
    return w


def niche_card(b, K, x, y, gods, rarity, name, desc, kind=None, key="1", tag="NEW", pips=0, S=1, hover=False,
               icon=None):
    g1 = GODS[gods[0]][0]
    g2 = GODS[gods[-1]][0]
    if hover:
        y -= 12
        radial(b, x + 150, y + 200, 230, 290, g1, 0.30, S, power=1.4)
    box_shadow(b, x, y + 60, 300, 360, 14, S, dy=12, blur=14, alpha=0.85)
    put(b, K, "frames/niche_body", x, y, S=S, tint=g1)
    put(b, K, "frames/niche_glow", x, y, S=S, tint=g1, alpha=0.42)
    if len(gods) > 1:   # duo: the second god's light on the right half
        tmp = pv.Board(int(300 * S), int(420 * S))
        put(tmp, K, "frames/niche_glow", 0, 0, S=S, tint=g2, alpha=0.5)
        tmp.p[:, :int(150 * S)] = 0
        b.put(tmp.p, int(x * S), int(y * S))
        tmp = pv.Board(int(300 * S), int(420 * S))
        put(tmp, K, "frames/niche_hairline", 0, 0, S=S, tint=g1)
        t2 = pv.Board(int(300 * S), int(420 * S))
        put(t2, K, "frames/niche_hairline", 0, 0, S=S, tint=g2)
        ramp = np.clip((np.arange(int(300 * S)) / S - 110) / 80, 0, 1)[None, :, None]
        b.put(tmp.p * (1 - ramp) + t2.p * ramp, int(x * S), int(y * S))
    else:
        put(b, K, "frames/niche_hairline", x, y, S=S, tint=g1)
    if rarity == "godforged":
        put(b, K, "ornaments/sunburst16", x + 150 - 88, y + 56 - 88, 176, 176, S, alpha=0.55)
    put(b, K, f"frames/niche_frame_{rarity}", x, y, S=S)
    if rarity != "common":
        for sx in (0, 300):
            rarity_gem(b, K, x + sx, y + 112, 8, rarity, S)
    # apex medallion
    mx, my = x + 150, y + 56
    box_shadow(b, mx - 50, my - 50, 100, 100, 50, S, dy=4, blur=6, alpha=0.8)
    if len(gods) > 1:
        tmp = pv.Board(int(100 * S), int(100 * S))
        put(tmp, K, "slots/enamel_disc", 0, 0, S=S, tint=g1)
        t2 = pv.Board(int(100 * S), int(100 * S))
        put(t2, K, "slots/enamel_disc", 0, 0, S=S, tint=g2)
        xx, yy = _grid(int(100 * S), int(100 * S))
        m = np.clip((xx - yy) / 1.5 + 0.5, 0, 1)[..., None]
        b.put(tmp.p * (1 - m) + t2.p * m, int((mx - 50) * S), int((my - 50) * S))
    else:
        put(b, K, "slots/enamel_disc", mx - 50, my - 50, S=S, tint=g1)
    if icon:
        put_icon(b, K, icon[0], mx, my, 64, S, fallback=icon[1], tint="#F4E6C8")
    put(b, K, "slots/medallion_rim_100", mx - 50, my - 50, S=S)
    if kind == "Legendary":
        put(b, K, "ornaments/suncrest_50", mx - 65, my - 50 - 31, S=S)
    badges = [(197, 93)] if len(gods) == 1 else [(104, 94), (196, 94)]
    for gk, (bx, by) in zip(gods if len(gods) > 1 else gods[:1], badges):
        gc = GODS[gk][0]
        box_shadow(b, x + bx - 17, y + by - 17, 34, 34, 17, S, dy=2, blur=4, alpha=0.8)
        put(b, K, "slots/enamel_disc", x + bx - 17, y + by - 17, 34, 34, S, tint=gc)
        put_icon(b, K, f"gods/{gk}", x + bx, y + by, 22, S, fallback=gk, tint="#F4E6C8")
        put(b, K, "slots/medallion_rim_34", x + bx - 17, y + by - 17, S=S)
    dy = 0
    gline = " & ".join(g.upper() for g in gods)
    gcol = "#%02X%02X%02X" % tuple(int(v * 255) for v in (c01(g1) * 0.55 + 0.45))
    text(b, x + 150, y + 146, gline, cz(13, S), S, fill=gcol, anchor="ms", tracking=3)
    if kind:
        f = cz(11, S)
        tw = f.getlength(kind.upper()) / S + 3 * len(kind)
        put(b, K, "frames/pill", x + 150 - tw / 2 - 12, y + 150, tw + 24, 18, S)
        text(b, x + 150, y + 163, kind.upper(), f, S, fill="ink_text", anchor="ms", tracking=2.4, shadow=False)
        dy = 22
    ncol = "parch" if rarity == "common" else RARITY[rarity]
    size = 26
    while cz(size, S).getlength(name.upper()) / S > 256 and size > 20:
        size -= 1
    text(b, x + 150, y + 194 + dy, name.upper(), cz(size, S), S, fill=ncol, anchor="ms", tracking=1)
    word = rarity.upper()
    f = cz(11, S)
    ww = f.getlength(word) / S + 2.4 * len(word) + 34
    put(b, K, "frames/ribbon_bronze" if rarity == "common" else "frames/ribbon_gilt", x + 150 - ww / 2, y + 206 + dy,
        ww, 22, S)
    rarity_gem(b, K, x + 150 - ww / 2 + 13, y + 217 + dy, 5.4, rarity, S)
    text(b, x + 150 + 8, y + 221 + dy, word, f, S, fill=("parch_dim" if rarity == "common" else RARITY[rarity]),
         anchor="ms", tracking=2.4)
    ember_knot(b, K, x + 150, y + 244 + dy, 204, S, gem="white", gem_tint=RARITY[rarity])
    fb = al(18, S)
    lines = desc
    for i, ln in enumerate(lines):
        text(b, x + 150, y + 284 + dy + i * 23, ln, fb, S, fill="parch", anchor="ms")
    text(b, x + 26, y + 386, tag, cz(11, S), S, fill=("ichor" if tag == "NEW" else "parch_dim"), tracking=2.4)
    for i in range(3):
        cxp = x + 266 - i * 14
        col = "ichor" if i < pips else "#3A2A1C"
        pts_r = 5
        put(b, K, "ornaments/gem_white", cxp - pts_r, y + 382 - pts_r, 2 * pts_r, 2 * pts_r, S, tint=col)
    keycap(b, K, x + 150, y + 405, key, 30, S)


def forge_panel(b, K, x0, y0, S=1):
    """A condensed Forge drawer (§7.1) built from the kit."""
    w, h = 880, 520
    box_shadow(b, x0, y0, w, h, 10, S, dy=8, blur=18, alpha=0.75)
    body(b, x0, y0, w, h, 10, S, alpha=0.95)
    put(b, K, "frames/gilt_panel", x0, y0, w, h, S)
    for c in ("tl", "tr", "bl", "br"):
        ox = x0 - 7.6 if c[1] == "l" else x0 + w - 76 + 7.6
        oy = y0 - 7.6 if c[0] == "t" else y0 + h - 76 + 7.6
        put(b, K, f"ornaments/forgehorn_76_{c}", ox, oy, S=S)
    put(b, K, "ornaments/suncrest_62", x0 + w / 2 - 80.5, y0 - 62 * 0.62, S=S)
    # header
    text(b, x0 + w / 2, y0 + 70, "THE FORGE", cz(36, S), S, fill="gold_lt", anchor="ms", tracking=5)
    text(b, x0 + w / 2, y0 + 96, "The Chainyard anvil burns hot", al(17, S, "Italic"), S, fill="parch_dim", anchor="ms")
    conic_ring(b, x0 + 72, y0 + 62, 28, 22, 19 / 25, S)
    put(b, K, "slots/medallion_rim_60", x0 + 72 - 30, y0 + 62 - 30, S=S, alpha=0.9)
    text(b, x0 + 72, y0 + 70, "19", cz(22, S), S, fill="numeral", anchor="ms")
    text(b, x0 + 72, y0 + 112, "HEAT", cz(12, S), S, fill="parch_dim", anchor="ms", tracking=2)
    for i in range(3):
        put_icon(b, K, "currency/forge_charge", x0 + 151 + i * 30, y0 + 58, 30, S, fallback="salvage",
                 mul=None if i < 2 else (0.35, 0.33, 0.3))
    text(b, x0 + 181, y0 + 112, "CHARGES", cz(12, S), S, fill="parch_dim", anchor="ms", tracking=2)
    put_icon(b, K, "currency/godshard", x0 + w - 100, y0 + 58, 32, S, fallback="godshard")
    text(b, x0 + w - 40, y0 + 68, "56", cz(26, S), S, fill="numeral", anchor="rs")
    text(b, x0 + w - 40, y0 + 112, "SHARDS", cz(12, S), S, fill="parch_dim", anchor="rs", tracking=2)
    ember_knot(b, K, x0 + w / 2, y0 + 132, w - 120, S, gem="ivory")
    text(b, x0 + 40, y0 + 164, "THE WEAPON", cz(15, S), S, fill="gold_lt", tracking=2.7)
    # chassis card + four socket cards
    cy0 = y0 + 176
    box_shadow(b, x0 + 40, cy0, 196, 180, 8, S, dy=6, blur=10, alpha=0.7)
    body(b, x0 + 40, cy0, 196, 180, 8, S, top="#2A1F18", bot="#100B08")
    radial(b, x0 + 138, cy0 + 70, 60, 60, ELEM["storm"], 0.30, S)
    put_icon(b, K, "chassis/colossus_cannon", x0 + 138, cy0 + 72, 100, S, fallback="cannon", tint="#E6CFA0")
    put(b, K, "frames/gilt_card_common", x0 + 40, cy0, 196, 180, S)
    text(b, x0 + 138, cy0 + 146, "COLOSSUS CANNON", cz(15, S), S, fill="parch", anchor="ms", tracking=0.8)
    put_icon(b, K, "elements/storm", x0 + 108, cy0 + 163, 18, S, fallback="storm", tint=ELEM["storm"])
    text(b, x0 + 146, cy0 + 168, "STORM", cz(13, S), S, fill=ELEM["storm"], anchor="ms", tracking=2)
    parts = [("CORE", "round", "slots/core", "core", "rare", "Stormcore"),
             ("MECHANISM", "octagon", "slots/mechanism", "mechanism", "epic", "Ricochet"),
             ("RELIC", "arch", "slots/relic", "relic", "rare", "Nyctian Eye"),
             ("SIGIL", "lozenge", "slots/sigil", "sigil", "godforged", "Anvilheart")]
    for i, (lab, shape, ic, fb, rar, nm) in enumerate(parts):
        cx = x0 + 252 + i * 150
        box_shadow(b, cx, cy0, 138, 180, 8, S, dy=6, blur=10, alpha=0.7)
        body(b, cx, cy0, 138, 180, 8, S, top="#2A1F18", bot="#100B08")
        radial(b, cx + 69, cy0 + 20, 69, 44, RARITY[rar], 0.18, S, power=1.2)
        put(b, K, f"frames/gilt_card_{rar}", cx, cy0, 138, 180, S)
        text(b, cx + 69, cy0 + 24, lab, cz(12, S), S, fill="parch_dim", anchor="ms", tracking=2)
        slot(b, K, shape, cx + 69, cy0 + 72, 74, S, icon=ic, fallback=fb, glow=(rar in ("epic", "godforged")),
             state="ready")
        rarity_gem(b, K, cx + 69, cy0 + 112, 5.4, rar, S)
        text(b, cx + 69, cy0 + 136, nm, al(16, S, "Bold"), S, fill=("parch" if rar == "common" else RARITY[rar]),
             anchor="ms")
        put(b, K, "frames/chip", cx + 15, cy0 + 146, 108, 26, S)
        put_icon(b, K, "currency/boon_reroll", cx + 31, cy0 + 159, 16, S, fallback="reroll")
        text(b, cx + 68, cy0 + 164, "REROLL", cz(11, S), S, fill="parch", anchor="ms", tracking=1.2)
        text(b, cx + 108, cy0 + 164, "6", al(13, S, "Bold"), S, fill="parch", anchor="ms")
        if i == 2:
            put(b, K, "frames/card_selected", cx - 5, cy0 - 5, 148, 190, S)
            put(b, K, "frames/pill", cx + 69 - 42, cy0 - 10, 84, 20, S)
            text(b, cx + 69, cy0 + 4, "REPLACE", cz(11, S), S, fill="ink_text", anchor="ms", tracking=1.6,
                 shadow=False)
    # DPS line + recipe hint
    text(b, x0 + 40, y0 + 400, "1,284", cz(38, S), S, fill="numeral")
    text(b, x0 + 158, y0 + 400, "DPS", cz(15, S), S, fill="parch_dim", tracking=2)
    text(b, x0 + 214, y0 + 400, "→", al(30, S, "Bold"), S, fill="gold_lt")
    text(b, x0 + 252, y0 + 400, "1,592", cz(38, S), S, fill="ichor")
    rx, ry, rw, rh = x0 + 40, y0 + 420, w - 80, 64
    body(b, rx, ry, rw, rh, 6, S, alpha=0.8)
    put(b, K, "frames/dashed_outline", rx, ry, rw, rh, S, tint="ichor")
    put_icon(b, K, "currency/seal", rx + 34, ry + 32, 36, S, fallback="seal")
    text(b, rx + 64, ry + 22, "ONE PART AWAY", cz(11, S), S, fill="ichor", tracking=2.4)
    text(b, rx + 64, ry + 42, "THE ENDLESS ARGUMENT", cz(17, S), S, fill="gold_lt", tracking=1.5)
    text(b, rx + 64, ry + 58, "+1 chain, +10% damage · Doomstack is in your bag", al(15, S), S, fill="parch_dim")
    for i, (shape, ic, fb) in enumerate((("round", "slots/core", "core"), ("octagon", "slots/mechanism", "mechanism"),
                                         ("arch", "slots/relic", "relic"))):
        slot(b, K, shape, rx + rw - 120 + i * 42, ry + 32, 34, S, icon=ic, fallback=fb, glow=(i == 2))
    # footer
    kx = keycap(b, K, x0 + 58, y0 + h - 22, "LMB", 20, S)
    text(b, x0 + 58 + kx / 2 + 10, y0 + h - 17, "SELECT", cz(12, S), S, fill="parch_dim", tracking=2)
    kx2 = keycap(b, K, x0 + 188, y0 + h - 22, "Tab", 20, S)
    text(b, x0 + 188 + kx2 / 2 + 10, y0 + h - 17, "CLOSE", cz(12, S), S, fill="parch_dim", tracking=2)


def states_panel(b, K, x0, y0, S=1):
    """Widget states: buttons, chips, keycaps, pills, ribbons, P chips, a tooltip (on a lacquer card)."""
    box_shadow(b, x0 - 24, y0 - 20, 580, 500, 10, S, dy=8, blur=18, alpha=0.7)
    body(b, x0 - 24, y0 - 20, 580, 500, 10, S, alpha=0.93)
    put(b, K, "frames/tooltip", x0 - 24, y0 - 20, 580, 500, S)
    text(b, x0, y0 + 14, "BUTTONS", cz(13, S), S, fill="gold_lt", tracking=2.4)
    rows = [("primary", "EQUIP", "ink_text"), ("secondary", "SALVAGE", "parch")]
    for j, (kind, lab, col) in enumerate(rows):
        for i, st in enumerate(("normal", "hover", "pressed")):
            name = f"frames/button_{kind}" + ("" if st == "normal" else f"_{st}")
            bx, by = x0 + i * 176, y0 + 28 + j * 58
            if kind == "primary" and st != "pressed":
                box_shadow(b, bx, by, 164, 46, 8, S, dy=0, blur=8 if st == "hover" else 6,
                           alpha=0.55 if st == "hover" else 0.4, color="ichor_glow", spread=1)
            put(b, K, name, bx, by, 164, 46, S)
            text(b, bx + 16, by + 30 + (1 if st == "pressed" else 0), lab, cz(17, S), S, fill=col, tracking=2,
                 shadow=(kind != "primary"))
            if j == 1:
                text(b, bx + 82, by + 64, st, al(13, S, "Italic"), S, fill="parch_mute", anchor="ms")
    bx, by = x0, y0 + 164
    put(b, K, "frames/button_disabled", bx, by, 164, 40, S)
    text(b, bx + 16, by + 26, "FUSE", cz(17, S), S, fill="parch_mute", tracking=2)
    text(b, bx + 150, by + 25, "no twin", al(14, S, "Italic"), S, fill="parch_mute", anchor="rs")
    for i, st in enumerate(("normal", "hover", "disabled")):
        cx = x0 + 186 + i * 118
        put(b, K, "frames/chip" + ("" if st == "normal" else f"_{st}"), cx, by + 7, 108, 26, S)
        put_icon(b, K, "currency/boon_reroll", cx + 16, by + 20, 16, S, fallback="reroll",
                 mul=(0.5, 0.5, 0.5) if st == "disabled" else None)
        text(b, cx + 62, by + 25, "REROLL", cz(11, S), S, fill="parch_mute" if st == "disabled" else "parch",
             anchor="ms", tracking=1.2)
    text(b, x0, y0 + 240, "KEYS · PILLS · PLAQUES", cz(13, S), S, fill="gold_lt", tracking=2.4)
    kx = x0 + 12
    for lab in ("Q", "E", "R", "V", "Tab", "LMB", "Esc"):
        w = keycap(b, K, kx + 10, y0 + 268, lab, 24, S)
        kx += w + 8
    keycap(b, K, kx + 14, y0 + 268, "F", 24, S, pressed=True)
    text(b, kx + 36, y0 + 273, "held", al(13, S, "Italic"), S, fill="parch_mute")
    px = x0
    for lab in ("DUO", "LEGENDARY", "REPLACE"):
        f = cz(11, S)
        tw = f.getlength(lab) / S + 2 * len(lab) + 24
        put(b, K, "frames/pill", px, y0 + 298, tw, 18, S)
        text(b, px + tw / 2, y0 + 311, lab, f, S, fill="ink_text", anchor="ms", tracking=2, shadow=False)
        px += tw + 8
    for lab in ("ALL", "CORE", "MECH"):
        f = cz(11, S)
        tw = f.getlength(lab) / S + 2 * len(lab) + 24
        put(b, K, "frames/pill_outline", px, y0 + 298, tw, 18, S)
        text(b, px + tw / 2, y0 + 311, lab, f, S, fill="parch_dim" if lab != "ALL" else "gold_lt", anchor="ms",
             tracking=2)
        px += tw + 8
    rx = x0
    for m, rar in (("bronze", "common"), ("gilt", "rare"), ("gilt", "epic"), ("gilt", "godforged")):
        word = rar.upper()
        f = cz(11, S)
        ww = f.getlength(word) / S + 2.4 * len(word) + 34
        put(b, K, f"frames/ribbon_{m}", rx, y0 + 330, ww, 22, S)
        rarity_gem(b, K, rx + 13, y0 + 341, 5.4, rar, S)
        text(b, rx + ww / 2 + 8, y0 + 345, word, f, S, fill="parch_dim" if rar == "common" else RARITY[rar],
             anchor="ms", tracking=2.4)
        rx += ww + 10
    for i in range(3):
        put(b, K, "frames/pchip", x0 + i * 40, y0 + 372, S=S)
        text(b, x0 + i * 40 + 15, y0 + 385, f"P{i + 2}", al(12, S, "Bold"), S, fill=PLAYER[i + 1], anchor="ms",
             shadow=False)
    tx, ty, tw, th = x0 + 140, y0 + 366, 390, 100
    box_shadow(b, tx, ty, tw, th, 6, S, dy=8, blur=18, alpha=0.75)
    body(b, tx, ty, tw, th, 6, S, alpha=0.97)
    put(b, K, "frames/tooltip", tx, ty, tw, th, S)
    text(b, tx + 18, ty + 30, "COLOSSUS CANNON", cz(15, S), S, fill="parch", tracking=1)
    text(b, tx + 18, ty + 52, "Stormcore · Ricochet · Nyctian Eye · Anvilheart", al(15, S), S, fill="parch_dim")
    w = text(b, tx + 18, ty + 80, "RAILSHOCK", cz(13, S), S, fill="ichor", tracking=2)
    text(b, tx + 18 + w + 30, ty + 80, "chains arc between marked foes", al(15, S, "Italic"), S, fill="parch_dim")


def end_card(b, K, x, y, pn, name, char, kills, share, mvp=False, S=1, w=300, h=314):
    """An end-screen party card (§7.3): gold panel + horns for the MVP, bronze for the rest."""
    if mvp:
        box_shadow(b, x, y, w, h, 10, S, dy=0, blur=16, alpha=0.45, color="#FFB23A", spread=2)
    box_shadow(b, x, y, w, h, 10, S, dy=8, blur=18, alpha=0.75)
    body(b, x, y, w, h, 10, S, alpha=0.95)
    put(b, K, "frames/gilt_panel" if mvp else "frames/gilt_panel_bronze", x, y, w, h, S)
    for c in ("tl", "tr", "bl", "br"):
        ox = x - 4 if c[1] == "l" else x + w - 40 + 4
        oy = y - 4 if c[0] == "t" else y + h - 40 + 4
        put(b, K, f"ornaments/forgehorn_40_{c}" if mvp else f"ornaments/forgehorn_bronze_40_{c}", ox, oy, S=S)
    pc = PLAYER[pn - 1]
    body(b, x + 14, y + 14, w - 28, 4, 1, S, top=pc, bot=pc, alpha=1.0)
    cx, cy = x + 56, y + 64
    box_shadow(b, cx - 34, cy - 34, 68, 68, 34, S, dy=3, blur=5, alpha=0.8)
    disc(b, cx, cy, 31.4, pc, S)
    disc(b, cx, cy, 28.8, "#140B06", S)
    disc(b, cx, cy, 28.0, "#3A2A1C", S)
    port = K.icon(f"portraits/{char.lower()}", int(56 * S), None)
    if port is not None:
        g = _grid(port.shape[1], port.shape[0])
        cl = np.clip(0.5 - (np.hypot(g[0] - port.shape[1] / 2, g[1] - port.shape[0] / 2) - 28 * S), 0, 1)
        b.put(port * cl[..., None], int((cx - 28) * S), int((cy - 28) * S))
    put(b, K, "slots/medallion_rim_68", cx - 34, cy - 34, S=S)
    put(b, K, "frames/pchip", cx - 15, y + 89, S=S)
    text(b, cx, y + 102, f"P{pn}", al(12, S, "Bold"), S, fill=pc, anchor="ms", shadow=False)
    text(b, x + 104, y + 62, name, al(22, S, "Bold"), S, fill="parch")
    text(b, x + 104, y + 84, char.upper(), cz(13, S), S, fill=pc, tracking=2.6)
    if mvp:
        bx_, by_ = x + w - 36, y + 34
        put(b, K, "slots/medallion_rim_34", bx_ - 17, by_ - 17, S=S)
        put(b, K, "fx/spark4", bx_ - 11, by_ - 11, 22, 22, S)
        text(b, bx_, by_ + 30, "MVP", cz(11, S), S, fill="gold_lt", anchor="ms", tracking=2)
    text(b, x + 24, y + 144, f"{kills}", cz(26, S), S, fill="numeral")
    text(b, x + 24, y + 160, "KILLS", cz(11, S), S, fill="parch_dim", tracking=2.4)
    text(b, x + w - 24, y + 144, f"{int(share * 100)}%", cz(26, S), S, fill="numeral", anchor="rs")
    text(b, x + w - 24, y + 160, "OF THE DAMAGE", cz(11, S), S, fill="parch_dim", anchor="rs", tracking=2.4)
    put(b, K, "bars/trough_thin", x + 9, y + 174, w - 18, 8, S)
    put(b, K, "bars/fill_white", x + 9.8, y + 174.8, (w - 19.6) * share / 0.44 * 0.95, 6.4, S, tint=pc)
    put(b, K, "bars/rim_thin", x + 9, y + 174, w - 18, 8, S)
    text(b, x + 24, y + 206, "THE WEAPON", cz(11, S), S, fill="parch_dim", tracking=2.4)
    slot(b, K, "hex_flat", x + 46, y + 238, 44, S, icon="chassis/colossus_cannon", fallback="cannon")
    for i, (shape, ic, fb, rar) in enumerate((("round", "slots/core", "core", "rare"),
                                             ("octagon", "slots/mechanism", "mechanism", "epic"),
                                             ("arch", "slots/relic", "relic", "rare"),
                                             ("lozenge", "slots/sigil", "sigil", "godforged"))):
        sx = x + 100 + i * 54
        slot(b, K, shape, sx, y + 238, 40, S, icon=ic, fallback=fb)
        rarity_gem(b, K, sx, y + 262, 4.4, rar, S)
    text(b, x + 24, y + 288, "BOONS", cz(11, S), S, fill="parch_dim", tracking=2.4)
    for i, gk in enumerate(("zephyros", "zephyros", "nyctia", "pyra")):
        put_icon(b, K, f"gods/{gk}", x + 104 + i * 30, y + 285, 24, S, fallback=gk, tint=GODS[gk][0])


# ───────────────────────────── the combat HUD ─────────────────────────────
def hearth(b, K, ox, oy, S=1):
    """The Hearth; (ox, oy) is the origin of its 1920x1080 frame (so the medallion is at ox+88, oy+980)."""
    radial(b, ox + 0, oy + 1080, 640, 250, "pool", 0.62, S)
    mx, my = ox + 88, oy + 980
    box_shadow(b, mx - 64, my - 64, 128, 128, 64, S, dy=3, blur=8, alpha=0.8)
    conic_ring(b, mx, my, 59.5, 54.5, 0.72, S)
    disc(b, mx, my, 52.7, PLAYER[0], S)            # the P band (code)
    disc(b, mx, my, 50.1, "#140B06", S)            # its separator
    Rp = 49.2
    W = int(2 * Rp * S)
    xx, yy = _grid(W, W)
    dd = np.hypot(xx - Rp * S, yy - Rp * S)
    rr = np.clip(np.hypot(xx - Rp * S, yy - Rp * S * 0.72) / (Rp * S), 0, 1)[..., None]
    win = c01("#5A3E27")[None, None, :] * (1 - rr) + c01("#100A07")[None, None, :] * rr
    b.put(layer(np.clip(0.5 - (dd - Rp * S), 0, 1), win), int((mx - Rp) * S), int((my - Rp) * S))
    port = K.icon("portraits/valdris", int(98 * S), "valdris", "#B08A52")
    if port is not None:
        g = _grid(int(98 * S), int(98 * S))
        cl = np.clip(0.5 - (np.hypot(g[0] - 49 * S, g[1] - 49 * S) - 49 * S), 0, 1)
        b.put(port * cl[..., None], int((mx - 49) * S), int((my - 49) * S))
    put(b, K, "slots/medallion_hearth", mx - 64, my - 64, S=S)
    keycap(b, K, mx, oy + 1046, "R", 21, S)
    slot(b, K, "round", ox + 137, oy + 931, 34, S, icon="kits/valdris_passive", fallback="reforged_flesh")
    put(b, K, "slots/medallion_rim_34", ox + 137 - 17, oy + 931 - 17, S=S)
    slot(b, K, "round", ox + 184, oy + 906, 28, S, icon="kits/valdris_e", fallback="siege_stance")
    conic_ring(b, ox + 184, oy + 906, 16, 14.6, 0.62, S, start_col="ichor", end_col="ichor", empty="#1A120B",
               meniscus=False)
    text(b, ox + 202, oy + 918, "6", al(14, S, "Bold"), S, fill="parch")
    hx, hy, hw, hh = ox + 170, oy + 928, 360, 22
    put(b, K, "bars/trough", hx, hy, hw, hh, S)
    f_hp, f_gh = 262 / 380, 300 / 380
    iw = hw - 2.8
    put(b, K, "bars/fill_ghost_hp", hx + 1.4, hy + 1.4, iw * f_gh, hh - 2.8, S)
    put(b, K, "bars/fill_hp", hx + 1.4, hy + 1.4, iw * f_hp, hh - 2.8, S)
    put(b, K, "bars/meniscus", hx + 1.4 + iw * f_hp - 4, hy + 1.4, 4, hh - 2.8, S)
    put(b, K, "fx/hatch_ward", hx + 1.4 + iw * f_gh, hy + 1.4, iw * 0.08, hh - 2.8, S, alpha=0.9)
    put(b, K, "bars/rim", hx, hy, hw, hh, S)
    put(b, K, "ornaments/finial_leaf", hx + hw - 4, hy, S=S)
    wmax = al(15, S, "Bold").getlength(" / 380") / S
    text(b, ox + 522, oy + 945, " / 380", al(15, S, "Bold"), S, fill="parch_dim", anchor="rs")
    text(b, ox + 522 - wmax, oy + 945, "262", al(19, S, "Bold"), S, fill="numeral", anchor="rs")
    put(b, K, "ornaments/hearth_rail", ox + 146, oy + 952, S=S)
    put(b, K, "ornaments/finial_lozenge", ox + 545, oy + 950, S=S)
    for i in range(6):
        put(b, K, "slots/armor_plate_full" if i < 4 else "slots/armor_plate_empty", ox + 170 + i * 38.5, oy + 962,
            35.5, 9, S)
    for i in range(3):
        put(b, K, "slots/dash_full" if i < 2 else "slots/dash_empty", ox + 524 - (2 - i) * 26 - 9, oy + 966 - 9, S=S)
    slot(b, K, "chamfer", ox + 200, oy + 1012, 60, S, icon="kits/valdris_q", fallback="bulwark_slam", glow=True)
    slot(b, K, "chamfer", ox + 272, oy + 1012, 60, S, icon="kits/valdris_e", fallback="siege_stance", state="cooling",
         sweep_left=0.42, cd_text="3.4")
    vx, vy, vs = ox + 352, oy + 1010, 68
    box_shadow(b, vx - vs / 2, vy - vs / 2, vs, vs, 20, S, dy=2.5, blur=5, alpha=0.7)
    put(b, K, "slots/slot_hex_pointy_fill", vx - vs / 2, vy - vs / 2, vs, vs, S)
    W = int(vs * S)
    mask = pv.stretch(K.img("slots/slot_hex_pointy_mask"), W, W)[..., 3]
    t = np.linspace(0, 1, W, dtype=np.float32)[:, None]
    lvl = 1 - 0.64
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :]
    wave = 0.012 * np.sin(xx * 3 * math.pi + 0.8)
    below = np.clip((t - lvl - wave) * W, 0, 1)
    depth = np.clip((t - lvl) / (1 - lvl), 0, 1)
    mol = np.stack([np.interp(depth, [0, .1, .35, .7, 1], [c01(h)[c] for h in
                                                              ("#FFFBEA", "#FFF6DA", "#FFC95A", "#E8942E", "#7A3E12")])
                    for c in range(3)], -1) * 0.85
    men = np.clip(1 - np.abs(t - lvl - wave) * W / (1.4 * S), 0, 1)
    b.put(layer(below * mask, mol), int((vx - vs / 2) * S), int((vy - vs / 2) * S))
    b.put(layer(men * mask, c01("#FFFBEA")), int((vx - vs / 2) * S), int((vy - vs / 2) * S))
    put_icon(b, K, "team/overdrive", vx, vy, 40, S, fallback="crucible", mul=(0.25, 0.14, 0.05))
    put(b, K, "slots/slot_hex_pointy_rim", vx - vs / 2, vy - vs / 2, vs, vs, S)
    for kx, lab in ((200, "Q"), (272, "E"), (352, "V")):
        keycap(b, K, ox + kx, oy + 1043, lab, 20, S)
    put_icon(b, K, "aim/auto", ox + 411, oy + 1004, 26, S, fallback="aim_auto")
    text(b, ox + 430, oy + 1009, "AUTO", cz(14, S), S, fill="parch", tracking=1.2)
    text(b, ox + 430, oy + 1027, "−10% dmg", al(15, S), S, fill="parch_dim")


def arsenal(b, K, ax, ay, S=1):
    """The Arsenal; (ax, ay) is the origin of its 1920x1080 frame."""
    radial(b, ax + 1920, ay + 1080, 520, 210, "pool", 0.6, S)
    for i, (shape, ic, fb, rar) in enumerate((("round", "slots/core", "core", "rare"),
                                             ("octagon", "slots/mechanism", "mechanism", "epic"),
                                             ("arch", "slots/relic", "relic", "rare"),
                                             ("lozenge", "slots/sigil", "sigil", "godforged"))):
        cx = ax + 1578 + i * 60
        slot(b, K, shape, cx, ay + 1014, 52, S, icon=ic, fallback=fb)
        rarity_gem(b, K, cx, ay + 1046, 5.4, rar, S)
    put_icon(b, K, "ui/lock", ax + 1778, ay + 993, 16, S, fallback="lock")
    cx, cy = ax + 1846, ay + 1006
    radial(b, cx, cy, 48, 48, ELEM["storm"], 0.30, S)
    slot(b, K, "hex_flat", cx, cy, 100, S, icon="chassis/colossus_cannon", fallback="cannon")
    slot(b, K, "round", ax + 1808, ay + 1040, 30, S, icon="elements/storm", fallback="storm", tint=ELEM["storm"])
    put_icon(b, K, "currency/godshard", ax + 1776, ay + 941, 28, S, fallback="godshard")
    text(b, ax + 1818, ay + 948, "30", cz(20, S), S, fill="numeral", anchor="rs")
    put_icon(b, K, "currency/ember", ax + 1846, ay + 941, 26, S, fallback="ember")
    text(b, ax + 1896, ay + 948, "74", cz(20, S), S, fill="numeral", anchor="rs")
    # the boon chip above the wallet
    gx, gy = ax + 1866, ay + 880
    radial(b, ax + 1760, gy, 180, 34, "pool", 0.62, S, power=1.2)
    box_shadow(b, gx - 30, gy - 30, 60, 60, 30, S, dy=2, blur=6, alpha=0.8)
    box_shadow(b, gx - 30, gy - 30, 60, 60, 30, S, dy=0, blur=12, alpha=0.45, color=GODS["pyra"][1], spread=1)
    put(b, K, "slots/enamel_disc", gx - 30, gy - 30, 60, 60, S, tint=GODS["pyra"][0])
    put_icon(b, K, "gods/pyra", gx, gy, 40, S, fallback="pyra", tint=GODS["pyra"][1])
    put(b, K, "slots/medallion_rim_60", gx - 30, gy - 30, S=S)
    text(b, ax + 1822, ay + 873, "PYRA OFFERS", cz(14, S), S, fill=GODS["pyra"][1], anchor="rs", tracking=2)
    text(b, ax + 1822, ay + 893, "a boon · 1 waiting", al(16, S), S, fill="parch_dim", anchor="rs")
    keycap(b, K, ax + 1690, ay + 882, "Tab", 22, S)


def boss_bar(b, K, bx, by, S=1):
    """The boss bar with the 620x18 bar at (bx, by)."""
    radial(b, bx + 310, by - 10, 490, 85, "pool", 0.7, S)
    text(b, bx + 310, by - 48, "WARLORD", cz(12, S), S, fill="#FF8A70", anchor="ms", tracking=4.8)
    text(b, bx + 310, by - 14, "THE BELLOWS", cz(30, S), S, fill="#FFD2A0", anchor="ms", tracking=3.6)
    ember_knot(b, K, bx + 60, by - 24, 150, S)
    ember_knot(b, K, bx + 560, by - 24, 150, S)
    bw, bh = 620, 18
    put(b, K, "bars/trough", bx, by, bw, bh, S)
    put(b, K, "bars/fill_ghost_boss", bx + 1.4, by + 1.4, (bw - 2.8) * 0.66, bh - 2.8, S)
    put(b, K, "bars/fill_boss", bx + 1.4, by + 1.4, (bw - 2.8) * 0.58, bh - 2.8, S)
    put(b, K, "bars/meniscus", bx + 1.4 + (bw - 2.8) * 0.58 - 4, by + 1.4, 4, bh - 2.8, S)
    put(b, K, "bars/rim", bx, by, bw, bh, S)
    put(b, K, "ornaments/boss_horn", bx - 30, by - 6, S=S)
    put(b, K, "ornaments/boss_horn", bx + bw - 4, by - 6, S=S, flip_x=True)
    for f in (0.66, 0.33):
        put(b, K, "ornaments/gem_ivory", bx + bw * f - 5, by - 5, 10, 10, S)
    put(b, K, "ornaments/gem_white", bx + bw / 2 - 5, by + bh - 5, 10, 10, S, tint="danger")
    text(b, bx + 310, by + 44, "II · BLAZE", cz(14, S), S, fill="#FFB08A", anchor="ms", tracking=3.4)


def party(b, K, px0, py0, S=1):
    radial(b, px0 - 24, py0 - 24, 420, 200, "pool", 0.55, S, power=1.4)
    for i, (nm, ch, hpf) in enumerate((("Bot 2", "SELENE", 0.92), ("Bot 3", "KAEL", 0.61), ("Bot 4", "SELENE", 0.34))):
        yy_ = py0 + i * 54
        cxm, cym = px0 + 23, yy_ + 23
        box_shadow(b, cxm - 23, cym - 23, 46, 46, 23, S, dy=2, blur=4, alpha=0.8)
        disc(b, cxm, cym, 20.8, PLAYER[i + 1], S)
        disc(b, cxm, cym, 18.2, "#140B06", S)
        disc(b, cxm, cym, 17.4, "#3A2A1C", S)
        port = K.icon(f"portraits/{ch.lower()}", int(36 * S), None)
        if port is not None:
            g = _grid(port.shape[1], port.shape[0])
            cl = np.clip(0.5 - (np.hypot(g[0] - port.shape[1] / 2, g[1] - port.shape[0] / 2) - 17.4 * S), 0, 1)
            b.put(port * cl[..., None], int((cxm - 18) * S), int((cym - 18) * S))
        put(b, K, "slots/medallion_rim_46", cxm - 23, cym - 23, S=S)
        put(b, K, "frames/pchip", cxm - 15, yy_ + 37, S=S)
        text(b, cxm, yy_ + 50, f"P{i + 2}", al(12, S, "Bold"), S, fill=PLAYER[i + 1], anchor="ms", shadow=False)
        text(b, px0 + 57, yy_ + 19, nm, al(18, S, "Bold"), S, fill="parch")
        text(b, px0 + 57 + al(18, S, "Bold").getlength(nm) / S + 9, yy_ + 19, ch, cz(12, S), S, fill="parch_dim",
             tracking=1.8)
        put(b, K, "bars/trough_thin", px0 + 57, yy_ + 28, 170, 8, S)
        put(b, K, "bars/fill_ghost_hp", px0 + 57.8, yy_ + 28.8, 168.4 * min(1, hpf + 0.08), 6.4, S)
        put(b, K, "bars/fill_hp", px0 + 57.8, yy_ + 28.8, 168.4 * hpf, 6.4, S)
        put(b, K, "bars/rim_thin", px0 + 57, yy_ + 28, 170, 8, S)


def pins_prompt(b, K, x0, y0, S=1):
    """Edge pins (gilt / shrine / ally / downed), a prompt plate with a hold ring, an ally tag."""
    for i, (kind, ang, col, key, fb, lab) in enumerate((("gilt", 35, None, "poi/anvil", "anvil", "58 m"),
                                                        ("gilt", -60, None, "poi/shrine", "shrine", "96 m"),
                                                        ("tint", 140, PLAYER[2], "portraits/kael", None, "P3"),
                                                        ("tint", 200, "danger", "states/downed", "skull", "8 s"))):
        cx, cy = x0 + i * 70, y0
        put(b, K, "markers/pin_disc", cx - 17, cy - 17, S=S)
        put_icon(b, K, key, cx, cy, 24, S, fallback=fb, tint="#E6CFA0",
                 mul=(c01(GODS["pyra"][1]) if key == "poi/shrine" else None))
        img = K.img(f"markers/pin_frame_{kind}").rotate(-ang, resample=Image.BICUBIC)
        arr = pv.stretch(img, int(56 * S), int(56 * S))
        b.put(arr, int((cx - 28) * S), int((cy - 28) * S), 1.0, None if col is None else c01(col))
        text(b, cx, cy + 44, lab, al(14, S, "Bold"), S, fill="parch", anchor="ms")
    # prompt plate
    ppx, ppy, ppw = x0 + 320, y0 - 24, 256
    box_shadow(b, ppx, ppy, ppw, 44, 6, S, dy=3, blur=9, alpha=0.55)
    body(b, ppx, ppy, ppw, 44, 6, S, alpha=0.8)
    cov = rrect_cov(int(ppw * S), int(44 * S), 6 * S)
    inner = np.zeros_like(cov)
    ii = rrect_cov(int((ppw - 2.2) * S), int((44 - 2.2) * S), 4.9 * S)
    inner[int(1.1 * S):int(1.1 * S) + ii.shape[0], int(1.1 * S):int(1.1 * S) + ii.shape[1]] = ii
    rimc = vgrad(cov.shape[0], cov.shape[1], "gold_lt", "gold_dk")
    b.put(layer(np.clip(cov - inner, 0, 1), rimc, 0.7), int(ppx * S), int(ppy * S))
    put(b, K, "markers/prompt_tail", ppx + ppw / 2 - 7, ppy + 43, S=S)
    conic_ring(b, ppx + 24, ppy + 22, 15, 13.2, 0.55, S, start_col="gold_lt", end_col="gold_lt", empty="#0A0706",
               meniscus=False)
    keycap(b, K, ppx + 24, ppy + 22, "F", 20, S, pressed=True)
    text(b, ppx + 48, ppy + 21, "KINDLE THE ANVIL", cz(16, S), S, fill="gold_lt", tracking=1.3)
    text(b, ppx + 48, ppy + 37, "Anvil · 1 Seal", al(14, S), S, fill="parch_dim")
    # ally tag
    tx, ty = x0 + 660, y0 - 6
    body(b, tx - 44, ty - 30, 88, 19, 9.5, S, top="#0C0806", bot="#0C0806", alpha=0.72)
    disc(b, tx - 33, ty - 20.5, 3.5, PLAYER[2], S)
    text(b, tx + 4, ty - 15.5, "Bot 3", al(14, S, "Bold"), S, fill="parch", anchor="ms")
    put(b, K, "bars/fill_hp", tx - 23, ty - 6, 46 * 0.45, 6, S)
    put(b, K, "markers/ally_chevron", tx - 4, ty + 2, S=S, tint=PLAYER[2])


def wayfinder(b, K, rx, y0, S=1):
    """Minimap frame + a few tracker rows, right-aligned at rx."""
    mmx, mmy, mmw, mmh = rx - 280, y0, 280, 176
    radial(b, rx + 24, y0 - 24, 520, 420, "pool", 0.55, S, power=1.4)
    W, H = int(mmw * S), int(mmh * S)
    n = ndimage.gaussian_filter(np.random.default_rng(4).standard_normal((H, W)).astype(np.float32), 9 * S)
    n = (n - n.min()) / (n.max() - n.min())
    sep = np.stack([np.interp(n, [0, .45, .7, 1], [c01(h)[c] for h in ("#140E0A", "#463424", "#967650", "#E2C896")])
                    for c in range(3)], -1)
    b.put(layer(rrect_cov(W, H, 9 * S), sep), int(mmx * S), int(mmy * S))
    for i, (dxm, dym) in enumerate(((140, 88), (120, 70), (170, 100), (150, 120))):
        disc(b, mmx + dxm, mmy + dym, 4 if i == 0 else 3.2, PLAYER[i], S)
    put(b, K, "frames/minimap_frame", mmx - 3, mmy - 3, S=S)
    ty = y0 + 218
    text(b, rx, ty + 24, "07:32", cz(24, S), S, fill="numeral", anchor="rs")
    put_icon(b, K, "run/hourglass", rx - 92, ty + 16, 18, S, fallback="doom")
    text(b, rx - 108, ty + 22, "CINDER WASTES", cz(14, S), S, fill="parch_dim", anchor="rs", tracking=2.2)
    put(b, K, "ornaments/emberknot_rule", rx - 280, ty + 27, 280, 14, S, flip_x=True)
    for i in range(7):
        cx = rx - 60 - i * 24
        if i < 4:
            put(b, K, "slots/gem_socket_round", cx - 8.5, ty + 58 - 8.5, 17, 17, S)
        else:
            put_icon(b, K, "currency/seal", cx, ty + 58, 24, S, fallback="seal")
    text(b, rx, ty + 65, "3/7", cz(19, S), S, fill="gold_lt", anchor="rs")
    for i in range(5):
        put(b, K, f"markers/threat_pip_{'lit' if i < 3 else 'dark'}", rx - 17 * (5 - i), ty + 86, S=S)
    text(b, rx - 94, ty + 97, "THREAT III", cz(14, S), S, fill="parch_dim", anchor="rs", tracking=2)


def hud(b, K, x0, y0, w, h, S=1):
    """A 1920-wide HUD folded into a (w x h) strip: the clusters keep their corner anchors."""
    party(b, K, x0 + 24, y0 + 24, S)
    boss_bar(b, K, x0 + w / 2 - 310, y0 + 86, S)
    wayfinder(b, K, x0 + w - 24, y0 + 24, S)
    hearth(b, K, x0, y0 + h - 1080, S)
    arsenal(b, K, x0 + w - 1920, y0 + h - 1080, S)
    pins_prompt(b, K, x0 + w / 2 - 330, y0 + h - 170, S)


# ───────────────────────────── the sheet ─────────────────────────────
def raw_grid(b, K, x0, y0, width, S=1, draw=True):
    """Every texture grouped by folder: pieces at their logical size (UiScale 1, sampled like Bevy),
    tiny ones (under 40 px) doubled (2x, marked), big ones as thumbnails (%); sized variants once."""
    groups = {}
    for n in K.man:
        if any(n.endswith(f"_{c}") for c in ("tr", "bl", "br")):
            continue
        groups.setdefault(n.split("/")[0], []).append(n)
    order = ["frames", "ornaments", "slots", "bars", "markers", "fx"]
    y = y0
    for g in order:
        names = groups.get(g, [])
        if not names:
            continue
        if draw:
            text(b, x0, y + 18, g.upper() + "/", cz(14, S), S, fill="gold_lt", tracking=2.4)
        y += 30
        cx = x0
        line_h = 0
        for n in names:
            m = K.meta(n)
            lw, lh = m["logical_size"]
            dw, dh = lw, lh
            zoom = 1
            if m["mode"] == "nine_slice" and lw < 100:   # slices shown stretched, as used
                dw = max(lw * 2, 96)
                dh = max(lh, 44) if lh < 44 else lh
            elif max(lw, lh) < 40:
                zoom = 2
                dw, dh = lw * 2, lh * 2
            box = 150 if max(lw, lh) < 300 else 170
            sc = min(1.0, box / dw, box / dh)
            dw, dh = dw * sc, dh * sc
            wcell = max(118, dw + 18)
            if cx + wcell > x0 + width:
                cx = x0
                y += line_h + 34
                line_h = 0
            if draw:
                tint = None
                t = str(m.get("tint") or "")
                if "god" in t:
                    tint = GODS["zephyros"][0]
                elif "ready" in t:
                    tint = "ready_glow"
                elif "player" in t:
                    tint = PLAYER[1]
                ox = cx + (wcell - dw) / 2
                if sc < 1.0:   # thumbnails: a proper downscale (not what the game does)
                    im = K.img(n).resize((max(1, int(dw * S)), max(1, int(dh * S))), Image.LANCZOS)
                    arr = pv.premul(im)
                    if tint:
                        arr = arr.copy()
                        arr[..., :3] *= c01(tint)
                    b.put(arr, int(ox * S), int(y * S))
                elif zoom == 2:
                    put(b, K, n, ox / 2, y / 2, lw, lh, 2 * S, tint=tint)
                else:
                    put(b, K, n, ox, y, dw, dh, S, tint=tint)
                short = n.split("/", 1)[1]
                label = short if sc >= 0.999 else f"{short} ({int(round(sc * 100))}%)"
                if zoom == 2:
                    label += " (2x)"
                f = al(11, S)
                while f.getlength(label) / S > wcell - 4 and len(label) > 8:
                    label = label[:-2]
                text(b, cx + wcell / 2, y + dh + 15, label, f, S, fill="parch_mute", anchor="ms", shadow=False)
            line_h = max(line_h, dh)
            cx += wcell
        y += line_h + 44
    return y


def lacquer_bg(W, H, seed=3):
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    col = c01("#1B130E")[None, None, :] * (1 - y) + c01("#0B0807")[None, None, :] * y
    rng = np.random.default_rng(seed)
    st = ndimage.gaussian_filter1d(rng.standard_normal(H).astype(np.float32), 1.2)
    st /= np.abs(st).max() + 1e-6
    col = col + (st * 4 / 255)[:, None, None]
    out = np.ones((H, W, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 1)
    return out


def plate_bg(W, H, dim=0.0):
    """A real game frame behind the demos: tools/ui/plates/battle_plate.jpg is an 850x560 HUD-free crop
    of an in-game capture (Cinder Wastes, --autoplay --bots 3 --horde 300, seed 7), scaled to cover."""
    p = Image.open(os.path.join(ROOT, "tools", "ui", "plates", "battle_plate.jpg")).convert("RGB")
    sc = max(W / p.width, H / p.height)
    p = p.resize((int(math.ceil(p.width * sc)), int(math.ceil(p.height * sc))), Image.LANCZOS)
    p = p.crop(((p.width - W) // 2, (p.height - H) // 2, (p.width - W) // 2 + W, (p.height - H) // 2 + H))
    a = np.ones((H, W, 4), np.float32)
    a[..., :3] = np.asarray(p, np.float32) / 255 * (1 - dim)
    return a


def section_title(b, x, y, title, sub=""):
    text(b, x, y, title, cz(20), 1, fill="gold_lt", tracking=4)
    if sub:
        w = cz(20).getlength(title) + 4 * len(title)
        text(b, x + w + 18, y, sub, al(15, 1, "Italic"), 1, fill="parch_dim")


def build(out_dir, path):
    K = Kit(out_dir)
    W = 2400
    grid_h = raw_grid(None, K, 40, 0, W - 80, draw=False)
    rows = [("head", 120), ("boons", 600), ("panels", 640), ("hud", 720), ("zoom", 520), ("kit", grid_h + 70)]
    H = int(sum(h for _, h in rows) + 20)
    b = pv.Board(W, H, bg=(0, 0, 0, 1.0))
    b.p[...] = lacquer_bg(W, H)
    y = 0
    # header
    text(b, 40, 62, "GODFORGE · UI TEXTURE KIT", cz(40), 1, fill="gold_lt", tracking=6)
    text(b, 40, 92, "assets/ui/*@2x.png · shown at UiScale 1.0 and sampled like Bevy (linear, no mips; @2x slices at "
         "max_corner_scale 0.5) · close-ups at UiScale 2.0 · generated by tools/ui/make_ui_kit.py",
         al(16, 1, "Italic"), 1, fill="parch_dim")
    ember_knot(b, K, W / 2, 110, W - 80, 1, gem="ivory")
    y += 120
    # row: boon cards over a dimmed plate (the spread's 0.64 spotlight dim)
    section_title(b, 40, y + 30, "BOON CARDS", "niche body, glow and hairline tinted by the god colour · frame by "
                                               "rarity · enamel + rim medallions · ribbon · ember-knot")
    b.put(plate_bg(W - 80, 540, dim=0.62), 40, y + 50)
    cards = [(("zephyros",), "common", "Stormbrand", ["+15% damage; hits have a", "25% chance to Shock."], None, "NEW",
              0, ("boons/stormbrand", "storm")),
             (("zephyros",), "rare", "Leaping Arc", ["Hits arc to 2 more enemies;", "each jump deals half the",
                                                     "damage of the last."], None, "UPGRADE", 2,
              ("boons/leaping_arc", "storm")),
             (("zephyros", "nyctia"), "epic", "Silent Thunder", ["+12% crit chance; +30%", "damage to Shocked enemies."],
              "Duo", "NEW", 0, ("boons/silent_thunder", "nyctia")),
             (("seraphel",), "godforged", "Last Light", ["Every 8th hit calls a", "sunbeam for 400% damage."],
              "Legendary", "NEW", 0, ("boons/last_light", "radiant")),
             (("pyra",), "rare", "Blastfire", ["Kills explode for 20% of", "the victim's max health."], None, "NEW", 1,
              ("boons/blastfire", "flame"))]
    for i, (gods, rar, nm, desc, kind, tag, pips, ic) in enumerate(cards):
        niche_card(b, K, 80 + i * 452, y + 130, list(gods), rar, nm, desc, kind=kind, key=str(i + 1), tag=tag,
                   pips=pips, S=1, hover=(i == 1), icon=ic)
    y += 600
    # row: the Forge drawer + widget states
    section_title(b, 40, y + 30, "PANELS & WIDGETS", "gilt panel 9-slice + forge-horns + sun-crest · rarity cards · "
                                                     "selection ring · buttons, chips, keys, pills, ribbons, tooltip · "
                                                     "end-screen cards (MVP gold, others bronze)")
    b.put(plate_bg(W - 80, 580, dim=0.4), 40, y + 50)
    forge_panel(b, K, 110, y + 94)
    states_panel(b, K, 1110, y + 94)
    end_card(b, K, 1738, y + 150, 1, "Host", "VALDRIS", 1204, 0.44, mvp=True)
    end_card(b, K, 2052, y + 150, 2, "Bot 2", "SELENE", 861, 0.31)
    y += 640
    # row: the HUD over the live plate
    section_title(b, 40, y + 30, "COMBAT HUD", "the Hearth · the Arsenal · boon chip · boss bar · party · wayfinder · "
                                               "pins · prompt — over a real frame of a 300-enemy fight")
    b.put(plate_bg(W - 80, 660, dim=0.0), 40, y + 50)
    hud(b, K, 40, y + 50, W - 80, 660)
    y += 720
    # row: close-ups at UiScale 2.0
    section_title(b, 40, y + 30, "CLOSE-UPS AT UISCALE 2.0", "the same textures 1:1 — the 4K view")
    b.put(plate_bg(W - 80, 460, dim=0.45), 40, y + 50)
    z = pv.Board(760, 440)
    hearth(z, K, -6, -864, S=2)
    b.put(z.p, 50, y + 60)
    z = pv.Board(760, 440)
    forge_panel(z, K, -250, 44, S=2)
    b.put(z.p, 820, y + 60)
    z = pv.Board(760, 440)
    niche_card(z, K, 40, 48, ["zephyros", "nyctia"], "epic", "Silent Thunder", ["+12% crit chance; +30%"], kind="Duo",
               S=2, icon=("boons/silent_thunder", "nyctia"))
    b.put(z.p, 1590, y + 60)
    y += 520
    # row: the raw kit
    section_title(b, 40, y + 30, "THE KIT", "every texture; small ones at their logical size (UiScale 1), big ones as "
                                            "thumbnails (%); forge-horns show one corner; tintable pieces tinted")
    raw_grid(b, K, 40, y + 56, W - 80)
    img = b.image().convert("RGB")
    img.save(path, optimize=True)
    return img
