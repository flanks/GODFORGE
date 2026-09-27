"""Review sheets for Kael's stage-2 production mesh (companion of s2_kael_review.py). Needs PIL + numpy, so run it with
ComfyUI's standalone python:

  <comfy-python> tools/blender/gf_hero/s2_kael_sheets.py <render_dir> <report_dir> <concept.png> <concept_mask.png>
                 <texture_dir> <stage1_render_dir> <stage1_stem>

A copy of s2_valdris_sheets.py (label / grid / < 2 MB saving / concept-silhouette IoU) with Kael's panels. Sheets
(reports/stage2/):
  stage2_vs_concept.png   the approved concept, stage 2 armed (serpent_smg on the right hand frame) and bare, T-pose,
                          silhouette overlays + IoU against the stage-1 cut-out mask (the concept without the revolvers
                          and the diffuse smoke), and the back
  stage2_turnaround.png   bare: toon review shading (6 views), clay (4), flat albedo (2)
  stage2_armed.png        with the serpent_smg GLB on the right-hand frame: turnaround and close-ups
  stage2_ingame.png       the client camera (ortho 55 deg, 22 m / 28 m, true 1080p pixels): bare and armed; toon,
                          toon + P1 rim, silhouette, toon at yaw 35, the stage-1 blockout; 3x zooms
  stage2_closeups.png     face (front, 3/4 both sides, profile), collar, torso, ghost arm and hand, gun hand, hips, hem
                          with the ghost-flame tatters, boot, coat back
  stage2_wireframe.png    joint topology on the body alone, and the parts
  stage2_textures.png     base colour, emissive, tangent normal map, UV layout
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MAX_BYTES = 2_000_000
BG = (40, 42, 46)
FG = (235, 235, 235)


def font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def label(img, text, size=20, pos=(8, 6), fill=FG):
    d = ImageDraw.Draw(img)
    f = font(size)
    x, y = pos
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        d.text((x + dx, y + dy), text, font=f, fill=(0, 0, 0))
    d.text((x, y), text, font=f, fill=fill)
    return img


def save_small(img, path, palette=False):
    """PNG under MAX_BYTES (shrunk 12 % at a time); palette=True stores 256 adaptive colours first (large sheets)."""
    img = img.convert("RGB")

    def save(im):
        (im.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) if palette else im).save(path, optimize=True)
    save(img)
    while os.path.getsize(path) > MAX_BYTES:
        img = img.resize((int(img.width * 0.88), int(img.height * 0.88)), Image.LANCZOS)
        save(img)
    print("[kael sheets] %s %dx%d %.2f MB" % (os.path.basename(path), img.width, img.height, os.path.getsize(path) / 1e6))


def load(p):
    return Image.open(p).convert("RGB") if os.path.isfile(p) else None


def tiles_sheet(items, cols, tile, title, tile_h=None):
    items = [(load(p) if isinstance(p, str) else p, t) for p, t in items]
    items = [(im, t) for im, t in items if im is not None]
    th = tile_h or tile
    rows = max(1, (len(items) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * tile, rows * th + 44), BG)
    label(sheet, title, 24, (10, 9))
    for i, (im, text) in enumerate(items):
        im = im.copy()
        im.thumbnail((tile, th), Image.LANCZOS)
        cell = Image.new("RGB", (tile, th), BG)
        cell.paste(im, ((tile - im.width) // 2, (th - im.height) // 2))
        label(cell, text, 17)
        sheet.paste(cell, ((i % cols) * tile, 44 + (i // cols) * th))
    return sheet


def bbox_mask(a):
    ys, xs = np.nonzero(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def iou(sil_path, cmask):
    m = np.asarray(Image.open(sil_path).convert("RGBA"))[..., 3] > 127
    c = np.asarray(Image.open(cmask).convert("L")) > 127
    cb, mb = bbox_mask(c), bbox_mask(m)
    h, w = cb.shape
    mr = np.asarray(Image.fromarray(mb.astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)) > 127
    v = float((cb & mr).sum()) / float((cb | mr).sum())
    ov = np.zeros((h, w, 3), np.uint8) + np.array(BG, np.uint8)
    ov[cb & mr] = (235, 200, 60)
    ov[cb & ~mr] = (220, 50, 40)
    ov[~cb & mr] = (60, 200, 90)
    return v, Image.fromarray(ov), mb.shape[1] / mb.shape[0], w / h


def main(argv):
    rd, od, concept, cmask, texdir, bdir, bstem = argv[:7]
    os.makedirs(od, exist_ok=True)
    R = lambda n: os.path.join(rd, n)  # noqa: E731
    B = lambda n: os.path.join(bdir, "%s_%s" % (bstem, n))  # noqa: E731
    tag = "Kael stage 2"
    met = json.load(open(R("review_metrics.json"))) if os.path.isfile(R("review_metrics.json")) else {}

    # ---- concept comparison -------------------------------------------------------------------------------------
    c = np.asarray(Image.open(cmask).convert("L")) > 127
    ys, xs = np.nonzero(c)
    con = Image.open(concept).convert("RGB").crop((xs.min() - 10, ys.min() - 10, xs.max() + 10, ys.max() + 10))
    res = {}
    for key, fn in (("bare_tpose", "frontsil.png"), ("armed_tpose", "armed_frontsil.png")):
        if os.path.isfile(R(fn)):
            res[key] = iou(R(fn), cmask)
            met["front_iou_vs_concept_" + key] = round(res[key][0], 4)
            met["aspect_mesh_" + key] = round(res[key][2], 4)
    met["aspect_concept"] = round(res["bare_tpose"][3], 4) if res else None
    T = 620
    tiles = [(con, "approved concept (front)"),
             (load(R("armed_toon_front.png")), "stage 2 armed (serpent_smg, weapon_R)"),
             (load(R("toon_front.png")), "stage 2 bare (hands empty)")]
    for key, lab in (("bare_tpose", "bare"), ("armed_tpose", "armed")):
        if key in res:
            tiles.append((res[key][1], "%s silhouette IoU %.3f vs the cut-out" % (lab, res[key][0])))
    tiles.append((load(R("toon_back.png")), "stage 2 back (brief section 7 proposal)"))
    sheet = Image.new("RGB", (3 * T, 2 * T + 44), BG)
    label(sheet, "%s vs the approved concept (silhouettes: yellow both, red concept only, green mesh only)" % tag, 24, (10, 9))
    for i, (im, t) in enumerate(tiles):
        if im is None:
            continue
        im = im.copy()
        im.thumbnail((T, T - 10), Image.LANCZOS)
        cell = Image.new("RGB", (T, T), BG)
        cell.paste(im, ((T - im.width) // 2, (T - im.height) // 2))
        label(cell, t, 17)
        sheet.paste(cell, ((i % 3) * T, 44 + (i // 3) * T))
    save_small(sheet, os.path.join(od, "stage2_vs_concept.png"))

    # ---- turnaround --------------------------------------------------------------------------------------------------
    items = [(R("toon_%s.png" % v), "toon %s" % v) for v in ("front", "front34L", "sideL", "back", "back34R", "sideR")]
    items += [(R("clay_%s.png" % v), "clay %s" % v) for v in ("front", "front34L", "sideL", "back")]
    items += [(R("albedo_%s.png" % v), "albedo %s" % v) for v in ("front", "back")]
    save_small(tiles_sheet(items, 6, 400, "%s: production mesh without the weapon (toon review shading, clay, flat albedo)" % tag),
               os.path.join(od, "stage2_turnaround.png"))

    # ---- armed -------------------------------------------------------------------------------------------------------
    items = [(R("armed_toon_%s.png" % v), "armed %s" % v) for v in ("front", "front34R", "sideR", "back34L")]
    items += [(R("armed_close_%s.png" % v), "serpent_smg %s" % v.replace("_", " ")) for v in ("smg_34", "smg_top", "upper_34")]
    save_small(tiles_sheet(items, 4, 480, "%s: with the serpent_smg GLB (weapon track) on the recorded right-hand frame, identity transform" % tag),
               os.path.join(od, "stage2_armed.png"))

    # ---- in-game --------------------------------------------------------------------------------------------------------
    rows = []
    for prefix, lab in (("", "bare"), ("armed_", "armed")):
        for vh in (22, 28):
            row = [(R("%singame_%d_%s.png" % (prefix, vh, look)), "%s %s %dm" % (lab, look, vh)) for look in ("toon", "toonP1", "sil", "toon34")]
            row.append((B("ingame_%d_tex.png" % vh), "stage-1 blockout %dm" % vh))
            rows.append(row)
    Z, CW, CH = 3, 150, 120
    ncol = 5
    rh = CH * Z
    sheet = Image.new("RGB", (ncol * 256 + 2 * CW * Z, 44 + len(rows) * rh), BG)
    label(sheet, "%s: client camera (ortho 55 deg, FixedVertical 22 m / 28 m, true 1080p px), Cycles-CPU toon review; + 3x zoom of toon and blockout" % tag, 20, (10, 10))
    for r_, row in enumerate(rows):
        for c_, (p, t) in enumerate(row):
            im = load(p)
            if im is None:
                continue
            tile = im.copy()
            label(tile, t, 14)
            sheet.paste(tile, (c_ * 256, 44 + r_ * rh))
            if c_ in (0, 4):
                k = 0 if c_ == 0 else 1
                x0, y0 = (256 - CW) // 2, (256 - CH) // 2
                z = im.crop((x0, y0, x0 + CW, y0 + CH)).resize((CW * Z, CH * Z), Image.NEAREST)
                sheet.paste(z, (ncol * 256 + k * CW * Z, 44 + r_ * rh))
    save_small(sheet, os.path.join(od, "stage2_ingame.png"))

    # ---- close-ups, wireframes -------------------------------------------------------------------------------------------
    names = ("head_front", "head_34", "head_34R", "head_side", "collar_34", "torso_front", "ghost_arm", "ghost_hand", "gun_hand",
             "hips_34R", "hem_front", "boot_34", "coat_back", "coat_34back")
    save_small(tiles_sheet([(R("close_%s.png" % n), n.replace("_", " ")) for n in names], 5, 480, "%s: close-ups (toon review shading)" % tag),
               os.path.join(od, "stage2_closeups.png"))
    names = ("body_front", "body_back", "shoulder", "elbow_forearm", "hand", "hip_knee", "knee", "face", "coat", "coat_back",
             "gear", "boots", "hair")
    save_small(tiles_sheet([(R("wire_%s.png" % n), n.replace("_", " ")) for n in names], 5, 440,
                           "%s: topology (the body alone for the joints; the parts)" % tag), os.path.join(od, "stage2_wireframe.png"))

    # ---- textures ----------------------------------------------------------------------------------------------------------
    S = 900
    ims = [Image.open(os.path.join(texdir, "kael_%s.png" % n)).convert("RGB") for n in ("basecolor", "emissive", "normal")]
    small = [im.resize((S, S), Image.LANCZOS) for im in ims]
    uv = small[0].copy()
    d = ImageDraw.Draw(uv)
    if os.path.isfile(R("uv_segments.npy")):
        for x0, y0, x1, y1 in np.load(R("uv_segments.npy")):
            d.line([(x0 * S, (1 - y0) * S), (x1 * S, (1 - y1) * S)], fill=(250, 250, 240), width=1)
    sheet = Image.new("RGB", (4 * S, S + 50), BG)
    label(sheet, "%s: base colour %dx%d | emissive | tangent normal (OpenGL +Y, baked from the blockout) | UV layout" % (tag, ims[0].width, ims[0].height), 22, (10, 12))
    for i, im in enumerate(small + [uv]):
        sheet.paste(im, (i * S, 50))
    save_small(sheet, os.path.join(od, "stage2_textures.png"))

    with open(R("review_metrics.json"), "w", newline="\n") as f:
        json.dump(met, f, indent=1)
        f.write("\n")
    rj = os.path.join(od, "review.json")
    if os.path.isfile(rj):
        rep = json.load(open(rj))
        rep.update({k: v for k, v in met.items() if k.startswith(("front_iou", "aspect_"))})
        with open(rj, "w", newline="\n") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    print("[kael sheets] IoU", {k: v for k, v in met.items() if k.startswith("front_iou")})


if __name__ == "__main__":
    main(sys.argv[1:])
