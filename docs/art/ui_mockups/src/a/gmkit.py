"""GILDED MYTHIC UI kit: procedural gilded frames, lacquer panels, gems, filigree, bars and text
for GODFORGE mockups. Everything is original vector/procedural work (no traced references).

Units: callers work in 1080p "UI px". Every primitive renders supersampled (SS) and returns an
RGBA PIL image at final size, so it can be pasted at integer positions onto a 1920x1080 layer.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

import os
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', '..', 'assets', 'fonts') + '/'
SS = 3  # supersampling factor for shapes

# ───────────────────────────── colour tokens ─────────────────────────────
TOK = {
    # lacquer
    "lac0": "#0D0907", "lac1": "#16100C", "lac2": "#211813", "lac3": "#2E221A", "oxblood": "#2A0F0C",
    # chrome gold (metal ramp anchors)
    "g_shadow": "#2A1A0B", "g_dark": "#5C3D18", "g_mid": "#A67B3A", "g_light": "#D9B56C", "g_hi": "#F6E3AE",
    "keyline": "#8C6A36", "keyline_hi": "#C9A45C",
    # text
    "parch": "#F2E6CE", "parch_dim": "#B9A98C", "parch_faint": "#7D705E", "ink": "#0A0706",
    "ichor": "#FFE9B0", "ichor_glow": "#FFC873", "ash_rose": "#C48B7E",
    # vitals
    "hp_lo": "#6E0E16", "hp_mid": "#B8232F", "hp_hi": "#E0524F", "hp_ghost": "#F2C58A",
    "armor_lo": "#5B6066", "armor_hi": "#C2C7CB", "shield": "#CFE0EA",
    "molten_lo": "#C9822E", "molten_mid": "#FFD27A", "molten_hi": "#FFF6DA",
    # danger (telegraph red-white, only for real danger)
    "danger": "#FF3B30",
}
RARITY = {"common": "#CFC6B4", "rare": "#4FA3FF", "epic": "#B865FF", "godforged": "#FFB82E"}
ELEMENT = {"kinetic": "#F4E3C1", "flame": "#FF7A1A", "storm": "#3FD8FF", "void": "#A45CFF",
           "plague": "#86E03A", "radiant": "#FFE27A"}
PLAYER = ["#FFC940", "#3FD8FF", "#B06CFF", "#5BE37D"]
GODS = {
    "pyra": ("Pyra", "#E0312B", "#FFC23D", "Flame, Wrath"),
    "zephyros": ("Zephyros", "#3FD8FF", "#F2FBFF", "Storm, Sky"),
    "nyctia": ("Nyctia", "#7B3FE0", "#141018", "Shadow, Silence"),
    "aeon": ("Aeon", "#C9D2DC", "#8A96A3", "Time, Fate"),
    "gaiaa": ("Gaiaa", "#4E9A3A", "#B07A3C", "Stone, Blood"),
    "morwenn": ("Morwenn", "#1FA39A", "#7FE36B", "Sea, Plague"),
    "seraphel": ("Seraphel", "#FFD86B", "#FFFFFF", "Light, Law"),
    "umbra_rex": ("Umbra-Rex", "#8E1B1B", "#FF6A2A", "Ruin, End"),
}


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h: str, a: float = 1.0) -> tuple[int, int, int, int]:
    return (*rgb(h), int(round(a * 255)))


def mix(a: str, b: str, t: float) -> str:
    ca, cb = rgb(a), rgb(b)
    return "#%02X%02X%02X" % tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))


# ───────────────────────────── fonts ─────────────────────────────
@lru_cache(maxsize=None)
def cinzel(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONTS + "Cinzel-Variable.ttf", size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


@lru_cache(maxsize=None)
def sans(size: int, style: str = "Regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS + f"AlegreyaSans-{style}.ttf", size)


@lru_cache(maxsize=None)
def dejavu(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONTS + ("DejaVuSerif-Bold.ttf" if bold else "DejaVuSans.ttf"), size)


# ───────────────────────────── helpers ─────────────────────────────
def blank(w: int, h: int, color=(0, 0, 0, 0)) -> Image.Image:
    return Image.new("RGBA", (max(1, int(w)), max(1, int(h))), color)


def down(img: Image.Image, w: int, h: int) -> Image.Image:
    return img.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)


def ramp(t: np.ndarray, stops: list[tuple[float, str]]) -> np.ndarray:
    xs = np.array([s[0] for s in stops])
    cs = np.array([rgb(s[1]) for s in stops], dtype=np.float32)
    out = np.empty(t.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, xs, cs[:, c])
    return out


GOLD_RAMP = [(0.0, "#140B05"), (0.18, "#3A240E"), (0.38, "#7A5424"), (0.56, "#B08440"),
             (0.72, "#D8B366"), (0.86, "#F0D493"), (1.0, "#FFF6DC")]
BRONZE_RAMP = [(0.0, "#0E0805"), (0.2, "#2C1A0C"), (0.42, "#5A3A1C"), (0.62, "#8A6232"),
               (0.8, "#B48C55"), (1.0, "#E6CFA0")]
STEEL_RAMP = [(0.0, "#0B0C0E"), (0.3, "#34383D"), (0.55, "#6F757C"), (0.78, "#B3B9BF"), (1.0, "#F2F5F7")]


def noise(h: int, w: int, scale: float = 6.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((h, w)).astype(np.float32)
    n = ndimage.gaussian_filter(n, scale)
    n /= (np.abs(n).max() + 1e-6)
    return n


def shade_metal(alpha: np.ndarray, bevel: float = 3.0, light=(-0.55, -0.85, 0.75), stops=GOLD_RAMP,
                spec: float = 0.55, shininess: float = 22.0, rough: float = 0.06, seed: int = 0,
                detail: np.ndarray | None = None, base: float = 0.12, gain: float = 0.78,
                profile: str = "round") -> np.ndarray:
    """Shade a coverage mask (float 0..1, supersampled) as bevelled metal. Returns HxWx4 float."""
    inside = alpha > 0.5
    d = ndimage.distance_transform_edt(inside).astype(np.float32)
    hgt = np.clip(d / max(bevel, 1e-3), 0.0, 1.0)
    if profile == "round":
        hgt = np.sin(hgt * np.pi / 2)
    elif profile == "ridge":
        hgt = np.sin(hgt * np.pi / 2) ** 0.7
    hgt = ndimage.gaussian_filter(hgt, 0.8)
    if detail is not None:
        hgt = hgt + detail
    gy, gx = np.gradient(hgt)
    k = bevel * 0.85
    n = np.dstack([-gx * k, -gy * k, np.ones_like(hgt)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    L = np.array(light, dtype=np.float32)
    L /= np.linalg.norm(L)
    diff = np.clip((n * L).sum(2), 0, 1)
    H = L + np.array([0, 0, 1.0], dtype=np.float32)
    H /= np.linalg.norm(H)
    sp = np.clip((n * H).sum(2), 0, 1) ** shininess
    t = base + gain * diff + spec * sp
    if rough > 0:
        t = t + rough * noise(*alpha.shape, scale=1.2 * SS, seed=seed)
    col = ramp(np.clip(t, 0, 1), stops)
    out = np.dstack([col, alpha.astype(np.float32) * 255.0])
    return out


def to_img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def mask_arr(m: Image.Image) -> np.ndarray:
    return np.asarray(m, dtype=np.float32) / 255.0


def metal_from_mask(m: Image.Image, w: int, h: int, bevel: float = 2.2, stops=GOLD_RAMP, **kw) -> Image.Image:
    """m: supersampled L mask (w*SS, h*SS). bevel in final px."""
    arr = shade_metal(mask_arr(m), bevel=bevel * SS, stops=stops, **kw)
    return down(to_img(arr), w, h)


def shadow_of(img: Image.Image, blur: float = 8, offset=(0, 4), opacity: float = 0.6, spread: int = 0,
              color="#000000") -> Image.Image:
    a = img.split()[3]
    if spread:
        a = a.filter(ImageFilter.MaxFilter(spread * 2 + 1))
    pad = int(blur * 3 + abs(offset[0]) + abs(offset[1]) + spread + 2)
    canvas = Image.new("L", (img.width + pad * 2, img.height + pad * 2), 0)
    canvas.paste(a, (pad + offset[0], pad + offset[1]))
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    canvas = canvas.point(lambda v: int(v * opacity))
    sh = Image.new("RGBA", canvas.size, rgba(color, 1.0))
    sh.putalpha(canvas)
    return sh, pad


def paste_shadowed(dst: Image.Image, src: Image.Image, xy, blur=8, offset=(0, 4), opacity=0.6, spread=0):
    sh, pad = shadow_of(src, blur, offset, opacity, spread)
    dst.alpha_composite(sh, (int(xy[0]) - pad, int(xy[1]) - pad))
    dst.alpha_composite(src, (int(xy[0]), int(xy[1])))


def glow(dst: Image.Image, src: Image.Image, xy, color: str, blur: float = 10, opacity: float = 0.7, spread: int = 2):
    a = src.split()[3]
    if spread:
        a = a.filter(ImageFilter.MaxFilter(spread * 2 + 1))
    pad = int(blur * 3 + spread + 2)
    canvas = Image.new("L", (src.width + pad * 2, src.height + pad * 2), 0)
    canvas.paste(a, (pad, pad))
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(min(255, v * opacity)))
    g = Image.new("RGBA", canvas.size, rgba(color))
    g.putalpha(canvas)
    dst.alpha_composite(g, (int(xy[0]) - pad, int(xy[1]) - pad))


def radial_glow(w: int, h: int, color: str, opacity: float = 0.6, falloff: float = 2.0) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    r = np.sqrt(((xx - cx) / (w / 2)) ** 2 + ((yy - cy) / (h / 2)) ** 2)
    a = np.clip(1 - r, 0, 1) ** falloff * opacity
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = rgb(color)
    out[..., 3] = a * 255
    return to_img(out)


# ───────────────────────────── shapes (supersampled masks) ─────────────────────────────
def rrect_mask(w, h, r, inset=0.0) -> Image.Image:
    m = Image.new("L", (int(w * SS), int(h * SS)), 0)
    d = ImageDraw.Draw(m)
    i = inset * SS
    d.rounded_rectangle([i, i, w * SS - 1 - i, h * SS - 1 - i], radius=max(0, r * SS - i), fill=255)
    return m


def ring_mask(w, h, r, thick, inset=0.0) -> Image.Image:
    outer = rrect_mask(w, h, r, inset)
    inner = rrect_mask(w, h, r, inset + thick)
    return ImageChops.subtract(outer, inner)


def chamfer_poly(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
            (x0, y0 + c)]


def chamfer_mask(w, h, c, inset=0.0) -> Image.Image:
    m = Image.new("L", (int(w * SS), int(h * SS)), 0)
    i = inset * SS
    ImageDraw.Draw(m).polygon(chamfer_poly(i, i, w * SS - 1 - i, h * SS - 1 - i, max(0.0, c * SS - i * 0.41)), fill=255)
    return m


def chamfer_ring(w, h, c, thick, inset=0.0) -> Image.Image:
    return ImageChops.subtract(chamfer_mask(w, h, c, inset), chamfer_mask(w, h, c, inset + thick))


def bezier(p0, p1, p2, p3, n=64):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


def taper_stroke(draw: ImageDraw.ImageDraw, pts, r0: float, r1: float, fill=255, ease=1.0):
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        t = (i / max(1, n - 1)) ** ease
        r = r0 + (r1 - r0) * t
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def spiral(cx, cy, r0, r1, turns, start_angle, n=120, direction=1):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = start_angle + direction * t * turns * 2 * math.pi
        r = r0 + (r1 - r0) * t
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ───────────────────────────── lacquer ─────────────────────────────
def lacquer(w: int, h: int, top: str = "#231A14", bot: str = "#0F0A08", alpha: float = 0.93, seed: int = 3,
            edge_dark: float = 0.45, sheen: float = 0.06, tint: str | None = None, tint_amt: float = 0.0) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ty = yy / max(1, h - 1)
    ct, cb = np.array(rgb(top), np.float32), np.array(rgb(bot), np.float32)
    col = ct[None, None, :] * (1 - ty[..., None]) + cb[None, None, :] * ty[..., None]
    if tint:
        col = col * (1 - tint_amt) + np.array(rgb(tint), np.float32) * tint_amt
    # edge darkening (vignette inside the panel)
    ex = np.minimum(xx, w - 1 - xx) / max(1.0, min(w, h) * 0.35)
    ey = np.minimum(yy, h - 1 - yy) / max(1.0, min(w, h) * 0.35)
    e = np.clip(np.minimum(ex, ey), 0, 1)
    col *= (1 - edge_dark) + edge_dark * (e ** 0.6)[..., None]
    # brushed lacquer: horizontal streaks + fine grain
    rng = np.random.default_rng(seed)
    streak = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), (0.6, 18))
    streak /= (np.abs(streak).max() + 1e-6)
    grain = rng.standard_normal((h, w)).astype(np.float32) * 0.5
    col += (streak * 5.5 + grain * 2.0)[..., None]
    # warm top sheen (lamp light on lacquer)
    sh = np.clip(1 - ty / 0.22, 0, 1) ** 2 * sheen * 255
    col += sh[..., None] * np.array([1.0, 0.78, 0.55])[None, None, :]
    out = np.dstack([col, np.full((h, w), alpha * 255, np.float32)])
    return to_img(out)


def clip_to(img: Image.Image, mask: Image.Image) -> Image.Image:
    out = img.copy()
    a = ImageChops.multiply(out.split()[3], mask)
    out.putalpha(a)
    return out


# ───────────────────────────── ornaments ─────────────────────────────
def horn_corner_mask(s: int) -> Image.Image:
    """Top-left 'anvil-horn' corner flourish in an s x s box (supersampled mask).
    Original GODFORGE ornament: an L-bracket whose arms taper into a curled horn, a flame tongue
    rising from the knee, and a socket for a lozenge rivet."""
    S = s * SS
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    u = S / 100.0
    # L bracket arms (tapered)
    taper_stroke(d, [(6 * u + i * 0.9 * u, 6 * u) for i in range(0, 100)], 3.2 * u, 0.6 * u)
    taper_stroke(d, [(6 * u, 6 * u + i * 0.9 * u) for i in range(0, 100)], 3.2 * u, 0.6 * u)
    # knee block
    d.polygon([(0, 0), (22 * u, 0), (22 * u, 5 * u), (5 * u, 22 * u), (0, 22 * u)], fill=255)
    # horn curl on the top arm
    pts = bezier((20 * u, 12 * u), (34 * u, 11 * u), (44 * u, 16 * u), (46 * u, 24 * u), 40)
    taper_stroke(d, pts, 2.4 * u, 1.3 * u)
    pts = spiral(40.5 * u, 24.5 * u, 5.8 * u, 1.2 * u, 0.85, 0.0, 50, direction=1)
    taper_stroke(d, pts, 1.3 * u, 0.7 * u)
    # horn curl on the left arm (mirror)
    pts = bezier((12 * u, 20 * u), (11 * u, 34 * u), (16 * u, 44 * u), (24 * u, 46 * u), 40)
    taper_stroke(d, pts, 2.4 * u, 1.3 * u)
    pts = spiral(24.5 * u, 40.5 * u, 5.8 * u, 1.2 * u, 0.85, math.pi / 2, 50, direction=-1)
    taper_stroke(d, pts, 1.3 * u, 0.7 * u)
    # flame tongue from the knee along the diagonal
    pts = bezier((14 * u, 14 * u), (24 * u, 20 * u), (22 * u, 28 * u), (30 * u, 30 * u), 40)
    taper_stroke(d, pts, 2.6 * u, 0.4 * u, ease=0.8)
    pts = bezier((14 * u, 14 * u), (20 * u, 24 * u), (28 * u, 22 * u), (30 * u, 30 * u), 40)
    taper_stroke(d, pts, 2.6 * u, 0.4 * u, ease=0.8)
    # rivet socket ring
    d.ellipse([7.5 * u, 7.5 * u, 17.5 * u, 17.5 * u], fill=0)
    d.ellipse([9.0 * u, 9.0 * u, 16.0 * u, 16.0 * u], fill=255)
    return m


def gem(size: int, color: str, shape: str = "lozenge", glow_amt: float = 0.0, dim: float = 1.0) -> Image.Image:
    """Faceted gem (lozenge, round cabochon or kite) with a gold bezel. size = final px."""
    S = size * SS
    base = rgb(color)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2

    def shade(k):
        return tuple(int(max(0, min(255, v * k * dim))) for v in base) + (255,)

    if shape == "lozenge":
        o = [(c, 0.04 * S), (0.96 * S, c), (c, 0.96 * S), (0.04 * S, c)]
        bez = Image.new("L", (S, S), 0)
        ImageDraw.Draw(bez).polygon(o, fill=255)
        inner = [(c, 0.2 * S), (0.8 * S, c), (c, 0.8 * S), (0.2 * S, c)]
        m_in = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m_in).polygon(inner, fill=255)
        ring = ImageChops.subtract(bez, m_in)
        metal = to_img(shade_metal(mask_arr(ring), bevel=0.06 * S, stops=GOLD_RAMP, rough=0.03))
        img.alpha_composite(metal)
        # facets
        t = [(c, 0.2 * S), (0.8 * S, c), (c, 0.8 * S), (0.2 * S, c)]
        tab = [(c, 0.36 * S), (0.64 * S, c), (c, 0.64 * S), (0.36 * S, c)]
        d.polygon([t[3], t[0], tab[0], tab[3]], fill=shade(1.25))
        d.polygon([t[0], t[1], tab[1], tab[0]], fill=shade(0.95))
        d.polygon([t[1], t[2], tab[2], tab[1]], fill=shade(0.55))
        d.polygon([t[2], t[3], tab[3], tab[2]], fill=shade(0.75))
        d.polygon(tab, fill=shade(1.05))
        gx, gy = c - 0.1 * S, c - 0.14 * S
        d.ellipse([gx - 0.045 * S, gy - 0.045 * S, gx + 0.045 * S, gy + 0.045 * S], fill=(255, 255, 245, int(230 * dim)))
    elif shape == "round":
        bez = Image.new("L", (S, S), 0)
        ImageDraw.Draw(bez).ellipse([0.03 * S, 0.03 * S, 0.97 * S, 0.97 * S], fill=255)
        m_in = Image.new("L", (S, S), 0)
        ImageDraw.Draw(m_in).ellipse([0.17 * S, 0.17 * S, 0.83 * S, 0.83 * S], fill=255)
        ring = ImageChops.subtract(bez, m_in)
        img.alpha_composite(to_img(shade_metal(mask_arr(ring), bevel=0.06 * S, rough=0.03)))
        # cabochon: radial shading
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
        r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / (0.33 * S)
        lit = np.sqrt(np.clip(1 - r ** 2, 0, 1))
        hl = np.clip(1 - np.sqrt((xx - c + 0.1 * S) ** 2 + (yy - c + 0.12 * S) ** 2) / (0.12 * S), 0, 1)
        k = (0.45 + 0.75 * lit) * dim
        colr = np.dstack([np.array(base, np.float32)[None, None, i] * k for i in range(3)])
        colr += (hl ** 1.5 * 200)[..., None]
        a = (r <= 1.0).astype(np.float32) * 255
        a = ndimage.gaussian_filter(a, 0.8)
        cab = to_img(np.dstack([colr, a]))
        img.alpha_composite(cab)
    out = down(img, size, size)
    if glow_amt > 0:
        g = blank(size * 3, size * 3)
        glow(g, out, (size, size), color, blur=size * 0.35, opacity=glow_amt, spread=1)
        g.alpha_composite(out, (size, size))
        return g
    return out


def divider(w: int, h: int = 14, gem_color: str | None = None, weight: float = 1.0) -> Image.Image:
    """Filigree divider: a hairline tapering to points, with a central lozenge and curls."""
    S = SS
    m = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(m)
    cy = h * S / 2
    cx = w * S / 2
    # tapered line both sides
    taper_stroke(d, [(cx - i, cy) for i in range(0, int(cx) - 2 * S, 2)], 1.3 * S * weight, 0.25 * S)
    taper_stroke(d, [(cx + i, cy) for i in range(0, int(cx) - 2 * S, 2)], 1.3 * S * weight, 0.25 * S)
    # curls near the centre
    for sgn in (-1, 1):
        pts = bezier((cx + sgn * 10 * S, cy), (cx + sgn * 16 * S, cy - 5 * S), (cx + sgn * 24 * S, cy - 5 * S),
                     (cx + sgn * 27 * S, cy - 1 * S), 30)
        taper_stroke(d, pts, 1.0 * S, 0.5 * S)
        pts = spiral(cx + sgn * 25.5 * S, cy + 0.6 * S, 2.2 * S, 0.4 * S, 0.8, -math.pi / 2, 30, direction=sgn)
        taper_stroke(d, pts, 0.6 * S, 0.35 * S)
    # centre lozenge setting
    r = h * S * 0.48
    d.polygon([(cx, cy - r), (cx + r * 0.9, cy), (cx, cy + r), (cx - r * 0.9, cy)], fill=255)
    out = metal_from_mask(m, w, h, bevel=1.1, rough=0.02)
    if gem_color:
        g = gem(int(h * 0.8), gem_color)
        out.alpha_composite(g, (w // 2 - g.width // 2, h // 2 - g.height // 2))
    return out


def sunburst(w: int, h: int, rays: int = 15, color_in="#FFE6A8", color_out="#B08440", opacity=0.9) -> Image.Image:
    """Half sunburst of tapering rays rising from the bottom centre (title crests)."""
    S = SS
    m = Image.new("L", (w * S, h * S), 0)
    d = ImageDraw.Draw(m)
    cx, cy = w * S / 2, h * S * 0.98
    R = min(w * S / 2, h * S) * 0.98
    for i in range(rays):
        a = math.pi + (i + 0.5) / rays * math.pi
        L = R * (1.0 if i % 2 == 0 else 0.72)
        wdt = 0.07 if i % 2 == 0 else 0.05
        p1 = (cx + math.cos(a - wdt) * R * 0.18, cy + math.sin(a - wdt) * R * 0.18)
        p2 = (cx + math.cos(a) * L, cy + math.sin(a) * L)
        p3 = (cx + math.cos(a + wdt) * R * 0.18, cy + math.sin(a + wdt) * R * 0.18)
        d.polygon([p1, p2, p3], fill=255)
    return metal_from_mask(m, w, h, bevel=1.0, rough=0.02)


# ───────────────────────────── panels ─────────────────────────────
def gilded_panel(w: int, h: int, r: int = 10, frame: float = 3.0, alpha: float = 0.93, corners: int = 34,
                 keyline: bool = True, tint: str | None = None, tint_amt: float = 0.0, crest: bool = False,
                 top="#241A14", bot="#0E0A08", chamfer: bool = False, corner_gems: str | None = None,
                 frame_stops=GOLD_RAMP, seed: int = 1) -> Image.Image:
    img = blank(w, h)
    # body
    body_mask = chamfer_mask(w, h, r) if chamfer else rrect_mask(w, h, r)
    body = lacquer(w, h, top=top, bot=bot, alpha=alpha, tint=tint, tint_amt=tint_amt, seed=seed)
    img.alpha_composite(clip_to(body, down(body_mask.convert("L"), w, h)))
    # outer gilded frame
    ring = chamfer_ring(w, h, r, frame) if chamfer else ring_mask(w, h, r, frame)
    img.alpha_composite(metal_from_mask(ring, w, h, bevel=frame * 0.55, stops=frame_stops, seed=seed))
    if keyline:
        k = chamfer_ring(w, h, r, 1.0, inset=frame + 3.5) if chamfer else ring_mask(w, h, max(0, r - 3), 1.0, inset=frame + 3.5)
        kl = metal_from_mask(k, w, h, bevel=0.5, stops=BRONZE_RAMP, rough=0.0)
        kl.putalpha(kl.split()[3].point(lambda v: int(v * 0.85)))
        img.alpha_composite(kl)
    if corners:
        cm = horn_corner_mask(corners)
        cimg = metal_from_mask(cm, corners, corners, bevel=1.4, seed=seed + 7)
        off = -2
        img.alpha_composite(cimg, (off, off))
        img.alpha_composite(cimg.transpose(Image.FLIP_LEFT_RIGHT), (w - corners - off, off))
        img.alpha_composite(cimg.transpose(Image.FLIP_TOP_BOTTOM), (off, h - corners - off))
        img.alpha_composite(cimg.transpose(Image.ROTATE_180), (w - corners - off, h - corners - off))
        if corner_gems:
            gs = max(7, int(corners * 0.26))
            g = gem(gs, corner_gems, "lozenge")
            p = int(corners * 0.125 + off) + 0
            for (x, y) in [(p, p), (w - p - gs, p), (p, h - p - gs), (w - p - gs, h - p - gs)]:
                img.alpha_composite(g, (x, y))
    return img


def socket(size: int, shape: str = "diamond", frame: float = 3.0, fill_top="#2A1F18", fill_bot="#0C0806",
           stops=GOLD_RAMP) -> Image.Image:
    """Empty ability/item socket (diamond, round or square-chamfer)."""
    img = blank(size, size)
    S = size * SS
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    if shape == "diamond":
        c = S / 2
        d.polygon([(c, 0), (S - 1, c), (c, S - 1), (0, c)], fill=255)
        inner = Image.new("L", (S, S), 0)
        k = frame * SS * 1.42
        ImageDraw.Draw(inner).polygon([(c, k), (S - 1 - k, c), (c, S - 1 - k), (k, c)], fill=255)
    elif shape == "round":
        d.ellipse([0, 0, S - 1, S - 1], fill=255)
        inner = Image.new("L", (S, S), 0)
        k = frame * SS
        ImageDraw.Draw(inner).ellipse([k, k, S - 1 - k, S - 1 - k], fill=255)
    else:
        m = chamfer_mask(size, size, size * 0.18)
        inner = chamfer_mask(size, size, size * 0.18, inset=frame)
    body = lacquer(size, size, top=fill_top, bot=fill_bot, alpha=0.96, edge_dark=0.6, sheen=0.1)
    img.alpha_composite(clip_to(body, down(inner, size, size)))
    ring = ImageChops.subtract(m, inner)
    img.alpha_composite(metal_from_mask(ring, size, size, bevel=frame * 0.6, stops=stops))
    return img


# ───────────────────────────── text ─────────────────────────────
def text_size(s: str, font, tracking: float = 0.0) -> tuple[int, int]:
    if not s:
        return 0, 0
    if tracking == 0:
        b = font.getbbox(s)
        return b[2] - b[0], b[3] - b[1]
    w = font.getlength(s) + tracking * (len(s) - 1)
    b = font.getbbox(s)
    return int(math.ceil(w)), b[3] - b[1]


def text_mask(s: str, font, tracking: float = 0.0, pad: int = 4) -> tuple[Image.Image, int]:
    asc, desc = font.getmetrics()
    w = int(math.ceil(font.getlength(s) + tracking * max(0, len(s) - 1))) + pad * 2
    h = asc + desc + pad * 2
    m = Image.new("L", (max(1, w), h), 0)
    d = ImageDraw.Draw(m)
    x = pad
    if tracking == 0:
        d.text((x, pad), s, font=font, fill=255)
    else:
        for i, ch in enumerate(s):
            # kerning-aware: advance = length of the prefix (includes pair kerning) + tracking
            x0 = font.getlength(s[:i + 1]) - font.getlength(ch)
            d.text((pad + x0 + tracking * i, pad), ch, font=font, fill=255)
    return m, pad


def draw_text(dst: Image.Image, xy, s: str, font, fill: str = TOK["parch"], tracking: float = 0.0,
              anchor: str = "l", shadow: float = 0.75, shadow_off=(0, 2), shadow_blur: float = 1.6,
              outline: int = 0, outline_color: str = TOK["ink"], gradient: tuple[str, str] | None = None,
              glow_color: str | None = None, glow_amt: float = 0.0, glow_blur: float = 8, alpha: float = 1.0,
              valign: str = "baseline") -> tuple[int, int, int, int]:
    """Draw text with tracking, optional vertical gradient fill, ink outline, drop shadow and glow.
    xy is the anchor point: anchor l/m/r horizontally; valign 'baseline' | 'top' | 'middle'."""
    if not s:
        return (0, 0, 0, 0)
    m, pad = text_mask(s, font, tracking)
    asc, desc = font.getmetrics()
    w, h = m.size
    x, y = xy
    tw = w - pad * 2
    if anchor == "m":
        x -= tw / 2
    elif anchor == "r":
        x -= tw
    if valign == "baseline":
        y -= asc
    elif valign == "middle":
        cap = font.getbbox("H")
        y -= (cap[1] + cap[3]) / 2
    x0, y0 = int(round(x - pad)), int(round(y - pad))
    if glow_color and glow_amt > 0:
        gl = Image.new("RGBA", m.size, rgba(glow_color))
        gl.putalpha(m)
        glow(dst, gl, (x0, y0), glow_color, blur=glow_blur, opacity=glow_amt, spread=1)
    if shadow > 0:
        sm = m
        if outline:
            sm = m.filter(ImageFilter.MaxFilter(outline * 2 + 1))
        sh = Image.new("RGBA", m.size, rgba(TOK["ink"]))
        sh.putalpha(sm.filter(ImageFilter.GaussianBlur(shadow_blur)).point(lambda v: int(v * shadow * alpha)))
        dst.alpha_composite(sh, (x0 + shadow_off[0], y0 + shadow_off[1]))
    if outline:
        om = m.filter(ImageFilter.MaxFilter(outline * 2 + 1))
        o = Image.new("RGBA", m.size, rgba(outline_color))
        o.putalpha(om.point(lambda v: int(v * alpha)))
        dst.alpha_composite(o, (x0, y0))
    if gradient:
        top, bot = gradient
        g = np.zeros((h, w, 4), np.float32)
        cap = font.getbbox("H")
        t = np.clip((np.arange(h, dtype=np.float32) - pad - cap[1]) / max(1, cap[3] - cap[1]), 0, 1)
        ct, cb = np.array(rgb(top), np.float32), np.array(rgb(bot), np.float32)
        g[..., :3] = (ct[None, :] * (1 - t[:, None]) + cb[None, :] * t[:, None])[:, None, :]
        g[..., 3] = np.asarray(m, np.float32) * alpha
        dst.alpha_composite(to_img(g), (x0, y0))
    else:
        f = Image.new("RGBA", m.size, rgba(fill))
        f.putalpha(m.point(lambda v: int(v * alpha)))
        dst.alpha_composite(f, (x0, y0))
    return (x0 + pad, y0 + pad, x0 + pad + tw, y0 + pad + asc + desc)


GOLD_TEXT = ("#FFF3CF", "#C9953F")
IVORY_TEXT = ("#FFF8E8", "#E6D2AC")


def keycap(label: str, size: int = 22, font_px: int = 13, wide: bool = False, style: str = "kb") -> Image.Image:
    """Keybind chip: a small lacquered keycap with a gilt edge (KB/M) or a round pad button."""
    f = sans(font_px, "Bold")
    tw, _ = text_size(label, f)
    w = max(size, tw + 10) if (wide or len(label) > 1) else size
    h = size
    img = blank(w + 2, h + 3)
    if style == "pad":
        m = Image.new("L", ((w) * SS, h * SS), 0)
        ImageDraw.Draw(m).ellipse([0, 0, w * SS - 1, h * SS - 1], fill=255)
    else:
        m = rrect_mask(w, h, 4)
    body = lacquer(w, h, top="#3A2C21", bot="#1A120D", alpha=0.97, edge_dark=0.3, sheen=0.14)
    img.alpha_composite(clip_to(body, down(m, w, h)), (1, 0))
    rm = ImageChops.subtract(m, rrect_mask(w, h, 3, inset=1.2) if style != "pad" else _ell_in(w, h, 1.2))
    img.alpha_composite(metal_from_mask(rm, w, h, bevel=0.8, rough=0.0), (1, 0))
    draw_text(img, (1 + w / 2, h / 2 + 0.5), label, f, fill=TOK["parch"], anchor="m", valign="middle", shadow=0.6,
              shadow_off=(0, 1), shadow_blur=0.6)
    return img


def _ell_in(w, h, inset):
    m = Image.new("L", (w * SS, h * SS), 0)
    i = inset * SS
    ImageDraw.Draw(m).ellipse([i, i, w * SS - 1 - i, h * SS - 1 - i], fill=255)
    return m


# ───────────────────────────── bars ─────────────────────────────
def blade_bar(w: int, h: int, frac: float, ghost: float | None, lo: str, mid: str, hi: str, ghost_col: str,
              frame: float = 2.0, point: int | None = None, segments: int = 0, notches: list[float] | None = None,
              track="#0B0706", label: str | None = None, label_font=None, sheen: bool = True,
              left_point: bool = True) -> Image.Image:
    """A gilded 'blade' bar: pointed ends, recessed dark track, glassy gradient fill with a bright
    meniscus, trailing ghost segment, optional segment ticks and phase notches."""
    point = point if point is not None else max(4, h // 2)
    img = blank(w, h)
    S = SS

    def poly(inset):
        i = inset * S
        W, H = w * S - 1, h * S - 1
        pl = point * S if left_point else i * 0.0 + 2 * S
        return [(pl, i), (W - point * S, i), (W - i * 1.2, H / 2), (W - point * S, H - i), (pl, H - i),
                (i * 1.2 if left_point else i, H / 2)] if left_point else \
            [(i, i), (W - point * S, i), (W - i * 1.2, H / 2), (W - point * S, H - i), (i, H - i)]

    outer = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(outer).polygon(poly(0), fill=255)
    inner = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(inner).polygon(poly(frame), fill=255)
    inner_s = down(inner, w, h)
    # track
    tr = lacquer(w, h, top="#070504", bot="#140E0B", alpha=0.95, edge_dark=0.2, sheen=0.0)
    img.alpha_composite(clip_to(tr, inner_s))
    # fill
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ty = yy / max(1, h - 1)
    x_in0, x_in1 = frame + (point if left_point else 0) * 0.5, w - frame - point * 0.5
    span = x_in1 - x_in0

    def band(f0, f1, cols, alpha=1.0):
        a0, a1 = x_in0 + span * f0, x_in0 + span * f1
        a = np.clip(xx - a0 + 0.5, 0, 1) * np.clip(a1 - xx + 0.5, 0, 1)
        c = ramp(ty, [(0.0, cols[2]), (0.38, cols[1]), (1.0, cols[0])])
        return np.dstack([c, a * 255 * alpha])

    if ghost is not None and ghost > frac:
        g = band(frac, ghost, (ghost_col, ghost_col, mix(ghost_col, "#FFFFFF", 0.3)), 0.9)
        img.alpha_composite(clip_to(to_img(g), inner_s))
    if frac > 0:
        f = band(0, frac, (lo, mid, hi))
        fi = to_img(f)
        if sheen:
            # glassy highlight band
            hl = np.clip(1 - np.abs(ty - 0.22) / 0.16, 0, 1) * 70
            fa = np.asarray(fi, np.float32)
            fa[..., :3] += hl[..., None]
            fi = to_img(fa)
        img.alpha_composite(clip_to(fi, inner_s))
        # meniscus
        mx = x_in0 + span * frac
        men = np.clip(1 - np.abs(xx - mx + 1) / 1.6, 0, 1) * 200
        me = np.dstack([np.full_like(xx, 255), np.full_like(xx, 240), np.full_like(xx, 215), men])
        img.alpha_composite(clip_to(to_img(me), inner_s))
    if segments:
        d = ImageDraw.Draw(img)
        for i in range(1, segments):
            x = x_in0 + span * i / segments
            d.line([(x, frame + 1), (x, h - frame - 2)], fill=(8, 5, 4, 150), width=1)
    ring = ImageChops.subtract(outer, inner)
    img.alpha_composite(metal_from_mask(ring, w, h, bevel=frame * 0.6, rough=0.02))
    if notches:
        for n in notches:
            x = int(x_in0 + span * n)
            g = gem(max(7, h - 2), "#E8D2A0", "lozenge", dim=0.75)
            img.alpha_composite(g, (x - g.width // 2, (h - g.height) // 2))
    if label and label_font:
        draw_text(img, (w - point - frame - 4, h / 2 + 0.5), label, label_font, fill=TOK["parch"], anchor="r",
                  valign="middle", shadow=0.9, shadow_off=(0, 1), shadow_blur=1.0, outline=1)
    return img


def conic_sweep(size: int, frac_left: float, color=(8, 5, 4), alpha: float = 0.78, edge: str | None = TOK["ichor"],
                shape_mask: Image.Image | None = None) -> Image.Image:
    """Cooldown sweep overlay: dark wedge covering the remaining fraction clockwise from 12 o'clock."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    ang = (np.arctan2(xx - c, -(yy - c)) / (2 * np.pi)) % 1.0  # 0 at top, clockwise
    done = 1.0 - frac_left
    a = (ang >= done).astype(np.float32) * alpha * 255
    a = ndimage.gaussian_filter(a, 0.6)
    out = np.dstack([np.full_like(xx, color[0]), np.full_like(xx, color[1]), np.full_like(xx, color[2]), a])
    img = to_img(out)
    if edge and 0 < frac_left < 1:
        d = ImageDraw.Draw(img)
        th = done * 2 * math.pi
        d.line([(c, c), (c + math.sin(th) * size, c - math.cos(th) * size)], fill=rgba(edge, 0.9), width=2)
    if shape_mask is not None:
        img = clip_to(img, shape_mask)
    return img
