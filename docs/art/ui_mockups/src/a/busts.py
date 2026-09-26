"""Portrait busts (silhouette crests) for the hero medallion and party frames + a few extra glyphs.
Original shapes: each hero reads by silhouette alone (Valdris horned helm + pauldrons, Selene
circlet + storm orb, Kael hood + collar)."""
import math

import gm_icons as I


def b_valdris(g):
    S = g.S
    # broad layered pauldrons
    g.d.ellipse([-0.08 * S, 0.6 * S, 0.44 * S, 1.1 * S], fill=255)
    g.d.ellipse([0.56 * S, 0.6 * S, 1.08 * S, 1.1 * S], fill=255)
    g.rect(0.2, 0.8, 0.8, 1.0)
    g.arc(0.18, 0.86, 0.2, math.radians(200), math.radians(300), 0.03, fill=0)
    g.arc(0.18, 0.92, 0.2, math.radians(205), math.radians(295), 0.025, fill=0)
    g.arc(0.82, 0.86, 0.2, math.radians(240), math.radians(340), 0.03, fill=0)
    g.arc(0.82, 0.92, 0.2, math.radians(245), math.radians(335), 0.025, fill=0)
    # gorget
    g.poly([(0.35, 0.64), (0.65, 0.64), (0.72, 0.82), (0.28, 0.82)])
    g.rect(0.34, 0.72, 0.66, 0.745, 0)
    # great helm: domed, flat-faced
    g.d.chord([0.31 * S, 0.16 * S, 0.69 * S, 0.56 * S], 180, 360, fill=255)
    g.poly([(0.31, 0.36), (0.69, 0.36), (0.67, 0.68), (0.5, 0.72), (0.33, 0.68)])
    # sweeping horns
    g.bez((0.35, 0.36), (0.16, 0.36), (0.08, 0.26), (0.1, 0.06), 0.1, 0.012)
    g.bez((0.65, 0.36), (0.84, 0.36), (0.92, 0.26), (0.9, 0.06), 0.1, 0.012)
    # visor slit + breaths
    g.poly([(0.35, 0.44), (0.65, 0.44), (0.62, 0.49), (0.38, 0.49)], 0)
    for x in (0.44, 0.5, 0.56):
        g.rect(x - 0.011, 0.54, x + 0.011, 0.64, 0)
    # crest ridge
    g.rect(0.485, 0.16, 0.515, 0.44, 0)


def b_selene(g):
    g.poly([(0.22, 1.0), (0.3, 0.8), (0.42, 0.74), (0.58, 0.74), (0.7, 0.8), (0.78, 1.0)])
    g.rect(0.44, 0.62, 0.56, 0.78)
    g.d.ellipse([0.36 * g.S, 0.3 * g.S, 0.64 * g.S, 0.66 * g.S], fill=255)
    # flowing hair to one side
    g.bez((0.62, 0.34), (0.86, 0.36), (0.8, 0.6), (0.92, 0.8), 0.1, 0.02)
    g.bez((0.6, 0.4), (0.78, 0.5), (0.72, 0.66), (0.8, 0.84), 0.06, 0.01)
    # circlet with a bolt point
    g.arc(0.5, 0.48, 0.16, math.radians(200), math.radians(340), 0.03, fill=0)
    g.poly([(0.5, 0.2), (0.54, 0.3), (0.5, 0.33), (0.46, 0.3)])
    # storm orb
    g.circle(0.18, 0.36, 0.1)
    g.circle(0.18, 0.36, 0.05, 0)
    g.line([(0.12, 0.24), (0.2, 0.16)], 0.02)


def b_kael(g):
    g.poly([(0.1, 1.0), (0.24, 0.78), (0.5, 0.7), (0.76, 0.78), (0.9, 1.0)])
    # hood
    g.poly([(0.5, 0.14), (0.72, 0.4), (0.7, 0.72), (0.3, 0.72), (0.28, 0.4)])
    g.d.ellipse([0.36 * g.S, 0.36 * g.S, 0.64 * g.S, 0.74 * g.S], fill=0)
    # face shadow with two glints
    g.circle(0.44, 0.54, 0.025)
    g.circle(0.56, 0.54, 0.025)
    # collar clasp
    g.poly([(0.5, 0.78), (0.56, 0.84), (0.5, 0.9), (0.44, 0.84)], 0)
    # pistol grip over shoulder
    g.poly([(0.74, 0.62), (0.94, 0.56), (0.95, 0.62), (0.8, 0.68)])


def g_passive_static(g):
    I.g_storm(g)


def g_threat(g):  # a flame pip for threat
    g.flame(0.5, 0.95, 0.5, 0.9)


I.GLYPHS.update({"bust_valdris": b_valdris, "bust_selene": b_selene, "bust_kael": b_kael, "threat": g_threat})
