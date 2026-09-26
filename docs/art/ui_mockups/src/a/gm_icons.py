"""GILDED MYTHIC icon set: original silhouette-first vector glyphs for GODFORGE.

Each glyph is drawn into an L mask in unit space (0..1), supersampled. `render_icon` turns a mask
into the house style: a 2-3 value enamel fill (ivory light -> category tint), ink outline, and an
optional thin gilt rim. Icons are designed to read at 20-24 px (markers) and shine at 64-96 px.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import gmkit as K
from gmkit import SS, bezier, taper_stroke, spiral


class G:
    """Unit-space drawing helper on a supersampled mask."""

    def __init__(self, size: int):
        self.size = size
        self.S = size * SS * 2  # extra 2x for glyph crispness
        self.m = Image.new("L", (self.S, self.S), 0)
        self.d = ImageDraw.Draw(self.m)

    def p(self, x, y):
        return (x * self.S, y * self.S)

    def poly(self, pts, fill=255):
        self.d.polygon([self.p(*q) for q in pts], fill=fill)

    def circle(self, cx, cy, r, fill=255):
        self.d.ellipse([(cx - r) * self.S, (cy - r) * self.S, (cx + r) * self.S, (cy + r) * self.S], fill=fill)

    def ring(self, cx, cy, r, w, fill=255):
        self.circle(cx, cy, r, fill)
        self.circle(cx, cy, r - w, 0 if fill else 255)

    def rect(self, x0, y0, x1, y1, fill=255, r=0.0):
        if r:
            self.d.rounded_rectangle([x0 * self.S, y0 * self.S, x1 * self.S, y1 * self.S], radius=r * self.S, fill=fill)
        else:
            self.d.rectangle([x0 * self.S, y0 * self.S, x1 * self.S, y1 * self.S], fill=fill)

    def line(self, pts, w, fill=255):
        pts = [self.p(*q) for q in pts]
        self.d.line(pts, fill=fill, width=max(1, int(w * self.S)), joint="curve")
        for q in (pts[0], pts[-1]):
            r = w * self.S / 2
            self.d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=fill)

    def taper(self, pts, w0, w1, fill=255, ease=1.0):
        taper_stroke(self.d, [self.p(*q) for q in pts], w0 * self.S / 2, w1 * self.S / 2, fill=fill, ease=ease)

    def bez(self, a, b, c, d, w0, w1=None, fill=255, n=60, ease=1.0):
        pts = bezier(a, b, c, d, n)
        self.taper(pts, w0, w1 if w1 is not None else w0, fill=fill, ease=ease)

    def arc(self, cx, cy, r, a0, a1, w, w1=None, fill=255, n=60):
        pts = [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        self.taper(pts, w, w1 if w1 is not None else w, fill=fill)

    def star(self, cx, cy, r0, r1, n, rot=-math.pi / 2, fill=255):
        pts = []
        for i in range(n * 2):
            r = r0 if i % 2 == 0 else r1
            a = rot + i * math.pi / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        self.poly(pts, fill)

    def flame(self, cx, by, w, h, fill=255, lean=0.0):
        # teardrop flame: base circle + tapering tip with a flick
        self.circle(cx, by - w * 0.5, w * 0.5, fill)
        self.poly([(cx - w * 0.5, by - w * 0.5), (cx + lean * h, by - h), (cx + w * 0.5, by - w * 0.5)], fill)
        self.bez((cx - w * 0.48, by - w * 0.55), (cx - w * 0.5, by - h * 0.7), (cx + lean * h - w * 0.1, by - h * 0.8),
                 (cx + lean * h, by - h), w * 0.25, 0.005, fill)

    def mask(self):
        return self.m.resize((self.size * SS, self.size * SS), Image.LANCZOS)


# ───────────────────────────── glyphs ─────────────────────────────
def g_anvil(g: G):
    g.poly([(0.12, 0.34), (0.8, 0.34), (0.92, 0.3), (0.8, 0.46), (0.62, 0.48), (0.6, 0.6), (0.72, 0.72),
            (0.74, 0.8), (0.26, 0.8), (0.28, 0.72), (0.4, 0.6), (0.38, 0.48), (0.24, 0.46)])
    g.bez((0.12, 0.34), (0.02, 0.36), (0.02, 0.44), (0.1, 0.45), 0.05, 0.02)  # horn curl
    g.rect(0.2, 0.84, 0.8, 0.9)
    # sparks
    g.star(0.5, 0.17, 0.09, 0.025, 4)
    g.star(0.28, 0.2, 0.045, 0.012, 4)
    g.star(0.72, 0.21, 0.045, 0.012, 4)


def g_skull_crown(g: G):  # Warlord
    g.circle(0.5, 0.52, 0.25)
    g.rect(0.36, 0.62, 0.64, 0.82, r=0.04)
    g.circle(0.4, 0.55, 0.075, 0)
    g.circle(0.6, 0.55, 0.075, 0)
    g.poly([(0.5, 0.63), (0.46, 0.71), (0.54, 0.71)], 0)
    for x in (0.42, 0.5, 0.58):
        g.rect(x - 0.012, 0.76, x + 0.012, 0.82, 0)
    # crown
    g.poly([(0.26, 0.34), (0.3, 0.12), (0.4, 0.26), (0.5, 0.06), (0.6, 0.26), (0.7, 0.12), (0.74, 0.34)])
    g.rect(0.26, 0.3, 0.74, 0.36, 0)


def g_fangs(g: G):  # Lair: a maw of fangs over skull stakes
    g.arc(0.5, 0.2, 0.42, math.radians(35), math.radians(145), 0.09)
    for x, h in ((0.24, 0.3), (0.37, 0.4), (0.5, 0.44), (0.63, 0.4), (0.76, 0.3)):
        g.poly([(x - 0.055, 0.5), (x, 0.5 + h * 0.8), (x + 0.055, 0.5)])
    g.arc(0.5, 0.95, 0.42, math.radians(-150), math.radians(-30), 0.07)


def g_shrine(g: G):  # altar with god flame
    g.flame(0.5, 0.52, 0.22, 0.44)
    g.flame(0.5, 0.5, 0.11, 0.24, fill=0)
    g.poly([(0.22, 0.56), (0.78, 0.56), (0.72, 0.64), (0.28, 0.64)])
    g.rect(0.34, 0.64, 0.66, 0.82)
    g.rect(0.24, 0.82, 0.76, 0.9)
    g.rect(0.41, 0.68, 0.59, 0.78, 0)


def g_chest(g: G):  # Reliquary
    g.rect(0.14, 0.44, 0.86, 0.84, r=0.03)
    g.d.chord([0.14 * g.S, 0.2 * g.S, 0.86 * g.S, 0.68 * g.S], 180, 360, fill=255)
    g.rect(0.14, 0.43, 0.86, 0.49, 0)
    g.rect(0.44, 0.38, 0.56, 0.58, 255)
    g.circle(0.5, 0.52, 0.025, 0)
    g.rect(0.2, 0.26, 0.26, 0.84, 0)
    g.rect(0.74, 0.26, 0.8, 0.84, 0)


def g_crystal(g: G):  # Vein
    g.poly([(0.5, 0.06), (0.62, 0.3), (0.58, 0.86), (0.42, 0.86), (0.38, 0.3)])
    g.poly([(0.26, 0.3), (0.36, 0.48), (0.36, 0.86), (0.2, 0.86), (0.16, 0.5)])
    g.poly([(0.76, 0.36), (0.84, 0.55), (0.8, 0.86), (0.64, 0.86), (0.66, 0.5)])
    g.line([(0.5, 0.1), (0.5, 0.84)], 0.02, 0)
    g.rect(0.1, 0.86, 0.9, 0.92)


def g_spring(g: G):  # basin + rising drop
    g.poly([(0.5, 0.06), (0.64, 0.3), (0.66, 0.38), (0.34, 0.38), (0.36, 0.3)])
    g.circle(0.5, 0.38, 0.16)
    g.circle(0.45, 0.36, 0.05, 0)
    g.d.chord([0.12 * g.S, 0.42 * g.S, 0.88 * g.S, 0.86 * g.S], 0, 180, fill=255)
    g.rect(0.1, 0.62, 0.9, 0.67)
    g.rect(0.4, 0.8, 0.6, 0.9)
    g.rect(0.28, 0.88, 0.72, 0.93)


def g_watchfire(g: G):  # pyre of logs + flame
    g.flame(0.5, 0.62, 0.3, 0.56, lean=0.02)
    g.flame(0.5, 0.6, 0.14, 0.3, fill=0)
    g.line([(0.16, 0.9), (0.84, 0.66)], 0.08)
    g.line([(0.16, 0.66), (0.84, 0.9)], 0.08)


def g_gate(g: G):  # arch with sealed door and seal sockets
    g.poly([(0.12, 0.92), (0.12, 0.4), (0.88, 0.4), (0.88, 0.92)])
    g.d.chord([0.12 * g.S, 0.1 * g.S, 0.88 * g.S, 0.72 * g.S], 180, 360, fill=255)
    g.poly([(0.26, 0.92), (0.26, 0.44), (0.74, 0.44), (0.74, 0.92)], 0)
    g.d.chord([0.26 * g.S, 0.24 * g.S, 0.74 * g.S, 0.66 * g.S], 180, 360, fill=0)
    g.star(0.5, 0.62, 0.13, 0.045, 4)
    for a in range(5):
        ang = math.pi + (a + 0.5) / 5 * math.pi
        g.circle(0.5 + math.cos(ang) * 0.31, 0.42 + math.sin(ang) * 0.27, 0.028, 0)


def g_godshard(g: G):
    g.poly([(0.5, 0.04), (0.74, 0.34), (0.62, 0.94), (0.38, 0.94), (0.26, 0.34)])
    g.line([(0.5, 0.06), (0.5, 0.92)], 0.03, 0)
    g.line([(0.27, 0.35), (0.5, 0.46), (0.73, 0.35)], 0.03, 0)


def g_ember(g: G):  # a glowing coal-lozenge with a flame lick
    g.poly([(0.5, 0.32), (0.86, 0.62), (0.5, 0.94), (0.14, 0.62)])
    g.flame(0.5, 0.52, 0.18, 0.5)
    g.poly([(0.5, 0.48), (0.7, 0.64), (0.5, 0.8), (0.3, 0.64)], 0)
    g.poly([(0.5, 0.56), (0.6, 0.64), (0.5, 0.72), (0.4, 0.64)])


def g_seal(g: G):  # a round seal stamped with an anvil
    g.ring(0.5, 0.5, 0.44, 0.08)
    g.star(0.5, 0.5, 0.33, 0.29, 16, fill=255)
    g.circle(0.5, 0.5, 0.26, 0)
    g.poly([(0.32, 0.44), (0.66, 0.44), (0.72, 0.41), (0.66, 0.5), (0.57, 0.51), (0.56, 0.58), (0.62, 0.64),
            (0.38, 0.64), (0.44, 0.58), (0.43, 0.51), (0.35, 0.5)])


def g_core(g: G):  # a burning heart-orb held by claws
    g.circle(0.5, 0.5, 0.2)
    g.circle(0.44, 0.44, 0.06, 0)
    for i in range(8):
        a = i * math.pi / 4
        g.poly([(0.5 + math.cos(a - 0.12) * 0.26, 0.5 + math.sin(a - 0.12) * 0.26),
                (0.5 + math.cos(a) * 0.44, 0.5 + math.sin(a) * 0.44),
                (0.5 + math.cos(a + 0.12) * 0.26, 0.5 + math.sin(a + 0.12) * 0.26)])


def g_gear(g: G):  # Mechanism
    g.star(0.5, 0.5, 0.44, 0.34, 8, rot=0.0)
    g.circle(0.5, 0.5, 0.36)
    g.circle(0.5, 0.5, 0.16, 0)
    g.circle(0.5, 0.5, 0.07)
    for i in range(3):
        a = i * 2 * math.pi / 3 + math.pi / 2
        g.line([(0.5, 0.5), (0.5 + math.cos(a) * 0.16, 0.5 + math.sin(a) * 0.16)], 0.05)


def g_relic(g: G):  # amulet: chain loop + eye pendant
    g.arc(0.5, 0.2, 0.18, math.pi, 2 * math.pi, 0.05)
    g.line([(0.32, 0.2), (0.4, 0.38)], 0.05)
    g.line([(0.68, 0.2), (0.6, 0.38)], 0.05)
    g.poly([(0.5, 0.34), (0.8, 0.58), (0.5, 0.95), (0.2, 0.58)])
    g.d.ellipse([0.33 * g.S, 0.5 * g.S, 0.67 * g.S, 0.72 * g.S], fill=0)
    g.circle(0.5, 0.61, 0.07)


def g_sigil(g: G):  # a seal-ring with a rune
    g.ring(0.5, 0.52, 0.4, 0.09)
    g.poly([(0.5, 0.2), (0.72, 0.52), (0.5, 0.84), (0.28, 0.52)])
    g.poly([(0.5, 0.3), (0.64, 0.52), (0.5, 0.74), (0.36, 0.52)], 0)
    g.line([(0.5, 0.36), (0.5, 0.68)], 0.05)
    g.line([(0.42, 0.46), (0.58, 0.46)], 0.05)


# elements
def g_kinetic(g: G):  # three impact chevrons + slug
    for i, y in enumerate((0.24, 0.46, 0.68)):
        g.poly([(0.18, y), (0.5, y + 0.14), (0.82, y), (0.82, y + 0.1), (0.5, y + 0.24), (0.18, y + 0.1)])


def g_flame(g: G):
    g.flame(0.5, 0.92, 0.5, 0.86, lean=0.03)
    g.flame(0.52, 0.9, 0.24, 0.42, fill=0, lean=-0.02)


def g_storm(g: G):
    g.poly([(0.58, 0.04), (0.2, 0.56), (0.46, 0.56), (0.36, 0.96), (0.8, 0.4), (0.54, 0.4), (0.7, 0.04)])


def g_void(g: G):  # eclipse spiral
    g.ring(0.5, 0.5, 0.42, 0.08)
    pts = spiral(0.5, 0.5, 0.3, 0.02, 1.1, 0.0, 80)
    g.taper(pts, 0.1, 0.03)
    g.circle(0.5, 0.5, 0.06)


def g_plague(g: G):  # drop with bubbles
    g.poly([(0.5, 0.06), (0.74, 0.5), (0.26, 0.5)])
    g.circle(0.5, 0.62, 0.27)
    g.circle(0.42, 0.62, 0.07, 0)
    g.circle(0.6, 0.72, 0.05, 0)
    g.circle(0.58, 0.5, 0.035, 0)


def g_radiant(g: G):
    g.star(0.5, 0.5, 0.46, 0.2, 8)
    g.circle(0.5, 0.5, 0.2)
    g.circle(0.5, 0.5, 0.11, 0)


# statuses
def g_burn(g: G):
    g_flame(g)


def g_shock(g: G):
    g_storm(g)


def g_curse(g: G):  # a hex eye
    g.d.chord([0.08 * g.S, 0.28 * g.S, 0.92 * g.S, 0.72 * g.S], 0, 360, fill=255)
    g.circle(0.5, 0.5, 0.17, 0)
    g.circle(0.5, 0.5, 0.09)
    for x in (0.26, 0.5, 0.74):
        g.line([(x, 0.12), (x, 0.22)], 0.05)


def g_root(g: G):
    g.line([(0.5, 0.08), (0.5, 0.58)], 0.1)
    g.bez((0.5, 0.5), (0.4, 0.7), (0.2, 0.7), (0.12, 0.92), 0.08, 0.02)
    g.bez((0.5, 0.5), (0.6, 0.7), (0.8, 0.7), (0.88, 0.92), 0.08, 0.02)
    g.bez((0.5, 0.56), (0.5, 0.75), (0.46, 0.85), (0.5, 0.95), 0.07, 0.02)


def g_bleed(g: G):
    for x, y, s in ((0.34, 0.2, 1.0), (0.66, 0.36, 0.8), (0.42, 0.6, 0.7)):
        g.poly([(x, y - 0.12 * s), (x + 0.12 * s, y + 0.1 * s), (x - 0.12 * s, y + 0.1 * s)])
        g.circle(x, y + 0.12 * s, 0.13 * s)


def g_mark(g: G):  # crosshair lozenge
    g.poly([(0.5, 0.06), (0.94, 0.5), (0.5, 0.94), (0.06, 0.5)])
    g.poly([(0.5, 0.22), (0.78, 0.5), (0.5, 0.78), (0.22, 0.5)], 0)
    g.circle(0.5, 0.5, 0.08)


def g_doom(g: G):  # hourglass skull tally
    g.poly([(0.22, 0.08), (0.78, 0.08), (0.56, 0.5), (0.78, 0.92), (0.22, 0.92), (0.44, 0.5)])
    g.poly([(0.32, 0.16), (0.68, 0.16), (0.5, 0.44)], 0)
    g.poly([(0.5, 0.6), (0.68, 0.84), (0.32, 0.84)], 0)
    g.poly([(0.5, 0.68), (0.6, 0.84), (0.4, 0.84)])


# valdris kit
def g_bulwark_slam(g: G):  # fist crashing into a raised wall with shock arcs
    g.rect(0.1, 0.62, 0.9, 0.72)  # ground/barricade top
    for x in (0.14, 0.38, 0.62):
        g.rect(x, 0.72, x + 0.22, 0.9)
    g.poly([(0.34, 0.1), (0.66, 0.1), (0.7, 0.3), (0.66, 0.5), (0.34, 0.5), (0.3, 0.3)])  # fist block
    for x in (0.4, 0.5, 0.6):
        g.line([(x, 0.14), (x, 0.3)], 0.025, 0)
    g.rect(0.3, 0.3, 0.7, 0.34, 0)
    g.arc(0.5, 0.62, 0.34, math.radians(200), math.radians(245), 0.05, 0.01)
    g.arc(0.5, 0.62, 0.34, math.radians(295), math.radians(340), 0.01, 0.05)
    g.arc(0.5, 0.62, 0.44, math.radians(205), math.radians(235), 0.035, 0.008)
    g.arc(0.5, 0.62, 0.44, math.radians(305), math.radians(335), 0.008, 0.035)


def g_siege_stance(g: G):  # a planted tower-shield with rising fire-rate chevrons
    g.poly([(0.2, 0.3), (0.5, 0.2), (0.8, 0.3), (0.76, 0.62), (0.5, 0.9), (0.24, 0.62)])
    g.poly([(0.3, 0.36), (0.5, 0.3), (0.7, 0.36), (0.67, 0.6), (0.5, 0.78), (0.33, 0.6)], 0)
    for y in (0.42, 0.56):
        g.poly([(0.38, y + 0.08), (0.5, y), (0.62, y + 0.08), (0.62, y + 0.13), (0.5, y + 0.05), (0.38, y + 0.13)])
    g.line([(0.08, 0.94), (0.92, 0.94)], 0.05)
    g.line([(0.2, 0.9), (0.14, 0.96)], 0.03)
    g.line([(0.8, 0.9), (0.86, 0.96)], 0.03)


def g_mountainfall(g: G):  # a colossal peak with a falling boulder and impact
    g.poly([(0.04, 0.9), (0.36, 0.36), (0.48, 0.52), (0.62, 0.28), (0.96, 0.9)])
    g.poly([(0.56, 0.38), (0.62, 0.3), (0.7, 0.44), (0.62, 0.42)], 0)
    g.circle(0.26, 0.16, 0.11)
    g.circle(0.23, 0.13, 0.03, 0)
    g.line([(0.36, 0.05), (0.3, 0.1)], 0.025)
    g.line([(0.4, 0.14), (0.34, 0.17)], 0.025)
    g.rect(0.0, 0.9, 1.0, 0.95)


def g_reforged_flesh(g: G):  # passive: armour plates over a heart
    g.poly([(0.5, 0.9), (0.14, 0.5), (0.14, 0.3), (0.3, 0.16), (0.5, 0.28), (0.7, 0.16), (0.86, 0.3), (0.86, 0.5)])
    g.poly([(0.5, 0.76), (0.26, 0.5), (0.26, 0.34), (0.34, 0.28), (0.5, 0.38), (0.66, 0.28), (0.74, 0.34), (0.74, 0.5)], 0)
    for y in (0.42, 0.54):
        g.rect(0.3, y, 0.7, y + 0.07)


def g_cannon(g: G):  # Colossus Cannon chassis
    g.poly([(0.08, 0.58), (0.12, 0.44), (0.62, 0.36), (0.66, 0.5), (0.2, 0.66)])
    g.rect(0.6, 0.3, 0.92, 0.5, r=0.02)
    g.rect(0.9, 0.28, 0.96, 0.52)
    g.circle(0.94, 0.4, 0.05, 0)
    g.circle(0.34, 0.66, 0.14)
    g.circle(0.34, 0.66, 0.06, 0)
    g.rect(0.66, 0.34, 0.72, 0.46, 0)
    g.rect(0.76, 0.34, 0.8, 0.46, 0)


def g_crucible(g: G):  # Team Overdrive: a tipped crucible pouring molten metal
    g.poly([(0.14, 0.2), (0.62, 0.2), (0.56, 0.62), (0.2, 0.62)])
    g.rect(0.1, 0.16, 0.66, 0.22)
    g.poly([(0.6, 0.22), (0.78, 0.3), (0.62, 0.3)])
    g.bez((0.74, 0.3), (0.82, 0.44), (0.76, 0.66), (0.8, 0.88), 0.07, 0.035)
    g.d.chord([0.62 * g.S, 0.8 * g.S, 0.98 * g.S, 1.0 * g.S], 180, 360, fill=255)
    g.poly([(0.24, 0.3), (0.52, 0.3), (0.5, 0.44), (0.26, 0.44)], 0)
    for i in range(3):
        x = 0.1 + i * 0.06
        g.line([(x, 0.66), (x - 0.03, 0.9)], 0.03)


def g_aim_auto(g: G):
    g.ring(0.5, 0.5, 0.4, 0.07)
    for a in range(4):
        ang = a * math.pi / 2
        g.line([(0.5 + math.cos(ang) * 0.26, 0.5 + math.sin(ang) * 0.26),
                (0.5 + math.cos(ang) * 0.48, 0.5 + math.sin(ang) * 0.48)], 0.07)
    g.poly([(0.5, 0.33), (0.62, 0.62), (0.56, 0.62), (0.53, 0.54), (0.47, 0.54), (0.44, 0.62), (0.38, 0.62)])
    g.poly([(0.5, 0.42), (0.52, 0.49), (0.48, 0.49)], 0)


def g_aim_assisted(g: G):
    g.poly([(0.5, 0.52), (0.1, 0.1), (0.9, 0.1)])
    g.poly([(0.5, 0.42), (0.22, 0.16), (0.78, 0.16)], 0)
    g.ring(0.5, 0.72, 0.18, 0.06)
    g.circle(0.5, 0.72, 0.05)


def g_aim_manual(g: G):
    g.ring(0.5, 0.5, 0.3, 0.05)
    for a in range(4):
        ang = a * math.pi / 2
        g.line([(0.5 + math.cos(ang) * 0.14, 0.5 + math.sin(ang) * 0.14),
                (0.5 + math.cos(ang) * 0.46, 0.5 + math.sin(ang) * 0.46)], 0.045)
    g.circle(0.5, 0.5, 0.045)


def g_skull(g: G):  # downed
    g.circle(0.5, 0.42, 0.3)
    g.rect(0.34, 0.56, 0.66, 0.84, r=0.05)
    g.circle(0.38, 0.46, 0.09, 0)
    g.circle(0.62, 0.46, 0.09, 0)
    g.poly([(0.5, 0.56), (0.45, 0.66), (0.55, 0.66)], 0)
    for x in (0.42, 0.5, 0.58):
        g.rect(x - 0.013, 0.74, x + 0.013, 0.84, 0)


def g_wing(g: G):  # dash pip glyph
    for i, (y, l) in enumerate(((0.3, 0.8), (0.5, 0.66), (0.7, 0.5))):
        g.bez((0.14, y), (0.4, y - 0.12), (0.7, y - 0.12), (0.14 + l, y - 0.02), 0.09, 0.01)


def g_reroll(g: G):
    g.arc(0.5, 0.5, 0.32, math.radians(200), math.radians(430), 0.1, 0.1)
    g.poly([(0.66, 0.02), (0.9, 0.24), (0.6, 0.32)])


def g_fuse(g: G):  # two lozenges merging into one
    g.poly([(0.3, 0.2), (0.48, 0.4), (0.3, 0.6), (0.12, 0.4)])
    g.poly([(0.7, 0.2), (0.88, 0.4), (0.7, 0.6), (0.52, 0.4)])
    g.poly([(0.5, 0.5), (0.72, 0.72), (0.5, 0.96), (0.28, 0.72)])


def g_salvage(g: G):  # hammer breaking a shard
    g.rect(0.18, 0.12, 0.62, 0.3, r=0.03)
    g.line([(0.4, 0.3), (0.72, 0.74)], 0.08)
    g.poly([(0.08, 0.66), (0.3, 0.52), (0.36, 0.76), (0.18, 0.92)])
    g.star(0.46, 0.56, 0.08, 0.02, 4)


def g_equip(g: G):  # arrow into socket
    g.poly([(0.5, 0.06), (0.8, 0.36), (0.6, 0.36), (0.6, 0.6), (0.4, 0.6), (0.4, 0.36), (0.2, 0.36)])
    g.poly([(0.5, 0.64), (0.8, 0.8), (0.5, 0.96), (0.2, 0.8)])
    g.poly([(0.5, 0.72), (0.64, 0.8), (0.5, 0.88), (0.36, 0.8)], 0)


def g_lock(g: G):
    g.arc(0.5, 0.42, 0.2, math.pi, 2 * math.pi, 0.08)
    g.line([(0.3, 0.42), (0.3, 0.5)], 0.08)
    g.line([(0.7, 0.42), (0.7, 0.5)], 0.08)
    g.rect(0.2, 0.5, 0.8, 0.9, r=0.05)
    g.circle(0.5, 0.66, 0.06, 0)
    g.rect(0.47, 0.66, 0.53, 0.8, 0)


def g_arrow(g: G):  # off-screen pointer (points up)
    g.poly([(0.5, 0.02), (0.92, 0.62), (0.5, 0.44), (0.08, 0.62)])


# god sigils (original emblems)
def g_pyra(g: G):  # a crowned flame with two wrath-horns
    g.flame(0.5, 0.9, 0.46, 0.84)
    g.flame(0.5, 0.86, 0.2, 0.4, fill=0)
    g.bez((0.3, 0.7), (0.06, 0.6), (0.06, 0.3), (0.16, 0.14), 0.08, 0.01)
    g.bez((0.7, 0.7), (0.94, 0.6), (0.94, 0.3), (0.84, 0.14), 0.08, 0.01)


def g_zephyros(g: G):  # a wind-eye: three gust curls around a bolt
    g_storm_small = [(0.56, 0.18), (0.36, 0.52), (0.5, 0.52), (0.42, 0.84), (0.66, 0.44), (0.52, 0.44), (0.62, 0.18)]
    g.poly(g_storm_small)
    for r, a0 in ((0.4, 200), (0.34, 20)):
        g.arc(0.5, 0.5, r, math.radians(a0), math.radians(a0 + 120), 0.07, 0.01)
    g.arc(0.5, 0.5, 0.46, math.radians(110), math.radians(170), 0.01, 0.06)


def g_nyctia(g: G):  # crescent moon with a veiled dagger
    g.circle(0.46, 0.5, 0.4)
    g.circle(0.6, 0.42, 0.34, 0)
    g.poly([(0.68, 0.18), (0.74, 0.18), (0.74, 0.7), (0.71, 0.84), (0.68, 0.7)])
    g.rect(0.6, 0.62, 0.82, 0.66)
    g.star(0.28, 0.24, 0.06, 0.015, 4)


GLYPHS = {
    "anvil": g_anvil, "warlord": g_skull_crown, "lair": g_fangs, "shrine": g_shrine, "reliquary": g_chest,
    "vein": g_crystal, "spring": g_spring, "watchfire": g_watchfire, "gate": g_gate,
    "godshard": g_godshard, "ember": g_ember, "seal": g_seal,
    "core": g_core, "mechanism": g_gear, "relic": g_relic, "sigil": g_sigil,
    "kinetic": g_kinetic, "flame": g_flame, "storm": g_storm, "void": g_void, "plague": g_plague,
    "radiant": g_radiant,
    "burn": g_burn, "shock": g_shock, "curse": g_curse, "root": g_root, "bleed": g_bleed, "mark": g_mark,
    "doom": g_doom,
    "bulwark_slam": g_bulwark_slam, "siege_stance": g_siege_stance, "mountainfall": g_mountainfall,
    "reforged_flesh": g_reforged_flesh, "cannon": g_cannon, "crucible": g_crucible,
    "aim_auto": g_aim_auto, "aim_assisted": g_aim_assisted, "aim_manual": g_aim_manual,
    "skull": g_skull, "wing": g_wing, "reroll": g_reroll, "fuse": g_fuse, "salvage": g_salvage,
    "equip": g_equip, "lock": g_lock, "arrow": g_arrow,
    "pyra": g_pyra, "zephyros": g_zephyros, "nyctia": g_nyctia,
}


def glyph_mask(name: str, size: int) -> Image.Image:
    g = G(size)
    GLYPHS[name](g)
    return g.mask()


def render_icon(name: str, size: int, tint: str = "#E6CFA0", style: str = "enamel", outline: float = 1.6,
                rim: bool = False, light: str = "#FFF7E6", dim: float = 1.0, glow_color: str | None = None,
                glow_amt: float = 0.0, pad: float = 0.12) -> Image.Image:
    """Render a glyph in house style. size = final px of the icon box (glyph drawn inside with pad)."""
    inner = max(4, int(round(size * (1 - 2 * pad))))
    m = glyph_mask(name, inner)
    S = size * SS
    full = Image.new("L", (S, S), 0)
    off = (S - inner * SS) // 2
    full.paste(m, (off, off))
    arr = np.asarray(full, np.float32) / 255.0
    h, w = arr.shape
    ty = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    if style == "enamel":
        col = K.ramp(ty, [(0.0, light), (0.45, K.mix(light, tint, 0.55)), (1.0, K.mix(tint, "#1A0F08", 0.35))])
    elif style == "gold":
        sh = K.shade_metal(arr, bevel=0.035 * S, stops=K.GOLD_RAMP, rough=0.02, base=0.2, gain=0.75)
        col = sh[..., :3]
    elif style == "flat":
        col = np.ones((h, w, 3), np.float32) * np.array(K.rgb(tint), np.float32)
    else:
        col = K.ramp(ty, [(0.0, light), (1.0, tint)])
    col = col * dim
    out = np.dstack([col, arr * 255.0])
    img = K.to_img(out)
    # ink outline
    if outline > 0:
        om = full.filter(ImageFilter.MaxFilter(int(outline * SS) * 2 + 1))
        o = Image.new("RGBA", (S, S), K.rgba(K.TOK["ink"], 0.95))
        o.putalpha(om)
        o.alpha_composite(img)
        img = o
        if rim:
            rm = om.filter(ImageFilter.MaxFilter(int(1.0 * SS) * 2 + 1))
            ring = ImageChops.subtract(rm, om)
            r_img = K.to_img(K.shade_metal(np.asarray(ring, np.float32) / 255.0, bevel=0.6 * SS, rough=0.0))
            r_img.alpha_composite(img)
            img = r_img
    out = K.down(img, size, size)
    if glow_color and glow_amt > 0:
        g = K.blank(size * 2, size * 2)
        K.glow(g, out, (size // 2, size // 2), glow_color, blur=size * 0.18, opacity=glow_amt, spread=1)
        g.alpha_composite(out, (size // 2, size // 2))
        return g
    return out
