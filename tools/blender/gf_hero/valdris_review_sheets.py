"""Valdris review of stages 2-5: the contact sheets (PIL; any Python with Pillow).

  python tools/blender/gf_hero/valdris_review_sheets.py [--in art/characters/valdris/work/review]
         [--out art/characters/valdris/reports/review] [--before <review dir of the previous file>]

closeups_<n>.png: from valdris_review.py's Workbench close-ups, one row per clip: its lower-body extreme frame (max knee)
and its upper-body extreme frame (highest arm, else max elbow), each as five views (shoulders / pauldrons, cannon elbow,
left elbow, knees, cape), labelled with the frame and the measured joint angles; six clips per sheet.
lineup.png / horde.png (when valdris_review_lineup.py has rendered them): composited on the ground at 1:1, with a 2x
nearest crop, and lineup_stats.json (CIE L*, gold / glow / red share per subject).
cape_before_after.png (with --before): the cape from behind where the legs meet it, the previous file above, this one below.
review.json: valdris_review.py's measurements, copied next to the sheets.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
argv = sys.argv[1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


IN = os.path.join(ROOT, opt("--in", os.path.join("art", "characters", "valdris", "work", "review")))
BEFORE = opt("--before", None)       # a review run of the previous file (valdris_review.py --glb <old> --out <dir>)
OUT = os.path.join(ROOT, opt("--out", os.path.join("art", "characters", "valdris", "reports", "review")))
os.makedirs(OUT, exist_ok=True)
T = 200
VIEWS = ["shoulders", "cannon_elbow", "left_elbow", "knees", "cape"]
LABW = 210


def font(sz):
    for f in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


F, FS = font(15), font(12)


def save_q(img, path):
    """A 256-colour palette PNG: the Workbench close-ups and the horde frame are review sheets, not measurements, and are
    committed (about a quarter of the size of full colour)."""
    img.convert("RGB").quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(
        path, optimize=True)
rep = json.load(open(os.path.join(IN, "review.json"), encoding="utf-8"))
with open(os.path.join(OUT, "review.json"), "w", encoding="utf-8", newline="\n") as _f:     # the measured numbers, next to the sheets
    json.dump(rep, _f, indent=1)
    _f.write("\n")
clips = [(k, c) for k, c in rep["clips"].items() if c.get("renders")]
per = 6
for n in range(0, len(clips), per):
    chunk = clips[n:n + per]
    W = LABW + 2 * len(VIEWS) * T + 12
    H = 40 + len(chunk) * (T + 22)
    im = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(im)
    d.text((8, 8), "Valdris review of stages 2-5: extreme frames of the SHIPPED valdris.glb + colossus_cannon.glb "
           "(Workbench). Left block: max-knee frame; right block: highest-arm / max-elbow frame.", fill=(230, 230, 230), font=F)
    for j, v in enumerate(VIEWS * 2):
        d.text((LABW + j * T + (12 if j >= len(VIEWS) else 0) + 4, 24), v, fill=(170, 170, 170), font=FS)
    for r, (name, c) in enumerate(chunk):
        y = 40 + r * (T + 22)
        fr = c["review_frames"]
        lines = [name, "frames %d" % c["frames"],
                 "low f%d  up f%d" % (fr["lower"], fr["upper"]),
                 "knee max %.0f / %.0f" % (c["knee_L_max"], c["knee_R_max"]),
                 "elbow max L %.0f R %.0f" % (c["elbow_L_max"], c["elbow_R_max"]),
                 "arm elev R %.0f..%.0f" % tuple(c["elev_R_range"]),
                 "lowest %.0f mm (%s)" % (c["lowest_z_mm"], c["lowest_bone"]),
                 "cannon poke %d cuts %d" % (c["cannon_poke_max"], c["cannon_cuts_max"])]
        for k, t in enumerate(lines):
            d.text((6, y + 4 + k * 16), t, fill=(235, 235, 235) if k == 0 else (190, 190, 190), font=F if k == 0 else FS)
        for b, tag in enumerate(("lower", "upper")):
            for j, p in enumerate(c["renders"][tag]):
                x = LABW + (b * len(VIEWS) + j) * T + (12 if b else 0)
                try:
                    t = Image.open(os.path.join(IN, p)).convert("RGB").resize((T, T), Image.LANCZOS)
                except OSError:
                    continue
                im.paste(t, (x, y))
    p = os.path.join(OUT, "closeups_%d.png" % (n // per + 1))
    save_q(im, p)
    print("wrote", p)



def lstar(rgb):
    """CIE L* of sRGB pixels (N x 3, 0-255)."""
    import numpy as np
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    Y = lin @ np.array([0.2126, 0.7152, 0.0722])
    return np.where(Y > 0.008856, 116 * np.cbrt(Y) - 16, 903.3 * Y)


GROUNDS = {"cinder ground": (58, 38, 28), "ash ground": (112, 104, 96)}
raw = os.path.join(IN, "lineup_raw.png")
if os.path.isfile(raw):
    import colorsys
    import numpy as np
    L = Image.open(raw).convert("RGBA")
    meta = json.load(open(os.path.join(IN, "lineup_boxes.json"), encoding="utf-8"))
    A = np.asarray(L).astype(float)
    stats = []
    for sub in meta["subjects"]:
        x0, y0, x1, y1 = sub["box"]
        px = A[y0:y1, x0:x1].reshape(-1, 4)
        px = px[px[:, 3] > 200][:, :3]
        if not len(px):
            continue
        ls = lstar(px)
        hsv = np.array([colorsys.rgb_to_hsv(*(p / 255.0)) for p in px])
        gold = ((hsv[:, 0] > 30 / 360) & (hsv[:, 0] < 55 / 360) & (hsv[:, 1] > 0.35) & (hsv[:, 2] > 0.35)).mean()
        glow = ((px[:, 0] > 200) & (px[:, 1] > 90) & (hsv[:, 1] > 0.3)).mean()
        red = (((hsv[:, 0] < 12 / 360) | (hsv[:, 0] > 345 / 360)) & (hsv[:, 1] > 0.45) & (hsv[:, 2] > 0.18)).mean()
        stats.append({"label": sub["label"], "pixels": int(len(px)), "L_mean": round(float(ls.mean()), 1),
                      "L_p10": round(float(np.percentile(ls, 10)), 1), "L_p90": round(float(np.percentile(ls, 90)), 1),
                      "gold_share": round(float(gold), 3), "glow_share": round(float(glow), 3), "red_share": round(float(red), 3),
                      "box_px": [x1 - x0, y1 - y0], "opaque_rows": int((A[y0:y1, x0:x1, 3] > 200).any(1).sum()),
                      "opaque_cols": int((A[y0:y1, x0:x1, 3] > 200).any(0).sum())})
    json.dump({"px_per_m": meta["px_per_m"], "subjects": stats}, open(os.path.join(OUT, "lineup_stats.json"), "w",
              encoding="utf-8", newline="\n"), indent=1)
    W0, H0 = L.size
    rows = []
    for gname, col in GROUNDS.items():
        bg = Image.new("RGBA", L.size, col + (255,))
        rows.append((gname, Image.alpha_composite(bg, L).convert("RGB")))
    # 1:1 on both grounds, then the hero block at 3x nearest on the cinder ground
    crop_w = min(W0, int(meta["subjects"][10]["box"][0]) if len(meta["subjects"]) > 10 else W0)
    big = rows[0][1].crop((0, 0, crop_w, H0)).resize((crop_w * 2, H0 * 2), Image.NEAREST)
    sheet = Image.new("RGB", (max(W0, big.size[0]) + 20, 40 + 2 * (H0 + 24) + big.size[1] + 30), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), "Game-size read: the 55 deg client camera at TRUE 1080p pixels, 22 m view height (%.1f px/m), "
           "toon preview; the top row faces screen-right, the bottom row faces the camera" % meta["px_per_m"], fill=(230, 230, 230), font=F)
    y = 34
    for gname, img in rows:
        d.text((10, y), gname + " (1:1)", fill=(200, 200, 200), font=FS)
        sheet.paste(img, (10, y + 16))
        y += H0 + 24
    d.text((10, y), "the heroes at 2x nearest (cinder ground)", fill=(200, 200, 200), font=FS)
    sheet.paste(big, (10, y + 16))
    for sub in meta["subjects"]:
        x0 = sub["box"][0]
        d.text((10 + x0 + 4, 34 + 16 + 2), sub["label"][:22], fill=(240, 220, 160), font=FS)
    sheet.save(os.path.join(OUT, "lineup.png"), optimize=True)
    print("wrote", os.path.join(OUT, "lineup.png"))
    for st in stats:
        print("  %-28s L* mean %5.1f p10 %5.1f p90 %5.1f gold %.3f glow %.3f red %.3f  %s px (%d x %d opaque)" % (
            st["label"], st["L_mean"], st["L_p10"], st["L_p90"], st["gold_share"], st["glow_share"], st["red_share"],
            st["pixels"], st["opaque_cols"], st["opaque_rows"]))
if BEFORE:
    B = os.path.join(ROOT, BEFORE)
    shots = json.load(open(os.path.join(IN, "review.json"), encoding="utf-8")).get("cape_shots", [])
    if shots:
        T2 = 240
        sheet = Image.new("RGB", (LABW + len(shots) * T2, 48 + 2 * (T2 + 20)), (24, 24, 28))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), "The cape from behind where the legs meet it: the previous file (top) and the fixed cloth pass (bottom)",
               fill=(230, 230, 230), font=F)
        for r, (lab, base) in enumerate((("before (39988a2)", B), ("after (this review)", IN))):
            y = 48 + r * (T2 + 20)
            d.text((6, y + 6), lab, fill=(235, 235, 235), font=F)
            for j, pth in enumerate(shots):
                try:
                    t = Image.open(os.path.join(base, pth)).convert("RGB").resize((T2, T2), Image.LANCZOS)
                except OSError:
                    continue
                sheet.paste(t, (LABW + j * T2, y))
                if r == 0:
                    d.text((LABW + j * T2 + 4, y - 14), os.path.basename(pth)[5:-4], fill=(170, 170, 170), font=FS)
        save_q(sheet, os.path.join(OUT, "cape_before_after.png"))
        print("wrote", os.path.join(OUT, "cape_before_after.png"))
hr = os.path.join(IN, "horde_raw.png")
if os.path.isfile(hr):
    H = Image.open(hr).convert("RGB")
    W1, H1 = H.size
    crop = H.crop((W1 // 2 - 320, H1 // 2 - 200, W1 // 2 + 320, H1 // 2 + 160)).resize((1280, 720), Image.NEAREST)
    sheet = Image.new("RGB", (W1, H1 + 720 + 40), (20, 20, 24))
    sheet.paste(H, (0, 0))
    sheet.paste(crop, (0, H1 + 40))
    d = ImageDraw.Draw(sheet)
    d.text((10, H1 + 10), "Above: a full 1920x1080 frame at the 22 m view height (true pixels): Valdris braced in the Siege "
           "Stance at the centre among 140 Cinder Wastes swarm enemies, Brax 5 m to the left on screen (no P1 ground ring, no VFX). Below: the centre at 2x nearest.",
           fill=(230, 230, 230), font=F)
    save_q(sheet, os.path.join(OUT, "horde.png"))
    print("wrote", os.path.join(OUT, "horde.png"))
