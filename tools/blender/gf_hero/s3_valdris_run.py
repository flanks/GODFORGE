"""Run Valdris's whole stage-3 rig chain (plain Python, standard library only). Brax keeps run_stage3.py.

  python tools/blender/gf_hero/s3_valdris_run.py [--from <step>] [--only <step>]

Steps (each a headless Blender run, or a Pillow python for the sheets):
  landmarks   s3_landmarks.py (shared)          the contract joints from the stage-2 fit -> work/valdris_landmarks.json
  lm_valdris  s3_valdris_landmarks.py           finger joints on the gauntlet lames, the hand tip on the forearm axis,
                                                chest_sigil on the anvil, the x_ extras (helpers, cape, loincloth, braids)
  seed        s3_mh_seed.py (shared)            MakeHuman CC0 game_engine weights, exact per BODY vertex
  skin        s3_skin.py (shared) + hook s3_valdris_skin.py   GF_Hero_v1 + extras, the driven helpers, the under-suit
                                                weights (as Brax), rigid armour per piece, beard, cloth grids, the
                                                colossus_cannon GLB on weapon_R -> production/valdris_rig.blend
  gltf_check  s3_gltf_check.py (shared)         scratch GLB read back: joints, hierarchy, <= 4 influences, socket frames,
                                                the identity attach proven with the shipped colossus_cannon.glb
  limits      s3_valdris_limits.py              range-of-motion sweeps (shoulder / pauldron, elbow, cannon arm, knee, hip,
                                                head, twist) with and without the helpers -> reports/stage3/limits.json
  poses       s3_valdris_poses.py               the validation poses (stage-4 solver), cloth posed clear, metrics, renders,
                                                GF_ValidationPoses stashed in the rig file -> reports/stage3/poses.json
  sheets      s3_valdris_sheets.py (Pillow)     review sheets -> reports/stage3/stage3_*.png
  contract    check_skeleton.py (stdlib)        the CI contract check

Inputs: the stage-2 outputs (production/valdris_stage2.blend, stage2_fit.json, stage2_parts.json, reports/stage2/{body_fit,
parts}.json, work/valdris_s2_mh_landmarks.json and work/valdris_s2_body_base.blend, rebuilt by s2_valdris_run.py --only base
when missing), stage3_skin.json and assets/models/weapons/colossus_cannon.glb. Renders use Cycles on the CPU and Workbench
only (the GPU is shared). About 3-4 minutes.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PIL_PY = os.environ.get("COMFY_PY") or next(
    (p for p in (r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe",) if os.path.isfile(p)), sys.executable)
STEPS = ["landmarks", "lm_valdris", "seed", "skin", "gltf_check", "limits", "poses", "sheets", "contract"]
KEY = "valdris"


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-64s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:6])[:64], time.time() - t, r.returncode))
    if r.returncode != 0:
        print(open(log_path, encoding="utf-8", errors="replace").read()[-3000:])
        raise SystemExit("step failed, log: " + log_path)


def main(argv):
    frm = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    A = os.path.join("art", "characters", KEY)
    W = os.path.join(A, "work")
    G = os.path.join("tools", "blender", "gf_hero")
    B = [BLENDER, "-b", "--python-exit-code", "1"]
    stage2 = os.path.join(A, "production", "%s_stage2.blend" % KEY)
    cmds = {
        "landmarks": B + [stage2, "-P", os.path.join(G, "s3_landmarks.py"), "--", KEY],
        "lm_valdris": B + [stage2, "-P", os.path.join(G, "s3_valdris_landmarks.py")],
        "seed": B + ["-P", os.path.join(G, "s3_mh_seed.py"), "--", KEY],
        "skin": B + ["-P", os.path.join(G, "s3_skin.py"), "--", KEY],
        "gltf_check": B + ["-P", os.path.join(G, "s3_gltf_check.py"), "--", KEY],
        "limits": B + ["-P", os.path.join(G, "s3_valdris_limits.py")],
        "poses": B + ["-P", os.path.join(G, "s3_valdris_poses.py")],
        "sheets": [PIL_PY, os.path.join(G, "s3_valdris_sheets.py")],
        "contract": [sys.executable, os.path.join(G, "check_skeleton.py")],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    base_out = [os.path.join(ROOT, W, "%s_s2_mh_landmarks.json" % KEY), os.path.join(ROOT, W, "%s_s2_body_base.blend" % KEY)]
    if {"landmarks", "seed"} & set(todo) and not all(os.path.isfile(p) for p in base_out):
        print("[valdris stage3] stage-2 base intermediates missing in work/: s2_valdris_run.py --only base")
        run([sys.executable, os.path.join(HERE, "s2_valdris_run.py"), "--only", "base"], os.path.join(ROOT, W, "logs", "stage3_stage2_base.log"))
    t0 = time.time()
    for st in todo:
        print("[valdris stage3] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage3_%s.log" % st))
    print("[valdris stage3] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
