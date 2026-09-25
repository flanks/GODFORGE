"""Stage 0: does the approved concept survive game scale? A 2D readability sheet.

  <comfy-python> tools/comfy/readability_sheet.py <key> <concept.png> [--height-m 2.2] [--out PNG]

<comfy-python> = D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe (PIL + numpy).

Cuts the figure out of the flat-background concept and shows it at the size a hero occupies in
game (6 % and 8 % of a 1080p frame = 65 / 86 px tall), in colour, as perceptual value (L*) and as
a flat silhouette; on each biome's ground colour (biomes.ron, unlit albedo tint = worst case);
and pasted into a real client frame (docs/media/doors.jpg) beside the current greybox hero, scaled
by in-game height (greybox ~2.0 u = 69 px there).

This is a 2D APPROXIMATION: a front T-pose plate pasted flat, not a render through the 55-degree
orthographic game camera (which shows the tops of the shoulders, head and gauntlets and shortens
the legs). The real in-camera check is the stage-1 blockout render. Default output:
art/characters/<key>/reports/stage0_readability.png
"""
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

import gf_img as G

FRAME = os.path.join(G.ROOT, "docs", "media", "doors.jpg")
FRAME_HERO_PX = 69          # greybox hero (capsule + head, top ~2.0 u) measured in doors.jpg: y 385..454
FRAME_HERO_M = 2.0
FRAME_FEET = (690, 454)     # an empty patch of floor left of the greybox (at x 795)
FRAME_CROP = (560, 300, 1040, 520)
FLOOR_PATCH = (300, 560, 520, 700)   # lit Cinder Wastes flagstone in doors.jpg


def biomes():
    try:
        src = open(os.path.join(G.ROOT, "assets", "content", "biomes.ron"), encoding="utf-8").read()
    except OSError:
        return []
    pat = re.compile(r'key:\s*"(\w+)",\s*name:\s*"([^"]+)".*?palette:\s*\("(#\w{6})",\s*"(#\w{6})",\s*"(#\w{6})"\)', re.S)
    return [m.groups() for m in pat.finditer(src)]


def variants(fig_rgba, height):
    """colour, value (L*) and flat-silhouette versions at `height` px."""
    col = G.fit_height(fig_rgba, height)
    a = np.asarray(col)
    gray = G.lstar_gray(a[..., :3])
    val = Image.fromarray(np.dstack([gray, gray, gray, a[..., 3]]), "RGBA")
    sil = Image.fromarray(np.dstack([np.full(a.shape[:2], 16, np.uint8)] * 3 + [a[..., 3]]), "RGBA")
    return col, val, sil


def on(bg_rgb, fg, pad=10, size=None):
    w, h = size or (fg.width + 2 * pad, fg.height + 2 * pad)
    tile = Image.new("RGB", (w, h), tuple(int(c) for c in bg_rgb))
    tile.paste(fg, ((w - fg.width) // 2, h - pad - fg.height), fg)
    return tile


def up(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    key, concept = argv[1], G.absp(argv[2])
    height_m = float(argv[argv.index("--height-m") + 1]) if "--height-m" in argv else 2.2
    out = G.absp(argv[argv.index("--out") + 1]) if "--out" in argv else \
        os.path.join(G.ROOT, "art", "characters", key, "reports", "stage0_readability.png")

    rgb = np.asarray(Image.open(concept).convert("RGB"))
    bg = G.background_rgb(rgb)
    mask = G.figure_mask(rgb, bg)
    fig = G.cutout(rgb, mask)
    frame = Image.open(FRAME).convert("RGB")
    floor = np.median(np.asarray(frame.crop(FLOOR_PATCH)).reshape(-1, 3), axis=0)
    grey = (104, 100, 96)

    W, H = 2400, 1420
    sheet, d = G.new_sheet(W, H)
    cream, dim = (236, 228, 210), (150, 146, 140)
    G.text(d, (40, 64), key.upper(), 50, True, (255, 150, 90), anchor="ls")
    G.text(d, (40 + G.text_w(key.upper(), 50, True) + 18, 64), "readability at game scale  -  stage 0, 2D approximation", 32, True, cream, anchor="ls")
    G.text(d, (40, 98), "The approved front plate cut out and shrunk to in-game size. NOT a render through the 55-degree ortho camera "
                        "(that view shows shoulder/head/gauntlet tops and shortens the legs); the in-camera check is the stage-1 blockout.",
           17, False, dim, anchor="ls")

    # 1. 1:1 at 6 % and 8 % of 1080p, plus 3x enlargements of the 8 % versions
    y0 = 150
    G.text(d, (40, y0), "1  At game size, 1:1 pixels on the lit Cinder Wastes floor (sampled from doors.jpg %s)" % G.rgb_to_hex(floor), 20, True, cream, anchor="ls")
    x = 40
    sets = {}
    for hpx, label in ((65, "6 % of 1080p = 65 px"), (86, "8 % of 1080p = 86 px")):
        sets[hpx] = variants(fig, hpx)
    for name, idx in (("colour", 0), ("value (L*)", 1), ("silhouette", 2)):
        for hpx in (65, 86):
            t = on(floor, sets[hpx][idx], pad=12, size=(130, 110))
            sheet.paste(t, (x, y0 + 20))
            G.text(d, (x + 65, y0 + 150), "%s %dpx" % (name, hpx), 13, False, dim, anchor="ms")
            x += 138
        x += 16
    xb = x + 20
    xb0 = xb
    for idx in range(3):
        t = up(on(floor, sets[86][idx], pad=8, size=(118, 104)), 3)
        sheet.paste(t, (xb, y0 + 20))
        xb += t.width + 12
    G.text(d, (xb0, y0 + 20 + t.height + 22), "the 86 px versions at 3x (nearest neighbour: every block is one screen pixel)", 14, False, dim, anchor="ls")

    # 2. on each biome ground
    y1 = y0 + 390
    G.text(d, (40, y1), "2  On each biome's ground colour at 8 % (86 px), shown 2x  -  biomes.ron albedo tint, unlit = worst case; the lit floor is lighter", 20, True, cream, anchor="ls")
    x = 40
    for bkey, name, ground, accent, fog in biomes():
        t = on(G.hex_to_rgb(ground), sets[86][0], pad=10, size=(190, 108))
        # a strip of the biome's glow accent under the tile, for hue competition
        tile = up(t, 2)
        sheet.paste(tile, (x, y1 + 18))
        d.rectangle([x, y1 + 18 + tile.height, x + tile.width, y1 + 18 + tile.height + 10], fill=G.hex_to_rgb(accent))
        G.text(d, (x, y1 + 18 + tile.height + 32), "%s  ground %s  glow %s" % (name, ground, accent), 14, False, dim, anchor="ls")
        x += tile.width + 24

    # 3. pasted into a real frame
    y2 = y1 + 320
    scale_px = round(FRAME_HERO_PX * height_m / FRAME_HERO_M)
    G.text(d, (40, y2), "3  Pasted into a client frame (docs/media/doors.jpg, 1600x900) left of the greybox hero: %.1f m -> %d px (greybox %.1f u = %d px)"
           % (height_m, scale_px, FRAME_HERO_M, FRAME_HERO_PX), 20, True, cream, anchor="ls")
    f2 = frame.copy()
    small = G.fit_height(fig, scale_px)
    fx, fy = FRAME_FEET
    f2.paste(small, (fx - small.width // 2, fy - small.height), small)
    crop = f2.crop(FRAME_CROP)
    sheet.paste(crop, (40, y2 + 20))
    G.text(d, (40, y2 + 20 + crop.height + 22), "1:1", 14, False, dim, anchor="ls")
    big = up(crop, 2)
    sheet.paste(big, (40 + crop.width + 30, y2 + 20))
    G.text(d, (40 + crop.width + 30, y2 + 20 + big.height + 22), "2x", 14, False, dim, anchor="ls")
    wx = 40 + crop.width + 30 + big.width + 30
    notes = ["Scale: in-game height %.1f m (roster range 2.0-2.3 m)." % height_m,
             "The front T-pose is wider than any gameplay pose;",
             "arms-down idle loses ~40 % of this width.",
             "Judgement and conclusions: brief.md,",
             "section 'Readability'."]
    for i, ln in enumerate(notes):
        G.text(d, (wx, y2 + 44 + i * 22), ln, 15, False, (200, 194, 184), anchor="ls")

    G.text(d, (40, H - 22), "generated by tools/comfy/readability_sheet.py from %s (sha256 %s...)" % (G.rel(concept), G.sha256(concept)[:16]),
           13, False, (120, 116, 110), anchor="ls")
    sheet.save(out, optimize=True)
    print("[readability] wrote", G.rel(out), "- figure bbox", mask.nonzero()[1].min(), mask.nonzero()[1].max(),
          mask.nonzero()[0].min(), mask.nonzero()[0].max(), "- frame paste", scale_px, "px")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
