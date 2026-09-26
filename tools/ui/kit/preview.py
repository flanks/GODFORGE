"""Preview helpers: render kit textures the way Bevy's UI renderer will, for the contact sheet.

- `sample()` is GPU-style bilinear sampling (one bilinear tap per output px, texel centres, clamp to
  edge, premultiplied), i.e. what a linear sampler does with no mipmaps. Minifying a texture more
  than 2x therefore aliases here exactly as it will in game, which is the point.
- `nine_slice()` follows UI_STYLE §8.2: corners are drawn at border x min(target/image,
  max_corner_scale) of the texture size, sides and centre stretch (or tile).
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
FONTS = os.path.join(ROOT, "assets", "fonts")


def premul(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("RGBA"), np.float32) / 255.0
    a[..., :3] *= a[..., 3:]
    return a


def unpremul(p: np.ndarray) -> Image.Image:
    a = p[..., 3:]
    rgb = np.where(a > 1e-6, p[..., :3] / np.maximum(a, 1e-6), 0)
    out = np.concatenate([rgb, a], -1)
    return Image.fromarray(np.clip(np.round(out * 255), 0, 255).astype(np.uint8), "RGBA")


def sample(src: np.ndarray, sx0, sy0, sx1, sy1, dw: int, dh: int) -> np.ndarray:
    """Bilinear-sample the texel rect [sx0, sx1) x [sy0, sy1) of a premultiplied texture into dw x dh."""
    h, w = src.shape[:2]
    if dw <= 0 or dh <= 0:
        return np.zeros((max(dh, 0), max(dw, 0), 4), np.float32)
    u = sx0 + (np.arange(dw, dtype=np.float32) + 0.5) * (sx1 - sx0) / dw - 0.5
    v = sy0 + (np.arange(dh, dtype=np.float32) + 0.5) * (sy1 - sy0) / dh - 0.5
    u = np.clip(u, 0, w - 1)
    v = np.clip(v, 0, h - 1)
    u0 = np.floor(u).astype(int)
    v0 = np.floor(v).astype(int)
    u1 = np.minimum(u0 + 1, w - 1)
    v1 = np.minimum(v0 + 1, h - 1)
    fu = (u - u0)[None, :, None]
    fv = (v - v0)[:, None, None]
    a = src[v0][:, u0]
    b = src[v0][:, u1]
    c = src[v1][:, u0]
    d = src[v1][:, u1]
    return (a * (1 - fu) + b * fu) * (1 - fv) + (c * (1 - fu) + d * fu) * fv


def stretch(img: Image.Image, dw: int, dh: int, flip_x=False, flip_y=False) -> np.ndarray:
    p = premul(img)
    if flip_x:
        p = p[:, ::-1]
    if flip_y:
        p = p[::-1]
    return sample(p, 0, 0, p.shape[1], p.shape[0], dw, dh)


def nine_slice(img: Image.Image, border, dw: int, dh: int, corner_scale: float = 0.5, tile_sides: bool = False,
               tile_px: float | None = None) -> np.ndarray:
    """border = (left, top, right, bottom) texture px; dw/dh output px; corner_scale = the
    texture-to-output factor for corners (0.5 at UiScale 1 for @2x art, 1.0 at UiScale 2)."""
    p = premul(img)
    ih, iw = p.shape[:2]
    b_l, b_t, b_r, b_b = border
    s = min(corner_scale, dw / iw, dh / ih)   # corner = border x min(target / image, max_corner_scale)
    L, T, R, B = [int(round(v * s)) for v in (b_l, b_t, b_r, b_b)]
    out = np.zeros((dh, dw, 4), np.float32)
    xs_src = [0, b_l, iw - b_r, iw]
    ys_src = [0, b_t, ih - b_b, ih]
    xs_dst = [0, L, dw - R, dw]
    ys_dst = [0, T, dh - B, dh]
    for j in range(3):
        for i in range(3):
            dx0, dx1 = xs_dst[i], xs_dst[i + 1]
            dy0, dy1 = ys_dst[j], ys_dst[j + 1]
            if dx1 <= dx0 or dy1 <= dy0:
                continue
            sx0, sx1 = xs_src[i], xs_src[i + 1]
            sy0, sy1 = ys_src[j], ys_src[j + 1]
            if tile_sides and (i == 1 or j == 1) and not (i == 1 and j == 1):
                # tile along the side's long axis at the corner scale
                if i == 1:
                    tw = int(round((sx1 - sx0) * s if tile_px is None else tile_px))
                    seg = sample(p, sx0, sy0, sx1, sy1, tw, dy1 - dy0)
                    reps = int(np.ceil((dx1 - dx0) / tw)) + 1
                    out[dy0:dy1, dx0:dx1] = np.tile(seg, (1, reps, 1))[:, :dx1 - dx0]
                else:
                    th = int(round((sy1 - sy0) * s if tile_px is None else tile_px))
                    seg = sample(p, sx0, sy0, sx1, sy1, dx1 - dx0, th)
                    reps = int(np.ceil((dy1 - dy0) / th)) + 1
                    out[dy0:dy1, dx0:dx1] = np.tile(seg, (reps, 1, 1))[:dy1 - dy0]
                continue
            out[dy0:dy1, dx0:dx1] = sample(p, sx0, sy0, sx1, sy1, dx1 - dx0, dy1 - dy0)
    return out


def three_slice_h(img: Image.Image, right: int, dw: int, dh: int, scale: float = 0.5, flip_x=False) -> np.ndarray:
    """The ember-knot rule: stretch the left part, keep the right `right` texels at `scale`."""
    p = premul(img)
    if flip_x:
        p = p[:, ::-1]
    ih, iw = p.shape[:2]
    R = int(round(right * scale))
    out = np.zeros((dh, dw, 4), np.float32)
    if flip_x:
        out[:, :R] = sample(p, 0, 0, right, ih, R, dh)
        out[:, R:] = sample(p, right, 0, iw, ih, dw - R, dh)
    else:
        out[:, :dw - R] = sample(p, 0, 0, iw - right, ih, dw - R, dh)
        out[:, dw - R:] = sample(p, iw - right, 0, iw, ih, R, dh)
    return out


class Board:
    """A premultiplied RGBA board for the contact sheet."""

    def __init__(self, w: int, h: int, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.p = np.zeros((h, w, 4), np.float32)
        if bg[3]:
            self.p[...] = np.array([bg[0] * bg[3], bg[1] * bg[3], bg[2] * bg[3], bg[3]], np.float32)

    def put(self, layer: np.ndarray, x: int, y: int, alpha: float = 1.0, tint=None):
        lay = layer
        if tint is not None:
            lay = layer.copy()
            lay[..., :3] *= np.asarray(tint, np.float32)[None, None, :]
        if alpha != 1.0:
            lay = lay * alpha
        h, w = lay.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        s = lay[y0 - y:y1 - y, x0 - x:x1 - x]
        d = self.p[y0:y1, x0:x1]
        self.p[y0:y1, x0:x1] = s + d * (1 - s[..., 3:])

    def put_img(self, img: Image.Image, x: int, y: int, alpha=1.0):
        self.put(premul(img), x, y, alpha)

    def image(self) -> Image.Image:
        return unpremul(self.p)


_FONT_CACHE: dict = {}


def font(name: str, size: int, weight: int | None = None):
    key = (name, size, weight)
    if key not in _FONT_CACHE:
        f = ImageFont.truetype(os.path.join(FONTS, name), size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


def cinzel(size: int, weight: int = 800):
    return font("Cinzel-Variable.ttf", size, weight)


def body(size: int, face: str = "Medium"):
    return font(f"AlegreyaSans-{face}.ttf", size)


def text(board: Board, xy, s: str, f, fill=(244, 230, 200), anchor="la", shadow=True, tracking: float = 0.0):
    """Draw text on the board (straight RGBA layer composited premultiplied)."""
    x, y = xy
    if tracking:
        width = f.getlength(s) + tracking * (len(s) - 1)
    else:
        width = f.getlength(s)
    asc, desc = f.getmetrics()
    lay = Image.new("RGBA", (int(width) + 12, asc + desc + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    if tracking:
        for i, c in enumerate(s):   # kerning-aware: the prefix advance includes pair kerning
            x0 = f.getlength(s[:i + 1]) - f.getlength(c)
            d.text((6 + x0 + tracking * i, 6), c, font=f, fill=fill + (255,))
    else:
        d.text((6, 6), s, font=f, fill=fill + (255,))
    ox = {"l": 0, "m": width / 2, "r": width}[anchor[0]]
    oy = {"a": 0, "m": (asc + desc) / 2, "s": asc}[anchor[1]]
    px, py = int(round(x - ox - 6)), int(round(y - oy - 6))
    if shadow:
        sh = Image.new("RGBA", lay.size, (10, 7, 6, 0))
        sh.putalpha(lay.split()[3].point(lambda v: int(v * 0.9)))
        board.put_img(sh, px, py + 2)
    board.put_img(lay, px, py)
    return width
