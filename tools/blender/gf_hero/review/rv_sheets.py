"""PIL sheets for the review renders (any Python with Pillow + numpy).

  python rv_sheets.py closeups <render_dir> <out_dir>          one 4x2 sheet per (clip, frame)
  python rv_sheets.py board <render_dir> <out.png>             the game-camera board at TRUE pixel size + silhouette stats
  python rv_sheets.py strips <old_dir> <new_dir> <out_dir>     before row over after row per clip and view
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ORDER = ["body34", "bodyside", "armL", "armR", "legL", "legR", "hips_front", "hips_back"]


def closeups(src, out):
    os.makedirs(out, exist_ok=True)
    groups = {}
    for r in json.load(open(os.path.join(src, "renders.json"))):
        if "view" in r and not r.get("strip"):
            groups.setdefault((r["clip"], r["frame"], r.get("tag", "")), []).append(r)
    for (clip, fr, tag), rs in groups.items():
        ims = {r["view"]: Image.open(r["png"]).convert("RGB") for r in rs}
        w = next(iter(ims.values())).width
        sheet = Image.new("RGB", (4 * w, 2 * (w + 14) + 20), (16, 16, 18))
        d = ImageDraw.Draw(sheet)
        d.text((4, 4), "%s  frame %d  -  %s" % (clip, fr, tag), fill=(255, 220, 120))
        for k, v in enumerate(ORDER):
            x, y = (k % 4) * w, 20 + (k // 4) * (w + 14)
            d.text((x + 3, y + 1), v, fill=(230, 230, 230))
            sheet.paste(ims[v], (x, y + 14))
        p = os.path.join(out, "%s_f%03d.png" % (clip.replace("@", "_"), fr))
        sheet.save(p)
        print(p)


def board(src, out):
    R = [r for r in json.load(open(os.path.join(src, "renders.json"))) if "H" in r]
    rows, cols, cell = [], [], {}
    for r in R:
        rk = (r["clip"], r["frame"], r["tag"])
        ck = (r["H"], r["yaw"], bool(r.get("silhouette")))
        if rk not in rows:
            rows.append(rk)
        if ck not in cols:
            cols.append(ck)
        cell[(rk, ck)] = r["png"]
    cols = [c for c in cols if not c[2]] + [c for c in cols if c[2]]
    W = max(Image.open(p).width for p in cell.values())
    lab = 118
    sheet = Image.new("RGB", (lab + len(cols) * (W + 4), 16 + len(rows) * (W + 4)), (10, 10, 12))
    dr = ImageDraw.Draw(sheet)
    for j, c in enumerate(cols):
        dr.text((lab + j * (W + 4) + 2, 2), "%dm yaw%d%s" % (c[0], c[1], " SIL" if c[2] else ""), fill=(230, 230, 230))
    stats = []
    for i, rk in enumerate(rows):
        dr.text((2, 16 + i * (W + 4) + 4), "%s\n%s f%d" % (rk[2], rk[0].split("_", 1)[-1], rk[1]), fill=(255, 220, 120))
        for j, c in enumerate(cols):
            p = cell.get((rk, c))
            if not p:
                continue
            im = Image.open(p).convert("RGB")
            if c[2]:
                a = np.asarray(im).astype(int)
                g = (a[:, :, 0] > 200) & (a[:, :, 1] > 60) & (a[:, :, 2] < 120)      # gauntlets: flat orange
                b = (np.abs(a[:, :, 0] - a[:, :, 1]) < 20) & (a[:, :, 0] > 30)       # everything else: flat grey
                hero = g | b
                ys = np.where(hero.any(1))[0]
                stats.append({"pose": rk[2], "clip": rk[0], "frame": rk[1], "view_height_m": c[0], "yaw": c[1],
                              "hero_px": int(hero.sum()), "gauntlet_share": round(float(g.sum()) / max(int(hero.sum()), 1), 3),
                              "height_px": int(ys.max() - ys.min() + 1) if len(ys) else 0})
            sheet.paste(im, (lab + j * (W + 4), 16 + i * (W + 4)))
    sheet.save(out)
    with open(os.path.splitext(out)[0] + "_silhouettes.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, indent=1)
    print(out, sheet.size)


def strips(old, new, out):
    os.makedirs(out, exist_ok=True)
    clips = {}
    for r in json.load(open(os.path.join(new, "renders.json"))):
        if r.get("strip"):
            clips.setdefault((r["clip"], r["view"]), []).append(r["frame"])
    for (clip, view), frames in clips.items():
        frames = sorted(set(frames))
        tag = clip.replace("@", "_")
        ims = [[Image.open(os.path.join(d, "strip_%s_%s_f%03d.png" % (tag, view, f))).convert("RGB") for f in frames]
               for d in (old, new)]
        w = ims[0][0].width
        per = min(len(frames), 9)
        nrow = (len(frames) + per - 1) // per
        sheet = Image.new("RGB", (per * w, nrow * 2 * (w + 12) + 18), (14, 14, 16))
        dr = ImageDraw.Draw(sheet)
        dr.text((4, 3), "%s  %s   top: before   bottom: after" % (clip, view), fill=(255, 220, 120))
        for k, f in enumerate(frames):
            r, c = divmod(k, per)
            for j in range(2):
                x, y = c * w, 18 + (r * 2 + j) * (w + 12)
                sheet.paste(ims[j][k], (x, y + 12))
                dr.text((x + 3, y), ("before" if j == 0 else "AFTER") + " f%d" % f,
                        fill=(200, 200, 200) if j == 0 else (140, 255, 140))
        p = os.path.join(out, "cmp_%s_%s.png" % (tag, view))
        sheet.save(p)
        print(p)


if __name__ == "__main__":
    {"closeups": closeups, "board": board, "strips": strips}[sys.argv[1]](*sys.argv[2:])
