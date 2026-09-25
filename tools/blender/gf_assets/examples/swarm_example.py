"""gf_assets example: a small rigged swarm crawler on GF_Swarm_v1, end to end (model -> rigid skin ->
six clips -> paint -> export -> validate -> review sheet). It proves the enemy path of the toolkit and is
the template for swarm enemies (clinker, rotmite, ticker, nullmite: docs/art/ENEMIES.md).

  "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup --python-exit-code 1 \
      -P tools/blender/gf_assets/examples/swarm_example.py -- [--out <dir>] [--no-review]

Writes to tools/blender/gf_assets/examples/_out/ (git-ignored) - never to assets/models/: the key
`example_crawler` is not a content key.
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from mathutils import Vector  # noqa: E402

import gfa_common as C  # noqa: E402
import gfa_export as E  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_paint as P  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402

KEY = "example_crawler"
BODY_Z = 0.3


def build(col):
    rng = random.Random(11)
    a = M.Assembly(KEY + "_mesh", ["obsidian", "bone", "ichor"], bones=RIG.BONE_NAMES)
    # body: a hunched faceted shell (obsidian) over a pale inner mass (bone)
    shell = M.ico(0.21, 1, scale=(1.0, 1.35, 0.8))
    M.noise_displace(shell, 0.03, freq=7.0, seed=2)
    M.xform(shell, loc=(0, 0.02, BODY_Z + 0.03))
    a.add(shell, "obsidian", bone="body", name="shell", shading="flat")
    inner = M.ico(0.17, 1, scale=(1.0, 1.25, 0.7))
    M.xform(inner, loc=(0, 0.02, BODY_Z - 0.03))
    a.add(inner, "bone", bone="body", name="inner", shading="flat")
    # glowing ichor core showing through the shell cracks
    core = M.ico(0.12, 1, scale=(1.0, 1.2, 0.8))
    M.xform(core, loc=(0, 0.0, BODY_Z + 0.06))
    a.add(core, "ichor", bone="body", name="core", shading="smooth")
    # back shards (tail group: they rattle)
    for i in range(3):
        sp = M.spike(0.05, 0.16 - 0.03 * i, sides=4, tip=(0, 0.04, 0))
        M.xform(sp, loc=(0.03 * (i - 1), 0.08 + 0.07 * i, BODY_Z + 0.16 - 0.03 * i), rot=(-35 - 10 * i, 12 * (i - 1), 0))
        a.add(sp, "obsidian", bone="tail", name="shard", shading="flat")
    # head: a blunt wedge with a vertical glowing split (jaw)
    head = M.box((0.16, 0.14, 0.13), bevel=0.02, taper=(0.8, 0.7))
    M.xform(head, loc=(0, -0.24, BODY_Z - 0.02), rot=(15, 0, 0))
    a.add(head, "obsidian", bone="head", name="head", shading="flat")
    split = M.box((0.018, 0.04, 0.1), bevel=0.004)
    M.xform(split, loc=(0, -0.305, BODY_Z - 0.02), rot=(15, 0, 0))
    a.add(split, "ichor", bone="head", name="jaw_glow", shading="flat")
    # legs: tripod gait groups (A = front-left, mid-right, back-left; B = the others)
    for side, sx in (("L", 1), ("R", -1)):
        for j, y in enumerate((-0.14, 0.0, 0.14)):
            group = "legs_a" if (j % 2 == 0) == (sx == 1) else "legs_b"
            hip = Vector((sx * 0.14, y, BODY_Z - 0.02))
            knee = Vector((sx * 0.3, y * 1.3 - 0.02, BODY_Z + 0.08))
            foot = Vector((sx * 0.36, y * 1.5 - 0.04, 0.0))
            a.add(M.horn([hip, knee, foot], 0.032, 0.006, sides=5), "obsidian", bone=group, name="leg_%s%d" % (side, j),
                  shading="flat")
    obj = a.to_object(col)
    C.log("mesh %d tris" % sum(len(p.vertices) - 2 for p in obj.data.polygons))
    return obj


def main():
    argv = C.script_args()
    out_dir = C.opt(argv, "--out", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out"))
    C.reset_scene(fps=30)
    col = C.get_collection(KEY)
    mesh = build(col)
    arm = RIG.build_swarm_rig({"body": (0, 0, BODY_Z), "head": (0, -0.18, BODY_Z), "legs_a": (0, 0, BODY_Z),
                               "legs_b": (0, 0, BODY_Z), "tail": (0, 0.1, BODY_Z + 0.05)}, col=col)
    probs = RIG.validate_rig(arm)
    assert not probs, probs
    skin = RIG.skin_rigid(mesh, arm)
    C.log("skin", skin)
    RIG.add_socket(arm, "body", "hit_center", (0, 0, BODY_Z))
    RIG.add_socket(arm, "body", "fx_core", (0, 0, BODY_Z + 0.06))
    RIG.add_socket(arm, "head", "fx_mouth", (0, -0.31, BODY_Z - 0.02))
    clips = RIG.swarm_clip_set(arm, KEY, scale=1.0)
    recipes = {
        "obsidian": P.faction_zone("unmade", "obsidian", planes=0.12, edge=0.9, edge_width=0.006),
        "bone": P.faction_zone("unmade", "bone"),
        "ichor": P.faction_zone("unmade", "ichor", glow=True,
                                emit={"color": "#1F8F7E", "hot": "#2FBFA8", "core": "#B8FFE8", "mode": "radial",
                                      "center": (0, 0, BODY_Z + 0.06), "radius": 0.2}),
    }
    cracks = M.crack_lines(random.Random(5), start=(0.0, -0.12), direction=90, length=0.3, branches=2)
    from mathutils import Matrix
    decal = P.decal_lines(cracks, Matrix.Translation((0, 0, BODY_Z)), 0.008, zones=["obsidian"], color="#2FBFA8",
                          rim="#07060A", emit={"color": "#2FBFA8", "core": "#B8FFE8"}, depth=(0.0, 0.3))
    tex_dir = os.path.join(out_dir, "textures")
    P.paint_asset(mesh, KEY, recipes, tex_dir, size=512, decals=[decal], ao_distance=0.05, seed=1)
    blend = os.path.join(out_dir, KEY + ".blend")
    C.save_blend(blend)
    rep = E.export_asset("enemy", KEY, "swarm", arm, source_blend=blend, build_script=__file__,
                         out=os.path.join(out_dir, KEY + ".glb"))
    C.log("clips", RIG.clips_report(arm))
    if not C.flag(argv, "--no-review"):
        R.review_enemy(KEY, arm, mesh, out_dir, os.path.join(out_dir, "work"), "Example crawler (GF_Swarm_v1 test)",
                       "gf_assets swarm path: rigid skin, six clips, export + validation",
                       clips=clips, textures=[os.path.join(tex_dir, KEY + "_basecolor.png"),
                                              os.path.join(tex_dir, KEY + "_emissive.png")],
                       notes=["%s tris, clips: %s" % (rep["tris"], ", ".join(rep["clips"]))])
    C.log("DONE", KEY)


if __name__ == "__main__":
    main()
