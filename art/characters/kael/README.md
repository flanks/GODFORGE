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
| 2 Production mesh | not started | the shared chain (`run_stage2.py`) with a `kael` variant for the coat, the ghost arm zone and the ghost-flame tatters |
| 3 Rig | not started | GF_Hero_v1 + `x_` coat / tatter chains |
| 4 Animation | not started | the 24 shared clips + his unique set (brief §8) |
| 5 Export & validate | not started | `assets/models/characters/kael.glb` |

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
