"""Final board: anchored HUD regions at 1920x1080 (logical px, UiScale 1.0), over the HUD fight mockup."""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'
import os
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'assets', 'fonts') + '/'
base = Image.open(f'{OUT}/ui_hud_fight_1920.png').convert('RGB')
base = ImageEnhance.Color(base).enhance(0.35)
base = ImageEnhance.Brightness(base).enhance(0.45)
img = base.convert('RGBA')
ov = Image.new('RGBA', img.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)
cz = ImageFont.truetype(FONTS + 'Cinzel-Variable.ttf', 17)
try:
    cz.set_variation_by_axes([800])
except Exception:
    pass
bd = ImageFont.truetype(FONTS + 'AlegreyaSans-Medium.ttf', 15)
bb = ImageFont.truetype(FONTS + 'AlegreyaSans-Bold.ttf', 15)

GOLD = (242, 198, 103)
GREEN = (120, 220, 140)
CYAN = (140, 200, 230)
ROSE = (240, 150, 140)


def box(x0, y0, x1, y1, title, lines, col=GOLD, fill_a=38, tx=None, ty=None):
    d.rectangle([x0, y0, x1, y1], outline=col + (235,), width=2, fill=col + (fill_a,))
    tx = x0 + 8 if tx is None else tx
    ty = y0 + 6 if ty is None else ty
    d.text((tx, ty), title, font=cz, fill=col + (255,))
    for i, ln in enumerate(lines):
        d.text((tx, ty + 24 + i * 18), ln, font=bd, fill=(236, 226, 206, 255))


# safe margin
d.rectangle([24, 24, 1896, 1056], outline=(200, 190, 170, 120), width=1)
d.text((1700, 1060), 'safe margin 24 px (TV-safe 48)', font=bd, fill=(200, 190, 170, 230))
# edge pin band (40 px inset)
d.rectangle([40, 40, 1880, 1040], outline=CYAN + (110,), width=1)
d.text((48, 760), 'edge pins: centres 40 px in,', font=bd, fill=CYAN + (255,))
d.text((48, 778), 'slide along the edge off HudRects', font=bd, fill=CYAN + (255,))

# clear zones
d.ellipse([810, 430, 1110, 650], outline=GREEN + (230,), width=2, fill=GREEN + (24,))
d.text((838, 652), 'HERO ZONE 300×220 @ (960, 540)', font=bb, fill=GREEN + (255,))
d.text((850, 670), 'world-anchored transients only', font=bd, fill=GREEN + (255,))
box(700, 880, 1220, 1080, 'SOUTH LANE — always clear', ['x 700–1220 · y 880–1080', 'no persistent UI; prompts never here;',
                                                        'only damage numbers and edge pins'], col=GREEN, fill_a=26)
box(1750, 490, 1920, 730, 'E LANE', ['x 1750–1920', 'y 490–730', 'pins only'], col=GREEN, fill_a=22, tx=1756)
box(0, 490, 170, 730, 'W LANE', ['x 0–170', 'y 490–730', 'pins only'], col=GREEN, fill_a=22)

# persistent clusters
box(24, 24, 282, 190, 'PARTY', ['x 24–282 · y 24–190', '3 rows × 54 px, Ø46 medallion', 'P chip · name · HP 170×8'])
box(16, 196, 464, 292, 'TOAST RAIL', ['x 16–464 · y 196–292', '3 max, 32 px pitch, newest on top'], col=CYAN)
box(1616, 24, 1896, 200, 'MINIMAP (phase 3)', ['x 1616–1896 · y 24–200 · 280×176', 'Display::None until phase 3;',
                                               'tracker docks at y 24'])
box(1566, 218, 1896, 486, 'TRACKER', ['right-aligned at x 1896, no box; floor y 486', 'row pitch 28–38, corner pool 0.64',
                                      'header · Seals · Warlord/Gate ·', 'Threat · Surge · Events · Next 2'])
box(24, 878, 580, 1056, 'HEARTH (me)', ['x 24–580 · y 878–1056', 'medallion Ø128 @ (88, 980) = portrait + ult',
                                         'HP 360×22 @ (170, 928) · Q/E 60 · V hex 68'])
box(1550, 924, 1896, 1056, 'ARSENAL', ['x 1550–1896 · y 924–1056', 'chassis hex 100 @ (1846, 1006)', 'parts 52 @ 60 pitch · wallet'])
box(1566, 846, 1896, 918, 'BOON CHIP', ['x 1566–1896 · y 846–918 (transient)'], col=CYAN)

# top-centre transient bands
box(610, 24, 1310, 150, 'BOSS BAR (boss / Warlord only)', ['x 610–1310 · y 24–150 · bar 620×18 @ y 86'], col=ROSE, fill_a=22)
box(510, 104, 1410, 176, 'CALLOUT LANE', ['baseline y 150 (206 while the boss bar is up) · max 900 wide'], col=CYAN, fill_a=18,
    tx=1000, ty=110)
box(560, 180, 1360, 280, 'REGION BANNER', ['y 180–280 · name baseline 236 · 3.5 s · suppressed in boss fights'], col=CYAN,
    fill_a=14)
d.text((24, 4), 'DEBUG STRIP (F10 / --fps): y 4–20, pushes the party down 18 px', font=bd, fill=(200, 190, 170, 230))

img.alpha_composite(ov)
out = img.convert('RGB')
a = np.asarray(out)
q = ((a >> 2) << 2) | 2
Image.fromarray(q.astype(np.uint8)).save(f'{OUT}/ui_layout_regions_1920.png', optimize=True)
print('ok')
