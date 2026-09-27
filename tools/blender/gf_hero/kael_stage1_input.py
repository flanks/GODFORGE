"""Kael stage-1 input: the approved front with the two revolvers and the diffuse ghost smoke cut away (PIL, numpy).

Run with the ComfyUI python (PIL + numpy):
  <comfy-python> tools/blender/gf_hero/kael_stage1_input.py

Why: the approved front (references/KAEL_front_approved.png) shows Kael holding two serpent revolvers in the T-pose.
The barrels are collinear with the arms and the grips sit inside the fists, so TRELLIS.2 would grow each arm into
one continuous arm-gun tube (the weapons are separate models, docs/ART_PIPELINE.md "Weapons"). The birefnet mask
also takes the whole translucent ghost smoke around the coat (plus the background showing through its holes) as a
solid figure, which would be modelled as wide opaque fins around the coat. The brief asks for a coat with a ragged
hem and a few chunky emissive tatters, not a smoke volume.

What it does, and nothing else:
  1. starts from the graph's own birefnet mask of the verbatim concept (run_trellis.py --mask-only);
  2. guns: inside a box around each hand, keeps only the fist polygon (the glove / ghost hand closed round the
     grip) and drops the barrel, cylinder, hammer spikes and the grip below the fist;
  3. smoke: below the belt line and outside the legs' column, drops the translucent teal smoke, its dark mottling
     and the background showing through it (all G > R); the coat is purple-black and the leather brown (R >= G), so
     they are kept; inside the legs' column only the bright smoke goes (trousers and boots are never that green);
     the removed smoke overlay on the coat edge becomes part of the ragged hem;
  4. keeps the largest connected part, fills enclosed holes, a small open/close to drop smoke threads;
  5. writes references/kael_concept_front_nogun.png (RGBA: the concept's own RGB, alpha = the edited mask; the RGB
     is not repainted) and references/kael_concept_front_nogun_mask.png (the mask, L);
  6. with --sheet, also writes reports/blockout/input_edit.png: the birefnet cut-out, what the edit removed (red), and
     the conditioning crop the graph builds from the edited alpha (work/maskcheck_own/, run_trellis.py --mask-only
     --own-mask) - the record of the edit next to reports/blockout/input_maskcheck.png.

run_trellis.py then runs with --own-mask on the RGBA file (the conditioning background stays #808080).
Deterministic: the same inputs give byte-identical outputs.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
K = os.path.join(ROOT, "art", "characters", "kael")
CONCEPT = os.path.join(K, "references", "KAEL_front_approved.png")
BIREFNET = os.path.join(K, "work", "maskcheck_raw", "kael_maskcheck_mask.png")
OUT_RGBA = os.path.join(K, "references", "kael_concept_front_nogun.png")
OUT_MASK = os.path.join(K, "references", "kael_concept_front_nogun_mask.png")
OWN_CROP = os.path.join(K, "work", "maskcheck_own", "kael_maskcheck_crop.png")
SHEET = os.path.join(K, "reports", "blockout", "input_edit.png")

# Hands, in concept pixels (1536x1024). Inside each box only the fist polygon survives.
# His RIGHT hand (image left, black fingerless glove): barrel and cylinder to the left, grip hanging below right.
R_HAND_BOX = (60, 140, 360, 300)
R_FIST = [(299, 202), (304, 194), (318, 190), (340, 188), (360, 189), (360, 241), (348, 244), (338, 248),
          (330, 256), (316, 259), (306, 254), (300, 244), (297, 222)]
# His LEFT hand (image right, the spectral ghost hand): cylinder and barrel to the right, grip hanging below left.
L_HAND_BOX = (1150, 140, 1480, 300)
L_FIST = [(1150, 191), (1175, 189), (1197, 187), (1222, 189), (1238, 195), (1249, 203), (1248, 214), (1243, 224),
          (1243, 244), (1234, 254), (1218, 259), (1203, 254), (1190, 249), (1170, 248), (1150, 246)]

SMOKE_Y0 = 405          # below the belt line (belt buckle at y ~365-385)
LEG_X = (555, 940)      # the legs' column (boots, trousers, loin cloth, holsters): only bright smoke is cut there


def main():
    rgb = Image.open(CONCEPT).convert("RGB")
    W, H = rgb.size
    a = np.asarray(rgb).astype(np.int16)
    m = np.asarray(Image.open(BIREFNET).convert("L")) > 127
    if m.shape != (H, W):
        sys.exit("mask %s does not match the concept %s" % (m.shape, (H, W)))

    # 2. guns
    for box, poly in ((R_HAND_BOX, R_FIST), (L_HAND_BOX, L_FIST)):
        keep = Image.new("L", (W, H), 0)
        ImageDraw.Draw(keep).polygon(poly, fill=255)
        keep = np.asarray(keep) > 0
        x0, y0, x1, y1 = box
        region = np.zeros_like(m)
        region[y0:y1, x0:x1] = True
        m = m & ~(region & ~keep)

    # 3. smoke
    # coat purple, black, brown leather: R >= G; the smoke, its dark mottling and the navy background: G > R
    R, G = a[..., 0], a[..., 1]
    lower = np.zeros_like(m)
    lower[SMOKE_Y0:, :] = True
    column = np.zeros_like(m)
    column[:, LEG_X[0]:LEG_X[1]] = True
    m = m & ~(lower & ~column & (G - R > 5))
    m = m & ~(lower & column & (G - R > 30))

    # 4. clean up
    img = Image.fromarray((m * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(7))   # open: cut smoke threads
    img = img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))   # close: re-join the hem
    m = np.asarray(img) > 127
    m = largest_component(m)
    m = fill_holes(m)
    # keep birefnet's soft edge where the mask was not edited
    soft = np.asarray(Image.open(BIREFNET).convert("L"))
    alpha = np.where(m, np.maximum(soft, 1), 0).astype(np.uint8)
    alpha = np.where(m & (soft < 128), 255, alpha).astype(np.uint8)

    rgba = np.dstack([np.asarray(rgb), alpha])
    Image.fromarray(rgba, "RGBA").save(OUT_RGBA, optimize=False)
    Image.fromarray(alpha, "L").save(OUT_MASK, optimize=False)
    print("kept %d px (birefnet %d); wrote %s, %s" % ((alpha > 127).sum(),
          (np.asarray(Image.open(BIREFNET).convert("L")) > 127).sum(), OUT_RGBA, OUT_MASK))
    if "--sheet" in sys.argv:
        sheet(rgb, soft > 127, alpha > 127)


def sheet(rgb, before, after):
    """Three panels at 640 px wide: birefnet cut-out on grey, the edit (grey kept, red removed), the conditioning crop."""
    W, H = rgb.size
    grey = Image.new("RGB", (W, H), (128, 128, 128))
    a = Image.composite(rgb, grey, Image.fromarray((before * 255).astype(np.uint8)))
    diff = np.zeros((H, W, 3), np.uint8)
    diff[before & after] = (200, 200, 200)
    diff[before & ~after] = (215, 45, 45)
    diff[~before & after] = (45, 200, 70)
    b = Image.fromarray(diff)
    c = Image.open(OWN_CROP).convert("RGB") if os.path.isfile(OWN_CROP) else Image.new("RGB", (1024, 1024), (60, 60, 60))
    pw = 640
    panels = [a.resize((pw, pw * H // W), Image.LANCZOS), b.resize((pw, pw * H // W), Image.NEAREST),
              c.resize((pw * H // W, pw * H // W), Image.LANCZOS)]
    ph = pw * H // W
    out = Image.new("RGB", (pw * 2 + ph + 40, ph + 70), (40, 42, 46))
    d = ImageDraw.Draw(out)
    titles = ["birefnet cut-out of the approved front (graph node 192)",
              "the edit: grey kept, red removed (guns, diffuse smoke)",
              "conditioning crop from the edited alpha (#808080)"]
    x = 10
    for p, t in zip(panels, titles):
        out.paste(p, (x, 40))
        d.text((x + 4, 14), t, fill=(230, 225, 215))
        x += p.width + 10
    d.text((10, ph + 48), "Kael stage-1 input edit - tools/blender/gf_hero/kael_stage1_input.py; kept %d px of birefnet's %d"
           % (int(after.sum()), int(before.sum())), fill=(160, 156, 150))
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    out.save(SHEET, optimize=True)
    print("wrote", SHEET)


def largest_component(m):
    """4-connected components by a two-pass union-find over row runs (no scipy in the ComfyUI env)."""
    H, W = m.shape
    parent = {}
    label = np.zeros((H, W), np.int32)
    runs = []
    nxt = 1

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    prev = []
    for y in range(H):
        row = m[y]
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts = np.where(d == 1)[0]
        ends = np.where(d == -1)[0]
        cur = []
        for s, e in zip(starts, ends):
            lab = nxt
            parent[lab] = lab
            nxt += 1
            for ps, pe, pl in prev:
                if ps < e and s < pe:
                    ra, rb = find(lab), find(pl)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
            cur.append((s, e, lab))
            runs.append((y, s, e, lab))
        prev = cur
    size = {}
    for y, s, e, lab in runs:
        r = find(lab)
        size[r] = size.get(r, 0) + (e - s)
    best = max(size, key=size.get)
    out = np.zeros_like(m)
    for y, s, e, lab in runs:
        if find(lab) == best:
            out[y, s:e] = True
    return out


def fill_holes(m):
    """Background = the complement's component touching the border; everything else is filled."""
    inv = ~m
    padded = np.pad(inv, 1, constant_values=True)
    outside = largest_component(padded)[1:-1, 1:-1]
    return ~outside


if __name__ == "__main__":
    main()
