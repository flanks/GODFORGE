# Selene, stage 3: the rig (GF_Hero_v1) and the skin

Made by AI (Claude) on 2026-09-27 with the automated Blender 5.2 chain `python tools/blender/gf_hero/s3_selene_run.py`
(about half a minute; Cycles on the CPU for the review renders). No human artist. The review record is one sheet:
[`stage3/stage3_rig.png`](stage3/stage3_rig.png). The user's visual approval is still pending (`status.json`).

## 1. Skeleton

GF_Hero_v1 unchanged (63 contract bones: 23 core, 6 twist, 30 fingers, 4 sockets) plus **32 per-hero `x_` extras** = 95
bones. The joints come from the stage-2 fit (the shared `s3_landmarks.py`: the MakeHuman joints through the stage-2
thin-plate spline, fingers on the glove's cross-sections, sockets from the stage-2 hand frames); `s3_selene_landmarks.py`
finishes the file (`work/selene_landmarks.json`, committed):

| Extra | Parent | What it does |
|---|---|---|
| `x_crown_01..06` | `head_top` | one per storm-crystal shard (01-03 her left, 04-06 her right). Head on the head's vertical axis at the shard's height, tail on the shard's centre: a turn about local X orbits the shard round the head, about local Z bobs it (an arc of ~1.5 cm per 7°), about its own Y spins it. Clips may only rotate joints (the gate: only the pelvis translates), hence the off-shard pivot. |
| `x_knee_L/R` | thigh | driven: a Copy Rotation of the shin at 0.5 (local, mixed AFTER), the Valdris pattern: the pointed knee cop and the knee fin turn half the bend. The export bakes it like the twist bones. |
| `x_cape_{L,R}_01..04`, `x_mantle_{L,R}_01..02` | upperarm | one chain down the middle column of each outer cape and shoulder drape (under the armlets) |
| `x_panel_{L,R}_01..03`, `x_tabard_01..03`, `x_back_01..03` | pelvis | the hip panels, the front tabard and the back panel |

Chain joints sit on each sheet's mid-surface at even steps of the sheet's own `v` (the stage-2 `gf_mask` colour). The
sockets: `weapon_R/L` = the stage-2 hand frames (the launcher's authoring frame); `head_top` = the top of the bun
(2.20 m); `chest_sigil` = the **collar gem's** front face at x = 0, z 1.744 (her emblem, not the bodysuit surface).

## 2. Skin (`s3_skin.py` shared + the hook `s3_selene_skin.py`, config `stage3_skin.json`)

* **BODY** (the bodysuit, face, arms, gloves) exactly as Brax and Valdris: MakeHuman CC0 game_engine weights per vertex,
  half bone heat on the torso and limbs, the twist split, knee / elbow blend bands, Euclidean smoothing at the jaw,
  shoulders and knees. 0 unweighted, max 4 influences.
* **Parts**, per stage-2 piece: hair shell / bun / band / locks on the head; each crown shard 100 % on its `x_crown`;
  the collar a rigid row 60 / 40 neck / spine_03; the gem and its setting on spine_03; the harness straps, neckline trim,
  waist straps, belt band, bracers, back-of-hand plates and the sabaton foot shells copy the body's weights vertex by
  vertex (they follow the skin); belt rings and hip plates one rigid row each (the mean of those copies); armlets, rings
  and blades on the upper arm; each claw on its last phalanx; greaves and sabaton shafts on the shin (the shaft stands
  above the ankle, inside the greave's flare); knee cops and fins on `x_knee`; heel blocks on the foot.
* **Cloth**: by the sheet's own `v`: rows above `v_pin` ride the pin row (capes 60 / 40 upper arm / clavicle, drapes
  75 / 25, skirts the pelvis), below it hat functions along the chain.

## 3. The weapon check

`assets/models/weapons/thundercoil_launcher.glb` (the weapon track's shipped file) is imported into the rig file as
`PREVIEW_thundercoil_launcher` (never exported) and held on `weapon_R` by a Child Of whose inverse is SOCKET_TO_GRIP (the
Blender form of the identity attach). Rest attach error **0.0**; in every validation pose 0.0. In the **hold** pose the
left palm is solved onto the launcher's `grip_L` (0.441 m up the barrel, 0.052 m above the right palm) from the posed
`weapon_R` frame: **0.0 mm** off. The preview has no `_R` suffix on purpose: `s4_anim.build_keepout` would read a
`PREVIEW_*_R` mesh reaching behind the wrist as a SLEEVE weapon (a star-shaped volume round the forearm), which the
carried launcher is not (it pushed the hold 27 cm off the hip).

## 4. Validation poses (`s3_selene_poses.py`, posed by the stage-4 solver, cloth by `selene_cloth.solve_static`)

bind, relaxed carry, the two-handed hold, a firing lunge, a deep crouch (knees 115-120°), Heaven's Verdict (arms up),
a run stride, a chest twist with a head turn. Numbers per pose in `stage3/poses.json` and on the sheet.

## 5. Known limits (no review rounds, by the user's rule)

* The hold needs the chest turned about 36-40° right of the aim (a bladed gunner stance): with a straighter chest the
  left hand cannot reach `grip_L` 0.44 m up the barrel. The clips use the bladed stance for every aimed pose.
* The cloth is posed per frame by `selene_cloth.py` (analytic capsules), not simulated; in the deep crouch 5 of 22 cloth
  bones still graze the legs. The capes' first bone is pinned under the armlet and never cleared.
* The crown bones orbit / bob / spin but cannot move a shard radially outward (rotation only).
* Not run, by the user's rule: `s3_gltf_check.py`, the range-of-motion sweeps and `check_skeleton.py` (the stage-5
  export gate checks the skeleton, the sockets and the weights of the shipped file).
