"""Stage 4 contact sheets (PIL; run with ComfyUI's python, which has PIL and numpy).

  <comfy-python> tools/blender/gf_hero/s4_sheets.py <key> [--only clip,clip]

Reads work/renders/stage4/<clip>/ (s4_render.py), reports/anim/clips.json (s4_anim.py) and reports/anim/render_checks.json
and writes art/characters/<key>/reports/anim/:
  <clip>.png          one sheet per clip: the key frames as close-ups (front three-quarter + side, on a 0.5 m ground
                      grid), through the client camera at true pixel size (yaw 0 and 90 at 1x, yaw 0 at 3x nearest),
                      the feet (ball height over time and the WORLD-space ball track with contacts drawn thick, so
                      sliding shows), and the clip's numbers (frames, loop seam, slide, wrist, gauntlet checks)
  anim_board_<n>.png  every clip at game size: its key frames at 1x and 2x through the client camera
Every sheet is a 256-colour palette PNG well under 2 MB.
"""
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KEY = sys.argv[1] if len(sys.argv) > 1 else "brax"
ONLY = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None
A = os.path.join(ROOT, "art", "characters", KEY)
REN = os.path.join(A, "work", "renders", "stage4")
OUT = os.path.join(A, "reports", "anim")
MAN = json.load(open(os.path.join(OUT, "clips.json"), encoding="utf-8"))
CK = json.load(open(os.path.join(OUT, "render_checks.json"), encoding="utf-8"))["clips"]
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
    """256-colour palette PNG (octree, no dither): the toon renders and pixel crops survive it, and 34+ sheets stay
    about a third of their RGB size in git."""
    path = os.path.join(OUT, name)
    buf = io.BytesIO()
    im.convert("RGB").quantize(colors=256, method=Image.FASTOCTREE, dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (buf.tell() / 1e6), im.size)


def label(im, text, xy=(4, 3), font=None, fill=FG):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=fill, font=font or SMALL)
    return im


def foot_plot(m, w, h, loop, travel):
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
            d.line((6 + pw * a2 / max(1, n - 1), y0 + 4 + (0 if s == "L" else 4), 6 + pw * b2 / max(1, n - 1), y0 + 4 + (0 if s == "L" else 4)), fill=cols[s], width=3)
    # world track
    x0 = w // 2 + 4
    pts_all = [p for s in "LR" for p in m["feet"][s]["world_xy"]]
    xs = [p[0] for p in pts_all]
    ys = [p[1] for p in pts_all]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 0.6)
    sc = min(pw, h - 30) / span
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    d.text((x0, 4), "ball WORLD track, top view (%.1f m box; thick = contact)" % span, fill=DIM, font=SMALL)

    def P(p):
        return (x0 + pw / 2 + (p[0] - cx) * sc, 22 + (h - 30) / 2 + (p[1] - cy) * sc)
    for s in "LR":
        wp = m["feet"][s]["world_xy"]
        d.line([P(p) for p in wp], fill=tuple(c // 2 for c in cols[s]), width=1)
        for a, b, _mm in m["feet"][s]["contact_intervals"]:
            seg = [P(wp[i % n]) for i in range(a, min(b, n - 1) + 1)]
            if len(seg) == 1:
                seg = seg * 2
            d.line(seg, fill=cols[s], width=5)
            d.ellipse((seg[0][0] - 3, seg[0][1] - 3, seg[0][0] + 3, seg[0][1] + 3), outline=cols[s])
    return im


def text_block(info, ck, w, h):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    m = info["metrics"]
    lines = []
    lines.append(("%d frames = %.2f s @ 30 fps%s, layer %s, weapon %s" % (
        info["frames"], info["duration_s"], ", LOOP" if info["loop"] else "", info["layer"], info["weapon"]), FG))
    if info["loop"]:
        lines.append(("loop seam %s: last - first frame %.4f deg / %.3f mm; accel through the seam %.2f deg, %.1f mm "
                      "(inside the clip up to %.2f deg, %.1f mm)" % (
                          "OK" if m["seam_ok"] else "ROUGH", m["loop_seam_deg"], m["loop_seam_pelvis_mm"], m["seam_accel_deg"],
                          m["seam_accel_mm"], m["interior_accel_max_deg"], m["interior_accel_max_mm"]), FG if m["seam_ok"] else WARN))
    sl = m["foot_slide_max_mm"]
    lines.append(("foot slide (world, in contact): L %.1f / R %.1f mm%s; ground %.1f mm" % (
        m["feet"]["L"]["slide_max_mm"], m["feet"]["R"]["slide_max_mm"], " (exempt: %s)" % info["notes"][:40] if info["slide_exempt"] else "",
        m["ground_penetration_mm"]), FG if (sl < 10 or info["slide_exempt"]) else WARN))
    lines.append(("in place: pelvis drift %.0f mm; IK miss %.1f mm; wrist swing %.2f deg; twist L %s R %s" % (
        m["pelvis_horizontal_max_mm"], m["ik_miss_max_mm"], m["wrist_swing_max_deg"], m["hand_twist_range_deg"]["L"],
        m["hand_twist_range_deg"]["R"]), FG))
    lines.append(("elbow flexion max L %.0f / R %.0f deg; knee L %.0f / R %.0f deg" % (
        m["elbow_flexion_max_deg"]["L"], m["elbow_flexion_max_deg"]["R"], m["knee_flexion_max_deg"]["L"], m["knee_flexion_max_deg"]["R"]), FG))
    if ck:
        cut = max(v.get("gauntlet_L_cuts_body", 0) + v.get("gauntlet_R_cuts_body", 0) for v in ck.values())
        touch = max(v.get("gauntlets_touch", 0) for v in ck.values())
        low = min(v["lowest_vertex_z_mm"] for v in ck.values())
        lines.append(("key frames: gauntlets cut body <= %d verts, gauntlets touch <= %d, lowest vertex %.0f mm" % (cut, touch, low),
                      FG if cut < 40 else WARN))
    if info.get("design_speed_mps"):
        lines.append(("design speed %.2f m/s (travel %s)" % (info["design_speed_mps"], info["travel_mps"]), FG))
    if info["events"]:
        lines.append(("events: " + ", ".join("%s @%d" % kv for kv in sorted(info["events"].items(), key=lambda kv: kv[1])), FG))
    lines.append(("maps to: " + info["maps_to"], DIM))
    y = 6
    for t, c in lines:
        # wrap long lines
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
        col = Image.new("RGB", (CW, CH * 2 + 6 + g0.height + 4 + CW), BG)
        col.paste(fr, (0, 0))
        col.paste(sd, (0, CH + 3))
        y = CH * 2 + 6
        col.paste(g0.crop((20, 0, 140, 160)) if g0.width >= 160 else g0, (0, y))
        col.paste(g9.crop((20, 0, 140, 160)) if g9.width >= 160 else g9, (125, y))
        y += g0.height + 4
        big = g0.crop((39, 30, 122, 113)).resize((249, 249), Image.NEAREST)
        col.paste(big, (0, y))
        cols.append(col)
    W = max(1100, sum(c.width + 4 for c in cols))
    H = cols[0].height
    head = Image.new("RGB", (W, 78), BG)
    d = ImageDraw.Draw(head)
    d.text((12, 6), "%s  (%s)" % (info["action"], info["family"]), fill=FG, font=BIG)
    d.text((12, 38), info["purpose"], fill=(255, 214, 150), font=FONT)
    d.text((12, 58), "rows: front 3/4 close-up (0.5 m grid) | side | client camera 55 deg, true 1080p pixels (yaw 0 | yaw 90) | yaw 0 at 3x nearest",
           fill=DIM, font=SMALL)
    body = Image.new("RGB", (W, H), BG)
    x = 0
    for c in cols:
        body.paste(c, (x, 0))
        x += c.width + 4
    fp = foot_plot(info["metrics"], min(W, 900), 220, info["loop"], info["travel_mps"])
    tb = text_block(info, CK.get(name), W - fp.width - 8, 220)
    foot = Image.new("RGB", (W, 224), BG)
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

# ---- the game-size board -----------------------------------------------------------------------------------------------
if not ONLY:
    rows = []
    for n in MAN["order"]:
        info = MAN["clips"][n]
        frames = [f for f in info["key_frames"]][:8]
        cells = []
        for f in frames:
            g0 = load(os.path.join(REN, n, "f%03d_ingame0.png" % f))
            g9 = load(os.path.join(REN, n, "f%03d_ingame90.png" % f))
            c = Image.new("RGB", (100 * 2 + 4 + 130, 160), BG)
            c.paste(g0.crop((30, 12, 130, 148)), (0, 12))
            c.paste(g9.crop((30, 12, 130, 148)), (104, 12))
            c.paste(g0.crop((47, 36, 112, 116)).resize((130, 160), Image.NEAREST), (208, 0))
            cells.append(c)
        line = Image.new("RGB", (190 + len(cells) * (c.width + 6), 164), BG)
        ImageDraw.Draw(line).text((6, 6), info["action"], fill=FG, font=FONT)
        ImageDraw.Draw(line).text((6, 30), "%d f%s" % (info["frames"], " loop" if info["loop"] else ""), fill=DIM, font=SMALL)
        x = 190
        for c in cells:
            line.paste(c, (x, 2))
            x += c.width + 6
        rows.append(line)
    per = 12
    for s in range(0, len(rows), per):
        ch = rows[s:s + per]
        W = max(r.width for r in ch)
        head = Image.new("RGB", (W, 56), BG)
        ImageDraw.Draw(head).text((12, 6), "%s - every clip at game size (%d-%d of %d)" % (KEY.capitalize(), s + 1, s + len(ch), len(rows)), fill=FG, font=BIG)
        ImageDraw.Draw(head).text((12, 36), "per key frame: client camera 55 deg at true 1080p pixels, yaw 0 and yaw 90 at 1x, then yaw 0 at 2x (nearest)", fill=DIM, font=SMALL)
        out = Image.new("RGB", (W, 56 + sum(r.height for r in ch)), BG)
        out.paste(head, (0, 0))
        y = 56
        for r in ch:
            out.paste(r, (0, y))
            y += r.height
        save(out, "anim_board_%d.png" % (s // per + 1))
