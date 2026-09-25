# Brax — stage 1 blockout report (TRELLIS.2)

> **SCULPT REFERENCE ONLY.** The meshes described here are dense, unrigged TRELLIS.2 output with
> baked lighting in the texture. They stay local in `art/characters/brax/source/` (gitignored), they are never
> copied to `assets/models/`, and they are never shipped. They are the silhouette and proportion reference for the
> human retopo of stage 2 (`docs/ART_PIPELINE.md`).

**Picked seed: `s202`** → `art/characters/brax/source/brax_trellis2_s202.glb`
(62,871,556 bytes, sha256 `071de67e…0b144`, provenance `source/brax_trellis2_s202.json`).

Summary sheet: [`blockout/blockout_selected.png`](blockout/blockout_selected.png) ·
all seeds: [`blockout/blockout_compare.png`](blockout/blockout_compare.png)

Date: 2026-09-25. Tools: `tools/comfy/run_trellis.py`, `tools/blender/gf_hero/render_blockout.py`,
`tools/comfy/blockout_sheets.py` (commands at the end).

## 1. Input

| | |
|---|---|
| Concept | `references/brax_concept_front.png`, byte-identical to the user-approved `docs/media/playable_characters/BRAX.png` (sha256 `407114e7…d08b64`, 1536x1024, T-pose, flat navy `#171E25`) |
| Cut-out | the graph's own birefnet (node 192) + ImageCropToMask (312) on a `#808080` conditioning background. No hand-made cut-out was needed |
| Check | [`blockout/input_maskcheck.png`](blockout/input_maskcheck.png) |

The worry was that birefnet would eat the near-black gauntlets on the dark navy ground. It did not:

- Mask bbox x 188–1347, y 28–995. A colour key against the navy (distance > 18) gives x 187–1347, y 26–995, so
  the full arm span and every fingertip and thumb are inside the mask.
- 3,696 px are foreground in the colour key but outside the mask. They are the 1 px anti-aliased rim (red in the check sheet).
- 16,978 px are inside the mask but would be *dropped* by a colour key: the darkest rock plates, the hair and the
  cloth shadows (blue in the check sheet). A PIL/colour cut-out would have been worse than birefnet, so the raw concept is fed as is.
- The conditioning crop that every seed actually used (`source/*_cond.png`, from ComfyUI's preview node 302) is
  pixel-identical to the mask-only check (max abs diff 0).

## 2. Generation

The user's TRELLIS.2 graph (`tools/comfy/trellis2_character_api.json`, verbatim, sha256 `8471ef6d…bb133c` with LF line endings) was run with
TRELLIS.2 forced (node 316 = True) and the Pixal3D branch pruned. The character settings were kept (DecimateMesh
700,000 faces, 4096 px bake, 2048 px normal bake), because a sculpt reference is judged in close-ups and never
ships. The seeds ran one after another, each one a single job on the shared RTX 4070 Laptop, with no OOM.

| Seed | Node seeds (3/18/23/12) | Prompt id | GPU time | High-poly decode | Output GLB |
|---|---|---|---|---|---|
| s101 | 104 / 119 / 124 / 113 | `00983fd7…` | 283 s | 5.67 M verts / 11.33 M faces | 63.0 MB, `d3163cad…` |
| **s202** | 205 / 220 / 225 / 214 | `7b0ea45d…` | 360 s | 7.22 M / 14.58 M | 62.9 MB, `071de67e…` |
| s303 | 306 / 321 / 326 / 315 | `fced99ea…` | 401 s | 6.29 M / 12.65 M | 66.2 MB, `0ba6741e…` |

All three GLBs have one double-sided material on one mesh (~695k tris), with a 4096² base colour, a 4096² packed occlusion/roughness/metallic map and a 2048² normal map. The GLBs use no glTF extensions. Full
records: `source/brax_trellis2_s<seed>.json`.

## 3. Review renders

Per seed, in `blockout/`: `*_turnaround.png` (lit, clay and unlit albedo, at a common ortho scale, with the hero normalised to
2.2 m), `*_closeups.png` (head, both gauntlets and skirt + legs, lit and clay; the last row shows connected components in colour
and mid-plane sections), `*_ingame.png` (the client camera: orthographic, 55° pitch, yaw 0, FixedVertical 22 m for 1 player
and 28 m for 4 players, at true 1080p pixel size, plus 3x zooms) and `*_silhouette.png` (front silhouette vs the concept mask).
I looked at every sheet. The full-size renders are in `work/renders/` (local only).

## 4. Comparison against the concept

| Criterion | Concept | s101 | **s202** | s303 |
|---|---|---|---|---|
| Gauntlet shape | black-rock slabs split by glowing cracks, a bronze band at the wrist and the elbow, a ring boss on the side, blocky fingers | rock reads as round **bubbly nodules** with bronze pips; the bands are thin | **large faceted rock plates** (closest to the slabs), two chunky bronze bands with ring rivets | faceted plates and a ring boss on top of the band (a nice match), but the fingers are strings of beads |
| Gauntlet mass (vertical thickness, m, at 55/75/95 % of the half-span; concept 0.27/0.16/0.09) | 0.31/0.22/0.11 | 0.31/0.22/0.11 | **0.30/0.20/0.10** | 0.31/0.19/0.14 |
| Fingers | huge, chunky | thin, lumpy | thin, segmented "sausage" fingers with knuckle studs | thin, beaded |
| Head / beard | short dark messy hair, full short beard, heavy brow | beard good; the hair forms a **spiky ring that reads as a laurel crown** | **messy swept hair, full beard, heavy brow: closest** | the same crown-like spiky ring as s101; flatter face |
| Torso V-taper | massive delts/lats, narrow waist | strong | strong, best-defined pecs/abs | strong |
| Chest sigil (ring + line) | glowing | absent | faint orange smear in the albedo | **visible as painted lines** |
| Skirt layers | bronze scale plates over torn brown cloth, teal sash | clear rows, but the sash is **green** | clear rows of bronze plates over tatters, **teal sash** | clear rows; the sash is green-teal |
| Legs / feet | teal ankle wraps, bare feet | wraps teal-ish, feet OK | wraps dark brown/black (wrong colour), feet OK | wraps dark, feet OK |
| Skin tone | warm tan under lava light | dull red-brown | orange, over-saturated with baked glow blotches | terracotta |
| Fused limbs | — | none | none | none |
| Front silhouette IoU vs concept (bbox-normalised) | — | 0.871 | 0.881 | 0.876 |
| Span / height | 1.199 | 1.234 | **1.222** | 1.244 |
| Connected components (welded) | — | **1 main** (+29 crumbs ≤ 0.1 %) | 1 main + **both lower legs as separate shells** (+31 crumbs) | 1 main + **a 16.5k-vertex internal shell inside the chest, upper arms and head** (seen only in the mid-depth section) (+26 crumbs) |
| Open boundary loops (holes) | — | 91 (largest 28 verts; 53 in the skirt, 14 in the hair) | 102 (largest 24 verts; 38 skirt, 20 legs, 19 feet) | 86 (largest 17 verts; 67 skirt) |
| Non-manifold edges | — | 5,643 (3,247 skirt) | 6,793 (3,555 skirt) | 9,916 (8,387 skirt) |

The silhouette IoU and the gauntlet mass hardly separate the seeds (IoU within 0.01, mass within ±5 %). The front
silhouette is what TRELLIS.2 is conditioned on, so all three match it; they differ in the 3D shapes and in the
views the concept does not show. The pick is therefore decided by the close-ups.

## 5. Pick: s202

- **Best gauntlets.** Faceted rock plates and chunky bronze bands are the nearest thing to the concept's slabs. The
  gauntlets are Brax's silhouette pillar, and at 6-8 % of screen height they are the biggest masses on screen.
- **Best head.** The messy hair and full beard do not have the laurel-crown misread that s101 and s303 share.
- **Best colour blocking** for a reference: the teal sash, the bronze skirt plates and the dark gauntlets separate
  cleanly, and the skin is closest in hue to the concept's warm tan, though too saturated.
- **Acceptable topology defects.** The detached lower legs sit under the skirt hem and overlap the thighs, so no
  gap is visible. s303 hides a second, internal surface inside the chest, shoulders and head. It is invisible from
  outside, but surface snapping or a shrink-wrap during retopo can grab it. s101 is the cleanest topologically,
  but its lumpy gauntlets and crown hair are shape problems, and a sculpt reference exists for its shapes.

s101 is the fallback if an artist wants a single watertight surface to shrink-wrap onto.

## 6. Known defects of s202 (all three seeds share most of them)

Shape:
1. **The fingers are too thin and too long**: segmented tubes with round knuckle studs. The concept's rock fists are
   nearly as wide as the forearm. Stage 2 must rebuild the hands chunkier; the concept is the authority, not the mesh.
2. **No lava-crack geometry or glow.** The cracks between the rock plates are shallow grooves. The emissive
   cracks, the chest sigil and the amber eyes exist only faintly (sigil) or not at all (eyes, cracks) in the
   albedo. All emissives must be authored in stage 2 (emissive mask).
3. The bronze bands carry round rivets where the concept has a single ring/gear boss on the outer side of the wrist.
4. The face is soft: no eye definition, the brow and nose are merged into one mass, and the hair is a noisy clump.
   The face is 1-2 px in gameplay, but portraits need a proper sculpt.
5. The lower legs (below ~0.80 m) are separate shells from the rest of the body. No large open loop sits there, so the join is an
   overlap under the skirt hem, not a visible gap. The thighs continue inside the skirt as their own loops up to ~1.05 m
   (checked on horizontal vertex slices), and the pelvis closes at ~1.2 m.
6. The skirt and sash are one thick fused volume with the legs behind them. The sash is not a separate cloth strip,
   and the tatters are thick slabs. Stage 2 builds cloth as separate thin meshes (brief.md: skirt and sash are skin-swappable parts).
7. The pose is the concept's T-pose, with the arms level at 1.76 m (concept 1.77 m). The rig's rest pose is stage 3's decision.

Surface and topology (irrelevant to a retopo reference, listed so nobody tries to ship or rig it):
8. 695k triangles of isotropic remesh with no edge loops. 102 small open boundary loops (largest 24 verts, mostly in
   the skirt tatters, legs and feet), 6,793 non-manifold edges (half in the skirt), and 31 loose crumbs of < 0.1 % of the vertices each.
9. The texture has baked lighting and over-saturated orange skin with bright glow blotches (the concept's lava light
   baked into the albedo). The ankle wraps came out dark brown/black where the concept has teal. It is not a
   texture source; stage 2 paints NPR textures from `palette.json`.
10. The metal/roughness map is generator output and is meaningless for the NPR shader.

## 7. In-game read (55° ortho camera)

At 22 m view height (1 player) the T-posed blockout is about 88 px tall and 130 px wide at 1080p; at 28 m (4 players) it is
about 69 px tall. From the game's pitch the head is small and seen from above; what reads is the two dark gauntlets with their
bronze bands, the warm skin mass of the shoulders and the teal sash. That confirms the brief's silhouette pillars:
the gauntlets carry the identity. Silhouette readability should be judged again on the stage-2 mesh in an idle pose,
because a T-pose makes every hero a wide cross.

## 8. What stage 2 should take from it

Take: overall proportions (2.2 m, span/height 1.22), shoulder and lat mass, the V-taper, the
thigh and calf volumes, skirt length and layering, gauntlet length and forearm plate faceting, and the band placement.
Ignore: the fingers, the face, the surface noise, the topology, the texture, and the fused cloth. Where the mesh
and the concept disagree, the concept (and the pending approved side/back sheets) wins.

## 9. Reproduce

```sh
python tools/comfy/run_trellis.py brax art/characters/brax/references/brax_concept_front.png --mask-only --out art/characters/brax/work/maskcheck_raw
python -u tools/comfy/run_trellis.py brax art/characters/brax/references/brax_concept_front.png --seed 101 --seed 202 --seed 303
for s in 101 202 303; do
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b -P tools/blender/gf_hero/render_blockout.py -- \
    art/characters/brax/source/brax_trellis2_s$s.glb art/characters/brax/work/renders/brax_trellis2_s$s brax_trellis2_s$s
done
D:/Comfy-Desktop/ComfyUI-Installs/ComfyUI/standalone-env/python.exe tools/comfy/blockout_sheets.py \
  art/characters/brax/work/renders art/characters/brax/reports/blockout \
  art/characters/brax/references/brax_concept_front.png art/characters/brax/work/maskcheck_raw/brax_maskcheck_mask.png \
  brax_trellis2_s101 brax_trellis2_s202 brax_trellis2_s303 --selected brax_trellis2_s202
python tools/comfy/art_manifest.py brax --selected brax_trellis2_s202.glb
```

TRELLIS.2 sampling is seeded, but the int8 kernels and remesh are not guaranteed bit-exact across driver or
ComfyUI versions. Verify a re-run against the recorded sha256; a mismatch means a new blockout, not the recorded one.
