"""GODFORGE UI texture kit: the rendering core.

Every piece is designed in *logical* px (1920x1080 UI units, UiScale 1.0) exactly as the numbers in
docs/art/UI_STYLE.md read, and rendered @2x (LP = 2 texture px per logical px), supersampled SS = 4
times per texture px (8 samples per logical px) and box-filtered down, so every edge is anti-aliased.

Shapes are signed distance fields (SDF) in logical px: negative inside. Coverage, insets, rings,
bevel heights and edge lines are all read off the SDF, which keeps hairlines exact at any size.
Colour work happens in premultiplied float RGBA; the output PNG is straight-alpha sRGB RGBA8.

Everything here is original GODFORGE work (README "IP hygiene"): no traced or sampled shapes.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

SS = 4   # supersamples per texture px (each axis)
LP = 2   # texture px per logical px (@2x)

# ───────────────────────────── tokens (UI_STYLE §3) ─────────────────────────────
TOK = {
    "lac0": "#0B0807", "lac1": "#130D0A", "lac2": "#2A1E16", "lac3": "#4A3624",
    "scrim": "#06050A", "pool": "#050302",
    "gold_hi": "#FFECB0", "gold_lt": "#F2C667", "gold_md": "#C9933E", "gold_dk": "#7A5424", "gold_sh": "#3B2610",
    "parch": "#F4E6C8", "parch_dim": "#B9A98C", "parch_mute": "#7D705E", "numeral": "#FFF8EA",
    "ink": "#0A0706", "ink_text": "#1A120B",
    "ichor": "#FFE9B0", "ichor_glow": "#FFC873", "ready_glow": "#FFC24A", "loss": "#A58C86",
    "hp_lt": "#E8574C", "hp": "#C8323A", "hp_dk": "#7E1420", "hp_ghost": "#F0B37A", "ward": "#DCE6EA",
    "danger": "#FF3B30",
    "stud": "#E9D3A0", "gem_ivory": "#FFE7A6",
}
RARITY = {"common": "#CFC6B4", "rare": "#4FA3FF", "epic": "#B865FF", "godforged": "#FFB82E"}

# Shading ramps: t = 0 (facing away, in shadow) .. 1 (specular). The gold ramp is built on the
# token stops so the metal always lands on gold_sh / gold_dk / gold_md / gold_lt / gold_hi.
GOLD = [(0.00, "#1C1007"), (0.10, "#3B2610"), (0.30, "#7A5424"), (0.52, "#C9933E"), (0.71, "#F2C667"),
        (0.87, "#FFECB0"), (1.00, "#FFFBEE")]
BRONZE = [(0.00, "#120B06"), (0.12, "#2E2012"), (0.34, "#6E5234"), (0.58, "#B08A5A"), (0.80, "#E6CFA0"),
          (1.00, "#FBF1DC")]
STEEL = [(0.00, "#0C0D10"), (0.18, "#2A2F36"), (0.42, "#4E5660"), (0.66, "#9AA4AE"), (0.86, "#DDE3E8"),
         (1.00, "#F8FAFC")]
IRON = [(0.00, "#070708"), (0.20, "#16171A"), (0.45, "#2E3036"), (0.68, "#55595F"), (0.86, "#8E939A"),
        (1.00, "#D4D8DD")]
# the flat hairline ramp of §3.1 (soft ramp lt -> md -> dk), used for keylines and code-like lines
GOLD_SOFT = [(0.0, "#F2C667"), (0.5, "#C9933E"), (1.0, "#7A5424")]

LIGHT = (-0.55, -0.85, 0.75)   # top-left key light (§8.3)


# ───────────────────────────── colour helpers ─────────────────────────────
def rgb(h: str) -> np.ndarray:
    h = TOK.get(h, h).lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def mixc(a, b, t: float) -> np.ndarray:
    a = rgb(a) if isinstance(a, str) else np.asarray(a, np.float32)
    b = rgb(b) if isinstance(b, str) else np.asarray(b, np.float32)
    return a + (b - a) * t


def ramp(t: np.ndarray, stops) -> np.ndarray:
    xs = np.array([s[0] for s in stops], np.float32)
    cs = np.array([rgb(s[1]) if isinstance(s[1], str) else s[1] for s in stops], np.float32)
    out = np.empty(t.shape + (3,), np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, xs, cs[:, c])
    return out


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ───────────────────────────── the canvas ─────────────────────────────
class Cv:
    """A supersampled premultiplied RGBA canvas sized in logical px.

    `x`, `y` are the logical coordinates of every sample centre, so SDFs can be written directly
    in the spec's units. `k` is samples per logical px."""

    def __init__(self, lw: float, lh: float, lp: int = LP, ss: int = SS):
        self.lw, self.lh = lw, lh
        self.lp, self.ss = lp, ss
        self.k = lp * ss
        self.tw, self.th = int(round(lw * lp)), int(round(lh * lp))
        self.W, self.H = self.tw * ss, self.th * ss
        ys = (np.arange(self.H, dtype=np.float32) + 0.5) / self.k
        xs = (np.arange(self.W, dtype=np.float32) + 0.5) / self.k
        self.y, self.x = np.meshgrid(ys, xs, indexing="ij")
        self.px = np.zeros((self.H, self.W, 4), np.float32)

    # coverage of an SDF (logical px): a one-sample AA ramp, box-filtered later
    def cov(self, sdf: np.ndarray) -> np.ndarray:
        return np.clip(0.5 - sdf * self.k, 0.0, 1.0)

    def over(self, col, cov: np.ndarray, alpha: float = 1.0):
        a = (cov * alpha)[..., None]
        col = np.asarray(col, np.float32)
        if col.ndim == 1:
            col = col[None, None, :]
        self.px[..., :3] = col * a + self.px[..., :3] * (1.0 - a)
        self.px[..., 3:] = a + self.px[..., 3:] * (1.0 - a)

    def over_px(self, other: np.ndarray):
        a = other[..., 3:]
        self.px = other + self.px * (1.0 - a)

    def erase(self, cov: np.ndarray, amount: float = 1.0):
        """Punch transparency (destination-out)."""
        self.px *= (1.0 - cov * amount)[..., None]

    def image(self) -> Image.Image:
        s = self.ss
        p = self.px.reshape(self.th, s, self.tw, s, 4).mean(axis=(1, 3))
        a = p[..., 3:]
        rgbv = np.where(a > 1e-6, p[..., :3] / np.maximum(a, 1e-6), 0.0)
        out = np.concatenate([rgbv, a], axis=2)
        return Image.fromarray(np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8), "RGBA")


# ───────────────────────────── SDFs (logical px, negative inside) ─────────────────────────────
def sd_rrect(cv: Cv, x0, y0, x1, y1, r) -> np.ndarray:
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx, hy = (x1 - x0) / 2.0, (y1 - y0) / 2.0
    r = min(r, hx, hy)
    qx = np.abs(cv.x - cx) - (hx - r)
    qy = np.abs(cv.y - cy) - (hy - r)
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def sd_circle(cv: Cv, cx, cy, r) -> np.ndarray:
    return np.hypot(cv.x - cx, cv.y - cy) - r


def sd_segment(cv: Cv, a, b) -> np.ndarray:
    px, py = cv.x - a[0], cv.y - a[1]
    bx, by = b[0] - a[0], b[1] - a[1]
    h = np.clip((px * bx + py * by) / max(bx * bx + by * by, 1e-9), 0.0, 1.0)
    return np.hypot(px - bx * h, py - by * h)


def _inside_poly(cv: Cv, pts) -> np.ndarray:
    """Even-odd point-in-polygon for every sample (exact, no raster)."""
    x, y = cv.x, cv.y
    inside = np.zeros(x.shape, bool)
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        if ay == by:
            continue
        cond = (ay > y) != (by > y)
        xc = (bx - ax) * (y - ay) / (by - ay) + ax
        inside ^= cond & (x < xc)
    return inside


class _Win:
    """A rectangular window of a canvas (sample-index bounds) with its coordinate grids."""

    def __init__(self, cv: Cv, x0, y0, x1, y1):
        self.i0, self.i1 = max(0, int(math.floor(x0 * cv.k))), min(cv.W, int(math.ceil(x1 * cv.k)) + 1)
        self.j0, self.j1 = max(0, int(math.floor(y0 * cv.k))), min(cv.H, int(math.ceil(y1 * cv.k)) + 1)
        self.x = cv.x[self.j0:self.j1, self.i0:self.i1]
        self.y = cv.y[self.j0:self.j1, self.i0:self.i1]
        self.empty = self.i1 <= self.i0 or self.j1 <= self.j0


def _win_for(cv: Cv, pts, margin: float) -> _Win:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return _Win(cv, min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def sd_poly(cv: Cv, pts, exact: bool | None = None, margin: float = 8.0) -> np.ndarray:
    """SDF of a closed polygon, evaluated inside its bounding box grown by `margin` (outside it the
    field holds `margin`, i.e. 'far outside'; enough for bevels, edge lines and contact shadows).
    Exact per-edge distances when cheap, else an EDT of a raster."""
    n = len(pts)
    out = np.full(cv.x.shape, margin, np.float32)
    w = _win_for(cv, pts, margin)
    if w.empty:
        return out
    if exact is None:
        exact = n * w.x.size <= 2.5e8
    if exact:
        d = np.full(w.x.shape, np.inf, np.float32)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            px, py = w.x - ax, w.y - ay
            vx, vy = bx - ax, by - ay
            h = np.clip((px * vx + py * vy) / max(vx * vx + vy * vy, 1e-9), 0.0, 1.0)
            d = np.minimum(d, np.hypot(px - vx * h, py - vy * h))
        inside = np.zeros(w.x.shape, bool)
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay == by:
                continue
            cond = (ay > w.y) != (by > w.y)
            xc = (bx - ax) * (w.y - ay) / (by - ay) + ax
            inside ^= cond & (w.x < xc)
        out[w.j0:w.j1, w.i0:w.i1] = np.minimum(np.where(inside, -d, d), margin)
        return out
    m = Image.new("L", (w.i1 - w.i0, w.j1 - w.j0), 0)
    ImageDraw.Draw(m).polygon([(px * cv.k - w.i0, py * cv.k - w.j0) for px, py in pts], fill=255)
    ins = np.asarray(m) > 127
    d_in = ndimage.distance_transform_edt(ins)
    d_out = ndimage.distance_transform_edt(~ins)
    sdf = np.where(ins, -(d_in - 0.5), d_out - 0.5) / cv.k
    out[w.j0:w.j1, w.i0:w.i1] = np.minimum(sdf, margin)
    return out


def sd_stroke(cv: Cv, pts, rfun, margin: float = 8.0) -> np.ndarray:
    """SDF of a variable-width stroke along a polyline; rfun(t) gives the radius at normalised arc
    length t in [0, 1] (vectorised). Evaluated in the stroke's bounding box."""
    n = len(pts) - 1
    lens = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(n)]
    total = sum(lens) or 1.0
    rmax = float(np.max(rfun(np.linspace(0, 1, 64))))
    out = np.full(cv.x.shape, margin, np.float32)
    w = _win_for(cv, pts, rmax + margin)
    if w.empty:
        return out
    d = np.full(w.x.shape, np.inf, np.float32)
    acc = 0.0
    for i in range(n):
        a, b = pts[i], pts[i + 1]
        px, py = w.x - a[0], w.y - a[1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        h = np.clip((px * vx + py * vy) / max(vx * vx + vy * vy, 1e-9), 0.0, 1.0)
        t = (acc + h * lens[i]) / total
        d = np.minimum(d, np.hypot(px - vx * h, py - vy * h) - rfun(t))
        acc += lens[i]
    out[w.j0:w.j1, w.i0:w.i1] = np.minimum(d, margin)
    return out


def flame_leaf(cv: Cv, pts, width: float, bulge: float = 0.35, tip: float = 0.08, base: float = 0.3,
               margin: float = 8.0) -> np.ndarray:
    """A curved flame-leaf along a path: rounded base, widest at `bulge`, drawn to a fine point."""
    def rf(t):
        up = np.clip(t / bulge, 0, 1)
        dn = np.clip((1 - t) / (1 - bulge), 0, 1)
        return width * (base + (1 - base) * np.sin(up * np.pi / 2)) * (dn ** 0.85) + tip * (1 - t) * 0
    return sd_stroke(cv, pts, rf, margin)


def sd_mask(cv: Cv, inside: np.ndarray) -> np.ndarray:
    """SDF (logical px) from a boolean sample mask via exact Euclidean distance transforms."""
    d_in = ndimage.distance_transform_edt(inside)
    d_out = ndimage.distance_transform_edt(~inside)
    sdf = np.where(inside, -(d_in - 0.5), d_out - 0.5)
    return (sdf / cv.k).astype(np.float32)


def raster(cv: Cv, draw_fn) -> np.ndarray:
    """Rasterise with PIL at sample resolution. draw_fn(ImageDraw, k) draws in logical px * k."""
    m = Image.new("L", (cv.W, cv.H), 0)
    draw_fn(ImageDraw.Draw(m), cv.k)
    return np.asarray(m) > 127


def u_union(*sdfs):
    out = sdfs[0]
    for s in sdfs[1:]:
        out = np.minimum(out, s)
    return out


def u_sub(a, b):
    return np.maximum(a, -b)


def u_isect(a, b):
    return np.maximum(a, b)


def band(sdf, a, b):
    """SDF of the band between insets a and b (a < b) of a shape."""
    return np.maximum(sdf + a, -sdf - b)


def rrect_pts(x0, y0, x1, y1, r, n=10):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def chamfer_pts(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
            (x0, y0 + c)]


def bezier(p0, p1, p2, p3, n=48):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def sd_polyline(cv: Cv, pts, r0: float, r1: float | None = None, ease: float = 1.0) -> np.ndarray:
    """SDF of a tapered stroke along a polyline (radius r0 at the start -> r1 at the end)."""
    r1 = r0 if r1 is None else r1
    d = np.full(cv.x.shape, 8.0, np.float32)
    n = len(pts) - 1
    lens = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(n)]
    total = sum(lens) or 1.0
    acc = 0.0
    # restrict work to a bounding box around the stroke
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    rm = max(r0, r1) + 2
    bx0, bx1 = max(0, int((min(xs) - rm) * cv.k)), min(cv.W, int((max(xs) + rm) * cv.k) + 1)
    by0, by1 = max(0, int((min(ys) - rm) * cv.k)), min(cv.H, int((max(ys) + rm) * cv.k) + 1)
    if bx1 <= bx0 or by1 <= by0:
        return d
    X, Y = cv.x[by0:by1, bx0:bx1], cv.y[by0:by1, bx0:bx1]
    sub = np.full(X.shape, np.inf, np.float32)
    for i in range(n):
        a, b = pts[i], pts[i + 1]
        px, py = X - a[0], Y - a[1]
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = max(vx * vx + vy * vy, 1e-9)
        h = np.clip((px * vx + py * vy) / L2, 0.0, 1.0)
        t = ((acc + h * lens[i]) / total) ** ease
        r = r0 + (r1 - r0) * t
        sub = np.minimum(sub, np.hypot(px - vx * h, py - vy * h) - r)
        acc += lens[i]
    d[by0:by1, bx0:bx1] = np.minimum(sub, 8.0)
    return d


def sd_leaf(cv: Cv, base, tip, width, n=40):
    """A pointed leaf / flame tongue between base and tip (a lens of two mirrored beziers)."""
    bx, by = base
    tx, ty = tip
    dx, dy = tx - bx, ty - by
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    c1 = (bx + dx * 0.35 + nx * width, by + dy * 0.35 + ny * width)
    c2 = (bx + dx * 0.75 + nx * width * 0.5, by + dy * 0.75 + ny * width * 0.5)
    c3 = (bx + dx * 0.35 - nx * width, by + dy * 0.35 - ny * width)
    c4 = (bx + dx * 0.75 - nx * width * 0.5, by + dy * 0.75 - ny * width * 0.5)
    pts = bezier(base, c1, c2, tip, n) + bezier(tip, c4, c3, base, n)[1:-1]
    return sd_poly(cv, pts)


def spiral_pts(cx, cy, r0, r1, turns, a0, n=80, direction=1):
    out = []
    for i in range(n + 1):
        t = i / n
        a = a0 + direction * t * turns * 2 * math.pi
        r = r0 + (r1 - r0) * t
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


# ───────────────────────────── noise ─────────────────────────────
def noise2(cv: Cv, scale: float, seed: int) -> np.ndarray:
    """Smooth 2D noise, roughly unit amplitude; scale in logical px."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((cv.H, cv.W)).astype(np.float32)
    n = ndimage.gaussian_filter(n, scale * cv.k, mode="wrap")
    return n / (np.abs(n).max() + 1e-6)


def noise1(length: int, scale_px: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = rng.standard_normal(length).astype(np.float32)
    n = ndimage.gaussian_filter1d(n, max(scale_px, 0.5), mode="wrap")
    return n / (np.abs(n).max() + 1e-6)


def noise_of(cv: Cv, field: np.ndarray, scale: float, seed: int, lo: float = -20.0, hi: float = 60.0) -> np.ndarray:
    """1D noise sampled along a scalar field (e.g. an SDF): streaks that follow the shape.

    Because it depends only on the field, it stays invariant along straight edges, so it is safe
    inside the stretched segments of a 9-slice."""
    res = 64  # samples per logical px along the field
    n = noise1(int((hi - lo) * res) + 2, scale * res, seed)
    idx = np.clip(((field - lo) * res).astype(np.int64), 0, len(n) - 1)
    return n[idx]


# ───────────────────────────── bevel heights ─────────────────────────────
def h_bead(sdf, a, b, groove: float = 0.0, groove_at: float = 0.68, groove_w: float = 0.07):
    """Height across a band [a, b] of insets: a rounded rod (0 at both edges, 1 in the middle).
    An optional engraved groove runs along it at `groove_at` of the width."""
    p = np.clip((-sdf - a) / max(b - a, 1e-6), 0.0, 1.0)
    h = np.clip(np.sin(np.pi * p), 0.0, 1.0) ** 0.8
    if groove:
        h = h - groove * np.exp(-((p - groove_at) / groove_w) ** 2)
    return h


def h_dome(sdf, bevel: float, profile: str = "round"):
    """Height of a solid shape rising over `bevel` logical px from its edge."""
    p = np.clip(-sdf / max(bevel, 1e-6), 0.0, 1.0)
    if profile == "round":
        return np.sin(p * np.pi / 2)
    if profile == "ridge":   # a sharp crest along the medial axis (blades, rays)
        return p
    if profile == "flat":
        return smoothstep(0.0, 1.0, p)
    return p


def blur(cv: Cv, a: np.ndarray, r: float) -> np.ndarray:
    return ndimage.gaussian_filter(a, r * cv.k) if r > 0 else a


# ───────────────────────────── shading ─────────────────────────────
def shade(cv: Cv, h: np.ndarray, amp: float, stops=GOLD, base=0.16, gain=0.72, spec=0.5, shin=24.0, bounce=0.10,
          vgrad=0.06, light=LIGHT, streak: np.ndarray | None = None, streak_amt: float = 0.0,
          hammer: np.ndarray | None = None, hammer_amt: float = 0.0, y0: float | None = None,
          y1: float | None = None) -> np.ndarray:
    """Light a height field as polished metal and map it through a ramp. Returns (H, W, 3).

    amp: bevel height in logical px (steepness). The top-left key light gives the bright upper-left
    bevels; a faint warm bounce from the lower right keeps the far bevels from going dead; `vgrad`
    brightens the top of the piece (the §3.1 metal ramp reads top to bottom)."""
    gy, gx = np.gradient(h)
    gx = gx * cv.k
    gy = gy * cv.k
    nx, ny = -amp * gx, -amp * gy
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
    nx, ny, nz = nx * inv, ny * inv, inv
    L = np.array(light, np.float32)
    L /= np.linalg.norm(L)
    diff = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0.0, 1.0)
    Hv = L + np.array([0, 0, 1.0], np.float32)
    Hv /= np.linalg.norm(Hv)
    sp = np.clip(nx * Hv[0] + ny * Hv[1] + nz * Hv[2], 0.0, 1.0) ** shin
    B = np.array([0.45, 0.7, 0.55], np.float32)
    B /= np.linalg.norm(B)
    bo = np.clip(nx * B[0] + ny * B[1] + nz * B[2], 0.0, 1.0) ** 2
    t = base + gain * diff + spec * sp + bounce * bo
    if vgrad:
        ya = 0.0 if y0 is None else y0
        yb = cv.lh if y1 is None else y1
        t = t + vgrad * (0.5 - np.clip((cv.y - ya) / max(yb - ya, 1e-6), 0, 1))
    if streak is not None and streak_amt:
        t = t + streak_amt * streak
    if hammer is not None and hammer_amt:
        t = t + hammer_amt * hammer
    return ramp(np.clip(t, 0.0, 1.0), stops)


def edge_line(col: np.ndarray, sdf_shape: np.ndarray, width: float, color="gold_sh", amount: float = 0.85):
    """Darken the inside rim of a metal shape: the §8.3 `gold_sh` edge line."""
    w = np.clip(1.0 - (-sdf_shape) / max(width, 1e-6), 0.0, 1.0)[..., None] * amount
    return col * (1.0 - w) + rgb(color)[None, None, :] * w


def metal(cv: Cv, sdf_shape: np.ndarray, h: np.ndarray, amp: float, stops=GOLD, edge: float = 0.7,
          edge_amt: float = 0.85, alpha: float = 1.0, **kw):
    """Shade and composite a metal shape in one call."""
    col = shade(cv, h, amp, stops=stops, **kw)
    if edge:
        col = edge_line(col, sdf_shape, edge, amount=edge_amt)
    cv.over(col, cv.cov(sdf_shape), alpha)
    return col


def lacquer_col(cv: Cv, top, bot, y0=0.0, y1=None, sdf=None, edge_dark=0.45, edge_w=None, streak=5.5,
                grain=2.0, sheen=0.06, sheen_frac=0.22, seed=3, slice_safe=False, tint=None, tint_amt=0.0):
    """The §8.3 lacquer: vertical gradient, inner edge darkening, brushed streaks, grain and a warm
    top sheen. Streak/grain amplitudes are in 8-bit steps like the recipe. With slice_safe the
    streaks depend on y only and there is no grain, so 9-slice stretching cannot smear them."""
    y1 = cv.lh if y1 is None else y1
    ty = np.clip((cv.y - y0) / max(y1 - y0, 1e-6), 0.0, 1.0)[..., None]
    col = rgb(top)[None, None, :] * (1 - ty) + rgb(bot)[None, None, :] * ty
    if tint is not None:
        col = col * (1 - tint_amt) + rgb(tint)[None, None, :] * tint_amt
    if sdf is not None and edge_dark:
        ew = edge_w if edge_w is not None else min(cv.lw, cv.lh) * 0.35
        e = np.clip(-sdf / ew, 0.0, 1.0) ** 0.6
        col = col * ((1 - edge_dark) + edge_dark * e)[..., None]
    if streak:
        if slice_safe:
            n = noise1(cv.H, 0.6 * cv.k, seed)[:, None]
            col = col + (n * streak / 255.0)[..., None] * np.ones((1, cv.W, 1), np.float32)
        else:
            rng = np.random.default_rng(seed)
            s = ndimage.gaussian_filter(rng.standard_normal((cv.H, cv.W)).astype(np.float32),
                                        (0.6 * cv.k, 18 * cv.k), mode="wrap")
            s /= (np.abs(s).max() + 1e-6)
            col = col + (s * streak / 255.0)[..., None]
    if grain and not slice_safe:
        rng = np.random.default_rng(seed + 101)
        g = ndimage.gaussian_filter(rng.standard_normal((cv.H, cv.W)).astype(np.float32), 0.5 * cv.ss)
        g /= (np.abs(g).max() + 1e-6)
        col = col + (g * grain / 255.0)[..., None]
    if sheen:
        tsh = np.clip((cv.y - y0) / max(y1 - y0, 1e-6), 0, 1)
        sh = np.clip(1 - tsh / sheen_frac, 0, 1) ** 2 * sheen
        col = col + sh[..., None] * np.array([1.0, 0.78, 0.55], np.float32)[None, None, :]
    return np.clip(col, 0, 1)


def lattice_lines(cv: Cv, step: float = 22.0, width: float = 0.55) -> np.ndarray:
    """The tooled lozenge lattice (§8.3): two diagonal line families, `step` logical px apart."""
    a = np.abs(((cv.x + cv.y) % step) - step / 2)
    b = np.abs(((cv.x - cv.y) % step) - step / 2)
    return np.clip(width - np.minimum(a, b), 0, width) / width


def inner_shadow(cv: Cv, sdf_edge: np.ndarray, width: float, alpha: float, power: float = 1.6) -> np.ndarray:
    """Alpha of a soft shadow falling inward from an edge (sdf_edge < 0 inside the lit area)."""
    t = np.clip(-sdf_edge / max(width, 1e-6), 0.0, 1.0)
    return (1.0 - t) ** power * alpha * (sdf_edge <= 0.5 / cv.k)


def drop_shadow_px(cv: Cv, cov: np.ndarray, dx: float, dy: float, blur_r: float, alpha: float, color="ink") -> np.ndarray:
    """A premultiplied shadow layer of a coverage mask (for contact shadows baked into ornaments)."""
    sh = ndimage.shift(cov, (dy * cv.k, dx * cv.k), order=1, mode="constant")
    sh = ndimage.gaussian_filter(sh, blur_r * cv.k) * alpha
    out = np.zeros((cv.H, cv.W, 4), np.float32)
    out[..., :3] = rgb(color)[None, None, :] * sh[..., None]
    out[..., 3] = sh
    return out


def glow_px(cv: Cv, cov: np.ndarray, blur_r: float, alpha: float, color="#FFFFFF", spread: float = 0.0) -> np.ndarray:
    c = cov
    if spread:
        c = np.clip(ndimage.maximum_filter(c, size=int(spread * cv.k) * 2 + 1), 0, 1)
    g = ndimage.gaussian_filter(c, blur_r * cv.k) * alpha
    out = np.zeros((cv.H, cv.W, 4), np.float32)
    out[..., :3] = rgb(color)[None, None, :] * g[..., None]
    out[..., 3] = g
    return out


# ───────────────────────────── gems (chrome gems, not rarity gems) ─────────────────────────────
def gem_lozenge(cv: Cv, cx, cy, rx, ry, color, setting: bool = True, setting_w: float | None = None,
                glint: float = 0.9, dim: float = 1.0, stops=GOLD):
    """A faceted lozenge gem in a thin gilt setting: table + four crown facets lit from the top-left."""
    sw = setting_w if setting_w is not None else max(0.5, min(rx, ry) * 0.22)
    outer = [(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)]
    sd_o = sd_poly(cv, outer, exact=True)
    if setting:
        h = h_bead(sd_o, 0.0, sw)
        metal(cv, sd_o, h, amp=sw * 0.8, stops=stops, edge=min(0.5, sw * 0.4), vgrad=0.0)
    irx, iry = rx - sw * 1.3, ry - sw * 1.3
    base = rgb(color) * dim
    tx, ty = irx * 0.42, iry * 0.42
    top, right, bottom, left = (cx, cy - iry), (cx + irx, cy), (cx, cy + iry), (cx - irx, cy)
    tab = [(cx, cy - ty), (cx + tx, cy), (cx, cy + ty), (cx - tx, cy)]
    facets = [([left, top, tab[0], tab[3]], 1.30), ([top, right, tab[1], tab[0]], 0.95),
              ([right, bottom, tab[2], tab[1]], 0.52), ([bottom, left, tab[3], tab[2]], 0.74), (tab, 1.08)]
    for poly, k in facets:
        c = np.clip(base * k + (0.12 if k > 1.2 else 0.0), 0, 1)
        cv.over(c, cv.cov(sd_poly(cv, poly, exact=True)))
    if glint:
        gx, gy = cx - irx * 0.28, cy - iry * 0.34
        g = np.exp(-(((cv.x - gx) / (irx * 0.16 + 0.2)) ** 2 + ((cv.y - gy) / (iry * 0.16 + 0.2)) ** 2))
        cv.over(np.array([1.0, 1.0, 0.97], np.float32), g * glint * cv.cov(sd_o))
