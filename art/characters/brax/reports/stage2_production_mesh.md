# Brax — stage 2 production mesh (made by AI, 2026-09-25)

> **Two user decisions of 2026-09-25, relayed by the workflow coordinator.**
> 1. There is no human artist: stage 2 is made by the AI pipeline at production quality. It is not a stand-in.
>    The remaining human gate is the user's own visual approval (`status.json` item `user_visual_approval`).
> 2. Weapons come off the hero bodies. Brax's body has bare forearms and hands; the rock forge-gauntlets are
>    the `anvil_gauntlets` weapon model in [`art/weapons/anvil_gauntlets/`](../../../weapons/anvil_gauntlets/README.md),
>    attached to `weapon_L` / `weapon_R` hand sockets.

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

The toon review shading is a 3-band ramp with a cool shadow band, a rim and the emissive. It approximates
`crates/gf_client/src/shaders/toon.wesl`, which is written but not yet wired in the client, so the look in the
actual Bevy renderer is still to be checked (open issues).

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/brax_stage2.blend` | `BODY`, `HAIR`, `BEARD`, `BELT`, `SASH`, `SKIRT_CLOTH`, `SKIRT_PLATES`, `WRAPS`, one material `M_brax`, face attribute `gf_zone` (paint zone), vertex attribute `gf_mask` | LFS |
| `textures/brax_basecolor.png`, `textures/brax_emissive.png` | 2048² sRGB each | LFS |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | every hand-set number of the build (landmarks, bands, part sizes, paint settings) | yes |
| `reports/stage2/*.json` | measured results: fit, parts, UV/texture stats | yes |
| `work/brax_retopo_start.blend` | the prepared sculpt reference with the concept behind it: the file a human would retopologise from | local (regenerated) |
| `source/brax_trellis2_s202.glb` | the selected stage-1 blockout, the fit's target | LFS |

Rebuild everything, weapon included, with `python tools/blender/gf_hero/run_stage2.py brax`. It takes about
5 minutes and runs prepare → base → fit → parts → weapon → texture → review → sheets.

## 2. Height: 2.2 m

In `crates/gf_client/src/scene.rs` `spawn_rig`, the greybox hero is:
- a capsule body up to 1.70 m;
- a head sphere at 1.82 m of radius `r * 0.62`.

With Brax's `stats.radius` of 0.52 that radius is 0.32 m, so the greybox top is at 2.14 m.

The roster range is 2.0–2.3 m. Brax is the bulky brawler but not the biggest hero; Valdris, the juggernaut
with radius 0.55, should keep the top of the range. So Brax stands **2.2 m**, 3 % over the greybox top. In
T-pose his torso half-width is about 0.29 m, which is about his 0.52 m collision radius with the arms in.
Meltdown's ×1.25 takes him to 2.75 m. The built mesh measures 2.196 m (hair top) with feet on z = 0.

## 3. How it was made

1. **Sculpt reference.** The selected TRELLIS.2 blockout (s202) is scaled to 2.2 m, welded and stripped of
   31 crumbs (755 vertices). Its colour is sampled into `src_col`, which is used only to recognise hair and
   beard.
2. **Base topology: the MakeHuman hm08 base mesh**, released as CC0 in 2020. It is a production human topology:
   all quads, closed, with loops around every joint, the eyes and the mouth. It is loaded through MPFB, which
   is used only as a tool. On top of it:
   - male, maximum muscle, heavy, tall macros;
   - CC0 face targets for the concept's square jaw, heavy brow and strong nose;
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
   - **Result:** mean distance to the sculpt 3.5 mm on the free-form bands.
   - **Arms:** the sculpt's forearms are gauntlet rock, so the bare forearms follow a radius profile from
     0.118 m at the biceps to 0.064 m at the wrist, and the hands are ×1.3.
   - **Knees:** three extra loops, at the knee and 5 cm to each side.
4. **Parts** are built procedurally on the sculpt's measured envelope and around the fitted body. All are
   closed meshes:
   - hair and beard shells (the body's own head quads, pushed out to the sculpt, with rims and spiky clumps);
   - the belt with its buckle ring;
   - the teal sash: waist wrap, knot, two front tails with a gold key band, and a back tail (approved sheet);
   - the torn underskirt;
   - 60 rigid leaf plates in three tiers;
   - ankle wraps with instep straps, and short wrist wraps.

   The hairline and beard line are angle tables around the head (`stage2_parts.json`).
5. **UVs** (one 2048² atlas):
   - the body gets region seams (head, torso, arms, hands split into back and palm, legs, feet, soles, ears,
     eyes) plus one shortest-path cut per region: back of the head, back of the torso, under the arms,
     inside the legs, back of the heels;
   - shells split into their outer surface and inner wall;
   - hard surface is smart-projected;
   - faces nobody can see (found by a ray along each normal) are packed at 0.3 density.
6. **Textures** are painted in numpy from baked position, normal, zone, object and mask maps. They are flat
   value planes from `palette.json` with no light direction and no ambient occlusion:
   - dark ink lines in the sculpt's deepest creases (abs, pecs), limited to where the body follows the sculpt;
   - a painted highlight band on the bronze;
   - dark outlines and a gold ridge on each skirt plate;
   - criss-cross teal wraps over linen;
   - painted heavy brows;
   - the gold key band on the sash tails.

   **Emissive** (a separate map):
   - the chest sigil (ring, vertical line and 6 rays), with veins spreading over the chest and shoulders;
   - the spine crack with its shoulder-blade branches (approved sheet);
   - lava cracks from the elbows down the forearms to the backs of the hands;
   - the eyes.

## 4. Budget and topology

| Part | Tris | Pieces | Notes |
|---|---|---|---|
| BODY | 7,642 | body + 2 eyeballs | 88 % quads, the rest triangles, no n-gons; symmetric |
| HAIR | 496 | 1 | shell + 14 spiky clumps |
| BEARD | 720 | 2 | shell (the moustache is part of it) |
| BELT | 524 | 3 | belt, buckle ring, boss |
| SASH | 1,076 | 5 | wrap, knot, 3 tails |
| SKIRT_CLOTH | 672 | 1 | torn hem, 8 mm thick |
| SKIRT_PLATES | 1,440 | 60 | rigid leaf plates |
| WRAPS | 1,408 | 6 | 2 ankle sleeves, 2 instep straps, 2 wrist wraps |
| **Body set** | **13,978** | | the budget is 15–25k: about 1k under the floor, kept as headroom (§7) |
| anvil_gauntlets (weapon) | 5,728 per pair | 70 per gauntlet | open and fist variants; budget 4–8k; see the weapon report |

Checks, all measured by `mesh_stats` in `reports/stage2/texture.json`: 0 boundary edges, 0 non-manifold
edges, 0 loose vertices and 0 degenerate faces on every object.

The body keeps hm08's deformation loops:
- **Shoulders:** radial loops into the deltoid; see the `shoulder` wireframe.
- **Elbows:** rings every 3–4 cm through the elbow.
- **Wrists:** a ring at the wrist line; each finger has about 8 around and 3 knuckle rings.
- **Hips:** hm08 loops (under the skirt).
- **Knees:** 3 added loops at 0.555 / 0.600 / 0.648 m.
- **Neck and face:** eye and mouth loops kept.

The remaining triangles sit at hm08's poles (nipples, navel, the knuckle webbing, toes, the reduction's
parity seam along the centre line). Rigid parts (plates, buckle) are separate closed pieces, so stage 3 can
weight each piece 100 % to one bone.

## 5. UVs and texel density

| | Value |
|---|---|
| Atlas | 2048² base colour + 2048² emissive, one material `M_brax` |
| Texel density, all faces, median | about 520 px/m (5.2 px/cm); 10th–90th percentile 157–594 px/m |
| Visible faces | 500–560 px/m on every part |
| Hidden faces | inner walls, undersides and caps packed at 0.3 density |
| Atlas coverage | about 52 % of the texels, with a 4 px margin and 12 px dilated gutters |
| Failed islands | none: 0 zero-area UV faces |

Blender still logs "unwrap failed to solve 1 of 21 islands"; the zero-area check finds no affected face.

At the in-game camera, 1 m is about 49 px at 1080p. The atlas is sized for the portrait and character-select
close-ups, not for gameplay.

## 6. Review against the concept (honest)

**Silhouette.** The front silhouette IoU against the approved concept is **0.867 armed** (with the gauntlets,
as the concept shows him) and **0.766 bare**. The stage-1 blockout scored 0.881; it is TRELLIS output
conditioned on exactly that silhouette.

**What matches:**
- the V-taper torso, massive arms and heavy legs;
- the short thick neck and the beard;
- the glowing amber eyes and the chest sigil (ring and line) with veins;
- the teal waist sash with a long front tail, the gold key band, and a back tail (per the sheet);
- the three-tier bronze scale skirt over a torn dark hem;
- criss-cross teal wraps and bare feet;
- the spine crack with shoulder-blade branches (per the sheet).

Armed, the dark basalt gauntlets with glowing grooves and the hexagonal bronze cuff, band and strap frame
are the biggest, darkest masses, as brief pillar 1 asks.

**At the in-game camera:**
- **Armed:** reads like the concept — two dark fists with orange grooves, bronze cuffs, a teal centre stripe
  and the sigil dot.
- **Bare:** loses the dark-fist read. The arms become warm skin-coloured bars; identity rests on the teal,
  the sigil and the lava forearm cracks. That is inherent to the weapons decision; the default chassis
  restores the look.

**What falls short of the bar**, for the user's review:
- The face is a fitted MakeHuman face with CC0 brow and jaw targets. It is stern and heroic but generic next
  to the sheet's grinning close-up. There is no expression and no facial rig; the head is rigid on `head`.
- The hair and beard are faceted low-poly shells with extruded clumps. They read at game scale and in the
  3/4 close-up, but they are stylised blocks, not the sheet's painted strands.
- The skirt plates are pointed leaves with painted gold ridges. The turnaround sheet's plates are rounder,
  fish-scale shapes. The front concept has the pointed ones, which is what was built.
- There are no normal maps. Muscle definition is painted line work from the sculpt's creases and reads
  weaker than the concept's painted anatomy.
- The toon look is a review approximation, not the game's shader.
- The T-pose deformation is untested: that is stage 3 (weights, validation poses).

## 7. Acceptance checklist (the spec this build meets)

| # | Check | Result |
|---|---|---|
| 1 | Body set 15–25k tris; weapon pair 4–8k | 13,978 body set (**under the 15k floor by 1k**: detail was not padded; the budget allows adding density to face/hands later) · weapon 5,728 ✔ |
| 2 | Clean loops at shoulders, elbows, wrists, knees, hips, neck; mostly quads | ✔ hm08 loops kept, 3 knee loops added; body 88 % quads |
| 3 | No non-manifold geometry, no holes, no loose parts, no n-gons | ✔ 0 / 0 / 0 on every object, n-gons triangulated |
| 4 | Rigid parts separate where that deforms better | ✔ 60 skirt plates, buckle, eyeballs; the weapon is fully rigid |
| 5 | Symmetric, T-pose, feet on z = 0, faces −Y, transforms applied | ✔ exact mirror of the body; origin between the feet |
| 6 | One UV set, consistent texel density, no overlaps in visible islands | ✔ about 520 px/m; hidden faces 0.3× |
| 7 | NPR base colour: flat painted planes, palette colours, no baked lighting | ✔ `palette.json` tones; no AO, no light direction |
| 8 | Separate emissive map for lava cracks, sigil, eyes | ✔ plus spine crack and forearm cracks |
| 9 | Silhouette matches the concept at game size | ✔ armed IoU 0.867; the in-game sheet reads |
| 10 | Weapons decision: bare hands, wrist wraps, forearm cracks, socket frame documented | ✔ `hand_frames` in `stage2/body_fit.json` |
| 11 | The user's final visual approval | **pending_human** |

## 8. Open items

- **User approval** of the look (`status.json` → `2_production_mesh.items.user_visual_approval`).
- **In-engine check** once the client loads glTF and wires `toon.wesl` (stage 5).
- **Stage 3.**
  - The GF_Hero_v1 rig. MPFB's game_engine rig and weights (CC0) could seed the weights, since the bone names
    match the plan: `calf` / `ball` vs `shin` / `toe`, and `_l` vs `_L`.
  - Add the `weapon_L` / `weapon_R` sockets at the recorded frames.
- **Budget headroom** (about 1k to the 15k floor): face density for portraits, or a fourth plate tier, if the
  approval asks for it.
- **The DINOv3 licence gate** from stage 1 still applies to the sculpt reference's provenance.
