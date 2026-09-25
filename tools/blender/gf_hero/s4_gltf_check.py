"""Stage 4, step 4: export the hero with every clip to a scratch GLB and check the clips in glTF (headless Blender).

  blender -b -P tools/blender/gf_hero/s4_gltf_check.py -- <key>

Exports GF_Hero_v1 + the skinned parts + every <key>_ NLA track of production/<key>_anim.blend the way stage 5 will
(glTF binary, +Y up, deform bones only, NLA tracks as animations, sampled every frame so the twist constraints are
baked; no compression) to work/gltf_check/<key>_anim.glb, reads it back and checks:
  * one glTF animation per clip, named exactly as reports/anim/clips.json says (<key>_<clip>[@loop]); nothing else
    (the GF_ValidationPoses track is left out);
  * each animation's time range is frames / 30 s, sampled at 30 fps;
  * in place: the root joint never moves or turns in any clip; only the pelvis translates; sockets never change;
  * loops: every channel's last sample equals its first;
  * the twist bones carry the sampled Copy Rotation (they move wherever a hand twists);
  * nothing in extensionsRequired (bevy_gltf 0.20).
Writes reports/anim/gltf_check.json; exits 1 when a check fails.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import log, rel, script_args, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
P = hero_paths(KEY)
A = P["A"]
OUTD = os.path.join(P["W"], "gltf_check")
os.makedirs(OUTD, exist_ok=True)
MAN = json.load(open(os.path.join(A, "reports", "anim", "clips.json"), encoding="utf-8"))
bpy.ops.wm.open_mainfile(filepath=os.path.join(A, "production", "%s_anim.blend" % KEY))
scene = bpy.context.scene
scene.render.fps = 30
arm = bpy.data.objects[R.RIG_NAME]
arm.animation_data.action = None
for tr in list(arm.animation_data.nla_tracks):      # the exporter ignores mute: keep only this hero's clips (in memory)
    if not tr.name.startswith(KEY + "_"):
        arm.animation_data.nla_tracks.remove(tr)
    else:
        tr.mute = False
for pb in arm.pose.bones:
    pb.rotation_euler = (0, 0, 0)
    pb.location = (0, 0, 0)
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm]
for o in scene.objects:
    o.select_set(False)
for o in [arm] + parts:
    o.hide_set(False)
    o.select_set(True)
bpy.context.view_layer.objects.active = arm
glb = os.path.join(OUTD, "%s_anim.glb" % KEY)
bpy.ops.export_scene.gltf(
    filepath=glb, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
    export_texcoords=True, export_normals=True, export_tangents=True, export_materials="EXPORT",
    export_skins=True, export_influence_nb=4, export_all_influences=False, export_def_bones=True,
    export_rest_position_armature=True, export_animations=True, export_animation_mode="NLA_TRACKS",
    export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=False,
    export_anim_single_armature=True, export_cameras=False, export_lights=False, export_extras=False)


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    clen = struct.unpack("<I", data[12:16])[0]
    js = json.loads(data[20:20 + clen])
    off = 20 + clen
    blen = struct.unpack("<I", data[off:off + 4])[0]
    return js, data[off + 8:off + 8 + blen]


def accessor(js, binary, idx):
    a = js["accessors"][idx]
    bv = js["bufferViews"][a["bufferView"]]
    comp = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[a["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(binary, dtype=comp, count=a["count"] * n, offset=start).reshape(a["count"], n).astype(np.float64)


js, binary = read_glb(glb)
names = [n.get("name", "") for n in js["nodes"]]
anims = {a["name"]: a for a in js.get("animations", [])}
expected = {info["action"]: (name, info) for name, info in MAN["clips"].items()}
fails = []
rep = {"hero": KEY, "file": rel(glb) + " (local scratch)", "bytes": os.path.getsize(glb),
       "extensionsRequired": js.get("extensionsRequired", []), "animations": len(anims), "clips": {}}
if rep["extensionsRequired"]:
    fails.append("extensionsRequired: %s" % rep["extensionsRequired"])
missing = sorted(set(expected) - set(anims))
extra = sorted(set(anims) - set(expected))
rep["missing"], rep["unexpected"] = missing, extra
if missing or extra:
    fails.append("animations differ from clips.json: missing %s, unexpected %s" % (missing, extra))
socks = set(R.SOCKET_NAMES)
twist = set(R.twist_bone_names())
for aname, a in sorted(anims.items()):
    if aname not in expected:
        continue
    clip, info = expected[aname]
    r = {"channels": len(a["channels"])}
    tmax = 0.0
    nsamp = 0
    moving_root = False
    moving_socket = []
    translating = set()
    loop_err = 0.0
    twist_moves = False
    for ch in a["channels"]:
        node = names[ch["target"]["node"]]
        path = ch["target"]["path"]
        s = a["samplers"][ch["sampler"]]
        t = accessor(js, binary, s["input"])[:, 0]
        v = accessor(js, binary, s["output"])
        tmax = max(tmax, float(t.max()))
        nsamp = max(nsamp, len(t))
        span = float(np.abs(v - v[0]).max())
        if node == "root" and span > 1e-6:
            moving_root = True
        if node in socks and span > 1e-6:
            moving_socket.append(node)
        if path == "translation" and span > 1e-6:
            translating.add(node)
        if node in twist and path == "rotation" and span > 1e-4:
            twist_moves = True
        if info["loop"]:
            d = np.abs(v[-1] - v[0])
            if path == "rotation" and float(np.dot(v[-1], v[0])) < 0:
                d = np.abs(v[-1] + v[0])
            loop_err = max(loop_err, float(d.max()))
    want = info["frames"] / 30.0
    r.update({"duration_s": round(tmax, 5), "samples": nsamp, "root_moves": moving_root, "sockets_move": moving_socket,
              "translating_nodes": sorted(translating), "twist_bones_move": twist_moves})
    if info["loop"]:
        r["loop_first_last_max_diff"] = loop_err
        if loop_err > 1e-4:
            fails.append("%s: loop first/last differ by %.2e" % (aname, loop_err))
    if abs(tmax - want) > 1e-3 or nsamp != info["frames"] + 1:
        fails.append("%s: %.4f s / %d samples, expected %.4f s / %d" % (aname, tmax, nsamp, want, info["frames"] + 1))
    if moving_root:
        fails.append("%s: the root joint moves (clips are in place)" % aname)
    if moving_socket:
        fails.append("%s: sockets are animated: %s" % (aname, moving_socket))
    if translating - {"pelvis"}:
        fails.append("%s: bones other than the pelvis translate: %s" % (aname, sorted(translating - {"pelvis"})))
    rep["clips"][aname] = r
rep["twist_bones_animated_in"] = sum(1 for r in rep["clips"].values() if r["twist_bones_move"])
rep["failures"] = fails
rep["ok"] = not fails
write_json(os.path.join(A, "reports", "anim", "gltf_check.json"), rep)
log("glTF: %d animations, %.1f MB, %d failures" % (len(anims), rep["bytes"] / 1e6, len(fails)))
for f in fails:
    log("FAIL", f)
if fails:
    raise SystemExit(1)
