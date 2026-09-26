"""Stage 5, Valdris: the shipped files next to the concept and the blockout (PIL; run with ComfyUI's python).

  <comfy-python> tools/blender/gf_hero/s5_valdris_sheets.py

The optional "board" step of run_stage5.py (it runs s5_<key>_sheets.py when the hero has one). Reads the review renders
smoke_import.py made of the SHIPPED files (work/renders/stage5/: valdris.glb re-imported into a fresh factory Blender,
the weapon track's colossus_cannon.glb on the imported weapon_R, the textures from inside the GLBs through the Cycles
CPU toon preview) and reports/export_report.json, and writes art/characters/valdris/reports/stage5/valdris_board.png:
  top     the approved concept (resolved front, cannon on his right), the turnaround sheet, the stage-1 blockout (lit
          front and client camera at 3x) - the same references as the stage-4 boards
  middle  the shipped file in the combat guard: front three-quarter and side close-ups, the client camera (55 deg,
          22 m view height, true 1080p pixels) at yaw 0 and 90 at 1x, and yaw 0 at 3x nearest
  bottom  every review shot through the client camera at 1x and at 2x nearest, labelled with the clip, the frame and
          what the frame is (event), and the export numbers
A 256-colour palette PNG. Adapted from s4_valdris_sheets.py (its header and crop) and s5_sheets.py.
"""
import io
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KEY = "valdris"
A = os.path.join(ROOT, "art", "characters", KEY)
REN = os.path.join(A, "work", "renders", "stage5")
OUT = os.path.join(A, "reports", "stage5")
REP = json.load(open(os.path.join(A, "reports", "export_report.json"), encoding="utf-8"))
CLIPS = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))["clips"]
CONCEPT = os.path.join(A, "references", "valdris_concept_front_mirrored.png")
SHEET = os.path.join(A, "references", "VALDRIS_sheet_turnaround.jpg")
BLOCKOUT = os.path.join(A, "reports", "blockout", "blockout_selected.png")
BG = (24, 24, 28)
FG = (232, 226, 214)
DIM = (150, 146, 140)
OKC = (150, 220, 150)
BAD = (255, 120, 100)
GOLD = (255, 214, 150)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 17)
    SMALL = ImageFont.truetype("arial.ttf", 13)
    BIG = ImageFont.truetype("arialbd.ttf", 24)
except OSError:
    FONT = SMALL = BIG = ImageFont.load_default()


def load(path, size=None):
    if not os.path.exists(path):
        im = Image.new("RGB", size or (160, 160), (40, 20, 20))
        ImageDraw.Draw(im).text((6, 6), "missing", fill=FG, font=SMALL)
        return im
    im = Image.open(path).convert("RGB")
    return im.resize(size, Image.LANCZOS) if size else im


def to_h(im, h):
    return im.resize((int(im.width * h / im.height), h), Image.LANCZOS)


def label(im, text, xy=(4, 3), font=None, fill=FG):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=fill, font=font or SMALL)
    return im


def centre_crop(im, w, h):
    """A w x h window of a client-camera render centred on the hero (pixels away from the floor colour), clamped."""
    px = im.load()
    bg = px[2, 2]
    xs, ys = [], []
    for y in range(im.height):
        for x in range(im.width):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 40:
                xs.append(x)
                ys.append(y)
    cx, cy = ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2) if xs else (im.width // 2, im.height // 2)
    x0 = max(0, min(im.width - w, cx - w // 2))
    y0 = max(0, min(im.height - h, cy - h // 2))
    return im.crop((x0, y0, x0 + w, y0 + h))


def event_at(clip, f):
    ev = [k for k, v in CLIPS.get(clip, {}).get("events", {}).items() if int(v) == f]
    return ev[0] if ev else ("loop" if CLIPS.get(clip, {}).get("loop") else "")


def main():
    bi = REP.get("blender_reimport", {})
    shots = bi.get("review_renders", {}).get("shots", [])
    if not shots:
        raise SystemExit("no review renders in export_report.json (run_stage5.py valdris --only reimport)")
    hero = REP.get("hero_export", {})
    val = hero.get("validation", {})
    bw = bi.get("weapon", {})
    H = 330          # the reference row
    HM = 360         # the shipped row (the 3x crop: 120 px of the 1x render)

    # ---- top: the references ----
    ref = to_h(load(CONCEPT), H)
    sheet = to_h(load(SHEET), H)
    bo = load(BLOCKOUT)
    cw, top = bo.width / 5.0, 37
    ch = (bo.height - top) / 2.0
    bo_front = to_h(bo.crop((int(cw), top, int(2 * cw), int(top + ch))), H)
    bo_game = to_h(bo.crop((int(4 * cw), int(top + ch), bo.width, bo.height)), H)
    refs = [(ref, "concept (mirrored)"), (sheet, "turnaround sheet"),
            (bo_front, "stage-1 blockout, lit front"), (bo_game, "blockout, client camera 3x")]

    # ---- middle: the shipped file in the guard ----
    g = shots[0]
    tag = g["shot"]
    fr = label(load(os.path.join(REN, "%s_front.png" % tag), (300, HM)), "shipped GLB, front 3/4", fill=GOLD)
    sd = label(load(os.path.join(REN, "%s_side.png" % tag), (300, HM)), "shipped GLB, side", fill=GOLD)
    g0 = load(os.path.join(REN, "%s_ingame0.png" % tag))
    g9 = load(os.path.join(REN, "%s_ingame90.png" % tag))
    big = centre_crop(g0, 120, 120).resize((HM, HM), Image.NEAREST)
    mids = [(fr, None), (sd, None), (g0, "yaw 0, 1x"), (g9, "yaw 90, 1x"), (label(big, "yaw 0, 3x nearest", fill=GOLD), None)]

    # ---- bottom: every shot at game size ----
    cells = []
    for s in shots:
        clip = s["clip"][len(KEY) + 1:].replace("@loop", "")
        i0 = load(os.path.join(REN, "%s_ingame0.png" % s["shot"]))
        c = Image.new("RGB", (160 + 6 + 240, 268), BG)
        c.paste(centre_crop(i0, 120, 120).resize((240, 240), Image.NEAREST), (166, 0))
        c.paste(i0, (0, 40))
        ev = event_at(clip, s["frame"])
        ImageDraw.Draw(c).text((2, 2), "%s f%d" % (clip, s["frame"]), fill=FG, font=FONT)
        ImageDraw.Draw(c).text((2, 22), ev, fill=DIM, font=SMALL)
        ImageDraw.Draw(c).text((170, 244), "1x | 2x nearest", fill=DIM, font=SMALL)
        cells.append(c)
    per_row = 4
    grid_w = per_row * (cells[0].width + 10)
    grid_h = ((len(cells) + per_row - 1) // per_row) * (cells[0].height + 10)

    ref_w = sum(im.width for im, _ in refs) + 12 * len(refs)
    mid_w = sum(im.width for im, _ in mids) + 12 * len(mids)
    W = max(ref_w, mid_w, grid_w) + 24
    lines = [
        ("%s: %s, %.2f MB, %s tris, %s joints (63 GF_Hero_v1 + %d x_ extras), %d clips, one single-sided material with %s PNGs" % (
            hero.get("glb"), "OK" if hero.get("ok") else "FAILED", (hero.get("bytes") or 0) / 1e6, val.get("tris"), val.get("joints"),
            len(val.get("extra_bones", [])), len(val.get("clips", [])),
            " / ".join("%s %d" % (t["role"], t["px"][0]) for t in val.get("textures", []))), OKC if hero.get("ok") else BAD),
        ("validate_glb (the CI gate) %s, %d warning(s): %s" % ("OK" if val.get("ok") else "FAILED", len(val.get("warnings", [])),
                                                             "; ".join(val.get("warnings", [])) or "-"), FG),
        ("source fidelity %.1e (every joint, every clip, first / middle / last frame); bind pose %.1e; Blender re-import %s: %d clips played, pose error %.1e" % (
            hero.get("source_fidelity", {}).get("max_error", -1), val.get("bind_pose_max_error", -1), "OK" if bi.get("ok") else "FAILED",
            bi.get("clips_played", 0), bi.get("clip_pose_max_error", -1)), FG),
        ("weapon %s (the weapon track's file, attached as shipped): identity child of weapon_R, rest error %.1e, rides weapon_R through fire_heavy f6 (%.1e)" % (
            bw.get("file"), bw.get("attach_rest_error", -1), bw.get("attach_fire_heavy_f6_error", -1)), FG),
        ("references: the approved concept (hero front, mirrored so the cannon is on his right, decisions[cannon_side_and_anvil_plate]), the turnaround sheet, the stage-1 TRELLIS.2 blockout s202", DIM),
        ("status: ai_final_pending_user_approval - the user's final visual approval is the remaining gate", GOLD),
    ]
    head_h = 44 + 18 * len(lines) + 8
    total = head_h + (H + 30) + (HM + 30) + 34 + grid_h + 10
    out = Image.new("RGB", (W, total), BG)
    d = ImageDraw.Draw(out)
    d.text((12, 8), "Valdris - stage 5: the shipped files next to the concept and the blockout", fill=FG, font=BIG)
    y = 42
    for t, col in lines:
        d.text((12, y), t, fill=col, font=SMALL)
        y += 18
    y = head_h
    x = 12
    for im, cap in refs:
        out.paste(im, (x, y + 18))
        d.text((x, y), cap, fill=DIM, font=SMALL)
        x += im.width + 12
    y += H + 30
    x = 12
    d.text((12, y - 4), "the shipped valdris.glb + colossus_cannon.glb, re-imported, %s f%d (the combat guard)" % (g["clip"], g["frame"]), fill=FG, font=SMALL)
    for im, cap in mids:
        yy = y + 14 + (HM - im.height) // 2 if im.height < HM else y + 14
        out.paste(im, (x, yy))
        if cap:
            d.text((x, yy + im.height + 4), cap, fill=DIM, font=SMALL)
        x += im.width + 12
    y += HM + 30
    d.text((12, y + 4), "every review shot through the client camera (55 deg, 22 m view height, true 1080p pixels), yaw 0", fill=FG, font=SMALL)
    y += 30
    for i, c in enumerate(cells):
        out.paste(c, (12 + (i % per_row) * (c.width + 10), y + (i // per_row) * (c.height + 10)))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "valdris_board.png")
    buf = io.BytesIO()
    out.quantize(colors=256, method=Image.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    with open(path, "wb") as fh:
        fh.write(buf.getvalue())
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (buf.tell() / 1e6), out.size)


if __name__ == "__main__":
    main()
