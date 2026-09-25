"""Molten Hexer (content key `molten_hexer`): an Unmade elite caster of the Cinder Wastes, built end to end from
code - model, hand-painted NPR textures, dedicated rig, clips, GLB export, validation, review sheets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P tools/blender/gf_assets/enemies/molten_hexer.py -- [--preview] [--look] [--poses] [--no-review] [--size 1024]

  --preview   geometry only: flat zone colours, turnaround + the game camera at 1x (seconds, no bakes, no export)
  --look      geometry + the final paint (textures into work/look/, not the pack): 3/4 view, close 55 deg view,
              game camera at true pixel size + silhouette (no rig, no export) - the value-hierarchy check
  --poses     geometry + rig + clips, key-frame renders in flat colours (no bakes, no export);
              [--game] through the game camera, [--clip <name>], [--size px]
  (default)   the full build: paint, rig, clips, save .blend, export + validate, review sheets, status.json

Content row (content/sheets/enemies.csv): Elite, Cinder Wastes, P0, hp 300, speed 2.4, radius 0.62, resist
Flame 0.4, Caster(range 13.0, windup 1.2, width 1.2, length 14.0, damage 36.0, cooldown 3.8, keep_distance 9.0),
colour #FF4D6D, greybox Spire, scale 1.1 - "Channels molten beams across the arena."
The sim (crates/gf_sim/src/enemies.rs, Caster): it stops, faces the target and holds still for the windup while
the engine draws a 14 x 1.2 m line telegraph from its position; the beam lands when the windup ends.

Design (docs/art/ENEMIES.md sections 3, 4, 6; the Slag King's court, so THE UNMADE):
  * verb THE BEAM: a hooded tower of cooled slag that holds a floating crucible of molten god-metal over its
    head. THE gimmick in the outline is that beam-focus: the crucible (a white-hot pool in a dark iron bowl,
    seen from above by the 55 deg camera) ringed by a floating CROWN OF MOLTEN RUNES - six bold 0.3 m glyphs
    lying flat in a 1.44 m ring round it, wider than the hem. When it channels, the ring contracts and whirls; when it
    fires, the crucible tips forward and the ring swings upright in front of the pour lip, a focus ring the
    beam passes through;
  * the body: a spire of cooling slag in THREE uneven tiers, never a stacked cake (art review 6.5/10): a short
    broad ash cape, ONE long overrobe that slumps toward the heavy slag arm (its hem a diagonal, torn long at
    the right-front, hitched short over the left-back, cracked by two molten fissures) and an underskirt wedge
    leaning the other way, puddling onto a dim molten pool; each tier leaks molten light from under the one
    above; a tall pointed cowl, an obsidian face split by one teal slit;
  * values against the Cinder floor (mauve-brown flagstones L* 17-39, oxblood gaps L* 6): a cool coal robe,
    pale ash on the cape and shoulder tops the 55 deg camera sees first, never near-black;
  * Unmade asymmetry that survives game size: a massive slag arm (right) with molten cracks against a thin pale
    bone arm (left), and a spray of teal-cracked obsidian shards off the left shoulder;
  * palette (gfa_spec.FACTIONS["unmade"]): slag, obsidian, bone, molten and a few teal cracks. The glow ramp
    runs white-hot -> peach -> orange and skips the forge-gold band (#FFC24B sits dE 5 from the player gold
    #FFC940). The row colour #FF4D6D only as a faint dark rose in the slag shadows. No player colours, no
    red-white (the engine draws the telegraph).

Footprint: radius 0.62 x scale 1.1 = 0.68 m collider; the hem is ~1.2 m across, the rune ring 1.44 m; the model
spans 1.65 x 1.78 m (2.4-2.6 x the collider radius). Height 2.75 m (1.25 x the hero).
Rig GF_MoltenHexer_v1: GF_Hero_v1 core bone names + crucible, molten, crown, crown_spin, rune_0..5, pool.
Clips: idle@loop, move@loop, windup, attack, hit, death (required) + channel@loop (the long channel pose) and
beam_sweep@loop (the beam dragged across the arena). See art/enemies/molten_hexer/README.md.

Adapted from: enemies/forge_warden.py (dedicated rig, per-frame solver, review sheets) and enemies/slag_king.py
(slag / molten paint recipes, the top-plane lift and molten underglow passes) - adapted here, never modified.
"""
import math
import os
import random
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_rig_dedicated as RD  # noqa: E402
import gfa_shell as S  # noqa: E402

KEY, KIND, TIER = "molten_hexer", "enemy", "elite"
RIG_NAME = "GF_MoltenHexer_v1"
FPS = 30

ZONES = ["slag", "arm", "obsidian", "bone", "iron", "molten", "core", "rune", "void", "pool"]
PREVIEW = {"slag": "#4A382E", "arm": "#3E2E26", "obsidian": "#2A2634", "bone": "#A89A84", "iron": "#4A4650",
           "molten": "#FF6B1A", "core": "#FFF3D6", "rune": "#FF8A2A", "void": "#160C0A", "pool": "#8A2E0C"}
GLOW_ZONES = ("molten", "core", "rune", "pool")

# ---- landmarks (rest pose = the idle stance; metres, faces -Y, +X = the hexer's LEFT) ------------------------
LM = {
    "root": (0.0, 0.0, 0.0), "root_tip": (0.0, 0.0, 0.25),
    "pelvis": (0.0, 0.02, 0.95), "spine_01": (0.0, 0.02, 1.15), "spine_02": (0.0, 0.02, 1.35),
    "spine_03": (0.0, 0.03, 1.53), "neck": (0.0, 0.01, 1.76), "head": (0.0, -0.02, 1.88), "head_tip": (0.0, -0.07, 2.18),
    "clavicle_L": (0.08, 0.04, 1.66), "shoulder_L": (0.3, 0.05, 1.68),
    "elbow_L": (0.56, -0.03, 1.86), "wrist_L": (0.42, -0.3, 2.2), "hand_L_tip": (0.33, -0.36, 2.37),
    "clavicle_R": (-0.08, 0.04, 1.64), "shoulder_R": (-0.35, 0.05, 1.66),
    "elbow_R": (-0.63, 0.0, 1.84), "wrist_R": (-0.45, -0.28, 2.14), "hand_R_tip": (-0.34, -0.36, 2.3),
    "hip_L": (0.14, 0.02, 0.92), "knee_L": (0.16, -0.02, 0.5), "ankle_L": (0.17, 0.02, 0.1),
    "ball_L": (0.18, -0.12, 0.04), "toe_L_tip": (0.18, -0.22, 0.03),
}
for _k in ("hip", "knee", "ankle", "ball", "toe_L_tip"):
    _src = _k if _k.endswith("tip") else _k + "_L"
    _p = LM[_src]
    LM[_src.replace("_L", "_R")] = (-_p[0], _p[1], _p[2])

# the beam focus: the crucible floats above and in front of the cowl; the rune crown rings it, tilted 12 deg
# toward the front so the 55 deg camera sees the ring open
CRUCIBLE = Vector((0.0, -0.34, 2.46))
CROWN_TILT = 12.0
CROWN_AXIS = Vector((0.0, -math.sin(math.radians(CROWN_TILT)), math.cos(math.radians(CROWN_TILT))))
CROWN_E1 = Vector((1.0, 0.0, 0.0))                                                 # ring plane: +X (left) ...
CROWN_E2 = Vector((0.0, -math.cos(math.radians(CROWN_TILT)), -math.sin(math.radians(CROWN_TILT))))  # ... and front
CROWN_C = CRUCIBLE + CROWN_AXIS * 0.12
CROWN_R = 0.72
RUNE_ANGLES = [60.0 * k for k in range(6)]          # 0 = the hexer's left, 90 = front (ring plane angles)


def rune_pos(k, r=CROWN_R):
    a = math.radians(RUNE_ANGLES[k])
    return CROWN_C + (CROWN_E1 * math.cos(a) + CROWN_E2 * math.sin(a)) * r


def P_(k):
    return Vector(LM[k]) if isinstance(k, str) else Vector(k)


BONES = [
    ("root", None, "root", "root_tip"),
    ("pelvis", "root", "pelvis", "spine_01"),
    ("spine_01", "pelvis", "spine_01", "spine_02"),
    ("spine_02", "spine_01", "spine_02", "spine_03"),
    ("spine_03", "spine_02", "spine_03", "neck"),
    ("neck", "spine_03", "neck", "head"),
    ("head", "neck", "head", "head_tip"),
    ("clavicle_L", "spine_03", "clavicle_L", "shoulder_L"),
    ("upperarm_L", "clavicle_L", "shoulder_L", "elbow_L"),
    ("lowerarm_L", "upperarm_L", "elbow_L", "wrist_L"),
    ("hand_L", "lowerarm_L", "wrist_L", "hand_L_tip"),
    ("clavicle_R", "spine_03", "clavicle_R", "shoulder_R"),
    ("upperarm_R", "clavicle_R", "shoulder_R", "elbow_R"),
    ("lowerarm_R", "upperarm_R", "elbow_R", "wrist_R"),
    ("hand_R", "lowerarm_R", "wrist_R", "hand_R_tip"),
    ("thigh_L", "pelvis", "hip_L", "knee_L"),
    ("shin_L", "thigh_L", "knee_L", "ankle_L"),
    ("foot_L", "shin_L", "ankle_L", "ball_L"),
    ("toe_L", "foot_L", "ball_L", "toe_L_tip"),
    ("thigh_R", "pelvis", "hip_R", "knee_R"),
    ("shin_R", "thigh_R", "knee_R", "ankle_R"),
    ("foot_R", "shin_R", "ankle_R", "ball_R"),
    ("toe_R", "foot_R", "ball_R", "toe_R_tip"),
    # the beam focus and the pool (not in GF_Hero_v1)
    ("crucible", "root", tuple(CRUCIBLE), tuple(CRUCIBLE + Vector((0, 0, 0.25)))),
    ("molten", "crucible", tuple(CRUCIBLE + Vector((0, 0, 0.06))), tuple(CRUCIBLE + Vector((0, 0, 0.2)))),
    ("crown", "crucible", tuple(CROWN_C), tuple(CROWN_C + CROWN_AXIS * 0.2)),
    ("crown_spin", "crown", tuple(CROWN_C), tuple(CROWN_C + CROWN_AXIS * 0.2)),
] + [("rune_%d" % k, "crown_spin", tuple(rune_pos(k)), tuple(rune_pos(k) + CROWN_AXIS * 0.12)) for k in range(6)] + [
    ("pool", "root", (0.0, 0.0, 0.0), (0.0, 0.0, 0.15)),
]
BONE_NAMES = [b[0] for b in BONES]


# ---- small geometry helpers ---------------------------------------------------------------------------------

def frame_z(origin, z_dir, x_hint=(1, 0, 0)):
    return M.orient(tuple(origin), tuple(z_dir), tuple(x_hint))


def bumps(spec):
    """spec [(angle deg, half width deg, amplitude)] -> f(theta) = the largest gaussian bump (0..1)."""
    def f(th):
        v = 0.0
        for a, w, amp in spec:
            d = (th - a + 180.0) % 360.0 - 180.0
            v = max(v, amp * math.exp(-(d / w) ** 2))
        return v
    return f


def skirt(a, name, bone, z_top, r_top, z_hem, r_hem, tongues, theta=(-180.0, 180.0), nu=24, nv=3, t=0.035,
          scallop=0.1, flare=0.05, sx=1.0, sy=1.0, zone="slag", seed=0.0, tilt=(0.0, 0.0), drips=(),
          slant=(0.0, 0.0), tears=(), skew=(0.0, 0.0), z_min=0.012):
    """One hanging tier of the slag robe: a flared, thick cone from (z_top, r_top) down to a hem that drips in
    tongues (reaching z_hem) with scallops `scallop` higher between them, tilted (x, y deg) about its top like
    a melting candle. Outer skin `zone`, inner skin void. drips: [(theta deg, extra length m)] - thick slag
    runnels running down the outside and hanging past the hem.
    Uneven hems (the art-review fix: no stacked cake tiers): slant (amp m, theta deg) raises the hem by amp at
    theta and lowers it by amp opposite (a hitched-up side and a sagging side); tears [(theta deg, half width
    deg, extra m)] are torn tongues hanging `extra` below the hem; skew (dx, dy) shears the hem sideways
    (the tier slumps off its axis). The hem never goes below z_min. Returns fn(theta deg, v) -> outer point."""
    tg = bumps(tongues)
    tr = bumps([(a_, w_, 1.0) for a_, w_, _e in tears])
    th0, th1 = theta
    full = abs(th1 - th0) >= 359.9
    piv = Vector((0.0, 0.0, z_top))
    T = (Matrix.Translation(piv) @ Matrix.Rotation(math.radians(tilt[0]), 4, "X")
         @ Matrix.Rotation(math.radians(tilt[1]), 4, "Y") @ Matrix.Translation(-piv))

    def tear(th):
        best = 0.0
        for a_, w_, e_ in tears:
            d = (th - a_ + 180.0) % 360.0 - 180.0
            best = max(best, e_ * math.exp(-(d / w_) ** 2))
        return best

    def at(th, v):
        k = tg(th)
        zb = z_hem + scallop * (1.0 - k) + slant[0] * math.cos(math.radians(th - slant[1])) - tear(th)
        zb = max(zb, z_min)
        z = z_top + (zb - z_top) * v
        kt = tr(th)
        r = r_top + (r_hem - r_top) * (v ** 0.9) + flare * v ** 3 + 0.03 * max(k, kt) * v * v
        r *= 1.0 + 0.035 * math.sin(math.radians(th) * 3.0 + seed)
        rad = math.radians(th)
        return T @ Vector((r * sx * math.cos(rad) + skew[0] * v * v, r * sy * math.sin(rad) + skew[1] * v * v, z))

    def fn(u, v):
        return at(th0 + (th1 - th0) * u, v)
    outer, inner = S.thick_patch(fn, nu, nv, t, wrap_u=full, flip=True)
    a.add(outer, zone, bone=bone, name=name, shading="smooth")
    a.add(inner, "void", bone=bone, name=name + "_in", shading="smooth")
    for k, (th, extra) in enumerate(drips):
        pts = []
        for v in (0.05, 0.35, 0.7, 0.97):
            p = at(th, v)
            out = Vector((p.x, p.y, 0.0))
            out = out.normalized() if out.length > 1e-6 else Vector((1, 0, 0))
            pts.append(p + out * 0.018)
        hem = pts[-1]
        pts.append(hem + Vector((0.0, 0.0, -extra * 0.6)) + (hem - pts[-2]).normalized() * 0.012)
        pts.append(hem + Vector((0.0, 0.0, -extra)))
        rad = [0.035, 0.05, 0.062, 0.07, 0.085, 0.0]
        d = M.tube(M.catmull(pts, 2), [rad[min(len(rad) - 1, i // 2)] for i in range(2 * (len(pts) - 1) + 1)], sides=8)
        a.add(d, zone, bone=bone, name=name + "_drip", shading="smooth")
    return at


def lumpy(bm, amount, freq, seed):
    M.noise_displace(bm, amount, freq=freq, seed=seed)
    return bm


# ---- the model ----------------------------------------------------------------------------------------------

HEM_FN = {}           # skirt name -> at(theta deg, v): filled by build_robe (the seam-glow paint pass reads it)


# The robe is THREE uneven tiers, never a stacked cake (art review 6.5/10: the four similar symmetric tiers read
# as a tiered cake / pagoda). Angles: 0 = the hexer's left (+X), -90 = front, 180 = its right (the slag arm).
# Everything slumps toward the heavy slag arm (right-front), like a candle melting off true; the left - the shard
# side - is hitched up short, so the three hems run as diagonals, not as parallel rings.
def build_robe(a):
    # T1, the underskirt, puddles wide onto the pool; split in three so the hidden legs can swing the front panels
    # (a step under the robe). It leans the other way (toward the left) and shows as a wedge under the hitched-up
    # left side of the overrobe
    t1 = dict(z_top=1.02, r_top=0.29, z_hem=0.0, r_hem=0.52, scallop=0.13, flare=0.07, nv=4, t=0.04,
              tongues=[(-110, 13, 1.0), (-35, 15, 1.0), (40, 13, 0.95), (105, 12, 1.0), (165, 14, 0.9),
                       (-165, 10, 0.85)], seed=0.7, tilt=(0.0, 3.0), skew=(0.05, 0.0))
    skirt(a, "skirt1_fl", "thigh_L", theta=(-92.0, 12.0), nu=10, **t1)
    skirt(a, "skirt1_fr", "thigh_R", theta=(-192.0, -88.0), nu=10, **t1)
    skirt(a, "skirt1_b", "pelvis", theta=(8.0, 172.0), nu=13, **t1)
    # the overrobe: ONE long crust tier (two tiers merged), sagging to the right-front: torn long there (one
    # tongue nearly reaches the pool), hitched short at the left-back, its hem sheared toward the slag arm
    HEM_FN["robe"] = skirt(a, "robe", "spine_01", z_top=1.62, r_top=0.25, z_hem=0.5, r_hem=0.45, scallop=0.09,
                           flare=0.08, t=0.035, nu=30, nv=5, sx=1.08, sy=0.96, seed=2.1, tilt=(-3.0, -8.0),
                           slant=(0.32, 40.0), skew=(-0.09, -0.04), tears=[(-140.0, 10.0, 0.22), (-62.0, 7.0, 0.12)],
                           tongues=[(-100, 13, 1.0), (-20, 11, 0.8), (60, 12, 0.9), (140, 13, 1.0), (175, 11, 0.9)])
    # the shoulder mantle: the top tier, a SHORT broad hunched crust cape (the cowl sits in its neck hole), longer
    # under the slag arm, hitched over the shard shoulder; its wide sloped top faces the 55 deg camera and takes the
    # brightest slag light
    HEM_FN["yoke"] = skirt(a, "yoke", "spine_03", z_top=1.84, r_top=0.15, z_hem=1.5, r_hem=0.46, scallop=0.06,
                           flare=0.05, t=0.035, sx=1.2, sy=0.95, nu=26, nv=4, seed=5.5, tilt=(0.0, -4.0),
                           slant=(0.07, -20.0), tears=[(172.0, 12.0, 0.15)],
                           tongues=[(-120, 13, 1.0), (-60, 12, 0.9), (0, 12, 1.0), (60, 12, 0.85), (115, 13, 1.0),
                                    (180, 12, 0.9)])
    # the right shoulder: a heavy slag boulder the big arm hangs from
    pb = M.ico(0.17, 1, scale=(1.25, 1.05, 0.85))
    lumpy(pb, 0.025, 6.0, 3)
    M.xform(pb, loc=(-0.37, 0.05, 1.73), rot=(0, 12, 0))
    a.add(pb, "slag", bone="clavicle_R", name="pauldron_R", shading="flat")
    # the left shoulder: a spray of Unmade obsidian shards breaking OUT of the mantle, so the left side of the
    # outline gets a jagged crystal crest under the ring (teal cracks are painted into them)
    base = Vector((0.3, 0.1, 1.66))
    for k, (d, L, r) in enumerate((((0.75, 0.2, 0.75), 0.58, 0.085), ((0.95, -0.1, 0.25), 0.42, 0.07),
                                   ((0.35, 0.55, 0.85), 0.36, 0.06), ((0.9, 0.35, -0.05), 0.26, 0.05),
                                   ((0.2, 0.15, 1.0), 0.24, 0.045))):
        sp = M.spike(r, L, sides=5, rot_offset=18 * k)
        M.xform(sp, matrix=frame_z(base + Vector(d).normalized() * 0.02, Vector(d).normalized(), (0, 0, 1)))
        a.add(sp, "obsidian", bone="clavicle_L", name="shard", shading="flat")


def build_head(a):
    # the cowl: a tall pointed hood leaning forward over the face, its opening a pointed arch, the peak swept back
    Mh = Matrix.Translation((0.0, 0.03, 1.72)) @ Matrix.Rotation(math.radians(16.0), 4, "X")
    prof = [(0.2, 0.0), (0.25, 0.1), (0.25, 0.22), (0.205, 0.34), (0.13, 0.46), (0.045, 0.55)]
    nu, nv = 16, 6

    def open_front(i, j):
        th = -180 + 360 * (i + 0.5) / nu
        return not ((abs(th + 90) < 38 and 1 <= j <= 3) or (abs(th + 90) < 15 and j == 4))
    fn = S.rev_fn(prof, -180, 180, sy=1.15, matrix=Mh, smooth=3)
    outer, inner = S.thick_patch(fn, nu, nv, 0.03, keep=open_front, wrap_u=True)
    a.add(outer, "slag", bone="head", name="cowl", shading="smooth")
    a.add(inner, "void", bone="head", name="cowl_in", shading="smooth")
    top = Mh @ Vector((0.0, 0.0, 0.53))
    peak = M.horn([top, top + Vector((0.0, 0.08, 0.08)), top + Vector((0.0, 0.2, 0.1)), top + Vector((0.0, 0.3, 0.06))],
                  0.06, 0.0, sides=5)
    a.add(peak, "slag", bone="head", name="peak", shading="flat")
    # the face: a dark obsidian plate sunk deep in the hood (one thin teal crack is painted down it)
    face = M.sphere(0.11, 10, 6, scale=(1.0, 0.7, 1.35))
    M.xform(face, loc=(0.0, -0.05, 1.94))
    a.add(face, "obsidian", bone="head", name="face", shading="smooth")


def _hand(a, side, fingers, finger_r, finger_len, palm, zone, curl):
    wr, tip = P_("wrist_" + side), P_("hand_%s_tip" % side)
    hd = (tip - wr).normalized()
    toward = (CRUCIBLE - wr)
    toward = (toward - hd * toward.dot(hd)).normalized()      # palm normal: toward the crucible
    Fm = frame_z(wr + hd * palm[2] * 0.5, hd, toward)        # local X = palm normal, Y = across, Z = fingers
    pb = M.box(palm, bevel=min(palm) * 0.25, taper=(0.9, 1.1))
    M.xform(pb, matrix=Fm)
    a.add(pb, zone, bone="hand_" + side, name="palm", shading="flat")
    X, Y, Z = (Fm.col[0].to_3d(), Fm.col[1].to_3d(), Fm.col[2].to_3d())
    root = wr + hd * palm[2]
    n = len(fingers)
    for k, (spread, lf) in enumerate(fingers):
        b = root + Y * spread
        L = finger_len * lf
        pts = [b, b + Z * L * 0.45 + Y * spread * 0.4, b + Z * L * 0.8 + Y * spread * 0.6 + X * L * curl * 0.5,
               b + Z * L * 0.95 + Y * spread * 0.7 + X * L * curl]
        a.add(M.horn(pts, finger_r, 0.0, sides=5), zone, bone="hand_" + side, name="finger", shading="smooth")
    th = wr + hd * palm[2] * 0.4 - Y * palm[1] * 0.55 * (1 if n else 1)
    pts = [th, th - Y * finger_len * 0.3 + Z * finger_len * 0.2, th - Y * finger_len * 0.35 + Z * finger_len * 0.45 + X * finger_len * 0.2]
    a.add(M.horn(pts, finger_r * 1.05, 0.0, sides=5), zone, bone="hand_" + side, name="thumb", shading="smooth")


def build_arms(a):
    # RIGHT: the massive slag arm, a slag cuff at the wrist, a three-clawed slag fist cupping the crucible
    sh, el, wr = P_("shoulder_R"), P_("elbow_R"), P_("wrist_R")
    up = M.tube(M.catmull([sh + (el - sh) * 0.1, sh.lerp(el, 0.55) + Vector((-0.02, 0.0, 0.03)), el], 3),
                [0.12] + [0.11] * 4 + [0.1] * 2, sides=8)
    lumpy(up, 0.018, 7.0, 11)
    a.add(up, "arm", bone="upperarm_R", name="upperarm_R", shading="smooth")
    eb = M.ico(0.105, 1, scale=(1.0, 1.0, 0.9))
    lumpy(eb, 0.015, 8.0, 12)
    M.xform(eb, loc=el + Vector((-0.02, 0.03, -0.02)))
    a.add(eb, "arm", bone="lowerarm_R", name="elbow_R", shading="flat")
    fd = (wr - el).normalized()
    fore = M.tube([el + fd * 0.04, el.lerp(wr, 0.45), el.lerp(wr, 0.85), wr + fd * 0.02], [0.085, 0.12, 0.14, 0.12],
                  sides=8)
    lumpy(fore, 0.02, 6.0, 13)
    a.add(fore, "arm", bone="lowerarm_R", name="forearm_R", shading="smooth")
    for k, (tt, ang) in enumerate(((0.35, 0.0), (0.62, 140.0), (0.5, 250.0))):
        # crust plates flaking off the forearm
        side = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0))
        side = (side - fd * side.dot(fd)).normalized()
        pl = M.box((0.12, 0.16, 0.035), bevel=0.01, taper=(0.7, 0.8))
        M.xform(pl, matrix=frame_z(el.lerp(wr, tt) + side * 0.12, side, fd))
        a.add(pl, "slag", bone="lowerarm_R", name="crust", shading="flat")
    cuff = M.ring(0.1, 0.145, 0.07, sides=10)
    M.xform(cuff, matrix=frame_z(wr - fd * 0.03, fd))
    lumpy(cuff, 0.01, 10.0, 14)
    a.add(cuff, "slag", bone="lowerarm_R", name="cuff_R", shading="flat")
    _hand(a, "R", [(-0.05, 1.0), (0.0, 1.1), (0.05, 0.95)], 0.034, 0.2, (0.08, 0.15, 0.13), "arm", 0.55)
    # LEFT: the thin pale bone arm (Unmade: flesh fused to mineral, one side wasted), long splayed fingers
    sh, el, wr = P_("shoulder_L"), P_("elbow_L"), P_("wrist_L")
    up = M.tube([sh + (el - sh) * 0.15, sh.lerp(el, 0.6), el], [0.055, 0.05, 0.045], sides=7)
    a.add(up, "bone", bone="upperarm_L", name="upperarm_L", shading="smooth")
    ek = M.sphere(0.058, 8, 6, scale=(1.0, 1.0, 1.15))
    M.xform(ek, loc=el)
    a.add(ek, "bone", bone="lowerarm_L", name="elbow_L", shading="smooth")
    fd = (wr - el).normalized()
    fore = M.tube([el + fd * 0.03, el.lerp(wr, 0.5), wr], [0.045, 0.038, 0.034], sides=7)
    a.add(fore, "bone", bone="lowerarm_L", name="forearm_L", shading="smooth")
    bang = M.ring(0.04, 0.075, 0.07, sides=8)          # a slag bangle fused to the wrist
    lumpy(bang, 0.008, 12.0, 21)
    M.xform(bang, matrix=frame_z(el.lerp(wr, 0.78), fd))
    a.add(bang, "slag", bone="lowerarm_L", name="bangle_L", shading="flat")
    _hand(a, "L", [(-0.045, 0.95), (-0.015, 1.1), (0.015, 1.05), (0.045, 0.85)], 0.017, 0.24, (0.04, 0.1, 0.09),
          "bone", 0.35)


# The crown's glyphs: bold two-stroke runes written ALONG the ring like an inscription (their "up" is the
# ring tangent), never pointing out (radial arrows read as a UI menu, a zigzag as a Storm bolt, a crossed stem as
# an X). A = the yew (an eihwaz stem hooked opposite ways at both ends), B = the thorn (a thurisaz stem with a
# hooked barb). Period 2 (A B A B A B), so a 120 deg turn of the ring
# is seamless and every clip can start and end on the same ring pose.
GLYPHS = {
    "A": [[(0.075, 0.075), (0.0, 0.15), (0.008, 0.0), (0.0, -0.15), (-0.075, -0.075)]],
    "B": [[(0.0, -0.15), (0.0, 0.15)], [(0.0, 0.09), (0.085, 0.0), (0.0, -0.075)]],
}


def build_crucible(a):
    c = CRUCIBLE
    F = Matrix.Translation(c)
    prof = [(0.0, -0.215), (0.12, -0.205), (0.215, -0.14), (0.27, -0.04), (0.284, 0.05), (0.274, 0.1),
            (0.232, 0.108), (0.222, 0.06)]
    bowl = M.lathe(prof, sides=16, cap=False)
    M.xform(bowl, matrix=F)
    a.add(bowl, "iron", bone="crucible", name="bowl", shading="smooth")
    for z, r0, r1, h in ((0.085, 0.262, 0.305, 0.05), (-0.085, 0.235, 0.268, 0.04)):
        band = M.ring(r0, r1, h, sides=16, bevel=0.006)
        M.xform(band, matrix=F @ Matrix.Translation((0, 0, z)))
        a.add(band, "iron", bone="crucible", name="band", shading="smooth")
    # pour spout at the front, tipped down, a molten tongue in it
    sp = M.box((0.13, 0.16, 0.05), bevel=0.01, taper=(0.7, 1.0))
    M.xform(sp, matrix=F @ M.trs((0.0, -0.33, 0.075), (18.0, 0.0, 0.0)))
    a.add(sp, "iron", bone="crucible", name="spout", shading="flat")
    drip = M.horn([c + Vector((0.0, -0.4, 0.05)), c + Vector((0.0, -0.42, -0.06)), c + Vector((0.005, -0.41, -0.2))],
                  0.028, 0.0, sides=5)
    a.add(drip, "molten", bone="crucible", name="drip", shading="smooth")
    # lugs the claws hold, and three cooled drips of iron under the bowl
    for sx in (-1, 1):
        lug = M.ring(0.025, 0.055, 0.045, sides=8, axis="Y")
        M.xform(lug, matrix=F @ Matrix.Translation((sx * 0.3, 0.0, 0.0)))
        a.add(lug, "iron", bone="crucible", name="lug", shading="flat")
    for k, ang in enumerate((30.0, 150.0, 270.0)):
        t = math.radians(ang)
        spk = M.spike(0.04, 0.13, sides=4)
        M.xform(spk, matrix=F @ frame_z(Vector((0.12 * math.cos(t), 0.12 * math.sin(t), -0.19)), (0.2 * math.cos(t), 0.2 * math.sin(t), -1.0)))
        a.add(spk, "iron", bone="crucible", name="foot_drip", shading="flat")
    # the molten pool: a white-hot surface filling the bowl (its own bone: it swells, spills and drains)
    pool = M.cylinder(0.228, 0.03, sides=16)
    M.xform(pool, matrix=F @ Matrix.Translation((0, 0, 0.056)))
    a.add(pool, "core", bone="molten", name="melt", shading="smooth")
    bulge = M.sphere(0.12, 10, 5, scale=(1.0, 1.0, 0.28))
    M.xform(bulge, matrix=F @ Matrix.Translation((0.02, -0.02, 0.07)))
    a.add(bulge, "core", bone="molten", name="melt_bulge", shading="smooth")


def build_crown(a):
    for k in range(6):
        ang = math.radians(RUNE_ANGLES[k])
        radial = CROWN_E1 * math.cos(ang) + CROWN_E2 * math.sin(ang)
        tang = CROWN_AXIS.cross(radial).normalized()
        o = rune_pos(k) - CROWN_AXIS * 0.025
        # glyph x = radial (outward), glyph y = the ring tangent, thickness along the ring axis
        Fk = Matrix(((radial.x, tang.x, CROWN_AXIS.x, o.x), (radial.y, tang.y, CROWN_AXIS.y, o.y),
                     (radial.z, tang.z, CROWN_AXIS.z, o.z), (0, 0, 0, 1)))
        g = M.ribbon(GLYPHS["A" if k % 2 == 0 else "B"], 0.06, 0.05, frame=Fk)
        a.add(g, "rune", bone="rune_%d" % k, name="rune", shading="flat")


def build_pool(a):
    tg = bumps([(-104, 14, 1.0), (-18, 14, 1.0), (84, 14, 1.0), (-160, 14, 1.0), (32, 12, 0.8), (140, 12, 0.7)])
    n = 28
    bm = __import__("bmesh").new()
    cv = bm.verts.new((0.0, 0.0, 0.006))
    ring = []
    for i in range(n):
        th = 360.0 * i / n
        r = 0.56 + 0.12 * tg(th) + 0.015 * math.sin(math.radians(th) * 5.0)
        ring.append(bm.verts.new((r * math.cos(math.radians(th)), r * math.sin(math.radians(th)), 0.006)))
    for i in range(n):
        bm.faces.new((cv, ring[i], ring[(i + 1) % n]))
    a.add(bm, "pool", bone="pool", name="pool", shading="smooth")


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_NAMES)
    build_robe(a)
    build_head(a)
    build_arms(a)
    build_crucible(a)
    build_crown(a)
    build_pool(a)
    report = {}
    for p in a.parts:
        k = p["name"].split("_in")[0]
        report[k] = report.get(k, 0) + p["faces"]
    obj = a.to_object(col)
    obj["gfa_part_names"] = ",".join(p["name"] for p in a.parts)
    C.log("faces per part: " + ", ".join("%s %d" % kv for kv in sorted(report.items(), key=lambda kv: -kv[1])))
    C.log("mesh: %d parts, %d tris" % (len(a.parts), tris_of(obj)))
    return obj, a.parts


def tris_of(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ---- paint (The Unmade, ENEMIES.md section 4; the Slag King's slag and molten) --------------------------------

# The slag values (art-review fix: the robe was a dark bell lost in the Cinder floor - 30-35 % of its pixels within
# +-7 L* of the flagstone gaps (L* 6) and dark stones (L* 17)). The slag body is lifted to a cool coal (a hue off the
# warm floor), the up-facing crust to pale ash (the cinderling's cooled-crust read) and the cape and shoulder tops -
# the planes the 55 deg camera sees first - to the palest ash, above every floor stone (L* <= 39)
SLAG_SHADOW, SLAG, ASH, ASH_PALE, ASH_EDGE = "#120C0E", "#3E3234", "#6E625C", "#877A72", "#B0A094"
SLAG_UPPER, SLAG_UNDER = "#504446", "#564B4B"      # the upper overrobe, the underskirt (body-value pass)
# The glow ramp (art-review fix): white-hot core -> PEACH -> orange -> molten rim. It never passes through forge gold
# (#FFC24B sits dE 5 from the player gold #FFC940): every white-to-orange mix stays > dE 34 from #FFC940
MOLTEN_RIM, MOLTEN, PEACH, WHITE_HOT = "#C8400C", "#FF6B1A", "#FFC4A0", "#FFF3D6"
MOLTEN_BASE = "#80340F"          # the painted base under the flat molten glow (half value, see recipes())
PALETTE = [  # (name, hex) for the review sheets
    ("slag shadow", SLAG_SHADOW), ("slag", SLAG), ("slag top ash", ASH), ("cape ash", ASH_PALE), ("slag edge", ASH_EDGE),
    ("crucible bounce", "#7A3418"), ("obsidian", "#1A1720"), ("bone", "#A89A84"), ("iron", "#363337"),
    ("iron rim", "#A49CA6"), ("molten rim", MOLTEN_RIM), ("molten", MOLTEN), ("peach", PEACH),
    ("white-hot core", WHITE_HOT), ("unmade teal", "#2FBFA8"),
]
TEAL = {"color": "#2FBFA8", "core": "#B8FFE8"}
HOT = {"color": MOLTEN_RIM, "core": "#FFB890"}
SHARD_BASE = Vector((0.3, 0.1, 1.66))


def recipes():
    import gfa_paint as P
    # warm bounce light from the crucible overhead onto the cowl, the mantle and the arms (painted, not lit)
    warm = {"center": tuple(CRUCIBLE), "range": (1.1, 0.3), "color": "#7A3418", "amount": 0.3}
    # slag: faceted value planes, cavity darks, a cool coal body (SLAG) under pale ash tops (paint_extras). The
    # painter's own edge strokes are off (edge=0): paint_extras strokes only real creases of a part's OWN edges
    # The robe tiers are smooth cones: per-normal plane values and spots broke them into camouflage patches, so the
    # slag keeps only quiet planes, a low-frequency brush and deep contact shadows (the lips carry the value steps)
    slag = P.zone(base=SLAG, shadow=SLAG_SHADOW, light=ASH_PALE, planes=0.06, parts=0.07, brush=0.04,
                  brush_freq=2.0, cavity=0.8, cavity_width=0.012, ao=0.45, ao_range=(0.38, 0.72), edge=0.0,
                  gradient=warm)
    arm = P.zone(base="#322828", shadow="#140A0C", light=ASH_PALE, planes=0.05, parts=0.06, brush=0.05,
                 brush_freq=3.0, cavity=0.7, cavity_width=0.012, ao=0.55, ao_range=(0.3, 0.65), edge=0.0, gradient=warm)
    # obsidian shards and the face: big faceted planes, bright broken edges; teal leaks where the shards break out
    obsidian = P.faction_zone("unmade", "obsidian", planes=0.16, parts=0.1, edge=1.0, edge_width=0.012,
                              edge_breakup=0.25, cavity=0.6, cavity_width=0.008, brush_freq=4.0, light="#6A6680",
                              emit={"color": "#0D3B35", "hot": "#1F8F7E", "core": "#2FBFA8", "mode": "radial",
                                    "center": tuple(SHARD_BASE), "radius": 0.5, "fade": (0.62, 0.2),
                                    "base_mix": 0.1, "strength": 1.0})
    # the wasted arm: bone one step darker than the faction bone so it never outshines the crucible
    bone = P.zone(base="#A89A84", shadow="#6E6152", light="#E6DCC6", planes=0.06, parts=0.04, brush=0.03,
                  brush_freq=5.0, edge=0.6, edge_width=0.006, cavity=0.5, cavity_width=0.006, ao=0.45,
                  gradient={"center": tuple(CRUCIBLE), "range": (0.9, 0.25), "color": "#D0885A", "amount": 0.35})
    # the crucible: dark iron, broad planes, one bright steel stroke on the rims (paint_extras), heat-tinted lip
    iron = P.zone(base="#363337", shadow="#0E0D10", light="#6E6970", planes=0.16, parts=0.07, brush=0.025,
                  brush_freq=3.0, cavity=0.8, cavity_width=0.008, ao=0.5, ao_range=(0.3, 0.65), edge=0.0,
                  gradient={"center": tuple(CRUCIBLE + Vector((0, 0, 0.1))), "range": (0.42, 0.12),
                            "color": "#6A2A14", "amount": 0.4})
    # molten and the white-hot melt: the ramp skips the gold band (the faction light #FFC24B is overridden too).
    # The pour drip glows flat orange over a HALF-VALUE base (gfa_paint emit "stops", the cinderling's fix): with
    # the glow colour as its base, the toon key light plus the x1.6 emission clipped red and rendered it gold
    molten = P.faction_zone("unmade", "molten", glow=True, light=PEACH,
                            emit={"color": MOLTEN_RIM, "hot": MOLTEN, "core": PEACH, "mode": "flat", "base_mix": 0.1,
                                  "stops": [(0.0, MOLTEN, MOLTEN_BASE), (1.0, MOLTEN, MOLTEN_BASE)]})
    core = P.faction_zone("unmade", "molten", glow=True, light=PEACH,
                          emit={"color": MOLTEN, "hot": PEACH, "core": WHITE_HOT, "mode": "radial",
                                "center": tuple(CRUCIBLE + Vector((0, 0, 0.07))), "radius": 0.25, "base_mix": 0.5})
    # the runes: saturated molten orange (the base darker than the glow, so it never washes out to salmon), hotter on
    # the inner end; a white-hot (peach-white, never gold) core line runs down every stroke (decals)
    rune = P.zone(base="#8A2A08", shadow="#3A0E05", light="#C8400C", planes=0.08, parts=0.04, brush=0.03,
                  brush_freq=6.0, edge=0.0, cavity=0.0, ao=0.0,
                  emit={"color": "#A8300A", "hot": "#E0520E", "core": "#FF7A1A", "mode": "axis",
                        "center": tuple(CROWN_C), "axis": tuple(CROWN_AXIS), "radius": 0.9, "base_mix": 0.0,
                        "strength": 0.9})
    void = P.zone(base="#1A0D0A", shadow="#0A0505", light="#2A1410", planes=0.04, parts=0.0, brush=0.05,
                  brush_freq=4.0, edge=0.0, cavity=0.0, ao=0.0)
    # the pool it stands in: dim, cooling to a dark crust at its edge (hot only where the drips touch it)
    pool = P.zone(base="#3A1208", shadow="#1A0805", light="#6E2410", planes=0.0, parts=0.0, brush=0.12,
                  brush_freq=6.0, edge=0.0, cavity=0.0, ao=0.0,
                  emit={"color": "#240904", "hot": "#6E1C06", "core": "#B83A0A", "mode": "radial",
                        "center": (0.0, 0.0, 0.0), "radius": 0.72, "base_mix": 0.05, "strength": 0.55})
    return {"slag": slag, "arm": arm, "obsidian": obsidian, "bone": bone, "iron": iron, "molten": molten,
            "core": core, "rune": rune, "void": void, "pool": pool}


def frame_at(origin, normal, up=(0, 0, 1)):
    """Decal frame: +Z = the outward surface normal (projection direction), +Y as close to `up` as possible."""
    z = Vector(normal).normalized()
    y = Vector(up) - z * Vector(up).dot(z)
    if y.length < 1e-4:
        y = Vector((0, 1, 0)) - z * z.y
    y.normalize()
    x = y.cross(z)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def decals():
    import gfa_paint as P
    out = []
    # the face: ONE teal slit down the obsidian plate (the Unmade's split face), a burnt rim round it
    slit = [[(0.004, -0.11), (-0.007, -0.05), (0.006, 0.0), (-0.005, 0.05), (0.003, 0.12)]]
    out.append(P.decal_lines(slit, frame_at((0.0, -0.13, 1.94), (0, -1, 0)), 0.016, zones=["obsidian"],
                             color="#6FD8C0", rim="#07060A", rim_width=0.04, emit=TEAL, depth=(-0.12, 0.12), facing=0.2))
    # the runes: a hot core line down every stroke, on both faces of each glyph
    for k in range(6):
        ang = math.radians(RUNE_ANGLES[k])
        radial = CROWN_E1 * math.cos(ang) + CROWN_E2 * math.sin(ang)
        tang = CROWN_AXIS.cross(radial).normalized()
        gl = GLYPHS["A" if k % 2 == 0 else "B"]
        for sgn in (1, -1):
            o = rune_pos(k) + CROWN_AXIS * 0.025 * sgn
            z = CROWN_AXIS * sgn
            y = tang * sgn
            fr = Matrix(((radial.x, y.x, z.x, o.x), (radial.y, y.y, z.y, o.y), (radial.z, y.z, z.z, o.z), (0, 0, 0, 1)))
            lines = [[(px, py * sgn) for px, py in ln] for ln in gl]
            out.append(P.decal_lines(lines, fr, 0.024, zones=["rune"], color="#FFB48A", rim=None,
                                     emit={"color": MOLTEN, "core": "#FFC8A8"}, depth=(-0.03, 0.03), facing=0.4))
    # the big arm: a few BOLD molten cracks (never a web), read from the game camera
    for o, nrm, ang, L, sd in (((-0.56, -0.2, 2.02), (-0.7, -0.6, 0.35), -60, 0.26, 3),
                               ((-0.5, 0.05, 1.77), (-0.8, -0.2, 0.5), -100, 0.22, 4)):
        lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.045, jag=0.4,
                              branches=1, branch_len=0.4, depth=1)
        out.append(P.decal_lines(lines, frame_at(o, nrm), 0.026, zones=["arm"], color="#FF6B1A", rim="#07060A",
                                 rim_width=0.06, emit=HOT, depth=(-0.2, 0.2), facing=0.25))
    # the mantle: one teal crack running from the shards across the left shoulder (the Unmade under the slag)
    for o, nrm, ang, L, sd in (((0.22, 0.06, 1.75), (0.4, -0.2, 1.0), 205, 0.3, 8),
                               ((0.3, 0.2, 1.68), (0.5, 0.6, 0.8), 150, 0.26, 9)):
        lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.05, jag=0.45,
                              branches=1, branch_len=0.45, depth=1)
        out.append(P.decal_lines(lines, frame_at(o, nrm), 0.03, zones=["slag"], color="#2FBFA8", rim="#07060A",
                                 rim_width=0.065, emit=TEAL, depth=(-0.12, 0.12), facing=0.3))
    # the overrobe: two BOLD molten cracks rising from its torn hem (the crust splitting as it sags toward the slag
    # arm), so the one long tier is cooling slag, not cloth. Placed on the robe surface itself (build_robe's fn)
    at = HEM_FN.get("robe")
    if at is not None:
        for th, v0, ang, L, sd in ((-124.0, 0.985, 98.0, 0.56, 21), (-50.0, 0.985, 84.0, 0.3, 23)):
            o = at(th, v0)
            n = (at(th + 1.0, v0) - at(th - 1.0, v0)).cross(at(th, v0 + 0.02) - at(th, v0 - 0.02)).normalized()
            if n.dot(Vector((o.x, o.y, 0.0))) < 0.0:
                n = -n
            lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.06, jag=0.55,
                                  branches=0, depth=0)        # single fissures: a forked crack reads as a glyph (Y)
            out.append(P.decal_lines(lines, frame_at(o, n), 0.034, zones=["slag"], color=MOLTEN, rim="#07060A",
                                     rim_width=0.075, emit=HOT, depth=(-0.14, 0.06), facing=0.3))
    return out


# ---- figure / ground passes (adapted from enemies/slag_king.py) ----------------------------------------------
# The Cinder floor is mauve-brown flagstones (L* 17-39) with oxblood gaps (L* 6), so a near-black slag drowned in
# the gaps (the art review: 30-35 % of the hexer's pixels within +-7 L* of the gaps and dark stones). The slag
# body is a cool coal (#3E3234, a hue off the warm floor) and painted passes separate the rest:
#   * TOP PLANES: planes facing up (the hem lips, the cowl top) are lifted to ash #6E625C with a brushy
#     boundary; the cape (the yoke) and the shoulder boulder - the broad planes the 55 deg camera sees first - get
#     the palest ash #877A72 over a wider band, above every floor stone. The steep robe sides stay coal;
#   * EDGE STROKES only on real creases of the texel's OWN part, weighted toward up-facing planes: every hem
#     lip of the tower gets one light stroke along its top;
#   * SEAM GLOW: the band right under each tier's hem (and under the mantle) leaks the molten inside: a hot
#     orange line under the lip cooling to a dim red band, the base warmed to a hot-slag red. This is the
#     tower's rhythm: dark lip, lit edge, molten seam;
#   * UNDERGLOW: the drip tongues standing in the pool heat up toward the ground.
EDGE_SLAG = {"color": ASH_EDGE, "width": 0.02, "breakup": 0.3, "up": (-0.1, 0.5), "amount": 1.0, "min_angle": 40.0}
EXTRAS = {
    # the robe bodies face up only 10-25 deg (normal z 0.2-0.4), the flared lips more: the band sits between them,
    # with little noise, so the lift never breaks a body into lifted / unlifted camouflage patches. top_parts: the
    # cape (normal z 0.6-0.75) and the shoulder boulder take the palest ash over a wider band (part, colour, amount,
    # band); top_guard: texels already this bright (luma) are not lifted
    "slag": {"top": (ASH, 0.9), "top_band": (0.46, 0.6), "top_noise": 0.08, "side": 0.0, "edge": EDGE_SLAG,
             "top_guard": (0.34, 0.5),
             "top_parts": {"yoke": (ASH_PALE, 1.0, (0.36, 0.56)), "pauldron_R": (ASH_PALE, 1.0, (0.1, 0.45)),
                           "peak": (ASH, 0.9, (0.3, 0.55))},
             # body values: the overrobe lightens upward under the cape (ash dust, the crucible's bounce); the
             # underskirt wedge is a lighter cooled crust than the overrobe, so the diagonal hem reads as a value
             # step, and the lower robe never sinks into the floor gaps
             "body": {"robe": {"color": SLAG_UPPER, "z": (0.85, 1.45)}, "skirt1": {"color": SLAG_UNDER}},
             "seam": True, "under": True},
    "arm": {"top": ("#76685F", 0.75), "top_band": (0.3, 0.55), "side": 0.15, "top_guard": (0.34, 0.5),
            "edge": dict(EDGE_SLAG, width=0.016, amount=0.8)},
    "iron": {"edge": {"color": "#A49CA6", "width": 0.016, "breakup": 0.15, "up": (-0.3, 0.4), "amount": 0.95,
                      "min_angle": 25.0}},
}
SEAM = {"band": 0.13, "rim": "#C8400C", "hot": "#FF6B1A", "tint": "#6E2410", "emit": 0.85, "warm": 0.5}
UNDER = {"height": (0.16, 0.01), "rim": "#C8400C", "hot": "#FF6B1A", "tint": "#5A1C0C", "warm": 0.45}
SEAM_BELOW = {"skirt1_fl": "robe", "skirt1_fr": "robe", "skirt1_b": "robe", "robe": "yoke"}


def part_crease_points(obj, min_angle, spacing=0.002, sharp_only_below=60.0):
    """Convex crease samples grouped by part id (an edge counts only inside ONE part)."""
    import bmesh as _bm
    from collections import defaultdict
    bm = _bm.new()
    bm.from_mesh(obj.data)
    layer = bm.faces.layers.int.get("gfa_part")
    out = defaultdict(list)
    lim, big = math.radians(min_angle), math.radians(sharp_only_below)
    for e in bm.edges:
        if not e.is_manifold:
            continue
        ang = e.calc_face_angle_signed(0.0)
        if ang <= 0 or ang < lim or (e.smooth and ang < big):
            continue
        f0, f1 = e.link_faces
        if f0[layer] != f1[layer]:
            continue
        p0, p1 = e.verts[0].co.copy(), e.verts[1].co.copy()
        n = max(1, int((p1 - p0).length / spacing))
        out[f0[layer]].extend(p0.lerp(p1, (i + 0.5) / n) for i in range(n))
    bm.free()
    return out


def part_edge_dist(P, crease, pos, part, cap=0.05):
    import numpy as np
    d = np.full(len(pos), cap, dtype=np.float32)
    for pid in np.unique(part):
        pts = crease.get(int(pid))
        if pts:
            idx = np.nonzero(part == pid)[0]
            d[idx] = P._kd_dist(pts, pos[idx], cap)
    return d


def _hem_table(name):
    """z of a tier's hem over theta (0.5 deg steps, index = (theta + 180) * 2)."""
    import numpy as np
    at = HEM_FN[name]
    return np.array([at(-180.0 + 0.5 * k, 1.0).z for k in range(721)], dtype=np.float32)


def paint_extras(P, maps, zones_order, recipes_, base, emis, obj, seed=0):
    import numpy as np
    pos, Z, part = maps["pos"], maps["zone"], maps["part"]
    names = obj["gfa_part_names"].split(",")
    wobble = P.spread01(P.fbm(pos, 30.0, 2, seed=seed + 5))
    dabs = P.spread01(P.fbm(pos, 11.0, 2, seed=seed + 6))
    crease = {}
    tables = {}
    for zname, ex in EXTRAS.items():
        if zname not in zones_order:
            continue
        m = Z == zones_order.index(zname)
        if not m.any():
            continue
        p, nz = pos[m], maps["snrm"][m, 2]
        c = base[m]
        brush = P.spread01(P.fbm(p, 4.0, 2, seed=seed + 501))
        # body values per part (before the top lift): a flat tint, and a gradient up the part's height
        for pname, bv in ex.get("body", {}).items():
            sel = np.isin(part[m], [i for i, n in enumerate(names) if n == pname or n.startswith(pname + "_")])
            if not sel.any():
                continue
            b0 = P.hex3(recipes_[zname]["base"])
            k = np.full(int(sel.sum()), bv.get("amount", 1.0), dtype=np.float32)
            if "z" in bv:
                z0, z1 = bv["z"]
                k = k * P.smoothstep(z0, z1, p[sel, 2] + (brush[sel] - 0.5) * 0.12)
            ratio = P.hex3(bv["color"]) / np.maximum(b0, 1e-3)
            c[sel] = c[sel] * (1.0 + (ratio - 1.0)[None, :] * k[:, None])
        if ex.get("top"):
            col, amt = ex["top"]
            b0 = P.hex3(recipes_[zname]["base"])
            nb = nz + (brush - 0.5) * ex.get("top_noise", 0.3)
            lo_, hi_ = ex.get("top_band", (0.3, 0.52))
            k = ex.get("side", 0.0) * P.smoothstep(-0.3, 0.05, nb) + (1.0 - ex.get("side", 0.0)) * P.smoothstep(lo_, hi_, nb)
            k = k * amt
            tgt = np.repeat(P.hex3(col)[None], len(p), 0)
            for pname, (pcol, pamt, (plo, phi)) in ex.get("top_parts", {}).items():
                sel = np.isin(part[m], [i for i, n in enumerate(names) if n == pname])
                if sel.any():
                    k[sel] = pamt * P.smoothstep(plo, phi, nb[sel])
                    tgt[sel] = P.hex3(pcol)
            lum = c @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
            g0, g1 = ex.get("top_guard", (0.2, 0.36))
            k = k * (1.0 - P.smoothstep(g0, g1, lum))
            ratio = tgt / np.maximum(b0, 1e-3)[None, :]
            c = c * (1.0 + (ratio - 1.0) * k[:, None])
        ed = ex.get("edge")
        if ed:
            if ed["min_angle"] not in crease:
                crease[ed["min_angle"]] = part_crease_points(obj, ed["min_angle"])
            d = part_edge_dist(P, crease[ed["min_angle"]], p, part[m])
            ew = ed["width"] * (0.35 + 1.1 * wobble[m])
            k = P.smoothstep(ew, ew * 0.3, d)
            k = k * P.smoothstep(ed["breakup"] - 0.12, ed["breakup"] + 0.12, dabs[m])
            k = k * P.smoothstep(ed["up"][0], ed["up"][1], nz) * ed["amount"]
            c = P.mix(c, P.hex3(ed["color"]), k)
        e_out = emis[m]
        if ex.get("seam"):
            pm = part[m]
            heat = np.zeros(len(p), dtype=np.float32)
            th = np.degrees(np.arctan2(p[:, 1], p[:, 0]))
            ti = np.clip(np.round((th + 180.0) * 2.0).astype(np.int64), 0, 720)
            brush2 = P.spread01(P.fbm(p, 9.0, 2, seed=seed + 502))
            for lower, upper in SEAM_BELOW.items():
                ids = [i for i, n in enumerate(names) if n == lower]
                if not ids:
                    continue
                sel = np.isin(pm, ids)
                if not sel.any():
                    continue
                if upper not in tables:
                    tables[upper] = _hem_table(upper)
                zh = tables[upper][ti[sel]]
                t = (zh - p[sel, 2]) / SEAM["band"] + (brush2[sel] - 0.5) * 0.35     # 0 right under the lip
                heat[sel] = np.where(t > -0.05, 1.0 - P.smoothstep(0.0, 1.0, t), 0.0)
            warm = P.smoothstep(0.15, 0.45, heat)
            hot = P.smoothstep(0.72, 0.9, heat)
            c = P.mix(c, P.hex3(SEAM["tint"]), warm * SEAM["warm"])
            c = P.mix(c, P.hex3(SEAM["rim"]), hot * 0.4)
            e = P.mix(np.repeat(P.hex3(SEAM["rim"])[None] * 0.55, len(p), 0) * warm[:, None], P.hex3(SEAM["hot"]), hot)
            e_out = np.maximum(e_out, e * SEAM["emit"])
        if ex.get("under"):
            z0, z1 = UNDER["height"]
            h = np.clip((z0 - p[:, 2]) / (z0 - z1), 0.0, 1.0)
            brush3 = P.spread01(P.fbm(p, 8.0, 2, seed=seed + 503))
            warm = P.smoothstep(0.35, 0.65, h + (brush3 - 0.5) * 0.4)
            hot = P.smoothstep(0.88, 0.97, h + (brush3 - 0.5) * 0.08)
            c = P.mix(c, P.hex3(UNDER["tint"]), warm * UNDER["warm"])
            c = P.mix(c, P.hex3(UNDER["rim"]), hot * 0.4)
            e = P.mix(np.repeat(P.hex3(UNDER["rim"])[None] * 0.35, len(p), 0) * warm[:, None], P.hex3(UNDER["hot"]), hot)
            e_out = np.maximum(e_out, e)
        emis[m] = e_out
        base[m] = c
    return base, emis


def apply_decals(P, maps, zones_order, base, emis, decals_):
    """The decal loop of gfa_paint.paint (painted lines, burnt rims, glowing channels)."""
    import numpy as np
    Z = maps["zone"]
    for dec in decals_:
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
def extra_paint_passes(obj):
    """Within the block, gfa_paint.paint also runs paint_extras() between the zones and the decals (gfa_paint is
    unchanged: this build wraps it for its one paint call, like enemies/slag_king.py)."""
    import numpy as np
    import gfa_paint as P
    orig = P.paint

    def paint(maps, zones_order, recipes_, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes_, dist_convex, dist_concave, (), seed)
        paint_extras(P, maps, zones_order, recipes_, base, emis, obj, seed=seed)
        apply_decals(P, maps, zones_order, base, emis, decals)
        return np.clip(base, 0, 1), np.clip(emis, 0, 1)

    P.paint = paint
    try:
        yield
    finally:
        P.paint = orig


def paint_mesh(mesh, tex_dir, size=1024):
    import gfa_paint as P
    with extra_paint_passes(mesh):
        return P.paint_asset(mesh, KEY, recipes(), tex_dir, size=size, decals=decals(), ao_distance=0.14,
                             ao_samples=24, seed=11, uv_angle=66.0, margin_px=3, uv_zone_scale={"void": 0.3, "pool": 0.4},
                             uv_small_islands=(0.0012, 0.5))


# ---- rig ------------------------------------------------------------------------------------------------------

def build_rig(col):
    table = [(n, par, tuple(P_(h)), tuple(P_(t))) for n, par, h, t in BONES]
    arm = RD.build_armature(RIG_NAME, table, col)
    probs = RD.validate_core(arm)
    if probs:
        raise RuntimeError("rig problems: %s" % probs)
    return arm


SOCKETS = {
    "hit_center": ("spine_03", (0.0, 0.0, 1.45)),
    "fx_core": ("molten", tuple(CRUCIBLE + Vector((0, 0, 0.08)))),        # the white-hot melt (glow, death burst)
    "attack_origin": ("crown_spin", tuple(CROWN_C)),                     # the focus ring: the beam leaves through it
    "fx_mouth": ("crucible", tuple(CRUCIBLE + Vector((0.0, -0.42, 0.1)))),  # the pour lip (spill / drip VFX)
    "head_top": ("head", (0.0, -0.1, 2.95)),
}


def add_sockets(arm):
    import gfa_rig as RIG
    return {name: RIG.add_socket(arm, bone, name, pos, size=0.06) for name, (bone, pos) in SOCKETS.items()}


def _blend(A, B, w):
    if w <= 0:
        return A.copy()
    if w >= 1:
        return B.copy()
    q = A.to_quaternion().slerp(B.to_quaternion(), w)
    m = q.to_matrix().to_4x4()
    m.translation = A.translation.lerp(B.translation, w)
    return m


class Solver:
    """Poses GF_MoltenHexer_v1 from a parameter dict in armature space:
      body:              loc (dx, dy, dz) WORLD offset of the pelvis; rot (x bend fwd, y twist left, z roll)
      spine_01..03, neck, head, clavicle_*, thigh_*, shin_*, molten, pool:  rot / loc / scale, bone-local
                         (bones point up: X = left, Y = up, Z = front; legs point down: +X swings them forward)
      crucible:          loc (dx, dy, dz) WORLD offset, rot (x tips the mouth forward, y, z) about the bowl centre;
                         space 0 = rides the chest (spine_03), 1 = the ground
      ring:              r (radial offset of every rune, m), spin (deg about the ring axis), lift (m along the
                         axis), tilt (extra deg, x), bob (m, a 3-crest wave round the ring), phase (rad),
                         fall (0..1: the runes drop to the ground)
      arm_L / arm_R:     w (1 = the wrist follows the crucible, 0 = the chest), off (world offset of the wrist),
                         hint (added to the elbow direction), rot (hand-local deg)
    """

    FK = ("spine_01", "spine_02", "spine_03", "neck", "head", "clavicle_L", "clavicle_R", "thigh_L", "thigh_R",
          "shin_L", "shin_R", "molten", "pool")

    def __init__(self, arm):
        self.arm = arm
        self.R = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        rng = random.Random(17)
        self.ground = []
        for k in range(6):
            a = math.radians(RUNE_ANGLES[k] + rng.uniform(-20, 20))
            r = rng.uniform(0.75, 1.05)
            yaw = rng.uniform(-60, 60)
            pos = Vector((r * math.cos(a), -0.35 + r * math.sin(a) * 0.9, 0.035))
            G = (Matrix.Translation(pos) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
                 @ Matrix.Rotation(math.radians(-CROWN_TILT), 4, "X") @ self.R["rune_%d" % k].to_3x3().to_4x4())
            self.ground.append(G)

    def _fk(self, bone, tr):
        pb = self.arm.pose.bones[bone]
        if "rot" in tr:
            pb.rotation_euler = RD.euler_deg(tr["rot"])
        if "loc" in tr:
            pb.location = Vector(tr["loc"])
        if "scale" in tr:
            sc = tr["scale"]
            pb.scale = (sc, sc, sc) if isinstance(sc, (int, float)) else tuple(sc)

    def _follow(self, bone_now, bone_rest, X):
        return self.arm.pose.bones[bone_now].matrix @ self.R[bone_rest].inverted() @ X

    def pose(self, p):
        arm, R = self.arm, self.R
        RD.reset(arm)
        body = p.get("body", {})
        pv = arm.pose.bones["pelvis"]
        d = Vector(body.get("loc", (0, 0, 0)))
        pv.location = (d.x, d.z, -d.y)
        pv.rotation_euler = RD.euler_deg(body.get("rot", (0, 0, 0)))
        for b in self.FK:
            if b in p:
                self._fk(b, p[b])
        # the ring: crown (lift, tilt) -> crown_spin (spin) -> runes (radial, bob)
        ring = p.get("ring", {})
        spin = float(ring.get("spin", 0.0))
        self._fk("crown", {"loc": (0.0, ring.get("lift", 0.0), 0.0),
                           "rot": (ring.get("tilt", 0.0), 0.0, ring.get("roll", 0.0))})
        self._fk("crown_spin", {"rot": (0.0, spin, 0.0)})
        dr, bob, ph = ring.get("r", 0.0), ring.get("bob", 0.0), ring.get("phase", 0.0)
        for k in range(6):
            a = math.radians(RUNE_ANGLES[k])
            now = math.radians(RUNE_ANGLES[k] + spin)
            b_ = bob * math.sin(3.0 * now + ph)
            self._fk("rune_%d" % k, {"loc": (dr * math.cos(a), b_, dr * math.sin(a))})
        RD.update()
        # the crucible floats in chest space (blended to the ground when it falls)
        cr = p.get("crucible", {})
        chest = self._follow("spine_03", "spine_03", R["crucible"])
        ground = arm.pose.bones["root"].matrix @ R["root"].inverted() @ R["crucible"]
        W = _blend(chest, ground, float(cr.get("space", 0.0)))
        W.translation = W.translation + Vector(cr.get("loc", (0, 0, 0)))
        W = W @ RD.euler_deg(cr.get("rot", (0, 0, 0))).to_matrix().to_4x4()
        RD.set_matrix(arm, "crucible", W)
        # the arms reach for the crucible (or fall away from it)
        for side, sx in (("L", 1.0), ("R", -1.0)):
            ap = p.get("arm_" + side, {})
            w = float(ap.get("w", 1.0))
            Fc = self._follow("crucible", "crucible", Matrix.Identity(4))
            Fb = self._follow("spine_03", "spine_03", Matrix.Identity(4))
            F = _blend(Fb, Fc, w)
            wrist = (F @ R["hand_" + side]).translation + Vector(ap.get("off", (0, 0, 0)))
            hint = Vector((sx * 1.0, 0.25, -0.45)) + Vector(ap.get("hint", (0, 0, 0)))
            RD.two_bone_ik(arm, "upperarm_" + side, "lowerarm_" + side, wrist, hint)
            head = RD.rest_frame_now(arm, "hand_" + side).translation
            Hm = F @ R["hand_" + side] @ RD.euler_deg(ap.get("rot", (0, 0, 0))).to_matrix().to_4x4()
            Hm.translation = head
            RD.set_matrix(arm, "hand_" + side, Hm)
        # the runes fall to the ground (death)
        fall = float(ring.get("fall", 0.0))
        if fall > 0:
            for k in range(6):
                nm = "rune_%d" % k
                cur = arm.pose.bones[nm].matrix.copy()
                RD.set_matrix(arm, nm, _blend(cur, self.ground[k], fall), upd=False)
            RD.update()


# ---- clips ------------------------------------------------------------------------------------------------------
# Every clip starts and ends with the ring turned by a multiple of 120 deg (the glyphs repeat every 2 runes), so
# the ring pose at every clip boundary is the same.

def P2(*poses):
    return RD.merge(*poses)


def _ring(spin, **kw):
    d = {"spin": spin}
    d.update(kw)
    return d


def idle_pose(t):
    w = 2 * math.pi * t
    s, c = math.sin(w), math.cos(w)
    return {
        "body": {"loc": (0.008 * s, 0.0, 0.01 * math.sin(2 * w)), "rot": (0.0, 1.2 * s, 1.0 * c)},
        "spine_02": {"rot": (1.2 * math.sin(w + 0.5), 0.0, 1.0 * c)},
        "spine_03": {"rot": (-1.2 * math.sin(w + 1.0), 1.5 * s, 0.0)},
        "neck": {"rot": (1.0 * math.sin(w + 1.2), 0.0, 0.0)},
        "head": {"rot": (2.5 * math.sin(w + 1.3), 4.0 * math.sin(w + 0.2), 0.0)},
        "crucible": {"loc": (0.012 * s, 0.008 * c, 0.035 * math.sin(2 * w + 0.4)), "rot": (2.5 * s, 0.0, 2.0 * c)},
        "ring": _ring(120.0 * t, bob=0.03, phase=w),
        "molten": {"scale": 1.0 + 0.05 * math.sin(2 * w)},
        "thigh_L": {"rot": (1.0 * s, 0.0, 0.0)}, "thigh_R": {"rot": (-1.0 * s, 0.0, 0.0)},
    }


MOVE_FRAMES = 24
MOVE_CYCLE_M = 2.4 * MOVE_FRAMES / FPS      # the row's speed 2.4 m/s at natural playback (client: speed / this)


def move_pose(t):
    w = 2 * math.pi * t
    s = math.sin(w)
    return {
        "body": {"loc": (0.02 * s, -0.02, -0.025 + 0.02 * math.cos(2 * w)), "rot": (6.0, 3.0 * s, -2.0 * s)},
        "spine_01": {"rot": (2.0, 0.0, 0.0)},
        "spine_02": {"rot": (2.0, 2.0 * s, 1.0 * s)},
        "spine_03": {"rot": (1.0, -2.5 * s, 0.0)},
        "head": {"rot": (-6.0, -2.0 * s, 0.0)},
        "thigh_L": {"rot": (15.0 * s, 0.0, 0.0)}, "thigh_R": {"rot": (-15.0 * s, 0.0, 0.0)},
        "crucible": {"loc": (0.0, 0.07, 0.025 * math.sin(2 * w)), "rot": (-6.0 + 2.0 * math.sin(2 * w), 0.0, 3.0 * s)},
        "ring": _ring(120.0 * t, tilt=-7.0, bob=0.035, phase=w),
        "molten": {"scale": 1.0 + 0.04 * math.sin(2 * w)},
    }


# key poses (absolute, the rest pose = the idle stance)
LOADED = {   # the channel: reared back, the crucible hoisted high and tipped back, the ring pulled in tight
    "body": {"loc": (0.0, 0.08, -0.06), "rot": (-8.0, 0.0, 0.0)},
    "spine_02": {"rot": (-4.0, 0.0, 0.0)}, "spine_03": {"rot": (-7.0, 0.0, 0.0)}, "neck": {"rot": (-8.0, 0, 0)},
    "head": {"rot": (-18.0, 0.0, 0.0)},
    "crucible": {"loc": (0.0, 0.1, 0.28), "rot": (-20.0, 0.0, 0.0)},
    "ring": _ring(0.0, r=-0.16, lift=0.06, tilt=-4.0),
    "molten": {"scale": 1.25, "loc": (0.0, 0.015, 0.0)},
    "arm_L": {"hint": (0.3, 0.0, 0.2)}, "arm_R": {"hint": (-0.3, 0.0, 0.2)},
    "thigh_L": {"rot": (-3.0, 0, 0)}, "thigh_R": {"rot": (-3.0, 0, 0)},
}
FIRE = {     # the beam: thrust forward, the crucible tipped so its lip faces the target, the ring upright in front
    "body": {"loc": (0.0, -0.12, -0.08), "rot": (9.0, 0.0, 0.0)},
    "spine_02": {"rot": (5.0, 0.0, 0.0)}, "spine_03": {"rot": (6.0, 0.0, 0.0)}, "neck": {"rot": (4.0, 0, 0)},
    "head": {"rot": (4.0, 0.0, 0.0)},
    "crucible": {"loc": (0.0, -0.32, -0.62), "rot": (78.0, 0.0, 0.0)},
    "ring": _ring(0.0, r=-0.05, lift=0.4),
    "molten": {"scale": 1.1},
    "arm_L": {"hint": (0.2, 0.3, 0.3)}, "arm_R": {"hint": (-0.2, 0.3, 0.3)},
    "thigh_L": {"rot": (6.0, 0, 0)}, "thigh_R": {"rot": (-4.0, 0, 0)},
}
FLINCH = {
    "body": {"loc": (0.02, 0.07, -0.03), "rot": (-6.0, 4.0, -3.0)},
    "spine_02": {"rot": (-4.0, 2.0, 0.0)}, "spine_03": {"rot": (-6.0, 3.0, 3.0)}, "head": {"rot": (-14.0, 8.0, -6.0)},
    "crucible": {"loc": (0.02, 0.08, 0.1), "rot": (-12.0, 0.0, 8.0)},
    "ring": _ring(0.0, r=0.09, tilt=6.0, bob=0.05, phase=1.0),
    "molten": {"scale": 1.15},
}
SAG = {      # death, mid-fall: the slag tower sinks and folds, the crucible slips, the runes drop
    "body": {"loc": (0.0, -0.04, -0.3), "rot": (12.0, 6.0, 4.0)},
    "spine_01": {"rot": (6.0, 0, 0)}, "spine_02": {"rot": (10.0, 0, 3.0)}, "spine_03": {"rot": (10.0, 0, 4.0)},
    "neck": {"rot": (10.0, 0, 0)}, "head": {"rot": (20.0, 6.0, 8.0)},
    "crucible": {"loc": (0.08, -0.35, -1.0), "rot": (55.0, 10.0, 25.0), "space": 0.6},
    "ring": _ring(0.0, r=0.12, fall=0.55),
    "arm_L": {"w": 0.3, "off": (0.12, 0.05, -0.35)}, "arm_R": {"w": 0.3, "off": (-0.12, 0.05, -0.35)},
    "thigh_L": {"rot": (10.0, 0, -6.0)}, "thigh_R": {"rot": (8.0, 0, 6.0)},
    "molten": {"scale": 0.9},
    "pool": {"scale": (1.15, 1.0, 1.25), "loc": (0.0, 0.0, 0.08)},
}
HEAP = {     # death, held: a slumped heap of slag, the crucible on its side spilling, dead runes in the pool
    "body": {"loc": (0.0, -0.08, -0.56), "rot": (22.0, 10.0, 6.0)},
    "spine_01": {"rot": (10.0, 0, 3.0)}, "spine_02": {"rot": (14.0, 4.0, 4.0)}, "spine_03": {"rot": (14.0, 0, 6.0)},
    "neck": {"rot": (16.0, 0, 0)}, "head": {"rot": (28.0, 10.0, 14.0)},
    "crucible": {"loc": (0.12, -0.62, -2.18), "rot": (102.0, 18.0, 30.0), "space": 1.0},
    "ring": _ring(0.0, fall=1.0),
    "arm_L": {"w": 0.0, "off": (0.2, 0.0, -0.75), "hint": (0.0, 0.0, -0.5)},
    "arm_R": {"w": 0.0, "off": (-0.15, -0.1, -0.7), "hint": (0.0, 0.0, -0.5)},
    "thigh_L": {"rot": (14.0, 0, -12.0)}, "thigh_R": {"rot": (10.0, 0, 12.0)},
    "molten": {"scale": 0.55, "loc": (0.0, -0.03, 0.0)},
    "pool": {"scale": (1.25, 1.0, 1.45), "loc": (0.0, 0.0, 0.3)},
}


def channel_pose(t):
    """The long channel: LOADED held, the ring whirling (240 deg a loop), the melt surging, a tremor."""
    w = 2 * math.pi * t
    tr = 0.006
    return P2(LOADED, {
        "body": {"loc": (tr * math.sin(3 * w), 0.08 + tr * math.sin(5 * w), -0.06 + 0.012 * math.sin(2 * w)),
                 "rot": (-8.0 + 0.8 * math.sin(2 * w), 1.0 * math.sin(w), 0.0)},
        "crucible": {"loc": (0.008 * math.sin(4 * w), 0.1, 0.28 + 0.02 * math.sin(2 * w)),
                     "rot": (-20.0 + 2.0 * math.sin(2 * w), 0.0, 2.0 * math.sin(3 * w))},
        "ring": _ring(240.0 * t, r=-0.16 + 0.02 * math.sin(2 * w), lift=0.06, tilt=-4.0, bob=0.02, phase=2 * w),
        "molten": {"scale": 1.25 + 0.08 * math.sin(2 * w), "loc": (0.0, 0.015, 0.0)},
    })


def sweep_pose(t):
    """The beam held and dragged across the arena: FIRE with the upper body and the focus yawing +-28 deg."""
    w = 2 * math.pi * t
    yaw = 28.0 * math.sin(w)
    return P2(FIRE, {
        "body": {"loc": (0.03 * math.sin(w), -0.12, -0.08), "rot": (9.0, 0.4 * yaw, 2.0 * math.sin(w))},
        "spine_02": {"rot": (5.0, 0.3 * yaw, 0.0)}, "spine_03": {"rot": (6.0, 0.3 * yaw, 0.0)},
        "head": {"rot": (4.0, 0.1 * yaw, 0.0)},
        "crucible": {"loc": (0.0, -0.32, -0.62 + 0.02 * math.sin(4 * w)), "rot": (78.0 + 2.0 * math.sin(4 * w), 0.0, 0.0)},
        "ring": _ring(480.0 * t, r=-0.05 + 0.015 * math.sin(4 * w), lift=0.4),
        "molten": {"scale": 1.1 + 0.05 * math.sin(4 * w)},
        "thigh_L": {"rot": (6.0 + 3.0 * math.sin(w), 0, 0)}, "thigh_R": {"rot": (-4.0 - 3.0 * math.sin(w), 0, 0)},
    })


def clip_defs():
    """{clip: (frames, pose(frame) -> params)}"""
    K = RD.Keys
    g0 = idle_pose(0.0)
    windup = K([(0, g0),
                (6, P2(LOADED, {"body": {"loc": (0.0, 0.03, -0.1)}, "crucible": {"loc": (0.0, 0.04, 0.08)},
                                "ring": _ring(90.0, r=-0.08, lift=0.03)}), "ease"),
                (18, P2(LOADED, {"ring": _ring(240.0, r=-0.16, lift=0.06, tilt=-4.0)}), "out")])
    attack = K([(0, P2(LOADED, {"ring": _ring(0.0, r=-0.16, lift=0.06, tilt=-4.0)})),
                (3, P2(LOADED, {"body": {"loc": (0.0, 0.11, -0.08)}, "crucible": {"loc": (0.0, 0.14, 0.32)},
                                "ring": _ring(40.0, r=-0.18, lift=0.06, tilt=-4.0)}), "ease"),
                (7, P2(FIRE, {"ring": _ring(150.0, r=0.02, lift=0.42)}), "snap"),
                (15, P2(FIRE, {"body": {"loc": (0.0, -0.1, -0.08)}, "ring": _ring(300.0, r=-0.05, lift=0.4)}), "linear"),
                (25, P2(idle_pose(0.0), {"ring": _ring(360.0)}), "ease")])
    hit = K([(0, g0), (3, P2(g0, FLINCH), "out"), (10, g0, "ease")])
    death = K([(0, g0),
               (4, P2(g0, FLINCH, {"body": {"loc": (0.0, 0.1, -0.04)}, "ring": _ring(20.0, r=0.14, tilt=10.0)}), "out"),
               (16, P2(g0, SAG, {"ring": _ring(60.0, r=0.12, fall=0.55)}), "ease"),
               (26, P2(g0, HEAP, {"body": {"loc": (0.0, -0.06, -0.5)}, "pool": {"scale": (1.25, 1.0, 1.4), "loc": (0, 0, 0.15)},
                                  "ring": _ring(80.0, fall=1.0)}), "in"),
               (32, P2(g0, HEAP, {"crucible": {"loc": (0.12, -0.6, -2.12), "rot": (96.0, 18.0, 30.0), "space": 1.0},
                                  "ring": _ring(90.0, fall=1.0)}), "out"),
               (40, P2(g0, HEAP, {"ring": _ring(96.0, fall=1.0)}), "ease"),
               (56, P2(g0, HEAP, {"ring": _ring(96.0, fall=1.0), "molten": {"scale": 0.4, "loc": (0.0, -0.05, 0.0)},
                                  "pool": {"scale": (1.3, 1.0, 1.55), "loc": (0.0, 0.0, 0.36)}}), "out")])
    return {
        "idle@loop": (72, lambda f: idle_pose(f / 72.0)),
        "move@loop": (MOVE_FRAMES, lambda f: move_pose(f / float(MOVE_FRAMES))),
        "windup": (windup.length, windup.at),
        "attack": (attack.length, attack.at),
        "hit": (hit.length, hit.at),
        "death": (death.length, death.at),
        "channel@loop": (30, lambda f: channel_pose(f / 30.0)),
        "beam_sweep@loop": (60, lambda f: sweep_pose(f / 60.0)),
    }


CLIP_ROLES = {
    "idle@loop": "hovering stance: the crucible bobs over the cowl, the rune ring turns slowly (120 deg a loop), the melt breathes",
    "move@loop": "glide: leaning in, the front robe panels step, the crucible trails and the ring tilts back",
    "windup": "the channel begins: it rears back and hoists the crucible, the ring pulls in tight and whirls (ends loaded)",
    "attack": "the beam: the crucible is thrust forward and tipped, the ring swings upright in front of the lip "
              "(the beam passes through it), a hold, then back to the stance",
    "hit": "flinch: the crucible jolts, the runes are flung outward",
    "death": "the tower sags and sinks into itself, the crucible slips and spills on its side, the runes drop into "
             "the spreading pool (held)",
    "channel@loop": "the long channel pose: loaded and trembling, the ring whirling (240 deg a loop), the melt surging "
                    "(play after windup while the sim holds the windup)",
    "beam_sweep@loop": "the beam held and dragged across the arena: the fire pose with the torso and the focus yawing "
                       "+-28 deg, the ring spinning fast",
}
CLIP_SHORT = {   # the clip sheet's labels (the full roles go to meta.json)
    "idle@loop": "the crucible bobs over the cowl, the ring turns 120 deg a loop",
    "move@loop": "glide: the front robe panels step, the crucible trails",
    "windup": "rears back, hoists the crucible, the ring pulls in and whirls (ends loaded)",
    "attack": "crucible thrust forward and tipped, the ring upright in front of the lip; fire at f7",
    "hit": "the crucible jolts, the runes are flung outward",
    "death": "the tower sinks, the crucible spills on its side, the runes drop (held)",
    "channel@loop": "the long channel: loaded, trembling, the ring whirling 240 deg a loop",
    "beam_sweep@loop": "the beam dragged across the arena: torso and focus yaw +-28 deg",
}
CLIP_ALIASES = {"channel": "channel@loop", "beam": "attack", "sweep@loop": "beam_sweep@loop"}
EVENTS = {"attack": {"beam_fire_s": round(7 / FPS, 3), "beam_end_s": round(15 / FPS, 3)},
          "death": {"crucible_lands_s": round(26 / FPS, 3)}}


def build_clips(arm, mesh):
    sol = Solver(arm)
    names = []
    for clip, (frames, fn) in clip_defs().items():
        RD.bake_clip(arm, KEY, clip, int(frames), lambda a, f, fn=fn: sol.pose(fn(f)), mute_meshes=[mesh])
        names.append(RD.clip_name(KEY, clip))
    return names, sol


# ---- review renders ---------------------------------------------------------------------------------------------

KEY_FRAMES = {
    "idle@loop": (0, 18, 36, 54), "move@loop": (0, 6, 12, 18), "windup": (0, 6, 12, 18),
    "attack": (0, 3, 7, 15, 25), "hit": (0, 3, 10), "death": (0, 4, 16, 26, 40, 56),
    "channel@loop": (0, 8, 15, 23), "beam_sweep@loop": (0, 15, 30, 45),
}
GAME_POSES = [("idle@loop", 0, "idle"), ("windup", 18, "channel (loaded)"), ("attack", 7, "beam fires"),
              ("beam_sweep@loop", 15, "beam sweep"), ("hit", 3, "hit"), ("death", 56, "death (held)")]


def game_d():
    return Vector((0.0, -math.cos(math.radians(55.0)), math.sin(math.radians(55.0))))


def clip_sheet(arm, mesh, reports, work, clips_rep):
    import gfa_render as R
    import gfa_rig as RIG
    scene = bpy.context.scene
    R.setup_cycles(scene, 10)
    view = Vector((0.7, -1.0, 0.42)).normalized()
    sections = []
    with R.toon_preview([mesh], ink=0.012):
        for clip, frames in KEY_FRAMES.items():
            tr = RD.clip_name(KEY, clip)
            ims = []
            for f in frames:
                RIG.pose_at(arm, tr, f)
                R.aim(scene, Vector((0.0, -0.35, 1.42)), view, 3.85)
                ims.append({"path": R.render(scene, os.path.join(work, "clip_%s_%02d.png" % (clip.replace("@", "_"), f)), 250),
                            "label": "f%d" % f})
            secs = next((c["seconds"] for c in clips_rep if c["name"] == tr), 0)
            sections.append({"label": "%s  (%.2f s)  -  %s" % (tr, secs, CLIP_SHORT[clip]), "height": 190, "images": ims})
    RIG.unmute_none(arm)
    scene.frame_set(0)
    layout = {"title": "Molten Hexer - clips (key poses)",
              "subtitle": "GF_MoltenHexer_v1, 30 fps, every frame keyed; loops are periodic. The engine draws the red-white "
                          "line telegraph and the beam VFX (attack_origin = the focus ring).",
              "width": 1600, "sections": sections,
              "notes": ["Aliases (meta.json clip_aliases): channel = channel@loop, beam = attack, sweep@loop = beam_sweep@loop.",
                        "Caster mapping: the sim's windup = windup then channel@loop; the beam lands = attack."]}
    return R.contact_sheet(layout, os.path.join(reports, "%s_clips.png" % KEY), work)


def size_lineup(mesh, work):
    """Front orthographic lineup: the 2.2 m hero mannequin next to the hexer, with height bars."""
    import gfa_render as R
    import gfa_spec as SPEC
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (-1.6, 0.0, 0.0)
    _lo, hi = C.world_bounds([mesh])
    bars = []
    for h, x0, x1, hexc in ((SPEC.HERO_HEIGHT, -2.2, -1.0, "#7A8494"), (hi.z, -0.85, 0.85, "#FF6B1A")):
        me = bpy.data.meshes.new("BAR")
        me.from_pydata([(x0, 0.9, h - 0.008), (x1, 0.9, h - 0.008), (x1, 0.9, h + 0.008), (x0, 0.9, h + 0.008)], [],
                       [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("BAR", me)
        scene.collection.objects.link(ob)
        me.materials.append(R.toon_material("BARM", flat_hex=hexc, rim=0.0))
        bars.append(ob)
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 10)
    with R.toon_preview([mesh, man], ink=0.012, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, Vector((-0.55, 0.0, 1.42)), Vector((0.0, -1.0, 0.0)), 3.7)
        scene.render.resolution_x, scene.render.resolution_y = 900, 760
        scene.render.filepath = os.path.join(work, "%s_size_lineup.png" % KEY)
        scene.camera.data.ortho_scale = 3.7
        bpy.ops.render.render(write_still=True)
    C.remove_objects([man] + bars)
    return scene.render.filepath, round(hi.z, 3)


def game_pose_strip(arm, mesh, work, px=210):
    """The game camera at TRUE 1080p pixel size (view height 22 m) for the key poses, with the mannequin."""
    import gfa_render as R
    import gfa_rig as RIG
    import gfa_spec as SPEC
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-1.9, 0.4, 0.0)
    floor = bpy.data.meshes.new("GFLOOR")
    floor.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("GFLOOR", floor)
    scene.collection.objects.link(fo)
    floor.materials.append(R.toon_material("GFLOORM", flat_hex=R.FLOOR, rim=0.0))
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 16, bg=R.FLOOR)
    tgt = Vector((-0.55, -0.3, 1.0))
    out = []
    with R.toon_preview([mesh, man], ink=0.012, flat={man.name: R.MANNEQUIN}):
        for clip, f, label in GAME_POSES:
            RIG.pose_at(arm, RD.clip_name(KEY, clip), f)
            R.aim(scene, tgt, game_d(), px / ppm)
            out.append((R.render(scene, os.path.join(work, "game_%s_%02d.png" % (clip.replace("@", "_"), f)), px), label))
    RIG.pose_at(arm, RD.clip_name(KEY, "idle@loop"), 0)
    R.setup_workbench_flat(scene)
    fo.hide_render = True
    R.aim(scene, tgt, game_d(), px / ppm)
    sil = R.render(scene, os.path.join(work, "game_idle_sil.png"), px)
    RIG.unmute_none(arm)
    scene.frame_set(0)
    C.remove_objects([man, fo])
    return out, sil


def hero_shot(mesh, out_path, size=900, view=(0.62, -1.0, 0.36), target=(0.0, -0.2, 1.4), scale=3.25):
    import gfa_render as R
    scene = bpy.context.scene
    R.setup_cycles(scene, 16)
    with R.toon_preview([mesh], ink=0.011):
        R.aim(scene, Vector(target), Vector(view).normalized(), scale)
        return R.render(scene, out_path, size)


def _import_glb(key):
    """Import a shipped enemy GLB (read-only) for the roster shot; returns (armature, meshes, new objects)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=C.model_path("enemy", key))
    new = [o for o in bpy.data.objects if o not in before]
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    meshes = [o for o in new if o.type == "MESH"]
    return arm, meshes, new


def roster_shot(mesh, arm, work, px_w=760, px_h=440):
    """The hexer among its biome-mates at TRUE pixel size: the forge_warden (the other Cinder elite) and a clinker
    swarm, plus two hero mannequins - is the hexer distinct at a glance, and is it clearly an elite?"""
    import gfa_boss as B
    import gfa_render as R
    import gfa_rig as RIG
    RIG.pose_at(arm, RD.clip_name(KEY, "idle@loop"), 0)
    made, extra = [], []
    try:
        w_arm, w_meshes, w_new = _import_glb("forge_warden")
        made += w_new
        root = w_arm if w_arm else w_meshes[0]
        root.location = (3.0, 1.2, 0.0)
        root.rotation_euler = (0.0, 0.0, math.radians(20.0))
        extra += w_meshes
        for k, (x, y, yaw) in enumerate(((-2.6, -1.9, -30), (-1.4, -2.7, 10), (0.9, -2.5, -5), (2.3, -1.9, 25),
                                         (-3.2, -0.6, -60), (1.6, -3.4, 0))):
            c_arm, c_meshes, c_new = _import_glb("clinker")
            made += c_new
            r_ = c_arm if c_arm else c_meshes[0]
            r_.location = (x, y, 0.0)
            r_.rotation_euler = (0.0, 0.0, math.radians(yaw))
            extra += c_meshes
    except Exception as ex:  # noqa: BLE001 - the roster is a bonus review; never fail the build on it
        C.log("roster: could not import the biome-mates (%s)" % ex)
    heroes = []
    for k, (x, y) in enumerate(((-1.2, -5.6), (1.8, -5.2))):
        m = R.mannequin(aim_dir=(-x, -y, 0.0), name="GFA_HERO_%d" % k)
        m.location = (x, y, 0.0)
        heroes.append(m)
    bpy.context.view_layer.update()
    path = os.path.join(work, "%s_roster.png" % KEY)
    B.ingame_frame([mesh] + extra, path, px_w, px_h, 22.0, (0.0, -1.6, 0.6), heroes, ink=0.012, samples=12)
    C.remove_objects(heroes + [o for o in made if o.name in bpy.data.objects])
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    RIG.unmute_none(arm)
    return path


def look(mesh, out_dir):
    """Paint check without rig / clips / export (--look)."""
    import gfa_render as R
    scene = bpy.context.scene
    hero_shot(mesh, os.path.join(out_dir, "look_34.png"), size=640)
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh], ink=0.011):
        R.aim(scene, Vector((0.0, -0.25, 1.45)), game_d(), 3.1)
        R.render(scene, os.path.join(out_dir, "look_top55.png"), 640)
    man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-1.9, 0.4, 0.0)
    bpy.context.view_layer.update()
    r = R.ingame([mesh], out_dir, "look", px=210, mannequin_obj=man, target=(-0.55, -0.3, 1.0))
    C.remove_objects([man] + [o for o in (bpy.data.objects.get("GFA_FLOOR"),) if o])
    return r


# ---- quick preview (flat zone colours, no bakes) --------------------------------------------------------------

def preview_materials(mesh):
    import gfa_render as R
    for s_ in mesh.material_slots:
        z = s_.material.name[4:]
        m = R.toon_material("PV_" + z, flat_hex=PREVIEW.get(z, "#FF00FF"), rim=0.3)
        if z in GLOW_ZONES:
            nt = m.node_tree
            em = [n for n in nt.nodes if n.type == "EMISSION"][0]
            em.inputs["Strength"].default_value = 2.2
        s_.material = m


def preview(mesh, out_dir, stem="pv", size=420):
    import gfa_render as R
    scene = bpy.context.scene
    views = dict(R.CREATURE_VIEWS)
    views["game"] = tuple(game_d())
    pts = R._points([mesh])
    ext = max(max(R.frame(pts, d)[1:]) for d in views.values())
    R.setup_cycles(scene, 8)
    hull = R.add_ink_hull(mesh, 0.012)
    paths = []
    for name, d in views.items():
        c, _, _ = R.frame(pts, d)
        R.aim(scene, c, d, ext * 1.1)
        paths.append(R.render(scene, os.path.join(out_dir, "%s_%s.png" % (stem, name)), size))
    man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-1.9, 0.3, 0.0)
    man.data.materials.clear()
    man.data.materials.append(R.toon_material("PV_man", flat_hex=R.MANNEQUIN, rim=0.25))
    bpy.context.view_layer.update()
    mh = R.add_ink_hull(man, 0.012)
    ppm = 1080 / 22.0
    fl = bpy.data.meshes.new("PVFLOOR")
    fl.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    flo = bpy.data.objects.new("PVFLOOR", fl)
    scene.collection.objects.link(flo)
    fl.materials.append(R.toon_material("PV_floor", flat_hex=R.FLOOR, rim=0.0))
    R.setup_cycles(scene, 8, bg=R.FLOOR)
    px = 200
    R.aim(scene, Vector((-0.8, 0, 1.1)), game_d(), px / ppm)
    paths.append(R.render(scene, os.path.join(out_dir, "%s_ingame.png" % stem), px))
    R.aim(scene, Vector((0.0, -0.2, 1.3)), game_d(), 3.2)
    paths.append(R.render(scene, os.path.join(out_dir, "%s_game_close.png" % stem), 560))
    C.remove_objects([man, mh, flo, hull])
    return paths


def pose_renders(arm, mesh, out_dir, frames, size=240, view=(0.7, -1.0, 0.42), scale=3.6, target=(0.0, -0.35, 1.3)):
    import gfa_render as R
    import gfa_rig as RIG
    scene = bpy.context.scene
    R.setup_cycles(scene, 8)
    hull = R.add_ink_hull(mesh, 0.012)
    out = []
    for clip, fl in frames.items():
        tr = RD.clip_name(KEY, clip)
        for f in fl:
            RIG.pose_at(arm, tr, f)
            R.aim(scene, Vector(target), Vector(view).normalized(), scale)
            out.append(R.render(scene, os.path.join(out_dir, "pose_%s_%02d.png" % (clip.replace("@", "_"), f)), size))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    C.remove_objects([hull])
    return out


# ---- main ---------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    C.reset_scene(fps=FPS)
    bpy.context.preferences.filepaths.save_version = 0
    col = C.get_collection(KEY)
    mesh, _parts = build_mesh(col)
    lo, hi = C.world_bounds([mesh])
    C.log("bounds", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "preview"))
    if C.flag(argv, "--preview"):
        preview_materials(mesh)
        preview(mesh, work)
        C.log("DONE preview")
        return
    if C.flag(argv, "--look"):
        tex_dir = C.ensure_dir(os.path.join(pack, "work", "look"))
        rep = paint_mesh(mesh, tex_dir, C.opt(argv, "--size", 1024, int))
        C.log("paint", {k: rep[k] for k in ("texel_density_px_per_m", "coverage", "emissive_texels", "seconds")})
        look(mesh, tex_dir)
        C.log("DONE look")
        return
    size = C.opt(argv, "--size", 1024, int)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = None
    if not C.flag(argv, "--poses"):
        paint_rep = paint_mesh(mesh, tex_dir, size)       # paint before skinning (rest pose)
    arm = build_rig(col)
    C.log("skin", RD.skin_rigid(mesh, arm)["per_bone"])
    add_sockets(arm)
    clips, _solver = build_clips(arm, mesh)
    C.log("clips", clips)
    if C.flag(argv, "--poses"):
        preview_materials(mesh)
        only = C.opt(argv, "--clip", None)
        fr = {k: v for k, v in KEY_FRAMES.items() if only is None or k.startswith(only)}
        view = tuple(game_d()) if C.flag(argv, "--game") else (0.7, -1.0, 0.42)
        pose_renders(arm, mesh, work, fr, size=C.opt(argv, "--size", 240, int), view=view)
        C.log("DONE poses")
        return
    import gfa_boss as B
    import gfa_export as E
    import gfa_render as R
    import gfa_rig as RIG
    import gfa_spec as SPEC
    for alias, clip in CLIP_ALIASES.items():
        B.alias_clip(arm, KEY, alias, clip)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    clips_rep = RIG.clips_report(arm)
    lo, hi = C.world_bounds([mesh])
    extra = {
        "faction": "unmade",
        "rig": {"armature": RIG_NAME, "bones": len(arm.data.bones),
                "core": "GF_Hero_v1 core names and parents (23 bones, docs/ART_PIPELINE.md section 5); the legs are "
                        "hidden under the robe and swing its front panels",
                "extra_bones": ["crucible", "molten", "crown", "crown_spin"] + ["rune_%d" % k for k in range(6)] + ["pool"],
                "skinning": "rigid: every part on one bone (slag robe tiers, arms, the floating crucible and runes)",
                "rest_pose": "the idle stance (the crucible held over the cowl)",
                "axes": "bone +Y along the bone, +Z toward the front (Ashen Covenant roll convention)",
                "crown_spin": "the rune ring turns about crown_spin's local +Y; the clips bake the spin (a multiple of "
                              "120 deg per clip: the glyphs repeat every two runes). The client may add spin on top."},
        "clip_roles": {RD.clip_name(KEY, c): txt for c, txt in CLIP_ROLES.items()},
        "clip_aliases": {RD.clip_name(KEY, a_): RD.clip_name(KEY, b_) for a_, b_ in CLIP_ALIASES.items()},
        "clip_seconds": {c["name"]: c["seconds"] for c in clips_rep},
        "clip_events_s": {RD.clip_name(KEY, c): ev for c, ev in EVENTS.items()},
        "move_cycle_m": round(MOVE_CYCLE_M, 3),
        "caster_mapping": "Caster windup (the sim holds still under the line telegraph) -> windup (0.6 s), then "
                          "channel@loop until the beam lands -> attack (the fire key at %.2f s). A held or sweeping beam "
                          "-> beam_sweep@loop. Beam VFX from attack_origin (the focus ring), spill and drip VFX at "
                          "fx_mouth, the glow and the death burst at fx_core." % (7 / FPS),
        "footprint": {"collider_radius_m": 0.682, "row": "radius 0.62 x scale 1.1",
                      "model_span_m": [round(hi.x - lo.x, 3), round(hi.y - lo.y, 3)]},
        "content_row": {"class": "Elite", "biome": "cinder_wastes", "behavior": "Caster(range: 13.0, windup: 1.2, "
                        "width: 1.2, length: 14.0, damage: 36.0, cooldown: 3.8, keep_distance: 9.0)",
                        "color": "#FF4D6D", "shape": "Spire", "scale": 1.1},
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage", "emissive_texels")},
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    review_paths = {}
    if not C.flag(argv, "--no-review"):
        rwork = C.ensure_dir(os.path.join(pack, "work", "review"))
        textures = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        notes = [
            "%s tris (elite budget 4000-8000) | textures %s | height %.2f m = %.2f x the 2.2 m hero | %d bones" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"],
                rep["height_vs_hero"], len(arm.data.bones)),
            "Clips: %s" % ", ".join(c.replace(KEY + "_", "") for c in rep["clips"]),
            "Sockets: %s. Faces glTF +Z; the engine turns it with yaw(angle) * rot_y(PI)." % ", ".join(sorted(rep["sockets"])),
            "Status: %s (the user gives the final visual approval)." % SPEC.STATUS_AI_FINAL,
        ]
        req = [RD.clip_name(KEY, c) for c in clip_defs()]
        review_paths.update(R.review_enemy(
            KEY, arm, mesh, reports, rwork, "Molten Hexer  (molten_hexer)",
            "Elite | The Unmade | Cinder Wastes | Caster: channels molten beams across the arena | verb: THE BEAM "
            "(the floating crucible and its crown of molten runes)", clips=req, swatches=PALETTE, notes=notes,
            textures=textures, strip_frames=4))
        review_paths["clips"] = clip_sheet(arm, mesh, reports, rwork, clips_rep)
        lineup, top = size_lineup(mesh, rwork)
        game, sil = game_pose_strip(arm, mesh, rwork)
        RIG.pose_at(arm, RD.clip_name(KEY, "idle@loop"), 0)
        review_paths["hero_shot"] = hero_shot(mesh, os.path.join(reports, "%s_34.png" % KEY))
        RIG.pose_at(arm, RD.clip_name(KEY, "attack"), 9)
        fire = hero_shot(mesh, os.path.join(rwork, "%s_34_fire.png" % KEY), size=640, target=(0.0, -0.6, 1.3),
                         scale=3.6)
        RIG.unmute_none(arm)
        roster = roster_shot(mesh, arm, rwork)
        layout = {
            "title": "Molten Hexer - scale and game read",
            "subtitle": "front orthographic lineup with the 2.2 m hero mannequin (grey bar 2.2 m, orange bar %.2f m); "
                        "below, the in-game camera (55 deg, view height 22 m = 1080 px, 49.1 px/m) at TRUE pixel size" % top,
            "width": 1600,
            "sections": [
                {"label": "Size comparison (front, orthographic), the idle stance and the beam firing (3/4 views)",
                 "height": 500,
                 "images": [{"path": lineup, "label": "hero mannequin 2.2 m | molten_hexer %.2f m (%.2f x)" % (top, top / 2.2)},
                            {"path": review_paths["hero_shot"], "label": "3/4 view, idle stance"},
                            {"path": fire, "label": "3/4 view, attack f9: the beam leaves through the upright ring"}]},
                {"label": "In-game camera, 1x true size: idle, channel, beam, sweep, hit, death", "height": None,
                 "images": [{"path": pth, "label": lb} for pth, lb in game]},
                {"label": "The same at 3x (nearest) + the idle silhouette at game size (3x)", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[:3]]
                 + [{"path": sil, "label": "silhouette 3x", "scale": 3}]},
                {"label": "", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[3:]]},
                {"label": "Among its biome-mates at 1x and 2x: forge_warden (the other Cinder elite), six clinkers, two "
                          "2.2 m hero mannequins", "height": None,
                 "images": [{"path": roster, "label": "1x"}, {"path": roster, "label": "2x", "scale": 2}]},
            ],
            "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
            "notes": ["The gimmick in the outline is the beam focus: the white-hot crucible over the cowl and its 1.44 m "
                      "crown of molten runes. The windup pulls the ring in and whirls it; the attack swings it upright "
                      "in front of the pour lip."],
        }
        review_paths["scale"] = R.contact_sheet(layout, os.path.join(reports, "%s_scale.png" % KEY), rwork)
    C.write_json(os.path.join(reports, "build_report.json"),
                 {"export": dict({k: v for k, v in rep.items() if k not in ("nodes",)}, file=C.rel(rep["file"])),
                  "paint": paint_rep, "clips": clips_rep,
                  "review": {k: C.rel(v) for k, v in review_paths.items() if isinstance(v, str)}})
    outputs = [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
               C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")),
               C.rel(os.path.join(tex_dir, KEY + "_emissive.png"))]
    outputs += [C.rel(os.path.join(reports, "%s_%s.png" % (KEY, n))) for n in ("review", "clips", "scale", "34",
                                                                                 "review_fix")]
    C.write_pack_status(KIND, KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/molten_hexer.py (model, NPR paint, "
                        "GF_MoltenHexer_v1 rig, 8 clips + 3 aliases, export + validation, review sheets). Art review "
                        "fix (6.5/10): the stacked-cake robe is now three uneven tiers (a short ash cape, one long "
                        "overrobe slumping toward the slag arm, an underskirt wedge) in values that clear the Cinder "
                        "floor, and the glow ramp runs white-hot -> peach -> orange with no forge-gold band; "
                        "before/after in reports/molten_hexer_review_fix.png (enemies/molten_hexer_fix_sheet.py).",
                        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
