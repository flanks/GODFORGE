"""The Bellows (the_bellows) - Cinder Wastes mini-boss (the biome's Warlord), FALLEN GODWORKS. Built end to end
from code: model -> hidden-face cull -> hand-painted NPR textures (2048) -> dedicated rig GF_Bellows_v1 ->
clips -> GLB + meta.json -> validation -> review sheets. art/enemies/the_bellows/README.md records the
decisions.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/the_bellows.py -- [--preview] [--size 2048] [--no-review] [--lite]

  --preview   model only: flat zone-colour views + game-size silhouette in art/enemies/the_bellows/work/preview
  --no-review skip the review renders (export + validation only)
  --lite      review only the 3/4 hero shots and the in-game frames (sheets in work/review; for paint passes)

Content row (content/sheets/enemies.csv): the_bellows, MiniBoss, cinder_wastes, P1, hp 7000, speed 1.8, radius
1.6, scale 1.6 (sim collider radius 2.56 m), mass 12, Boss(script "the_bellows"), colour #B5532A, greybox
Colossus - "A furnace-lung the size of a house. It breathes fire and cinderlings."
Phases (assets/content/bosses.ron): Stoke (100 %: Radial 12, Summon cinderling x6, Strike Ring 2-5.5 at_self),
Blaze (50 %: Radial 18, Summon emberwisp x4, Strike Circle r3 targeted, Strike Ring 2-6.5 at_self).
docs/OPEN_WORLD.md: it is the Cinder Wastes' Warlord POI boss (met in every run, on the way to the gate).

Design (silhouette verb BREATHE):
  * the great bellows of the gods' forge, walked off its hearth when the pantheon fell: a house-sized
    teardrop bellows (5.5 x 9.0 m footprint, 5.23 m tall at rest = 2.38 x the hero) on four cabriole
    bronze legs with lion-paw feet (divine forge furniture come alive), a flat ring handle behind;
  * the LUNG is the bellows bag: five pleated hide folds between a god-bronze lid and a bottom board. The
    lid is hinged at the front, so every breath lifts the lid and fans the folds open; the folds swell on
    the inhale (bared fold valleys glow dead ember: the furnace inside) and crush flat on the exhale;
  * the nozzle is a bronze bell out of the hinge that flares into a cracked porcelain WIND-GOD MASK: puffed
    cheeks, heavy V brows over hollow sockets with cold-gold pupils, pursed O-lips around a bronze nozzle,
    framed all round by swept bronze rays (a sun). It breathes fire and vomits cinderlings through the O;
  * two chimney vents and a snapped third on the lid glow dead ember to cold gold, each whole stack branded
    with one broken rune; two fire hatches on the lid blow open in phase 2 (Blaze), and the mask's left
    cheek breaks away to show the furnace;
  * Godworks palette: dark god-bronze with verdigris shadows, old-gold trim, porcelain, rust hide (the row
    colour #B5532A as its light plane's hue), cold-gold to dead-ember glows. No player colours, no red-white.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_boss as B  # noqa: E402
import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_shell as SH  # noqa: E402
import gfa_spec as SPEC  # noqa: E402

KEY, KIND, TIER = "the_bellows", "enemy", "miniboss"
RIG_NAME = "GF_Bellows_v1"
PAINT_SCALE = 0.25                      # painted at 1/4 scale: the painter's brush features become 0.1-0.4 m strokes
UV_ANGLE = 42.0                         # smart-project angle: splits the conical fold rings into arcs that pack
FPS = 30
ZONES = ["bronze", "bronze_dark", "trim", "hide", "porcelain", "void", "socket", "fire", "ember", "eyes"]
FLAT = {"bronze": "#6A5A3A", "bronze_dark": "#3E3627", "trim": "#9C8248", "hide": "#7A3E28", "porcelain": "#DCD6C9",
        "void": "#14100C", "socket": "#0E0A08", "fire": "#FFE9B0", "ember": "#E0A050", "eyes": "#E8CF80"}

# ---- body layout (creature space: faces -Y, +X = its left, ground z = 0) --------------------------------
Y0, Y1 = -2.2, 3.0                      # the board outline: front (hinge) edge and rear tip
LEN = Y1 - Y0
HW_FRONT, HW_MAX, U_MAX = 0.72, 2.15, 0.6  # half-width at the hinge, at the widest point (at U_MAX of the length)
DOME_C = (0.0, 0.75)                    # centre the lid's dome rings are scaled about
Z_BOARD = (1.6, 1.88)                   # the bottom board: underside, top
HINGE = Vector((0.0, Y0, 2.55))         # the lid hinge axis (along X) = the lid's underside at the front
LID_REST = 14.0                         # deg the lid stands open at rest (rear up)
N_PLEAT = 5
PLEAT_H = 0.8                           # height of one fold (rhombus section)
PLEAT_OUT = 0.5                         # how far the middle fold's ridge stands out of the board outline
LID_RINGS = [(1.0, 0.0), (1.0, 0.2), (0.8, 0.32), (0.45, 0.38)]   # (scale about DOME_C, height above the underside)

# the head: a bronze nozzle bell out of the hinge, flaring into the porcelain mask (face tilted up 18 deg)
NECK = Vector((0.0, Y0 - 0.05, 2.2))
MASK_TILT = 18.0
BELL_LEN = 1.3
MASK_N = Vector((0.0, -math.cos(math.radians(MASK_TILT)), math.sin(math.radians(MASK_TILT))))
MASK_C = NECK + MASK_N * BELL_LEN
MASK_R, MASK_SY, MASK_D = 0.86, 1.12, 0.4        # half-width, height factor, dome depth (face-frame units)
MASK_SCALE = 1.12                                # the whole face is built at 0.86 m and scaled up by this

# cabriole lion legs tucked under the body: (hip, knee bulge, ankle, paw centre) for the left side
LEG = {
    "front": ((0.95, -0.75, 1.7), (1.55, -0.95, 1.2), (1.35, -1.2, 0.52), (1.45, -1.4, 0.28)),
    "hind": ((1.3, 1.85, 1.7), (1.95, 2.1, 1.2), (1.72, 2.35, 0.52), (1.82, 2.45, 0.28)),
}


# ---- the outline and its lofts --------------------------------------------------------------------------

def outline(offset=0.0, n_front=7, n_rear=9):
    """The teardrop board outline (CCW seen from above) as [(x, y), ...], offset outward by `offset` m."""
    side = []
    for k in range(n_front):
        t = k / n_front
        hw = HW_FRONT + (HW_MAX - HW_FRONT) * (1 - (1 - t) ** 1.7)
        side.append((hw, Y0 + U_MAX * t * LEN))
    for k in range(n_rear):
        phi = math.pi / 2 * k / n_rear
        side.append((HW_MAX * math.cos(phi), Y0 + (U_MAX + (1 - U_MAX) * math.sin(phi)) * LEN))
    pts = side + [(0.0, Y1)] + [(-x, y) for x, y in reversed(side)] + [(0.0, Y0)]
    if not offset:
        return pts
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e0, e1 = (b - a).normalized(), (c - b).normalized()
        n0, n1 = Vector((e0.y, -e0.x)), Vector((e1.y, -e1.x))
        nv = (n0 + n1).normalized()
        k = max(0.55, nv.dot(n1))
        p = b + nv * (offset / k)
        out.append((p.x, p.y))
    return out


def ring(offset=0.0, z=0.0, scale=1.0):
    pts = outline(offset)
    cx, cy = DOME_C
    return [Vector((cx + (x - cx) * scale, cy + (y - cy) * scale, z)) for x, y in pts]


def loft(rings, close_profile=False, cap0=False, cap1=False, sharp=()):
    """Quads between consecutive rings (all the same point count, closed loops). sharp: ring indices whose
    loop edges are marked sharp (crisp painted planes); everything else stays smooth (add with shading='keep')."""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    n, R_ = len(rings[0]), len(rings)
    for k in range(R_ if close_profile else R_ - 1):
        a, b = vr[k], vr[(k + 1) % R_]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap0:
        bm.faces.new(list(reversed(vr[0])))
    if cap1:
        bm.faces.new(vr[-1])
    M.recalc(bm)
    for e in bm.edges:
        e.smooth = True
    for k in sharp:
        for i in range(n):
            e = bm.edges.get((vr[k][i], vr[k][(i + 1) % n]))
            if e is not None:
                e.smooth = False
    if cap0 or cap1:
        for e in bm.edges:
            if e.is_manifold and e.calc_face_angle(0) > math.radians(50):
                e.smooth = False
    return bm


def rot_x_about(p, deg):
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, "X") @ Matrix.Translation(-p)


def lid_matrix():
    return rot_x_about(HINGE, LID_REST)


def pleat_frac(i):
    """Fraction of the lid's opening the i-th fold (1..N) follows (0 = bottom board, 1 = lid)."""
    return (i - 0.5) / N_PLEAT


def _outline_dist(x, y, cx, cy):
    """Distance from (cx, cy) to the outline along the ray through (x, y)."""
    d = Vector((x - cx, y - cy))
    if d.length < 1e-6:
        return 1.0, 0.0
    d.normalize()
    pts = outline()
    best = None
    for i in range(len(pts)):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % len(pts)])
        e = b - a
        den = d.x * (-e.y) - d.y * (-e.x)
        if abs(den) < 1e-9:
            continue
        w = a - Vector((cx, cy))
        t = (w.x * (-e.y) - w.y * (-e.x)) / den
        s = (d.x * w.y - d.y * w.x) / den
        if t > 0 and -1e-6 <= s <= 1 + 1e-6 and (best is None or t < best):
            best = t
    return best or 1.0, Vector((x - cx, y - cy)).length


def dome_z(x, y):
    """Height of the lid's top surface above its underside at plan point (x, y) (closed-lid coordinates)."""
    L, r = _outline_dist(x, y, *DOME_C)
    s = r / L
    rs = [(sc, z) for sc, z in LID_RINGS[1:]]          # (1.0, 0.22), (0.83, 0.4), (0.47, 0.53)
    if s >= rs[0][0]:
        return rs[0][1]
    if s <= rs[-1][0]:
        return rs[-1][1]
    for (s0, z0), (s1, z1) in zip(rs[:-1], rs[1:]):
        if s1 <= s <= s0:
            return z0 + (z1 - z0) * (s0 - s) / (s0 - s1)
    return rs[-1][1]


def lid_pt(x, y, dz=0.0):
    """World rest position of a point on the lid's top surface (plan x, y in closed-lid coords) + dz along the
    lid normal."""
    p = Vector((x, y, HINGE.z + dome_z(x, y) + dz))
    return lid_matrix() @ p


def lid_normal():
    return (lid_matrix().to_3x3() @ Vector((0, 0, 1))).normalized()


# ---- the mask frame --------------------------------------------------------------------------------------

def mask_matrix():
    """Face frame: X = the creature's left, Y = up the face, Z = out of the face (forward, tilted up)."""
    t = math.radians(MASK_TILT)
    x = Vector((1, 0, 0))
    z = Vector((0, -math.cos(t), math.sin(t)))
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, MASK_C.x), (x.y, y.y, z.y, MASK_C.y), (x.z, y.z, z.z, MASK_C.z), (0, 0, 0, 1))) @ \
        Matrix.Scale(MASK_SCALE, 4)


def face_z(x, y):
    rho2 = (x / MASK_R) ** 2 + (y / (MASK_R * MASK_SY)) ** 2
    return MASK_D * math.sqrt(max(0.0, 1.0 - rho2))


def fm(p):
    return mask_matrix() @ Vector(p)


# ---- small shape helpers -------------------------------------------------------------------------------------

def place(bm, origin, direction, x_hint=(1, 0, 0)):
    """Move a part built along +Y so +Y -> direction at origin (x_hint keeps the flat side)."""
    d = Vector(direction).normalized()
    x = Vector(x_hint) - d * Vector(x_hint).dot(d)
    if x.length < 1e-5:
        x = Vector((0, 0, 1)) - d * d.z
    x.normalize()
    z = x.cross(d)
    m = Matrix(((x.x, d.x, z.x, origin[0]), (x.y, d.y, z.y, origin[1]), (x.z, d.z, z.z, origin[2]), (0, 0, 0, 1)))
    M.xform(bm, matrix=m)
    return bm


def smooth_tube(points, radii, sides=12, per=4, noise=0.0, seed=0):
    pts = M.catmull([Vector(p) for p in points], per) if len(points) > 2 else [Vector(p) for p in points]
    n = len(pts)
    rr = []
    for i in range(n):
        t = i / (n - 1) * (len(radii) - 1)
        k = min(int(t), len(radii) - 2)
        f = t - k
        rr.append(radii[k] * (1 - f) + radii[k + 1] * f)
    b = M.tube(pts, rr, sides=sides)
    if noise:
        M.noise_displace(b, noise, freq=1.2, seed=seed)
    return b


def disc(radius, sides=16):
    """A flat disc in the XY plane facing +Z (glow faces)."""
    bm = bmesh.new()
    vs = [bm.verts.new((radius * math.cos(2 * math.pi * k / sides), radius * math.sin(2 * math.pi * k / sides), 0))
          for k in range(sides)]
    bm.faces.new(vs)
    return bm


def ring_handle(y0, z0, length, rise):
    """A bellows handle in closed-board coordinates: a flat bar from the rear rim (y0, z0) running back
    `length` m (rising `rise`), ending in a flat ring grip lying in the board's plane (the game camera sees
    the hole). Returns [(bm, zone), ...]."""
    ring_r = 0.5
    bar = M.loft_rect([(0.0, 0.78, 0.2, 0, 0.0), (length * 0.5, 0.42, 0.17, 0, rise * 0.45),
                       (length, 0.36, 0.16, 0, rise)], bevel=0.04)
    M.xform(bar, loc=(0, y0, z0))
    rg = M.ring(ring_r - 0.17, ring_r, 0.16, sides=20, bevel=0.035)
    M.xform(rg, loc=(0, y0 + length + ring_r - 0.08, z0 + rise))
    knob = M.sphere(0.13, 10, 6)
    M.xform(knob, loc=(0, y0 + length + 2 * ring_r - 0.1, z0 + rise))
    return [(bar, "bronze"), (rg, "trim"), (knob, "trim")]


# ---- the model ---------------------------------------------------------------------------------------------

BONE_ORDER = ["root", "pelvis", "lid"] + ["pleat_%d" % i for i in range(1, N_PLEAT + 1)] + [
    "head", "mask_shard", "hatch_L", "hatch_R", "chimney_1", "chimney_2", "chimney_3",
    "front_thigh_L", "front_shin_L", "front_paw_L", "front_thigh_R", "front_shin_R", "front_paw_R",
    "hind_thigh_L", "hind_shin_L", "hind_paw_L", "hind_thigh_R", "hind_shin_R", "hind_paw_R"]

# chimneys on the lid (closed-lid plan x, y), height, radius, lean (x, y) in world, snapped?
CHIMNEYS = [  # bone, (x, y), height, radius, lean, broken
    ("chimney_1", (1.0, 1.2), 1.15, 0.33, (0.12, 0.1), False),
    ("chimney_2", (-1.05, 0.7), 0.9, 0.29, (-0.18, 0.02), False),
    ("chimney_3", (0.55, 2.25), 0.7, 0.29, (0.05, 0.25), True),
]
HATCHES = [("hatch_L", 1), ("hatch_R", -1)]
GEO = {"chimney": {}, "hatch": {}}      # anchors recorded by build_mesh(): chimney base / mouth, hatch hinge, shard
HATCH_C = (0.64, -0.62)          # plan centre (x for the left one) in closed-lid coords
HATCH_SIZE = (0.68, 0.9)


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_ORDER)
    containers = []

    def add(bm, zone, bone, name, shading="auto", container=False):
        pid = a.add(bm, zone, bone=bone, name=name, shading=shading)
        if container:
            containers.append(pid)
        return pid

    LM = lid_matrix()

    # ---------------- bottom board (the chassis) ----------------
    bb = loft([ring(0.0, Z_BOARD[0]), ring(0.0, Z_BOARD[1] - 0.06), ring(-0.08, Z_BOARD[1])], cap0=True, cap1=True,
              sharp=(1,))
    board_pid = add(bb, "bronze_dark", "pelvis", "bottom_board", shading="keep", container=True)
    band = loft([ring(-0.04, Z_BOARD[0] + 0.05), ring(0.07, Z_BOARD[0] + 0.05), ring(0.07, Z_BOARD[1] - 0.08),
                 ring(-0.04, Z_BOARD[1] - 0.08)], close_profile=True, sharp=(1, 2))
    add(band, "trim", "pelvis", "bottom_band", shading="keep")
    # the hinge barrel between the boards at the front (the nozzle neck)
    hb = M.cylinder(0.4, 1.7, sides=14, axis="X", bevel=0.06)
    M.xform(hb, loc=(0, Y0 - 0.02, NECK.z))
    add(hb, "bronze", "pelvis", "hinge_barrel", shading="smooth", container=True)
    # the bottom handle: a flat bronze bar ending in a ring grip (the lower handle of the bellows)
    for part_, zone in ring_handle(Y1 - 0.4, Z_BOARD[0] + 0.14, 1.0, 0.0):
        add(part_, zone, "pelvis", "bottom_handle")

    # ---------------- the pleated hide lung ----------------
    gap0 = HINGE.z - Z_BOARD[1]
    h2 = PLEAT_H / 2
    for i in range(1, N_PLEAT + 1):
        f = pleat_frac(i)
        zc = Z_BOARD[1] + gap0 * f
        out = PLEAT_OUT * (0.85 + 0.3 * math.sin(math.pi * f))       # the middle folds stand out furthest
        # an open V strip: the ridge and the two fold faces (the inner half of a fold is buried in the bag)
        pl = loft([ring(-0.02, zc - h2), ring(out, zc), ring(-0.02, zc + h2)], sharp=(1,))
        M.xform(pl, matrix=rot_x_about(HINGE, f * LID_REST))
        add(pl, "hide", "pleat_%d" % i, "pleat_%d" % i, shading="keep")

    # ---------------- the lid (fan-ribbed god-bronze board) ----------------
    lid_rings = [ring(0.0, HINGE.z + z, s) for s, z in LID_RINGS]
    lid = loft(lid_rings, cap0=True, cap1=True, sharp=(1, 2, 3))
    M.xform(lid, matrix=LM)
    lid_pid = add(lid, "bronze", "lid", "lid_plate", shading="keep", container=True)
    rim = loft([ring(-0.03, HINGE.z - 0.05), ring(0.1, HINGE.z - 0.05), ring(0.1, HINGE.z + 0.2),
                ring(-0.05, HINGE.z + 0.27)], close_profile=True, sharp=(1, 2, 3))
    M.xform(rim, matrix=LM)
    add(rim, "trim", "lid", "lid_rim", shading="keep")
    # the spine ridge and two fan straps (raised ridges over the dome)
    spine_pts = []
    for k in range(13):
        y = Y0 + 0.25 + (Y1 - 0.35 - Y0 - 0.25) * k / 12
        spine_pts.append(Vector((0.0, y, HINGE.z + dome_z(0.0, y) + 0.05)))
    sp = M.tube(spine_pts, 1.0, profile=[(0.0, -0.15), (0.13, 0.0), (0.0, 0.15), (-0.3, 0.0)], up=(0, 0, 1))
    M.xform(sp, matrix=LM)
    add(sp, "trim", "lid", "lid_spine", shading="auto")
    for sx in (1, -1):
        pts = []
        for k in range(9):
            t = k / 8
            x = sx * (0.35 + 1.55 * t)
            y = Y0 + 0.35 + 3.0 * t
            pts.append(Vector((x, y, HINGE.z + dome_z(x, y) + 0.03)))
        stp = M.tube(pts, 1.0, profile=[(0.0, -0.13), (0.11, 0.0), (0.0, 0.13), (-0.2, 0.0)], up=(0, 0, 1))
        M.xform(stp, matrix=LM)
        add(stp, "bronze", "lid", "lid_strap", shading="auto")
    # rivets round the rim
    pts, nrms = [], []
    ol = outline(0.02)
    for k in range(0, len(ol), 2):
        x, y = ol[k]
        pts.append(LM @ Vector((x, y, HINGE.z + 0.27)))
        nrms.append(lid_normal())
    add(M.studs(pts, nrms, 0.09, 0.07), "trim", "lid", "lid_rivets")
    # hinge knuckles on the lid's front edge
    for x in (-0.62, 0.0, 0.62):
        kn = M.cylinder(0.2, 0.42, sides=10, axis="X")
        M.xform(kn, loc=(x, Y0 - 0.06, HINGE.z + 0.06))
        add(kn, "trim", "lid", "lid_knuckle", shading="smooth")
    # the top handle: a flat bronze paddle sweeping back and up off the rear rim
    for part_, zone in ring_handle(Y1 - 0.45, HINGE.z + 0.14, 1.15, 0.22):
        M.xform(part_, matrix=LM)
        add(part_, zone, "lid", "top_handle")

    # fire hatches (phase 2 blows them open) over glowing grates
    for bone, sx in HATCHES:
        cx, cy = sx * HATCH_C[0], HATCH_C[1]
        wx, wy = HATCH_SIZE
        base_z = HINGE.z + max(dome_z(cx - wx / 2, cy), dome_z(cx + wx / 2, cy)) + 0.0
        pit = M.box((wx - 0.08, wy - 0.08, 0.06))
        M.xform(pit, loc=(cx, cy, base_z + 0.02))
        M.xform(pit, matrix=LM)
        add(pit, "ember", "lid", "grate_glow", shading="flat")
        fr = []
        for (dx, dy, w, h) in ((0, wy / 2, wx + 0.1, 0.1), (0, -wy / 2, wx + 0.1, 0.1), (wx / 2, 0, 0.1, wy),
                               (-wx / 2, 0, 0.1, wy)):
            b_ = M.box((w, h, 0.14), bevel=0.02)
            M.xform(b_, loc=(cx + dx, cy + dy, base_z + 0.06))
            fr.append(b_)
        for k in range(3):
            b_ = M.box((0.06, wy - 0.05, 0.08))
            M.xform(b_, loc=(cx + (k - 1) * wx / 4, cy, base_z + 0.08))
            fr.append(b_)
        g = M.merge(*fr)
        for b_ in fr:
            b_.free()
        M.xform(g, matrix=LM)
        add(g, "bronze_dark", "lid", "grate", shading="flat")
        hp = M.box((wx + 0.06, wy + 0.06, 0.09), bevel=0.03, taper=(0.94, 0.94))
        M.xform(hp, loc=(cx, cy, base_z + 0.18))
        M.xform(hp, matrix=LM)
        add(hp, "bronze", bone, "hatch_plate")
        ring_ = M.ring(0.09, 0.14, 0.05, sides=8)
        M.xform(ring_, rot=(90, 0, 0), loc=(cx - sx * 0.18, cy, base_z + 0.26))
        M.xform(ring_, matrix=LM)
        add(ring_, "trim", bone, "hatch_ring")
        GEO["hatch"][bone] = (LM @ Vector((cx + sx * (wx / 2 + 0.02), cy, base_z + 0.17)),
                              LM @ Vector((cx, cy, base_z + 0.06)))
        for dy in (-0.3, 0.3):
            hg = M.cylinder(0.07, 0.22, sides=8, axis="Y")
            M.xform(hg, loc=(cx + sx * (wx / 2 + 0.02), cy + dy, base_z + 0.17))
            M.xform(hg, matrix=LM)
            add(hg, "trim", bone, "hatch_hinge", shading="smooth")

    # chimneys (vents): bronze stacks with a crown rim and a glowing mouth
    for bone, (x, y), h, r, lean, broken in CHIMNEYS:
        base = lid_pt(x, y, -0.05)
        d = Vector((lean[0], lean[1], 1.0)).normalized()
        if broken:
            prof = [(r * 1.25, -0.25), (r * 1.2, 0.12), (r, 0.3), (r * 0.95, h * 0.7), (r * 1.05, h)]
        else:
            prof = [(r * 1.3, -0.25), (r * 1.25, 0.14), (r, 0.34), (r * 0.92, h * 0.62), (r * 1.08, h * 0.8),
                    (r * 1.35, h), (r * 1.2, h + 0.06)]
        inner = r * 0.78
        prof = prof + [(inner, prof[-1][1] - 0.02), (inner, h - 0.12 - (0.25 if broken else 0.0))]
        ch = M.lathe(prof, sides=14)
        if broken:          # a snapped stack: jag the rim
            rng = random.Random(3)
            for v in ch.verts:
                if v.co.z > h - 0.05:
                    ang = math.atan2(v.co.y, v.co.x)
                    v.co.z -= 0.22 * (0.5 + 0.5 * math.sin(3 * ang + 0.7)) + rng.uniform(0, 0.08)
        frame_ = M.orient(base, d, (1, 0, 0))
        GEO["chimney"][bone] = (frame_ @ Vector((0, 0, 0.1)), frame_ @ Vector((0, 0, h - (0.2 if broken else 0.0))))
        GEO.setdefault("chimney_frame", {})[bone] = (frame_.copy(), h, r)
        M.xform(ch, matrix=frame_)
        add(ch, "bronze", bone, "chimney", shading="smooth")
        gl = disc(inner * 1.02, 14)
        M.xform(gl, loc=(0, 0, h - 0.1 - (0.25 if broken else 0.0)))
        M.xform(gl, matrix=frame_)
        add(gl, "ember", bone, "chimney_glow", shading="flat")
        for t in (0.3,):              # one band low down: the stack above it is the rune's field
            bnd = M.ring(r * 0.98, r * 1.14, 0.12, sides=14, bevel=0.02)
            M.xform(bnd, loc=(0, 0, h * t))
            M.xform(bnd, matrix=frame_)
            add(bnd, "trim", bone, "chimney_band", shading="flat")
        if not broken:      # a crown of six short spikes round the mouth (the Godworks sun motif)
            sp_ = []
            for k in range(6):
                ang = 2 * math.pi * k / 6 + 0.3
                s_ = M.spike(0.07, 0.34, sides=4)
                M.xform(s_, rot=(0, 0, 0))
                o = Vector((math.cos(ang) * r * 1.28, math.sin(ang) * r * 1.28, h + 0.02))
                dd = Vector((math.cos(ang) * 0.45, math.sin(ang) * 0.45, 1.0))
                M.xform(s_, matrix=M.orient(o, dd, (0, 0, 1)))
                sp_.append(s_)
            crown = M.merge(*sp_)
            for s_ in sp_:
                s_.free()
            M.xform(crown, matrix=frame_)
            add(crown, "trim", bone, "chimney_crown", shading="flat")

    # ---------------- the head: furnace kiln + porcelain wind-god mask ----------------
    # the nozzle bell: out of the hinge barrel, a narrow neck flaring into the mask (open at the flare, with a
    # dark inner wall, so the phase-2 hole in the mask looks into a furnace, not through the bronze)
    BF = M.orient(NECK, MASK_N, (1, 0, 0))
    bell_prof = [(0.5, -0.25), (0.46, 0.1), (0.36, 0.45), (0.35, 0.68), (0.46, 0.9), (0.76, 1.12),
                 (1.0, BELL_LEN - 0.02)]
    bell = M.lathe(bell_prof, sides=18, cap=False)
    M.xform(bell, matrix=BF)
    add(bell, "bronze", "head", "bell", shading="smooth")
    inner = M.lathe([(0.001, -0.1)] + [(r - 0.07, z) for r, z in bell_prof[1:]], sides=18, cap=False)
    bmesh.ops.reverse_faces(inner, faces=inner.faces[:])
    M.xform(inner, matrix=BF)
    add(inner, "void", "head", "bell_inner", shading="smooth")
    for t, r_ in ((0.12, 0.5), (0.72, 0.42)):
        bnd = M.ring(r_ - 0.04, r_ + 0.07, 0.14, sides=18, bevel=0.03)
        M.xform(bnd, loc=(0, 0, t))
        M.xform(bnd, matrix=BF)
        add(bnd, "trim", "head", "bell_band", shading="flat")
    # the furnace core inside the bell (shows through the phase-2 hole and the O-mouth)
    core = M.ico(0.5, 2)
    M.xform(core, loc=MASK_C - MASK_N * 0.32)
    add(core, "fire", "head", "furnace_core", shading="smooth")
    MM = mask_matrix()
    # the mask shell: an elliptic dome in the face frame; the left-cheek shard is cut out as its own plate
    nu, nv = 24, 6
    shard_cells = {(i, j) for i in range(9, 13) for j in range(2, 5)} | {(8, 3), (13, 2), (13, 3), (10, 1), (11, 5)}
    shard_cells -= {(12, 4)}
    fn = SH.cap_fn(MASK_R, MASK_D, theta0=-180.0, theta1=180.0, sy=MASK_SY, matrix=MM)
    main_o, main_i = SH.thick_patch(fn, nu, nv, 0.07, keep=lambda i, j: (i, j) not in shard_cells, wrap_u=True)
    shard_o, shard_i = SH.thick_patch(fn, nu, nv, 0.07, keep=lambda i, j: (i, j) in shard_cells, wrap_u=True)
    add(main_o, "porcelain", "head", "mask", shading="smooth")
    add(main_i, "void", "head", "mask_inner", shading="smooth")
    GEO["shard_c"] = sum((v.co for v in shard_o.verts), Vector()) / max(1, len(shard_o.verts))
    add(shard_o, "porcelain", "mask_shard", "mask_shard", shading="smooth")
    add(shard_i, "void", "mask_shard", "mask_shard_inner", shading="smooth")
    # a bronze collar round the mask's edge (hides the join to the kiln)
    col_ = M.tube([Vector((MASK_R * 1.02 * math.cos(2 * math.pi * k / 28),
                           MASK_R * MASK_SY * 1.02 * math.sin(2 * math.pi * k / 28), -0.03)) for k in range(28)],
                  0.1, sides=8, closed=True)
    M.xform(col_, matrix=MM)
    add(col_, "trim", "head", "mask_collar", shading="smooth")
    # puffed cheeks (the blowing wind god): the left one rides the shard
    for sx, bone in ((1, "mask_shard"), (-1, "head")):
        cx, cy = sx * 0.4, -0.22
        ck = M.sphere(0.27, 14, 10, scale=(1.0, 0.92, 0.66))
        M.xform(ck, loc=(cx, cy, face_z(cx, cy) - 0.09))
        M.xform(ck, matrix=MM)
        add(ck, "porcelain", bone, "cheek", shading="smooth")
    # a severe theatre mask, never a baby face: heavy V brows over HOLLOW almond sockets (a dark hole in the
    # porcelain at game size), each with a small cold-gold ember of a pupil deep inside
    for sx in (1, -1):
        ex, ey = sx * 0.34, 0.19
        br = M.box((0.52, 0.15, 0.2), bevel=0.05, segments=1, taper=(1.0, 0.7))
        M.xform(br, rot=(0, 0, sx * 22), loc=(sx * 0.33, 0.41, face_z(sx * 0.33, 0.41) + 0.03))
        M.xform(br, matrix=MM)
        add(br, "porcelain", "head", "brow")
        lens = []
        for k in range(10):
            a_ = 2 * math.pi * k / 10
            x_, y_ = 0.22 * math.cos(a_), 0.1 * math.sin(a_) * (1.0 - 0.35 * math.cos(a_) * sx)
            ca, sa = math.cos(math.radians(sx * 14)), math.sin(math.radians(sx * 14))
            lens.append((ex + x_ * ca - y_ * sa, ey + x_ * sa + y_ * ca))
        skt = bmesh.new()
        lo_ = [skt.verts.new((x_, y_, face_z(x_, y_) - 0.04)) for x_, y_ in lens]
        hi_ = [skt.verts.new((x_, y_, face_z(x_, y_) + 0.03)) for x_, y_ in lens]
        skt.faces.new(hi_)
        skt.faces.new(list(reversed(lo_)))
        for k in range(10):
            j = (k + 1) % 10
            skt.faces.new((lo_[k], lo_[j], hi_[j], hi_[k]))
        M.recalc(skt)
        M.xform(skt, matrix=MM)
        add(skt, "socket", "head", "eye_socket", shading="flat")
        pup = M.sphere(0.06, 8, 6, scale=(1.0, 0.8, 0.6))
        M.xform(pup, loc=(ex + sx * 0.03, ey - 0.01, face_z(ex, ey) + 0.04))
        M.xform(pup, matrix=MM)
        add(pup, "eyes", "head", "pupil", shading="smooth")
    nose = M.box((0.16, 0.3, 0.12), bevel=0.04, taper=(0.6, 0.8))
    M.xform(nose, rot=(-12, 0, 0), loc=(0, 0.05, face_z(0, 0.05) - 0.02))
    M.xform(nose, matrix=MM)
    add(nose, "porcelain", "head", "nose")
    # pursed O-lips round a bronze nozzle with the fire inside
    my = -0.4
    lip_z = face_z(0, my) + 0.06
    lips = M.tube([Vector((0.25 * math.cos(2 * math.pi * k / 16), 0.2 * math.sin(2 * math.pi * k / 16), 0))
                   for k in range(16)], 0.1, sides=8, closed=True)
    M.xform(lips, loc=(0, my, lip_z))
    M.xform(lips, matrix=MM)
    add(lips, "porcelain", "head", "lips", shading="smooth")
    nz = M.lathe([(0.2, -0.3), (0.2, 0.05), (0.24, 0.16), (0.2, 0.2), (0.14, 0.18), (0.14, -0.2)], sides=14)
    M.xform(nz, loc=(0, my, lip_z))
    M.xform(nz, matrix=MM)
    add(nz, "trim", "head", "nozzle", shading="smooth")
    fdisc = disc(0.145, 14)
    M.xform(fdisc, loc=(0, my, lip_z - 0.12))
    M.xform(fdisc, matrix=MM)
    add(fdisc, "ember", "head", "nozzle_fire", shading="flat")
    # the mane: swept bronze rays round the upper rim (a sun of wind, blown back)
    for k, (ang, L) in enumerate(((90, 1.05), (62, 0.95), (118, 0.95), (36, 0.85), (144, 0.85), (12, 0.7),
                                  (168, 0.7), (-14, 0.55), (194, 0.55))):
        a_ = math.radians(ang)
        rdir = Vector((math.cos(a_), math.sin(a_) * MASK_SY, 0)).normalized()
        o = Vector((MASK_R * 0.98 * math.cos(a_), MASK_R * MASK_SY * 0.98 * math.sin(a_), -0.02))
        p1 = o + rdir * (L * 0.45) + Vector((0, 0, -0.25 * L))
        p2 = o + rdir * (L * 0.8) + Vector((0, 0, -0.62 * L)) + Vector((0, 0.1 * L, 0))
        ray = M.horn([o, p1, p2], 0.15, 0.02, sides=6)
        M.xform(ray, matrix=MM)
        add(ray, "trim", "head", "mane_ray", shading="smooth")
    # the beard: shorter swept rays under the chin, so the rays frame the whole face (a sun, not a bonnet)
    for ang, L in ((222, 0.62), (246, 0.78), (270, 0.9), (294, 0.78), (318, 0.62)):
        a_ = math.radians(ang)
        rdir = Vector((math.cos(a_), math.sin(a_) * MASK_SY, 0)).normalized()
        o = Vector((MASK_R * 0.97 * math.cos(a_), MASK_R * MASK_SY * 0.97 * math.sin(a_), -0.02))
        p1 = o + rdir * (L * 0.5) + Vector((0, 0, -0.2 * L))
        p2 = o + rdir * (L * 0.85) + Vector((0, 0, -0.5 * L)) + Vector((-0.12 * L * math.cos(a_), 0, 0))
        ray = M.horn([o, p1, p2], 0.13, 0.02, sides=6)
        M.xform(ray, matrix=MM)
        add(ray, "trim", "head", "beard_ray", shading="smooth")

    # ---------------- legs: cabriole lion legs (divine forge furniture) ----------------
    for kind, (hip, knee, ank, paw) in LEG.items():
        for side, sx in (("L", 1), ("R", -1)):
            hp_, kn_, an_, pw_ = [Vector((sx * p[0], p[1], p[2])) for p in (hip, knee, ank, paw)]
            thigh = "%s_thigh_%s" % (kind, side)
            shin = "%s_shin_%s" % (kind, side)
            pawb = "%s_paw_%s" % (kind, side)
            hipb = M.sphere(0.44, 12, 8, scale=(1.0, 1.0, 0.8))
            M.xform(hipb, loc=hp_ + Vector((0, 0, 0.05)))
            add(hipb, "bronze_dark", thigh, "hip_ball", shading="smooth")
            # the knee: a fat cabriole bulge with an old-gold scroll boss on its outer face
            mid = hp_.lerp(kn_, 0.55) + Vector((sx * 0.08, 0, 0.05))
            add(smooth_tube([hp_, mid, kn_], [0.36, 0.44, 0.46], sides=12), "bronze", thigh, "thigh",
                shading="smooth", container=True)
            kb = M.sphere(0.24, 10, 8, scale=(0.6, 1.0, 1.0))
            M.xform(kb, loc=kn_ + Vector((sx * 0.36, -0.04, 0.02)))
            add(kb, "trim", thigh, "knee_boss", shading="smooth")
            # the shin: tapering in to a slim ankle, then out into the paw
            smid = kn_.lerp(an_, 0.5) + Vector((sx * 0.04, 0, 0))
            add(smooth_tube([kn_, smid, an_], [0.44, 0.3, 0.22], sides=12), "bronze", shin, "shin",
                shading="smooth", container=True)
            # a feathered old-gold acanthus flange down the front of the knee (the cabriole's carving)
            fl = M.horn([kn_ + Vector((0, -0.38, 0.1)), kn_.lerp(an_, 0.45) + Vector((0, -0.3, 0)),
                         an_ + Vector((0, -0.2, 0.1))], 0.12, 0.03, sides=5)
            add(fl, "trim", shin, "knee_flange")
            cuff = M.ring(0.2, 0.31, 0.14, sides=12, bevel=0.03)
            M.xform(cuff, matrix=M.orient(an_ + Vector((0, 0, 0.06)), (0, 0, 1)))
            add(cuff, "trim", pawb, "ankle_cuff")
            pm = M.sphere(0.46, 14, 8, scale=(1.0, 1.12, 0.62))
            M.xform(pm, loc=pw_)
            add(pm, "bronze", pawb, "paw", shading="smooth", container=True)
            for k, tx in enumerate((-0.3, -0.1, 0.1, 0.3)):
                toe_c = pw_ + Vector((sx * tx, -0.4 + 0.04 * abs(k - 1.5), -0.08))
                toe = M.sphere(0.16, 10, 6, scale=(1.0, 1.15, 0.9))
                M.xform(toe, loc=toe_c)
                add(toe, "bronze", pawb, "toe", shading="smooth")
                cl = M.horn([toe_c + Vector((0, -0.12, 0.02)), toe_c + Vector((0, -0.26, -0.03)),
                             toe_c + Vector((0, -0.33, -0.15))], 0.07, 0.01, sides=5)
                add(cl, "bronze_dark", pawb, "claw")

    tris_before = a.tris()
    culled = B.cull_hidden_faces(a, containers, eps=0.03)
    # the lid's underside and the board's top lie inside the bag: never seen, so they take no texels
    ln_ = lid_normal()
    a.bm.normal_update()
    buried = [f for f in a.bm.faces if (f[a.part_layer] == lid_pid and f.normal.dot(ln_) < -0.95) or
              (f[a.part_layer] == board_pid and f.normal.z > 0.95)]
    bmesh.ops.delete(a.bm, geom=buried, context="FACES")
    culled += len(buried)
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
    man.location = (-3.5, -5.0, 0.0)
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / 22.0
    R.setup_workbench_flat(scene)
    R.aim(scene, Vector((0, -0.5, 2.0)), B.game_dir(), 560 / ppm, dist=90)
    out["sil_game"] = R.render(scene, os.path.join(out_dir, "%s_sil_game22.png" % KEY), 560, 480)
    C.remove_objects([man])
    return out


# ---- paint ---------------------------------------------------------------------------------------------
# Painted at 1/4 scale (the painter's fixed brush features become 0.1-0.4 m strokes on a 7 m creature). The
# pipeline is gfa_paint's (unwrap, Cycles bakes, zone painter, dilation, final material) with gfa_brush's
# broad value planes on the bronze (lathes and tubes would streak under per-facet values), then this build's
# own passes (EXTRAS: top planes, the hide's fold stripes, patina, per-vent ember glow), then the decals.

PALETTE = [  # (name, hex) for the review sheet
    ("bronze shadow (verdigris)", "#1B3029"), ("dark god-bronze", "#5E5034"), ("bronze light", "#8E7B4E"),
    ("old-gold trim", "#86703F"), ("hide", "#542D20"), ("hide light (row hue)", "#A84E2A"),
    ("porcelain", "#D9D3C6"), ("verdigris patina", "#3D5E50"), ("dead ember", "#8A3A1E"),
    ("cold gold glow", "#D4B45A"), ("white-gold core", "#FFF4D0"),
]
RUNE = "#C9AA56"
RUNE_GLOW = {"color": "#3A2C10", "core": "#6E5626"}


def core_pos():
    return MASK_C - MASK_N * 0.32


def mouth_pos():
    return fm((0.0, -0.4, face_z(0.0, -0.4) + 0.34))


def recipes():
    import gfa_paint as P
    low_dark = {"axis": (0, 0, -1), "range": (-1.6, -0.2), "color": "#1E241A", "amount": 0.45}
    return {
        # dark god-bronze (forge_warden lesson: the body stays dark, verdigris in every shadow)
        "bronze": P.zone(base="#5E5034", shadow="#1B3029", light="#8E7B4E", planes=0.1, parts=0.08, brush=0.05,
                         brush_freq=1.0, edge=0.85, edge_width=0.05, edge_breakup=0.35, cavity=0.85,
                         cavity_width=0.05, ao=0.8, ao_range=(0.15, 0.5), gradient=low_dark,
                         spots={"color": "#3D5E50", "amount": 0.6, "freq": 1.1, "threshold": (0.54, 0.66)}),
        "bronze_dark": P.zone(base="#3E3627", shadow="#0C1613", light="#6A5E40", planes=0.08, parts=0.07, brush=0.05,
                              brush_freq=1.0, edge=0.8, edge_width=0.045, edge_breakup=0.4, cavity=0.8,
                              cavity_width=0.045, ao=0.75, ao_range=(0.15, 0.5), gradient=low_dark,
                              spots={"color": "#274237", "amount": 0.55, "freq": 1.4, "threshold": (0.55, 0.67)}),
        # old-gold trim: dull, a clear step below the porcelain and the glows
        "trim": P.zone(base="#86703F", shadow="#3A2E17", light="#B49A5A", planes=0.08, parts=0.06, brush=0.04,
                       brush_freq=1.3, edge=0.8, edge_width=0.035, edge_breakup=0.35, cavity=0.7, cavity_width=0.03,
                       ao=0.6, ao_range=(0.2, 0.55),
                       spots={"color": "#4A6A5A", "amount": 0.35, "freq": 1.8, "threshold": (0.6, 0.72)}),
        # the lung's hide: rust leather, the row colour #B5532A as its light plane; bright fold ridges
        "hide": P.zone(base="#542D20", shadow="#1E0E0C", light="#A84E2A", planes=0.08, parts=0.05, brush=0.05,
                       brush_freq=0.8, edge=0.9, edge_width=0.07, edge_breakup=0.3, cavity=0.6, cavity_width=0.04,
                       ao=0.75, ao_range=(0.12, 0.45), stroke=(0, 0, 1), stroke_amount=0.12, stroke_freq=(2.2, 0.35)),
        "porcelain": P.zone(base="#DCD6C9", shadow="#8C877E", light="#F6F2E8", planes=0.035, parts=0.02, brush=0.025,
                            brush_freq=1.5, edge=0.5, edge_width=0.02, cavity=0.45, cavity_width=0.02, ao=0.45,
                            ao_range=(0.25, 0.65)),
        # the dark inside (mask shell, bell): verdigris-black, dead ember close to the furnace core
        "void": P.zone(base="#10201C", shadow="#07100D", light="#1C302A", planes=0.05, parts=0.0, brush=0.06,
                       brush_freq=1.0, edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#8A3A1E", "hot": "#4A1A0C", "color": "#0C0806", "mode": "radial",
                             "center": tuple(core_pos()), "radius": 1.1, "base_mix": 0.0, "strength": 0.9}),
        # the hollow eye sockets: near-black, warm (the pupils carry the glow)
        "socket": P.zone(base="#120C0A", shadow="#060404", light="#241A14", planes=0.04, parts=0.0, brush=0.03,
                         brush_freq=1.0, edge=0.3, edge_width=0.015, cavity=0.0, ao=0.0),
        # the furnace: white-gold at the heart, cold gold, dead ember at the rim
        "fire": P.zone(base="#F0D890", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFF4D0", "hot": "#E2CA7C", "color": "#B8702E", "mode": "radial",
                             "center": tuple(core_pos()), "radius": 0.75, "base_mix": 0.15}),
        # vents and grates: painted per part in paint_extras (hot centre, ember rim); this is the flat fallback
        "ember": P.zone(base="#E0A050", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#FFF0C8", "hot": "#D4B45A", "color": "#8A3A1E", "mode": "flat", "base_mix": 0.2}),
        "eyes": P.zone(base="#E8CF80", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFF4D0", "hot": "#E8CF80", "color": "#8A6A28", "mode": "flat", "base_mix": 0.2}),
    }


def broad_zones():
    import gfa_brush as BR
    s = PAINT_SCALE
    # broad() lengths and frequencies are in paint-space metres (real x PAINT_SCALE)
    common = dict(wobble=0.3, wobble_freq=1.4 / s, inner=0.04, inner_freq=0.6 / s, stroke=0.85,
                  stroke_width=0.05 * s, stroke_len=0.7 * s, stroke_cover=0.5, glint=0.4)
    return {"bronze": BR.broad(levels=(-0.28, -0.1, 0.08, 0.22), **common),
            "bronze_dark": BR.broad(levels=(-0.2, -0.06, 0.06, 0.16), **common)}


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
    # (no lid cracks: at 1x every glowing line on the lid read as a glyph. The vents and the fold valleys
    # already show the furnace inside, and the lid stays one clean painted plane.)
    # porcelain: dark hairline cracks, the widest round the left-cheek shard (it breaks away in Blaze)
    MM = mask_matrix()
    mz = (MM.to_3x3() @ Vector((0, 0, 1))).normalized()
    my_ = (MM.to_3x3() @ Vector((0, 1, 0))).normalized()
    for (x, y), ang, L, w, sd in (((0.22, 0.05), -35, 0.75, 0.024, 21), ((0.12, 0.55), 80, 0.35, 0.02, 22),
                                  ((-0.55, 0.4), 150, 0.4, 0.018, 23)):
        lines = M.crack_lines(random.Random(sd), start=(x, y), direction=ang, length=L, step=0.07, jag=0.5,
                              branches=1, branch_len=0.4, depth=1)
        out.append(P.decal_lines(lines, frame_at(MASK_C, mz, my_), w, zones=["porcelain"], color="#4E463E",
                                 rim="#8C877E", rim_width=w * 2.2, depth=(-0.8, 1.2), facing=0.2))
    # broken runes: ONE big two-stroke glyph on each whole chimney stack, on the side the camera sees (the vents
    # are branded with the forge's marks); cold gold on dark bronze, a dim glow (forge_warden rune lesson). A
    # planar decal with a tight depth range, so it never stamps the lid behind the stack.
    for (bone, _xy, _h, _r, _lean, broken), face_deg, sd in zip(CHIMNEYS, (-40.0, -140.0, -90.0), (51, 52, 53)):
        if broken:
            continue
        fr, h, r = GEO["chimney_frame"][bone]
        a_ = math.radians(face_deg)
        rot = fr.to_3x3()
        axis = (rot @ Vector((0, 0, 1))).normalized()
        out_dir = (rot @ Vector((math.cos(a_), math.sin(a_), 0))).normalized()
        v0 = 0.3 * h + 0.08 + (h - 0.1 - 0.3 * h - 0.08) * 0.5
        size = min(0.52, (h - 0.1 - 0.3 * h - 0.08) * 0.95)
        o = fr @ Vector((r * 0.95 * math.cos(a_), r * 0.95 * math.sin(a_), v0))
        g = M.rune_glyph(random.Random(sd), size=size, strokes=2, broken=0.15)
        out.append(P.decal_lines(g, frame_at(o, out_dir, axis), 0.075, zones=["bronze"], color=RUNE, rim="#16201A",
                                 rim_width=0.13, emit=RUNE_GLOW, depth=(-0.2, 0.2), facing=0.3))
    return out


EXTRAS = {  # zone -> top-plane lift (target colour, amount), down-plane darkening, patina
    "bronze": {"top": ("#76663F", 0.55), "patina": ("#3D5E50", 0.5)},
    "bronze_dark": {"top": ("#55492F", 0.5), "patina": ("#274237", 0.45)},
    "hide": {"top": ("#843E27", 0.7), "down": ("#1A0C0A", 0.6)},
}
# the furnace between the folds: dead ember deep in every fold valley (hidden when the lung is crushed, bared
# when it swells on the inhale), cooling to the plain hide toward the ridge
VALLEY = {"from": 0.34, "to": 0.62, "rim": "#4A1A0C", "hot": "#A8481E", "tint": "#3A1410"}


def ridge_points(obj):
    """{part id: [points]} along each hide fold's ridge (the one convex sharp loop of a V strip; paint space)."""
    from collections import defaultdict
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    layer = bm.faces.layers.int.get("gfa_part")
    hide_i = [sl.material.name[4:] for sl in obj.material_slots].index("hide")
    out = defaultdict(list)
    for e in bm.edges:
        if not e.is_manifold or e.smooth:
            continue
        f0, f1 = e.link_faces
        if f0.material_index != hide_i or f0[layer] != f1[layer] or e.calc_face_angle_signed(0.0) <= 0:
            continue
        p0, p1 = e.verts[0].co.copy(), e.verts[1].co.copy()
        n = max(1, int((p1 - p0).length / 0.004))
        out[f0[layer]].extend(p0.lerp(p1, (i + 0.5) / n) for i in range(n))
    bm.free()
    return out


def paint_extras(P, maps, zones_order, base, emis, scale, seed=0, obj=None):
    import numpy as np
    pos = maps["pos"] / scale                                    # real metres
    Z = maps["zone"]
    for zname, ex in EXTRAS.items():
        if zname not in zones_order:
            continue
        m = Z == zones_order.index(zname)
        if not m.any():
            continue
        p, nz = pos[m], maps["snrm"][m, 2]
        c = base[m]
        brush = P.spread01(P.fbm(p, 0.7, 2, seed=seed + 501))
        nb = nz + (brush - 0.5) * 0.3
        if ex.get("top"):
            col, amt = ex["top"]
            k = P.smoothstep(0.25, 0.6, nb) * amt
            lum = c @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
            k = k * (1.0 - P.smoothstep(0.35, 0.55, lum))           # never flatten the light edge strokes
            c = P.mix(c, P.hex3(col), k)
        if ex.get("down"):
            col, amt = ex["down"]
            c = P.mix(c, P.hex3(col), P.smoothstep(-0.2, -0.6, nb) * amt)
        if ex.get("patina"):
            col, amt = ex["patina"]
            occ = 1.0 - maps["ao"][m]
            n1 = P.spread01(P.fbm(p, 0.9, 3, seed=seed + 503))
            k = P.smoothstep(0.58, 0.7, n1 + occ * 0.35) * amt
            c = P.mix(c, P.hex3(col), k)
        base[m] = c
    # the fold valleys (see VALLEY)
    if obj is not None and "hide" in zones_order:
        m = np.nonzero(Z == zones_order.index("hide"))[0]
        ridges = ridge_points(obj)
        d = np.full(len(m), 0.0, dtype=np.float32)
        for pid, pts in ridges.items():
            ii = np.nonzero(maps["part"][m] == pid)[0]
            if len(ii):
                d[ii] = P._kd_dist(pts, maps["pos"][m][ii], 5.0) / scale
        wob = (P.spread01(P.fbm(pos[m], 1.6, 2, seed=seed + 509)) - 0.5) * 0.12
        k = P.smoothstep(VALLEY["from"], VALLEY["to"], d + wob)
        glow = P.mix(np.repeat(P.hex3(VALLEY["rim"])[None], len(m), 0), P.hex3(VALLEY["hot"]),
                     P.smoothstep(0.5, 1.0, k))
        emis[m] = np.maximum(emis[m], glow * k[:, None])
        base[m] = P.mix(base[m], P.hex3(VALLEY["tint"]), k * 0.7)
        C.log("fold valleys: %.0f%% of the hide texels glow" % (100 * float((k > 0.1).mean())))
    # vents and grates: every ember part glows hot at its centre and dead ember at its rim
    if "ember" in zones_order:
        m = np.nonzero(Z == zones_order.index("ember"))[0]
        parts = maps["part"][m]
        core, hot, rim = P.hex3("#FFF0C8"), P.hex3("#D4B45A"), P.hex3("#8A3A1E")
        for pid in np.unique(parts):
            ii = m[parts == pid]
            pp = pos[ii]
            ctr = pp.mean(0)
            d = np.linalg.norm(pp - ctr, axis=1)
            d = d / max(1e-3, float(d.max()))
            wob = P.spread01(P.fbm(pp, 3.0, 2, seed=seed + 507)) * 0.25
            t = np.clip(d + wob - 0.1, 0.0, 1.0)
            e = P.mix(P.mix(np.repeat(core[None], len(ii), 0), hot, P.smoothstep(0.0, 0.45, t)), rim,
                      P.smoothstep(0.45, 0.95, t))
            emis[ii] = e
            base[ii] = P.mix(e, np.ones(3, dtype=np.float32), 0.2)
    return base, emis


def paint_bellows(obj, size, seed=5):
    """gfa_paint.paint_asset() at PAINT_SCALE, with gfa_brush broad planes on the bronze zones, this build's
    paint_extras() pass and then the decals. Writes the two PNGs, applies M_<key>, returns a report."""
    import time
    import numpy as np
    import gfa_brush as BR
    import gfa_paint as P
    t0 = time.time()
    s = PAINT_SCALE
    S = Matrix.Scale(s, 4)
    rec = {z: B._scale_recipe(r, s) for z, r in recipes().items()}
    decs = []
    for d in decals():
        d = dict(d)
        d["frame"] = [list(r) for r in (S @ Matrix(d["frame"]))]
        decs.append(d)
    broad = broad_zones()
    tex_dir = os.path.join(C.pack_dir(KIND, KEY), "textures")
    zones_order = [sl.material.name[4:] for sl in obj.material_slots]
    obj.data.transform(S)
    obj.data.update()
    try:
        frames = BR.part_frames(obj)
        dens = P.unwrap(obj, size, 4, UV_ANGLE, zone_scale={"void": 0.5}, small_islands=(0.3 * s * s, 0.55))
        mp = P.bake_maps(obj, size, 0.7 * s, 16)
        zone_img = mp["zone"][..., 0]
        valid = zone_img > 0.5 / 64
        ao_img = P.masked_blur(mp["ao"][..., 0], valid, radius=2, passes=2)
        lo, hi = mp["lo"], mp["hi"]
        flat = {
            "zone": np.rint(zone_img[valid] * 64 - 1).astype(np.int64),
            "pos": (mp["pos"][..., :3][valid] * (hi - lo) + lo).astype(np.float32),
            "tnrm": mp["tnrm"][..., :3][valid] * 2 - 1,
            "snrm": mp["snrm"][..., :3][valid] * 2 - 1,
            "part": np.rint(mp["part"][..., 0][valid] * 4096 - 1).astype(np.int64),
            "ao": ao_img[valid].astype(np.float32),
        }
        for k in ("tnrm", "snrm"):
            flat[k] = flat[k] / (np.linalg.norm(flat[k], axis=1, keepdims=True) + 1e-9)
        convex, concave = P.edge_points(obj, 0.002, 20.0)
        dv = P._kd_dist(convex, flat["pos"], 0.05)
        dc = P._kd_dist(concave, flat["pos"], 0.05)
        C.log("edge samples: %d convex / %d concave, %d texels" % (len(convex), len(concave), len(dv)))
        base, emis = P.paint(flat, zones_order, rec, dv, dc, decals=(), seed=seed)
        samples = {}
        for zname, b in broad.items():
            m = flat["zone"] == zones_order.index(zname)
            if not m.any():
                continue
            if 20.0 not in samples:
                samples[20.0] = BR.edge_samples(obj, 0.002, 20.0)
            pts, pids = samples[20.0]
            w_s = BR.stroke_weights(pts, b, seed, pids)
            d_z, cw = BR.own_edge_strokes(flat["pos"][m], flat["part"][m], pts, pids, w_s)
            base[m] = BR.repaint_broad(rec[zname], b, flat["pos"][m], flat["tnrm"][m], flat["part"][m], flat["ao"][m],
                                       dc[m], d_z, cw, frames, seed + 17 * zones_order.index(zname))
        paint_extras(P, flat, zones_order, base, emis, s, seed=seed, obj=obj)
        base, emis = BR.apply_decals(base, emis, flat["pos"], flat["tnrm"], flat["zone"], zones_order, decs)
        Bi = np.zeros((size, size, 3), dtype=np.float32)
        Ei = np.zeros((size, size, 3), dtype=np.float32)
        Bi[valid] = base
        Ei[valid] = emis
        Bi = P.dilate(Bi, valid, 12)
        Ei = P.dilate(Ei, valid, 12)
        C.ensure_dir(tex_dir)
        bp = os.path.join(tex_dir, "%s_basecolor.png" % KEY)
        ep = os.path.join(tex_dir, "%s_emissive.png" % KEY)
        P.save_png(bp, Bi, "%s_basecolor" % KEY)
        P.save_png(ep, Ei, "%s_emissive" % KEY)
        P.apply_final_material(obj, "M_%s" % KEY, bp, ep)
    finally:
        obj.data.transform(S.inverted())
        obj.data.update()
    rep = {"size": size, "paint_scale": s,
           "texel_density_px_per_m": {k: round(v * s, 1) for k, v in dens.items()},
           "coverage": round(float(valid.mean()), 3), "zones": zones_order, "broad_zones": sorted(broad),
           "decals": len(decs), "basecolor": C.rel(bp), "emissive": C.rel(ep),
           "emissive_texels": int((Ei.max(2) > 0.02).sum()), "seconds": round(time.time() - t0, 1)}
    C.log("painted in %.0fs (coverage %.0f%%, %s px/m)" % (rep["seconds"], 100 * rep["coverage"],
                                                          rep["texel_density_px_per_m"]))
    return rep


# ---- rig ----------------------------------------------------------------------------------------------

PELVIS = Vector((0.0, 0.55, 1.75))
HIND_DY = LEG["hind"][0][1] - PELVIS.y          # the hind hips sit this far behind the pelvis pivot


def rig_table():
    ln = tuple(lid_normal())
    t = [("root", None, (0.0, 0.0, 0.0)), ("pelvis", "root", tuple(PELVIS)), ("lid", "pelvis", tuple(HINGE))]
    t += [("pleat_%d" % i, "pelvis", tuple(HINGE)) for i in range(1, N_PLEAT + 1)]
    t += [("head", "pelvis", tuple(NECK)), ("mask_shard", "head", tuple(GEO["shard_c"]))]
    for bone, _sx in HATCHES:
        t.append((bone, "lid", tuple(GEO["hatch"][bone][0]), ln))     # along the lid normal: local Z = the hinge line
    for bone, *_ in CHIMNEYS:
        t.append((bone, "lid", tuple(GEO["chimney"][bone][0])))
    for kind, (hip, knee, ank, _paw) in LEG.items():
        for side, sx in (("L", 1), ("R", -1)):
            t += [("%s_thigh_%s" % (kind, side), "pelvis", (sx * hip[0], hip[1], hip[2])),
                  ("%s_shin_%s" % (kind, side), "%s_thigh_%s" % (kind, side), (sx * knee[0], knee[1], knee[2])),
                  ("%s_paw_%s" % (kind, side), "%s_shin_%s" % (kind, side), (sx * ank[0], ank[1], ank[2]))]
    return t


def sockets(arm):
    import gfa_rig as RIG
    socks = [("pelvis", "hit_center", (0.0, 0.3, 2.75)), ("head", "fx_core", core_pos()),
             ("head", "fx_mouth", mouth_pos()), ("head", "attack_origin", mouth_pos()),
             ("lid", "head_top", lid_pt(0.0, 0.6, 1.9))]
    for i, (bone, *_r) in enumerate(CHIMNEYS):
        socks.append((bone, "vent_%d" % (i + 1), GEO["chimney"][bone][1]))
    for bone, _sx in HATCHES:
        socks.append(("lid", "hatch_vent_" + bone[-1], GEO["hatch"][bone][1]))
    for kind, (_h, _k, _a, paw) in LEG.items():
        for side, sx in (("L", 1), ("R", -1)):
            socks.append(("%s_paw_%s" % (kind, side), "paw_fx_%s_%s" % (kind, side), (sx * paw[0], paw[1] - 0.2, 0.0)))
    out = {}
    for bone, name, pos in socks:
        RIG.add_socket(arm, bone, name, tuple(pos), size=0.3)
        out[name] = {"bone": bone, "blender_pos": [round(v, 3) for v in pos],
                     "gltf_pos": [round(v, 3) for v in C.blender_to_gltf(pos)]}
    return out


# ---- clips ----------------------------------------------------------------------------------------------
# Every clip keys EVERY bone (gfa_rig.keyed_clip / cycle_clip), so each clip states its phase: Stoke clips hold
# the fire hatches shut and the mask whole; Blaze clips (the _p2 twins, strike_circle, death) hold the hatches
# blown open and the left-cheek shard scaled to 0.001. `phase2` is the change.
# Pose axes (bone frame = creature frame): +X pitches nose-down / swings a hanging leg BACK, +Y yaws left,
# +Z rolls the left side up. Hatch bones point along the lid normal, so their Z is the hatch hinge line.
HIDE = 0.001
HATCH_OPEN = 118.0
LEG_SEG = 0.78               # thigh / shin segment length used for the knee fold
LEG_L = 1.2                  # hip-to-ankle height


def pose(*parts):
    out = {}
    for p in parts:
        for b, tr in p.items():
            out.setdefault(b, {}).update(tr)
    return out


def state(phase, hatch=0.0):
    if phase == 1:
        return {"hatch_L": {"rot": (0, 0, 0)}, "hatch_R": {"rot": (0, 0, 0)}, "mask_shard": {"scale": 1.0}}
    a = HATCH_OPEN + hatch
    return {"hatch_L": {"rot": (0, 0, -a)}, "hatch_R": {"rot": (0, 0, a)}, "mask_shard": {"scale": HIDE}}


def K(phase, *poses):
    return pose(state(phase), *poses)


def lung(d=0.0, swell=1.0):
    """The breath: the lid opens by d degrees about its hinge and every fold follows its share of the opening;
    swell > 1 fattens the folds (the middle ones most), < 1 crushes them flat."""
    p = {"lid": {"rot": (d, 0, 0)}}            # +X about the hinge lifts the lid's rear: opens
    for i in range(1, N_PLEAT + 1):
        f = pleat_frac(i)
        w = math.sin(math.pi * f) ** 0.6
        sc = 1.0 + (swell - 1.0) * w
        p["pleat_%d" % i] = {"rot": (f * d, 0, 0), "scale": (sc, 1.0 + (sc - 1.0) * 0.5, 1.0 + (sc - 1.0) * 0.45)}
    return p


def chim(r1=(0, 0, 0), r2=(0, 0, 0), r3=(0, 0, 0), s1=1.0, s2=1.0, s3=1.0):
    return {"chimney_1": {"rot": r1, "scale": (1.0, s1, 1.0)}, "chimney_2": {"rot": r2, "scale": (1.0, s2, 1.0)},
            "chimney_3": {"rot": r3, "scale": (1.0, s3, 1.0)}}


def fold_for(drop):
    """Knee fold (deg) that shortens a leg by `drop` m (two equal segments folding symmetrically)."""
    c = max(-1.0, min(1.0, 1.0 - max(0.0, drop) / (2 * LEG_SEG)))
    return math.degrees(math.acos(c))


def leg(kind, side, swing=0.0, fold=0.0, curl=0.0):
    """One leg: swing = the thigh's pitch (deg, + = back), fold = knee fold (front legs fold the elbow back, hind
    legs the knee forward), the paw kept level plus `curl`."""
    sg = 1.0 if kind == "front" else -1.0
    t = swing + sg * fold
    sh = -2.0 * sg * fold
    return {"%s_thigh_%s" % (kind, side): {"rot": (t, 0, 0)}, "%s_shin_%s" % (kind, side): {"rot": (sh, 0, 0)},
            "%s_paw_%s" % (kind, side): {"rot": (-(t + sh) + curl, 0, 0)}}


def body(pitch=0.0, drop=0.0, fwd=0.0, roll=0.0, yaw=0.0, lift=None):
    """The chassis: pitch (+ = nose down) about the pelvis with the hind hips held at their height, lowered by
    `drop`; planted legs counter-rotate and fold so their paws stay down. lift: {(kind, side): (swing, fold)}
    for legs in the air."""
    sp = math.sin(math.radians(pitch))
    up = -HIND_DY * sp
    p = {"root": {"loc": (0.0, up - drop, fwd)}, "pelvis": {"rot": (pitch, yaw, roll)}}
    for kind in ("front", "hind"):
        dy = LEG[kind][0][1] - PELVIS.y
        hip_dz = dy * sp + up - drop
        for side in "LR":
            if lift and (kind, side) in lift:
                sw, fo = lift[(kind, side)]
                p.update(leg(kind, side, -pitch + sw, fo))
            else:
                p.update(leg(kind, side, -pitch, fold_for(-hip_dz)))
    return p


def head(pitch=0.0, yaw=0.0, roll=0.0, fwd=0.0):
    return {"head": {"rot": (pitch, yaw, roll), "loc": (0.0, 0.0, fwd)}}


def shake(k, amp=1.0):
    r = random.Random(1000 + k)
    return {"pelvis": {"rot": (amp * r.uniform(-1, 1), amp * r.uniform(-1, 1), amp * r.uniform(-1, 1))},
            "head": {"rot": (amp * 2 * r.uniform(-1, 1), amp * 2 * r.uniform(-1, 1), 0)}}


def addp(a, b):
    """Add two poses channel by channel (rot and loc sum; scale from b, else a)."""
    out = {}
    for bn in set(a) | set(b):
        A_, B_ = a.get(bn, {}), b.get(bn, {})
        d = {}
        for ch in ("rot", "loc"):
            if ch in A_ or ch in B_:
                d[ch] = tuple(x + y for x, y in zip(A_.get(ch, (0, 0, 0)), B_.get(ch, (0, 0, 0))))
        if "scale" in A_ or "scale" in B_:
            d["scale"] = B_.get("scale", A_.get("scale"))
        out[bn] = d
    return out


def breath(t, amp=1.0, rate=1, p2=False):
    """The idle breath for t in [0, 1): the lid rises and falls `rate` times, the folds swell, the head lifts on
    the inhale; Blaze breathes deeper and the open hatches flutter."""
    w = 2 * math.pi * rate * t
    inh = 0.5 - 0.5 * math.cos(w)                       # 0 -> 1 -> 0
    p = pose(lung(6.5 * amp * inh, 1.0 + 0.1 * amp * inh),
             body(pitch=-0.8 * amp * inh, drop=0.03 * amp * (1 - inh), roll=0.8 * math.sin(w * 0.5 + 0.4)),
             head(-4.0 * amp * inh + 1.5 * math.sin(w + 1.2), 2.5 * math.sin(2 * math.pi * t + 0.7)),
             chim((1.5 * inh, 0, 1.5 * math.sin(w + 0.5)), (-1.5 * inh, 0, -1.2 * math.sin(w + 1.3)),
                  (1.0 * inh, 0, 0), 1.0 + 0.04 * inh, 1.0 + 0.03 * inh, 1.0))
    if p2:
        f = 7.0 * math.sin(2 * math.pi * 3 * t)
        p = pose(p, {"hatch_L": {"rot": (0, 0, -(HATCH_OPEN + f))}, "hatch_R": {"rot": (0, 0, HATCH_OPEN - f)},
                     "mask_shard": {"scale": HIDE}})
    return p


GAIT_PHASE = {("hind", "L"): 0.0, ("front", "L"): 0.25, ("hind", "R"): 0.5, ("front", "R"): 0.75}


def gait(t, A=22.0, S=0.65, p2=False):
    """One lateral-sequence walk cycle (LH, LF, RH, RF) for t in [0, 1): each paw is planted for S of the
    cycle, sweeping from -A (forward) to +A (back) with the knee folded so it stays on the ground."""
    d0 = LEG_L * (1 - math.cos(math.radians(A)))           # the body rides this much lower while walking
    p = {}
    for (kind, side), ph in GAIT_PHASE.items():
        q = (t + ph) % 1.0
        if q < S:
            th = -A + 2 * A * q / S
            lift = 0.0
        else:
            u = (q - S) / (1 - S)
            th = A - 2 * A * (0.5 - 0.5 * math.cos(math.pi * u))
            lift = math.sin(math.pi * u)
        need = LEG_L * (1 - math.cos(math.radians(A)) / max(0.5, math.cos(math.radians(th))))
        p.update(leg(kind, side, th - 6 * lift, fold_for(need) + 30 * lift, 14 * lift))
    w = 2 * math.pi * t
    thud = 0.035 * (0.5 + 0.5 * math.cos(4 * w))            # four footfalls a cycle
    p["root"] = {"loc": (0.08 * math.sin(w), -d0 - thud, 0.0)}
    p["pelvis"] = {"rot": (1.2 * math.sin(4 * w + 0.6), 2.5 * math.sin(w + 0.4), 2.2 * math.sin(w))}
    br = 0.5 - 0.5 * math.cos(2 * w)
    p = pose(p, lung(2.5 * br, 1.0 + 0.04 * br), head(1.5 * math.sin(4 * w + 1.0), -3.0 * math.sin(w + 0.4)),
             chim((2.0 * math.sin(4 * w), 0, 2.0 * math.sin(w)), (2.0 * math.sin(4 * w + 0.7), 0, -2.0 * math.sin(w)),
                  (1.5 * math.sin(4 * w + 1.4), 0, 0)))
    if p2:
        f = 9.0 * math.sin(2 * math.pi * 4 * t)
        p = pose(p, {"hatch_L": {"rot": (0, 0, -(HATCH_OPEN + f))}, "hatch_R": {"rot": (0, 0, HATCH_OPEN - f)},
                     "mask_shard": {"scale": HIDE}})
    return p


def move_cycle_m(A=22.0, S=0.65):
    """Metres the body travels per walk cycle (the planted paw sweeps 2 L sin A in S of the cycle)."""
    return round(2 * 1.7 * math.sin(math.radians(A)) / S, 3)


# key poses (phase-free; K(phase, ...) adds the phase state)
INHALE = pose(lung(12.0, 1.17), body(pitch=-3.0, drop=0.12), head(-16.0),
              chim((-5, 0, 3), (-5, 0, -3), (-4, 0, 0), 1.06, 1.06, 1.0))
INHALE2 = pose(INHALE, lung(13.5, 1.2), head(-19.0))
EXHALE = pose(lung(-7.0, 0.86), body(pitch=4.0, drop=0.22, fwd=0.25), head(9.0, fwd=0.25),
              chim((7, 0, -3), (7, 0, 3), (6, 0, 0), 0.9, 0.92, 0.95))
EXHALE_HOLD = pose(EXHALE, lung(-5.5, 0.88), head(6.0, fwd=0.2))
FLINCH = pose(lung(5.0, 1.06), body(pitch=-4.0, drop=0.05, roll=-4.0, fwd=-0.15), head(-12.0, 9.0, 4.0),
              chim((-6, 0, 5), (-7, 0, -6), (-5, 0, 3)))


def rear_pose(d=13.0, swell=1.2, pitch=-11.0):
    """Reared on the hind legs, the front paws lifted, a full breath held."""
    return pose(lung(d, swell), body(pitch=pitch, drop=0.05, lift={("front", "L"): (-30.0, 34.0), ("front", "R"): (-26.0, 30.0)}),
                head(-18.0), chim((-7, 0, 3), (-7, 0, -3), (-6, 0, 0), 1.08, 1.08, 1.0))


def slam_pose(fwd=0.2):
    """The front paws slam down and the lid slams shut: the whole bag blasts out round the body (the ring)."""
    return pose(lung(-8.5, 0.82), body(pitch=5.0, drop=0.3, fwd=fwd), head(12.0, fwd=0.1),
                chim((9, 0, -4), (9, 0, 4), (8, 0, 0), 0.88, 0.9, 0.94))


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

    mc = move_cycle_m()
    # ---- loops
    loop("idle@loop", 96, lambda t: K(1, breath(t)), 1)
    loop("move@loop", 48, lambda t: K(1, gait(t)), 1, {"move_cycle_m": mc})
    loop("idle_p2@loop", 96, lambda t: K(2, breath(t, 1.35, 2, True)), 2)
    loop("move_p2@loop", 40, lambda t: K(2, gait(t, 24.0, 0.62, True)), 2, {"move_cycle_m": move_cycle_m(24.0, 0.62)})
    b1, b2 = K(1, breath(0.0)), K(2, breath(0.0, 1.35, 2, True))
    for ph, sfx in ((1, ""), (2, "_p2")):
        base = b1 if ph == 1 else b2
        # windup = INHALE (the verb's first half): brace, the lid heaves open, the folds swell; ends loaded
        one("windup" + sfx, [(0, base), (8, K(ph, lung(-2.0, 0.97), body(pitch=1.5, drop=0.1), head(4.0))),
                             (24, K(ph, INHALE)), (30, K(ph, INHALE2))], {"loaded": 1.0}, ph)
        # attack = BREATHE: the lid slams shut, the mask thrusts, fire pours out of the O (release on frame 4)
        one("attack" + sfx, [(0, K(ph, INHALE2)), (4, K(ph, EXHALE)), (7, K(ph, addp(EXHALE, shake(1, 1.2)))),
                             (12, K(ph, EXHALE_HOLD)), (16, K(ph, addp(EXHALE_HOLD, shake(2, 0.8)))),
                             (20, K(ph, EXHALE_HOLD)), (34, base)], {"release": 0.133, "breath_end": 0.667}, ph)
        one("hit" + sfx, [(0, base), (3, K(ph, FLINCH)), (7, K(ph, addp(FLINCH, shake(3, 1.0)))), (15, base)], None, ph)
        # radial: squat and suck, then two hard pumps: every vent barks embers (release on the first pump)
        squat = pose(lung(9.0, 1.14), body(pitch=1.0, drop=0.3), head(-6.0),
                     chim((-3, 0, 0), (-3, 0, 0), (-3, 0, 0), 1.05, 1.05, 1.0))
        pump = pose(lung(-8.0, 0.84), body(pitch=-2.0, drop=0.05), head(-10.0),
                    chim((-8, 0, 7), (-8, 0, -8), (-6, 0, 4), 1.22, 1.24, 1.15))
        pump2 = pose(pump, lung(-6.0, 0.86), chim((-6, 0, -6), (-6, 0, 7), (-5, 0, -4), 1.18, 1.2, 1.12))
        one("radial" + sfx, [(0, base), (11, K(ph, squat)), (15, K(ph, pump)), (19, K(ph, squat, lung(4.0, 1.05))),
                             (23, K(ph, pump2)), (27, K(ph, addp(pump2, shake(4, 1.0)))), (48, base)],
            {"release": 0.5, "second_release": 0.767}, ph)
        # summon: head down to the ground, three heaves; a coal is born out of the O on each (cinderlings in
        # Stoke, emberwisps in Blaze)
        bow = pose(lung(5.0, 1.08), body(pitch=7.0, drop=0.25), head(30.0, fwd=0.1),
                   chim((4, 0, 0), (4, 0, 0), (4, 0, 0)))
        heave = pose(lung(-5.0, 0.88), body(pitch=9.0, drop=0.32, fwd=0.12), head(38.0, fwd=0.35),
                     chim((7, 0, -3), (7, 0, 3), (6, 0, 0), 0.92, 0.92, 0.96))
        refill = pose(bow, lung(6.0, 1.1))
        one("summon" + sfx, [(0, base), (12, K(ph, bow)), (19, K(ph, heave)), (25, K(ph, refill)), (30, K(ph, heave)),
                             (36, K(ph, refill)), (41, K(ph, heave)), (45, K(ph, addp(heave, shake(5, 0.8)))),
                             (62, base)], {"spawn": [0.633, 1.0, 1.367]}, ph)
    # strike_ring (both phases, at_self): rear up on the hind legs with a full breath, slam the front paws down;
    # the lid slams and the bag blasts a ring round the body. Impact on the bosses.ron windup (1.0 s / 0.9 s).
    for ph, sfx, imp in ((1, "", 30), (2, "_p2", 27)):
        base = b1 if ph == 1 else b2
        sl = slam_pose()
        one("strike_ring" + sfx, [(0, base), (8, K(ph, body(pitch=2.0, drop=0.18), lung(-2.0, 0.96), head(5.0))),
                                  (imp - 8, K(ph, rear_pose())), (imp - 3, K(ph, rear_pose(14.5, 1.22, -13.0))),
                                  (imp, K(ph, sl)), (imp + 3, K(ph, addp(sl, shake(6, 1.8)))),
                                  (imp + 7, K(ph, addp(sl, shake(7, 1.0)))), (imp + 12, K(ph, sl)),
                                  (imp + 32, base)], {"impact": round(imp / FPS, 3)}, ph)
    # strike_circle (Blaze): inhale, aim at the target, lob a gout of fire (release) that lands on the 0.9 s impact
    aim = pose(INHALE2, head(-4.0), body(pitch=-1.0, drop=0.15))
    lob = pose(lung(-7.5, 0.86), body(pitch=-3.0, drop=0.1, fwd=0.2), head(-24.0, fwd=0.25),
               chim((6, 0, -3), (6, 0, 3), (5, 0, 0), 0.9, 0.92, 0.95))
    one("strike_circle", [(0, b2), (8, K(2, lung(-2.0, 0.97), body(pitch=1.5, drop=0.1), head(4.0))),
                          (16, K(2, INHALE2)), (19, K(2, aim)), (22, K(2, lob)), (27, K(2, addp(lob, shake(8, 1.0)))),
                          (33, K(2, lob, head(-14.0))), (54, b2)], {"release": 0.733, "impact": 0.9}, 2)
    # phase2 (Stoke -> Blaze): heaving, a breath too big, the left cheek cracks off the mask and falls, the fire
    # hatches blow open; the shard ends on the ground and scales away
    sc = GEO["shard_c"]
    fall_to = Vector((sc.x + 0.9, sc.y - 1.2, 0.35))
    local = fall_to - sc                              # bone frame = creature frame: (x left, y up, z fwd)
    heave1 = pose(lung(10.0, 1.15), body(pitch=-2.0, drop=0.1), head(-12.0))
    burst = pose(lung(16.0, 1.26), body(pitch=-6.0, drop=0.0), head(-22.0, 0, -6.0),
                 chim((-9, 0, 6), (-9, 0, -7), (-7, 0, 5), 1.25, 1.25, 1.18))
    keys = [(0, b1), (10, K(1, heave1)), (14, K(1, addp(heave1, shake(9, 1.4))))]
    keys += [(14 + 3 * k, K(1, addp(heave1, shake(10 + k, 1.2 + 0.3 * k)))) for k in range(1, 7)]
    keys += [(36, K(1, burst, {"hatch_L": {"rot": (0, 0, -40)}, "hatch_R": {"rot": (0, 0, 40)},
                               "mask_shard": {"loc": (0.08, -0.05, 0.25), "rot": (-12, 0, 18), "scale": 1.0}})),
             (40, K(1, burst, {"hatch_L": {"rot": (0, 0, -(HATCH_OPEN + 25))}, "hatch_R": {"rot": (0, 0, HATCH_OPEN + 25)},
                               "mask_shard": {"loc": (local.x * 0.3, local.z * 0.3 + 0.3, -local.y * 0.3),
                                              "rot": (-40, 10, 60), "scale": 1.0}})),
             (48, K(1, burst, {"hatch_L": {"rot": (0, 0, -HATCH_OPEN)}, "hatch_R": {"rot": (0, 0, HATCH_OPEN)},
                               "mask_shard": {"loc": (local.x, local.z, -local.y), "rot": (-80, 20, 110), "scale": 1.0}})),
             (56, K(2, pose(lung(-6.0, 0.88), body(pitch=4.0, drop=0.2), head(10.0)),
                    {"mask_shard": {"loc": (local.x, local.z, -local.y), "rot": (-90, 20, 115), "scale": 1.0}})),
             (60, K(2, pose(lung(-6.0, 0.88), body(pitch=4.0, drop=0.2), head(10.0)),
                    {"mask_shard": {"loc": (local.x, local.z, -local.y), "rot": (-90, 20, 115), "scale": HIDE}})),
             (78, b2)]
    one("phase2", keys, {"crack": 1.2, "burst": 1.333}, "1to2")
    # death (always in Blaze): a last gasp, the legs buckle front first, the bag sags and the lid slams shut,
    # the tall chimney topples, the mask face-plants; ends held
    gasp = pose(lung(15.0, 1.22), body(pitch=-5.0, drop=0.0), head(-24.0, 6.0, 5.0),
                chim((-8, 0, 6), (-8, 0, -6), (-6, 0, 3), 1.2, 1.2, 1.1))
    kneel = pose(lung(-4.0, 0.92), body(pitch=12.0, drop=0.55, roll=-5.0), head(26.0, -5.0, -4.0),
                 chim((10, 0, -12), (6, 0, 8), (5, 0, 0)))
    down = pose(lung(-9.0, 0.78), {"root": {"loc": (0.0, -1.05, 0.1)}, "pelvis": {"rot": (6.0, 3.0, -7.0)}},
                leg("front", "L", -62.0, 6.0, 20.0), leg("front", "R", -66.0, 4.0, 22.0),
                leg("hind", "L", 58.0, 8.0, -18.0), leg("hind", "R", 62.0, 6.0, -18.0),
                head(34.0, -6.0, -8.0), chim((12, 0, -58), (8, 0, 14), (6, 0, -6), 0.95, 1.0, 1.0))
    one("death", [(0, b2), (6, K(2, gasp)), (12, K(2, addp(gasp, shake(20, 1.6)))), (18, K(2, gasp)),
                  (34, K(2, kneel)), (40, K(2, addp(kneel, shake(21, 1.4)))), (58, K(2, down)),
                  (63, K(2, addp(down, {"root": {"loc": (0, 0.06, 0)}}))), (68, K(2, down)), (90, K(2, down))],
        {"collapse": 1.933}, 2)
    return clips


ALIASES = {  # the brief's names -> the contract clip they duplicate (docs/art/ENEMIES.md section 6)
    "inhale": "windup", "breathe": "attack", "inhale_p2": "windup_p2", "breathe_p2": "attack_p2",
    "walk@loop": "move@loop", "blaze_idle@loop": "idle_p2@loop", "phase_transition": "phase2",
}
CLIP_ORDER = ["idle@loop", "move@loop", "windup", "attack", "hit", "radial", "summon", "strike_ring", "phase2",
              "idle_p2@loop", "move_p2@loop", "windup_p2", "attack_p2", "hit_p2", "radial_p2", "summon_p2",
              "strike_ring_p2", "strike_circle", "death"]


def clip_track(c):
    return "%s_%s" % (KEY, c)


# ---- review ---------------------------------------------------------------------------------------------

def _pose(arm, clip, frame=0):
    import gfa_rig as RIG
    RIG.pose_at(arm, clip_track(clip), frame)


def _party(positions):
    out = []
    for i, (x, y) in enumerate(positions):
        m = R.mannequin(aim_dir=(-x, -y, 0.0), name="GFA_HERO_%d" % i)
        m.location = (x, y, 0.0)
        out.append(m)
    bpy.context.view_layer.update()
    return out


def key_poses(info, n=5):
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


def review(mesh, arm, rep, paint_rep, clips, lite=False):
    import gfa_rig as RIG
    scene = bpy.context.scene
    pack = C.pack_dir(KIND, KEY)
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    work = C.ensure_dir(os.path.join(pack, "work", "review"))
    tex = [os.path.join(pack, "textures", KEY + "_basecolor.png"), os.path.join(pack, "textures", KEY + "_emissive.png")]
    # hero shots (the first look): Stoke and Blaze, 3/4 front
    hero = {}
    for ph, clip in ((1, "idle@loop"), (2, "idle_p2@loop")):
        _pose(arm, clip, 0)
        hero[ph] = R.turnaround([mesh], work, KEY + "_hero_p%d" % ph, {"34": (0.62, -0.72, 0.34)}, size=760,
                                samples=14)["34"]
    # the game camera at true 1080p pixels: 4 heroes at the fight distance (keep_distance 6 m)
    party = _party([(-5.2, -6.2), (4.6, -6.6), (7.2, -1.4), (-7.0, -0.8)])
    ing = {}
    _pose(arm, "idle@loop", 0)
    pts = R._points([mesh] + party)
    tgt, _, _ = R.frame(pts, B.game_dir())
    ing["p1_22"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p1_22.png"), 1200, 760, 22.0, tgt, party,
                                  silhouette_path=os.path.join(work, KEY + "_ingame_p1_22_sil.png"))
    ing["p1_28"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p1_28.png"), 1200, 760, 28.0, tgt, party)
    _pose(arm, "idle_p2@loop", 0)
    arm.rotation_euler = (0.0, 0.0, math.radians(35.0))
    bpy.context.view_layer.update()
    ing["p2_22"] = B.ingame_frame([mesh], os.path.join(work, KEY + "_ingame_p2_22.png"), 1200, 760, 22.0, tgt, party,
                                  silhouette_path=os.path.join(work, KEY + "_ingame_p2_22_sil.png"))
    arm.rotation_euler = (0.0, 0.0, 0.0)
    C.remove_objects(party)
    # the verb at game size: rest, inhaled (windup end), breathing out (attack release), crushed (summon heave)
    verb = []
    vt = Vector((0.0, 0.35, 1.2))
    for clip, f, label in (("idle@loop", 0, "rest"), ("windup", 30, "INHALE (windup end)"),
                           ("attack", 4, "BREATHE (attack release)"), ("summon", 19, "vomit a cinderling (summon)")):
        _pose(arm, clip, f)
        pth = os.path.join(work, "%s_verb_%s_%d.png" % (KEY, clip.replace("@", "_"), f))
        B.ingame_frame([mesh], pth, 470, 520, 22.0, vt)
        verb.append({"path": pth, "label": label + ", 1x", "scale": 1})
    for clip, f, label in (("idle@loop", 0, "rest"), ("windup", 30, "inhale"), ("attack", 4, "breathe")):
        _pose(arm, clip, f)
        pth = os.path.join(work, "%s_verb_side_%s_%d.png" % (KEY, clip.replace("@", "_"), f))
        arm.rotation_euler = (0.0, 0.0, math.radians(90.0))
        bpy.context.view_layer.update()
        B.ingame_frame([mesh], pth, 520, 470, 22.0, Vector((0.0, 0.0, 1.4)))
        arm.rotation_euler = (0.0, 0.0, 0.0)
        verb.append({"path": pth, "label": label + ", side-on, 1x", "scale": 1})
    RIG.unmute_none(arm)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    first_look_sheets(hero, ing, verb, reports if not lite else work, work)
    if lite:
        return {"hero": hero, "ingame": ing}
    # turnarounds: Stoke (idle frame 0) and Blaze (idle_p2 frame 0)
    _pose(arm, "idle@loop", 0)
    turn1 = R.turnaround([mesh], work, KEY + "_p1", R.CREATURE_VIEWS, size=400, samples=10)
    _pose(arm, "idle_p2@loop", 0)
    v2 = {k: R.CREATURE_VIEWS[k] for k in ("front", "34_front", "side", "top")}
    v2["game"] = tuple(B.game_dir())
    turn2 = R.turnaround([mesh], work, KEY + "_p2", v2, size=400, samples=10)
    _pose(arm, "idle@loop", 0)
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0), name="GFA_HERO_SIZE")
    man.location = (4.4, -1.0, 0.0)
    bpy.context.view_layer.update()
    size_png = B.size_compare([mesh], os.path.join(work, KEY + "_size.png"), man, w=1100, h=620, pole_height=6)
    C.remove_objects([man])
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    # clip key frames (3/4 front, one shared scale)
    strips = B.clip_frames(arm, [mesh], [clip_track(c) for c in CLIP_ORDER], work, KEY, frames=4, size=280,
                           direction=(0.62, -0.72, 0.34), ext=9.0, center=(0.0, -0.3, 2.1), samples=6, ink=0.03,
                           frame_lists={clip_track(c): key_poses(clips[c], 5) for c in CLIP_ORDER
                                        if not c.endswith("@loop")})
    RIG.unmute_none(arm)
    scene.frame_set(0)
    thumbs = R._thumbs(tex, work)
    notes = [
        "%s tris (mini-boss budget 10,000-20,000) | textures %s | %.2f m tall = %.2f x the 2.2 m hero | footprint "
        "%.1f x %.1f m (sim collider radius 2.56 m)" % (
            "{:,}".format(rep["tris"]), " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"],
            rep["height_m"] / SPEC.HERO_HEIGHT, rep["bounds"]["max"][0] - rep["bounds"]["min"][0],
            rep["bounds"]["max"][2] - rep["bounds"]["min"][2]),
        "Rig %s: %d joints, rigid skin; %d clips (+%d brief-name aliases); the phase state lives in the clips "
        "(hatches shut + mask whole in Stoke, hatches open + shard at scale 0.001 in Blaze)." % (
            RIG_NAME, len(arm.data.bones), len(clips), len(ALIASES)),
        "Painted at 1/4 scale: %s px/m median texel density, UV coverage %.0f %%. Status: %s." % (
            paint_rep["texel_density_px_per_m"].get("median"), 100 * paint_rep["coverage"], SPEC.STATUS_AI_FINAL),
    ]
    layout = {
        "title": "The Bellows  (the_bellows)",
        "subtitle": "Mini-boss | Cinder Wastes Warlord | Fallen Godworks | verb: BREATHE | Stoke / Blaze",
        "width": 1600,
        "sections": [
            {"label": "Stoke (phase 1) turnaround - toon preview of the final textures (ramp, rim, ink; emissive x1.6)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn1.items()]},
            {"label": "Blaze (phase 2): fire hatches blown open, the left cheek broken off the mask (idle_p2 frame 0)",
             "height": 250, "images": [{"path": v, "label": k} for k, v in turn2.items()]},
            {"label": "Size: front view beside the 2.2 m hero mannequin and a 6 m pole (1 m bands, every 5th light)",
             "height": 440, "images": [{"path": size_png, "label": "size comparison"}]},
            {"label": "Textures (base colour, emissive)", "height": 240,
             "images": [{"path": p, "label": lb} for p, lb in thumbs]},
        ],
        "swatches": [{"hex": h, "label": n} for n, h in PALETTE],
        "notes": notes,
    }
    R.contact_sheet(layout, os.path.join(reports, KEY + "_review.png"), work)
    groups = [("Stoke loops and the verb: inhale (windup), breathe (attack), hit", CLIP_ORDER[:5]),
              ("Stoke attacks: radial (the vents bark), summon (cinderlings out of the O), strike_ring (rear and slam)",
               CLIP_ORDER[5:8]),
              ("Stoke -> Blaze and the Blaze loops", CLIP_ORDER[8:11]),
              ("Blaze twins", CLIP_ORDER[11:17]),
              ("Blaze: strike_circle (the lobbed gout) and death", CLIP_ORDER[17:])]
    secs = []
    for label, names in groups:
        imgs = []
        for c in names:
            for cl, f, pth in strips:
                if cl == clip_track(c):
                    imgs.append({"path": pth, "label": "%s f%d" % (c, f)})
        secs.append({"label": label, "height": 168, "images": imgs})
    lay3 = {"title": "The Bellows - clip key frames", "subtitle": "3/4 front, one shared scale, 30 fps; loops: 4 "
            "evenly spaced frames; one-shots: the key poses (start, loaded, event, follow-through, end)",
            "width": 1600, "sections": secs,
            "notes": ["Brief-name aliases (same action, second track): " +
                      ", ".join("%s = %s" % kv for kv in ALIASES.items()),
                      "; ".join("%s %.2f s" % (c, clips[c]["seconds"]) for c in CLIP_ORDER[:10]),
                      "; ".join("%s %.2f s" % (c, clips[c]["seconds"]) for c in CLIP_ORDER[10:])]}
    R.contact_sheet(lay3, os.path.join(reports, KEY + "_clips.png"), work)
    return {"turn1": turn1, "turn2": turn2, "size": size_png, "ingame": ing, "hero": hero}


def first_look_sheets(hero, ing, verb, out_dir, work):
    R.contact_sheet({"title": "The Bellows - Stoke (phase 1) and Blaze (phase 2)",
                     "subtitle": "3/4 front, toon preview of the final textures (engine-like ramp, rim, ink; emissive x1.6)",
                     "width": 1560, "sections": [{"label": "", "height": 740, "images": [
                         {"path": hero[1], "label": "Stoke: hatches shut, mask whole"},
                         {"path": hero[2], "label": "Blaze: fire hatches open, the cheek broken off"}]}]},
                    os.path.join(out_dir, KEY + "_34.png"), work)
    ppm22, ppm28 = SPEC.SCREEN_H / 22.0, SPEC.SCREEN_H / 28.0
    lay = {
        "title": "The Bellows - in-game camera at true pixel size",
        "subtitle": "orthographic, 55 deg pitch, yaw 0; crops of the 1080p frame; four 2.2 m hero mannequins at the "
                    "fight distance",
        "width": 1600,
        "sections": [
            {"label": "Stoke, 1 player (view height 22 m = %.1f px/m), 1x" % ppm22, "height": None,
             "images": [{"path": ing["p1_22"]["color"], "label": "Stoke, 22 m"}]},
            {"label": "Blaze, turned 35 deg, 22 m, 1x", "height": None,
             "images": [{"path": ing["p2_22"]["color"], "label": "Blaze, 22 m"}]},
            {"label": "4 players (view height 28 m = %.1f px/m), 1x" % ppm28, "height": None,
             "images": [{"path": ing["p1_28"]["color"], "label": "Stoke, 28 m"}]},
            {"label": "Game-size silhouettes (22 m, shown at half size)", "height": 380,
             "images": [{"path": ing["p1_22"]["sil"], "label": "Stoke"}, {"path": ing["p2_22"]["sil"], "label": "Blaze"}]},
        ],
        "notes": ["The engine draws the red-white telegraph decals and the fire; the model carries none."],
    }
    R.contact_sheet(lay, os.path.join(out_dir, KEY + "_ingame.png"), work)
    R.contact_sheet({"title": "The Bellows - the verb BREATHE at game size",
                     "subtitle": "the game camera at 22 m (49.1 px/m), true pixels: the lid heaves open and the folds swell "
                                 "(the furnace shows between them), then the lid slams and the folds crush flat",
                     "width": 1600, "sections": [{"label": "Facing the camera, then side-on", "height": None,
                                                  "images": verb}],
                     "notes": ["Fire, embers and the spawned cinderlings are engine VFX at fx_mouth / vent_1..2 / "
                               "hatch_vent_L/R; the model carries no red-white."]},
                    os.path.join(out_dir, KEY + "_verb.png"), work)


def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 2048, int)
    C.reset_scene(fps=FPS)
    bpy.context.preferences.filepaths.save_version = 0
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
    paint_rep = paint_bellows(mesh, size, seed=5)
    arm = B.build_rig(RIG_NAME, rig_table(), col=col, bone_len=0.4)
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
                "rest": "every bone points up with roll 0 (creature frame: X left, Y up, Z forward) except hatch_L/R, "
                        "which point along the lid normal (local Z = the hatch hinge line)"},
        "boss_sockets": socks,
        "clip_info": clips,
        "clip_aliases": {clip_track(a_): clip_track(c_) for a_, c_ in ALIASES.items()},
        "phases": {
            "Stoke": {"below": 1.0, "loops": ["idle@loop", "move@loop"],
                      "attacks": {"Radial": "radial", "Summon": "summon", "Strike(Ring, at_self)": "strike_ring"},
                      "body": "fire hatches shut, the porcelain mask whole"},
            "Blaze": {"below": 0.5, "enter": "phase2", "loops": ["idle_p2@loop", "move_p2@loop"],
                      "attacks": {"Radial": "radial_p2", "Summon": "summon_p2", "Strike(Circle)": "strike_circle",
                                  "Strike(Ring, at_self)": "strike_ring_p2"},
                      "body": "fire hatches blown open, the mask's left cheek broken off (the furnace shows)"},
        },
        "phase_switch": "Clips carry the phase: every clip keys every joint. Stoke clips hold hatch_L/R shut and "
                        "mask_shard at scale 1; phase2 blows the hatches open and drops the shard (scale 0.001 at "
                        "its end); Blaze clips hold that state. In Blaze play '<clip>_p2' when it exists, else "
                        "'<clip>' (strike_circle and death are authored with the Blaze body). Generic windup / attack "
                        "are the verb: windup = the inhale (ends loaded, time-stretch to the sim windup), attack = the "
                        "breath (fire VFX from fx_mouth at events_s.release).",
        "move_cycle_m": {"move@loop": move_cycle_m(), "move_p2@loop": move_cycle_m(24.0, 0.62)},
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage", "paint_scale", "broad_zones")},
        "row": {"hp": 7000, "speed": 1.8, "radius": 1.6, "scale": 1.6, "collider_radius_m": 2.56, "mass": 12,
                "color": "#B5532A", "shape": "Colossus", "open_world": "Cinder Wastes Warlord POI (docs/OPEN_WORLD.md)"},
        "faction": "fallen_godworks",
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.write_json(os.path.join(pack, "reports", "build_report.json"),
                 {"export": {k: v for k, v in rep.items() if k != "nodes"}, "paint": paint_rep, "skin": skin})
    if not C.flag(argv, "--no-review"):
        review(mesh, arm, rep, paint_rep, clips, lite=C.flag(argv, "--lite"))
    tex_dir = os.path.join(pack, "textures")
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        "art/enemies/the_bellows/reports/the_bellows_review.png", "art/enemies/the_bellows/reports/the_bellows_ingame.png",
        "art/enemies/the_bellows/reports/the_bellows_clips.png", "art/enemies/the_bellows/reports/the_bellows_34.png",
        "art/enemies/the_bellows/reports/the_bellows_verb.png"],
        "Built from code by tools/blender/gf_assets/enemies/the_bellows.py (dedicated rig GF_Bellows_v1).", tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
