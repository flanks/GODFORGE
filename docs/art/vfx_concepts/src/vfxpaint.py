"""Paint-over toolkit for GODFORGE VFX concept frames.

Everything works in the full screenshot's pixel coordinates (1600x900); a Canvas crops and scales,
so the same recipe renders the 1:1 frame and a 2x detail inset. Colour math is linear, additive
light accumulates a bloom source, and `finish` tonemaps hot cores toward white like TonyMcMapface.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

K_ISO = math.sin(math.radians(55.0))  # ground depth -> screen y
H_ISO = math.cos(math.radians(55.0))  # height -> screen y
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "assets", "fonts") + os.sep


def s2l(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def l2s(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def hx(h):
    h = h.lstrip("#")
    return s2l([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


# ---- colour ramps: ink, deep, body, light, hot -------------------------------------------------
RAMPS = {
    "kinetic": ["#1A120C", "#8A4A16", "#E3A64A", "#F4E3C1", "#FFFBF0"],
    "flame": ["#240A06", "#A8300A", "#FF7A1A", "#FFC24B", "#FFF3D6"],
    "storm": ["#06101E", "#1B4E9B", "#3FD8FF", "#BDF6FF", "#FFFFFF"],
    "void": ["#0C0416", "#3B1675", "#A45CFF", "#E2CCFF", "#FFF6FF"],
    "plague": ["#0D1507", "#3A6414", "#86E03A", "#D9FF8C", "#F6FFE0"],
    "radiant": ["#241703", "#B07A12", "#FFE27A", "#FFF3BE", "#FFFFFF"],
    "unmade": ["#07060A", "#0D3B35", "#2FBFA8", "#8FF2D8", "#E0FFF6"],
    "godworks": ["#1E1408", "#5A4A20", "#D4B45A", "#F4E6B0", "#FFF4D0"],
    "enemy": ["#1A0610", "#7A1040", "#FF5AA8", "#FFC0E0", "#FFFFFF"],
}


class Ramp:
    def __init__(self, key):
        self.key = key
        self.ink, self.deep, self.body, self.light, self.hot = [hx(c) for c in RAMPS[key]]


class Noise:
    """Tiling value noise sampled at arbitrary coordinates (bilinear, fractal)."""

    def __init__(self, seed, n=97):
        self.g = np.random.default_rng(seed).random((n, n)).astype(np.float32)
        self.g = ndi.gaussian_filter(self.g, 0.6, mode="wrap")
        self.g = (self.g - self.g.min()) / (self.g.max() - self.g.min())

    def __call__(self, u, v, octaves=3):
        s = 0.0
        a = 1.0
        t = 0.0
        f = 1.0
        for _ in range(octaves):
            s = s + a * ndi.map_coordinates(self.g, [v * f, u * f], order=1, mode="grid-wrap")
            t += a
            a *= 0.5
            f *= 2.03
        return s / t


def wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def clean_image(im, patches):
    """Paint out old-style effects: copy feathered floor patches (dst_x, dst_y, src_x, src_y, r)."""
    a = np.asarray(im, np.float32).copy()
    H, W = a.shape[:2]
    for dx, dy, sx, sy, r in patches:
        R = int(r * 1.6) + 2
        for y in range(max(0, dy - R), min(H, dy + R)):
            for x in range(max(0, dx - R), min(W, dx + R)):
                d = math.hypot(x - dx, y - dy) / r
                if d < 1.6:
                    w = 1.0 if d < 1.0 else max(0.0, 1 - (d - 1) / 0.6)
                    X, Y = x - dx + sx, y - dy + sy
                    if 0 <= X < W and 0 <= Y < H:
                        a[y, x] = a[y, x] * (1 - w) + a[Y, X] * w
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class Canvas:
    def __init__(self, path, crop, S=1, clean=None):
        im = Image.open(path).convert("RGB")
        if clean:
            im = clean_image(im, clean)
        im = im.crop(crop)
        if S != 1:
            im = im.resize((int(round(im.width * S)), int(round(im.height * S))), Image.LANCZOS)
        self.S = S
        self.ox, self.oy = crop[0], crop[1]
        self.img = s2l(np.asarray(im, np.float32) / 255.0)
        self.base = self.img.copy()
        self.bloom = np.zeros_like(self.img)
        self.H, self.W = self.img.shape[:2]

    # -- regions --------------------------------------------------------------------------------
    def _pix(self, bbox):
        x0, y0, x1, y1 = bbox
        px0 = max(0, int(math.floor((x0 - self.ox) * self.S)))
        px1 = min(self.W, int(math.ceil((x1 - self.ox) * self.S)))
        py0 = max(0, int(math.floor((y0 - self.oy) * self.S)))
        py1 = min(self.H, int(math.ceil((y1 - self.oy) * self.S)))
        if px1 <= px0 or py1 <= py0:
            return None
        return px0, py0, px1, py1

    def grid(self, bbox, ss=3):
        p = self._pix(bbox)
        if p is None:
            return None
        px0, py0, px1, py1 = p
        xs = px0 + (np.arange((px1 - px0) * ss) + 0.5) / ss
        ys = py0 + (np.arange((py1 - py0) * ss) + 0.5) / ss
        X = (self.ox + xs / self.S).astype(np.float32)
        Y = (self.oy + ys / self.S).astype(np.float32)
        XX, YY = np.meshgrid(X, Y)
        return (slice(py0, py1), slice(px0, px1)), XX, YY, ss

    @staticmethod
    def down(a, ss):
        h, w = a.shape
        return a.reshape(h // ss, ss, w // ss, ss).mean(axis=(1, 3))

    def raster(self, polys=(), lines=(), dots=(), ss=3, pad=4):
        """PIL-rasterise polygons [(pts)], lines [(pts, width)], dots [(x, y, r)] -> (slice, mask)."""
        xs, ys = [], []
        for pts in polys:
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
        for pts, w in lines:
            xs += [p[0] - w for p in pts] + [p[0] + w for p in pts]
            ys += [p[1] - w for p in pts] + [p[1] + w for p in pts]
        for x, y, r in dots:
            xs += [x - r, x + r]
            ys += [y - r, y + r]
        if not xs:
            return None
        p = self._pix((min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad))
        if p is None:
            return None
        px0, py0, px1, py1 = p
        img = Image.new("L", ((px1 - px0) * ss, (py1 - py0) * ss), 0)
        d = ImageDraw.Draw(img)
        k = self.S * ss

        def tp(pt):
            return ((pt[0] - self.ox) * self.S - px0) * ss, ((pt[1] - self.oy) * self.S - py0) * ss

        for pts in polys:
            if len(pts) >= 3:
                d.polygon([tp(q) for q in pts], fill=255)
        for pts, w in lines:
            q = [tp(pt) for pt in pts]
            wpx = max(1, int(round(w * k)))
            d.line(q, fill=255, width=wpx, joint="curve")
            for e in (q[0], q[-1]):
                rr = wpx / 2
                d.ellipse((e[0] - rr, e[1] - rr, e[0] + rr, e[1] + rr), fill=255)
        for x, y, r in dots:
            cx, cy = tp((x, y))
            rr = r * k
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=255)
        a = np.asarray(img, np.float32) / 255.0
        return (slice(py0, py1), slice(px0, px1)), self.down(a, ss)

    # -- compositing ----------------------------------------------------------------------------
    def over(self, sl, a, col, bloom=0.0):
        if a is None:
            return
        a = np.clip(a, 0, 1)[..., None]
        r = self.img[sl]
        col = np.asarray(col, np.float32)
        r[:] = r * (1 - a) + col * a
        self.bloom[sl] *= 1 - a  # ink swallows the light under it
        if bloom > 0:
            self.bloom[sl] += col * a * bloom

    def fill(self, r, col, alpha=1.0, bloom=0.0):
        """Alpha-over a raster/field result (sl, cov, ...) that may be None (clipped away)."""
        if r:
            self.over(r[0], r[1] * alpha, col, bloom)

    def add(self, sl, a, col, gain=1.0, bloom=1.0):
        if a is None:
            return
        c = np.clip(a, 0, None)[..., None] * np.asarray(col, np.float32) * gain
        self.img[sl] += c
        self.bloom[sl] += c * bloom

    def light(self, sl, a, col, gain=1.0):
        """Light spill: tint and brighten the base (ground lit by the flash)."""
        c = np.clip(a, 0, None)[..., None] * np.asarray(col, np.float32) * gain
        self.img[sl] += self.base[sl] * c

    def darken(self, sl, a, k):
        self.img[sl] *= 1 - np.clip(a, 0, 1)[..., None] * k

    def restore_danger(self, c, rx, ry, alpha=0.92, g_ratio=0.62, b_ratio=0.5):
        """Telegraphs draw above player VFX: put red-dominant base pixels back inside the ellipse."""
        g = ellipse_field(self, c, rx, ry, ss=1)
        if not g:
            return
        sl, X, Y, d, ss = g
        b = l2s(self.base[sl])
        red = (b[..., 0] > 0.5) & (b[..., 1] < g_ratio * b[..., 0]) & (b[..., 2] < b_ratio * b[..., 0]) & (d <= 1.0)
        a = red.astype(np.float32)[..., None] * alpha
        self.img[sl] = self.img[sl] * (1 - a) + self.base[sl] * a
        self.bloom[sl] *= 1 - a

    def protect(self, c, rx, ry, alpha=1.0):
        """Ground layers render under characters: restore the base inside a soft ellipse."""
        g = ellipse_field(self, c, rx, ry, ss=1)
        if not g:
            return
        sl, X, Y, d, ss = g
        a = (np.clip((1.0 - d) / 0.2, 0, 1) * alpha)[..., None]
        self.img[sl] = self.img[sl] * (1 - a) + self.base[sl] * a
        self.bloom[sl] *= 1 - a

    def finish(self, bloom=0.35, radii=(2.5, 7.0, 18.0), weights=(0.5, 0.32, 0.18)):
        b = np.zeros_like(self.img)
        for r, w in zip(radii, weights):
            b += ndi.gaussian_filter(self.bloom, sigma=(r * self.S, r * self.S, 0)) * w
        out = self.img + b * bloom
        # hot cores bleed toward white (TonyMcMapface-like), then a soft shoulder
        mx = out.max(axis=2, keepdims=True)
        excess = np.clip(mx - 1.0, 0, None)
        out = out + excess * 0.45
        k = 0.82
        out = np.where(out < k, out, k + (1 - k) * (1 - np.exp(-(out - k) / (1 - k))))
        return Image.fromarray((l2s(out) * 255 + 0.5).astype(np.uint8))


# ---- geometry helpers ---------------------------------------------------------------------------
def ground(c, dx_m, dz_m, ppm):
    """Screen point of a ground offset (dx right, dz toward the camera) from screen point c."""
    return (c[0] + dx_m * ppm, c[1] + dz_m * ppm * K_ISO)


def up(p, h_m, ppm):
    return (p[0], p[1] - h_m * ppm * H_ISO)


def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def norm(v):
    L = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / L, v[1] / L)


# ---- field shapes -------------------------------------------------------------------------------
def prof(t, peak=0.72, pw=1.3):
    a = np.clip(t / peak, 0, 1)
    upw = np.sin(a * np.pi / 2) ** pw
    b = np.clip((t - peak) / (1 - peak), 0, 1)
    cap = np.sqrt(np.clip(1 - b * b, 0, 1))
    return np.where(t < peak, upw, cap)


def crescent(cv, c, R, a0, a1, width, ky=K_ISO, rotation=0.0, seed=1, erode=0.75, ss=3, peak=0.72,
             rim=0.2, streak=(2.5, 9.0), inner_rag=0.35):
    """Crescent smear field. Returns (sl, cov, rimcov, headcov) or None. Angles in radians in the
    (unsquashed) plane; sweep a0 (tail) -> a1 (head). `ky` squashes y (K_ISO = lies on the ground)."""
    pad = width + 4
    g = cv.grid((c[0] - R - pad, c[1] - (R + pad) * ky - 2, c[0] + R + pad, c[1] + (R + pad) * ky + 2), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    x = X - c[0]
    y = (Y - c[1]) / ky
    cr, sr = math.cos(-rotation), math.sin(-rotation)
    xl = x * cr - y * sr
    yl = x * sr + y * cr
    th = np.arctan2(yl, xl)
    r = np.hypot(xl, yl)
    span = a1 - a0
    sg = 1.0 if span >= 0 else -1.0
    d = np.mod((th - a0) * sg, 2 * np.pi)
    t = d / abs(span)
    w = width * prof(np.clip(t, 0, 1), peak)
    s = (R - r) / np.maximum(w, 1e-3)
    nz = Noise(seed)
    n = nz(t * streak[0] * 8, s * streak[1] + t * 0.7, 3)
    thr = erode * (1 - np.clip(t, 0, 1)) ** 1.6
    rag = 1 - inner_rag * nz(t * 20 + 5, s * 2 + 11, 2)
    inside = (t <= 1) & (s >= 0) & (s <= rag) & (n > thr)
    cov = cv.down(inside.astype(np.float32), ss)
    rimm = cv.down((inside & (s < rim)).astype(np.float32), ss)
    head = cv.down((inside * np.clip((t - 0.55) / 0.45, 0, 1)).astype(np.float32), ss)
    return sl, cov, rimm, head


def star(cv, c, spikes, r_in, ky=1.0, ss=3, p=1.5):
    """Spiky impact star. spikes = [(angle, length, half_width_rad)]. Returns (sl, cov, core)."""
    L = max([s[1] for s in spikes] + [r_in]) + 3
    g = cv.grid((c[0] - L, c[1] - L * ky, c[0] + L, c[1] + L * ky), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    x = X - c[0]
    y = (Y - c[1]) / ky
    th = np.arctan2(y, x)
    r = np.hypot(x, y)
    edge = np.full_like(r, r_in)
    for a, ln, h in spikes:
        dd = np.abs(wrap(th - a))
        k = np.clip(1 - dd / h, 0, 1) ** p
        edge = np.maximum(edge, r_in + (ln - r_in) * k)
    inside = r <= edge
    core = np.clip(1 - r / np.maximum(edge, 1e-3), 0, 1) * inside
    return sl, cv.down(inside.astype(np.float32), ss), cv.down(core.astype(np.float32), ss)


def rand_spikes(rng, n, L, jitter=0.35, hw=0.22, long_short=True, a0=None, cone=None):
    a0 = rng.uniform(0, 2 * math.pi) if a0 is None else a0
    out = []
    for i in range(n):
        if cone is None:
            a = a0 + 2 * math.pi * i / n + rng.uniform(-0.25, 0.25) * 2 * math.pi / n
        else:
            a = cone[0] + cone[1] * (2 * i / max(1, n - 1) - 1) + rng.uniform(-0.08, 0.08)
        ln = L * (1.0 if (i % 2 == 0 or not long_short) else 0.55) * (1 + rng.uniform(-jitter, jitter))
        out.append((a, ln, hw * (1 + rng.uniform(-0.3, 0.3))))
    return out


def ellipse_field(cv, c, rx, ry, ss=2, pad=2):
    g = cv.grid((c[0] - rx - pad, c[1] - ry - pad, c[0] + rx + pad, c[1] + ry + pad), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    d = np.hypot((X - c[0]) / rx, (Y - c[1]) / ry)
    return sl, X, Y, d, ss


def soft(cv, c, rx, ry, power=2.0):
    """Soft radial falloff (1 at centre -> 0 at the ellipse), for light spill and glows."""
    g = ellipse_field(cv, c, rx, ry, ss=1)
    if g is None:
        return None
    sl, X, Y, d, ss = g
    return sl, np.clip(1 - d, 0, 1) ** power


def ring(cv, c, R, thick, ky=K_ISO, seed=3, gaps=0.35, ss=3, taper=True, wob=0.12):
    """Broken ground ring (an accent, never a full circle). Returns (sl, cov, inner_t)."""
    pad = thick + 4
    g = cv.grid((c[0] - R - pad, c[1] - (R + pad) * ky, c[0] + R + pad, c[1] + (R + pad) * ky), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    x = X - c[0]
    y = (Y - c[1]) / ky
    th = np.arctan2(y, x)
    r = np.hypot(x, y)
    nz = Noise(seed)
    u = (th + np.pi) / (2 * np.pi) * 6
    n = nz(u * 4, np.full_like(u, 3.3), 2)
    w = thick * (0.45 + 0.8 * n) if taper else thick
    rr = R * (1 + wob * (nz(u * 2 + 9, np.full_like(u, 7.1), 2) - 0.5))
    band = np.abs(r - rr) <= w / 2
    keep = n > gaps
    inside = band & keep
    tt = np.clip((r - (rr - w / 2)) / np.maximum(w, 1e-3), 0, 1)
    return sl, cv.down(inside.astype(np.float32), ss), cv.down((inside * tt).astype(np.float32), ss)


def blob_field(cv, circles, seed=5, rough=0.22, ss=2, light_dir=(0.0, -1.0), light_pt=None, rim=0.2, mid=0.45):
    """Union of noisy circles (smoke puffs), painter's order. Returns (sl, cov, tone): tone is a coverage-
    weighted 0 (shadow) / 1 (mid) / 2 (lit rim) map. Rim and mid are crescents on the side facing the light."""
    if not circles:
        return None
    xs = [c[0] - c[2] * 1.3 for c in circles] + [c[0] + c[2] * 1.3 for c in circles]
    ys = [c[1] - c[2] * 1.3 for c in circles] + [c[1] + c[2] * 1.3 for c in circles]
    g = cv.grid((min(xs), min(ys), max(xs), max(ys)), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    nz = Noise(seed)
    cov = np.zeros_like(X, dtype=bool)
    tone = np.zeros_like(X)
    for i, (cx, cy, r) in enumerate(circles):
        dx = X - cx
        dy = Y - cy
        th = np.arctan2(dy, dx)
        wob = rough * (nz((th + np.pi) * 2 + i * 7.7, np.full_like(th, i * 3.1), 2) - 0.5) * 2
        rn = r * (1 + wob)
        d = np.hypot(dx, dy)
        ins = d <= rn
        if light_pt is not None:
            ld = norm((light_pt[0] - cx, light_pt[1] - cy))
        else:
            ld = norm(light_dir)
        # distance from a circle shifted away from the light: outside it = the lit crescent
        d_rim = np.hypot(dx + ld[0] * r * rim, dy + ld[1] * r * rim) / np.maximum(rn, 1e-3)
        d_mid = np.hypot(dx + ld[0] * r * mid, dy + ld[1] * r * mid) / np.maximum(rn, 1e-3)
        t = np.where(d_rim > 1.0, 2.0, np.where(d_mid > 1.0, 1.0, 0.0))
        tone = np.where(ins, t, tone)
        cov |= ins
    covf = cv.down(cov.astype(np.float32), ss)
    tonef = cv.down(np.where(cov, tone, 0).astype(np.float32), ss) / np.maximum(covf, 1e-3)
    return sl, covf, tonef


# ---- polygon shapes -----------------------------------------------------------------------------
def kite(p, d, L, w, back=0.35):
    d = norm(d)
    n = (-d[1], d[0])
    tip = (p[0] + d[0] * L, p[1] + d[1] * L)
    tail = (p[0] - d[0] * L * back, p[1] - d[1] * L * back)
    return [tip, (p[0] + n[0] * w, p[1] + n[1] * w), tail, (p[0] - n[0] * w, p[1] - n[1] * w)]


def streak_poly(p0, p1, w0, w1=0.0, cap=True):
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


def tapered_path(pts, widths):
    """Polygon around a polyline with per-point widths (ribbons, trails, tongues)."""
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


def bolt_points(p0, p1, rng, jag=0.22, depth=5):
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


def flame_tongue(base, H, W, rng, lean=0.0, curl=0.35, n=18):
    """A flame tongue polygon rising from base (screen up), leaning and curling at the tip."""
    spine = []
    widths = []
    ph = rng.uniform(0, 6.28)
    for i in range(n):
        t = i / (n - 1)
        sway = W * curl * math.sin(ph + t * 3.2) * t + lean * H * t * t
        spine.append((base[0] + sway, base[1] - H * t))
        widths.append(W * (math.sin(math.pi * min(1.0, t ** 0.75)) ** 0.9) * (1 - t) ** 0.35 + 0.4)
    return tapered_path(spine, widths)


# ---- text ---------------------------------------------------------------------------------------
def draw_text(img, xy, text, size, fill, font="DejaVuSans.ttf", stroke=2, stroke_fill=(20, 10, 8), anchor="mm"):
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_DIR + font, size)
    d.text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor=anchor)
    return img


def ribbon_field(cv, pts, widths, ss=2, pad=3):
    """Per-pixel ribbon around a polyline (head = pts[0]). Returns (sl, X, Y, inside, t, s, ss): t = 0 head ->
    1 tail along the length, s = -1..1 across (left..right of travel)."""
    P = np.asarray(pts, np.float32)
    Wd = np.asarray(widths, np.float32)
    wmax = float(Wd.max()) / 2 + pad
    g = cv.grid((P[:, 0].min() - wmax, P[:, 1].min() - wmax, P[:, 0].max() + wmax, P[:, 1].max() + wmax), ss)
    if g is None:
        return None
    sl, X, Y, ss = g
    seg = np.linalg.norm(P[1:] - P[:-1], axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = max(cum[-1], 1e-3)
    best = np.full(X.shape, 1e9, np.float32)
    tt = np.zeros(X.shape, np.float32)
    ss_ = np.zeros(X.shape, np.float32)
    ww = np.zeros(X.shape, np.float32)
    for i in range(len(P) - 1):
        a = P[i]
        b = P[i + 1]
        ab = b - a
        L2 = float(ab @ ab) or 1e-6
        u = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0, 1)
        qx = a[0] + ab[0] * u
        qy = a[1] + ab[1] * u
        dx = X - qx
        dy = Y - qy
        dist = np.hypot(dx, dy)
        w = (Wd[i] + (Wd[i + 1] - Wd[i]) * u) / 2
        rel = dist / np.maximum(w, 1e-3)
        m = rel < best
        best = np.where(m, rel, best)
        tt = np.where(m, (cum[i] + u * seg[i]) / total, tt)
        side = np.sign(ab[0] * dy - ab[1] * dx)
        ss_ = np.where(m, side * np.minimum(rel, 1), ss_)
        ww = np.where(m, w, ww)
    inside = best <= 1.0
    return sl, X, Y, inside, tt, ss_, ss
