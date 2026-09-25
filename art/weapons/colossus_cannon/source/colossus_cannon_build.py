"""Colossus Cannon - Valdris's signature arm-mounted siege cannon, built end to end from code with
tools/blender/gf_assets (docs/art/WEAPONS.md). Regenerate everything with:

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P art/weapons/colossus_cannon/source/colossus_cannon_build.py -- [--size 1024] [--no-review]

(tools/blender/gf_assets/weapons/colossus_cannon.py is a thin alias that runs this file.)

Content row (content/sheets/chassis.csv): colossus_cannon "Colossus Cannon", P0, Auto fire, damage 26,
2.6 shots/s, speed 20, range 13, knockback 3.0, splash radius 1.6 (0.5 damage), Kinetic, style Shell,
tags "heavy; splash; valdris" - "Siege artillery for one. Shells burst on impact, knocking the horde back."

References: docs/media/playable_characters/VALDRIS.jpg and "VALDRIS THE ANVIL-BORN.jpg" (the cannon on
his arm), art/characters/valdris/brief.md (sections 2 and 4: barrel ~0.31 m across, 0.48 m with the top
clamps and under-bracket, three gold bands, a glowing ember muzzle as his hottest point) and the TRELLIS
blockout close-ups in art/characters/valdris/reports/blockout/.

Design (docs/art/WEAPONS.md section 5, family HEAVY / SPLASH, verb THE LUMP):
  * ARM-MOUNTED (the orchestrator's brief, from the concept; WEAPONS.md's first line said "shoulder-slung"):
    a plated sleeve straps over the right forearm (two war-red straps with gold buckles) and the right
    fist closes on an inner handle bar inside the sleeve (= grip_R, the origin);
  * the silhouette is a dumbbell of three masses along the aim: a slim sleeve -> a fat BREECH DRUM (the
    widest mass, ~1/3 of the length, two top clamps with gold caps and an under-bracket, as in the concept)
    -> a short barrel -> a wide stepped MUZZLE COLLAR (a siege-gun swell, deliberately not the Sunspike's
    bell) with a gold ring and a big glowing ember bore;
  * the drum is a revolving shell housing: an octagon of eight bevelled gunmetal staves with the cream
    Kinetic shells recessed in the gaps (cream / dark stripes = "loaded drum");
  * the off-hand grip (grip_L, two-handed tier) is a BRACE HANDLE on the sleeve's upper-left, slung between
    the two strap lugs over the right forearm: the left hand steadies the cannon arm in front of the chest
    (revision 2, art review: the first build put it on the drum's left flank, 0.95 m from the left shoulder
    and out of a 2.2 m hero's reach); a steam vent with a glowing grille on the barrel's right side is the
    `eject` socket;
  * the "shell-burst ring": eight glowing radial slots on the muzzle face around the bore and eight
    glowing blast ports around the collar (painted decals, so they cost no triangles);
  * Valdris's anvil sigil in forge gold on the top stave between the clamps (faces the game camera);
  * value rhythm: the sleeve darkens toward the elbow -> gold drum hoops and cream shells -> dark barrel
    -> gold band -> gold muzzle ring -> the brightest value, the ember bore (Kinetic cream-white core,
    Valdris's Ember Amber rim);
  * palette: Valdris's colour script (gunmetal #2A242E / cannon steel #47403A, Forge Gold #FFC24B, Ember
    Amber #FF6B1A, Deep War Red #7A1F1F) + the Kinetic element hue #F4E3C1 (palette.rs) for the shells and
    the white-hot core of every glow.

Grip frame (docs/art/WEAPONS.md section 2): origin = palm centre of the right fist on the inner handle,
+Y = barrel, +Z = up, +X = the weapon's right. The sleeve / barrel axis runs through the palm (the
forearm lies along -Y inside the sleeve, the elbow at about y = -0.38).

Hold (the review mannequin, and what the GF_Hero_v1 aim pose should do): the right upper arm swings in
and forward so the elbow sits in front of the right chest and the forearm points along the aim; the
cannon is carried close to the body's centre line (the palm ~0.18 m right of it at ~1.47 m), and the left
hand takes the brace handle ~0.58 m from the left shoulder (a 2.2 m hero reaches ~0.76 m).

Paint (revision 2, art review: "regular horizontal white streaks that look like procedural brushed metal"):
the gunmetal zone is painted by tools/blender/gf_assets/gfa_brush.py - a few broad value planes per part
and tapered brush strokes on the edges - instead of gfa_paint's per-facet planes, fbm dabs and spots.

Adapted patterns: tools/blender/gf_assets/weapons/sunspike_shotgun.py (structure, paint recipes,
review) and gfa_render.mannequin / ingame (the arm-mount hold below re-uses them).
"""
import math
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GFA = os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "tools", "blender", "gf_assets"))
sys.path.insert(0, GFA)
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_brush as B  # noqa: E402
import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY, KIND, TIER = "colossus_cannon", "weapon", "two_handed"
AX = 0.0                        # barrel / sleeve axis height above the palm centre (m)

# stations along +Y (m): sleeve | drum | barrel | muzzle collar
SLEEVE_Y = (-0.345, 0.06)
DRUM_Y = (0.045, 0.415)
BARREL_Y = (0.405, 0.66)
COLLAR_Y = (0.635, 0.79)
MUZZLE_Y = 0.80                 # front of the muzzle ring (the muzzle socket)
BORE_R = 0.12                   # bore radius at the face

R_SLEEVE = 0.146                # sleeve outer radius (rear segment); inner radius 0.10 (the forearm goes inside)
R_SLEEVE_IN = 0.100
R_DRUM_CORE = 0.196
R_DRUM = 0.228                  # drum staves outer radius (octagon apothem)
R_BARREL = 0.156
R_COLLAR = 0.236                # muzzle collar outer radius

# off-hand brace handle on the sleeve's upper-left, between the two straps (revision 2; was the drum's
# left-flank handle at (-0.312, 0.23, AX), out of reach)
BRACE_ANG = 150.0               # around the barrel axis, from +X toward +Z (90 = top, 180 = the left)
BRACE_R = 0.215                 # bar centre from the axis (finger clearance over the straps)
BRACE_Y = (-0.19, -0.04)        # the lugs ride on the two straps
GRIP_L = (round(BRACE_R * math.cos(math.radians(BRACE_ANG)), 4), sum(BRACE_Y) / 2,
          round(AX + BRACE_R * math.sin(math.radians(BRACE_ANG)), 4))
CORE = (0.0, 0.23, AX)          # the breech chamber (heat pulse / point light)
EJECT = (0.212, 0.49, AX + 0.07)

ZONES = ["gunmetal", "iron", "gold", "leather", "shell", "glow_bore", "glow_vent"]
GUNMETAL = {"base": "#48424C", "shadow": "#1A161D", "light": "#A59BA8"}
EMBER = {"rim": "#E2561A", "hot": "#FF9A3C", "core": "#FFF4D6"}
PALETTE = [  # (name, hex) for the review sheet
    ("gunmetal", GUNMETAL["base"]), ("dark iron", "#2A2530"), ("forge gold", "#D29C40"), ("war red", "#7A1F1F"),
    ("kinetic shell", "#E6D2A6"), ("ember rim", EMBER["rim"]), ("ember hot", EMBER["hot"]), ("core", EMBER["core"]),
]


# ---- geometry -------------------------------------------------------------------------------------------------

TRIS = {}                       # tris per part name (build report)


def _y(bm):
    """Rotate a part built around +Z so that its axis runs along +Y (local +Z -> +Y)."""
    return M.xform(bm, rot=(-90, 0, 0))


def facing(bm, expect):
    """Open surfaces (lathes that are not closed solids): make the whole surface face `expect(centre)`.
    recalc_face_normals only guesses on open meshes, and the engine material is single-sided."""
    bm.normal_update()
    score = sum(f.calc_area() * f.normal.dot(expect(f.calc_center_median())) for f in bm.faces)
    if score < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    return bm


def _radial(c):
    return Vector((c.x, 0.0, c.z - AX)).normalized()


def _front(c):
    return Vector((0.0, 1.0, 0.0))


def _polar(r, ang_deg, y):
    """Point at radius r around the Y axis, angle measured from +X toward +Z (top = 90)."""
    a = math.radians(ang_deg)
    return Vector((r * math.cos(a), y, AX + r * math.sin(a)))


def _on_surface(ang_deg, r, y):
    """4x4 placing a part built with its thin side along local X onto the cylinder surface around Y:
    local X -> radial (outward), local Y -> the barrel axis, local Z -> tangent."""
    return Matrix.Translation(_polar(r, ang_deg, y)) @ Matrix.Rotation(math.radians(-ang_deg), 4, "Y")


def hoop(r_in, r_out, height, y, sides=16, chamfer=0.008, inner=False):
    """A band around the barrel axis at station y with chamfered outer corners. inner=False leaves the
    inner wall out (it is buried in the part underneath), which saves a third of the triangles."""
    h = height / 2
    c = min(chamfer, height / 3)
    if c > 0:
        prof = [(r_in, -h), (r_out - c, -h), (r_out, -h + c), (r_out, h - c), (r_out - c, h), (r_in, h)]
    else:
        prof = [(r_in, -h), (r_out, -h), (r_out, h), (r_in, h)]
    if inner:
        prof.append((r_in, -h))
    bm = M.lathe(prof, sides=sides, cap=False)
    _y(bm)
    M.xform(bm, loc=(0, y, AX))
    return facing(bm, _radial) if not inner else M.recalc(bm)


def strap(add, ys, rs):
    """A war-red strap around the sleeve with a gold buckle on the upper right."""
    add(hoop(rs - 0.006, rs + 0.013, 0.046, ys, sides=16, chamfer=0.0), "leather", "strap")
    bk = M.box((0.026, 0.066, 0.068), bevel=0.007)
    M.xform(bk, matrix=_on_surface(38, rs + 0.019, ys))
    add(bk, "gold", "buckle")
    tg = M.box((0.012, 0.026, 0.028))
    M.xform(tg, matrix=_on_surface(38, rs + 0.034, ys))
    add(tg, "iron", "buckle_pin")


def build_mesh(col):
    rng = random.Random(11)
    a = M.Assembly(KEY + "_mesh", ZONES)

    def add(bm, zone, name, **kw):
        TRIS[name] = TRIS.get(name, 0) + sum(len(f.verts) - 2 for f in bm.faces)
        return a.add(bm, zone, name=name, **kw)

    # ---- sleeve over the forearm: one closed lathe (the inner wall shows through the elbow opening) with a
    #      groove that splits it into two segments; the lengthwise plate seams are painted -----------------------
    y0, y1 = SLEEVE_Y
    sl = M.lathe([(R_SLEEVE - 0.01, y0 + 0.012), (R_SLEEVE - 0.004, y0 + 0.05), (R_SLEEVE, -0.13),
                  (R_SLEEVE - 0.012, -0.118), (R_SLEEVE - 0.012, -0.102), (R_SLEEVE + 0.004, -0.09),
                  (R_SLEEVE + 0.01, y1)], sides=16, cap=False)
    _y(sl)
    add(facing(sl, _radial), "gunmetal", "sleeve", shading="smooth")
    # the inner wall (dark iron, facing the axis): what shows around the forearm at the elbow opening
    inner = M.lathe([(R_SLEEVE_IN, y0 + 0.02), (R_SLEEVE_IN, y1)], sides=16, cap=False)
    _y(inner)
    add(facing(inner, lambda c: -_radial(c)), "iron", "sleeve_inner", shading="smooth")
    # a raised spine plate on the sleeve top (the side the game camera sees) with two gold rivets
    sp = M.box((0.03, 0.17, 0.082), bevel=0.009, taper=(0.8, 0.92))
    M.xform(sp, matrix=_on_surface(90, R_SLEEVE + 0.006, -0.225))
    add(sp, "gunmetal", "spine_plate")
    add(M.studs([_polar(R_SLEEVE + 0.021, 90, yy) for yy in (-0.285, -0.165)], [(0, 0, 1)] * 2, 0.013, 0.01, sides=6),
        "gold", "spine_rivet", shading="smooth")
    # dark iron cuff at the elbow end (inner wall kept: it frames the arm opening)
    add(hoop(R_SLEEVE_IN - 0.004, R_SLEEVE + 0.026, 0.04, y0 + 0.012, sides=16, chamfer=0.01, inner=True),
        "gunmetal", "cuff")
    # two war-red straps with gold buckles on the upper right (the side the game camera sees)
    strap(add, BRACE_Y[1], R_SLEEVE + 0.01)
    strap(add, BRACE_Y[0], R_SLEEVE)
    # the off-hand brace handle (grip_L) on the upper-left, slung between two lugs that ride on the straps:
    # gunmetal lugs, an iron bar with gold end caps, a war-red leather wrap where the left palm closes
    for yh, rs in ((BRACE_Y[0], R_SLEEVE + 0.013), (BRACE_Y[1], R_SLEEVE + 0.023)):
        r_top = BRACE_R + 0.026
        lug = M.box((r_top - rs + 0.004, 0.036, 0.054), bevel=0.009)
        M.chip_corners(lug, rng, count=1, depth=(0.003, 0.007))
        M.xform(lug, matrix=_on_surface(BRACE_ANG, (r_top + rs - 0.004) / 2, yh))
        add(lug, "gunmetal", "brace_lug")
    hb = M.cylinder(0.018, BRACE_Y[1] - BRACE_Y[0] + 0.05, sides=6, axis="Y")
    M.xform(hb, loc=GRIP_L)
    add(hb, "iron", "brace_bar", shading="smooth")
    for yy in (BRACE_Y[0] - 0.027, BRACE_Y[1] + 0.027):
        capb = M.cylinder(0.024, 0.014, sides=8, axis="Y")
        M.xform(capb, loc=(GRIP_L[0], yy, GRIP_L[2]))
        add(capb, "gold", "brace_cap")
    wrap = M.cylinder(0.025, BRACE_Y[1] - BRACE_Y[0] - 0.046, sides=6, axis="Y")
    M.xform(wrap, loc=GRIP_L)
    add(wrap, "leather", "brace_wrap", shading="smooth")

    # inner handle bar the right fist closes on (grip_R): iron bar across the sleeve interior
    bar = M.cylinder(0.02, 2 * R_SLEEVE_IN + 0.01, sides=6, axis="Z")
    M.xform(bar, loc=(0, 0.0, AX))
    add(bar, "iron", "inner_handle", shading="smooth")

    # ---- breech drum: octagon of flat bevelled staves, Kinetic shells recessed in the gaps, gold hoops ------
    d0, d1 = DRUM_Y
    dm = (d0 + d1) / 2
    dcore = M.cylinder(R_DRUM_CORE, d1 - d0 - 0.03, sides=8, axis="Y")
    M.xform(dcore, loc=(0, dm, AX), rot=(0, 22.5, 0))
    add(dcore, "iron", "drum_core")
    for k in range(8):
        st = M.box((0.036, d1 - d0 - 0.05, 0.122), bevel=0.011)
        M.chip_corners(st, rng, count=1, depth=(0.004, 0.01))
        M.xform(st, matrix=_on_surface(45 * k, R_DRUM - 0.018, dm))
        add(st, "gunmetal", "drum_stave")
    for k in range(8):
        sh = M.cylinder(0.025, d1 - d0 - 0.07, sides=6, axis="Y")
        M.xform(sh, loc=_polar(R_DRUM_CORE - 0.01, 22.5 + 45 * k, dm))
        add(sh, "shell", "shell", shading="smooth")
    for yy in (d0 + 0.022, d1 - 0.022):
        add(hoop(R_SLEEVE - 0.01, R_DRUM + 0.026, 0.05, yy, sides=16, chamfer=0.012), "gold", "drum_hoop")

    # top clamps: two saddle blocks on the drum top, gold caps, gold rivets on the sides
    for yc in (d0 + 0.1, d1 - 0.1):
        cl = M.box((0.13, 0.085, 0.11), bevel=0.013, segments=1, taper=(0.76, 0.84))
        M.chip_corners(cl, rng, count=2, depth=(0.006, 0.014))
        M.xform(cl, loc=(0, yc, AX + R_DRUM + 0.03))
        add(cl, "gunmetal", "clamp")
        cap = M.box((0.084, 0.092, 0.024), bevel=0.007)
        M.xform(cap, loc=(0, yc, AX + R_DRUM + 0.09))
        add(cap, "gold", "clamp_cap")
        add(M.studs([(sx * 0.057, yc, AX + R_DRUM + 0.03) for sx in (-1, 1)], [(-1, 0, 0), (1, 0, 0)], 0.012, 0.009,
                    sides=5), "gold", "clamp_rivet", shading="smooth")
    # under-bracket: a heavy tapered block under the drum
    ub = M.box((0.13, 0.26, 0.11), bevel=0.013, segments=1, taper=(0.7, 0.8))
    M.chip_corners(ub, rng, count=2, depth=(0.006, 0.015))
    M.xform(ub, rot=(180, 0, 0), loc=(0, dm, AX - R_DRUM - 0.028))
    add(ub, "gunmetal", "under_bracket")
    add(M.studs([(sx * 0.057, yb, AX - R_DRUM - 0.035) for sx in (-1, 1) for yb in (dm - 0.075, dm + 0.075)],
                [(-1, 0, 0), (-1, 0, 0), (1, 0, 0), (1, 0, 0)], 0.011, 0.008, sides=5), "gold", "bracket_rivet",
        shading="smooth")

    # ---- barrel: one lathe (two segments), the third gold band between ---------------------------------------
    b0, b1 = BARREL_Y
    bm_ = b0 + 0.13
    br = M.lathe([(R_BARREL - 0.02, b0), (R_BARREL, b0 + 0.012), (R_BARREL - 0.006, bm_ - 0.012),
                  (R_BARREL - 0.02, bm_), (R_BARREL - 0.008, bm_ + 0.012), (R_BARREL - 0.012, b1)],
                 sides=16, cap=False)
    _y(br)
    add(facing(br, _radial), "gunmetal", "barrel", shading="smooth")
    add(hoop(R_BARREL - 0.03, R_BARREL + 0.024, 0.044, bm_, sides=16, chamfer=0.01), "gold", "barrel_band")
    # steam vent with a glowing grille on the barrel's right (the eject socket)
    vent = M.box((0.085, 0.1, 0.05), bevel=0.01, taper=(0.8, 0.9))
    M.xform(vent, rot=(0, 90, 0), loc=(R_BARREL + 0.007, EJECT[1], EJECT[2]))
    add(vent, "gunmetal", "vent")
    grille = M.box((0.012, 0.072, 0.056))
    M.xform(grille, loc=(R_BARREL + 0.036, EJECT[1], EJECT[2]))
    add(grille, "glow_vent", "vent_glow")
    for dz in (-0.014, 0.014):
        slat = M.box((0.014, 0.08, 0.008))
        M.xform(slat, loc=(R_BARREL + 0.04, EJECT[1], EJECT[2] + dz))
        add(slat, "iron", "vent_slat")

    # ---- muzzle: a stepped siege collar (not a bell), gold ring, iron face with the burst slots, ember bore --
    c0, c1 = COLLAR_Y
    cl = M.lathe([(R_BARREL - 0.018, c0), (R_BARREL + 0.004, c0 + 0.012), (0.19, c0 + 0.03), (0.206, c0 + 0.042),
                  (R_COLLAR - 0.012, c0 + 0.05), (R_COLLAR, c0 + 0.062), (R_COLLAR, c1 - 0.016),
                  (R_COLLAR - 0.014, c1), (0.2, c1 + 0.003), (0.19, c1 - 0.01)], sides=18, cap=False)
    _y(cl)
    add(facing(cl, _radial), "gunmetal", "collar", shading="smooth")
    add(hoop(0.17, 0.21, 0.034, MUZZLE_Y - 0.014, sides=18, chamfer=0.009), "gold", "muzzle_ring")
    face = M.lathe([(0.174, MUZZLE_Y - 0.03), (0.174, MUZZLE_Y - 0.017), (BORE_R + 0.012, MUZZLE_Y - 0.011),
                    (BORE_R, MUZZLE_Y - 0.019)], sides=18, cap=False)
    _y(face)
    add(facing(face, _front), "iron", "muzzle_face", shading="smooth")
    bore = M.lathe([(BORE_R, MUZZLE_Y - 0.019), (BORE_R - 0.014, MUZZLE_Y - 0.065), (0.06, MUZZLE_Y - 0.12),
                    (0.0, MUZZLE_Y - 0.14)], sides=18, cap=False)
    _y(bore)
    add(facing(bore, _front), "glow_bore", "bore", shading="smooth")

    obj = a.to_object(col)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    C.log("tris by part: " + ", ".join("%s %d" % kv for kv in sorted(TRIS.items(), key=lambda kv: -kv[1])))
    return obj


# ---- paint -------------------------------------------------------------------------------------------------------

RECIPES = {
    # gunmetal: only base / shadow / light, the elbow gradient, AO and cavity are read from here; its value planes
    # and edge strokes come from BROAD below (gfa_brush), which replaced the per-facet planes, fbm edge dabs,
    # brush noise and soot spots that read as regular horizontal brushed-metal streaks (art review, revision 2)
    "gunmetal": P.zone(base=GUNMETAL["base"], shadow=GUNMETAL["shadow"], light=GUNMETAL["light"], cavity=0.75,
                       cavity_width=0.007, ao=0.6,
                       gradient={"axis": (0, 1, 0), "range": (0.05, SLEEVE_Y[0]), "color": "shadow", "amount": 0.32}),
    "iron": P.zone(base="#2A2530", shadow="#0F0C12", light="#6E6474", planes=0.06, parts=0.04, edge=0.7,
                   edge_width=0.005, cavity=0.6, ao=0.5),
    "gold": P.zone(base="#D29C40", shadow="#6A4318", light="#FFE6A0", planes=0.09, parts=0.05, edge=0.9,
                   edge_width=0.0055, cavity=0.65, ao=0.5,
                   spots={"color": "#9A6A2A", "amount": 0.25, "freq": 16.0, "threshold": (0.62, 0.74)}),
    "leather": P.zone(base="#7A1F1F", shadow="#2C0A0C", light="#B5503F", planes=0.04, edge=0.55, edge_width=0.004,
                      cavity=0.6, ao=0.5, stroke=(1, 0, 0), stroke_amount=0.18, stroke_freq=(90.0, 8.0)),
    "shell": P.zone(base="#E6D2A6", shadow="#7C6242", light="#FFF6E0", planes=0.05, parts=0.05, edge=0.5,
                    edge_width=0.004, cavity=0.5, ao=0.75, ao_range=(0.15, 0.55)),
    "glow_bore": P.zone(base="#FFB060", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": EMBER["core"], "hot": EMBER["hot"], "color": EMBER["rim"], "mode": "axis",
                              "center": (0, MUZZLE_Y, AX), "axis": (0, 1, 0), "radius": BORE_R, "base_mix": 0.3}),
    "glow_vent": P.zone(base="#FF9A40", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#FFE2A0", "hot": "#FF8A2A", "color": EMBER["rim"], "mode": "radial",
                              "center": (R_BARREL + 0.042, EJECT[1], EJECT[2]), "radius": 0.05, "base_mix": 0.3}),
}


# a few broad painted value planes per part + tapered brush strokes on the edges (tools/blender/gf_assets/gfa_brush.py)
BROAD = {
    "gunmetal": B.broad(levels=(-0.35, -0.12, 0.12, 0.35), wobble=0.3, wobble_freq=6.0, inner=0.04, stroke=0.7,
                        stroke_width=0.011, stroke_len=0.2, stroke_cover=0.4, glint=0.45),
    # the dark iron drum core shows between the staves along the whole drum: its octagon edges were the
    # brightest of the regular streaks, so it gets the same treatment, quieter
    "iron": B.broad(levels=(-0.25, -0.08, 0.08, 0.22), wobble=0.3, wobble_freq=6.0, inner=0.03, stroke=0.55,
                    stroke_width=0.008, stroke_len=0.2, stroke_cover=0.3, glint=0.3),
}


def _frame(origin, x, y):
    """4x4 decal frame: x, y span the drawing plane, z = x cross y is the projection direction."""
    x, y = Vector(x).normalized(), Vector(y).normalized()
    z = x.cross(y)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def _cyl_u(ang_deg, r):
    """Decal u coordinate of the world angle ang_deg on a 'cylinder' decal around +Y built with _frame(
    (0, y, AX), (1, 0, 0), (0, 0, -1)): the decal angle is -ang, wrapped into (-180, 180]."""
    a = -ang_deg
    a = (a + 180.0) % 360.0 - 180.0
    return math.radians(a) * r


def decals():
    out = []
    ember = {"color": EMBER["rim"], "core": "#FFC070"}
    # the shell-burst ring: eight glowing radial slots on the iron muzzle face, around the bore
    fr = _frame((0, MUZZLE_Y - 0.015, AX), (-1, 0, 0), (0, 0, 1))
    out.append(P.decal_lines(M.sunburst(8, BORE_R + 0.01, 0.17, start_deg=90.0), fr, 0.016, zones=["iron"],
                             color="#FFB45A", rim="#120D10", rim_width=0.022, emit=ember, facing=0.3,
                             depth=(-0.05, 0.03)))
    # eight glowing blast ports around the collar (the burst ring read from the side and the top)
    ym = COLLAR_Y[1] - 0.045
    cyl = _frame((0, ym, AX), (1, 0, 0), (0, 0, -1))
    ports = [[(_cyl_u(22.5 + 45 * k, R_COLLAR), -0.02), (_cyl_u(22.5 + 45 * k, R_COLLAR), 0.02)] for k in range(8)]
    out.append(P.decal_lines(ports, cyl, 0.022, zones=["gunmetal"], color="#FFB45A", rim="#120D10", rim_width=0.03,
                             emit=ember, facing=0.5, mapping="cylinder", radius=R_COLLAR))
    # plate seams on the sleeve: two rings of six plates, the front ring offset half a plate (brickwork)
    seams = []
    for angs, (va, vb) in (((30, 150, 210, 330, 270), (-0.33, -0.125)), ((0, 60, 120, 240, 300), (-0.095, 0.06))):
        for g in angs:
            seams.append([(_cyl_u(g, R_SLEEVE), va), (_cyl_u(g, R_SLEEVE), vb)])
    out.append(P.decal_lines(seams, _frame((0, 0, AX), (1, 0, 0), (0, 0, -1)), 0.006, zones=["gunmetal"],
                             color="#141017", rim=None, facing=0.5, mapping="cylinder", radius=R_SLEEVE))
    # Valdris's anvil sigil in forge gold on the top stave between the clamps (faces the game camera);
    # drawn upright for a viewer behind the gun (anvil top toward the muzzle), horn to the left
    anvil = [(-0.03, 0.017), (0.028, 0.017), (0.028, 0.006), (0.014, 0.002), (0.011, -0.01), (0.024, -0.02),
             (-0.022, -0.02), (-0.009, -0.01), (-0.012, 0.002), (-0.028, 0.004), (-0.046, 0.011), (-0.03, 0.017)]
    spark = [[(0.0, 0.026), (0.0, 0.036)], [(-0.012, 0.024), (-0.018, 0.032)], [(0.012, 0.024), (0.018, 0.032)]]
    dm = sum(DRUM_Y) / 2
    top = _frame(_polar(R_DRUM, 90, dm), (1, 0, 0), (0, 1, 0))     # z = +Z: projected down
    out.append(P.decal_lines([anvil] + spark, top, 0.0065, zones=["gunmetal"], color="#E8B24E", rim="#15101A",
                             rim_width=0.012, facing=0.6, depth=(-0.03, 0.02)))
    return out


# ---- arm-mount hold for the review (the forearm lies inside the sleeve) ------------------------------------------

# GF_Hero_v1 arm (Brax, 2.155 m, art/characters/brax/reports/stage3/landmarks.json): upperarm 0.33 +
# lowerarm 0.325 + wrist -> palm centre 0.09 m, scaled to the 2.2 m review hero
ARM_REACH = (0.33 + 0.3252 + 0.09) * SPEC.HERO_HEIGHT / 2.155


def armmount_hold(aim_dir, height=SPEC.HERO_HEIGHT):
    """(grip-frame world matrix, elbow world point) for a mannequin at the origin aiming along aim_dir.
    Revision 2 (art review): the right upper arm swings in and forward (~0.36 m, the GF_Hero_v1 upper arm)
    so the elbow sits in front of the right chest, the forearm points along the aim inside the sleeve and
    the cannon is carried close to the body's centre line, where the left hand reaches the brace handle.
    (Revision 1 hung the upper arm straight down, 0.43 m right of the centre line at 1.27 m.)"""
    s = height / 2.2
    a = Vector(aim_dir)
    a.z = 0
    a.normalize()
    right = a.cross(Vector((0, 0, 1)))
    elbow = right * 0.18 * s + a * 0.18 * s + Vector((0, 0, 1.47 * s))
    palm = elbow + a * 0.38 * s
    return C.frame_from_axes(palm, a, (0, 0, 1)), elbow


def left_shoulder(aim_dir, height=SPEC.HERO_HEIGHT):
    """The review mannequin's left shoulder joint (gfa_render.mannequin: x 0.36, z 1.70 at 2.2 m)."""
    s = height / 2.2
    a = Vector(aim_dir)
    a.z = 0
    a.normalize()
    right = a.cross(Vector((0, 0, 1)))
    return -right * 0.36 * s + Vector((0, 0, 1.70 * s))


def grip_l_reach():
    """Left shoulder -> grip_L distance (m) in the review hold, for the mannequin and for Brax's shoulder
    (x 0.27, z 1.765 at 2.155 m, scaled to 2.2 m), against the GF_Hero_v1 arm reach."""
    hold, _ = armmount_hold((0.0, 1.0, 0.0))
    gl = hold @ Vector(GRIP_L)
    k = SPEC.HERO_HEIGHT / 2.155
    brax_sh = Vector((-0.27 * k, -0.035 * k, 1.765 * k))     # Brax faces -Y; this hold faces +Y
    return {"shoulder_to_grip_L_m": round((gl - left_shoulder((0.0, 1.0, 0.0))).length, 3),
            "shoulder_to_grip_L_m_gf_hero": round((gl - brax_sh).length, 3),
            "arm_reach_m": round(ARM_REACH, 3),
            "grip_L_world_m": [round(v, 3) for v in gl],
            "hold": "right elbow in front of the right chest (0.18 m right of the centre line, 0.18 m forward, "
                    "1.47 m up), forearm along the aim inside the sleeve; hero 2.2 m",
            "revision_1": "the drum's left-flank handle (-0.312, 0.23, 0 Blender grip space) with the upper arm "
                          "hanging 0.43 m right of the centre line: 0.95 m from the left shoulder"}


def armmount_mannequin(aim_dir, grip_mat, elbow, grip_l):
    """gfa_render.mannequin with the right 'hand' at the elbow, plus a forearm + fist to the palm."""
    man = R.mannequin(aim_dir=aim_dir, grip_r=elbow, grip_l=grip_l)
    bpy.context.view_layer.update()
    inv = man.matrix_world.inverted()
    palm = grip_mat.translation
    bm = bmesh.new()
    bm.from_mesh(man.data)
    fa = M.tube([inv @ elbow, inv @ elbow.lerp(palm, 0.6), inv @ palm], [0.068, 0.062, 0.056], sides=8)
    M._append_raw(bm, fa)
    fist = M.sphere(0.066, 8, 6)
    M.xform(fist, loc=inv @ palm)
    M._append_raw(bm, fist)
    bm.to_mesh(man.data)
    bm.free()
    for p in man.data.polygons:
        p.use_smooth = True
    return man


def review(root, mesh, reports, work, tex_dir, rep):
    scene = bpy.context.scene
    out = {}
    turn = R.turnaround([mesh], work, KEY, R.WEAPON_VIEWS, size=420)
    out.update({"turn_" + k: v for k, v in turn.items()})
    out["sil_side"] = R.silhouette([mesh], os.path.join(work, "%s_sil_side.png" % KEY), (1, 0, 0), size=260)
    out["sil_top"] = R.silhouette([mesh], os.path.join(work, "%s_sil_top.png" % KEY), (0, 0.0001, 1), size=260)
    out["sil_front"] = R.silhouette([mesh], os.path.join(work, "%s_sil_front.png" % KEY), (0, 1, 0.0001), size=260)
    saved = root.matrix_world.copy()
    sockets = {c.name: c for c in root.children if c.type == "EMPTY"}
    ing, held, held_close = [], [], []
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    game_dir = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
    for i, aim_dir in enumerate(((1.0, 0.0, 0.0), (0.6, -0.8, 0.0), (-0.5, 0.85, 0.0))):
        hold, elbow = armmount_hold(aim_dir)
        root.matrix_world = hold
        bpy.context.view_layer.update()
        gl = sockets["grip_L"].matrix_world.translation.copy()
        man = armmount_mannequin(aim_dir, hold, elbow, gl)
        ing.append(R.ingame([mesh], work, "%s_aim%d" % (KEY, i), px=170, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                            mannequin_obj=man, target=(0.0, 0.2, 1.0)))
        # the same framing at a readable size (the hold at its grip frame, seen through the game camera)
        R.setup_cycles(scene, 14)
        fl = bpy.data.objects.get("GFA_FLOOR")
        with R.toon_preview([mesh, man], ink=0.009, flat={man.name: R.MANNEQUIN}):
            R.aim(scene, Vector((0.1, 0.2, 1.2)), game_dir, 2.9)
            held.append(R.render(scene, os.path.join(work, "%s_held_%d.png" % (KEY, i)), 560))
            if i < 2:
                # both hands on the cannon, closer (the left palm on the brace handle)
                R.aim(scene, (hold.translation + gl) * 0.5 + Vector((0, 0, -0.05)), game_dir, 1.45)
                held_close.append(R.render(scene, os.path.join(work, "%s_held_close_%d.png" % (KEY, i)), 560))
        C.remove_objects([man])
    root.matrix_world = saved
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    # large 3/4 close-ups (the README image) on the review background
    R.setup_cycles(scene, 16)
    pts = R._points([mesh])
    with R.toon_preview([mesh], ink=0.006):
        for name, d in (("34", (0.78, 0.52, 0.42)), ("34_back", (-0.72, -0.5, 0.48))):
            c, w, h = R.frame(pts, d)
            R.aim(scene, c, d, max(w, h) * 1.08)
            out["close_" + name] = R.render(scene, os.path.join(reports, "%s_%s.png" % (KEY, name)), 800)
        # paint detail: the drum staves and the sleeve up close (where revision 1 streaked)
        R.aim(scene, Vector((-0.02, 0.06, AX + 0.04)), (-0.62, 0.45, 0.64), 0.62)
        out["close_detail"] = R.render(scene, os.path.join(reports, "%s_detail.png" % KEY), 800)
    tex = R._thumbs([os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")], work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    notes = [
        "%s tris (two-handed / heavy budget 2000-4000) | textures %s | length %.2f m | sockets: %s" % (
            rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
            ", ".join(sorted(rep["sockets"]))),
        "Grip frame: origin = right palm centre on the inner handle (the forearm lies along -Y inside the sleeve), "
        "Blender +Y = barrel (glTF -Z), +Z = up. grip_L = the sleeve's brace handle, muzzle = bore face, eject = right vent.",
        "Revision 2: grip_L moved from the drum's left flank to the sleeve's upper-left brace handle; left shoulder -> "
        "grip_L %.2f m (GF_Hero_v1 shoulder %.2f m; arm reach %.2f m; revision 1: 0.95 m)." % (
            rep["grip_L_reach"]["shoulder_to_grip_L_m"], rep["grip_L_reach"]["shoulder_to_grip_L_m_gf_hero"],
            rep["grip_L_reach"]["arm_reach_m"]),
        "Revision 2: gunmetal and the iron drum core repainted with broad value planes and brush strokes "
        "(gfa_brush) instead of the streaky per-facet planes and edge dabs.",
        "Status: %s (the user gives the final visual approval)." % rep.get("status", SPEC.STATUS_AI_FINAL),
    ]
    layout = {
        "title": "Colossus Cannon  (colossus_cannon)",
        "subtitle": "Kinetic | Shell, auto 2.6/s, splash r 1.6, knockback 3 | tags: heavy, splash, valdris | "
                    "verb: THE LUMP (arm-mounted shell drum, stepped siege collar, ember bore)",
        "width": 1600,
        "sections": [
            {"label": "Turnaround - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k.replace("turn_", "")} for k, v in out.items() if k.startswith("turn_")]},
            {"label": "Close-up, 3/4 front and 3/4 back, and the paint up close (drum staves and sleeve; toon preview)",
             "height": 400,
             "images": [{"path": out["close_34"], "label": "34_front"}, {"path": out["close_34_back"], "label": "34_back"},
                        {"path": out["close_detail"], "label": "paint detail"}]},
            {"label": "Held by the 2.2 m mannequin (forearm in the sleeve, left hand on the brace handle, carried in front "
                      "of the chest), seen through the 55 deg game camera",
             "height": 300, "images": [{"path": p, "label": "aim %d" % i} for i, p in enumerate(held)]
                + [{"path": p, "label": "aim %d, hands close-up" % i} for i, p in enumerate(held_close)]},
            {"label": "In-game camera: orthographic, 55 deg pitch, view height %.0f m = 1080 px (%.1f px/m) - 1x true size, then 3x nearest"
                      % (SPEC.GAME_VIEW_HEIGHTS[0], ppm),
             "height": None, "images": sum([[{"path": r["color"], "label": "aim %d, 1x" % i},
                                             {"path": r["color"], "label": "aim %d, 3x" % i, "scale": 3}]
                                            for i, r in enumerate(ing[:2])], [])},
            {"label": "Silhouette: flat side / top / front, and the game-size silhouettes (3x)",
             "height": None, "images": [{"path": out["sil_side"], "label": "side"}, {"path": out["sil_top"], "label": "top"},
                                        {"path": out["sil_front"], "label": "front"}]
                + [{"path": r["sil"], "label": "aim %d game size, 3x" % i, "scale": 2} for i, r in enumerate(ing[:2])]},
            {"label": "Textures (base colour, emissive)", "height": 240,
             "images": [{"path": p, "label": lb} for p, lb in tex]},
        ],
        "swatches": [{"hex": h, "label": n} for n, h in PALETTE],
        "notes": notes,
    }
    for i, r in enumerate(ing):
        out["ingame_%d" % i] = r["color"]
        out["ingame_sil_%d" % i] = r["sil"]
    for i, p in enumerate(held):
        out["held_%d" % i] = p
    for i, p in enumerate(held_close):
        out["held_close_%d" % i] = p
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)
    shutil.copyfile(held[1], os.path.join(reports, "%s_held.png" % KEY))
    shutil.copyfile(held_close[0], os.path.join(reports, "%s_held_close.png" % KEY))
    return out


# ---- main ----------------------------------------------------------------------------------------------------------

REVISIONS = [
    {"rev": 1, "date": "2026-09-25", "change": "first build (commit cb41ae2)"},
    {"rev": 2, "date": "2026-09-25", "reason": "art review 7/10, must-fix items",
     "changes": [
         "grip_L moved from the drum's left-flank side handle, Blender grip space (-0.312, 0.23, 0) = glTF "
         "(-0.312, 0, -0.23), to a brace handle on the sleeve's upper-left between the two straps, Blender "
         "(%.3f, %.3f, %.3f) = glTF (%.3f, %.3f, %.3f): 0.13 m in toward the barrel axis and 0.35 m back toward "
         "the body. The drum's side handle is gone. The review hold now carries the cannon in front of the "
         "chest (the right elbow tucked in front of the right chest), which puts the handle on the body's "
         "centre line 0.45 m in front of the shoulders. Left shoulder -> grip_L: 0.95 m before, ~0.58 m now "
         "(a 2.2 m hero reaches ~0.76 m)." % (GRIP_L[0], GRIP_L[1], GRIP_L[2], GRIP_L[0], GRIP_L[2], -GRIP_L[1]),
         "gunmetal (and the dark-iron drum core that shows between the staves) repainted with a few broad "
         "value planes per part and tapered brush strokes on each part's own edges "
         "(tools/blender/gf_assets/gfa_brush.py) instead of per-facet planes, fbm edge dabs, brush noise and "
         "soot spots, which read as regular horizontal brushed-metal streaks up close."]},
]


def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 1024, int)
    C.reset_scene()
    col = C.get_collection(KEY)
    root = C.add_empty(KEY, size=0.1, col=col)
    mesh = build_mesh(col)
    mesh.parent = root
    # sockets (docs/art/WEAPONS.md section 3): children of the root, +Y forward, +Z up
    C.add_empty("grip_R", (0, 0, 0), parent=root, col=col)
    C.add_empty("grip_L", GRIP_L, parent=root, col=col)
    C.add_empty("muzzle", (0, MUZZLE_Y, AX), parent=root, col=col)
    C.add_empty("glow_core", CORE, parent=root, col=col)
    # eject: +Y = the steam / casing direction (out of the right vent, a little up and back)
    C.add_empty("eject", EJECT, rotation=C.frame_from_axes((0, 0, 0), (1.0, -0.25, 0.35), (0, 0, 1)).to_3x3(),
                parent=root, col=col)

    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = B.paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decals=decals(), broad=BROAD,
                              ao_distance=0.04, ao_samples=24, seed=7)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    b1 = blend + "1"
    if os.path.exists(b1):
        os.remove(b1)
    reach = grip_l_reach()
    C.log("grip_L reach: %.3f m from the mannequin's left shoulder, %.3f m from a GF_Hero_v1 shoulder "
          "(arm reach %.3f m)" % (reach["shoulder_to_grip_L_m"], reach["shoulder_to_grip_L_m_gf_hero"],
                                  reach["arm_reach_m"]))
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=os.path.abspath(__file__),
                         extra={"chassis": {"damage_type": "Kinetic", "style": "Shell", "fire": "Auto",
                                            "tags": ["heavy", "splash", "valdris"]},
                                "mount": "arm: the right forearm lies along -Y inside the sleeve (elbow ~0.38 m "
                                         "behind the palm), carried close to the body's centre line; grip_L is "
                                         "the brace handle on the sleeve's upper-left, between the two straps",
                                "grip_L_reach": reach,
                                "revisions": REVISIONS,
                                "paint": dict({k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
                                              painter="gfa_paint + gfa_brush broad zones %s" % paint_rep["broad_zones"])})
    rep["grip_L_reach"] = reach
    reports = os.path.join(pack, "reports")
    if not C.flag(argv, "--no-review"):
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        review(root, mesh, reports, work, tex_dir, rep)
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        C.rel(os.path.join(reports, KEY + "_review.png"))],
        "Built from code by art/weapons/colossus_cannon/source/colossus_cannon_build.py (gf_assets toolkit).",
        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
