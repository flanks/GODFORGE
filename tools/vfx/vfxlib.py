"""GODFORGE VFX asset toolkit: packed flipbook cells, ramps, noise, the reference shader, sheets.

Every combat texture in assets/vfx/ is a *packed grey* texture, never a coloured one. One painted
flipbook serves every element; the ramp row picks the colours (docs/art/VFX_STYLE.md sections 3.3
and 21.5). The channels of every atlas cell:

  R  shape mask as a signed distance field: 0.5 is the painted edge, +-SDF_SPREAD cell px of
     distance maps to 1.0 / 0.0. The shader turns it into crisp coverage at any scale with
     `smoothstep(0.5 - w, 0.5 + w, r)`, w = fwidth(r) * 0.7.
  G  value: where the pixel sits on the element ramp (ink 0.06, deep 0.29, body 0.50, light 0.70,
     hot 0.93). It is continuous; the ramp texture posterizes it, so the band edges stay crisp when
     the sprite is magnified.
  B  erosion order: the pixel survives while B > t (t = normalized age x erode strength). Tails,
     edges and secondary layers hold low values, heads and cores high ones.

G and B are edge-padded (nearest covered texel) inside the SDF band and 0 beyond it, so bilinear
filtering never bleeds garbage and the PNGs stay small. The textures are data: load them as linear
(not sRGB) and never premultiply them. The shader outputs premultiplied colour (see `shade`).

Authoring happens at SS x the cell resolution with PIL polygons and numpy fields, then `Cell.pack`
builds the SDF with scipy's exact Euclidean distance transform and area-averages G and B.

Nothing here is traced or sampled from any reference image: every shape is a primitive in this file.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "assets", "vfx")
SHEETS = os.path.join(ROOT, "docs", "art", "vfx_concepts")
FONTS = os.path.join(ROOT, "assets", "fonts")

SS = 4  # supersampling while painting
SDF_SPREAD = 4.0  # cell px from the edge to R = 0 or 1

V_INK, V_DEEP, V_BODY, V_LIGHT, V_HOT = 0.06, 0.29, 0.50, 0.70, 0.93
BAND_EDGES = (0.18, 0.40, 0.60, 0.81)  # ink | deep | body | light | hot
BAND_GAIN = (1.0, 1.0, 1.25, 1.6, 2.6)  # HDR gain per band (VFX_STYLE 3.2), stored as A = gain / 4
INK_ALPHA = 0.9
ADD_FROM, ADD_TO = 0.80, 0.90  # hot values blend from alpha-over to additive

TAU = 2 * math.pi


# ------------------------------------------------------------------------------------------------
# colour helpers
# ------------------------------------------------------------------------------------------------
def s2l(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def l2s(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hexrgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def wrap(a):
    return (a + np.pi) % TAU - np.pi


# ------------------------------------------------------------------------------------------------
# ramps (VFX_STYLE 3.3). Row order is the contract with vfx.ron / the shader: never reorder.
# ------------------------------------------------------------------------------------------------
RAMPS = [
    ("kinetic", "Kinetic bone-brass", ["#1A120C", "#8A4A16", "#E3A64A", "#F4E3C1", "#FFFBF0"]),
    ("flame", "Flame", ["#240A06", "#A8300A", "#FF7A1A", "#FFC24B", "#FFF3D6"]),
    ("storm", "Storm", ["#06101E", "#1B4E9B", "#3FD8FF", "#BDF6FF", "#FFFFFF"]),
    ("void", "Void", ["#0C0416", "#3B1675", "#A45CFF", "#E2CCFF", "#FFF6FF"]),
    ("plague", "Plague", ["#0D1507", "#3A6414", "#86E03A", "#D9FF8C", "#F6FFE0"]),
    ("radiant", "Radiant", ["#241703", "#B07A12", "#FFE27A", "#FFF3BE", "#FFFFFF"]),
    ("unmade", "Unmade ichor (enemy)", ["#07060A", "#0D3B35", "#2FBFA8", "#8FF2D8", "#B8FFE8"]),
    ("godworks_gold", "Godworks cold gold (enemy)", ["#1E1408", "#5A4A20", "#D4B45A", "#F4E6B0", "#FFF4D0"]),
    ("godworks_ember", "Godworks dead ember (enemy)", ["#2A0E08", "#4A1A0C", "#8A3A1E", "#C8663A", "#E08A50"]),
    ("enemy_shot", "Enemy shot (magenta core)", ["#1A0610", "#7A1040", "#FF5AA8", "#FFC0E0", "#FFFFFF"]),
    ("zone_gold", "Player zone hem (gold)", ["#241703", "#8A6A20", "#FFC940", "#FFE6A0", "#FFF8E0"]),
    ("heal", "Heal / revive", ["#1A1406", "#6A5A20", "#FFE9A8", "#FFF4D0", "#FFFFFF"]),
    ("bleed", "Bleed (crimson drips, never red-white)", ["#12040A", "#4A0A16", "#8A1020", "#B8404E", "#E07A84"]),
    ("time", "Time (Epoch, pale steel)", ["#0C1016", "#3C5064", "#9FB6C8", "#DCE8F0", "#FFFFFF"]),
    ("dust", "Dust / smoke / ash (neutral)", ["#141012", "#3A3034", "#6E6064", "#B3A69C", "#E8DED2"]),
    ("mono", "Mono ink-white (impact frames, execute)", ["#0C080C", "#4A4448", "#B8B2B4", "#F2EEEC", "#FFFFFF"]),
]
RAMP_INDEX = {k: i for i, (k, _, _) in enumerate(RAMPS)}


def ramp_table(key, posterize=True, n=256):
    """(n, 4) float32: sRGB colour (0..1) and A = HDR gain / 4. Posterized rows keep a 1-texel soft edge."""
    cols = np.array([hexrgb(c) for c in dict((k, c) for k, _, c in RAMPS)[key]], np.float32)
    x = (np.arange(n) + 0.5) / n
    centers = np.array([V_INK, V_DEEP, V_BODY, V_LIGHT, V_HOT], np.float32)
    out = np.zeros((n, 4), np.float32)
    gains = np.array(BAND_GAIN, np.float32)
    if posterize:
        idx = np.searchsorted(np.array(BAND_EDGES), x)
        rgb = cols[idx]
        g = gains[idx]
        # 1-texel soft edge: average with the neighbour at each boundary
        rgb2 = rgb.copy()
        g2 = g.copy()
        for i in range(1, n - 1):
            if idx[i] != idx[i + 1] or idx[i] != idx[i - 1]:
                j = i + 1 if idx[i] != idx[i + 1] else i - 1
                rgb2[i] = rgb[i] * 0.65 + rgb[j] * 0.35
                g2[i] = g[i] * 0.65 + g[j] * 0.35
        out[:, :3] = rgb2
        out[:, 3] = g2 / 4.0
    else:
        lin = s2l(cols)
        for c in range(3):
            out[:, c] = l2s(np.interp(x, centers, lin[:, c]))
        out[:, 3] = np.interp(x, centers, gains) / 4.0
    return out


# ------------------------------------------------------------------------------------------------
# noise
# ------------------------------------------------------------------------------------------------
def equalize(a):
    """Rank-equalize to a uniform 0..1 histogram (dissolves progress linearly with the threshold)."""
    flat = a.ravel()
    order = np.argsort(flat, kind="stable")
    out = np.empty_like(flat, dtype=np.float32)
    out[order] = (np.arange(flat.size, dtype=np.float32) + 0.5) / flat.size
    return out.reshape(a.shape)


def fbm_tile(n, seed, beta=2.2, ax=1.0, ay=1.0, lo_cut=1.0, eq=True):
    """Tiling fractal noise by spectral synthesis (1/f^beta), optionally anisotropic (ax, ay scale the
    frequency axes: ax > ay stretches features along y)."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal((n, n))
    F = np.fft.fft2(w)
    fy = np.fft.fftfreq(n)[:, None] * n
    fx = np.fft.fftfreq(n)[None, :] * n
    f = np.sqrt((fx * ax) ** 2 + (fy * ay) ** 2)
    f[0, 0] = 1.0
    amp = np.where(f < lo_cut, 0.0, f ** (-beta / 2))
    amp[0, 0] = 0.0
    a = np.real(np.fft.ifft2(F * amp)).astype(np.float32)
    if eq:
        return equalize(a)
    a -= a.min()
    return a / max(a.max(), 1e-6)


def worley_tile(n, seed, count, f2=False):
    """Tiling cellular noise: F1 (or F2 - F1 edges) normalized to 0..1."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)) * n
    tiles = [pts + np.array([dx, dy]) * n for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
    tree = cKDTree(np.concatenate(tiles))
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    d, _ = tree.query(np.stack([xx.ravel(), yy.ravel()], 1), k=2)
    v = (d[:, 1] - d[:, 0]) if f2 else d[:, 0]
    v = v.reshape(n, n).astype(np.float32)
    v -= v.min()
    return v / max(v.max(), 1e-6)


class Noise:
    """Tiling fBm sampled at arbitrary coordinates (bilinear, grid-wrap). 1 unit = 1 grid texel."""

    def __init__(self, seed, n=128, beta=2.0, ax=1.0, ay=1.0):
        self.g = fbm_tile(n, seed, beta=beta, ax=ax, ay=ay, eq=True)
        self.n = n

    def __call__(self, u, v):
        return ndi.map_coordinates(self.g, [np.asarray(v, np.float32), np.asarray(u, np.float32)], order=1,
                                   mode="grid-wrap")


# ------------------------------------------------------------------------------------------------
# geometry helpers (cell px, y down)
# ------------------------------------------------------------------------------------------------
def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def norm(v):
    L = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / L, v[1] / L)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out(t, p=2.0):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** p


def ease_in(t, p=2.0):
    t = min(max(t, 0.0), 1.0)
    return t ** p


def tapered_path(pts, widths):
    """Polygon around a polyline with per-point widths."""
    L, R = [], []
    n = len(pts)
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        d = norm((b[0] - a[0], b[1] - a[1]))
        nn = (-d[1], d[0])
        w = widths[i] / 2
        L.append((pts[i][0] + nn[0] * w, pts[i][1] + nn[1] * w))
        R.append((pts[i][0] - nn[0] * w, pts[i][1] - nn[1] * w))
    return L + R[::-1]


def kite(p, d, L, w, back=0.35, skew=0.0):
    """Four-point kite: tip along d at L, tail at -back*L, half-width w (skew shifts the waist)."""
    d = norm(d)
    n = (-d[1], d[0])
    tip = (p[0] + d[0] * L, p[1] + d[1] * L)
    tail = (p[0] - d[0] * L * back, p[1] - d[1] * L * back)
    m = (p[0] + d[0] * L * skew, p[1] + d[1] * L * skew)
    return [tip, (m[0] + n[0] * w, m[1] + n[1] * w), tail, (m[0] - n[0] * w * 0.8, m[1] - n[1] * w * 0.8)]


def streak_poly(p0, p1, w0, w1=0.0, cap=True):
    """A streak from a round head p0 (width w0) tapering to p1 (width w1)."""
    d = norm((p1[0] - p0[0], p1[1] - p0[1]))
    n = (-d[1], d[0])
    pts = [(p0[0] + n[0] * w0 / 2, p0[1] + n[1] * w0 / 2)]
    if cap:
        for a in np.linspace(0.3, math.pi - 0.3, 5):
            v = rot(n, -a)
            pts.append((p0[0] + v[0] * w0 / 2, p0[1] + v[1] * w0 / 2))
    pts.append((p0[0] - n[0] * w0 / 2, p0[1] - n[1] * w0 / 2))
    pts.append((p1[0] - n[0] * w1 / 2, p1[1] - n[1] * w1 / 2))
    pts.append((p1[0] + n[0] * w1 / 2, p1[1] + n[1] * w1 / 2))
    return pts


def bolt_points(p0, p1, rng, jag=0.22, depth=5, keep_ends=True):
    pts = [p0, p1]
    amp = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * jag
    for _ in range(depth):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            d = norm((b[0] - a[0], b[1] - a[1]))
            n = (-d[1], d[0])
            o = rng.uniform(-amp, amp)
            out += [(m[0] + n[0] * o, m[1] + n[1] * o), b]
        pts = out
        amp *= 0.52
    return pts


def arc_pts(c, r, a0, a1, n=24, ky=1.0):
    return [(c[0] + math.cos(a) * r, c[1] + math.sin(a) * r * ky) for a in np.linspace(a0, a1, n)]


def bezier(p0, p1, p2, n=24, p3=None):
    t = np.linspace(0, 1, n)[:, None]
    P0, P1, P2 = np.array(p0), np.array(p1), np.array(p2)
    if p3 is None:
        pts = (1 - t) ** 2 * P0 + 2 * (1 - t) * t * P1 + t ** 2 * P2
    else:
        P3 = np.array(p3)
        pts = (1 - t) ** 3 * P0 + 3 * (1 - t) ** 2 * t * P1 + 3 * (1 - t) * t ** 2 * P2 + t ** 3 * P3
    return [tuple(p) for p in pts]


def tongue_poly(base, H, W, phase=0.0, lean=0.0, curl=0.35, n=22, tip_curl=0.5, fat=0.9):
    """A flame tongue rising from base (screen up): an S-curve spine that tapers to a curled tip."""
    spine, widths = [], []
    for i in range(n):
        t = i / (n - 1)
        sway = W * curl * math.sin(phase + t * 3.4) * t + lean * H * t * t
        sway += W * tip_curl * max(0.0, t - 0.7) ** 2 * 6 * math.cos(phase * 0.7)
        spine.append((base[0] + sway, base[1] - H * t))
        prof = (1 - t) ** 0.55 * (0.62 + 0.38 * math.sin(math.pi / 2 * min(1.0, t / 0.35)) ** fat)
        widths.append(W * prof + 0.25)
    return tapered_path(spine, widths)


# ------------------------------------------------------------------------------------------------
# the cell canvas
# ------------------------------------------------------------------------------------------------
class Cell:
    """One atlas cell painted at SS x resolution. Coordinates are cell px (float), y down.

    paint(mask, value, order): later paints cover earlier ones. `order` (0..1) is the layer's place
    in the erosion sequence: low orders erode first. pack() combines the order with the distance to
    the edge and a ragged noise into B.
    """

    def __init__(self, w, h, seed=0, ss=SS):
        self.w, self.h, self.ss = int(w), int(h), ss
        self.W, self.H = self.w * ss, self.h * ss
        xs = ((np.arange(self.W) + 0.5) / ss).astype(np.float32)
        ys = ((np.arange(self.H) + 0.5) / ss).astype(np.float32)
        self.X, self.Y = np.meshgrid(xs, ys)
        self.cov = np.zeros((self.H, self.W), bool)
        self.val = np.zeros((self.H, self.W), np.float32)
        self.order = np.zeros((self.H, self.W), np.float32)
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.nz = Noise(seed * 7 + 1)
        self.nz_streak = Noise(seed * 7 + 3, ax=1.0, ay=6.0)

    # -- rasterizers ---------------------------------------------------------------------------
    def _img(self):
        return Image.new("L", (self.W, self.H), 0)

    def polys(self, polys):
        img = self._img()
        d = ImageDraw.Draw(img)
        s = self.ss
        for pts in polys:
            if len(pts) >= 3:
                d.polygon([(p[0] * s, p[1] * s) for p in pts], fill=255)
        return np.asarray(img) > 127

    def lines(self, lines):
        """lines = [(pts, width)] with round caps."""
        img = self._img()
        d = ImageDraw.Draw(img)
        s = self.ss
        for pts, w in lines:
            q = [(p[0] * s, p[1] * s) for p in pts]
            wp = max(1, int(round(w * s)))
            if len(q) > 1:
                d.line(q, fill=255, width=wp, joint="curve")
            for e in (q[0], q[-1]):
                r = wp / 2
                d.ellipse((e[0] - r, e[1] - r, e[0] + r, e[1] + r), fill=255)
        return np.asarray(img) > 127

    def dots(self, dots):
        img = self._img()
        d = ImageDraw.Draw(img)
        s = self.ss
        for x, y, r in dots:
            d.ellipse(((x - r) * s, (y - r) * s, (x + r) * s, (y + r) * s), fill=255)
        return np.asarray(img) > 127

    def ellipse(self, c, rx, ry, angle=0.0):
        x = self.X - c[0]
        y = self.Y - c[1]
        ca, sa = math.cos(-angle), math.sin(-angle)
        xl = x * ca - y * sa
        yl = x * sa + y * ca
        return (xl / rx) ** 2 + (yl / ry) ** 2 <= 1.0

    def polar(self, c):
        x = self.X - c[0]
        y = self.Y - c[1]
        return np.hypot(x, y), np.arctan2(y, x)

    # -- shape fields --------------------------------------------------------------------------
    def star(self, c, spikes, r_in, p=1.7, twist=0.0, rough=0.0, rough_freq=6.0, skew=0.0):
        """Spiky star. spikes = [(angle, length, half_width_rad)]. Returns (mask, rel) where rel = r /
        edge(theta): 0 at the centre, 1 on the edge (nested bands come from thresholds on rel).
        skew > 0 makes every spike a pinwheel blade: a straight leading flank, a long curved trailing one."""
        r, th = self.polar(c)
        L = max([s[1] for s in spikes] + [r_in])
        tht = th - twist * np.clip(r / max(L, 1e-3), 0, 1.5)
        edge = np.full_like(r, r_in)
        for a, ln, h in spikes:
            dd = wrap(tht - a)
            hh = np.where(dd > 0, h * (1 + skew), h * (1 - skew * 0.6))
            k = np.clip(1 - np.abs(dd) / hh, 0, 1) ** p
            edge = np.maximum(edge, r_in + (ln - r_in) * k)
        if rough > 0:
            n = self.nz((th + np.pi) / TAU * rough_freq * 8, r * 0.05 + 3.0)
            edge = edge * (1 + rough * (n - 0.5))
        rel = r / np.maximum(edge, 1e-3)
        return rel <= 1.0, rel

    def crescent(self, c, R, a0, a1, width, peak=0.72, erode=0.7, streak=(2.5, 9.0), inner_rag=0.3, ky=1.0,
                 rotation=0.0):
        """Crescent smear field: sweep a0 (tail) -> a1 (head), outer radius R, max width `width`.
        Returns (mask, t along the sweep 0..1, s across 0 outer .. 1 inner)."""
        x = self.X - c[0]
        y = (self.Y - c[1]) / ky
        cr, sr = math.cos(-rotation), math.sin(-rotation)
        xl = x * cr - y * sr
        yl = x * sr + y * cr
        th = np.arctan2(yl, xl)
        r = np.hypot(xl, yl)
        span = a1 - a0
        sg = 1.0 if span >= 0 else -1.0
        d = np.mod((th - a0) * sg, TAU)
        t = d / abs(span)
        tc = np.clip(t, 0, 1)
        a = np.clip(tc / peak, 0, 1)
        up = np.sin(a * np.pi / 2) ** 1.3
        b = np.clip((tc - peak) / (1 - peak), 0, 1)
        cap = np.sqrt(np.clip(1 - b * b, 0, 1))
        w = width * np.where(tc < peak, up, cap)
        s = (R - r) / np.maximum(w, 1e-3)
        n = self.nz_streak(tc * streak[0] * 16, s * streak[1] * 4 + tc * 3)
        thr = erode * (1 - tc) ** 1.6
        rag = 1 - inner_rag * self.nz(tc * 40 + 5, s * 4 + 11)
        inside = (t <= 1) & (s >= 0) & (s <= rag) & (n > thr)
        return inside, tc, s

    def sdf(self, mask):
        """Hi-res signed distance (cell px): + inside, - outside."""
        din = ndi.distance_transform_edt(mask)
        dout = ndi.distance_transform_edt(~mask)
        return (np.where(mask, din - 0.5, -(dout - 0.5)) / self.ss).astype(np.float32)

    def inside_dist(self, mask):
        return (ndi.distance_transform_edt(mask) / self.ss).astype(np.float32)

    def ragged(self, mask, amp=1.5, freq=0.25, streak=False):
        """Roughen a mask's edge by +-amp cell px of noise (brush edges)."""
        sd = self.sdf(mask)
        nz = self.nz_streak if streak else self.nz
        n = nz(self.X * freq * 4, self.Y * freq * 4) - 0.5
        return sd + n * 2 * amp > 0

    # -- painting ------------------------------------------------------------------------------
    def paint(self, mask, value, order=0.5):
        m = np.asarray(mask, bool)
        self.cov |= m
        v = np.broadcast_to(np.asarray(value, np.float32), m.shape)
        o = np.broadcast_to(np.asarray(order, np.float32), m.shape)
        self.val[m] = v[m]
        self.order[m] = o[m]

    def erase(self, mask):
        m = np.asarray(mask, bool)
        self.cov &= ~m

    def clear_border(self, margin=None):
        m = int(round((SDF_SPREAD + 1 if margin is None else margin) * self.ss))
        self.cov[:m, :] = False
        self.cov[-m:, :] = False
        self.cov[:, :m] = False
        self.cov[:, -m:] = False

    # -- packing -------------------------------------------------------------------------------
    def pack(self, w_order=0.5, w_dist=0.3, w_noise=0.2, dist_scale=None, ero=None, border=True):
        """-> uint8 (h, w, 3). ero: optional explicit hi-res B field (0..1) replacing the default mix."""
        if border:
            self.clear_border()
        cov = self.cov
        ss = self.ss
        h, w = self.h, self.w
        if not cov.any():
            return np.zeros((h, w, 3), np.uint8)
        sd = self.sdf(cov)
        sd_lo = sd.reshape(h, ss, w, ss).mean(axis=(1, 3))
        R = np.clip(0.5 + sd_lo / (2 * SDF_SPREAD), 0, 1)
        if ero is None:
            din = np.clip(sd, 0, None)
            scale = dist_scale if dist_scale is not None else max(float(din.max()) * 0.6, 1.0)
            dist = np.clip(din / scale, 0, 1)
            n = self.nz(self.X * 0.9 + 17, self.Y * 0.9 + 5)
            ero = w_order * self.order + w_dist * dist + w_noise * n
            ero = ero / max(w_order + w_dist + w_noise, 1e-6)
        ero = np.clip(ero, 0.02, 1.0)
        c = cov.astype(np.float32)
        csum = c.reshape(h, ss, w, ss).sum(axis=(1, 3))
        G = (self.val * c).reshape(h, ss, w, ss).sum(axis=(1, 3)) / np.maximum(csum, 1e-6)
        B = (ero * c).reshape(h, ss, w, ss).sum(axis=(1, 3)) / np.maximum(csum, 1e-6)
        has = csum > 0
        if has.any() and not has.all():
            _, idx = ndi.distance_transform_edt(~has, return_indices=True)
            G = G[idx[0], idx[1]]
            B = B[idx[0], idx[1]]
        band = R > 0.0
        G = np.where(band, G, 0)
        B = np.where(band, B, 0)
        out = np.stack([R, G, B], -1)
        return np.clip(np.round(out * 255), 0, 255).astype(np.uint8)


def band_value(rel, edges=(0.3, 0.58, 0.86), values=(V_HOT, V_LIGHT, V_BODY, V_DEEP), jitter=None):
    """Nested bands by a 0 (centre) .. 1 (edge) field: rel < e0 -> values[0], ... (jitter perturbs rel)."""
    r = rel if jitter is None else rel + jitter
    out = np.full(r.shape, values[-1], np.float32)
    for e, v in zip(edges[::-1], values[-2::-1]):
        out = np.where(r < e, v, out)
    return out


# ------------------------------------------------------------------------------------------------
# atlases and the manifest
# ------------------------------------------------------------------------------------------------
MANIFEST: list[dict] = []


class Atlas:
    def __init__(self, name, cols, rows, cw, ch, sub="atlas", kind="flipbook_packed", intended=""):
        self.name, self.cols, self.rows, self.cw, self.ch = name, cols, rows, cw, ch
        self.W, self.H = cols * cw, rows * ch
        for v in (self.W, self.H):
            assert v & (v - 1) == 0, f"{name}: atlas side {v} is not a power of two"
        self.img = np.zeros((self.H, self.W, 3), np.uint8)
        self.sub, self.kind, self.intended = sub, kind, intended
        self.sequences = []
        self.cells = {}

    def put(self, col, row, packed):
        assert packed.shape == (self.ch, self.cw, 3), (self.name, packed.shape)
        self.img[row * self.ch:(row + 1) * self.ch, col * self.cw:(col + 1) * self.cw] = packed

    def cell(self, col, row):
        return self.img[row * self.ch:(row + 1) * self.ch, col * self.cw:(col + 1) * self.cw]

    def seq(self, name, row, frames, fps=None, loop=False, pivot=(0.5, 0.5), intended="", col0=0, **extra):
        d = dict(name=name, row=row, col0=col0, frames=frames, fps=fps, loop=loop, pivot=list(pivot),
                 intended=intended)
        d.update(extra)
        self.sequences.append(d)

    @property
    def rel(self):
        return f"{self.sub}/{self.name}.png"

    def save(self, fps=None, **extra):
        path = os.path.join(OUT, self.sub, self.name + ".png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.fromarray(self.img, "RGB").save(path, optimize=True)
        entry = dict(file=self.rel, kind=self.kind, size=[self.W, self.H], grid=[self.cols, self.rows],
                     cell=[self.cw, self.ch], frames=sum(s["frames"] for s in self.sequences) or self.cols * self.rows,
                     fps=fps, intended=self.intended, sequences=self.sequences)
        entry.update(extra)
        register(entry)
        return path


def _call(job):
    fn, args = job
    return fn(*args)


def pmap(fn, jobs, workers=None):
    """Paint cells in parallel: fn must be a module-level function, jobs a list of argument tuples."""
    from concurrent.futures import ProcessPoolExecutor
    jobs = list(jobs)
    if len(jobs) <= 2 or os.environ.get("VFX_SERIAL"):
        return [fn(*a) for a in jobs]
    n = workers or int(os.environ.get("VFX_WORKERS", 0)) or max(1, min(10, (os.cpu_count() or 4) - 2))
    with ProcessPoolExecutor(max_workers=n) as ex:
        return list(ex.map(_call, [(fn, a) for a in jobs], chunksize=1))


def register(entry):
    for i, e in enumerate(MANIFEST):
        if e["file"] == entry["file"]:
            MANIFEST[i] = entry
            return
    MANIFEST.append(entry)


def save_gray(rel, a, kind, intended, **extra):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(np.clip(np.round(a * 255), 0, 255).astype(np.uint8), "L").save(path, optimize=True)
    e = dict(file=rel.replace("\\", "/"), kind=kind, size=[a.shape[1], a.shape[0]], grid=[1, 1], frames=1, fps=None,
             intended=intended)
    e.update(extra)
    register(e)
    return path


def load_atlas(rel):
    return np.asarray(Image.open(os.path.join(OUT, rel)).convert("RGB"))


# ------------------------------------------------------------------------------------------------
# the reference shader (what vfx.wesl computes) and sheet compositing
# ------------------------------------------------------------------------------------------------
_RAMP_CACHE = {}


def ramp_linear(key, posterize=True):
    k = (key, posterize)
    if k not in _RAMP_CACHE:
        t = ramp_table(key, posterize)
        _RAMP_CACHE[k] = (s2l(t[:, :3]), t[:, 3] * 4.0)
    return _RAMP_CACHE[k]


def resample(packed, scale):
    """Bilinear resample of a packed cell (what the GPU sampler does)."""
    if abs(scale - 1.0) < 1e-6:
        return packed.astype(np.float32) / 255.0
    h, w = packed.shape[:2]
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    chans = [np.asarray(Image.fromarray(packed[..., i]).resize((nw, nh), Image.BILINEAR), np.float32) / 255.0
             for i in range(3)]
    return np.stack(chans, -1)


def shade(tex, ramp="kinetic", t=0.0, value=None, alpha=1.0, gain=1.0, scale=1.0, posterize=True, cool=0.0,
          ink_alpha=INK_ALPHA):
    """The reference fragment shader. tex = float (h, w, 3) packed texture at display resolution.
    Returns premultiplied linear HDR (h, w, 4): rgb and alpha, where hot values contribute additively.

      coverage = smoothstep(0.5 - w, 0.5 + w, R)          w = 0.7 / (2 * SDF_SPREAD * scale)
      coverage *= smoothstep(t - 0.05, t, B)              (t = eroded age; 0 = untouched)
      v = value override or G; v -= cool * (1 - B) * t    (cooling: old, low-B texels drop a band)
      rgb, gain = ramp(v); ink band (v < 0.18) alpha *= 0.9
      add = smoothstep(0.80, 0.90, v)
      out = (rgb * gain * coverage, coverage * (1 - add))  premultiplied, AlphaMode::Premultiplied
    """
    R, G, B = tex[..., 0], tex[..., 1], tex[..., 2]
    w = 0.7 / (2 * SDF_SPREAD * max(scale, 1e-3))
    cov = smoothstep(0.5 - w, 0.5 + w, R)
    if t > 0:
        cov = cov * smoothstep(t - 0.05, t, B)
    v = G if value is None else np.full_like(G, value)
    if cool > 0:
        v = np.clip(v - cool * t * (1.2 - B), 0, 1)
    rgb_t, gain_t = ramp_linear(ramp, posterize)
    x = np.clip(v * 255.0, 0, 255)
    i0 = np.floor(x).astype(int)
    i1 = np.minimum(i0 + 1, 255)
    f = (x - i0)[..., None]
    rgb = rgb_t[i0] * (1 - f) + rgb_t[i1] * f
    g = gain_t[i0] * (1 - f[..., 0]) + gain_t[i1] * f[..., 0]
    a = cov * alpha * np.where(v < BAND_EDGES[0], ink_alpha, 1.0)
    add = smoothstep(ADD_FROM, ADD_TO, v)
    out = np.zeros(tex.shape[:2] + (4,), np.float32)
    out[..., :3] = rgb * (g * gain)[..., None] * a[..., None]
    out[..., 3] = a * (1 - add)
    return out


class Plate:
    """A linear-light compositing surface for contact sheets: premultiplied over, bloom, tonemap."""

    def __init__(self, w, h, bg="#141016", image=None):
        if image is not None:
            self.img = s2l(np.asarray(image.convert("RGB"), np.float32) / 255.0)
        else:
            self.img = np.ones((h, w, 3), np.float32) * s2l(hexrgb(bg))
        self.H, self.W = self.img.shape[:2]
        self.labels = []

    def over(self, px, x, y):
        """Composite a premultiplied (h, w, 4) layer with its top-left at (x, y)."""
        h, w = px.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.W, x + w), min(self.H, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        src = px[y0 - y:y1 - y, x0 - x:x1 - x]
        dst = self.img[y0:y1, x0:x1]
        dst[:] = src[..., :3] + dst * (1 - src[..., 3:4])

    def rect(self, x0, y0, x1, y1, col, alpha=1.0):
        c = s2l(hexrgb(col)) if isinstance(col, str) else np.asarray(col, np.float32)
        self.img[y0:y1, x0:x1] = self.img[y0:y1, x0:x1] * (1 - alpha) + c * alpha

    def paste(self, image, x, y):
        a = s2l(np.asarray(image.convert("RGB"), np.float32) / 255.0)
        h, w = a.shape[:2]
        self.img[y:y + h, x:x + w] = a[:max(0, min(h, self.H - y)), :max(0, min(w, self.W - x))]

    def label(self, x, y, text, size=15, fill=(236, 226, 210), font="AlegreyaSans-Medium.ttf", anchor="la"):
        self.labels.append((x, y, text, size, fill, font, anchor))

    def finish(self, bloom=0.22, shoulder=0.8):
        img = self.img
        src = np.clip(img - 0.9, 0, None)
        b = np.zeros_like(img)
        for r, wgt in ((2.0, 0.45), (6.0, 0.35), (16.0, 0.2)):
            b += ndi.gaussian_filter(src, sigma=(r, r, 0)) * wgt
        out = img + b * bloom * 2.5
        mx = out.max(axis=2, keepdims=True)
        out = out + np.clip(mx - 1.0, 0, None) * 0.18
        k = shoulder
        out = np.where(out < k, out, k + (1 - k) * (1 - np.exp(-(out - k) / (1 - k))))
        im = Image.fromarray((l2s(out) * 255 + 0.5).astype(np.uint8))
        d = ImageDraw.Draw(im)
        for x, y, text, size, fill, font, anchor in self.labels:
            f = ImageFont.truetype(os.path.join(FONTS, font), size)
            d.text((x, y), text, font=f, fill=fill, anchor=anchor, stroke_width=2, stroke_fill=(12, 8, 10))
        return im


def fnt(size, name="AlegreyaSans-Medium.ttf"):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def write_manifest():
    path = os.path.join(OUT, "vfx_assets.json")
    doc = dict(
        version=1,
        generator="tools/vfx/build_all.py",
        spec="docs/art/VFX_STYLE.md sections 3, 21 and 22",
        conventions=dict(
            packed_channels=dict(
                R="shape mask as a signed distance field; 0.5 = edge; +-%g cell px -> 1.0 / 0.0" % SDF_SPREAD,
                G="value on the ramp: ink %.2f, deep %.2f, body %.2f, light %.2f, hot %.2f; band edges %s"
                  % (V_INK, V_DEEP, V_BODY, V_LIGHT, V_HOT, list(BAND_EDGES)),
                B="erosion order: visible while B > t (t = normalized age x erode); low = erodes first",
            ),
            color_space="packed atlases, trails, smears and noise are linear data (load with is_srgb = false); "
                        "ramps are sRGB colour with A = HDR gain / 4",
            premultiplied="packed data is never premultiplied; the shader outputs premultiplied colour "
                          "(AlphaMode::Premultiplied) and hot values (G > %.2f) fade to additive by G = %.2f"
                          % (ADD_FROM, ADD_TO),
            shader_reference="tools/vfx/vfxlib.py shade(): coverage = smoothstep(0.5-w, 0.5+w, R) with "
                             "w = fwidth(R) * 0.7; coverage *= smoothstep(t-0.05, t, B); rgb, gain = "
                             "ramp(G); ink band alpha x %.2f; out = (rgb*gain*a, a*(1-add))" % INK_ALPHA,
            ramp_rows={k: i for i, (k, _, _) in enumerate(RAMPS)},
            band_gain=list(BAND_GAIN),
            uv="atlas cells: u right, v down (image rows); frame i of a sequence is cell (col0 + i, row)",
            pivot="per sequence: the effect origin in cell-relative uv (0..1)",
            flipbook_timing="fps is the playback rate; frame_times_60 (when present) lists the 60 fps frame each "
                            "flipbook frame was painted at, so a front-loaded burst plays fast-in, slow-out at a "
                            "constant fps",
            strips="trails and smears: u = 0 at the tail (oldest end), 1 at the head (newest end); v = 0 inner / "
                   "left edge, 1 outer / right edge; tileable_u rows repeat seamlessly along u",
            meshes="glTF 2.0 binary, +Y up, forward = -Z (Transform::looking_to), metres; COLOR_0 carries the "
                   "same packing (R = 1 mask, G = value band, B = erosion order); UV0 as documented per mesh",
            sizes="radius_in_cell: the gameplay radius R as a fraction of the half cell; quad side = 2R / "
                  "radius_in_cell",
        ),
        assets=sorted(MANIFEST, key=lambda e: e["file"]),
    )
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return path


def load_manifest():
    path = os.path.join(OUT, "vfx_assets.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        MANIFEST[:] = doc.get("assets", [])
