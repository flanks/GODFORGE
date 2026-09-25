"""The Bellows art-review fix: the before / after sheet (PIL + numpy, no Blender; run with ComfyUI's python).

    python the_bellows_fix_sheet.py --before-review DIR --views DIR [--after-review DIR]
        -> art/enemies/the_bellows/reports/the_bellows_review_fix.png + the_bellows_review_fix.json

  --before-review  work/review of the pre-fix build (commit 46a1f3d): the_bellows_hero_p1_turn_34.png,
                   the_bellows_size.png, the_bellows_ingame_p1_22.png
  --after-review   work/review of this build (default art/enemies/the_bellows/work/review)
  --views          the_bellows_fix_views.py output for both builds: {before,after}_ground.json,
                   {before,after}_side_*.png, {before,after}_sil_game22.png

The review (5.5/10) had three must-fix items; the sheet answers each one with the same renders of both builds:
  1. the mask read as a cartoon mascot -> 3/4 hero, front and in-game (1x, shown x3) crops of the face;
  2. the game-camera silhouette was a teardrop hanging from a ring (a locket) -> game-size silhouettes and the
     true-pixel in-game frame;
  3. clips went through the floor -> side views of the deepest frames against the floor, and the lowest paw and
     head (mask, rays, horn, shard) z of every clip, measured on the skinned mesh on every frame.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "comfy"))
import gf_img  # noqa: E402

PACK = os.path.join(ROOT, "art", "enemies", "the_bellows")
BG, PANEL, INK, DIM, ACCENT = (30, 27, 33), (40, 36, 44), (232, 226, 212), (160, 152, 140), (242, 193, 78)
BAD, GOOD = (235, 120, 110), (140, 210, 150)
W = 1600
MAX_BYTES = 1_900_000
CLIPS = ["idle@loop", "move@loop", "windup", "attack", "hit", "radial", "summon", "strike_ring", "phase2",
         "idle_p2@loop", "move_p2@loop", "windup_p2", "attack_p2", "hit_p2", "radial_p2", "summon_p2",
         "strike_ring_p2", "strike_circle", "death"]
# the review's numbers (clip, what, review's depth in m)
CITED = [("move@loop", "paw", 0.22), ("strike_ring", "head", 0.44), ("summon", "head", 0.88), ("death", "head", 1.25)]
SIDE = ["move_loop_36", "strike_ring_30", "summon_19", "death_90"]
SIDE_LABEL = ["move@loop f36", "strike_ring f30 (the slam)", "summon f19 (a heave)", "death f90 (the end)"]
TOL = 0.005                     # below -5 mm counts as under the floor


def fmt(v):
    """Metres with a sign; a solved-to-zero -0.0003 prints as +0.00, not -0.00."""
    return "%+.2f" % (0.0 if abs(v) < 0.005 else v)


def opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def img(path, h=None, scale=None, crop=None):
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if scale:
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    if h and im.height != h:
        im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
    return im


def ground_rows(views):
    out = {}
    for tag in ("before", "after"):
        g = json.load(open(os.path.join(views, "%s_ground.json" % tag), encoding="utf-8"))
        out[tag] = {c: {"paw": g[c]["paw_min_z"], "head": g[c]["head_min_z"], "body": g[c]["body_min_z"]}
                    for c in CLIPS if c in g}
    return out


class Sheet:
    def __init__(self):
        self.parts = []            # (kind, payload, height)

    def add(self, kind, payload, h):
        self.parts.append((kind, payload, h))

    def render(self, title, subtitle):
        H = 74 + sum(h for _k, _p, h in self.parts) + 10
        sheet, d = gf_img.new_sheet(W, H, BG)
        gf_img.text(d, (14, 12), title, 30, True, ACCENT)
        gf_img.text(d, (14, 50), subtitle, 15, False, DIM)
        y = 74
        for kind, p, h in self.parts:
            if kind == "section":
                d.rectangle((6, y + 2, W - 6, y + h - 4), fill=PANEL)
                gf_img.text(d, (14, y + 8), p, 18, True, INK)
            elif kind == "row":
                x = 14
                tag, ims, notes = p
                gf_img.text(d, (x, y + 4), tag, 16, True, BAD if tag == "BEFORE" else GOOD)
                x += 92
                for im, lab in ims:
                    sheet.paste(im, (x, y + 4))
                    if lab:
                        gf_img.text(d, (x + 4, y + im.height + 6), lab, 13, False, DIM)
                    x += im.width + 12
                ty = y + 6
                for line in notes:
                    gf_img.text(d, (x + 6, ty), line, 14, False, INK)
                    ty += 20
            elif kind == "table":
                self._table(d, y, p)
            elif kind == "notes":
                ty = y + 4
                for line, col in p:
                    gf_img.text(d, (14, ty), line, 14, False, col)
                    ty += 20
            y += h
        return sheet

    @staticmethod
    def _table(d, y, rows):
        x0, cw = 214, (W - 214 - 16) / len(CLIPS)
        for i, c in enumerate(CLIPS):
            gf_img.text(d, (x0 + i * cw + cw / 2, y + 4), c.replace("@loop", "@l").replace("strike_", "s_"), 12,
                        False, DIM, anchor="ma")
        for r, (label, tag, key) in enumerate((("paws, before", "before", "paw"), ("paws, after", "after", "paw"),
                                               ("mask, before", "before", "head"), ("mask, after", "after", "head"))):
            yy = y + 26 + r * 22
            gf_img.text(d, (14, yy), "lowest %s (m)" % label, 13, True, INK)
            for i, c in enumerate(CLIPS):
                v = rows[tag][c][key]
                gf_img.text(d, (x0 + i * cw + cw / 2, yy), fmt(v), 13, False, BAD if v < -TOL else GOOD,
                            anchor="ma")


def save_small(sheet, out):
    im = sheet
    while True:
        im.save(out, optimize=True)
        if os.path.getsize(out) <= MAX_BYTES:
            return im.size, os.path.getsize(out)
        im = im.resize((int(im.width * 0.92), int(im.height * 0.92)), Image.LANCZOS)


def main():
    argv = sys.argv[1:]
    before = opt(argv, "--before-review")
    after = opt(argv, "--after-review", os.path.join(PACK, "work", "review"))
    views = opt(argv, "--views")
    g = ground_rows(views)
    s = Sheet()

    # 1. the face
    s.add("section", "1. The mask: a stern wind god, not a mascot (3/4 hero, front, in-game 1x crop shown x3)", 34)
    notes = {
        "BEFORE": ["Black eye blobs with white pupils,", "V-brows, a pig-snout O-nozzle, puffed",
                   "cheeks; bright white: the most comic", "shape on screen."],
        "AFTER": ["A carved relief face: one heavy brow", "shelf, HOLLOW sockets lit cold gold",
                  "(no pupils), a straight Greek nose,", "a hard mouth slit clenching a curled",
                  "bronze war-horn (its bell opens to the", "side: no O on the chin).",
                  "Porcelain a step darker, soot in every", "cavity and on the lips, verdigris",
                  "tear-streaks from the sockets."]}
    # the in-game face crops (1x pixels): the new, taller carved face sits ~25 px higher in the frame
    for tag, d_, fc in (("BEFORE", before, (545, 435, 655, 545)), ("AFTER", after, (545, 410, 655, 520))):
        ims = [(img(os.path.join(d_, "the_bellows_hero_p1_turn_34.png"), 330, crop=(40, 300, 400, 660)),
                "3/4 hero"),
               (img(os.path.join(d_, "the_bellows_size.png"), 330, crop=(200, 150, 560, 510)), "front"),
               (img(os.path.join(d_, "the_bellows_ingame_p1_22.png"), 330, scale=3, crop=fc),
                "in-game 1x (x3)")]
        s.add("row", (tag, ims, notes[tag]), 330 + 30)

    # 2. the silhouette
    s.add("section", "2. The game-camera silhouette: no ring handle (22 m view, true pixels)", 34)
    frame = (340, 40, 860, 640)
    ims = [(img(os.path.join(views, "before_sil_game22.png"), 380), "before: a teardrop from a ring"),
           (img(os.path.join(views, "after_sil_game22.png"), 380), "after: forked grips, a curled horn"),
           (img(os.path.join(before, "the_bellows_ingame_p1_22.png"), 380, crop=frame), "before, in-game 1x"),
           (img(os.path.join(after, "the_bellows_ingame_p1_22.png"), 380, crop=frame), "after, in-game 1x")]
    s.add("row", ("", ims, []), 380 + 30)
    s.add("notes", [("The ring grip closed the outline into a locket bail. It is replaced by TWIN FORKED HANDLES "
                     "splayed 27 deg off the lid's rear rim (the bellows' grips as an open V), and the horn curls "
                     "to the creature's right,", INK),
                    ("so the chin no longer ends in a centred stem. The collider and the body are unchanged; the "
                     "footprint is 5.5 x 9.2 m, horn to grips (was 5.5 x 9.0 m, mask to ring).", INK)], 48)

    # 3. the floor
    s.add("section", "3. Ground contact: the paws planted at z = 0 (IK), the mask always above the floor", 34)
    for tag in ("before", "after"):
        ims = [(img(os.path.join(views, "%s_side_%s.png" % (tag, n)), 280), lab) for n, lab in zip(SIDE, SIDE_LABEL)]
        s.add("row", (tag.upper(), ims, []), 280 + 30)
    s.add("table", g, 26 + 4 * 22 + 8)
    cited = []
    for c, key, depth in CITED:
        b, a = g["before"][c][key], g["after"][c][key]
        cited.append("%s %s: review %.2f m under, measured %s -> %s m" % (c, "paws" if key == "paw" else "mask",
                                                                        depth, fmt(b), fmt(a)))
    s.add("notes", [("; ".join(cited[:2]), INK), ("; ".join(cited[2:]), INK),
                    ("Every clip is re-solved per frame after keying: the body rises if the lung or a leg would touch "
                     "the floor, two-bone IK plants each paw's lowest vertex at z = 0 (the walk", DIM),
                    ("loops move each paw on a lateral-sequence plan), the head pitches up just enough to keep the "
                     "mask, rays and horn 4 cm clear, and the fallen cheek shard lies on the floor.", DIM),
                    ("Measured here on the skinned mesh of both .blend files, every frame of all 19 clips (red: below "
                     "-5 mm; 'mask' = the head and the cheek shard, so phase2's 0.00 is the shard lying on the floor).",
                     DIM), ("The build itself fails if any clip goes through the floor.", DIM)], 6 * 20 + 12)

    sheet = s.render("The Bellows - art review fixes (before / after)",
                     "review 5.5/10, three must-fix items: the mascot mask, the locket silhouette, clips through the "
                     "floor | pre-fix build 46a1f3d vs this build")
    out = os.path.join(PACK, "reports", "the_bellows_review_fix.png")
    size, nbytes = save_small(sheet, out)
    rep = {"review_items": ["mask read as a cartoon mascot", "silhouette read as a locket (ring handle)",
                            "clips through the floor"],
           "ground_min_z_m": g, "floor_tolerance_m": TOL,
           "clips_below_floor": {t: sorted(c for c, r in g[t].items() if min(r["paw"], r["head"], r["body"]) < -TOL)
                                 for t in g},
           "cited": cited, "sheet": {"path": os.path.relpath(out, ROOT).replace("\\", "/"), "size": list(size),
                                     "bytes": nbytes}}
    with open(os.path.join(PACK, "reports", "the_bellows_review_fix.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, indent=1)
        f.write("\n")
    print("wrote", out, size, "%.2f MB" % (nbytes / 1e6))
    print("below the floor:", rep["clips_below_floor"])


if __name__ == "__main__":
    main()
