"""Sunspike Shotgun - the gf_assets proof weapon, built end to end from code (copy this file to start a
new weapon: tools/blender/gf_assets/README.md "New weapon in 8 steps").

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/weapons/sunspike_shotgun.py -- [--size 1024] [--no-review]

Content row (content/sheets/chassis.csv): sunspike_shotgun, Radiant, style Pellet, 7 pellets, 22 deg
spread, range 8, fire rate 1.6, tags "spread; close" - "A fistful of sunlight at arm's length."

Design (docs/art/WEAPONS.md section 5, family SPREAD):
  * silhouette verb FAN-OUT: a short, heavy two-handed blunderbuss whose bell muzzle flares into a crown
    of ten sun-rays (alternating long / short, raked forward 32 deg). The crown is the one shape that
    must survive at 50 px: wide + spiky at the front = spread;
  * value rhythm, dark to light toward the muzzle: dark wood stock -> bronze receiver -> dark iron barrel
    -> gold crown with white-hot ray tips and a white-gold glowing bore;
  * radiant language: a sun core set in a gold ring on both receiver sides (glow_core socket), a
    glowing channel along the top rib, a carved sunburst on the stock, sun-shells on the stock side;
  * palette: warm metals of the player's arsenal + the Radiant element gold (#FFE27A, palette.rs).

Grip frame (docs/art/WEAPONS.md section 2): origin = palm centre of the right hand on the pistol grip,
+Y = barrel, +Z = up, +X = the weapon's right. Bore axis 0.13 m above the palm; overall 1.07 m.
Outputs: assets/models/weapons/sunspike_shotgun.glb (+ .meta.json), art/weapons/sunspike_shotgun/
{source/*.blend, textures/*.png, reports/*.png, status.json}.
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402

KEY, KIND, TIER = "sunspike_shotgun", "weapon", "two_handed"
AX = 0.14                      # bore axis height above the palm centre (m)
MUZZLE_Y = 0.592               # front of the bell lip (the muzzle socket)
RAY_BASE_Y, RAY_R0 = 0.570, 0.122
RAY_RAKE = 30.0                # degrees the crown's rays lean forward
GRIP_L = (0.0, 0.31, 0.012)    # palm centre of the left hand under the pump
CORE = (0.0, 0.06, AX)         # the receiver's sun core

ZONES = ["iron", "bronze", "gold", "sunray", "wood", "leather", "shell", "glow_bell", "glow_core", "glow_line"]
PALETTE = [  # (name, hex) for the review sheet
    ("wood", "#5E3625"), ("iron", "#3B3340"), ("bronze", "#B87A35"), ("gold", "#E4B24A"),
    ("shell", "#E6D8B8"), ("leather", "#4A2622"), ("glow rim", "#FFB43C"), ("radiant", "#FFE27A"), ("core", "#FFFCEE"),
]


# ---- geometry ---------------------------------------------------------------------------------------------

def build_mesh(col):
    a = M.Assembly(KEY + "_mesh", ZONES)

    # pistol grip (wood, raked back) + bronze pommel cap
    g = M.box((0.056, 0.08, 0.17), bevel=0.013, segments=2, taper=(1.08, 1.12))
    M.xform(g, loc=(0, -0.01, -0.01), rot=(-16, 0, 0))
    a.add(g, "wood", name="grip")
    cap = M.box((0.064, 0.094, 0.028), bevel=0.009, taper=(0.9, 0.9))
    M.xform(cap, loc=(0, -0.036, -0.098), rot=(-16, 0, 0))
    a.add(cap, "bronze", name="pommel")

    # receiver: a chunky bronze block, tapered top (z 0.065 .. 0.215, y -0.07 .. 0.18)
    rec = M.box((0.10, 0.25, 0.15), bevel=0.016, segments=2, taper=(0.86, 0.97))
    M.xform(rec, loc=(0, 0.055, AX))
    a.add(rec, "bronze", name="receiver")
    # sun core on both sides: a glowing disc in a proud gold ring, eight small rays on the side plate
    core = M.cylinder(0.047, 0.106, sides=16, axis="X")
    M.xform(core, loc=CORE)
    a.add(core, "glow_core", name="core_disc")
    ring = M.ring(0.045, 0.066, 0.116, sides=16, bevel=0.005, axis="X")
    M.xform(ring, loc=CORE)
    a.add(ring, "gold", name="core_ring")
    for sx in (-1, 1):
        for i in range(8):
            ang = math.radians(22.5 + 45 * i)
            L = 0.036 if i % 2 == 0 else 0.02
            d = Vector((0, math.cos(ang), math.sin(ang)))
            sp = M.spike(0.013, L, sides=4, base_scale=(1.0, 0.35), rot_offset=0)
            # wide side along the plate (tangent), thin across it (X)
            M.xform(sp, matrix=M.orient(Vector(CORE) + Vector((sx * 0.047, 0, 0)) + d * 0.058, d,
                                        (0, -math.sin(ang), math.cos(ang))))
            a.add(sp, "gold", name="core_ray")
    # rivets on the side plates (the side leans in toward the tapered top: follow it)
    for sx in (-1, 1):
        pts = [(sx * (0.0505 - (z - 0.065) / 0.15 * 0.007), y, z) for y in (-0.052, 0.162) for z in (0.088, 0.192)]
        a.add(M.studs(pts, [(sx, 0, 0)] * 4, 0.0085, 0.007), "gold", name="rivets", shading="smooth")
    # hammer crest at the back of the receiver: a small half sun
    for i in range(5):
        ang = math.radians(-60 + 30 * i)
        d = Vector((0, -math.sin(ang) * 0.35 - 0.5, math.cos(ang))).normalized()
        sp = M.spike(0.014, 0.042 if i % 2 == 0 else 0.03, sides=4, base_scale=(1.0, 0.45), rot_offset=0)
        M.xform(sp, matrix=M.orient((0, -0.065, AX + 0.064), d, (1, 0, 0)))
        a.add(sp, "gold", name="crest")

    # top rib (flush with the receiver top) carrying the radiant channel
    rib = M.box((0.03, 0.30, 0.03), bevel=0.006)
    M.xform(rib, loc=(0, 0.32, AX + 0.06))
    a.add(rib, "bronze", name="rib")
    ch = M.ribbon([[(0.0, -0.055), (0.0, 0.455)]], width=0.013, height=0.006)
    M.xform(ch, loc=(0, 0, AX + 0.074))
    a.add(ch, "glow_line", name="channel", shading="flat")

    # barrel (dark iron) with two gold bands
    bar = M.cylinder(0.045, 0.30, sides=12, axis="Y")
    M.xform(bar, loc=(0, 0.31, AX))
    a.add(bar, "iron", name="barrel", shading="smooth")
    for y in (0.2, 0.43):
        b = M.ring(0.043, 0.058, 0.028, sides=16, bevel=0.005, axis="Y")
        M.xform(b, loc=(0, y, AX))
        a.add(b, "gold", name="band")

    # pump / foregrip (wood) with iron grip ribs
    pump = M.box((0.092, 0.17, 0.072), bevel=0.015, segments=2, taper=(0.92, 1.0))
    M.xform(pump, loc=(0, 0.31, AX - 0.08), rot=(180, 0, 0))
    a.add(pump, "wood", name="pump")
    for y in (0.26, 0.31, 0.36):
        rb = M.box((0.097, 0.016, 0.058), bevel=0.005)
        M.xform(rb, loc=(0, y, AX - 0.084))
        a.add(rb, "iron", name="pump_rib")

    # muzzle bell (bronze) + glowing bore (a shallow cone inside the lip)
    bell = M.lathe([(0.046, 0.44), (0.055, 0.47), (0.07, 0.505), (0.095, 0.535), (0.122, 0.558),
                    (0.14, 0.573), (0.136, 0.59), (0.118, MUZZLE_Y)], sides=16, cap=False)
    M.xform(bell, rot=(-90, 0, 0))
    M.xform(bell, loc=(0, 0, AX))
    a.add(bell, "bronze", name="bell", shading="smooth")
    bore = M.lathe([(0.118, MUZZLE_Y), (0.088, 0.574), (0.05, 0.556), (0.0, 0.546)], sides=16, cap=False)
    M.xform(bore, rot=(-90, 0, 0))
    M.xform(bore, loc=(0, 0, AX))
    a.add(bore, "glow_bell", name="bore", shading="smooth")

    # the sun crown: ten chunky rays raked forward, alternating long / short (the SPREAD silhouette)
    for i in range(10):
        ang = math.radians(90 + 36 * i)
        radial = Vector((math.cos(ang), 0, math.sin(ang)))
        rake = math.radians(RAY_RAKE)
        d = (radial * math.cos(rake) + Vector((0, 1, 0)) * math.sin(rake)).normalized()
        long_ray = i % 2 == 0
        sp = M.spike(0.032 if long_ray else 0.026, 0.16 if long_ray else 0.105, sides=4, base_scale=(1.0, 0.55),
                     rot_offset=0)
        M.xform(sp, matrix=M.orient(Vector((0, RAY_BASE_Y, AX)) + radial * RAY_R0, d,
                                    (-math.sin(ang), 0, math.cos(ang))))
        a.add(sp, "sunray", name="ray")

    # butt stock (wood) lofted from inside the receiver back, bronze butt plate
    stock = M.loft_rect([(-0.035, 0.07, 0.09, 0, AX), (-0.12, 0.062, 0.082, 0, AX - 0.02),
                         (-0.26, 0.068, 0.14, 0, AX - 0.038), (-0.36, 0.074, 0.18, 0, AX - 0.046)],
                        bevel=0.013, segments=2)
    a.add(stock, "wood", name="stock")
    bp = M.box((0.082, 0.032, 0.195), bevel=0.009, taper=(0.9, 1.0))
    M.xform(bp, loc=(0, -0.374, AX - 0.046))
    a.add(bp, "bronze", name="butt_plate")
    a.add(M.studs([(0, -0.39, AX + 0.02), (0, -0.39, AX - 0.11)], [(0, -1, 0)] * 2, 0.009, 0.007), "gold",
          name="butt_rivets", shading="smooth")

    # sun-shells in a leather holder on the stock's right side (+X is the weapon's right)
    strap = M.box((0.013, 0.13, 0.06), bevel=0.004)
    M.xform(strap, loc=(0.038, -0.187, AX - 0.035))
    a.add(strap, "leather", name="shell_strap")
    for k in range(4):
        y = -0.235 + k * 0.032
        sh = M.cylinder(0.013, 0.07, sides=8, bevel=0.002, axis="Z")
        M.xform(sh, loc=(0.052, y, AX - 0.035))
        a.add(sh, "shell", name="shell", shading="smooth")
        hd = M.cylinder(0.014, 0.015, sides=8, axis="Z")
        M.xform(hd, loc=(0.052, y, AX - 0.077))
        a.add(hd, "gold", name="shell_head", shading="smooth")

    # trigger guard (iron strap) and trigger
    guard = M.catmull([(0, 0.03, AX - 0.072), (0, 0.05, AX - 0.13), (0, 0.1, AX - 0.142), (0, 0.13, AX - 0.112),
                       (0, 0.14, AX - 0.072)], 3)
    a.add(M.band(guard, 0.018, 0.01, up=(1, 0, 0)), "iron", name="guard")
    a.add(M.horn([(0, 0.08, AX - 0.074), (0, 0.076, AX - 0.096), (0, 0.086, AX - 0.114)], 0.007, 0.003, sides=5),
          "iron", name="trigger", shading="smooth")

    obj = a.to_object(col)
    C.log("mesh: %d parts, %d tris" % (len(a.parts), sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return obj


# ---- paint -------------------------------------------------------------------------------------------------

RECIPES = {
    "iron": P.zone(base="#3B3340", shadow="#161119", light="#8C7F92", planes=0.07, edge=0.95, edge_width=0.0045,
                   cavity=0.6, ao=0.5, brush=0.05),
    "bronze": P.zone(base="#B87A35", shadow="#57301A", light="#F6CE7A", planes=0.08, parts=0.05, edge=0.85,
                     edge_width=0.005, cavity=0.75, ao=0.6,
                     spots={"color": "#7A4A22", "amount": 0.25, "freq": 14.0, "threshold": (0.62, 0.74)}),
    "gold": P.zone(base="#E4B24A", shadow="#86511A", light="#FFF2BE", planes=0.08, edge=0.8, edge_width=0.004,
                   cavity=0.6, ao=0.5),
    "sunray": P.zone(base="#E8B64C", shadow="#8A531A", light="#FFF4C8", planes=0.1, edge=0.7, edge_width=0.004,
                     cavity=0.5, ao=0.4,
                     emit={"core": "#FFB43C", "hot": "#FFD45A", "color": "#FFF6D8", "mode": "axis",
                           "center": (0, RAY_BASE_Y, AX), "axis": (0, 1, 0), "radius": 0.27,
                           "fade": (0.7, 0.92), "base_mix": 0.35}),
    "wood": P.zone(base="#5E3625", shadow="#29130D", light="#9C6642", planes=0.05, parts=0.04, edge=0.55,
                   edge_width=0.005, cavity=0.7, ao=0.6, stroke=(0, 1, 0), stroke_amount=0.32,
                   stroke_freq=(75.0, 5.0)),
    "leather": P.zone(base="#4A2622", shadow="#1C0C0B", light="#7E4839", edge=0.5, edge_width=0.003),
    "shell": P.zone(base="#E6D8B8", shadow="#8A7254", light="#FFF9EA", planes=0.04, edge=0.4, cavity=0.5, ao=0.5),
    "glow_bell": P.zone(base="#FFE27A", emit={"core": "#FFFCEE", "hot": "#FFE27A", "color": "#FFAA33", "mode": "axis",
                                              "center": (0, MUZZLE_Y, AX), "axis": (0, 1, 0), "radius": 0.118}),
    "glow_core": P.zone(base="#FFE27A", emit={"core": "#FFFCEE", "hot": "#FFE27A", "color": "#FFA531", "mode": "axis",
                                              "center": CORE, "axis": (1, 0, 0), "radius": 0.047}),
    "glow_line": P.zone(base="#FFE27A", edge=0.0, cavity=0.0, ao=0.0,
                        emit={"core": "#FFD45A", "hot": "#FFE27A", "color": "#FFF6D8", "mode": "plane",
                              "axis": (0, 1, 0), "range": (-0.055, 0.455)}),
}


def decals():
    out = []
    # carved sunburst on both stock sides: painted gold lines in a dark burnt groove
    for sx in (-1, 1):
        u = Vector((0, sx, 0))            # u x v must point out of the side (+X left, -X right)
        v = Vector((0, 0, 1))
        z = u.cross(v)
        fr = Matrix(((u.x, v.x, z.x, 0), (u.y, v.y, z.y, 0), (u.z, v.z, z.z, 0), (0, 0, 0, 1)))
        fr = Matrix.Translation(Vector((0, -0.268, AX - 0.04))) @ fr
        lines = M.sunburst(12, 0.018, 0.056, 0.04)
        lines.append([(0.018 * math.cos(math.radians(a)), 0.018 * math.sin(math.radians(a))) for a in range(0, 361, 30)])
        out.append(P.decal_lines(lines, fr, 0.0045, zones=["wood"], color="#D9A444", rim="#1E0D08",
                                 rim_width=0.008, depth=(0.0, 0.06)))
    return out


# ---- main ---------------------------------------------------------------------------------------------------

def main():
    argv = C.script_args()
    size = C.opt(argv, "--size", 1024, int)
    C.reset_scene()
    col = C.get_collection(KEY)
    root = C.add_empty(KEY, size=0.1, col=col)
    mesh = build_mesh(col)
    mesh.parent = root
    # sockets (docs/art/WEAPONS.md section 3): children of the root, +Y forward, +Z up
    C.add_empty("grip_R", (0, 0, 0), parent=root, col=col)
    C.add_empty("grip_L", GRIP_L, parent=root, col=col)
    C.add_empty("muzzle", (0, MUZZLE_Y, AX), parent=root, col=col)
    C.add_empty("glow_core", CORE, parent=root, col=col)

    pack = C.pack_dir(KIND, KEY)
    tex_dir = os.path.join(pack, "textures")
    paint_rep = P.paint_asset(mesh, KEY, RECIPES, tex_dir, size=size, decals=decals(), ao_distance=0.035,
                              ao_samples=24, seed=3)
    blend = os.path.join(pack, "source", KEY + ".blend")
    C.save_blend(blend)
    bpy.ops.file.make_paths_relative()
    C.save_blend(blend)
    rep = E.export_asset(KIND, KEY, TIER, root, source_blend=blend, build_script=__file__,
                         extra={"chassis": {"damage_type": "Radiant", "style": "Pellet", "tags": ["spread", "close"]},
                                "paint": {k: paint_rep[k] for k in ("size", "texel_density_px_per_m", "coverage")}})
    reports = os.path.join(pack, "reports")
    if not C.flag(argv, "--no-review"):
        work = C.ensure_dir(os.path.join(pack, "work", "review"))
        notes = [
            "%s tris (two-handed budget 2000-4000) | textures %s | length %.2f m | sockets: %s" % (
                rep["tris"], " + ".join("%dpx" % t["px"][0] for t in rep["textures"]), rep["length_m"],
                ", ".join(sorted(rep["sockets"]))),
            "Grip frame: origin = right palm centre on the pistol grip, Blender +Y = barrel (glTF -Z), +Z = up. "
            "grip_L under the pump, muzzle at the bore, glow_core in the receiver sun.",
            "Status: %s (the user gives the final visual approval)." % rep.get("status", "ai_final_pending_user_approval"),
        ]
        R.review_weapon(KEY, root, mesh, reports, work, "Sunspike Shotgun  (sunspike_shotgun)",
                        "Radiant | Pellet x7, 22 deg spread | tags: spread, close | silhouette verb: FAN-OUT (sun-crown bell)",
                        swatches=PALETTE, notes=notes,
                        textures=[os.path.join(tex_dir, KEY + "_basecolor.png"), os.path.join(tex_dir, KEY + "_emissive.png")])
    C.write_json(os.path.join(reports, "build_report.json"), {"export": rep, "paint": paint_rep})
    C.write_pack_status(KIND, KEY, [
        C.rel(C.model_path(KIND, KEY)), C.rel(os.path.splitext(C.model_path(KIND, KEY))[0] + ".meta.json"),
        C.rel(blend), C.rel(os.path.join(tex_dir, KEY + "_basecolor.png")), C.rel(os.path.join(tex_dir, KEY + "_emissive.png")),
        C.rel(os.path.join(reports, KEY + "_review.png"))],
        "Built from code by tools/blender/gf_assets/weapons/sunspike_shotgun.py (gf_assets proof weapon).",
        tier=TIER)
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
