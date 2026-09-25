"""Before / after sheet for the cinderling art-review fix (plain Python + PIL + numpy; no Blender).

    python tools/blender/gf_assets/enemies/cinderling_fix_sheet.py BEFORE_DIR
        -> art/enemies/cinderling/reports/cinderling_review_fix.png

The review (7.5/10) had one must-fix: in the wind-up, 7 % of the pixels sat within dE 20 of the player gold
#FFC940 - the throat ramp dwelt in the #FFC24B band, a gold ring round the white-hot core. BEFORE_DIR holds
the pre-fix build (commit 0b0e701): <key>/<key>_pose_<pose>_ingame_22.png (the 72 px game-camera crops that
cinderling.py writes to work/<key>/) and <key>_emissive.png / <key>_basecolor.png (the textures). AFTER comes
from the current art/enemies/cinderling/work/<key>/ and textures/. Same build script, cameras and crops.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
PACK = os.path.join(ROOT, "art", "enemies", "cinderling")
LOOKS = [("cinderling", "Grinning coal"), ("cinderling_v1", "Split-crown"), ("cinderling_v2", "Heavy-brow")]
PLAYER_GOLD = (0xFF, 0xC9, 0x40)
MARK = (255, 0, 255)                      # the gold-band mask (a review colour, not an asset colour)
BG, PANEL, INK, SUB, HEAD = (30, 27, 33), (46, 42, 50), (236, 230, 220), (170, 162, 150), (240, 200, 170)
FLOOR = (0x3A, 0x2C, 0x24)

FIX = [
    "Throat ramp: the old core -> hot blend ran in sRGB over half the ramp radius, and the throat floor never reached",
    "the peach core (texture max #FFA364). Under the x1.6 emission gain plus the toon key light that orange clipped",
    "to a ring of player gold. Now a pool of white-hot peach (#FFF3D6 -> #FFD9B0) sits on the throat floor of each",
    "look and steps STRAIGHT to the hot orange #FF6B1A in about 1.5 cm, blended in linear light (gfa_paint emit",
    "'stops'). The painted base under the orange bowl is half value, so the key light no longer washes the lit orange",
    "to gold; the ember-red ring the rest pose shows is unchanged. The 1x rest pose differs by a handful of pixels",
    "(the rest gap shows the deep core white, not yellow); the glow share is kept (within 0.3 points).",
]


def font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def lab(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


GOLD_LAB = lab(np.array(PLAYER_GOLD, dtype=np.float64))


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def creature(a):
    """The creature's pixels in a game-camera crop (everything that is not the flat floor)."""
    return np.abs(a - np.array(FLOOR)).sum(-1) > 12


def gold_share(a):
    m = creature(a)
    de = np.linalg.norm(lab(a) - GOLD_LAB, axis=-1)
    return 100.0 * (de[m] < 20).mean(), de < 20


def up(im, s):
    return im.resize((im.width * s, im.height * s), Image.NEAREST)


def masked(a, mask):
    b = a.copy()
    b[mask & creature(a)] = MARK
    return Image.fromarray(b.astype(np.uint8))


def path_chips(a, n=14):
    """The rendered colours from the throat's orange out to the hottest pixel (a horizontal run through it)."""
    s = a.sum(-1)
    y, x = np.unravel_index(s.argmax(), s.shape)
    run = [a[y, xx] for xx in range(max(0, x - n + 1), x + 1)]
    return run


def tex_crop(path, box_c, r=40, s=3):
    im = Image.open(path).convert("RGB")
    x, y = box_c
    return up(im.crop((x - r, y - r, x + r, y + r)), s)


def hottest(path):
    a = load(path)
    s = a.sum(-1)
    y, x = np.unravel_index(s.argmax(), s.shape)
    return int(x), int(y)


def main():
    before = sys.argv[1] if len(sys.argv) > 1 else "."
    work = os.path.join(PACK, "work")
    tex = os.path.join(PACK, "textures")
    pad, W = 16, 1560
    S = 4
    tile = 72 * S
    rows = []
    for key, name in LOOKS:
        f = "%s_pose_windup_loaded_ingame_22.png" % key
        rows.append((key, name, "windup (loaded)", load(os.path.join(before, key, f)), load(os.path.join(work, key, f))))
    hits = []
    for key, name in LOOKS:
        f = "%s_pose_hit_ingame_22.png" % key
        hits.append((key, name, load(os.path.join(before, key, f)), load(os.path.join(work, key, f))))

    title_h, fix_h = 78, 22 * len(FIX) + 16
    row_h = 30 + tile + 30
    hit_h = 34 + 72 * 3 + 30
    chip_h = 40 + 2 * 64
    tex_h = 40 + 108 + 30
    H = title_h + fix_h + 36 + len(rows) * (row_h + pad) + hit_h + pad + chip_h + pad + tex_h + pad
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 12), "Cinderling - art review fix (7.5/10): no gold ring round the white-hot throat",
           font=font(26, True), fill=HEAD)
    d.text((pad, 48), "same build script, game camera (55 deg, 49 px/m, TRUE 72 px crops shown %dx nearest); before = "
                      "0b0e701, after = this fix. Magenta = pixels within dE 20 (CIE76) of the player gold #FFC940"
           % S, font=font(14), fill=SUB)
    y = title_h
    for line in FIX:
        d.text((pad, y), line, font=font(15), fill=INK)
        y += 22
    y += 16
    cols = [pad + 170 + k * (tile + 14) for k in range(4)]
    for k, lb in enumerate(("BEFORE", "BEFORE: gold band", "AFTER", "AFTER: gold band")):
        d.text((cols[k], y), lb, font=font(18, True), fill=HEAD if k >= 2 else SUB)
    y += 36
    for key, name, pose, b, a in rows:
        gb, mb = gold_share(b)
        ga, ma = gold_share(a)
        d.rectangle((pad, y, W - pad, y + row_h - 1), fill=PANEL)
        d.text((pad + 10, y + 10), name, font=font(17, True), fill=INK)
        d.text((pad + 10, y + 34), "%s.glb" % key, font=font(13), fill=SUB)
        d.text((pad + 10, y + 54), pose, font=font(13), fill=SUB)
        d.text((pad + 10, y + 90), "gold pixels", font=font(13), fill=SUB)
        d.text((pad + 10, y + 108), "%.1f %% -> %.1f %%" % (gb, ga), font=font(17, True), fill=INK)
        ims = [up(Image.fromarray(b.astype(np.uint8)), S), up(masked(b, mb), S),
               up(Image.fromarray(a.astype(np.uint8)), S), up(masked(a, ma), S)]
        for k, im in enumerate(ims):
            sheet.paste(im, (cols[k], y + 30))
        d.text((pad + 10, y + 30 + tile - 100), "TRUE size 1x: before | after", font=font(12), fill=SUB)
        sheet.paste(Image.fromarray(b.astype(np.uint8)), (pad + 10, y + 30 + tile - 78))
        sheet.paste(Image.fromarray(a.astype(np.uint8)), (pad + 10 + 80, y + 30 + tile - 78))
        y += row_h + pad
    # hit poses (the lid pops open over the throat), before | after per look, 3x
    d.rectangle((pad, y, W - pad, y + hit_h - 1), fill=PANEL)
    d.text((pad + 10, y + 8), "hit pose (the lid pops open over the throat), before | after, 3x nearest",
           font=font(15, True), fill=INK)
    x = pad + 10
    for key, name, b, a in hits:
        gb, _ = gold_share(b)
        ga, _ = gold_share(a)
        for k, im in enumerate((b, a)):
            sheet.paste(up(Image.fromarray(im.astype(np.uint8)), 3), (x + k * (216 + 6), y + 34))
        d.text((x, y + 34 + 216 + 6), "%s: gold %.1f %% -> %.1f %%" % (name, gb, ga), font=font(13), fill=SUB)
        x += 2 * 216 + 6 + 40
    y += hit_h + pad
    # the rendered colour run from the orange throat to the hottest pixel (base look, wind-up loaded)
    d.text((pad, y + 8), "rendered colours from the throat's orange to the core (Grinning coal, wind-up, 1x pixels; "
                         "dE to #FFC940 under each chip; < 20 = the gold band)", font=font(15, True), fill=INK)
    y += 40
    for lb, arr in (("before", rows[0][3]), ("after", rows[0][4])):
        d.text((pad, y + 20), lb, font=font(15, True), fill=HEAD if lb == "after" else SUB)
        for i, c in enumerate(path_chips(arr)):
            x0 = pad + 80 + i * 96
            col = tuple(int(v) for v in c)
            de = float(np.linalg.norm(lab(np.array(col, dtype=np.float64)) - GOLD_LAB))
            d.rectangle((x0, y, x0 + 88, y + 34), fill=col)
            if de < 20:
                d.rectangle((x0 - 2, y - 2, x0 + 90, y + 36), outline=MARK, width=2)
            d.text((x0, y + 38), "#%02X%02X%02X %2.0f" % (col + (de,)), font=font(11), fill=SUB)
        y += 64
    y += pad
    # the painted throat, emissive and base colour, before | after
    d.text((pad, y + 8), "the painted throat (textures around the hottest texel, 3x): emissive before | after, "
                         "base colour before | after (half value under the orange bowl)", font=font(15, True), fill=INK)
    y += 40
    x = pad
    r, s = 18, 3
    t = 2 * r * s
    for key, name in LOOKS:
        x_look = x
        eb = os.path.join(before, "%s_emissive.png" % key)
        ea = os.path.join(tex, "%s_emissive.png" % key)
        for kind in ("emissive", "basecolor"):
            for src, hot_src in ((os.path.join(before, "%s_%s.png" % (key, kind)), eb),
                                 (os.path.join(tex, "%s_%s.png" % (key, kind)), ea)):
                sheet.paste(tex_crop(src, hottest(hot_src), r=r, s=s), (x, y))
                x += t + 4
            x += 8
        d.text((x_look, y + t + 6), "%s: emissive b | a, base b | a" % name, font=font(12), fill=SUB)
        x += 28
    out = os.path.join(PACK, "reports", "cinderling_review_fix.png")
    sheet.save(out, optimize=True)
    print(out, sheet.size, "%.2f MB" % (os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
