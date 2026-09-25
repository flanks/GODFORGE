"""Record a person's approval of a stage-0 reference sheet (the stage-0 human gate).

  python tools/comfy/approve_sheet.py <key> <item> <sheet.png> --by "<who approved>" [--on YYYY-MM-DD]

  <item>: front | side | three_quarter | back | expression | weapon_gauntlet | color_script

Run this ONLY after a person has looked at the sheet and approved it; --by names that person.
It never decides anything itself. It:
  1. copies the sheet to art/characters/<key>/references/<KEY>_<item>_approved.png (refuses > 20 MB:
     no Git LFS in this repo);
  2. sets stages.0_concept_reference.items.<item> in status.json to done with approved_by / approved_on /
     sha256 / outputs, and the stage itself to done once every sheet item is done;
  3. adds or replaces the sheet's entry under "references" in manifest.json.
It does not commit. Pure standard library; key order in the JSON files is preserved.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SHEETS = ("front", "side", "three_quarter", "back", "expression", "weapon_gauntlet", "color_script")
STAGE = "0_concept_reference"
LIMIT = 20_000_000


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key")
    ap.add_argument("item", choices=SHEETS)
    ap.add_argument("sheet")
    ap.add_argument("--by", required=True, help="the person who approved the sheet")
    ap.add_argument("--on", default=datetime.date.today().isoformat())
    a = ap.parse_args(argv)

    base = os.path.join(ROOT, "art", "characters", a.key)
    src = os.path.abspath(a.sheet)
    size = os.path.getsize(src)
    if size > LIMIT:
        raise SystemExit("%s is %d bytes: over the 20 MB commit limit; export a smaller PNG" % (src, size))
    dst = os.path.join(base, "references", "%s_%s_approved.png" % (a.key.upper(), a.item))
    if os.path.abspath(dst) != src:
        shutil.copyfile(src, dst)
    digest = hashlib.sha256(open(dst, "rb").read()).hexdigest()
    rel = os.path.relpath(dst, ROOT).replace("\\", "/")

    status_path = os.path.join(base, "status.json")
    status = load(status_path)
    stage = status["stages"][STAGE]
    item = stage.setdefault("items", {}).setdefault(a.item, {})
    item.update({"status": "done", "human_signoff_required": True, "approved_by": a.by, "approved_on": a.on,
                 "sha256": digest, "outputs": [rel], "notes": "Approved by %s on %s." % (a.by, a.on)})
    if all(stage["items"].get(s, {}).get("status") == "done" for s in SHEETS):
        stage["status"] = "done"
    if rel not in stage.setdefault("outputs", []):
        stage["outputs"].append(rel)
    status["updated"] = datetime.date.today().isoformat()
    save(status_path, status)

    man_path = os.path.join(base, "manifest.json")
    man = load(man_path) if os.path.isfile(man_path) else {"asset": a.key}
    refs = [r for r in man.get("references", []) if r.get("path") != rel]
    refs.append({"path": rel, "bytes": os.path.getsize(dst), "sha256": digest,
                 "role": "approved stage-0 sheet: %s" % a.item, "in_git": True, "approved_by": a.by, "approved_on": a.on})
    man["references"] = refs
    save(man_path, man)
    print("[approve] %s %s -> %s (sha256 %s..., approved by %s on %s); stage 0 is %s"
          % (a.key, a.item, rel, digest[:12], a.by, a.on, stage["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
