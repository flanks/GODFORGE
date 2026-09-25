"""Review sheets for Valdris's stage-2 production mesh (companion of s2_valdris_review.py). Needs PIL + numpy, so run it
with ComfyUI's standalone python:

  <comfy-python> tools/blender/gf_hero/s2_valdris_sheets.py <render_dir> <report_dir> <concept.png> <concept_mask.png>
                 <texture_dir> <stage1_render_dir> <stage1_stem> [<before_render_dir>]

Adapted from tools/comfy/stage2_sheets.py (Brax; label / grid / < 2 MB saving / concept-silhouette IoU), which stays
unchanged. Sheets (reports/stage2/):
  stage2_vs_concept.png   the concept, armed in the review pose45 (the concept's 3/4-drawn arms), armed T-pose, bare,
                          silhouette overlays + IoU for all three
  stage2_turnaround.png   bare: toon review shading (6 views), clay (4), flat albedo (2)
  stage2_armed.png        with the colossus_cannon GLB on the right-hand frame: T-pose turnaround, pose45, cannon
                          close-ups, a section of the cannon (cut on its axis) with the forearm in the sleeve, the fit
  stage2_ingame.png       the client camera (ortho 55 deg, 22 m / 28 m, true 1080p pixels): bare, armed, armed pose45;
                          toon, toon + P1 rim, silhouette, toon at yaw 35, the stage-1 blockout; 3x zooms
  stage2_closeups.png     head, torso, anvil, pauldron, arm, hand, hips, legs, boot, cape
  stage2_wireframe.png    joint topology on the body alone, and the parts
  stage2_textures.png     base colour, emissive, tangent normal map, UV layout
  stage2_before_after.png (with <before_render_dir>, the renders of the previous build) the stage-2 polish: the
                          concept, before / after fronts and 3/4s, close-up pairs, the in-game camera 3x crops with the
                          stage-1 blockout
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
    print("[valdris sheets] %s %dx%d %.2f MB" % (os.path.basename(path), img.width, img.height, os.path.getsize(path) / 1e6))


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
    tag = "Valdris stage 2 (polished)"
    met = json.load(open(R("review_metrics.json"))) if os.path.isfile(R("review_metrics.json")) else {}

    # ---- concept comparison -------------------------------------------------------------------------------------
    c = np.asarray(Image.open(cmask).convert("L")) > 127
    ys, xs = np.nonzero(c)
    con = Image.open(concept).convert("RGB").crop((xs.min() - 10, ys.min() - 10, xs.max() + 10, ys.max() + 10))
    res = {}
    for key, fn in (("bare_tpose", "frontsil.png"), ("armed_tpose", "armed_frontsil.png"), ("armed_pose45", "pose45_armed_frontsil.png")):
        if os.path.isfile(R(fn)):
            res[key] = iou(R(fn), cmask)
            met["front_iou_vs_concept_" + key] = round(res[key][0], 4)
            met["aspect_mesh_" + key] = round(res[key][2], 4)
    met["aspect_concept"] = round(res["bare_tpose"][3], 4) if res else None
    T = 520
    tiles = [(con, "approved concept (resolved front)"),
             (load(R("pose45_armed_toon_front.png")), "stage 2 armed, arms 45 deg fwd (review pose)"),
             (load(R("armed_toon_front.png")), "stage 2 armed, T-pose (rest pose)"),
             (load(R("toon_front.png")), "stage 2 bare, T-pose")]
    for key, lab in (("armed_pose45", "armed pose45"), ("armed_tpose", "armed T-pose"), ("bare_tpose", "bare T-pose")):
        if key in res:
            tiles.append((res[key][1], "%s silhouette IoU %.3f" % (lab, res[key][0])))
    sheet = Image.new("RGB", (4 * T, 2 * T + 74), BG)
    label(sheet, "%s vs the approved concept (silhouettes: yellow both, red concept only, green mesh only)" % tag, 24, (10, 9))
    for i, (im, t) in enumerate(tiles):
        if im is None:
            continue
        im = im.copy()
        im.thumbnail((T, T - 10), Image.LANCZOS)
        cell = Image.new("RGB", (T, T), BG)
        cell.paste(im, ((T - im.width) // 2, (T - im.height) // 2))
        label(cell, t, 17)
        sheet.paste(cell, ((i % 4) * T, 44 + (i // 4) * T))
    sheet_t = sheet
    save_small(sheet_t, os.path.join(od, "stage2_vs_concept.png"))

    # ---- turnaround --------------------------------------------------------------------------------------------------
    items = [(R("toon_%s.png" % v), "toon %s" % v) for v in ("front", "front34L", "sideL", "back", "back34R", "sideR")]
    items += [(R("clay_%s.png" % v), "clay %s" % v) for v in ("front", "front34L", "sideL", "back")]
    items += [(R("albedo_%s.png" % v), "albedo %s" % v) for v in ("front", "back")]
    save_small(tiles_sheet(items, 6, 400, "%s: production mesh without the weapon (toon review shading, clay, flat albedo)" % tag),
               os.path.join(od, "stage2_turnaround.png"))

    # ---- armed -------------------------------------------------------------------------------------------------------
    items = [(R("armed_toon_%s.png" % v), "armed T-pose %s" % v) for v in ("front", "front34R", "sideR", "back34L")]
    items += [(R("pose45_armed_toon_%s.png" % v), "armed pose45 %s" % v) for v in ("front", "front34R", "front34L")]
    items += [(R("armed_close_%s.png" % v), "cannon %s" % v.replace("_", " ")) for v in ("cannon_34", "cannon_top", "upper_34")]
    items += [(R("armed_section_%s.png" % v), "section (cannon cut on its axis) %s" % v) for v in ("top", "34", "front")]
    sf = met.get("sleeve_fit", {}).get("objects", [])
    panel = Image.new("RGB", (480, 480), BG)
    y = 12
    label(panel, "sleeve fit (grip frame, T-pose rest)", 18, (10, y))
    y += 34
    for r in sf:
        txt = "%s: %d in span, %d in the wall (max %.1f cm), %d out of the skin" % (
            r["object"], r["verts_in_cannon_span"], r["penetrating_verts"], 100 * r["max_penetration_m"],
            r.get("verts_poking_out_of_sleeve", 0))
        label(panel, txt, 15, (10, y))
        y += 26
    for line in ("bore: 9.8 cm sleeve, 9.4 cm rear cuff, 18 cm drum;", "outer skin: 13.4-16.6 cm over the forearm.",
                 "The polished MASSIVE arm (vambrace 24-27 cm across)", "is wider than the bore on purpose: it lies inside",
                 "the sleeve WALL, hidden; nothing pokes out of the", "outer skin. Weapon track: widen the sleeve (bore",
                 "~15 cm) for the concept's 29 cm fist arm.", "Hand hits: the open rest-pose THUMB (it folds",
                 "over the fingers in the grip) and the palm."):
        label(panel, line, 15, (10, y))
        y += 22
    items.append((panel, ""))
    save_small(tiles_sheet(items, 4, 480, "%s: with the colossus_cannon GLB (weapon track) on the recorded right-hand frame, identity transform" % tag),
               os.path.join(od, "stage2_armed.png"))

    # ---- in-game --------------------------------------------------------------------------------------------------------
    rows = []
    for prefix, lab in (("", "bare"), ("armed_", "armed T"), ("pose45_armed_", "armed pose45")):
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
    names = ("head_front", "head_34", "head_side", "torso_front", "anvil_34", "pauldron_34", "arm_34", "hand_top", "hips_34",
             "legs_34", "boot_34", "cape_back", "cape_34")
    save_small(tiles_sheet([(R("close_%s.png" % n), n.replace("_", " ")) for n in names], 5, 480, "%s: close-ups (toon review shading)" % tag),
               os.path.join(od, "stage2_closeups.png"))
    names = ("body_front", "body_back", "shoulder", "elbow_forearm", "hand", "hip_knee", "knee", "neck_face", "face", "pauldron",
             "anvil_torso", "arm_plates", "legs_plates", "beard", "cape")
    save_small(tiles_sheet([(R("wire_%s.png" % n), n.replace("_", " ")) for n in names], 5, 440,
                           "%s: topology (the under-suit body alone for the joints; the parts)" % tag), os.path.join(od, "stage2_wireframe.png"))

    # ---- textures ----------------------------------------------------------------------------------------------------------
    S = 900
    ims = [Image.open(os.path.join(texdir, "valdris_%s.png" % n)).convert("RGB") for n in ("basecolor", "emissive", "normal")]
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

    # ---- before / after (the stage-2 polish) ------------------------------------------------------------------------------
    if len(argv) > 7 and os.path.isdir(argv[7]):
        before_after(argv[7], R, B, con, tag, od)

    with open(R("review_metrics.json"), "w", newline="\n") as f:
        json.dump(met, f, indent=1)
        f.write("\n")
    rj = os.path.join(od, "review.json")          # the review step's report: add this pass's IoU / aspect values
    if os.path.isfile(rj):
        rep = json.load(open(rj))
        rep.update({k: v for k, v in met.items() if k.startswith(("front_iou", "aspect_"))})
        with open(rj, "w", newline="\n") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    print("[valdris sheets] IoU", {k: v for k, v in met.items() if k.startswith("front_iou")})


def before_after(bd, R, B, con, tag, od):
    """The polish pass side by side: the previous build's renders (bd) vs this one, same cameras and shading."""
    P = lambda n: os.path.join(bd, n)  # noqa: E731
    GREEN, GREY = (140, 230, 140), (200, 200, 200)

    def cell(im, w, h, text, col=FG):
        c = Image.new("RGB", (w, h), BG)
        if im is not None:
            im = im.copy()
            if im.width > w or im.height > h - 4:
                im.thumbnail((w, h - 4), Image.LANCZOS)
            c.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        label(c, text, 17, fill=col)
        return c

    def zoom(path, k=3, cw=150, ch=120):
        im = load(path)
        if im is None:
            return None
        x0, y0 = (im.width - cw) // 2, (im.height - ch) // 2
        return im.crop((x0, y0, x0 + cw, y0 + ch)).resize((cw * k, ch * k), Image.NEAREST)
    W = 2400
    rows = []
    t = W // 5
    r1 = [cell(con, t, t, "approved concept")]
    for n, lab in (("toon_front.png", "front"), ("toon_front34L.png", "3/4")):
        r1.append(cell(load(P(n)), t, t, "BEFORE " + lab, GREY))
        r1.append(cell(load(R(n)), t, t, "AFTER " + lab, GREEN))
    rows.append(r1)
    t = W // 6
    pairs = ("pauldron_34", "arm_34", "anvil_34", "legs_34", "hand_top", "boot_34")
    for k in range(0, len(pairs), 3):
        r = []
        for n in pairs[k:k + 3]:
            r.append(cell(load(P("close_%s.png" % n)), t, t, "BEFORE " + n.replace("_", " "), GREY))
            r.append(cell(load(R("close_%s.png" % n)), t, t, "AFTER " + n.replace("_", " "), GREEN))
        rows.append(r)
    t = W // 4
    h = 380
    rows.append([cell(zoom(P("pose45_armed_ingame_22_toon.png")), t, h, "BEFORE in game 22 m, armed, 3x", GREY),
                 cell(zoom(R("pose45_armed_ingame_22_toon.png")), t, h, "AFTER in game 22 m, armed, 3x", GREEN),
                 cell(zoom(R("pose45_armed_ingame_22_toon34.png")), t, h, "AFTER yaw 35, 3x", GREEN),
                 cell(zoom(B("ingame_22_tex.png")), t, h, "stage-1 blockout 22 m, 3x", GREY)])
    rows.append([cell(load(P("pose45_armed_ingame_22_toon.png")), t, 270, "BEFORE 1:1", GREY),
                 cell(load(R("pose45_armed_ingame_22_toon.png")), t, 270, "AFTER 1:1", GREEN),
                 cell(load(R("pose45_armed_ingame_28_toon.png")), t, 270, "AFTER 28 m 1:1", GREEN),
                 cell(load(B("ingame_22_tex.png")), t, 270, "blockout 1:1", GREY)])
    heights = [max(c.height for c in r) for r in rows]
    sheet = Image.new("RGB", (W, 44 + sum(heights)), BG)
    label(sheet, "%s polish: BEFORE (the first stage-2 build) / AFTER, same cameras and Cycles-CPU toon review" % tag, 22, (10, 10))
    y = 44
    for r, hh in zip(rows, heights):
        x = 0
        for c in r:
            sheet.paste(c, (x, y))
            x += c.width
        y += hh
    save_small(sheet, os.path.join(od, "stage2_before_after.png"), palette=True)


if __name__ == "__main__":
    main(sys.argv[1:])
