"""Wraith Bow - Thessaly's charge bow, built end to end from code with tools/blender/gf_assets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P art/weapons/wraith_bow/source/wraith_bow_build.py -- [--size 1024] [--no-review]

Content row (content/sheets/chassis.csv): wraith_bow, Void, style Arrow, fire Charge, damage 40, fire rate
2.0, 1 projectile, speed 30, range 18, pierce 2, charge 0.8 s x2.5, crit 8 % x2.5, tags "charge; pierce;
thessaly" - "Draw to charge; loose hex-bolts that pass through the living." Signature chassis of Thessaly,
the Hexweaver (content/sheets/characters.csv: a witch-engineer who turns the battlefield into a cursed
machine). Any hero can wield it, so it carries the Void element hue, not Thessaly's player colour.

Design (docs/art/WEAPONS.md section 5, family CHARGE; secondary tags pierce, void):
  * silhouette verb THE DRAW: a recurve bow of pale wraith-wood held at half draw. The spectral string
    makes a shallow V back to the right hand, so the bow always shows stored tension. Each limb is a
    ghostly wing: a pale spar that curves back to the string nock, with a fan of carved wood feathers.
    The feathers turn from pointing forward near the riser to pointing outward and back at the tip,
    like a spread wing's primaries, and their tips dissolve into violet glow. A spectral hex-bolt sits
    on the string and runs through the riser, so the one sharp point (pierce) is at the front;
  * CANTED about the aim axis (72 deg, top limb to the weapon's right): the game camera looks down at
    55 deg, so an upright bow turns edge-on whenever the hero aims up or down the screen. Canted this
    far, the whole wing shape shows from every aim (the limb plane faces the camera at 0.57-0.97);
  * value rhythm: dark iron riser in the middle (grip wrap, limb pockets, nock claws), pale limbs and
    feathers, then the glows: violet string, white-hot bolt head in front (the brightest value);
  * void accent: a hollow VOID EYE in an iron frame on the riser, with a violet rim and a glowing slit
    pupil. Hexweaver sigils are carved into the limbs;
  * palette: pale wraith-wood + dark iron + dark plum leather + bone-brass bolts (the arsenal's warm
    metals) + the Void element hue #A45CFF (palette.rs element_color) for every glow.

Grip frame (docs/art/WEAPONS.md sections 2-3): origin = grip_R = the right palm centre at the string's
nocking point (the drawing hand). +Y = the aim (the bolt), +Z = up, +X = the weapon's right. grip_L = the
left palm on the riser grip, muzzle = the arrow rest on the riser (as WEAPONS.md specifies for this
chassis), glow_core = the bolt head (charge-fill VFX). The geometry is modelled as an upright bow in
a "bow frame" (limbs along +Z) and rotated by CANT at the end; every paint centre, decal and socket uses W().
Outputs: assets/models/weapons/wraith_bow.glb (+ .meta.json), art/weapons/wraith_bow/{source/*.blend,
textures/*.png, reports/*.png, status.json}.
Based on tools/blender/gf_assets/weapons/sunspike_shotgun.py, the toolkit's worked example.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender", "gf_assets"))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402

KEY, KIND, TIER = "wraith_bow", "weapon", "two_handed"

# ---- the bow frame (upright bow: x = lateral, y = aim, z = along the limbs) --------------------------------
CANT_DEG = 72.0                                   # rotation about the aim axis (+ = top limb to the right)
CANT = Matrix.Rotation(math.radians(CANT_DEG), 4, "Y")
T = 0.62                                          # string nock height (z) on each limb
NOCK_Y = 0.09                                     # nock depth: the string's V (half draw) back to the origin
GRIP_L = (0.0, 0.332, -0.09)                      # left palm centre on the riser grip
REST = (0.0, 0.38, 0.0)                           # the arrow rest at the riser front (muzzle socket)
BOLT_TIP_Y = 0.75
HEAD = (0.0, 0.63, 0.0)                           # bolt head centre (glow_core socket)
EYE = (0.006, 0.34, 0.07)                         # centre of the void eye on the riser window face (-x)
EYE_SCALE = (1.0, 0.86, 1.32)

# upper limb centre line (x = 0), from inside the limb pocket to the string nock
LIMB_CTRL = [(0, 0.300, 0.185), (0, 0.300, 0.25), (0, 0.290, 0.32), (0, 0.266, 0.395), (0, 0.228, 0.463),
             (0, 0.180, 0.522), (0, 0.132, 0.574), (0, NOCK_Y, T)]

# feathers per limb: (u along the limb 0..1, angle from the limb tangent toward the front (deg),
#                     length, in-plane width, curl toward the back (deg))
FEATHERS = [
    (0.12, 78.0, 0.130, 0.078, 10.0),
    (0.27, 65.0, 0.170, 0.084, 13.0),
    (0.42, 52.0, 0.210, 0.088, 16.0),
    (0.58, 39.0, 0.255, 0.088, 20.0),
    (0.75, 25.0, 0.295, 0.084, 26.0),
    (0.92, 9.0, 0.300, 0.074, 34.0),
]

ZONES = ["wood", "feather", "iron", "wrap", "brass", "void", "glow_eye", "glow_string", "glow_bolt"]
PALETTE = [  # (name, hex) for the review sheet
    ("wraith-wood", "#9C91A3"), ("feather", "#B0A6BC"), ("iron", "#35303F"), ("wrap", "#4E2C48"),
    ("bone-brass", "#C2A673"), ("void", "#140B20"), ("Void element", "#A45CFF"), ("glow rim", "#6E3CE0"),
    ("glow hot", "#8A5CF5"), ("bolt core", "#F2ECFF"),
]


def W(p):
    """A bow-frame point -> the grip frame (the cant applied)."""
    return tuple(CANT @ Vector(p))


def WD(d):
    """A bow-frame direction -> the grip frame."""
    return tuple(CANT.to_3x3() @ Vector(d))


SWAP_YZ = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # (x, y, z) -> (x, z, y)


def loft_z(sections, bevel=0.0, segments=1):
    """loft_rect along +Z: sections = [(z, width_x, depth_y, cx, cy), ...]."""
    bm = M.loft_rect([(z, w, d, cx, cy) for z, w, d, cx, cy in sections], bevel=bevel, segments=segments)
    return M.xform(bm, matrix=SWAP_YZ)


def mirror_z(bm):
    return M.mirrored(bm, "Z")


# ---- the limb curve ------------------------------------------------------------------------------------

def limb_points(per=4):
    return M.catmull(LIMB_CTRL, per)


def limb_at(pts, u):
    """(point, unit tangent) at fraction u of the limb's arc length."""
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg)
    s = max(0.0, min(1.0, u)) * total
    acc = 0.0
    for i, L in enumerate(seg):
        if acc + L >= s or i == len(seg) - 1:
            t = 0.0 if L < 1e-9 else (s - acc) / L
            p = pts[i].lerp(pts[i + 1], min(1.0, t))
            return p, (pts[i + 1] - pts[i]).normalized()
        acc += L
    return pts[-1], (pts[-1] - pts[-2]).normalized()


def front_of(t):
    """In-plane normal of a limb tangent that points to the front (+y) and outward."""
    return Vector((0.0, t.z, -t.y)).normalized()


def rot_inplane(d, deg):
    """Rotate a (0, y, z) direction in the limb plane; + turns from outward (+z) toward the front (+y)."""
    a = math.radians(deg)
    y, z = d.y, d.z
    return Vector((0.0, y * math.cos(a) + z * math.sin(a), z * math.cos(a) - y * math.sin(a))).normalized()


CHAMFER8 = [(-0.5, -0.28), (-0.28, -0.5), (0.28, -0.5), (0.5, -0.28), (0.5, 0.28), (0.28, 0.5), (-0.28, 0.5), (-0.5, 0.28)]
LENS6 = [(0.5, 0.0), (0.24, 0.5), (-0.24, 0.5), (-0.5, 0.0), (-0.24, -0.5), (0.24, -0.5)]


FEATHER_PROF_W = [0.72, 0.95, 1.0, 0.97, 0.85, 0.58, 0.0]
FEATHER_PROF_T = [1.0, 1.0, 1.0, 0.92, 0.8, 0.6, 0.0]


def feather_path(root, direction, length, curl, n=7):
    """Centre line (the rachis) of a feather: n points from the root, turning `curl` degrees toward the back."""
    d = Vector(direction).normalized()
    pts = [Vector(root)]
    step = length / (n - 1)
    for i in range(1, n):
        d = rot_inplane(d, -curl / (n - 1))
        pts.append(pts[-1] + d * step)
    return pts


def feather(pts, width, thick):
    """A carved feather blade in the limb plane along `pts`: lens section (ridge = rachis), pointed tip."""
    n = len(pts)
    return M.tube(pts, [1.0] * (n - 1) + [0.0], profile=LENS6, up=(1, 0, 0),
                  scale_xy=[(thick * FEATHER_PROF_T[i], width * FEATHER_PROF_W[i]) for i in range(n)])


def feather_specs(feathers=FEATHERS):
    """[(rachis points, width, thickness), ...] for the upper limb's feathers (bow frame)."""
    pts = limb_points(4)
    out = []
    for k, (u, ang, L, w, curl) in enumerate(feathers):
        p, t = limb_at(pts, u)
        d = rot_inplane(t, ang)
        root = p + front_of(t) * 0.012 - d * 0.02 + Vector((-0.005 * k, 0, 0))
        out.append((feather_path(root, d, L, curl), w, 0.022 - 0.001 * k))
    return out


# ---- geometry -----------------------------------------------------------------------------------------------

def build_upper_limb(a, rng, feathers=FEATHERS):
    """Adds one limb (spar, feathers, pocket, band, nock claw) for the upper side; returns the parts' bmeshes
    as (bm, zone, name, shading) so the caller can add them and their mirrored copies."""
    parts = []
    pts = limb_points(4)
    n = len(pts)
    ws, ts = [], []
    for i in range(n):
        f = i / (n - 1)
        ws.append(0.050 - 0.020 * f)          # across the bow plane (x)
        ts.append(0.074 - 0.036 * f ** 0.8)   # in the bow plane (what the camera sees)
    spar = M.tube(pts, 1.0, profile=CHAMFER8, up=(1, 0, 0), scale_xy=list(zip(ws, ts)))
    parts.append((spar, "wood", "limb", "auto"))
    # feathers: a fan from forward-pointing (near the riser) to outward-and-back (the wing tip)
    for fp, w, th in feather_specs(feathers):
        parts.append((feather(fp, w, th), "feather", "feather", "auto"))
    # iron limb pocket over the riser end, two bone-brass bolts on the visible (-x) face
    p, t = limb_at(pts, 0.035)
    pocket = M.box((0.066, 0.086, 0.07), bevel=0.012, segments=1, taper=(0.9, 0.86))
    M.xform(pocket, matrix=M.orient(p + Vector((0, 0.004, 0.0)), t, (1, 0, 0)))
    parts.append((pocket, "iron", "pocket", "auto"))
    fr = front_of(t)
    bolts = M.studs([p + fr * 0.022 + Vector((-0.033, 0, 0)), p - fr * 0.022 + Vector((-0.033, 0, 0))],
                    [(-1, 0, 0)] * 2, 0.0105, 0.008)
    parts.append((bolts, "brass", "pocket_bolts", "smooth"))
    # an iron band around the spar at mid-limb
    p, t = limb_at(pts, 0.44)
    band = M.box((0.05, 0.068, 0.026), bevel=0.006)
    M.xform(band, matrix=M.orient(p, t, (1, 0, 0)))
    parts.append((band, "iron", "band", "auto"))
    # the nock claw: an iron hook that holds the string loop and curls forward past the nock
    tip = pts[-1]
    tprev = (pts[-1] - pts[-3]).normalized()
    c0 = tip - tprev * 0.035
    c1 = tip + tprev * 0.01
    out = Vector((0, 0, 1))
    c2 = tip + out * 0.045 + Vector((0, 0.005, 0))
    c3 = tip + out * 0.07 + Vector((0, 0.04, 0))
    c4 = tip + out * 0.062 + Vector((0, 0.075, 0))
    claw = M.tube(M.catmull([c0, c1, c2, c3, c4], 2), [0.022, 0.024, 0.022, 0.018, 0.013, 0.01, 0.007, 0.004, 0.0],
                  sides=6, up=(1, 0, 0))
    parts.append((claw, "iron", "nock_claw", "auto"))
    return parts


def build_mesh(col, feathers=FEATHERS):
    a = M.Assembly(KEY + "_mesh", ZONES)
    rng = random.Random(7)

    # ---- riser (dark iron): lower block, wrapped grip, stepped window section (the step = the arrow shelf)
    lower = loft_z([(-0.25, 0.046, 0.056, 0.0, 0.296), (-0.205, 0.052, 0.068, 0.0, 0.308),
                    (-0.150, 0.056, 0.078, 0.0, 0.320)], bevel=0.009)
    a.add(lower, "iron", name="riser_lower")
    upper = loft_z([(-0.030, 0.056, 0.080, 0.0, 0.333), (-0.013, 0.056, 0.082, 0.0, 0.335),
                    (-0.007, 0.040, 0.088, 0.032, 0.337), (0.060, 0.040, 0.094, 0.032, 0.340),
                    (0.130, 0.042, 0.090, 0.030, 0.336), (0.178, 0.050, 0.074, 0.008, 0.318),
                    (0.215, 0.050, 0.064, 0.0, 0.304), (0.25, 0.046, 0.056, 0.0, 0.296)], bevel=0.008)
    a.add(upper, "iron", name="riser_upper")
    wrap = loft_z([(-0.158, 0.064, 0.088, 0.0, 0.323), (-0.12, 0.068, 0.094, 0.0, 0.327),
                   (-0.06, 0.068, 0.094, 0.0, 0.330), (-0.024, 0.064, 0.088, 0.0, 0.333)], bevel=0.012, segments=2)
    a.add(wrap, "wrap", name="grip_wrap", shading="smooth")
    for z in (-0.158, -0.026):
        fe = loft_z([(z - 0.009, 0.07, 0.096, 0.0, 0.325 + (z + 0.158) * 0.06),
                     (z + 0.009, 0.07, 0.096, 0.0, 0.325 + (z + 0.158) * 0.06)], bevel=0.004)
        a.add(fe, "iron", name="grip_ferrule")
    # the riser's crest: an iron beak on the window section's front, beside the eye (the head between the wings)
    keel = M.spike(0.034, 0.075, sides=4, base_scale=(0.5, 1.0), rot_offset=0)
    M.xform(keel, matrix=M.orient((0.03, 0.37, 0.075), (0, 1, 0.12), (1, 0, 0)))
    a.add(keel, "iron", name="keel")

    # ---- the void eye on the window face (-x): iron frame, violet rim, hollow void with a glowing slit
    ex = M.ring(0.030, 0.045, 0.016, sides=14, bevel=0.003, axis="X")
    M.xform(ex, loc=EYE, scale=EYE_SCALE)
    a.add(ex, "iron", name="eye_frame")
    er = M.ring(0.020, 0.031, 0.010, sides=14, axis="X")
    M.xform(er, loc=(EYE[0] + 0.002, EYE[1], EYE[2]), scale=EYE_SCALE)
    a.add(er, "glow_eye", name="eye_rim", shading="smooth")
    ev = M.cylinder(0.021, 0.008, sides=14, axis="X")
    M.xform(ev, loc=(EYE[0] + 0.005, EYE[1], EYE[2]), scale=EYE_SCALE)
    a.add(ev, "void", name="eye_void", shading="smooth")
    # bone-brass studs at the riser ends
    a.add(M.studs([(-0.024, 0.318, 0.19), (-0.024, 0.318, -0.19)], [(-1, 0, 0)] * 2, 0.009, 0.007), "brass",
          name="riser_studs", shading="smooth")

    # ---- limbs: upper built, lower mirrored (z -> -z)
    for bm, zone, name, shading in build_upper_limb(a, rng, feathers):
        low = mirror_z(bm)
        a.add(bm, zone, name=name + "_up", shading=shading)
        a.add(low, zone, name=name + "_lo", shading=shading)

    # ---- the spectral string: a V from each nock to the nocking point (the right hand), a knot at the nock
    for sz in (1, -1):
        s = M.tube([Vector((0, NOCK_Y + 0.004, sz * (T + 0.004))), Vector((0, 0, 0))], 0.0085, sides=6)
        a.add(s, "glow_string", name="string", shading="smooth")
    knot = M.ico(0.016, 1, scale=(1.0, 1.25, 1.0))
    a.add(knot, "glow_string", name="string_knot", shading="smooth")

    # ---- the spectral hex-bolt: shaft, hexagonal bipyramid head, three vanes, nock
    shaft = M.cylinder(0.0095, 0.60, sides=6, axis="Y")
    M.xform(shaft, loc=(0, 0.28, 0))
    a.add(shaft, "glow_bolt", name="bolt_shaft", shading="smooth")
    head = M.lathe([(0.0, 0.555), (0.038, 0.60), (0.03, 0.635), (0.0, BOLT_TIP_Y)], sides=6, cap=False, axis="Z")
    M.xform(head, rot=(-90, 0, 0))
    a.add(head, "glow_bolt", name="bolt_head", shading="flat")
    for k in range(3):
        ang = math.radians(90 + 120 * k)
        vane = M.box((0.004, 0.10, 0.03), taper=(1.0, 0.45), shear=(0.0, -0.02))
        M.xform(vane, loc=(0, 0, 0.015))
        M.xform(vane, matrix=Matrix.Translation((0, 0.085, 0)) @ Matrix.Rotation(ang - math.pi / 2, 4, "Y"))
        a.add(vane, "glow_bolt", name="bolt_vane", shading="flat")

    obj = a.to_object(col)
    obj.data.transform(CANT)
    obj.data.update()
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return obj


# ---- paint -------------------------------------------------------------------------------------------------

LIMB_AXIS = WD((0, 0, 1))
BOW_CENTER = W((0, 0.26, 0))

RECIPES = {
    "wood": P.zone(base="#9C91A3", shadow="#3F3556", light="#D8D0DE", planes=0.07, parts=0.04, edge=0.85,
                   edge_width=0.005, cavity=0.75, ao=0.6, brush=0.04, stroke=LIMB_AXIS, stroke_amount=0.42,
                   stroke_freq=(80.0, 5.0),
                   gradient={"center": BOW_CENTER, "range": (0.30, 0.62), "color": "#8C7CB4", "amount": 0.25}),
    "feather": P.zone(base="#B0A6BC", shadow="#483E68", light="#E6E0EC", planes=0.1, parts=0.1, edge=0.8,
                      edge_width=0.0045, cavity=0.65, ao=0.75, ao_range=(0.12, 0.45), brush=0.03,
                      gradient={"center": BOW_CENTER, "range": (0.5, 0.85), "color": "#8C80D2", "amount": 0.5},
                      emit={"color": "#6E3CE0", "hot": "#8A5CF5", "core": "#B89CFF", "mode": "radial",
                            "center": BOW_CENTER, "radius": 0.86, "fade": (0.84, 0.98), "base_mix": 0.25,
                            "strength": 0.85}),
    "iron": P.zone(base="#35303F", shadow="#120F17", light="#8E849C", planes=0.07, parts=0.05, edge=0.95,
                   edge_width=0.0042, cavity=0.6, ao=0.5, brush=0.05),
    "wrap": P.zone(base="#4E2C48", shadow="#1E0E1C", light="#8C5C80", planes=0.04, edge=0.5, edge_width=0.004,
                   cavity=0.7, ao=0.6, brush=0.05),
    "brass": P.zone(base="#C2A673", shadow="#5E4626", light="#F6E9C2", planes=0.08, edge=0.7, edge_width=0.003,
                    cavity=0.5, ao=0.4),
    "void": P.zone(base="#140B20", shadow="#050308", light="#3A2A52", planes=0.02, edge=0.2, cavity=0.2, ao=0.2,
                   brush=0.02),
    "glow_eye": P.zone(base="#C8A0FF", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"color": "#8A4CFF", "hot": "#9C6BFF", "core": "#E2D6FF", "mode": "flat",
                             "base_mix": 0.2}),
    "glow_string": P.zone(base="#6E3CE0", edge=0.0, cavity=0.0, ao=0.0,
                          emit={"core": "#B89CFF", "hot": "#8A5CF5", "color": "#6E3CE0", "mode": "radial",
                                "center": (0, 0, 0), "radius": 0.62, "base_mix": 0.1}),
    "glow_bolt": P.zone(base="#7040E6", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#F2ECFF", "hot": "#A585FF", "color": "#7040E6", "mode": "plane",
                              "axis": (0, -1, 0), "range": (-BOLT_TIP_Y, -0.05), "base_mix": 0.2}),
}


def decals():
    out = []
    rng = random.Random(11)
    # carved Hexweaver sigils on the visible (-x) face of both limbs: violet lines in a dark groove, faintly lit.
    # Frame: X = limb axis (z), Y = aim (y), Z = -x (projection axis); u x v = z holds: z x y = -x.
    fr = CANT @ Matrix(((0, 0, -1, 0), (0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 0, 1)))
    pts = limb_points(4)
    lines = []
    for sz in (1, -1):
        for u in (0.28, 0.40, 0.56):
            p, t = limb_at(pts, u)
            g = M.rune_glyph(rng, size=0.034, strokes=3)
            ang = math.atan2(t.y, t.z)          # glyph stem along the limb
            ca, sa = math.cos(ang), math.sin(ang)
            for ln in g:
                lines.append([(sz * (p.z + (q[1] * ca - q[0] * sa)), p.y + (q[1] * sa + q[0] * ca)) for q in ln])
    out.append(P.decal_lines(lines, fr, 0.0042, zones=["wood"], color="#7B5CB0", rim="#2A1E3A", rim_width=0.0085,
                             emit={"color": "#6E36C0", "core": "#9E6BFF"}, depth=(0.0, 0.08)))
    # feathers, painted like carved plumes: a pale rachis and two dark splits in the vane, on both faces.
    # The feathers are stacked 5 mm apart across the bow plane, so each decal only takes its own feather's depth.
    fr_back = CANT @ Matrix(((0, 0, 1, 0), (0, -1, 0, 0), (1, 0, 0, 0), (0, 0, 0, 1)))   # X = z, Y = -y, Z = +x
    for k, (fp, w, th) in enumerate(feather_specs()):
        n = len(fp)
        for sz in (1, -1):
            rach = [fp[i] for i in range(1, n - 1)]
            splits = []
            for f, side in ((0.52, 1), (0.7, -1)):
                i = f * (n - 1)
                i0 = int(i)
                p = fp[i0].lerp(fp[i0 + 1], i - i0)
                d = (fp[i0 + 1] - fp[i0]).normalized()
                perp = Vector((0, d.z, -d.y)) * side
                hw = 0.5 * w * (FEATHER_PROF_W[i0] + (FEATHER_PROF_W[i0 + 1] - FEATHER_PROF_W[i0]) * (i - i0))
                e = p + perp * hw * 1.1
                splits.append([e, p + perp * hw * 0.35 - d * 0.02])
            for frame, flip, depth in ((fr, 1, (0.005 * k + 0.0005, 0.005 * k + 0.0125)),
                                       (fr_back, -1, (-0.005 * k + 0.0005, -0.005 * k + 0.0125))):
                def uv(q):
                    return (sz * q.z, flip * q.y)
                out.append(P.decal_lines([[uv(q) for q in rach]], frame, 0.0042, zones=["feather"], color="#FBF7FF",
                                         rim=None, depth=depth, facing=0.3))
                out.append(P.decal_lines([[uv(q) for q in s] for s in splits], frame, 0.0038, zones=["feather"],
                                         color="#5E527A", rim=None, depth=depth, facing=0.3))
    # the wraith's slit pupil in the void eye, and a hexagon engraved round the eye frame
    fe = CANT @ Matrix(((0, 0, -1, EYE[0]), (0, 1, 0, EYE[1]), (1, 0, 0, EYE[2]), (0, 0, 0, 1)))
    slit = [[(-0.022, 0.0), (0.022, 0.0)]]
    out.append(P.decal_lines(slit, fe, 0.006, zones=["void"], color="#E6D6FF", rim="#5A2A9A", rim_width=0.012,
                             emit={"color": "#A45CFF", "core": "#F4EAFF"}, depth=(-0.03, 0.03), facing=0.2))
    hexa = [[(0.084 * math.cos(math.radians(60 * i)), 0.044 * math.sin(math.radians(60 * i))) for i in range(7)]]
    out.append(P.decal_lines(hexa, fe, 0.0035, zones=["iron"], color="#8E6CC8", rim="#0C0910", rim_width=0.007,
                             emit={"color": "#5A2A9A", "core": "#8E5CE0"}, depth=(-0.03, 0.03), facing=0.4))
    # the grip wrap: dark spiral seams (cylinder mapping around the grip axis)
    fg = CANT @ Matrix(((1, 0, 0, 0.0), (0, 1, 0, 0.33), (0, 0, 1, -0.09), (0, 0, 0, 1)))
    r = 0.04
    spiral = []
    for k in range(7):
        v0 = -0.075 + k * 0.022
        spiral.append([(-math.pi * r + i * (2 * math.pi * r) / 12, v0 + i * 0.024 / 12) for i in range(13)])
    out.append(P.decal_lines(spiral, fg, 0.004, zones=["wrap"], color="#1E0E1C", rim=None, mapping="cylinder",
                             radius=r))
    return out


# ---- main ---------------------------------------------------------------------------------------------------

def build_rig(col):
    """Root (grip frame) + mesh + sockets. Returns (root, mesh)."""
    root = C.add_empty(KEY, size=0.1, col=col)
    mesh = build_mesh(col)
    mesh.parent = root
    # sockets (docs/art/WEAPONS.md section 3): children of the root, +Y forward, +Z up
    C.add_empty("grip_R", (0, 0, 0), parent=root, col=col)
    C.add_empty("grip_L", W(GRIP_L), parent=root, col=col)
    C.add_empty("muzzle", W(REST), parent=root, col=col)
    C.add_empty("glow_core", W(HEAD), parent=root, col=col)
    return root, mesh


def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 1024, int)
    C.reset_scene()
    col = C.get_collection(KEY)
    root, mesh = build_rig(col)

    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = P.paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decals=decals(), ao_distance=0.03,
                              ao_samples=24, seed=5)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=__file__,
                         extra={"chassis": {"damage_type": "Void", "style": "Arrow", "fire": "Charge",
                                            "tags": ["charge", "pierce", "thessaly"]},
                                "cant_deg": CANT_DEG,
                                "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")}})
    reports = C.ensure_dir(os.path.join(pack, "reports"))   # gfa_sheet.py does not create the folder
    if not C.flag(argv, "--no-review"):
        review(root, mesh, rep, reports, tex_dir, pack)
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        C.rel(os.path.join(reports, KEY + "_review.png")), C.rel(os.path.join(reports, KEY + "_hold.png"))],
        "Built from code by art/weapons/wraith_bow/source/wraith_bow_build.py (tools/blender/gf_assets).",
        tier=TIER)
    C.log("DONE", KEY)


def review(root, mesh, rep, reports, tex_dir, pack):
    work = C.ensure_dir(os.path.join(pack, "work", "review"))
    notes = [
        "%s tris (two-handed budget 2000-4000) | textures %s | longest extent %.2f m | sockets: %s" % (
            rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
            ", ".join(sorted(rep["sockets"]))),
        "Grip frame: origin = grip_R = right palm at the string's nocking point, Blender +Y = aim (glTF -Z), +Z = up. "
        "grip_L on the riser grip, muzzle at the arrow rest, glow_core in the bolt head. Bow canted %.0f deg about the aim." % CANT_DEG,
        "Status: %s (the user gives the final visual approval)." % rep.get("status", "ai_final_pending_user_approval"),
    ]
    textures = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
    R.review_weapon(KEY, root, mesh, reports, work, "Wraith Bow  (wraith_bow)",
                    "Void | Arrow, Charge 0.8 s x2.5, pierce 2 | tags: charge, pierce, thessaly | silhouette verb: THE DRAW "
                    "(winged recurve at half draw, spectral string + hex-bolt)",
                    swatches=PALETTE, notes=notes, textures=textures)
    hold_sheet(root, mesh, reports, work)


def hold_sheet(root, mesh, reports, work):
    """Extra review: a hero 3/4 render, and the mannequin holding the bow through the in-game camera, zoomed
    (smooth, 4.5x the 1080p scale) for three aims, plus the true-size crops for comparison."""
    scene = bpy.context.scene
    out = {}
    hero = R.turnaround([mesh], work, KEY + "_hero", {"34": (0.45, -0.35, 0.85)}, size=900)
    out["hero"] = hero["34"]
    saved = root.matrix_world.copy()
    sockets = {c.name: c for c in root.children if c.type == "EMPTY"}
    shots = []
    for i, a in enumerate(((1.0, 0.0, 0.0), (0.6, -0.8, 0.0), (-0.7, 0.7, 0.0))):
        root.matrix_world = R.weapon_hold_matrix(a)
        bpy.context.view_layer.update()
        gl = sockets["grip_L"].matrix_world.translation.copy()
        man = R.mannequin(aim_dir=a, grip_r=root.matrix_world.translation, grip_l=gl)
        zoom = R.ingame([mesh], work, "%s_hold%d" % (KEY, i), px=620, view_height=22.0 / 4.5, mannequin_obj=man,
                        target=(0.0, 0.0, 1.0), ink=0.012, silhouette_too=False)
        true = R.ingame([mesh], work, "%s_hold%d_1x" % (KEY, i), px=150, view_height=22.0, mannequin_obj=man,
                        target=(0.0, 0.0, 1.0), silhouette_too=True)
        shots.append((a, zoom["color"], true["color"], true["sil"]))
        C.remove_objects([man])
    root.matrix_world = saved
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    layout = {
        "title": "Wraith Bow  (wraith_bow)  -  held by the 2.2 m mannequin",
        "subtitle": "grip_R (right palm) on the string's nocking point, grip_L (left palm) on the riser grip; "
                    "game camera: orthographic, 55 deg pitch",
        "width": 1600,
        "sections": [
            {"label": "Hero view (toon preview of the final textures)", "height": 520,
             "images": [{"path": out["hero"], "label": "3/4 above"}]},
            {"label": "In-game camera, zoomed 4.5x (smooth render, same angle), three aim directions", "height": 470,
             "images": [{"path": z, "label": "aim (%.1f, %.1f)" % (a[0], a[1])} for a, z, _, _ in shots]},
            {"label": "The same aims at true 1080p size (22 m view height, 49 px/m): 1x, then 3x nearest, then the 3x silhouette",
             "height": None,
             "images": sum([[{"path": t, "label": "1x"}, {"path": t, "label": "3x", "scale": 3},
                             {"path": s, "label": "sil 3x", "scale": 3}] for a, _, t, s in shots], [])},
        ],
        "notes": ["The bow is canted %.0f deg about the aim axis so that the wing-shaped limbs face the 55 deg camera "
                  "for every aim direction." % CANT_DEG],
    }
    R.contact_sheet(layout, os.path.join(reports, "%s_hold.png" % KEY), work)
    # a small stand-alone hero image for the pack README
    import shutil
    shutil.copyfile(out["hero"], os.path.join(reports, "%s_34.png" % KEY))
    return out


if __name__ == "__main__":
    main()
