"""Run Selene's whole stage-4 animation chain (plain Python, standard library only). Brax keeps run_stage4.py.

  python tools/blender/gf_hero/s4_selene_run.py [--from <step>] [--only <step>]

Steps (each one a headless Blender run, or ComfyUI's python for the PIL sheet):
  anim        s4_anim.py (shared)        solve + bake the shared GF_Hero_v1 set as s4_selene.shared_clips re-poses it for her
                                         two-handed launcher (the left palm put on grip_L per frame) and her kit set
                                         (s4_selene.unique_clips) -> production/selene_anim.blend (Git LFS) + reports/anim/clips.json
  cloth       s4_selene_cloth.py         the cloth and crown pass: her eight cloth chains hung, lagged and cleared, the crown
                                         shards bobbing, keyed in every clip -> reports/anim/cloth.json
  render      s4_selene_render.py        four key frames per clip (Cycles CPU toon) and the grip audit -> render_checks.json
  sheets      s4_selene_sheets.py        the one review board -> reports/anim/anim_board.png
  gltf_check  s4_gltf_check.py (shared)  a scratch GLB with every clip read back -> reports/anim/gltf_check.json (CI reads it)

Inputs: production/selene_rig.blend (stage 3), work/selene_landmarks.json, content/sheets/characters.csv (move speed).
About two minutes on the dev machine (Cycles on the CPU; the GPU is shared).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY") or next(
    (p for p in (r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe",) if os.path.isfile(p)), sys.executable)
KEY = "selene"
STEPS = ["anim", "cloth", "render", "sheets", "gltf_check"]


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-60s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:5])[:60], time.time() - t, r.returncode))
    if r.returncode != 0:
        print(open(log_path, encoding="utf-8", errors="replace").read()[-3000:])
        raise SystemExit("step failed, log: " + log_path)


def main(argv):
    frm = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    W = os.path.join("art", "characters", KEY, "work")
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    B = [BLENDER, "-b", "--python-exit-code", "1"]
    G = os.path.join("tools", "blender", "gf_hero")
    cmds = {
        "anim": B + ["-P", os.path.join(G, "s4_anim.py"), "--", KEY],
        "cloth": B + ["-P", os.path.join(G, "s4_selene_cloth.py"), "--"],
        "render": B + ["-P", os.path.join(G, "s4_selene_render.py"), "--"],
        "sheets": [COMFY_PY, os.path.join(G, "s4_selene_sheets.py")],
        "gltf_check": B + ["-P", os.path.join(G, "s4_gltf_check.py"), "--", KEY],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    for st in todo:
        print("[selene stage4] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage4_%s.log" % st))
    print("[selene stage4] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
