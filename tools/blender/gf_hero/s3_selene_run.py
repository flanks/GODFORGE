"""Run Selene's whole stage-3 rig chain (plain Python, standard library only). Brax keeps run_stage3.py.

  python tools/blender/gf_hero/s3_selene_run.py [--from <step>] [--only <step>]

Steps (each a headless Blender run, or a Pillow python for the sheet):
  landmarks   s3_landmarks.py (shared)          the contract joints from the stage-2 fit -> work/selene_landmarks.json
  lm_selene   s3_selene_landmarks.py            chest_sigil on the collar gem, the x_ extras: x_crown_01..06 (under head_top),
                                                x_knee_L/R, one cloth chain down each of the eight stage-2 sheets
  seed        s3_mh_seed.py (shared)            MakeHuman CC0 game_engine weights, exact per BODY vertex
  skin        s3_skin.py (shared) + hook s3_selene_skin.py   GF_Hero_v1 + extras, the knee helpers, the bodysuit weights
                                                (as Brax / Valdris), every part per stage-2 piece (rigid rows, body copies,
                                                cloth grids by the sheet's own v), the thundercoil_launcher GLB on weapon_R
                                                -> production/selene_rig.blend
  poses       s3_selene_poses.py                the validation poses (stage-4 solver, the two-handed hold as the weapon check,
                                                cloth hung clear by selene_cloth.py), Cycles-CPU toon renders -> poses.json
  sheets      s3_selene_sheets.py (Pillow)      the one review sheet -> reports/stage3/stage3_rig.png

Inputs: the stage-2 outputs (production/selene_stage2.blend, stage2_fit.json, stage2_parts.json, reports/stage2/{body_fit,
parts}.json, work/selene_s2_mh_landmarks.json and work/selene_s2_body_base.blend, rebuilt by s2_selene_run.py --only base
when missing), stage3_skin.json and assets/models/weapons/thundercoil_launcher.glb. Renders use Cycles on the CPU only
(the GPU is shared). About half a minute.
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
STEPS = ["landmarks", "lm_selene", "seed", "skin", "poses", "sheets"]
KEY = "selene"


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
        "lm_selene": B + [stage2, "-P", os.path.join(G, "s3_selene_landmarks.py")],
        "seed": B + ["-P", os.path.join(G, "s3_mh_seed.py"), "--", KEY],
        "skin": B + ["-P", os.path.join(G, "s3_skin.py"), "--", KEY],
        "poses": B + ["-P", os.path.join(G, "s3_selene_poses.py")],
        "sheets": [PIL_PY, os.path.join(G, "s3_selene_sheets.py")],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    base_out = [os.path.join(ROOT, W, "%s_s2_mh_landmarks.json" % KEY), os.path.join(ROOT, W, "%s_s2_body_base.blend" % KEY)]
    if {"landmarks", "seed"} & set(todo) and not all(os.path.isfile(p) for p in base_out):
        print("[selene stage3] stage-2 base intermediates missing in work/: s2_selene_run.py --only base")
        run([sys.executable, os.path.join(HERE, "s2_selene_run.py"), "--only", "base"], os.path.join(ROOT, W, "logs", "stage3_stage2_base.log"))
    t0 = time.time()
    for st in todo:
        print("[selene stage3] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage3_%s.log" % st))
    print("[selene stage3] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
