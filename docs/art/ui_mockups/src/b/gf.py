"""GODFORGE UI mockup kit (designer B, "Readable Chaos").

Everything is authored in 1080p reference units (1920x1080) and rendered supersampled onto a
1600x900 capture, exactly as Bevy would with UiScale = 900/1080.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import os
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', '..', 'assets', 'fonts') + '/'
W, H = 1920, 1080
SS = 3                      # supersample factor of the working canvas
UI = 1.0
K = UI * SS                 # logical (reference) px -> canvas px
RW, RH = W / UI, H / UI     # logical screen size (1778 x 1000 at 1600x900)


def wp(x, y):
    """Screenshot pixel -> logical px."""
    return x / UI, y / UI


def P(v):
    return v * K


# ───────────────────────────── tokens ─────────────────────────────
def hx(s, a=255):
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), a)


T = dict(
    ink='#0B0807', lac_top='#2A1E16', lac_bot='#130D0A', lac_hl='#4A3624',
    gold_hi='#FFECB0', gold_lt='#F2C667', gold_md='#C9933E', gold_dk='#7A5424', gold_sh='#3B2610',
    parch='#F4E6C8', parch_dim='#B9A98C', parch_mute='#7D705E', ink_text='#1A120B',
    hp_dk='#7E1420', hp='#C8323A', hp_lt='#E8574C', hp_ghost='#F0B37A',
    ward='#DCE6EA', steel='#9AA4AE', steel_dk='#4E5660',
    danger='#FF3B30',
    common='#CFC6B4', rare='#4FA3FF', epic='#B865FF', godforged='#FFB82E',
    kinetic='#F4E3C1', flame='#FF7A1A', storm='#3FD8FF', void='#A45CFF', plague='#86E03A', radiant='#FFE27A',
    p1='#FFC940', p2='#3FD8FF', p3='#B06CFF', p4='#5BE37D',
    up='#FFE08A', down='#A58C86',
)
C = {k: hx(v) for k, v in T.items()}


def rgba(c, a=None):
    if isinstance(c, str):
        c = C[c] if c in C else hx(c)
    if a is None:
        return tuple(c) if len(c) == 4 else (*c, 255)
    return (c[0], c[1], c[2], int(a * 255) if isinstance(a, float) else a)


def mix(a, b, t):
    a, b = rgba(a), rgba(b)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))


# ───────────────────────────── fonts ─────────────────────────────
_fc = {}


def font(name, size_ref, weight=None):
    size = max(4, round(size_ref * K))
    key = (name, size, weight)
    if key not in _fc:
        f = ImageFont.truetype(FONTS + name, size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight])
            except Exception:
                pass
        _fc[key] = f
    return _fc[key]


def cinzel(sz, w=700):
    return font('Cinzel-Variable.ttf', sz, w)


def body(sz, style='Medium'):
    return font(f'AlegreyaSans-{style}.ttf', sz)


def dejavu(sz):
    return font('DejaVuSans.ttf', sz)


# ───────────────────────────── raster helpers ─────────────────────────────
def grad_img(w, h, stops, horizontal=False):
    """stops: [(t, color)] ascending."""
    n = w if horizontal else h
    t = np.linspace(0, 1, max(n, 1))
    ts = [s[0] for s in stops]
    cols = np.array([rgba(s[1]) for s in stops], dtype=np.float32)
    ch = [np.interp(t, ts, cols[:, i]) for i in range(4)]
    line = np.stack(ch, -1)
    if horizontal:
        arr = np.repeat(line[None, :, :], h, 0)
    else:
        arr = np.repeat(line[:, None, :], w, 1)
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')


def radial_img(w, h, inner, outer, cx=0.5, cy=0.5, rx=0.5, ry=0.5, power=1.0):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x / max(w, 1) - cx) / rx) ** 2 + ((y / max(h, 1) - cy) / ry) ** 2)
    t = np.clip(d, 0, 1) ** power
    a, b = np.array(rgba(inner), np.float32), np.array(rgba(outer), np.float32)
    arr = a[None, None, :] * (1 - t[..., None]) + b[None, None, :] * t[..., None]
    return Image.fromarray(arr.astype(np.uint8), 'RGBA')


GOLD_STOPS = [(0, 'gold_hi'), (0.22, 'gold_lt'), (0.5, 'gold_md'), (0.78, 'gold_dk'), (1.0, 'gold_md')]
GOLD_SOFT = [(0, 'gold_lt'), (0.5, 'gold_md'), (1.0, 'gold_dk')]
LAQ_STOPS = [(0, 'lac_top'), (1, 'lac_bot')]


def with_alpha(img, a):
    if a >= 1:
        return img
    r, g, b, al = img.split()
    al = al.point(lambda v: int(v * a))
    return Image.merge('RGBA', (r, g, b, al))


def mask_mul(img, mask):
    """Multiply img alpha by an L mask of the same size."""
    r, g, b, a = img.split()
    a = ImageChops.multiply(a, mask)
    return Image.merge('RGBA', (r, g, b, a))


def solid(w, h, color):
    return Image.new('RGBA', (w, h), rgba(color))


def noise_grain(w, h, amp=10, seed=3):
    rng = np.random.default_rng(seed)
    n = rng.normal(0, amp, (h // 3 + 1, w // 3 + 1)).astype(np.float32)
    img = Image.fromarray(np.clip(n + 128, 0, 255).astype(np.uint8), 'L').resize((w, h), Image.BILINEAR)
    return img


class Canvas:
    def __init__(self, bg_path=None, bg=None):
        if bg is None:
            bg = Image.open(bg_path).convert('RGB')
        bg = bg.resize((W, H), Image.LANCZOS)
        self.base = bg
        self.img = bg.convert('RGBA').resize((W * SS, H * SS), Image.BICUBIC)

    # composite an RGBA layer at canvas px position
    def put(self, layer, x, y):
        x, y = int(round(x)), int(round(y))
        self.img.alpha_composite(layer, (max(x, 0), max(y, 0)),
                                 (max(-x, 0), max(-y, 0)))

    def dim(self, alpha, color='#07050A'):
        self.img.alpha_composite(solid(*self.img.size, rgba(color, alpha)))

    def vignette(self, strength=0.6, color='#050303'):
        w, h = self.img.size
        v = radial_img(w // 4, h // 4, rgba(color, 0), rgba(color, strength), rx=0.72, ry=0.72, power=2.2)
        self.img.alpha_composite(v.resize((w, h), Image.BILINEAR))

    def save(self, path):
        out = self.img.resize((W, H), Image.LANCZOS).convert('RGB')
        out.save(path)
        return out


# shape masks (canvas px), drawn at 1x canvas (already supersampled)
def rr_mask(w, h, r):
    m = Image.new('L', (max(1, int(w)), max(1, int(h))), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, int(w) - 1, int(h) - 1], radius=max(0, int(r)), fill=255)
    return m


def chamfer_poly(w, h, c):
    return [(c, 0), (w - c, 0), (w, c), (w, h - c), (w - c, h), (c, h), (0, h - c), (0, c)]


def poly_mask(w, h, pts):
    m = Image.new('L', (max(1, int(w)), max(1, int(h))), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def ring_of(mask, width):
    """Inner ring of a mask (erode and subtract)."""
    k = int(width) * 2 + 1
    er = mask.filter(ImageFilter.MinFilter(k if k % 2 else k + 1))
    return ImageChops.subtract(mask, er)


def grow(mask, width):
    k = int(width) * 2 + 1
    return mask.filter(ImageFilter.MaxFilter(k))


def shrink(mask, width):
    k = int(width) * 2 + 1
    return mask.filter(ImageFilter.MinFilter(k))


def pad_mask(mask, pad):
    m = Image.new('L', (mask.width + 2 * pad, mask.height + 2 * pad), 0)
    m.paste(mask, (pad, pad))
    return m


def shadow(cv, mask, x, y, blur=P(10), off=(0, P(4)), alpha=0.6, spread=0, color='#000000'):
    pad = int(blur * 2 + spread + 4)
    m = pad_mask(mask, pad)
    if spread:
        m = grow(m, spread)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    lay = solid(m.width, m.height, rgba(color, alpha))
    lay = mask_mul(lay, m)
    cv.put(lay, x - pad + off[0], y - pad + off[1])


def glow(cv, mask, x, y, color, blur=P(8), alpha=0.8, spread=0):
    shadow(cv, mask, x, y, blur=blur, off=(0, 0), alpha=alpha, spread=spread, color=color)


def fill_mask(cv, mask, x, y, fill):
    """fill: color, or an RGBA image the size of the mask."""
    if isinstance(fill, Image.Image):
        lay = fill
    else:
        lay = solid(mask.width, mask.height, fill)
    cv.put(mask_mul(lay, mask), x, y)


def gold_fill(w, h, stops=GOLD_STOPS):
    return grad_img(int(w), int(h), stops)


# ───────────────────────────── frames ─────────────────────────────
def quiet_plate(cv, x, y, w, h, r=4, alpha=0.78, rim=0.55, sh=0.55, shape=None, top='lac_top', bot='lac_bot'):
    """Combat-HUD plate: lacquer gradient, gold hairline, inner highlight, soft drop shadow (ref units)."""
    X, Y, Wd, Ht = P(x), P(y), P(w), P(h)
    m = shape if shape is not None else rr_mask(Wd, Ht, P(r))
    if sh:
        shadow(cv, m, X, Y, blur=P(9), off=(0, P(3)), alpha=sh)
    fill = grad_img(m.width, m.height, [(0, rgba(top, alpha)), (1, rgba(bot, alpha))])
    fill_mask(cv, m, X, Y, fill)
    if rim:
        ring = ring_of(m, max(1, P(1.1)))
        fill_mask(cv, ring, X, Y, with_alpha(gold_fill(m.width, m.height, GOLD_SOFT), rim))
        hl = ring_of(shrink(m, P(1.1)), max(1, P(0.8)))
        top_only = grad_img(m.width, m.height, [(0, rgba('gold_hi', 0.28)), (0.35, rgba('gold_hi', 0.0)), (1, rgba('gold_hi', 0))])
        fill_mask(cv, hl, X, Y, top_only)
    return m


def gilt_frame(cv, x, y, w, h, r=8, fill_alpha=0.94, thick=3.0, corners=True, top='lac_top', bot='lac_bot',
               glow_color=None, inner_line=True, sh=0.7):
    """Premium panel frame: double gold rim with bevel, lacquer body, anvil-horn corner flourishes."""
    X, Y, Wd, Ht = P(x), P(y), P(w), P(h)
    m = rr_mask(Wd, Ht, P(r))
    if sh:
        shadow(cv, m, X, Y, blur=P(18), off=(0, P(8)), alpha=sh)
    if glow_color:
        glow(cv, m, X, Y, glow_color, blur=P(16), alpha=0.35)
    body_ = grad_img(m.width, m.height, [(0, rgba(top, fill_alpha)), (1, rgba(bot, fill_alpha))])
    grain = noise_grain(m.width, m.height, 7)
    body_ = Image.merge('RGBA', (*[ImageChops.add(ch, ImageChops.subtract(grain, Image.new('L', grain.size, 124)))
                                   for ch in body_.split()[:3]], body_.split()[3]))
    fill_mask(cv, m, X, Y, body_)
    # outer dark edge, bright rim, dark groove, thin inner rim
    ring_outer = ring_of(m, P(thick))
    fill_mask(cv, ring_outer, X, Y, gold_fill(m.width, m.height))
    edge = ring_of(m, max(1, P(0.7)))
    fill_mask(cv, edge, X, Y, rgba('gold_sh', 0.9))
    if inner_line:
        inner = shrink(m, P(thick + 3.5))
        ir = ring_of(inner, max(1, P(1.0)))
        fill_mask(cv, ir, X, Y, with_alpha(gold_fill(m.width, m.height, GOLD_SOFT), 0.75))
    if corners:
        for (cx, cy, fx, fy) in [(x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)]:
            corner_flourish(cv, cx, cy, fx, fy, size=22)
    return m


def corner_flourish(cv, cx, cy, fx, fy, size=22):
    """An original 'anvil-horn' corner: an L bracket that tapers into a horn with a rivet."""
    s = P(size) * 2
    n = int(s * 2)
    m = Image.new('L', (n, n), 0)
    d = ImageDraw.Draw(m)
    o = n * 0.18
    t = n * 0.07
    # bracket arms, tapering
    d.polygon([(o, o), (n * 0.92, o), (n * 0.80, o + t), (o + t, o + t), (o + t, n * 0.80), (o, n * 0.92)], fill=255)
    # horn curl
    d.pieslice([o - t * 0.2, o - t * 0.2, o + n * 0.36, o + n * 0.36], 180, 270, fill=255)
    d.ellipse([o + n * 0.12, o + n * 0.12, o + n * 0.30, o + n * 0.30], fill=0)
    d.polygon([(o + t * 1.4, o + t * 1.4), (o + n * 0.2, o + t * 1.4), (o + t * 1.4, o + n * 0.2)], fill=255)
    # rivet
    r = n * 0.045
    d.ellipse([o + n * 0.21 - r, o + n * 0.21 - r, o + n * 0.21 + r, o + n * 0.21 + r], fill=255)
    m = m.resize((n // 2, n // 2), Image.LANCZOS)
    if fx < 0:
        m = m.transpose(Image.FLIP_LEFT_RIGHT)
    if fy < 0:
        m = m.transpose(Image.FLIP_TOP_BOTTOM)
    X = P(cx) - (m.width * 0.18 if fx > 0 else m.width * 0.82)
    Y = P(cy) - (m.height * 0.18 if fy > 0 else m.height * 0.82)
    shadow(cv, m, X, Y, blur=P(2), off=(0, P(1.5)), alpha=0.8)
    fill_mask(cv, grow(m, 1), X, Y, rgba('gold_sh'))
    fill_mask(cv, m, X, Y, gold_fill(m.width, m.height))


def filigree_rule(cv, cx, y, half, color_alpha=1.0, gem=None, thick=1.4, gap=0):
    """A horizontal gold rule that tapers to points, with a central lozenge (and optional gem)."""
    w = P(half) * 2
    h = P(14)
    m = Image.new('L', (int(w) + 4, int(h)), 0)
    d = ImageDraw.Draw(m)
    mid = m.width / 2
    yy = h / 2
    t = P(thick)
    g = P(gap)
    d.polygon([(2, yy), (mid - P(10) - g, yy - t), (mid - P(10) - g, yy + t)], fill=255)
    d.polygon([(m.width - 2, yy), (mid + P(10) + g, yy - t), (mid + P(10) + g, yy + t)], fill=255)
    if not g:
        q = P(6.5)
        d.polygon([(mid, yy - q), (mid + q, yy), (mid, yy + q), (mid - q, yy)], fill=255)
        d.polygon([(mid - P(12), yy), (mid - P(9), yy - P(2.5)), (mid - P(6), yy), (mid - P(9), yy + P(2.5))], fill=255)
        d.polygon([(mid + P(12), yy), (mid + P(9), yy - P(2.5)), (mid + P(6), yy), (mid + P(9), yy + P(2.5))], fill=255)
    X, Y = P(cx) - m.width / 2, P(y) - h / 2
    shadow(cv, m, X, Y, blur=P(2), off=(0, P(1.2)), alpha=0.7)
    fill_mask(cv, m, X, Y, with_alpha(gold_fill(m.width, m.height), color_alpha))
    if gem and not g:
        gem_at(cv, cx, y, 4.2, gem)


def gem_at(cv, cx, cy, r, color, facet=True, glow_a=0.5):
    """A cut lozenge gem (rarity / socket)."""
    R = P(r) * 2
    n = int(R * 2 + 6)
    m = Image.new('L', (n, n), 0)
    d = ImageDraw.Draw(m)
    c = n / 2
    d.polygon([(c, c - R), (c + R, c), (c, c + R), (c - R, c)], fill=255)
    m = m.resize((n // 2, n // 2), Image.LANCZOS)
    X, Y = P(cx) - m.width / 2, P(cy) - m.height / 2
    if glow_a:
        glow(cv, m, X, Y, color, blur=P(r * 0.9), alpha=glow_a, spread=0)
    fill_mask(cv, grow(m, max(1, P(0.9))), X, Y, rgba('gold_sh'))
    base = rgba(color)
    g = grad_img(m.width, m.height, [(0, mix(base, '#FFFFFF', 0.55)), (0.45, base), (1, mix(base, '#000000', 0.45))])
    fill_mask(cv, m, X, Y, g)
    if facet:
        f = Image.new('L', m.size, 0)
        fd = ImageDraw.Draw(f)
        c2 = m.width / 2
        rr = m.width / 2 * 0.55
        fd.polygon([(c2 - rr * 0.1, c2 - rr), (c2 + rr * 0.55, c2 - rr * 0.1), (c2 - rr * 0.1, c2 - rr * 0.1)], fill=200)
        fill_mask(cv, f, X, Y, rgba('#FFFFFF', 0.75))


# ───────────────────────────── text ─────────────────────────────
def text_mask(s, f, tracking=0.0):
    """Return (L mask, baseline_y, width). tracking: extra px (canvas) between glyphs."""
    asc, desc = f.getmetrics()
    if tracking == 0:
        w = f.getlength(s)
        m = Image.new('L', (int(w) + 8, asc + desc + 8), 0)
        ImageDraw.Draw(m).text((4, 4), s, font=f, fill=255)
        return m, asc + 4, w
    widths = [f.getlength(ch) for ch in s]
    total = sum(widths) + tracking * (len(s) - 1)
    m = Image.new('L', (int(total) + 8, asc + desc + 8), 0)
    d = ImageDraw.Draw(m)
    xx = 4
    for ch, wd in zip(s, widths):
        d.text((xx, 4), ch, font=f, fill=255)
        xx += wd + tracking
    return m, asc + 4, total


def draw_text(cv, x, y, s, f, fill='parch', anchor='l', tracking=0.0, shadow_a=0.85, shadow_off=(0, 1.6),
              shadow_blur=1.6, glow_color=None, glow_a=0.0, stroke=0, stroke_color='#0B0807', alpha=1.0, grad=None):
    """x,y in ref units; y is the baseline. anchor l/m/r. tracking in em (fraction of font size)."""
    trk = tracking * f.size
    m, base, w = text_mask(s, f, trk)
    X = P(x) - 4 - (w / 2 if anchor == 'm' else w if anchor == 'r' else 0)
    Y = P(y) - base
    if glow_color and glow_a:
        glow(cv, m, X, Y, glow_color, blur=f.size * 0.35, alpha=glow_a)
    if stroke:
        sm = grow(m, P(stroke))
        fill_mask(cv, sm, X, Y, rgba(stroke_color, 0.9 * alpha))
    if shadow_a:
        shadow(cv, m, X, Y, blur=P(shadow_blur), off=(P(shadow_off[0]), P(shadow_off[1])), alpha=shadow_a * alpha)
    if grad is not None:
        lay = grad_img(m.width, m.height, [(0, grad[0]), (0.55, grad[1]), (1, grad[2] if len(grad) > 2 else grad[1])])
        lay = with_alpha(lay, alpha)
    else:
        lay = solid(m.width, m.height, rgba(fill, alpha) if not isinstance(fill, tuple) else (fill[:3] + (int(fill[3] * alpha) if len(fill) > 3 else int(255 * alpha),)))
    fill_mask(cv, m, X, Y, lay)
    return w / K


def text_w(s, f, tracking=0.0):
    return text_mask(s, f, tracking * f.size)[2] / K


def wrap(s, f, width_ref):
    words = s.split()
    lines, cur = [], ''
    for wd in words:
        t = (cur + ' ' + wd).strip()
        if text_w(t, f) <= width_ref:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def rich_line(cv, x, y, parts, anchor='l', shadow_a=0.85):
    """parts: [(text, font, color)] drawn left to right on one baseline."""
    total = sum(text_w(t, f) for t, f, _ in parts)
    xx = x - (total / 2 if anchor == 'm' else total if anchor == 'r' else 0)
    for t, f, col in parts:
        draw_text(cv, xx, y, t, f, fill=col, shadow_a=shadow_a)
        xx += text_w(t, f)
    return total


# ───────────────────────────── widgets ─────────────────────────────
def keycap(cv, cx, cy, label, h=20, pad=6, dark=False, alpha=1.0, fsize=None):
    """Keybind chip: dark keycap, gold rim, Cinzel caps."""
    f = body(fsize or h * 0.72, 'Bold') if label.isdigit() else cinzel(fsize or h * 0.62, 800)
    tw = text_w(label, f)
    w = max(h, tw + pad * 2)
    X, Y = P(cx - w / 2), P(cy - h / 2)
    m = rr_mask(P(w), P(h), P(4))
    shadow(cv, m, X, Y, blur=P(2), off=(0, P(1.5)), alpha=0.8 * alpha)
    fill_mask(cv, m, X, Y, with_alpha(grad_img(m.width, m.height, [(0, '#3A2B1E'), (1, '#16100B')]), alpha))
    fill_mask(cv, ring_of(m, max(1, P(1))), X, Y, with_alpha(gold_fill(m.width, m.height, GOLD_SOFT), alpha))
    # bottom lip
    lip = Image.new('L', m.size, 0)
    ImageDraw.Draw(lip).rectangle([0, m.height - P(3), m.width, m.height], fill=255)
    fill_mask(cv, ImageChops.multiply(lip, shrink(m, P(1))), X, Y, rgba('#000000', 0.45 * alpha))
    draw_text(cv, cx, cy + h * 0.24, label, f, fill='parch', anchor='m', shadow_a=0, alpha=alpha)
    return w


def pad_button(cv, cx, cy, which, r=10, alpha=1.0):
    """Generic gamepad face-button glyph (original: a round stud with a letter)."""
    col = {'A': '#8FD18B', 'B': '#E88A7E', 'X': '#8CB8F0', 'Y': '#F0D27A'}.get(which, '#CFC6B4')
    R = P(r)
    m = Image.new('L', (int(R * 2) + 2, int(R * 2) + 2), 0)
    ImageDraw.Draw(m).ellipse([0, 0, R * 2, R * 2], fill=255)
    X, Y = P(cx) - R, P(cy) - R
    shadow(cv, m, X, Y, blur=P(2), off=(0, P(1.5)), alpha=0.8)
    fill_mask(cv, m, X, Y, with_alpha(grad_img(m.width, m.height, [(0, '#3A2B1E'), (1, '#140E0A')]), alpha))
    fill_mask(cv, ring_of(m, max(1, P(1.4))), X, Y, rgba(col, alpha))
    draw_text(cv, cx, cy + r * 0.42, which, cinzel(r * 1.15, 800), fill=col, anchor='m', shadow_a=0, alpha=alpha)


def bar(cv, x, y, w, h, frac, fill_stops, ghost=None, ghost_color='hp_ghost', trough='#0E0907', r=None, rim=0.7,
        sheen=True, ticks=None, notch_color='gold_lt'):
    r = h / 2 if r is None else r
    X, Y, Wd, Ht = P(x), P(y), P(w), P(h)
    m = rr_mask(Wd, Ht, P(r))
    shadow(cv, m, X, Y, blur=P(3), off=(0, P(1.5)), alpha=0.7)
    fill_mask(cv, m, X, Y, rgba(trough, 0.88))
    inner = shrink(m, P(1.2))

    def seg(f0, f1, lay):
        mm = Image.new('L', m.size, 0)
        ImageDraw.Draw(mm).rectangle([Wd * f0, 0, Wd * f1, Ht], fill=255)
        fill_mask(cv, ImageChops.multiply(mm, inner), X, Y, lay)
    if ghost is not None and ghost > frac:
        seg(frac, ghost, grad_img(m.width, m.height, [(0, mix(ghost_color, '#FFFFFF', 0.25)), (1, rgba(ghost_color))]))
    if frac > 0:
        seg(0, frac, grad_img(m.width, m.height, fill_stops))
        if sheen:
            s = grad_img(m.width, m.height, [(0, rgba('#FFFFFF', 0.38)), (0.45, rgba('#FFFFFF', 0.05)), (0.5, rgba('#000000', 0.0)), (1, rgba('#000000', 0.25))])
            seg(0, frac, s)
        # leading edge highlight
        edge = Image.new('L', m.size, 0)
        ImageDraw.Draw(edge).rectangle([Wd * frac - P(1.6), 0, Wd * frac, Ht], fill=255)
        fill_mask(cv, ImageChops.multiply(edge, inner), X, Y, rgba('#FFF4DC', 0.55))
    if ticks:
        for t in ticks:
            tk = Image.new('L', m.size, 0)
            ImageDraw.Draw(tk).rectangle([Wd * t - P(0.8), 0, Wd * t + P(0.8), Ht], fill=255)
            fill_mask(cv, ImageChops.multiply(tk, inner), X, Y, rgba('#000000', 0.55))
    if rim:
        fill_mask(cv, ring_of(m, max(1, P(1))), X, Y, with_alpha(gold_fill(m.width, m.height, GOLD_SOFT), rim))
    return m


def conic_mask(size, frac, start_deg=-90):
    m = Image.new('L', (size, size), 0)
    if frac > 0:
        ImageDraw.Draw(m).pieslice([0, 0, size - 1, size - 1], start_deg, start_deg + 360 * frac, fill=255)
    return m


def circle_mask(d):
    d = int(d)
    m = Image.new('L', (d * 2, d * 2), 0)
    ImageDraw.Draw(m).ellipse([0, 0, d * 2 - 1, d * 2 - 1], fill=255)
    return m.resize((d, d), Image.LANCZOS)


def place_icon(cv, icon, cx, cy, size, alpha=1.0, tint=None, desat=0.0, dark=0.0):
    """icon: RGBA master (any size). size in ref px."""
    s = int(P(size))
    im = icon.resize((s, s), Image.LANCZOS)
    if desat or dark or tint:
        r, g, b, a = [np.asarray(ch, np.float32) for ch in im.split()]
        rgb = np.stack([r, g, b], -1)
        if desat:
            lum = (rgb @ np.array([0.3, 0.59, 0.11], np.float32))[..., None]
            rgb = rgb * (1 - desat) + lum * desat
        if tint:
            tc = np.array(rgba(tint)[:3], np.float32) / 255
            rgb = rgb * tc
        if dark:
            rgb = rgb * (1 - dark)
        im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8), 'RGBA')
    if alpha < 1:
        im = with_alpha(im, alpha)
    cv.put(im, P(cx) - s / 2, P(cy) - s / 2)


def sepia_map(img, strength=0.78):
    """Minimap look: kill preview labels, fold terrain into a warm ink-and-parchment ramp."""
    from PIL import ImageFilter
    im = img.convert('RGB')
    a = np.asarray(im, np.float32) / 255
    lum = a @ np.array([0.3, 0.59, 0.11], np.float32)
    ramp_t = [0, 0.35, 0.7, 1]
    ramp = np.array([[20, 14, 10], [70, 52, 36], [150, 118, 80], [226, 200, 150]], np.float32) / 255
    sep = np.stack([np.interp(lum, ramp_t, ramp[:, i]) for i in range(3)], -1)
    out = sep * strength + a * (1 - strength)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), 'RGB')
