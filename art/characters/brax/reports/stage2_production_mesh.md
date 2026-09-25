# Brax — stage 2 production mesh (made by AI, 2026-09-25)

> **Two user decisions of 2026-09-25, relayed by the workflow coordinator.**
> 1. There is no human artist: stage 2 is made by the AI pipeline at production quality. It is not a stand-in.
>    The remaining human gate is the user's own visual approval (`status.json` item `user_visual_approval`).
> 2. Weapons come off the hero bodies. Brax's body has bare forearms and hands; the rock forge-gauntlets are
>    the `anvil_gauntlets` weapon model in [`art/weapons/anvil_gauntlets/`](../../../weapons/anvil_gauntlets/README.md),
>    attached to `weapon_L` / `weapon_R` hand sockets.
>
> **Polish pass (same day).** The orchestrator reviewed v1 (commit `e294a57`) and judged that at game size the
> stage-1 blockout column still read more like the concept than the production mesh. v2 addresses that:
> - the gauntlets are rebuilt on the blockout's own gauntlet;
> - tangent-space normal maps and AO/cavity are baked from the blockout;
> - the sigil and crack network are bolder;
> - the face grins;
> - the hair and beard are chunkier.
>
> Before/after: [`stage2/stage2_polish_before_after.png`](stage2/stage2_polish_before_after.png) and
> [`../../../weapons/anvil_gauntlets/reports/stage2/stage2_weapon_before_after.png`](../../../weapons/anvil_gauntlets/reports/stage2/stage2_weapon_before_after.png).

Review sheets (all in [`stage2/`](stage2/)):

| Sheet | What |
|---|---|
| [`stage2_vs_concept.png`](stage2/stage2_vs_concept.png) | concept vs stage 2 armed / bare, silhouette overlay + IoU |
| [`stage2_turnaround.png`](stage2/stage2_turnaround.png) | bare body: toon review shading, clay, flat albedo |
| [`stage2_armed.png`](stage2/stage2_armed.png) | with the gauntlets on their sockets |
| [`stage2_ingame.png`](stage2/stage2_ingame.png) | the client camera (orthographic 55°, 22 m / 28 m, true 1080p pixels), bare and armed, stage-1 blockout beside them |
| [`stage2_closeups.png`](stage2/stage2_closeups.png) | head, torso, arm, hand, skirt, legs |
| [`stage2_wireframe.png`](stage2/stage2_wireframe.png) | joint topology on the body alone (shoulder, elbow/forearm, hand, hip, knee, neck, face) and the parts |
| [`stage2_textures.png`](stage2/stage2_textures.png) | base colour, emissive, UV layout |
| [`stage2_polish_before_after.png`](stage2/stage2_polish_before_after.png) | v1 vs v2: concept comparison, armed, in-game |

**Review shading.** The toon review material is a 3-band ramp with a cool shadow band, a rim, the normal map
and the emissive. It approximates `crates/gf_client/src/shaders/toon.wesl`. The client's `ToonMaterial`
(`ExtendedMaterial<StandardMaterial, Toon>`) runs Bevy's PBR lighting first, including the normal map, then
posterises it. The real in-engine look is still to be checked once the hero GLB loads (stage 5).

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/brax_stage2.blend` | `BODY`, `HAIR`, `BEARD` (with the teeth), `BELT`, `SASH`, `SKIRT_CLOTH`, `SKIRT_PLATES`, `WRAPS`; one material `M_brax` (base colour + emissive + normal map); face attribute `gf_zone` (paint zone), vertex attribute `gf_mask` | LFS |
| `textures/brax_basecolor.png`, `textures/brax_emissive.png` | 2048² sRGB each | LFS |
| `textures/brax_normal.png` | 2048² Non-Color tangent-space normal map (OpenGL / +Y: the glTF and Bevy convention) | LFS |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | every hand-set number of the build (landmarks, bands, face targets, grin, part sizes, bake and paint settings) | yes |
| `reports/stage2/*.json` | measured results: fit, parts, UV/texture/bake stats, glTF check | yes |
| `work/brax_retopo_start.blend` | the prepared sculpt reference with the concept behind it: the file a human would retopologise from | local (regenerated) |
| `source/brax_trellis2_s202.glb` | the selected stage-1 blockout: the fit's target and the normal/AO bake source (never shipped) | LFS |

Rebuild everything, weapon included, with `python tools/blender/gf_hero/run_stage2.py brax`. The chain runs:
prepare → base → fit → parts → weapon → texture → weapon_texture → gltf_check → review → sheets.
It takes 5 to 11 minutes on the dev machine; the bakes run on the RTX 4070 through OPTIX and slow down when
ComfyUI shares the GPU.

## 2. Height: 2.2 m

In `crates/gf_client/src/scene.rs` `spawn_rig`, the greybox hero is:
- a capsule body up to 1.70 m;
- a head sphere at 1.82 m of radius `r * 0.62`.

With Brax's `stats.radius` of 0.52 that radius is 0.32 m, so the greybox top is at 2.14 m.

The roster range is 2.0–2.3 m. Brax is the bulky brawler but not the biggest hero; Valdris, the juggernaut
with radius 0.55, should keep the top of the range. So Brax stands **2.2 m**, 3 % over the greybox top. In
T-pose his torso half-width is about 0.29 m, which is about his 0.52 m collision radius with the arms in.
Meltdown's ×1.25 takes him to 2.75 m. The built mesh measures 2.195 m (hair top) with feet on z = 0.

## 3. How it was made

1. **Sculpt reference.** The selected TRELLIS.2 blockout (s202) is scaled to 2.2 m, welded and stripped of
   31 crumbs (755 vertices). Its colour is sampled into `src_col`, which is used only to recognise hair and
   beard.
2. **Base topology: the MakeHuman hm08 base mesh**, released as CC0 in 2020. It is a production human topology:
   all quads, closed, with loops around every joint, the eyes and the mouth. It is loaded through MPFB, which
   is used only as a tool. On top of it:
   - male, maximum muscle, heavy, tall macros;
   - CC0 face targets toward the turnaround sheet's grinning brawler: heavier brow, full square jaw and chin,
     raised cheeks, mouth corners up;
   - T-posed with MPFB's CC0 game_engine weights.

   Two un-subdivide passes keep every second loop in both directions, going from 26.8k to about 7.3k tris.
   The reduction leaves one parity seam, so the clean half is mirrored, which makes the mesh exactly
   symmetric, and triangle pairs are joined back into quads.
3. **Fit.**
   - **Landmark warp:** a thin-plate spline on 37 landmarks sets the proportions (joints, eyes, nose tip,
     ears, skull top and back, chin, heels, toes).
   - **Surface fit:** a smoothed, symmetric fit to the sculpt by body band. TRELLIS output is a thin
     double-walled shell, so each vertex takes the first hit ahead along its normal, or a same-facing hit
     behind; never the nearest point.
   - **Bands:** hair and beard regions keep the skull and jaw 2 cm inside the sculpt; the head and feet use
     near-rigid fits so the face loops and toes keep their shape.
   - **Result:** mean distance to the sculpt 3.4 mm on the free-form bands.
   - **Arms:** the sculpt's forearms are gauntlet rock, so the bare forearms follow a radius profile from
     0.118 m at the biceps to 0.064 m at the wrist, and the hands are ×1.3.
   - **Extra deformation loops:** at the knees (0.555 / 0.600 / 0.648 m), the elbows (|x| 0.565 / 0.600 /
     0.635 m) and the wrists (|x| 0.895 / 0.925 m).
   - **The grin:** the lower lip drops 4.5 mm at the centre, and the mouth corners rise 4 mm and widen 6 %.
4. **Parts** are built procedurally on the sculpt's measured envelope and around the fitted body. All are
   closed meshes:
   - hair and beard shells: the body's own head quads, pushed out to the sculpt with smoothed offsets, so no
     facets;
   - 22 chunky lofted hair clumps swept up and back, and a 7-clump pointed chin tuft;
   - a teeth strip behind the parted lips;
   - the belt with its buckle ring;
   - the teal sash: waist wrap, knot, two front tails with a gold key band, and a back tail (approved sheet);
   - the torn underskirt;
   - 60 rigid leaf plates in three tiers;
   - ankle wraps with instep straps, and short wrist wraps.
5. **UVs** (one 2048² atlas):
   - the body gets region seams (head, torso, arms, hands split into back and palm, legs, feet, soles, ears,
     eyes) plus one shortest-path cut per region;
   - everything else is smart-projected;
   - faces nobody can see (found by a ray along each normal) are packed at 0.3 density.
6. **Bakes (polish pass).** High-to-low from the blockout onto the body skin, selected-to-active, with a
   3 cm cage and a 6 cm ray, on the GPU through OPTIX:
   - a **tangent-space normal map**;
   - the blockout's **cavity** (Laplacian concavity);
   - its **AO**, baked into its vertex colours;
   - its **hit position**.

   Cleaning:
   - A texel whose hit lies more than 1–2.2 cm from the low-poly surface fades to flat. That is where the
     blockout's hair, beard, skirt or gauntlet sits instead of skin.
   - The blockout's forearms and hands (gauntlet rock) are excluded.
   - The normals get a normalised 1.5 px blur inside the valid area and are clamped.

   About 66 % of the skin takes sculpt detail. A self-AO bake of the assembled parts adds the belt over the
   waist, the plates over the cloth and the hair over the scalp.
7. **Textures** are painted in numpy from palette.json. They use flat value planes with no light direction:
   - **form** comes from the normal map through the toon bands (muscle volume, abs, pecs);
   - the cavity and both AOs are folded in as darker painted planes;
   - a painted highlight band on the bronze;
   - skirt plates with dark outlines and gold ridges;
   - hair and beard as value planes (a light top plane, a dark underside, lighter clump tips);
   - heavy painted brows, teeth, a dark mouth interior;
   - criss-cross teal wraps and the gold key band on the sash.

   **Emissive** (a separate map):
   - a bold chest sigil: ring, vertical bar and 8 radiating rays, with white-hot centre lines and a soft halo
     band for bloom;
   - a domain-warped lava crack network, gated into patches:
     - thicker near the sigil;
     - denser on the forearms (his identity when bare-handed);
     - light on the shoulders and back;
   - the deepest chest creases of the sculpt glow;
   - the spine crack with its shoulder-blade branches;
   - the eyes.

## 4. Budget and topology

| Part | Tris | Pieces | Notes |
|---|---|---|---|
| BODY | 7,842 | body + 2 eyeballs | 88 % quads, the rest triangles, no n-gons; symmetric |
| HAIR | 1,132 | 23 | smooth shell + 22 clumps |
| BEARD | 954 | 10 | shell (with the moustache) + 7 chin clumps + teeth |
| BELT | 524 | 3 | belt, buckle ring, boss |
| SASH | 1,076 | 5 | wrap, knot, 3 tails |
| SKIRT_CLOTH | 672 | 1 | torn hem, 8 mm thick |
| SKIRT_PLATES | 1,440 | 60 | rigid leaf plates |
| WRAPS | 1,408 | 6 | 2 ankle sleeves, 2 instep straps, 2 wrist wraps |
| **Body set** | **15,048** | | within the 15–25k budget |
| anvil_gauntlets (weapon) | 7,716 per pair (3,858 each) | 100 per gauntlet | open and fist variants; budget about 8k; see the weapon report |

Checks, all measured by `mesh_stats` in `reports/stage2/texture.json`: 0 boundary edges, 0 non-manifold
edges, 0 loose vertices and 0 degenerate faces on every object; n-gons are triangulated.

The body keeps hm08's deformation loops:
- **Shoulders:** radial loops into the deltoid; see the `shoulder` wireframe.
- **Elbows and wrists:** hm08's rings plus 3 added elbow loops and 2 added wrist loops.
- **Fingers:** about 8 around, with 3 knuckle rings.
- **Hips:** hm08 loops (under the skirt).
- **Knees:** 3 added loops.
- **Neck and face:** eye and mouth loops kept; the mouth is parted for the grin, with a mouth bag and
  teeth behind.

The remaining triangles sit at hm08's poles (nipples, navel, the knuckle webbing, toes, the reduction's
parity seam along the centre line). Rigid parts (plates, buckle, teeth) are separate closed pieces, so
stage 3 can weight each piece 100 % to one bone.

## 5. UVs, texel density, textures

| | Value |
|---|---|
| Atlas | 2048² base colour + 2048² emissive + 2048² normal map, one material `M_brax` |
| Texel density, all faces, median | about 512 px/m (5.1 px/cm); 10th–90th percentile 160–587 px/m |
| Visible faces | 500–560 px/m on every part |
| Hidden faces | inner walls, undersides and caps packed at 0.3 density |
| Atlas coverage | about 52 % of the texels, with a 4 px margin and 12 px dilated gutters |
| Failed islands | none: 0 zero-area UV faces |
| Normal bake | about 469k texels with sculpt detail; 66 % of the skin within the hit-distance mask |
| glTF check | `reports/stage2/gltf_check.json`: `M_brax` exports `baseColorTexture`, `emissiveTexture` (with `KHR_materials_emissive_strength` 3) and `normalTexture`; all 8 primitives carry NORMAL, TANGENT and TEXCOORD_0; nothing in `extensionsRequired` |

Bevy 0.20 support, checked in the cargo registry sources:
- `bevy_pbr-0.20.0-rc.1`: `StandardMaterial::normal_map_texture`, with `flip_normal_map_y` false by default,
  which is the OpenGL convention.
- `bevy_gltf-0.20.0-rc.1` `loader/mod.rs`: maps glTF `normalTexture` onto it, and generates MikkTSpace
  tangents only when TANGENT is missing. The export carries them.

At the in-game camera, 1 m is about 49 px at 1080p. The atlas is sized for the portrait and character-select
close-ups, not for gameplay.

## 6. Review against the concept (honest)

**Silhouette.** The front silhouette IoU against the approved concept is **0.855 armed** (v1: 0.867) and
**0.762 bare**. The stage-1 blockout scored 0.881; it is TRELLIS output conditioned on exactly that
silhouette. v2 lost 0.01 because the rock hand is palm-down with the fingers fanned in plan. The concept's
hands are fanned vertically in the front view; a palm-down T-pose hand is what the rig needs.

**Close-ups and turnarounds (v2).** They now carry the concept's hierarchy:
- a bold glowing sigil with rays over a sparse crack network;
- muscle volume through the toon bands from the normal map (pecs, abs, deltoids, back);
- a grinning face with heavy brows, a full beard with a pointed chin tuft, and chunky swept-back hair;
- the gauntlets as chunky dark basalt with thick glowing seams, hexagonal bronze cuffs, bands and a strap
  frame, and massive knuckles;
- the fist variant closes into a glowing-knuckled block.

**At the in-game camera (the orchestrator's question): does the armed read now beat the blockout column?**
Honestly: **roughly on par, better on identity and worse on skin value.**
- **Better than the blockout:**
  - the chest sigil reads as a bright ring and bar at 22 m and 28 m (the blockout shows none);
  - the fists read as lava-seamed rock with bronze cuffs;
  - the teal sash and the bronze skirt read cleanly.
- **Worse than the blockout:**
  - the skin is lighter and flatter at 1–2 px per muscle; the blockout has baked lighting in its albedo;
  - from 55° above, the gauntlets read orange-patterned more than dark-massed;
  - bare, the arms read as warm bars with a glowing crack sleeve.
- **v1 → v2:** a clear gain in every sheet (before/after).
- **Caveat:** the two columns use different lighting. The blockout column comes from the stage-1 renderer on
  a grey floor, the stage-2 column from the toon review on a Cinder-Wastes floor. The real answer comes from
  the client's own `ToonMaterial` once the GLB is in the game.

**What still falls short of the bar**, for the user's review:
- The face is a fitted MakeHuman face with CC0 targets and a sculpted grin. It is confident, but simpler than
  the sheet's painted close-up. There is no facial rig; the head is rigid on `head`.
- The hair clumps are stylised blocks, not painted strands.
- The skirt plates are pointed leaves (front concept), not the turnaround sheet's rounder scales.
- The skin value at game size, as above: the key lever is the in-game toon ramp and lighting, which this
  review only approximates.
- The T-pose deformation is untested: that is stage 3 (weights, validation poses).

## 7. Acceptance checklist (the spec this build meets)

| # | Check | Result |
|---|---|---|
| 1 | Body set 15–25k tris; weapon pair about 4–8k | 15,048 body set ✔ · weapon 7,716 ✔ |
| 2 | Clean loops at shoulders, elbows, wrists, knees, hips, neck; mostly quads | ✔ hm08 loops kept, 3 knee, 3 elbow and 2 wrist loops added; body 88 % quads |
| 3 | No non-manifold geometry, no holes, no loose parts, no n-gons | ✔ 0 / 0 / 0 on every object, n-gons triangulated |
| 4 | Rigid parts separate where that deforms better | ✔ 60 skirt plates, buckle, eyeballs, teeth; the weapon is fully rigid |
| 5 | Symmetric, T-pose, feet on z = 0, faces −Y, transforms applied | ✔ exact mirror of the body; origin between the feet |
| 6 | One UV set, consistent texel density, no overlaps in visible islands | ✔ about 512 px/m; hidden faces 0.3× |
| 7 | NPR base colour: flat painted planes, palette colours, no baked light direction | ✔ `palette.json` tones; AO and cavity folded in as painted planes (polish brief) |
| 8 | Tangent-space normal map from the sculpt, cleaned, exported in the GLB | ✔ cage + hit-distance mask + normalised blur; `gltf_check.json` ok |
| 9 | Separate emissive map: bold sigil, crack network, eyes | ✔ plus spine crack and forearm cracks |
| 10 | Silhouette matches the concept at game size | ✔ armed IoU 0.855; the in-game read is on par with the blockout (above) |
| 11 | Weapons decision: bare hands, wrist wraps, forearm cracks, socket frame documented | ✔ `hand_frames` in `stage2/body_fit.json` |
| 12 | The user's final visual approval | **pending_human** |

## 8. Open items

- **User approval** of the look (`status.json` → `2_production_mesh.items.user_visual_approval`).
- **In-engine check** with the client's `ToonMaterial` once the hero GLB loads (stage 5). The skin value and
  the gauntlet glow balance at 22–28 m are the things to judge there.
- **Stage 3.**
  - The GF_Hero_v1 rig. MPFB's game_engine rig and weights (CC0) could seed the weights, since the bone names
    match the plan: `calf` / `ball` vs `shin` / `toe`, and `_l` vs `_L`.
  - Add the `weapon_L` / `weapon_R` sockets at the recorded frames.
- **The DINOv3 licence gate** from stage 1 still applies to the sculpt reference's provenance.
