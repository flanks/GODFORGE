"""Review sheets for stage-2 production meshes (companion of tools/blender/gf_hero/s2_review.py).

Adapted from tools/comfy/blockout_sheets.py (grid / label / <2 MB saving / concept-silhouette IoU). Needs
PIL + numpy, so run it with ComfyUI's standalone python:

  hero:   <comfy-python> tools/comfy/stage2_sheets.py <render_dir> <report_dir> <concept.png> <concept_mask.png>
                  <basecolor.png> <emissive.png> [--blockout <stage1 render dir> <stage1 stem>] [--tag <title>]
  weapon: <comfy-python> tools/comfy/stage2_sheets.py --weapon <render_dir> <report_dir> <basecolor.png> <emissive.png>
                  [--tag <title>]

Hero sheets: stage2_turnaround.png (bare), stage2_armed.png (with the signature weapon attached, when rendered),
stage2_closeups.png, stage2_wireframe.png, stage2_ingame.png (bare + armed rows, stage-1 blockout beside them),
stage2_textures.png, stage2_vs_concept.png. The concept IoU is measured on the armed silhouette (the approved
concept shows the gauntlets) and the bare one; both go into <render_dir>/review_metrics.json.
Weapon sheets: stage2_weapon.png (open + fist close-ups, attach frame), stage2_weapon_wireframe.png,
stage2_weapon_textures.png.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blockout_sheets import BG, bbox_mask, label, load, save_small  # noqa: E402


def tiles_sheet(items, cols, tile, title):
    items = [(p, t) for p, t in items if os.path.isfile(p)]
    rows = max(1, (len(items) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * tile, rows * tile + 44), BG)
    label(sheet, title, 26, (10, 8))
    for i, (path, text) in enumerate(items):
        im = load(path).convert("RGB").resize((tile, tile), Image.LANCZOS)
        label(im, text, 19)
        sheet.paste(im, ((i % cols) * tile, 44 + (i // cols) * tile))
    return sheet


def texture_sheet(basec, emis, segs_path, title, out):
    b = Image.open(basec).convert("RGB")
    e = Image.open(emis).convert("RGB")
    S = 1024
    bs, es = b.resize((S, S), Image.LANCZOS), e.resize((S, S), Image.LANCZOS)
    uv = bs.copy()
    d = ImageDraw.Draw(uv)
    for x0, y0, x1, y1 in np.load(segs_path):
        d.line([(x0 * S, (1 - y0) * S), (x1 * S, (1 - y1) * S)], fill=(250, 250, 240), width=1)
    sheet = Image.new("RGB", (3 * S, S + 50), BG)
    label(sheet, "%s: base colour %dx%d | emissive %dx%d | UV layout over base colour" % (title, b.width, b.height, e.width, e.height), 26, (10, 10))
    for i, im in enumerate((bs, es, uv)):
        sheet.paste(im, (i * S, 50))
    save_small(sheet, out)


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


def ingame_sheet(rows, title, out, zoom_cols):
    Z, CW, CH = 3, 150, 120
    ncol = max(len(r) for r in rows)
    rh = max(256, CH * Z)
    sheet = Image.new("RGB", (ncol * 256 + len(zoom_cols) * CW * Z, 44 + len(rows) * rh), BG)
    label(sheet, title, 22, (10, 8))
    for r, row in enumerate(rows):
        for c, (p, t) in enumerate(row):
            im = load(p)
            if im is None:
                continue
            im = im.convert("RGB")
            tile = im.copy()
            label(tile, t, 15)
            sheet.paste(tile, (c * 256, 44 + r * rh))
            if c in zoom_cols:
                k = zoom_cols.index(c)
                x0, y0 = (256 - CW) // 2, (256 - CH) // 2
                z = im.crop((x0, y0, x0 + CW, y0 + CH)).resize((CW * Z, CH * Z), Image.NEAREST)
                sheet.paste(z, (ncol * 256 + k * CW * Z, 44 + r * rh))
    save_small(sheet, out)


def hero(argv):
    rd, od, concept, cmask, basec, emis = argv[:6]
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "stage 2"
    bdir = bstem = None
    if "--blockout" in argv:
        i = argv.index("--blockout")
        bdir, bstem = argv[i + 1], argv[i + 2]
    os.makedirs(od, exist_ok=True)
    R = lambda n: os.path.join(rd, n)  # noqa: E731
    items = [(R("toon_%s.png" % v), "toon %s" % v) for v in ("front", "front34L", "sideL", "back", "back34R", "sideR")]
    items += [(R("clay_%s.png" % v), "clay %s" % v) for v in ("front", "front34L", "sideL", "back")]
    items += [(R("albedo_%s.png" % v), "albedo %s" % v) for v in ("front", "back")]
    save_small(tiles_sheet(items, 6, 400, "%s: production body, bare fists (toon review shading, clay, flat albedo)" % tag),
               os.path.join(od, "stage2_turnaround.png"))
    armed = os.path.isfile(R("armed_toon_front.png"))
    if armed:
        items = [(R("armed_toon_%s.png" % v), "armed %s" % v) for v in ("front", "front34L", "sideL", "back")]
        items += [(R("armed_close_%s.png" % v), "armed %s" % v.replace("_", " ")) for v in ("gauntlet_34", "gauntlet_top", "upper_34")]
        items += [(R("toon_front34L.png"), "bare 3/4 (same body)")]
        save_small(tiles_sheet(items, 4, 480, "%s: with the anvil_gauntlets weapon on its weapon_L / weapon_R sockets" % tag),
                   os.path.join(od, "stage2_armed.png"))
    names = ("head_front", "head_34", "head_side", "torso_front", "arm_34", "hand_34", "skirt_34", "skirt_back", "legs_34")
    save_small(tiles_sheet([(R("close_%s.png" % n), n.replace("_", " ")) for n in names], 3, 520,
                           "%s: close-ups (toon review shading)" % tag), os.path.join(od, "stage2_closeups.png"))
    names = ("body_front", "body_back", "shoulder", "elbow_forearm", "hand", "hip_knee", "knee", "neck_face", "face",
             "skirt", "head_parts", "legs_parts")
    save_small(tiles_sheet([(R("wire_%s.png" % n), n.replace("_", " ")) for n in names], 4, 450,
                           "%s: topology (body alone for the joints; parts)" % tag), os.path.join(od, "stage2_wireframe.png"))
    rows = []
    for prefix, lab in (("", "bare"), ("armed_", "armed")):
        if prefix and not armed:
            continue
        for vh in (22, 28):
            row = [(R("%singame_%d_%s.png" % (prefix, vh, look)), "%s %s %dm" % (lab, look, vh)) for look in ("toon", "sil", "toon34")]
            if bdir:
                row.append((os.path.join(bdir, "%s_ingame_%d_tex.png" % (bstem, vh)), "stage-1 blockout %dm" % vh))
            rows.append(row)
    ingame_sheet(rows, "%s: in-game camera (ortho 55 deg, FixedVertical 22 m / 28 m, true 1080p pixels) + 3x zoom" % tag,
                 os.path.join(od, "stage2_ingame.png"), [0, 3] if bdir else [0])
    texture_sheet(basec, emis, R("uv_segments.npy"), tag, os.path.join(od, "stage2_textures.png"))
    met = json.load(open(R("review_metrics.json"))) if os.path.isfile(R("review_metrics.json")) else {}
    v_bare, ov_bare, a_m, a_c = iou(R("frontsil.png"), cmask)
    met["front_iou_vs_concept_bare"] = round(v_bare, 4)
    met["aspect_concept"] = round(a_c, 4)
    met["aspect_mesh_bare"] = round(a_m, 4)
    ov, v_main, lab_main = ov_bare, v_bare, "bare"
    if armed:
        v_arm, ov_arm, a_m2, _ = iou(R("armed_frontsil.png"), cmask)
        met["front_iou_vs_concept_armed"] = round(v_arm, 4)
        met["aspect_mesh_armed"] = round(a_m2, 4)
        ov, v_main, lab_main = ov_arm, v_arm, "armed"
    T = 600
    c = np.asarray(Image.open(cmask).convert("L")) > 127
    ys, xs = np.nonzero(c)
    con = Image.open(concept).convert("RGB").crop((xs.min() - 10, ys.min() - 10, xs.max() + 10, ys.max() + 10))
    tiles = [(con, "approved concept"),
             (Image.open(R("armed_toon_front.png" if armed else "toon_front.png")).convert("RGB"), "stage 2 %s front" % lab_main),
             (Image.open(R("toon_front.png")).convert("RGB"), "stage 2 bare front"),
             (ov, "%s silhouette IoU %.3f (yellow both, red concept only, green mesh only)" % (lab_main, v_main))]
    sheet = Image.new("RGB", (4 * T, T + 44), BG)
    label(sheet, "%s vs the approved concept" % tag, 26, (10, 8))
    for i, (im, t) in enumerate(tiles):
        im = im.copy()
        im.thumbnail((T, T), Image.LANCZOS)
        cell = Image.new("RGB", (T, T), BG)
        cell.paste(im, ((T - im.width) // 2, (T - im.height) // 2))
        label(cell, t, 17)
        sheet.paste(cell, (i * T, 44))
    save_small(sheet, os.path.join(od, "stage2_vs_concept.png"))
    with open(R("review_metrics.json"), "w", newline="\n") as f:
        json.dump(met, f, indent=1)
        f.write("\n")
    print("[stage2_sheets] IoU bare %.4f%s" % (v_bare, (" armed %.4f" % met["front_iou_vs_concept_armed"]) if armed else ""))


def weapon(argv):
    rd, od, basec, emis = argv[:4]
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else "weapon stage 2"
    os.makedirs(od, exist_ok=True)
    R = lambda n: os.path.join(rd, n)  # noqa: E731
    names = ("open_front", "open_top", "open_34", "open_back34", "open_under", "pair_front", "fist_front", "fist_34",
             "fist_knuckles", "fist_top")
    items = [(R("w_close_%s.png" % n), n.replace("_", " ")) for n in names]
    items += [(R("w_frame_open.png"), "attach frame (open): X red, Y green = fingers, Z blue = back of hand"),
              (R("w_frame_fist.png"), "attach frame (fist)")]
    save_small(tiles_sheet(items, 4, 450, "%s: open (concept) and closed-fist variants, socket frame at the palm centre" % tag),
               os.path.join(od, "stage2_weapon.png"))
    items = [(R("w_wire_%s.png" % n), n.replace("_", " ")) for n in ("open", "fist", "open_under")]
    save_small(tiles_sheet(items, 3, 520, "%s: topology (rigid closed pieces)" % tag), os.path.join(od, "stage2_weapon_wireframe.png"))
    texture_sheet(basec, emis, R("uv_segments.npy"), tag, os.path.join(od, "stage2_weapon_textures.png"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--weapon":
        weapon(a[1:])
    else:
        hero(a)
