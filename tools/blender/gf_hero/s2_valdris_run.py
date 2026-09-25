"""Run Valdris's whole stage-2 chain (plain Python, standard library only). Brax keeps run_stage2.py.

  python tools/blender/gf_hero/s2_valdris_run.py [--from <step>] [--only <step>]

Steps (each a headless Blender run, or ComfyUI's python for the PIL sheets):
  prepare   s2_prepare_blockout.py (shared)  selected stage-1 GLB -> work/valdris_retopo_start.blend (sculpt reference)
  base      s2_body_base.py (shared)         MakeHuman hm08 (CC0) via MPFB, T-pose, 4x reduced, symmetric
  fit       s2_body_fit.py (shared)          landmark warp (proportions), knee / elbow / wrist loops, hand frames
  conform   s2_valdris_body.py               under-suit girth: legs to the blockout's outer envelope, barrel torso,
                                             forearms centred on the arm axis, hand frames on the forearm axis
  parts     s2_valdris_parts.py              armour, beard, cape (stage2_parts.json)
  texture   s2_texture.py (shared, Valdris zones + s2_valdris_paint.py)   UVs, bakes, NPR base colour, emissive,
                                             tangent normal map from the blockout, M_valdris
  gltf_check  s2_gltf_check.py (shared)      scratch GLB: textures, tangents, no unloadable extensions
  review    s2_valdris_review.py             Cycles-CPU toon review renders (never EEVEE: the GPU is shared), the
                                             colossus_cannon GLB on the right hand frame, fit / penetration check
  sheets    s2_valdris_sheets.py (ComfyUI python)   review sheets into reports/stage2/ + concept IoU (+ the before /
                                             after sheet when work/renders/stage2_before holds an earlier build's renders)

The weapon is NOT built here: colossus_cannon is owned by the weapon track (art/weapons/colossus_cannon/).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe")
STEPS = ["prepare", "base", "fit", "conform", "parts", "texture", "gltf_check", "review", "sheets"]
KEY = "valdris"


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
    concept = os.path.join(A, "references", "valdris_concept_front_mirrored.png")
    mask = os.path.join(A, "references", "valdris_concept_front_mirrored_mask.png")
    sel = os.path.join(A, "source", "valdris_trellis2_s202.glb")
    fitj, partsj, texj = (os.path.join(A, n) for n in ("stage2_fit.json", "stage2_parts.json", "stage2_texture.json"))
    start = os.path.join(W, "valdris_retopo_start.blend")
    lm = os.path.join(W, "valdris_s2_mh_landmarks.json")
    prod = os.path.join(A, "production", "valdris_stage2.blend")
    cannon = os.path.join("assets", "models", "weapons", "colossus_cannon.glb")
    cmds = {
        "prepare": B + [os.path.join(G, "s2_prepare_blockout.py"), "--", sel, start, concept, "--height", "2.3",
                        "--concept-fig", "190,1009,394", "--report", os.path.join(S2, "blockout_prepare.json")],
        "base": B + [os.path.join(G, "s2_body_base.py"), "--", os.path.join(W, "valdris_s2_body_base.blend"), lm, "--config", fitj],
        "fit": B + [os.path.join(G, "s2_body_fit.py"), "--", os.path.join(W, "valdris_s2_body_base.blend"), lm, fitj, start,
                    os.path.join(W, "valdris_s2_body_fit.blend"), "--report", os.path.join(S2, "body_fit.json")],
        "conform": B + [os.path.join(G, "s2_valdris_body.py"), "--", os.path.join(W, "valdris_s2_body_fit.blend"), start, fitj,
                        os.path.join(W, "valdris_s2_body.blend"), "--report", os.path.join(S2, "body_conform.json"),
                        "--fit-report", os.path.join(S2, "body_fit.json")],
        "parts": B + [os.path.join(G, "s2_valdris_parts.py"), "--", os.path.join(W, "valdris_s2_body.blend"), start, partsj, fitj, lm,
                      os.path.join(W, "valdris_s2_parts.blend"), "--report", os.path.join(S2, "parts.json")],
        "texture": B + [os.path.join(G, "s2_texture.py"), "--", os.path.join(W, "valdris_s2_parts.blend"), start, texj,
                        os.path.join(S2, "body_fit.json"), prod, os.path.join(A, "textures"), "--report", os.path.join(S2, "texture.json")],
        "gltf_check": [BLENDER, "-b", prod, "--python-exit-code", "1", "-P", os.path.join(G, "s2_gltf_check.py"), "--",
                       os.path.join(W, "gltf_check", "valdris.glb"), os.path.join(S2, "gltf_check.json")],
        "review": B + [os.path.join(G, "s2_valdris_review.py"), "--", prod, os.path.join(W, "renders", "stage2"), "--ref", start,
                       "--cannon", cannon, "--fit", os.path.join(S2, "body_fit.json"), "--report", os.path.join(S2, "review.json")],
        "sheets": [COMFY_PY, os.path.join(G, "s2_valdris_sheets.py"), os.path.join(W, "renders", "stage2"), S2, concept, mask,
                   os.path.join(A, "textures"), os.path.join(W, "renders", "valdris_trellis2_s202"), "valdris_trellis2_s202",
                   os.path.join(W, "renders", "stage2_before")],
    }
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, S2), exist_ok=True)
    todo = [only] if only else STEPS[STEPS.index(frm):]
    t0 = time.time()
    for st in todo:
        print("[valdris stage2] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage2_%s.log" % st))
    print("[valdris stage2] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
