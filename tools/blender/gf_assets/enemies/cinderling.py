"""Cinderling - the Cinder Wastes swarm blob (The Unmade): "A coal that learned to hate." The most common
Cinder fodder, built, painted, rigged on GF_Swarm_v1, animated, exported and reviewed from code. One base
look and two variant looks, each its own GLB (the clinker's variant rule).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/enemies/cinderling.py -- --variant base|v1|v2 [--size 512] [--no-review] [--preview]

  then (after all three): -P tools/blender/gf_assets/enemies/cinderling_crowd.py   (lineup, 40-copy horde)

Content row (content/sheets/enemies.csv): cinderling, Swarm, P0, hp 30, speed 3.2, radius 0.42, scale 1.0,
contact damage 8, mass 1.0, Chaser, colour #E0662B, shape Blob, packs of 3-6. The Slag King summons it
(assets/content/bosses.ron: Summon(cinderling x6 / x8): "the furnace spits cinderlings").
Collider radius x scale = 0.42 m, so the footprint is ~0.92-1.26 m (docs/art/ENEMIES.md section 2).

Design (docs/art/ENEMIES.md sections 3-5; the user's enemy pack; art/enemies/cinderling/README.md):
  * verb HOP: a lumpy, knapped coal the size of a boulder (0.94-1.0 m wide, 0.64-0.74 m tall = 0.29-0.34 x
    the hero), split across the front by a jagged molten MAW (a face split snapped onto a designed sawtooth).
    The lower half is an underbite jaw with dark obsidian fangs; the upper half is a lid hinged at the back
    (the `head` bone), so the wind-up read is the lid rearing back over a white-hot throat. It moves in
    squash-and-stretch hops. A round lump, so it never reads as the clinker (a long, legged crawler);
  * value plan at 35-45 px: a crown of pale ash on every up-facing facet (the Cinder floor #3A2C24 is dark
    and warm), coal-black flanks framed by the ink and a few anthracite glints, three or four hand-drawn,
    tapered molten seams across the ash, a deep ember-red grin at rest; the only white-hot shape is the
    throat the wind-up reveals (glow 13-18 % of the pixels at rest, 51-54 % loaded);
  * faction: THE UNMADE, the Slag King's brood. Materials from gfa_spec.FACTIONS["unmade"]: slag (the coal,
    its light plane pushed pale into ash), obsidian (fangs, growth), molten (the glow; the hot tone sits by
    the row colour #E0662B) and one fused cluster of obsidian crystals glowing dim teal at the root - the
    anti-life that woke the coal (wrong, asymmetric geometry: a swollen brow on one side, the growth on
    the other, a mouth that sags to one side). No player colours, no #7CFF6B, no red-white.

Rig GF_Swarm_v1 (rigid): body = the jaw half and the throat bowl; head = the lid (+ its fangs); tail = the
obsidian growth (it lags on every hop); legs_a / legs_b stay unweighted (a blob has no legs). The hop is a
body scale squash-and-stretch that keeps the base on the ground (see make_clips).

Toolkit: tools/blender/gf_assets (gfa_model / gfa_paint / gfa_rig / gfa_export / gfa_render / gfa_boss).
Swarm conventions and the review layout follow enemies/clinker.py.
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

CONTENT_KEY = "cinderling"
KEY = CONTENT_KEY                  # the file stem of the look being built (main() sets it per variant)
KIND, TIER = "enemy", "swarm"
FPS = 30
ROW = {"key": "cinderling", "class": "Swarm", "biome": "cinder_wastes", "phase": "P0", "hp": 30, "speed": 3.2,
       "radius": 0.42, "scale": 1.0, "contact_damage": 8, "mass": 1.0, "behavior": "Chaser", "color": "#E0662B",
       "shape": "Blob", "pack": "(3, 6)"}
ZONES = ["crust", "coal", "maw", "fang", "cyst"]

# ---- the looks ------------------------------------------------------------------------------------------------
# One table per look; every look is its own GLB with the identical GF_Swarm_v1, sockets and clip suffixes
# (the clinker's variant rule, art/enemies/clinker/README.md). `mirror` flips a look left-right.
BASE = dict(
    key="cinderling", name="Grinning coal", mirror=False,
    seed=7,
    radii=(0.46, 0.42, 0.37),          # half extents of the lump (x wide, y deep, z tall) before lobes
    lobes=[((-0.55, -0.45, 0.70), 0.15, 0.55),   # the swollen brow over the right side of the mouth
           ((0.70, 0.35, -0.10), 0.10, 0.60),    # a heavy left haunch
           ((-0.30, 0.80, 0.30), 0.06, 0.50),    # the back of the crown
           ((0.10, 0.10, 1.00), 0.05, 0.40)],    # a raised crown
    noise=(0.035, 2.2),                 # low-frequency lumps (amount m, frequency /m)
    # knapped facets (direction, depth below the surface): none crosses the mouth band at the front
    chisel=[((0.25, -0.35, 0.90), 0.050), ((-0.55, 0.10, 0.80), 0.045), ((0.60, 0.30, 0.75), 0.055),
            ((0.05, 0.60, 0.80), 0.040), ((0.90, -0.10, 0.45), 0.045), ((-0.95, 0.30, 0.30), 0.045),
            ((-0.30, -0.70, 0.65), 0.035), ((0.20, -0.75, -0.55), 0.035), ((0.20, 0.95, 0.10), 0.045),
            ((-0.60, 0.70, -0.10), 0.035), ((0.75, 0.60, 0.20), 0.030)],
    ico=4,                              # icosphere level (Blender: 3 = 320 tris, 4 = 1280)
    decimate=0.5,                       # < 1 collapses the icosphere to irregular facets (no geodesic grid)
    sharp=40.0,                         # skin edges sharper than this get painted ridge strokes
    saw=(32.0, 0.050),                  # mouth teeth: period (deg of azimuth) and height (m)
    mouth_skew=-0.03,                   # the mouth sags toward the creature's right (wrong, lopsided)
    base_flat=0.70,                     # the flat underside starts at -base_flat * rz
    mouth_z=0.05,                       # mouth plane height at the lump centre (relative to the centre, m)
    mouth_tilt=13.0,                    # the plane rises toward the back (deg): low at the front, hinge high
    rest_open=5.5,                      # the lid rests open by this much: the smouldering grin
    jut=0.10,                           # the underbite: the jaw's upper front juts forward (m)
    # fangs: (azimuth deg from the front, + = the creature's left, length m, base radius m)
    jaw_fangs=[(-50, 0.150, 0.050), (-17, 0.105, 0.040), (14, 0.115, 0.042), (47, 0.140, 0.048)],
    lid_fangs=[(-34, 0.090, 0.038), (0, 0.080, 0.034), (31, 0.085, 0.036)],
    # the Unmade growth: obsidian crystals erupting from the back-left haunch (tail bone), teal at the root
    growth=dict(dir=(0.70, 0.62, 0.18), shards=[((0.50, 0.50, 0.72), 0.34, 0.070), ((0.90, 0.20, 0.45), 0.21, 0.052),
                                                ((0.15, 0.85, 0.50), 0.17, 0.046)]),
    # molten seams over the ash crown: top-view polylines (x = the creature's left, y = back) and the width at
    # their crest end; drawn by hand (random walks read as letters on a 45 px dome), then wobbled and tapered
    seams=[([(-0.05, 0.10), (-0.09, -0.04), (-0.06, -0.17), (-0.12, -0.29), (-0.10, -0.44)], 0.040),
           ([(-0.05, 0.10), (0.07, 0.15), (0.19, 0.11), (0.31, 0.17), (0.45, 0.13)], 0.036),
           ([(-0.05, 0.10), (-0.17, 0.19), (-0.29, 0.25), (-0.42, 0.20)], 0.034),
           ([(-0.07, -0.13), (0.03, -0.19), (0.09, -0.28)], 0.024)],
    motion=dict(move_frames=12, idle_frames=48, hop=0.17, air=(0.22, 0.86), move_cycle_m=0.9,
                squash_curve=[(0.03, 0.80), (0.12, 0.92), (0.22, 1.15), (0.40, 1.04), (0.54, 0.98), (0.70, 1.05),
                              (0.84, 1.13), (0.93, 0.88)]),
)


def look_from(base, **kw):
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    out.update(kw)
    return out


VARIANTS = {
    "base": BASE,
    # Split-crown: taller and narrower, a keel along the crown split by one long seam front to back, the growth
    # on the other side (mirrored) as two long shards, a lighter, higher hop
    "v1": look_from(
        BASE, key="cinderling_v1", name="Split-crown", mirror=True, seed=19,
        radii=(0.455, 0.42, 0.40),
        lobes=[((0.0, 0.25, 1.0), 0.09, 0.32), ((0.0, -0.35, 0.9), 0.07, 0.32), ((-0.60, -0.40, 0.50), 0.10, 0.50),
               ((0.65, 0.40, -0.10), 0.08, 0.55)],
        chisel=[((0.55, -0.20, 0.80), 0.045), ((-0.55, 0.05, 0.80), 0.050), ((0.50, 0.45, 0.70), 0.045),
                ((-0.40, 0.55, 0.70), 0.040), ((0.90, -0.10, 0.40), 0.045), ((-0.95, 0.25, 0.30), 0.045),
                ((0.30, -0.70, 0.62), 0.035), ((-0.25, -0.75, -0.55), 0.035), ((0.10, 0.95, 0.15), 0.045),
                ((0.60, 0.70, -0.10), 0.035)],
        saw=(28.0, 0.048), mouth_skew=0.025, jut=0.08,
        jaw_fangs=[(-44, 0.130, 0.046), (-12, 0.095, 0.038), (20, 0.120, 0.044), (50, 0.110, 0.042)],
        lid_fangs=[(-28, 0.085, 0.036), (5, 0.075, 0.032), (36, 0.080, 0.034)],
        growth=dict(dir=(0.70, 0.62, 0.22), shards=[((0.45, 0.45, 0.78), 0.40, 0.068), ((0.85, 0.35, 0.40), 0.20, 0.050)]),
        seams=[([(0.00, 0.42), (0.03, 0.24), (-0.02, 0.08), (0.03, -0.08), (-0.01, -0.25), (0.03, -0.43)], 0.042),
               ([(-0.02, 0.08), (-0.14, -0.02), (-0.26, -0.14), (-0.36, -0.28)], 0.030),
               ([(0.03, 0.24), (0.14, 0.32), (0.27, 0.36)], 0.026)],
        motion=dict(move_frames=11, idle_frames=44, hop=0.20, air=(0.20, 0.86), move_cycle_m=0.95,
                    squash_curve=[(0.03, 0.82), (0.12, 0.94), (0.20, 1.18), (0.40, 1.05), (0.54, 0.98), (0.70, 1.06),
                                  (0.84, 1.15), (0.93, 0.88)]),
    ),
    # Heavy-brow: squat and wide, a massive brow over a bigger underbite with tusks, a star of short seams, a
    # cluster of small crystals; a low, heavy hop
    "v2": look_from(
        BASE, key="cinderling_v2", name="Heavy-brow", mirror=False, seed=31,
        radii=(0.48, 0.43, 0.33),
        lobes=[((0.0, -0.60, 0.65), 0.17, 0.55), ((-0.50, -0.30, 0.70), 0.08, 0.45), ((0.70, 0.30, -0.10), 0.09, 0.60),
               ((-0.20, 0.80, 0.30), 0.06, 0.50)],
        chisel=[((0.30, -0.30, 0.90), 0.050), ((-0.50, 0.15, 0.80), 0.050), ((0.60, 0.35, 0.72), 0.050),
                ((0.00, 0.65, 0.75), 0.045), ((0.92, -0.05, 0.40), 0.045), ((-0.95, 0.30, 0.25), 0.050),
                ((-0.35, -0.70, 0.62), 0.040), ((0.20, -0.75, -0.55), 0.035), ((0.25, 0.95, 0.05), 0.045),
                ((-0.60, 0.70, -0.10), 0.035), ((0.75, 0.60, 0.20), 0.030)],
        saw=(36.0, 0.055), mouth_skew=-0.02, jut=0.13, mouth_z=0.04,
        jaw_fangs=[(-56, 0.175, 0.058), (-20, 0.100, 0.040), (18, 0.105, 0.040), (54, 0.170, 0.056)],
        lid_fangs=[(-36, 0.080, 0.036), (0, 0.075, 0.034), (34, 0.080, 0.036)],
        growth=dict(dir=(0.72, 0.58, 0.20), shards=[((0.50, 0.40, 0.75), 0.24, 0.056), ((0.80, 0.10, 0.55), 0.17, 0.046),
                                                    ((0.25, 0.80, 0.55), 0.16, 0.044), ((0.85, 0.55, 0.35), 0.12, 0.040)]),
        # the brow is cracked right across (an arc over the front of the crown), one seam curls back from it
        seams=[([(0.44, -0.02), (0.30, -0.14), (0.12, -0.21), (-0.07, -0.19), (-0.25, -0.13), (-0.43, -0.03)], 0.038),
               ([(-0.10, -0.18), (-0.08, -0.02), (-0.16, 0.14), (-0.12, 0.30), (-0.20, 0.42)], 0.034),
               ([(0.22, -0.17), (0.28, -0.30), (0.24, -0.42)], 0.024)],
        motion=dict(move_frames=13, idle_frames=52, hop=0.13, air=(0.24, 0.84), move_cycle_m=0.85,
                    squash_curve=[(0.03, 0.78), (0.12, 0.90), (0.24, 1.12), (0.40, 1.03), (0.54, 0.98), (0.70, 1.04),
                                  (0.82, 1.10), (0.92, 0.86)]),
    ),
}


def mirrored_look(look):
    """The same look flipped left-right (the growth, the brow, the skew and the seams change sides)."""
    out = look_from(look)
    fx = lambda v: (-v[0],) + tuple(v[1:])  # noqa: E731
    out["lobes"] = [(fx(c), a, w) for c, a, w in look["lobes"]]
    out["chisel"] = [(fx(n), d) for n, d in look["chisel"]]
    out["jaw_fangs"] = [(-az, ln, r) for az, ln, r in look["jaw_fangs"]]
    out["lid_fangs"] = [(-az, ln, r) for az, ln, r in look["lid_fangs"]]
    out["mouth_skew"] = -look["mouth_skew"]
    g = look["growth"]
    out["growth"] = dict(dir=fx(g["dir"]), shards=[(fx(d), ln, r) for d, ln, r in g["shards"]])
    out["seams"] = [([(-x, y) for x, y in pts], w) for pts, w in look["seams"]]
    return out


# palette (sRGB). Coal = the faction slag, ash = the slag light pushed pale and cool (burnt-out skin on the
# up-facing facets), glints = the obsidian light; molten = gfa_spec molten, hot tone warmed to the row colour.
COAL_DEEP = "#0F0B0C"
COAL = "#231A1B"
COAL_MID = "#3A2F31"
ASH_DARK = "#574D4A"
ASH = "#7B7068"
ASH_LIGHT = "#B0A396"
GLINT = "#6F6878"
MOLTEN_RIM = "#C8400C"
THROAT = "#6A1E06"                 # the throat's outer ring (behind the teeth): a deep smoulder, not a flare
MOLTEN_HOT = "#FF6B1A"
MOLTEN_CORE = "#FFCE9E"            # pale peach (hue 29 deg): never the player gold #FFC940 (hue 43 deg)
SEAM_CORE = "#FF8A3A"              # the seams' core: hot orange, a step below the maw's white-hot centre
BURNT = "#120A08"
TEAL = "#2FBFA8"
PALETTE = [("coal", COAL), ("coal mid", COAL_MID), ("ash", ASH), ("ash light", ASH_LIGHT), ("glint", GLINT),
           ("molten rim", MOLTEN_RIM), ("molten hot", MOLTEN_HOT), ("molten core", MOLTEN_CORE),
           ("row colour", ROW["color"]), ("cyst", "#20262C"), ("ichor", TEAL)]
UV_SCALE = {"maw": 0.55, "fang": 0.8, "cyst": 0.9}   # gfa_paint.unwrap zone_scale: the crown gets the pixels


def mix_hex(a, b, t):
    ca, cb = C.hex_rgb(a), C.hex_rgb(b)
    return "#%02X%02X%02X" % tuple(int(round((x * (1 - t) + y * t) * 255)) for x, y in zip(ca, cb))


# ---- geometry helpers ---------------------------------------------------------------------------------------

def chisel_plane(bm, n, co):
    """One knapped facet: slice away everything beyond the plane (co, n) and fill the cut flat."""
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6, plane_co=co,
                                 plane_no=n, clear_outer=True)
    cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    if cut:
        try:
            bmesh.ops.edgeloop_fill(bm, edges=cut)
        except Exception:  # noqa: BLE001
            bmesh.ops.holes_fill(bm, edges=bm.edges[:], sides=0)
    return M.recalc(bm)


def decimate(bm, ratio):
    """Collapse-decimate a bmesh (irregular triangles: coal facets instead of a geodesic grid). bm is freed."""
    me = bpy.data.meshes.new("gfa_tmp_dec")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("gfa_tmp_dec", me)
    bpy.context.scene.collection.objects.link(ob)
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    out = bmesh.new()
    out.from_mesh(ev.to_mesh())
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    bpy.context.view_layer.update()
    return M.recalc(out)


def maw_fill(bm, cut_edges, normal, push, inset=0.6, flatten=0.85):
    """Close the open mouth loop with a throat: a steep pleated band (the gums behind the teeth) down to an
    inset ring pulled flat onto the mouth plane, then a smooth shallow dome / bowl to the centre. A plain fan
    from a sawtooth rim folds into pleats all the way in, which reads as a folded orange plate.
    Returns the new faces."""
    loop = [e for e in cut_edges if e.is_valid and len(e.link_faces) == 1]
    verts = list({v for e in loop for v in e.verts})
    if not verts:
        return []
    n = Vector(normal).normalized()
    c0 = sum((v.co for v in verts), Vector()) / len(verts)
    inner = {}
    for v in verts:
        q = c0 + (v.co - c0) * inset
        q = q - n * ((q - c0).dot(n) * flatten) + Vector(push) * 0.6
        inner[v] = bm.verts.new(q)
    c = bm.verts.new(c0 + Vector(push))
    faces = []
    for e in loop:
        f0 = e.link_faces[0]
        v0, v1 = e.verts
        order = None
        for lp in f0.loops:
            if lp.vert is v0 and lp.link_loop_next.vert is v1:
                order = (v1, v0)
                break
            if lp.vert is v1 and lp.link_loop_next.vert is v0:
                order = (v0, v1)
                break
        if order is None:
            continue
        a_, b_ = order
        try:
            faces.append(bm.faces.new((a_, b_, inner[b_], inner[a_])))
            faces.append(bm.faces.new((inner[a_], inner[b_], c)))
        except ValueError:
            pass
    return faces


def split_faces(bm, key_fn):
    """{key: bmesh copy keeping only the faces with key_fn(face) == key}. bm is freed."""
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    keys = [key_fn(f) for f in bm.faces]
    out = {}
    for k in sorted(set(keys)):
        c = bm.copy()
        c.faces.ensure_lookup_table()
        dele = [c.faces[i] for i, kk in enumerate(keys) if kk != k]
        bmesh.ops.delete(c, geom=dele, context="FACES")
        out[k] = c
    bm.free()
    return out


def rot_about_x(bm_or_pts, deg, pivot):
    R_ = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(deg), 4, "X") @ Matrix.Translation(-Vector(pivot))
    if isinstance(bm_or_pts, bmesh.types.BMesh):
        bmesh.ops.transform(bm_or_pts, matrix=R_, verts=bm_or_pts.verts[:])
        return R_
    return [R_ @ Vector(p) for p in bm_or_pts]


def wobble_line(pts, rng, amount, step=0.03):
    """Resample a 2D polyline every `step` m and push each inner point sideways by up to `amount` (a brush line)."""
    out = [pts[0]]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(1, n + 1):
            t = i / n
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if not (i == n and (x1, y1) == pts[-1]):
                x += rng.uniform(-amount, amount)
                y += rng.uniform(-amount, amount)
            out.append((x, y))
    return out


def taper(pts, w0, w_end, pieces=3):
    """Split a polyline into `pieces` overlapping runs with widths falling from w0 to w0 * w_end (a tapered
    brush line built from constant-width decals)."""
    n = len(pts)
    out = []
    for i in range(pieces):
        a = int(round(i * (n - 1) / pieces))
        b = min(n, int(round((i + 1) * (n - 1) / pieces)) + 2)
        w = w0 * (1.0 - (1.0 - w_end) * i / max(1, pieces - 1))
        if b - a >= 2:
            out.append((pts[a:b], w))
    return out


def fang(base, direction, length, r, rng, sides=4):
    b = M.spike(r, length, sides=sides, base_scale=(1.0, 0.72), rot_offset=rng.uniform(0, 90),
                tip=(rng.uniform(-0.2, 0.2) * r, rng.uniform(-0.2, 0.2) * r))
    M.xform(b, matrix=M.orient(base, direction, (direction[1], -direction[0], 0.0) if abs(direction[2]) < 0.9 else (1, 0, 0)))
    return b


# ---- the model ------------------------------------------------------------------------------------------------

class Build:
    def __init__(self, look=BASE):
        self.V = mirrored_look(look) if look.get("mirror") else look
        self.rng = random.Random(look["seed"])
        self.info = {}

    def lump(self):
        """The whole coal, centred on the origin: a dense icosphere pushed out by a few big lobes and
        low-frequency lumps, a flat underside, then decimated to irregular facets (no geodesic pattern)."""
        V = self.V
        rx, ry, rz = V["radii"]
        bm = M.ico(1.0, V["ico"])
        for v in bm.verts:
            d = v.co.normalized()
            r = 1.0
            for c, amp, w in V["lobes"]:
                r += amp * math.exp(-(d.angle(Vector(c).normalized()) / w) ** 2)
            v.co = d * r
            v.co = Vector((v.co.x * rx, v.co.y * ry, v.co.z * rz))
        M.noise_displace(bm, V["noise"][0], freq=V["noise"][1], seed=V["seed"])
        zb = -V["base_flat"] * rz
        for v in bm.verts:
            if v.co.z < zb:
                v.co.z = zb + (v.co.z - zb) * 0.12
        if V["decimate"] < 1.0:
            bm = decimate(bm, V["decimate"])
        self.base_z = -min(v.co.z for v in bm.verts)       # lift so the underside rests on z = 0
        return bm

    def build(self, col):
        V, rng = self.V, self.rng
        a = M.Assembly(KEY + "_mesh", ZONES, bones=RIG.BONE_NAMES)
        bm = self.lump()
        bmesh.ops.translate(bm, vec=Vector((0.0, 0.0, self.base_z)), verts=bm.verts[:])
        ry = V["radii"][1]
        th = math.radians(V["mouth_tilt"])
        n_m = Vector((0.0, -math.sin(th), math.cos(th)))           # mouth plane normal (up, leaning forward)
        p_m = Vector((0.0, 0.0, self.base_z + V["mouth_z"]))
        # knapped facets: the cut planes come from the WHOLE lump, so both halves share every facet plane
        planes = []
        for n, depth in V["chisel"]:
            n = Vector(n).normalized()
            planes.append((n, n * (max(v.co.dot(n) for v in bm.verts) - depth)))
        # --- the jagged split: a face belongs to the lid when it lies above the mouth plane plus a sawtooth
        # (teeth about 0.2 m apart across the front), so the gap zig-zags like a crack, not a lid seam ---
        per, amp = V["saw"]

        def offset(c):
            az = math.degrees(math.atan2(c.x, -c.y))
            if abs(az) > 100:
                return 0.0
            ph = ((az + per * 0.25) / per) % 1.0
            tri = 4 * abs(ph - 0.5) - 1                            # -1 .. 1 triangle wave
            fade = min(1.0, (100 - abs(az)) / 30.0)
            return amp * tri * fade + V["mouth_skew"] * (az / 90.0)
        bm.faces.ensure_lookup_table()
        is_lid = {f.index: (f.calc_center_median() - p_m).dot(n_m) > offset(f.calc_center_median()) for f in bm.faces}
        for _ in range(3):                                         # no islands: a face surrounded by the other half flips
            for f in bm.faces:
                nb = [is_lid[g.index] for e in f.edges for g in e.link_faces if g is not f]
                if nb and all(x != is_lid[f.index] for x in nb):
                    is_lid[f.index] = not is_lid[f.index]
        # snap the boundary vertices (vertically) onto the designed sawtooth surface: the split follows big
        # clean teeth instead of every small triangle
        rim_v = set()
        for e in bm.edges:
            lf = e.link_faces
            if len(lf) == 2 and is_lid[lf[0].index] != is_lid[lf[1].index]:
                rim_v.update(e.verts)
        for v in rim_v:
            v.co.z += (offset(v.co) - (v.co - p_m).dot(n_m)) / n_m.z
        bm.normal_update()
        cut_pts = [v.co.copy() for v in rim_v]
        halves = split_faces(bm, lambda f: "lid" if is_lid[f.index] else "jaw")
        lid, jaw = halves["lid"], halves["jaw"]
        for b, push in ((lid, n_m * 0.10), (jaw, -n_m * 0.08)):
            for f in maw_fill(b, b.edges[:], n_m, push):
                f.material_index = 1
            M.recalc(b)
            for n, co in planes:
                chisel_plane(b, n, co)
        front = [p for p in cut_pts if p.y < -0.2 and abs(p.x) < 0.15]
        zf = min(p.z for p in front) if front else p_m.z

        def jut(p):
            w_front = max(0.0, min(1.0, (-p.y - 0.05) / (ry * 0.8)))
            w_up = max(0.0, min(1.0, (p.z - 0.04) / max(0.05, zf - 0.04))) ** 1.4
            return Vector((p.x * (1 + 0.06 * w_front * w_up), p.y - V["jut"] * w_front * w_up, p.z))
        for v in jaw.verts:
            v.co = jut(v.co)
        jaw_rim = [jut(p) for p in cut_pts]
        # the hinge: where the split leaves the back of the lump
        back = sorted(cut_pts, key=lambda p: -p.y)[:6]
        self.hinge = Vector((0.0, back[0].y - 0.06, sum(p.z for p in back) / len(back)))
        rot_about_x(lid, -V["rest_open"], self.hinge)
        # surface samples of the jaw (skin faces only) for placing the growth
        self._jaw_pts = [v.co.copy() for f in jaw.faces if f.material_index != 1 for v in f.verts]
        # zones: the cut faces glow (maw); the skin is crust (lid) or coal (jaw)
        pieces = {"lid": (lid, "head", "crust"), "jaw": (jaw, "body", "coal")}
        for tag, (b, bone, skin) in pieces.items():
            parts = split_faces(b, lambda f: "maw" if f.material_index == 1 else skin)
            for z, piece in parts.items():
                for f in piece.faces:
                    f.material_index = 0
                a.add(piece, z, bone=bone, name="%s_%s" % (tag, z), shading="smooth" if z == "maw" else "auto",
                      sharp_angle=V["sharp"])
        # --- fangs: dark obsidian teeth on both rims, interlocking across the glowing gap ---
        rim_front = [p for p in jaw_rim if p.y < -0.05]
        self.mouth_pt = Vector((0.0, min(p.y for p in jaw_rim) + 0.14, zf + 0.04))
        # the white-hot core sits deep in the throat: hidden under the lid at rest, blazing when it opens
        self.maw_core = Vector((0.0, min(p.y for p in jaw_rim) + 0.40, zf - 0.02))

        def rim_at(pts, az, sign):
            near = [p for p in pts if abs(math.degrees(math.atan2(p.x, -p.y)) - az) < 7.0]
            if not near:
                return min(pts, key=lambda p: abs(math.degrees(math.atan2(p.x, -p.y)) - az))
            return max(near, key=lambda p: sign * p.z)
        for az, ln, r in V["jaw_fangs"]:
            p = rim_at(rim_front, az, 1)
            out = Vector((p.x, p.y, 0.0)).normalized()
            d = (Vector((0, 0, 1)) * 0.85 + out * 0.35 + Vector((0, 0.1, 0))).normalized()
            a.add(fang(p - out * 0.012 - d * 0.01, d, ln, r, rng), "fang", bone="body", name="fang_jaw", shading="flat")
        # the lid's rim is the un-jutted cut line, turned open with the lid
        lid_rim = [q for q in rot_about_x(cut_pts, -V["rest_open"], self.hinge) if q.y < -0.05]
        for az, ln, r in V["lid_fangs"]:
            p = rim_at(lid_rim, az, -1)
            out = Vector((p.x, p.y, 0.0)).normalized()
            d = (Vector((0, 0, -1)) * 0.9 + out * 0.2).normalized()
            a.add(fang(p - out * 0.02 - d * 0.008, d, ln, r, rng), "fang", bone="head", name="fang_lid", shading="flat")
        # --- the growth: obsidian crystals fused into the back-left haunch (tail: they lag on every hop) ---
        g = V["growth"]
        d0 = Vector(g["dir"]).normalized()
        centre = Vector((0, 0, self.base_z))
        surf = max(self._jaw_pts, key=lambda q: (q - centre).normalized().dot(d0))
        self.growth_root = surf.copy()
        grng = random.Random(V["seed"] + 5)
        self.growth_top = 0.0
        for dirv, ln, r in g["shards"]:
            d = Vector(dirv).normalized()
            a.add(fang(surf - d * 0.05 + Vector((grng.uniform(-0.02, 0.02), grng.uniform(-0.02, 0.02), 0)), d, ln, r,
                       grng, sides=5), "cyst", bone="tail", name="growth_shard", shading="flat")
            self.growth_top = max(self.growth_top, (surf + d * ln).z)
        tris = a.tris()
        obj = a.to_object(col)
        self.parts = a.parts
        self.tris = tris
        self.top = max(self.growth_top, max(v.co.z for v in obj.data.vertices))
        self.front_y = min(v.co.y for v in obj.data.vertices)
        self.zf = zf
        C.log("%s mesh: %d tris, %d parts" % (KEY, tris, len(a.parts)))
        return obj

    # -- rig anchors --
    def body_z(self):
        return self.base_z * 0.95

    def pivots(self):
        bz = self.body_z()
        return {"root": (0.0, 0.0, 0.0), "body": (0.0, 0.0, bz), "head": tuple(self.hinge),
                "legs_a": (0.0, 0.0, bz), "legs_b": (0.0, 0.0, bz), "tail": tuple(self.growth_root)}

    def sockets(self):
        bz = self.body_z()
        return [("body", "hit_center", (0.0, 0.0, bz + 0.02)),
                ("body", "fx_core", tuple(self.maw_core)),
                ("body", "fx_mouth", (0.0, self.front_y + 0.03, self.zf + 0.03)),
                ("body", "head_top", (0.0, 0.0, self.top + 0.15))]

    # -- paint --
    def recipes(self):
        warm = {"center": tuple(self.mouth_pt), "range": (0.34, 0.12), "color": "#6B2A12", "amount": 0.55}
        crust_facets = {"dir": (0, 0, 1), "soft": 0.08,
                        "stops": [(-1.0, COAL_DEEP), (0.05, COAL), (0.34, COAL_MID), (0.54, ASH_DARK), (0.74, ASH)]}
        coal_facets = {"dir": (0, 0, 1), "soft": 0.05,
                       "stops": [(-1.0, COAL_DEEP), (-0.2, COAL), (0.35, COAL_MID), (0.62, ASH_DARK)]}
        maw = {"color": THROAT, "hot": MOLTEN_HOT, "core": MOLTEN_CORE, "mode": "radial",
               "center": tuple(self.maw_core), "radius": 0.28, "base_mix": 0.05}
        return {
            # the lid: pale ash on every up-facing facet, coal on the flanks, bright broken strokes on the
            # knapped ridges (the value frame against the floor), warm bounce light around the maw
            "crust": P.zone(base=ASH, shadow=COAL_DEEP, light=ASH_LIGHT, facets=crust_facets, planes=0.07, parts=0.03,
                            brush=0.06, brush_freq=4.0, edge=0.95, edge_width=0.010, edge_breakup=0.38, cavity=0.85,
                            cavity_width=0.008, ao=0.6, gradient=warm),
            # the jaw: coal, darker, anthracite glints on the ridges
            "coal": P.zone(base=COAL, shadow=COAL_DEEP, light=GLINT, facets=coal_facets, planes=0.08, parts=0.03,
                           brush=0.06, brush_freq=4.0, edge=0.95, edge_width=0.010, edge_breakup=0.34, cavity=0.8,
                           cavity_width=0.008, ao=0.65, gradient=warm),
            "maw": P.faction_zone("unmade", "molten", glow=True, emit=maw, brush=0.08, brush_freq=9.0),
            # obsidian fangs: dark teeth silhouetted against the glow, glassy edges
            "fang": P.faction_zone("unmade", "obsidian", light="#8A8298", planes=0.2, parts=0.08, edge=1.0,
                                   edge_width=0.008, edge_breakup=0.2, cavity=0.6, ao=0.3),
            # the Unmade growth: black glass with a wet sheen, glowing teal where it bursts out of the coal
            # (the one teal accent: bold, at the root, never speckle)
            "cyst": P.zone(base="#1A1720", shadow="#07060A", light="#7FA7A0", planes=0.18, parts=0.08, edge=1.0,
                           edge_width=0.009, edge_breakup=0.25, cavity=0.7, ao=0.4,
                           emit={"color": "#155F55", "hot": "#1F8F7E", "core": TEAL, "mode": "radial",
                                 "center": tuple(self.growth_root), "radius": 0.2, "fade": (0.55, 0.22),
                                 "base_mix": 0.1, "strength": 0.85}),
        }

    def _molten_lines(self, lines, frame, width, zones, depth, facing=0.25, halo=0.05):
        """A molten fissure: a dim ember spill in the coal, then the crack - a burnt lip around a hot line
        with a pale core."""
        return [P.decal_lines(lines, frame, 0.001, zones=zones, color=None, rim="#4A1A0C", rim_width=halo,
                              emit={"color": "#2A0C04", "core": "#2A0C04"}, depth=depth, facing=facing - 0.35),
                P.decal_lines(lines, frame, width, zones=zones, color=MOLTEN_HOT, rim=BURNT, rim_width=width * 2.3,
                              emit={"color": MOLTEN_RIM, "core": SEAM_CORE}, depth=depth, facing=facing)]

    def decals(self):
        """Few, bold fissures (a crack web turns to speckle at 35 px): three molten cracks over the ash crown
        from the crest down toward the maw and the flanks, one weeping down each side of the jaw, and the
        teal Unmade seam where the obsidian growth has burst out of the coal."""
        V = self.V
        rng = random.Random(V["seed"] + 100)
        out = []
        top = Matrix.Identity(4)
        # the seams split the ash crust from one crest point (the look's `seams`). Each tapers like a brush
        # stroke: widest where the crust split first, thin at the ends
        for ln, w0 in V["seams"]:
            for seg, w in taper(wobble_line(ln, rng, 0.012), w0, 0.45):
                out += self._molten_lines([seg], top, w, ["crust"], (0.28, 1.2), facing=-0.25, halo=w * 1.7)
        # side cracks on the jaw, projected sideways (right flank forward, left flank back)
        for sx, u0 in ((-1, -0.10), (1, 0.10)):
            xa = Vector((0, sx, 0))
            ya = Vector((0, 0, 1))
            za = xa.cross(ya)
            fr = Matrix(((xa.x, ya.x, za.x, sx * 0.05), (xa.y, ya.y, za.y, 0.0), (xa.z, ya.z, za.z, 0.0), (0, 0, 0, 1)))
            c = M.crack_lines(rng, start=(u0 * sx, self.zf - 0.02), direction=-95 + rng.uniform(-15, 15), length=0.17,
                              step=0.025, jag=0.4, branches=1, depth=1)
            out += self._molten_lines(c, fr, 0.026, ["coal"], (0.0, 0.6), facing=0.25, halo=0.045)
        # the Unmade seam: teal cracks spreading out of the growth's root into the coal
        g = self.growth_root
        d0 = (g - Vector((0, 0, self.base_z))).normalized()
        fr = C.frame_from_axes(g - d0 * 0.3, Vector((0, 0, 1)) - d0 * d0.z, d0)
        fr = Matrix(fr)
        tl = [wobble_line([(0.0, 0.0), (-0.06, -0.05), (-0.13, -0.07)], rng, 0.008)]
        out.append(P.decal_lines(tl, fr, 0.001, zones=["coal", "crust"], color=None, rim="#123C38", rim_width=0.04,
                                 emit={"color": "#0B2F2B", "core": "#0B2F2B"}, depth=(0.15, 0.6), facing=-0.2))
        out.append(P.decal_lines(tl, fr, 0.028, zones=["coal", "crust"], color=TEAL, rim="#07060A", rim_width=0.06,
                                 emit={"color": "#1F8F7E", "core": TEAL}, depth=(0.15, 0.6), facing=0.1))
        return out


# ---- clips ------------------------------------------------------------------------------------------------------

def periodic(points, t):
    """Catmull-Rom through [(t, value), ...] over one period [0, 1) (the first point repeats at t + 1)."""
    pts = sorted(points)
    n = len(pts)
    t = t % 1.0
    ext = [(pts[-1][0] - 1.0, pts[-1][1])] + pts + [(pts[0][0] + 1.0, pts[0][1]), (pts[1][0] + 1.0, pts[1][1])]
    for i in range(1, n + 1):
        t0, t1 = ext[i][0], ext[i + 1][0]
        if t0 <= t <= t1:
            u = (t - t0) / (t1 - t0)
            p0, p1, p2, p3 = ext[i - 1][1], ext[i][1], ext[i + 1][1], ext[i + 2][1]
            return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)
    return pts[0][1]


def make_clips(arm, bz, motion):
    """The six required clips plus `spawn` (the Slag King's furnace spits it out). The whole lump squashes
    and stretches on the `body` bone with the base kept on the ground (scale about the body pivot, then a
    matching drop); the lid (head) gnashes; the growth (tail) lags."""
    sin, tau = math.sin, 2 * math.pi
    mo = motion

    def body(k=1.0, pitch=0.0, yaw=0.0, roll=0.0, uni=1.0, lift=0.0):
        # k = vertical stretch (volume kept: the width goes 1/sqrt(k)); uni = uniform scale (swell / crumble)
        sx = uni / math.sqrt(k)
        sy = uni * k
        return {"scale": (sx, sy, sx), "loc": (0.0, -(1.0 - sy) * bz + lift, 0.0), "rot": (pitch, yaw, roll)}

    def lid(open_deg=0.0, yaw=0.0, loc=None, scale=None):
        tr = {"rot": (-open_deg, yaw, 0.0)}
        if loc:
            tr["loc"] = loc
        if scale is not None:
            tr["scale"] = scale
        return tr

    H = mo["hop"]
    air0, air1 = mo["air"]
    K = mo["squash_curve"]
    PITCH = [(0.0, -3.0), (0.22, 5.0), (0.54, 9.0), (0.84, 3.0), (0.93, -5.0)]
    LID = [(0.0, -1.5), (0.22, 3.0), (0.50, 12.0), (0.78, 5.0), (0.86, 0.0), (0.93, -2.0)]
    TAIL = [(0.0, 7.0), (0.22, -12.0), (0.50, 0.0), (0.84, 7.0), (0.93, 13.0)]

    def move(t):
        h = H * sin(math.pi * (t - air0) / (air1 - air0)) if air0 <= t <= air1 else 0.0
        return {"root": {"loc": (0.0, h, 0.0)},
                "body": body(periodic(K, t), pitch=periodic(PITCH, t), roll=2.5 * sin(tau * t + 0.7)),
                "head": lid(periodic(LID, t)),
                "tail": {"rot": (periodic(TAIL, t), 0.0, 6.0 * sin(tau * t + 1.9))}}

    def idle(t):
        w = tau * t
        grind = math.exp(-((((t - 0.58 + 0.5) % 1.0) - 0.5) / 0.035) ** 2)
        return {"body": body(1.0 + 0.035 * sin(w), pitch=1.5 * sin(w + 0.4), roll=1.0 * sin(w + 2.0)),
                "head": lid(1.0 + 4.0 * (0.5 + 0.5 * sin(w - 0.7)) + 5 * grind, yaw=4.0 * grind * sin(t * 90)),
                "tail": {"rot": (3.0 * sin(w + 1.2), 0.0, 3.0 * sin(w + 0.3))}}

    rest = {}
    dip = {"body": body(0.9, pitch=4.0), "head": lid(-1.0)}
    loaded = {"root": {"loc": (0.0, 0.0, -0.04)}, "body": body(0.76, pitch=-14.0), "head": lid(40.0),
              "tail": {"rot": (15.0, 0.0, 0.0)}}
    loaded2 = {"root": {"loc": (0.0, 0.0, -0.05)}, "body": body(0.74, pitch=-16.0, yaw=2.0), "head": lid(46.0, yaw=-3.0),
               "tail": {"rot": (17.0, 0.0, 3.0)}}
    launch = {"root": {"loc": (0.0, 0.16, 0.30)}, "body": body(1.22, pitch=12.0), "head": lid(34.0),
              "tail": {"rot": (-16.0, 0.0, 0.0)}}
    chomp = {"root": {"loc": (0.0, 0.12, 0.40)}, "body": body(1.10, pitch=18.0), "head": lid(-4.0),
             "tail": {"rot": (-6.0, 0.0, 0.0)}}
    land = {"root": {"loc": (0.0, 0.0, 0.36)}, "body": body(0.80, pitch=6.0), "head": lid(9.0),
            "tail": {"rot": (14.0, 0.0, -4.0)}}
    gnash = {"root": {"loc": (0.0, 0.0, 0.30)}, "body": body(0.92, pitch=3.0), "head": lid(-3.0, yaw=4.0),
             "tail": {"rot": (6.0, 0.0, 3.0)}}
    flinch = {"root": {"loc": (0.0, 0.02, -0.06)}, "body": body(0.84, pitch=-12.0, roll=8.0), "head": lid(18.0, yaw=6.0),
              "tail": {"rot": (-10.0, 0.0, 10.0)}}
    settle = {"body": body(1.04, pitch=4.0, roll=-3.0), "head": lid(2.0), "tail": {"rot": (6.0, 0.0, -4.0)}}
    swell = {"body": body(1.0, pitch=-6.0, uni=1.12), "head": lid(14.0), "tail": {"rot": (-8.0, 0.0, 6.0)}}
    crack = {"body": body(0.9, pitch=-3.0, uni=1.05), "head": lid(62.0, loc=(0.0, 0.12, -0.06)),
             "tail": {"loc": (0.06, 0.05, -0.05), "rot": (-30.0, 0.0, 40.0)}}
    fall = {"body": body(0.72, pitch=4.0, roll=6.0), "head": lid(112.0, loc=(0.02, -0.06, -0.26), scale=0.92),
            "tail": {"loc": (0.18, -0.12, -0.08), "rot": (-80.0, 30.0, 90.0), "scale": 0.9}}
    crumble = {"root": {"loc": (0.0, -0.03, 0.0)}, "body": body(0.7, pitch=4.0, roll=6.0, uni=0.55),
               "head": lid(118.0, loc=(0.02, -0.12, -0.3), scale=0.5), "tail": {"loc": (0.2, -0.16, -0.1),
                                                                                 "rot": (-90.0, 30.0, 95.0), "scale": 0.4}}
    gone = {"root": {"loc": (0.0, -0.05, 0.0)}, "body": body(0.7, uni=0.02), "head": lid(118.0, scale=0.05),
            "tail": {"scale": 0.05}}
    curled = {"body": body(1.0, pitch=-20.0, uni=0.3), "head": lid(-2.0), "tail": {"rot": (20.0, 0.0, 0.0)}}
    pop = {"root": {"loc": (0.0, 0.10, 0.0)}, "body": body(1.18, pitch=6.0, uni=1.06), "head": lid(20.0),
           "tail": {"rot": (-14.0, 0.0, 0.0)}}
    thud = {"body": body(0.8, pitch=-4.0), "head": lid(4.0), "tail": {"rot": (12.0, 0.0, 0.0)}}
    RIG.cycle_clip(arm, KEY, "idle@loop", mo["idle_frames"], idle)
    RIG.cycle_clip(arm, KEY, "move@loop", mo["move_frames"], move)
    RIG.keyed_clip(arm, KEY, "windup", [(0, rest), (4, dip), (10, loaded), (15, loaded2)])
    RIG.keyed_clip(arm, KEY, "attack", [(0, loaded2), (3, launch), (5, chomp), (8, land), (10, gnash), (15, rest)])
    RIG.keyed_clip(arm, KEY, "hit", [(0, rest), (2, flinch), (5, settle), (9, rest)])
    RIG.keyed_clip(arm, KEY, "death", [(0, rest), (3, swell), (6, crack), (12, fall), (18, crumble), (26, gone), (27, gone)])
    RIG.keyed_clip(arm, KEY, "spawn", [(0, curled), (5, pop), (9, thud), (12, settle), (15, rest)])
    return [RIG.clip_name(KEY, c) for c in SPEC.ENEMY_CLIPS_REQUIRED + ("spawn",)]


def key_frames(mo):
    mf, idf = mo["move_frames"], mo["idle_frames"]
    return {"idle@loop": [0, int(idf * 0.3), int(idf * 0.55), int(idf * 0.8)],
            "move@loop": [0, round(mf * 0.25), round(mf * 0.5), round(mf * 0.75)], "windup": [0, 4, 10, 15],
            "attack": [0, 3, 5, 8, 15], "hit": [0, 2, 5, 9], "death": [0, 3, 6, 12, 18, 26], "spawn": [0, 5, 9, 15]}


# ---- review --------------------------------------------------------------------------------------------------------

def ink_hull_without_maw(orig):
    """Wrap gfa_render.add_ink_hull (installed by main() for the review only; the shared module is untouched):
    the preview's inverted-hull ink pokes through the concave throat as dark spokes, where the engine's N.V ink
    edge (toon.wesl) draws nothing. Drop the hull faces of the glowing maw."""
    def add_ink_hull(obj, thickness):
        hull = orig(obj, thickness)
        zones = str(obj.get("gfa_zones", "")).split(",")
        me = hull.data
        if "maw" in zones and "gfa_zone" in me.attributes:
            zi = zones.index("maw")
            bm = bmesh.new()
            bm.from_mesh(me)
            layer = bm.faces.layers.int.get("gfa_zone")
            dele = [f for f in bm.faces if f[layer] == zi]
            bmesh.ops.delete(bm, geom=dele, context="FACES")
            bm.to_mesh(me)
            bm.free()
        return hull
    return add_ink_hull


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
    """Side view (orthographic, from the creature's left) beside the 2.2 m hero mannequin, with the hero's
    waist line (1.1 m, the swarm ceiling) and the cinderling's own top."""
    scene = bpy.context.scene
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (0.0, 1.15, 0.0)
    bpy.context.view_layer.update()
    bars = [guide_bar("GUIDE_waist", (0.9, -0.8, 1.1), (0.9, 1.7, 1.1), 0.012, "#D9CFA6"),
            guide_bar("GUIDE_top", (0.9, -0.8, height), (0.9, 0.6, height), 0.008, MOLTEN_CORE),
            guide_bar("GUIDE_ground", (0.9, -0.8, 0.0), (0.9, 1.7, 0.0), 0.01, "#6B5A50")]
    R.setup_cycles(scene, 12)
    with R.toon_preview([mesh, man], ink=0.008, flat={man.name: R.MANNEQUIN}):
        R.aim(scene, (0.0, 0.45, 1.12), (1.0, 0.0, 0.0), 2.55)
        p = R.render(scene, os.path.join(work, "%s_size_side.png" % KEY), 420, 420)
    C.remove_objects([man] + bars)
    return p


def clip_strips(arm, mesh, work, mo):
    scene = bpy.context.scene
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    pts = R._points([mesh])
    d = R.CREATURE_VIEWS["34_front"]
    c, w, h = R.frame(pts, d)
    ext = max(w, h) * 1.75
    c = c + Vector((0.0, 0.0, 0.1))
    R.setup_cycles(scene, 10)
    out = []
    with R.toon_preview([mesh], ink=0.005):
        for clip, frames in key_frames(mo).items():
            track = RIG.clip_name(KEY, clip)
            for f in frames:
                RIG.pose_at(arm, track, f)
                R.aim(scene, c, d, ext)
                p = os.path.join(work, "%s_clip_%s_f%02d.png" % (KEY, clip.replace("@", "_"), f))
                out.append((clip, f, R.render(scene, p, 200)))
    RIG.unmute_none(arm)
    scene.frame_set(0)
    return out


def ingame_poses(arm, mesh, work, mo, view_height=SPEC.GAME_VIEW_HEIGHTS[0]):
    """Key poses through the game camera at true 1080p pixel size (no mannequin, 72 px crops)."""
    out = []
    mf = mo["move_frames"]
    poses = [("rest", None, 0), ("hop (push-off)", "move@loop", round(mf * 0.25)), ("hop (apex)", "move@loop", round(mf * 0.5)),
             ("wind-up (loaded)", "windup", 15), ("attack (chomp)", "attack", 5), ("hit", "hit", 2), ("death", "death", 6)]
    for label, clip, f in poses:
        if clip:
            RIG.pose_at(arm, RIG.clip_name(KEY, clip), f)
        else:
            RIG.unmute_none(arm)
        bpy.context.view_layer.update()
        stem = "%s_pose_%s" % (KEY, label.replace(" ", "_").replace("(", "").replace(")", "").replace("-", ""))
        r = R.ingame([mesh], work, stem, px=72, view_height=view_height, target=(0.0, -0.05, 0.35), silhouette_too=False,
                     ink=0.012)
        out.append((label, r["color"]))
    RIG.unmute_none(arm)
    bpy.context.scene.frame_set(0)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    return out


def review(b, arm, mesh, rep, reports, work, tex, notes):
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    out = {}
    turn = R.turnaround([mesh], work, KEY, R.CREATURE_VIEWS, size=400)
    height = rep.get("height_m") or 0.7
    size_p = size_compare(mesh, work, height)
    mo = b.V["motion"]
    strips = clip_strips(arm, mesh, work, mo)
    ing = []
    for label, yaw in (("facing the camera", -30.0), ("hopping away", 150.0)):
        arm.rotation_euler = (0.0, 0.0, math.radians(yaw))
        man = R.mannequin(aim_dir=(0.6, -0.8, 0.0))
        man.location = (-1.05, 0.35, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([mesh], work, "%s_%s" % (KEY, "face" if yaw < 0 else "away"), px=120,
                     view_height=SPEC.GAME_VIEW_HEIGHTS[0], mannequin_obj=man)
        C.remove_objects([man])
        ing.append((label, r))
    arm.rotation_euler = (0.0, 0.0, math.radians(-30.0))
    poses = ingame_poses(arm, mesh, work, mo)
    arm.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        C.remove_objects([fl])
    th = R._thumbs(tex, work)
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    layout = {
        "title": "Cinderling - %s  (%s.glb)" % (b.V["name"], KEY),
        "subtitle": "\"A coal that learned to hate.\" | The Unmade (the Slag King's brood) | Swarm, Cinder Wastes | "
                    "verb HOP | GF_Swarm_v1 | Chaser, packs of 3-6%s" % (" | mirrored" if b.V["mirror"] else ""),
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
            {"label": "Clip key frames (3/4 front): idle@loop, move@loop (hop), windup, attack, hit, death, spawn", "height": 150,
             "images": [{"path": p, "label": "%s f%d" % (cl, f)} for cl, f, p in strips]},
            {"label": "Textures (base colour, emissive)", "height": 220, "images": [{"path": p, "label": lb} for p, lb in th]},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": list(notes),
    }
    out["sheet"] = R.contact_sheet(layout, os.path.join(reports, "%s_review.png" % KEY), work)
    out.update({"turn": turn, "size": size_p, "ingame": ing, "poses": poses})
    return out


# ---- fast shape previews (Workbench, flat zone colours) ---------------------------------------------------------

PREVIEW_COLORS = {"crust": ASH, "coal": COAL_MID, "maw": MOLTEN_HOT, "fang": "#15121A",
                  "cyst": "#20262C"}


def preview(mesh, work):
    import gfa_boss as BOSS
    views = {"front": (0.0, -1.0, 0.12), "34_front": (0.7, -0.7, 0.3), "side": (1.0, 0.0, 0.1),
             "back": (0.0, 1.0, 0.12), "top": (0.0, -0.0001, 1.0), "game": (0.0, -math.cos(math.radians(55)),
                                                                           math.sin(math.radians(55)))}
    out = BOSS.flat_views([mesh], work, KEY, PREVIEW_COLORS, views, size=360)
    # the game camera at TRUE pixel size (49 px/m), shown later at 3x nearest
    scene = bpy.context.scene
    ppm = SPEC.SCREEN_H / SPEC.GAME_VIEW_HEIGHTS[0]
    d = Vector(views["game"]).normalized()
    R.aim(scene, (0, 0, 0.3), d, 80 / ppm, dist=40)
    scene.display.shading.background_color = C.hex_linear(R.FLOOR)[:3]
    out["game_1x"] = R.render(scene, os.path.join(work, "%s_flat_game1x.png" % KEY), 80)
    return out


# ---- main ----------------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 512, int)
    vk = C.opt(argv, "--variant", "base")
    global KEY
    KEY = VARIANTS[vk]["key"]
    C.reset_scene(fps=FPS)
    col = C.get_collection(KEY)
    b = Build(VARIANTS[vk])
    mesh = b.build(col)
    pack = C.pack_dir(KIND, CONTENT_KEY)
    work = C.ensure_dir(os.path.join(pack, "work", KEY))
    if C.flag(argv, "--preview"):
        out = preview(mesh, work)
        lo, hi = C.world_bounds([mesh])
        C.log("bounds", tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi), "tris", b.tris)
        C.log("preview", out)
        return
    tex_dir = os.path.join(pack, "textures")
    reports = C.ensure_dir(os.path.join(pack, "reports"))
    paint_rep = P.paint_asset(mesh, KEY, b.recipes(), tex_dir, size=size, decals=b.decals(), ao_distance=0.05,
                              ao_samples=16, edge_min_angle=24.0, margin_px=3, uv_angle=66.0, seed=b.V["seed"],
                              uv_zone_scale=UV_SCALE)
    arm = RIG.build_swarm_rig(b.pivots(), col=col)
    probs = RIG.validate_rig(arm)
    if probs:
        raise RuntimeError(probs)
    skin = RIG.skin_rigid(mesh, arm)
    for bone, name, p in b.sockets():
        RIG.add_socket(arm, bone, name, p)
    MOTION = b.V["motion"]
    clips = make_clips(arm, b.body_z(), MOTION)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    extra = {
        "content_key": CONTENT_KEY,
        "variant": vk, "variant_name": b.V["name"], "variant_set": [VARIANTS[k]["key"] for k in ("base", "v1", "v2")],
        "variant_rule": "one file per look; identical GF_Swarm_v1, sockets and clip suffixes; clips are named "
                        "{file_stem}_{clip}. Pick one of variant_set per spawn (cinderling.glb alone is complete).",
        "mirrored": bool(b.V["mirror"]),
        "faction": "unmade",
        "verb": "HOP",
        "move_cycle_m": MOTION["move_cycle_m"],
        "move_note": "one hop per move@loop cycle: play it at speed / move_cycle_m cycles per second (row speed 3.2 m/s "
                     "-> about %.1f hops/s). The hop is in place; root only lifts (%.2f m apex)." % (
                         ROW["speed"] / MOTION["move_cycle_m"], MOTION["hop"]),
        "clip_notes": {
            "windup": "squash low, rear back, the lid (head) opens over the white-hot maw; ends on the loaded pose",
            "attack": "a pounce-chomp: leaps ~0.4 m forward in place-relative root motion, the lid snaps shut at "
                      "frame 5 (the contact hit), lands and returns to rest",
            "death": "swells, the lid bursts off and falls behind, the growth breaks away, the coal slumps and crumbles "
                     "to ash (scale 0.02, held); burst / ember VFX at fx_core are the engine's",
            "spawn": "extra clip for Summon (the Slag King's furnace): pops from a curled ember to full size",
        },
        "rig_note": "GF_Swarm_v1: body = jaw half + maw bowl (squash/stretch by scale, base kept on the ground); "
                    "head = the lid hinged at the back (rotate -X opens the mouth); tail = the obsidian growth; "
                    "legs_a / legs_b unweighted (a blob has no legs)",
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
        R.add_ink_hull = ink_hull_without_maw(R.add_ink_hull)
        tex = [os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")]
        notes = [
            "%s tris (swarm budget 600-1500) | textures %s | %.2f m tall (%.2f x hero), %.2f x %.2f m footprint (collider "
            "radius 0.42 m) | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["height_m"], rep["height_m"] / 2.2,
                rep["bounds"]["max"][0] - rep["bounds"]["min"][0], rep["bounds"]["max"][2] - rep["bounds"]["min"][2],
                ", ".join(sorted(rep["sockets"]))),
            "Clips: %s" % ", ".join(c["name"].replace(KEY + "_", "") + " %.2fs" % c["seconds"] for c in RIG.clips_report(arm)),
            "Lid = the head bone, hinged at the back (-X opens the maw). move_cycle_m %.2f (one hop). Status: %s." % (
                MOTION["move_cycle_m"], SPEC.STATUS_AI_FINAL),
        ]
        review(b, arm, mesh, rep, reports, work, tex, notes)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
