"""Stage 5 review sheet (PIL; run with ComfyUI's python, which has PIL).

  <comfy-python> tools/blender/gf_hero/s5_sheets.py <key>

Reads work/renders/stage5/ (smoke_import.py --render: the SHIPPED GLBs re-imported into a fresh Blender, the weapon
attached through the imported sockets), work/renders/stage4/ (the stage-4 source renders of the same frames, when they
are on this machine) and reports/export_report.json, and writes art/characters/<key>/reports/stage5/export_review.png:
one row per key pose - the stage-4 source (front three-quarter), the shipped file (front three-quarter + side), and the
client camera at true 1080p pixel size (yaw 0 and 90 at 1x, yaw 0 at 3x nearest) - plus the export numbers. A 256-colour
palette PNG well under 2 MB.
"""
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KEY = sys.argv[1] if len(sys.argv) > 1 else "brax"
A = os.path.join(ROOT, "art", "characters", KEY)
REN = os.path.join(A, "work", "renders", "stage5")
SRC = os.path.join(A, "work", "renders", "stage4")
OUT = os.path.join(A, "reports", "stage5")
REP = json.load(open(os.path.join(A, "reports", "export_report.json"), encoding="utf-8"))
BG = (24, 24, 28)
FG = (232, 226, 214)
DIM = (150, 146, 140)
OKC = (150, 220, 150)
BAD = (255, 120, 100)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 16)
    SMALL = ImageFont.truetype("arial.ttf", 13)
    BIG = ImageFont.truetype("arialbd.ttf", 24)
except OSError:
    FONT = SMALL = BIG = ImageFont.load_default()
CW, CH = 300, 360          # close-up cell
IG = 160                   # in-game crop at 1x (true 1080p pixels)
GAP = 8


def load(path, size):
    if not os.path.exists(path):
        im = Image.new("RGB", size, (40, 30, 30))
        ImageDraw.Draw(im).text((8, 8), "not on this machine", fill=DIM, font=SMALL)
        return im
    return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)


def label(im, text, xy=(5, 4), font=None, fill=FG):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=fill, font=font or SMALL)
    return im


def main():
    shots = REP.get("blender_reimport", {}).get("review_renders", {}).get("shots", [])
    if not shots:
        raise SystemExit("no review renders in export_report.json (run smoke_import.py --render ... --report ...)")
    hero = REP.get("hero_export", {})
    val = hero.get("validation", {})
    bi = REP.get("blender_reimport", {})
    wep = (REP.get("weapons") or {})
    head_h = 118
    row_h = CH + GAP
    width = GAP + 3 * (CW + GAP) + 2 * (IG + GAP) + 3 * IG + GAP
    height = head_h + len(shots) * row_h + 30
    out = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(out)
    d.text((12, 8), "%s - stage 5: the shipped GLB, re-imported into a fresh Blender" % KEY.capitalize(), fill=FG, font=BIG)
    lines = [
        "%s: %s, %.2f MB, %s tris, %s joints, %d clips, textures %s; validate_glb %s; source fidelity %.1e; Blender re-import %s (clip pose error %.1e)" % (
            hero.get("glb"), "OK" if hero.get("ok") else "FAILED", (hero.get("bytes") or 0) / 1e6, val.get("tris"), val.get("joints"),
            len(val.get("clips", [])), "/".join("%s %d" % (t["role"], t["px"][0]) for t in val.get("textures", [])),
            "OK" if val.get("ok") else "FAILED", hero.get("source_fidelity", {}).get("max_error", -1),
            "OK" if bi.get("ok") else "FAILED", bi.get("clip_pose_max_error", -1)),
    ]
    for k, w in wep.items():
        lines.append("weapon %s: %s, %s tris shown (fist pair), %d meshes (open + fist per hand), attached by identity on weapon_R / weapon_L (rest error %.1e)" % (
            w.get("glb"), "OK" if w.get("ok") else "FAILED", w.get("tris_shown_pair"), len(w.get("tris_per_mesh", {})),
            bi.get("weapon", {}).get("attach_rest_error", -1)))
    lines.append("columns: stage-4 source render (Blender file) | the shipped GLB, front 3/4 and side | client camera 55 deg at true 1080p pixels: yaw 0, yaw 90 (1x), yaw 0 at 3x nearest")
    y = 42
    for i, ln in enumerate(lines):
        d.text((12, y), ln, fill=(OKC if i == 0 and hero.get("ok") and bi.get("ok") else FG) if i < len(lines) - 1 else DIM, font=SMALL)
        y += 18
    y0 = head_h
    for s in shots:
        tag, clip, f = s["shot"], s["clip"], s["frame"]
        name = clip[len(KEY) + 1:].replace("@loop", "")
        x = GAP
        src = load(os.path.join(SRC, name, "f%03d_front.png" % f), (CW, CH))
        out.paste(label(src, "stage 4 source  %s f%d" % (name, f)), (x, y0))
        x += CW + GAP
        for view in ("front", "side"):
            im = load(os.path.join(REN, "%s_%s.png" % (tag, view)), (CW, CH))
            out.paste(label(im, "shipped GLB  %s" % view, fill=(255, 214, 150)), (x, y0))
            x += CW + GAP
        for yaw in (0, 90):
            im = load(os.path.join(REN, "%s_ingame%d.png" % (tag, yaw)), (IG, IG))
            out.paste(im, (x, y0))
            label(out, "yaw %d, 1x" % yaw, (x + 4, y0 + IG + 4), fill=DIM)
            x += IG + GAP
        big = load(os.path.join(REN, "%s_ingame0.png" % tag), (IG, IG)).resize((3 * IG, 3 * IG), Image.NEAREST)
        big = big.crop((0, (3 * IG - CH) // 2, 3 * IG, (3 * IG - CH) // 2 + CH))
        out.paste(big, (x, y0))
        ws = s.get("weapon_shown", {})
        info = "%s f%d\nweapon L %s / R %s\nclip pose err %.1e" % (clip, f, ws.get("L"), ws.get("R"),
                                                                    bi.get("clips", {}).get(clip, {}).get("max_bone_error", -1))
        ImageDraw.Draw(out).multiline_text((GAP + 3 * (CW + GAP), y0 + IG + 26), info, fill=FG, font=SMALL, spacing=4)
        y0 += row_h
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "export_review.png")
    buf = io.BytesIO()
    out.quantize(colors=256, method=Image.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (buf.tell() / 1e6), out.size)


if __name__ == "__main__":
    main()
