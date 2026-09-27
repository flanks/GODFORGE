"""Selene stage-1 input: the approved front with a verified alpha, for run_trellis.py --own-mask.

  <comfy-python> art/characters/selene/stage1_input.py

<comfy-python> = D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe (PIL, numpy, scipy).

The RGB is the approved front, byte for byte; only the alpha is new. It starts from the graph's own birefnet
mask (references/selene_concept_front_mask.png, run_trellis.py --mask-only) and changes two things, both found
by the first TRELLIS.2 run on the plain concept (reports/blockout_report.md section 2):

  1. the two floating coils are weapon / VFX, not body: they are cut (TRELLIS made them ~1 m barrels in depth
     that cross the cape and the hips in every side view);
  2. around the head birefnet keeps the dark navy ground between the hair, the wisps and the six crown shards
     (TRELLIS fused it into a second hair mass): there only what a colour key over a fitted background calls
     figure is kept (grown 2 px for the soft edge; enclosed holes under 150 px filled).

Writes references/selene_concept_front_input.png (RGBA). Deterministic.
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "references")
COILS = ((280, 472, 200, 484), (280, 472, 1052, 1330), (280, 420, 1036, 1052))   # y0, y1, x0, x1
HEAD = (640, 0, 896, 200)                                                           # x0, y0, x1, y1
KEY_THRESHOLD = 12.0


def main():
    img = np.asarray(Image.open(os.path.join(REF, "SELENE_front_approved.png")).convert("RGB")).astype(np.float64)
    m = np.asarray(Image.open(os.path.join(REF, "selene_concept_front_mask.png")).convert("L")).astype(np.float64)
    h, w, _ = img.shape
    # colour key: a smooth background (2nd order per channel) fitted well outside the figure
    far = ~ndi.binary_dilation(m > 5, iterations=25)
    yy, xx = np.mgrid[0:h, 0:w]
    X = np.stack([np.ones_like(xx), xx / w, yy / h, (xx / w) ** 2, (yy / h) ** 2, xx * yy / (w * h)], -1)
    bg = np.zeros_like(img)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(X[far], img[..., c][far], rcond=None)
        bg[..., c] = X @ coef
    key = np.sqrt(((img - bg) ** 2).sum(-1)) > KEY_THRESHOLD

    out = m.copy()
    for y0, y1, x0, x1 in COILS:
        out[y0:y1, x0:x1] = 0
    x0, y0, x1, y1 = HEAD
    k = ndi.binary_dilation(key[y0:y1, x0:x1], iterations=2)
    holes = ndi.binary_fill_holes(k) & ~k
    hl, hn = ndi.label(holes)
    hs = ndi.sum(np.ones(holes.shape), hl, range(1, hn + 1))
    k |= np.isin(hl, [i + 1 for i, v in enumerate(hs) if v < 150])
    sub = out[y0:y1, x0:x1]
    removed = int(((sub > 127) & ~k).sum())
    sub[~k] = 0
    lab, n = ndi.label(out > 127)
    sizes = ndi.sum(np.ones_like(out), lab, range(1, n + 1))
    out[np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s < 40])] = 0

    alpha = out.clip(0, 255).astype(np.uint8)
    dst = os.path.join(REF, "selene_concept_front_input.png")
    Image.fromarray(np.dstack([img.astype(np.uint8), alpha]), "RGBA").save(dst, optimize=True)
    lab, n = ndi.label(alpha > 127)
    sizes = sorted((int(s) for s in ndi.sum(np.ones_like(out), lab, range(1, n + 1))), reverse=True)
    print(json.dumps({"out": "art/characters/selene/references/selene_concept_front_input.png",
                      "head_px_removed": removed, "components": int(n), "component_px": sizes,
                      "alpha_px": int((alpha > 127).sum())}))


if __name__ == "__main__":
    main()
