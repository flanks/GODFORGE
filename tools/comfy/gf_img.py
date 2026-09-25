"""Small image helpers shared by the stage-0 sheet tools (palette_extract.py, readability_sheet.py).

Needs PIL + numpy, so run the tools with ComfyUI's standalone python:
  D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe
Nothing here talks to ComfyUI itself; it only borrows that interpreter.
"""
import hashlib
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT_DIR = os.path.join(ROOT, "assets", "fonts")   # DejaVu, bundled with the game (redistributable)


def rel(path):
    """Repo-relative path with forward slashes (what the JSON files store)."""
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


def absp(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path.replace("/", os.sep))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def font(size, bold=False):
    name = "DejaVuSerif-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(int(round(float(c))) for c in rgb)


def srgb_to_lab(rgb):
    """sRGB (0-255, any leading shape, last axis 3) -> CIELAB D65 (L* 0-100)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lstar_gray(rgb_u8):
    """Greyscale image whose grey level is L* (perceptual value), for value checks."""
    L = srgb_to_lab(rgb_u8)[..., 0]
    # grey sRGB level that has this L*: invert the L* curve through Y
    Y = np.where(L > 8, ((L + 16) / 116) ** 3, L / 903.3)
    s = np.where(Y <= 0.0031308, 12.92 * Y, 1.055 * np.power(np.clip(Y, 0, None), 1 / 2.4) - 0.055)
    return np.clip(s * 255 + 0.5, 0, 255).astype(np.uint8)


def hsv_arrays(rgb_u8):
    a = rgb_u8.astype(np.float32) / 255.0
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    safe = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / safe) % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4)) * 60.0
    h = np.where(d < 1e-4, 0.0, h)
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx


def background_rgb(rgb_u8, patch=40):
    """Median of the four corner patches: the flat sheet background."""
    p = patch
    corners = np.concatenate([rgb_u8[:p, :p].reshape(-1, 3), rgb_u8[:p, -p:].reshape(-1, 3),
                              rgb_u8[-p:, :p].reshape(-1, 3), rgb_u8[-p:, -p:].reshape(-1, 3)])
    return np.median(corners.astype(np.float32), axis=0)


def figure_mask(rgb_u8, bg, threshold=12.0):
    """Foreground of a character plate on a flat background, holes filled.

    Pixels farther than `threshold` (RGB distance) from the background are figure; background
    pockets NOT connected to the image border (between fingers, under the arm) stay figure only if
    enclosed, which is what a silhouette wants."""
    dist = np.sqrt(((rgb_u8.astype(np.float32) - bg) ** 2).sum(-1))
    fg = dist > threshold
    # flood the background from a 1 px frame around the image (PIL's C flood fill)
    h, w = fg.shape
    m = Image.new("L", (w + 2, h + 2), 0)
    m.paste(Image.fromarray((fg * 255).astype(np.uint8), "L"), (1, 1))
    ImageDraw.floodfill(m, (0, 0), 128, thresh=0)
    outside = np.asarray(m)[1:-1, 1:-1] == 128
    return ~outside


def cutout(rgb_u8, mask):
    """RGBA image of the figure with a hard alpha from the mask."""
    rgba = np.dstack([rgb_u8, (mask * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA")


def fit_height(img_rgba, height, bbox=None):
    """Crop to the alpha bbox (or `bbox`) and resize to `height` px tall, premultiplied Lanczos."""
    box = bbox or img_rgba.getbbox()
    c = img_rgba.crop(box)
    w = max(1, round(c.width * height / c.height))
    return c.convert("RGBa").resize((w, height), Image.LANCZOS).convert("RGBA")


def text(draw, xy, s, size=16, bold=False, fill=(230, 226, 214), anchor="la"):
    draw.text(xy, s, font=font(size, bold), fill=fill, anchor=anchor)


def text_w(s, size=16, bold=False):
    return font(size, bold).getlength(s)


def ink_on(rgb):
    """Readable text colour on top of a swatch."""
    return (20, 18, 16) if srgb_to_lab(np.array(rgb, dtype=np.float64))[0] > 58 else (240, 236, 226)


def new_sheet(w, h, bg=(24, 22, 26)):
    im = Image.new("RGB", (w, h), bg)
    return im, ImageDraw.Draw(im)
