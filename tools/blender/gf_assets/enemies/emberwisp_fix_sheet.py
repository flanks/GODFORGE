"""Emberwisp art-review fix: measure the review's numbers and draw the before / after sheet (PIL + numpy, no Blender).

    python emberwisp_fix_sheet.py --analyse DIR
        -> DIR/metrics.json (one metric-render set: `emberwisp.py -- --metrics-only`)
    python emberwisp_fix_sheet.py BEFORE_DIR AFTER_DIR [BEFORE_CROWD AFTER_CROWD] [BEFORE_TURN AFTER_TURN]
        -> art/enemies/emberwisp/reports/emberwisp_review_fix.png + emberwisp_review_fix.json

Each DIR holds the three metric passes per pose (toon preview on the Cinder floor, emission x1.6 alone, zones by
bone) rendered through the game camera at TRUE 1x pixel size from a shipped GLB; the pre-fix GLB is measured with
the same code. The review's two must-fix items, as numbers:
  * player gold: share of the wisp's rendered pixels within dE 20 of P1 gold #FFC940 (CIE76 and CIEDE2000; the
    target is none), and the glow share (pixels whose emissive x1.6 alone is lit; the target is 40 % or less);
  * mask: the width of the soot-bronze mask (the widest row of mask-head pixels that are dark and do not glow; it
    gives the review's "about 8 px" on the pre-fix file) against the flame's width (the mask-head plus the tongues
    and the hood, without the trailing tail); the target is about 45 %.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
PACK = os.path.join(ROOT, "art", "enemies", "emberwisp")
PLAYER_GOLD = "#FFC940"
DE_LIMIT = 20.0
GLOW_THRESH = 0.13        # emission-only render, sRGB max channel: an emissive texel of 0.1 x 1.6 (glow_faces' cut)
DARK_LUMA = 0.35          # the soot-bronze mask: mask-head pixels darker than this (sRGB luma) that do not glow
BG, PANEL, INK, SUB, GOLDTXT, BAD, GOOD = ((30, 27, 33), (46, 42, 50), (236, 230, 220), (170, 162, 150),
                                           (226, 196, 120), (235, 120, 110), (140, 210, 150))


# ---- colour science -------------------------------------------------------------------------------------------

def srgb_to_lab(rgb):
    """(N, 3) sRGB 0..1 -> CIELAB (D65)."""
    rgb = np.asarray(rgb, dtype=np.float64)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def de76(lab, ref):
    return np.linalg.norm(lab - ref[None], axis=1)


def de2000(lab, ref):
    """CIEDE2000 between every row of lab (N, 3) and one reference (3,)."""
    L1, a1, b1 = lab[:, 0], lab[:, 1], lab[:, 2]
    L2, a2, b2 = ref
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(cb7 / (cb7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    zero = (C1p * C2p) == 0
    dh = np.where(zero, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hbp = np.where(zero, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dth = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    cbp7 = Cbp ** 7
    Rc = 2 * np.sqrt(cbp7 / (cbp7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dth)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def hex01(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


GOLD_LAB = srgb_to_lab(hex01(PLAYER_GOLD)[None])[0]
LIVING = ("rest front", "rest 3/4", "drift", "flicker", "moving away")


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def zones(path):
    """Zone pass -> (H, W) labels: 0 background, 1 mask-head (body), 2 tail, 3 flame."""
    z = load(path)
    lab = np.full(z.shape[:2], 3, dtype=np.int8)
    lab[(z[..., 2] > 0.8) & (z[..., 0] < 0.2) & (z[..., 1] < 0.2)] = 0
    lab[(lab != 0) & (z.max(2) < 0.15)] = 1
    lab[(lab != 0) & (z.min(2) > 0.15) & (z.max(2) < 0.9)] = 2
    return lab


def bbox_w(mask):
    cols = np.nonzero(mask.any(0))[0]
    return int(cols[-1] - cols[0] + 1) if len(cols) else 0


def gold_near(rgb):
    lab = srgb_to_lab(rgb.reshape(-1, 3))
    return de76(lab, GOLD_LAB), de2000(lab, GOLD_LAB)


def analyse_pose(p):
    zl = zones(p["zone"])
    toon, emis = load(p["toon"]), load(p["emis"])
    wisp = zl > 0
    n = int(wisp.sum())
    d76, d00 = gold_near(toon[wisp])
    glow = emis.max(2) > GLOW_THRESH
    near = d76 < DE_LIMIT
    luma = toon @ np.array([0.2126, 0.7152, 0.0722])
    head = zl == 1
    body_flame = (zl == 1) | (zl == 3)
    # the soot-bronze mask as the player sees it: mask-head pixels that are dark and do not glow (the old glowing
    # break and gold edge strokes do not count); its width is the widest row of such pixels (a chord, so stray
    # dark pixels do not stretch it). This reproduces the review's "about 8 px" on the pre-fix file.
    soot = head & ~glow & (luma < DARK_LUMA)
    chord = int(soot.sum(1).max()) if soot.any() else 0
    fw = bbox_w(body_flame)
    flame_px = toon[zl == 3]
    med = np.median(flame_px, 0) if len(flame_px) else np.zeros(3)
    return {
        "label": p["label"], "wisp_px": n,
        "gold_de76_lt20_pct": round(100 * float(near.mean()), 2), "gold_de2000_lt20_pct": round(100 * float((d00 < DE_LIMIT).mean()), 2),
        "gold_de76_lt20_px": int(near.sum()), "min_de76": round(float(d76.min()), 1), "min_de2000": round(float(d00.min()), 1),
        "glow_pct": round(100 * float(glow[wisp].mean()), 1),
        "gold_near_glowing_pct": round(100 * float(glow[wisp][near].mean()), 1) if near.any() else 0.0,
        "mask_w_px": chord, "flame_w_px": fw, "wisp_w_px": bbox_w(wisp),
        "mask_to_flame_w_pct": round(100 * chord / max(1, fw), 1),
        "mask_head_zone_w_px": bbox_w(head), "soot_mask_px": int(soot.sum()),
        "flame_median": "#%02X%02X%02X" % tuple(int(round(c * 255)) for c in med),
    }


def analyse(d):
    idx = json.load(open(os.path.join(d, "renders.json"), encoding="utf-8"))
    poses = [analyse_pose(p) for p in idx["poses"]]
    keys = ("gold_de76_lt20_pct", "gold_de2000_lt20_pct", "glow_pct", "mask_to_flame_w_pct", "mask_w_px", "flame_w_px")
    out = {"glb": idx["glb"], "tag": idx["tag"], "px": idx["px"], "poses": poses,
           "worst": {"gold_de76_lt20_pct": max(p["gold_de76_lt20_pct"] for p in poses),
                     "gold_de2000_lt20_pct": max(p["gold_de2000_lt20_pct"] for p in poses),
                     "min_de76": min(p["min_de76"] for p in poses), "min_de2000": min(p["min_de2000"] for p in poses),
                     "glow_pct": max(p["glow_pct"] for p in poses),
                     "mask_to_flame_w_pct": min(p["mask_to_flame_w_pct"] for p in poses)},
           "mean": {k: round(float(np.mean([p[k] for p in poses])), 1) for k in keys},
           # the poses the wisp spends its life in (hovering, drifting, flickering), and its rest pose
           "mean_living": {k: round(float(np.mean([p[k] for p in poses if p["label"] in LIVING])), 1) for k in keys},
           "rest": {k: next(p[k] for p in poses if p["label"] == "rest front") for k in keys}}
    with open(os.path.join(d, "metrics.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
    return out


def image_gold_px(path):
    """Pixels of a whole render (e.g. the 40-copy horde) within dE 20 of the player gold."""
    im = load(path)
    d76, d00 = gold_near(im.reshape(-1, 3))
    return {"px": int(im.shape[0] * im.shape[1]), "de76_lt20": int((d76 < DE_LIMIT).sum()),
            "de2000_lt20": int((d00 < DE_LIMIT).sum())}


def summary(m):
    lines = ["%-12s %6s %6s %6s %6s %5s %5s %5s %s" % ("pose", "dE76%", "dE00%", "glow%", "mask%", "mask", "flame", "head", "flame median")]
    for p in m["poses"]:
        lines.append("%-12s %6.2f %6.2f %6.1f %6.1f %5d %5d %5d %s" % (
            p["label"], p["gold_de76_lt20_pct"], p["gold_de2000_lt20_pct"], p["glow_pct"], p["mask_to_flame_w_pct"],
            p["mask_w_px"], p["flame_w_px"], p["mask_head_zone_w_px"], p["flame_median"]))
    lines.append("worst %s" % json.dumps(m["worst"]))
    return "\n".join(lines)


# ---- the sheet -------------------------------------------------------------------------------------------------

def font(size, bold=False):
    for name in (("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def big(path, k):
    im = Image.open(path).convert("RGB")
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def marked(p, k):
    """The toon render greyed, with the pixels within dE 20 of the player gold in magenta (nearest k x)."""
    toon = load(p["toon"])
    zl = zones(p["zone"])
    d76, _ = gold_near(toon)
    near = (d76.reshape(toon.shape[:2]) < DE_LIMIT) & (zl > 0)
    g = (toon @ np.array([0.2126, 0.7152, 0.0722]))[..., None].repeat(3, 2) * 0.8
    g[near] = (1.0, 0.0, 1.0)
    im = Image.fromarray((g * 255).astype(np.uint8))
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def zone_tile(p, k):
    zl = zones(p["zone"])
    pal = np.array([(52, 48, 58), (20, 16, 14), (120, 110, 100), (226, 150, 90)], dtype=np.uint8)
    im = Image.fromarray(pal[zl])
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def sheet(before_dir, after_dir, crowd=None, turn=None):
    mb, ma = analyse(before_dir), analyse(after_dir)
    rb = json.load(open(os.path.join(before_dir, "renders.json"), encoding="utf-8"))["poses"]
    ra = json.load(open(os.path.join(after_dir, "renders.json"), encoding="utf-8"))["poses"]
    extra = {}
    if crowd:
        extra["crowd"] = {"before": image_gold_px(crowd[0]), "after": image_gold_px(crowd[1])}
    W, pad, K = 1600, 16, 3
    show = [i for i, p in enumerate(ra) if p["label"] in ("rest front", "rest 3/4", "drift", "flicker", "windup",
                                                          "moving away")]
    tile = 76 * K
    fx = [
        ("1  Player-colour clash. Worst pose within dE 20 of P1 gold #FFC940: %.1f %% -> %.1f %% (CIE76), %.1f %% -> %.1f %% "
         "(CIEDE2000); nearest pixel dE76 %.1f -> %.1f." % (mb["worst"]["gold_de76_lt20_pct"], ma["worst"]["gold_de76_lt20_pct"],
                                                           mb["worst"]["gold_de2000_lt20_pct"], ma["worst"]["gold_de2000_lt20_pct"],
                                                           mb["worst"]["min_de76"], ma["worst"]["min_de76"])),
        ("   Glow share (worst pose) %.0f %% -> %.0f %% (target 40 %% or less). The flame is re-ramped to dead ember "
         "#8A3A1E-#C8663A tongues; cold gold #D4B45A only next to the core; no pale band." % (mb["worst"]["glow_pct"],
                                                                                            ma["worst"]["glow_pct"])),
        ("2  Mask read. Soot-bronze mask width (widest row of dark, non-glowing mask pixels) at rest %d px -> %d px at 1x, "
         "%.0f %% -> %.0f %% of the flame width (target about 45 %%); hover / drift / flicker mean %.0f %% -> %.0f %%." % (
             mb["rest"]["mask_w_px"], ma["rest"]["mask_w_px"], mb["rest"]["mask_to_flame_w_pct"], ma["rest"]["mask_to_flame_w_pct"],
             mb["mean_living"]["mask_to_flame_w_pct"], ma["mean_living"]["mask_to_flame_w_pct"])),
        ("   The mask-head grew (r 0.15 -> 0.18 m), the flame roots moved behind it, the broken corner is a charred notch with "
         "no glow,",),
        ("   and one big gold eye slit is the only light on the mask. Windup, attack and the burst flare the flame wide by "
         "design.",),
        ("   dE is CIE76, which reproduces the review's 19 % at rest; CIEDE2000 is listed for reference only (it puts the "
         "faction's own cold gold #D4B45A at 9.3 from #FFC940).",),
    ]
    if crowd:
        fx.append(("   40-copy horde render (1x, 600 x 450, with 24 clinkers): pixels within dE 20 of #FFC940 %d -> %d (CIE76), "
                   "%d -> %d (CIEDE2000)." % (extra["crowd"]["before"]["de76_lt20"], extra["crowd"]["after"]["de76_lt20"],
                                              extra["crowd"]["before"]["de2000_lt20"], extra["crowd"]["after"]["de2000_lt20"])))
    # wrap the notes to the sheet width (continuation lines keep a small indent)
    meas = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    wrapped = []
    for line in fx:
        text = line if isinstance(line, str) else line[0]
        lead = text[:len(text) - len(text.lstrip())]
        words = text.lstrip().split(" ")
        cur = lead + words[0]
        for word in words[1:]:
            cand = cur + " " + word
            if meas.textlength(cand, font=font(15)) > W - 2 * pad:
                wrapped.append(cur)
                cur = "     " + word
            else:
                cur = cand
        wrapped.append(cur)
    fx = wrapped
    rows = [("Game camera (55 deg, 22 m view = 49 px/m), TRUE 1x pixels shown 3x nearest, Cinder floor + blob shadow",
             lambda p: big(p["toon"], K)),
            ("Pixels within dE 20 of the player gold #FFC940 in magenta (CIE76, same renders)", lambda p: marked(p, K)),
            ("Zones by bone at 1x (3x): mask-head black, flame orange, tail grey", lambda p: zone_tile(p, K))]
    table_h = 24 * (len(ra) + 2) + 10
    H = 64 + 24 * len(fx) + 14 + table_h + sum(30 + 2 * (tile + 22) + 8 for _ in rows) + 40
    crowd_imgs = None
    if crowd:
        box = (60, 30, 540, 330)
        crowd_imgs = [Image.open(c).convert("RGB").crop(box) for c in crowd]
        crowd_imgs = [im.resize((im.width * 3 // 2, im.height * 3 // 2), Image.NEAREST) for im in crowd_imgs]
        H += 30 + crowd_imgs[0].height + 26
    turn_imgs = None
    if turn:
        turn_imgs = [Image.open(t).convert("RGB") for t in turn]
        th = 320
        turn_imgs = [im.resize((im.width * th // im.height, th), Image.LANCZOS) for im in turn_imgs]
        H += 30 + th + 26
    s = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(s)
    d.text((pad, 12), "Emberwisp - art review fixes (5/10 must-fix list), before and after", font=font(28, True), fill=GOLDTXT)
    d.text((pad, 44), "the same metric code on the pre-fix and the fixed shipped GLB (emberwisp.py -- --metrics-only); "
                      "toon preview = the review's engine-like ramp, rim and ink, emissive x1.6", font=font(14), fill=SUB)
    y = 66
    for line in fx:
        d.text((pad, y), line if isinstance(line, str) else line[0], font=font(15), fill=INK)
        y += 24
    y += 10
    # metric table
    cols = [("pose", 0), ("dE76<20 %", 150), ("dE2000<20 % (ref.)", 290), ("glow %", 450), ("mask / flame width %", 560),
            ("mask px", 760), ("flame px", 860), ("flame median", 990)]
    for name, x in cols:
        d.text((pad + x, y), name, font=font(14, True), fill=SUB)
    d.text((pad + 1150, y), "before -> after", font=font(14, True), fill=SUB)
    y += 24
    for pb, pa in zip(mb["poses"], ma["poses"]):
        vals = [pb["label"],
                "%.1f -> %.1f" % (pb["gold_de76_lt20_pct"], pa["gold_de76_lt20_pct"]),
                "%.1f -> %.1f" % (pb["gold_de2000_lt20_pct"], pa["gold_de2000_lt20_pct"]),
                "%.0f -> %.0f" % (pb["glow_pct"], pa["glow_pct"]),
                "%.0f -> %.0f" % (pb["mask_to_flame_w_pct"], pa["mask_to_flame_w_pct"]),
                "%d -> %d" % (pb["mask_w_px"], pa["mask_w_px"]),
                "%d -> %d" % (pb["flame_w_px"], pa["flame_w_px"]),
                "%s -> %s" % (pb["flame_median"], pa["flame_median"])]
        ok = [None, pa["gold_de76_lt20_pct"] == 0, None, pa["glow_pct"] <= 40,
              True if pa["mask_to_flame_w_pct"] >= 42 else None, None, None, None]
        for (name, x), v, good in zip(cols, vals, ok):
            d.text((pad + x, y), v, font=font(14), fill=INK if good is None else (GOOD if good else BAD))
        for k, hx in enumerate((pb["flame_median"], pa["flame_median"])):
            d.rectangle([pad + 1150 + 40 * k, y + 2, pad + 1150 + 40 * k + 30, y + 16], fill=hx)
        y += 24
    y += 10
    for label, fn in rows:
        d.text((pad, y + 4), label, font=font(16, True), fill=INK)
        y += 30
        for tag, rr in (("BEFORE", rb), ("AFTER", ra)):
            x = pad
            d.text((x, y), tag, font=font(13, True), fill=SUB if tag == "BEFORE" else GOLDTXT)
            for i in show:
                im = fn(rr[i])
                s.paste(im, (x, y + 18))
                d.text((x + 4, y + 20), rr[i]["label"], font=font(12), fill=SUB)
                x += tile + 10
            y += tile + 22
        y += 8
    if crowd_imgs:
        d.text((pad, y + 4), "The 40-copy horde with 24 clinkers at TRUE 1x (crop, shown 1.5x nearest): before | after",
               font=font(16, True), fill=INK)
        y += 30
        s.paste(crowd_imgs[0], (pad, y))
        s.paste(crowd_imgs[1], (pad * 2 + crowd_imgs[0].width, y))
        y += crowd_imgs[0].height + 26
    if turn_imgs:
        d.text((pad, y + 4), "Turnaround 3/4 front (toon preview): before | after", font=font(16, True), fill=INK)
        y += 30
        s.paste(turn_imgs[0], (pad, y))
        s.paste(turn_imgs[1], (pad * 2 + turn_imgs[0].width, y))
    out = os.path.join(PACK, "reports", "emberwisp_review_fix.png")
    s.save(out, optimize=True)
    rep = {"before": {k: mb[k] for k in ("worst", "mean", "poses")}, "after": {k: ma[k] for k in ("worst", "mean", "poses")},
           "method": __doc__.strip().splitlines()[-9:], **extra}
    with open(os.path.join(PACK, "reports", "emberwisp_review_fix.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rep, fh, indent=1)
    print("wrote", out)
    print("BEFORE\n" + summary(mb))
    print("AFTER\n" + summary(ma))
    if crowd:
        print("crowd", json.dumps(extra["crowd"]))


def main():
    a = sys.argv[1:]
    if a and a[0] == "--analyse":
        m = analyse(a[1])
        print(summary(m))
        return
    crowd = a[2:4] if len(a) >= 4 else None
    turn = a[4:6] if len(a) >= 6 else None
    sheet(a[0], a[1], crowd, turn)


if __name__ == "__main__":
    main()
