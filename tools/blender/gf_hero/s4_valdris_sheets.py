"""Stage 4, Valdris: contact sheets (PIL; run with ComfyUI's python, which has PIL and numpy).

  <comfy-python> tools/blender/gf_hero/s4_valdris_sheets.py [--only clip,clip]

Adapted from s4_sheets.py (Brax) with Valdris's measures. Reads work/renders/stage4/<clip>/ (s4_valdris_render.py),
reports/anim/clips.json (s4_anim.py), reports/anim/render_checks.json (the every-frame audit) and reports/anim/cloth.json
(the cloth pass), and writes art/characters/valdris/reports/anim/:
  <clip>.png          one sheet per clip: the key frames as close-ups (front three-quarter + side over a 0.5 m ground
                      grid), through the client camera at true pixel size (yaw 0 and 90 at 1x, yaw 0 at 3x nearest), the
                      feet (ball height over time and the world-space ball track, contacts thick), and the clip's numbers
  anim_board_<n>.png  every clip at game size (key frames through the client camera at 1x and 2x), next to the concept
Every sheet is a 256-colour palette PNG.
"""
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KEY = "valdris"
ONLY = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
A = os.path.join(ROOT, "art", "characters", KEY)
REN = os.path.join(A, "work", "renders", "stage4")
OUT = os.path.join(A, "reports", "anim")
MAN = json.load(open(os.path.join(OUT, "clips.json"), encoding="utf-8"))
CK = json.load(open(os.path.join(OUT, "render_checks.json"), encoding="utf-8"))["clips"]
CL = json.load(open(os.path.join(OUT, "cloth.json"), encoding="utf-8"))["clips"] if os.path.exists(os.path.join(OUT, "cloth.json")) else {}
CONCEPT = os.path.join(A, "references", "valdris_concept_front_mirrored.png")
SHEET = os.path.join(A, "references", "VALDRIS_sheet_turnaround.jpg")
BLOCKOUT = os.path.join(A, "reports", "blockout", "blockout_selected.png")
BG = (24, 24, 28)
FG = (232, 226, 214)
DIM = (150, 146, 140)
WARN = (255, 170, 110)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 17)
    SMALL = ImageFont.truetype("arial.ttf", 13)
    BIG = ImageFont.truetype("arialbd.ttf", 24)
except OSError:
    FONT = SMALL = BIG = ImageFont.load_default()


def load(path, size=None):
    if not os.path.exists(path):
        im = Image.new("RGB", size or (100, 100), (40, 20, 20))
        ImageDraw.Draw(im).text((6, 6), "missing", fill=FG, font=SMALL)
        return im
    im = Image.open(path).convert("RGB")
    return im.resize(size, Image.LANCZOS) if size else im


def save(im, name):
    path = os.path.join(OUT, name)
    buf = io.BytesIO()
    im.convert("RGB").quantize(colors=256, method=Image.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (buf.tell() / 1e6), im.size)


def centre_crop(im, w, h):
    """A w x h window of a client-camera render centred on the hero (pixels away from the floor colour, which fills the
    corners), clamped to the image."""
    px = im.load()
    bg = px[2, 2]
    xs, ys = [], []
    for y in range(im.height):
        for x in range(im.width):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 40:
                xs.append(x)
                ys.append(y)
    if not xs:
        cx, cy = im.width // 2, im.height // 2
    else:
        cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    x0 = max(0, min(im.width - w, cx - w // 2))
    y0 = max(0, min(im.height - h, cy - h // 2))
    return im.crop((x0, y0, x0 + w, y0 + h))


def label(im, text, xy=(4, 3), font=None, fill=FG):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=fill, font=font or SMALL)
    return im


def foot_plot(m, w, h):
    """Left: ball height over the clip (L orange, R cyan). Right: the ball's WORLD track (hero space + travel), top view;
    frames in contact drawn thick, so a planted foot is a dot and a sliding one a smear."""
    im = Image.new("RGB", (w, h), (30, 30, 36))
    d = ImageDraw.Draw(im)
    cols = {"L": (255, 160, 70), "R": (90, 200, 255)}
    n = len(m["feet"]["L"]["ball_z"])
    pw = w // 2 - 10
    zmax = max(0.35, max(max(m["feet"][s]["ball_z"]) for s in "LR"))
    d.text((6, 4), "ball height (0-%.2f m) over %d frames" % (zmax, n - 1), fill=DIM, font=SMALL)
    y0 = h - 14
    d.line((6, y0, 6 + pw, y0), fill=(80, 80, 90))
    for s in "LR":
        zs = m["feet"][s]["ball_z"]
        pts = [(6 + pw * i / max(1, n - 1), y0 - (h - 40) * z / zmax) for i, z in enumerate(zs)]
        d.line(pts, fill=cols[s], width=2)
        for a, b, _mm in m["feet"][s]["contact_intervals"]:
            a2, b2 = a % n, min(b, n - 1)
            yy = y0 + 4 + (0 if s == "L" else 4)
            d.line((6 + pw * a2 / max(1, n - 1), yy, 6 + pw * b2 / max(1, n - 1), yy), fill=cols[s], width=3)
    x0 = w // 2 + 4
    pts_all = [p for s in "LR" for p in m["feet"][s]["world_xy"]]
    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 0.6)
    sc = min(pw, h - 30) / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    d.text((x0, 4), "ball WORLD track, top view (%.1f m box; thick = contact)" % span, fill=DIM, font=SMALL)

    def Pt(p):
        return (x0 + pw / 2 + (p[0] - cx) * sc, 22 + (h - 30) / 2 + (p[1] - cy) * sc)
    for s in "LR":
        wp = m["feet"][s]["world_xy"]
        d.line([Pt(p) for p in wp], fill=tuple(c // 2 for c in cols[s]), width=1)
        for a, b, _mm in m["feet"][s]["contact_intervals"]:
            seg = [Pt(wp[i % n]) for i in range(a, min(b, n - 1) + 1)]
            if len(seg) == 1:
                seg = seg * 2
            d.line(seg, fill=cols[s], width=5)
    return im


def text_block(name, info, w, h):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    m = info["metrics"]
    au = CK.get(name, {}).get("audit", {})
    cl = CL.get(name, {}).get("groups", {})
    lines = [("%d frames = %.2f s @ 30 fps%s, layer %s%s" % (info["frames"], info["duration_s"], ", LOOP" if info["loop"] else "",
                                                           info["layer"], (", base " + info["base"]) if info.get("base") else ""), FG)]
    if info["loop"]:
        lines.append(("loop seam %s: last - first %.4f deg / %.3f mm; accel through the seam %.2f deg (inside the clip up to %.2f)" % (
            "OK" if m["seam_ok"] else "ROUGH", m["loop_seam_deg"], m["loop_seam_pelvis_mm"], m["seam_accel_deg"],
            m["interior_accel_max_deg"]), FG if m["seam_ok"] else WARN))
    lines.append(("ball slide (planted, world) L %.1f / R %.1f mm; sole slip per contact L %s / R %s mm; pelvis drift %.0f mm" % (
        m["feet"]["L"]["slide_max_mm"], m["feet"]["R"]["slide_max_mm"], au.get("sole_slip_mm_per_contact_max", {}).get("L", "-"),
        au.get("sole_slip_mm_per_contact_max", {}).get("R", "-"), m["pelvis_horizontal_max_mm"]), FG))
    lines.append(("elbow max L %.0f / R %.0f deg (cannon clean <= 25-33); knee L %.0f / R %.0f; wrist swing %.2f; IK miss %.1f mm" % (
        m["elbow_flexion_max_deg"]["L"], m["elbow_flexion_max_deg"]["R"], m["knee_flexion_max_deg"]["L"],
        m["knee_flexion_max_deg"]["R"], m["wrist_swing_max_deg"], m["ik_miss_max_mm"]), FG))
    if au:
        lines.append(("every frame: plate clipping max %d (f%d, median %.0f), sliding lames max %d, cannon poke / cuts max %d / %d" % (
            au["clipping_max"], au["clipping_max_frame"], au["clipping_median"], au["sliding_max"], au["cannon_poke_max"],
            au["cannon_cuts_max"]), FG if au["clipping_max"] < 250 else WARN))
        lines.append(("cloth inside a plate (> 3 mm) max: cape %d, loincloth %d, braids %d; lowest solid %.0f mm, cloth %.0f mm" % (
            au["cape_inside_max"], au["loin_inside_max"], au["braids_inside_max"], au["lowest_solid_mm"], au["lowest_cloth_mm"]),
            FG if au["lowest_solid_mm"] > -25 else WARN))
        if cl:
            lines.append(("cloth pass (movable cloth after the clear, every frame): " + ", ".join(
                "%s %d inside (deepest %.0f mm, accel %.0f deg/f2)" % (g, r["inside_gt3mm_max"], r["deepest_mm"], r["accel_max_deg_per_frame2"])
                for g, r in cl.items()), DIM))
        if au.get("clipping_worst_pairs"):
            lines.append(("worst pairs: " + ", ".join("%s %d" % (p, c) for p, c in au["clipping_worst_pairs"][:3]), DIM))
    if info.get("design_speed_mps"):
        lines.append(("design speed %.2f m/s (travel %s)" % (info["design_speed_mps"], info["travel_mps"]), FG))
    if info["events"]:
        lines.append(("events: " + ", ".join("%s @%d" % kv for kv in sorted(info["events"].items(), key=lambda kv: kv[1])), FG))
    lines.append(("maps to: " + info["maps_to"], DIM))
    y = 6
    for t, c in lines:
        words = t.split(" ")
        cur = ""
        for wd in words:
            if d.textlength(cur + " " + wd, font=SMALL) > w - 16:
                d.text((8, y), cur, fill=c, font=SMALL)
                y += 16
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        d.text((8, y), cur, fill=c, font=SMALL)
        y += 17
    return im


def clip_sheet(name, info):
    frames = list(info["key_frames"])
    if info["loop"] and info["frames"] not in frames:
        frames.append(info["frames"])
    d_ = os.path.join(REN, name)
    CW, CH = 250, 300
    cols = []
    for f in frames:
        fr = load(os.path.join(d_, "f%03d_front.png" % f), (CW, CH))
        sd = load(os.path.join(d_, "f%03d_side.png" % f), (CW, CH))
        g0 = load(os.path.join(d_, "f%03d_ingame0.png" % f))
        g9 = load(os.path.join(d_, "f%03d_ingame90.png" % f))
        tag = "f%d" % f
        if info["loop"] and f == info["frames"]:
            tag += " = f0 (seam)"
        ev = [k for k, v in info["events"].items() if int(v) == f]
        if ev:
            tag += "  " + ",".join(ev)
        label(fr, tag, font=FONT)
        col = Image.new("RGB", (CW, CH * 2 + 6 + 140 + 4 + 325), BG)
        col.paste(fr, (0, 0))
        col.paste(sd, (0, CH + 3))
        y = CH * 2 + 6
        col.paste(centre_crop(g0, 120, 140), (0, y))
        col.paste(centre_crop(g9, 120, 140), (125, y))
        y += 140 + 4
        big = centre_crop(g0, 100, 130).resize((250, 325), Image.NEAREST)
        col.paste(big, (0, y))
        cols.append(col)
    W = max(1100, sum(c.width + 4 for c in cols))
    H = cols[0].height
    head = Image.new("RGB", (W, 78), BG)
    d = ImageDraw.Draw(head)
    d.text((12, 6), "%s  (%s)" % (info["action"], info["family"]), fill=FG, font=BIG)
    d.text((12, 38), info["purpose"], fill=(255, 214, 150), font=FONT)
    d.text((12, 58), "rows: front 3/4 close-up (0.5 m grid) | side | client camera 55 deg, true 1080p pixels (yaw 0 | yaw 90) | yaw 0 at 2.5x nearest",
           fill=DIM, font=SMALL)
    body = Image.new("RGB", (W, H), BG)
    x = 0
    for c in cols:
        body.paste(c, (x, 0))
        x += c.width + 4
    fp = foot_plot(info["metrics"], min(W // 2, 760), 240)
    tb = text_block(name, info, W - fp.width - 8, 240)
    foot = Image.new("RGB", (W, 244), BG)
    foot.paste(fp, (0, 2))
    foot.paste(tb, (fp.width + 8, 2))
    out = Image.new("RGB", (W, head.height + H + foot.height), BG)
    out.paste(head, (0, 0))
    out.paste(body, (0, head.height))
    out.paste(foot, (0, head.height + H))
    save(out, "%s.png" % name)


names = [n for n in MAN["order"] if (not ONLY or n in ONLY)]
for n in names:
    clip_sheet(n, MAN["clips"][n])

# ---- the game-size boards, next to the concept -----------------------------------------------------------------------
if not ONLY:
    ref = load(CONCEPT)
    ref = ref.resize((int(ref.width * 300 / ref.height), 300), Image.LANCZOS)
    sheet = load(SHEET)
    sheet = sheet.resize((int(sheet.width * 300 / sheet.height), 300), Image.LANCZOS)
    # the stage-1 blockout (sculpt reference): its lit front and its client-camera cell (the 5 x 2 grid of that sheet)
    bo = load(BLOCKOUT)
    cw, top = bo.width / 5.0, 37
    ch = (bo.height - top) / 2.0
    bo_front = bo.crop((int(cw), top, int(2 * cw), int(top + ch)))
    bo_game = bo.crop((int(4 * cw), int(top + ch), bo.width, bo.height))
    bo_front = bo_front.resize((int(bo_front.width * 300 / bo_front.height), 300), Image.LANCZOS)
    bo_game = bo_game.resize((int(bo_game.width * 300 / bo_game.height), 300), Image.LANCZOS)
    rows = []
    for n in MAN["order"]:
        info = MAN["clips"][n]
        frames = [f for f in info["key_frames"]][:8]
        cells = []
        for f in frames:
            g0 = load(os.path.join(REN, n, "f%03d_ingame0.png" % f))
            g9 = load(os.path.join(REN, n, "f%03d_ingame90.png" % f))
            c = Image.new("RGB", (100 * 2 + 4 + 180, 240), BG)
            c.paste(centre_crop(g0, 100, 136), (0, 52))
            c.paste(centre_crop(g9, 100, 136), (104, 52))
            c.paste(centre_crop(g0, 90, 120).resize((180, 240), Image.NEAREST), (208, 0))
            cells.append(c)
        line = Image.new("RGB", (230 + len(cells) * (c.width + 6), 244), BG)
        ImageDraw.Draw(line).text((6, 6), info["action"], fill=FG, font=FONT)
        ImageDraw.Draw(line).text((6, 30), "%d f%s, %s" % (info["frames"], " loop" if info["loop"] else "", info["family"]), fill=DIM, font=SMALL)
        x = 230
        for c in cells:
            line.paste(c, (x, 2))
            x += c.width + 6
        rows.append(line)
    per = 12
    for s in range(0, len(rows), per):
        ch = rows[s:s + per]
        W = max(max(r.width for r in ch), ref.width + sheet.width + bo_front.width + bo_game.width + 70)
        head = Image.new("RGB", (W, 380), BG)
        hd = ImageDraw.Draw(head)
        hd.text((12, 6), "Valdris - every clip at game size (%d-%d of %d)" % (s + 1, s + len(ch), len(rows)), fill=FG, font=BIG)
        hd.text((12, 36), "per key frame: client camera 55 deg at true 1080p pixels, yaw 0 and yaw 90 at 1x, then yaw 0 at 2x (nearest). "
                          "Top: the approved concept (resolved front, cannon on his right), the turnaround sheet, the stage-1 blockout "
                          "(lit front, client camera at 3x)", fill=DIM, font=SMALL)
        head.paste(ref, (12, 62))
        head.paste(sheet, (24 + ref.width, 62))
        head.paste(bo_front, (36 + ref.width + sheet.width, 62))
        head.paste(bo_game, (48 + ref.width + sheet.width + bo_front.width, 62))
        out = Image.new("RGB", (W, 380 + sum(r.height for r in ch)), BG)
        out.paste(head, (0, 0))
        y = 380
        for r in ch:
            out.paste(r, (0, y))
            y += r.height
        save(out, "anim_board_%d.png" % (s // per + 1))
