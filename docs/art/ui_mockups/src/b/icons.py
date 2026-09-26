"""Original GODFORGE icon masters (vector-built, 512 px working size, 256 px masters).

Style: silhouette first, 2-3 values (light face, mid body, ink), bevel light from the top-left,
2.5 % ink outline. Nothing here is traced from any reference.
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from gf import grad_img, rgba, mix, mask_mul, solid, grow, shrink

N = 512


def new():
    m = Image.new('L', (N, N), 0)
    return m, ImageDraw.Draw(m)


def bez(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in np.linspace(0, 1, n)]


def circ(d, cx, cy, r, fill=255):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def ring(d, cx, cy, r, w, fill=255):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fill, width=int(w))


def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def rrect(cx, cy, w, h, deg=0):
    pts = [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
    return rot(pts, cx, cy, deg)


def star(cx, cy, r1, r2, n, deg=-90):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.radians(deg + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def flame_pts(cx, cy, w, h, lean=0.0):
    """Teardrop flame: round base at the bottom, S-curved tip at the top."""
    base_r = w / 2
    by = cy + h / 2 - base_r
    tip = (cx + lean * w, cy - h / 2)
    left = bez((cx - base_r, by), (cx - base_r * 1.05, cy - h * 0.15), tip)
    right = bez(tip, (cx + base_r * 0.9, cy - h * 0.05), (cx + base_r, by))
    arc = [(cx + base_r * math.cos(a), by + base_r * math.sin(a)) for a in np.linspace(0, math.pi, 20)]
    return left + right + arc


def flame3(d, cx, cy, w, h, fill=255):
    """Three-tongue flame: a tall S-curved main tongue and two leaning side licks on a round base."""
    d.polygon(flame_pts(cx + w * 0.02, cy, w * 0.78, h, 0.10), fill=fill)
    d.polygon(flame_pts(cx - w * 0.24, cy + h * 0.17, w * 0.46, h * 0.62, -0.32), fill=fill)
    d.polygon(flame_pts(cx + w * 0.25, cy + h * 0.2, w * 0.42, h * 0.55, 0.36), fill=fill)
    r = w * 0.40
    d.ellipse([cx - r, cy + h / 2 - 2 * r, cx + r, cy + h / 2], fill=fill)


def bolt_pts(cx, cy, s):
    return [(cx + x * s, cy + y * s) for x, y in
            [(0.12, -1.0), (-0.52, 0.12), (-0.05, 0.12), (-0.22, 1.0), (0.55, -0.22), (0.06, -0.22), (0.3, -1.0)]]


def anvil_pts(cx, cy, s):
    """Anvil silhouette (horn to the left)."""
    pts = [(-1.0, -0.42), (-0.55, -0.52), (0.95, -0.52), (0.95, -0.2), (0.5, -0.2), (0.28, 0.05), (0.28, 0.32),
           (0.62, 0.36), (0.62, 0.55), (-0.52, 0.55), (-0.52, 0.36), (-0.2, 0.32), (-0.2, 0.05), (-0.45, -0.2),
           (-0.62, -0.26)]
    return [(cx + x * s, cy + y * s) for x, y in pts]


def finish(sil, detail=None, face=('#FFF4D6', '#EBC06E', '#9C6B2B'), ink='#120B07', outline=14, bevel=9,
           rim=None, glow=None, size=256, cut=None):
    """Turn a silhouette mask into a finished icon."""
    if cut is not None:
        sil = ImageChops.subtract(sil, cut)
    pad = 40
    big = Image.new('L', (N + pad * 2, N + pad * 2), 0)
    big.paste(sil, (pad, pad))
    sil = big
    W = sil.width
    out = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    if glow:
        g = grow(sil, 10).filter(ImageFilter.GaussianBlur(22))
        out.alpha_composite(mask_mul(solid(W, W, rgba(glow, 0.9)), g))
    if rim:
        rm = grow(sil, outline + 9)
        out.alpha_composite(mask_mul(grad_img(W, W, [(0, '#FFE9A8'), (0.5, '#C9933E'), (1, '#6E4A1E')]), rm))
    om = grow(sil, outline)
    out.alpha_composite(mask_mul(solid(W, W, rgba(ink)), om))
    fg = grad_img(W, W, [(0.1, face[0]), (0.5, face[1]), (0.92, face[2])])
    out.alpha_composite(mask_mul(fg, sil))
    # bevel: light on up-left edges, shade on down-right
    sh1 = ImageChops.offset(sil, bevel, bevel)
    hl = ImageChops.subtract(sil, sh1).filter(ImageFilter.GaussianBlur(2))
    out.alpha_composite(mask_mul(solid(W, W, rgba('#FFFFFF', 0.55)), hl))
    sh2 = ImageChops.offset(sil, -bevel, -bevel)
    dk = ImageChops.subtract(sil, sh2).filter(ImageFilter.GaussianBlur(2))
    out.alpha_composite(mask_mul(solid(W, W, rgba('#000000', 0.38)), dk))
    if detail is not None:
        dm = Image.new('L', (W, W), 0)
        dm.paste(detail, (pad, pad))
        dm = ImageChops.multiply(dm, sil)
        out.alpha_composite(mask_mul(solid(W, W, rgba(ink, 0.92)), dm))
    out = out.crop((pad // 2, pad // 2, W - pad // 2, W - pad // 2))
    return out.resize((size, size), Image.LANCZOS)


def tone(color, light=0.55, dark=0.45):
    return (mix(color, '#FFFFFF', light), rgba(color), mix(color, '#000000', dark))


GOLD_FACE = ('#FFF4D6', '#EBC06E', '#9C6B2B')
BONE_FACE = ('#FFF8E8', '#E9D8B2', '#A48B63')
STEEL_FACE = ('#F2F6F8', '#B8C1CA', '#5B6570')


# ───────────────────────── characters (portrait sigils) ─────────────────────────
def valdris():
    m, d = new()
    d.polygon(anvil_pts(256, 300, 200), fill=255)
    # hammer raised over the anvil
    d.polygon(rrect(300, 150, 150, 70, -28), fill=255)
    d.polygon(rrect(240, 205, 26, 150, -28), fill=255)
    det, dd = new()
    dd.line([(150, 206), (440, 206)], fill=255, width=8)
    return finish(m, det)


def selene():
    m, d = new()
    circ(d, 240, 256, 170)
    cut, c = new()
    circ(c, 300, 225, 150)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon(bolt_pts(318, 262, 150), fill=255)
    return finish(m, face=tone('#BFEFFF', 0.6, 0.55))


def kael():
    m, d = new()
    # hood
    d.polygon(bez((256, 70), (430, 150), (400, 420)) + [(330, 440), (256, 380), (182, 440), (112, 420)] +
              bez((112, 420), (82, 150), (256, 70))[1:], fill=255)
    cut, c = new()
    c.polygon(bez((256, 170), (350, 230), (320, 380)) + [(256, 330), (192, 380)] + bez((192, 380), (162, 230), (256, 170))[1:], fill=255)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    # eyes
    d.polygon([(205, 275), (245, 262), (240, 282)], fill=255)
    d.polygon([(307, 275), (267, 262), (272, 282)], fill=255)
    return finish(m, face=tone('#D9C8F2', 0.5, 0.55))


# ───────────────────────── Valdris kit ─────────────────────────
def bulwark_slam():
    m, d = new()
    # fist-hammer coming down
    d.polygon(rrect(256, 140, 170, 110, 0), fill=255)
    d.polygon(rrect(256, 60, 40, 80), fill=255)
    # impact wall
    d.polygon([(80, 360), (432, 360), (432, 440), (80, 440)], fill=255)
    for x in (120, 200, 280, 360):
        d.polygon([(x, 360), (x + 30, 330), (x + 60, 360)], fill=255)
    # shock lines
    for a, l in [(-150, 80), (-120, 70), (-60, 70), (-30, 80)]:
        r = math.radians(a)
        x0, y0 = 256 + 130 * math.cos(r), 290 + 110 * math.sin(r)
        d.line([(x0, y0), (x0 + l * math.cos(r), y0 + l * math.sin(r))], fill=255, width=22)
    det, dd = new()
    dd.line([(80, 400), (432, 400)], fill=255, width=7)
    for x in (170, 330):
        dd.line([(x, 360), (x, 400)], fill=255, width=7)
    for x in (250, 410):
        dd.line([(x, 400), (x, 440)], fill=255, width=7)
    return finish(m, det, face=BONE_FACE)


def siege_stance():
    m, d = new()
    # tower shield planted with a spike
    shield = [(130, 80), (382, 80), (382, 300)] + bez((382, 300), (382, 400), (256, 450)) + bez((256, 450), (130, 400), (130, 300))[1:]
    d.polygon(shield, fill=255)
    cut, c = new()
    c.polygon([(256, 130), (300, 250), (256, 380), (212, 250)], fill=255)
    d2 = ImageDraw.Draw(m)
    m = ImageChops.subtract(m, cut)
    d2 = ImageDraw.Draw(m)
    d2.polygon([(256, 170), (282, 250), (256, 330), (230, 250)], fill=255)
    # ground stakes
    for x in (100, 412):
        d2.polygon([(x - 14, 300), (x + 14, 300), (x, 470)], fill=255)
    return finish(m, face=BONE_FACE)


def mountainfall():
    m, d = new()
    d.polygon([(40, 450), (200, 170), (260, 250), (320, 150), (472, 450)], fill=255)
    d.polygon(anvil_pts(260, 88, 110), fill=255)
    det, dd = new()
    dd.line([(200, 170), (230, 300), (190, 380)], fill=255, width=8)
    dd.line([(320, 150), (345, 280), (390, 360)], fill=255, width=8)
    return finish(m, det, face=GOLD_FACE, glow='#FFB347')


def armor_passive():
    m, d = new()
    for i, y in enumerate((120, 230, 340)):
        w = 330 - i * 60
        d.polygon([(256 - w / 2, y), (256 + w / 2, y), (256 + w / 2 - 25, y + 85), (256 - w / 2 + 25, y + 85)], fill=255)
    return finish(m, face=STEEL_FACE)


# ───────────────────────── Selene / Kael (ally kits, for completeness) ─────────────────────────
def arc_nova():
    m, d = new()
    ring(d, 256, 256, 170, 40)
    for a in range(0, 360, 60):
        pts = bolt_pts(256 + 150 * math.cos(math.radians(a)), 256 + 150 * math.sin(math.radians(a)), 60)
        d.polygon(rot(pts, 256 + 150 * math.cos(math.radians(a)), 256 + 150 * math.sin(math.radians(a)), a + 90), fill=255)
    circ(d, 256, 256, 60)
    return finish(m, face=tone('#8FEAFF', 0.6, 0.5))


def fan_blades():
    m, d = new()
    for a in (-35, 0, 35):
        pts = [(256, 440), (236, 200), (256, 60), (276, 200)]
        d.polygon(rot(pts, 256, 440, a), fill=255)
    return finish(m, face=BONE_FACE)


# ───────────────────────── overdrive / aim ─────────────────────────
def overdrive():
    m, d = new()
    d.polygon(star(256, 256, 230, 70, 4, -90), fill=255)
    d.polygon(star(256, 256, 150, 60, 4, -45), fill=255)
    cut, c = new()
    circ(c, 256, 256, 58)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    circ(d, 256, 256, 34)
    return finish(m, face=GOLD_FACE, glow='#FFC940')


def aim_auto():
    m, d = new()
    ring(d, 256, 256, 150, 34)
    for a in (0, 90, 180, 270):
        d.polygon(rot([(240, 60), (272, 60), (256, 150)], 256, 256, a), fill=255)
    circ(d, 256, 256, 30)
    # orbit arrow
    d.arc([60, 60, 452, 452], 200, 330, fill=255, width=26)
    d.polygon([(420, 150), (470, 120), (440, 205)], fill=255)
    return finish(m, face=BONE_FACE)


def aim_assisted():
    m, d = new()
    ring(d, 256, 256, 150, 34)
    circ(d, 256, 256, 30)
    d.polygon([(256, 256), (470, 150), (470, 362)], fill=255)
    cut, c = new()
    c.polygon([(290, 256), (440, 185), (440, 327)], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=BONE_FACE)


def aim_manual():
    m, d = new()
    for a in (0, 90, 180, 270):
        d.polygon(rot([(238, 40), (274, 40), (266, 200), (246, 200)], 256, 256, a), fill=255)
    circ(d, 256, 256, 26)
    return finish(m, face=BONE_FACE)


# ───────────────────────── parts ─────────────────────────
def core(color, inner):
    def f():
        m, d = new()
        circ(d, 256, 256, 190)
        cut, c = new()
        circ(c, 256, 256, 130)
        m = ImageChops.subtract(m, cut)
        d = ImageDraw.Draw(m)
        inner(d)
        return finish(m, face=tone(color, 0.55, 0.5))
    return f


stormcore = core('#3FD8FF', lambda d: d.polygon(bolt_pts(262, 256, 110), fill=255))
embercore = core('#FF7A1A', lambda d: flame3(d, 256, 262, 150, 220))
ironcore = core('#F4E3C1', lambda d: d.polygon([(256, 150), (310, 230), (310, 360), (202, 360), (202, 230)], fill=255))
dawncore = core('#FFE27A', lambda d: d.polygon(star(256, 256, 120, 45, 6), fill=255))
voidcore = core('#A45CFF', lambda d: (circ(d, 256, 256, 90), d.ellipse([200, 200, 312, 312], fill=0), circ(d, 256, 256, 28)))


def ricochet():
    m, d = new()
    pts = [(70, 120), (220, 380), (330, 170), (440, 330)]
    d.line(pts, fill=255, width=40, joint='curve')
    d.polygon([(470, 380), (400, 330), (455, 280)], fill=255)
    for p in pts[1:3]:
        circ(d, p[0], p[1], 34)
    return finish(m, face=BONE_FACE)


def bounce_fork():
    m, d = new()
    d.line([(60, 400), (250, 250)], fill=255, width=42)
    circ(d, 250, 250, 42)
    d.line([(250, 250), (400, 110)], fill=255, width=34)
    d.line([(250, 250), (430, 300)], fill=255, width=34)
    d.polygon([(450, 70), (360, 110), (420, 170)], fill=255)
    d.polygon([(480, 315), (400, 350), (410, 260)], fill=255)
    return finish(m, face=BONE_FACE)


def multishot():
    m, d = new()
    for a in (-22, 0, 22):
        pts = [(246, 440), (266, 440), (266, 150), (300, 150), (256, 60), (212, 150), (246, 150)]
        d.polygon(rot(pts, 256, 440, a), fill=255)
    return finish(m, face=BONE_FACE)


def splitspawn():
    m, d = new()
    d.polygon([(150, 440), (362, 440), (320, 330), (192, 330)], fill=255)
    circ(d, 256, 280, 90)
    d.polygon(rrect(350, 200, 200, 50, -30), fill=255)
    d.polygon(star(120, 150, 70, 22, 4), fill=255)
    return finish(m, face=BONE_FACE)


def nyctian_eye():
    m, d = new()
    d.polygon(bez((40, 256), (256, 60), (472, 256)) + bez((472, 256), (256, 452), (40, 256))[1:], fill=255)
    cut, c = new()
    circ(c, 256, 256, 110)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon([(256, 160), (290, 256), (256, 352), (222, 256)], fill=255)
    return finish(m, face=tone('#D2B8FF', 0.5, 0.55))


def vampire():
    m, d = new()
    d.polygon(flame_pts(256, 290, 260, 380), fill=255)
    cut, c = new()
    c.polygon([(180, 260), (220, 260), (200, 360)], fill=255)
    c.polygon([(292, 260), (332, 260), (312, 360)], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#E0485A', 0.4, 0.5))


def sigil_anvilheart():
    m, d = new()
    d.polygon([(256, 460)] + bez((256, 460), (40, 300), (80, 150)) + bez((80, 150), (160, 40), (256, 140))[1:] +
              bez((256, 140), (352, 40), (432, 150))[1:] + bez((432, 150), (472, 300), (256, 460))[1:], fill=255)
    cut, c = new()
    c.polygon(anvil_pts(256, 270, 120), fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=GOLD_FACE)


def colossus_cannon():
    m, d = new()
    d.polygon(rot([(60, 210), (400, 190), (440, 170), (470, 175), (470, 300), (440, 305), (400, 285), (60, 300)], 256, 256, -18), fill=255)
    circ(d, 170, 330, 80)
    d.polygon([(100, 450), (250, 450), (230, 380), (120, 380)], fill=255)
    det, dd = new()
    for x in (180, 280):
        dd.line(rot([(x, 195), (x, 300)], 256, 256, -18), fill=255, width=10)
    circ(dd, 170, 330, 30)
    return finish(m, det, face=BONE_FACE)


# ───────────────────────── elements ─────────────────────────
def el_kinetic():
    m, d = new()
    d.polygon(star(256, 256, 220, 70, 8, -90), fill=255)
    return finish(m, face=tone('#F4E3C1', 0.5, 0.5))


def el_flame():
    m, d = new()
    flame3(d, 256, 262, 330, 440)
    cut, c = new()
    c.polygon(flame_pts(262, 350, 120, 190, -0.12), fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#FF7A1A', 0.55, 0.45))


def el_storm():
    m, d = new()
    d.polygon(bolt_pts(256, 256, 230), fill=255)
    return finish(m, face=tone('#3FD8FF', 0.6, 0.5))


def el_void():
    m, d = new()
    ring(d, 256, 256, 200, 46)
    circ(d, 256, 256, 80)
    d.arc([90, 90, 422, 422], 20, 150, fill=255, width=30)
    return finish(m, face=tone('#A45CFF', 0.5, 0.5))


def el_plague():
    m, d = new()
    d.polygon(flame_pts(256, 290, 300, 400), fill=255)
    cut, c = new()
    for (x, y, r) in [(220, 300, 34), (300, 340, 26), (280, 250, 20)]:
        circ(c, x, y, r)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#86E03A', 0.5, 0.5))


def el_radiant():
    m, d = new()
    d.polygon(star(256, 256, 230, 120, 12), fill=255)
    cut, c = new()
    circ(c, 256, 256, 96)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    circ(d, 256, 256, 66)
    return finish(m, face=tone('#FFE27A', 0.5, 0.45))


# ───────────────────────── currencies ─────────────────────────
def godshard():
    m, d = new()
    d.polygon([(256, 30), (360, 200), (310, 480), (200, 480), (150, 200)], fill=255)
    det, dd = new()
    dd.line([(256, 30), (256, 480)], fill=255, width=8)
    dd.line([(150, 200), (256, 250), (360, 200)], fill=255, width=8)
    return finish(m, det, face=('#FFF6DA', '#F7C957', '#B0701E'), glow='#FFC94066')


def ember():
    m, d = new()
    d.polygon([(150, 150), (330, 90), (440, 200), (430, 380), (300, 460), (120, 420), (70, 260)], fill=255)
    det, dd = new()
    dd.line([(170, 190), (250, 260), (230, 360), (300, 420)], fill=255, width=14)
    dd.line([(250, 260), (380, 220)], fill=255, width=12)
    return finish(m, det, face=('#FFD9A8', '#F07A34', '#6E1A0E'), ink='#1A0805', glow='#FF7A2A55')


def seal():
    m, d = new()
    pts = []
    for i in range(36):
        a = math.radians(i * 10)
        r = 215 if i % 2 == 0 else 195
        pts.append((256 + r * math.cos(a), 256 + r * math.sin(a)))
    d.polygon(pts, fill=255)
    det, dd = new()
    ring(dd, 256, 256, 150, 10)
    dd.polygon(anvil_pts(256, 262, 105), fill=255)
    return finish(m, det, face=GOLD_FACE)


# ───────────────────────── POIs ─────────────────────────
def poi_anvil():
    m, d = new()
    d.polygon(anvil_pts(256, 300, 230), fill=255)
    flame3(d, 256, 110, 170, 170)
    return finish(m)


def poi_warlord():
    m, d = new()
    # horned helm
    d.polygon(bez((110, 300), (110, 120), (256, 110)) + bez((256, 110), (402, 120), (402, 300))[1:] +
              [(402, 420), (320, 460), (256, 400), (192, 460), (110, 420)], fill=255)
    d.polygon(bez((130, 200), (20, 150), (60, 30)) + bez((60, 30), (90, 150), (180, 170))[1:], fill=255)
    d.polygon(bez((382, 200), (492, 150), (452, 30)) + bez((452, 30), (422, 150), (332, 170))[1:], fill=255)
    cut, c = new()
    c.polygon([(160, 270), (240, 280), (240, 320), (170, 310)], fill=255)
    c.polygon([(352, 270), (272, 280), (272, 320), (342, 310)], fill=255)
    c.rectangle([248, 250, 264, 400], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#FF6A55', 0.45, 0.5))


def poi_lair():
    m, d = new()
    circ(d, 256, 220, 150)
    d.rectangle([170, 300, 342, 420], fill=255)
    cut, c = new()
    circ(c, 200, 230, 45)
    circ(c, 312, 230, 45)
    c.polygon([(256, 280), (280, 330), (232, 330)], fill=255)
    for x in (200, 240, 280, 320):
        c.rectangle([x - 8, 370, x + 8, 420], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#E8A070', 0.5, 0.5))


def poi_shrine():
    m, d = new()
    d.polygon([(186, 470), (326, 470), (300, 230), (256, 196), (212, 230)], fill=255)
    d.rectangle([140, 440, 372, 482], fill=255)
    d.rectangle([168, 408, 344, 440], fill=255)
    flame3(d, 256, 110, 150, 190)
    det, dd = new()
    dd.line([(256, 250), (256, 400)], fill=255, width=10)
    return finish(m, det)


def poi_reliquary():
    m, d = new()
    d.polygon([(90, 220)] + bez((90, 220), (256, 60), (422, 220))[1:] + [(422, 440), (90, 440)], fill=255)
    det, dd = new()
    dd.line([(90, 250), (422, 250)], fill=255, width=12)
    dd.rectangle([230, 230, 282, 310], fill=255)
    for x in (150, 362):
        dd.line([(x, 150), (x, 440)], fill=255, width=10)
    return finish(m, det, face=tone('#D5B0FF', 0.5, 0.55))


def poi_vein():
    m, d = new()
    for (x, h, w, a) in [(256, 400, 110, 0), (160, 280, 90, -20), (350, 300, 90, 18), (95, 170, 60, -30), (420, 180, 60, 28)]:
        pts = [(x, 470 - h), (x + w / 2, 470 - h + w * 0.6), (x + w / 2, 470), (x - w / 2, 470), (x - w / 2, 470 - h + w * 0.6)]
        d.polygon(rot(pts, x, 470, a), fill=255)
    return finish(m, face=tone('#8FF7FF', 0.55, 0.5))


def poi_spring():
    m, d = new()
    d.polygon(flame_pts(256, 200, 200, 300), fill=255)
    d.chord([80, 300, 432, 480], 0, 180, fill=255)
    cut, c = new()
    c.arc([150, 330, 362, 440], 20, 160, fill=255, width=16)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#FF8FA3', 0.5, 0.5))


def poi_watchfire():
    m, d = new()
    for a in (-20, 20):
        d.polygon(rot([(238, 490), (274, 490), (274, 250), (238, 250)], 256, 490, a), fill=255)
    d.polygon([(110, 250), (402, 250), (360, 300), (152, 300)], fill=255)
    flame3(d, 256, 140, 250, 250)
    return finish(m)


def poi_gate():
    m, d = new()
    d.polygon([(60, 480), (60, 230)] + bez((60, 230), (60, 40), (256, 40))[1:] + bez((256, 40), (452, 40), (452, 230))[1:] +
              [(452, 480)], fill=255)
    cut, c = new()
    c.polygon([(140, 480), (140, 250)] + bez((140, 250), (140, 120), (256, 120))[1:] + bez((256, 120), (372, 120), (372, 250))[1:] +
              [(372, 480)], fill=255)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon([(256, 190), (300, 280), (256, 370), (212, 280)], fill=255)
    return finish(m)


# ───────────────────────── misc ─────────────────────────
def lock():
    m, d = new()
    d.rounded_rectangle([110, 220, 402, 470], 40, fill=255)
    d.arc([150, 50, 362, 330], 180, 360, fill=255, width=50)
    d.rectangle([150, 180, 200, 230], fill=255)
    d.rectangle([312, 180, 362, 230], fill=255)
    cut, c = new()
    circ(c, 256, 320, 35)
    c.rectangle([244, 330, 268, 400], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=STEEL_FACE)


def dice():
    m, d = new()
    d.polygon([(256, 50), (450, 150), (450, 370), (256, 470), (62, 370), (62, 150)], fill=255)
    det, dd = new()
    dd.line([(62, 150), (256, 250), (450, 150)], fill=255, width=10)
    dd.line([(256, 250), (256, 470)], fill=255, width=10)
    for (x, y) in [(256, 150), (160, 300), (200, 380), (350, 290), (310, 380)]:
        circ(dd, x, y, 22)
    return finish(m, det, face=BONE_FACE)


def hammer():
    m, d = new()
    d.polygon(rrect(310, 170, 290, 150, 38), fill=255)
    d.polygon(rrect(190, 340, 62, 300, 38), fill=255)
    det, dd = new()
    dd.line(rot([(240, 170), (380, 170)], 310, 170, 38), fill=255, width=10)
    return finish(m, det, face=GOLD_FACE)


def fuse():
    m, d = new()
    d.polygon(rot([(150, 80), (230, 160), (150, 240), (70, 160)], 150, 160, 0), fill=255)
    d.polygon([(362, 80), (442, 160), (362, 240), (282, 160)], fill=255)
    d.polygon([(256, 250), (360, 360), (256, 470), (152, 360)], fill=255)
    d.line([(150, 240), (230, 320)], fill=255, width=22)
    d.line([(362, 240), (282, 320)], fill=255, width=22)
    return finish(m, face=GOLD_FACE)


def salvage():
    m, d = new()
    d.polygon([(200, 60), (300, 200), (230, 470), (120, 470), (90, 220)], fill=255)
    d.polygon([(330, 170), (430, 300), (380, 470), (280, 470), (300, 280)], fill=255)
    return finish(m, face=('#FFF6DA', '#F7C957', '#B0701E'))


def skull():
    m, d = new()
    circ(d, 256, 220, 170)
    d.rectangle([170, 300, 342, 440], fill=255)
    cut, c = new()
    circ(c, 195, 230, 50)
    circ(c, 317, 230, 50)
    c.polygon([(256, 290), (282, 350), (230, 350)], fill=255)
    for x in (205, 256, 307):
        c.rectangle([x - 10, 390, x + 10, 440], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=BONE_FACE)


def check():
    m, d = new()
    d.line([(90, 270), (210, 390), (430, 130)], fill=255, width=70, joint='curve')
    return finish(m, face=GOLD_FACE)


def threat():
    m, d = new()
    d.polygon([(256, 40), (470, 250), (390, 250), (256, 118), (122, 250), (42, 250)], fill=255)
    d.polygon([(256, 200), (470, 410), (390, 410), (256, 278), (122, 410), (42, 410)], fill=255)
    return finish(m, face=('#FFD9A0', '#F06A2A', '#7A1810'))


def hourglass():
    m, d = new()
    d.rectangle([120, 50, 392, 90], fill=255)
    d.rectangle([120, 422, 392, 462], fill=255)
    d.polygon([(150, 90), (362, 90), (270, 256), (362, 422), (150, 422), (242, 256)], fill=255)
    cut, c = new()
    c.polygon([(190, 115), (322, 115), (256, 225)], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=BONE_FACE)


def tether():
    m, d = new()
    d.polygon(flame_pts(256, 280, 250, 380), fill=255)
    cut, c = new()
    c.rectangle([232, 200, 280, 400], fill=255)
    c.rectangle([176, 256, 336, 304], fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#FFE27A', 0.5, 0.5))


# ───────────────────────── gods (sigils) and boons ─────────────────────────
def god_pyra():
    m, d = new()
    flame3(d, 256, 250, 340, 420)
    cut, c = new()
    flame3(c, 256, 330, 170, 230)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon(flame_pts(256, 372, 70, 120, 0.1), fill=255)
    d.polygon([(150, 470), (362, 470), (330, 430), (182, 430)], fill=255)
    return finish(m, face=('#FFE6B0', '#FF8A3A', '#8E1B12'))


def god_zephyros():
    m, d = new()
    for i, r in enumerate((190, 130, 70)):
        d.arc([256 - r, 256 - r, 256 + r, 256 + r], 150 + i * 40, 420 + i * 40, fill=255, width=34)
    d.polygon(bolt_pts(256, 256, 70), fill=255)
    return finish(m, face=tone('#3FD8FF', 0.6, 0.5))


def god_nyctia():
    m, d = new()
    circ(d, 256, 256, 200)
    cut, c = new()
    circ(c, 330, 210, 170)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon(star(330, 250, 70, 18, 4), fill=255)
    return finish(m, face=tone('#A67BFF', 0.5, 0.55))


def boon_blastfire():
    m, d = new()
    d.polygon(star(256, 256, 230, 110, 10), fill=255)
    cut, c = new()
    c.polygon(star(256, 256, 120, 60, 10, -72), fill=255)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    circ(d, 256, 256, 50)
    return finish(m, face=('#FFE6B0', '#FF8A3A', '#8E1B12'))


def boon_leaping_arc():
    m, d = new()
    pts = [(60, 380), (170, 150), (270, 330), (360, 120), (450, 280)]
    d.line(pts, fill=255, width=34, joint='curve')
    for p in pts:
        circ(d, p[0], p[1], 40)
    return finish(m, face=tone('#3FD8FF', 0.6, 0.5))


def boon_quietus():
    m, d = new()
    d.polygon([(256, 30), (300, 330), (256, 380), (212, 330)], fill=255)
    d.rectangle([140, 330, 372, 370], fill=255)
    d.rectangle([236, 370, 276, 470], fill=255)
    d.polygon(star(256, 200, 26, 8, 4), fill=0)
    return finish(m, face=tone('#B68CFF', 0.5, 0.55))


def boon_team_forge():
    m, d = new()
    d.polygon(anvil_pts(256, 300, 200), fill=255)
    for a in (-60, -20, 20, 60):
        x = 256 + 200 * math.sin(math.radians(a)); y = 250 - 170 * math.cos(math.radians(a))
        circ(d, x, y, 34)
    return finish(m)


def doomstack():
    m, d = new()
    for i, y in enumerate((400, 320, 240)):
        w = 330 - i * 50
        d.ellipse([256 - w / 2, y - 45, 256 + w / 2, y + 45], fill=255)
    d.polygon(star(256, 110, 95, 28, 4), fill=255)
    det, dd = new()
    for i, y in enumerate((400, 320, 240)):
        w = 330 - i * 50
        dd.arc([256 - w / 2, y - 45, 256 + w / 2, y + 45], 0, 180, fill=255, width=9)
    return finish(m, det, face=tone('#C9A2FF', 0.5, 0.55))


def volatile_heart():
    m, d = new()
    d.polygon([(256, 440)] + bez((256, 440), (70, 300), (100, 180)) + bez((100, 180), (170, 90), (256, 170))[1:] +
              bez((256, 170), (342, 90), (412, 180))[1:] + bez((412, 180), (442, 300), (256, 440))[1:], fill=255)
    for a in range(0, 360, 45):
        pts = rot([(246, 30), (266, 30), (256, 90)], 256, 256, a)
        d.polygon(pts, fill=255)
    cut, c = new()
    c.polygon(star(256, 270, 80, 30, 5), fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#FF8A5A', 0.45, 0.5))


def sort_icon():
    m, d = new()
    for i, w in enumerate((360, 270, 180)):
        d.rounded_rectangle([76, 110 + i * 110, 76 + w, 170 + i * 110], 20, fill=255)
    return finish(m, face=BONE_FACE)


def boon_stormbrand():
    m, d = new()
    # a blade with a bolt branded along it
    d.polygon([(256, 30), (300, 110), (300, 360), (212, 360), (212, 110)], fill=255)
    d.rectangle([150, 360, 362, 400], fill=255)
    d.rectangle([232, 400, 280, 480], fill=255)
    cut, c = new()
    c.polygon(bolt_pts(256, 220, 105), fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#9FEFFF', 0.55, 0.5))


def boon_silent_thunder():
    m, d = new()
    circ(d, 250, 256, 200)
    cut, c = new()
    circ(c, 330, 205, 170)
    m = ImageChops.subtract(m, cut)
    d = ImageDraw.Draw(m)
    d.polygon(bolt_pts(318, 290, 125), fill=255)
    d.polygon(star(380, 120, 55, 14, 4), fill=255)
    return finish(m, face=tone('#B7C8FF', 0.55, 0.55))


def reroll_dice():
    return dice()


def st_shock():
    m, d = new()
    circ(d, 256, 256, 210)
    cut, c = new()
    c.polygon(bolt_pts(256, 256, 150), fill=255)
    m = ImageChops.subtract(m, cut)
    return finish(m, face=tone('#3FD8FF', 0.55, 0.5))



ALL = {k: v for k, v in dict(globals()).items() if callable(v) and v.__module__ == __name__ and not k.startswith('_')
       and k not in ('new', 'bez', 'circ', 'ring', 'rot', 'rrect', 'star', 'flame_pts', 'flame3', 'bolt_pts', 'anvil_pts',
                     'finish', 'tone', 'core', 'get', 'grad_img', 'rgba', 'mix', 'mask_mul', 'solid', 'grow', 'shrink')}

_cache = {}


def get(name):
    if name not in _cache:
        _cache[name] = ALL[name]()
    return _cache[name]
