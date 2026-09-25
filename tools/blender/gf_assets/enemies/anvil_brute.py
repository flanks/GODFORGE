"""Anvil Brute (content key `anvil_brute`): the Cinder Wastes plated Elite Brute, built end to end from code -
model, hand-painted NPR textures, dedicated rig, clips, GLB export, validation, review sheets.

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 ^
      -P tools/blender/gf_assets/enemies/anvil_brute.py -- [--preview] [--look] [--poses] [--no-review] [--size 1024]

  --preview   geometry only: flat zone colours, turnaround + the game camera at 1x (seconds, no bakes, no export);
              [--state intact|cracked|stripped|both|all] shows one plate state (all: the three)
  --look      geometry + the final paint (textures into work/look/, not the pack): the three plate states in the
              3/4 view, the 55 deg view and the game camera at true pixel size (no rig, no export); [--close]
              adds close-ups of the plates
  --poses     geometry + rig + clips, key-frame renders in flat colours (no bakes, no export);
              [--game] through the game camera, [--clip <name>], [--size px]
  (default)   the full build: paint, rig, clips, save .blend, export + validate, review sheets, status.json

Content row (content/sheets/enemies.csv): Elite, Cinder Wastes, P0, hp 520, speed 2.4, radius 0.9, contact 18,
mass 4.0, plating (resist {Kinetic: 0.5}, plate_hp 260), Charger(range 9.0, windup 0.9, speed 13.0, duration
0.55, cooldown 3.5, damage 34.0, width 1.4), colour #7A7F8C, greybox Brute, scale 1.3 - "Plated in anvil-iron.
Kinetic rounds glance off until the plates crack."

Design (docs/art/ENEMIES.md sections 3, 4, 6; art/enemies/anvil_brute/README.md):
  * faction THE UNMADE (the Slag King's court): a hunched knuckle-walking hulk of faceted obsidian and dark
    fused flesh that has hammered the forge-gods' anvil-iron onto itself as armour; teal ichor seeps where the
    iron is fused in. 2.81 m to the horn tip (1.28 x the 2.2 m hero), a 2.55 x 1.75 m footprint;
  * THE ONE GIMMICK - anvil-iron plates, the only light metal on a black body. A whole ANVIL is fused across
    the shoulders like a yoke, long axis across the body, so the game camera sees the anvil icon in profile
    (a bull-swept horn jutting out past the left shoulder, the polished face, the square heel over the right
    shoulder, the pinched waist sunk into the hump in a glowing ichor weld); two stepped iron domes on the right
    shoulder, an iron visor with one teal eye slit under a V of brow, and iron cuffs on both forearms. Every plate exists twice in the mesh: INTACT (one solid piece, bone plate_<p>) and CRACKED (the
    same plate cut by jagged gaps into 2-3 fragments whose crack walls glow teal, bones plate_<p>_crk_<n>
    under plate_<p>_crk). The engine switches them by joint scale after the animation system (README:
    "Plate states"), and the plates_break clip blows the cracked fragments off;
  * verb: the OVERHEAD SLAM that launches the charge - windup rears up with both fists clasped overhead (3.8 m),
    attack hammers them into the ground and bulls forward, charge@loop is the head-down gallop;
  * palette (Unmade, gfa_spec.FACTIONS): obsidian #1A1720 with violet-grey top planes, dark plum flesh, anvil
    iron from the row colour #7A7F8C with a polished face, toxic teal #2FBFA8 glow (mint #B8FFE8 cores only);
    no player colours, no red-white (the engine draws the charge telegraph).

Rig GF_AnvilBrute_v1: GF_Hero_v1 core names + the plate joints; rigid skinning. Clips: idle@loop, move@loop
(knuckle walk), windup (overhead slam wind-up), attack (slam + launch), charge@loop, hit, death, plates_break.

Adapted from gf_assets enemies/forge_warden.py (the worked elite: landmark rig table, Solver, Keys + bake_clip,
review sheets) and enemies/slag_king.py (a top-plane lift so a dark body separates from the Cinder floor) -
adapted here, never modified there. The cracked plates are cut with an EXACT boolean (crack_solid).
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_rig_dedicated as RD  # noqa: E402
import gfa_shell as S  # noqa: E402

KEY, KIND, TIER = "anvil_brute", "enemy", "elite"
RIG_NAME = "GF_AnvilBrute_v1"

ZONES = ["obsidian", "flesh", "iron", "iron_crk", "crack", "ichor"]
PREVIEW = {"obsidian": "#2A2632", "flesh": "#24222A", "iron": "#8A909C", "iron_crk": "#7C8290", "crack": "#2FBFA8",
           "ichor": "#3FE0C4"}

# ---- landmarks (rest pose = the idle stance: hunched, knuckles planted; metres, faces -Y, +X = its LEFT) -------
LM = {
    "root": (0.0, 0.0, 0.0), "root_tip": (0.0, 0.0, 0.25),
    "pelvis": (0.0, 0.16, 0.93), "spine_01": (0.0, 0.1, 1.15), "spine_02": (0.0, -0.02, 1.39),
    "spine_03": (0.0, -0.18, 1.63), "neck": (0.0, -0.46, 1.74), "head": (0.0, -0.62, 1.7), "head_tip": (0.0, -0.9, 1.72),
    "clavicle_L": (0.14, -0.18, 1.87), "shoulder_L": (0.72, -0.2, 1.87),
    "elbow_L": (1.03, -0.38, 1.28), "wrist_L": (0.97, -0.66, 0.68), "hand_L_tip": (0.97, -0.8, 0.26),
    "clavicle_R": (-0.14, -0.18, 1.85), "shoulder_R": (-0.69, -0.18, 1.85),
    "elbow_R": (-0.97, -0.36, 1.29), "wrist_R": (-0.9, -0.62, 0.7), "hand_R_tip": (-0.9, -0.74, 0.3),
    "hip_L": (0.28, 0.16, 0.88), "knee_L": (0.44, -0.1, 0.52), "ankle_L": (0.47, 0.1, 0.15),
    "ball_L": (0.49, -0.15, 0.06), "toe_L_tip": (0.5, -0.33, 0.05),
}
for _k in ("hip", "knee", "ankle", "ball", "toe"):
    _n = _k + "_L" if _k != "toe" else "toe_L_tip"
    _p = LM[_n]
    LM[_n.replace("_L", "_R")] = (-_p[0], _p[1], _p[2])

# the anvil fused across the shoulders: local X = the long axis (horn at +X, the brute's left), Y = across the face,
# Z = up out of the face. Yawed so the horn swings forward, rolled so the horn end rides higher, pitched so the
# polished face tilts toward the game camera.
ANVIL_C = Vector((0.03, 0.12, 2.4))
ANVIL_M = (Matrix.Translation(ANVIL_C) @ Matrix.Rotation(math.radians(-13), 4, "Z")
           @ Matrix.Rotation(math.radians(-7), 4, "Y") @ Matrix.Rotation(math.radians(13), 4, "X"))
CORE_POS = Vector((0.0, 0.0, 1.72))          # the ichor heart inside the hump (fx_core: glow, death burst)


def P_(k):
    return Vector(LM[k]) if isinstance(k, str) else Vector(k)


def frame_z(origin, z_dir, x_hint=(1, 0, 0)):
    """4x4 with local +Z along z_dir and +X as close to x_hint as possible."""
    return M.orient(tuple(origin), tuple(z_dir), tuple(x_hint))


def blob(center, radii, rot=(0, 0, 0), sub=2, noise=0.0, freq=2.5, seed=0, jit=0.0, taper=0.0):
    """Faceted obsidian mass: an icosphere scaled to radii, lumped by coherent noise. taper widens the top (+)
    and narrows the bottom along local X (a V-shaped torso)."""
    b = M.ico(1.0, sub, scale=radii)
    if taper:
        for v in b.verts:
            v.co.x *= 1.0 + taper * v.co.z / radii[2]
    if noise:
        M.noise_displace(b, noise, freq=freq, seed=seed)
    if jit:
        M.jitter(b, random.Random(seed), jit)
    M.xform(b, loc=center, rot=rot)
    return b


def muscle(p0, p1, prof, sides=10, bow=(0.0, 0.0, 0.0)):
    """A flesh tube p0 -> p1 with a muscle profile prof = [(t, radius), ...] and a sideways bow (m)."""
    p0, p1, bw = Vector(p0), Vector(p1), Vector(bow)
    pts = [p0.lerp(p1, t) + bw * math.sin(math.pi * t) for t, _ in prof]
    return M.tube(pts, [r for _, r in prof], sides=sides, cap=True)


def fist_parts(wr, tip, sx, k, seed):
    """A knuckle-walker's fist: a chamfered, lumpy obsidian block with a row of four knuckles at the end that
    meets the ground, a thumb block on the inner side. Returns [bmesh]."""
    hd = (tip - wr).normalized()
    F = frame_z(wr.lerp(tip, 0.52), hd, (sx, 0, 0))           # local Z = along the hand, +Y = the fist's front
    out = []
    blk = M.box((0.44 * k, 0.4 * k, 0.4 * k), bevel=0.06 * k, segments=2, taper=(0.95, 1.05))
    M.noise_displace(blk, 0.018 * k, freq=5.0, seed=seed)
    M.xform(blk, matrix=F)
    out.append(blk)
    for j, x in enumerate((-0.15, -0.05, 0.05, 0.15)):
        kn = M.box((0.1 * k, 0.13 * k, 0.11 * k), bevel=0.022 * k, taper=(0.85, 0.85))
        M.xform(kn, matrix=F @ M.trs(loc=(x * k * sx, 0.08 * k, (0.2 + 0.012 * (j % 2)) * k)))
        out.append(kn)
    th = M.box((0.12 * k, 0.16 * k, 0.2 * k), bevel=0.025 * k, taper=(0.8, 0.8))
    M.xform(th, matrix=F @ M.trs(loc=(-0.23 * k * sx, 0.1 * k, 0.02 * k), rot=(20, 0, -sx * 12)))
    out.append(th)
    return out


def shard(base, direction, radius, length, x_hint=(1, 0, 0), flat=0.55, sides=4):
    sp = M.spike(radius, length, sides=sides, base_scale=(1.0, flat), rot_offset=0 if sides == 4 else 45)
    M.xform(sp, matrix=frame_z(base, direction, x_hint))
    return sp


# ---- cracked plates ------------------------------------------------------------------------------------------
# A plate is authored once as a closed solid (the intact look). The cracked look is the same solid cut by jagged
# gaps: a thick polyline prism (drawn in the plate frame's XY plane, extruded along its Z through the whole plate)
# is subtracted with an EXACT boolean whose new faces take the cutter's material, so the crack walls are known.
# The islands are grouped into fragments by the nearest seed point, inset a little (so the intact plate hides the
# cracked copy when both are shown) and nudged apart.

def _prism(lines, gap, reach, frame):
    """Closed prisms around 2D polylines (width = gap, mitred joints), from z = -reach to +reach in `frame`."""
    out = bmesh.new()
    F = Matrix(frame)
    for ln in lines:
        P = [Vector((p[0], p[1])) for p in ln]
        n = len(P)
        left, right = [], []
        for i in range(n):
            t0 = (P[i] - P[i - 1]).normalized() if i > 0 else None
            t1 = (P[i + 1] - P[i]).normalized() if i < n - 1 else None
            if t0 is None:
                t0 = t1
            if t1 is None:
                t1 = t0
            nrm0 = Vector((-t0.y, t0.x))
            nrm1 = Vector((-t1.y, t1.x))
            m = (nrm0 + nrm1)
            m = m.normalized() if m.length > 1e-6 else nrm0
            k = 1.0 / max(0.35, m.dot(nrm1))
            left.append(P[i] + m * (gap * 0.5 * k))
            right.append(P[i] - m * (gap * 0.5 * k))
        ring = left + list(reversed(right))
        bot = [out.verts.new(F @ Vector((q.x, q.y, -reach))) for q in ring]
        top = [out.verts.new(F @ Vector((q.x, q.y, reach))) for q in ring]
        L = len(ring)
        out.faces.new(list(reversed(bot)))
        out.faces.new(top)
        for i in range(L):
            j = (i + 1) % L
            out.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(out, faces=out.faces[:])
    return out


def _mat(name):
    return bpy.data.materials.get(name) or bpy.data.materials.new(name)


def _islands(bm):
    """Connected face sets of a bmesh (lists of faces)."""
    parent = {}

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    for v in bm.verts:
        parent[v] = v
    for e in bm.edges:
        a, b = find(e.verts[0]), find(e.verts[1])
        if a is not b:
            parent[a] = b
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f.verts[0]), []).append(f)
    return list(groups.values())


def _copy_faces(faces):
    """A new bmesh holding copies of `faces` (smooth / sharp flags kept)."""
    out = bmesh.new()
    vm = {}
    for f in faces:
        vs = []
        for v in f.verts:
            if v not in vm:
                vm[v] = out.verts.new(v.co)
            vs.append(vm[v])
        try:
            nf = out.faces.new(vs)
            nf.smooth = f.smooth
        except ValueError:
            pass
    out.edges.ensure_lookup_table()
    for f in faces:
        for e in f.edges:
            if not e.smooth and all(v in vm for v in e.verts):
                ne = out.edges.get([vm[e.verts[0]], vm[e.verts[1]]])
                if ne is not None:
                    ne.smooth = False
    return out


def crack_solid(bm, lines, frame, gap, seeds, reach=1.0):
    """Cut the closed solid `bm` along 2D polylines in `frame`'s XY plane (projected along its Z) with a gap.
    Returns one entry per seed (2D, frame XY): {"surface": bmesh, "wall": bmesh, "centroid": Vector}; every
    island goes to the fragment of the nearest seed. `bm` is not modified."""
    ms, mw = _mat("_CRK_surface"), _mat("_CRK_wall")
    meA = bpy.data.meshes.new("_crkA")
    bm.to_mesh(meA)
    meA.materials.append(ms)
    A = bpy.data.objects.new("_crkA", meA)
    bpy.context.scene.collection.objects.link(A)
    cut = _prism(lines, gap, reach, frame)
    meB = bpy.data.meshes.new("_crkB")
    cut.to_mesh(meB)
    cut.free()
    meB.materials.append(mw)
    B = bpy.data.objects.new("_crkB", meB)
    bpy.context.scene.collection.objects.link(B)
    B.hide_render = True
    mod = A.modifiers.new("crk", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = B
    mod.material_mode = "TRANSFER"
    mod.use_self = True               # the plate's parts overlap (anvil face, horn, heel, waist)
    mod.use_hole_tolerant = True
    dg = bpy.context.evaluated_depsgraph_get()
    ev = A.evaluated_get(dg)
    me = ev.to_mesh()
    wall_idx = {i for i, m in enumerate(me.materials) if m is not None and m.name.startswith("_CRK_wall")}
    res = bmesh.new()
    res.from_mesh(me)
    ev.to_mesh_clear()
    bpy.data.objects.remove(A)
    bpy.data.objects.remove(B)
    bpy.data.meshes.remove(meA)
    bpy.data.meshes.remove(meB)
    bpy.context.view_layer.update()
    Fi = Matrix(frame).inverted()
    frags = [{"faces_s": [], "faces_w": [], "pts": []} for _ in seeds]
    for isl in _islands(res):
        cen = sum((f.calc_center_median() for f in isl), Vector()) / len(isl)
        q = Fi @ cen
        k = min(range(len(seeds)), key=lambda s: (q.x - seeds[s][0]) ** 2 + (q.y - seeds[s][1]) ** 2)
        for f in isl:
            (frags[k]["faces_w"] if f.material_index in wall_idx else frags[k]["faces_s"]).append(f)
            frags[k]["pts"].extend(v.co.copy() for v in f.verts)
    out = []
    for fr in frags:
        pts = fr["pts"]
        cen = sum(pts, Vector()) / max(1, len(pts))
        out.append({"surface": _copy_faces(fr["faces_s"]), "wall": _copy_faces(fr["faces_w"]), "centroid": cen})
    res.free()
    return out


# plate name -> parent bone; filled while modelling: FRAGS[plate] = [(centroid, outward), ...], PLATE_C[plate]
PLATE_PARENT = {"back": "spine_03", "pauldron": "clavicle_R", "helm": "head", "cuff_L": "lowerarm_L",
                "cuff_R": "lowerarm_R"}
PLATE_FRAGS = {"back": 3, "pauldron": 2, "helm": 2, "cuff_L": 2, "cuff_R": 2}
PLATES = list(PLATE_PARENT)
FRAGS = {}
PLATE_C = {}
PLATE_OUT = {}
CRACK_DECALS = []          # (lines, frame, width) of every crack, for the glow decals


def plate_bones():
    out = []
    for p in PLATES:
        out += ["plate_" + p, "plate_%s_crk" % p] + ["plate_%s_crk_%d" % (p, k + 1) for k in range(PLATE_FRAGS[p])]
    return out


BONE_NAMES = [b for b, _ in RD.HERO_CORE] + plate_bones()


def add_plate(a, name, parts, lines, frame, gap, seeds, out_dir, inset=0.975, sink=0.012, nudge=0.008, tilt=1.2,
              seed=0):
    """Add one plate twice: the intact parts on plate_<name>, and the cracked fragments (surface zone iron_crk,
    crack walls zone crack) on plate_<name>_crk_<n>. parts: [bmesh] (closed solids, merged for the cut).
    out_dir: the plate's outward direction (world); the cracked copy is scaled by `inset` about the plate centre
    and sunk `sink` m inward, so the intact plate hides it; fragments are nudged `nudge` m apart and tilted up
    to `tilt` degrees."""
    rng = random.Random(seed)
    solid = M.merge(*parts)
    pts = [v.co.copy() for v in solid.verts]
    cen = sum(pts, Vector()) / len(pts)
    PLATE_C[name] = cen
    out_dir = Vector(out_dir).normalized()
    PLATE_OUT[name] = out_dir
    frags = crack_solid(solid, lines, frame, gap, seeds)
    CRACK_DECALS.append((lines, frame, gap))
    for p in parts:
        a.add(p, "iron", bone="plate_" + name, name="plate_" + name, shading="auto")
    info = []
    for k, fr in enumerate(frags):
        fc = fr["centroid"]
        away = (fc - cen)
        away = away - out_dir * away.dot(out_dir)
        away = away.normalized() if away.length > 1e-6 else Vector((0, 0, 0))
        axis = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
        R = Matrix.Rotation(math.radians(rng.uniform(-tilt, tilt)), 4, axis)
        T = (Matrix.Translation(cen - out_dir * sink) @ Matrix.Scale(inset, 4) @ Matrix.Translation(-cen))
        Mf = Matrix.Translation(away * nudge) @ Matrix.Translation(fc) @ R @ Matrix.Translation(-fc)
        bone = "plate_%s_crk_%d" % (name, k + 1)
        for key_, zone in (("surface", "iron_crk"), ("wall", "crack")):
            b = fr[key_]
            if not len(b.faces):
                b.free()
                continue
            M.xform(b, matrix=Mf @ T)
            a.add(b, zone, bone=bone, name="plate_%s_crk" % name, shading="auto" if zone == "iron_crk" else "flat")
        c2 = Mf @ T @ fc
        o2 = (out_dir + away * 0.6).normalized()
        info.append((c2, o2))
    FRAGS[name] = info
    solid.free()


# ---- the model ----------------------------------------------------------------------------------------------------

def build_body(a):
    # torso: faceted obsidian masses - chest, hump (under the anvil), belly, pelvis
    a.add(blob((0.0, -0.22, 1.62), (0.6, 0.5, 0.42), rot=(-32, 0, 0), sub=2, noise=0.065, freq=2.2, seed=1, taper=0.3,
               jit=0.015),
          "obsidian", bone="spine_03", name="chest", shading="flat")
    a.add(blob((0.02, 0.04, 1.9), (0.62, 0.44, 0.3), rot=(8, 0, 5), sub=2, noise=0.04, freq=2.6, seed=2, taper=-0.15),
          "obsidian", bone="spine_03", name="hump", shading="flat")
    # the trapezius ridge that carries the anvil: a wide flat mass from shoulder to shoulder
    a.add(blob((0.0, -0.06, 1.98), (0.7, 0.3, 0.18), rot=(-10, 0, 3), sub=2, noise=0.03, freq=3.0, seed=5),
          "obsidian", bone="spine_03", name="traps", shading="flat")
    a.add(blob((0.0, 0.02, 1.27), (0.47, 0.41, 0.32), rot=(-14, 0, 0), sub=2, noise=0.03, freq=3.0, seed=3),
          "obsidian", bone="spine_01", name="belly", shading="flat")
    a.add(blob((0.0, 0.16, 0.98), (0.41, 0.34, 0.25), sub=1, noise=0.02, freq=3.0, seed=4),
          "obsidian", bone="pelvis", name="hips", shading="flat")
    # obsidian shards jutting from the lower back behind the anvil (the Unmade's wrong, knapped edges)
    for k, (x, y, z, d, L) in enumerate(((0.16, 0.4, 1.52, (0.25, 0.8, 0.55), 0.3), (-0.22, 0.43, 1.38, (-0.3, 0.85, 0.4), 0.26),
                                          (0.34, 0.26, 1.78, (0.55, 0.55, 0.6), 0.22), (-0.04, 0.38, 1.2, (0.0, 0.9, 0.2), 0.2))):
        a.add(shard((x, y, z), d, 0.07, L, x_hint=(1, 0, 0), flat=0.5), "obsidian", bone="spine_02" if z < 1.7 else "spine_03",
              name="back_shard", shading="flat")


def build_head(a):
    hc = P_("head") + Vector((0.0, -0.1, 0.0))
    skull = blob(hc + Vector((0, 0.0, 0.02)), (0.2, 0.2, 0.17), sub=1, noise=0.02, seed=11)
    a.add(skull, "obsidian", bone="head", name="skull", shading="flat")
    # the underbite: a heavy jaw of obsidian with fangs, the teal maw between
    jaw = M.box((0.34, 0.26, 0.12), bevel=0.02, taper=(1.1, 1.0))
    M.xform(jaw, loc=hc + Vector((0, -0.08, -0.13)), rot=(8, 0, 0))
    a.add(jaw, "obsidian", bone="head", name="jaw", shading="flat")
    for k, x in enumerate((-0.12, -0.05, 0.04, 0.12)):
        a.add(shard(hc + Vector((x, -0.2, -0.08)), (0.1 * x, -0.25, 1.0), 0.028, 0.08 + 0.02 * (k % 2), flat=0.6),
              "obsidian", bone="head", name="fang", shading="flat")
    maw = M.box((0.24, 0.05, 0.05))
    M.xform(maw, loc=hc + Vector((0, -0.17, -0.06)))
    a.add(maw, "ichor", bone="head", name="maw", shading="flat")
    # eyes glowing behind the visor slit
    for sx in (-1, 1):
        e = M.ico(0.04, 1, scale=(1.7, 0.7, 0.42))
        M.xform(e, loc=hc + Vector((sx * 0.075, -0.175, 0.04)), rot=(0, -sx * 20, 0))
        a.add(e, "ichor", bone="head", name="eye", shading="flat")


def helm_parts():
    """The iron visor: one thick hammered shell over the brow and the face, open across the eyes in a single slit
    (the teal eyes glow through it); the obsidian jaw juts out below."""
    hc = P_("head") + Vector((0.0, -0.1, 0.0))
    prof = [(0.205, -0.07), (0.222, 0.02), (0.222, 0.1), (0.19, 0.18), (0.11, 0.235), (0.02, 0.25)]
    nu, nv = 12, 5

    def slit(i, j):
        th = -90 - 75 + 150 * (i + 0.5) / nu
        return not (j == 1 and abs(th + 90) < 58)
    fn = S.rev_fn(prof, -90 - 75, -90 + 75, sx=1.0, sy=1.08, matrix=Matrix.Translation(hc), smooth=3)
    shell, _ = S.thick_patch(fn, nu, nv, 0.045, keep=slit, inner=False)
    parts = [shell]
    # a heavy V of brow over the slit: the inner ends drop, so the eyes glare instead of staring
    for sx in (-1, 1):
        brow = M.box((0.17, 0.07, 0.055), bevel=0.012)
        M.xform(brow, loc=hc + Vector((sx * 0.085, -0.228, 0.098)), rot=(-8, -sx * 18, sx * 12))
        parts.append(brow)
    return parts, hc


def pauldron_parts():
    """The right shoulder: two stepped anvil-iron domes (thick hammered shells) over the deltoid."""
    sh = P_("shoulder_R")
    axis = Vector((-0.6, 0.05, 1.0)).normalized()
    fr = frame_z(Vector((sh.x - 0.1, sh.y + 0.02, sh.z + 0.1)), axis, (0, -1, 0))
    d1 = S.cap_fn(0.34, 0.15, 0, 360, sx=1.08, sy=1.0, matrix=fr)
    s1, _ = S.thick_patch(d1, 12, 3, 0.06, wrap_u=True, inner=False)
    d2 = S.cap_fn(0.22, 0.1, 0, 360, sx=1.1, sy=1.0, matrix=fr @ Matrix.Translation((0.03, 0.0, 0.1)))
    s2, _ = S.thick_patch(d2, 10, 2, 0.05, wrap_u=True, inner=False)
    return [s1, s2], fr


def weld_ring(sink=0.0, scale=1.0):
    """The ichor weld: a glowing seam round the anvil's waist where it is fused into the hump."""
    ring = []
    for i in range(12):
        t = 2 * math.pi * i / 12
        ring.append(ANVIL_M @ Vector((-0.12 + 0.3 * scale * math.cos(t), 0.185 * scale * math.sin(t), -0.26 - sink)))
    return M.tube(ring, 0.03, sides=5, closed=True)


def cuff_parts(side):
    """An iron cuff round the forearm: an octagonal band, heavier on the slam arm (left)."""
    sx = 1 if side == "L" else -1
    el, wr = P_("elbow_" + side), P_("wrist_" + side)
    ax = (wr - el).normalized()
    big = side == "L"
    L = 0.36 if big else 0.28
    c = el.lerp(wr, 0.62)
    r_in = 0.232 if big else 0.205
    band = M.ring(r_in, r_in + (0.055 if big else 0.048), L, sides=8, bevel=0.012, start_angle=22.5)
    fr = frame_z(c, ax, (sx, 0, 0))
    M.xform(band, matrix=fr)
    return [band], fr, c, ax


def build_plates(a):
    # --- the anvil (back): polished face slab, table step, bull-swept horn, heel, pinched waist ---------------------
    parts = []
    face = M.box((0.98, 0.44, 0.17), bevel=0.026, segments=1)
    M.xform(face, loc=(-0.14, 0.0, 0.055))
    parts.append(face)
    heel = M.box((0.2, 0.36, 0.13), bevel=0.018, taper=(0.55, 0.85))
    M.xform(heel, loc=(-0.52, 0.0, -0.09), rot=(180, 0, 0))
    parts.append(heel)
    horn = M.horn([(0.3, 0.0, 0.0), (0.58, 0.0, 0.012), (0.84, 0.0, 0.05), (1.04, 0.0, 0.14), (1.16, 0.0, 0.27)],
                  0.13, 0.012, sides=8)
    parts.append(horn)
    step = M.box((0.12, 0.3, 0.13), bevel=0.012)
    M.xform(step, loc=(0.36, 0.0, -0.005))
    parts.append(step)
    waist = M.loft_rect([(0.0, 0.62, 0.34, 0.0, 0.0), (0.13, 0.38, 0.25, 0.0, 0.0), (0.32, 0.64, 0.36, 0.0, 0.0)],
                        bevel=0.015)
    M.xform(waist, loc=(-0.12, 0.0, -0.02), rot=(-90, 0, 0))
    parts.append(waist)
    for p in parts:
        M.xform(p, matrix=ANVIL_M)
    rng = random.Random(7)
    lines = [
        _jag(rng, (0.26, -0.5), (0.36, 0.5), 5, 0.045),          # across the face at the horn's root
        _jag(rng, (-0.34, -0.5), (-0.22, 0.5), 5, 0.045),         # across the face near the heel
    ]
    add_plate(a, "back", parts, lines, ANVIL_M, 0.055, [(0.7, 0.0), (0.0, 0.0), (-0.5, 0.0)],
              out_dir=ANVIL_M.to_3x3() @ Vector((0, 0, 1)), inset=0.978, sink=0.014, nudge=0.012, tilt=1.4, seed=3)
    # the glowing weld rides the anvil (intact) and its middle fragment (cracked): it leaves with the plate
    a.add(weld_ring(), "ichor", bone="plate_back", name="plate_back_weld", shading="smooth")
    a.add(weld_ring(0.006, 0.99), "ichor", bone="plate_back_crk_2", name="plate_back_weld_crk", shading="smooth")
    # --- the right pauldron ----------------------------------------------------------------------------------
    parts, fr = pauldron_parts()
    lines = [_jag(random.Random(9), (-0.5, 0.04), (0.5, -0.04), 4, 0.04)]
    add_plate(a, "pauldron", parts, lines, fr, 0.045, [(0.0, -0.2), (0.0, 0.2)],
              out_dir=fr.to_3x3() @ Vector((0, 0, 1)), inset=0.965, sink=0.012, nudge=0.008, tilt=1.2, seed=5)
    # --- the visor -------------------------------------------------------------------------------------------
    parts, hc = helm_parts()
    hf = frame_z(hc, (0, -1.0, 0.0), (1, 0, 0))              # local X = the brute's left, Y = up, Z = forward
    lines = [_jag(random.Random(12), (0.025, -0.5), (-0.03, 0.5), 5, 0.028)]
    add_plate(a, "helm", parts, lines, hf, 0.032, [(-0.15, 0.0), (0.15, 0.0)], out_dir=(0, -0.7, 0.7), inset=0.95,
              sink=0.0, nudge=0.004, tilt=0.6, seed=8)
    # --- the forearm cuffs -------------------------------------------------------------------------------------
    for side in ("L", "R"):
        parts, fr, c, ax = cuff_parts(side)
        sx = 1 if side == "L" else -1
        # crack along the arm through both sides of the band (frame: Z = across the arm, X = along it)
        cf = frame_z(c, (sx, 0.0, 0.0), tuple(ax))
        lines = [_jag(random.Random(20 + sx), (-0.4, 0.02), (0.4, -0.02), 4, 0.03)]
        add_plate(a, "cuff_" + side, parts, lines, cf, 0.038, [(0.0, 0.3), (0.0, -0.3)],
                  out_dir=(sx, -0.4, 0.3), inset=0.93, sink=0.0, nudge=0.004, tilt=0.5, seed=30 + sx)


def _jag(rng, p0, p1, n, amp):
    """A jagged 2D crack from p0 to p1 with n interior zig-zag points (+-amp across the line)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    nrm = Vector((-d.y, d.x)).normalized()
    pts = [tuple(p0)]
    for i in range(1, n + 1):
        t = i / (n + 1) + rng.uniform(-0.3, 0.3) / (n + 1)
        q = p0 + d * t + nrm * (amp * (1 if i % 2 else -1) * rng.uniform(0.6, 1.2))
        pts.append((q.x, q.y))
    pts.append(tuple(p1))
    return pts


def scute(a, pos, normal, size, bone, seed, up=(0, 0, 1)):
    """A knapped obsidian plate fused into the flesh (flattened, faceted), facing `normal`."""
    b = M.ico(1.0, 1, scale=size)
    M.jitter(b, random.Random(seed), 0.08)
    M.xform(b, matrix=frame_z(pos, normal, up))
    a.add(b, "obsidian", bone=bone, name="scute", shading="flat")


def build_arm(a, side):
    sx = 1 if side == "L" else -1
    big = side == "L"
    sh, el, wr, tip = P_("shoulder_" + side), P_("elbow_" + side), P_("wrist_" + side), P_("hand_%s_tip" % side)
    k = 1.0 if big else 0.87
    # deltoid mass + upper arm (flesh), forearm thickening toward the fist (gorilla)
    a.add(blob(sh + Vector((sx * 0.08, -0.02, 0.0)), (0.27 * k, 0.26 * k, 0.25 * k), sub=2, noise=0.02, seed=40 + sx),
          "flesh", bone="upperarm_" + side, name="deltoid", shading="smooth")
    a.add(muscle(sh, el, [(0.0, 0.2 * k), (0.3, 0.24 * k), (0.55, 0.215 * k), (0.85, 0.16 * k), (1.0, 0.15 * k)],
                 bow=(sx * 0.05, -0.04, 0.0)), "flesh", bone="upperarm_" + side, name="upperarm", shading="smooth")
    a.add(muscle(el, wr, [(0.0, 0.15 * k), (0.22, 0.205 * k), (0.5, 0.215 * k), (0.8, 0.19 * k), (1.0, 0.165 * k)],
                 bow=(sx * 0.03, -0.03, 0.0)), "flesh", bone="lowerarm_" + side, name="forearm", shading="smooth")
    # the fist: a lumpy obsidian block with a knuckle row where it meets the ground, crystals over the knuckles
    fc = wr.lerp(tip, 0.58)
    for b_ in fist_parts(wr, tip, sx, k, 50 + sx):
        a.add(b_, "obsidian", bone="hand_" + side, name="fist", shading="flat")
    for j, (ox, oz) in enumerate(((-0.12, 0.0), (0.0, 0.04), (0.12, 0.0))):
        base = fc + Vector((ox * k, -0.17 * k, (oz - 0.02) * k))
        a.add(shard(base, (ox * 0.8, -1.0, 0.2), 0.055 * k, (0.14 + 0.04 * (j == 1)) * k, flat=0.6), "obsidian",
              bone="hand_" + side, name="knuckle", shading="flat")
    # knapped obsidian plates fused into the upper arm (the flesh-and-mineral of the Unmade)
    for j, (t, sz) in enumerate(((0.35, (0.13, 0.1, 0.045)), (0.62, (0.11, 0.085, 0.04)))):
        if not big and j == 1:
            continue
        c_ = sh.lerp(el, t)
        out = Vector((sx * 1.0, 0.25, 0.15)).normalized()
        scute(a, c_ + out * 0.18 * k, out, tuple(v * k for v in sz), "upperarm_" + side, 70 + j + (5 if big else 0),
              up=tuple(sh - el))
    if big:
        # the slam arm grew a crest of obsidian along the forearm's outer edge
        for j in range(3):
            t = 0.08 + 0.12 * j
            base = el.lerp(wr, t) + Vector((sx * 0.19, 0.07, 0.0))
            a.add(shard(base, (sx * 0.8, 0.5, 0.25), 0.055, 0.2 - 0.03 * j, flat=0.5), "obsidian",
                  bone="lowerarm_" + side, name="arm_shard", shading="flat")


def build_leg(a, side):
    sx = 1 if side == "L" else -1
    hip, kn, an, ball = (P_(k + "_" + side) for k in ("hip", "knee", "ankle", "ball"))
    a.add(muscle(hip, kn, [(0.0, 0.24), (0.35, 0.27), (0.7, 0.22), (1.0, 0.17)], bow=(sx * 0.03, 0.0, 0.0)), "flesh",
          bone="thigh_" + side, name="thigh", shading="smooth")
    a.add(muscle(kn, an, [(0.0, 0.16), (0.3, 0.19), (0.7, 0.15), (1.0, 0.13)], bow=(0.0, 0.035, 0.0)), "flesh",
          bone="shin_" + side, name="shin", shading="smooth")
    out = Vector((sx * 1.0, -0.2, 0.0)).normalized()
    scute(a, hip.lerp(kn, 0.45) + out * 0.21, out, (0.12, 0.09, 0.045), "thigh_" + side, 80 + sx, up=tuple(hip - kn))
    knee = M.box((0.24, 0.24, 0.13), bevel=0.03, taper=(0.72, 0.7))
    M.noise_displace(knee, 0.012, freq=6.0, seed=60 + sx)
    M.xform(knee, matrix=frame_z(kn + Vector((0, -0.1, 0.02)), (0, -1.0, 0.25), (1, 0, 0)))
    a.add(knee, "obsidian", bone="shin_" + side, name="knee", shading="flat")
    foot = M.box((0.31, 0.38, 0.17), bevel=0.03, taper=(0.8, 0.7), shear=(0, 0.04))
    M.xform(foot, loc=(an.x, an.y - 0.06, 0.085))
    a.add(foot, "obsidian", bone="foot_" + side, name="foot", shading="flat")
    for j, ox in enumerate((-0.09, 0.02, 0.11)):
        a.add(shard((ball.x + sx * ox, ball.y + 0.02, 0.05), (0.2 * ox, -1.0, -0.15), 0.05, 0.13, flat=0.6),
              "obsidian", bone="toe_" + side, name="toe", shading="flat")


def build_mesh(col):
    FRAGS.clear()
    PLATE_C.clear()
    PLATE_OUT.clear()
    CRACK_DECALS.clear()
    a = M.Assembly(KEY + "_mesh", ZONES, bones=BONE_NAMES)
    build_body(a)
    build_head(a)
    for s in ("L", "R"):
        build_arm(a, s)
        build_leg(a, s)
    build_plates(a)
    obj = a.to_object(col)
    obj["gfa_part_names"] = ",".join(p["name"] for p in a.parts)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    zt = {}
    for p in obj.data.polygons:
        z = ZONES[p.material_index]
        zt[z] = zt.get(z, 0) + len(p.vertices) - 2
    C.log("tris per zone: %s" % zt)
    return obj, a.parts


# ---- rig ------------------------------------------------------------------------------------------------------------
# GF_AnvilBrute_v1: the 23 GF_Hero_v1 core bones (docs/ART_PIPELINE.md section 5) + per plate p:
#   plate_<p>            the INTACT plate (child of its body bone)
#   plate_<p>_crk        the CRACKED plate group (same parent, same pivot)
#   plate_<p>_crk_<n>    one joint per fragment (child of the group), so plates_break can blow them off
# The engine switches a plate's state by scaling plate_<p> / plate_<p>_crk after the animation system (README).

CORE_BONES = [  # (name, parent, head landmark, tail landmark)
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
]


def rig_table():
    t = [(n, par, tuple(P_(h)), tuple(P_(tl))) for n, par, h, tl in CORE_BONES]
    for p in PLATES:
        c, o = PLATE_C[p], PLATE_OUT[p]
        for b in ("plate_" + p, "plate_%s_crk" % p):
            t.append((b, PLATE_PARENT[p], tuple(c), tuple(c + o * 0.25)))
        for k, (fc, fo) in enumerate(FRAGS[p]):
            t.append(("plate_%s_crk_%d" % (p, k + 1), "plate_%s_crk" % p, tuple(fc), tuple(fc + fo * 0.2)))
    return t


def build_rig(col):
    arm = RD.build_armature(RIG_NAME, rig_table(), col)
    probs = RD.validate_core(arm)
    if probs:
        raise RuntimeError("rig problems: %s" % probs)
    return arm


SOCKETS = {  # name: (bone, position) - ENEMIES.md section 5 names (+ the slam impact points)
    "hit_center": ("spine_03", (0.0, -0.3, 1.62)),
    "fx_core": ("spine_03", tuple(CORE_POS)),
    "head_top": ("spine_03", (0.0, 0.0, 3.0)),
    "fx_mouth": ("head", (0.0, -0.9, 1.6)),
    "attack_origin": ("spine_03", (0.0, -0.95, 1.45)),
    "impact_L": ("hand_L", (0.97, -0.84, 0.12)),
    "impact_R": ("hand_R", (-0.9, -0.78, 0.15)),
}


def add_sockets(arm):
    import gfa_rig as RIG
    out = {}
    for name, (bone, pos) in SOCKETS.items():
        RIG.add_socket(arm, bone, name, pos, size=0.06)
        out[name] = {"bone": bone, "blender_pos": [round(v, 3) for v in pos],
                     "gltf_pos": [round(v, 3) for v in C.blender_to_gltf(pos)]}
    return out


class Solver:
    """Poses GF_AnvilBrute_v1 from a parameter dict, in armature space: FK spine / neck / head / clavicles,
    two-bone IK that plants the feet AND the fists (a knuckle-walker: the fists are feet as often as weapons),
    the hand following its forearm, and the plate fragments flung by plates_break.

    POSE PARAMETERS (degrees, metres; the armature is at the world origin):
      body:          loc (dx, dy, dz) WORLD offset of the pelvis; rot (x bend forward, y twist left, z roll)
      spine_01..03, neck, clavicle_*:  rot / loc, bone-local (+X bends the spine forward)
      head:          rot, bone-local: the head bone points FORWARD, so +X looks UP, +Z tilts toward its right
      foot_L/R:      off (dx, dy, dz) world offset of the ankle; pitch (toes up +)
      knee_L/R:      hint (x, y, z) added to the knee direction (+-0.3, -1, 0)
      fist_L/R:      off (dx, dy, dz) offset of the wrist from its rest point, or at (x, y, z) an absolute world
                     wrist target; space 0 = carried by the chest, 1 = planted on the ground (default 1);
                     rot (x, y, z) hand-local on top of following the forearm; elbow (x, y, z) added to the
                     elbow hint (outward, back)
      frag:          {plate: t} flight progress 0..1 of that plate's fragments (plates_break)
      scale:         {bone: s} extra joint scales (plate states inside a clip, fragments shrinking)
    """

    FK = ("spine_01", "spine_02", "spine_03", "neck", "head", "clavicle_L", "clavicle_R")

    def __init__(self, arm):
        self.arm = arm
        self.R = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        rng = random.Random(77)
        self.spin = {}
        for p in PLATES:
            for k in range(PLATE_FRAGS[p]):
                ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
                self.spin["plate_%s_crk_%d" % (p, k + 1)] = (ax, rng.uniform(200, 340) * rng.choice((-1, 1)),
                                                              rng.uniform(0.85, 1.25))

    def _fk(self, bone, tr):
        pb = self.arm.pose.bones[bone]
        if "rot" in tr:
            pb.rotation_euler = RD.euler_deg(tr["rot"])
        if "loc" in tr:
            pb.location = Vector(tr["loc"])

    def _arm_ik(self, side, spec):
        arm, R = self.arm, self.R
        sx = 1 if side == "L" else -1
        rest_w = R["hand_" + side].translation.copy()
        w = float(spec.get("space", 1.0))
        if "at" in spec:
            target = Vector(spec["at"])
        else:
            q = rest_w + Vector(spec.get("off", (0, 0, 0)))
            chest = arm.pose.bones["spine_03"].matrix @ R["spine_03"].inverted() @ q
            target = chest.lerp(q, w)
        hint = Vector((sx * 0.9, 0.55, -0.1)) + Vector(spec.get("elbow", (0, 0, 0)))
        RD.two_bone_ik(arm, "upperarm_" + side, "lowerarm_" + side, target, hint)
        lo = arm.pose.bones["lowerarm_" + side].matrix
        hm = lo @ R["lowerarm_" + side].inverted() @ R["hand_" + side]
        hm = hm @ RD.euler_deg(spec.get("rot", (0, 0, 0))).to_matrix().to_4x4()
        hm.translation = lo @ Vector((0.0, arm.data.bones["lowerarm_" + side].length, 0.0))
        RD.set_matrix(arm, "hand_" + side, hm)

    def _frags(self, frag):
        arm, R = self.arm, self.R
        for p, t in frag.items():
            if t <= 0:
                continue
            for k in range(PLATE_FRAGS[p]):
                b = "plate_%s_crk_%d" % (p, k + 1)
                par = "plate_%s_crk" % p
                base = arm.pose.bones[par].matrix @ R[par].inverted() @ R[b]
                ax, deg, sp = self.spin[b]
                out = (base.to_3x3() @ Vector((0, 1, 0))).normalized()     # bone +Y = the fragment's outward
                tt = min(1.0, t * sp)
                d = out * (1.15 * tt) + Vector((0, 0, 1.0)) * (0.9 * tt) - Vector((0, 0, 1.0)) * (2.1 * tt * tt)
                rot = Matrix.Rotation(math.radians(deg * tt), 4, ax)
                m = Matrix.Translation(base.translation + d) @ rot @ base.to_3x3().to_4x4()
                RD.set_matrix(arm, b, m, upd=False)
        RD.update()

    def pose(self, p):
        arm = self.arm
        RD.reset(arm)
        body = p.get("body", {})
        pv = arm.pose.bones["pelvis"]
        pv.location = self.R["pelvis"].to_3x3().inverted() @ Vector(body.get("loc", (0, 0, 0)))
        pv.rotation_euler = RD.euler_deg(body.get("rot", (0, 0, 0)))
        for b in self.FK:
            if b in p:
                self._fk(b, p[b])
        RD.update()
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
        for side in ("L", "R"):
            self._arm_ik(side, p.get("fist_" + side, {}))
        RD.update()
        if p.get("frag"):
            self._frags(p["frag"])
        for b, s in p.get("scale", {}).items():
            arm.pose.bones[b].scale = (s, s, s)
        RD.update()


# ---- clips -----------------------------------------------------------------------------------------------------------
# All poses are offsets from the rest stance (hunched, knuckles planted). World metres / degrees; see Solver.

def P2(*poses):
    return RD.merge(*poses)


def idle_pose(t):
    w = 2 * math.pi * t
    s, c = math.sin(w), math.cos(w)
    return {
        "body": {"loc": (0.01 * c, 0.0, -0.02 + 0.022 * s), "rot": (1.5 * s, 0.0, 1.2 * c)},
        "spine_02": {"rot": (-1.5 * s, 0.0, 0.0)},
        "spine_03": {"rot": (-2.5 * math.sin(w + 0.4), 1.5 * c, 0.0)},       # the heaving chest lifts the anvil
        "neck": {"rot": (1.5 * s, 0.0, 0.0)},
        "head": {"rot": (-3.0 + 3.0 * math.sin(w + 1.2), 0.0, 0.0), "loc": (0.0, 0.0, 0.0)},
        "fist_L": {"off": (0.0, 0.0, 0.0), "rot": (2.0 * s, 0, 0)},
        "fist_R": {"off": (0.0, 0.0, 0.012 * max(0.0, math.sin(w * 2 + 0.5))), "rot": (-2.0 * s, 0, 0)},
    }


MOVE_FRAMES = 24          # 0.8 s knuckle-walk cycle
MOVE_STRIDE = 0.42        # foot / fist travel either side of the rest line (m)
MOVE_STANCE = 0.58        # fraction of the cycle a foot or fist is planted
MOVE_CYCLE_M = 2 * MOVE_STRIDE / MOVE_STANCE   # ground covered per cycle (client: playback = speed / this)


def _track(t, stride, stance, lift, pitch=14.0):
    """(dy, dz, pitch) of a planted-then-swung limb whose contact is at t = 0 (+dy = back)."""
    t %= 1.0
    if t < stance:
        s = t / stance
        return (-stride + 2 * stride * s, 0.0, -6.0 * max(0.0, (s - 0.75) / 0.25))
    s = (t - stance) / (1 - stance)
    e = s * s * (3 - 2 * s)
    return (stride - 2 * stride * e, lift * math.sin(math.pi * s) ** 1.2, pitch * math.sin(math.pi * s * 0.9))


def move_pose(t):
    w = 2 * math.pi * t
    yl, zl, pl = _track(t, MOVE_STRIDE, MOVE_STANCE, 0.2)
    yr, zr, pr = _track(t + 0.5, MOVE_STRIDE, MOVE_STANCE, 0.2)
    al, azl, _ = _track(t + 0.5 + 0.08, MOVE_STRIDE * 1.1, MOVE_STANCE, 0.3)    # fists: diagonal to the feet
    ar, azr, _ = _track(t + 0.08, MOVE_STRIDE * 1.1, MOVE_STANCE, 0.3)
    bob = -0.05 + 0.045 * (1 - math.cos(2 * w)) / 2
    return {
        "body": {"loc": (0.05 * math.sin(w), 0.0, bob), "rot": (4.0, -6.0 * math.sin(w), 4.0 * math.sin(w))},
        "spine_02": {"rot": (2.0 + 1.5 * math.cos(2 * w), 4.0 * math.sin(w), -2.0 * math.sin(w))},
        "spine_03": {"rot": (1.0, 5.0 * math.sin(w), -3.0 * math.sin(w))},
        "neck": {"rot": (-2.0, -4.0 * math.sin(w), 0.0)},
        "head": {"rot": (4.0 + 2.0 * math.cos(2 * w), 0.0, 3.0 * math.sin(w))},
        "foot_L": {"off": (0.0, yl, zl), "pitch": pl},
        "foot_R": {"off": (0.0, yr, zr), "pitch": pr},
        "fist_L": {"off": (0.0, al - 0.06, azl), "rot": (-10.0 * azl / 0.3, 0, 0)},
        "fist_R": {"off": (0.0, ar - 0.06, azr), "rot": (-10.0 * azr / 0.3, 0, 0)},
    }


CHARGE_FRAMES = 12        # 0.4 s bounding gallop, head down behind the anvil


def charge_pose(t):
    w = 2 * math.pi * t
    fl, fzl, _ = _track(t, 0.5, 0.45, 0.32)
    fr_, fzr, _ = _track(t + 0.06, 0.5, 0.45, 0.32)
    yl, zl, pl = _track(t + 0.5, 0.42, 0.5, 0.26, 20.0)
    yr, zr, pr = _track(t + 0.6, 0.42, 0.5, 0.26, 20.0)
    return {
        "body": {"loc": (0.0, -0.22, -0.12 + 0.07 * math.sin(w + 1.0)), "rot": (22.0 + 5.0 * math.sin(w), 0.0, 0.0)},
        "spine_01": {"rot": (4.0, 0.0, 0.0)},
        "spine_02": {"rot": (4.0 - 3.0 * math.sin(w + 0.6), 0.0, 0.0)},
        "spine_03": {"rot": (6.0 - 3.0 * math.sin(w + 0.9), 0.0, 0.0)},
        "neck": {"rot": (-6.0, 0.0, 0.0)},
        "head": {"rot": (14.0, 0.0, 0.0)},
        "foot_L": {"off": (0.0, yl + 0.1, zl), "pitch": pl},
        "foot_R": {"off": (0.0, yr + 0.1, zr), "pitch": pr},
        "knee_L": {"hint": (0.1, 0.0, 0.0)}, "knee_R": {"hint": (-0.1, 0.0, 0.0)},
        "fist_L": {"off": (-0.1, fl - 0.42, fzl + 0.05), "rot": (-18.0 * fzl / 0.32, 0, 0)},
        "fist_R": {"off": (0.1, fr_ - 0.42, fzr + 0.05), "rot": (-18.0 * fzr / 0.32, 0, 0)},
    }


# the overhead slam: gather, rear up with both fists clasped high over the head, hammer them down
GATHER = {
    "body": {"loc": (0.0, 0.06, -0.12), "rot": (6.0, 0.0, 0.0)},
    "spine_02": {"rot": (4.0, 0, 0)}, "spine_03": {"rot": (6.0, 0, 0)}, "head": {"rot": (-6.0, 0, 0)},
    "fist_L": {"off": (-0.25, 0.28, 0.45), "space": 0.3, "rot": (-30, 0, 0)},
    "fist_R": {"off": (0.25, 0.28, 0.45), "space": 0.3, "rot": (-30, 0, 0)},
    "knee_L": {"hint": (0.1, 0.0, 0.0)}, "knee_R": {"hint": (-0.1, 0.0, 0.0)},
}
OVERHEAD = {
    "body": {"loc": (0.0, 0.14, 0.1), "rot": (-20.0, 0.0, 0.0)},
    "spine_01": {"rot": (-6.0, 0, 0)}, "spine_02": {"rot": (-7.0, 0, 0)}, "spine_03": {"rot": (-7.0, 0, 0)},
    "neck": {"rot": (-6.0, 0, 0)}, "head": {"rot": (22.0, 0, 0)},
    "clavicle_L": {"rot": (0.0, 0.0, 0.0)}, "clavicle_R": {"rot": (0.0, 0.0, 0.0)},
    "fist_L": {"at": (0.15, 0.12, 3.32), "rot": (0, 0, 0), "elbow": (0.3, 0.2, 0.3)},
    "fist_R": {"at": (-0.15, 0.12, 3.32), "rot": (0, 0, 0), "elbow": (-0.3, 0.2, 0.3)},
    "foot_L": {"off": (0.0, 0.06, 0.0)}, "foot_R": {"off": (0.0, 0.06, 0.0)},
}
LOADED = P2(OVERHEAD, {
    "body": {"loc": (0.0, 0.18, 0.12), "rot": (-23.0, 0.0, 0.0)},
    "spine_03": {"rot": (-9.0, 0, 0)},
    "fist_L": {"at": (0.13, 0.3, 3.42), "rot": (0, 0, 0), "elbow": (0.3, 0.2, 0.3)},
    "fist_R": {"at": (-0.13, 0.3, 3.42), "rot": (0, 0, 0), "elbow": (-0.3, 0.2, 0.3)},
})
IMPACT = {
    "body": {"loc": (0.0, -0.34, -0.2), "rot": (34.0, 0.0, 0.0)},
    "spine_01": {"rot": (6.0, 0, 0)}, "spine_02": {"rot": (8.0, 0, 0)}, "spine_03": {"rot": (8.0, 0, 0)},
    "neck": {"rot": (-8.0, 0, 0)}, "head": {"rot": (18.0, 0, 0)},
    "fist_L": {"at": (0.2, -1.45, 0.42), "rot": (-20, 0, 0), "elbow": (0.2, 0.1, 0.0)},
    "fist_R": {"at": (-0.2, -1.45, 0.42), "rot": (-20, 0, 0), "elbow": (-0.2, 0.1, 0.0)},
    "foot_L": {"off": (0.0, -0.05, 0.0)}, "foot_R": {"off": (0.0, 0.1, 0.0), "pitch": 8.0},
    "knee_L": {"hint": (0.1, 0.0, 0.0)}, "knee_R": {"hint": (-0.1, 0.0, 0.0)},
}
FLINCH = {
    "body": {"loc": (0.02, 0.1, 0.03), "rot": (-9.0, 4.0, -4.0)},
    "spine_02": {"rot": (-4.0, 0, 0)}, "spine_03": {"rot": (-7.0, 3.0, 3.0)},
    "neck": {"rot": (-4.0, 0, 0)}, "head": {"rot": (16.0, 6.0, -6.0)},
    "fist_L": {"off": (0.05, 0.1, 0.16), "space": 0.4}, "fist_R": {"off": (-0.05, 0.06, 0.1), "space": 0.4},
}
ROAR = {
    "body": {"loc": (0.0, 0.12, 0.08), "rot": (-16.0, 0.0, 0.0)},
    "spine_02": {"rot": (-6.0, 0, 0)}, "spine_03": {"rot": (-10.0, 0, 0)},
    "neck": {"rot": (-4.0, 0, 0)}, "head": {"rot": (26.0, 0, 0)},
    "fist_L": {"at": (1.55, -0.35, 1.7), "rot": (0, 0, 20), "elbow": (0.0, 0.4, -0.3)},
    "fist_R": {"at": (-1.5, -0.35, 1.7), "rot": (0, 0, -20), "elbow": (0.0, 0.4, -0.3)},
}
DEATH_JOLT = P2(FLINCH, {"body": {"loc": (0.0, 0.16, 0.05), "rot": (-14.0, 6.0, -6.0)}, "head": {"rot": (24.0, 10.0, -8.0)}})
DEATH_KNEEL = {
    "body": {"loc": (0.0, 0.05, -0.36), "rot": (8.0, 6.0, 4.0)},
    "spine_02": {"rot": (6.0, 0, 0)}, "spine_03": {"rot": (8.0, 0, 2.0)}, "head": {"rot": (-12.0, 4.0, 4.0)},
    "knee_L": {"hint": (0.3, -0.4, 0.0)}, "knee_R": {"hint": (-0.3, -0.4, 0.0)},
    "fist_L": {"off": (0.12, 0.0, 0.0)}, "fist_R": {"off": (-0.1, 0.05, 0.0)},
}
DEATH_DOWN = {
    "body": {"loc": (0.0, -0.36, -0.6), "rot": (52.0, 8.0, 6.0)},
    "spine_01": {"rot": (8.0, 0, 0)}, "spine_02": {"rot": (8.0, 0, 3.0)}, "spine_03": {"rot": (6.0, 0, 4.0)},
    "neck": {"rot": (4.0, 0, 0)}, "head": {"rot": (-10.0, 10.0, 16.0)},
    "knee_L": {"hint": (0.5, -0.6, 0.0)}, "knee_R": {"hint": (-0.5, -0.6, 0.0)},
    "foot_L": {"roll": -10.0}, "foot_R": {"roll": 10.0},
    "fist_L": {"at": (1.45, -1.0, 0.24), "rot": (-60, 0, 30), "elbow": (0.2, 0.3, 0.3)},
    "fist_R": {"at": (-1.3, -1.25, 0.24), "rot": (-60, 0, -30), "elbow": (-0.2, 0.3, 0.3)},
}

def plate_scales(intact, cracked):
    out = {}
    for p in PLATES:
        out["plate_" + p] = intact
        out["plate_%s_crk" % p] = cracked
    return out


def clip_defs():
    """{clip: (frames, pose(frame) -> params)}"""
    g0 = idle_pose(0.0)
    K = RD.Keys
    windup = K([(0, g0), (7, P2(g0, GATHER), "ease"), (19, P2(g0, OVERHEAD), "out"), (27, P2(g0, LOADED), "ease")])
    c0 = charge_pose(0.0)
    attack = K([(0, P2(g0, LOADED)), (5, P2(g0, IMPACT), "in"),
                (8, P2(g0, IMPACT, {"body": {"loc": (0.0, -0.38, -0.24)}}), "out"),
                (16, c0, "ease")])
    hit = K([(0, g0), (3, P2(g0, FLINCH), "out"), (10, g0, "ease")])
    death = K([(0, g0), (5, P2(g0, DEATH_JOLT), "out"), (16, P2(g0, DEATH_KNEEL), "ease"),
               (27, P2(g0, DEATH_DOWN), "in"),
               (31, P2(g0, DEATH_DOWN, {"body": {"loc": (0.0, -0.36, -0.54), "rot": (48.0, 8.0, 6.0)}}), "out"),
               (36, P2(g0, DEATH_DOWN), "in"), (48, P2(g0, DEATH_DOWN, {"head": {"rot": (-14.0, 10.0, 18.0)}}), "ease")])
    brk_hold = P2(g0, ROAR, {"body": {"loc": (0.0, 0.1, 0.06)}})
    brk_keys = K([(0, g0), (4, P2(g0, ROAR), "out"), (14, brk_hold, "ease"), (24, g0, "ease")])

    def plates_break(f):
        p = brk_keys.at(f)
        t = max(0.0, (f - 3) / 17.0)
        p["frag"] = {pl: t for pl in PLATES}
        sc = plate_scales(HIDE, 1.0 if f < 22 else HIDE)
        shrink = 1.0 - max(0.0, min(1.0, (f - 12) / 8.0))
        for pl in PLATES:
            for k in range(PLATE_FRAGS[pl]):
                sc["plate_%s_crk_%d" % (pl, k + 1)] = max(HIDE, shrink)
        p["scale"] = sc
        return p
    return {
        "idle@loop": (60, lambda f: idle_pose(f / 60.0)),
        "move@loop": (MOVE_FRAMES, lambda f: move_pose(f / float(MOVE_FRAMES))),
        "windup": (windup.length, windup.at),
        "attack": (attack.length, attack.at),
        "charge@loop": (CHARGE_FRAMES, lambda f: charge_pose(f / float(CHARGE_FRAMES))),
        "hit": (hit.length, hit.at),
        "death": (death.length, death.at),
        "plates_break": (24, plates_break),
    }


CLIP_ROLES = {
    "idle@loop": "hunched on its knuckles, the chest heaves and lifts the anvil, the visor looks around",
    "move@loop": "knuckle walk: fists and feet planted in diagonal pairs, the torso rolls under the anvil",
    "windup": "the overhead slam wind-up: gathers, rears up on its legs, both fists clasped overhead (3.8 m) "
              "(anticipation; the engine draws the red-white charge telegraph); ends on the loaded pose",
    "attack": "the slam that launches the charge: both fists hammer the ground in front (impact at 0.17 s, sockets "
              "impact_L/R) and it drives forward into the charge posture",
    "charge@loop": "the charge: a head-down bounding gallop behind the anvil (play while the sim's CHARGING flag "
                   "is set)",
    "hit": "a flinch back; the plates rattle with the chest",
    "death": "jolts, sags to its knees and crashes face-down onto its fists under the anvil (held)",
    "plates_break": "the plates shatter (GameEvent::PlatesShattered): it rears up roaring, arms flung wide, and "
                    "the cracked fragments fly off, tumble and vanish; plate_* joints are keyed hidden",
}
CLIP_ALIASES = {"walk@loop": "move@loop", "slam": "attack", "slam_windup": "windup", "plate_shatter": "plates_break"}


def build_clips(arm, mesh):
    sol = Solver(arm)
    names = []
    for clip, (frames, fn) in clip_defs().items():
        RD.bake_clip(arm, KEY, clip, int(frames), lambda a, f, fn=fn: sol.pose(fn(f)), mute_meshes=[mesh])
        names.append(RD.clip_name(KEY, clip))
    return names, sol


# ---- paint (THE UNMADE, ENEMIES.md section 4) --------------------------------------------------------------------
# Value hierarchy at game size: the anvil's polished face is the ONE bright metal; the other plates are mid iron;
# the body is black obsidian whose up-facing planes are lifted to a cool violet-grey (so it separates from the warm
# #3A2C24 Cinder floor) and whose knapped creases carry bright broken strokes; teal only in the eye slit, the maw,
# the ichor welds where iron is fused into flesh, and (cracked) the crack walls.

PALETTE = [  # (name, hex) for the review sheets
    ("obsidian", "#1A1720"), ("obsidian top", "#444053"), ("obsidian edge", "#8A8298"), ("fused flesh", "#26202C"),
    ("flesh sheen", "#6E6282"), ("anvil iron", "#545A66"), ("iron light", "#858D9A"), ("forge scale", "#343842"),
    ("polished face", "#9AA2AD"), ("iron shadow", "#1E2128"), ("ichor", "#1F8F7E"), ("unmade teal", "#2FBFA8"),
    ("mint core", "#B8FFE8"),
]
TEAL = {"color": "#2FBFA8", "core": "#B8FFE8"}
TEAL_DIM = {"color": "#1F8F7E", "core": "#2FBFA8"}


def recipes():
    import gfa_paint as P
    iron = P.zone(base="#545A66", shadow="#1E2128", light="#858D9A", planes=0.1, parts=0.06, brush=0.03,
                  brush_freq=3.0, cavity=0.85, cavity_width=0.012, ao=0.65, ao_range=(0.2, 0.6), edge=0.8,
                  edge_width=0.012, edge_breakup=0.3,
                  gradient={"axis": (0, 0, -1), "range": (-1.6, -0.4), "color": "#2A2D36", "amount": 0.45})
    return {
        "obsidian": P.faction_zone("unmade", "obsidian", light="#8A8298", planes=0.14, parts=0.06, brush=0.05,
                                   brush_freq=3.0, edge=1.0, edge_width=0.014, edge_breakup=0.42, cavity=0.8,
                                   cavity_width=0.012, ao=0.7, ao_range=(0.2, 0.6),
                                   gradient={"axis": (0, 0, -1), "range": (-1.2, -0.1), "color": "shadow",
                                             "amount": 0.4}),
        "flesh": P.faction_zone("unmade", "obsidian_wet", base="#26202C", shadow="#0C0A10", light="#6E6282",
                                planes=0.05, parts=0.05,
                                brush=0.06, brush_freq=3.0, edge=0.3, edge_width=0.01, cavity=0.7, cavity_width=0.012,
                                ao=0.75, ao_range=(0.2, 0.6), stroke=(0.0, 0.0, -1.0), stroke_amount=0.1,
                                stroke_freq=(26.0, 3.0),
                                gradient={"axis": (0, 0, -1), "range": (-1.2, -0.2), "color": "shadow", "amount": 0.35}),
        "iron": iron,
        "iron_crk": dict(iron),
        "crack": P.faction_zone("unmade", "ichor", glow=True,
                                emit={"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8", "mode": "flat",
                                      "base_mix": 0.2}),
        "ichor": P.faction_zone("unmade", "ichor", glow=True,
                                emit={"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8", "mode": "flat",
                                      "base_mix": 0.2}),
    }


def broad_recipes():
    import gfa_brush as B
    b = B.broad(levels=(-0.3, -0.12, 0.04, 0.16), wobble=0.28, wobble_freq=5.0, inner=0.03, stroke=0.85,
                stroke_width=0.013, stroke_len=0.16, stroke_cover=0.55, glint=0.35, glint_color="#B4BBC6",
                edge_min_angle=20.0)
    return {"iron": b, "iron_crk": dict(b)}


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
    # the cracks of every cracked plate: a burnt lip, a teal line, a mint core - on the fragments and their walls
    for lines, fr, gap in CRACK_DECALS:
        w = gap + 0.035
        out.append(P.decal_lines(lines, fr, w, zones=["iron_crk", "crack"], color="#2FBFA8", rim="#0B0D12",
                                 rim_width=w * 2.2, emit=TEAL, depth=(-1.0, 1.0), facing=-1.1))
    # the anvil: hardy (square) and pritchel (round) holes near the heel, painted dark on the polished face
    hardy = [[(-0.44, -0.035), (-0.44, 0.035)]]
    out.append(P.decal_lines(hardy, ANVIL_M, 0.07, zones=["iron", "iron_crk"], color="#15171C", rim=None,
                             depth=(0.05, 0.3), facing=0.6))
    out.append(P.decal_lines([[(-0.3, 0.0), (-0.296, 0.004)]], ANVIL_M, 0.04, zones=["iron", "iron_crk"],
                             color="#15171C", rim=None, depth=(0.05, 0.3), facing=0.6))
    # ichor wounds where the anvil is fused into the hump: short fissures radiating from the weld (they show round
    # the waist while plated, and as a glowing scar once the anvil is gone)
    base_fr = ANVIL_M @ Matrix.Translation((-0.12, 0.0, -0.26))
    for k in range(6):
        ang = 360.0 * k / 6 + 20
        a_ = math.radians(ang)
        start = (0.3 * math.cos(a_), 0.19 * math.sin(a_))
        lines = M.crack_lines(random.Random(80 + k), start=start, direction=ang, length=0.22, step=0.05, jag=0.4,
                              branches=1, branch_len=0.4, depth=1)
        out.append(P.decal_lines(lines, base_fr, 0.03, zones=["obsidian"], color="#2FBFA8", rim="#07060A",
                                 rim_width=0.07, emit=TEAL_DIM, depth=(-0.35, 0.3), facing=0.2))
    # a few bold teal fissures in the obsidian: the chest flanks and the knuckles
    spec = [((0.42, -0.5, 1.55), (0.7, -0.7, 0.1), -80, 0.32, 1), ((-0.4, -0.52, 1.5), (-0.7, -0.7, 0.1), -100, 0.3, 2),
            ((0.25, 0.42, 1.55), (0.3, 0.9, 0.3), 200, 0.3, 3)]
    for o, nrm, ang, L, sd in spec:
        lines = M.crack_lines(random.Random(sd), start=(0.0, 0.0), direction=ang, length=L, step=0.06, jag=0.45,
                              branches=1, branch_len=0.45, depth=1)
        out.append(P.decal_lines(lines, frame_at(o, nrm), 0.026, zones=["obsidian"], color="#2FBFA8", rim="#07060A",
                                 rim_width=0.06, emit=TEAL, depth=(-0.3, 0.3), facing=0.3))
    for side, sx in (("L", 1), ("R", -1)):
        wr, tip = P_("wrist_" + side), P_("hand_%s_tip" % side)
        fc = wr.lerp(tip, 0.58)
        lines = M.crack_lines(random.Random(90 + sx), start=(0.0, 0.05), direction=-90, length=0.2, step=0.05,
                              jag=0.4, branches=1, branch_len=0.5, depth=1)
        out.append(P.decal_lines(lines, frame_at(fc, (sx * 0.3, -1.0, 0.1)), 0.024, zones=["obsidian"],
                                 color="#2FBFA8", rim="#07060A", rim_width=0.055, emit=TEAL, depth=(-0.4, 0.4),
                                 facing=0.3))
    return out


# the top-plane lift and the anvil polish: a painted pass between the zone paint and the decals
LIFT = {"obsidian": ("#444053", 0.8), "flesh": ("#3A3244", 0.6)}
POLISH = {"color": "#737B87", "band": "#9AA2AD", "horn": 0.4}   # the face, its hammer-struck band, the horn top
SCALE = {"color": "#343842", "amount": 0.5, "freq": 4.0, "threshold": (0.56, 0.68)}   # dark forge-scale patches
WOUND = {"base": "#0D3B35", "emit": "#1F8F7E", "core": "#2FBFA8"}                    # raw flesh under the anvil


def lift_pass(base, emis, P_pos, Nt, Z, zones_order):
    import numpy as np
    import gfa_paint as P
    brush = P.spread01(P.fbm(P_pos, 3.0, 2, seed=501))
    for zname, (col, amt) in LIFT.items():
        if zname not in zones_order:
            continue
        m = Z == zones_order.index(zname)
        if not m.any():
            continue
        c = base[m]
        nz = Nt[m, 2] + (brush[m] - 0.5) * 0.3
        k = 0.35 * P.smoothstep(-0.2, 0.1, nz) + 0.65 * P.smoothstep(0.35, 0.6, nz)
        lum = c @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
        k = k * amt * (1.0 - P.smoothstep(0.24, 0.4, lum))           # leave the edge strokes alone
        c = P.mix(c, P.hex3(col), k)
        base[m] = c
    # the anvil's polished face (and the worn top of the horn): the brightest metal on the model
    A = np.array(ANVIL_M.inverted(), dtype=np.float32)
    up = np.array(ANVIL_M.to_3x3() @ Vector((0, 0, 1)), dtype=np.float32)
    for zname in ("iron", "iron_crk"):
        m = Z == zones_order.index(zname)
        q = P_pos[m] @ A[:3, :3].T + A[:3, 3]
        nd = Nt[m] @ up
        face = (q[:, 0] > -0.66) & (q[:, 0] < 0.37) & (np.abs(q[:, 1]) < 0.25) & (q[:, 2] > 0.08) & (q[:, 2] < 0.2)
        k = face * P.smoothstep(0.75, 0.92, nd)
        horn = (q[:, 0] > 0.3) & (q[:, 0] < 1.25) & (np.abs(q[:, 1]) < 0.16) & (q[:, 2] > -0.05) & (q[:, 2] < 0.35)
        k = np.maximum(k, horn * P.smoothstep(0.35, 0.75, nd) * POLISH["horn"])
        k = k * (0.85 + 0.15 * brush[m])
        # the striking band down the middle of the face: a lighter painted plane with a brushy border
        wob = (P.spread01(P.fbm(P_pos[m], 9.0, 2, seed=612)) - 0.5) * 0.05
        band = (1.0 - P.smoothstep(0.1, 0.14, np.abs(q[:, 1]) + wob)) *             (1.0 - P.smoothstep(0.24, 0.32, q[:, 0] + wob)) * P.smoothstep(-0.56, -0.48, q[:, 0] - wob)
        band = band * face * P.smoothstep(0.75, 0.92, nd)
        # dark forge scale in patches everywhere but the polished face
        sc = P.smoothstep(SCALE["threshold"][0], SCALE["threshold"][1], P.fbm(P_pos[m], SCALE["freq"], 3, seed=611))
        base[m] = P.mix(base[m], P.hex3(SCALE["color"]), sc * SCALE["amount"] * (1.0 - k))
        base[m] = P.mix(base[m], P.hex3(POLISH["color"]), k)
        base[m] = P.mix(base[m], P.hex3(POLISH["band"]), band * 0.9)
    # the raw wound under the anvil's waist: hidden while plated, a glowing ichor bed once the anvil is gone
    m = Z == zones_order.index("obsidian")
    q = P_pos[m] @ A[:3, :3].T + A[:3, 3]
    r = np.sqrt(((q[:, 0] + 0.12) / 0.34) ** 2 + (q[:, 1] / 0.22) ** 2)
    wz = P.smoothstep(-0.55, -0.45, q[:, 2]) * (1.0 - P.smoothstep(-0.2, -0.12, q[:, 2]))
    facing = P.smoothstep(0.35, 0.6, Nt[m] @ up)          # only the flesh the anvil's waist actually covers
    k = (1.0 - P.smoothstep(0.72, 0.98, r + (brush[m] - 0.5) * 0.25)) * wz * facing
    base[m] = P.mix(base[m], P.hex3(WOUND["base"]), k * 0.9)
    glow = P.mix(np.repeat(P.hex3(WOUND["emit"])[None], int(m.sum()), 0), P.hex3(WOUND["core"]),
                 1.0 - P.smoothstep(0.2, 0.8, r))
    emis[m] = np.maximum(emis[m], glow * (k * 0.8)[:, None])
    return base, emis


def paint_mesh(mesh, tex_dir, size=1024):
    import gfa_brush as B
    orig = B.apply_decals

    def with_lift(base, emis, P_pos, Nt, Z, zones_order, decals_):
        base, emis = lift_pass(base, emis, P_pos, Nt, Z, zones_order)
        return orig(base, emis, P_pos, Nt, Z, zones_order, decals_)
    B.apply_decals = with_lift
    try:
        return B.paint_asset(mesh, KEY, recipes(), tex_dir, size=size, decals=decals(), broad=broad_recipes(),
                             ao_distance=0.14, ao_samples=24, edge_min_angle=34.0, margin_px=3, seed=11, uv_angle=66.0,
                             uv_small_islands=(0.0015, 0.5))
    finally:
        B.apply_decals = orig


def state_copy(mesh, state):
    """A copy of the painted mesh showing one plate state (faces of the other states deleted)."""
    ob = mesh.copy()
    ob.data = mesh.data.copy()
    ob.name = "%s_%s" % (mesh.name, state)
    ob.hide_render = False
    for c in mesh.users_collection:
        c.objects.link(ob)
    mesh_state_preview(ob, state)
    return ob


CLOSE_VIEWS = {  # name: (target, direction, ortho scale) - close checks of the plates (--look --close)
    "anvil": ((0.25, 0.05, 2.35), (0.0, -0.57, 0.82), 1.9),
    "head": ((0.0, -0.75, 1.72), (0.35, -1.0, 0.35), 0.9),
    "cuff": ((0.98, -0.52, 0.95), (0.6, -1.0, 0.45), 1.0),
    "pauldron": ((-0.8, -0.2, 1.95), (-0.6, -1.0, 0.6), 1.0),
}


def look(mesh, out_dir, close=False):
    """--look: the three plate states as the 3/4 beauty view and through the game camera at TRUE pixel size."""
    import gfa_render as R
    import gfa_spec as SPEC
    scene = bpy.context.scene
    d55 = Vector((0.0, -math.cos(math.radians(SPEC.GAME_PITCH_DEG)), math.sin(math.radians(SPEC.GAME_PITCH_DEG))))
    mesh.hide_render = True
    out = []
    for st in ("intact", "cracked", "stripped"):
        ob = state_copy(mesh, st)
        R.setup_cycles(scene, 12)
        with R.toon_preview([ob], ink=0.012):
            R.aim(scene, Vector((0.1, -0.1, 1.45)), Vector((0.62, -1.0, 0.36)).normalized(), 3.6)
            out.append(R.render(scene, os.path.join(out_dir, "look_34_%s.png" % st), 560))
            R.aim(scene, Vector((0.1, -0.1, 1.5)), d55, 3.4)
            out.append(R.render(scene, os.path.join(out_dir, "look_top55_%s.png" % st), 560))
            if close and st != "stripped":
                for nm, (tg, dr, sc) in CLOSE_VIEWS.items():
                    R.aim(scene, Vector(tg), Vector(dr).normalized(), sc)
                    out.append(R.render(scene, os.path.join(out_dir, "close_%s_%s.png" % (nm, st)), 420))
        man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
        man.location = (-2.3, 0.4, 0.0)
        bpy.context.view_layer.update()
        r = R.ingame([ob], out_dir, "look_%s" % st, px=220, mannequin_obj=man, target=(-0.7, -0.1, 1.0))
        out.append(r["color"])
        C.remove_objects([man, ob] + [o for o in (bpy.data.objects.get("GFA_FLOOR"),) if o])
    mesh.hide_render = False
    return out


# ---- review renders ------------------------------------------------------------------------------------------------

def apply_state(arm, state):
    """What the engine does after its animation system: scale the plate joints for one plate state."""
    vis = {"intact": (1.0, HIDE), "cracked": (HIDE, 1.0), "stripped": (HIDE, HIDE), "both": (1.0, 1.0)}[state]
    for p in PLATES:
        arm.pose.bones["plate_" + p].scale = (vis[0],) * 3
        arm.pose.bones["plate_%s_crk" % p].scale = (vis[1],) * 3
    bpy.context.view_layer.update()


def show(arm, clip, frame, state):
    import gfa_rig as RIG
    if clip is None:
        RIG.unmute_none(arm)
        bpy.context.scene.frame_set(0)
    else:
        RIG.pose_at(arm, RD.clip_name(KEY, clip), frame)
    apply_state(arm, state)


KEY_FRAMES = {   # the key poses of each clip for the clip contact sheet
    "idle@loop": (0, 15, 30, 45), "move@loop": (0, 4, 8, 12, 16, 20), "windup": (0, 7, 13, 19, 27),
    "attack": (0, 3, 5, 8, 12, 16), "charge@loop": (0, 3, 6, 9), "hit": (0, 3, 10),
    "death": (0, 5, 16, 22, 27, 36, 48), "plates_break": (0, 4, 8, 12, 16, 24),
}
CLIP_STATE = {"plates_break": "cracked"}   # the plate state each clip is shown in (default intact)
GAME_POSES = [("idle@loop", 0, "idle"), ("windup", 27, "windup (loaded)"), ("attack", 5, "slam impact"),
              ("charge@loop", 3, "charge"), ("death", 48, "death (held)")]


def clip_sheet(arm, mesh, reports, work, clips_rep):
    """Contact sheet: every clip's key poses (textured toon preview, 3/4 front, one shared scale)."""
    import gfa_render as R
    scene = bpy.context.scene
    R.setup_cycles(scene, 10)
    view = Vector((0.75, -1.0, 0.45)).normalized()
    sections = []
    with R.toon_preview([mesh], ink=0.012):
        for clip, frames in KEY_FRAMES.items():
            tr = RD.clip_name(KEY, clip)
            ims = []
            for f in frames:
                show(arm, clip, f, CLIP_STATE.get(clip, "intact"))
                R.aim(scene, Vector((0.05, -0.35, 1.45)), view, 4.6)
                p = R.render(scene, os.path.join(work, "clip_%s_%02d.png" % (clip.replace("@", "_"), f)), 240)
                ims.append({"path": p, "label": "f%d" % f})
            secs = next((c["seconds"] for c in clips_rep if c["name"] == tr), 0)
            sections.append({"label": "%s  (%.2f s)  -  %s" % (tr, secs, CLIP_ROLES[clip]), "height": 190,
                             "images": ims})
    show(arm, None, 0, "both")
    layout = {"title": "Anvil Brute - clips (key poses)",
              "subtitle": "GF_AnvilBrute_v1, 30 fps, every frame keyed; loops are periodic. Plates shown intact "
                          "(plates_break: cracked, as the engine plays it). The engine draws the red-white telegraph.",
              "width": 1600, "sections": sections,
              "notes": ["Brief names map to the contract names through meta.json clip_aliases: walk@loop -> move@loop, "
                        "slam_windup -> windup, slam -> attack, plate_shatter -> plates_break."]}
    return R.contact_sheet(layout, os.path.join(reports, "%s_clips.png" % KEY), work)


def _floor(scene):
    import gfa_render as R
    fl = bpy.data.meshes.new("GFLOOR")
    fl.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("GFLOOR", fl)
    scene.collection.objects.link(fo)
    fl.materials.append(R.toon_material("GFLOORM", flat_hex=R.FLOOR, rim=0.0))
    return fo


def size_lineup(arm, mesh, work):
    """Front orthographic lineup: the 2.2 m hero mannequin next to the brute (rest and windup), height bars."""
    import gfa_render as R
    import gfa_spec as SPEC
    scene = bpy.context.scene
    show(arm, None, 0, "intact")
    _lo, hi = C.world_bounds([mesh])
    man = R.mannequin(aim_dir=(0.0, -1.0, 0.0))
    man.location = (-2.2, 0.0, 0.0)
    bars = []
    for h, x0, x1, hexc in ((SPEC.HERO_HEIGHT, -2.8, -1.6, "#7A8494"), (hi.z, -1.3, 1.6, "#2FBFA8")):
        me = bpy.data.meshes.new("BAR")
        me.from_pydata([(x0, 0.9, h - 0.01), (x1, 0.9, h - 0.01), (x1, 0.9, h + 0.01), (x0, 0.9, h + 0.01)], [],
                       [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("BAR", me)
        scene.collection.objects.link(ob)
        me.materials.append(R.toon_material("BARM", flat_hex=hexc, rim=0.0))
        bars.append(ob)
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 10)
    flat = {man.name: R.MANNEQUIN}
    paths = []
    with R.toon_preview([mesh, man], ink=0.012, flat=flat):
        for nm, clip, f in (("rest", None, 0), ("windup", "windup", 27)):
            show(arm, clip, f, "intact")
            R.aim(scene, Vector((-0.6, 0.0, 1.75)), Vector((0.0, -1.0, 0.0)), 4.6)
            paths.append(R.render(scene, os.path.join(work, "%s_size_%s.png" % (KEY, nm)), 620, 720))
    show(arm, None, 0, "both")
    C.remove_objects([man] + bars)
    return paths, round(hi.z, 3)


def game_strip(arm, mesh, work, poses=GAME_POSES, state="intact", stem="game", px=240, sil=True):
    """The in-game camera at TRUE 1080p pixel size (view height 22 m) with the mannequin."""
    import gfa_render as R
    import gfa_spec as SPEC
    scene = bpy.context.scene
    vh = SPEC.GAME_VIEW_HEIGHTS[0]
    ppm = SPEC.SCREEN_H / vh
    d = Vector((0.0, -math.cos(math.radians(SPEC.GAME_PITCH_DEG)), math.sin(math.radians(SPEC.GAME_PITCH_DEG))))
    man = R.mannequin(aim_dir=(-0.5, -0.8, 0.0))
    man.location = (-2.3, 0.4, 0.0)
    fo = _floor(scene)
    bpy.context.view_layer.update()
    R.setup_cycles(scene, 16, bg=R.FLOOR)
    out = []
    tgt = Vector((-0.6, -0.2, 1.0))
    with R.toon_preview([mesh, man], ink=0.012, flat={man.name: R.MANNEQUIN}):
        for clip, f, label in poses:
            st = state if isinstance(state, str) else state[len(out)]
            show(arm, clip, f, st)
            R.aim(scene, tgt, d, px / ppm)
            out.append((R.render(scene, os.path.join(work, "%s_%s_%s_%02d.png" % (stem, st, (clip or "rest").replace("@", "_"), f)),
                                 px), label))
    silp = None
    if sil:
        show(arm, poses[0][0], poses[0][1], state if isinstance(state, str) else state[0])
        R.setup_workbench_flat(scene)
        fo.hide_render = True
        R.aim(scene, tgt, d, px / ppm)
        silp = R.render(scene, os.path.join(work, "%s_sil.png" % stem), px)
    show(arm, None, 0, "both")
    C.remove_objects([man, fo])
    return out, silp


def hero_shot(arm, mesh, reports, state="intact", name=None, size=900):
    import gfa_render as R
    scene = bpy.context.scene
    show(arm, None, 0, state)
    R.setup_cycles(scene, 16)
    with R.toon_preview([mesh], ink=0.011):
        R.aim(scene, Vector((0.12, -0.2, 1.42)), Vector((0.62, -1.0, 0.36)).normalized(), 3.5)
        p = R.render(scene, os.path.join(reports, name or "%s_34.png" % KEY), size)
    show(arm, None, 0, "both")
    return p


def plates_sheet(arm, mesh, reports, work):
    """The gimmick: the three plate states (3/4 view, the game camera at 1x and 3x), the shatter clip, the switch."""
    import gfa_render as R
    scene = bpy.context.scene
    views = []
    for st in ("intact", "cracked", "stripped"):
        views.append((hero_shot(arm, mesh, work, st, "plates_34_%s.png" % st, size=420), st))
    game, _ = game_strip(arm, mesh, work, poses=[(None, 0, "intact"), (None, 0, "cracked"), (None, 0, "stripped")],
                         state=["intact", "cracked", "stripped"], stem="plates_game", px=200, sil=False)
    fb = hero_shot(arm, mesh, work, "both", "plates_34_both.png", size=420)
    R.setup_cycles(scene, 10)
    brk = []
    view = Vector((0.75, -1.0, 0.45)).normalized()
    with R.toon_preview([mesh], ink=0.012):
        for f in (0, 4, 7, 10, 13, 16, 20, 24):
            show(arm, "plates_break", f, "cracked")
            R.aim(scene, Vector((0.05, -0.2, 1.6)), view, 5.0)
            brk.append({"path": R.render(scene, os.path.join(work, "plates_break_%02d.png" % f), 200),
                        "label": "plates_break f%d" % f})
    show(arm, None, 0, "both")
    layout = {
        "title": "Anvil Brute - the plates (the one gimmick)",
        "subtitle": "Every plate is in the mesh twice - intact (plate_<p>) and cracked (plate_<p>_crk + fragments); "
                    "the engine picks the state by joint scale after animation.",
        "width": 1600,
        "sections": [
            {"label": "3/4 view: intact | cracked (teal crack walls) | stripped (ichor wound) | fallback (both on)",
             "height": 360, "images": [{"path": p, "label": s} for p, s in views] + [{"path": fb, "label": "fallback"}]},
            {"label": "The game camera at TRUE pixel size (55 deg, 49.1 px/m, 2.2 m mannequin): 1x, then 3x",
             "height": None, "images": [{"path": p, "label": lb + " 1x"} for p, lb in game]
             + [{"path": p, "label": lb + " 3x", "scale": 3} for p, lb in game]},
            {"label": "plates_break (on PlatesShattered): it rears up roaring, the fragments fly off and shrink away",
             "height": 190, "images": brk},
        ],
        "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
        "notes": [
            "Joint scales after animation: intact = plate_<p> 1, plate_<p>_crk 0 | cracked = 0 / 1 | stripped = 0 / 0.",
            "Plates: %s. Crack them one by one from a client plate-wear estimate while PLATED;" % ", ".join(PLATES),
            "on GameEvent::PlatesShattered play plates_break, then hold stripped (README: Plate states).",
        ],
    }
    return R.contact_sheet(layout, os.path.join(reports, "%s_plates.png" % KEY), work)


def pose_renders(arm, mesh, out_dir, frames, size=220, view=(0.75, -1.0, 0.45), scale=4.8, target=(0.05, -0.3, 1.5)):
    """Flat toon renders of clip frames (the caller set the materials): the --poses check."""
    import gfa_render as R
    scene = bpy.context.scene
    R.setup_cycles(scene, 8)
    hull = R.add_ink_hull(mesh, 0.012)
    out = []
    for clip, fl in frames.items():
        for f in fl:
            show(arm, clip, f, CLIP_STATE.get(clip, "intact"))
            R.aim(scene, Vector(target), Vector(view).normalized(), scale)
            path = os.path.join(out_dir, "pose_%s_%02d.png" % (clip.replace("@", "_"), f))
            out.append((clip, f, R.render(scene, path, size)))
    show(arm, None, 0, "both")
    C.remove_objects([hull])
    return out


# ---- plate states (review; the engine does the same with joint scales after animation) ---------------------------

HIDE = 0.001


def mesh_state_preview(mesh, state):
    """Without a rig: hide the faces of the other state (review of the geometry only). Returns the removed count."""
    if state == "both":
        return 0
    names = mesh["gfa_part_names"].split(",")
    import numpy as np
    me = mesh.data
    lay = me.attributes.get("gfa_part")
    pid = np.empty(len(me.polygons), dtype=np.int64)
    lay.data.foreach_get("value", pid)
    drop = set()
    for i, nm in enumerate(names):
        intact = nm.startswith("plate_") and not nm.endswith("_crk")
        cracked = nm.endswith("_crk")
        if (state == "intact" and cracked) or (state == "cracked" and intact) or (state == "stripped" and (intact or cracked)):
            drop.add(i)
    bm = bmesh.new()
    bm.from_mesh(me)
    layer = bm.faces.layers.int.get("gfa_part")
    kill = [f for f in bm.faces if f[layer] in drop]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(me)
    bm.free()
    me.update()
    return len(kill)


def preview_materials(mesh):
    import gfa_render as R
    for s in mesh.material_slots:
        z = s.material.name[4:]
        m = R.toon_material("PV_" + z, flat_hex=PREVIEW.get(z, "#FF00FF"), rim=0.3)
        if z in ("crack", "ichor"):
            nt = m.node_tree
            em = [n for n in nt.nodes if n.type == "EMISSION"][0]
            em.inputs["Strength"].default_value = 3.0
        s.material = m


def preview(mesh, out_dir, stem="pv", size=420):
    import gfa_render as R
    scene = bpy.context.scene
    views = dict(R.CREATURE_VIEWS)
    views["game55"] = (0.0, -math.cos(math.radians(55)), math.sin(math.radians(55)))
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
    man.location = (-2.3, 0.4, 0.0)
    man.data.materials.clear()
    man.data.materials.append(R.toon_material("PV_man", flat_hex=R.MANNEQUIN, rim=0.25))
    bpy.context.view_layer.update()
    mh = R.add_ink_hull(man, 0.012)
    ppm = 1080 / 22.0
    d = Vector((0.0, -math.cos(math.radians(55)), math.sin(math.radians(55))))
    fl = bpy.data.meshes.new("PVFLOOR")
    fl.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    flo = bpy.data.objects.new("PVFLOOR", fl)
    scene.collection.objects.link(flo)
    fl.materials.append(R.toon_material("PV_floor", flat_hex=R.FLOOR, rim=0.0))
    R.setup_cycles(scene, 8, bg=R.FLOOR)
    px = 220
    R.aim(scene, Vector((-0.8, 0, 1.0)), d, px / ppm)
    paths.append(R.render(scene, os.path.join(out_dir, "%s_ingame.png" % stem), px))
    C.remove_objects([man, mh, flo, hull])
    return paths


POSE_FRAMES = {
    "idle@loop": (0, 30), "move@loop": (0, 6, 12, 18), "windup": (0, 7, 19, 27), "attack": (0, 5, 8, 16),
    "charge@loop": (0, 3, 6, 9), "hit": (3,), "death": (16, 27, 48), "plates_break": (4, 10, 16),
}


def plate_switch_meta():
    """meta.json: how the engine shows the plate states (README "Plate states")."""
    return {
        "plates": {p: {"parent": PLATE_PARENT[p], "intact_joint": "plate_" + p, "cracked_joint": "plate_%s_crk" % p,
                       "fragments": ["plate_%s_crk_%d" % (p, k + 1) for k in range(PLATE_FRAGS[p])]} for p in PLATES},
        "states": {"intact": "plate_<p> scale 1, plate_<p>_crk scale 0", "cracked": "plate_<p> 0, plate_<p>_crk 1",
                   "stripped": "both 0"},
        "rule": "Set these joint scales every frame AFTER the animation system and before transform propagation: "
                "every clip keys the plate joints (at scale 1, plates_break at the cracked state), so the client's "
                "state wins. 0 may be 0.001 (the clips use 0.001). Keep a plate cracked while plates_break plays.",
        "sim_signals": "EntityFlags::PLATED while plate_hp is left; GameEvent::PlatesShattered when it runs out; "
                       "GameEvent::Hit per hit (amount after resist, element) for a client-side plate-wear estimate.",
        "suggested": "spawn intact; while PLATED, estimate wear = sum of Hit amounts x 1.5 for Kinetic (resisted) "
                     "and x 0.5 for other elements (gf_core::damage::apply_plating), and crack plates in crack_order "
                     "as wear / plate_hp passes crack_at; on PlatesShattered set every plate cracked, play "
                     "plates_break once (it flings the fragments), then hold stripped; a brute without PLATED is "
                     "stripped",
        "fallback": "with no client support both layers stay at scale 1: the intact plates hide the cracked copies "
                    "(inset 3-7 %), so the model reads intact",
        "crack_at": [0.15, 0.35, 0.55, 0.7, 0.85],
        "crack_order": ["back", "pauldron", "helm", "cuff_L", "cuff_R"],
    }


def main():
    argv = C.script_args()
    pack = C.pack_dir(KIND, KEY)
    work = C.ensure_dir(os.path.join(pack, "work", "preview"))
    if C.flag(argv, "--preview"):
        state = C.opt(argv, "--state", "intact")
        for st in (("intact", "cracked", "stripped") if state == "all" else (state,)):
            C.reset_scene(fps=30)
            mesh, _parts = build_mesh(C.get_collection(KEY))
            mesh_state_preview(mesh, st)
            preview_materials(mesh)
            preview(mesh, work, stem="pv_" + st)
        C.log("DONE preview")
        return
    C.reset_scene(fps=30)
    col = C.get_collection(KEY)
    mesh, _parts = build_mesh(col)
    if C.flag(argv, "--look"):
        tex_dir = C.ensure_dir(os.path.join(pack, "work", "look"))
        paint_mesh(mesh, tex_dir, C.opt(argv, "--size", 1024, int))
        look(mesh, tex_dir, close=C.flag(argv, "--close"))
        C.log("DONE look")
        return
    arm = build_rig(col)
    C.log("skin", RD.skin_rigid(mesh, arm)["per_bone"])
    socks = add_sockets(arm)
    clips, _solver = build_clips(arm, mesh)
    C.log("clips", clips)
    if C.flag(argv, "--poses"):
        preview_materials(mesh)
        only = C.opt(argv, "--clip", None)
        fr = {k: v for k, v in POSE_FRAMES.items() if only is None or k.startswith(only)}
        if C.flag(argv, "--game"):
            pose_renders(arm, mesh, work, fr, size=C.opt(argv, "--size", 220, int),
                         view=(0.0, -math.cos(math.radians(55)), math.sin(math.radians(55))))
        else:
            pose_renders(arm, mesh, work, fr, size=C.opt(argv, "--size", 220, int))
        C.log("DONE poses")
        return
    import gfa_export as E
    import gfa_render as R
    import gfa_rig as RIG
    import gfa_spec as SPEC
    size = C.opt(argv, "--size", 1024, int)
    tex_dir = os.path.join(pack, "textures")
    RIG.unmute_none(arm)
    bpy.context.view_layer.update()
    paint_rep = paint_mesh(mesh, tex_dir, size)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    clips_rep = RIG.clips_report(arm)
    lo, hi = C.world_bounds([mesh])
    extra = {
        "faction": "unmade",
        "rig": {"armature": RIG_NAME, "bones": len(arm.data.bones),
                "core": "GF_Hero_v1 core names and parents (23 bones, docs/ART_PIPELINE.md section 5)",
                "extra_bones": plate_bones(),
                "skinning": "rigid: every part on one bone",
                "rest_pose": "the idle stance (hunched, knuckles planted)",
                "axes": "bone +Y along the bone, +Z toward the front (Ashen Covenant roll convention)"},
        "plate_states": plate_switch_meta(),
        "clip_roles": {RD.clip_name(KEY, c): txt for c, txt in CLIP_ROLES.items()},
        "clip_aliases": {a: RD.clip_name(KEY, b) for a, b in CLIP_ALIASES.items()},
        "clip_seconds": {c["name"]: c["seconds"] for c in clips_rep},
        "clip_playback": {
            "windup": "time-stretch to the Charger windup (0.9 s), hold the last frame",
            "attack": "play when CHARGING starts (0.55 s = the charge duration: the slam launches the charge)",
            "charge@loop": "loop while CHARGING after attack ends (visual cadence, 1.0-1.5x; not stride matched)",
            "plates_break": "one-shot on GameEvent::PlatesShattered, layered or played as a reaction; then stripped",
        },
        "move_cycle_m": round(MOVE_CYCLE_M, 3),
        "sockets_detail": socks,
        "footprint": {"collider_radius_m": round(0.9 * 1.3, 3), "row": "radius 0.9 x scale 1.3",
                      "model_span_m": [round(hi.x - lo.x, 3), round(hi.y - lo.y, 3)]},
        "content_row": {"class": "Elite", "biome": "cinder_wastes", "plating": "(resist: {Kinetic: 0.5}, plate_hp: 260.0)",
                        "behavior": "Charger(range: 9.0, windup: 0.9, speed: 13.0, duration: 0.55, cooldown: 3.5, "
                                    "damage: 34.0, width: 1.4)", "color": "#7A7F8C", "shape": "Brute", "scale": 1.3},
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
            "Sockets: %s. Faces glTF +Z; the engine turns it with yaw(angle) * rot_y(PI)." % ", ".join(sorted(socks)),
            "Turnaround and strips show BOTH plate layers (no client switch); the intact plates hide the cracked.",
            "Status: %s (the user gives the final visual approval)." % SPEC.STATUS_AI_FINAL,
        ]
        review_paths.update(R.review_enemy(
            KEY, arm, mesh, reports, rwork, "Anvil Brute  (anvil_brute)",
            "Elite | The Unmade | Cinder Wastes | plated Charger | gimmick: anvil-iron plates that crack and fall "
            "away | verb: the overhead slam",
            clips=clips, swatches=PALETTE, notes=notes, textures=textures, strip_frames=4))
        review_paths["clips"] = clip_sheet(arm, mesh, reports, rwork, clips_rep)
        review_paths["plates"] = plates_sheet(arm, mesh, reports, rwork)
        lineup, top = size_lineup(arm, mesh, rwork)
        game, sil = game_strip(arm, mesh, rwork)
        review_paths["hero_shot"] = hero_shot(arm, mesh, reports)
        layout = {
            "title": "Anvil Brute - scale and game read",
            "subtitle": "front orthographic lineup with the 2.2 m hero mannequin (grey bar 2.2 m, teal bar %.2f m), rest "
                        "and windup; below, the in-game camera (55 deg, view height 22 m = 1080 px, 49.1 px/m) at TRUE "
                        "pixel size" % top,
            "width": 1600,
            "sections": [
                {"label": "Size comparison (front, orthographic): rest and the loaded windup; 3/4 view of the rest pose",
                 "height": 520,
                 "images": [{"path": lineup[0], "label": "hero 2.2 m | anvil_brute %.2f m (%.2f x)" % (top, top / 2.2)},
                            {"path": lineup[1], "label": "windup (loaded): the fists reach 3.8 m"},
                            {"path": review_paths["hero_shot"], "label": "3/4 view, rest (plates intact)"}]},
                {"label": "In-game camera, 1x true size: idle, windup, slam, charge, death", "height": None,
                 "images": [{"path": pth, "label": lb} for pth, lb in game]},
                {"label": "The same at 3x (nearest) + the idle silhouette at game size (3x)", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[:3]]
                 + [{"path": sil, "label": "silhouette 3x", "scale": 3}]},
                {"label": "", "height": None,
                 "images": [{"path": pth, "label": lb + " 3x", "scale": 3} for pth, lb in game[3:]]},
            ],
            "swatches": [{"hex": h_, "label": n} for n, h_ in PALETTE],
            "notes": ["The anvil (face, horn and heel) is the outline in every pose; the windup lifts the fists above it, "
                      "the charge drops the head behind it."],
        }
        review_paths["scale"] = R.contact_sheet(layout, os.path.join(reports, "%s_scale.png" % KEY), rwork)
    C.write_json(os.path.join(reports, "build_report.json"),
                 {"export": dict({k: v for k, v in rep.items() if k not in ("nodes",)}, file=C.rel(rep["file"])),
                  "paint": paint_rep, "clips": clips_rep,
                  "review": {k: C.rel(v) for k, v in review_paths.items() if isinstance(v, str)}})
    outputs = [C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
               C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")),
               C.rel(os.path.join(tex_dir, KEY + "_emissive.png"))]
    outputs += [C.rel(os.path.join(reports, "%s_%s.png" % (KEY, n))) for n in ("review", "clips", "plates", "scale", "34")]
    C.write_pack_status(KIND, KEY, outputs,
                        "Built from code by tools/blender/gf_assets/enemies/anvil_brute.py (model with intact + cracked "
                        "plates, NPR paint, GF_AnvilBrute_v1 rig, 8 clips, export + validation, review sheets).",
                        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
