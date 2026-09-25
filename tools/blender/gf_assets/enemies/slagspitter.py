"""Slagspitter - the Cinder Wastes swarm SPIRE (The Unmade): a squat cone of cooled slag with a molten maw on
top. It lobs molten slag where you are about to be. Built, painted, rigged on GF_Swarm_v1, animated, exported
and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/slagspitter.py -- [--size 512] [--no-review] [--preview]
  ... -P tools/blender/gf_assets/enemies/slagspitter.py -- --crowd      (after the build and the clinker family:
                                                                          40 slagspitters + clinkers, game camera)

Content row (content/sheets/enemies.csv): slagspitter, Swarm, P0, hp 40, speed 2.6, radius 0.48, scale 1.0,
Lobber(range 11, windup 1.1, radius 1.4, damage 18, cooldown 3.2, keep_distance 7), colour #C24A1C, shape
Spire, packs of 1-2 - "Lobs molten slag where you are about to be." Collider radius x scale = 0.48 m, so the
footprint is ~1.05-1.45 m (docs/art/ENEMIES.md section 2); the swarm tier keeps it below the hero's waist.

Design (docs/art/ENEMIES.md sections 3-5; the user's enemy pack; brief, decisions and metrics in
art/enemies/slagspitter/README.md):
  * verb LOB: a squat lava cone - six thick slag crust plates over a molten core, on three stubby toes. The
    seams between the plates widen toward the top, so the core glows through as cracks radiating from the maw;
    each plate's top edge rises into one jagged tooth that curls in over the maw (low in front, a tall crown at
    the back). The molten glob in the crater is the `head` bone: in the wind-up the cone squats and tilts back
    to aim while the glob swells up out of the maw (the one bright shape at game size that says "about to
    throw"); the attack springs the cone up and the glob leaves the maw (attack_origin), then the cone recoils
    and the maw refills. (The first blockout, a stack of concentric tiers, read as a beehive / cake.)
  * value plan at game size: slag plates darker than the #3A2C24 floor, framed by light brush strokes on each
    plate's own edges (gfa_brush broad zones) and the hot seams between them; the crust teeth a step lighter;
    the glob the brightest spot, its hot centre small, a band of dark cooling crust round its base
    (crust_pass); two teal Unmade fissures; a flat molten tongue spilling over the low front plate;
  * Unmade asymmetry: the neck leans forward and to one side, a slag blister bulges from the right front, a
    cluster of black obsidian shards erupts from the back left, three toes (two on the left, one big one on the
    right), the maw breached in front;
  * palette: THE UNMADE (gfa_spec.FACTIONS): slag, molten (the Slag King's glow ramp, pale-peach hot spot, no
    gold), obsidian, ichor teal. The row colour #C24A1C only warms the slag toward the maw (hot slag). No
    player colours, no red-white (the build's review audits both textures).

Rig GF_Swarm_v1 (rigid): body = the cone (plates, core, lip, overflow tongue); head = the molten glob (it
swells, leaves on the lob and refills); legs_a = the two left toes; legs_b = the big right toe; tail = the
obsidian back shards (they flare in the wind-up and blow off in the death). Every body pose keeps the lowest
skirt point on the ground. In idle and move the leg groups (sharing the body pivot) counter the body exactly
(basis = body^-1 @ own motion), so the toes stay planted while the cone rocks over them; in the one-shots they
ride with the body (a rearing cone lifts its front toe).

Toolkit: tools/blender/gf_assets (gfa_model / gfa_paint / gfa_rig / gfa_export / gfa_render / gfa_boss).
Structure and review layout follow enemies/clinker.py (the reviewed swarm).
"""
import math
import os
import random
import shutil
import sys
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402
import gfa_shell as S  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "slagspitter"
KIND, TIER = "enemy", "swarm"
FPS = 30
SEED = 71
ROW = {"key": "slagspitter", "class": "Swarm", "biome": "cinder_wastes", "hp": 40, "speed": 2.6, "radius": 0.48,
       "scale": 1.0, "behavior": "Lobber(range: 11.0, windup: 1.1, radius: 1.4, damage: 18.0, cooldown: 3.2, "
       "keep_distance: 7.0)", "color": "#C24A1C", "shape": "Spire", "pack": "(1, 2)"}
ZONES = ["slag", "crust", "core", "molten", "spill", "obsidian", "under"]
ZONE_PREVIEW = {"slag": "#4A362C", "crust": "#8C6A52", "core": "#C8400C", "molten": "#FF8A30", "spill": "#FF6B1A",
                "obsidian": "#231F2C", "under": "#1A1310"}

# ---- the cone: slag crust plates over a molten core ---------------------------------------------------------------
# The outer flank radius r_out(z): a concave volcano flank, wide skirt on the ground, a thick neck at the maw.
BASE_R, NECK_R, CONE_H, FLANK_EXP = 0.555, 0.290, 0.70, 1.75
PLATE_TWIST = 0.32                 # rad per metre of height: the seams wind a little round the cone
PLATE_T = 0.045                    # crust plate thickness
GAP0, GAP1 = 3.0, 9.5              # seam between two plates (deg) at the ground / at the top: the seams widen
                                   # toward the maw, so the molten core shows as glowing cracks radiating from it
DOME = 0.075                       # each plate bows out across its width (every plate reads as its own form)
LEAN_X = -0.05                     # the neck leans to the creature's right (-X) ...
NECK_FWD = 0.22                    # ... and forward (-Y): the mortar muzzle points toward the target
BULGE_TH, BULGE_Z, BULGE_A = math.radians(215.0), 0.16, 0.09      # a slag blister (right front, low)
# plates: (angle from, angle to (deg, counter-clockwise from +X; front = 270), top height, tooth height, tooth
# position across the plate 0..1, inward curl of the tooth (m)). The front plate is low: the maw breaches there
# and the molten glob spills over it (the one bright shape the camera sees face-on).
PLATES = [
    (242.0, 298.0, 0.505, 0.030, 0.40, 0.00),     # front: the breach
    (298.0, 350.0, 0.615, 0.090, 0.30, 0.05),     # front left
    (350.0, 425.0, 0.645, 0.165, 0.66, 0.07),     # left / back left (the widest)
    (425.0, 488.0, 0.665, 0.235, 0.42, 0.09),     # back (the tallest tooth: a jagged crown behind the glow)
    (488.0, 548.0, 0.640, 0.150, 0.52, 0.07),     # back right
    (548.0, 602.0, 0.600, 0.080, 0.65, 0.05),     # right
]
PLATE_NU, PLATE_NV = 4, 4
CORE_SIDES = 12
LIP_Z = 0.600                      # the core's crater lip (under the plate teeth, above the front breach)
THROAT = [(0.225, 0.625), (0.190, 0.600), (0.0, 0.582)]    # over the lip into the crater (under the glob)

# the molten glob (head bone): a lumpy dome in the crater, its top a little above the lip
GLOB_R, GLOB_H, GLOB_Z = 0.182, 0.108, 0.628
HEAD_PIVOT_Z = 0.585               # the crater floor: scaling the head grows the glob up out of the maw
BODY_Z = 0.20                      # body pivot (centre of mass of a squat cone); legs share it

# toes: (name, angle deg, size, bone). Two on the left, one big one on the right (the Unmade 2 + 1).
TOES = [("L", 322.0, 1.0, "legs_a"), ("B", 80.0, 0.9, "legs_a"), ("R", 214.0, 1.2, "legs_b")]
# obsidian shards breaking out of the back-left seam (tail): (angle deg, height, length, base radius, tilt deg)
SHARDS = [(42.0, 0.36, 0.44, 0.08, 34.0), (58.0, 0.27, 0.28, 0.06, 50.0), (26.0, 0.24, 0.18, 0.046, 58.0)]
# the overflow: molten slag spilling from the maw over the low front plate
SPILL = (0.42, 0.44, 0.042)        # (u across the front plate, lowest v on it, radius)

TEAL = {"color": "#2FBFA8", "core": "#B8FFE8"}
HOT_SLAG = "#5A2412"               # the row colour #C24A1C pulled into the slag shadow: hot slag near the maw
PALETTE = [("slag", "#231A17"), ("slag stroke", "#7A5A48"), ("crust", "#3E2E25"), ("crust stroke", "#B08A68"),
           ("hot slag", HOT_SLAG), ("seam glow", "#9A2A08"), ("molten rim", "#C23C0C"), ("molten", "#FF6B1A"),
           ("hot spot", "#FFC88A"), ("cooled crust", "#2A1510"), ("obsidian", "#1A1720"), ("teal glow", "#2FBFA8"),
           ("row tint", ROW["color"])]


def angdiff(a, b):
    return (a - b + math.pi) % (2 * math.pi) - math.pi


def smooth01(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def r_out(z):
    t = max(0.0, min(1.0, z / CONE_H))
    return NECK_R + (BASE_R - NECK_R) * (1.0 - t) ** FLANK_EXP


def lump(th, z, amount=1.0):
    """Radius multiplier: lobes that drift with height (cooled flows), plus the blister."""
    k = (0.045 * math.cos(th - 4.0 + 1.6 * z) + 0.032 * math.cos(2 * th + 0.9 - 2.8 * z)
         + 0.022 * math.cos(3 * th + 2.1 + 3.3 * z))
    b = BULGE_A * math.exp(-(angdiff(th, BULGE_TH) / 0.5) ** 2) * math.exp(-((z - BULGE_Z) / 0.12) ** 2)
    return 1.0 + amount * (k + b)


def center(z):
    return LEAN_X * z, -NECK_FWD * max(0.0, z - 0.30)


def pos(r, z, th, amount=1.0):
    cx, cy = center(z)
    rr = r * lump(th, z, amount)
    return Vector((cx + rr * math.cos(th), cy + rr * math.sin(th), z))


def surf(th, z):
    """A point on the plates' outer flank at angle th and height z (ignoring each plate's bow), its normal."""
    def at(th_, z_):
        return pos(r_out(z_), z_, th_)
    p = at(th, z)
    n = (at(th + 0.01, z) - at(th - 0.01, z)).cross(at(th, z + 0.01) - at(th, z - 0.01)).normalized()
    if n.dot(Vector((math.cos(th), math.sin(th), 0.0))) < 0:
        n = -n
    return p, n


def plate_fn(pi):
    """Surface fn(u, v) of crust plate pi: u across (0..1 counter-clockwise), v up (0 = ground, 1 = the top edge
    with its tooth). Each plate bows out, its seams widen toward the top, the top edge rises into a tooth that
    curls in over the maw, and the whole plate winds a little round the cone."""
    a0, a1, top, tooth, tu, curl = PLATES[pi]

    def fn(u, v):
        g = GAP0 + (GAP1 - GAP0) * v
        tp = max(0.0, 1.0 - abs(u - tu) / 0.5) ** 1.4          # the tooth profile along the top edge
        zt = top + tooth * tp - 0.03 * (1.0 - tp)
        z = zt * v
        th = math.radians(a0 + g / 2 + (a1 - a0 - g) * u) + PLATE_TWIST * z
        r = r_out(z) * (1.0 + DOME * math.sin(math.pi * u) * (1.0 - 0.5 * v)) - curl * tp * v ** 3
        return pos(r, z, th)
    return fn


def fn_normal(fn, u, v, eps=1e-3):
    du = fn(min(1.0, u + eps), v) - fn(max(0.0, u - eps), v)
    dv = fn(u, min(1.0, v + eps)) - fn(u, max(0.0, v - eps))
    return du.cross(dv).normalized()


def split_by_faces(bm, key_fn):
    """{key: bmesh copy keeping only the faces with key_fn(face) == key}. bm is freed. The keys are taken
    from bm's faces by index (a copy keeps the face order; layers do not carry across copies)."""
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    fkeys = [key_fn(f) for f in bm.faces]
    out = {}
    for k in sorted(set(fkeys)):
        c = bm.copy()
        c.faces.ensure_lookup_table()
        dele = [c.faces[i] for i, fk in enumerate(fkeys) if fk != k]
        bmesh.ops.delete(c, geom=dele, context="FACES")
        c.normal_update()
        out[k] = c
    bm.free()
    return out


# ---- the model --------------------------------------------------------------------------------------------------

class Build:
    """The geometry, rig anchors and sockets (creature faces -Y, its left is +X, ground at z = 0)."""

    def core(self, a):
        """The molten core: a closed cone just inside the plates, over the crater lip into the throat. It shows
        through the seams, over the low front plate and inside the maw (its paint glows hotter toward the maw)."""
        prof = [(r_out(z) - PLATE_T - 0.008, z) for z in (0.0, 0.12, 0.25, 0.38, 0.50, 0.60)]
        prof += [(r_out(LIP_Z) - PLATE_T + 0.004, LIP_Z - 0.035), (r_out(LIP_Z) - PLATE_T - 0.012, LIP_Z)]
        prof += THROAT
        bm = bmesh.new()
        rings = []
        for k, (r, z) in enumerate(prof):
            if r <= 1e-6:
                cx, cy = center(z)
                rings.append([bm.verts.new((cx, cy, z))])
                continue
            amt = 0.35 if k >= len(prof) - len(THROAT) else 1.0
            rings.append([bm.verts.new(pos(r, z, 0.2 * k + 2 * math.pi * i / CORE_SIDES, amt))
                          for i in range(CORE_SIDES)])
        for ra, rb in zip(rings[:-1], rings[1:]):
            n = CORE_SIDES
            for i in range(n):
                if len(rb) == 1:
                    bm.faces.new((ra[i], ra[(i + 1) % n], rb[0]))
                else:
                    bm.faces.new((ra[i], ra[(i + 1) % n], rb[(i + 1) % n], rb[i]))
        cx, cy = center(0.0)
        c0 = bm.verts.new((cx, cy, 0.0))
        for i in range(CORE_SIDES):
            bm.faces.new((rings[0][(i + 1) % CORE_SIDES], rings[0][i], c0))
        M.recalc(bm)
        for zone, piece in split_by_faces(bm, lambda f: "under" if f.calc_center_median().z < 0.01 else "core").items():
            a.add(piece, zone, bone="body", name="core_" + zone, shading="auto", sharp_angle=40.0)
        cx, cy = center(LIP_Z)
        self.maw_pt = Vector((cx, cy, LIP_Z + 0.03))

    def plates(self, a):
        """Six thick crust plates, each bowed out, the seams between them widening toward the top, the top
        edge rising into one jagged tooth that curls in over the maw."""
        self.plate_tops = []
        for pi, (a0, a1, top, tooth, tu, curl) in enumerate(PLATES):
            fn = plate_fn(pi)
            outer, inner = S.thick_patch(fn, PLATE_NU, PLATE_NV, PLATE_T, inner=True)
            inner.free()                               # the inside skin faces the core, 8 mm away: never seen
            for vtx in outer.verts:                    # the bottom rim's inner edge is offset along the skirt's
                vtx.co.z = max(0.0, vtx.co.z)          # up-tilted normal, below the ground: flatten it onto z = 0
            M.noise_displace(outer, 0.005, freq=7.0, seed=SEED + 31 * pi, mask=lambda v: smooth01(0.01, 0.05, v.co.z))
            ztop = top + tooth
            ztop_edge = top - 0.03
            cut = ztop_edge - (top / PLATE_NV) * 0.55

            def key(f, cut=cut):
                return "crust" if f.calc_center_median().z > cut else "slag"
            for zone, piece in split_by_faces(outer, key).items():
                a.add(piece, zone, bone="body", name="plate%d_%s" % (pi, zone), shading="flat")
            self.plate_tops.append(ztop)
        self.lip_top = max(self.plate_tops)

    def glob(self, a):
        """The molten dome in the crater (head bone)."""
        bm = M.sphere(1.0, 10, 6)
        for v in bm.verts:
            x, y, z = v.co
            if z < 0:
                z *= 1.4                          # a deep bottom that stays inside the throat
            v.co = Vector((x * GLOB_R, y * GLOB_R, z * GLOB_H))
        cx, cy = center(GLOB_Z)
        M.xform(bm, loc=(cx, cy, GLOB_Z))
        M.noise_displace(bm, 0.010, freq=9.0, seed=SEED + 5)
        a.add(bm, "molten", bone="head", name="glob", shading="smooth")
        self.glob_c = Vector((cx, cy, GLOB_Z))
        self.glob_top = Vector((cx, cy, GLOB_Z + GLOB_H))

    def spill(self, a):
        """Molten slag overflowing the maw's breach and running down the low front plate (body bone): from inside
        the crater, over the plate's top edge, then hugging the plate down to a drip."""
        u0, v_end, rad = SPILL
        fn = plate_fn(0)
        cx, cy = center(LIP_Z)
        top = fn(u0, 1.0)
        into = Vector((top.x - cx, top.y - cy, 0.0)).normalized()
        p_in = Vector((cx, cy, LIP_Z + 0.005)) + into * 0.16
        pts, radii = [p_in], [rad * 1.15]
        flat = [(0.55, 1.5)]
        for k, (u, v) in enumerate(((u0, 1.0), (u0 + 0.03, 0.84), (u0 + 0.05, 0.64), (u0 + 0.04, v_end))):
            p = fn(u, v)
            n = fn_normal(fn, u, v)
            pts.append(p + n * rad * (0.35, 0.25, 0.2, 0.0)[k])
            radii.append(rad * (1.25, 1.0, 0.75, 0.001)[k])
            flat.append(((0.5, 1.6), (0.45, 1.5), (0.45, 1.3), (1.0, 1.0))[k])
        # a flat tongue of lava: thin along the plate normal, wide across it (up = the plate's outward normal)
        up = fn_normal(fn, u0, 0.8)
        a.add(M.tube(pts, radii, sides=6, up=tuple(up), scale_xy=flat), "spill", bone="body", name="spill",
              shading="smooth")

    def toes(self, a):
        for name, deg, s, bone in TOES:
            th = math.radians(deg)
            radial = Vector((math.cos(th), math.sin(th), 0.0))
            # a low wedge tucked under the skirt: only its blunt tip and claw show past the plates
            c = Vector((center(0.0)[0], center(0.0)[1], 0.0)) + radial * (BASE_R * 0.95)
            c.z = 0.03 * s
            bm = M.sphere(1.0, 7, 4)
            for v in bm.verts:
                x, y, z = v.co
                if z < 0:
                    z *= 0.6
                if x > 0:
                    z *= 1.0 - 0.3 * x            # tall at the heel, low at the tip
                v.co = Vector((x * 0.16 * s, y * 0.115 * s, z * 0.06 * s))
            M.xform(bm, rot=(0, 0, deg))
            M.xform(bm, loc=c)
            M.noise_displace(bm, 0.006, freq=12.0, seed=SEED + int(deg))
            for v in bm.verts:
                v.co.z = max(0.0, v.co.z)                  # flat on the ground (after the noise)
            a.add(bm, "slag", bone=bone, name="toe_" + name, shading="flat")
            # a stubby obsidian claw at the tip (the Unmade mineral breaking through)
            tip = c + radial * 0.14 * s + Vector((0, 0, 0.005))
            d = (radial + Vector((0, 0, -0.3))).normalized()
            cl = M.spike(0.032 * s, 0.085 * s, sides=3, rot_offset=90)
            M.xform(cl, matrix=M.orient(tip - d * 0.03 * s, d, (0, 0, 1)))
            for v in cl.verts:
                v.co.z = max(0.004, v.co.z)
            a.add(cl, "obsidian", bone=bone, name="claw_" + name, shading="flat")

    def shards(self, a):
        rng = random.Random(SEED + 23)
        for deg, z, ln, rad, tilt in SHARDS:
            th = math.radians(deg)
            p, n = surf(th, z)
            tr = math.radians(tilt)
            d = (Vector((0, 0, 1)) * math.cos(tr) + n * math.sin(tr)).normalized()
            tang = Vector((-math.sin(th), math.cos(th), 0.0))
            b = M.spike(rad, ln, sides=5, base_scale=(1.0, 0.62), tip=(rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01)),
                        rot_offset=rng.uniform(0, 72))
            M.xform(b, matrix=M.orient(p - n * 0.05, d, tang))
            a.add(b, "obsidian", bone="tail", name="shard", shading="flat")
        th = math.radians(SHARDS[0][0])
        p, _ = surf(th, SHARDS[1][1])
        self.tail_pivot = p

    def build(self, col):
        a = M.Assembly(KEY + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        self.core(a)
        self.plates(a)
        self.glob(a)
        self.spill(a)
        self.toes(a)
        self.shards(a)
        self.tris = a.tris()
        obj = a.to_object(col)
        self.parts = a.parts
        C.log("%s mesh: %d tris, %d parts" % (KEY, self.tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def pivots(self):
        b = (0.0, 0.0, BODY_Z)
        cx, cy = center(HEAD_PIVOT_Z)
        return {"root": (0.0, 0.0, 0.0), "body": b, "head": (cx, cy, HEAD_PIVOT_Z), "legs_a": b, "legs_b": b,
                "tail": tuple(self.tail_pivot)}

    def sockets(self):
        return [("body", "hit_center", (0.0, 0.0, 0.40)),
                ("body", "fx_core", tuple(self.glob_c)),
                ("body", "fx_mouth", tuple(self.maw_pt + Vector((0, 0, 0.04)))),
                ("head", "attack_origin", tuple(self.glob_top + Vector((0, 0, 0.03)))),
                ("body", "head_top", (0.0, 0.0, max(self.lip_top, self.glob_top.z) + 0.30))]


# ---- preview (flat zone colours, Workbench) -------------------------------------------------------------------------

def preview(mesh, work):
    import gfa_boss as B
    views = {"front": (0.0, -1.0, 0.12), "34_front": (0.7, -0.7, 0.3), "side": (1.0, 0.0, 0.1),
             "back": (0.0, 1.0, 0.12), "top": (0.0, -0.0001, 1.0), "game": tuple(B.game_dir())}
    out = B.flat_views([mesh], work, KEY, ZONE_PREVIEW, views, size=360)
    # the game camera at TRUE pixel size (49 px/m) beside the mannequin, then 3x nearest
    man = R.mannequin(aim_dir=(0.5, -0.8, 0.0))
    man.location = (-1.2, 0.3, 0.0)
    man.data.materials[0].diffuse_color = C.hex_linear(R.MANNEQUIN)
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    R.aim(scene, (-0.55, 0.0, 0.6), B.game_dir(), 150 / ppm, dist=80.0)
    p = R.render(scene, os.path.join(work, "%s_flat_game1x.png" % KEY), 150)
    out["game1x"] = p
    C.remove_objects([man])
    return out


# ---- paint --------------------------------------------------------------------------------------------------------

def recipes(b):
    """Zone recipes (gfa_paint). slag and crust are repainted by gfa_brush as broad zones (broad_zones()): their
    planes / parts / brush / edge terms are replaced by a few broad value planes per plate and tapered brush
    strokes on each plate's own edges; base / shadow / light, gradient, AO and cavity still come from here."""
    import gfa_paint as P
    maw = tuple(b.glob_c)
    # the crust plates: slag darker than the #3A2C24 floor (a dark mass framed by light strokes and hot seams),
    # warming to hot slag toward the maw
    slag = P.zone(base="#231A17", shadow="#0C0908", light="#7A5A48", cavity=0.8, cavity_width=0.01, ao=0.6,
                  ao_range=(0.22, 0.62), gradient={"center": maw, "range": (0.42, 0.14), "color": HOT_SLAG,
                                                   "amount": 0.35})
    # the plate tops and teeth round the maw: cooled crust, a value step above the slag (it frames the glow)
    crust = P.zone(base="#3E2E25", shadow="#140C09", light="#B08A68", cavity=0.8, cavity_width=0.008, ao=0.5,
                   gradient={"center": maw, "range": (0.30, 0.16), "color": "#7A2E14", "amount": 0.45})
    # the molten core: glows through the seams (deep red low down, orange higher), hottest in the breach and throat
    core = P.zone(base="#5A1A08", shadow="#2A0A04", light="#C8400C", planes=0.04, parts=0.0, brush=0.04, edge=0.0,
                  cavity=0.0, ao=0.0,
                  emit={"color": "#4A1204", "hot": "#9A2A08", "core": "#E0600F", "mode": "radial", "center": maw,
                        "radius": 0.75, "base_mix": 0.1})
    # the glob: the Slag King's molten ramp; a small pale-hot (not gold) spot right on top
    molten = P.zone(base="#FF6B1A", shadow="#7A1E05", light="#FF9A4A", planes=0.03, parts=0.0, brush=0.05, edge=0.0,
                    cavity=0.0, ao=0.0,
                    emit={"color": "#C23C0C", "hot": "#FF6B1A", "core": "#FFC88A", "mode": "radial",
                          "center": tuple(b.glob_top), "radius": 0.22, "base_mix": 0.15})
    # the overflow tongue: hot where it leaves the maw, cooling toward the drip
    spill = P.zone(base="#E0500F", shadow="#7A1E05", light="#FF9A4A", planes=0.03, parts=0.0, brush=0.05, edge=0.0,
                   cavity=0.0, ao=0.0,
                   emit={"color": "#7A2006", "hot": "#D2480E", "core": "#FF7A22", "mode": "plane", "axis": (0, 0, -1),
                         "range": (-LIP_Z - 0.02, -0.30), "base_mix": 0.1})
    obsidian = P.faction_zone("unmade", "obsidian", planes=0.16, parts=0.1, edge=1.0, edge_width=0.01,
                              edge_breakup=0.25, cavity=0.6, light="#6A6680")
    under = P.zone(base="#1A1310", shadow="#0C0908", light="#2E211C", edge=0.0, cavity=0.0, ao=0.3)
    return {"slag": slag, "crust": crust, "core": core, "molten": molten, "spill": spill, "obsidian": obsidian,
            "under": under}


# Cooling crust on the molten: dark crust plates (voronoi cells) with glowing cracks between them, so only the
# glob's centre burns hot and the maw reads as molten slag, not an orange ball. gfa_paint has no such pass and stays
# unchanged (other assets build with it): crust_pass() wraps gfa_paint.paint for this build's one paint call, and
# gfa_brush.paint_asset calls gfa_paint.paint, so the broad zones and the decals still paint on top as usual.
CRUST = {  # zone -> (cell frequency /m, share of cells crusted, hot centre (point, clear radius, full radius), z floor)
    "molten": (10.0, 0.7, "glob_top", 0.115, 0.165, None),  # ~10 cm plates in a band round the glob's base
    "spill": (10.0, 0.6, None, 0.0, 0.0, None),
    "core": (8.5, 0.72, None, 0.0, 0.0, LIP_Z - 0.07),
}
CRUST_COLOR = "#2A1510"


@contextmanager
def crust_pass(b):
    import numpy as np
    import gfa_paint as P
    orig = P.paint

    def paint(maps, zones_order, recipes_, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes_, dist_convex, dist_concave, decals, seed)
        for zname, (freq, share, hot, r0, r1, zmin) in CRUST.items():
            m = np.nonzero(maps["zone"] == zones_order.index(zname))[0]
            if not len(m):
                continue
            p = maps["pos"][m]
            _, edge, cid = P.voronoi(p, freq, seed=seed + 900 + len(zname))
            k = P.smoothstep(0.06, 0.13, edge) * (cid < share)
            if hot:
                c = np.asarray(getattr(b, hot), dtype=np.float32)
                d = np.linalg.norm((p - c)[:, :2], axis=1)
                k = k * P.smoothstep(r0, r1, d)
            if zmin is not None:
                k = k * P.smoothstep(zmin, zmin + 0.04, p[:, 2])
            if zname == "spill":
                k = k * P.smoothstep(LIP_Z - 0.02, 0.36, p[:, 2])          # the tongue cools toward its tip
            k = k.astype(np.float32)
            base[m] = P.mix(base[m], P.hex3(CRUST_COLOR), k * 0.9)
            emis[m] = emis[m] * (1.0 - 0.92 * k)[:, None]
        return base, emis

    P.paint = paint
    try:
        yield
    finally:
        P.paint = orig


def broad_zones():
    import gfa_brush as BR
    return {"slag": BR.broad(levels=(-0.4, -0.18, 0.04, 0.2), wobble=0.25, wobble_freq=6.0, inner=0.07, inner_freq=4.5,
                             stroke=0.85, stroke_width=0.011, stroke_len=0.12, stroke_cover=0.55, glint=0.35),
            "crust": BR.broad(levels=(-0.25, -0.06, 0.1, 0.26), wobble=0.25, wobble_freq=7.0, inner=0.05, stroke=1.0,
                              stroke_width=0.012, stroke_len=0.1, stroke_cover=0.65, glint=0.5)}


def _frame_on(fn, u, v):
    """Decal frame on a plate: origin on the surface, +Z = the plate's outward normal, +Y = up the plate."""
    p = fn(u, v)
    n = fn_normal(fn, u, v)
    up = fn(u, min(1.0, v + 0.05)) - fn(u, max(0.0, v - 0.05))
    return _frame_zy(p, n, up)


def _frame_zy(origin, z_axis, y_hint):
    z = Vector(z_axis).normalized()
    y = Vector(y_hint) - z * Vector(y_hint).dot(z)
    y.normalize()
    x = y.cross(z)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def decals(b):
    """Few, bold marks (a crack web turns to speckle at game size): a warm heat spill painted along every seam
    (the seams read as glowing cracks, not thin lines), and two teal Unmade fissures - one radiating from the
    shards' roots, one on the right flank - each with a burnt dark lip and a teal glow spill."""
    import gfa_paint as P
    out = []
    n = len(PLATES)
    for i in range(n):
        fa, fb = plate_fn(i), plate_fn((i + 1) % n)
        pts = [(fa(1.0, v) + fb(0.0, v)) * 0.5 for v in (0.03, 0.2, 0.4, 0.6, 0.8, 0.97)]
        mid = pts[2]
        th = math.atan2(mid.y - center(mid.z)[1], mid.x - center(mid.z)[0])
        _, nrm = surf(th, mid.z)
        fr = _frame_zy(mid, nrm, pts[-1] - pts[0])
        inv = fr.inverted()
        line = [tuple((inv @ p)[:2]) for p in pts]
        out.append(P.decal_lines([line], fr, 0.001, zones=["slag", "crust"], color=None, rim=HOT_SLAG,
                                 rim_width=0.026, emit={"color": "#2A0A03", "core": "#2A0A03"}, depth=(-0.25, 0.25),
                                 facing=-0.25))
    rng = random.Random(SEED + 100)
    for pi, u, v, direction, length in ((2, 0.72, 0.42, -115.0, 0.24), (5, 0.42, 0.40, -70.0, 0.22)):
        fn = plate_fn(pi)
        fr = _frame_on(fn, u, v)
        lines = M.crack_lines(rng, start=(0.0, 0.05), direction=direction, length=length, step=0.03, jag=0.45,
                              branches=1, branch_len=0.45, depth=1)
        out.append(P.decal_lines(lines, fr, 0.001, zones=["slag"], color=None, rim="#123C38", rim_width=0.042,
                                 emit={"color": "#0B2F2B", "core": "#0B2F2B"}, depth=(-0.12, 0.12), facing=0.0))
        out.append(P.decal_lines(lines, fr, 0.017, zones=["slag"], color="#2FBFA8", rim="#07060A", rim_width=0.036,
                                 emit=TEAL, depth=(-0.12, 0.12), facing=0.1))
    return out


# ---- clips ----------------------------------------------------------------------------------------------------------

def pulse(t, t0, w):
    d = ((t - t0 + 0.5) % 1.0) - 0.5
    return math.exp(-(d / w) ** 2)


def mat_basis(tr):
    loc = Vector(tr.get("loc", (0.0, 0.0, 0.0)))
    rot = Euler([math.radians(x) for x in tr.get("rot", (0.0, 0.0, 0.0))], "XYZ").to_matrix().to_4x4()
    s = tr.get("scale", 1.0)
    s = (s, s, s) if isinstance(s, (int, float)) else tuple(s)
    return Matrix.Translation(loc) @ rot @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))


def basis_tr(m):
    loc, q, sc = m.decompose()
    return {"loc": tuple(loc), "rot": tuple(math.degrees(x) for x in q.to_euler("XYZ")), "scale": tuple(sc)}


def make_clips(arm, b, skirt):
    """The six clips. Bone-local frame (GF_Swarm_v1): X = the creature's left, Y = up, Z = forward; +X rot pitches
    nose-down, +Y yaws left, +Z rolls the left side up."""
    sin, cos, tau = math.sin, math.cos, 2 * math.pi
    piv = Vector((0.0, 0.0, BODY_Z))
    loc_pts = [Vector((p.x - piv.x, p.z - piv.z, -(p.y - piv.y))) for p in skirt]     # skirt in body-local axes

    def body(rot=(0.0, 0.0, 0.0), sq=1.0, wide=1.0, up=0.0):
        """Body pose (squash sq, spread wide) with the lowest skirt point kept on the ground (+ up: a hop)."""
        tr = {"rot": rot, "scale": (wide, sq, wide), "loc": (0.0, 0.0, 0.0)}
        m = mat_basis(tr)
        low = min((m @ p).y for p in loc_pts) + BODY_Z
        tr["loc"] = (0.0, -low + up, 0.0)
        return tr

    def plant(pose, own=None):
        """legs_a / legs_b share the body pivot: basis = body^-1 @ own motion, so the toes stay planted."""
        inv = mat_basis(pose.get("body", {})).inverted()
        for g in ("legs_a", "legs_b"):
            pose[g] = basis_tr(inv @ mat_basis((own or {}).get(g, {})))
        return pose

    def idle(t):
        w = tau * t
        bub = pulse(t, 0.62, 0.05)
        p = {"body": body(rot=(1.2 * sin(w), 0.0, 0.8 * sin(w + 1.0)), sq=1.0 + 0.018 * sin(w), wide=1.0 - 0.009 * sin(w)),
             "head": {"scale": (1.0 + 0.04 * sin(2 * w) + 0.08 * bub, 1.0 + 0.07 * sin(2 * w) + 0.22 * bub,
                                1.0 + 0.04 * sin(2 * w) + 0.08 * bub), "loc": (0.0, 0.006 * sin(2 * w) + 0.014 * bub, 0.0)},
             "tail": {"rot": (3.0 * sin(w - 0.8), 0.0, 2.0 * sin(w))}}
        return plant(p)

    S, LIFT = 0.075, 0.07

    def move(t):
        w = tau * t
        la, lb = max(0.0, sin(w)), max(0.0, -sin(w))
        roll = 9.0 * sin(w)
        p = {"body": body(rot=(4.0 + 1.5 * sin(2 * w), 3.0 * sin(w), roll), sq=1.0 - 0.02 * cos(2 * w),
                          up=0.018 * (1 - cos(2 * w)) / 2),
             "head": {"rot": (2.0 * sin(2 * w), 0.0, -5.0 * sin(w - 0.6)), "scale": 1.0 + 0.04 * sin(2 * w + 1.0)},
             "tail": {"rot": (5.0 * sin(2 * w + 0.5), 0.0, 3.0 * sin(w))}}
        return plant(p, {"legs_a": {"loc": (0.0, LIFT * la, -S * cos(w)), "rot": (-8.0 * la, 0.0, 0.0)},
                         "legs_b": {"loc": (0.0, LIFT * lb, S * cos(w)), "rot": (-8.0 * lb, 0.0, 0.0)}})

    # one-shots: the toes ride with the body (a rearing cone lifts its front toe; planted toes would hang in the
    # air under the lifted skirt). Only idle and move plant them.
    rest = {}
    dip = {"body": body(rot=(5.0, 0.0, 0.0), sq=0.93, wide=1.04), "head": {"scale": 0.88, "loc": (0, -0.01, 0)},
           "tail": {"rot": (4.0, 0.0, 0.0)}}
    loaded = {"body": body(rot=(-10.0, 0.0, -2.0), sq=0.86, wide=1.07),
              "head": {"scale": (1.3, 1.75, 1.3), "loc": (0.0, 0.06, 0.02)}, "tail": {"rot": (-16.0, 0.0, -5.0)}}
    loaded2 = {"body": body(rot=(-12.0, 0.0, -3.0), sq=0.84, wide=1.08),
               "head": {"scale": (1.38, 1.95, 1.38), "loc": (0.0, 0.08, 0.02)}, "tail": {"rot": (-20.0, 0.0, -6.0)}}
    fire = {"body": body(rot=(-6.0, 0.0, 0.0), sq=1.13, wide=0.94),
            "head": {"scale": (1.05, 1.45, 1.05), "loc": (0.0, 0.34, 0.12)}, "tail": {"rot": (-6.0, 0.0, 0.0)}}
    away = {"body": body(rot=(6.0, 0.0, 1.0), sq=1.05, wide=0.97),
            "head": {"scale": 0.02, "loc": (0.0, 0.8, 0.3)}, "tail": {"rot": (8.0, 0.0, 2.0)}}
    recoil = {"body": body(rot=(8.0, 0.0, 2.0), sq=0.9, wide=1.05),
              "head": {"scale": 0.02, "loc": (0.0, -0.03, 0.0)}, "tail": {"rot": (12.0, 0.0, 4.0)}}
    refill = {"body": body(rot=(2.0, 0.0, 0.0), sq=0.98, wide=1.01),
              "head": {"scale": 0.55, "loc": (0.0, -0.02, 0.0)}, "tail": {"rot": (2.0, 0.0, 0.0)}}
    flinch = {"body": body(rot=(-9.0, 5.0, -7.0), sq=0.94, wide=1.03),
              "head": {"scale": (1.15, 0.8, 1.15)}, "tail": {"rot": (-12.0, 0.0, 8.0)}}
    settle = {"body": body(rot=(3.0, -2.0, 2.0), sq=1.02), "head": {"scale": 1.04}, "tail": {"rot": (4.0, 0.0, -3.0)}}
    swell = {"body": body(rot=(-5.0, 0.0, 3.0), sq=1.06, wide=1.05), "head": {"scale": (1.3, 1.7, 1.3), "loc": (0, 0.04, 0)},
             "tail": {"rot": (-8.0, 0.0, 0.0)}}
    bulge = {"body": body(rot=(-7.0, 0.0, 4.0), sq=1.08, wide=1.08), "head": {"scale": (1.7, 2.5, 1.7), "loc": (0, 0.08, 0)},
             "tail": {"rot": (-14.0, 0.0, -4.0), "loc": (0.0, 0.02, -0.02)}}
    burst = {"body": body(rot=(0.0, 0.0, 6.0), sq=0.96, wide=1.1), "head": {"scale": 0.02, "loc": (0, 0.1, 0)},
             "tail": {"rot": (-50.0, 15.0, 30.0), "loc": (0.05, 0.12, -0.12)}}
    slump = {"body": body(rot=(9.0, 0.0, 12.0), sq=0.55, wide=1.18), "head": {"scale": 0.02},
             "tail": {"rot": (-100.0, 30.0, 70.0), "loc": (0.12, -0.12, -0.3), "scale": 0.8}}
    collapse = {"body": body(rot=(10.0, 0.0, 14.0), sq=0.3, wide=1.25), "head": {"scale": 0.02},
                "tail": {"rot": (-110.0, 30.0, 80.0), "loc": (0.14, -0.25, -0.35), "scale": 0.4}}
    gone = {"body": body(rot=(10.0, 0.0, 14.0), sq=0.02, wide=0.02), "head": {"scale": 0.02}, "tail": {"scale": 0.02}}
    RIG.cycle_clip(arm, KEY, "idle@loop", MOTION["idle_frames"], idle)
    RIG.cycle_clip(arm, KEY, "move@loop", MOTION["move_frames"], move)
    RIG.keyed_clip(arm, KEY, "windup", [(0, rest), (5, dip), (12, loaded), (18, loaded2)])
    RIG.keyed_clip(arm, KEY, "attack", [(0, loaded2), (2, fire), (4, away), (7, recoil), (11, refill), (18, rest)])
    RIG.keyed_clip(arm, KEY, "hit", [(0, rest), (2, flinch), (5, settle), (10, rest)])
    RIG.keyed_clip(arm, KEY, "death", [(0, rest), (4, swell), (8, bulge), (10, burst), (16, slump), (22, collapse),
                                       (27, gone), (28, gone)])
    return [RIG.clip_name(KEY, c) for c in SPEC.ENEMY_CLIPS_REQUIRED]


MOTION = {"idle_frames": 48, "move_frames": 14, "move_cycle_m": 1.0, "lob_release_frame": 2}
KEY_FRAMES = {"idle@loop": [0, 14, 29, 36], "move@loop": [0, 4, 7, 11], "windup": [0, 5, 12, 18],
              "attack": [0, 2, 4, 7, 11, 18], "hit": [0, 2, 5, 10], "death": [0, 4, 8, 10, 16, 22, 27]}
GAME_POSES = [("rest", None, 0), ("move", "move@loop", 4), ("wind-up (loaded)", "windup", 18),
              ("attack (lob)", "attack", 2), ("hit", "hit", 2), ("death (burst)", "death", 10)]


# ---- review ----------------------------------------------------------------------------------------------------------

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
    bm = M.box((abs(p1[0] - p0[0]) + thick, abs(p1[1] - p0[1]) + thick, abs(p1[2] - p0[2]) + thick))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = [(a + c) / 2 for a, c in zip(p0, p1)]
    me.materials.append(_emit_mat("GUIDE_" + hexc, hexc))
    return ob


def size_compare(mesh, work, height, width):
    """Side view (orthographic, from the creature's left) beside the 2.2 m hero mannequin: the hero's waist line
    (1.1 m, the swarm ceiling) and the slagspitter's own top."""
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (0.0, 1.25, 0.0)
    bpy.context.view_layer.update()
    bars = [guide_bar("GUIDE_waist", (0.9, -0.8, 1.1), (0.9, 1.8, 1.1), 0.012, "#D9CFA6"),
            guide_bar("GUIDE_top", (0.9, -0.8, height), (0.9, 0.75, height), 0.008, "#FF8A30"),
            guide_bar("GUIDE_ground", (0.9, -0.8, 0.0), (0.9, 1.8, 0.0), 0.01, "#6B5A50")]
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh, man], ink=0.008, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (0.0, 0.5, 1.12), (1.0, 0.0, 0.0), 2.6)
        p = R.render(scene, os.path.join(work, "%s_size_side.png" % KEY), 420, 420)
    C.remove_objects([man] + bars)
    return p


def clip_strips(arm, mesh, work, size=200):
    scene = bpy.context.scene
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    pts = R._points([mesh])
    d = R.CREATURE_VIEWS["34_front"]
    c, w, h = R.frame(pts, d)
    ext = max(w, h) * 1.5
    c = c + Vector((0.0, 0.0, 0.1))
    R.setup_cycles(scene, 10)
    out = []
    with R.toon_preview([mesh], ink=0.005):
        for clip, frames in KEY_FRAMES.items():
            track = RIG.clip_name(KEY, clip)
            for f in frames:
                RIG.pose_at(arm, track, f)
                R.aim(scene, c, d, ext)
                p = os.path.join(work, "%s_clip_%s_f%02d.png" % (KEY, clip.replace("@", "_"), f))
                out.append((clip, f, R.render(scene, p, size)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def close_ups(arm, mesh, work, size=700):
    """Two big 3/4 front toon renders at one scale: the rest pose and the loaded wind-up."""
    scene = bpy.context.scene
    RIG.pose_at(arm, RIG.clip_name(KEY, "windup"), 18)
    pts = R._points([mesh])
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    d = Vector((0.62, -0.72, 0.42))
    c, w, h = R.frame(pts, d)
    R.setup_cycles(scene, 16)
    out = []
    with R.toon_preview([mesh], ink=0.006):
        for label, clip, f in (("rest", None, 0), ("wind-up, loaded (f18)", "windup", 18)):
            if clip:
                RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
            else:
                RIG.unmute_none(arm)
            bpy.context.view_layer.update()
            R.aim(scene, c, d, max(w, h) * 1.12)
            out.append((label, R.render(scene, os.path.join(work, "%s_close_%s.png" % (KEY, clip or "rest")), size)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def ingame_poses(arm, mesh, work, view_height=SPEC.GAME_VIEW_HEIGHTS[0], px=80):
    """Key poses through the game camera at true 1080p pixel size (no mannequin)."""
    out = []
    for label, clip, f in GAME_POSES:
        if clip:
            RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
        else:
            RIG.unmute_none(arm)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_pose_%s" % (KEY, label.split()[0].replace("-", "")), px=px,
                     view_height=view_height, target=(0.0, -0.05, 0.4), silhouette_too=False, ink=0.01)
        out.append((label, r["color"]))
    RIG.unmute_none(arm)
    bpy.context.scene.frame_set(0)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    return out


def review(arm, mesh, rep, reports, work, tex, notes):
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    out = {}
    turn = R.turnaround([mesh], work, KEY, R.CREATURE_VIEWS, size=400)
    height = rep.get("height_m") or 0.8
    lo, hi = C.world_bounds([mesh])
    size_p = size_compare(mesh, work, height, max(hi.x - lo.x, hi.y - lo.y))
    strips = clip_strips(arm, mesh, work)
    ing = []
    for label, yaw in (("facing the camera", -30.0), ("turned away", 150.0)):
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.35, 0.3, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_%s" % (KEY, "face" if yaw < 0 else "away"), px=160,
                     view_height=SPEC.GAME_VIEW_HEIGHTS[0], mannequin_obj=man, target=(-0.6, 0.0, 0.55))
        C.remove_objects([man])
        ing.append((label, r))
    arm.rotation_euler = (0.0, 0.0, math.radians(-30.0))
    poses = ingame_poses(arm, mesh, work)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    beauty = close_ups(arm, mesh, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Slagspitter  (slagspitter.glb)",
        "subtitle": "The Unmade | Swarm Spire, Cinder Wastes | Lobber | verb LOB: a squat slag cone whose molten glob "
                    "swells out of the maw and is thrown | GF_Swarm_v1",
        "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn.items()]},
            {"label": "Close-up (3/4 front, toon preview): at rest, and loaded at the end of the wind-up", "height": None,
             "images": [{"path": p, "label": lb} for lb, p in beauty]},
            {"label": "Size vs the 2.2 m hero (side; waist line = swarm ceiling) | in-game camera, 55 deg, %.1f px/m, "
                      "TRUE size 1x, then 3x nearest" % ppm,
             "height": None, "images": [{"path": size_p, "label": "side: %.2f m tall = %.2f x hero" % (height, height / 2.2)},
                                        {"path": ing[0][1]["color"], "label": "1x"},
                                        {"path": ing[0][1]["color"], "label": "3x " + ing[0][0], "scale": 3},
                                        {"path": ing[1][1]["color"], "label": "3x " + ing[1][0], "scale": 3}]},
            {"label": "Game-size silhouette (3x) and key poses through the game camera at TRUE pixel size (3x nearest)",
             "height": None,
             "images": [{"path": ing[0][1]["sil"], "label": "silhouette 3x", "scale": 3}]
             + [{"path": p, "label": lb, "scale": 3} for lb, p in poses]},
            {"label": "Clip key frames (3/4 front): idle@loop, move@loop, windup, attack (the lob), hit, death",
             "height": 150, "images": [{"path": p, "label": "%s f%d" % (cl, f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220,
             "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)
    # the clip key-frame sheet on its own, bigger (3/4 front at 260 px + the game-size key poses)
    big = clip_strips(arm, mesh, work, size=260)
    rows = []
    for clip in KEY_FRAMES:
        rows.append({"label": clip, "height": None,
                     "images": [{"path": p, "label": "f%d (%.2fs)" % (f, f / FPS)} for cl, f, p in big if cl == clip]})
    rows.append({"label": "The same key poses through the game camera, TRUE pixel size, 3x nearest", "height": None,
                 "images": [{"path": p, "label": lb, "scale": 3} for lb, p in poses]})
    clips_layout = {"title": "Slagspitter - clip key frames", "subtitle": "GF_Swarm_v1 | %s" % ", ".join(
        c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
        "width": 1600, "sections": rows, "notes": [
            "windup: the cone squats and tilts back to aim while the molten glob (head bone) swells out of the maw; "
            "it ends on the loaded pose (the client time-stretches it).",
            "attack: the cone springs up, the glob leaves the maw on frame %d (attack_origin) and shrinks to nothing - "
            "the engine's projectile takes over - then the cone recoils and the maw refills." % MOTION["lob_release_frame"],
            "death: the glob swells and bursts (engine VFX at fx_core), the obsidian shards blow off, the cone slumps "
            "into a puddle and shrinks away."]}
    out["clips_sheet"] = R.contact_sheet(clips_layout, os.path.join(reports, "%s_clips.png" % KEY), work)
    out.update({"turn": turn, "size": size_p, "ingame": ing, "poses": poses})
    return out


# ---- the full build ---------------------------------------------------------------------------------------------------

def build_full(b, mesh, col, pack, work, size, argv):
    import gfa_export as E
    import gfa_paint as P
    tex_dir = os.path.join(pack, "textures")
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    # the skirt (lowest body vertices) for the clip grounding, before skinning
    body_vg = mesh.vertex_groups["body"].index
    skirt = [v.co.copy() for v in mesh.data.vertices if v.co.z < 0.012
             and any(g.group == body_vg and g.weight > 0 for g in v.groups)]
    import gfa_brush as BR
    with crust_pass(b):
        paint_rep = BR.paint_asset(mesh, KEY, recipes(b), tex_dir, size=size, decals=decals(b), broad=broad_zones(),
                                   ao_distance=0.06, ao_samples=16, edge_min_angle=30.0, margin_px=3, uv_angle=66.0,
                                   seed=SEED, uv_zone_scale={"under": 0.2, "core": 0.75})
    arm = RIG.build_swarm_rig(b.pivots(), col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in b.sockets():
        RIG.add_socket(arm, bone, name, p)
    make_clips(arm, b, skirt)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    extra = {
        "content_key": KEY,
        "faction": "unmade",
        "move_cycle_m": MOTION["move_cycle_m"],
        "move_note": "a rocking tripod waddle: play move@loop at speed / move_cycle_m cycles per second (row speed 2.6 m/s "
                     "-> 2.6 cycles/s)",
        "lob": {"windup": "ends on the loaded pose (the glob swollen out of the maw); time-stretch it into the telegraph",
                "attack_release_frame": MOTION["lob_release_frame"],
                "attack_origin": "on the head bone, on top of the glob: spawn the lobbed slag there at the release frame",
                "note": "Lobber(windup 1.1 s): e.g. play windup over the first ~0.5 s of the telegraph, then attack, so "
                        "the thrown glob flies for the rest of it and lands with the damage"},
        "bones": {"body": "the cone, crust plates, teeth, core and the overflow tongue",
                  "head": "the molten glob in the maw (swells, is thrown, refills)",
                  "legs_a": "the two left toes", "legs_b": "the big right toe", "tail": "the obsidian back shards",
                  "root": "hops and the death sink"},
        "content_row": ROW,
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
        "skin": skin,
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.log("clips", RIG.clips_report(arm))
    C.write_json(os.path.join(reports, "%s_build_report.json" % KEY),
                 {"export": {k: rep[k] for k in rep if k not in ("nodes",)}, "paint": paint_rep, "skin": skin,
                  "parts": b.parts, "tris_blender": b.tris, "clips": RIG.clips_report(arm)})
    if not C.flag(argv, "--no-review"):
        tex = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        RIG.unmute_none(arm)
        bpy.context.scene.frame_set(0)
        bpy.context.view_layer.update()
        lo, hi = C.world_bounds([mesh])
        notes = [
            "%s tris (swarm budget 600-1500) | textures %s | %.2f m tall (%.2f x hero), footprint %.2f x %.2f m "
            "(collider 0.48 m -> 1.06-1.44 m) | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"],
                rep["height_m"] / 2.2, hi.x - lo.x, hi.y - lo.y, ", ".join(sorted(rep["sockets"]))),
            "Clips: %s" % ", ".join(c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
            "head bone = the molten glob (swells in windup, thrown on attack f%d, bursts in death). move_cycle_m %.2f. "
            "Status: %s." % (MOTION["lob_release_frame"], MOTION["move_cycle_m"], SPEC.STATUS_AI_FINAL),
        ]
        review(arm, mesh, rep, reports, work, tex, notes)
    write_status()
    C.log("DONE", KEY)


def write_status():
    outs = ["assets/models/enemies/%s.glb" % KEY, "assets/models/enemies/%s.meta.json" % KEY,
            "art/enemies/%s/source/%s.blend" % (KEY, KEY), "art/enemies/%s/textures/%s_basecolor.png" % (KEY, KEY),
            "art/enemies/%s/textures/%s_emissive.png" % (KEY, KEY), "art/enemies/%s/reports/%s_review.png" % (KEY, KEY),
            "art/enemies/%s/reports/%s_clips.png" % (KEY, KEY)]
    for extra in ("%s_crowd.png" % KEY, "%s_crowd_review.png" % KEY):
        if os.path.exists(os.path.join(C.pack_dir(KIND, KEY), "reports", extra)):
            outs.append("art/enemies/%s/reports/%s" % (KEY, extra))
    C.write_pack_status(KIND, KEY, outs,
                        "Built from code by tools/blender/gf_assets/enemies/slagspitter.py and reviewed by the same script "
                        "with --crowd (40 slagspitters among the clinker family through the game camera).",
                        tier=TIER, extra={"skeleton": SPEC.SWARM_SKELETON, "faction": "unmade"})


# ---- crowd review (imports the SHIPPED GLBs) -----------------------------------------------------------------------------

CLINKERS = ("clinker", "clinker_v1", "clinker_v2", "clinker_v3")


def import_glb(key):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=C.model_path("enemy", key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    # the skinned creature mesh (the glTF importer also adds an "Icosphere" bone-display helper mesh)
    mesh = next(o for o in new if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers))
    for o in new:
        if o.type == "MESH" and o is not mesh:
            o.hide_render = True
    arm.name, mesh.name = key + "_ARM", key + "_MESH"
    acts = {}
    for c in SPEC.ENEMY_CLIPS_REQUIRED:
        act = bpy.data.actions.get("%s_%s" % (key, c))
        if act is None:
            raise RuntimeError("%s.glb has no clip %s_%s" % (key, key, c))
        act.use_fake_user = True
        acts[c] = act
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    meta = C.read_json(os.path.splitext(C.model_path("enemy", key))[0] + ".meta.json")
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts, "meta": meta}


def spawn(v, loc, yaw, clip=None, frame=0.0):
    col = bpy.context.scene.collection
    a2 = v["arm"].copy()
    col.objects.link(a2)
    a2.animation_data_clear()
    m2 = v["mesh"].copy()
    m2.data = v["mesh"].data.copy()
    col.objects.link(m2)
    m2.parent = a2
    m2.matrix_parent_inverse = v["mesh"].matrix_parent_inverse.copy()
    for mod in m2.modifiers:
        if mod.type == "ARMATURE":
            mod.object = a2
    a2.location = loc
    a2.rotation_euler = (0.0, 0.0, yaw)
    for pb in a2.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    if clip:
        a2.pose.apply_pose_from_action(v["acts"][clip], evaluation_time=frame)
    return a2, m2


def face_yaw(frm, to):
    d = Vector(to) - Vector(frm)
    return math.atan2(d.x, -d.y)


def game_render(objs, flat, path, w, h, target, sil_path=None, ink=0.012, samples=16,
                view_h=SPEC.GAME_VIEW_HEIGHTS[0]):
    import gfa_boss as B
    return B.ingame_frame(objs, path, w=w, h=h, view_height=view_h, target=target, ink=ink, samples=samples,
                          silhouette_path=sil_path, extra_flat=flat)["color"]


def clear_copies(objs):
    meshes = [o for o in objs if o.type == "MESH"]
    arms = [o for o in objs if o.type == "ARMATURE"]
    C.remove_objects(meshes)
    for o in arms:
        bpy.data.objects.remove(o)


def upscale(src, dst, k):
    import numpy as np
    img = bpy.data.images.load(src, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    big = px.reshape(h, w, 4).repeat(k, 0).repeat(k, 1)
    o = bpy.data.images.new("gfa_up", w * k, h * k, alpha=False)
    o.pixels.foreach_set(big.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(img)
    bpy.data.images.remove(o)
    return dst


def crowd_main():
    """40 slagspitters hanging back at lob range among 24 clinkers (all four looks) swarming two heroes, through the
    game camera at TRUE 1080p pixel size; plus a lineup (slagspitter, the four clinkers, the hero) at 1x and 3x."""
    C.reset_scene(fps=FPS)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "crowd"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    ss = import_glb(KEY)
    cl = [import_glb(k) for k in CLINKERS]
    for i, v in enumerate([ss] + cl):
        v["arm"].location = (200.0 + 5 * i, 200.0, 0.0)
    bpy.context.view_layer.update()
    out = {}
    # 1. lineup through the game camera
    made = []
    made += spawn(ss, (0.0, 0.0, 0.0), math.radians(-20))
    for i, v in enumerate(cl):
        made += spawn(v, (1.1 + 0.85 * i, 0.15, 0.0), math.radians(-25))
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-1.25, 0.2, 0.0)
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    out["lineup"] = game_render(meshes + [man], {man.name: R.MANNEQUIN}, os.path.join(work, "lineup_1x.png"), 290, 110,
                                (1.0, 0.1, 0.45), ink=0.01)
    clear_copies(made)
    C.remove_objects([man])
    # 2. the horde: two heroes, clinkers swarming close, slagspitters ringed at lob range (keep_distance 7 m)
    rng = random.Random(9)
    heroes = [Vector((-0.8, 0.9, 0.0)), Vector((0.9, 1.4, 0.0))]
    mans = []
    for hp, aim in zip(heroes, ((0.4, -0.9, 0.0), (0.7, 0.7, 0.0))):
        m = R.mannequin(aim_dir=aim)
        m.location = hp
        mans.append(m)
    hc = (heroes[0] + heroes[1]) / 2
    spit_pts, clink_pts = [], []
    tries = 0
    while len(spit_pts) < 40 and tries < 50000:
        tries += 1
        r = rng.uniform(3.2, 8.2)
        ang = rng.uniform(0.0, 2 * math.pi)
        p = hc + Vector((math.cos(ang) * r * 1.2, math.sin(ang) * r * 0.95, 0.0))
        if p.y < hc.y - 6.2 or p.y > hc.y + 7.8 or abs(p.x - hc.x) > 9.0:
            continue
        if any((p - q).length < 1.2 for q in spit_pts):
            continue
        spit_pts.append(p)
    tries = 0
    while len(clink_pts) < 24 and tries < 50000:
        tries += 1
        c = heroes[rng.randrange(2)]
        r = rng.uniform(0.9, 3.4)
        ang = rng.uniform(0, 2 * math.pi)
        p = c + Vector((math.cos(ang) * r, math.sin(ang) * r, 0.0))
        if any((p - q).length < 0.7 for q in clink_pts) or any((p - q).length < 1.0 for q in spit_pts) \
                or any((p - h).length < 0.85 for h in heroes):
            continue
        clink_pts.append(p)
    made, phases = [], []
    for p in spit_pts:
        tgt = min(heroes, key=lambda h: (h - p).length)
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-20, 20))
        u = rng.random()
        if u < 0.45:
            clip, f = "idle@loop", rng.uniform(0, MOTION["idle_frames"])
        elif u < 0.7:
            clip, f = "move@loop", rng.uniform(0, MOTION["move_frames"])
        elif u < 0.9:
            clip, f = "windup", 18.0
        else:
            clip, f = "attack", 2.0
        phases.append(clip)
        made += spawn(ss, p, yaw, clip, f)
    for i, p in enumerate(clink_pts):
        v = cl[i % 4]
        tgt = min(heroes, key=lambda h: (h - p).length)
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-25, 25))
        clip, f = ("move@loop", rng.uniform(0, 10)) if rng.random() < 0.75 else ("windup", 15.0)
        made += spawn(v, p, yaw, clip, f)
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    tgt = (hc.x, hc.y + 0.6, 0.3)
    out["crowd"] = game_render(meshes + mans, flat, os.path.join(work, "crowd_1x.png"), 900, 700, tgt,
                               sil_path=os.path.join(work, "crowd_1x_sil.png"))
    out["crowd_sil"] = os.path.join(work, "crowd_1x_sil.png")
    out["crowd28"] = game_render(meshes + mans, flat, os.path.join(work, "crowd_1x_28.png"), 710, 550, tgt,
                                 view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    clear_copies(made)
    C.remove_objects(mans)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = upscale(out["crowd"], os.path.join(work, "crowd_2x.png"), 2)
    shutil.copyfile(crowd2x, os.path.join(reports, "%s_crowd.png" % KEY))
    counts = {c: phases.count(c) for c in set(phases)}
    sections = [
        {"label": "Lineup through the game camera (55 deg, %.1f px/m): slagspitter, the four clinker looks, the 2.2 m hero - "
                  "1x, then 3x nearest" % (SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]), "height": None,
         "images": [{"path": out["lineup"], "label": "1x"}, {"path": out["lineup"], "label": "3x", "scale": 3}]},
        {"label": "HORDE READ: 40 slagspitters (%s) ringed at lob range round two heroes, 24 clinkers swarming them - "
                  "TRUE 1080p pixel size (1x)" % ", ".join("%d %s" % (n, c) for c, n in sorted(counts.items(), key=lambda t: -t[1])),
         "height": None, "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px)"},
                                    {"path": out["crowd_sil"], "label": "1x silhouette"}]},
        {"label": "The four-player view (28 m = 1080 px), 1x", "height": None,
         "images": [{"path": out["crowd28"], "label": "1x"}]},
    ]
    notes = ["slagspitter %s tris, %s m tall; clinkers %s" % (
        ss["meta"]["tris"], ss["meta"]["size_m"], ", ".join("%s %s tris" % (v["key"], v["meta"]["tris"]) for v in cl)),
        "Every copy is posed from the actions inside the shipped GLBs (imported with Blender's glTF importer)."]
    layout = {"title": "Slagspitter horde read  (The Unmade, Cinder Wastes)",
              "subtitle": "40 slagspitters among the clinker family | Lobber, packs of 1-2 | verb LOB | status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "swatches": [{"hex": h, "label": n} for n, h in PALETTE], "notes": notes}
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_crowd_review.png" % KEY), work)
    write_status()
    C.log("DONE crowd", out["sheet"])


# ---- entry ---------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    if C.flag(argv, "--crowd"):
        crowd_main()
        return
    size = C.opt(argv, "--size", 512, int)
    C.reset_scene(fps=FPS)
    col = C.get_collection(KEY)
    b = Build()
    mesh = b.build(col)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work"))
    if C.flag(argv, "--preview"):
        lo, hi = C.world_bounds([mesh])
        C.log("bounds", tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi))
        out = preview(mesh, work)
        C.log("preview", out)
        return
    build_full(b, mesh, col, pack, work, size, argv)


if __name__ == "__main__":
    main()
