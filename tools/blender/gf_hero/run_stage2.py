"""Run the whole stage-2 production-mesh chain for one hero (plain Python, standard library only).

  python tools/blender/gf_hero/run_stage2.py brax [--from <step>] [--only <step>]

Steps (each one a headless Blender run, or ComfyUI's python for the PIL sheets):
  prepare  s2_prepare_blockout.py  selected stage-1 GLB -> work/<key>_retopo_start.blend (sculpt reference)
  base     s2_body_base.py         MakeHuman hm08 (CC0) via MPFB -> T-pose, 4x reduced, symmetric
  fit      s2_body_fit.py          landmark warp + surface fit to the sculpt, knee loops, arm cut, eyes
  parts    s2_parts.py             gauntlets, belt, sash, skirt cloth + plates, wraps, hair, beard
  texture  s2_texture.py           UVs, bakes, hand-painted NPR base colour + emissive, M_<key>
  review   s2_review.py            review renders (toon / clay / albedo / wire / in-game / silhouette)
  sheets   tools/comfy/stage2_sheets.py  review sheets into reports/stage2/ + concept IoU
  weapon, weapon_texture, weapon_review, weapon_sheets: the same for the hero's signature chassis weapon
           (stage2_fit.json "signature_weapon", art/weapons/<chassis>/): s2_weapon.py builds it around this
           hero's fitted body and puts it in the hand sockets' frame; the hero review renders it attached.

Inputs per hero: art/characters/<key>/stage2_fit.json, stage2_parts.json, stage2_texture.json, palette.json,
references/<KEY>_front_approved.png, the selected sculpt reference named in manifest.json and the
stage-1 mask check (work/maskcheck_raw/<key>_maskcheck_mask.png).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COMFY_PY = os.environ.get("COMFY_PY", r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe")
STEPS = ["prepare", "base", "fit", "parts", "weapon", "texture", "weapon_texture", "review", "weapon_review", "sheets", "weapon_sheets"]


def run(cmd, log_path):
    t = time.time()
    with open(log_path, "w", encoding="utf-8", newline="\n") as log:
        r = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    print("  %-70s %5.0fs  exit %d" % (" ".join(os.path.basename(c) for c in cmd[:4])[:70], time.time() - t, r.returncode))
    if r.returncode != 0:
        print(open(log_path, encoding="utf-8", errors="replace").read()[-3000:])
        raise SystemExit("step failed, log: " + log_path)


def main(argv):
    key = argv[0]
    frm = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    A = os.path.join("art", "characters", key)
    W = os.path.join(A, "work")
    S2 = os.path.join(A, "reports", "stage2")
    man = json.load(open(os.path.join(ROOT, A, "manifest.json")))
    sel = man["selected_sculpt_reference"]
    stem = os.path.splitext(os.path.basename(sel))[0]
    concept = os.path.join(A, "references", "%s_front_approved.png" % key.upper())
    os.makedirs(os.path.join(ROOT, W, "logs"), exist_ok=True)
    B = [BLENDER, "-b", "--python-exit-code", "1", "-P"]
    G = os.path.join("tools", "blender", "gf_hero")
    start = os.path.join(W, "%s_retopo_start.blend" % key)
    cmds = {
        "prepare": B + [os.path.join(G, "s2_prepare_blockout.py"), "--", sel, start, concept, "--height",
                        str(json.load(open(os.path.join(ROOT, A, "stage2_fit.json")))["height_m"]), "--report", os.path.join(S2, "blockout_prepare.json")],
        "base": B + [os.path.join(G, "s2_body_base.py"), "--", os.path.join(W, "%s_s2_body_base.blend" % key),
                     os.path.join(W, "%s_s2_mh_landmarks.json" % key), "--config", os.path.join(A, "stage2_fit.json")],
        "fit": B + [os.path.join(G, "s2_body_fit.py"), "--", os.path.join(W, "%s_s2_body_base.blend" % key),
                    os.path.join(W, "%s_s2_mh_landmarks.json" % key), os.path.join(A, "stage2_fit.json"), start,
                    os.path.join(W, "%s_s2_body.blend" % key), "--report", os.path.join(S2, "body_fit.json")],
        "parts": B + [os.path.join(G, "s2_parts.py"), "--", os.path.join(W, "%s_s2_body.blend" % key), start,
                      os.path.join(A, "stage2_parts.json"), os.path.join(W, "%s_s2_parts.blend" % key), "--report", os.path.join(S2, "parts.json")],
        "texture": B + [os.path.join(G, "s2_texture.py"), "--", os.path.join(W, "%s_s2_parts.blend" % key), start,
                        os.path.join(A, "stage2_texture.json"), os.path.join(S2, "body_fit.json"),
                        os.path.join(A, "production", "%s_stage2.blend" % key), os.path.join(A, "textures"), "--report", os.path.join(S2, "texture.json")],
        "review": B + [os.path.join(G, "s2_review.py"), "--", os.path.join(A, "production", "%s_stage2.blend" % key), os.path.join(W, "renders", "stage2")],
        "sheets": [COMFY_PY, os.path.join("tools", "comfy", "stage2_sheets.py"), os.path.join(W, "renders", "stage2"), S2, concept,
                   os.path.join(W, "maskcheck_raw", "%s_maskcheck_mask.png" % key), os.path.join(A, "textures", "%s_basecolor.png" % key),
                   os.path.join(A, "textures", "%s_emissive.png" % key), "--blockout", os.path.join(W, "renders", stem), stem,
                   "--tag", "%s stage 2" % key.capitalize()],
    }
    wkey = json.load(open(os.path.join(ROOT, A, "stage2_fit.json"))).get("signature_weapon")
    if wkey:
        WA = os.path.join("art", "weapons", wkey)
        WS2 = os.path.join(WA, "reports", "stage2")
        wprod = os.path.join(WA, "production", "%s_stage2.blend" % wkey)
        cmds["weapon"] = B + [os.path.join(G, "s2_weapon.py"), "--", os.path.join(W, "%s_s2_body.blend" % key), os.path.join(WA, "stage2_weapon.json"),
                              os.path.join(S2, "body_fit.json"), os.path.join(WA, "work", "%s_parts.blend" % wkey), "--report", os.path.join(WS2, "parts.json")]
        cmds["weapon_texture"] = B + [os.path.join(G, "s2_texture.py"), "--", os.path.join(WA, "work", "%s_parts.blend" % wkey), "-",
                                      os.path.join(WA, "stage2_texture.json"), "-", wprod, os.path.join(WA, "textures"), "--report", os.path.join(WS2, "texture.json")]
        cmds["review"] = cmds["review"] + ["--attach", wprod]
        cmds["weapon_review"] = B + [os.path.join(G, "s2_review.py"), "--", wprod, os.path.join(WA, "work", "renders", "stage2"), "--weapon"]
        cmds["weapon_sheets"] = [COMFY_PY, os.path.join("tools", "comfy", "stage2_sheets.py"), "--weapon", os.path.join(WA, "work", "renders", "stage2"), WS2,
                                 os.path.join(WA, "textures", "%s_basecolor.png" % wkey), os.path.join(WA, "textures", "%s_emissive.png" % wkey),
                                 "--tag", "%s (weapon) stage 2" % wkey]
        for d in (WS2, os.path.join(WA, "work", "logs")):
            os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    todo = [only] if only else [st for st in STEPS[STEPS.index(frm):] if st in cmds]
    t0 = time.time()
    for st in todo:
        print("[stage2] %s" % st)
        run(cmds[st], os.path.join(ROOT, W, "logs", "stage2_%s.log" % st))
    print("[stage2] done in %.0fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
