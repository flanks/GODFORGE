"""Remaining god sigils (original emblems) + a few UI glyphs used by the boards."""
import math

import gm_icons as I


def g_aeon(g):  # a ring-dial with two hands and an hourglass pip
    g.ring(0.5, 0.5, 0.44, 0.07)
    for k in range(12):
        a = k * math.pi / 6
        r0 = 0.3 if k % 3 == 0 else 0.33
        g.line([(0.5 + math.cos(a) * r0, 0.5 + math.sin(a) * r0), (0.5 + math.cos(a) * 0.36, 0.5 + math.sin(a) * 0.36)], 0.035)
    g.line([(0.5, 0.5), (0.5, 0.24)], 0.06)
    g.line([(0.5, 0.5), (0.68, 0.6)], 0.06)
    g.circle(0.5, 0.5, 0.06)


def g_gaiaa(g):  # a faceted heart-stone with a blood drop and roots
    g.poly([(0.5, 0.08), (0.84, 0.3), (0.78, 0.66), (0.5, 0.86), (0.22, 0.66), (0.16, 0.3)])
    g.poly([(0.5, 0.3), (0.62, 0.5), (0.5, 0.66), (0.38, 0.5)], 0)
    g.poly([(0.5, 0.4), (0.56, 0.52), (0.5, 0.6), (0.44, 0.52)])
    g.bez((0.4, 0.8), (0.34, 0.9), (0.24, 0.92), (0.16, 0.98), 0.05, 0.01)
    g.bez((0.6, 0.8), (0.66, 0.9), (0.76, 0.92), (0.84, 0.98), 0.05, 0.01)


def g_morwenn(g):  # a curling wave with a falling drop
    g.arc(0.46, 0.56, 0.3, math.radians(170), math.radians(400), 0.12, 0.03)
    g.bez((0.08, 0.72), (0.3, 0.9), (0.7, 0.9), (0.94, 0.7), 0.08, 0.02)
    g.poly([(0.74, 0.08), (0.84, 0.26), (0.64, 0.26)])
    g.circle(0.74, 0.3, 0.1)


def g_seraphel(g):  # a halo over balanced scales
    g.ring(0.5, 0.16, 0.14, 0.05)
    g.line([(0.5, 0.3), (0.5, 0.86)], 0.06)
    g.line([(0.16, 0.42), (0.84, 0.42)], 0.05)
    for x in (0.2, 0.8):
        g.line([(x, 0.42), (x - 0.1, 0.66)], 0.025)
        g.line([(x, 0.42), (x + 0.1, 0.66)], 0.025)
        g.d.chord([(x - 0.14) * g.S, 0.56 * g.S, (x + 0.14) * g.S, 0.78 * g.S], 0, 180, fill=255)
    g.rect(0.34, 0.86, 0.66, 0.92)


def g_umbra_rex(g):  # a broken crown over a closed eye
    g.poly([(0.14, 0.62), (0.2, 0.22), (0.34, 0.44), (0.5, 0.14), (0.62, 0.4), (0.7, 0.3), (0.8, 0.46), (0.86, 0.22),
            (0.86, 0.62)])
    g.line([(0.58, 0.14), (0.52, 0.34), (0.6, 0.44), (0.54, 0.62)], 0.035, 0)
    g.arc(0.5, 0.64, 0.26, math.radians(20), math.radians(160), 0.06)
    g.line([(0.3, 0.84), (0.26, 0.92)], 0.03)
    g.line([(0.5, 0.9), (0.5, 0.98)], 0.03)
    g.line([(0.7, 0.84), (0.74, 0.92)], 0.03)


def g_infinity(g):
    for cx in (0.3, 0.7):
        g.ring(cx, 0.5, 0.2, 0.08)
    g.line([(0.42, 0.4), (0.58, 0.6)], 0.08)
    g.line([(0.42, 0.6), (0.58, 0.4)], 0.08)


def g_revive(g):  # soul-tether: a hand-flame
    g.flame(0.5, 0.9, 0.36, 0.7)
    g.circle(0.5, 0.62, 0.1, 0)
    g.arc(0.5, 0.62, 0.36, math.radians(200), math.radians(340), 0.05, 0.01)


I.GLYPHS.update({"aeon": g_aeon, "gaiaa": g_gaiaa, "morwenn": g_morwenn, "seraphel": g_seraphel, "umbra_rex": g_umbra_rex,
                 "infinity": g_infinity, "revive": g_revive})
