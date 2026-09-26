"""Contact sheets and animated preview strips for docs/art/vfx_concepts/assets_*.png.

Every sheet renders the shipped assets through the reference shader (vfxlib.shade), the way vfx.wesl
will: packed cell -> SDF coverage -> posterized ramp -> premultiplied composite -> bloom -> tonemap.
assets_game_scale.png composites them at the real game scale (~36 px/m at 1600 x 900) over in-game
plates, with the red-white telegraph restored on top (it draws after every VFX layer).
"""
import json
import math
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import preview as V
import vfxlib as L

BG = "#241D1F"
MID = "#4E423F"
PALE = "#8E7E70"
TITLE_H = 70


def entry(rel):
    for e in L.MANIFEST:
        if e["file"] == rel:
            return e
    raise KeyError(rel)


def seq(rel, name):
    e = entry(rel)
    s = [q for q in e["sequences"] if q["name"] == name][0]
    img = L.load_atlas(rel)
    return [V.frame_of(img, e, s, i) for i in range(s["frames"])], s


def sheet(w, h, title, sub, bg=BG):
    p = L.Plate(w, h, bg)
    p.rect(0, 0, w, TITLE_H, "#140F11")
    p.rect(0, TITLE_H - 2, w, TITLE_H, "#6A5330")
    p.label(18, 12, title, 28, (240, 214, 160), "Cinzel-Variable.ttf")
    p.label(20, 46, sub, 15, (200, 188, 170))
    return p


def band(p, y0, y1, col):
    p.rect(0, y0, p.W, y1, col)


def draw(p, cell, ramp, cx, cy, scale, ink=False, t=0.0, value=None, sx=None, sy=None, angle=0.0, pivot=None,
         alpha=1.0, cool=0.0, size=None):
    h, w = cell.shape[:2]
    if size is None:
        size = int(max(w * (sx or scale), h * (sy or scale)) * (1.5 if ink else 1.05)) + 6
    if ink:
        V.put(p, V.sprite(cell, ramp, scale * 1.3, angle + 0.11, size, pivot, t=t, value=L.V_INK, alpha=0.95 * alpha,
                          sx=None if sx is None else sx * 1.3, sy=None if sy is None else sy * 1.3), cx, cy)
    V.put(p, V.sprite(cell, ramp, scale, angle, size, pivot, t=t, value=value, alpha=alpha, sx=sx, sy=sy, cool=cool),
          cx, cy)


def out(name):
    return os.path.join(L.SHEETS, f"assets_{name}.png")


def save(p, name, shoulder=0.8):
    path = out(name)
    p.finish(shoulder=shoulder).save(path, optimize=True)
    print("sheet", os.path.relpath(path, L.ROOT), os.path.getsize(path) // 1024, "KB")
    return path


# ------------------------------------------------------------------------------------------------
def sheet_impacts():
    W, H = 1840, 1430
    p = sheet(W, H, "VFX assets · impact stars and muzzle flashes",
              "atlas/vfx_impact_star.png (ink backing = the same frame at value 0.06, 1.3x, +6 deg), "
              "atlas/vfx_petal_flash.png, atlas/vfx_muzzle_directional.png · rendered through the reference shader")
    band(p, TITLE_H, 760, MID)
    y = TITLE_H + 26
    p.label(20, y - 16, "impact star · frames painted at f0 1 2 4 6 8 11 14 (60 fps) · played at 30 fps · ink backing on "
            "frames 0-4 only", 16, (240, 214, 160))
    for r, (name, ramp) in enumerate([("star4", "radiant"), ("star5", "kinetic"), ("star7", "flame"), ("star9", "storm")]):
        frames, _ = seq("atlas/vfx_impact_star.png", name)
        cy = y + 80 + r * 162
        p.label(20, cy, f"{name} / {ramp}", 15, anchor="lm")
        for i, fr in enumerate(frames):
            draw(p, fr, ramp, 250 + i * 150, cy, 0.52, ink=i <= 4, size=220)
    # one frame, every ramp
    fr = seq("atlas/vfx_impact_star.png", "star7")[0][2]
    y2 = y + 80 + 4 * 162 - 30
    p.label(1640, TITLE_H + 14, "star7 f2, every ramp", 14, (240, 214, 160), anchor="ma")
    for k, (key, lab, _) in enumerate(L.RAMPS):
        cx = 1485 + (k % 4) * 104
        cy = TITLE_H + 100 + (k // 4) * 158
        draw(p, fr, key, cx, cy, 0.36, ink=True, size=140)
        p.label(cx, cy + 50, key, 11, anchor="ma")
    y = 790
    p.label(20, y, "petal flashes · f0 core, f1 full, f2 break-up, f3 remnants · pivot = the muzzle socket", 16, (240, 214, 160))
    names = [("forward_fan", ["kinetic", "storm"]), ("sunburst", ["radiant"]), ("cross", ["radiant"]), ("inward_star", ["void"])]
    row = 0
    for name, ramps in names:
        frames, s = seq("atlas/vfx_petal_flash.png", name)
        for rp in ramps:
            cy = y + 70 + row * 118
            p.label(20, cy, f"{name} / {rp}", 14, anchor="lm")
            for i, fr in enumerate(frames):
                draw(p, fr, rp, 250 + i * 150, cy, 0.46, size=130)
            row += 1
    x0 = 900
    p.label(x0, y + 20, "directional flashes (256 x 128) · muzzle at u = 0.06", 15, (240, 214, 160))
    for r, (name, rp) in enumerate([("flicker3", "kinetic"), ("flicker3", "enemy_shot"), ("spike", "kinetic"),
                                    ("rail", "storm"), ("petal_bloom", "plague")]):
        frames, s = seq("atlas/vfx_muzzle_directional.png", name)
        cy = y + 70 + r * 118
        p.label(x0, cy, f"{name} / {rp}", 14, anchor="lm")
        for i, fr in enumerate(frames):
            draw(p, fr, rp, x0 + 290 + i * 190, cy, 0.7, pivot=(0.5, 0.5), size=190)
    return save(p, "impacts_flashes")


def sheet_bursts():
    from atlas_bursts import ELEMENTS, RAMP_OF, T16
    W = 1900
    step = 108
    H = TITLE_H + 50 + len(ELEMENTS) * 116 + 20
    p = sheet(W, H, "VFX assets · element bursts (16-frame flipbooks)",
              "atlas/vfx_burst_<element>.png · painted at front-loaded 60 fps times, played at 24 fps: fast in, slow out · "
              "R = radius_in_cell 0.55")
    band(p, TITLE_H, H, MID)
    y = TITLE_H + 32
    for i, t in enumerate(T16):
        p.label(170 + i * step + step // 2, y - 20, f"f{t:g}", 13, (240, 214, 160), anchor="ma")
    for r, name in enumerate(ELEMENTS):
        frames, s = seq(f"atlas/vfx_burst_{name}.png", "burst")
        cy = y + 40 + r * 116
        p.label(20, cy - 8, name, 16, anchor="lm")
        p.label(20, cy + 12, f"ramp {RAMP_OF[name]}", 12, (190, 176, 160), anchor="lm")
        for i, fr in enumerate(frames):
            draw(p, fr, RAMP_OF[name], 170 + i * step + step // 2, cy, 0.43, size=112)
    return save(p, "bursts")


def sheet_particles():
    W, H = 1840, 1500
    p = sheet(W, H, "VFX assets · smoke, sparks, shards, motes and flames",
              "atlas/vfx_smoke_puff.png (8 silhouettes x 4 ages, lit from the cell top), atlas/vfx_sparks_shards.png, "
              "atlas/vfx_flame_tongue.png (8-frame loops)")
    band(p, TITLE_H, 700, MID)
    y = TITLE_H + 30
    p.label(20, y - 12, "smoke puffs · ages 0-3 · kinetic (rim lit by the blast) and dust ramps", 16, (240, 214, 160))
    e = entry("atlas/vfx_smoke_puff.png")
    img = L.load_atlas("atlas/vfx_smoke_puff.png")
    for age in range(4):
        for v in range(8):
            cell = V.cell_of(img, (256, 256), v, age)
            rp = "kinetic" if v < 4 else "dust"
            draw(p, cell, rp, 110 + v * 150 + (40 if v >= 4 else 0), y + 80 + age * 146, 0.55, size=150)
    p.label(1330, y + 40, "the rim cools with age\n(shader 'cool'): t = 0, .35, .7", 14, anchor="la")
    cell = V.cell_of(img, (256, 256), 0, 1)
    for k, t in enumerate((0.0, 0.35, 0.7)):
        draw(p, cell, "flame", 1400 + k * 140, y + 200, 0.5, t=t, cool=0.9, size=140)
    cell = V.cell_of(img, (256, 256), 6, 0)
    for k, rp in enumerate(("storm", "void", "plague")):
        draw(p, cell, rp, 1400 + k * 140, y + 360, 0.5, size=140)
    p.label(1330, y + 440, "one silhouette, three ramps", 14)
    y = 730
    p.label(20, y, "sparks · shards · teardrops · coin spin · glints · element motes (128 px) · kinetic / unmade / "
                   "godworks_gold / bleed", 16, (240, 214, 160))
    img = L.load_atlas("atlas/vfx_sparks_shards.png")
    for r in range(4):
        rp = ["kinetic", "unmade", "godworks_gold", "flame"][r]
        for c in range(8):
            cell = V.cell_of(img, (128, 128), c, r)
            rp2 = "bleed" if (r == 2 and c < 4 and c % 2 == 1) else rp
            if r == 3 and c >= 4:
                rp2 = ["flame", "plague", "void", "dust"][c - 4]
            draw(p, cell, rp2, 90 + c * 118, y + 80 + r * 112, 0.8, size=112)
    x0 = 1060
    p.label(x0, y + 30, "flame tongues · 8-frame loops · flame and plague", 15, (240, 214, 160))
    img = L.load_atlas("atlas/vfx_flame_tongue.png")
    for r in range(4):
        for c in range(8):
            cell = V.cell_of(img, (128, 256), c, r)
            draw(p, cell, "flame" if r != 2 else "plague", x0 + 50 + c * 96, y + 140 + r * 175, 0.66, size=180)
    p.label(20, 1240, "flames read by shape: nested tongues (deep tip and rim, body, light, hot core at the base)", 14)
    return save(p, "particles_flames")


def sheet_elements():
    W, H = 1840, 1880
    p = sheet(W, H, "VFX assets · storm, void, plague, radiant and spark flipbooks",
              "atlas/vfx_bolt_strips.png, vfx_storm.png, vfx_void_swirl.png, vfx_plague.png, vfx_radiant.png, vfx_sparkfx.png")
    band(p, TITLE_H, H, MID)
    y = TITLE_H + 30
    p.label(20, y - 12, "lightning strips (1024 x 64) · shown native, and stretched to a 7 m hop at game scale", 16, (240, 214, 160))
    img = L.load_atlas("atlas/vfx_bolt_strips.png")
    for i in range(8):
        cell = img[i * 64:(i + 1) * 64]
        draw(p, cell, "storm" if i < 6 else "void", 20 + 440, y + 30 + i * 44, 0.86, size=(900, 64))
    for i in range(4):
        cell = img[i * 64:(i + 1) * 64]
        cx = 1120 + (i % 2) * 330
        cy = y + 90 + (i // 2) * 150
        draw(p, cell, ["storm", "storm", "radiant", "plague"][i], cx, cy, 1.0, sx=260 / 1024, sy=34 / 64,
             angle=0.4 * (i - 1.5), size=320)
    y = 470
    p.label(20, y, "Lichtenberg scorch · micro-arc crackle", 16, (240, 214, 160))
    img = L.load_atlas("atlas/vfx_storm.png")
    for k in range(8):
        cell = V.cell_of(img, (256, 256), k % 4, k // 4)
        draw(p, cell, "storm", 100 + k * 150, y + 90, 0.55, sy=0.55 * (0.82 if k < 4 else 1.0), size=150)
    y = 660
    p.label(20, y, "void swirl · 16-frame loop (Well hazard, implosions, Eclipse), shown on the ground plane", 16, (240, 214, 160))
    frames, _ = seq("atlas/vfx_void_swirl.png", "swirl")
    for i in range(16):
        draw(p, frames[i], "void", 70 + i * 110, y + 80, 0.4, sy=0.4 * 0.82, size=112)
    y = 820
    p.label(20, y, "plague · bubble, drip, splat, spores (128 px, 8 frames)", 16, (240, 214, 160))
    for r, name in enumerate(["bubble", "drip", "splat", "spores"]):
        frames, _ = seq("atlas/vfx_plague.png", name)
        for i, fr in enumerate(frames):
            draw(p, fr, "plague", 80 + i * 100, y + 70 + r * 100, 0.72, size=100)
    x0 = 900
    p.label(x0, y, "radiant · cross flare, ray fan, halo arcs, ground sunburst", 16, (240, 214, 160))
    for r, name in enumerate(["cross_flare", "ray_fan", "halo_arcs", "sunburst"]):
        frames, _ = seq("atlas/vfx_radiant.png", name)
        for i, fr in enumerate(frames):
            draw(p, fr, "radiant", x0 + 60 + i * 112, y + 70 + r * 100, 0.4, sy=0.4 * (0.82 if r == 3 else 1.0), size=112)
    y = 1260
    p.label(20, y, "spark flipbooks · radial burst, cone spray, gold shower, ember/ash drift", 16, (240, 214, 160))
    for r, (name, rp) in enumerate([("radial_burst", "kinetic"), ("cone_spray", "storm"), ("shower", "zone_gold"),
                                    ("ember_drift", "flame")]):
        frames, _ = seq("atlas/vfx_sparkfx.png", name)
        for i, fr in enumerate(frames):
            draw(p, fr, rp, 80 + i * 150, y + 80 + r * 135, 0.55, size=150)
    p.label(1300, y + 60, "sparks are chunky on purpose:\nat 36 px/m a spark is 4-8 px wide", 14)
    return save(p, "elements")


def sheet_glyphs_decals():
    W, H = 1840, 1300
    p = sheet(W, H, "VFX assets · sigils, status pips and ground decals",
              "atlas/vfx_glyphs.png (256), atlas/vfx_pips.png (128, shown at 64 / 40 / 24 px), atlas/vfx_decals.png "
              "(ground plane, never bloom)")
    band(p, TITLE_H, 560, MID)
    from atlas_glyphs import DECALS, GLYPHS, PIPS
    y = TITLE_H + 30
    img = L.load_atlas("atlas/vfx_glyphs.png")
    for k in range(16):
        cell = V.cell_of(img, (256, 256), k % 4, k // 4)
        rp = "void" if k in (0, 2, 3) else ("time" if k == 6 else ("radiant" if k < 8 else "zone_gold"))
        cx, cy = 70 + k * 112, y + 60
        draw(p, cell, rp, cx, cy, 0.4, size=110)
        p.label(cx, cy + 54, GLYPHS[k].replace("god_", ""), 11, anchor="ma")
    y = 280
    img = L.load_atlas("atlas/vfx_pips.png")
    for k in range(16):
        cell = V.cell_of(img, (128, 128), k % 4, k // 4)
        rp = ["flame", "storm", "void", "plague", "bleed", "radiant", "radiant", "void", "radiant", "enemy_shot", "storm",
              "kinetic", "zone_gold", "zone_gold", "heal", "time"][k]
        cx = 70 + k * 112
        for j, sc in enumerate((0.5, 0.31, 0.19)):
            draw(p, cell, rp, cx, y + 36 + [0, 60, 104][j], sc, size=70)
        p.label(cx, y + 142, PIPS[k], 11, anchor="ma")
    y = 590
    p.label(20, y, "decals on a dark and a pale floor (squashed 0.82 by the 55 deg camera) · scorches keep their "
                   "glowing cracks for 40 frames (low B)", 16, (240, 214, 160))
    img = L.load_atlas("atlas/vfx_decals.png")
    for half, bg in enumerate(("#2A2224", PALE)):
        p.rect(0, y + 20 + half * 330, W, y + 20 + (half + 1) * 330, bg)
        for k in range(16):
            cell = V.cell_of(img, (256, 256), k % 4, k // 4)
            rp = ["flame", "kinetic", "storm", "dust", "dust", "dust", "flame", "unmade", "unmade", "plague", "plague",
                  "void", "void", "plague", "dust", "flame"][k]
            cx = 70 + (k % 8) * 222 + (k // 8) * 111
            cy = y + 100 + half * 330 + (k // 8) * 150
            draw(p, cell, rp, cx, cy, 0.5, sy=0.5 * 0.82, alpha=0.9, size=150)
            if half == 0:
                p.label(cx, cy + 60, DECALS[k], 11, anchor="ma")
    return save(p, "glyphs_decals")


# ---- strips mapped onto curves -----------------------------------------------------------------
def warp_arc(strip, C, R, a0, a1, width, ky=0.82, size=None, peak=0.72):
    """Map a strip (u tail->head, v inner->outer) onto a crescent: returns a float packed layer."""
    Wd = int(size[0]) if size else int(2 * R + 2 * width + 10)
    Hd = int(size[1]) if size else Wd
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32) + 0.5
    x = xx - C[0]
    y = (yy - C[1]) / ky
    th = np.arctan2(y, x)
    r = np.hypot(x, y)
    span = a1 - a0
    sg = 1.0 if span >= 0 else -1.0
    t = np.mod((th - a0) * sg, 2 * np.pi) / abs(span)
    tc = np.clip(t, 0, 1)
    w = np.where(tc < peak, np.sin(np.clip(tc / peak, 0, 1) * np.pi / 2) ** 1.3,
                 np.sqrt(np.clip(1 - ((tc - peak) / (1 - peak)) ** 2, 0, 1))) * width
    w = np.maximum(w, 0.8)
    v = 1 - (R - r) / w
    inside = (t <= 1) & (v >= 0) & (v <= 1)
    h, wd = strip.shape[:2]
    su = tc * (wd - 1)
    sv = np.clip(v, 0, 1) * (h - 1)
    chans = [ndi.map_coordinates(strip[..., k].astype(np.float32) / 255, [sv, su], order=1, mode="nearest") for k in range(3)]
    out = np.stack(chans, -1)
    out[~inside] = 0
    return out


def warp_path(strip, pts, width, size, tile_len=None):
    """Map a strip onto a polyline (pts from tail to head) with a constant width."""
    Wd, Hd = size
    P = np.asarray(pts, np.float32)
    seg = np.linalg.norm(P[1:] - P[:-1], axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32) + 0.5
    best = np.full(xx.shape, 1e9, np.float32)
    U = np.zeros_like(xx)
    S = np.zeros_like(xx)
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        d = b - a
        L2 = float(d @ d) or 1e-6
        t = np.clip(((xx - a[0]) * d[0] + (yy - a[1]) * d[1]) / L2, 0, 1)
        px = a[0] + d[0] * t
        py = a[1] + d[1] * t
        dist = np.hypot(xx - px, yy - py)
        side = np.sign((xx - a[0]) * d[1] - (yy - a[1]) * d[0])
        m = dist < best
        best = np.where(m, dist, best)
        U = np.where(m, (cum[i] + t * np.sqrt(L2)), U)
        S = np.where(m, side * dist, S)
    u = U / total if tile_len is None else (U / tile_len) % 1.0
    v = 0.5 + S / width
    inside = (np.abs(S) < width / 2)
    h, wd = strip.shape[:2]
    chans = [ndi.map_coordinates(strip[..., k].astype(np.float32) / 255, [np.clip(v, 0, 1) * (h - 1), u * (wd - 1)],
                                 order=1, mode="grid-wrap" if tile_len else "nearest") for k in range(3)]
    out = np.stack(chans, -1)
    out[~inside] = 0
    return out


def shade_layer(tex, ramp, scale=1.0, t=0.0, alpha=1.0):
    return L.shade(tex, ramp, t=t, alpha=alpha, scale=scale)


def sheet_strips():
    from atlas_strips import SMEARS, TRAILS
    W, H = 1840, 1620
    p = sheet(W, H, "VFX assets · trail and smear strips",
              "trails/vfx_trails.png (1024 x 64 rows) and smears/vfx_smears.png (1024 x 128 rows) · u = 0 tail .. 1 head · "
              "right: the same strips bent onto paths and crescents")
    band(p, TITLE_H, H, MID)
    img = L.load_atlas("trails/vfx_trails.png")
    y = TITLE_H + 26
    ramps_t = ["storm", "kinetic", "void", "kinetic", "storm", "dust", "zone_gold", "flame", "void", "radiant", "kinetic",
               "radiant", "flame", "zone_gold", "zone_gold", "zone_gold"]
    for k, (name, tile, _) in enumerate(TRAILS):
        cell = img[k * 64:(k + 1) * 64]
        cy = y + 22 + k * 44
        p.label(20, cy, name + (" (tiles)" if tile else ""), 13, anchor="lm")
        draw(p, cell, ramps_t[k], 200 + 360, cy, 0.7, size=(730, 48))
    img_s = L.load_atlas("smears/vfx_smears.png")
    y = TITLE_H + 26 + 16 * 44 + 30
    ramps_s = ["kinetic", "radiant", "dust", "flame", "void", "storm", "kinetic", "storm"]
    for k, (name, tile, _) in enumerate(SMEARS):
        cell = img_s[k * 128:(k + 1) * 128]
        cy = y + 30 + k * 76
        p.label(20, cy, name, 13, anchor="lm")
        draw(p, cell, ramps_s[k], 200 + 360, cy, 0.7, size=(730, 94))
    # in use: crescents
    x0, y0 = 960, TITLE_H + 20
    p.label(x0, y0, "smears on crescents (ground plane, the 55 deg squash) · trails on paths", 15, (240, 214, 160))
    arcs = [(0, "kinetic"), (3, "flame"), (4, "void"), (5, "storm"), (1, "radiant"), (2, "dust")]
    for k, (row, rp) in enumerate(arcs):
        cell = img_s[row * 128:(row + 1) * 128]
        mirror = k % 2 == 1
        a0, a1 = (math.radians(15), math.radians(165))
        if mirror:
            a0, a1 = a1, a0
        tex = warp_arc(cell, (150, 40), 125, a0, a1, 64 if row != 1 else 34, size=(300, 170))
        lay = shade_layer(tex, rp, scale=0.5)
        cx = x0 + 150 + (k % 3) * 290
        cy = y0 + 120 + (k // 3) * 220
        V.put(p, lay, cx, cy)
        p.label(cx, cy + 86, SMEARS[row][0], 12, anchor="ma")
    # trails on paths
    y1 = y0 + 560
    paths = [
        (0, "storm", [(20, 60), (400, 30)], 20), (1, "kinetic", [(20, 110), (150, 95), (300, 70), (420, 90)], 22),
        (2, "void", [(20, 170), (440, 140)], 30), (3, "kinetic", [(30, 250), (200, 200), (430, 220)], 36),
        (4, "storm", [(30, 300), (440, 290)], 26), (7, "flame", [(30, 360), (220, 330), (440, 370)], 30),
        (9, "radiant", [(30, 420), (440, 410)], 22), (6, "zone_gold", [(30, 470), (440, 460)], 18),
    ]
    for row, rp, pts, width in paths:
        cell = img[row * 64:(row + 1) * 64]
        tex = warp_path(cell, pts, width, (470, 500))
        V.put(p, shade_layer(tex, rp, scale=0.45), x0 + 235 + 20, y1 + 250)
    tiles = [(11, "flame", [(20, 560), (440, 540)], 14, 160), (12, "flame", [(20, 600), (440, 580)], 26, 200),
             (13, "zone_gold", [(20, 650), (440, 650)], 20, 140), (14, "storm", [(20, 700), (200, 690), (440, 720)], 14, 90)]
    for row, rp, pts, width, tl in tiles:
        cell = img[row * 64:(row + 1) * 64]
        tex = warp_path(cell, [(x, y - 500) for x, y in pts], width, (470, 260), tile_len=tl)
        V.put(p, shade_layer(tex, rp, scale=0.5), x0 + 255, y1 + 500 + 130)
    p.label(x0 + 490, y1 + 40, "tracer\ndry brush (bolt)\nghost smear (arrow)\nsmoke (shell)\nhelix (orb)\n"
            "flame trail\nglint trail (shard)\nzig-zag (coin)", 13)
    p.label(x0 + 490, y1 + 520, "beam core, beam body,\nloot beam, tether braid\n(tileable along u)", 13)
    return save(p, "strips")


def sheet_noise_ramps():
    W, H = 1840, 1180
    p = sheet(W, H, "VFX assets · ramps, noise and the packed format",
              "ramps/vfx_ramps.png (16 rows, posterized; A = HDR gain / 4), noise/*.png (tileable, shown 2 x 2), and one "
              "packed cell decoded channel by channel")
    band(p, TITLE_H, H, MID)
    y = TITLE_H + 30
    ramp_img = np.asarray(Image.open(os.path.join(L.OUT, "ramps/vfx_ramps.png")).convert("RGB"))
    ramp_s = np.asarray(Image.open(os.path.join(L.OUT, "ramps/vfx_ramps_smooth.png")).convert("RGB"))
    for k, (key, lab, cols) in enumerate(L.RAMPS):
        yy = y + k * 34
        row = Image.fromarray(ramp_img[k:k + 1]).resize((512, 26), Image.NEAREST)
        rows = Image.fromarray(ramp_s[k:k + 1]).resize((256, 26), Image.BILINEAR)
        p.paste(row, 330, yy)
        p.paste(rows, 860, yy)
        p.label(20, yy + 13, f"{k:2d} {key}", 14, anchor="lm")
        p.label(1130, yy + 13, lab, 13, (200, 188, 170), anchor="lm")
    p.label(330, y - 16, "posterized (ink | deep | body | light | hot)", 13, (240, 214, 160))
    p.label(860, y - 16, "smooth", 13, (240, 214, 160))
    y = y + 16 * 34 + 30
    p.label(20, y, "noise tiles (2 x 2 to show the wrap)", 16, (240, 214, 160))
    for k, f in enumerate(["noise_erode_256", "noise_streak_256", "noise_brush_256", "noise_cells_256", "noise_hex_256"]):
        im = Image.open(os.path.join(L.OUT, f"noise/{f}.png")).convert("RGB")
        t = Image.new("RGB", (512, 512))
        for dx in (0, 256):
            for dy in (0, 256):
                t.paste(im, (dx, dy))
        t = t.resize((230, 230), Image.BILINEAR)
        p.paste(t, 20 + k * 250, y + 20)
        p.label(20 + k * 250 + 115, y + 258, f.replace("_256", ""), 13, anchor="ma")
    x0 = 1290
    p.label(x0, y, "the packed cell (star7 f2)", 16, (240, 214, 160))
    cell = seq("atlas/vfx_impact_star.png", "star7")[0][2]
    for k, (nm, ch) in enumerate((("R: SDF mask", 0), ("G: value", 1), ("B: erosion", 2))):
        im = Image.fromarray(cell[..., ch]).convert("RGB").resize((150, 150), Image.BILINEAR)
        p.paste(im, x0 + k * 170, y + 20)
        p.label(x0 + k * 170 + 75, y + 176, nm, 12, anchor="ma")
    for k, t in enumerate((0.0, 0.3, 0.55, 0.8)):
        draw(p, cell, "flame", x0 + 60 + k * 135, y + 250, 0.5, t=t, size=135)
        p.label(x0 + 60 + k * 135, y + 312, f"t = {t:g}", 12, anchor="ma")
    return save(p, "noise_ramps")


def sheet_meshes(render_path):
    W, H = 1840, 1130
    p = sheet(W, H, "VFX assets · meshes (glTF, Blender 5.2)",
              "meshes/*.glb · COLOR_0 packed like the atlases (G = value band -> ramp) · arcs, rings and beams are shown "
              "with their strip textures · ink outline = inverted hull, as in game")
    im = Image.open(render_path).convert("RGB")
    im = im.resize((1800, 1000), Image.LANCZOS)
    p.paste(im, 20, TITLE_H + 20)
    labels = json.load(open(render_path + ".json"))
    for name, (x, y) in labels.items():
        tris = BM_TRIS.get(name)
        p.label(20 + x * 1800 / 1800, TITLE_H + 20 + y + 70, f"{name.replace('vfx_', '')}" + (f" · {tris} tris" if tris else ""),
                13, anchor="ma")
    return save(p, "meshes")


BM_TRIS = {}


# ---- game scale ------------------------------------------------------------------------------------
PPM = 36.0  # px per metre at 1600 x 900
KY = 0.82


def restore_telegraph(plate, base_lin, c, rx, ry):
    """Telegraphs sort after every VFX layer: put the red-dominant plate pixels back inside the ellipse."""
    yy, xx = np.mgrid[0:plate.H, 0:plate.W]
    d = np.hypot((xx - c[0]) / rx, (yy - c[1]) / ry)
    b = L.l2s(base_lin)
    red = (b[..., 0] > 0.45) & (b[..., 1] < 0.62 * b[..., 0]) & (b[..., 2] < 0.55 * b[..., 0]) & (d <= 1.05)
    a = red[..., None].astype(np.float32)
    plate.img = plate.img * (1 - a) + base_lin * a


def burst_at(p, name, f_idx, x, y, R_m, ramp=None, alpha=1.0):
    from atlas_bursts import RAMP_OF, RIC
    frames, s = seq(f"atlas/vfx_burst_{name}.png", "burst")
    side = 2 * R_m * PPM / RIC
    sc = side / 256
    draw(p, frames[f_idx], ramp or RAMP_OF[name], x, y + (0.56 - 0.5) * side, sc, alpha=alpha, pivot=(0.5, 0.5))


def sheet_game_scale():
    W = 1640
    H = TITLE_H + 20 + 480 + 40 + 400 + 20
    p = sheet(W, H, "VFX assets · at game scale (1:1, ~36 px/m, 1600 x 900)",
              "composited over in-game Cinder captures with the reference shader · allies' effects at 0.55 alpha · the "
              "red-white telegraph restored on top (it sorts after every VFX layer)")
    plate_a = Image.open(os.path.join(os.path.dirname(__file__), "plates", "cinder_road.jpg")).convert("RGB")
    plate_b = Image.open(os.path.join(os.path.dirname(__file__), "plates", "cinder_slag_flats.jpg")).convert("RGB")
    # --- plate A: Brax's gauntlets, a kinetic burst, a storm chain, a flame burst, a void well, needles
    A = L.Plate(800, 480, image=plate_a)
    baseA = A.img.copy()
    dec = L.load_atlas("atlas/vfx_decals.png")
    draw(A, V.cell_of(dec, (256, 256), 0, 0), "flame", 585, 318, 1.6 * PPM * 2 / 0.72 / 256 * 0.9,
         sy=1.6 * PPM * 2 / 0.72 / 256 * 0.9 * KY, alpha=0.8)
    # void well on the ground (ally, 0.55)
    sw = seq("atlas/vfx_void_swirl.png", "swirl")[0]
    sc = 1.4 * PPM * 2 / 0.88 / 256
    draw(A, sw[5], "void", 120, 400, sc, sy=sc * KY, alpha=0.55)
    burst_at(A, "kinetic", 4, 585, 312, 1.6)
    burst_at(A, "flame", 6, 598, 80, 1.3, alpha=0.55)
    # an ally's burst lands on the telegraph: the telegraph must still read on top
    burst_at(A, "kinetic", 9, 300, 318, 1.2, alpha=0.55)
    # storm chain hops with node stars
    bolts = L.load_atlas("atlas/vfx_bolt_strips.png")
    nodes = [(255, 34), (282, 96), (420, 150)]
    stars = seq("atlas/vfx_impact_star.png", "star4")[0]
    for k in range(len(nodes) - 1):
        a, b = nodes[k], nodes[k + 1]
        L_ = math.hypot(b[0] - a[0], b[1] - a[1])
        ang = -math.atan2(b[1] - a[1], b[0] - a[0])
        cell = bolts[(k * 3 % 8) * 64:(k * 3 % 8 + 1) * 64]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        draw(A, cell, "storm", mid[0], mid[1], 1.0, sx=L_ / 1024, sy=26 / 64, angle=ang, size=int(L_ + 40))
    for n in nodes[1:]:
        draw(A, stars[2], "storm", n[0], n[1], 0.16, ink=True, size=70)
    # Brax's gauntlet finisher: a crescent smear and a contact star
    smears = L.load_atlas("smears/vfx_smears.png")
    tex = warp_arc(smears[0:128], (80, 80), 62, math.radians(-150), math.radians(10), 30, size=(160, 160))
    V.put(A, shade_layer(tex, "kinetic", scale=0.25), 420, 262)
    draw(A, seq("atlas/vfx_impact_star.png", "star5")[0][2], "kinetic", 478, 252, 0.2, ink=True, size=90)
    # needle stream from Brax toward the upper left
    trails = L.load_atlas("trails/vfx_trails.png")
    for k, (x0, y0, x1, y1) in enumerate([(400, 250, 330, 205), (360, 225, 290, 180), (315, 196, 262, 160)]):
        tex = warp_path(trails[10 * 64:11 * 64], [(x0 - 200, y0 - 120), (x1 - 200, y1 - 120)], 7, (200, 140))
        V.put(A, shade_layer(tex, "kinetic", scale=0.2), 300, 190)
    # crit on the far enemy
    draw(A, seq("atlas/vfx_radiant.png", "cross_flare")[0][1], "radiant", 598, 66, 0.2, size=70)
    # a plain hit spark cone off the enemy at the left
    draw(A, seq("atlas/vfx_sparkfx.png", "cone_spray")[0][2], "kinetic", 290, 96, 0.3, angle=math.radians(160),
         pivot=(0.12, 0.5), size=120)
    restore_telegraph(A, baseA, (257, 297), 52, 44)
    # --- plate B: plague and Unmade deaths, a radiant burst, a loot beam, a scorch and a curse sigil
    B = L.Plate(800, 400, image=plate_b)
    baseB = B.img.copy()
    gl = L.load_atlas("atlas/vfx_glyphs.png")
    draw(B, V.cell_of(gl, (256, 256), 0, 0), "void", 552, 244, 0.22, sy=0.22 * KY, alpha=0.9)
    burst_at(B, "plague", 6, 200, 250, 1.4)
    burst_at(B, "unmade", 3, 380, 300, 0.9)
    burst_at(B, "radiant", 3, 690, 120, 1.2, alpha=0.55)
    burst_at(B, "godworks", 5, 110, 110, 0.9, alpha=0.55)
    pips = L.load_atlas("atlas/vfx_pips.png")
    draw(B, V.cell_of(pips, (128, 128), 0, 0), "flame", 552, 196, 0.18)
    draw(B, V.cell_of(pips, (128, 128), 2, 0), "void", 575, 196, 0.18)
    # loot beam on a part
    tex = warp_path(trails[13 * 64:14 * 64], [(30, 230), (30, 10)], 16, (60, 240), tile_len=120)
    V.put(B, shade_layer(tex, "zone_gold", scale=0.25), 470, 250)
    draw(B, V.cell_of(pips, (128, 128), 3, 2), "radiant", 470, 368, 0.2)
    # a Mountainfall-style dust wall is best seen in the full recipe; here: a broken gold hem of an ally zone
    ring_strip = trails[15 * 64:16 * 64]
    yy, xx = np.mgrid[0:200, 0:320].astype(np.float32) + 0.5
    cx, cy, Rr = 160, 100, 120
    th = np.arctan2((yy - cy) / KY, xx - cx)
    rr = np.hypot(xx - cx, (yy - cy) / KY)
    u = ((th + np.pi) / (2 * np.pi) * 4) % 1.0
    v = 0.5 + (rr - Rr) / 12
    inside = np.abs(rr - Rr) < 6
    chans = [ndi.map_coordinates(ring_strip[..., k].astype(np.float32) / 255, [np.clip(v, 0, 1) * 63, u * 1023], order=1,
                                 mode="grid-wrap") for k in range(3)]
    tex = np.stack(chans, -1)
    tex[~inside] = 0
    V.put(B, L.shade(tex, "zone_gold", alpha=0.55, scale=0.3), 680, 300)
    restore_telegraph(B, baseB, (0, 0), 1, 1)
    # compose
    p.img[TITLE_H + 20:TITLE_H + 500, 20:820] = A.img
    p.img[TITLE_H + 20:TITLE_H + 420, 830:1630] = B.img
    p.label(28, TITLE_H + 504, "Brax's gauntlet finisher + contact star, a needle stream, a Storm chain, a kinetic burst "
            "(R 1.6 m) on its scorch; an ally's flame burst and void well at 0.55 · the enemy telegraph stays on top", 13)
    # 2x details
    y2 = TITLE_H + 540
    crop = A.img[200:400, 250:680]
    big = np.kron(crop, np.ones((2, 2, 1), np.float32))
    p.img[y2:y2 + big.shape[0], 20:20 + big.shape[1]] = big
    crop = B.img[180:380, 120:480]
    big = np.kron(crop, np.ones((2, 2, 1), np.float32))
    p.img[y2:y2 + big.shape[0], 900:900 + big.shape[1]] = big
    p.label(28, y2 + 8, "2x detail", 13)
    p.label(908, y2 + 8, "2x detail: plague splatter, an Unmade death, a Curse sigil with burn / curse pips", 13)
    p.label(838, TITLE_H + 424, "a plague burst, an Unmade death, allies' radiant and Godworks bursts (0.55), a loot beam, "
            "a gold zone hem", 13)
    return save(p, "game_scale", shoulder=0.92)


def ring_band(strip, R, thick, reps, ky=KY, size=None):
    """Map a tileable band (u round the ring, v across) onto a ground ellipse."""
    Wd = size or int(2 * R + 4 * thick)
    Hd = int(Wd * ky) + 8
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32) + 0.5
    cx, cy = Wd / 2, Hd / 2
    th = np.arctan2((yy - cy) / ky, xx - cx)
    rr = np.hypot(xx - cx, (yy - cy) / ky)
    u = ((th + np.pi) / (2 * np.pi) * reps) % 1.0
    v = 0.5 + (rr - R) / thick
    inside = np.abs(rr - R) < thick / 2
    h, w = strip.shape[:2]
    chans = [ndi.map_coordinates(strip[..., k].astype(np.float32) / 255, [np.clip(v, 0, 1) * (h - 1), u * (w - 1)],
                                 order=1, mode="grid-wrap") for k in range(3)]
    tex = np.stack(chans, -1)
    tex[~inside] = 0
    return tex


def sheet_bodies():
    W, H = 1840, 1000
    p = sheet(W, H, "VFX assets · projectile bodies, charge cues and ring bands",
              "atlas/vfx_bodies.png (billboards, head at +u) and trails/vfx_bands.png (tileable bands on meshes/vfx_ring_*)")
    band(p, TITLE_H, H, MID)
    y = TITLE_H + 30
    p.label(20, y - 12, "orb loop (storm, time) · globe loop (void, plague, kinetic iron)", 16, (240, 214, 160))
    frames, _ = seq("atlas/vfx_bodies.png", "orb")
    for i, fr in enumerate(frames):
        draw(p, fr, "storm", 80 + i * 110, y + 70, 0.8, size=110)
        draw(p, fr, "time", 80 + i * 110, y + 180, 0.8, size=110)
    frames, _ = seq("atlas/vfx_bodies.png", "globe")
    for i, fr in enumerate(frames):
        for r, rp in enumerate(("void", "plague", "kinetic")):
            draw(p, fr, rp, 980 + i * 105, y + 70 + r * 105, 0.78, size=110)
    y = 420
    p.label(20, y, "enemy shot (magenta core, ink shell, never an element colour) · needle, pellet, bolt, slug", 16,
            (240, 214, 160))
    frames, _ = seq("atlas/vfx_bodies.png", "enemy_shot")
    for i, fr in enumerate(frames):
        draw(p, fr, "enemy_shot", 80 + i * 120, y + 80, 0.9, sx=0.9 * 1.3, sy=0.9, size=160)
    frames, _ = seq("atlas/vfx_bodies.png", "small_bodies")
    for i, fr in enumerate(frames):
        draw(p, fr, ["kinetic", "radiant", "kinetic", "storm"][i], 600 + i * 130, y + 80, 0.9, size=130)
    p.label(1150, y, "charge: core stages and the tightening broken ring", 16, (240, 214, 160))
    frames, _ = seq("atlas/vfx_bodies.png", "charge_core")
    rings, _ = seq("atlas/vfx_bodies.png", "charge_ring")
    for i in range(4):
        draw(p, rings[i], "void", 1200 + i * 150, y + 90, 0.9, size=140)
        draw(p, frames[i], "void", 1200 + i * 150, y + 90, 0.5, size=140)
    y = 620
    p.label(20, y, "ring bands on the ground (the 55 deg squash): dust wall, shock front, Still Field ticks (x12), "
                   "hex shield", 16, (240, 214, 160))
    img = L.load_atlas("trails/vfx_bands.png")
    for k, (rp, reps, thick) in enumerate([("dust", 5, 40), ("zone_gold", 4, 22), ("time", 12, 30), ("godworks_gold", 3, 26)]):
        strip = img[k * 64:(k + 1) * 64]
        tex = ring_band(strip, 150, thick, reps, size=380)
        V.put(p, L.shade(tex, rp, scale=0.4), 220 + k * 450, y + 180)
    return save(p, "bodies_bands")


def build(mesh_render=None):
    L.load_manifest()
    os.makedirs(L.SHEETS, exist_ok=True)
    paths = [sheet_impacts(), sheet_bursts(), sheet_particles(), sheet_elements(), sheet_glyphs_decals(), sheet_strips(),
             sheet_noise_ramps(), sheet_bodies(), sheet_game_scale()]
    if mesh_render and os.path.exists(mesh_render):
        paths.append(sheet_meshes(mesh_render))
    return paths


if __name__ == "__main__":
    import sys
    only = sys.argv[1:]
    L.load_manifest()
    for name in only or ["impacts", "bursts", "particles", "elements", "glyphs", "strips", "noise", "bodies", "game"]:
        {"impacts": sheet_impacts, "bursts": sheet_bursts, "particles": sheet_particles, "elements": sheet_elements,
         "glyphs": sheet_glyphs_decals, "strips": sheet_strips, "noise": sheet_noise_ramps,
         "bodies": sheet_bodies, "game": sheet_game_scale}[name]()
