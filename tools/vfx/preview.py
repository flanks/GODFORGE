"""Preview rendering: sample packed cells like the GPU (bilinear, rotated, scaled) and shade them with
the reference shader onto Plates. Used by the contact sheets (sheets.py) and for quick looks:

    python tools/vfx/preview.py atlas/vfx_impact_star.png kinetic,storm out.png
"""
import math
import os
import sys

import numpy as np
from PIL import Image

import vfxlib as L


def sample(packed, scale=1.0, angle=0.0, size=None, pivot=None, sx=None, sy=None):
    """Bilinear-resample a packed uint8 cell into a float (size, size, 3) canvas: the cell is scaled
    (sx, sy default to scale), rotated by `angle` (radians, counter-clockwise on screen) about its pivot
    (cell uv), and the pivot lands at the canvas centre."""
    h, w = packed.shape[:2]
    sx = scale if sx is None else sx
    sy = scale if sy is None else sy
    if size is None:
        size = int(math.ceil(max(w * sx, h * sy) * 1.5)) + 4
    sw, sh = (size, size) if isinstance(size, int) else size
    pu, pv = (0.5, 0.5) if pivot is None else pivot
    px, py = pu * w, pv * h
    ca, sa = math.cos(angle), math.sin(angle)
    # output (X, Y) -> input: x = px + ((X - cx) * ca - (Y - cy) * sa) / sx ... (inverse of rotate-by-angle, y down)
    cx, cy = sw / 2, sh / 2
    # PIL's affine maps output -> input: x_in = a*x + b*y + c, y_in = d*x + e*y + f (the inverse of
    # scale-then-rotate about the pivot; a positive angle turns the sprite counter-clockwise on screen)
    A = (ca / sx, -sa / sx, 0.0, sa / sy, ca / sy, 0.0)
    c0 = px - (A[0] * cx + A[1] * cy)
    f0 = py - (A[3] * cx + A[4] * cy)
    coeffs = (A[0], A[1], c0, A[3], A[4], f0)
    out = []
    for i in range(3):
        im = Image.fromarray(packed[..., i])
        out.append(np.asarray(im.transform((sw, sh), Image.AFFINE, coeffs, resample=Image.BILINEAR, fillcolor=0),
                              np.float32) / 255.0)
    return np.stack(out, -1)


def sprite(packed, ramp, scale=1.0, angle=0.0, size=None, pivot=None, t=0.0, value=None, alpha=1.0, gain=1.0,
           sx=None, sy=None, cool=0.0, posterize=True):
    tex = sample(packed, scale, angle, size, pivot, sx, sy)
    s = min(scale if sx is None else sx, scale if sy is None else sy)
    return L.shade(tex, ramp, t=t, value=value, alpha=alpha, gain=gain, scale=s, cool=cool, posterize=posterize)


def put(plate, layer, cx, cy):
    h, w = layer.shape[:2]
    plate.over(layer, int(round(cx - w / 2)), int(round(cy - h / 2)))


def ink_backed(plate, packed, ramp, cx, cy, scale=1.0, angle=0.0, ink_scale=1.3, ink_rot=0.11, pivot=None, t=0.0,
               alpha=1.0, size=None):
    """The VFX_STYLE star recipe: the same frame as an ink shape 30 % larger and rotated, then the body."""
    if size is None:
        size = int(max(packed.shape[:2]) * scale * ink_scale * 1.45) + 4
    put(plate, sprite(packed, ramp, scale * ink_scale, angle + ink_rot, size, pivot, t=t, value=L.V_INK,
                      alpha=alpha * 0.95), cx, cy)
    put(plate, sprite(packed, ramp, scale, angle, size, pivot, t=t, alpha=alpha), cx, cy)


def cell_of(img, grid_cell, col, row):
    cw, ch = grid_cell
    return img[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw]


def frame_of(img, ent, seq, i):
    """Frame i of a sequence: row-major from (col0, row), wrapping at the grid width."""
    cols = ent["grid"][0]
    k = seq.get("col0", 0) + i
    if seq.get("axis") == "column":
        return cell_of(img, ent["cell"], seq.get("col0", 0), seq["row"] + i)
    return cell_of(img, ent["cell"], k % cols, seq["row"] + k // cols)


def quick(rel, ramps, out, scale=1.0, ink=False, bg="#17131A"):
    img = L.load_atlas(rel)
    L.load_manifest()
    ent = [e for e in L.MANIFEST if e["file"] == rel][0]
    cw, ch = ent["cell"]
    seqs = ent["sequences"]
    pad = 8
    cwp, chp = int(cw * scale) + pad, int(ch * scale) + pad
    ncol = max(s["frames"] for s in seqs)
    W = ncol * cwp + 160
    H = len(seqs) * len(ramps) * chp + 20
    p = L.Plate(W, H, bg)
    y = 10
    for s in seqs:
        for rp in ramps:
            p.label(8, y + chp // 2, f"{s['name']} / {rp}", 13, anchor="lm")
            for i in range(s["frames"]):
                cell = frame_of(img, ent, s, i)
                cx = 160 + i * cwp + cwp // 2
                cy = y + chp // 2
                size = (int(cw * scale * 1.0) + 2, int(ch * scale) + 2)
                if ink:
                    ink_backed(p, cell, rp, cx, cy, scale, size=max(size))
                else:
                    lay = sprite(cell, rp, scale, 0.0, size, None)
                    put(p, lay, cx, cy)
            y += chp
    p.finish().save(out)


if __name__ == "__main__":
    rel = sys.argv[1]
    ramps = sys.argv[2].split(",")
    out = sys.argv[3]
    sc = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    bg = [a.split("=")[1] for a in sys.argv if a.startswith("--bg=")]
    quick(rel, ramps, out, sc, ink="--ink" in sys.argv, bg=bg[0] if bg else "#17131A")
