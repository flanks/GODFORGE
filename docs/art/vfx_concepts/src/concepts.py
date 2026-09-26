"""GODFORGE VFX concept frames: paint-overs of real in-game captures (docs/art/VFX_STYLE.md).

Each frame paints the effect language of VFX_STYLE.md over a capture in `shots/` (local, untracked
captures of the release build at 1600x900) and writes `docs/art/vfx_concepts/NN_<name>.png`.

usage: python docs/art/vfx_concepts/src/concepts.py [name ...]   (no names = all ten)
needs: Python 3 with numpy, scipy and Pillow.
"""
import math
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
from vfxpaint import Canvas, H_ISO, K_ISO, Ramp, hx, up, norm, rot, star, rand_spikes, crescent  # noqa: E402
import fx  # noqa: E402
from burst import burst  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
SHOTS = os.path.join(ROOT, "shots") + os.sep
OUT = os.environ.get("VFX_OUT", os.path.normpath(os.path.join(HERE, "..")))
FONTS = os.path.join(ROOT, "assets", "fonts") + os.sep
R = {k: Ramp(k) for k in ("kinetic", "flame", "storm", "void", "plague", "radiant", "unmade", "godworks", "enemy")}

CONCEPTS = {}


def concept(name, base, crop, inset=None, inset_at="tl", title="", notes=(), ppm=32.0, strip=None, clean=None,
            inset_S=2.0):
    def deco(fn):
        CONCEPTS[name] = dict(fn=fn, base=base, crop=crop, inset=inset, inset_at=inset_at, title=title, notes=notes,
                              ppm=ppm, strip=strip, clean=clean, inset_S=inset_S)
        return fn

    return deco


def caption(img, title, notes, idx):
    W, H = img.size
    bar = 92
    a = np.zeros((bar, W, 4), np.uint8)
    a[..., 0:3] = (14, 9, 10)
    a[..., 3] = 255
    ov = Image.fromarray(a, "RGBA")
    img = img.convert("RGBA")
    img.alpha_composite(ov, (0, H - bar))
    d = ImageDraw.Draw(img)
    d.line([(0, H - bar), (W, H - bar)], fill=(200, 160, 90, 255), width=1)
    ft = ImageFont.truetype(FONTS + "Cinzel-Variable.ttf", 24)
    try:
        ft.set_variation_by_axes([700])
    except Exception:
        pass
    fn = ImageFont.truetype(FONTS + "AlegreyaSans-Medium.ttf", 16)
    fi = ImageFont.truetype(FONTS + "AlegreyaSans-Bold.ttf", 14)
    d.text((16, H - bar + 11), f"{idx:02d}", font=fi, fill=(200, 160, 90, 255))
    d.text((42, H - bar + 5), title, font=ft, fill=(240, 214, 150, 255))
    d.text((W - 14, H - bar + 11), "GODFORGE · VFX concept · paint-over of an in-game capture", font=fi,
           fill=(150, 130, 110, 255), anchor="ra")
    half = (len(notes) + 1) // 2
    for i, line in enumerate((notes[:half], notes[half:])):
        if line:
            d.text((42, H - bar + 38 + i * 24), "  ·  ".join(line), font=fn, fill=(226, 214, 196, 255))
    return img.convert("RGB")


def add_strip(img, c):
    """Filmstrip under the frame: strip = dict(fn=paint(cv, ppm, f), region=(x0,y0,x1,y1), S=, frames=[...],
    label=)."""
    st = c["strip"]
    tiles = []
    for f in st["frames"]:
        cv = Canvas(SHOTS + c["base"], st["region"], st["S"], clean=c["clean"])
        st["fn"](cv, c["ppm"], f)
        tiles.append((f, cv.finish()))
    tw, th = tiles[0][1].size
    gap = 4
    W = img.width
    head = 30
    strip = Image.new("RGB", (W, th + head + 10), (14, 9, 10))
    d = ImageDraw.Draw(strip)
    fl = ImageFont.truetype(FONTS + "AlegreyaSans-Bold.ttf", 15)
    d.text((16, 7), st["label"], font=fl, fill=(240, 214, 150))
    x = (W - (tw + gap) * len(tiles) + gap) // 2
    for f, t in tiles:
        strip.paste(t, (x, head))
        dd = ImageDraw.Draw(strip)
        dd.text((x + 6, head + 4), f"f{f}", font=fl, fill=(255, 236, 190), stroke_width=2, stroke_fill=(10, 6, 6))
        dd.text((x + tw - 6, head + 4), f"{f / 60 * 1000:.0f} ms", font=fl, fill=(200, 180, 150), stroke_width=2,
                stroke_fill=(10, 6, 6), anchor="ra")
        x += tw + gap
    out = Image.new("RGB", (W, img.height + strip.height), (14, 9, 10))
    out.paste(img, (0, 0))
    out.paste(strip, (0, img.height))
    return out


def render(name, idx):
    c = CONCEPTS[name]
    S = 1280.0 / (c["crop"][2] - c["crop"][0])
    cv = Canvas(SHOTS + c["base"], c["crop"], S, clean=c["clean"])
    texts = c["fn"](cv, c["ppm"]) or []
    img = cv.finish()
    dd = ImageDraw.Draw(img)
    for (x, y, text, px, col) in texts:
        ft = ImageFont.truetype(FONTS + "DejaVuSans.ttf", int(px * S))
        X, Y = (x - c["crop"][0]) * S, (y - c["crop"][1]) * S
        dd.text((X + 1.5 * S, Y + 1.5 * S), text, font=ft, fill=(0, 0, 0), anchor="mm")
        dd.text((X, Y), text, font=ft, fill=col, anchor="mm", stroke_width=1, stroke_fill=(20, 10, 8))
    if c["inset"]:
        ib = c["inset"]
        cv2 = Canvas(SHOTS + c["base"], ib, c["inset_S"], clean=c["clean"])
        c["fn"](cv2, c["ppm"])
        ins = cv2.finish()
        iw, ih = ins.size
        x0, y0, x1, y1 = c["crop"]
        pad = 12
        pos = {"tl": (pad, pad), "tr": (img.width - iw - pad, pad), "bl": (pad, img.height - ih - 104),
               "br": (img.width - iw - pad, img.height - ih - 104)}[c["inset_at"]]
        d = ImageDraw.Draw(img)
        # mark the zoomed region
        d.rectangle([(ib[0] - x0) * S, (ib[1] - y0) * S, (ib[2] - x0) * S, (ib[3] - y0) * S], outline=(200, 160, 90),
                    width=1)
        sh = Image.new("RGB", (iw + 6, ih + 6), (10, 6, 6))
        img.paste(sh, (pos[0] - 3, pos[1] - 3))
        img.paste(ins, pos)
        d.rectangle([pos[0] - 1, pos[1] - 1, pos[0] + iw, pos[1] + ih], outline=(200, 160, 90), width=2)
        f = ImageFont.truetype(FONTS + "AlegreyaSans-Bold.ttf", 15)
        d.text((pos[0] + 8, pos[1] + 6), f"{c['inset_S'] / S:.1f}x detail", font=f, fill=(240, 214, 150), stroke_width=2,
               stroke_fill=(10, 6, 6))
    img = caption(img, c["title"], c["notes"], idx)
    if c["strip"]:
        img = add_strip(img, c)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{idx:02d}_{name}.png")
    img.save(p, optimize=True)
    print(p, os.path.getsize(p) // 1024, "KB")


# =================================================================================================
# 01 Colossus Cannon: shell in flight + layered Kinetic shell impact
# =================================================================================================
def _colossus_strip(cv, ppm, f):
    burst(cv, (1424, 728), 1.6, ppm, f, R["kinetic"], seed=11)


@concept("colossus_shell_impact", "p2fix_after_solo7_01.png", (320, 180, 1600, 900), inset=(1330, 610, 1520, 770),
         inset_at="tl", ppm=40.9,
         strip=dict(fn=_colossus_strip, region=(1348, 646, 1500, 780), S=1.0,
                    frames=[0, 1, 3, 6, 10, 16, 24, 45],
                    label="Anatomy of the impact at 60 fps (1:1 game scale): impact frame f0-1 (white star on ink) -> "
                          "blast f2-5 -> collapse f6-14 -> smoke shrinks and lifts f14-40 -> scorch + dust stay 3 s"), title="Colossus Cannon · Kinetic shell",
         notes=["muzzle (frame 2): brass petal star, ink puff, no ring",
                "in flight: heavy brass shell, hot base, ink smoke trail that thins with age",
                "impact (frame 3): white core in a brass petal star, ink smoke crown lit from inside",
                "shrapnel + 8 chunky sparks · ground dust marks the true 1.6 m splash · scorch 3 s"])
def colossus(cv, ppm):
    rng = np.random.default_rng(7)
    k = R["kinetic"]
    muzzle = (850, 455)
    target = (1424, 718)
    d = norm((target[0] - muzzle[0], target[1] - muzzle[1]))
    # new shot, muzzle frame 2
    fx.smoke(cv, [(muzzle[0] + d[0] * 8 + rng.uniform(-5, 5), muzzle[1] + d[1] * 8 + rng.uniform(-5, 3),
                   rng.uniform(7, 11)) for _ in range(5)], k, (muzzle[0] + d[0] * 34, muzzle[1] + d[1] * 34),
             alpha=0.9, seed=3, rim=fx.mixc(k.light, hx('#FFB060'), 0.4), rough=0.12)
    fx.muzzle_flash(cv, (muzzle[0] + d[0] * 14, muzzle[1] + d[1] * 14), d, 38, R['flame'], rng, petals=5,
                    cone=0.5, gain=1.3)
    # previous shell, 0.38 s out (7.7 m)
    sh = (muzzle[0] + d[0] * 320, muzzle[1] + d[1] * 320)
    nrm = (-d[1], d[0])
    trail = []
    for s_ in np.linspace(8, 270, 60):
        wob = math.sin(s_ * 0.045 + 1.3) * (s_ / 270.0) * 7
        trail.append((sh[0] - d[0] * s_ + nrm[0] * wob, sh[1] - d[1] * s_ + nrm[1] * wob - (s_ / 270.0) ** 2 * 14))
    wid = [5 + 17 * (i / 59) ** 0.8 for i in range(60)]
    fx.ribbon(cv, trail, [w * 1.25 for w in wid], k.ink, alpha=0.7, fade=0.85, erode=0.55, seed=5)
    fx.ribbon(cv, trail, wid, [(0.35, fx.mixc(k.deep, k.light, 0.35)), (1.0, fx.mixc(k.ink, k.deep, 0.55))],
              alpha=0.75, fade=0.95, erode=0.6, seed=6, bloom=0.0)
    fx.ribbon(cv, trail[:10], [5 - 4.5 * i / 9 for i in range(10)], R["flame"].light * 1.6, fade=0.6, bloom=0.8)
    cv.fill(cv.raster(polys=[fx.ellipse_poly(sh, d, 14, 9)]), k.ink)
    cv.fill(cv.raster(polys=[fx.ellipse_poly(sh, d, 11.5, 6.8)]), hx("#B07C3A") * 1.15)
    cv.fill(cv.raster(polys=[fx.ellipse_poly((sh[0] - d[0] * 2, sh[1] - d[1] * 2), d, 2.2, 6.9)]), hx("#4A3018"))
    cv.fill(cv.raster(polys=[fx.ellipse_poly((sh[0] + d[0] * 2 - d[1] * 2.6, sh[1] + d[1] * 2 + d[0] * 2.6), d,
                                             7, 1.4)]), k.hot * 1.5, bloom=0.3)
    fx.glow(cv, (sh[0] - d[0] * 12, sh[1] - d[1] * 12), 9, R["flame"].light, gain=1.5)
    # the shot before: impact frame 3 on the pack
    burst(cv, (1424, 728), 1.6, ppm, 3, k, seed=11)


# =================================================================================================
# 02 Serpent SMG: a hissing needle stream
# =================================================================================================
def needle(cv, head, d, L, ramp, trail_len, gain=1.6, width=2.4, alpha=1.0):
    d = norm(d)
    tail = [(head[0] - d[0] * s_, head[1] - d[1] * s_) for s_ in np.linspace(0, trail_len, 12)]
    fx.ribbon(cv, tail, [width * 2.2 * (1 - i / 11) ** 0.7 + 0.3 for i in range(12)], ramp.ink, alpha=0.55 * alpha,
              fade=0.9)
    fx.ribbon(cv, tail, [width * 1.1 * (1 - i / 11) ** 0.9 + 0.2 for i in range(12)],
              [(0.35, ramp.light * gain), (1.0, ramp.body * gain * 0.9)], alpha=alpha, fade=0.95, bloom=0.5)
    cv.fill(cv.raster(polys=[fx.kite(head, d, L * 0.55, width * 1.2, back=1.2)]), ramp.ink, alpha=0.9 * alpha)
    cv.fill(cv.raster(polys=[fx.kite(head, d, L * 0.5, width * 0.6, back=1.1)]), ramp.hot * gain * 1.3,
            alpha=alpha, bloom=0.9)


def tick_spark(cv, p, d_in, size, ramp, rng, gain=1.6):
    """Small-hit punctuation: a 4-point ink-backed star plus 3 sparks kicked back toward the shooter."""
    fx.impact_star(cv, p, size, ramp, rng, n=4, gain=gain, core_gain=2.2, ink_scale=1.4, hw=0.2,
                   rotation=math.atan2(d_in[1], d_in[0]) + rng.uniform(-0.3, 0.3))
    back = (-d_in[0], -d_in[1])
    fx.sparks(cv, p, rng, 3, size * 0.5, size * 1.9, ramp, width=2.0, dir=back, spread=0.9, gain=1.8, ky=1.0)


@concept("serpent_smg_needle_stream", "p2crit_s7solo_00.png", (320, 120, 1600, 840), inset=(1290, 300, 1470, 440),
         inset_at="bl", ppm=40.9, title="Serpent SMG · Kinetic needle stream",
         notes=["11 shots/s reads as ONE stitched line: needle = hot core in an ink sliver, 1.2 m brass streak",
                "muzzle: 3-petal flicker, alternating 15 deg each shot; brass casings spin out of `eject`",
                "hits: 4-point ink-backed tick sparks kicked back at the shooter, aggregated per target",
                "no rings, no spheres; the stream converges on the aimed target"])
def serpent(cv, ppm):
    rng = np.random.default_rng(3)
    k = R["kinetic"]
    muzzle = (872, 447)
    targets = [(1386, 356), (1402, 380), (1392, 372), (1410, 350)]
    base_d = norm((targets[0][0] - muzzle[0], targets[0][1] - muzzle[1]))
    dist = math.hypot(targets[0][0] - muzzle[0], targets[0][1] - muzzle[1])
    # the wake: a faint heat line under the whole stream (own weapon, Full tier only)
    wake = [(muzzle[0] + base_d[0] * s_, muzzle[1] + base_d[1] * s_) for s_ in np.linspace(dist, 20, 30)]
    fx.ribbon(cv, wake, [7 * (0.4 + 0.6 * i / 29) for i in range(30)], k.body * 0.9, alpha=0.18, fade=0.0,
              erode=0.35, seed=4, bloom=0.2)
    # casings: brass slivers flicked up and back out of the eject port
    for i, (dx, dy, ang) in enumerate([(-4, -24, 0.4), (-18, -38, 1.3), (-33, -44, 2.2), (-48, -40, 2.9)]):
        p = (muzzle[0] - 16 + dx, muzzle[1] - 4 + dy)
        dd = (math.cos(ang), math.sin(ang))
        cv.fill(cv.raster(polys=[fx.kite(p, dd, 6.5, 3.4, back=1.0)]), k.ink, alpha=0.85)
        cv.fill(cv.raster(polys=[fx.kite(p, dd, 5.2, 2.2, back=1.0)]), hx("#D8A450") * (1.5 - i * 0.22), bloom=0.2)
    # needles in flight, newest nearest the muzzle
    for i, s_ in enumerate(np.arange(46, dist - 10, 97.0)):
        ang = math.radians(rng.uniform(-3.0, 3.0))
        d = rot(base_d, ang)
        head = (muzzle[0] + d[0] * s_, muzzle[1] + d[1] * s_)
        needle(cv, head, d, 26, k, min(74, s_ - 12), gain=1.6, width=3.6)
    fx.muzzle_flash(cv, (muzzle[0] + base_d[0] * 8, muzzle[1] + base_d[1] * 8), rot(base_d, 0.26), 32, k, rng,
                    petals=3, cone=0.38, gain=1.5, back=False)
    # hits on the front of the pack: tick stars + chips of the target (Unmade: obsidian and teal)
    u = R["unmade"]
    for p, sz in ((targets[0], 22), (targets[1], 13), (targets[3], 11)):
        tick_spark(cv, p, base_d, sz, k, rng, gain=1.7)
        fx.shards(cv, p, rng, 3, sz * 0.6, sz * 1.5, sz * 0.4, u, ky=1.0, dark=u.ink, edge=u.body, gain=1.4)
    fx.glow(cv, targets[0], 20, k.light, gain=0.4)


# =================================================================================================
# 03 Thundercoil Launcher: coiled orb + chain arcs (Storm)
# =================================================================================================
def storm_orb(cv, c, d, r, ramp, rng, trail=90):
    d = norm(d)
    n = (-d[1], d[0])
    # the coil: a helix ribbon wrapped round the flight path, fading behind the orb
    for phase, alpha in ((0.0, 1.0), (math.pi, 0.55)):
        pts = []
        for s_ in np.linspace(0, trail, 40):
            w = r * 0.9 * (1 - s_ / trail * 0.4) * math.sin(s_ * 0.16 + phase)
            pts.append((c[0] - d[0] * s_ + n[0] * w, c[1] - d[1] * s_ + n[1] * w))
        fx.ribbon(cv, pts, [3.2 * (1 - i / 39) + 0.4 for i in range(40)], ramp.ink, alpha=0.5 * alpha, fade=0.9)
        fx.ribbon(cv, pts, [1.8 * (1 - i / 39) + 0.3 for i in range(40)], ramp.body * 1.8, alpha=alpha, fade=0.95,
                  bloom=0.7)
    # body: ink core, cyan rim crescent, white pin
    cv.fill(cv.raster(dots=[(c[0], c[1], r * 1.25)]), ramp.ink, alpha=0.95)
    cv.fill(cv.raster(dots=[(c[0], c[1], r)]), ramp.deep * 1.2)
    rim = crescent(cv, c, r * 1.02, math.atan2(d[1], d[0]) - 2.4, math.atan2(d[1], d[0]) + 2.4, r * 0.45, ky=1.0,
                   seed=5, erode=0.0, peak=0.5, inner_rag=0.0)
    if rim:
        cv.over(rim[0], rim[1], ramp.body * 1.8, bloom=0.8)
    cv.fill(cv.raster(dots=[(c[0] + d[0] * r * 0.25, c[1] + d[1] * r * 0.25, r * 0.32)]), ramp.hot * 2.4, bloom=1.0)
    # crackle: 3 short arcs licking off the surface
    for i in range(3):
        a = rng.uniform(0, 6.28)
        p0 = (c[0] + math.cos(a) * r, c[1] + math.sin(a) * r)
        p1 = (c[0] + math.cos(a + 0.5) * r * 2.3, c[1] + math.sin(a + 0.5) * r * 2.3)
        fx.bolt(cv, p0, p1, rng, ramp, width=1.3, branches=0, jag=0.35, gain=1.6, depth=3, ink_w=2.4)


def lichtenberg(cv, c, R, rng, ramp, n=7, ky=K_ISO):
    lines = []
    for i in range(n):
        a = 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
        p1 = (c[0] + math.cos(a) * R * rng.uniform(0.6, 1.1), c[1] + math.sin(a) * R * rng.uniform(0.6, 1.1) * ky)
        pts = fx.bolt_points(c, p1, rng, jag=0.3, depth=4)
        lines.append((pts, 2.0))
        j = len(pts) // 2
        q = (pts[j][0] + math.cos(a + 0.8) * R * 0.35, pts[j][1] + math.sin(a + 0.8) * R * 0.35 * ky)
        lines.append((fx.bolt_points(pts[j], q, rng, jag=0.3, depth=3), 1.2))
    r = cv.raster(lines=lines)
    if r:
        cv.darken(r[0], r[1], 0.75)
    r = cv.raster(lines=[(p, w * 0.4) for p, w in lines])
    if r:
        cv.over(r[0], r[1] * 0.7, ramp.body * 1.3, bloom=0.3)


def storm_impact(cv, c, ppm, rng, ramp, splash_m=1.0):
    Rx = splash_m * ppm
    core = up(c, 0.5, ppm)
    fx.light_spill(cv, c, Rx * 3.2, ramp.light, gain=1.4)
    lichtenberg(cv, c, Rx * 1.1, rng, ramp)
    # storm star: many thin, sharp spikes (angular, never round)
    sp = rand_spikes(rng, 10, Rx * 1.15, hw=0.12, jitter=0.45)
    cv.fill(star(cv, core, [(a + 0.06, L * 1.3, h * 1.5) for a, L, h in sp], Rx * 0.34), ramp.ink, alpha=0.95)
    r = star(cv, core, sp, Rx * 0.3, p=1.1)
    if r:
        sl, cov, cr = r
        kk = cr[..., None]
        cv.over(sl, cov, np.where(kk > 0.5, ramp.hot * 2.4, np.where(kk > 0.25, ramp.light * 1.6, ramp.body * 1.5)),
                bloom=0.6)
    for i in range(5):
        a = rng.uniform(0, 6.28)
        fx.bolt(cv, core, (core[0] + math.cos(a) * Rx * 1.3, core[1] + math.sin(a) * Rx * 1.1), rng, ramp,
                width=1.6, branches=1, jag=0.3, gain=1.8, depth=4)


@concept("thundercoil_orb_chain", "m1/m1_after_verdant_00.png", (430, 140, 1390, 680), inset=(598, 196, 858, 316),
         inset_at="tr", inset_S=1.8, ppm=32.0, title="Thundercoil Launcher · Storm orb + chain arcs",
         notes=["orb: ink core, cyan rim crescent, white pin, 3 crackles; a helix coil trail (the Thundercoil verb)",
                "impact: thin angular star + 5 forked bolts + Lichtenberg scorch; never a round flash",
                "chain: hops 1-2 frames apart, ink-sheathed bolt with a white core, a small star per node",
                "bolts strobe: 2 alternating shapes at 30 Hz, then vanish; the scorch stays 2 s"])
def thundercoil(cv, ppm):
    rng = np.random.default_rng(12)
    st = R["storm"]
    muzzle = (850, 382)
    hit = (630, 252)
    d = norm((hit[0] - muzzle[0], hit[1] - muzzle[1]))
    fx.muzzle_flash(cv, (muzzle[0] + d[0] * 6, muzzle[1] + d[1] * 6), d, 20, st, rng, petals=4, cone=0.7, gain=1.4)
    storm_orb(cv, (muzzle[0] + d[0] * 70, muzzle[1] + d[1] * 70), d, 9.5, st, rng, trail=62)
    storm_impact(cv, hit, ppm, rng, st)
    chain = [up(hit, 0.6, ppm), up((718, 266), 0.6, ppm), up((741, 236), 0.6, ppm), up((793, 250), 0.6, ppm),
             up((838, 266), 0.6, ppm)]
    for i, (a, b) in enumerate(zip(chain[:-1], chain[1:])):
        # the strobe: a dim ghost of the previous frame's shape under the current bolt
        fx.bolt(cv, a, b, np.random.default_rng(100 + i), st, width=1.4, branches=0, jag=0.3, gain=0.9, depth=4,
                ink=False)
        fx.bolt(cv, a, b, rng, st, width=3.0, branches=1, jag=0.22, gain=1.9, depth=5)
        fx.impact_star(cv, b, 10, st, rng, n=6, gain=1.5, core_gain=2.3, ink_scale=1.4, hw=0.14)
        fx.light_spill(cv, (b[0], b[1] + 12), 40, st.light, gain=0.8)


# =================================================================================================
# 04 Wraith Bow: charge -> loose -> a hex-bolt that passes through the living (Void, pierce)
# =================================================================================================
def void_arrow(cv, head, d, ramp, rng, L=66, trail=150, width=11):
    d = norm(d)
    n = (-d[1], d[0])
    tail = [(head[0] - d[0] * s_, head[1] - d[1] * s_) for s_ in np.linspace(L * 0.5, L * 0.5 + trail, 40)]
    # ghost trail: a wide ink smear with bright violet edges and a dry-brush tail (void = dark core, bright rim)
    fx.ribbon(cv, tail, [width * 3.8 * (1 - i / 39) ** 0.55 + 0.6 for i in range(40)], ramp.body * 1.5, alpha=0.95,
              fade=0.75, erode=0.5, seed=31, bloom=0.6)
    fx.ribbon(cv, tail, [width * 3.0 * (1 - i / 39) ** 0.6 + 0.3 for i in range(40)], ramp.ink, alpha=0.97,
              fade=0.55, erode=0.45, seed=31)
    fx.ribbon(cv, tail[:14], [width * 0.5 * (1 - i / 13) + 0.2 for i in range(14)], ramp.light * 1.6, alpha=0.9,
              fade=0.9, bloom=0.6)
    # hex motes peeling off the trail
    pts = []
    for i in range(7):
        s_ = rng.uniform(0.15, 0.9) * trail
        side = 1 if i % 2 else -1
        off = width * rng.uniform(1.6, 3.0) * side
        pts.append((head[0] - d[0] * (L * 0.5 + s_) + n[0] * off, head[1] - d[1] * (L * 0.5 + s_) + n[1] * off))
    fx.diamond_glints(cv, pts, 4.5, ramp.light, gain=1.8)
    # two wisps peeling off the fletching
    for sg in (1, -1):
        pts = [(tail[0][0] - d[0] * s_ + n[0] * sg * (s_ * 0.18 + math.sin(s_ * 0.08) * 4),
                tail[0][1] - d[1] * s_ + n[1] * sg * (s_ * 0.18 + math.sin(s_ * 0.08) * 4)) for s_ in np.linspace(0, 60, 16)]
        fx.ribbon(cv, pts, [3.0 * (1 - i / 15) + 0.3 for i in range(16)], ramp.light * 1.4, fade=0.9, bloom=0.6)
    # spectral head: ink body, violet rim, white tip
    cv.fill(cv.raster(polys=[fx.kite(head, d, L * 0.62, width * 1.9, back=0.75)]), ramp.body * 1.8, bloom=0.7)
    cv.fill(cv.raster(polys=[fx.kite((head[0] - d[0] * 4, head[1] - d[1] * 4), d, L * 0.5, width * 1.35, back=0.7)]),
            ramp.ink)
    cv.fill(cv.raster(polys=[fx.kite((head[0] + d[0] * 6, head[1] + d[1] * 6), d, L * 0.24, width * 0.5, back=0.7)]),
            ramp.hot * 2.4, bloom=1.0)


def pierce_wound(cv, p, d, ramp, rng, size=20, age=0):
    """Exit wound: an ink slash through the target along the flight line, violet shards out the far side."""
    d = norm(d)
    a = math.atan2(d[1], d[0])
    k = max(0.25, 1 - age / 10)
    r = crescent(cv, (p[0] - d[1] * size * 1.8, p[1] + d[0] * size * 1.8), size * 1.8, a - 0.55 + math.pi / 2,
                 a + 0.55 + math.pi / 2, size * 0.5 * k, ky=1.0, seed=int(p[0]), erode=0.5)
    if r:
        cv.over(r[0], r[1], ramp.ink, 0)
        cv.over(r[0], r[2], ramp.body * 1.8, bloom=0.7)
    fx.sparks(cv, (p[0] + d[0] * size * 0.4, p[1] + d[1] * size * 0.4), rng, 5, size * 0.3, size * 1.6 * (1 + age / 6),
              ramp, width=3.0, dir=d, spread=0.55, gain=1.8, hot=ramp.light, cool=ramp.body)


def charge_gather(cv, c, ppm, frac, ramp, rng):
    """Charge anticipation: motes spiral in, a broken ring tightens, the core fills."""
    R0 = 1.3 * ppm
    rr = R0 * (1 - 0.72 * frac)
    fx.ring_accent(cv, (c[0], c[1] + 6), rr, 3.2, ramp.light, gain=1.6, gaps=0.5, seed=4, alpha=0.9)
    fx.ring_accent(cv, (c[0], c[1] + 6), rr * 1.08, 5.5, ramp.ink, gain=1.0, gaps=0.5, seed=4, alpha=0.5)
    pts = []
    for i in range(9):
        a = i * 2.4 + frac * 5.0
        r_ = R0 * (1.25 - frac) * (0.55 + 0.45 * ((i * 37) % 10) / 10)
        pts.append((c[0] + math.cos(a) * r_, c[1] + math.sin(a) * r_ * 0.8))
        tail = [(c[0] + math.cos(a - t) * r_ * (1 + t * 0.5), c[1] + math.sin(a - t) * r_ * 0.8 * (1 + t * 0.5))
                for t in np.linspace(0, 0.7, 8)]
        fx.ribbon(cv, tail, [2.6 * (1 - j / 7) + 0.3 for j in range(8)], ramp.body * 1.5, fade=0.8, bloom=0.5)
    fx.motes(cv, pts, 2.2, ramp.light, gain=1.8, ink=ramp.ink)
    cv.fill(cv.raster(dots=[(c[0], c[1], 5 + 6 * frac)]), ramp.ink, alpha=0.9)
    cv.fill(cv.raster(dots=[(c[0], c[1], 3 + 4 * frac)]), ramp.body * 1.8, bloom=0.8)
    cv.fill(cv.raster(dots=[(c[0], c[1], 1.5 + 2 * frac)]), ramp.hot * 2.2, bloom=1.0)


@concept("wraith_bow_charged_arrow", "p2crit_lair3_02.png", (300, 170, 1580, 890), inset=(1100, 540, 1300, 670),
         inset_at="tr", ppm=40.9, clean=[(933, 513, 1023, 513, 23), (962, 482, 1052, 482, 23), (980, 446, 1070, 446, 23)],
         title="Wraith Bow · Void charged hex-bolt",
         notes=["charge (anticipation): 9 motes spiral in, a broken ring tightens 1.3 m -> 0.35 m, the core fills",
                "full charge: 1-frame 4-point glint + the ring flashes white (the release window)",
                "arrow: ink shaft with a violet edge and white tip; ghost trail = dark core, bright violet rims",
                "pierce: an ink slash through each body + violet shards out the far side, 6 frames"])
def wraith_bow(cv, ppm):
    rng = np.random.default_rng(21)
    v = R["void"]
    bow = (846, 468)
    e1, e2 = (1150, 590), (1222, 618)
    d = norm((e1[0] - bow[0], e1[1] - bow[1]))
    head = (bow[0] + d[0] * 560, bow[1] + d[1] * 560)
    fx.light_spill(cv, (head[0] - d[0] * 40, head[1] - d[1] * 40 + 20), 90, v.light, gain=0.9)
    void_arrow(cv, head, d, v, rng, trail=260)
    pierce_wound(cv, e1, d, v, rng, size=24, age=4)
    pierce_wound(cv, e2, d, v, rng, size=24, age=1)
    charge_gather(cv, bow, ppm, 0.55, v, rng)


# =================================================================================================
# 05 Anvil Gauntlets (Brax): jab smear -> shotgun-fist finisher, around a live bomber telegraph
# =================================================================================================
@concept("gauntlet_punch_combo", "vfx_base_brax_07.png", (400, 200, 1360, 740), inset=(760, 400, 960, 620),
         inset_at="tr", inset_S=1.9, ppm=32.0, title="Anvil Gauntlets · punch combo (Brax)",
         notes=["jab / hook: ink crescent smears in the fist plane, white leading edge, dry-brush tail (8 frames)",
                "finisher (every 3rd): shotgun-fist cone = 5 speed streaks + a flat shock front at the 2.8 m reach",
                "contact: big ink-backed impact star, the target knocked back with ink drag lines; Brax's Burn = ember licks",
                "the Kindlejack's red-white telegraph stays on top: player ink never covers danger"])
def gauntlets(cv, ppm):
    rng = np.random.default_rng(5)
    k = R["kinetic"]
    fl = R["flame"]
    brax = (846, 456)
    tgt = (866, 548)
    # previous strike: the hook, 8 frames old, breaking into dry-brush streaks
    fx.smear(cv, brax, 64, math.radians(215), math.radians(118), 22, k, seed=3, erode=1.1, gain=1.15, rim_gain=1.4,
             ink_alpha=0.75)
    # finisher, frame 2: a full-reach crescent sweeping across the front, the shock front on its outer edge
    fx.light_spill(cv, (brax[0] + 40, brax[1] + 60), 150, hx("#FFD9A0"), gain=0.9)
    fx.smear(cv, (brax[0] + 6, brax[1] + 2), 104, math.radians(128), math.radians(-18), 42, k, seed=8, erode=0.45,
             gain=1.5, rim_gain=2.5, ink_scale=1.6)
    aim = math.radians(80)
    polys_i, polys_b = [], []
    for i in range(3):
        a = aim + math.radians(-18 + 18 * i) + rng.uniform(-0.05, 0.05)
        v = (math.cos(a), math.sin(a) * K_ISO)
        p0 = (brax[0] + v[0] * 30, brax[1] + 8 + v[1] * 30)
        p1 = (brax[0] + v[0] * 70, brax[1] + 8 + v[1] * 70)
        polys_i.append(fx.streak_poly(p1, p0, 6.0, 0.0))
        polys_b.append(fx.streak_poly(p1, p0, 2.6, 0.0))
    cv.fill(cv.raster(polys=polys_i), k.ink, alpha=0.75)
    cv.fill(cv.raster(polys=polys_b), k.light * 1.7, bloom=0.6)
    # contact on the cinderling: impact star, knockback drag lines, Burn licks
    fx.light_spill(cv, tgt, 90, hx("#FFD9A0"), gain=1.0)
    drag = []
    for i in range(4):
        x0 = tgt[0] - 14 + i * 9
        drag.append(fx.streak_poly((x0 + 2, tgt[1] + 36 + i % 2 * 6), (x0, tgt[1] + 10), 4.5, 0.0))
    cv.fill(cv.raster(polys=drag), k.ink, alpha=0.8)
    fx.flames(cv, [(tgt[0] - 11, tgt[1] + 4), (tgt[0] + 10, tgt[1] + 8)], 22, 9, fl, rng, gain=1.4)
    fx.impact_star(cv, up(tgt, 0.45, ppm), 32, k, rng, n=6, gain=1.35, core_gain=2.4, ink_scale=1.35, hw=0.24)
    fx.sparks(cv, up(tgt, 0.45, ppm), rng, 7, 18, 58, fl, width=3.6, dir=(0.1, 1.0), spread=0.8, gain=1.6,
              hot=fl.light, cool=fl.body)
    fx.ground_dust(cv, (brax[0], brax[1] + 18), 28, rng, 7, 4, 8, hx("#2B1E15"), hx("#6A5040"), brax, alpha=0.7)
    # danger stays on top
    cv.restore_danger((810, 523), 44, 40)


# =================================================================================================
# 06 Sunspike Shotgun: a fistful of sunlight (Radiant spread)
# =================================================================================================
def cross_glint(cv, p, size, ramp, rng, rays=8, gain=1.8):
    """Radiant punctuation: an ink-backed 4-point cross + thin straight rays (law, not fire)."""
    sp = [(a, size * (1.0 if i % 2 == 0 else 0.45), 0.13) for i, a in enumerate(np.linspace(0, 2 * math.pi, 8, endpoint=False) + math.pi / 4)]
    cv.fill(star(cv, p, [(a, L * 1.35, h * 1.5) for a, L, h in sp], size * 0.2), ramp.ink, alpha=0.9)
    r = star(cv, p, sp, size * 0.16, p=1.0)
    if r:
        sl, cov, cr = r
        cv.over(sl, cov, np.where(cr[..., None] > 0.35, ramp.hot * 2.4, ramp.body * gain), bloom=0.8)
    polys = []
    for i in range(rays):
        a = rng.uniform(0, 6.28)
        v = (math.cos(a), math.sin(a))
        polys.append(fx.streak_poly((p[0] + v[0] * size * rng.uniform(1.1, 1.8), p[1] + v[1] * size * rng.uniform(1.1, 1.8)),
                                    (p[0] + v[0] * size * 0.5, p[1] + v[1] * size * 0.5), 1.6, 0.0, cap=False))
    cv.fill(cv.raster(polys=polys), ramp.light * 1.6, bloom=0.6)


@concept("sunspike_spread_burst", "m1/m1_after_spire_00.png", (440, 150, 1400, 690), inset=(800, 400, 1000, 580),
         inset_at="tr", inset_S=1.9, ppm=32.0, clean=[(928, 568, 1010, 575, 18)],
         title="Sunspike Shotgun · Radiant spread burst",
         notes=["muzzle (THE FAN): ink-backed sunburst sector, 7 straight rays on the pellet lines, 4 frames",
                "pellets: gold diamonds with short straight streaks; the fan shape reads as one blast",
                "hits: 4-point cross glints + thin straight rays, never round; Radiant sparkles drift up",
                "Radiant = geometry and straight lines; Flame = curling tongues. Same warm family, opposite shapes"])
def sunspike(cv, ppm):
    rng = np.random.default_rng(8)
    ra = R["radiant"]
    muzzle = (838, 452)
    aim = math.atan2(532 - 452, 945 - 838)
    fx.light_spill(cv, (muzzle[0] + 50, muzzle[1] + 40), 130, ra.light, gain=0.9)
    # the sunburst fan (frame 3): ink fan, banded gold sector, 7 rays, a pointed white core
    spread = math.radians(24)

    def fan(radius, wob, n=16, sc=1.0):
        return [muzzle] + [(muzzle[0] + math.cos(aim + t) * (radius + wob * math.cos(t * 11)),
                            muzzle[1] + math.sin(aim + t) * (radius + wob * math.cos(t * 11)))
                           for t in np.linspace(-spread * sc, spread * sc, n)]

    cv.fill(cv.raster(polys=[fan(112, 6, sc=1.3)]), ra.ink, alpha=0.8)
    # sunburst: alternating wedges (law geometry), ink-cut between them
    edges = np.linspace(-spread * 1.15, spread * 1.15, 10)
    for i, (t0, t1) in enumerate(zip(edges[:-1], edges[1:])):
        rad = 98 if i % 2 == 0 else 74
        g = 0.012
        wedge = [(muzzle[0] + math.cos(aim + t0 + g) * 8, muzzle[1] + math.sin(aim + t0 + g) * 8),
                 (muzzle[0] + math.cos(aim + t0 + g) * rad, muzzle[1] + math.sin(aim + t0 + g) * rad),
                 (muzzle[0] + math.cos(aim + (t0 + t1) / 2) * (rad + 12), muzzle[1] + math.sin(aim + (t0 + t1) / 2) * (rad + 12)),
                 (muzzle[0] + math.cos(aim + t1 - g) * rad, muzzle[1] + math.sin(aim + t1 - g) * rad),
                 (muzzle[0] + math.cos(aim + t1 - g) * 8, muzzle[1] + math.sin(aim + t1 - g) * 8)]
        cv.fill(cv.raster(polys=[wedge]), (ra.body * 1.2 if i % 2 == 0 else ra.deep * 1.4), bloom=0.3)
    cv.fill(cv.raster(polys=[fan(40, 4, sc=0.9)]), ra.light * 1.3, bloom=0.5)
    cv.fill(star(cv, muzzle, [(aim, 26, 0.2), (aim + 2.3, 9, 0.3), (aim - 2.3, 9, 0.3), (aim + math.pi, 7, 0.3)],
                 3.5), ra.hot * 1.9, bloom=0.8)
    # pellets at ~2.5-4 m
    for i, t in enumerate(np.linspace(-spread, spread, 7)):
        a = aim + t + rng.uniform(-0.03, 0.03)
        dist = rng.uniform(96, 124) if i not in (3, 4) else 128
        d = (math.cos(a), math.sin(a))
        head = (muzzle[0] + d[0] * dist, muzzle[1] + d[1] * dist)
        tail = [(head[0] - d[0] * s_, head[1] - d[1] * s_) for s_ in np.linspace(0, 34, 10)]
        fx.ribbon(cv, tail, [4.2 * (1 - j / 9) + 0.3 for j in range(10)], ra.body * 1.5, fade=0.9, bloom=0.5)
        cv.fill(cv.raster(polys=[fx.kite(head, d, 7, 4.2, back=1.0)]), ra.ink, alpha=0.8)
        cv.fill(cv.raster(polys=[fx.kite(head, d, 5.2, 2.6, back=1.0)]), ra.hot * 2.2, bloom=0.9)
    # hits on the pair ahead
    for p, sz in (((938, 518), 22), ((958, 534), 17)):
        cross_glint(cv, p, sz, ra, rng)
    fx.diamond_glints(cv, [(925, 492), (968, 505), (950, 480), (985, 522)], 4.0, ra.light, gain=1.8)


# =================================================================================================
# 07 Firestorm synergy (Flame + Storm): a burning thunderhead squats on the target
# =================================================================================================
@concept("firestorm_synergy", "vfx_base_brax_02.png", (60, 280, 940, 775), inset=(176, 430, 370, 590), inset_at="tr",
         inset_S=2.6, ppm=32.0,
         title="Firestorm (Flame + Storm) · synergy set-piece",
         notes=["trigger: orange + cyan spirals wind into the target and snap (6 frames); the field holds 3 s",
                "rim: a dense ring of low flame tongues; a thin broken GOLD hem marks the true 3 m player zone",
                "storm from above: ink smoke arms spiral in, fire-lit on their leading edge, a cyan eye",
                "a bolt every 0.3 s from the eye into a body inside (strike 2 frames + ground star); embers climb in"])
def firestorm(cv, ppm):
    rng = np.random.default_rng(31)
    fl, st = R["flame"], R["storm"]
    c = (272, 540)
    Rx = 3.0 * ppm
    # ground: warm light from the fires, dark storm-shadow, the gold hem
    fx.light_spill(cv, c, Rx * 1.7, fl.light, gain=0.8)
    g = fx.ellipse_field(cv, c, Rx * 0.8, Rx * 0.8 * K_ISO, ss=1)
    if g:
        sl, X, Y, d, ss = g
        cv.darken(sl, np.clip(1 - d, 0, 1) ** 0.7 * 0.55, 1.0)
    fx.ring_accent(cv, c, Rx, 1.8, hx("#FFC940"), gain=1.0, gaps=0.55, seed=7, alpha=0.35)
    # a dense low ring of flame tongues on the rim, leaning with the swirl (back half first)
    bases, leans = [], []
    for i in range(34):
        t = 2 * math.pi * i / 34 + rng.uniform(-0.05, 0.05)
        k = rng.uniform(0.84, 1.0)
        bases.append((c[0] + math.cos(t) * Rx * k, c[1] + math.sin(t) * Rx * K_ISO * k))
        leans.append(-math.sin(t) * 0.9)
    back = [(b, l_) for b, l_ in zip(bases, leans) if b[1] < c[1]]
    front = [(b, l_) for b, l_ in zip(bases, leans) if b[1] >= c[1]]
    fx.flames(cv, [b for b, _ in back], 17, 10, fl, rng, gain=1.2, leans=[l_ for _, l_ in back], core_k=0.25)
    # the storm seen from above: smoke arms spiralling in, fire-lit only at their heads
    eye = up(c, 1.6, ppm)
    smoke_dark = fx.mixc(fl.ink, hx("#2A1E2A"), 0.6)
    smoke_mid = hx("#4A3440")
    arms = [(0.95, 0.3, 1.5, 0.36), (0.8, 1.9, 1.3, 0.3), (0.92, 3.3, 1.6, 0.34), (0.75, 4.7, 1.2, 0.28),
            (0.6, 0.9, 1.4, 0.26), (0.55, 3.9, 1.3, 0.24)]
    for i, (rf, a0, span, wf) in enumerate(arms):
        r = crescent(cv, eye, Rx * rf, a0, a0 + span, Rx * wf, ky=K_ISO, seed=40 + i, erode=0.75, peak=0.62,
                     rim=0.3)
        if r:
            sl, cov, rimm, head = r
            cv.over(sl, cov * 0.92, smoke_dark)
            cv.over(sl, (cov - rimm) * np.clip(head * 1.6, 0, 1) * 0.8, smoke_mid)
            cv.over(sl, rimm * np.clip(head * 1.8, 0, 1), fl.body * 1.4, bloom=0.4)
    for i in range(3):
        a0 = i * 2.1 + 1.0
        r = crescent(cv, eye, Rx * 0.38, a0, a0 + 1.6, Rx * 0.16, ky=K_ISO, seed=50 + i, erode=0.6, peak=0.6, rim=0.3)
        if r:
            sl, cov, rimm, head = r
            cv.over(sl, cov * 0.9, st.ink)
            cv.over(sl, rimm * np.clip(head * 1.8, 0, 1), st.body * 1.4, bloom=0.5)
    # the eye: cyan light inside the storm
    fx.glow(cv, eye, 34, st.body, gain=0.8, ky=K_ISO)
    # embers climbing into the storm
    em = [(c[0] + rng.uniform(-80, 80), c[1] - rng.uniform(-10, 70)) for _ in range(24)]
    fx.motes(cv, em, 1.5, fl.light, gain=1.8)
    # strikes: a bolt from the eye into a body (frame 1) and one fading (frame 3)
    for i, (tgt, wd, gn) in enumerate((((250, 502), 3.4, 2.1), ((304, 562), 2.0, 1.1))):
        top = (eye[0] + rng.uniform(-10, 10), eye[1] - 4)
        fx.bolt(cv, top, tgt, np.random.default_rng(60 + i), st, width=wd, branches=2, jag=0.24, gain=gn, depth=5)
        fx.impact_star(cv, tgt, 20 if i == 0 else 12, st, rng, n=7, gain=1.5, core_gain=2.3, ink_scale=1.35, hw=0.14)
        fx.light_spill(cv, (tgt[0], tgt[1] + 6), 70, st.light, gain=1.0 if i == 0 else 0.5)
    fx.flames(cv, [b for b, _ in front], 19, 11, fl, rng, gain=1.25, leans=[l_ for _, l_ in front], core_k=0.25)


# =================================================================================================
# 08 Mountainfall (Valdris ultimate): anvil-avatar ground pound + boulder shots
# =================================================================================================
def ground_pound(cv, c, Rm, ppm, f, rng, k, fl):
    Rx = Rm * ppm
    t = f / 60.0
    front = Rx * (0.25 + 0.75 * (1 - (1 - min(1.0, f / 9.0)) ** 3))
    fx.light_spill(cv, c, Rx * 1.4, hx("#FFC070"), gain=1.2 * max(0.2, 1 - f / 14))
    # a crater at the feet and molten gashes radiating to the true radius (they stay 1.5 s)
    g = fx.ellipse_field(cv, c, Rx * 0.26, Rx * 0.26 * K_ISO, ss=2)
    if g:
        sl, X, Y, d, ss = g
        cv.darken(sl, cv.down((d < 1.0).astype(np.float32) * np.clip((1 - d) * 3, 0, 1), ss), 0.75)
    dark, core = [], []
    for i in range(10):
        a = 2 * math.pi * i / 10 + rng.uniform(-0.22, 0.22)
        L = Rx * rng.uniform(0.7, 1.02)
        p0 = (c[0] + math.cos(a) * Rx * 0.18, c[1] + math.sin(a) * Rx * 0.18 * K_ISO)
        p1 = (c[0] + math.cos(a) * L, c[1] + math.sin(a) * L * K_ISO)
        pts = fx.bolt_points(p0, p1, rng, jag=0.09, depth=3)
        n = len(pts)
        dark.append(fx.tapered_path(pts, [17 * (1 - j / (n - 1)) ** 0.8 + 1.2 for j in range(n)]))
        core.append(fx.tapered_path(pts, [6.5 * (1 - j / (n - 1)) ** 0.9 + 0.4 for j in range(n)]))
    cv.fill(cv.raster(polys=dark), hx("#140C0A"), alpha=0.92)
    cv.fill(cv.raster(polys=core), fl.body * 1.5, bloom=0.55)
    fx.glow(cv, c, Rx * 0.3, fl.body, gain=0.9, ky=K_ISO)
    # the dust wall riding the shock front, lit gold from the centre
    fx.ground_dust(cv, c, front, rng, 26, Rx * 0.07, Rx * 0.14, hx("#4A3628"), hx("#D8A870"), up(c, 1.0, ppm), alpha=0.85,
                   seed=77)
    if f <= 4:
        fx.ring_accent(cv, c, front * 1.04, 3.6, hx("#FFC870"), gain=1.3, gaps=0.52, seed=11, alpha=0.85)
    # rock debris thrown up and out
    fx.shards(cv, c, rng, 12, front * 0.5, front * 1.05, Rx * 0.12, k, lift=Rx * 0.45, dark=hx("#2A211C"),
              edge=hx("#C8A070"), gain=1.0)
    # impact core at the feet (frame 5: collapsing star)
    fx.impact_star(cv, up(c, 0.3, ppm), Rx * 0.5 * max(0.3, 1 - f / 10), fl, rng, n=9, gain=1.3, core_gain=2.2,
                   ink_scale=1.3, hw=0.2, ky=K_ISO)


def boulder(cv, p, d, size, rng, k, fl, trail=120):
    d = norm(d)
    tail = [(p[0] - d[0] * s_, p[1] - d[1] * s_ - (s_ / trail) ** 2 * 8) for s_ in np.linspace(size * 0.6, trail, 30)]
    fx.ribbon(cv, tail, [size * 1.6 * (0.5 + 0.8 * i / 29) for i in range(30)], hx("#2A1E18"), alpha=0.55, fade=0.95,
              erode=0.6, seed=9)
    fx.motes(cv, [(q[0] + rng.uniform(-6, 6), q[1] + rng.uniform(-6, 6)) for q in tail[2:18:2]], 1.6, fl.light, gain=1.6)
    # a chunky faceted rock: ink rim, three value planes, molten seams
    pts = []
    for i in range(7):
        a = 2 * math.pi * i / 7 + rng.uniform(-0.2, 0.2)
        rr = size * rng.uniform(0.8, 1.1)
        pts.append((p[0] + math.cos(a) * rr, p[1] + math.sin(a) * rr * 0.9))
    cv.fill(cv.raster(polys=[[(p[0] + (x - p[0]) * 1.2, p[1] + (y - p[1]) * 1.2) for x, y in pts]]), k.ink)
    cv.fill(cv.raster(polys=[pts]), hx("#4A3A30"))
    cv.fill(cv.raster(polys=[[pts[0], pts[1], pts[2], p]]), hx("#7A6250"))
    cv.fill(cv.raster(polys=[[pts[5], pts[6], pts[0], p]]), hx("#2E241E"))
    seams = [([p, pts[1]], 1.6), ([p, pts[4]], 1.4), ([(p[0] - 2, p[1] + 1), pts[6]], 1.2)]
    cv.fill(cv.raster(lines=seams), fl.light * 1.8, bloom=0.8)


@concept("mountainfall_ground_pound", "p2crit_warlord7_03.png", (480, 150, 1600, 780), inset=None, ppm=32.0,
         clean=[(985, 458, 1060, 470, 26)],
         title="Mountainfall · anvil-avatar ground pound (Valdris ultimate)",
         notes=["avatar: gold forge-light rim + molten seams on the silhouette, heat embers rising, scale 1.8",
                "pound every 1.1 s: molten cracks to the true 4.5 m radius, a gold-lit dust wall on the shock front, rock debris",
                "every shot is a boulder: faceted rock, molten seams, dust trail, a layered burst on impact",
                "the Warlord's red ring telegraph stays on top of every player effect, even an ultimate"])
def mountainfall(cv, ppm):
    rng = np.random.default_rng(44)
    k, fl = R["kinetic"], R["flame"]
    val = (800, 412)
    feet = (800, 428)
    ground_pound(cv, feet, 4.5, ppm, 3, rng, k, fl)
    cv.protect((812, 548), 20, 30)
    # avatar aura: a forge-heat column behind the silhouette, embers climbing
    fx.glow(cv, (val[0], val[1] - 14), 34, hx("#FF9A40"), gain=0.8, ky=1.6)
    fx.motes(cv, [(val[0] + rng.uniform(-30, 30), val[1] - rng.uniform(20, 90)) for _ in range(16)], 1.7, fl.light,
             gain=1.8)
    # boulder shots: one in flight, the previous one bursting on the Warlord's flank
    tgt = (1138, 486)
    d = norm((tgt[0] - val[0], tgt[1] - val[1]))
    boulder(cv, (val[0] + d[0] * 190, val[1] + d[1] * 190), d, 19, rng, k, fl, trail=150)
    burst(cv, (tgt[0] - 6, tgt[1] + 30), 1.5, ppm, 3, k, seed=5, core_lift=1.1, crown=4)
    cv.restore_danger((800, 430), 240, 200, g_ratio=0.45, b_ratio=0.42)


# =================================================================================================
# 09 Unmade death shatter (swarm), four deaths at four ages + kill motes to the killer
# =================================================================================================
def teardrop(p, d, L, w):
    d = norm(d)
    n = (-d[1], d[0])
    pts = []
    for t in np.linspace(0, 2 * math.pi, 14, endpoint=False):
        r = 1.0 if math.cos(t) < 0 else 1.0
        x = math.cos(t)
        y = math.sin(t) * (0.5 + 0.5 * (1 - x) / 2)
        pts.append((p[0] + d[0] * x * L * (0.6 if x < 0 else 1.0) + n[0] * y * w,
                    p[1] + d[1] * x * L * (0.6 if x < 0 else 1.0) + n[1] * y * w))
    return pts


def unmade_death(cv, c, r, f, rng, u, killer=None):
    """Unmade swarm death at frame f: white flash -> obsidian shards + teal ichor burst -> stain + motes."""
    core = (c[0], c[1] - r * 0.5)
    if f <= 1:
        sp = rand_spikes(rng, 6, r * 2.4, hw=0.22)
        cv.fill(star(cv, core, [(a + 0.15, L * 1.3, h * 1.3) for a, L, h in sp], r * 0.7), u.ink, alpha=0.95)
        rr = star(cv, core, sp, r * 0.55, p=1.3)
        if rr:
            sl, cov, cr = rr
            cv.over(sl, cov, np.where(cr[..., None] > 0.4, u.hot * 2.0, u.light * 1.5), bloom=0.7)
        return
    t = f / 60.0
    # ichor stain decal: grows over 10 frames, stays 2 s
    if f >= 3:
        k = min(1.0, (f - 2) / 10)
        blobs = [(c[0] + rng.uniform(-1, 1) * r * 0.9 * k, c[1] + rng.uniform(-0.5, 0.5) * r * 0.7 * k, r * rng.uniform(0.45, 0.8) * k)
                 for _ in range(5)] + [(c[0], c[1], r * 0.9 * k)]
        rr = fx.blob_field(cv, blobs, seed=int(c[0]), rough=0.25, light_dir=(-0.4, -0.9))
        if rr:
            sl, cov, tone = rr
            cv.over(sl, cov * 0.85, np.where((tone > 1.5)[..., None], u.body * 1.3, u.deep))
    # ink puff + ichor burst (frames 2-8)
    if f <= 10:
        kk = max(0.0, 1 - (f - 2) / 8)
        fx.smoke(cv, [(core[0] + rng.uniform(-r, r), core[1] + rng.uniform(-r, r * 0.4), r * rng.uniform(0.6, 0.9) * (0.7 + f / 12))
                      for _ in range(4)], u, core, alpha=0.9 * kk + 0.1, rim=u.body * 1.2, mid=fx.mixc(u.ink, u.deep, 0.6),
                 seed=int(c[1]), rough=0.12)
        sp = rand_spikes(rng, 8, r * 2.4 * (0.6 + 0.4 * kk), hw=0.2)
        rr = star(cv, core, sp, r * 0.6)
        if rr:
            sl, cov, cr = rr
            cv.over(sl, cov * (0.4 + 0.6 * kk), np.where(cr[..., None] > 0.45, u.light * 1.5, u.body * 1.3), bloom=0.5)
    # obsidian shards: fly, land, shrink away by frame 40
    if f < 40:
        sz = r * 0.7 * (1 - max(0, f - 20) / 20)
        fx.shards(cv, c, rng, 6, r * (0.6 + 2.2 * min(1, t / 0.2)), r * (1.0 + 3.0 * min(1, t / 0.2)), sz, u, ky=K_ISO,
                  lift=r * 2.0 * max(0.0, 1 - t / 0.25), dark=u.ink, edge=hx("#7F7278"), gain=1.0, spin=1.2)
    # ichor droplets: teardrops flung out, then fallen
    if 3 <= f <= 24:
        drops = []
        for i in range(7):
            a = rng.uniform(0, 2 * math.pi)
            dist = r * (1.0 + 2.6 * min(1.0, t / 0.2))
            h = max(0.0, r * 3.0 * math.sin(min(1.0, t / 0.35) * math.pi))
            p = (c[0] + math.cos(a) * dist, c[1] + math.sin(a) * dist * K_ISO - h)
            drops.append(teardrop(p, (math.cos(a), math.sin(a) * K_ISO + 0.6), r * 0.5, r * 0.32))
        cv.fill(cv.raster(polys=drops), u.body * 1.4, bloom=0.4)
    # kill motes curving to the killer (frames 10-40)
    if killer is not None and 10 <= f <= 40:
        k = (f - 10) / 30.0
        ctrl = ((c[0] + killer[0]) / 2, min(c[1], killer[1]) - 120)

        def bez(s2):
            return ((1 - s2) ** 2 * c[0] + 2 * (1 - s2) * s2 * ctrl[0] + s2 ** 2 * killer[0],
                    (1 - s2) ** 2 * (c[1] - r) + 2 * (1 - s2) * s2 * ctrl[1] + s2 ** 2 * (killer[1] - 20))

        heads = []
        for i in range(3):
            s_ = min(1.0, max(0.0, k - 0.06 * i))
            tail = [bez(max(0.0, s_ - 0.012 * j)) for j in range(12)]
            fx.ribbon(cv, tail, [3.4 * (1 - j / 11) + 0.3 for j in range(12)], hx("#FFE9A8") * 1.3, fade=0.9, bloom=0.5)
            heads.append(bez(s_))
        fx.diamond_glints(cv, heads, 5.0, hx("#FFF4D0"), gain=2.0)


@concept("unmade_death_shatter", "dc_before_horde300_00.png", (40, 330, 840, 780), inset=(290, 404, 390, 484),
         inset_at="tl", inset_S=3.0, ppm=32.0,
         title="Unmade death shatter · swarm kills at four ages",
         notes=["f0-1: the body flashes white over an ink star (the kill confirm, own kills only at full size)",
                "f2-10: obsidian shell shards with bone-grey edge light, a teal ichor splash, a black-teal ink puff",
                "f3-24: ichor teardrops arc out and fall; f3+: a teal-black ichor stain decal that fades over 2 s",
                "f10-40: 3 kill motes curve to the killer and flash their ring; Godworks die in cold-gold sparks instead"])
def unmade(cv, ppm):
    rng = np.random.default_rng(90)
    u = R["unmade"]
    killer = (776, 420)
    for c, f in (((350, 546), 1), ((336, 446), 5), ((206, 634), 14), ((296, 684), 24)):
        unmade_death(cv, c, 13, f, np.random.default_rng(int(c[0] * 7 + f)), u, killer=killer)
    fx.glow(cv, (776, 420), 22, hx("#FFC940"), gain=0.9)


# =================================================================================================
# 10 Crit vs precision vs a plain hit (and boss-scale hit feedback)
# =================================================================================================
def crit_hit(cv, p, d, size, ramp, rng, gold):
    """Crit punctuation: an anime slash cut across the hit, a 4-point white star, gold chips."""
    d = norm(d)
    a = math.atan2(d[1], d[0]) + math.radians(62)
    # the slash: a long thin crescent cut, ink edge under it
    c0 = (p[0] - math.cos(a + math.pi / 2) * size * 2.2, p[1] - math.sin(a + math.pi / 2) * size * 2.2)
    r = crescent(cv, c0, size * 2.2, a + math.pi / 2 - 0.66, a + math.pi / 2 + 0.66, size * 0.5, ky=1.0, seed=3,
                 erode=0.2, peak=0.5, rim=0.35)
    if r:
        cv.over(r[0], r[1], ramp.ink)
    r = crescent(cv, (c0[0] + 2, c0[1] - 3), size * 2.2, a + math.pi / 2 - 0.6, a + math.pi / 2 + 0.6, size * 0.32,
                 ky=1.0, seed=4, erode=0.15, peak=0.5, rim=0.45)
    if r:
        cv.over(r[0], r[1], gold * 1.6, bloom=0.6)
        cv.over(r[0], r[2], ramp.hot * 2.2, bloom=0.9)
    # the star: 4 long points, ink behind at 45 degrees
    cv.fill(star(cv, p, [(math.pi / 4 + i * math.pi / 2, size * 1.1, 0.22) for i in range(4)], size * 0.2), ramp.ink,
            alpha=0.9)
    rr = star(cv, p, [(i * math.pi / 2, size * (1.5 if i % 2 == 0 else 1.1), 0.14) for i in range(4)], size * 0.16, p=1.0)
    if rr:
        sl, cov, cr = rr
        cv.over(sl, cov, np.where(cr[..., None] > 0.3, ramp.hot * 2.3, gold * 1.7), bloom=0.9)
    fx.shards(cv, p, rng, 6, size * 0.5, size * 1.4, size * 0.3, ramp, ky=1.0, dark=hx("#5A3A10"), edge=gold, gain=1.5)


def precision_hit(cv, p, size, col, ramp, rng):
    """Precision (manual perfect hit): a bullseye accent collapsing onto the point + a crosshair glint."""
    fx.ring_accent(cv, p, size * 1.2, 2.4, col, gain=1.6, ky=1.0, gaps=0.2, seed=2)
    fx.ring_accent(cv, p, size * 1.2 + 3, 4.5, ramp.ink, gain=1.0, ky=1.0, gaps=0.2, seed=2, alpha=0.7)
    lines = []
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        v = (math.cos(a), math.sin(a))
        lines.append(fx.streak_poly((p[0] + v[0] * size * 0.95, p[1] + v[1] * size * 0.95),
                                    (p[0] + v[0] * size * 0.35, p[1] + v[1] * size * 0.35), 2.6, 0.6, cap=False))
    cv.fill(cv.raster(polys=lines), col * 1.7, bloom=0.7)
    cv.fill(star(cv, p, [(i * math.pi / 2, size * 0.7, 0.12) for i in range(4)], size * 0.1, p=1.0), col * 2.2,
            bloom=0.9)


@concept("crit_precision_hits", "p2fix_after_warlord7_01.png", (560, 260, 1360, 710), inset=(950, 400, 1040, 520),
         inset_at="tl", inset_S=3.2, ppm=32.0, clean=[(851, 459, 822, 500, 20), (920, 410, 900, 372, 16), (962, 457, 936, 426, 16), (1067, 470, 1067, 438, 13),
                (943, 497, 925, 470, 12)],
         title="Hit punctuation · crit, precision and a plain hit",
         notes=["plain hit: a small 5-point ink-backed star in the element colour, 4 frames",
                "crit: a gold anime slash across the hit + a 4-point white star + gold chips; 3-frame hit-stop on the target",
                "precision (Manual): a cyan-white bullseye collapses onto the point + crosshair glint",
                "boss hits: punctuation at the contact edge, never over the eyes; the red telegraph stays on top"])
def crits(cv, ppm):
    rng = np.random.default_rng(17)
    k = R["kinetic"]
    gold = hx("#FFC940")
    cyan = hx("#7FF6FF")
    muzzle = (808, 452)
    # a plain hit on a cinderling
    fx.impact_star(cv, up((932, 650), 0.4, ppm), 11, k, rng, n=5, gain=1.4, core_gain=2.2, ink_scale=1.4, hw=0.22)
    # precision on a cinderling
    precision_hit(cv, (887, 520), 20, cyan, k, rng)
    # crit on the Warlord's flank (contact edge), with a boss rim-flash on the near edge
    hit = (984, 468)
    r = crescent(cv, (1058, 468), 84, math.radians(150), math.radians(210), 9, ky=1.0, seed=2, erode=0.2, peak=0.5)
    if r:
        cv.over(r[0], r[1] * 0.8, gold * 1.2, bloom=0.4)
    fx.light_spill(cv, hit, 70, gold, gain=0.6, ky=1.0)
    crit_hit(cv, hit, (1.0, 0.08), 34, k, rng, gold)
    return [(1004, 420, "57", 24, (255, 201, 64)), (887, 486, "31", 21, (127, 246, 255)), (932, 624, "12", 14, (255, 247, 230))]


if __name__ == "__main__":
    names = sys.argv[1:] or list(CONCEPTS)
    order = list(CONCEPTS)
    for n in names:
        render(n, order.index(n) + 1)
