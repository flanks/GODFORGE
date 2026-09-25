"""Ashrunner - the Cinder Wastes swarm hound (The Unmade): built, painted, rigged on GF_Swarm_v1, animated,
exported and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/ashrunner.py -- [--size 512] [--no-review] [--preview]

  then: -P tools/blender/gf_assets/enemies/ashrunner_crowd.py   (the horde read, mixed with clinkers)
        -P tools/blender/gf_assets/enemies/ashrunner_fix_sheet.py -- --before DIR   (the review-fix sheet)

Content row (content/sheets/enemies.csv): ashrunner, Swarm, P0, hp 18, speed 5.2, radius 0.36, scale 1.0,
Swarmer(jitter 0.6), colour #F2A541, shape Hound, packs of 2-4 - "Fast ash-hounds that hunt in pairs."
Collider radius x scale = 0.36 m, so the body is about 0.8-1.1 m long (docs/art/ENEMIES.md section 2).

Design (docs/art/ENEMIES.md; the user's enemy pack):
  * verb SPRINT: an ash-grey hound of cinder and char, built like an arrow - a long, low skull held level
    with the spine, a tucked waist, hard haunches, long legs and a whip tail streaming straight back. Black
    char shards stream back off the neck like a wind-torn mane, and two big ears sweep back over the withers.
    Every long line points backward: it reads as speed standing still;
  * a WEDGE from the game camera (art review fix): hyena-heavy forequarters - a bull neck, 0.46 m shoulders and
    a broad ash ruff flaring back off them (about 0.5 m across), a heavier skull with cheek ruffs and broad
    ears - narrowing through the chest to a 0.17 m waist and a 0.19 m rump. Head-on (the hunting approach)
    it is 25 px wide at 1x, not a 13 px sliver;
  * the signature is the BURNT-OPEN CHEST: the hide has burnt through over the ribcage in ONE hot window, a
    lens that is longest over the back and runs down the left flank, framed at its rear by ONE black rib bar.
    From the 55 deg camera: pale shoulders, one hot orange shape, one dark bar, a pale rump - "a grey streak
    with a burning chest". (The first build had four black ribs with ember edge strokes: a barcode at 1x.);
  * THE UNMADE's wrong asymmetry, bold enough for 35 px: the window is burnt open down the whole left flank but
    framed by hide on the right; the right ear is snapped off short; the mane and the ruff lean right;
  * faction glow: the Cinder Wastes Unmade burn molten (the Slag King's ramp) with the Unmade teal as the
    marker - the window and the tail tip glow ember (rim #C8400C, hot #FF6B1A, a warm #FFB070 core instead of
    the white-hot #FFF3D6, so no white speckle), the eye slits and the maw glow teal #2FBFA8. The bite
    telegraph is the clinker's language: the skull tips back and bares a teal maw;
  * value plan at game size: ash-grey top masses (lighter than the #3A2C24 floor), charcoal legs, jaw,
    underside and mane (darker than the floor, with light brush edges), the ember window and the tail tip as
    the one warm accent. The clinker is a dark dome with a pale club and teal; the ashrunner is a pale wedge
    with an orange chest: distinct at a glance, same faction.

Rig GF_Swarm_v1 (rigid). The gallop is a double-suspension bound with a FLEXING SPINE:
  body   = neck, shoulders and chest (one loft), ember core, the rib bar, lower jaw, mane and ruff
  head   = the skull + upper jaw, eyes, cheek ruffs and ears, hinged at the jaw joint: pitching it nose-up
           opens the mouth, and the lower jaw's teal floor faces the camera (the bite telegraph)
  legs_a = both front legs (pivot: the shoulder joints)     legs_b = both hind legs (pivot: the hip joints)
  tail   = the loin, rump and tail (pivot: the loin): it flexes the spine - rump tucked under in the
           gathered phase, stretched back in the extended phase. The hind legs follow the rump (their
           location and pitch are solved from the tail bone's rotation, follow_tail()), so the hips stay on.

Toolkit: tools/blender/gf_assets (gfa_model / gfa_paint / gfa_rig / gfa_export / gfa_render); structure and
review layout follow enemies/clinker.py.
"""
import math
import os
import random
import sys
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "ashrunner"
KIND, TIER = "enemy", "swarm"
FPS = 30
SEED = 29
ROW = {"key": "ashrunner", "class": "Swarm", "biome": "cinder_wastes", "hp": 18, "speed": 5.2, "radius": 0.36,
       "scale": 1.0, "behavior": "Swarmer(jitter: 0.6)", "color": "#F2A541", "shape": "Hound", "pack": "(2, 4)"}
ZONES = ["hide", "char", "rib", "ember", "maw", "eye", "bone"]

# ---- proportions (metres; faces -Y, +X = the creature's left, ground z = 0) ---------------------------------
Y_C = -0.02                               # body centre
SHOULDER = Vector((0.0, -0.20, 0.44))     # front-leg pivot (the shoulder joints lie on this line)
HIP = Vector((0.0, 0.30, 0.43))           # hind-leg pivot
LOIN = Vector((0.0, 0.16, 0.47))          # tail-bone pivot: the spine flexes here
JAW = Vector((0.0, -0.415, 0.548))        # head-bone pivot: the jaw hinge
CORE = Vector((0.0, -0.02, 0.405))        # ember core centre (fx_core)
EMBER_C = Vector((0.015, -0.055, 0.56))   # centre of the ember glow ramp: on the window top the camera sees
# Review fix (art review 6/10): head-on the old body was 0.30 m wide (15 px at 1x, a pale sliver) and its four
# ember-edged ribs read as a barcode. The torso is now ONE loft, a hyena-heavy wedge from above: 0.46 m across
# the shoulders (0.5 m with the ash ruff), 0.34 m over the chest window, a 0.17 m waist, a 0.19 m rump. The
# hide is burnt through in ONE hot window over the ribcage (WIN_Y[0]..WIN_Y[1]), framed at its rear by ONE rib
# bar: from the camera, pale hide -> one hot shape -> one dark bar -> pale hide (a rib crossing the middle of
# the window read as an orange-black-orange wasp stripe in the horde)
WIN_Y = (-0.11, 0.03, 0.075)              # chest window: front edge, rear edge = the rib bar; then a shape ring
RIB_W = 0.042                             # rib bar width (along the body)
# torso rings (y, cx, cz, w, h), neck to waist: a bull neck, the widest point at the shoulders, the window,
# then a hard tuck into the waist (the rump loft on the tail bone starts inside the last ring)
TORSO_RINGS = [(-0.40, 0.0, 0.567, 0.17, 0.16), (-0.345, 0.0, 0.537, 0.29, 0.245), (-0.285, 0.0, 0.492, 0.42, 0.31),
               (-0.21, 0.0, 0.458, 0.47, 0.34), (WIN_Y[0], 0.0, 0.425, 0.40, 0.30), (WIN_Y[1], 0.0, 0.41, 0.345, 0.28),
               (WIN_Y[2], 0.0, 0.42, 0.29, 0.25), (0.105, 0.0, 0.452, 0.17, 0.17)]
# the window's open faces: (ring interval, profile segment). Segment k joins BODY_PROFILE vertices k and k+1:
# 0 = top-left, 1 = upper left flank, 2 = mid left flank, 9 = top-right. The Unmade asymmetry: from above the
# window is framed by pale hide on the right, but it is burnt open down the whole LEFT flank
WIN_FACES = {(4, 0), (4, 1), (4, 2), (4, 9)}
# the window's outline: y shifts of its edge vertices (ring, profile vertex) - a lens that is longest over the
# back and narrows down the left flank, so it reads as a hole burnt in the hide rather than a band
WIN_SHIFT = {(4, 0): -0.026, (4, 1): -0.02, (4, 9): -0.014, (4, 2): -0.004, (4, 3): 0.028,
             (5, 0): 0.004, (5, 1): 0.0, (5, 9): 0.002, (5, 8): 0.0, (5, 2): -0.012, (5, 3): -0.026, (5, 4): -0.03}

# unit cross-sections (x, z): a keel-chested hound body, a skull with a flat brow plane, a narrow jaw
BODY_PROFILE = [(0.0, 1.0), (0.62, 0.84), (0.97, 0.34), (0.86, -0.3), (0.46, -0.8), (0.0, -1.0),
                (-0.46, -0.8), (-0.86, -0.3), (-0.97, 0.34), (-0.62, 0.84)]
SKULL_PROFILE = [(0.0, 1.0), (0.62, 0.9), (1.0, 0.36), (0.9, -0.4), (0.5, -1.0), (-0.5, -1.0),
                 (-0.9, -0.4), (-1.0, 0.36), (-0.62, 0.9)]
JAW_PROFILE = [(0.0, 1.0), (0.85, 0.75), (1.0, 0.0), (0.6, -0.85), (0.0, -1.0), (-0.6, -0.85), (-1.0, 0.0),
               (-0.85, 0.75)]

# ---- palette (The Unmade; gfa_spec.FACTIONS + the row colour as a faint warm tint) ---------------------------


def mix_hex(a, b, t):
    ca, cb = C.hex_rgb(a), C.hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ca, cb))


ASH = "#838079"                                        # ash-grey hide (base)
ASH_LIGHT = mix_hex("#B6B0A8", ROW["color"], 0.10)     # pale ash top planes, faintly warmed by the row colour
ASH_SHADOW = "#3C3134"                                 # warm violet char-grey
CHAR = "#221C1D"
CHAR_LIGHT = "#6A5A54"                                 # warm char edge light
SMOULDER = "#7A3418"                                   # the burn line where the ash hide chars (painted, dim glow)
RIB_BASE = "#2A1D1A"
RIB_LIGHT = "#C0673C"                                  # rib edges lit by the ember inside
EMBER = {"color": "#C8400C", "hot": "#FF6B1A", "core": "#FFB070"}      # Slag King molten ramp, cooled core
TEAL = {"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#8FF2D8"}      # ichor (no #B8FFE8 speckle at 35 px)
FANG = "#B3A58F"                                       # faction bone a step down (no white speckle)
PALETTE = [("ash", ASH), ("ash light", ASH_LIGHT), ("ash shadow", ASH_SHADOW), ("char", CHAR),
           ("char edge", CHAR_LIGHT), ("rib", RIB_BASE), ("rib edge", RIB_LIGHT), ("ember rim", EMBER["color"]),
           ("ember", EMBER["hot"]), ("ember core", EMBER["core"]), ("teal", TEAL["hot"]), ("fang", FANG),
           ("row tint", ROW["color"])]
UV_WEIGHT = {"hide": 1.3, "char": 0.9, "rib": 1.0, "ember": 0.4, "maw": 0.75, "eye": 0.6, "bone": 0.6}


# ---- geometry helpers ------------------------------------------------------------------------------------------

def loft(rings, profile, cap0=True, cap1=True):
    """Closed tube through rings (y, cx, cz, w, h) of a unit profile [(x, z)] (rings perpendicular to Y)."""
    bm = bmesh.new()
    rv = [[bm.verts.new((cx + px * w / 2, y, cz + pz * h / 2)) for px, pz in profile] for y, cx, cz, w, h in rings]
    n = len(profile)
    for a, b in zip(rv[:-1], rv[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    if cap0:
        bm.faces.new(rv[0])
    if cap1:
        bm.faces.new(rv[-1])
    return M.recalc(bm)


def split_by_faces(bm, key_fn):
    """{key: bmesh copy keeping only the faces with key_fn(face) == key}. bm is freed."""
    bm.normal_update()
    keys = sorted({key_fn(f) for f in bm.faces})
    out = {}
    for k in keys:
        c = bm.copy()
        c.normal_update()
        dele = [f for f in c.faces if key_fn(f) != k]
        bmesh.ops.delete(c, geom=dele, context="FACES")
        out[k] = c
    bm.free()
    return out


def arc_band(pts, radial, width, thick):
    """A flat band (rib) along points `pts` with outward directions `radial`: `width` along the band's
    side axis (tangent x radial), `thick` along radial (outward from the point). Closed, 4 verts per point."""
    bm = bmesh.new()
    rings = []
    n = len(pts)
    for i in range(n):
        p = Vector(pts[i])
        t = (Vector(pts[min(n - 1, i + 1)]) - Vector(pts[max(0, i - 1)])).normalized()
        r = Vector(radial[i]).normalized()
        s = t.cross(r).normalized()
        rings.append([bm.verts.new(p + s * width / 2), bm.verts.new(p + s * width / 2 + r * thick),
                      bm.verts.new(p - s * width / 2 + r * thick), bm.verts.new(p - s * width / 2)])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    return M.recalc(bm)


def shard(base, direction, length, r, flat=0.45, x_hint=(1, 0, 0), rot=45.0):
    """A flattened 4-sided spike from `base` along `direction` (its wide side follows x_hint)."""
    b = M.spike(r, length, sides=4, base_scale=(1.0, flat), rot_offset=rot)
    M.xform(b, matrix=M.orient(Vector(base), direction, x_hint))
    return b


def torso_ring(y):
    """The torso loft's ring (y, cx, cz, w, h) at y (linear between its rings, clamped)."""
    rs = sorted(TORSO_RINGS)
    if y <= rs[0][0]:
        return rs[0]
    for r0, r1 in zip(rs[:-1], rs[1:]):
        if r0[0] <= y <= r1[0]:
            t = (y - r0[0]) / (r1[0] - r0[0])
            return tuple(a + (b - a) * t for a, b in zip(r0, r1))
    return rs[-1]


def fore_top(y):
    """Top of the torso loft at y."""
    _, _, cz, _, h = torso_ring(y)
    return cz + h / 2


def torso_pt(y, px, pz, grow=0.0):
    """A point on the torso loft's surface at y for a profile coordinate (px, pz), pushed out by `grow` m."""
    _, cx, cz, w, h = torso_ring(y)
    return Vector((cx + px * (w / 2 + grow), y, cz + pz * (h / 2 + grow)))


def torso_ring_verts(shift=None, inset=0.0, lo=0, hi=None):
    """The torso rings' vertex positions (Vectors) with WIN_SHIFT-style y shifts, pulled `inset` m inside."""
    shift = shift or {}
    out = []
    for i, (y, cx, cz, w, h) in enumerate(TORSO_RINGS[lo:hi], start=lo):
        out.append([Vector((cx + px * (w / 2 - inset), y + shift.get((i, k), 0.0), cz + pz * (h / 2 - inset)))
                    for k, (px, pz) in enumerate(BODY_PROFILE)])
    return out


def loft_open(ring_verts, skip=(), ring0=0):
    """A lofted tube through ring_verts (lists of Vectors of equal length) without the faces (ring interval i,
    profile segment k) in `skip` (interval numbers start at ring0), capped at both ends."""
    bm = bmesh.new()
    rv = [[bm.verts.new(p) for p in ring] for ring in ring_verts]
    n = len(rv[0])
    for i, (a, b) in enumerate(zip(rv[:-1], rv[1:]), start=ring0):
        for k in range(n):
            if (i, k) not in skip:
                bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    bm.faces.new(rv[0])
    bm.faces.new(rv[-1])
    return M.recalc(bm)


# ---- the model ------------------------------------------------------------------------------------------------

class Build:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.info = {}

    def torso(self, a):
        """Neck, shoulders and chest as ONE loft (a wedge from above), burnt open in one chest window over an
        ember core and crossed by one black rib bar; then the loin + rump (tail bone). Down-facing faces are char,
        the rest ash hide."""
        def zone_down(f, lim=-0.42):
            return "char" if f.normal.z < lim else "hide"
        torso = loft_open(torso_ring_verts(WIN_SHIFT), WIN_FACES)
        # a burnt, ragged rim: the window's edge vertices step a little in and out along the body
        for v in torso.verts:
            if any(e.is_boundary for e in v.link_edges):
                v.co.y += self.rng.uniform(-0.006, 0.006)
        M.noise_displace(torso, 0.005, freq=8.0, seed=SEED)
        self.window_edges = [[e.verts[0].co.copy(), e.verts[1].co.copy()] for e in torso.edges if e.is_boundary]
        for z, piece in split_by_faces(torso, zone_down).items():
            a.add(piece, z, bone="body", name="torso_" + z, shading="auto", sharp_angle=28.0)
        # ember core: the torso itself from the shoulders to the waist, 12 mm inside the hide, so it fills the
        # window to the brim (no see-through slivers past back-face-culled inner walls in the engine)
        core = loft_open(torso_ring_verts(WIN_SHIFT, inset=0.012, lo=3), ring0=3)
        a.add(core, "ember", bone="body", name="ember_core", shading="smooth")
        # the one rib: a black hoop from the left lower chest over the top to the right upper flank. It runs along
        # the window's rear edge (half over the glow, half over the hide), stands 12 mm proud, and both ends dive
        # under the hide
        pts, rad = [], []
        for k, grow in ((4, -0.035), (3, -0.01), (2, -0.01), (1, -0.01), (0, -0.01), (9, -0.01), (8, -0.035)):
            px, pz = BODY_PROFILE[k]
            p = torso_pt(WIN_Y[1] + WIN_SHIFT.get((5, k), 0.0), px, pz, grow)
            pts.append(p)
            _, _, cz, w, h = torso_ring(p.y)
            rad.append(Vector((px / (w / 2), 0.0, pz / (h / 2))).normalized())
        a.add(arc_band(pts, rad, RIB_W, 0.022), "rib", bone="body", name="rib", shading="flat")
        # loin + rump (tail bone): a tucked waist that swells into hard haunches (the narrow end of the wedge)
        rump = loft([(0.07, 0.0, 0.47, 0.12, 0.12), (0.15, 0.0, 0.47, 0.13, 0.12), (0.235, 0.0, 0.462, 0.185, 0.15),
                     (0.33, 0.0, 0.462, 0.19, 0.155), (0.425, 0.0, 0.475, 0.1, 0.095)], BODY_PROFILE)
        M.noise_displace(rump, 0.004, freq=9.0, seed=SEED + 1)
        for z, piece in split_by_faces(rump, zone_down).items():
            a.add(piece, z, bone="tail", name="rump_" + z, shading="auto", sharp_angle=28.0)

    def head(self, a):
        """Skull + upper jaw (head bone, hinged at JAW), lower jaw (body). Palate and jaw floor are teal maw.
        A jackal's head: a broad brow plane, a tapered snout, big raked-back triangular ears."""
        # review fix: a heavier skull - 0.2 m across the cheeks (was 0.15), a broad brow, a blunter muzzle
        skull = loft([(-0.385, 0.0, 0.612, 0.17, 0.13), (-0.44, 0.0, 0.62, 0.205, 0.145), (-0.51, 0.0, 0.601, 0.15, 0.108),
                      (-0.585, 0.0, 0.578, 0.1, 0.078), (-0.655, 0.0, 0.56, 0.066, 0.054)], SKULL_PROFILE)

        def skull_zone(f):
            c = f.calc_center_median()
            if f.normal.z < -0.55:
                # only the flat palate is maw (the bevelled lip faces stay char: no teal stripe at rest)
                return "maw" if (c.y < -0.46 and f.normal.z < -0.93) else "char"
            if c.y < -0.6:
                return "char"                           # burnt nose
            return "hide"
        for z, piece in split_by_faces(skull, skull_zone).items():
            a.add(piece, z, bone="head", name="skull_" + z, shading="auto", sharp_angle=28.0)
        jaw = loft([(-0.395, 0.0, 0.522, 0.13, 0.06), (-0.49, 0.0, 0.524, 0.1, 0.052),
                    (-0.565, 0.0, 0.524, 0.072, 0.04), (-0.632, 0.0, 0.526, 0.048, 0.029)], JAW_PROFILE)

        def jaw_zone(f):
            return "maw" if f.normal.z > 0.9 and f.calc_center_median().y < -0.43 else "char"
        for z, piece in split_by_faces(jaw, jaw_zone).items():
            a.add(piece, z, bone="body", name="jaw_" + z, shading="auto", sharp_angle=30.0)
        # fangs: upper canines over the jaw, lower canines up
        for sx in (1, -1):
            a.add(shard((sx * 0.036, -0.57, 0.552), (sx * 0.1, -0.15, -1.0), 0.04, 0.01, flat=0.8), "bone",
                  bone="head", name="fang_up", shading="flat")
            a.add(shard((sx * 0.027, -0.61, 0.522), (sx * 0.15, -0.2, 1.0), 0.028, 0.008, flat=0.8), "bone",
                  bone="body", name="fang_lo", shading="flat")
        # teal eye slits on the brow (they show the facing from above)
        for sx in (1, -1):
            e = M.sphere(1.0, 6, 3)
            M.xform(e, scale=(0.011, 0.027, 0.008))
            M.xform(e, rot=(14, 0, sx * -26))
            M.xform(e, loc=(sx * 0.058, -0.5, 0.645))
            a.add(e, "eye", bone="head", name="eye", shading="smooth")
        # ash cheek ruffs flaring back off the jaw corners: the skull reads broad from above
        for sx in (1, -1):
            d = Vector((sx * 0.85, 0.8, 0.05)).normalized()
            a.add(shard((sx * 0.075, -0.45, 0.585), d, 0.085, 0.034, flat=0.4, x_hint=(d.y, -d.x, 0.0), rot=0.0),
                  "hide", bone="head", name="cheek_ruff", shading="flat")
        # ears: big black jackal ears (review fix: a broader base, set wider), raked back and splayed out so they
        # break the outline from the game camera; the right one is torn off halfway
        for sx, ln in ((1, 0.22), (-1, 0.125)):
            base = Vector((sx * 0.072, -0.425, 0.672))
            d = Vector((sx * 0.62, 0.6, 0.85)).normalized()
            b = shard(base, d, ln, 0.066, flat=0.55, x_hint=(sx * 0.7, -0.7, 0.0), rot=0.0)
            if ln < 0.15:                               # the torn ear: a notched, blunt tip
                tip = max(b.verts, key=lambda v: (v.co - base).length)
                tip.co = base + d * ln + Vector((sx * 0.014, 0.0, 0.012))
            a.add(b, "char", bone="head", name="ear_" + ("L" if sx > 0 else "R"), shading="flat")
        self.info["mouth"] = Vector((0.0, -0.55, 0.54))
        self.info["head_top"] = 0.75

    def mane(self, a):
        """A black char crest streaming back off the neck and withers (a wind-torn cinder mane, leaning right),
        and (review fix) a broad ASH RUFF: flat blades flaring back and out off both shoulders, so the
        forequarters read about 0.5 m wide from the game camera. The ruff is fuller on the right (the mane
        leans right; the left flank is the burnt-open one)."""
        stations = [(-0.37, 0.0, 0.14, 0.03), (-0.31, -0.024, 0.2, 0.036), (-0.245, 0.012, 0.22, 0.038),
                    (-0.18, -0.026, 0.17, 0.034)]
        for y, x, ln, r in stations:
            z = fore_top(y)
            d = Vector((x * 4.0 - 0.18, 1.0, 0.62)).normalized()
            a.add(shard((x, y, z - 0.03), d, ln, r, flat=0.4, x_hint=(0, 0, 1), rot=self.rng.uniform(30, 60)), "char",
                  bone="body", name="mane", shading="flat")
        # ruff blades: (y, profile x, profile z, direction (out, back, up), length, base radius)
        blades = [(-0.335, 0.5, 0.86, (0.55, 1.0, 0.3), 0.16, 0.046), (-0.27, 0.8, 0.6, (0.72, 1.0, 0.12), 0.165, 0.05),
                  (-0.2, 0.95, 0.25, (0.78, 1.0, -0.06), 0.13, 0.046)]
        for sx, gain in ((1, 0.9), (-1, 1.1)):
            for y, px, pz, (dx, dy, dz), ln, r in blades:
                base = torso_pt(y, sx * px, pz, -0.02)
                d = Vector((sx * dx, dy, dz)).normalized()
                a.add(shard(base, d, ln * gain, r, flat=0.35, x_hint=(d.y, -d.x, 0.0), rot=0.0), "hide", bone="body",
                      name="ruff", shading="flat")

    def legs(self, a):
        """Front legs (legs_a) nearly straight under the shoulders; hind legs (legs_b) in the hound's Z.
        Upper legs are ash hide, lower legs and paws char."""
        self.feet = {}
        for sx in (1, -1):
            # review fix: the front legs hang from the wider shoulders, heavier in the upper arm
            sh = Vector((sx * 0.15, -0.205, 0.47))
            el = Vector((sx * 0.14, -0.155, 0.285))
            wr = Vector((sx * 0.118, -0.19, 0.085))
            pw = Vector((sx * 0.118, -0.228, 0.03))
            a.add(M.tube([sh, el], [0.066, 0.04], sides=6), "hide", bone="legs_a", name="upperarm", shading="auto")
            a.add(M.tube([el + Vector((0, 0.004, 0.02)), wr, pw], [0.038, 0.026, 0.02], sides=5), "char", bone="legs_a",
                  name="forearm", shading="auto", sharp_angle=40.0)
            paw = M.sphere(1.0, 5, 3)
            M.xform(paw, loc=(pw.x, pw.y - 0.018, 0.02), scale=(0.028, 0.045, 0.02))
            a.add(paw, "char", bone="legs_a", name="paw_f", shading="flat")
            self.feet["F" + ("L" if sx > 0 else "R")] = pw
            hp = Vector((sx * 0.092, 0.3, 0.45))
            st = Vector((sx * 0.102, 0.215, 0.27))
            hk = Vector((sx * 0.095, 0.37, 0.13))
            pw = Vector((sx * 0.095, 0.345, 0.03))
            a.add(M.tube([hp, st], [0.07, 0.04], sides=6), "hide", bone="legs_b", name="thigh", shading="auto")
            a.add(M.tube([st + Vector((0, 0.005, 0.015)), hk, pw], [0.038, 0.025, 0.02], sides=5), "char", bone="legs_b",
                  name="shin", shading="auto", sharp_angle=40.0)
            a.add(shard(hk + Vector((0, 0.01, 0.0)), (0, 1.0, 0.35), 0.05, 0.014, flat=0.6), "char", bone="legs_b",
                  name="hock_spur", shading="flat")
            paw = M.sphere(1.0, 5, 3)
            M.xform(paw, loc=(pw.x, pw.y - 0.018, 0.02), scale=(0.027, 0.043, 0.02))
            a.add(paw, "char", bone="legs_b", name="paw_h", shading="flat")
            self.feet["H" + ("L" if sx > 0 else "R")] = pw

    def tail(self, a):
        """A thick brush tail streaming straight back (a rudder at speed) with ash tatters torn off its top,
        ending in an ember cinder."""
        pts = [Vector(p) for p in ((0.0, 0.405, 0.492), (0.0, 0.5, 0.477), (0.01, 0.6, 0.468), (0.024, 0.69, 0.465),
                                    (0.03, 0.735, 0.462))]
        t = M.tube(pts, [0.034, 0.048, 0.05, 0.04, 0.02], sides=6)

        def tz(f):
            return "char" if f.normal.z < -0.35 else "hide"
        for z, piece in split_by_faces(t, tz).items():
            a.add(piece, z, bone="tail", name="tail_" + z, shading="auto", sharp_angle=40.0)
        for u, ln, sx in ((0.3, 0.075, 0.25), (0.55, 0.07, -0.3), (0.78, 0.06, 0.2)):
            i = min(len(pts) - 2, int(u * (len(pts) - 1)))
            f = u * (len(pts) - 1) - i
            p = pts[i].lerp(pts[i + 1], f) + Vector((0, 0, 0.022))
            d = Vector((sx, 1.0, 0.45)).normalized()
            a.add(shard(p, d, ln, 0.02, flat=0.45, x_hint=(0, 0, 1)), "hide", bone="tail", name="tail_tatter",
                  shading="flat")
        d = (pts[-1] - pts[-2]).normalized()
        tip = shard(pts[-1] - d * 0.02, d, 0.075, 0.024, flat=0.75)
        a.add(tip, "ember", bone="tail", name="tail_cinder", shading="flat")
        back = shard(pts[-1] - d * 0.012, -d, 0.03, 0.024, flat=0.75)
        a.add(back, "ember", bone="tail", name="tail_cinder_b", shading="flat")
        self.info["tail_tip"] = pts[-1] + d * 0.03

    def build(self, col):
        a = M.Assembly(KEY + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        self.torso(a)
        self.head(a)
        self.mane(a)
        self.legs(a)
        self.tail(a)
        self.tris = a.tris()
        obj = a.to_object(col)
        self.parts = a.parts
        C.log("%s mesh: %d tris, %d parts" % (KEY, self.tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def pivots(self):
        return {"root": (0.0, Y_C, 0.0), "body": (0.0, Y_C, 0.42), "head": tuple(JAW), "legs_a": tuple(SHOULDER),
                "legs_b": tuple(HIP), "tail": tuple(LOIN)}

    def sockets(self):
        return [("body", "hit_center", (0.0, Y_C, 0.43)), ("body", "fx_core", tuple(CORE)),
                ("head", "fx_mouth", tuple(self.info["mouth"])), ("body", "head_top", (0.0, -0.3, 0.92))]

    # -- paint --
    def recipes(self):
        return {
            # ash hide: painted planes, wind-swept streaks along the body (speed, not grain), brushy edge light;
            # the top-plane lift and the burn from below are extra_passes()
            "hide": P.zone(base=ASH, shadow=ASH_SHADOW, light=ASH_LIGHT, planes=0.2, parts=0.07, brush=0.1,
                           brush_freq=4.0, stroke=(0.0, 1.0, 0.12), stroke_amount=0.2, stroke_freq=(28.0, 3.0),
                           edge=0.9, edge_width=0.008, edge_breakup=0.38, cavity=0.8, cavity_width=0.008, ao=0.65,
                           gradient={"axis": (0, 0, 1), "range": (0.46, 0.34), "color": "shadow", "amount": 0.3}),
            "char": P.zone(base=CHAR, shadow="#0B0808", light=CHAR_LIGHT, planes=0.14, parts=0.06, brush=0.06,
                           brush_freq=5.0, edge=0.95, edge_width=0.007, edge_breakup=0.35, cavity=0.6, ao=0.5),
            # the one rib bar: black, its edges only warm-lit by the core (no glowing strokes: one dark bar)
            "rib": P.zone(base=RIB_BASE, shadow="#100909", light=RIB_LIGHT, planes=0.12, parts=0.08, brush=0.05,
                          edge=0.6, edge_width=0.007, edge_breakup=0.3, cavity=0.5, ao=0.3),
            # the window glow: one small cooled-hot spot on the back, hot orange over most of the window, deepening
            # to the rim red down the burnt left flank; a darker painted base under it keeps the glow saturated
            # (a pale base under a big glow washes it to a pale lantern at 1x)
            "ember": P.faction_zone("unmade", "molten", glow=True,
                                    emit=dict(EMBER, mode="radial", center=tuple(EMBER_C), radius=0.2, base_mix=0.0,
                                              stops=[(0.0, EMBER["core"], "#E07A34"), (0.3, EMBER["hot"], "#C4501A"),
                                                     (0.7, EMBER["hot"], "#B0400F"), (1.0, EMBER["color"], "#7A1E05")])),
            "maw": P.faction_zone("unmade", "ichor", glow=True,
                                  emit=dict(TEAL, mode="radial", center=tuple(self.info["mouth"]), radius=0.12,
                                            base_mix=0.2)),
            "eye": P.faction_zone("unmade", "ichor", glow=True, emit=dict(TEAL, mode="flat")),
            "bone": P.faction_zone("unmade", "bone", base=FANG, planes=0.06, edge=0.4, cavity=0.3, ao=0.3),
        }

    def decals(self):
        """Few, bold marks: an ember crack burning through each shoulder and the rump (the hide is cinder)."""
        rng = random.Random(SEED + 100)
        out = []
        for sx in (1, -1):
            xa = Vector((0, sx, 0))       # frame X along -y/+y so lines run down the flank
            ya = Vector((0, 0, 1))
            za = Vector((sx, 0, 0))
            fr = Matrix(((xa.x, ya.x, za.x, sx * 0.05), (xa.y, ya.y, za.y, -0.2), (xa.z, ya.z, za.z, 0.42), (0, 0, 0, 1)))
            lines = M.crack_lines(rng, start=(0.0, 0.1), direction=-95 + rng.uniform(-15, 15), length=0.14, step=0.02,
                                  jag=0.4, branches=1, branch_len=0.4, depth=1)
            out += self._ember_lines(lines, fr, ["hide"], (-0.05, 0.2))
        top = Matrix.Translation((0, 0.3, 0.5))
        lines = M.crack_lines(rng, start=(0.03, -0.05), direction=70, length=0.12, step=0.02, jag=0.4, branches=1, depth=1)
        out += self._ember_lines(lines, top, ["hide"], (-0.1, 0.1))
        return out

    def _ember_lines(self, lines, frame, zones, depth, width=0.013):
        return [P.decal_lines(lines, frame, 0.001, zones=zones, color=None, rim="#4A2418", rim_width=0.02,
                              emit={"color": "#2A0E06", "core": "#2A0E06"}, depth=depth, facing=-0.1),
                P.decal_lines(lines, frame, width, zones=zones, color=EMBER["hot"], rim="#140C0B", rim_width=width * 2.2,
                              emit={"color": EMBER["color"], "core": EMBER["hot"]}, depth=depth, facing=0.2)]


# ---- extra paint passes (this build only; gfa_paint.paint stays unchanged) -----------------------------------
# gfa_paint has no normal- or height-driven pass. Like enemies/slag_king.py, this build wraps gfa_paint.paint for its
# one paint call: the zones paint as usual, these passes run, then the decals go on top (gfa_paint's decal loop):
#   * TOP PLANES of the ash hide (what the 55 deg camera mostly sees) are lifted toward the pale ash light, with a
#     brushy boundary; side planes part of the way. The lift skips texels that are already light (edge strokes);
#   * BURNT FROM THE GROUND UP: below a ragged line at about BURN_Z the hide chars to black (the lower chest, the
#     elbows and stifles), with a smouldering rust band on the line - the hound runs through cinders;
#   * THE BURNT WINDOW RIM (review fix; it replaces the ember strokes on the edges of four ribs, which read as a
#     barcode at 1x): the hide around the chest window chars in a thin brushy band (about 12 mm), with one
#     broken ember line on the very edge. Pale hide -> black rim -> hot core: one framed hot shape, measured to
#     the window's own boundary edges (Build.window_edges).
BURN_Z = 0.35


def _polyline_samples(lines, spacing=0.002):
    out = []
    for ln in lines:
        for a_, b_ in zip(ln[:-1], ln[1:]):
            n = max(1, int((b_ - a_).length / spacing))
            out.extend(a_.lerp(b_, (i + 0.5) / n) for i in range(n))
    return out


def extra_passes(maps, zones_order, base, emis, window_edges, seed=0):
    import numpy as np
    Z, pos, tn = maps["zone"], maps["pos"], maps["tnrm"]
    if "hide" in zones_order:
        m = Z == zones_order.index("hide")
        p, nz, c = pos[m], tn[m, 2], base[m]
        br = P.spread01(P.fbm(p, 5.0, 2, seed=seed + 501))
        nb = nz + (br - 0.5) * 0.35
        k = 0.35 * P.smoothstep(-0.1, 0.15, nb) + 0.65 * P.smoothstep(0.45, 0.62, nb)
        lum = c @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
        k = k * (1.0 - P.smoothstep(0.62, 0.75, lum))
        c = P.mix(c, P.hex3(ASH_LIGHT), k * 0.4)
        h = BURN_Z + (P.spread01(P.fbm(p, 7.0, 2, seed=seed + 502)) - 0.5) * 0.09
        d = p[:, 2] - h
        burn = P.smoothstep(0.008, -0.008, d)
        line = P.smoothstep(0.016, 0.004, np.abs(d))
        c = P.mix(c, P.hex3(CHAR) * 1.2, burn * 0.92)
        c = P.mix(c, P.hex3(SMOULDER), line * 0.8)
        emis[m] = np.maximum(emis[m], P.hex3("#3A1206")[None, :] * line[:, None])
        base[m] = c
    idx = [zones_order.index(z) for z in ("hide", "char") if z in zones_order]
    if idx and window_edges:
        m = np.isin(Z, idx)
        p = pos[m]
        d = P._kd_dist(_polyline_samples(window_edges), p, 0.05)
        br = P.spread01(P.fbm(p, 14.0, 2, seed=seed + 503))
        rim = P.smoothstep(0.017, 0.009, d + (br - 0.5) * 0.01)
        base[m] = P.mix(base[m], P.hex3(CHAR), rim * 0.7)
        dabs = P.spread01(P.fbm(p, 9.0, 2, seed=seed + 504))
        k = P.smoothstep(0.0075, 0.0035, d) * P.smoothstep(0.22, 0.34, dabs)
        base[m] = P.mix(base[m], P.hex3(EMBER["hot"]), k * 0.6)
        glow = P.mix(np.repeat(P.hex3(EMBER["color"])[None], len(p), 0), P.hex3(EMBER["hot"]), P.smoothstep(0.5, 1.0, k))
        emis[m] = np.maximum(emis[m], glow * k[:, None])
    return base, emis


def apply_decals(maps, zones_order, base, emis, decals):
    """gfa_paint.paint()'s decal loop (painted lines, burnt rims, glowing channels)."""
    import numpy as np
    Z = maps["zone"]
    for dec in decals:
        target = np.ones(len(Z), dtype=bool) if not dec["zones"] else np.isin(Z, [zones_order.index(z) for z in dec["zones"]])
        idx = np.nonzero(target)[0]
        line, rimm = P._decal_masks(dec, maps["pos"][idx], maps["tnrm"][idx])
        if dec["rim"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["rim"]), rimm * 0.75)
        if dec["color"]:
            base[idx] = P.mix(base[idx], P.hex3(dec["color"]), line)
        if dec["emit"]:
            ec = P.hex3(dec["emit"]["color"])
            core = P.hex3(dec["emit"].get("core", dec["emit"]["color"]))
            glow = P.mix(np.repeat(ec[None], len(idx), 0), core, P.smoothstep(0.5, 1.0, line))
            emis[idx] = np.maximum(emis[idx], glow * np.maximum(line, rimm * 0.25)[:, None])
    return base, emis


@contextmanager
def painter_passes(window_edges):
    """Within the block, gfa_paint.paint also runs extra_passes() (between the zones and the decals)."""
    import numpy as np
    orig = P.paint

    def paint(maps, zones_order, recipes_, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes_, dist_convex, dist_concave, (), seed)
        base, emis = extra_passes(maps, zones_order, base, emis, window_edges, seed)
        base, emis = apply_decals(maps, zones_order, base, emis, decals)
        return np.clip(base, 0, 1), np.clip(emis, 0, 1)

    P.paint = paint
    try:
        yield
    finally:
        P.paint = orig


# ---- UVs: importance-weighted islands (same wrapper as enemies/clinker.py) -----------------------------------

def weighted_unwrap(orig_unwrap):
    import numpy as np

    def unwrap(obj, size=1024, margin_px=6, angle_limit=60.0, **kw):
        me = obj.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        zones = [s.material.name[4:] for s in obj.material_slots]
        pids = np.empty(len(me.polygons), dtype=np.int64)
        me.attributes["gfa_part"].data.foreach_get("value", pids)
        mats = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("material_index", mats)
        vpart = np.full(n, -1, dtype=np.int64)
        vzone = np.zeros(n, dtype=np.int64)
        for poly in me.polygons:
            for vi in poly.vertices:
                vpart[vi] = pids[poly.index]
                vzone[vi] = mats[poly.index]
        new = co.copy()
        for pid in np.unique(vpart):
            m = vpart == pid
            w = UV_WEIGHT.get(zones[int(vzone[m][0])], 1.0)
            c = co[m].mean(0)
            new[m] = c + (co[m] - c) * w
        me.vertices.foreach_set("co", new.ravel())
        me.update()
        orig_unwrap(obj, size, margin_px, angle_limit, **kw)
        me.vertices.foreach_set("co", co.ravel())
        me.update()
        return P.texel_density(obj, size)
    return unwrap


# ---- preview (flat zone colours, Workbench: fast silhouette iterations) --------------------------------------

PREVIEW_COLORS = {"hide": "#948C82", "char": "#221C1D", "rib": "#2A1D1A", "ember": "#FF6B1A", "maw": "#2FBFA8",
                  "eye": "#2FBFA8", "bone": "#B3A58F"}


def preview(mesh, work):
    import gfa_boss as B
    views = dict(R.CREATURE_VIEWS)
    out = B.flat_views([mesh], work, KEY, PREVIEW_COLORS, views, size=420)
    # game camera, true pixel size, flat colours on the floor
    scene = bpy.context.scene
    fl = B._floor(scene)
    fm = fl.data.materials[0]
    fm.diffuse_color = C.hex_linear(R.FLOOR)
    for yaw, tag in ((-35.0, "face"), (145.0, "away"), (90.0, "side"), (0.0, "head"), (180.0, "tail")):
        mesh.rotation_euler = (0, 0, math.radians(yaw))
        bpy.context.view_layer.update()
        ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
        px = 80
        R.aim(scene, Vector((0, 0, 0.35)), B.game_dir(), px / ppm, dist=60.0)
        out["game_" + tag] = R.render(scene, os.path.join(work, "%s_flat_game_%s.png" % (KEY, tag)), px)
    mesh.rotation_euler = (0, 0, 0)
    C.remove_objects([fl])
    return out


# ---- clips ------------------------------------------------------------------------------------------------------
# Pose dicts in GF_Swarm_v1's shared bone frame (gfa_rig): rot degrees (+X pitch nose-down / a leg group swings
# its feet back, +Y yaw left, +Z roll left side up), loc metres (+X left, +Y up, +Z forward).

def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def follow_tail(pose):
    """The hind legs (legs_b, pivot HIP) hang from the rump, which rides on the tail bone (pivot LOIN). Compose
    the tail bone's rotation / translation into legs_b so the hips stay on the rump when the spine flexes:
    loc = Rt h - h + Rt L_own + loc_tail, rot = Rt @ R_own (h = HIP - LOIN in the bone frame)."""
    tr = pose.get("tail", {})
    Rt = Euler([math.radians(v) for v in tr.get("rot", (0, 0, 0))], "XYZ").to_matrix()
    h = HIP - LOIN
    hl = Vector((h.x, h.z, -h.y))
    lb = pose.setdefault("legs_b", {})
    Rl = Euler([math.radians(v) for v in lb.get("rot", (0, 0, 0))], "XYZ").to_matrix()
    own = Vector(lb.get("loc", (0, 0, 0)))
    loc = Rt @ hl - hl + Rt @ own + Vector(tr.get("loc", (0, 0, 0)))
    lb["rot"] = tuple(math.degrees(v) for v in (Rt @ Rl).to_euler("XYZ"))
    lb["loc"] = tuple(loc)
    return pose


def counter(pose, gain=1.0):
    """Cancel small root + body rotations on both leg groups (feet stay planted while the body breathes)."""
    tot = (0.0, 0.0, 0.0)
    for b in ("root", "body"):
        tot = _add(tot, pose.get(b, {}).get("rot", (0, 0, 0)))
    for g in ("legs_a", "legs_b"):
        tr = pose.setdefault(g, {})
        tr["rot"] = _add(tr.get("rot", (0, 0, 0)), tuple(-gain * v for v in tot))
    return pose


def pulse(t, t0, w):
    d = ((t - t0 + 0.5) % 1.0) - 0.5
    return math.exp(-(d / w) ** 2)


MOTION = dict(move_frames=10, idle_frames=48, front=40.0, hind=36.0, flex=11.0, pitch=6.0, bob=0.035, lift=0.05,
              move_cycle_m=1.4)


def make_clips(arm):
    mo = MOTION
    sin, cos, tau = math.sin, math.cos, 2 * math.pi

    def idle(t):
        """The hunting stance: slow breaths, a snarl (the skull lifts off the teal jaw), a sniff dip, tail sway."""
        w = tau * t
        snarl = pulse(t, 0.32, 0.06)
        sniff = pulse(t, 0.72, 0.045)
        p = {"root": {"loc": (0, 0.005 * sin(w), 0)},
             "body": {"rot": (1.5 * sin(w) + 4.0 * sniff, 1.5 * sin(w + 1.0), 0.8 * sin(w + 0.4))},
             "head": {"rot": (-3.0 - 1.5 * (0.5 + 0.5 * sin(2 * w)) - 16.0 * snarl + 5.0 * sniff, 3.0 * sin(w + 2.0), 0)},
             "tail": {"rot": (-1.5 * sin(w - 0.6), 3.5 * sin(w + 0.8), 0)}}
        counter(p)
        return follow_tail(p)

    def move(t):
        """Double-suspension gallop, one stride. t=0: extended suspension (front feet reaching, hind feet
        thrown back, spine stretched); t=.25 front stance (nose dips); t=.5 gathered suspension (front feet
        swept back, hind feet reaching under the ribs, spine arched, rump tucked); t=.75 hind stance."""
        w = tau * t
        p = {"root": {"loc": (0, mo["bob"] * cos(2 * w) + 0.012, 0)},
             "body": {"rot": (mo["pitch"] * sin(w), 0, 0)},
             "head": {"rot": (-2.0 - 2.0 * sin(w), 0, 0)},
             "legs_a": {"rot": (-mo["front"] * cos(w), 0, 0), "loc": (0, mo["lift"] * max(0.0, -sin(w)), 0)},
             "legs_b": {"rot": (mo["hind"] * cos(w), 0, 0), "loc": (0, mo["lift"] * max(0.0, sin(w)), 0)},
             "tail": {"rot": (mo["flex"] * cos(w), 0, 0)}}
        return follow_tail(p)

    F = follow_tail
    rest = {}
    coil = F({"root": {"loc": (0, -0.03, -0.02)}, "body": {"rot": (4, 0, 0)}, "head": {"rot": (-8, 0, 0)},
              "legs_a": {"rot": (-10, 0, 0), "loc": (0, 0.02, 0)}, "legs_b": {"rot": (-8, 0, 0), "loc": (0, 0.02, 0)},
              "tail": {"rot": (-5, 0, 0)}})
    loaded = F({"root": {"loc": (0, -0.065, -0.05)}, "body": {"rot": (6, 0, 2)}, "head": {"rot": (-36, 0, 0)},
                "legs_a": {"rot": (-24, 0, 0), "loc": (0, 0.045, 0)}, "legs_b": {"rot": (-17, 0, 0), "loc": (0, 0.04, 0)},
                "tail": {"rot": (-10, 0, 0)}})
    loaded2 = F({"root": {"loc": (0, -0.07, -0.055)}, "body": {"rot": (7, 0, 2)}, "head": {"rot": (-40, 0, 0)},
                 "legs_a": {"rot": (-25, 0, 0), "loc": (0, 0.048, 0)}, "legs_b": {"rot": (-18, 0, 0), "loc": (0, 0.042, 0)},
                 "tail": {"rot": (-11, 0, 0)}})
    leap = F({"root": {"loc": (0, 0.07, 0.3)}, "body": {"rot": (-4, 0, 0)}, "head": {"rot": (-42, 0, 0)},
              "legs_a": {"rot": (-52, 0, 0), "loc": (0, 0.03, 0)}, "legs_b": {"rot": (44, 0, 0)}, "tail": {"rot": (14, 0, 0)}})
    bite = F({"root": {"loc": (0, 0.0, 0.36)}, "body": {"rot": (13, 0, 0)}, "head": {"rot": (4, 0, 0)},
              "legs_a": {"rot": (-32, 0, 0), "loc": (0, 0.02, 0)}, "legs_b": {"rot": (30, 0, 0)}, "tail": {"rot": (7, 0, 0)}})
    shake = F({"root": {"loc": (0, -0.01, 0.34)}, "body": {"rot": (11, 7, -5)}, "head": {"rot": (2, 13, -6)},
               "legs_a": {"rot": (-26, 0, 0), "loc": (0, 0.02, 0)}, "legs_b": {"rot": (24, 0, 0)}, "tail": {"rot": (4, -5, 0)}})
    shake2 = F({"root": {"loc": (0, -0.01, 0.3)}, "body": {"rot": (10, -6, 4)}, "head": {"rot": (1, -11, 5)},
                "legs_a": {"rot": (-20, 0, 0), "loc": (0, 0.015, 0)}, "legs_b": {"rot": (18, 0, 0)},
                "tail": {"rot": (3, 5, 0)}})
    back = F({"root": {"loc": (0, 0.0, 0.1)}, "body": {"rot": (3, 0, 0)}, "head": {"rot": (-4, 0, 0)},
              "legs_a": {"rot": (-6, 0, 0)}, "legs_b": {"rot": (6, 0, 0)}, "tail": {"rot": (2, 0, 0)}})
    flinch = F(counter({"root": {"loc": (0, -0.03, -0.03)}, "body": {"rot": (-9, -8, 12), "loc": (0, 0.0, -0.02)},
                        "head": {"rot": (-24, -12, 4)}, "tail": {"rot": (-5, 7, 0)}}, gain=0.7))
    settle = F(counter({"body": {"rot": (3, 3, -3)}, "head": {"rot": (-6, 4, 0)}, "tail": {"rot": (2, -3, 0)}}))
    jolt = F({"root": {"loc": (0, 0.02, 0)}, "body": {"rot": (-16, 0, 6)}, "head": {"rot": (-32, 0, 0)},
              "legs_a": {"rot": (-10, 0, 0)}, "legs_b": {"rot": (8, 0, 0)}, "tail": {"rot": (6, 0, 0)}})
    stumble = F({"root": {"loc": (0, -0.08, 0.12)}, "body": {"rot": (22, 0, 26)}, "head": {"rot": (-12, 10, 0)},
                 "legs_a": {"rot": (38, 0, -8)}, "legs_b": {"rot": (-12, 0, 6)}, "tail": {"rot": (-10, 0, 0)}})
    side = F({"root": {"loc": (0, -0.145, 0.15)}, "body": {"rot": (6, 0, 84)}, "head": {"rot": (-14, 0, -18)},
              "legs_a": {"rot": (-28, 0, 16)}, "legs_b": {"rot": (22, 0, 12)}, "tail": {"rot": (4, 12, 0)}})
    crumble = F({"root": {"loc": (0, -0.19, 0.15)}, "body": {"rot": (6, 0, 88), "scale": 0.6},
                 "head": {"rot": (-10, 0, -22), "scale": 0.6}, "legs_a": {"rot": (-30, 0, 18), "scale": 0.45},
                 "legs_b": {"rot": (24, 0, 14), "scale": 0.45}, "tail": {"rot": (4, 14, 0), "scale": 0.55}})
    gone = F({"root": {"loc": (0, -0.24, 0.15)}, "body": {"rot": (6, 0, 88), "scale": 0.02},
              "head": {"rot": (-10, 0, -22), "scale": 0.02}, "legs_a": {"rot": (-30, 0, 18), "scale": 0.02},
              "legs_b": {"rot": (24, 0, 14), "scale": 0.02}, "tail": {"rot": (4, 14, 0), "scale": 0.02}})
    RIG.cycle_clip(arm, KEY, "idle@loop", mo["idle_frames"], idle)
    RIG.cycle_clip(arm, KEY, "move@loop", mo["move_frames"], move)
    RIG.keyed_clip(arm, KEY, "windup", [(0, rest), (4, coil), (11, loaded), (15, loaded2)])
    RIG.keyed_clip(arm, KEY, "attack", [(0, loaded2), (3, leap), (5, bite), (7, shake), (9, shake2), (12, back), (15, rest)])
    RIG.keyed_clip(arm, KEY, "hit", [(0, rest), (2, flinch), (5, settle), (9, rest)])
    RIG.keyed_clip(arm, KEY, "death", [(0, rest), (3, jolt), (8, stumble), (14, side), (20, crumble), (26, gone),
                                       (27, gone)])
    return [RIG.clip_name(KEY, c) for c in SPEC.ENEMY_CLIPS_REQUIRED]


# key frames shown in the review strips
KEY_FRAMES = {"idle@loop": [0, 15, 34, 40], "move@loop": [0, 2, 5, 7], "windup": [0, 4, 11, 15],
              "attack": [0, 3, 5, 7, 12], "hit": [0, 2, 5, 9], "death": [0, 3, 8, 14, 20, 26]}


# ---- review --------------------------------------------------------------------------------------------------------

def _emit_mat(name, hexc):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = C.hex_linear(hexc)
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def guide_bar(name, p0, p1, thick, hexc):
    b = M.box((abs(p1[0] - p0[0]) + thick, abs(p1[1] - p0[1]) + thick, abs(p1[2] - p0[2]) + thick))
    me = bpy.data.meshes.new(name)
    b.to_mesh(me)
    b.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = [(a + c) / 2 for a, c in zip(p0, p1)]
    me.materials.append(_emit_mat("GUIDE_" + hexc, hexc))
    return ob


def size_compare(mesh, work, height):
    """Side view of the ashrunner beside the 2.2 m hero mannequin, the hero's waist line (the swarm ceiling),
    the ashrunner's own top and a 1 m bar on the ground."""
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (0.0, 1.35, 0.0)
    bpy.context.view_layer.update()
    bars = [guide_bar("GUIDE_waist", (0.8, -0.9, 1.1), (0.8, 1.9, 1.1), 0.012, "#D9CFA6"),
            guide_bar("GUIDE_top", (0.8, -0.9, height), (0.8, 0.95, height), 0.008, "#FF9A5A"),
            guide_bar("GUIDE_ground", (0.8, -0.9, 0.0), (0.8, 1.9, 0.0), 0.01, "#6B5A50"),
            guide_bar("GUIDE_m", (0.8, -0.7, -0.03), (0.8, 0.3, -0.03), 0.02, "#8FA0B0")]
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh, man], ink=0.008, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (0.0, 0.5, 1.12), (1.0, 0.0, 0.0), 2.75)
        p = R.render(scene, os.path.join(work, "%s_size_side.png" % KEY), 440, 440)
    C.remove_objects([man] + bars)
    return p


def clip_strips(arm, mesh, work):
    scene = bpy.context.scene
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    pts = R._points([mesh])
    d = R.CREATURE_VIEWS["34_front"]
    c, w, h = R.frame(pts, d)
    ext = max(w, h) * 1.5
    R.setup_cycles(scene, 10)
    out = []
    with R.toon_preview([mesh], ink=0.004):
        for clip, frames in KEY_FRAMES.items():
            track = RIG.clip_name(KEY, clip)
            for f in frames:
                RIG.pose_at(arm, track, f)
                R.aim(scene, c + Vector((0, 0.08, 0.02)), d, ext)
                p = os.path.join(work, "%s_clip_%s_f%02d.png" % (KEY, clip.replace("@", "_"), f))
                out.append((clip, f, R.render(scene, p, 200)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def ingame_poses(arm, mesh, work, yaw=-35.0, px=84):
    """Key poses through the game camera at true 1080p pixel size (no mannequin)."""
    out = []
    arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
    poses = [("rest", None, 0), ("gallop f0", "move@loop", 0), ("gallop f5", "move@loop", 5),
             ("wind-up (loaded)", "windup", 15), ("lunge", "attack", 3), ("bite", "attack", 5), ("hit", "hit", 2),
             ("death", "death", 14)]
    for label, clip, f in poses:
        if clip:
            RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
        else:
            RIG.unmute_none(arm)
        bpy.context.view_layer.update()
        tag = label.split()[0].replace("-", "") + ("%d" % f if clip == "move@loop" else "")
        r = R.ingame([mesh], work, "%s_pose_%s" % (KEY, tag), px=px, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                     target=(0.0, 0.0, 0.3), silhouette_too=False, ink=0.01)
        out.append((label, r["color"]))
    RIG.unmute_none(arm)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.frame_set(0)
    return out


def gallop_strip(arm, mesh, work, yaw, tag, px=84):
    """move@loop, every 2nd frame, through the game camera at true pixel size."""
    out = []
    arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
    for f in range(0, MOTION["move_frames"], 2):
        RIG.pose_at(arm, RIG.clip_name(KEY, "move@loop"), f)
        r = R.ingame([mesh], work, "%s_gallop_%s_f%02d" % (KEY, tag, f), px=px, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                     target=(0.0, 0.0, 0.3), silhouette_too=False, ink=0.01)
        out.append((f, r["color"]))
    RIG.unmute_none(arm)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.frame_set(0)
    return out


def beauty(arm, mesh, reports):
    """reports/ashrunner_34.png: the hound mid-gallop (extended suspension) beside its rest pose, 3/4 front, toon
    preview of the final textures - the close-up for the user's approval."""
    scene = bpy.context.scene
    R.setup_cycles(scene, 16)
    out = []
    for tag, clip, f in (("gallop", "move@loop", 0), ("windup", "windup", 15)):
        RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
        with R.toon_preview([mesh], ink=0.005):
            R.aim(scene, (0.0, -0.02, 0.36), (0.72, -0.62, 0.34), 1.75)
            out.append(R.render(scene, os.path.join(reports, "..", "work", "%s_34_%s.png" % (KEY, tag)), 760, 560))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    layout = {"title": "Ashrunner - burnt-open chest, teal maw", "subtitle": "gallop (extended suspension) | wind-up "
              "(the skull tips back off the teal jaw: the bite telegraph)", "width": 1600,
              "sections": [{"label": "3/4 front, toon preview of the final textures", "height": 560,
                            "images": [{"path": out[0], "label": "move@loop f0"}, {"path": out[1], "label": "windup f15"}]}]}
    return R.contact_sheet(layout, os.path.join(reports, "%s_34.png" % KEY), os.path.join(reports, "..", "work"))


def review(arm, mesh, rep, reports, work, tex, notes):
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    beauty(arm, mesh, reports)
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    turn = R.turnaround([mesh], work, KEY, R.CREATURE_VIEWS, size=400)
    height = rep.get("height_m") or 0.7
    size_p = size_compare(mesh, work, height)
    strips = clip_strips(arm, mesh, work)
    ing = []
    for label, yaw, pose in (("facing the camera, rest", -35.0, None), ("running across, gallop f2", 90.0, 2),
                             ("running away, gallop f7", 150.0, 7), ("head-on (the hunting approach), gallop f2", 0.0, 2),
                             ("tail-on, gallop f7", 180.0, 7)):
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        if pose is not None:
            RIG.pose_at(arm, RIG.clip_name(KEY, "move@loop"), pose)
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.1, 0.35, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_%d" % (KEY, int(yaw) % 360), px=150, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                     mannequin_obj=man, target=(-0.45, 0.1, 0.55))
        C.remove_objects([man])
        RIG.unmute_none(arm)
        ing.append((label, r))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    poses = ingame_poses(arm, mesh, work)
    gal_a = gallop_strip(arm, mesh, work, 90.0, "across")
    gal_b = gallop_strip(arm, mesh, work, -30.0, "toward")
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Ashrunner - the ash hound  (ashrunner.glb)",
        "subtitle": "Swarm Hound | The Unmade | Cinder Wastes | verb SPRINT | GF_Swarm_v1 | burnt-open chest, teal maw",
        "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 240, "images": [{"path": v, "label": k} for k, v in turn.items()]},
            {"label": "Size vs the 2.2 m hero (side; waist line = swarm ceiling, blue bar = 1 m) | in-game camera, 55 deg, "
                      "%.1f px/m, TRUE size 1x, then 3x nearest" % ppm,
             "height": None, "images": [{"path": size_p, "label": "side: %.2f m tall = %.2f x hero" % (height, height / 2.2)},
                                        {"path": ing[0][1]["color"], "label": "1x"}]
                + [{"path": r["color"], "label": "3x " + lb, "scale": 3} for lb, r in ing]},
            {"label": "Game-size silhouette (3x) and key poses through the game camera at TRUE pixel size (3x nearest)",
             "height": None, "images": [{"path": ing[1][1]["sil"], "label": "silhouette 3x (gallop)", "scale": 3}]
                + [{"path": p, "label": lb, "scale": 3} for lb, p in poses]},
            {"label": "SPRINT at game size: move@loop every 2nd frame, true pixels 3x nearest (across the screen, then toward the camera)",
             "height": None, "images": [{"path": p, "label": "f%d" % f, "scale": 3} for f, p in gal_a + gal_b]},
            {"label": "Clip key frames (3/4 front): idle@loop, move@loop (gallop), windup, attack (lunge bite), hit, death",
             "height": 150, "images": [{"path": p, "label": "%s f%d" % (cl, f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220, "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    out = {"sheet": R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)}
    out.update({"turn": turn, "size": size_p, "ingame": ing, "poses": poses})
    return out


# ---- main ----------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 512, int)
    C.reset_scene(fps=FPS)
    col = C.get_collection(KEY)
    b = Build()
    mesh = b.build(col)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work"))
    if C.flag(argv, "--preview"):
        out = preview(mesh, work)
        C.log("preview", out)
        return
    tex_dir = os.path.join(pack, "textures")
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    P.unwrap = weighted_unwrap(P.unwrap)
    with painter_passes(b.window_edges):
        paint_rep = P.paint_asset(mesh, KEY, b.recipes(), tex_dir, size=size, decals=b.decals(), ao_distance=0.04,
                                  ao_samples=16, edge_min_angle=24.0, margin_px=3, uv_angle=66.0, seed=SEED)
    arm = RIG.build_swarm_rig(b.pivots(), col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in b.sockets():
        RIG.add_socket(arm, bone, name, p)
    make_clips(arm)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    extra = {
        "content_key": KEY,
        "faction": "unmade",
        "verb": "SPRINT",
        "gait": "double-suspension gallop: legs_a = both front legs (pivot: shoulders), legs_b = both hind legs "
                "(pivot: hips); the tail bone is the loin + rump + tail and flexes the spine each stride",
        "jaw": "the head bone is the skull + upper jaw hinged at the jaw joint: pitching it nose-up (-X) opens the "
               "mouth and shows the teal maw (the bite telegraph in windup)",
        "move_cycle_m": MOTION["move_cycle_m"],
        "move_note": "play move@loop at speed / move_cycle_m cycles per second (row speed 5.2 m/s -> about 3.7 "
                     "strides/s, a 0.27 s gallop stride)",
        "content_row": ROW,
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
        "skin": skin,
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.log("clips", RIG.clips_report(arm))
    rep_path = os.path.join(reports, "%s_build_report.json" % KEY)
    C.write_json(rep_path, {"export": {k: rep[k] for k in rep if k not in ("nodes",)}, "paint": paint_rep, "skin": skin,
                            "parts": b.parts, "tris_blender": b.tris, "clips": RIG.clips_report(arm)})
    if not C.flag(argv, "--no-review"):
        tex = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        notes = [
            "%s tris (swarm budget 600-1500) | textures %s | %.2f m tall (%.2f x hero), %.2f m long | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"], rep["height_m"] / 2.2,
                (rep["bounds"]["max"][2] - rep["bounds"]["min"][2]), ", ".join(sorted(rep["sockets"]))),
            "Clips: %s" % ", ".join(c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
            "Gallop: front pair / hind pair + spine flex (tail bone). Jaw: the head bone lifts the skull off the teal jaw. "
            "move_cycle_m %.2f. Status: %s." % (MOTION["move_cycle_m"], SPEC.STATUS_AI_FINAL),
        ]
        review(arm, mesh, rep, reports, work, tex, notes)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
