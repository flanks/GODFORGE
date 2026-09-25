"""The Bellows review-fix evidence (headless Blender 5.2): ground contact of every clip, side views of the key
poses against the ground, and the game-size silhouette, for ANY build of the_bellows (the committed pre-fix blend
or the current one), so the before / after sheet compares like with like.

    blender -b <the_bellows.blend> --factory-startup --python-exit-code 1 \
        -P tools/blender/gf_assets/enemies/the_bellows_fix_views.py -- --out DIR --tag before|after [--tex DIR]

  --out  where the PNGs and <tag>_ground.json go
  --tex  relink missing textures from this folder (a pre-fix blend copied out of the pack)

Ground contact is measured on the evaluated (skinned) mesh on every frame of every clip: the lowest paw vertex
(z of the paw, toes and claws), the lowest vertex of the head (bell, mask, rays, horn) and the lowest vertex of
everything else. The floor is z = 0.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import gfa_boss as B  # noqa: E402
import gfa_common as C  # noqa: E402
import gfa_model as M  # noqa: E402
import gfa_render as R  # noqa: E402
import gfa_rig as RIG  # noqa: E402

KEY = "the_bellows"
CLIPS = ["idle@loop", "move@loop", "windup", "attack", "hit", "radial", "summon", "strike_ring", "phase2",
         "idle_p2@loop", "move_p2@loop", "windup_p2", "attack_p2", "hit_p2", "radial_p2", "summon_p2",
         "strike_ring_p2", "strike_circle", "death"]
# the side views: (clip, frame, label) - the frames where the pre-fix build went deepest under the floor
SIDE = [("move@loop", 36, "move@loop f36"), ("strike_ring", 30, "strike_ring f30 (slam)"),
        ("summon", 19, "summon f19 (heave)"), ("death", 90, "death f90 (end)")]


def objs():
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    mesh = next(o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers))
    return arm, mesh


def relink(tex):
    for img in bpy.data.images:
        if img.source != "FILE":
            continue
        p = bpy.path.abspath(img.filepath)
        if not os.path.exists(p):
            q = os.path.join(tex, os.path.basename(img.filepath))
            if os.path.exists(q):
                img.filepath = q
                img.reload()


def groups(mesh):
    names = {vg.index: vg.name for vg in mesh.vertex_groups}
    n = len(mesh.data.vertices)
    g = np.empty(n, dtype=object)
    for v in mesh.data.vertices:
        g[v.index] = names[max(v.groups, key=lambda x: x.weight).group] if len(v.groups) else ""
    paw = np.array(["_paw_" in s for s in g])
    head = np.array([s in ("head", "mask_shard") for s in g])
    legs = {k: np.array([s == k for s in g]) for k in sorted({s for s in g if "_paw_" in s})}
    return paw, head, ~(paw | head), legs


def zs(mesh):
    # tag and force the depsgraph before reading: an untagged read can return a stale skinned mesh (seen once as
    # single-frame 5-10 cm "dips" that a re-run did not reproduce; the baked pose itself matched its F-curves)
    arm = mesh.find_armature()
    for ob in (arm, mesh):
        if ob is not None:
            ob.update_tag()
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    ev = mesh.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    co = co.reshape(-1, 3)
    mw = np.array(mesh.matrix_world)
    return (co @ mw[:3, :3].T + mw[:3, 3])[:, 2]


def ground_report(arm, mesh):
    paw, head, rest, legs = groups(mesh)
    out = {}
    for clip in CLIPS:
        tr = arm.animation_data.nla_tracks.get("%s_%s" % (KEY, clip))
        if tr is None:
            continue
        a = tr.strips[0].action
        f0, f1 = int(a.frame_start), int(a.frame_end)
        rows = []
        for f in range(f0, f1 + 1):
            RIG.pose_at(arm, tr.name, f)
            z = zs(mesh)
            rows.append({"f": f, "paw": float(z[paw].min()), "head": float(z[head].min()), "body": float(z[rest].min()),
                         "legs": {k: float(z[m].min()) for k, m in legs.items()}})
        low = min(rows, key=lambda r: r["paw"])
        hlow = min(rows, key=lambda r: r["head"])
        blow = min(rows, key=lambda r: r["body"])
        # a paw counts as planted when it is the lowest point of its leg's cycle within 5 cm of the floor
        out[clip] = {"frames": [f0, f1],
                     "paw_min_z": round(low["paw"], 3), "paw_min_frame": low["f"],
                     "head_min_z": round(hlow["head"], 3), "head_min_frame": hlow["f"],
                     "body_min_z": round(blow["body"], 3), "body_min_frame": blow["f"],
                     "per_frame": [{"f": r["f"], "paw": round(r["paw"], 3), "head": round(r["head"], 3),
                                    "body": round(r["body"], 3)} for r in rows]}
        C.log("%-16s paw %+.3f (f%d)  head %+.3f (f%d)  body %+.3f (f%d)" % (
            clip, low["paw"], low["f"], hlow["head"], hlow["f"], blow["body"], blow["f"]))
    RIG.unmute_none(arm)
    return out


def ground_props():
    """A dark 'underground' band behind the creature (x = -4.5) topped by a light floor line: anything drawn
    over the band is under the floor. Returns (band, line)."""
    out = []
    for name, size, loc in (("GFA_UNDERGROUND", (0.1, 24.0, 3.0), (-4.5, 0.0, -1.5)),
                            ("GFA_GROUND_LINE", (0.1, 24.0, 0.05), (-4.4, 0.0, -0.025))):
        asm = M.Assembly(name, ["flat"])
        b = M.box(size)
        M.xform(b, loc=loc)
        asm.add(b, "flat")
        out.append(asm.to_object())
    return out


def side_views(arm, mesh, out_dir, tag):
    scene = bpy.context.scene
    R.setup_cycles(scene, 6, bg="#2E2A33")
    band, line = ground_props()
    out = []
    d = Vector((1.0, 0.0, 0.0))
    with R.toon_preview([mesh, band, line], ink=0.03, flat={band.name: "#3B2F2A", line.name: "#E8DCC0"}):
        for clip, f, label in SIDE:
            RIG.pose_at(arm, "%s_%s" % (KEY, clip), f)
            R.aim(scene, Vector((0.0, -0.9, 2.0)), d, 12.0, dist=60.0)
            p = os.path.join(out_dir, "%s_side_%s_%d.png" % (tag, clip.replace("@", "_"), f))
            R.render(scene, p, 520, 420)
            out.append({"clip": clip, "frame": f, "label": label, "path": p})
    RIG.unmute_none(arm)
    C.remove_objects([band, line])
    return out


def silhouette(arm, mesh, out_dir, tag):
    """Flat black at the game camera, 22 m view height, true pixels (like the review's game-size silhouette)."""
    scene = bpy.context.scene
    RIG.pose_at(arm, "%s_idle@loop" % KEY, 0)
    R.setup_workbench_flat(scene)
    fl = bpy.data.objects.get("GFA_FLOOR")
    if fl:
        fl.hide_render = True
    ppm = 1080 / 22.0
    R.aim(scene, Vector((0.0, 0.3, 1.5)), B.game_dir(), 560 / ppm, dist=90.0)
    p = os.path.join(out_dir, "%s_sil_game22.png" % tag)
    R.render(scene, p, 560, 560)
    RIG.unmute_none(arm)
    return p


def main():
    argv = C.script_args()
    out_dir = C.ensure_dir(C.opt(argv, "--out", "."))
    tag = C.opt(argv, "--tag", "after")
    tex = C.opt(argv, "--tex", None)
    if tex:
        relink(tex)
    arm, mesh = objs()
    rep = ground_report(arm, mesh)
    C.write_json(os.path.join(out_dir, "%s_ground.json" % tag), rep, quiet=True)
    views = side_views(arm, mesh, out_dir, tag)
    sil = silhouette(arm, mesh, out_dir, tag)
    C.write_json(os.path.join(out_dir, "%s_views.json" % tag), {"side": views, "sil": sil}, quiet=True)
    C.log("DONE", tag)


if __name__ == "__main__":
    main()
