# Selene — stage 1 blockout report (TRELLIS.2)

> **SCULPT REFERENCE ONLY.** The meshes described here are dense, unrigged TRELLIS.2 output with baked lighting in
> the texture. They are never copied to `assets/models/` and never shipped. They are the silhouette and proportion
> reference for the stage-2 production mesh (`docs/ART_PIPELINE.md`). The selected seed's GLB is committed through
> Git LFS so a fresh clone has it; the other seeds stay local.

**Picked seed: `s303`** → `art/characters/selene/source/selene_trellis2_s303.glb`
(64,280,388 bytes, sha256 `3c7c70f8…5454d`, Git LFS, provenance `source/selene_trellis2_s303.json`).

Summary sheet: [`blockout/blockout_selected.png`](blockout/blockout_selected.png) ·
all seeds: [`blockout/blockout_compare.png`](blockout/blockout_compare.png) ·
input check: [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png)

Date: 2026-09-27. Tools: `tools/comfy/run_trellis.py`, `tools/comfy/maskcheck_sheet.py`,
`art/characters/selene/stage1_input.py`, `tools/blender/gf_hero/render_blockout.py` and
`tools/comfy/render_blockout_parts.py` (both run through `tools/blender/gf_hero/selene_blockout_render.py`, Cycles CPU),
`tools/comfy/blockout_sheets.py`, `tools/comfy/art_manifest.py` (commands in §9). Views, parts and body regions:
[`../blockout_views.json`](../blockout_views.json).

## 1. Input check

The approved front (`references/SELENE_front_approved.png`, 1536x1024, sha256 `a75de828…f6e0`) is a T-pose on a flat
dark navy ground (RGB ~22,32,43) that sits within a few L\* of her black bodysuit, leggings and sabatons: exactly where
birefnet can lose an edge. `run_trellis.py --mask-only` ran the graph's own birefnet (node 192) and crop (312), and
`maskcheck_sheet.py` compared the mask with an independent colour key over a fitted background (residual mean 0.7,
p99 2.3 RGB levels; threshold 12):

- mask bbox x 224–1304, y 24–987; the key's bbox x 223–1305, y 23–989: **nothing is lost**. Of 9,460 key-only pixels,
  156 lie more than 3 px outside the mask and none more than 9 px (the anti-aliased rim).
- Per region, key-only pixels / more than 3 px out: crown shards 1,171 / 51 (the shards' glow halo), right hand and claws
  366 / **0**, sabatons 307 / 4, cape tatters 419 / **0**. The fingertips, the claws, the ragged hems, all six shards
  and the pointed sabatons are kept.
- 18,324 px inside the mask would be dropped by the colour key (the black suit, the sabatons: correct to keep), **but
  around the head** birefnet also keeps the dark navy ground between the hair, the lightning wisps and the shards.

## 2. The first run, and the cleaned input

A first TRELLIS.2 run on the plain concept (seed 101, 331 s; kept local in `work/first_input/`) showed two problems
that no seed would fix:

1. **The coils.** The two floating coil devices (weapon / VFX, not body) came out as barrels about 1 m long in depth,
   crossing in front of the hips and the capes in every side and 3/4 view (bounds 2.13 x **1.79** x 2.20 m, 58
   components). They would pollute the stage-2 surface fit and the normal bake.
2. **The head.** The kept ground around the head and the six shards fused into a second, larger hair mass behind and
   above the head: no shards, a double bun.

So the stage-1 input is the front with a **verified alpha** (`art/characters/selene/stage1_input.py`, fed with
`--own-mask`; the RGB is the approved front byte for byte): the coils are cut, and in the head box only what the colour
key calls figure is kept (grown 2 px, holes under 150 px filled; 894 px of ground removed). The alpha has 9 components:
the body (266,279 px), the six shards (165–401 px each) and two wisps. Input sha256 `f8ee0514…ff25`.

## 3. Generation

The user's TRELLIS.2 graph (`tools/comfy/trellis2_character_api.json`, unchanged, template sha256 `8471ef6d…`) with
TRELLIS.2 forced (node 316 = True), the Pixal3D branch pruned, the character settings kept (700,000 faces, 4096 px
bake, 2048 px normal bake), conditioning background `#808080`, the mask from the input's alpha. One job at a time on the
shared GPU (the Kael track's jobs ran in between); no OOM, no retry.

| Seed | Node seeds (3/18/23/12) | Prompt id | GPU time | High-poly decode | Output GLB |
|---|---|---|---|---|---|
| s101 | 104 / 119 / 124 / 113 | `66b07790…` | 293 s | 5.43 M verts / 10.89 M faces | 64.0 MB, `f7f77b5a…` |
| s202 | 205 / 220 / 225 / 214 | `0f4db6d4…` | 291 s | 4.94 M / 9.98 M | 65.8 MB, `c98355b3…` |
| **s303** | 306 / 321 / 326 / 315 | `d5f681e4…` | 308 s | 5.64 M / 11.39 M | 64.3 MB, `3c7c70f8…` |

Full records: `source/selene_trellis2_s<seed>.json`.

## 4. Review renders and comparison

Every seed is normalised to **2.2 m** (feet on z = 0, facing Blender −Y, her right = −X) and rendered by the shared
`render_blockout.py` (turnaround, in-game camera, diagnostics) and `render_blockout_parts.py` with Selene's
`blockout_views.json` (head + bun + crown incl. a top view, the right forearm and claws, collar / bust / belt, the
whole from above and at 55°, the capes from behind and from her right, the legs and a cut at knee height). The lit views
are **Cycles on the CPU** (24 samples, denoised) through `selene_blockout_render.py`, never EEVEE: the GPU is shared.
Sheets per seed in `blockout/`: `*_turnaround.png`, `*_closeups.png`, `*_closeups2.png`, `*_ingame.png`,
`*_silhouette.png`.

| Criterion | Concept | s101 | s202 | **s303** |
|---|---|---|---|---|
| Face | slim, cold, pale skin, glowing ice-blue eyes | broad masculine jaw, warm skin | tanned face | **slim female face, pale skin, pale eyes: the concept's** |
| Hair | silver-white, high bun | blue-grey | grey-blue with a white forelock | **silver-white** |
| Bun | on top of the head | a separate mass ~0.2 m behind the head + a hair tail down the back (all seeds) | same | same (its own 11,787-vertex component) |
| Crown shards (six, floating) | a ring around the head | thin tendrils + side prongs | horn-like side prongs | side prongs fused to the hair |
| Cloth colour | deep storm blue → pale storm-cloud | **teal-cyan** (against the brief's P2 rule) | **teal-cyan** | **deep storm blue**, as painted |
| Hands | fingerless gauntlet, ice-blue claws | claws, thin fingers | claws, spread fingers | **five clean fingers with claws, gauntlet cuff** |
| Legs vs cloth (knee cut) | legs together, panels and tabard free | separate | the two legs fused into one section | **two legs, tabard in front, panels free** |
| Span / height (concept 0.932) | 2.05 m | 0.992 (2.18 m) | 0.985 (2.17 m) | **0.961 (2.11 m)** |
| Depth | — | 0.76 m | 0.61 m | 0.71 m |
| Front silhouette IoU vs the concept (coils masked out) | — | 0.704 | **0.758** | 0.734 |
| Components (welded) | — | 29: main 257,933 + hair tail 39,621 + cloth pieces | **12: main 324,139** + one hip panel + 10 crumbs ≤ 159 verts | 22: main 265,071 + hip panels (11-13k each) + bun/tail |
| Open boundary loops (largest) | — | 87 (41 verts, 2.2 cm) | 61 (**204 verts, 0.12 m, at the back under the panels**) | 65 (33 verts, 1.6 cm) |
| Non-manifold edges | — | 6,289 | 5,031 | 5,682 |
| In-game height at 22 m / 28 m | — | 93 / 73 px | 86 / 68 px | 91 / 71 px |

The IoU is lower than Brax's and Valdris's (0.70-0.76 against 0.84-0.88): the ragged cloth is thin, so a small offset of a
hem costs a large share of its area (red and green bands along the capes in `*_silhouette.png`), and the orthographic
render flares the hems a little wider than the concept. It barely ranks the seeds; the pick comes from the close-ups.

## 5. Pick: s303

- **The head the concept draws.** The only slim female face with pale skin and pale eyes, and the only silver-white
  hair. It is the best 3D reference for the stage-2 face fit and the hair shell.
- **The concept's palette.** Deep storm blue cloth fading to pale edges; s101 and s202 turned the cloth teal-cyan,
  the colour the brief keeps off large areas (P2 ring `#3FD8FF`).
- **Clean hands and legs.** Five separate clawed fingers with a gauntlet cuff; at the knee two legs with the tabard in
  front and the hip panels free, which is what the cloth chains need.
- **The closest proportions** (span/height 0.961 against the concept's 0.932) and no hole larger than 1.6 cm.

What it gives up: s202 has the cleanest topology (one main shell, 12 components). That matters little for a retopo
reference whose cloth stage 2 rebuilds anyway, and s202's one real opening (0.12 m at the back) is worse than s303's
pin-holes.

## 6. Known defects of s303 (the other seeds share most of them)

Shape:
1. **The bun sits behind the head**, a separate mass about 0.2 m back with a hair tail down to the shoulder blades (all
   three seeds: TRELLIS read the bun drawn above the head as a mass behind it). Stage 2 builds the high bun on the
   skull, as the concept draws it.
2. **No floating crown shards.** They are fused into the hair as horn-like side prongs. Stage 2 models six rigid
   shards from the concept (brief §7.2 Q1) on `x_crown_*` bones.
3. **The cloth is thick and partly fused**: the outer capes are joined to the shoulders, the hip panels are separate
   shells, the tabard is fused to the legs at the top. Stage 2 builds thin cloth parts on bone chains.
4. **No emissive**: the veins, the gem, the eyes and the greave glows exist only faintly in the albedo. All glows are
   authored in stage 2.
5. The shoulder bows and the gold filigree are soft lumps; take their shapes from the concept.

Surface and topology (irrelevant for a retopo reference; listed so nobody tries to ship or rig it):
6. 694k triangles of isotropic remesh, no edge loops; 65 pin-hole boundary loops, 5,682 non-manifold edges (63 % in the
   cloth), 14 components under 1 % of the vertices.
7. The texture has baked lighting and is not a texture source; stage 2 paints NPR textures from `palette.json`.

## 7. In-game read (55° ortho camera)

At 22 m view height (1 player) the T-pose blockout is **91 px tall** at 1080p (8.4 % of the screen height); at 28 m
(4 players) 71 px (6.6 %). From the game's pitch the player sees the silver head as the brightest point, the pale arm
line, the dark vertical core and the blue cloth fan opening below the arms; the gold trim at the shoulders and hips
reads as a few bright pixels. That is the brief's pillar order (§2). The T-pose fan is wider than any gameplay pose;
judge readability again on the stage-2 mesh in an idle pose.

## 8. What stage 2 should take from it

Take: the body proportions (2.2 m, long legs, slim waist, the bust and collar volume), the collar and gem position,
the hip plates and belt rings, the greave and pointed sabaton shapes, the hands, and the cloth's attachment points,
lengths and flare (capes from the shoulders, hip panels, tabard between the legs). Ignore: the bun position and the hair
tail (defect 1), the crown (defect 2), the fused thick cloth (defect 3), the surface noise, the topology and the texture.
Where the mesh and the concept disagree, the concept wins.

## 9. Reproduce

```sh
PY=D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe
B="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
python tools/comfy/run_trellis.py selene art/characters/selene/references/SELENE_front_approved.png --mask-only --out art/characters/selene/work/maskcheck_raw
cp art/characters/selene/work/maskcheck_raw/selene_maskcheck_mask.png art/characters/selene/references/selene_concept_front_mask.png
$PY tools/comfy/maskcheck_sheet.py Selene art/characters/selene/references/SELENE_front_approved.png \
  art/characters/selene/work/maskcheck_raw/selene_maskcheck_mask.png art/characters/selene/work/maskcheck_raw/selene_maskcheck_crop.png \
  art/characters/selene/reports/blockout/input_maskcheck.png --region "crown shards=650,10,880,200" \
  --region "right hand + claws=315,200,520,275" --region "sabatons=690,820,850,1000" --region "cape tatters=290,560,560,800"
$PY art/characters/selene/stage1_input.py
python -u tools/comfy/run_trellis.py selene art/characters/selene/references/selene_concept_front_input.png --own-mask --seed 101 --seed 202 --seed 303
for s in 101 202 303; do
  stem=selene_trellis2_s$s; glb=art/characters/selene/source/$stem.glb; out=art/characters/selene/work/renders/$stem
  "$B" -b -P tools/blender/gf_hero/selene_blockout_render.py -- tools/blender/gf_hero/render_blockout.py $glb $out $stem --height 2.2
  "$B" -b -P tools/blender/gf_hero/selene_blockout_render.py -- tools/comfy/render_blockout_parts.py $glb $out $stem art/characters/selene/blockout_views.json --height 2.2
done
$PY tools/comfy/blockout_sheets.py art/characters/selene/work/renders art/characters/selene/reports/blockout \
  art/characters/selene/references/SELENE_front_approved.png art/characters/selene/references/selene_concept_front_mask_nocoils.png \
  selene_trellis2_s101 selene_trellis2_s202 selene_trellis2_s303 --views art/characters/selene/blockout_views.json --selected selene_trellis2_s303
python tools/comfy/art_manifest.py selene --selected selene_trellis2_s303.glb
```

TRELLIS.2 sampling is seeded, but the int8 kernels and the remesh are not guaranteed bit-exact across driver or ComfyUI
versions. Verify a re-run against the recorded sha256; a mismatch means a new blockout, not the recorded one.

## 10. Tooling added for this run (Selene files only; no shared script changed)

- `art/characters/selene/stage1_input.py`: the verified-alpha input (§2).
- `tools/blender/gf_hero/selene_blockout_render.py`: runs the shared `render_blockout.py` / `render_blockout_parts.py`
  with their one EEVEE line swapped for Cycles on the CPU (low samples, denoised), everything else unchanged. Another
  hero can use it as it is.
- `art/characters/selene/blockout_views.json`: her close-up parts, views and body regions.
