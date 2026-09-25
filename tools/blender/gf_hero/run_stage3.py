"""Run the whole stage-3 rig chain for one hero (plain Python, standard library only).

  python tools/blender/gf_hero/run_stage3.py brax [--from <step>] [--only <step>]

Steps (each one a headless Blender run, or ComfyUI's python for the PIL sheets):
  landmarks   s3_landmarks.py   the GF_Hero_v1 landmark file from the stage-2 fit -> work/<key>_landmarks.json (committed)
  seed        s3_mh_seed.py     MakeHuman CC0 game_engine weights, exact per BODY vertex -> work/<key>_s3_mh_seed.npz
  skin        s3_skin.py        armature + skin (seed, bone heat, twist split, joint fixes, parts) -> production/<key>_rig.blend
  poses       s3_poses.py       validation poses with the signature weapon on the sockets: metrics + renders, weapon limits,
                                the GF_ValidationPoses action stashed in the rig file
  gltf_check  s3_gltf_check.py  scratch GLB: joints, hierarchy, influences, socket frames, the weapon's identity attach
  sheets      s3_sheets.py      review sheets into reports/stage3/
  contract    check_skeleton.py the stdlib contract check CI runs (every hero's landmark file + stage-3 reports)

Inputs per hero: the stage-2 outputs (production/<key>_stage2.blend, stage2_fit.json, reports/stage2/body_fit.json,
work/<key>_s2_mh_landmarks.json and work/<key>_s2_body_base.blend from run_stage2.py's base step, rebuilt
automatically when missing, e.g. on a fresh clone) and stage3_skin.json.
About a minute on the dev machine; the review renders use Cycles on the CPU and Workbench only (the GPU is shared).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
# the PIL review sheets run in any Python with Pillow: $COMFY_PY, else the dev machine's ComfyUI env, else this Python
COMFY_PY = os.environ.get("COMFY_PY") or next(
    (p for p in (r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe",) if os.path.isfile(p)), sys.executable)
STEPS = ["landmarks", "seed", "skin", "poses", "gltf_check", "sheets", "contract"]


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
    A = os.path.join("art", "characters", key)
    W = os.path.join(A, "work")
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    B = [BLENDER, "-b", "--python-exit-code", "1"]
    G = os.path.join("tools", "blender", "gf_hero")
    stage2 = os.path.join(A, "production", "%s_stage2.blend" % key)
    cmds = {
        "landmarks": B + [stage2, "-P", os.path.join(G, "s3_landmarks.py"), "--", key],
        "seed": B + ["-P", os.path.join(G, "s3_mh_seed.py"), "--", key],
        "skin": B + ["-P", os.path.join(G, "s3_skin.py"), "--", key],
        "poses": B + ["-P", os.path.join(G, "s3_poses.py"), "--", key],
        "gltf_check": B + ["-P", os.path.join(G, "s3_gltf_check.py"), "--", key],
        "sheets": [COMFY_PY, os.path.join(G, "s3_sheets.py"), key],
        "contract": [sys.executable, os.path.join(G, "check_skeleton.py")],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    # work/ is not in git: on a fresh clone the stage-2 base intermediates (MakeHuman landmarks and the reduced hm08
    # body, deterministic, a few seconds) are rebuilt first
    base_out = [os.path.join(ROOT, W, "%s_s2_mh_landmarks.json" % key), os.path.join(ROOT, W, "%s_s2_body_base.blend" % key)]
    if {"landmarks", "seed"} & set(todo) and not all(os.path.isfile(p) for p in base_out):
        print("[stage3] stage-2 base intermediates missing in work/: run_stage2.py %s --only base" % key)
        run([sys.executable, os.path.join(HERE, "run_stage2.py"), key, "--only", "base"],
            os.path.join(ROOT, W, "logs", "stage3_stage2_base.log"))
    for st in todo:
        print("[stage3] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage3_%s.log" % st))
    print("[stage3] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
