"""The GF_Hero_v1 clip contract (stage 4), plain data: read by s4_anim.py (Blender) and check_clips.py (stdlib, CI).

Every hero on GF_Hero_v1 ships the SHARED clips under the same {clip} names, plus 6 to 10 unique clips named after its
kit. In the hero's GLB each clip is the animation "<key>_<clip>", loops add "@loop" (ARCHITECTURE section 9,
docs/art/GF_HERO_SKELETON.md section 8). The client maps a sim state to format!("{key}_{clip}") and never special-cases
a hero.
"""
import re

# (clip, loop, layer): the shared set, in library order. layer "upper" = designed to layer spine_01 and its children
# over locomotion; its first and last frame are the idle_combat reference pose.
SHARED_CLIPS = [
    ("idle", True, "full"),
    ("idle_combat", True, "full"),
    ("walk", True, "full"),
    ("run", True, "full"),
    ("strafe_left", True, "full"),
    ("strafe_right", True, "full"),
    ("backpedal", True, "full"),
    ("dash", False, "full"),
    ("dash_recover", False, "full"),
    ("fire_light", False, "upper"),
    ("fire_heavy", False, "upper"),
    ("fire_charge", True, "upper"),
    ("hit_light", False, "upper"),
    ("hit_heavy", False, "full"),
    ("knockdown", False, "full"),
    ("get_up", False, "full"),
    ("death", False, "full"),
    ("downed", True, "full"),
    ("revive", False, "full"),
    ("reforge_in", False, "full"),
    ("victory", False, "full"),
    ("ping", False, "upper"),
    ("interact", False, "full"),
    ("forge_hammer", True, "full"),
]
UNIQUE_MIN, UNIQUE_MAX = 6, 10
FPS = 30
CLIP_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# quality gates (the clips are validated by these numbers and by the review renders, not by tests)
MAX_FOOT_SLIDE_MM = 10.0        # a planted ball joint may drift this much in world space inside one contact
MAX_WRIST_SWING_DEG = 0.01      # sleeve weapons: the hand only twists
MAX_IK_MISS_MM = 60.0           # an effector the limb cannot reach (soft IK) - larger means a pose asks for too much
MAX_GROUND_PENETRATION_MM = 15.0


def action_name(key, clip, loop):
    return "%s_%s%s" % (key, clip, "@loop" if loop else "")
