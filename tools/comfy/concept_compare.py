"""Stage 0: put approved concepts side by side and mark where they disagree (a sheet-analysis image).

  <comfy-python> tools/comfy/concept_compare.py art/characters/<key>/<spec>.json

<comfy-python> = D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe (PIL + numpy).

When a hero's approved images disagree (a side view drawn mirrored, a weapon on the other arm, a
different chest piece), the stage-0 pack records every difference and the resolution. This tool
draws the evidence: rows of panels, each a crop of an approved image (optionally mirrored, which is
how a resolved reference set is shown), with numbered markers that match a legend of findings.

Spec (JSON; coordinates are pixels of the SOURCE image, before crop and mirror):
  {"title", "subtitle", "output",
   "rows": [{"label", "height", "panels": [{"image", "crop": [x0, y0, x1, y1], "mirror": false,
             "caption", "status": "conflict" | "ok" | "info", "markers": [[x, y, n], ...]}]}],
   "legend": [{"n", "title", "text", "status"}], "legend_columns": 2, "footer"}
Deterministic; writes one PNG (a sheet over 2 MB is re-saved with 256 dithered colours, the review-PNG
limit of docs/ART_PIPELINE.md). It draws what the spec says: the findings themselves are written
by a person or agent in the spec and in the pack's sheet-analysis note.
"""
import json
import os
import sys

from PIL import Image, ImageOps

import gf_img as G

STATUS_RGB = {"conflict": (255, 140, 90), "ok": (140, 220, 140), "info": (200, 194, 184)}
MARK_RGB = (255, 194, 75)
LIMIT = 2_000_000


def marker(d, x, y, n, r=13):
    d.ellipse([x - r - 2, y - r - 2, x + r + 2, y + r + 2], fill=(20, 18, 22))
    d.ellipse([x - r, y - r, x + r, y + r], fill=MARK_RGB)
    G.text(d, (x, y + 5), str(n), 14, True, (24, 20, 16), anchor="ms")


def wrap_lines(s, width, size, bold=False):
    words, line, out = s.split(), "", []
    for w in words:
        t = (line + " " + w).strip()
        if G.text_w(t, size, bold) > width and line:
            out.append(line)
            line = w
        else:
            line = t
    if line:
        out.append(line)
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec_path = G.absp(argv[1])
    spec = json.load(open(spec_path, encoding="utf-8"))
    W = spec.get("width", 2400)
    cream, grey, soft = (236, 228, 210), (150, 146, 140), (200, 194, 184)

    # lay out the rows first (panel sizes), then the legend, to know the height
    rows = []
    for row in spec["rows"]:
        h = row.get("height", 560)
        panels = []
        for p in row["panels"]:
            src = Image.open(G.absp(p["image"])).convert("RGB")
            x0, y0, x1, y1 = p.get("crop") or (0, 0, src.width, src.height)
            im = src.crop((x0, y0, x1, y1))
            if p.get("mirror"):
                im = ImageOps.mirror(im)
            s = h / float(im.height)
            panels.append((p, im.resize((max(1, round(im.width * s)), h), Image.LANCZOS), s, (x0, y0, x1, y1)))
        ncap = max(len(wrap_lines(p.get("caption", ""), im.width - 4, 14, True)[:3]) for p, im, _, _ in panels)
        rows.append((row, h, panels, 40 + 18 * ncap + 30))
    cols = spec.get("legend_columns", 2)
    col_w = (W - 80 - (cols - 1) * 40) // cols
    items = []
    for it in spec.get("legend", []):
        lines = wrap_lines(it["text"], col_w - 44, 15)
        items.append((it, lines, 26 + 20 * len(lines) + 14))
    per_col = -(-len(items) // cols) if items else 0
    col_heights = [sum(t[2] for t in items[c * per_col:(c + 1) * per_col]) for c in range(cols)]
    H = 130 + sum(h + 16 + gap for _, h, _, gap in rows) + (60 + max(col_heights) if items else 0) + 50

    sheet, d = G.new_sheet(W, H)
    G.text(d, (40, 64), spec["title"], 42, True, MARK_RGB, anchor="ls")
    G.text(d, (40, 98), spec.get("subtitle", ""), 17, False, grey, anchor="ls")
    y = 130
    for row, h, panels, gap in rows:
        G.text(d, (40, y + 4), row["label"], 20, True, cream, anchor="ls")
        y += 16
        x = 40
        for p, im, s, (x0, y0, x1, y1) in panels:
            sheet.paste(im, (x, y))
            col = STATUS_RGB.get(p.get("status", "info"), soft)
            d.rectangle([x - 1, y - 1, x + im.width, y + im.height], outline=col, width=2)
            for mx, my, n in p.get("markers", []):
                px = (x1 - mx) if p.get("mirror") else (mx - x0)
                marker(d, x + px * s, y + (my - y0) * s, n)
            cap = wrap_lines(p.get("caption", ""), im.width - 4, 14, True)
            for k, ln in enumerate(cap[:3]):
                G.text(d, (x, y + h + 20 + 18 * k), ln, 14, True, col if k == 0 else soft, anchor="ls")
            x += im.width + 24
        y += h + gap
    if items:
        y += 10
        G.text(d, (40, y), spec.get("legend_title", "Findings (numbers match the markers)"), 20, True, cream, anchor="ls")
        y += 20
        for c in range(cols):
            cx, cy = 40 + c * (col_w + 40), y
            for it, lines, hh in items[c * per_col:(c + 1) * per_col]:
                marker(d, cx + 14, cy + 14, it["n"])
                col = STATUS_RGB.get(it.get("status", "info"), soft)
                G.text(d, (cx + 40, cy + 20), it["title"], 16, True, col, anchor="ls")
                for k, ln in enumerate(lines):
                    G.text(d, (cx + 40, cy + 42 + 20 * k), ln, 15, False, soft, anchor="ls")
                cy += hh
    srcs = sorted({p["image"] for row in spec["rows"] for p in row["panels"]})
    foot = spec.get("footer") or "generated by tools/comfy/concept_compare.py from %s; sources: %s" % (
        G.rel(spec_path), ", ".join("%s (%s...)" % (os.path.basename(s_), G.sha256(G.absp(s_))[:12]) for s_ in srcs))
    G.text(d, (40, H - 22), foot, 13, False, (120, 116, 110), anchor="ls")
    out = G.absp(spec["output"])
    sheet.save(out, optimize=True)
    note = ""
    if os.path.getsize(out) > LIMIT:      # review PNGs stay under 2 MB: fall back to 256 dithered colours
        sheet.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(out, optimize=True)
        note = ", 256-colour dithered to stay under 2 MB"
    print("[compare] wrote %s (%dx%d, %.2f MB%s)" % (G.rel(out), W, H, os.path.getsize(out) / 1e6, note))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
