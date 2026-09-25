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

Optional spec keys (added for Valdris; a spec without them, like Brax's, gives the same bytes as before):
  "mask"          figure mask for the concept (PNG, > 127 = figure; e.g. the graph's birefnet mask from
                  run_trellis.py --mask-only). Use it when the background is a gradient, not flat: it
                  replaces the flat-background figure mask and also limits every concept sample.
  "sources"       {"name": "path"}: more approved images (e.g. a turnaround sheet). A swatch with
                  "source": "name" samples its boxes there instead of on the concept.
  "anchors"       the sheet's own declared colour script: [{"label", "hex" (the declared value),
                  "source", "box" (the painted chip), "swatch" (the measured material it names)}].
                  Reports declared vs painted chip vs measured material, in CIELAB dE.
  "cross_checks"  [{"swatch", "source", "boxes", "label"}]: measure a swatch again (same filter) on
                  another image and report the dE between the two images' base tones.
  "checks"        {"pairs": [[key_a, key_b, note]], "content_vs": key, "content_vs_tone": tone name
                  (default: base), "content_note": text, "probe": [keys],
                  "probe_labels": {key: label}, "emissive_vs_biome": key, "bg_probe": key,
                  "bg_note": text}: which contrast checks to compute and print (default: Brax's).
  "title", "subtitle", "title_rgb", "header_note", "value_note": callout-sheet text (default: the
                  hero key, its characters.csv title, and the original wording).
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


def load_image(path):
    """RGB array, flat-background colour, distance to it, HSV arrays."""
    rgb = np.asarray(Image.open(G.absp(path)).convert("RGB"))
    bg = G.background_rgb(rgb)
    dist = np.sqrt(((rgb.astype(np.float32) - bg) ** 2).sum(-1))
    return rgb, bg, dist, G.hsv_arrays(rgb)


def load_mask(path, shape):
    m = np.asarray(Image.open(G.absp(path)).convert("L")) > 127
    if m.shape != shape:
        raise SystemExit("mask %s is %s, the concept is %s" % (path, m.shape[::-1], shape[::-1]))
    return m


def csv_title(key):
    """The hero's title from content/sheets/characters.csv ('' if not found)."""
    import csv
    try:
        with open(os.path.join(G.ROOT, "content", "sheets", "characters.csv"), encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("key") == key:
                    return row.get("title", "")
    except OSError:
        pass
    return ""


def lab_of(hx):
    return G.srgb_to_lab(np.array(G.hex_to_rgb(hx), dtype=np.float64))


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec_path = G.absp(argv[1])
    spec = json.load(open(spec_path, encoding="utf-8"))
    concept = G.absp(spec["concept"])
    rgb, bg, dist, hsv = load_image(concept)
    H, W, _ = rgb.shape
    fig = load_mask(spec["mask"], (H, W)) if spec.get("mask") else G.figure_mask(rgb, bg)
    # other approved images a swatch may sample (optional; name -> (rgb, bg, dist, hsv))
    others = {name: load_image(path) for name, path in spec.get("sources", {}).items()}

    def source_of(sw):
        name = sw.get("source")
        if not name:
            return rgb, hsv, dist, (fig if spec.get("mask") else None)
        o = others[name]
        return o[0], o[3], o[2], None

    swatches, masks = [], []
    for i, sw in enumerate(spec["swatches"]):
        srgb, shsv, sdist, smask = source_of(sw)
        m = sample(sw, srgb, shsv, sdist)
        if smask is not None:
            m &= smask
        px = srgb[m].astype(np.float64)
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
        if sw.get("source"):
            rec["source"] = sw["source"]
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
    cfg = spec.get("checks")
    if cfg is None:            # the original (Brax) checks
        if "bronze" in by and "scale_plates" in by:
            checks["dE_bronze_vs_scale_plates"] = dE(by["bronze"]["base_lab"], by["scale_plates"]["base_lab"])
        if "lava_glow" in by and spec.get("content_color"):
            cc = G.srgb_to_lab(np.array(G.hex_to_rgb(spec["content_color"]), dtype=np.float64))
            checks["dE_content_color_vs_lava_hot"] = dE(cc, by["lava_glow"]["base_lab"])
        probe = [k for k in ("gauntlet_rock", "skin", "bronze", "teal_sash", "lava_glow") if k in by]
        emissive_key, emissive_field = "lava_glow", "dE_lava_hot_vs_biome_accent"
    else:
        for pair in cfg.get("pairs", []):
            if pair[0] in by and pair[1] in by:
                checks["dE_%s_vs_%s" % (pair[0], pair[1])] = dE(by[pair[0]]["base_lab"], by[pair[1]]["base_lab"])
        ck, ct = cfg.get("content_vs"), cfg.get("content_vs_tone")
        if ck in by and spec.get("content_color"):
            ref = lab_of(by[ck]["tones"][ct]) if ct else by[ck]["base_lab"]
            checks["dE_content_color_vs_%s" % ck] = dE(lab_of(spec["content_color"]), ref)
        probe = [k for k in cfg.get("probe", []) if k in by]
        emissive_key = cfg.get("emissive_vs_biome")
        emissive_field = "dE_%s_vs_biome_accent" % emissive_key
    checks["dL_vs_sheet_background"] = {s["key"]: round(s["base_lab"][0] - float(bg_lab[0]), 1) for s in swatches}
    bl = []
    for key, name, ground, accent, fog in biomes():
        g = G.srgb_to_lab(np.array(G.hex_to_rgb(ground), dtype=np.float64))
        a = G.srgb_to_lab(np.array(G.hex_to_rgb(accent), dtype=np.float64))
        bl.append({"biome": key, "name": name, "ground": ground, "accent": accent,
                   "dL_vs_ground": {k: round(by[k]["base_lab"][0] - float(g[0]), 1) for k in probe},
                   emissive_field: dE(by[emissive_key]["base_lab"], a) if emissive_key in by else None})
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
    if spec.get("mask"):
        out["mask"] = {"path": G.rel(G.absp(spec["mask"])), "sha256": G.sha256(G.absp(spec["mask"])),
                       "use": "figure mask for the silhouette shares; every concept sample is limited to it"}
        out["method"] = out["method"].replace("flat background removed", "background removed by the figure mask")
    if others:
        out["sources"] = {name: {"path": G.rel(G.absp(path)), "sha256": G.sha256(G.absp(path)),
                                 "size": [others[name][0].shape[1], others[name][0].shape[0]]}
                          for name, path in spec["sources"].items()}
    if spec.get("anchors"):
        out["anchors"] = anchors(spec, rgb, others, by, dE)
    if spec.get("cross_checks"):
        out["cross_checks"] = cross_checks(spec, rgb, hsv, dist, others, by, dE)
    outs = spec["outputs"]
    with open(G.absp(outs["palette"]), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    audit_overlay(rgb, masks, spec, G.absp(outs["overlay"]), others)
    color_script(rgb, fig, spec, out, G.absp(outs["color_script"]), others)
    for s in swatches:
        print("[palette] %2d %-14s %s  n=%6d  share %.1f%%" % (s["n"], s["key"], " ".join(s["tones"].values()),
                                                              s["pixels_sampled"], 100 * s["silhouette_share"]))
    print("[palette] checks:", json.dumps({k: v for k, v in checks.items() if k.startswith("dE")}))
    for a in out.get("anchors", []):
        print("[palette] anchor %-24s declared %s painted %s -> %s %s: dE declared/painted %s, to measured %s (nearest tone %s %s, dE %.1f)"
              % (a["label"], a["declared"], a["painted_chip"], a.get("swatch"), a.get("measured_base"),
                 a.get("dE_declared_vs_painted"), a.get("dE_declared_vs_measured_base", a.get("dE_painted_vs_measured_base")),
                 a.get("nearest_measured_tone", {}).get("name"), a.get("nearest_measured_tone", {}).get("hex"),
                 a.get("nearest_measured_tone", {}).get("dE", float("nan"))))
    for c in out.get("cross_checks", []):
        print("[palette] cross-check %-14s on %s: base %s vs %s  dE %.1f" % (c["swatch"], c["source"], c["tones"][c["base_name"]],
                                                                          c["concept_base"], c["dE_base"]))
    print("[palette] wrote", outs["palette"], outs["color_script"], outs["overlay"])
    return 0


def anchors(spec, rgb, others, by, dE):
    """The sheet's declared colour script: declared hex vs the painted chip vs the measured material."""
    res = []
    for a in spec["anchors"]:
        img = others[a["source"]][0] if a.get("source") else rgb
        x0, y0, x1, y1 = a["box"]
        chip = np.median(img[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64), axis=0)
        pl = G.srgb_to_lab(chip)
        rec = {"label": a["label"], "declared": a["hex"].upper() if a.get("hex") else None,
               "painted_chip": G.rgb_to_hex(chip), "painted_Lstar": round(float(pl[0]), 1)}
        dl = lab_of(a["hex"]) if a.get("hex") else pl      # no declared value: compare the painted chip
        if a.get("hex"):
            rec.update({"dE_declared_vs_painted": dE(dl, pl), "declared_Lstar": round(float(dl[0]), 1)})
        sw = by.get(a.get("swatch"))
        if sw:
            base = sw["tones"][list(sw["tones"])[1]]
            near = min(sw["tones"].items(), key=lambda t: float(np.linalg.norm(lab_of(t[1]) - dl)))
            tag_ = "declared" if a.get("hex") else "painted"
            rec.update({"swatch": sw["key"], "measured_base": base, "dE_%s_vs_measured_base" % tag_: dE(dl, sw["base_lab"]),
                        "nearest_measured_tone": {"name": near[0], "hex": near[1], "dE": dE(dl, lab_of(near[1]))}})
        if a.get("note"):
            rec["note"] = a["note"]
        res.append(rec)
    return res


def cross_checks(spec, rgb, hsv, dist, others, by, dE):
    """A swatch measured again (same filter) on another image: do the two images agree?"""
    sws = {s["key"]: s for s in spec["swatches"]}
    res = []
    for c in spec["cross_checks"]:
        sw = dict(sws[c["swatch"]], boxes=c["boxes"])
        if c.get("source"):
            img, ihsv, idist = others[c["source"]][0], others[c["source"]][3], others[c["source"]][2]
        else:
            img, ihsv, idist = rgb, hsv, dist
        m = sample(sw, img, ihsv, idist)
        px = img[m].astype(np.float64)
        if len(px) < 30:
            raise SystemExit("cross-check %s: only %d pixels passed" % (c["swatch"], len(px)))
        names, pcts = sw.get("tone_names", TONE_NAMES), sw.get("tones", TONES)
        tv = tones_of(px, pcts)
        mine = by[c["swatch"]]
        res.append({"swatch": c["swatch"], "label": c.get("label", ""), "source": c.get("source", "concept"),
                    "boxes": c["boxes"], "pixels_sampled": int(len(px)),
                    "tones": {nm: G.rgb_to_hex(t) for nm, t in zip(names, tv)}, "base_name": names[1],
                    "concept_base": mine["tones"][names[1]],
                    "dE_base": dE(G.srgb_to_lab(tv[1]), mine["base_lab"]),
                    "dL_base": round(float(G.srgb_to_lab(tv[1])[0] - mine["base_lab"][0]), 1)})
    return res


def audit_overlay(rgb, masks, spec, path, others=None):
    ov = (rgb.astype(np.float32) * 0.35).astype(np.uint8)
    for i, m in enumerate(masks):
        if not spec["swatches"][i].get("source"):
            ov[m] = AUDIT[i % len(AUDIT)]
    im = Image.fromarray(ov)
    d = ImageDraw.Draw(im)
    for i, sw in enumerate(spec["swatches"]):
        if sw.get("source"):
            continue
        for (x0, y0, x1, y1) in sw["boxes"]:
            d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=AUDIT[i % len(AUDIT)], width=1)
        x0, y0 = sw["boxes"][0][:2]
        d.rectangle([x0, y0 - 16, x0 + 20, y0 - 1], fill=(0, 0, 0))
        G.text(d, (x0 + 3, y0 - 15), str(i + 1), 12, True, AUDIT[i % len(AUDIT)])
    G.text(d, (16, 12), "%s - pixels sampled per swatch (false colour); boxes from %s" % (spec["character"], os.path.basename(spec["outputs"]["palette"]).replace("palette.json", "palette_spec.json")), 16)
    if not others:
        im.save(path, optimize=True)
        return
    # extra sources: one panel each, to the right, at native size
    panels = []
    for name, (orgb, obg, odist, ohsv) in others.items():
        o = (orgb.astype(np.float32) * 0.35).astype(np.uint8)
        od = None
        idx = {s["key"]: i for i, s in enumerate(spec["swatches"])}
        for i, sw in enumerate(spec["swatches"]):
            if sw.get("source") == name:
                o[masks[i]] = AUDIT[i % len(AUDIT)]
        for c in spec.get("cross_checks", []):
            if c.get("source") == name:
                i = idx[c["swatch"]]
                cm = sample(dict(spec["swatches"][i], boxes=c["boxes"]), orgb, ohsv, odist)
                o[cm] = AUDIT[i % len(AUDIT)]
        oi = Image.fromarray(o)
        od = ImageDraw.Draw(oi)
        for i, sw in enumerate(spec["swatches"]):
            if sw.get("source") == name:
                for (x0, y0, x1, y1) in sw["boxes"]:
                    od.rectangle([x0, y0, x1 - 1, y1 - 1], outline=AUDIT[i % len(AUDIT)], width=1)
                G.text(od, (sw["boxes"][0][0] + 3, sw["boxes"][0][1] + 2), str(i + 1), 12, True, AUDIT[i % len(AUDIT)])
        for c in spec.get("cross_checks", []):
            if c.get("source") == name:
                i = idx[c["swatch"]]
                for (x0, y0, x1, y1) in c["boxes"]:
                    od.rectangle([x0, y0, x1 - 1, y1 - 1], outline=AUDIT[i % len(AUDIT)], width=1)
                G.text(od, (c["boxes"][0][0] + 3, c["boxes"][0][1] + 2), "x%d" % (i + 1), 12, True, AUDIT[i % len(AUDIT)])
        for a in spec.get("anchors", []):
            if a.get("source") == name:
                x0, y0, x1, y1 = a["box"]
                od.rectangle([x0 - 2, y0 - 2, x1 + 1, y1 + 1], outline=(255, 255, 255), width=1)
        G.text(od, (16, oi.height - 30), "%s: swatch boxes (n), cross-checks (xn), colour-script chips (white)" % name, 16)
        panels.append(oi)
    Wt = im.width + sum(p.width + 20 for p in panels)
    Ht = max([im.height] + [p.height for p in panels])
    out = Image.new("RGB", (Wt, Ht), (0, 0, 0))
    out.paste(im, (0, 0))
    x = im.width + 20
    for p in panels:
        out.paste(p, (x, 0))
        x += p.width + 20
    out.save(path, optimize=True)


DEFAULT_VALUE_NOTE = ("Three value groups carry Brax at game scale: DARK (rock, leather, hair, wraps), MID (skin, bronze, "
                      "sash, cloth) and the EMISSIVE lava/eyes above everything. Keep that grouping through the toon ramp; "
                      "do not let rim light or bloom merge the dark and mid groups.")


def color_script(rgb, fig, spec, pal, path, others=None):
    Wd, Hd = 2400, 1320
    sheet, d = G.new_sheet(Wd, Hd)
    sw = pal["swatches"]
    cream, grey = (236, 228, 210), (150, 146, 140)
    # header
    title = spec.get("title") or spec["character"].upper()
    subtitle = spec.get("subtitle") or "%s  -  colour callouts" % csv_title(spec["character"])
    title_rgb = G.hex_to_rgb(spec["title_rgb"]) if spec.get("title_rgb") else (255, 150, 90)
    G.text(d, (40, 64), title, 50, True, title_rgb, anchor="ls")
    G.text(d, (40 + G.text_w(title, 50, True) + 18, 64), subtitle, 32, True, cream, anchor="ls")
    note = spec.get("header_note") or ("Measured from the approved front concept (%s). Stage-0 derived data: it records the approved colours, it is not "
                                       "the painted colour-script sheet (pending)." % pal["source"]["path"])
    G.text(d, (40, 98), note, 17, False, grey, anchor="ls")
    # header chips: sheet background, content colour
    x = Wd - 40
    for label, hx in (("content colour (characters.csv)", pal["content_color"]), ("sheet background", pal["sheet_background"])):
        if not hx:
            continue
        tw = G.text_w(label + "  " + hx, 16)
        d.rectangle([x - 44, 40, x, 76], fill=G.hex_to_rgb(hx), outline=(90, 88, 84))
        G.text(d, (x - 56, 64), label + "  " + hx, 16, False, cream, anchor="rs")
        x -= 44 + 36 + tw + 20

    # concept with sample boxes (0.72 for a 1536x1024 plate; a taller plate is fitted to 760 px)
    sc = min(0.72, 1106.0 / rgb.shape[1], 760.0 / rgb.shape[0])
    cw, ch = int(rgb.shape[1] * sc), int(rgb.shape[0] * sc)
    cx, cy = 40, 130
    thumb = Image.fromarray(rgb).resize((cw, ch), Image.LANCZOS)
    sheet.paste(thumb, (cx, cy))
    d.rectangle([cx - 1, cy - 1, cx + cw, cy + ch], outline=(70, 68, 66))
    for i, s in enumerate(spec["swatches"]):
        if s.get("source"):
            continue
        for (x0, y0, x1, y1) in s["boxes"]:
            d.rectangle([cx + x0 * sc, cy + y0 * sc, cx + x1 * sc - 1, cy + y1 * sc - 1], outline=(245, 240, 230), width=1)
        bx, by_ = s["boxes"][0][0], s["boxes"][0][1]
        tag(d, cx + bx * sc - 2, cy + by_ * sc - 2, i + 1)
    G.text(d, (cx, cy + ch + 26), "White boxes: where each swatch was sampled (numbers match the list). Audit of the exact pixels: "
                                  "reports/stage0_palette_samples.png", 15, False, grey, anchor="ls")
    if others:
        sources_panel(sheet, d, spec, pal, others, cx + cw + 30, cy, 1150)

    # swatch list
    x0, y = 1180, 124
    chip_w, chip_h, gap = 116, 42, 8
    xs = [x0 + 330 + k * (chip_w + gap) for k in range(3)]
    for k, nm in enumerate(TONE_NAMES):
        G.text(d, (xs[k] + chip_w / 2, y + 14), nm, 14, False, grey, anchor="ms")
    y += 24
    row_h = min(55, (925 - y) // max(1, len(sw)))
    for s in sw:
        tag(d, x0 + 4, y + 6, s["n"])
        G.text(d, (x0 + 40, y + 26), s["label"], 20, True, cream, anchor="ls")
        sub = s["key"] + ("  -  EMISSIVE" if s["emissive"] else "") + ("  -  from %s" % s["source"] if s.get("source") else "")
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
    kw = 80 if len(order) * 85 <= 1110 else int(1110 / len(order)) - 5
    for j, s in enumerate(order):
        c = np.array(G.hex_to_rgb(s["tones"]["base"] if "base" in s["tones"] else list(s["tones"].values())[1]), dtype=np.uint8)
        g = int(G.lstar_gray(c.reshape(1, 1, 3))[0, 0])
        xx = 40 + j * (kw + 5)
        d.rectangle([xx, by0 + 18, xx + kw, by0 + 78], fill=tuple(int(v) for v in c))
        d.rectangle([xx, by0 + 78, xx + kw, by0 + 138], fill=(g, g, g))
        G.text(d, (xx + kw / 2, by0 + 160), "%d" % s["n"], 15, True, cream, anchor="ms")
        G.text(d, (xx + kw / 2, by0 + 180), "L*%.0f" % s["base_lab"][0], 13, False, grey, anchor="ms")
    wrap(d, 40, by0 + 214, spec.get("value_note") or DEFAULT_VALUE_NOTE, 1100, 15, (200, 194, 184))

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
    lines = check_lines(spec, pal) if spec.get("checks") is not None else []
    if spec.get("checks") is None:
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


def check_lines(spec, pal):
    """Callout-sheet lines for a spec with a "checks" block."""
    cfg, c = spec["checks"], pal["checks"]
    by = {s["key"]: s for s in pal["swatches"]}
    lab = cfg.get("probe_labels", {})

    def name(k):
        return lab.get(k) or (by[k]["label"] if k in by else k)
    lines = []
    for pair in cfg.get("pairs", []):
        k = "dE_%s_vs_%s" % (pair[0], pair[1])
        if k in c:
            lines.append("%s vs %s: dE %.1f%s" % (by[pair[0]]["label"], by[pair[1]]["label"], c[k],
                                                  (" - " + pair[2]) if len(pair) > 2 and pair[2] else ""))
    ck = cfg.get("content_vs")
    if ck and "dE_content_color_vs_%s" % ck in c:
        tone = cfg.get("content_vs_tone")
        lines.append("UI colour %s vs %s%s: dE %.1f%s" % (pal["content_color"], by[ck]["label"],
                                                         (" " + tone) if tone else "", c["dE_content_color_vs_%s" % ck],
                                                         (" - " + cfg["content_note"]) if cfg.get("content_note") else ""))
    bp = cfg.get("bg_probe")
    if bp and bp in c["dL_vs_sheet_background"]:
        lines.append("%s vs the concept's background: dL* %+.1f%s" % (by[bp]["label"], c["dL_vs_sheet_background"][bp],
                                                                     (" - " + cfg["bg_note"]) if cfg.get("bg_note") else ""))
    ek = cfg.get("emissive_vs_biome")
    for b in c.get("biomes", []):
        r = b["dL_vs_ground"]
        parts = ", ".join("%s %+.0f" % (name(k), v) for k, v in r.items())
        tail = ""
        if ek and b.get("dE_%s_vs_biome_accent" % ek) is not None:
            tail = "; %s vs biome glow dE %.0f" % (name(ek), b["dE_%s_vs_biome_accent" % ek])
        lines.append("%s ground %s: dL* %s%s" % (b["name"], b["ground"], parts, tail))
    return lines


def sources_panel(sheet, d, spec, pal, others, x0, y0, x1):
    """Extra approved images (thumbnail with their boxes), the declared colour script and the cross-checks."""
    cream, grey, soft = (236, 228, 210), (150, 146, 140), (200, 194, 184)
    width = x1 - x0
    y = y0
    idx = {s["key"]: i for i, s in enumerate(spec["swatches"])}
    for name, (orgb, _, _, _) in others.items():
        s2 = min(width / float(orgb.shape[1]), 340.0 / orgb.shape[0])
        tw, th = int(orgb.shape[1] * s2), int(orgb.shape[0] * s2)
        sheet.paste(Image.fromarray(orgb).resize((tw, th), Image.LANCZOS), (x0, y))
        d.rectangle([x0 - 1, y - 1, x0 + tw, y + th], outline=(70, 68, 66))
        for i, s in enumerate(spec["swatches"]):
            if s.get("source") == name:
                for (bx0, by0, bx1, by1) in s["boxes"]:
                    d.rectangle([x0 + bx0 * s2, y + by0 * s2, x0 + bx1 * s2 - 1, y + by1 * s2 - 1], outline=(245, 240, 230), width=1)
                tag(d, x0 + s["boxes"][0][0] * s2 - 2, y + s["boxes"][0][1] * s2 - 2, i + 1)
        for cc in spec.get("cross_checks", []):
            if cc.get("source") == name:
                for (bx0, by0, bx1, by1) in cc["boxes"]:
                    d.rectangle([x0 + bx0 * s2, y + by0 * s2, x0 + bx1 * s2 - 1, y + by1 * s2 - 1], outline=(90, 200, 255), width=1)
        for a in spec.get("anchors", []):
            if a.get("source") == name:
                ax0, ay0, ax1, ay1 = a["box"]
                d.rectangle([x0 + ax0 * s2 - 2, y + ay0 * s2 - 2, x0 + ax1 * s2 + 1, y + ay1 * s2 + 1], outline=(255, 194, 75), width=2)
        y += th + 20
        fit_text(d, (x0, y), "%s (%s): white = swatch boxes, blue = cross-checks, gold = its colour-script chips"
                 % (name, os.path.basename(pal["sources"][name]["path"])), width, 13, grey)
        y += 22
    anc = pal.get("anchors", [])
    if anc:
        y += 6
        G.text(d, (x0, y), "The sheet's own colour script: declared / painted / measured", 16, True, cream, anchor="ls")
        y += 6
        cw_ = 40
        tx = x0 + 3 * (cw_ + 4) + 8
        for a in anc:
            for k, hx in enumerate((a["declared"], a["painted_chip"], a.get("measured_base"))):
                if not hx:
                    G.text(d, (x0 + k * (cw_ + 4) + cw_ / 2, y + 22), "-", 14, False, grey, anchor="ms")
                    continue
                cc = G.hex_to_rgb(hx)
                d.rectangle([x0 + k * (cw_ + 4), y + 4, x0 + k * (cw_ + 4) + cw_, y + 30], fill=cc, outline=(70, 68, 66))
            G.text(d, (tx, y + 15), "%s  %s" % (a["label"], a["declared"] or "(no hex on the sheet)"), 13, True, cream, anchor="ls")
            if a["declared"]:
                sub = "painted %s (dE %.0f)" % (a["painted_chip"], a["dE_declared_vs_painted"])
            else:
                sub = "painted %s" % a["painted_chip"]
            if a.get("swatch"):
                near = a["nearest_measured_tone"]
                sub += " | nearest measured: %d %s %s (dE %.0f)" % (idx.get(a["swatch"], -1) + 1, near["name"], near["hex"], near["dE"])
            fit_text(d, (tx, y + 30), sub, x1 - tx, 12, soft)
            y += 36
    xc = pal.get("cross_checks", [])
    if xc:
        y += 10
        G.text(d, (x0, y), "Same material on both images (same filter; base tones)", 16, True, cream, anchor="ls")
        for cc in xc:
            y += 17
            fit_text(d, (x0, y), "%d %s: sheet %s vs hero %s  dE %.0f, dL* %+.0f" % (
                idx[cc["swatch"]] + 1, cc.get("label") or cc["swatch"], cc["tones"][cc["base_name"]],
                cc["concept_base"], cc["dE_base"], cc["dL_base"]), x1 - x0, 12, soft)


def fit_text(d, xy, s, width, size, fill):
    """One line, shrunk (down to 9 px) until it fits the width."""
    while size > 9 and G.text_w(s, size) > width:
        size -= 1
    G.text(d, xy, s, size, False, fill, anchor="ls")


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
