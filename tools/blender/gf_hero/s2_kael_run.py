"""Run Kael's whole stage-2 chain (plain Python, standard library only). Brax keeps run_stage2.py, Valdris
s2_valdris_run.py.

  python tools/blender/gf_hero/s2_kael_run.py [--from <step>] [--only <step>]

Steps (each a headless Blender run, or ComfyUI's python for the PIL sheets):
  prepare   s2_prepare_blockout.py (shared)  selected stage-1 GLB (s202) -> work/kael_retopo_start.blend (sculpt reference)
  recentre  s2_kael_recentre.py              the body's centre line onto the origin (the duster trails behind him)
  base      s2_body_base.py (shared)         MakeHuman hm08 (CC0) via MPFB, lean macro, T-pose, 4x reduced, symmetric
  fit       s2_body_fit.py (shared)          landmark warp (proportions), thigh fit, knee / elbow / wrist loops, lean
                                             forearms, hand frames, eyeballs
  parts     s2_kael_parts.py                 duster (yoke, sleeves, skirt with a back vent, collar, lapels, cuffs), the
                                             ghost-flame tatters, scarf, loin cloth, belts, bandolier, holster, pouch,
                                             straps, bracer, boots, hair, chin beard (stage2_parts.json)
  texture   s2_texture.py (shared, Kael zones + s2_kael_paint.py)   UVs, bakes, NPR base colour, emissive, tangent
                                             normal map from the blockout, M_kael
  gltf_check  s2_gltf_check.py (shared)      scratch GLB: textures, tangents, no unloadable extensions
  review    s2_kael_review.py                Cycles-CPU toon review renders (never EEVEE: the GPU is shared), the
                                             serpent_smg GLB on the right hand frame
  sheets    s2_kael_sheets.py (ComfyUI python)   review sheets into reports/stage2/ + concept IoU

The weapon is NOT built here: serpent_smg is owned by the weapon track (assets/models/weapons/serpent_smg.glb).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe")
STEPS = ["prepare", "recentre", "base", "fit", "parts", "texture", "gltf_check", "review", "sheets"]
KEY = "kael"


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-70s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:6])[:70], time.time() - t, r.returncode))
    if r.returncode != 0:
        print(open(log_path, encoding="utf-8", errors="replace").read()[-3000:])
        raise SystemExit("step failed, log: " + log_path)


def main(argv):
    frm = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    A = os.path.join("art", "characters", KEY)
    W = os.path.join(A, "work")
    S2 = os.path.join(A, "reports", "stage2")
    G = os.path.join("tools", "blender", "gf_hero")
    B = [BLENDER, "-b", "--python-exit-code", "1", "-P"]
    concept = os.path.join(A, "references", "KAEL_front_approved.png")
    mask = os.path.join(A, "references", "kael_concept_front_nogun_mask.png")
    sel = os.path.join(A, "source", "kael_trellis2_s202.glb")
    fitj, partsj, texj = (os.path.join(A, n) for n in ("stage2_fit.json", "stage2_parts.json", "stage2_texture.json"))
    start = os.path.join(W, "kael_retopo_start.blend")
    lm = os.path.join(W, "kael_s2_mh_landmarks.json")
    prod = os.path.join(A, "production", "kael_stage2.blend")
    smg = os.path.join("assets", "models", "weapons", "serpent_smg.glb")
    cmds = {
        "prepare": B + [os.path.join(G, "s2_prepare_blockout.py"), "--", sel, start, concept, "--height", "2.1",
                        "--concept-fig", "27,998,752", "--report", os.path.join(S2, "blockout_prepare.json")],
        "recentre": B + [os.path.join(G, "s2_kael_recentre.py"), "--", start, "--offset", "0.03,0.225,0",
                         "--report", os.path.join(S2, "blockout_prepare.json")],
        "base": B + [os.path.join(G, "s2_body_base.py"), "--", os.path.join(W, "kael_s2_body_base.blend"), lm, "--config", fitj],
        "fit": B + [os.path.join(G, "s2_body_fit.py"), "--", os.path.join(W, "kael_s2_body_base.blend"), lm, fitj, start,
                    os.path.join(W, "kael_s2_body.blend"), "--report", os.path.join(S2, "body_fit.json")],
        "parts": B + [os.path.join(G, "s2_kael_parts.py"), "--", os.path.join(W, "kael_s2_body.blend"), start, partsj, fitj, lm,
                      os.path.join(W, "kael_s2_parts.blend"), "--report", os.path.join(S2, "parts.json"),
                      "--fit-report", os.path.join(S2, "body_fit.json")],
        "texture": B + [os.path.join(G, "s2_texture.py"), "--", os.path.join(W, "kael_s2_parts.blend"), start, texj,
                        os.path.join(S2, "body_fit.json"), prod, os.path.join(A, "textures"), "--report", os.path.join(S2, "texture.json")],
        "gltf_check": [BLENDER, "-b", prod, "--python-exit-code", "1", "-P", os.path.join(G, "s2_gltf_check.py"), "--",
                       os.path.join(W, "gltf_check", "kael.glb"), os.path.join(S2, "gltf_check.json")],
        "review": B + [os.path.join(G, "s2_kael_review.py"), "--", prod, os.path.join(W, "renders", "stage2"),
                       "--smg", smg, "--fit", os.path.join(S2, "body_fit.json"), "--report", os.path.join(S2, "review.json")],
        "sheets": [COMFY_PY, os.path.join(G, "s2_kael_sheets.py"), os.path.join(W, "renders", "stage2"), S2, concept, mask,
                   os.path.join(A, "textures"), os.path.join(W, "renders", "kael_trellis2_s202"), "kael_trellis2_s202"],
    }
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, S2), exist_ok=True)
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    for st in todo:
        print("[kael stage2] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage2_%s.log" % st))
    print("[kael stage2] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
