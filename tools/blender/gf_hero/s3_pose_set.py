"""The GF_Hero_v1 validation pose set (stage 3), defined from a hero's landmark file so it fits any proportions.

Used by s3_poses.py (review + metrics) and reusable by stage 4 as reference key poses. Adapted from the POSES table of
Ashen Covenant p04_validation_poses.py (FK in degrees on the bone-local axes, IK wrist / ankle targets, hand aims).

Bone-local axes (gf_hero_rig.py): +X swings the child toward the front on both sides (shoulder / elbow / finger flexion
+X, knee flexion -X), Y twists, Z swings toward world +X. For the T-pose arms that means +Z raises the left arm and lowers
the right one. mirror() turns a left-side entry into the right-side one: X kept, Y and Z negated, world x flipped.

Entry keys (s3lib.apply_pose): rot (deg, local XYZ), loc_world (m, world offset of the bone head), aim (world direction),
ik + pole (world target for the bone's tail + the side the middle joint bends toward), aim_after_ik (+ twist, deg; the
value "parent" keeps the joint straight: a sleeve weapon such as the anvil_gauntlets needs the wrist straight, only
twisted, or the rigid sleeve swings through the forearm - see reports/stage3 weapon limits).
The weapon variant per pose: "open" (the weapon's open hand), "fist" (closed-fist variant, the body's fingers clenched
under it) or "none" (bare: body-only stress poses).
"""
from mathutils import Vector

import gf_hero_rig as R


def fist(side, amount=1.0):
    """A closed fist: fingers curl at all three joints, the thumb folds across the middle phalanges."""
    d = {}
    for f in ("index", "middle", "ring", "pinky"):
        d["%s_01_%s" % (f, side)] = {"rot": (80 * amount, 0, 0)}
        d["%s_02_%s" % (f, side)] = {"rot": (95 * amount, 0, 0)}
        d["%s_03_%s" % (f, side)] = {"rot": (60 * amount, 0, 0)}
    z = -30 if side == "L" else 30
    d["thumb_01_%s" % side] = {"rot": (40 * amount, 0, z * amount)}
    d["thumb_02_%s" % side] = {"rot": (45 * amount, 0, 0)}
    d["thumb_03_%s" % side] = {"rot": (35 * amount, 0, 0)}
    return d


def mirror(pose):
    out = {}
    for b, tr in pose.items():
        if not b.endswith("_L"):
            continue
        t = {}
        for k, v in tr.items():
            if k == "rot":
                t[k] = (v[0], -v[1], -v[2])
            elif k in ("ik", "pole", "aim", "aim_after_ik", "loc_world") and not isinstance(v, str):
                t[k] = (-v[0], v[1], v[2])
            elif k == "twist":
                t[k] = -v
            else:
                t[k] = v
        out[b[:-2] + "_R"] = t
    return out


def both(pose_l):
    out = dict(pose_l)
    out.update(mirror(pose_l))
    return out


def merge(*ps):
    out = {}
    for p in ps:
        for b, tr in p.items():
            out.setdefault(b, {}).update(tr)
    return out


def build_poses(lm):
    """[(name, pose, weapon_variant)] for a hero's landmarks, and the fist-only pose (the weapon reference)."""
    V = lambda k: Vector(R.point(lm, k))  # noqa: E731
    S, elL, wrL = V("shoulder_L"), V("elbow_L"), V("wrist_L")
    arm_len = (elL - S).length + (wrL - elL).length
    hipL, knL, anL = V("hip_L"), V("knee_L"), V("ankle_L")
    leg_len = (knL - hipL).length + (anL - knL).length
    foot_dir = tuple((V("ball_L") - anL).normalized())
    toe_dir = tuple((V("toe_L_tip") - V("ball_L")).normalized())
    FISTS = merge(fist("L"), fist("R"))
    STANCE = both({"thigh_L": {"rot": (6, 0, 5)}, "shin_L": {"rot": (-10, 0, 0)}, "foot_L": {"rot": (4, 0, 0)}})
    APOSE = both({"upperarm_L": {"rot": (4, 0, -47)}, "lowerarm_L": {"rot": (14, 0, 0)}})

    def at(x, dy, dz):
        """A left-side point: world x, and y / z relative to the left shoulder."""
        return (x, S.y + dy, S.z + dz)

    def planted(drop, back=0.0, pole_fwd=0.6):
        return merge({"pelvis": {"loc_world": (0, back, -drop)}},
                     both({"shin_L": {"ik": tuple(anL), "pole": (anL.x + 0.25, anL.y - pole_fwd, knL.z)},
                           "foot_L": {"aim_after_ik": foot_dir}, "toe_L": {"aim_after_ik": toe_dir}}))

    guard_l = {"lowerarm_L": {"ik": at(0.25, -0.52, -0.02), "pole": at(0.55, 0.0, -0.75)},
               "hand_L": {"aim_after_ik": "parent", "twist": -70}}
    poses = [
        ("bind", {}, "open"),
        ("apose", merge(APOSE, FISTS), "fist"),
        ("punch_both", merge(
            {"spine_01": {"rot": (5, 0, 0)}, "spine_02": {"rot": (4, 0, 0)}},
            both({"clavicle_L": {"rot": (10, 0, 0)},
                  "lowerarm_L": {"ik": at(0.20, -0.94 * arm_len, -0.05), "pole": at(0.40, -0.3, -0.7)},
                  "hand_L": {"aim_after_ik": "parent"}}), STANCE, FISTS), "fist"),
        ("guard", merge(
            {"spine_01": {"rot": (6, 0, 0)}, "spine_02": {"rot": (5, 0, 0)}, "neck": {"rot": (-4, 0, 0)}, "head": {"rot": (4, 0, 0)}},
            both(dict(guard_l, clavicle_L={"rot": (8, 0, -4)})), STANCE, FISTS), "fist"),
        ("deep_squat", merge(
            planted(0.52 * leg_len, back=0.16, pole_fwd=0.7),
            {"spine_01": {"rot": (22, 0, 0)}, "spine_02": {"rot": (10, 0, 0)}, "spine_03": {"rot": (4, 0, 0)},
             "neck": {"rot": (-18, 0, 0)}, "head": {"rot": (-12, 0, 0)}},
            both({"lowerarm_L": {"ik": at(0.24, -0.78 * arm_len, -0.62), "pole": at(0.6, 0.0, -1.0)},
                  "hand_L": {"aim_after_ik": "parent"}}), FISTS), "fist"),
        ("lunge_cross", merge(
            {"pelvis": {"loc_world": (0, 0.05, -0.36 * leg_len)}},
            {"shin_L": {"ik": (anL.x - 0.02, anL.y - 0.62, anL.z), "pole": (anL.x + 0.2, anL.y - 1.2, knL.z)},
             "foot_L": {"aim_after_ik": foot_dir}, "toe_L": {"aim_after_ik": toe_dir},
             "shin_R": {"ik": (-anL.x + 0.02, anL.y + 0.62, anL.z + 0.14), "pole": (-anL.x - 0.1, anL.y - 0.4, 0.0)},
             "foot_R": {"aim_after_ik": (0.0, -0.45, -0.9)}, "toe_R": {"aim_after_ik": (0.0, -1.0, -0.05)}},
            {"spine_01": {"rot": (4, 10, 0)}, "spine_02": {"rot": (4, 12, 0)}, "spine_03": {"rot": (2, 8, 0)},
             "neck": {"rot": (0, -16, 0)}, "head": {"rot": (0, -12, 0)}, "clavicle_R": {"rot": (14, 0, 0)},
             "lowerarm_R": {"ik": (0.05, S.y - 0.98 * arm_len, S.z - 0.08), "pole": (-0.4, S.y - 0.3, S.z - 0.8)},
             "hand_R": {"aim_after_ik": "parent"},
             "lowerarm_L": {"ik": (0.36, S.y - 0.50, S.z - 0.02), "pole": (0.8, S.y + 0.05, S.z - 0.8)},
             "hand_L": {"aim_after_ik": "parent", "twist": -70}}, FISTS), "fist"),
        ("torso_twist", merge(
            {"spine_01": {"rot": (0, 20, 0)}, "spine_02": {"rot": (0, 20, 0)}, "spine_03": {"rot": (0, 15, 0)}, "neck": {"rot": (0, -10, 0)}},
            both({"upperarm_L": {"rot": (20, 0, -55)}, "lowerarm_L": {"rot": (60, 0, 0)}}), FISTS), "fist"),
        ("head_left_down", merge({"neck": {"rot": (10, 25, 0)}, "head": {"rot": (16, 35, 4)}}, APOSE, FISTS), "fist"),
        ("head_right_up", merge({"neck": {"rot": (-10, -25, 0)}, "head": {"rot": (-22, -35, -4)}}, APOSE, FISTS), "fist"),
        ("fist_clench", merge(both({"upperarm_L": {"rot": (38, 0, -58)}, "lowerarm_L": {"rot": (88, 0, 0)}}), FISTS), "fist"),
        ("uppercut", merge(
            {"pelvis": {"loc_world": (0, 0, -0.06)}, "spine_01": {"rot": (-6, -12, 0)}, "spine_02": {"rot": (-6, -10, 0)},
             "spine_03": {"rot": (-4, -6, 0)}, "neck": {"rot": (-8, 10, 0)}, "head": {"rot": (-6, 8, 0)},
             "clavicle_L": {"rot": (0, 0, 16)},
             "upperarm_L": {"aim": (0.16, -0.30, 1.0)}, "lowerarm_L": {"aim": (0.05, -0.34, 1.0)},
             "hand_L": {"aim_after_ik": "parent", "twist": -90},
             "lowerarm_R": {"ik": (-0.34, S.y + 0.10, S.z - 0.45), "pole": (-0.8, S.y + 0.5, S.z - 0.6)},
             "hand_R": {"aim_after_ik": "parent", "twist": 80}}, STANCE, FISTS), "fist"),
        ("forearm_twist", merge(
            both({"lowerarm_L": {"ik": at(0.30, -0.9 * arm_len, -0.1), "pole": at(0.6, -0.2, -0.8)},
                  "hand_L": {"aim_after_ik": "parent", "twist": -100}}), FISTS), "fist"),
        ("elbow_knee_max", merge(
            both({"upperarm_L": {"rot": (30, 0, -65)}, "lowerarm_L": {"rot": (145, 0, 0)}}),
            {"thigh_L": {"rot": (112, 0, 8)}, "shin_L": {"rot": (-135, 0, 0)}, "foot_L": {"rot": (-10, 0, 0)}}, FISTS), "none"),
    ]
    return poses, FISTS
