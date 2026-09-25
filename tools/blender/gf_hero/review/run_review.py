"""Independent review of a shipped hero GLB (plain Python, standard library only; written for the review of Brax
stages 3-5, art/characters/brax/reports/review_stage3_5.md).

  python tools/blender/gf_hero/review/run_review.py <key> [--out <dir>] [--glb <hero.glb>] [--weapon <weapon.glb>]

Steps (headless Blender 5.2 for the audit and the renders, any Python with Pillow + numpy for the sheets):
  audit     glb_audit.py   skeleton / sockets / weights / clip names against the docs, every frame of every clip:
                           joint ranges, loop seams, in place, planted feet, ground, gauntlet enclosure -> audit.json
  closeups  rv_render.py   per clip its most extreme frame (the most foreign vertices inside a gauntlet, else the
                           deepest elbow or knee): full body + shoulder/elbow, knee and hip close-ups -> closeups/*.png
  game      rv_render.py   the 55 deg client camera at true pixel size, 22 m (one player) and 28 m (four players), next
                           to the greybox capsule, + gauntlet / body silhouettes -> game_board.png (+ _silhouettes.json)
Default output: art/characters/<key>/work/review/ (not in git). $BLENDER and $COMFY_PY override the tools.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY") or next(
    (p for p in (r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe",) if os.path.isfile(p)), sys.executable)


def arg(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def run(cmd, log):
    with open(log, "w", encoding="utf-8", newline="\n") as f:
        r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    script = next((c for c in cmd if c.endswith(".py")), cmd[0])
    print("  %-14s exit %d  (%s)" % (os.path.basename(script), r.returncode, log))
    if r.returncode:
        raise SystemExit(open(log, encoding="utf-8", errors="replace").read()[-3000:])


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    key = argv[0]
    out = os.path.abspath(arg(argv, "--out", os.path.join(ROOT, "art", "characters", key, "work", "review")))
    glb = os.path.abspath(arg(argv, "--glb", os.path.join(ROOT, "assets", "models", "characters", key + ".glb")))
    meta = json.load(open(glb.replace(".glb", ".meta.json"), encoding="utf-8"))
    wglb = os.path.abspath(arg(argv, "--weapon", os.path.join(ROOT, meta["weapon"]["glb"])))
    os.makedirs(out, exist_ok=True)
    B = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P"]
    audit = os.path.join(out, "audit.json")
    run(B + [os.path.join(HERE, "glb_audit.py"), "--", ROOT, glb, wglb, audit], os.path.join(out, "audit.log"))
    A = json.load(open(audit, encoding="utf-8"))
    # close-ups: each clip's worst frame
    picks = []
    for n, c in A["clips"].items():
        if c["gauntlet_foreign_intrusion_max"]:
            fr, tag = c["gauntlet_foreign_intrusion_frame"], "%d foreign vertices in a gauntlet" % c["gauntlet_foreign_intrusion_max"]
        else:
            s = max("LR", key=lambda s: c["elbow_max_" + s])
            fr, tag = c["elbow_argmax_" + s], "deepest elbow %.0f" % c["elbow_max_" + s]
        picks.append({"clip": n, "frame": fr, "tag": tag})
        k = max("LR", key=lambda s: c["knee_max_" + s])
        if c["knee_max_" + k] > 135.0 and c["knee_argmax_" + k] != fr:
            picks.append({"clip": n, "frame": c["knee_argmax_" + k], "tag": "deepest knee %.0f" % c["knee_max_" + k]})
    # the game camera: idle, run, the first unique strike's hit, the first unique clip with two events, downed
    import csv
    with open(os.path.join(ROOT, "content", "sheets", "characters.csv"), encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f) if r["key"] == key)
    ci = meta["clip_info"]

    def name(clip):
        return next((n for n in ci if ci[n]["clip"] == clip), None)
    poses = [(name("idle"), 0, "idle"), (name("run"), 0, "run contact"), (name("run"), ci[name("run")]["frames"] // 4, "run passing"),
             (name("idle_combat"), 0, "guard")]
    for n, c in ci.items():
        if c["family"] != "shared" and c["events"] and len([p for p in poses if p[2].startswith("kit")]) < 4:
            for ev, e in sorted(c["events"].items(), key=lambda kv: kv[1]["frame"]):
                poses.append((n, e["frame"], "kit %s %s" % (c["clip"], ev)))
    poses.append((name("downed"), 0, "downed"))
    jobs = {"closeups": picks,
            "ingame": [{"clip": c, "frame": f, "tag": t} for c, f, t in poses if c],
            "ingame_views": [{"H": 22, "yaw": 0, "crop": 190, "silhouette": True}, {"H": 22, "yaw": 90, "crop": 190},
                             {"H": 22, "yaw": 180, "crop": 190, "silhouette": True}, {"H": 28, "yaw": 0, "crop": 150},
                             {"H": 28, "yaw": 180, "crop": 150}],
            "greybox": {"radius": float(row["stats.radius"]), "color": row["color"]}}
    jp = os.path.join(out, "jobs.json")
    with open(jp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(jobs, f, indent=1)
    rdir = os.path.join(out, "renders")
    run(B + [os.path.join(HERE, "rv_render.py"), "--", glb, wglb, jp, rdir], os.path.join(out, "render.log"))
    S = os.path.join(HERE, "rv_sheets.py")
    run([COMFY_PY, S, "closeups", rdir, os.path.join(out, "closeups")], os.path.join(out, "sheets.log"))
    run([COMFY_PY, S, "board", rdir, os.path.join(out, "game_board.png")], os.path.join(out, "board.log"))
    print("problems: %d (audit.json 'problems'); sheets in %s" % (len(A["problems"]), out))
    for p in A["problems"]:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
