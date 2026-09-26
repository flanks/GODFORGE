"""Glyphs, status pips and ground decals (VFX_STYLE sections 11, 12.3, 16, 17, 19).

  atlas/vfx_glyphs.png   16 sigils (256 px): curse, mark, binding hex, root chain, radiant hexagram,
                         sun wheel, clock dial, precision bullseye, and the 8 god sigils (gods.csv order)
  atlas/vfx_pips.png     16 status / pickup pips (128 px) drawn at head_top or on pickups
  atlas/vfx_decals.png   16 ground decals (256 px): scorches with glowing cracks, crack stars, soot,
                         burn patch, ichor / plague / ink stains, rot scar, crater, molten gashes
Glyphs are 2-4 brush strokes, no fine detail: they must read at 24-40 px.
"""
import math

import numpy as np

import paint as P
from vfxlib import (V_BODY, V_DEEP, V_HOT, V_INK, V_LIGHT, Atlas, Cell, bolt_points, kite, pmap, streak_poly,
                    tapered_path)

GLYPHS = ["curse", "mark", "binding_hex", "root_chain", "hexagram", "sun_wheel", "clock_dial", "bullseye",
          "god_pyra", "god_zephyros", "god_nyctia", "god_aeon", "god_gaiaa", "god_morwenn", "god_seraphel",
          "god_umbra_rex"]
PIPS = ["burn", "shock", "curse", "root", "bleed", "mark", "stun", "doom", "note", "heart", "shard", "part", "coin",
        "ping", "heal", "tick"]
DECALS = ["scorch_a", "scorch_b", "scorch_c", "crack_star_a", "crack_star_b", "soot", "burn_patch", "ichor_stain_a",
          "ichor_stain_b", "plague_stain_a", "plague_stain_b", "ink_stain_a", "ink_stain_b", "rot_scar", "crater",
          "molten_gashes"]


def brush(pts, w, taper=(0.35, 0.3)):
    """A calligraphic stroke: thin at both ends, full width in the middle."""
    n = len(pts)
    wid = []
    for i in range(n):
        t = i / max(1, n - 1)
        a = min(1.0, t / max(taper[0], 1e-3))
        b = min(1.0, (1 - t) / max(taper[1], 1e-3))
        wid.append(w * (0.25 + 0.75 * min(a, b) ** 0.6))
    return tapered_path(pts, wid)


def arc(C, r, a0, a1, n=40, ky=1.0):
    return [(C[0] + math.cos(a) * r, C[1] + math.sin(a) * r * ky) for a in np.linspace(a0, a1, n)]


def finish_glyph(c, strokes, hot=None, outline=2.4, body_band=1.6):
    """Strokes: light fill, a body band along the edge, an ink outline; optional hot accents."""
    m = c.polys(strokes)
    m = c.ragged(m, 0.5, 0.8)
    c.paint(c.sdf(m) > -outline, V_INK, order=0.2)
    d = c.inside_dist(m)
    c.paint(m, np.where(d < body_band, V_BODY, V_LIGHT), order=0.6)
    if hot is not None:
        c.paint(hot & m, V_HOT, order=0.9)
    return m


def glyph_cell(i, seed, s=256):
    c = Cell(s, s, seed=seed + i)
    C = (s / 2, s / 2)
    R = s * 0.4
    name = GLYPHS[i]
    st = []
    hot = None
    if name == "curse":
        for k in range(6):
            a0 = math.pi / 6 + k * math.tau / 6
            p0 = (C[0] + math.cos(a0) * R, C[1] + math.sin(a0) * R)
            p1 = (C[0] + math.cos(a0 + math.tau / 6 * 0.78) * R, C[1] + math.sin(a0 + math.tau / 6 * 0.78) * R)
            st.append(brush([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), p1], 9))
        tri = [(C[0], C[1] + R * 0.62), (C[0] - R * 0.52, C[1] - R * 0.3), (C[0] + R * 0.52, C[1] - R * 0.3)]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            st.append(brush([tri[a], ((tri[a][0] + tri[b][0]) / 2, (tri[a][1] + tri[b][1]) / 2), tri[b]], 10))
        st.append(brush([(C[0], C[1] - R * 0.8), (C[0], C[1]), (C[0], C[1] + R * 0.35)], 11))
        hot = c.dots([(C[0], C[1] - R * 0.05, 7)])
        st.append([(x + 0.01, y) for x, y in arc(C, 8, 0, math.tau, 12)])
    elif name == "mark":
        for k in range(4):
            a0 = k * math.pi / 2 + 0.28
            st.append(brush(arc(C, R * 0.8, a0, a0 + math.pi / 2 - 0.56, 16), 10))
            a = k * math.pi / 2
            p0 = (C[0] + math.cos(a) * R * 1.02, C[1] + math.sin(a) * R * 1.02)
            p1 = (C[0] + math.cos(a) * R * 0.5, C[1] + math.sin(a) * R * 0.5)
            st.append(brush([p0, p1], 12, (0.1, 0.6)))
        st.append([(x, y) for x, y in arc(C, 9, 0, math.tau, 14)])
        hot = c.dots([(C[0], C[1], 6)])
    elif name == "binding_hex":
        st.append(brush(arc(C, R, 0.1, math.tau - 0.1, 80), 7, (0.05, 0.05)))
        st.append(brush(arc(C, R * 0.8, 0.5, math.tau + 0.2, 80), 5, (0.05, 0.05)))
        for k in range(6):
            a = k * math.tau / 6
            p = (C[0] + math.cos(a) * R * 0.9, C[1] + math.sin(a) * R * 0.9)
            d = (math.cos(a + 1.2), math.sin(a + 1.2))
            st.append(brush([(p[0] - d[0] * 12, p[1] - d[1] * 12), (p[0] + d[0] * 12, p[1] + d[1] * 12)], 9))
            st.append(brush([(p[0] - d[1] * 7, p[1] + d[0] * 7), (p[0] + d[1] * 7 + d[0] * 6, p[1] - d[0] * 7 + d[1] * 6)], 6))
        for k in range(3):
            a0 = -math.pi / 2 + k * math.tau / 3
            p0 = (C[0] + math.cos(a0) * R * 0.62, C[1] + math.sin(a0) * R * 0.62)
            p1 = (C[0] + math.cos(a0 + math.tau / 3) * R * 0.62, C[1] + math.sin(a0 + math.tau / 3) * R * 0.62)
            st.append(brush([p0, p1], 6))
    elif name == "root_chain":
        for k, (dx, ang) in enumerate([(-R * 0.36, 0.5), (R * 0.36, 0.5)]):
            pts = []
            for a in np.linspace(0, math.tau, 48):
                x, y = math.cos(a) * R * 0.46, math.sin(a) * R * 0.26
                ca, sa = math.cos(ang), math.sin(ang)
                pts.append((C[0] + dx + x * ca - y * sa, C[1] + x * sa + y * ca))
            st.append(tapered_path(pts, [15] * 48))
        m_o = c.polys(st)
        st = []
        hole = []
        for dx in (-R * 0.36, R * 0.36):
            pts = []
            for a in np.linspace(0, math.tau, 48):
                x, y = math.cos(a) * R * 0.3, math.sin(a) * R * 0.1
                ca, sa = math.cos(0.5), math.sin(0.5)
                pts.append((C[0] + dx + x * ca - y * sa, C[1] + x * sa + y * ca))
            hole.append(pts)
        m = m_o & ~c.polys(hole)
        m = c.ragged(m, 0.5, 0.8)
        c.paint(c.sdf(m) > -2.4, V_INK, order=0.2)
        c.paint(m, np.where(c.inside_dist(m) < 1.6, V_BODY, V_LIGHT), order=0.6)
        return c.pack()
    elif name == "hexagram":
        for off in (0.0, math.pi):
            tri = [(C[0] + math.cos(-math.pi / 2 + off + k * math.tau / 3) * R, C[1] + math.sin(-math.pi / 2 + off + k * math.tau / 3) * R)
                   for k in range(3)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                st.append(tapered_path([tri[a], tri[b]], [8, 8]))
        st.append([(x, y) for x, y in arc(C, R * 0.18, 0, math.tau, 6)])
        hot = c.dots([(C[0], C[1], R * 0.1)])
    elif name == "sun_wheel":
        st.append(tapered_path(arc(C, R * 0.5, 0, math.tau, 60), [10] * 60))
        for k in range(8):
            a = k * math.tau / 8
            p0 = (C[0] + math.cos(a) * R * 0.12, C[1] + math.sin(a) * R * 0.12)
            p1 = (C[0] + math.cos(a) * R * 0.5, C[1] + math.sin(a) * R * 0.5)
            st.append(tapered_path([p0, p1], [4, 7]))
            q0 = (C[0] + math.cos(a + math.pi / 8) * R * 0.66, C[1] + math.sin(a + math.pi / 8) * R * 0.66)
            q1 = (C[0] + math.cos(a + math.pi / 8) * R * 1.02, C[1] + math.sin(a + math.pi / 8) * R * 1.02)
            st.append(tapered_path([q0, q1], [9, 0.5]))
        hot = c.dots([(C[0], C[1], R * 0.12)])
        st.append([(x, y) for x, y in arc(C, R * 0.14, 0, math.tau, 16)])
    elif name == "clock_dial":
        st.append(brush(arc(C, R * 0.92, -1.2, math.tau - 1.5, 90), 8, (0.08, 0.12)))
        for k in range(12):
            a = k * math.tau / 12
            L = 0.24 if k % 3 == 0 else 0.13
            p0 = (C[0] + math.cos(a) * R * 0.78, C[1] + math.sin(a) * R * 0.78)
            p1 = (C[0] + math.cos(a) * R * (0.78 - L), C[1] + math.sin(a) * R * (0.78 - L))
            st.append(tapered_path([p0, p1], [7 if k % 3 == 0 else 5, 2]))
        st.append(tapered_path([C, (C[0] + R * 0.1, C[1] - R * 0.55)], [11, 2]))
        st.append(tapered_path([C, (C[0] + R * 0.42, C[1] + R * 0.12)], [9, 2]))
        hot = c.dots([(C[0], C[1], 8)])
        st.append([(x, y) for x, y in arc(C, 10, 0, math.tau, 12)])
    elif name == "bullseye":
        st.append(brush(arc(C, R * 0.95, 0.3, 1.9, 30), 7))
        st.append(brush(arc(C, R * 0.95, 2.4, 3.9, 30), 7))
        st.append(brush(arc(C, R * 0.95, 4.4, 5.9, 30), 7))
        st.append(brush(arc(C, R * 0.55, 1.0, 2.9, 24), 6))
        st.append(brush(arc(C, R * 0.55, 3.8, 5.9, 24), 6))
        for k in range(4):
            a = k * math.pi / 2 + math.pi / 4
            p0 = (C[0] + math.cos(a) * R * 1.1, C[1] + math.sin(a) * R * 1.1)
            p1 = (C[0] + math.cos(a) * R * 0.72, C[1] + math.sin(a) * R * 0.72)
            st.append(tapered_path([p0, p1], [8, 1.5]))
        m, _ = c.star(C, [(k * math.pi / 2, R * 0.28, 0.35) for k in range(4)], R * 0.05, p=2)
        hot = m
        st.append([(C[0] + math.cos(k * math.pi / 2) * R * 0.28, C[1] + math.sin(k * math.pi / 2) * R * 0.28) for k in range(4)])
    elif name == "god_pyra":  # flame
        from vfxlib import tongue_poly
        st.append(tongue_poly((C[0], C[1] + R * 0.85), R * 1.7, R * 0.95, 0.6, curl=0.3, tip_curl=0.5))
        inner = tongue_poly((C[0] + 4, C[1] + R * 0.8), R * 0.85, R * 0.4, 1.4, curl=0.3)
        m = finish_glyph(c, st)
        c.paint(c.polys([inner]) & m, V_DEEP, order=0.8)
        return c.pack()
    elif name == "god_zephyros":  # wind: three curls
        for k, (dy, L) in enumerate([(-0.45, 1.5), (0.0, 1.9), (0.45, 1.3)]):
            y = C[1] + dy * R
            pts = [(C[0] - R * 0.95 + t * R * L, y + math.sin(t * 3.0) * R * 0.08) for t in np.linspace(0, 1, 20)]
            end = pts[-1]
            curl = [(end[0] + math.cos(a) * R * 0.18, end[1] - R * 0.18 + math.sin(a) * R * 0.18)
                    for a in np.linspace(math.pi / 2, -math.pi, 14)]
            st.append(brush(pts + curl[1:], 12 - 2 * abs(k - 1), (0.2, 0.15)))
    elif name == "god_nyctia":  # crescent moon
        m = c.dots([(C[0], C[1], R * 0.9)]) & ~c.dots([(C[0] + R * 0.4, C[1] - R * 0.18, R * 0.78)])
        m = c.ragged(m, 0.5, 0.8)
        c.paint(c.sdf(m) > -2.4, V_INK, order=0.2)
        c.paint(m, np.where(c.inside_dist(m) < 1.6, V_BODY, V_LIGHT), order=0.6)
        st2 = c.polys([kite((C[0] + R * 0.55, C[1] + R * 0.45), (0, -1), 16, 5, back=1.0),
                       kite((C[0] + R * 0.55, C[1] + R * 0.45), (1, 0), 11, 4, back=1.0)])
        c.paint(st2, V_HOT, order=0.8)
        return c.pack()
    elif name == "god_aeon":  # hourglass dial
        top = [(C[0] - R * 0.55, C[1] - R * 0.8), (C[0] + R * 0.55, C[1] - R * 0.8), (C[0] + R * 0.06, C[1]),
               (C[0] + R * 0.55, C[1] + R * 0.8), (C[0] - R * 0.55, C[1] + R * 0.8), (C[0] - R * 0.06, C[1])]
        for a, b in zip(top, top[1:] + top[:1]):
            st.append(tapered_path([a, b], [9, 9]))
        st.append(tapered_path([(C[0] - R * 0.75, C[1] - R * 0.86), (C[0] + R * 0.75, C[1] - R * 0.86)], [11, 11]))
        st.append(tapered_path([(C[0] - R * 0.75, C[1] + R * 0.86), (C[0] + R * 0.75, C[1] + R * 0.86)], [11, 11]))
        sand = [(C[0] - R * 0.3, C[1] + R * 0.78), (C[0] + R * 0.3, C[1] + R * 0.78), (C[0], C[1] + R * 0.3)]
        hot = c.polys([sand])
        st.append(sand)
    elif name == "god_gaiaa":  # stone: a faceted standing stone
        pts = [(C[0] - R * 0.5, C[1] + R * 0.85), (C[0] - R * 0.62, C[1] - R * 0.2), (C[0] - R * 0.2, C[1] - R * 0.88),
               (C[0] + R * 0.35, C[1] - R * 0.7), (C[0] + R * 0.6, C[1] + R * 0.1), (C[0] + R * 0.48, C[1] + R * 0.85)]
        m = c.polys([pts])
        m = c.ragged(m, 0.6, 0.6)
        c.paint(c.sdf(m) > -2.4, V_INK, order=0.2)
        c.paint(m, V_BODY, order=0.4)
        c.paint(c.polys([[pts[1], pts[2], pts[3], (C[0] + R * 0.05, C[1] - R * 0.1)]]) & m, V_LIGHT, order=0.6)
        c.paint(c.polys([[pts[4], pts[5], (C[0] + R * 0.1, C[1] + R * 0.85), (C[0] + R * 0.12, C[1] + R * 0.05)]]) & m,
                V_DEEP, order=0.6)
        return c.pack()
    elif name == "god_morwenn":  # wave crest
        pts = [(C[0] - R * 0.95 + t * R * 1.9, C[1] + R * 0.35 + math.sin(t * math.tau * 1.5) * R * 0.12)
               for t in np.linspace(0, 1, 30)]
        crest = [(C[0] - R * 0.2 + math.cos(a) * R * 0.55, C[1] + R * 0.05 + math.sin(a) * R * 0.55)
                 for a in np.linspace(math.pi * 0.95, math.pi * 2.3, 30)]
        st.append(brush(pts, 12, (0.1, 0.1)))
        st.append(brush(crest, 13, (0.15, 0.4)))
        st.append(brush([(C[0] + R * 0.25, C[1] - R * 0.18), (C[0] + R * 0.5, C[1] - R * 0.5)], 7))
    elif name == "god_seraphel":  # winged sun
        st.append([(x, y) for x, y in arc(C, R * 0.3, 0, math.tau, 30)])
        for s in (-1, 1):
            for k in range(3):
                y = C[1] - R * 0.1 + k * R * 0.18
                p0 = (C[0] + s * R * 0.35, y)
                p1 = (C[0] + s * R * (1.0 - 0.18 * k), y - R * (0.28 - 0.08 * k))
                st.append(brush([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - 4), p1], 11 - 2 * k, (0.1, 0.5)))
        hot = c.dots([(C[0], C[1], R * 0.14)])
    else:  # umbra_rex: a broken crown
        base = [(C[0] - R * 0.8, C[1] + R * 0.5), (C[0] + R * 0.8, C[1] + R * 0.5)]
        st.append(tapered_path(base, [16, 16]))
        pts = [(C[0] - R * 0.8, C[1] + R * 0.45), (C[0] - R * 0.7, C[1] - R * 0.55), (C[0] - R * 0.35, C[1] - R * 0.05),
               (C[0] - R * 0.05, C[1] - R * 0.8), (C[0] + R * 0.12, C[1] - R * 0.2)]
        for a, b in zip(pts[:-1], pts[1:]):
            st.append(tapered_path([a, b], [9, 9]))
        pts2 = [(C[0] + R * 0.3, C[1] - R * 0.1), (C[0] + R * 0.55, C[1] - R * 0.6), (C[0] + R * 0.8, C[1] + R * 0.45)]
        for a, b in zip(pts2[:-1], pts2[1:]):
            st.append(tapered_path([a, b], [9, 9]))
        # the crack
        rng = np.random.default_rng(5)
        cr = bolt_points((C[0] + R * 0.2, C[1] - R * 0.4), (C[0] + R * 0.15, C[1] + R * 0.7), rng, 0.2, 3)
        m = finish_glyph(c, st)
        c.erase(c.lines([(cr, 6)]))
        return c.pack()
    finish_glyph(c, st, hot)
    return c.pack()


def pip_cell(i, seed, s=128):
    c = Cell(s, s, seed=seed + i)
    C = (s / 2, s / 2)
    R = s * 0.38
    name = PIPS[i]
    from vfxlib import tongue_poly
    st = []
    hot = None
    if name == "burn":
        st.append(tongue_poly((C[0], C[1] + R * 0.95), R * 1.9, R * 1.1, 0.8, curl=0.3, tip_curl=0.5))
        m = finish_glyph(c, st, outline=2.2, body_band=1.2)
        c.paint(c.polys([tongue_poly((C[0] + 2, C[1] + R * 0.9), R * 0.9, R * 0.45, 1.5)]) & m, V_HOT, order=0.8)
        return c.pack()
    if name == "shock":
        st.append(tapered_path([(C[0] + R * 0.35, C[1] - R), (C[0] - R * 0.3, C[1] + R * 0.05), (C[0] + R * 0.25, C[1] + R * 0.05),
                                (C[0] - R * 0.35, C[1] + R)], [4, 11, 11, 3]))
    elif name == "curse":
        for k in range(6):
            a0 = math.pi / 6 + k * math.tau / 6
            p0 = (C[0] + math.cos(a0) * R, C[1] + math.sin(a0) * R)
            p1 = (C[0] + math.cos(a0 + math.tau / 6 * 0.8) * R, C[1] + math.sin(a0 + math.tau / 6 * 0.8) * R)
            st.append(tapered_path([p0, p1], [6, 6]))
        st.append(tapered_path([(C[0], C[1] - R * 0.7), (C[0], C[1] + R * 0.5)], [8, 3]))
    elif name == "root":
        for dx in (-R * 0.36, R * 0.36):
            st.append(tapered_path([(C[0] + dx + math.cos(a) * R * 0.45, C[1] + math.sin(a) * R * 0.28)
                                    for a in np.linspace(0, math.tau, 32)], [8] * 32))
    elif name == "bleed":
        st.append(P.teardrop((C[0], C[1] + R * 0.35), (0, 1), R * 0.62, R * 1.4))
    elif name == "mark":
        for k in range(4):
            a0 = k * math.pi / 2 + 0.3
            st.append(tapered_path(arc(C, R * 0.8, a0, a0 + math.pi / 2 - 0.6, 10), [7] * 10))
            a = k * math.pi / 2
            st.append(tapered_path([(C[0] + math.cos(a) * R * 1.05, C[1] + math.sin(a) * R * 1.05),
                                    (C[0] + math.cos(a) * R * 0.45, C[1] + math.sin(a) * R * 0.45)], [8, 1]))
        hot = c.dots([(C[0], C[1], 5)])
        st.append(arc(C, 6, 0, math.tau, 10))
    elif name == "stun":
        m, rel = c.star(C, [(k * math.pi / 2 - math.pi / 2, R * 1.05, 0.34) for k in range(4)], R * 0.2, p=1.5)
        c.paint(c.sdf(m) > -2.2, V_INK, order=0.2)
        c.paint(m, np.where(rel < 0.4, V_HOT, V_LIGHT), order=0.6)
        return c.pack()
    elif name == "doom":
        st.append([(C[0], C[1] - R), (C[0] + R * 0.75, C[1]), (C[0], C[1] + R), (C[0] - R * 0.75, C[1])])
        m = finish_glyph(c, st)
        c.paint(c.polys([[(C[0], C[1] - R * 0.45), (C[0] + R * 0.3, C[1]), (C[0], C[1] + R * 0.45), (C[0] - R * 0.3, C[1])]]),
                V_INK, order=0.8)
        return c.pack()
    elif name == "note":
        st.append(tapered_path([(C[0] + R * 0.3, C[1] + R * 0.6), (C[0] + R * 0.3, C[1] - R * 0.95)], [8, 8]))
        st.append(tapered_path([(C[0] + R * 0.3, C[1] - R * 0.95), (C[0] + R * 0.85, C[1] - R * 0.55)], [9, 4]))
        st.append([(C[0] - R * 0.05 + math.cos(a) * R * 0.42, C[1] + R * 0.62 + math.sin(a) * R * 0.3)
                   for a in np.linspace(0, math.tau, 20)])
    elif name == "heart":
        m = c.dots([(C[0] - R * 0.42, C[1] - R * 0.25, R * 0.52), (C[0] + R * 0.42, C[1] - R * 0.25, R * 0.52)]) | \
            c.polys([[(C[0] - R * 0.9, C[1] - R * 0.1), (C[0] + R * 0.9, C[1] - R * 0.1), (C[0], C[1] + R * 0.95)]])
        c.paint(c.sdf(m) > -2.4, V_INK, order=0.2)
        c.paint(m, V_BODY, order=0.5)
        c.paint(c.dots([(C[0] - R * 0.45, C[1] - R * 0.35, R * 0.22)]), V_LIGHT, order=0.8)
        return c.pack()
    elif name == "shard":
        k, f = P.shard_polys((C[0], C[1] + R * 0.1), (0.25, -1), R * 1.2, R * 0.5, back=0.55)
        m = c.polys([k])
        c.paint(c.sdf(m) > -2.2, V_INK, order=0.2)
        c.paint(m, V_BODY, order=0.4)
        c.paint(c.polys([f]) & m, V_LIGHT, order=0.6)
        return c.pack()
    elif name == "part":
        st.append([(C[0], C[1] - R), (C[0] + R * 0.85, C[1]), (C[0], C[1] + R), (C[0] - R * 0.85, C[1])])
        hot = c.polys([[(C[0], C[1] - R * 0.5), (C[0] + R * 0.25, C[1]), (C[0], C[1] + R * 0.1), (C[0] - R * 0.25, C[1])]])
    elif name == "coin":
        m = c.dots([(C[0], C[1], R * 0.85)])
        c.paint(c.sdf(m) > -2.2, V_INK, order=0.2)
        c.paint(m, V_DEEP, order=0.3)
        c.paint(c.dots([(C[0], C[1], R * 0.68)]), V_BODY, order=0.4)
        c.paint(c.dots([(C[0], C[1], R * 0.68)]) & ~c.dots([(C[0] + R * 0.15, C[1] + R * 0.15, R * 0.66)]), V_LIGHT, order=0.5)
        return c.pack()
    elif name == "ping":
        st.append([(C[0] - R * 0.8, C[1] - R * 0.6), (C[0], C[1] + R * 0.8), (C[0] + R * 0.8, C[1] - R * 0.6),
                   (C[0], C[1] - R * 0.1)])
    elif name == "heal":
        st.append(tapered_path([(C[0], C[1] - R), (C[0], C[1] + R)], [14, 14]))
        st.append(tapered_path([(C[0] - R, C[1]), (C[0] + R, C[1])], [14, 14]))
    else:  # tick: a clock hand sweeping
        st.append(tapered_path(arc(C, R * 0.9, -2.2, 1.2, 30), [3] + [6] * 28 + [3]))
        st.append(tapered_path([C, (C[0] + R * 0.1, C[1] - R * 0.75)], [8, 2]))
        st.append(arc(C, 6, 0, math.tau, 10))
    finish_glyph(c, st, hot, outline=2.2, body_band=1.2)
    return c.pack()


# ---- decals ------------------------------------------------------------------------------------
def blotch(c, C, R, rough=0.35, freq=3.0, seed_off=0.0):
    r, th = c.polar(C)
    n = c.nz((th + np.pi) / math.tau * freq * 8 + seed_off, r * 0.03 + seed_off)
    n2 = c.nz(c.X * 0.08 + seed_off, c.Y * 0.08)
    edge = R * (1 + rough * (n - 0.5) * 2) * (0.9 + 0.2 * n2)
    return r < edge, r / np.maximum(edge, 1e-3)


def cracks(c, C, R, rng, n, w=2.4, reach=(0.6, 1.1), jag=0.16):
    lines = []
    for k in range(n):
        a = math.tau * k / n + rng.uniform(-0.3, 0.3)
        p0 = (C[0] + math.cos(a) * R * 0.12, C[1] + math.sin(a) * R * 0.12)
        L = R * rng.uniform(*reach)
        p1 = (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L)
        pts = bolt_points(p0, p1, rng, jag, 4)
        lines.append((pts, w))
        if rng.random() < 0.6:
            j = len(pts) // 2
            b = a + rng.uniform(-0.8, 0.8)
            q = (pts[j][0] + math.cos(b) * L * 0.35, pts[j][1] + math.sin(b) * L * 0.35)
            lines.append((bolt_points(pts[j], q, rng, jag, 3), w * 0.6))
    return lines


def decal_cell(i, seed, s=256):
    c = Cell(s, s, seed=seed + i)
    rng = np.random.default_rng(seed + i)
    C = (s / 2, s / 2)
    R = s * 0.36
    name = DECALS[i]
    r, th = c.polar(C)
    ero_d = np.clip(1 - r / (R * 1.3), 0.02, 1)
    if name.startswith("scorch"):
        m, rel = blotch(c, C, R, rough=0.3 + 0.1 * i, seed_off=i * 3)
        c.paint(m, np.where(rel > 0.82, V_DEEP, V_INK), order=0.6)
        # splatter specks
        specks = [(C[0] + math.cos(a) * R * rng.uniform(1.0, 1.35), C[1] + math.sin(a) * R * rng.uniform(1.0, 1.35),
                   rng.uniform(1.5, 5)) for a in rng.uniform(0, math.tau, 14)]
        c.paint(c.dots(specks), V_INK, order=0.2)
        ln = cracks(c, C, R, rng, 5 + i, w=2.6)
        mc = c.lines(ln)
        c.paint(c.lines([(p, w * 2.2) for p, w in ln]) & m, V_DEEP, order=0.3)
        c.paint(mc & m, V_LIGHT, order=0.25)
        c.paint(c.lines([(p[:len(p) // 2], w * 0.45) for p, w in ln]) & m, V_HOT, order=0.2)
        return c.pack(ero=np.where(mc, 0.25, ero_d * 0.8 + 0.2 * c.nz(c.X * 0.2, c.Y * 0.2)))
    if name.startswith("crack_star"):
        n = 7 if name.endswith("a") else 9
        gash, lit = [], []
        for k in range(n):
            a = k * math.tau / n + rng.uniform(-0.25, 0.25)
            L = R * 1.3 * rng.uniform(0.6, 1.0)
            pts = bolt_points((C[0] + math.cos(a) * R * 0.1, C[1] + math.sin(a) * R * 0.1),
                              (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L), rng, 0.1, 3)
            m_ = len(pts)
            wid = [12 * (1 - j / (m_ - 1)) ** 0.9 + 0.8 for j in range(m_)]
            gash.append(tapered_path(pts, wid))
            lit.append(tapered_path([(x + 1.5, y + 2.0) for x, y in pts], [w * 0.35 for w in wid]))
            if rng.random() < 0.7:
                j = m_ // 2
                b = a + rng.uniform(-0.9, 0.9)
                q = (pts[j][0] + math.cos(b) * L * 0.35, pts[j][1] + math.sin(b) * L * 0.35)
                br = bolt_points(pts[j], q, rng, 0.12, 2)
                gash.append(tapered_path(br, [5 * (1 - t) + 0.6 for t in np.linspace(0, 1, len(br))]))
        dark, rel = blotch(c, C, R * 0.45, rough=0.4)
        c.paint(dark, V_INK, order=0.7)
        c.paint(c.polys(gash), V_INK, order=0.5)
        c.paint(c.polys(lit) & ~dark, V_DEEP, order=0.45)
        polys = [kite((C[0] + math.cos(a) * R * rng.uniform(0.5, 1.2), C[1] + math.sin(a) * R * rng.uniform(0.5, 1.2)),
                      (math.cos(a), math.sin(a)), rng.uniform(6, 12), rng.uniform(2.5, 4.5)) for a in rng.uniform(0, math.tau, 14)]
        c.paint(c.polys(polys), V_DEEP, order=0.3)
        return c.pack()
    if name == "soot":
        m, rel = blotch(c, C, R * 1.1, rough=0.45, freq=4)
        m &= c.nz(c.X * 0.1, c.Y * 0.1) + rel * 0.4 < 1.05
        c.paint(m, V_INK, order=0.5)
        specks = [(C[0] + math.cos(a) * R * rng.uniform(0.3, 1.1), C[1] + math.sin(a) * R * rng.uniform(0.3, 1.1), 2.2)
                  for a in rng.uniform(0, math.tau, 10)]
        c.paint(c.dots(specks), V_BODY, order=0.2)
        return c.pack()
    if name == "burn_patch":
        m, rel = blotch(c, C, R, rough=0.35, freq=5)
        v = np.where(rel < 0.4, V_LIGHT, np.where(rel < 0.7, V_BODY, np.where(rel < 0.88, V_DEEP, V_INK)))
        c.paint(m, v, order=0.5)
        return c.pack(ero=np.clip(1 - rel, 0.02, 1) * 0.7 + 0.3 * c.nz(c.X * 0.2, c.Y * 0.2))
    if name.startswith("ichor_stain") or name.startswith("plague_stain"):
        pl = name.startswith("plague")
        m, rel = blotch(c, C, R * (0.85 if pl else 0.8), rough=0.4, freq=3 + i % 2, seed_off=i)
        drops = []
        for k in range(10 if not pl else 6):
            a = rng.uniform(0, math.tau)
            rr = R * rng.uniform(0.95, 1.35)
            drops.append((C[0] + math.cos(a) * rr, C[1] + math.sin(a) * rr, rng.uniform(3, 8)))
        dm = c.dots(drops)
        c.paint(m | dm, V_INK, order=0.4)
        inner = m & (rel < 0.8)
        c.paint(inner, V_DEEP, order=0.5)
        # a lit pool edge (the wet sheen) toward the top
        sheen = inner & ~blotch(c, (C[0] + 4, C[1] + 6), R * (0.8 if pl else 0.75) * 0.95, rough=0.4, seed_off=i)[0]
        c.paint(sheen, V_BODY, order=0.6)
        if pl:
            bub = []
            for k in range(7):
                a = rng.uniform(0, math.tau)
                rr = R * rng.uniform(0.1, 0.6)
                bub.append((C[0] + math.cos(a) * rr, C[1] + math.sin(a) * rr, rng.uniform(4, 10)))
            mb = c.dots(bub) & inner
            c.paint(mb, V_BODY, order=0.7)
            c.paint(c.dots([(x - r * 0.3, y - r * 0.3, r * 0.3) for x, y, r in bub]) & mb, V_LIGHT, order=0.8)
        return c.pack()
    if name.startswith("ink_stain"):
        m, rel = blotch(c, C, R * 0.8, rough=0.5, freq=6, seed_off=i * 2)
        # dendritic bleeding at the edge
        tend = []
        for k in range(12):
            a = rng.uniform(0, math.tau)
            p0 = (C[0] + math.cos(a) * R * 0.6, C[1] + math.sin(a) * R * 0.6)
            p1 = (C[0] + math.cos(a) * R * rng.uniform(1.0, 1.4), C[1] + math.sin(a) * R * rng.uniform(1.0, 1.4))
            tend.append(streak_poly(p0, p1, rng.uniform(5, 11), 0.5))
        m |= c.polys(tend)
        c.paint(m, V_INK, order=0.5)
        c.paint(m & (rel < 0.5), V_DEEP, order=0.6)
        return c.pack()
    if name == "rot_scar":
        m, rel = blotch(c, C, R, rough=0.5, freq=4)
        c.paint(m, V_INK, order=0.5)
        blobs = [(C[0] + math.cos(a) * R * rng.uniform(0.1, 0.8), C[1] + math.sin(a) * R * rng.uniform(0.1, 0.8),
                  rng.uniform(6, 16)) for a in rng.uniform(0, math.tau, 9)]
        mb = c.ragged(c.dots(blobs), 1.5, 0.4) & m
        c.paint(mb, V_DEEP, order=0.6)
        c.paint(c.lines(cracks(c, C, R, rng, 4, w=2.0)) & m, V_BODY, order=0.3)
        return c.pack()
    if name == "crater":
        m, rel = blotch(c, C, R * 1.05, rough=0.18, freq=6)
        c.paint(m, np.where(rel < 0.62, V_INK, np.where(rel < 0.8, V_DEEP, V_INK)), order=0.5)
        # the raised rim lit on the far (top) side
        rim = m & (rel > 0.8) & (c.Y < C[1] - R * 0.2)
        c.paint(rim, V_BODY, order=0.6)
        return c.pack()
    # molten gashes: tapered radial gashes from the centre (Mountainfall)
    gashes, cores = [], []
    for k in range(7):
        a = k * math.tau / 7 + rng.uniform(-0.25, 0.25)
        L = R * 1.3 * rng.uniform(0.75, 1.0)
        pts = bolt_points((C[0] + math.cos(a) * R * 0.15, C[1] + math.sin(a) * R * 0.15),
                          (C[0] + math.cos(a) * L, C[1] + math.sin(a) * L), rng, 0.08, 3)
        n = len(pts)
        wid = [9 * (1 - j / (n - 1)) ** 0.8 + 0.6 for j in range(n)]
        gashes.append(tapered_path(pts, [w * 2.0 for w in wid]))
        cores.append(tapered_path(pts, wid))
    c.paint(c.polys(gashes), V_INK, order=0.6)
    mc = c.polys(cores)
    c.paint(mc, V_BODY, order=0.4)
    c.paint(mc & (r < R * 0.7), V_LIGHT, order=0.3)
    c.paint(c.dots([(C[0], C[1], R * 0.22)]), V_INK, order=0.7)
    return c.pack(ero=np.clip(1 - r / (R * 1.4), 0.02, 1) * 0.8 + 0.2 * c.nz(c.X * 0.2, c.Y * 0.2))


def _call2(fn, args):
    return fn(*args)


def build():
    g = Atlas("vfx_glyphs", 4, 4, 256, 256, intended="sigils and god glyphs: decals under targets, turning "
              "Curse/Mark sigils, Binding Hex, boon pillars, Still Field dial")
    for k, cell in enumerate(pmap(glyph_cell, [(i, 2000) for i in range(16)])):
        g.put(k % 4, k // 4, cell)
    g.seq("glyph", 0, 16, pivot=(0.5, 0.5), names=GLYPHS, note="one sprite per cell, row-major")
    g.save()

    p = Atlas("vfx_pips", 4, 4, 128, 128, intended="status pips at head_top and pickup glyphs")
    for k, cell in enumerate(pmap(pip_cell, [(i, 2100) for i in range(16)])):
        p.put(k % 4, k // 4, cell)
    p.seq("pip", 0, 16, pivot=(0.5, 0.5), names=PIPS, note="one sprite per cell, row-major")
    p.save()

    d = Atlas("vfx_decals", 4, 4, 256, 256, intended="ground decals in a ring buffer (never bloom; <= 0.9 gain): "
              "the crack cores hold low B so they cool and vanish first")
    for k, cell in enumerate(pmap(decal_cell, [(i, 2200) for i in range(16)])):
        d.put(k % 4, k // 4, cell)
    d.seq("decal", 0, 16, pivot=(0.5, 0.5), names=DECALS, radius_in_cell=0.72, plane="ground",
          note="one sprite per cell, row-major")
    d.save()
    return [g, p, d]


if __name__ == "__main__":
    build()
