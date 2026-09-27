"""Stage 5, Selene: the per-hero hook of smoke_import.py (plain data, no bpy).

smoke_import.py loads tools/blender/gf_hero/s5_<key>.py when it exists and takes these three names from it; without a
hook it uses Brax's defaults (jab_r, uppercut, meltdown_start ...), which Selene does not have.

  REVIEW_SHOTS   (clip, frame) pairs rendered from the SHIPPED files (selene.glb + the weapon track's
                 thundercoil_launcher.glb on weapon_R): one row each on reports/stage5/export_review.png. Every frame is a
                 stage-4 key frame.
  ATTACH_FOLLOW  the clip and frame at which the launcher must ride weapon_R (identity child) in the re-import: the heavy
                 shot's release.
  CLOSEUP        close-up aim point (Blender metres) and ortho scale: she is 2.2 m to the top of the bun.
"""

REVIEW_SHOTS = [
    ("idle_combat@loop", 0),       # the combat hold every upper-layer clip starts and ends on
    ("fire_heavy", 7),             # the charged shot's release ('shot' event)
    ("arc_nova", 6),               # active1: the cast ('cast' event), both hands thrown forward
    ("run@loop", 6),               # locomotion, mid-stride, the launcher held on the aim
    ("blink_in", 3),               # active2: the arrival ('land' event)
    ("heavens_verdict@loop", 15),  # ultimate: hovering, arms raised to the storm
    ("idle_signature@loop", 22),   # the signature hover
]
ATTACH_FOLLOW = ("fire_heavy", 7)
CLOSEUP = ((-0.1, -0.15, 1.12), 3.1)
