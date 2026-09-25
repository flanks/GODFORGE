"""Art-track gates that need no Blender and no GPU (run by .github/workflows/art.yml, and locally).

  python tools/comfy/check_art.py

Errors (exit 1):
  * a file tracked by git, or an untracked file under art/ or assets/models/ that git would add,
    is larger than 20 MB, unless .gitattributes routes it through Git LFS (filter=lfs: git then
    stores a small pointer; e.g. a hero's selected raw TRELLIS GLB). Other raw output stays local,
    see art/.gitignore;
  * art/characters/<key>/status.json breaks the pipeline's status rules (docs/ART_PIPELINE.md):
      - every stage/item status is one of not_started | in_progress | done | stand_in | pending_human | blocked;
      - status stand_in  =>  stand_in: true;  stand_in: true  =>  never final, never plain done;
      - a human gate (human_signoff_required: true) marked done names its approver
        (approved_by / signed_off_by), directly or on every item it contains;
      - "final": true only when stage 5 is done and signed off;
  * a manifest.json entry marked in_git: false is tracked by git anyway;
  * a GLB under assets/models/ requires a glTF extension bevy_gltf 0.20 cannot load
    (Draco, meshopt, mesh quantisation, ...).
Warnings: a committed file whose sha256 no longer matches its manifest entry (re-run the manifest tool).
Pure standard library.
"""
import hashlib
import json
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LIMIT = 20_000_000
STATUSES = {"not_started", "in_progress", "done", "stand_in", "pending_human", "blocked"}
# extensions bevy_gltf-0.20.0-rc.1 (src/lib.rs table + gltf-json ENABLED_EXTENSIONS) can load when required
BEVY_OK = {"KHR_lights_punctual", "KHR_materials_unlit", "KHR_texture_transform", "KHR_materials_transmission",
           "KHR_materials_ior", "KHR_materials_emissive_strength", "KHR_materials_specular",
           "KHR_materials_volume", "KHR_materials_clearcoat", "KHR_materials_anisotropy"}

errors, warnings = [], []


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return [p for p in r.stdout.decode("utf-8").split("\0") if p]


def lfs_paths(paths):
    """The subset of paths that .gitattributes sends through Git LFS (filter=lfs)."""
    if not paths:
        return set()
    r = subprocess.run(["git", "check-attr", "-z", "--stdin", "filter"], cwd=ROOT, capture_output=True,
                       input="\0".join(paths).encode("utf-8"))
    f = r.stdout.decode("utf-8").split("\0")
    return {f[i] for i in range(0, len(f) - 2, 3) if f[i + 2] == "lfs"}


def check_sizes():
    tracked = git("ls-files", "-z")
    addable = git("ls-files", "-z", "--others", "--exclude-standard", "--", "art", "assets/models")
    big = [rel for rel in tracked + addable
           if os.path.isfile(os.path.join(ROOT, rel)) and os.path.getsize(os.path.join(ROOT, rel)) > LIMIT]
    lfs = lfs_paths(big)
    for rel in big:
        if rel in lfs:
            continue            # git stores an LFS pointer, not the bytes
        kind = "tracked" if rel in tracked else "untracked and NOT ignored"
        errors.append("%s is %d bytes (> 20 MB, %s, not in Git LFS)" % (rel, os.path.getsize(os.path.join(ROOT, rel)), kind))
    return set(tracked)


def check_entry(where, e):
    st = e.get("status")
    if st not in STATUSES:
        errors.append("%s: status %r is not one of %s" % (where, st, sorted(STATUSES)))
    if st == "stand_in" and e.get("stand_in") is not True:
        errors.append("%s: status stand_in needs stand_in: true" % where)
    if e.get("stand_in") is True:
        if e.get("final") is True:
            errors.append("%s: a stand-in can never be final" % where)
        if st == "done":
            errors.append("%s: a stand-in is status stand_in, not done" % where)
    if "human_signoff_required" in e and not isinstance(e["human_signoff_required"], bool):
        errors.append("%s: human_signoff_required must be true/false" % where)
    # a stage with items is signed off through its items (each checked on its own)
    if e.get("human_signoff_required") is True and st == "done" and not e.get("items")             and not (e.get("approved_by") or e.get("signed_off_by")):
        errors.append("%s: a human gate marked done must name its approver (approved_by / signed_off_by)" % where)


def check_status(key, path):
    try:
        s = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        errors.append("%s: unreadable (%s)" % (path, ex))
        return
    stages = s.get("stages")
    if not isinstance(stages, dict) or not stages:
        errors.append("%s: no stages" % path)
        return
    for name, st in stages.items():
        where = "%s status.%s" % (key, name)
        check_entry(where, st)
        for k in ("outputs",):
            if k in st and not isinstance(st[k], list):
                errors.append("%s: %s must be a list" % (where, k))
        for iname, it in (st.get("items") or {}).items():
            check_entry("%s.items.%s" % (where, iname), it)
    if s.get("final") is True:
        last = [v for k, v in stages.items() if k.startswith("5")]
        if not last or last[0].get("status") != "done" or not (last[0].get("signed_off_by") or last[0].get("approved_by")):
            errors.append("%s: final: true but stage 5 is not done and signed off" % key)


def check_manifest(key, path, tracked):
    try:
        m = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as ex:
        errors.append("%s: unreadable (%s)" % (path, ex))
        return
    for e in m.get("files", []) + m.get("references", []):
        rel = e.get("path", "")
        if e.get("in_git") is False and rel in tracked:
            errors.append("%s manifest: %s is marked local-only but git tracks it" % (key, rel))
        p = os.path.join(ROOT, rel)
        if e.get("in_git") and os.path.isfile(p) and e.get("sha256"):
            h = hashlib.sha256(open(p, "rb").read()).hexdigest()
            if h != e["sha256"]:
                warnings.append("%s manifest: %s changed since it was recorded (re-run the manifest tool)" % (key, rel))


def check_glb(path):
    with open(path, "rb") as f:
        head = f.read(20)
        if len(head) < 20 or head[:4] != b"glTF":
            errors.append("%s: not a binary glTF" % path)
            return
        clen, ctype = struct.unpack("<II", head[12:20])
        if ctype != 0x4E4F534A:
            errors.append("%s: first chunk is not JSON" % path)
            return
        doc = json.loads(f.read(clen).decode("utf-8"))
    bad = sorted(set(doc.get("extensionsRequired", [])) - BEVY_OK)
    if bad:
        errors.append("%s requires %s, which bevy_gltf 0.20 cannot load (export uncompressed)" % (os.path.relpath(path, ROOT).replace(os.sep, "/"), ", ".join(bad)))


def main():
    tracked = check_sizes()
    chars = os.path.join(ROOT, "art", "characters")
    n = 0
    for key in sorted(os.listdir(chars)) if os.path.isdir(chars) else []:
        base = os.path.join(chars, key)
        if not os.path.isdir(base):
            continue
        n += 1
        if os.path.isfile(os.path.join(base, "status.json")):
            check_status(key, os.path.join(base, "status.json"))
        else:
            errors.append("art/characters/%s has no status.json" % key)
        if os.path.isfile(os.path.join(base, "manifest.json")):
            check_manifest(key, os.path.join(base, "manifest.json"), tracked)
        if os.path.isfile(os.path.join(base, "palette.json")):
            try:
                json.load(open(os.path.join(base, "palette.json"), encoding="utf-8"))
            except ValueError as ex:
                errors.append("%s palette.json: %s" % (key, ex))
    glbs = 0
    for dirpath, _, names in os.walk(os.path.join(ROOT, "assets", "models")):
        for nm in names:
            if nm.lower().endswith(".glb"):
                glbs += 1
                check_glb(os.path.join(dirpath, nm))
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("ERROR:", e)
    print("[check_art] %d character(s), %d shipped GLB(s), %d tracked files size-checked: %d error(s), %d warning(s)"
          % (n, glbs, len(tracked), len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
