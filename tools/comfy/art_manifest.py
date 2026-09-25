"""Record a hero's local-only art files (path, bytes, sha256) in art/characters/<key>/manifest.json.

  python tools/comfy/art_manifest.py <key> [--selected <file>] [--note "..."]

Raw generator output (TRELLIS GLBs, ComfyUI previews) and heavy .blend files never enter git
(art/.gitignore; no Git LFS, nothing > 20 MB committed). The manifest is the committed record that
lets anyone verify a local copy: it lists every file under source/ (plus any *.blend under work/),
whether git ignores it, its size and sha256, and the provenance JSON that produced it.
Existing per-file notes and top-level keys other than "files" are preserved.
Pure standard library.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def ignored(paths):
    if not paths:
        return set()
    # -z (NUL-separated, bytes): with text=True on Windows the "\n" separators reach git as "\r\n",
    # git echoes every path but the last with a trailing \r, and those looked "not ignored".
    r = subprocess.run(["git", "check-ignore", "--stdin", "-z"], cwd=ROOT, input="\0".join(paths).encode("utf-8"),
                       capture_output=True)
    return set(p for p in r.stdout.decode("utf-8").split("\0") if p)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("--selected", default=None, help="file name under source/ picked as the sculpt reference")
    ap.add_argument("--note", default=None)
    args = ap.parse_args(argv)
    base = os.path.join(ROOT, "art", "characters", args.key)
    path = os.path.join(base, "manifest.json")
    old = json.load(open(path)) if os.path.isfile(path) else {}
    old_notes = {f["path"]: f.get("note") for f in old.get("files", []) if f.get("note")}

    found = []
    for sub, keep in (("source", lambda n: not n.endswith(".json")), ("work", lambda n: n.endswith(".blend"))):
        d = os.path.join(base, sub)
        for dirpath, _, names in os.walk(d):
            for n in sorted(names):
                if keep(n):
                    found.append(os.path.join(dirpath, n))
    rels = [rel(p) for p in found]
    ign = ignored(rels)
    files = []
    for p, r in zip(found, rels):
        entry = {"path": r, "bytes": os.path.getsize(p), "sha256": sha256(p), "in_git": r not in ign}
        stem = os.path.splitext(os.path.basename(p))[0]
        for suffix in ("_cond", "_mask"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        prov = os.path.join(os.path.dirname(p), stem + ".json")
        if os.path.isfile(prov):
            entry["provenance"] = rel(prov)
        if r in old_notes:
            entry["note"] = old_notes[r]
        files.append(entry)
        if entry["in_git"] and entry["bytes"] > 20_000_000:
            print("[manifest] WARNING %s is %d bytes and NOT ignored by git" % (r, entry["bytes"]), file=sys.stderr)

    manifest = dict(old)
    manifest.update({"asset": args.key, "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "policy": "files listed with in_git=false stay local (art/.gitignore); verify a copy by sha256",
                     "files": files})
    if args.selected:
        manifest["selected_sculpt_reference"] = "art/characters/%s/source/%s" % (args.key, args.selected)
    if args.note:
        manifest["note"] = args.note
    with open(path, "w", newline="\n") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    print("[manifest] %s: %d local files recorded" % (rel(path), len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
