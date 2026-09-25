"""Stage-1 input check sheet: does the TRELLIS.2 graph's birefnet mask keep the whole hero?

Run after `run_trellis.py <key> <input.png> --mask-only --out <dir>` (docs/ART_PIPELINE.md section 4,
step 1). Compares the graph's mask with an independent colour key: a smooth background model
(a 4th-order polynomial per channel, fitted to the pixels well outside the mask, so a vignette or
gradient ground is handled) and a per-pixel distance threshold. Needs PIL + numpy, so run it with
ComfyUI's standalone python:

  <comfy-python> tools/comfy/maskcheck_sheet.py <Name> <input.png> <mask.png> <crop.png> <out.png>
      [--original <approved.png>] [--region "label=x0,y0,x1,y1" ...] [--threshold 12] [--json <out.json>]

  --original  the approved concept when the TRELLIS input is derived from it (mirrored, cut out, ...)
  --region    a close-up of the input, gamma-lifted so dark-on-dark edges show. Overlay colours:
              green = mask outline, red = colour key says hero but the mask drops it,
              blue = the mask keeps it but the colour key would drop it (dark areas)
Writes <out.png> (< 2 MB) and, with --json, the numbers the stage-1 report quotes.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

MAX_BYTES = 2_000_000
BG = (40, 42, 46)
FG = (230, 225, 215)


def font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def label(img, text, size=20, pos=(8, 6)):
    d = ImageDraw.Draw(img)
    f = font(size)
    x, y = pos
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        d.text((x + dx, y + dy), text, font=f, fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=FG)
    return img


def grow(mask, r):
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def shrink(mask, r):
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(2 * r + 1))) > 0


def background_model(img, mask):
    h, w, _ = img.shape
    far = ~grow(mask > 0.02, 25)
    ys, xs = np.nonzero(far)
    yy, xx = np.mgrid[0:h, 0:w]

    def feats(y, x):
        y = y / h * 2 - 1
        x = x / w * 2 - 1
        return np.stack([np.ones_like(x), x, y, x * x, y * y, x * y, x ** 3, y ** 3, x * x * y, x * y * y,
                         x ** 4, y ** 4, x * x * y * y], -1)

    a = feats(ys.astype(float), xs.astype(float))
    bg = np.zeros_like(img)
    for ch in range(3):
        coef, *_ = np.linalg.lstsq(a, img[ys, xs, ch], rcond=None)
        bg[..., ch] = feats(yy.astype(float), xx.astype(float)) @ coef
    resid = np.abs(img[far] - bg[far])
    return bg, {"fit_pixels": int(far.sum()), "residual_mean": round(float(resid.mean()), 2),
                "residual_p99": round(float(np.percentile(resid, 99)), 2)}


def fit_tile(img, w, h):
    t = Image.new("RGB", (w, h), BG)
    s = min(w / img.width, h / img.height)
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    t.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return t


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("input")
    ap.add_argument("mask")
    ap.add_argument("crop")
    ap.add_argument("out")
    ap.add_argument("--original")
    ap.add_argument("--region", action="append", default=[])
    ap.add_argument("--threshold", type=float, default=12.0)
    ap.add_argument("--json")
    a = ap.parse_args(argv)

    inp = Image.open(a.input).convert("RGB")
    img = np.asarray(inp).astype(float)
    mask = np.asarray(Image.open(a.mask).convert("L").resize(inp.size)).astype(float) / 255
    m = mask > 0.5
    bg, fit = background_model(img, mask)
    dist = np.sqrt(((img - bg) ** 2).sum(-1))
    key = np.asarray(Image.fromarray((dist > a.threshold).astype(np.uint8) * 255).filter(ImageFilter.MedianFilter(3))) > 127
    key_only = key & ~m
    mask_only = m & ~key
    ys, xs = np.nonzero(m)
    kys, kxs = np.nonzero(key)
    beyond = {str(r): int((key & ~grow(m, r)).sum()) for r in (1, 3, 9, 25)}
    stats = {
        "input": a.input.replace("\\", "/"), "size": list(inp.size), "threshold": a.threshold, "background_fit": fit,
        "mask_px": int(m.sum()), "mask_soft_px": int(((mask > 0.02) & (mask < 0.98)).sum()),
        "mask_bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "key_bbox": [int(kxs.min()), int(kys.min()), int(kxs.max()), int(kys.max())],
        "key_only_px": int(key_only.sum()), "mask_only_dark_px": int(mask_only.sum()),
        "key_only_px_beyond_mask_by": beyond, "regions": {},
    }
    edge = m & ~shrink(m, 1)
    lift = 255 * (img / 255) ** 0.45
    ov = lift.copy()
    ov[key_only] = (255, 40, 30)
    ov[mask_only] = ov[mask_only] * 0.5 + np.array((40, 90, 255)) * 0.5
    ov[edge] = (60, 255, 90)
    ovi = Image.fromarray(ov.clip(0, 255).astype(np.uint8))

    tw, th = 480, 640
    top = []
    if a.original:
        top.append((Image.open(a.original).convert("RGB"), "approved concept %dx%d" % Image.open(a.original).size))
    top.append((inp, "TRELLIS input %dx%d%s" % (inp.width, inp.height, " (derived)" if a.original else "")))
    top.append((Image.open(a.mask).convert("RGB"), "birefnet mask, bbox x %d-%d y %d-%d" % (xs.min(), xs.max(), ys.min(), ys.max())))
    top.append((Image.open(a.crop).convert("RGB"), "node 312 crop = what TRELLIS.2 sees"))
    top.append((ovi, "overlay: red key-only, blue dark kept, green outline"))

    regions = []
    for spec in a.region:
        lab, box = spec.split("=", 1)
        x0, y0, x1, y1 = (int(v) for v in box.split(","))
        sub = (slice(y0, y1), slice(x0, x1))
        stats["regions"][lab] = {"box": [x0, y0, x1, y1], "mask_px": int(m[sub].sum()), "key_only_px": int(key_only[sub].sum()),
                                 "key_only_beyond_3px": int((key & ~grow(m, 3))[sub].sum())}
        regions.append((ovi.crop((x0, y0, x1, y1)), "%s: %d px key-only, %d beyond 3 px" % (lab, stats["regions"][lab]["key_only_px"],
                                                                                     stats["regions"][lab]["key_only_beyond_3px"])))
    cols = max(len(top), 4)
    rw, rh = 380, 420
    rcols = max(1, min(len(regions), cols * tw // rw))
    rrows = (len(regions) + rcols - 1) // rcols if regions else 0
    sheet = Image.new("RGB", (max(cols * tw, rcols * rw), 44 + th + rrows * rh), BG)
    label(sheet, "%s stage-1 input check: birefnet (graph node 192) vs a colour key over a fitted background (threshold %g)"
          % (a.name, a.threshold), 24, (10, 8))
    for i, (im, text) in enumerate(top):
        t = fit_tile(im, tw, th)
        label(t, text, 17)
        sheet.paste(t, (i * tw, 44))
    for i, (im, text) in enumerate(regions):
        s = min((rw - 12) / im.width, (rh - 36) / im.height)
        t = Image.new("RGB", (rw, rh), BG)
        z = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.NEAREST)
        t.paste(z, ((rw - z.width) // 2, 30 + (rh - 30 - z.height) // 2))
        ImageDraw.Draw(t).rectangle((0, 0, rw - 1, rh - 1), outline=(90, 92, 98))
        label(t, text, 15, (6, 6))
        sheet.paste(t, ((i % rcols) * rw, 44 + th + (i // rcols) * rh))
    sheet.save(a.out, optimize=True)
    while os.path.getsize(a.out) > MAX_BYTES:
        sheet = sheet.resize((int(sheet.width * 0.85), int(sheet.height * 0.85)), Image.LANCZOS)
        sheet.save(a.out, optimize=True)
    if a.json:
        with open(a.json, "w", newline="\n") as f:
            json.dump(stats, f, indent=1)
            f.write("\n")
    print("[maskcheck] %s: mask %d px, key-only %d px (%s beyond 1/3/9/25 px), dark kept %d px -> %s %.2f MB"
          % (a.name, stats["mask_px"], stats["key_only_px"], "/".join(str(v) for v in beyond.values()),
             stats["mask_only_dark_px"], a.out, os.path.getsize(a.out) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
