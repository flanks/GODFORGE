"""Stage 3, Selene: the one review sheet (Pillow) -> art/characters/selene/reports/stage3/stage3_rig.png

  <python with Pillow> tools/blender/gf_hero/s3_selene_sheets.py

From work/renders/stage3/ (s3_selene_poses.py) and reports/stage3/{poses,skin,landmarks}.json: the bind pose with the
GF_Hero_v1 bones drawn over it (core, twist, fingers, sockets, her x_ extras by kind), the seven validation poses with
their numbers, the weapon check close-up (the thundercoil_launcher on weapon_R, the left palm on grip_L) and the 55 deg
client camera at true pixel size (x2).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
A = os.path.join(ROOT, "art", "characters", "selene")
REN = os.path.join(A, "work", "renders", "stage3")
OUT = os.path.join(A, "reports", "stage3", "stage3_rig.png")


def font(sz, bold=False):
    for f in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


poses = json.load(open(os.path.join(A, "reports", "stage3", "poses.json"), encoding="utf-8"))["poses"]
skin = json.load(open(os.path.join(A, "reports", "stage3", "skin.json"), encoding="utf-8"))
CW, CH = 460, 640
HEAD = 70
sheet = Image.new("RGB", (CW * 5, HEAD + CH * 2 + 30), (30, 31, 36))
d = ImageDraw.Draw(sheet)
F, FB, FS = font(17), font(26, True), font(14)
b = skin["bones"]
d.text((14, 10), "Selene stage 3: GF_Hero_v1 + %d x_ extras (6 crown shards, 2 knee helpers, 8 cloth chains), %d bones, "
       "skinned; poses by the stage-4 solver, cloth hung clear" % (b["extras"], b["total"]), font=FB, fill=(235, 235, 240))
d.text((14, 44), "Cycles CPU toon, front three-quarter from her right. The thundercoil_launcher GLB rides weapon_R (identity "
       "attach); in the hold the left palm is solved onto its grip_L.", font=F, fill=(190, 190, 200))
COL = {"core": (255, 214, 90), "twist": (255, 150, 60), "fingers": (120, 230, 140), "sockets": (255, 90, 200),
       "crown": (255, 240, 150), "knee": (255, 120, 120), "cloth": (110, 200, 255)}


def kind(n):
    if n.startswith("x_crown"):
        return "crown"
    if n.startswith("x_knee"):
        return "knee"
    if n.startswith("x_"):
        return "cloth"
    if n in ("weapon_R", "weapon_L", "head_top", "chest_sigil"):
        return "sockets"
    if "twist" in n:
        return "twist"
    if any(n.startswith(f) for f in ("thumb", "index", "middle", "ring", "pinky")):
        return "fingers"
    return "core"


def cell(i, name, label, lines):
    x, y = (i % 5) * CW, HEAD + (i // 5) * CH
    im = Image.open(os.path.join(REN, "pose_%s.png" % name)).convert("RGB")
    sheet.paste(im, (x, y))
    dd = ImageDraw.Draw(sheet)
    if name == "bind":
        for n, h, t in poses["bind"]["bone_lines_px"]:
            c = COL[kind(n)]
            dd.line([(x + h[0], y + h[1]), (x + t[0], y + t[1])], fill=c, width=2)
            dd.ellipse([x + h[0] - 2, y + h[1] - 2, x + h[0] + 2, y + h[1] + 2], fill=c)
        yy = y + 470
        for k, c in COL.items():
            dd.rectangle([x + 10, yy + 3, x + 22, yy + 15], fill=c)
            dd.text((x + 28, yy), k, font=FS, fill=(230, 230, 230))
            yy += 19
    dd.rectangle([x, y, x + CW - 1, y + 24], fill=(18, 18, 22))
    dd.text((x + 8, y + 3), label, font=F, fill=(240, 240, 240))
    yy = y + CH - 18 * len(lines) - 6
    for ln in lines:
        dd.text((x + 8, yy), ln, font=FS, fill=(225, 225, 230))
        yy += 18


def nums(p):
    r = poses[p]
    out = []
    if "elbow_deg" in r:
        out.append("elbow L %.0f / R %.0f deg, knee L %.0f / R %.0f deg" % (r["elbow_deg"]["L"], r["elbow_deg"]["R"],
                                                                             r["knee_deg"]["L"], r["knee_deg"]["R"]))
    if "grip_L_error_m" in r:
        out.append("left palm to grip_L %.1f mm" % (1000 * r["grip_L_error_m"]))
    if "weapon_attach_error" in r and p != "bind":
        out.append("launcher on weapon_R: attach error %.1e" % r["weapon_attach_error"])
    if "cloth_bones_touching" in r:
        out.append("cloth bones still touching: %d of 22" % r["cloth_bones_touching"])
    return out


order = [("bind", "bind T-pose + bones"), ("relaxed", "relaxed carry"), ("hold", "HOLD (weapon check pose)"),
         ("lunge_fire", "firing lunge"), ("crouch", "deep crouch"), ("verdict", "Heaven's Verdict arms up"),
         ("run_stride", "run stride"), ("twist_look", "twist + head turn")]
for i, (n, lab) in enumerate(order):
    cell(i, n, lab, nums(n))
# the last two cells: the weapon close-up and the in-game view (1:1 and x2)
x, y = 3 * CW, HEAD + CH
d = ImageDraw.Draw(sheet)
d.rectangle([x, y, x + 2 * CW - 1, y + 24], fill=(18, 18, 22))
d.text((x + 8, y + 3), "the hold: close-up | the 55 deg client camera at true pixel size (22 m view), 1:1 and x2", font=F,
       fill=(240, 240, 240))
cl = Image.open(os.path.join(REN, "hold_closeup.png")).convert("RGB")
sheet.paste(cl, (x, y + 26))
ig = Image.open(os.path.join(REN, "hold_ingame.png")).convert("RGB")
sheet.paste(ig, (x + cl.width + 20, y + 30))
ig2 = ig.resize((ig.width * 2, ig.height * 2), Image.NEAREST).crop((ig.width // 2, ig.height // 2, ig.width * 3 // 2, ig.height * 3 // 2))
sheet.paste(ig2, (x + cl.width + 20, y + 40 + ig.height))
d.text((x + 8, y + 26 + cl.height + 8), "grip_L: %.1f mm off; launcher attach %.1e (identity child of weapon_R)" % (
    1000 * poses["hold"]["grip_L_error_m"], poses["hold"]["weapon_attach_error"]), font=F, fill=(225, 225, 230))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
sheet.save(OUT, optimize=True)
print("wrote", OUT, sheet.size)
