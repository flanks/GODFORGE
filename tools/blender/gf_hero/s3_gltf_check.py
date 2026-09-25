"""Stage 3, step 5: export the rigged hero to a scratch GLB and check the skeleton contract in glTF (headless Blender).

  blender -b -P tools/blender/gf_hero/s3_gltf_check.py -- <key>

Exports GF_Hero_v1 + the skinned body parts (not the PREVIEW weapon) the way stage 5 will (glTF binary, +Y up, deform bones
only, 4 influences, no compression) to art/characters/<key>/work/gltf_check/<key>_rig.glb, reads the file back and checks:
  * the skin's joints are exactly the contract bones (+ per-hero x_ extras), the armature node is named GF_Hero_v1, the
    hierarchy (node parents) matches the contract, every mesh primitive has one JOINTS_0 / WEIGHTS_0 set (<= 4
    influences) and nothing is in extensionsRequired (bevy_gltf 0.20);
  * the IDENTITY ATTACH: for each socket, the glTF world frame of the socket node must equal C . grip . C^-1 (grip = the
    Blender grip frame at the socket, C = the +Y-up conversion). Proven with real data too: each signature-weapon
    gauntlet is exported on its own in its authoring frame (identity object transform, as the weapon GLB will be),
    its glTF vertices are pushed through the socket node's world matrix and compared with the Blender positions of the
    same gauntlet held on the socket by the rig (converted to +Y up).
Writes reports/stage3/gltf_check.json; exits 1 when a check fails.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Quaternion  # noqa: E402

import gf_hero_rig as R  # noqa: E402
from s2lib import get_co, log, rel, script_args, write_json  # noqa: E402
from s3lib import hero_paths  # noqa: E402

argv = script_args(__doc__)
if not argv:
    raise SystemExit(__doc__)
KEY = argv[0]
P = hero_paths(KEY)
OUTD = os.path.join(P["W"], "gltf_check")
os.makedirs(OUTD, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=P["rig"])
scene = bpy.context.scene
arm = bpy.data.objects[R.RIG_NAME]
if arm.animation_data:
    arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.rotation_euler = (0, 0, 0)
    pb.location = (0, 0, 0)
bpy.context.view_layer.update()
parts = [o for o in scene.objects if o.type == "MESH" and o.parent == arm]
C = Matrix(R.SOCKET_TO_GRIP)            # (x, y, z) -> (x, z, -y): the glTF +Y-up conversion
report = {"hero": KEY, "file": None, "checks": {}}
fails = []


def export(objs, path, skins=True):
    for o in scene.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
        export_texcoords=True, export_normals=True, export_tangents=True, export_materials="EXPORT",
        export_skins=skins, export_influence_nb=4, export_all_influences=False, export_def_bones=True,
        export_rest_position_armature=True, export_animations=False, export_cameras=False, export_lights=False,
        export_extras=False)


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
    stride = bv.get("byteStride", 0)
    itemsize = np.dtype(comp).itemsize * n
    if stride and stride != itemsize:
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * a["count"], offset=start).reshape(a["count"], stride)[:, :itemsize]
        return np.frombuffer(raw.tobytes(), dtype=comp).reshape(a["count"], n)
    return np.frombuffer(binary, dtype=comp, count=a["count"] * n, offset=start).reshape(a["count"], n)


def node_local(n):
    if "matrix" in n:
        return Matrix(np.array(n["matrix"]).reshape(4, 4).T.tolist())
    t = Matrix.Translation(n.get("translation", (0, 0, 0)))
    q = n.get("rotation", (0, 0, 0, 1))
    r = Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4()
    s = Matrix.Diagonal((*n.get("scale", (1, 1, 1)), 1.0))
    return t @ r @ s


# ---- 1. the hero ----------------------------------------------------------------------------------------------------------
glb = os.path.join(OUTD, "%s_rig.glb" % KEY)
export([arm] + parts, glb)
report["file"] = rel(glb) + " (local scratch)"
js, binary = read_glb(glb)
nodes = js["nodes"]
names = [n.get("name", "") for n in nodes]
parent = {}
for i, n in enumerate(nodes):
    for c in n.get("children", []):
        parent[c] = i
skin = js["skins"][0]
joints = [names[j] for j in skin["joints"]]
expected = R.contract_bone_names() + [b.name for b in arm.data.bones if b.name.startswith(R.EXTRA_PREFIX)]
report["checks"]["joints"] = {"count": len(joints), "missing": [b for b in expected if b not in joints],
                              "unexpected": [j for j in joints if j not in expected]}
if report["checks"]["joints"]["missing"] or report["checks"]["joints"]["unexpected"]:
    fails.append("skin joints differ from the contract")
par_bad = []
for b, p in R.contract_parents().items():
    i = names.index(b)
    pn = names[parent[i]] if i in parent else None
    want = p if p is not None else R.RIG_NAME
    if pn != want:
        par_bad.append("%s parent %s (want %s)" % (b, pn, want))
report["checks"]["hierarchy"] = {"armature_node": R.RIG_NAME in names, "wrong_parents": par_bad}
if par_bad or R.RIG_NAME not in names:
    fails.append("glTF hierarchy / armature node name")
prims = []
for mi, m in enumerate(js["meshes"]):
    for p in m["primitives"]:
        at = p["attributes"]
        prims.append({"mesh": m.get("name"), "JOINTS_0": "JOINTS_0" in at, "WEIGHTS_0": "WEIGHTS_0" in at,
                      "extra_sets": [k for k in at if k in ("JOINTS_1", "WEIGHTS_1")]})
report["checks"]["primitives"] = prims
if any(not (p["JOINTS_0"] and p["WEIGHTS_0"]) or p["extra_sets"] for p in prims):
    fails.append("a primitive lacks JOINTS_0/WEIGHTS_0 or has more than 4 influences")
report["checks"]["extensionsRequired"] = js.get("extensionsRequired", [])
if js.get("extensionsRequired"):
    fails.append("extensionsRequired is not empty")
# weights sum to 1 in the file
wsum_err = 0.0
for m in js["meshes"]:
    for p in m["primitives"]:
        w = accessor(js, binary, p["attributes"]["WEIGHTS_0"]).astype(np.float64)
        if js["accessors"][p["attributes"]["WEIGHTS_0"]]["componentType"] != 5126:
            w = w / 255.0 if w.max() > 1.5 else w
        wsum_err = max(wsum_err, float(np.abs(w.sum(axis=1) - 1).max()))
report["checks"]["weights_sum_max_error"] = wsum_err
if wsum_err > 2e-3:
    fails.append("exported weights do not sum to 1")


def world(i):
    m = node_local(nodes[i])
    while i in parent:
        i = parent[i]
        m = node_local(nodes[i]) @ m
    return m


sock = {}
for s in R.SOCKET_NAMES:
    G = world(names.index(s))
    B = C @ R.grip_matrix(arm, s, pose=False) @ C.inverted()
    err = max(abs(a - b) for ra, rb in zip(G, B) for a, b in zip(ra, rb))
    sock[s] = {"gltf_world": [[round(v, 5) for v in r] for r in G], "max_abs_vs_grip_frame": err}
    if err > 1e-4:
        fails.append("socket %s frame in glTF differs from the grip frame (%.2e)" % (s, err))
report["checks"]["socket_frames"] = sock
log("sockets in glTF vs the grip frame:", {s: "%.1e" % v["max_abs_vs_grip_frame"] for s, v in sock.items()})

# ---- 2. the real weapon: exported alone in its authoring frame, attached by identity --------------------------------------
wtest = {}
for ob in [o for o in scene.objects if o.name.startswith("PREVIEW_GAUNTLET_FIST_")]:
    side = ob.name[-1]
    held = get_co(ob.data) @ np.array(ob.matrix_world)[:3, :3].T + np.array(ob.matrix_world)[:3, 3]   # Blender, on the rig
    held_gltf = held @ np.array(C.to_3x3()).T
    tmp = bpy.data.objects.new("W_" + ob.data.name, ob.data)       # the weapon asset: identity transform = authoring frame
    scene.collection.objects.link(tmp)
    wglb = os.path.join(OUTD, "%s_alone.glb" % ob.data.name.lower())
    export([tmp], wglb, skins=False)
    wjs, wbin = read_glb(wglb)
    wn = wjs["nodes"][[i for i, n in enumerate(wjs["nodes"]) if "mesh" in n][0]]
    L = node_local(wn)
    pos = np.concatenate([accessor(wjs, wbin, p["attributes"]["POSITION"]) for p in wjs["meshes"][wn["mesh"]]["primitives"]]).astype(np.float64)
    G = np.array(world(names.index("weapon_" + side)) @ L)
    attached = pos @ G[:3, :3].T + G[:3, 3]
    # glTF splits vertices at UV seams: compare as point sets (each exported vertex to its nearest held vertex)
    from mathutils.kdtree import KDTree
    kd = KDTree(len(held_gltf))
    for i, p in enumerate(held_gltf):
        kd.insert(p, i)
    kd.balance()
    d = np.array([kd.find(p)[2] for p in attached])
    wtest[ob.data.name] = {"socket": "weapon_" + side, "weapon_node_local_is_identity": bool(np.allclose(np.array(L), np.eye(4), atol=1e-6)),
                           "vertices": int(len(attached)), "max_distance_m": float(d.max()), "mean_distance_m": float(d.mean())}
    bpy.data.objects.remove(tmp)
    if d.max() > 1e-4:
        fails.append("%s attached by identity at weapon_%s is off by %.2e m" % (ob.data.name, side, d.max()))
report["checks"]["weapon_identity_attach"] = wtest
log("weapon identity attach:", {k: "%.1e m" % v["max_distance_m"] for k, v in wtest.items()})
report["ok"] = not fails
report["failures"] = fails
write_json(os.path.join(P["S3"], "gltf_check.json"), report)
if fails:
    raise SystemExit("glTF check failed: " + "; ".join(fails))
log("glTF check OK")
