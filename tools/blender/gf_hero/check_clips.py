"""GF_Hero_v1 clip contract check (standard library only; run by .github/workflows/art.yml and by run_stage4.py).

  python tools/blender/gf_hero/check_clips.py

For every hero whose status.json marks stage 4 (4_animation) done, reads art/characters/<key>/reports/anim/clips.json
(s4_anim.py) and reports/anim/gltf_check.json (s4_gltf_check.py) and checks:
  * every shared clip of s4_contract.SHARED_CLIPS is there, with its loop flag and layer, named <key>_<clip>[@loop];
  * the hero has 6 to 10 unique clips (family == key), all lower_snake_case;
  * 30 fps; clips are in place (root, twist bones and sockets are not in the keyed set);
  * loops: the last frame is the first and the seam is no rougher than the clip itself;
  * planted feet drift <= s4_contract.MAX_FOOT_SLIDE_MM in world space (clips marked slide_exempt excepted), the wrist of a
    sleeve weapon never bends, no effector is asked for more than the limb can reach, the feet stay out of the ground;
  * the glTF export check passed (one animation per clip, durations, in place, loops closed, no required extensions).
Exit 1 on any problem.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gf_hero_rig as R  # noqa: E402
import s4_contract as SC  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_hero(key, A):
    probs = []
    man_p = os.path.join(A, "reports", "anim", "clips.json")
    gl_p = os.path.join(A, "reports", "anim", "gltf_check.json")
    if not os.path.exists(man_p):
        return ["%s: stage 4 is done but reports/anim/clips.json is missing" % key]
    man = load(man_p)
    clips = man.get("clips", {})
    if man.get("fps") != SC.FPS:
        probs.append("%s: fps %s, expected %d" % (key, man.get("fps"), SC.FPS))
    keyed = set(man.get("keyed_bones", []))
    never = {"root"} | set(R.twist_bone_names()) | set(R.SOCKET_NAMES)
    if keyed & never:
        probs.append("%s: keyed bones include %s (root, twist bones and sockets are never keyed)" % (key, sorted(keyed & never)))
    for name, loop, layer in SC.SHARED_CLIPS:
        c = clips.get(name)
        if c is None:
            probs.append("%s: shared clip %s is missing" % (key, name))
            continue
        if c["loop"] != loop or c["layer"] != layer:
            probs.append("%s: %s loop/layer %s/%s, contract %s/%s" % (key, name, c["loop"], c["layer"], loop, layer))
        if c["action"] != SC.action_name(key, name, loop):
            probs.append("%s: %s is named %s, expected %s" % (key, name, c["action"], SC.action_name(key, name, loop)))
    shared = {n for n, _l, _y in SC.SHARED_CLIPS}
    unique = [n for n, c in clips.items() if n not in shared]
    if not (SC.UNIQUE_MIN <= len(unique) <= SC.UNIQUE_MAX):
        probs.append("%s: %d unique clips, the pipeline wants %d-%d" % (key, len(unique), SC.UNIQUE_MIN, SC.UNIQUE_MAX))
    for n in unique:
        c = clips[n]
        if c.get("family") != key:
            probs.append("%s: unique clip %s has family %s" % (key, n, c.get("family")))
        if c["action"] != SC.action_name(key, n, c["loop"]):
            probs.append("%s: %s is named %s" % (key, n, c["action"]))
    for n, c in clips.items():
        if not SC.CLIP_NAME.match(n):
            probs.append("%s: clip name %r is not lower_snake_case" % (key, n))
        m = c.get("metrics", {})
        if c["loop"] and not m.get("seam_ok"):
            probs.append("%s: %s loop seam is not clean (%s deg, accel %s vs %s)" % (
                key, n, m.get("loop_seam_deg"), m.get("seam_accel_deg"), m.get("interior_accel_max_deg")))
        if not c.get("slide_exempt") and m.get("foot_slide_max_mm", 0) > SC.MAX_FOOT_SLIDE_MM:
            probs.append("%s: %s planted feet slide %.1f mm" % (key, n, m["foot_slide_max_mm"]))
        if c.get("weapon") == "fist" and m.get("wrist_swing_max_deg", 0) > SC.MAX_WRIST_SWING_DEG:
            probs.append("%s: %s bends the wrist %.2f deg under a sleeve weapon" % (key, n, m["wrist_swing_max_deg"]))
        if m.get("ik_miss_max_mm", 0) > SC.MAX_IK_MISS_MM:
            probs.append("%s: %s asks a limb for %.0f mm more than it reaches" % (key, n, m["ik_miss_max_mm"]))
        if m.get("ground_penetration_mm", 0) < -SC.MAX_GROUND_PENETRATION_MM:
            probs.append("%s: %s puts a foot %.0f mm into the ground" % (key, n, -m["ground_penetration_mm"]))
    if not os.path.exists(gl_p):
        probs.append("%s: reports/anim/gltf_check.json is missing" % key)
    else:
        gl = load(gl_p)
        if not gl.get("ok"):
            probs.append("%s: the glTF clip check failed: %s" % (key, gl.get("failures")))
        if gl.get("animations") != len(clips):
            probs.append("%s: the GLB has %s animations for %d clips" % (key, gl.get("animations"), len(clips)))
    return probs


def main():
    problems = []
    heroes = 0
    for st_path in sorted(glob.glob(os.path.join(ROOT, "art", "characters", "*", "status.json"))):
        A = os.path.dirname(st_path)
        key = os.path.basename(A)
        stage = load(st_path).get("stages", {}).get("4_animation", {})
        if stage.get("status") not in ("done", "pending_human"):
            continue
        heroes += 1
        problems += check_hero(key, A)
    for p in problems:
        print("ERROR", p)
    print("GF_Hero_v1 clips: %d animated hero(es), %d problem(s)" % (heroes, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
