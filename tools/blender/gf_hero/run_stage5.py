"""Run the whole stage-5 export & validation chain for one hero (plain Python, standard library only).

  python tools/blender/gf_hero/run_stage5.py brax [--from <step>] [--only <step>]

Steps (each one a headless Blender run, ComfyUI's python for the PIL sheet, or plain python):
  weapon    export_glb.py --weapon <chassis>  the hero's signature chassis weapon, when the gf_hero chain built it
                                              (art/weapons/<chassis>/production/<chassis>_stage2.blend) ->
                                              assets/models/weapons/<chassis>.glb + .meta.json
  export    export_glb.py --key <key>         production/<key>_anim.blend -> assets/models/characters/<key>.glb + .meta.json,
                                              Blender-side checks, the stdlib gate, source fidelity ->
                                              reports/export_report.json
  reimport  smoke_import.py                   fresh factory Blender: re-import, names, every clip one frame, the weapon
                                              on the sockets, review renders -> work/renders/stage5/ + export_report.json
  sheet     s5_sheets.py (PIL)                reports/stage5/export_review.png
  board     s5_<key>_sheets.py (PIL)          optional per-hero board (skipped when the hero has no such script), e.g.
                                              Valdris's shipped file next to his concept and blockout
  validate  validate_glb.py --blender         exactly what CI runs (stdlib gate + the Blender re-import)
Inputs: production/<key>_anim.blend (stage 4), reports/anim/clips.json, work/<key>_landmarks.json, required_clips.json.
About a minute on the dev machine (Cycles on the CPU for the few review renders; the GPU is shared).
"""
import json
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
STEPS = ["weapon", "export", "reimport", "sheet", "board", "validate"]


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-60s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:6])[:60], time.time() - t, r.returncode))
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
    with open(os.path.join(ROOT, A, "status.json"), encoding="utf-8") as f:
        chassis = (json.load(f).get("signature_weapon") or {}).get("chassis")
    wblend = os.path.join("art", "weapons", chassis or "-", "production", "%s_stage2.blend" % chassis)
    has_weapon = bool(chassis) and os.path.isfile(os.path.join(ROOT, wblend))
    wglb = os.path.join("assets", "models", "weapons", "%s.glb" % chassis) if chassis else None
    glb = os.path.join("assets", "models", "characters", "%s.glb" % key)
    B = [BLENDER, "-b", "--python-exit-code", "1"]
    G = os.path.join("tools", "blender", "gf_hero")
    smoke = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "-P", os.path.join(G, "smoke_import.py"), "--", glb,
             "--render", os.path.join(W, "renders", "stage5"), "--report", os.path.join(A, "reports", "export_report.json")]
    if wglb and os.path.isfile(os.path.join(ROOT, wglb)) or has_weapon:
        smoke += ["--weapon", wglb]
    cmds = {
        "weapon": B + [wblend, "-P", os.path.join(G, "export_glb.py"), "--", "--weapon", chassis] if has_weapon else None,
        "export": B + [os.path.join(A, "production", "%s_anim.blend" % key), "-P", os.path.join(G, "export_glb.py"), "--", "--key", key],
        "reimport": smoke,
        "sheet": [COMFY_PY, os.path.join(G, "s5_sheets.py"), key],
        "board": [COMFY_PY, os.path.join(G, "s5_%s_sheets.py" % key)] if os.path.isfile(os.path.join(ROOT, G, "s5_%s_sheets.py" % key)) else None,
        "validate": [sys.executable, os.path.join(G, "validate_glb.py"), glb, "--blender", BLENDER,
                     "--json", os.path.join(W, "stage5_validate.json")],
    }
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    for st in todo:
        if cmds[st] is None:
            print("[stage5] %s: skipped (%s)" % (st, "no gf_hero-built signature weapon" if st == "weapon" else "no s5_%s_sheets.py" % key))
            continue
        print("[stage5] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage5_%s.log" % st))
    print("[stage5] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
