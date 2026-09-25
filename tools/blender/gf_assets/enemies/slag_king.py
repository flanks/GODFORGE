"""The Slag King (slag_king) - Cinder Wastes boss, THE UNMADE. Built end to end from code: model -> hidden
face cull -> hand-painted NPR textures (2048) -> dedicated rig GF_SlagKing_v1 -> clips -> GLB + meta.json ->
validation -> review sheets. docs/art/ENEMIES.md section 7 (E3) is the brief; art/enemies/slag_king/README.md
records the decisions.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/slag_king.py -- [--preview] [--size 2048] [--no-review] [--quick] [--lite]

  --preview   model only: flat zone-colour views + game-size silhouette in art/enemies/slag_king/work/preview
  --no-review skip the review renders (export + validation only)
  --quick     review with fewer clip frames
  --lite      review only the 3/4 hero shots and the in-game frames (sheets in work/review; for paint passes)

Content row (content/sheets/enemies.csv): slag_king, Boss, cinder_wastes, hp 28000, speed 1.6, radius 2.2,
scale 2.4 (sim collider radius 5.28 m), mass 30, resist Flame 0.5, Boss(script "slag_king"), colour #6B2A14,
greybox shape Colossus - "A living foundry colossus crowned in cooling slag."
Phases (assets/content/bosses.ron): Molten Court (100 %: SlamTrail, Strike Circle at_self, Radial),
Slagfall (60 %: Pools, Summon cinderling x8, SlamTrail, Strike Cone), Final Pour (25 %: Strike Line,
Radial, SlamTrail, Pools).

Design (silhouette verb THE FURNACE THAT WALKS):
  * a hunched slag titan 12.8 m tall with a 15 x 11.4 m footprint (about 2.2 x the 5.28 m collider),
    knuckle-heavy gorilla proportions: short column legs, a huge shoulder hump, forearms bigger than
    the upper arms;
  * the head is a cast-iron furnace slung low in front of the hump; its face is a bottom-hinged furnace
    door (a grille of glowing slits = the "face") over a pocket with a white-hot core; a glowing flue on
    the furnace dome gives the crown a hot centre from the 55 deg camera;
  * a halo crown of 11 broken sword blades and 11 snapped stubs fused into a molten ring floats over the
    furnace dome (joint crown_spin);
  * right fist = a whole broken anvil (horn out and forward, face down: the ground-pound head); left fist = a claw
    of fused broken blades; failed weapons jut from the hump, shoulders and forearms; two chimney
    stacks on the hump glow at the mouth; Unmade obsidian shards with teal ichor grow from the left
    shoulder and the back; teal Unmade cracks run through the slag;
  * phase 2 (Slagfall): the door bursts and hangs open, two molten arms (arm2_*) unfold from under the
    pecs, the blade crown spins (engine-driven, see README). Phase 3 (Final Pour): same body, the engine
    pushes the emissive toward white.

Phase switching (meta.json phase_switch, art/enemies/slag_king/README.md): every clip keys every joint, so
each clip carries its phase. Phase-1 clips hold arm2_upper_L/R at scale 0.001 and the door shut; phase2
grows the arms and bursts the door; phase-2+ clips hold them. In phase >= 2 the client plays '<clip>_p2'
when it exists. The crown spin is procedural on the crown_spin joint.

Adapted pieces: gf_assets toolkit (gfa_*, gfa_boss), Ashen Covenant tools/blender/ac_humanoid_enemy/ac_pose.py
(pose dicts keyed per clip and stashed as NLA tracks) and forge_colossus_gameplay_anims.py (boss clip
vocabulary: wind-up, slam, stagger, multi-stage collapse).
"""
import math
import os
import random
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_boss as B  # noqa: E402
import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY, KIND, TIER = "slag_king", "enemy", "boss"
PAINT_SCALE = 0.125                          # painted at 1/8 scale (gfa_boss.paint_scaled): boss-sized brush strokes
RIG_NAME = "GF_SlagKing_v1"
# slag = the faceted body masses; limb = the same slag on the arms and legs, smooth-shaded and painted
# without facets (the limbs read as muscle, not rock); blade = dark sword steel; edge = the bright
# sharpened edges of every sword (separate strips, so a blade reads as a blade at 38 px/m).
ZONES = ["slag", "limb", "crust", "iron", "steel", "blade", "edge", "molten", "lava", "core", "obsidian", "ichor"]
FLAT = {"slag": "#2A201C", "limb": "#3A2C24", "crust": "#3A2418", "iron": "#3C3844", "steel": "#9C98A4",
        "blade": "#4A4446", "edge": "#E0D8CC", "molten": "#FF7A22", "lava": "#E0541A",
        "core": "#FFF3D6", "obsidian": "#1A1720", "ichor": "#2FBFA8"}

# ---- skeleton pivots (creature space: faces -Y, +X = its left, ground z = 0) -----------------------------
HEAD_AUTHOR_PIVOT = Vector((0.0, -1.7, 6.9))  # the head parts are authored upright around this neck point ...
HEAD_PIVOT = Vector((0.0, -1.95, 6.45))       # ... and moved onto the real neck (lower, further forward)
HEAD_SCALE = 1.18
HEAD_TILT = -7.0                             # the furnace face tilts up 7 deg (reads from the 55 deg camera)
HC = Vector((0.0, -2.75, 7.35))              # furnace centre before the tilt
DOOR_Y = -4.07                               # front face of the door plate (upright head)
DOOR_HINGE_UP = Vector((0.0, -4.0, 6.18))    # door hinge (bottom edge of the mouth), upright head
PIV = {
    "root": (0.0, 0.0, 0.0),
    "pelvis": (0.0, 0.5, 3.7),
    "spine_01": (0.0, 0.3, 5.0),
    "spine_02": (0.0, 0.0, 6.6),
    "upperarm_L": (3.9, -0.3, 8.2), "lowerarm_L": (4.85, -0.1, 5.3), "hand_L": (5.0, -1.95, 2.45),
    "thigh_L": (2.1, 0.8, 3.6), "shin_L": (2.6, -0.1, 2.0), "foot_L": (2.5, 0.4, 0.85),
    "arm2_upper_L": (2.45, -1.45, 6.3), "arm2_lower_L": (5.15, -3.05, 7.0), "arm2_hand_L": (6.25, -4.15, 9.0),
}
for _k in list(PIV):
    if _k.endswith("_L"):
        _p = PIV[_k]
        PIV[_k[:-2] + "_R"] = (-_p[0], _p[1], _p[2])


def head_matrix():
    """Rest transform of the furnace head: tilt about the neck pivot."""
    return (Matrix.Translation(HEAD_PIVOT) @ Matrix.Rotation(math.radians(HEAD_TILT), 4, "X") @
            Matrix.Scale(HEAD_SCALE, 4) @ Matrix.Translation(-HEAD_AUTHOR_PIVOT))


def hm(p):
    return head_matrix() @ Vector(p)


CROWN_UP = Vector((0.0, -2.55, 10.12))          # crown ring centre on the upright head
CROWN_C = None                                # filled in main(): tilted
CROWN_AXIS = None


# ---- shape helpers ---------------------------------------------------------------------------------------

def lump(center, size, sub=2, noise=0.15, freq=0.7, seed=0, rot=(0, 0, 0)):
    """Faceted slag boulder: an icosphere of diameter `size` (x, y, z), noise-displaced."""
    b = M.ico(0.5, sub, scale=size)
    if noise:
        M.noise_displace(b, noise, freq=freq, seed=seed)
    M.xform(b, loc=center, rot=rot)
    return b


def limb(points, radii, sides=10, per=4, noise=0.1, freq=0.8, seed=0, scale_xy=None):
    """Lumpy tapered limb along a smoothed centre line (capped, flat-faceted)."""
    pts = M.catmull([Vector(p) for p in points], per) if len(points) > 2 else [Vector(p) for p in points]
    n = len(pts)
    rr = []
    for i in range(n):
        t = i / (n - 1) * (len(radii) - 1)
        k = min(int(t), len(radii) - 2)
        f = t - k
        rr.append(radii[k] * (1 - f) + radii[k + 1] * f)
    b = M.tube(pts, rr, sides=sides, scale_xy=scale_xy)
    if noise:
        M.noise_displace(b, noise, freq=freq, seed=seed)
    return b


def sword(length, width=0.34, thick=0.08, broken=0.4, seed=0, guard=True, edge=0.17, guard_w=2.6):
    """A broken sword along +Y from y = 0 (the guard) to y = length; width along X, thickness along Z;
    broken = how much of the tip is snapped off at an angle (0 = pointed). Three parts: the dark core with
    its raised ridge (the 'blade' zone), the two sharpened edges (the 'edge' zone: a thinner strip down
    each side, so a bright line frames the dark steel from every angle - a blade, not a crystal) and the
    crossguard (guard_w blade widths across). Returns (core, edges, guard | None)."""
    rng = random.Random(seed)
    tipw = width * (0.2 + 0.55 * broken)
    off = (0.5 if rng.random() < 0.5 else -0.5) * width * (0.25 + 0.3 * broken)
    sec = [(0.0, width, thick, 0.0), (length * 0.6, width * 0.97, thick * 0.92, 0.0),
           (length * 0.88, width * (0.92 if broken else 0.6), thick * 0.8, off * 0.2),
           (length, tipw, thick * 0.6, off)]
    core_k = 1.0 - 2.0 * edge
    flat_ = M.loft_rect([(y, w * core_k, t, cx, 0.0) for (y, w, t, cx) in sec], bevel=min(0.02, thick * 0.2), segments=1)
    ridge = M.loft_rect([(y, w * 0.26, t * 1.6, cx, 0.0) for (y, w, t, cx) in sec[:-1]] +
                        [(length * 0.97, tipw * 0.3, thick * 0.85, off, 0.0)], bevel=0.0)
    core = M.merge(flat_, ridge)
    flat_.free()
    ridge.free()
    strips = []
    for s in (-1.0, 1.0):
        # each strip overlaps the core by a fifth of its width; its outer edge sits on the blade outline
        strips.append(M.loft_rect([(y, w * edge * 1.25, t * 0.5, cx + s * (w * 0.5 - w * edge * 0.625), 0.0)
                                   for (y, w, t, cx) in sec], bevel=0.0))
    edges = M.merge(*strips)
    for b_ in strips:
        b_.free()
    g = None
    if guard:
        g = M.box((width * guard_w, thick * 2.4, thick * 2.2), bevel=thick * 0.35)
    return core, edges, g


def slab(poly, y0, depth):
    """A flat plate from a convex 2D outline [(x, z), ...] in an XZ plane: back face at y = y0, front
    face at y0 - depth (it stands out toward -Y, the creature's front). Face features: eyes, fangs."""
    import bmesh as _bm
    bm = _bm.new()
    back = [bm.verts.new((x, y0, z)) for x, z in poly]
    front = [bm.verts.new((x, y0 - depth, z)) for x, z in poly]
    n = len(poly)
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((back[i], back[j], front[j], front[i]))
    return M.recalc(bm)


def place(bm, origin, direction, x_hint=(1, 0, 0)):
    """Move a part built along +Y so +Y -> direction at origin (x_hint keeps the flat side)."""
    d = Vector(direction).normalized()
    y = d
    x = Vector(x_hint) - y * Vector(x_hint).dot(y)
    if x.length < 1e-5:
        x = Vector((0, 0, 1)) - y * y.z
    x.normalize()
    z = x.cross(y)
    m = Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))
    M.xform(bm, matrix=m)
    return bm


def drip(top, length, r=0.16, seed=0):
    """A molten drip hanging from `top`: a tapered cone and a round bulb."""
    rng = random.Random(seed)
    c = M.cylinder(r, length, sides=6, radius_top=r * 0.35, cap=True)
    M.xform(c, loc=(0, 0, -length / 2), rot=(180, 0, 0))
    bulb = M.ico(r * (0.75 + 0.3 * rng.random()), 1)
    M.xform(bulb, loc=(0, 0, -length))
    out = M.merge(c, bulb)
    M.xform(out, loc=top, rot=(rng.uniform(-8, 8), rng.uniform(-8, 8), rng.uniform(0, 60)))
    return out


def chain(top, links, size, seed=0):
    """A hanging chain of `links` oval links (alternating 90 deg) from `top` downward; link length = size."""
    rng = random.Random(seed)
    parts = []
    w, t = size * 0.62, size * 0.13
    for i in range(links):
        pts = []
        for k in range(10):
            a_ = 2 * math.pi * k / 10
            pts.append((math.cos(a_) * w / 2, 0.0, math.sin(a_) * size / 2))
        lk = M.tube(pts, t, sides=5, closed=True)
        M.xform(lk, rot=(0, 0, 90 * (i % 2) + rng.uniform(-10, 10)), loc=(0, 0, -size * 0.5 - i * size * 0.78))
        parts.append(lk)
    bm_ = M.merge(*parts)
    for p_ in parts:
        p_.free()
    M.xform(bm_, loc=top, rot=(rng.uniform(-6, 6), rng.uniform(-6, 6), 0))
    return bm_


def crystal(base, direction, length, r=0.35, sides=5, seed=0):
    rng = random.Random(seed)
    s = M.spike(r, length, sides=sides, tip=(rng.uniform(-0.1, 0.1) * length, rng.uniform(-0.1, 0.1) * length),
                base_scale=(1.0, 0.75))
    M.xform(s, matrix=M.orient(base, direction, (1, 0.3, 0)))
    return s


def anvil():
    """A broken London-pattern anvil in its own frame: working face on +Z (z = 0 top), horn toward +Y,
    base toward -Z. About 3.0 m long, 2.0 m tall."""
    parts = {}
    body = M.box((1.05, 1.5, 0.78), bevel=0.07, segments=1)
    M.xform(body, loc=(0, 0.0, -0.39))
    face = M.box((1.0, 1.42, 0.12), bevel=0.03)
    M.xform(face, loc=(0, 0.0, -0.02))
    heel = M.box((0.8, 0.62, 0.55), bevel=0.06, taper=(1.0, 1.25))
    M.xform(heel, loc=(0, -1.02, -0.3))
    horn = M.loft_rect([(0.0, 0.92, 0.72, 0, -0.38), (0.35, 0.72, 0.56, 0, -0.3), (0.8, 0.42, 0.34, 0, -0.18),
                        (1.2, 0.12, 0.1, 0, -0.06)], bevel=0.04)
    M.xform(horn, loc=(0, 0.75, 0))
    waist = M.box((0.66, 0.95, 0.72), bevel=0.06, taper=(1.25, 1.35))
    M.xform(waist, loc=(0, -0.05, -1.14))
    base = M.box((1.25, 1.65, 0.45), bevel=0.07, taper=(0.82, 0.78))
    M.xform(base, loc=(0, -0.05, -1.72))
    parts["iron"] = [body, heel, horn, waist, base]
    parts["steel"] = [face]
    return parts


# ---- the model ---------------------------------------------------------------------------------------------

BONE_ORDER = ["root", "pelvis", "spine_01", "spine_02", "head", "door", "crown", "crown_spin",
              "upperarm_L", "lowerarm_L", "hand_L", "upperarm_R", "lowerarm_R", "hand_R",
              "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R",
              "arm2_upper_L", "arm2_lower_L", "arm2_hand_L", "arm2_upper_R", "arm2_lower_R", "arm2_hand_R"]


def build_mesh(col):
    rng = random.Random(7)
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_ORDER)
    containers = []

    def add(bm, zone, bone, name, shading="flat", container=False):
        pid = a.add(bm, zone, bone=bone, name=name, shading=shading)
        if container:
            containers.append(pid)
        return pid

    def add_sword(sw, origin, direction, x_hint, bone, name, guard_zone="iron", head=False):
        """Place a sword() (core, edges, guard) along `direction` at `origin` and add its three parts."""
        core, edges, gd = sw
        for part_, zone, nm in ((core, "blade", name), (edges, "edge", name + "_edge"), (gd, guard_zone, name + "_guard")):
            if part_ is None:
                continue
            place(part_, origin, direction, x_hint)
            if head:
                M.xform(part_, matrix=head_matrix())
            add(part_, zone, bone, nm)

    # ---------------- legs (short columns, bent knees, anvil-block feet) ----------------
    # Every limb part is smooth-shaded 'limb' slag: no facets and no triangle web of edge / cavity lines.
    for side, sx in (("L", 1), ("R", -1)):
        dy = 0.0 if sx > 0 else -0.35            # asymmetric stance: the right foot a step ahead
        hip = Vector((sx * 2.1, 0.8 + dy * 0.3, 3.75))
        knee = Vector((sx * 2.6, -0.15 + dy, 2.0))
        ank = Vector((sx * 2.5, 0.35 + dy, 0.85))
        add(limb([hip, (hip + knee) / 2 + Vector((sx * 0.15, 0, 0)), knee], [1.45, 1.3, 1.05], sides=16,
                 noise=0.16, freq=0.75, seed=11 + sx), "limb", "thigh_" + side, "thigh_" + side, shading="smooth", container=True)
        add(lump(knee + Vector((sx * 0.05, -0.25, 0.05)), (1.9, 1.8, 1.7), sub=3, noise=0.1, seed=13 + sx),
            "limb", "shin_" + side, "knee_" + side, shading="smooth", container=True)
        add(limb([knee, (knee + ank) / 2, ank], [1.0, 1.08, 1.2], sides=16, noise=0.14, freq=0.8, seed=15 + sx),
            "limb", "shin_" + side, "shin_" + side, shading="smooth", container=True)
        # shin guard: a bent iron plate (a fused breastplate) over the front of the shin
        g = M.box((1.35, 0.22, 1.5), bevel=0.06, taper=(0.8, 1.0))
        M.xform(g, loc=(sx * 2.62, -0.95 + dy, 1.45), rot=(-14, 0, sx * -6))
        add(g, "iron", "shin_" + side, "shinguard_" + side)
        # foot: a heavy block with three blunt claws
        f = M.box((1.95, 2.7, 1.05), bevel=0.16, segments=1, taper=(0.82, 0.8))
        M.noise_displace(f, 0.05, freq=1.1, seed=17 + sx)
        M.xform(f, loc=(sx * 2.5, -0.15 + dy, 0.52))
        add(f, "slag", "foot_" + side, "foot_" + side, container=True)
        for k, ox in enumerate((-0.6, 0.0, 0.6)):
            cl = M.horn([(0, 0, 0), (0, -0.45, -0.12), (0, -0.8, -0.45)], 0.26, 0.04, sides=5)
            M.xform(cl, loc=(sx * 2.5 + ox * (1 if sx > 0 else -1), -1.35 + dy, 0.5 + (0.08 if k == 1 else 0)))
            add(cl, "steel" if k == 1 else "iron", "foot_" + side, "claw_%s%d" % (side, k))
        # a fused iron plate on the outer thigh, riveted
        tp = M.box((0.25, 1.5, 1.3), bevel=0.05, taper=(1.0, 0.85))
        M.xform(tp, rot=(0, sx * 12, 0), loc=(sx * 3.45, 0.25 + dy * 0.3, 3.05))
        add(tp, "iron", "thigh_" + side, "thighplate_" + side)
        add(M.rivet_row((sx * 3.6, -0.3 + dy * 0.3, 3.45), (sx * 3.6, 0.8 + dy * 0.3, 3.45), 3, (sx, 0, 0.2), radius=0.08,
                        height=0.06), "iron", "thigh_" + side, "thighplate_rivets")
        add(M.rivet_row((sx * 2.3, -1.25 + dy, 2.0), (sx * 2.95, -1.25 + dy, 2.0), 3, (0, -1, 0.2), radius=0.07,
                        height=0.05), "iron", "shin_" + side, "shinguard_rivets")
        # a broken blade driven into the thigh
        add_sword(sword(1.5, 0.3, 0.07, broken=0.6, seed=21 + sx), hip + Vector((sx * 0.9, 0.2, -0.5)),
                  (sx * 0.8, 0.45, 0.35), (1, 0, 0), "thigh_" + side, "thighblade_" + side)

    # ---------------- pelvis / belly / waist ----------------
    add(lump((0, -0.25, 4.1), (4.6, 3.4, 3.0), sub=3, noise=0.2, seed=31), "slag", "pelvis", "belly", container=True)
    for sx in (1, -1):
        add(lump((sx * 1.9, 0.6, 3.8), (2.5, 2.6, 2.4), sub=3, noise=0.14, seed=33 + sx), "slag", "pelvis",
            "hip", container=True)
    add(lump((0, 1.4, 4.2), (3.8, 2.2, 2.4), sub=2, noise=0.15, seed=36), "slag", "pelvis", "rump", container=True)
    # a broken anvil fused into the belly (face out, horn snapped off) + two hanging chains
    av = anvil()
    Mb = Matrix.Translation((0.15, -1.75, 3.55)) @ Matrix.Rotation(math.radians(-80), 4, "X") @         Matrix.Rotation(math.radians(8), 4, "Y") @ Matrix.Scale(0.8, 4)
    for zone, bms in av.items():
        for k, bm_ in enumerate(bms):
            if zone == "iron" and k == 2:
                bm_.free()
                continue                         # the horn broke off
            M.xform(bm_, matrix=Mb)
            add(bm_, zone, "pelvis", "belly_anvil_%s%d" % (zone, k))
    for cx, cz, n_ in ((-1.35, 2.85, 5), (1.55, 3.0, 4)):
        add(chain((cx, -1.75, cz), n_, 0.34, seed=int(cx * 10)), "iron", "pelvis", "belly_chain", shading="smooth")
    add(lump((0, 0.2, 5.4), (4.8, 3.5, 2.6), sub=3, noise=0.18, seed=41), "slag", "spine_01", "waist", container=True)

    # ---------------- chest, hump, shoulders ----------------
    add(lump((0, -0.6, 7.0), (6.0, 3.8, 3.6), sub=3, noise=0.24, seed=51, rot=(-12, 0, 0)), "slag", "spine_02",
        "chest", container=True)
    for sx in (1, -1):
        add(lump((sx * 1.5, -1.7, 7.1), (2.8, 1.9, 2.6), noise=0.12, seed=53 + sx, rot=(0, 0, sx * 10)),
            "slag", "spine_02", "pec", container=True)
        add(lump((sx * 3.3, -0.35, 8.35), (2.9, 3.0, 2.8), sub=3, noise=0.16, seed=56 + sx), "slag", "spine_02",
            "shoulder", container=True)
    add(lump((0, 1.05, 9.0), (5.6, 4.0, 3.3), sub=3, noise=0.26, seed=61), "slag", "spine_02", "hump", container=True)
    add(lump((0, 1.7, 7.3), (4.6, 2.6, 3.0), sub=2, noise=0.16, seed=62), "slag", "spine_02", "back", container=True)

    # chimney stacks on the hump (the foundry): iron flues with a glowing mouth
    for sx, h, dx in ((1, 2.9, 0.3), (-1, 2.3, 0.22)):
        prof = [(0.66, -0.8), (0.6, h * 0.55), (0.52, h * 0.82), (0.78, h * 0.88), (0.78, h), (0.54, h + 0.04),
                (0.47, h - 0.3)]
        ch = M.lathe(prof, sides=18)
        base = Vector((sx * 1.3, 1.75, 9.6))
        frame_ = M.orient(base, (sx * dx, 0.45, 1.0), (1, 0, 0))
        M.xform(ch, matrix=frame_)
        add(ch, "iron", "spine_02", "chimney", shading="smooth")
        glow = M.cylinder(0.47, 0.06, sides=18)
        M.xform(glow, loc=(0, 0, h - 0.24))
        M.xform(glow, matrix=frame_)
        add(glow, "molten", "spine_02", "chimney_glow", shading="flat")
        for t in (0.2, 0.5):
            band = M.ring(0.6, 0.74, 0.2, sides=18, bevel=0.03)
            M.xform(band, loc=(0, 0, h * t))
            M.xform(band, matrix=frame_)
            add(band, "iron", "spine_02", "chimney_band", shading="flat")

    # failed weapons fused into the hump: one greatsword, one war axe, one spear through the right shoulder
    add_sword(sword(3.3, 0.58, 0.12, broken=0.3, seed=71), (0.75, 1.9, 9.9), (0.22, 0.5, 1.0), (1, 0, 0),
              "spine_02", "greatsword")
    hilt = M.cylinder(0.11, 1.0, sides=6, axis="Y")
    M.xform(hilt, loc=(0, -0.5, 0))
    place(hilt, (0.75, 1.9, 9.9), (0.22, 0.5, 1.0), (1, 0, 0))
    add(hilt, "iron", "spine_02", "greatsword_hilt")
    haft = M.cylinder(0.13, 2.9, sides=6, axis="Y")
    M.xform(haft, loc=(0, 1.45, 0))
    axe = M.loft_rect([(0.0, 0.16, 0.5, 0, 0), (0.55, 0.12, 0.9, 0, 0.1), (1.05, 0.06, 1.5, 0, 0.18)], bevel=0.03)
    M.xform(axe, rot=(0, 0, -90), loc=(0.0, 2.55, 0))
    for part_, zone in ((haft, "iron"), (axe, "steel")):
        place(part_, (2.3, 1.1, 9.3), (0.6, 0.45, 0.8), (0, 0, 1))
        add(part_, zone, "spine_02", "war_axe")
    sp = M.cylinder(0.12, 4.6, sides=6, axis="Y")
    M.xform(sp, loc=(0, 2.3, 0))
    head = M.spike(0.3, 1.0, sides=4, base_scale=(1.0, 0.3))
    M.xform(head, rot=(-90, 0, 0), loc=(0, 4.6, 0))
    spear = M.merge(sp, head)
    place(spear, (-3.0, -1.0, 7.2), (-0.45, 0.62, 0.7))
    add(spear, "iron", "spine_02", "spear")
    for o, d, L, w, br, sd in (((-2.4, 1.6, 9.9), (-0.3, 0.55, 1.0), 1.9, 0.4, 0.6, 76),
                               ((-0.9, 2.7, 9.3), (-0.2, 1.0, 0.45), 1.4, 0.34, 0.75, 77),
                               ((2.6, 1.9, 8.4), (0.7, 0.8, 0.2), 1.5, 0.36, 0.7, 78)):
        add_sword(sword(L, w, 0.1, broken=br, seed=sd), o, d, (1, 0, 0) if abs(d[0]) < 0.5 else (0, 0, 1),
                  "spine_02", "back_blade")
    hh = M.cylinder(0.12, 2.2, sides=6, axis="Y")
    M.xform(hh, loc=(0, 1.1, 0))
    hm_ = M.box((0.95, 0.6, 0.6), bevel=0.08, segments=2)
    M.xform(hm_, loc=(0, 2.3, 0))
    for part_, zone in ((hh, "iron"), (hm_, "iron")):
        place(part_, (1.5, 2.6, 8.0), (0.5, 0.9, -0.1), (0, 0, 1))
        add(part_, zone, "spine_02", "war_hammer")
    # Unmade obsidian shards with teal ichor at the roots (left shoulder + back)
    for i, (o, d, L) in enumerate((((3.5, -0.3, 9.5), (0.3, 0.05, 1.0), 2.5), ((4.4, 0.3, 9.1), (0.85, 0.2, 0.75), 1.8),
                                   ((3.0, 0.7, 9.7), (0.1, 0.5, 1.0), 1.5), ((-1.8, 2.5, 8.6), (-0.4, 0.8, 0.6), 1.7),
                                   ((-1.0, 2.8, 9.1), (-0.1, 0.7, 0.9), 1.2))):
        add(crystal(o, d, L, r=0.36 + 0.05 * (i % 2), seed=80 + i), "obsidian", "spine_02", "shard")
        root = M.ico(0.45, 1, scale=(1.0, 1.0, 0.6))
        M.xform(root, matrix=M.orient(o, d, (1, 0, 0)))
        add(root, "ichor", "spine_02", "shard_root")

    # cooled slag flows running down the masses (surface character; each rides the mass it sits on)
    flows = [  # (centre, size, rot, bone)
        ((2.6, -1.2, 8.9), (1.3, 1.1, 2.0), (18, 12, 20), "spine_02"), ((-2.7, -1.1, 8.8), (1.2, 1.0, 1.9), (15, -10, -25), "spine_02"),
        ((1.2, 2.6, 9.0), (1.5, 1.0, 2.2), (-20, 8, 10), "spine_02"), ((-1.4, 2.5, 8.2), (1.4, 1.0, 2.4), (-25, -6, -15), "spine_02"),
        ((0.2, 3.0, 7.6), (1.6, 0.9, 2.0), (-15, 0, 0), "spine_02"), ((2.9, 0.9, 7.9), (1.2, 1.2, 2.1), (5, 20, 10), "spine_02"),
        ((-3.0, 0.8, 7.8), (1.2, 1.2, 2.0), (5, -18, -10), "spine_02"), ((1.8, -2.35, 6.3), (1.1, 0.8, 1.6), (25, 10, 5), "spine_02"),
        ((-1.9, -2.3, 6.2), (1.1, 0.8, 1.5), (25, -10, -5), "spine_02"), ((1.3, -1.5, 4.3), (1.2, 0.9, 1.6), (20, 5, 0), "pelvis"),
        ((-1.6, -1.2, 4.6), (1.1, 0.9, 1.5), (18, -5, 0), "pelvis"), ((0.0, 2.2, 5.6), (1.8, 1.0, 1.6), (-15, 0, 0), "spine_01"),
        ((2.9, 0.6, 3.2), (1.0, 1.0, 1.5), (0, 15, 0), "thigh_L"), ((-2.9, 0.4, 3.1), (1.0, 1.0, 1.5), (0, -15, 0), "thigh_R"),
        ((4.1, 0.3, 7.2), (1.1, 1.2, 1.8), (0, 10, 0), "upperarm_L"), ((-4.2, 0.3, 7.1), (1.1, 1.2, 1.8), (0, -10, 0), "upperarm_R"),
        ((5.55, -0.5, 4.3), (1.0, 1.3, 1.5), (20, 15, 0), "lowerarm_L"), ((-5.6, -0.6, 4.2), (1.0, 1.3, 1.5), (20, -15, 0), "lowerarm_R"),
        ((4.7, -1.6, 3.9), (1.1, 0.9, 1.3), (30, 0, 10), "lowerarm_L"), ((-4.75, -1.7, 3.8), (1.1, 0.9, 1.3), (30, 0, -10), "lowerarm_R"),
        ((2.3, -0.9, 3.4), (1.1, 0.9, 1.4), (25, 0, 0), "thigh_L"), ((-2.3, -1.1, 3.3), (1.1, 0.9, 1.4), (25, 0, 0), "thigh_R"),
        ((2.95, 0.6, 1.4), (0.9, 1.0, 1.2), (0, 12, 0), "shin_L"), ((-2.9, 0.3, 1.4), (0.9, 1.0, 1.2), (0, -12, 0), "shin_R"),
    ]
    for i, (c_, sz, rt, bn) in enumerate(flows):
        # poured slag: smooth-shaded (a flat-shaded sub-2 ico painted a web of edge lines)
        on_limb = bn.split("_")[0] in ("thigh", "shin", "upperarm", "lowerarm")
        add(lump(c_, sz, sub=2, noise=0.1, freq=1.1, seed=300 + i, rot=rt), "limb" if on_limb else "slag", bn,
            "slag_flow", shading="smooth")

    # belly molten drips
    for i, p in enumerate(((-1.1, -1.55, 2.95), (0.9, -1.4, 2.9), (1.9, -0.9, 3.05))):
        add(drip(p, 0.7 + 0.25 * (i % 2), 0.17, seed=90 + i), "molten", "pelvis", "drip", shading="smooth")

    # ---------------- the furnace head ----------------
    H = head_matrix()

    def head_part(bm, zone, name, bone="head", shading="flat", container=False):
        M.xform(bm, matrix=H)
        return add(bm, zone, bone, name, shading=shading, container=container)

    hx, hy, hz = HC
    # mouth pocket: x in [-0.85, 0.85], z in [6.3, 8.05], y from the front (-4.0) back to -2.9
    brow = M.box((3.0, 2.9, 0.95), bevel=0.14, segments=1, taper=(0.92, 0.92))
    M.xform(brow, loc=(hx, hy + 0.05, 8.5))
    head_part(brow, "iron", "brow", container=True)
    dome = M.lathe([(1.35, 0.0), (1.3, 0.35), (1.05, 0.72), (0.62, 0.95), (0.0, 1.02)], sides=20)
    M.xform(dome, loc=(hx, hy + 0.2, 8.85), scale=(1.05, 1.0, 1.0))
    head_part(dome, "iron", "dome", shading="smooth", container=True)
    flue = M.lathe([(0.62, -0.2), (0.55, 0.3), (0.7, 0.42), (0.7, 0.58), (0.46, 0.6), (0.4, 0.38)], sides=16)
    M.xform(flue, loc=(hx, hy + 0.2, 9.75))
    head_part(flue, "iron", "flue", shading="smooth")
    fg = M.cylinder(0.41, 0.05, sides=16)
    M.xform(fg, loc=(hx, hy + 0.2, 10.18))
    head_part(fg, "molten", "flue_glow")
    dband = M.ring(1.3, 1.45, 0.26, sides=24, bevel=0.03)
    M.xform(dband, loc=(hx, hy + 0.2, 8.98), scale=(1.05, 1.0, 1.0))
    head_part(dband, "iron", "dome_band")
    dpts = [(hx + 1.47 * 1.05 * math.cos(2 * math.pi * k / 14), hy + 0.2 + 1.47 * math.sin(2 * math.pi * k / 14), 8.98)
            for k in range(14)]
    head_part(M.studs(dpts, [(math.cos(2 * math.pi * k / 14), math.sin(2 * math.pi * k / 14), 0) for k in range(14)],
                      0.08, 0.06), "iron", "dome_rivets")
    head_part(M.rivet_row((hx - 1.15, DOOR_Y - 0.02, 6.1), (hx + 1.15, DOOR_Y - 0.02, 6.1), 6, (0, -1, 0), radius=0.08,
                          height=0.06), "iron", "chin_rivets")
    for sx in (1, -1):
        head_part(M.rivet_row((sx * 1.2, DOOR_Y - 0.04, 6.45), (sx * 1.2, DOOR_Y - 0.04, 7.95), 4, (0, -1, 0),
                              radius=0.08, height=0.06), "iron", "cheek_rivets")
    chin = M.box((2.7, 2.7, 0.5), bevel=0.1, taper=(1.0, 1.0))
    M.xform(chin, loc=(hx, hy + 0.1, 6.02))
    head_part(chin, "iron", "chin", container=True)
    for sx in (1, -1):
        ck = M.box((0.62, 2.8, 1.85), bevel=0.1)
        M.xform(ck, loc=(sx * 1.2, hy + 0.05, 7.17))
        head_part(ck, "iron", "cheek", container=True)
        # side flanges with rivets
        fl = M.box((0.16, 1.9, 2.1), bevel=0.04)
        M.xform(fl, loc=(sx * 1.55, hy - 0.2, 7.2))
        head_part(fl, "iron", "flange")
        head_part(M.rivet_row((sx * 1.64, hy - 1.0, 6.35), (sx * 1.64, hy - 1.0, 8.05), 4, (sx, 0, 0), radius=0.08,
                              height=0.06), "iron", "flange_rivets")
    back = M.box((1.8, 1.4, 1.85), bevel=0.06)
    M.xform(back, loc=(hx, hy + 0.85, 7.17))
    head_part(back, "iron", "pocket_back", container=True)
    # hot pocket liner and the white-hot core
    liner = M.box((1.66, 1.1, 1.7))
    import bmesh as _bm
    _bm.ops.delete(liner, geom=[f for f in liner.faces if f.normal.y < -0.9], context="FACES_ONLY")
    _bm.ops.reverse_faces(liner, faces=liner.faces[:])
    M.xform(liner, loc=(hx, hy - 0.62, 7.17))
    head_part(liner, "molten", "pocket_liner", shading="flat")
    core = M.ico(0.62, 2)
    M.xform(core, loc=(hx, hy - 0.45, 7.17))
    head_part(core, "core", "core", shading="smooth")
    # rim bands and rivets round the mouth
    rim = M.box((2.3, 0.2, 0.22), bevel=0.04)
    M.xform(rim, loc=(hx, DOOR_Y + 0.12, 8.12))
    head_part(rim, "iron", "rim_top")
    head_part(M.rivet_row((hx - 1.25, DOOR_Y + 0.02, 8.5), (hx + 1.25, DOOR_Y + 0.02, 8.5), 6, (0, -1, 0),
                          radius=0.09, height=0.07), "iron", "brow_rivets")
    # molten drips from the chin
    for i, xo in enumerate((-0.7, 0.15, 0.85)):
        d = drip((hx + xo, DOOR_Y + 0.35, 5.8), 0.6 + 0.3 * (i == 1), 0.15, seed=100 + i)
        head_part(d, "molten", "chin_drip", shading="smooth")

    # ---------------- the furnace door (the face) on its hinge bone ----------------
    dz0, dz1 = 6.2, 8.1
    door = M.box((1.95, 0.22, dz1 - dz0), bevel=0.06)
    M.xform(door, loc=(hx, DOOR_Y + 0.11, (dz0 + dz1) / 2))
    head_part(door, "iron", "door", bone="door", container=True)
    frame = []
    for (sx0, sz0, w, h) in ((0, dz1 - 0.08, 2.05, 0.16), (0, dz0 + 0.08, 2.05, 0.16), (-0.95, (dz0 + dz1) / 2, 0.16, 1.9),
                             (0.95, (dz0 + dz1) / 2, 0.16, 1.9)):
        fb = M.box((w, 0.12, h), bevel=0.03)
        M.xform(fb, loc=(hx + sx0, DOOR_Y - 0.05, sz0))
        frame.append(fb)
    head_part(M.merge(*frame), "iron", "door_frame", bone="door")
    # the face, a SCOWL that reads at 38 px/m: two eye slits that slope DOWN toward the centre (inner ends
    # low: angry, never worried) under a V of heavy iron brows, over a jagged grate mouth: iron fangs from
    # above and below interlock across a glowing slot, so the glow between them is a zigzag.
    y_face = DOOR_Y + 0.0                       # the door plate's front face
    glow = []
    for sx in (1, -1):
        eye = [(0.12, 7.34), (0.80, 7.66), (0.82, 7.86), (0.10, 7.56)]      # inner-bottom, outer-bottom, outer-top, inner-top
        glow.append(slab([(hx + sx * x, z) for x, z in (eye if sx > 0 else list(reversed(eye)))], y_face, 0.07))
    mouth = [(-0.74, 7.12), (0.74, 7.12), (0.64, 6.40), (-0.64, 6.40)]
    glow.append(slab([(hx + x, z) for x, z in mouth], y_face, 0.05))
    head_part(M.merge(*glow), "molten", "door_slits", bone="door")
    brows, fangs = [], []
    for sx in (1, -1):
        brow = [(0.0, 7.60), (0.92, 7.95), (0.92, 8.08), (-0.02, 7.78)]
        brows.append(slab([(hx + sx * x, z) for x, z in (brow if sx > 0 else list(reversed(brow)))], y_face, 0.2))
    for x0 in (-0.54, -0.18, 0.18, 0.54):       # upper fangs, pointing down
        fangs.append(slab([(hx + x0 - 0.13, 7.14), (hx + x0 + 0.13, 7.14), (hx + x0 + 0.02, 6.68)], y_face, 0.13))
    for x0 in (-0.36, 0.0, 0.36):               # lower fangs, pointing up between them (the glow between = a zigzag)
        fangs.append(slab([(hx + x0 + 0.12, 6.38), (hx + x0 + 0.01, 6.82), (hx + x0 - 0.12, 6.38)], y_face, 0.13))
    head_part(M.merge(*brows), "iron", "door_brows", bone="door")
    head_part(M.merge(*fangs), "iron", "door_fangs", bone="door")
    # latch: a vertical bolt on the right frame edge (off the face, so it never reads as a nose or a mouth)
    lh = M.box((0.16, 0.18, 0.5), bevel=0.03)
    M.xform(lh, loc=(hx - 1.06, DOOR_Y - 0.08, 7.2))
    head_part(lh, "steel", "latch", bone="door")
    # hinge knuckles
    for sx in (-0.6, 0.6):
        kn = M.cylinder(0.14, 0.4, sides=6, axis="X")
        M.xform(kn, loc=(hx + sx, DOOR_HINGE_UP.y - 0.04, DOOR_HINGE_UP.z))
        head_part(kn, "iron", "hinge", bone="door")

    # ---------------- the blade crown (halo of broken swords fused into a molten ring) ----------------
    ring = M.ring(1.0, 1.42, 0.38, sides=40, bevel=0.07)
    M.noise_displace(ring, 0.04, freq=2.0, seed=111)
    M.xform(ring, loc=CROWN_UP)
    head_part(ring, "iron", "crown_ring", bone="crown_spin", container=True)
    n = 11
    lengths = [2.5, 1.95, 2.35, 2.05, 2.6, 1.85, 2.45, 2.15, 1.95, 2.55, 1.9]
    HILTED = (0, 2, 4, 7, 9)       # these swords sit further out: grip + crossguard show outside the ring
    for i in range(n):
        # half a step off the front: blades 0 and 10 flank the furnace face and no blade covers it from the
        # game camera; a short steep stub sits over the brow instead
        ang = 2 * math.pi * (i + 0.5) / n - math.pi / 2
        r_hat = Vector((math.cos(ang), math.sin(ang), 0))
        elev = math.radians(33 + 6 * (((i * 4) % 3) - 1))
        dvec = r_hat * math.cos(elev) + Vector((0, 0, 1)) * math.sin(elev)
        o = CROWN_UP + r_hat * 1.22 + Vector((0, 0, 0.1))
        tang = (-math.sin(ang), math.cos(ang), 0)
        br = 0.2 + 0.6 * ((i * 7) % 5) / 4
        if i in HILTED:
            push = 0.5
            add_sword(sword(lengths[i] - 0.3, 0.5, 0.11, broken=br, seed=120 + i, guard_w=2.3), o + dvec * push, dvec,
                      tang, "crown_spin", "crown_blade", guard_zone="steel", head=True)
            grip = M.cylinder(0.075, push + 0.1, sides=6, axis="Y")
            M.xform(grip, loc=(0, (push + 0.1) / 2 - 0.1, 0))
            place(grip, o, dvec, tang)
            head_part(grip, "iron", "crown_grip", bone="crown_spin")
        else:
            add_sword(sword(lengths[i], 0.5, 0.11, broken=br, seed=120 + i), o, dvec, tang, "crown_spin",
                      "crown_blade", head=True)
        # a short broken stub between blades (inner ring, steeper): the crown of a thousand failed weapons
        mid = ang + math.pi / n
        r2 = Vector((math.cos(mid), math.sin(mid), 0))
        e2_ = math.radians(62 + 6 * ((i % 3) - 1))
        d2 = r2 * math.cos(e2_) + Vector((0, 0, 1)) * math.sin(e2_)
        o2 = CROWN_UP + r2 * 1.12 + Vector((0, 0, 0.12))
        tang2 = (-math.sin(mid), math.cos(mid), 0)
        add_sword(sword(0.8 + 0.35 * ((i * 3) % 4) / 3, 0.36, 0.09, broken=0.85, seed=160 + i), o2, d2, tang2,
                  "crown_spin", "crown_stub", head=True)
        # a molten weld bead between blades
        bead = M.ico(0.2, 1, scale=(1.3, 1.0, 0.8))
        M.xform(bead, loc=CROWN_UP + Vector((math.cos(mid) * 1.44, math.sin(mid) * 1.44, -0.05)))
        head_part(bead, "molten", "crown_bead", bone="crown_spin")

    # ---------------- arms ----------------
    for side, sx in (("L", 1), ("R", -1)):
        sh_ = Vector(PIV["upperarm_" + side])
        el = Vector(PIV["lowerarm_" + side])
        wr = Vector(PIV["hand_" + side])
        add(limb([sh_, (sh_ + el) / 2 + Vector((sx * 0.35, 0.25, 0)), el], [1.3, 1.15, 0.95], sides=16, noise=0.16, freq=0.75,
                 seed=140 + sx), "limb", "upperarm_" + side, "upperarm_" + side, shading="smooth", container=True)
        add(lump(sh_ + Vector((sx * 0.3, 0.1, -1.2)), (2.0, 2.0, 2.4), sub=3, noise=0.1, seed=142 + sx), "limb",
            "upperarm_" + side, "bicep_" + side, shading="smooth", container=True)
        add(lump(el + Vector((sx * 0.05, 0.25, 0.0)), (1.95, 1.95, 1.9), sub=3, noise=0.08, seed=144 + sx), "limb",
            "lowerarm_" + side, "elbow_" + side, shading="smooth", container=True)
        mid = (el + wr) / 2 + Vector((sx * 0.2, 0.1, 0.1))
        add(limb([el, mid, wr], [1.05, 1.35, 1.25], sides=18, noise=0.17, freq=0.7, seed=146 + sx), "limb",
            "lowerarm_" + side, "forearm_" + side, shading="smooth", container=True)
        # iron bracer bands round the forearm (fused cuffs)
        for k, t in enumerate((0.45, 0.8)):
            c = el.lerp(wr, t)
            cuff = M.ring(1.18 + 0.12 * k, 1.42 + 0.12 * k, 0.4, sides=16, bevel=0.05)
            M.xform(cuff, matrix=M.orient(c, (wr - el), (1, 0, 0)))
            add(cuff, "iron", "lowerarm_" + side, "cuff_%s%d" % (side, k))
        # a broken shackle chain hanging from the lower cuff
        c0 = el.lerp(wr, 0.8) + Vector((sx * 1.25, 0.2, -0.3))
        add(chain(c0, 4, 0.3, seed=40 + sx), "iron", "lowerarm_" + side, "wrist_chain", shading="smooth")
        # one broken blade jutting from the back of the forearm
        o = el.lerp(wr, 0.5) + Vector((sx * 0.8, 0.8, 0.25))
        add_sword(sword(2.1, 0.44, 0.1, broken=0.55, seed=150 + sx), o, (sx * 0.6, 0.85, 0.45), (0, 0, 1),
                  "lowerarm_" + side, "arm_blade")
        # molten drips under the forearm
        add(drip(el.lerp(wr, 0.55) + Vector((0, -0.4, -1.15)), 0.8, 0.17, seed=160 + sx), "molten",
            "lowerarm_" + side, "arm_drip", shading="smooth")

    # right fist: a whole anvil, face down (the ground-pound head), horn pointing out and forward so the
    # classic anvil profile shows from the front and from the game camera
    wr = Vector(PIV["hand_R"])
    av = anvil()
    hdir = Vector((-0.78, -0.62, 0.0)).normalized()          # horn direction
    zdir = Vector((0.0, 0.0, -1.0))                          # working face down
    xdir = hdir.cross(zdir)
    rot = Matrix((xdir, hdir, zdir)).transposed().to_4x4()
    Ma = Matrix.Translation(wr + Vector((0.0, -0.35, -0.2))) @ rot @ Matrix.Translation(Vector((0, 0.05, 1.95)))
    for zone, bms in av.items():
        for k, bm_ in enumerate(bms):
            M.xform(bm_, matrix=Ma)
            add(bm_, zone, "hand_R", "anvil_%s%d" % (zone, k), container=(zone == "iron" and k == 0))
    add(lump(wr + Vector((0, -0.2, 0.25)), (1.9, 1.9, 1.3), sub=3, noise=0.08, seed=171), "limb", "hand_R", "wrist_R",
        shading="smooth", container=True)

    # left fist: a claw of four fused broken swords and a thumb; the two middle swords stand out of the fist
    # far enough to show their crossguards (they read as swords, not crystals)
    wl = Vector(PIV["hand_L"])
    palm = lump(wl + Vector((0.05, -0.45, -0.35)), (1.9, 2.1, 1.5), sub=3, noise=0.08, seed=181)
    add(palm, "limb", "hand_L", "palm_L", shading="smooth", container=True)
    for k, ox in enumerate((-0.55, -0.18, 0.2, 0.58)):
        o = wl + Vector((ox, -1.25, -0.55))
        dcl = Vector((ox * 0.25, -0.55, -1.0)).normalized()
        L = (1.35, 1.6, 1.55, 1.2)[k]
        if k in (1, 2):
            add_sword(sword(L - 0.3, 0.3, 0.09, broken=0.15, seed=185 + k, guard_w=2.6), o + dcl * 0.42, dcl,
                      (1, 0, 0), "hand_L", "claw_blade", guard_zone="steel")
            grip = M.cylinder(0.06, 0.5, sides=6, axis="Y")
            M.xform(grip, loc=(0, 0.17, 0))
            place(grip, o, dcl, (1, 0, 0))
            add(grip, "iron", "hand_L", "claw_grip")
        else:
            add_sword(sword(L, 0.3, 0.09, broken=0.15, seed=185 + k), o, dcl, (1, 0, 0), "hand_L", "claw_blade")
    th = M.horn([wl + Vector((-0.75, -0.55, -0.4)), wl + Vector((-1.1, -1.0, -0.9)), wl + Vector((-1.0, -1.35, -1.6))],
                0.28, 0.05, sides=5)
    add(th, "steel", "hand_L", "thumb")

    # shoulder pieces: left = a broken crucible cupping the shoulder, right = a stack of fused plates
    cru = M.lathe([(0.0, -0.1), (1.2, 0.0), (1.55, 0.7), (1.7, 1.35), (1.5, 1.35), (1.35, 0.75), (0.0, 0.6)], sides=18,
                  angle=250, start_angle=-40)
    M.xform(cru, matrix=M.orient(Vector((3.95, -0.3, 8.7)), (0.55, -0.1, 1.0), (0, 1, 0)))
    add(cru, "iron", "upperarm_L", "crucible", shading="smooth")
    for k in range(3):
        pl = M.box((2.3 - 0.35 * k, 2.4 - 0.3 * k, 0.28), bevel=0.06, taper=(0.9, 0.9))
        M.xform(pl, rot=(8 * (k - 1), -22 - 6 * k, 5 * k), loc=(-3.95 - 0.12 * k, -0.35 + 0.1 * k, 9.2 + 0.26 * k))
        add(pl, "iron", "upperarm_R", "pauldron_%d" % k)
    add(M.rivet_row((-3.2, -1.3, 9.35), (-4.4, -1.3, 8.95), 4, (0, -0.5, 0.8), radius=0.09, height=0.07), "iron",
        "upperarm_R", "pauldron_rivets")

    # ---------------- phase-2 molten arms (scaled to ~0 until Slagfall) ----------------
    for side, sx in (("L", 1), ("R", -1)):
        s2 = Vector(PIV["arm2_upper_" + side])
        e2 = Vector(PIV["arm2_lower_" + side])
        w2 = Vector(PIV["arm2_hand_" + side])
        add(limb([s2, (s2 + e2) / 2 + Vector((0, -0.2, 0.4)), e2], [0.66, 0.78, 0.6], sides=12, noise=0.1,
                 freq=1.2, seed=200 + sx), "lava", "arm2_upper_" + side, "arm2_upper", shading="smooth")
        add(lump(e2, (1.3, 1.3, 1.25), sub=1, noise=0.08, seed=202 + sx), "crust", "arm2_lower_" + side, "arm2_elbow")
        add(limb([e2, (e2 + w2) / 2 + Vector((sx * 0.25, -0.15, 0)), w2], [0.6, 0.66, 0.62], sides=12, noise=0.08,
                 freq=1.3, seed=204 + sx), "lava", "arm2_lower_" + side, "arm2_lower", shading="smooth")
        for k, (t, sz, up) in enumerate(((0.22, 1.05, 0.45), (0.5, 1.15, 0.5), (0.8, 0.95, 0.42))):
            c = s2.lerp(e2, t) + Vector((sx * 0.05, 0.25, up))
            add(lump(c, (sz, sz * 1.3, sz * 0.62), sub=2, noise=0.07, freq=1.5, seed=210 + k + 5 * sx,
                     rot=(10, sx * 15, 0)), "crust", "arm2_upper_" + side, "arm2_plate")
        for k, (t, sz) in enumerate(((0.3, 0.95), (0.68, 0.9))):
            c = e2.lerp(w2, t) + Vector((sx * 0.3, 0.3, 0.05))
            add(lump(c, (sz * 0.75, sz, sz * 1.15), sub=2, noise=0.06, freq=1.5, seed=216 + k + 5 * sx), "crust",
                "arm2_lower_" + side, "arm2_plate")
        # the hand: a crust palm with three long splayed talons and a thumb (reads as an open claw)
        add(lump(w2 + Vector((0, -0.15, 0.35)), (1.35, 1.3, 1.15), sub=2, noise=0.06, seed=220 + sx), "crust",
            "arm2_hand_" + side, "arm2_palm")
        for k, (fx, fy) in enumerate(((-0.75, 0.15), (-0.25, -0.3), (0.25, -0.35), (0.72, 0.05))):
            b0 = w2 + Vector((sx * fx * 0.6, fy - 0.2, 0.75))
            d1 = Vector((sx * fx * 1.0, fy - 0.4, 1.0)).normalized()
            tal = M.horn([b0, b0 + d1 * 0.8, b0 + d1 * 1.45 + Vector((0, -0.45, 0.0))], 0.22, 0.03, sides=6)
            add(tal, "steel", "arm2_hand_" + side, "arm2_talon")
        b0 = w2 + Vector((-sx * 0.55, -0.3, 0.2))
        add(M.horn([b0, b0 + Vector((-sx * 0.5, -0.45, 0.25)), b0 + Vector((-sx * 0.65, -0.95, 0.45))], 0.17, 0.03,
                   sides=5), "steel", "arm2_hand_" + side, "arm2_thumb")
        add(drip(e2 + Vector((0, 0, -0.55)), 0.6, 0.13, seed=230 + sx), "molten", "arm2_lower_" + side, "arm2_drip",
            shading="smooth")

    tris_before = a.tris()
    culled = B.cull_hidden_faces(a, containers, eps=0.03)
    obj = a.to_object(col)
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    C.log("mesh: %d parts, %d tris (%d before culling, %d buried faces removed)" % (len(a.parts), tris, tris_before, culled))
    obj["gfa_parts_list"] = ",".join(sorted({p["name"] for p in a.parts}))
    return obj


# ---- previews -------------------------------------------------------------------------------------------

def preview(mesh, out_dir):
    views = {"front": (0.0, -1.0, 0.12), "34_front": (0.7, -0.7, 0.3), "side": (1.0, 0.0, 0.1),
             "back": (0.0, 1.0, 0.12), "34_back": (-0.7, 0.7, 0.3), "top": (0.0, -0.0001, 1.0),
             "game": tuple(B.game_dir())}
    out = B.flat_views([mesh], out_dir, KEY, FLAT, views, size=520)
    man = R.mannequin(aim_dir=(0.3, -1.0, 0.0))
    man.location = (-4.0, -8.0, 0.0)
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / 22.0
    R.setup_workbench_flat(scene)
    R.aim(scene, Vector((0, -1.5, 4.0)), B.game_dir(), 900 / ppm, dist=90)
    out["sil_game"] = R.render(scene, os.path.join(out_dir, "%s_sil_game22.png" % KEY), 900, 700)
    C.remove_objects([man])
    return out


# ---- paint ---------------------------------------------------------------------------------------------

PALETTE = [  # (name, hex) for the review sheet
    ("slag shadow", "#0C0908"), ("slag", "#2B201B"), ("slag light", "#5E4434"), ("row tint", "#6B2A14"),
    ("iron", "#363337"), ("steel", "#77716C"), ("molten", "#FF6B1A"), ("forge gold", "#FFC24B"),
    ("white-hot core", "#FFF3D6"), ("obsidian", "#1A1720"), ("unmade teal", "#2FBFA8"),
]


def frame_at(origin, normal, up=(0, 0, 1)):
    """Decal frame: +Z = the outward surface normal (projection direction), +Y as close to `up` as possible."""
    z = Vector(normal).normalized()
    y = Vector(up) - z * Vector(up).dot(z)
    if y.length < 1e-4:
        y = Vector((0, 1, 0)) - z * z.y
    y.normalize()
    x = y.cross(z)
    return Matrix(((x.x, y.x, z.x, origin[0]), (x.y, y.y, z.y, origin[1]), (x.z, y.z, z.z, origin[2]), (0, 0, 0, 1)))


def recipes():
    import gfa_paint as P
    door_c = tuple(hm((0.0, DOOR_Y, 7.2)))
    crown_c = tuple(CROWN_C)
    core_c = tuple(hm((HC.x, HC.y - 0.45, 7.17)))
    # slag, limb, iron and steel carry NO painter edge strokes (edge=0): the painter strokes every convex edge
    # over 20 deg, which drew the triangle web on the slag and scratchy double lines on every bevel. Their
    # strokes are painted by paint_extras (EXTRAS[zone]["edge"]): only real creases, mostly on up-facing
    # planes, one stroke wider than the bevel.
    # slag body: faceted value planes, cavity darks, the row tint round the furnace
    slag = P.zone(base="#2B201B", shadow="#0C0908", light="#8C6A52", planes=0.16, parts=0.07, brush=0.06,
                  brush_freq=0.55, cavity=0.85, cavity_width=0.09, ao=0.65, ao_range=(0.22, 0.62), edge=0.0,
                  gradient={"center": door_c, "range": (6.5, 2.0), "color": "#6B2A14", "amount": 0.45},
                  spots={"color": "#3E1E14", "amount": 0.45, "freq": 0.45, "threshold": (0.56, 0.7)},
                  stroke=(0, 0, -1), stroke_amount=0.05, stroke_freq=(1.4, 0.2))
    # limbs: the same slag, smooth: soft planes, no facet values; big soft contact shadows
    limb_ = P.zone(base="#2B201B", shadow="#0C0908", light="#8C6A52", planes=0.04, parts=0.06, brush=0.05,
                   brush_freq=0.45, cavity=0.7, cavity_width=0.08, ao=0.7, ao_range=(0.25, 0.6), edge=0.0,
                   spots={"color": "#3E1E14", "amount": 0.4, "freq": 0.4, "threshold": (0.56, 0.7)})
    crust = P.zone(base="#3A2418", shadow="#140A07", light="#8A5234", planes=0.14, parts=0.08, brush=0.06,
                   brush_freq=0.9, cavity=0.8, cavity_width=0.06, ao=0.5, edge=0.95, edge_width=0.06,
                   edge_breakup=0.35, spots={"color": "#7A2A10", "amount": 0.5, "freq": 1.2, "threshold": (0.55, 0.68)})
    # iron bands, plates and rivets: broad value planes (no spots, no streaks, a quiet low-frequency brush)
    # and one brushy top-edge stroke (paint_extras)
    iron = P.zone(base="#363337", shadow="#0E0D10", light="#6E6970", planes=0.16, parts=0.07, brush=0.025,
                  brush_freq=0.35, cavity=0.85, cavity_width=0.06, ao=0.6, ao_range=(0.25, 0.65), edge=0.0,
                  gradient={"center": door_c, "range": (3.2, 1.0), "color": "#7A3418", "amount": 0.4})
    steel = P.zone(base="#77716C", shadow="#2A2628", light="#B4AA9E", planes=0.16, parts=0.08, brush=0.025,
                   brush_freq=0.4, cavity=0.7, cavity_width=0.04, ao=0.5, edge=0.0)
    # sword steel: DARK blued steel (the bright line is the separate 'edge' zone), temper-bronze toward the
    # crown ring, glowing only in the weld right at the ring
    weld = {"color": "#C8400C", "hot": "#FF6B1A", "core": "#FFC24B", "mode": "radial", "center": crown_c,
            "radius": 3.4, "fade": (0.5, 0.44), "base_mix": 0.2}
    blade = P.zone(base="#3A3539", shadow="#121014", light="#6E6870", planes=0.1, parts=0.08, brush=0.025,
                   brush_freq=0.5, cavity=0.7, cavity_width=0.04, ao=0.45, edge=0.35, edge_width=0.05,
                   edge_breakup=0.3,
                   gradient={"center": crown_c, "range": (2.4, 1.7), "color": "#6E3C1C", "amount": 0.55}, emit=weld)
    # the sharpened edges: bright cold-warm steel, flat, one value (so a blade has a bright outline)
    edge_ = P.zone(base="#CFC5B6", shadow="#6A625C", light="#F4ECDF", planes=0.05, parts=0.04, brush=0.02,
                   brush_freq=0.5, cavity=0.2, cavity_width=0.02, ao=0.25, edge=0.5, edge_width=0.03,
                   edge_breakup=0.4, emit=weld)
    # the phase-2 molten limbs: white-hot where they leave the body, cooling to dark crust at the claws
    lava = P.zone(base="#35180F", shadow="#0E0605", light="#7A3A20", planes=0.1, parts=0.05, brush=0.08,
                  brush_freq=1.2, cavity=0.6, cavity_width=0.05, ao=0.3, edge=0.8, edge_width=0.06, edge_breakup=0.4,
                  emit={"color": "#A82E0A", "hot": "#FF6B1A", "core": "#FFC24B", "mode": "radial",
                        "center": (0.0, -1.2, 6.6), "radius": 8.0, "fade": (0.98, 0.66), "base_mix": 0.25})
    molten = P.faction_zone("unmade", "molten", glow=True,
                            emit={"color": "#C8400C", "hot": "#FF6B1A", "core": "#FFC24B", "mode": "radial",
                                  "center": (0.0, -1.5, 7.0), "radius": 9.0, "base_mix": 0.3})
    core = P.faction_zone("unmade", "molten", glow=True,
                          emit={"color": "#FFC24B", "hot": "#FFE6A8", "core": "#FFF3D6", "mode": "radial",
                                "center": core_c, "radius": 0.9, "base_mix": 0.5})
    obsidian = P.faction_zone("unmade", "obsidian", planes=0.16, parts=0.1, edge=1.0, edge_width=0.04,
                              edge_breakup=0.25, cavity=0.6, cavity_width=0.03, brush_freq=1.2,
                              light="#6A6680")
    ichor = P.faction_zone("unmade", "ichor", glow=True)
    return {"slag": slag, "limb": limb_, "crust": crust, "iron": iron, "steel": steel, "blade": blade, "edge": edge_,
            "molten": molten, "lava": lava, "core": core, "obsidian": obsidian, "ichor": ichor}


def decals():
    import gfa_paint as P
    teal = {"color": "#2FBFA8", "core": "#B8FFE8"}
    hot = {"color": "#FF6B1A", "core": "#FFC24B"}
    out = []
    spec = [  # (origin, normal, direction deg, length, seed, emit, width)
        ((2.2, -2.55, 7.7), (0.4, -1.0, 0.25), -70, 2.6, 1, teal, 0.075),
        ((-2.5, -2.2, 6.4), (-0.5, -1.0, 0.1), 250, 2.2, 2, teal, 0.075),
        ((0.6, 1.3, 10.3), (0.0, 0.3, 1.0), 20, 3.2, 3, teal, 0.08),
        ((-0.8, 3.0, 7.8), (0.0, 1.0, 0.2), -100, 2.6, 4, teal, 0.075),
        ((1.9, -1.8, 4.4), (0.4, -1.0, 0.0), -60, 1.5, 7, teal, 0.06),
        ((3.6, 0.9, 8.9), (0.5, 0.3, 1.0), 200, 2.0, 8, teal, 0.07),
        ((0.0, -0.9, 9.3), (0.0, -0.35, 1.0), 180, 2.6, 11, hot, 0.085),
        ((-0.6, -2.0, 4.7), (0.0, -1.0, 0.1), -90, 1.6, 12, hot, 0.07),
        ((-3.3, -0.9, 9.6), (-0.2, -0.3, 1.0), 160, 1.8, 13, hot, 0.07),
    ]
    for o, nrm, ang, L, sd, em, w in spec:
        lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.16, jag=0.5,
                              branches=2, branch_len=0.45, depth=2)
        out.append(P.decal_lines(lines, frame_at(o, nrm), w, zones=["slag"], color=em["color"], rim="#07060A",
                                 rim_width=w * 2.6, emit=em, depth=(-1.4, 1.4), facing=0.3))
    # the limbs: a FEW BOLD cracks (wide, long steps, one short branch) instead of fine webs, one per limb
    # read from the game camera: molten on the creature's left, Unmade teal on its right
    limbs = [  # (origin, normal, direction deg, length, seed, emit)
        ((5.35, -1.35, 4.3), (0.7, -0.7, 0.15), -80, 2.4, 21, hot),        # forearm L
        ((-5.45, -1.35, 4.2), (-0.7, -0.7, 0.15), -100, 2.4, 22, teal),    # forearm R
        ((4.45, -1.15, 7.2), (0.45, -1.0, 0.15), -95, 2.0, 23, hot),       # upper arm / bicep L
        ((-4.45, -1.15, 7.2), (-0.45, -1.0, 0.15), -85, 2.0, 24, teal),    # upper arm / bicep R
        ((3.35, -0.55, 3.2), (0.6, -0.8, 0.0), -75, 1.9, 25, teal),        # thigh L
        ((-3.3, -0.85, 2.9), (-0.6, -0.8, 0.0), -105, 1.9, 26, hot),       # thigh / knee R
    ]
    for o, nrm, ang, L, sd, em in limbs:
        lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.3, jag=0.35,
                              branches=1, branch_len=0.4, depth=1)
        out.append(P.decal_lines(lines, frame_at(o, nrm), 0.13, zones=["limb", "slag"], color=em["color"],
                                 rim="#07060A", rim_width=0.3, emit=em, depth=(-1.4, 1.4), facing=0.3))
    return out


# ---- figure / ground passes ------------------------------------------------------------------------------
# The slag (#2B201B) is the same value and hue as the Cinder Wastes floor (#3A2C24): lit by the toon ramp
# it lands right on the floor value, so only the ink separated the body. Two painted passes fix that:
#   * TOP PLANES: planes facing up (what the 55 deg camera mostly sees) are lifted toward the slag light
#     #5E4434, with a brushy break-up of the boundary. The lift multiplies, so the painted cavity darks stay
#     dark, and it skips texels that are already light (the edge strokes);
#   * MOLTEN UNDERGLOW: the lowest metres of the body (feet, shins, fists near the ground) and the faces
#     turned down glow in the emissive in two broken painted bands, a dim molten red cooling upward over a
#     hot orange line at the ground, and the base colour under them warms to a hot-slag red: the body
#     stands in its own heat.
# The same pass paints the EDGE STROKES of slag, limb, iron and steel (their painter strokes are off): only
# creases that really bend (slag and limbs: over 40 deg, so the triangles of a lump draw no web), only the
# texel's OWN part's creases (the painter measures to any part, so every rivet painted a light halo on its
# plate), weighted toward up-facing planes (a band gets one stroke along its top, not a line on every bevel).
# gfa_paint.paint has no normal- or height-driven pass and stays unchanged (other assets build with it), so
# this build wraps it for its one paint call (extra_paint_passes): the zones paint as usual, these passes
# run, then the decals go on top (the decal loop is the one from gfa_paint.paint).
SLAG_EDGE = {"color": "#8C6A52", "width": 0.11, "breakup": 0.32, "up": (-0.1, 0.5), "amount": 1.0, "min_angle": 40.0}
EXTRAS = {  # zone -> top-plane lift (target colour, amount), underglow strength, edge stroke
    "slag": {"top": ("#5E4434", 0.85), "under": 1.0, "edge": SLAG_EDGE},
    "limb": {"top": ("#5E4434", 0.8), "under": 1.0, "edge": dict(SLAG_EDGE, width=0.1, amount=0.9)},
    "iron": {"edge": {"color": "#78727B", "width": 0.13, "breakup": 0.18, "up": (-0.25, 0.45), "amount": 0.9,
                      "min_angle": 20.0}},
    "steel": {"edge": {"color": "#C4BAAC", "width": 0.09, "breakup": 0.18, "up": (-0.25, 0.45), "amount": 0.9,
                       "min_angle": 20.0}},
}
UNDER = {"rim": "#C8400C", "hot": "#FF6B1A", "tint": "#6E2410", "height": (2.0, 0.15), "down": 0.6,
         "down_below": 7.0, "warm_emit": 0.4}


def part_crease_points(obj, min_angle, spacing=0.002, sharp_only_below=60.0):
    """Convex crease samples of obj grouped by part id {part: [Vector, ...]}. The painter's rule for which
    edges count (gfa_paint.edge_points), but an edge counts only inside ONE part: rivets, chain links and
    crossguards never paint a light halo onto the plate or the slag they sit on."""
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
    """Distance from each texel (pos, part) to the nearest convex crease of its OWN part."""
    import numpy as np
    d = np.full(len(pos), cap, dtype=np.float32)
    for pid in np.unique(part):
        pts = crease.get(int(pid))
        if pts:
            idx = np.nonzero(part == pid)[0]
            d[idx] = P._kd_dist(pts, pos[idx], cap)
    return d


def paint_extras(P, maps, zones_order, recipes_, base, emis, scale, obj, seed=0):
    import numpy as np
    pos = maps["pos"] / scale                                    # real metres (the paint runs at 1/8 scale)
    Z = maps["zone"]
    wobble = P.spread01(P.fbm(maps["pos"], 30.0, 2, seed=seed + 5))   # the painter's own stroke wobble / dabs
    dabs = P.spread01(P.fbm(maps["pos"], 11.0, 2, seed=seed + 6))
    crease = {}                                                  # min_angle -> {part: convex crease samples}
    for zname, ex in EXTRAS.items():
        if zname not in zones_order:
            continue
        m = Z == zones_order.index(zname)
        if not m.any():
            continue
        p, nz = pos[m], maps["snrm"][m, 2]
        c = base[m]
        brush = P.spread01(P.fbm(p, 0.55, 2, seed=seed + 501))  # ~2 m brush patches
        if ex.get("top"):
            col, amt = ex["top"]
            b0 = P.hex3(recipes_[zname]["base"])
            ratio = P.hex3(col) / np.maximum(b0, 1e-3)
            # three painted values per form: top planes fully lifted, side planes 40 % (lit, a plain side plane
            # lands on the floor value), undersides not at all
            nb = nz + (brush - 0.5) * 0.35
            k = 0.4 * P.smoothstep(-0.3, 0.05, nb) + 0.6 * P.smoothstep(0.3, 0.52, nb)
            lum = c @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
            k = k * amt * (1.0 - P.smoothstep(0.2, 0.36, lum))
            c = c * (1.0 + (ratio - 1.0)[None, :] * k[:, None])
        ed = ex.get("edge")
        if ed:
            if ed["min_angle"] not in crease:
                crease[ed["min_angle"]] = part_crease_points(obj, ed["min_angle"])
            d = part_edge_dist(P, crease[ed["min_angle"]], maps["pos"][m], maps["part"][m])
            ew = ed["width"] * scale * (0.35 + 1.1 * wobble[m])
            k = P.smoothstep(ew, ew * 0.3, d)
            k = k * P.smoothstep(ed["breakup"] - 0.12, ed["breakup"] + 0.12, dabs[m])
            k = k * P.smoothstep(ed["up"][0], ed["up"][1], nz) * ed["amount"]
            c = P.mix(c, P.hex3(ed["color"]), k)
        if ex.get("under"):
            z0, z1 = UNDER["height"]
            h = np.clip((z0 - p[:, 2]) / (z0 - z1), 0.0, 1.0)       # linear: 1 at the ground, 0 at z0
            down = P.smoothstep(-0.15, -0.65, nz) * P.smoothstep(UNDER["down_below"], UNDER["down_below"] - 2.0, p[:, 2])
            heat = np.maximum(h, down * UNDER["down"])
            brush2 = P.spread01(P.fbm(p, 0.8, 2, seed=seed + 502))
            warm = P.smoothstep(0.3, 0.55, heat + (brush2 - 0.5) * 0.45)    # painted bands, not an airbrushed fade
            hot = P.smoothstep(0.9, 0.97, h + (brush2 - 0.5) * 0.08)       # a hot line along the ground only
            c = P.mix(c, P.hex3(UNDER["tint"]), warm * 0.6)
            c = P.mix(c, P.hex3(UNDER["rim"]), hot * 0.35)
            e = P.mix(np.repeat(P.hex3(UNDER["rim"])[None] * UNDER["warm_emit"], len(p), 0) * warm[:, None],
                      P.hex3(UNDER["hot"]), hot)
            emis[m] = np.maximum(emis[m], e * ex["under"])
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
def extra_paint_passes(scale, obj):
    """Within the block, gfa_paint.paint also runs paint_extras() (between the zones and the decals).
    obj = the mesh being painted (its crease edges are sampled at the paint scale, like the painter's)."""
    import numpy as np
    import gfa_paint as P
    orig = P.paint

    def paint(maps, zones_order, recipes_, dist_convex, dist_concave, decals=(), seed=0):
        base, emis = orig(maps, zones_order, recipes_, dist_convex, dist_concave, (), seed)
        paint_extras(P, maps, zones_order, recipes_, base, emis, scale, obj, seed=seed)
        apply_decals(P, maps, zones_order, base, emis, decals)
        return np.clip(base, 0, 1), np.clip(emis, 0, 1)

    P.paint = paint
    try:
        yield
    finally:
        P.paint = orig


# ---- rig ----------------------------------------------------------------------------------------------

def rig_table():
    door = hm(DOOR_HINGE_UP)
    t = [("root", None, PIV["root"]), ("pelvis", "root", PIV["pelvis"]), ("spine_01", "pelvis", PIV["spine_01"]),
         ("spine_02", "spine_01", PIV["spine_02"]), ("head", "spine_02", tuple(HEAD_PIVOT)),
         ("door", "head", tuple(door)), ("crown", "head", tuple(CROWN_C), tuple(CROWN_AXIS)),
         ("crown_spin", "crown", tuple(CROWN_C), tuple(CROWN_AXIS))]
    for s_ in ("L", "R"):
        t += [("upperarm_" + s_, "spine_02", PIV["upperarm_" + s_]),
              ("lowerarm_" + s_, "upperarm_" + s_, PIV["lowerarm_" + s_]),
              ("hand_" + s_, "lowerarm_" + s_, PIV["hand_" + s_]),
              ("thigh_" + s_, "pelvis", PIV["thigh_" + s_]), ("shin_" + s_, "thigh_" + s_, PIV["shin_" + s_]),
              ("foot_" + s_, "shin_" + s_, PIV["foot_" + s_]),
              ("arm2_upper_" + s_, "spine_02", PIV["arm2_upper_" + s_]),
              ("arm2_lower_" + s_, "arm2_upper_" + s_, PIV["arm2_lower_" + s_]),
              ("arm2_hand_" + s_, "arm2_lower_" + s_, PIV["arm2_hand_" + s_])]
    return t


def sockets(arm):
    import gfa_rig as RIG
    core = hm((HC.x, HC.y - 0.45, 7.17))
    mouth = hm((0.0, DOOR_Y - 0.15, 7.2))
    socks = [("spine_02", "hit_center", (0.0, -0.6, 7.2)), ("head", "fx_core", core), ("head", "fx_mouth", mouth),
             ("head", "attack_origin", mouth), ("crown", "head_top", CROWN_C + Vector((0, 0, 2.6))),
             ("crown", "crown_center", CROWN_C), ("hand_R", "impact_R", (-5.3, -3.0, 0.3)),
             ("hand_L", "impact_L", (5.1, -3.3, 0.6)), ("foot_L", "foot_L_fx", (2.5, -0.2, 0.0)),
             ("foot_R", "foot_R_fx", (-2.5, -0.5, 0.0)),
             ("arm2_hand_L", "arm2_tip_L", Vector(PIV["arm2_hand_L"]) + Vector((0.1, -0.9, 1.4))),
             ("arm2_hand_R", "arm2_tip_R", Vector(PIV["arm2_hand_R"]) + Vector((-0.1, -0.9, 1.4)))]
    for sx, name, h_, dx in ((1, "chimney_L", 2.9, 0.3), (-1, "chimney_R", 2.3, 0.22)):
        d = Vector((sx * dx, 0.45, 1.0)).normalized()
        socks.append(("spine_02", name, Vector((sx * 1.3, 1.75, 9.6)) + d * (h_ + 0.1)))
    out = {}
    for bone, name, pos in socks:
        RIG.add_socket(arm, bone, name, tuple(pos), size=0.4)
        out[name] = {"bone": bone, "blender_pos": [round(v, 3) for v in pos],
                     "gltf_pos": [round(v, 3) for v in C.blender_to_gltf(pos)]}
    return out


# ---- clips ----------------------------------------------------------------------------------------------
# Every clip keys EVERY bone (gfa_rig.keyed_clip / cycle_clip), so each clip fully states its phase:
# phase 1 (Molten Court) clips hold arm2_upper_* at scale 0.001 and the door shut; phase 2+ clips (Slagfall,
# Final Pour) hold the extra arms out and the door burst open. The crown's spin is engine-driven on the
# crown_spin joint (README), so clips keep crown_spin at identity and blends never whip it backwards.
FPS = 30
HIDE = 0.001


def state(phase):
    if phase == 1:
        return {"arm2_upper_L": {"scale": HIDE}, "arm2_upper_R": {"scale": HIDE}, "door": {"rot": (0, 0, 0)}}
    return {"arm2_upper_L": {"scale": 1.0}, "arm2_upper_R": {"scale": 1.0}, "door": {"rot": (112, 0, 7)}}


def pose(*parts):
    """Merge pose dicts (later wins per bone channel)."""
    out = {}
    for p in parts:
        for b, tr in p.items():
            out.setdefault(b, {}).update(tr)
    return out


def K(phase, *poses):
    return pose(state(phase), *poses)


def sym(bone_l, rot=(0, 0, 0), loc=None):
    """A left/right pair: the right side mirrors yaw (Y) and roll (Z) and the X location."""
    out = {bone_l: {"rot": rot}}
    rr = {"rot": (rot[0], -rot[1], -rot[2])}
    if loc is not None:
        out[bone_l]["loc"] = loc
        rr["loc"] = (-loc[0], loc[1], loc[2])
    out[bone_l[:-1] + "R"] = rr
    return out


def addp(pose_a, pose_b):
    """Add two poses channel by channel (rotations and locations sum; scale from b, else a)."""
    out = {}
    for b in set(pose_a) | set(pose_b):
        A, Bb = pose_a.get(b, {}), pose_b.get(b, {})
        d = {}
        for ch in ("rot", "loc"):
            if ch in A or ch in Bb:
                d[ch] = tuple(x + y for x, y in zip(A.get(ch, (0, 0, 0)), Bb.get(ch, (0, 0, 0))))
        if "scale" in A or "scale" in Bb:
            d["scale"] = Bb.get("scale", A.get("scale"))
        out[b] = d
    return out


def breathe(t, amp=1.0, p2=False):
    w = 2 * math.pi * t
    s1, s2 = math.sin(w), math.sin(2 * w)
    p = {"root": {"loc": (0, -0.05 * amp * (1 - math.cos(w)), 0)},
         "spine_01": {"rot": (1.2 * amp * math.sin(w + 0.5), 0, 0)},
         "spine_02": {"rot": (-2.2 * amp * s1, 1.2 * amp * math.sin(w + 1.3), 0), "loc": (0, 0.06 * amp * s1, 0)},
         "head": {"rot": (2.5 * amp * math.sin(w + 0.9), 2.5 * amp * math.sin(w + 2.0), 1.0 * s2)},
         "crown": {"loc": (0, 0.12 * math.sin(w + 1.6), 0), "rot": (1.5 * math.sin(w + 0.4), 0, 1.5 * math.sin(w + 2.4))},
         "door": {"rot": (1.2 * (1 - math.cos(2 * w)), 0, 0)}}
    p.update(sym("upperarm_L", (1.5 * amp * math.sin(w + 0.3), 0, 1.8 * amp * s1)))
    p.update(sym("lowerarm_L", (-2.0 * amp * math.sin(w + 0.8), 0, 0)))
    if p2:
        p["door"] = {"rot": (112 + 4 * math.sin(w + 0.5), 0, 7 + 3 * s1)}
        p.update({"arm2_upper_L": {"rot": (4 * math.sin(w + 0.6), 3 * s2, 5 * math.sin(w + 1.1))},
                  "arm2_upper_R": {"rot": (4 * math.sin(w + 2.2), -3 * s2, -5 * math.sin(w + 2.7))},
                  "arm2_lower_L": {"rot": (-6 * math.sin(w + 1.4), 0, 4 * math.sin(2 * w + 0.5))},
                  "arm2_lower_R": {"rot": (-6 * math.sin(w + 3.0), 0, -4 * math.sin(2 * w + 1.0))},
                  "arm2_hand_L": {"rot": (8 * math.sin(2 * w + 0.3), 0, 6 * s1)},
                  "arm2_hand_R": {"rot": (8 * math.sin(2 * w + 1.9), 0, -6 * math.sin(w + 1.0))}})
    return p


def gait(t, stride=18.0, p2=False):
    """One full stride (left step, then right step) for t in [0, 1)."""
    w = 2 * math.pi * t
    leg = 3.4
    p = {}
    for side, ph in (("L", 0.0), ("R", math.pi)):
        ww = w + ph
        th = -stride * math.cos(ww)                  # + = foot back (the stance pushes it back)
        swing = max(0.0, -math.sin(ww))              # second half: the foot is in the air
        knee = 38.0 * swing
        p["thigh_" + side] = {"rot": (th - 8.0 * swing, 0, 0)}
        p["shin_" + side] = {"rot": (knee, 0, 0)}
        p["foot_" + side] = {"rot": (-(th + knee) * 0.75 + 6 * swing, 0, 0)}
    th_st = stride * math.cos(w)
    drop = leg * (1 - math.cos(math.radians(th_st)))
    stomp = 0.12 * max(0.0, math.cos(2 * w)) ** 6
    p["root"] = {"loc": (0.32 * math.sin(w), -drop - stomp + 0.05, 0)}
    p["pelvis"] = {"rot": (0, 6 * math.cos(w), -4 * math.sin(w))}
    p["spine_01"] = {"rot": (3, -3 * math.cos(w), 2 * math.sin(w))}
    p["spine_02"] = {"rot": (5 + 2.5 * math.sin(2 * w + 0.6), -5 * math.cos(w), 3 * math.sin(w))}
    p["head"] = {"rot": (-3 - 2.5 * math.sin(2 * w + 1.2), 4 * math.cos(w), -2 * math.sin(w))}
    p["crown"] = {"loc": (0, 0.14 * math.sin(2 * w + 1.8), 0), "rot": (3 * math.sin(2 * w + 1.2), 0, 2 * math.sin(w + 0.6))}
    p["door"] = {"rot": (3.5 * (1 - math.cos(2 * w)) / 2, 0, 0)}
    arm = 16.0
    p["upperarm_L"] = {"rot": (arm * math.cos(w) - 4, 0, 3 + 2 * math.sin(w))}
    p["upperarm_R"] = {"rot": (-arm * math.cos(w) - 4, 0, -3 + 2 * math.sin(w))}
    p["lowerarm_L"] = {"rot": (8 * math.cos(w - 0.7) - 6, 0, 0)}
    p["lowerarm_R"] = {"rot": (-8 * math.cos(w - 0.7) - 6, 0, 0)}
    if p2:
        p["door"] = {"rot": (112 + 7 * math.sin(2 * w + 0.4), 0, 7 + 4 * math.sin(w))}
        p["arm2_upper_L"] = {"rot": (-10 * math.cos(w) + 4, 0, 6 * math.sin(2 * w))}
        p["arm2_upper_R"] = {"rot": (10 * math.cos(w) + 4, 0, -6 * math.sin(2 * w + 0.5))}
        p["arm2_lower_L"] = {"rot": (-8 * math.sin(2 * w + 0.8), 0, 0)}
        p["arm2_lower_R"] = {"rot": (-8 * math.sin(2 * w + 2.0), 0, 0)}
        p["arm2_hand_L"] = {"rot": (10 * math.sin(2 * w + 1.4), 0, 0)}
        p["arm2_hand_R"] = {"rot": (10 * math.sin(2 * w + 2.6), 0, 0)}
    return p


def shake(k, amp=1.0):
    """A small deterministic tremble (index k), added on top of a held pose."""
    r = random.Random(1000 + k)
    return {"spine_02": {"rot": (amp * r.uniform(-1, 1), amp * r.uniform(-1, 1), amp * r.uniform(-1, 1))},
            "head": {"rot": (amp * 1.5 * r.uniform(-1, 1), amp * 1.5 * r.uniform(-1, 1), 0)},
            "crown": {"loc": (0, amp * 0.06 * r.uniform(-1, 1), 0)}}


# key poses (phase-free; K(phase, ...) adds the phase state). Rotations in degrees in the bone frame:
# +X pitches forward (a hanging limb swings BACK), +Y yaws left, +Z rolls the left side up.
DIP = pose({"root": {"loc": (0, -0.3, 0)}, "spine_02": {"rot": (7, 0, 0)}, "spine_01": {"rot": (3, 0, 0)},
            "head": {"rot": (6, 0, 0)}}, sym("upperarm_L", (12, 0, 4)), sym("lowerarm_L", (-6, 0, 0)),
           sym("thigh_L", (-8, 0, 0)), sym("shin_L", (14, 0, 0)), sym("foot_L", (-6, 0, 0)))
OVERHEAD = pose({"root": {"loc": (0, 0.25, 0.25)}, "spine_01": {"rot": (-6, 0, 0)}, "spine_02": {"rot": (-13, 0, 0)},
                 "head": {"rot": (-16, 0, 0)}, "crown": {"loc": (0, 0.35, 0)}},
                sym("upperarm_L", (-162, 0, 16)), sym("lowerarm_L", (-42, 0, 0)), sym("hand_L", (-10, 0, 0)),
                sym("thigh_L", (4, 0, 0)), sym("shin_L", (-2, 0, 0)))
OVERHEAD2 = pose(OVERHEAD, {"spine_02": {"rot": (-15, 0, 0)}, "head": {"rot": (-19, 0, 0)}})
SLAM = pose({"root": {"loc": (0, -0.75, 0.5)}, "spine_01": {"rot": (12, 0, 0)}, "spine_02": {"rot": (27, 0, 0)},
             "head": {"rot": (6, 0, 0)}, "crown": {"loc": (0, -0.25, 0.1)}},
            sym("upperarm_L", (-58, 0, 6)), sym("lowerarm_L", (-18, 0, 0)), sym("hand_L", (8, 0, 0)),
            sym("thigh_L", (-20, 0, 0)), sym("shin_L", (34, 0, 0)), sym("foot_L", (-14, 0, 0)))
FLINCH = pose({"root": {"loc": (0, -0.12, -0.2)}, "spine_02": {"rot": (-9, 6, -3)}, "spine_01": {"rot": (-3, 0, 0)},
               "head": {"rot": (-13, -10, 4)}, "crown": {"loc": (0.1, 0.35, 0), "rot": (6, 0, -5)}},
              sym("upperarm_L", (6, 0, 9)), sym("lowerarm_L", (-10, 0, 0)))
ROAR = pose({"root": {"loc": (0, 0.12, -0.15)}, "spine_01": {"rot": (-4, 0, 0)}, "spine_02": {"rot": (-12, 0, 0)},
             "head": {"rot": (-24, 0, 0)}, "crown": {"loc": (0, 0.6, 0)}, "door": {"rot": (104, 0, 0)}},
            sym("upperarm_L", (-38, 0, 42)), sym("lowerarm_L", (-30, 0, 0)), sym("hand_L", (-10, 0, 0)))
HUNCH = pose({"root": {"loc": (0, -0.35, 0)}, "spine_01": {"rot": (6, 0, 0)}, "spine_02": {"rot": (16, 0, 0)},
              "head": {"rot": (18, 0, 0)}, "crown": {"loc": (0, -0.3, 0)}},
             sym("upperarm_L", (-38, 0, -14)), sym("lowerarm_L", (-40, 0, 0)))
A2_UP = {"arm2_upper_L": {"rot": (-30, 0, 18)}, "arm2_upper_R": {"rot": (-30, 0, -18)},
         "arm2_lower_L": {"rot": (-20, 0, 0)}, "arm2_lower_R": {"rot": (-20, 0, 0)}}
A2_DOWN = {"arm2_upper_L": {"rot": (55, 0, -10)}, "arm2_upper_R": {"rot": (55, 0, 10)},
           "arm2_lower_L": {"rot": (30, 0, 0)}, "arm2_lower_R": {"rot": (30, 0, 0)},
           "arm2_hand_L": {"rot": (20, 0, 0)}, "arm2_hand_R": {"rot": (20, 0, 0)}}
A2_TUCK = {"arm2_upper_L": {"rot": (40, 20, -30)}, "arm2_upper_R": {"rot": (40, -20, 30)},
           "arm2_lower_L": {"rot": (60, 0, 0)}, "arm2_lower_R": {"rot": (60, 0, 0)}}


def crown_on_ground(arm, body_pose, where, tilt_deg):
    """The crown's local loc/rot (degrees) that put it at world `where` (ring centre), tilted by tilt_deg
    (XYZ), when the rest of the body holds `body_pose`: solved through the pose-bone matrix."""
    import gfa_rig as RIG
    from mathutils import Euler
    RIG.apply_pose(arm, body_pose)
    bpy.context.view_layer.update()
    pb = arm.pose.bones["crown"]
    rest = arm.data.bones["crown"].matrix_local
    tgt = Matrix.Translation(Vector(where)) @ Euler([math.radians(a) for a in tilt_deg], "XYZ").to_matrix().to_4x4()         @ rest.to_3x3().to_4x4()
    pb.matrix = arm.matrix_world.inverted() @ tgt
    bpy.context.view_layer.update()
    out = {"loc": tuple(pb.location), "rot": tuple(math.degrees(a) for a in pb.rotation_euler)}
    RIG.reset_pose(arm)
    return out


def build_clips(arm):
    import gfa_rig as RIG
    clips = {}

    def one(name, keys, events=None, phase=None):
        RIG.keyed_clip(arm, KEY, name, keys)
        clips[name] = {"frames": keys[-1][0], "seconds": round(keys[-1][0] / FPS, 3), "phase": phase,
                       "events_s": events or {}, "key_frames": sorted({f for f, _ in keys})}

    def loop(name, frames, fn, phase, extra=None):
        RIG.cycle_clip(arm, KEY, name, frames, fn)
        clips[name] = {"frames": frames, "seconds": round(frames / FPS, 3), "phase": phase, "loop": True}
        clips[name].update(extra or {})

    b2 = K(2, breathe(0.0, 1.3, True))              # the phase-2 rest (= idle_p2@loop at t = 0)
    # ---- loops
    loop("idle@loop", 96, lambda t: K(1, breathe(t)), 1)
    loop("move@loop", 72, lambda t: K(1, gait(t)), 1, {"move_cycle_m": 4.45})
    loop("idle_p2@loop", 144, lambda t: K(2, breathe((2 * t) % 1.0, 1.3, True)), 2)
    loop("move_p2@loop", 144, lambda t: K(2, gait((2 * t) % 1.0, 19.0, True)), 2, {"move_cycle_m": 9.4})
    # ---- the generic attack pair (the two-fisted ground pound), phase 1 and phase 2+
    for ph, sfx in ((1, ""), (2, "_p2")):
        a2u = A2_UP if ph == 2 else {}
        a2d = A2_DOWN if ph == 2 else {}
        base = b2 if ph == 2 else K(1)
        one("windup" + sfx, [(0, base), (9, K(ph, DIP, a2d)), (24, K(ph, OVERHEAD, a2u)), (30, K(ph, OVERHEAD2, a2u))],
            {"loaded": 1.0}, ph)
        one("attack" + sfx, [(0, K(ph, OVERHEAD2, a2u)), (5, K(ph, SLAM, a2d)), (8, K(ph, addp(SLAM, shake(1, 1.5)), a2d)),
                             (13, K(ph, SLAM, a2d)), (26, base)], {"impact": 0.167}, ph)
        one("hit" + sfx, [(0, base), (3, K(ph, FLINCH, a2u, {"door": {"rot": (14 if ph == 1 else 124, 0, 7 * (ph - 1))}})),
                          (15, base)], None, ph)
    # ---- Molten Court: strike_circle (the big ground pound, impact on the 1.2 s windup)
    one("strike_circle", [(0, K(1)), (10, K(1, DIP)), (28, K(1, OVERHEAD)), (31, K(1, OVERHEAD2)),
                          (36, K(1, SLAM, {"door": {"rot": (9, 0, 0)}})),
                          (39, K(1, addp(SLAM, shake(2, 2.0)), {"door": {"rot": (12, 0, 0)}})),
                          (44, K(1, SLAM)), (66, K(1))], {"impact": 1.2}, 1)
    # ---- slam_trail: the anvil slams (impact on the windup), the claw follows on the trail's second beat
    for ph, sfx, imp in ((1, "", 27), (2, "_p2", 26)):
        base = K(1) if ph == 1 else b2
        up_r = pose({"spine_02": {"rot": (-10, -16, -4)}, "spine_01": {"rot": (-4, -6, 0)}, "head": {"rot": (-12, 8, 0)},
                     "root": {"loc": (0, 0.15, 0.1)}},
                    {"upperarm_R": {"rot": (-168, 0, -14)}, "lowerarm_R": {"rot": (-40, 0, 0)},
                     "upperarm_L": {"rot": (18, 0, 10)}, "lowerarm_L": {"rot": (-12, 0, 0)}},
                    A2_UP if ph == 2 else {})
        up_r2 = pose(up_r, {"upperarm_R": {"rot": (-176, 0, -14)}})
        slam_r = pose({"spine_02": {"rot": (24, 14, 4)}, "spine_01": {"rot": (8, 6, 0)}, "head": {"rot": (6, -6, 0)},
                       "root": {"loc": (0, -0.6, 0.45)}},
                      {"upperarm_R": {"rot": (-55, 0, -4)}, "lowerarm_R": {"rot": (-16, 0, 0)},
                       "upperarm_L": {"rot": (-70, 0, 8)}, "lowerarm_L": {"rot": (-50, 0, 0)}},
                      sym("thigh_L", (-16, 0, 0)), sym("shin_L", (28, 0, 0)), sym("foot_L", (-12, 0, 0)),
                      A2_DOWN if ph == 2 else {})
        slam_l = pose(slam_r, {"spine_02": {"rot": (26, -12, -4)}, "upperarm_L": {"rot": (-56, 0, 6)},
                               "lowerarm_L": {"rot": (-14, 0, 0)}, "upperarm_R": {"rot": (-62, 0, -6)},
                               "lowerarm_R": {"rot": (-22, 0, 0)}})
        one("slam_trail" + sfx, [(0, base), (8, K(ph, DIP)), (imp - 5, K(ph, up_r)), (imp - 2, K(ph, up_r2)),
                                 (imp, K(ph, slam_r)), (imp + 3, K(ph, addp(slam_r, shake(3, 1.5)))),
                                 (imp + 6, K(ph, slam_l)), (imp + 9, K(ph, addp(slam_l, shake(4, 1.5)))),
                                 (imp + 14, K(ph, slam_l)), (imp + 34, base)],
            {"impact": round(imp / FPS, 3), "second_impact": round((imp + 6) / FPS, 3)}, ph)
        # radial: gather under the crown, then fling everything wide (the crown sprays slag)
        gather = pose(HUNCH, {"crown": {"loc": (0, -0.4, 0)}}, A2_TUCK if ph == 2 else {})
        fling = pose({"root": {"loc": (0, 0.2, -0.1)}, "spine_01": {"rot": (-5, 0, 0)}, "spine_02": {"rot": (-15, 0, 0)},
                      "head": {"rot": (-22, 0, 0)}, "crown": {"loc": (0, 0.9, 0)}},
                     sym("upperarm_L", (-42, 0, 58)), sym("lowerarm_L", (-18, 0, 0)), sym("hand_L", (-12, 0, 0)),
                     A2_UP if ph == 2 else {"door": {"rot": (12, 0, 0)}})
        one("radial" + sfx, [(0, base), (12, K(ph, gather)), (15, K(ph, fling)), (19, K(ph, addp(fling, shake(5, 1.2)))),
                             (27, K(ph, fling)), (48, base)], {"release": 0.5}, ph)
    # ---- the furnace face (phase 1): the door drops like a jaw, and the roar
    op = {"door": {"rot": (100, 0, 0)}, "head": {"rot": (-8, 0, 0)}, "crown": {"loc": (0, 0.2, 0)}}
    one("door_open", [(0, K(1)), (7, K(1, {"door": {"rot": (-3, 0, 0)}, "head": {"rot": (3, 0, 0)}})),
                      (17, K(1, op, {"door": {"rot": (108, 0, 0)}})), (21, K(1, op, {"door": {"rot": (96, 0, 0)}})),
                      (24, K(1, op))], {"open": 0.567}, 1)
    one("door_close", [(0, K(1, op)), (8, K(1, op, {"door": {"rot": (60, 0, 0)}})), (14, K(1, {"door": {"rot": (-4, 0, 0)}})),
                       (18, K(1, {"door": {"rot": (2, 0, 0)}})), (24, K(1))], {"shut": 0.467}, 1)
    one("roar", [(0, K(1)), (14, K(1, HUNCH, {"door": {"rot": (-2, 0, 0)}})), (24, K(1, ROAR))] +
        [(24 + 4 * k, K(1, addp(ROAR, shake(10 + k, 1.4)))) for k in range(1, 10)] + [(72, K(1))], {"peak": 0.8}, 1)
    # ---- phase changes
    burst = pose({"root": {"loc": (0, 0.2, -0.3)}, "spine_01": {"rot": (-6, 0, 0)}, "spine_02": {"rot": (-18, 0, 0)},
                  "head": {"rot": (-26, 0, 0)}, "crown": {"loc": (0, 1.1, 0)}, "door": {"rot": (128, 0, 12)}},
                 sym("upperarm_L", (-48, 0, 62)), sym("lowerarm_L", (-20, 0, 0)), A2_UP)
    keys = [(0, K(1)), (14, K(1, HUNCH))]
    keys += [(14 + 3 * k, K(1, addp(HUNCH, shake(20 + k, 1.2 + 0.25 * k)))) for k in range(1, 9)]
    keys += [(41, K(1, HUNCH, {"door": {"rot": (20, 0, 0)}})),
             (44, K(2, burst, {"arm2_upper_L": {"rot": (-30, 0, 18), "scale": 1.18},
                               "arm2_upper_R": {"rot": (-30, 0, -18), "scale": 1.18}})),
             (50, K(2, burst)), (54, K(2, addp(burst, shake(40, 1.5)))), (62, K(2, burst)), (90, b2)]
    one("phase2", keys, {"burst": round(44 / FPS, 3)}, "1to2")
    p3 = pose(ROAR, {"door": {"rot": (126, 0, 10)}, "crown": {"loc": (0, 1.0, 0)}}, A2_UP,
              sym("upperarm_L", (-120, 0, 38)), sym("lowerarm_L", (-40, 0, 0)))
    one("phase3", [(0, b2), (12, K(2, HUNCH)), (22, K(2, p3))] +
        [(22 + 4 * k, K(2, addp(p3, shake(50 + k, 1.6)))) for k in range(1, 8)] + [(72, b2)], {"peak": 0.733}, "2to3")
    # ---- Slagfall / Final Pour attacks (phase-2 body)
    sweep_load = pose({"spine_02": {"rot": (-4, -32, -6)}, "spine_01": {"rot": (0, -10, 0)}, "head": {"rot": (-6, 18, 0)},
                       "root": {"loc": (0, 0.05, 0)}},
                      {"upperarm_R": {"rot": (-38, 0, -72)}, "lowerarm_R": {"rot": (-24, 0, 0)},
                       "upperarm_L": {"rot": (-22, 0, 16)}}, A2_UP)
    sweep_hit = pose({"spine_02": {"rot": (14, 30, 4)}, "spine_01": {"rot": (4, 10, 0)}, "head": {"rot": (4, -14, 0)},
                      "root": {"loc": (0, -0.3, 0.2)}},
                     {"upperarm_R": {"rot": (-72, 38, -12)}, "lowerarm_R": {"rot": (-12, 0, 0)},
                      "upperarm_L": {"rot": (14, 0, 22)}}, A2_DOWN)
    sweep_end = pose(sweep_hit, {"spine_02": {"rot": (10, 42, 4)}, "upperarm_R": {"rot": (-66, 58, 4)}})
    one("strike_cone", [(0, b2), (9, K(2, DIP)), (20, K(2, sweep_load)),
                        (26, K(2, sweep_load, {"spine_02": {"rot": (-4, -36, -6)}})), (30, K(2, sweep_hit)),
                        (34, K(2, sweep_end)), (39, K(2, addp(sweep_end, shake(60, 1.2)))), (60, b2)],
        {"impact": 1.0}, 2)
    rear = pose({"root": {"loc": (0, 0.2, -0.3)}, "spine_02": {"rot": (-15, 0, 0)}, "spine_01": {"rot": (-5, 0, 0)},
                 "head": {"rot": (-22, 0, 0)}, "crown": {"loc": (0, 0.5, 0)}, "door": {"rot": (135, 0, 5)}},
                sym("upperarm_L", (-40, 0, 36)), A2_UP)
    pour = pose({"root": {"loc": (0, -0.55, 0.6)}, "spine_02": {"rot": (26, 0, 0)}, "spine_01": {"rot": (8, 0, 0)},
                 "head": {"rot": (34, 0, 0)}, "crown": {"loc": (0, -0.2, 0.3)}, "door": {"rot": (150, 0, 8)}},
                sym("upperarm_L", (-52, 0, 18)), sym("lowerarm_L", (-10, 0, 0)), sym("thigh_L", (-14, 0, 0)),
                sym("shin_L", (24, 0, 0)), sym("foot_L", (-10, 0, 0)), A2_DOWN)
    one("strike_line", [(0, b2), (10, K(2, DIP)), (26, K(2, rear)), (30, K(2, pour))] +
        [(30 + 5 * k, K(2, addp(pour, shake(70 + k, 0.8)))) for k in range(1, 7)] + [(84, b2)],
        {"impact": 1.0, "pour_end": 2.0}, 2)
    raise_all = pose({"root": {"loc": (0, 0.15, 0)}, "spine_02": {"rot": (-10, 0, 0)}, "head": {"rot": (-12, 0, 0)}},
                     sym("upperarm_L", (-150, 0, 30)), sym("lowerarm_L", (-30, 0, 0)),
                     {"arm2_upper_L": {"rot": (-50, 0, 30)}, "arm2_upper_R": {"rot": (-50, 0, -30)},
                      "arm2_lower_L": {"rot": (-30, 0, 0)}, "arm2_lower_R": {"rot": (-30, 0, 0)}})
    whip = pose({"root": {"loc": (0, -0.35, 0.2)}, "spine_02": {"rot": (14, 0, 0)}, "head": {"rot": (8, 0, 0)}},
                sym("upperarm_L", (-40, 0, 72)), sym("lowerarm_L", (-8, 0, 0)), sym("hand_L", (18, 0, 0)),
                {"arm2_upper_L": {"rot": (20, 0, 45)}, "arm2_upper_R": {"rot": (20, 0, -45)},
                 "arm2_lower_L": {"rot": (10, 0, 0)}, "arm2_lower_R": {"rot": (10, 0, 0)}})
    one("pools", [(0, b2), (8, K(2, HUNCH, A2_TUCK)), (21, K(2, raise_all)),
                  (26, K(2, raise_all, {"spine_02": {"rot": (-13, 0, 0)}})), (30, K(2, whip)),
                  (34, K(2, addp(whip, shake(80, 1.2)))), (54, b2)], {"release": 1.0}, 2)
    belch = pose({"root": {"loc": (0, 0.05, 0.35)}, "spine_02": {"rot": (8, 0, 0)},
                  "head": {"rot": (-16, 0, 0), "loc": (0, 0, 0.5)}, "door": {"rot": (142, 0, 4)},
                  "crown": {"loc": (0, 0.3, 0.2)}}, sym("upperarm_L", (-18, 0, 20)), A2_UP)
    belch2 = pose(belch, {"head": {"rot": (-8, 0, 0), "loc": (0, 0, 0.2)}, "door": {"rot": (104, 0, 10)}})
    one("summon", [(0, b2), (12, K(2, HUNCH, A2_TUCK)), (19, K(2, belch)), (25, K(2, belch2)), (30, K(2, belch)),
                   (36, K(2, belch2)), (41, K(2, belch)), (60, b2)], {"spawn": [0.633, 1.0, 1.367]}, 2)
    # ---- death (the boss always dies in Final Pour: phase-2 body). Knees buckle, it falls forward onto its
    # fists, the crown slides off the furnace and the molten arms sag.
    stagger = pose({"root": {"loc": (0, -0.1, -0.6)}, "spine_02": {"rot": (-16, 8, -6)}, "head": {"rot": (-22, 0, 8)},
                    "crown": {"loc": (0.2, 0.5, 0), "rot": (10, 0, -8)}, "door": {"rot": (140, 0, 14)}},
                   sym("upperarm_L", (-30, 0, 40)), sym("lowerarm_L", (-30, 0, 0)), A2_UP)
    buckle = pose({"root": {"loc": (0, -1.3, 0.1)}, "pelvis": {"rot": (8, 0, 0)}, "spine_02": {"rot": (22, -5, 4)},
                   "head": {"rot": (24, 0, -6)}, "crown": {"loc": (0.4, -0.3, 0.4), "rot": (18, 0, 14)},
                   "door": {"rot": (160, 0, 18)}},
                  sym("thigh_L", (-34, 0, 4)), sym("shin_L", (62, 0, 0)), sym("foot_L", (-26, 0, 0)),
                  sym("upperarm_L", (-18, 0, 10)), sym("lowerarm_L", (-20, 0, 0)), A2_DOWN)
    down = pose({"root": {"loc": (0, -1.95, 0.6), "rot": (12, 0, 0)}, "pelvis": {"rot": (6, 0, 0)},
                 "spine_02": {"rot": (32, 4, 6)}, "spine_01": {"rot": (8, 0, 0)}, "head": {"rot": (38, 0, -10)},
                 "crown": {"loc": (0.6, -2.3, 1.2), "rot": (38, 0, 24)}, "door": {"rot": (170, 0, 22)}},
                sym("thigh_L", (-46, 0, 6)), sym("shin_L", (84, 0, 0)), sym("foot_L", (-36, 0, 0)),
                sym("upperarm_L", (-46, 0, 14)), sym("lowerarm_L", (-8, 0, 0)), sym("hand_L", (20, 0, 0)),
                {"arm2_upper_L": {"rot": (70, 0, -30), "scale": 0.82}, "arm2_upper_R": {"rot": (70, 0, 30), "scale": 0.82},
                 "arm2_lower_L": {"rot": (50, 0, 0)}, "arm2_lower_R": {"rot": (50, 0, 0)}})
    down = pose(down, {"crown": crown_on_ground(arm, K(2, down), (1.6, -8.2, 0.55), (14, -8, 22))})
    slid = pose(down, {"crown": crown_on_ground(arm, K(2, down), (1.9, -8.6, 0.5), (8, -4, 30))})
    one("death", [(0, b2), (8, K(2, stagger)), (14, K(2, addp(stagger, shake(90, 2.0)))), (30, K(2, buckle)),
                  (38, K(2, addp(buckle, shake(91, 1.5)))), (54, K(2, down)),
                  (60, K(2, slid)), (66, K(2, down)), (105, K(2, down))],
        {"collapse": 1.8}, 2)
    return clips


ALIASES = {  # the brief's clip names -> the contract clip they duplicate (docs/art/ENEMIES.md section 6)
    "walk@loop": "move@loop", "ground_pound": "strike_circle", "sweep": "strike_cone", "furnace_open": "door_open",
    "phase2_idle@loop": "idle_p2@loop", "phase_transition": "phase2",
}


def clip_track(c):
    return "%s_%s" % (KEY, c)


# ---- review ---------------------------------------------------------------------------------------------

def _p2_pose(arm):
    import gfa_rig as RIG
    RIG.pose_at(arm, clip_track("idle_p2@loop"), 0)


def _p1_pose(arm):
    """Phase-1 idle, frame 0 (the bind pose shows the phase-2 arms: never review it as phase 1)."""
    import gfa_rig as RIG
    RIG.pose_at(arm, clip_track("idle@loop"), 0)


def _party(positions):
    """2.2 m hero mannequins facing the boss (at the origin)."""
    out = []
    for i, (x, y) in enumerate(positions):
        m = R.mannequin(aim_dir=(-x, -y, 0.0), name="GFA_HERO_%d" % i)
        m.location = (x, y, 0.0)
        out.append(m)
    bpy.context.view_layer.update()
    return out


def key_poses(info, n=5):
    """Up to n frames that tell a one-shot: the first and last frame, the events (impact, release, burst...),
    the loaded key just before the first event, then key frames spread between them."""
    keys = info["key_frames"]
    ev = []
    for v in info.get("events_s", {}).values():
        for t in (v if isinstance(v, list) else [v]):
            f = int(round(t * FPS))
            if keys[0] < f <= keys[-1]:
                ev.append(f)
    ev = sorted(set(ev))[:2]
    pick = {keys[0], keys[-1]} | set(ev)
    if ev:
        before = [k for k in keys if k < ev[0] - 1]
        if before:
            pick.add(before[-1])
    rest = [k for k in keys if k not in pick]
    while len(pick) < n and rest:
        pick.add(rest.pop(len(rest) // 2))
    pick = sorted(pick)
    return pick if len(pick) <= n else pick[:n - 1] + [keys[-1]]


def first_look_sheets(hero, ing, out_dir, work):
    """The two sheets the user sees first: the 3/4 hero shots and the in-game camera at true pixel size."""
    R.contact_sheet({"title": "The Slag King - Molten Court (phase 1) and Slagfall / Final Pour (phase 2+)",
                     "subtitle": "3/4 front, toon preview of the final textures; the crown spins in phase 2+ (engine)",
                     "width": 1560, "sections": [{"label": "", "height": 740, "images": [
                         {"path": hero[1], "label": "phase 1: door shut, two arms"},
                         {"path": hero[2], "label": "phase 2+: door burst, molten arms out"}]}]},
                    os.path.join(out_dir, KEY + "_34.png"), work)
    ppm22, ppm28 = SPEC.SCREEN_H / 22.0, SPEC.SCREEN_H / 28.0
    lay2 = {
        "title": "The Slag King - in-game camera at true pixel size",
        "subtitle": "orthographic, 55 deg pitch, yaw 0; 1560 x 860 crops of the 1080p frame; four 2.2 m hero mannequins",
        "width": 1600,
        "sections": [
            {"label": "Phase 1, 1 player (view height 22 m = %.1f px/m), 1x" % ppm22, "height": None,
             "images": [{"path": ing["p1_22"]["color"], "label": "phase 1, 22 m"}]},
            {"label": "Phase 2+, turned 28 deg toward a hero, 22 m, 1x", "height": None,
             "images": [{"path": ing["p2_22"]["color"], "label": "phase 2, 22 m"}]},
            {"label": "4 players (view height 28 m = %.1f px/m), 1x; and the game-size silhouettes (half size)" % ppm28,
             "height": None, "images": [{"path": ing["p1_28"]["color"], "label": "phase 1, 28 m"}]},
            {"label": "Silhouettes at game size (shown at half size)", "height": 430,
             "images": [{"path": ing["p1_22"]["sil"], "label": "phase 1"}, {"path": ing["p2_22"]["sil"], "label": "phase 2"}]},
        ],
        "notes": ["The engine draws the red-white telegraph decals; the model carries none."],
    }
    R.contact_sheet(lay2, os.path.join(out_dir, KEY + "_ingame.png"), work)


def review(mesh, arm, rep, paint_rep, clips, quick=False, lite=False):
    """All review renders and the four report sheets. lite: only the hero shots and the in-game frames,
    with their two sheets written to work/review (paint iterations; reports/ is left alone)."""
    import gfa_rig as RIG
    scene = bpy.context.scene
    pack = C.pack_dir(KIND, KEY)
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    work = C.ensure_dir(os.path.join(pack, "work", "review"))
    tex = [os.path.join(pack, "textures", KEY + "_basecolor.png"), os.path.join(pack, "textures", KEY + "_emissive.png")]
    _p1_pose(arm)
    # 1) turnarounds: phase 1 (idle frame 0), phase 2 (idle_p2 frame 0)
    turn1 = turn2 = {}
    if not lite:
        turn1 = R.turnaround([mesh], work, KEY + "_p1", R.CREATURE_VIEWS, size=400, samples=10)
        _p2_pose(arm)
        v2 = {k: R.CREATURE_VIEWS[k] for k in ("front", "34_front", "side", "top")}
        v2["game"] = tuple(B.game_dir())
        turn2 = R.turnaround([mesh], work, KEY + "_p2", v2, size=400, samples=10)
        _p1_pose(arm)
    # hero shots (the user's first look): phase 1 and phase 2, 3/4 front
    hero = {}
    for ph, fn in ((1, _p1_pose), (2, _p2_pose)):
        fn(arm)
        hero[ph] = R.turnaround([mesh], work, KEY + "_hero_p%d" % ph, {"34": (0.62, -0.72, 0.3)}, size=760,
                                samples=14)["34"]
    _p1_pose(arm)
    # 2) size comparison: front view beside a 2.2 m hero and a 1 m measuring pole
    size_png = None
    if not lite:
        man = R.mannequin(aim_dir=(0.0, -1.0, 0.0), name="GFA_HERO_SIZE")
        man.location = (9.2, -1.0, 0.0)
        bpy.context.view_layer.update()
        size_png = B.size_compare([mesh], os.path.join(work, KEY + "_size.png"), man, w=1100, h=760, pole_height=13)
        C.remove_objects([man])
    # 3) the in-game camera at true 1080p pixel size (a 1560 x 860 crop of the frame)
    party = _party([(-6.5, -8.5), (5.5, -9.0), (9.5, -3.0), (-9.5, -2.5)])
    ing = {}
    pts = R._points([mesh] + party)
    tgt, _, _ = R.frame(pts, B.game_dir())
    ing["p1_22"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p1_22.png"), 1560, 860, 22.0, tgt, party,
                                  silhouette_path=os.path.join(work, KEY + "_ingame_p1_22_sil.png"))
    ing["p1_28"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p1_28.png"), 1560, 860, 28.0, tgt, party)
    _p2_pose(arm)
    arm.rotation_euler = (0.0, 0.0, math.radians(28.0))
    bpy.context.view_layer.update()
    ing["p2_22"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p2_22.png"), 1560, 860, 22.0, tgt, party,
                                  silhouette_path=os.path.join(work, KEY + "_ingame_p2_22_sil.png"))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    _p1_pose(arm)
    C.remove_objects(party)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    if lite:
        first_look_sheets(hero, ing, work, work)
        return {"ingame": ing, "hero": hero}
    # 4) key frames of every clip (3/4 front, one shared scale)
    order = ["idle@loop", "move@loop", "windup", "attack", "hit", "strike_circle", "slam_trail", "radial", "door_open",
             "door_close", "roar", "phase2", "idle_p2@loop", "move_p2@loop", "windup_p2", "attack_p2", "hit_p2",
             "slam_trail_p2", "radial_p2", "strike_cone", "strike_line", "pools", "summon", "phase3", "death"]
    nf = 3 if quick else 5
    strips = B.clip_frames(arm, [mesh], [clip_track(c) for c in order], work, KEY, frames=4 if not quick else 2,
                           size=300, direction=(0.62, -0.72, 0.3), ext=18.5, center=(0.0, -2.0, 6.6), samples=6,
                           ink=0.05, frame_lists={clip_track(c): key_poses(clips[c], nf) for c in order
                                                  if not c.endswith("@loop")})
    RIG.unmute_none(arm)
    scene.frame_set(0)
    thumbs = R._thumbs(tex, work)
    # ---- sheets
    notes = [
        "%s tris (boss budget 20,000-40,000) | textures %s | %.1f m tall = %.1f x the 2.2 m hero | footprint %.1f x %.1f m "
        "(sim collider radius 5.28 m)" % (
            "{:,}".format(rep["tris"]), " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"],
            rep["height_m"] / SPEC.HERO_HEIGHT, rep["bounds"]["max"][0] - rep["bounds"]["min"][0],
            rep["bounds"]["max"][2] - rep["bounds"]["min"][2]),
        "Rig GF_SlagKing_v1: %d joints, rigid skin; %d clips (+%d brief-name aliases); phase state lives in the clips "
        "(arm2 scale 0.001 in phase 1, door burst in phase 2+); crown_spin is spun by the engine." % (
            len(arm.data.bones), len(clips), len(ALIASES)),
        "Painted at 1/8 scale: %s px/m median texel density, UV coverage %.0f %%. Status: %s." % (
            paint_rep["texel_density_px_per_m"].get("median"), 100 * paint_rep["coverage"], SPEC.STATUS_AI_FINAL),
    ]
    layout = {
        "title": "The Slag King  (slag_king)",
        "subtitle": "Boss | Cinder Wastes | The Unmade | verb: THE FURNACE THAT WALKS | Molten Court / Slagfall / Final Pour",
        "width": 1600,
        "sections": [
            {"label": "Phase 1 (Molten Court) turnaround - toon preview of the final textures (ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn1.items()]},
            {"label": "Phase 2+ (Slagfall, Final Pour): door burst, molten arms out (idle_p2 frame 0)", "height": 250,
             "images": [{"path": v, "label": k} for k, v in turn2.items()]},
            {"label": "Size: front view beside the 2.2 m hero mannequin and a 13 m pole (1 m bands, every 5th light)",
             "height": 520, "images": [{"path": size_png, "label": "size comparison"}]},
            {"label": "Textures (base colour, emissive)", "height": 240,
             "images": [{"path": p, "label": lb} for p, lb in thumbs]},
        ],
        "swatches": [{"hex": h, "label": n} for n, h in PALETTE],
        "notes": notes,
    }
    R.contact_sheet(layout, os.path.join(reports, KEY + "_review.png"), work)
    first_look_sheets(hero, ing, reports, work)
    groups = [("Phase 1 loops and the generic pair (windup, attack, hit)", order[:5]),
              ("Molten Court attacks and the furnace face", order[5:11]),
              ("Phase change 1 -> 2 and the phase-2 loops", order[11:14]),
              ("Phase-2 generic pair and attacks", order[14:23]),
              ("Final Pour roar and death", order[23:])]
    secs = []
    for label, names in groups:
        imgs = []
        for c in names:
            for cl, f, pth in strips:
                if cl == clip_track(c):
                    imgs.append({"path": pth, "label": "%s f%d" % (c, f)})
        secs.append({"label": label, "height": 150, "images": imgs})
    lay3 = {"title": "The Slag King - clip key frames", "subtitle": "3/4 front, one shared scale, 30 fps; loops: 4 "
            "evenly spaced frames; one-shots: the key poses (start, loaded, event, follow-through, end)",
            "width": 1600, "sections": secs,
            "notes": ["Brief-name aliases (same action, second track): " +
                      ", ".join("%s = %s" % kv for kv in ALIASES.items()),
                      "; ".join("%s %.2f s" % (c, clips[c]["seconds"]) for c in order[:13]),
                      "; ".join("%s %.2f s" % (c, clips[c]["seconds"]) for c in order[13:])]}
    R.contact_sheet(lay3, os.path.join(reports, KEY + "_clips.png"), work)
    # a single hero image for the user: the phase-2 3/4 view
    return {"turn1": turn1, "turn2": turn2, "size": size_png, "ingame": ing}


def main():
    global CROWN_C, CROWN_AXIS
    argv = C.script_args()
    size = C.opt(argv, "--size", 2048, int)
    C.reset_scene(fps=FPS)
    bpy.context.preferences.filepaths.save_version = 0
    CROWN_C = hm(CROWN_UP)
    CROWN_AXIS = (head_matrix().to_3x3() @ Vector((0, 0, 1))).normalized()
    col = C.get_collection(KEY)
    mesh = build_mesh(col)
    lo, hi = C.world_bounds([mesh])
    C.log("bounds", tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi))
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work"))
    if C.flag(argv, "--preview"):
        out = preview(mesh, C.ensure_dir(os.path.join(work, "preview")))
        C.log("preview", out)
        return
    # paint before skinning, at 1/8 scale so the painter's brush features are boss-sized
    tex_dir = os.path.join(pack, "textures")
    with extra_paint_passes(PAINT_SCALE, mesh):
        paint_rep = B.paint_scaled(mesh, KEY, recipes(), tex_dir, scale=PAINT_SCALE, size=size, decals=decals(),
                                   ao_distance=0.7, ao_samples=16, seed=5, margin_px=4,
                                   uv_small_islands=(0.35, 0.55))
    C.log("paint", {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage", "seconds")})
    # rig, skin, sockets, clips
    arm = B.build_rig(RIG_NAME, rig_table(), col=col, bone_len=0.6)
    skin = B.skin_rigid(mesh, arm)
    C.log("skin", skin["per_bone"])
    socks = sockets(arm)
    clips = build_clips(arm)
    for alias, clip in ALIASES.items():
        B.alias_clip(arm, KEY, alias, clip)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    import gfa_export as E
    extra = {
        "rig": {"name": RIG_NAME, "bones": [b.name for b in arm.data.bones],
                "rest": "every bone points up with roll 0 (creature frame: X left, Y up, Z forward) except crown and "
                        "crown_spin, which point along the crown axis (local +Y = the spin axis)"},
        "boss_sockets": socks,
        "clip_info": clips,
        "clip_aliases": {clip_track(a_): clip_track(c_) for a_, c_ in ALIASES.items()},
        "phases": {
            "Molten Court": {"below": 1.0, "loops": ["idle@loop", "move@loop"], "body": "door shut, two arms, crown still"},
            "Slagfall": {"below": 0.6, "enter": "phase2", "loops": ["idle_p2@loop", "move_p2@loop"],
                         "body": "door burst open, four arms, crown spinning"},
            "Final Pour": {"below": 0.25, "enter": "phase3", "loops": ["idle_p2@loop", "move_p2@loop"],
                           "body": "as Slagfall; the client pushes the emissive toward white and spins the crown faster"},
        },
        "phase_switch": "Clips carry the phase: every clip keys every joint. Phase-1 clips hold arm2_upper_L/R at scale "
                        "0.001 (folded inside the chest) and the door shut; phase2 bursts the door and grows the arms; "
                        "phase-2+ clips hold them. In phase >= 2 play '<clip>_p2' when it exists, else '<clip>'. The "
                        "crown spin is procedural: after animation, rotate the joint crown_spin about its local +Y "
                        "(75 deg/s in Slagfall, 150 deg/s in Final Pour, x2 during radial).",
        "move_cycle_m": {"move@loop": 4.45, "move_p2@loop": 9.4},
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage", "paint_scale")},
        "row": {"hp": 28000, "speed": 1.6, "radius": 2.2, "scale": 2.4, "collider_radius_m": 5.28, "mass": 30,
                "color": "#6B2A14", "shape": "Colossus"},
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.write_json(os.path.join(pack, "reports", "build_report.json"),
                 {"export": {k: v for k, v in rep.items() if k != "nodes"}, "paint": paint_rep, "skin": skin})
    if not C.flag(argv, "--no-review"):
        review(mesh, arm, rep, paint_rep, clips, quick=C.flag(argv, "--quick"), lite=C.flag(argv, "--lite"))
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        "art/enemies/slag_king/reports/slag_king_review.png", "art/enemies/slag_king/reports/slag_king_ingame.png",
        "art/enemies/slag_king/reports/slag_king_clips.png"],
        "Built from code by tools/blender/gf_assets/enemies/slag_king.py (dedicated rig GF_SlagKing_v1).", tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
