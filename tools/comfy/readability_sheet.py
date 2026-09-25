"""Stage 0: does the approved concept survive game scale? A 2D readability sheet.

  <comfy-python> tools/comfy/readability_sheet.py <key> <concept.png> [--height-m 2.2] [--out PNG]
        [--mask MASK.png] [--note "line" ...] [--horde N] [--ring] [--radius-m 0.55]

<comfy-python> = D:\\Comfy-Desktop\\ComfyUI-Installs\\ComfyUI\\standalone-env\\python.exe (PIL + numpy).

Cuts the figure out of the flat-background concept and shows it at the size a hero occupies in
game (6 % and 8 % of a 1080p frame = 65 / 86 px tall), in colour, as perceptual value (L*) and as
a flat silhouette; on each biome's ground colour (biomes.ron, unlit albedo tint = worst case);
and pasted into a real client frame (docs/media/doors.jpg) beside the current greybox hero, scaled
by in-game height (greybox ~2.0 u = 69 px there).

This is a 2D APPROXIMATION: a front T-pose plate pasted flat, not a render through the 55-degree
orthographic game camera (which shows the tops of the shoulders, head and gauntlets and shortens
the legs). The real in-camera check is the stage-1 blockout render. Default output:
art/characters/<key>/reports/stage0_readability.png

Options added for Valdris (without them the sheet is byte-identical to before):
  --mask MASK.png  figure mask (> 127 = figure) instead of the flat-background cut-out, for a concept
                   on a gradient background (e.g. the graph's birefnet mask from run_trellis.py --mask-only)
  --note "line"    replaces the pose notes beside panel 3 (repeat for several lines)
  --horde N        adds panel 4: the hero at 8 % (86 px) among N swarm enemies of each biome
                   (content/sheets/enemies.csv: class Swarm, colour, radius x scale, shape), spread over
                   a 1920x1080 frame and crowding him, as flat shaded tokens on the biome ground; shown
                   1:1 as colour and as value (L*), plus a row with the P1 ground ring (--ring,
                   colour = assets/content/game.ron player_colors[0]). Enemies never overlap (collision radius
                   as in the sim); the hero's radius comes from --radius-m (default 0.55). Deterministic.
"""
import csv
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

import gf_img as G

FRAME = os.path.join(G.ROOT, "docs", "media", "doors.jpg")
FRAME_HERO_PX = 69          # greybox hero (capsule + head, top ~2.0 u) measured in doors.jpg: y 385..454
FRAME_HERO_M = 2.0
FRAME_FEET = (690, 454)     # an empty patch of floor left of the greybox (at x 795)
FRAME_CROP = (560, 300, 1040, 520)
FLOOR_PATCH = (300, 560, 520, 700)   # lit Cinder Wastes flagstone in doors.jpg


def biomes():
    try:
        src = open(os.path.join(G.ROOT, "assets", "content", "biomes.ron"), encoding="utf-8").read()
    except OSError:
        return []
    pat = re.compile(r'key:\s*"(\w+)",\s*name:\s*"([^"]+)".*?palette:\s*\("(#\w{6})",\s*"(#\w{6})",\s*"(#\w{6})"\)', re.S)
    return [m.groups() for m in pat.finditer(src)]


def variants(fig_rgba, height):
    """colour, value (L*) and flat-silhouette versions at `height` px."""
    col = G.fit_height(fig_rgba, height)
    a = np.asarray(col)
    gray = G.lstar_gray(a[..., :3])
    val = Image.fromarray(np.dstack([gray, gray, gray, a[..., 3]]), "RGBA")
    sil = Image.fromarray(np.dstack([np.full(a.shape[:2], 16, np.uint8)] * 3 + [a[..., 3]]), "RGBA")
    return col, val, sil


def on(bg_rgb, fg, pad=10, size=None):
    w, h = size or (fg.width + 2 * pad, fg.height + 2 * pad)
    tile = Image.new("RGB", (w, h), tuple(int(c) for c in bg_rgb))
    tile.paste(fg, ((w - fg.width) // 2, h - pad - fg.height), fg)
    return tile


def up(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


HORDE_H = 360               # one row of panel 4: tile + label
HORDE_TILE = (540, 300)     # 1:1 crop around the hero, game pixels
HORDE_PX = 86               # hero height on screen: 8 % of 1080 px
PITCH = math.radians(55.0)  # the iso camera; the ground's depth axis is foreshortened by sin(55)


def swarm_enemies():
    """{biome: [(key, colour, radius_m, shape)]} for class Swarm in content/sheets/enemies.csv."""
    out = {}
    try:
        with open(os.path.join(G.ROOT, "content", "sheets", "enemies.csv"), encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("class") == "Swarm" and re.fullmatch(r"#[0-9A-Fa-f]{6}", r.get("color") or ""):
                    rad = float(r["radius"]) * float(r.get("scale") or 1.0)
                    out.setdefault(r["biome"], []).append((r["key"], r["color"], rad, r.get("shape") or "Blob"))
    except (OSError, ValueError, KeyError):
        return {}
    return out


def ring_colour():
    """The P1 ground-ring colour (assets/content/game.ron player_colors[0]); the ring is per player slot."""
    try:
        m = re.search(r'player_colors:\s*\(\s*"(#[0-9A-Fa-f]{6})"', open(os.path.join(G.ROOT, "assets", "content", "game.ron"), encoding="utf-8").read())
        if m:
            return G.hex_to_rgb(m.group(1))
    except OSError:
        pass
    return (255, 201, 64)


def shade(rgb, k):
    return tuple(int(max(0, min(255, c * k))) for c in rgb)


def token(d, x, y, rad_px, colour, shape):
    """A flat-shaded enemy token standing at ground point (x, y): contact shadow, body, top light."""
    c = G.hex_to_rgb(colour)
    w = rad_px * {"Hound": 1.25, "Crawler": 1.2}.get(shape, 1.0)
    h = rad_px * {"Hound": 1.25, "Crawler": 0.8, "Wisp": 1.0}.get(shape, 1.9)
    lift = rad_px * 1.1 if shape == "Wisp" else 0
    d.ellipse([x - w * 1.05, y - w * 0.45, x + w * 1.05, y + w * 0.45], fill=(0, 0, 0, 90))
    top = y - lift - h
    d.ellipse([x - w, top, x + w, y - lift], fill=shade(c, 0.62) + (255,))
    d.ellipse([x - w * 0.9, top, x + w * 0.9, y - lift - h * 0.3], fill=c + (255,))
    d.ellipse([x - w * 0.45, top + h * 0.08, x + w * 0.35, top + h * 0.38], fill=shade(c, 1.25) + (255,))


def horde_tile(fig86, ground, enemies, n, ppm, ring_rgb, seed, hero_r=0.55):
    """1:1 crop of a 1920x1080 frame: n enemies around the hero at the frame centre.

    Enemies never overlap (collision radius = enemies.csv radius x scale, as in the sim): each one
    tries positions from the crowd distribution first, then from the whole screen."""
    rng = np.random.default_rng(seed)
    FW, FH = 1920, 1080
    cx, cy = FW / 2.0, FH / 2.0 + HORDE_PX / 2.0          # hero's feet
    sy = math.sin(PITCH)
    half_w, half_d = FW / 2.0 / ppm, FH / 2.0 / ppm / sy   # the frame's half extent on the ground, metres
    pos = np.zeros((0, 2))
    rads = np.zeros(0)
    pts = []
    for i in range(n):
        e = enemies[int(rng.integers(len(enemies)))]
        crowd = i < int(n * 0.55)                          # the crowd pressing on him (he taunts)
        for t in range(300):
            if crowd and t < 60:
                r = hero_r + e[2] + abs(rng.normal(0.0, 2.5))
                a = rng.uniform(0.0, 2 * math.pi)
                x, z = r * math.cos(a), r * math.sin(a)
            else:                                          # the rest of the horde across the screen
                x, z = rng.uniform(-half_w, half_w), rng.uniform(-half_d, half_d)
            if math.hypot(x, z) < hero_r + e[2]:
                continue
            if len(rads) and (np.hypot(pos[:, 0] - x, pos[:, 1] - z) < rads + e[2]).any():
                continue
            pos = np.vstack([pos, [x, z]])
            rads = np.append(rads, e[2])
            px, py = cx + x * ppm, cy + z * ppm * sy
            if 0 <= px < FW and 0 <= py < FH:
                pts.append((py, px, e))
            break
    tw, th = HORDE_TILE
    ox, oy = int(cx - tw / 2), int(cy - th * 0.62)
    tile = Image.new("RGBA", (tw, th), tuple(ground) + (255,))
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")
    hero_drawn = False
    inside = 0
    for y, x, (k, col, rad, shape) in sorted(pts, key=lambda t: t[0]):
        if not hero_drawn and y >= cy:
            tile.alpha_composite(layer)
            layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer, "RGBA")
            put_hero(tile, fig86, cx - ox, cy - oy, ppm, ring_rgb)
            hero_drawn = True
        lx, ly = x - ox, y - oy
        if -40 < lx < tw + 40 and -60 < ly < th + 60:
            token(d, lx, ly, rad * ppm, col, shape)
            if 0 <= lx < tw and 0 <= ly < th:
                inside += 1
    tile.alpha_composite(layer)
    if not hero_drawn:
        put_hero(tile, fig86, cx - ox, cy - oy, ppm, ring_rgb)
    return tile.convert("RGB"), inside, len(pts)


def put_hero(tile, fig86, fx, fy, ppm, ring_rgb):
    if ring_rgb:
        d = ImageDraw.Draw(tile, "RGBA")
        rw = 1.2 * ppm
        d.ellipse([fx - rw, fy - rw * math.sin(PITCH), fx + rw, fy + rw * math.sin(PITCH)],
                  outline=ring_rgb + (255,), width=3)
    tile.alpha_composite(fig86, (int(fx - fig86.width / 2), int(fy - fig86.height)))


def horde_panel(sheet, d, key, fig, n, height_m, y0, ring, hero_r=0.55):
    cream, dim = (236, 228, 210), (150, 146, 140)
    ppm = HORDE_PX / height_m
    fig86 = G.fit_height(fig, HORDE_PX)
    enemies = swarm_enemies()
    G.text(d, (40, y0), "4  In the horde: %d swarm enemies per biome (enemies.csv colours and sizes), hero at 8 %% (86 px), 1:1 crops of a 1920x1080 frame"
           % n, 20, True, cream, anchor="ls")
    G.text(d, (40, y0 + 24), "Flat tokens on the unlit biome ground, no overlaps (collision radii), 55 %% of the horde crowding him (he taunts), the rest across the screen; "
           "row 2 is the same frame as value (L*)%s. A 2D approximation: no lighting, no VFX, no outline shader."
           % (", row 3 adds the P1 ground ring (game.ron player_colors)" if ring else ""), 15, False, dim, anchor="ls")
    rows = [("colour", False), ("value (L*)", False)] + ([("colour + player ring", True)] if ring else [])
    y = y0 + 44
    ring_rgb = ring_colour()
    for ri, (label, with_ring) in enumerate(rows):
        x = 40
        for bi, (bkey, name, ground, accent, fog) in enumerate(biomes()):
            ens = enemies.get(bkey)
            if not ens:
                continue
            tile, inside, total = horde_tile(fig86, G.hex_to_rgb(ground), ens, n, ppm, ring_rgb if with_ring else None, 1000 + bi,
                                             hero_r)
            if label.startswith("value"):
                g = G.lstar_gray(np.asarray(tile))
                tile = Image.fromarray(np.dstack([g, g, g]))
            sheet.paste(tile, (x, y))
            G.text(d, (x, y + tile.height + 22), "%s - %s: %d tokens in this crop (%d on screen)" % (name, label, inside, total),
                   14, False, dim, anchor="ls")
            x += tile.width + 20
        y += HORDE_H


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    key, concept = argv[1], G.absp(argv[2])
    height_m = float(argv[argv.index("--height-m") + 1]) if "--height-m" in argv else 2.2
    out = G.absp(argv[argv.index("--out") + 1]) if "--out" in argv else \
        os.path.join(G.ROOT, "art", "characters", key, "reports", "stage0_readability.png")

    mask_path = G.absp(argv[argv.index("--mask") + 1]) if "--mask" in argv else None
    notes_opt = [argv[i + 1] for i, a in enumerate(argv) if a == "--note"]
    horde = int(argv[argv.index("--horde") + 1]) if "--horde" in argv else 0
    rgb = np.asarray(Image.open(concept).convert("RGB"))
    bg = G.background_rgb(rgb)
    if mask_path:
        mask = np.asarray(Image.open(mask_path).convert("L")) > 127
    else:
        mask = G.figure_mask(rgb, bg)
    fig = G.cutout(rgb, mask)
    frame = Image.open(FRAME).convert("RGB")
    floor = np.median(np.asarray(frame.crop(FLOOR_PATCH)).reshape(-1, 3), axis=0)
    grey = (104, 100, 96)

    W, H = 2400, 1420
    if horde:
        H += HORDE_H * (3 if "--ring" in argv else 2) + 120
    sheet, d = G.new_sheet(W, H)
    cream, dim = (236, 228, 210), (150, 146, 140)
    G.text(d, (40, 64), key.upper(), 50, True, (255, 150, 90), anchor="ls")
    G.text(d, (40 + G.text_w(key.upper(), 50, True) + 18, 64), "readability at game scale  -  stage 0, 2D approximation", 32, True, cream, anchor="ls")
    G.text(d, (40, 98), "The approved front plate cut out and shrunk to in-game size. NOT a render through the 55-degree ortho camera "
                        "(that view shows shoulder/head/gauntlet tops and shortens the legs); the in-camera check is the stage-1 blockout.",
           17, False, dim, anchor="ls")

    # 1. 1:1 at 6 % and 8 % of 1080p, plus 3x enlargements of the 8 % versions
    y0 = 150
    G.text(d, (40, y0), "1  At game size, 1:1 pixels on the lit Cinder Wastes floor (sampled from doors.jpg %s)" % G.rgb_to_hex(floor), 20, True, cream, anchor="ls")
    x = 40
    sets = {}
    for hpx, label in ((65, "6 % of 1080p = 65 px"), (86, "8 % of 1080p = 86 px")):
        sets[hpx] = variants(fig, hpx)
    for name, idx in (("colour", 0), ("value (L*)", 1), ("silhouette", 2)):
        for hpx in (65, 86):
            t = on(floor, sets[hpx][idx], pad=12, size=(130, 110))
            sheet.paste(t, (x, y0 + 20))
            G.text(d, (x + 65, y0 + 150), "%s %dpx" % (name, hpx), 13, False, dim, anchor="ms")
            x += 138
        x += 16
    xb = x + 20
    xb0 = xb
    for idx in range(3):
        t = up(on(floor, sets[86][idx], pad=8, size=(118, 104)), 3)
        sheet.paste(t, (xb, y0 + 20))
        xb += t.width + 12
    G.text(d, (xb0, y0 + 20 + t.height + 22), "the 86 px versions at 3x (nearest neighbour: every block is one screen pixel)", 14, False, dim, anchor="ls")

    # 2. on each biome ground
    y1 = y0 + 390
    G.text(d, (40, y1), "2  On each biome's ground colour at 8 % (86 px), shown 2x  -  biomes.ron albedo tint, unlit = worst case; the lit floor is lighter", 20, True, cream, anchor="ls")
    x = 40
    for bkey, name, ground, accent, fog in biomes():
        t = on(G.hex_to_rgb(ground), sets[86][0], pad=10, size=(190, 108))
        # a strip of the biome's glow accent under the tile, for hue competition
        tile = up(t, 2)
        sheet.paste(tile, (x, y1 + 18))
        d.rectangle([x, y1 + 18 + tile.height, x + tile.width, y1 + 18 + tile.height + 10], fill=G.hex_to_rgb(accent))
        G.text(d, (x, y1 + 18 + tile.height + 32), "%s  ground %s  glow %s" % (name, ground, accent), 14, False, dim, anchor="ls")
        x += tile.width + 24

    # 3. pasted into a real frame
    y2 = y1 + 320
    scale_px = round(FRAME_HERO_PX * height_m / FRAME_HERO_M)
    G.text(d, (40, y2), "3  Pasted into a client frame (docs/media/doors.jpg, 1600x900) left of the greybox hero: %.1f m -> %d px (greybox %.1f u = %d px)"
           % (height_m, scale_px, FRAME_HERO_M, FRAME_HERO_PX), 20, True, cream, anchor="ls")
    f2 = frame.copy()
    small = G.fit_height(fig, scale_px)
    fx, fy = FRAME_FEET
    f2.paste(small, (fx - small.width // 2, fy - small.height), small)
    crop = f2.crop(FRAME_CROP)
    sheet.paste(crop, (40, y2 + 20))
    G.text(d, (40, y2 + 20 + crop.height + 22), "1:1", 14, False, dim, anchor="ls")
    big = up(crop, 2)
    sheet.paste(big, (40 + crop.width + 30, y2 + 20))
    G.text(d, (40 + crop.width + 30, y2 + 20 + big.height + 22), "2x", 14, False, dim, anchor="ls")
    wx = 40 + crop.width + 30 + big.width + 30
    notes = ["Scale: in-game height %.1f m (roster range 2.0-2.3 m)." % height_m,
             "The front T-pose is wider than any gameplay pose;",
             "arms-down idle loses ~40 % of this width.",
             "Judgement and conclusions: brief.md,",
             "section 'Readability'."]
    if notes_opt:
        notes = notes[:1] + notes_opt + notes[3:]
    for i, ln in enumerate(notes):
        G.text(d, (wx, y2 + 44 + i * 22), ln, 15, False, (200, 194, 184), anchor="ls")

    if horde:
        hero_r = float(argv[argv.index("--radius-m") + 1]) if "--radius-m" in argv else 0.55
        horde_panel(sheet, d, key, fig, horde, height_m, y2 + 20 + big.height + 70, "--ring" in argv, hero_r)
    tail = " + mask %s (sha256 %s...)" % (G.rel(mask_path), G.sha256(mask_path)[:16]) if mask_path else ""
    G.text(d, (40, H - 22), "generated by tools/comfy/readability_sheet.py from %s (sha256 %s...)%s" % (G.rel(concept), G.sha256(concept)[:16], tail),
           13, False, (120, 116, 110), anchor="ls")
    sheet.save(out, optimize=True)
    print("[readability] wrote", G.rel(out), "- figure bbox", mask.nonzero()[1].min(), mask.nonzero()[1].max(),
          mask.nonzero()[0].min(), mask.nonzero()[0].max(), "- frame paste", scale_px, "px")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
