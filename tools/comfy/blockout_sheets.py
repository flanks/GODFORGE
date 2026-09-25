"""Contact sheets + concept-silhouette IoU for stage-1 hero blockouts.

Companion of tools/blender/gf_hero/render_blockout.py (which writes the individual renders and a
metrics JSON per seed). Needs PIL + numpy, so run it with ComfyUI's standalone python:

  D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe tools/comfy/blockout_sheets.py \
      <render_root> <report_dir> <concept.png> <concept_mask.png> <stem> [<stem> ...]

<render_root>/<stem>/ holds render_blockout.py's output for that stem. Writes into <report_dir>:
  <stem>_turnaround.png   textured (top) + clay (bottom) front / 3-4 / side / back / 3-4 back / side
  <stem>_closeups.png     head, both gauntlets, skirt + legs (textured and clay)
  <stem>_ingame.png       the client camera (ortho, 55 deg, 22 m and 28 m view heights) at 1080p pixel
                          scale, then 4x nearest-neighbour zooms of the same pixels
  <stem>_silhouette.png   front silhouette vs the concept mask (yellow = both, red = concept only,
                          green = mesh only) and the IoU, which is also written into <stem>_metrics.json
  blockout_compare.png    the concept next to every stem's front / 3-4 / clay views
  blockout_selected.png   with --selected <stem>: the picked seed beside the concept, 2 rows
Every PNG is kept under 2 MB (downscaled until it fits).
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

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


def label(img, text, size=22, pos=(8, 6)):
    d = ImageDraw.Draw(img)
    f = font(size)
    x, y = pos
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        d.text((x + dx, y + dy), text, font=f, fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=FG)
    return img


def save_small(img, path):
    img = img.convert("RGB")
    img.save(path, optimize=True)
    while os.path.getsize(path) > MAX_BYTES:
        img = img.resize((int(img.width * 0.85), int(img.height * 0.85)), Image.LANCZOS)
        img.save(path, optimize=True)
    print("[sheets] %s %dx%d %.2f MB" % (os.path.basename(path), img.width, img.height, os.path.getsize(path) / 1e6))


def grid(tiles, cols, tile, title=None):
    rows = (len(tiles) + cols - 1) // cols
    top = 44 if title else 0
    sheet = Image.new("RGB", (cols * tile, rows * tile + top), BG)
    if title:
        label(sheet, title, 28, (10, 6))
    for i, (img, text) in enumerate(tiles):
        if img is None:
            continue
        t = img.convert("RGB").resize((tile, tile), Image.LANCZOS)
        label(t, text, 20)
        sheet.paste(t, ((i % cols) * tile, top + (i // cols) * tile))
    return sheet


def load(path):
    return Image.open(path) if os.path.isfile(path) else None


def bbox_mask(a):
    ys, xs = np.nonzero(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def silhouette(render_dir, stem, concept_mask_path, out_dir):
    m = np.asarray(Image.open(os.path.join(render_dir, "%s_frontsil.png" % stem)).convert("RGBA"))[..., 3] > 127
    c = np.asarray(Image.open(concept_mask_path).convert("L")) > 127
    cb = bbox_mask(c)
    mb = bbox_mask(m)
    h, w = cb.shape
    mr = np.asarray(Image.fromarray(mb.astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)) > 127
    inter, union = (cb & mr).sum(), (cb | mr).sum()
    iou = float(inter) / float(union)
    ov = np.zeros((h, w, 3), np.uint8) + np.array(BG, np.uint8)
    ov[cb & mr] = (235, 200, 60)
    ov[cb & ~mr] = (220, 50, 40)
    ov[~cb & mr] = (60, 200, 90)
    img = Image.fromarray(ov)
    label(img, "%s  front silhouette IoU vs concept = %.3f   (aspect mesh %.3f / concept %.3f)"
          % (stem, iou, mb.shape[1] / mb.shape[0], w / h), 26, (12, 8))
    label(img, "yellow both   red concept only   green mesh only", 22, (12, 44))
    save_small(img, os.path.join(out_dir, "%s_silhouette.png" % stem))
    return {"front_iou_vs_concept": round(iou, 4), "aspect_mesh": round(mb.shape[1] / mb.shape[0], 4),
            "aspect_concept": round(w / h, 4)}


def ingame(render_dir, stem, out_dir):
    tiles = []
    for vh in (22, 28):
        row = []
        for look in ("tex", "sil", "tex34"):
            im = load(os.path.join(render_dir, "%s_ingame_%d_%s.png" % (stem, vh, look)))
            if im is None:
                continue
            row.append((im.convert("RGB"), look))
        tiles.append((vh, row))
    Z, CW, CH = 3, 160, 128          # zoom window: the whole T-pose span at 22 m fits in 160 px
    row_h = max(256, CH * Z)
    sheet = Image.new("RGB", (3 * 256 + 3 * CW * Z, 44 + 2 * row_h), BG)
    label(sheet, "%s  in-game camera (ortho, 55 deg pitch, yaw 0): native 1080p pixels (left), 3x nearest zoom (right)" % stem, 24, (10, 8))
    for r, (vh, row) in enumerate(tiles):
        y = 44 + r * row_h
        for i, (im, look) in enumerate(row):
            n = im.copy()
            label(n, "%dm %s" % (vh, look), 16, (4, 4))
            sheet.paste(n, (i * 256, y))
            cx, cy = im.width // 2, im.height // 2
            z = im.crop((cx - CW // 2, cy - CH // 2, cx + CW // 2, cy + CH // 2)).resize((CW * Z, CH * Z), Image.NEAREST)
            label(z, "view height %d m (%s) - %s" % (vh, "1 player" if vh == 22 else "4 players", look), 18)
            sheet.paste(z, (3 * 256 + i * CW * Z, y))
    save_small(sheet, os.path.join(out_dir, "%s_ingame.png" % stem))


def main(argv):
    if len(argv) < 5:
        print(__doc__)
        return 2
    selected = None
    if "--selected" in argv:
        i = argv.index("--selected")
        selected = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    render_root, out_dir, concept, concept_mask = argv[:4]
    stems = argv[4:]
    os.makedirs(out_dir, exist_ok=True)
    views = ["front", "front34L", "sideL", "back", "back34R", "sideR"]
    concept_img = Image.open(concept).convert("RGB").crop((150, 0, 1386, 1024))
    compare = []
    for stem in stems:
        rd = os.path.join(render_root, stem)
        tex = [(load(os.path.join(rd, "%s_tex_%s.png" % (stem, v))), "lit " + v) for v in views]
        clay = [(load(os.path.join(rd, "%s_clay_%s.png" % (stem, v))), "clay " + v) for v in views]
        albedo = [(load(os.path.join(rd, "%s_albedo_%s.png" % (stem, v))), "unlit albedo " + v) for v in ("front", "front34L", "back")]
        save_small(grid([t for t in tex + clay + albedo if t[0] is not None], 6, 440,
                        "%s  turnaround (common ortho scale, hero normalised to 2.2 m): lit / clay / unlit albedo" % stem),
                   os.path.join(out_dir, "%s_turnaround.png" % stem))
        close = []
        for part, vs in (("head", ("front", "34L", "side")), ("gauntletR", ("front", "34", "top")),
                         ("gauntletL", ("front", "34")), ("legs", ("front", "34L", "back"))):
            row = []
            for tag in ("close", "closeclay"):
                for v in vs:
                    row.append((load(os.path.join(rd, "%s_%s_%s_%s.png" % (stem, tag, part, v))),
                                "%s %s %s" % ("lit" if tag == "close" else "clay", part, v)))
            close += row + [(None, "")] * (6 - len(row))
        close += [(load(os.path.join(rd, "%s_diag_%s.png" % (stem, v))), t) for v, t in (
            ("front", "components front"), ("back", "components back"), ("sectionFront", "section at mid-depth"),
            ("sectionSide", "section at mid-width"))]
        save_small(grid(close, 6, 400, "%s  close-ups; last row: components (grey main, red/blue/green next, yellow tiny) and sections" % stem),
                   os.path.join(out_dir, "%s_closeups.png" % stem))
        ingame(rd, stem, out_dir)
        sil = silhouette(rd, stem, concept_mask, out_dir)
        mpath = os.path.join(rd, "%s_metrics.json" % stem)
        if os.path.isfile(mpath):
            metrics = json.load(open(mpath))
            metrics.update(sil)
            with open(mpath, "w", newline="\n") as f:
                json.dump(metrics, f, indent=1)
                f.write("\n")
        seed = stem.rsplit("_", 1)[-1]
        compare.append((concept_img, "approved concept"))
        for kind, v in (("tex", "front"), ("tex", "front34L"), ("tex", "back"), ("clay", "front34L"), ("albedo", "front")):
            compare.append((load(os.path.join(rd, "%s_%s_%s.png" % (stem, kind, v))),
                            "%s %s %s" % (seed, {"tex": "lit", "clay": "clay", "albedo": "albedo"}[kind], v)))
    save_small(grid(compare, 6, 400, "Brax stage-1 blockout: concept vs TRELLIS.2 seeds, one row per seed (SCULPT REFERENCE ONLY)"),
               os.path.join(out_dir, "blockout_compare.png"))
    if selected:
        rd = os.path.join(render_root, selected)
        game = load(os.path.join(rd, "%s_ingame_22_tex.png" % selected))
        if game is not None:
            game = game.crop((48, 64, 208, 192)).resize((500, 400), Image.NEAREST)
        tiles = [(concept_img, "approved concept (front)")]
        tiles += [(load(os.path.join(rd, "%s_%s.png" % (selected, n))), t) for n, t in (
            ("tex_front", "lit front"), ("tex_front34L", "lit 3/4"), ("tex_back34R", "lit back 3/4"),
            ("clay_front34L", "clay 3/4"), ("close_head_34L", "head 3/4"), ("close_gauntletR_34", "right gauntlet 3/4"),
            ("closeclay_gauntletR_top", "gauntlet clay, top"), ("close_legs_34L", "skirt + legs 3/4"))]
        tiles.append((game, "in-game 55 deg, 22 m, 3x pixels"))
        save_small(grid(tiles, 5, 440, "Brax stage-1 blockout: picked seed %s vs concept - SCULPT REFERENCE ONLY, never shipped"
                        % selected.rsplit("_", 1)[-1]), os.path.join(out_dir, "blockout_selected.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
