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
| 3 | weight-paint sign-off (shoulders, hands, face) | **human** | `pending_human` → `done` with `signed_off_by` |
| 4 | none for the clips themselves | — | Mixamo/ActorCore-seeded clips are `stand_in` |
| 5 | the final Hades-II bar | **human** | `done` with `signed_off_by`. Only then may the hero's `final` be `true` |

**Decision of 2026-09-25 (the user, relayed by the workflow coordinator): there is no human artist for
stage 2.** The production mesh, UVs and NPR textures are made by the AI pipeline in §5 at production
quality, not as a stand-in. The human gate that remains at stage 2 is the user's own visual approval.

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
  silhouette matters more than micro-detail.
* **Procedural stays procedural.** Weapon fire, recoil, aim offsets and hit flinches stay
  procedural in `scene.rs`, so they don't multiply authored clips.

### Clip naming

* Every clip in a hero's GLB is named `{char}_{clip}`, and loops add `@loop`: `brax_idle@loop`,
  `brax_run@loop`, `brax_dash`, `brax_hit_front`, `brax_death`, `brax_cinder_uppercut`,
  `brax_meltdown_idle@loop`. `{clip}` is lower_snake_case.
* The **shared set** (~40 clips) uses the same `{clip}` names for every hero, so the client maps
  a state to `format!("{key}_{clip}")` and never special-cases a hero. The **unique set** (6 to 10
  clips: ult, 2 actives, signature idle) is named after the kit's abilities.
* Shared clips are authored once on GF_Hero_v1 (§5) and **baked per hero** at export, on that
  hero's proportions (hip height, reach).
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
  reports/        review sheets (PNG < 2 MB) and stage reports (committed); reports/stage2/ = stage-2 sheets + JSON
  stage2_fit.json / stage2_parts.json / stage2_texture.json   the hero's stage-2 inputs (landmarks, part
                  parameters, paint settings; committed, hand-edited)
  production/     <key>_stage2.blend: the production mesh + material (committed, Git LFS)
  textures/       <key>_basecolor.png, <key>_emissive.png (committed, Git LFS)
  manifest.json   sha256 of the references + every local-only file: path, bytes, sha256 (committed)
  status.json     per stage: status, outputs, human_signoff_required, notes (committed)
art/weapons/<chassis>/   one folder per chassis weapon model, same layout and the same status/manifest schema
                  (stage2_weapon.json, stage2_texture.json, production/, textures/, reports/stage2/)
tools/comfy/      ComfyUI drivers and the user's graphs (API format), plus the stdlib/PIL art tools:
                  palette_extract.py, readability_sheet.py, approve_sheet.py, art_manifest.py, check_art.py
tools/blender/gf_hero/   headless Blender scripts: stage-1 review renders, the stage-2 chain (run_stage2.py, s2_*.py),
                  later rig/export
assets/models/characters/<key>.glb   shipped hero mesh only (stage 5 output; the client falls back to greybox when missing)
assets/models/weapons/<chassis>.glb  shipped weapon model (stage 5 output), attached to the weapon sockets
```

Git LFS is enabled (repo `.gitattributes`, 2026-09-25): `.blend`, `.glb` and `art/**/textures/**/*.png` go
through LFS. No file over 20 MB is committed outside LFS; `art/.gitignore` keeps scratch and unselected raw
output local (§8).

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

## 5. Stages 2-4 (stage 2 implemented; 3-4 planned)

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

### Weapons (chassis models, user decision 2026-09-25)

Weapons are **not part of hero bodies**. Every chassis has its own model, attached to hand sockets, so any
hero can wield any chassis (6+ chassis; a hero's signature chassis is only the default).

* Source work lives in `art/weapons/<chassis>/` (own `status.json` / `manifest.json`, same schema as a hero);
  stage 5 exports `assets/models/weapons/<chassis>.glb`.
* A weapon is rigid and authored in its **socket frame**: origin at the palm centre, **+Y along the fingers,
  +Z out of the back of the hand**, +X = Y × Z (mirrored hands get mirrored frames). Stage 3 adds
  `weapon_L` / `weapon_R` sockets on GF_Hero_v1 at exactly that frame; the weapon then parents with an
  identity local transform. The frame's T-pose position for the hero it was designed on is recorded in the
  hero's `reports/stage2/body_fit.json` (`hand_frames`) and the weapon's `reports/stage2/parts.json`.
* Worn weapons enclose the hand and forearm; a weapon that hides the fingers ships an open and a
  closed-fist variant with identical topology (one UV layout, one texture).
* A weapon that the stage-1 blockout already shows is built on the blockout's own geometry: for the
  anvil_gauntlets, the blockout's radius around the gauntlet axis is sampled, its plate lumps give the plate
  centres, the plate tops follow its surface (radially scaled), and a scaled copy of it is the high-poly
  source of the weapon's normal bake (never shipped).
* The hero body keeps bare forearms and hands with fist-capable loops.

### Stage 3: GF_Hero_v1, the one master skeleton

GF_Hero_v1 is adapted from the user's `AC_Player_Humanoid_v1` (Ashen Covenant
`tools/blender/ac_player_rig/`), which is proven there from landmarks to game import.

| Group | Bones | Notes |
|---|---|---|
| Core (23) | `root`, `pelvis`, `spine_01..03`, `neck`, `head`, `clavicle/upperarm/lowerarm/hand_L/R`, `thigh/shin/foot/toe_L/R` | identical names and parenting for every hero |
| Twist (6) | `upperarm/lowerarm/thigh_twist_L/R` | driven by Copy Rotation constraints, so FK animation bakes the twist into the export |
| Hands (15 per side) | `thumb/index/middle/ring/pinky_01..03_L/R` | roll aligned to the palm normal, so +X curls toward the palm on both hands |
| Sockets (exported, never weighted) | `weapon_L` / `weapon_R` (child of `hand_L/R`, at the weapon socket frame: origin palm centre, +Y along the fingers, +Z out of the back of the hand); proposed: `hand_fx_L/R`, `chest_fx_socket`, `head_fx_socket`, `feet_fx_L/R`, `back_socket` | the weapon sockets are fixed by the 2026-09-25 weapons decision (§5); the rest is trimmed or extended when the roster's chassis are mapped |
| Per-hero extras | leaf chains prefixed `x_` (e.g. `x_sash_L_01`) | cloth, hair and tails; never rename or reparent a contract bone |

* **Conventions** (from the source rig): 1 unit = 1 m, the character faces −Y in Blender (+Z in
  glTF), +X is the character's left, Z is up, and local +Y runs along each bone. Every runtime bone
  has `use_deform = True`, so the glTF exporter keeps it. Control bones from Rigify or AccuRIG
  have `use_deform = False`. The armature object is named **`GF_Hero_v1` in every hero file**
  (Bevy target IDs, §2).
* **Proportions** come from each hero's landmark JSON (bone head and tail positions, the Ashen
  Covenant `make_landmarks_*.py` pattern). The hierarchy never changes.
* **Weights** start as auto weights, get hand fixes on the shoulders, hands and face, and then
  need a human sign-off. Validation poses and a retarget test between two heroes (the Ashen
  Covenant p04/p07 steps) come before any clip work.

### Stage 4: animation

The shared set (~40 clips) is authored once on GF_Hero_v1 and baked per hero at export (§2 clip
naming). The unique set per hero is 6 to 10 clips: ult, 2 actives and a signature idle. Brax's
proposal is in `art/characters/brax/brief.md` §8. Mixamo or ActorCore seeds are prototype
`stand_in`s and are replaced before final. Weapon fire stays procedural.

## 6. Export format note (stage 5, checked now so nobody plans around a dead end)

`bevy_gltf-0.20.0-rc.1` (`src/lib.rs`, "Supported KHR Extensions" table) supports **none** of
`KHR_draco_mesh_compression`, `KHR_mesh_quantization` or `EXT_meshopt_compression`. A GLB that
lists any of them in `extensionsRequired` will not load. Stage 5 therefore exports **uncompressed**
glTF (float positions, no quantisation) and stays inside the per-hero budget instead
(~15-25k tris, textures sized for 6-8 % of screen height). `docs/ARCHITECTURE.md` §9 still says
"(meshopt)"; that line needs updating by its owner when stage 5 lands.

§9 also names `tools/blender/export.py`. The exporter will live in `tools/blender/gf_hero/` with
the rest of the hero scripts, so that line needs the same update.

**CI already guards the format.** `.github/workflows/art.yml` runs `tools/comfy/check_art.py` on
every change under `art/`, `assets/models/` or the art tools. It rejects:
- a GLB under `assets/models/` that requires an extension bevy_gltf 0.20 cannot load;
- any file over 20 MB that git tracks or would add;
- a local-only file that git tracks;
- a status.json that breaks the gate rules (§1).

The headless Blender export and the import smoke test join that workflow with the stage-5
exporter.

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
