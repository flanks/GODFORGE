"""Review contact sheet from a layout JSON (PIL + numpy; run with ComfyUI's standalone python).

  D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe tools/blender/gf_assets/gfa_sheet.py <layout.json>

Layout:
  {"out": "<png>", "title": "...", "subtitle": "...", "width": 1600,
   "sections": [{"label": "...", "height": 300,
                 "images": [{"path": "...", "label": "...", "scale": 3 (integer nearest upscale, optional)}]}],
   "swatches": [{"hex": "#RRGGBB", "label": "..."}],
   "notes": ["...", ...]}
Images keep their aspect ratio; with "scale" they are enlarged with nearest-neighbour (game-size
pixels stay visible). Rows wrap. The sheet is shrunk until the PNG is under 1.9 MB (commit rule: < 2 MB).
Fonts: assets/fonts (DejaVu, bundled with the game), via tools/comfy/gf_img.py.
"""
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "comfy"))
import gf_img  # noqa: E402

BG = (30, 27, 33)
PANEL = (40, 36, 44)
INK = (232, 226, 212)
DIM = (160, 152, 140)
ACCENT = (242, 193, 78)
MAX_BYTES = 1_900_000


def load(entry, target_h):
    im = Image.open(entry["path"]).convert("RGB")
    s = entry.get("scale")
    if s:
        im = im.resize((im.width * int(s), im.height * int(s)), Image.NEAREST)
    elif target_h and im.height != target_h:
        w = max(1, round(im.width * target_h / im.height))
        im = im.resize((w, target_h), Image.LANCZOS)
    return im


def build(layout):
    W = int(layout.get("width", 1600))
    pad = 14
    blocks = []
    y = 0
    # title
    title_h = 70
    blocks.append(("title", y, title_h))
    y += title_h
    for sec in layout.get("sections", []):
        ims = [(e, load(e, sec.get("height"))) for e in sec["images"]]
        rows, row, rw = [], [], pad
        for e, im in ims:
            if row and rw + im.width + pad > W:
                rows.append(row)
                row, rw = [], pad
            row.append((e, im))
            rw += im.width + pad
        if row:
            rows.append(row)
        h = 30 + sum(max(im.height for _, im in r) + 26 for r in rows) + 8
        blocks.append(("section", y, h, sec, rows))
        y += h
    sw = layout.get("swatches", [])
    notes = layout.get("notes", [])
    foot_h = (60 if sw else 0) + 22 * len(notes) + (20 if notes else 0)
    blocks.append(("foot", y, foot_h))
    y += foot_h
    sheet, d = gf_img.new_sheet(W, y + 6, BG)
    for b in blocks:
        if b[0] == "title":
            gf_img.text(d, (pad, 12), layout.get("title", ""), 30, True, ACCENT)
            gf_img.text(d, (pad, 48), layout.get("subtitle", ""), 15, False, DIM)
        elif b[0] == "section":
            _, y0, h, sec, rows = b
            d.rectangle((6, y0 + 2, W - 6, y0 + h - 4), fill=PANEL)
            gf_img.text(d, (pad, y0 + 8), sec.get("label", ""), 17, True, INK)
            yy = y0 + 32
            for r in rows:
                xx = pad
                rh = max(im.height for _, im in r)
                for e, im in r:
                    sheet.paste(im, (xx, yy))
                    if e.get("label"):
                        gf_img.text(d, (xx + 2, yy + im.height + 4), e["label"], 13, False, DIM)
                    xx += im.width + pad
                yy += rh + 26
        else:
            _, y0, h = b
            xx = pad
            yy = y0 + 6
            for s in sw:
                rgb = gf_img.hex_to_rgb(s["hex"])
                d.rectangle((xx, yy, xx + 44, yy + 30), fill=rgb, outline=(0, 0, 0))
                gf_img.text(d, (xx, yy + 34), s.get("label", s["hex"]), 11, False, DIM)
                xx += max(60, int(gf_img.text_w(s.get("label", s["hex"]), 11)) + 16)
            yy += 60 if sw else 0
            for n in notes:
                gf_img.text(d, (pad, yy), n, 14, False, INK)
                yy += 22
    return sheet


def save_small(im, path):
    scale = 1.0
    while True:
        out = im if scale == 1.0 else im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        out.save(path, optimize=True)
        n = os.path.getsize(path)
        if n <= MAX_BYTES or scale < 0.4:
            return n, out.size
        scale *= 0.88


def main():
    layout = json.load(open(sys.argv[1], encoding="utf-8"))
    im = build(layout)
    n, size = save_small(im, layout["out"])
    print("[gfa_sheet] wrote %s (%dx%d, %.2f MB)" % (layout["out"], size[0], size[1], n / 1e6))


if __name__ == "__main__":
    main()
