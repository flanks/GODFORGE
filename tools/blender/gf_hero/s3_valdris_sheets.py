"""Stage 3, Valdris: review sheets (Pillow; run with any Python that has PIL, e.g. ComfyUI's).

  <python> tools/blender/gf_hero/s3_valdris_sheets.py

Reads the renders of s3_valdris_poses.py (art/characters/valdris/work/renders/stage3/) and reports/stage3/{poses,limits,
gltf_check,skin}.json, and writes art/characters/valdris/reports/stage3/:
  stage3_skeleton.png   GF_Hero_v1 + his 53 x_ extras over an x-ray body (core red, twist pink, fingers green, driven helpers
                        orange, cape / loincloth chains violet, braids lime, sockets as RGB = XYZ grip axes) and the dominant
                        bone per vertex on every part (a rigid plate is one flat colour)
  stage3_poses_<n>.png  one row per validation pose: toon 3/4 front and back, clay close-ups (shoulder front / back, elbow,
                        knee, hips, head, cannon), and the pose's numbers
  stage3_ingame.png     every pose through the client camera (orthographic 55 deg, 22 m, true 1080p pixels) at 1x and 3x
  stage3_weapon.png     the colossus_cannon on weapon_R: the section along the barrel (rest and aimed), the arm in the
                        sleeve per pose, the identity-attach proof and the elbow range the sleeve allows
  stage3_limits.png     the range-of-motion sweeps (s3_valdris_limits.py) as small multiples
Every sheet stays under 2 MB (an octree 256-colour palette with dithering when a plain PNG would be larger).
"""
import io
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
A = os.path.join(ROOT, "art", "characters", "valdris")
REN = os.path.join(A, "work", "renders", "stage3")
OUT = os.path.join(A, "reports", "stage3")
BG = (24, 24, 28)
FG = (232, 226, 214)
DIM = (160, 156, 150)
HOT = (255, 214, 150)
try:
    FONT = ImageFont.truetype("arialbd.ttf", 18)
    SMALL = ImageFont.truetype("arial.ttf", 14)
    TINY = ImageFont.truetype("arial.ttf", 12)
    BIG = ImageFont.truetype("arialbd.ttf", 26)
except OSError:
    FONT = SMALL = TINY = BIG = ImageFont.load_default()


def jload(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return json.load(f)


POSES = jload("poses.json")["poses"]
NAMES = list(POSES.keys())
LIM = jload("limits.json")["sweeps"]
GL = jload("gltf_check.json")
SKIN = jload("skin.json")


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
        im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG).save(buf, "PNG", optimize=True)
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


def header(width, title, sub, sub2=None):
    im = Image.new("RGB", (width, 84 if sub2 else 64), BG)
    d = ImageDraw.Draw(im)
    d.text((14, 8), title, fill=FG, font=BIG)
    d.text((14, 40), sub, fill=DIM, font=SMALL)
    if sub2:
        d.text((14, 60), sub2, fill=DIM, font=SMALL)
    return im


def stack(rows, width):
    out = Image.new("RGB", (width, sum(r.height for r in rows)), BG)
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out


def hrow(cells, h, gap=0):
    line = Image.new("RGB", (sum(c.width for c in cells) + gap * (len(cells) - 1), h), BG)
    x = 0
    for c in cells:
        line.paste(c, (x, 0))
        x += c.width + gap
    return line


def skeleton(view, h):
    """The body pass dimmed, the bones pass (transparent film) composited on top."""
    bp = os.path.join(REN, "skeleton_%s_body.png" % view)
    kp = os.path.join(REN, "skeleton_%s_bones.png" % view)
    if not (os.path.exists(bp) and os.path.exists(kp)):
        return load("skeleton_%s.png" % view, h)
    body = Image.open(bp).convert("RGB")
    body = Image.blend(body, Image.new("RGB", body.size, BG), 0.45)
    bones = Image.open(kp).convert("RGBA")
    body.paste(bones, (0, 0), bones)
    return body.resize((round(body.width * h / body.height), h), Image.LANCZOS)


# ---- skeleton + weights --------------------------------------------------------------------------------------------------
H = 500
bones = SKIN["bones"]
r1 = [label(skeleton("front", H), "front"),
      label(skeleton("back", H), "back: the 5 x 5 cape chains"), label(skeleton("side", H), "side"),
      label(skeleton("head", H), "head: braid chains, head_top, chest_sigil"),
      label(skeleton("hand", H), "left hand: finger bones on the lame joints, weapon_L")]
r2 = [label(load("weights_dominant_front.png", H), "dominant bone per vertex (front)"), label(load("weights_dominant_back.png", H), "back"),
      label(load("weights_dominant_side.png", H), "side"), label(load("weights_dominant_shoulder.png", H), "shoulder: pauldron on x_pauldron"),
      label(load("weights_dominant_hand.png", H), "hand: one colour per finger lame"), label(load("weights_dominant_cape.png", H), "cape grid")]
W = max(sum(i.width for i in r1), sum(i.width for i in r2))
save(stack([header(W, "Valdris - GF_Hero_v1 on the stage-2 mesh (%d bones)" % bones["total"],
                   "%d contract bones (23 core, 6 twist, 30 finger, 4 sockets) + %d per-hero x_ extras: 9 driven helpers (pauldron, elbow, knee, "
                   "tasset L/R, fauld), cape 5 x 5, loincloth 3 x 3, braids 5 x 2" % (bones["total"] - bones["extras"], bones["extras"]),
                   "bones: core red, twist pink, fingers green, driven helpers orange, cape / loincloth violet, braids lime; sockets: RGB = the grip "
                   "frame's X Y Z (weapon_R holds the colossus_cannon by the identity attach; chest_sigil sits on the anvil's front face)"),
            hrow(r1, H), hrow(r2, H)], W), "stage3_skeleton.png")

# ---- poses ---------------------------------------------------------------------------------------------------------------
CH = 250
VIEWS = ["full", "back", "shoulder_front", "shoulder_back", "elbow", "knee", "hips", "head", "cannon"]


def pose_text(r):
    pl = r["plates"]
    t = [("clipping: %d new verts" % pl["clipping"], HOT)]
    for k, n in pl["clipping_worst"][:3]:
        t.append(("  %s %d" % (k, n), DIM))
    t.append(("sliding lames: %d   in suit: %d" % (pl["sliding"], pl["suit"]), FG))
    c = r["cloth"]
    t.append(("cloth inside: cape %d, loin %d, braids %d" % (c["cape"]["inside_gt3mm"], c["loin"]["inside_gt3mm"], c["braids"]["inside_gt3mm"]), FG))
    if "cannon" in r:
        t.append(("cannon: poke %d, cuts %d" % (r["cannon"]["poke_through"], r["cannon"]["cuts"]), FG))
    b = r["body"]
    t.append(("suit: collapsed %d (shoulders %d/%d), vol %.3f" % (b["collapsed_verts_area_lt_0_4"], b["collapsed_shoulder_L_R"][0],
                                                                  b["collapsed_shoulder_L_R"][1], b["volume_ratio"]), FG))
    if "helpers_off" in r:
        off = r["helpers_off"]["plates"]
        t.append(("helpers muted: clipping %d" % off["clipping"], DIM))
    return t


def pose_row(i, name):
    tag = "pose_%02d_%s" % (i, name)
    cells = []
    for v in VIEWS:
        vv = v if (v != "cannon" or os.path.exists(os.path.join(REN, "%s_cannon.png" % tag))) else "cape"
        im = load("%s_%s.png" % (tag, vv), CH, round(CH * 560 / 640) if vv in ("full", "back") else CH)
        cells.append(label(im, "%d %s" % (i, name) if vv == "full" else vv, font=FONT if vv == "full" else SMALL))
    line = Image.new("RGB", (sum(c.width for c in cells) + 360, CH), BG)
    x = 0
    for c in cells:
        line.paste(c, (x, 0))
        x += c.width
    d = ImageDraw.Draw(line)
    for k, (t, col) in enumerate(pose_text(POSES[name])):
        d.text((x + 10, 8 + k * 20), t, fill=col, font=TINY if t.startswith("  ") else SMALL)
    return line


rows_all = [pose_row(i, n) for i, n in enumerate(NAMES, start=1)]
per = 4
for s in range(0, len(rows_all), per):
    chunk = rows_all[s:s + per]
    W = max(r.width for r in chunk)
    save(stack([header(W, "Valdris - validation poses %d-%d (GF_Hero_v1 + x_ helpers, colossus_cannon on weapon_R)" % (s + 1, s + len(chunk)),
                       "full / back: Cycles CPU toon review. Close-ups: Workbench clay, the cannon slate blue, cloth red. Cape, loincloth and braids "
                       "posed clear by s3_valdris_cloth.py.",
                       "Numbers (reports/stage3/poses.json): new vertices of one piece inside another vs rest - clipping = different regions, "
                       "sliding = lames of one region, suit = a plate inside the under-suit")] + chunk, W),
         "stage3_poses_%d.png" % (s // per + 1))

# ---- in-game ---------------------------------------------------------------------------------------------------------------
cells = []
for i, n in enumerate(NAMES, start=1):
    tag = "pose_%02d_%s" % (i, n)
    a = load(tag + "_ingame0.png")
    b = load(tag + "_ingame35.png")
    col = Image.new("RGB", (a.width * 3 + 8, a.height * 4 + 34), BG)
    col.paste(a, (0, 24))
    col.paste(b, (a.width + 4, 24))
    col.paste(a.resize((a.width * 3, a.height * 3), Image.NEAREST), (0, a.height + 30))
    ImageDraw.Draw(col).text((4, 3), "%d %s" % (i, n), fill=FG, font=SMALL)
    cells.append(col)
lines = []
for s in range(0, len(cells), 5):
    lines.append(hrow(cells[s:s + 5], cells[0].height, gap=6))
W = max(l_.width for l_ in lines)
save(stack([header(W, "Valdris - validation poses through the client camera",
                   "orthographic, 55 deg pitch, FixedVertical 22 m = 1080 px (true pixel size, 176 px crops): yaw 0 and 35 at 1x, yaw 0 at 3x (nearest)")]
           + lines, W), "stage3_ingame.png")

# ---- the weapon ------------------------------------------------------------------------------------------------------------
wa = GL["checks"]["weapon_identity_attach"]
att = next(iter(wa.values())) if wa else {}
idx = {n: i for i, n in enumerate(NAMES, start=1)}
top = [label(load("sleeve_section_rest_fist.png", 330), "section along the barrel, rest pose + fist: the forearm, fist and massive vambrace in the sleeve"),
       label(load("sleeve_section_cannon_aim.png", 330), "the same section, cannon aimed (elbow 33 deg)")]
mid = []
for n in ("cannon_aim", "guard", "siege_brace", "lunge", "bulwark_raise"):
    if n in idx:
        mid.append(label(load("pose_%02d_%s_cannon.png" % (idx[n], n), 330), n))
txt = Image.new("RGB", (900, 200), BG)
d = ImageDraw.Draw(txt)
lines_t = [("The identity attach, proven in glTF (s3_gltf_check.py):", HOT),
           ("the rig exported as stage 5 will export it; the SHIPPED assets/models/weapons/colossus_cannon.glb read back, every mesh", FG),
           ("node pushed through the weapon_R node's world matrix: %d vertices land on the cannon the rig holds within %.1e m." % (
               att.get("vertices", 0), att.get("max_distance_m", float("nan"))), FG),
           ("Weapon scene roots identity: %s. All four socket frames match the grip frames within %.0e." % (
               att.get("weapon_scene_roots_identity"), max(v["max_abs_vs_grip_frame"] for v in GL["checks"]["socket_frames"].values())), FG),
           ("Sleeve rule: the wrist never bends, the hand only twists about the forearm axis (the hand bone's tail sits on that axis),", FG),
           ("so the barrel stays coaxial; the right couter rides the forearm (x_elbow_R follow 1.0). Clean elbow range: see the chart.", FG)]
for k, (t, c) in enumerate(lines_t):
    d.text((10, 8 + k * 24), t, fill=c, font=SMALL)


def line_chart(w, h, title, xs, series, xlabel, ylabel, ymax=None, note=None, vmark=None):
    """A small line chart on the dark sheet: one y-axis, recessive grid, 2 px lines, 8 px markers, a legend (>= 2 series)
    and the series labelled at their line ends; text in text colours, never in series colours."""
    SURF, GRID, AX = (26, 26, 25), (56, 56, 53), (110, 108, 102)
    im = Image.new("RGB", (w, h), SURF)
    d = ImageDraw.Draw(im)
    d.text((10, 6), title, fill=FG, font=SMALL)
    d.text((10 + d.textlength(title, font=SMALL) + 10, 8), "(y: %s)" % ylabel, fill=DIM, font=TINY)
    L_, R_, T_, B_ = 46, 150, 34, 36 + (16 if note else 0)
    x0, x1, y0, y1 = L_, w - R_, T_, h - B_
    top = ymax or max(1, max(max(v for v in s[1] if v is not None) for s in series))
    step = [s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000) if top / s <= 5][0]
    top = step * (int(top / step) + 1)
    xmin, xmax = min(xs), max(xs)
    X = lambda v: x0 + (v - xmin) / (xmax - xmin) * (x1 - x0)  # noqa: E731
    Y = lambda v: y1 - v / top * (y1 - y0)  # noqa: E731
    for g in range(0, top + 1, step):
        d.line([(x0, Y(g)), (x1, Y(g))], fill=GRID, width=1)
        d.text((4, Y(g) - 7), "%d" % g, fill=DIM, font=TINY)
    for xv in xs:
        d.text((X(xv) - 8, y1 + 4), ("%d" % xv) if float(xv).is_integer() else ("%.2f" % xv), fill=DIM, font=TINY)
    d.line([(x0, y1), (x1, y1)], fill=AX, width=1)
    d.text((x0, h - 18 - (16 if note else 0)), xlabel, fill=DIM, font=TINY)
    if vmark is not None:
        xv, txt = vmark
        for yy in range(int(y0), int(y1), 6):
            d.line([(X(xv), yy), (X(xv), yy + 3)], fill=AX, width=1)
        d.text((X(xv) + 4, y0), txt, fill=DIM, font=TINY)
    ends = []
    for lab, ys, col, wd in series:
        pts = [(X(x), Y(y)) for x, y in zip(xs, ys) if y is not None]
        d.line(pts, fill=col, width=wd, joint="curve")
        for px, py in pts:
            d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=col, outline=SURF, width=2)
        ends.append([pts[-1][1], lab, col])
    ends.sort()
    for k in range(1, len(ends)):                     # keep the end labels 13 px apart
        ends[k][0] = max(ends[k][0], ends[k - 1][0] + 13)
    for yy, lab, col in ends:
        d.line([(x1 + 4, yy), (x1 + 12, yy)], fill=col, width=2)
        d.text((x1 + 15, yy - 7), lab, fill=FG, font=TINY)
    if note:
        d.text((x0, h - 16), note, fill=DIM, font=TINY)
    return im


ORD = [(24, 79, 149), (37, 106, 191), (57, 135, 229), (109, 167, 236), (158, 197, 244)]    # blue ramp 600..200 (dark mode)
ON, OFF = (57, 135, 229), (217, 89, 38)                                                        # categorical 1 / 2 (dark mode)
cn = [r for r in LIM.get("cannon", []) if "flex" in r]
chart_cannon = line_chart(900, 260, "Cannon arm: elbow flexion vs the sleeve (upper arm out 30, down 20)", [r["flex"] for r in cn],
                          [("cuts by the cannon", [r["cannon_cuts"] for r in cn], ON, 2),
                           ("arm poke-through", [r["cannon_poke"] for r in cn], OFF, 2)],
                          "elbow flexion (deg)", "vertices", note="the rear cuff ends 5 cm in front of the elbow: clean to ~25 deg, the upper-arm plate from ~30 deg")
right = stack([txt, chart_cannon], 900)
W = max(sum(i.width for i in top) + 12 + right.width, sum(i.width for i in mid))
save(stack([header(W, "Valdris - the colossus_cannon on weapon_R (identity attach, sleeve weapon)",
                   "The cannon is a separate weapon GLB (art/weapons/colossus_cannon/). Its forearm sleeve encloses the massive vambrace, which lies "
                   "inside the sleeve wall (hidden). PREVIEW object, never exported with the hero."),
            hrow(top + [right], max(330, right.height), gap=6), hrow(mid, 330)], W), "stage3_weapon.png")

# ---- range of motion --------------------------------------------------------------------------------------------------------
panels = []
sh = LIM["shoulder"]
fol = sorted({r["follow"] for r in sh})
chosen = json.load(open(os.path.join(A, "stage3_skin.json"), encoding="utf-8"))["rig"]["helpers"]
CAT = [(57, 135, 229), (217, 89, 38), (25, 158, 112)]        # categorical slots 1-3, dark mode


def clean_limit(f, az, allow=25):
    """The highest upper-arm elevation reached from level (0, 15, 30 ...) before the raise adds more than `allow`
    clipping + suit vertices to the level arm."""
    rows = {r["el"]: r["clipping"] + r["suit"] for r in sh if r["follow"] == f and r["az"] == az}
    base, lim = rows[0], 0
    for e in sorted(e for e in rows if e >= 0):
        if rows[e] - base > allow:
            break
        lim = e
    return lim


ser = [("arm %s" % nm, [clean_limit(f, az) for f in fol], CAT[k], 2)
       for k, (az, nm) in enumerate(((0, "to the side"), (45, "half forward"), (80, "forward")))]
panels.append(line_chart(640, 300, "Shoulder: how high the arm rises clean, by pauldron follow", fol, ser, "pauldron follow (x_pauldron)",
                         "clean elevation (deg)", ymax=60, vmark=(chosen["pauldron"]["follow"], "rig %.2f" % chosen["pauldron"]["follow"]),
                         note="clean = at most 25 new clipping + suit vertices over the level arm; the sweep has 15 deg steps"))
els = sorted({r["el"] for r in sh if r["az"] == 0})
rig_f = min(fol, key=lambda f: abs(f - chosen["pauldron"]["follow"]))
panels.append(line_chart(640, 300, "Shoulder at pauldron follow %.2f, by arm direction" % rig_f, els,
                         [("arm %s" % nm, [next(r["clipping"] + r["suit"] for r in sh if r["follow"] == rig_f and r["az"] == az and r["el"] == e)
                                           for e in els], CAT[k], 2)
                          for k, (az, nm) in enumerate(((0, "to the side"), (45, "half forward"), (80, "forward")))],
                         "upper-arm elevation (deg)", "clipping + suit vertices",
                         note="lowered, the rerebrace meets the chest band at the armpit; forward and level it touches the chest and anvil"))
for key, xk, title, fk, lab in (("elbow", "flex", "Left elbow flexion: x_elbow", "follow", "elbow flexion (deg)"),
                                ("knee", "flex", "Knee flexion: x_knee", "follow", "knee flexion (deg)")):
    rows = LIM[key]
    xs = sorted({r[xk] for r in rows})
    ser = []
    for f, col in ((0.0, OFF), (0.5, ON)):
        ser.append(("follow %.1f%s" % (f, " (rig)" if f else ""), [next(r["clipping"] for r in rows if r[fk] == f and r[xk] == x) for x in xs], col, 2))
    panels.append(line_chart(640, 300, title, xs, ser, lab, "clipping vertices",
                             note=("the two lines coincide: the poleyn clips nothing either way; at 0.5 it covers the knee instead of "
                                   "floating off it") if key == "knee" else None))
if "ankle" in LIM:
    rows = LIM["ankle"]
    xs = [r["dorsiflex"] for r in rows]
    panels.append(line_chart(640, 300, "Ankle: greave / shin plate into the sabaton", xs,
                             [("clipping", [r["clipping"] for r in rows], ON, 2), ("sliding", [r["sliding"] for r in rows], OFF, 2)],
                             "foot flexion vs the shin (deg, + = toes up)", "vertices"))
hp = LIM["hip"]
tf = sorted({r["follow"] for r in hp})
xs = sorted({r["flex"] for r in hp})
for lean in (0, 12):
    ser = []
    for k, f in enumerate(tf):
        pick = abs(f - chosen["tasset"]["follow"]) < 1e-6
        ser.append(("tasset %.2f%s" % (f, " (rig)" if pick else ""),
                    [next(r["clipping"] for r in hp if r["follow"] == f and r["lean"] == lean and r["fauld"] == 1.0 and r["flex"] == x) for x in xs],
                    ORD[min(k + 1, len(ORD) - 1)], 4 if pick else 2))
    panels.append(line_chart(640, 300, "Thigh flexion, torso %s: tasset follow" % ("upright" if lean == 0 else "leaning 12 deg"), xs, ser,
                             "thigh flexion (deg)", "clipping vertices"))
hd = LIM["head"]
ys = sorted({r["yaw"] for r in hd})
panels.append(line_chart(640, 300, "Head yaw: beard and braids vs pauldrons / gorget", ys,
                         [("level", [next(r["clipping"] for r in hd if r["nod"] == 0 and r["yaw"] == y) for y in ys], ON, 2),
                          ("nod 20", [next(r["clipping"] for r in hd if r["nod"] == 20 and r["yaw"] == y) for y in ys], OFF, 2)],
                         "neck + head yaw (deg)", "clipping vertices",
                         note="braids at rest on the head here; in the validation poses the braid chains are posed clear (0 left inside)"))
tw = LIM["twist"]
panels.append(line_chart(640, 300, "Torso twist (a third on each spine bone)", [r["twist"] for r in tw],
                         [("clipping", [r["clipping"] for r in tw], ON, 2), ("sliding", [r["sliding"] for r in tw], OFF, 2)],
                         "twist (deg)", "vertices"))
grid = []
for s in range(0, len(panels), 3):
    grid.append(hrow(panels[s:s + 3], 300, gap=10))
W = max(g.width for g in grid)
spaced = []
for g in grid:
    spaced += [g, Image.new("RGB", (W, 10), BG)]
save(stack([header(W, "Valdris - range of motion of the rigid armour (s3_valdris_limits.py)",
                   "Each sample: one joint turned from the rest pose; new vertices of one armour piece inside another (clipping: different regions; "
                   "sliding: lames of one region; suit: into the under-suit). Thick line = the value the rig uses.",
                   "These sweeps chose the helpers' follow factors and set the animation ranges for stage 4 (reports/rig_report.md section 5).")]
           + spaced, W), "stage3_limits.png")
