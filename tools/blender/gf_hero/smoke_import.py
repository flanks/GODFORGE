"""Stage 5: re-import smoke test of a shipped hero GLB in a fresh headless Blender (+ optional review renders).

  blender -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/smoke_import.py -- \
          assets/models/characters/brax.glb [--weapon assets/models/weapons/anvil_gauntlets.glb] [--json out.json] \
          [--render <dir>] [--report art/characters/brax/reports/export_report.json]

Factory settings, 30 fps, then Blender's own glTF importer (a second, independent consumer of the file):
  * the armature object is GF_Hero_v1 and its bones are exactly the contract bones (names + parents, gf_hero_rig),
    the four sockets are there, the mesh is skinned to it (Armature modifier, vertex groups = bones);
  * one action per glTF animation with the exact name; EVERY clip is played one frame (its middle): each bone's world
    frame, mapped through that bone's constant rest correction, must equal the frame the GLB's own forward kinematics
    gives (validate_glb.py, stdlib) within 1e-4, and the skinned mesh must stay sane (finite, on the ground, not
    exploded or collapsed);
  * --weapon: the weapon GLB is imported too and attached the way the client will (its root on weapon_R, its offhand
    node on weapon_L, both as identity children in glTF terms); the grip frames are compared with the GLB sockets.
--render <dir>: review renders of the shipped files (the stage-2 textures from inside the GLBs through the Cycles CPU
  toon preview of s3lib, never EEVEE): six key poses as front three-quarter close-ups and the 55 deg client camera at
  true 1080p pixel size (22 m view height, 160 px), the weapon variant per hand as the hero sidecar says.
Writes the JSON report (--json, and section "blender_reimport" of --report); exits 1 on any error.
The Bevy-side import (a Rust test that loads the GLB through bevy_gltf) comes with the engine integration.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import gf_hero_rig as R  # noqa: E402
import validate_glb as V  # noqa: E402

T0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    raise SystemExit(__doc__)


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


def log(*a):
    print("[smoke %6.1fs]" % (time.time() - T0), *a, flush=True)


GLB = os.path.abspath(argv[0])
WEAPON = opt("--weapon")
WEAPON = os.path.abspath(WEAPON) if WEAPON else None
RENDER = opt("--render")
C = Matrix(R.SOCKET_TO_GRIP)          # Blender -> glTF
CI = C.inverted()
E, W = [], []
rep = {"file": V.relpath(GLB), "blender": bpy.app.version_string, "importer": None}


def mat(rows):
    return Matrix([list(r) for r in rows])


def finish():
    rep["errors"], rep["warnings"] = E, W
    rep["ok"] = not E
    rep["seconds"] = round(time.time() - T0, 1)
    js = opt("--json")
    if js:
        with open(js, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    rp = opt("--report")
    if rp:
        full = {}
        if os.path.isfile(rp):
            with open(rp, encoding="utf-8") as f:
                full = json.load(f)
        full["blender_reimport"] = rep
        oks = [v.get("ok") for k, v in full.items() if isinstance(v, dict) and "ok" in v]
        oks += [v.get("ok") for v in full.get("weapons", {}).values() if isinstance(v, dict)]
        full["ok"] = all(o is True for o in oks) if oks else False
        with open(rp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(full, f, indent=1)
            f.write("\n")
    for w in W:
        log("warning:", w)
    for e in E:
        log("ERROR:", e)
    log("re-import %s: %s" % (rep["file"], "OK" if not E else "FAILED"))
    if E:
        raise SystemExit(1)


# ---- import ------------------------------------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps, scene.render.fps_base = V.FPS, 1.0
g = V.Glb(GLB)
key = os.path.splitext(os.path.basename(GLB))[0]
meta_p = os.path.splitext(GLB)[0] + ".meta.json"
meta = json.load(open(meta_p, encoding="utf-8")) if os.path.isfile(meta_p) else {}
before = set(bpy.data.objects)
res = bpy.ops.import_scene.gltf(filepath=GLB, disable_bone_shape=True, import_shading="NORMALS")
rep["importer"] = sorted(res)
hero_objs = [o for o in bpy.data.objects if o not in before]
arms = [o for o in hero_objs if o.type == "ARMATURE"]
meshes = [o for o in hero_objs if o.type == "MESH"]
rep["objects"] = sorted(o.name for o in hero_objs)
if len(arms) != 1:
    E.append("%d armatures after import" % len(arms))
    finish()
arm = arms[0]
if arm.name != R.RIG_NAME:
    E.append("the armature object is %r, not %s (Bevy target paths start at it)" % (arm.name, R.RIG_NAME))
bones = arm.data.bones
names = {b.name for b in bones}
contract = set(R.contract_bone_names())
rep["bones"] = len(bones)
if contract - names:
    E.append("bones missing after import: %s" % sorted(contract - names))
if {n for n in names - contract if not n.startswith(R.EXTRA_PREFIX)}:
    E.append("unexpected bones %s" % sorted(n for n in names - contract if not n.startswith(R.EXTRA_PREFIX)))
wrong = [b for b, p in R.contract_parents().items()
         if b in names and (bones[b].parent.name if bones[b].parent else None) != p]
if wrong:
    E.append("bone parents differ from the contract after import: %s" % wrong[:8])
rep["sockets"] = {s: s in names for s in R.SOCKET_NAMES}
if not all(rep["sockets"].values()):
    E.append("sockets missing after import: %s" % [s for s, ok in rep["sockets"].items() if not ok])
skinned = [o for o in meshes if any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
rep["meshes"] = {o.name: {"verts": len(o.data.vertices), "skinned": o in skinned,
                          "vertex_groups_not_bones": sorted(vg.name for vg in o.vertex_groups if vg.name not in names),
                          "materials": [m.name for m in o.data.materials if m],
                          "uv_layers": [u.name for u in o.data.uv_layers]} for o in meshes}
if not skinned or len(skinned) != len(meshes):
    E.append("mesh objects not skinned to %s: %s" % (R.RIG_NAME, [o.name for o in meshes if o not in skinned]))
for o in meshes:
    if rep["meshes"][o.name]["vertex_groups_not_bones"]:
        E.append("%s has vertex groups that are not bones: %s" % (o.name, rep["meshes"][o.name]["vertex_groups_not_bones"][:6]))
rep["images"] = {im.name: list(im.size) for im in bpy.data.images}

# ---- rest correction per bone: imported bone frame -> glTF node frame (constant) ------------------------------------------
gw_rest = V.world_matrices(g)
gidx = {n: i for i, n in enumerate(g.names)}
arm.animation_data_create()
arm.animation_data.action = None
for tr in arm.animation_data.nla_tracks:
    tr.mute = True
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()
K = {}
for b in bones:
    if b.name in gidx:
        B = arm.matrix_world @ arm.pose.bones[b.name].matrix
        K[b.name] = B.inverted() @ (CI @ mat(gw_rest[gidx[b.name]]) @ C)
rest_socket_err = {}
for s in R.SOCKET_NAMES:
    if s in K:           # the importer should restore the authored socket axes: K = the +Y-up conversion (SOCKET_TO_GRIP)
        rest_socket_err[s] = max(abs(K[s][r][c] - C[r][c]) for r in range(4) for c in range(4))
rep["socket_axes_restored_vs_authoring"] = rest_socket_err

# ---- every clip, one frame --------------------------------------------------------------------------------------------------
anims = g.doc.get("animations", [])
clips = {}
worst = 0.0
dg = bpy.context.evaluated_depsgraph_get()


def mesh_sane(tag):
    import numpy as np
    pts = []
    for o in skinned:
        e = o.evaluated_get(dg)
        me = e.to_mesh()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        e.to_mesh_clear()
        mw = np.array(o.matrix_world)
        pts.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
    pts = np.concatenate(pts)
    fin = np.isfinite(pts).all(axis=1)
    bad = int((~fin).sum())
    lo, hi = Vector(pts[fin].min(0).tolist()), Vector(pts[fin].max(0).tolist())
    ext = hi - lo
    probs = []
    if bad:
        probs.append("%d non-finite vertices" % bad)
    if lo.z < -0.35:
        probs.append("mesh %.2f m under the ground" % lo.z)
    if max(ext) > 3.2 or max(abs(lo.x), abs(hi.x), abs(lo.y), abs(hi.y)) > 2.5:
        probs.append("mesh exploded (extent %s)" % [round(x, 2) for x in ext])
    if max(ext) < 0.5:
        probs.append("mesh collapsed (extent %s)" % [round(x, 2) for x in ext])
    return {"min_z": round(lo.z, 4), "extent": [round(x, 3) for x in ext]}, probs


for a in anims:
    name = a.get("name", "")
    act = bpy.data.actions.get(name)
    if act is None:
        E.append("no action %r after import" % name)
        continue
    arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
    chans = V.channel_data(g, a)
    tmax = max(c[3][-1] for c in chans) if chans else 0.0
    f = int(round(tmax * V.FPS / 2.0))
    scene.frame_set(f)
    bpy.context.view_layer.update()
    gw = V.world_matrices(g, V.sample_animation(g, a, f / float(V.FPS), chans))
    err = 0.0
    for bn, k in K.items():
        B = arm.matrix_world @ arm.pose.bones[bn].matrix @ k
        G = CI @ mat(gw[gidx[bn]]) @ C
        err = max(err, max(abs(B[r][c] - G[r][c]) for r in range(3) for c in range(4)))
    worst = max(worst, err)
    ms, probs = mesh_sane(name)
    clips[name] = {"frame": f, "frame_range": list(act.frame_range), "max_bone_error": err, "mesh": ms}
    if err > 1e-4:
        E.append("%s: the imported pose differs from the GLB's kinematics by %.2e at frame %d" % (name, err, f))
    for p in probs:
        E.append("%s frame %d: %s" % (name, f, p))
extra_actions = sorted(a.name for a in bpy.data.actions if a.name not in {x.get("name") for x in anims})
if extra_actions:
    W.append("actions that are not glTF animations: %s" % extra_actions)
rep["clips_played"] = len(clips)
rep["clip_pose_max_error"] = worst
rep["clips"] = clips
log("%d clips played one frame each; worst bone frame error %.2e" % (len(clips), worst))
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.matrix_basis = Matrix.Identity(4)
bpy.context.view_layer.update()

# ---- the weapon, attached as the client will ------------------------------------------------------------------------------
W_OPEN, W_FIST = {}, {}
if WEAPON:
    wg = V.Glb(WEAPON)
    wkey = os.path.splitext(os.path.basename(WEAPON))[0]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=WEAPON, import_shading="NORMALS")
    wobjs = {o.name: o for o in bpy.data.objects if o not in before}
    wr = {"file": V.relpath(WEAPON), "objects": sorted(wobjs)}
    need = [wkey, "grip_R", "offhand"]
    for n in need:
        if n not in wobjs:
            E.append("weapon %s: no %s after import" % (wkey, n))
    if all(n in wobjs for n in need):
        root, off = wobjs[wkey], wobjs["offhand"]
        wr["root_is_identity"] = max(abs(root.matrix_world[r][c] - (1.0 if r == c else 0.0)) for r in range(4) for c in range(4)) < 1e-6
        if not wr["root_is_identity"]:
            E.append("weapon root %s is not at the identity after import" % wkey)
        for s, ob in (("weapon_R", root), ("weapon_L", off)):
            target = CI @ mat(gw_rest[gidx[s]]) @ C                 # the socket's glTF frame, in Blender axes
            ob.parent = arm
            ob.parent_type = "BONE"
            ob.parent_bone = s
            bpy.context.view_layer.update()
            ob.matrix_world = target
        bpy.context.view_layer.update()
        # grip frames through the imported sockets vs the GLB sockets
        gerr = 0.0
        for s, ob in (("weapon_R", root), ("weapon_L", off)):
            target = CI @ mat(gw_rest[gidx[s]]) @ C
            gerr = max(gerr, max(abs(ob.matrix_world[r][c] - target[r][c]) for r in range(3) for c in range(4)))
        wr["attach_rest_error"] = gerr
        for n, o in wobjs.items():
            if o.type == "MESH":
                (W_FIST if "_fist_" in n else W_OPEN)[n[-1]] = o
        wr["variants"] = {"fist": sorted(o.name for o in W_FIST.values()), "open": sorted(o.name for o in W_OPEN.values())}
        # follow one clip: the grip must ride the socket (identity child) at the strike frame
        act = bpy.data.actions.get("%s_jab_r" % key)
        if act is not None:
            arm.animation_data.action = act
            arm.animation_data.action_slot = act.slots[0]
            scene.frame_set(3)
            bpy.context.view_layer.update()
            a = [x for x in anims if x["name"] == act.name][0]
            gw = V.world_matrices(g, V.sample_animation(g, a, 3 / float(V.FPS)))
            target = CI @ mat(gw[gidx["weapon_R"]]) @ C
            wr["attach_jab_r_f3_error"] = max(abs(root.matrix_world[r][c] - target[r][c]) for r in range(3) for c in range(4))
            if wr["attach_jab_r_f3_error"] > 1e-4:
                E.append("the weapon does not ride weapon_R during %s (%.2e)" % (act.name, wr["attach_jab_r_f3_error"]))
            arm.animation_data.action = None
    rep["weapon"] = wr
    log("weapon %s attached: rest error %.1e" % (wkey, wr.get("attach_rest_error", -1)))


# ---- review renders of the shipped files ------------------------------------------------------------------------------------
def review(out_dir):
    from s2lib import aim_ortho, render_still
    from s3lib import cycles_cpu, make_toon_cycles
    os.makedirs(out_dir, exist_ok=True)
    toon = {}
    objs = skinned + list(W_FIST.values()) + list(W_OPEN.values())
    for o in objs:
        M = o.material_slots[0].material if o.material_slots else None
        if M is None:
            continue
        if M.name not in toon:
            toon[M.name] = make_toon_cycles(M)
        o.material_slots[0].link = "OBJECT"
        o.material_slots[0].material = toon[M.name]
    grid = bpy.data.objects.new("GRID", bpy.data.meshes.new("GRID"))
    grid.data.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    gm = bpy.data.materials.new("grid")
    gm.use_nodes = True
    nt = gm.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em, outn, ck, tc = (nt.nodes.new(t) for t in ("ShaderNodeEmission", "ShaderNodeOutputMaterial", "ShaderNodeTexChecker", "ShaderNodeTexCoord"))
    ck.inputs["Scale"].default_value = 12.0
    ck.inputs["Color1"].default_value = (0.11, 0.075, 0.06, 1)
    ck.inputs["Color2"].default_value = (0.16, 0.115, 0.09, 1)
    nt.links.new(tc.outputs["Object"], ck.inputs["Vector"])
    nt.links.new(ck.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], outn.inputs["Surface"])
    grid.data.materials.append(gm)
    scene.collection.objects.link(grid)
    floor = bpy.data.objects.new("GROUND", bpy.data.meshes.new("GROUND"))
    floor.data.from_pydata([(-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new("ground")
    fm.use_nodes = True
    fnt = fm.node_tree
    for n in list(fnt.nodes):
        fnt.nodes.remove(n)
    e2, o2 = fnt.nodes.new("ShaderNodeEmission"), fnt.nodes.new("ShaderNodeOutputMaterial")
    e2.inputs["Color"].default_value = (0.075, 0.032, 0.018, 1)
    fnt.links.new(e2.outputs[0], o2.inputs["Surface"])
    floor.data.materials.append(fm)
    scene.collection.objects.link(floor)
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.035, 0.035, 0.04, 1)
    info = meta.get("clip_info", {})
    shots = [("idle_combat@loop", 0), ("jab_r", 3), ("uppercut", 10), ("meltdown_start", 27), ("run@loop", 6), ("ping", 14)]
    done = []
    for clip, f in shots:
        name = "%s_%s" % (key, clip)
        act = bpy.data.actions.get(name)
        if act is None:
            continue
        arm.animation_data.action = act
        arm.animation_data.action_slot = act.slots[0]
        scene.frame_set(f)
        bpy.context.view_layer.update()
        wv = (info.get(name) or {}).get("weapon_variant") or {}
        shown = {}
        for s in ("L", "R"):
            v = wv.get(s, {"start": "fist", "swap_frames": []})
            fist = v["start"] == "fist"
            for sw in v["swap_frames"]:
                if f >= sw:
                    fist = not fist
            if s in W_FIST:
                W_FIST[s].hide_render = not fist
            if s in W_OPEN:
                W_OPEN[s].hide_render = fist
            shown[s] = "fist" if fist else "open"
        cycles_cpu(scene, samples=6)
        tag = "%s_f%03d" % (clip.replace("@loop", ""), f)
        grid.hide_render, floor.hide_render = False, True
        for view, az_d, el_d in (("front", 28, 10), ("side", 100, 8)):
            az, el = math.radians(az_d), math.radians(el_d)
            d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
            aim_ortho(scene, (0.0, 0.0, 1.05), d, 2.9)
            render_still(scene, os.path.join(out_dir, "%s_%s.png" % (tag, view)), 400, 480)
        grid.hide_render, floor.hide_render = True, False
        p = math.radians(55.0)
        for yaw in (0, 90):
            y = math.radians(yaw)
            dd = Vector((math.sin(y) * math.cos(p), -math.cos(y) * math.cos(p), math.sin(p)))
            aim_ortho(scene, (0.0, 0.0, 0.9), dd, 22.0 * 160 / 1080.0)
            render_still(scene, os.path.join(out_dir, "%s_ingame%d.png" % (tag, yaw)), 160)
        done.append({"shot": tag, "clip": name, "frame": f, "weapon_shown": shown})
        log("rendered", tag, shown)
    arm.animation_data.action = None
    return done


if RENDER:
    try:
        rep["review_renders"] = {"dir": V.relpath(RENDER), "shots": review(os.path.abspath(RENDER))}
    except Exception as ex:  # noqa: BLE001 - a render failure (device, memory) must not hide the checks
        W.append("review renders failed: %s" % ex)
finish()
