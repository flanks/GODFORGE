"""Serpent SMG (serpent_smg): Kael's signature rapid-fire needle gun, built end to end from code with
tools/blender/gf_assets (docs/art/WEAPONS.md). Started as a copy of
tools/blender/gf_assets/weapons/sunspike_shotgun.py (the toolkit's template weapon).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P art/weapons/serpent_smg/source/serpent_smg_build.py -- [--size 1024] [--no-review] [--quick]

  --quick      geometry only: flat zone colours, Workbench turnaround + game-size silhouettes into
               work/quick/ (a few seconds; for silhouette iterations, nothing is exported)
  --no-review  build, paint, export and validate, but skip the review renders

Content row (content/sheets/chassis.csv): serpent_smg "Serpent SMG", Kinetic, style Needle, fire Auto,
fire rate 11/s, damage 7, spread 6 deg, range 11, tags "rapid; kael" - "A hissing stream of needles.
Never stops talking." Signature chassis of Kael, the Wraithshot (content/sheets/characters.csv: ghost
gunslinger, agile duelist / crit, colour #9A7CFF).

Design (docs/art/WEAPONS.md section 5, family RAPID -> verb THE STREAM; tier one_handed):
  * one serpent is the whole gun: its tail (a bone rattle) lies on the back of the receiver, its body
    winds FOUR tight coils around the bronze receiver (the "many small repeated elements" of the rapid
    family: a dark / bronze stripe rhythm), then runs forward as a lean neck along a thin dark-iron
    barrel with four backswept glowing needle quills on its spine (a row of small lights leading to
    the muzzle), and its head is the muzzle: a wedge viper skull with a bronze crown, backswept bone
    horns, jaws wide open, two long bone fangs, slit-pupil glowing eyes, a glowing throat / palate /
    tongue, and the needle barrel it spits (the small muzzle of the family);
  * the drum magazine sits under the front coils (Thompson-style, in front of the grip): its faces are
    painted as a coiled serpent tail in scales and its bronze band carries engraved overlapping scales
    (the "coiled drum" / "scale-textured drum" of both briefs);
  * value rhythm: dark violet scales over a bronze core (stripes), a bronze drum, a dark neck and head,
    and the brightest values at the front: bone fangs, Kinetic glow in the eyes, the mouth and the
    white-hot needle;
  * palette: the warm metals of the player's arsenal (bronze, gold, bone, dark wood) plus the Kinetic
    element glow #F4E3C1 (palette.rs). The scales are a violet-tinted dark iron and the grip wrap a
    dark violet leather: a quiet nod to Kael's #9A7CFF that stays out of the glow channel.
  * scale texture: the snake skin (diamond-back pattern, overlapping scales, bone belly scutes) is
    painted by a post-pass on top of gfa_paint.paint (see skin_postpass): texels are mapped into
    body-local coordinates (arc length along the serpent's centre-line, angle around the tube).

Grip frame (docs/art/WEAPONS.md section 2): origin = palm centre of the right hand on the pistol grip,
+Y = barrel, +Z = up, +X = the weapon's right. Bore axis AX above the palm.
Outputs: assets/models/weapons/serpent_smg.glb (+ .meta.json), art/weapons/serpent_smg/
{source/serpent_smg.blend, textures/*.png, reports/*.png, status.json}.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "blender", "gf_assets"))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.kdtree import KDTree  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402

KEY, KIND, TIER = "serpent_smg", "weapon", "one_handed"
AX = 0.095                       # bore axis height above the palm centre (m)

# serpent body: tail -> tight coils around the receiver -> a lean neck along the barrel -> the head
COIL_Y = (-0.095, 0.165)         # first coil crest / end of the coils along the bore
TURNS = 4
COIL_END = 0.6                   # the last coil stops this many radians before the top (smooth neck exit)
COIL_R = (0.050, 0.046)          # helix radius (centre-line to bore axis) at the back / front
BODY_R = [(0.0, 0.009), (0.05, 0.015), (0.13, 0.0225), (0.66, 0.022), (0.84, 0.0185), (1.0, 0.019)]  # (t, r)
COIL_SAMPLES = 5                 # control points per turn (x2 after smoothing)

HEAD_HINGE = (0.352, AX)         # jaw hinge (y, z)
JAW_UP, JAW_DOWN = 14.0, 24.0    # degrees the upper head lifts / the lower jaw drops
NEEDLE = (0.37, 0.528)           # needle barrel from the throat to its tip (y)
MUZZLE = (0.0, NEEDLE[1], AX)
THROAT = (0.0, 0.378, AX)        # glow_core: the glowing throat behind the needle
DRUM_C = (0.0, 0.186, AX - 0.097)
DRUM_R, DRUM_W = 0.062, 0.068

ZONES = ["scales", "head", "bronze", "gold", "bone", "iron", "wood", "wrap", "drum_face",
         "glow_eye", "glow_throat", "needle", "quill"]
PALETTE = [  # (name, hex) for the review sheet
    ("scales", "#2E2438"), ("diamond", "#4E4062"), ("outline", "#D6B97E"), ("belly", "#D2C09A"),
    ("bronze", "#B87A35"), ("gold", "#E4B24A"), ("bone", "#E8DCC0"), ("iron", "#3B3340"), ("wood", "#4E2E22"),
    ("wrap", "#3E2A4E"), ("glow rim", "#D9A85C"), ("kinetic", "#F4E3C1"), ("core", "#FFFBF0"),
]

PATH = {}                        # centre-line samples for the skin painter (filled by build_mesh)
EYES = []                        # eye centres after the jaw lift (filled by build_mesh): slit pupils


# ---- geometry -----------------------------------------------------------------------------------------

def _lerp_table(table, t):
    for (t0, v0), (t1, v1) in zip(table[:-1], table[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return table[-1][1]


def body_centerline():
    """The serpent's centre-line from the tail tip (back) to the neck (front): the tail lies on the
    housing's rear, the body winds TURNS tight coils around the receiver, the neck leaves the last coil
    near the top and runs forward along the barrel with a slight rise (a snake about to strike)."""
    y0, y1 = COIL_Y
    ctrl = [Vector((0.0, y0 - 0.088, AX + 0.062)), Vector((0.0, y0 - 0.046, AX + 0.058))]
    phi_end = 2 * math.pi * TURNS - COIL_END
    n = int(round(TURNS * COIL_SAMPLES))
    for i in range(n + 1):
        t = i / n
        phi = phi_end * t                             # 0 = top, +90 deg = the weapon's right (+X)
        r = COIL_R[0] + (COIL_R[1] - COIL_R[0]) * t
        ctrl.append(Vector((r * math.sin(phi), y0 + (y1 - y0) * t, AX + r * math.cos(phi))))
    h = HEAD_HINGE[0]
    ctrl += [Vector((0.0, y1 + 0.036, AX + 0.052)), Vector((0.0, 0.25, AX + 0.050)),
             Vector((0.0, 0.30, AX + 0.040)), Vector((0.0, h - 0.012, AX + 0.029))]
    return M.catmull(ctrl, 2)


def _arc(pts):
    s = [0.0]
    for a, b in zip(pts[:-1], pts[1:]):
        s.append(s[-1] + (b - a).length)
    return s


def hinge(angle_deg):
    """Rotation about the jaw hinge (an X axis through HEAD_HINGE); + lifts the front."""
    h = Vector((0.0, HEAD_HINGE[0], HEAD_HINGE[1]))
    return Matrix.Translation(h) @ Matrix.Rotation(math.radians(angle_deg), 4, "X") @ Matrix.Translation(-h)


def _on_path(pts, y, after=0):
    """Centre-line point at bore position y (linear), searching from index `after`."""
    for a, b in zip(pts[after:-1], pts[after + 1:]):
        if (a.y - y) * (b.y - y) <= 0 and abs(b.y - a.y) > 1e-9:
            return a.lerp(b, (y - a.y) / (b.y - a.y))
    return pts[-1]


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES)
    H = HEAD_HINGE[0]

    # -- receiver core: a bronze housing above the grip, a sleeve inside the front coils, a thin barrel
    hs = M.box((0.052, 0.19, 0.062), bevel=0.011, segments=1, taper=(0.86, 1.0))
    M.xform(hs, loc=(0, -0.035, AX - 0.002))
    a.add(hs, "bronze", name="housing")
    sl = M.cylinder(0.027, 0.15, sides=10, axis="Y")
    M.xform(sl, loc=(0, 0.11, AX))
    a.add(sl, "bronze", name="sleeve", shading="smooth")
    col_ = M.ring(0.017, 0.033, 0.02, sides=10, axis="Y")
    M.xform(col_, loc=(0, 0.185, AX))
    a.add(col_, "gold", name="collar")
    bar = M.cylinder(0.0175, H - 0.19, sides=8, axis="Y")
    M.xform(bar, loc=(0, (H + 0.19) / 2, AX))
    a.add(bar, "iron", name="barrel", shading="smooth")
    cap = M.box((0.056, 0.02, 0.068), bevel=0.006, taper=(0.9, 1.0))
    M.xform(cap, loc=(0, -0.132, AX - 0.002))
    a.add(cap, "gold", name="rear_cap")

    # -- the serpent body: tail + coils + neck, one tube
    pts = body_centerline()
    s = _arc(pts)
    L = s[-1]
    radii = [_lerp_table(BODY_R, si / L) for si in s]
    body = M.tube(pts, radii, sides=7, cap=True)
    a.add(body, "scales", name="body", shading="smooth")
    PATH["pts"], PATH["s"], PATH["r"] = pts, s, radii

    # tail rattle: bone beads stacked backward-up behind the tail tip
    tip, prev = pts[0], pts[2]
    d = (tip - prev).normalized()
    for k in range(4):
        rr = 0.0135 - 0.0022 * k
        bead = M.sphere(rr, 6, 4, scale=(1.0, 1.0, 0.72))
        M.xform(bead, matrix=M.orient(tip + d * (0.006 + 0.0155 * k), d, (1, 0, 0)))
        a.add(bead, "bone", name="rattle", shading="smooth")

    # dorsal quills along the neck: glowing needles swept back (the forward sweep of the family and a
    # row of small repeated lights leading to the muzzle: the needles the serpent spits)
    k0 = len(pts) // 2
    for i, y in enumerate((0.205, 0.238, 0.271, 0.304)):
        c = _on_path(pts, y, k0)
        rr = _lerp_table(BODY_R, s[min(range(len(pts)), key=lambda j: (pts[j] - c).length)] / L)
        sp = M.spike(0.0085 - 0.0008 * i, 0.03 - 0.003 * i, sides=4, base_scale=(0.45, 1.0), rot_offset=0)
        M.xform(sp, matrix=M.orient(c + Vector((0, 0, rr - 0.004)), (0, -0.62, 0.78), (1, 0, 0)))
        a.add(sp, "quill", name="quill", shading="smooth")

    # -- the head: a viper wedge (upper head lifted about the hinge) + a dropped lower jaw
    upper = []
    skull = M.loft_rect([(H - 0.028, 0.048, 0.042, 0, AX + 0.023), (H + 0.006, 0.096, 0.054, 0, AX + 0.022),
                         (H + 0.050, 0.084, 0.047, 0, AX + 0.021), (H + 0.092, 0.054, 0.034, 0, AX + 0.017),
                         (H + 0.124, 0.026, 0.021, 0, AX + 0.013)], bevel=0.008)
    upper.append((skull, "head", "skull", "auto"))
    crown = M.loft_rect([(H + 0.004, 0.034, 0.012, 0, AX + 0.047), (H + 0.064, 0.026, 0.010, 0, AX + 0.042),
                         (H + 0.104, 0.012, 0.008, 0, AX + 0.030)], bevel=0.003)
    upper.append((crown, "bronze", "crown", "auto"))
    for sx in (-1, 1):
        brow = M.box((0.016, 0.05, 0.012), bevel=0.004, taper=(0.7, 0.8))
        M.xform(brow, loc=(sx * 0.031, H + 0.036, AX + 0.041), rot=(4, -sx * 18, sx * 10))
        upper.append((brow, "bronze", "brow", "auto"))
        eye = M.sphere(0.0145, 6, 4, scale=(0.8, 1.25, 0.9))
        M.xform(eye, loc=(sx * 0.037, H + 0.038, AX + 0.032))
        upper.append((eye, "glow_eye", "eye", "smooth"))
        horn = M.horn([(sx * 0.030, H + 0.016, AX + 0.040), (sx * 0.040, H - 0.014, AX + 0.056),
                       (sx * 0.046, H - 0.048, AX + 0.063)], 0.0095, 0.0, sides=5)
        upper.append((horn, "bone", "horn", "smooth"))
        fang = M.horn([(sx * 0.0165, H + 0.096, AX + 0.006), (sx * 0.018, H + 0.109, AX - 0.021),
                       (sx * 0.014, H + 0.129, AX - 0.046)], 0.0088, 0.0, sides=5)
        upper.append((fang, "bone", "fang", "smooth"))
    # glowing palate under the upper jaw (shows as a light wedge between the open jaws)
    pal = M.loft_rect([(H - 0.006, 0.07, 0.006, 0, AX - 0.005), (H + 0.05, 0.062, 0.006, 0, AX - 0.004),
                       (H + 0.1, 0.03, 0.006, 0, AX - 0.001)])
    upper.append((pal, "glow_throat", "palate", "flat"))
    R_up = hinge(JAW_UP)
    EYES[:] = [R_up @ Vector((sx * 0.037, H + 0.038, AX + 0.032)) for sx in (-1, 1)]
    for bm, zone, name, shading in upper:
        M.xform(bm, matrix=R_up)
        a.add(bm, zone, name=name, shading=shading)

    jaw = M.loft_rect([(H - 0.016, 0.062, 0.020, 0, AX - 0.016), (H + 0.034, 0.058, 0.017, 0, AX - 0.018),
                       (H + 0.086, 0.034, 0.013, 0, AX - 0.017)], bevel=0.005)
    lower = [(jaw, "head", "jaw", "auto")]
    tongue = M.loft_rect([(H - 0.01, 0.05, 0.005, 0, AX - 0.0055), (H + 0.07, 0.03, 0.005, 0, AX - 0.0065)])
    lower.append((tongue, "glow_throat", "tongue", "flat"))
    for sx in (-1, 1):
        lf = M.horn([(sx * 0.013, H + 0.076, AX - 0.012), (sx * 0.013, H + 0.083, AX + 0.002),
                     (sx * 0.011, H + 0.090, AX + 0.012)], 0.0048, 0.0, sides=4)
        lower.append((lf, "bone", "lower_fang", "smooth"))
    R_dn = hinge(-JAW_DOWN)
    for bm, zone, name, shading in lower:
        M.xform(bm, matrix=R_dn)
        a.add(bm, zone, name=name, shading=shading)

    # glowing throat between the jaws, and the needle barrel it spits
    throat = M.cylinder(0.022, 0.03, sides=8, radius_top=0.013, axis="Y")
    M.xform(throat, loc=(0, THROAT[1] - 0.008, AX))
    a.add(throat, "glow_throat", name="throat", shading="smooth")
    ndl = M.cylinder(0.0075, NEEDLE[1] - 0.03 - NEEDLE[0], sides=8, axis="Y")
    M.xform(ndl, loc=(0, (NEEDLE[0] + NEEDLE[1] - 0.03) / 2, AX))
    a.add(ndl, "needle", name="needle", shading="smooth")
    tipm = M.spike(0.0075, 0.03, sides=8, rot_offset=0)
    M.xform(tipm, matrix=M.orient((0, NEEDLE[1] - 0.03, AX), (0, 1, 0), (1, 0, 0)))
    a.add(tipm, "needle", name="needle_tip", shading="smooth")
    rg = M.ring(0.0065, 0.012, 0.009, sides=8, axis="Y")
    M.xform(rg, loc=(0, NEEDLE[1] - 0.062, AX))
    a.add(rg, "gold", name="needle_ring")

    # -- the drum magazine: bronze rim, recessed painted faces, gold hub, a magwell up into the sleeve
    rim = M.ring(DRUM_R - 0.012, DRUM_R, DRUM_W, sides=16, axis="X")
    M.xform(rim, loc=DRUM_C)
    a.add(rim, "bronze", name="drum_rim")
    face = M.cylinder(DRUM_R - 0.011, DRUM_W - 0.012, sides=16, axis="X")
    M.xform(face, loc=DRUM_C)
    a.add(face, "drum_face", name="drum_face", shading="smooth")
    hub = M.cylinder(0.011, DRUM_W + 0.006, sides=8, axis="X")
    M.xform(hub, loc=DRUM_C)
    a.add(hub, "gold", name="drum_hub")
    well = M.box((0.034, 0.05, 0.03), bevel=0.005, taper=(0.9, 0.9))
    M.xform(well, loc=(0, DRUM_C[1], AX - 0.036))
    a.add(well, "iron", name="magwell")

    # -- pistol grip (dark wood, violet leather wraps), gold pommel, iron trigger guard
    rake = math.radians(17)

    def on_grip(h):                                   # a point on the grip's (raked) centre axis
        return (0, -0.012 + h * math.sin(rake), -0.005 + h * math.cos(rake))

    g = M.box((0.036, 0.052, 0.14), bevel=0.011, segments=2, taper=(1.06, 1.1))
    M.xform(g, loc=on_grip(0), rot=(-17, 0, 0))
    a.add(g, "wood", name="grip")
    for h in (0.026, -0.018):
        w = M.box((0.041, 0.058, 0.02), bevel=0.005)
        M.xform(w, loc=on_grip(h), rot=(-17, 0, 0))
        a.add(w, "wrap", name="wrap")
    pom = M.box((0.044, 0.07, 0.022), bevel=0.007, taper=(0.85, 0.9))
    M.xform(pom, loc=on_grip(-0.078), rot=(-17, 0, 0))
    a.add(pom, "gold", name="pommel")
    guard = M.catmull([(0, 0.02, AX - 0.035), (0, 0.028, AX - 0.083), (0, 0.062, AX - 0.1), (0, 0.10, AX - 0.094),
                       (0, 0.128, AX - 0.092)], 2)
    a.add(M.band(guard, 0.016, 0.01, up=(1, 0, 0)), "bronze", name="guard")
    a.add(M.horn([(0, 0.052, AX - 0.04), (0, 0.047, AX - 0.062), (0, 0.055, AX - 0.08)], 0.006, 0.003, sides=5),
          "iron", name="trigger", shading="smooth")

    obj = a.to_object(col)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return obj


# ---- paint --------------------------------------------------------------------------------------------

KGLOW = {"core": "#FFFBF0", "hot": "#F4E3C1", "color": "#D9A85C"}     # Kinetic element glow (palette.rs)

RECIPES = {
    "scales": P.zone(base="#3A3046", shadow="#171220", light="#7A6C8E", planes=0.0, parts=0.0, brush=0.05,
                     edge=0.0, cavity=0.0, ao=0.65, ao_range=(0.2, 0.6)),
    "head": P.zone(base="#3A3046", shadow="#171220", light="#8A7C9E", planes=0.08, edge=0.9, edge_width=0.004,
                   cavity=0.7, ao=0.6),
    "bronze": P.zone(base="#B87A35", shadow="#57301A", light="#F6CE7A", planes=0.08, parts=0.05, edge=0.85,
                     edge_width=0.0045, cavity=0.75, ao=0.65, stroke=(0, 1, 0), stroke_amount=0.16,
                     stroke_freq=(110.0, 6.0),
                     spots={"color": "#7A4A22", "amount": 0.22, "freq": 16.0, "threshold": (0.62, 0.74)}),
    "gold": P.zone(base="#E4B24A", shadow="#86511A", light="#FFF2BE", planes=0.08, edge=0.8, edge_width=0.0035,
                   cavity=0.6, ao=0.5),
    "bone": P.zone(base="#E8DCC0", shadow="#8C7458", light="#FFFBEE", planes=0.05, edge=0.5, edge_width=0.003,
                   cavity=0.5, ao=0.45),
    "iron": P.zone(base="#3B3340", shadow="#161119", light="#8C7F92", planes=0.07, edge=0.9, edge_width=0.0035,
                   cavity=0.6, ao=0.5),
    "wood": P.zone(base="#4E2E22", shadow="#22110C", light="#8A5A3C", planes=0.05, parts=0.04, edge=0.55,
                   edge_width=0.004, cavity=0.7, ao=0.6, stroke=(0, 0, 1), stroke_amount=0.3,
                   stroke_freq=(90.0, 5.0)),
    "wrap": P.zone(base="#3E2A4E", shadow="#170E1F", light="#7A5E92", planes=0.05, edge=0.55, edge_width=0.003,
                   cavity=0.6, ao=0.5, stroke=(1, 0, 0), stroke_amount=0.25, stroke_freq=(140.0, 8.0)),
    "drum_face": P.zone(base="#3A3046", shadow="#171220", light="#7A6C8E", planes=0.0, parts=0.0, edge=0.0,
                        cavity=0.0, ao=0.6),
    "glow_eye": P.zone(base="#F4E3C1", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFF8E6", "hot": "#F4E3C1", "color": "#E0B060", "mode": "flat"}),
    # throat, palate and tongue: white-hot at the throat, Kinetic cream, warm gold toward the snout
    "glow_throat": P.zone(base="#F4E3C1", edge=0.0, cavity=0.0, ao=0.0,
                          emit={"core": "#FFF6DE", "hot": "#F4E3C1", "color": "#E09A48", "mode": "radial",
                                "center": THROAT, "radius": 0.07, "strength": 0.7, "base_mix": 0.1}),
    "quill": P.zone(base="#EFE2C4", shadow="#8C7458", light="#FFFBEE", edge=0.0, cavity=0.0, ao=0.2,
                    emit=dict(KGLOW, mode="flat", strength=0.75, base_mix=0.5)),
    # the needle glows along its whole length, white-hot at the tip (the brightest value of the gun)
    "needle": P.zone(base="#D8CCB4", shadow="#6E6152", light="#FFF8E8", planes=0.05, edge=0.6, edge_width=0.003,
                     cavity=0.4, ao=0.4,
                     emit=dict(KGLOW, mode="plane", axis=(0, -1, 0), range=(-NEEDLE[1] + 0.004, -NEEDLE[0]),
                               base_mix=0.45)),
}


def decals():
    """The viper's post-ocular stripe on both head sides: a bone-gold line with a black halo from behind
    the eye to the back of the skull (the body's diamond outline style carried onto the head)."""
    out = []
    H = HEAD_HINGE[0]
    R_up = hinge(JAW_UP)
    for sx in (-1, 1):
        pts = [R_up @ Vector((0.0, H + y, AX + z)) for y, z in ((0.024, 0.027), (0.006, 0.019), (-0.018, 0.013))]
        pts2 = [R_up @ Vector((0.0, H + y, AX + z)) for y, z in ((0.050, 0.030), (0.064, 0.026), (0.080, 0.020))]
        u = Vector((0, sx, 0))
        v = Vector((0, 0, 1))
        z = u.cross(v)
        fr = Matrix(((u.x, v.x, z.x, 0), (u.y, v.y, z.y, 0), (u.z, v.z, z.z, 0), (0, 0, 0, 1)))
        lines = [[(sx * p.y, p.z) for p in pts], [(sx * p.y, p.z) for p in pts2]]
        out.append(P.decal_lines(lines, fr, 0.0036, zones=["head"], color="#D6B97E", rim="#110C16",
                                 rim_width=0.008, depth=(0.02, 0.08)))
    return out


# ---- the snake-skin post-pass (runs inside gfa_paint.paint_asset) --------------------------------------

SKIN = {
    "base": "#2E2438", "scale_dark": "#1B1422", "scale_light": "#4A3D5A",
    "diamond_fill": "#4E4062", "diamond_inner": "#80664A", "diamond_line": "#D6B97E", "diamond_rim": "#110C16",
    "fleck": "#B89A68", "belly": "#D2C09A", "belly_line": "#6E5A45",
    "scale_len": 0.0125, "scale_wid": 0.0105,          # one scale (m), along / across the body
    "diamond_pitch": 0.052,                            # diamonds along the back (m)
}


def _dense_path(step=0.0015):
    """Resample the body centre-line: points, tangents, outward vectors, arc length, radius."""
    pts, s, r = PATH["pts"], PATH["s"], PATH["r"]
    L = s[-1]
    n = int(L / step) + 1
    ss = np.linspace(0.0, L, n)
    P_ = np.array([p[:] for p in pts])
    S = np.array(s)
    D = np.stack([np.interp(ss, S, P_[:, k]) for k in range(3)], 1)
    Rr = np.interp(ss, S, np.array(r))
    T = np.gradient(D, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-12
    # outward = away from the bore axis (x = 0, z = AX), perpendicular to the tangent (up where degenerate)
    rad = D - np.stack([np.zeros(n), D[:, 1], np.full(n, AX)], 1)
    rad -= T * (rad * T).sum(1, keepdims=True)
    small = np.linalg.norm(rad, axis=1) < 0.012
    rad[small] = np.array([0.0, 0.0, 1.0]) - T[small] * T[small][:, 2:3]
    O = rad / (np.linalg.norm(rad, axis=1, keepdims=True) + 1e-12)
    B = np.cross(T, O)
    return D, T, O, B, ss, Rr


def _nearest(points, queries):
    kd = KDTree(len(points))
    for i, p in enumerate(points.tolist()):
        kd.insert(p, i)
    kd.balance()
    out = np.empty(len(queries), dtype=np.int64)
    for i, q in enumerate(queries.tolist()):
        out[i] = kd.find(q)[1]
    return out


def skin_colour(u, w, hw, seed=0, belly=None, p=None):
    """Painted snake skin in body coordinates: u = metres along the body (toward the head), w = metres
    across it (0 on the spine), hw = half the visible width (the flank), belly = 0..1 mask. Returns
    (N, 3) sRGB and a (N,) mask of the diamond fill (for the light accents)."""
    S = SKIN
    n = len(u)
    col = np.repeat(P.hex3(S["base"])[None], n, 0)
    # low-frequency paint variation (never grunge)
    if p is not None:
        col *= (1 + 0.06 * (P.fbm(p, 9.0, 2, seed=seed + 3) * 2 - 1))[:, None]
    # overlapping scales: a diamond lattice; each scale lighter at its free (tail-ward) tip, dark seams
    a = u / S["scale_len"]
    b = w / S["scale_wid"]
    x, y = a + b, a - b
    fx, fy = x - np.floor(x), y - np.floor(y)
    seam = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
    tipv = 1.0 - (fx + fy) * 0.5                      # 1 at the tail-ward tip of the scale
    amt = 1.0 if p is None else 0.55 + 0.45 * P.spread01(P.fbm(p, 14.0, 2, seed=seed + 9))
    col = P.mix(col, P.hex3(S["scale_light"]), P.smoothstep(0.6, 0.95, tipv) * 0.35 * amt)
    col = P.mix(col, P.hex3(S["scale_dark"]), P.smoothstep(0.12, 0.03, seam) * 0.45 * amt)
    # diamond-back pattern along the spine: light diamonds with a black rim
    pitch = S["diamond_pitch"]
    k = np.round(u / pitch)
    du = np.abs(u - k * pitch) / (pitch * 0.5)
    dw = np.abs(w) / (hw * 0.62)
    dd = du + dw                                       # < 1 inside the diamond
    if p is not None:
        dd = dd + 0.05 * (P.fbm(p, 40.0, 2, seed=seed + 21) * 2 - 1)
    # drawn as a bone-gold OUTLINE (with a black halo outside it) around a slightly lighter violet fill
    # and a small muted-bronze inner diamond: the coils stay a DARK mass at game size, the chain of
    # outlines is the rhythm up close
    rim = P.smoothstep(1.24, 1.12, dd)
    line = P.smoothstep(1.12, 1.04, dd) * P.smoothstep(0.84, 0.91, dd)
    fill = P.smoothstep(0.91, 0.84, dd)
    inner = P.smoothstep(0.40, 0.33, dd)
    col = P.mix(col, P.hex3(S["diamond_rim"]), rim * 0.85)
    dcol = P.mix(np.repeat(P.hex3(S["diamond_fill"])[None], n, 0), P.hex3(S["diamond_inner"]), inner)
    # keep the scale seams faintly inside the diamonds (it is the same skin)
    dcol = P.mix(dcol, dcol * 0.75, P.smoothstep(0.14, 0.03, seam) * 0.6)
    col = P.mix(col, dcol, fill)
    col = P.mix(col, P.hex3(S["diamond_line"]), line)
    # lateral dabs between the diamonds (small light flecks low on the flank)
    fl = np.abs(np.abs(w) / hw - 0.78)
    kk = np.round((u - pitch * 0.5) / pitch)
    fu = np.abs(u - pitch * 0.5 - kk * pitch) / (pitch * 0.18)
    fleck = P.smoothstep(1.0, 0.6, fu + fl / 0.12)
    col = P.mix(col, P.hex3(S["fleck"]), fleck * 0.7)
    # belly scutes: transverse bone plates
    if belly is not None:
        bu = u / (S["scale_len"] * 0.95)
        fb = bu - np.floor(bu)
        bcol = P.mix(np.repeat(P.hex3(S["belly"])[None], n, 0), P.hex3(S["belly_line"]),
                     P.smoothstep(0.16, 0.04, np.minimum(fb, 1 - fb)))
        bcol = P.mix(bcol, P.hex3(S["belly"]) * 1.08, P.smoothstep(0.5, 0.95, fb) * 0.4)
        col = P.mix(col, bcol, belly)
    return np.clip(col, 0, 1), fill


def skin_postpass(maps, zones_order, base, emis, seed=0):
    P_, Z, ao = maps["pos"], maps["zone"], maps["ao"]
    # 1) the serpent body
    zi = zones_order.index("scales")
    idx = np.nonzero(Z == zi)[0]
    if len(idx):
        D, T, O, B, ss, Rr = _dense_path()
        q = P_[idx]
        near = _nearest(D, q)
        v = q - D[near]
        along = (v * T[near]).sum(1)
        v = v - T[near] * along[:, None]
        phi = np.arctan2((v * B[near]).sum(1), (v * O[near]).sum(1))
        rr = Rr[near]
        u = ss[near] + along
        w = phi * rr
        hw = np.pi * rr * 0.58                        # visible half-width of the back + flanks
        belly = P.smoothstep(2.05, 2.35, np.abs(phi))
        col, _ = skin_colour(u, w, hw, seed=seed, belly=belly, p=q)
        # keep the painter's contact shadows (AO) from the base pass
        occ = 1 - ao[idx]
        k = P.smoothstep(0.2, 0.6, occ)
        col = P.mix(col, P.hex3(RECIPES["scales"]["shadow"]), k * 0.6)
        # tail end fades to the rattle's bone
        col = P.mix(col, P.hex3("#8C7458"), P.smoothstep(0.03, 0.0, u) * 0.5)
        base[idx] = col
    # 2) the drum faces: a coiled serpent tail in scales (a flat spiral band on each face)
    zi = zones_order.index("drum_face")
    idx = np.nonzero(Z == zi)[0]
    if len(idx):
        q = P_[idx] - np.array(DRUM_C, dtype=np.float32)
        r = np.sqrt(q[:, 1] ** 2 + q[:, 2] ** 2)
        side = np.sign(q[:, 0])
        th = np.arctan2(q[:, 2], q[:, 1] * side)       # mirrored per face: both spirals wind the same way on screen
        r0, r1, turns = 0.016, DRUM_R - 0.013, 2.0
        band = (r1 - r0) / turns
        psi = (r - r0) / band - th / (2 * np.pi)
        f = psi - np.floor(psi)
        u = (th + 2 * np.pi * np.floor(psi)) * (r0 + band * np.floor(psi) + band * 0.5)
        w = (f - 0.5) * band
        col, _ = skin_colour(u, w, band * 0.5, seed=seed + 50, p=P_[idx])
        # the groove between the turns (black) with a light brushed edge on the outer side of each turn
        groove = P.smoothstep(0.1, 0.02, np.minimum(f, 1 - f))
        col = P.mix(col, P.hex3("#0E0A12"), groove * 0.95)
        col = P.mix(col, P.hex3(SKIN["scale_light"]) * 1.25, P.smoothstep(0.8, 0.9, f) * P.smoothstep(0.98, 0.9, f) * 0.6)
        # face edge (the drum's rim casts a painted contact shadow onto the face)
        col = P.mix(col, P.hex3("#120D18"), P.smoothstep(r1 - 0.004, r1 + 0.002, r) * 0.8)
        # flat caps only: the cylinder side under the rim stays dark
        cap = np.abs(maps["tnrm"][idx, 0]) > 0.7
        col[~cap] = P.hex3("#1A1420")
        base[idx] = np.clip(col, 0, 1)
    # 3) the drum's outer band: overlapping scales engraved into the bronze (the "scale-textured drum")
    zi = zones_order.index("bronze")
    idx = np.nonzero(Z == zi)[0]
    if len(idx):
        q = P_[idx] - np.array(DRUM_C, dtype=np.float32)
        r = np.sqrt(q[:, 1] ** 2 + q[:, 2] ** 2)
        nr = (maps["tnrm"][idx, 1] * q[:, 1] + maps["tnrm"][idx, 2] * q[:, 2]) / np.maximum(r, 1e-6)
        sel = (np.abs(q[:, 0]) < DRUM_W / 2 - 0.0035) & (np.abs(r - DRUM_R) < 0.003) & (nr > 0.8)
        sub = idx[sel]
        if len(sub):
            qs = q[sel]
            u = np.arctan2(qs[:, 2], qs[:, 1]) * DRUM_R          # around the drum
            v = qs[:, 0] + DRUM_W / 2                            # across the band
            su, sv, rs = 0.017, 0.0105, 0.0112
            best_d = np.full(len(sub), 9.0, dtype=np.float32)
            j0 = np.floor(v / sv)
            for dj in (-1, 0, 1, 2):                             # later rows lie on top of earlier ones
                j = j0 + dj
                off = (np.mod(j, 2)) * su * 0.5
                cu = np.round((u - off) / su) * su + off
                d = np.hypot(u - cu, v - j * sv) / rs
                best_d = np.where(d < 1.0, d, best_d)
            col = base[sub]
            col = P.mix(col, P.hex3("#F2C46E"), P.smoothstep(0.75, 0.25, best_d) * 0.28)
            col = P.mix(col, P.hex3("#4A2814"), P.smoothstep(0.8, 0.97, best_d) * P.smoothstep(1.2, 1.0, best_d) * 0.7)
            base[sub] = col
    # 4) slit pupils in the glowing eyes (dark, no emission)
    zi = zones_order.index("glow_eye")
    idx = np.nonzero(Z == zi)[0]
    if len(idx) and EYES:
        q = P_[idx]
        slit = np.zeros(len(idx), dtype=np.float32)
        for e in EYES:
            v = q - np.array(e[:], dtype=np.float32)
            out_side = v[:, 0] * np.sign(e.x) > 0.004
            d = (v[:, 1] / 0.0034) ** 2 + (v[:, 2] / 0.0125) ** 2
            slit = np.maximum(slit, P.smoothstep(1.2, 0.8, d) * out_side)
        base[idx] = P.mix(base[idx], P.hex3("#1A1020"), slit)
        emis[idx] = emis[idx] * (1 - slit)[:, None]
    return base, emis


_paint_orig = P.paint


def _paint_with_skin(maps, zones_order, recipes, dist_convex, dist_concave, decals=(), seed=0):
    base, emis = _paint_orig(maps, zones_order, recipes, dist_convex, dist_concave, decals, seed)
    return skin_postpass(maps, zones_order, base, emis, seed)


# ---- quick silhouette review ------------------------------------------------------------------------------

def quick_review(root, mesh, work):
    """Workbench turnaround in flat zone colours + in-game silhouettes (no paint, no export)."""
    scene = bpy.context.scene
    for s in mesh.material_slots:
        z = s.material.name[4:]
        s.material.diffuse_color = C.hex_linear(RECIPES[z]["base"])
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    sh.show_cavity, sh.show_object_outline = True, True
    sh.background_type = "VIEWPORT"
    sh.background_color = C.hex_linear(R.BG_REVIEW)[:3]
    scene.view_settings.view_transform = "Standard"
    pts = R._points([mesh])
    views = dict(R.WEAPON_VIEWS)
    ext = max(max(R.frame(pts, d)[1:]) for d in views.values())
    for name, d in views.items():
        c, _, _ = R.frame(pts, d)
        R.aim(scene, c, d, ext * 1.1)
        R.render(scene, os.path.join(work, "q_%s.png" % name), 480)
    R.silhouette([mesh], os.path.join(work, "q_sil_side.png"), (1, 0, 0), size=360)
    R.silhouette([mesh], os.path.join(work, "q_sil_top.png"), (0, 0.0001, 1), size=360)
    for i, aimd in enumerate(((1.0, 0.0, 0.0), (0.6, -0.8, 0.0), (-0.3, 0.95, 0.0))):
        root.matrix_world = R.weapon_hold_matrix(aimd)
        bpy.context.view_layer.update()
        man = R.mannequin(aim_dir=aimd, grip_r=root.matrix_world.translation)
        R.ingame([mesh], work, "q_aim%d" % i, px=150, mannequin_obj=man, target=(0.0, 0.0, 1.0))
        C.remove_objects([man])
    root.matrix_world = Matrix.Identity(4)


# ---- extra review images -----------------------------------------------------------------------------------

def hero_closeup(mesh, path, direction=(0.75, 0.55, 0.38), w=900, h=520):
    """A large toon-preview render of the weapon alone (the pack README's picture)."""
    scene = bpy.context.scene
    pts = R._points([mesh])
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh], ink=0.0035):
        c, fw, fh = R.frame(pts, direction)
        R.aim(scene, c, direction, max(fw, fh) * 1.08)
        R.render(scene, path, w, h)
    return path


def held_review(key, root, mesh, reports, work, true_size):
    """The weapon in the mannequin's right hand at its grip frame, seen through the in-game camera (55 deg
    pitch, yaw 0) zoomed to a 6 m view height, next to the true-size 1080p renders (3x nearest)."""
    shots = []
    for i, a in enumerate(((1.0, 0.0, 0.0), (0.6, -0.8, 0.0), (-0.45, 0.89, 0.0))):
        root.matrix_world = R.weapon_hold_matrix(a)
        bpy.context.view_layer.update()
        g = root.matrix_world.translation.copy()
        man = R.mannequin(aim_dir=a, grip_r=g)
        r = R.ingame([mesh], work, "%s_held%d" % (key, i), px=380, view_height=6.0, mannequin_obj=man,
                     target=(g.x * 0.6, g.y * 0.6, 1.25), ink=0.0045, silhouette_too=False, samples=12)
        shots.append({"path": r["color"], "label": "aim %d" % i})
        C.remove_objects([man])
    root.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    layout = {
        "title": "Serpent SMG held at its grip frame", "width": 1200,
        "subtitle": "2.2 m hero mannequin, right hand on grip_R (one-handed: the left arm hangs); "
                    "in-game camera: orthographic, 55 deg pitch, yaw 0",
        "sections": [
            {"label": "In-game camera zoomed to a 6 m view height (180 px/m)", "height": 380, "images": shots},
            {"label": "The same camera at true 1080p size (22 m view height, 49 px/m), 3x nearest", "height": None,
             "images": [{"path": p, "label": "aim %d" % i, "scale": 3} for i, p in enumerate(true_size)]},
        ],
        "notes": ["The review hold (weapon_hold_matrix) is a stand-in until GF_Hero_v1's weapon_socket_R exists."],
    }
    return R.contact_sheet(layout, os.path.join(reports, "%s_held.png" % key), work)


# ---- main ------------------------------------------------------------------------------------------------

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
    C.add_empty("muzzle", MUZZLE, parent=root, col=col)
    C.add_empty("glow_core", THROAT, parent=root, col=col)

    pack = C.pack_dir(KIND, KEY)
    if C.flag(argv, "--quick"):
        quick_review(root, mesh, C.ensure_dir(os.path.join(pack, "work", "quick")))
        C.log("QUICK DONE", C.count_tris([mesh]), "tris")
        return

    tex_dir = os.path.join(pack, "textures")
    P.paint = _paint_with_skin               # runtime hook: the skin post-pass (gfa_paint itself is unchanged)
    try:
        paint_rep = P.paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decals=decals(), ao_distance=0.03,
                                  ao_samples=24, seed=5)
    finally:
        P.paint = _paint_orig
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=__file__,
                         extra={"chassis": {"damage_type": "Kinetic", "style": "Needle", "fire": "Auto",
                                            "tags": ["rapid", "kael"]},
                                "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")}})
    reports = C.ensure_dir(os.path.join(pack, "reports"))   # gfa_sheet.py does not create it
    if not C.flag(argv, "--no-review"):
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        notes = [
            "%s tris (one-handed budget 1000-2500) | textures %s | length %.2f m | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
                ", ".join(sorted(rep["sockets"]))),
            "Grip frame: origin = right palm centre on the pistol grip, Blender +Y = barrel (glTF -Z), +Z = up. "
            "muzzle at the needle tip, glow_core in the serpent's throat. One-handed: no grip_L.",
            "Status: %s (the user gives the final visual approval)." % rep.get("status", "ai_final_pending_user_approval"),
        ]
        out = R.review_weapon(KEY, root, mesh, reports, work, "Serpent SMG  (serpent_smg)",
                              "Kinetic | Needle, auto, 11 shots/s | tags: rapid, kael | silhouette verb: THE STREAM "
                              "(coiled serpent receiver, fanged needle muzzle, coiled drum)",
                              swatches=PALETTE, notes=notes,
                              textures=[os.path.join(tex_dir, KEY + "_basecolor.png"),
                                        os.path.join(tex_dir, KEY + "_emissive.png")])
        hero_closeup(mesh, os.path.join(reports, KEY + "_34.png"))
        held_review(KEY, root, mesh, reports, work, [out["ingame_0"], out["ingame_1"]])
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        C.rel(os.path.join(reports, KEY + "_review.png")), C.rel(os.path.join(reports, KEY + "_34.png")),
        C.rel(os.path.join(reports, KEY + "_held.png"))],
        "Built from code by art/weapons/serpent_smg/source/serpent_smg_build.py (gf_assets toolkit).",
        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
