"""Godsbane Rifle - the PRECISE / PIERCE long rifle, built end to end from code with tools/blender/gf_assets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/weapons/godsbane_rifle.py -- [--size 1024] [--no-review] [--details-only]

(--details-only: paint iteration, renders only the close-up sheet and the 4x in-game hold; no export.)

(art/weapons/godsbane_rifle/godsbane_rifle_build.py is a launcher for this same script.)

Content row (content/sheets/chassis.csv): godsbane_rifle, Kinetic, style Slug, fire Auto, damage 22,
fire rate 3.2, 1 projectile, 1 deg spread, speed 34, range 17, pierce 1, crit 10 % x2.5, precision zone
0.5, tags "precise; pierce" - "The rifle that killed a god. It remembers."

Design (docs/art/WEAPONS.md section 5, family PRECISE / PIERCE):
  * silhouette verb THE NEEDLE: the longest, thinnest line of the arsenal so far (1.6 m, about 78 px
    at 1080p), a crystal scope and a sight blade on top, ONE sharp point at the front (a bone fang
    bayonet under a tapered gold muzzle), nothing sticking out sideways except a short bolt knob;
  * value rhythm: pale god-bone stock -> dark leather grip + dark iron receiver under a cut Kinetic-cream
    crystal scope (three painted facet values and a darker core, no glow) -> dark octagonal barrel framed
    by three gilded lines (two side rails, one top rib) -> gold muzzle crown with a glowing bore and a
    pale bone fang: the brightest values at the front;
  * story ("It remembers"): the stock is a god's femur whose butt ends in the bone's double knuckle,
    a carved god-eye with a faintly glowing slit iris sits on both stock sides, and three large
    engraved Kinetic sigils (forked stave, god-eye, fang) sit on the barrel between the gold bands;
  * palette: the warm metals of the player's arsenal (bone-ivory, gold, dark iron, dark leather) + the
    Kinetic element cream #F4E3C1 (palette.rs element_color) for every glow.

Grip frame (docs/art/WEAPONS.md section 2): origin = palm centre of the right hand on the pistol grip,
+Y = barrel, +Z = up, +X = the weapon's right. Bore axis 0.085 m above the palm.
Outputs: assets/models/weapons/godsbane_rifle.glb (+ .meta.json), art/weapons/godsbane_rifle/
{source/*.blend, textures/*.png, reports/*.png, status.json}.
Based on tools/blender/gf_assets/weapons/sunspike_shotgun.py (the toolkit's worked example).
"""
import math
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY, KIND, TIER = "godsbane_rifle", "weapon", "two_handed"
AX = 0.085                      # bore axis height above the palm centre (m)
MUZZLE_Y = 1.118                # bore exit at the tip of the gold crown (the muzzle socket)
FANG_TIP_Y = 1.20               # the one sharp point
BUTT_Y = -0.405                 # back of the femur knuckle
GRIP_L = (0.0, 0.40, AX - 0.058)            # palm centre of the left hand under the bone forend
SCOPE_Z = AX + 0.074                        # crystal axis height
SCOPE = (0.0, 0.058, SCOPE_Z)               # crystal centre (glow_core)
EJECT = (0.03, 0.075, AX + 0.012)           # ejection port, right side of the receiver
REVIEW_PX = 190                 # in-game crop (1080p px): 150 px cut the 1.6 m rifle's muzzle off

FANG = [(0, 0.95, AX - 0.037), (0, 1.03, AX - 0.041), (0, 1.11, AX - 0.037), (0, FANG_TIP_Y, AX - 0.025)]

ZONES = ["bone", "leather", "iron", "gold", "crystal", "fang", "glow_bore", "glow_ring"]
PALETTE = [  # (name, hex) for the review sheet
    ("bone", "#E3D4B4"), ("bone shadow", "#8A6A4C"), ("leather", "#4A2622"), ("iron", "#3E3746"),
    ("gold", "#E4B24A"), ("crystal lit", "#E0CA9C"), ("crystal flank", "#957250"), ("crystal pavilion", "#43375A"),
    ("crystal core", "#5E4230"), ("glow rim", "#D8B679"), ("kinetic", "#F4E3C1"), ("core", "#FFFFFF"),
]

# barrel radius (to the octagon's corners) along +Y: chamber, taper, muzzle
BARREL = [(0.19, 0.031), (0.27, 0.031), (0.32, 0.0272), (0.99, 0.0205)]
OCT = math.cos(math.radians(22.5))          # octagon flat / corner radius


def barrel_r(y):
    for (y0, r0), (y1, r1) in zip(BARREL[:-1], BARREL[1:]):
        if y <= y1:
            t = max(0.0, (y - y0) / (y1 - y0))
            return r0 + (r1 - r0) * t
    return BARREL[-1][1]


# femur stock sections: (y, top z, bottom z, width x) from the receiver back to the knuckle
STOCK = [(-0.055, AX + 0.030, AX - 0.040, 0.047), (-0.12, AX + 0.021, AX - 0.031, 0.040),
         (-0.20, AX + 0.018, AX - 0.045, 0.041), (-0.27, AX + 0.019, AX - 0.068, 0.046),
         (-0.325, AX + 0.024, AX - 0.096, 0.056), (-0.352, AX + 0.026, AX - 0.108, 0.058)]


def stock_at(y):
    """(centre z, height, width) of the stock at y (linear between the sections)."""
    S = STOCK
    for a, b in zip(S[:-1], S[1:]):
        if a[0] >= y >= b[0]:
            t = (a[0] - y) / (a[0] - b[0])
            top = a[1] + (b[1] - a[1]) * t
            bot = a[2] + (b[2] - a[2]) * t
            w = a[3] + (b[3] - a[3]) * t
            return (top + bot) / 2, top - bot, w
    top, bot, w = (S[0][1], S[0][2], S[0][3]) if y > S[0][0] else (S[-1][1], S[-1][2], S[-1][3])
    return (top + bot) / 2, top - bot, w


# ---- geometry ---------------------------------------------------------------------------------------------

def ellip_tube(points, heights, widths, sides=10):
    """Tube along points with elliptical sections (height along +Z, width along X)."""
    radii = [h / 2 for h in heights]
    sc = [(1.0, (w / h) if h > 1e-6 else 1.0) for h, w in zip(heights, widths)]
    return M.tube(points, radii, sides=sides, up=(0, 0, 1), scale_xy=sc)


# the crystal's rings along +Y: (y, radius, rotation in degrees); a point at each end
CRYSTAL = [(-0.090, 0.0175, 0.0), (-0.052, 0.0222, 30.0), (0.056, 0.0240, 0.0), (0.164, 0.0222, 30.0),
           (0.204, 0.0172, 0.0)]
CRYSTAL_TIPS = (-0.128, 0.25)


def crystal_mesh():
    """A hand-cut quartz: an irregular hexagon section (alternating wide / narrow facets, a ridge on top)
    whose rings turn 30 degrees against each other, so every band between two rings is cut into twelve
    triangular facets (kites and diamonds along the body) with a pointed termination at each end. The
    cut facets each take one painted value; a straight prism read as a round rod, whatever its paint."""
    bm = bmesh.new()
    rings = []
    for y, r, rot in CRYSTAL:
        ring = []
        for k in range(6):
            ang = math.radians(60 * k + (10 if k % 2 else -10) + rot)
            rk = 1.0 if k % 2 == 0 else 0.86
            ring.append(bm.verts.new((math.sin(ang) * r * rk, y, SCOPE_Z + math.cos(ang) * r * rk)))
        rings.append(ring)
    for A, B in zip(rings[:-1], rings[1:]):
        # the ring with the larger rotation sits half a facet ahead: B[k] lies between A[k] and A[k + 1]
        lead, trail = (B, A) if CRYSTAL[rings.index(B)][2] > CRYSTAL[rings.index(A)][2] else (A, B)
        for k in range(6):
            k1 = (k + 1) % 6
            if lead is B:
                bm.faces.new((A[k], A[k1], B[k]))
                bm.faces.new((A[k1], B[k1], B[k]))
            else:
                bm.faces.new((B[k], B[k1], A[k]))
                bm.faces.new((B[k1], A[k1], A[k]))
    for y, ring in ((CRYSTAL_TIPS[0], rings[0]), (CRYSTAL_TIPS[1], rings[-1])):
        tip = bm.verts.new((0.0, y, SCOPE_Z))
        for k in range(6):
            bm.faces.new((ring[k], ring[(k + 1) % 6], tip))
    return M.recalc(bm)


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES)

    # -- god-bone stock: a femur. Shaft thin at the wrist, flaring to a double knuckle at the butt --
    ys = [s[0] for s in STOCK]
    pts, hs, ws = [], [], []
    for y in ys:
        cz, h, w = stock_at(y)
        pts.append((0, y, cz))
        hs.append(h)
        ws.append(w)
    stock = ellip_tube(pts, hs, ws, sides=12)
    M.noise_displace(stock, 0.0016, freq=16.0, seed=4)   # carved, not machined
    a.add(stock, "bone", name="stock", shading="smooth")
    # the femur knuckle: heel and toe condyles, the intercondylar notch between them
    for zc, r, nm in ((AX + 0.007, 0.034, "condyle_heel"), (AX - 0.086, 0.038, "condyle_toe")):
        s = M.sphere(r, 12, 8, scale=(0.8, 1.22, 1.0))
        M.xform(s, loc=(0, BUTT_Y + r * 1.22, zc))
        a.add(s, "bone", name=nm, shading="smooth")
    # gold bindings: at the wrist and before the knuckle
    for y, L in ((-0.098, 0.022), (-0.33, 0.02)):
        cz, h, w = stock_at(y)
        b = ellip_tube([(0, y + L / 2, cz), (0, y - L / 2, cz)], [h + 0.010] * 2, [w + 0.010] * 2, sides=12)
        a.add(b, "gold", name="binding")

    # -- pistol grip: dark leather over bone, raked back, bone knuckle pommel --
    gp = [(0, -0.043, -0.078), (0, -0.018, -0.02), (0, 0.004, 0.03), (0, 0.016, AX - 0.028)]
    grip = M.tube(gp, [0.023, 0.025, 0.024, 0.024], sides=10, up=(0, 1, 0),
                  scale_xy=[(1.0, 0.72)] * 4)
    a.add(grip, "leather", name="grip", shading="smooth")
    gax = (Vector(gp[-1]) - Vector(gp[0])).normalized()
    for t in (0.22, 0.5, 0.78):
        p0 = Vector(gp[0]).lerp(Vector(gp[-1]), t)
        # thin raised wrap ridges (leather strap edges), tilted 12 deg off the grip axis like a real wrap
        ring = M.tube([p0 - gax * 0.0045, p0 + gax * 0.0045], 0.0268, sides=10, up=(0, 1, 0),
                      scale_xy=[(1.0, 0.76)] * 2)
        M.xform(ring, matrix=Matrix.Translation(p0) @ Matrix.Rotation(math.radians(12), 4, "X")
                @ Matrix.Translation(-p0))
        a.add(ring, "leather", name="wrap")
    pom = M.sphere(0.024, 10, 6, scale=(0.85, 1.25, 0.8))
    M.xform(pom, loc=(0, -0.047, -0.088), rot=(-21, 0, 0))
    a.add(pom, "bone", name="pommel", shading="smooth")
    fer = M.cylinder(0.025, 0.012, sides=10, axis="Z")
    M.xform(fer, loc=(0, -0.041, -0.072), rot=(-21, 0, 0), scale=(0.8, 1.05, 1))
    a.add(fer, "gold", name="pommel_ring")

    # -- receiver: a lean dark iron block, tapered top --
    rec = M.box((0.052, 0.28, 0.074), bevel=0.009, segments=2, taper=(0.84, 0.985))
    M.xform(rec, loc=(0, 0.065, AX - 0.003))
    a.add(rec, "iron", name="receiver")
    # tang: the receiver's lower rear runs into the grip
    tang = M.box((0.044, 0.07, 0.03), bevel=0.006, taper=(1.0, 1.0))
    M.xform(tang, loc=(0, -0.01, AX - 0.045))
    a.add(tang, "iron", name="tang")
    # gold trim strip along both lower edges of the receiver
    for sx in (-1, 1):
        tr = M.box((0.006, 0.25, 0.012), bevel=0.0025)
        M.xform(tr, loc=(sx * 0.0255, 0.07, AX - 0.028))
        a.add(tr, "gold", name="trim")
    # bolt: short stem on the right, bone knob (the only thing that leaves the line, and barely)
    bolt = M.tube([(0.02, -0.03, AX + 0.012), (0.046, -0.04, AX + 0.0), (0.056, -0.048, AX - 0.018)],
                  [0.0065, 0.006, 0.0055], sides=6)
    a.add(bolt, "iron", name="bolt", shading="smooth")
    knob = M.sphere(0.0135, 8, 6)
    M.xform(knob, loc=(0.058, -0.05, AX - 0.024))
    a.add(knob, "bone", name="bolt_knob", shading="smooth")
    # trigger guard (gold strap) and trigger
    guard = M.catmull([(0, 0.03, AX - 0.04), (0, 0.032, AX - 0.068), (0, 0.062, AX - 0.088),
                       (0, 0.1, AX - 0.074), (0, 0.112, AX - 0.04)], 3)
    a.add(M.band(guard, 0.014, 0.0065, up=(1, 0, 0)), "gold", name="guard")
    a.add(M.horn([(0, 0.066, AX - 0.04), (0, 0.062, AX - 0.058), (0, 0.07, AX - 0.074)], 0.0055, 0.0025, sides=5),
          "iron", name="trigger", shading="smooth")

    # -- crystal scope: a long faceted Kinetic crystal held by gold claw rings --
    a.add(crystal_mesh(), "crystal", name="crystal", shading="flat")
    for y in (-0.04, 0.152):
        rg = M.ring(0.0185, 0.0275, 0.018, sides=12, bevel=0.002, axis="Y")
        M.xform(rg, loc=(0, y, SCOPE_Z))
        a.add(rg, "gold", name="scope_ring")
        post = M.box((0.016, 0.014, SCOPE_Z - 0.024 - (AX + 0.033) + 0.004), bevel=0.003)
        M.xform(post, loc=(0, y, (SCOPE_Z - 0.024 + AX + 0.033) / 2))
        a.add(post, "gold", name="scope_post")
    # prong claws gripping the crystal's front tip (converging like a gem setting)
    for y0, sgn in ((0.186, 1),):
        for k in range(4):
            ang = math.radians(45 + 90 * k)
            radial = Vector((math.cos(ang), 0, math.sin(ang)))
            d = (-radial * 0.3 + Vector((0, sgn, 0))).normalized()
            sp = M.spike(0.0065, 0.036, sides=4, base_scale=(1.0, 0.5), rot_offset=0)
            M.xform(sp, matrix=M.orient(Vector((0, y0, SCOPE_Z)) + radial * 0.0205, d, (-radial.z, 0, radial.x)))
            a.add(sp, "gold", name="claw")
    # eyepiece cup at the back of the crystal
    cup = M.lathe([(0.014, -0.1), (0.022, -0.092), (0.0235, -0.078), (0.019, -0.072)], sides=12, cap=False)
    M.xform(cup, rot=(-90, 0, 0))
    M.xform(cup, loc=(0, 0, SCOPE_Z))
    a.add(cup, "gold", name="scope_cup", shading="smooth")

    # -- barrel: long octagonal dark iron, tapering toward the muzzle --
    bar = M.lathe([(r, y) for y, r in BARREL], sides=8, cap=True, start_angle=22.5)
    M.xform(bar, rot=(-90, 0, 0))
    M.xform(bar, loc=(0, 0, AX))
    a.add(bar, "iron", name="barrel", shading="auto")
    # gilded rails: two side rails at bore height + a top rib, all converging with the taper
    ys = [0.2, 0.27, 0.32, 0.62, 0.95]
    for sx in (-1, 1):
        secs = []
        for y in ys:
            t = (y - ys[0]) / (ys[-1] - ys[0])
            hw = 0.0056 - 0.0014 * t
            secs.append((y, hw * 2, 0.0125 - 0.003 * t, sx * (barrel_r(y) * OCT + 0.0016 + hw), AX))
        a.add(M.loft_rect(secs, bevel=0.0018), "gold", name="rail")
    secs = []
    for y in ys:
        t = (y - ys[0]) / (ys[-1] - ys[0])
        h = 0.0095 - 0.002 * t
        secs.append((y, 0.012 - 0.002 * t, h, 0, AX + barrel_r(y) * OCT + h / 2 - 0.0012))
    a.add(M.loft_rect(secs, bevel=0.0018), "gold", name="top_rib")
    # bands: breech collar, two barrel bands holding the rails
    for y, L in ((0.212, 0.032), (0.47, 0.02), (0.77, 0.02)):
        br = barrel_r(y)
        rail_out = br * OCT + 0.0016 + 0.0112
        r_out = (rail_out + 0.0035) / OCT
        rg = M.ring(br - 0.002, r_out, L, sides=8, bevel=0.0022, axis="Y", start_angle=22.5)
        M.xform(rg, loc=(0, y, AX))
        a.add(rg, "gold", name="band")

    # -- bone forend under the barrel, ending in a small forward claw --
    fy = [0.2, 0.3, 0.44, 0.56, 0.64]
    fz = [AX - 0.028, AX - 0.029, AX - 0.028, AX - 0.026, AX - 0.024]
    fh = [0.05, 0.047, 0.042, 0.033, 0.0]
    fw = [0.05, 0.047, 0.043, 0.034, 0.0]
    fore = M.tube([(0, y, z) for y, z in zip(fy, fz)], [h / 2 for h in fh], sides=10, up=(0, 0, 1),
                  scale_xy=[(1.0, (w / h) if h else 1.0) for h, w in zip(fh, fw)])
    M.noise_displace(fore, 0.0012, freq=18.0, seed=9)
    a.add(fore, "bone", name="forend", shading="smooth")

    # -- muzzle: a tapered gold crown narrowing to the bore (the needle point) --
    crown = M.lathe([(0.019, 0.948), (0.031, 0.953), (0.0345, 0.968), (0.0335, 0.99), (0.0262, 1.0),
                     (0.0242, 1.03), (0.0175, 1.08), (0.0112, MUZZLE_Y)], sides=10, cap=False, start_angle=18.0)
    M.xform(crown, rot=(-90, 0, 0))
    M.xform(crown, loc=(0, 0, AX))
    a.add(crown, "gold", name="crown", shading="auto", sharp_angle=25.0)
    # the bore: a convex glowing "pupil" just proud of the crown, so the shot's origin glows from the side too
    bore = M.lathe([(0.0112, MUZZLE_Y), (0.0086, MUZZLE_Y + 0.0045), (0.0, MUZZLE_Y + 0.007)], sides=10, cap=False,
                   start_angle=18.0)
    M.xform(bore, rot=(-90, 0, 0))
    M.xform(bore, loc=(0, 0, AX))
    a.add(bore, "glow_bore", name="bore", shading="smooth")
    # a thin glowing Kinetic band set into the crown's taper: the muzzle's bright point from every side
    gr = M.ring(0.019, 0.0238, 0.007, sides=10, axis="Y", start_angle=18.0)
    M.xform(gr, loc=(0, 1.042, AX))
    a.add(gr, "glow_ring", name="glow_ring", shading="smooth")
    # front sight blade on the rib, raked forward
    blade = M.box((0.005, 0.046, 0.03), taper=(1.0, 0.22), shear=(0.0, 0.014), bevel=0.0012)
    M.xform(blade, loc=(0, 0.905, AX + barrel_r(0.905) * OCT + 0.008 + 0.013))
    a.add(blade, "gold", name="sight_blade")

    # -- the fang: a god's tooth set under the muzzle, the one sharp point --
    lug = M.box((0.017, 0.052, 0.022), bevel=0.003)
    M.xform(lug, loc=(0, 0.965, AX - 0.03))
    a.add(lug, "gold", name="fang_lug")
    fang = M.tube(FANG, [0.0135, 0.0125, 0.0085, 0.0], sides=6, up=(0, 0, 1), scale_xy=[(1.0, 0.45)] * 4)
    a.add(fang, "fang", name="fang", shading="auto")

    obj = a.to_object(col)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return obj


# ---- paint -------------------------------------------------------------------------------------------------

RECIPES = {
    "bone": P.zone(base="#D9C6A2", shadow="#7A5A40", light="#F6ECD4", planes=0.05, parts=0.04, brush=0.06,
                   brush_freq=8.0, stroke=(0, 1, 0), stroke_amount=0.22, stroke_freq=(110.0, 5.0), cavity=0.7,
                   ao=0.7, edge=0.55, edge_width=0.004,
                   gradient={"axis": (0, 1, 0), "range": (-0.18, -0.40), "color": "#A98B63", "amount": 0.32},
                   spots={"color": "#A88A60", "amount": 0.4, "freq": 9.0, "threshold": (0.6, 0.74)}),
    "leather": P.zone(base="#4A2622", shadow="#1C0C0B", light="#8A5040", planes=0.05, edge=0.6, edge_width=0.003,
                      cavity=0.7, ao=0.5, stroke=(0, 0.35, 0.94), stroke_amount=0.25, stroke_freq=(140.0, 8.0)),
    "iron": P.zone(base="#3E3746", shadow="#17121B", light="#9A8FA6", planes=0.08, parts=0.04, edge=0.95,
                   edge_width=0.0038, cavity=0.6, ao=0.5, brush=0.05),
    "gold": P.zone(base="#E4B24A", shadow="#86511A", light="#FFF2BE", planes=0.08, edge=0.8, edge_width=0.0032,
                   cavity=0.6, ao=0.5,
                   spots={"color": "#B97F2E", "amount": 0.25, "freq": 16.0, "threshold": (0.62, 0.74)}),
    # the crystal is PAINTED as a faceted gem in three Kinetic-cream value planes picked by facet orientation
    # (lit cream table on top, warm tan flanks, violet pavilion underneath) with a darker core in the middle of
    # its length, so it reads as a cut stone and never as a white tube. It carries almost no emission (a few
    # small glints, see decals()): the brightest value of the rifle stays at the muzzle.
    "crystal": P.zone(base="#B8976A", shadow="#3F3452", light="#F2DEB4",
                      facets={"dir": (0, 0, 1), "soft": 0.04,
                              "stops": [(-1.0, "#43375A"), (-0.42, "#957250"), (0.45, "#E0CA9C")]},
                      planes=0.1, parts=0.0, brush=0.05, brush_freq=11.0, edge=0.85, edge_width=0.0032,
                      edge_breakup=0.15, cavity=0.0, ao=0.35,
                      gradient={"center": SCOPE, "range": (0.085, 0.035), "color": "#5E4230", "amount": 0.5}),
    "fang": P.zone(base="#EDE2C8", shadow="#8C7254", light="#FFFBF0", planes=0.07, edge=0.9, edge_width=0.004,
                   cavity=0.5, ao=0.45, edge_breakup=0.3,
                   gradient={"axis": (0, 1, 0), "range": (0.98, 1.18), "color": "light", "amount": 0.55}),
    "glow_bore": P.zone(base="#F4E3C1", emit={"core": "#FFFFFF", "hot": "#F4E3C1", "color": "#E0BF84", "mode": "axis",
                                              "center": (0, MUZZLE_Y, AX), "axis": (0, 1, 0), "radius": 0.0112}),
    "glow_ring": P.zone(base="#F4E3C1", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#FFF4D6", "hot": "#F4E3C1", "color": "#D9B77E", "mode": "flat",
                              "base_mix": 0.1}),
}


def _side_frame(sx, origin):
    """Planar decal frame on the weapon's side sx (+1 right, -1 left): u along +Y*sx, v up, z out."""
    u = Vector((0, sx, 0))
    v = Vector((0, 0, 1))
    z = u.cross(v)
    fr = Matrix(((u.x, v.x, z.x, 0), (u.y, v.y, z.y, 0), (u.z, v.z, z.z, 0), (0, 0, 0, 1)))
    return Matrix.Translation(Vector(origin)) @ fr


def god_eye(w=0.074, h_up=0.018, h_dn=0.013, iris=0.0105, n=9):
    """The carved god-eye (almond lids, slit pupil, five lash rays) as 2D polylines; iris circle apart."""
    hw = w / 2
    up = [(-hw + w * i / (n - 1), h_up * (1 - ((-hw + w * i / (n - 1)) / hw) ** 2)) for i in range(n)]
    dn = [(-hw + w * i / (n - 1), -h_dn * (1 - ((-hw + w * i / (n - 1)) / hw) ** 2)) for i in range(n)]
    tail = [(-hw, 0.0), (-hw - 0.014, -0.004), (-hw - 0.022, -0.001)]
    lashes = []
    for k in range(5):
        ang = math.radians(50 + 20 * k)
        x0 = math.cos(ang) * hw * 0.62
        y0 = h_up * (1 - (x0 / hw) ** 2)
        lashes.append([(x0, y0 + 0.003), (x0 + math.cos(ang) * 0.011, y0 + 0.003 + math.sin(ang) * 0.011)])
    pupil = [[(0.0, -iris * 0.8), (0.0, iris * 0.8)]]
    ring = [[(iris * math.cos(math.radians(a)), iris * math.sin(math.radians(a))) for a in range(0, 361, 24)]]
    return [up, dn, tail] + lashes, ring, pupil


def barrel_glyphs(hu=0.0055, hv=0.014):
    """The three barrel sigils as 2D polylines, u across the flat, v along the barrel (+v = toward the muzzle):
    the forked stave (the god that fell), the god-eye lozenge (it remembers) and the fang, a tooth-shaped
    triangle pointing at the muzzle (the kill). Big, simple, angular shapes spaced far apart, so the 0.0042 m
    engraving reads as three carved sigils and not as a line of type."""
    stave = [[(0.0, -hv), (0.0, hv)], [(-hu, -hv), (0.0, -0.0025)], [(hu, -hv), (0.0, -0.0025)]]
    eye = [[(0.0, -hv), (hu, 0.0), (0.0, hv), (-hu, 0.0), (0.0, -hv)]]
    fang = [[(-hu, -hv), (0.0, hv), (hu, -hv), (-hu, -hv)]]
    return stave, eye, fang


def decals():
    out = []
    # the god-eye on both stock sides: gold inlay in a burnt carved groove, the slit iris glows faintly
    ey = -0.235
    cz, _, _ = stock_at(ey)
    for sx in (-1, 1):
        fr = _side_frame(sx, (0, ey, cz - 0.004))
        lids, ring, pupil = god_eye()
        # mirror so the tail points back (toward the butt) on both sides
        lids = [[(p[0] * sx, p[1]) for p in ln] for ln in lids]
        out.append(P.decal_lines(lids, fr, 0.0036, zones=["bone"], color="#C9922E", rim="#3A2414",
                                 rim_width=0.0075, depth=(0.0, 0.06)))
        out.append(P.decal_lines(ring, fr, 0.0032, zones=["bone"], color="#D9A444", rim="#3A2414",
                                 rim_width=0.006, depth=(0.0, 0.06)))
        out.append(P.decal_lines(pupil, fr, 0.0038, zones=["bone"], color="#FFF6DC", rim="#2A160C",
                                 rim_width=0.007, depth=(0.0, 0.06), emit={"color": "#D8B679", "core": "#FFF6DC"}))
    # the fang's fuller: a glowing Kinetic line etched along both flat sides (the muzzle's bright point)
    cl = [p for p in M.catmull(FANG, 6) if 0.972 <= p.y <= 1.168]
    for sx in (-1, 1):
        fr = _side_frame(sx, (0, 0, 0))
        line = [[(p.y * sx, p.z + 0.001) for p in cl]]
        out.append(P.decal_lines(line, fr, 0.0036, zones=["fang"], color="#FFF6DC", rim="#6E5238", rim_width=0.0068,
                                 depth=(0.0, 0.03), emit={"color": "#E0BF84", "core": "#FFFFFF"}))
    # the crystal: no glowing streaks (they bleached it into a white tube). Short painted glints on a few facet
    # edges toward the ends, where the stone is lightest, with only a dim warm emission
    for sx in (-1, 1):
        fr = _side_frame(sx, (0, 0, 0))
        glints = [[((y - 0.008) * sx, SCOPE_Z - 0.005), ((y + 0.008) * sx, SCOPE_Z + 0.005)] for y in (-0.068, 0.178)]
        out.append(P.decal_lines(glints, fr, 0.003, zones=["crystal"], color="#FFF6E2", depth=(0.0, 0.04),
                                 emit={"color": "#3A2E1E", "core": "#8C7450"}))
    top = Matrix(((0, -1, 0, 0), (1, 0, 0, 0), (0, 0, 1, SCOPE_Z), (0, 0, 0, 1)))   # u = +Y, v = -X, out = +Z
    tg = [[(0.168, 0.006), (0.19, 0.004)], [(-0.078, -0.006), (-0.062, -0.007)]]
    out.append(P.decal_lines(tg, top, 0.003, zones=["crystal"], color="#FFF6E2", depth=(0.0, 0.04),
                             emit={"color": "#3A2E1E", "core": "#8C7450"}))
    # four glowing channels running up the muzzle crown's taper to the bore
    cfr = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, AX), (0, 0, 0, 1)))
    ch = [[(math.radians(a) * 0.018, 1.052), (math.radians(a) * 0.018, 1.109)] for a in (-135.0, -45.0, 45.0, 135.0)]
    out.append(P.decal_lines(ch, cfr, 0.0034, zones=["gold"], color="#FFF1CC", rim="#7A4A1A", rim_width=0.006,
                             mapping="cylinder", radius=0.018, emit={"color": "#D9B77E", "core": "#FFF4D6"}))
    # hairline cracks in the god-bone (it did not survive the god unmarked)
    for sx, seed in ((-1, 21), (1, 5)):
        crng = random.Random(seed)
        fr = _side_frame(sx, (0, 0, 0))
        cr = M.crack_lines(crng, start=(-0.338, AX + 0.02), direction=-28.0, length=0.07, step=0.007, jag=0.5,
                           branches=1, branch_len=0.45, depth=1)
        cr += M.crack_lines(crng, start=(-0.155, AX - 0.03), direction=150.0, length=0.045, step=0.006, jag=0.5,
                            branches=1, branch_len=0.4, depth=1)
        cr = [[(p[0] * sx, p[1]) for p in ln] for ln in cr]
        out.append(P.decal_lines(cr, fr, 0.0017, zones=["bone"], color="#4E3624", rim="#9C7E58",
                                 rim_width=0.0038, depth=(0.0, 0.06)))
    # "It remembers": three large engraved Kinetic glyphs on each upper barrel flat between the two bands,
    # widely spaced so they read as sigils, not as a line of text (the old nine-glyph rune band did)
    fr = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, AX), (0, 0, 0, 1)))   # x = +X, y = -Z, z = +Y (barrel axis)
    rr = 0.024
    for ang_deg in (-45.0, -135.0):
        su = 1.0 if ang_deg == -45.0 else -1.0          # mirror across the rib so both flats read the same way
        lines = []
        for yc, glyph in zip((0.548, 0.622, 0.696), barrel_glyphs()):
            lines += [[(ang_deg * math.pi / 180.0 * rr + p[0] * su, yc + p[1]) for p in ln] for ln in glyph]
        out.append(P.decal_lines(lines, fr, 0.0042, zones=["iron"], color="#B09470", rim="#15101A",
                                 rim_width=0.0068, mapping="cylinder", radius=rr,
                                 emit={"color": "#3E3222", "core": "#A08868"}))
    # engraved gold border on both receiver sides (classic engraved action)
    y0, y1, z0, z1, c = -0.012, 0.172, AX - 0.013, AX + 0.021, 0.008
    border = [[(y0 + c, z0), (y1 - c, z0), (y1, z0 + c), (y1, z1 - c), (y1 - c, z1), (y0 + c, z1), (y0, z1 - c),
               (y0, z0 + c), (y0 + c, z0)]]
    ym, zm = (y0 + y1) / 2, (z0 + z1) / 2
    lozenge = [[(ym - 0.022, zm), (ym, zm + 0.009), (ym + 0.022, zm), (ym, zm - 0.009), (ym - 0.022, zm)],
               [(y0 + 0.012, zm), (ym - 0.03, zm)], [(ym + 0.03, zm), (y1 - 0.012, zm)]]
    for sx in (-1, 1):
        fr = _side_frame(sx, (0, 0, 0))
        lines = [[(p[0] * sx, p[1]) for p in ln] for ln in border + lozenge]
        out.append(P.decal_lines(lines, fr, 0.0026, zones=["iron"], color="#C9922E", rim="#120E16",
                                 rim_width=0.005, depth=(0.015, 0.04)))
    return out


# ---- extra review images -------------------------------------------------------------------------------------

WIDE_VIEWS = {"side_R": (1.0, 0.0, 0.06), "34_front": (0.62, 0.62, 0.48), "side_L": (-1.0, 0.0, 0.06),
              "34_back_top": (-0.55, -0.45, 0.7)}


def wide_views(mesh, work, reports, w=1500, h=380, ink=0.0035, samples=16):
    """Wide toon-preview renders (a 1.6 m rifle is lost in square tiles): one per WIDE_VIEWS entry, each
    fitted to a w x h frame, stacked into <reports>/<key>_views.png with gfa_sheet (PIL)."""
    scene = bpy.context.scene
    pts = R._points([mesh])
    R.setup_cycles(scene, samples)
    paths = {}
    with R.toon_preview([mesh], ink=ink):
        for name, d in WIDE_VIEWS.items():
            c, ew, eh = R.frame(pts, d)
            R.aim(scene, c, d, max(ew * 1.06, eh * 1.12 * w / h))
            scene.render.resolution_x, scene.render.resolution_y = w, h
            scene.render.resolution_percentage = 100
            scene.render.filepath = os.path.join(work, "%s_wide_%s.png" % (KEY, name))
            bpy.ops.render.render(write_still=True)
            paths[name] = scene.render.filepath
    layout = {"title": "Godsbane Rifle  (godsbane_rifle)",
              "subtitle": "Toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6), 1.60 m",
              "width": w + 40,
              "sections": [{"label": n.replace("_", " "), "height": h, "images": [{"path": p, "label": ""}]}
                           for n, p in paths.items()],
              "swatches": [{"hex": x, "label": n} for n, x in PALETTE], "notes": []}
    return R.contact_sheet(layout, os.path.join(reports, "%s_views.png" % KEY), work)

# close-ups: name -> (camera direction, y range, z range, width, height) of the region to frame
DETAIL_VIEWS = {
    "scope_34_above": ((0.62, 0.45, 0.64), (-0.135, 0.255), (AX + 0.03, 1.0), 740, 440),
    "scope_side_R": ((1.0, 0.0, 0.06), (-0.135, 0.255), (AX + 0.03, 1.0), 740, 440),
    "barrel_sigils_above_R": ((0.5, 0.0, 0.87), (0.46, 0.785), (-1.0, 1.0), 1500, 330),
}


def detail_views(mesh, work, reports, ink=0.0012, samples=16):
    """Close-up toon-preview renders of the crystal scope and the barrel sigils (the details a 1.6 m rifle
    loses in the whole-weapon views), stacked into <reports>/<key>_details.png."""
    scene = bpy.context.scene
    pts = R._points([mesh])
    R.setup_cycles(scene, samples)
    paths = {}
    with R.toon_preview([mesh], ink=ink):
        for name, (d, yr, zr, w, h) in DETAIL_VIEWS.items():
            sub = [p for p in pts if yr[0] <= p.y <= yr[1] and zr[0] <= p.z <= zr[1]]
            c, ew, eh = R.frame(sub, d)
            R.aim(scene, c, d, max(ew * 1.08, eh * 1.2 * w / h))
            paths[name] = R.render(scene, os.path.join(work, "%s_detail_%s.png" % (KEY, name)), w, h)
    layout = {"title": "Godsbane Rifle  (godsbane_rifle): details",
              "subtitle": "Toon preview close-ups of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
              "width": 1540,
              "sections": [
                  {"label": "Crystal scope: cut facets in three Kinetic-cream values, a darker core, small glints (no glow)",
                   "height": 440, "images": [{"path": paths["scope_34_above"], "label": "3/4 from above"},
                                             {"path": paths["scope_side_R"], "label": "right side"}]},
                  {"label": "Barrel sigils between the bands: forked stave, god-eye, fang pointing at the muzzle",
                   "height": 330, "images": [{"path": paths["barrel_sigils_above_R"], "label": "from above right"}]}],
              "swatches": [{"hex": x, "label": n} for n, x in PALETTE], "notes": []}
    return R.contact_sheet(layout, os.path.join(reports, "%s_details.png" % KEY), work)


def relayout_review(work, reports):
    """Re-flow the standard review sheet: with the 190 px in-game crop the 3x game-size silhouettes no longer fit
    beside the side / top silhouettes and wrapped onto a half-empty row; show them at 2x instead."""
    spec = os.path.join(work, "%s_review_layout.json" % KEY)
    layout = C.read_json(spec)
    for sec in layout["sections"]:
        if sec["label"].startswith("Silhouette"):
            sec["label"] = "Silhouette: flat side / top, and the game-size silhouettes (2x)"
            for im in sec["images"]:
                if im.get("scale") == 3:
                    im["scale"] = 2
                    im["label"] = im["label"].replace("3x", "2x")
    return R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)


def hold_closeup(root, mesh, work, reports, aim=(1.0, 0.0, 0.0), scale=4, px=None,
                 view_height=SPEC.GAME_VIEW_HEIGHTS[0]):
    """The review's in-game shot (55 deg ortho, mannequin holding the weapon at its grip frame) rendered at
    `scale` x the 1080p resolution with the SAME framing: what the 1x pixels are made of."""
    px = px or REVIEW_PX
    saved = root.matrix_world.copy()
    socks = {c.name: c for c in root.children if c.type == "EMPTY"}
    root.matrix_world = R.weapon_hold_matrix(aim)
    bpy.context.view_layer.update()
    man = R.mannequin(aim_dir=aim, grip_r=root.matrix_world.translation,
                      grip_l=socks["grip_L"].matrix_world.translation.copy())
    r = R.ingame([mesh], work, "%s_hold_x%d" % (KEY, scale), px=px * scale, view_height=view_height / scale,
                 mannequin_obj=man, target=(0.0, 0.0, 1.0), silhouette_too=False, samples=24)
    C.remove_objects([man])
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    root.matrix_world = saved
    bpy.context.view_layer.update()
    dst = os.path.join(reports, "%s_hold_ingame_x%d.png" % (KEY, scale))
    shutil.copyfile(r["color"], dst)
    return dst


# ---- main ---------------------------------------------------------------------------------------------------

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
    C.add_empty("glow_core", SCOPE, parent=root, col=col)
    C.add_empty("eject", EJECT, rotation=C.frame_from_axes((0, 0, 0), (1, 0, 0.45), (0, 0, 1)).to_3x3(),
                parent=root, col=col)

    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = P.paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decals=decals(), ao_distance=0.03,
                              ao_samples=24, seed=7)
    if C.flag(argv, "--details-only"):
        # paint iteration: close-ups (+ the 4x in-game hold) only; no .blend, no export, no status
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        reports = C.ensure_dir(os.path.join(pack, "reports"))
        detail_views(mesh, work, reports)
        hold_closeup(root, mesh, work, reports)
        C.log("DONE (details only)", KEY)
        return
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    bak = blend + "1"
    if os.path.exists(bak):
        os.remove(bak)
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=__file__,
                         extra={"chassis": {"damage_type": "Kinetic", "style": "Slug", "tags": ["precise", "pierce"],
                                            "family": "precise", "verb": "THE NEEDLE"},
                                "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")}})
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    outputs = [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
               C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")),
               C.rel(os.path.join(tex_dir, KEY + "_emissive.png"))]
    if not C.flag(argv, "--no-review"):
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        notes = [
            "%s tris (two-handed budget 2000-4000) | textures %s | length %.2f m | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
                ", ".join(sorted(rep["sockets"]))),
            "Grip frame: origin = right palm centre on the pistol grip, Blender +Y = barrel (glTF -Z), +Z = up. "
            "grip_L under the bone forend, muzzle at the crown's bore, glow_core in the crystal, eject on the right.",
            "Status: %s (the user gives the final visual approval)." % rep.get("status", SPEC.STATUS_AI_FINAL),
        ]
        rv = R.review_weapon(KEY, root, mesh, reports, work, "Godsbane Rifle  (godsbane_rifle)",
                             "Kinetic | Slug, pierce 1, 1 deg spread, range 17 | tags: precise, pierce | "
                             "silhouette verb: THE NEEDLE (bone stock, crystal scope, gilded rails, fang point)",
                             swatches=PALETTE, notes=notes, px=REVIEW_PX,
                             textures=[os.path.join(tex_dir, KEY + "_basecolor.png"),
                                       os.path.join(tex_dir, KEY + "_emissive.png")])
        relayout_review(work, reports)
        shutil.copyfile(rv["turn_34_front"], os.path.join(reports, KEY + "_34.png"))
        hold = hold_closeup(root, mesh, work, reports)
        views = wide_views(mesh, work, reports)
        details = detail_views(mesh, work, reports)
        outputs += [C.rel(os.path.join(reports, KEY + "_review.png")), C.rel(os.path.join(reports, KEY + "_34.png")),
                    C.rel(hold), C.rel(views), C.rel(details)]
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, outputs,
                        "Built from code by tools/blender/gf_assets/weapons/godsbane_rifle.py "
                        "(launcher: art/weapons/godsbane_rifle/godsbane_rifle_build.py).", tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
