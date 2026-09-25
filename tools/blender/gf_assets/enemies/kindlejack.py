"""Kindlejack - the Cinder Wastes bomber (The Unmade): a kindling-stuffed runner that ignites and bursts.
Built, painted, rigged on GF_Swarm_v1, animated, exported and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/kindlejack.py -- [--size 512] [--preview] [--no-review] [--no-crowd]

  --preview    model + rig + clips only, flat zone colours (Workbench): fast silhouette iterations
  --no-review  skip the review sheet (export and validation still run)
  --no-crowd   skip the horde review (it imports the shipped kindlejack + clinker GLBs)
  --crowd-only only re-render the horde review from the shipped GLBs

Content row (content/sheets/enemies.csv): kindlejack, Swarm, P0, hp 26, speed 4.6, radius 0.4, scale 1.0,
contact_damage 0, Bomber(trigger_range 1.6, fuse 0.9, radius 2.2, damage 32), colour #FF7A1A, shape Blob, packs
of 1-2 - "Runs at you. Then it is you who runs." The sim (crates/gf_sim/src/enemies.rs, Bomber) runs at 1.1x
toward the target; inside trigger_range it stops, is PRIMED for fuse x telegraph_time, then despawns in a
radius-2.2 blast drawn by the engine's red-white circle telegraph. So the client needs: move@loop (the sprint),
windup (primed: plant, swell, the fuse burns down; time-stretched to the fuse), attack (the detonation, from the
windup's loaded pose) and death (shot down before it blows: a stagger, a sputtering swell and a smaller burst).

Design (docs/art/ENEMIES.md; the user's enemy pack; must read apart from the clinker and the cinderling):
  * verb RUSH: a tall, forward-leaning SHEAF of split kindling - ten sticks tied at the waist and the neck by two
    jagged obsidian collars, their bottom ends cut at angles and flaring below the waist, their tops running on
    through the neck collar and flaring out into a TORCH HEAD of fourteen stick ends (burnt black at the collar,
    bleached to pale ash above; some splintered, some snapped blunt) around a teal Unmade fire - and a lit FUSE
    rising out of the fire and arcing back over the shoulders to a big white-teal spark: a walking bundle of
    dynamite with a torch for a head. Two long obsidian stilt legs (digitigrade, knee and heel spurs) sprint
    under it; one long stick arm trails straight back, the other is a snapped stump under a pair of obsidian
    shoulder shards (the Unmade's wrong asymmetry). 1.09 m tall, a 0.86 x 0.89 m footprint (the torch head is the
    widest thing on it): it fills its 0.4 m collider, upright where the clinker is low and wide;
  * the sheaf is stuffed with Unmade fire: it bursts out of a torn chest opening (the front stick is snapped) and
    burns in the torch head, where the 55 deg camera looks down into it. The spark hangs BEHIND and above the
    torch head (two lights, not one blob) and streams back like a comet's tail in the sprint. PRIMED, the fire
    blazes up to about twice its size and throbs three times a second (primed@loop): the brightest swarm on screen
    for the 0.9 s fuse;
  * value plan at game size: weathered warm wood (bone warmed toward the row colour, a different value per stick,
    two sticks burnt black, scorched toward the neck; a different hue from the clinker's cream bone clubs and
    value from its violet-black shells) framed by two dark obsidian bands, a pale ash ring of flared stick ends
    (the one light top plane in the Cinder horde, separating the kindlejack from the #3A2C24 floor and from the
    dark teal-slit clinker), dark legs, and teal accents - the chest, the torch-head fire and the spark;
  * palette: THE UNMADE (gfa_spec.FACTIONS): obsidian, slag char, ichor teal #2FBFA8 / #1F8F7E (#8FF2D8 in the
    chest and the fire's heart, #B8FFE8 / #E4FFF6 only in the fire's centre line and the spark), plus the kindling
    wood and its pale ash. The only glow is faction teal; no player colours, no #7CFF6B, no red-white. The row
    colour #FF7A1A appears only as a painted, non-glowing tint (wood, scorch);
  * iterations (art/enemies/kindlejack/README.md): stave-like planks read as a barrel -> round, bent sticks
    through the collars; a dark crown turned to speckle -> few big charred ends with ash tips; a slim first pass
    looked smaller than a clinker in the horde -> girth G = 1.45 (radial sizes only); the sprint was invisible
    from the front -> bounce, roll, twist, fuse whip, leg kick. ART REVIEW FIX (5/10): lost among the clinkers
    (about 540 px at 1x against a clinker's 960, the same dark body and teal slits) -> G 1.9, thicker sticks
    closing the slits, the crown flared into a pale ash torch head, a 2.5 x white-teal spark; the primed state
    read only at detonation -> a teal fire in the torch head that blazes and throbs through primed@loop.

Rig GF_Swarm_v1 (rigid): body = the sheaf (sticks, crown, collars, core, shoulder shards) and both arms; head =
the torch-head fire (pivot at the neck collar's centre: scaling it makes the fire blaze and throb); tail = the
fuse and its spark (pivot at the fuse's root: scaling it burns the fuse down); legs_a = left leg, legs_b = right
leg (pivot on the hip line). The legs are posed in world space (Poser.legs): they ride on the hip point the body
carries but never inherit its lean or swell, so the feet stay on the ground while the bundle inflates.
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Quaternion, Vector  # noqa: E402

import gfa_boss as B  # noqa: E402
import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "kindlejack"
KIND, TIER = "enemy", "swarm"
FPS = 30
SEED = 71
ROW = {"key": "kindlejack", "class": "Swarm", "biome": "cinder_wastes", "hp": 26, "speed": 4.6, "radius": 0.4,
       "scale": 1.0, "contact_damage": 0, "behavior": "Bomber(trigger_range: 1.6, fuse: 0.9, radius: 2.2, damage: 32.0)",
       "color": "#FF7A1A", "shape": "Blob", "pack": "(1, 2)"}
ZONES = ["wood", "char", "crown", "bind", "limb", "core", "heart", "flame", "fuse", "spark"]
MOVE_FRAMES = 12            # one full sprint cycle (two strides) = 0.4 s
IDLE_FRAMES = 42
MOVE_CYCLE_M = 0.9          # metres per move@loop cycle: 4.6 m/s / 0.9 = ~5 cycles (10 strides) per second
PRIMED_FRAMES = 10          # primed@loop: one throb of the fire = 0.33 s, three a second through the 0.9 s fuse
# the torch-head fire (bone `head`) as a multiple of its modelled size: small licks in the bowl while it runs, a
# blaze of about 2 x (x the 1.32 swell) that throbs +-20-26 % while PRIMED
FL_IDLE, FL_MOVE = 0.72, 0.66
FP_W, FP_H, FP_K, FP_KH = 1.95, 2.3, 0.17, 0.22


def mix_hex(a, b, t):
    ca, cb = C.hex_rgb(a), C.hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ca, cb))


# ---- palette ------------------------------------------------------------------------------------------------
WOOD = "#94745A"            # weathered split kindling: faction bone darkened and warmed toward the row colour
WOOD_LIGHT = "#D4B690"
WOOD_SHADOW = "#3E2822"     # red-violet leaning painted shadow
SCORCH = mix_hex("#4E3A30", ROW["color"], 0.22)          # the scorched band under the neck collar
CHAR_EDGE = "#6E625A"       # ash-grey edges on the charred splinters
CHAR = "#231A17"
# the torch head: every crown stick is burnt black where it leaves the neck collar and bleached to pale ash
# over its flared upper two thirds - a pale ring around the fire, the one light top plane in the Cinder horde
ASH = "#CBC2B5"
CROWN_CHAR = "#33261F"      # charred kindling (warm, a step lighter than the slag char)
ASH_R = (0.2, 0.27)         # m from the bundle axis: charred inside, pale ash on the flared ends beyond
OBS_EDGE = "#7D7078"        # knapped obsidian edge light (the clinker's scute edge family)
CORD = "#A8916E"
SPILL_TEAL = "#5E9C90"      # teal light painted on the wood beside the chest opening
BURN = "#2E1C14"            # burnt rim of the chest opening
PALETTE = [("wood", WOOD), ("wood light", WOOD_LIGHT), ("scorch", SCORCH), ("char", CHAR), ("crown char", CROWN_CHAR),
           ("ash tips", ASH), ("obsidian", "#1A1720"), ("obsidian edge", OBS_EDGE), ("fuse cord", CORD),
           ("ichor", "#1F8F7E"), ("glow", "#2FBFA8"), ("hot core", "#B8FFE8"), ("row colour (tint only)", ROW["color"])]
ZONE_FLAT = {"wood": WOOD, "char": "#2A201C", "crown": ASH, "bind": "#221E28", "limb": "#1E1A22", "core": "#2FBFA8",
             "heart": "#B8FFE8", "flame": "#2FBFA8", "fuse": CORD, "spark": "#E8FFF6"}
# UV importance (linear texel scale per zone before packing): the sheaf and the torch head get the pixels
UV_SCALE = {"wood": 1.15, "char": 0.9, "crown": 1.1, "bind": 0.95, "limb": 0.8, "core": 0.5, "heart": 0.4,
            "flame": 0.45, "fuse": 0.75, "spark": 0.4}

# ---- the sheaf frame --------------------------------------------------------------------------------------------
LEAN = math.radians(12.0)                                  # the whole sheaf leans into the run
AX = Vector((0.0, -math.sin(LEAN), math.cos(LEAN)))        # bundle axis (up, tipped forward)
LEFT = Vector((1.0, 0.0, 0.0))
FRONT = -(AX.cross(LEFT)).normalized()                     # perpendicular to the axis, pointing forward (-Y)
B0 = Vector((0.0, 0.04, 0.41))                            # the waist collar (s = 0)
BL = 0.42                                                  # waist collar to the neck collar (s = 1)
# girth: every radial size (sheaf, sticks, collars, core, limbs) is scaled by G, the heights are not. The collider
# is radius 0.4 (ENEMIES.md: footprint 2.2-3 x that); a slimmer first pass looked SMALLER than a clinker in the horde
# (the 55 deg camera reads the footprint first). The art review (5/10) still measured it at ~540 px against a
# clinker's ~960 at 1x, so the review fix fills the collider: G 1.45 -> 1.9, thicker sticks, the crown flared out
# into a torch head, a wider stance and a longer trailing arm - a 0.86 x 0.89 m footprint at 1.09 m tall.
# GR rescales the sizes that were hand-placed at G 1.45 (collars, shoulders, arms, shards).
G = 1.9
GR = G / 1.45
STICK_GIRTH = 1.14          # the sticks thicken with the bundle (closes the teal slits between them)
# centre-line radius of the sticks along s: the skirt ends flare, the waist and neck are tied, the belly bulges
STICK_R = [(-0.27, 0.12), (0.0, 0.084), (0.22, 0.096), (0.46, 0.1), (0.72, 0.097), (1.0, 0.082)]
# split-wood cross-sections (unit): irregular polygons, so the facets paint as different planes
PENT = [(1.0, 0.0), (0.33, 0.95), (-0.78, 0.66), (-0.95, -0.38), (0.22, -0.97)]
CHARRED_STICKS = (2, 6)     # two sticks burnt black through: the bundle reads as separate sticks, not staves


def apt(s):
    return B0 + AX * (BL * s)


def radial(theta_deg):
    t = math.radians(theta_deg)
    return (FRONT * math.cos(t) + LEFT * math.sin(t)).normalized()


def rad_at(s):
    k = STICK_R
    if s <= k[0][0]:
        return k[0][1] * G
    for (s0, r0), (s1, r1) in zip(k[:-1], k[1:]):
        if s <= s1:
            t = (s - s0) / (s1 - s0)
            return (r0 + (r1 - r0) * t) * G
    return k[-1][1] * G


def frame_at(origin, z_dir, x_dir):
    z = Vector(z_dir).normalized()
    x = (Vector(x_dir) - z * Vector(x_dir).dot(z)).normalized()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


# ---- the model --------------------------------------------------------------------------------------------------

class Build:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.info = {}

    def sticks(self, a):
        """Ten split sticks around the sheaf (a slight hand-tied twist, bent, the bottom ends cut at angles and
        flaring below the waist collar) and the snapped front stick. The two sticks beside the front bow apart at
        the chest: the torn opening where the teal core bursts out. Two sticks are burnt black through."""
        rng = self.rng
        n = 10
        self.tops = []
        for i in range(n):
            th0 = 19.0 + i * 322.0 / (n - 1) + rng.uniform(-4, 4)
            gap_side = 0.0
            if abs(((th0 + 180) % 360) - 180) < 40:                 # the two sticks flanking the front
                gap_side = 1.0 if ((th0 + 180) % 360) - 180 > 0 else -1.0
            r = rng.uniform(0.034, 0.04) * STICK_GIRTH
            k = rng.uniform(0.96, 1.04)
            s_bot = rng.uniform(-0.27, -0.16)
            ss = [s_bot, 0.0, 0.3, 0.62, 1.0]
            bend = [0.0, 0.0, rng.uniform(-0.011, 0.011), rng.uniform(-0.011, 0.011), 0.0]
            pts = []
            for s_, bd in zip(ss, bend):
                th = th0 + 14.0 * (s_ - 0.5) + gap_side * 8.0 * math.exp(-((s_ - 0.62) / 0.22) ** 2)
                pts.append(apt(s_) + radial(th) * rad_at(s_) * k + radial(th + 90) * bd)
            radii = [r * 0.88, r, r * 1.04, r * 1.02, r * 0.95]
            b = M.tube(pts, radii, profile=PENT, up=radial(th0), scale_xy=[(1.0, 1.1)] * len(pts))
            cut = (radial(th0 + rng.uniform(-70, 70)) * rng.uniform(0.5, 0.9)).normalized()
            for v in b.verts:
                if (v.co - pts[0]).length < r * 1.4:
                    v.co += AX * ((v.co - pts[0]).dot(cut) * 0.7)
            zone = "char" if i in CHARRED_STICKS else "wood"
            a.add(b, zone, bone="body", name="stick%d" % i, shading="flat")
            self.tops.append((th0 + 7.0, k, r * 0.95))
        # the snapped front stick: only the lower half is left, ending in a splintered point at the chest
        th0 = rng.uniform(-4, 4)
        r = 0.037 * STICK_GIRTH
        pts = [apt(s_) + radial(th0 + 14.0 * (s_ - 0.5)) * rad_at(s_) * 1.02 for s_ in (-0.22, 0.0, 0.24)]
        top = apt(0.44) + radial(th0 - 2) * rad_at(0.44) * 1.08
        b = M.tube(pts + [top], [r * 0.9, r, r * 1.02, 0.0], profile=PENT, up=radial(th0),
                   scale_xy=[(1.0, 1.1)] * 4)
        a.add(b, "wood", bone="body", name="stick_snapped", shading="flat")

    def crown(self, a):
        """The TORCH HEAD: every stick runs on through the neck collar and flares out, about 40 deg off the axis
        and bending further out toward the top (a trumpet), so the crown opens into a 0.65 m ring of stick ends
        around the fire - the widest thing on the creature and what the 55 deg camera sees first. Each end is
        burnt black at the collar and bleached to pale ash above (the "crown" zone); some break off in a
        splintered point, some are snapped blunt. Shorter at the front, so the camera looks down into the fire
        and the fuse stands clear behind."""
        rng = self.rng
        self.crown_top = 0.0
        self.crown_r = 0.0
        # four extra splints pushed in through the neck collar fill the torch head to 14 ends
        tops = list(self.tops) + [(th + rng.uniform(-5, 5), 0.97, 0.033 * STICK_GIRTH) for th in (62.0, 170.0, 206.0, 296.0)]
        # the ends are ROUND sticks of mixed thickness (a first pass with broad slats and pale sticks read as a
        # daisy of petals from above): most snapped off blunt and jagged, some splintered to a point, two burnt off
        # short; length, lean and spacing vary stick by stick. A V-shaped flare, about 35 deg off the axis.
        order = rng.sample(range(len(tops)), len(tops))
        pointed, short = set(order[:5]), set(order[5:7])
        for j, (th, k, r) in enumerate(tops):
            front = math.cos(math.radians(th))                     # 1 at the front, -1 at the back
            ln = rng.uniform(0.36, 0.5) * (1.0 - 0.3 * max(0.0, front)) * (0.6 if j in short else 1.0)
            flare = rng.uniform(0.14, 0.2) * (1.0 + 0.12 * max(0.0, front)) * (0.7 if j in short else 1.0)
            thj = th + rng.uniform(-8, 8)
            p0 = apt(0.94) + radial(th) * rad_at(0.94) * k
            p1 = apt(1.0 + ln * 0.45) + radial(th) * (rad_at(1.0) * k + flare * 0.4)
            p2 = apt(1.0 + ln) + radial(thj) * (rad_at(1.0) * k + flare) + radial(thj + 90) * rng.uniform(-0.025, 0.025)
            blunt = j not in pointed                                # snapped off blunt and jagged
            if blunt:
                p2 = p1.lerp(p2, 0.85)
            rr = r * rng.uniform(0.9, 1.2)
            b = M.tube([p0, p1, p2], [rr, rr * 0.95, rr * 0.8 if blunt else 0.0], profile=PENT, up=radial(th),
                       scale_xy=[(1.0, 1.12)] * 3)
            if blunt:
                dn = (p2 - p1).normalized()
                for v in b.verts:
                    if (v.co - p2).length < rr * 1.25:
                        v.co += dn * rng.uniform(-0.025, 0.015)
            a.add(b, "crown", bone="body", name="stick_top%d" % j, shading="flat")
            self.crown_top = max(self.crown_top, p2.z)
            ax_p = apt(0.0) + AX * (p2 - apt(0.0)).dot(AX)
            self.crown_r = max(self.crown_r, (p2 - ax_p).length)

    def collars(self, a):
        """Two cracked obsidian collars binding the sheaf (the Unmade crust growing over the wood), and a pair
        of obsidian shards breaking out of the neck collar over the stump shoulder."""
        for tag, s, r_in, r_out, h, seed in (("waist", 0.0, 0.1, 0.176, 0.05, 3), ("neck", 1.0, 0.098, 0.178, 0.055, 5)):
            ring = M.ring(r_in * GR, r_out * GR, h, sides=8, start_angle=11.0 * seed)
            jr = random.Random(SEED + seed)
            for v in ring.verts:                                   # a jagged crust, not a machined hoop
                if abs(v.co.z) > h * 0.4:
                    v.co.z += math.copysign(jr.uniform(-0.004, 0.012), v.co.z)
            M.noise_displace(ring, 0.009, freq=8.0, seed=SEED + seed)
            M.xform(ring, matrix=frame_at(apt(s), AX, LEFT))
            a.add(ring, "bind", bone="body", name="collar_" + tag, shading="flat")
        rng = random.Random(SEED + 40)
        root = apt(0.96) + radial(92) * 0.152 * GR
        for d, ln, r in (((0.85, 0.25, 0.3), 0.2, 0.05), ((0.6, 0.55, 0.4), 0.15, 0.04), ((0.95, -0.15, 0.1), 0.12, 0.03)):
            sp = M.spike(r, ln, sides=4, base_scale=(1.0, 0.62), rot_offset=rng.uniform(0, 90))
            M.xform(sp, matrix=M.orient(root - Vector(d).normalized() * 0.02, d, (0, 0, 1)))
            a.add(sp, "bind", bone="body", name="shoulder_shard", shading="flat")

    def core(self, a):
        """The teal fire the sheaf is stuffed with: a spindle inside the sticks, bulging out of the chest opening,
        its top a glowing dome inside the crown."""
        # held back a little inside the thicker sticks (0.9 x), so the gaps between them read dark, not as teal
        # slits (the review: "the same dark body and teal slits" as the clinker); only the chest opening glows
        cg = 0.9 * G
        prof = [(0.0, -0.05), (0.045 * cg, 0.02), (0.062 * cg, 0.16), (0.066 * cg, 0.3), (0.052 * cg, 0.38),
                (0.034 * cg, 0.42), (0.0, 0.44)]
        b = M.lathe(prof, sides=8, start_angle=22.5)
        for v in b.verts:
            x, y, z = v.co
            # local frame: x = LEFT, y = -FRONT (the lathe's y is mapped by frame_at below), z = the axis
            if y < -0.02 and 0.17 < z < 0.4:
                v.co.y -= 0.042 * G * math.sin(math.pi * (z - 0.17) / 0.23)   # bulge through the chest opening
        M.xform(b, matrix=frame_at(B0, AX, LEFT))
        a.add(b, "core", bone="body", name="core", shading="smooth")
        self.core_c = apt(0.62) + FRONT * 0.045
        self.core_top = apt(0.44 / BL)

    def legs(self, a):
        """Two long obsidian stilt legs (digitigrade: the knee forward, the ankle back), a spur on each knee and
        heel. The right one is a little heavier."""
        rng = self.rng
        for side, bone, th in ((1, "legs_a", 1.12), (-1, "legs_b", 1.2)):
            hip = Vector((0.1 * side, 0.05, 0.445))
            knee = Vector((0.148 * side, -0.08, 0.27))
            ankle = Vector((0.152 * side, 0.07, 0.09))
            toe = Vector((0.168 * side, -0.075, 0.0))
            b = M.tube([hip, knee, ankle, toe], [0.063 * th, 0.05 * th, 0.037 * th, 0.0], sides=5)
            a.add(b, "limb", bone=bone, name="leg_%s" % ("L" if side > 0 else "R"), shading="flat")
            for p, d, ln, r in ((knee, (0.2 * side, -1.0, 0.55), 0.09, 0.025), (ankle, (0.1 * side, 1.0, 0.25), 0.075, 0.021)):
                sp = M.spike(r * th, ln * th, sides=4, base_scale=(1.0, 0.65), rot_offset=rng.uniform(0, 90))
                M.xform(sp, matrix=M.orient(p, d, (1, 0, 0)))
                a.add(sp, "limb", bone=bone, name="spur", shading="flat")
        self.hip = Vector((0.0, 0.05, 0.43))

    def arms(self, a):
        """The long right arm trails straight back (the RUSH read), three charred twig fingers; the left is a
        snapped stump ending in a charred splinter. Both ride rigidly on `body` since the review fix: `head`
        now carries the torch-head fire and `tail` the fuse (GF_Swarm_v1 has exactly six bones)."""
        sh_r = apt(0.86) + radial(-90) * 0.158 * GR
        el_r = sh_r + Vector((-0.13, 0.18, -0.1))
        wr_r = el_r + Vector((-0.06, 0.24, 0.035))
        mid1 = sh_r.lerp(el_r, 0.5) + Vector((-0.012, 0.0, 0.015))
        mid2 = el_r.lerp(wr_r, 0.5) + Vector((0.01, 0.0, -0.015))
        b = M.tube([sh_r, mid1, el_r, mid2, wr_r], [0.04, 0.037, 0.034, 0.031, 0.027], profile=PENT, up=(0, 0, 1))
        a.add(b, "wood", bone="body", name="arm_R", shading="flat")
        rng = random.Random(SEED + 60)
        for d, ln in (((-0.25, 1.0, 0.45), 0.12), ((0.2, 1.0, 0.05), 0.135), ((-0.5, 0.8, -0.35), 0.1)):
            sp = M.spike(0.026, ln, sides=3, rot_offset=rng.uniform(0, 90))
            M.xform(sp, matrix=M.orient(wr_r - Vector(d).normalized() * 0.01, d, (0, 0, 1)))
            a.add(sp, "char", bone="body", name="finger", shading="flat")
        sh_l = apt(0.84) + radial(90) * 0.158 * GR
        el_l = sh_l + Vector((0.16, 0.13, -0.1))
        b = M.tube([sh_l, el_l], [0.04, 0.036], profile=PENT, up=(0, 0, 1))
        a.add(b, "wood", bone="body", name="stump_L", shading="flat")
        d = (el_l - sh_l).normalized()
        sp = M.spike(0.036, 0.075, sides=4, tip=(0.012, -0.01), rot_offset=20)
        M.xform(sp, matrix=M.orient(el_l - d * 0.004, d, (0, 0, 1)))
        a.add(sp, "char", bone="body", name="stump_break", shading="flat")
        self.shoulders = (sh_l + sh_r) / 2

    def flame(self, a):
        """The Unmade fire in the torch head (bone `head`, pivot at the neck collar's centre): a teardrop heart that
        sways in an S and hooks over at the tip, and four flattened tongues that bulge out of the bowl, rise and
        curl back in with a sideways flick (a triangle section: a lit ridge outside, a flat face to the heart), so
        from the side they read as licking tongues, not as a bouquet of crystals (the first pass, round pointed
        prisms painted white along the axis, did). The heart is the white-teal hot core (its own zone), the tongues
        saturated faction teal, deeper at every tip (gfa_paint radial stops). At rest it only fills the torch
        head's bowl; windup and primed@loop
        scale the bone up about 2 x and throb it, so a PRIMED kindlejack becomes a teal-white blaze wider than the
        torch head - the brightest swarm on screen for its 0.9 s fuse."""
        rng = random.Random(SEED + 90)
        self.flame_c = apt(0.98)
        # the heart: a teardrop (widest low in the bowl), an S-sway and a tip hooked over toward the stump side
        prof = [(0.0, -0.02), (0.06 * GR, 0.035), (0.056 * GR, 0.095), (0.036 * GR, 0.165), (0.014 * GR, 0.235),
                (0.0, 0.29)]
        b = M.lathe(prof, sides=6, start_angle=15.0, cap=False)
        for v in b.verts:
            z = v.co.z
            v.co.x += 0.03 * math.sin(z * 14.0) * min(1.0, z / 0.1) + 0.06 * max(0.0, z - 0.2) / 0.09
            v.co.y += 0.012 * math.sin(z * 26.0 + 1.0)
        M.xform(b, matrix=frame_at(apt(0.95), AX, LEFT))
        a.add(b, "heart", bone="head", name="flame_heart", shading="smooth")
        tri = [(1.0, 0.0), (-0.5, 0.87), (-0.5, -0.87)]
        for i in range(4):
            th = i * 90.0 + 30.0 + rng.uniform(-14, 14)
            out, tan = radial(th), radial(th + 90)
            sw = 1.0 if i % 2 else -1.0                              # neighbours flick opposite ways
            h = rng.uniform(0.17, 0.24)                              # m above the neck collar
            rr = rng.uniform(0.11, 0.14)                             # how far the tongue bulges out
            c0 = apt(0.95)
            pts = [c0 + out * 0.03 + AX * 0.0,
                   c0 + out * rr * 0.8 + AX * (0.04 + h * 0.12) + tan * 0.012 * sw,
                   c0 + out * rr + AX * (0.02 + h * 0.45) - tan * 0.022 * sw,
                   c0 + out * rr * 0.78 + AX * (0.02 + h * 0.78) + tan * 0.03 * sw,
                   c0 + out * rr * 0.42 + AX * (0.02 + h) + tan * 0.06 * sw]      # the tip curls in and flicks
            w = 0.042 * GR
            b = M.tube(pts, [w * 0.55, w, w * 0.85, w * 0.5, 0.0], profile=tri, up=out,
                       scale_xy=[(0.62, 1.0)] * 5)
            a.add(b, "flame", bone="head", name="flame_tongue", shading="smooth")
        self.flame_top = apt(0.95) + AX * 0.29

    def fuse(self, a):
        """The fuse (bone `tail`, pivot at the fuse's root: scaling it burns the fuse down): a cord rising out of the
        fire and arcing back over the shoulders, past the torch head's rim, to a teal-white spark. The spark is the
        kindlejack's own signal in the horde - a 0.14 m white-teal core (7 px at 1x; 2.5 x the first pass in area) in six
        short teal rays. From the 55 deg camera it hangs BEHIND and above the crown (two separate lights), and in the
        sprint the fuse streams back like a comet's tail - the RUSH read from above."""
        base = apt(1.08)
        ctrl = [apt(0.98), base + Vector((0.0, -0.004, 0.07)), base + Vector((-0.006, 0.035, 0.145)),
                base + Vector((-0.018, 0.12, 0.185)), base + Vector((-0.03, 0.235, 0.17)), base + Vector((-0.04, 0.33, 0.115))]
        pts = M.catmull(ctrl, 2)
        n = len(pts)
        radii = [0.03 - 0.008 * i / (n - 1) for i in range(n)]
        b = M.tube(pts, radii, sides=4, twist=120.0)
        a.add(b, "fuse", bone="tail", name="fuse", shading="flat")
        tip = pts[-1] + (pts[-1] - pts[-2]).normalized() * 0.03
        self.fuse_base = base
        self.spark = tip
        s = M.sphere(0.07, 6, 4)
        M.xform(s, loc=tip)
        a.add(s, "spark", bone="tail", name="spark", shading="smooth")
        rng = random.Random(SEED + 80)
        dirs = [(1, 0.2, 0.35), (-1, 0.3, 0.3), (0.2, -1, 0.5), (-0.1, 1, 0.2), (0.3, 0.7, 0.55), (-0.3, -0.4, -0.6)]
        for d in dirs:
            ln = rng.uniform(0.12, 0.15)
            sp = M.spike(0.03, ln, sides=3, cap=False, rot_offset=rng.uniform(0, 90))
            M.xform(sp, matrix=M.orient(tip, d, (0, 0, 1)))
            a.add(sp, "spark", bone="tail", name="spark_ray", shading="flat")

    def build(self, col):
        a = M.Assembly(KEY + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        self.sticks(a)
        self.crown(a)
        self.collars(a)
        self.core(a)
        self.legs(a)
        self.arms(a)
        self.flame(a)
        self.fuse(a)
        self.tris = a.tris()
        self.parts = a.parts
        obj = a.to_object(col)
        C.log("%s mesh: %d tris, %d parts" % (KEY, self.tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def pivots(self):
        return {"root": (0.0, 0.03, 0.0), "body": tuple(apt(0.46)), "head": tuple(self.flame_c),
                "legs_a": tuple(self.hip), "legs_b": tuple(self.hip), "tail": tuple(self.fuse_base)}

    def sockets(self):
        return [("body", "hit_center", tuple(apt(0.5))), ("body", "fx_core", tuple(self.core_c)),
                ("body", "head_top", (0.0, 0.0, 1.3))]

    # -- paint --
    def recipes(self):
        rim = {"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8"}
        proj = lambda s: apt(s).dot(AX)  # noqa: E731
        return {
            # the kindling: broad facet planes, a different value per stick, a faint grain along the sticks,
            # scorched warm-dark toward the neck collar (the fire is inside)
            "wood": P.zone(base=WOOD, shadow=WOOD_SHADOW, light=WOOD_LIGHT, planes=0.14, parts=0.17, brush=0.05,
                           brush_freq=5.0, stroke=tuple(AX), stroke_amount=0.16, stroke_freq=(70.0, 5.0),
                           cavity=0.8, cavity_width=0.006, ao=0.7, ao_range=(0.22, 0.6), edge=0.55, edge_width=0.006,
                           edge_breakup=0.55,
                           gradient={"axis": tuple(AX), "range": (proj(0.62), proj(1.0)), "color": SCORCH, "amount": 0.55}),
            # charred wood (the two burnt sticks, the fingers, the stump's break)
            "char": P.faction_zone("unmade", "slag", light=CHAR_EDGE, planes=0.14, parts=0.08, brush=0.05, edge=0.6,
                                   edge_width=0.006, edge_breakup=0.45, cavity=0.6, ao=0.4),
            # the torch head: charred wood around the fire, bleached to pale ash toward the flared ends (a
            # cylindrical gradient out from the bundle axis) - from above a dark ring framing the fire inside a
            # broken pale rim; broad flat planes (one value per facet and per stick), a few brushy edges, no speckle
            "crown": P.zone(base=CROWN_CHAR, shadow="#120D0B", light=CHAR_EDGE, planes=0.12, parts=0.12, brush=0.04,
                            brush_freq=5.0, cavity=0.5, cavity_width=0.006, ao=0.35, ao_range=(0.3, 0.72), edge=0.55,
                            edge_width=0.007, edge_breakup=0.5,
                            gradient={"center": tuple(apt(1.0)), "axis": tuple(AX), "range": (ASH_R[0], ASH_R[1]),
                                      "color": ASH, "amount": 0.97}),
            "bind": P.faction_zone("unmade", "obsidian", light=OBS_EDGE, planes=0.2, parts=0.08, brush=0.06,
                                   brush_freq=4.0, edge=1.0, edge_width=0.009, edge_breakup=0.32, cavity=0.85,
                                   cavity_width=0.007, ao=0.6),
            "limb": P.faction_zone("unmade", "obsidian", light=mix_hex("#4B4658", OBS_EDGE, 0.6), planes=0.14, parts=0.06,
                                   edge=0.95, edge_width=0.008, edge_breakup=0.3, cavity=0.7, ao=0.5,
                                   gradient={"axis": (0, 0, 1), "range": (0.25, 0.0), "color": "shadow", "amount": 0.3}),
            # hottest in a column down the chest opening, teal round its flanks, then banked down to a dark ember
            # teal toward the back: the gaps between the sticks read dark, not as the clinker's teal slits (the art
            # review), so the chest opening and the torch-head fire are the only glow on the bundle
            "core": P.faction_zone("unmade", "ichor", glow=True,
                                   emit=dict(rim, mode="axis", center=tuple(apt(0.6) + FRONT * 0.1), axis=tuple(AX),
                                             radius=0.3, base_mix=0.08,
                                             stops=[(0.0, "#8FF2D8"), (0.28, "#2FBFA8"), (0.42, "#1F8F7E"),
                                                    (0.56, "#0B2F2B"), (1.0, "#071C19")])),
            # the fire in the torch head. Its heart is the hot core the 55 deg camera looks down onto: white-teal
            # low in the bowl, pale ichor up its body, cooling to faction teal only at the hooked tip...
            "heart": P.faction_zone("unmade", "ichor", glow=True,
                                    emit=dict(rim, mode="radial", center=tuple(apt(0.95)), radius=0.3,
                                              stops=[(0.0, "#E4FFF6"), (0.35, "#B8FFE8"), (0.62, "#8FF2D8"),
                                                     (1.0, "#2FBFA8")], base_mix=0.2)),
            # ...and its tongues are saturated faction teal, paler only where they leave the bowl, a deeper teal at
            # every tip (the first pass painted the whole fire white along its axis: a white crystal spike)
            "flame": P.faction_zone("unmade", "ichor", glow=True,
                                    emit=dict(rim, mode="radial", center=tuple(apt(0.95) + AX * 0.035), radius=0.27,
                                              stops=[(0.0, "#B8FFE8"), (0.2, "#8FF2D8"), (0.4, "#2FBFA8"),
                                                     (0.75, "#2FBFA8"), (1.0, "#1F8F7E")], base_mix=0.12)),
            # a braided cord: painted bands across it (streaks along z at a high frequency)
            "fuse": P.zone(base=CORD, shadow="#3A302A", light="#C8B89E", planes=0.12, parts=0.0, brush=0.04,
                           stroke=(0, 0, 1), stroke_amount=0.45, stroke_freq=(6.0, 70.0),
                           edge=0.6, edge_width=0.004, edge_breakup=0.4, cavity=0.5, ao=0.3,
                           emit=dict(rim, mode="radial", center=tuple(self.spark), radius=0.12, fade=(1.0, 0.6),
                                     base_mix=0.2)),
            # the spark: a white-teal core (#E4FFF6, the ichor core pushed toward white: never red-white) in teal rays
            "spark": P.faction_zone("unmade", "ichor", glow=True,
                                    emit=dict(rim, core="#E4FFF6", mode="radial", center=tuple(self.spark), radius=0.3,
                                              base_mix=0.45)),
        }

    def decals(self):
        """The torn chest opening: a burnt rim on the sticks around it, then teal light right at its edges."""
        o = apt(0.62) + FRONT * 0.18 * GR
        fr = frame_at(o, FRONT, LEFT)
        k = 1.12                                          # the flanking sticks sit further out on the thicker sheaf
        lines = [[(-0.082 * k, -0.15), (-0.075 * k, -0.02), (-0.067 * k, 0.13)],
                 [(0.08 * k, -0.15), (0.073 * k, -0.02), (0.067 * k, 0.13)]]
        return [P.decal_lines(lines, fr, 0.001, zones=["wood"], color=None, rim=BURN, rim_width=0.05,
                              depth=(-0.1, 0.06), facing=-0.3),
                P.decal_lines(lines, fr, 0.001, zones=["wood"], color=None, rim=SPILL_TEAL, rim_width=0.024,
                              emit={"color": "#0B2F2B", "core": "#0B2F2B"}, depth=(-0.1, 0.06), facing=-0.3)]


# ---- posing: pose dicts with world-space legs ---------------------------------------------------------------------

class Poser:
    """Evaluates GF_Swarm_v1 pose dicts (gfa_rig.apply_pose format) with mathutils only, so a clip can place a
    bone in WORLD space: the legs follow the hip point the body carries but not its lean, twist or swell."""

    def __init__(self, arm, hip):
        bones = arm.data.bones
        self.rest = {b.name: b.matrix_local.copy() for b in bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in bones}
        self.hip = Vector(hip)

    @staticmethod
    def basis(tr):
        loc = Vector(tr.get("loc", (0.0, 0.0, 0.0)))
        rot = tr.get("rot", (0.0, 0.0, 0.0))
        s = tr.get("scale", 1.0)
        s = (s, s, s) if isinstance(s, (int, float)) else tuple(s)
        return (Matrix.Translation(loc) @ Euler([math.radians(v) for v in rot], "XYZ").to_matrix().to_4x4()
                @ Matrix.Diagonal((s[0], s[1], s[2], 1.0)))

    def pose_mat(self, pose, bone):
        m = self.rest[bone] @ self.basis(pose.get(bone, {}))
        par = self.parent[bone]
        return m if par is None else self.pose_mat(pose, par) @ self.rest[par].inverted() @ m

    def world(self, pose, bone):
        if bone is None:
            return Matrix.Identity(4)
        return self.pose_mat(pose, bone) @ self.rest[bone].inverted()

    def solve(self, pose, bone, W):
        Wp = self.world(pose, self.parent[bone])
        m = self.rest[bone].inverted() @ Wp.inverted() @ W @ self.rest[bone]
        loc, q, sc = m.decompose()
        pose[bone] = {"loc": tuple(loc), "rot": tuple(math.degrees(v) for v in q.to_euler("XYZ")), "scale": tuple(sc)}
        return pose

    def legs(self, pose, a=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0), follow=1.0, scale=1.0, drop=0.0):
        """a / b: (swing deg, + = foot back; lift m; splay deg, + = foot outward) for legs_a (left) / legs_b."""
        hip = self.hip
        h = self.world(pose, "body") @ hip
        for bone, (sw, lift, sp), side in (("legs_a", a, 1), ("legs_b", b, -1)):
            rot = Matrix.Rotation(math.radians(sw), 4, "X") @ Matrix.Rotation(math.radians(-side * sp), 4, "Y")
            T = Matrix.Translation((h - hip) * follow + Vector((0.0, 0.0, lift - drop)))
            S = Matrix.Diagonal((scale, scale, scale, 1.0))
            self.solve(pose, bone, T @ Matrix.Translation(hip) @ rot @ S @ Matrix.Translation(-hip))
        return pose


def to_local(v):
    """World vector -> GF_Swarm_v1 bone-local (X left, Y up, Z forward)."""
    return (v[0], v[2], -v[1])


def swell_loc(s, pivot):
    """Body location that keeps the waist collar where it is while the body scales by s about its pivot."""
    w = apt(0.0) - Vector(pivot)
    return to_local(-(s - 1.0) * w)


def pulse(t, t0, w):
    d = ((t - t0 + 0.5) % 1.0) - 0.5
    return math.exp(-(d / w) ** 2)


def make_clips(arm, bld):
    """The six required clips + primed@loop. Poses are dicts; the legs are solved in world space per pose.
    Bones: body = the sheaf and both arms (scale = the swell), head = the torch-head fire (scale = its flare),
    tail = the fuse + spark (scale = the fuse burning down), legs_a / legs_b = the stilts."""
    piv = bld.pivots()
    pz = Poser(arm, piv["legs_a"])
    bp = piv["body"]
    sin, cos, tau = math.sin, math.cos, 2 * math.pi

    def P_(root=None, body=None, fuse=None, flame=None, legs=((0, 0, 0), (0, 0, 0)), swell=1.0, leg_scale=1.0,
           leg_drop=0.0, follow=1.0):
        p = {}
        if root:
            p["root"] = dict(root)
        bd = dict(body or {})
        if swell != 1.0:
            bd["scale"] = swell
            sl = swell_loc(swell, bp)
            l0 = bd.get("loc", (0, 0, 0))
            bd["loc"] = tuple(x + y for x, y in zip(l0, sl))
        if bd:
            p["body"] = bd
        if flame:
            p["head"] = dict(flame)
        if fuse:
            p["tail"] = dict(fuse)
        return pz.legs(p, legs[0], legs[1], follow=follow, scale=leg_scale, drop=leg_drop)

    def fl(w, h, rot=(0.0, 0.0, 0.0), loc=None):
        """The fire: w = width scale, h = height scale (bone Y = up), about the neck collar's centre."""
        d = {"rot": tuple(rot), "scale": (w, h, w)}
        if loc:
            d["loc"] = tuple(loc)
        return d

    def idle(t):
        w = tau * t
        tw = pulse(t, 0.32, 0.035)
        bob = 0.012 * (0.5 - 0.5 * cos(2 * w))
        fk = 0.05 * sin(3 * w + 1.0)
        return P_(root={"loc": (0, bob, 0)},
                  body={"rot": (5 + 2 * sin(w) + 4 * tw, 6 * tw, 2 * sin(w + 1))},
                  fuse={"rot": (-5 + 5 * sin(2 * w + 1) - 8 * tw, 0, 7 * sin(w + 0.5))},
                  flame=fl(FL_IDLE * (1 + fk), FL_IDLE * (1 + 0.1 * sin(3 * w) + 0.05 * sin(5 * w + 0.3)),
                           (-3 + 3 * sin(2 * w) - 6 * tw, 0, 4 * sin(w + 0.4))),
                  swell=1.0 + 0.035 * (0.5 + 0.5 * sin(w - 0.4)),
                  legs=((5 * sin(w), 0.03 * pulse(t, 0.25, 0.07), 2), (-5 * sin(w), 0.03 * pulse(t, 0.75, 0.07), 2)))

    def move(t):
        # the sprint reads from every side: a big bounce, a side-to-side roll and twist (seen from the front, where
        # the fore-aft leg swing is foreshortened), the fuse whipping and the fire streaming back, the lifted leg
        # kicking out
        w = tau * t
        bob = 0.055 * (0.5 - 0.5 * cos(2 * w))
        la, lb = max(0.0, cos(w)), max(0.0, -cos(w))
        return P_(root={"loc": (0, bob, 0)},
                  body={"rot": (8 + 3 * sin(2 * w + 0.4), 11 * sin(w), 9 * sin(w))},
                  fuse={"rot": (-26 - 10 * sin(2 * w - 1.0), 0, 16 * sin(w - 1.3))},
                  flame=fl(FL_MOVE * 0.92, FL_MOVE * (1.12 + 0.1 * sin(2 * w + 0.3)),
                           (-28 - 6 * sin(2 * w - 0.5), -6 * sin(w), 8 * sin(w - 0.8))),
                  legs=((-42 * sin(w), 0.09 * la, 3 + 10 * la), (42 * sin(w), 0.09 * lb, 3 + 10 * lb)))

    def primed(t):
        # PRIMED: planted, swollen, the fuse burnt to a stub - and the fire in the torch head blazes up to ~2 x and
        # throbs three times a second (pulse k), a flicker on top (f); frame 0 is windup's last (loaded) pose
        w = tau * t
        k = sin(w)
        f = 0.06 * sin(3 * w + 0.5)
        return P_(body={"rot": (-4 + 1.5 * sin(2 * w), 0, 3 * sin(2 * w))},
                  fuse={"rot": (8, 0, 3 * sin(2 * w + 1)), "scale": (0.5, 0.3, 0.46)},
                  flame=fl(FP_W * (1 + FP_K * k + f), FP_H * (1 + FP_KH * k + f), (3 * sin(2 * w + 0.5), 0, 5 * sin(w + 1))),
                  swell=1.32 + 0.04 * k, root={"loc": (0, -0.025, 0)}, legs=((-20, 0.0, 10), (15, 0.0, 10)))

    # windup = PRIMED begins: skid to a stop, the fire catches and flares twice while the bundle swells and the fuse
    # burns down; it ends on primed@loop's first frame, so the loop follows with no hitch
    rest = P_()
    skid = P_(body={"rot": (-14, 0, 2)}, fuse={"rot": (-26, 0, -6)}, flame=fl(1.3, 1.5, (-12, 0, 0)), swell=1.06,
              root={"loc": (0, -0.01, 0)}, legs=((-30, 0.0, 6), (20, 0.0, 6)))
    catch = P_(body={"rot": (-10, 0, -1)}, fuse={"rot": (0, 0, 2), "scale": (0.9, 0.82, 0.88)},
               flame=fl(2.05, 2.6, (-4, 0, 3)), swell=1.14, root={"loc": (0, -0.015, 0)},
               legs=((-24, 0.0, 8), (17, 0.0, 8)))
    dip = P_(body={"rot": (-8, 0, -2)}, fuse={"rot": (6, 0, 4), "scale": (0.72, 0.58, 0.68)},
             flame=fl(1.55, 1.8, (4, 0, -3)), swell=1.22, root={"loc": (0, -0.02, 0)},
             legs=((-22, 0.0, 9), (16, 0.0, 9)))
    flare2 = P_(body={"rot": (-5, 0, 3)}, fuse={"rot": (10, 0, -4), "scale": (0.6, 0.42, 0.56)},
                flame=fl(2.2, 2.75, (3, 0, -5)), swell=1.29, root={"loc": (0, -0.025, 0)},
                legs=((-20, 0.0, 10), (15, 0.0, 10)))
    loaded = primed(0.0)

    # attack = the detonation, from the loaded pose: the fire flashes up, then flat and wide, then gone
    peak = P_(body={"rot": (-6, 0, 0)}, fuse={"rot": (0, 0, 0), "scale": (0.3, 0.12, 0.3)}, flame=fl(2.7, 3.2),
              swell=1.55, root={"loc": (0, -0.03, 0)}, legs=((-26, 0.0, 16), (22, 0.0, 16)))
    blast = P_(body={"rot": (-4, 0, 0)}, fuse={"loc": (0, 0.12, 0), "scale": (0.3, 0.05, 0.3)}, flame=fl(2.5, 2.1),
               swell=1.85, root={"loc": (0, 0.0, 0)}, legs=((-45, 0.05, 40), (40, 0.05, 40)))
    shards = P_(body={"rot": (0, 0, 0)}, fuse={"loc": (0, 0.3, 0), "scale": 0.02}, flame=fl(0.02, 0.02, loc=(0, 0.1, 0)),
                swell=0.3, root={"loc": (0, 0.0, 0)}, legs=((-80, 0.15, 75), (75, 0.15, 75)), leg_scale=0.55)
    gone_a = P_(body={}, fuse={"loc": (0, 0.3, 0), "scale": 0.01}, flame=fl(0.01, 0.01, loc=(0, 0.1, 0)),
                swell=0.02, legs=((-90, 0.1, 90), (90, 0.1, 90)), leg_scale=0.02)

    # hit: a flinch back with a squash; the fuse and the fire whip forward and gutter
    flinch = P_(root={"loc": (0, -0.01, -0.05)}, body={"rot": (-17, -5, 9)}, fuse={"rot": (20, 0, -10)},
                flame=fl(0.75, 0.6, (26, 0, -10)), swell=0.94, legs=((10, 0.0, 4), (-6, 0.0, 4)))
    settle = P_(body={"rot": (6, 2, -4)}, fuse={"rot": (-10, 0, 6)}, flame=fl(1.12, 1.25, (-8, 0, 4)), swell=1.02)

    # death: stagger, a sputtering swell, a hitch, a smaller burst; the pieces scatter and shrink away
    stagger = P_(root={"loc": (0, -0.015, -0.07)}, body={"rot": (-24, 6, 13)}, fuse={"rot": (28, 0, -14)},
                 flame=fl(0.7, 0.55, (30, 0, -12)), swell=0.95, legs=((14, 0.0, 6), (-10, 0.0, 6)))
    sputter = P_(root={"loc": (0, -0.03, -0.05)}, body={"rot": (-8, 0, -7)},
                 fuse={"rot": (34, 0, 10), "scale": (0.85, 0.74, 0.82)}, flame=fl(1.45, 1.8, (10, 0, 6)), swell=1.22,
                 legs=((-8, 0.0, 12), (6, 0.0, 12)))
    hitch = P_(root={"loc": (0, -0.035, -0.05)}, body={"rot": (-12, 0, 9)},
               fuse={"rot": (40, 0, -8), "scale": (0.78, 0.64, 0.74)}, flame=fl(0.85, 0.7, (18, 0, -6)), swell=1.12,
               legs=((-8, 0.0, 14), (6, 0.0, 14)))
    swell2 = P_(root={"loc": (0, -0.035, -0.05)}, body={"rot": (-6, 0, -4)},
                fuse={"rot": (30, 0, 6), "scale": (0.55, 0.4, 0.5)}, flame=fl(1.9, 2.3, (6, 0, 4)),
                swell=1.42, legs=((-12, 0.0, 16), (10, 0.0, 16)))
    pop = P_(root={"loc": (0, -0.03, -0.05)}, body={"rot": (-4, 0, 0)},
             fuse={"rot": (50, 0, 0), "loc": (0, 0.08, 0), "scale": (0.6, 0.3, 0.6)}, flame=fl(2.2, 1.7), swell=1.62,
             legs=((-30, 0.04, 34), (28, 0.04, 34)))
    scatter = P_(root={"loc": (0, -0.06, -0.05)}, body={"rot": (10, 0, 25)},
                 fuse={"rot": (160, 40, 0), "loc": (0.05, 0.22, 0.05), "scale": 0.45},
                 flame=fl(0.25, 0.25, (20, 0, 0), loc=(0, 0.1, 0)), swell=0.45,
                 legs=((-70, 0.0, 70), (65, 0.0, 70)), leg_scale=0.7, leg_drop=0.05)
    crumble = P_(root={"loc": (0, -0.08, -0.05)}, body={"rot": (20, 0, 35)},
                 fuse={"rot": (200, 60, 0), "loc": (0.06, 0.05, 0.1), "scale": 0.2},
                 flame=fl(0.03, 0.03), swell=0.2,
                 legs=((-88, 0.0, 88), (85, 0.0, 88)), leg_scale=0.4, leg_drop=0.08)
    gone_d = P_(root={"loc": (0, -0.1, -0.05)}, body={"rot": (20, 0, 35)}, fuse={"scale": 0.01},
                flame=fl(0.01, 0.01), swell=0.02, legs=((-90, 0.0, 90), (90, 0.0, 90)), leg_scale=0.02, leg_drop=0.1)

    RIG.cycle_clip(arm, KEY, "idle@loop", IDLE_FRAMES, idle)
    RIG.cycle_clip(arm, KEY, "move@loop", MOVE_FRAMES, move)
    RIG.keyed_clip(arm, KEY, "windup", [(0, rest), (3, skid), (6, catch), (9, dip), (12, flare2), (15, loaded)])
    RIG.keyed_clip(arm, KEY, "attack", [(0, loaded), (2, peak), (4, blast), (7, shards), (10, gone_a), (11, gone_a)])
    RIG.keyed_clip(arm, KEY, "hit", [(0, rest), (2, flinch), (5, settle), (9, rest)])
    RIG.keyed_clip(arm, KEY, "death", [(0, rest), (3, stagger), (7, sputter), (10, hitch), (14, swell2), (16, pop),
                                        (19, scatter), (23, crumble), (26, gone_d), (27, gone_d)])
    RIG.cycle_clip(arm, KEY, "primed@loop", PRIMED_FRAMES, primed)
    return [RIG.clip_name(KEY, c) for c in SPEC.ENEMY_CLIPS_REQUIRED] + [RIG.clip_name(KEY, "primed@loop")]


KEY_FRAMES = {"idle@loop": [0, 13, 21, 32], "move@loop": [0, 3, 6, 9], "windup": [0, 3, 6, 9, 12, 15],
              "attack": [0, 2, 4, 7], "hit": [0, 2, 5, 9], "death": [0, 3, 7, 14, 16, 19, 23],
              "primed@loop": [0, 3, 5, 8]}
PRIMED_PEAK, PRIMED_LOW = 3, 8          # primed@loop frames at the top and the bottom of the throb


# ---- review --------------------------------------------------------------------------------------------------------

def flat_zone_mats():
    for z, hx in ZONE_FLAT.items():
        m = bpy.data.materials.get("GFA_" + z)
        if m:
            m.diffuse_color = C.hex_linear(hx)


def preview_game(objs, path, px=110, target=(0.0, 0.0, 0.45), up=4):
    """Workbench flat-colour render through the game camera at true 1080p pixel size (preview mode)."""
    scene = bpy.context.scene
    fl = B._floor(scene)
    fm = fl.data.materials[0]
    fm.diffuse_color = C.hex_linear(R.FLOOR)
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = False
    sh.show_shadows = False
    sh.show_object_outline = True
    sh.object_outline_color = (0.02, 0.01, 0.01)
    sh.background_type = "VIEWPORT"
    sh.background_color = C.hex_linear(R.FLOOR)[:3]
    fl.hide_render = False
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    R.aim(scene, Vector(target), B.game_dir(), px / ppm, dist=60.0)
    R.render(scene, path, px)
    fl.hide_render = True
    return path


def pose_track(arm, clip, frame):
    if clip is None:
        RIG.unmute_none(arm)
    else:
        RIG.pose_at(arm, RIG.clip_name(KEY, clip), frame)
    bpy.context.view_layer.update()


def preview(bld, arm, mesh, work):
    """Fast modelling check: flat zone colours from 4 views + the game camera (true size, shown 4x) for key poses."""
    flat_zone_mats()
    views = {"front": (0.0, -1.0, 0.12), "34_front": (0.7, -0.7, 0.3), "side": (1.0, 0.0, 0.1), "top": (0.0, -0.0001, 1.0)}
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    fv = B.flat_views([mesh], work, KEY, ZONE_FLAT, views, size=360)
    ims = [{"path": p, "label": k} for k, p in fv.items()]
    game = []
    for label, clip, f in (("rest", None, 0), ("sprint", "move@loop", 3), ("sprint", "move@loop", 9),
                           ("primed", "windup", 15), ("primed peak", "primed@loop", PRIMED_PEAK),
                           ("primed low", "primed@loop", PRIMED_LOW), ("burst", "attack", 4), ("hit", "hit", 2),
                           ("death", "death", 16)):
        pose_track(arm, clip, f)
        for yaw, tag in ((-35.0, "toward"), (90.0, "side"), (145.0, "away")):
            arm.rotation_euler = (0, 0, math.radians(yaw))
            bpy.context.view_layer.update()
            p = preview_game([mesh], os.path.join(work, "pv_%s_%d_%d.png" % (label.replace(" ", "_"), f, yaw)), px=72,
                             target=(0.0, 0.0, 0.6))
            game.append({"path": p, "label": "%s f%d %s" % (label, f, tag), "scale": 3})
        arm.rotation_euler = (0, 0, 0)
    RIG.unmute_none(arm)
    layout = {"title": "Kindlejack - preview (flat zone colours)", "subtitle": "%d tris" % bld.tris, "width": 1600,
              "sections": [{"label": "views", "height": 300, "images": ims},
                           {"label": "game camera, true size, 3x nearest", "height": None, "images": game}],
              "swatches": [{"hex": h, "label": z} for z, h in ZONE_FLAT.items()], "notes": []}
    return R.contact_sheet(layout, os.path.join(work, "%s_preview.png" % KEY), work)


def ingame_poses(arm, mesh, work, yaw=-35.0):
    out = []
    poses = [("rest", None, 0), ("sprint", "move@loop", 3), ("primed: windup end", "windup", 15),
             ("primed@loop: throb peak", "primed@loop", PRIMED_PEAK), ("primed@loop: throb low", "primed@loop", PRIMED_LOW),
             ("detonation", "attack", 4), ("hit", "hit", 2), ("death burst", "death", 16)]
    arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
    for label, clip, f in poses:
        pose_track(arm, clip, f)
        tag = "".join(ch if ch.isalnum() else "_" for ch in label.split(":")[-1].strip())[:24]
        r = R.ingame([mesh], work, "%s_pose_%s" % (KEY, tag), px=80, view_height=SPEC.GAME_VIEW_HEIGHTS[0],
                     target=(0.0, 0.0, 0.75), silhouette_too=False, ink=0.01)
        out.append((label, r["color"]))
    RIG.unmute_none(arm)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.scene.frame_set(0)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    return out


def review(bld, arm, mesh, rep, reports, work, tex, notes):
    import clinker as K                      # size_compare (side view beside the hero, waist line)
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    turn = R.turnaround([mesh], work, KEY, R.CREATURE_VIEWS, size=400)
    height = rep.get("height_m") or 1.0
    size_p = K.size_compare(mesh, work, KEY, height)
    tracks = [RIG.clip_name(KEY, c) for c in KEY_FRAMES]
    strips = B.clip_frames(arm, [mesh], tracks, work, KEY, size=190, direction=R.CREATURE_VIEWS["34_front"], ink=0.006,
                           samples=8, frame_lists={RIG.clip_name(KEY, c): f for c, f in KEY_FRAMES.items()},
                           ext=2.1, center=(0.0, 0.03, 0.85))
    ing = []
    for label, yaw, clip, f in (("sprinting at the camera", -35.0, "move@loop", 3), ("sprinting away", 145.0, "move@loop", 9)):
        pose_track(arm, clip, f)
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.0, 0.25, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_%s" % (KEY, "face" if yaw < 0 else "away"), px=150,
                     view_height=SPEC.GAME_VIEW_HEIGHTS[0], mannequin_obj=man)
        C.remove_objects([man])
        ing.append((label, r))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    RIG.unmute_none(arm)
    poses = ingame_poses(arm, mesh, work)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Kindlejack  (kindlejack.glb)",
        "subtitle": "The Unmade | Swarm, Cinder Wastes | Bomber: runs, primes, bursts | verb RUSH | GF_Swarm_v1 | "
                    "\"Runs at you. Then it is you who runs.\"",
        "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn.items()]},
            {"label": "Size vs the 2.2 m hero (side; waist line = swarm ceiling) | in-game camera, 55 deg, %.1f px/m, TRUE size 1x, "
                      "then 3x nearest (sprint pose)" % ppm,
             "height": None, "images": [{"path": size_p, "label": "side: %.2f m tall = %.2f x hero" % (height, height / 2.2)},
                                        {"path": ing[0][1]["color"], "label": "1x"},
                                        {"path": ing[0][1]["color"], "label": "3x " + ing[0][0], "scale": 3},
                                        {"path": ing[1][1]["color"], "label": "3x " + ing[1][0], "scale": 3}]},
            {"label": "Game-size silhouette (3x) and key poses through the game camera at TRUE pixel size (3x nearest)",
             "height": None,
             "images": [{"path": ing[0][1]["sil"], "label": "silhouette 3x", "scale": 3}]
                + [{"path": p, "label": lb, "scale": 3} for lb, p in poses]},
            {"label": "Clip key frames (3/4 front, one scale): idle, move (sprint), windup (swell, fuse burns down), attack "
                      "(detonation), hit, death, primed@loop",
             "height": 150, "images": [{"path": p, "label": "%s f%d" % (cl.replace(KEY + "_", ""), f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220, "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    return R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)


# ---- horde review: the shipped GLBs, mixed with clinkers ------------------------------------------------------------

def cinderling_greybox(loc):
    """The cinderling's current in-game greybox (crates/gf_client/src/scene.rs, EnemyShape::Blob at radius 0.42):
    a 0.84 x 0.67 m ellipsoid with an ember cone on top - the shape the kindlejack must not be confused with."""
    r = 0.42
    asm = M.Assembly("GFA_CINDERLING_GREYBOX", ["body", "crown"])
    b = M.sphere(1.0, 16, 10, scale=(r, r, r * 0.8))
    M.xform(b, loc=(0, 0, r * 0.8))
    asm.add(b, "body", shading="smooth")
    c = M.cylinder(r * 0.32, r * 0.7, sides=10, radius_top=0.0)
    M.xform(c, loc=(0, 0, r * 1.75))
    asm.add(c, "crown", shading="smooth")
    o = asm.to_object()
    o.location = loc
    return o


def import_glb(key, clips):
    """Import a shipped GLB and return {key, arm, mesh, acts} like clinker_crowd.import_variant, but pick the
    SKINNED mesh: Blender's glTF importer also adds an icosphere bone-display mesh, which may sort first by name."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=C.model_path(KIND, key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    meshes = [o for o in new if o.type == "MESH"]
    mesh = next(o for o in meshes if any(m.type == "ARMATURE" for m in o.modifiers))
    extra = [o for o in meshes if o is not mesh]
    arm.name, mesh.name = key + "_ARM", key + "_MESH"
    acts = {}
    for c in clips:
        act = bpy.data.actions.get("%s_%s" % (key, c))
        if act is None:
            raise RuntimeError("%s.glb has no clip %s_%s" % (key, key, c))
        act.use_fake_user = True
        acts[c] = act
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    for pb in arm.pose.bones:                      # the importer's bone-display shapes must not leak into renders
        pb.custom_shape = None
    C.remove_objects(extra)
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts}


def spawn(v, loc, yaw, clip=None, frame=0.0):
    """clinker_crowd.spawn, with the yaw actually applied: Blender's glTF importer leaves the armature object in
    QUATERNION rotation mode, so setting rotation_euler alone turns nothing."""
    import clinker_crowd as CC
    a2, m2 = CC.spawn(v, loc, yaw, clip, frame)
    a2.rotation_mode = "QUATERNION"
    a2.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), yaw) @ v["arm"].matrix_world.to_quaternion()
    return a2, m2


def crowd(out_notes):
    """Imports kindlejack.glb and the four clinker looks, and renders through the game camera at TRUE 1080p size:
    a lineup (hero, clinker, cinderling greybox, kindlejack), a 40-kindlejack horde mixed with 24 clinkers, a
    realistic pack (3 kindlejacks in 40 clinkers) and the sprint cycle. Returns the sheet path."""
    import clinker as K
    import clinker_crowd as CC
    C.reset_scene(fps=FPS)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "crowd"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    scene = bpy.context.scene
    kj = import_glb(KEY, list(SPEC.ENEMY_CLIPS_REQUIRED) + ["primed@loop"])
    kj["arm"].location = (100.0, 100.0, 0.0)
    clinkers = []
    for i, vk in enumerate(("base", "v1", "v2", "v3")):
        v = import_glb(K.VARIANTS[vk]["key"], SPEC.ENEMY_CLIPS_REQUIRED)
        v["V"] = K.VARIANTS[vk]
        v["arm"].location = (105.0 + 5 * i, 100.0, 0.0)
        clinkers.append(v)
    bpy.context.view_layer.update()
    out = {}

    # 1. lineup: hero, clinker, cinderling greybox, kindlejack (sprint and primed)
    made = []
    made += list(spawn(clinkers[0], (-0.2, 0.0, 0.0), math.radians(-25), "idle@loop", 0))
    grey = cinderling_greybox((0.85, 0.0, 0.0))
    made += list(spawn(kj, (1.9, 0.0, 0.0), math.radians(-25), "move@loop", 3))
    made += list(spawn(kj, (2.8, 0.0, 0.0), math.radians(-25), "windup", 15))
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-1.3, 0.1, 0.0)
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {man.name: R.MANNEQUIN, grey.name: "#E0662B"}
    R.setup_cycles(scene, 12)
    with R.toon_preview(meshes + [man, grey], ink=0.006, flat=flat):
        R.aim(scene, (0.75, 0.0, 0.8), (0.25, -0.9, 0.35), 5.2)
        out["lineup"] = R.render(scene, os.path.join(work, "kj_lineup.png"), 1400, 560)
    out["lineup_game"] = CC.game_render(meshes + [man, grey], flat, os.path.join(work, "kj_lineup_game.png"), 250, 120,
                                        (0.75, 0.1, 0.45))
    CC.clear_copies(made)
    C.remove_objects([man, grey])

    # 2. the horde: 40 kindlejacks + 24 clinkers converging on two heroes; mixed facings and clip phases
    rng = random.Random(19)
    heroes = [Vector((-0.8, -0.2, 0.0)), Vector((0.9, 0.4, 0.0))]

    def horde(n_kj, n_cl, seed, min_d=0.62):
        rng.seed(seed)
        mans = []
        for hp, aim in zip(heroes, ((0.4, 0.9, 0.0), (0.9, 0.4, 0.0))):
            m = R.mannequin(aim_dir=aim)
            m.location = hp
            mans.append(m)
        pts = []
        tries = 0
        while len(pts) < n_kj + n_cl and tries < 40000:
            tries += 1
            c = heroes[rng.randrange(2)]
            r = rng.uniform(1.0, 4.6)
            ang = rng.uniform(-0.25 * math.pi, 1.15 * math.pi)
            p = c + Vector((math.cos(ang) * r * 1.2, math.sin(ang) * r, 0.0))
            if any((p - q).length < min_d for q in pts) or any((p - h).length < 0.9 for h in heroes):
                continue
            pts.append(p)
        order = [True] * n_kj + [False] * n_cl
        rng.shuffle(order)
        made, phases = [], []
        for i, (p, is_kj) in enumerate(zip(pts, order)):
            tgt = min(heroes, key=lambda h: (h - p).length)
            yaw = CC.face_yaw(p, tgt) + math.radians(rng.uniform(-25, 25))
            u = rng.random()
            if is_kj:
                d = (tgt - p).length
                if d < 1.7 and u < 0.7:              # PRIMED: late windup or anywhere in the primed@loop throb
                    clip, f = rng.choice((("windup", 12.0), ("windup", 15.0), ("primed@loop", float(PRIMED_PEAK)),
                                          ("primed@loop", 5.0), ("primed@loop", float(PRIMED_LOW))))
                elif u < 0.85:
                    clip, f = "move@loop", rng.uniform(0, MOVE_FRAMES)
                else:
                    clip, f = "idle@loop", rng.uniform(0, IDLE_FRAMES)
                made += list(spawn(kj, p, yaw, clip, f))
                phases.append("kindlejack " + clip)
            else:
                v = clinkers[i % 4]
                mv = v["V"]["motion"]
                if u < 0.7:
                    clip, f = "move@loop", rng.uniform(0, mv["move_frames"])
                elif u < 0.88:
                    clip, f = "idle@loop", rng.uniform(0, mv["idle_frames"])
                else:
                    clip, f = "windup", 15.0
                made += list(spawn(v, p, yaw, clip, f))
                phases.append("clinker")
        bpy.context.view_layer.update()
        return made, mans, phases

    made, mans, phases = horde(40, 24, 19)
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    out["crowd"] = CC.game_render(meshes + mans, flat, os.path.join(work, "kj_crowd_1x.png"), 640, 470, (0.1, 0.8, 0.3),
                                  sil_path=os.path.join(work, "kj_crowd_1x_sil.png"))
    out["crowd_sil"] = os.path.join(work, "kj_crowd_1x_sil.png")
    out["crowd28"] = CC.game_render(meshes + mans, flat, os.path.join(work, "kj_crowd_1x_28.png"), 500, 370,
                                    (0.1, 0.8, 0.3), view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    n_kj = sum(1 for p in phases if p.startswith("kindlejack"))
    counts = {}
    for p in phases:
        counts[p] = counts.get(p, 0) + 1
    CC.clear_copies(made)
    C.remove_objects(mans)

    # 3. the realistic read: a pack of 3 kindlejacks inside a 40-clinker horde - can you spot the bombers?
    made, mans, phases3 = horde(3, 40, 23, min_d=0.6)
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    out["pack"] = CC.game_render(meshes + mans, flat, os.path.join(work, "kj_pack_1x.png"), 640, 470, (0.1, 0.8, 0.3))
    CC.clear_copies(made)
    C.remove_objects(mans)

    # 4. the sprint cycle across the screen and toward the camera, the primed swell and the detonation at game size
    strip = []
    for clip, frames, yaw, tag in (("move@loop", [0, 2, 4, 6, 8, 10], 90.0, "across"),
                                   ("move@loop", [0, 2, 4, 6, 8, 10], -30.0, "toward"),
                                   ("windup", [0, 3, 6, 9, 12, 15], -30.0, ""),
                                   ("primed@loop", [0, PRIMED_PEAK, 5, PRIMED_LOW], -30.0, ""),
                                   ("attack", [0, 2, 4, 7], -30.0, "")):
        for f in frames:
            made = list(spawn(kj, (0.0, 0.0, 0.0), math.radians(yaw), clip, f))
            bpy.context.view_layer.update()
            p = os.path.join(work, "kj_%s_%s_%02d.png" % (clip.replace("@", "_"), tag or "c", f))
            CC.game_render([o for o in made if o.type == "MESH"], {}, p, 84, 84, (0.0, 0.0, 0.72), samples=12)
            CC.clear_copies(made)
            strip.append(((clip + " " + tag).strip(), f, p))
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = CC.upscale(out["crowd"], os.path.join(reports, "%s_crowd.png" % KEY), 2)
    sections = [
        {"label": "Lineup (toon preview of the shipped GLBs): the 2.2 m hero, a clinker, the cinderling's current greybox "
                  "(Blob, r 0.42), the kindlejack sprinting and primed", "height": 380,
         "images": [{"path": out["lineup"], "label": "hero | clinker | cinderling greybox | kindlejack sprint | kindlejack primed"}]},
        {"label": "The same lineup through the game camera (55 deg, 49.1 px/m): TRUE size 1x, then 3x nearest", "height": None,
         "images": [{"path": out["lineup_game"], "label": "1x"}, {"path": out["lineup_game"], "label": "3x", "scale": 3}]},
        {"label": "HORDE READ: %d kindlejacks mixed with %d clinkers around two 2.2 m heroes, TRUE 1080p pixel size (1x); "
                  "kindlejacks inside 1.7 m of a hero are primed" % (n_kj, len(phases) - n_kj), "height": None,
         "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px)"},
                    {"path": out["crowd_sil"], "label": "1x silhouette"}]},
        {"label": "The same horde in the four-player view (28 m = 1080 px), and the realistic pack: 3 kindlejacks in a 40-clinker "
                  "horde (1x)", "height": None,
         "images": [{"path": out["crowd28"], "label": "1x, 28 m view"}, {"path": out["pack"], "label": "1x: find the 3 bombers"}]},
        {"label": "The horde, 2x nearest", "height": None, "images": [{"path": out["crowd"], "label": "2x", "scale": 2}]},
        {"label": "RUSH at game size, TRUE pixels 3x nearest: move@loop across / toward the camera, windup (the fire "
                  "catches), primed@loop (its throb), attack", "height": None,
         "images": [{"path": p, "label": "%s f%d" % (c, f), "scale": 3} for c, f, p in strip]},
    ]
    layout = {"title": "Kindlejack - horde read, mixed with clinkers (The Unmade, Cinder Wastes)",
              "subtitle": "content key kindlejack | Swarm | Bomber(trigger 1.6, fuse 0.9, radius 2.2) | packs of 1-2 | verb RUSH | "
                          "status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "swatches": [{"hex": h, "label": n} for n, h in PALETTE],
              "notes": list(out_notes) + ["Every copy is posed from the actions inside the shipped GLBs (Blender's glTF importer). "
                                          "Phases: " + ", ".join("%d %s" % (n, c) for c, n in sorted(counts.items(), key=lambda t: -t[1]))]}
    sheet = R.contact_sheet(layout, os.path.join(reports, "%s_horde_review.png" % KEY), work)
    return sheet, crowd2x


# ---- main ----------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 512, int)
    pv = C.flag(argv, "--preview")
    if C.flag(argv, "--crowd-only"):              # re-render the horde review from the shipped GLBs
        C.log("horde review", crowd([])[0])
        return
    C.reset_scene(fps=FPS)
    col = C.get_collection(KEY)
    bld = Build()
    mesh = bld.build(col)
    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    work = C.ensure_dir(os.path.join(pack, "work", KEY))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    if pv:
        arm = RIG.build_swarm_rig(bld.pivots(), col=col)
        RIG.skin_rigid(mesh, arm)
        make_clips(arm, bld)
        C.log("preview sheet", preview(bld, arm, mesh, work))
        return
    paint_rep = P.paint_asset(mesh, KEY, bld.recipes(), tex_dir, size=size, decals=bld.decals(), ao_distance=0.035,
                              ao_samples=16, edge_min_angle=24.0, margin_px=3, uv_angle=66.0, seed=SEED,
                              uv_zone_scale=UV_SCALE)
    arm = RIG.build_swarm_rig(bld.pivots(), col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in bld.sockets():
        RIG.add_socket(arm, bone, name, p)
    RIG.add_socket(arm, "tail", "fx_fuse", tuple(bld.spark))       # extra: the spark VFX (follows the fuse burning down)
    clips = make_clips(arm, bld)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    extra = {
        "content_key": KEY,
        "content_row": ROW,
        "verb": "RUSH",
        "design": "a forward-leaning sheaf of kindling tied by two obsidian collars, flaring into a pale ash torch head "
                  "around a teal Unmade fire, a lit fuse with a big white-teal spark; two obsidian stilt legs, one stick "
                  "arm trailing back, one snapped stump",
        "bones": {"root": "bob, lean, knock-back",
                  "body": "the sheaf (sticks, torch head, collars, core, shoulder shards) and both arms; scale = the swell",
                  "head": "the torch-head fire (pivot at the neck collar's centre; scale = the fire blazing and throbbing)",
                  "legs_a": "left leg", "legs_b": "right leg",
                  "tail": "the fuse + spark (pivot at the fuse's root; scale = the fuse burning down)"},
        "clip_map": {"move@loop": "Approach (the sprint)", "windup": "PRIMED begins: skid, the fire catches and flares, "
                     "swell, the fuse burns down; ends on primed@loop's first frame",
                     "primed@loop": "PRIMED: loop it after windup for the rest of the fuse - the fire blazes about 2 x "
                                    "and throbs three times a second (the brightest swarm on screen)",
                     "attack": "the detonation when the fuse runs out (play on the despawn; the blast is the engine's VFX "
                               "at fx_core)", "death": "shot down before it blows: stagger, sputtering swell, a small burst",
                     "hit": "flinch", "idle@loop": "bouncing on its toes"},
        "extra_sockets": {"fx_fuse": "on tail: the spark at the fuse tip (moves down as the fuse burns in windup)"},
        "move_cycle_m": MOVE_CYCLE_M,
        "move_note": "rigid-group sprint: play move@loop at speed / move_cycle_m cycles per second (the Bomber runs at "
                     "1.1 x 4.6 m/s -> about 5.6 cycles/s, 11 strides a second: the frantic RUSH)",
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
        "skin": skin,
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.log("clips", RIG.clips_report(arm))
    C.write_json(os.path.join(reports, "%s_build_report.json" % KEY),
                 {"export": {k: rep[k] for k in rep if k not in ("nodes",)}, "paint": paint_rep, "skin": skin,
                  "parts": bld.parts, "tris_blender": bld.tris, "clips": RIG.clips_report(arm)})
    notes = [
        "%s tris (swarm budget 600-1500) | textures %s | %.2f m tall (%.2f x hero), %.2f m long | sockets: %s + fx_fuse" % (
            rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"], rep["height_m"] / 2.2,
            (rep["bounds"]["max"][2] - rep["bounds"]["min"][2]), ", ".join(sorted(rep["sockets"]))),
        "Clips: %s" % ", ".join(c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
        "move_cycle_m %.2f. The torch-head fire is the head bone (scale = its blaze and throb), the fuse the tail bone (scale "
        "burns it down);" % MOVE_CYCLE_M,
        "the swell is the body scale; the legs are posed in world space and stay planted. Status: %s." % SPEC.STATUS_AI_FINAL,
    ]
    outputs = [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
               "art/enemies/%s/source/%s.blend" % (KEY, KEY), "art/enemies/%s/textures/%s_basecolor.png" % (KEY, KEY),
               "art/enemies/%s/textures/%s_emissive.png" % (KEY, KEY)]
    if not C.flag(argv, "--no-review"):
        tex = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        sheet = review(bld, arm, mesh, rep, reports, work, tex, notes)
        outputs.append(C.rel(sheet))
    if not C.flag(argv, "--no-crowd"):
        sheet, crowd2x = crowd(notes[:1])
        outputs += [C.rel(sheet), C.rel(crowd2x)]
    fix_sheet = os.path.join(reports, "%s_review_fix.png" % KEY)       # written by enemies/kindlejack_fix_sheet.py
    if os.path.exists(fix_sheet):
        outputs.append(C.rel(fix_sheet))
    C.write_pack_status(KIND, KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/kindlejack.py (model, paint, GF_Swarm_v1 rig, "
                        "7 clips, export, validation, review and the horde read mixed with clinkers). Art review fix "
                        "(5/10): it fills its collider (footprint 0.65 x 0.67 -> 0.86 x 0.89 m, on a par with a clinker "
                        "on screen), the crown flares into a pale ash torch head, the spark is a 0.14 m white-teal core (2.5 x the area), "
                        "the slits between the sticks are banked dark, and primed@loop throbs a teal fire in the torch "
                        "head (the brightest swarm on screen while primed); before/after in "
                        "reports/kindlejack_review_fix.png (enemies/kindlejack_fix_sheet.py).", tier=TIER,
                        extra={"skeleton": SPEC.SWARM_SKELETON, "faction": "unmade", "verb": "RUSH"})
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
