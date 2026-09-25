"""Emberwisp - the Cinder Wastes swarm wisp (Fallen Godworks): built, painted, rigged on GF_Swarm_v1,
animated, exported and reviewed from code.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/emberwisp.py -- [--size 512] [--no-review] [--no-crowd] [--preview]
  "...blender.exe" -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/emberwisp.py -- --crowd-only

  --preview     flat zone colours through Workbench (about 10 s): silhouette iterations, nothing exported
  --no-review   build, paint, rig, export and validate only
  --no-crowd    skip the horde review (40 emberwisps mixed with clinkers, imported from the shipped GLBs)
  --crowd-only  only the horde review (needs assets/models/enemies/emberwisp.glb and clinker*.glb)
  --metrics-only [--glb PATH] [--out DIR] [--tag T]   only the art-review metric renders of a shipped GLB (toon,
                emission-only and zone passes at true 1x); enemies/emberwisp_fix_sheet.py measures them and draws
                the before / after sheet. The full build runs them on the new GLB unless --no-metrics

Content row (content/sheets/enemies.csv): emberwisp, Swarm, P0, hp 20, speed 4.2, radius 0.34, scale 1.0,
Swarmer(jitter 1.4), colour #FFD27A, shape Wisp, packs of 2-3, death_burst (radius 1.6, damage 16) -
"Erratic sparks that burst when snuffed." The Bellows (the Cinder Wastes mini-boss, assets/content/bosses.ron)
summons four of them in its Blaze phase. Collider radius x scale = 0.34 m, so the footprint is about
0.75-1.0 m (docs/art/ENEMIES.md section 2); the greybox wisp hovers with its centre about 0.8 m up.

Design (docs/art/ENEMIES.md; the user's enemy pack):
  * FACTION: the Fallen Godworks. Their glow is literally this creature: cold gold #D4B45A fading to dead
    ember #8A3A1E. It is the last spark of a dead god-forge, still wearing a scrap of its war-machine: a small
    soot-blackened god-bronze mask. ART REVIEW FIX (5/10): the first pass was a white-gold / pale-gold fire and
    19-27 % of its pixels sat within dE 20 of the player gold #FFC940 (it read as a gold pickup or fire VFX).
    The flame is now dead ember (#C8663A tongues cooling to #8A3A1E tips, painted, lit by the toon ramp, not
    emissive), cold gold #D4B45A glows only in a thin band against the core, and there is no pale band: no
    pixel within dE 20 of #FFC940 and at most 40 % of the pixels glow in any pose. The row colour #FFD27A is
    the greybox tint only. No red-white.
  * VERB FLICKER: a dark mask-head in a cup of flame, a ring of flame tongues rising and curling around it
    (open over the face and the crown, so the 55 deg camera always sees the dark core in the middle of the
    fire), a forked tail streaming behind. Two tongue groups flare and gutter out of phase, the tail whips,
    and the whole spirit jinks in small erratic darts.
  * VALUE PLAN at game size: the dark mask is the creature (review fix: the 8 px dark core read as a
    fireball; the mask-head is now about 16 px at 1x, over half the flame's width, and all of it reads dark),
    framed by a thin cold-gold band against the core, then the mid-value ember flame, whose tips and tail
    tip go to dead ember. The face carries one big slanted cold-gold eye slit, the only light on the mask and
    the focal point; the mask's upper-left corner is broken off into a charred notch (unlit), so the
    asymmetry is in the mask's outline against the fire, and the lopsided tongues carry the rest.
  * PAINT: the flame is painted, not graded: flat heat bands (flame_paint(), installed around gfa_paint.paint
    for this build only). Heat runs along each lick's own centreline, its blade edges run cooler than its
    centre (a hot stripe up every tongue), smooth waves across the flame bend the band borders into flame
    fingers, and each band has its own emission gain and base-colour factor (only the cold-gold and warm
    ember-core bands next to the core glow). The emissive PNG is sRGB, so the flame stores its emission
    close to the band colour. The mask-head is the gf_assets NPR painter: dark bronze value planes,
    verdigris cavities, sparse dull old-gold edge strokes, a low war-helm crest over the crown, two painted
    (unlit) dead-ember cracks from the broken corner.
  * The review renders drop the preview's ink hull on glowing faces (the engine's toon shader adds emission
    after its ink edge) and draw the client's blob shadow under the hovering wisp.

Rig GF_Swarm_v1 (rigid): body = the mask-head core (centre of mass; it persists and falls in the death),
head = the flame hood cupping the core, legs_a / legs_b = the two tongue groups (they flicker out of phase),
tail = the forked tail and its sparks, root = the hover bob and tilts.

Toolkit: tools/blender/gf_assets (gfa_model / gfa_paint / gfa_rig / gfa_export / gfa_render / gfa_boss).
Structure follows enemies/clinker.py (the shipped swarm crawler).
"""
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY = "emberwisp"
KIND, TIER = "enemy", "swarm"
FPS = 30
SEED = 29
ROW = {"key": "emberwisp", "class": "Swarm", "biome": "cinder_wastes", "hp": 20, "speed": 4.2, "radius": 0.34,
       "scale": 1.0, "behavior": "Swarmer(jitter: 1.4)", "color": "#FFD27A", "shape": "Wisp", "pack": "(2, 3)",
       "death_burst": "(1.6, 16.0)"}
ZONES = ["mask", "crust", "ember", "flame", "tongue", "tail", "spark"]
FLAME_ZONES = ("flame", "tongue", "tail", "spark")

CZ = 0.60                  # hover height of the core centre (m)
HEAD_R = 0.18              # mask-head radius (review fix: 0.15 -> 0.18, the mask is the creature, not a pip)
FACE_TILT = 16.0           # the face looks this much up (deg), toward the 55 deg camera
CORE = Vector((0.0, 0.0, CZ))

# the flame tongues: flat blades with a diamond section, rising in an S from a ring BEHIND the mask-head's
# outline (review fix: the roots no longer cover the mask's sides, and the hooked tongue no longer curls over
# the crown). (angle deg around the core, 0 = front / -Y, 90 = the creature's LEFT / +X; height; outward reach;
# back sweep; base half-width; inward curl of the tip; S wiggle; bone). The left side carries one big hooked
# tongue, the right side two lower licks - lopsided on purpose; the back is a tall crest of three; nothing
# rises in front of the face (two short licks flank the jaw).
TONGUES = [
    (64.0, 0.17, 0.08, 0.05, 0.070, 0.02, 0.015, "legs_a"),
    (100.0, 0.44, 0.16, 0.12, 0.130, 0.10, 0.030, "legs_b"),
    (142.0, 0.42, 0.06, 0.20, 0.140, 0.04, -0.030, "legs_a"),
    (180.0, 0.52, 0.02, 0.24, 0.150, 0.02, 0.035, "legs_b"),
    (220.0, 0.38, 0.06, 0.18, 0.135, 0.03, -0.030, "legs_a"),
    (262.0, 0.26, 0.12, 0.09, 0.110, 0.04, 0.025, "legs_b"),
    (298.0, 0.15, 0.08, 0.05, 0.066, 0.02, -0.015, "legs_a"),
]
TONGUE_ROOT = 0.62         # tongue roots sit this x HEAD_R out from the core, and a little behind it
DIAMOND = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]

# ---- palette (gfa_spec.FACTIONS["godworks"]) -------------------------------------------------------------
GOLD_LIGHT, GOLD, GOLD_RIM = "#F4E6B0", "#D4B45A", "#8A6A28"
EMBER_LIGHT, EMBER, EMBER_RIM = "#C8663A", "#8A3A1E", "#4A1A0C"
BRONZE_DARK, OLD_GOLD, VERDIGRIS_SH = "#5E5034", "#86703F", "#10201C"
SOOT = "#241E17"           # the soot-blackened bronze of the mask-head (the dark core)
EMBER_CORE = "#E08A50"     # dead_ember core: the warm step between the gold and the rust
# the eye slit's glow (rim, core): held-back cold gold. Over the gold base line, lit by the toon ramp and x1.6,
# the slit lands at a pale cold gold (#F9CF8C-#FFE894 on screen, dE76 27+ from #FFC940); a pale-gold core
# (#F4E6B0) clipped to cream-white and read as a white pip, not the gold eye the review asked for
EYE_GOLD, EYE_CORE = "#9C8452", "#B39469"
# Heat bands of the painted flame: (heat where the band starts, colour, emission gain, base-colour factor).
# REVIEW FIX (player-colour clash): the flame is dead ember, not gold. Cold gold glows only in a thin band
# against the core, then the warm ember step (a dim glow), and the tongues themselves are painted dead ember
# #C8663A -> #8A3A1E with NO emission: the engine's toon ramp lights them, so they carry form and an ink edge
# like the rest of the creature, and the glow stays a focal accent (the review's target: 40 % or less of the
# pixels glow). The old ramp (white-gold core, pale gold, gold, then ember tips, all emissive x1.6 in the
# review) put 19-27 % of the pixels within dE 20 of the P1 gold #FFC940. No pale band anywhere.
BANDS = [(0.00, GOLD, 0.68, 0.40), (0.15, EMBER_CORE, 0.60, 0.55), (0.30, EMBER_LIGHT, 0.0, 1.0),
         (0.62, EMBER, 0.0, 1.0)]
# The emissive PNG is sRGB (the engine linearises it); the review preview multiplies it by 1.6. A gold gain of
# 0.68 lands the lit, glowing band at about #D4B45A on screen (dE76 about 24 from #FFC940); a gain near 1.0
# lands at about #FFDE70 (dE76 17): the clash.
FLAME_EMIT_K = 1.0         # emission = band colour x gain x this (sRGB)
PALETTE = [("soot bronze (core)", SOOT), ("dark bronze", BRONZE_DARK), ("old-gold edge", OLD_GOLD),
           ("verdigris shadow", VERDIGRIS_SH), ("eye glow", EYE_CORE), ("cold gold (by the core)", GOLD),
           ("ember core (dim glow)", EMBER_CORE), ("ember light (tongues)", EMBER_LIGHT), ("dead ember (tips)", EMBER),
           ("ember rim (break)", EMBER_RIM)]
UV_SCALE = {"mask": 1.7, "crust": 1.5, "ember": 1.2, "flame": 0.8, "tongue": 0.75, "tail": 0.75, "spark": 0.5}


def mix_hex(a, b, t):
    ca, cb = C.hex_rgb(a), C.hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ca, cb))


# ---- geometry helpers ------------------------------------------------------------------------------------

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


def cut(bm, co, n):
    """Slice bm with the plane (co, n), delete the side n points to, cap the hole flat. Returns (co, n)."""
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6, plane_co=co,
                                 plane_no=n, clear_outer=True)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if edges:
        try:
            bmesh.ops.edgeloop_fill(bm, edges=edges)
        except Exception:  # noqa: BLE001
            bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
    M.recalc(bm)
    return (Vector(co), Vector(n).normalized())


def diamond(r, loc, rot=(0, 0, 0), stretch=1.6):
    b = M.sphere(r, 4, 2)                      # an octahedron: 8 tris
    M.xform(b, scale=(1.0, 1.0, stretch), rot=rot, loc=loc)
    return b


# ---- the model ------------------------------------------------------------------------------------------

class Build:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.heat = {}          # part id -> heat rule for flame_paint()
        self.parts = []

    def head(self, a):
        """The dark core: a small god-mask head of soot-blackened bronze. A flat face plane with a nose ridge
        and a heavy brow, a narrow pointed chin, a low domed crown. The upper-left corner is broken away
        (two cuts: a V notch) and the break is the burning inside (zone ember)."""
        r = HEAD_R
        bm = M.sphere(1.0, 10, 8)
        M.xform(bm, rot=(0, 0, 18))               # a vertex column on the face centre line: the nose ridge
        for v in bm.verts:
            x, y, z = v.co
            if y < -0.5:
                y = -0.5 + (y + 0.5) * 0.4        # flat face plane
            if y < -0.2 and 0.25 < z < 0.6:
                y -= 0.10                         # heavy brow ledge over the eye band
            if z < 0:
                x *= 1.0 - 0.32 * (-z)            # narrow jaw
                if y < -0.2 and z < -0.5:
                    z -= 0.16                     # pointed chin
                    y -= 0.06
            if z > 0.6:
                z *= 1.06
            v.co = Vector((x * r * 1.02, y * r * 0.94, z * r * 1.04))
        M.recalc(bm)
        # the break: a V notch off the upper-left corner, shallower than before (review fix: it is a dim ember
        # socket now, so the gold eye slit is the one focal point, and the dark mask stays whole)
        planes = [cut(bm, Vector((0.58, -0.50, 0.64)).normalized() * 0.915 * r, (0.58, -0.50, 0.64)),
                  cut(bm, Vector((0.90, -0.10, 0.42)).normalized() * 0.945 * r, (0.90, -0.10, 0.42))]
        M.noise_displace(bm, 0.004, freq=12.0, seed=SEED + 1)
        tilt = Matrix.Translation(CORE) @ Matrix.Rotation(math.radians(-FACE_TILT), 4, "X")
        M.xform(bm, matrix=tilt)
        planes = [(tilt @ co, (tilt.to_3x3() @ n).normalized()) for co, n in planes]
        face_n = (tilt.to_3x3() @ Vector((0, -1, 0))).normalized()
        self.face_n = face_n
        self.planes = planes

        def zone_of(f):
            c = f.calc_center_median()
            if any(abs((c - co).dot(n)) < 0.006 and f.normal.dot(n) > 0.9 for co, n in planes):
                return "ember"
            if f.normal.dot(face_n) > 0.5 and (c - CORE).dot(face_n) > 0.45 * r:
                return "mask"
            return "crust"
        for z, piece in split_by_faces(bm, zone_of).items():
            a.add(piece, z, bone="body", name="head_" + z, shading="flat")
        # the break's centre (for its radial glow) and the face frame (eye decal)
        self.break_c = sum((co for co, _ in planes), Vector()) / len(planes)
        self.face_c = CORE + face_n * (0.5 * 0.94 * r + 0.004)
        # a low war-helm crest from the brow back over the crown (Godworks: the mask is a machine's helm); its
        # old-gold edge is the light line that frames the dark core from the 55 deg camera
        arc = [Vector((0.0, math.sin(math.radians(a_)), math.cos(math.radians(a_)))) for a_ in range(-40, 101, 28)]
        pts = [tilt @ (d * r * 0.97) for d in arc]           # from the brow over the crown to the back
        hts = [0.006, 0.018, 0.024, 0.022, 0.016, 0.006]
        crest = M.tube(pts, [1.0] * len(pts), profile=[(0.0, -0.5), (1.0, 0.0), (0.0, 0.5)],
                       scale_xy=[(h_ + 0.006, 0.024) for h_ in hts], up=(0.0, 0.0, 1.0))
        a.add(crest, "crust", bone="body", name="crest", shading="flat")

    def hood(self, a):
        """The flame hood: a closed teardrop of flame cupping the core from below and behind (head bone).
        Its top sits inside the head, so only a collar of fire around the jaw shows. It is painted by distance
        from the core: cold gold against the mask, dead ember at the bottom tip (review fix)."""
        zb = CZ - 0.215
        prof = [(0.0, zb), (0.065, zb + 0.015), (0.125, CZ - 0.15), (0.158, CZ - 0.085), (0.165, CZ - 0.03),
                (0.135, CZ + 0.02), (0.0, CZ + 0.04)]
        bm = M.lathe(prof, sides=10)
        for v in bm.verts:
            dz = CZ - v.co.z
            if dz > 0:
                v.co.y += 0.9 * dz * dz + 0.3 * max(0.0, dz - 0.15)       # the round bottom leans back
            front = max(0.0, -v.co.y) / 0.18
            if v.co.z > CZ - 0.20:
                v.co.z -= 0.13 * front ** 1.2 * min(1.0, (v.co.z - (CZ - 0.20)) / 0.12)   # open in front: the face shows
            v.co.y += 0.04 * max(0.0, v.co.y) / 0.18 + 0.02               # fuller at the back, the head sits forward
        M.noise_displace(bm, 0.010, freq=9.0, seed=SEED + 2)
        pid = a.add(bm, "flame", bone="head", name="hood", shading="smooth")
        # heat by distance from the core, in mask radii: 1.0 = the mask's surface, 1.22 = the bottom tip
        self.heat[pid] = ("shell", Vector(CORE), HEAD_R * 1.0, HEAD_R * 1.24, 0.0, 0.78, 7.0)

    def tongues(self, a):
        """A ring of flame licks rising around the core's sides and back: out, up, sweeping back, and the tips
        curling in (legs_a / legs_b: two flicker groups)."""
        up, back = Vector((0, 0, 1)), Vector((0, 1, 0))
        self.tongue_tips = []
        for th, h, out, sweep, r, curl, wig, bone in TONGUES:
            t = math.radians(th)
            rad = Vector((math.sin(t), -math.cos(t), 0.0))
            side = up.cross(rad)
            base = CORE + rad * (TONGUE_ROOT * HEAD_R) + Vector((0, 0.04, -0.06))
            pts = [base,
                   base + rad * out * 0.60 + up * h * 0.24 + back * sweep * 0.10 + side * wig * 0.5,
                   base + rad * out * 1.00 + up * h * 0.50 + back * sweep * 0.36 + side * wig,
                   base + rad * (out * 0.95 - curl * 0.40) + up * h * 0.78 + back * sweep * 0.72 - side * wig * 0.6,
                   base + rad * (out * 0.80 - curl) + up * h + back * sweep - side * wig * 0.2]
            pts = M.catmull(pts, 2)
            n = len(pts)
            radii = []
            for i in range(n):
                u = i / (n - 1)
                radii.append(0.0 if i == n - 1 else r * (0.8 + 0.45 * math.sin(math.pi * min(1.0, u * 1.8))) * (1 - u) ** 0.9)
            flat = [(0.62, 1.0)] * n                     # blades: thinner radially, wide around the ring
            bm = M.tube(pts, radii, up=rad, profile=DIAMOND, scale_xy=flat)
            pid = a.add(bm, "tongue", bone=bone, name="tongue_%d" % int(th), shading="auto", sharp_angle=40.0)
            self.heat[pid] = ("curve", [Vector(q) for q in pts], [max(rr, 0.01) for rr in radii], rad, 0.08, 1.0, 0.28)
            self.tongue_tips.append(Vector(pts[-1]))

    def tail(self, a):
        """The forked tail: a flat ribbon of flame streaming back from the hood, curling up at the end, with a
        second lick forking off to the left, and two sparks in its wake (tail bone)."""
        root = Vector((0.0, 0.08, CZ - 0.12))
        path = [root, Vector((0.02, 0.28, CZ - 0.17)), Vector((-0.03, 0.46, CZ - 0.15)),
                Vector((0.0, 0.61, CZ - 0.08)), Vector((0.05, 0.72, CZ + 0.02))]
        pts = M.catmull(path, 2)
        n = len(pts)
        radii = [0.0 if i == n - 1 else 0.125 * (1 - i / (n - 1)) ** 0.85 for i in range(n)]
        flat = [(0.55, 1.0)] * n
        pid = a.add(M.tube(pts, radii, sides=6, up=(0, 0, 1), scale_xy=flat), "tail", bone="tail", name="tail",
                    shading="smooth")
        self.heat[pid] = ("curve", [Vector(q) for q in pts], [max(rr, 0.01) for rr in radii], Vector((0, 0, 1)), 0.2, 1.0,
                          0.22)
        fork0 = Vector(pts[4])
        fk = [fork0, fork0 + Vector((0.07, 0.10, 0.05)), fork0 + Vector((0.11, 0.21, 0.13))]
        fk = M.catmull(fk, 2)
        m = len(fk)
        rr = [0.0 if i == m - 1 else 0.05 * (1 - i / (m - 1)) for i in range(m)]
        pid = a.add(M.tube(fk, rr, sides=5, up=(0, 0, 1), scale_xy=[(0.6, 1.0)] * m), "tail", bone="tail",
                    name="tail_fork", shading="smooth")
        self.heat[pid] = ("curve", [Vector(q) for q in fk], [max(x, 0.01) for x in rr], Vector((0, 0, 1)), 0.55, 1.0, 0.2)
        self.tail_tip = Vector(pts[-1])
        for loc, s, rot in (((0.14, 0.46, CZ + 0.03), 0.040, (20, 10, 30)), ((-0.10, 0.70, CZ + 0.07), 0.034, (-15, 25, 0))):
            pid = a.add(diamond(s, loc, rot), "spark", bone="tail", name="spark", shading="flat")
            self.heat[pid] = ("const", 0.2)       # sparks: the dim ember-core glow

    def build(self, col):
        a = M.Assembly(KEY + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        self.head(a)
        self.hood(a)
        self.tongues(a)
        self.tail(a)
        self.tris = a.tris()
        obj = a.to_object(col)
        self.parts = a.parts
        C.log("%s mesh: %d tris, %d parts" % (KEY, self.tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def pivots(self):
        return {"root": (0.0, 0.0, 0.0), "body": tuple(CORE), "head": tuple(CORE), "legs_a": tuple(CORE),
                "legs_b": tuple(CORE), "tail": (0.0, 0.10, CZ - 0.10)}

    def sockets(self):
        top = max(p.z for p in self.tongue_tips)
        return [("body", "hit_center", tuple(CORE)), ("body", "fx_core", tuple(CORE)),
                ("body", "fx_mouth", tuple(self.face_c)), ("body", "head_top", (0.0, 0.0, top + 0.16))]

    # -- paint --
    def recipes(self):
        flat_flame = dict(edge=0.0, cavity=0.0, ao=0.0, planes=0.0, parts=0.0, brush=0.0)
        return {
            # the face: soot-blackened god-bronze, broad value planes, dull old-gold edge strokes (the chipped
            # soot), verdigris in the cavities; the chin sinks into shadow. Review fix: one step darker and fewer
            # edge strokes, so the whole mask reads as ONE dark shape at 35 px with the eye slit as its light
            "mask": P.zone(base=mix_hex(SOOT, BRONZE_DARK, 0.5), shadow=VERDIGRIS_SH, light=OLD_GOLD, planes=0.2,
                           parts=0.0, brush=0.06, brush_freq=5.0, edge=0.5, edge_width=0.008, edge_breakup=0.45,
                           cavity=0.8, cavity_width=0.007, ao=0.45,
                           gradient={"axis": (0, 0, 1), "range": (CZ + 0.01, CZ - 0.16), "color": "shadow", "amount": 0.4}),
            # the crown and the back of the head: darker soot, dark bronze edges
            "crust": P.zone(base=SOOT, shadow=VERDIGRIS_SH, light=mix_hex(BRONZE_DARK, OLD_GOLD, 0.35), planes=0.18,
                            parts=0.0, brush=0.06, brush_freq=5.0, edge=0.6, edge_width=0.009, edge_breakup=0.4,
                            cavity=0.8, cavity_width=0.007, ao=0.45),
            # the broken corner: the charred inside of the head, burnt soot with a rust cast and NO glow (review
            # fix: it was a white-gold light that competed with the eye; a dim ember glow still covered a third
            # of the head the 55 deg camera sees and cut the dark mask to a crescent). The notch reads in the
            # mask's outline against the fire; the eye slit is the one light on the mask
            "ember": P.zone(base=mix_hex(SOOT, EMBER_RIM, 0.45), shadow="#140A07", light=mix_hex(EMBER_RIM, EMBER, 0.4),
                            planes=0.12, parts=0.0, brush=0.05, brush_freq=6.0, edge=0.0, cavity=0.5,
                            cavity_width=0.006, ao=0.4,
                            gradient={"center": tuple(self.break_c), "range": (0.07, 0.0), "color": "light",
                                      "amount": 0.35}),
            # flame zones: repainted by flame_paint() (heat bands); these recipes only keep the painter happy
            "flame": P.zone(base=GOLD, **flat_flame), "tongue": P.zone(base=EMBER_LIGHT, **flat_flame),
            "tail": P.zone(base=EMBER_LIGHT, **flat_flame), "spark": P.zone(base=EMBER_CORE, **flat_flame),
        }

    def face_frame(self):
        z = self.face_n
        x = Vector((1.0, 0.0, 0.0))
        y = z.cross(x).normalized()
        o = self.face_c
        return Matrix(((x.x, y.x, z.x, o.x), (x.y, y.y, z.y, o.y), (x.z, y.z, z.z, o.z), (0, 0, 0, 1)))

    def decals(self):
        """Few, bold lines (a web of small cracks turns to speckle at 35 px): the one slanted, glowing eye slit
        on the right half of the face (THE focal point, the only light on the mask) and two painted, unlit
        dead-ember cracks over the crown from the broken corner (close-up detail; they fade out at game size)."""
        rng = random.Random(SEED + 100)
        burnt = "#0E0A07"
        fr = self.face_frame()
        out = []
        # the eye: an angry slant (the outer end high) under the brow, about 5 x 2 px at 1x (review fix: it was
        # 3 x 1.5 px), a pale cold gold on screen (EYE_GOLD / EYE_CORE), never the saturated player gold. A burnt
        # rim cuts it out of the dark mask
        eye = [[(-0.122, 0.050), (-0.090, 0.036), (-0.056, 0.022), (-0.026, 0.010)]]
        out.append(P.decal_lines(eye, fr, 0.042, zones=["mask"], color=GOLD, rim=burnt, rim_width=0.030,
                                 emit={"color": EYE_GOLD, "core": EYE_CORE}, facing=0.2, depth=(-0.07, 0.09)))
        # two cracks over the crown from the break toward the back (seen from the 55 deg camera): painted dead
        # ember, no emission (review fix: glowing cracks broke the dark crown into speckle)
        top = Matrix.Translation((0.0, 0.0, CZ + 0.26))
        crown = M.crack_lines(rng, start=(0.06, -0.024), direction=128, length=0.17, step=0.024, jag=0.4,
                              branches=1, branch_len=0.35, depth=1)
        crown += M.crack_lines(rng, start=(0.085, 0.024), direction=72, length=0.12, step=0.024, jag=0.4, branches=0,
                               depth=0)
        out.append(P.decal_lines(crown, top, 0.018, zones=["crust", "mask"], color=EMBER, rim=burnt, rim_width=0.034,
                                 emit=None, facing=0.3, depth=(-0.3, 0.0)))
        return out


# ---- the painted flame (installed around gfa_paint.paint for this build only) -------------------------------

def _band_mix(h, stops, soft):
    """Pick flat bands along h: stops [(start, value (k,) array)], soft = half-width of each border."""
    out = np.repeat(np.asarray(stops[0][1], dtype=np.float32)[None], len(h), 0)
    for start, val in stops[1:]:
        out = P.mix(out, np.asarray(val, dtype=np.float32), P.smoothstep(start - soft, start + soft, h))
    return out


def curve_coords(q, pts, widths, up):
    """(u along the centreline 0..1 by arc length, lateral offset across the blade / local width) for points q
    (N, 3) near a swept part: the nearest centreline sample gives u; the offset is measured along the blade's
    wide axis (tangent x the frame normal toward `up`, as gfa_model.tube builds it)."""
    P_ = np.array([tuple(p) for p in pts], dtype=np.float32)
    n = len(P_)
    T = np.zeros_like(P_)
    for i in range(n):
        d = P_[min(n - 1, i + 1)] - P_[max(0, i - 1)]
        T[i] = d / (np.linalg.norm(d) + 1e-9)
    upv = np.asarray(tuple(up), dtype=np.float32)
    Nn = upv[None] - T * (T @ upv)[:, None]
    Nn /= np.linalg.norm(Nn, axis=1, keepdims=True) + 1e-9
    B = np.cross(T, Nn)
    seg = np.linalg.norm(np.diff(P_, axis=0), axis=1)
    s_ = np.concatenate([[0.0], np.cumsum(seg)]) / max(1e-6, seg.sum())
    # nearest point on the polyline (segment projection)
    best_d = np.full(len(q), 1e9, dtype=np.float32)
    best_u = np.zeros(len(q), dtype=np.float32)
    best_a = np.zeros(len(q), dtype=np.float32)
    W = np.asarray(widths, dtype=np.float32)
    for i in range(n - 1):
        a, b = P_[i], P_[i + 1]
        ab = b - a
        L2 = float(ab @ ab) + 1e-12
        t = np.clip(((q - a) @ ab) / L2, 0.0, 1.0)
        c = a + t[:, None] * ab
        d = np.linalg.norm(q - c, axis=1)
        m = d < best_d
        if not m.any():
            continue
        best_d[m] = d[m]
        best_u[m] = s_[i] + (s_[i + 1] - s_[i]) * t[m]
        bi = B[i] * (1 - t[m])[:, None] + B[i + 1] * t[m][:, None]
        wi = W[i] * (1 - t[m]) + W[i + 1] * t[m]
        best_a[m] = ((q[m] - c[m]) * bi).sum(1) / np.maximum(wi, 0.008)
    return best_u, np.clip(best_a, -1.2, 1.2)


def flame_paint(orig, heat_rules):
    """gfa_paint.paint wrapper: paint everything as usual, then repaint the flame zones as FLAT HEAT BANDS
    (hand-painted fire, not a CG gradient). Heat per texel comes from the part's own rule: along each lick
    (arc length on its centreline) with the blade's edges cooler than its centre (a hot stripe up every
    tongue), or down the hood from the core. Smooth lick waves across the flame bend the band borders into
    flame fingers; a faint wobble keeps them brushy. Base colour and emission per band (BANDS)."""
    def paint(maps, zones_order, recipes, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes, dist_convex, dist_concave, decals, seed)
        fz = [zones_order.index(z) for z in FLAME_ZONES if z in zones_order]
        idx = np.nonzero(np.isin(maps["zone"], fz))[0]
        p = maps["pos"][idx].astype(np.float32)
        pid = maps["part"][idx]
        h = np.zeros(len(idx), dtype=np.float32)
        rng = random.Random(seed + 61)
        for k, rule in heat_rules.items():
            s = pid == k
            if not s.any():
                continue
            q = p[s]
            ph1, ph2 = rng.uniform(0, 6.283), rng.uniform(0, 6.283)
            if rule[0] == "curve":
                pts, widths, up, t0, t1, edge = rule[1:]
                u, a = curve_coords(q, pts, widths, up)
                wave = 0.5 * np.sin(a * 4.4 + ph1) + 0.3 * np.sin(a * 9.1 + ph2)      # licks across the blade
                h[s] = t0 + (t1 - t0) * u ** 1.25 + edge * np.abs(a) ** 2 + 0.07 * wave * (0.4 + u)
            elif rule[0] == "hood":
                z_top, z_bot, t0, t1, licks = rule[1:]
                u = np.clip((z_top - q[:, 2]) / (z_top - z_bot), 0.0, 1.0)
                ang = np.arctan2(q[:, 0], -q[:, 1])
                wave = 0.55 * np.sin(ang * licks + ph1) + 0.3 * np.sin(ang * (licks * 2 + 1) + ph2)
                h[s] = t0 + (t1 - t0) * u ** 1.1 + 0.10 * wave * (0.35 + u)
            elif rule[0] == "shell":
                # by distance from a centre (r_in -> r_out): the cold gold hugs the mask, the ember falls away
                c0, r_in, r_out, t0, t1, licks = rule[1:]
                dvec = q - np.asarray(tuple(c0), dtype=np.float32)[None]
                u = np.clip((np.linalg.norm(dvec, axis=1) - r_in) / (r_out - r_in), 0.0, 1.0)
                ang = np.arctan2(dvec[:, 0], -dvec[:, 1])
                wave = 0.55 * np.sin(ang * licks + ph1) + 0.3 * np.sin(ang * (licks * 2 + 1) + ph2)
                h[s] = t0 + (t1 - t0) * u + 0.08 * wave * (0.3 + u)
            else:
                h[s] = rule[1]
        wob = P.spread01(P.fbm(p, 24.0, 1, seed=seed + 62))
        h = h + 0.025 * (wob - 0.5)
        cols = _band_mix(h, [(s0, P.hex3(hx)) for s0, hx, _, _ in BANDS], 0.010)
        cols = cols * (1.0 + 0.08 * (P.fbm(p, 8.0, 2, seed=seed + 63) - 0.5))[:, None]   # a faint brush drift
        gain = _band_mix(h, [(s0, np.array([g], np.float32)) for s0, _, g, _ in BANDS], 0.010)[:, 0]
        kb = _band_mix(h, [(s0, np.array([k], np.float32)) for s0, _, _, k in BANDS], 0.010)[:, 0]
        # glowing bands keep a dim base (the emission carries their colour); the painted ember bands carry the
        # full colour in the base, lit by the engine's toon ramp like the mask
        base[idx] = np.clip(cols * kb[:, None], 0, 1)
        emis[idx] = np.clip(cols * (gain * FLAME_EMIT_K)[:, None], 0, 1)
        return base, emis
    return paint


# ---- clips ------------------------------------------------------------------------------------------------

def pulse(t, t0, w):
    d = ((t - t0 + 0.5) % 1.0) - 0.5
    return math.exp(-(d / w) ** 2)


def sharp(x, k=0.65):
    return math.copysign(abs(x) ** k, x)


def flick_scale(f, amp=0.24):
    """Tongue-group scale for a flicker value f in about [-1, 1]: taller and narrower when it flares."""
    s = 1.0 + amp * f
    return (1.0 - 0.28 * (s - 1.0), s, 1.0 - 0.1 * (s - 1.0))


def make_clips(arm):
    sin, tau = math.sin, 2 * math.pi
    fr = {}

    # FLICKER: two tongue groups flare and gutter out of phase on integer harmonics (so the loops stay
    # seamless), sharpened so the flame snaps rather than breathes; the hood pulses, the tail whips; small
    # erratic darts (jinks) of the whole spirit.
    def idle(t):
        w = tau * t
        fa = sharp(0.55 * sin(3 * w) + 0.30 * sin(5 * w + 1.3) + 0.15 * sin(8 * w + 0.4)) - 0.9 * pulse(t, 0.56, 0.035)
        fb = sharp(0.55 * sin(3 * w + 3.8) + 0.30 * sin(4 * w + 2.1) + 0.15 * sin(7 * w + 1.7)) - 0.9 * pulse(t, 0.13, 0.035)
        jink = pulse(t, 0.34, 0.035) - 0.8 * pulse(t, 0.71, 0.03)
        return {"root": {"loc": (0.0, 0.035 * sin(w) + 0.01 * sin(3 * w + 1), 0.0), "rot": (0, 0, 3 * sin(w + 0.6))},
                "body": {"loc": (0.04 * jink, 0.012 * sin(2 * w), -0.02 * jink),
                         "rot": (-3 + 3 * sin(w + 0.4), 9 * jink, 4 * sin(w) + 9 * jink)},
                "head": {"scale": (1 + 0.05 * fb, 1 + 0.07 * fa, 1 + 0.05 * fb)},
                "legs_a": {"rot": (-6 + 6 * sin(3 * w), 0, 6 * sin(2 * w + 0.7)), "scale": flick_scale(fa, 0.32)},
                "legs_b": {"rot": (-6 + 6 * sin(3 * w + 2), 0, -6 * sin(2 * w + 1.9)), "scale": flick_scale(fb, 0.32)},
                "tail": {"rot": (4 * sin(2 * w + 0.5), 14 * sin(w + 0.8) + 6 * sin(3 * w) - 14 * jink, 0),
                         "scale": (1, 1, 1 + 0.1 * sin(3 * w + 1))}}

    def move(t):
        w = tau * t
        fa = sharp(0.6 * sin(2 * w) + 0.4 * sin(3 * w + 0.9))
        fb = sharp(0.6 * sin(2 * w + 3.4) + 0.4 * sin(3 * w + 2.6))
        return {"root": {"loc": (0.03 * sin(w), 0.025 * sin(2 * w + 0.5), 0.0), "rot": (0, 6 * sin(w + 0.3), -10 * sin(w))},
                "body": {"rot": (12 + 3 * sin(2 * w), 0, 0)},
                "head": {"rot": (-10, 0, 0), "scale": (1 + 0.04 * fb, 1 + 0.06 * fa, 1.12)},
                "legs_a": {"rot": (-24 + 7 * sin(2 * w), 0, 6 * sin(w)), "scale": flick_scale(fa, 0.34)},
                "legs_b": {"rot": (-24 + 7 * sin(2 * w + 2), 0, -6 * sin(w + 1)), "scale": flick_scale(fb, 0.34)},
                "tail": {"rot": (-8 + 4 * sin(2 * w), 22 * sin(w + 0.9), 0), "scale": (1, 1, 1.22 + 0.1 * sin(2 * w))}}

    rest = {}
    tongues = lambda s, rx=0.0, rz=0.0: {"legs_a": {"scale": s, "rot": (rx, 0, rz)}, "legs_b": {"scale": s, "rot": (rx, 0, -rz)}}  # noqa: E731
    # windup: the flame gutters inward (it draws breath), then flares wide and the spirit rears back
    gutter = RIG.merge({"root": {"loc": (0, -0.03, 0)}, "body": {"rot": (-6, 0, 0), "scale": 0.92},
                        "head": {"scale": (0.85, 0.8, 0.85)}, "tail": {"rot": (6, 0, 0), "scale": (0.9, 0.9, 0.75)}},
                       tongues((0.82, 0.6, 0.82), 6.0))
    flare = RIG.merge({"root": {"loc": (0, 0.05, 0)}, "body": {"loc": (0, 0, -0.08), "rot": (-16, 0, 0), "scale": 1.06},
                       "head": {"scale": (1.15, 1.25, 1.15)}, "tail": {"rot": (-22, 0, 0), "scale": (1.1, 1.1, 1.1)}},
                      tongues((1.25, 1.42, 1.2), -10.0, 12.0))
    loaded = RIG.merge(flare, {"body": {"loc": (0, 0, -0.10), "rot": (-19, 0, 0), "scale": 1.08}},
                       tongues((1.3, 1.5, 1.22), -12.0, 14.0))
    # attack: a dart forward with the flame streaming back, a head-butt of fire, recoil
    dart = RIG.merge({"root": {"loc": (0, -0.04, 0)}, "body": {"loc": (0, 0, 0.30), "rot": (22, 0, 0)},
                      "head": {"scale": (0.95, 1.0, 1.3)}, "tail": {"rot": (-6, 0, 0), "scale": (0.9, 0.9, 1.45)}},
                     tongues((0.92, 1.1, 1.35), -38.0))
    strike = RIG.merge(dart, {"body": {"loc": (0, 0, 0.34), "rot": (10, 0, 0), "scale": 1.08}},
                       tongues((1.35, 1.35, 1.3), -20.0, 16.0))
    recoil = RIG.merge({"body": {"loc": (0, 0, 0.1), "rot": (-6, 0, 0)}}, tongues((0.9, 0.9, 0.9), -6.0))
    # hit: knocked back, the flame blown sideways and guttering, then it flares back up
    flinch = {"root": {"loc": (0, 0.02, 0)}, "body": {"loc": (0.02, 0.02, -0.08), "rot": (-14, 10, -16)},
              "head": {"scale": (0.8, 0.75, 0.8)},
              "legs_a": {"scale": (0.78, 0.6, 0.78), "rot": (-30, 0, -25)}, "legs_b": {"scale": (0.8, 0.68, 0.8), "rot": (-28, 0, -30)},
              "tail": {"rot": (-10, 35, 0)}}
    settle = RIG.merge({"body": {"rot": (4, -3, 5)}, "tail": {"rot": (0, -12, 0)}}, tongues((1.12, 1.2, 1.1), -8.0))
    # death (spark-burst): the flame gutters, the core swells, the fire BURSTS outward and is gone (the burst
    # VFX is the engine's, at fx_core), and the blackened mask tumbles to the ground and crumbles
    d_gutter = RIG.merge({"root": {"loc": (0, -0.04, 0)}, "body": {"rot": (-12, 8, 6), "scale": 0.94},
                          "head": {"scale": 0.8}, "tail": {"scale": (0.8, 0.8, 0.7)}}, tongues((0.7, 0.5, 0.7), 8.0))
    d_swell = RIG.merge({"root": {"loc": (0, 0.02, 0)}, "body": {"rot": (-6, 0, 0), "scale": 1.18},
                         "head": {"scale": 0.55}, "tail": {"scale": (0.5, 0.5, 0.5)}}, tongues((0.4, 0.35, 0.4)))
    d_burst = RIG.merge({"body": {"rot": (-20, 0, 0), "scale": 1.1}, "head": {"scale": 1.55},
                         "tail": {"scale": (1.5, 1.5, 1.5), "rot": (-30, 40, 0)}}, tongues((1.75, 1.7, 1.75), -20.0, 35.0))
    tiny = 0.02
    d_gone = RIG.merge({"body": {"loc": (0.02, -0.10, 0.02), "rot": (-60, 20, 25), "scale": 1.0},
                        "head": {"scale": tiny}, "tail": {"scale": tiny}}, tongues(tiny))
    d_fall = RIG.merge(d_gone, {"body": {"loc": (0.05, -0.44, 0.05), "rot": (-140, 40, 30), "scale": 0.75}})
    d_crumble = RIG.merge(d_fall, {"body": {"loc": (0.05, -0.50, 0.05), "rot": (-150, 40, 30), "scale": 0.35}})
    d_end = RIG.merge(d_crumble, {"body": {"scale": tiny, "loc": (0.05, -0.52, 0.05)}})

    RIG.cycle_clip(arm, KEY, "idle@loop", 48, idle)
    RIG.cycle_clip(arm, KEY, "move@loop", 18, move)
    RIG.keyed_clip(arm, KEY, "windup", [(0, rest), (5, gutter), (11, flare), (15, loaded)])
    RIG.keyed_clip(arm, KEY, "attack", [(0, loaded), (3, dart), (5, strike), (9, recoil), (15, rest)])
    RIG.keyed_clip(arm, KEY, "hit", [(0, rest), (2, flinch), (5, settle), (9, rest)])
    RIG.keyed_clip(arm, KEY, "death", [(0, rest), (4, d_gutter), (8, d_swell), (11, d_burst), (14, d_gone),
                                       (19, d_fall), (22, d_crumble), (24, d_end), (25, d_end)])
    fr.update({"idle@loop": [0, 8, 16, 24, 32, 40], "move@loop": [0, 3, 6, 9, 12, 15], "windup": [0, 5, 11, 15],
               "attack": [0, 3, 5, 9, 15], "hit": [0, 2, 5, 9], "death": [0, 4, 8, 11, 14, 19, 24]})
    return [RIG.clip_name(KEY, c) for c in SPEC.ENEMY_CLIPS_REQUIRED], fr


# ---- review rendering ---------------------------------------------------------------------------------------

FLOOR_BRIGHT = "#B4A68C"       # a bright flagstone (the brief: the dark core must read on bright floors)


def glow_faces(obj, thresh=0.1):
    """Face indices of obj whose emissive texture is lit at the face's UV centre. The engine's toon shader adds
    the emission AFTER the ink edge, so glowing surfaces carry no ink line; the preview's ink hull drops them."""
    mat = obj.material_slots[0].material if obj.material_slots else None
    img = R._tex_of(mat, "Emission Color")
    if img is None:
        return []
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    me = obj.data
    uvl = me.uv_layers.active.data
    out = []
    for p in me.polygons:
        u = sum(uvl[i].uv.x for i in p.loop_indices) / p.loop_total
        v = sum(uvl[i].uv.y for i in p.loop_indices) / p.loop_total
        c = px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int(u * w))), :3]
        if float(c.max()) > thresh:
            out.append(p.index)
    return out


class Preview:
    """R.toon_preview with the ink hull trimmed off the glowing faces (engine-faithful: emission is added after
    the ink), for the build's mesh and for imported GLB copies."""

    _cache = {}

    def __init__(self, objs, ink=0.006, flat=None):
        self.objs, self.ink, self.flat = objs, ink, flat or {}
        self.glow = {}
        for o in objs:
            if o.type != "MESH" or o.name in self.flat:
                continue
            k = (o.data.name.split(".")[0], len(o.data.polygons))     # copies share their source's faces
            if k not in Preview._cache:
                Preview._cache[k] = glow_faces(o)
            self.glow[o.name] = Preview._cache[k]

    def __enter__(self):
        self.cm = R.toon_preview(self.objs, ink=self.ink, flat=self.flat)
        hulls = self.cm.__enter__()
        for h in hulls:
            src = h.name[:-4]
            faces = self.glow.get(src)
            if not faces:
                continue
            bm = bmesh.new()
            bm.from_mesh(h.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in faces if i < len(bm.faces)], context="FACES")
            bm.to_mesh(h.data)
            bm.free()
        return hulls

    def __exit__(self, *exc):
        return self.cm.__exit__(*exc)


def _emit_mat(name, hexc):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = C.hex_linear(hexc)
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def floor(hexc=R.FLOOR):
    f = bpy.data.objects.get("GFA_FLOOR")
    if f is None:
        me = bpy.data.meshes.new("GFA_FLOOR")
        me.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
        f = bpy.data.objects.new("GFA_FLOOR", me)
        bpy.context.scene.collection.objects.link(f)
        me.materials.append(_emit_mat("GFA_FLOOR", hexc))
    f.data.materials[0] = _emit_mat("GFA_FLOOR_" + hexc.lstrip("#"), hexc)
    return f


def blob_shadow(name, loc, radius=0.32, alpha=0.55):
    """A soft dark disc on the ground under a hovering copy (the client draws a blob shadow under every enemy,
    scene.rs Kit::shadow): it shows the hover height through the game camera."""
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=radius, segments=24)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (loc[0], loc[1], 0.004)
    m = bpy.data.materials.get("GFA_BLOB")
    if m is None:
        m = bpy.data.materials.new("GFA_BLOB")
        nt = m.node_tree
        nt.nodes.clear()
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        mix = nt.nodes.new("ShaderNodeMixShader")
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "LENGTH"
        nt.links.new(tc.outputs["Object"], vm.inputs[0])
        cr = nt.nodes.new("ShaderNodeMapRange")
        cr.inputs["From Min"].default_value = radius * 0.45
        cr.inputs["From Max"].default_value = radius
        cr.inputs["To Min"].default_value = alpha
        cr.inputs["To Max"].default_value = 0.0
        nt.links.new(vm.outputs["Value"], cr.inputs["Value"])
        nt.links.new(cr.outputs["Result"], mix.inputs["Fac"])
        nt.links.new(tr.outputs[0], mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], o.inputs[0])
    me.materials.append(m)
    return ob


def game_dir():
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    return Vector((0.0, -math.cos(pitch), math.sin(pitch)))


def game_render(objs, flat, path, w, h, target, sil_path=None, ink=0.012, samples=16, view_h=SPEC.GAME_VIEW_HEIGHTS[0],
                floor_hex=R.FLOOR):
    """The game camera (orthographic, 55 deg pitch, yaw 0) at TRUE 1080p pixel size, a w x h crop."""
    scene = bpy.context.scene
    fl = floor(floor_hex)
    R.setup_cycles(scene, samples, bg=floor_hex)
    fl.hide_render = False
    with Preview(objs, ink=ink, flat=flat):
        R.aim(scene, target, game_dir(), view_h * max(w, h) / SPEC.SCREEN_H)
        R.render(scene, path, w, h)
    if sil_path:
        R.setup_workbench_flat(scene)
        fl.hide_render = True
        blobs = [o for o in bpy.data.objects if o.name.startswith("GFA_BLOB")]
        for b in blobs:
            b.hide_render = True
        R.aim(scene, target, game_dir(), view_h * max(w, h) / SPEC.SCREEN_H)
        R.render(scene, sil_path, w, h)
        fl.hide_render = False
        for b in blobs:
            b.hide_render = False
    return path


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


def size_compare(mesh, work, top_z):
    """Side view of the wisp beside the 2.2 m hero mannequin: the hero's waist line (1.1 m, the swarm
    ceiling), the wisp's top and the ground."""
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (0.0, 1.2, 0.0)
    bpy.context.view_layer.update()
    bars = [guide_bar("GUIDE_waist", (0.8, -0.8, 1.1), (0.8, 1.8, 1.1), 0.012, "#D9CFA6"),
            guide_bar("GUIDE_top", (0.8, -0.8, top_z), (0.8, 0.9, top_z), 0.008, GOLD_LIGHT),
            guide_bar("GUIDE_ground", (0.8, -0.8, 0.0), (0.8, 1.8, 0.0), 0.01, "#6B5A50")]
    R.setup_cycles(scene, 12)
    with Preview([mesh, man], ink=0.008, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (0.0, 0.5, 1.12), (1.0, 0.0, 0.0), 2.6)
        p = R.render(scene, os.path.join(work, "%s_size_side.png" % KEY), 420, 420)
    C.remove_objects([man] + bars)
    return p


def turnaround(mesh, work, size=400):
    scene = bpy.context.scene
    views = R.CREATURE_VIEWS
    pts = R._points([mesh])
    ext = max(max(R.frame(pts, d)[1:]) for d in views.values())
    R.setup_cycles(scene, 12)
    out = {}
    with Preview([mesh], ink=0.006):
        for name, d in views.items():
            c, _, _ = R.frame(pts, d)
            R.aim(scene, c, d, ext * 1.12)
            out[name] = R.render(scene, os.path.join(work, "%s_turn_%s.png" % (KEY, name)), size)
    return out


def clip_strips(arm, mesh, work, frames):
    scene = bpy.context.scene
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    pts = R._points([mesh])
    d = R.CREATURE_VIEWS["34_front"]
    c, w, h = R.frame(pts, d)
    ext = max(w, h) * 1.5
    R.setup_cycles(scene, 10)
    out = []
    with Preview([mesh], ink=0.005):
        for clip, fl in frames.items():
            for f in fl:
                RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
                R.aim(scene, c, d, ext)
                p = os.path.join(work, "%s_clip_%s_f%02d.png" % (KEY, clip.replace("@", "_"), f))
                out.append((clip, f, R.render(scene, p, 190)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def game_poses(arm, mesh, work, poses, px=76, floor_hex=R.FLOOR, tag=""):
    """Poses through the game camera at true pixel size (px x px crops), the wisp turned 3/4 to the camera."""
    out = []
    arm.rotation_euler = (0.0, 0.0, math.radians(-35.0))
    blob = blob_shadow("GFA_BLOB_pose", (0.0, 0.0))
    for label, clip, f in poses:
        if clip:
            RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
        else:
            RIG.unmute_none(arm)
        bpy.context.view_layer.update()
        slug = "".join(ch if ch.isalnum() else "_" for ch in label).strip("_")
        p = os.path.join(work, "%s_game%s_%s.png" % (KEY, tag, slug))
        game_render([mesh], {}, p, px, px, (0.0, 0.12, 0.36), samples=16, floor_hex=floor_hex)
        out.append((label, p))
    RIG.unmute_none(arm)
    bpy.context.scene.frame_set(0)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    C.remove_objects([blob])
    return out


def review(b, arm, mesh, rep, reports, work, tex, notes, frames):
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    turn = turnaround(mesh, work)
    top_z = rep["bounds"]["max"][1]
    size_p = size_compare(mesh, work, top_z)
    strips = clip_strips(arm, mesh, work, frames)
    # in-game camera: facing the camera 3/4 beside the mannequin, then moving away; the bright-floor check
    ing = []
    for label, yaw, fl in (("facing the camera", -35.0, R.FLOOR), ("moving away", 145.0, R.FLOOR),
                           ("bright floor", -35.0, FLOOR_BRIGHT)):
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.0, 0.25, 0.0)
        blob = blob_shadow("GFA_BLOB_ing", (0.0, 0.0))
        bpy.context.view_layer.update()
        stem = "%s_ingame_%s" % (KEY, label.split()[0])
        r = game_render([mesh, man], {man.name: R.MANNEQUIN}, os.path.join(work, stem + ".png"), 150, 150,
                        (-0.45, 0.2, 0.7), sil_path=os.path.join(work, stem + "_sil.png"), floor_hex=fl)
        C.remove_objects([man, blob])
        ing.append((label, r, os.path.join(work, stem + "_sil.png")))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    poses = [("rest", None, 0), ("drift", "move@loop", 4), ("flicker (idle)", "idle@loop", 10),
             ("wind-up (loaded)", "windup", 15), ("attack (dart)", "attack", 5), ("hit", "hit", 2),
             ("death (swell)", "death", 8), ("death (burst)", "death", 11), ("death (mask falls)", "death", 19)]
    gp = game_poses(arm, mesh, work, poses)
    gp_bright = game_poses(arm, mesh, work, poses[:4], floor_hex=FLOOR_BRIGHT, tag="_bright")
    flick = game_poses(arm, mesh, work, [("f%d" % f, "idle@loop", f) for f in range(0, 48, 6)], tag="_flick")
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Emberwisp  (emberwisp.glb)",
        "subtitle": "Swarm Wisp | Fallen Godworks | Cinder Wastes | verb FLICKER | GF_Swarm_v1 | "
                    "\"Erratic sparks that burst when snuffed.\"",
        "width": 1600,
        "sections": [
            {"label": "Turnaround (rest pose) - toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6; "
                      "no ink on glowing faces, as in the engine)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn.items()]},
            {"label": "Size vs the 2.2 m hero (waist line = swarm ceiling) | game camera, 55 deg, %.1f px/m, TRUE size 1x, "
                      "then 3x (+ blob shadow)" % ppm,
             "height": None, "images": [{"path": size_p, "label": "side: top at %.2f m = %.2f x hero" % (top_z, top_z / 2.2)},
                                        {"path": ing[0][1], "label": "1x"},
                                        {"path": ing[0][1], "label": "3x " + ing[0][0], "scale": 3},
                                        {"path": ing[1][1], "label": "3x " + ing[1][0], "scale": 3}]},
            {"label": "Bright floor (the dark core keeps the read) and the game-size silhouette, 3x nearest", "height": None,
             "images": [{"path": ing[2][1], "label": "3x on a bright floor %s" % FLOOR_BRIGHT, "scale": 3},
                        {"path": ing[0][2], "label": "silhouette 3x", "scale": 3}]},
            {"label": "Key poses through the game camera at TRUE pixel size (3x nearest)", "height": None,
             "images": [{"path": p, "label": lb, "scale": 3} for lb, p in gp]},
            {"label": "The same on the bright floor, and FLICKER: idle@loop every 6 frames (0.2 s) at game size (3x)", "height": None,
             "images": [{"path": p, "label": lb, "scale": 3} for lb, p in gp_bright]
                + [{"path": p, "label": "idle " + lb, "scale": 3} for lb, p in flick]},
            {"label": "Clip key frames (3/4 front): idle@loop, move@loop (drift), windup, attack, hit, death", "height": 150,
             "images": [{"path": p, "label": "%s f%d" % (cl, f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220, "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    return R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)


# ---- the horde: 40 emberwisps mixed with clinkers, imported from the shipped GLBs ---------------------------

CLINKER_LOOKS = ("clinker", "clinker_v1", "clinker_v2", "clinker_v3")
CROWD_CLIPS = SPEC.ENEMY_CLIPS_REQUIRED


def import_glb(key, path=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path or C.model_path("enemy", key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == "ARMATURE")
    mesh = next(o for o in new if o.type == "MESH")
    arm.name, mesh.name = key + "_ARM", key + "_MESH"
    acts = {}
    for c in CROWD_CLIPS:
        a = bpy.data.actions.get("%s_%s" % (key, c))
        if a is None:
            raise RuntimeError("%s.glb has no clip %s_%s" % (key, key, c))
        a.use_fake_user = True
        acts[c] = a
    arm.animation_data_clear()
    for o in new:
        if o.type == "EMPTY":
            o.hide_render = True
    arm.location = (200.0 + 5 * len(bpy.data.objects), 200.0, 0.0)
    return {"key": key, "arm": arm, "mesh": mesh, "acts": acts,
            "frames": {c: a.frame_range[1] for c, a in acts.items()}}


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
    # the glTF importer leaves its objects in QUATERNION mode (rotation_euler would be ignored, and every copy
    # faced the same way): turn the imported rest rotation about world Z (as enemies/ashrunner_crowd.py)
    q0 = v["arm"].rotation_quaternion.copy() if v["arm"].rotation_mode == "QUATERNION" else \
        v["arm"].rotation_euler.to_quaternion()
    a2.rotation_mode = "QUATERNION"
    a2.rotation_quaternion = Quaternion((0.0, 0.0, 1.0), yaw) @ q0
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


def upscale(src, dst, k):
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


def crowd_review(reports, work):
    """40 emberwisps and 24 clinkers (6 of each look) converging on two heroes, posed from the actions inside
    the shipped GLBs, through the game camera at true 1080p pixel size (+ silhouette, + the 4-player view)."""
    C.reset_scene(fps=FPS)
    wisp = import_glb(KEY)
    clinkers = [import_glb(k) for k in CLINKER_LOOKS if os.path.isfile(C.model_path("enemy", k))]
    bpy.context.view_layer.update()
    rng = random.Random(41)
    heroes = [Vector((-0.8, -0.2, 0.0)), Vector((0.9, 0.45, 0.0))]
    mans = []
    for hp, aimd in zip(heroes, ((0.4, 0.9, 0.0), (0.9, 0.4, 0.0))):
        m = R.mannequin(aim_dir=aimd)
        m.location = hp
        mans.append(m)
    n_w, n_c = 40, 6 * len(clinkers)
    pts = []
    tries = 0
    while len(pts) < n_w + n_c and tries < 40000:
        tries += 1
        c = heroes[rng.randrange(2)]
        r = rng.uniform(0.95, 4.6)
        ang = rng.uniform(-0.3 * math.pi, 1.2 * math.pi)
        p = c + Vector((math.cos(ang) * r * 1.2, math.sin(ang) * r, 0.0))
        if any((p - q).length < 0.6 for q in pts) or any((p - h).length < 0.85 for h in heroes):
            continue
        pts.append(p)
    rng.shuffle(pts)
    made, blobs, phases = [], [], []
    for i, p in enumerate(pts):
        is_wisp = i < n_w
        v = wisp if is_wisp else clinkers[(i - n_w) % len(clinkers)]
        tgt = min(heroes, key=lambda h: (h - p).length)
        yaw = face_yaw(p, tgt) + math.radians(rng.uniform(-30, 30))
        u = rng.random()
        if u < 0.62:
            clip = "move@loop"
        elif u < 0.84:
            clip = "idle@loop"
        elif u < 0.91:
            clip = "windup"
        elif u < 0.96:
            clip = "attack"
        else:
            clip = "hit"
        nfr = v["frames"][clip]
        f = rng.uniform(0, nfr) if clip.endswith("@loop") else {"windup": nfr, "attack": 4.0, "hit": 2.0}[clip]
        if is_wisp:
            phases.append(clip)
            blobs.append(blob_shadow("GFA_BLOB_%d" % i, p))
        made += list(spawn(v, p, yaw, clip, f))
    bpy.context.view_layer.update()
    meshes = [o for o in made if o.type == "MESH"]
    flat = {m.name: R.MANNEQUIN for m in mans}
    out = {}
    out["crowd"] = game_render(meshes + mans, flat, os.path.join(work, "%s_crowd_1x.png" % KEY), 600, 450, (0.1, 0.8, 0.4),
                               sil_path=os.path.join(work, "%s_crowd_1x_sil.png" % KEY))
    out["crowd_sil"] = os.path.join(work, "%s_crowd_1x_sil.png" % KEY)
    out["crowd28"] = game_render(meshes + mans, flat, os.path.join(work, "%s_crowd_1x_28.png" % KEY), 470, 350,
                                 (0.1, 0.8, 0.4), view_h=SPEC.GAME_VIEW_HEIGHTS[-1])
    out["crowd_bright"] = game_render(meshes + mans, flat, os.path.join(work, "%s_crowd_1x_bright.png" % KEY), 600, 450,
                                      (0.1, 0.8, 0.4), floor_hex=FLOOR_BRIGHT)
    arms = [o for o in made if o.type == "ARMATURE"]
    C.remove_objects(meshes + blobs)
    for o in arms:
        bpy.data.objects.remove(o)
    C.remove_objects(mans)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    crowd2x = upscale(out["crowd"], os.path.join(reports, "%s_crowd.png" % KEY), 2)
    counts = {c: phases.count(c) for c in set(phases)}
    sections = [
        {"label": "HORDE: 40 emberwisps (%s) + %d clinkers (4 looks), two 2.2 m heroes, TRUE 1080p size" % (
                      ", ".join("%d %s" % (n, c) for c, n in sorted(counts.items(), key=lambda t: -t[1])), n_c),
         "height": None, "images": [{"path": out["crowd"], "label": "1x, one-hero view (22 m = 1080 px), Cinder floor"},
                                    {"path": out["crowd_sil"], "label": "1x silhouette"}]},
        {"label": "The same horde: four-player view (28 m = 1080 px), and on a bright floor", "height": None,
         "images": [{"path": out["crowd28"], "label": "1x, 28 m view"},
                    {"path": out["crowd_bright"], "label": "1x, bright floor %s" % FLOOR_BRIGHT}]},
        {"label": "2x nearest (Cinder floor)", "height": None, "images": [{"path": out["crowd"], "label": "2x", "scale": 2}]},
    ]
    layout = {"title": "Emberwisp horde read (40 copies, mixed with clinkers)",
              "subtitle": "Fallen Godworks spark wisps (warm, hovering, dark mask core) among Unmade clinkers (dark teal "
                          "crawlers) | status %s" % SPEC.STATUS_AI_FINAL,
              "width": 1600, "sections": sections, "swatches": [{"hex": h, "label": n} for n, h in PALETTE],
              "notes": ["Each emberwisp stands on the client's blob shadow (a soft 55 % disc, scene.rs Kit::shadow).",
                        "Every copy (wisps and clinkers) is imported with Blender's glTF importer and posed from its "
                        "own GLB actions: the exported files load, skin and animate."]}
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_crowd_review.png" % KEY), work)
    out["crowd2x"] = crowd2x
    return out


# ---- review-fix metrics: the art review's numbers, measured on a shipped GLB --------------------------------
# Three passes per pose through the game camera at TRUE 1x pixel size (the same framing as game_poses):
#   toon  - the review's toon preview on the Cinder floor (+ blob shadow): the colours the player sees;
#   emis  - the emissive texture x1.6 alone on black: which pixels glow;
#   zone  - Workbench flat, AA off: the mask-head (body bone) black, the flame (head / legs) white, the tail and its
#           sparks grey, background blue: the mask's width against the flame's.
# enemies/emberwisp_fix_sheet.py analyses them (dE to the player gold, glow share, mask width) and draws the
# before / after sheet. Run on any emberwisp GLB, so the pre-fix file is measured with the same code.

METRIC_POSES = [("rest front", None, 0, 0.0), ("rest 3/4", None, 0, -35.0), ("drift", "move@loop", 4, -35.0),
                ("flicker", "idle@loop", 10, -35.0), ("windup", "windup", 15, -35.0), ("attack", "attack", 5, -35.0),
                ("hit", "hit", 2, -35.0), ("death burst", "death", 11, -35.0), ("moving away", "move@loop", 4, 145.0)]
METRIC_PX = 76
METRIC_TARGET = (0.0, 0.12, 0.36)
ZONE_RGB = {"body": (0.0, 0.0, 0.0), "tail": (0.5, 0.5, 0.5), "flame": (1.0, 1.0, 1.0)}


def _emis_only_mat(img, gain=1.6):
    m = bpy.data.materials.new("GFA_EMIS_ONLY")
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    e.inputs["Strength"].default_value = gain
    nt.links.new(t.outputs["Color"], e.inputs["Color"])
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def _zone_mats(mesh):
    """Give a (copied) GLB mesh three flat materials by bone: body (the mask-head), tail (+ sparks), flame."""
    mats = {}
    for k, rgb in ZONE_RGB.items():
        m = bpy.data.materials.get("GFA_ZONE_" + k) or bpy.data.materials.new("GFA_ZONE_" + k)
        m.diffuse_color = (*rgb, 1.0)
        mats[k] = m
    me = mesh.data
    names = {vg.index: vg.name for vg in mesh.vertex_groups}
    order = ["body", "tail", "flame"]
    me.materials.clear()
    for k in order:
        me.materials.append(mats[k])
    idx = np.zeros(len(me.polygons), dtype=np.int32)
    for p in me.polygons:
        v = me.vertices[p.vertices[0]]
        g = max(v.groups, key=lambda gg: gg.weight, default=None)
        bone = names.get(g.group, "") if g else ""
        idx[p.index] = order.index(bone) if bone in ("body", "tail") else 2
    me.polygons.foreach_set("material_index", idx)
    me.update()


def metric_renders(glb, out_dir, tag):
    """Render the three metric passes for every METRIC_POSES pose of `glb` into out_dir; returns the index."""
    C.reset_scene(fps=FPS)
    v = import_glb(KEY, glb)
    scene = bpy.context.scene
    C.ensure_dir(out_dir)
    index = {"glb": glb, "tag": tag, "px": METRIC_PX, "view_height_m": SPEC.GAME_VIEW_HEIGHTS[0],
             "floor": R.FLOOR, "emissive_gain": 1.6, "poses": []}
    ortho = SPEC.GAME_VIEW_HEIGHTS[0] * METRIC_PX / SPEC.SCREEN_H
    for label, clip, f, yaw in METRIC_POSES:
        arm, mesh = spawn(v, (0.0, 0.0, 0.0), math.radians(yaw), clip, f)
        blob = blob_shadow("GFA_BLOB_metric", (0.0, 0.0))
        bpy.context.view_layer.update()
        slug = "".join(ch if ch.isalnum() else "_" for ch in label)
        paths = {k: os.path.join(out_dir, "%s_%s_%s.png" % (KEY, slug, k)) for k in ("toon", "emis", "zone")}
        # 1) toon preview on the Cinder floor with the blob shadow
        game_render([mesh], {}, paths["toon"], METRIC_PX, METRIC_PX, METRIC_TARGET, samples=16)
        # 2) emission x1.6 only, on black
        fl = bpy.data.objects.get("GFA_FLOOR")
        fl.hide_render = True
        blob.hide_render = True
        R.setup_cycles(scene, 16, bg="#000000")
        saved = mesh.material_slots[0].material
        em = _emis_only_mat(R._tex_of(saved, "Emission Color"))
        mesh.material_slots[0].material = em
        R.aim(scene, METRIC_TARGET, game_dir(), ortho)
        R.render(scene, paths["emis"], METRIC_PX, METRIC_PX)
        mesh.material_slots[0].material = saved
        bpy.data.materials.remove(em)
        # 3) zones by bone, Workbench flat, no anti-aliasing
        _zone_mats(mesh)
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light, sh.color_type = "FLAT", "MATERIAL"
        sh.show_cavity = sh.show_shadows = sh.show_object_outline = False
        sh.background_type = "VIEWPORT"
        sh.background_color = (0.0, 0.0, 1.0)
        scene.display.render_aa = "OFF"
        scene.view_settings.view_transform = "Standard"
        R.aim(scene, METRIC_TARGET, game_dir(), ortho)
        R.render(scene, paths["zone"], METRIC_PX, METRIC_PX)
        scene.display.render_aa = "8"
        fl.hide_render = False
        index["poses"].append({"label": label, "clip": clip, "frame": f, "yaw": yaw,
                               **{k: os.path.abspath(p) for k, p in paths.items()}})
        C.remove_objects([mesh, blob])
        bpy.data.objects.remove(arm)
    with open(os.path.join(out_dir, "renders.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(index, fh, indent=1)      # (C.write_json logs a repo-relative path; out_dir may be elsewhere)
    C.log("metric renders", tag, out_dir)
    return index


# ---- preview (flat zone colours, Workbench) -------------------------------------------------------------------

PREVIEW_COLORS = {"mask": "#3A3024", "crust": "#2A231A", "ember": "#3A1C12", "flame": "#D4B45A", "tongue": "#C8663A",
                  "tail": "#A4492A", "spark": "#E08A50"}


def preview(mesh, work):
    import gfa_boss as B
    views = dict(R.CREATURE_VIEWS)
    views["game_front"] = tuple(B.game_dir())
    views["game_back"] = (0.0, math.cos(math.radians(55)), math.sin(math.radians(55)))
    out = B.flat_views([mesh], work, KEY, PREVIEW_COLORS, views, size=360)
    C.log("preview", out)
    return out


MOVE_FRAMES = 18


def status_outputs(reports):
    return [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
            "art/enemies/%s/source/%s.blend" % (KEY, KEY), "art/enemies/%s/textures/%s_basecolor.png" % (KEY, KEY),
            "art/enemies/%s/textures/%s_emissive.png" % (KEY, KEY), "art/enemies/%s/reports/%s_review.png" % (KEY, KEY),
            "art/enemies/%s/reports/%s_crowd_review.png" % (KEY, KEY), "art/enemies/%s/reports/%s_crowd.png" % (KEY, KEY),
            "art/enemies/%s/reports/%s_build_report.json" % (KEY, KEY)]


def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 512, int)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work"))
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    if C.flag(argv, "--crowd-only"):
        crowd_review(reports, work)
        C.log("DONE crowd")
        return
    if C.flag(argv, "--metrics-only"):
        tag = C.opt(argv, "--tag", "after")
        metric_renders(os.path.abspath(C.opt(argv, "--glb", C.model_path(KIND, KEY))),
                       os.path.abspath(C.opt(argv, "--out", os.path.join(work, "metrics", tag))), tag)
        C.log("DONE metrics")
        return
    C.reset_scene(fps=FPS)
    col = C.get_collection(KEY)
    b = Build()
    mesh = b.build(col)
    if C.flag(argv, "--preview"):
        preview(mesh, work)
        C.log("DONE preview")
        return
    tex_dir = os.path.join(pack, "textures")
    orig = P.paint
    P.paint = flame_paint(orig, b.heat)
    try:
        paint_rep = P.paint_asset(mesh, KEY, b.recipes(), tex_dir, size=size, decals=b.decals(), ao_distance=0.05,
                                  ao_samples=16, edge_min_angle=24.0, margin_px=3, uv_angle=66.0, seed=SEED,
                                  uv_zone_scale=UV_SCALE)
    finally:
        P.paint = orig
    arm = RIG.build_swarm_rig(b.pivots(), col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in b.sockets():
        RIG.add_socket(arm, bone, name, p)
    clips, frames = make_clips(arm)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    cycle_m = round(ROW["speed"] * MOVE_FRAMES / FPS, 2)
    extra = {
        "content_key": KEY,
        "faction": "fallen_godworks",
        "look": "a soot-blackened god-bronze mask-head (the dark core, about half the flame's width) with one "
                "cold-gold eye slit, in a cup and ring of dead-ember flame (cold gold only against the core); the "
                "mask's upper-left corner is broken off (a charred notch) and a forked tail streams behind",
        "hover_m": {"core_centre": CZ, "flame_bottom": None, "flame_top": None},
        "bones": {"root": "hover bob and tilts", "body": "the mask-head core (persists; it falls in the death)",
                  "head": "the flame hood cupping the core", "legs_a": "tongue group A (flickers against B)",
                  "legs_b": "tongue group B", "tail": "the forked tail and its two sparks"},
        "move_cycle_m": cycle_m,
        "move_note": "move@loop is the erratic drift (0.6 s): play it at speed / move_cycle_m cycles per second "
                     "(1x at the row speed 4.2 m/s). Clips play in place; the Swarmer jitter moves the entity",
        "death_note": "death: the flame gutters, the core swells, the fire bursts outward and is gone by frame 14 "
                      "(0.47 s); spawn the death_burst VFX (row death_burst radius 1.6) at fx_core around frame 11 "
                      "(0.37 s). The blackened mask then tumbles to the ground and crumbles (held at 2 %)",
        "windup_note": "windup: the flame gutters inward, then flares wide as the wisp rears back; attack: a 0.3 m "
                       "dart forward and back (in place overall). The Swarmer has no windup state yet",
        "content_row": ROW,
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
        "skin": skin,
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    # fill the flame top into meta.json now that the bounds are known
    mpath = os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"
    meta = C.read_json(mpath)
    meta["hover_m"]["flame_top"] = rep["bounds"]["max"][1]
    meta["hover_m"]["flame_bottom"] = rep["bounds"]["min"][1]
    C.write_json(mpath, meta)
    C.log("clips", RIG.clips_report(arm))
    C.write_json(os.path.join(reports, "%s_build_report.json" % KEY),
                 {"export": {k: rep[k] for k in rep if k not in ("nodes",)}, "paint": paint_rep, "skin": skin,
                  "parts": b.parts, "tris_blender": b.tris, "clips": RIG.clips_report(arm)})
    if not C.flag(argv, "--no-review"):
        tex = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        top = rep["bounds"]["max"][1]
        notes = [
            "%s tris (swarm budget 600-1500) | textures %s | hovers: core centre %.2f m, flame %.2f-%.2f m (top %.2f x hero) | "
            "mesh %.2f m tall, %.2f m long | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), CZ, rep["bounds"]["min"][1], top,
                top / 2.2, rep["height_m"], rep["bounds"]["max"][2] - rep["bounds"]["min"][2], ", ".join(sorted(rep["sockets"]))),
            "Clips: %s | move_cycle_m %.2f" % (", ".join(c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"]
                                                         for c in RIG.clips_report(arm)), cycle_m),
            "Bones: body = mask-head core, head = flame hood, legs_a / legs_b = the two tongue groups, tail = forked tail + "
            "sparks. Death burst VFX at fx_core (frame 11). Status: %s." % SPEC.STATUS_AI_FINAL,
        ]
        review(b, arm, mesh, rep, reports, work, tex, notes, frames)
        if not C.flag(argv, "--no-crowd"):
            crowd_review(reports, work)
        if not C.flag(argv, "--no-metrics"):
            # the art review's numbers on the shipped GLB (player-gold clash, glow share, mask width)
            mdir = os.path.join(work, "metrics", "after")
            metric_renders(C.model_path(KIND, KEY), mdir, "after")
            C.run_comfy_python("enemies/emberwisp_fix_sheet.py", "--analyse", mdir)
        C.write_pack_status(KIND, KEY, status_outputs(reports),
                            "Built from code by tools/blender/gf_assets/enemies/emberwisp.py (model, heat-band flame "
                            "paint, GF_Swarm_v1 rig, six clips, export, review sheets and the 40-copy horde render "
                            "mixed with clinkers).", tier=TIER,
                            extra={"skeleton": SPEC.SWARM_SKELETON, "faction": "fallen_godworks"})
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
