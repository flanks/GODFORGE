"""Stage 3 review sheets (PIL; run with ComfyUI's python, which has PIL and numpy).

  <comfy-python> tools/blender/gf_hero/s3_sheets.py <key>

Reads the renders of s3_poses.py (art/characters/<key>/work/renders/stage3/) and reports/stage3/poses.json, and writes
art/characters/<key>/reports/stage3/:
  stage3_skeleton.png   GF_Hero_v1 on the hero (bones over an x-ray body, sockets as RGB = XYZ grip axes) + weights
                        (dominant bone per vertex)
  stage3_poses_<n>.png  one row per validation pose: toon full body, clay close-ups (shoulder front / back, elbow,
                        knee, hands, head) with the weapon in slate blue, and the pose's numbers
  stage3_ingame.png     every pose through the client camera (orthographic 55 deg, 22 m, true 1080p pixels) at 1x and 3x
  stage3_weapon.png     the weapon on the sockets: bare vs gauntleted hands (fist clench, guard, forearm twist)
Every sheet stays under 2 MB (adaptive palette when a plain PNG would be larger).
"""
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
KEY = sys.argv[1] if len(sys.argv) > 1 else "brax"
A = os.path.join(ROOT, "art", "characters", KEY)
REN = os.path.join(A, "work", "renders", "stage3")
OUT = os.path.join(A, "reports", "stage3")
os.makedirs(OUT, exist_ok=True)
BG = (24, 24, 28)
FG = (232, 226, 214)
DIM = (150, 146, 140)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 18)
    SMALL = ImageFont.truetype("arial.ttf", 14)
    BIG = ImageFont.truetype("arialbd.ttf", 26)
except OSError:
    FONT = SMALL = BIG = ImageFont.load_default()
poses = json.load(open(os.path.join(OUT, "poses.json"), encoding="utf-8"))["poses"]
names = list(poses.keys())


def load(name, h=None, w=None):
    p = os.path.join(REN, name)
    if not os.path.exists(p):
        im = Image.new("RGB", (w or h or 100, h or 100), (40, 20, 20))
        ImageDraw.Draw(im).text((8, 8), "missing\n" + name, fill=FG, font=SMALL)
        return im
    im = Image.open(p).convert("RGB")
    if h and not w:
        im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
    elif w and h:
        im = im.resize((w, h), Image.LANCZOS)
    return im


def save(im, name):
    path = os.path.join(OUT, name)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    if buf.tell() > 1.9e6:
        buf = io.BytesIO()
        im.convert("P", palette=Image.ADAPTIVE, colors=256).save(buf, "PNG", optimize=True)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    print("wrote", os.path.relpath(path, ROOT), "%.2f MB" % (buf.tell() / 1e6), im.size)


def label(im, text, xy=(6, 4), font=None):
    d = ImageDraw.Draw(im)
    x, y = xy
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font or SMALL)
    d.text(xy, text, fill=FG, font=font or SMALL)
    return im


def header(width, title, sub):
    im = Image.new("RGB", (width, 64), BG)
    d = ImageDraw.Draw(im)
    d.text((14, 8), title, fill=FG, font=BIG)
    d.text((14, 40), sub, fill=DIM, font=SMALL)
    return im


def stack(rows, width):
    h = sum(r.height for r in rows)
    out = Image.new("RGB", (width, h), BG)
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out


# ---- skeleton + weights --------------------------------------------------------------------------------------------------
H = 520
row1 = [load("skeleton_front.png", H), load("skeleton_side.png", H), load("skeleton_head.png", H), load("skeleton_hand.png", H),
        load("skeleton_hand_front.png", H)]
row2 = [load("weights_dominant_front.png", H), load("weights_dominant_side.png", H), load("weights_dominant_back.png", H),
        load("weights_dominant_shoulder.png", H), load("weights_dominant_hand.png", H)]
labels1 = ["bones (red core, pink twist, green fingers, cyan root)", "side", "head / neck / sockets", "hand from above: fingers + weapon_L",
           "hand from the front"]
labels2 = ["dominant bone per vertex (front)", "side", "back", "shoulder", "hand"]
W = max(sum(i.width for i in row1), sum(i.width for i in row2))
rows = [header(W, "%s - GF_Hero_v1 on the stage-2 mesh" % KEY.capitalize(),
               "63 bones: 23 core, 6 twist (Copy Rotation), 30 finger, 4 sockets (weapon_R, weapon_L, head_top, chest_sigil; axes red X, green Y, blue Z = the grip frame)")]
for r, labs in ((row1, labels1), (row2, labels2)):
    line = Image.new("RGB", (W, H), BG)
    x = 0
    for im, lab in zip(r, labs):
        line.paste(label(im, lab), (x, 0))
        x += im.width
    rows.append(line)
save(stack(rows, W), "stage3_skeleton.png")

# ---- poses ---------------------------------------------------------------------------------------------------------------
CH = 250
views = ["full", "shoulder_front", "shoulder_back", "elbow", "knee", "hands", "head"]


def pose_row(i, name):
    tag = "pose_%02d_%s" % (i, name)
    cells = [load("%s_%s.png" % (tag, v), CH, round(CH * 560 / 640) if v == "full" else CH) for v in views]
    r = poses[name]
    wid = sum(c.width for c in cells) + 330
    line = Image.new("RGB", (wid, CH), BG)
    x = 0
    for c, v in zip(cells, views):
        line.paste(label(c, v if v != "full" else "%d %s" % (i, name), font=FONT if v == "full" else SMALL), (x, 0))
        x += c.width
    d = ImageDraw.Draw(line)
    txt = ["stretch max %.0f mm (p99.9 %.0f)" % (r["stretch_mm_max"], r["stretch_mm_p99_9"]),
           "edges >+40%%: %d   <-40%%: %d" % (r["edges_over_40pct"], r["edges_under_minus40pct"]),
           "collapsed verts: %d" % r["collapsed_verts_area_lt_0_4"],
           "body volume: %.3f" % r["volume_ratio"],
           "forearm section L/R: %.2f / %.2f" % (r["forearm_section_L"][0], r["forearm_section_R"][0])]
    for s in ("L", "R"):
        wr = r.get("weapon_" + s)
        if wr:
            txt.append("gauntlet %s: poke %d, cuts body %d" % (s, wr["poke_through"], wr["weapon_cuts_body"]))
    txt.append("weapon: %s" % r["weapon_variant"])
    for k, t in enumerate(txt):
        d.text((x + 12, 10 + k * 22), t, fill=FG if k else (255, 214, 150), font=SMALL)
    return line


rows_all = [pose_row(i, n) for i, n in enumerate(names, start=1)]
per = 5
for s in range(0, len(rows_all), per):
    chunk = rows_all[s:s + per]
    W = max(r.width for r in chunk)
    save(stack([header(W, "%s - validation poses %d-%d (GF_Hero_v1, anvil_gauntlets on weapon_L / weapon_R)" % (KEY.capitalize(), s + 1, s + len(chunk)),
                       "full: Cycles CPU toon review. close-ups: Workbench clay, gauntlets slate blue. Numbers: s3_poses.py (reports/stage3/poses.json)")]
                 + chunk, W), "stage3_poses_%d.png" % (s // per + 1))

# ---- in-game ---------------------------------------------------------------------------------------------------------------
cells = []
for i, n in enumerate(names, start=1):
    tag = "pose_%02d_%s" % (i, n)
    a = load(tag + "_ingame0.png")
    b = load(tag + "_ingame35.png")
    col = Image.new("RGB", (a.width * 3 + 8, a.height * 4 + 34), BG)
    col.paste(a, (0, 24))
    col.paste(b, (a.width + 4, 24))
    col.paste(a.resize((a.width * 3, a.height * 3), Image.NEAREST), (0, a.height + 30))
    ImageDraw.Draw(col).text((4, 3), "%d %s" % (i, n), fill=FG, font=SMALL)
    cells.append(col)
per_row = 7
lines = []
for s in range(0, len(cells), per_row):
    ch = cells[s:s + per_row]
    line = Image.new("RGB", (sum(c.width + 6 for c in ch), ch[0].height), BG)
    x = 0
    for c in ch:
        line.paste(c, (x, 0))
        x += c.width + 6
    lines.append(line)
W = max(l_.width for l_ in lines)
save(stack([header(W, "%s - validation poses through the client camera" % KEY.capitalize(),
                   "orthographic, 55 deg pitch, FixedVertical 22 m = 1080 px (true pixel size, 128 px crops): yaw 0 and 35 at 1x, yaw 0 at 3x (nearest)")] + lines, W),
     "stage3_ingame.png")

# ---- weapon on the sockets --------------------------------------------------------------------------------------------------
idx = {n: i for i, n in enumerate(names, start=1)}
pairs = []
for n in ("fist_clench", "guard", "forearm_twist"):
    if n in idx:
        tag = "pose_%02d_%s" % (idx[n], n)
        pairs.append((label(load(tag + "_hands_bare.png", 380), "%s: body only (fingers clenched)" % n),
                      label(load(tag + "_hands.png", 380), "%s: + anvil_gauntlets fist" % n)))
        if n == "forearm_twist":
            pairs.append((label(load(tag + "_forearm_bare.png", 380), "forearm twist 100 deg: body only"),
                          label(load("skeleton_hand.png", 380), "weapon_L grip frame at rest (R X, G Y fingers, B Z back of hand)")))
pairs.append((label(load("skeleton_socket_fist.png", 380), "the fist gauntlet on weapon_L at rest (frame drawn in front)"),
              label(load("skeleton_hand_front.png", 380), "hand bones + weapon_L from the front")))
line_w = max(a.width + b.width + 12 for a, b in pairs)
lines = []
for a, b in pairs:
    line = Image.new("RGB", (line_w, max(a.height, b.height)), BG)
    line.paste(a, (0, 0))
    line.paste(b, (a.width + 12, 0))
    lines.append(line)
grid = []
for s in range(0, len(lines), 2):
    ch = lines[s:s + 2]
    line = Image.new("RGB", (sum(c.width + 16 for c in ch), max(c.height for c in ch)), BG)
    x = 0
    for c in ch:
        line.paste(c, (x, 0))
        x += c.width + 16
    grid.append(line)
W = max(g.width for g in grid)
save(stack([header(W, "%s - the weapon on the sockets" % KEY.capitalize(),
                   "anvil_gauntlets (fist variant) held by Child Of on weapon_L / weapon_R with inverse SOCKET_TO_GRIP = the identity attach of the glTF contract")] + grid, W),
     "stage3_weapon.png")
