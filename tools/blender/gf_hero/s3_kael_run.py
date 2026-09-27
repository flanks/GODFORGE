"""Run Kael's whole stage-3 rig chain (plain Python, standard library only). Brax keeps run_stage3.py.

  python tools/blender/gf_hero/s3_kael_run.py [--from <step>] [--only <step>]

Steps (each a headless Blender run, or a Pillow python for the sheet):
  landmarks   s3_landmarks.py (shared)       the contract joints and sockets from the stage-2 fit -> work/kael_landmarks.json
  lm_kael     s3_kael_landmarks.py           his x_ cloth chains placed on the stage-2 mesh: x_coat (6 x 4) down the
                                             duster's skirt, x_loin (3 x 3), x_wisp (5 x 3) on the ghost-flame tatters
  seed        s3_mh_seed.py (shared)         MakeHuman CC0 game_engine weights, exact per BODY vertex
  skin        s3_skin.py (shared) + hook s3_kael_skin.py   GF_Hero_v1 + extras, the body weighted as Brax's, gear /
                                             boots / yoke copying the body, the cloth on its chains, serpent_smg.glb on
                                             weapon_R (PREVIEW, identity attach) -> production/kael_rig.blend
  gltf_check  s3_gltf_check.py (shared)      scratch GLB read back: joints, hierarchy, <= 4 influences, socket frames, the
                                             identity attach proven with the shipped serpent_smg.glb (CI reads its report)
  review      s4_kael_review.py --stage3     skeleton, weights, rest turnaround and the check poses (needs the stage-4
                                             file: the check poses are baked clip frames with the cloth pass)
  sheet       kael_review_sheets.py stage3   reports/stage3/stage3_rig.png

Inputs: the stage-2 outputs (production/kael_stage2.blend, stage2_fit.json, stage2_parts.json, reports/stage2/{body_fit,
parts}.json, work/kael_s2_mh_landmarks.json and work/kael_s2_body_base.blend, rebuilt by s2_kael_run.py --only base when
missing), stage3_skin.json and assets/models/weapons/serpent_smg.glb. Renders use Cycles on the CPU and Workbench only.
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
STEPS = ["landmarks", "lm_kael", "seed", "skin", "gltf_check", "review", "sheet"]
KEY = "kael"


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
        "lm_kael": B + [stage2, "-P", os.path.join(G, "s3_kael_landmarks.py")],
        "seed": B + ["-P", os.path.join(G, "s3_mh_seed.py"), "--", KEY],
        "skin": B + ["-P", os.path.join(G, "s3_skin.py"), "--", KEY],
        "gltf_check": B + ["-P", os.path.join(G, "s3_gltf_check.py"), "--", KEY],
        "review": B + ["-P", os.path.join(G, "s4_kael_review.py"), "--", "--stage3"],
        "sheet": [PIL_PY, os.path.join(G, "kael_review_sheets.py"), "stage3"],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    base_out = [os.path.join(ROOT, W, "%s_s2_mh_landmarks.json" % KEY), os.path.join(ROOT, W, "%s_s2_body_base.blend" % KEY)]
    if {"landmarks", "seed"} & set(todo) and not all(os.path.isfile(p) for p in base_out):
        print("[kael stage3] stage-2 base intermediates missing in work/: s2_kael_run.py --only base")
        run([sys.executable, os.path.join(HERE, "s2_kael_run.py"), "--only", "base"], os.path.join(ROOT, W, "logs", "stage3_stage2_base.log"))
    t0 = time.time()
    for st in todo:
        print("[kael stage3] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage3_%s.log" % st))
    print("[kael stage3] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
