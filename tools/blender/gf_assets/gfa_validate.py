"""Validate a shipped GODFORGE asset GLB against the gf_assets contract (pure standard library).

  python tools/blender/gf_assets/gfa_validate.py assets/models/weapons/sunspike_shotgun.glb
  python tools/blender/gf_assets/gfa_validate.py <glb> --kind enemy --tier swarm [--json report.json]

kind / tier default to the sidecar <key>.meta.json next to the GLB. Exit code 1 on any error.

Checks (docs/art/WEAPONS.md section 6, docs/art/ENEMIES.md section 7):
  * binary glTF 2.0; no required extension bevy_gltf 0.20 cannot load; no Draco / meshopt / quantisation;
  * key is lower_snake_case and equals the file stem;
  * triangle count inside the tier budget (over = error, under the minimum = warning);
  * textures embedded, <= the tier's max size, >= 256 px (power of two expected); one material with a
    base-colour texture and an emissive texture;
  * required sockets present as nodes; weapons: grip_R at the origin, muzzle in front (glTF -Z);
  * rigged enemies: skin present, joints exactly GF_Swarm_v1 for swarms, every clip named
    {key}_{clip}[@loop] and the required clip set present, loops flagged @loop;
  * size sanity: weapon length, creature height vs the tier ratio of the 2.2 m hero.
"""
import json
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import gfa_spec as SPEC  # noqa: E402


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("not a binary glTF")
    version, total = struct.unpack("<II", data[4:12])
    if version != 2:
        raise ValueError("glTF version %d" % version)
    off = 12
    doc, binc = None, b""
    while off < len(data):
        ln, typ = struct.unpack("<II", data[off:off + 8])
        chunk = data[off + 8:off + 8 + ln]
        if typ == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif typ == 0x004E4942:
            binc = chunk
        off += 8 + ln
    if doc is None:
        raise ValueError("no JSON chunk")
    return doc, binc


def image_size(blob):
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", blob[16:24])
        return w, h, "png"
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i < len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            ln = struct.unpack(">H", blob[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xC3:
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return w, h, "jpeg"
            i += 2 + ln
    return 0, 0, "unknown"


# ---- tiny matrix helpers (column-major glTF -> row lists) --------------------------------------------

def _mat_from_node(n):
    if "matrix" in n:
        m = n["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    t = n.get("translation", [0, 0, 0])
    q = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    x, y, z, w = q
    R = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[R[r][0] * s[0], R[r][1] * s[1], R[r][2] * s[2], t[r]] for r in range(3)] + [[0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def world_matrices(doc):
    nodes = doc.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    cache = {}

    def wm(i):
        if i in cache:
            return cache[i]
        m = _mat_from_node(nodes[i])
        if i in parent:
            m = _mul(wm(parent[i]), m)
        cache[i] = m
        return m
    return [wm(i) for i in range(len(nodes))]


def _apply(m, p):
    return [m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3)]


def tri_count(doc):
    n = 0
    for mesh in doc.get("meshes", []):
        for p in mesh.get("primitives", []):
            if p.get("mode", 4) != 4:
                continue
            if "indices" in p:
                n += doc["accessors"][p["indices"]]["count"] // 3
            else:
                n += doc["accessors"][p["attributes"]["POSITION"]]["count"] // 3
    return n


def mesh_bounds(doc, wms):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for i, n in enumerate(doc.get("nodes", [])):
        if "mesh" not in n:
            continue
        m = wms[i] if "skin" not in n else [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        for p in doc["meshes"][n["mesh"]]["primitives"]:
            acc = doc["accessors"][p["attributes"]["POSITION"]]
            a, b = acc.get("min"), acc.get("max")
            if not a:
                continue
            for x in (a[0], b[0]):
                for y in (a[1], b[1]):
                    for z in (a[2], b[2]):
                        q = _apply(m, (x, y, z))
                        lo = [min(lo[k], q[k]) for k in range(3)]
                        hi = [max(hi[k], q[k]) for k in range(3)]
    return lo, hi


def validate(path, kind=None, tier=None, key=None, meta=None):
    errors, warnings = [], []
    stem = os.path.splitext(os.path.basename(path))[0]
    key = key or stem
    meta = meta or {}
    kind = kind or meta.get("kind")
    tier = tier or meta.get("tier")
    rep = {"file": path, "key": key, "kind": kind, "tier": tier}
    try:
        doc, binc = read_glb(path)
    except (OSError, ValueError) as ex:
        return dict(rep, ok=False, errors=["%s: %s" % (path, ex)], warnings=[])
    if kind not in SPEC.KINDS:
        errors.append("kind %r is not one of %s" % (kind, sorted(SPEC.KINDS)))
        return dict(rep, ok=False, errors=errors, warnings=warnings)
    bclass = "%s_%s" % (kind, tier)
    if bclass not in SPEC.BUDGETS:
        errors.append("tier %r unknown for %s (budget classes: %s)" % (tier, kind, sorted(SPEC.BUDGETS)))
        return dict(rep, ok=False, errors=errors, warnings=warnings)
    tmin, tmax, texmax = SPEC.BUDGETS[bclass]
    # extensions
    req = set(doc.get("extensionsRequired", []))
    used = set(doc.get("extensionsUsed", []))
    bad = sorted(req - SPEC.BEVY_OK_EXTENSIONS)
    if bad:
        errors.append("requires glTF extensions bevy_gltf 0.20 cannot load: %s" % bad)
    banned = sorted((req | used) & SPEC.BANNED_EXTENSIONS)
    if banned:
        errors.append("uses compression/quantisation extensions (export uncompressed): %s" % banned)
    rep["extensions_used"] = sorted(used)
    # naming
    if not re.match(SPEC.KEY_RE, key):
        errors.append("key %r is not lower_snake_case" % key)
    if key != stem:
        errors.append("file stem %r != key %r" % (stem, key))
    # triangles
    tris = tri_count(doc)
    rep["tris"] = tris
    rep["budget"] = [tmin, tmax]
    if tris > tmax:
        errors.append("%d tris > %s budget %d" % (tris, bclass, tmax))
    elif tris < tmin:
        warnings.append("%d tris < %s minimum %d (unfinished?)" % (tris, bclass, tmin))
    # textures / materials
    roles = {}
    for m in doc.get("materials", []):
        for role, ref in (("base_color", m.get("pbrMetallicRoughness", {}).get("baseColorTexture")),
                          ("emissive", m.get("emissiveTexture"))):
            if ref is not None:
                src = doc["textures"][ref["index"]].get("source")
                roles.setdefault(src, role)
    texs = []
    for i, im in enumerate(doc.get("images", [])):
        if "bufferView" not in im:
            errors.append("image %d is not embedded (uri %r)" % (i, im.get("uri")))
            continue
        bv = doc["bufferViews"][im["bufferView"]]
        blob = binc[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        w, h, fmt = image_size(blob)
        texs.append({"name": im.get("name", "image_%d" % i), "role": roles.get(i, "unused"), "px": [w, h],
                     "format": fmt, "bytes": bv["byteLength"]})
        if i not in roles:
            warnings.append("image %s is not used by the material" % im.get("name"))
        if max(w, h) > texmax:
            errors.append("texture %s is %dx%d > %d px for %s" % (im.get("name"), w, h, texmax, bclass))
        if min(w, h) < SPEC.MIN_TEXTURE_PX:
            warnings.append("texture %s is only %dx%d" % (im.get("name"), w, h))
        if w & (w - 1) or h & (h - 1):
            warnings.append("texture %s is not a power of two (%dx%d)" % (im.get("name"), w, h))
    rep["textures"] = texs
    mats = doc.get("materials", [])
    rep["materials"] = [m.get("name") for m in mats]
    if len(mats) != 1:
        (errors if not mats else warnings).append("%d materials (expected exactly 1)" % len(mats))
    for m in mats:
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" not in pbr:
            errors.append("material %s has no base-colour texture" % m.get("name"))
        if "emissiveTexture" not in m:
            errors.append("material %s has no emissive texture (use a black one when nothing glows)" % m.get("name"))
    # nodes / sockets
    nodes = doc.get("nodes", [])
    names = [n.get("name", "") for n in nodes]
    wms = world_matrices(doc)
    rep["nodes"] = names
    socket_names = SPEC.WEAPON_SOCKETS_REQUIRED.get(bclass, ()) if kind == "weapon" else SPEC.ENEMY_SOCKETS_REQUIRED
    optional = SPEC.WEAPON_SOCKETS_OPTIONAL if kind == "weapon" else SPEC.ENEMY_SOCKETS_OPTIONAL
    socks = {}
    for nm in set(socket_names) | set(optional):
        if nm in names:
            i = names.index(nm)
            m = wms[i]
            socks[nm] = {"translation": [round(m[r][3], 4) for r in range(3)],
                         "forward": [round(-m[r][2], 4) for r in range(3)],
                         "up": [round(m[r][1], 4) for r in range(3)]}
    rep["sockets"] = socks
    for nm in socket_names:
        if nm not in names:
            errors.append("required socket node %r missing" % nm)
    lo, hi = mesh_bounds(doc, wms)
    rep["bounds"] = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}
    dims = [hi[k] - lo[k] for k in range(3)]
    if kind == "weapon":
        if key not in names:
            warnings.append("no root node named %r" % key)
        g = socks.get("grip_R")
        if g and math.dist(g["translation"], (0, 0, 0)) > 0.01:
            errors.append("grip_R is not at the origin (%s): the grip frame IS the origin" % g["translation"])
        mz = socks.get("muzzle")
        if mz:
            t = mz["translation"]
            if t[2] > -0.05:
                errors.append("muzzle at glTF z %.3f: the barrel must point to glTF -Z (Blender +Y)" % t[2])
            if mz["forward"][2] > -0.7:
                errors.append("muzzle does not point along glTF -Z (forward %s)" % mz["forward"])
        L = max(dims)
        if not (SPEC.WEAPON_LENGTH_RANGE[0] <= L <= SPEC.WEAPON_LENGTH_RANGE[1]):
            errors.append("weapon length %.2f m outside %s" % (L, SPEC.WEAPON_LENGTH_RANGE))
        rep["length_m"] = round(L, 3)
    else:
        h = dims[1]
        ratio = h / SPEC.HERO_HEIGHT
        rep["height_m"] = round(h, 3)
        rep["height_vs_hero"] = round(ratio, 3)
        rr = SPEC.TIER_HEIGHT_RATIO.get(bclass)
        if rr and not (rr[0] <= ratio <= rr[1]):
            warnings.append("height %.2f m = %.2f x hero, outside the %s range %s" % (h, ratio, bclass, rr))
        skins = doc.get("skins", [])
        if not skins:
            errors.append("no skin: enemies ship rigged (GF_Swarm_v1 for swarms, a dedicated rig otherwise)")
        else:
            joints = [names[j] for j in skins[0]["joints"]]
            rep["joints"] = joints
            if bclass == "enemy_swarm":
                want = [b for b, _ in SPEC.SWARM_BONES]
                if sorted(joints) != sorted(want):
                    errors.append("swarm joints %s != GF_Swarm_v1 %s" % (joints, want))
                if SPEC.SWARM_SKELETON not in names:
                    errors.append("armature node %r missing (Bevy animation target paths)" % SPEC.SWARM_SKELETON)
                else:
                    for b, par in SPEC.SWARM_BONES:
                        if b in names and par is not None:
                            pi = names.index(par)
                            if names.index(b) not in nodes[pi].get("children", []):
                                errors.append("bone %s is not a child of %s" % (b, par))
        anims = [a.get("name", "") for a in doc.get("animations", [])]
        rep["clips"] = anims
        for a in anims:
            if not a.startswith(key + "_") or not re.match(SPEC.CLIP_RE, a[len(key) + 1:]):
                errors.append("clip %r is not named %s_<clip>[@loop]" % (a, key))
        for c in SPEC.ENEMY_CLIPS_REQUIRED:
            if "%s_%s" % (key, c) not in anims:
                errors.append("required clip %s_%s missing" % (key, c))
    rep["errors"], rep["warnings"] = errors, warnings
    rep["ok"] = not errors
    return rep


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv else None
    meta_path = os.path.splitext(path)[0] + ".meta.json"
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.isfile(meta_path) else {}
    rep = validate(path, opt("--kind"), opt("--tier"), opt("--key"), meta)
    for w in rep.get("warnings", []):
        print("warning:", w)
    for e in rep.get("errors", []):
        print("ERROR:", e)
    print("[gfa_validate] %s: %s, %s tris, %d texture(s), sockets %s, clips %d" % (
        os.path.basename(path), "OK" if rep["ok"] else "FAILED", rep.get("tris"), len(rep.get("textures", [])),
        sorted(rep.get("sockets", {})), len(rep.get("clips", []))))
    if opt("--json"):
        with open(opt("--json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(rep, f, indent=1)
            f.write("\n")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
