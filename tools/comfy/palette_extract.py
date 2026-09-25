"""Stage 0: measure a hero's palette from the approved front concept and draw the colour callouts.

  <comfy-python> tools/comfy/palette_extract.py art/characters/<key>/palette_spec.json

<comfy-python> = D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe (has PIL + numpy).

The spec names the concept, and per material a few sample boxes plus an HSV filter (see the
"about" field in art/characters/brax/palette_spec.json). For every material the tool keeps the
pixels inside its boxes that pass the filter (flat background removed), sorts them by CIELAB L*
and reports three tones: shadow / base / highlight (emissive materials: rim / hot / core), each
the median colour of the pixels within +-5 percentile of the requested lightness percentile.
Deterministic: no clustering, no randomness, same input -> same bytes.

Writes (paths from the spec's "outputs"):
  palette.json      the measured swatches, silhouette shares, contrast checks, source sha256
  color_script.png  labelled callout sheet: concept with numbered sample boxes, swatch ramps,
                    value key, colour budget, readability checks
  overlay PNG       the exact pixels each swatch sampled (false colour), to audit the boxes

These are MEASUREMENTS of approved art, not new design: the painted colour-script sheet (lighting
states, Meltdown, biome moods) is a separate stage-0 sheet that a human approves.
"""
import datetime
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

import gf_img as G

TONE_NAMES = ["shadow", "base", "highlight"]
TONES = [15, 50, 90]
# false colours for the audit overlay (index = swatch number - 1)
AUDIT = [(255, 150, 110), (120, 120, 255), (255, 255, 0), (0, 230, 0), (255, 0, 255), (0, 235, 235),
         (255, 255, 255), (230, 30, 30), (180, 100, 20), (30, 120, 255), (255, 210, 0), (0, 255, 160),
         (210, 200, 130), (255, 120, 200), (140, 255, 90)]


def biomes():
    """(key, name, ground, accent, fog) from assets/content/biomes.ron, read-only; [] if unparsable."""
    path = os.path.join(G.ROOT, "assets", "content", "biomes.ron")
    try:
        src = open(path, encoding="utf-8").read()
    except OSError:
        return []
    pat = re.compile(r'key:\s*"(\w+)",\s*name:\s*"([^"]+)".*?palette:\s*\("(#\w{6})",\s*"(#\w{6})",\s*"(#\w{6})"\)', re.S)
    return [m.groups() for m in pat.finditer(src)]


def sample(sw, rgb, hsv, dist):
    h, s, v = hsv
    m = np.zeros(dist.shape, bool)
    for x0, y0, x1, y1 in sw["boxes"]:
        m[y0:y1, x0:x1] = True
    m &= dist > 14.0
    if "hue" in sw:
        h0, h1 = sw["hue"]
        m &= ((h >= h0) & (h <= h1)) if h0 <= h1 else ((h >= h0) | (h <= h1))
    s0, s1 = sw.get("sat", [0.0, 1.0])
    v0, v1 = sw.get("val", [0.0, 1.0])
    m &= (s >= s0) & (s <= s1) & (v >= v0) & (v <= v1)
    if sw.get("drop_hot"):
        m &= ~((s > 0.72) & (v > 0.85))     # lava-lit pixels inside a non-emissive material's box
    return m


def tones_of(px_rgb, pcts):
    L = G.srgb_to_lab(px_rgb)[..., 0]
    out = []
    for p in pcts:
        lo, hi = np.percentile(L, max(0, p - 5)), np.percentile(L, min(100, p + 5))
        band = px_rgb[(L >= lo) & (L <= hi)]
        out.append(np.median(band, axis=0))
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec_path = G.absp(argv[1])
    spec = json.load(open(spec_path, encoding="utf-8"))
    concept = G.absp(spec["concept"])
    rgb = np.asarray(Image.open(concept).convert("RGB"))
    H, W, _ = rgb.shape
    bg = G.background_rgb(rgb)
    dist = np.sqrt(((rgb.astype(np.float32) - bg) ** 2).sum(-1))
    hsv = G.hsv_arrays(rgb)
    fig = G.figure_mask(rgb, bg)

    swatches, masks = [], []
    for i, sw in enumerate(spec["swatches"]):
        m = sample(sw, rgb, hsv, dist)
        px = rgb[m].astype(np.float64)
        if len(px) < 30:
            raise SystemExit("swatch %s: only %d pixels passed its filter - fix its boxes" % (sw["key"], len(px)))
        names = sw.get("tone_names", TONE_NAMES)
        pcts = sw.get("tones", TONES)
        tvals = tones_of(px, pcts)
        rec = {
            "n": i + 1, "key": sw["key"], "label": sw["label"], "emissive": bool(sw.get("emissive")),
            "tones": {nm: G.rgb_to_hex(t) for nm, t in zip(names, tvals)},
            "tone_percentiles_Lstar": dict(zip(names, pcts)),
            "base_lab": [round(float(c), 1) for c in G.srgb_to_lab(tvals[1])],
            "pixels_sampled": int(len(px)),
            "note": sw.get("note", ""),
        }
        swatches.append(rec)
        masks.append(m)

    # silhouette share: every figure pixel goes to the nearest tone (CIELAB); ink/deep shadow apart
    lab = G.srgb_to_lab(rgb[fig].astype(np.float64))
    refs, owner = [], []
    for k, sw in enumerate(swatches):
        for hx in sw["tones"].values():
            refs.append(G.srgb_to_lab(np.array(G.hex_to_rgb(hx), dtype=np.float64)))
            owner.append(k)
    refs = np.array(refs)
    d2 = ((lab[:, None, :] - refs[None, :, :]) ** 2).sum(-1)
    cls = np.array(owner)[d2.argmin(1)]
    ink = lab[:, 0] < 8.0
    total = float(len(lab))
    for k, sw in enumerate(swatches):
        sw["silhouette_share"] = round(float(((cls == k) & ~ink).sum()) / total, 4)
    ink_share = round(float(ink.sum()) / total, 4)

    # checks
    by = {s["key"]: s for s in swatches}

    def dE(a, b):
        return round(float(np.linalg.norm(np.array(a) - np.array(b))), 1)

    bg_lab = G.srgb_to_lab(bg.astype(np.float64))
    checks = {"notes": "dE = CIELAB dE76 between base tones; dL = difference in L* (value), the part a toon ramp and a small screen keep."}
    if "bronze" in by and "scale_plates" in by:
        checks["dE_bronze_vs_scale_plates"] = dE(by["bronze"]["base_lab"], by["scale_plates"]["base_lab"])
    if "lava_glow" in by and spec.get("content_color"):
        cc = G.srgb_to_lab(np.array(G.hex_to_rgb(spec["content_color"]), dtype=np.float64))
        checks["dE_content_color_vs_lava_hot"] = dE(cc, by["lava_glow"]["base_lab"])
    checks["dL_vs_sheet_background"] = {s["key"]: round(s["base_lab"][0] - float(bg_lab[0]), 1) for s in swatches}
    probe = [k for k in ("gauntlet_rock", "skin", "bronze", "teal_sash", "lava_glow") if k in by]
    bl = []
    for key, name, ground, accent, fog in biomes():
        g = G.srgb_to_lab(np.array(G.hex_to_rgb(ground), dtype=np.float64))
        a = G.srgb_to_lab(np.array(G.hex_to_rgb(accent), dtype=np.float64))
        bl.append({"biome": key, "name": name, "ground": ground, "accent": accent,
                   "dL_vs_ground": {k: round(by[k]["base_lab"][0] - float(g[0]), 1) for k in probe},
                   "dE_lava_hot_vs_biome_accent": dE(by["lava_glow"]["base_lab"], a) if "lava_glow" in by else None})
    checks["biomes"] = bl
    checks["biomes_note"] = ("ground = the biome's albedo tint from biomes.ron (unlit); the lit floor in game is lighter. "
                             "Treat these as worst-case value contrast, not a render.")

    src_sha = G.sha256(concept)
    out = {
        "character": spec["character"],
        "generated_by": "tools/comfy/palette_extract.py",
        "spec": G.rel(spec_path),
        "source": {"path": G.rel(concept), "sha256": src_sha, "size": [W, H]},
        "generated": datetime.date.today().isoformat(),
        "kind": "measured from approved art (stage 0 derived data, not a new design)",
        "method": "per swatch: pixels in the sample boxes passing the HSV filter, flat background removed; tones = median colour of the pixels within +-5 percentile of the named CIELAB L* percentile",
        "sheet_background": G.rgb_to_hex(bg),
        "content_color": spec.get("content_color"),
        "swatches": swatches,
        "ink_and_deep_shadow_share": ink_share,
        "checks": checks,
    }
    outs = spec["outputs"]
    with open(G.absp(outs["palette"]), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    audit_overlay(rgb, masks, spec, G.absp(outs["overlay"]))
    color_script(rgb, fig, spec, out, G.absp(outs["color_script"]))
    for s in swatches:
        print("[palette] %2d %-14s %s  n=%6d  share %.1f%%" % (s["n"], s["key"], " ".join(s["tones"].values()),
                                                              s["pixels_sampled"], 100 * s["silhouette_share"]))
    print("[palette] checks:", json.dumps({k: v for k, v in checks.items() if k.startswith("dE")}))
    print("[palette] wrote", outs["palette"], outs["color_script"], outs["overlay"])
    return 0


def audit_overlay(rgb, masks, spec, path):
    ov = (rgb.astype(np.float32) * 0.35).astype(np.uint8)
    for i, m in enumerate(masks):
        ov[m] = AUDIT[i % len(AUDIT)]
    im = Image.fromarray(ov)
    d = ImageDraw.Draw(im)
    for i, sw in enumerate(spec["swatches"]):
        for (x0, y0, x1, y1) in sw["boxes"]:
            d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=AUDIT[i % len(AUDIT)], width=1)
        x0, y0 = sw["boxes"][0][:2]
        d.rectangle([x0, y0 - 16, x0 + 20, y0 - 1], fill=(0, 0, 0))
        G.text(d, (x0 + 3, y0 - 15), str(i + 1), 12, True, AUDIT[i % len(AUDIT)])
    G.text(d, (16, 12), "%s - pixels sampled per swatch (false colour); boxes from %s" % (spec["character"], os.path.basename(spec["outputs"]["palette"]).replace("palette.json", "palette_spec.json")), 16)
    im.save(path, optimize=True)


def color_script(rgb, fig, spec, pal, path):
    Wd, Hd = 2400, 1320
    sheet, d = G.new_sheet(Wd, Hd)
    sw = pal["swatches"]
    cream, grey = (236, 228, 210), (150, 146, 140)
    # header
    G.text(d, (40, 64), "BRAX", 50, True, (255, 150, 90), anchor="ls")
    G.text(d, (40 + G.text_w("BRAX", 50, True) + 18, 64), "The Furnace-Born  -  colour callouts", 32, True, cream, anchor="ls")
    G.text(d, (40, 98), "Measured from the approved front concept (%s). Stage-0 derived data: it records the approved colours, it is not "
                        "the painted colour-script sheet (pending)." % pal["source"]["path"], 17, False, grey, anchor="ls")
    # header chips: sheet background, content colour
    x = Wd - 40
    for label, hx in (("content colour (characters.csv)", pal["content_color"]), ("sheet background", pal["sheet_background"])):
        if not hx:
            continue
        tw = G.text_w(label + "  " + hx, 16)
        d.rectangle([x - 44, 40, x, 76], fill=G.hex_to_rgb(hx), outline=(90, 88, 84))
        G.text(d, (x - 56, 64), label + "  " + hx, 16, False, cream, anchor="rs")
        x -= 44 + 36 + tw + 20

    # concept with sample boxes
    sc = 0.72
    cw, ch = int(rgb.shape[1] * sc), int(rgb.shape[0] * sc)
    cx, cy = 40, 130
    thumb = Image.fromarray(rgb).resize((cw, ch), Image.LANCZOS)
    sheet.paste(thumb, (cx, cy))
    d.rectangle([cx - 1, cy - 1, cx + cw, cy + ch], outline=(70, 68, 66))
    for i, s in enumerate(spec["swatches"]):
        for (x0, y0, x1, y1) in s["boxes"]:
            d.rectangle([cx + x0 * sc, cy + y0 * sc, cx + x1 * sc - 1, cy + y1 * sc - 1], outline=(245, 240, 230), width=1)
        bx, by_ = s["boxes"][0][0], s["boxes"][0][1]
        tag(d, cx + bx * sc - 2, cy + by_ * sc - 2, i + 1)
    G.text(d, (cx, cy + ch + 26), "White boxes: where each swatch was sampled (numbers match the list). Audit of the exact pixels: "
                                  "reports/stage0_palette_samples.png", 15, False, grey, anchor="ls")

    # swatch list
    x0, y = 1180, 124
    chip_w, chip_h, gap = 116, 42, 8
    xs = [x0 + 330 + k * (chip_w + gap) for k in range(3)]
    for k, nm in enumerate(TONE_NAMES):
        G.text(d, (xs[k] + chip_w / 2, y + 14), nm, 14, False, grey, anchor="ms")
    y += 24
    row_h = 55
    for s in sw:
        tag(d, x0 + 4, y + 6, s["n"])
        G.text(d, (x0 + 40, y + 26), s["label"], 20, True, cream, anchor="ls")
        sub = s["key"] + ("  -  EMISSIVE" if s["emissive"] else "")
        G.text(d, (x0 + 40, y + 46), sub, 13, False, (255, 170, 90) if s["emissive"] else grey, anchor="ls")
        for k, (nm, hx) in enumerate(s["tones"].items()):
            c = G.hex_to_rgb(hx)
            d.rectangle([xs[k], y + 4, xs[k] + chip_w, y + 4 + chip_h], fill=c)
            G.text(d, (xs[k] + chip_w / 2, y + 4 + chip_h / 2 + 5), hx, 14, False, G.ink_on(c), anchor="ms")
            if s["emissive"]:
                G.text(d, (xs[k] + 4, y + 16), nm, 10, False, G.ink_on(c), anchor="ls")
        note_x = xs[2] + chip_w + 18
        wrap(d, note_x, y + 20, s["note"], Wd - 40 - note_x, 14, (200, 194, 184))
        y += row_h

    # value key
    by0 = 950
    G.text(d, (40, by0), "Value key  -  base tones sorted dark to light (top: colour, bottom: its L* as grey)", 20, True, cream, anchor="ls")
    order = sorted(sw, key=lambda s: s["base_lab"][0])
    kw = 80
    for j, s in enumerate(order):
        c = np.array(G.hex_to_rgb(s["tones"]["base"] if "base" in s["tones"] else list(s["tones"].values())[1]), dtype=np.uint8)
        g = int(G.lstar_gray(c.reshape(1, 1, 3))[0, 0])
        xx = 40 + j * (kw + 5)
        d.rectangle([xx, by0 + 18, xx + kw, by0 + 78], fill=tuple(int(v) for v in c))
        d.rectangle([xx, by0 + 78, xx + kw, by0 + 138], fill=(g, g, g))
        G.text(d, (xx + kw / 2, by0 + 160), "%d" % s["n"], 15, True, cream, anchor="ms")
        G.text(d, (xx + kw / 2, by0 + 180), "L*%.0f" % s["base_lab"][0], 13, False, grey, anchor="ms")
    wrap(d, 40, by0 + 214, "Three value groups carry Brax at game scale: DARK (rock, leather, hair, wraps), MID (skin, bronze, "
                           "sash, cloth) and the EMISSIVE lava/eyes above everything. Keep that grouping through the toon ramp; "
                           "do not let rim light or bloom merge the dark and mid groups.", 1100, 15, (200, 194, 184))

    # colour budget
    bx0, bw = 1180, 1180
    G.text(d, (bx0, by0), "Colour budget  -  approx. share of the silhouette (nearest swatch)", 20, True, cream, anchor="ls")
    xx = bx0
    ink = pal["ink_and_deep_shadow_share"]
    parts = sorted(((s["silhouette_share"], s) for s in sw), key=lambda t: -t[0])
    for share, s in parts:
        w = share * bw
        c = G.hex_to_rgb(list(s["tones"].values())[1])
        d.rectangle([xx, by0 + 18, xx + w, by0 + 66], fill=c)
        if share >= 0.035:
            G.text(d, (xx + w / 2, by0 + 48), "%d" % s["n"], 15, True, G.ink_on(c), anchor="ms")
            G.text(d, (xx + w / 2, by0 + 86), "%.0f%%" % (100 * share), 13, False, grey, anchor="ms")
        xx += w
    d.rectangle([xx, by0 + 18, bx0 + bw, by0 + 66], fill=(8, 8, 8), outline=(60, 60, 60))
    G.text(d, (bx0 + bw, by0 + 86), "ink / deep shadow %.0f%%" % (100 * ink), 13, False, grey, anchor="rs")

    # checks
    c = pal["checks"]
    lines = []
    if "dE_bronze_vs_scale_plates" in c:
        lines.append("Bronze bands vs scale plates: dE %.1f - one bronze material; the plates differ by wear and roughness, not hue." % c["dE_bronze_vs_scale_plates"])
    if "dE_content_color_vs_lava_hot" in c:
        lines.append("UI colour %s vs lava 'hot': dE %.1f - the kit colour and the model's glow agree." % (pal["content_color"], c["dE_content_color_vs_lava_hot"]))
    dl = c["dL_vs_sheet_background"]
    if "gauntlet_rock" in dl:
        lines.append("Gauntlet rock vs the sheet's navy: dL* %+.1f - near-invisible by value; cracks, bronze and the ink outline carry the fists." % dl["gauntlet_rock"])
    for b in c.get("biomes", []):
        r = b["dL_vs_ground"]
        lines.append("%s ground %s: dL* rock %+.0f, skin %+.0f, teal %+.0f; lava vs biome glow dE %.0f" % (
            b["name"], b["ground"], r.get("gauntlet_rock", 0), r.get("skin", 0), r.get("teal_sash", 0), b["dE_lava_hot_vs_biome_accent"] or 0))
    y = by0 + 124
    G.text(d, (bx0, y), "Checks (CIELAB; ground colours are unlit albedo tints from biomes.ron)", 17, True, cream, anchor="ls")
    for ln in lines:
        y += 24
        G.text(d, (bx0, y), ln, 14, False, (200, 194, 184), anchor="ls")

    G.text(d, (40, Hd - 22), "generated by tools/comfy/palette_extract.py from %s  -  source sha256 %s...  -  %s" % (
        pal["spec"], pal["source"]["sha256"][:16], pal["generated"]), 13, False, (120, 116, 110), anchor="ls")
    sheet.save(path, optimize=True)


def tag(d, x, y, n):
    d.ellipse([x, y, x + 24, y + 24], fill=(236, 228, 210))
    G.text(d, (x + 12, y + 18), str(n), 14, True, (24, 22, 26), anchor="ms")


def wrap(d, x, y, s, width, size, fill):
    words, line, yy = s.split(), "", y
    for w in words:
        t = (line + " " + w).strip()
        if G.text_w(t, size) > width and line:
            G.text(d, (x, yy), line, size, False, fill, anchor="ls")
            yy += size + 5
            line = w
        else:
            line = t
    if line:
        G.text(d, (x, yy), line, size, False, fill, anchor="ls")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
