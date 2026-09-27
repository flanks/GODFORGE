# Kael — stage 1 blockout report (TRELLIS.2)

> **SCULPT REFERENCE ONLY.** The meshes described here are dense, unrigged TRELLIS.2 output with baked lighting in
> the texture. They are never copied to `assets/models/` and never shipped. They are the silhouette and proportion
> reference for the stage-2 production mesh (`docs/ART_PIPELINE.md`). The selected seed's GLB is committed through
> Git LFS so a fresh clone has it; the other seeds stay local.

**Picked seed: `s202`** → `art/characters/kael/source/kael_trellis2_s202.glb`
(63,502,248 bytes, sha256 `5ca75c6c…dfaab5`, Git LFS, provenance `source/kael_trellis2_s202.json`).

Summary sheet: [`blockout/blockout_selected.png`](blockout/blockout_selected.png) ·
all seeds: [`blockout/blockout_compare.png`](blockout/blockout_compare.png) ·
input check: [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png) ·
input edit: [`blockout/input_edit.png`](blockout/input_edit.png)

Date: 2026-09-27. Tools: `tools/comfy/run_trellis.py`, `tools/comfy/maskcheck_sheet.py`,
`tools/blender/gf_hero/kael_stage1_input.py`, `tools/blender/gf_hero/kael_render_blockout.py` and
`kael_render_blockout_parts.py` (Cycles-CPU copies of the shared renderers, below), `tools/comfy/blockout_sheets.py`,
`tools/comfy/art_manifest.py` (commands at the end). The views, parts and body regions are in
[`../blockout_views.json`](../blockout_views.json).

## 1. Input

| | |
|---|---|
| Concept | `references/KAEL_front_approved.png`: the user's approved front (1536x1024, T-pose, flat navy `#141E27`), verbatim, sha256 `237a8187…4dce6` |
| Ghost arm side | as painted: his **left** arm (image right), not mirrored (`status.json` `decisions[ghost_arm_side]`) |
| Cut-out | the graph's own birefnet (node 192) on the verbatim concept, then **edited**: the two revolvers and the diffuse ghost smoke removed from the alpha → `references/kael_concept_front_nogun.png` (the concept's own RGB, verified identical; only the alpha is new), fed with `--own-mask` (InvertMask of the PNG alpha) and ImageCropToMask (312) on `#808080` |
| Check | [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png) (birefnet vs an independent colour key), [`blockout/input_edit.png`](blockout/input_edit.png) (what the edit removed, and the conditioning crop the graph built from it) |

**Birefnet on dark-on-dark.** The worry was the black glove, the violet-black coat and the dark boots on the navy
ground. Birefnet kept all of it. The check compares its mask with a colour key over a fitted background model (a
4th-order polynomial per channel; residual mean 0.6, p99 1.9 RGB levels; key threshold 12): mask bbox x 79–1454,
y 24–998, the key's x 78–1454, y 20–998. Pixels the key calls "hero" that lie more than 3 px outside the mask: right
fist + gun 1, ghost fist + gun 3, between the legs 8, boots 0, head + hair 60 (flyaway hair tips), the coat flanks
2,011 and 195 (the faintest outer smoke, which is cut anyway). 47,674 px inside the mask the colour key would drop
(the darkest coat and trouser faces): a colour-key cut-out would be worse than birefnet.

**Why the mask was edited (the one input change).** Birefnet does its job too well for a body blockout:
- **The revolvers.** The barrels are collinear with the arms and the grips sit inside the fists. TRELLIS.2 would
  grow each arm into one arm-gun tube and wrap the fingers round a grip. Weapons are separate models (the user's
  decision), so inside a box round each hand only the fist polygon is kept: barrel, cylinder, hammer spikes and the
  grip below the fist are cut. The fists stay closed round an empty grip line.
- **The ghost smoke.** The translucent teal smoke round the coat, with the navy showing through its holes, is all
  inside birefnet's mask (about a quarter of it by area). It would come back as wide opaque fins round the coat; the brief asks
  for a coat with a ragged hem and 4-6 chunky emissive tatters built in stage 2. Below the belt and outside the legs'
  column every pixel with G > R (the smoke, its dark mottling and the navy) is cut; the coat is violet-black and the
  leather brown (R ≥ G), so they stay; inside the legs' column only the bright smoke goes. Then the largest connected
  part, a small open/close, holes filled.

Kept: 281,452 of birefnet's 390,501 px. The figure fills more of the 1024² conditioning crop than it would with the
guns (arm span 952 px instead of 1,376), so TRELLIS.2 sees the body at a larger scale.

## 2. Generation

The user's TRELLIS.2 graph (`tools/comfy/trellis2_character_api.json`, unchanged, template sha256 `8471ef6d…bb133c`)
was run with TRELLIS.2 forced (node 316 = True) and the Pixal3D branch pruned. The character settings were kept
(DecimateMesh 700,000 faces, 4096 px bake, 2048 px normal bake), exactly as for Brax and Valdris. The seeds ran one
after another on the shared RTX 4070 Laptop (ComfyUI queues the other hero's jobs serially), with no OOM and no retry.

| Seed | Node seeds (3/18/23/12) | Prompt id | GPU time | High-poly decode | Output GLB |
|---|---|---|---|---|---|
| s101 | 104 / 119 / 124 / 113 | `e459b9bc…` | 432 s | 7.90 M verts / 15.83 M faces | 68.1 MB, `cba5f8b8…` |
| **s202** | 205 / 220 / 225 / 214 | `43a5af1f…` | 401 s | 7.63 M / 15.34 M | 63.5 MB, `5ca75c6c…` |
| s303 | 306 / 321 / 326 / 315 | `6488a250…` | 351 s | 6.91 M / 13.85 M | 66.0 MB, `8929a9c2…` |

All three GLBs have one double-sided material on one mesh (692-694k tris) with a 4096² base colour, a 4096² packed
occlusion/roughness/metallic map and a 2048² normal map, and no glTF extensions. Full records:
`source/kael_trellis2_s<seed>.json`.

## 3. Review renders

Everything is rendered with the hero normalised to **2.1 m** (the brief's proposed height; feet on z = 0, facing
Blender −Y, his right = −X). The lit renders use **Cycles on the CPU** (24 samples, OpenImageDenoise): the shared
renderers use EEVEE, and the GPU was busy with TRELLIS.2 for both heroes, so this pack uses copies
(`tools/blender/gf_hero/kael_render_blockout.py`, `kael_render_blockout_parts.py`) that change only the lit engine;
names, framing, lights and metrics are the shared ones. Clay and albedo are Workbench as before. About 2.5 min per
seed. Per seed, in `blockout/`:

- `*_turnaround.png`: lit, clay and unlit albedo at a common ortho scale.
- `*_closeups.png`: head + collar (front, 3/4, side with the arm clipped away), the right (gloved) fist and the left
  (ghost) fist (front, 3/4, end-on), lit and clay.
- `*_closeups2.png`: the whole figure from above and at the game's 55° pitch (front and 3/4), the coat (back, back
  3/4, his right side), the legs and coat hem (front, 3/4, back), a horizontal cut at 33 % of the height (front at the
  bottom) and vertical cuts through each thigh; the last row shows connected components and mid-plane sections.
- `*_ingame.png`: the client camera (orthographic, 55° pitch, yaw 0; 22 m and 28 m view height) at true 1080p pixels,
  with 3x zooms.
- `*_silhouette.png`: the front silhouette against the edited concept mask.

I looked at every sheet and at the full-size renders (`work/renders/`, local only). The topology numbers come from
`*_parts_metrics.json` (welded vertices, Kael's body regions from `blockout_views.json`).

## 4. Comparison against the concept

| Criterion | Concept | s101 | **s202** | s303 |
|---|---|---|---|---|
| Hands (empty fists) | right: black fingerless glove, skin fingers; left: ghost hand | shapes clean, but **the textures are swapped**: a green fist on the gloved sleeve, a dark gloved fist on the ghost arm | **right gloved fist with skin fingers, left ghost fist**; the ghost fist's knuckles baked dark with teal glints | the ghost hand is **gloved**; a **grip-shaped tunnel through the right fist** |
| Ghost arm | his left forearm, mint ghost flesh | mint-green, mottled | **pale mint, mottled**, from the bicep strap to the wrist | pale blue-white, thin |
| Head / face | swept dark hair, grey streak, stubble, smirk, glowing left eye with glow over the left cheek | dark face, hair over the eyes | good hair mass and collar; the face glow baked as a **pale patch over the left eye and cheek** | **sharpest face** (brow, smirk, beard) |
| Collar | high, two points framing the head | tall, ragged | **tall with clean points**, open at the front | tall, but a **hood** grows at the back (not in the concept) |
| Coat back (not in the concept) | — (brief: one violet panel, torn hem) | dark with red streaks, shaggy | **one solid dark violet-navy panel, torn into long points at the hem** | solid, but baked **teal-blue** |
| Coat vs legs (33 % cut, thigh cuts) | the coat hangs round the legs, open at the front | legs clear of the coat | **legs clear of the coat** | legs clear of the coat |
| Front silhouette IoU vs the edited mask | — | 0.856 | 0.833 | 0.825 |
| Span / height (concept 0.979) | — | 0.991 | 0.999 | 1.003 |
| Arm line (72-80 % height) / coat at 10-30 % / at 30-45 % | 2.06 m / ≤ 1.21 m (tatter tips) | 2.08 / 1.33 / 1.44 m | 2.09 / 1.31 / 1.37 m | 2.11 / 1.21 / 1.29 m |
| Depth | — | 0.90 m | 0.95 m | 0.77 m |
| Connected components (welded) | — | 32: main + a **1,804-vert coat slab at his right hip** + a 1,447-vert piece in front of the belt + crumbs | **67: one main shell (334k verts) + crumbs of ≤ 608 verts** | 46: main + a **4,102-vert floating pouch** at his left thigh + crumbs |
| Open boundary loops (holes) | — | 147; largest 119 verts, 6.5 cm (coat, front of the belt) | 146; largest 72 verts, 5.5 cm (coat, the belt line) | 128; largest 69 verts, 2.7 cm (collar) |
| Non-manifold edges | — | **10,167** (5,712 waist/coat) | **6,589** (1,831 waist/coat, 1,577 hem) | 7,451 (2,202 waist/coat) |

The silhouette IoU hardly separates the seeds (0.825-0.856), as for Brax and Valdris: TRELLIS.2 is conditioned on
that exact front. All three flare the coat wider than the concept below the belt (1.3-1.4 m against 1.2 m): the
orthographic render sees the tatter points spread in depth as well. The pick comes from the hands, the coat and the
views the concept does not show.

## 5. Pick: s202

- **The hands are right.** The gloved right fist with skin fingers and the ghost left fist, both closed and clean,
  with no gun left in them. s101 swaps the two hand textures; s303 gloves the ghost hand and keeps a grip tunnel
  through the right fist. The ghost arm is his identity (brief pillar 2) and the fists are what the weapon sockets
  are built on.
- **The coat the brief asks for.** A tall collar with clean points, one solid violet-navy back panel torn into long
  points at the hem, hanging clear of the legs (33 % cut and thigh cuts). s101's back is shaggy with red streaks;
  s303 grows a hood and bakes the back teal.
- **The cleanest surface.** One main shell, no loose slab (s101 has a 1,804-vert coat slab, s303 a 4,102-vert
  floating pouch), no hole above 5.5 cm and the fewest non-manifold edges (6,589 against 10,167 and 7,451).
- **The proportions.** Span/height 0.999 (concept 0.979), the arm line 2.09 m (concept 2.06 m), the collar, the
  bandolier, the belts, the holster and the boots where the concept has them.

What it gives up: the face. s202 bakes the face glow as a pale patch; the face is 1-2 px in gameplay, and for the
stage-2 head and portraits use the concept first and **s303's head** (the sharpest brow, smirk and beard) as the
secondary 3D reference.

## 6. Known defects of s202 (the other seeds share most of them)

Shape:
1. **The coat is one thick fibrous volume** fused to the torso's back and shoulders; the tatters are thick slabs and
   flare to 1.31-1.37 m (concept ≤ 1.21 m). Stage 2 builds the coat as a separate thin cloth part on `x_` chains and
   takes the flare from the concept (brief §3).
2. **No ghost-flame tatters and no glow in the geometry or the emissive.** The smoke was cut from the input on purpose
   (§1); the 4-6 emissive tatters, the ghost-arm emissive, the eye, the face glow and the gem are authored in stage 2.
3. **The face is soft** and the face glow is baked as a pale patch (§5, use s303's head).
4. The ghost fist's knuckles are baked dark with teal glints (a remnant of the cut revolver's glow in the conditioning
   pixels next to the fist); the shape is a clean fist.
5. The fists are closed round an empty grip line (the concept's pose); stage 2 builds open hands with fist-capable
   loops from the MakeHuman topology, as for Brax.
Surface and topology (irrelevant for a retopo reference; listed so nobody tries to ship or rig it):
6. 692k triangles of isotropic remesh with no edge loops; 146 small boundary loops, 6,589 non-manifold edges (most
   in the coat and hem), 66 loose crumbs of ≤ 608 vertices.
7. The texture has baked lighting and the concept's shading. It is not a texture source; stage 2 paints NPR
   textures from `palette.json`.
8. The metal/roughness map is generator output and means nothing for the NPR shader.

## 7. In-game read (55° ortho camera)

At 22 m view height (1 player) the arms-out blockout is **70 px tall and 102 px wide** at 1080p (6.5 % of the screen
height); at 28 m (4 players) it is **55 x 80 px** (5.1 %). From the game's pitch the player sees the collar and the
hair as a dark cap, the tops of the two arms (the ghost arm a pale bar on his left, the gloved arm dark on his
right), the coat's back and shoulders as a dark triangle flaring over the legs, the belt and the boots. The silhouette
is a narrow dark wedge with one light arm, as the brief's readability section predicted: the dark body sinks into the
dark floor and the **ghost arm carries him**. Its emissive (defect 2) and the ink outline are load-bearing; judge it
again on the stage-2 mesh in an idle pose, where the arm is folded in.

## 8. What stage 2 should take from it

Take: the overall proportions (2.1 m, span/height about 1.0), the lean torso and narrow waist, the collar's height and
points, the coat's attachment, length (hem at mid-shin) and its clearance round the legs, the belts, bandolier, holster
and pouch placement, the thigh straps, the boots' shapes and cuffs, the fist size, the head and hair mass. Ignore: the
coat's thickness and its over-wide flare (defect 1: take the flare from the concept), the face (use the concept and
s303), the baked glow patches, the surface noise, the topology and the texture. Where the mesh and the concept
disagree, the concept wins; for the back, the brief's §7 proposal (one violet panel, centre vent, torn hem) stands
until a back sheet is approved.

## 9. Reproduce

```sh
PY=D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe
python tools/comfy/run_trellis.py kael art/characters/kael/references/KAEL_front_approved.png --mask-only --out art/characters/kael/work/maskcheck_raw
$PY tools/comfy/maskcheck_sheet.py Kael art/characters/kael/references/KAEL_front_approved.png \
  art/characters/kael/work/maskcheck_raw/kael_maskcheck_mask.png art/characters/kael/work/maskcheck_raw/kael_maskcheck_crop.png \
  art/characters/kael/reports/blockout/input_maskcheck.png --region "R fist + gun=60,140,420,300" --region "L ghost fist + gun=1120,140,1480,300" \
  --region "head + hair=660,10,860,170" --region "coat R flank + smoke=250,400,640,900" --region "coat L flank + smoke=900,400,1200,900" \
  --region "between legs=640,650,900,900" --region "boots=520,850,960,1010"
python tools/comfy/run_trellis.py kael art/characters/kael/references/kael_concept_front_nogun.png --mask-only --own-mask --out art/characters/kael/work/maskcheck_own
$PY tools/blender/gf_hero/kael_stage1_input.py --sheet      # needs work/maskcheck_raw (the edit) and work/maskcheck_own (the sheet's crop)
python -u tools/comfy/run_trellis.py kael art/characters/kael/references/kael_concept_front_nogun.png --own-mask --seed 101 --seed 202 --seed 303
B="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
for s in 101 202 303; do
  stem=kael_trellis2_s$s; glb=art/characters/kael/source/$stem.glb; out=art/characters/kael/work/renders/$stem
  "$B" -b -P tools/blender/gf_hero/kael_render_blockout.py -- $glb $out $stem --height 2.1
  "$B" -b -P tools/blender/gf_hero/kael_render_blockout_parts.py -- $glb $out $stem art/characters/kael/blockout_views.json --height 2.1
done
$PY tools/comfy/blockout_sheets.py art/characters/kael/work/renders art/characters/kael/reports/blockout \
  art/characters/kael/references/KAEL_front_approved.png art/characters/kael/references/kael_concept_front_nogun_mask.png \
  kael_trellis2_s101 kael_trellis2_s202 kael_trellis2_s303 --views art/characters/kael/blockout_views.json --selected kael_trellis2_s202
python tools/comfy/art_manifest.py kael --selected kael_trellis2_s202.glb
```

The input edit is deterministic (re-running it gives byte-identical PNGs). TRELLIS.2 sampling is seeded, but the int8
kernels and the remesh are not guaranteed bit-exact across driver or ComfyUI versions. Verify a re-run against the
recorded sha256; a mismatch means a new blockout, not the recorded one.

## 10. Tooling added for this run (Kael files only; no shared tool changed)

- `tools/blender/gf_hero/kael_stage1_input.py`: the stage-1 input edit (§1) and its record sheet (`--sheet`).
- `tools/blender/gf_hero/kael_render_blockout.py`, `tools/blender/gf_hero/kael_render_blockout_parts.py`: verbatim
  copies of `tools/blender/gf_hero/render_blockout.py` and `tools/comfy/render_blockout_parts.py` whose lit renders use
  Cycles on the CPU (24 samples, `GF_CYCLES_SAMPLES` overrides) instead of EEVEE; the parts copy also resolves the repo
  root from its own folder. Output names and metrics are unchanged, so `blockout_sheets.py` reads them as it reads
  Brax's and Valdris's.
