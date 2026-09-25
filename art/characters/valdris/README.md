# Valdris — "The Anvil-Born" (hero key `valdris`)

P0 playable juggernaut and the **default vertical-slice character** (`content/sheets/characters.csv`
row `valdris`; kit in `assets/content/kits.ron`): a walking siege engine in cracked gunmetal plate
with a siege cannon for a right forearm (signature chassis `colossus_cannon`), colour `#C8A25A`.
Passive Reforged Flesh, actives Bulwark Slam and Siege Stance, ultimate Mountainfall (8 s at 1.8x
scale).

Pipeline: [`docs/ART_PIPELINE.md`](../../../docs/ART_PIPELINE.md). Current state: [`status.json`](status.json).

## Status (2026-09-25)

Nothing here is final. Per the user's decision of 2026-09-25 there is no human artist: AI does
every stage, and the user gives the final visual approval.

| Stage | Status | Waiting on |
|---|---|---|
| 0 Concept & reference | **done** | The user supplied and approved two concepts: the turnaround sheet [`references/VALDRIS_sheet_turnaround.jpg`](references/VALDRIS_sheet_turnaround.jpg) (front A-pose, side, back, colour script, lighting note) and the hero front [`references/VALDRIS_front_approved.jpg`](references/VALDRIS_front_approved.jpg). They disagree in places; **the pack resolves them as cannon on his RIGHT arm, anvil chest plate kept** (the orchestrator's default; the user may override), so the stage-1 input is the hero front mirrored: [`references/valdris_concept_front_mirrored.png`](references/valdris_concept_front_mirrored.png). Every difference and its resolution: [`reports/stage0_sheet_analysis.md`](reports/stage0_sheet_analysis.md). Optional, not blocking: 3/4 view, expression sheet, siege-cannon weapon sheet, Mountainfall concept, cape emblem detail (prompts in [`turnaround_prompts.md`](turnaround_prompts.md)). For the user: confirm the resolution and the head size (brief §7.2 Q1) |
| 1 Blockout (TRELLIS.2) | **done** (SCULPT REFERENCE ONLY) | Seeds s101/s202/s303 generated at 2.3 m; **s202 picked** as the stage-2 sculpt reference ([`reports/blockout_report.md`](reports/blockout_report.md), [`reports/blockout/blockout_selected.png`](reports/blockout/blockout_selected.png)): the only seed with the anvil plate mounted on the chest, the cleanest surface, a solid cape clear of the legs. Its GLB is in Git LFS; s101/s303 stay local (sha256 in `manifest.json`). Never shipped, never in `assets/models/`. Review views: [`blockout_views.json`](blockout_views.json) |
| 2 Production mesh | **done** (made by AI; the user's visual approval pending) | 20,866 tris: the hm08 under-suit body, 141 rigid armour pieces (pauldrons with glowing slots and upright plates, the anvil, shingled cuirass, fauld and tassets, arm plates, per-phalanx gauntlet lames, knee cops, greaves, sabatons), the beard with five braids, the separate cape. One 2048 atlas: NPR base colour, emissive seams, a tangent normal map from the blockout. The siege cannon is the separate `colossus_cannon` weapon on the right-hand frame; the forearm armour clears its sleeve. Report: [`reports/stage2_production_mesh.md`](reports/stage2_production_mesh.md); sheets in [`reports/stage2/`](reports/stage2/). **For the user: the visual approval** |
| 3 Rig | not_started | The GF_Hero_v1 master skeleton (the stage-2 report §8 plans the rigid pieces and the `x_` cloth / braid chains); weight-paint sign-off |
| 4 Animation | not_started | Shared clip set + Valdris's unique set (proposal in [`brief.md`](brief.md) §8) |
| 5 Export & validate | not_started | `assets/models/characters/valdris.glb`, then the final visual approval |

## Stage 0 files

| File | What it is |
|---|---|
| [`brief.md`](brief.md) | Character brief: kit facts, silhouette pillars, measured proportions (at 2.3 m), material callouts with declared vs measured colours, readability at 6-8 % and in a 400-enemy horde, what must survive the toon shader, how Siege Stance / Mountainfall / Reforged Flesh should read, open questions, notes for stages 1-4 |
| [`reports/stage0_sheet_analysis.md`](reports/stage0_sheet_analysis.md) · [`reports/stage0_sheet_compare.png`](reports/stage0_sheet_compare.png) | The 17 differences between the two concepts and the resolution of each; the picture shows the concepts as supplied and the resolved reference set (the sheet's side view mirrored). Made by `tools/comfy/concept_compare.py` from [`concept_compare_spec.json`](concept_compare_spec.json) |
| [`turnaround_prompts.md`](turnaround_prompts.md) | Ready-to-paste ChatGPT prompts for the five missing sheets, the assumptions they use and the acceptance checklist |
| [`color_script.png`](color_script.png) · [`palette.json`](palette.json) | 10 measured swatches (shadow/base/highlight), the sheet's declared colour script vs its painted chips vs the measured materials, the same materials cross-checked on both concepts, value key, colour budget, biome contrast. Made by `tools/comfy/palette_extract.py` from [`palette_spec.json`](palette_spec.json) |
| [`reports/stage0_palette_samples.png`](reports/stage0_palette_samples.png) | Audit of the exact pixels each swatch, cross-check and chip sampled, on both images |
| [`reports/stage0_readability.png`](reports/stage0_readability.png) | The resolved front at 6-8 % of screen height, on each biome's ground, in a client frame, and inside 400 swarm enemies per biome (colour, value, with the P1 ring). Made by `tools/comfy/readability_sheet.py … --mask … --horde 400 --ring` |
| [`manifest.json`](manifest.json) | sha256 of the references (`references`) and of every local-only raw file (`files`, written by `tools/comfy/art_manifest.py`) |

Regenerate (with `<comfy-python>` = `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe`):

```text
<comfy-python> tools/comfy/palette_extract.py art/characters/valdris/palette_spec.json
<comfy-python> tools/comfy/concept_compare.py art/characters/valdris/concept_compare_spec.json
<comfy-python> tools/comfy/readability_sheet.py valdris art/characters/valdris/references/valdris_concept_front_mirrored.png --height-m 2.3 --radius-m 0.55 --mask art/characters/valdris/references/valdris_concept_front_mirrored_mask.png --note "The hero front's arms-out pose is wider than" --note "any gameplay pose (cannon forward, fist guard)." --horde 400 --ring
```

## Stage 2 files

| File | What it is |
|---|---|
| [`reports/stage2_production_mesh.md`](reports/stage2_production_mesh.md) | How it was made, the budget, the cannon fit, the honest review against the concept and the blockout, the stage-3 plan (rigid pieces, `x_` helper chains), the shared tool changes, the acceptance checklist |
| [`reports/stage2/`](reports/stage2/) | Review sheets (`stage2_vs_concept`, `_turnaround`, `_armed`, `_ingame`, `_closeups`, `_wireframe`, `_textures`) and the measured JSON (fit, conform, parts with the piece table, texture, glTF check, review metrics) |
| [`stage2_fit.json`](stage2_fit.json) · [`stage2_parts.json`](stage2_parts.json) · [`stage2_texture.json`](stage2_texture.json) | Every hand-set number: landmarks and conform targets, armour sizes, paint settings |
| `production/valdris_stage2.blend` · `textures/valdris_{basecolor,emissive,normal}.png` | The production mesh and its 2048 textures (Git LFS) |

Rebuild: `python tools/blender/gf_hero/s2_valdris_run.py` (4-9 min, CPU only).

## Folders

| Folder | Content | In git |
|---|---|---|
| `references/` | `VALDRIS_front_approved.jpg` and `VALDRIS_sheet_turnaround.jpg`: the user's approved concepts, verbatim copies of `docs/media/playable_characters/VALDRIS.jpg` (sha256 `55d018f3…`) and `…/VALDRIS THE ANVIL-BORN.jpg` (sha256 `d27bf5f3…`), so git stores one blob each. `valdris_concept_front_mirrored.png`: **derived**, the hero front mirrored left-right, lossless (the stage-1 TRELLIS input, sha256 `62fc6eed…`). `valdris_concept_front_mirrored_mask.png`: **derived**, the TRELLIS graph's own birefnet figure mask of that input (the stage-0 tools use it because the concept's background is a gradient). Approved sheets land here as `VALDRIS_<sheet>_approved.<ext>` | yes |
| `source/` | raw TRELLIS.2 GLBs (`valdris_trellis2_s<seed>.glb`) + ComfyUI previews; the selected seed's GLB goes to git through Git LFS | local except the selected GLB and the provenance JSONs |
| `work/` | full-size renders, mask checks, logs, the intermediate stage-2 `.blend` files | no |
| `reports/` | `stage0_*` review sheets and notes; stage-1 review sheets in `reports/blockout/`; stage 2 in `reports/stage2/` | yes |
| `production/`, `textures/` | the stage-2 production `.blend` and its textures | yes (Git LFS) |

**Everything in `source/` is a stage-1 SCULPT REFERENCE ONLY.** It is dense, unrigged and carries
baked lighting in its texture; it is never copied to `assets/models/` and never shipped.
