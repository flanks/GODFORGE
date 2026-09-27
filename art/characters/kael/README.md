# Kael — "The Wraithshot" (hero key `kael`)

P1 playable agile duelist (`content/sheets/characters.csv` row `kael`; kit in `assets/content/kits.ron`): a ghost
gunslinger in a long tattered violet duster whose left arm is spectral ghost flesh, signature chassis `serpent_smg`,
colour `#9A7CFF`. Passive Ghost Step, actives Fan of Blades and Shadow Roll, ultimate Bullet Ballet (6 s of infinite
dash and twin spectral pistols).

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md). Current state: [`status.json`](status.json).

## Status (2026-09-27)

Nothing here is final. Per the user's decision of 2026-09-25 there is no human artist: AI does every stage, and the
user gives the final visual approval.

| Stage | Status | Waiting on |
|---|---|---|
| 0 Concept & reference | **done** | The user supplied the approved T-pose front [`references/KAEL_front_approved.png`](references/KAEL_front_approved.png) (verbatim copy of `docs/media/playable_characters/KAEL, THE WRAITHSHOT.png`). Brief, measured palette, colour callouts and the game-scale check are made. Optional, not blocking: side, 3/4, back, expression and colour-script sheets (prompts in [`turnaround_prompts.md`](turnaround_prompts.md), each `pending_human`). For the user: the ghost arm is kept on his **left** arm as the concept paints it (`status.json` `decisions[ghost_arm_side]`) |
| 1 Blockout (TRELLIS.2) | **done** (SCULPT REFERENCE ONLY) | Seeds s101/s202/s303 generated at 2.1 m from the approved front with the revolvers and the diffuse ghost smoke cut out of the mask ([`reports/blockout/input_edit.png`](reports/blockout/input_edit.png)); **s202 picked** as the stage-2 sculpt reference ([`reports/blockout_report.md`](reports/blockout_report.md), [`reports/blockout/blockout_selected.png`](reports/blockout/blockout_selected.png)): the only seed with both hands right (gloved right fist, ghost left fist), a solid coat back clear of the legs, the cleanest surface. Its GLB is in Git LFS; s101/s303 stay local (sha256 in `manifest.json`). Never shipped, never in `assets/models/`. For the face use the concept and s303's head |
| 2 Production mesh | **done** (made by AI) | The user's visual approval. 24,114 tris, 8 closed objects, one 2048 atlas; [`reports/stage2_production_mesh.md`](reports/stage2_production_mesh.md), sheets in [`reports/stage2/`](reports/stage2/) |
| 3 Rig | **done** (made by AI) | The user's visual approval. GF_Hero_v1 + 48 `x_` cloth bones (coat 6 x 4, loin 3 x 3, tatters 5 x 3), serpent_smg on `weapon_R`; [`reports/stage3/stage3_rig.png`](reports/stage3/stage3_rig.png) |
| 4 Animation | **done** (made by AI) | The user's visual approval. 24 shared clips re-posed for the gunslinger + 8 kit clips, cloth pass; [`reports/anim/anim_board.png`](reports/anim/anim_board.png) |
| 5 Export & validate | **done** (made by AI) | The user's visual approval. [`assets/models/characters/kael.glb`](../../../assets/models/characters/kael.glb) + `.meta.json` (`ai_final_pending_user_approval`), 0 errors / 0 warnings; [`reports/stage5/export_review.png`](reports/stage5/export_review.png). Stages 3-5: [`reports/stage3_5_report.md`](reports/stage3_5_report.md) |

## Stage 0 files

| File | What it is |
|---|---|
| [`brief.md`](brief.md) | Character brief: kit facts and what they mean for the art, silhouette pillars, measured proportions (at 2.1 m), material callouts, readability at 6-8 % and in a 400-enemy horde, what must survive the toon shader, open questions and decisions (ghost arm side, the weapons decision: empty hands), notes for stages 1-4 and the proposed unique clips |
| [`turnaround_prompts.md`](turnaround_prompts.md) | Ready-to-paste ChatGPT prompts for the five optional sheets (side, 3/4, back, expression, colour script), the proposals they use and the acceptance checklist. No weapon sheet: `serpent_smg` is already built |
| [`color_script.png`](color_script.png) · [`palette.json`](palette.json) | 12 measured swatches (shadow/base/highlight; emissive rim/hot/core), value key, colour budget, checks against the biome grounds. Made by `tools/comfy/palette_extract.py` from [`palette_spec.json`](palette_spec.json). A `stand_in` for a painted colour script |
| [`reports/stage0_palette_samples.png`](reports/stage0_palette_samples.png) | Audit of the exact pixels each swatch sampled |
| [`reports/stage0_readability.png`](reports/stage0_readability.png) | The stage-1 cut-out (no revolvers, no diffuse smoke) at 6-8 % of screen height, on each biome's ground, in a client frame, and inside 400 swarm enemies per biome (colour, value, with the P1 ring) |
| [`manifest.json`](manifest.json) | sha256 of the references (`references`) and of every local-only raw file (`files`, written by `tools/comfy/art_manifest.py`) |

Regenerate (with `<comfy-python>` = `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe`):

```text
<comfy-python> tools/comfy/palette_extract.py art/characters/kael/palette_spec.json
<comfy-python> tools/comfy/readability_sheet.py kael art/characters/kael/references/KAEL_front_approved.png --height-m 2.1 --radius-m 0.44 --mask art/characters/kael/references/kael_concept_front_nogun_mask.png --note "Cut-out without the two revolvers (weapons are" --note "separate models) and without the diffuse smoke." --note "The arms-out pose is wider than any gameplay pose." --horde 400 --ring
```

## Stage 1 files

| File | What it is |
|---|---|
| [`reports/blockout_report.md`](reports/blockout_report.md) | The input check and edit, the generation record, the comparison of the three seeds, the pick, the known defects, the in-game read, what stage 2 should take, the commands |
| [`reports/blockout/`](reports/blockout/) | `blockout_selected.png` (the pick next to the concept), `blockout_compare.png` (all seeds), `input_maskcheck.png`, `input_edit.png`, and per seed `_turnaround`, `_closeups`, `_closeups2`, `_ingame`, `_silhouette` |
| [`references/kael_concept_front_nogun.png`](references/kael_concept_front_nogun.png) · [`_mask.png`](references/kael_concept_front_nogun_mask.png) | The TRELLIS.2 input: the approved front's own pixels with an edited alpha (no revolvers, no diffuse smoke), made by `tools/blender/gf_hero/kael_stage1_input.py` |
| [`blockout_views.json`](blockout_views.json) | Kael's close-up parts, views and body regions for the review renders |
| `source/kael_trellis2_s202.glb` (Git LFS) · `source/*.json` | The selected sculpt reference and the provenance of every seed (graph hash, patched inputs, seeds, timings, output sha256) |

Every command is in [`reports/blockout_report.md`](reports/blockout_report.md) §9.

## Stages 3-5 files

| File | What it is |
|---|---|
| [`reports/stage3_5_report.md`](reports/stage3_5_report.md) | What stages 3-5 built, the numbers and the known limits |
| [`stage3_skin.json`](stage3_skin.json) · `work/kael_landmarks.json` | Every hand-set number of the rig and skin (the cloth chains' columns, heights, blends); the GF_Hero_v1 landmark file |
| `production/kael_rig.blend` · `production/kael_anim.blend` (Git LFS) | The rigged hero; the rig + one action / NLA track per clip, the cloth chains keyed |
| [`reports/stage3/`](reports/stage3/) · [`reports/anim/`](reports/anim/) · [`reports/stage5/`](reports/stage5/) · [`reports/export_report.json`](reports/export_report.json) | Sheets and measured results |

Regenerate: `python tools/blender/gf_hero/s3_kael_run.py`, `python tools/blender/gf_hero/s4_kael_run.py`, then
`python tools/blender/gf_hero/run_stage5.py kael --only export`, `python tools/blender/gf_hero/s5_kael.py --sidecar`,
`python tools/blender/gf_hero/run_stage5.py kael --only reimport` and `--only sheet`.
