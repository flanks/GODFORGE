"""Ashrunner - the Cinder Wastes swarm hound (The Unmade): built, painted, rigged on GF_Swarm_v1, animated,
exported and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/ashrunner.py -- [--size 512] [--no-review] [--preview]

  then: -P tools/blender/gf_assets/enemies/ashrunner_crowd.py   (the horde read, mixed with clinkers)

Content row (content/sheets/enemies.csv): ashrunner, Swarm, P0, hp 18, speed 5.2, radius 0.36, scale 1.0,
Swarmer(jitter 0.6), colour #F2A541, shape Hound, packs of 2-4 - "Fast ash-hounds that hunt in pairs."
Collider radius x scale = 0.36 m, so the body is about 0.8-1.1 m long (docs/art/ENEMIES.md section 2).

Design (docs/art/ENEMIES.md; the user's enemy pack):
  * verb SPRINT: a lean ash-grey hound of cinder and char, built like an arrow - a long, low skull held
    level with the spine, a deep keel chest, a tucked waist, small hips, long legs and a whip tail streaming
    straight back. Black char shards stream back off the neck like a wind-torn mane, and two long ear
    spikes sweep back over the withers. Every long line points backward: it reads as speed standing still;
  * the signature is the EMBER-LINED RIBCAGE: the hide has burnt away over the flanks, four black rib bars
    arc down each side over a glowing ember core. From the 55 deg camera: pale ash shoulders, a pale spine
    ridge and a pale rump frame a window of orange-lit dark ribs - "a grey streak with a burning chest";
  * THE UNMADE's wrong asymmetry, bold enough for 35 px: the ribcage is burnt open on the whole left flank,
    but a torn flap of ash hide still hangs over the rear ribs on the right; the right ear is snapped off
    short; the mane leans to the right;
  * faction glow: the Cinder Wastes Unmade burn molten (the Slag King's ramp) with the Unmade teal as the
    marker - the ribs and the tail tip glow ember (rim #C8400C, hot #FF6B1A, a warm #FFB070 core instead of
    the white-hot #FFF3D6, so no white speckle), the eye slits and the maw glow teal #2FBFA8. The bite
    telegraph is the clinker's language: the skull tips back and bares a teal maw;
  * value plan at game size: ash-grey top masses (lighter than the #3A2C24 floor), charcoal legs, jaw,
    keel and mane (darker than the floor, with light brush edges), the ember window and the tail tip as the
    one warm accent. The clinker is a dark dome with a pale club and teal; the ashrunner is a pale arrow
    with an orange chest: distinct at a glance, same faction.

Rig GF_Swarm_v1 (rigid). The gallop is a double-suspension bound with a FLEXING SPINE:
  body   = fore-chest, neck, ribcage, ember core, keel, spine ridge, lower jaw, mane, right hide flap
  head   = the skull + upper jaw, eyes and ears, hinged at the jaw joint: pitching it nose-up opens the
           mouth, and the lower jaw's teal floor faces the camera (the bite telegraph)
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
RIB_C = (0.405, 0.126, 0.142)             # ribcage ellipse: centre z, half-width, half-height
RIB_Y = (-0.125, -0.055, 0.015, 0.082)    # the four ribs (y at the spine)
RIB_W = 0.032                             # rib bar width (along the body)
# fore-chest + neck rings (y, cx, cz, w, h): high withers (the apex), wide shoulders, a thick neck
FORE_RINGS = [(-0.13, 0.0, 0.42, 0.21, 0.28), (-0.21, 0.0, 0.445, 0.25, 0.32), (-0.285, 0.0, 0.46, 0.2, 0.26),
              (-0.345, 0.0, 0.515, 0.14, 0.17), (-0.405, 0.0, 0.56, 0.1, 0.11)]

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


def arc_plate(stations, phis, thick, ridge=0.0, lift=None):
    """A thick plate draped over an ellipse: stations = [(y, cx, cz, a, b, offset)], phis = angles (deg,
    0 = top, + toward the creature's left). ridge raises the phi = 0 line; lift(u) adds z along the stations."""
    bm = bmesh.new()
    rings = []
    ns = len(stations)
    for si, (y, cx, cz, a, b, o) in enumerate(stations):
        dz = lift(si / max(1, ns - 1)) if lift else 0.0
        outer, inner = [], []
        for ph in phis:
            r = math.radians(ph)
            rr = 1.0 + (ridge if abs(ph) < 1e-3 else 0.0)
            outer.append((cx + math.sin(r) * (a + o), y, cz + dz + math.cos(r) * (b + o) * rr))
            inner.append((cx + math.sin(r) * (a + o - thick), y, cz + dz + math.cos(r) * (b + o - thick)))
        rings.append([bm.verts.new(p) for p in outer + inner[::-1]])
    n = len(rings[0])
    for a_, b_ in zip(rings[:-1], rings[1:]):
        for k in range(n):
            bm.faces.new((a_[k], a_[(k + 1) % n], b_[(k + 1) % n], b_[k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    return M.recalc(bm)


def shard(base, direction, length, r, flat=0.45, x_hint=(1, 0, 0), rot=45.0):
    """A flattened 4-sided spike from `base` along `direction` (its wide side follows x_hint)."""
    b = M.spike(r, length, sides=4, base_scale=(1.0, flat), rot_offset=rot)
    M.xform(b, matrix=M.orient(Vector(base), direction, x_hint))
    return b


def fore_top(y):
    """Top of the fore-chest / neck loft at y (linear between its rings)."""
    rs = sorted(FORE_RINGS)
    tops = [(r[0], r[2] + r[4] / 2) for r in rs]
    if y <= tops[0][0]:
        return tops[0][1]
    for (y0, z0), (y1, z1) in zip(tops[:-1], tops[1:]):
        if y0 <= y <= y1:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return tops[-1][1]


def ellipse_pt(phi_deg, y, cz, a, b, grow=0.0):
    r = math.radians(phi_deg)
    return Vector((math.sin(r) * (a + grow), y, cz + math.cos(r) * (b + grow)))


# ---- the model ------------------------------------------------------------------------------------------------

class Build:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.info = {}

    def torso(self, a):
        """Fore-chest + neck (one loft), the keel, the ribcage hoops over the ember core, a black spine bar, the
        torn right hide flap, and the loin + rump (tail bone). Down-facing faces are char, the rest ash hide."""
        def zone_down(f, lim=-0.42):
            return "char" if f.normal.z < lim else "hide"
        fore = loft(FORE_RINGS, BODY_PROFILE)
        M.noise_displace(fore, 0.005, freq=8.0, seed=SEED)
        for z, piece in split_by_faces(fore, zone_down).items():
            a.add(piece, z, bone="body", name="forechest_" + z, shading="auto", sharp_angle=28.0)
        cz, ra, rb = RIB_C
        # ember core: fills the ribcage, its top shows between the ribs from the game camera
        core = M.sphere(1.0, 8, 6)
        M.xform(core, loc=CORE, scale=(ra - 0.022, 0.16, rb - 0.022))
        a.add(core, "ember", bone="body", name="ember_core", shading="smooth")
        # keel (sternum): a char bar under the ribcage
        keel = loft([(-0.2, 0.0, 0.272, 0.05, 0.05), (-0.06, 0.0, 0.26, 0.05, 0.045), (0.1, 0.0, 0.3, 0.035, 0.035)],
                    [(0, 1), (1, 0.2), (0.5, -1), (-0.5, -1), (-1, 0.2)])
        a.add(keel, "char", bone="body", name="keel", shading="flat")
        # ribs: four black hoops from keel to keel over the top, sweeping back as they arc down; seen from the
        # 55 deg camera they cross the ember core like a grille ("ember-lined ribs")
        phis = (-156, -112, -68, -28, 0, 28, 68, 112, 156)
        self.rib_edges = []                             # the outer long edges of every rib (painted ember lines)
        for i, y0 in enumerate(RIB_Y):
            s = 1.0 - 0.08 * abs(i - 1.2)                # deepest at the second rib
            pts, rad = [], []
            for ph in phis:
                u = abs(ph) / 156.0
                p = ellipse_pt(ph, y0 + 0.045 * u * u, cz, ra * s, rb * s)
                pts.append(p)
                rad.append(Vector((p.x, 0.0, (p.z - cz) * (ra / rb) ** 2)).normalized())
            w, t = RIB_W, 0.022
            a.add(arc_band(pts, rad, w, t), "rib", bone="body", name="rib%d" % i, shading="flat")
            for sgn in (1, -1):
                line = []
                for k in range(len(pts)):
                    tg = (pts[min(len(pts) - 1, k + 1)] - pts[max(0, k - 1)]).normalized()
                    sd = tg.cross(rad[k]).normalized()
                    line.append(pts[k] + sd * sgn * w / 2 + rad[k] * t)
                self.rib_edges.append(line)
        # spine bar: the black backbone the ribs hang from
        sp = [ellipse_pt(0, y, cz, ra, rb, 0.012) for y in (-0.19, -0.05, 0.1)]
        a.add(M.tube(sp, [0.022, 0.02, 0.017], sides=5), "rib", bone="body", name="spine_bar", shading="flat")
        # the torn right-flank hide flap over the rear ribs (the Unmade asymmetry)
        st = [(-0.02, 0.0, cz, ra * 0.99, rb * 0.97, 0.03), (0.04, 0.0, cz, ra * 0.95, rb * 0.93, 0.032),
              (0.11, 0.0, cz + 0.005, ra * 0.84, rb * 0.86, 0.03)]
        flap = arc_plate(st, (-36, -64, -92, -120), 0.018)
        for v in flap.verts:                            # a torn lower edge
            if v.co.z < cz - 0.03:
                v.co.z += self.rng.uniform(-0.025, 0.025)
                v.co.y += self.rng.uniform(-0.012, 0.012)
        a.add(flap, "hide", bone="body", name="hide_flap_R", shading="flat")
        # loin + rump (tail bone): a narrow waist that swells into small hard haunches
        rump = loft([(0.07, 0.0, 0.47, 0.085, 0.095), (0.15, 0.0, 0.47, 0.098, 0.105), (0.235, 0.0, 0.462, 0.155, 0.145),
                     (0.33, 0.0, 0.462, 0.162, 0.15), (0.425, 0.0, 0.475, 0.088, 0.088)], BODY_PROFILE)
        M.noise_displace(rump, 0.004, freq=9.0, seed=SEED + 1)
        for z, piece in split_by_faces(rump, zone_down).items():
            a.add(piece, z, bone="tail", name="rump_" + z, shading="auto", sharp_angle=28.0)
        self.info["spine_top"] = cz + rb + 0.03

    def head(self, a):
        """Skull + upper jaw (head bone, hinged at JAW), lower jaw (body). Palate and jaw floor are teal maw.
        A jackal's head: a broad brow plane, a tapered snout, big raked-back triangular ears."""
        skull = loft([(-0.39, 0.0, 0.61, 0.12, 0.115), (-0.445, 0.0, 0.615, 0.15, 0.13), (-0.515, 0.0, 0.595, 0.105, 0.095),
                      (-0.588, 0.0, 0.574, 0.074, 0.07), (-0.655, 0.0, 0.558, 0.05, 0.048)], SKULL_PROFILE)

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
        jaw = loft([(-0.395, 0.0, 0.524, 0.09, 0.054), (-0.49, 0.0, 0.525, 0.075, 0.048),
                    (-0.565, 0.0, 0.524, 0.056, 0.037), (-0.632, 0.0, 0.526, 0.038, 0.027)], JAW_PROFILE)

        def jaw_zone(f):
            return "maw" if f.normal.z > 0.9 and f.calc_center_median().y < -0.43 else "char"
        for z, piece in split_by_faces(jaw, jaw_zone).items():
            a.add(piece, z, bone="body", name="jaw_" + z, shading="auto", sharp_angle=30.0)
        # fangs: upper canines over the jaw, lower canines up
        for sx in (1, -1):
            a.add(shard((sx * 0.029, -0.57, 0.55), (sx * 0.1, -0.15, -1.0), 0.038, 0.009, flat=0.8), "bone",
                  bone="head", name="fang_up", shading="flat")
            a.add(shard((sx * 0.022, -0.61, 0.522), (sx * 0.15, -0.2, 1.0), 0.026, 0.007, flat=0.8), "bone",
                  bone="body", name="fang_lo", shading="flat")
        # teal eye slits on the brow (they show the facing from above)
        for sx in (1, -1):
            e = M.sphere(1.0, 6, 3)
            M.xform(e, scale=(0.009, 0.024, 0.007))
            M.xform(e, rot=(14, 0, sx * -26))
            M.xform(e, loc=(sx * 0.047, -0.505, 0.633))
            a.add(e, "eye", bone="head", name="eye", shading="smooth")
        # ears: big black jackal ears, raked back and splayed out so they break the outline from the game camera; the
        # right one is torn off halfway
        for sx, ln in ((1, 0.21), (-1, 0.115)):
            base = Vector((sx * 0.05, -0.43, 0.662))
            d = Vector((sx * 0.5, 0.62, 0.9)).normalized()
            b = shard(base, d, ln, 0.05, flat=0.55, x_hint=(sx * 0.7, -0.7, 0.0), rot=0.0)
            if ln < 0.15:                               # the torn ear: a notched, blunt tip
                tip = max(b.verts, key=lambda v: (v.co - base).length)
                tip.co = base + d * ln + Vector((sx * 0.012, 0.0, 0.01))
            a.add(b, "char", bone="head", name="ear_" + ("L" if sx > 0 else "R"), shading="flat")
        self.info["mouth"] = Vector((0.0, -0.55, 0.54))
        self.info["head_top"] = 0.75

    def mane(self, a):
        """Char shards streaming back off the neck and withers (a wind-torn cinder mane), leaning right."""
        stations = [(-0.37, 0.0, 0.13, 0.026), (-0.315, -0.022, 0.19, 0.032), (-0.255, 0.016, 0.23, 0.036),
                    (-0.19, -0.028, 0.2, 0.034), (-0.13, 0.006, 0.13, 0.026)]
        for y, x, ln, r in stations:
            z = fore_top(y)
            d = Vector((x * 4.0 - 0.18, 1.0, 0.62)).normalized()
            a.add(shard((x, y, z - 0.03), d, ln, r, flat=0.4, x_hint=(0, 0, 1), rot=self.rng.uniform(30, 60)), "char",
                  bone="body", name="mane", shading="flat")

    def legs(self, a):
        """Front legs (legs_a) nearly straight under the shoulders; hind legs (legs_b) in the hound's Z.
        Upper legs are ash hide, lower legs and paws char."""
        self.feet = {}
        for sx in (1, -1):
            sh = Vector((sx * 0.09, -0.205, 0.46))
            el = Vector((sx * 0.088, -0.155, 0.285))
            wr = Vector((sx * 0.083, -0.19, 0.085))
            pw = Vector((sx * 0.083, -0.228, 0.03))
            a.add(M.tube([sh, el], [0.052, 0.034], sides=6), "hide", bone="legs_a", name="upperarm", shading="auto")
            a.add(M.tube([el + Vector((0, 0.004, 0.02)), wr, pw], [0.034, 0.024, 0.019], sides=5), "char", bone="legs_a",
                  name="forearm", shading="auto", sharp_angle=40.0)
            paw = M.sphere(1.0, 5, 3)
            M.xform(paw, loc=(pw.x, pw.y - 0.018, 0.02), scale=(0.028, 0.045, 0.02))
            a.add(paw, "char", bone="legs_a", name="paw_f", shading="flat")
            self.feet["F" + ("L" if sx > 0 else "R")] = pw
            hp = Vector((sx * 0.082, 0.3, 0.45))
            st = Vector((sx * 0.09, 0.215, 0.27))
            hk = Vector((sx * 0.085, 0.37, 0.13))
            pw = Vector((sx * 0.085, 0.345, 0.03))
            a.add(M.tube([hp, st], [0.066, 0.038], sides=6), "hide", bone="legs_b", name="thigh", shading="auto")
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
            "rib": P.zone(base=RIB_BASE, shadow="#100909", light=RIB_LIGHT, planes=0.12, parts=0.08, brush=0.05,
                          edge=1.0, edge_width=0.008, edge_breakup=0.25, cavity=0.5, ao=0.3),
            "ember": P.faction_zone("unmade", "molten", glow=True,
                                    emit=dict(EMBER, mode="radial", center=tuple(CORE), radius=0.16, base_mix=0.25)),
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
#   * EMBER-LINED RIBS: both outer long edges of every rib carry a broken, glowing ember stroke (the brief's
#     signature), measured to the rib's own edge lines, so no glow runs across a rib at its segment joints.
BURN_Z = 0.35


def _polyline_samples(lines, spacing=0.002):
    out = []
    for ln in lines:
        for a_, b_ in zip(ln[:-1], ln[1:]):
            n = max(1, int((b_ - a_).length / spacing))
            out.extend(a_.lerp(b_, (i + 0.5) / n) for i in range(n))
    return out


def extra_passes(maps, zones_order, base, emis, rib_edges, seed=0):
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
    if "rib" in zones_order and rib_edges:
        m = Z == zones_order.index("rib")
        p = pos[m]
        d = P._kd_dist(_polyline_samples(rib_edges), p, 0.03)
        dabs = P.spread01(P.fbm(p, 12.0, 2, seed=seed + 503))
        k = P.smoothstep(0.0062, 0.0026, d) * P.smoothstep(0.2, 0.36, dabs)
        base[m] = P.mix(base[m], P.hex3(EMBER["hot"]), k * 0.5)
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
def painter_passes(rib_edges):
    """Within the block, gfa_paint.paint also runs extra_passes() (between the zones and the decals)."""
    import numpy as np
    orig = P.paint

    def paint(maps, zones_order, recipes_, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes_, dist_convex, dist_concave, (), seed)
        base, emis = extra_passes(maps, zones_order, base, emis, rib_edges, seed)
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
    for yaw, tag in ((-35.0, "face"), (145.0, "away"), (90.0, "side")):
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
    stumble = F({"root": {"loc": (0, -0.12, 0.12)}, "body": {"rot": (22, 0, 26)}, "head": {"rot": (-12, 10, 0)},
                 "legs_a": {"rot": (38, 0, -8)}, "legs_b": {"rot": (-12, 0, 6)}, "tail": {"rot": (-10, 0, 0)}})
    side = F({"root": {"loc": (0, -0.265, 0.15)}, "body": {"rot": (6, 0, 84)}, "head": {"rot": (-14, 0, -18)},
              "legs_a": {"rot": (-28, 0, 16)}, "legs_b": {"rot": (22, 0, 12)}, "tail": {"rot": (4, 12, 0)}})
    crumble = F({"root": {"loc": (0, -0.3, 0.15)}, "body": {"rot": (6, 0, 88), "scale": 0.6},
                 "head": {"rot": (-10, 0, -22), "scale": 0.6}, "legs_a": {"rot": (-30, 0, 18), "scale": 0.45},
                 "legs_b": {"rot": (24, 0, 14), "scale": 0.45}, "tail": {"rot": (4, 14, 0), "scale": 0.55}})
    gone = F({"root": {"loc": (0, -0.34, 0.15)}, "body": {"rot": (6, 0, 88), "scale": 0.02},
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
    layout = {"title": "Ashrunner - ember-lined ribs, teal maw", "subtitle": "gallop (extended suspension) | wind-up "
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
                             ("running away, gallop f7", 150.0, 7)):
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
        "subtitle": "Swarm Hound | The Unmade | Cinder Wastes | verb SPRINT | GF_Swarm_v1 | ember-lined ribs, teal maw",
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
    with painter_passes(b.rib_edges):
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
