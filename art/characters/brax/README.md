# Brax — "The Furnace-Born" (hero key `brax`)

EA playable brawler (`content/sheets/characters.csv` row `brax`; kit in `assets/content/kits.ron`):
bare-knuckle demigod with forge-gauntlets (signature chassis `anvil_gauntlets`), colour `#FF7A3D`.
Actives Cinder Uppercut and Furnace Rush, ultimate Meltdown, passive Heat Gauge.

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md). Current state: [`status.json`](status.json).

## Status (2026-09-25)

Nothing here is final. The Hades-II bar is a human gate at stage 5.

| Stage | Status | Waiting on |
|---|---|---|
| 0 Concept & reference | **pending_human** | The front is approved (user). Side, 3/4, back, expression, gauntlet and colour-script sheets have prompts ready in [`turnaround_prompts.md`](turnaround_prompts.md) and wait for a human to generate and approve them (record approvals with `tools/comfy/approve_sheet.py`). The measured palette is a `stand_in` for the colour-script sheet. |
| 1 Blockout (TRELLIS.2) | **done** (SCULPT REFERENCE ONLY) | Seeds s101/s202/s303 generated; **s202 picked** as the stage-2 sculpt reference ([`reports/blockout_report.md`](reports/blockout_report.md), [`reports/blockout/blockout_selected.png`](reports/blockout/blockout_selected.png)). The GLBs stay local (gitignored, sha256 in `manifest.json`), are never shipped and never go to `assets/models/`. |
| 2 Production mesh | not_started | Human retopo + hand-painted NPR textures (human gate). |
| 3 Rig | not_started | The GF_Hero_v1 master skeleton, then a human weight-paint sign-off. |
| 4 Animation | not_started | Shared clip set + Brax's unique set (proposal in [`brief.md`](brief.md) §8). |
| 5 Export & validate | not_started | `assets/models/characters/brax.glb`, then the final human Hades-II bar. |

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
| `references/` | `BRAX_front_approved.png`: the user-approved front concept (T-pose, 1536x1024), copied verbatim from `docs/media/playable_characters/BRAX.png`. `brax_concept_front.png` is a byte-identical copy that stage 1 uses as its TRELLIS input (same sha256 `407114e7…`, so git stores one blob). Approved sheets land here as `BRAX_<sheet>_approved.png`. | yes |
| `source/` | raw TRELLIS.2 GLBs (`brax_trellis2_s<seed>.glb`, ~60-90 MB) + ComfyUI conditioning/mask previews | **no** (local; path/size/sha256 in `manifest.json`) |
| `source/*.json` | one provenance record per GLB (graph sha256, patched inputs, seed, prompt id, timings, output hash) | yes |
| `work/` | full-size renders, mask checks, logs | no |
| `reports/` | `stage0_*.png` review sheets; `blockout_report.md` + review sheets in `reports/blockout/` | yes |

**Everything in `source/` is a stage-1 SCULPT REFERENCE ONLY.** It is dense, unrigged and carries
baked lighting in its texture; it is never copied to `assets/models/` and never shipped. The game
mesh comes from a human retopo (stage 2).
