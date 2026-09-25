"""Clinker - E1 SHARDLING (The Unmade), the Cinder Wastes swarm crawler: one base look + three shell
variants, each built, painted, rigged on GF_Swarm_v1, animated, exported and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/clinker.py -- --variant base|v1|v2|v3 [--size 512] [--no-review]

  then (after all four): -P tools/blender/gf_assets/enemies/clinker_crowd.py   (family lineup, 40-copy crowd)

Content row (content/sheets/enemies.csv): clinker, Swarm, P0, hp 9, speed 3.8, radius 0.26, scale 0.8,
Swarmer(jitter 1.0), colour #9A5B3C, shape Crawler, packs of 6-10 - "Skittering slag. There are always more."
Collider radius x scale = 0.21 m, so the body footprint is ~0.45-0.6 m (docs/art/ENEMIES.md section 3).

Design (docs/art/ENEMIES.md section 7, E1; the user's enemy pack):
  * verb SKITTER: a hunched, eyeless infant figure fused into a cracked obsidian carapace. The big bowed
    skull hangs low in front; the back is three overlapping obsidian scutes with teal ichor glowing
    through the gaps; the limbs are WRONG: three thin shard legs on one side, one huge clawed arm on the
    other. The skull is split vertically: one half is a jaw that swings open sideways on a hinge (the
    `head` bone), showing a glowing teal maw - that wedge of light is the wind-up read at 35 px;
  * value plan at game size: dark obsidian mass (reads against the #3A2C24 Cinder floor through the
    engine ink + rim), teal slits on the back and the face, pale bone belly / knees / claws;
  * palette: THE UNMADE only (gfa_spec.FACTIONS): obsidian, wet obsidian, ichor teal #2FBFA8 with a
    #B8FFE8 hot core, bone. The row colour #9A5B3C is only a faint warm tint in the shell's light plane.

Variants (the enemy pack's "3 shell variants per base" rule, applied inside the clinker key). Each is
its OWN file with the same skeleton, sockets and clip suffixes, so the client can pick one per spawn
(docs: art/enemies/clinker/README.md):
  base -> clinker.glb      "Shardling"    3 scutes, a few back shards, 3 legs on the LEFT
  v1   -> clinker_v1.glb   "Crested"      tall shard crest along the spine, long thin legs, mirrored
  v2   -> clinker_v2.glb   "Brood-back"   squat and broad, four scutes, big skull and claw, heavy limp
  v3   -> clinker_v3.glb   "Split-back"   scutes split along the spine over a glowing rift, jittery, mirrored

Rig GF_Swarm_v1 (rigid): body = hull, belly, right skull half, maw, drips; head = the hinged jaw half
(+ its teeth); tail = the scutes and shards (they rattle, they blow off in the death); legs_a = front
and rear leg of the three-leg side; legs_b = middle leg + the big arm (so the lone arm limps with the
middle leg). Mirrored variants are built canonically and mirrored after painting (mesh, pivots, poses).

Toolkit: tools/blender/gf_assets (gfa_model / gfa_paint / gfa_rig / gfa_export / gfa_render). Clip
vocabulary adapted from Ashen Covenant tools/blender/ac_crawler_rig.py (crawler pose set) and
e05_animations.py (keyed one-shots, seamless loops), via gfa_rig.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

CONTENT_KEY = "clinker"
KIND, TIER = "enemy", "swarm"
FPS = 30
ROW = {"key": "clinker", "class": "Swarm", "biome": "cinder_wastes", "hp": 9, "speed": 3.8, "radius": 0.26,
       "scale": 0.8, "behavior": "Swarmer(jitter: 1.0)", "color": "#9A5B3C", "shape": "Crawler", "pack": "(6, 10)"}
ZONES = ["hull", "plate", "limb", "skull", "bone", "core", "maw", "ichor"]

# ---- the variant table -------------------------------------------------------------------------------------
# plates (scutes): (y0, y1, front offset, rear offset, rear lift, roll deg) - the offset is how far the scute
# stands off the hull (front edge tucked, rear edge flared and lifted = overlapping scales with glowing slits).
# shards: (plate, u along the plate 0..1, s along the arc -1 right flank .. 0 top .. +1 left flank, length,
# lean back deg, base radius). legs: spread (x), reach (y), knee (z), thickness. motion: gait / idle tempo.
VARIANTS = {
    "base": dict(
        key="clinker", name="Shardling", mirror=False, seed=11,
        hull_len=1.0, hull_w=1.0, hull_h=1.0, lean=0.12,
        plates=[(-0.170, -0.045, 0.010, 0.030, 0.012, 0.0), (-0.030, 0.115, 0.012, 0.034, 0.020, -3.0),
                (0.145, 0.290, 0.012, 0.030, 0.022, 4.0)],
        split=0.0, plate_t=0.030, ridge=0.22,
        shards=[(1, 0.70, 0.22, 0.12, 40, 0.030), (1, 0.80, -0.32, 0.10, 45, 0.026), (2, 0.60, 0.12, 0.10, 50, 0.028),
                (2, 0.75, -0.22, 0.07, 55, 0.022), (0, 0.75, 0.55, 0.065, 30, 0.020)],
        head=1.0, head_bow=26.0,
        legs=dict(spread=1.0, reach=1.0, knee=1.0, thick=1.0), arm=1.0,
        cracks="web",
        motion=dict(move_frames=10, stride=0.065, lift=0.045, roll=7.0, wag=5.0, chatter=5.0, charge=8.0,
                    idle_frames=48, jaw_idle=4.0, move_cycle_m=0.6),
    ),
    "v1": dict(
        key="clinker_v1", name="Crested", mirror=True, seed=23,
        hull_len=1.04, hull_w=0.9, hull_h=1.0, lean=0.10,
        plates=[(-0.170, -0.050, 0.010, 0.030, 0.018, 3.0), (-0.035, 0.110, 0.012, 0.034, 0.026, -3.0),
                (0.125, 0.290, 0.012, 0.032, 0.030, 4.0)],
        split=0.0, plate_t=0.030, ridge=0.45,
        shards=[(0, 0.60, 0.02, 0.12, 28, 0.026), (1, 0.30, -0.03, 0.17, 25, 0.032), (1, 0.75, 0.03, 0.21, 32, 0.034),
                (2, 0.35, -0.02, 0.17, 38, 0.030), (2, 0.80, 0.02, 0.12, 48, 0.024), (1, 0.55, 0.45, 0.08, 30, 0.018)],
        head=0.92, head_bow=30.0,
        legs=dict(spread=1.12, reach=1.1, knee=1.15, thick=0.85), arm=0.95,
        cracks="spine",
        motion=dict(move_frames=10, stride=0.07, lift=0.05, roll=5.0, wag=4.0, chatter=4.0, charge=6.0,
                    idle_frames=54, jaw_idle=3.0, move_cycle_m=0.65),
    ),
    "v2": dict(
        key="clinker_v2", name="Brood-back", mirror=False, seed=37,
        hull_len=0.98, hull_w=1.16, hull_h=0.86, lean=0.16,
        plates=[(-0.165, -0.080, 0.010, 0.026, 0.010, -2.0), (-0.065, 0.035, 0.012, 0.030, 0.014, 3.0),
                (0.050, 0.155, 0.012, 0.030, 0.016, -3.0), (0.170, 0.285, 0.012, 0.028, 0.018, 4.0)],
        split=0.0, plate_t=0.032, ridge=0.14,
        shards=[(1, 0.60, 0.35, 0.06, 40, 0.026), (2, 0.60, -0.30, 0.065, 44, 0.026), (3, 0.60, 0.10, 0.055, 50, 0.024)],
        head=1.12, head_bow=22.0,
        legs=dict(spread=0.95, reach=0.9, knee=0.82, thick=1.22), arm=1.15,
        cracks="star",
        motion=dict(move_frames=12, stride=0.055, lift=0.035, roll=10.0, wag=3.0, chatter=6.0, charge=10.0,
                    idle_frames=42, jaw_idle=5.0, move_cycle_m=0.55),
    ),
    "v3": dict(
        key="clinker_v3", name="Split-back", mirror=True, seed=53,
        hull_len=1.06, hull_w=0.94, hull_h=0.97, lean=0.10,
        plates=[(-0.175, -0.040, 0.012, 0.030, 0.020, 0.0), (-0.025, 0.120, 0.012, 0.034, 0.030, 0.0),
                (0.135, 0.295, 0.012, 0.030, 0.036, 0.0)],
        split=0.06, plate_t=0.030, ridge=0.35,
        shards=[(0, 0.60, 0.12, 0.07, 30, 0.020), (0, 0.60, -0.12, 0.06, 30, 0.020), (1, 0.50, 0.14, 0.10, 34, 0.024),
                (1, 0.62, -0.14, 0.09, 36, 0.024), (2, 0.50, 0.14, 0.08, 44, 0.022), (2, 0.60, -0.14, 0.085, 44, 0.022)],
        head=1.0, head_bow=26.0,
        legs=dict(spread=1.1, reach=1.1, knee=1.12, thick=0.9), arm=1.0,
        cracks="rift",
        motion=dict(move_frames=9, stride=0.065, lift=0.05, roll=6.0, wag=7.0, chatter=8.0, charge=7.0,
                    idle_frames=40, jaw_idle=6.0, move_cycle_m=0.6),
    ),
}

# canonical hull (base proportions): rings (y, cx, cz, w, h), profile = unit cross-section (x, z). A round,
# hunched infant back: shoulders low behind the skull, the peak over the rump, a pale belly underneath.
HULL_RINGS = [(-0.220, 0.00, 0.215, 0.17, 0.17), (-0.140, 0.00, 0.245, 0.31, 0.27),
              (-0.030, 0.01, 0.265, 0.39, 0.32), (0.090, 0.01, 0.275, 0.41, 0.34),
              (0.200, 0.00, 0.255, 0.35, 0.29), (0.280, 0.00, 0.225, 0.22, 0.20)]
HULL_POLE = (0.0, 0.320, 0.200)
HULL_PROFILE = [(0.0, 1.0), (0.6, 0.84), (0.95, 0.38), (1.0, -0.12), (0.74, -0.7), (0.0, -0.92),
                (-0.74, -0.7), (-1.0, -0.12), (-0.95, 0.38), (-0.6, 0.84)]
# the scutes follow the upper hull arc (from the left flank over the top to the right flank)
ARC = [(1.0, 0.1), (0.95, 0.42), (0.6, 0.84), (0.0, 1.0), (-0.6, 0.84), (-0.95, 0.42), (-1.0, 0.1)]
# UV importance (linear texel scale per zone before packing): what the 55 deg camera sees gets the pixels
UV_WEIGHT = {"plate": 1.35, "skull": 1.3, "hull": 1.05, "limb": 0.95, "bone": 0.85, "core": 0.75, "maw": 0.85,
             "ichor": 0.6}
Y_C = 0.02                 # body centre (y)
JAW_GAP = 0.010            # gap between the skull halves at the hinge
PLATE_STANDOFF = 0.012     # added to every scute offset (the hull noise is +-8 mm)
JAW_V = 4.5                # degrees each half's inner face opens toward the front (the resting glow wedge)

PALETTE = [("obsidian", "#1A1720"), ("obsidian light", "#5B4A52"), ("wet sheen", "#7FA7A0"), ("bone", "#BDB09A"),
           ("ichor", "#1F8F7E"), ("glow", "#2FBFA8"), ("hot core", "#B8FFE8"), ("row tint", "#9A5B3C")]


def mix_hex(a, b, t):
    ca, cb = C.hex_rgb(a), C.hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ca, cb))


LIGHT_WARM = mix_hex("#4B4658", ROW["color"], 0.28)     # obsidian light plane, faintly warmed by the row colour
SPILL = "#123C38"                                         # teal glow spill painted into the obsidian


# ---- small geometry helpers -----------------------------------------------------------------------------------

def loft(rings, profile, pole_back=None, cap_front=True):
    """Closed hull through rings (y, cx, cz, w, h) of a unit profile [(x, z)], front cap flat, back to a pole."""
    bm = bmesh.new()
    rv = [[bm.verts.new((cx + px * w / 2, y, cz + pz * h / 2)) for px, pz in profile] for y, cx, cz, w, h in rings]
    n = len(profile)
    for a, b in zip(rv[:-1], rv[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    if cap_front:
        bm.faces.new(rv[0])
    if pole_back is not None:
        pv = bm.verts.new(pole_back)
        for k in range(n):
            bm.faces.new((rv[-1][k], rv[-1][(k + 1) % n], pv))
    else:
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


def arc_point(s, arc=None):
    """Unit (px, pz) on the scute arc at s in [-1 (right flank) .. 0 (top) .. +1 (left flank)]."""
    arc = arc or ARC
    f = (1.0 - s) / 2.0 * (len(arc) - 1)
    i = min(len(arc) - 2, int(f))
    t = f - i
    return tuple(arc[i][k] * (1 - t) + arc[i + 1][k] * t for k in range(2))


def scute(hull_at, y0, y1, o0, o1, t, lift, ridge, arc, xshift=0.0, rng=None, jag=0.0):
    """A thick scute hugging the hull: the unit arc `arc` at three rings (y0, mid, y1), standing off the hull
    by o0 at the front (tucked) to o1 at the rear (flared), `t` thick, the rear edge lifted by `lift`; `ridge`
    raises the top point (keel / rift lip); `jag` breaks the flared rear edge (random y / z nicks, metres).
    hull_at(y) -> (cx, cz, w, h)."""
    bm = bmesh.new()
    rings = []
    for u in (0.0, 0.5, 1.0):
        y = y0 + (y1 - y0) * u
        cx, cz, w, h = hull_at(y)
        o = o0 + (o1 - o0) * u
        dz = lift * u * u
        outer, inner = [], []
        for px, pz in arc:
            rr = 1.0 + (ridge if abs(px) < 1e-3 else 0.0)
            jy = jz = 0.0
            if rng is not None and jag > 0 and u > 0.99:
                jy, jz = rng.uniform(-jag, jag * 0.4), rng.uniform(-0.4 * jag, 0.4 * jag)
            outer.append((cx + xshift + px * (w / 2 + o), y + jy, cz + dz + jz + pz * (h / 2 + o) * rr))
            inner.append((cx + xshift + px * (w / 2 + o - t), y + jy, cz + dz + jz + pz * (h / 2 + o - t)))
        rings.append([bm.verts.new(p) for p in outer + inner[::-1]])
    n = len(rings[0])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]))
    bm.faces.new(rings[0])
    bm.faces.new(rings[-1][::-1])
    return M.recalc(bm)


def knob(r, loc, rot=(0, 0, 45)):
    """Faceted bone knuckle (a 4 x 3 sphere: 16 tris)."""
    b = M.sphere(r, 4, 3)
    M.xform(b, loc=loc, rot=rot)
    return b


def shard(loc, direction, length, r, rng, flat=0.55):
    flat = min(1.0, flat + max(0.0, length - 0.1) * 2.5)     # tall crest crystals stay chunky, not paper blades
    b = M.spike(r, length, sides=4, base_scale=(1.0, flat), rot_offset=rng.uniform(0, 90))
    xh = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0.2))
    M.xform(b, matrix=M.orient(loc, direction, xh))
    return b


# ---- the model ----------------------------------------------------------------------------------------------

class Build:
    """Everything one variant's geometry decides: the mesh, pivots, sockets, paint anchors and decals
    (canonical frame: three limbs on +X; mirrored variants are flipped after painting)."""

    def __init__(self, vk):
        self.vk = vk
        self.V = VARIANTS[vk]
        self.rng = random.Random(self.V["seed"])
        V = self.V
        L, W, H = V["hull_len"], V["hull_w"], V["hull_h"]
        self.rings = [(Y_C + (y - Y_C) * L, cx * W, cz * H + (1 - H) * 0.02, w * W, h * H) for y, cx, cz, w, h in HULL_RINGS]
        self.pole = (0.0, Y_C + (HULL_POLE[1] - Y_C) * L, HULL_POLE[2] * H)
        self.info = {}

    def hull_at(self, y):
        rs = self.rings
        if y <= rs[0][0]:
            return rs[0][1:]
        for a, b in zip(rs[:-1], rs[1:]):
            if a[0] <= y <= b[0]:
                t = (y - a[0]) / (b[0] - a[0])
                return tuple(a[i] * (1 - t) + b[i] * t for i in range(1, 5))
        return rs[-1][1:]

    # -- parts --
    def hull(self, a):
        V = self.V
        bm = loft(self.rings, HULL_PROFILE, pole_back=self.pole)
        for v in bm.verts:
            v.co.z += V["lean"] * v.co.x                      # the lone-arm side sags
            if v.co.x < 0 and v.co.y > 0.1:                   # ... and its rear drags
                v.co.z -= 0.03 * min(1.0, (v.co.y - 0.1) / 0.15) * min(1.0, -v.co.x / 0.15)
        M.noise_displace(bm, 0.008, freq=7.0, seed=V["seed"])
        top = max(v.co.z for v in bm.verts)
        self.hull_top = top

        def key(f):
            n = f.normal
            if n.z < -0.55:
                return "bone"
            if n.z > 0.7 and f.calc_center_median().z > top - 0.075:
                return "core"
            return "hull"
        for z, piece in split_by_faces(bm, key).items():
            a.add(piece, z, bone="body", name="hull_" + z, shading="flat")
        self.core_pt = (0.0, Y_C + 0.05, top - 0.01)

    def plates(self, a):
        """Overlapping scutes that hug the hull (tail bone: they rattle and blow off in the death), with
        obsidian crystals erupting from their ridges."""
        V, rng = self.V, self.rng
        L = V["hull_len"]
        self.plate_geo = []
        sp = V["split"]
        halves = [(0.0, ARC)] if sp <= 0 else [(sp / 2, [p for p in ARC if p[0] >= 0]),
                                               (-sp / 2, [p for p in ARC if p[0] <= 0])]
        for i, (y0, y1, o0, o1, lift, roll) in enumerate(V["plates"]):
            y0, y1 = Y_C + (y0 - Y_C) * L, Y_C + (y1 - Y_C) * L
            o0, o1 = o0 + PLATE_STANDOFF, o1 + PLATE_STANDOFF      # clear of the hull's noise: no poke-through
            cx, cz, w, h = self.hull_at((y0 + y1) / 2)
            geo = dict(y0=y0, y1=y1, o0=o0, o1=o1, lift=lift, roll=roll)
            self.plate_geo.append(geo)
            piv = Vector((cx, (y0 + y1) / 2, cz))
            rot = Matrix.Translation(piv) @ Matrix.Rotation(math.radians(roll), 4, "Y") @ Matrix.Translation(-piv)
            geo["matrix"] = rot
            for k, (xs, arc) in enumerate(halves):
                b = scute(self.hull_at, y0, y1, o0, o1, V["plate_t"], lift, V["ridge"], arc, xshift=xs, rng=rng, jag=0.016)
                M.xform(b, matrix=rot)
                a.add(b, "plate", bone="tail", name="scute%d%s" % (i, "" if sp <= 0 else "LR"[k]), shading="flat")
        top = 0.0
        for pi, u, s, length, back, r in V["shards"]:
            g = self.plate_geo[pi]
            y = g["y0"] + (g["y1"] - g["y0"]) * u
            cx, cz, w, h = self.hull_at(y)
            o = g["o0"] + (g["o1"] - g["o0"]) * u
            px, pz = arc_point(s)
            xs = 0.0 if sp <= 0 else math.copysign(sp / 2, s if s else 1)
            rr = 1.0 + V["ridge"] * max(0.0, 1.0 - abs(s) / 0.3)
            base = Vector((cx + xs + px * (w / 2 + o) * 0.97, y, cz + g["lift"] * u * u + pz * (h / 2 + o) * rr * 0.97))
            base = g["matrix"] @ base
            radial = Vector((px, 0.0, pz)).normalized()
            bk = math.radians(back)
            d = Vector((radial.x * math.cos(bk), math.sin(bk), radial.z * math.cos(bk))).normalized()
            a.add(shard(base - d * 0.012, d, length, r, self.rng), "plate", bone="tail", name="shard", shading="flat")
            top = max(top, (base + d * length).z)
        self.shard_top = top

    def head(self, a):
        """The bowed infant skull: a wide cranium, a flat eyeless face of pale bone and a small chin, split
        down the face. Three closed pieces, no overlap: the hinged front-left jaw (head bone), the front-right
        half and the back of the skull (body). Every cut face is glowing maw: it shows when the jaw opens."""
        V = self.V
        hs = V["head"]
        yf = self.rings[0][0]
        neck_cz = self.rings[0][2]
        hinge_y = yf - 0.012                          # just in front of the hull's front cap
        hy, hz = hinge_y - 0.055 * hs, neck_cz - 0.03
        rx, ry, rz = 0.13 * hs, 0.135 * hs, 0.125 * hs
        bm = M.sphere(1.0, 8, 6)
        M.xform(bm, rot=(0, 0, 22.5))                 # two vertex columns flank the face centre line
        for v in bm.verts:
            x, y, z = v.co
            if z > 0:
                x *= 1.0 + 0.14 * z                   # wide infant cranium
                if y > 0:
                    y *= 1.06
                    z *= 1.05
            else:
                x *= 1.0 - 0.3 * (-z)                 # small chin
            if y < -0.7:
                y = -0.7 + (y + 0.7) * 0.3            # flat, eyeless face
            if y > 0:
                y *= 0.85                             # the back of the skull sinks into the neck
            v.co = Vector((x * rx, y * ry, z * rz))
        bow = math.radians(V["head_bow"])
        M.xform(bm, rot=(V["head_bow"], 0, 0))
        M.xform(bm, loc=(0, hy, hz))
        M.noise_displace(bm, 0.005, freq=10.0, seed=V["seed"] + 3)
        face_n = Vector((0.0, -math.cos(bow), -math.sin(bow)))
        tv = math.tan(math.radians(JAW_V))
        self.head_c = (0.0, hy, hz)
        self.hinge = (JAW_GAP / 2, hinge_y, hz)
        self.mouth_pt = (0.0, hy - ry * 0.6, hz - 0.03)
        self.head_front = hy - ry * 0.8
        back_plane = (Vector((0.0, 1.0, 0.0)), Vector((0.0, hinge_y, hz)))
        front_plane = (Vector((0.0, -1.0, 0.0)), Vector((0.0, hinge_y, hz)))
        pieces = [("L", "head", [(Vector((1.0, tv, 0.0)).normalized(), Vector((JAW_GAP / 2, hinge_y, hz))), front_plane]),
                  ("R", "body", [(Vector((-1.0, tv, 0.0)).normalized(), Vector((-JAW_GAP / 2, hinge_y, hz))), front_plane]),
                  ("B", "body", [back_plane])]
        for tag, bone, planes in pieces:
            b = bm.copy()
            for n, co in planes:
                res = bmesh.ops.bisect_plane(b, geom=b.verts[:] + b.edges[:] + b.faces[:], dist=1e-6, plane_co=co,
                                             plane_no=n, clear_inner=True)
                cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
                try:
                    bmesh.ops.edgeloop_fill(b, edges=cut)
                except Exception:  # noqa: BLE001
                    bmesh.ops.holes_fill(b, edges=b.edges[:], sides=0)
                M.recalc(b)

            def zone_of(f, planes=planes):
                if any(all(abs((v.co - co).dot(n)) < 2e-4 for v in f.verts) for n, co in planes):
                    return "maw"
                if f.normal.dot(face_n) > 0.72 and f.calc_center_median().y < hy - 0.45 * ry:
                    return "bone"
                return "skull"
            if tag in "LR":
                # teeth along the front edge of the split (pointing into the gap)
                sx = 1 if tag == "L" else -1
                n0, co0 = planes[0]
                cap = sorted({v.co.copy().freeze() for f in b.faces for v in f.verts
                              if abs((v.co - co0).dot(n0)) < 2e-4}, key=lambda p: p.y)
                front = sorted(cap[:max(3, len(cap) // 2)], key=lambda p: p.z)
                picks = [front[min(len(front) - 1, int(i * (len(front) - 1) / 3.0 + 0.5))] for i in (0.6, 1.5, 2.4)] \
                    if len(front) >= 3 else []
                for k, p in enumerate(picks):
                    d = Vector((-sx, -0.35, 0.05 * (k - 1))).normalized()
                    t = M.spike(0.0085 * hs, 0.026 * hs, sides=3)
                    M.xform(t, matrix=M.orient(Vector(p) - d * 0.004 + Vector((0, 0.004, 0)), d))
                    a.add(t, "bone", bone=bone, name="tooth", shading="flat")
            for z, piece in split_by_faces(b, zone_of).items():
                a.add(piece, z, bone=bone, name="skull_%s_%s" % (tag, z), shading="auto", sharp_angle=30.0)
        bm.free()
        # the glowing slab between the halves (seen through the resting wedge, fully when the jaw opens)
        slab = M.box((0.010, 0.12 * hs, 0.15 * hs), bevel=0.003)
        M.xform(slab, rot=(V["head_bow"], 0, 0))
        M.xform(slab, loc=(0, hy - 0.03 * hs, hz - 0.01))
        a.add(slab, "maw", bone="body", name="maw_slab", shading="flat")

    def legs(self, a):
        """Three bent shard legs on the left (thick femur, pale knuckle, a spur) and ONE huge clawed arm on
        the right - the wrong asymmetry that makes the silhouette."""
        V, rng = self.V, self.rng
        lg = V["legs"]
        sp, re, kn, th = lg["spread"], lg["reach"], lg["knee"], lg["thick"]
        base_legs = {
            "L1": [(0.14, -0.13, 0.22), (0.27, -0.21, 0.30), (0.33, -0.30, 0.10), (0.345, -0.345, 0.0)],
            "L2": [(0.17, 0.02, 0.22), (0.32, 0.01, 0.31), (0.39, 0.04, 0.10), (0.405, 0.06, 0.0)],
            "L3": [(0.14, 0.17, 0.21), (0.28, 0.25, 0.29), (0.34, 0.34, 0.09), (0.355, 0.385, 0.0)],
        }
        groups = {"L1": "legs_a", "L2": "legs_b", "L3": "legs_a"}
        W = V["hull_w"]
        self.feet = {}
        for name, pts in base_legs.items():
            hip = Vector(pts[0])
            hip.x *= W
            out = [hip]
            for p in pts[1:]:
                out.append(Vector((hip.x + (p[0] - pts[0][0]) * sp, hip.y + (p[1] - pts[0][1]) * re, p[2] * kn)))
            out[-1].z = 0.0
            radii = [0.044 * th, 0.038 * th, 0.024 * th, 0.0]
            a.add(M.tube(out, radii, sides=5), "limb", bone=groups[name], name="leg_" + name, shading="flat")
            a.add(knob(0.032 * th, out[1]), "bone", bone=groups[name], name="knee_" + name, shading="flat")
            d = Vector((0.45, 0.5, 1.0)).normalized()
            a.add(shard(out[1] + d * 0.014, d, 0.07 * th + 0.01, 0.018 * th, rng, flat=0.7), "limb", bone=groups[name],
                  name="spur_" + name, shading="flat")
            self.feet[name] = out[-1]
        # the one huge arm on the other side (legs_b: it limps with the middle leg)
        s = V["arm"]
        sh = Vector((-0.13 * W, -0.12, 0.24))
        rel = [(0, 0, 0), (-0.16, 0.06, -0.01), (-0.155, -0.15, -0.165), (-0.135, -0.21, -0.19)]
        pts = [sh + Vector(r) * s for r in rel]
        pts[-1].z = max(0.045, pts[-1].z)
        radii = [0.07 * s, 0.062 * s, 0.05 * s, 0.045 * s]
        a.add(M.tube(pts, radii, sides=6), "limb", bone="legs_b", name="arm_R", shading="flat")
        a.add(knob(0.05 * s, pts[1]), "bone", bone="legs_b", name="elbow_R", shading="flat")
        d = Vector((-0.5, 0.6, 0.6)).normalized()
        a.add(shard(pts[1] + d * 0.03, d, 0.1 * s, 0.024 * s, rng), "limb", bone="legs_b", name="elbow_spike", shading="flat")
        hand_c = pts[-1] + Vector((0.004, -0.03, 0.0)) * s
        hand = M.sphere(1.0, 6, 4)
        M.xform(hand, loc=hand_c, scale=(0.078 * s, 0.072 * s, 0.05 * s))
        a.add(hand, "limb", bone="legs_b", name="hand_R", shading="flat")
        for k, dx in enumerate((-0.045, 0.0, 0.045)):
            c0 = hand_c + Vector((dx * s, -0.05 * s, 0.01))
            c1 = c0 + Vector((dx * 0.4 * s, -0.05 * s, 0.0))
            c2 = c1 + Vector((dx * 0.2 * s, -0.035 * s, -c1.z + 0.003))
            a.add(M.tube([c0, c1, c2], [0.02 * s, 0.013 * s, 0.0], sides=4), "bone", bone="legs_b", name="claw%d" % k,
                  shading="flat")
        self.feet["R1"] = hand_c

    def drips(self, a):
        rng = self.rng
        for (y, sx) in ((-0.06, 1), (0.16, 1), (0.05, -1)):
            cx, cz, w, h = self.hull_at(y)
            p = Vector((cx + sx * w / 2 * 0.93, y, cz - 0.02 + self.V["lean"] * sx * w / 2 * 0.93))
            b = M.spike(0.013, 0.05 + rng.uniform(0, 0.02), sides=4)
            M.xform(b, matrix=M.orient(p, (sx * 0.2, 0, -1)))
            a.add(b, "ichor", bone="body", name="drip", shading="flat")

    def build(self, col):
        a = M.Assembly(self.V["key"] + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        self.hull(a)
        self.plates(a)
        self.head(a)
        self.legs(a)
        self.drips(a)
        tris = a.tris()
        obj = a.to_object(col)
        obj["gfa_variant"] = self.vk
        self.parts = a.parts
        self.tris = tris
        C.log("%s mesh: %d tris, %d parts" % (self.V["key"], tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def pivots(self):
        body_z = self.hull_at(Y_C)[1]
        g = self.plate_geo[len(self.plate_geo) // 2]
        ty = (g["y0"] + g["y1"]) / 2
        _, cz, _, h = self.hull_at(ty)
        return {"root": (0, Y_C, 0.0), "body": (0, Y_C, body_z), "head": self.hinge, "legs_a": (0, Y_C, 0.21),
                "legs_b": (0, Y_C, 0.21), "tail": (0, ty, cz + 0.3 * h)}

    def sockets(self):
        body_z = self.hull_at(Y_C)[1]
        top = max(self.hull_top, self.shard_top)
        return [("body", "hit_center", (0, Y_C, body_z + 0.02)), ("body", "fx_core", self.core_pt),
                ("body", "fx_mouth", (0, self.head_front - 0.01, self.head_c[2] - 0.02)),
                ("body", "head_top", (0, Y_C, top + 0.14))]

    # -- paint --
    def recipes(self):
        rim = {"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8"}
        return {
            "hull": P.faction_zone("unmade", "obsidian", light=LIGHT_WARM, planes=0.14, parts=0.04, brush=0.07,
                                   brush_freq=4.0, edge=0.9, edge_width=0.007, edge_breakup=0.42, cavity=0.85,
                                   cavity_width=0.008, ao=0.65,
                                   gradient={"axis": (0, 0, 1), "range": (0.30, 0.10), "color": "shadow", "amount": 0.5}),
            "plate": P.faction_zone("unmade", "obsidian", light=LIGHT_WARM, planes=0.22, parts=0.10, brush=0.09,
                                    brush_freq=4.0, edge=1.0, edge_width=0.010, edge_breakup=0.46, cavity=0.85,
                                    cavity_width=0.008, ao=0.7),
            "limb": P.faction_zone("unmade", "obsidian", light=LIGHT_WARM, planes=0.14, parts=0.06, edge=0.9,
                                   edge_width=0.006, edge_breakup=0.38, cavity=0.7, ao=0.5,
                                   gradient={"axis": (0, 0, 1), "range": (0.22, 0.0), "color": "shadow", "amount": 0.3}),
            "skull": P.faction_zone("unmade", "obsidian", light=mix_hex(LIGHT_WARM, "#7FA7A0", 0.35), planes=0.14,
                                    parts=0.03, edge=0.85, edge_width=0.007, edge_breakup=0.4, cavity=0.8, ao=0.6,
                                    stroke=(0, 0, 1), stroke_amount=0.3, stroke_freq=(55.0, 5.0)),
            "bone": P.faction_zone("unmade", "bone", planes=0.08, parts=0.06, edge=0.55, edge_width=0.005, cavity=0.75,
                                   ao=0.65, gradient={"axis": (0, 0, 1), "range": (0.25, 0.06), "color": "shadow", "amount": 0.35}),
            # the core under the scutes: teal, white-mint only right at fx_core (it shows through slits / the rift)
            "core": P.faction_zone("unmade", "ichor", glow=True,
                                   emit=dict(rim, mode="radial", center=self.core_pt, radius=0.13, base_mix=0.1)),
            "maw": P.faction_zone("unmade", "ichor", glow=True,
                                  emit=dict(rim, mode="radial", center=self.mouth_pt, radius=0.14, base_mix=0.2)),
            "ichor": P.faction_zone("unmade", "ichor", glow=True, emit=dict(rim, core="#8FF2D8", mode="flat")),
        }

    def _glow_lines(self, lines, frame, width, zones, depth, facing=0.3, halo=0.03):
        """A glowing fissure: first a wide painted teal spill (glow bleeding into the obsidian, faintly
        emissive), then the crack itself - a burnt dark lip around a teal line with a mint core."""
        return [P.decal_lines(lines, frame, 0.001, zones=zones, color=None, rim=SPILL, rim_width=halo,
                              emit={"color": "#0B2F2B", "core": "#0B2F2B"}, depth=depth, facing=facing - 0.4),
                P.decal_lines(lines, frame, width, zones=zones, color="#2FBFA8", rim="#07060A", rim_width=width * 2.4,
                              emit={"color": "#2FBFA8", "core": "#B8FFE8"}, depth=depth, facing=facing)]

    def decals(self):
        """Few, bold fissures (a crack web turns to speckle at 35 px): 2-5 per variant on the scutes, one over
        the skull, a weeping crack on each flank; teal spill along every glowing slit between the scutes."""
        V = self.V
        rng = random.Random(V["seed"] + 100)
        out = []
        L = V["hull_len"]
        top = Matrix.Translation((0, 0, 0.28))
        kind = V["cracks"]
        lines = []
        if kind == "web":
            for st, dr, ln in (((0.03, 0.05), 200, 0.23), ((-0.02, 0.07), -25, 0.2), ((0.0, -0.1), 105, 0.15)):
                lines += M.crack_lines(rng, start=st, direction=dr, length=ln * L, step=0.02, jag=0.45, branches=1,
                                       branch_len=0.4, depth=1)
        elif kind == "spine":
            for x in (0.028, -0.03):
                lines += M.crack_lines(rng, start=(x, -0.17 * L), direction=90, length=0.44 * L, step=0.022, jag=0.3,
                                       branches=2, branch_len=0.3, branch_angle=60, depth=1)
        elif kind == "star":
            for k in range(5):
                lines += M.crack_lines(rng, start=(0.0, 0.05), direction=k * 72 + 20, length=0.2, step=0.02, jag=0.4,
                                       branches=1, branch_len=0.35, depth=1)
        elif kind == "rift":
            for y in (-0.1, 0.12):
                for sx in (1, -1):
                    lines += M.crack_lines(rng, start=(sx * V["split"] / 2, y * L),
                                           direction=(0 if sx > 0 else 180) + rng.uniform(-25, 25),
                                           length=0.14, step=0.02, jag=0.45, branches=0, depth=0)
        out += self._glow_lines(lines, top, 0.008, ["plate"], (0.0, 0.4), halo=0.032)
        # teal spill on the scute lips beside each glowing slit (and along the rift)
        slits = []
        g = self.plate_geo
        for a_, b_ in zip(g[:-1], g[1:]):
            y = (a_["y1"] + b_["y0"]) / 2
            slits.append([(-0.24, y), (0.24, y)])
        if V["split"] > 0:
            slits.append([(0.0, g[0]["y0"]), (0.0, g[-1]["y1"])])
        out.append(P.decal_lines(slits, top, 0.001, zones=["plate"], color=None, rim=SPILL, rim_width=0.03,
                                 emit={"color": "#0B2F2B", "core": "#0B2F2B"}, depth=(0.0, 0.4), facing=-0.6))
        # a crack over the skull (from the split back over the crown)
        hy = self.head_c[1]
        sk = M.crack_lines(rng, start=(0.02, hy - 0.08 * V["head"]), direction=75, length=0.13, step=0.018, jag=0.45,
                           branches=1, depth=1)
        out += self._glow_lines(sk, Matrix.Translation((0, 0, self.head_c[2])), 0.007, ["skull"], (0.0, 0.25), halo=0.024)
        # hull side cracks weeping ichor (both sides), projected sideways
        for sx in (1, -1):
            xa = Vector((0, sx, 0))
            ya = Vector((0, 0, 1))
            za = xa.cross(ya)
            fr = Matrix(((xa.x, ya.x, za.x, sx * 0.05), (xa.y, ya.y, za.y, 0.0), (xa.z, ya.z, za.z, 0.24), (0, 0, 0, 1)))
            cl, weep = [], []
            for u0 in ((-0.10, 0.12) if sx > 0 else (0.02,)):
                c = M.crack_lines(rng, start=(u0 * sx, 0.05), direction=-80 + rng.uniform(-20, 20), length=0.1, step=0.016,
                                  jag=0.45, branches=1, depth=1)
                cl += c
                end = c[0][-1]
                weep.append([(end[0], end[1]), (end[0] + 0.004, end[1] - 0.03), (end[0] - 0.003, end[1] - 0.06)])
            out += self._glow_lines(cl, fr, 0.007, ["hull"], (0.0, 0.3), halo=0.022)
            out.append(P.decal_lines(weep, fr, 0.009, zones=["hull"], color="#1F8F7E", rim=None,
                                     emit={"color": "#0D3B35", "core": "#1F8F7E"}, depth=(0.0, 0.3), facing=0.2))
        return out


# ---- UVs: importance-weighted islands ----------------------------------------------------------------------------

def weighted_unwrap(orig_unwrap):
    """Wrap gfa_paint.unwrap (installed by main() only; the shared module is untouched): every part is scaled
    about its own centre by UV_WEIGHT[zone] before the smart-project / average-scale / pack, so what the game
    camera sees (scutes, skull) gets more texels than the belly and the drips; the mesh is restored after."""
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
        orig_unwrap(obj, size, margin_px, angle_limit, **kw)      # (newer gfa_paint passes zone_scale=...)
        me.vertices.foreach_set("co", co.ravel())
        me.update()
        return P.texel_density(obj, size)
    return unwrap


# ---- mirroring (variants with the three limbs on the other side) --------------------------------------------------

def mirror_mesh_x(obj):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.transform(bm, matrix=Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)), verts=bm.verts[:])
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:], flip_multires=False)
    bm.to_mesh(me)
    bm.free()
    me.update()


def mx(p, mirror):
    return (-p[0], p[1], p[2]) if mirror else tuple(p)


def mirror_pose(pose):
    out = {}
    for b, tr in pose.items():
        t = {}
        if "rot" in tr:
            x, y, z = tr["rot"]
            t["rot"] = (x, -y, -z)
        if "loc" in tr:
            x, y, z = tr["loc"]
            t["loc"] = (-x, y, z)
        if "scale" in tr:
            t["scale"] = tr["scale"]
        out[b] = t
    return out


# ---- clips ------------------------------------------------------------------------------------------------------

def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def counter(pose, gain=1.0, rot_only=False):
    """Legs are children of the body: cancel the root + body motion on both leg groups (small angles), so the
    feet stay planted while the shell bobs, rolls and pitches over them. Returns the pose (modified)."""
    tot_r, tot_l = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    for b in ("root", "body"):
        tot_r = _add(tot_r, pose.get(b, {}).get("rot", (0, 0, 0)))
        tot_l = _add(tot_l, pose.get(b, {}).get("loc", (0, 0, 0)))
    for g in ("legs_a", "legs_b"):
        tr = pose.setdefault(g, {})
        tr["rot"] = _add(tr.get("rot", (0, 0, 0)), tuple(-gain * v for v in tot_r))
        if not rot_only:
            tr["loc"] = _add(tr.get("loc", (0, 0, 0)), tuple(-gain * v for v in (tot_l[0], tot_l[1], 0.0)))
    return pose


def pulse(t, t0, w):
    d = ((t - t0 + 0.5) % 1.0) - 0.5
    return math.exp(-(d / w) ** 2)


def make_clips(arm, key, V):
    mo = V["motion"]
    mir = V["mirror"]
    fix = mirror_pose if mir else (lambda p: p)
    sin, cos, tau = math.sin, math.cos, 2 * math.pi

    def idle(t):
        w = tau * t
        tw = pulse(t, 0.30, 0.03)
        jaw = mo["jaw_idle"] * (0.5 + 0.5 * sin(w)) + 10 * pulse(t, 0.55, 0.022) + 8 * pulse(t, 0.63, 0.02)
        p = {"body": {"loc": (0, 0.006 * sin(w), 0), "rot": (2.0 * sin(w) + 3 * tw, -3 * tw, 1.5 * sin(w + 1) + 4 * tw)},
             "head": {"rot": (0, jaw, 0)},
             "tail": {"loc": (0, 0.009 * (0.5 + 0.5 * sin(w - 0.8)), 0), "rot": (-3 * sin(w - 0.8), 0, 5 * pulse(t, 0.31, 0.02))},
             "legs_a": {"loc": (0, 0.022 * pulse(t, 0.8, 0.03), 0.008 * sin(w + 1))},
             "legs_b": {"loc": (0, 0.022 * pulse(t, 0.12, 0.03), -0.008 * sin(w + 1))}}
        return fix(counter(p))

    def move(t):
        w = tau * t
        la, lb = max(0.0, cos(w)), max(0.0, -cos(w))
        S, Lf = mo["stride"], mo["lift"]
        p = {"root": {"rot": (0, mo["wag"] * sin(w), 0)},
             "body": {"loc": (0, 0.010 * cos(2 * w) - 0.012 * lb, 0),
                      "rot": (mo["charge"] + 2 * sin(2 * w), 0, mo["roll"] * lb - 0.3 * mo["roll"] * la)},
             "head": {"rot": (0, mo["chatter"] * (1 + sin(2 * w + 0.5)), 0)},
             "tail": {"loc": (0, 0.006 * (1 + sin(2 * w + 1)), 0), "rot": (3 * sin(2 * w + 1), 0, 4 * sin(w + 0.5))},
             "legs_a": {"loc": (0, Lf * la, S * sin(w)), "rot": (-6 * sin(w), 0, 0)},
             "legs_b": {"loc": (0, Lf * lb, -S * sin(w)), "rot": (6 * sin(w), 0, 0)}}
        return fix(counter(p))

    rest = {}
    dip = counter({"body": {"rot": (7, 0, 0), "loc": (0, -0.018, 0.01)}, "head": {"rot": (0, 4, 0)},
                   "tail": {"rot": (4, 0, 0)}})
    loaded = {"root": {"loc": (0, -0.01, -0.05)}, "body": {"rot": (-24, 0, 3), "loc": (0, 0.05, -0.02)},
              "head": {"rot": (0, 42, 0)}, "tail": {"rot": (-16, 0, -4), "loc": (0, 0.03, 0)},
              "legs_a": {"rot": (21, 0, -3), "loc": (0, -0.035, -0.015)}, "legs_b": {"rot": (23, 0, -3), "loc": (0, -0.035, -0.01)}}
    loaded2 = RIG.merge(loaded, {"body": {"rot": (-26, 0, 4)}, "head": {"rot": (0, 47, 0)}, "tail": {"rot": (-18, 0, -3)}})
    strike = {"root": {"loc": (0, 0.02, 0.20)}, "body": {"rot": (20, 0, -2), "loc": (0, -0.02, 0.05)},
              "head": {"rot": (0, 0, 0)}, "tail": {"rot": (10, 0, 3)},
              "legs_a": {"rot": (-16, 0, 0), "loc": (0, 0.0, -0.06)}, "legs_b": {"rot": (-20, 0, 0), "loc": (0, 0.0, -0.07)}}
    bite = RIG.merge(strike, {"root": {"loc": (0, 0.0, 0.22)}, "body": {"rot": (24, 0, 0), "loc": (0, -0.03, 0.05)}})
    chomp = RIG.merge(bite, {"head": {"rot": (0, 15, 0)}, "body": {"rot": (17, 0, 1)}, "root": {"loc": (0, 0, 0.16)}})
    shut = RIG.merge(chomp, {"head": {"rot": (0, 0, 0)}, "root": {"loc": (0, 0, 0.1)}, "body": {"rot": (10, 0, 0)}})
    flinch = counter({"root": {"loc": (0, 0, -0.05)}, "body": {"rot": (-14, -6, -10), "loc": (0, 0.025, 0)},
                      "head": {"rot": (0, 22, 0)}, "tail": {"loc": (0, 0.035, 0), "rot": (-14, 0, 8)}}, gain=0.7, rot_only=True)
    settle = counter({"body": {"rot": (4, 2, 3)}, "head": {"rot": (0, 6, 0)}, "tail": {"rot": (5, 0, -3)}}, rot_only=True)
    conv = {"body": {"scale": 1.1, "rot": (-12, 0, 0), "loc": (0, 0.02, 0)}, "head": {"rot": (0, 28, 0)},
            "tail": {"loc": (0, 0.03, 0)}, "legs_a": {"rot": (-12, 0, 0)}, "legs_b": {"rot": (-12, 0, 0)}}
    burst = {"tail": {"loc": (0, 0.17, -0.10), "rot": (-50, 15, 25), "scale": 1.05},
             "head": {"rot": (0, 80, -15), "loc": (0.07, 0.0, 0.02)},
             "body": {"scale": 0.97, "loc": (0, -0.03, 0)},
             "legs_a": {"loc": (0.04, -0.05, 0), "rot": (0, 0, -30)}, "legs_b": {"loc": (0, -0.05, 0), "rot": (-25, 0, 0)}}
    fall = {"tail": {"loc": (0, 0.04, -0.24), "rot": (-120, 30, 50), "scale": 0.9},
            "head": {"rot": (0, 100, -60), "loc": (0.13, -0.10, 0.04)},
            "body": {"loc": (0, -0.12, 0), "rot": (8, 0, 20)},
            "legs_a": {"loc": (0.06, -0.10, 0), "rot": (0, 0, -40)}, "legs_b": {"loc": (0, -0.09, 0), "rot": (-40, 0, 0)}}
    crumble = RIG.merge(fall, {"tail": {"scale": 0.45, "loc": (0, -0.02, -0.26)}, "head": {"scale": 0.45},
                               "body": {"scale": 0.75, "loc": (0, -0.14, 0)}})
    gone = RIG.merge(crumble, {"tail": {"scale": 0.02}, "head": {"scale": 0.02}, "legs_a": {"scale": 0.05},
                               "legs_b": {"scale": 0.05}, "body": {"scale": 0.02, "loc": (0, -0.2, 0)},
                               "root": {"loc": (0, -0.03, 0)}})
    F = fix
    names = []
    RIG.cycle_clip(arm, key, "idle@loop", mo["idle_frames"], idle)
    RIG.cycle_clip(arm, key, "move@loop", mo["move_frames"], move)
    RIG.keyed_clip(arm, key, "windup", [(0, rest), (3, F(dip)), (10, F(loaded)), (15, F(loaded2))])
    RIG.keyed_clip(arm, key, "attack", [(0, F(loaded2)), (3, F(strike)), (5, F(bite)), (7, F(chomp)), (9, F(shut)), (15, rest)])
    RIG.keyed_clip(arm, key, "hit", [(0, rest), (2, F(flinch)), (5, F(settle)), (9, rest)])
    RIG.keyed_clip(arm, key, "death", [(0, rest), (3, F(conv)), (6, F(burst)), (12, F(fall)), (18, F(crumble)),
                                       (26, F(gone)), (27, F(gone))])
    for c in SPEC.ENEMY_CLIPS_REQUIRED:
        names.append(RIG.clip_name(key, c))
    return names


# key frames shown in the review strips (per clip; move / idle scale with the loop length)
def key_frames(V):
    mf, idf = V["motion"]["move_frames"], V["motion"]["idle_frames"]
    return {"idle@loop": [0, int(idf * 0.3), int(idf * 0.56), int(idf * 0.8)],
            "move@loop": [0, round(mf * 0.25), round(mf * 0.5), round(mf * 0.75)],
            "windup": [0, 3, 10, 15], "attack": [0, 3, 5, 7, 15], "hit": [0, 2, 5, 9], "death": [0, 3, 6, 12, 18, 26]}


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


def size_compare(mesh, work, key, height):
    """Side view (orthographic, from the creature's left) of the clinker next to the 2.2 m hero mannequin,
    with the hero's waist line (1.1 m, the swarm ceiling) and the clinker's own top."""
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (0.0, 1.0, 0.0)
    bpy.context.view_layer.update()
    bars = [guide_bar("GUIDE_waist", (0.8, -0.8, 1.1), (0.8, 1.6, 1.1), 0.012, "#D9CFA6"),
            guide_bar("GUIDE_top", (0.8, -0.8, height), (0.8, 0.5, height), 0.008, "#8FF2D8"),
            guide_bar("GUIDE_ground", (0.8, -0.8, 0.0), (0.8, 1.6, 0.0), 0.01, "#6B5A50")]
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh, man], ink=0.008, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (0.0, 0.42, 1.12), (1.0, 0.0, 0.0), 2.5)
        p = R.render(scene, os.path.join(work, "%s_size_side.png" % key), 420, 420)
    C.remove_objects([man] + bars)
    return p


def clip_strips(arm, mesh, work, key, V):
    scene = bpy.context.scene
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    pts = R._points([mesh])
    d = R.CREATURE_VIEWS["34_front"]
    c, w, h = R.frame(pts, d)
    ext = max(w, h) * 1.38
    c = c + Vector((0, -0.04, 0.0))
    R.setup_cycles(scene, 10)
    out = []
    with R.toon_preview([mesh], ink=0.004):
        for clip, frames in key_frames(V).items():
            track = RIG.clip_name(V["key"], clip)
            for f in frames:
                RIG.pose_at(arm, track, f)
                R.aim(scene, c, d, ext)
                p = os.path.join(work, "%s_clip_%s_f%02d.png" % (key, clip.replace("@", "_"), f))
                out.append((clip, f, R.render(scene, p, 200)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def ingame_poses(arm, mesh, work, key, V, view_height=SPEC.GAME_VIEW_HEIGHTS[0]):
    """Key poses through the game camera at true 1080p pixel size (no mannequin, 90 px crops)."""
    out = []
    poses = [("rest", None, 0), ("skitter", "move@loop", round(V["motion"]["move_frames"] * 0.25)),
             ("wind-up (loaded)", "windup", 15), ("attack (bite)", "attack", 5), ("hit", "hit", 2), ("death", "death", 12)]
    for label, clip, f in poses:
        if clip:
            RIG.pose_at(arm, RIG.clip_name(V["key"], clip), f)
        else:
            RIG.unmute_none(arm)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_pose_%s" % (key, label.split()[0].replace("-", "")), px=56, view_height=view_height,
                     target=(0.0, -0.05, 0.2), silhouette_too=False, ink=0.01)
        out.append((label, r["color"]))
    RIG.unmute_none(arm)
    bpy.context.scene.frame_set(0)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    return out


def review(b, arm, mesh, rep, reports, work, tex, notes):
    V = b.V
    key = V["key"]
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    out = {}
    turn = R.turnaround([mesh], work, key, R.CREATURE_VIEWS, size=400)
    height = rep.get("height_m") or 0.5
    size_p = size_compare(mesh, work, key, height)
    strips = clip_strips(arm, mesh, work, key, V)
    # in-game camera: the clinker at 3/4 toward the camera beside the mannequin, then 3/4 away
    ing = []
    for label, yaw in (("facing the camera", -35.0), ("moving away", 145.0)):
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.0, 0.25, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_%s" % (key, "face" if yaw < 0 else "away"), px=150, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                     mannequin_obj=man)
        C.remove_objects([man])
        ing.append((label, r))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    arm.rotation_euler = (0.0, 0.0, math.radians(-35.0))
    poses = ingame_poses(arm, mesh, work, key, V)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Clinker - %s  (%s.glb)" % (V["name"], key),
        "subtitle": "E1 Shardling | The Unmade | Swarm, Cinder Wastes | verb SKITTER | GF_Swarm_v1 | %s" % (
            "three limbs on the RIGHT (mirrored)" if V["mirror"] else "three limbs on the LEFT"),
        "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn.items()]},
            {"label": "Size vs the 2.2 m hero (side; waist line = swarm ceiling) | in-game camera, 55 deg, %.1f px/m, TRUE size 1x, then 3x nearest" % ppm,
             "height": None, "images": [{"path": size_p, "label": "side: %.2f m tall = %.2f x hero" % (height, height / 2.2)},
                                        {"path": ing[0][1]["color"], "label": "1x"},
                                        {"path": ing[0][1]["color"], "label": "3x " + ing[0][0], "scale": 3},
                                        {"path": ing[1][1]["color"], "label": "3x " + ing[1][0], "scale": 3}]},
            {"label": "Game-size silhouette (3x) and key poses through the game camera at TRUE pixel size (3x nearest)", "height": None,
             "images": [{"path": ing[0][1]["sil"], "label": "silhouette 3x", "scale": 3}]
                + [{"path": p, "label": lb, "scale": 3} for lb, p in poses]},
            {"label": "Clip key frames (3/4 front): idle@loop, move@loop (skitter), windup, attack, hit, death", "height": 150,
             "images": [{"path": p, "label": "%s f%d" % (cl, f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220, "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % key), work)
    out.update({"turn": turn, "size": size_p, "ingame": ing, "poses": poses})
    return out


# ---- main ----------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    vk = C.opt(argv, "--variant", "base")
    size = C.opt(argv, "--size", 512, int)
    V = VARIANTS[vk]
    key = V["key"]
    C.reset_scene(fps=FPS)
    col = C.get_collection(key)
    b = Build(vk)
    mesh = b.build(col)
    pack = C.pack_dir(KIND, CONTENT_KEY)
    tex_dir = os.path.join(pack, "textures")
    work = C.ensure_dir(os.path.join(pack, "work", key))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    # paint in the canonical frame, then mirror (the texture follows the UVs)
    P.unwrap = weighted_unwrap(P.unwrap)
    paint_rep = P.paint_asset(mesh, key, b.recipes(), tex_dir, size=size, decals=b.decals(), ao_distance=0.04,
                              ao_samples=16, edge_min_angle=24.0, margin_px=3, uv_angle=66.0, seed=V["seed"])
    mir = V["mirror"]
    if mir:
        mirror_mesh_x(mesh)
    piv = {k: mx(p, mir) for k, p in b.pivots().items()}
    arm = RIG.build_swarm_rig(piv, col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in b.sockets():
        RIG.add_socket(arm, bone, name, mx(p, mir))
    clips = make_clips(arm, key, V)
    blend = os.path.join(pack, "source", key + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    variants = [VARIANTS[k]["key"] for k in ("base", "v1", "v2", "v3")]
    extra = {
        "content_key": CONTENT_KEY,
        "variant": vk, "variant_name": V["name"], "variant_set": variants,
        "variant_rule": "one file per look; identical GF_Swarm_v1, sockets and clip suffixes; clips are named "
                        "{file_stem}_{clip}. Pick one of variant_set per spawn (clinker.glb alone is complete).",
        "mirrored": mir,
        "limbs": "three shard legs on the %s, one huge clawed arm on the %s" % (("right", "left") if mir else ("left", "right")),
        "gait": "legs_a = front + rear leg of the three-leg side; legs_b = middle leg + the big arm (limps)",
        "move_cycle_m": V["motion"]["move_cycle_m"],
        "move_note": "rigid-group skitter: play move@loop at speed / move_cycle_m cycles per second (row speed 3.8 m/s "
                     "-> about 6 cycles/s, the frantic flicker that reads as SKITTER at 35 px)",
        "content_row": ROW,
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
        "skin": skin,
    }
    rep = E.export_asset(KIND, key, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.log("clips", RIG.clips_report(arm))
    rep_path = os.path.join(reports, "%s_build_report.json" % key)
    C.write_json(rep_path, {"export": {k: rep[k] for k in rep if k not in ("nodes",)}, "paint": paint_rep, "skin": skin,
                            "parts": b.parts, "tris_blender": b.tris, "clips": RIG.clips_report(arm)})
    if not C.flag(argv, "--no-review"):
        tex = [os.path.join(tex_dir, key + "_basecolor.png"), os.path.join(tex_dir, key + "_emissive.png")]
        notes = [
            "%s tris (swarm budget 600-1500, brief 600-1200) | textures %s | %.2f m tall (%.2f x hero), %.2f m long | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"], rep["height_m"] / 2.2,
                (rep["bounds"]["max"][2] - rep["bounds"]["min"][2]), ", ".join(sorted(rep["sockets"]))),
            "Clips: %s" % ", ".join(c["name"].replace(key + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
            "Jaw: the head bone is the hinged left skull half (yaw opens it; mirrored variants open to the right). "
            "move_cycle_m %.2f. Status: %s." % (V["motion"]["move_cycle_m"], SPEC.STATUS_AI_FINAL),
        ]
        review(b, arm, mesh, rep, reports, work, tex, notes)
    C.log("DONE", key)


if __name__ == "__main__":
    main()
