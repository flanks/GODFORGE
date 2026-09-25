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
    horns, jaws wide open, two long bone fangs, big slit-pupil glowing eyes, a glowing throat / palate /
    tongue and a glowing jet that tapers into the needle barrel it spits (the small muzzle of the family);
  * the drum magazine is a squat bronze canister tucked up under the front coils (Thompson-style, in
    front of the grip; the coils swallow its top, so it is the belly of the coil mass): its domed faces
    are painted as the serpent's coiled tail (one bronze spiral), a gold chamfer rim catches the light
    and its band carries engraved overlapping scales (the "coiled drum" / "scale-textured drum");
  * value rhythm (art review 2026-09-25: lifted for the 38 px game size): the coils in broad
    alternating dark violet / light bronze bands, three per coil, so the coils read as a bold stripe
    rhythm; a bright bronze drum; a banded neck; a bronze-crowned head; and the brightest values at the
    front: bone fangs, big Kinetic eyes, the white-hot mouth, jet and needle;
  * palette: the warm metals of the player's arsenal (bronze, gold, bone, dark wood) plus the Kinetic
    element glow #F4E3C1 (palette.rs). The dark bands are a violet-tinted dark and the grip wrap a
    dark violet leather: a quiet nod to Kael's #9A7CFF that stays out of the glow channel.
  * snake skin: painted by a post-pass on top of gfa_paint.paint (see skin_postpass): texels are mapped
    into body-local coordinates (arc length along the serpent's centre-line, angle around the tube);
    the bands are locked to the helix angle around the bore (see _band_coord).

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
JAW_UP, JAW_DOWN = 17.0, 28.0    # degrees the upper head lifts / the lower jaw drops (a wide glowing gape)
NEEDLE = (0.37, 0.528)           # needle barrel from the throat to its tip (y)
NEEDLE_R = 0.0095                # needle radius (thick enough to stay a white-hot line at game size)
MUZZLE = (0.0, NEEDLE[1], AX)
THROAT = (0.0, 0.378, AX)        # glow_core: the glowing throat behind the needle
# the drum: a squat canister tucked up under the front coils (its top is swallowed by the coil mass, so it
# reads as the belly of the coiled body, not a wheel hanging below the gun)
DRUM_C = (0.0, 0.158, AX - 0.080)
DRUM_R, DRUM_W = 0.055, 0.080
DRUM_CHAMFER = 0.009             # the gold rim bevel between the faces and the band
EYE_R = 0.019                    # glowing eyes (big enough to stay two bright pixels at game size)

ZONES = ["scales", "head", "bronze", "gold", "bone", "iron", "wood", "wrap", "drum_face",
         "glow_eye", "glow_throat", "needle", "quill"]
PALETTE = [  # (name, hex) for the review sheet
    ("dark band", "#3A2D4C"), ("bronze band", "#CC9046"), ("band ring", "#F6D896"), ("belly", "#D8C7A0"),
    ("bronze", "#B87A35"), ("gold", "#E4B24A"), ("bone", "#E8DCC0"), ("head", "#44365A"), ("iron", "#3B3340"),
    ("wood", "#4E2E22"), ("wrap", "#3E2A4E"), ("glow rim", "#E6A650"), ("kinetic", "#F4E3C1"), ("core", "#FFFBF0"),
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
    # a broad bronze crown plate: the head's top is what the 55 deg game camera sees, so it carries a
    # light value (the dark skull only shows on the flanks)
    crown = M.loft_rect([(H - 0.004, 0.050, 0.013, 0, AX + 0.047), (H + 0.050, 0.046, 0.012, 0, AX + 0.043),
                         (H + 0.106, 0.020, 0.009, 0, AX + 0.030)], bevel=0.0035)
    upper.append((crown, "bronze", "crown", "auto"))
    for sx in (-1, 1):
        brow = M.box((0.016, 0.05, 0.012), bevel=0.004, taper=(0.7, 0.8))
        M.xform(brow, loc=(sx * 0.033, H + 0.034, AX + 0.043), rot=(4, -sx * 18, sx * 10))
        upper.append((brow, "bronze", "brow", "auto"))
        eye = M.sphere(EYE_R, 6, 4, scale=(0.85, 1.25, 0.9))
        M.xform(eye, loc=(sx * 0.038, H + 0.040, AX + 0.031))
        upper.append((eye, "glow_eye", "eye", "smooth"))
        horn = M.horn([(sx * 0.030, H + 0.016, AX + 0.040), (sx * 0.040, H - 0.014, AX + 0.056),
                       (sx * 0.046, H - 0.048, AX + 0.063)], 0.0095, 0.0, sides=5)
        upper.append((horn, "bone", "horn", "smooth"))
        fang = M.horn([(sx * 0.0165, H + 0.096, AX + 0.006), (sx * 0.018, H + 0.109, AX - 0.021),
                       (sx * 0.014, H + 0.129, AX - 0.046)], 0.0088, 0.0, sides=5)
        upper.append((fang, "bone", "fang", "smooth"))
    # glowing palate under the upper jaw (shows as a light wedge between the open jaws)
    pal = M.loft_rect([(H - 0.006, 0.076, 0.006, 0, AX - 0.005), (H + 0.05, 0.068, 0.006, 0, AX - 0.004),
                       (H + 0.104, 0.034, 0.006, 0, AX - 0.001)])
    upper.append((pal, "glow_throat", "palate", "flat"))
    R_up = hinge(JAW_UP)
    EYES[:] = [R_up @ Vector((sx * 0.038, H + 0.040, AX + 0.031)) for sx in (-1, 1)]
    for bm, zone, name, shading in upper:
        M.xform(bm, matrix=R_up)
        a.add(bm, zone, name=name, shading=shading)

    jaw = M.loft_rect([(H - 0.016, 0.062, 0.020, 0, AX - 0.016), (H + 0.034, 0.058, 0.017, 0, AX - 0.018),
                       (H + 0.086, 0.034, 0.013, 0, AX - 0.017)], bevel=0.005)
    lower = [(jaw, "head", "jaw", "auto")]
    tongue = M.loft_rect([(H - 0.01, 0.056, 0.005, 0, AX - 0.0055), (H + 0.078, 0.036, 0.005, 0, AX - 0.0065)])
    lower.append((tongue, "glow_throat", "tongue", "flat"))
    for sx in (-1, 1):
        lf = M.horn([(sx * 0.013, H + 0.076, AX - 0.012), (sx * 0.013, H + 0.083, AX + 0.002),
                     (sx * 0.011, H + 0.090, AX + 0.012)], 0.0048, 0.0, sides=4)
        lower.append((lf, "bone", "lower_fang", "smooth"))
    R_dn = hinge(-JAW_DOWN)
    for bm, zone, name, shading in lower:
        M.xform(bm, matrix=R_dn)
        a.add(bm, zone, name=name, shading=shading)

    # glowing throat between the jaws (a big white-hot cone: the brightest mass at the front end at game
    # size), and the needle barrel it spits
    throat = M.cylinder(0.029, 0.042, sides=8, radius_top=0.018, axis="Y")
    M.xform(throat, loc=(0, THROAT[1] - 0.012, AX))
    a.add(throat, "glow_throat", name="throat", shading="smooth")
    # the glowing jet: the throat's light carried forward between the fangs, tapering into the needle
    # (a bright arrow-head at the front end of the gun at game size)
    j0, j1 = THROAT[1] + 0.009, 0.472
    jet = M.cylinder(0.018, j1 - j0, sides=8, radius_top=NEEDLE_R + 0.001, axis="Y")
    M.xform(jet, loc=(0, (j0 + j1) / 2, AX))
    a.add(jet, "glow_throat", name="jet", shading="smooth")
    ndl = M.cylinder(NEEDLE_R, NEEDLE[1] - 0.032 - NEEDLE[0], sides=8, axis="Y")
    M.xform(ndl, loc=(0, (NEEDLE[0] + NEEDLE[1] - 0.032) / 2, AX))
    a.add(ndl, "needle", name="needle", shading="smooth")
    tipm = M.spike(NEEDLE_R, 0.032, sides=8, rot_offset=0)
    M.xform(tipm, matrix=M.orient((0, NEEDLE[1] - 0.032, AX), (0, 1, 0), (1, 0, 0)))
    a.add(tipm, "needle", name="needle_tip", shading="smooth")
    rg = M.ring(NEEDLE_R - 0.001, NEEDLE_R + 0.005, 0.009, sides=8, axis="Y")
    M.xform(rg, loc=(0, NEEDLE[1] - 0.064, AX))
    a.add(rg, "gold", name="needle_ring")

    # -- the drum magazine: a squat bronze canister tucked up under the front coils (the coils swallow its
    # top, so at game size it is the belly of the coil mass). Domed faces painted as the serpent's coiled
    # tail; a gold chamfer rim catches the light; no hub, no recessed face, no magwell (the old thin
    # rim + hub + recessed face read as a cart wheel)
    h, R_, c = DRUM_W / 2, DRUM_R, DRUM_CHAMFER
    prof = [(0.0, -h - 0.004), (R_ * 0.55, -h - 0.0025), (R_ - c, -h), (R_, -h + c),
            (R_, h - c), (R_ - c, h), (R_ * 0.55, h + 0.0025), (0.0, h + 0.004)]
    drum = M.lathe(prof, sides=16, axis="X")
    M.xform(drum, loc=DRUM_C)
    a.add(drum, "drum_face", name="drum", shading="auto")

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
    "head": P.zone(base="#44365A", shadow="#1A1324", light="#9484AC", planes=0.08, edge=0.9, edge_width=0.0045,
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
    # the drum canister: a light bronze band (engraved scales and the gold chamfer rim come from the skin
    # post-pass, which also paints the domed faces)
    "drum_face": P.zone(base="#C88A3E", shadow="#5E341B", light="#F8D286", planes=0.06, parts=0.0, edge=0.9,
                        edge_width=0.005, cavity=0.6, ao=0.6, stroke=(1, 0, 0), stroke_amount=0.12,
                        stroke_freq=(110.0, 6.0)),
    "glow_eye": P.zone(base="#F4E3C1", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFFBF0", "hot": "#F8EBCF", "color": "#E6B868", "mode": "flat"}),
    # throat, palate and tongue: white-hot at the throat, Kinetic cream, warm gold toward the snout; at full
    # strength and a wide radius so the whole open mouth is one bright shape at game size
    "glow_throat": P.zone(base="#F4E3C1", edge=0.0, cavity=0.0, ao=0.0,
                          emit={"core": "#FFFBF0", "hot": "#F4E3C1", "color": "#E6A650", "mode": "radial",
                                "center": THROAT, "radius": 0.11, "strength": 1.0, "base_mix": 0.2}),
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
    the eye to the back of the skull (the band edges' gold line carried onto the head)."""
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
    # broad alternating bands, dark violet / light bronze: THREE per coil. An odd count per turn makes
    # neighbouring coils swap colours, so the side of the receiver reads as a bold dark / bronze stripe
    # rhythm at game size (the earlier diamond-outline pattern turned into speckle at 1x)
    "dark": "#3A2D4C", "dark_ridge": "#5E4C74", "dark_shadow": "#1A1322",
    "bronze": "#CC9046", "bronze_ridge": "#F2C874", "bronze_shadow": "#6A3C1E",
    "ring_line": "#160F1B", "ring_light": "#F6D896",     # a thin dark ring + a broken gold line at each band edge
    "belly": "#D8C7A0", "belly_line": "#7A6448", "tail_bone": "#8C7458",
    "scale_len": 0.0125, "scale_wid": 0.0105,          # one scale (m), along / across the body (a faint hint)
    "bands_per_turn": 3,
    "band_phase_deg": 60.0,                            # band edges at 60 / 180 / 300 deg: one band sits centred
                                                       # on top of each coil, where the game camera looks
    "chevron": 0.0,                                    # band edges lean back on the flanks (0 = straight rings)
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


def _band_coord(D, ss):
    """Band coordinate along the dense centre-line (an integer at every band edge). In the coils it
    follows the helix angle around the bore (bands_per_turn per turn, phase-locked, so every coil has
    the same band layout and the colours swap from coil to coil); on the tail and the neck it follows
    the arc length at the coils' mean band length. Returns (coordinate, mean band length in m)."""
    th = np.unwrap(np.arctan2(D[:, 0], D[:, 2] - AX))
    th = th - th[0]
    per = 2 * np.pi / SKIN["bands_per_turn"]
    ph = math.radians(SKIN["band_phase_deg"])
    tmax = th.max()
    ia = int(np.argmax(th > 0.05))
    ib = int(len(th) - 1 - np.argmax((th < tmax - 0.05)[::-1]))
    band_len = (ss[ib] - ss[ia]) / max(1e-6, (th[ib] - th[ia]) / per)
    bc = (th + ph) / per
    bc = np.where(ss < ss[ia], (th[ia] + ph) / per - (ss[ia] - ss) / band_len, bc)
    bc = np.where(ss > ss[ib], (th[ib] + ph) / per + (ss - ss[ib]) / band_len, bc)
    return bc, band_len


def _nearest(points, queries):
    kd = KDTree(len(points))
    for i, p in enumerate(points.tolist()):
        kd.insert(p, i)
    kd.balance()
    out = np.empty(len(queries), dtype=np.int64)
    for i, q in enumerate(queries.tolist()):
        out[i] = kd.find(q)[1]
    return out


def skin_colour(bcoord, w, hw, band_len, seed=0, belly=None, p=None, chevron=None):
    """Painted banded snake skin. bcoord = band coordinate along the body (an integer at each band edge),
    w = metres across the body (0 on the spine), hw = half the visible width (the flank), band_len = one
    band in metres, belly = 0..1 mask. Returns (N, 3) sRGB and the (N,) bronze-band mask.
    Big flat value shapes first (the bands, a lighter painted ridge along the back of each coil, darker
    flanks), then the small stuff that only shows up close: a thin dark ring and a broken gold line at
    every band edge, a faint scale lattice, bone belly scutes."""
    S = SKIN
    n = len(bcoord)
    x = np.abs(w) / np.maximum(hw, 1e-6)              # 0 on the spine .. 1 at the visible flank edge
    b = bcoord + (S["chevron"] if chevron is None else chevron) * np.minimum(x, 1.2)
    if p is not None:                                  # hand-painted band edges: a gentle wobble, no jaggies
        b = b + 0.03 * (P.spread01(P.fbm(p, 24.0, 2, seed=seed + 21)) - 0.5)
    k = np.floor(b)
    f = b - k
    bronze = (np.mod(k, 2) == 1).astype(np.float32)

    def pick(d_hex, b_hex):
        return P.mix(np.repeat(P.hex3(d_hex)[None], n, 0), P.hex3(b_hex), bronze)

    col = pick(S["dark"], S["bronze"])
    if p is not None:                                  # low-frequency paint variation (never grunge)
        col = col * (1 + 0.05 * (P.fbm(p, 9.0, 2, seed=seed + 3) * 2 - 1))[:, None]
    # a lighter painted ridge along the back of the coil, the flanks falling toward the shadow hue
    col = P.mix(col, pick(S["dark_ridge"], S["bronze_ridge"]),
                P.smoothstep(0.62, 0.12, x) * (0.3 + 0.14 * bronze))
    col = P.mix(col, pick(S["dark_shadow"], S["bronze_shadow"]), P.smoothstep(0.85, 1.25, x) * 0.25)
    # a faint scale lattice (low contrast: it averages out at game size instead of speckling)
    u = bcoord * band_len
    a_ = u / S["scale_len"]
    bb = w / S["scale_wid"]
    fx, fy = (a_ + bb) - np.floor(a_ + bb), (a_ - bb) - np.floor(a_ - bb)
    seam = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
    tipv = 1.0 - (fx + fy) * 0.5
    col = P.mix(col, col * 1.14, P.smoothstep(0.6, 0.95, tipv) * 0.5)
    col = P.mix(col, col * 0.78, P.smoothstep(0.1, 0.03, seam) * 0.45)
    # band edges: a thin dark ring, and a thin broken gold line just inside every bronze band
    e = np.minimum(f, 1 - f) * band_len               # metres to the nearest band edge
    col = P.mix(col, P.hex3(S["ring_line"]), P.smoothstep(0.0034, 0.0018, e) * 0.9)
    gl = P.smoothstep(0.0028, 0.0038, e) * P.smoothstep(0.0066, 0.005, e) * bronze
    if p is not None:
        gl = gl * P.smoothstep(0.3, 0.5, P.spread01(P.fbm(p, 55.0, 2, seed=seed + 33)))
    col = P.mix(col, P.hex3(S["ring_light"]), gl * 0.85)
    # belly scutes: transverse bone plates
    if belly is not None:
        bu = u / (S["scale_len"] * 0.95)
        fb = bu - np.floor(bu)
        bcol = P.mix(np.repeat(P.hex3(S["belly"])[None], n, 0), P.hex3(S["belly_line"]),
                     P.smoothstep(0.16, 0.04, np.minimum(fb, 1 - fb)))
        bcol = P.mix(bcol, P.hex3(S["belly"]) * 1.06, P.smoothstep(0.5, 0.95, fb) * 0.4)
        col = P.mix(col, bcol, belly)
    return np.clip(col, 0, 1), bronze


def skin_postpass(maps, zones_order, base, emis, seed=0):
    P_, Z, ao = maps["pos"], maps["zone"], maps["ao"]
    # 1) the serpent body: broad bands locked to the coils
    zi = zones_order.index("scales")
    idx = np.nonzero(Z == zi)[0]
    if len(idx):
        D, T, O, B, ss, Rr = _dense_path()
        BC, band_len = _band_coord(D, ss)
        q = P_[idx]
        near = _nearest(D, q)
        v = q - D[near]
        along = (v * T[near]).sum(1)
        v = v - T[near] * along[:, None]
        phi = np.arctan2((v * B[near]).sum(1), (v * O[near]).sum(1))
        rr = Rr[near]
        u = ss[near] + along
        bc = np.interp(u, ss, BC)
        w = phi * rr
        hw = np.pi * rr * 0.58                        # visible half-width of the back + flanks
        belly = P.smoothstep(2.05, 2.35, np.abs(phi))
        col, bronze = skin_colour(bc, w, hw, band_len, seed=seed, belly=belly, p=q)
        # keep the painter's contact shadows (AO) from the base pass, in each band's own shadow hue
        occ = 1 - ao[idx]
        k = P.smoothstep(0.2, 0.6, occ)
        sh = P.mix(np.repeat(P.hex3(SKIN["dark_shadow"])[None], len(idx), 0), P.hex3(SKIN["bronze_shadow"]), bronze)
        col = P.mix(col, sh, k * 0.6)
        # the tail end fades to the rattle's bone
        col = P.mix(col, P.hex3(SKIN["tail_bone"]), P.smoothstep(0.03, 0.0, u) * 0.5)
        base[idx] = col
        C.log("skin: band length %.3f m, band coordinate %.1f .. %.1f" % (band_len, BC.min(), BC.max()))
    # 2) the drum canister: domed faces = the serpent's coiled tail (one bronze spiral); a gold chamfer rim; a light
    #    bronze band with engraved overlapping scales (the "coiled drum" / "scale-textured drum")
    zi = zones_order.index("drum_face")
    idx = np.nonzero(Z == zi)[0]
    if len(idx):
        q = P_[idx] - np.array(DRUM_C, dtype=np.float32)
        nx = np.abs(maps["tnrm"][idx, 0])
        r = np.sqrt(q[:, 1] ** 2 + q[:, 2] ** 2)
        occ = P.smoothstep(0.2, 0.6, 1 - ao[idx])
        # a) faces: the serpent's coiled tail as ONE light bronze spiral (a painted ridge along its crest, a
        #    soft violet groove between the turns) that curls in to the centre. One colour along the spiral:
        #    alternating bands line up from turn to turn into spokes, and a centre disc reads as a hub; both
        #    made the old drum a cart wheel
        cap = nx > 0.85
        if cap.any():
            qc, rc = q[cap], r[cap]
            pc = P_[idx][cap]
            side = np.sign(qc[:, 0])
            th = np.arctan2(qc[:, 2], qc[:, 1] * side)  # mirrored per face: both spirals wind the same way on screen
            r1, turns = DRUM_R - DRUM_CHAMFER - 0.002, 2.25
            band = r1 / turns
            psi = rc / band - th / (2 * np.pi)
            fl = np.floor(psi)
            f = psi - fl
            x = np.abs(f - 0.5) * 2                   # 0 on the crest of the coil .. 1 in the groove
            col = np.repeat(P.hex3(SKIN["bronze"])[None], len(rc), 0)
            col = col * (1 + 0.05 * (P.fbm(pc, 9.0, 2, seed=seed + 51) * 2 - 1))[:, None]
            col = P.mix(col, P.hex3(SKIN["bronze_ridge"]), P.smoothstep(0.62, 0.1, x) * 0.45)
            col = P.mix(col, P.hex3(SKIN["bronze_shadow"]), P.smoothstep(0.55, 0.85, x) * 0.45)
            # a faint scale lattice along the coil (low contrast, like the body)
            u = (th + 2 * np.pi * fl) * np.maximum(rc, 0.004)
            a_, bb = u / SKIN["scale_len"], (f - 0.5) * band / SKIN["scale_wid"]
            fx, fy = (a_ + bb) - np.floor(a_ + bb), (a_ - bb) - np.floor(a_ - bb)
            seam = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
            col = P.mix(col, col * 0.8, P.smoothstep(0.1, 0.03, seam) * 0.4 * P.smoothstep(0.004, 0.012, rc))
            # the groove between the turns: a soft painted violet-black, broken like a brush line
            gw = 0.86 + 0.05 * (P.spread01(P.fbm(pc, 40.0, 2, seed=seed + 52)) - 0.5)
            col = P.mix(col, P.hex3("#241A2E"), P.smoothstep(gw, gw + 0.1, x) * 0.9)
            # a painted contact shadow just inside the rim, and the AO where the coils swallow the drum
            col = P.mix(col, P.hex3("#241A2E"), P.smoothstep(r1 - 0.001, r1 + 0.0025, rc) * 0.75)
            col = P.mix(col, P.hex3(SKIN["bronze_shadow"]), occ[cap] * 0.6)
            base[idx[cap]] = np.clip(col, 0, 1)
        # b) the chamfer: a bright gold rim with a broken brushy highlight (the drum's read at game size)
        ch = (nx > 0.35) & (nx <= 0.85)
        if ch.any():
            pc = P_[idx][ch]
            col = np.repeat(P.hex3("#E8B84E")[None], int(ch.sum()), 0)
            col = col * (1 + 0.06 * (P.fbm(pc, 12.0, 2, seed=seed + 61) * 2 - 1))[:, None]
            hl = P.smoothstep(0.35, 0.55, P.spread01(P.fbm(pc, 38.0, 2, seed=seed + 62)))
            col = P.mix(col, P.hex3("#FFEDB4"), hl * 0.6)
            col = P.mix(col, P.hex3("#86511A"), occ[ch] * 0.6)
            base[idx[ch]] = np.clip(col, 0, 1)
        # c) the band: overlapping scales engraved into the light bronze
        bd = nx <= 0.35
        if bd.any():
            sub = idx[bd]
            qs = q[bd]
            uu = np.arctan2(qs[:, 2], qs[:, 1]) * DRUM_R          # around the drum
            vv = qs[:, 0] + DRUM_W / 2                            # across the band
            su, sv, rs = 0.017, 0.0105, 0.0112
            best_d = np.full(len(sub), 9.0, dtype=np.float32)
            j0 = np.floor(vv / sv)
            for dj in (-1, 0, 1, 2):                             # later rows lie on top of earlier ones
                j = j0 + dj
                off = (np.mod(j, 2)) * su * 0.5
                cu = np.round((uu - off) / su) * su + off
                d = np.hypot(uu - cu, vv - j * sv) / rs
                best_d = np.where(d < 1.0, d, best_d)
            col = base[sub]
            col = P.mix(col, P.hex3("#F6CE7A"), P.smoothstep(0.75, 0.25, best_d) * 0.3)
            col = P.mix(col, P.hex3("#4A2814"), P.smoothstep(0.8, 0.97, best_d) * P.smoothstep(1.2, 1.0, best_d) * 0.6)
            base[sub] = col
    # 3) slit pupils in the glowing eyes (dark, no emission): thin, so the eyes stay big bright shapes
    zi = zones_order.index("glow_eye")
    idx = np.nonzero(Z == zi)[0]
    if len(idx) and EYES:
        q = P_[idx]
        slit = np.zeros(len(idx), dtype=np.float32)
        for e in EYES:
            v = q - np.array(e[:], dtype=np.float32)
            out_side = v[:, 0] * np.sign(e.x) > 0.005
            d = (v[:, 1] / 0.0032) ** 2 + (v[:, 2] / 0.0145) ** 2
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
