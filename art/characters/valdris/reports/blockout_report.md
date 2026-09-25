# Valdris — stage 1 blockout report (TRELLIS.2)

> **SCULPT REFERENCE ONLY.** The meshes described here are dense, unrigged TRELLIS.2 output with
> baked lighting in the texture. They are never copied to `assets/models/` and never shipped. They are the
> silhouette and proportion reference for the stage-2 production mesh (`docs/ART_PIPELINE.md`). The selected
> seed's GLB is committed through Git LFS so a fresh clone has it; the other seeds stay local.

**Picked seed: `s202`** → `art/characters/valdris/source/valdris_trellis2_s202.glb`
(80,625,416 bytes, sha256 `98900f1c…60792`, Git LFS, provenance `source/valdris_trellis2_s202.json`).

Summary sheet: [`blockout/blockout_selected.png`](blockout/blockout_selected.png) ·
all seeds: [`blockout/blockout_compare.png`](blockout/blockout_compare.png) ·
input check: [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png)

Date: 2026-09-25. Tools: `tools/comfy/run_trellis.py`, `tools/comfy/maskcheck_sheet.py`,
`tools/blender/gf_hero/render_blockout.py`, `tools/comfy/render_blockout_parts.py`, `tools/comfy/blockout_sheets.py`,
`tools/comfy/art_manifest.py` (commands at the end). The views, parts and body regions are in
[`../blockout_views.json`](../blockout_views.json).

## 1. Input

| | |
|---|---|
| Concept | `references/valdris_concept_front_mirrored.png`: the user's approved hero front `VALDRIS.jpg` (784x1168, sha256 `55d018f3…2dfd`) **mirrored left-right**, lossless (sha256 `62fc6eed…146d`) |
| Why mirrored | the two approved concepts disagree; the orchestrator default puts the cannon on his RIGHT arm (the turnaround sheet, the labelled blockout reference) and keeps the anvil chest plate (the hero front). Mirroring the hero front gives both. What else the mirror flips is listed in `status.json` `decisions[cannon_side_and_anvil_plate]`; the user may override |
| Cut-out | the graph's own birefnet (node 192) + ImageCropToMask (312) on a `#808080` conditioning background. No hand-made cut-out was needed |
| Check | [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png), made by `tools/comfy/maskcheck_sheet.py` |

The worry was dark gunmetal on a near-black vignette (RGB 11 in the corners to about 25 behind him): exactly where
birefnet can lose the pauldron edges, the cape tatters and the fist. It did not. The check compares the mask with an
independent colour key over a fitted background model (a 4th-order polynomial per channel, fitted to the pixels
more than 25 px outside the mask; residual mean 0.9, p99 5.3 RGB levels; key threshold 12):

- Mask bbox x 4–771, y 190–1009; the colour key's bbox is x 0–772, y 189–1013. The extra key pixels are the
  muzzle's glow halo at the left edge and the floor shadow under the boots.
- Per region, pixels the key calls "hero" but the mask drops, and how many lie more than 3 px outside the mask:
  right pauldron 229 / **0**, left pauldron 398 / **5**, fist 342 / **5**, right cape tatters 373 / **0**, left cape
  tatters 736 / **28**, between the legs 269 / **0**. The rest are the 1-2 px anti-aliased rim. The cannon muzzle
  (156 beyond 3 px) and the boots (7,054) differ only by the glow halo and the floor shadow, which must stay out.
- 17,014 px inside the mask would be *dropped* by the colour key (blue in the sheet): the darkest plate faces and
  the cape shadows. A colour-key cut-out would be worse than birefnet, so the mirrored concept is fed as is.
- The conditioning crop that every seed used (`source/*_cond.png`, ComfyUI preview node 302) and its mask are
  pixel-identical to the mask-only check (max abs diff 0).

## 2. Generation

The user's TRELLIS.2 graph (`tools/comfy/trellis2_character_api.json`, unchanged, template sha256 `8471ef6d…bb133c`)
was run with TRELLIS.2 forced (node 316 = True) and the Pixal3D branch pruned. The character settings were kept
(DecimateMesh 700,000 faces, 4096 px bake, 2048 px normal bake), exactly as for Brax. The seeds ran one after
another, one job at a time on the shared RTX 4070 Laptop, with no OOM and no retry.

| Seed | Node seeds (3/18/23/12) | Prompt id | GPU time | High-poly decode | Output GLB |
|---|---|---|---|---|---|
| s101 | 104 / 119 / 124 / 113 | `eef79029…` | 2429 s | 22.52 M verts / 45.96 M faces | 84.2 MB, `64acfff8…` |
| **s202** | 205 / 220 / 225 / 214 | `c784d2c8…` | 2621 s | 21.03 M / 41.83 M | 80.6 MB, `98900f1c…` |
| s303 | 306 / 321 / 326 / 315 | `fd571fb4…` | 2630 s | 18.79 M / 38.33 M | 77.9 MB, `3e43aca4…` |

Each seed took 40-44 min against Brax's 5-7 min. Two reasons, both from the ComfyUI log: the high-poly decode is
three times Brax's (a plate-armoured colossus with a full cape fills far more of the voxel grid than a bare-chested
brawler), and the shape sampler ran at 27-31 s/it with the 5 GB TRELLIS.2 model on dynamic VRAM offload, because the
8 GB GPU was shared with a running game build (the GPU drew 34 W of 62 W). Nothing failed.

All three GLBs have one double-sided material on one mesh (690-694k tris), with a 4096² base colour, a 4096²
packed occlusion/roughness/metallic map and a 2048² normal map. They use no glTF extensions. Full records:
`source/valdris_trellis2_s<seed>.json`.

## 3. Review renders

Everything is rendered with the hero normalised to **2.3 m** (the brief's proposed height; feet on z = 0, facing
Blender −Y, his right = −X). Per seed, in `blockout/`:

- `*_turnaround.png`: lit, clay and unlit albedo at a common ortho scale (`render_blockout.py`).
- `*_closeups.png`: head + beard (front, 3/4, side with the pauldron clipped away), the cannon (3/4, along the
  muzzle axis from his right, top) and the fist (front, 3/4, end-on), lit and clay (`render_blockout_parts.py`).
- `*_closeups2.png`: the whole figure from above and at the game's 55° pitch (front and 3/4, large), pauldrons +
  anvil plate, the cape (back, back 3/4, his right side), the legs and cape hem (front, 3/4, back), and three cuts:
  a horizontal cut at knee height (30 % of the height; front at the bottom) and vertical cuts through each thigh.
  The last row shows connected components (grey main; red, blue, green next; yellow tiny) and mid-plane sections.
- `*_ingame.png`: the client camera (orthographic, 55° pitch, yaw 0, 22 m view height for 1 player and 28 m for 4)
  at true 1080p pixel size, with 3x zooms.
- `*_silhouette.png`: the front silhouette against the concept mask.

I looked at every sheet and at the full-size renders (`work/renders/`, local only). The topology numbers below come
from `*_parts_metrics.json` (welded vertices, Valdris's own body regions from `blockout_views.json`).

## 4. Comparison against the concepts

The criteria come from the task and the brief's silhouette pillars (`brief.md` §2-3).

| Criterion | Concept (mirrored front + sheet) | s101 | **s202** | s303 |
|---|---|---|---|---|
| Cannon on his RIGHT arm | yes (mirror) | yes | **yes** | yes; the only seed whose bore is baked bright yellow like the glowing muzzle |
| Anvil chest plate | flat top at the arm line, horn to his left, on the chest | present, horn left, but a **separate floating shell ~0.15 m in front of the chest** (2,659-vertex component, red in the components view) | **present, horn left, mounted on the chest** (one shell with the torso) | present, horn left; its front is joined, but a 1,749-vertex loose inner slab sits behind it and the top view shows a thin gap to the chest |
| Pauldrons (width at 90-95 % height; brief 1.23 m) | huge squared stacks, tips level with the crown, gold trim, glow slits | layered plates, good trim (1.33 m) | **big, clean block planes** (1.29 m); less layering | layered plates, good trim (1.29 m) |
| Head / beard | bald, heavy brow, glowing eyes, 5 braids with rings, head sunk between the pauldrons | sharpest face; braids with gold rings; **scalp baked pale blue** (a bright dot in the game view) | softer, darker face; braids with rings; the head reads as the brief's "small dark knot" | sharp face, reddish skin, dark scalp; braids with rings |
| Cape | deep red, from the shoulders to near the ground, solid body, tatters at the hem | attached; ragged strands top to bottom, holes in the body | **attached; a solid mass at the back with tatters at the hem** | attached; solid, very dark |
| Cape vs legs (knee cut, thigh cuts) | the cape hangs clear behind the legs | legs and cape separate | **legs and cape separate** | legs and cape separate |
| Fused limbs | — | none | none | none |
| Arm direction (top view) | arms out to the sides; the bore and fist drawn in 3/4 | both arms reach ~45° forward | both arms reach ~45° forward | both arms reach ~45° forward |
| Front silhouette IoU vs the concept mask | — | 0.850 | 0.848 | 0.840 |
| Span / height (concept 0.937) | — | 0.921 | **0.935** | 0.931 |
| Arm-line width (70-80 % height) / widest below the arms (the cape) | 2.15 m / 1.65 m | 2.12 / 1.80 m | **2.15** / 1.83 m | 2.14 / 1.87 m |
| Connected components (welded) | — | 18: main + the **floating anvil** + 16 crumbs | **30: one main shell** + 29 crumbs of ≤ 140 verts | 11: main + the **loose anvil slab** + 9 crumbs |
| Open boundary loops (holes) | — | 83; largest **307 verts, 0.24 m, at the crotch under the tabard**, and 170 verts, 0.13 m, at the right cape edge | **63; largest 17 verts (1.1 cm)**; all pin-holes | 30; largest **335 verts, 0.26 m, at the back of the crotch**, two of ~0.18 m at the left hip under the fist arm |
| Non-manifold edges | — | 2,307 (780 waist/cape, 586 torso) | **1,582** (679 waist/cape) | 1,617 (391 head/beard, 320 cannon) |

The silhouette IoU hardly separates the seeds (0.840-0.850): TRELLIS.2 is conditioned on exactly that front, so all
three match it; the lower IoU than Brax's (0.87-0.88) comes mostly from the cape, which flares 10-13 % wider near
the hem in the orthographic render than in the concept's perspective (green at the bottom of `*_silhouette.png`). As for Brax, the pick comes from the close-ups, the cuts
and the views the concept does not show.

## 5. Pick: s202

- **The anvil plate is on his chest.** It is his identity (the "Anvil-Born" pillar) and the centre mark of the
  silhouette. s101 floats it as a separate shell in front of the chest and s303 half-detaches it; a sculpt
  reference that mounts it correctly saves stage 2 from guessing the depth.
- **By far the cleanest surface.** One main shell, no hole larger than 1.1 cm and the fewest non-manifold edges.
  s101 and s303 each have a 0.24-0.26 m opening at the crotch and further large holes; a shrink-wrap or snapping
  pass during retopo would fall into them.
- **The cape the brief asks for.** A solid mass at the back with the tatters at the hem (brief pillar 4: "keep the
  mass solid"), separated from the legs at the knee.
- **The best-matching block proportions.** Span/height 0.935 (concept 0.937), the arm line 2.15 m (concept 2.15 m),
  clean pauldron planes, and a dark head that reads as the brief's
  "small dark knot" at game scale.

What it gives up: the face is softer and darker than s101's and s303's. The face is 1-2 px in gameplay; for the
stage-2 head sculpt and portraits, use the concept first and **s303's head** (sharpest brow, eyes and nose, dark
scalp) as the secondary 3D reference. s303 is also the reference for the **cannon's ring stack and glowing bore**.

## 6. Known defects of s202 (the other seeds share most of them)

Shape:
1. **Both arms reach about 45° forward** (top view), so the cannon's bore faces the camera in the front view and the
   bounding depth is 1.63 m. The concept draws the arms out to the sides with the bore and the fist in 3/4;
   TRELLIS.2 read them as pointing at the viewer. All three seeds do it. It is a pose, not a shape problem: stage 2
   builds the rest pose the rig asks for, with the cannon's axis along the forearm (and the brief notes that in
   gameplay the cannon points forward anyway).
2. **The face is soft**: brow, eyes and nose are one mass, no eye glow. See §5 for the head reference.
3. **No seam glow in the geometry or the emissive.** The glowing seams, the muzzle glow, the eyes and the pauldron
   slits exist only faintly in the albedo (s202's bore is dark). All emissives are authored in stage 2.
4. The pauldrons are big clean blocks with less layering and trim relief than the concept.
5. The anvil is a thick wedge; the concept's waisted anvil body with two feet is only partly there. Take the
   silhouette from the concept (brief §3: 0.79 x 0.45 m).
6. The cape is one thick fibrous volume, fused to the torso's back and shoulders; the tatters are thick slabs. It
   hangs clear of the legs from the thighs down (knee and thigh cuts). Stage 2 builds it as a separate thin mesh
   on bone chains (brief §8).
7. The head follows the hero front (small, sunk between the pauldrons): the pack default for the open question on
   head size (`decisions[head_size]`, brief §7.2 Q1).

Surface and topology (irrelevant for a retopo reference; listed so nobody tries to ship or rig it):
8. 690k triangles of isotropic remesh with no edge loops; 63 pin-hole boundary loops, 1,582 non-manifold edges
   (43 % in the waist/cape), 29 loose crumbs of ≤ 140 vertices.
9. The texture has baked lighting (the concept's forge light and the muzzle glow, mirrored). It is not a texture
   source; stage 2 paints NPR textures from `palette.json` and the approved colour script.
10. The metal/roughness map is generator output and means nothing for the NPR shader.

## 7. In-game read (55° ortho camera)

At 22 m view height (1 player) the arms-out blockout is **90 px tall and 105 px wide** at 1080p (8.3 % of the
screen height); at 28 m (4 players) it is **70 x 82 px** (6.5 %). From the game's pitch the player sees the tops of
the two pauldron blocks, the anvil's flat top as a bar across the chest, the cannon's gold ring stack on his right,
the boots, and a strip of red cape at each side; the head is a small dark knot between the pauldrons. The
silhouette is a wide, flat-topped block, which is the brief's pillar 1. The gold trim carries the shape on the
dark floor; the seams will need their emissive (defect 3) to hold it on the darkest biomes. Judge readability again
on the stage-2 mesh in an idle pose: the arms-out pose is wider than any gameplay pose.

## 8. What stage 2 should take from it

Take: the overall block (2.3 m, span/height 0.935), the pauldron size and placement (tips level with the crown), the
anvil's position on the chest and its flat top at the arm line, the torso and thigh volumes, the short legs and
wide stance, the boot shapes, the cape's attachment, length, flare and its clearance behind the legs, the cannon's
length, diameter and ring spacing, and the fist's size. Ignore: the arm direction (defect 1), the face (use the
concept and s303), the surface noise, the topology, the texture and the fused cloth. Where the mesh and the
concepts disagree, the concepts win (the hero front for the front, the turnaround sheet for the side and the back).

## 9. Reproduce

```sh
python tools/comfy/run_trellis.py valdris art/characters/valdris/references/valdris_concept_front_mirrored.png --mask-only --out art/characters/valdris/work/maskcheck_raw
D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe tools/comfy/maskcheck_sheet.py Valdris \
  art/characters/valdris/references/valdris_concept_front_mirrored.png \
  art/characters/valdris/work/maskcheck_raw/valdris_maskcheck_mask.png art/characters/valdris/work/maskcheck_raw/valdris_maskcheck_crop.png \
  art/characters/valdris/reports/blockout/input_maskcheck.png --original art/characters/valdris/references/VALDRIS_front_approved.jpg \
  --region "R pauldron=120,160,330,330" --region "L pauldron=440,160,650,330" --region "cannon muzzle=0,230,190,400" \
  --region "fist=590,240,784,400" --region "cape R tatters=60,560,260,960" --region "cape L tatters=560,560,760,960" \
  --region "between legs=290,700,500,960" --region "feet + floor=120,860,680,1060"
python -u tools/comfy/run_trellis.py valdris art/characters/valdris/references/valdris_concept_front_mirrored.png --seed 101 --seed 202 --seed 303
B="C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
for s in 101 202 303; do
  stem=valdris_trellis2_s$s; glb=art/characters/valdris/source/$stem.glb; out=art/characters/valdris/work/renders/$stem
  "$B" -b -P tools/blender/gf_hero/render_blockout.py -- $glb $out $stem --height 2.3
  "$B" -b -P tools/comfy/render_blockout_parts.py -- $glb $out $stem art/characters/valdris/blockout_views.json --height 2.3
done
D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe tools/comfy/blockout_sheets.py \
  art/characters/valdris/work/renders art/characters/valdris/reports/blockout \
  art/characters/valdris/references/valdris_concept_front_mirrored.png art/characters/valdris/work/maskcheck_raw/valdris_maskcheck_mask.png \
  valdris_trellis2_s101 valdris_trellis2_s202 valdris_trellis2_s303 \
  --views art/characters/valdris/blockout_views.json --selected valdris_trellis2_s202
python tools/comfy/art_manifest.py valdris --selected valdris_trellis2_s202.glb
```

TRELLIS.2 sampling is seeded, but the int8 kernels and the remesh are not guaranteed bit-exact across driver or
ComfyUI versions. Verify a re-run against the recorded sha256; a mismatch means a new blockout, not the recorded one.

## 10. Tooling added for this run (backwards compatible; Brax's sheets rebuild byte-identical)

- `tools/comfy/render_blockout_parts.py`: a Blender script for per-hero close-ups, cuts and region topology from a
  JSON spec (here `blockout_views.json`), with the same normalisation, lights and naming as `render_blockout.py`,
  whose close-ups are fixed to Brax's parts.
- `tools/comfy/blockout_sheets.py --views <spec>`: the hero name, height, concept crop and label, close-up rows,
  close-up sheet split and summary tiles from the spec. Without `--views` the output is unchanged (verified
  byte-identical on Brax's s202 renders).
- `tools/comfy/maskcheck_sheet.py`: the stage-1 input check as a tool (Brax's check sheet was made by hand).
- `tools/comfy/check_art.py` and `tools/comfy/art_manifest.py`: a file that `.gitattributes` routes through Git LFS
  is exempt from the 20 MB rule (git stores a pointer) and is recorded with `lfs: true`.
