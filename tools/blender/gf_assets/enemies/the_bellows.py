"""The Bellows (the_bellows) - Cinder Wastes mini-boss (the biome's Warlord), FALLEN GODWORKS. Built end to end
from code: model -> hidden-face cull -> hand-painted NPR textures (2048) -> dedicated rig GF_Bellows_v1 ->
clips -> GLB + meta.json -> validation -> review sheets. art/enemies/the_bellows/README.md records the
decisions.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/the_bellows.py -- [--preview] [--size 2048] [--no-review] [--lite]

  --preview   model only: flat zone-colour views + game-size silhouette in art/enemies/the_bellows/work/preview
  --no-review skip the review renders (export + validation only)
  --lite      review only the 3/4 hero shots and the in-game frames (sheets in work/review; for paint passes)
  --clips-only  no paint, no export: the rig, the clips and the floor solve's report (--save keeps work/*.blend)

Content row (content/sheets/enemies.csv): the_bellows, MiniBoss, cinder_wastes, P1, hp 7000, speed 1.8, radius
1.6, scale 1.6 (sim collider radius 2.56 m), mass 12, Boss(script "the_bellows"), colour #B5532A, greybox
Colossus - "A furnace-lung the size of a house. It breathes fire and cinderlings."
Phases (assets/content/bosses.ron): Stoke (100 %: Radial 12, Summon cinderling x6, Strike Ring 2-5.5 at_self),
Blaze (50 %: Radial 18, Summon emberwisp x4, Strike Circle r3 targeted, Strike Ring 2-6.5 at_self).
docs/OPEN_WORLD.md: it is the Cinder Wastes' Warlord POI boss (met in every run, on the way to the gate).

Design (silhouette verb BREATHE):
  * the great bellows of the gods' forge, walked off its hearth when the pantheon fell: a house-sized
    teardrop bellows (5.5 x 9.2 m footprint, 5.23 m tall at rest = 2.38 x the hero) on four cabriole
    bronze legs with lion-paw feet (divine forge furniture come alive), twin forked handles splayed off the
    lid's rear rim (an open V: the first build's ring grip read as a locket from the game camera);
  * the LUNG is the bellows bag: five pleated hide folds between a god-bronze lid and a bottom board. The
    lid is hinged at the front, so every breath lifts the lid and fans the folds open; the folds swell on
    the inhale (bared fold valleys glow dead ember: the furnace inside) and crush flat on the exhale;
  * the nozzle is a bronze bell out of the hinge behind a cracked porcelain WIND-GOD MASK, stern and mythic
    (never a mascot): a carved relief face, one heavy brow shelf, hollow sockets lit cold gold from inside
    (no pupils), a straight nose and a hard mouth slit clenching a curled bronze war-horn whose bell opens
    sideways (no O on the chin), grimed with soot and verdigris, framed all round by swept bronze rays (a
    sun). It breathes fire and coughs up cinderlings through the horn;
  * two chimney vents and a snapped third on the lid glow dead ember to cold gold, each whole stack branded
    with one broken rune; two fire hatches on the lid blow open in phase 2 (Blaze), and the mask's left
    cheek breaks away to show the furnace;
  * Godworks palette: dark god-bronze with verdigris shadows, old-gold trim, porcelain, rust hide (the row
    colour #B5532A as its light plane's hue), cold-gold to dead-ember glows. No player colours, no red-white;
  * ground contact: every clip is re-solved per frame on the floor (plant_clips: IK-planted paws at z = 0,
    the body and the head kept clear) and the build fails if anything goes through it.
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
MASK_SCALE = 1.12                                # the whole face is built in face units and scaled up by this
# the face: a carved shield of porcelain (face units): top / bottom edge, half-width, relief depth
FACE_T, FACE_B, FACE_HW, FACE_D = 1.0, -1.0, 0.84, 0.36
EYES = (0.34, 0.15)                              # socket centre (x of the left one, y)
MOUTH_Y = -0.45                                  # the mouth slit that clenches the horn
# the war-horn clenched in the mouth (face frame, face units): out of the lips, down in front of the chin, then
# curling to the creature's RIGHT (-X) so its bell opens sideways and down. From the front the flare is seen in
# profile (never an O on the chin); from the game camera it breaks the teardrop's symmetry under the face.
# (x, y, z out of the face, tube radius); the bell flares on from the last point along the last segment
HORN_PATH = [(0.0, MOUTH_Y, None, 0.09), (0.0, -0.58, 0.56, 0.08), (-0.05, -0.86, 0.67, 0.074),
             (-0.27, -1.1, 0.65, 0.08), (-0.52, -1.35, 0.66, 0.1)]
HORN_BELL = [(0.1, -0.05), (0.112, 0.06), (0.15, 0.16), (0.22, 0.26), (0.3, 0.34), (0.36, 0.4)]  # (r, along)
# the left-cheek shard that breaks away in Blaze (face units, the creature's left = +X)
SHARD_POLY = [(0.15, -0.06), (0.36, -0.01), (0.56, -0.07), (0.69, -0.28), (0.6, -0.54), (0.38, -0.66),
              (0.24, -0.48), (0.13, -0.28)]

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


def face_hw(y):
    """Half-width of the face at height y (face units): a domed brow, then a jaw that narrows to the chin."""
    if y >= 0.12:
        t = min(1.0, (y - 0.12) / (FACE_T - 0.12))
        return max(0.22, FACE_HW * math.sqrt(max(0.0, 1.0 - t ** 2.4)))
    t = min(1.0, (0.12 - y) / (0.12 - FACE_B))
    return FACE_HW * (1.0 - 0.5 * t ** 1.7)


def _g(x, y, cx, cy, sx, sy):
    return math.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))


def _band(v, a, b, w=0.1):
    def ss(e0, e1, t):
        t = min(1.0, max(0.0, (t - e0) / (e1 - e0)))
        return t * t * (3 - 2 * t)
    return ss(a, a + w, v) * (1.0 - ss(b - w, b, v))


def face_rho(x, y):
    """Normalised distance to the face outline (a superellipse): 0 at the centre, 1 on the edge."""
    sx_ = abs(x) / face_hw(y)
    sy_ = y / FACE_T if y >= 0 else y / FACE_B
    return (sx_ ** 4 + abs(sy_) ** 4) ** 0.25


def face_z(x, y):
    """Height of the carved face out of the face plane (face units): a flat-topped plate dome with deep eye
    sockets, cheekbones over sunken cheeks, a jutting muzzle round the horn, the skull's brow and a chin."""
    rho = face_rho(x, y)
    if rho >= 1.0:
        return 0.0
    base = FACE_D * math.sqrt(1.0 - rho * rho)
    ax = abs(x)
    rel = (-0.15 * _g(ax, y, EYES[0], EYES[1], 0.22, 0.1)
           + 0.055 * math.exp(-((y - (-0.05 - 0.14 * ax)) / 0.07) ** 2) * _band(ax, 0.14, 0.74)
           - 0.06 * _g(ax, y, 0.47, -0.4, 0.17, 0.2)
           + 0.07 * _g(x, y, 0.0, MOUTH_Y, 0.3, 0.2)
           + 0.035 * _g(x, y, 0.0, 0.64, 0.5, 0.25)
           + 0.04 * _g(x, y, 0.0, -0.86, 0.26, 0.14))
    return base + rel * (1.0 - rho ** 8)


def face_outline(n_side=18, scale=1.0):
    """The face edge as a closed CCW polygon [(x, y), ...] (face units)."""
    ys = [FACE_B + (FACE_T - FACE_B) * (1 - math.cos(math.pi * k / (n_side - 1))) / 2 for k in range(n_side)]
    right = [(face_hw(y) * scale, y * scale) for y in ys]
    left = [(-x, y) for x, y in reversed(right)]
    return right + left


def outline_hit(ang_deg, poly=None):
    """Point where a ray from the face centre at `ang_deg` (0 = +X, 90 = up) leaves the face outline."""
    poly = poly or face_outline()
    d = Vector((math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))))
    best = None
    for i in range(len(poly)):
        a, b = Vector(poly[i]), Vector(poly[(i + 1) % len(poly)])
        e = b - a
        den = d.x * (-e.y) - d.y * (-e.x)
        if abs(den) < 1e-9:
            continue
        t = (a.x * (-e.y) - a.y * (-e.x)) / den
        s_ = (d.x * a.y - d.y * a.x) / den
        if t > 0 and -1e-6 <= s_ <= 1 + 1e-6 and (best is None or t < best):
            best = t
    return d * (best or 1.0)


def in_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


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


def fork_handles():
    """The bellows' grips as TWIN FORKED HANDLES off the lid's rear rim (closed-lid coordinates): two long, broad,
    flat bronze paddles splayed 27 deg left and right, each capped with an old-gold grip block. From the game
    camera they fork out of the round end of the board in a V, so the outline never closes into a ring (the
    first build's ring grip read as a locket). Returns [(bm, zone), ...]."""
    out = []
    for sx in (1, -1):
        ang = math.radians(27.0)
        d = Vector((sx * math.sin(ang), math.cos(ang), 0.12)).normalized()
        root = Vector((sx * 0.36, Y1 - 0.4, HINGE.z + 0.2))
        xh = (d.y, -d.x, 0.0)
        bar = M.loft_rect([(0.0, 0.62, 0.22, 0, 0.0), (0.85, 0.5, 0.19, 0, 0.0), (1.45, 0.52, 0.19, 0, 0.0)],
                          bevel=0.045)
        place(bar, root, d, xh)
        out.append((bar, "bronze"))
        grip = M.box((0.66, 0.36, 0.28), bevel=0.06)
        place(grip, root + d * 1.6, d, xh)
        out.append((grip, "trim"))
    return out


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
GEO = {"chimney": {}, "hatch": {}}      # anchors recorded by build_mesh(): chimney base / mouth, hatch hinge, shard,
#                                         the horn (bell centre, axis) and the part ids by name ("pids")
HATCH_C = (0.64, -0.62)          # plan centre (x for the left one) in closed-lid coords
HATCH_SIZE = (0.68, 0.9)


def face_loft(sections, cap=True):
    """Loft closed cross-sections (lists of face-frame points, same count) into a solid placed by the mask
    matrix (the carved parts: brow shelf, nose, mouth slit)."""
    MM = mask_matrix()
    return loft([[MM @ Vector(p) for p in sec] for sec in sections], cap0=cap, cap1=cap)


def build_face(add):
    """A stern mythic wind god in cracked porcelain, never a mascot: a carved shield face (relief, not a dome),
    one heavy continuous brow shelf over HOLLOW almond sockets lit cold gold from the furnace inside (no pupils),
    a straight Greek nose, a hard mouth slit clenching a bronze HORN whose bell hangs down the chin (seen from
    the side by the 55 deg camera, never end-on as an O), the bronze collar and the sun of swept bronze rays.
    The left cheek (SHARD_POLY) is its own plate on bone mask_shard: it breaks away in Blaze."""
    MM = mask_matrix()

    def fp(x, y, dz=0.0):
        return MM @ Vector((x, y, face_z(x, y) + dz))

    # the face plate: a thick patch over the relief; the grid rows follow the outline, so the edge is clean
    nu, nv = 20, 30

    def face_fn(u, v):
        y = FACE_B + (FACE_T - FACE_B) * v
        x = (2 * u - 1) * face_hw(y)
        return MM @ Vector((x, y, face_z(x, y)))

    def cell_xy(i, j):
        y = FACE_B + (FACE_T - FACE_B) * (j + 0.5) / nv
        return (2 * (i + 0.5) / nu - 1) * face_hw(y), y

    shard = {(i, j) for i in range(nu) for j in range(nv) if in_poly(*cell_xy(i, j), SHARD_POLY)}
    main_o, main_i = SH.thick_patch(face_fn, nu, nv, 0.07, keep=lambda i, j: (i, j) not in shard)
    shard_o, shard_i = SH.thick_patch(face_fn, nu, nv, 0.07, keep=lambda i, j: (i, j) in shard)
    add(main_o, "porcelain", "head", "mask", shading="smooth")
    add(main_i, "void", "head", "mask_inner", shading="smooth")
    GEO["shard_c"] = sum((v.co for v in shard_o.verts), Vector()) / max(1, len(shard_o.verts))
    add(shard_o, "porcelain", "mask_shard", "mask_shard", shading="smooth")
    add(shard_i, "void", "mask_shard", "mask_shard_inner", shading="smooth")

    # the brow shelf: ONE carved slab across the face, level with a slight frown down to a furrow at the centre
    # and a sharp undercut into the sockets (a stern god, not a V of cartoon brows)
    secs = []
    for k in range(17):
        t = -1.0 + 2.0 * k / 16
        x = 0.72 * t
        y0 = 0.33 + 0.035 * abs(t) - 0.028 * math.exp(-(t / 0.13) ** 2)
        z0 = face_z(x, y0)
        sc = 1.0 - 0.45 * t * t
        prof = [(0.1, -0.03), (0.07, 0.075), (0.0, 0.125), (-0.055, 0.1), (-0.078, -0.03)]
        secs.append([(x, y0 + dy * (0.75 + 0.25 * sc), z0 + dz * sc) for dy, dz in prof])
    add(face_loft(secs), "porcelain", "head", "brow", shading="auto")

    # the nose: a straight Greek ridge down from the brow's furrow, flaring at the wings
    secs = []
    for y, w, h in ((0.31, 0.06, 0.04), (0.2, 0.065, 0.075), (0.08, 0.075, 0.1), (-0.04, 0.09, 0.13),
                    (-0.14, 0.12, 0.155), (-0.22, 0.15, 0.125), (-0.27, 0.11, 0.05)):
        z0 = face_z(0.0, y)
        prof = [(-w, -0.035), (-0.55 * w, 0.7 * h), (0.0, h), (0.55 * w, 0.7 * h), (w, -0.035), (0.0, -0.06)]
        secs.append([(dx, y, z0 + dz) for dx, dz in prof])
    add(face_loft(secs), "porcelain", "head", "nose", shading="auto")

    # the sockets: hollow almonds sunk in the relief, lit from inside (painted: cold-gold core, dark rim); the
    # inner corners sit a little lower under the brow (stern). A shallow dish facing out of the face.
    for sx in (1, -1):
        ex, ey = sx * EYES[0], EYES[1]
        ca, sa = math.cos(math.radians(sx * 9.0)), math.sin(math.radians(sx * 9.0))
        rings = []
        for scale, dz in ((1.0, 0.012), (0.55, -0.035)):
            ring_ = []
            for k in range(14):
                a_ = 2 * math.pi * k / 14
                px = 0.2 * math.cos(a_)
                py = (0.085 if math.sin(a_) < 0 else 0.058) * math.sin(a_)
                x_, y_ = ex + scale * (px * ca - py * sa), ey + scale * (px * sa + py * ca)
                ring_.append((x_, y_, face_z(x_, y_) + dz))
            rings.append(ring_)
        bm = bmesh.new()
        vo = [bm.verts.new(MM @ Vector(p)) for p in rings[0]]
        vm = [bm.verts.new(MM @ Vector(p)) for p in rings[1]]
        vc = bm.verts.new(MM @ Vector((ex, ey, face_z(ex, ey) - 0.05)))
        for k in range(14):
            j = (k + 1) % 14
            bm.faces.new((vo[k], vo[j], vm[j], vm[k]))
            bm.faces.new((vm[k], vm[j], vc))
        bm.normal_update()
        add(bm, "eyes", "head", "eye_socket", shading="smooth")

    # the mouth: a hard slit, its corners turned down, clenching the horn
    secs = []
    for k in range(9):
        t = -1.0 + 2.0 * k / 8
        x = 0.25 * t
        y0 = MOUTH_Y - 0.06 * abs(t) ** 1.6
        z0 = face_z(x, y0)
        h = 0.028 * (1.0 - 0.4 * t * t)
        secs.append([(x, y0 - h, z0 - 0.035), (x, y0 - h, z0 + 0.022), (x, y0 + h, z0 + 0.022),
                     (x, y0 + h, z0 - 0.035)])
    add(face_loft(secs), "socket", "head", "mouth", shading="flat")

    # the HORN: a curled bronze war-horn clenched in the mouth (the breath and the fire come out of it): a bore
    # tube down in front of the chin that curls to the creature's right, and a bell flaring sideways and down;
    # a glowing throat deep in the bell, an old-gold rim, a ferrule at the lips and a band on the curl
    pts = [Vector((x, y, (face_z(x, y) - 0.06) if z is None else z)) for x, y, z, _r in HORN_PATH]
    path = M.catmull(pts, per_segment=6)
    seg = [0.0]
    for a_, b_ in zip(path[:-1], path[1:]):
        seg.append(seg[-1] + (b_ - a_).length)
    ctrl = [0.0]
    for a_, b_ in zip(pts[:-1], pts[1:]):
        ctrl.append(ctrl[-1] + (b_ - a_).length)

    def radius_at(sv):
        u = sv / seg[-1] * ctrl[-1]
        for k in range(len(ctrl) - 1):
            if u <= ctrl[k + 1] + 1e-9:
                t = (u - ctrl[k]) / max(1e-9, ctrl[k + 1] - ctrl[k])
                return HORN_PATH[k][3] + (HORN_PATH[k + 1][3] - HORN_PATH[k][3]) * t
        return HORN_PATH[-1][3]

    bore = M.tube(path, [radius_at(sv) for sv in seg], sides=12)
    M.xform(bore, matrix=MM)
    add(bore, "bronze", "head", "horn", shading="smooth")

    def along(sv):
        """Point and tangent on the bore at arc length sv (face units)."""
        for k in range(len(seg) - 1):
            if sv <= seg[k + 1]:
                t = (sv - seg[k]) / max(1e-9, seg[k + 1] - seg[k])
                return path[k].lerp(path[k + 1], t), (path[k + 1] - path[k]).normalized()
        return path[-1], (path[-1] - path[-2]).normalized()

    for frac, r0, r1, w in ((0.14, 0.085, 0.13, 0.08), (0.62, 0.07, 0.115, 0.07)):
        c_, t_ = along(frac * seg[-1])
        bnd = M.ring(r0, r1, w, sides=12, bevel=0.012)
        M.xform(bnd, matrix=MM @ M.orient(c_, t_, (1, 0, 0)))
        add(bnd, "trim", "head", "horn_band", shading="flat")
    end, axis = path[-1], (path[-1] - path[-2]).normalized()
    HM = MM @ M.orient(end, axis, (0, 1, 0))
    blen = HORN_BELL[-1][1]
    bell_o = M.lathe(HORN_BELL, sides=16, cap=False)
    M.xform(bell_o, matrix=HM)
    add(bell_o, "bronze", "head", "horn", shading="smooth")
    horn_i = M.lathe([(0.02, 0.03), (0.075, 0.1), (0.13, 0.18), (0.2, 0.27), (0.28, 0.345), (0.33, 0.39)],
                     sides=16, cap=False)
    bmesh.ops.reverse_faces(horn_i, faces=horn_i.faces[:])
    M.xform(horn_i, matrix=HM)
    add(horn_i, "void", "head", "horn_inner", shading="smooth")
    rim = M.ring(0.31, 0.39, 0.06, sides=16, bevel=0.015)
    M.xform(rim, loc=(0, 0, blen))
    M.xform(rim, matrix=HM)
    add(rim, "trim", "head", "horn_rim", shading="flat")
    thr = disc(0.08, 12)
    M.xform(thr, loc=(0, 0, 0.09))
    M.xform(thr, matrix=HM)
    add(thr, "ember", "head", "horn_fire", shading="flat")
    GEO["horn"] = (HM @ Vector((0, 0, blen)), (HM.to_3x3() @ Vector((0, 0, 1))).normalized())

    # a bronze collar round the face's edge (hides the join to the bell)
    col_ = M.tube([Vector((x, y, -0.03)) for x, y in face_outline(18, 1.02)], 0.1, sides=8, closed=True)
    M.xform(col_, matrix=MM)
    add(col_, "trim", "head", "mask_collar", shading="smooth")
    # the mane: swept bronze rays round the upper edge (a sun of wind, blown back)
    poly = face_outline(24, 1.0)
    for ang, L in ((90, 1.05), (62, 0.95), (118, 0.95), (36, 0.85), (144, 0.85), (12, 0.7), (168, 0.7),
                   (-14, 0.55), (194, 0.55)):
        o2 = outline_hit(ang, poly) * 0.98
        rdir = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0))
        o = Vector((o2.x, o2.y, -0.02))
        p1 = o + rdir * (L * 0.45) + Vector((0, 0, -0.25 * L))
        p2 = o + rdir * (L * 0.8) + Vector((0, 0, -0.62 * L)) + Vector((0, 0.1 * L, 0))
        ray = M.horn([o, p1, p2], 0.15, 0.02, sides=6)
        M.xform(ray, matrix=MM)
        add(ray, "trim", "head", "mane_ray", shading="smooth")
    # the beard: shorter rays swept back under the jaw, clear of the horn
    for ang, L in ((218, 0.62), (240, 0.72), (300, 0.72), (322, 0.62)):
        o2 = outline_hit(ang, poly) * 0.97
        rdir = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0))
        o = Vector((o2.x, o2.y, -0.02))
        p1 = o + rdir * (L * 0.5) + Vector((0, 0, -0.22 * L))
        p2 = o + rdir * (L * 0.85) + Vector((0, 0, -0.55 * L)) + Vector((-0.12 * L * rdir.x, 0, 0))
        ray = M.horn([o, p1, p2], 0.13, 0.02, sides=6)
        M.xform(ray, matrix=MM)
        add(ray, "trim", "head", "beard_ray", shading="smooth")


def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_ORDER)
    containers = []

    def add(bm, zone, bone, name, shading="auto", container=False):
        pid = a.add(bm, zone, bone=bone, name=name, shading=shading)
        if container:
            containers.append(pid)
        GEO.setdefault("pids", {}).setdefault(name, []).append(pid)
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
    # the grips: twin forked handles splayed off the rear rim (never a ring in the game-camera outline)
    for part_, zone in fork_handles():
        M.xform(part_, matrix=LM)
        add(part_, zone, "lid", "fork_handle")

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

    # ---------------- the head: the nozzle bell + the porcelain wind-god mask ----------------
    # the nozzle bell: out of the hinge barrel, a narrow neck flaring behind the mask (open at the flare, with a
    # dark inner wall, so the phase-2 hole in the mask looks into a furnace, not through the bronze)
    BF = M.orient(NECK, MASK_N, (1, 0, 0))
    bell_prof = [(0.5, -0.25), (0.46, 0.1), (0.36, 0.45), (0.35, 0.68), (0.46, 0.9), (0.72, 1.12),
                 (0.9, BELL_LEN - 0.02)]
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
    # the furnace core inside the bell (shows through the phase-2 hole)
    core = M.ico(0.5, 2)
    M.xform(core, loc=MASK_C - MASK_N * 0.32)
    add(core, "fire", "head", "furnace_core", shading="smooth")
    build_face(add)

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
    # the face close up: straight on, and from the game camera's side (37 deg above the face normal)
    scene = bpy.context.scene
    game_face = (MASK_N * math.cos(math.radians(37)) + Vector((0, 0.309, 0.951)) * math.sin(math.radians(37)))
    for name, d in (("face", MASK_N), ("face_game", game_face)):
        R.aim(scene, MASK_C + MASK_N * 0.3 + Vector((0, 0, -0.25)), d, 3.6, dist=40.0)
        out[name] = R.render(scene, os.path.join(out_dir, "%s_flat_%s.png" % (KEY, name)), 520)
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
    ("porcelain", "#C7BFAE"), ("porcelain soot", "#2A2521"), ("verdigris streaks", "#44705E"),
    ("verdigris patina", "#3D5E50"), ("dead ember", "#8A3A1E"),
    ("cold gold glow", "#D4B45A"), ("white-gold core", "#FFF4D0"),
]
RUNE = "#C9AA56"
RUNE_GLOW = {"color": "#3A2C10", "core": "#6E5626"}


def core_pos():
    return MASK_C - MASK_N * 0.32


def mouth_pos():
    """Just outside the horn's bell (the fire breath, the lobbed gout, spawned cinderlings and emberwisps)."""
    c, ax = GEO["horn"]
    return c + ax * 0.15


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
        # old porcelain, a step darker than the first build (it read as the brightest, most comic shape on
        # screen): grey-green shadows, carved edges caught in light strokes; paint_extras grimes it (soot in every
        # cavity and round the horn, verdigris tear-streaks from the sockets and the brow, patina at the edge)
        "porcelain": P.zone(base="#C7BFAE", shadow="#646B64", light="#E2DBCB", planes=0.06, parts=0.02, brush=0.03,
                            brush_freq=1.5, edge=0.65, edge_width=0.025, cavity=0.85, cavity_width=0.035, ao=0.6,
                            ao_range=(0.25, 0.65)),
        # the dark inside (mask shell, bell): verdigris-black, dead ember close to the furnace core
        "void": P.zone(base="#10201C", shadow="#07100D", light="#1C302A", planes=0.05, parts=0.0, brush=0.06,
                       brush_freq=1.0, edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#8A3A1E", "hot": "#4A1A0C", "color": "#0C0806", "mode": "radial",
                             "center": tuple(core_pos()), "radius": 1.1, "base_mix": 0.0, "strength": 0.9}),
        # the mouth slit that clenches the horn: near-black, warm
        "socket": P.zone(base="#120C0A", shadow="#060404", light="#241A14", planes=0.04, parts=0.0, brush=0.03,
                         brush_freq=1.0, edge=0.3, edge_width=0.015, cavity=0.0, ao=0.0),
        # the furnace: white-gold at the heart, cold gold, dead ember at the rim
        "fire": P.zone(base="#F0D890", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#FFF4D0", "hot": "#E2CA7C", "color": "#B8702E", "mode": "radial",
                             "center": tuple(core_pos()), "radius": 0.75, "base_mix": 0.15}),
        # vents and grates: painted per part in paint_extras (hot centre, ember rim); this is the flat fallback
        "ember": P.zone(base="#E0A050", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#FFF0C8", "hot": "#D4B45A", "color": "#8A3A1E", "mode": "flat", "base_mix": 0.2}),
        # the hollow sockets: painted per part in paint_extras (cold-gold light deep inside, dark rim); flat fallback
        "eyes": P.zone(base="#3A2A14", edge=0.0, cavity=0.0, ao=0.0,
                       emit={"core": "#F2E4B4", "hot": "#D4B45A", "color": "#3A2410", "mode": "flat", "base_mix": 0.2}),
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
    # (metres in the face plane: x = the creature's left, y = up the face; SHARD_POLY x 1.12)
    for (x, y), ang, L, w, sd in (((0.19, -0.08), 60, 0.45, 0.026, 21), ((-0.34, 0.78), -150, 0.5, 0.022, 22),
                                  ((0.7, -0.36), 120, 0.4, 0.022, 23)):
        lines = M.crack_lines(random.Random(sd), start=(x, y), direction=ang, length=L, step=0.07, jag=0.5,
                              branches=1, branch_len=0.4, depth=1)
        out.append(P.decal_lines(lines, frame_at(MASK_C, mz, my_), w, zones=["porcelain"], color="#2E2824",
                                 rim="#77756C", rim_width=w * 2.2, depth=(-0.8, 1.2), facing=0.2))
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
# the porcelain grime (paint_extras): soot, verdigris, and the verdigris tear-streaks (face units: x, top y,
# half-width, length) that run down from the sockets and the brow's ends - a few broad painted drips, never noise
GRIME = {"soot": "#2A2521", "verdigris": "#44705E", "soot_amount": 0.85, "streak_amount": 0.55, "edge_amount": 0.45,
         "mouth_amount": 0.55}
STREAKS = [(0.44, 0.08, 0.075, 0.66), (-0.46, 0.07, 0.085, 0.74), (0.2, 0.07, 0.05, 0.36), (-0.19, 0.08, 0.05, 0.44),
           (0.7, 0.38, 0.07, 0.52), (-0.68, 0.4, 0.08, 0.62), (0.06, 0.92, 0.05, 0.36)]
# the hollow sockets' light and the horn's throat (cold gold deep inside, dead ember, dark at the rim)
SOCKET_GLOW = {"core": "#F2E4B4", "hot": "#D4B45A", "rim": "#3A2410", "dark": "#120C08"}
HORN_GLOW = {"rim": "#1E0E08", "mid": "#8A3A1E", "deep": "#D4B45A", "dark": "#1A1210"}


def face_coords(p):
    """World (rest) points (N x 3 numpy) -> face-frame coordinates in face units."""
    import numpy as np
    Mi = np.array(mask_matrix().inverted(), dtype=np.float64)
    return p @ Mi[:3, :3].T + Mi[:3, 3]


def face_rho_np(x, y):
    import numpy as np
    t1 = np.clip((y - 0.12) / (FACE_T - 0.12), 0.0, 1.0)
    top = np.maximum(0.22, FACE_HW * np.sqrt(np.maximum(0.0, 1.0 - t1 ** 2.4)))
    t2 = np.clip((0.12 - y) / (0.12 - FACE_B), 0.0, 1.0)
    hw = np.where(y >= 0.12, top, FACE_HW * (1.0 - 0.5 * t2 ** 1.7))
    sy = np.where(y >= 0, y / FACE_T, y / FACE_B)
    return ((np.abs(x) / hw) ** 4 + np.abs(sy) ** 4) ** 0.25


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
    # the porcelain: soot in every cavity and round the horn (the fire breath), dark round the sockets,
    # verdigris at the edge (the bronze collar weeps) and broad tear-streaks down from the sockets and the brow
    if "porcelain" in zones_order:
        m = np.nonzero(Z == zones_order.index("porcelain"))[0]
        p = pos[m]
        fc = face_coords(p.astype(np.float64))
        fx, fy = fc[:, 0], fc[:, 1]
        n1 = P.spread01(P.fbm(p, 2.2, 2, seed=seed + 521))
        occ = 1.0 - maps["ao"][m]
        soot = P.smoothstep(0.16, 0.46, occ + (n1 - 0.5) * 0.2)
        # soot tight on the lips round the horn (a broad patch under the nose read as a moustache)
        g_m = np.exp(-((fx / 0.2) ** 2 + ((fy - MOUTH_Y) / 0.12) ** 2))
        soot = np.maximum(soot, GRIME["mouth_amount"] * P.smoothstep(0.25, 0.8, g_m + (n1 - 0.5) * 0.2))
        g_e = np.exp(-(((np.abs(fx) - EYES[0]) / 0.3) ** 2 + ((fy - EYES[1]) / 0.15) ** 2))
        soot = np.maximum(soot, 0.8 * P.smoothstep(0.3, 0.8, g_e))
        c = P.mix(base[m], P.hex3(GRIME["soot"]), soot * GRIME["soot_amount"])
        vk = P.smoothstep(0.8, 0.97, face_rho_np(fx, fy) + (n1 - 0.5) * 0.14) * GRIME["edge_amount"]
        for x0, y0, w, L in STREAKS:
            along = (y0 - fy) / L
            across = (fx - x0 - 0.02 * np.sin(fy * 13.0 + x0 * 5.0)) / w
            k = np.exp(-across ** 2 * 1.6) * P.smoothstep(0.0, 0.06, along) * (1.0 - P.smoothstep(0.45, 1.0, along))
            vk = np.maximum(vk, k * (0.85 + 0.3 * (n1 - 0.5)) * GRIME["streak_amount"])
        base[m] = P.mix(c, P.hex3(GRIME["verdigris"]), np.clip(vk, 0.0, 1.0))
        C.log("porcelain grime: %.0f%% sooty, %.0f%% verdigris" % (100 * float((soot > 0.4).mean()),
                                                                   100 * float((vk > 0.3).mean())))
    pids = GEO.get("pids", {})
    # the hollow sockets: cold-gold light deep inside, darkening to a black rim (no pupils)
    if "eyes" in zones_order:
        m = np.nonzero(Z == zones_order.index("eyes"))[0]
        parts = maps["part"][m]
        g = SOCKET_GLOW
        for pid in np.unique(parts):
            ii = m[parts == pid]
            pp = pos[ii]
            d = np.linalg.norm(pp - pp.mean(0), axis=1)
            t = np.clip(d / max(1e-3, float(d.max())), 0.0, 1.0)
            e = P.mix(np.repeat(P.hex3(g["core"])[None], len(ii), 0), P.hex3(g["hot"]), P.smoothstep(0.0, 0.42, t))
            e = P.mix(e, P.hex3(g["rim"]), P.smoothstep(0.45, 0.85, t))
            e = e * (1.0 - 0.9 * P.smoothstep(0.8, 1.0, t))[:, None]
            emis[ii] = e
            base[ii] = P.mix(P.mix(e, np.ones(3, dtype=np.float32), 0.15), P.hex3(g["dark"]),
                             P.smoothstep(0.55, 0.95, t))
    # the horn's inside: dark at the bell's rim, dead ember, then cold gold deep in the throat
    horn_ids = pids.get("horn_inner", [])
    if horn_ids and "void" in zones_order:
        m = np.nonzero((Z == zones_order.index("void")) & np.isin(maps["part"], horn_ids))[0]
        if len(m):
            c_, ax = GEO["horn"]
            depth = (np.array(c_)[None] - pos[m]) @ np.array(ax)
            g = HORN_GLOW
            e = P.mix(np.repeat(P.hex3(g["rim"])[None], len(m), 0), P.hex3(g["mid"]), P.smoothstep(0.0, 0.14, depth))
            e = P.mix(e, P.hex3(g["deep"]), P.smoothstep(0.14, 0.3, depth))
            emis[m] = e
            base[m] = P.mix(P.hex3(g["dark"]), e, 0.5)
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


# the walk (lateral sequence LH, LF, RH, RF): half the planted paw's sweep (m), the stance share of the cycle,
# the swing's lift (m), how low the body rides while walking (m) and the cycle length (frames). plant_clips()
# moves each paw on this plan with IK; gait() gives the body's bob, sway and breathing.
WALK = {"move@loop": {"half": 0.55, "S": 0.65, "lift": 0.3, "crouch": 0.12, "frames": 48},
        "move_p2@loop": {"half": 0.6, "S": 0.62, "lift": 0.34, "crouch": 0.15, "frames": 40}}
STANCE_SHIFT = {"front": 0.1, "hind": -0.1}       # the stance is centred this far back (+) of the rest paw spot


def gait(t, S=0.65, crouch=0.12, p2=False):
    """The walk cycle's body for t in [0, 1): it rides `crouch` low with a thud on the four footfalls, sways and
    rolls over the planted paws and breathes twice. The legs here are only a rough FK guess: plant_clips()
    re-solves them with IK on walk_plan()."""
    p = {}
    for (kind, side), ph in GAIT_PHASE.items():
        q = (t + ph) % 1.0
        lift = 0.0 if q < S else math.sin(math.pi * (q - S) / (1 - S))
        p.update(leg(kind, side, -6 * lift, fold_for(crouch) + 30 * lift, 14 * lift))
    w = 2 * math.pi * t
    thud = 0.035 * (0.5 + 0.5 * math.cos(4 * w))            # four footfalls a cycle
    p["root"] = {"loc": (0.08 * math.sin(w), -crouch - thud, 0.0)}
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


def walk_plan(t, half, S):
    """{(kind, side): (dy, lift 0..1)} for t in [0, 1): a planted paw slides from `half` in front of its stance
    centre to `half` behind it (the body walks over it); a swinging paw lifts and comes forward on a cosine."""
    out = {}
    for leg_, ph in GAIT_PHASE.items():
        q = (t + ph) % 1.0
        if q < S:
            out[leg_] = (-half + 2 * half * q / S, 0.0)
        else:
            u = (q - S) / (1 - S)
            out[leg_] = (half * math.cos(math.pi * u), math.sin(math.pi * u))
    return out


def move_cycle_m(clip="move@loop"):
    """Metres the body travels per walk cycle: the planted paw sweeps 2 x half in S of the cycle."""
    w = WALK[clip]
    return round(2 * w["half"] / w["S"], 3)


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
    w1, w2 = WALK["move@loop"], WALK["move_p2@loop"]
    # ---- loops
    loop("idle@loop", 96, lambda t: K(1, breath(t)), 1)
    loop("move@loop", w1["frames"], lambda t: K(1, gait(t, w1["S"], w1["crouch"])), 1, {"move_cycle_m": mc})
    loop("idle_p2@loop", 96, lambda t: K(2, breath(t, 1.35, 2, True)), 2)
    loop("move_p2@loop", w2["frames"], lambda t: K(2, gait(t, w2["S"], w2["crouch"], True)), 2,
         {"move_cycle_m": move_cycle_m("move_p2@loop")})
    b1, b2 = K(1, breath(0.0)), K(2, breath(0.0, 1.35, 2, True))
    for ph, sfx in ((1, ""), (2, "_p2")):
        base = b1 if ph == 1 else b2
        # windup = INHALE (the verb's first half): brace, the lid heaves open, the folds swell; ends loaded
        one("windup" + sfx, [(0, base), (8, K(ph, lung(-2.0, 0.97), body(pitch=1.5, drop=0.1), head(4.0))),
                             (24, K(ph, INHALE)), (30, K(ph, INHALE2))], {"loaded": 1.0}, ph)
        # attack = BREATHE: the lid slams shut, the mask thrusts, fire pours out of the horn (release on frame 4)
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
        # summon: the face bows until the horn's bell is at the ground, three heaves; a coal is born out of the
        # horn on each (cinderlings in Stoke, emberwisps in Blaze). The body tips only a little so the floor solve
        # keeps the bow (the heave's bell touches down, the refill lifts it again)
        bow = pose(lung(5.0, 1.08), body(pitch=3.0, drop=0.12), head(8.0, fwd=0.1),
                   chim((4, 0, 0), (4, 0, 0), (4, 0, 0)))
        heave = pose(lung(-5.0, 0.88), body(pitch=4.5, drop=0.18, fwd=0.12), head(22.0, fwd=0.35),
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
    burst = pose(lung(16.0, 1.26), body(pitch=-6.0, drop=0.06), head(-22.0, 0, -6.0),
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


# ---- ground contact: IK-planted paws, and a body, head and shard that never pass the floor ------------------
# The clips above are keyed pose to pose (gfa_rig.keyed_clip / cycle_clip); their leg angles are only a guess.
# plant_clips() samples every frame of every clip and re-solves it:
#   1. the body: if the board, lid, folds or vents would come within CLEAR_BODY of the floor, the root rises;
#   2. the legs: analytic two-bone IK (thigh -> knee -> ankle, the knee bending in the leg's rest plane carried
#      by the pelvis). A planted paw stays level and sits exactly on the floor (its lowest vertex at z = 0) at
#      its plant spot: the rest spot (+ PLANT_KEYS offsets), or the walk plan in the move loops. Legs in LIFTS
#      keep their keyed pose in the air and blend onto the plant spot as they come down;
#   3. the head: if the mask, the rays or the horn would come within CLEAR_HEAD of the floor, the head pitches
#      up just enough (the face bows TO the floor, never through it);
#   4. the fallen cheek shard (phase2) rests on the floor.
# Then every frame is keyed (linear) under the same clip name. The build fails if a planted paw leaves the floor
# or anything goes below it (ground_check()).

LEGS = [(k, s_) for k in ("front", "hind") for s_ in "LR"]
CLEAR_HEAD = 0.04
CLEAR_BODY = 0.05
CLEAR_LEG = 0.01                  # thighs and shins stay this far off the floor (the body rises)
BODY_BONES = ["pelvis", "lid"] + ["pleat_%d" % i for i in range(1, N_PLEAT + 1)] + [
    "hatch_L", "hatch_R", "chimney_1", "chimney_2", "chimney_3"]
LIFTS = {"strike_ring": ("front",), "strike_ring_p2": ("front",)}   # legs whose keyed pose may leave the floor
# plant-spot offsets (outward, back) keyed on the clip's frames (smoothstep between keys): death splays the paws
# as the body sinks onto its belly
_SPLAY = {"front": (0.4, -0.35), "hind": (0.42, 0.35)}
PLANT_KEYS = {"death": [(0, {}), (18, {}), (34, {"front": (0.12, -0.12), "hind": (0.05, 0.05)}), (58, _SPLAY),
                        (90, _SPLAY)]}


def _ss(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def plant_offset(clip, frame, kind):
    keys = PLANT_KEYS.get(clip)
    if not keys:
        return 0.0, 0.0
    for (f0, a0), (f1, a1) in zip(keys[:-1], keys[1:]):
        if f0 <= frame <= f1:
            t = _ss((frame - f0) / max(1e-6, f1 - f0))
            p0, p1 = a0.get(kind, (0.0, 0.0)), a1.get(kind, (0.0, 0.0))
            return p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
    return keys[-1][1].get(kind, (0.0, 0.0))


def _frame3(v, n):
    a_ = v.normalized()
    c_ = n.normalized()
    return Matrix((a_, c_.cross(a_), c_)).transposed()


class Planter:
    """Rest data of the rig and the skinned mesh (rigid: every vertex on one bone) for the floor solve."""

    def __init__(self, arm, mesh):
        import numpy as np
        self.arm = arm
        me = mesh.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        Mw = np.array(arm.matrix_world.inverted() @ mesh.matrix_world, dtype=np.float64)
        co = co.reshape(-1, 3) @ Mw[:3, :3].T + Mw[:3, 3]
        names = {g.index: g.name for g in mesh.vertex_groups}
        owner = np.array([names[max(v.groups, key=lambda g: g.weight).group] for v in me.vertices])
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        self.verts = {b: co[owner == b] for b in self.rest}
        self.legs = {}
        for kind, side in LEGS:
            th, sh, pw = ("%s_%s_%s" % (kind, part, side) for part in ("thigh", "shin", "paw"))
            H0, K0, A0 = (self.rest[x].translation.copy() for x in (th, sh, pw))
            u0 = (A0 - H0).normalized()
            w0 = (K0 - H0) - u0 * (K0 - H0).dot(u0)
            V = self.verts[pw]
            self.legs[(kind, side)] = {
                "bones": (th, sh, pw), "H0": H0, "K0": K0, "A0": A0, "L1": (K0 - H0).length, "L2": (A0 - K0).length,
                "w0": w0.normalized(), "n0": u0.cross(w0).normalized(),
                "ankle_h": float(A0.z - V[:, 2].min()), "Vrel": V - np.array(A0)}

    def deform(self, bone, pose_m):
        import numpy as np
        D = np.array(pose_m @ self.rest[bone].inverted(), dtype=np.float64)
        return self.verts[bone] @ D[:3, :3].T + D[:3, 3]

    def zmin(self, bones, mats=None):
        pb = self.arm.pose.bones
        z = [float(self.deform(b, (mats or {}).get(b, pb[b].matrix))[:, 2].min()) for b in bones
             if len(self.verts[b])]
        return min(z) if z else 99.0

    def frame_now(self, bone, parent_pose=None):
        b = self.arm.data.bones[bone]
        if b.parent is None:
            return self.rest[bone].copy()
        pp = parent_pose if parent_pose is not None else self.arm.pose.bones[b.parent.name].matrix
        return pp @ (self.rest[b.parent.name].inverted() @ self.rest[bone])

    def paw_low(self, leg_, A, R3):
        """Lowest z of the paw placed with its ankle at A and world rotation R3."""
        import numpy as np
        V = self.legs[leg_]["Vrel"] @ np.array(R3, dtype=np.float64).T
        return float(V[:, 2].min()) + A.z

    def solve_leg(self, leg_, A_t, R3):
        """Two-bone IK: the ankle to A_t (clamped to the reach), the paw at world rotation R3 (identity = level,
        as at rest). Writes the three bones' local transforms. Returns (reach used / max, miss in m)."""
        L = self.legs[leg_]
        th, sh, pw = L["bones"]
        pbs = self.arm.pose.bones
        F_th = self.frame_now(th)
        H = F_th.translation.copy()
        Rp = F_th.to_3x3() @ self.rest[th].to_3x3().inverted()
        hint = Rp @ L["w0"]
        d = A_t - H
        dist = d.length
        L1, L2 = L["L1"], L["L2"]
        reach = min(max(dist, abs(L1 - L2) + 1e-4), (L1 + L2) * 0.999)
        u = d.normalized()
        w = hint - u * hint.dot(u)
        if w.length < 1e-6:
            w = Rp @ Vector((1.0, 0.0, 0.0))
            w = w - u * w.dot(u)
        w.normalize()
        ca = (L1 * L1 + reach * reach - L2 * L2) / (2 * L1 * reach)
        a_ = math.acos(max(-1.0, min(1.0, ca)))
        K_ = H + (u * math.cos(a_) + w * math.sin(a_)) * L1
        A_ = H + u * reach
        n = u.cross(w).normalized()
        R1 = _frame3(K_ - H, n) @ _frame3(L["K0"] - L["H0"], L["n0"]).transposed()
        R2 = _frame3(A_ - K_, n) @ _frame3(L["A0"] - L["K0"], L["n0"]).transposed()
        M_th = Matrix.Translation(H) @ (R1 @ self.rest[th].to_3x3()).to_4x4()
        M_sh = Matrix.Translation(K_) @ (R2 @ self.rest[sh].to_3x3()).to_4x4()
        M_pw = Matrix.Translation(A_) @ (Matrix(R3) @ self.rest[pw].to_3x3()).to_4x4()
        pbs[th].matrix_basis = F_th.inverted() @ M_th
        pbs[sh].matrix_basis = self.frame_now(sh, M_th).inverted() @ M_sh
        pbs[pw].matrix_basis = self.frame_now(pw, M_sh).inverted() @ M_pw
        return reach / (L1 + L2), max(0.0, dist - reach), {th: M_th, sh: M_sh, pw: M_pw}


def _read_pose(arm):
    return {pb.name: (tuple(pb.location), tuple(pb.rotation_euler), tuple(pb.scale)) for pb in arm.pose.bones}


def _write_pose(arm, row):
    for pb in arm.pose.bones:
        loc, rot, sc = row[pb.name]
        pb.location, pb.rotation_euler, pb.scale = loc, rot, sc


def _basis(loc, rot, sc):
    from mathutils import Euler
    return Matrix.Translation(Vector(loc)) @ Euler(rot, "XYZ").to_matrix().to_4x4() @ Matrix.Diagonal((*sc, 1.0))


def solve_legs(pl, clip, f, plan, walk, fk, diag):
    """Step 2 of solve_frame: every leg by two-bone IK onto its plant spot (or its keyed lift). Returns the
    legs' world matrices {bone: matrix}."""
    mats = {}
    for leg_ in LEGS:
        kind, side = leg_
        L = pl.legs[leg_]
        sx = 1.0 if side == "L" else -1.0
        ox, oy = plant_offset(clip, f, kind)
        A = Vector((L["A0"].x + sx * ox, L["A0"].y + oy, L["ankle_h"]))
        R3 = Matrix.Identity(3)
        if plan:
            dy, lift = plan[leg_]
            A.y += STANCE_SHIFT[kind] + dy
            A.z += walk["lift"] * lift
            R3 = Matrix.Rotation(math.radians(28.0 * lift ** 1.5), 3, "X")
        elif kind in LIFTS.get(clip, ()):
            Mfk = fk[leg_]
            z_fk = pl.paw_low(leg_, Mfk.translation, Mfk.to_3x3() @ pl.rest[L["bones"][2]].to_3x3().inverted())
            wgt = _ss((z_fk - 0.02) / 0.23)
            if wgt > 0:
                A = A.lerp(Mfk.translation, wgt)
                q_fk = (Mfk.to_3x3() @ pl.rest[L["bones"][2]].to_3x3().inverted()).to_quaternion()
                R3 = Matrix.Identity(3).to_quaternion().slerp(q_fk, wgt).to_matrix()
        low = pl.paw_low(leg_, A, R3)
        if low < 0.0 or (not plan and kind not in LIFTS.get(clip, ())):
            A.z -= low                      # planted: the lowest paw vertex exactly on the floor
        r, miss, m_ = pl.solve_leg(leg_, A, R3)
        mats.update(m_)
        diag["reach"] = max(diag["reach"], r)
        diag["miss"] = max(diag["miss"], miss)
    return mats


def solve_frame(pl, clip, f, frames):
    """The floor solve of one frame (the keyed FK pose is already on the bones). Returns its diagnostics."""
    arm = pl.arm
    pbs = arm.pose.bones
    upd = bpy.context.view_layer.update
    upd()
    diag = {"lift_body": 0.0, "head_up_deg": 0.0, "reach": 0.0, "miss": 0.0}
    # 1. the body
    zb = pl.zmin(BODY_BONES)
    if zb < CLEAR_BODY:
        loc = list(pbs["root"].location)
        loc[1] += CLEAR_BODY - zb
        pbs["root"].location = loc
        diag["lift_body"] = CLEAR_BODY - zb
        upd()
    # FK paws (legs that may lift keep them)
    fk = {leg_: pbs[pl.legs[leg_]["bones"][2]].matrix.copy() for leg_ in LEGS}
    walk = WALK.get(clip)
    plan = walk_plan(f / frames, walk["half"], walk["S"]) if walk else None
    for _ in range(5):
        mats = solve_legs(pl, clip, f, plan, walk, fk, diag)
        # a thigh or shin on the floor (the belly flop in death): the body rises until the legs clear it
        zl = pl.zmin([b for leg_ in LEGS for b in pl.legs[leg_]["bones"][:2]], mats)
        if zl >= CLEAR_LEG - 1e-4:
            break
        loc = list(pbs["root"].location)
        loc[1] += CLEAR_LEG - zl
        pbs["root"].location = loc
        diag["lift_body"] += CLEAR_LEG - zl
        upd()
    upd()
    # 3. the head: pitch up just enough to clear the floor
    hb = pbs["head"]
    F_h = pl.frame_now("head")
    loc, rot, sc = tuple(hb.location), tuple(hb.rotation_euler), tuple(hb.scale)
    sb = pbs["mask_shard"]
    attached = Vector(sb.location).length < 1e-4 and Vector(sb.rotation_euler).length < 1e-4 and \
        abs(sb.scale[0] - 1.0) < 1e-4

    def head_low(delta):
        Mh = F_h @ _basis(loc, (rot[0] - delta, rot[1], rot[2]), sc)
        z = float(pl.deform("head", Mh)[:, 2].min())
        if attached:
            z = min(z, float(pl.deform("mask_shard", pl.frame_now("mask_shard", Mh))[:, 2].min()))
        return z

    if head_low(0.0) < CLEAR_HEAD:
        lo_, hi_ = 0.0, math.radians(75.0)
        for _ in range(18):
            mid = 0.5 * (lo_ + hi_)
            if head_low(mid) < CLEAR_HEAD:
                lo_ = mid
            else:
                hi_ = mid
        hb.rotation_euler = (rot[0] - hi_, rot[1], rot[2])
        diag["head_up_deg"] = math.degrees(hi_)
    # 4. the fallen cheek shard rests on the floor (also the hidden speck on its way back to the mask)
    if not attached:
        Mh = F_h @ _basis(tuple(hb.location), tuple(hb.rotation_euler), tuple(hb.scale))
        F_s = pl.frame_now("mask_shard", Mh)
        Ms = F_s @ sb.matrix_basis
        zs = float(pl.deform("mask_shard", Ms)[:, 2].min())
        if zs < 0.0:
            sb.matrix_basis = F_s.inverted() @ (Matrix.Translation((0.0, 0.0, -zs)) @ Ms)
    return diag


def ground_check(pl, clip, frames):
    """Evaluate the solved clip (it is the active NLA track): the lowest paw vertex of every planted paw, of every
    paw, of the head, of the shard and of the rest of the body per frame."""
    import gfa_rig as RIG
    rows = []
    leg_bones = [b for leg_ in LEGS for b in pl.legs[leg_]["bones"][:2]]
    for f in range(frames + 1):
        RIG.pose_at(pl.arm, clip_track(clip), f)
        paws = {"%s_%s" % leg_: pl.zmin([pl.legs[leg_]["bones"][2]]) for leg_ in LEGS}
        rows.append({"f": f, "paws": paws, "head": pl.zmin(["head"]), "shard": pl.zmin(["mask_shard"]),
                     "body": pl.zmin(BODY_BONES), "legs": pl.zmin(leg_bones)})
    return rows


def plant_clips(arm, mesh, clips):
    """Re-solve and re-bake every clip on the floor (see above). Returns the ground-contact report."""
    import gfa_rig as RIG
    pl = Planter(arm, mesh)
    ad = arm.animation_data
    saved = [m for m in mesh.modifiers if m.type == "ARMATURE" and m.show_viewport]
    for m in saved:
        m.show_viewport = False
    report = {}
    try:
        for clip in CLIP_ORDER:
            name = clip_track(clip)
            tr = ad.nla_tracks.get(name)
            act = tr.strips[0].action
            f0, f1 = int(act.frame_start), int(act.frame_end)
            rows = []
            for f in range(f0, f1 + 1):
                RIG.pose_at(arm, name, f)
                rows.append(_read_pose(arm))
            RIG.unmute_none(arm)
            ad.nla_tracks.remove(tr)
            bpy.data.actions.remove(act)
            diags, solved, prev = [], [], {}
            for f, row in enumerate(rows):
                _write_pose(arm, row)
                diags.append(solve_frame(pl, clip, f, f1 - f0))
                out = {}
                for pb in arm.pose.bones:
                    e = pb.rotation_euler.copy()
                    if pb.name in prev:
                        e.make_compatible(prev[pb.name])
                    prev[pb.name] = e.copy()
                    out[pb.name] = (tuple(pb.location), tuple(e), tuple(pb.scale))
                solved.append(out)
            _bake(arm, name, solved, clip.endswith("@loop"))
            report[clip] = {"frames": [f0, f1],
                            "max_body_lift_m": round(max(d["lift_body"] for d in diags), 3),
                            "max_head_up_deg": round(max(d["head_up_deg"] for d in diags), 1),
                            "head_clamped_frames": sum(1 for d in diags if d["head_up_deg"] > 0.05),
                            "max_leg_reach": round(max(d["reach"] for d in diags), 3),
                            "max_reach_miss_m": round(max(d["miss"] for d in diags), 3)}
    finally:
        for m in saved:
            m.show_viewport = True
    # verify on the baked clips (evaluated through the NLA, as the exporter samples them)
    for clip in CLIP_ORDER:
        rows = ground_check(pl, clip, report[clip]["frames"][1])
        walk = WALK.get(clip)
        planted = []
        for r in rows:
            for leg_ in LEGS:
                if walk:
                    q = (r["f"] / report[clip]["frames"][1] + GAIT_PHASE[leg_]) % 1.0
                    if q >= walk["S"]:
                        continue
                elif leg_[0] in LIFTS.get(clip, ()):
                    continue
                planted.append(r["paws"]["%s_%s" % leg_])
        low = min(min(r["paws"].values()) for r in rows)
        report[clip].update({
            "planted_paw_z": [round(min(planted), 4), round(max(planted), 4)] if planted else None,
            "paw_min_z": round(low, 4), "head_min_z": round(min(r["head"] for r in rows), 3),
            "shard_min_z": round(min(r["shard"] for r in rows), 3),
            "body_min_z": round(min(r["body"] for r in rows), 3),
            "leg_min_z": round(min(r["legs"] for r in rows), 3)})
        rc = report[clip]
        C.log("ground %-16s planted paws z %s | paws >= %+.3f | head >= %+.3f | shard >= %+.3f | body >= %+.3f | "
              "legs >= %+.3f | head up %4.1f deg (%d f) | reach %.3f" % (
                  clip, rc["planted_paw_z"], low, rc["head_min_z"], rc["shard_min_z"], rc["body_min_z"],
                  rc["leg_min_z"], rc["max_head_up_deg"], rc["head_clamped_frames"], rc["max_leg_reach"]))
    RIG.unmute_none(arm)
    bad = [c for c, r in report.items() if (r["planted_paw_z"] and (r["planted_paw_z"][0] < -0.005 or
                                                                   r["planted_paw_z"][1] > 0.02))
           or r["paw_min_z"] < -0.005 or r["head_min_z"] < 0.0 or r["shard_min_z"] < -0.005 or r["body_min_z"] < 0.0
           or r["leg_min_z"] < 0.0]
    if bad:
        raise RuntimeError("clips through the floor or paws off it: %s" % bad)
    return report


def _bake(arm, name, rows, loop):
    """Key every frame of `rows` ({bone: (loc, euler, scale)}) linearly into a new action stashed as the muted
    NLA track `name` (the gfa_rig / gfa_rig_dedicated clip convention)."""
    import gfa_rig as RIG
    ad = arm.animation_data
    act = bpy.data.actions.new(name)
    ad.action = act
    if hasattr(act, "slots"):
        ad.action_slot = act.slots.new(id_type="OBJECT", name=arm.name)
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, len(rows) - 1
    act.use_fake_user = True
    for f, row in enumerate(rows):
        for pb in arm.pose.bones:
            loc, rot, sc = row[pb.name]
            pb.location, pb.rotation_euler, pb.scale = loc, rot, sc
            pb.keyframe_insert("location", frame=f)
            pb.keyframe_insert("rotation_euler", frame=f)
            pb.keyframe_insert("scale", frame=f)
    for fc in RIG._fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    ad.action = None
    RIG.reset_pose(arm)
    tr = ad.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.name = name
    tr.mute = True
    act["gfa_loop"] = bool(loop)
    return act


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
              ("Stoke attacks: radial (the vents bark), summon (cinderlings out of the horn), strike_ring (rear and slam)",
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
    if C.flag(argv, "--clips-only"):         # iteration: rig + clips + the floor solve and its report only
        arm = B.build_rig(RIG_NAME, rig_table(), col=col, bone_len=0.4)
        B.skin_rigid(mesh, arm)
        sockets(arm)
        plant_clips(arm, mesh, build_clips(arm))
        if C.flag(argv, "--save"):
            C.save_blend(os.path.join(work, KEY + "_clips.blend"))
        return
    paint_rep = paint_bellows(mesh, size, seed=5)
    arm = B.build_rig(RIG_NAME, rig_table(), col=col, bone_len=0.4)
    skin = B.skin_rigid(mesh, arm)
    C.log("skin", skin["per_bone"])
    socks = sockets(arm)
    clips = build_clips(arm)
    ground = plant_clips(arm, mesh, clips)
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
        "move_cycle_m": {"move@loop": move_cycle_m(), "move_p2@loop": move_cycle_m("move_p2@loop")},
        "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage", "paint_scale", "broad_zones")},
        "row": {"hp": 7000, "speed": 1.8, "radius": 1.6, "scale": 1.6, "collider_radius_m": 2.56, "mass": 12,
                "color": "#B5532A", "shape": "Colossus", "open_world": "Cinder Wastes Warlord POI (docs/OPEN_WORLD.md)"},
        "faction": "fallen_godworks",
        "ground_contact": {
            "rule": "floor z = 0: planted paws sit on it (their lowest vertex at 0, IK), nothing else goes below it; "
                    "the head's lowest point stays >= %.2f m, the body's >= %.2f m" % (CLEAR_HEAD, CLEAR_BODY),
            "clips": {c: {k: r[k] for k in ("planted_paw_z", "paw_min_z", "head_min_z", "body_min_z")}
                      for c, r in ground.items()}},
    }
    rep = E.export_asset(KIND, KEY, TIER, arm, source_blend=blend, build_script=__file__, extra=extra)
    C.write_json(os.path.join(pack, "reports", "build_report.json"),
                 {"export": {k: v for k, v in rep.items() if k != "nodes"}, "paint": paint_rep, "skin": skin,
                  "ground": ground})
    if not C.flag(argv, "--no-review"):
        review(mesh, arm, rep, paint_rep, clips, lite=C.flag(argv, "--lite"))
    tex_dir = os.path.join(pack, "textures")
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        "art/enemies/the_bellows/reports/the_bellows_review.png", "art/enemies/the_bellows/reports/the_bellows_ingame.png",
        "art/enemies/the_bellows/reports/the_bellows_clips.png", "art/enemies/the_bellows/reports/the_bellows_34.png",
        "art/enemies/the_bellows/reports/the_bellows_verb.png",
        "art/enemies/the_bellows/reports/the_bellows_review_fix.png"],
        "Built from code by tools/blender/gf_assets/enemies/the_bellows.py (dedicated rig GF_Bellows_v1). Art review "
        "fix (5.5/10): the mask remade as a stern wind god with a curled war-horn, twin forked grips instead of the "
        "ring handle, every clip floor-solved (IK-planted paws at z = 0, nothing below the floor); before / after "
        "in reports/the_bellows_review_fix.png (the_bellows_fix_views.py + the_bellows_fix_sheet.py).", tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
