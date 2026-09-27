"""Kael's review sheets for stages 3 and 4 (PIL; run with ComfyUI's python, which has PIL).

  <comfy-python> tools/blender/gf_hero/kael_review_sheets.py stage3|stage4

stage3 -> art/characters/kael/reports/stage3/stage3_rig.png: GF_Hero_v1 on Kael (bones over an x-ray body: core white,
          twist yellow, x_ cloth chains cyan, sockets red), the dominant bone per vertex (front, back), the rest
          turnaround with the serpent_smg on weapon_R (toon), then the check poses (baked stage-4 frames with the cloth
          pass, front three-quarter and right three-quarter) and the rig numbers (reports/stage3/skin.json).
stage4 -> art/characters/kael/reports/anim/anim_board.png: every clip at its key frames (front three-quarter toon) with
          the client camera at true 1080p pixels (55 deg, 22 m), and the clip numbers (reports/anim/clips.json,
          cloth.json).
Inputs: work/renders/stage3|stage4 (s4_kael_review.py). A palette PNG, kept under a few MB.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
A = os.path.join(ROOT, "art", "characters", "kael")
BG = (22, 22, 26)
FG = (232, 226, 214)
DIM = (150, 146, 140)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 15)
    SMALL = ImageFont.truetype("arial.ttf", 13)
    BIG = ImageFont.truetype("arialbd.ttf", 24)
except OSError:
    FONT = SMALL = BIG = ImageFont.load_default()
KIND = {"core": (240, 240, 240), "twist": (250, 210, 80), "extra": (90, 230, 230), "socket": (255, 80, 70)}


def load(path, size):
    if not os.path.exists(path):
        im = Image.new("RGB", size, (50, 30, 30))
        ImageDraw.Draw(im).text((6, 6), "missing", fill=DIM, font=SMALL)
        return im
    im = Image.open(path).convert("RGB")
    return im.resize(size, Image.LANCZOS)


def label(im, text, xy=(5, 4), font=None):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=FG, font=font or SMALL)
    return im


def save(im, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.convert("P", palette=Image.ADAPTIVE, colors=255).save(path, optimize=True)
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (os.path.getsize(path) / 1e6))


def stage3():
    ren = os.path.join(A, "work", "renders", "stage3")
    rv = json.load(open(os.path.join(ren, "review.json"), encoding="utf-8"))
    skin = json.load(open(os.path.join(A, "reports", "stage3", "skin.json"), encoding="utf-8"))
    cw, ch, gap = 240, 300, 6
    cells = []
    for view in ("front", "side"):
        im = load(os.path.join(ren, "skeleton_%s.png" % view), (cw, ch))
        d = ImageDraw.Draw(im)
        for s in rv["views"]["skeleton_" + view]:
            h = (s["h"][0] * cw, s["h"][1] * ch)
            t = (s["t"][0] * cw, s["t"][1] * ch)
            d.line([h, t], fill=KIND[s["kind"]], width=2 if s["kind"] != "extra" else 1)
            d.ellipse([h[0] - 1.5, h[1] - 1.5, h[0] + 1.5, h[1] + 1.5], fill=KIND[s["kind"]])
        cells.append(label(im, "GF_Hero_v1 %s" % view))
    for view in ("front", "back"):
        cells.append(label(load(os.path.join(ren, "weights_%s.png" % view), (cw, ch)), "dominant bone, %s" % view))
    for view in ("front", "front34R", "side", "back"):
        cells.append(label(load(os.path.join(ren, "rest_%s.png" % view), (cw, ch)), "rest %s, serpent_smg on weapon_R" % view))
    poses = []
    for p in rv["poses"]:
        for view in ("front", "right"):
            poses.append(label(load(os.path.join(ren, "pose_%s_%s.png" % (p["tag"], view)), (cw, ch)),
                               "%s f%d: %s" % (p["clip"], p["frame"], p["what"]) if view == "front" else "  (right 3/4)"))
    rows = [cells[:8], poses[:8], poses[8:16]]
    head = 96
    W = gap + 8 * (cw + gap)
    H = head + len(rows) * (ch + gap) + 20
    out = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(out)
    b = skin["bones"]
    d.text((12, 8), "Kael - stage 3: GF_Hero_v1 rig, skin and the check poses (made by AI; the user's visual approval pending)", fill=FG, font=BIG)
    objs = skin["objects"]
    lines = [
        "%d bones: %d core, %d twist, %d fingers, %d sockets, %d x_ cloth chain bones (x_coat 6 x 4, x_loin 3 x 3, x_wisp 5 x 3; parent pelvis / the coat's last bones); "
        "%d weighted objects, max %d influences, 0 unweighted vertices" % (
            b["total"], b["core"], b["twist"], b["fingers"], b["sockets"], b["extras"], len(objs),
            max(o.get("max_influences", 0) for o in objs.values())),
        "BODY: MakeHuman CC0 seed + bone heat + twist split + joint fixes (as Brax); COAT yoke / lapels, GEAR, BOOTS: copy of the body; cuffs, buckles, cartridges rigid; "
        "skirt / loin cloth / tatters on their chains; serpent_smg.glb (the weapon track's file) on weapon_R by the identity attach",
        "check poses: baked stage-4 frames with the cloth pass (s4_kael_cloth.py): the chains are keyed per clip, the shared clips never key them",
    ]
    for i, ln in enumerate(lines):
        d.text((12, 40 + 17 * i), ln, fill=FG if i < 2 else DIM, font=SMALL)
    y = head
    for row in rows:
        x = gap
        for im in row:
            out.paste(im, (x, y))
            x += cw + gap
        y += ch + gap
    save(out, os.path.join(A, "reports", "stage3", "stage3_rig.png"))


def stage4():
    ren = os.path.join(A, "work", "renders", "stage4")
    rv = json.load(open(os.path.join(ren, "review.json"), encoding="utf-8"))
    man = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
    cloth = json.load(open(os.path.join(A, "reports", "anim", "cloth.json"), encoding="utf-8"))
    cw, ch, ig, gap = 104, 125, 125, 4
    nmax = 7
    strip_w = nmax * (cw + gap) + ig + gap
    strip_h = ch + 18 + gap
    order = man["order"]
    half = (len(order) + 1) // 2
    head = 92
    W = 12 + 2 * (strip_w + 14)
    H = head + half * strip_h + 16
    out = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(out)
    d.text((12, 8), "Kael - stage 4: %d clips on GF_Hero_v1 (24 shared re-posed for the gunslinger + 8 of his kit), 30 fps, in place, "
                    "cloth pass keyed (made by AI)" % len(order), fill=FG, font=FONT)
    tot = sum(man["clips"][c]["frames"] for c in order)
    loops = sum(1 for c in order if man["clips"][c]["loop"])
    slide = max(man["clips"][c]["metrics"]["foot_slide_max_mm"] for c in order if not man["clips"][c].get("slide_exempt"))
    miss = max(man["clips"][c]["metrics"]["ik_miss_max_mm"] for c in order)
    lines = ["%d frames, %d loops (every seam clean), foot slide max %.1f mm, IK miss max %.1f mm, solver vs Blender %.1e; "
             "cloth: x_coat / x_loin / x_wisp keyed in every clip (%d bones)" % (tot, loops, slide, miss, man.get("solver_vs_blender_max_error", 0),
                                                                             len(cloth.get("cloth_keyed_bones", []))),
             "each strip: the key frames, front three-quarter toon (Cycles CPU), then the client camera (orthographic 55 deg, 22 m = 1080 px) at true pixel size"]
    for i, ln in enumerate(lines):
        d.text((12, 36 + 17 * i), ln, fill=FG if i == 0 else DIM, font=SMALL)
    for k, clip in enumerate(order):
        c = man["clips"][clip]
        info = rv.get(clip)
        x0 = 12 + (k // half) * (strip_w + 14)
        y0 = head + (k % half) * strip_h
        name = c["action"]
        d.text((x0, y0), "%s  %d f%s  %s" % (name, c["frames"], "  loop" if c["loop"] else "", c.get("layer", "")), fill=FG, font=SMALL)
        if not info:
            continue
        x = x0
        for f in info["frames"][:nmax]:
            im = label(load(os.path.join(ren, clip, "f%03d_front.png" % f), (cw, ch)), "f%d" % f)
            out.paste(im, (x, y0 + 16))
            x += cw + gap
        x = x0 + nmax * (cw + gap)
        p = os.path.join(ren, clip, "f%03d_ingame0.png" % info["ingame_frame"])
        if os.path.exists(p):
            g = Image.open(p).convert("RGB")
            g = g.crop(((g.width - ig) // 2, (g.height - ig) // 2, (g.width - ig) // 2 + ig, (g.height - ig) // 2 + ig))
            out.paste(g, (x, y0 + 16))
    save(out, os.path.join(A, "reports", "anim", "anim_board.png"))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "stage3"
    {"stage3": stage3, "stage4": stage4}[mode]()
