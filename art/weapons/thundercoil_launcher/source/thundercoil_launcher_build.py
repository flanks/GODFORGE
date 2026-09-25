"""Thundercoil Launcher - Selene's signature storm launcher, built end to end from code with gf_assets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P art/weapons/thundercoil_launcher/source/thundercoil_launcher_build.py -- [--size 1024] [--no-review]

(tools/blender/gf_assets/weapons/thundercoil_launcher.py is a shim that runs this file.)

Content row (content/sheets/chassis.csv): thundercoil_launcher, Storm, style Orb, auto fire 3.5/s, damage 16,
speed 22, range 14, splash radius 1.0 at 40 %, tags "storm; splash; selene" - "Coiled lightning orbs that
crackle on impact." Wielder (characters.csv): Selene, the Stormcaller, a glass cannon ("Lightning in
human shape"), colour #6FE3FF.

Design (docs/art/WEAPONS.md section 5: family HEAVY/SPLASH, secondary tag storm = coils):
  * the brief asks for SLENDER and ELEGANT, so the LUMP verb is carried by ONE mass only: a storm-glass
    orb (0.20 m across; with its cups 0.25 m, a fifth of the length) sitting in the breech between the
    hands, set in two small brass cups whose rims open into five calyx leaves each. Everything else is
    thin: a smoked-bone swan-neck skeleton stock with a dark bronze crescent butt (Selene = the moon), a
    slim dark-iron receiver with a copper lightning inlay, a copper coil pack on the neck, a wooden
    forestock sleeve, a tapering copper induction coil, and a round emitter muzzle (a copper halo ring +
    three thick forward-swept conductor prongs with blunt glowing electrode tips): the wide round muzzle
    of the splash family, forked like a conductor;
  * value rhythm (checked at 1x in the 55 deg camera): mid smoked-bone stock falling off to a dark bronze
    butt -> dark iron receiver / dark wood grip -> the glowing orb in bright brass (the lead) -> dark
    sleeve -> copper coil -> copper halo, white-hot prong tips and a glowing bore where the orbs leave;
  * Storm #3FD8FF lives in the EMISSIVE only: the orb's plasma wisps and crackle veins, the bore, the
    front half of each prong (about 18 % of the surface). Base colour under glows is pale steel-white,
    never cyan;
  * rev 2 (art review 7/10): the pale bone stock was the largest light shape and pulled the eye to the
    back at 1x -> darkened one value step with a fall-off toward the butt, bronze crescent, 4 cm shorter;
    the needle tines were 1-2 px at 1x -> longer, ~60 % thicker, wider, blunt glowing tips (same tris);
  * palette: the warm metals of the player's arsenal (copper, bone-brass, dark iron, dark wood, bone) +
    a dark slate storm-glass.

Grip frame (docs/art/WEAPONS.md section 2): origin = palm centre of the right hand on the pistol grip,
+Y = barrel, +Z = up, +X = the weapon's right. Bore axis 0.10 m above the palm.
Outputs: assets/models/weapons/thundercoil_launcher.glb (+ .meta.json), art/weapons/thundercoil_launcher/
{source/*.blend, textures/*.png, reports/*.png, status.json}.

Built on tools/blender/gf_assets (toolkit by the gf_assets stage; the painter pass order here copies
gfa_paint.paint_asset so the glass can get its own plasma pass). Helix / coil sweeps follow the
tube-sweep idea of gfa_model.tube (itself adapted from Ashen Covenant tools/blender/ac_env_props).
"""
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender", "gf_assets"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402

KEY, KIND, TIER = "thundercoil_launcher", "weapon", "two_handed"
AX = 0.10                         # bore axis height above the palm centre (m)
CH_Y, CH_A, CH_R = 0.27, 0.108, 0.102   # storm-glass orb: centre y, half length (along Y), radius
CUP_LIP = 0.077                   # the brass cups hold the orb up to |y - CH_Y| = CUP_LIP
NECK = (0.098, 0.168)             # rear neck (iron core) wound with the copper coil pack
SLEEVE = (0.392, 0.490)           # wooden forestock sleeve (left hand)
COIL = (0.502, 0.582)             # barrel induction coil (tapering)
HALO_Y, HALO_R = 0.630, 0.060     # copper halo ring at the muzzle
MUZZLE_Y = 0.634                  # bore exit (the muzzle socket)
TINE_TIP_Y = 0.800                # rev 2: 0.762 -> 0.800, the prongs are longer, thicker and splay wider
TINE_GLOW_Y = 0.712               # the tines glow from here to the tip (rev 2: was the last ~2 cm only)
STOCK_CC_Y = -0.388               # crescent-butt arc centre (rev 2: -0.426 -> -0.388, a shorter stock)
GRIP_L = (0.0, 0.441, AX - 0.048)  # palm centre of the left hand under the sleeve
CORE = (0.0, CH_Y, AX)            # the orb's plasma core (glow_core)

ZONES = ["iron", "brass", "bronze", "copper", "coil", "tine", "wood", "bone", "glass", "glow_bore"]
# rev 2 (art review): the bone stock was the largest light shape and pulled the eye to the back at 1x.
# It is now smoked bone one value step darker (#D2C3A5 -> #9A7F5C) that also falls off toward the butt,
# and the crescent is dark bronze instead of bright brass: the orb and the muzzle lead the read.
BONE = "#9A7F5C"
PALETTE = [  # (name, hex) for the review sheet
    ("smoked bone", BONE), ("wood", "#45282A"), ("iron", "#2D2A38"), ("brass", "#C79E55"), ("bronze", "#8A6638"),
    ("copper", "#C0673A"), ("storm glass", "#18202E"), ("glow rim", "#0E4E7E"), ("storm", "#3FD8FF"),
    ("core", "#F2FFFF"),
]

# glass colours (sRGB)
GLASS_DARK = "#18202E"
GLASS_MID = "#2A3B54"
GLASS_EDGE = "#3A4E68"
GLASS_PALE = "#DCEAF0"
STORM = "#3FD8FF"
STORM_DEEP = "#0E4E7E"
STORM_CORE = "#F2FFFF"


# ---- geometry helpers ---------------------------------------------------------------------------------------

def radial(ang_deg, r, y):
    """Point at angle ang (0 = weapon right +X, 90 = up) and radius r around the bore axis, at y."""
    a = math.radians(ang_deg)
    return Vector((r * math.cos(a), y, AX + r * math.sin(a)))


def glass_radius(y):
    t = (y - CH_Y) / CH_A
    return CH_R * math.sqrt(max(0.0, 1.0 - t * t))


def helix(y0, y1, turns, radius_fn, per_turn=12, phase=0.0):
    """Centre-line of a coil around the bore axis from y0 to y1. radius_fn(y) -> distance from the axis."""
    n = max(4, int(round(turns * per_turn)))
    pts = []
    for i in range(n + 1):
        s = i / n
        y = y0 + (y1 - y0) * s
        pts.append(radial(math.degrees(phase + 2 * math.pi * turns * s), radius_fn(y), y))
    return pts


def lathe_y(profile, sides=16, cap=False):
    """Lathe around the bore axis: profile = [(radius, y), ...]."""
    bm = M.lathe(profile, sides=sides, cap=cap)
    M.xform(bm, rot=(-90, 0, 0))       # lathe height (Z) -> +Y
    M.xform(bm, loc=(0, 0, AX))
    return bm


def coil(a, y0, y1, turns, core_r0, core_r1, wire, per_turn, name):
    """An iron former (cone frustum) wound with a copper wire helix."""
    core = M.cylinder(core_r0, y1 - y0 + 0.006, sides=10, radius_top=core_r1, axis="Y")
    M.xform(core, loc=(0, (y0 + y1) / 2, AX))
    a.add(core, "iron", name=name + "_core", shading="smooth")

    def core_r(y):
        return core_r0 + (core_r1 - core_r0) * (y - y0 + 0.003) / (y1 - y0 + 0.006)
    pts = helix(y0, y1, turns, lambda y: core_r(y) + wire * 0.7, per_turn=per_turn, phase=math.radians(90))
    a.add(M.tube(pts, wire, sides=6), "coil", name=name, shading="smooth")


PETAL_T = (0.75, 0.60, 0.45, 0.30, 0.16)          # fraction of CH_A from the centre, cup lip first
PETAL_W = (0.030, 0.038, 0.031, 0.018, 0.003)      # leaf width along the orb's circumference (m)
PETAL_H = (0.006, 0.0055, 0.005, 0.004, 0.003)     # leaf thickness (m)


def petal(ang, side):
    """A brass calyx leaf lying on the orb, from the rear (side -1) or front (side +1) cup lip toward the
    equator: the orb sits in a flower-like setting (width across the orb, thickness radial)."""
    pts = []
    for t in PETAL_T:
        y = CH_Y + side * t * CH_A
        pts.append(radial(ang, glass_radius(y) + 0.0032, y))
    a = math.radians(ang)
    rect = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    return M.tube(pts, 1.0, profile=rect, up=(math.cos(a), 0, math.sin(a)),
                  scale_xy=list(zip(PETAL_H, PETAL_W)))


def stock_curves():
    """Centre-lines of the upper and lower stock struts and the crescent arc (shared by the mesh and the
    pinstripe decals)."""
    cc = Vector((0.0, STOCK_CC_Y, 0.030))     # crescent arc centre (y, z); the horns point back
    cr = 0.105

    def arc(th):
        return Vector((0.0, cc.y + cr * math.cos(math.radians(th)), cc.z + cr * math.sin(math.radians(th))))
    top = M.catmull([(0, -0.085, AX + 0.004), (0, -0.17, AX - 0.012), (0, -0.26, AX - 0.012),
                     tuple(arc(40.0))], 3)
    low = M.catmull([(0, -0.045, -0.060), (0, -0.14, -0.050), (0, -0.25, -0.046), tuple(arc(-38.0))], 3)
    return top, low, arc


# ---- geometry -----------------------------------------------------------------------------------------------

def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES)
    rect = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]

    # -- pistol grip (dark wood, raked back) + brass pommel cap
    g = M.box((0.042, 0.064, 0.155), bevel=0.012, segments=2, taper=(1.08, 1.12))
    M.xform(g, loc=(0, -0.012, -0.012), rot=(-18, 0, 0))
    a.add(g, "wood", name="grip")
    cap = M.box((0.05, 0.078, 0.024), bevel=0.008, taper=(0.88, 0.86))
    M.xform(cap, loc=(0, -0.040, -0.094), rot=(-18, 0, 0))
    a.add(cap, "brass", name="pommel")

    # -- receiver: a slim dark-iron body rising toward the neck coil
    rec = M.loft_rect([(-0.105, 0.044, 0.060, 0, AX - 0.002), (-0.02, 0.054, 0.084, 0, AX - 0.008),
                       (0.06, 0.058, 0.096, 0, AX - 0.004), (0.108, 0.054, 0.086, 0, AX)],
                      bevel=0.011, segments=2)
    a.add(rec, "iron", name="receiver")
    # copper conductor rail along the receiver top, running into the neck coil
    rail = M.tube([(0, -0.10, AX + 0.026), (0, -0.02, AX + 0.034), (0, 0.06, AX + 0.044), (0, 0.12, AX + 0.030)],
                  0.0075, sides=6)
    a.add(rail, "copper", name="rail", shading="smooth")
    # brass rivets on the receiver sides (the sides are vertical)
    for sx in (-1, 1):
        pts = [(sx * 0.0275, y, z) for y, z in ((-0.075, AX - 0.012), (0.085, AX - 0.022))]
        a.add(M.studs(pts, [(sx, 0, 0)] * len(pts), 0.0065, 0.005), "brass", name="rivets", shading="smooth")

    # -- swan-neck skeleton stock (bone): a curved upper strut, a lower strut, a crescent butt (Selene = the moon)
    top, low, arc = stock_curves()
    n = len(top)
    sc = [(0.036 - 0.004 * i / (n - 1), 0.040 - 0.008 * math.sin(math.pi * i / (n - 1))) for i in range(n)]
    a.add(M.tube(top, 1.0, profile=rect, up=(1, 0, 0), scale_xy=sc), "bone", name="stock_top")
    a.add(M.band(low, 0.031, 0.024, up=(1, 0, 0)), "bone", name="stock_low")
    cres = [arc(th) for th in range(-66, 67, 12)]
    n = len(cres)
    sc = []
    for i in range(n):
        t = abs(i / (n - 1) * 2 - 1)            # 1 at the horns, 0 in the middle
        sc.append((0.046 - 0.012 * t, 0.032 - 0.024 * t * t))
    a.add(M.tube(cres, 1.0, profile=rect, up=(1, 0, 0), scale_xy=sc), "bronze", name="crescent")

    # -- trigger guard (iron strap) and trigger
    guard = M.catmull([(0, 0.022, AX - 0.062), (0, 0.036, AX - 0.122), (0, 0.072, AX - 0.136),
                       (0, 0.097, AX - 0.108), (0, 0.098, AX - 0.050)], 3)
    a.add(M.band(guard, 0.015, 0.008, up=(1, 0, 0)), "iron", name="guard")
    a.add(M.horn([(0, 0.058, AX - 0.056), (0, 0.054, AX - 0.080), (0, 0.064, AX - 0.098)], 0.0065, 0.003, sides=5),
          "iron", name="trigger", shading="smooth")

    # -- the thundercoil: a copper coil pack wound on the neck between the receiver and the orb
    coil(a, NECK[0] + 0.008, NECK[1] - 0.012, 3.0, 0.031, 0.031, 0.0056, 9, "neck_coil")

    # -- the storm-glass orb in two small brass cups whose rims open into five calyx leaves each
    glass = M.sphere(CH_R, 16, 10, scale=(1, 1, CH_A / CH_R))
    M.xform(glass, rot=(-90, 0, 0))
    M.xform(glass, loc=CORE)
    a.add(glass, "glass", name="orb", shading="smooth")
    rear = [(0.026, CH_Y - 0.126), (0.034, CH_Y - 0.118), (0.046, CH_Y - 0.108), (0.058, CH_Y - 0.098),
            (0.068, CH_Y - 0.088), (0.075, CH_Y - 0.081), (0.077, CH_Y - CUP_LIP), (0.074, CH_Y - 0.073),
            (0.066, CH_Y - 0.072)]
    a.add(lathe_y(rear, 14), "brass", name="cup_rear", shading="smooth")
    front = [(r, 2 * CH_Y - y) for r, y in reversed(rear)]
    a.add(lathe_y(front, 14), "brass", name="cup_front", shading="smooth")
    for side, off in ((-1, 90.0), (1, 126.0)):
        for k in range(5):
            a.add(petal(off + 72.0 * k, side), "brass", name="petal")

    # -- barrel: iron rod, wooden sleeve (left hand), brass bands, tapering copper induction coil
    rod = M.cylinder(0.019, 0.60 - 0.385, sides=10, axis="Y")
    M.xform(rod, loc=(0, (0.60 + 0.385) / 2, AX))
    a.add(rod, "iron", name="rod", shading="smooth")
    y0, y1 = SLEEVE
    sleeve = [(0.024, y0), (0.031, y0 + 0.016), (0.0345, y0 + 0.045), (0.033, y0 + 0.075), (0.027, y1)]
    a.add(lathe_y(sleeve, 12), "wood", name="sleeve", shading="smooth")
    for y in (y0 - 0.001, y1 + 0.004):
        b = M.ring(0.018, 0.035, 0.011, sides=14, axis="Y")
        M.xform(b, loc=(0, y, AX))
        a.add(b, "brass", name="band")
    coil(a, COIL[0], COIL[1], 4.5, 0.029, 0.0235, 0.0052, 9, "barrel_coil")

    # -- the emitter: brass bell, glowing bore, copper halo ring, three conductor tines
    bell = [(0.019, MUZZLE_Y - 0.056), (0.026, MUZZLE_Y - 0.044), (0.040, MUZZLE_Y - 0.024),
            (0.049, MUZZLE_Y - 0.010), (0.050, MUZZLE_Y - 0.001), (0.043, MUZZLE_Y)]
    a.add(lathe_y(bell, 16), "brass", name="bell", shading="smooth")
    bore = [(0.043, MUZZLE_Y), (0.030, MUZZLE_Y - 0.006), (0.015, MUZZLE_Y - 0.012), (0.0, MUZZLE_Y - 0.014)]
    a.add(lathe_y(bore, 16), "glow_bore", name="bore", shading="smooth")
    ring_pts = [radial(360.0 * i / 16, HALO_R, HALO_Y) for i in range(16)]
    a.add(M.tube(ring_pts, 0.0105, sides=5, closed=True, up=(0, 1, 0)), "copper", name="halo", shading="smooth")
    # rev 2 (art review: the needle tines were 1-2 px at 1x): the prongs are longer (tip 0.762 -> 0.800),
    # about 60 % thicker (base radius 0.0115 -> 0.0185), splay wider (0.083 -> 0.097 from the axis, the
    # muzzle is now 0.23 m across) and end in a blunt electrode tip (radius 0.006) instead of a needle,
    # so each glowing tip is a dot at game size. Same ring count, so the same triangle count.
    radii = [0.0185, 0.0172, 0.0160, 0.0150, 0.0142, 0.0136, 0.0132, 0.0130, 0.0126, 0.0108, 0.0060]
    for ang in (90.0, 210.0, 330.0):
        ctrl = [radial(ang, r, y) for r, y in ((HALO_R - 0.006, HALO_Y - 0.006), (0.081, HALO_Y + 0.026),
                                                (0.097, HALO_Y + 0.066), (0.096, HALO_Y + 0.106),
                                                (0.084, HALO_Y + 0.142), (0.068, TINE_TIP_Y))]
        pts = M.catmull(ctrl, 2)
        assert len(pts) == len(radii)
        a.add(M.tube(pts, radii, sides=5, cap=True), "tine", name="tine", shading="smooth")

    obj = a.to_object(col)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return obj


# ---- paint -------------------------------------------------------------------------------------------------

RECIPES = {
    "iron": P.zone(base="#2D2A38", shadow="#110E17", light="#7F7A9C", planes=0.08, edge=0.95, edge_width=0.004,
                   cavity=0.6, ao=0.5, brush=0.05),
    "brass": P.zone(base="#C79E55", shadow="#62431D", light="#F8E0A2", planes=0.08, parts=0.05, edge=0.85,
                    edge_width=0.004, cavity=0.7, ao=0.6,
                    spots={"color": "#7C5A2C", "amount": 0.22, "freq": 16.0, "threshold": (0.62, 0.74)}),
    "copper": P.zone(base="#C0673A", shadow="#5A2214", light="#FFBE8C", planes=0.09, parts=0.04, edge=0.8,
                     edge_width=0.0035, cavity=0.6, ao=0.55),
    "coil": P.zone(base="#BD6536", shadow="#4E1A0E", light="#FFB885", planes=0.12, parts=0.0, edge=0.35,
                   edge_width=0.0025, cavity=0.3, ao=0.85, ao_range=(0.2, 0.55), brush=0.04),
    # rev 2: the glow runs over the front half of each prong (was the last ~2 cm), storm blue -> Storm ->
    # white-hot at the blunt tip, so the three tips read as bright dots at 1x
    "tine": P.zone(base="#C0673A", shadow="#5A2214", light="#FFBE8C", planes=0.1, edge=0.6, edge_width=0.003,
                   cavity=0.4, ao=0.4,
                   emit={"core": STORM_DEEP, "hot": STORM, "color": STORM_CORE, "mode": "plane",
                         "axis": (0, 1, 0), "range": (TINE_GLOW_Y, TINE_TIP_Y), "fade": (0.0, 0.3),
                         "base_mix": 0.75}),
    "bone": P.zone(base=BONE, shadow="#4A3826", light="#CDB690", planes=0.06, parts=0.04, edge=0.5,
                   edge_width=0.004, cavity=0.75, ao=0.6, stroke=(0, 1, 0), stroke_amount=0.22,
                   stroke_freq=(120.0, 3.0), brush=0.06, brush_freq=9.0,
                   gradient={"axis": (0, 1, 0), "range": (-0.12, -0.33), "color": "shadow", "amount": 0.32}),
    "bronze": P.zone(base="#8A6638", shadow="#3E2810", light="#D0AA68", planes=0.08, parts=0.0, edge=0.8,
                     edge_width=0.004, cavity=0.7, ao=0.6,
                     spots={"color": "#5A3E1E", "amount": 0.25, "freq": 16.0, "threshold": (0.62, 0.74)}),
    "wood": P.zone(base="#45282A", shadow="#1A0C0E", light="#7E4C45", planes=0.05, parts=0.04, edge=0.55,
                   edge_width=0.0045, cavity=0.7, ao=0.6, stroke=(0, 1, 0), stroke_amount=0.3,
                   stroke_freq=(80.0, 5.0)),
    # the glass gets its own plasma pass (paint_glass); this recipe only fills it before that
    "glass": P.zone(base=GLASS_DARK, edge=0.0, cavity=0.0, ao=0.0, planes=0.0, parts=0.0),
    "glow_bore": P.zone(base=GLASS_PALE, edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": STORM_CORE, "hot": STORM, "color": STORM_DEEP, "mode": "axis",
                              "center": (0, MUZZLE_Y, AX), "axis": (0, 1, 0), "radius": 0.043, "base_mix": 0.8}),
}


def glass_frame():
    """Cylinder-decal frame: Z = the bore axis (+Y), X = weapon right; u = angle * CH_R, v = y - CH_Y."""
    return Matrix(((1, 0, 0, CORE[0]), (0, 0, 1, CORE[1]), (0, -1, 0, CORE[2]), (0, 0, 0, 1)))


def crackle_lines(seed=11):
    """Lightning veins over the storm-glass orb, (u, v) metres around it. The seam of the cylinder mapping
    (u = +-pi * R, the weapon's left side) is avoided; v stays between the cups."""
    rng = random.Random(seed)
    lim_u = math.pi * CH_R - 0.022
    lim_v = CUP_LIP - 0.004
    out = []

    def keep(ln):
        ln = [p for p in ln if abs(p[0]) < lim_u and abs(p[1]) < lim_v]
        if len(ln) >= 2:
            out.append(ln)
    # forks that leap from the equator toward the cups (the plasma reaching for the coils)
    n = 7
    for k in range(n):
        u0 = (-1 + (2 * k + 1) / n) * (lim_u - 0.01) + rng.uniform(-0.01, 0.01)
        for d in (90.0, -90.0):
            ls = M.crack_lines(rng, start=(u0, rng.uniform(-0.01, 0.01)), direction=d + rng.uniform(-30, 30),
                               length=rng.uniform(0.05, 0.075), step=0.009, jag=0.6, branches=1,
                               branch_len=0.55, branch_angle=40, depth=1)
            for ln in ls:
                keep(ln)
    # a jagged arc running around the equator, broken into strokes
    for u0 in (-0.27, -0.13, 0.01, 0.15):
        pts = [(u0 + 0.105 * i / 6, rng.uniform(-0.008, 0.008)) for i in range(7)]
        keep(pts)
    return out


def bolt_lines(sx):
    """A lightning bolt inlaid along the receiver side (u runs forward on both sides)."""
    pts = [(-0.085, 0.010), (-0.040, 0.004), (-0.030, 0.016), (0.020, -0.004), (0.030, 0.008), (0.078, -0.014)]
    return [[(sx * u, v) for u, v in pts]]


def decals():
    out = []
    for sx in (-1, 1):
        u = Vector((0, sx, 0))
        v = Vector((0, 0, 1))
        z = u.cross(v)
        fr = Matrix(((u.x, v.x, z.x, 0), (u.y, v.y, z.y, 0.008), (u.z, v.z, z.z, AX - 0.004), (0, 0, 0, 1)))
        out.append(P.decal_lines(bolt_lines(sx), fr, 0.0055, zones=["iron"], color="#E28A52", rim="#0D0A12",
                                 rim_width=0.010, depth=(0.0, 0.06)))
        # scrimshaw line inked along both bone struts (u = sx * y so the frame's +Z points out of this side);
        # rev 2: dark ink instead of the brass pinstripe, which vanished into the darker smoked bone
        top, low, _ = stock_curves()
        fr0 = Matrix(((u.x, v.x, z.x, 0), (u.y, v.y, z.y, 0), (u.z, v.z, z.z, 0), (0, 0, 0, 1)))
        stripes = []
        for curve, y_lo, y_hi in ((top, -0.29, -0.11), (low, -0.29, -0.075)):
            stripes.append([(sx * p.y, p.z) for p in curve if y_lo <= p.y <= y_hi])
        out.append(P.decal_lines(stripes, fr0, 0.0030, zones=["bone"], color="#2E2026", rim="#6A563F",
                                 rim_width=0.0062, depth=(0.0, 0.06)))
    # an engraved frieze around each brass cup: two rings and a lightning zig-zag between them
    for side in (-1, 1):
        dy = side * 0.092
        r = 0.064
        fr = Matrix(((1, 0, 0, 0), (0, 0, 1, CH_Y + dy), (0, -1, 0, AX), (0, 0, 0, 1)))
        lim = math.pi * r - 0.012
        lines = [[(-lim, v), (lim, v)] for v in (-0.0062, 0.0062)]
        zz, u, k = [], -lim, 0
        while u < lim:
            zz.append((u, 0.0036 * (1 if k % 2 == 0 else -1)))
            u += 0.011
            k += 1
        lines.append(zz)
        out.append(P.decal_lines(lines, fr, 0.0022, zones=["brass"], color="#5B3816", rim=None, facing=0.2,
                                 mapping="cylinder", radius=r))
    out.append(P.decal_lines(crackle_lines(), glass_frame(), 0.0040, zones=["glass"], color="#EAF6FA",
                             emit={"color": STORM, "core": STORM_CORE}, rim_width=0.011, facing=0.15,
                             mapping="cylinder", radius=CH_R))
    return out


def paint_glass(flat, zones_order, base, emis, seed=5):
    """The storm-glass orb as a plasma globe: dark slate glass lit from inside by a low storm-blue glow,
    thin bright plasma wisps (ridged noise) drifting through it, a lighter glass rim at the brass cups.
    The crackle veins (decals) carry the brightest white-cyan. No light direction."""
    zi = zones_order.index("glass")
    m = flat["zone"] == zi
    if not m.any():
        return base, emis
    p = flat["pos"][m]
    n = len(p)
    t = np.abs((p[:, 1] - CH_Y) / CH_A)                       # 0 at the equator, 1 at the poles
    cloud = P.spread01(P.fbm(p, 11.0, 3, seed=seed), 2.6)
    w1 = P.spread01(P.fbm(p * np.array([1.0, 0.6, 1.0], dtype=np.float32), 17.0, 3, seed=seed + 3), 2.4)
    w2 = P.spread01(P.fbm(p, 27.0, 2, seed=seed + 9), 2.4)
    wisp = np.maximum((1 - np.abs(2 * w1 - 1)) ** 7, 0.7 * (1 - np.abs(2 * w2 - 1)) ** 9)   # thin ridges
    band = P.smoothstep(0.92, 0.4, t)                          # fades out under the calyx leaves
    # base: dark glass with slate depths, lighter glass toward the cup lips
    c = P.mix(P.hex3(GLASS_DARK)[None].repeat(n, 0), P.hex3(GLASS_MID), P.smoothstep(0.4, 0.85, cloud) * 0.7)
    c = P.mix(c, P.hex3(GLASS_EDGE), P.smoothstep(0.55, 0.7, t) * 0.7)
    # emission intensity: a steady low glow, stronger in the clouds, the wisps on top
    I = band * np.clip(0.34 + 0.22 * cloud + 0.75 * wisp, 0, 1)
    deep, storm, core = P.hex3(STORM_DEEP), P.hex3(STORM), P.hex3(STORM_CORE)
    em = P.mix(deep[None].repeat(n, 0), storm, P.smoothstep(0.22, 0.55, I))
    em = P.mix(em, core, P.smoothstep(0.72, 0.98, I) * 0.8)
    em = em * np.clip(I * 1.25, 0, 1)[:, None]
    c = P.mix(c, P.hex3(GLASS_PALE), P.smoothstep(0.7, 1.0, I) * 0.6)
    base[m] = c
    emis[m] = em
    return base, emis


def apply_decals(flat, zones_order, base, emis, decs):
    """Same as the decal pass at the end of gfa_paint.paint (run after the glass pass)."""
    P_, Nt, Z = flat["pos"], flat["tnrm"], flat["zone"]
    N = len(P_)
    for dec in decs:
        target = np.ones(N, dtype=bool) if not dec["zones"] else np.isin(Z, [zones_order.index(z) for z in dec["zones"]])
        idx = np.nonzero(target)[0]
        line, rimm = P._decal_masks(dec, P_[idx], Nt[idx])
        if dec["rim"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["rim"]), rimm * 0.75)
        if dec["color"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["color"]), line)
        if dec["emit"]:
            ec = P.hex3(dec["emit"]["color"])
            core = P.hex3(dec["emit"].get("core", dec["emit"]["color"]))
            glow = P.mix(np.repeat(ec[None], len(idx), 0), core, P.smoothstep(0.5, 1.0, line))
            emis[idx] = np.maximum(emis[idx], glow * np.maximum(line, rimm * 0.3)[:, None])
    return np.clip(base, 0, 1), np.clip(emis, 0, 1)


def paint_asset(obj, key, recipes, tex_dir, size=1024, decs=(), ao_distance=0.03, ao_samples=24, seed=0):
    """gfa_paint.paint_asset with one extra step: the glass plasma pass between the zone paint and the
    decals. Same outputs: <key>_basecolor.png, <key>_emissive.png, material M_<key>, a report."""
    t0 = time.time()
    zones_order = [s.material.name[4:] for s in obj.material_slots]
    dens = P.unwrap(obj, size, 6, 60.0)
    C.log("unwrapped: %.0f px/m median" % dens["median"])
    mp = P.bake_maps(obj, size, ao_distance, ao_samples)
    zone_img = mp["zone"][..., 0]
    valid = zone_img > 0.5 / 64
    ao_img = P.masked_blur(mp["ao"][..., 0], valid, radius=2, passes=2)
    lo, hi = mp["lo"], mp["hi"]
    flat = {
        "zone": np.rint(zone_img[valid] * 64 - 1).astype(np.int64),
        "pos": (mp["pos"][..., :3][valid] * (hi - lo) + lo).astype(np.float32),
        "tnrm": mp["tnrm"][..., :3][valid] * 2 - 1,
        "snrm": mp["snrm"][..., :3][valid] * 2 - 1,
        "part": np.rint(mp["part"][..., 0][valid] * 4096 - 1).astype(np.int64),
        "ao": ao_img[valid].astype(np.float32),
    }
    for k in ("tnrm", "snrm"):
        flat[k] = flat[k] / (np.linalg.norm(flat[k], axis=1, keepdims=True) + 1e-9)
    dv, dc = P.edge_distances(obj, flat["pos"])
    base, emis = P.paint(flat, zones_order, recipes, dv, dc, (), seed)
    base, emis = paint_glass(flat, zones_order, base, emis)
    base, emis = apply_decals(flat, zones_order, base, emis, decs)
    B = np.zeros((size, size, 3), dtype=np.float32)
    Em = np.zeros((size, size, 3), dtype=np.float32)
    B[valid] = base
    Em[valid] = emis
    B = P.dilate(B, valid, 12)
    Em = P.dilate(Em, valid, 12)
    C.ensure_dir(tex_dir)
    bp = os.path.join(tex_dir, "%s_basecolor.png" % key)
    ep = os.path.join(tex_dir, "%s_emissive.png" % key)
    P.save_png(bp, B, "%s_basecolor" % key)
    P.save_png(ep, Em, "%s_emissive" % key)
    P.apply_final_material(obj, "M_%s" % key, bp, ep)
    rep = {"size": size, "texel_density_px_per_m": dens, "coverage": round(float(valid.mean()), 3),
           "zones": zones_order, "decals": len(decs), "basecolor": C.rel(bp), "emissive": C.rel(ep),
           "emissive_texels": int((emis.max(1) > 0.1).sum()),
           # texel density is equalised by the unwrap, so this is roughly the share of the SURFACE that glows
           "emissive_fraction_of_painted": round(float((emis.max(1) > 0.1).sum()) / max(1, len(emis)), 3),
           "seconds": round(time.time() - t0, 1)}
    C.log("painted %s in %.0fs (coverage %.0f%%, emissive %.1f%% of painted texels)" % (
        key, rep["seconds"], 100 * rep["coverage"], 100 * rep["emissive_fraction_of_painted"]))
    return rep


# ---- extra review renders ------------------------------------------------------------------------------------

def extra_reviews(root, mesh, reports, work):
    """A large 3/4 hero image and a close-up through the in-game camera (55 deg pitch, zoomed) with the
    weapon in the mannequin's hands at its grip frame."""
    out = {}
    turn = R.turnaround([mesh], work, KEY + "_beauty", {"34": (0.78, 0.5, 0.42)}, size=760, pad=1.06)
    out["beauty"] = turn["34"]
    saved = root.matrix_world.copy()
    sockets = {c.name: c for c in root.children if c.type == "EMPTY"}
    for i, (aim, vh) in enumerate((((0.55, -0.83, 0.0), 5.2), ((1.0, 0.0, 0.0), 5.2))):
        root.matrix_world = R.weapon_hold_matrix(aim)
        bpy.context.view_layer.update()
        gl = sockets["grip_L"].matrix_world.translation.copy()
        man = R.mannequin(aim_dir=aim, grip_r=root.matrix_world.translation, grip_l=gl)
        r = R.ingame([mesh], work, "%s_close%d" % (KEY, i), px=560, view_height=vh, mannequin_obj=man,
                     target=(0.25 * aim[0], 0.25 * aim[1], 1.05), ink=0.0045, samples=16, silhouette_too=False)
        out["close_%d" % i] = r["color"]
        C.remove_objects([man])
    root.matrix_world = saved
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    return out


def copy_png(src, dst):
    import shutil
    C.ensure_dir(os.path.dirname(dst))
    shutil.copyfile(src, dst)
    return dst


# ---- main ---------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 1024, int)
    C.reset_scene()
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 next to the source
    col = C.get_collection(KEY)
    root = C.add_empty(KEY, size=0.1, col=col)
    mesh = build_mesh(col)
    mesh.parent = root
    # sockets (docs/art/WEAPONS.md section 3): children of the root, +Y forward, +Z up
    C.add_empty("grip_R", (0, 0, 0), parent=root, col=col)
    C.add_empty("grip_L", GRIP_L, parent=root, col=col)
    C.add_empty("muzzle", (0, MUZZLE_Y, AX), parent=root, col=col)
    C.add_empty("glow_core", CORE, parent=root, col=col)

    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decs=decals(), ao_distance=0.03,
                            ao_samples=24, seed=7)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=os.path.abspath(__file__),
                         extra={"chassis": {"damage_type": "Storm", "style": "Orb", "tags": ["storm", "splash", "selene"],
                                            "wielder": "selene"},
                                "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage",
                                                                    "emissive_fraction_of_painted")}})
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    if not C.flag(argv, "--no-review"):
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        notes = [
            "%s tris (two-handed budget 2000-4000) | textures %s | length %.2f m | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
                ", ".join(sorted(rep["sockets"]))),
            "Grip frame: origin = right palm centre on the pistol grip, Blender +Y = barrel (glTF -Z), +Z = up. "
            "grip_L under the wooden sleeve, muzzle at the bore inside the halo, glow_core in the orb.",
            "Storm #3FD8FF only in the emissive (%.1f %% of the surface): orb plasma + crackle, bore, tine tips." % (
                100 * paint_rep["emissive_fraction_of_painted"]),
            "Status: %s (the user gives the final visual approval)." % rep.get("status", "ai_final_pending_user_approval"),
        ]
        rv = R.review_weapon(KEY, root, mesh, reports, work, "Thundercoil Launcher  (thundercoil_launcher)",
                             "Storm | Orb, auto 3.5/s, splash 1.0 m | tags: storm, splash, selene | "
                             "silhouette verb: THE LUMP (one storm-glass orb) on a slender frame + round forked emitter",
                             swatches=PALETTE, notes=notes,
                             textures=[os.path.join(tex_dir, KEY + "_basecolor.png"),
                                       os.path.join(tex_dir, KEY + "_emissive.png")])
        ex = extra_reviews(root, mesh, reports, work)
        copy_png(ex["beauty"], os.path.join(reports, KEY + "_34.png"))
        copy_png(ex["close_0"], os.path.join(reports, KEY + "_ingame_close.png"))
        copy_png(ex["close_1"], os.path.join(reports, KEY + "_ingame_close_side.png"))
        copy_png(rv["ingame_0"], os.path.join(reports, KEY + "_ingame_1x.png"))
        copy_png(rv["ingame_sil_0"], os.path.join(reports, KEY + "_ingame_1x_sil.png"))
        copy_png(rv["turn_side_R"], os.path.join(reports, KEY + "_side.png"))
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.abspath(__file__)),
        C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        C.rel(os.path.join(reports, KEY + "_review.png")), C.rel(os.path.join(reports, KEY + "_34.png")),
        C.rel(os.path.join(reports, KEY + "_ingame_close.png"))],
        "Built from code by art/weapons/thundercoil_launcher/source/thundercoil_launcher_build.py "
        "(tools/blender/gf_assets). Selene's signature chassis.",
        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
