"""Stage 5, Valdris: the per-hero hook of smoke_import.py (plain data, no bpy).

smoke_import.py loads tools/blender/gf_hero/s5_<key>.py when it exists and takes these three names from it; without
a hook it uses Brax's defaults (jab_r, uppercut, meltdown_start ...), which Valdris does not have.

  REVIEW_SHOTS   (clip, frame) pairs rendered from the SHIPPED files (valdris.glb + the weapon track's
                 colossus_cannon.glb on weapon_R): one row each on reports/stage5/export_review.png. Every frame is a
                 stage-4 key frame, so the sheet's "stage 4 source" column has its render.
  ATTACH_FOLLOW  the clip and frame at which the cannon must ride weapon_R (identity child) in the re-import: the
                 heavy shot, the arm at its fullest recoil.
  CLOSEUP        close-up aim point (Blender metres) and ortho scale: he is 2.33 m to the pauldron tops (Brax 2.2 m).
"""

REVIEW_SHOTS = [
    ("idle_combat@loop", 0),       # the combat guard every upper-layer clip starts and ends on
    ("fire_heavy", 6),             # the colossus_cannon heavy shot ('shot' event)
    ("bulwark_slam", 21),          # active1: the landing ('land' event: Nova)
    ("siege_stance@loop", 0),      # active2: the rooted brace
    ("run@loop", 6),               # locomotion, mid-stride
    ("mountainfall_pound", 15),    # ultimate: the ground pound ('pound' event)
    ("ping", 14),                  # the left gauntlet open, pointing (hand_pose L: open between frames 4 and 16)
]
ATTACH_FOLLOW = ("fire_heavy", 6)
CLOSEUP = ((-0.15, -0.12, 1.12), 3.25)
