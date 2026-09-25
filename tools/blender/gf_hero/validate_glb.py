"""Validate shipped GODFORGE hero GLBs against the GF_Hero_v1 contract (standard library only; CI and stage 5).

  python tools/blender/gf_hero/validate_glb.py assets/models/characters/brax.glb [more.glb ...]
         [--json <report.json>] [--blender <blender exe>] [--weapon <weapon.glb>] [--no-meta] [--quiet]

The stage-5 gate (docs/ART_PIPELINE.md section 5, docs/art/GF_HERO_SKELETON.md). Every problem below is an ERROR (exit 1);
warnings never fail. What bevy_gltf 0.20 (the client enables only bevy/3d + bevy/png) needs is checked as well as the
contract:
  * container: binary glTF 2.0, JSON + BIN chunks, header length = file size, file <= 20 MB; nothing in
    extensionsRequired that bevy_gltf 0.20 cannot load, no Draco / meshopt / quantisation at all;
  * naming: file stem = hero key (lower_snake_case), one scene whose single root node is the armature GF_Hero_v1, every
    node named and unique (Bevy builds AnimationTargetIds from name paths; an unnamed node drops its animation);
  * skeleton: one skin whose joints are exactly the GF_Hero_v1 contract bones (+ per-hero x_ extras), parented as the
    contract says (root under GF_Hero_v1), <= 256 joints, inverse bind matrices consistent with the node rest pose;
  * sockets: weapon_R / weapon_L / head_top / chest_sigil present, parented right, never weighted, never animated, their
    rest frames sane (T-pose grips along +-X with the back of the hand up, the chest facing glTF +Z) and equal to the
    hero's committed landmark file when it is there;
  * skinning: every primitive triangles with POSITION / NORMAL / TANGENT / TEXCOORD_0 / JOINTS_0 / WEIGHTS_0, no second
    influence set (<= 4 influences), no COLOR_n (Bevy multiplies the base colour by COLOR_0), every vertex weighted with
    weights summing to 1, no weight on root or a socket, joint indices in range;
  * budget: <= 25,000 triangles for the hero body set (< 15,000 is a warning), textures embedded PNG <= 2048 px
    (power of two, >= 256 px expected), every material with base colour + emissive + normal textures;
  * clips: the animation set of tools/blender/gf_hero/required_clips.json (the shared set, which must equal
    s4_contract.SHARED_CLIPS, + the hero's unique set) named <key>_<clip>[@loop] with the right loop suffix, no
    badly named or duplicate animation; each clip sampled at 30 fps from t = 0, in place (root never moves, only the
    pelvis translates, no bone scales, sockets untouched), loops closed (last sample = first);
  * rest shape: 1.8-2.5 m tall (2.0-2.3 expected), feet on y = 0, centred on the origin;
  * sidecar <stem>.meta.json (unless --no-meta): exists, names this file's sha256, tris, clip list and sockets;
  * --weapon <glb> (default: the sidecar's weapon.glb when that file exists): the weapon attached as an identity child
    of weapon_R (its offhand node on weapon_L) encloses each hand in the rest pose;
  * --blender <exe>: also runs tools/blender/gf_hero/smoke_import.py in a fresh headless Blender (re-import, bone and
    socket names, every clip played one frame and compared with this file's own forward kinematics).
Pure standard library; smoke_import.py and export_glb.py import the reader and the forward kinematics from here.
"""
import array
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import gf_hero_rig as R  # noqa: E402  (plain data at import time; bpy only inside its build functions)
import s4_contract as SC  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SPEC_PATH = os.path.join(HERE, "required_clips.json")
MAX_BYTES = 20_000_000
MAX_TRIS, MIN_TRIS = 25_000, 15_000
MAX_TEX, MIN_TEX = 2048, 256
MAX_JOINTS = 256                     # bevy_mesh skinning limit
HEIGHT_OK, HEIGHT_HARD = (2.0, 2.3), (1.8, 2.5)
FPS = SC.FPS
# extensions bevy_gltf-0.20.0-rc.1 can load when REQUIRED (its src/lib.rs table; same list as tools/comfy/check_art.py)
BEVY_OK = {"KHR_lights_punctual", "KHR_materials_unlit", "KHR_texture_transform", "KHR_materials_transmission",
           "KHR_materials_ior", "KHR_materials_emissive_strength", "KHR_materials_specular",
           "KHR_materials_volume", "KHR_materials_clearcoat", "KHR_materials_anisotropy"}
BANNED = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_meshopt_compression", "KHR_mesh_quantization"}
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
STATUSES = {"ai_final_pending_user_approval", "final"}

COMP = {5120: ("b", 1, 127.0), 5121: ("B", 1, 255.0), 5122: ("h", 2, 32767.0), 5123: ("H", 2, 65535.0),
        5125: ("I", 4, None), 5126: ("f", 4, None)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


# ---- reading -----------------------------------------------------------------------------------------------------------

class Glb:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        self.bytes = len(self.data)
        self.sha256 = hashlib.sha256(self.data).hexdigest()
        self.problems = []
        d = self.data
        if len(d) < 20 or d[:4] != b"glTF":
            raise ValueError("not a binary glTF (no 'glTF' magic)")
        version, total = struct.unpack("<II", d[4:12])
        if version != 2:
            raise ValueError("glTF container version %d, expected 2" % version)
        if total != len(d):
            self.problems.append("header length %d != file size %d" % (total, len(d)))
        off, self.doc, self.bin = 12, None, b""
        first = True
        while off + 8 <= len(d):
            ln, typ = struct.unpack("<II", d[off:off + 8])
            chunk = d[off + 8:off + 8 + ln]
            if ln % 4:
                self.problems.append("chunk at %d is not 4-byte aligned (%d bytes)" % (off, ln))
            if typ == 0x4E4F534A:
                if not first:
                    self.problems.append("the JSON chunk is not the first chunk")
                self.doc = json.loads(chunk.decode("utf-8"))
            elif typ == 0x004E4942:
                self.bin = chunk
            first = False
            off += 8 + ln
        if self.doc is None:
            raise ValueError("no JSON chunk")
        self.nodes = self.doc.get("nodes", [])
        self.names = [n.get("name", "") for n in self.nodes]
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get("children", []):
                self.parent[c] = i
        self._acc = {}

    def accessor(self, idx):
        """Accessor values as a flat array plus the component count (normalized integers dequantised to floats)."""
        if idx in self._acc:
            return self._acc[idx]
        a = self.doc["accessors"][idx]
        fmt, size, norm = COMP[a["componentType"]]
        n = NCOMP[a["type"]]
        count = a["count"]
        if "bufferView" not in a:
            vals = array.array("f", [0.0] * (count * n))
        else:
            bv = self.doc["bufferViews"][a["bufferView"]]
            start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
            stride = bv.get("byteStride", 0) or size * n
            if stride == size * n:
                vals = array.array(fmt)
                vals.frombytes(self.bin[start:start + count * n * size])
            else:
                vals = array.array(fmt)
                for i in range(count):
                    s = start + i * stride
                    vals.frombytes(self.bin[s:s + n * size])
            if sys.byteorder != "little":
                vals.byteswap()
            if a.get("normalized") and norm:
                vals = array.array("f", [max(v / norm, -1.0) for v in vals])
        if a.get("sparse"):
            self.problems.append("accessor %d is sparse (not expected in a hero export)" % idx)
        self._acc[idx] = (vals, n)
        return vals, n

    def rows(self, idx):
        vals, n = self.accessor(idx)
        return [tuple(vals[i:i + n]) for i in range(0, len(vals), n)]

    def image_blob(self, im):
        if "bufferView" not in im:
            return None
        bv = self.doc["bufferViews"][im["bufferView"]]
        o = bv.get("byteOffset", 0)
        return self.bin[o:o + bv["byteLength"]]


def image_info(blob):
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", blob[16:24])
        return w, h, "png"
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            ln = struct.unpack(">H", blob[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xC3:
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return w, h, "jpeg"
            i += 2 + ln
        return 0, 0, "jpeg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return 0, 0, "webp"
    if blob[:12] == b"\xabKTX 20\xbb\r\n\x1a\n":
        return 0, 0, "ktx2"
    return 0, 0, "unknown"


# ---- math (row-major 4x4 lists, column vectors) ---------------------------------------------------------------------------

def quat_to_mat3(q):
    x, y, z, w = q
    ln = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / ln, y / ln, z / ln, w / ln
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def trs_matrix(t, q, s):
    r = quat_to_mat3(q)
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def node_trs(n):
    """(t, q, s) of a node; a node given by a matrix is decomposed (no shear expected)."""
    if "matrix" in n:
        m = n["matrix"]
        M = [[m[c * 4 + r] for c in range(4)] for r in range(4)]
        t = [M[0][3], M[1][3], M[2][3]]
        s = [math.sqrt(sum(M[r][c] ** 2 for r in range(3))) for c in range(3)]
        rm = [[M[r][c] / (s[c] or 1.0) for c in range(3)] for r in range(3)]
        return t, mat3_to_quat(rm), s
    return (list(n.get("translation", [0.0, 0.0, 0.0])), list(n.get("rotation", [0.0, 0.0, 0.0, 1.0])),
            list(n.get("scale", [1.0, 1.0, 1.0])))


def mat3_to_quat(m):
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        return [(m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s]
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        return [0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s]
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        return [(m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s]
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
    return [(m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s]


def mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def apply(m, p):
    return [m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3)]


def invert_rigid(m):
    """Inverse of a rotation(+uniform scale) + translation matrix."""
    s2 = sum(m[r][0] ** 2 for r in range(3)) or 1.0
    rt = [[m[c][r] / s2 for c in range(3)] for r in range(3)]
    t = [-sum(rt[r][k] * m[k][3] for k in range(3)) for r in range(3)]
    return [rt[r] + [t[r]] for r in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def max_abs_diff(a, b):
    return max(abs(a[r][c] - b[r][c]) for r in range(4) for c in range(4))


def world_matrices(g, trs_override=None):
    """World matrix of every node; trs_override {node: (t, q, s)} replaces node transforms (an animation sample)."""
    trs_override = trs_override or {}
    cache = {}

    def wm(i):
        if i in cache:
            return cache[i]
        t, q, s = trs_override.get(i) or node_trs(g.nodes[i])
        m = trs_matrix(t, q, s)
        if i in g.parent:
            m = mul(wm(g.parent[i]), m)
        cache[i] = m
        return m
    return [wm(i) for i in range(len(g.nodes))]


def _lerp(a, b, f):
    return [x + (y - x) * f for x, y in zip(a, b)]


def _slerp(a, b, f):
    d = sum(x * y for x, y in zip(a, b))
    if d < 0:
        b, d = [-v for v in b], -d
    if d > 0.9995:
        r = _lerp(a, b, f)
    else:
        th = math.acos(min(1.0, d))
        s = math.sin(th)
        wa, wb = math.sin((1 - f) * th) / s, math.sin(f * th) / s
        r = [wa * x + wb * y for x, y in zip(a, b)]
    ln = math.sqrt(sum(v * v for v in r)) or 1.0
    return [v / ln for v in r]


def channel_data(g, anim):
    """[(node, path, interpolation, times, values_rows)] of one animation."""
    out = []
    for ch in anim.get("channels", []):
        s = anim["samplers"][ch["sampler"]]
        interp = s.get("interpolation", "LINEAR")
        times = [v[0] for v in g.rows(s["input"])]
        vals = g.rows(s["output"])
        if interp == "CUBICSPLINE":
            vals = vals[1::3]
        out.append((ch["target"].get("node"), ch["target"]["path"], interp, times, vals))
    return out


def sample_animation(g, anim, t, chans=None):
    """{node: (t, q, s)} of every animated node at time t (LINEAR / STEP / CUBICSPLINE values), the rest elsewhere."""
    import bisect
    chans = chans if chans is not None else channel_data(g, anim)
    pose = {}
    for node, path, interp, times, vals in chans:
        if node is None or path not in ("translation", "rotation", "scale"):
            continue
        if node not in pose:
            pose[node] = [list(x) for x in node_trs(g.nodes[node])]
        if t <= times[0]:
            v = list(vals[0])
        elif t >= times[-1]:
            v = list(vals[-1])
        else:
            k = bisect.bisect_right(times, t) - 1
            f = (t - times[k]) / ((times[k + 1] - times[k]) or 1.0)
            if interp == "STEP" or f < 1e-9:
                v = list(vals[k])
            elif path == "rotation":
                v = _slerp(vals[k], vals[k + 1], f)
            else:
                v = _lerp(vals[k], vals[k + 1], f)
        pose[node][{"translation": 0, "rotation": 1, "scale": 2}[path]] = v
    return {k: tuple(v) for k, v in pose.items()}


# ---- helpers --------------------------------------------------------------------------------------------------------------

def load_spec():
    with open(SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


def spec_problems(spec):
    """required_clips.json against s4_contract.SHARED_CLIPS (the two must never drift)."""
    probs = []
    got = [(c["clip"], bool(c["loop"]), c.get("layer", "full")) for c in spec.get("shared", [])]
    if got != list(SC.SHARED_CLIPS):
        probs.append("required_clips.json 'shared' differs from s4_contract.SHARED_CLIPS")
    if spec.get("fps") != SC.FPS:
        probs.append("required_clips.json fps %s != %d" % (spec.get("fps"), SC.FPS))
    return probs


def required_clip_names(spec, key):
    """{animation name: (clip, loop)} a hero GLB must contain, or None when the hero has no block."""
    out = {}
    for c in spec.get("shared", []):
        out[SC.action_name(key, c["clip"], c["loop"])] = (c["clip"], bool(c["loop"]))
    uniq = spec.get("heroes", {}).get(key)
    if uniq is None:
        return None
    for c in uniq:
        out[SC.action_name(key, c["clip"], c["loop"])] = (c["clip"], bool(c["loop"]))
    return out


def load_landmarks(key):
    p = os.path.join(ROOT, "art", "characters", key, "work", "%s_landmarks.json" % key)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def relpath(path):
    """Repo-relative path with forward slashes (the absolute path when it lies outside the repo / on another drive)."""
    try:
        r = os.path.relpath(os.path.abspath(path), ROOT)
    except ValueError:
        return os.path.abspath(path).replace(os.sep, "/")
    return os.path.abspath(path).replace(os.sep, "/") if r.startswith("..") else r.replace(os.sep, "/")


def to_gltf(v):
    """Blender (x, y, z) -> glTF (x, z, -y)."""
    return [v[0], v[2], -v[1]]


def _norm(v):
    ln = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / ln for x in v]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def axis(m, k):
    return [m[0][k], m[1][k], m[2][k]]


# ---- the hero check -------------------------------------------------------------------------------------------------------

def validate_hero(path, meta="auto", weapon=None, spec=None):
    """Report dict {ok, errors, warnings, stats...} for one hero GLB. meta: "auto" (read <stem>.meta.json, error if
    missing), None (skip the sidecar), or a dict."""
    E, W = [], []
    key = os.path.splitext(os.path.basename(path))[0]
    rep = {"file": relpath(path), "key": key}
    try:
        g = Glb(path)
    except (OSError, ValueError, UnicodeDecodeError) as ex:
        rep.update(ok=False, errors=["cannot read %s: %s" % (path, ex)], warnings=[])
        return rep
    doc = g.doc
    E += ["container: %s" % p for p in g.problems]
    rep["bytes"], rep["sha256"] = g.bytes, g.sha256
    if g.bytes > MAX_BYTES:
        E.append("file is %.1f MB > 20 MB" % (g.bytes / 1e6))
    if doc.get("asset", {}).get("version") != "2.0":
        E.append("asset.version %r, expected '2.0'" % doc.get("asset", {}).get("version"))
    rep["generator"] = doc.get("asset", {}).get("generator")
    req, used = set(doc.get("extensionsRequired", [])), set(doc.get("extensionsUsed", []))
    rep["extensions_used"], rep["extensions_required"] = sorted(used), sorted(req)
    if req - BEVY_OK:
        E.append("extensionsRequired has %s, which bevy_gltf 0.20 cannot load" % sorted(req - BEVY_OK))
    if (req | used) & BANNED:
        E.append("compression / quantisation extensions %s (export uncompressed)" % sorted((req | used) & BANNED))
    if used - BEVY_OK - BANNED:
        W.append("extensionsUsed %s are ignored by bevy_gltf 0.20" % sorted(used - BEVY_OK - BANNED))
    if not KEY_RE.match(key):
        E.append("file stem %r is not a lower_snake_case hero key" % key)
    spec = spec or load_spec()
    E += spec_problems(spec)

    # -- scene / names --
    names = g.names
    scenes = doc.get("scenes", [])
    if not scenes:
        E.append("no scene (Bevy loads '#Scene0')")
    else:
        roots = scenes[doc.get("scene", 0)].get("nodes", [])
        rep["scene_roots"] = [names[i] for i in roots]
        if [names[i] for i in roots] != [R.RIG_NAME]:
            E.append("the scene's root nodes are %s; expected exactly the armature %s" % (rep["scene_roots"], R.RIG_NAME))
    unnamed = [i for i, n in enumerate(names) if not n]
    if unnamed:
        E.append("%d unnamed node(s) %s: Bevy drops animation under an unnamed node" % (len(unnamed), unnamed[:8]))
    dup = sorted({n for n in names if n and names.count(n) > 1})
    if dup:
        E.append("duplicate node names %s (animation target paths must be unique)" % dup)
    rep["nodes"] = len(names)

    # -- skeleton --
    skins = doc.get("skins", [])
    joints = []
    if len(skins) != 1:
        E.append("%d skins; a hero ships exactly one (GF_Hero_v1)" % len(skins))
    if skins:
        sk = skins[0]
        joints = list(sk["joints"])
        jn = [names[j] for j in joints]
        rep["joints"] = len(joints)
        if len(joints) > MAX_JOINTS:
            E.append("%d joints > %d (Bevy's skinning limit)" % (len(joints), MAX_JOINTS))
        contract = R.contract_bone_names()
        missing = [b for b in contract if b not in jn]
        extra = [b for b in jn if b not in contract]
        bad_extra = [b for b in extra if not b.startswith(R.EXTRA_PREFIX)]
        rep["extra_bones"] = [b for b in extra if b.startswith(R.EXTRA_PREFIX)]
        if missing:
            E.append("skin lacks contract bones %s" % missing)
        if bad_extra:
            E.append("skin has non-contract bones %s (per-hero bones are prefixed %s)" % (bad_extra, R.EXTRA_PREFIX))
        if len(set(jn)) != len(jn):
            E.append("duplicate joints in the skin")
        wrong_par = []
        for b, p in R.contract_parents().items():
            if b not in names:
                continue
            i = names.index(b)
            actual = names[g.parent[i]] if i in g.parent else None
            want = p if p is not None else R.RIG_NAME
            if actual != want:
                wrong_par.append("%s under %s (contract: %s)" % (b, actual, want))
        if wrong_par:
            E.append("skeleton parents break the contract: %s" % wrong_par[:10])
        for b in rep["extra_bones"]:
            i = names.index(b)
            if i in g.parent and names[g.parent[i]] not in jn:
                E.append("extra bone %s hangs off a non-joint node" % b)
        if R.RIG_NAME not in names:
            E.append("no armature node named %s" % R.RIG_NAME)
        # bind pose: world(joint) @ IBM == world(skinned mesh node) at rest
        wm = world_matrices(g)
        mesh_nodes = [i for i, n in enumerate(g.nodes) if "mesh" in n]
        skinned = [i for i in mesh_nodes if g.nodes[i].get("skin") == 0]
        unskinned = [names[i] for i in mesh_nodes if "skin" not in g.nodes[i]]
        if unskinned:
            E.append("mesh nodes without a skin: %s (the hero body set is skinned)" % unskinned)
        if "inverseBindMatrices" not in sk:
            E.append("skin has no inverseBindMatrices")
        else:
            ibm = g.rows(sk["inverseBindMatrices"])
            ref = wm[skinned[0]] if skinned else [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
            err = 0.0
            for k, j in enumerate(joints):
                m = ibm[k]
                M = [[m[c * 4 + r] for c in range(4)] for r in range(4)]
                err = max(err, max_abs_diff(mul(wm[j], M), ref))
            rep["bind_pose_max_error"] = err
            if err > 1e-4:
                E.append("inverse bind matrices do not match the node rest pose (max error %.2e)" % err)
            if skinned and max_abs_diff(ref, [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]) > 1e-6:
                W.append("the skinned mesh node is not at the identity (Bevy ignores a skinned mesh's own transform)")
        # sockets
        socks = {}
        lm = load_landmarks(key)
        for s in R.SOCKET_NAMES:
            if s not in names:
                E.append("socket %s missing" % s)
                continue
            m = wm[names.index(s)]
            socks[s] = {"parent": dict((b[0], b[1]) for b in R.SOCKET_BONES)[s],
                        "translation": [round(m[r][3], 5) for r in range(3)],
                        "forward": [round(-m[r][2], 5) for r in range(3)],
                        "up": [round(m[r][1], 5) for r in range(3)]}
            if lm and s in lm.get("sockets", {}):
                o, _x, f, u = R.socket_axes(lm["sockets"][s])
                d = max(max(abs(a - b) for a, b in zip(socks[s]["translation"], to_gltf(o))),
                        max(abs(a - b) for a, b in zip(socks[s]["forward"], to_gltf(f))),
                        max(abs(a - b) for a, b in zip(socks[s]["up"], to_gltf(u))))
                socks[s]["vs_landmarks"] = round(d, 7)
                if d > 1e-4:
                    E.append("socket %s differs from the landmark file by %.2e" % (s, d))
        rep["sockets"] = socks
        if "weapon_L" in socks and _dot(socks["weapon_L"]["forward"], [1, 0, 0]) < 0.9:
            E.append("weapon_L forward %s: the T-pose left fingers point along glTF +X" % socks["weapon_L"]["forward"])
        if "weapon_R" in socks and _dot(socks["weapon_R"]["forward"], [-1, 0, 0]) < 0.9:
            E.append("weapon_R forward %s: the T-pose right fingers point along glTF -X" % socks["weapon_R"]["forward"])
        for s in ("weapon_L", "weapon_R"):
            if s in socks and _dot(socks[s]["up"], [0, 1, 0]) < 0.9:
                E.append("%s up %s: the back of the hand faces up in the T-pose" % (s, socks[s]["up"]))
            h = "hand_" + s[-1]
            if s in socks and h in names and "middle_01_" + s[-1] in names:
                w = [wm[names.index(h)][r][3] for r in range(3)]
                k = [wm[names.index("middle_01_" + s[-1])][r][3] for r in range(3)]
                hl = math.dist(w, k)
                if math.dist(socks[s]["translation"], w) > 1.5 * hl + 0.05:
                    E.append("%s is not on the hand" % s)
        if "chest_sigil" in socks and _dot(socks["chest_sigil"]["forward"], [0, 0, 1]) < 0.9:
            E.append("chest_sigil faces %s: the hero must face glTF +Z" % socks["chest_sigil"]["forward"])
        if "head_top" in socks and _dot(socks["head_top"]["up"], [0, 1, 0]) < 0.9:
            E.append("head_top up %s is not glTF +Y" % socks["head_top"]["up"])

    # -- meshes, skinning, budget --
    no_weight = set(R.non_weight_bone_names())
    tris = 0
    vstats = {"vertices": 0, "unweighted": 0, "over_4": 0, "not_normalized": 0, "on_non_weight_bones": 0,
              "bad_joint_index": 0, "weight_sum_max_error": 0.0}
    lo, hi = [1e9] * 3, [-1e9] * 3
    used_materials = set()
    for mi, mesh in enumerate(doc.get("meshes", [])):
        for pi, p in enumerate(mesh.get("primitives", [])):
            where = "mesh %s primitive %d" % (mesh.get("name", mi), pi)
            at = p.get("attributes", {})
            if p.get("mode", 4) != 4:
                E.append("%s: mode %s, expected triangles" % (where, p.get("mode")))
            for need in ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0", "JOINTS_0", "WEIGHTS_0"):
                if need not in at:
                    E.append("%s: no %s" % (where, need))
            if "JOINTS_1" in at or "WEIGHTS_1" in at:
                E.append("%s: a second JOINTS/WEIGHTS set (more than 4 influences)" % where)
            colours = sorted(k for k in at if k.startswith("COLOR_"))
            if colours:
                E.append("%s: vertex colours %s (Bevy multiplies the base colour by COLOR_0; export without them)" % (where, colours))
            if p.get("targets"):
                W.append("%s: %d morph targets (none expected)" % (where, len(p["targets"])))
            if "material" in p:
                used_materials.add(p["material"])
            else:
                E.append("%s: no material" % where)
            if "POSITION" in at:
                acc = doc["accessors"][at["POSITION"]]
                if "min" not in acc or "max" not in acc:
                    E.append("%s: POSITION has no min/max" % where)
                else:
                    lo = [min(lo[k], acc["min"][k]) for k in range(3)]
                    hi = [max(hi[k], acc["max"][k]) for k in range(3)]
                n_idx = doc["accessors"][p["indices"]]["count"] if "indices" in p else acc["count"]
                tris += n_idx // 3
            if "JOINTS_0" in at and "WEIGHTS_0" in at and joints:
                jv, _ = g.accessor(at["JOINTS_0"])
                wv, _ = g.accessor(at["WEIGHTS_0"])
                wtype = doc["accessors"][at["WEIGHTS_0"]]["componentType"]
                tol = 2e-3 if wtype == 5126 else 4.0 / (255.0 if wtype == 5121 else 65535.0)
                nv = len(wv) // 4
                vstats["vertices"] += nv
                nw_idx = {k for k, j in enumerate(joints) if names[j] in no_weight}
                for v in range(nv):
                    ws = wv[v * 4:v * 4 + 4]
                    js = jv[v * 4:v * 4 + 4]
                    tot = ws[0] + ws[1] + ws[2] + ws[3]
                    nz = [k for k in range(4) if ws[k] > 0.0]
                    if not nz:
                        vstats["unweighted"] += 1
                        continue
                    e = abs(tot - 1.0)
                    if e > vstats["weight_sum_max_error"]:
                        vstats["weight_sum_max_error"] = e
                    if e > tol:
                        vstats["not_normalized"] += 1
                    for k in nz:
                        if js[k] >= len(joints):
                            vstats["bad_joint_index"] += 1
                        elif js[k] in nw_idx and ws[k] > 1e-3:
                            vstats["on_non_weight_bones"] += 1
    rep["tris"] = tris
    rep["skin"] = vstats
    if vstats["unweighted"]:
        E.append("%d unweighted vertices" % vstats["unweighted"])
    if vstats["not_normalized"]:
        E.append("%d vertices whose weights do not sum to 1 (max error %.4f)" % (vstats["not_normalized"], vstats["weight_sum_max_error"]))
    if vstats["on_non_weight_bones"]:
        E.append("%d vertices weighted to root or a socket" % vstats["on_non_weight_bones"])
    if vstats["bad_joint_index"]:
        E.append("%d influences reference a joint index outside the skin" % vstats["bad_joint_index"])
    if tris > MAX_TRIS:
        E.append("%d triangles > the hero budget %d" % (tris, MAX_TRIS))
    elif tris < MIN_TRIS:
        W.append("%d triangles < %d (the hero budget is 15-25k; unfinished?)" % (tris, MIN_TRIS))
    if hi[0] > -1e8:
        h = hi[1] - lo[1]
        rep["bounds_m"] = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}
        rep["height_m"] = round(h, 4)
        if not HEIGHT_HARD[0] <= h <= HEIGHT_HARD[1]:
            E.append("rest height %.2f m outside %s" % (h, HEIGHT_HARD))
        elif not HEIGHT_OK[0] <= h <= HEIGHT_OK[1]:
            W.append("rest height %.2f m outside the hero range %s" % (h, HEIGHT_OK))
        if not -0.02 <= lo[1] <= 0.03:
            E.append("feet at y = %.3f m; the origin is on the ground (y = 0)" % lo[1])
        if abs((lo[0] + hi[0]) / 2) > 0.15 or abs((lo[2] + hi[2]) / 2) > 0.2:
            E.append("the rest shape is not centred on the origin (x %.2f, z %.2f)" % ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2))

    # -- materials / textures --
    mats = doc.get("materials", [])
    rep["materials"] = []
    tex_roles = {}
    for i in sorted(used_materials):
        m = mats[i]
        pbr = m.get("pbrMetallicRoughness", {})
        roles = {"base_color": pbr.get("baseColorTexture"), "emissive": m.get("emissiveTexture"),
                 "normal": m.get("normalTexture")}
        rep["materials"].append({"name": m.get("name"), "double_sided": bool(m.get("doubleSided")),
                                 "emissive_strength": m.get("extensions", {}).get("KHR_materials_emissive_strength", {}).get("emissiveStrength", 1.0),
                                 "textures": {k: v is not None for k, v in roles.items()}})
        for role, ref in roles.items():
            if ref is None:
                E.append("material %s has no %s texture" % (m.get("name"), role))
                continue
            if ref.get("texCoord", 0) != 0:
                E.append("material %s %s texture uses TEXCOORD_%d" % (m.get("name"), role, ref["texCoord"]))
            if role != "base_color" and "KHR_texture_transform" in ref.get("extensions", {}):
                W.append("KHR_texture_transform on the %s texture (Bevy applies it to base colour only)" % role)
            src = doc["textures"][ref["index"]].get("source")
            tex_roles.setdefault(src, role)
    texs = []
    for i, im in enumerate(doc.get("images", [])):
        blob = g.image_blob(im)
        if blob is None:
            E.append("image %s is not embedded (uri %r)" % (im.get("name", i), im.get("uri")))
            continue
        w, h, fmt = image_info(blob)
        texs.append({"name": im.get("name", "image_%d" % i), "role": tex_roles.get(i, "unused"), "px": [w, h],
                     "format": fmt, "bytes": len(blob)})
        if fmt != "png":
            E.append("image %s is %s; the client enables only bevy/png" % (im.get("name", i), fmt))
        if max(w, h) > MAX_TEX:
            E.append("texture %s is %dx%d > %d px" % (im.get("name"), w, h, MAX_TEX))
        if w and min(w, h) < MIN_TEX:
            W.append("texture %s is only %dx%d" % (im.get("name"), w, h))
        if w & (w - 1) or h & (h - 1):
            W.append("texture %s is not a power of two (%dx%d)" % (im.get("name"), w, h))
        if i not in tex_roles:
            W.append("image %s is not used by a material" % im.get("name"))
    rep["textures"] = texs

    # -- clips --
    anims = doc.get("animations", [])
    an = [a.get("name", "") for a in anims]
    rep["clips"] = an
    req = required_clip_names(spec, key)
    clip_re = re.compile(r"^%s_[a-z][a-z0-9_]*(@loop)?$" % re.escape(key))
    for a in an:
        if not clip_re.match(a):
            E.append("animation %r is not named %s_<clip>[@loop] (lower_snake_case)" % (a, key))
    if len(set(an)) != len(an):
        E.append("duplicate animation names %s" % sorted({a for a in an if an.count(a) > 1}))
    if req is None:
        E.append("required_clips.json has no block for hero %r (add its unique clips)" % key)
    else:
        n_uniq = len(spec["heroes"][key])
        lo_u, hi_u = spec.get("unique_count", [SC.UNIQUE_MIN, SC.UNIQUE_MAX])
        if not lo_u <= n_uniq <= hi_u:
            E.append("required_clips.json lists %d unique clips for %s (the pipeline wants %d-%d)" % (n_uniq, key, lo_u, hi_u))
        for name, (clip, loop) in req.items():
            if name in an:
                continue
            other = SC.action_name(key, clip, not loop)
            if other in an:
                E.append("clip %s is %s: the loop suffix is wrong (contract: %s)" % (clip, other, name))
            else:
                E.append("required clip %s is missing" % name)
        extra = [a for a in an if a not in req]
        if extra:
            W.append("animations not in required_clips.json: %s" % extra)
    meta_d = None
    if meta == "auto":
        mp = os.path.splitext(path)[0] + ".meta.json"
        if os.path.isfile(mp):
            with open(mp, encoding="utf-8") as f:
                meta_d = json.load(f)
        else:
            E.append("no sidecar %s (clip events, sockets and status live there)" % os.path.basename(mp))
    elif isinstance(meta, dict):
        meta_d = meta
    info = (meta_d or {}).get("clip_info", {})
    jset = set(joints)
    socket_idx = {names.index(s) for s in R.SOCKET_NAMES if s in names}
    root_idx = names.index("root") if "root" in names else None
    pelvis_idx = names.index("pelvis") if "pelvis" in names else None
    clip_rep = {}
    for a, name in zip(anims, an):
        cr = {"channels": len(a.get("channels", []))}
        errs = []
        chans = channel_data(g, a)
        tmax, t0, nsamp = 0.0, 1e9, 0
        spacing_bad = False
        animated = set()
        loop_err = 0.0
        for node, path, interp, times, vals in chans:
            if node is None or node not in jset:
                errs.append("channel on %s, which is not a joint" % (names[node] if node is not None else None))
                continue
            if path == "weights":
                errs.append("morph-weight channel")
                continue
            if interp not in ("LINEAR", "STEP", "CUBICSPLINE"):
                errs.append("interpolation %s" % interp)
            animated.add(node)
            tmax, t0, nsamp = max(tmax, times[-1]), min(t0, times[0]), max(nsamp, len(times))
            for k in range(1, len(times)):
                if abs((times[k] - times[k - 1]) * FPS - 1.0) > 1e-3:
                    spacing_bad = True
                    break
            rest = node_trs(g.nodes[node])[{"translation": 0, "rotation": 1, "scale": 2}[path]]
            if path == "rotation":                   # component-wise, sign-insensitive: 1e-5 ~ 0.001 deg
                dev = max(min(max(abs(x - y) for x, y in zip(v, rest)), max(abs(x + y) for x, y in zip(v, rest)))
                          for v in vals)
            else:
                dev = max(max(abs(x - y) for x, y in zip(v, rest)) for v in vals)
            dev_tol = 1e-5
            nm = names[node]
            if node == root_idx and dev > dev_tol:
                errs.append("the root moves (clips are in place)")
            if node in socket_idx and dev > dev_tol:
                errs.append("socket %s is animated" % nm)
            if path == "translation" and node != pelvis_idx and dev > dev_tol:
                errs.append("%s translates (only the pelvis may)" % nm)
            if path == "scale" and max(max(abs(x - 1.0) for x in v) for v in vals) > 1e-4:
                errs.append("%s scales" % nm)
            if name.endswith("@loop"):
                d = max(abs(x - y) for x, y in zip(vals[-1], vals[0]))
                if path == "rotation":
                    d = min(d, max(abs(x + y) for x, y in zip(vals[-1], vals[0])))
                loop_err = max(loop_err, d)
        if not chans:
            errs.append("no channels")
        if t0 > 1e-4 and chans:
            errs.append("starts at t = %.4f s, not 0" % t0)
        if spacing_bad:
            errs.append("not sampled at %d fps" % FPS)
        cr.update(duration_s=round(tmax, 5), samples=nsamp, animated_joints=len(animated))
        if name.endswith("@loop"):
            cr["loop_first_last_max_diff"] = loop_err
            if loop_err > 1e-4:
                errs.append("loop not closed (first/last differ by %.2e)" % loop_err)
        ci = info.get(name)
        if ci:
            want = ci["frames"] / float(FPS)
            if abs(tmax - want) > 1e-3 or nsamp != ci["frames"] + 1:
                errs.append("%.4f s / %d samples, the sidecar says %d frames" % (tmax, nsamp, ci["frames"]))
        core_missing = [b for b in R.core_bone_names() if b != "root" and b in names and names.index(b) not in animated]
        if core_missing:
            W.append("%s leaves core bones unkeyed (blending would keep the previous clip's pose): %s" % (name, core_missing[:6]))
        for e in sorted(set(errs)):
            E.append("%s: %s" % (name, e))
        clip_rep[name] = cr
    rep["clip_checks"] = clip_rep

    # -- sidecar --
    if meta_d is not None:
        rep["sidecar"] = "checked"
        if meta_d.get("glb_sha256") != g.sha256:
            E.append("sidecar glb_sha256 does not match the file (re-run the export)")
        if meta_d.get("tris") != tris:
            E.append("sidecar tris %s != %d" % (meta_d.get("tris"), tris))
        if sorted(meta_d.get("clips", [])) != sorted(an):
            E.append("sidecar clip list differs from the animations")
        missing_info = [a for a in an if a not in info]
        if missing_info:
            E.append("sidecar clip_info lacks %s" % missing_info[:6])
        if sorted(meta_d.get("sockets", {})) != sorted(R.SOCKET_NAMES):
            E.append("sidecar sockets %s != %s" % (sorted(meta_d.get("sockets", {})), sorted(R.SOCKET_NAMES)))
        if meta_d.get("skeleton") != "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION):
            E.append("sidecar skeleton %r" % meta_d.get("skeleton"))
        if meta_d.get("status") not in STATUSES:
            E.append("sidecar status %r not in %s" % (meta_d.get("status"), sorted(STATUSES)))
        wglb = (meta_d.get("weapon") or {}).get("glb")
        if weapon is None and wglb and os.path.isfile(os.path.join(ROOT, wglb)):
            weapon = os.path.join(ROOT, wglb)

    # -- weapon attach --
    if weapon and skins:
        rep["weapon_attach"] = attach_check(g, weapon, E, W)

    rep["errors"], rep["warnings"] = E, W
    rep["ok"] = not E
    return rep


def weapon_layout(wg):
    """The sleeve / chassis weapon GLB, as the client attaches it: {"R": [(node, matrix)], "L": [...]} where matrix maps
    the mesh's positions into its socket's frame (the root is an identity child of weapon_R; the offhand node is
    re-parented to weapon_L with an identity transform)."""
    names = wg.names
    wm = world_matrices(wg)
    off = names.index("offhand") if "offhand" in names else None
    under_off = set()
    if off is not None:
        stack = [off]
        while stack:
            i = stack.pop()
            under_off.add(i)
            stack += wg.nodes[i].get("children", [])
    out = {"R": [], "L": []}
    for i, n in enumerate(wg.nodes):
        if "mesh" not in n:
            continue
        if i in under_off:
            out["L"].append((i, mul(invert_rigid(wm[off]), wm[i])))
        else:
            out["R"].append((i, wm[i]))
    return out


def attach_check(g, weapon_path, E, W):
    """The weapon on the hero's sockets in the rest pose: every weapon mesh on a side must enclose that hand (the wrist,
    the palm centre and the middle knuckle inside its bounding box)."""
    r = {"weapon": relpath(weapon_path)}
    try:
        wg = Glb(weapon_path)
    except (OSError, ValueError) as ex:
        E.append("weapon %s unreadable: %s" % (weapon_path, ex))
        return r
    stem = os.path.splitext(os.path.basename(weapon_path))[0]
    if stem not in wg.names:
        E.append("weapon %s has no root node named %s" % (stem, stem))
    if "grip_R" not in wg.names:
        E.append("weapon %s has no grip_R" % stem)
    else:
        m = world_matrices(wg)[wg.names.index("grip_R")]
        if max_abs_diff(m, [[1.0 if a == b else 0.0 for b in range(4)] for a in range(4)]) > 1e-5:
            E.append("weapon %s grip_R is not the identity (the grip frame is the origin)" % stem)
    hw = world_matrices(g)
    names = g.names
    lay = weapon_layout(wg)
    r["meshes"] = {}
    for side, items in lay.items():
        sock = "weapon_" + side
        if sock not in names:
            continue
        S = hw[names.index(sock)]
        pts = {"wrist": [hw[names.index("hand_" + side)][k][3] for k in range(3)],
               "palm": [S[k][3] for k in range(3)],
               "knuckle": [hw[names.index("middle_01_" + side)][k][3] for k in range(3)]}
        for i, M in items:
            T = mul(S, M)
            lo, hi = [1e9] * 3, [-1e9] * 3
            for p in wg.doc["meshes"][wg.nodes[i]["mesh"]]["primitives"]:
                vals, n = wg.accessor(p["attributes"]["POSITION"])
                for k in range(0, len(vals), 3):
                    q = apply(T, vals[k:k + 3])
                    lo = [min(lo[a], q[a]) for a in range(3)]
                    hi = [max(hi[a], q[a]) for a in range(3)]
            inside = {k: all(lo[a] <= v[a] <= hi[a] for a in range(3)) for k, v in pts.items()}
            r["meshes"][wg.names[i]] = {"socket": sock, "encloses": inside}
            if not all(inside.values()):
                E.append("weapon mesh %s on %s does not enclose the hand (%s)" % (wg.names[i], sock, inside))
    if not lay["L"] and not lay["R"]:
        E.append("weapon %s has no meshes" % stem)
    return r


# ---- CLI ------------------------------------------------------------------------------------------------------------------

def run_blender_smoke(blender, glb, weapon):
    fd, tmp = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    cmd = [blender, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(HERE, "smoke_import.py"),
           "--", glb, "--json", tmp]
    if weapon:
        cmd += ["--weapon", weapon]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    try:
        with open(tmp, encoding="utf-8") as f:
            out = json.load(f)
    except (OSError, ValueError):
        out = {"ok": False, "errors": ["the Blender smoke test wrote no report (exit %d): %s" % (r.returncode, (r.stdout + r.stderr)[-1500:])]}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if r.returncode != 0 and out.get("ok"):
        out["ok"] = False
        out.setdefault("errors", []).append("Blender exited %d" % r.returncode)
    return out


def main(argv):
    opts, files, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--json", "--blender", "--weapon"):
            opts[a] = argv[i + 1] if i + 1 < len(argv) else None
            i += 2
            continue
        if a.startswith("--"):
            opts[a] = True
        else:
            files.append(a)
        i += 1
    if not files:
        print(__doc__)
        return 2

    def opt(name):
        return opts.get(name)
    blender = opt("--blender")
    weapon = opt("--weapon")
    quiet = "--quiet" in opts
    argv = list(opts)
    reports = {}
    ok = True
    for p in files:
        rep = validate_hero(p, meta=None if "--no-meta" in argv else "auto", weapon=weapon)
        if blender:
            wp = weapon or (os.path.join(ROOT, rep["weapon_attach"]["weapon"]) if rep.get("weapon_attach") else None)
            wp = wp if wp and os.path.isfile(wp) else None
            sm = run_blender_smoke(blender, p, wp)
            rep["blender_smoke"] = sm
            for e in sm.get("errors", []):
                rep["errors"].append("blender smoke: %s" % e)
            rep["ok"] = not rep["errors"]
        reports[rep["file"]] = rep
        ok = ok and rep["ok"]
        if not quiet:
            for w in rep.get("warnings", []):
                print("warning: %s: %s" % (rep["file"], w))
        for e in rep.get("errors", []):
            print("ERROR: %s: %s" % (rep["file"], e))
        print("[validate_glb] %s: %s, %s tris, %s joints, %d clip(s), %d texture(s), %.1f MB%s" % (
            rep["file"], "OK" if rep["ok"] else "FAILED", rep.get("tris"), rep.get("joints"), len(rep.get("clips", [])),
            len(rep.get("textures", [])), rep.get("bytes", 0) / 1e6,
            ", Blender re-import %s" % ("OK" if rep.get("blender_smoke", {}).get("ok") else "FAILED") if blender else ""))
    if opt("--json"):
        with open(opt("--json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"ok": ok, "files": reports}, f, indent=1)
            f.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
