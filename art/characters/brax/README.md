# Brax — "The Furnace-Born" (hero key `brax`)

EA playable brawler (`content/sheets/characters.csv` row `brax`; kit in `assets/content/kits.ron`):
bare-knuckle demigod with forge-gauntlets (signature chassis `anvil_gauntlets`, a separate weapon model in
[`art/weapons/anvil_gauntlets/`](../../weapons/anvil_gauntlets/README.md) since 2026-09-25), colour `#FF7A3D`.
Actives Cinder Uppercut and Furnace Rush, ultimate Meltdown, passive Heat Gauge.

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md). Current state: [`status.json`](status.json).

## Status (2026-09-25)

Nothing here is final. The Hades-II bar is a human gate at stage 5.

| Stage | Status | Waiting on |
|---|---|---|
| 0 Concept & reference | **done** | Approved by the user (2026-09-25): the T-pose front and the full turnaround sheet [`references/BRAX_sheet_turnaround.png`](references/BRAX_sheet_turnaround.png) (A-pose front/side/back, gauntlet and face close-ups, chest-sigil detail, five colour swatches). The sheet is the authority for the side and back shapes, the back cracks, the gauntlet construction and the face. Optional, not blocking: a dedicated 3/4 turnaround and a colour script (prompts in [`turnaround_prompts.md`](turnaround_prompts.md)). The measured palette stays a `stand_in` for the materials the swatches do not cover. |
| 1 Blockout (TRELLIS.2) | **done** (SCULPT REFERENCE ONLY) | Seeds s101/s202/s303 generated; **s202 picked** as the stage-2 sculpt reference ([`reports/blockout_report.md`](reports/blockout_report.md), [`reports/blockout/blockout_selected.png`](reports/blockout/blockout_selected.png)). s202 is committed through Git LFS; the other seeds stay local (sha256 in `manifest.json`). Never shipped, never in `assets/models/`. |
| 2 Production mesh | **done** (made by AI, no human artist: the user's decision of 2026-09-25) · user approval **pending_human** | [`production/brax_stage2.blend`](production/brax_stage2.blend) + [`textures/`](textures/): 15,048 tris body set, bare fists (the gauntlets are the `anvil_gauntlets` weapon), 2048² NPR base colour + emissive + tangent-space normal map baked from the blockout (polish pass 2026-09-25, before/after in `reports/stage2/stage2_polish_before_after.png`). Report and checklist: [`reports/stage2_production_mesh.md`](reports/stage2_production_mesh.md); sheets in [`reports/stage2/`](reports/stage2/). Rebuild: `python tools/blender/gf_hero/run_stage2.py brax`. |
| 3 Rig | **done** (made by AI, no human artist: the user's decision of 2026-09-25) · user approval **pending_human** | [`production/brax_rig.blend`](production/brax_rig.blend): the **GF_Hero_v1** master skeleton (63 bones: 23 core, 6 twist, 30 finger, 4 sockets; contract in [`docs/art/GF_HERO_SKELETON.md`](../../../docs/art/GF_HERO_SKELETON.md)) skinned on every part, the validation poses stashed as `GF_ValidationPoses`, the `anvil_gauntlets` linked onto `weapon_L` / `weapon_R` (identity attach, proven in glTF to < 1 µm). Landmarks [`work/brax_landmarks.json`](work/brax_landmarks.json), skinning numbers [`stage3_skin.json`](stage3_skin.json). Report and honest findings: [`reports/rig_report.md`](reports/rig_report.md); sheets in [`reports/stage3/`](reports/stage3/). Rebuild: `python tools/blender/gf_hero/run_stage3.py brax`. |
| 4 Animation | **done** (made by AI, no animator: the user's decision of 2026-09-25) · user approval **pending_human** | [`production/brax_anim.blend`](production/brax_anim.blend): 34 clips on GF_Hero_v1, the 24-clip shared library (idle, locomotion, dash, fire, hits, knockdown, death / wraith / revive / reforge, victory, ping, interact, forge) and Brax's 10 unique clips (jabs, hook, Cinder Uppercut, Furnace Rush, Meltdown, Heat vent, signature idle), in place, 30 fps, loops closed, planted feet at most 0.9 mm. Clip table, sim-state map and honest findings: [`reports/anim_report.md`](reports/anim_report.md); one contact sheet per clip in [`reports/anim/`](reports/anim/). Rebuild: `python tools/blender/gf_hero/run_stage4.py brax`. |
| 5 Export & validate | **done** (made by AI, headless Blender, no human step) · the user's final approval **pending_human** | [`assets/models/characters/brax.glb`](../../../assets/models/characters/brax.glb) (9.97 MB: GF_Hero_v1 + one skinned 15,048-tri mesh + the 34 clips, uncompressed for bevy_gltf 0.20, no vertex colours) and its sidecar [`brax.meta.json`](../../../assets/models/characters/brax.meta.json) (clip events, weapon-variant swaps, design speeds, sockets, status `ai_final_pending_user_approval`); the gauntlets as [`assets/models/weapons/anvil_gauntlets.glb`](../../../assets/models/weapons/anvil_gauntlets.glb). Gate `tools/blender/gf_hero/validate_glb.py` (CI job `hero-glb`): 0 errors; Blender re-import of every clip within 1.8e-6; source fidelity 1.9e-5. Report [`reports/export_report.json`](reports/export_report.json), review sheet [`reports/stage5/export_review.png`](reports/stage5/export_review.png). Rebuild: `python tools/blender/gf_hero/run_stage5.py brax`. The final Hades-II bar is the user's approval. |

## Stage 0 files

| File | What it is |
|---|---|
| [`brief.md`](brief.md) | Character brief: kit facts, silhouette pillars, measured proportions, material callouts, readability findings, what must survive the toon shader, open design questions |
| [`turnaround_prompts.md`](turnaround_prompts.md) | Ready-to-paste ChatGPT prompts for the six missing sheets, plus the acceptance checklist |
| [`color_script.png`](color_script.png) · [`palette.json`](palette.json) | 13 measured swatches (shadow/base/highlight), value key, colour budget, contrast checks. Made by `tools/comfy/palette_extract.py` from [`palette_spec.json`](palette_spec.json) |
| [`reports/stage0_readability.png`](reports/stage0_readability.png) | The concept at 6-8 % of screen height, on each biome's ground and in a client frame. Made by `tools/comfy/readability_sheet.py` |
| [`reports/stage0_palette_samples.png`](reports/stage0_palette_samples.png) | Audit of the exact pixels each swatch sampled |
| [`manifest.json`](manifest.json) | sha256 of the references (`references`) and of every local-only raw file (`files`, written by `tools/comfy/art_manifest.py`) |

## Folders

| Folder | Content | In git |
|---|---|---|
| `references/` | `BRAX_front_approved.png`: the user-approved front concept (T-pose, 1536x1024), copied verbatim from `docs/media/playable_characters/BRAX.png`. `brax_concept_front.png` is a byte-identical copy that stage 1 uses as its TRELLIS input (same sha256 `407114e7…`, so git stores one blob). `BRAX_sheet_turnaround.png`: the user-approved turnaround/detail sheet, copied verbatim from `docs/media/playable_characters/BRAX THE FURNACE-BORN .png` (sha256 `a74e23eb…`). Further approved sheets land here as `BRAX_<sheet>_approved.png`. | yes |
| `source/` | raw TRELLIS.2 GLBs (`brax_trellis2_s<seed>.glb`, ~60-90 MB) + ComfyUI conditioning/mask previews | the selected `brax_trellis2_s202.glb` **yes (Git LFS)**; the other seeds and the previews no (local; path/size/sha256 in `manifest.json`) |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | stage-2 inputs: landmarks and fit bands, part parameters, UV/paint settings | yes |
| `stage3_skin.json` | stage-3 inputs: heat/seed mix, twist ramps, joint fixes, how each part is weighted | yes |
| `production/` | `brax_stage2.blend`: the production mesh (body, hair, beard, belt, sash, skirt cloth + plates, wraps), material `M_brax`; `brax_rig.blend`: GF_Hero_v1 + the skinned parts + validation poses (stage 3); `brax_anim.blend`: the rig file + the 34 clips as actions / NLA tracks (stage 4) | yes (Git LFS) |
| `textures/` | `brax_basecolor.png`, `brax_emissive.png` (2048², sRGB), `brax_normal.png` (2048², Non-Color tangent-space) | yes (Git LFS) |
| `source/*.json` | one provenance record per GLB (graph sha256, patched inputs, seed, prompt id, timings, output hash) | yes |
| `work/` | full-size renders, mask checks, logs, the stage-2 intermediates (`brax_retopo_start.blend` = the prepared sculpt reference, body/parts files), the stage-3 seed weights | no (regenerated), except `work/brax_landmarks.json` (the GF_Hero_v1 landmark file, committed with `git add -f`) |
| `reports/` | `stage0_*.png` review sheets; `blockout_report.md` + `reports/blockout/`; `stage2_production_mesh.md` + `reports/stage2/` (sheets + fit/parts/texture JSON); `rig_report.md` + `reports/stage3/` (rig sheets + landmark/seed/skin/pose/glTF JSON); `anim_report.md` + `reports/anim/` (a contact sheet per clip, the game-size boards, `clips.json`, `render_checks.json`, `gltf_check.json`); `export_report.json` + `reports/stage5/export_review.png` (stage 5: the shipped GLB's checks and its re-import review) | yes |

**Everything in `source/` is a stage-1 SCULPT REFERENCE ONLY.** It is dense, unrigged and carries
baked lighting in its texture; it is never copied to `assets/models/` and never shipped. The game
mesh is the AI-made stage-2 production mesh, rigged on GF_Hero_v1 in stage 3.
