"""GF_Hero_v1 contract check (standard library only; run by .github/workflows/art.yml and by run_stage3.py).

  python tools/blender/gf_hero/check_skeleton.py

For every hero under art/characters/<key>/ that has a landmark file (work/<key>_landmarks.json, committed):
  * the landmark file passes gf_hero_rig.validate_landmarks (every key, no zero-length bone, unit vectors, perpendicular
    socket frames, a symmetric rest pose, weapon sockets on the hands, per-hero bones prefixed x_) and names the current
    contract version;
  * when stage 3 is marked done in status.json: reports/stage3/skin.json says the weight check passed with the contract's
    bone count, reports/stage3/gltf_check.json says the export check passed (joints, hierarchy, <= 4 influences, socket
    frames, the weapon's identity attach), and the user's visual approval of the rig is recorded as the stage's human gate
    (item user_visual_approval; the AI makes the rig, the user approves it - decision of 2026-09-25).
Exit 1 on any problem. Nothing here needs Blender: the contract tables in gf_hero_rig.py are plain data.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gf_hero_rig as R  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    problems = []
    heroes = 0
    for lm_path in sorted(glob.glob(os.path.join(ROOT, "art", "characters", "*", "work", "*_landmarks.json"))):
        key = os.path.basename(os.path.dirname(os.path.dirname(lm_path)))
        if os.path.basename(lm_path) != "%s_landmarks.json" % key:
            continue
        heroes += 1
        lm = load(lm_path)
        for p in R.validate_landmarks(lm):
            problems.append("%s landmarks: %s" % (key, p))
        want = "%s v%d" % (R.RIG_NAME, R.CONTRACT_VERSION)
        if lm.get("_meta", {}).get("contract") != want:
            problems.append("%s landmarks: contract %r, expected %r" % (key, lm.get("_meta", {}).get("contract"), want))
        A = os.path.join(ROOT, "art", "characters", key)
        st_path = os.path.join(A, "status.json")
        stage = load(st_path).get("stages", {}).get("3_rig", {}) if os.path.exists(st_path) else {}
        if stage.get("status") in ("done", "pending_human"):
            skin_p = os.path.join(A, "reports", "stage3", "skin.json")
            gl_p = os.path.join(A, "reports", "stage3", "gltf_check.json")
            if not os.path.exists(skin_p):
                problems.append("%s: stage 3 is %s but reports/stage3/skin.json is missing" % (key, stage.get("status")))
            else:
                skin = load(skin_p)
                if not skin.get("weight_check", {}).get("ok"):
                    problems.append("%s: stage-3 weight check failed: %s" % (key, skin.get("weight_check")))
                n = len(R.contract_bone_names()) + skin.get("bones", {}).get("extras", 0)
                if skin.get("bones", {}).get("total") != n:
                    problems.append("%s: rig has %s bones, the contract needs %d" % (key, skin.get("bones", {}).get("total"), n))
            if not os.path.exists(gl_p):
                problems.append("%s: stage 3 is %s but reports/stage3/gltf_check.json is missing" % (key, stage.get("status")))
            elif not load(gl_p).get("ok"):
                problems.append("%s: stage-3 glTF check failed: %s" % (key, load(gl_p).get("failures")))
            gate = stage.get("items", {}).get("user_visual_approval", {})
            if not gate.get("human_signoff_required") or (gate.get("status") == "done" and not (gate.get("approved_by") or gate.get("signed_off_by"))):
                problems.append("%s: stage 3 needs the item user_visual_approval (the human gate)" % key)
    for p in problems:
        print("ERROR", p)
    print("GF_Hero_v1 contract: %d hero landmark file(s), %d problem(s)" % (heroes, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
