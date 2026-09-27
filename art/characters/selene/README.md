# Selene — "The Stormcaller" (hero key `selene`)

P1 playable glass cannon / blaster (`content/sheets/characters.csv` row `selene`; kit in `assets/content/kits.ron`):
lightning in human shape, colour `#6FE3FF`. Signature chassis `thundercoil_launcher` (a separate, already shipped
weapon model: `assets/models/weapons/thundercoil_launcher.glb`). Actives Arc Nova and Blink, ultimate Heaven's
Verdict, passive Static Charge.

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md). Current state: [`status.json`](status.json).

## Status (2026-09-27)

Nothing here is final: every stage is made by AI and waits on the user's visual approval. The Hades-II bar is the user's approval at stage 5.

| Stage | Status | Waiting on |
|---|---|---|
| 0 Concept & reference | **done** | The user-approved T-pose front [`references/SELENE_front_approved.png`](references/SELENE_front_approved.png). Brief, measured palette (`stand_in` for a painted colour script), readability sheet, prompts for the four optional sheets (side, back, 3/4, expression: `pending_human`, not blocking). The two floating coils in the concept are weapon / VFX, not body. |
| 1 Blockout (TRELLIS.2) | **done** (SCULPT REFERENCE ONLY) | Seeds s101/s202/s303 on the front with a verified alpha ([`stage1_input.py`](stage1_input.py): coils cut, the ground around the crown removed); **s303 picked** (the concept's face, silver hair and deep storm-blue cloth; [`reports/blockout_report.md`](reports/blockout_report.md), [`reports/blockout/blockout_selected.png`](reports/blockout/blockout_selected.png)). s303 is committed through Git LFS; the other seeds stay local (sha256 in `manifest.json`). Never shipped, never in `assets/models/`. |
| 2 Production mesh | **done** (made by AI) | the user's visual approval ([`reports/stage2/`](reports/stage2/), [`reports/stage2_production_mesh.md`](reports/stage2_production_mesh.md)) |
| 3 Rig | **done** (made by AI) | the user's visual approval: GF_Hero_v1 + 32 `x_` extras (six crown shards, two knee helpers, eight cloth chains), the launcher on `weapon_R` ([`reports/stage3/stage3_rig.png`](reports/stage3/stage3_rig.png), [`reports/rig_report.md`](reports/rig_report.md)) |
| 4 Animation | **done** (made by AI) | the user's visual approval: 31 clips (24 shared re-posed for her two-handed launcher hold + 7 kit), cloth and crown pass ([`reports/anim/anim_board.png`](reports/anim/anim_board.png), [`reports/anim_report.md`](reports/anim_report.md)) |
| 5 Export & validate | **done** (`ai_final_pending_user_approval`) | the user's final approval of [`assets/models/characters/selene.glb`](../../../assets/models/characters/selene.glb) + `selene.meta.json` (0 errors, 0 warnings; [`reports/stage5/export_review.png`](reports/stage5/export_review.png)) |

Rebuild: `python tools/blender/gf_hero/s2_selene_run.py`, `s3_selene_run.py`, `s4_selene_run.py`, then
`python tools/blender/gf_hero/run_stage5.py selene --only export` (and `--only reimport`, `--only sheet`).

## Stage 0 files

| File | What it is |
|---|---|
| [`brief.md`](brief.md) | Character brief: kit facts, silhouette pillars, measured proportions, material callouts, readability findings, what must survive the toon shader, how the kit should read, open design questions |
| [`turnaround_prompts.md`](turnaround_prompts.md) | Ready-to-paste prompts for the four optional sheets, plus the acceptance checklist |
| [`color_script.png`](color_script.png) · [`palette.json`](palette.json) | 15 measured swatches (shadow/base/highlight), value key, colour budget, contrast checks. Made by `tools/comfy/palette_extract.py` from [`palette_spec.json`](palette_spec.json) |
| [`reports/stage0_readability.png`](reports/stage0_readability.png) | The concept (coils masked out) at 6-8 % of screen height, on each biome's ground, in a client frame and in a 400-enemy horde. Made by `tools/comfy/readability_sheet.py` |
| [`reports/stage0_palette_samples.png`](reports/stage0_palette_samples.png) | Audit of the exact pixels each swatch sampled |
| [`manifest.json`](manifest.json) | sha256 of the references and of every local-only raw file (`tools/comfy/art_manifest.py`) |

## Folders

| Folder | Content | In git |
|---|---|---|
| `references/` | `SELENE_front_approved.png`: the approved front, copied verbatim from `docs/media/playable_characters/selene.png` (sha256 `a75de828…`). `selene_concept_front_mask.png`: the TRELLIS graph's birefnet mask of it (`run_trellis.py --mask-only`); `selene_concept_front_mask_nocoils.png`: the same without the two coils (readability, silhouette IoU). `selene_concept_front_input.png`: the stage-1 input (the front's RGB + a verified alpha, `stage1_input.py`). Further approved sheets land here as `SELENE_<sheet>_approved.png`. | yes |
| `source/` | raw TRELLIS.2 GLBs (`selene_trellis2_s<seed>.glb`) + ComfyUI previews; one provenance JSON per GLB | the selected seed's GLB **yes (Git LFS)** and every provenance JSON; the other seeds and the previews no (sha256 in `manifest.json`) |
| `work/` | full-size renders, the mask check, logs, the first (discarded) run on the plain concept (`work/first_input/`) | no |
| `reports/` | `stage0_*.png`; `blockout_report.md` + `reports/blockout/` (stage 1); `stage2_production_mesh.md` + `reports/stage2/`; `rig_report.md` + `reports/stage3/`; `anim_report.md` + `reports/anim/`; `export_report.json` + `reports/stage5/` | yes |
| `production/` | `selene_stage2.blend` (the mesh), `selene_rig.blend` (+ GF_Hero_v1, skinned, the launcher PREVIEW), `selene_anim.blend` (+ the 31 clips) | yes (Git LFS) |

**Everything in `source/` is a stage-1 SCULPT REFERENCE ONLY.** It is dense, unrigged and carries baked lighting
in its texture; it is never copied to `assets/models/` and never shipped.
