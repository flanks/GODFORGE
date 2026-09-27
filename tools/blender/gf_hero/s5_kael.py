"""Stage 5, Kael: the per-hero hook of smoke_import.py (plain data, no bpy).

smoke_import.py loads tools/blender/gf_hero/s5_<key>.py when it exists and takes these three names from it; without a
hook it uses Brax's defaults (jab_r, uppercut, meltdown_start ...), which Kael does not have.

  REVIEW_SHOTS   (clip, frame) pairs rendered from the SHIPPED files (kael.glb + the weapon track's serpent_smg.glb on
                 weapon_R): one row each on reports/stage5/export_review.png. Every frame is a stage-4 key frame, so the
                 sheet's "stage 4 source" column has its render (work/renders/stage4/<clip>/fNNN_front.png).
  ATTACH_FOLLOW  the clip and frame at which the gun must ride weapon_R (identity child) in the re-import: the heavy
                 shot's muzzle kick.
  CLOSEUP        close-up aim point (Blender metres) and ortho scale: 2.16 m to the hair tips, the duster flares 0.6 m.
"""

REVIEW_SHOTS = [
    ("idle_combat@loop", 0),       # the aim every upper-layer clip starts and ends on
    ("fire_heavy", 9),             # the braced two-handed shot, the muzzle kick
    ("fan_of_blades", 8),          # active1: the ghost hand fans across the gun ('burst')
    ("shadow_roll", 6),            # active2: upside down in the roll
    ("run@loop", 6),               # locomotion, mid-stride, the duster streaming
    ("bullet_ballet@loop", 0),     # ultimate: the twin-pistol stance
    ("idle_signature@loop", 70),   # the ghost hand held up in front of him
]
ATTACH_FOLLOW = ("fire_heavy", 9)
CLOSEUP = ((0.0, -0.05, 1.08), 2.8)


# ---- the sidecar's weapon text ------------------------------------------------------------------------------------------
# export_glb.py writes the sleeve-weapon wording (Valdris's colossus_cannon) for any default weapon without an offhand
# node or hand variants. The serpent_smg is a one-handed gun held in the right fist, so after the export
# (python tools/blender/gf_hero/s5_kael.py --sidecar) the two texts are replaced; nothing else in the sidecar changes.
ATTACH_TEXT = ("weapon scene = identity child of weapon_R: the serpent_smg (one-handed, the weapon track's GLB) sits in the "
               "right fist, its grip_R on the palm frame; it has no offhand node. The left (ghost) hand is his own; the "
               "Bullet Ballet twin pistol is a VFX copy on weapon_L (kael_fire_twin fires it)")
VARIANT_TEXT = ("clip_info.<clip>.weapon_variant is null: serpent_smg has no hand variants, so nothing swaps. The right hand "
                "stays curled round the grip in every clip; clip_info.<clip>.hand_pose lists each hand's fist / open state "
                "for reference")


def fix_sidecar():
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "assets", "models", "characters", "kael.meta.json")
    with open(p, encoding="utf-8") as f:
        meta = json.load(f)
    meta["weapon"]["attach"] = ATTACH_TEXT
    meta["playback"]["weapon_variant"] = VARIANT_TEXT
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")
    print("kael.meta.json: weapon texts set")


if __name__ == "__main__":
    import sys
    if "--sidecar" in sys.argv:
        fix_sidecar()
