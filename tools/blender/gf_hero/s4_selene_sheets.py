"""Stage 4, Selene: the one review board (Pillow) -> art/characters/selene/reports/anim/anim_board.png

  <python with Pillow> tools/blender/gf_hero/s4_selene_sheets.py

Every clip in reports/anim/clips.json order, two clips per row, four key frames each (work/renders/stage4/, rendered by
s4_selene_render.py), labelled with the clip's action name, frames, loop / layer, events and the numbers that matter:
the planted-foot slide, the left palm on the launcher's grip_L, the cloth pass.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
A = os.path.join(ROOT, "art", "characters", "selene")
REN = os.path.join(A, "work", "renders", "stage4")
OUT = os.path.join(A, "reports", "anim", "anim_board.png")


def font(sz, bold=False):
    for f in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


man = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
chk = json.load(open(os.path.join(A, "reports", "anim", "render_checks.json"), encoding="utf-8"))
cloth = json.load(open(os.path.join(A, "reports", "anim", "cloth.json"), encoding="utf-8"))
CW, CH, LAB = 220, 280, 46
HEAD = 84
order = man["order"]
rows = (len(order) + 1) // 2
W = 2 * 4 * CW + 20
sheet = Image.new("RGB", (W, HEAD + rows * (CH + LAB) + 10), (30, 31, 36))
d = ImageDraw.Draw(sheet)
F, FB, FS = font(15), font(26, True), font(13)
nsh = sum(1 for c in order if man["clips"][c]["family"] == "shared")
d.text((14, 10), "Selene stage 4: %d clips on GF_Hero_v1 (%d shared re-posed for her two-handed launcher hold + %d kit), 30 fps, "
       "in place, cloth + crown pass" % (len(order), nsh, len(order) - nsh), font=FB, fill=(235, 235, 240))
d.text((14, 46), "Four key frames per clip (Cycles CPU toon, front three-quarter from her right, one scale). 'grip' = the left "
       "palm on the thundercoil_launcher's grip_L (frames within 5 cm); 'slide' = planted-foot drift in world space.",
       font=F, fill=(190, 190, 200))
for i, clip in enumerate(order):
    info = man["clips"][clip]
    m = info["metrics"]
    x0 = (i % 2) * (4 * CW + 20)
    y0 = HEAD + (i // 2) * (CH + LAB)
    frames = chk["clips"][clip]["frames_rendered"]
    for j, f in enumerate(frames):
        p = os.path.join(REN, "%s_f%02d.png" % (clip, f))
        if os.path.exists(p):
            sheet.paste(Image.open(p).convert("RGB"), (x0 + j * CW, y0 + LAB))
        d.text((x0 + j * CW + 4, y0 + LAB + 3), "f%d" % f, font=FS, fill=(220, 220, 225))
    ev = ", ".join("%s %d" % (k, v) for k, v in sorted(info.get("events", {}).items(), key=lambda kv: kv[1]))
    g = chk["clips"][clip]["grip_L_error_mm"]
    d.rectangle([x0, y0, x0 + 4 * CW - 1, y0 + LAB - 2], fill=(18, 18, 22))
    d.text((x0 + 6, y0 + 3), "%s  (%d f, %s%s)" % (info["action"], info["frames"], "loop" if info["loop"] else "one-shot",
                                                  ", upper layer" if info["layer"] == "upper" else ""), font=F, fill=(245, 225, 150))
    d.text((x0 + 6, y0 + 23), "%sslide %.1f mm | grip %d/%d f | knee max %.0f deg | cloth inside %d bone-f" % (
        ("events: " + ev + " | ") if ev else "", m["foot_slide_max_mm"], g["frames_on_grip"], g["frames"],
        max(m["knee_flexion_max_deg"].values()), cloth["clips"][clip]["inside_bone_frames"]), font=FS, fill=(210, 210, 215))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
sheet.save(OUT, optimize=True)
print("wrote", OUT, sheet.size)
