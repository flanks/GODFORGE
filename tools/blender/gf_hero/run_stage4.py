"""Run the whole stage-4 animation chain for one hero (plain Python, standard library only).

  python tools/blender/gf_hero/run_stage4.py brax [--from <step>] [--only <step>]

Steps (each one a headless Blender run, or ComfyUI's python for the PIL sheets):
  anim        s4_anim.py        solve + bake the shared GF_Hero_v1 library (s4_clips.py) and the hero's unique set
                                (s4_<key>.py) -> production/<key>_anim.blend (Git LFS) + reports/anim/clips.json (metrics)
  render      s4_render.py      key-frame renders (Cycles CPU toon close-ups + the 55 deg client camera at true pixel size)
                                and mesh checks -> work/renders/stage4/, reports/anim/render_checks.json
  sheets      s4_sheets.py      one contact sheet per clip + the game-size boards -> reports/anim/*.png
  gltf_check  s4_gltf_check.py  a scratch GLB with every clip read back -> reports/anim/gltf_check.json
  contract    check_clips.py    the stdlib clip contract CI runs (needs status.json stage 4 marked done to check a hero)

Inputs: production/<key>_rig.blend (stage 3), work/<key>_landmarks.json, content/sheets/characters.csv (move speed).
About 10 minutes on the dev machine, almost all of it the review renders (Cycles on the CPU; the GPU is shared).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe")
STEPS = ["anim", "render", "sheets", "gltf_check", "contract"]


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-60s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:5])[:60], time.time() - t, r.returncode))
    if r.returncode != 0:
        print(open(log_path, encoding="utf-8", errors="replace").read()[-3000:])
        raise SystemExit("step failed, log: " + log_path)


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    key = argv[0]
    frm = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    W = os.path.join("art", "characters", key, "work")
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    B = [BLENDER, "-b", "--python-exit-code", "1"]
    G = os.path.join("tools", "blender", "gf_hero")
    cmds = {
        "anim": B + ["-P", os.path.join(G, "s4_anim.py"), "--", key],
        "render": B + ["-P", os.path.join(G, "s4_render.py"), "--", key],
        "sheets": [COMFY_PY, os.path.join(G, "s4_sheets.py"), key],
        "gltf_check": B + ["-P", os.path.join(G, "s4_gltf_check.py"), "--", key],
        "contract": [sys.executable, os.path.join(G, "check_clips.py")],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    for st in todo:
        print("[stage4] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage4_%s.log" % st))
    print("[stage4] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
