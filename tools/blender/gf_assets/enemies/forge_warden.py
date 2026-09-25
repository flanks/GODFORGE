"""Forge Warden (content key `forge_warden`): the E2 "Warden Husk" of the user's enemy pack, built end to end
from code - model, hand-painted NPR textures, dedicated rig, clips, GLB export, validation, review sheets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P tools/blender/gf_assets/enemies/forge_warden.py -- [--preview] [--poses] [--no-review] [--size 1024]

  --preview   geometry only: flat zone colours, turnaround + in-game 1x (seconds, no bakes, no export)
  --poses     geometry + rig + clips, key-frame renders in flat colours (no bakes, no export);
              [--pick] a few key poses, [--game] through the game camera, [--zoom], [--clip <name>], [--size px]
  (default)   the full build: paint, rig, clips, save .blend, export + validate, review sheets, status.json

Content row (content/sheets/enemies.csv): Elite, Cinder Wastes, P0, hp 380, speed 2.2, radius 0.75,
shield 80, Support(range 6.0, shield 60.0, interval 4.0, keep_distance 6.0), colour #D9B45A, greybox
Spire, scale 1.2 - "Wraps nearby Unmade in forge-shields. Kill it first."

Design (docs/art/ENEMIES.md sections 3, 4, 6, 7):
  * verb THE WALL - a hollow god-bronze war-construct, helm 2.54 m, crown tip 2.79 m (1.27 x the 2.2 m
    hero). The plates
    FLOAT over an empty interior: open collar, split belly lames, open-backed greaves and cuisses,
    see-through gaps at the waist and between every arm segment; the dark inside is painted as a
    verdigris-black void lit from within by a cold-gold heart (fx_core);
  * THE silhouette: an oversized broken-halo shield, 1.33 m ring, 1.7 m with its rays (a fragment of a
    god's ring: a gold ring with twelve chunky rays around a bronze dome, a jagged bite torn out of its upper edge,
    two ring shards floating in the gap), carried in front on the left arm; a shattered spear held
    upright in the right hand balances it;
  * the head: a bronze helm crowned with five rays, a cracked porcelain god-mask with no face behind
    it, cold gold leaking from the eye slits; broken runes crawl over the plates (cold-gold decals);
  * palette (Fallen Godworks, gfa_spec.FACTIONS): faded god-bronze, verdigris shadows, cracked porcelain,
    cold gold glow #D4B45A -> #FFF4D0, dead-ember depths #8A3A1E; no player colours, no red-white.

Footprint: radius 0.75 x scale 1.2 = 0.9 m collider; the body + shield span 2.27 x 1.32 m (2.5 x).
Rig GF_ForgeWarden_v1: GF_Hero_v1 core bone names (ART_PIPELINE.md section 5) + pauldron_L/R, core,
mask_L/R, shield, spear; rigid plate skinning. Clips: idle@loop (shield-up guard), move@loop, windup,
attack (shield bash), hit, death (collapse inward, the mask cracks last), cast (support pulse),
shield_up (brace). See art/enemies/forge_warden/README.md.

Adapted from: gf_assets examples/swarm_example.py (pipeline), Ashen Covenant
tools/blender/ac_humanoid_enemy/ac_humanoid_rig.py (landmark-table armature, forward roll convention)
and ac_pose.py (FK pose dictionaries) - adapted here, never modified there.
New shared helpers written for this build: gfa_shell.py (thick hollow shells) and gfa_rig_dedicated.py.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_rig_dedicated as RD  # noqa: E402
import gfa_shell as S  # noqa: E402

KEY, KIND, TIER = "forge_warden", "enemy", "elite"
RIG_NAME = "GF_ForgeWarden_v1"

ZONES = ["bronze", "bronze_dark", "gold", "porcelain", "void", "glow", "shield"]
PREVIEW = {"bronze": "#9C8045", "bronze_dark": "#5A4A2C", "gold": "#C9AD62", "porcelain": "#E9E3D6",
           "void": "#15201D", "glow": "#F4E6B0", "shield": "#8C7443"}

# ---- landmarks (rest pose = the guard stance; metres, faces -Y, +X = the warden's LEFT) --------------------
LM = {
    "root": (0.0, 0.0, 0.0), "root_tip": (0.0, 0.0, 0.25),
    "pelvis": (0.0, 0.03, 1.14), "spine_01": (0.0, 0.03, 1.34), "spine_02": (0.0, 0.035, 1.54),
    "spine_03": (0.0, 0.04, 1.76), "neck": (0.0, 0.04, 2.04), "head": (0.0, 0.0, 2.17), "head_tip": (0.0, 0.0, 2.47),
    "clavicle_L": (0.1, 0.05, 1.97), "shoulder_L": (0.5, 0.07, 1.97),
    "clavicle_R": (-0.1, 0.05, 1.97), "shoulder_R": (-0.5, 0.07, 1.97),
    "elbow_R": (-0.66, 0.1, 1.5), "wrist_R": (-0.7, -0.2, 1.3), "hand_R_tip": (-0.71, -0.33, 1.25),
    "hip_L": (0.2, 0.03, 1.12), "knee_L": (0.3, -0.07, 0.64), "ankle_L": (0.34, 0.04, 0.17),
    "ball_L": (0.36, -0.2, 0.06), "toe_L_tip": (0.37, -0.36, 0.05),
}
for _k in ("hip", "knee", "ankle", "ball"):
    _p = LM[_k + "_L"]
    LM[_k + "_R"] = (-_p[0], _p[1], _p[2])
LM["toe_R_tip"] = (-LM["toe_L_tip"][0], LM["toe_L_tip"][1], LM["toe_L_tip"][2])

# the shield frame: origin = centre of the disc's rim plane, +Z = the face normal (front), +Y = shield up
SHIELD_C = Vector((0.58, -0.5, 1.43))
_n = Vector((math.sin(math.radians(24)), -math.cos(math.radians(24)), 0.0)) * math.cos(math.radians(17))
_n.z = math.sin(math.radians(17))
SHIELD_N = _n.normalized()
SHIELD_R = 0.56          # disc
RING_R = (0.53, 0.665)   # halo ring (inner, outer)
RAY_R = 0.65             # rays start here
BREAK = (28.0, 86.0)     # the bite torn out of the halo (degrees in the shield frame, 0 = shield +X)


def shield_frame():
    z = SHIELD_N
    y = Vector((0, 0, 1)) - z * z.z
    y.normalize()
    x = y.cross(z)
    m = Matrix.Identity(4)
    for r in range(3):
        m[r][0], m[r][1], m[r][2], m[r][3] = x[r], y[r], z[r], SHIELD_C[r]
    return m


SF = shield_frame()
_fore_mid = SHIELD_C - SHIELD_N * 0.16
_fore_dir = Vector((SHIELD_N.y, -SHIELD_N.x, 0.0)).normalized()     # across the body, toward the right
LM["elbow_L"] = tuple(_fore_mid - _fore_dir * 0.22 + Vector((0, 0, -0.01)))
LM["wrist_L"] = tuple(_fore_mid + _fore_dir * 0.2)
LM["hand_L_tip"] = tuple(_fore_mid + _fore_dir * 0.33)
SHIELD_GRIP = _fore_mid + _fore_dir * 0.27        # the fist on the handle

# the spear: upright in the right fist, top leaning out and a little forward
SPEAR_GRIP = (Vector(LM["wrist_R"]) + Vector(LM["hand_R_tip"])) * 0.5
SPEAR_DIR = Vector((-0.07, -0.08, 1.0)).normalized()
SPEAR_BUTT = SPEAR_GRIP - SPEAR_DIR * 1.17
SPEAR_TOP = SPEAR_GRIP + SPEAR_DIR * 0.8          # the snapped end of the shaft
SPEAR_HEAD = SPEAR_TOP + SPEAR_DIR * 0.15         # the head floats this far above the splinters
CORE_POS = Vector((0.0, 0.05, 1.63))              # the cold-gold heart floating in the hollow chest
HEAD_C = Vector(LM["head"])
MASK_C = HEAD_C + Vector((0.0, -0.162, 0.12))     # centre of the porcelain face's base ellipse
MASK_RX, MASK_RY = 0.1, 0.14

# bones: (name, parent, head landmark / point, tail landmark / point)
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
    # props and floating plates (not in GF_Hero_v1)
    ("pauldron_L", "clavicle_L", (0.5, 0.07, 2.02), (0.5, 0.07, 2.22)),
    ("pauldron_R", "clavicle_R", (-0.5, 0.07, 2.02), (-0.5, 0.07, 2.22)),
    ("core", "spine_02", tuple(CORE_POS), tuple(CORE_POS + Vector((0, 0, 0.12)))),
    ("mask_L", "head", tuple(MASK_C + Vector((0.035, -0.03, -0.03))), tuple(MASK_C + Vector((0.035, -0.03, 0.09)))),
    ("mask_R", "head", tuple(MASK_C + Vector((-0.035, -0.03, -0.03))), tuple(MASK_C + Vector((-0.035, -0.03, 0.09)))),
    ("shield", "lowerarm_L", tuple(SHIELD_GRIP), tuple(SHIELD_GRIP + SHIELD_N * 0.2)),
    ("spear", "hand_R", tuple(SPEAR_GRIP), tuple(SPEAR_GRIP + SPEAR_DIR * 0.3)),
]
BONE_NAMES = [b[0] for b in BONES]


def P_(k):
    return Vector(LM[k]) if isinstance(k, str) else Vector(k)


# ---- small geometry helpers ---------------------------------------------------------------------------------

def frame_z(origin, z_dir, x_hint=(1, 0, 0)):
    """4x4 with local +Z along z_dir and +X as close to x_hint as possible."""
    return M.orient(tuple(origin), tuple(z_dir), tuple(x_hint))


def add_shell(a, fn, nu, nv, t, zone, bone, name, inner_zone="void", keep=None, wrap_u=False, shading="auto",
              flip=False):
    outer, inner = S.thick_patch(fn, nu, nv, t, keep=keep, wrap_u=wrap_u, flip=flip, inner=inner_zone is not None)
    a.add(outer, zone, bone=bone, name=name, shading=shading)
    if inner is not None and len(inner.faces):
        a.add(inner, inner_zone, bone=bone, name=name + "_in", shading=shading)
    elif inner is not None:
        inner.free()


def limb_tube(a, p0, p1, r0, r1, zone, bone, name, t=0.025, nu=10, nv=3, theta=(0.0, 360.0), front=(0, -1, 0),
              keep=None, flare=None, inner_zone="void"):
    """A hollow plate tube from p0 to p1 (radius r0 -> r1), optionally open (theta range measured from the
    `front` side: 0 deg = front). flare: extra list of (v, r) profile points."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = p1 - p0
    L = ax.length
    fr = Vector(front) - ax.normalized() * Vector(front).dot(ax.normalized())
    Mx = frame_z(p0, ax, fr)       # local X = front
    prof = [(r0, 0.0), (r1, L)] if flare is None else [(r, v * L) for v, r in flare]
    full = abs(theta[1] - theta[0]) >= 359.9
    fn = S.rev_fn(prof, theta[0], theta[1], matrix=Mx, smooth=4 if flare else 0)
    add_shell(a, fn, nu, nv, t, zone, bone, name, inner_zone=inner_zone, keep=keep, wrap_u=full)


def spike_at(a, base, direction, radius, length, zone, bone, name, flat=0.45, x_hint=(1, 0, 0), sides=4):
    sp = M.spike(radius, length, sides=sides, base_scale=(1.0, flat), rot_offset=0 if sides == 4 else 45)
    M.xform(sp, matrix=frame_z(base, direction, x_hint))
    a.add(sp, zone, bone=bone, name=name, shading="flat")


# ---- the model ----------------------------------------------------------------------------------------------

def build_head(a):
    hc = HEAD_C + Vector((0, 0.02, 0))
    # helm: a deep bronze dome, the face torn open for the mask (the hollow shows around it)
    prof = [(0.16, -0.02), (0.195, 0.06), (0.205, 0.15), (0.195, 0.24), (0.155, 0.31), (0.085, 0.355), (0.0, 0.37)]
    nu, nv = 16, 6

    def face_open(i, j):
        th = -180 + 360 * (i + 0.5) / nu      # u=0 at -180 deg, so the front (-90) sits between i = 3 and 4
        return not (abs(th + 90) < 36 and 1 <= j <= 3) and not (abs(th + 90) < 14 and j == 4)
    fn = S.rev_fn(prof, -180, 180, sy=1.12, matrix=Matrix.Translation(hc), smooth=3)
    add_shell(a, fn, nu, nv, 0.024, "bronze", "head", "helm", keep=face_open, wrap_u=True, shading="smooth")
    # diadem: a gold band hugging the brow, carrying the radiant crown
    fn = S.rev_fn([(0.207, 0.19), (0.2, 0.255)], -90 - 70, -90 + 70, sy=1.12, matrix=Matrix.Translation(hc))
    add_shell(a, fn, 8, 1, 0.022, "gold", "head", "diadem", inner_zone=None, shading="smooth")
    # the crown: five flat rays fanning up from the brow like a dead god's sun crown
    for k, (deg, L, w) in enumerate(((0, 0.24, 0.055), (26, 0.18, 0.046), (-26, 0.18, 0.046), (50, 0.12, 0.04),
                                     (-50, 0.12, 0.04))):
        t = math.radians(deg)
        d = Vector((-math.sin(t) * 1.0, 0.18, math.cos(t))).normalized()
        base = hc + Vector((-math.sin(t) * 0.16, -0.19 + 0.06 * abs(math.sin(t)), 0.22 + 0.03 * math.cos(t)))
        spike_at(a, base, d, w, L, "gold", "head", "crown", flat=0.34, x_hint=(math.cos(t), 0, math.sin(t)))


def mask_fn():
    """Porcelain god-face: a shallow elliptical dome facing -Y, recessed in the helm opening, with a
    brow ridge, a straight nose and faint eye hollows (serene, simple planes)."""
    mc = MASK_C
    # mask frame: X = world +X, Y = world +Z (up), Z = world -Y (out of the face)
    Mf = Matrix(((1, 0, 0, mc.x), (0, 0, -1, mc.y), (0, 1, 0, mc.z), (0, 0, 0, 1)))
    rx, ry, depth = MASK_RX, MASK_RY, 0.052

    def fn(u, v):
        th = 2 * math.pi * u
        s_ = math.sin(v * math.pi / 2)
        x, y = rx * s_ * math.cos(th), ry * s_ * math.sin(th)
        z = depth * math.cos(v * math.pi / 2) ** 0.7
        z += 0.01 * math.exp(-((y - 0.03) / 0.02) ** 2) * math.exp(-(x / 0.075) ** 2)          # brow
        nose = math.exp(-(x / 0.013) ** 2) * max(0.0, min(1.0, (0.03 - y) / 0.02)) * max(0.0, min(1.0, (y + 0.05) / 0.02))
        z += 0.014 * nose
        return Mf @ Vector((x, y, z))
    return fn


def build_mask(a):
    nu, nv = 20, 5
    fn = mask_fn()

    def side(i, j):
        th = 2 * math.pi * (i + 0.5) / nu
        s = math.sin((j + 0.5) / nv * math.pi / 2)
        x = MASK_RX * s * math.cos(th)
        y = MASK_RY * s * math.sin(th)
        cx = 0.012 + 0.018 * math.sin(y * 60.0) + (0.012 if y > 0.06 else 0.0)
        return x > cx
    for bone, want in (("mask_L", True), ("mask_R", False)):
        keep = (lambda i, j, w=want: side(i, j) == w)
        outer, inner = S.thick_patch(fn, nu, nv, 0.02, keep=keep, wrap_u=True, inner=False)
        a.add(outer, "porcelain", bone=bone, name="mask_half", shading="smooth")


def build_torso(a):
    # collar (spine_03): standing gorget ring, open at the front, the head floats inside it
    fn = S.rev_fn([(0.25, 2.0), (0.27, 2.08), (0.255, 2.15)], -90 + 26, 270 - 26, sy=0.92,
                  matrix=Matrix.Translation((0, 0.04, 0)))
    add_shell(a, fn, 14, 1, 0.022, "gold", "spine_03", "collar", inner_zone="void", shading="smooth")
    # cuirass: a thick barrel, torn open at the lower front-right and the back (the hollow shows)
    prof = [(0.33, 1.6), (0.44, 1.67), (0.5, 1.78), (0.505, 1.88), (0.46, 1.97), (0.36, 2.03), (0.25, 2.06)]
    nu, nv = 24, 6
    tears = {   # column centre (deg) -> torn rows: a jagged hole in the back, a bite at the lower front-right
        82.5: (2, 3), 97.5: (1, 2, 3, 4), 112.5: (1, 2),
        -127.5: (0,), -112.5: (0, 1, 2), -97.5: (0, 1),
    }

    def torn(i, j):
        th = round(-180 + 360 * (i + 0.5) / nu, 1)
        return j not in tears.get(th, ())
    fn = S.rev_fn(prof, -180, 180, sy=0.74, matrix=Matrix.Translation((0, 0.04, 0)), smooth=3)
    add_shell(a, fn, nu, nv, 0.035, "bronze", "spine_03", "cuirass", keep=torn, wrap_u=True, shading="smooth")
    # breastplate overlay: a raised pectoral plate with a keel (layered edge), front only
    fn = S.rev_fn([(0.47, 1.72), (0.522, 1.81), (0.52, 1.9), (0.47, 1.975)], -90 - 50, -90 + 50, sy=0.76,
                  matrix=Matrix.Translation((0, 0.04, 0)), smooth=3)
    add_shell(a, fn, 10, 4, 0.025, "bronze", "spine_03", "breastplate", inner_zone=None, shading="smooth",
              keep=S.jagged_keep(10, 4, edges=("v0",), depth=1, seed=4, prob=0.4))
    keel = M.tube([(0, -0.365, 1.74), (0, -0.395, 1.83), (0, -0.39, 1.91), (0, -0.35, 1.975)], 0.02, sides=4)
    a.add(keel, "gold", bone="spine_03", name="keel", shading="flat")
    # belly lames (spine_02 / spine_01): split bands with the front open - the heart shows through
    fn = S.rev_fn([(0.35, 1.47), (0.37, 1.565)], -90 + 34, 270 - 34, sy=0.8, matrix=Matrix.Translation((0, 0.04, 0)))
    add_shell(a, fn, 14, 1, 0.03, "bronze_dark", "spine_02", "lame_a", shading="smooth",
              keep=S.jagged_keep(14, 1, edges=("u0", "u1"), depth=1, seed=2, prob=0.5))
    fn = S.rev_fn([(0.33, 1.365), (0.345, 1.44)], -90 + 48, 270 - 40, sy=0.82, matrix=Matrix.Translation((0, 0.04, 0)))
    add_shell(a, fn, 12, 1, 0.03, "bronze_dark", "spine_01", "lame_b", shading="smooth")
    # belt (pelvis) with a halo-disc buckle
    fn = S.rev_fn([(0.345, 1.25), (0.36, 1.33)], -180, 180, sy=0.84, matrix=Matrix.Translation((0, 0.035, 0)))
    add_shell(a, fn, 16, 1, 0.035, "bronze_dark", "pelvis", "belt", wrap_u=True, shading="smooth")
    buckle = M.cylinder(0.075, 0.04, sides=10, bevel=0.01, axis="Y")
    M.xform(buckle, loc=(0, -0.285, 1.29))
    a.add(buckle, "gold", bone="pelvis", name="buckle", shading="smooth")
    br = M.ring(0.075, 0.1, 0.035, sides=12, axis="Y", angle=300, start_angle=120)
    M.xform(br, loc=(0, -0.285, 1.29))
    a.add(br, "gold", bone="pelvis", name="buckle_ring", shading="smooth")
    # back tasset (pelvis)
    fn = S.rev_fn([(0.37, 1.27), (0.41, 1.1), (0.45, 0.96)], 90 - 42, 90 + 42, sy=0.86,
                  matrix=Matrix.Translation((0, 0.035, 0)), smooth=2)
    add_shell(a, fn, 8, 3, 0.028, "bronze_dark", "pelvis", "tasset_back", shading="smooth", flip=True,
              keep=S.jagged_keep(8, 3, edges=("v1",), depth=1, seed=8))
    # the heart: a cold-gold crystal floating in the hollow (core bone)
    heart = M.ico(0.075, 1, scale=(0.9, 0.9, 1.45))
    M.xform(heart, loc=CORE_POS, rot=(0, 0, 20))
    a.add(heart, "glow", bone="core", name="heart", shading="flat")
    for k in range(3):
        sh = M.spike(0.022, 0.07, sides=3, rot_offset=0)
        ang = math.radians(40 + 120 * k)
        d = Vector((math.cos(ang), math.sin(ang), 0.35 if k % 2 else -0.4)).normalized()
        M.xform(sh, matrix=frame_z(CORE_POS + d * 0.1, d))
        a.add(sh, "glow", bone="core", name="heart_shard", shading="flat")


def build_pauldron(a, sx):
    side = "L" if sx > 0 else "R"
    bone = "pauldron_" + side
    c = Vector((sx * 0.5, 0.07, 1.99))
    axis = Vector((sx * 0.75, 0.0, 1.0)).normalized()
    Mf = frame_z(c, axis, (0, -1, 0))        # local X = forward
    # the dome: a broad, flat, flared shoulder shell with a torn lower rim
    fn = S.cap_fn(0.3, 0.16, -180, 180, sx=1.2, sy=1.0, matrix=Mf)
    add_shell(a, fn, 14, 4, 0.03, "bronze", bone, "pauldron_dome", wrap_u=True, shading="smooth",
              keep=S.jagged_keep(14, 4, edges=("v0",), depth=1, seed=11 if sx > 0 else 12, prob=0.35))
    # rolled gold rim around the dome's base, broken on the outer side
    rim = S.rev_fn([(0.298, -0.02), (0.31, 0.012), (0.3, 0.042)], 70, 70 + 320, sx=1.2, matrix=Mf)
    add_shell(a, rim, 22, 1, 0.022, "gold", bone, "pauldron_rim", inner_zone=None, shading="smooth",
              keep=S.jagged_keep(22, 1, edges=("u0", "u1"), depth=1, seed=51 if sx > 0 else 52))
    # a raised keel ridge over the top, front to back
    ridge = [Mf @ Vector((0.3 * 1.2 * math.sin(math.radians(t)) * 0.97, 0.0, 0.16 * math.cos(math.radians(t)) + 0.012))
             for t in range(-66, 67, 22)]
    a.add(M.tube(ridge, 0.03, sides=3, up=tuple(axis)), "gold", bone=bone, name="pauldron_ridge", shading="flat")
    # two lames below it, stepping out and down on the outer side
    Ml = frame_z(c + Vector((sx * 0.03, 0.0, -0.03)), Vector((sx * 0.3, 0.0, 1.0)).normalized(), (0, -1, 0))
    for k, (r, z0, z1) in enumerate(((0.3, -0.02, -0.115), (0.32, -0.105, -0.2))):
        # theta 0 = local +X = forward; a 300 deg band whose gap faces the neck
        fn2 = S.rev_fn([(r, z0), (r + 0.018, z1)], 0, 300, sx=1.12,
                       matrix=Ml @ Matrix.Rotation(math.radians(-60 if sx > 0 else 120), 4, "Z"))
        add_shell(a, fn2, 12, 1, 0.026, "bronze_dark", bone, "pauldron_lame%d" % k, shading="smooth", flip=True,
                  keep=S.jagged_keep(14, 1, edges=("u0", "u1"), depth=1, seed=20 + k))
    # the haute-piece: a standing flange on the neck side of the dome
    fl = S.grid_fn(0.3, 0.15, bend_x=0.04, matrix=frame_z(c + Vector((-sx * 0.16, 0.0, 0.2)),
                                                          Vector((sx * 1.0, 0, 0.12)), (0, 0, 1)))
    add_shell(a, fl, 6, 2, 0.025, "gold", bone, "flange", inner_zone=None, shading="auto",
              keep=S.jagged_keep(6, 2, edges=("v1",), depth=1, seed=31 if sx > 0 else 32, prob=0.5))


def build_arm(a, sx):
    side = "L" if sx > 0 else "R"
    sh, el, wr, tip = P_("shoulder_" + side), P_("elbow_" + side), P_("wrist_" + side), P_("hand_%s_tip" % side)
    # upper arm: a hollow rerebrace floating below the pauldron
    d = (el - sh).normalized()
    limb_tube(a, sh + d * 0.12, el - d * 0.07, 0.12, 0.105, "bronze", "upperarm_" + side, "rerebrace", nu=8, nv=2,
              t=0.024)
    # couter: a round elbow cop with a spike pointing back
    fd = (wr - el).normalized()
    back = (d - fd).normalized()
    cf = frame_z(el + back * 0.04, back, (0, 0, 1))
    add_shell(a, S.cap_fn(0.11, 0.07, -180, 180, matrix=cf), 8, 2, 0.022, "bronze_dark", "lowerarm_" + side,
              "couter", inner_zone=None, wrap_u=True, shading="smooth")
    spike_at(a, el + back * 0.1, back, 0.03, 0.09, "gold", "lowerarm_" + side, "couter_spike")
    # vambrace: flared forearm shell (the cuff opens wide at the wrist)
    limb_tube(a, el + fd * 0.08, wr + fd * 0.02, 0.1, 0.14, "bronze", "lowerarm_" + side, "vambrace", nu=8, nv=2,
              t=0.024, flare=[(0.0, 0.098), (0.55, 0.11), (1.0, 0.145)])
    # gauntlet: a heavy fist
    hd = (tip - wr).normalized()
    fist = M.box((0.15, 0.17, 0.13), bevel=0.025, segments=1, taper=(0.9, 0.85))
    M.xform(fist, matrix=frame_z(wr + hd * 0.085, hd, (0, 0, 1)))
    a.add(fist, "bronze_dark", bone="hand_" + side, name="gauntlet", shading="flat")
    kn = M.box((0.16, 0.05, 0.06), bevel=0.012)
    M.xform(kn, matrix=frame_z(wr + hd * 0.15, hd, (0, 0, 1)) @ Matrix.Translation((0, 0.04, 0)))
    a.add(kn, "bronze", bone="hand_" + side, name="knuckles", shading="flat")


def build_leg(a, sx):
    side = "L" if sx > 0 else "R"
    hip, kn, an, ball = (P_(k + "_" + side) for k in ("hip", "knee", "ankle", "ball"))
    # front + side tassets hang from the belt but ride the thigh
    for k, (t0, t1) in enumerate(((-90 + 10, -90 + 64), (-90 + 70, -90 + 120)) if sx > 0 else
                                 ((-90 - 64, -90 - 10), (-90 - 120, -90 - 70))):
        fn = S.rev_fn([(0.375, 1.27), (0.42, 1.1), (0.47, 0.95)], t0, t1, sy=0.86,
                      matrix=Matrix.Translation((0, 0.035, 0)), smooth=2)
        add_shell(a, fn, 5, 3, 0.028, "bronze" if k == 0 else "bronze_dark", "thigh_" + side, "tasset%d" % k,
                  shading="smooth", flip=True, keep=S.jagged_keep(5, 3, edges=("v1",), depth=1, seed=40 + k + (5 if sx > 0 else 0)))
    # cuisse: open-backed thigh shell
    d = (kn - hip).normalized()
    limb_tube(a, hip + d * 0.16, kn - d * 0.05, 0.15, 0.13, "bronze_dark", "thigh_" + side, "cuisse", nu=8, nv=2,
              t=0.024, theta=(-120, 120))
    # poleyn: knee cop facing forward with a short ridge spike
    kf = frame_z(kn + Vector((0, -0.07, 0.0)), (0, -1, 0.15), (1, 0, 0))
    add_shell(a, S.cap_fn(0.12, 0.08, -180, 180, sy=1.15, matrix=kf), 8, 2, 0.024, "bronze", "shin_" + side, "poleyn",
              inner_zone=None, wrap_u=True, shading="smooth")
    spike_at(a, kn + Vector((0, -0.14, 0.02)), (0, -1, 0.5), 0.028, 0.07, "gold", "shin_" + side, "poleyn_spike",
             x_hint=(1, 0, 0))
    # greave: open-backed flared shin shell
    d2 = (an - kn).normalized()
    limb_tube(a, kn + d2 * 0.08, an + d2 * 0.01, 0.14, 0.12, "bronze", "shin_" + side, "greave", nu=8, nv=3,
              t=0.026, theta=(-125, 125), flare=[(0.0, 0.15), (0.35, 0.165), (1.0, 0.125)])
    # sabaton: layered wedge boot + pointed toe cap
    fd = Vector((ball.x - an.x, ball.y - an.y, 0)).normalized()
    boot = M.box((0.22, 0.3, 0.15), bevel=0.02, taper=(0.85, 0.7), shear=(0, 0.04))
    M.xform(boot, matrix=frame_z(Vector((an.x + fd.x * 0.07, an.y + fd.y * 0.07, 0.085)), (0, 0, 1), (1, 0, 0)))
    a.add(boot, "bronze_dark", bone="foot_" + side, name="sabaton", shading="flat")
    for k in range(2):
        lm = M.box((0.2 - 0.02 * k, 0.07, 0.035))
        M.xform(lm, loc=(ball.x, ball.y + 0.06 - 0.07 * k, 0.16 - 0.045 * k), rot=(-28, 0, 0))
        a.add(lm, "bronze", bone="foot_" + side, name="sabaton_lame", shading="flat")
    tc = M.spike(0.1, 0.2, sides=4, base_scale=(1.0, 0.55), rot_offset=45)
    M.xform(tc, matrix=frame_z(Vector((ball.x, ball.y + 0.04, 0.055)), (0, -1, 0.05), (1, 0, 0)))
    a.add(tc, "bronze", bone="toe_" + side, name="toe_cap", shading="flat")


def build_spear(a):
    bone = "spear"
    shaft = M.cylinder(0.028, (SPEAR_TOP - SPEAR_BUTT).length, sides=8)
    mid = (SPEAR_TOP + SPEAR_BUTT) * 0.5
    M.xform(shaft, matrix=frame_z(mid, SPEAR_DIR))
    a.add(shaft, "bronze_dark", bone=bone, name="shaft", shading="smooth")
    # splinters where it snapped, and the cold-gold band that still holds the head in place
    for k, (ang, L) in enumerate(((20, 0.09), (150, 0.06), (260, 0.075))):
        t = math.radians(ang)
        off = Vector((math.cos(t), math.sin(t), 0.0)) * 0.012
        spike_at(a, SPEAR_TOP + off - SPEAR_DIR * 0.01, (SPEAR_DIR + off * 6).normalized(), 0.014, L, "bronze_dark", bone,
                 "splinter", flat=0.6)
    gl = M.ring(0.03, 0.042, 0.02, sides=8)
    M.xform(gl, matrix=frame_z(SPEAR_TOP + SPEAR_DIR * 0.1, SPEAR_DIR))
    a.add(gl, "glow", bone=bone, name="spear_bind", shading="flat")
    # ferrule spike at the butt
    spike_at(a, SPEAR_BUTT + SPEAR_DIR * 0.03, -SPEAR_DIR, 0.034, 0.14, "gold", bone, "ferrule", flat=1.0, sides=6)
    # bindings
    for t in (0.18, 1.02, 1.5, 1.84):
        r = M.cylinder(0.038, 0.05, sides=6)
        M.xform(r, matrix=frame_z(SPEAR_BUTT + SPEAR_DIR * t, SPEAR_DIR))
        a.add(r, "gold", bone=bone, name="binding", shading="smooth")
    # socket + wings
    sock = M.cylinder(0.042, 0.16, sides=8, radius_top=0.03, bevel=0.006)
    M.xform(sock, matrix=frame_z(SPEAR_HEAD + SPEAR_DIR * 0.06, SPEAR_DIR))
    a.add(sock, "gold", bone=bone, name="socket", shading="smooth")
    side = Vector((1, 0, 0)) - SPEAR_DIR * SPEAR_DIR.x
    side.normalize()
    for s in (-1, 1):
        spike_at(a, SPEAR_HEAD + SPEAR_DIR * 0.1, (side * s + SPEAR_DIR * 0.35).normalized(), 0.03, 0.13, "gold", bone,
                 "wing", flat=0.35, x_hint=tuple(SPEAR_DIR))
    # the broken leaf blade: bottom half of a broad blade, snapped along a jagged diagonal
    nu, nv = 6, 8
    bw, bh = 0.26, 0.5
    blade_base = SPEAR_HEAD + SPEAR_DIR * 0.14
    face_n = side.cross(SPEAR_DIR).normalized()

    def blade_fn(u, v):
        w = bw * (0.35 + 1.1 * math.sin(math.pi * min(1.0, 0.25 + v * 0.95)) ** 0.8) * (1 - 0.9 * v * v)
        x = (u - 0.5) * w
        return blade_base + side * x + SPEAR_DIR * (v * bh) + face_n * 0.0

    def snapped(i, j):
        brk = 3.4 + 2.6 * (i / (nu - 1)) + (0.8 if i in (2, 4) else 0.0)
        return j < brk
    th = (lambda u, v: 0.028 * (1 - abs(2 * u - 1)) + 0.004)
    outer, inner = S.thick_patch(blade_fn, nu, nv, th, keep=snapped, inner=False)
    M.xform(outer, matrix=Matrix.Translation(face_n * 0.016))
    a.add(outer, "gold", bone=bone, name="blade", shading="flat")


def build_shield(a):
    bone = "shield"
    # the dome face: bronze, a jagged bite torn out under the halo's break
    nu, nv = 24, 4
    b0 = (BREAK[0] + 4) / 360 * nu
    b1 = (BREAK[1] - 4) / 360 * nu
    bite = S.bite_keep(nu, nv, (b0 + b1) / 2, (b1 - b0) / 2 + 0.6, 2.4, seed=5, jag=0.6, from_edge="v0")
    fn = S.cap_fn(SHIELD_R, 0.1, 0, 360, matrix=SF)
    add_shell(a, fn, nu, nv, 0.035, "shield", bone, "shield_face", inner_zone="bronze_dark", keep=bite, wrap_u=True,
              shading="smooth")
    # boss: a gold dome in a ring at the apex
    boss_f = SF @ Matrix.Translation((0, 0, 0.085))
    add_shell(a, S.cap_fn(0.13, 0.07, 0, 360, matrix=boss_f), 10, 2, 0.02, "gold", bone, "boss", inner_zone=None,
              wrap_u=True, shading="smooth")
    # inner halo: a raised gold ring riding the dome, broken where the bite is
    def dome_z(r):
        return 0.1 * math.cos(math.asin(min(1.0, r / SHIELD_R))) + 0.01
    fn = S.rev_fn([(0.3, dome_z(0.3)), (0.36, dome_z(0.36))], BREAK[1] + 6, BREAK[0] + 354, matrix=SF)
    add_shell(a, fn, 22, 1, 0.022, "gold", bone, "inner_halo", inner_zone=None, shading="smooth",
              keep=S.jagged_keep(22, 1, edges=("u0", "u1"), depth=1, seed=3))
    # the halo ring (a god's ring fragment): thick gold annulus with the break, jagged ends
    span0, span1 = BREAK[1], BREAK[0] + 360
    rn = 40
    ring_fn = (lambda u, v: SF @ Vector(((RING_R[0] + (RING_R[1] - RING_R[0]) * v) * math.cos(math.radians(span0 + (span1 - span0) * u)),
                                         (RING_R[0] + (RING_R[1] - RING_R[0]) * v) * math.sin(math.radians(span0 + (span1 - span0) * u)),
                                         -0.055)))
    keep = S.jagged_keep(rn, 2, edges=("u0", "u1"), depth=2, seed=9, prob=0.6)
    outer, _ = S.thick_patch(ring_fn, rn, 2, 0.11, keep=keep, inner=False)
    a.add(outer, "gold", bone=bone, name="halo_ring", shading="auto")
    # rays: twelve chunky rays, alternating long / short, none in the break
    for k in range(12):
        ang = 15 + 30 * k
        if BREAK[0] - 8 < ang < BREAK[1] + 8:
            continue
        th = math.radians(ang)
        radial = SF.to_3x3() @ Vector((math.cos(th), math.sin(th), 0))
        tang = SF.to_3x3() @ Vector((-math.sin(th), math.cos(th), 0))
        base = SF @ Vector((RAY_R * math.cos(th), RAY_R * math.sin(th), 0.0))
        long_ray = k % 2 == 0
        sp = M.spike(0.085 if long_ray else 0.06, 0.2 if long_ray else 0.11, sides=4, base_scale=(1.0, 0.36), rot_offset=0)
        M.xform(sp, matrix=frame_z(base, radial, tang))
        a.add(sp, "gold", bone=bone, name="ray", shading="flat")
    # two shards of the ring floating in the break
    for k, (ang, dr, tilt) in enumerate(((BREAK[0] + 9, 0.05, 12.0), (BREAK[0] + 32, 0.1, -16.0))):
        th0 = ang
        rot = Matrix.Rotation(math.radians(tilt), 4, Vector((math.cos(math.radians(th0)), math.sin(math.radians(th0)), 0)))
        sfn = (lambda u, v, th0=th0, dr=dr, rot=rot: SF @ rot @ Vector(
            ((RING_R[0] + dr + 0.12 * v) * math.cos(math.radians(th0 + 17 * u)),
             (RING_R[0] + dr + 0.12 * v) * math.sin(math.radians(th0 + 17 * u)), -0.03 + 0.02 * k)))
        outer, _ = S.thick_patch(sfn, 3, 1, 0.06, inner=False)
        a.add(outer, "gold", bone=bone, name="ring_shard", shading="flat")
    # back: handle + two braces
    for off in (-0.18, 0.18):
        br = M.box((0.9, 0.06, 0.03), bevel=0.008)
        M.xform(br, matrix=SF @ Matrix.Translation((0, off, -0.06)))
        a.add(br, "bronze_dark", bone=bone, name="brace", shading="flat")
    hb = M.box((0.36, 0.05, 0.05), bevel=0.01)
    M.xform(hb, matrix=SF @ Matrix.Translation((0, 0, -0.1)))
    a.add(hb, "bronze_dark", bone=bone, name="handle", shading="flat")


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_NAMES)
    build_head(a)
    build_mask(a)
    build_torso(a)
    for sx in (1, -1):
        build_pauldron(a, sx)
        build_arm(a, sx)
        build_leg(a, sx)
    build_spear(a)
    build_shield(a)
    report = {}
    for p in a.parts:
        k = p["name"].split("_in")[0]
        report[k] = report.get(k, 0) + p["faces"]
    obj = a.to_object(col)
    obj["gfa_part_names"] = ",".join(p["name"] for p in a.parts)
    C.log("faces per part: " + ", ".join("%s %d" % kv for kv in sorted(report.items(), key=lambda kv: -kv[1])))
    C.log("mesh: %d parts, %d tris" % (len(a.parts), a_tris(obj)))
    return obj, a.parts


def a_tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ---- rig ------------------------------------------------------------------------------------------------------

def build_rig(col):
    table = [(n, par, tuple(P_(h)), tuple(P_(t))) for n, par, h, t in BONES]
    arm = RD.build_armature(RIG_NAME, table, col)
    probs = RD.validate_core(arm)
    if probs:
        raise RuntimeError("rig problems: %s" % probs)
    return arm


def add_sockets(arm):
    """ENEMIES.md section 5 socket names (hit_center required) + the Support VFX anchor on the shield."""
    import gfa_rig as RIG
    socks = {
        "hit_center": ("spine_03", (0.0, 0.0, 1.72)),
        "fx_core": ("core", tuple(CORE_POS)),
        "head_top": ("head", tuple(HEAD_C + Vector((0, 0.02, 0.62)))),
        "shield": ("shield", tuple(SF @ Vector((0, 0, 0.12)))),
        "attack_origin": ("shield", tuple(SF @ Vector((0, -0.1, 0.22)))),
    }
    out = {}
    for name, (bone, pos) in socks.items():
        out[name] = RIG.add_socket(arm, bone, name, pos, size=0.06)
    return out


class Solver:
    """Poses GF_ForgeWarden_v1 from a parameter dict (see POSE PARAMETERS below) in armature space:
    FK for the spine / head / floating plates, two-bone IK that plants the feet, and the PROPS DRIVING THE
    ARMS: the shield (strapped to the left forearm) and the spear (in the right fist) are placed first,
    relative to the chest (space 0) or the ground (space 1, blended), and the forearm + fist follow them
    rigidly while the upper arm aims at the elbow.

    POSE PARAMETERS (degrees, metres):
      body:            loc (dx, dy, dz) WORLD offset of the pelvis; rot (x bend fwd, y twist left, z roll)
      spine_01..03, neck, head, clavicle_*, pauldron_*, core, mask_*, toe_*:  rot / loc / scale, bone-local
      foot_L / foot_R: off (dx, dy, dz) world offset of the ankle target; pitch (toes up +)
      knee_L / knee_R: hint (x, y, z) added to the default knee direction (+-0.3, -1, 0)
      shield:          loc / rot in the shield's rest frame (X across to the warden's right, Y = the face
                       normal, Z = up), pivot = the handle; space 0 = rides the chest, 1 = the ground
      spear:           loc / rot in the spear's rest frame (X = left, Y = up the shaft, Z = forward), pivot
                       = the fist; space as above
    """

    FK = ("spine_01", "spine_02", "spine_03", "neck", "head", "clavicle_L", "clavicle_R", "pauldron_L",
          "pauldron_R", "core", "mask_L", "mask_R", "toe_L", "toe_R")

    def __init__(self, arm):
        self.arm = arm
        self.R = {b.name: b.matrix_local.copy() for b in arm.data.bones}

    def _fk(self, bone, tr):
        pb = self.arm.pose.bones[bone]
        if "rot" in tr:
            pb.rotation_euler = RD.euler_deg(tr["rot"])
        if "loc" in tr:
            pb.location = Vector(tr["loc"])
        if "scale" in tr:
            s = tr["scale"]
            pb.scale = (s, s, s) if isinstance(s, (int, float)) else tuple(s)

    def _prop_world(self, prop, follow, tr):
        """World (armature-space) matrix of a prop bone: rest relation to `follow`, blended with the ground
        by tr['space'], then the local delta (pivot = the prop bone's head)."""
        arm, R = self.arm, self.R
        rest_p = R[prop]
        f_now = arm.pose.bones[follow].matrix
        chest = f_now @ R[follow].inverted() @ rest_p
        ground = arm.pose.bones["root"].matrix @ R["root"].inverted() @ rest_p
        w = float(tr.get("space", 0.0))
        if w <= 0:
            base = chest
        elif w >= 1:
            base = ground
        else:
            q = chest.to_quaternion().slerp(ground.to_quaternion(), w)
            base = q.to_matrix().to_4x4()
            base.translation = chest.translation.lerp(ground.translation, w)
        D = Matrix.Translation(Vector(tr.get("loc", (0, 0, 0)))) @ RD.euler_deg(tr.get("rot", (0, 0, 0))).to_matrix().to_4x4()
        return base @ D

    def _arm_follow(self, side, prop, W_prop):
        arm, R = self.arm, self.R
        lower, hand, upper = "lowerarm_" + side, "hand_" + side, "upperarm_" + side
        W_lower = W_prop @ R[prop].inverted() @ R[lower]
        W_hand = W_prop @ R[prop].inverted() @ R[hand]
        RD.aim_bone(arm, upper, W_lower.translation)
        RD.set_matrix(arm, lower, W_lower)
        RD.set_matrix(arm, hand, W_hand)
        RD.set_matrix(arm, prop, W_prop)

    def pose(self, p):
        arm = self.arm
        RD.reset(arm)
        body = p.get("body", {})
        pv = arm.pose.bones["pelvis"]
        d = Vector(body.get("loc", (0, 0, 0)))
        pv.location = (d.x, d.z, -d.y)             # pelvis local axes: X = left, Y = up, Z = forward
        pv.rotation_euler = RD.euler_deg(body.get("rot", (0, 0, 0)))
        for b in self.FK:
            if b in p:
                self._fk(b, p[b])
        RD.update()
        # legs: plant the ankles (rest + offset), keep the sabatons flat (+ pitch)
        for side, sx in (("L", 1), ("R", -1)):
            ft = p.get("foot_" + side, {})
            target = Vector(LM["ankle_" + side]) + Vector(ft.get("off", (0, 0, 0)))
            hint = Vector((sx * 0.3, -1.0, 0.0)) + Vector(p.get("knee_" + side, {}).get("hint", (0.0, 0.0, 0.0)))
            RD.two_bone_ik(arm, "thigh_" + side, "shin_" + side, target, hint)
            head = RD.rest_frame_now(arm, "foot_" + side).translation
            rot = self.R["foot_" + side].to_3x3() @ RD.euler_deg((ft.get("pitch", 0.0), 0, ft.get("roll", 0.0))).to_matrix()
            m = rot.to_4x4()
            m.translation = head
            RD.set_matrix(arm, "foot_" + side, m)
            if "toe_" + side in p:
                self._fk("toe_" + side, p["toe_" + side])
        # props drive the arms
        self._arm_follow("L", "shield", self._prop_world("shield", "spine_03", p.get("shield", {})))
        self._arm_follow("R", "spear", self._prop_world("spear", "spine_03", p.get("spear", {})))
        RD.update()


# ---- clips ------------------------------------------------------------------------------------------------------
# All poses start from GUARD (the idle's rest line). Degrees; see Solver for the parameter meanings.

GUARD = {"body": {"loc": (0.0, 0.0, -0.04)}, "spine_02": {"rot": (4.0, 0, 0)}, "spine_03": {"rot": (3.0, 0, 0)},
         "neck": {"rot": (-4.0, 0, 0)}, "head": {"rot": (-11.0, 0, 0)}}


def P2(*poses):
    return RD.merge(*poses)


def idle_pose(t):
    w = 2 * math.pi * t
    s, c = math.sin(w), math.cos(w)
    return P2(GUARD, {
        "body": {"loc": (0.006 * s, 0.0, -0.04 + 0.014 * s)},
        "spine_02": {"rot": (4.0 + 1.6 * s, 0.0, 0.0)},
        "spine_03": {"rot": (3.0 + 1.8 * math.sin(w + 0.5), 1.2 * c, 0.0)},
        "neck": {"rot": (-4.0 - 1.0 * s, 0.0, 0.0)},
        "head": {"rot": (-11.0 + 2.5 * math.sin(w + 1.1), 5.0 * math.sin(w + 0.3), 1.5 * c)},
        "pauldron_L": {"loc": (0.0, 0.014 * math.sin(w + 0.9), 0.0), "rot": (1.5 * math.sin(w + 0.9), 0, 2.0 * c)},
        "pauldron_R": {"loc": (0.0, 0.014 * math.sin(w + 2.6), 0.0), "rot": (1.5 * math.sin(w + 2.6), 0, -2.0 * c)},
        "core": {"loc": (0.0, 0.025 * math.sin(2 * w), 0.0), "rot": (0.0, 360.0 * t, 0.0),
                 "scale": 1.0 + 0.08 * math.sin(2 * w + 0.5)},
        "shield": {"loc": (0.0, 0.01 * math.sin(w + 0.4), 0.012 * math.sin(w + 0.4)), "rot": (1.5 * math.sin(w + 0.4), 0, 0)},
        "spear": {"rot": (1.5 * math.sin(w + 1.8), 0.0, 1.0 * c)},
    })


MOVE_FRAMES = 24          # 0.8 s gait cycle
MOVE_STRIDE = 0.44        # ankle travel either side of the rest line (m)
MOVE_STANCE = 0.56        # fraction of the cycle a foot is planted
MOVE_CYCLE_M = 2 * MOVE_STRIDE / MOVE_STANCE   # ground covered per cycle (client: playback = speed / this)


def _foot_track(t):
    """Ankle offset (dy, dz) and pitch for a foot whose contact is at t = 0 (planted until MOVE_STANCE)."""
    t %= 1.0
    if t < MOVE_STANCE:
        s = t / MOVE_STANCE
        return (-MOVE_STRIDE + 2 * MOVE_STRIDE * s, 0.0, -6.0 * max(0.0, (s - 0.75) / 0.25))
    s = (t - MOVE_STANCE) / (1 - MOVE_STANCE)
    e = s * s * (3 - 2 * s)
    return (MOVE_STRIDE - 2 * MOVE_STRIDE * e, 0.2 * math.sin(math.pi * s) ** 1.2, 14.0 * math.sin(math.pi * s * 0.9))


def move_pose(t):
    w = 2 * math.pi * t
    yl, zl, pl = _foot_track(t)
    yr, zr, pr = _foot_track(t + 0.5)
    bob = -0.085 + 0.045 * (1 - math.cos(2 * w)) / 2          # lowest at each contact (t = 0, 0.5)
    return P2(GUARD, {
        "body": {"loc": (0.035 * math.sin(w), 0.0, bob), "rot": (0.0, -4.0 * math.sin(w), 3.0 * math.sin(w))},
        "spine_01": {"rot": (7.0, 3.0 * math.sin(w), 0.0)},
        "spine_02": {"rot": (6.0 + 1.5 * math.cos(2 * w), 3.0 * math.sin(w), -2.0 * math.sin(w))},
        "spine_03": {"rot": (4.0, 2.0 * math.sin(w), -1.5 * math.sin(w))},
        "neck": {"rot": (-5.0, -2.0 * math.sin(w), 0.0)},
        "head": {"rot": (-8.0 - 2.0 * math.cos(2 * w), -2.0 * math.sin(w), -2.0 * math.sin(w))},
        "pauldron_L": {"loc": (0.0, 0.02 * math.sin(2 * w - 1.2), 0.0), "rot": (3.0 * math.sin(2 * w - 1.2), 0, 0)},
        "pauldron_R": {"loc": (0.0, 0.02 * math.sin(2 * w - 1.6), 0.0), "rot": (3.0 * math.sin(2 * w - 1.6), 0, 0)},
        "core": {"loc": (0.0, 0.02 * math.sin(2 * w - 1.8), 0.0), "rot": (0.0, 360.0 * t, 0.0)},
        "foot_L": {"off": (0.0, yl, zl), "pitch": pl},
        "foot_R": {"off": (0.0, yr, zr), "pitch": pr},
        "shield": {"loc": (0.0, 0.0, 0.02 * math.sin(2 * w + 0.8)), "rot": (2.0 * math.sin(2 * w + 0.8), 0.0, 2.0 * math.sin(w))},
        "spear": {"rot": (-7.0 * math.sin(w), 0.0, 2.0 * math.sin(w)), "loc": (0.0, 0.015 * math.sin(2 * w), 0.0)},
    })


# the key poses (merged over GUARD)
WINDUP_LOADED = {
    "body": {"loc": (-0.03, 0.09, -0.15), "rot": (0.0, 8.0, -2.0)},
    "spine_01": {"rot": (-4.0, 4.0, 0.0)}, "spine_02": {"rot": (-6.0, 5.0, 0.0)}, "spine_03": {"rot": (-6.0, 6.0, 3.0)},
    "neck": {"rot": (4.0, -6.0, 0.0)}, "head": {"rot": (2.0, -8.0, 0.0)},
    "pauldron_L": {"loc": (0.0, 0.03, 0.0)}, "pauldron_R": {"loc": (0.0, -0.01, 0.0)},
    "shield": {"loc": (-0.2, -0.22, 0.58), "rot": (-12.0, 0.0, -10.0)},
    "spear": {"loc": (0.0, 0.0, 0.1), "rot": (-10.0, 0.0, -6.0)},
    "core": {"scale": 1.25},
}
BASH_IMPACT = {
    "body": {"loc": (0.02, -0.3, -0.16), "rot": (0.0, -10.0, 2.0)},
    "spine_01": {"rot": (10.0, -4.0, 0.0)}, "spine_02": {"rot": (10.0, -5.0, 0.0)}, "spine_03": {"rot": (8.0, -6.0, -2.0)},
    "neck": {"rot": (-8.0, 5.0, 0.0)}, "head": {"rot": (-10.0, 6.0, 0.0)},
    "pauldron_L": {"loc": (0.0, -0.02, 0.02)}, "pauldron_R": {"loc": (0.0, 0.01, -0.02)},
    "shield": {"loc": (0.05, 0.18, 0.1), "rot": (24.0, 0.0, 4.0)},
    "spear": {"loc": (0.0, 0.0, -0.05), "rot": (-26.0, 0.0, 8.0)},
    "knee_L": {"hint": (0.12, 0.0, 0.0)},
    "core": {"scale": 1.3},
}
FLINCH = {
    "body": {"loc": (0.02, 0.07, -0.02), "rot": (0.0, 5.0, -3.0)},
    "spine_02": {"rot": (-7.0, 3.0, 0.0)}, "spine_03": {"rot": (-8.0, 4.0, 4.0)},
    "neck": {"rot": (-8.0, 0.0, 0.0)}, "head": {"rot": (-16.0, 8.0, -6.0)},
    "pauldron_L": {"loc": (0.02, 0.03, 0.02), "rot": (0, 0, 8.0)}, "pauldron_R": {"loc": (-0.02, 0.03, 0.02), "rot": (0, 0, -8.0)},
    "shield": {"loc": (-0.05, -0.06, 0.08), "rot": (-10.0, 0.0, -8.0)},
    "spear": {"rot": (-8.0, 0.0, -5.0)},
    "mask_L": {"loc": (0.004, 0.0, 0.004)}, "mask_R": {"loc": (-0.004, 0.0, 0.004)},
}
CAST_GATHER = {
    "body": {"loc": (0.0, 0.03, -0.1)},
    "spine_02": {"rot": (-3.0, 0, 0)}, "spine_03": {"rot": (-6.0, 0, 0)}, "neck": {"rot": (-6.0, 0, 0)},
    "head": {"rot": (-14.0, 0, 0)},
    "shield": {"loc": (0.14, -0.2, 0.3), "rot": (-30.0, 0.0, 0.0)},
    "spear": {"loc": (0.0, 0.3, 0.0), "rot": (0.0, 0.0, -3.0)},
    "pauldron_L": {"loc": (0.0, 0.03, 0.0)}, "pauldron_R": {"loc": (0.0, 0.03, 0.0)},
    "core": {"scale": 1.35},
}
CAST_PULSE = {
    "body": {"loc": (0.0, 0.0, -0.13)},
    "spine_01": {"rot": (-3.0, 0, 0)}, "spine_02": {"rot": (-5.0, 0, 0)}, "spine_03": {"rot": (-9.0, 0, 0)},
    "neck": {"rot": (-8.0, 0, 0)}, "head": {"rot": (-20.0, 0, 0)},
    "shield": {"loc": (0.3, -0.42, 0.98), "rot": (74.0, 0.0, 0.0)},
    "spear": {"loc": (0.0, -0.1, 0.0), "rot": (2.0, 0.0, -2.0)},
    "pauldron_L": {"loc": (0.0, 0.05, 0.0), "rot": (0, 0, 6.0)}, "pauldron_R": {"loc": (0.0, 0.05, 0.0), "rot": (0, 0, -6.0)},
    "clavicle_L": {"rot": (0.0, 0.0, -6.0)},
    "core": {"scale": 1.6},
}
BRACE = {
    "body": {"loc": (0.0, 0.04, -0.13)},
    "spine_01": {"rot": (6.0, 0, 0)}, "spine_02": {"rot": (8.0, 0, 0)}, "spine_03": {"rot": (6.0, 3.0, 0)},
    "neck": {"rot": (4.0, 0, 0)}, "head": {"rot": (6.0, -4.0, 0)},
    "shield": {"loc": (0.1, 0.06, 0.2), "rot": (4.0, 0.0, 6.0)},
    "spear": {"loc": (0.0, -0.05, 0.0), "rot": (-6.0, 0.0, -4.0)},
    "pauldron_L": {"loc": (0.0, -0.02, 0.03)}, "pauldron_R": {"loc": (0.0, -0.02, 0.03)},
    "knee_L": {"hint": (0.2, 0.0, 0.0)}, "knee_R": {"hint": (-0.2, 0.0, 0.0)},
}
# death: the binding fails - plates drop and fold inward, the shield topples flat, the spear clatters down,
# the heart goes out, and last of all the porcelain mask cracks apart
DEATH_JOLT = P2(FLINCH, {"body": {"loc": (0.0, 0.08, 0.0)}, "head": {"rot": (-24.0, 10.0, -8.0)}})
DEATH_SAG = {
    "body": {"loc": (0.0, 0.02, -0.26), "rot": (6.0, 4.0, 3.0)},
    "spine_01": {"rot": (8.0, 0, 0)}, "spine_02": {"rot": (10.0, 0, 2.0)}, "spine_03": {"rot": (10.0, 0, 3.0)},
    "neck": {"rot": (12.0, 0, 0)}, "head": {"rot": (22.0, 6.0, 6.0)},
    "knee_L": {"hint": (0.5, 0.0, 0.0)}, "knee_R": {"hint": (-0.5, 0.0, 0.0)},
    "shield": {"loc": (0.0, 0.05, -0.3), "rot": (22.0, 0.0, -6.0), "space": 0.6},
    "spear": {"rot": (0.0, 0.0, -22.0), "loc": (0.0, -0.1, 0.0), "space": 0.7},
    "pauldron_L": {"loc": (-0.03, -0.04, 0.0)}, "pauldron_R": {"loc": (0.03, -0.04, 0.0)},
    "core": {"scale": 0.8},
}
DEATH_HEAP = {
    "body": {"loc": (0.0, -0.04, -0.66), "rot": (8.0, 4.0, 4.0)},
    "spine_01": {"rot": (8.0, 0, 3.0), "loc": (0.0, -0.05, 0.0)},
    "spine_02": {"rot": (8.0, 0, 3.0), "loc": (0.0, -0.06, 0.0)},
    "spine_03": {"rot": (6.0, 0, 4.0), "loc": (0.0, -0.06, 0.0)},
    "neck": {"rot": (-10.0, 0, 0), "loc": (0.0, -0.12, 0.0)}, "head": {"rot": (-26.0, 12.0, 22.0)},
    "knee_L": {"hint": (0.7, 0.3, 0.0)}, "knee_R": {"hint": (-0.7, 0.3, 0.0)},
    "foot_L": {"roll": -10.0}, "foot_R": {"roll": 10.0},
    "shield": {"loc": (0.06, -0.2, -1.3), "rot": (84.0, 0.0, -10.0), "space": 1.0},
    "spear": {"rot": (0.0, 18.0, -78.0), "loc": (0.0, -0.95, 0.0), "space": 1.0},
    "pauldron_L": {"loc": (-0.08, -0.14, 0.02), "rot": (0, 0, -14.0)},
    "pauldron_R": {"loc": (0.08, -0.14, 0.02), "rot": (0, 0, 14.0)},
    "clavicle_L": {"rot": (0, 0, -10.0)}, "clavicle_R": {"rot": (0, 0, 10.0)},
    "core": {"scale": 0.5},
}


def clip_defs():
    """{clip: (frames, pose(frame) -> params)}"""
    g0 = idle_pose(0.0)
    K = RD.Keys
    windup = K([(0, g0), (5, P2(GUARD, WINDUP_LOADED, {"body": {"loc": (-0.02, 0.05, -0.1)}}), "ease"),
                (13, P2(GUARD, WINDUP_LOADED), "ease"),
                (18, P2(GUARD, WINDUP_LOADED, {"shield": {"loc": (-0.21, -0.24, 0.62), "rot": (-14.0, 0.0, -11.0)}}), "ease")])
    attack = K([(0, P2(GUARD, WINDUP_LOADED, {"shield": {"loc": (-0.21, -0.24, 0.62), "rot": (-14.0, 0.0, -11.0)}})),
                (4, P2(GUARD, BASH_IMPACT), "in"),
                (9, P2(GUARD, BASH_IMPACT, {"body": {"loc": (0.02, -0.26, -0.15)}, "shield": {"loc": (0.05, 0.14, 0.08)}}), "out"),
                (21, g0, "ease")])
    hit = K([(0, g0), (3, P2(GUARD, FLINCH), "out"), (10, g0, "ease")])
    death = K([(0, g0), (4, P2(GUARD, DEATH_JOLT), "out"), (15, P2(GUARD, DEATH_SAG), "ease"),
               (27, P2(GUARD, DEATH_HEAP), "in"),
               (32, P2(GUARD, DEATH_HEAP, {"body": {"loc": (0.0, -0.06, -0.62)}, "shield": {"rot": (80.0, 0.0, -10.0)},
                                           "spear": {"rot": (0.0, 18.0, -74.0)}}), "out"),
               (38, P2(GUARD, DEATH_HEAP), "ease"),
               (46, P2(GUARD, DEATH_HEAP, {"core": {"scale": 0.0}}), "ease"),
               (50, P2(GUARD, DEATH_HEAP, {"core": {"scale": 0.0}, "mask_L": {"loc": (0.006, 0.0, 0.004), "rot": (0, 0, -4)},
                                           "mask_R": {"loc": (-0.006, 0.0, 0.004), "rot": (0, 0, 4)}}), "snap"),
               (58, P2(GUARD, DEATH_HEAP, {"core": {"scale": 0.0},
                                           "mask_L": {"loc": (0.045, -0.06, 0.03), "rot": (-20, 10, -28)},
                                           "mask_R": {"loc": (-0.04, -0.07, 0.025), "rot": (-24, -8, 24)}}), "in"),
               (66, P2(GUARD, DEATH_HEAP, {"core": {"scale": 0.0},
                                           "mask_L": {"loc": (0.05, -0.075, 0.035), "rot": (-22, 10, -30)},
                                           "mask_R": {"loc": (-0.045, -0.085, 0.03), "rot": (-26, -8, 26)}}), "out")])
    cast = K([(0, g0), (10, P2(GUARD, CAST_GATHER), "ease"), (15, P2(GUARD, CAST_PULSE), "in"),
              (26, P2(GUARD, CAST_PULSE, {"body": {"loc": (0.0, 0.0, -0.12)}, "core": {"scale": 1.5}}), "out"),
              (36, g0, "ease")])
    shield_up = K([(0, g0), (8, P2(GUARD, BRACE), "out"), (12, P2(GUARD, BRACE, {"body": {"loc": (0.0, 0.04, -0.12)}}), "ease")])
    return {
        "idle@loop": (60, lambda f: idle_pose(f / 60.0)),
        "move@loop": (MOVE_FRAMES, lambda f: move_pose(f / float(MOVE_FRAMES))),
        "windup": (windup.length, windup.at),
        "attack": (attack.length, attack.at),
        "hit": (hit.length, hit.at),
        "death": (death.length, death.at),
        "cast": (cast.length, cast.at),
        "shield_up": (shield_up.length, shield_up.at),
    }


# the clip names from the task brief -> the shipped names (ENEMIES.md section 5/6 naming)
CLIP_ROLES = {
    "idle@loop": "shield-up guard, breathing; plates hover, the heart spins",
    "move@loop": "walk: heavy planted steps, shield held forward (brief name: walk@loop)",
    "windup": "the shield rises up and back for the bash (anticipation; the engine adds the telegraph)",
    "attack": "shield bash: lunge, the rim drives forward and down (brief name: shield_bash)",
    "hit": "flinch back, the mask rattles",
    "death": "the binding fails: plates drop inward into a heap, shield topples flat, spear falls, the heart "
             "goes out, the mask cracks apart last",
    "cast": "support pulse: spear slams down, the halo shield is raised overhead face-up (brief name: cast_shield)",
    "shield_up": "brace: shield up to the eyes, crouched behind it (held on the last frame)",
}
CLIP_ALIASES = {"walk@loop": "move@loop", "shield_bash": "attack", "cast_shield": "cast"}


def build_clips(arm, mesh):
    sol = Solver(arm)
    names = []
    for clip, (frames, fn) in clip_defs().items():
        RD.bake_clip(arm, KEY, clip, int(frames), lambda a, f, fn=fn: sol.pose(fn(f)), mute_meshes=[mesh])
        names.append(RD.clip_name(KEY, clip))
    return names, sol


# ---- paint (Fallen Godworks, ENEMIES.md section 4) -----------------------------------------------------------------

PALETTE = [  # (name, hex) for the review sheet
    ("god-bronze", "#7E6A3F"), ("bronze light", "#C2A35A"), ("verdigris", "#22382F"), ("dark bronze", "#4F4530"),
    ("shield face", "#5E5436"), ("halo gold", "#CDB066"), ("porcelain", "#D9D3C6"), ("void", "#10201C"), ("dead ember", "#8A3A1E"),
    ("cold gold", "#D4B45A"), ("glow core", "#FFF4D0"),
]
GLOW = {"color": "#8A6A28", "core": "#FFF4D0"}          # decal glow: cold gold rim -> white-gold core


def recipes():
    P = _paint()
    low_dark = {"axis": (0, 0, -1), "range": (-1.2, -0.15), "color": "#2A2A1C", "amount": 0.4}
    return {
        "bronze": P.zone(base="#7E6A3F", shadow="#22382F", light="#C2A35A", planes=0.1, parts=0.08, brush=0.05,
                         brush_freq=3.0, edge=0.9, edge_width=0.016, edge_breakup=0.35, cavity=0.8, cavity_width=0.014,
                         ao=0.7, ao_range=(0.2, 0.55), gradient=low_dark,
                         spots={"color": "#4E7264", "amount": 0.5, "freq": 3.5, "threshold": (0.58, 0.68)}),
        "bronze_dark": P.zone(base="#4F4530", shadow="#0E1A16", light="#8C7A4C", planes=0.08, parts=0.07, brush=0.05,
                              brush_freq=3.0, edge=0.8, edge_width=0.013, edge_breakup=0.4, cavity=0.8, cavity_width=0.012,
                              ao=0.7, ao_range=(0.2, 0.55), gradient=low_dark,
                              spots={"color": "#2E4A40", "amount": 0.5, "freq": 5.0, "threshold": (0.58, 0.68)}),
        "gold": P.zone(base="#CDB066", shadow="#6A5424", light="#F4E6B0", planes=0.08, parts=0.05, brush=0.04,
                       brush_freq=4.0, edge=0.95, edge_width=0.013, edge_breakup=0.3, cavity=0.7, cavity_width=0.01,
                       ao=0.55, ao_range=(0.25, 0.6),
                       spots={"color": "#5E8374", "amount": 0.22, "freq": 6.0, "threshold": (0.64, 0.74)}),
        "porcelain": P.zone(base="#DCD6C9", shadow="#8C877E", light="#F6F2E8", planes=0.035, parts=0.02, brush=0.025,
                            brush_freq=6.0, edge=0.5, edge_width=0.006, cavity=0.45, cavity_width=0.006, ao=0.35,
                            ao_range=(0.3, 0.7)),
        "void": P.zone(base="#10201C", shadow="#07100D", light="#1C302A", planes=0.05, parts=0.0, brush=0.06,
                       brush_freq=4.0, edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#7A6026", "hot": "#3A2410", "color": "#0A0604", "mode": "radial",
                             "center": tuple(CORE_POS), "radius": 0.7, "base_mix": 0.0, "strength": 0.9}),
        "glow": P.zone(base="#F4E6B0", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFF4D0", "hot": "#E8CF7A", "color": "#D4B45A", "mode": "radial",
                             "center": tuple(CORE_POS), "radius": 0.16, "base_mix": 0.4}),
        "shield": P.zone(base="#5E5436", shadow="#1C2C26", light="#968252", planes=0.07, parts=0.05, brush=0.05,
                         brush_freq=2.5, edge=0.9, edge_width=0.016, cavity=0.8, cavity_width=0.014, ao=0.6,
                         ao_range=(0.2, 0.55),
                         gradient={"center": tuple(SHIELD_C + SHIELD_N * 0.1), "range": (0.15, 0.6), "color": "#3E4A34",
                                   "amount": 0.35},
                         spots={"color": "#3E5A4C", "amount": 0.45, "freq": 3.5, "threshold": (0.58, 0.68)}),
    }


def _paint():
    import gfa_paint as P
    return P


def _frame(origin, z_dir, x_dir):
    """4x4 decal frame: +Z = projection direction (out of the surface), +X = the lines' x."""
    z = Vector(z_dir).normalized()
    x = Vector(x_dir) - z * Vector(x_dir).dot(z)
    x.normalize()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def runes_on_arc(rng, radius, a0, a1, count, size, broken=0.4, strokes=3, gap=0.0):
    """Rune glyphs standing on a circle (2D, the circle's plane), tangentially rotated, from a0 to a1 deg."""
    out = []
    for k in range(count):
        a = math.radians(a0 + (a1 - a0) * (k + 0.5) / count)
        if gap and rng.random() < gap:
            continue
        g = M.rune_glyph(rng, size, strokes, broken)
        ca, sa = math.cos(a - math.pi / 2), math.sin(a - math.pi / 2)
        cx, cy = radius * math.cos(a), radius * math.sin(a)
        for ln in g:
            out.append([(cx + p[0] * ca - p[1] * sa, cy + p[0] * sa + p[1] * ca) for p in ln])
    return out


def decals():
    P = _paint()
    rng = random.Random(17)
    out = []
    # --- the shield: broken runes around the halo ring and the face, glowing cracks from the bite
    ring_fr = SF @ Matrix.Translation((0, 0, 0.0))
    lines = runes_on_arc(rng, (RING_R[0] + RING_R[1]) / 2, BREAK[1] + 8, BREAK[0] + 352, 12, 0.085, broken=0.4, gap=0.1)
    out.append(P.decal_lines(lines, ring_fr, 0.017, zones=["gold"], color="#FFF1C4", rim="#4A3A1E", rim_width=0.02,
                             emit=GLOW, depth=(-0.02, 0.1), facing=0.5))
    lines = runes_on_arc(rng, 0.45, BREAK[1] + 14, BREAK[0] + 340, 10, 0.08, broken=0.45, gap=0.15)
    out.append(P.decal_lines(lines, ring_fr, 0.016, zones=["shield"], color="#E9D696", rim="#1E2A22", rim_width=0.02,
                             emit=GLOW, depth=(-0.03, 0.16), facing=0.3))
    mid = math.radians((BREAK[0] + BREAK[1]) / 2)
    start = (0.47 * math.cos(mid), 0.47 * math.sin(mid))
    cr = M.crack_lines(rng, start=start, direction=math.degrees(mid) + 180, length=0.34, step=0.03, jag=0.5,
                       branches=2, branch_len=0.5, depth=2)
    out.append(P.decal_lines(cr, ring_fr, 0.018, zones=["shield"], color="#F4E6B0", rim="#10201C", rim_width=0.04,
                             emit=GLOW, depth=(-0.03, 0.16), facing=0.3))
    # --- the mask: glowing eye slits with tears of light, a dark hairline crack along the split, the mouth
    mf = Matrix(((1, 0, 0, MASK_C.x), (0, 0, -1, MASK_C.y), (0, 1, 0, MASK_C.z), (0, 0, 0, 1)))
    eyes = []
    for sx in (-1, 1):
        eyes.append([(sx * 0.017, 0.015), (sx * 0.043, 0.004), (sx * 0.07, 0.014)])
    out.append(P.decal_lines(eyes, mf, 0.021, zones=["porcelain"], color="#FFF4D0", rim="#3A2A18", rim_width=0.028,
                             emit={"color": "#D4B45A", "core": "#FFF4D0"}, depth=(-0.02, 0.12), facing=0.1))
    tears = [[(sx * 0.048, -0.004), (sx * 0.05, -0.034), (sx * 0.047, -0.064)] for sx in (-1, 1)]
    out.append(P.decal_lines(tears, mf, 0.008, zones=["porcelain"], color="#E8CF7A", rim=None,
                             emit={"color": "#8A6A28", "core": "#D4B45A"}, depth=(-0.02, 0.12), facing=0.1))
    crack = [[(0.012 + 0.018 * math.sin(y * 60.0) + (0.012 if y > 0.06 else 0.0), y)
              for y in [(-0.13 + 0.26 * k / 24) for k in range(25)]]]
    crack += M.crack_lines(random.Random(4), start=(0.025, 0.07), direction=30, length=0.05, step=0.012, branches=0, depth=0)
    out.append(P.decal_lines(crack, mf, 0.005, zones=["porcelain"], color="#4E463E", rim="#B4AEA4", rim_width=0.009,
                             depth=(-0.02, 0.12), facing=0.05))
    out.append(P.decal_lines([[(-0.024, -0.08), (0.0, -0.084), (0.024, -0.08)]], mf, 0.0045, zones=["porcelain"],
                             color="#7A7266", depth=(-0.02, 0.12), facing=0.1))
    # --- broken runes crawling over the plates (cold gold): pauldron tops (the camera sees them), the back,
    # the breastplate, the greaves
    for sx in (1, -1):
        c = Vector((sx * 0.5, 0.07, 1.99))
        axis = Vector((sx * 0.75, 0.0, 1.0)).normalized()
        fr = _frame(c, axis, (0, -1, 0))
        lines = runes_on_arc(rng, 0.2, 200 if sx > 0 else -20, 340 if sx > 0 else 120, 4, 0.09, broken=0.4)
        out.append(P.decal_lines(lines, fr, 0.016, zones=["bronze"], color="#F4E6B0", rim="#2E2616", rim_width=0.022,
                                 emit=GLOW, depth=(0.0, 0.3), facing=0.35))
        cr = M.crack_lines(random.Random(30 + sx), start=(0.0, 0.0), direction=90 + sx * 40, length=0.22, step=0.025,
                           branches=1, depth=1)
        out.append(P.decal_lines(cr, fr, 0.014, zones=["bronze"], color="#E8CF7A", rim="#10201C", rim_width=0.03,
                                 emit=GLOW, depth=(0.0, 0.3), facing=0.35))
    cyl = Matrix.Translation((0.0, 0.04, 0.0))
    band = M.rune_band(rng, count=6, size=0.095, spacing=1.6, broken=0.4, origin=(-0.5 * 0.4, 1.86))
    # cylinder mapping: u = angle * radius, u = 0 on +X; the back of the torso is at +90 deg (u ~ +0.6)
    back = [[(p[0] + 0.5 * math.pi / 2 * 0.74 + 0.02, p[1]) for p in ln] for ln in band]
    out.append(P.decal_lines(back, cyl, 0.016, zones=["bronze"], color="#F4E6B0", rim="#2E2616", rim_width=0.024,
                             emit=GLOW, mapping="cylinder", radius=0.5 * 0.9))
    front = [[(p[0] - 0.5 * math.pi / 2 * 0.74 - 0.35, p[1] - 0.02) for p in ln] for ln in band[:9]]
    out.append(P.decal_lines(front, cyl, 0.016, zones=["bronze"], color="#F4E6B0", rim="#2E2616", rim_width=0.024,
                             emit=GLOW, mapping="cylinder", radius=0.5 * 0.9))
    # cracks leaking light around the torn hole in the back (cylinder mapping; +90 deg = the back)
    for k, (u0, v0, ang) in enumerate(((0.52, 1.72, 200), (0.95, 1.9, -20), (0.8, 1.66, -70), (0.6, 1.95, 110))):
        cr = M.crack_lines(random.Random(60 + k), start=(u0, v0), direction=ang, length=0.2, step=0.025, branches=1,
                           depth=1)
        out.append(P.decal_lines(cr, cyl, 0.014, zones=["bronze"], color="#F4E6B0", rim="#10201C", rim_width=0.03,
                                 emit=GLOW, mapping="cylinder", radius=0.45))
    # chest crack leaking light
    cr = M.crack_lines(random.Random(9), start=(-0.12, 1.94), direction=-70, length=0.3, step=0.025, branches=2, depth=1)
    out.append(P.decal_lines(cr, _frame((0, 0.0, 0.0), (0, -1, 0), (1, 0, 0)), 0.015, zones=["bronze"], color="#F4E6B0",
                             rim="#10201C", rim_width=0.024, emit=GLOW, depth=(0.2, 0.6), facing=0.3))
    for sx in (1, -1):
        kn, an = P_("knee_" + ("L" if sx > 0 else "R")), P_("ankle_" + ("L" if sx > 0 else "R"))
        g = M.rune_glyph(rng, 0.1, 3, 0.4) + M.rune_glyph(rng, 0.08, 2, 0.5)
        g = [[(p[0], p[1] + (0.0 if i < 3 else -0.1)) for p in ln] for i, ln in enumerate(g)]
        fr = _frame(kn.lerp(an, 0.35) + Vector((0, -0.16, 0)), (0, -1, 0), (1, 0, 0))
        out.append(P.decal_lines(g, fr, 0.016, zones=["bronze"], color="#F4E6B0", rim="#2E2616", rim_width=0.03,
                                 emit=GLOW, depth=(-0.06, 0.12), facing=0.4))
    # the spear: the snapped blade still glows along the break
    side = Vector((1, 0, 0)) - SPEAR_DIR * SPEAR_DIR.x
    side.normalize()
    face_n = side.cross(SPEAR_DIR).normalized()
    base = SPEAR_HEAD + SPEAR_DIR * 0.14
    for sgn in (1, -1):
        fr = Matrix(((side.x, SPEAR_DIR.x, face_n.x * sgn, base.x), (side.y, SPEAR_DIR.y, face_n.y * sgn, base.y),
                     (side.z, SPEAR_DIR.z, face_n.z * sgn, base.z), (0, 0, 0, 1)))
        brk = [[(-0.12, 0.29), (-0.04, 0.3), (0.0, 0.44), (0.03, 0.37), (0.07, 0.5), (0.11, 0.44)]]
        out.append(P.decal_lines(brk, fr, 0.014, zones=["gold"], color="#FFF4D0", rim="#5A4A20", rim_width=0.03,
                                 emit=GLOW, depth=(-0.06, 0.08), facing=0.3))
    return out


# ---- review renders ---------------------------------------------------------------------------------------------------

KEY_FRAMES = {   # the key poses of each clip for the clip contact sheet
    "idle@loop": (0, 15, 30, 45), "move@loop": (0, 4, 8, 12, 16, 20), "windup": (0, 5, 13, 18),
    "attack": (0, 2, 4, 9, 15, 21), "hit": (0, 3, 10), "death": (0, 4, 15, 22, 27, 38, 46, 50, 58, 66),
    "cast": (0, 10, 15, 26, 36), "shield_up": (0, 4, 8, 12),
}
GAME_POSES = [("idle@loop", 0, "guard"), ("windup", 18, "windup (loaded)"), ("attack", 4, "bash impact"),
              ("cast", 15, "cast pulse"), ("shield_up", 12, "brace"), ("death", 66, "death (held)")]


def clip_sheet(arm, mesh, reports, work, clips_rep):
    """Contact sheet: every clip's key poses (textured toon preview, 3/4 front, one shared scale)."""
    import gfa_render as R
    import gfa_rig as RIG
    scene = bpy.context.scene
    R.setup_cycles(scene, 10)
    view = Vector((0.75, -1.0, 0.45)).normalized()
    sections = []
    with R.toon_preview([mesh], ink=0.012):
        for clip, frames in KEY_FRAMES.items():
            tr = RD.clip_name(KEY, clip)
            ims = []
            for f in frames:
                RIG.pose_at(arm, tr, f)
                R.aim(scene, Vector((0.05, -0.1, 1.25)), view, 3.7)
                p = R.render(scene, os.path.join(work, "clip_%s_%02d.png" % (clip.replace("@", "_"), f)), 260)
                ims.append({"path": p, "label": "f%d" % f})
            secs = next((c["seconds"] for c in clips_rep if c["name"] == tr), 0)
            sections.append({"label": "%s  (%d frames, %.2f s)  -  %s" % (tr, frames[-1] if not clip.endswith("@loop") else
                                                                           int(round(secs * 30)), secs, CLIP_ROLES[clip]),
                             "height": 196, "images": ims})
    RIG.unmute_none(arm)
    scene.frame_set(0)
    layout = {"title": "Forge Warden - clips (key poses)",
              "subtitle": "GF_ForgeWarden_v1, 30 fps, every frame keyed; loops are periodic. Anticipation: the windup "
                          "lifts the whole halo shield up and back, the engine adds the red-white telegraph decal.",
              "width": 1600, "sections": sections,
              "notes": ["Clip names from the brief map to the contract names: walk@loop -> move@loop, shield_bash -> "
                        "attack, cast_shield -> cast (meta.json clip_aliases)."]}
    return R.contact_sheet(layout, os.path.join(reports, "%s_clips.png" % KEY), work)


def size_lineup(mesh, work):
    """Front orthographic lineup: the 2.2 m hero mannequin next to the warden, with height bars."""
    import gfa_render as R
    import gfa_spec as SPEC
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (-1.75, 0.0, 0.0)
    _lo, hi = C.world_bounds([mesh])
    bars = []
    for h, x0, x1, hexc in ((SPEC.HERO_HEIGHT, -2.35, -1.15, "#7A8494"), (hi.z, -0.8, 1.3, "#D4B45A")):
        me = bpy.data.meshes.new("BAR")
        me.from_pydata([(x0, 0.6, h - 0.008), (x1, 0.6, h - 0.008), (x1, 0.6, h + 0.008), (x0, 0.6, h + 0.008)], [],
                       [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("BAR", me)
        scene.collection.objects.link(ob)
        me.materials.append(R.toon_material("BARM", flat_hex=hexc, rim=0.0))
        bars.append(ob)
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 10)
    flat = {man.name: R.MANNEQUIN}
    with R.toon_preview([mesh, man], ink=0.012, flat=flat):
        R.aim(scene, Vector((-0.45, 0.0, 1.45)), Vector((0.0, -1.0, 0.0)), 3.6)
        scene.render.resolution_x, scene.render.resolution_y = 900, 760
        scene.render.filepath = os.path.join(work, "%s_size_lineup.png" % KEY)
        cam = scene.camera
        cam.data.ortho_scale = 3.9
        bpy.ops.render.render(write_still=True)
    C.remove_objects([man] + bars)
    return scene.render.filepath, round(hi.z, 3)


def game_pose_strip(arm, mesh, work):
    """The in-game camera at TRUE 1080p pixel size (view height 22 m) for the key poses, with the mannequin."""
    import gfa_render as R
    import gfa_rig as RIG
    import gfa_spec as SPEC
    scene = bpy.context.scene
    vh = SPEC.GAME_VIEW_HEIGHTS[0]
    ppm = SPEC.SCREEN_H / vh
    pitch = math.radians(SPEC.GAME_PITCH_DEG)
    d = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
    man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-2.1, 0.4, 0.0)
    floor = bpy.data.meshes.new("GFLOOR")
    floor.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("GFLOOR", floor)
    scene.collection.objects.link(fo)
    floor.materials.append(R.toon_material("GFLOORM", flat_hex=R.FLOOR, rim=0.0))
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 16, bg=R.FLOOR)
    px = 204
    out = []
    with R.toon_preview([mesh, man], ink=0.012, flat={man.name: R.MANNEQUIN}):
        for clip, f, label in GAME_POSES:
            RIG.pose_at(arm, RD.clip_name(KEY, clip), f)
            R.aim(scene, Vector((-0.55, -0.1, 1.0)), d, px / ppm)
            out.append((R.render(scene, os.path.join(work, "game_%s_%02d.png" % (clip.replace("@", "_"), f)), px), label))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    # the silhouette of the guard at game size
    R.setup_workbench_flat(scene)
    fo.hide_render = True
    R.aim(scene, Vector((-0.55, -0.1, 1.0)), d, px / ppm)
    sil = R.render(scene, os.path.join(work, "game_guard_sil.png"), px)
    C.remove_objects([man, fo])
    return out, sil


def hero_shot(mesh, reports):
    """One larger 3/4 beauty render of the rest pose for the README / the user."""
    import gfa_render as R
    scene = bpy.context.scene
    R.setup_cycles(scene, 16)
    with R.toon_preview([mesh], ink=0.011):
        R.aim(scene, Vector((0.12, -0.05, 1.36)), Vector((0.62, -1.0, 0.36)).normalized(), 3.05)
        p = R.render(scene, os.path.join(reports, "%s_34.png" % KEY), 900)
    return p


# ---- quick preview (flat zone colours, no bakes) --------------------------------------------------------------

def preview_materials(mesh):
    import gfa_render as R
    for s in mesh.material_slots:
        z = s.material.name[4:]
        m = R.toon_material("PV_" + z, flat_hex=PREVIEW.get(z, "#FF00FF"), rim=0.3)
        if z == "glow":
            nt = m.node_tree
            em = [n for n in nt.nodes if n.type == "EMISSION"][0]
            em.inputs["Strength"].default_value = 3.0
        s.material = m


def preview(mesh, out_dir, stem="pv", views=None, size=420, ingame=True):
    import gfa_render as R
    scene = bpy.context.scene
    views = views or R.CREATURE_VIEWS
    pts = R._points([mesh])
    ext = max(max(R.frame(pts, d)[1:]) for d in views.values())
    R.setup_cycles(scene, 8)
    R.add_ink_hull(mesh, 0.012)
    paths = []
    for name, d in views.items():
        c, _, _ = R.frame(pts, d)
        R.aim(scene, c, d, ext * 1.1)
        paths.append(R.render(scene, os.path.join(out_dir, "%s_%s.png" % (stem, name)), size))
    if ingame:
        man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
        man.location = (-2.0, 0.3, 0.0)
        man.data.materials.clear()
        man.data.materials.append(R.toon_material("PV_man", flat_hex=R.MANNEQUIN, rim=0.25))
        bpy.context.view_layer.update()
        R.add_ink_hull(man, 0.012)
        vh = 22.0
        ppm = 1080 / vh
        pitch = math.radians(55)
        d = Vector((0.0, -math.cos(pitch), math.sin(pitch)))
        fl = bpy.data.meshes.new("PVFLOOR")
        fl.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
        flo = bpy.data.objects.new("PVFLOOR", fl)
        scene.collection.objects.link(flo)
        fl.materials.append(R.toon_material("PV_floor", flat_hex=R.FLOOR, rim=0.0))
        R.setup_cycles(scene, 8, bg=R.FLOOR)
        px = 200
        R.aim(scene, Vector((-0.9, 0, 1.0)), d, px / ppm)
        paths.append(R.render(scene, os.path.join(out_dir, "%s_ingame.png" % stem), px))
    return paths


POSE_FRAMES = {
    "idle@loop": (0, 15, 30, 45), "move@loop": (0, 3, 6, 9, 12, 15, 18, 21), "windup": (0, 5, 13, 18),
    "attack": (0, 2, 4, 9, 15, 21), "hit": (0, 3, 6, 10), "death": (0, 4, 15, 22, 27, 32, 38, 46, 50, 58, 66),
    "cast": (0, 6, 10, 15, 26, 36), "shield_up": (0, 4, 8, 12),
}


def pose_renders(arm, mesh, out_dir, size=220, view=(0.75, -1.0, 0.45), scale=4.2, target=(0.05, 0.0, 1.25),
                 frames=POSE_FRAMES, ink=0.012):
    """Flat or textured toon renders of the key frames of every clip (the caller set the materials).
    Returns [(clip, frame, path)]."""
    import gfa_render as R
    import gfa_rig as RIG
    scene = bpy.context.scene
    R.setup_cycles(scene, 8)
    hull = R.add_ink_hull(mesh, ink)
    out = []
    for clip, fl in frames.items():
        tr = RD.clip_name(KEY, clip)
        for f in fl:
            RIG.pose_at(arm, tr, f)
            R.aim(scene, Vector(target), Vector(view).normalized(), scale)
            path = os.path.join(out_dir, "pose_%s_%02d.png" % (clip.replace("@", "_"), f))
            out.append((clip, f, R.render(scene, path, size)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    C.remove_objects([hull])
    return out


def main():
    argv = C.script_args()
    C.reset_scene(fps=30)
    col = C.get_collection(KEY)
    mesh, _parts = build_mesh(col)
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "preview"))
    if C.flag(argv, "--preview"):
        preview_materials(mesh)
        preview(mesh, work)
        if C.flag(argv, "--close"):
            import gfa_render as R
            scene = bpy.context.scene
            for name, d, c, sc in (("head", (0.55, -1.0, 0.35), (0, -0.1, 2.25), 0.9),
                                   ("shield", (0.3, -1.0, 0.25), tuple(SHIELD_C), 1.9),
                                   ("back", (-0.4, 1.0, 0.3), (0, 0.1, 1.6), 1.6),
                                   ("top55", (0.0, -math.cos(math.radians(55)), math.sin(math.radians(55))), (0.1, 0, 1.4), 3.0)):
                R.aim(scene, Vector(c), Vector(d).normalized(), sc)
                R.render(scene, os.path.join(work, "close_%s.png" % name), 600)
        C.log("DONE preview")
        return
    arm = build_rig(col)
    C.log("skin", RD.skin_rigid(mesh, arm)["per_bone"])
    add_sockets(arm)
    clips, _solver = build_clips(arm, mesh)
    C.log("clips", clips)
    if C.flag(argv, "--poses"):
        preview_materials(mesh)
        only = C.opt(argv, "--clip", None)
        fr = {k: v for k, v in POSE_FRAMES.items() if only is None or k.startswith(only)}
        if C.flag(argv, "--pick"):
            fr = {"move@loop": (0, 6), "windup": (18,), "attack": (4, 9), "hit": (3,), "death": (27, 66),
                  "cast": (15,), "shield_up": (12,)}
        view = (0.0, -math.cos(math.radians(55)), math.sin(math.radians(55))) if C.flag(argv, "--game") else (0.75, -1.0, 0.45)
        if C.flag(argv, "--zoom"):
            pose_renders(arm, mesh, work, frames=fr, size=C.opt(argv, "--size", 220, int), view=view, scale=2.4,
                         target=(0.25, -0.1, 1.75))
        else:
            pose_renders(arm, mesh, work, frames=fr, size=C.opt(argv, "--size", 220, int), view=view)
        C.log("DONE poses")
        return
    import gfa_export as E
    import gfa_paint as P
    import gfa_render as R
    import gfa_rig as RIG
    import gfa_spec as SPEC
    size = C.opt(argv, "--size", 1024, int)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = P.paint_asset(mesh, KEY, recipes(), tex_dir, size=size, decals=decals(), ao_distance=0.12,
                              ao_samples=24, seed=7, uv_angle=66.0, margin_px=3, uv_zone_scale={"void": 0.35},
                              uv_small_islands=(0.0012, 0.45))
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    clips_rep = RIG.clips_report(arm)
    lo, hi = C.world_bounds([mesh])
    extra = {
        "faction": "fallen_godworks",
        "rig": {"armature": RIG_NAME, "bones": len(arm.data.bones),
                "core": "GF_Hero_v1 core names and parents (23 bones, docs/ART_PIPELINE.md section 5)",
                "extra_bones": ["pauldron_L", "pauldron_R", "core", "mask_L", "mask_R", "shield", "spear"],
                "skinning": "rigid: every plate on one bone (hollow armour, no deformation)",
                "rest_pose": "the guard stance (shield up in front, spear upright)",
                "axes": "bone +Y along the bone, +Z toward the front (Ashen Covenant roll convention)"},
        "clip_roles": {RD.clip_name(KEY, c): txt for c, txt in CLIP_ROLES.items()},
        "clip_aliases": {a: RD.clip_name(KEY, b) for a, b in CLIP_ALIASES.items()},
        "clip_seconds": {c["name"]: c["seconds"] for c in clips_rep},
        "move_cycle_m": round(MOVE_CYCLE_M, 3),
        "footprint": {"collider_radius_m": 0.9, "row": "radius 0.75 x scale 1.2",
                      "model_span_m": [round(hi.x - lo.x, 3), round(hi.y - lo.y, 3)]},
        "content_row": {"class": "Elite", "biome": "cinder_wastes", "behavior": "Support(range: 6.0, shield: 60.0, "
                        "interval: 4.0, keep_distance: 6.0)", "color": "#D9B45A", "shape": "Spire", "scale": 1.2},
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")},
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
        review_paths.update(R.review_enemy(
            KEY, arm, mesh, reports, rwork, "Forge Warden  (forge_warden)",
            "Elite | Fallen Godworks | Cinder Wastes | Support: wraps nearby Unmade in forge-shields | verb: THE WALL "
            "(the broken-halo shield)", clips=clips, swatches=PALETTE, notes=notes, textures=textures, strip_frames=4))
        review_paths["clips"] = clip_sheet(arm, mesh, reports, rwork, clips_rep)
        lineup, top = size_lineup(mesh, rwork)
        game, sil = game_pose_strip(arm, mesh, rwork)
        review_paths["hero_shot"] = hero_shot(mesh, reports)
        layout = {
            "title": "Forge Warden - scale and game read",
            "subtitle": "front orthographic lineup with the 2.2 m hero mannequin (grey bar 2.2 m, gold bar %.2f m); "
                        "below, the in-game camera (55 deg, view height 22 m = 1080 px, 49.1 px/m) at TRUE pixel size" % top,
            "width": 1600,
            "sections": [
                {"label": "Size comparison (front, orthographic) and a 3/4 view of the rest pose", "height": 520,
                 "images": [{"path": lineup, "label": "hero mannequin 2.2 m | forge_warden %.2f m (%.2f x)" % (top, top / 2.2)},
                            {"path": review_paths["hero_shot"], "label": "3/4 view, rest pose (guard)"}]},
                {"label": "In-game camera, 1x true size: guard, windup, bash, cast, brace, death", "height": None,
                 "images": [{"path": pth, "label": lb} for pth, lb in game]},
                {"label": "The same at 3x (nearest) + the guard silhouette at game size (3x)", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[:3]]
                 + [{"path": sil, "label": "silhouette 3x", "scale": 3}]},
                {"label": "", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[3:]]},
            ],
            "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
            "notes": ["The shield (a broken god-halo: 1.33 m ring, 1.7 m with its rays) is the outline in every pose; the "
                      "windup lifts it high, the cast raises it overhead face-up."],
        }
        review_paths["scale"] = R.contact_sheet(layout, os.path.join(reports, "%s_scale.png" % KEY), rwork)
    C.write_json(os.path.join(reports, "build_report.json"),
                 {"export": dict({k: v for k, v in rep.items() if k not in ("nodes",)}, file=C.rel(rep["file"])),
                  "paint": paint_rep, "clips": clips_rep,
                  "review": {k: C.rel(v) for k, v in review_paths.items() if isinstance(v, str)}})
    outputs = [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
               C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")),
               C.rel(os.path.join(tex_dir, KEY + "_emissive.png"))]
    outputs += [C.rel(os.path.join(reports, "%s_%s.png" % (KEY, n))) for n in ("review", "clips", "scale", "34")]
    C.write_pack_status(KIND, KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/forge_warden.py (model, NPR paint, "
                        "GF_ForgeWarden_v1 rig, 8 clips, export + validation, review sheets).", tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
