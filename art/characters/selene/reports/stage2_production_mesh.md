# Selene — stage 2 production mesh (made by AI, 2026-09-27)

Made by the AI pipeline, not a stand-in. There is no human artist (the user's decision of 2026-09-25); the user's visual
approval is the only human gate left (`status.json` item `user_visual_approval: pending_human`). One command rebuilds
it from the committed inputs in about 2.5 minutes on the CPU (the GPU is shared with ComfyUI and the Kael track):

```sh
python tools/blender/gf_hero/s2_selene_run.py            # [--from <step>] [--only <step>]
```

Review sheets (one set, Cycles CPU / Workbench, never EEVEE): [`stage2/stage2_vs_concept.png`](stage2/stage2_vs_concept.png),
[`stage2/stage2_turnaround.png`](stage2/stage2_turnaround.png), [`stage2/stage2_ingame.png`](stage2/stage2_ingame.png),
[`stage2/stage2_closeups.png`](stage2/stage2_closeups.png), [`stage2/stage2_wireframe.png`](stage2/stage2_wireframe.png),
[`stage2/stage2_textures.png`](stage2/stage2_textures.png), [`stage2/stage2_armed.png`](stage2/stage2_armed.png).

## 1. Deliverables

| File | What |
|---|---|
| `production/selene_stage2.blend` (Git LFS) | 13 objects, one material `M_selene`, zones kept as the face attribute `gf_zone`, rigid-piece / cloth ids as `gf_piece` |
| `textures/selene_basecolor.png` (2048², sRGB, LFS) | hand-painted NPR base colour from `palette.json`, no baked lighting |
| `textures/selene_emissive.png` (2048², sRGB, LFS) | eyes, collar gem, arm + cheek lightning veins, greave and sabaton V slots, the six crown crystals, the claws, the bun band (0.5 % of the atlas) |
| `textures/selene_normal.png` (2048², Non-Color, LFS) | tangent-space normal map (OpenGL +Y) baked from the recentred s303 blockout (hit-distance and tilt filtered) |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | the hand-edited inputs |
| `reports/stage2/*.json` | blockout_prepare (+ recentre), body_fit (hand frames, eyes), parts (piece table, cloth chains), texture, gltf_check, review |

## 2. Proportions

2.2 m to the top of the bun (the brief and the blockout), span 2.00 m (concept 1.99 m). The body is the CC0 MakeHuman
hm08 base (MPFB used as a tool only), a tall slender woman (gender 0, weight 0.42, muscle 0.55, cup 0.9), landmark-warped
to the blockout's heights and the concept's arm segments: eyes 1.945, chin 1.842, neck base 1.80, arm line 1.72,
waist 1.49, hips 1.17, knee 0.63, ankles 0.14 on heeled sabatons (heel 0.075, ball 0.03: the blockout's heel spike and the
brief's "heels slightly raised by the sabaton shape"); shoulder |x| 0.20, elbow 0.52, wrist 0.79, claw tips 0.99. The
posture is upright: the blockout leans its hips 12 cm forward of its ankles (the concept's floating pose), so its REF
copy is recentred by (-0.034, +0.15, 0) (`s2_selene_recentre.py`) and only the aligned parts take normal detail.
In game (55°, true 1080p px, T-pose): 74 px tall at 22 m (6.9 %), 58 px at 28 m (5.4 %).

## 3. How it was made (the Brax / Valdris method)

| Step | Script | Result |
|---|---|---|
| prepare, recentre | `s2_prepare_blockout.py` (shared), `s2_selene_recentre.py` | the s303 sculpt reference on the origin |
| base, fit | `s2_body_base.py`, `s2_body_fit.py` (shared) | hm08 reduced 4x, symmetric, T-pose, knee / elbow / wrist loops, slender arms (limb_radial), hand frames, eyeballs |
| parts | `s2_selene_parts.py` | the leg girth for the leggings, then every part below as closed meshes (0 boundary, 0 non-manifold edges) |
| texture | `s2_texture.py` (shared) + `s2_selene_paint.py` | UVs, CPU bakes, the painter, `M_selene` |
| gltf_check | `s2_gltf_check.py` (shared) | base colour + emissive + normal textures, tangents on all 13 primitives, no required extensions: ok |
| review, sheets | `s2_selene_review.py`, `s2_selene_sheets.py` (copies of the Valdris pair) | the sheets above |

Parts (triangles): BODY 7,862 · HAIR 1,598 (a shell over the scalp, the high twisted bun with a glowing band, face-framing
strands, swept clumps) · CROWN 264 (**six** gold-rimmed storm-crystal shards, one rigid piece each on `x_crown_01..06`) ·
COLLAR 1,672 (high collar with gold rims, the faceted collar gem in a gold setting, harness straps, the sweetheart
neckline trim, the waist straps) · BELT 1,064 (belt, two big gold rings, hip plates) · SHOULDERS 1,296 (armlets, rings,
pointed blades) · CAPES 1,968 · MANTLES 608 · PANELS 888 · TABARD 764 (front tabard + back panel) · GAUNTLETS 1,844
(bracers with a pointed top edge, back-of-hand plates, ten claw caps) · GREAVES 1,128 (greaves, pointed knee cops,
knee fins) · SABATONS 1,400 (ankle shaft, pointed heeled foot shell, heel block). **Total 22,356** (budget 15-25k).
84 rigid pieces and 8 cloth sheets; the hands are empty (the weapon is separate) and the two floating coils are not built.

## 4. UVs and textures

One 2048 atlas for all 13 objects, 55 % coverage, one texel density (median 574 px/m; hidden faces packed at 0.3).
The painter: skin pale and cool above the sweetheart neckline, on the shoulders and arms (a smooth analytic neckline /
armhole, hidden under the gold trim); the suit navy-black lifted toward #36435B on up-facing planes with a gold spine line
on the back; the leggings a step bluer with gold outer seams; the capes #213F6F fading to the pale storm-cloud #7788A8
through watercolour cloud blotches (the cloth mask R = v); the hip panels and drapes #40648D with gold side trims; the
tabard pale storm blue with a gold vein tree; gold warmer and lighter than the measured dull gold (the brief); plate dark
navy with light-catching outlines. Emissive: ice-blue eyes, the gem, jagged forked lightning veins down both arms and one
down her left cheek (the concept), cyan V slots on the greave fronts and sabaton insteps, the crystal shards, the claws,
the bun band. Normal bake from the blockout: 20 % of the suit / legging / cloth texels take detail (the rest fades flat:
the blockout's cloth hangs elsewhere and its hips lean), 41k texels dropped by the 30-50° tilt filter.

## 5. For stage 3

* GF_Hero_v1 unchanged. Per-hero extras: `x_crown_01..06` under `head_top` (L upper / middle / lower = 01-03, R = 04-06;
  each shard is 100 % one bone); cloth chains `x_cape_{L,R}_01..04` (root `upperarm_{l,r}`), `x_mantle_{L,R}_01..02`
  (root `upperarm`), `x_panel_{L,R}_01..03`, `x_tabard_01..03`, `x_back_01..03` (root `pelvis`). Every cloth sheet is a
  regular grid (u across, v down; `parts.json` cloth), so a chain link maps to a band of rows.
* Rigid pieces carry their suggested bone in `parts.json` `piece_table` (collar → neck_01, gem / straps → spine_03,
  belt / rings / hip plates → pelvis, armlets → upperarm, bracers → lowerarm, hand plates → hand, claws → the last
  phalanx, greaves / knee cops → calf, knee fins → thigh, sabatons → foot).
* Weapon frames: `body_fit.json` `hand_frames` (palm centre R at x -0.864, z 1.703); the thundercoil_launcher GLB rides
  weapon_R with an identity transform in `stage2_armed.png`.
* The heeled feet: the foot bone slopes from the ankle (0.14) to the ball (0.03); the ground contact of the shared clips
  must use the ball / toe, and the heel block sits under the heel.

## 6. Known limits (no further rounds, by the user's rule)

* The hair is a stylised shell with swept clumps and painted strands: under the toon shader it still reads as one smooth
  mass (a cap) in close-ups; at game size (the head is ~8 px) it is the light knot the brief asks for.
* The capes are flat billowing sheets in the frontal plane (the concept's fan): from the side they are thin.
* The front silhouette IoU against the concept (coils masked out) is 0.60: the concept's feet point down and its
  crown wisps and flaring cape curls are wider; the armed IoU (0.37) is not comparable (the launcher widens the box).
* At 28 m she is 5.4 % of the screen height in the T-pose, just under the 6 % target (the width is the cloth fan).

## 7. Reproduce

```sh
python tools/blender/gf_hero/s2_selene_run.py
```
