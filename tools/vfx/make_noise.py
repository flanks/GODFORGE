"""Tileable noise, dissolve masks and the element ramps (VFX_STYLE sections 3.3, 21.5).

  noise/noise_erode_256.png   fractal value noise, rank-equalized (uniform dissolve thresholds)
  noise/noise_streak_256.png  anisotropic brush-streak noise along u (smears, ribbons, beams)
  noise/noise_brush_256.png   dry-brush dissolve mask: fibrous bristle strokes along u
  noise/noise_cells_256.png   cellular noise, RGB: R = F1, G = F2 - F1 (cell edges), B = per-cell random
  noise/noise_hex_256.png     hex lattice, RGB: R = edge (1 on the walls), G = distance to the cell centre,
                              B = per-cell random (shield ripples, chaos glass); 8 x 10 cells, 8 % squashed
  ramps/vfx_ramps.png         16 rows x 256: posterized element ramps, RGB sRGB colour, A = HDR gain / 4
  ramps/vfx_ramps_smooth.png  the same rows as smooth gradients (light spill, smoke, heat haze)
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

import vfxlib as L


def brush_noise(n=256, seed=5):
    """Many thin horizontal strokes of random brightness, wrapped (tiles in both axes)."""
    rng = np.random.default_rng(seed)
    a = np.zeros((n, n), np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    for _ in range(420):
        y = rng.uniform(0, n)
        x0 = rng.uniform(0, n)
        ln = rng.uniform(n * 0.15, n * 0.7)
        w = rng.uniform(0.6, 2.4)
        val = rng.uniform(0.2, 1.0)
        dy = np.abs(((yy - y + n / 2) % n) - n / 2)
        dx = ((xx - x0) % n)
        t = dx / ln
        prof = np.where(t < 1, np.clip(np.sin(np.pi * np.clip(t, 0, 1)), 0, 1) ** 0.5, 0)
        m = np.clip(1 - dy / w, 0, 1) * prof
        a = np.maximum(a, m * val)
    a = ndi.gaussian_filter(a, (0.4, 1.2), mode="wrap")
    a = 0.8 * a + 0.2 * L.fbm_tile(n, seed + 1, beta=2.0, ax=6, ay=1)
    return L.equalize(a)


def hex_noise(n=256, cols=8, rows=10, seed=9):
    rng = np.random.default_rng(seed)
    w = n / cols
    hstep = n / rows
    pts = []
    for j in range(rows):
        for i in range(cols):
            pts.append(((i + (0.5 if j % 2 else 0.0)) * w, j * hstep))
    pts = np.array(pts)
    tiles = np.concatenate([pts + np.array([dx, dy]) * n for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    ids = np.tile(np.arange(len(pts)), 9)
    tree = cKDTree(tiles)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    d, idx = tree.query(np.stack([xx.ravel(), yy.ravel()], 1), k=2)
    f1 = d[:, 0].reshape(n, n)
    edge = (d[:, 1] - d[:, 0]).reshape(n, n)
    edge = 1 - np.clip(edge / (w * 0.18), 0, 1)
    dist = np.clip(f1 / (w * 0.6), 0, 1)
    rnd = rng.random(len(pts))[ids[idx[:, 0]]].reshape(n, n)
    return np.stack([edge, dist, rnd], -1).astype(np.float32)


def cells_noise(n=256, count=48, seed=11):
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)) * n
    tiles = np.concatenate([pts + np.array([dx, dy]) * n for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    ids = np.tile(np.arange(count), 9)
    tree = cKDTree(tiles)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    d, idx = tree.query(np.stack([xx.ravel(), yy.ravel()], 1), k=2)
    f1 = d[:, 0].reshape(n, n)
    f2f1 = (d[:, 1] - d[:, 0]).reshape(n, n)
    f1 = f1 / f1.max()
    f2f1 = np.clip(f2f1 / np.percentile(f2f1, 98), 0, 1)
    rnd = rng.random(count)[ids[idx[:, 0]]].reshape(n, n)
    return np.stack([f1, f2f1, rnd], -1).astype(np.float32)


def save_rgb(rel, a, kind, intended, **extra):
    path = os.path.join(L.OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(np.clip(np.round(a * 255), 0, 255).astype(np.uint8), "RGB").save(path, optimize=True)
    e = dict(file=rel, kind=kind, size=[a.shape[1], a.shape[0]], grid=[1, 1], frames=1, fps=None, intended=intended)
    e.update(extra)
    L.register(e)


def build():
    n = 256
    L.save_gray("noise/noise_erode_256.png", L.fbm_tile(n, 101, beta=2.3), "noise_tile",
                "dissolve threshold: tiling fractal noise, uniform histogram (alpha = smoothstep(t-0.04, t, n))",
                tileable=True, channels="L")
    L.save_gray("noise/noise_streak_256.png", L.fbm_tile(n, 102, beta=2.0, ax=8.0, ay=1.0), "noise_tile",
                "brush streaks along u: multiply into the erosion threshold of smears, ribbons and beams; scroll "
                "along u", tileable=True, channels="L")
    L.save_gray("noise/noise_brush_256.png", brush_noise(n, 103), "noise_tile",
                "dry-brush dissolve: bristle strokes along u; the tails of smears and trails break into streaks",
                tileable=True, channels="L")
    save_rgb("noise/noise_cells_256.png", cells_noise(n, 48, 104), "noise_tile",
             "cellular: plague bubbles (R = F1), chaos glass cracks and dried stains (G = F2-F1 edges), "
             "per-cell flicker (B)", tileable=True, channels="R=F1, G=F2-F1, B=cell random")
    save_rgb("noise/noise_hex_256.png", hex_noise(n, 8, 10, 105), "noise_tile",
             "hex lattice: forge-shield ripples, Binding Hex, shield breaks (R = wall, G = centre distance, "
             "B = cell random)", tileable=True, channels="R=edge, G=centre distance, B=cell random",
             note="8 x 10 cells; the rows are squashed 8 % so the lattice tiles in a square")
    rows = len(L.RAMPS)
    for smooth in (False, True):
        a = np.zeros((rows, 256, 4), np.float32)
        for i, (key, _, _) in enumerate(L.RAMPS):
            a[i] = L.ramp_table(key, posterize=not smooth)
        rel = "ramps/vfx_ramps_smooth.png" if smooth else "ramps/vfx_ramps.png"
        path = os.path.join(L.OUT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.fromarray(np.clip(np.round(a * 255), 0, 255).astype(np.uint8), "RGBA").save(path, optimize=True)
        L.register(dict(file=rel, kind="ramp", size=[256, rows], grid=[1, rows], frames=1, fps=None,
                        intended=("smooth ramps: light spill, heat haze, soft smoke" if smooth else
                                  "posterized element ramps: G (value) -> colour; sample at v = (row + 0.5) / 16"),
                        rows=[dict(row=i, key=k, label=lab, tones=dict(zip(["ink", "deep", "body", "light", "hot"], c)))
                              for i, (k, lab, c) in enumerate(L.RAMPS)],
                        color_space="RGB sRGB, A linear = HDR gain / 4", band_edges=list(L.BAND_EDGES)))


if __name__ == "__main__":
    L.load_manifest()
    build()
    L.write_manifest()
