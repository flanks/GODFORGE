# GODFORGE — Hero Art Pipeline

> **AI accelerates iteration. Humans guarantee the Hades-II bar. AI output never ships raw.**

This is the character-art track that feeds `docs/ARCHITECTURE.md` §9 (art pipeline hook). It is the
same pipeline the user proved end to end on Ashen Covenant. Where a GODFORGE tool is an adapted
copy, its header says which Ashen Covenant tool it came from. The stage-0 sheet tools are new.
Nothing under `D:\Ashen_Covenant` is modified.

## 1. Stages

The user's pipeline, verbatim:

| Stage | Tool | Output | Rule |
|---|---|---|---|
| 0. Concept & reference | ChatGPT (briefs, turnaround prompts) + ComfyUI (IP-Adapter/LoRA style-locked workflows) | Approved 2D reference sheets: front/side/3/4, expression sheet, weapon sheet, color script | Style LoRAs trained ONLY on our own approved style bible - never competitor art |
| 1. 3D blockout | ComfyUI image-to-3D nodes (Trellis / Hunyuan3D / TripoSR-class) | Rough silhouette mesh from approved reference | Sculpt reference only - never shipped. Dense topology, no deformation loops, baked-texture artifacts |
| 2. Production mesh | Human artist, Blender 5.2 | Game mesh: manual retopo (~15-25k tris/char), clean shoulder/elbow/knee edge loops, UVs, hand-painted NPR textures | AI blockout is a silhouette accelerator, not a substitute for deformation-aware topology |
| 3. Rig | Rigify / AccuRIG auto-rig + hand weight-paint fixes (shoulders, hands, face) | ONE MASTER SKELETON for the entire roster - identical bone hierarchy, adjustable proportions per character | Same rig = shared animation library across 8-12 characters |
| 4. Animation | Blender 5.2 + Cascadeur-style posing; Mixamo/ActorCore seeds acceptable for prototyping only | Shared clip set (~40 clips: locomotion, dash, hit/death reactions, fire poses) + per-character unique set (6-10 clips: ult, 2 actives, signature idle) | Weapon fire is mostly procedural in Bevy (recoil curves, aim offsets, IK, additive layers) - not full-body authored clips |
| 5. Export & validate | Headless Blender CI -> glTF (Draco/meshopt) | {char}_{clip}@loop naming, animations baked, import smoke-test | CI rejects broken weights, missing clips, or over-budget meshes |

GODFORGE narrows two cells without changing the table. Stage 1 uses **TRELLIS.2 only**, because it
is the only image-to-3D model whose licence has been cleared (§7). Stage 5 exports **uncompressed**
glTF, because Bevy 0.20 can load neither Draco nor meshopt (§6).

### Gates in GODFORGE

| Stage | Gate | Who | In `status.json` |
|---|---|---|---|
| 0 | every new sheet is approved (front, side, 3/4, back, expression, weapon, colour script) | **human** approver | each sheet is an item: `pending_human` until approved, then `done` with `approved_by` / `approved_on` (`tools/comfy/approve_sheet.py`) |
| 1 | none; judged by eye against the concept in review renders | automated + reviewer | `in_progress` → `done`, with the note SCULPT REFERENCE ONLY |
| 2 | production mesh + NPR textures: **made by AI**, no human artist (user decision, 2026-09-25); the user's final visual approval | the **user** | `done` with `produced_by`; an item `user_visual_approval` stays `pending_human` until the user approves the review sheets |
| 3 | rig + skin weights: **made by AI** (the same decision; stage 3 has no weight-paint artist either); the user's final visual approval | the **user** | `done` with `produced_by`; an item `user_visual_approval` stays `pending_human` until the user approves the stage-3 sheets |
| 4 | the clips: **made by AI** (no animator; the same decision), validated by metrics and review renders; the user's final visual approval | the **user** | `done` with `produced_by`; an item `user_visual_approval` stays `pending_human`. Mixamo/ActorCore-seeded clips would be `stand_in` |
| 5 | export & validation: **made by AI** (the exporter, the stdlib gate, a Blender re-import, the CI job `hero-glb`); the user's final visual approval is the Hades-II bar | the **user** | `done` with `produced_by`; an item `user_final_approval` stays `pending_human`. When the user signs it off, the item and the stage get `signed_off_by` / `signed_off_on`; only then may the hero's `final` be `true` |

**Decision of 2026-09-25 (the user, relayed by the workflow coordinator): there is no human artist for
stage 2.** The production mesh, UVs and NPR textures are made by the AI pipeline in §5 at production
quality, not as a stand-in. The human gate that remains at stage 2 is the user's own visual approval. The
same holds for stage 3 (the rig and its weights are AI-made and validated by poses, metrics and review renders;
the user gives the final visual approval), stage 4 (the clips) and stage 5 (the export: validators and review
renders are the quality gate, the user's final visual approval is the only human gate).

**Human gates are real.** Every gate above is recorded as `pending_human` in the hero's
`art/characters/<key>/status.json` until a person signs it off. When engineering needs something
before a gate clears, the automated substitute is a **stand-in**: `stand_in: true` in status.json,
never called final, never promoted past its gate.

The status values are `not_started | in_progress | done | stand_in | pending_human | blocked`. Every
stage has `status`, `outputs`, `human_signoff_required` and `notes`. Stage 0 also has one `items`
entry per sheet. `tools/comfy/check_art.py`, run in CI by `.github/workflows/art.yml`, rejects
these violations:
- an unknown status;
- a stand-in marked `done` or `final`;
- a human gate marked `done` without an approver's name;
- `final: true` before stage 5 is signed off.

## 2. How it maps onto GODFORGE

### The runtime hook (ARCHITECTURE §9)

* **Keys.** A hero's asset key is its `CharacterDef.key` from `content/sheets/characters.csv`
  (`brax`). Chassis and enemies use `ChassisDef.key` and `EnemyDef.shape` in the same way.
* **One file per hero.** Stage 5 writes `assets/models/characters/<key>.glb`
  (`assets/models/{kind}/{key}.glb`). `gf_client::palette` gains a `Handle<Scene>` lookup by key
  and **falls back to the greybox primitive when the file is missing**, so content can land before
  art. The art track only produces files. It never edits `crates/`.
* **Scale and framing.** 1 unit = 1 m. A hero stands 2.0 to 2.3 m tall (Brax: 2.2 m proposed),
  with the origin on the ground between the feet. glTF is Y-up and its assets face +Z; the client
  applies the facing when it wires the scene in. Heroes are seen from a fixed 55°
  orthographic iso camera at about **6 to 8 % of screen height** (65 to 86 px at 1080p), so the
  silhouette matters more than micro-detail. That holds for 1-2 players: the camera widens to 28 m of view height for
  4 players (up to 32 m when they spread), where a 2.2 m hero is about 58 px (5.4 %), so check the 4-player read too
  (Brax: `art/characters/brax/reports/review_stage3_5.md`).
* **Procedural stays procedural.** Weapon fire, recoil, aim offsets and hit flinches stay
  procedural in `scene.rs`, so they don't multiply authored clips.

### Clip naming

* Every clip in a hero's GLB is named `{char}_{clip}`, and loops add `@loop`: `brax_idle@loop`,
  `brax_run@loop`, `brax_dash`, `brax_hit_light`, `brax_death`, `brax_uppercut`,
  `brax_meltdown@loop`. `{clip}` is lower_snake_case.
* The **shared set** (24 clips since stage 4; the table is `docs/art/GF_HERO_SKELETON.md` §8 and the
  contract `tools/blender/gf_hero/s4_contract.py`) uses the same `{clip}` names for every hero, so the
  client maps a state to `format!("{key}_{clip}")` and never special-cases a hero. The **unique set** (6 to
  10 clips: ult, 2 actives, signature idle) is named after the kit's abilities.
* Shared clips are authored once on GF_Hero_v1 (§5) and **baked per hero**, on that hero's proportions
  (leg and arm length from its landmark file) and move speed.
* Bevy builds each `AnimationTargetId` from the **bone-name path starting at the animation
  root**. Identical bone names, parenting *and armature object name* therefore let one hero's
  clip drive another hero's scene. A hero-specific armature name such as `brax_rig` would break
  that.

### Where things live

```text
art/characters/<key>/
  README.md       index + status summary (committed)
  brief.md        stage-0 character brief: kit, silhouette pillars, proportions, materials, readability (committed)
  turnaround_prompts.md  ready-to-paste prompts for the missing stage-0 sheets + acceptance checklist (committed)
  palette_spec.json  where each material is sampled on the approved front (committed, hand-edited)
  palette.json    measured swatches + contrast checks (committed, generated)
  color_script.png   colour callout sheet (committed, generated)
  references/     approved concept(s) and approved sheets <KEY>_<sheet>_approved.png (committed, < 2 MB each)
  source/         raw generator output: TRELLIS GLBs + ComfyUI previews (LOCAL, gitignored)
                  and one provenance JSON per GLB (committed)
  work/           full-size renders, mask checks, .blend files (LOCAL, gitignored)
  reports/        review sheets (PNG < 2 MB) and stage reports (committed); reports/stage2/ = stage-2 sheets + JSON;
                  reports/stage3/ + rig_report.md = the rig's sheets, metrics and glTF check;
                  reports/anim/ + anim_report.md = one contact sheet per clip, the game-size boards, clips.json
                  (the clip manifest: frames, loops, layers, events, design speeds, metrics) and the glTF clip check;
                  export_report.json + reports/stage5/export_review.png = the stage-5 export: Blender-side checks, the
                  gate, source fidelity, the Blender re-import, the signature weapon, the review sheet of the shipped file
  stage2_fit.json / stage2_parts.json / stage2_texture.json   the hero's stage-2 inputs (landmarks, part
                  parameters, paint settings; committed, hand-edited)
  production/     <key>_stage2.blend: the production mesh + material (committed, Git LFS);
                  <key>_rig.blend: GF_Hero_v1 + the skinned parts + the validation poses (stage 3, Git LFS);
                  <key>_anim.blend: the rig file + one action / NLA track per clip (stage 4, Git LFS)
  stage3_skin.json  the hero's stage-3 skinning numbers (committed, hand-edited)
  work/<key>_landmarks.json  the hero's GF_Hero_v1 landmark file (committed with git add -f; the rest of work/ is local)
  textures/       <key>_basecolor.png, <key>_emissive.png (committed, Git LFS)
  manifest.json   sha256 of the references + every local-only file: path, bytes, sha256 (committed)
  status.json     per stage: status, outputs, human_signoff_required, notes (committed)
art/weapons/<chassis>/   one folder per chassis weapon model, same layout and the same status/manifest schema
                  (stage2_weapon.json, stage2_texture.json, production/, textures/, reports/stage2/)
tools/comfy/      ComfyUI drivers and the user's graphs (API format), plus the stdlib/PIL art tools:
                  palette_extract.py, readability_sheet.py, approve_sheet.py, art_manifest.py, check_art.py
tools/blender/gf_hero/   headless Blender scripts: stage-1 review renders, the stage-2 chain (run_stage2.py, s2_*.py),
                  the stage-3 rig chain (gf_hero_rig.py = the GF_Hero_v1 contract, run_stage3.py, s3_*.py, check_skeleton.py),
                  the stage-4 clip chain (run_stage4.py, s4lib.py = the solver, s4_clips.py = the shared library,
                  s4_<key>.py = a hero's unique set, s4_contract.py, check_clips.py), the stage-5 export (run_stage5.py,
                  export_glb.py, validate_glb.py = the gate, smoke_import.py, s5_sheets.py, required_clips.json)
assets/models/characters/<key>.glb   the shipped hero: GF_Hero_v1 + one skinned mesh + every clip (stage 5 output; the
                  client falls back to greybox when missing) and <key>.meta.json, its sidecar (clip events, sockets, status)
assets/models/weapons/<chassis>.glb  shipped weapon model (stage 5 output) + <chassis>.meta.json, attached to the weapon sockets
```

Git LFS is enabled (repo `.gitattributes`, 2026-09-25): `.blend`, `.glb` and `art/**/textures/**/*.png` go
through LFS. No file over 20 MB is committed outside LFS; `art/.gitignore` keeps scratch and unselected raw
output local (§8).

### Commands per stage

Run from the repo root. `<blender>` is `"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"` (the chain
runners read `BLENDER`), `<comfy-python>` is `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe` (PIL;
the runners read `COMFY_PY`). Review renders use Cycles on the CPU or Workbench, never EEVEE: the GPU is shared.

| Stage | Command | Output |
|---|---|---|
| 0 palette | `<comfy-python> tools/comfy/palette_extract.py art/characters/<key>/palette_spec.json` | `palette.json`, `color_script.png` |
| 0 readability | `<comfy-python> tools/comfy/readability_sheet.py <key> <front.png>` | `reports/stage0_readability.png` |
| 0 approval (human) | `python tools/comfy/approve_sheet.py <key> <sheet> <png> --by "<name>"` | `references/<KEY>_<sheet>_approved.png`, status item `done` |
| 1 input check | `python tools/comfy/run_trellis.py <key> <concept.png> --mask-only --out art/characters/<key>/work/maskcheck_raw` | mask + conditioning crop |
| 1 generate | `python -u tools/comfy/run_trellis.py <key> <concept.png> --seed 101 --seed 202 --seed 303` | `source/<key>_trellis2_s<seed>.glb` + provenance JSON |
| 1 review | `<blender> -b -P tools/blender/gf_hero/render_blockout.py -- <glb> art/characters/<key>/work/renders/<stem> <stem>`, then `<comfy-python> tools/comfy/blockout_sheets.py <renders> <reports/blockout> <concept> <mask> <stems...> --selected <stem>` and `python tools/comfy/art_manifest.py <key> --selected <glb>` | review sheets, `manifest.json` |
| 2 production mesh | `python tools/blender/gf_hero/run_stage2.py <key>` (armoured variant: `python tools/blender/gf_hero/s2_valdris_run.py`) | `production/<key>_stage2.blend`, `textures/`, the signature weapon pack, `reports/stage2/` |
| 3 rig | `python tools/blender/gf_hero/run_stage3.py <key>` (armoured variant: `python tools/blender/gf_hero/s3_valdris_run.py`) | `production/<key>_rig.blend`, `work/<key>_landmarks.json`, `reports/stage3/` |
| 4 animation | `python tools/blender/gf_hero/run_stage4.py <key>` (armoured variant: `python tools/blender/gf_hero/s4_valdris_run.py`) | `production/<key>_anim.blend`, `reports/anim/` |
| 5 export & validate | `python tools/blender/gf_hero/run_stage5.py <key>` | `assets/models/characters/<key>.glb` + `.meta.json`, `assets/models/weapons/<chassis>.glb` + `.meta.json`, `reports/export_report.json`, `reports/stage5/` |
| 5 gate only (CI) | `python tools/blender/gf_hero/validate_glb.py assets/models/characters/*.glb [--blender <blender>] [--json <report>]` | exit 1 on any error |
| CI (stdlib) | `python tools/comfy/check_art.py`, `python tools/blender/gf_hero/check_skeleton.py`, `python tools/blender/gf_hero/check_clips.py` | the `.github/workflows/art.yml` jobs |

Every runner takes `--from <step>` / `--only <step>` and writes one log per step to `art/characters/<key>/work/logs/`.

## 3. Stage 0: concept and reference (implemented)

`<comfy-python>` below is `D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\standalone-env\python.exe`,
which has PIL and numpy. The other art tools use only the standard library.

1. **Approved front.** The user supplies the front concept (T-pose, orthographic, flat dark
   background). It is copied verbatim to `references/<KEY>_front_approved.png`. `status.json`
   records it as item `front: done, approved_by: user`, and `manifest.json` records its sha256
   under `references`.
2. **Brief.** `brief.md` is written from the content rows (`characters.csv`, `kits.ron`,
   `chassis.csv`) and the concept. It covers what the kit implies for the art, the silhouette
   pillars, measured proportions, material callouts, readability findings, what must survive the
   toon shader, and the open design questions.
3. **Measured palette.** `<comfy-python> tools/comfy/palette_extract.py art/characters/<key>/palette_spec.json`
   writes `palette.json`, `color_script.png` and `reports/stage0_palette_samples.png`.
   `palette_spec.json` gives each material sample boxes and an HSV filter. The shadow / base /
   highlight tones are the CIELAB L\* percentiles 15 / 50 / 90 (for emissives: rim / hot / core).
   The output is deterministic. It measures approved art and is a **`stand_in` for the painted
   colour-script sheet** until that sheet is approved.
4. **Readability check.** `<comfy-python> tools/comfy/readability_sheet.py <key> <front.png>` writes
   `reports/stage0_readability.png`. It shows the concept at 6 % and 8 % of a 1080p frame, as
   colour, value and flat silhouette, on each biome's ground, and pasted into a real client frame
   beside the greybox hero. This is a 2D approximation; the check through the real camera is
   stage 1.
5. **Prompts for the missing sheets.** `turnaround_prompts.md` has one self-contained block per
   sheet (side, 3/4, back, expression, weapon, colour script), pasted with the approved front
   attached. Each block locks the design, proportions, hex colours, T-pose, orthographic view and
   flat background. **Prompts never name another game, studio or artist.** The only style
   reference is our own approved art.
6. **Approval (human gate).** A person generates the sheet, checks it against the acceptance list
   and approves it. Then
   `python tools/comfy/approve_sheet.py <key> <sheet> <png> --by "<name>"`
   copies it to `references/`, sets its status item to `done` with the approver's name, and
   records its sha256. The tool records a decision; it never makes one.

## 4. Stage 1 — blockout with TRELLIS.2 (implemented)

1. **Input check** (cheap, seconds):
   `python tools/comfy/run_trellis.py <key> <concept.png> --mask-only --out art/characters/<key>/work/maskcheck_raw`
   runs only the graph's own background removal + crop (nodes 122/193/192/248/312) and saves the
   mask and the exact conditioning crop. Check that the mask covers the full silhouette (T-pose arm
   span, fingertips, dark props on a dark ground). If birefnet eats a part, feed a cut-out with a
   verified alpha instead and pass `--own-mask`.
2. **Generate** (283-401 s per seed measured for Brax on the RTX 4070 Laptop, one job at a time — the GPU is shared):
   `python -u tools/comfy/run_trellis.py <key> <concept.png> --seed 101 --seed 202 --seed 303`
   - graph: `tools/comfy/trellis2_character_api.json`, a verbatim copy of the user's TRELLIS.2 graph;
     patches are applied in memory and written to the provenance JSON;
   - TRELLIS.2 is forced (node 316 = True) and the Pixal3D branch is pruned before submission —
     only TRELLIS.2's MIT licence is cleared;
   - character settings kept: 700k-face decimation, 4096 px bake (a sculpt reference is judged
     close-up, so the extra detail is useful and it never ships);
   - conditioning background `#808080` (the template's black would swallow dark props);
   - waits for an idle ComfyUI queue, polls `/history`, retries after a CUDA OOM.
   Output: `art/characters/<key>/source/<key>_trellis2_s<seed>.glb` + `.json` (+ `_cond.png`, `_mask.png`).
3. **Review renders** (headless Blender, per seed):
   `blender -b -P tools/blender/gf_hero/render_blockout.py -- <glb> art/characters/<key>/work/renders/<stem> <stem>`
   normalises the mesh to 2.2 m (feet on z = 0, facing Blender −Y), renders lit, clay and unlit-albedo
   turnarounds, close-ups (the head's side view is clipped so the T-pose arm does not hide it), the
   in-game camera (orthographic, 55° pitch, yaw 0, 22 m / 28 m view heights at 1080p pixel scale), and
   diagnostics (connected components in colour, mid-plane sections). It writes topology metrics per
   body region: components, open boundary loops, non-manifold edges. About 25 s per seed.
4. **Sheets + concept IoU**: `<comfy-python> tools/comfy/blockout_sheets.py <renders> <reports/blockout> <concept> <mask> <stems...> [--selected <stem>]`
   builds the committed review sheets (every PNG < 2 MB) and the front-silhouette IoU against the
   concept mask. The IoU barely separates seeds, because TRELLIS.2 is conditioned on that exact
   silhouette. The pick comes from the close-ups and the views the concept does not show.
5. **Pick a seed** by eye against the concept, write `reports/blockout_report.md`, record the local
   GLBs with `python tools/comfy/art_manifest.py <key> --selected <glb>`, and set stage 1 to `done`
   with the note SCULPT REFERENCE ONLY. The blockout never goes to `assets/models/`.

Result for Brax (2026-09-25): three seeds; **s202** picked (faceted gauntlet plates, head/beard,
colour blocking). Known defects are listed in `art/characters/brax/reports/blockout_report.md` §6.

## 5. Stages 2-5 (implemented)

### Stage 2: production mesh (implemented; made by AI, 2026-09-25)

The user decided on 2026-09-25 that there is no human artist: stage 2 is produced by the AI pipeline at
production quality (the coordinator relayed the decision). One command rebuilds a hero and its signature
weapon from the committed inputs, in about 5 minutes on the dev machine:

```sh
python tools/blender/gf_hero/run_stage2.py <key>          # [--from <step>] [--only <step>]
```

| Step | Script | What it does |
|---|---|---|
| prepare | `s2_prepare_blockout.py` | the selected stage-1 GLB, welded, crumbs dropped, scaled to the hero height, feet on z = 0, facing −Y, the TRELLIS colour sampled into `src_col`, the approved concept behind it as a reference image → `work/<key>_retopo_start.blend` (the sculpt reference; a human could retopologise from it) |
| base | `s2_body_base.py` | the **MakeHuman hm08 base mesh (CC0)** loaded through MPFB (used as a tool only): macro sliders + CC0 face targets from `stage2_fit.json`, T-posed with MPFB's game_engine weights, reduced 4× by two un-subdivide passes (every second loop in both directions, so the joint loops survive), made symmetric from the clean half, triangle pairs joined back into quads |
| fit | `s2_body_fit.py` | a thin-plate-spline landmark warp (joints, eyes, nose, ears, skull, chin, heels) to the hero's measured landmarks, then a surface fit to the sculpt by body band (rays along the normals, so the sculpt's double-walled shell is handled; smoothed, symmetric, tangentially relaxed); head and feet near-rigid; extra knee, elbow and wrist loops; forearm radius profile; the grin (lips parted, corners up); the weapon attach frame per hand |
| parts | `s2_parts.py` | belt + buckle, sash (wrap, knot, tails), torn underskirt, three tiers of rigid skirt plates, ankle and wrist wraps, hair and beard shells (the body's own head quads pushed out to the sculpt's hair/beard, offsets smoothed, closed with rims) with chunky lofted clumps, teeth behind the parted lips, all closed meshes on the sculpt's measured envelope |
| weapon | `s2_weapon.py` + `s2_gauntlet.py` | the hero's signature chassis weapon, built on the blockout's own weapon geometry (below) |
| texture | `s2_texture.py` + `s2_uv.py` + `s2_paint.py` | UVs (region seams + shortest-path cuts on the body, smart projection elsewhere, hidden faces packed small, one texel density, one atlas); Cycles bakes of position / normal / zone / object / mask; **high-to-low from the sculpt source** with a cage: a tangent-space normal map, the source's cavity and AO, cleaned by a hit-distance mask, zone and region masks and a normalised blur; a self-AO bake of the assembled parts; then numpy **hand-painted NPR** base colour (cavity and AO folded in) + emissive from `palette.json`; one material `M_<key>` with base colour, emissive and normal map; zone kept as the face attribute `gf_zone` |
| gltf_check | `s2_gltf_check.py` | a scratch GLB export read back: every material has base colour, emissive and normal textures, every primitive NORMAL + TANGENT + TEXCOORD_0, nothing in `extensionsRequired` (bevy_gltf 0.20 maps them onto `StandardMaterial`, which the client's `ToonMaterial` extends) |
| review / sheets | `s2_review.py`, `tools/comfy/stage2_sheets.py` | toon-review / clay / albedo turnarounds, close-ups, wireframes of the joints, the in-game camera (55°, 22 m / 28 m at true 1080p pixels), bare and armed, the concept silhouette IoU, texture + UV sheets |

Budgets: the hero body set is **15 to 25k tris** (the weapon is separate), the chassis weapon **about 4 to 8k
for the pair**. Textures: one 2048² sRGB base colour + one 2048² sRGB emissive per hero; 1024² for a
weapon, each with a Non-Color tangent-space normal map (OpenGL / +Y, the glTF and Bevy convention). The
painting rules: flat painted value planes from the measured palette, no light direction (the toon shader
lights it); form comes from the normal map through the toon bands (muscle volume, rock facets), with the
sculpt's cavity and AO folded in as darker painted planes; art-directed cues only (lifted top faces on dark
rock for the 55° camera, a painted highlight band on bronze, value planes on hair); and the glows (lava, sigil,
crack network, eyes) in a separate emissive map that Heat / Meltdown scale at runtime. Polish pass
(2026-09-25): gauntlets rebuilt on the blockout's own gauntlet, normal / AO bakes, bolder sigil and crack
network, grin, chunkier hair and beard. Brax's results,
numbers and the acceptance checklist: `art/characters/brax/reports/stage2_production_mesh.md`.

**Valdris (2026-09-25, polished 2026-09-26), the armoured variant of the chain.** His blockout is plate armour, not
a body, so the same base / fit steps set only the proportions and a Valdris step makes the rest:

```sh
python tools/blender/gf_hero/s2_valdris_run.py            # [--from <step>] [--only <step>], 4-9 min, CPU only
```

| Step | What |
|---|---|
| `s2_valdris_body.py` | conforms the hm08 body into an **under-suit**: the legs follow the blockout's outer armour envelope minus the plate thickness, the torso becomes a smooth barrel, the forearms are centred for the colossus_cannon sleeve, the weapon frames are recorded on the forearm axis |
| `s2_valdris_parts.py` + `s2_valdris_geom.py` | 168 closed rigid armour pieces with suggested bones (since the polish: massive layered arms, box-lame gauntlet fists, stepped layered pauldrons, the protruding anvil with a lava gasket, segmented legs), the beard (moustache, five braids), and the separate cape with its collar |
| `s2_valdris_paint.py` | the painter behind the shared `s2_texture.py` (its new `zones` / `painter` / `bake_device` hooks): cracked stone-like gunmetal, lava veins and lava joints (its own edge and 3 cm joint-AO bakes) |
| `s2_valdris_repaint.py` | look-development aid: with `GF_VALDRIS_PAINT_CACHE=<cache.npz>` the texture step keeps the painter's inputs, and this repaints the atlas from them in about a minute; shipped textures always come from a full run |
| `s2_valdris_review.py`, `s2_valdris_sheets.py` | review renders: a Cycles-CPU emission toon (never EEVEE: the GPU is shared), the weapon GLB on the hand frame with a sleeve-fit check (its bore and its outer skin), review sheets and a before / after sheet |

Results and the stage-3 helper-bone plan: `art/characters/valdris/reports/stage2_production_mesh.md`. The shared
scripts only gained default-preserving options, so Brax's chain is unchanged (§ "Shared tool changes" in that report).

### Weapons (chassis models, user decision 2026-09-25)

Weapons are **not part of hero bodies**. Every chassis has its own model, attached to hand sockets, so any
hero can wield any chassis (6+ chassis; a hero's signature chassis is only the default).

* Source work lives in `art/weapons/<chassis>/` (own `status.json` / `manifest.json`, same schema as a hero);
  stage 5 exports `assets/models/weapons/<chassis>.glb`.
* A weapon is rigid and authored in its **socket frame**: origin at the palm centre, **+Y along the fingers,
  +Z out of the back of the hand**, +X = Y × Z (mirrored hands get mirrored frames). GF_Hero_v1 has
  `weapon_L` / `weapon_R` sockets at exactly that frame (stage 3, done 2026-09-25); in glTF the weapon scene is an
  **identity child** of the socket node (proven on Brax with the exported gauntlets:
  [`GF_HERO_SKELETON.md`](art/GF_HERO_SKELETON.md) §3). The frame's T-pose position for the hero it was designed on is recorded in the
  hero's `reports/stage2/body_fit.json` (`hand_frames`) and the weapon's `reports/stage2/parts.json`.
* Worn weapons enclose the hand and forearm; a weapon that hides the fingers ships an open and a
  closed-fist variant with identical topology (one UV layout, one texture).
* A weapon that the stage-1 blockout already shows is built on the blockout's own geometry: for the
  anvil_gauntlets, the blockout's radius around the gauntlet axis is sampled, its plate lumps give the plate
  centres, the plate tops follow its surface (radially scaled), and a scaled copy of it is the high-poly
  source of the weapon's normal bake (never shipped).
* The hero body keeps bare forearms and hands with fist-capable loops.

### Stage 3: GF_Hero_v1, the one master skeleton (implemented; made by AI, 2026-09-25)

The contract is [`docs/art/GF_HERO_SKELETON.md`](art/GF_HERO_SKELETON.md) (code: `tools/blender/gf_hero/gf_hero_rig.py`).
GF_Hero_v1 is adapted from the user's `AC_Player_Humanoid_v1` (Ashen Covenant `tools/blender/ac_player_rig/`), which is
proven there from landmarks to game import: identical core names, parents and roll, twist bones driven by Copy
Rotation, 15-bone hands, deform flags.

| Group | Bones | Notes |
|---|---|---|
| Core (23) | `root`, `pelvis`, `spine_01..03`, `neck`, `head`, `clavicle/upperarm/lowerarm/hand_L/R`, `thigh/shin/foot/toe_L/R` | identical names and parenting for every hero; `root` at the feet, never keyed (no root motion) |
| Twist (6) | `upperarm/lowerarm/thigh_twist_L/R` | driven by Copy Rotation constraints, so FK animation bakes the twist into the export |
| Hands (15 per side) | `thumb/index/middle/ring/pinky_01..03_L/R` | roll aligned to the palm normal, so +X curls toward the palm on both hands |
| Sockets (4, exported, never weighted) | `weapon_R` / `weapon_L` (children of `hand_R/L`, at the weapon grip frame), `head_top` (child of `head`), `chest_sigil` (child of `spine_03`) | built from full frames so a weapon GLB (or VFX) attaches as an identity child in glTF; further sockets are appended only when a chassis needs them |
| Per-hero extras | leaf chains prefixed `x_` (e.g. `x_sash_L_01`) | cloth, hair and tails; never rename or reparent a contract bone |

* **Conventions**: 1 unit = 1 m, the character faces −Y in Blender (+Z in glTF), +X is the character's left, Z is up,
  local +Y runs along each bone, rest pose = the stage-2 T-pose. Every runtime bone has `use_deform = True`; the
  armature object is named **`GF_Hero_v1` in every hero file** (Bevy target IDs, §2).
* **Proportions** come from each hero's landmark JSON (`work/<key>_landmarks.json`, committed), derived by
  `s3_landmarks.py` from the stage-2 fit for MakeHuman-based bodies, or written by any means for other bodies.
* **Weights** (`s3_skin.py`, numbers in `stage3_skin.json`): the MakeHuman CC0 game_engine weights, exact per vertex on
  the hm08-derived body (MPFB as a tool only), blended with Blender's bone-heat automatic weights (half on the torso
  and limbs, none on the hands, 20 % on the head); twist shares along each limb; hand-style fixes (knee cap with the
  thigh and olecranon with the forearm, spatial smoothing of the jaw fold, shoulders and knees, a relaxed knee
  dimple); parts: hair and beard 100 % head, tight parts copy the body, skirt cloth copies the body at the belt and
  then hangs from the pelvis following the thigh on its side, rigid pieces (plates, buckle, knot) one row each; at most
  4 influences, normalised, nothing unweighted (checked).
* **Validation** (`s3_poses.py`): A-pose, both-arms punch, guard, deep squat, lunge + cross, torso twist, head turns,
  fist clench, uppercut, forearm twist and a bare elbow/knee maximum, each with the signature weapon on the sockets
  (closed-fist variant), measured (stretch, collapse, volume, forearm section, weapon poke-through / cuts, weapon joint
  limits) and rendered close-up and at the client camera; `s3_gltf_check.py` exports the rig and the weapon and
  proves the identity attach numerically. CI (`check_skeleton.py`) checks every landmark file and the stage-3 reports.
* Rebuild: `python tools/blender/gf_hero/run_stage3.py <key>` (about a minute). Brax's results:
  `art/characters/brax/reports/rig_report.md`. A retarget test between two heroes comes when the second hero is rigged.

**Valdris (2026-09-26), the armoured variant.** The same master skeleton and the same under-suit weighting, through the
shared scripts; what his plate needs is added by Valdris files and two default-off hooks:

```sh
python tools/blender/gf_hero/s3_valdris_run.py            # [--from <step>] [--only <step>], about 2 min, CPU only
```

| Step | Script | What it adds |
|---|---|---|
| landmarks, lm_valdris | `s3_landmarks.py` + `s3_valdris_landmarks.py` | finger joints on the gauntlet lames, the hand bone's tail on the forearm axis (a sleeve weapon stays coaxial when the hand twists), `chest_sigil` on the anvil, 53 `x_` extras |
| skin | `s3_skin.py` + its new optional `hook` (`s3_valdris_skin.py`) | driven helpers (pauldrons lift with the arm's elevation, half-turning couters and knee cops, tassets, a max-of-thighs fauld), all additive and baked into clips by the export like the twist bones; 137 armour pieces rigid, one weight row each; beard, braids, cape and loincloth on `x_` chains; the colossus_cannon GLB as a PREVIEW on `weapon_R` |
| gltf_check | `s3_gltf_check.py` (new branch for GLB weapons) | the identity attach proven with the SHIPPED weapon GLB (0.28 µm) |
| limits | `s3_valdris_limits.py` | range-of-motion sweeps of the rigid armour (plate-inside-plate by ray parity), which chose the helper factors and set his animation ranges |
| poses, sheets | `s3_valdris_poses.py`, `s3_valdris_cloth.py`, `s3_valdris_check.py`, `s3_valdris_sheets.py` | 13 validation poses written with the stage-4 solver, the cloth chains posed clear, metrics and review sheets |

Results, the ranges stage 4 must keep, and the honest limits: `art/characters/valdris/reports/rig_report.md`. The
hooks are default-off, and Brax's stage-3 outputs are byte-identical with them
(`art/characters/valdris/reports/stage3/brax_regression.json`).

### Stage 4: animation (implemented; made by AI, 2026-09-25)

No human animator and no Mixamo / ActorCore seeds: the clips are keyed in Python on GF_Hero_v1, Cascadeur-style
(strong key poses with anticipation, contact, follow-through and weight, effector-driven), and solved per frame.
The contract, the naming, the shared table and the authoring model are in
[`docs/art/GF_HERO_SKELETON.md`](art/GF_HERO_SKELETON.md) §8. One command bakes, renders and checks a hero, in
about 10 minutes on the dev machine (almost all of it the review renders, Cycles on the CPU):

```sh
python tools/blender/gf_hero/run_stage4.py <key>          # [--from <step>] [--only <step>]
```

| Step | Script | What it does |
|---|---|---|
| anim | `s4_anim.py` (+ `s4lib.py`, `s4_clips.py`, `s4_<key>.py`) | the shared set (24 clips) + the hero's unique set, key poses interpolated in parameter space and solved every frame with an analytic two-bone IK (soft limits: elbow 145°, knee 150°) and the arm keep-out (the hand's weapon volume is pushed out of the skinned body; GF_HERO_SKELETON §7); one action + one NLA track per clip in `production/<key>_anim.blend`; metrics per clip in `reports/anim/clips.json`: loop seam, foot slide in world space, in-place drift, wrist rule, elbow / knee range and eased frames, IK misses, keep-out pushes and residual overlap, the gauntlet variant swaps |
| render | `s4_render.py` | the key frames: toon close-ups (front 3/4 + side on a 0.5 m grid) and the 55° client camera at true 1080p pixels; mesh checks (ground, the sleeve weapon against the body and against the other gauntlet) |
| sheets | `s4_sheets.py` | a contact sheet per clip (key frames, game size at 1x and 3x, the feet's world track, the numbers) + the game-size boards |
| gltf_check | `s4_gltf_check.py` | a scratch GLB with every clip read back: names, durations, 30 fps, in place, loops closed, twist bones baked, no required extensions |
| contract | `check_clips.py` | the stdlib contract (also a CI job): names, loops, planted feet, the wrist rule, reach, the elbow / knee limits, the keep-out residual, the ground |

Weapon fire stays procedural (recoil, aim, hit-stop); the fire and strike clips are short upper-layer clips that
start and end on the `idle_combat` reference pose. Aim offsets are not authored: at the 55° top-down camera the hero
turns to the aim, and the torso-versus-legs split is covered by the strafe and backpedal clips. Brax's results:
`art/characters/brax/reports/anim_report.md`.

**Valdris (2026-09-26), the armoured variant.** His plate rules out most of the library's arm and foot keys (his cannon
elbow is clean to about 30°, his arms live between −45° and +30° of elevation, his sabaton's instep lame rides the
shin and its sole is one rigid plate past the ball), so his module poses the shared set itself through the new
default-off hooks of `s4_anim.py`, and a cloth pass and his own audit follow the bake:

```sh
python tools/blender/gf_hero/s4_valdris_run.py            # [--from <step>] [--only <step>], about 12 min, CPU only
```

| Step | Script | What it adds |
|---|---|---|
| anim | `s4_anim.py` + `s4_valdris.py` | `shared_clips(K)`: the 24 shared clips (same names, loops, layers, events, timing) re-posed in his vocabulary: arms as upper-arm / forearm directions inside his ranges, interpolated by direction; planted feet with upright shins (the pelvis solved through s4lib's own leg IK); feet that roll about the sole's front and rear edges and, in the air, hang in line with the shins; a wider, heavier gait; one knee down built, not solved. `unique_clips(K)`: his 10 kit clips. `KEEPOUT_LOOSE_PARTS` / `KEEPOUT_OWN_BONES` for the arm keep-out |
| cloth | `s4_valdris_cloth.py` | the cape, loincloth and braid chains keyed in every clip: a lagged hang under the apparent gravity at the pin, drag against the design travel, cleared out of the plates and the ground every frame (the stage-3 clear step), smoothed so it never pops |
| render | `s4_valdris_render.py` | the key-frame renders, and the stage-3 measures on EVERY frame: plate clipping, the cannon's poke-through and cuts, cloth inside a plate, the ground, sole slip |
| sheets | `s4_valdris_sheets.py` | a sheet per clip and the game-size boards next to the concept |
| gltf_check, contract | `s4_gltf_check.py`, `check_clips.py` (shared, unchanged) | as for Brax |

Results and findings: `art/characters/valdris/reports/anim_report.md`. The hooks are default-off, and Brax's stage-4
outputs are byte-identical with them (`art/characters/valdris/reports/anim/brax_regression.json`).

### Stage 5: export & validate (implemented; made by AI, 2026-09-25)

No human step: the export is headless Blender, and the quality gate is the validators and the review renders of the
shipped file (the user's decision: content over tests, no test sweeps). The user's final visual approval is the only
human gate. One command exports, checks and reviews a hero and its signature chassis weapon, in under a minute:

```sh
python tools/blender/gf_hero/run_stage5.py <key>          # [--from <step>] [--only <step>]
```

| Step | Script | What it does |
|---|---|---|
| weapon | `export_glb.py --weapon <chassis>` | the signature chassis weapon, when the gf_hero chain built it (`art/weapons/<chassis>/production/<chassis>_stage2.blend`) → `assets/models/weapons/<chassis>.glb` + `.meta.json` in the `docs/art/WEAPONS.md` layout |
| export | `export_glb.py --key <key>` | `production/<key>_anim.blend` → `assets/models/characters/<key>.glb` + `<key>.meta.json`: Blender-side checks, the export, the gate, source fidelity → `reports/export_report.json` |
| reimport | `smoke_import.py` | a fresh factory-settings Blender re-imports the shipped files: names, every clip played one frame, the weapon on the sockets, review renders (`work/renders/stage5/`) |
| sheet | `s5_sheets.py` (PIL) | `reports/stage5/export_review.png`: the stage-4 source next to the shipped file, and the client camera at true pixel size |
| board | `s5_<key>_sheets.py` (PIL, optional) | a hero's own board, skipped when there is none (Valdris: the shipped file next to the concept and the blockout) |
| validate | `validate_glb.py --blender` | exactly what CI runs |

What each step runs, for use on its own:

```sh
<blender> -b --python-exit-code 1 art/weapons/<chassis>/production/<chassis>_stage2.blend -P tools/blender/gf_hero/export_glb.py -- --weapon <chassis>
<blender> -b --python-exit-code 1 art/characters/<key>/production/<key>_anim.blend -P tools/blender/gf_hero/export_glb.py -- --key <key>
<blender> -b --factory-startup --python-exit-code 1 -P tools/blender/gf_hero/smoke_import.py -- assets/models/characters/<key>.glb \
        --weapon assets/models/weapons/<chassis>.glb --render art/characters/<key>/work/renders/stage5 --report art/characters/<key>/reports/export_report.json
<comfy-python> tools/blender/gf_hero/s5_sheets.py <key>
python tools/blender/gf_hero/validate_glb.py assets/models/characters/<key>.glb --blender <blender> [--json <report.json>]
```

**The shipped hero file** (`assets/models/characters/<key>.glb`):
- glTF binary, +Y up, 1 unit = 1 m, the hero faces +Z, rest pose = the T-pose; uncompressed (§6), PNG textures
  embedded;
- the scene's single root is the armature node `GF_Hero_v1`: the 63 deform bones of the contract (core, twist,
  fingers, the four sockets, any `x_` extras) and nothing else;
- **one** skinned mesh `<key>_mesh`: the body parts are joined at export (one draw call). It has one material `M_<key>`
  with base colour, emissive and normal textures (≤ 2048 px), KHR_materials_emissive_strength (used, not required),
  and TANGENT. It is single-sided when every part is closed, as Brax's are;
- **no vertex colours**: Bevy multiplies the base colour by `COLOR_0`, and the stage-2 paint masks (`gf_mask`,
  `src_col`) would otherwise ship as `COLOR_0` / `COLOR_1` (the stage-4 scratch export had them);
- every clip is one animation `<key>_<clip>[@loop]`, sampled at 30 fps from t = 0 (frames + 1 samples). All the bones
  are keyed, so blending never keeps a stale pose, and the twist constraints are baked;
- re-exporting an unchanged source gives a byte-identical file, so a rerun never adds an LFS blob.

**The sidecar** `<key>.meta.json` holds what glTF cannot:
- `skeleton` and `joints`, plus `tris`, `textures` and `material`;
- `sockets`: the rest frames in glTF, with parents;
- `clips` (the names), `clip_info` and `playback` (the engine rules). Per clip, `clip_info` gives loop, layer, frames,
  duration, the `events` (frame and time: strike, launch, slam and so on), the design speed, the weapon-variant swap
  frames per hand and the sim state it maps to;
- `weapon`: the default chassis and its GLB;
- `status: ai_final_pending_user_approval`, and the GLB's `glb_sha256`. The gate rejects a stale sidecar.

**The gate** (`validate_glb.py`, standard library only, CI) rejects:
- a container that is not GLB 2.0, a file over 20 MB, or a required extension that bevy_gltf 0.20 cannot load
  (Draco, meshopt and quantisation are banned outright);
- an unnamed or duplicated node (Bevy drops the animation of an unnamed path);
- a skeleton whose names or parents differ from GF_Hero_v1, more than 256 joints, or inverse bind matrices that
  disagree with the rest pose;
- missing sockets, sockets off the hands or not facing forward, sockets that differ from the committed landmark
  file, or animated sockets;
- unweighted vertices, more than 4 influences, weights that do not sum to 1, weight on root or a socket, vertex
  colours, or a missing NORMAL / TANGENT / TEXCOORD_0;
- more than 25k triangles for the hero, a texture over 2048 px, a texture that is not PNG, or a missing base colour /
  emissive / normal texture;
- clips: every clip of `tools/blender/gf_hero/required_clips.json` must be there (the shared set, kept equal to
  `s4_contract.SHARED_CLIPS`, plus the hero's unique block) with the right `@loop` suffix. Bad or duplicate names,
  a clip that is not 30 fps from t = 0, a moving root, a bone other than the pelvis translating, scaling bones and
  open loops are all rejected;
- a rest height outside 1.8-2.5 m, or feet off y = 0;
- a stale sidecar;
- a weapon that does not enclose each hand once it sits on the sockets.

The export adds **Blender-side checks** before writing: the same weight rules per part, closed surfaces, one UV
map, the NLA tracks against `clips.json` and `required_clips.json`. After writing it runs a **source-fidelity** check:
for every clip, at its first, middle and last frame, every joint's world matrix from the GLB's own forward
kinematics must equal the Blender pose bone within 1e-4. The **re-import smoke test** covers everything that depends
on Blender's importer:
- the armature name;
- bone names and parents, and the sockets;
- skinning;
- one action per animation, each played one frame against the GLB's kinematics;
- a sane mesh at every clip;
- the weapon scene on `weapon_R` with its `offhand` on `weapon_L` (a sleeve weapon without an `offhand` node, such as
  the colossus_cannon, rides `weapon_R` alone).

A new hero adds its unique clips to `required_clips.json`; everything else is generic. A hero may add
`tools/blender/gf_hero/s5_<key>.py` (plain data: `REVIEW_SHOTS`, `ATTACH_FOLLOW`, `CLOSEUP`) when Brax's default review
shots (`jab_r`, `uppercut`, `meltdown_start`) are not his clips.

**CI.** The job `hero-glb` in `.github/workflows/art.yml` runs on changes to `assets/models/**` or `tools/blender/**`
(the workflow's paths). It fetches the shipped models from Git LFS, downloads the newest Blender 5.2.x LTS for Linux
(cached), and runs `validate_glb.py --blender` on every `assets/models/characters/*.glb`. The export itself runs on the
dev machine; CI checks what is committed. The **Bevy-side import** is a Rust test that loads the GLB through
bevy_gltf, spawns `#Scene0` and plays each clip. It belongs to the engine integration (`crates/`, not the art track).

**The weapon file.** A chassis that the gf_hero stage-2 chain builds ships in the WEAPONS.md layout. The root
`<chassis>` is the right grip frame. Under it sit `grip_R` (the origin), `muzzle` (the strike point),
`glow_core` and `grip_L`. The `offhand` node holds the left pair and `muzzle_2`; the client re-parents it to
`weapon_L` with an identity transform. A weapon with hand variants ships them as separate mesh nodes:
`<chassis>_fist_R` / `<chassis>_open_R` / `<chassis>_fist_L` / `<chassis>_open_L`. All four are visible when the
scene spawns; the client hides the pair it does not show, per hand, at the swap frames the hero's `clip_info` gives.

Brax's results (2026-09-25):
- `brax.glb`: 9.97 MB, 15,048 tris, 63 joints, 34 clips, three 2048² textures;
- source fidelity 1.9e-5, Blender re-import 1.8e-6, bind pose 1.1e-6;
- `anvil_gauntlets.glb`: 3.65 MB, 7,716 tris shown, 15,432 with both variants;
- all of it in `art/characters/brax/reports/export_report.json` and `reports/stage5/export_review.png`.

**Valdris (2026-09-26), the armoured variant.** The same command, the same exporter and gate: `python
tools/blender/gf_hero/run_stage5.py valdris` (about 35 s). His signature weapon, the colossus_cannon, is the weapon
track's file (`tools/blender/gf_assets`), so the weapon step is skipped and the shipped
`assets/models/weapons/colossus_cannon.glb` is attached as it is. What his stage 5 added, all default-off for Brax:

| Piece | Script | What it does |
|---|---|---|
| hook | `s5_valdris.py` | plain data for `smoke_import.py`: his seven review shots (the guard, the heavy shot, the Bulwark landing, the Siege brace, the run, the Mountainfall pound, the open-hand ping), the clip the cannon must ride `weapon_R` through (`fire_heavy` f6), a wider close-up for his 2.33 m |
| sleeve weapon | `smoke_import.py`, `export_glb.py` (shared) | a weapon GLB without an `offhand` node rides `weapon_R` alone and its mesh is always shown; in the sidecar `clip_info.<clip>.weapon_variant` is null (the cannon has no variants) and the fist / open frames of his own gauntlet fingers are `hand_pose` |
| board | `s5_valdris_sheets.py` | `reports/stage5/valdris_board.png`: the shipped file next to the concept, the turnaround and the blockout, and every review shot at game size |

His results:
- `valdris.glb`: 16.89 MB, 24,958 tris (the 25k budget), 116 joints (63 contract + 53 `x_` armour helpers and cloth
  chains), one single-sided `M_valdris` with three 2048² PNGs, 34 clips; 0 errors, one warning: the rest height
  2.33 m (the pauldron tops; his crown is 2.305 m) is over the 2.0-2.3 m hero range, as stage 2 measured;
- source fidelity 4.5e-5, Blender re-import 2.7e-5 over all 34 clips, bind pose 1.9e-6; the cannon's rest attach
  1.5e-7, and it rides `weapon_R` through the heavy shot to 5.4e-7;
- re-exporting is byte-identical; Brax's stage-5 outputs are unchanged by the shared changes
  (`art/characters/valdris/reports/stage5/brax_regression.json`);
- all of it in `art/characters/valdris/reports/export_report.json`, `reports/stage5/export_review.png` and
  `reports/stage5/valdris_board.png`.

## 6. Export format note (stage 5)

`bevy_gltf-0.20.0-rc.1` (`src/lib.rs`, "Supported KHR Extensions" table) supports **none** of
`KHR_draco_mesh_compression`, `KHR_mesh_quantization` or `EXT_meshopt_compression`. A GLB that
lists any of them in `extensionsRequired` will not load. Stage 5 therefore exports **uncompressed**
glTF (float positions, no quantisation) and stays inside the per-hero budget instead
(~15-25k tris, textures sized for 6-8 % of screen height). The client enables only `bevy/png`, so textures ship
as PNG (no JPEG, WebP or KTX2). `docs/ARCHITECTURE.md` §9 still says "(meshopt)"; its owner needs to update that
line now that stage 5 has landed.

§9 also names `tools/blender/export.py`. The exporter is `tools/blender/gf_hero/export_glb.py` (§5, stage 5), so that
line needs the same update.

**CI already guards the format.** `.github/workflows/art.yml` runs `tools/comfy/check_art.py` on
every change under `art/`, `assets/models/` or the art tools. It rejects:
- a GLB under `assets/models/` that requires an extension bevy_gltf 0.20 cannot load;
- any file over 20 MB that git tracks or would add;
- a local-only file that git tracks;
- a status.json that breaks the gate rules (§1).

Since stage 5 the job `hero-glb` adds the full gate and the Blender 5.2 re-import smoke test for every shipped hero
GLB (§5, stage 5).

## 7. Licensing and provenance

* **ChatGPT (stage 0).** OpenAI's Terms of Use assign ownership of the output to the user. The
  user's own review read them on 2026-09-18 for Ashen Covenant
  (`docs/production/SECURITY_AND_LICENSING.md` §2/§4 there).
* **TRELLIS.2 (stage 1).** The code (`github.com/microsoft/TRELLIS.2`) and the weights
  (`huggingface.co/microsoft/TRELLIS.2-4B`) are both **MIT**, per the same review. It runs
  locally through ComfyUI: no hosted service and nothing to accept.
* **Pixal3D: not used.** The user's graph can switch to Pixal3D, and its saved template leaves
  switch node 316 on the Pixal3D side. GODFORGE forces TRELLIS.2 and prunes the Pixal3D branch
  (§4). Only TRELLIS.2's licence is cleared for this project.
* **Other models inside the TRELLIS.2 branch:**
  - The DINOv3-L conditioning encoder (`dino_v3_L_naf_fp32`) ships under Meta's own DINOv3
    licence, **not MIT**. Nobody has read it for GODFORGE yet, so it is listed as a
    `pending_human` gate in each hero's status.json.
  - BiRefNet (background removal) is MIT according to its repository; not re-read here.
  - MoGe-2 feeds only the pruned Pixal3D branch.
* **MakeHuman hm08 base mesh (stage 2).** The body topology of every AI-made stage-2 hero starts from
  the MakeHuman `hm08` base mesh and its targets, which their copyright holders explicitly released as
  **CC0** in September 2020 (header of `data/3dobjs/base.obj` in the MPFB install). **MPFB** (the
  MakeHuman add-on for Blender, GPL-3.0-or-later) is used **only as a tool** in the user's Blender to load
  that mesh, apply the CC0 macro/face targets and the CC0 game_engine rig weights for the T-pose; no MPFB
  code or MPFB data file is copied into GODFORGE or shipped. The hero's shape comes from the fit to our own
  approved sculpt reference; `art/characters/<key>/reports/stage2/` records the base-mesh statistics.
* **Style.** No style LoRA exists. If one is trained, it is trained **only** on our own approved
  style bible (approved sheets), never on competitor art. Prompts and workflows never name another
  game, studio or artist. "The Hades-II bar" is a quality bar that humans apply; it is not a style
  source.
* **Provenance.** Every generated file has a record: the stage-1 JSON next to each GLB (model,
  graph hash, patched inputs, seed, input sha256), `palette.json` (source sha256, method), and
  `manifest.json` (sha256 of the references and the local-only files).

## 8. Large files and Git LFS

**Git LFS is enabled (2026-09-25, the user's approval).** The repo `.gitattributes` routes `*.glb`,
`*.blend`, `*.fbx`, `*.abc`, `*.psd`, `*.kra`, `*.exr`, `*.hdr`, `*.tga`, `*.tif(f)` and
`art/**/textures/**/*.png` through LFS. What is committed through LFS: each hero's **selected** stage-1
GLB (re-included in `art/.gitignore`), the stage-2 production `.blend` files and the textures. What stays
local and is only recorded (path, bytes, sha256) in the asset's `manifest.json`: the unselected TRELLIS
seeds, the ComfyUI previews and `work/` (renders, logs, the intermediate `.blend` files of the stage-2
chain, which `run_stage2.py` regenerates). Nothing over 20 MB is committed outside LFS; `check_art.py`
enforces it in CI. Run `git lfs install` once per machine.
