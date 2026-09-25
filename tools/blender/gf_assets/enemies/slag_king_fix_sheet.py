"""Before / after sheet for the Slag King art-review fixes (plain Python + PIL; no Blender).

    python tools/blender/gf_assets/enemies/slag_king_fix_sheet.py BEFORE_DIR
        -> art/enemies/slag_king/reports/slag_king_review_fix.png

BEFORE_DIR holds the pre-fix renders: old_34.png (the committed reports/slag_king_34.png) and
old_ingame_p1_22.png (the pre-fix work/review/slag_king_ingame_p1_22.png, the 1x game-camera frame).
AFTER comes from the current art/enemies/slag_king/reports/slag_king_34.png and
work/review/slag_king_ingame_p1_22.png. Every crop is taken at the same box from both.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
PACK = os.path.join(ROOT, "art", "enemies", "slag_king")
BG, PANEL, INK, SUB, GOLD = (30, 27, 33), (46, 42, 50), (236, 230, 220), (170, 162, 150), (240, 190, 90)

FIXES = [
    "1  figure / ground: top planes lifted to the slag light, brighter edge strokes, molten underglow on feet, "
    "shins and fists",
    "2  crown and claw: dark sword steel with bright sharpened-edge strips; 5 crown swords and 2 claw swords "
    "show grip + crossguard",
    "3  limbs: smooth-shaded 'limb' zone (no facets, no triangle web of edge lines); six bold molten / teal cracks",
    "4  iron and steel: broad value planes, one brushy top-edge stroke from the part's own edges, no streaks, "
    "rivets in iron (no white halos)",
    "5  face: eye slits slope down to the centre under a V of iron brows (a scowl); jagged mouth of interlocking "
    "iron fangs over a glowing slot",
]


def font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def crop(path, box, scale=1.0):
    im = Image.open(path).convert("RGB").crop(box)
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    return im


def main():
    before = sys.argv[1] if len(sys.argv) > 1 else "."
    rows = [
        # (label, before image, after image, crop box, scale)
        ("3/4 front, phase 1 (toon preview of the final textures)",
         os.path.join(before, "old_34.png"), os.path.join(PACK, "reports", "slag_king_34.png"), (40, 110, 740, 830), 0.95),
        ("in-game camera, 55 deg, view height 22 m = 49 px/m, shown at 1x (the floor is the Cinder Wastes mid-tone)",
         os.path.join(before, "old_ingame_p1_22.png"), os.path.join(PACK, "work", "review", "slag_king_ingame_p1_22.png"),
         (400, 0, 1160, 560), 0.875),
        ("the furnace face, 2x",
         os.path.join(before, "old_34.png"), os.path.join(PACK, "reports", "slag_king_34.png"), (180, 330, 520, 560), 1.95),
    ]
    tiles = [(lb, crop(b, box, s), crop(a, box, s)) for lb, b, a, box, s in rows]
    W = 1500
    pad = 16
    title_h, head_h, lab_h = 70, 34, 28
    fix_h = 26 * len(FIXES) + 20
    H = title_h + fix_h + head_h + sum(lab_h + max(t[1].height, t[2].height) + pad for t in tiles) + pad
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((pad, 14), "The Slag King - art review fixes (7/10 must-fix list), before and after", font=font(28, True), fill=GOLD)
    d.text((pad, 48), "same build script, same cameras and crops; left = before, right = after", font=font(15), fill=SUB)
    y = title_h
    for line in FIXES:
        d.text((pad, y + 4), line, font=font(15), fill=INK)
        y += 26
    y += 20
    col_w = (W - 3 * pad) // 2
    d.text((pad, y), "BEFORE", font=font(20, True), fill=SUB)
    d.text((2 * pad + col_w, y), "AFTER", font=font(20, True), fill=GOLD)
    y += head_h
    for lb, b, a in tiles:
        d.text((pad, y + 4), lb, font=font(15), fill=INK)
        y += lab_h
        h = max(b.height, a.height)
        for k, im in enumerate((b, a)):
            x0 = pad + k * (col_w + pad)
            d.rectangle((x0, y, x0 + col_w - 1, y + h - 1), fill=PANEL)
            sheet.paste(im, (x0 + (col_w - im.width) // 2, y + (h - im.height) // 2))
        y += h + pad
    out = os.path.join(PACK, "reports", "slag_king_review_fix.png")
    sheet.save(out, optimize=True)
    if os.path.getsize(out) > 1.9e6:          # review PNGs stay under 2 MB: fall back to a 256-colour palette
        sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(
            out, optimize=True)
    print(out, sheet.size, "%.2f MB" % (os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
