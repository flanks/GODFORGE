#!/usr/bin/env python3
"""GODFORGE icon generator (UI lane I).

Draws every icon listed in docs/art/UI_STYLE.md section 9 as an original vector silhouette and
writes the 128x128 RGBA masters to assets/ui/icons/<group>/<name>.png, the manifest
assets/ui/icons/icons.json (key -> file, category, meaning) and a labelled contact sheet
docs/art/ui_mockups/icon_sheet.png (every icon at 64, 48, 32 and 24 px on lacquer).

House style (UI_STYLE section 9.1):
  * silhouette first, one idea per icon, at most a couple of interior cuts;
  * 2-3 values: an ivory light (#FFF7E6) at the top of the glyph grading into the category tint,
    which is mixed 35 % toward #1A0F08 at the bottom; optional shade regions; ink details;
  * an ink outline of about 2.3 % of the cell (#0A0706 at 0.95);
  * the glyph sits inside an 8 % pad; the frame (slot, pin, medallion) is drawn by the UI;
  * rarity is never baked into an icon (the rarity gems are the one exception) and player colours
    never appear in one.

Every shape here is built from primitives in this file (polygons, circles, Bezier strokes). Nothing
is traced, sampled or copied from any reference.

Run (Python 3 + Pillow + numpy + scipy):
    python tools/ui/make_icons.py                 # everything
    python tools/ui/make_icons.py --only kits     # one or more groups (comma separated)
    python tools/ui/make_icons.py --review DIR    # also write per-group review sheets at 128 px
    python tools/ui/make_icons.py --rust-table crates/gf_client/src/icon_table.rs
The output is deterministic. The generator fails when a content key (part, boon, chassis,
character, god, kit) resolves to no icon.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT_DIR = os.path.join(ROOT, "assets", "ui", "icons")
SHEET_PATH = os.path.join(ROOT, "docs", "art", "ui_mockups", "icon_sheet.png")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
SHEETS = os.path.join(ROOT, "content", "sheets")
GENERATED = os.path.join(ROOT, "assets", "content", "generated")
KITS_RON = os.path.join(ROOT, "assets", "content", "kits.ron")

# ───────────────────────────── tokens ─────────────────────────────
MASTER = 128          # master icon size (px)
SS = 6                # supersampling factor of the master
WORK = MASTER * SS    # working resolution of the finished master
PAD = 0.08            # glyph pad inside the cell
OUTLINE = 0.023       # ink outline, fraction of the cell

IVORY = "#FFF7E6"
DARK = "#1A0F08"
INK = "#0A0706"

T_KIT = "#D9B56C"       # kit, actions, chrome
T_BONE = "#E6CFA0"      # POIs, parts, currencies, chassis
T_PORTRAIT = "#B08A52"  # portrait busts
T_WARLORD = "#FF7A5A"   # the Warlord glyph everywhere
T_STEEL = "#C9D0D6"

ELEMENT = {"kinetic": "#F4E3C1", "flame": "#FF7A1A", "storm": "#3FD8FF", "void": "#A45CFF",
           "plague": "#86E03A", "radiant": "#FFE27A"}
RARITY = {"common": "#CFC6B4", "rare": "#4FA3FF", "epic": "#B865FF", "godforged": "#FFB82E"}
STATUS_ELEMENT = {"burn": "flame", "shock": "storm", "curse": "void", "bleed": "kinetic"}
# gods: filled from content/sheets/gods.csv (colour, secondary)
GODS: dict[str, tuple[str, str]] = {}
RED_GODS = {"pyra", "umbra_rex"}  # red primaries never sit on a white-ish glyph: use the secondary


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> str:
    ca, cb = rgb(a), rgb(b)
    return "#%02X%02X%02X" % tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))


def ramp(t: np.ndarray, stops: list[tuple[float, str]]) -> np.ndarray:
    xs = np.array([s[0] for s in stops], np.float32)
    cs = np.array([rgb(s[1]) for s in stops], np.float32)
    out = np.empty(t.shape + (3,), np.float32)
    for i in range(3):
        out[..., i] = np.interp(t, xs, cs[:, i])
    return out


# ───────────────────────────── geometry ─────────────────────────────
def cubic(p0, p1, p2, p3, n=40):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def quad(p0, p1, p2, n=30):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return out


def arcpts(cx, cy, rx, ry, a0, a1, n=None):
    """Points on an ellipse arc; angles in degrees, 0 = +x, 90 = down (screen space)."""
    if n is None:
        n = max(8, int(abs(a1 - a0) / 4))
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def mirror_x(pts, cx=0.5):
    return [(2 * cx - x, y) for x, y in pts]


def sym(half, cx=0.5):
    """A closed polygon from its left half (top to bottom); mirrored about x = cx."""
    return list(half) + mirror_x(list(reversed(half)), cx)


class Path:
    """Tiny path builder: M / L / C / Q / arc, returns a point list."""

    def __init__(self, x, y):
        self.p = [(x, y)]

    def L(self, x, y):
        self.p.append((x, y))
        return self

    def C(self, x1, y1, x2, y2, x, y, n=30):
        self.p += cubic(self.p[-1], (x1, y1), (x2, y2), (x, y), n)[1:]
        return self

    def Q(self, x1, y1, x, y, n=24):
        self.p += quad(self.p[-1], (x1, y1), (x, y), n)[1:]
        return self

    def A(self, cx, cy, rx, ry, a0, a1, n=None):
        self.p += arcpts(cx, cy, rx, ry, a0, a1, n)
        return self

    def pts(self):
        return self.p


def stroke_poly(pts, w0, w1=None, ease=1.0):
    """Outline polygon of a polyline with a width tapering from w0 to w1 (butt ends)."""
    if w1 is None:
        w1 = w0
    n = len(pts)
    if n < 2:
        return []
    # cumulative length for the taper
    d = [0.0]
    for i in range(1, n):
        d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    total = d[-1] or 1.0
    left, right = [], []
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
        elif i == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln
        t = (d[i] / total) ** ease
        w = (w0 + (w1 - w0) * t) / 2
        left.append((pts[i][0] + nx * w, pts[i][1] + ny * w))
        right.append((pts[i][0] - nx * w, pts[i][1] - ny * w))
    return left + right[::-1]


# ───────────────────────────── canvas ─────────────────────────────
class Canvas:
    """Unit-space drawing on supersampled masks.

    Layers: `m` the silhouette (op add / cut), `s` shade regions (op shade / unshade), `k` ink
    details (op ink). The unit square maps to [MARG, MARG + U] px; anything outside survives
    until the auto-fit crops to the glyph bounds.
    """

    U = 600
    MARG = 200

    def __init__(self):
        size = self.U + 2 * self.MARG
        self.size = size
        self.m = Image.new("L", (size, size), 0)
        self.s = Image.new("L", (size, size), 0)
        self.k = Image.new("L", (size, size), 0)
        self.dm = ImageDraw.Draw(self.m)
        self.ds = ImageDraw.Draw(self.s)
        self.dk = ImageDraw.Draw(self.k)
        self._op = "add"
        self._tf = [(1.0, 0.0, 0.0, 0.0, 1.0, 0.0)]

    # transforms ---------------------------------------------------------
    @contextmanager
    def at(self, x=0.0, y=0.0, s=1.0, r=0.0, sx=None, sy=None):
        """Local frame: translate to (x, y), rotate r degrees, scale s (or sx / sy)."""
        sx = s if sx is None else sx
        sy = s if sy is None else sy
        a = math.radians(r)
        ca, sa = math.cos(a), math.sin(a)
        loc = (ca * sx, -sa * sy, x, sa * sx, ca * sy, y)
        p = self._tf[-1]
        comb = (p[0] * loc[0] + p[1] * loc[3], p[0] * loc[1] + p[1] * loc[4], p[0] * loc[2] + p[1] * loc[5] + p[2],
                p[3] * loc[0] + p[4] * loc[3], p[3] * loc[1] + p[4] * loc[4], p[3] * loc[2] + p[4] * loc[5] + p[5])
        self._tf.append(comb)
        try:
            yield self
        finally:
            self._tf.pop()

    @contextmanager
    def place(self, cx, cy, sz, r=0.0, sx=None, sy=None):
        """Draw a unit-square atom centred at (cx, cy) with side sz, rotated r degrees."""
        with self.at(cx, cy, s=sz, r=r, sx=None if sx is None else sz * sx, sy=None if sy is None else sz * sy):
            with self.at(-0.5, -0.5):
                yield self

    @contextmanager
    def box(self, x0, y0, x1, y1):
        """Map the unit square onto the rectangle (x0, y0)-(x1, y1)."""
        with self.at(x0, y0, sx=x1 - x0, sy=y1 - y0):
            yield self

    @contextmanager
    def op(self, name):
        old = self._op
        self._op = name
        try:
            yield self
        finally:
            self._op = old

    def P(self, x, y):
        t = self._tf[-1]
        ux = t[0] * x + t[1] * y + t[2]
        uy = t[3] * x + t[4] * y + t[5]
        return (self.MARG + ux * self.U, self.MARG + uy * self.U)

    def scale(self):
        t = self._tf[-1]
        return math.sqrt(abs(t[0] * t[4] - t[1] * t[3]))

    # raw fill -------------------------------------------------------------
    def _fill(self, px):
        if len(px) < 3:
            return
        op = self._op
        if op == "add":
            self.dm.polygon(px, fill=255)
        elif op == "cut":
            self.dm.polygon(px, fill=0)
            self.ds.polygon(px, fill=0)
            self.dk.polygon(px, fill=0)
        elif op == "shade":
            self.ds.polygon(px, fill=255)
        elif op == "unshade":
            self.ds.polygon(px, fill=0)
        elif op == "ink":
            self.dk.polygon(px, fill=255)
        elif op == "unink":
            self.dk.polygon(px, fill=0)
        else:
            raise ValueError(op)

    # primitives -----------------------------------------------------------
    def poly(self, pts):
        self._fill([self.P(x, y) for x, y in pts])

    def ellipse(self, cx, cy, rx, ry, r=0.0, n=96):
        pts = [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]
        if r:
            pts = rot(pts, cx, cy, r)
        self.poly(pts)

    def circle(self, cx, cy, r, n=96):
        self.ellipse(cx, cy, r, r, n=n)

    def ring(self, cx, cy, r, w, n=96):
        """A ring of outer radius r and width w (the hole is left untouched)."""
        ri = r - w
        for i in range(n):
            a0 = 2 * math.pi * i / n
            a1 = 2 * math.pi * (i + 1) / n
            self.poly([(cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1)),
                       (cx + ri * math.cos(a1), cy + ri * math.sin(a1)), (cx + ri * math.cos(a0), cy + ri * math.sin(a0))])

    def rect(self, x0, y0, x1, y1, r=0.0):
        if r <= 0:
            self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            return
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            pts += arcpts(cx, cy, r, r, a0, a0 + 90, 8)
        self.poly(pts)

    def line(self, pts, w, cap=True):
        """Polyline with round joins (and round caps unless cap=False)."""
        for a, b in zip(pts[:-1], pts[1:]):
            self.poly(stroke_poly([a, b], w))
        joints = pts[1:-1] if not cap else pts
        for p in joints:
            self.circle(p[0], p[1], w / 2, n=32)

    def taper(self, pts, w0, w1=None, ease=1.0, cap0=False, cap1=False):
        self.poly(stroke_poly(pts, w0, w1, ease))
        if cap0:
            self.circle(pts[0][0], pts[0][1], w0 / 2, n=32)
        if cap1:
            self.circle(pts[-1][0], pts[-1][1], (w1 if w1 is not None else w0) / 2, n=32)

    def bez(self, p0, p1, p2, p3, w0, w1=None, ease=1.0, cap0=False, cap1=False, n=40):
        self.taper(cubic(p0, p1, p2, p3, n), w0, w1, ease, cap0, cap1)

    def arc(self, cx, cy, r, a0, a1, w, w1=None, ease=1.0, cap=False, ry=None):
        pts = arcpts(cx, cy, r, r if ry is None else ry, a0, a1)
        self.taper(pts, w, w1, ease, cap, cap)

    def knock(self, pts, w=0.05):
        """Cut a polygon grown by w (a clean gap), so a shape drawn next sits apart from what is under it."""
        with self.op("cut"):
            self.poly(pts)
            self.line(list(pts) + [pts[0]], w * 2)

    def star(self, cx, cy, r0, r1, n, rot_deg=-90.0):
        pts = []
        for i in range(n * 2):
            r = r0 if i % 2 == 0 else r1
            a = math.radians(rot_deg + i * 180.0 / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.poly(pts)

    def ngon(self, cx, cy, r, n, rot_deg=-90.0):
        self.poly([(cx + r * math.cos(math.radians(rot_deg + i * 360.0 / n)),
                    cy + r * math.sin(math.radians(rot_deg + i * 360.0 / n))) for i in range(n)])


# ───────────────────────────── registry ─────────────────────────────
@dataclass
class IconDef:
    group: str
    name: str
    draw: Callable | None
    tint: str
    meaning: str
    kind: str = "glyph"          # glyph | gem | portrait | boon
    fit: float = 1.0             # optical scale inside the pad box
    autofit: bool = True
    light: str = IVORY
    extra: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.group}/{self.name}"


ICONS: dict[str, IconDef] = {}


def reg(group, name, draw, tint, meaning, **kw):
    d = IconDef(group, name, draw, tint, meaning, **kw)
    if d.key in ICONS:
        raise SystemExit(f"duplicate icon key {d.key}")
    ICONS[d.key] = d
    return d


def icon(group, name, tint, meaning, **kw):
    def deco(fn):
        reg(group, name, fn, tint, meaning, **kw)
        return fn
    return deco


# ───────────────────────────── rendering ─────────────────────────────
def canvas_of(fn, *args) -> Canvas:
    c = Canvas()
    fn(c, *args)
    return c


def fit_masks(c: Canvas, fit: float = 1.0, autofit: bool = True, bold: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Crop the canvas to its glyph, scale it into the pad box and centre it on a WORK canvas."""
    m = np.asarray(c.m, np.float32) / 255.0
    s = np.asarray(c.s, np.float32) / 255.0
    k = np.asarray(c.k, np.float32) / 255.0
    box_px = WORK * (1 - 2 * PAD) * fit
    if autofit:
        ys, xs = np.nonzero(m > 0.02)
        if len(xs) == 0:
            raise SystemExit("empty glyph")
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        scale = box_px / max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        scale = box_px / Canvas.U
        cx = cy = Canvas.MARG + Canvas.U / 2
    out = []
    for arr in (m, s, k):
        # affine resample: output pixel (u, v) -> input (cx + (u - WORK/2) / scale, ...)
        inv = 1.0 / scale
        o = ndimage.affine_transform(arr, [inv, inv], offset=[cy - (WORK / 2) * inv, cx - (WORK / 2) * inv],
                                     output_shape=(WORK, WORK), order=1, mode="constant", cval=0.0)
        out.append(np.clip(o, 0, 1))
    if bold > 0:
        # embolden thin silhouettes (weapons drawn with fine strokes) so they hold at small sizes
        dist = ndimage.distance_transform_edt(out[0] < 0.5).astype(np.float32)
        out[0] = np.maximum(out[0], np.clip(bold * WORK - dist + 0.5, 0, 1))
    return out[0], out[1], out[2]


def enamel(m: np.ndarray, s: np.ndarray, k: np.ndarray, tint: str, light: str = IVORY,
           outline: float = OUTLINE, bevel: bool = True) -> np.ndarray:
    """House style: ivory -> tint ramp, shade regions, ink details, soft bevel, ink outline.
    Returns a premultiplied float RGBA array at WORK resolution (0..1)."""
    a = m
    ys = np.nonzero(a.max(axis=1) > 0.5)[0]
    y0, y1 = (ys.min(), ys.max()) if len(ys) else (0, WORK - 1)
    t = np.clip((np.arange(WORK, dtype=np.float32) - y0) / max(1.0, (y1 - y0)), 0, 1)[:, None] * np.ones((1, WORK), np.float32)
    lo = mix(tint, DARK, 0.35)
    base = ramp(t, [(0.0, light), (0.45, mix(light, tint, 0.55)), (1.0, lo)]) / 255.0
    shadec = ramp(t, [(0.0, mix(tint, DARK, 0.45)), (1.0, mix(tint, DARK, 0.72))]) / 255.0
    sh = np.clip(s, 0, 1)[..., None]
    col = base * (1 - sh) + shadec * sh
    if bevel:
        inside = a > 0.5
        d = ndimage.distance_transform_edt(inside).astype(np.float32)
        bw = WORK * 0.03
        h = np.sin(np.clip(d / bw, 0, 1) * np.pi / 2)
        h = ndimage.gaussian_filter(h, SS * 0.6)
        gy, gx = np.gradient(h)
        kk = bw * 0.9
        n = np.dstack([-gx * kk, -gy * kk, np.ones_like(h)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        L = np.array([-0.45, -0.8, 0.9], np.float32)
        L /= np.linalg.norm(L)
        diff = (n * L).sum(2)
        flat = L[2]
        lift = np.clip((diff - flat) * 1.6, -0.35, 0.3)[..., None]
        col = np.where(lift > 0, col + (1 - col) * lift, col * (1 + lift))
    inkc = np.array(rgb(INK), np.float32) / 255.0
    kk_ = np.clip(k, 0, 1)[..., None]
    col = col * (1 - kk_) + inkc * kk_
    # outline
    ow = outline * WORK
    if ow > 0:
        dist = ndimage.distance_transform_edt(a < 0.5).astype(np.float32)
        ol = np.clip(ow - dist + 0.5, 0, 1) * 0.95
    else:
        ol = np.zeros_like(a)
    alpha = a + ol * (1 - a)
    prem = col * a[..., None] + inkc * (ol * (1 - a))[..., None]
    return np.dstack([prem, alpha])


def downsample(prem: np.ndarray, factor: int) -> np.ndarray:
    h, w, _ = prem.shape
    return prem.reshape(h // factor, factor, w // factor, factor, 4).mean(axis=(1, 3))


def to_image(prem: np.ndarray) -> Image.Image:
    a = prem[..., 3:4]
    rgbv = np.where(a > 1e-6, prem[..., :3] / np.maximum(a, 1e-6), 0)
    arr = np.dstack([np.clip(rgbv, 0, 1), np.clip(a, 0, 1)])
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGBA")


def over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Premultiplied src over dst."""
    return src + dst * (1 - src[..., 3:4])


def render_glyph_prem(d: IconDef) -> np.ndarray:
    c = canvas_of(d.draw)
    m, s, k = fit_masks(c, d.fit, d.autofit, d.extra.get("bold", 0.0))
    return enamel(m, s, k, d.tint, d.light, bevel=d.extra.get("bevel", True))


# ───────────────────────────── atoms ─────────────────────────────
# Each atom draws into the unit square of the current frame; position it with c.place(cx, cy, size).

def polar(cx, cy, r, deg):
    return (cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg)))


def teardrop_pts(cx, by, r, h, lean=0.0):
    """Round base of radius r resting on y = by, a pointed tip h above it, leaning by `lean`."""
    tip = (cx + lean, by - h)
    ccy = by - r
    p = Path(*tip)
    p.C(tip[0] - r * 0.1, by - h * 0.55, cx - r * 1.08, ccy - r * 0.9, cx - r, ccy)
    p.A(cx, ccy, r, r, 180, 0)
    p.C(cx + r * 1.08, ccy - r * 0.9, tip[0] + r * 0.1, by - h * 0.55, tip[0], tip[1])
    return p.pts()


def gear_pts(cx, cy, ro, ri, n, rot_deg=0.0, top=0.34, rise=0.14):
    pts = []
    w = 360.0 / n
    for i in range(n):
        a = rot_deg + i * w
        pts += [polar(cx, cy, ri, a), polar(cx, cy, ro, a + w * rise), polar(cx, cy, ro, a + w * (rise + top)),
                polar(cx, cy, ri, a + w * (2 * rise + top))]
    return pts


def spiral_pts(cx, cy, r0, r1, turns, a0=0.0, n=160, cw=True):
    out = []
    for i in range(n + 1):
        t = i / n
        a = math.radians(a0 + (360 * turns * t) * (1 if cw else -1))
        r = r0 + (r1 - r0) * t
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


BOLT = [(0.60, 0.0), (0.16, 0.57), (0.46, 0.57), (0.33, 1.0), (0.86, 0.40), (0.55, 0.40), (0.73, 0.0)]


def g_bolt(c):
    c.poly(BOLT)


def g_flame(c, core=True, lean=0.05):
    c.poly(teardrop_pts(0.5, 0.98, 0.31, 0.98, lean))
    c.poly(teardrop_pts(0.27, 0.93, 0.17, 0.58, -0.13))
    c.poly(teardrop_pts(0.73, 0.94, 0.16, 0.52, 0.12))
    if core:
        with c.op("cut"):
            c.poly(teardrop_pts(0.52, 0.88, 0.12, 0.40, -0.04))


def g_flame_simple(c, lean=0.04, core=False):
    c.poly(teardrop_pts(0.5, 1.0, 0.36, 1.0, lean))
    if core:
        with c.op("cut"):
            c.poly(teardrop_pts(0.52, 0.9, 0.14, 0.42, -0.03))


def g_drop(c, hole=False):
    c.poly(teardrop_pts(0.5, 1.0, 0.36, 1.0, 0.0))
    if hole:
        with c.op("cut"):
            c.ellipse(0.4, 0.66, 0.07, 0.1, r=-20)


def g_skull(c, teeth=True):
    c.circle(0.5, 0.42, 0.38)
    c.rect(0.27, 0.5, 0.73, 0.94, r=0.08)
    with c.op("cut"):
        c.ellipse(0.35, 0.49, 0.11, 0.125)
        c.ellipse(0.65, 0.49, 0.11, 0.125)
        c.poly([(0.5, 0.62), (0.435, 0.74), (0.565, 0.74)])
        if teeth:
            for x in (0.405, 0.5, 0.595):
                c.rect(x - 0.02, 0.83, x + 0.02, 0.95)


def g_heart(c):
    c.poly(Path(0.5, 0.95).C(0.2, 0.74, 0.02, 0.54, 0.04, 0.32).C(0.06, 0.1, 0.38, 0.02, 0.5, 0.24)
           .C(0.62, 0.02, 0.94, 0.1, 0.96, 0.32).C(0.98, 0.54, 0.8, 0.74, 0.5, 0.95).pts())


ANVIL = (Path(0.27, 0.2).L(0.98, 0.2).L(0.98, 0.33).L(0.8, 0.4).Q(0.66, 0.45, 0.645, 0.6).Q(0.66, 0.72, 0.84, 0.77)
         .L(0.84, 0.88).L(0.2, 0.88).L(0.2, 0.77).Q(0.38, 0.72, 0.395, 0.6).Q(0.38, 0.46, 0.28, 0.42)
         .C(0.18, 0.4, 0.08, 0.34, 0.02, 0.22).C(0.1, 0.23, 0.18, 0.22, 0.27, 0.2).pts())


def g_anvil(c, band=True):
    c.poly(ANVIL)
    if band:
        with c.op("shade"):
            c.poly([(0.27, 0.2), (0.98, 0.2), (0.98, 0.25), (0.27, 0.25)])


def g_hammer(c):
    c.rect(0.12, 0.06, 0.88, 0.36, r=0.05)
    c.rect(0.43, 0.3, 0.57, 0.97, r=0.04)
    with c.op("shade"):
        c.rect(0.12, 0.06, 0.24, 0.36)
        c.rect(0.76, 0.06, 0.88, 0.36)
    with c.op("cut"):
        c.rect(0.24, 0.06, 0.265, 0.36)
        c.rect(0.735, 0.06, 0.76, 0.36)


def g_sword(c, w=0.16, fuller=True):
    c.poly([(0.5, 0.0), (0.5 + w / 2, 0.14), (0.5 + w / 2, 0.66), (0.5 - w / 2, 0.66), (0.5 - w / 2, 0.14)])
    c.rect(0.24, 0.65, 0.76, 0.73, r=0.035)
    c.rect(0.45, 0.72, 0.55, 0.9)
    c.circle(0.5, 0.93, 0.065)
    if fuller:
        with c.op("cut"):
            c.poly([(0.5, 0.16), (0.515, 0.2), (0.515, 0.6), (0.485, 0.6), (0.485, 0.2)])


def g_dagger(c):
    c.poly([(0.5, 0.0), (0.6, 0.2), (0.59, 0.6), (0.41, 0.6), (0.4, 0.2)])
    c.poly(Path(0.2, 0.56).Q(0.5, 0.66, 0.8, 0.56).L(0.8, 0.66).Q(0.5, 0.74, 0.2, 0.66).pts())
    c.rect(0.44, 0.68, 0.56, 0.9, r=0.02)
    c.circle(0.5, 0.93, 0.07)


def g_arrow(c, fletch=True, head=0.3, w=0.07):
    """An arrow pointing right along y = 0.5."""
    c.rect(0.06, 0.5 - w / 2, 1.0 - head * 0.8, 0.5 + w / 2)
    c.poly([(1.0 - head, 0.32), (1.0, 0.5), (1.0 - head, 0.68), (1.0 - head * 0.8, 0.5)])
    if fletch:
        c.poly([(0.0, 0.3), (0.12, 0.3), (0.26, 0.47), (0.14, 0.47)])
        c.poly([(0.0, 0.7), (0.12, 0.7), (0.26, 0.53), (0.14, 0.53)])


def g_arrowhead(c):
    c.poly([(0.5, 0.0), (0.95, 0.9), (0.5, 0.68), (0.05, 0.9)])


def g_chevron(c, thick=0.22):
    c.poly([(0.5, 0.2), (0.95, 0.65), (0.95, 0.65 + thick), (0.5, 0.2 + thick), (0.05, 0.65 + thick), (0.05, 0.65)])


def g_spark4(c, inner=0.13):
    c.star(0.5, 0.5, 0.5, inner, 4)


def g_spark8(c):
    c.star(0.5, 0.5, 0.5, 0.2, 4)
    c.star(0.5, 0.5, 0.32, 0.12, 4, rot_deg=-45)


def g_eye(c, pupil=True):
    c.poly(Path(0.0, 0.5).Q(0.5, -0.02, 1.0, 0.5).Q(0.5, 1.02, 0.0, 0.5).pts())
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.21)
    if pupil:
        c.circle(0.5, 0.5, 0.12)


def g_crescent(c, cut_dx=0.2, cut_dy=-0.14, r=0.47, cr=0.4):
    c.circle(0.5, 0.5, r)
    with c.op("cut"):
        c.circle(0.5 + cut_dx, 0.5 + cut_dy, cr)


def g_gear(c, n=8, hub=True):
    c.poly(gear_pts(0.5, 0.5, 0.5, 0.39, n, rot_deg=-90 - 360 / n * 0.31))
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.2)
    if hub:
        c.circle(0.5, 0.5, 0.09)


def g_coin(c, emblem=None):
    c.circle(0.5, 0.5, 0.48)
    with c.op("cut"):
        c.ring(0.5, 0.5, 0.39, 0.045)
    if emblem == "star":
        with c.op("cut"):
            c.star(0.5, 0.5, 0.22, 0.09, 4)
    elif emblem == "slot":
        with c.op("cut"):
            c.rect(0.44, 0.3, 0.56, 0.7, r=0.03)


def g_shard(c, facets=True):
    c.poly([(0.5, 0.0), (0.78, 0.3), (0.66, 1.0), (0.34, 1.0), (0.22, 0.3)])
    if facets:
        with c.op("shade"):
            c.poly([(0.5, 0.0), (0.78, 0.3), (0.66, 1.0), (0.5, 1.0), (0.5, 0.36)])
        with c.op("ink"):
            c.line([(0.22, 0.3), (0.5, 0.36), (0.78, 0.3)], 0.025)


def g_crystal(c):
    c.poly([(0.5, 0.0), (0.66, 0.2), (0.62, 1.0), (0.38, 1.0), (0.34, 0.2)])


SHIELD = (Path(0.08, 0.08).Q(0.5, 0.0, 0.92, 0.08).L(0.92, 0.46).C(0.92, 0.72, 0.72, 0.88, 0.5, 1.0)
          .C(0.28, 0.88, 0.08, 0.72, 0.08, 0.46).L(0.08, 0.08).pts())
SHIELD_IN = (Path(0.2, 0.19).Q(0.5, 0.13, 0.8, 0.19).L(0.8, 0.46).C(0.8, 0.66, 0.66, 0.78, 0.5, 0.86)
             .C(0.34, 0.78, 0.2, 0.66, 0.2, 0.46).L(0.2, 0.19).pts())


def g_shield(c, boss=None):
    c.poly(SHIELD)
    if boss == "rim":
        with c.op("cut"):
            c.poly(SHIELD_IN)
    elif boss == "half":
        with c.op("shade"):
            c.poly(Path(0.5, 0.04).Q(0.71, 0.03, 0.92, 0.08).L(0.92, 0.46).C(0.92, 0.72, 0.72, 0.88, 0.5, 1.0).pts())


def g_round_shield(c):
    c.circle(0.5, 0.5, 0.48)
    with c.op("cut"):
        c.ring(0.5, 0.5, 0.38, 0.05)
    c.circle(0.5, 0.5, 0.13)


def g_hourglass(c, sand=True):
    c.rect(0.14, 0.0, 0.86, 0.1, r=0.03)
    c.rect(0.14, 0.9, 0.86, 1.0, r=0.03)
    c.poly(Path(0.22, 0.1).L(0.78, 0.1).C(0.78, 0.36, 0.56, 0.42, 0.56, 0.5).C(0.56, 0.58, 0.78, 0.64, 0.78, 0.9)
           .L(0.22, 0.9).C(0.22, 0.64, 0.44, 0.58, 0.44, 0.5).C(0.44, 0.42, 0.22, 0.36, 0.22, 0.1).pts())
    with c.op("cut"):
        c.poly(Path(0.31, 0.17).L(0.69, 0.17).C(0.69, 0.34, 0.5, 0.4, 0.5, 0.46).C(0.5, 0.4, 0.31, 0.34, 0.31, 0.17).pts())
        if sand:
            c.poly(Path(0.5, 0.62).C(0.52, 0.7, 0.69, 0.72, 0.69, 0.83).L(0.31, 0.83).C(0.31, 0.72, 0.48, 0.7, 0.5, 0.62).pts())
    if sand:
        c.poly([(0.5, 0.7), (0.64, 0.83), (0.36, 0.83)])


def g_clock(c, h1=-90.0, h2=30.0, ticks=True):
    c.ring(0.5, 0.5, 0.5, 0.1)
    if ticks:
        for i in range(12):
            a = i * 30
            r0 = 0.3 if i % 3 == 0 else 0.34
            c.line([polar(0.5, 0.5, r0, a), polar(0.5, 0.5, 0.37, a)], 0.045 if i % 3 == 0 else 0.03, cap=False)
    c.line([(0.5, 0.5), polar(0.5, 0.5, 0.28, h1)], 0.075)
    c.line([(0.5, 0.5), polar(0.5, 0.5, 0.2, h2)], 0.075)
    c.circle(0.5, 0.5, 0.07)


def g_spiral(c, turns=1.6, w0=0.13, w1=0.03, cw=True, a0=0.0):
    c.taper(spiral_pts(0.5, 0.5, 0.46, 0.05, turns, a0, cw=cw), w0, w1)


def g_cloud(c):
    for x, y, r in ((0.3, 0.58, 0.22), (0.52, 0.42, 0.28), (0.74, 0.56, 0.2), (0.16, 0.7, 0.14), (0.86, 0.7, 0.13)):
        c.circle(x, y, r)
    c.rect(0.16, 0.6, 0.86, 0.84, r=0.12)


def g_wave(c):
    c.poly(Path(0.02, 0.92).C(0.02, 0.5, 0.3, 0.12, 0.62, 0.12).C(0.86, 0.12, 0.98, 0.3, 0.9, 0.46)
           .C(0.84, 0.3, 0.7, 0.28, 0.62, 0.36).C(0.52, 0.46, 0.66, 0.6, 0.78, 0.56).C(0.7, 0.72, 0.5, 0.74, 0.44, 0.66)
           .C(0.4, 0.78, 0.6, 0.86, 0.98, 0.86).L(0.98, 0.92).pts())


def g_chain_link(c, w=0.12):
    c.rect(0.24, 0.02, 0.76, 0.98, r=0.26)
    with c.op("cut"):
        c.rect(0.24 + w, 0.02 + w, 0.76 - w, 0.98 - w, r=0.14)


def g_bell(c):
    c.poly(Path(0.5, 0.04).C(0.7, 0.04, 0.76, 0.2, 0.76, 0.42).C(0.76, 0.62, 0.84, 0.72, 0.96, 0.8).L(0.96, 0.86)
           .L(0.04, 0.86).L(0.04, 0.8).C(0.16, 0.72, 0.24, 0.62, 0.24, 0.42).C(0.24, 0.2, 0.3, 0.04, 0.5, 0.04).pts())
    c.circle(0.5, 0.92, 0.08)
    c.rect(0.44, 0.0, 0.56, 0.08, r=0.03)
    with c.op("cut"):
        c.rect(0.04, 0.76, 0.96, 0.79)


def g_flask(c, liquid=True):
    """Round-bottomed flask with a neck."""
    c.circle(0.5, 0.64, 0.34)
    c.rect(0.39, 0.08, 0.61, 0.4)
    c.rect(0.33, 0.02, 0.67, 0.11, r=0.03)
    if liquid:
        with c.op("shade"):
            c.poly([(0.1, 0.62), (0.9, 0.62), (0.9, 1.0), (0.1, 1.0)])


def g_fist(c):
    """A front-facing fist, knuckles up."""
    for x, top in ((0.26, 0.16), (0.42, 0.1), (0.58, 0.13), (0.74, 0.2)):
        c.rect(x - 0.085, top, x + 0.085, 0.56, r=0.085)
    c.rect(0.17, 0.38, 0.83, 0.8, r=0.1)
    c.rect(0.28, 0.76, 0.72, 0.99, r=0.02)
    with c.op("cut"):
        for x in (0.34, 0.5, 0.66):
            c.rect(x - 0.012, 0.2, x + 0.012, 0.46)
        c.poly(stroke_poly([(0.1, 0.62), (0.62, 0.53)], 0.2))
    c.poly(stroke_poly([(0.13, 0.63), (0.58, 0.55)], 0.13))
    c.circle(0.58, 0.55, 0.065)
    c.circle(0.15, 0.63, 0.065)
    with c.op("shade"):
        c.rect(0.28, 0.8, 0.72, 0.99)


def g_fist_side(c):
    """A side-view fist punching to the right (thumb on top)."""
    c.rect(0.02, 0.36, 0.26, 0.72, r=0.03)
    c.rect(0.2, 0.26, 0.76, 0.8, r=0.14)
    for i in range(4):
        y0 = 0.3 + i * 0.125
        c.rect(0.58, y0, 0.97, y0 + 0.118, r=0.055)
    with c.op("cut"):
        for i in range(1, 4):
            y = 0.3 + i * 0.125 - 0.006
            c.rect(0.66, y - 0.006, 0.97, y + 0.006)
        c.poly(stroke_poly([(0.3, 0.3), (0.72, 0.3)], 0.16))
    c.poly(stroke_poly([(0.32, 0.3), (0.72, 0.3)], 0.1))
    c.circle(0.72, 0.3, 0.05)
    with c.op("shade"):
        c.rect(0.02, 0.36, 0.26, 0.72)


def g_hand_grab(c):
    """A clawed hand reaching down, fingers curling inward."""
    c.rect(0.3, 0.0, 0.7, 0.26, r=0.06)
    c.poly(Path(0.22, 0.2).L(0.78, 0.2).C(0.86, 0.3, 0.86, 0.46, 0.78, 0.52).L(0.22, 0.52).C(0.14, 0.46, 0.14, 0.3, 0.22, 0.2).pts())
    for x0, x1, bend in ((0.26, 0.2, -0.1), (0.42, 0.4, -0.05), (0.58, 0.6, 0.05), (0.74, 0.8, 0.1)):
        c.bez((x0, 0.45), (x0 + bend * 0.5, 0.7), (x1 + bend, 0.8), (0.5 + (x1 - 0.5) * 0.55, 0.96), 0.13, 0.03)
    with c.op("shade"):
        c.rect(0.3, 0.0, 0.7, 0.2)


def g_wing(c, feathers=4):
    """A swept wing pointing up-right."""
    for i in range(feathers):
        t = i / max(1, feathers - 1)
        y = 0.18 + t * 0.62
        ln = 0.92 - t * 0.38
        c.bez((0.06, 0.8 - t * 0.1), (0.3, y + 0.05), (0.06 + ln * 0.6, y - 0.08), (0.06 + ln, y - 0.14), 0.18 - t * 0.04, 0.02)
    c.circle(0.12, 0.78, 0.1)


def g_crown(c, points=5, band=True):
    pts = [(0.04, 0.84), (0.04, 0.3)]
    n = points
    for i in range(n):
        x0 = 0.04 + 0.92 * i / n
        x1 = 0.04 + 0.92 * (i + 1) / n
        mid = (x0 + x1) / 2
        hi = 0.12 if i % 2 == 0 else 0.22
        if i == n // 2:
            hi = 0.04
        pts += [(mid, hi), (x1, 0.46 if i < n - 1 else 0.3)]
    pts += [(0.96, 0.84)]
    c.poly(pts)
    if band:
        with c.op("cut"):
            c.rect(0.04, 0.6, 0.96, 0.66)


def g_scales(c):
    c.circle(0.5, 0.1, 0.07)
    c.rect(0.46, 0.1, 0.54, 0.86)
    c.rect(0.08, 0.2, 0.92, 0.27, r=0.03)
    c.rect(0.24, 0.86, 0.76, 0.95, r=0.03)
    for x in (0.18, 0.82):
        c.line([(x, 0.24), (x - 0.12, 0.58)], 0.035)
        c.line([(x, 0.24), (x + 0.12, 0.58)], 0.035)
        c.poly(Path(x - 0.2, 0.56).L(x + 0.2, 0.56).C(x + 0.18, 0.7, x - 0.18, 0.7, x - 0.2, 0.56).pts())


def g_book(c):
    c.poly(Path(0.5, 0.2).C(0.34, 0.08, 0.14, 0.08, 0.0, 0.14).L(0.0, 0.86).C(0.14, 0.8, 0.34, 0.8, 0.5, 0.92)
           .C(0.66, 0.8, 0.86, 0.8, 1.0, 0.86).L(1.0, 0.14).C(0.86, 0.08, 0.66, 0.08, 0.5, 0.2).pts())
    with c.op("cut"):
        c.line([(0.5, 0.24), (0.5, 0.86)], 0.04)
    with c.op("shade"):
        c.poly(Path(0.5, 0.2).C(0.66, 0.08, 0.86, 0.08, 1.0, 0.14).L(1.0, 0.86).C(0.86, 0.8, 0.66, 0.8, 0.5, 0.92).pts())


def g_bullet(c):
    """A slug pointing up."""
    c.poly(Path(0.3, 0.98).L(0.3, 0.42).C(0.3, 0.2, 0.4, 0.06, 0.5, 0.0).C(0.6, 0.06, 0.7, 0.2, 0.7, 0.42).L(0.7, 0.98).pts())
    with c.op("cut"):
        c.rect(0.3, 0.7, 0.7, 0.74)
    with c.op("shade"):
        c.rect(0.3, 0.74, 0.7, 0.98)


def g_reticle(c, gap=0.16, ring_r=0.36, w=0.075):
    c.ring(0.5, 0.5, ring_r, w)
    for a in (0, 90, 180, 270):
        c.line([polar(0.5, 0.5, gap, a), polar(0.5, 0.5, 0.5, a)], w, cap=False)
    c.circle(0.5, 0.5, 0.05)


def g_burst(c, n=10, r0=0.5, r1=0.26, hole=0.0):
    pts = []
    for i in range(n * 2):
        r = r0 if i % 2 == 0 else r1
        if i % 4 == 2:
            r *= 0.8
        pts.append(polar(0.5, 0.5, r, -90 + i * 180 / n))
    c.poly(pts)
    if hole:
        with c.op("cut"):
            c.circle(0.5, 0.5, hole)


def g_sawblade(c, n=10):
    pts = []
    for i in range(n):
        a = i * 360 / n
        pts += [polar(0.5, 0.5, 0.36, a), polar(0.5, 0.5, 0.5, a + 360 / n * 0.15), polar(0.5, 0.5, 0.4, a + 360 / n * 0.6)]
    c.poly(pts)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.13)


def g_magnet(c):
    c.poly(Path(0.08, 0.0).L(0.34, 0.0).L(0.34, 0.5).C(0.34, 0.62, 0.42, 0.7, 0.5, 0.7).C(0.58, 0.7, 0.66, 0.62, 0.66, 0.5)
           .L(0.66, 0.0).L(0.92, 0.0).L(0.92, 0.5).C(0.92, 0.8, 0.74, 0.96, 0.5, 0.96).C(0.26, 0.96, 0.08, 0.8, 0.08, 0.5).L(0.08, 0.0).pts())
    with c.op("shade"):
        c.rect(0.08, 0.0, 0.34, 0.16)
        c.rect(0.66, 0.0, 0.92, 0.16)


def g_die(c):
    """An isometric die."""
    c.poly([(0.5, 0.02), (0.94, 0.25), (0.94, 0.74), (0.5, 0.98), (0.06, 0.74), (0.06, 0.25)])
    with c.op("shade"):
        c.poly([(0.5, 0.48), (0.94, 0.25), (0.94, 0.74), (0.5, 0.98)])
    with c.op("cut"):
        c.line([(0.06, 0.25), (0.5, 0.48), (0.94, 0.25)], 0.035)
        c.line([(0.5, 0.48), (0.5, 0.98)], 0.035)
        c.ellipse(0.5, 0.25, 0.08, 0.05)
        for (x, y) in ((0.2, 0.46), (0.28, 0.61), (0.36, 0.76)):
            c.ellipse(x, y, 0.05, 0.065)
        for (x, y) in ((0.64, 0.56), (0.8, 0.72)):
            c.ellipse(x, y, 0.05, 0.065)


def g_boot(c):
    c.poly(Path(0.2, 0.0).L(0.56, 0.0).L(0.56, 0.52).C(0.62, 0.6, 0.86, 0.62, 0.96, 0.74).L(0.98, 0.96).L(0.14, 0.96)
           .L(0.14, 0.7).C(0.18, 0.5, 0.2, 0.3, 0.2, 0.0).pts())
    with c.op("shade"):
        c.rect(0.12, 0.86, 1.0, 0.96)
        c.rect(0.2, 0.0, 0.56, 0.1)


def g_footprint(c):
    c.poly(Path(0.5, 0.36).C(0.72, 0.36, 0.78, 0.56, 0.72, 0.74).C(0.66, 0.94, 0.52, 1.0, 0.42, 0.96)
           .C(0.3, 0.92, 0.28, 0.76, 0.32, 0.6).C(0.34, 0.46, 0.38, 0.36, 0.5, 0.36).pts())
    for x, y, r in ((0.28, 0.2, 0.08), (0.42, 0.12, 0.07), (0.56, 0.1, 0.065), (0.69, 0.14, 0.055), (0.8, 0.22, 0.05)):
        c.circle(x, y, r)


def g_paw(c):
    c.poly(Path(0.5, 0.44).C(0.76, 0.44, 0.9, 0.7, 0.8, 0.86).C(0.72, 0.98, 0.58, 0.9, 0.5, 0.9)
           .C(0.42, 0.9, 0.28, 0.98, 0.2, 0.86).C(0.1, 0.7, 0.24, 0.44, 0.5, 0.44).pts())
    for x, y, r, a in ((0.14, 0.4, 0.1, -20), (0.36, 0.16, 0.11, -8), (0.64, 0.16, 0.11, 8), (0.86, 0.4, 0.1, 20)):
        c.ellipse(x, y, r * 0.85, r * 1.15, r=a)


def g_comet(c):
    c.circle(0.7, 0.3, 0.26)
    c.poly([polar(0.7, 0.3, 0.26, 70), (0.02, 0.98), polar(0.7, 0.3, 0.26, 200)])
    with c.op("cut"):
        c.poly(stroke_poly([(0.54, 0.62), (0.22, 0.9)], 0.05))
        c.poly(stroke_poly([(0.44, 0.44), (0.12, 0.74)], 0.04))


def g_boulder(c):
    c.poly([(0.2, 0.2), (0.56, 0.04), (0.88, 0.2), (0.98, 0.56), (0.82, 0.9), (0.4, 0.98), (0.08, 0.8), (0.02, 0.44)])
    with c.op("shade"):
        c.poly([(0.98, 0.56), (0.82, 0.9), (0.4, 0.98), (0.56, 0.62)])
    with c.op("cut"):
        c.line([(0.2, 0.2), (0.4, 0.4), (0.56, 0.62), (0.98, 0.56)], 0.035)


def g_mountain(c):
    c.poly([(0.0, 0.96), (0.34, 0.3), (0.46, 0.48), (0.64, 0.12), (1.0, 0.96)])
    with c.op("shade"):
        c.poly([(0.64, 0.12), (1.0, 0.96), (0.6, 0.96), (0.7, 0.6)])


def g_antler(c):
    c.bez((0.62, 1.0), (0.6, 0.7), (0.52, 0.4), (0.26, 0.06), 0.14, 0.05)
    c.bez((0.56, 0.62), (0.7, 0.52), (0.86, 0.42), (0.9, 0.2), 0.1, 0.03)
    c.bez((0.44, 0.38), (0.54, 0.3), (0.64, 0.18), (0.64, 0.02), 0.09, 0.03)
    c.bez((0.6, 0.82), (0.74, 0.8), (0.9, 0.74), (0.98, 0.6), 0.09, 0.03)


def g_javelin(c):
    """Pointing up-right."""
    c.line([(0.06, 0.94), (0.72, 0.28)], 0.075)
    c.poly(rot([(0.5, 0.0), (0.6, 0.2), (0.5, 0.36), (0.4, 0.2)], 0.5, 0.18, 45))


def g_candle(c):
    c.rect(0.34, 0.42, 0.66, 0.96, r=0.03)
    c.poly(Path(0.34, 0.46).C(0.3, 0.52, 0.3, 0.6, 0.32, 0.64).L(0.34, 0.6).pts())
    with c.place(0.5, 0.2, 0.36):
        g_flame_simple(c)
    with c.op("shade"):
        c.rect(0.34, 0.86, 0.66, 0.96)


def g_lozenge(c, hole=0.0):
    c.poly([(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)])
    if hole:
        with c.op("cut"):
            h = hole
            c.poly([(0.5, 0.5 - h), (0.5 + h, 0.5), (0.5, 0.5 + h), (0.5 - h, 0.5)])


def g_mark(c):
    """The Mark status: a crosshair lozenge."""
    c.poly([(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)])
    with c.op("cut"):
        c.poly([(0.5, 0.2), (0.8, 0.5), (0.5, 0.8), (0.2, 0.5)])
    c.circle(0.5, 0.5, 0.1)
    for a in (0, 90, 180, 270):
        c.line([polar(0.5, 0.5, 0.17, a), polar(0.5, 0.5, 0.3, a)], 0.055, cap=False)


def g_hexeye(c):
    """The Curse status: a hex eye under three tally marks."""
    c.poly(Path(0.0, 0.58).Q(0.5, 0.12, 1.0, 0.58).Q(0.5, 1.04, 0.0, 0.58).pts())
    with c.op("cut"):
        c.circle(0.5, 0.58, 0.2)
    c.poly([(0.5, 0.44), (0.58, 0.58), (0.5, 0.72), (0.42, 0.58)])
    for x, tilt in ((0.22, -14), (0.5, 0), (0.78, 14)):
        c.poly(rot([(x - 0.045, 0.0), (x + 0.045, 0.0), (x + 0.03, 0.24), (x - 0.03, 0.24)], x, 0.12, tilt))


def g_roots(c):
    c.poly(stroke_poly([(0.5, 0.0), (0.5, 0.5)], 0.16))
    c.bez((0.5, 0.42), (0.36, 0.62), (0.16, 0.62), (0.04, 0.96), 0.13, 0.03)
    c.bez((0.5, 0.42), (0.64, 0.62), (0.84, 0.62), (0.96, 0.96), 0.13, 0.03)
    c.bez((0.5, 0.5), (0.48, 0.7), (0.54, 0.84), (0.48, 1.0), 0.12, 0.03)
    c.bez((0.3, 0.62), (0.24, 0.72), (0.3, 0.84), (0.22, 0.98), 0.06, 0.02)
    c.bez((0.7, 0.62), (0.76, 0.72), (0.7, 0.84), (0.78, 0.98), 0.06, 0.02)


def g_blood(c):
    """The Bleed status: three falling drops."""
    with c.place(0.33, 0.33, 0.62):
        g_drop(c)
    with c.place(0.72, 0.5, 0.46):
        g_drop(c)
    with c.place(0.4, 0.8, 0.36):
        g_drop(c)


def g_tower_shield(c):
    c.poly(Path(0.14, 0.0).L(0.86, 0.0).L(0.86, 0.72).C(0.86, 0.86, 0.7, 0.94, 0.5, 1.0).C(0.3, 0.94, 0.14, 0.86, 0.14, 0.72).pts())
    with c.op("shade"):
        c.poly(Path(0.5, 0.0).L(0.86, 0.0).L(0.86, 0.72).C(0.86, 0.86, 0.7, 0.94, 0.5, 1.0).pts())


def g_turret(c):
    c.rect(0.3, 0.18, 0.96, 0.34, r=0.03)
    c.rect(0.24, 0.1, 0.56, 0.5, r=0.08)
    c.rect(0.36, 0.48, 0.44, 0.64)
    c.line([(0.4, 0.62), (0.1, 0.98)], 0.08)
    c.line([(0.4, 0.62), (0.7, 0.98)], 0.08)
    c.line([(0.4, 0.62), (0.4, 0.98)], 0.07)
    with c.op("shade"):
        c.rect(0.24, 0.3, 0.56, 0.5)


def g_speed_lines(c, n=3):
    for i in range(n):
        y = 0.2 + i * 0.3
        x0 = 0.02 + (0.2 if i == 1 else 0.0)
        c.line([(x0, y), (0.98, y)], 0.09)


def g_ccw_arrow(c, a0=320.0, a1=40.0, r=0.4, w=0.12):
    """A circular arrow; the stroke runs from a1 back to a0 and the head sits at a0 pointing on."""
    c.arc(0.5, 0.5, r, a0, a1, w)
    tip = polar(0.5, 0.5, r, a0 - 34)
    c.poly([polar(0.5, 0.5, r + w * 1.25, a0), polar(0.5, 0.5, r - w * 1.25, a0), tip])


def g_cw_arrow(c, a0=200.0, a1=480.0, r=0.4, w=0.12):
    """A circular arrow turning clockwise from a0 to a1; the head sits at a1."""
    c.arc(0.5, 0.5, r, a0, a1, w)
    tip = polar(0.5, 0.5, r, a1 + 34)
    c.poly([polar(0.5, 0.5, r + w * 1.25, a1), polar(0.5, 0.5, r - w * 1.25, a1), tip])


def g_lock(c):
    c.arc(0.5, 0.38, 0.26, 180, 360, 0.12)
    c.rect(0.18, 0.38, 0.32, 0.46)
    c.rect(0.68, 0.38, 0.82, 0.46)
    c.rect(0.08, 0.44, 0.92, 0.98, r=0.08)
    with c.op("cut"):
        c.circle(0.5, 0.64, 0.08)
        c.poly([(0.46, 0.66), (0.54, 0.66), (0.57, 0.84), (0.43, 0.84)])


def g_check(c):
    c.line([(0.06, 0.54), (0.36, 0.84), (0.94, 0.18)], 0.2)


def g_cross(c, w=0.2):
    c.line([(0.1, 0.1), (0.9, 0.9)], w)
    c.line([(0.9, 0.1), (0.1, 0.9)], w)


def g_plus(c, w=0.24):
    c.rect(0.5 - w / 2, 0.04, 0.5 + w / 2, 0.96, r=0.03)
    c.rect(0.04, 0.5 - w / 2, 0.96, 0.5 + w / 2, r=0.03)


# ───────────────────────────── display levels and sheets ─────────────────────────────
def box2(img: Image.Image) -> Image.Image:
    """Premultiplied 2x2 box filter, as the runtime builds its 64 and 32 levels."""
    a = np.asarray(img, np.float32) / 255.0
    prem = np.dstack([a[..., :3] * a[..., 3:4], a[..., 3:4]])
    h, w, _ = prem.shape
    prem = prem.reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
    return to_image(prem)


def levels(img: Image.Image) -> dict[int, Image.Image]:
    l64 = box2(img)
    return {128: img, 64: l64, 32: box2(l64)}


def at_size(lv: dict[int, Image.Image], px: int) -> Image.Image:
    """What the game shows at `px` logical px: the smallest level >= px, bilinear to px."""
    src = lv[128]
    for s in (32, 64, 128):
        if s >= px:
            src = lv[s]
            break
    if src.size[0] == px:
        return src
    return src.convert("RGBa").resize((px, px), Image.BILINEAR).convert("RGBA")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    if name.startswith("Cinzel"):
        try:
            f.set_variation_by_axes([700])
        except Exception:
            pass
    return f


def lacquer_bg(w: int, h: int, top=(0x2A, 0x1E, 0x16), bot=(0x13, 0x0D, 0x0A)) -> Image.Image:
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bot, np.float32) * t
    arr = np.repeat(arr, w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


_DISCS: dict[int, Image.Image] = {}


def slot_disc(size: int) -> Image.Image:
    """A dark round recess with a thin gilt rim, like a HUD slot, to judge icons on their ground."""
    if size in _DISCS:
        return _DISCS[size]
    s = size * 4
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.sqrt((xx - s / 2 + 0.5) ** 2 + (yy - s / 2 + 0.5) ** 2) / (s / 2)
    inside = np.clip((1.0 - r) * s / 2, 0, 1)
    t = np.clip(yy / s, 0, 1)[..., None]
    col = np.array([0x35, 0x26, 0x1A], np.float32) * (1 - t) + np.array([0x11, 0x0B, 0x08], np.float32) * t
    rim = np.clip(1 - np.abs(r - 0.965) * s / 3, 0, 1)[..., None]
    col = col * (1 - rim) + np.array([0xB0, 0x84, 0x40], np.float32) * rim
    arr = np.dstack([col, inside * 255]).astype(np.uint8)
    _DISCS[size] = Image.fromarray(arr, "RGBA").resize((size, size), Image.LANCZOS)
    return _DISCS[size]


def contact_sheet(keys: list[str], images: dict[str, Image.Image], path: str, title: str,
                  sizes=(64, 48, 32, 24), cols: int = 10, meanings: dict[str, str] | None = None):
    """A labelled sheet: every icon at each of `sizes` on a slot recess, grouped by folder."""
    label_f = font("AlegreyaSans-Medium.ttf", 14)
    head_f = font("Cinzel-Variable.ttf", 26)
    title_f = font("Cinzel-Variable.ttf", 40)
    sub_f = font("AlegreyaSans-Italic.ttf", 18)
    gap = 12
    cell_w = 14 + sum(int(s * 1.25) + gap for s in sizes)
    first = sizes[0]
    cell_h = int(first * 1.25) + 34
    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(k.split("/")[0], []).append(k)
    rows = sum((len(v) + cols - 1) // cols for v in groups.values())
    W = 40 + cols * cell_w + 30
    H = 130 + len(groups) * 60 + rows * (cell_h + 8) + 40
    sheet = lacquer_bg(W, H)
    d = ImageDraw.Draw(sheet)
    d.text((40, 28), title, font=title_f, fill=(0xF2, 0xC6, 0x67))
    d.text((40, 82), f"{len(keys)} icons, each shown at " + " / ".join(str(s) for s in sizes) +
           " px (the runtime's 128/64/32 levels, bilinear between) on a HUD slot recess. All shapes original to GODFORGE.",
           font=sub_f, fill=(0xB9, 0xA9, 0x8C))
    y = 126
    for g, ks in groups.items():
        d.text((40, y + 12), f"{g.upper()}  ·  {len(ks)}", font=head_f, fill=(0xF2, 0xC6, 0x67))
        d.line([(40, y + 50), (W - 30, y + 50)], fill=(0x7A, 0x54, 0x24), width=1)
        y += 60
        for i, k in enumerate(ks):
            cx = 40 + (i % cols) * cell_w
            cy = y + (i // cols) * (cell_h + 8)
            d.rounded_rectangle([cx, cy, cx + cell_w - 8, cy + cell_h], radius=6, fill=(0x1A, 0x12, 0x0E),
                                outline=(0x3B, 0x26, 0x10))
            lv = levels(images[k])
            x = cx + 10
            for s in sizes:
                disc = slot_disc(int(s * 1.25))
                dy = cy + 5 + (int(first * 1.25) - disc.size[1]) // 2
                sheet.alpha_composite(disc, (x, dy))
                off = (disc.size[0] - s) // 2
                sheet.alpha_composite(at_size(lv, s), (x + off, dy + off))
                x += disc.size[0] + gap
            name = k.split("/", 1)[1]
            tw = d.textlength(name, font=label_f)
            while tw > cell_w - 20 and len(name) > 4:
                name = name[:-2] + "…"
                tw = d.textlength(name, font=label_f)
            d.text((cx + 10, cy + cell_h - 24), name, font=label_f, fill=(0xE8, 0xDA, 0xBE))
        y += ((len(ks) + cols - 1) // cols) * (cell_h + 8)
    sheet = sheet.crop((0, 0, W, y + 24))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.convert("RGB").save(path, optimize=True)
    return sheet


# ───────────────────────────── content ─────────────────────────────
@dataclass
class Content:
    characters: list[dict]
    gods: dict[str, dict]
    parts: list[dict]
    boons: list[dict]
    chassis: list[dict]
    kits: dict[str, dict]
    ron_keys: dict[str, list[str]]


def _csv(name: str) -> list[dict]:
    with open(os.path.join(SHEETS, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _ron_keys(name: str) -> list[str]:
    with open(os.path.join(GENERATED, name), encoding="utf-8") as f:
        return re.findall(r'^\s*key:\s*"([a-z0-9_]+)"', f.read(), re.M)


def _kits() -> dict[str, dict]:
    """character -> {q, e, r: (name, desc), passive: primitive name} from kits.ron."""
    with open(KITS_RON, encoding="utf-8") as f:
        text = f.read()
    out: dict[str, dict] = {}
    blocks = re.split(r'\n\s*\(\s*\n\s*character:\s*"', text)[1:]
    for b in blocks:
        ch = b.split('"', 1)[0]
        pas = re.search(r"passive:\s*([A-Za-z]+)", b)
        abil = {}
        for slot, field_ in (("q", "active1"), ("e", "active2"), ("r", "ultimate")):
            m = re.search(field_ + r':\s*\(\s*name:\s*"([^"]+)",\s*desc:\s*"([^"]+)"', b)
            if m:
                abil[slot] = (m.group(1), m.group(2))
        out[ch] = {"passive": pas.group(1) if pas else "", **abil}
    return out


def load_content() -> Content:
    chars = _csv("characters.csv")
    gods = {r["key"]: r for r in _csv("gods.csv")}
    for k, r in gods.items():
        GODS[k] = (r["color"], r["color_secondary"])
    return Content(
        characters=chars, gods=gods, parts=_csv("parts.csv"), boons=_csv("boons.csv"), chassis=_csv("chassis.csv"),
        kits=_kits(),
        ron_keys={n: _ron_keys(n + ".ron") for n in ("parts", "boons", "chassis", "characters", "gods")})


CONTENT_HOOKS: list[Callable[[Content], None]] = []


def content_hook(fn):
    CONTENT_HOOKS.append(fn)
    return fn


def god_tint(god: str, small: bool = True) -> str:
    """A god's colour for a glyph; red primaries switch to the secondary (UI_STYLE 2, 3.4)."""
    col, sec = GODS[god]
    return sec if god in RED_GODS else col


# ───────────────────────────── elements ─────────────────────────────
def g_kinetic(c):
    """Impact chevrons: three stacked chevrons driving down into a point."""
    for i, (y, w) in enumerate(((0.0, 0.9), (0.24, 0.72), (0.46, 0.54))):
        x0 = 0.5 - w / 2
        c.poly([(x0, y), (0.5, y + w * 0.3), (x0 + w, y), (x0 + w, y + 0.17), (0.5, y + w * 0.3 + 0.17), (x0, y + 0.17)])
    with c.place(0.5, 0.86, 0.4):
        g_spark4(c, 0.14)


def g_storm(c):
    """A forked bolt."""
    c.poly([(0.62, 0.0), (0.2, 0.55), (0.45, 0.55), (0.36, 1.0), (0.84, 0.4), (0.57, 0.4), (0.75, 0.0)])
    c.poly([(0.3, 0.55), (0.4, 0.55), (0.24, 0.72), (0.3, 0.72), (0.06, 0.96), (0.14, 0.7), (0.08, 0.7)])


def g_void_el(c):
    """A ringed singularity: a ring round a spiral falling into a core."""
    c.ring(0.5, 0.5, 0.5, 0.1)
    c.taper(spiral_pts(0.5, 0.5, 0.33, 0.09, 1.15, 200), 0.12, 0.05)
    c.circle(0.5, 0.5, 0.1)


def g_plague_el(c):
    """A spore drop: a drop pitted with spores and two satellites."""
    c.poly(teardrop_pts(0.46, 1.0, 0.36, 0.96, 0.0))
    with c.op("cut"):
        c.circle(0.36, 0.72, 0.08)
        c.circle(0.56, 0.82, 0.06)
        c.circle(0.52, 0.6, 0.045)
    c.circle(0.86, 0.36, 0.1)
    c.circle(0.9, 0.6, 0.065)


def g_radiant(c):
    """An eight-point sun."""
    c.star(0.5, 0.5, 0.5, 0.25, 8)
    c.star(0.5, 0.5, 0.36, 0.2, 8, rot_deg=-90 + 22.5)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.2)
    c.circle(0.5, 0.5, 0.13)


ELEMENT_GLYPH = {"kinetic": g_kinetic, "flame": g_flame, "storm": g_storm, "void": g_void_el, "plague": g_plague_el,
                 "radiant": g_radiant}
for _e, _fn in ELEMENT_GLYPH.items():
    reg("elements", _e, _fn, ELEMENT[_e], f"The {_e.capitalize()} element")


# ───────────────────────────── rarity gems (the one baked-colour exception) ─────────────────────────────
def _gem_polys(shape: str):
    """Outer outline and facets (polygon, shade) of a cut, in unit space centred on 0.5."""
    cx = cy = 0.5
    L = np.array([-0.55, -0.83])
    facets = []
    if shape == "rare":  # lozenge
        outer = [(0.5, 0.02), (0.86, 0.5), (0.5, 0.98), (0.14, 0.5)]
        table = [(0.5, 0.3), (0.64, 0.5), (0.5, 0.7), (0.36, 0.5)]
    elif shape == "epic":  # hexagon step-cut
        outer = [polar(cx, cy, 0.48, -90 + i * 60) for i in range(6)]
        table = [polar(cx, cy, 0.27, -90 + i * 60) for i in range(6)]
    elif shape == "godforged":  # eight-point star
        outer = []
        for i in range(16):
            outer.append(polar(cx, cy, 0.5 if i % 2 == 0 else 0.26, -90 + i * 22.5))
        table = [polar(cx, cy, 0.14, -90 + i * 45) for i in range(8)]
        for i in range(16):
            a, b = outer[i], outer[(i + 1) % 16]
            mid = ((a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy)
            n = np.array(mid) / (np.linalg.norm(mid) + 1e-6)
            k = 1.0 + 0.5 * float(n @ L) + (0.18 if i % 2 else -0.12)
            facets.append(([a, b, (cx, cy)], k))
        return outer, facets, table
    else:
        raise ValueError(shape)
    n = len(outer)
    for i in range(n):
        a, b = outer[i], outer[(i + 1) % n]
        ta, tb = table[i], table[(i + 1) % n]
        mid = ((a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy)
        nv = np.array(mid) / (np.linalg.norm(mid) + 1e-6)
        k = 1.0 + 0.55 * float(nv @ L)
        facets.append(([a, b, tb, ta], k))
    facets.append((table, 1.12))
    return outer, facets, table


def gem_prem(rarity: str) -> np.ndarray:
    col = np.array(rgb(RARITY[rarity]), np.float32) / 255.0
    S = WORK
    pad = PAD * S
    span = S - 2 * pad

    def px(p, grow=1.0):
        return (pad + (0.5 + (p[0] - 0.5) * grow) * span, pad + (0.5 + (p[1] - 0.5) * grow) * span)

    if rarity == "common":
        # round cabochon in a bezel
        setting = unit_disc(0.45)
        stone = unit_disc(0.36)
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
        r = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (0.36 * S)
        lit = np.sqrt(np.clip(1 - r ** 2, 0, 1))
        hl = np.clip(1 - np.sqrt((xx - S * 0.42) ** 2 + (yy - S * 0.38) ** 2) / (0.11 * S), 0, 1) ** 1.6
        shadev = (0.5 + 0.7 * lit) * (1.0 - 0.25 * np.clip((yy - S / 2) / (0.36 * S), 0, 1))
        gemc = col[None, None, :] * shadev[..., None] + hl[..., None] * 0.85
        gem_a = stone
        outer_mask = setting
    else:
        outer, facets, _ = _gem_polys(rarity)
        im = Image.new("RGB", (S, S), (0, 0, 0))
        d = ImageDraw.Draw(im)
        for poly, k in facets:
            c3 = np.clip(col * k + max(0.0, k - 1.15) * 0.6, 0, 1)
            d.polygon([px(p) for p in poly], fill=tuple(int(v * 255) for v in c3))
        # facet edges read as fine dark lines
        for poly, _ in facets:
            d.line([px(p) for p in poly] + [px(poly[0])], fill=tuple(int(v * 255 * 0.55) for v in col), width=max(1, SS // 2))
        gemc = np.asarray(im, np.float32) / 255.0
        mk = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mk).polygon([px(p) for p in outer], fill=255)
        gem_a = np.asarray(mk, np.float32) / 255.0
        sm = Image.new("L", (S, S), 0)
        ImageDraw.Draw(sm).polygon([px(p, 1.16) for p in outer], fill=255)
        outer_mask = np.asarray(sm, np.float32) / 255.0
        # glint: a small four-point star on the upper-left facets
        g = Canvas()
        g.star(0.5, 0.5, 0.5, 0.12, 4)
        gm, _, _ = fit_masks(g, 1.0, True)
        gm = small_at(gm, 0.2, 0.4, 0.34)
        gemc = gemc * (1 - gm[..., None]) + gm[..., None] * np.array([1.0, 1.0, 0.96])
    # gold_sh setting: a thin dark-gold bezel with a lit top edge
    ring = np.clip(outer_mask - gem_a, 0, 1)
    yy = np.linspace(0, 1, S, dtype=np.float32)[:, None] * np.ones((1, S), np.float32)
    metal = ramp(yy, [(0.0, "#C9933E"), (0.4, "#7A5424"), (1.0, "#3B2610")]) / 255.0
    base = np.dstack([metal * ring[..., None], ring])
    gem = np.dstack([gemc * gem_a[..., None], gem_a])
    out = over(base, gem)
    # ink outline
    ol = np.clip(OUTLINE * S - ndimage.distance_transform_edt(outer_mask < 0.5) + 0.5, 0, 1) * 0.95
    inkc = np.array(rgb(INK), np.float32) / 255.0
    return over(np.dstack([inkc * ol[..., None], ol]), out)


for _r, _cut in (("common", "round cabochon"), ("rare", "lozenge"), ("epic", "hexagon step-cut"),
                 ("godforged", "eight-point star")):
    reg("rarity", f"gem_{_r}", (lambda r=_r: gem_prem(r)), RARITY[_r],
        f"{_r.capitalize()} rarity gem: a {_cut} in its rarity colour (the only icon with a baked colour)", kind="gem")


# ───────────────────────────── part-slot ghost glyphs ─────────────────────────────
@icon("slots", "core", T_BONE, "Core slot (ghost glyph for an empty socket): an orb held in claws")
def s_core(c):
    c.circle(0.5, 0.54, 0.27)
    with c.op("cut"):
        c.circle(0.42, 0.46, 0.07)
    for a in (-135, -45, 45, 135):
        p0 = polar(0.5, 0.54, 0.46, a)
        p1 = polar(0.5, 0.54, 0.34, a + 28)
        p2 = polar(0.5, 0.54, 0.3, a + 40)
        c.bez(polar(0.5, 0.54, 0.5, a - 16), p0, p1, p2, 0.12, 0.02)


@icon("slots", "mechanism", T_BONE, "Mechanism slot (ghost glyph): a gear")
def s_mech(c):
    g_gear(c, 8)


@icon("slots", "relic", T_BONE, "Relic slot (ghost glyph): an amulet with an eye")
def s_relic(c):
    c.arc(0.5, 0.2, 0.22, 180, 360, 0.08)
    c.line([(0.28, 0.2), (0.38, 0.4)], 0.08)
    c.line([(0.72, 0.2), (0.62, 0.4)], 0.08)
    c.poly(Path(0.5, 0.34).C(0.72, 0.4, 0.86, 0.58, 0.5, 1.0).C(0.14, 0.58, 0.28, 0.4, 0.5, 0.34).pts())
    with c.op("cut"):
        c.poly(Path(0.3, 0.64).Q(0.5, 0.48, 0.7, 0.64).Q(0.5, 0.8, 0.3, 0.64).pts())
    c.circle(0.5, 0.64, 0.065)


def seal_ring(c, bumps=12, r=0.5, w=0.13):
    pts = []
    n = bumps * 8
    for i in range(n):
        a = 360 * i / n
        rr = r - 0.035 * (1 - math.cos(math.radians(a * bumps))) / 2
        pts.append(polar(0.5, 0.5, rr, a))
    c.poly(pts)
    with c.op("cut"):
        c.circle(0.5, 0.5, r - w)


@icon("slots", "sigil", T_BONE, "Sigil slot (ghost glyph): a seal ring with a rune")
def s_sigil(c):
    seal_ring(c)
    c.line([(0.5, 0.28), (0.5, 0.74)], 0.09)
    c.line([(0.5, 0.42), (0.34, 0.3)], 0.08)
    c.line([(0.5, 0.42), (0.66, 0.3)], 0.08)
    c.line([(0.38, 0.62), (0.62, 0.62)], 0.08)


# ───────────────────────────── POIs ─────────────────────────────
@icon("poi", "anvil", T_BONE, "Anvil: hold the ring, then forge")
def p_anvil(c):
    with c.box(0.0, 0.2, 1.0, 1.0):
        g_anvil(c)
    with c.place(0.52, 0.12, 0.26):
        g_spark4(c)
    with c.place(0.26, 0.2, 0.15):
        g_spark4(c)
    with c.place(0.78, 0.2, 0.15):
        g_spark4(c)


@icon("poi", "warlord", T_WARLORD, "Warlord: the biome mini-boss (a crowned skull)")
def p_warlord(c):
    with c.box(0.1, 0.26, 0.9, 1.0):
        g_skull(c)
    c.poly([(0.16, 0.36), (0.2, 0.06), (0.35, 0.22), (0.5, 0.0), (0.65, 0.22), (0.8, 0.06), (0.84, 0.36),
            (0.5, 0.28)])
    with c.op("cut"):
        c.poly([(0.14, 0.33), (0.5, 0.25), (0.86, 0.33), (0.86, 0.37), (0.5, 0.3), (0.14, 0.37)])


@icon("poi", "lair", T_BONE, "Lair: a den of elites (a clawed cave maw)")
def p_lair(c):
    c.poly(Path(0.0, 0.96).C(0.0, 0.4, 0.22, 0.08, 0.5, 0.08).C(0.78, 0.08, 1.0, 0.4, 1.0, 0.96).pts())
    with c.op("cut"):
        c.poly(Path(0.22, 0.96).C(0.22, 0.62, 0.34, 0.44, 0.5, 0.44).C(0.66, 0.44, 0.78, 0.62, 0.78, 0.96).pts())
    for x, h in ((0.34, 0.2), (0.5, 0.26), (0.66, 0.2)):
        c.poly([(x - 0.07, 0.46), (x + 0.07, 0.46), (x, 0.46 + h)])
    with c.op("cut"):
        for i in range(3):
            x = 0.34 + i * 0.13
            c.poly(stroke_poly([(x + 0.02, 0.12), (x + 0.2, 0.34)], 0.05 - i * 0.005))


@icon("poi", "shrine", T_BONE, "Shrine: hold the ring for a boon (an altar flame; the UI tints it with the god)")
def p_shrine(c):
    with c.place(0.5, 0.26, 0.5):
        g_flame(c, core=True)
    c.poly([(0.14, 0.52), (0.86, 0.52), (0.78, 0.62), (0.22, 0.62)])
    c.rect(0.3, 0.62, 0.7, 0.86)
    c.rect(0.16, 0.86, 0.84, 0.98, r=0.02)
    with c.op("cut"):
        c.rect(0.4, 0.67, 0.6, 0.81)


@icon("poi", "reliquary", T_BONE, "Reliquary: hold the ring for a cache of parts (a chest)")
def p_reliquary(c):
    c.poly(Path(0.04, 0.44).C(0.04, 0.16, 0.24, 0.1, 0.5, 0.1).C(0.76, 0.1, 0.96, 0.16, 0.96, 0.44).pts())
    c.rect(0.04, 0.44, 0.96, 0.92, r=0.03)
    with c.op("cut"):
        c.rect(0.04, 0.44, 0.96, 0.49)
    with c.op("shade"):
        c.rect(0.18, 0.1, 0.26, 0.92)
        c.rect(0.74, 0.1, 0.82, 0.92)
    c.rect(0.4, 0.38, 0.6, 0.64, r=0.03)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.035)
        c.rect(0.49, 0.5, 0.51, 0.58)


@icon("poi", "vein", T_BONE, "Vein: hold the ring for godshards (a crystal cluster)")
def p_vein(c):
    for x, y, w, h, a in ((0.5, 0.0, 0.26, 0.9, 0), (0.24, 0.26, 0.2, 0.62, -22), (0.78, 0.3, 0.2, 0.58, 20),
                          (0.08, 0.56, 0.14, 0.36, -40), (0.93, 0.6, 0.13, 0.32, 38)):
        pts = [(x, y), (x + w / 2, y + w * 0.6), (x + w / 2, 0.92), (x - w / 2, 0.92), (x - w / 2, y + w * 0.6)]
        c.poly(rot(pts, x, 0.92, a))
    with c.op("shade"):
        c.poly([(0.5, 0.0), (0.63, 0.156), (0.63, 0.92), (0.5, 0.92)])
    c.rect(0.02, 0.88, 0.98, 0.98, r=0.03)


@icon("poi", "spring", T_BONE, "Spring: a healing spring, once per player (a basin and a rising drop)")
def p_spring(c):
    with c.place(0.5, 0.26, 0.5):
        g_drop(c, hole=True)
    c.poly(Path(0.02, 0.58).L(0.98, 0.58).C(0.96, 0.8, 0.76, 0.88, 0.5, 0.88).C(0.24, 0.88, 0.04, 0.8, 0.02, 0.58).pts())
    with c.op("cut"):
        c.rect(0.02, 0.64, 0.98, 0.68)
    c.rect(0.38, 0.86, 0.62, 0.94)
    c.rect(0.24, 0.92, 0.76, 1.0, r=0.02)


@icon("poi", "watchfire", T_BONE, "Watchfire: touch to reveal the map around it (a pyre)")
def p_watchfire(c):
    with c.place(0.5, 0.36, 0.72):
        g_flame(c, core=True)
    c.line([(0.1, 0.96), (0.9, 0.7)], 0.11)
    c.line([(0.1, 0.7), (0.9, 0.96)], 0.11)


@icon("poi", "gate", T_BONE, "Boss Gate: sealed until enough Seals (an arch with seal sockets)")
def p_gate(c):
    c.poly(Path(0.04, 1.0).L(0.04, 0.46).C(0.04, 0.16, 0.26, 0.0, 0.5, 0.0).C(0.74, 0.0, 0.96, 0.16, 0.96, 0.46).L(0.96, 1.0).pts())
    with c.op("cut"):
        c.poly(Path(0.2, 1.0).L(0.2, 0.5).C(0.2, 0.3, 0.34, 0.2, 0.5, 0.2).C(0.66, 0.2, 0.8, 0.3, 0.8, 0.5).L(0.8, 1.0).pts())
    c.poly(Path(0.26, 1.0).L(0.26, 0.52).C(0.26, 0.36, 0.38, 0.27, 0.5, 0.27).C(0.62, 0.27, 0.74, 0.36, 0.74, 0.52).L(0.74, 1.0).pts())
    with c.op("cut"):
        c.rect(0.485, 0.27, 0.515, 1.0)
        for i in range(5):
            a = 180 + (i + 0.5) * 36
            p = polar(0.5, 0.5, 0.39, a)
            c.circle(p[0], p[1] - 0.02, 0.035)
    with c.op("shade"):
        c.rect(0.515, 0.27, 0.74, 1.0)


@icon("poi", "camp", T_BONE, "Camp: crossed spears over embers")
def p_camp(c):
    for flip in (1, -1):
        a = (0.5 - 0.42 * flip, 0.96)
        b = (0.5 + 0.34 * flip, 0.1)
        c.line([a, b], 0.1)
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln
        tip = (b[0] + ux * 0.14, b[1] + uy * 0.14)
        c.poly([tip, (b[0] - uy * 0.07, b[1] + ux * 0.07), (b[0] - ux * 0.04, b[1] - uy * 0.04),
                (b[0] + uy * 0.07, b[1] - ux * 0.07)])
    with c.place(0.5, 0.7, 0.5):
        g_flame(c, core=True)
    c.poly(Path(0.22, 0.98).Q(0.5, 0.86, 0.78, 0.98).pts() + [(0.22, 0.98)])


# ───────────────────────────── currencies ─────────────────────────────
@icon("currency", "godshard", T_BONE, "Godshard: the run's forge currency")
def cu_godshard(c):
    g_shard(c)


@icon("currency", "ember", T_BONE, "Ember: the meta currency (a glowing coal)")
def cu_ember(c):
    body = [(0.12, 0.4), (0.4, 0.16), (0.72, 0.2), (0.96, 0.46), (0.9, 0.82), (0.58, 1.0), (0.2, 0.92), (0.02, 0.66)]
    c.poly(body)
    with c.op("shade"):
        c.poly(body)
    with c.op("unshade"):
        c.line([(0.16, 0.5), (0.36, 0.56), (0.5, 0.48), (0.66, 0.54), (0.88, 0.5)], 0.075)
        c.line([(0.5, 0.48), (0.46, 0.3)], 0.06)
        c.line([(0.36, 0.56), (0.34, 0.78), (0.5, 0.9)], 0.06)
        c.line([(0.66, 0.54), (0.74, 0.76)], 0.06)


@icon("currency", "seal", T_BONE, "Seal: claimed at a POI; enough of them open the Boss Gate (a stamp with an anvil)")
def cu_seal(c):
    seal_ring(c, bumps=14, r=0.5, w=0.5)
    with c.op("cut"):
        c.ring(0.5, 0.5, 0.38, 0.035)
        with c.box(0.24, 0.26, 0.76, 0.74):
            c.poly(ANVIL)


@icon("currency", "forge_charge", T_BONE, "Forge charge: one anvil action while the anvil is Hot (a hammer)")
def cu_forge_charge(c):
    with c.place(0.5, 0.5, 1.0, r=35):
        g_hammer(c)


@icon("currency", "free_action", T_BONE, "Free anvil action (a spark over a hammer)")
def cu_free_action(c):
    with c.place(0.44, 0.56, 0.86, r=35):
        g_hammer(c)
    with c.op("cut"):
        c.circle(0.8, 0.2, 0.24)
    with c.place(0.8, 0.2, 0.4):
        g_spark4(c, 0.14)


@icon("currency", "boon_reroll", T_BONE, "Boon reroll (a die)")
def cu_reroll(c):
    g_die(c)


# ───────────────────────────── statuses ─────────────────────────────
@icon("status", "burn", ELEMENT["flame"], "Burn: Flame damage over time")
def st_burn(c):
    with c.box(0.12, 0.0, 0.88, 0.86):
        g_flame_simple(c, core=True)
    c.poly(Path(0.0, 0.9).Q(0.5, 0.78, 1.0, 0.9).L(1.0, 1.0).Q(0.5, 0.9, 0.0, 1.0).pts())
    with c.place(0.1, 0.46, 0.16):
        g_spark4(c)
    with c.place(0.9, 0.34, 0.14):
        g_spark4(c)


@icon("status", "shock", ELEMENT["storm"], "Shock: stacks discharge Storm damage and stun")
def st_shock(c):
    with c.box(0.22, 0.0, 0.78, 1.0):
        g_bolt(c)
    for side in (-1, 1):
        x = 0.5 + side * 0.38
        c.line([(x - side * 0.02, 0.2), (x + side * 0.1, 0.34), (x - side * 0.02, 0.48), (x + side * 0.08, 0.62)], 0.06)


@icon("status", "curse", ELEMENT["void"], "Curse: the target takes more damage from every source (a hex eye)")
def st_curse(c):
    g_hexeye(c)


@icon("status", "root", T_KIT, "Root: the target cannot move")
def st_root(c):
    g_roots(c)


@icon("status", "bleed", ELEMENT["kinetic"], "Bleed: Kinetic damage over time that ticks harder while moving")
def st_bleed(c):
    g_blood(c)


@icon("status", "mark", T_KIT, "Mark: hits against the target gain crit chance (a crosshair lozenge)")
def st_mark(c):
    g_mark(c)


# ───────────────────────────── states ─────────────────────────────
@icon("states", "stun", T_KIT, "Stunned: stars circling")
def sx_stun(c):
    c.poly(stroke_poly(arcpts(0.5, 0.62, 0.46, 0.2, 200, 340), 0.07) )
    c.poly(stroke_poly(arcpts(0.5, 0.62, 0.46, 0.2, 20, 160), 0.07))
    for x, y, s in ((0.5, 0.2, 0.42), (0.14, 0.52, 0.28), (0.86, 0.52, 0.28)):
        with c.place(x, y, s):
            g_spark4(c, 0.16)
    with c.place(0.5, 0.86, 0.26):
        g_spark4(c, 0.16)


@icon("states", "slow", T_KIT, "Slowed (a snail)")
def sx_slow(c):
    c.poly(Path(0.0, 0.96).L(0.0, 0.84).C(0.1, 0.8, 0.2, 0.78, 0.3, 0.78).L(0.84, 0.78).C(0.9, 0.62, 0.9, 0.46, 0.98, 0.4)
           .L(1.0, 0.5).C(0.98, 0.7, 1.0, 0.86, 0.9, 0.96).pts())
    c.line([(0.9, 0.5), (0.86, 0.26)], 0.04)
    c.line([(0.95, 0.46), (1.02, 0.26)], 0.04)
    c.circle(0.86, 0.25, 0.045)
    c.circle(1.02, 0.25, 0.045)
    c.circle(0.44, 0.48, 0.38)
    with c.op("cut"):
        c.taper(spiral_pts(0.44, 0.48, 0.3, 0.03, 1.25, 90), 0.05, 0.03)


@icon("states", "armor_break", T_STEEL, "Armour broken (a split breastplate)")
def sx_armor_break(c):
    left = [(0.06, 0.06), (0.44, 0.04), (0.38, 0.3), (0.5, 0.46), (0.36, 0.64), (0.44, 0.96), (0.2, 0.86), (0.06, 0.6)]
    c.poly(rot([(x - 0.04, y) for x, y in left], 0.3, 0.5, -6))
    right = [(0.58, 0.04), (0.94, 0.06), (0.94, 0.6), (0.8, 0.86), (0.54, 0.96), (0.46, 0.64), (0.6, 0.46), (0.48, 0.3)]
    c.poly(rot([(x + 0.06, y) for x, y in right], 0.7, 0.5, 6))
    with c.op("shade"):
        c.poly(rot([(x + 0.06, y) for x, y in right], 0.7, 0.5, 6))
    c.poly([(0.47, 0.0), (0.56, 0.08), (0.5, 0.14)])
    c.poly([(0.52, 0.86), (0.6, 0.98), (0.46, 1.0)])


@icon("states", "ward", "#DCE6EA", "Ward: a shield that soaks damage (a hatched ward disc)")
def sx_ward(c):
    c.ring(0.5, 0.5, 0.5, 0.1)
    for i in range(4):
        x = 0.18 + i * 0.2
        c.poly([(x - 0.05, 0.9), (x + 0.03, 0.9), (x + 0.33, 0.1), (x + 0.25, 0.1)])
    with c.op("cut"):
        c.ring(0.5, 0.5, 1.2, 0.72)
        c.ring(0.5, 0.5, 0.41, 0.035)


@icon("states", "taunt", T_KIT, "Taunting: enemies target you (chevrons closing on a crest)")
def sx_taunt(c):
    with c.place(0.5, 0.5, 0.36):
        g_lozenge(c)
    for a in (45, 135, 225, 315):
        with c.place(*polar(0.5, 0.5, 0.36, a), 0.36, r=a - 90):
            g_chevron(c, 0.26)


@icon("states", "doom", T_KIT, "Doom: stacks that burst at a count (an hourglass with a tally)")
def sx_doom(c):
    with c.box(0.0, 0.0, 0.62, 1.0):
        g_hourglass(c)
    for i in range(3):
        y = 0.18 + i * 0.26
        c.rect(0.74, y, 0.98, y + 0.12, r=0.02)
    with c.op("shade"):
        c.rect(0.74, 0.7, 0.98, 0.82)


@icon("states", "downed", T_BONE, "Downed: an ally waits to be revived (a skull)")
def sx_downed(c):
    g_skull(c)


def g_cupped_hand(c):
    c.poly(Path(0.02, 0.5).C(0.12, 0.46, 0.2, 0.52, 0.26, 0.58).L(0.9, 0.58).C(0.98, 0.58, 1.0, 0.66, 0.94, 0.7)
           .L(0.7, 0.76).L(0.96, 0.78).C(1.0, 0.84, 0.96, 0.9, 0.9, 0.9).L(0.62, 0.92).C(0.5, 1.0, 0.3, 1.0, 0.18, 0.94)
           .L(0.02, 0.86).pts())
    with c.op("cut"):
        c.line([(0.66, 0.66), (0.88, 0.64)], 0.03)
        c.line([(0.6, 0.82), (0.86, 0.84)], 0.03)


@icon("states", "tether", "#FFC873", "Soul tether: reviving an ally (a flame held in a hand)")
def sx_tether(c):
    with c.place(0.56, 0.3, 0.56):
        g_flame(c, core=True)
    g_cupped_hand(c)


@icon("states", "reforging", T_KIT, "Reforging: the Forge is rebuilding you (an anvil in a turning ring)")
def sx_reforging(c):
    g_cw_arrow(c, 220, 470, r=0.44, w=0.09)
    with c.place(0.5, 0.54, 0.56):
        g_anvil(c)


@icon("states", "rekindle", T_KIT, "Rekindle: a solo self-revive (a relit candle)")
def sx_rekindle(c):
    g_candle(c)
    with c.place(0.2, 0.18, 0.2):
        g_spark4(c)
    with c.place(0.82, 0.3, 0.16):
        g_spark4(c)


@icon("states", "invulnerable", T_KIT, "Invulnerable (a shield with a star)")
def sx_invulnerable(c):
    g_shield(c)
    with c.op("cut"):
        c.star(0.5, 0.46, 0.3, 0.09, 4)


@icon("states", "infinite_dash", T_KIT, "Infinite dash (a lemniscate)")
def sx_infinite(c):
    pts = []
    for i in range(121):
        t = 2 * math.pi * i / 120
        den = 1 + math.sin(t) ** 2
        pts.append((0.5 + 0.46 * math.cos(t) / den, 0.5 + 0.62 * math.sin(t) * math.cos(t) / den))
    c.line(pts, 0.11)


@icon("states", "forge_aegis", T_KIT, "Forge Aegis: protected while forging (an anvil under a ward dome)")
def sx_forge_aegis(c):
    c.poly(Path(0.0, 0.94).C(0.0, 0.36, 0.22, 0.02, 0.5, 0.02).C(0.78, 0.02, 1.0, 0.36, 1.0, 0.94).L(0.88, 0.94)
           .C(0.88, 0.44, 0.72, 0.14, 0.5, 0.14).C(0.28, 0.14, 0.12, 0.44, 0.12, 0.94).pts())
    with c.box(0.18, 0.4, 0.82, 1.0):
        g_anvil(c)
    c.rect(0.0, 0.9, 1.0, 1.0, r=0.02)


@icon("states", "deadeye", T_KIT, "Deadeye: MANUAL aim precision stacks (an eye in a reticle)")
def sx_deadeye(c):
    with c.box(0.14, 0.26, 0.86, 0.74):
        g_eye(c)
    for a in (0, 90, 180, 270):
        c.line([polar(0.5, 0.5, 0.4, a), polar(0.5, 0.5, 0.52, a)], 0.08, cap=False)
    c.ring(0.5, 0.5, 0.52, 0.06)
    with c.op("cut"):
        for a in (45, 135, 225, 315):
            c.circle(*polar(0.5, 0.5, 0.49, a), 0.1)


def g_overdrive_star(c):
    c.star(0.5, 0.5, 0.5, 0.15, 4)
    c.star(0.5, 0.5, 0.34, 0.14, 4, rot_deg=-45)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.12)
    c.circle(0.5, 0.5, 0.07)


@icon("states", "overdrive_active", T_KIT, "Team Overdrive active (the Overdrive star in a blaze)")
def sx_overdrive_active(c):
    g_burst(c, 12, 0.5, 0.38)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.36)
    with c.place(0.5, 0.5, 0.66):
        g_overdrive_star(c)


@icon("states", "low_hp", T_KIT, "Low health (a cracked heart)")
def sx_low_hp(c):
    g_heart(c)
    with c.op("cut"):
        c.line([(0.5, 0.24), (0.42, 0.42), (0.58, 0.54), (0.46, 0.7), (0.52, 0.94)], 0.06)


# ───────────────────────────── portraits (bust crests) ─────────────────────────────
# Drawn in the unit square of the Ø116 window (the head near (0.5, 0.42)); shoulders run off the
# bottom and are clipped by the window. Each character reads by silhouette alone.

def _shoulders(c, top=0.76, w=0.5, slope=0.1):
    c.poly(Path(0.5 - w * 0.3, top).L(0.5 + w * 0.3, top).C(0.5 + w * 0.8, top + slope * 0.4, 0.5 + w, top + slope, 0.5 + w + 0.1, 1.2)
           .L(0.5 - w - 0.1, 1.2).C(0.5 - w, top + slope, 0.5 - w * 0.8, top + slope * 0.4, 0.5 - w * 0.3, top).pts())


def b_valdris(c):
    c.ellipse(0.13, 0.92, 0.3, 0.2)
    c.ellipse(0.87, 0.92, 0.3, 0.2)
    c.rect(0.2, 0.82, 0.8, 1.2)
    with c.op("shade"):
        c.ellipse(0.13, 1.02, 0.3, 0.12)
        c.ellipse(0.87, 1.02, 0.3, 0.12)
    with c.op("cut"):
        c.arc(0.13, 0.98, 0.26, 200, 330, 0.03)
        c.arc(0.87, 0.98, 0.26, 210, 340, 0.03)
    c.poly([(0.34, 0.62), (0.66, 0.62), (0.73, 0.86), (0.27, 0.86)])
    with c.op("cut"):
        c.rect(0.3, 0.74, 0.7, 0.765)
    # great helm
    c.poly(Path(0.3, 0.4).C(0.3, 0.2, 0.4, 0.14, 0.5, 0.14).C(0.6, 0.14, 0.7, 0.2, 0.7, 0.4).L(0.68, 0.66)
           .L(0.5, 0.72).L(0.32, 0.66).pts())
    c.bez((0.34, 0.38), (0.14, 0.38), (0.06, 0.26), (0.1, 0.04), 0.12, 0.014)
    c.bez((0.66, 0.38), (0.86, 0.38), (0.94, 0.26), (0.9, 0.04), 0.12, 0.014)
    with c.op("cut"):
        c.poly([(0.33, 0.43), (0.67, 0.43), (0.64, 0.48), (0.36, 0.48)])
        for x in (0.44, 0.5, 0.56):
            c.rect(x - 0.012, 0.54, x + 0.012, 0.64)
        c.rect(0.488, 0.15, 0.512, 0.42)
    with c.op("shade"):
        c.poly([(0.5, 0.14), (0.6, 0.14), (0.7, 0.2), (0.7, 0.4), (0.68, 0.66), (0.5, 0.72)])


def b_selene(c):
    _shoulders(c, 0.76, 0.34, 0.12)
    c.rect(0.44, 0.58, 0.56, 0.8)
    # hair mass behind, flowing to the right
    c.poly(Path(0.34, 0.4).C(0.32, 0.22, 0.44, 0.18, 0.54, 0.2).C(0.72, 0.22, 0.78, 0.4, 0.84, 0.58).C(0.9, 0.74, 0.98, 0.82, 1.02, 0.9)
           .C(0.86, 0.9, 0.74, 0.8, 0.66, 0.66).L(0.36, 0.6).pts())
    with c.op("shade"):
        c.poly(Path(0.66, 0.4).C(0.76, 0.5, 0.84, 0.66, 1.02, 0.9).C(0.86, 0.9, 0.74, 0.8, 0.66, 0.66).pts())
    c.ellipse(0.49, 0.46, 0.14, 0.18)
    # circlet with a bolt point
    with c.op("cut"):
        c.arc(0.49, 0.5, 0.155, 200, 340, 0.03)
    c.poly([(0.49, 0.2), (0.535, 0.3), (0.49, 0.345), (0.445, 0.3)])
    # storm orb
    c.circle(0.16, 0.34, 0.11)
    with c.op("cut"):
        c.ring(0.16, 0.34, 0.075, 0.025)
    c.line([(0.1, 0.2), (0.16, 0.12), (0.13, 0.1), (0.2, 0.02)], 0.022)


def b_kael(c):
    c.poly(Path(0.0, 1.2).L(0.04, 0.88).C(0.14, 0.78, 0.28, 0.74, 0.4, 0.72).L(0.6, 0.72).C(0.72, 0.74, 0.86, 0.78, 0.96, 0.88).L(1.0, 1.2).pts())
    c.poly(Path(0.5, 0.08).C(0.62, 0.18, 0.76, 0.34, 0.76, 0.56).L(0.74, 0.8).L(0.26, 0.8).L(0.24, 0.56)
           .C(0.24, 0.34, 0.38, 0.18, 0.5, 0.08).pts())
    with c.op("cut"):
        c.poly(Path(0.5, 0.28).C(0.62, 0.3, 0.66, 0.44, 0.64, 0.62).L(0.36, 0.62).C(0.34, 0.44, 0.38, 0.3, 0.5, 0.28).pts())
    c.poly([(0.36, 0.56), (0.64, 0.56), (0.66, 0.66), (0.5, 0.72), (0.34, 0.66)])
    c.poly([(0.4, 0.46), (0.47, 0.43), (0.46, 0.48)])
    c.poly([(0.6, 0.46), (0.53, 0.43), (0.54, 0.48)])
    with c.op("shade"):
        c.poly(Path(0.5, 0.08).C(0.62, 0.18, 0.76, 0.34, 0.76, 0.56).L(0.74, 0.8).L(0.64, 0.8).L(0.66, 0.4).pts())
    # pistol grip over the shoulder
    c.poly(rot([(0.78, 0.66), (0.98, 0.66), (0.98, 0.72), (0.84, 0.74), (0.82, 0.84), (0.76, 0.84)], 0.8, 0.7, -18))


def b_thessaly(c):
    _shoulders(c, 0.8, 0.36, 0.1)
    # shawl hem
    with c.op("shade"):
        c.poly([(0.1, 1.2), (0.14, 0.92), (0.3, 0.84), (0.5, 0.96), (0.7, 0.84), (0.86, 0.92), (0.9, 1.2)])
    c.ellipse(0.5, 0.56, 0.13, 0.16)
    # wide-brimmed pointed hat, tip bent back
    c.poly(Path(0.34, 0.4).L(0.44, 0.18).C(0.5, 0.06, 0.62, 0.0, 0.8, 0.04).C(0.68, 0.08, 0.62, 0.16, 0.62, 0.26).L(0.68, 0.4).pts())
    c.ellipse(0.5, 0.42, 0.42, 0.075)
    with c.op("cut"):
        c.rect(0.36, 0.34, 0.66, 0.37)
    # veil over the lower face
    c.poly(Path(0.34, 0.5).L(0.66, 0.5).L(0.64, 0.72).L(0.58, 0.68).L(0.54, 0.74).L(0.5, 0.69).L(0.46, 0.74)
           .L(0.42, 0.68).L(0.36, 0.72).pts())
    with c.op("shade"):
        c.poly([(0.36, 0.49), (0.64, 0.49), (0.64, 0.53), (0.36, 0.53)])
    c.circle(0.44, 0.47, 0.018)
    c.circle(0.56, 0.47, 0.018)
    # spindle
    c.line([(0.9, 0.2), (0.88, 0.96)], 0.035)
    c.poly([(0.895, 0.22), (0.945, 0.36), (0.89, 0.52), (0.84, 0.36)])
    c.ellipse(0.885, 0.62, 0.07, 0.03)


def b_brax(c):
    # traps sloping from the ears to broad shoulders
    c.poly(Path(-0.1, 1.2).L(-0.08, 0.84).C(0.06, 0.74, 0.2, 0.66, 0.3, 0.5).L(0.7, 0.5).C(0.8, 0.66, 0.94, 0.74, 1.08, 0.84)
           .L(1.1, 1.2).pts())
    with c.op("shade"):
        c.poly(Path(0.5, 0.5).L(0.7, 0.5).C(0.8, 0.66, 0.94, 0.74, 1.08, 0.84).L(1.1, 1.2).L(0.5, 1.2).pts())
    # a broad bald head
    c.poly(Path(0.3, 0.46).C(0.28, 0.24, 0.38, 0.16, 0.5, 0.16).C(0.62, 0.16, 0.72, 0.24, 0.7, 0.46).L(0.66, 0.52).L(0.34, 0.52).pts())
    with c.op("shade"):
        c.poly([(0.31, 0.3), (0.69, 0.3), (0.68, 0.36), (0.32, 0.36)])
    with c.op("cut"):
        c.poly([(0.36, 0.37), (0.47, 0.39), (0.46, 0.42), (0.37, 0.41)])
        c.poly([(0.64, 0.37), (0.53, 0.39), (0.54, 0.42), (0.63, 0.41)])
    # the furnace-grate jaw
    c.poly([(0.28, 0.46), (0.72, 0.46), (0.68, 0.7), (0.5, 0.76), (0.32, 0.7)])
    with c.op("cut"):
        for x in (0.39, 0.465, 0.535, 0.61):
            c.rect(x - 0.016, 0.52, x + 0.016, 0.66)
    c.circle(0.24, 0.44, 0.05)
    c.circle(0.76, 0.44, 0.05)


def b_ossian(c):
    _shoulders(c, 0.78, 0.38, 0.1)
    with c.op("shade"):
        c.poly([(0.5, 0.78), (0.9, 0.86), (1.0, 1.2), (0.5, 1.2)])
    c.poly(Path(0.5, 0.2).C(0.68, 0.2, 0.74, 0.36, 0.74, 0.52).L(0.72, 0.8).L(0.28, 0.8).L(0.26, 0.52)
           .C(0.26, 0.36, 0.32, 0.2, 0.5, 0.2).pts())
    with c.op("cut"):
        c.ellipse(0.5, 0.54, 0.14, 0.16)
    c.poly([(0.38, 0.62), (0.62, 0.62), (0.58, 0.72), (0.42, 0.72)])
    c.circle(0.56, 0.5, 0.022)
    # antlers
    for sgn in (-1, 1):
        x = lambda v: 0.5 + sgn * (v - 0.5)
        c.bez((x(0.62), 0.26), (x(0.7), 0.14), (x(0.8), 0.08), (x(0.84), -0.06), 0.06, 0.02)
        c.bez((x(0.72), 0.14), (x(0.8), 0.14), (x(0.9), 0.12), (x(0.96), 0.04), 0.045, 0.015)
        c.bez((x(0.66), 0.2), (x(0.66), 0.1), (x(0.64), 0.04), (x(0.66), -0.02), 0.04, 0.015)
    # bow limb over the shoulder
    c.arc(0.1, 0.6, 0.36, 290, 370, 0.035)


def b_mirren(c):
    c.poly(Path(0.0, 1.2).L(0.04, 0.86).L(0.3, 0.72).L(0.36, 0.84).L(0.5, 0.78).L(0.64, 0.84).L(0.7, 0.72).L(0.96, 0.86)
           .L(1.0, 1.2).pts())
    c.rect(0.44, 0.6, 0.56, 0.8)
    # bob of hair
    c.poly(Path(0.3, 0.62).C(0.26, 0.4, 0.3, 0.24, 0.5, 0.24).C(0.7, 0.24, 0.74, 0.4, 0.7, 0.62).L(0.62, 0.6).L(0.38, 0.6).pts())
    c.ellipse(0.5, 0.5, 0.14, 0.16)
    # fox mask with tall ears
    mask = Path(0.33, 0.44).L(0.3, 0.14).L(0.44, 0.32).L(0.56, 0.32).L(0.7, 0.14).L(0.67, 0.44).C(0.64, 0.52, 0.56, 0.56, 0.5, 0.62)
    mask.C(0.44, 0.56, 0.36, 0.52, 0.33, 0.44)
    c.poly(mask.pts())
    with c.op("cut"):
        c.poly([(0.38, 0.42), (0.47, 0.44), (0.45, 0.48), (0.4, 0.47)])
        c.poly([(0.62, 0.42), (0.53, 0.44), (0.55, 0.48), (0.6, 0.47)])
    with c.op("shade"):
        c.poly([(0.33, 0.3), (0.31, 0.19), (0.39, 0.29)])
        c.poly([(0.67, 0.3), (0.69, 0.19), (0.61, 0.29)])
    # coin earring
    c.line([(0.36, 0.6), (0.34, 0.68)], 0.02)
    c.circle(0.34, 0.72, 0.045)
    with c.op("cut"):
        c.circle(0.34, 0.72, 0.018)


def b_epoch(c):
    # clock halo behind the head
    c.ring(0.5, 0.42, 0.34, 0.05)
    for i in range(12):
        a = i * 30
        c.line([polar(0.5, 0.42, 0.34, a), polar(0.5, 0.42, 0.42 if i % 3 == 0 else 0.39, a)], 0.035 if i % 3 == 0 else 0.022, cap=False)
    _shoulders(c, 0.78, 0.34, 0.12)
    c.poly([(0.36, 0.7), (0.64, 0.7), (0.7, 0.82), (0.3, 0.82)])  # high collar
    with c.op("shade"):
        c.poly([(0.36, 0.7), (0.64, 0.7), (0.7, 0.82), (0.3, 0.82)])
    c.rect(0.44, 0.58, 0.56, 0.74)
    c.ellipse(0.5, 0.46, 0.13, 0.16)
    # crown of clock hands
    c.poly([(0.36, 0.34), (0.64, 0.34), (0.62, 0.28), (0.38, 0.28)])
    c.poly([(0.47, 0.29), (0.5, 0.08), (0.53, 0.29)])
    c.poly([(0.41, 0.29), (0.34, 0.14), (0.45, 0.29)])
    c.poly([(0.59, 0.29), (0.66, 0.14), (0.55, 0.29)])
    c.circle(0.5, 0.1, 0.03)
    with c.op("cut"):
        c.poly([(0.42, 0.44), (0.47, 0.45), (0.42, 0.46)])
        c.poly([(0.58, 0.44), (0.53, 0.45), (0.58, 0.46)])


def b_fenra(c):
    # fur mantle
    pts = [(-0.1, 1.2), (-0.06, 0.86)]
    for i in range(9):
        x = 0.02 + i * 0.12
        pts += [(x, 0.72 + (0.06 if i % 2 else 0.0)), (x + 0.06, 0.8)]
    pts += [(1.06, 0.86), (1.1, 1.2)]
    c.poly(pts)
    c.rect(0.44, 0.58, 0.56, 0.78)
    c.ellipse(0.5, 0.52, 0.13, 0.15)
    # braids
    for x in (0.34, 0.66):
        for i in range(4):
            c.ellipse(x, 0.56 + i * 0.07, 0.035, 0.04)
    # wolf pelt: skull-cap head with ears and an upper jaw over the brow
    c.poly(Path(0.28, 0.46).C(0.26, 0.26, 0.36, 0.16, 0.5, 0.16).C(0.64, 0.16, 0.74, 0.26, 0.72, 0.46).L(0.62, 0.42)
           .L(0.5, 0.48).L(0.38, 0.42).pts())
    c.poly([(0.3, 0.3), (0.26, 0.02), (0.44, 0.18)])
    c.poly([(0.7, 0.3), (0.74, 0.02), (0.56, 0.18)])
    with c.op("shade"):
        c.poly([(0.31, 0.24), (0.29, 0.1), (0.38, 0.19)])
        c.poly([(0.69, 0.24), (0.71, 0.1), (0.62, 0.19)])
    for x in (0.4, 0.6):
        c.poly([(x - 0.03, 0.42), (x + 0.03, 0.42), (x, 0.52)])
    with c.op("cut"):
        c.poly([(0.36, 0.3), (0.44, 0.32), (0.42, 0.35)])
        c.poly([(0.64, 0.3), (0.56, 0.32), (0.58, 0.35)])


def b_lyra(c):
    _shoulders(c, 0.8, 0.34, 0.12)
    with c.op("shade"):
        c.poly([(0.22, 0.82), (0.32, 0.8), (0.82, 1.2), (0.62, 1.2)])
    # long hair (shaded) framing a lit face
    hair = (Path(0.3, 0.4).C(0.3, 0.2, 0.4, 0.14, 0.5, 0.14).C(0.6, 0.14, 0.7, 0.2, 0.7, 0.4).C(0.72, 0.62, 0.78, 0.8, 0.84, 0.98)
            .L(0.62, 0.9).L(0.38, 0.9).L(0.16, 0.98).C(0.22, 0.8, 0.28, 0.62, 0.3, 0.4).pts())
    c.poly(hair)
    with c.op("shade"):
        c.poly(hair)
    with c.op("unshade"):
        c.ellipse(0.5, 0.48, 0.125, 0.16)
        c.rect(0.45, 0.6, 0.55, 0.8)
    with c.op("cut"):
        c.ring(0.5, 0.48, 0.14, 0.02)
        c.poly([(0.42, 0.46), (0.47, 0.47), (0.42, 0.48)])
        c.poly([(0.58, 0.46), (0.53, 0.47), (0.58, 0.48)])
    # laurel wreath
    for i in range(8):
        a = 196 + i * 21
        p = polar(0.5, 0.44, 0.21, a)
        c.ellipse(p[0], p[1], 0.055, 0.024, r=a + 90 + (28 if i < 4 else -28))
        with c.op("unshade"):
            c.ellipse(p[0], p[1], 0.055, 0.024, r=a + 90 + (28 if i < 4 else -28))
    with c.place(0.86, 0.7, 0.28):
        g_lyre(c)


def b_vex(c):
    c.poly(Path(0.0, 1.2).L(0.04, 0.86).C(0.14, 0.78, 0.26, 0.74, 0.34, 0.72).L(0.66, 0.72).C(0.74, 0.74, 0.86, 0.78, 0.96, 0.86)
           .L(1.0, 1.2).pts())
    # standing collar
    c.poly([(0.26, 0.86), (0.22, 0.52), (0.34, 0.64), (0.66, 0.64), (0.78, 0.52), (0.74, 0.86)])
    with c.op("shade"):
        c.poly([(0.26, 0.86), (0.22, 0.52), (0.34, 0.64), (0.36, 0.86)])
        c.poly([(0.74, 0.86), (0.78, 0.52), (0.66, 0.64), (0.64, 0.86)])
    # hood
    c.poly(Path(0.5, 0.14).C(0.66, 0.14, 0.72, 0.28, 0.72, 0.44).L(0.68, 0.66).L(0.32, 0.66).L(0.28, 0.44)
           .C(0.28, 0.28, 0.34, 0.14, 0.5, 0.14).pts())
    # goggles and beak
    with c.op("cut"):
        c.ring(0.41, 0.42, 0.075, 0.03)
        c.ring(0.59, 0.42, 0.075, 0.03)
        c.rect(0.47, 0.41, 0.53, 0.43)
    c.poly(Path(0.42, 0.5).L(0.58, 0.5).C(0.58, 0.64, 0.54, 0.76, 0.5, 0.88).C(0.46, 0.76, 0.42, 0.64, 0.42, 0.5).pts())
    with c.op("shade"):
        c.poly(Path(0.5, 0.5).L(0.58, 0.5).C(0.58, 0.64, 0.54, 0.76, 0.5, 0.88).pts())
    # flask on the chest strap
    c.line([(0.2, 0.8), (0.8, 1.1)], 0.03)
    with c.place(0.74, 0.94, 0.16):
        g_flask(c)


def b_seraph(c):
    c.ring(0.5, 0.1, 0.13, 0.04)
    c.ellipse(0.16, 0.9, 0.24, 0.16)
    c.ellipse(0.84, 0.9, 0.24, 0.16)
    _shoulders(c, 0.76, 0.34, 0.12)
    with c.op("shade"):
        c.poly([(0.4, 0.8), (0.6, 0.8), (0.58, 1.2), (0.42, 1.2)])
    c.poly([(0.36, 0.62), (0.64, 0.62), (0.68, 0.82), (0.32, 0.82)])
    # rounded helm with a T-visor
    c.poly(Path(0.33, 0.44).C(0.33, 0.28, 0.4, 0.22, 0.5, 0.22).C(0.6, 0.22, 0.67, 0.28, 0.67, 0.44).L(0.65, 0.66)
           .L(0.5, 0.72).L(0.35, 0.66).pts())
    with c.op("cut"):
        c.rect(0.37, 0.42, 0.63, 0.46)
        c.rect(0.48, 0.42, 0.52, 0.62)
    # helm wings
    for sgn in (-1, 1):
        x = lambda v: 0.5 + sgn * (v - 0.5)
        for i, (y0, ln) in enumerate(((0.36, 0.3), (0.42, 0.24), (0.48, 0.17))):
            c.bez((x(0.66), y0), (x(0.78), y0 - 0.02), (x(0.84), y0 - 0.1), (x(0.66 + ln), y0 - 0.2 + i * 0.04), 0.06, 0.012)


def g_lyre(c):
    c.bez((0.3, 0.9), (0.12, 0.7), (0.06, 0.4), (0.2, 0.08), 0.11, 0.06)
    c.bez((0.7, 0.9), (0.88, 0.7), (0.94, 0.4), (0.8, 0.08), 0.11, 0.06)
    c.rect(0.14, 0.18, 0.86, 0.26, r=0.03)
    c.rect(0.26, 0.84, 0.74, 0.96, r=0.04)
    for x in (0.38, 0.5, 0.62):
        c.line([(x, 0.24), (x, 0.86)], 0.035, cap=False)


PORTRAITS = {"valdris": b_valdris, "selene": b_selene, "kael": b_kael, "thessaly": b_thessaly, "brax": b_brax,
             "ossian": b_ossian, "mirren": b_mirren, "epoch": b_epoch, "fenra": b_fenra, "lyra": b_lyra, "vex": b_vex,
             "seraph": b_seraph}
PORTRAIT_NOTES = {"valdris": "horned great-helm and pauldrons", "selene": "circlet, flowing hair and a storm orb",
                  "kael": "pointed hood, masked face and eye glints", "thessaly": "wide-brimmed witch hat, veil and spindle",
                  "brax": "bull neck, bald head and a furnace-grate jaw", "ossian": "hooded archer crowned with stag antlers",
                  "mirren": "fox mask with tall ears and a coin earring", "epoch": "clock halo and a crown of clock hands",
                  "fenra": "wolf-pelt headdress, braids and a fur mantle", "lyra": "laurel wreath, long hair and a small lyre",
                  "vex": "goggled beak mask, hood and standing collar", "seraph": "winged helm with a T-visor and a halo"}


# ───────────────────────────── kits (Q, E, R, passive) ─────────────────────────────
def k_valdris_q(c):  # Bulwark Slam: a fist into the ground raising a barricade
    with c.place(0.5, 0.26, 0.5, r=180):
        g_fist(c)
    c.rect(0.02, 0.62, 0.98, 0.7, r=0.02)
    for x in (0.08, 0.36, 0.64):
        c.rect(x, 0.72, x + 0.28, 0.98, r=0.02)
    with c.op("shade"):
        c.rect(0.02, 0.86, 0.98, 0.98)
    for a, ln in ((200, 0.16), (225, 0.12), (315, 0.12), (340, 0.16)):
        p0 = polar(0.5, 0.6, 0.3, a)
        c.line([p0, polar(0.5, 0.6, 0.3 + ln, a)], 0.06)


def k_valdris_e(c):  # Siege Stance: a planted tower shield with rising chevrons
    with c.box(0.14, 0.0, 0.86, 0.86):
        g_tower_shield(c)
    with c.op("cut"):
        for y in (0.2, 0.44):
            c.poly([(0.3, y + 0.14), (0.5, y), (0.7, y + 0.14), (0.7, y + 0.22), (0.5, y + 0.08), (0.3, y + 0.22)])
    c.rect(0.0, 0.9, 1.0, 0.98, r=0.02)
    for x in (0.08, 0.92):
        c.poly([(x - 0.05, 0.9), (x + 0.05, 0.9), (x, 0.72)])


def k_valdris_r(c):  # Mountainfall: a peak crowned by an anvil, a boulder falling
    with c.box(0.0, 0.36, 1.0, 1.0):
        g_mountain(c)
    with c.place(0.64, 0.3, 0.44):
        g_anvil(c, band=False)
    with c.place(0.18, 0.16, 0.26):
        g_boulder(c)
    c.line([(0.3, 0.02), (0.36, 0.08)], 0.04)
    c.line([(0.36, 0.14), (0.44, 0.2)], 0.04)


def k_valdris_p(c):  # Reforged Flesh: armour plates over a heart
    g_heart(c)
    with c.op("cut"):
        c.rect(0.0, 0.37, 1.0, 0.42)
        c.rect(0.0, 0.57, 1.0, 0.62)
    with c.op("shade"):
        c.rect(0.0, 0.42, 1.0, 0.57)


def k_selene_q(c):  # Arc Nova: a ring of branching bolts
    c.circle(0.5, 0.5, 0.16)
    c.ring(0.5, 0.5, 0.3, 0.06)
    for i in range(6):
        a = -90 + i * 60
        with c.place(*polar(0.5, 0.5, 0.39, a), 0.24, r=a + 90):
            c.poly([(0.55, 0.0), (0.2, 0.55), (0.45, 0.55), (0.35, 1.0), (0.8, 0.42), (0.55, 0.42), (0.72, 0.0)])


def k_selene_e(c):  # Blink: a dissolving figure trailing a bolt
    with c.box(0.46, 0.0, 1.0, 1.0):
        g_figure(c)
    for x, y, s in ((0.36, 0.2, 0.1), (0.3, 0.42, 0.08), (0.38, 0.62, 0.09), (0.22, 0.3, 0.06), (0.2, 0.54, 0.05), (0.26, 0.76, 0.06)):
        c.poly([(x, y - s), (x + s, y), (x, y + s), (x - s, y)])
    with c.place(0.1, 0.5, 0.36, r=-10):
        g_bolt(c)


def k_selene_r(c):  # Heaven's Verdict: a storm cloud over three bolts
    with c.box(0.0, 0.0, 1.0, 0.56):
        g_cloud(c)
    with c.op("shade"):
        c.rect(0.1, 0.44, 0.9, 0.5)
    for x in (0.24, 0.5, 0.76):
        with c.place(x, 0.74, 0.36):
            g_bolt(c)


def k_selene_p(c):  # Static Charge: a bolt inside a charging ring
    c.arc(0.5, 0.5, 0.46, -90, 180, 0.12)
    with c.op("cut"):
        for a in (-45, 0, 45, 90, 135):
            c.poly(stroke_poly([polar(0.5, 0.5, 0.38, a), polar(0.5, 0.5, 0.54, a)], 0.03))
    with c.place(0.5, 0.5, 0.56):
        g_bolt(c)


def g_figure(c):
    """A standing figure in a cloak (used for blinks and decoys)."""
    c.circle(0.5, 0.14, 0.13)
    c.poly(Path(0.5, 0.28).C(0.72, 0.28, 0.8, 0.44, 0.84, 0.62).L(0.94, 1.0).L(0.06, 1.0).L(0.16, 0.62)
           .C(0.2, 0.44, 0.28, 0.28, 0.5, 0.28).pts())
    with c.op("shade"):
        c.poly(Path(0.5, 0.28).C(0.72, 0.28, 0.8, 0.44, 0.84, 0.62).L(0.94, 1.0).L(0.56, 1.0).pts())


def k_kael_q(c):  # Fan of Blades: three fanned blades from one grip
    for a in (-34, 0, 34):
        with c.at(0.5, 0.94, r=a):
            c.poly([(0.0, 0.0), (-0.085, -0.2), (-0.075, -0.62), (0.0, -0.9), (0.075, -0.62), (0.085, -0.2)])
            with c.op("shade"):
                c.poly([(0.0, 0.0), (0.0, -0.9), (0.075, -0.62), (0.085, -0.2)])
    c.circle(0.5, 0.92, 0.1)
    with c.op("cut"):
        c.circle(0.5, 0.92, 0.035)


def k_kael_e(c):  # Shadow Roll: a crescent with afterimages
    with c.place(0.64, 0.5, 0.72):
        g_crescent(c, -0.22, -0.1, 0.47, 0.38)
    for x, s in ((0.3, 0.5), (0.12, 0.34)):
        with c.place(x, 0.5, s):
            with c.op("add"):
                g_crescent(c, -0.22, -0.1, 0.47, 0.38)
    with c.op("shade"):
        c.rect(0.0, 0.0, 0.34, 1.0)
    for y in (0.14, 0.86):
        c.line([(0.34, y), (0.64, y)], 0.05)


def g_pistol(c):
    """A long-barrelled pistol pointing right."""
    c.rect(0.28, 0.24, 1.0, 0.38, r=0.02)
    c.rect(0.16, 0.2, 0.48, 0.46, r=0.04)
    c.poly(Path(0.18, 0.4).L(0.4, 0.44).C(0.34, 0.6, 0.3, 0.76, 0.26, 0.96).L(0.02, 0.96).C(0.08, 0.76, 0.14, 0.56, 0.18, 0.4).pts())
    c.arc(0.46, 0.48, 0.1, 0, 150, 0.04)
    c.poly([(0.16, 0.22), (0.1, 0.1), (0.22, 0.2)])
    with c.op("shade"):
        c.rect(0.48, 0.32, 1.0, 0.38)
        c.poly(Path(0.28, 0.6).C(0.26, 0.76, 0.24, 0.86, 0.22, 0.96).L(0.02, 0.96).C(0.04, 0.9, 0.06, 0.8, 0.08, 0.72).pts())


def k_kael_r(c):  # Bullet Ballet: twin spectral pistols spinning back to back
    with c.place(0.58, 0.34, 0.62):
        g_pistol(c)
    with c.place(0.42, 0.68, 0.62, sx=-1):
        g_pistol(c)
    c.arc(0.5, 0.5, 0.5, 190, 300, 0.07, 0.01)
    c.arc(0.5, 0.5, 0.5, 10, 120, 0.07, 0.01)


def k_kael_p(c):  # Ghost Step: a footprint with a ghost trail
    with c.place(0.62, 0.52, 0.8, r=12):
        g_footprint(c)
    for i, y in enumerate((0.3, 0.55, 0.8)):
        c.bez((0.02, y + 0.06), (0.12, y - 0.06), (0.2, y + 0.06), (0.3 - i * 0.02, y), 0.06, 0.02)


def k_thessaly_q(c):  # Forge Turret: a tripod turret
    g_turret(c)
    with c.place(0.86, 0.1, 0.2):
        g_spark4(c)


def k_thessaly_e(c):  # Binding Hex: a rune circle bound with a chain
    c.ring(0.5, 0.5, 0.46, 0.09)
    with c.place(0.5, 0.5, 0.5):
        g_hexeye(c)
    with c.op("cut"):
        c.poly(stroke_poly([(0.02, 0.98), (0.98, 0.02)], 0.24))
    for i in range(5):
        t = 0.1 + i * 0.2
        with c.place(t, 1.0 - t, 0.26, r=45 + 90 * (i % 2)):
            g_chain_link(c, 0.15)


def k_thessaly_r(c):  # Sabbath of Sparks: a candle inside a ring of sparks
    with c.place(0.5, 0.56, 0.52):
        g_candle(c)
    for i in range(8):
        a = -90 + i * 45
        with c.place(*polar(0.5, 0.52, 0.42, a), 0.18 if i % 2 else 0.24):
            g_spark4(c, 0.16)


def g_spindle(c):
    c.line([(0.5, 0.0), (0.5, 1.0)], 0.07)
    c.poly([(0.5, 0.06), (0.66, 0.34), (0.5, 0.62), (0.34, 0.34)])
    with c.op("cut"):
        for y in (0.22, 0.3, 0.38, 0.46):
            c.line([(0.38, y + 0.02), (0.62, y - 0.02)], 0.02)
    c.ellipse(0.5, 0.78, 0.2, 0.06)


def k_thessaly_p(c):  # Curse Weaver: a spindle with a hex eye
    with c.box(0.52, 0.0, 1.02, 1.0):
        g_spindle(c)
    with c.place(0.3, 0.46, 0.56):
        g_hexeye(c)


def g_geyser(c):
    """A flame geyser column rising from a crack."""
    c.poly(Path(0.3, 1.0).C(0.36, 0.7, 0.26, 0.5, 0.36, 0.28).L(0.5, 0.0).L(0.64, 0.28).C(0.74, 0.5, 0.64, 0.7, 0.7, 1.0).pts())
    with c.op("cut"):
        c.poly(teardrop_pts(0.5, 0.94, 0.08, 0.5, 0.0))


def k_brax_q(c):  # Cinder Uppercut: a rising fist over a flame geyser
    with c.place(0.5, 0.3, 0.6):
        g_fist(c)
    with c.box(0.18, 0.54, 0.82, 1.0):
        g_flame(c)


def k_brax_e(c):  # Furnace Rush: a shoulder charge with drag lines
    c.poly(Path(0.36, 0.1).C(0.66, 0.06, 0.94, 0.2, 0.98, 0.5).C(0.94, 0.8, 0.66, 0.94, 0.36, 0.9).L(0.46, 0.5).pts())
    with c.op("shade"):
        c.poly(Path(0.46, 0.5).L(0.98, 0.5).C(0.94, 0.8, 0.66, 0.94, 0.36, 0.9).pts())
    with c.op("cut"):
        c.arc(0.5, 0.5, 0.36, -70, 70, 0.04)
    for i, y in enumerate((0.24, 0.5, 0.76)):
        c.line([(0.02 + (0.08 if i != 1 else 0.0), y), (0.34, y)], 0.07)


def k_brax_r(c):  # Meltdown: dripping molten fists
    for x in (0.28, 0.72):
        with c.place(x, 0.36, 0.48):
            g_fist(c)
    for x, h in ((0.14, 0.2), (0.3, 0.28), (0.52, 0.2), (0.7, 0.3), (0.86, 0.22)):
        c.poly(teardrop_pts(x, 0.64 + h + 0.04, 0.045, h, 0.0)[::-1])
        c.rect(x - 0.03, 0.58, x + 0.03, 0.64 + h * 0.5)


def k_brax_p(c):  # Heat Gauge: a flame thermometer
    c.rect(0.4, 0.04, 0.6, 0.72, r=0.1)
    c.circle(0.5, 0.8, 0.2)
    with c.op("cut"):
        c.rect(0.46, 0.12, 0.54, 0.66, r=0.04)
    c.rect(0.465, 0.36, 0.535, 0.7)
    with c.op("cut"):
        c.poly(teardrop_pts(0.5, 0.92, 0.09, 0.26, 0.02))
    for y in (0.2, 0.32, 0.44, 0.56):
        c.line([(0.66, y), (0.8, y)], 0.04, cap=False)
    with c.place(0.2, 0.3, 0.3):
        g_flame_simple(c)


def k_ossian_q(c):  # Piercing Comet: a comet through a wall
    c.rect(0.4, 0.04, 0.6, 0.96, r=0.02)
    with c.op("cut"):
        for y in (0.28, 0.52, 0.76):
            c.rect(0.4, y - 0.015, 0.6, y + 0.015)
        c.circle(0.5, 0.5, 0.16)
    c.circle(0.8, 0.5, 0.17)
    c.poly([polar(0.8, 0.5, 0.17, 90), (0.0, 0.5), polar(0.8, 0.5, 0.17, 270)])
    with c.op("cut"):
        c.line([(0.12, 0.46), (0.4, 0.4)], 0.025)
        c.line([(0.12, 0.54), (0.4, 0.6)], 0.025)


def k_ossian_e(c):  # Skyhook Mortar: an arcing shell splitting into bomblets
    pts = arcpts(0.46, 0.86, 0.42, 0.7, 180, 300, 60)
    for i in range(0, len(pts) - 5, 11):
        c.line(pts[i:i + 6], 0.08)
    with c.place(0.74, 0.28, 0.36, r=60):
        g_bullet(c)
    for x, y, r in ((0.72, 0.72, 0.08), (0.86, 0.84, 0.07), (0.96, 0.62, 0.065)):
        c.circle(x, y, r)
    c.rect(0.0, 0.94, 1.0, 1.0, r=0.02)


def k_ossian_r(c):  # Rain of the Hunt: arrows falling on marks
    for x, y in ((0.2, 0.0), (0.5, 0.12), (0.8, 0.0)):
        with c.place(x, y + 0.34, 0.66, r=90):
            g_arrow(c, head=0.3)
    for x in (0.2, 0.5, 0.8):
        with c.place(x, 0.9, 0.2):
            g_lozenge(c, 0.2)


def g_stag_skull(c):
    c.poly(Path(0.36, 0.44).L(0.64, 0.44).L(0.6, 0.8).L(0.54, 0.98).L(0.46, 0.98).L(0.4, 0.8).pts())
    with c.op("cut"):
        c.poly([(0.4, 0.54), (0.48, 0.58), (0.44, 0.64)])
        c.poly([(0.6, 0.54), (0.52, 0.58), (0.56, 0.64)])
    for sgn in (-1, 1):
        x = lambda v: 0.5 + sgn * (v - 0.5)
        c.bez((x(0.6), 0.46), (x(0.72), 0.3), (x(0.8), 0.2), (x(0.84), 0.0), 0.08, 0.02)
        c.bez((x(0.74), 0.26), (x(0.86), 0.26), (x(0.94), 0.2), (x(0.98), 0.1), 0.06, 0.015)
        c.bez((x(0.68), 0.36), (x(0.62), 0.22), (x(0.64), 0.12), (x(0.62), 0.04), 0.05, 0.015)


def k_ossian_p(c):  # Marked Quarry: a reticle on a stag skull
    g_stag_skull(c)
    c.ring(0.5, 0.66, 0.24, 0.045)
    for a in (0, 180):
        c.line([polar(0.5, 0.66, 0.18, a), polar(0.5, 0.66, 0.32, a)], 0.045, cap=False)


def g_fox_mask(c):
    c.poly(Path(0.14, 0.5).L(0.08, 0.0).L(0.36, 0.26).L(0.64, 0.26).L(0.92, 0.0).L(0.86, 0.5).C(0.8, 0.7, 0.62, 0.84, 0.5, 1.0)
           .C(0.38, 0.84, 0.2, 0.7, 0.14, 0.5).pts())
    with c.op("cut"):
        c.poly([(0.22, 0.46), (0.42, 0.5), (0.38, 0.58), (0.26, 0.56)])
        c.poly([(0.78, 0.46), (0.58, 0.5), (0.62, 0.58), (0.74, 0.56)])
    with c.op("shade"):
        c.poly([(0.14, 0.24), (0.12, 0.08), (0.28, 0.22)])
        c.poly([(0.86, 0.24), (0.88, 0.08), (0.72, 0.22)])
        c.poly([(0.44, 0.86), (0.56, 0.86), (0.5, 1.0)])


def k_mirren_q(c):  # Gilded Decoy: a fox mask bursting into coins
    with c.place(0.44, 0.56, 0.72):
        g_fox_mask(c)
    for x, y, r in ((0.86, 0.16, 0.12), (0.92, 0.46, 0.09), (0.66, 0.06, 0.08), (0.1, 0.16, 0.08)):
        with c.place(x, y, r * 2):
            g_coin(c)


def k_mirren_e(c):  # Snatch: a hand closing on a gem
    with c.place(0.5, 0.34, 0.68, r=180):
        g_hand_open(c, spread=9.0)
    with c.place(0.5, 0.84, 0.34):
        g_lozenge(c)
    with c.op("shade"):
        c.poly([(0.5, 0.67), (0.67, 0.84), (0.5, 1.01)])


def k_mirren_r(c):  # Grand Heist: a spilling sack
    c.poly(Path(0.2, 0.34).C(0.02, 0.5, 0.0, 0.9, 0.3, 0.96).L(0.62, 0.96).C(0.86, 0.92, 0.84, 0.6, 0.66, 0.4)
           .L(0.6, 0.3).L(0.28, 0.3).pts())
    c.poly([(0.22, 0.34), (0.16, 0.12), (0.3, 0.22), (0.44, 0.08), (0.52, 0.24), (0.66, 0.14), (0.62, 0.34)])
    with c.op("cut"):
        c.rect(0.22, 0.29, 0.64, 0.33)
    with c.op("shade"):
        c.poly(Path(0.5, 0.4).L(0.66, 0.4).C(0.84, 0.6, 0.86, 0.92, 0.62, 0.96).L(0.5, 0.96).pts())
    for x, y in ((0.82, 0.62), (0.9, 0.84), (0.72, 0.9)):
        with c.place(x, y, 0.2):
            g_coin(c)


def k_mirren_p(c):  # Fortune's Favour: a coin with a fox ear
    with c.place(0.5, 0.58, 0.84):
        g_coin(c, "star")
    c.poly([(0.16, 0.36), (0.14, 0.0), (0.42, 0.2)])
    c.poly([(0.84, 0.36), (0.86, 0.0), (0.58, 0.2)])


def k_epoch_q(c):  # Still Field: a bubble of paused motes
    c.ring(0.5, 0.5, 0.5, 0.07)
    c.arc(0.5, 0.5, 0.38, 200, 250, 0.05)
    c.rect(0.36, 0.34, 0.45, 0.66, r=0.02)
    c.rect(0.55, 0.34, 0.64, 0.66, r=0.02)
    for x, y in ((0.24, 0.62), (0.76, 0.3), (0.72, 0.74), (0.3, 0.3)):
        c.circle(x, y, 0.045)


def k_epoch_e(c):  # Rewind Wounds: a counter-clockwise arrow around a heart
    g_ccw_arrow(c, 250, 560, r=0.42, w=0.1)
    with c.place(0.5, 0.52, 0.46):
        g_heart(c)


def k_epoch_r(c):  # Stolen Second: a clock with a missing wedge, the wedge pulled away
    c.circle(0.46, 0.54, 0.46)
    with c.op("cut"):
        c.ring(0.46, 0.54, 0.38, 0.04)
        c.poly([(0.46, 0.54), polar(0.46, 0.54, 0.7, -90), polar(0.46, 0.54, 0.7, -35)])
        c.line([(0.46, 0.54), polar(0.46, 0.54, 0.24, -150)], 0.07)
        c.line([(0.46, 0.54), polar(0.46, 0.54, 0.17, 130)], 0.07)
    off = polar(0, 0, 0.14, -62)
    c.poly([(0.46 + off[0], 0.54 + off[1]), polar(0.46 + off[0], 0.54 + off[1], 0.46, -88),
            polar(0.46 + off[0], 0.54 + off[1], 0.46, -37)])


def k_epoch_p(c):  # Borrowed Time: an hourglass with a stride arrow
    with c.box(0.0, 0.0, 0.56, 1.0):
        g_hourglass(c)
    with c.place(0.78, 0.62, 0.46):
        g_arrow(c, fletch=False, head=0.42, w=0.14)
    c.line([(0.6, 0.36), (0.9, 0.36)], 0.06)


def g_wolf_head(c, open_jaw=False):
    """A wolf head in profile, facing right."""
    p = Path(0.08, 1.0).C(0.08, 0.8, 0.12, 0.54, 0.22, 0.4).L(0.28, 0.04).L(0.44, 0.3).L(0.52, 0.3).L(0.6, 0.36)
    if open_jaw:
        p.L(0.98, 0.42).L(0.98, 0.5).L(0.86, 0.52).L(0.9, 0.56).L(0.78, 0.55).L(0.64, 0.6).L(0.92, 0.74).L(0.9, 0.8)
        p.L(0.6, 0.8)
    else:
        p.L(0.96, 0.46).L(0.98, 0.54).L(0.8, 0.58).L(0.66, 0.6).L(0.86, 0.64).L(0.84, 0.7).L(0.56, 0.78)
    p.C(0.52, 0.86, 0.48, 0.94, 0.46, 1.0)
    c.poly(p.pts())
    with c.op("cut"):
        c.poly([(0.5, 0.4), (0.62, 0.41), (0.54, 0.45)])
    with c.op("shade"):
        c.poly([(0.29, 0.14), (0.4, 0.3), (0.3, 0.34)])
    if open_jaw:
        c.poly([(0.88, 0.5), (0.92, 0.5), (0.9, 0.58)])
        c.poly([(0.8, 0.7), (0.84, 0.69), (0.8, 0.62)])


def k_fenra_p(c):  # Pack Bond: the pup copies your Mechanism (a paw and a gear)
    with c.place(0.42, 0.56, 0.84):
        g_paw(c)
    with c.op("cut"):
        c.circle(0.82, 0.2, 0.22)
    with c.place(0.82, 0.2, 0.36):
        g_gear(c, 6)


def k_fenra_q(c):  # Sic 'Em: the pup pounces
    c.poly(Path(0.0, 0.66).C(0.14, 0.62, 0.22, 0.5, 0.36, 0.44).C(0.46, 0.34, 0.56, 0.3, 0.66, 0.28).L(0.7, 0.14).L(0.76, 0.24)
           .L(0.82, 0.16).L(0.84, 0.28).C(0.9, 0.3, 0.96, 0.34, 1.0, 0.4).L(0.9, 0.44).L(0.94, 0.5).L(0.8, 0.48)
           .C(0.74, 0.56, 0.66, 0.6, 0.6, 0.62).L(0.74, 0.8).L(0.66, 0.84).L(0.5, 0.66).L(0.36, 0.66).L(0.2, 0.84)
           .L(0.12, 0.8).L(0.24, 0.64).C(0.16, 0.7, 0.08, 0.72, 0.0, 0.72).pts())
    with c.op("cut"):
        c.poly([(0.76, 0.32), (0.82, 0.33), (0.78, 0.36)])
    for i, (x, y) in enumerate(((0.8, 0.72), (0.88, 0.66), (0.94, 0.58))):
        c.line([(x, y), (x + 0.06, y + 0.12)], 0.035)


def k_fenra_e(c):  # Den Call: a howl that roots nearby enemies
    with c.box(0.0, 0.08, 0.7, 0.86):
        g_wolf_howl(c)
    for r in (0.12, 0.22):
        c.arc(0.66, 0.1, r, -40, 50, 0.055)
    with c.box(0.6, 0.66, 1.0, 1.0):
        g_roots(c)
    c.rect(0.0, 0.84, 0.62, 0.9, r=0.02)


def k_fenra_r(c):  # Wild Hunt: the pup grows colossal (a snarling wolf head over a small one)
    g_wolf_head(c, open_jaw=True)
    with c.op("cut"):
        c.circle(0.16, 0.86, 0.2)
    with c.place(0.16, 0.86, 0.3):
        g_wolf_head(c)


def g_note(c):
    """An eighth note."""
    c.ellipse(0.32, 0.82, 0.22, 0.15, r=-22)
    c.rect(0.46, 0.08, 0.56, 0.82)
    c.bez((0.51, 0.08), (0.7, 0.2), (0.86, 0.3), (0.8, 0.56), 0.12, 0.04)


def k_lyra_p(c):  # Crescendo: a swelling hairpin under a rising note
    c.poly([(0.0, 0.8), (1.0, 0.62), (1.0, 0.7), (0.08, 0.84), (1.0, 0.98), (1.0, 1.06), (0.0, 0.88)])
    with c.place(0.6, 0.28, 0.56):
        g_note(c)


def k_lyra_q(c):  # Hymn of Haste: a winged note
    with c.place(0.6, 0.5, 0.8):
        g_note(c)
    with c.place(0.2, 0.46, 0.44, sx=-1):
        g_wing(c, 3)


def k_lyra_e(c):  # Dirge: a falling note over a hex eye
    with c.place(0.36, 0.34, 0.64, r=16):
        g_note(c)
    with c.place(0.7, 0.76, 0.5):
        g_hexeye(c)


def k_lyra_r(c):  # Last Chorus: a lyre in ringing arcs
    with c.place(0.5, 0.56, 0.62):
        g_lyre(c)
    for r in (0.34, 0.46):
        c.arc(0.5, 0.56, r, 200, 250, 0.05)
        c.arc(0.5, 0.56, r, 290, 340, 0.05)


def k_vex_p(c):  # Transmute: corpses become bombs (a skull with a lit fuse)
    with c.place(0.44, 0.58, 0.8):
        g_skull(c)
    c.bez((0.6, 0.22), (0.7, 0.08), (0.8, 0.2), (0.86, 0.1), 0.05, 0.04)
    with c.place(0.9, 0.06, 0.2):
        g_spark4(c)


def k_vex_q(c):  # Bottle Toss: a flask arcing to a splash
    for i, (x, y) in enumerate(((0.06, 0.9), (0.14, 0.68), (0.26, 0.5))):
        c.circle(x, y, 0.035 + i * 0.01)
    with c.place(0.6, 0.38, 0.56, r=35):
        g_flask(c)
    for a in (-60, -20, 20):
        c.line([polar(0.82, 1.0, 0.1, a - 90), polar(0.82, 1.0, 0.22, a - 90)], 0.05)


def k_vex_e(c):  # Miasma Step: a dash that leaves a toxic cloud
    with c.box(0.0, 0.38, 0.6, 0.96):
        g_cloud(c)
    with c.op("cut"):
        c.circle(0.24, 0.66, 0.05)
        c.circle(0.42, 0.58, 0.04)
    with c.place(0.74, 0.44, 0.6, r=18):
        g_footprint(c)


def k_vex_r(c):  # Red Death: every corpse detonates (a skull in a burst)
    g_burst(c, 12, 0.5, 0.34)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.33)
    with c.place(0.5, 0.52, 0.5):
        g_skull(c)


def k_seraph_p(c):  # Judgement Marks: the scales and a mark
    with c.box(0.0, 0.1, 0.78, 1.0):
        g_scales(c)
    with c.place(0.84, 0.16, 0.3):
        g_mark(c)


def k_seraph_q(c):  # Aegis: shield allies in a radius (a shield under a ward dome)
    c.arc(0.5, 0.62, 0.48, 190, 350, 0.08)
    with c.place(0.5, 0.64, 0.62):
        g_shield(c, "half")
    c.rect(0.0, 0.94, 1.0, 1.0, r=0.02)


def k_seraph_e(c):  # Smite: a beam of judgement striking the ground
    c.poly([(0.26, 0.0), (0.74, 0.0), (0.56, 0.76), (0.44, 0.76)])
    with c.op("shade"):
        c.poly([(0.5, 0.0), (0.74, 0.0), (0.56, 0.76), (0.5, 0.76)])
    with c.place(0.5, 0.8, 0.54):
        g_burst(c, 8, 0.5, 0.2)
    c.rect(0.0, 0.9, 1.0, 0.97, r=0.02)


def g_gavel(c):
    """A gavel striking down-left."""
    c.rect(0.08, 0.1, 0.62, 0.38, r=0.05)
    with c.op("shade"):
        c.rect(0.08, 0.1, 0.2, 0.38)
        c.rect(0.5, 0.1, 0.62, 0.38)
    c.poly(stroke_poly([(0.35, 0.3), (0.98, 0.98)], 0.1))


def k_seraph_r(c):  # Verdict: mark every enemy on screen
    with c.place(0.46, 0.4, 0.74, r=-20):
        g_gavel(c)
    for x, y in ((0.14, 0.86), (0.4, 0.92), (0.84, 0.3)):
        with c.place(x, y, 0.2):
            g_lozenge(c, 0.18)


def g_hand_open(c, spread=6.0):
    """An open hand, palm to the viewer, fingers up."""
    c.rect(0.3, 0.84, 0.7, 1.0, r=0.03)
    c.rect(0.22, 0.44, 0.78, 0.9, r=0.16)
    for i, (x, top) in enumerate(((0.3, 0.14), (0.445, 0.06), (0.59, 0.1), (0.72, 0.22))):
        with c.at(x, 0.56, r=(i - 1.5) * spread):
            c.rect(-0.065, top - 0.56, 0.065, 0.0, r=0.065)
    with c.op("cut"):
        c.poly(stroke_poly([(0.3, 0.8), (0.04, 0.52)], 0.2))
    c.poly(stroke_poly([(0.3, 0.78), (0.08, 0.5)], 0.13))
    c.circle(0.08, 0.5, 0.065)
    with c.op("cut"):
        for x in (0.372, 0.517, 0.655):
            c.rect(x - 0.01, 0.3, x + 0.01, 0.5)


def g_wolf_howl(c):
    """A sitting wolf howling, facing right."""
    c.poly(Path(0.04, 1.0).C(-0.02, 0.92, 0.02, 0.84, 0.12, 0.86).C(0.1, 0.72, 0.16, 0.6, 0.26, 0.52)
           .C(0.34, 0.44, 0.42, 0.36, 0.46, 0.26).L(0.44, 0.04).L(0.56, 0.16).L(0.62, 0.14).L(0.86, 0.0).L(0.92, 0.04)
           .L(0.8, 0.14).L(0.9, 0.14).L(0.76, 0.24).L(0.7, 0.34).C(0.72, 0.46, 0.72, 0.58, 0.7, 0.66).L(0.74, 0.98)
           .L(0.8, 1.0).L(0.56, 1.0).L(0.56, 0.78).L(0.48, 0.9).L(0.52, 1.0).pts())
    with c.op("cut"):
        c.poly([(0.56, 0.2), (0.64, 0.18), (0.6, 0.23)])
        c.arc(0.3, 0.86, 0.16, 200, 300, 0.035)
    with c.op("shade"):
        c.poly([(0.46, 0.08), (0.53, 0.16), (0.48, 0.2)])


KITS = {
    "valdris": (k_valdris_q, k_valdris_e, k_valdris_r, k_valdris_p),
    "selene": (k_selene_q, k_selene_e, k_selene_r, k_selene_p),
    "kael": (k_kael_q, k_kael_e, k_kael_r, k_kael_p),
    "thessaly": (k_thessaly_q, k_thessaly_e, k_thessaly_r, k_thessaly_p),
    "brax": (k_brax_q, k_brax_e, k_brax_r, k_brax_p),
    "ossian": (k_ossian_q, k_ossian_e, k_ossian_r, k_ossian_p),
    "mirren": (k_mirren_q, k_mirren_e, k_mirren_r, k_mirren_p),
    "epoch": (k_epoch_q, k_epoch_e, k_epoch_r, k_epoch_p),
    "fenra": (k_fenra_q, k_fenra_e, k_fenra_r, k_fenra_p),
    "lyra": (k_lyra_q, k_lyra_e, k_lyra_r, k_lyra_p),
    "vex": (k_vex_q, k_vex_e, k_vex_r, k_vex_p),
    "seraph": (k_seraph_q, k_seraph_e, k_seraph_r, k_seraph_p),
}


KIT_NOTES = {
    "valdris": ("a fist driving into the ground behind a raised barricade", "a planted tower shield with rising chevrons",
                "a peak crowned by an anvil, a boulder falling", "armour plates over a heart"),
    "selene": ("a ring of bolts around a charged core", "a figure dissolving into shards behind a bolt",
               "a storm cloud over three bolts", "a bolt in a charging ring"),
    "kael": ("three blades fanned from one grip", "a crescent rolling with afterimages", "twin pistols spinning back to back",
             "a footprint with a ghost trail"),
    "thessaly": ("a tripod turret", "a hex eye in a rune circle bound by a chain", "a candle in a ring of sparks",
                 "a spindle and a hex eye"),
    "brax": ("a rising fist over a flame geyser", "a charging shoulder with drag lines", "two dripping molten fists",
             "a flame thermometer"),
    "ossian": ("a comet punching through a wall", "an arcing shell splitting into bomblets", "arrows falling on marks",
               "a reticle on a stag skull"),
    "mirren": ("a fox mask bursting into coins", "a hand closing on a gem", "a sack spilling coins", "a coin with fox ears"),
    "epoch": ("a bubble of paused motes", "a turning-back arrow around a heart", "a clock with its wedge pulled away",
              "an hourglass with a stride arrow"),
    "fenra": ("the pup pouncing", "a howling wolf over roots", "a snarling wolf over a small one", "a paw and a gear"),
    "lyra": ("a winged note", "a falling note over a hex eye", "a lyre in ringing arcs", "a swelling hairpin under a note"),
    "vex": ("a flask arcing to a splash", "a footprint leaving a toxic cloud", "a skull in a burst", "a skull with a lit fuse"),
    "seraph": ("a shield under a ward dome", "a beam striking the ground", "a gavel over marks", "the scales and the mark"),
}


@content_hook
def register_characters(content: Content):
    for row in content.characters:
        ch = row["key"]
        if ch in PORTRAITS:
            reg("portraits", ch, PORTRAITS[ch], T_PORTRAIT,
                f"{row['name']}, {row['title']}: bust crest ({PORTRAIT_NOTES[ch]})", kind="portrait")
        if ch not in KITS:
            continue
        kit = content.kits.get(ch, {})
        texts = {"passive": row["passive"], "q": row["active1"], "e": row["active2"], "r": row["ultimate"]}
        for i, (slot, fn) in enumerate(zip(("q", "e", "r", "passive"), KITS[ch])):
            if slot != "passive" and slot in kit:
                name, desc = kit[slot]
            else:
                name, _, desc = texts[slot].partition(":")
                desc = desc.strip()
            label = {"q": "Q", "e": "E", "r": "R (ultimate)", "passive": "passive"}[slot]
            desc = desc[:1].upper() + desc[1:]
            if not desc.endswith("."):
                desc += "."
            note = KIT_NOTES[ch][i]
            reg("kits", f"{ch}_{slot}", fn, T_KIT, f"{row['name']} {label}: {name.strip()}. {desc} Icon: {note}.",
                extra={"motif_name": note})


# ───────────────────────────── chassis (weapon silhouettes, muzzle to the right) ─────────────────────────────
def w_colossus_cannon(c):
    with c.at(0.0, 0.0, r=-14):
        c.rect(0.14, 0.28, 0.86, 0.5, r=0.03)
        c.rect(0.84, 0.24, 0.98, 0.54, r=0.03)
        c.rect(0.02, 0.3, 0.16, 0.48, r=0.08)
        with c.op("cut"):
            for x in (0.36, 0.6):
                c.rect(x, 0.28, x + 0.03, 0.5)
            c.circle(0.94, 0.39, 0.05)
        with c.op("shade"):
            c.rect(0.14, 0.42, 0.86, 0.5)
    c.poly([(0.2, 0.62), (0.62, 0.5), (0.66, 0.6), (0.3, 0.78)])
    c.circle(0.36, 0.74, 0.2)
    with c.op("cut"):
        c.ring(0.36, 0.74, 0.14, 0.03)
    for a in range(0, 360, 60):
        with c.op("cut"):
            c.line([polar(0.36, 0.74, 0.04, a), polar(0.36, 0.74, 0.11, a)], 0.03, cap=False)
    c.circle(0.36, 0.74, 0.045)


def w_thundercoil_launcher(c):
    c.rect(0.04, 0.4, 0.74, 0.62, r=0.05)
    for x in (0.26, 0.4, 0.54):
        c.rect(x, 0.32, x + 0.08, 0.7, r=0.03)
    c.poly([(0.12, 0.6), (0.3, 0.6), (0.24, 0.92), (0.1, 0.92)])
    c.circle(0.84, 0.51, 0.16)
    with c.op("cut"):
        c.ring(0.84, 0.51, 0.1, 0.03)
    c.poly([(0.86, 0.36), (0.8, 0.52), (0.86, 0.52), (0.82, 0.66), (0.9, 0.48), (0.84, 0.48)])
    with c.op("shade"):
        c.rect(0.04, 0.54, 0.74, 0.62)


def w_serpent_smg(c):
    c.poly([(0.2, 0.34), (0.74, 0.34), (0.74, 0.5), (0.2, 0.52)])
    # serpent-head muzzle
    c.poly(Path(0.72, 0.3).C(0.84, 0.26, 0.96, 0.32, 1.0, 0.42).L(0.9, 0.46).L(0.98, 0.5).C(0.92, 0.56, 0.8, 0.56, 0.72, 0.54).pts())
    with c.op("cut"):
        c.poly([(0.84, 0.36), (0.88, 0.37), (0.85, 0.39)])
    # curved magazine like a tail
    c.bez((0.48, 0.5), (0.46, 0.7), (0.56, 0.84), (0.44, 0.98), 0.12, 0.05)
    # grip and stock
    c.poly([(0.26, 0.5), (0.38, 0.5), (0.32, 0.8), (0.2, 0.8)])
    c.poly([(0.0, 0.3), (0.22, 0.36), (0.22, 0.48), (0.02, 0.5)])
    with c.op("cut"):
        c.rect(0.04, 0.38, 0.14, 0.44)
    with c.op("shade"):
        c.rect(0.2, 0.44, 0.74, 0.52)


def w_godsbane_rifle(c):
    c.rect(0.3, 0.44, 1.0, 0.52, r=0.02)
    c.poly([(0.0, 0.46), (0.3, 0.42), (0.46, 0.42), (0.46, 0.6), (0.3, 0.6), (0.2, 0.62), (0.02, 0.7)])
    c.poly([(0.34, 0.58), (0.44, 0.58), (0.4, 0.8), (0.3, 0.8)])
    c.rect(0.4, 0.28, 0.66, 0.36, r=0.04)
    c.rect(0.48, 0.34, 0.52, 0.44)
    c.rect(0.58, 0.34, 0.62, 0.44)
    c.rect(0.9, 0.4, 0.94, 0.44)
    with c.op("cut"):
        c.circle(0.44, 0.32, 0.02)
    with c.op("shade"):
        c.poly([(0.02, 0.58), (0.2, 0.56), (0.2, 0.62), (0.02, 0.7)])


def w_wraith_bow(c):
    c.poly(Path(0.42, 0.0).C(0.62, 0.14, 0.66, 0.34, 0.58, 0.5).C(0.66, 0.66, 0.62, 0.86, 0.42, 1.0).L(0.46, 0.9)
           .C(0.56, 0.78, 0.56, 0.64, 0.5, 0.5).C(0.56, 0.36, 0.56, 0.22, 0.46, 0.1).pts())
    c.line([(0.44, 0.04), (0.2, 0.5), (0.44, 0.96)], 0.025)
    c.rect(0.14, 0.475, 0.9, 0.525)
    c.poly([(0.84, 0.4), (1.0, 0.5), (0.84, 0.6), (0.88, 0.5)])
    c.poly([(0.1, 0.4), (0.2, 0.47), (0.2, 0.53), (0.1, 0.6), (0.14, 0.5)])
    with c.op("cut"):
        c.poly([(0.9, 0.46), (0.94, 0.5), (0.9, 0.54)])


def w_sunspike_shotgun(c):
    c.rect(0.3, 0.36, 0.84, 0.46, r=0.02)
    c.rect(0.3, 0.48, 0.84, 0.58, r=0.02)
    c.poly([(0.0, 0.46), (0.34, 0.34), (0.42, 0.34), (0.42, 0.62), (0.3, 0.62), (0.06, 0.7)])
    c.poly([(0.36, 0.6), (0.48, 0.6), (0.44, 0.82), (0.32, 0.82)])
    with c.place(0.9, 0.47, 0.3):
        g_burst(c, 8, 0.5, 0.2)
    with c.op("shade"):
        c.rect(0.3, 0.52, 0.84, 0.58)


def w_anvil_gauntlets(c):
    with c.box(0.08, 0.2, 0.92, 1.0):
        g_fist(c)
    with c.box(0.04, 0.0, 0.96, 0.44):
        c.knock(ANVIL, 0.05)
        c.poly(ANVIL)
    with c.op("shade"):
        with c.box(0.04, 0.0, 0.96, 0.44):
            c.poly([(0.27, 0.2), (0.98, 0.2), (0.98, 0.26), (0.27, 0.26)])


def w_longstrider_rail(c):
    c.poly([(0.0, 0.5), (0.22, 0.42), (0.36, 0.42), (0.36, 0.6), (0.24, 0.6), (0.04, 0.64)])
    c.rect(0.3, 0.42, 0.62, 0.6, r=0.03)
    c.rect(0.6, 0.4, 1.0, 0.46)
    c.rect(0.6, 0.54, 1.0, 0.6)
    c.rect(0.6, 0.46, 0.8, 0.54)
    for x in (0.66, 0.78, 0.9):
        c.rect(x, 0.38, x + 0.03, 0.62)
    c.rect(0.28, 0.28, 0.6, 0.36, r=0.04)
    c.rect(0.36, 0.34, 0.4, 0.42)
    c.poly([(0.34, 0.58), (0.44, 0.58), (0.4, 0.78), (0.3, 0.78)])
    with c.op("shade"):
        c.rect(0.3, 0.54, 0.62, 0.6)


def w_coinshooter(c):
    with c.box(0.0, 0.14, 0.78, 0.9):
        g_pistol(c)
    with c.place(0.84, 0.3, 0.3):
        g_coin(c, "star")
    c.arc(0.84, 0.3, 0.24, 110, 200, 0.03)


def w_pendulum_repeater(c):
    c.rect(0.08, 0.3, 0.9, 0.42, r=0.03)
    c.poly([(0.0, 0.3), (0.12, 0.3), (0.12, 0.5), (0.02, 0.56)])
    c.rect(0.86, 0.26, 0.96, 0.46, r=0.02)
    c.rect(0.56, 0.18, 0.72, 0.3, r=0.02)
    c.line([(0.4, 0.42), (0.52, 0.84)], 0.035)
    c.circle(0.53, 0.86, 0.1)
    with c.op("cut"):
        c.circle(0.53, 0.86, 0.04)
    c.circle(0.4, 0.42, 0.04)
    c.poly([(0.2, 0.42), (0.3, 0.42), (0.26, 0.64), (0.16, 0.64)])
    with c.op("shade"):
        c.rect(0.08, 0.37, 0.9, 0.42)


def w_bellowfire_projector(c):
    c.poly([(0.02, 0.2), (0.14, 0.26), (0.36, 0.4), (0.36, 0.62), (0.14, 0.76), (0.02, 0.82)])
    with c.op("cut"):
        for x in (0.1, 0.18, 0.26):
            c.line([(x, 0.28 + (x - 0.1) * 0.6), (x, 0.74 - (x - 0.1) * 0.6)], 0.022, cap=False)
    c.rect(0.34, 0.4, 0.58, 0.62, r=0.03)
    c.poly([(0.56, 0.44), (0.7, 0.46), (0.7, 0.56), (0.56, 0.58)])
    with c.place(0.84, 0.51, 0.44, r=90):
        g_flame(c, core=True)


def w_gravemaw_mortar(c):
    with c.place(0.5, 0.44, 0.84, r=-35):
        c.rect(0.14, 0.32, 0.86, 0.68, r=0.04)
        c.rect(0.8, 0.26, 0.96, 0.74, r=0.03)
        with c.op("cut"):
            for x in (0.84, 0.88, 0.92):
                c.poly([(x, 0.3), (x + 0.02, 0.3), (x + 0.01, 0.38)])
                c.poly([(x, 0.7), (x + 0.02, 0.7), (x + 0.01, 0.62)])
        with c.op("shade"):
            c.rect(0.14, 0.56, 0.86, 0.68)
    c.poly([(0.1, 0.96), (0.2, 0.74), (0.56, 0.74), (0.66, 0.96)])
    c.circle(0.38, 0.72, 0.1)


def w_stormlash(c):
    c.rect(0.02, 0.62, 0.3, 0.76, r=0.06)
    c.rect(0.28, 0.58, 0.34, 0.8, r=0.02)
    c.circle(0.04, 0.69, 0.06)
    c.line([(0.34, 0.68), (0.46, 0.5), (0.56, 0.62), (0.68, 0.34), (0.78, 0.46), (0.9, 0.16), (0.96, 0.22)], 0.07)
    with c.place(0.94, 0.12, 0.2):
        g_spark4(c)


def w_seraph_lance(c):
    c.rect(0.0, 0.47, 0.7, 0.53)
    c.poly([(0.66, 0.5), (0.76, 0.4), (1.0, 0.5), (0.76, 0.6)])
    with c.op("cut"):
        c.line([(0.78, 0.5), (0.94, 0.5)], 0.02)
    for sgn in (-1, 1):
        c.bez((0.62, 0.5 + sgn * 0.04), (0.54, 0.5 + sgn * 0.16), (0.46, 0.5 + sgn * 0.2), (0.4, 0.5 + sgn * 0.3), 0.07, 0.02)
        c.bez((0.62, 0.5 + sgn * 0.04), (0.58, 0.5 + sgn * 0.12), (0.52, 0.5 + sgn * 0.14), (0.5, 0.5 + sgn * 0.2), 0.05, 0.015)
    c.circle(0.06, 0.5, 0.05)


def w_tidecaller_harpoon(c):
    c.rect(0.12, 0.46, 0.74, 0.54)
    c.poly([(0.7, 0.42), (1.0, 0.5), (0.7, 0.58), (0.74, 0.5)])
    c.poly([(0.72, 0.44), (0.62, 0.3), (0.7, 0.44)])
    c.poly([(0.66, 0.46), (0.6, 0.34), (0.58, 0.46)])
    c.poly([(0.72, 0.56), (0.62, 0.7), (0.7, 0.56)])
    c.poly([(0.66, 0.54), (0.6, 0.66), (0.58, 0.54)])
    c.rect(0.08, 0.42, 0.2, 0.58, r=0.03)
    c.bez((0.1, 0.56), (0.0, 0.7), (0.24, 0.82), (0.34, 0.66), 0.04, 0.03)
    c.bez((0.34, 0.66), (0.44, 0.52), (0.5, 0.86), (0.36, 0.9), 0.035, 0.02)


def w_orrery_discs(c):
    c.circle(0.5, 0.5, 0.14)
    c.ring(0.5, 0.5, 0.48, 0.03)
    c.arc(0.5, 0.5, 0.32, 0, 360, 0.025)
    for (a, r, s) in ((-40, 0.48, 0.24), (150, 0.48, 0.2), (80, 0.32, 0.17)):
        with c.place(*polar(0.5, 0.5, r, a), s):
            g_sawblade(c, 8)


def w_huntmother_javelins(c):
    for i, off in enumerate((-0.16, 0.0, 0.16)):
        with c.at(0.5 + off, 0.5 + off * 0.3, r=-38 + i * 8):
            c.rect(-0.46, -0.025, 0.3, 0.025)
            c.poly([(0.26, -0.07), (0.48, 0.0), (0.26, 0.07), (0.3, 0.0)])
            c.poly([(0.28, -0.05), (0.2, -0.11), (0.24, -0.03)])
            c.poly([(0.28, 0.05), (0.2, 0.11), (0.24, 0.03)])
    c.rect(0.3, 0.56, 0.5, 0.66, r=0.03)


def w_chorus_harp(c):
    c.poly(Path(0.14, 0.96).L(0.14, 0.1).C(0.3, 0.0, 0.5, 0.12, 0.62, 0.24).C(0.74, 0.36, 0.86, 0.4, 0.94, 0.34)
           .L(0.94, 0.44).C(0.82, 0.52, 0.66, 0.46, 0.56, 0.36).C(0.44, 0.24, 0.32, 0.18, 0.26, 0.2).L(0.26, 0.96).pts())
    c.line([(0.24, 0.94), (0.92, 0.4)], 0.07)
    for i in range(5):
        x = 0.34 + i * 0.1
        top = 0.2 + i * 0.05 + (0.04 if i > 2 else 0.0)
        c.line([(x, top), (x, 0.9 - i * 0.08)], 0.02, cap=False)
    c.rect(0.08, 0.92, 0.34, 1.0, r=0.02)


def w_plaguebloom_sprayer(c):
    c.rect(0.02, 0.34, 0.3, 0.84, r=0.12)
    with c.op("cut"):
        c.rect(0.02, 0.52, 0.3, 0.55)
    c.rect(0.1, 0.24, 0.22, 0.36, r=0.02)
    c.bez((0.16, 0.26), (0.2, 0.06), (0.44, 0.1), (0.5, 0.36), 0.05, 0.05)
    c.rect(0.44, 0.34, 0.74, 0.44, r=0.03)
    c.poly([(0.5, 0.42), (0.58, 0.42), (0.54, 0.6), (0.46, 0.6)])
    for x, y, r in ((0.84, 0.36, 0.1), (0.94, 0.26, 0.07), (0.94, 0.48, 0.07), (0.8, 0.2, 0.05), (0.8, 0.54, 0.05)):
        c.circle(x, y, r)
    with c.op("shade"):
        c.rect(0.02, 0.55, 0.3, 0.84)


def w_dawnbreaker_carbine(c):
    c.rect(0.3, 0.42, 0.9, 0.52, r=0.02)
    c.poly([(0.0, 0.42), (0.34, 0.38), (0.5, 0.38), (0.5, 0.58), (0.34, 0.6), (0.04, 0.66)])
    c.poly([(0.36, 0.56), (0.46, 0.56), (0.42, 0.78), (0.32, 0.78)])
    c.rect(0.56, 0.52, 0.66, 0.72, r=0.02)
    with c.place(0.2, 0.26, 0.26):
        g_radiant(c)
    c.rect(0.88, 0.36, 0.94, 0.44)
    with c.op("shade"):
        c.rect(0.3, 0.48, 0.9, 0.52)


def w_titanfall_hammer(c):
    c.poly(stroke_poly([(0.04, 0.96), (0.62, 0.38)], 0.08))
    with c.at(0.66, 0.34, r=-45):
        c.rect(-0.2, -0.36, 0.2, 0.3, r=0.04)
        c.rect(-0.24, -0.4, 0.24, -0.28, r=0.03)
        c.rect(-0.24, 0.18, 0.24, 0.3, r=0.03)
        with c.op("shade"):
            c.rect(0.06, -0.28, 0.2, 0.18)
    c.circle(0.05, 0.95, 0.06)


def w_voidheart_singularity(c):
    with c.place(0.5, 0.52, 0.58):
        g_heart(c)
    with c.at(0.5, 0.52, r=-20):
        with c.op("cut"):
            c.taper(arcpts(0.0, 0.0, 0.48, 0.15, 0, 360), 0.11)
        c.taper(arcpts(0.0, 0.0, 0.48, 0.15, 0, 360), 0.05)
    for a in (-35, 35, 145, 215):
        c.line([polar(0.5, 0.52, 0.5, a - 90), polar(0.5, 0.52, 0.4, a - 90)], 0.045)


def w_echoing_greatbow(c):
    c.poly(Path(0.36, 0.0).C(0.62, 0.16, 0.64, 0.84, 0.36, 1.0).L(0.4, 0.92).C(0.54, 0.78, 0.54, 0.22, 0.4, 0.08).pts())
    c.line([(0.38, 0.04), (0.12, 0.5), (0.38, 0.96)], 0.022)
    for a in (-16, 0, 16):
        with c.at(0.12, 0.5, r=a):
            c.rect(0.0, -0.02, 0.8, 0.02)
            c.poly([(0.76, -0.07), (0.9, 0.0), (0.76, 0.07)])


def w_epochal_sundial(c):
    c.circle(0.5, 0.56, 0.42)
    with c.op("cut"):
        c.ring(0.5, 0.56, 0.34, 0.03)
        for i in range(12):
            a = i * 30
            c.line([polar(0.5, 0.56, 0.24, a), polar(0.5, 0.56, 0.3, a)], 0.025, cap=False)
    c.poly([(0.5, 0.56), (0.54, 0.54), (0.96, 0.08), (0.5, 0.5)])
    with c.op("shade"):
        c.poly([(0.5, 0.56), (0.54, 0.54), (0.96, 0.08)])
    c.circle(0.5, 0.56, 0.05)


CHASSIS_BOLD = {"seraph_lance": 0.016, "tidecaller_harpoon": 0.016, "stormlash": 0.014, "huntmother_javelins": 0.016,
                "echoing_greatbow": 0.014, "wraith_bow": 0.014, "orrery_discs": 0.01, "chorus_harp": 0.008,
                "godsbane_rifle": 0.01, "longstrider_rail": 0.008, "pendulum_repeater": 0.01, "coinshooter": 0.008}
CHASSIS = {k[2:]: v for k, v in dict(globals()).items() if k.startswith("w_") and callable(v)}


@content_hook
def register_chassis(content: Content):
    for row in content.chassis:
        k = row["key"]
        if k in CHASSIS:
            reg("chassis", k, CHASSIS[k], T_BONE, f"{row['name']} (chassis): {row['desc']}",
                extra={"bold": CHASSIS_BOLD.get(k, 0.006)})


# ───────────────────────────── god sigils ─────────────────────────────
def gs_pyra(c):  # a crowned flame with two wrath-horns
    with c.box(0.2, 0.08, 0.8, 0.84):
        g_flame(c, core=True)
    c.bez((0.3, 0.72), (0.06, 0.64), (0.02, 0.34), (0.12, 0.08), 0.1, 0.014)
    c.bez((0.7, 0.72), (0.94, 0.64), (0.98, 0.34), (0.88, 0.08), 0.1, 0.014)
    c.poly([(0.2, 0.84), (0.8, 0.84), (0.86, 0.98), (0.14, 0.98)])
    for x in (0.28, 0.5, 0.72):
        c.poly([(x - 0.05, 0.86), (x, 0.78), (x + 0.05, 0.86)])
    with c.op("cut"):
        c.rect(0.18, 0.9, 0.82, 0.92)


def gs_zephyros(c):  # a bolt in gust curls
    with c.box(0.3, 0.12, 0.7, 0.88):
        g_bolt(c)
    c.taper(spiral_pts(0.5, 0.5, 0.48, 0.3, 0.42, 150), 0.1, 0.02)
    c.taper(spiral_pts(0.5, 0.5, 0.48, 0.3, 0.42, 330), 0.1, 0.02)
    c.arc(0.5, 0.5, 0.5, 60, 110, 0.02, 0.07)
    c.arc(0.5, 0.5, 0.5, 240, 290, 0.02, 0.07)


def gs_nyctia(c):  # a crescent and a veiled dagger
    g_crescent(c, 0.24, -0.1, 0.46, 0.38)
    with c.at(0.66, 0.5, s=0.72, r=20):
        c.poly([(0.0, -0.5), (0.07, -0.26), (0.06, 0.16), (-0.06, 0.16), (-0.07, -0.26)])
        c.rect(-0.18, 0.14, 0.18, 0.21, r=0.03)
        c.rect(-0.04, 0.2, 0.04, 0.38)
        c.circle(0.0, 0.42, 0.055)
    with c.place(0.2, 0.16, 0.2):
        g_spark4(c)


def gs_aeon(c):  # a ring dial with two hands
    g_clock(c, -100, 20)
    c.poly([(0.5, -0.06), (0.56, 0.04), (0.5, 0.1), (0.44, 0.04)])


def gs_gaiaa(c):  # a faceted heart-stone with roots
    heart = (Path(0.5, 0.8).L(0.12, 0.44).L(0.1, 0.2).L(0.28, 0.04).L(0.5, 0.18).L(0.72, 0.04).L(0.9, 0.2)
             .L(0.88, 0.44).L(0.5, 0.8).pts())
    c.poly(heart)
    with c.op("shade"):
        c.poly([(0.5, 0.18), (0.72, 0.04), (0.9, 0.2), (0.88, 0.44), (0.5, 0.8), (0.5, 0.42)])
    with c.op("cut"):
        c.line([(0.1, 0.2), (0.3, 0.3), (0.5, 0.42), (0.7, 0.3), (0.9, 0.2)], 0.03)
        c.line([(0.3, 0.3), (0.28, 0.04)], 0.03)
        c.line([(0.7, 0.3), (0.72, 0.04)], 0.03)
        c.line([(0.5, 0.42), (0.5, 0.78)], 0.03)
    c.bez((0.4, 0.7), (0.32, 0.84), (0.2, 0.86), (0.06, 0.98), 0.08, 0.015)
    c.bez((0.6, 0.7), (0.68, 0.84), (0.8, 0.86), (0.94, 0.98), 0.08, 0.015)
    c.bez((0.5, 0.76), (0.5, 0.86), (0.46, 0.92), (0.5, 1.02), 0.07, 0.015)


def gs_morwenn(c):  # a wave and a drop
    with c.box(0.0, 0.3, 1.0, 1.0):
        g_wave(c)
    with c.place(0.8, 0.18, 0.34):
        g_drop(c)


def gs_seraphel(c):  # a halo over scales
    c.ring(0.5, 0.12, 0.14, 0.055)
    with c.box(0.0, 0.26, 1.0, 1.0):
        g_scales(c)


def gs_umbra_rex(c):  # a broken crown over a closed eye
    c.poly([(0.06, 0.56), (0.12, 0.14), (0.3, 0.36), (0.44, 0.06), (0.52, 0.3), (0.58, 0.22), (0.7, 0.36), (0.88, 0.14), (0.94, 0.56)])
    with c.op("cut"):
        c.line([(0.5, 0.08), (0.46, 0.26), (0.54, 0.36), (0.48, 0.56)], 0.04)
        c.rect(0.06, 0.46, 0.94, 0.5)
    c.arc(0.5, 0.62, 0.3, 20, 160, 0.08)
    for x, a in ((0.26, 115), (0.5, 90), (0.74, 65)):
        c.line([polar(0.5, 0.62, 0.3, a), polar(0.5, 0.62, 0.42, a)], 0.05)


GOD_SIGILS = {"pyra": gs_pyra, "zephyros": gs_zephyros, "nyctia": gs_nyctia, "aeon": gs_aeon, "gaiaa": gs_gaiaa,
              "morwenn": gs_morwenn, "seraphel": gs_seraphel, "umbra_rex": gs_umbra_rex}
GOD_NOTES = {"pyra": "a crowned flame with wrath-horns", "zephyros": "a bolt in gust curls",
             "nyctia": "a crescent and a veiled dagger", "aeon": "a ring dial with hands",
             "gaiaa": "a faceted heart-stone with roots", "morwenn": "a wave and a drop",
             "seraphel": "a halo over scales", "umbra_rex": "a broken crown over a closed eye"}


@content_hook
def register_gods(content: Content):
    for k, row in content.gods.items():
        col, sec = GODS[k]
        if k in RED_GODS:
            tint, light = col, sec  # the red never meets a white-ish top: it grades from the secondary
        else:
            tint, light = col, IVORY
        reg("gods", k, GOD_SIGILS[k], tint, f"{row['name']} ({row['domain']}): {GOD_NOTES[k]}", light=light)


# ───────────────────────────── boon kinds ─────────────────────────────
@icon("boon_kind", "legendary", T_KIT, "Legendary boon (a crown)")
def bk_legendary(c):
    c.poly([(0.04, 0.9), (0.04, 0.3), (0.26, 0.5), (0.5, 0.1), (0.74, 0.5), (0.96, 0.3), (0.96, 0.9)])
    for x, y in ((0.04, 0.24), (0.5, 0.06), (0.96, 0.24)):
        c.circle(x, y, 0.07)
    with c.op("cut"):
        c.rect(0.04, 0.7, 0.96, 0.75)
        c.poly([(0.5, 0.42), (0.58, 0.54), (0.5, 0.64), (0.42, 0.54)])


@icon("boon_kind", "duo", T_KIT, "Duo boon: two gods at once (a split lozenge)")
def bk_duo(c):
    c.poly([(0.46, 0.0), (0.46, 1.0), (0.0, 0.5)])
    c.poly([(0.54, 0.0), (1.0, 0.5), (0.54, 1.0)])
    with c.op("shade"):
        c.poly([(0.54, 0.0), (1.0, 0.5), (0.54, 1.0)])
    with c.op("cut"):
        c.poly([(0.46, 0.3), (0.46, 0.7), (0.26, 0.5)])


@icon("boon_kind", "team", T_KIT, "Team boon: every player gains it (a four-link chain in chrome gold, never player colours)")
def bk_team(c):
    """A closed loop of four links: each link crosses over one neighbour and under the other."""
    def link(a, knock):
        ctr = polar(0.5, 0.5, 0.3, a)
        with c.place(ctr[0], ctr[1], 0.62, r=a + 90):
            if knock:
                with c.op("cut"):
                    c.rect(0.04, 0.26, 0.96, 0.74, r=0.22)
            c.rect(0.08, 0.3, 0.92, 0.7, r=0.2)
            with c.op("cut"):
                c.rect(0.26, 0.43, 0.74, 0.57, r=0.07)
    for a in (0, 180):
        link(a, False)
    for a in (90, 270):
        link(a, True)


# ───────────────────────────── aim ─────────────────────────────
@icon("aim", "auto", T_KIT, "AUTO aim: the weapon picks and fires (a reticle with an orbit arrow)")
def aim_auto(c):
    g_reticle(c, gap=0.14, ring_r=0.34, w=0.07)
    c.arc(0.5, 0.5, 0.48, 200, 320, 0.07)
    c.poly([polar(0.5, 0.5, 0.58, 320), polar(0.5, 0.5, 0.38, 320), polar(0.5, 0.5, 0.48, 352)])


@icon("aim", "assisted", T_KIT, "ASSISTED aim: a magnetism cone pulls your shots on")
def aim_assisted(c):
    c.poly([(0.04, 0.5), (0.96, 0.06), (0.96, 0.94)])
    with c.op("cut"):
        c.poly([(0.22, 0.5), (0.88, 0.2), (0.88, 0.8)])
    c.ring(0.7, 0.5, 0.17, 0.06)
    c.circle(0.7, 0.5, 0.05)


@icon("aim", "manual", T_KIT, "MANUAL aim: you aim; precision earns Deadeye (a fine reticle)")
def aim_manual(c):
    for a in (0, 90, 180, 270):
        with c.at(0.5, 0.5, r=a):
            c.poly([(-0.05, -0.5), (0.05, -0.5), (0.025, -0.14), (-0.025, -0.14)])
    c.ring(0.5, 0.5, 0.3, 0.04)
    c.circle(0.5, 0.5, 0.045)


def _bias_frame(c):
    """The shared target-bias frame: four corner brackets."""
    for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        x = 0.02 if sx == 0 else 0.98
        y = 0.02 if sy == 0 else 0.98
        dx = 0.24 if sx == 0 else -0.24
        dy = 0.24 if sy == 0 else -0.24
        c.line([(x + dx, y), (x, y), (x, y + dy)], 0.08)


@icon("aim", "bias_balanced", T_KIT, "Target bias: Balanced")
def aim_bias_balanced(c):
    _bias_frame(c)
    with c.box(0.22, 0.24, 0.78, 0.8):
        g_scales(c)


@icon("aim", "bias_nearest", T_KIT, "Target bias: Nearest (the closest target first)")
def aim_bias_nearest(c):
    _bias_frame(c)
    c.circle(0.5, 0.64, 0.12)
    c.circle(0.3, 0.34, 0.06)
    c.circle(0.72, 0.3, 0.06)
    with c.place(0.5, 0.36, 0.24, r=180):
        g_chevron(c, 0.3)


@icon("aim", "bias_strongest", T_KIT, "Target bias: Strongest (elites and bosses first)")
def aim_bias_strongest(c):
    _bias_frame(c)
    with c.box(0.26, 0.24, 0.74, 0.78):
        c.poly([(0.0, 0.9), (0.0, 0.3), (0.26, 0.5), (0.5, 0.1), (0.74, 0.5), (1.0, 0.3), (1.0, 0.9)])
        with c.op("cut"):
            c.rect(0.0, 0.7, 1.0, 0.76)


@icon("aim", "bias_lowest_hp", T_KIT, "Target bias: Lowest HP (finish the wounded)")
def aim_bias_lowest_hp(c):
    _bias_frame(c)
    with c.box(0.24, 0.26, 0.76, 0.78):
        g_heart(c)
        with c.op("cut"):
            c.line([(0.5, 0.24), (0.4, 0.44), (0.58, 0.56), (0.48, 0.8)], 0.08)


@icon("aim", "bias_pinned", T_KIT, "Target bias: Pinned (your pinged target)")
def aim_bias_pinned(c):
    _bias_frame(c)
    with c.box(0.3, 0.2, 0.7, 0.84):
        g_pin(c)


def g_pin(c):
    """A map pin."""
    c.poly(Path(0.5, 1.0).C(0.36, 0.76, 0.06, 0.58, 0.06, 0.36).C(0.06, 0.14, 0.26, 0.0, 0.5, 0.0).C(0.74, 0.0, 0.94, 0.14, 0.94, 0.36)
           .C(0.94, 0.58, 0.64, 0.76, 0.5, 1.0).pts())
    with c.op("cut"):
        c.circle(0.5, 0.36, 0.16)


# ───────────────────────────── team ─────────────────────────────
@icon("team", "overdrive", T_KIT, "Team Overdrive (the star emblem; also stamped in the V hex)")
def tm_overdrive(c):
    g_overdrive_star(c)


@icon("team", "ult_ready", T_KIT, "Ultimate ready (a full molten ring with a rising spark)")
def tm_ult_ready(c):
    c.ring(0.5, 0.5, 0.5, 0.12)
    for a in range(0, 360, 36):
        with c.op("cut"):
            c.line([polar(0.5, 0.5, 0.36, a), polar(0.5, 0.5, 0.5, a)], 0.02, cap=False)
    with c.place(0.5, 0.5, 0.56):
        g_spark4(c, 0.16)


@icon("team", "ping", T_KIT, "Ping (a pin with a ripple)")
def tm_ping(c):
    with c.box(0.26, 0.0, 0.74, 0.74):
        g_pin(c)
    c.poly(stroke_poly(arcpts(0.5, 0.84, 0.46, 0.14, 0, 180), 0.07))
    c.poly(stroke_poly(arcpts(0.5, 0.84, 0.46, 0.14, 205, 335), 0.07))


@icon("team", "mvp", T_KIT, "MVP (a radiant spark in a wreath)")
def tm_mvp(c):
    with c.place(0.5, 0.42, 0.62):
        g_spark8(c)
    for sgn in (-1, 1):
        for i in range(5):
            a = 100 + sgn * (i * 22 + 20)
            p = polar(0.5, 0.46, 0.44, a)
            c.ellipse(p[0], p[1], 0.07, 0.03, r=a + 90 + sgn * 30)
    c.poly(stroke_poly(arcpts(0.5, 0.46, 0.44, 0.44, 30, 150), 0.03))


# ───────────────────────────── run ─────────────────────────────
@icon("run", "hourglass", T_KIT, "Run timer (an hourglass)")
def rn_hourglass(c):
    g_hourglass(c)


@icon("run", "threat", T_KIT, "Threat level (a chevron)")
def rn_threat(c):
    g_chevron(c, 0.3)
    with c.at(0.0, 0.36):
        g_chevron(c, 0.3)


@icon("run", "surge", T_KIT, "Surge: the horde floods in (a war horn with arrows)")
def rn_surge(c):
    horn = (Path(0.02, 0.9).C(0.1, 0.86, 0.3, 0.8, 0.44, 0.62).C(0.52, 0.5, 0.56, 0.4, 0.58, 0.26).L(0.84, 0.44)
            .C(0.74, 0.54, 0.62, 0.66, 0.5, 0.78).C(0.36, 0.9, 0.16, 0.96, 0.02, 0.96).pts())
    c.poly(horn)
    c.poly([(0.52, 0.2), (0.92, 0.48), (0.96, 0.4), (0.6, 0.14)])
    with c.op("shade"):
        c.poly(Path(0.02, 0.96).C(0.16, 0.96, 0.36, 0.9, 0.5, 0.78).C(0.62, 0.66, 0.74, 0.54, 0.84, 0.44).L(0.76, 0.38)
               .C(0.62, 0.56, 0.4, 0.84, 0.02, 0.93).pts())
    with c.op("cut"):
        c.rect(0.2, 0.84, 0.26, 0.98)
    for i, (x, y) in enumerate(((0.86, 0.08), (1.0, 0.24))):
        with c.place(x, y, 0.2, r=-45 + 90):
            g_chevron(c, 0.32)


@icon("run", "gate_open", T_KIT, "Boss Gate open")
def rn_gate_open(c):
    c.poly(Path(0.04, 1.0).L(0.04, 0.46).C(0.04, 0.16, 0.26, 0.0, 0.5, 0.0).C(0.74, 0.0, 0.96, 0.16, 0.96, 0.46).L(0.96, 1.0).pts())
    with c.op("cut"):
        c.poly(Path(0.2, 1.0).L(0.2, 0.5).C(0.2, 0.3, 0.34, 0.2, 0.5, 0.2).C(0.66, 0.2, 0.8, 0.3, 0.8, 0.5).L(0.8, 1.0).pts())
    c.poly([(0.22, 0.36), (0.34, 0.46), (0.34, 1.0), (0.22, 1.0)])
    c.poly([(0.78, 0.36), (0.66, 0.46), (0.66, 1.0), (0.78, 1.0)])
    with c.place(0.5, 0.62, 0.3):
        g_spark4(c, 0.14)


@icon("run", "gate_sealed", T_KIT, "Boss Gate sealed")
def rn_gate_sealed(c):
    c.poly(Path(0.04, 1.0).L(0.04, 0.46).C(0.04, 0.16, 0.26, 0.0, 0.5, 0.0).C(0.74, 0.0, 0.96, 0.16, 0.96, 0.46).L(0.96, 1.0).pts())
    with c.op("cut"):
        c.poly(Path(0.2, 1.0).L(0.2, 0.5).C(0.2, 0.3, 0.34, 0.2, 0.5, 0.2).C(0.66, 0.2, 0.8, 0.3, 0.8, 0.5).L(0.8, 1.0).pts())
    c.poly(Path(0.25, 1.0).L(0.25, 0.52).C(0.25, 0.34, 0.37, 0.26, 0.5, 0.26).C(0.63, 0.26, 0.75, 0.34, 0.75, 0.52).L(0.75, 1.0).pts())
    with c.op("cut"):
        c.circle(0.5, 0.62, 0.16)
    c.circle(0.5, 0.62, 0.12)
    with c.op("cut"):
        c.circle(0.5, 0.6, 0.035)
        c.poly([(0.48, 0.61), (0.52, 0.61), (0.535, 0.7), (0.465, 0.7)])


@icon("run", "gathering", T_KIT, "Gathering at the gate (four pips converging)")
def rn_gathering(c):
    c.ring(0.5, 0.5, 0.18, 0.06)
    for a in (-135, -45, 45, 135):
        p = polar(0.5, 0.5, 0.42, a)
        c.circle(p[0], p[1], 0.09)
        with c.place(*polar(0.5, 0.5, 0.27, a), 0.14, r=a - 90):
            g_chevron(c, 0.34)


@icon("run", "warlord_slain", T_WARLORD, "Warlord slain (the crowned skull, struck through)")
def rn_warlord_slain(c):
    p_warlord(c)
    with c.op("cut"):
        c.poly(stroke_poly([(0.0, 0.96), (1.0, 0.1)], 0.14))
    c.poly(stroke_poly([(0.04, 0.92), (0.96, 0.14)], 0.07))


@icon("run", "named_combo", T_KIT, "Named combo formed (a seal with a star)")
def rn_named_combo(c):
    seal_ring(c, bumps=14, r=0.5, w=0.5)
    with c.op("cut"):
        c.ring(0.5, 0.5, 0.38, 0.035)
        c.star(0.5, 0.5, 0.26, 0.1, 5)


@icon("run", "boon_queued", T_KIT, "Boon waiting (an arched boon card with a spark)")
def rn_boon_queued(c):
    c.poly(Path(0.14, 1.0).L(0.14, 0.4).C(0.14, 0.16, 0.3, 0.02, 0.5, 0.02).C(0.7, 0.02, 0.86, 0.16, 0.86, 0.4).L(0.86, 1.0).pts())
    with c.op("cut"):
        c.poly(Path(0.24, 0.92).L(0.24, 0.42).C(0.24, 0.24, 0.36, 0.12, 0.5, 0.12).C(0.64, 0.12, 0.76, 0.24, 0.76, 0.42).L(0.76, 0.92).pts())
    with c.place(0.5, 0.48, 0.36):
        g_spark4(c, 0.16)


@icon("run", "explored", T_KIT, "Explored (a compass)")
def rn_explored(c):
    c.ring(0.5, 0.5, 0.5, 0.08)
    c.poly([(0.5, 0.08), (0.6, 0.5), (0.5, 0.92), (0.4, 0.5)])
    c.poly([(0.08, 0.5), (0.5, 0.42), (0.92, 0.5), (0.5, 0.58)])
    with c.op("shade"):
        c.poly([(0.5, 0.5), (0.6, 0.5), (0.5, 0.92), (0.4, 0.5)])
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.04)


@icon("run", "kills", T_KIT, "Kills (a skull)")
def rn_kills(c):
    g_skull(c)
    for sgn in (-1, 1):
        c.poly(stroke_poly([(0.5 + sgn * 0.62, 0.98), (0.5 + sgn * 0.3, 0.8)], 0.08))


# ───────────────────────────── ui ─────────────────────────────
@icon("ui", "equip", T_KIT, "Equip (an arrow into a socket)")
def ui_equip(c):
    c.poly([(0.5, 0.62), (0.82, 0.3), (0.62, 0.3), (0.62, 0.0), (0.38, 0.0), (0.38, 0.3), (0.18, 0.3)])
    c.poly(Path(0.08, 0.72).C(0.08, 0.88, 0.28, 0.98, 0.5, 0.98).C(0.72, 0.98, 0.92, 0.88, 0.92, 0.72).L(0.8, 0.72)
           .C(0.8, 0.82, 0.66, 0.88, 0.5, 0.88).C(0.34, 0.88, 0.2, 0.82, 0.2, 0.72).pts())


@icon("ui", "fuse", T_KIT, "Fuse two parts (two lozenges merging into one)")
def ui_fuse(c):
    with c.place(0.22, 0.24, 0.42):
        g_lozenge(c)
    with c.place(0.78, 0.24, 0.42):
        g_lozenge(c)
    c.line([(0.3, 0.42), (0.44, 0.58)], 0.07)
    c.line([(0.7, 0.42), (0.56, 0.58)], 0.07)
    with c.place(0.5, 0.76, 0.46):
        g_lozenge(c, 0.18)


@icon("ui", "salvage", T_KIT, "Salvage a part (a shard split by a hammer blow)")
def ui_salvage(c):
    c.poly([(0.18, 0.3), (0.42, 0.42), (0.34, 1.0), (0.1, 0.9), (0.02, 0.5)])
    c.poly([(0.58, 0.42), (0.86, 0.34), (0.98, 0.62), (0.78, 1.0), (0.5, 0.92)])
    with c.op("shade"):
        c.poly([(0.58, 0.42), (0.86, 0.34), (0.98, 0.62), (0.78, 1.0), (0.5, 0.92)])
    with c.place(0.52, 0.22, 0.46, r=-30):
        g_hammer(c)


@icon("ui", "reroll", T_KIT, "Reroll (a turning arrow)")
def ui_reroll(c):
    g_cw_arrow(c, 180, 450, r=0.4, w=0.13)


@icon("ui", "lock", T_KIT, "Locked")
def ui_lock(c):
    g_lock(c)


@icon("ui", "check", T_KIT, "Done / ready (a check mark)")
def ui_check(c):
    g_check(c)


@icon("ui", "close", T_KIT, "Close (a cross)")
def ui_close(c):
    g_cross(c, 0.18)


@icon("ui", "back", T_KIT, "Back (a curved arrow)")
def ui_back(c):
    c.poly(Path(0.4, 0.3).L(0.62, 0.3).C(0.86, 0.3, 0.98, 0.46, 0.98, 0.64).C(0.98, 0.82, 0.86, 0.96, 0.62, 0.96).L(0.3, 0.96)
           .L(0.3, 0.82).L(0.62, 0.82).C(0.76, 0.82, 0.84, 0.74, 0.84, 0.64).C(0.84, 0.52, 0.76, 0.44, 0.62, 0.44).L(0.4, 0.44).pts())
    c.poly([(0.02, 0.37), (0.44, 0.08), (0.44, 0.66)])


@icon("ui", "confirm", T_KIT, "Confirm (a check in a lozenge)")
def ui_confirm(c):
    g_lozenge(c)
    with c.op("cut"):
        c.line([(0.28, 0.52), (0.44, 0.66), (0.72, 0.36)], 0.1)


@icon("ui", "info", T_KIT, "Information (a lozenge dot over a stem, no letter)")
def ui_info(c):
    c.ring(0.5, 0.5, 0.5, 0.09)
    c.poly([(0.5, 0.16), (0.6, 0.26), (0.5, 0.36), (0.4, 0.26)])
    c.rect(0.42, 0.44, 0.58, 0.82, r=0.03)


@icon("ui", "filter", T_KIT, "Filter / sort (a funnel)")
def ui_filter(c):
    c.poly([(0.02, 0.06), (0.98, 0.06), (0.62, 0.52), (0.62, 0.9), (0.38, 1.0), (0.38, 0.52)])
    with c.op("cut"):
        c.rect(0.02, 0.16, 0.98, 0.2)


@icon("ui", "new", T_KIT, "New (a four-point spark with a dot)")
def ui_new(c):
    g_spark4(c, 0.12)
    c.circle(0.86, 0.14, 0.09)


@icon("ui", "upgrade", T_KIT, "Upgrade (a double up-chevron)")
def ui_upgrade(c):
    g_chevron(c, 0.24)
    with c.at(0.0, 0.34):
        g_chevron(c, 0.24)
    with c.op("shade"):
        with c.at(0.0, 0.34):
            g_chevron(c, 0.24)


@icon("ui", "delta_up", T_KIT, "A gain (an up-chevron; the UI colours it ichor)")
def ui_delta_up(c):
    c.poly([(0.5, 0.12), (0.96, 0.82), (0.04, 0.82)])


@icon("ui", "delta_down", T_KIT, "A loss (a down-chevron; the UI colours it loss)")
def ui_delta_down(c):
    c.poly([(0.5, 0.88), (0.96, 0.18), (0.04, 0.18)])


@icon("ui", "bearing", T_KIT, "Bearing to an objective (a chevron, rotated by the UI)")
def ui_bearing(c):
    c.poly([(0.5, 0.0), (0.96, 0.92), (0.5, 0.66), (0.04, 0.92)])


@icon("ui", "arrowhead", T_KIT, "Edge-pin nub (an arrowhead pointing up)")
def ui_arrowhead(c):
    c.poly([(0.5, 0.0), (1.0, 1.0), (0.0, 1.0)])
    with c.op("shade"):
        c.poly([(0.5, 0.0), (1.0, 1.0), (0.5, 1.0)])


@icon("ui", "pause", T_KIT, "Paused / contested (two bars)")
def ui_pause(c):
    c.rect(0.14, 0.04, 0.4, 0.96, r=0.04)
    c.rect(0.6, 0.04, 0.86, 0.96, r=0.04)


@icon("ui", "settings", T_KIT, "Settings (a gear)")
def ui_settings(c):
    c.poly(gear_pts(0.5, 0.5, 0.5, 0.38, 8, rot_deg=-90 - 45 * 0.31))
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.17)


@icon("ui", "help", T_KIT, "Help (an open tome)")
def ui_help(c):
    with c.box(0.0, 0.16, 1.0, 0.92):
        g_book(c)
    c.poly([(0.46, 0.8), (0.54, 0.8), (0.54, 1.0), (0.5, 0.95), (0.46, 1.0)])


@icon("ui", "map", T_KIT, "Map (a folded chart with a route)")
def ui_map(c):
    c.poly([(0.0, 0.14), (0.32, 0.04), (0.66, 0.14), (1.0, 0.04), (1.0, 0.86), (0.66, 0.96), (0.32, 0.86), (0.0, 0.96)])
    with c.op("shade"):
        c.poly([(0.32, 0.04), (0.66, 0.14), (0.66, 0.96), (0.32, 0.86)])
    with c.op("cut"):
        c.line([(0.14, 0.76), (0.3, 0.56), (0.5, 0.62), (0.7, 0.38)], 0.04)
        c.line([(0.76, 0.2), (0.88, 0.32)], 0.05)
        c.line([(0.88, 0.2), (0.76, 0.32)], 0.05)


@icon("ui", "spark4", T_KIT, "A four-point spark (crit spark, ready gleam)")
def ui_spark4(c):
    g_spark4(c, 0.12)


# ───────────────────────────── input prompts (no letters, no colours, no trademarks) ─────────────────────────────
def g_mouse(c, lit: str):
    body = (Path(0.5, 0.02).C(0.78, 0.02, 0.92, 0.2, 0.92, 0.44).L(0.92, 0.66).C(0.92, 0.88, 0.74, 1.0, 0.5, 1.0)
            .C(0.26, 1.0, 0.08, 0.88, 0.08, 0.66).L(0.08, 0.44).C(0.08, 0.2, 0.22, 0.02, 0.5, 0.02).pts())
    c.poly(body)
    with c.op("shade"):
        c.poly(body)
    with c.op("cut"):
        c.rect(0.08, 0.42, 0.92, 0.46)
        c.rect(0.48, 0.02, 0.52, 0.44)
    left = Path(0.46, 0.06).C(0.26, 0.08, 0.14, 0.2, 0.14, 0.38).L(0.46, 0.38).pts()
    right = [(1 - x, y) for x, y in left]
    if lit == "lmb":
        with c.op("unshade"):
            c.poly(left)
    elif lit == "rmb":
        with c.op("unshade"):
            c.poly(right)
    wheel_on = lit in ("mmb", "wheel")
    with c.op("cut"):
        c.rect(0.42, 0.12, 0.58, 0.36, r=0.08)
    c.rect(0.445, 0.14, 0.555, 0.34, r=0.05)
    if wheel_on:
        with c.op("unshade"):
            c.rect(0.445, 0.14, 0.555, 0.34, r=0.05)


def _mouse_wheel(c):
    with c.box(0.16, 0.0, 0.84, 1.0):
        g_mouse(c, "wheel")
    c.poly([(0.94, 0.0), (1.08, 0.16), (0.8, 0.16)])
    c.poly([(0.94, 0.5), (1.08, 0.34), (0.8, 0.34)])


for _b, _m in (("lmb", "left button"), ("rmb", "right button"), ("mmb", "middle button (wheel press)")):
    reg("input", f"mouse_{_b}", (lambda c, b=_b: g_mouse(c, b)), T_KIT, f"Mouse {_m} (the lit part)")
reg("input", "mouse_wheel", _mouse_wheel, T_KIT, "Mouse wheel scroll (the lit wheel with up and down arrows)")


def g_face_studs(c, lit: int):
    """Four round studs in a diamond; the lit one marks the position (0 south, 1 east, 2 west, 3 north)."""
    spots = {0: (0.5, 0.8), 1: (0.8, 0.5), 2: (0.2, 0.5), 3: (0.5, 0.2)}
    for i, (x, y) in spots.items():
        r = 0.2 if i == lit else 0.14
        c.circle(x, y, r)
        if i != lit:
            with c.op("shade"):
                c.circle(x, y, r)
        else:
            with c.op("cut"):
                c.ring(x, y, r - 0.05, 0.025)


for _i, _pos in enumerate(("south", "east", "west", "north")):
    reg("input", f"pad_{_pos}", (lambda c, i=_i: g_face_studs(c, i)), T_KIT,
        f"Gamepad {_pos} face button (a lit stud in the {_pos} position; no colours, no letters)")


def g_bumper(c, right: bool):
    pts = Path(0.04, 0.9).L(0.04, 0.52).C(0.04, 0.26, 0.2, 0.1, 0.46, 0.1).L(0.96, 0.1).L(0.96, 0.9).pts()
    if right:
        pts = [(1 - x, y) for x, y in pts]
    c.poly(pts)
    with c.op("cut"):
        c.rect(0.0, 0.64, 1.0, 0.7)
    with c.op("shade"):
        c.rect(0.0, 0.7, 1.0, 0.92)


def g_trigger(c, right: bool):
    pts = Path(0.22, 1.0).L(0.22, 0.46).C(0.22, 0.18, 0.4, 0.0, 0.66, 0.0).C(0.84, 0.0, 0.9, 0.14, 0.9, 0.3).L(0.9, 1.0).pts()
    if right:
        pts = [(1 - x, y) for x, y in pts]
    c.poly(pts)
    with c.op("shade"):
        c.rect(0.0, 0.66, 1.0, 1.0)
    with c.op("cut"):
        c.rect(0.0, 0.6, 1.0, 0.66)


def _side_dots(c, right: bool):
    for i, x in enumerate((0.3, 0.7)):
        on = (i == 1) == right
        c.circle(x, 1.0, 0.09 if on else 0.06)
        if not on:
            with c.op("shade"):
                c.circle(x, 1.0, 0.06)


def g_stick(c, right: bool, click: bool = False):
    c.circle(0.5, 0.44, 0.44)
    with c.op("shade"):
        c.circle(0.5, 0.44, 0.44)
    c.circle(0.5, 0.44, 0.3)
    with c.op("cut"):
        c.ring(0.5, 0.44, 0.2, 0.03)
    if click:
        with c.op("cut"):
            c.circle(0.5, 0.44, 0.1)
        c.poly([(0.5, 0.52), (0.38, 0.36), (0.62, 0.36)])
    _side_dots(c, right)


for _side in ("l", "r"):
    _right = _side == "r"
    _word = "right" if _right else "left"
    reg("input", f"pad_{_side}b", (lambda c, r=_right: g_bumper(c, r)), T_KIT,
        f"Gamepad {_word} bumper (the shape leans to its side; no letters)")
    reg("input", f"pad_{_side}t", (lambda c, r=_right: g_trigger(c, r)), T_KIT,
        f"Gamepad {_word} trigger (the shape leans to its side; no letters)")
    reg("input", f"pad_{_side}s", (lambda c, r=_right: g_stick(c, r)), T_KIT,
        f"Gamepad {_word} stick (the lit dot below marks the side)")
    reg("input", f"pad_{_side}s_click", (lambda c, r=_right: g_stick(c, r, True)), T_KIT,
        f"Gamepad {_word} stick press (a press chevron; the lit dot marks the side)")


def g_dpad(c, lit: str):
    arms = {"up": (0.34, 0.0, 0.66, 0.4), "down": (0.34, 0.6, 0.66, 1.0), "left": (0.0, 0.34, 0.4, 0.66),
            "right": (0.6, 0.34, 1.0, 0.66)}
    c.rect(0.3, 0.3, 0.7, 0.7)
    for k, (x0, y0, x1, y1) in arms.items():
        c.rect(x0, y0, x1, y1, r=0.05)
    with c.op("shade"):
        c.rect(0.0, 0.0, 1.0, 1.0)
    with c.op("unshade"):
        x0, y0, x1, y1 = arms[lit]
        c.rect(x0, y0, x1, y1, r=0.05)
    with c.op("cut"):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[lit]
        tip = (cx + d[0] * 0.1, cy + d[1] * 0.1)
        base = (cx - d[0] * 0.06, cy - d[1] * 0.06)
        side = (-d[1] * 0.09, d[0] * 0.09)
        c.poly([tip, (base[0] + side[0], base[1] + side[1]), (base[0] - side[0], base[1] - side[1])])


for _d in ("up", "down", "left", "right"):
    reg("input", f"pad_dpad_{_d}", (lambda c, d=_d: g_dpad(c, d)), T_KIT, f"Gamepad d-pad {_d} (the lit arm)")


@icon("input", "pad_view", T_KIT, "Gamepad view button (a small centre pill with a window mark; no trademark glyph)")
def in_view(c):
    c.rect(0.0, 0.22, 1.0, 0.78, r=0.28)
    with c.op("cut"):
        c.rect(0.3, 0.36, 0.7, 0.64, r=0.04)
    c.rect(0.36, 0.42, 0.64, 0.58)


@icon("input", "pad_menu", T_KIT, "Gamepad menu button (a small centre pill with three lines)")
def in_menu(c):
    c.rect(0.0, 0.22, 1.0, 0.78, r=0.28)
    with c.op("cut"):
        for y in (0.36, 0.5, 0.64):
            c.rect(0.3, y - 0.025, 0.7, y + 0.025, r=0.02)


def w_bellowfire_projector(c):
    c.poly([(0.02, 0.2), (0.14, 0.26), (0.36, 0.4), (0.36, 0.62), (0.14, 0.76), (0.02, 0.82)])
    with c.op("cut"):
        for x in (0.1, 0.18, 0.26):
            c.line([(x, 0.28 + (x - 0.1) * 0.6), (x, 0.74 - (x - 0.1) * 0.6)], 0.022, cap=False)
    c.rect(0.34, 0.4, 0.58, 0.62, r=0.03)
    c.poly([(0.56, 0.44), (0.7, 0.46), (0.7, 0.56), (0.56, 0.58)])
    with c.place(0.84, 0.51, 0.44, r=90):
        g_flame(c, core=True)


# ───────────────────────────── motif library (parts and boons) ─────────────────────────────
def sub(c, fn, x, y, s, r=0.0, knock=0.0, sx=None, **kw):
    """Draw atom `fn` centred at (x, y) with side s; `knock` first cuts a clear disc around it."""
    if knock:
        with c.op("cut"):
            c.circle(x, y, s * 0.5 + knock)
    with c.place(x, y, s, r=r, sx=sx):
        fn(c, **kw)


def m_chain(c):
    """Chain lightning: three nodes linked by short bolts."""
    nodes = [(0.12, 0.78), (0.5, 0.26), (0.88, 0.7)]
    for (x0, y0), (x1, y1) in zip(nodes[:-1], nodes[1:]):
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        nx, ny = -(y1 - y0), (x1 - x0)
        ln = math.hypot(nx, ny)
        nx, ny = nx / ln * 0.08, ny / ln * 0.08
        c.line([(x0, y0), (mx + nx, my + ny), (mx - nx, my - ny), (x1, y1)], 0.07)
    for x, y in nodes:
        c.circle(x, y, 0.12)


def m_ricochet(c):
    pts = [(0.02, 0.2), (0.3, 0.84), (0.6, 0.2), (0.8, 0.62)]
    c.line(pts, 0.09)
    c.poly([(0.72, 0.52), (1.0, 0.92), (0.64, 0.84)])
    for x, y, up in ((0.3, 0.84, False), (0.6, 0.2, True)):
        c.rect(x - 0.14, y + (-0.1 if up else 0.06), x + 0.14, y + (-0.06 if up else 0.1))


def m_fork(c, n=2, spread=34.0):
    c.line([(0.04, 0.5), (0.46, 0.5)], 0.1)
    c.circle(0.46, 0.5, 0.08)
    angs = [0.0] if n == 1 else [(-spread + 2 * spread * i / (n - 1)) for i in range(n)]
    for a in angs:
        with c.at(0.46, 0.5, r=a):
            c.rect(0.0, -0.04, 0.34, 0.04)
            c.poly([(0.3, -0.12), (0.54, 0.0), (0.3, 0.12)])


def m_multishot(c, n=3, spread=22.0):
    for i in range(n):
        a = -spread + 2 * spread * i / max(1, n - 1)
        with c.at(0.5, 0.98, r=a):
            c.rect(-0.04, -0.66, 0.04, 0.0)
            c.poly([(-0.12, -0.62), (0.0, -0.96), (0.12, -0.62)])


def m_pierce(c, bars=3):
    for i in range(bars):
        x = 0.34 + i * 0.2 - (bars - 3) * 0.08
        c.rect(x - 0.05, 0.1, x + 0.05, 0.9, r=0.02)
    with c.op("cut"):
        c.rect(0.0, 0.42, 1.0, 0.58)
    c.rect(0.0, 0.455, 0.84, 0.545)
    c.poly([(0.76, 0.32), (1.0, 0.5), (0.76, 0.68)])


def m_homing(c):
    c.ring(0.76, 0.26, 0.2, 0.06)
    c.circle(0.76, 0.26, 0.06)
    pts = cubic((0.06, 0.94), (0.1, 0.4), (0.5, 0.9), (0.6, 0.44), 30)
    c.taper(pts, 0.05, 0.1)
    c.poly([(0.5, 0.46), (0.68, 0.3), (0.7, 0.54)])


def m_orbit(c, n=3, blade=g_sawblade):
    c.circle(0.5, 0.5, 0.12)
    c.ring(0.5, 0.5, 0.36, 0.04)
    for i in range(n):
        p = polar(0.5, 0.5, 0.36, -90 + i * 360 / n)
        sub(c, blade, p[0], p[1], 0.3, knock=0.03)


def m_beam(c, sweep=True, width=0.2):
    c.circle(0.14, 0.5, 0.14)
    with c.op("cut"):
        c.ring(0.14, 0.5, 0.09, 0.03)
    c.poly([(0.22, 0.5 - width / 2), (1.0, 0.5 - width / 2 - 0.05), (1.0, 0.5 + width / 2 + 0.05), (0.22, 0.5 + width / 2)])
    with c.op("shade"):
        c.poly([(0.22, 0.5), (1.0, 0.5), (1.0, 0.5 + width / 2 + 0.05), (0.22, 0.5 + width / 2)])
    if sweep:
        c.arc(0.14, 0.5, 0.78, -38, -20, 0.06)
        c.arc(0.14, 0.5, 0.78, 20, 38, 0.06)


def m_echo(c):
    """A shot and its two ringing echoes."""
    with c.place(0.74, 0.5, 0.56, r=90):
        g_bullet(c)
    for i, r in enumerate((0.24, 0.36)):
        c.arc(0.56, 0.5, r, 130, 230, 0.07)


def m_trail(c):
    """A shot dragging a wavy wake."""
    c.circle(0.8, 0.3, 0.16)
    for i, off in enumerate((-0.1, 0.1)):
        pts = [(0.72 - t * 0.7, 0.34 + off + t * 0.5 + 0.05 * math.sin(t * 14)) for t in [j / 30 for j in range(31)]]
        c.taper(pts, 0.09, 0.02)


def m_puddle(c):
    c.ellipse(0.5, 0.78, 0.48, 0.18)
    with c.op("shade"):
        c.ellipse(0.5, 0.8, 0.36, 0.1)
    for x, y, r in ((0.5, 0.36, 0.1), (0.28, 0.5, 0.07), (0.72, 0.5, 0.07)):
        c.circle(x, y, r)
    sub(c, g_drop, 0.5, 0.12, 0.22)


def m_explode(c):
    g_burst(c, 10, 0.5, 0.26)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.14)
    c.circle(0.5, 0.5, 0.08)


def m_bomb(c):
    c.circle(0.44, 0.58, 0.4)
    c.rect(0.52, 0.12, 0.72, 0.26, r=0.03)
    with c.op("cut"):
        c.circle(0.3, 0.44, 0.08)
    c.bez((0.64, 0.16), (0.72, 0.02), (0.84, 0.1), (0.9, 0.04), 0.04, 0.03)
    sub(c, g_spark4, 0.92, 0.04, 0.2)


def m_doom(c):
    """Doom stacks: three discs piled under a four-point star."""
    for i, y in enumerate((0.86, 0.66, 0.46)):
        w = 0.48 - i * 0.08
        c.ellipse(0.5, y, w, 0.1)
        with c.op("cut"):
            c.arc(0.5, y + 0.005, w * 0.98, 20, 160, 0.03, ry=0.09)
    sub(c, g_spark4, 0.5, 0.18, 0.36)


def m_crit(c):
    """A blade tip meeting a crit spark."""
    with c.place(0.36, 0.64, 0.8, r=45):
        g_dagger(c)
    sub(c, g_spark4, 0.76, 0.24, 0.46, knock=0.03)


def m_execute(c):
    """A headsman's axe."""
    c.line([(0.2, 0.98), (0.66, 0.06)], 0.08)
    c.poly(Path(0.52, 0.12).C(0.72, 0.02, 0.96, 0.14, 0.98, 0.42).C(0.84, 0.4, 0.7, 0.46, 0.62, 0.56).L(0.46, 0.4).pts())
    with c.op("shade"):
        c.poly(Path(0.62, 0.56).C(0.7, 0.46, 0.84, 0.4, 0.98, 0.42).L(0.9, 0.46).C(0.8, 0.46, 0.7, 0.5, 0.64, 0.58).pts())


def m_fang_drop(c):
    """Lifesteal: a drop with two fang cuts."""
    g_drop(c)
    with c.op("cut"):
        c.poly([(0.36, 0.5), (0.46, 0.5), (0.41, 0.72)])
        c.poly([(0.54, 0.5), (0.64, 0.5), (0.59, 0.72)])


def m_greed(c):
    """Shards falling from a cut stone."""
    sub(c, g_shard, 0.5, 0.36, 0.7)
    for x, y in ((0.14, 0.86), (0.86, 0.86), (0.5, 0.96)):
        sub(c, g_coin, x, y, 0.2)


def m_knockback(c):
    sub(c, g_fist_side, 0.38, 0.5, 0.74)
    for r in (0.34, 0.46):
        c.arc(0.46, 0.5, r, -40, 40, 0.06)


def m_gravity(c):
    g_spiral(c, turns=1.4, w0=0.12, w1=0.03)
    c.circle(0.5, 0.5, 0.08)


def m_spread(c, n=5):
    for i in range(n):
        a = -48 + 96 * i / (n - 1)
        with c.at(0.5, 0.96, r=a):
            c.circle(0.0, -0.78, 0.09)
            c.line([(0.0, -0.66), (0.0, -0.42)], 0.05)
    c.circle(0.5, 0.94, 0.1)


def m_charge(c):
    """A bow at full draw."""
    c.poly(Path(0.2, 0.02).C(0.5, 0.1, 0.62, 0.3, 0.62, 0.5).C(0.62, 0.7, 0.5, 0.9, 0.2, 0.98).L(0.24, 0.9)
           .C(0.44, 0.82, 0.52, 0.66, 0.52, 0.5).C(0.52, 0.34, 0.44, 0.18, 0.24, 0.1).pts())
    c.line([(0.22, 0.06), (0.02, 0.5), (0.22, 0.94)], 0.03)
    c.rect(0.02, 0.47, 0.88, 0.53)
    c.poly([(0.84, 0.38), (1.0, 0.5), (0.84, 0.62)])


def m_velocity(c):
    with c.place(0.62, 0.5, 0.76):
        g_arrow(c, fletch=False, head=0.34, w=0.12)
    for y, x0 in ((0.24, 0.1), (0.76, 0.1), (0.5, 0.0)):
        c.line([(x0, y), (x0 + 0.26, y)], 0.07)


def m_dash(c):
    for x in (0.18, 0.5):
        with c.place(x + 0.16, 0.5, 0.56, r=90):
            g_chevron(c, 0.3)
    for y in (0.3, 0.5, 0.7):
        c.line([(0.0, y), (0.14, y)], 0.06)


def m_dash_nova(c, inner=None):
    """A dash bursting into a ring: dash chevrons inside a burst ring, plus an inner element glyph."""
    c.ring(0.5, 0.5, 0.5, 0.08)
    for a in range(0, 360, 45):
        with c.op("cut"):
            c.line([polar(0.5, 0.5, 0.4, a + 22), polar(0.5, 0.5, 0.52, a + 22)], 0.035, cap=False)
    with c.place(0.5, 0.5, 0.52, r=90):
        g_chevron(c, 0.3)
    with c.place(0.34, 0.5, 0.4, r=90):
        g_chevron(c, 0.3)
    if inner:
        sub(c, inner, 0.72, 0.28, 0.3, knock=0.03)


def m_giant(c):
    """Elites and bosses: a great horned helm split by a sword."""
    c.poly(Path(0.22, 0.44).C(0.22, 0.2, 0.36, 0.1, 0.5, 0.1).C(0.64, 0.1, 0.78, 0.2, 0.78, 0.44).L(0.74, 0.86)
           .L(0.26, 0.86).pts())
    c.bez((0.24, 0.36), (0.08, 0.34), (0.02, 0.2), (0.06, 0.04), 0.1, 0.02)
    c.bez((0.76, 0.36), (0.92, 0.34), (0.98, 0.2), (0.94, 0.04), 0.1, 0.02)
    with c.op("cut"):
        c.rect(0.3, 0.44, 0.7, 0.5)
        c.poly(stroke_poly([(0.0, 1.02), (0.9, 0.12)], 0.16))
    c.poly(stroke_poly([(0.04, 0.98), (0.86, 0.16)], 0.07))
    c.poly(stroke_poly([(0.1, 0.8), (0.24, 0.94)], 0.08))


def m_low_hp(c):
    """A cracked heart with a fire in the crack."""
    g_heart(c)
    with c.op("cut"):
        c.line([(0.5, 0.22), (0.42, 0.42), (0.58, 0.56), (0.48, 0.76), (0.5, 0.94)], 0.08)


def m_clover(c):
    for a in (0, 90, 180, 270):
        with c.place(*polar(0.5, 0.44, 0.2, a - 90), 0.42, r=a):
            g_heart(c)
    c.bez((0.5, 0.5), (0.52, 0.7), (0.6, 0.86), (0.7, 0.98), 0.07, 0.04)


def m_nova(c):
    c.circle(0.5, 0.5, 0.18)
    c.ring(0.5, 0.5, 0.34, 0.06)
    for i in range(8):
        a = -90 + i * 45
        c.poly([polar(0.5, 0.5, 0.52, a), polar(0.5, 0.5, 0.4, a - 8), polar(0.5, 0.5, 0.4, a + 8)])


def m_shrapnel(c):
    c.circle(0.3, 0.7, 0.14)
    for a, ln in ((-70, 0.5), (-30, 0.56), (10, 0.46)):
        with c.at(0.3, 0.7, r=a):
            c.poly([(0.2, -0.05), (0.2 + ln, 0.0), (0.2, 0.05), (0.14, 0.0)])


def m_contagion(c):
    for (x, y, r) in ((0.24, 0.72, 0.18), (0.5, 0.3, 0.16), (0.78, 0.66, 0.14)):
        c.circle(x, y, r)
        with c.op("cut"):
            c.circle(x - r * 0.3, y - r * 0.2, r * 0.28)
    c.line([(0.24, 0.72), (0.5, 0.3), (0.78, 0.66)], 0.05)


def m_chaos(c):
    """A splinter breaking apart."""
    c.poly([(0.5, 0.0), (0.64, 0.3), (0.52, 0.5), (0.36, 0.3)])
    c.poly([(0.56, 0.54), (0.74, 0.4), (0.86, 0.74), (0.66, 1.0)])
    c.poly([(0.46, 0.56), (0.3, 0.4), (0.12, 0.66), (0.34, 0.96)])
    sub(c, g_spark4, 0.86, 0.16, 0.24)
    sub(c, g_spark4, 0.14, 0.2, 0.18)


def m_heart_plus(c):
    g_heart(c)
    with c.op("cut"):
        c.rect(0.44, 0.3, 0.56, 0.7, r=0.02)
        c.rect(0.3, 0.44, 0.7, 0.56, r=0.02)


def m_regen(c):
    g_heart(c)
    with c.op("cut"):
        for x in (0.32, 0.5, 0.68):
            c.poly([(x, 0.3), (x + 0.08, 0.44), (x + 0.03, 0.44), (x + 0.03, 0.62), (x - 0.03, 0.62), (x - 0.03, 0.44), (x - 0.08, 0.44)])


def m_winged_boot(c):
    sub(c, g_boot, 0.58, 0.58, 0.8)
    with c.place(0.22, 0.34, 0.5, sx=-1):
        g_wing(c, 3)


def m_fire_rate(c):
    for i, x in enumerate((0.3, 0.55, 0.8)):
        with c.place(x, 0.46, 0.5):
            g_bullet(c)
    for x in (0.3, 0.55, 0.8):
        c.line([(x, 0.78), (x, 0.98)], 0.06)


def m_area(c):
    c.circle(0.5, 0.5, 0.14)
    c.ring(0.5, 0.5, 0.3, 0.06)
    for a in (-45, 45, 135, 225):
        p0 = polar(0.5, 0.5, 0.36, a)
        p1 = polar(0.5, 0.5, 0.5, a)
        c.line([p0, p1], 0.07)
        with c.place(p1[0], p1[1], 0.2, r=a + 90):
            g_chevron(c, 0.4)


def m_cooldown(c):
    """Actives recover faster: an ability tile inside a turning arrow."""
    g_cw_arrow(c, 250, 520, r=0.44, w=0.09)
    c.poly([(0.36, 0.3), (0.64, 0.3), (0.72, 0.38), (0.72, 0.62), (0.64, 0.7), (0.36, 0.7), (0.28, 0.62), (0.28, 0.38)])
    with c.op("cut"):
        c.star(0.5, 0.5, 0.14, 0.05, 4)


def m_active(c, inner=None):
    """Active damage: a chamfered ability tile with a burst."""
    c.poly([(0.22, 0.0), (0.78, 0.0), (1.0, 0.22), (1.0, 0.78), (0.78, 1.0), (0.22, 1.0), (0.0, 0.78), (0.0, 0.22)])
    with c.op("cut"):
        c.poly([(0.26, 0.1), (0.74, 0.1), (0.9, 0.26), (0.9, 0.74), (0.74, 0.9), (0.26, 0.9), (0.1, 0.74), (0.1, 0.26)])
    sub(c, inner or (lambda cc: g_burst(cc, 8, 0.5, 0.22)), 0.5, 0.5, 0.64)


def m_ult_ground(c, inner=None):
    """Ultimates scar the ground: a molten ring over a cracked patch, with the element glyph."""
    c.ellipse(0.5, 0.82, 0.5, 0.16)
    with c.op("cut"):
        c.line([(0.1, 0.8), (0.3, 0.84), (0.46, 0.76), (0.66, 0.86), (0.9, 0.8)], 0.04)
    sub(c, inner or g_flame, 0.5, 0.36, 0.62)


def m_range(c):
    """Further: an eye with a long arrow."""
    sub(c, g_eye, 0.24, 0.5, 0.48)
    c.rect(0.44, 0.47, 0.86, 0.53)
    c.poly([(0.8, 0.38), (1.0, 0.5), (0.8, 0.62)])
    for x in (0.56, 0.68):
        c.rect(x, 0.4, x + 0.03, 0.6)


def m_opener(c):
    """The first hit: an arrow in the bullseye of a whole target."""
    c.ring(0.44, 0.56, 0.42, 0.08)
    c.ring(0.44, 0.56, 0.24, 0.07)
    c.circle(0.44, 0.56, 0.08)
    with c.at(0.44, 0.56, r=-40):
        c.rect(0.0, -0.03, 0.66, 0.03)
        c.poly([(0.52, -0.1), (0.66, -0.03), (0.66, 0.03), (0.52, 0.1), (0.6, 0.0)])


def m_vs(c, glyph):
    """Damage against a status: a sword striking down into the status glyph."""
    sub(c, glyph, 0.36, 0.64, 0.7)
    with c.op("cut"):
        c.poly(stroke_poly([(1.04, -0.04), (0.34, 0.66)], 0.24))
    with c.place(0.62, 0.38, 0.86, r=-135):
        g_sword(c, 0.22, fuller=False)


def m_heavy(c):
    """A weight: an anvil with a down-chevron."""
    sub(c, g_anvil, 0.5, 0.64, 0.84)
    with c.place(0.5, 0.1, 0.36, r=180):
        g_chevron(c, 0.3)


def m_precise(c):
    g_reticle(c, gap=0.12, ring_r=0.3, w=0.05)
    c.ring(0.5, 0.5, 0.5, 0.04)


def m_cone(c, wide=True):
    """A short wide gout of force."""
    c.rect(0.0, 0.36, 0.2, 0.64, r=0.04)
    c.poly([(0.18, 0.4), (0.9, 0.04), (1.0, 0.5), (0.9, 0.96), (0.18, 0.6)])
    with c.op("cut"):
        for r in (0.42, 0.62):
            c.arc(0.18, 0.5, r, -38, 38, 0.035)


def m_shield_mark(c, glyph):
    g_shield(c, "half")
    sub(c, glyph, 0.5, 0.46, 0.44, knock=0.02)


# ───────────────────────────── parts ─────────────────────────────
# Cores: the motif glows inside a dark orb in the element hue. Sigils: the motif is a rune in a seal
# ring. Mechanisms and relics: the motif alone (the slot frame carries the category).

def core_orb(c):
    c.circle(0.5, 0.5, 0.5)
    with c.op("shade"):
        c.circle(0.5, 0.5, 0.41)
    for a in (-90, 0, 90, 180):
        with c.op("cut"):
            c.poly([polar(0.5, 0.5, 0.52, a - 5), polar(0.5, 0.5, 0.44, a), polar(0.5, 0.5, 0.52, a + 5)])


def sigil_ring(c):
    seal_ring(c, bumps=12, r=0.5, w=0.1)
    with c.op("shade"):
        c.circle(0.5, 0.5, 0.52)


# ---- core motifs
def pc_ember(c):
    g_flame(c)


def pc_storm(c):
    g_bolt(c)


def pc_void(c):
    m_gravity(c)


def pc_plague(c):
    m_puddle(c)


def pc_dawn(c):
    g_mark(c)


def pc_iron(c):
    with c.place(0.5, 0.5, 1.0, r=45):
        g_bullet(c)


def pc_shrapnel(c):
    m_shrapnel(c)


def pc_barb(c):
    c.poly([(0.02, 0.98), (0.12, 0.86), (0.86, 0.12), (0.98, 0.02), (0.9, 0.2), (0.16, 0.94)])
    for t in (0.3, 0.5, 0.7):
        x, y = 0.02 + t * 0.96, 0.98 - t * 0.96
        c.poly([(x, y), (x - 0.2, y - 0.02), (x - 0.05, y + 0.08)])


def pc_cairn(c):
    for (x, y, w, h) in ((0.5, 0.84, 0.46, 0.15), (0.48, 0.58, 0.34, 0.13), (0.52, 0.36, 0.24, 0.11), (0.5, 0.16, 0.14, 0.09)):
        c.ellipse(x, y, w, h)


def pc_slag(c):
    g_burst(c, 9, 0.5, 0.3)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.2)
    sub(c, g_drop, 0.5, 0.52, 0.3)


def pc_kiln(c):
    c.ellipse(0.5, 0.84, 0.48, 0.15)
    sub(c, g_flame, 0.5, 0.42, 0.66)


def pc_wick(c):
    c.bez((0.02, 0.96), (0.2, 0.6), (0.5, 0.9), (0.6, 0.46), 0.08, 0.06)
    sub(c, g_flame, 0.72, 0.26, 0.5)


def pc_tempest(c):
    sub(c, g_bolt, 0.5, 0.5, 0.86)
    sub(c, g_spark4, 0.12, 0.2, 0.26)
    sub(c, g_spark4, 0.88, 0.8, 0.26)


def pc_squall(c):
    g_storm(c)


def pc_hex(c):
    g_hexeye(c)


def pc_gloam(c):
    g_crescent(c, -0.2, -0.16, 0.48, 0.4)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.02)


def pc_blight(c):
    m_contagion(c)


def pc_miasma(c):
    with c.box(0.0, 0.3, 0.8, 0.96):
        g_cloud(c)
    c.circle(0.8, 0.26, 0.18)


def pc_gild(c):
    sub(c, g_coin, 0.36, 0.64, 0.66, emblem="star")
    c.line([(0.6, 0.4), (0.76, 0.2), (0.9, 0.36)], 0.07)
    c.poly([(0.84, 0.28), (1.0, 0.44), (0.82, 0.46)])


def pc_halo(c):
    c.poly(stroke_poly(arcpts(0.5, 0.24, 0.42, 0.16, 0, 360, 72), 0.1))
    with c.op("cut"):
        c.poly(stroke_poly(arcpts(0.5, 0.24, 0.42, 0.16, 20, 160, 30), 0.03))
    pts = cubic((0.08, 0.96), (0.14, 0.52), (0.62, 0.9), (0.72, 0.56), 30)
    c.taper(pts, 0.06, 0.1)
    c.poly([(0.6, 0.6), (0.8, 0.42), (0.84, 0.66)])


def pc_vitriol(c):
    g_flask(c)
    with c.op("cut"):
        c.line([(0.26, 0.6), (0.4, 0.72), (0.34, 0.86)], 0.04)
        c.line([(0.72, 0.56), (0.6, 0.7)], 0.04)


def pc_verdict(c):
    sub(c, g_lozenge, 0.5, 0.5, 0.96, hole=0.3)
    with c.place(0.5, 0.5, 0.56):
        g_bullet(c)


def pc_unmade(c):
    m_chaos(c)


# ---- mechanisms
def pm_ricochet_rosary(c):
    pts = [(0.04, 0.2), (0.32, 0.84), (0.62, 0.2), (0.9, 0.78)]
    c.line(pts, 0.035)
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        for t in (0.0, 0.34, 0.67):
            c.circle(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 0.085)
    c.poly([(0.8, 0.62), (1.0, 0.98), (0.7, 0.84)])


def pm_skipstone(c):
    c.rect(0.0, 0.86, 1.0, 0.92, r=0.02)
    for x0, x1, h in ((0.0, 0.36, 0.44), (0.36, 0.62, 0.3), (0.62, 0.82, 0.18)):
        c.poly(stroke_poly(arcpts((x0 + x1) / 2, 0.86, (x1 - x0) / 2, h, 180, 360, 30), 0.055))
    c.ellipse(0.88, 0.76, 0.12, 0.07, r=-15)
    for x in (0.36, 0.62):
        c.poly([(x - 0.07, 0.86), (x, 0.74), (x + 0.07, 0.86)])


def pm_hydra(c):
    for i, (bx, a) in enumerate(((0.2, -30), (0.5, 0), (0.8, 30))):
        with c.at(0.5, 0.98, r=a):
            c.bez((0.0, 0.0), (-0.12, -0.3), (0.12, -0.46), (0.0, -0.66), 0.13, 0.1)
            c.poly([(-0.1, -0.64), (0.1, -0.64), (0.04, -0.9), (-0.04, -0.9)])
            with c.op("cut"):
                c.circle(0.03, -0.74, 0.02)
    c.ellipse(0.5, 0.94, 0.22, 0.08)


def pm_compass_rose(c):
    c.star(0.5, 0.5, 0.5, 0.12, 4)
    c.star(0.5, 0.5, 0.34, 0.1, 4, rot_deg=-45)
    with c.op("shade"):
        for a in (-90, 0, 90, 180):
            c.poly([(0.5, 0.5), polar(0.5, 0.5, 0.5, a), polar(0.5, 0.5, 0.12, a + 45)])
    c.circle(0.5, 0.5, 0.06)


def pm_seeker(c):
    c.ring(0.84, 0.5, 0.15, 0.05)
    c.circle(0.84, 0.5, 0.045)
    for sgn in (-1, 1):
        pts = cubic((0.04, 0.5), (0.2, 0.5 + sgn * 0.56), (0.5, 0.5 + sgn * 0.5), (0.62, 0.5 + sgn * 0.16), 30)
        c.taper(pts, 0.06, 0.07)
        tip = (0.7, 0.5 + sgn * 0.06)
        c.poly([tip, (0.54, 0.5 + sgn * 0.08), (0.64, 0.5 + sgn * 0.28)])
    c.circle(0.04, 0.5, 0.07)


def pm_carrion(c):
    c.arc(0.5, 0.56, 0.42, 110, 400, 0.04)
    # a crow in flight
    c.poly(Path(0.2, 0.36).C(0.32, 0.22, 0.42, 0.26, 0.5, 0.36).C(0.58, 0.26, 0.68, 0.22, 0.8, 0.36)
           .C(0.7, 0.34, 0.62, 0.38, 0.56, 0.46).L(0.6, 0.58).L(0.5, 0.52).L(0.4, 0.58).L(0.44, 0.46)
           .C(0.38, 0.38, 0.3, 0.34, 0.2, 0.36).pts())
    c.circle(0.5, 0.8, 0.07)


def pm_railspike(c):
    c.poly([(0.16, 0.44), (0.8, 0.44), (1.0, 0.5), (0.8, 0.56), (0.16, 0.56)])
    c.rect(0.12, 0.36, 0.2, 0.64)
    for y, x0 in ((0.24, 0.2), (0.76, 0.2), (0.5, 0.0)):
        c.line([(x0 - (0.1 if y != 0.5 else 0.0), y), (x0 + (0.34 if y != 0.5 else 0.08), y)], 0.05)


def pm_impaler(c):
    for x in (0.2, 0.4, 0.6, 0.8):
        c.circle(x, 0.5, 0.1)
    with c.op("cut"):
        c.rect(0.0, 0.47, 1.0, 0.53)
    c.rect(0.0, 0.48, 0.9, 0.52)
    c.poly([(0.86, 0.42), (1.0, 0.5), (0.86, 0.58)])


def pm_cleave(c):
    m_fork(c, 3, 40.0)


def pm_tuning(c):
    c.poly(Path(0.36, 0.06).L(0.44, 0.06).L(0.44, 0.56).C(0.44, 0.62, 0.56, 0.62, 0.56, 0.56).L(0.56, 0.06).L(0.64, 0.06)
           .L(0.64, 0.58).C(0.64, 0.68, 0.56, 0.72, 0.54, 0.72).L(0.54, 0.98).L(0.46, 0.98).L(0.46, 0.72)
           .C(0.44, 0.72, 0.36, 0.68, 0.36, 0.58).pts())
    for sgn in (-1, 1):
        for r in (0.24, 0.36):
            c.arc(0.5, 0.3, r, (270 - 40 if sgn < 0 else 270 + 10) - 90, (270 - 10 if sgn < 0 else 270 + 40) - 90, 0.04)


def pm_arc_relay(c):
    """A conductor coil: a ringed column under a sphere throwing two arcs."""
    c.rect(0.08, 0.9, 0.62, 1.0, r=0.03)
    c.rect(0.28, 0.36, 0.42, 0.92)
    for y in (0.46, 0.58, 0.7, 0.82):
        c.rect(0.2, y - 0.04, 0.5, y + 0.04, r=0.03)
    with c.op("shade"):
        c.rect(0.35, 0.36, 0.5, 0.92)
    c.circle(0.35, 0.22, 0.16)
    with c.op("cut"):
        c.circle(0.3, 0.17, 0.045)
    c.line([(0.5, 0.18), (0.62, 0.3), (0.74, 0.14), (0.88, 0.28), (0.98, 0.16)], 0.06)
    c.line([(0.48, 0.32), (0.6, 0.48), (0.72, 0.4), (0.84, 0.58)], 0.05)


def pm_needle_ray(c):
    c.circle(0.14, 0.5, 0.14)
    with c.op("cut"):
        c.circle(0.14, 0.5, 0.05)
    c.poly([(0.24, 0.42), (1.0, 0.5), (0.24, 0.58)])
    with c.op("shade"):
        c.poly([(0.24, 0.5), (1.0, 0.5), (0.24, 0.58)])
    for x in (0.46, 0.7):
        c.line([(x, 0.3), (x + 0.1, 0.3)], 0.04)
        c.line([(x, 0.7), (x + 0.1, 0.7)], 0.04)


def pm_whirling_anvils(c):
    c.circle(0.5, 0.5, 0.08)
    c.arc(0.5, 0.5, 0.36, 0, 360, 0.03)
    for a in (-60, 120):
        p = polar(0.5, 0.5, 0.36, a)
        c.line([(0.5, 0.5), p], 0.03)
        sub(c, g_anvil, p[0], p[1], 0.36, knock=0.02)


def pm_razor_halo(c):
    c.ring(0.5, 0.5, 0.3, 0.05)
    for i in range(5):
        a = -90 + i * 72
        with c.at(*polar(0.5, 0.5, 0.36, a), r=a + 90):
            c.poly([(-0.14, 0.04), (0.16, -0.02), (0.14, 0.06), (-0.14, 0.1)])


def pm_gatling(c):
    c.circle(0.5, 0.5, 0.48)
    with c.op("shade"):
        c.circle(0.5, 0.5, 0.48)
    for i in range(6):
        p = polar(0.5, 0.5, 0.28, -90 + i * 60)
        with c.op("unshade"):
            c.circle(p[0], p[1], 0.12)
        with c.op("cut"):
            c.circle(p[0], p[1], 0.05)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.06)
    for a in (-30, 150):
        c.arc(0.5, 0.5, 0.58, a, a + 60, 0.05)


def pm_heavy_hand(c):
    sub(c, g_fist, 0.5, 0.42, 0.78, r=180)
    for x in (0.1, 0.9):
        c.line([(x, 0.06), (x, 0.34)], 0.06)
    c.rect(0.0, 0.9, 1.0, 0.96, r=0.02)
    for a in (200, 340):
        c.line([polar(0.5, 0.94, 0.3, a), polar(0.5, 0.94, 0.46, a)], 0.05)


def pm_quickdraw(c):
    with c.box(0.2, 0.0, 1.0, 1.0):
        m_charge(c)
    for y in (0.3, 0.7):
        c.line([(0.0, y), (0.2, y)], 0.06)


def pm_deep_draw(c):
    m_charge(c)
    c.rect(0.7, 0.2, 0.78, 0.8, r=0.02)
    with c.op("cut"):
        c.rect(0.68, 0.44, 0.8, 0.56)
    c.rect(0.66, 0.47, 0.82, 0.53)


def pm_resounding(c):
    sub(c, g_bell, 0.42, 0.52, 0.74)
    for r in (0.3, 0.42):
        c.arc(0.42, 0.52, r, -40, 30, 0.05)


def pm_choke(c):
    c.poly([(0.0, 0.1), (0.44, 0.38), (0.44, 0.62), (0.0, 0.9), (0.0, 0.76), (0.34, 0.56), (0.34, 0.44), (0.0, 0.24)])
    c.rect(0.44, 0.38, 0.72, 0.62, r=0.03)
    c.rect(0.72, 0.46, 1.0, 0.54)
    c.poly([(0.9, 0.38), (1.04, 0.5), (0.9, 0.62)])


def pm_sundering(c):
    with c.place(0.34, 0.6, 0.64, r=90):
        g_bullet(c)
    sub(c, lambda cc: g_burst(cc, 8, 0.5, 0.22), 0.78, 0.4, 0.5, knock=0.02)


def pm_split_carom(c):
    c.line([(0.02, 0.2), (0.3, 0.82), (0.52, 0.42)], 0.08)
    c.rect(0.16, 0.9, 0.44, 0.94)
    with c.at(0.52, 0.42, r=-20):
        for a in (-26, 26):
            with c.at(0.0, 0.0, r=a):
                c.rect(0.0, -0.035, 0.3, 0.035)
                c.poly([(0.26, -0.1), (0.46, 0.0), (0.26, 0.1)])


def pm_packhunt(c):
    for i, (y, a) in enumerate(((0.2, 16), (0.5, 0), (0.8, -16))):
        with c.at(0.02, y, r=a):
            pts = cubic((0.0, 0.0), (0.3, 0.12 * (1 - i)), (0.6, -0.08 * (1 - i)), (0.82, 0.0), 20)
            c.taper(pts, 0.05, 0.06)
            c.poly([(0.74, -0.1), (0.98, 0.0), (0.74, 0.1), (0.8, 0.0)])
            c.poly([(0.84, -0.04), (0.86, -0.16), (0.9, -0.03)])


def pm_chorus(c):
    for x, y in ((0.28, 0.82), (0.74, 0.7)):
        c.ellipse(x, y, 0.16, 0.11, r=-22)
    c.rect(0.38, 0.12, 0.46, 0.82)
    c.rect(0.84, 0.0, 0.92, 0.7)
    c.poly([(0.38, 0.12), (0.92, 0.0), (0.92, 0.14), (0.38, 0.26)])
    with c.op("cut"):
        c.poly([(0.46, 0.3), (0.84, 0.21), (0.84, 0.23), (0.46, 0.32)])


def pm_overclock(c):
    sub(c, g_gear, 0.58, 0.5, 0.84)
    for y in (0.3, 0.5, 0.7):
        c.line([(0.0, y), (0.16, y)], 0.07)


def pm_twin_barrel(c):
    for y in (0.3, 0.7):
        with c.place(0.6, y, 0.34, r=90):
            g_bullet(c)
        c.rect(0.0, y - 0.1, 0.4, y + 0.1, r=0.03)
    c.rect(0.08, 0.3, 0.24, 0.7)


def pm_lancet(c):
    m_pierce(c, 3)


def pm_scatter(c):
    m_spread(c, 5)


def pm_homing(c):
    m_homing(c)


def pm_beam(c):
    m_beam(c)


def pm_saw_orbit(c):
    m_orbit(c, 3)


def pm_gatling_hymn(c):
    pm_gatling(c)


def pm_titans_exhale(c):
    m_cone(c)


# ---- relics
def pr_splitspawn(c):
    sub(c, g_turret, 0.42, 0.6, 0.8)
    sub(c, g_spark4, 0.82, 0.2, 0.36, knock=0.02)


def pr_frostwake(c):
    c.circle(0.78, 0.28, 0.18)
    for i, off in enumerate((-0.12, 0.0, 0.12)):
        pts = [(0.66 - t * 0.64, 0.34 + off * 1.4 + t * 0.46 + 0.05 * math.sin(t * 12)) for t in [j / 30 for j in range(31)]]
        c.taper(pts, 0.08 if i == 1 else 0.06, 0.02)
    sub(c, g_hourglass, 0.2, 0.2, 0.32, knock=0.03)


def pr_volatile_heart(c):
    g_heart(c)
    for a in range(-90, 270, 45):
        c.poly([polar(0.5, 0.5, 0.56, a), polar(0.5, 0.5, 0.42, a - 7), polar(0.5, 0.5, 0.42, a + 7)])
    with c.op("cut"):
        c.star(0.5, 0.5, 0.2, 0.08, 5)


def pr_greedstone(c):
    m_greed(c)


def pr_executioners_seal(c):
    m_execute(c)
    with c.op("cut"):
        c.circle(0.2, 0.78, 0.25)
    with c.place(0.2, 0.78, 0.4):
        seal_ring(c, bumps=10, r=0.5, w=0.5)
        with c.op("cut"):
            c.circle(0.5, 0.5, 0.2)


def pr_nyctian_eye(c):
    c.poly(Path(0.0, 0.5).Q(0.5, -0.04, 1.0, 0.5).Q(0.5, 1.04, 0.0, 0.5).pts())
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.22)
    c.poly([(0.5, 0.3), (0.58, 0.5), (0.5, 0.7), (0.42, 0.5)])


def pr_bloodletter(c):
    with c.place(0.5, 0.36, 0.72, r=-45):
        g_dagger(c)
    for x, y, s in ((0.3, 0.72, 0.24), (0.52, 0.86, 0.2), (0.16, 0.92, 0.16)):
        sub(c, g_drop, x, y, s)


def pr_giantsbane(c):
    m_giant(c)


def pr_brand(c, glyph):
    """A branding iron: a rod ending in a stamp face bearing the glyph."""
    c.line([(0.02, 0.98), (0.42, 0.58)], 0.09)
    c.rect(0.0, 0.86, 0.16, 1.02, r=0.03)
    with c.at(0.64, 0.36, r=-45):
        c.rect(-0.3, -0.3, 0.3, 0.3, r=0.06)
        c.rect(-0.36, 0.26, 0.36, 0.36, r=0.03)
    with c.op("cut"):
        with c.place(0.64, 0.36, 0.4, r=-45):
            glyph(c)


def pr_coal_tongue(c):
    pr_brand(c, g_flame_simple)


def pr_stormglass(c):
    c.poly(Path(0.36, 0.2).L(0.64, 0.2).L(0.64, 0.4).C(0.84, 0.48, 0.86, 0.9, 0.5, 0.98).C(0.14, 0.9, 0.16, 0.48, 0.36, 0.4).pts())
    c.rect(0.32, 0.04, 0.68, 0.18, r=0.03)
    with c.op("cut"):
        c.poly(Path(0.42, 0.44).C(0.28, 0.52, 0.26, 0.84, 0.5, 0.9).C(0.74, 0.84, 0.72, 0.52, 0.58, 0.44).pts())
    sub(c, g_bolt, 0.5, 0.68, 0.38)


def pr_hexnail(c):
    c.poly([(0.44, 0.28), (0.56, 0.28), (0.53, 0.86), (0.5, 1.0), (0.47, 0.86)])
    sub(c, g_hexeye, 0.5, 0.16, 0.5)


def pr_rootbinder(c):
    g_roots(c)
    c.ring(0.5, 0.46, 0.2, 0.08)


def pr_quarry_brand(c):
    pr_brand(c, g_mark)


def pr_ashen_covenant(c):
    m_vs(c, g_flame)


def pr_stormcatcher(c):
    c.rect(0.46, 0.34, 0.54, 1.0)
    c.poly([(0.5, 0.18), (0.58, 0.36), (0.42, 0.36)])
    c.rect(0.3, 0.62, 0.7, 0.68)
    c.rect(0.24, 0.94, 0.76, 1.0)
    with c.place(0.3, 0.12, 0.34, r=-20):
        g_bolt(c)


def pr_ledger(c):
    with c.box(0.0, 0.14, 1.0, 1.0):
        g_book(c)
    sub(c, g_hexeye, 0.5, 0.3, 0.46, knock=0.03)


def pr_pinning_stake(c):
    with c.box(0.1, 0.62, 0.9, 1.0):
        g_roots(c)
    c.poly([(0.4, 0.0), (0.6, 0.0), (0.58, 0.62), (0.5, 0.82), (0.42, 0.62)])
    c.rect(0.34, 0.0, 0.66, 0.1, r=0.02)


def pr_salt_wound(c):
    m_vs(c, g_drop)


def pr_scale_judgement(c):
    g_scales(c)
    sub(c, g_mark, 0.18, 0.62, 0.28, knock=0.02)


def pr_leech_crown(c):
    g_crown(c, 5)
    for x, h in ((0.22, 0.18), (0.5, 0.26), (0.78, 0.18)):
        c.poly(teardrop_pts(x, 0.84 + h, 0.05, h * 0.9, 0.0)[::-1])


def pr_ichor_chalice(c):
    c.poly(Path(0.14, 0.12).L(0.86, 0.12).C(0.86, 0.46, 0.7, 0.58, 0.56, 0.6).L(0.56, 0.82).L(0.76, 0.92).L(0.76, 1.0)
           .L(0.24, 1.0).L(0.24, 0.92).L(0.44, 0.82).L(0.44, 0.6).C(0.3, 0.58, 0.14, 0.46, 0.14, 0.12).pts())
    with c.op("shade"):
        c.poly(Path(0.2, 0.2).L(0.8, 0.2).C(0.8, 0.4, 0.66, 0.5, 0.5, 0.5).C(0.34, 0.5, 0.2, 0.4, 0.2, 0.2).pts())
    sub(c, g_drop, 0.5, 0.0, 0.2)


def pr_hound9(c):
    sub(c, g_turret, 0.36, 0.62, 0.66)
    sub(c, g_turret, 0.76, 0.32, 0.46)
    sub(c, g_gear, 0.82, 0.82, 0.3)


def pr_sentry_seed(c):
    c.poly(Path(0.0, 1.0).C(0.1, 0.84, 0.3, 0.8, 0.5, 0.8).C(0.7, 0.8, 0.9, 0.84, 1.0, 1.0).pts())
    c.bez((0.5, 0.82), (0.46, 0.7), (0.54, 0.62), (0.5, 0.52), 0.07, 0.05)
    c.poly(Path(0.5, 0.7).C(0.6, 0.56, 0.8, 0.56, 0.9, 0.62).C(0.8, 0.74, 0.62, 0.78, 0.5, 0.7).pts())
    c.poly(Path(0.5, 0.64).C(0.4, 0.52, 0.2, 0.52, 0.1, 0.58).C(0.2, 0.7, 0.38, 0.72, 0.5, 0.64).pts())
    sub(c, g_turret, 0.54, 0.26, 0.5)


def pr_funeral_bell(c):
    g_bell(c)
    with c.op("cut"):
        c.poly([(0.5, 0.26), (0.56, 0.36), (0.5, 0.46), (0.44, 0.36)])


def pr_epitaph(c):
    c.poly(Path(0.14, 1.0).L(0.14, 0.36).C(0.14, 0.14, 0.3, 0.02, 0.5, 0.02).C(0.7, 0.02, 0.86, 0.14, 0.86, 0.36).L(0.86, 1.0).pts())
    with c.op("cut"):
        for x in (0.3, 0.42, 0.54, 0.66):
            c.rect(x - 0.02, 0.36, x + 0.02, 0.7)
        c.poly(stroke_poly([(0.24, 0.66), (0.76, 0.4)], 0.035))


def pr_pyre_lung(c):
    for sgn in (-1, 1):
        x = lambda v: 0.5 + sgn * (v - 0.5)
        c.poly(Path(x(0.46), 0.3).C(x(0.3), 0.24, x(0.08), 0.46, x(0.08), 0.8).C(x(0.08), 0.96, x(0.3), 0.98, x(0.44), 0.86).pts())
    c.rect(0.46, 0.02, 0.54, 0.36)
    c.line([(0.5, 0.34), (0.38, 0.46)], 0.05)
    c.line([(0.5, 0.34), (0.62, 0.46)], 0.05)
    sub(c, g_flame, 0.5, 0.72, 0.36, knock=0.02)


def pr_dying_star(c):
    c.star(0.5, 0.5, 0.3, 0.12, 8)
    c.ring(0.5, 0.5, 0.5, 0.06)
    for a in range(-90, 270, 45):
        with c.place(*polar(0.5, 0.5, 0.36, a), 0.14, r=a - 90):
            g_chevron(c, 0.4)


def pr_reapers_tithe(c):
    c.line([(0.2, 1.0), (0.6, 0.04)], 0.07)
    c.poly(Path(0.58, 0.08).C(0.3, -0.02, 0.06, 0.12, 0.0, 0.38).C(0.14, 0.22, 0.34, 0.16, 0.56, 0.2).pts())
    sub(c, g_shard, 0.8, 0.66, 0.46, knock=0.02)


def pr_misericorde(c):
    c.poly([(0.5, 0.0), (0.55, 0.14), (0.54, 0.64), (0.46, 0.64), (0.45, 0.14)])
    c.rect(0.24, 0.62, 0.76, 0.69, r=0.03)
    c.circle(0.24, 0.655, 0.06)
    c.circle(0.76, 0.655, 0.06)
    c.rect(0.45, 0.68, 0.55, 0.9)
    c.circle(0.5, 0.93, 0.07)


def pr_anvil_plate(c):
    c.poly(Path(0.12, 0.06).L(0.34, 0.02).C(0.4, 0.12, 0.6, 0.12, 0.66, 0.02).L(0.88, 0.06).L(0.94, 0.4).C(0.9, 0.7, 0.76, 0.9, 0.5, 1.0)
           .C(0.24, 0.9, 0.1, 0.7, 0.06, 0.4).pts())
    with c.op("shade"):
        c.poly(Path(0.5, 0.1).C(0.6, 0.1, 0.62, 0.06, 0.66, 0.02).L(0.88, 0.06).L(0.94, 0.4).C(0.9, 0.7, 0.76, 0.9, 0.5, 1.0).pts())
    with c.op("cut"):
        with c.box(0.26, 0.3, 0.74, 0.72):
            c.poly(ANVIL)


def pr_gilded_aegis(c):
    g_round_shield(c)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.2)
    sub(c, g_radiant, 0.5, 0.5, 0.34)


def pr_beating_stone(c):
    sub(c, g_heart, 0.5, 0.56, 0.8)
    with c.op("cut"):
        c.line([(0.2, 0.54), (0.36, 0.54), (0.44, 0.36), (0.54, 0.72), (0.62, 0.5), (0.8, 0.5)], 0.045)
    for sgn in (-1, 1):
        c.arc(0.5, 0.52, 0.52, 270 + sgn * 70 - 12, 270 + sgn * 70 + 12, 0.05)


def pr_ember_of_ruin(c):
    g_heart(c)
    with c.op("cut"):
        c.line([(0.5, 0.22), (0.42, 0.4), (0.5, 0.48)], 0.07)
        with c.box(0.36, 0.44, 0.64, 0.86):
            g_flame_simple(c)


def pr_brink_coin(c):
    g_coin(c)
    with c.op("cut"):
        c.line([(0.36, 0.16), (0.46, 0.4), (0.38, 0.56), (0.5, 0.84)], 0.05)
    sub(c, g_skull, 0.66, 0.56, 0.32, knock=0.02)


def pr_opening_verse(c):
    m_opener(c)


def pr_titanbreaker(c):
    sub(c, g_boulder, 0.5, 0.64, 0.72)
    with c.op("cut"):
        c.poly([(0.36, 0.0), (0.64, 0.0), (0.54, 0.72), (0.46, 0.72)])
    c.poly([(0.4, 0.0), (0.6, 0.0), (0.5, 0.6)])


def pr_knucklebone(c):
    c.poly(Path(0.2, 0.3).C(0.08, 0.2, 0.1, 0.02, 0.28, 0.06).C(0.4, 0.1, 0.44, 0.22, 0.5, 0.26).C(0.56, 0.22, 0.6, 0.1, 0.72, 0.06)
           .C(0.9, 0.02, 0.92, 0.2, 0.8, 0.3).C(0.7, 0.4, 0.7, 0.6, 0.8, 0.7).C(0.92, 0.8, 0.9, 0.98, 0.72, 0.94)
           .C(0.6, 0.9, 0.56, 0.78, 0.5, 0.74).C(0.44, 0.78, 0.4, 0.9, 0.28, 0.94).C(0.1, 0.98, 0.08, 0.8, 0.2, 0.7)
           .C(0.3, 0.6, 0.3, 0.4, 0.2, 0.3).pts())
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.08)
    with c.op("shade"):
        c.poly([(0.5, 0.26), (0.72, 0.06), (0.9, 0.2), (0.8, 0.3), (0.7, 0.5), (0.8, 0.7), (0.9, 0.9), (0.72, 0.94), (0.5, 0.74)])


def pr_headsman_hood(c):
    c.poly(Path(0.5, 0.0).C(0.64, 0.1, 0.84, 0.3, 0.84, 0.62).L(0.96, 1.0).L(0.04, 1.0).L(0.16, 0.62).C(0.16, 0.3, 0.36, 0.1, 0.5, 0.0).pts())
    with c.op("cut"):
        c.poly([(0.28, 0.42), (0.46, 0.46), (0.42, 0.54), (0.3, 0.52)])
        c.poly([(0.72, 0.42), (0.54, 0.46), (0.58, 0.54), (0.7, 0.52)])
    with c.op("shade"):
        c.poly([(0.5, 0.0), (0.64, 0.1), (0.84, 0.3), (0.84, 0.62), (0.96, 1.0), (0.5, 1.0)])


def pr_razorwake(c):
    with c.place(0.64, 0.36, 0.56, r=-35):
        c.poly([(0.0, 0.3), (1.0, 0.36), (0.96, 0.62), (0.04, 0.7)])
        with c.op("cut"):
            c.rect(0.3, 0.46, 0.6, 0.54, r=0.03)
    for i in range(3):
        y = 0.56 + i * 0.14
        c.bez((0.02, y + 0.1), (0.2, y - 0.04), (0.34, y + 0.04), (0.46 - i * 0.04, y - 0.1), 0.05, 0.02)


def pr_tarpit(c):
    sub(c, g_heart, 0.5, 0.4, 0.66)
    c.ellipse(0.5, 0.78, 0.5, 0.2)
    with c.op("shade"):
        c.ellipse(0.5, 0.78, 0.5, 0.2)
    with c.op("cut"):
        c.poly(stroke_poly(arcpts(0.5, 0.64, 0.32, 0.06, 200, 340, 30), 0.03))
    for x in (0.3, 0.72):
        c.poly(teardrop_pts(x, 0.64, 0.035, 0.12, 0.0)[::-1])


def pr_gyrestone(c):
    for r, w in ((0.5, 0.05), (0.38, 0.05)):
        c.ring(0.5, 0.5, r, w)
    c.poly([(0.5, 0.26), (0.7, 0.4), (0.66, 0.68), (0.4, 0.74), (0.28, 0.5)])
    with c.op("cut"):
        c.taper(spiral_pts(0.49, 0.52, 0.16, 0.02, 1.0, 0), 0.03, 0.02)


def pr_cindertread(c):
    sub(c, g_boot, 0.46, 0.44, 0.8)
    for x, y, s in ((0.2, 0.9, 0.2), (0.5, 0.94, 0.16), (0.8, 0.9, 0.2)):
        sub(c, g_flame_simple, x, y, s)


def pr_last_chorus_bell(c):
    sub(c, g_bell, 0.4, 0.56, 0.72)
    sub(c, g_note, 0.84, 0.24, 0.36)
    c.arc(0.4, 0.56, 0.44, -50, 10, 0.05)


def pr_alembic(c):
    c.circle(0.3, 0.64, 0.3)
    c.rect(0.24, 0.12, 0.36, 0.4)
    c.poly(stroke_poly([(0.3, 0.14), (0.82, 0.56)], 0.07))
    c.circle(0.86, 0.78, 0.13)
    c.rect(0.82, 0.56, 0.9, 0.7)
    with c.op("cut"):
        with c.place(0.3, 0.66, 0.34):
            g_skull(c, teeth=False)


def pr_fang(c):
    c.poly(Path(0.3, 0.02).L(0.84, 0.02).C(0.82, 0.3, 0.72, 0.62, 0.5, 0.86).C(0.44, 0.94, 0.36, 1.0, 0.3, 0.98)
           .C(0.4, 0.74, 0.44, 0.44, 0.3, 0.02).pts())
    with c.op("shade"):
        c.poly(Path(0.6, 0.02).L(0.84, 0.02).C(0.82, 0.3, 0.72, 0.62, 0.5, 0.86).C(0.6, 0.6, 0.64, 0.3, 0.6, 0.02).pts())
    with c.op("cut"):
        c.rect(0.28, 0.1, 0.86, 0.14)


def pr_heirs_oath(c):
    m_shield_mark(c, g_mark)


def pr_vampire(c):
    m_fang_drop(c)


def pr_doomstack(c):
    m_doom(c)


def pr_executioner(c):
    m_execute(c)


# ---- sigils (the rune motif sits in a seal ring)
def ps_anvilheart(c):
    g_heart(c)
    with c.op("cut"):
        with c.box(0.24, 0.24, 0.76, 0.76):
            c.poly(ANVIL)


def ps_quaking_step(c):
    sub(c, g_footprint, 0.5, 0.42, 0.72)
    with c.op("cut"):
        c.line([(0.36, 0.56), (0.5, 0.66), (0.44, 0.8)], 0.04)
    c.rect(0.0, 0.86, 1.0, 0.92)
    for x in (0.1, 0.9):
        c.line([(x, 0.7), (x, 0.8)], 0.05)


def ps_colossal_echo(c):
    m_ult_ground(c, g_flame)


def ps_cadence(c):
    for i, x in enumerate((0.1, 0.34, 0.58)):
        c.rect(x - 0.05, 0.3, x + 0.05, 0.7, r=0.03)
    sub(c, g_spark4, 0.84, 0.5, 0.5)


def ps_static_bloom(c):
    for i in range(5):
        a = -90 + i * 72
        with c.at(0.5, 0.5, r=a + 90):
            with c.box(-0.12, -0.5, 0.12, -0.08):
                g_bolt(c)
    c.circle(0.5, 0.5, 0.12)


def ps_skyrender(c):
    g_wing(c, 4)


def ps_nightfall(c):
    g_crescent(c, 0.24, -0.12, 0.46, 0.38)
    sub(c, g_spark4, 0.72, 0.66, 0.4)


def ps_silent_edge(c):
    with c.place(0.5, 0.5, 0.96, r=30):
        g_dagger(c)
    c.line([(0.1, 0.2), (0.3, 0.2)], 0.06)


def ps_ghostlight(c):
    m_dash(c)


def ps_hexlace(c):
    for i in range(3):
        y = 0.2 + i * 0.3
        c.bez((0.0, y), (0.3, y - 0.2), (0.7, y + 0.2), (1.0, y), 0.06, 0.06)
    sub(c, g_hexeye, 0.5, 0.5, 0.56, knock=0.03)


def ps_tinkers_grace(c):
    sub(c, g_gear, 0.36, 0.6, 0.72)
    sub(c, g_hourglass, 0.78, 0.3, 0.44, knock=0.03)


def ps_bound_souls(c):
    c.ellipse(0.5, 0.82, 0.5, 0.16)
    sub(c, g_hexeye, 0.5, 0.36, 0.66)


def ps_furnace_heart(c):
    g_heart(c)
    with c.op("cut"):
        with c.box(0.3, 0.22, 0.7, 0.8):
            g_flame_simple(c)


def ps_iron_knuckle(c):
    g_fist(c)


def ps_meltpoint(c):
    sub(c, g_drop, 0.5, 0.36, 0.64)
    sub(c, g_flame, 0.5, 0.82, 0.36, knock=0.02)


def ps_huntmark(c):
    sub(c, g_antler, 0.42, 0.5, 0.9)
    sub(c, g_mark, 0.78, 0.76, 0.38, knock=0.03)


def ps_far_sight(c):
    m_range(c)


def ps_patient_death(c):
    sub(c, g_hourglass, 0.36, 0.5, 0.8)
    with c.place(0.74, 0.5, 0.9, r=20):
        c.poly([(0.5, 0.0), (0.56, 0.14), (0.55, 0.66), (0.45, 0.66), (0.44, 0.14)])
        c.rect(0.34, 0.64, 0.66, 0.7)
        c.rect(0.46, 0.7, 0.54, 0.9)


def ps_gilded_tongue(c):
    m_clover(c)


def ps_pickpocket(c):
    with c.place(0.5, 0.36, 0.7, r=180):
        g_hand_open(c, spread=8.0)
    sub(c, g_shard, 0.5, 0.86, 0.3)


def ps_loaded_dice(c):
    g_die(c)


def ps_borrowed_hour(c):
    sub(c, g_hourglass, 0.34, 0.5, 0.8)
    with c.place(0.8, 0.5, 0.4):
        g_arrow(c, fletch=False, head=0.44, w=0.16)


def ps_slow_rot(c):
    c.bez((0.5, 1.0), (0.5, 0.7), (0.56, 0.5), (0.74, 0.36), 0.07, 0.05)
    c.poly(Path(0.74, 0.36).C(0.86, 0.4, 0.94, 0.56, 0.9, 0.7).C(0.8, 0.62, 0.74, 0.5, 0.74, 0.36).pts())
    c.ellipse(0.72, 0.5, 0.1, 0.18, r=-30)
    c.poly(Path(0.5, 0.74).C(0.38, 0.62, 0.2, 0.66, 0.14, 0.74).C(0.24, 0.84, 0.4, 0.84, 0.5, 0.74).pts())
    for x, y in ((0.26, 0.2), (0.4, 0.36)):
        sub(c, g_drop, x, y, 0.16, r=180)


def ps_second_hand(c):
    g_clock(c, -90, 60, ticks=True)
    sub(c, g_spark4, 0.84, 0.16, 0.3, knock=0.02)


PART_ART: dict[str, tuple[Callable, str]] = {
    # cores (motif inside an element orb)
    "embercore": (pc_ember, "a flame"), "stormcore": (pc_storm, "a bolt"), "voidcore": (pc_void, "a gravity spiral"),
    "plaguecore": (pc_plague, "a drop over a festering pool"), "dawncore": (pc_dawn, "the mark lozenge"),
    "ironcore": (pc_iron, "a slug"), "shrapnelcore": (pc_shrapnel, "a shot bursting into shards"),
    "barbcore": (pc_barb, "a barbed needle"), "cairncore": (pc_cairn, "a cairn of stones"),
    "slagcore": (pc_slag, "a molten burst"), "kilncore": (pc_kiln, "a flame over a burning pool"),
    "wickcore": (pc_wick, "a lit fuse"), "tempestcore": (pc_tempest, "a bolt with static sparks"),
    "squallcore": (pc_squall, "a forked bolt"), "hexcore": (pc_hex, "a hex eye"), "gloamcore": (pc_gloam, "a dusk blade crescent"),
    "blightcore": (pc_blight, "linked spores"), "miasmacore": (pc_miasma, "a globe weeping fog"),
    "gildcore": (pc_gild, "a coin with a rebound"), "halocore": (pc_halo, "a halo with a seeking arc"),
    "vitriolcore": (pc_vitriol, "a cracked flask"), "verdictcore": (pc_verdict, "a slug in a mark"),
    "unmadecore": (pc_unmade, "a splinter breaking apart"),
    # mechanisms
    "mech_ricochet": (m_ricochet, "a bouncing path"), "mech_multishot": (m_multishot, "three fanned arrows"),
    "mech_homing_shards": (pm_homing, "a curving shot finding a reticle"), "mech_beam_sweep": (pm_beam, "a sweeping beam"),
    "mech_bounce_fork": (m_fork, "a shot splitting in two"), "mech_sawblade_orbit": (pm_saw_orbit, "three orbiting sawblades"),
    "mech_lancet_drive": (pm_lancet, "a shot through three bars"), "mech_scatterburst": (pm_scatter, "a wide fan of pellets"),
    "mech_overclock": (pm_overclock, "a racing gear"), "mech_twin_barrel": (pm_twin_barrel, "twin barrels"),
    "mech_hydra_volley": (pm_hydra, "three hydra heads"), "mech_compass_rose": (pm_compass_rose, "a compass rose"),
    "mech_skipstone": (pm_skipstone, "a skipping stone"), "mech_ricochet_rosary": (pm_ricochet_rosary, "rosary beads on a bouncing path"),
    "mech_seeker_swarm": (pm_seeker, "shots that part and turn"), "mech_carrion_drift": (pm_carrion, "a circling crow"),
    "mech_railspike": (pm_railspike, "a hypervelocity spike"), "mech_impaler": (pm_impaler, "a skewer through four"),
    "mech_cleaving_fork": (pm_cleave, "a shot cleaving in three"), "mech_tuning_fork": (pm_tuning, "a ringing tuning fork"),
    "mech_arc_relay": (pm_arc_relay, "a conductor coil"), "mech_needle_ray": (pm_needle_ray, "a thin far ray"),
    "mech_titans_exhale": (pm_titans_exhale, "a short wide gout"), "mech_whirling_anvils": (pm_whirling_anvils, "two anvils on chains"),
    "mech_razor_halo": (pm_razor_halo, "a halo of razors"), "mech_gatling_hymn": (pm_gatling_hymn, "a spinning barrel cluster"),
    "mech_heavy_hand": (pm_heavy_hand, "a fist driving down"), "mech_quickdraw_string": (pm_quickdraw, "a fast-drawn bow"),
    "mech_deep_draw": (pm_deep_draw, "a deep draw piercing a bar"), "mech_resounding_vault": (pm_resounding, "a ringing bell"),
    "mech_choke_bore": (pm_choke, "a funnel narrowing the spread"), "mech_sundering_payload": (pm_sundering, "a bursting shell"),
    "mech_split_carom": (pm_split_carom, "a bounce that splits"), "mech_packhunt_volley": (pm_packhunt, "shots running as a pack"),
    "mech_chorus_lattice": (pm_chorus, "two sung notes"),
    # relics
    "relic_vampire": (pr_vampire, "a fanged drop"), "relic_splitspawn": (pr_splitspawn, "a turret sprung from a crit"),
    "relic_doomstack": (pr_doomstack, "doom stacks under a star"), "relic_frostwake": (pr_frostwake, "a slowing wake"),
    "relic_volatile_heart": (pr_volatile_heart, "a spiked, bursting heart"), "relic_greedstone": (pr_greedstone, "a stone shedding coins"),
    "relic_executioners_seal": (pr_executioners_seal, "a headsman's axe on a seal"), "relic_nyctian_eye": (pr_nyctian_eye, "an eye with a lozenge pupil"),
    "relic_bloodletter": (pr_bloodletter, "a lancet and drops"), "relic_giantsbane": (pr_giantsbane, "a horned helm split by a sword"),
    "relic_coal_tongue_brand": (pr_coal_tongue, "a branding iron with a flame"), "relic_stormglass_phial": (pr_stormglass, "a phial holding a bolt"),
    "relic_hexnail": (pr_hexnail, "a coffin nail under a hex eye"), "relic_rootbinders_knot": (pr_rootbinder, "roots bound by a ring"),
    "relic_quarry_brand": (pr_quarry_brand, "a branding iron with the mark"), "relic_ashen_covenant": (pr_ashen_covenant, "a blade through a flame"),
    "relic_stormcatcher": (pr_stormcatcher, "a lightning rod"), "relic_ledger_of_sins": (pr_ledger, "an open ledger with a hex eye"),
    "relic_pinning_stake": (pr_pinning_stake, "a stake driven into roots"), "relic_salt_the_wound": (pr_salt_wound, "a blade through blood drops"),
    "relic_scale_of_judgement": (pr_scale_judgement, "scales tipping on the mark"), "relic_leech_crown": (pr_leech_crown, "a dripping crown"),
    "relic_ichor_chalice": (pr_ichor_chalice, "a chalice of god-blood"), "relic_hound9_spares": (pr_hound9, "little turrets and a spare gear"),
    "relic_sentry_seed": (pr_sentry_seed, "a seed sprouting a turret"), "relic_funeral_bell": (pr_funeral_bell, "a funeral bell"),
    "relic_epitaph_engine": (pr_epitaph, "a gravestone tallying"), "relic_pyre_lung": (pr_pyre_lung, "lungs with a flame"),
    "relic_dying_star": (pr_dying_star, "a star collapsing inward"), "relic_reapers_tithe": (pr_reapers_tithe, "a scythe taking a shard"),
    "relic_misericorde": (pr_misericorde, "a mercy blade"), "relic_anvil_plate": (pr_anvil_plate, "a breastplate stamped with an anvil"),
    "relic_gilded_aegis": (pr_gilded_aegis, "a round shield with a sun boss"), "relic_beating_stone": (pr_beating_stone, "a beating stone heart"),
    "relic_ember_of_ruin": (pr_ember_of_ruin, "a cracked heart with an ember"), "relic_brink_coin": (pr_brink_coin, "a cracked coin with a skull"),
    "relic_opening_verse": (pr_opening_verse, "an arrow in a whole target"), "relic_titanbreaker_wedge": (pr_titanbreaker, "a wedge splitting a boulder"),
    "relic_crooked_knucklebone": (pr_knucklebone, "a crooked knucklebone"), "relic_headsmans_hood": (pr_headsman_hood, "a headsman's hood"),
    "relic_razorwake": (pr_razorwake, "a razor and its wake"), "relic_tarpit_heart": (pr_tarpit, "a heart sinking in pitch"),
    "relic_gyrestone": (pr_gyrestone, "a spiral stone in widening rings"), "relic_cindertread": (pr_cindertread, "a boot kicking cinders"),
    "relic_last_chorus_bell": (pr_last_chorus_bell, "a bell and a note"), "relic_reddeath_alembic": (pr_alembic, "an alembic with a skull"),
    "relic_huntmothers_fang": (pr_fang, "a great fang"), "relic_heirs_oath": (pr_heirs_oath, "a shield bearing the mark"),
    # sigils (a rune in a seal ring)
    "sigil_anvilheart": (ps_anvilheart, "a heart stamped with an anvil"), "sigil_quaking_step": (ps_quaking_step, "a quaking footprint"),
    "sigil_colossal_echo": (ps_colossal_echo, "a flame over scarred ground"), "sigil_cadence": (ps_cadence, "three beats and a spark"),
    "sigil_static_bloom": (ps_static_bloom, "a bloom of bolts"), "sigil_skyrender": (ps_skyrender, "a wing"),
    "sigil_nightfall": (ps_nightfall, "a crescent and a spark"), "sigil_silent_edge": (ps_silent_edge, "a quiet dagger"),
    "sigil_ghostlight": (ps_ghostlight, "dash chevrons"), "sigil_hexlace": (ps_hexlace, "laced threads over a hex eye"),
    "sigil_tinkers_grace": (ps_tinkers_grace, "a gear and an hourglass"), "sigil_bound_souls": (ps_bound_souls, "a hex eye over a pool"),
    "sigil_furnace_heart": (ps_furnace_heart, "a heart with a flame"), "sigil_iron_knuckle": (ps_iron_knuckle, "a fist"),
    "sigil_meltpoint": (ps_meltpoint, "a melting drop over a flame"), "sigil_huntmark": (ps_huntmark, "an antler and the mark"),
    "sigil_far_sight": (ps_far_sight, "an eye and a long arrow"), "sigil_patient_death": (ps_patient_death, "an hourglass and a blade"),
    "sigil_gilded_tongue": (ps_gilded_tongue, "a four-leaf charm"), "sigil_pickpocket": (ps_pickpocket, "a hand lifting a shard"),
    "sigil_loaded_dice": (ps_loaded_dice, "a die"), "sigil_borrowed_hour": (ps_borrowed_hour, "an hourglass and a stride arrow"),
    "sigil_slow_rot": (ps_slow_rot, "a wilting stem"), "sigil_second_hand": (ps_second_hand, "a clock and a spark"),
}

# The composition kit (UI_STYLE 9.4) for parts added later without a hand recipe: the first matching
# tag picks the motif.
TAG_MOTIFS: list[tuple[str, Callable]] = [
    ("chain", m_chain), ("ricochet", m_ricochet), ("fork", m_fork), ("multishot", m_multishot), ("pierce", m_pierce),
    ("homing", m_homing), ("orbit", m_orbit), ("beam", m_beam), ("turret", g_turret), ("echo", m_echo),
    ("trail", m_trail), ("puddle", m_puddle), ("explode", m_explode), ("volatile", m_bomb), ("doom", m_doom),
    ("crit", m_crit), ("execute", m_execute), ("mark", g_mark), ("curse", g_hexeye), ("bleed", g_blood),
    ("burn", g_flame), ("shock", st_shock), ("root", g_roots), ("lifesteal", m_fang_drop), ("shield", g_shield),
    ("greed", m_greed), ("knockback", m_knockback), ("gravity", m_gravity), ("spread", m_spread), ("charge", m_charge),
    ("velocity", m_velocity), ("dash", m_dash), ("elite", m_giant), ("low_hp", m_low_hp), ("luck", m_clover),
    ("coin", g_coin), ("nova", m_nova), ("shrapnel", m_shrapnel), ("contagion", m_contagion), ("chaos", m_chaos),
]
PART_BOLD = {"mech_needle_ray": 0.004, "mech_impaler": 0.012, "relic_misericorde": 0.014, "relic_stormcatcher": 0.012,
             "relic_pinning_stake": 0.01, "relic_reapers_tithe": 0.01, "relic_razorwake": 0.008, "relic_hexnail": 0.008,
             "mech_railspike": 0.008, "mech_seeker_swarm": 0.006, "mech_homing_shards": 0.006, "mech_quickdraw_string": 0.008,
             "mech_deep_draw": 0.008, "relic_bloodletter": 0.006, "mech_arc_relay": 0.004}
SLOT_GLYPH = {"Core": s_core, "Mechanism": s_mech, "Relic": s_relic, "Sigil": s_sigil}


def compose_part(row: dict) -> tuple[Callable, str]:
    tags = [t.strip() for t in row["tags"].split(";") if t.strip()]
    for tag, fn in TAG_MOTIFS:
        if tag in tags:
            return fn, f"composed from its '{tag}' tag"
    return SLOT_GLYPH[row["slot"]], "the slot's generic glyph (no motif tag)"


def _core_element(row: dict) -> str:
    m = re.search(r"Element\((\w+)\)", row["mods"])
    return m.group(1).lower() if m else "kinetic"


@content_hook
def register_parts(content: Content):
    for row in content.parts:
        k = row["key"]
        fn, note = PART_ART.get(k) or compose_part(row)
        slot = row["slot"]
        meaning = f"{row['name']} ({slot}): {row['desc']} Icon: {note}."
        if slot == "Core":
            el = _core_element(row)
            reg("parts", k, None, ELEMENT[el], meaning, kind="framed",
                extra={"frame": core_orb, "motif": fn, "motif_size": 0.62, "window": 0.35, "motif_name": note})
        elif slot == "Sigil":
            reg("parts", k, None, T_BONE, meaning, kind="framed",
                extra={"frame": sigil_ring, "motif": fn, "motif_size": 0.66, "window": 0.4, "motif_name": note})
        else:
            reg("parts", k, fn, T_BONE, meaning, extra={"motif_name": note, "bold": PART_BOLD.get(k, 0.0)})


# ───────────────────────────── boons ─────────────────────────────
# One glyph per boon, chosen by its first status or mechanic mod and kept distinct within each god.
# The renderer adds the god sigil(s) small at the top corner(s).

def b_flaming_sword(c):
    with c.place(0.5, 0.46, 0.92, r=35):
        g_sword(c, 0.2, fuller=False)
    sub(c, g_flame, 0.26, 0.78, 0.4, knock=0.03)


def b_flaming_bullets(c):
    m_fire_rate(c)
    sub(c, g_flame, 0.84, 0.14, 0.3, knock=0.02)


def b_cinder_bloom(c):
    sub(c, g_skull, 0.5, 0.62, 0.6)
    for a in (-150, -90, -30):
        with c.place(*polar(0.5, 0.56, 0.42, a), 0.3, r=a + 90):
            g_flame_simple(c)


def b_blastfire(c):
    g_burst(c, 10, 0.5, 0.26)
    with c.op("cut"):
        c.star(0.5, 0.5, 0.26, 0.12, 10, rot_deg=-72)
    c.circle(0.5, 0.5, 0.1)


def b_dash_nova_el(el_glyph):
    def f(c):
        m_dash_nova(c, el_glyph)
    return f


def b_ult_ground_el(el_glyph):
    def f(c):
        m_ult_ground(c, el_glyph)
    return f


def b_seared_heart(c):
    g_heart(c)
    with c.op("cut"):
        c.line([(0.2, 0.44), (0.8, 0.44)], 0.07)
        for x in (0.32, 0.5, 0.68):
            c.line([(x, 0.34), (x, 0.54)], 0.045)
    sub(c, g_flame, 0.2, 0.8, 0.34, knock=0.03)


def b_twin_flame(c):
    sub(c, g_flame_simple, 0.34, 0.56, 0.84, core=True)
    sub(c, g_flame_simple, 0.72, 0.62, 0.64, knock=0.03, core=True)


def b_roaring_pyre(c):
    sub(c, g_flame, 0.5, 0.52, 0.56)
    for r in (0.36, 0.48):
        c.arc(0.5, 0.56, r, 200, 250, 0.05)
        c.arc(0.5, 0.56, r, 290, 340, 0.05)


def b_furnace_rite(c):
    m_active(c, g_flame)


def b_searing_brand(c):
    pr_brand(c, g_flame_simple)


def b_pyre(c):
    sub(c, g_flame, 0.5, 0.36, 0.72)
    for i, y in enumerate((0.8, 0.9)):
        c.line([(0.08, y + 0.04), (0.92, y - 0.04)] if i == 0 else [(0.08, y - 0.04), (0.92, y + 0.04)], 0.08)
    sub(c, g_skull, 0.5, 0.66, 0.26, knock=0.02)


def b_tailwind(c):
    m_winged_boot(c)


def b_stormbrand(c):
    c.poly([(0.5, 0.0), (0.62, 0.14), (0.62, 0.66), (0.38, 0.66), (0.38, 0.14)])
    c.rect(0.2, 0.66, 0.8, 0.74, r=0.03)
    c.rect(0.44, 0.74, 0.56, 0.92)
    c.circle(0.5, 0.95, 0.06)
    with c.op("cut"):
        with c.box(0.4, 0.14, 0.6, 0.6):
            g_bolt(c)


def b_leaping_arc(c):
    pts = [(0.04, 0.8), (0.28, 0.26), (0.5, 0.7), (0.74, 0.2), (0.96, 0.6)]
    c.line(pts, 0.07)
    for p in pts:
        c.circle(p[0], p[1], 0.09)


def b_gale_arrow(c):
    with c.place(0.56, 0.54, 0.84):
        g_arrow(c, fletch=True, head=0.3, w=0.1)
    c.taper(spiral_pts(0.22, 0.26, 0.2, 0.06, 0.8, 90), 0.06, 0.02)
    c.line([(0.3, 0.84), (0.66, 0.84)], 0.05)


def b_updraft(c):
    c.taper(spiral_pts(0.5, 0.72, 0.36, 0.06, 1.1, 0), 0.08, 0.03)
    with c.place(0.5, 0.2, 0.44):
        g_chevron(c, 0.3)
    with c.place(0.5, 0.4, 0.3):
        g_chevron(c, 0.3)


def b_thunderhead(c):
    with c.box(0.04, 0.0, 0.96, 0.5):
        g_cloud(c)
    sub(c, g_bolt, 0.5, 0.66, 0.36)
    c.ellipse(0.5, 0.92, 0.46, 0.08)


def b_rebounding_gale(c):
    m_ricochet(c)


def b_ionized(c):
    sub(c, g_bolt, 0.5, 0.52, 0.8)
    c.arc(0.5, 0.5, 0.48, 200, 250, 0.05)
    c.arc(0.5, 0.5, 0.48, 20, 70, 0.05)
    for x, y, s in ((0.14, 0.72, 0.22), (0.86, 0.3, 0.2), (0.2, 0.2, 0.16)):
        sub(c, g_spark4, x, y, s)


def b_galvanize(c):
    m_active(c, g_bolt)


def b_stormcalm(c):
    c.taper(spiral_pts(0.5, 0.5, 0.5, 0.24, 1.0, 0), 0.1, 0.04)
    c.circle(0.5, 0.5, 0.14)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.06)


def b_thousandfold(c):
    c.line([(0.5, 0.0), (0.44, 0.24), (0.54, 0.4), (0.46, 0.6)], 0.08)
    for (x0, y0), pts in (((0.44, 0.24), [(0.26, 0.36), (0.2, 0.56), (0.06, 0.66)]),
                          ((0.54, 0.4), [(0.72, 0.5), (0.76, 0.72), (0.92, 0.82)]),
                          ((0.46, 0.6), [(0.36, 0.76), (0.42, 0.98)]),
                          ((0.2, 0.56), [(0.14, 0.86)]), ((0.76, 0.72), [(0.62, 0.9)])):
        c.line([(x0, y0)] + pts, 0.055)


def b_umbral_edge(c):
    m_crit(c)


def b_quietus(c):
    c.poly([(0.5, 0.0), (0.6, 0.56), (0.5, 0.66), (0.4, 0.56)])
    c.rect(0.24, 0.62, 0.76, 0.7, r=0.03)
    c.rect(0.45, 0.7, 0.55, 0.92)
    c.circle(0.5, 0.95, 0.06)
    with c.op("cut"):
        c.star(0.5, 0.36, 0.1, 0.03, 4)


def b_serrated(c):
    pts = [(0.14, 0.9)]
    for i in range(6):
        t = i / 6
        pts.append((0.2 + t * 0.66, 0.84 - t * 0.66))
        pts.append((0.28 + t * 0.66, 0.84 - t * 0.66 - 0.02))
    pts += [(0.96, 0.04), (0.9, 0.2), (0.24, 0.96)]
    c.poly(pts)
    sub(c, g_drop, 0.22, 0.34, 0.3)


def b_veil_knives(c):
    with c.box(0.0, 0.34, 1.0, 1.0):
        g_cloud(c)
    for a in (-30, 0, 30):
        with c.at(0.5, 0.56, r=a):
            c.poly([(0.0, -0.56), (0.06, -0.36), (0.04, -0.12), (-0.04, -0.12), (-0.06, -0.36)])


def b_ambuscade(c):
    g_crescent(c, -0.26, -0.06, 0.46, 0.4)
    with c.op("cut"):
        c.poly(stroke_poly([(0.34, 0.96), (0.96, 0.18)], 0.2))
    with c.place(0.64, 0.56, 0.84, r=40):
        g_dagger(c)


def b_shade_twin(c):
    with c.box(0.3, 0.06, 0.9, 1.0):
        g_figure(c)
    with c.box(0.06, 0.18, 0.56, 1.0):
        with c.op("shade"):
            g_figure(c)
        g_figure(c)
    sub(c, g_spark4, 0.84, 0.16, 0.26)


def b_keen_dark(c):
    sub(c, g_eye, 0.46, 0.56, 0.9)
    sub(c, g_spark4, 0.84, 0.16, 0.34, knock=0.03)


def b_assassin_vow(c):
    with c.box(0.06, 0.58, 0.94, 1.0):
        g_crown(c, 5, band=False)
    with c.op("cut"):
        c.poly([(0.36, 0.0), (0.64, 0.0), (0.62, 0.7), (0.5, 0.86), (0.38, 0.7)])
    with c.place(0.5, 0.36, 0.84, r=180):
        g_dagger(c)


def b_nightshroud(c):
    c.poly(Path(0.5, 0.02).C(0.7, 0.1, 0.86, 0.34, 0.86, 0.6).L(0.98, 1.0).L(0.02, 1.0).L(0.14, 0.6)
           .C(0.14, 0.34, 0.3, 0.1, 0.5, 0.02).pts())
    with c.op("cut"):
        c.poly(Path(0.5, 0.22).C(0.64, 0.26, 0.7, 0.4, 0.68, 0.58).L(0.32, 0.58).C(0.3, 0.4, 0.36, 0.26, 0.5, 0.22).pts())
    c.poly([(0.38, 0.44), (0.47, 0.42), (0.45, 0.47)])
    c.poly([(0.62, 0.44), (0.53, 0.42), (0.55, 0.47)])
    with c.op("shade"):
        c.poly([(0.5, 0.02), (0.7, 0.1), (0.86, 0.34), (0.86, 0.6), (0.98, 1.0), (0.6, 1.0)])


def b_hunting_shadows(c):
    m_homing(c)
    sub(c, g_crescent, 0.18, 0.2, 0.3, knock=0.02)


def b_dark_moon(c):
    c.circle(0.5, 0.5, 0.36)
    with c.op("shade"):
        c.circle(0.56, 0.44, 0.34)
    c.ring(0.5, 0.5, 0.5, 0.05)
    for a in range(0, 360, 30):
        c.line([polar(0.5, 0.5, 0.38, a), polar(0.5, 0.5, 0.44, a)], 0.035, cap=False)


def b_kiss_silence(c):
    c.poly(Path(0.04, 0.34).Q(0.5, 0.74, 0.96, 0.34).Q(0.5, 0.56, 0.04, 0.34).pts())
    for x in (0.22, 0.38, 0.5, 0.62, 0.78):
        c.line([(x, 0.5 - abs(x - 0.5) * 0.3), (x - 0.02 * (x - 0.5) * 4, 0.64 - abs(x - 0.5) * 0.2)], 0.035)
    with c.place(0.5, 0.78, 0.44, r=90):
        g_dagger(c)


def b_stilled_sands(c):
    sub(c, g_hourglass, 0.72, 0.5, 0.56)
    for i, y in enumerate((0.3, 0.5, 0.7)):
        c.line([(0.02 + i * 0.04, y), (0.4, y)], 0.06)


def b_ageless_flame(c):
    c.ring(0.5, 0.5, 0.5, 0.06)
    for a in range(0, 360, 30):
        c.line([polar(0.5, 0.5, 0.36, a), polar(0.5, 0.5, 0.43, a)], 0.035, cap=False)
    sub(c, g_flame_simple, 0.5, 0.52, 0.52, core=True)


def b_unclosing(c):
    g_ccw_arrow(c, 250, 560, r=0.44, w=0.08)
    sub(c, g_blood, 0.5, 0.52, 0.52)


def b_quickened(c):
    g_clock(c, -60, 60, ticks=False)
    sub(c, m_dash, 0.16, 0.5, 0.26, knock=0.02)


def b_rewinding_ward(c):
    g_shield(c, "half")
    with c.op("cut"):
        with c.place(0.5, 0.48, 0.56):
            g_ccw_arrow(c, 250, 540, r=0.36, w=0.14)


def b_echo_instant(c):
    m_echo(c)
    sub(c, g_clock, 0.2, 0.2, 0.34, knock=0.02, ticks=False)


def b_stutterstep(c):
    m_dash(c)
    sub(c, ui_pause, 0.84, 0.18, 0.3, knock=0.02)


def b_shattered_moment(c):
    g_clock(c, -110, 30, ticks=False)
    with c.op("cut"):
        c.line([(0.5, 0.0), (0.56, 0.3), (0.44, 0.5), (0.6, 0.72), (0.52, 1.0)], 0.06)


def b_heavy_hours(c):
    sub(c, g_hourglass, 0.36, 0.44, 0.76)
    sub(c, g_anvil, 0.74, 0.8, 0.44, knock=0.02)


def b_turning_hands(c):
    c.circle(0.5, 0.5, 0.1)
    c.arc(0.5, 0.5, 0.4, 0, 360, 0.03)
    for a in (-40, 140):
        with c.at(0.5, 0.5, r=a):
            c.poly([(0.0, -0.04), (0.44, -0.02), (0.52, 0.0), (0.44, 0.02), (0.0, 0.04)])
            c.poly([(0.36, -0.08), (0.52, 0.0), (0.36, 0.08)])


def b_wound_spring(c):
    for i in range(5):
        y = 0.14 + i * 0.16
        c.line([(0.2, y), (0.8, y + 0.08)], 0.07)
        if i < 4:
            c.line([(0.8, y + 0.08), (0.2, y + 0.16)], 0.07)
    c.rect(0.1, 0.02, 0.9, 0.1, r=0.03)
    c.rect(0.1, 0.9, 0.9, 0.98, r=0.03)


def b_recurrence(c):
    c.arc(0.5, 0.5, 0.4, 30, 330, 0.14)
    c.poly([polar(0.5, 0.5, 0.58, 20), polar(0.5, 0.5, 0.22, 20), polar(0.5, 0.5, 0.42, 58)])
    with c.op("cut"):
        c.circle(*polar(0.5, 0.5, 0.4, 310), 0.03)
    c.circle(0.5, 0.5, 0.12)


def b_grasping_stone(c):
    c.rect(0.0, 0.8, 1.0, 0.9, r=0.02)
    with c.place(0.5, 0.42, 0.74):
        g_hand_open(c, spread=10.0)
    with c.op("shade"):
        c.rect(0.0, 0.8, 1.0, 1.0)


def b_granite_skin(c):
    c.poly([(0.2, 0.06), (0.8, 0.06), (0.96, 0.34), (0.84, 0.84), (0.5, 1.0), (0.16, 0.84), (0.04, 0.34)])
    with c.op("shade"):
        c.poly([(0.5, 0.4), (0.96, 0.34), (0.84, 0.84), (0.5, 1.0)])
    with c.op("cut"):
        c.line([(0.04, 0.34), (0.5, 0.4), (0.96, 0.34)], 0.035)
        c.line([(0.5, 0.4), (0.5, 1.0)], 0.035)
        c.line([(0.2, 0.06), (0.3, 0.37)], 0.03)
        c.line([(0.8, 0.06), (0.7, 0.37)], 0.03)


def b_bedrock(c):
    for i, (y, w) in enumerate(((0.86, 0.5), (0.7, 0.44), (0.54, 0.38))):
        c.rect(0.5 - w, y - 0.07, 0.5 + w, y + 0.07, r=0.03)
    sub(c, g_heart, 0.5, 0.24, 0.42, knock=0.02)


def b_bloodroot(c):
    sub(c, g_roots, 0.5, 0.66, 0.66)
    sub(c, g_drop, 0.5, 0.18, 0.36)


def b_tremor_step(c):
    ps_quaking_step(c)


def b_crush_bound(c):
    m_vs(c, g_roots)


def b_sanguine_thorns(c):
    c.bez((0.04, 0.96), (0.4, 0.8), (0.3, 0.3), (0.9, 0.1), 0.08, 0.06)
    for t, sgn in ((0.25, 1), (0.45, -1), (0.65, 1), (0.82, -1)):
        p = cubic((0.04, 0.96), (0.4, 0.8), (0.3, 0.3), (0.9, 0.1), 20)[int(t * 20)]
        c.poly([(p[0] - 0.04, p[1]), (p[0] + sgn * 0.14, p[1] - 0.08), (p[0] + 0.04, p[1] - 0.04)])
    sub(c, g_drop, 0.78, 0.66, 0.34)


def b_tectonic(c):
    c.poly([(0.0, 0.66), (0.4, 0.5), (0.46, 0.96), (0.0, 0.96)])
    c.poly([(0.54, 0.4), (1.0, 0.56), (1.0, 0.96), (0.52, 0.96)])
    with c.op("shade"):
        c.poly([(0.54, 0.4), (1.0, 0.56), (1.0, 0.96), (0.52, 0.96)])
    for x, y in ((0.3, 0.3), (0.62, 0.16), (0.82, 0.3)):
        c.poly([(x, y - 0.08), (x + 0.07, y), (x, y + 0.08), (x - 0.07, y)])


def b_earthen_might(c):
    m_active(c, g_fist)


def b_deep_marrow(c):
    c.poly(stroke_poly([(0.24, 0.76), (0.76, 0.24)], 0.14))
    for (x, y) in ((0.24, 0.76), (0.76, 0.24)):
        for a in (135, -45):
            p = polar(x, y, 0.1, a + (0 if x < 0.5 else 180) + 45)
            c.circle(p[0], p[1], 0.1)
    sub(c, g_heart, 0.78, 0.8, 0.34, knock=0.03)


def b_landslide(c):
    sub(c, g_boulder, 0.34, 0.36, 0.56)
    sub(c, g_boulder, 0.72, 0.68, 0.46, knock=0.02)
    for y in (0.64, 0.8):
        c.line([(0.0, y + 0.1), (0.2, y)], 0.05)


def b_unbroken(c):
    with c.box(0.0, 0.3, 1.0, 1.0):
        g_mountain(c)
    sub(c, g_shield, 0.5, 0.26, 0.44, knock=0.03)


def b_brackish(c):
    m_puddle(c)


def b_witchs_brine(c):
    c.poly(Path(0.06, 0.4).L(0.94, 0.4).C(0.94, 0.78, 0.74, 0.96, 0.5, 0.96).C(0.26, 0.96, 0.06, 0.78, 0.06, 0.4).pts())
    c.rect(0.0, 0.36, 1.0, 0.44, r=0.03)
    for x, y, r in ((0.3, 0.26, 0.08), (0.5, 0.18, 0.1), (0.7, 0.28, 0.06)):
        c.circle(x, y, r)
    with c.op("cut"):
        c.ellipse(0.5, 0.64, 0.16, 0.1)
    c.circle(0.5, 0.64, 0.05)


def b_plague_wake(c):
    m_trail(c)
    for x, y in ((0.14, 0.94), (0.3, 0.86)):
        c.circle(x, y, 0.05)


def b_spreading_blight(c):
    sub(c, g_drop, 0.26, 0.5, 0.46)
    for a in (-35, 35):
        with c.at(0.44, 0.5, r=a):
            c.rect(0.0, -0.035, 0.24, 0.035)
            sub(c, g_drop, 0.38, 0.0, 0.26, r=90)


def b_brinestep(c):
    with c.box(0.0, 0.3, 1.0, 1.0):
        g_wave(c)
    with c.place(0.3, 0.18, 0.3, r=90):
        g_chevron(c, 0.3)
    with c.place(0.5, 0.18, 0.3, r=90):
        g_chevron(c, 0.3)


def b_dragged_under(c):
    c.poly(Path(0.0, 0.6).C(0.2, 0.52, 0.3, 0.68, 0.5, 0.6).C(0.7, 0.52, 0.8, 0.68, 1.0, 0.6).L(1.0, 1.0).L(0.0, 1.0).pts())
    with c.op("shade"):
        c.rect(0.0, 0.6, 1.0, 1.0)
    c.bez((0.62, 0.66), (0.66, 0.4), (0.4, 0.3), (0.3, 0.06), 0.14, 0.04)
    for t in (0.3, 0.55):
        p = cubic((0.62, 0.66), (0.66, 0.4), (0.4, 0.3), (0.3, 0.06), 20)[int(t * 20)]
        with c.op("cut"):
            c.circle(p[0] - 0.02, p[1], 0.025)
    sub(c, g_hexeye, 0.2, 0.36, 0.3, knock=0.02)


def b_deluge(c):
    g_wave(c)
    for x in (0.2, 0.46):
        sub(c, g_drop, x, 0.1, 0.18)


def b_drowning_gyre(c):
    g_spiral(c, turns=2.0, w0=0.1, w1=0.03, cw=False, a0=180)
    c.circle(0.5, 0.5, 0.06)


def b_contagion(c):
    m_contagion(c)
    sub(c, g_hexeye, 0.84, 0.16, 0.3, knock=0.02)


def b_wreckers(c):
    """An anchor."""
    c.ring(0.5, 0.12, 0.1, 0.05)
    c.rect(0.46, 0.2, 0.54, 0.92)
    c.rect(0.28, 0.3, 0.72, 0.36, r=0.02)
    c.arc(0.5, 0.58, 0.38, 20, 160, 0.08)
    for sgn in (-1, 1):
        p = polar(0.5, 0.58, 0.38, 90 - sgn * 70)
        c.poly([(p[0], p[1] - 0.16), (p[0] + sgn * 0.1, p[1] - 0.02), (p[0] - sgn * 0.02, p[1] + 0.02)])


def b_barnacle(c):
    """A ribbed shell."""
    c.poly(Path(0.5, 0.96).L(0.04, 0.44).C(0.1, 0.16, 0.3, 0.04, 0.5, 0.04).C(0.7, 0.04, 0.9, 0.16, 0.96, 0.44).pts())
    with c.op("cut"):
        for a in (-60, -30, 0, 30, 60):
            p = polar(0.5, 0.96, 0.84, -90 + a)
            c.line([(0.5, 0.9), p], 0.035)
    c.rect(0.36, 0.86, 0.64, 0.98, r=0.03)


def b_black_tide(c):
    g_wave(c)
    sub(c, g_hexeye, 0.26, 0.64, 0.4, knock=0.03)


def b_writ(c):
    c.rect(0.14, 0.12, 0.86, 0.86, r=0.02)
    c.ellipse(0.14, 0.12, 0.1, 0.12)
    c.ellipse(0.86, 0.86, 0.1, 0.12)
    with c.op("cut"):
        for y in (0.26, 0.38):
            c.rect(0.26, y, 0.74, y + 0.04)
    sub(c, g_mark, 0.52, 0.64, 0.34, knock=0.02)


def b_sentence(c):
    with c.place(0.56, 0.4, 0.8, r=-10):
        g_gavel(c)
    sub(c, g_mark, 0.24, 0.8, 0.36, knock=0.03)


def b_aegis_law(c):
    g_shield(c, "half")
    with c.op("cut"):
        with c.box(0.26, 0.22, 0.74, 0.7):
            g_scales(c)


def b_lance_dawn(c):
    c.poly([(0.0, 0.44), (0.66, 0.42), (1.0, 0.5), (0.66, 0.58), (0.0, 0.56)])
    with c.op("shade"):
        c.poly([(0.0, 0.5), (1.0, 0.5), (0.66, 0.58), (0.0, 0.56)])
    sub(c, g_radiant, 0.66, 0.5, 0.4, knock=0.03)
    for y in (0.26, 0.74):
        c.line([(0.06, y), (0.42, y)], 0.06)


def b_smite_mighty(c):
    c.poly([(0.36, 0.0), (0.64, 0.0), (0.56, 0.5), (0.44, 0.5)])
    with c.op("shade"):
        c.poly([(0.5, 0.0), (0.64, 0.0), (0.56, 0.5), (0.5, 0.5)])
    with c.box(0.1, 0.56, 0.9, 0.98):
        g_crown(c, 5)


def b_sanctified_step(c):
    m_dash_nova(c, g_radiant)


def b_litany(c):
    g_book(c)
    sub(c, g_radiant, 0.5, 0.1, 0.34, knock=0.03)


def b_radiant_mantle(c):
    c.poly(stroke_poly(arcpts(0.5, 0.1, 0.2, 0.08, 0, 360, 48), 0.06))
    with c.box(0.08, 0.2, 0.92, 1.0):
        g_figure(c)
    with c.op("cut"):
        c.line([(0.5, 0.52), (0.5, 0.96)], 0.03)


def b_rebuke(c):
    with c.place(0.4, 0.52, 0.84):
        g_hand_open(c, spread=4.0)
    for r in (0.3, 0.42):
        c.arc(0.46, 0.46, r, -50, 40, 0.05)


def b_guiding_light(c):
    """A lantern."""
    c.ring(0.5, 0.08, 0.08, 0.035)
    c.poly([(0.3, 0.16), (0.7, 0.16), (0.78, 0.26), (0.22, 0.26)])
    c.poly([(0.26, 0.26), (0.74, 0.26), (0.7, 0.84), (0.3, 0.84)])
    c.rect(0.2, 0.84, 0.8, 0.94, r=0.03)
    with c.op("cut"):
        c.poly([(0.34, 0.32), (0.66, 0.32), (0.63, 0.78), (0.37, 0.78)])
    sub(c, g_flame_simple, 0.5, 0.58, 0.3)


def b_judgment_absolute(c):
    g_radiant(c)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.26)
    sub(c, g_mark, 0.5, 0.5, 0.42)


def b_brink_ruin(c):
    pr_ember_of_ruin(c)


def b_tolling_doom(c):
    g_bell(c)
    for r in (0.54, 0.66):
        c.arc(0.5, 0.5, r, -30, 10, 0.05)
        c.arc(0.5, 0.5, r, 170, 210, 0.05)
    with c.op("cut"):
        with c.place(0.5, 0.46, 0.3):
            g_skull(c, teeth=False)


def b_pound_flesh(c):
    sub(c, g_heart, 0.5, 0.6, 0.8)
    with c.op("cut"):
        c.poly([(0.38, 0.0), (0.62, 0.0), (0.6, 0.66), (0.5, 0.8), (0.4, 0.66)])
    with c.place(0.5, 0.36, 0.72, r=180):
        g_dagger(c)


def b_tyrants_haste(c):
    m_fire_rate(c)
    with c.box(0.2, 0.0, 0.9, 0.24):
        g_crown(c, 5, band=False)


def b_ruinstep(c):
    sub(c, g_footprint, 0.5, 0.4, 0.7)
    c.poly([(0.0, 0.84), (0.3, 0.8), (0.4, 0.9), (0.56, 0.8), (0.7, 0.9), (1.0, 0.84), (1.0, 1.0), (0.0, 1.0)])
    with c.op("cut"):
        c.line([(0.4, 0.9), (0.46, 1.0)], 0.03)
        c.line([(0.7, 0.9), (0.66, 1.0)], 0.03)


def b_ashen_scar(c):
    c.ellipse(0.5, 0.8, 0.5, 0.18)
    with c.op("shade"):
        c.ellipse(0.5, 0.8, 0.5, 0.18)
    c.poly([(0.1, 0.9), (0.9, 0.7), (0.92, 0.76), (0.14, 0.96)])
    sub(c, g_void_el, 0.5, 0.34, 0.54)


def b_kings_tithe(c):
    with c.box(0.08, 0.0, 0.92, 0.5):
        g_crown(c, 5)
    for x, y in ((0.24, 0.74), (0.5, 0.84), (0.76, 0.72)):
        sub(c, g_coin, x, y, 0.3)


def b_spite_dying(c):
    sub(c, g_skull, 0.44, 0.5, 0.84)
    sub(c, g_drop, 0.84, 0.72, 0.3, knock=0.02)


def b_weight_end(c):
    sub(c, g_hourglass, 0.5, 0.5, 1.0)
    with c.op("cut"):
        with c.place(0.5, 0.72, 0.2):
            g_skull(c, teeth=False)


def b_cinder_oath(c):
    g_shield(c, "half")
    with c.op("cut"):
        with c.box(0.3, 0.2, 0.7, 0.78):
            g_flame_simple(c)


def b_harbinger(c):
    """A raven with spread wings."""
    c.poly(Path(0.5, 0.26).C(0.36, 0.1, 0.16, 0.06, 0.0, 0.2).C(0.14, 0.24, 0.24, 0.34, 0.3, 0.46).L(0.14, 0.52)
           .L(0.36, 0.56).L(0.42, 0.76).L(0.38, 0.96).L(0.5, 0.86).L(0.62, 0.96).L(0.58, 0.76).L(0.64, 0.56)
           .L(0.86, 0.52).L(0.7, 0.46).C(0.76, 0.34, 0.86, 0.24, 1.0, 0.2).C(0.84, 0.06, 0.64, 0.1, 0.5, 0.26).pts())
    c.circle(0.5, 0.3, 0.1)
    c.poly([(0.44, 0.32), (0.5, 0.46), (0.56, 0.32)])
    with c.op("cut"):
        c.circle(0.46, 0.28, 0.02)


def b_last_crown(c):
    c.poly([(0.04, 0.96), (0.08, 0.5), (0.22, 0.66), (0.3, 0.44), (0.4, 0.62), (0.44, 0.96)])
    c.poly([(0.56, 0.96), (0.6, 0.6), (0.7, 0.44), (0.78, 0.66), (0.92, 0.5), (0.96, 0.96)])
    with c.op("cut"):
        c.rect(0.0, 0.84, 1.0, 0.88)
    sub(c, g_flame, 0.5, 0.36, 0.6)


def b_bond_forge(c):
    m_dash(c)
    with c.op("cut"):
        c.rect(0.0, 0.84, 1.0, 1.0)
    for i, x in enumerate((0.3, 0.5, 0.7)):
        with c.place(x, 0.9, 0.2, r=90 * (i % 2)):
            g_chain_link(c, 0.18)


def b_choir_anvils(c):
    sub(c, g_anvil, 0.42, 0.64, 0.84)
    sub(c, g_note, 0.84, 0.22, 0.4, knock=0.03)


def b_spoils(c):
    sub(c, g_magnet, 0.36, 0.6, 0.7, r=-30)
    for x, y, s in ((0.8, 0.18, 0.3), (0.62, 0.08, 0.2), (0.9, 0.44, 0.22)):
        sub(c, g_shard, x, y, s)


def b_wall_halos(c):
    with c.place(0.5, 0.56, 0.56):
        g_shield(c, "half")
    for a in (-135, -45, 45, 135):
        p = polar(0.5, 0.52, 0.4, a)
        c.poly(stroke_poly(arcpts(p[0], p[1], 0.13, 0.06, 0, 360, 40), 0.045))


def b_thunderburn(c):
    sub(c, g_bolt, 0.4, 0.5, 0.96)
    sub(c, g_flame, 0.78, 0.7, 0.44, knock=0.03)


def b_pitchfire(c):
    c.ellipse(0.5, 0.8, 0.5, 0.18)
    with c.op("shade"):
        c.ellipse(0.5, 0.8, 0.5, 0.18)
    sub(c, g_flame, 0.32, 0.52, 0.5)
    sub(c, g_flame, 0.68, 0.46, 0.6)


def b_funeral_pyre(c):
    b_pyre(c)


def b_blaze_ruin(c):
    g_burst(c, 12, 0.5, 0.36)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.36)
    sub(c, m_low_hp, 0.5, 0.52, 0.56)


def b_stormwhirl(c):
    b_drowning_gyre(c)
    sub(c, g_bolt, 0.82, 0.18, 0.36, knock=0.03)


def b_sky_tribunal(c):
    g_scales(c)
    sub(c, g_bolt, 0.5, 0.52, 0.3, knock=0.02)


def b_silent_thunder(c):
    g_crescent(c, 0.22, -0.16, 0.48, 0.4)
    sub(c, g_bolt, 0.64, 0.6, 0.56)
    sub(c, g_spark4, 0.8, 0.16, 0.26)


def b_dusk_verdict(c):
    c.circle(0.5, 0.5, 0.46)
    with c.op("shade"):
        c.poly([(0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0)])
    with c.op("cut"):
        c.circle(0.62, 0.42, 0.22)
    sub(c, g_mark, 0.34, 0.54, 0.34)


def b_thousand_cuts(c):
    for i, (x, y) in enumerate(((0.2, 0.2), (0.46, 0.14), (0.72, 0.24), (0.3, 0.5), (0.58, 0.46), (0.84, 0.54), (0.42, 0.78), (0.7, 0.8))):
        c.poly(stroke_poly([(x - 0.12, y + 0.1), (x + 0.12, y - 0.1)], 0.05))
    sub(c, g_drop, 0.16, 0.8, 0.24)


def b_amber_tomb(c):
    c.ngon(0.5, 0.5, 0.5, 6)
    with c.op("shade"):
        c.poly([polar(0.5, 0.5, 0.5, -30), polar(0.5, 0.5, 0.5, 30), polar(0.5, 0.5, 0.5, 90), (0.5, 0.5)])
    with c.op("cut"):
        with c.place(0.5, 0.5, 0.5):
            g_figure(c)


def b_doomsday_clock(c):
    g_clock(c, -80, -20, ticks=True)
    with c.op("cut"):
        c.circle(0.5, 0.66, 0.14)
    sub(c, g_skull, 0.5, 0.66, 0.22)


def b_tide_ages(c):
    with c.box(0.0, 0.34, 1.0, 1.0):
        g_wave(c)
    sub(c, g_hourglass, 0.74, 0.2, 0.36, knock=0.03)


def b_sunken_roots(c):
    c.poly(Path(0.0, 0.34).C(0.2, 0.26, 0.3, 0.42, 0.5, 0.34).C(0.7, 0.26, 0.8, 0.42, 1.0, 0.34).L(1.0, 0.42)
           .C(0.8, 0.5, 0.7, 0.34, 0.5, 0.42).C(0.3, 0.5, 0.2, 0.34, 0.0, 0.42).pts())
    sub(c, g_roots, 0.5, 0.7, 0.6)
    sub(c, g_drop, 0.5, 0.1, 0.2)


def b_hallowed_bulwark(c):
    c.ring(0.5, 0.1, 0.14, 0.05)
    with c.box(0.08, 0.24, 0.92, 1.0):
        b_granite_skin(c)


def b_covenant_blood(c):
    sub(c, g_drop, 0.5, 0.5, 0.64)
    c.arc(0.5, 0.5, 0.46, 0, 360, 0.05)
    for a in range(0, 360, 45):
        c.poly([polar(0.5, 0.5, 0.52, a), polar(0.5, 0.5, 0.42, a - 8), polar(0.5, 0.5, 0.42, a + 8)])


def b_day_reckoning(c):
    g_radiant(c)
    with c.op("cut"):
        c.circle(0.5, 0.5, 0.26)
    sub(c, g_skull, 0.5, 0.52, 0.34)


BOON_ART: dict[str, tuple[Callable, str]] = {
    # Pyra
    "pyra_wrathful_strike": (b_flaming_sword, "a flaming sword"), "pyra_kindling_volley": (b_flaming_bullets, "a kindled volley"),
    "pyra_cinder_bloom": (b_cinder_bloom, "a skull blooming into flame"), "pyra_blastfire_rounds": (b_blastfire, "a blastfire burst"),
    "pyra_flarestep": (b_dash_nova_el(g_flame), "a dash bursting into a fire ring"),
    "pyra_scorched_heavens": (b_ult_ground_el(g_flame), "flame over scorched ground"),
    "pyra_cauterize": (b_seared_heart, "a seared heart"), "pyra_conflagration": (b_twin_flame, "twin flames"),
    "pyra_roaring_pyre": (b_roaring_pyre, "a flame in widening rings"), "pyra_furnace_rite": (b_furnace_rite, "an ability tile aflame"),
    "pyra_searing_brand": (b_searing_brand, "a searing brand"), "pyra_pyre_eternal": (b_pyre, "an eternal pyre"),
    # Zephyros
    "zephyros_tailwind": (b_tailwind, "a winged boot"), "zephyros_stormbrand": (b_stormbrand, "a blade branded with a bolt"),
    "zephyros_leaping_arc": (b_leaping_arc, "an arc leaping between foes"),
    "zephyros_skystride": (b_dash_nova_el(g_bolt), "a dash cracking into a thunder ring"),
    "zephyros_quickening_gale": (b_gale_arrow, "a shot on a gale"), "zephyros_updraft": (b_updraft, "an updraft"),
    "zephyros_thunderhead": (b_thunderhead, "a thunderhead over the ground"), "zephyros_rebounding_gale": (b_rebounding_gale, "a gust-borne rebound"),
    "zephyros_ionized_air": (b_ionized, "a blade through a bolt"), "zephyros_galvanize": (b_galvanize, "an ability tile charged"),
    "zephyros_stormcalm": (b_stormcalm, "the calm eye of a storm"), "zephyros_thousandfold_thunder": (b_thousandfold, "branching lightning"),
    # Nyctia
    "nyctia_umbral_edge": (b_umbral_edge, "a blade and a crit spark"), "nyctia_quietus": (b_quietus, "a quiet blade"),
    "nyctia_serrated_shadow": (b_serrated, "a serrated blade and a drop"), "nyctia_veil_of_knives": (b_veil_knives, "knives in smoke"),
    "nyctia_ambuscade": (b_ambuscade, "a dagger from the dark of the moon"), "nyctia_shade_twin": (b_shade_twin, "a shadow double"),
    "nyctia_keen_darkness": (b_keen_dark, "a keen eye and a spark"), "nyctia_assassins_vow": (b_assassin_vow, "a dagger through a crown"),
    "nyctia_nightshroud": (b_nightshroud, "a night shroud"), "nyctia_hunting_shadows": (b_hunting_shadows, "a hunting shot under a crescent"),
    "nyctia_dark_of_the_moon": (b_dark_moon, "a darkened moon"), "nyctia_kiss_of_silence": (b_kiss_silence, "sealed lips over a blade"),
    # Aeon
    "aeon_stilled_sands": (b_stilled_sands, "stilled sands"), "aeon_ageless_flame": (b_ageless_flame, "a flame in a dial"),
    "aeon_unclosing_wounds": (b_unclosing, "drops in a turning-back arrow"), "aeon_quickened_hours": (b_quickened, "a dial with racing hands"),
    "aeon_rewinding_ward": (b_rewinding_ward, "a ward that winds back"), "aeon_echoing_instant": (b_echo_instant, "an echoing shot and a dial"),
    "aeon_stutterstep": (b_stutterstep, "a dash held in pause"), "aeon_shattered_moment": (b_shattered_moment, "a shattered dial"),
    "aeon_heavy_hours": (b_heavy_hours, "an hourglass with a weight"), "aeon_turning_hands": (b_turning_hands, "orbiting clock hands"),
    "aeon_wound_spring": (b_wound_spring, "a wound spring"), "aeon_eternal_recurrence": (b_recurrence, "a returning circle"),
    # Gaiaa
    "gaiaa_grasping_stone": (b_grasping_stone, "a hand rising from the ground"), "gaiaa_granite_skin": (b_granite_skin, "a granite plate"),
    "gaiaa_bedrock": (b_bedrock, "bedrock under a heart"), "gaiaa_bloodroot": (b_bloodroot, "a drop feeding roots"),
    "gaiaa_tremor_step": (b_tremor_step, "a quaking step"), "gaiaa_crush_the_bound": (b_crush_bound, "a blade through roots"),
    "gaiaa_sanguine_thorns": (b_sanguine_thorns, "a thorned vine and a drop"),
    "gaiaa_tectonic_wrath": (b_tectonic, "grinding plates"), "gaiaa_earthen_might": (b_earthen_might, "an ability tile with a fist"),
    "gaiaa_deep_marrow": (b_deep_marrow, "a bone and a heart"), "gaiaa_landslide": (b_landslide, "a landslide"),
    "gaiaa_unbroken_mountain": (b_unbroken, "a mountain under a shield"),
    # Morwenn
    "morwenn_brackish_pools": (b_brackish, "a brackish pool"), "morwenn_witchs_brine": (b_witchs_brine, "a bubbling cauldron"),
    "morwenn_plague_wake": (b_plague_wake, "a festering wake"), "morwenn_spreading_blight": (b_spreading_blight, "a drop splitting in two"),
    "morwenn_brinestep": (b_brinestep, "a dash riding a wave"), "morwenn_dragged_under": (b_dragged_under, "a tentacle dragging under"),
    "morwenn_deluge": (b_deluge, "a deluge"), "morwenn_drowning_gyre": (b_drowning_gyre, "a whirlpool"),
    "morwenn_contagion": (b_contagion, "linked spores and a hex eye"), "morwenn_wreckers_haul": (b_wreckers, "an anchor"),
    "morwenn_barnacle_hide": (b_barnacle, "a ribbed shell"), "morwenn_black_tide": (b_black_tide, "a black wave with a hex eye"),
    # Seraphel
    "seraphel_condemning_writ": (b_writ, "a writ bearing the mark"), "seraphel_sentence_passed": (b_sentence, "a blade through the mark"),
    "seraphel_aegis_of_law": (b_aegis_law, "a shield bearing scales"), "seraphel_lance_of_dawn": (b_lance_dawn, "a lance of dawn"),
    "seraphel_smite_the_mighty": (b_smite_mighty, "a beam striking a crown"),
    "seraphel_sanctified_step": (b_sanctified_step, "a dash flaring in a holy ring"),
    "seraphel_consecrated_ground": (b_ult_ground_el(g_radiant), "a sun over consecrated ground"),
    "seraphel_litany_of_light": (b_litany, "a book under a sun"), "seraphel_radiant_mantle": (b_radiant_mantle, "a haloed mantle"),
    "seraphel_rebuke": (b_rebuke, "a raised palm"), "seraphel_guiding_light": (b_guiding_light, "a lantern"),
    "seraphel_judgment_absolute": (b_judgment_absolute, "the mark inside a sun"),
    # Umbra-Rex
    "umbra_rex_brink_of_ruin": (b_brink_ruin, "a cracked heart with an ember"), "umbra_rex_tolling_doom": (b_tolling_doom, "a tolling bell"),
    "umbra_rex_pound_of_flesh": (b_pound_flesh, "a blade in a heart"), "umbra_rex_tyrants_haste": (b_tyrants_haste, "crowned shots"),
    "umbra_rex_ruinstep": (b_ruinstep, "a step that breaks the ground"),
    "umbra_rex_ashen_scar": (b_ashen_scar, "a void over a scar"), "umbra_rex_kings_tithe": (b_kings_tithe, "a crown and coins"),
    "umbra_rex_spite_of_the_dying": (b_spite_dying, "a skull and a drop"), "umbra_rex_weight_of_the_end": (b_weight_end, "an hourglass with a skull"),
    "umbra_rex_cinder_oath": (b_cinder_oath, "a shield with a flame"), "umbra_rex_harbinger": (b_harbinger, "a raven"),
    "umbra_rex_last_crown": (b_last_crown, "the broken crown"),
    # Team
    "bond_of_the_forge": (b_bond_forge, "dash chevrons over a chain"), "choir_of_anvils": (b_choir_anvils, "a singing anvil"),
    "spoils_of_the_shatterlands": (b_spoils, "a magnet drawing shards"), "wall_of_halos": (b_wall_halos, "four haloed figures"),
    # Duo
    "thunderburn": (b_thunderburn, "a bolt and a flame"), "pitchfire": (b_pitchfire, "burning pitch"),
    "funeral_pyre": (b_funeral_pyre, "a funeral pyre"), "blaze_of_ruin": (b_blaze_ruin, "a cracked heart bursting"),
    "stormwhirl": (b_stormwhirl, "a whirlpool with a bolt"), "sky_tribunal": (b_sky_tribunal, "scales with a bolt"),
    "silent_thunder": (b_silent_thunder, "a crescent and a bolt"), "dusk_verdict": (b_dusk_verdict, "a half-dark moon over the mark"),
    "thousand_cuts": (b_thousand_cuts, "a thousand cuts"), "amber_tomb": (b_amber_tomb, "a figure sealed in amber"),
    "doomsday_clock": (b_doomsday_clock, "a clock with a skull"), "tide_of_ages": (b_tide_ages, "a wave and an hourglass"),
    "sunken_roots": (b_sunken_roots, "roots under water"), "hallowed_bulwark": (b_hallowed_bulwark, "a haloed stone plate"),
    "covenant_of_blood": (b_covenant_blood, "a drop in a thorn ring"), "day_of_reckoning": (b_day_reckoning, "a skull in the sun"),
}

# The composition kit (UI_STYLE 9.4) for boons added later without a hand recipe: the first mod picks the motif.
MOD_MOTIFS: list[tuple[str, Callable]] = [
    ("ApplyStatus(status: Burn", g_flame), ("ApplyStatus(status: Shock", st_shock), ("ApplyStatus(status: Curse", g_hexeye),
    ("ApplyStatus(status: Root", g_roots), ("ApplyStatus(status: Bleed", g_blood), ("ApplyStatus(status: Mark", g_mark),
    ("DamageVsStatus", m_crit), ("ExplodeOnKill", m_bomb), ("Explode", m_explode), ("DashNova", m_dash_nova),
    ("UltGround", m_ult_ground), ("UltCharge", tm_ult_ready), ("Chain", m_chain), ("Ricochet", m_ricochet), ("Fork", m_fork),
    ("Pierce", m_pierce), ("Homing", m_homing), ("Orbit", m_orbit), ("EchoShot", m_echo), ("Trail", m_trail),
    ("Puddle", m_puddle), ("GravityWell", m_gravity), ("Doomstack", m_doom), ("Execute", m_execute), ("Lifesteal", m_fang_drop),
    ("MaxShield", g_shield), ("MaxHealth", m_heart_plus), ("Regen", m_regen), ("DamageTaken", g_shield),
    ("DamageWhileLowHp", m_low_hp), ("DamageVsFullHp", m_opener), ("DamageVsElites", m_giant), ("CritChance", m_crit),
    ("CritDamage", m_crit), ("FireRate", m_fire_rate), ("MoveSpeed", m_winged_boot), ("ProjectileSpeed", m_velocity),
    ("DashCharges", m_dash), ("DashRecharge", m_dash), ("CooldownRate", m_cooldown), ("ActiveDamage", m_active),
    ("Area", m_area), ("Knockback", m_knockback), ("ShardsOnKill", m_greed), ("Luck", m_clover), ("PickupRadius", g_magnet),
    ("Range", m_range), ("ChargeTime", m_charge), ("SpawnTurretOnCrit", g_turret), ("Damage", g_sword),
]


BOON_BOLD = {"nyctia_serrated_shadow": 0.01, "seraphel_lance_of_dawn": 0.006, "zephyros_quickening_gale": 0.006,
             "nyctia_hunting_shadows": 0.006, "morwenn_plague_wake": 0.006, "zephyros_thousandfold_thunder": 0.004}


def compose_boon(row: dict) -> tuple[Callable, str]:
    for needle, fn in MOD_MOTIFS:
        if needle in row["mods"]:
            return fn, f"composed from its {needle.split('(')[0]} mod"
    return bk_legendary, "a generic boon glyph"


@content_hook
def register_boons(content: Content):
    for row in content.boons:
        k = row["key"]
        gods = [g.strip() for g in row["gods"].split(";") if g.strip()]
        fn, note = BOON_ART.get(k) or compose_boon(row)
        tint = mix(T_BONE, god_tint(gods[0]), 0.55) if gods else T_KIT
        who = " & ".join(content.gods[g]["name"] for g in gods) if gods else "every player"
        meaning = f"{row['name']} ({row['kind']} boon, {who}): {row['desc']} Icon: {note}."
        reg("boons", k, fn, tint, meaning, kind="boon",
            extra={"gods": gods, "motif_name": note, "bold": BOON_BOLD.get(k, 0.0)})


# ───────────────────────────── special renderers ─────────────────────────────
def unit_disc(r_cell: float, cx: float = 0.5, cy: float = 0.5, soft: float = 1.0) -> np.ndarray:
    """A coverage disc on the WORK grid; r and centre in cell fractions."""
    yy, xx = np.mgrid[0:WORK, 0:WORK].astype(np.float32)
    d = np.sqrt((xx + 0.5 - cx * WORK) ** 2 + (yy + 0.5 - cy * WORK) ** 2)
    return np.clip(r_cell * WORK - d + 0.5 * soft, 0, 1)


def dilate(a: np.ndarray, px: float) -> np.ndarray:
    dist = ndimage.distance_transform_edt(a < 0.5).astype(np.float32)
    return np.maximum(a, np.clip(px - dist + 0.5, 0, 1))


def framed_prem(d: IconDef) -> np.ndarray:
    """Cores (a dark element orb with a lit motif) and sigils (a seal ring around a rune motif)."""
    frame = canvas_of(d.extra["frame"])
    motif = Canvas()
    msz = d.extra.get("motif_size", 0.6)
    with motif.place(0.5, 0.5 + d.extra.get("motif_dy", 0.0), msz):
        d.extra["motif"](motif)
    fm, fs, fk = fit_masks(frame, 1.0, autofit=False)
    mm, ms, mk = fit_masks(motif, 1.0, autofit=False)
    # keep the motif inside its window and separate it from the frame with an ink gap
    window = unit_disc(d.extra.get("window", 0.34))
    mm = mm * window
    ms = ms * window
    mk = mk * window
    gap = dilate(mm, WORK * 0.022)
    m = np.maximum(fm * (1 - (gap - mm) * d.extra.get("gap_cut", 0.0)), mm)
    s = np.clip(fs * (1 - gap) + ms, 0, 1)
    k = np.clip(np.maximum(fk * (1 - gap), mk) + (gap - mm) * fm * d.extra.get("gap_ink", 1.0), 0, 1)
    return enamel(m, s, k, d.tint, d.light)


def render_portrait(d: IconDef) -> np.ndarray:
    """A bust crest on a Ø116 circular lacquer window, clipped (UI_STYLE 9.3)."""
    c = Canvas()
    with c.place(0.5, 0.58, 1.16):
        d.draw(c)
    fitk = (116 / 128) / (1 - 2 * PAD)
    m, s, k = fit_masks(c, fitk, autofit=False)
    inner = unit_disc(0.5 * 116 / 128 - OUTLINE * 0.6)
    m, s, k = m * inner, s * inner, k * inner
    bust = enamel(m, s, k, d.tint, d.light)
    disc = unit_disc(0.5 * 116 / 128)
    yy, xx = np.mgrid[0:WORK, 0:WORK].astype(np.float32)
    r = np.sqrt((xx - WORK * 0.5) ** 2 + (yy - WORK * 0.42) ** 2) / (WORK * 0.58)
    back = ramp(np.clip(r, 0, 1), [(0.0, "#3E2C1E"), (0.55, "#22170F"), (1.0, "#0B0807")]) / 255.0
    edge = np.clip(1 - (0.5 * 116 / 128 * WORK - np.sqrt((xx - WORK / 2) ** 2 + (yy - WORK / 2) ** 2)) / (WORK * 0.05), 0, 1)
    back = back * (1 - 0.55 * edge[..., None])
    base = np.dstack([back * disc[..., None], disc])
    out = over(base, bust)
    return out * disc[..., None]


def render_boon(d: IconDef) -> np.ndarray:
    """A boon: the mechanic motif in a god-tinted ivory, with the god sigil(s) small at the top."""
    c = canvas_of(d.draw)
    m, s, k = fit_masks(c, d.fit * 0.9, d.autofit, d.extra.get("bold", 0.0))
    shift = int(WORK * 0.035)
    m, s, k = (np.roll(np.roll(a, shift, axis=0), -shift // 2, axis=1) for a in (m, s, k))
    main = enamel(m, s, k, d.tint, d.light)
    gods = d.extra.get("gods", [])
    spots = [(0.815, 0.185)] if len(gods) == 1 else [(0.185, 0.185), (0.815, 0.185)]
    for god, (bx, by) in zip(gods, spots):
        br = 0.175
        disc = unit_disc(br, bx, by)
        hole = dilate(disc, WORK * 0.03)
        main = main * (1 - hole[..., None])
        ring = np.clip(disc - unit_disc(br - 0.028, bx, by), 0, 1)
        col = np.array(rgb(god_tint(god)), np.float32) / 255.0
        inkc = np.array(rgb("#120C08"), np.float32) / 255.0
        badge = np.dstack([inkc * disc[..., None] * 0.95, disc * 0.95])
        badge = over(badge, np.dstack([col * ring[..., None], ring]))
        sig = Canvas()
        GOD_SIGILS[god](sig)
        sm, ss_, sk = fit_masks(sig, 1.0, True)
        scale = (br * 1.18)
        sm, ss_, sk = (small_at(a, scale, bx, by) for a in (sm, ss_, sk))
        glyph = enamel(sm, ss_, sk, god_tint(god), mix(IVORY, god_tint(god), 0.25), outline=0.0, bevel=False)
        badge = over(badge, glyph)
        main = over(main, badge)
    return main


def small_at(a: np.ndarray, scale: float, cx: float, cy: float) -> np.ndarray:
    """Scale a WORK-sized centred mask by `scale` and re-centre it at (cx, cy) (cell fractions)."""
    inv = 1.0 / scale
    return np.clip(ndimage.affine_transform(a, [inv, inv], offset=[WORK / 2 - cy * WORK * inv, WORK / 2 - cx * WORK * inv],
                                            output_shape=(WORK, WORK), order=1), 0, 1)


def render(d: IconDef) -> Image.Image:
    if d.kind == "gem":
        prem = d.draw()
    elif d.kind == "portrait":
        prem = render_portrait(d)
    elif d.kind == "boon":
        prem = render_boon(d)
    elif d.kind == "framed":
        prem = framed_prem(d)
    else:
        prem = render_glyph_prem(d)
    return to_image(downsample(prem, SS))


# ───────────────────────────── outputs ─────────────────────────────
GROUP_ORDER = ["elements", "rarity", "slots", "poi", "currency", "status", "states", "portraits", "kits", "chassis",
               "parts", "gods", "boons", "boon_kind", "aim", "team", "run", "ui", "input"]


def validate(content: Content):
    missing = []
    want = [f"parts/{k}" for k in content.ron_keys["parts"]]
    want += [f"boons/{k}" for k in content.ron_keys["boons"]]
    want += [f"chassis/{k}" for k in content.ron_keys["chassis"]]
    want += [f"gods/{k}" for k in content.ron_keys["gods"]]
    for ch in content.ron_keys["characters"]:
        want += [f"portraits/{ch}"] + [f"kits/{ch}_{s}" for s in ("q", "e", "r", "passive")]
    for k in want:
        if k not in ICONS:
            missing.append(k)
    if missing:
        raise SystemExit("content keys without an icon:\n  " + "\n  ".join(missing))


def write_rust_table(path: str, keys: list[str]):
    rel = os.path.relpath(OUT_DIR, os.path.dirname(os.path.abspath(path))).replace("\\", "/")
    lines = ["// GENERATED by tools/ui/make_icons.py; do not edit.",
             "// Every UI icon master (128x128 RGBA), keyed <group>/<name>, sorted.",
             "pub const ICONS: &[(&str, &[u8])] = &["]
    for k in keys:
        lines.append(f'    ("{k}", include_bytes!("{rel}/{k}.png")),')
    lines.append("];")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def _worker_init():
    content = load_content()
    for hook in CONTENT_HOOKS:
        hook(content)


def _render_png(key: str) -> bytes:
    buf = io.BytesIO()
    render(ICONS[key]).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated groups to (re)render")
    ap.add_argument("--keys", default="", help="comma-separated keys or name prefixes to render")
    ap.add_argument("--review", default="", help="also write big per-group review sheets into this folder")
    ap.add_argument("--no-sheet", action="store_true", help="skip the contact sheet")
    ap.add_argument("--rust-table", default="", help="write a Rust include_bytes! table to this path")
    ap.add_argument("--dev", action="store_true", help="skip the content coverage check (while drawing)")
    ap.add_argument("--jobs", type=int, default=max(1, min(8, (os.cpu_count() or 2) - 1)),
                    help="worker processes (the output does not depend on it)")
    args = ap.parse_args(argv)

    content = load_content()
    for hook in CONTENT_HOOKS:
        hook(content)
    if not args.dev:
        validate(content)

    only = {g for g in args.only.split(",") if g}
    pref = [k for k in args.keys.split(",") if k]
    keys = sorted(ICONS)
    todo = [k for k in keys if (not only or ICONS[k].group in only) and (not pref or any(k.startswith(p) or k.split("/")[1].startswith(p) for p in pref))]
    images: dict[str, Image.Image] = {}
    if args.jobs > 1 and len(todo) > 8:
        with ProcessPoolExecutor(max_workers=args.jobs, initializer=_worker_init) as ex:
            blobs = list(ex.map(_render_png, todo, chunksize=2))
    else:
        blobs = [_render_png(k) for k in todo]
    for k, blob in zip(todo, blobs):
        d = ICONS[k]
        path = os.path.join(OUT_DIR, d.group, d.name + ".png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(blob)
        images[k] = Image.open(io.BytesIO(blob)).convert("RGBA")
    print(f"rendered {len(todo)} icons into {os.path.relpath(OUT_DIR, ROOT)}")

    if not only and not pref:
        manifest = {"version": 1, "size": MASTER, "generator": "tools/ui/make_icons.py",
                    "note": "Masters are 128x128 straight-alpha RGBA. Tint and frame are applied by the UI; "
                            "rarity is never baked in except rarity/gem_*.",
                    "icons": {}}
        for k in keys:
            d = ICONS[k]
            e = {"file": f"{d.group}/{d.name}.png", "category": d.group, "meaning": d.meaning, "tint": d.tint}
            if d.extra.get("motif_name"):
                e["motif"] = d.extra["motif_name"]
            manifest["icons"][k] = e
        with open(os.path.join(OUT_DIR, "icons.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, indent=1, sort_keys=False, ensure_ascii=False)
            f.write("\n")
        print(f"wrote icons.json ({len(keys)} icons)")
        if args.rust_table:
            write_rust_table(args.rust_table, keys)
            print(f"wrote {args.rust_table}")
    if not args.no_sheet and not only and not pref:
        order = {g: i for i, g in enumerate(GROUP_ORDER)}
        sheet_keys = sorted(keys, key=lambda k: (order.get(ICONS[k].group, 99), k))
        contact_sheet(sheet_keys, images, SHEET_PATH, "GODFORGE · UI ICONS")
        print(f"wrote {os.path.relpath(SHEET_PATH, ROOT)}")
    if args.review:
        for i in range(0, len(todo), 35):
            part = todo[i:i + 35]
            contact_sheet(part, images, os.path.join(args.review, f"review_{i // 35:02d}.png"), "REVIEW",
                          sizes=(128, 48, 32, 24), cols=5)


if __name__ == "__main__":
    main()
