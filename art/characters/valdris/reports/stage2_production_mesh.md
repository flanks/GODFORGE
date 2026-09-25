# Valdris — stage 2 production mesh (made by AI, 2026-09-25)

> **Made by AI, not a stand-in.** The user decided on 2026-09-25 that there is no human artist. The AI pipeline
> makes stage 2 at production quality, and the user gives the final visual approval (`status.json`,
> item `user_visual_approval`, `pending_human`).
>
> **Weapons are separate models (same decision).** The siege cannon is not part of his body. It is the weapon
> track's `colossus_cannon` (`assets/models/weapons/colossus_cannon.glb`, `art/weapons/colossus_cannon/`),
> attached at the recorded right-hand frame with an identity transform. His body has two normal armoured arms
> with plate-gauntlet hands. Both arms use the concept's fist-gauntlet arm as the design, and they are sized so
> that the right forearm fits inside the cannon's sleeve.
>
> **Kept from stage 0:** the anvil chest plate, and the head size from the hero front (a small head sunk between
> the pauldrons). Both are recorded under `decisions` in `status.json`, and the user may still override them.

## Polish pass (2026-09-26)

The workflow orchestrator reviewed the first build (commit `c2d9810`). Its verdict was that the build was clean but
read **weaker than both the concept and the stage-1 blockout column** at game size. This pass rebuilt the parts that
caused that and kept what worked: the under-suit body, the beard, the cape, the UV / bake pipeline and the 15–25k
budget. Before and after, with the same cameras and shading:
[`stage2/stage2_before_after.png`](stage2/stage2_before_after.png).

| Area | Before | After (polished) |
|---|---|---|
| **Arms** | thin bars: vambrace about 15–17 cm across, so it cleared the cannon's 9.8 cm bore | the concept's **massive layered fist arm** on both sides. Two rerebrace lames (r 0.15–0.16), a glowing elbow ring, a couter with a raised gold band and a cop, two vambrace segments (r 0.12–0.126, 24–27 cm across; the second has a raised gold band), and the gold wrist cuff. It is wider than the bore on purpose (§6) |
| **Gauntlets** | MakeHuman fingers with thin lames: a splayed claw | **chunky plate fists**. The glove is at hand scale 1.6, with a thick back plate and a heavy knuckle guard with four gold studs. Each finger gets box-section lames as wide as its share of the hand, so the four fingers close into one plated block |
| **Anvil** | a thin slab that barely showed from the front | a **protruding anvil**, its front 0.65 m in front of the spine line. The flat top face is 0.88 m wide at the arm line and catches the light. The horn points to his left, the body is strongly waisted, and it stands on two feet. It sits over the breastplate, and a lava gasket glows round its waist, so the glowing seams frame it from the front and from 55° |
| **Pauldrons** | flat boxes with gold stripes | **three top lames stepping up** from the front to the upright back plate, which reads as a staircase of lit bevels and dark tops from the 55° camera. Below them: the cap block, the glowing slot, the lower block and the arm lame. The upright plate has a rounded top. Edges are chipped, and gold is **only on edges**: a thin 1.6 cm rim facet on each step and the outer-end chamfers |
| **Legs** | blocks | **segmented legs**: two gold-rimmed cuisse lames, big faceted knee cops with a 12 cm boss and side wings, a glowing lava smile under each knee cop, and greaves with a gold-edged raised shin plate over a lava gasket, ending in huge blocky gold-banded sabatons. The tassets were rebuilt: a jagged end wall had shown as a black notch at the right hip |
| **Plate material** | plasticky black with sparse cracks | **cracked, stone-like gunmetal**. The declared `#2A242E` is pulled 35 % toward the measured plate tone, so it stays that family but loses the lavender cast. On top of it: a rectangular stone-block mosaic, painted value planes per plate and per face orientation, lit block bevels and dark joint cavities. The hard edges are chipped and lighter, using the edge bake with a convexity measured against each mesh's median pointiness. Lava veins run through the block joints with white-hot corners, and **lava joints** glow wherever one plate meets another (a new 3 cm ambient-occlusion bake). Forge gold stays on trims, rivets and bands; gold rims are 2 cm instead of 1.6. The normal map from the blockout is kept |

At game size the armed read now beats the blockout column (§7): a dark mass, gold-framed stepped pauldrons, a
light anvil bar, ember knees, pauldron slots and anvil flanks, the red loincloth, collar and cape flanks, and the
cannon.

New tools (Valdris-only; the shared `gf_hero` scripts are untouched by this pass):
- `s2_valdris_repaint.py` is a look-development aid. It repaints the atlas in about 1 min from a paint cache, which
  `s2_texture.py` writes only when `GF_VALDRIS_PAINT_CACHE` is set. The shipped textures always come from a full
  texture run.
- `s2_valdris_paint.bake_extra` gained the joint AO pass.
- `s2_valdris_review.py` also checks the cannon's **outer skin**.
- `s2_valdris_sheets.py` writes the before / after sheet.

Sections 1–12 below describe the build as it now stands. Where the first build's reasoning still applies, the text
is kept.

Review sheets (all in [`stage2/`](stage2/)):

| Sheet | What |
|---|---|
| [`stage2_before_after.png`](stage2/stage2_before_after.png) | The polish pass: the concept, before / after front and 3/4, six close-up pairs, the in-game camera at 3x and 1:1 beside the stage-1 blockout |
| [`stage2_vs_concept.png`](stage2/stage2_vs_concept.png) | The concept beside stage 2, armed (review pose45 and T-pose) and bare, with silhouette overlays and IoU |
| [`stage2_turnaround.png`](stage2/stage2_turnaround.png) | Without the weapon: toon review shading (6 views), clay (4), flat albedo (2) |
| [`stage2_armed.png`](stage2/stage2_armed.png) | With the colossus_cannon on the right-hand frame: T-pose, pose45, cannon close-ups, **a section through the cannon along its axis** showing the forearm in the sleeve, and the measured fit |
| [`stage2_ingame.png`](stage2/stage2_ingame.png) | The client camera (orthographic 55°, 22 m / 28 m, true 1080p pixels) for bare, armed and armed pose45; toon, toon + P1 rim, silhouette and yaw 35. The stage-1 blockout is beside each row, with 3x zooms |
| [`stage2_closeups.png`](stage2/stage2_closeups.png) | Head (front, 3/4, profile), torso, anvil, pauldron, arm, gauntlet, hips, legs, boot, cape |
| [`stage2_wireframe.png`](stage2/stage2_wireframe.png) | Joint topology on the under-suit body alone (shoulder, elbow, hand, hip, knee, neck, face), and the parts |
| [`stage2_textures.png`](stage2/stage2_textures.png) | Base colour, emissive, tangent normal map, UV layout |

**Review shading.** The GPU is shared, so nothing here renders in EEVEE. The toon review is a Cycles-CPU
emission shader that computes its own lighting:
- key + fill N·L through the tangent normal map;
- constant bands with a lifted cool shadow band;
- × base colour, + rim, + emissive.

It is noise-free at 8–16 samples, and the whole review runs in about 40–100 s on 32 threads. The floor is a
diffuse plane under a sun, so he still casts a shadow.

Two rim variants:
- **`toon`** uses a faint neutral rim, to judge the model itself;
- **`toonP1`** adds the client's hero rim in the P1 colour (`crates/gf_client/src/materials.rs`
  `ToonStyle::hero`: rim width 0.42, strength 1; `shaders/toon.wesl`).

The real look still has to be checked in the engine with `ToonMaterial` at stage 5.

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/valdris_stage2.blend` | 12 objects (§4), one material `M_valdris` (base colour, emissive at strength 3, tangent normal map); the face attribute `gf_zone` (paint zone), the vertex colour `gf_mask` (plate outline / per-piece random), and on the parts the face attribute `gf_piece` (rigid piece id → `reports/stage2/parts.json` `piece_table`) | LFS |
| `textures/valdris_basecolor.png`, `valdris_emissive.png` | 2048², sRGB | LFS |
| `textures/valdris_normal.png` | 2048², Non-Color, tangent space, OpenGL +Y (the glTF / Bevy convention) | LFS |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | every hand-set number of the build: landmarks, conform targets, part sizes, paint settings | yes |
| `reports/stage2/*.json` | measured results: fit and conform, parts and pieces, UV / bake / texture stats, glTF check, review metrics including the sleeve fit | yes |
| `work/…` | the sculpt reference with the concept behind it (`valdris_retopo_start.blend`), the intermediate blends, full-size renders and logs | local (regenerated) |

Rebuild everything with `python tools/blender/gf_hero/s2_valdris_run.py [--from <step>]`. The chain is
prepare → base → fit → conform → parts → texture → gltf_check → review → sheets, and takes about 4–9 min on
the dev machine, CPU only.

## 2. Height and proportions

- **Height and head.** 2.30 m (the brief's proposal, the top of the roster range; Brax is 2.2 m). The built mesh
  measures 2.334 m to the rounded tops of the upright pauldron plates. The crown is at 2.305; the highest top lame
  is at 2.296, and the uprights rise 3 cm above the crown.
  Mountainfall's ×1.8 takes him to 4.1 m. The head follows the hero front: eyes at 2.195, the face 0.23 m in
  front of the spine line, about 11 heads tall.
- **Arms.** The arm line is at z 1.78, the anvil's top face. The upper arm is short and swallowed by the pauldron:
  shoulder at |x| 0.37, elbow at 0.595. **Elbow to palm is 0.40 m**, because the cannon's sleeve starts 0.345 m
  behind the palm.
- **Legs.** Crotch about 1.10, knee 0.62, ankle 0.14 inside the sabaton.
- **Stance.** It was widened from the blockout's (boot centres at |x| 0.29) to **0.35** (outer boot to outer boot
  1.07 m, 0.46 H), toward the brief's pillar 1 (0.52 H).
- **In game** (bare T-pose): 97 px tall × 113 px wide at 22 m, 76 × 89 px at 28 m. The blockout measured 90 × 105
  and 70 × 82.

## 3. How it was made

1. **Sculpt reference.** The selected TRELLIS.2 blockout (s202) is scaled to 2.3 m, welded, and stripped of 29
   crumbs. The shared `s2_prepare_blockout.py` gained `--concept-fig` for Valdris's portrait concept.
2. **Base topology.** MakeHuman hm08 (CC0), loaded through MPFB as a tool only, with an older, maximally muscled,
   heavy macro. CC0 face targets push toward the hero front's stern forge-lord:
   - a heavy brow set forward and angled down over deep-set small eyes;
   - a broad, flared nose with a hump;
   - mouth corners down;
   - strong cheekbones, a wide jaw and chin;
   - a thick neck.

   Two un-subdivide passes then reduce it, keeping the joint loops, and it is made symmetric (the same
   `s2_body_base.py` as Brax).
3. **Landmark warp** (shared `s2_body_fit.py`, 36 landmarks): the proportions in §2. The blockout is armour, not a
   body, so every surface-fit band is at weight 0. The feet keep the landmark warp (a new, backwards-compatible
   `mode: landmarks_only` for the rigid feet). Extra loops are added at the knees (3), elbows (3) and wrists (2).
4. **Under-suit conform** (`s2_valdris_body.py`, Valdris only). The body becomes the **under-suit**: mail and
   padding, the face and the gauntlet glove.
   - **Legs.** The blockout's legs are hollow, double-walled shells: a fit along the normal lands on their inner
     wall and gave stick legs. Instead, each leg moves radially to the blockout's **outer** envelope minus an
     inset (3.5–5 cm). The envelope is sampled around the blockout's own leg centres, then applied around the
     wider stance.
   - **Torso.** A smooth superellipse barrel per 2 cm slab (targets measured on the blockout's plate faces beside
     the anvil and under the cape). MakeHuman's muscle bumps would only print through the cuirass as lumps.
   - **Forearms.** Each slab is centred on the arm axis and its radius set (5.2–6.6 cm): the massive plates stand
     off it. Since the polish the glove hand is scaled ×1.6 about the arm axis (`limb_radial.hand_scale`; the
     first build used 1.22), which gives the chunky gauntlet fist room.
   - **Weapon frame.** The weapon attach frame is recorded **on the forearm axis** (§6).
5. **Armour and parts** (`s2_valdris_parts.py` + `s2_valdris_geom.py`, from `stage2_parts.json`). Plates are
   built procedurally around the under-suit and on the blockout's measured envelope, never copied from it. Every
   part is closed, with bevel lips and thin (2 cm; 1.6 cm in the first build) rim bands. The shapes come from the
   concept (§4).
6. **UVs, bakes, textures** (shared `s2_texture.py` with backwards-compatible hooks: Valdris's zone list, his
   painter `s2_valdris_paint.py`, CPU bakes, a tilt filter for the normal bake, and a deeper hidden-face probe in
   `s2_uv.py`).
   - **UVs.** One 2048² atlas. The under-suit that armour covers within 8.5 cm is packed at 0.3 density. The
    hidden-face probe starts 6 mm off each face, so a plate's own shallow creases (pulled-in rims, raised gold
    bands) don't mark visible plates as hidden.
   - **Normal bake.** A high-to-low tangent normal map from the blockout onto the armour and beard, with a 4 cm
     cage. It is cleaned:
     - texels whose hit is more than 1.2–3 cm off the plate fade to flat;
     - normals tilted more than 32–52° fade to flat (39,338 texels);
     - a normalised 1.5 px blur is applied.

     The cape is excluded: the blockout's cape is a fused, fibrous slab, and its normals put pale streaks on
     the cloth. About 291k texels keep sculpt detail.
   - **AO and cavity.** The blockout's cavity and AO, plus a self-AO of the assembled parts, are folded into the
     base colour as darker planes.
7. **Painting** (numpy, from `palette.json` and the sheet's declared colour script):
   - **Plate (polished): cracked stone-like gunmetal.** The base is the declared Gunmetal `#2A242E` pulled 35 %
     toward the measured plate tone `#312C27` (`gunmetal_warm`), so the label's violet does not turn him lavender
     under the cool shadow band. On it:
     - a rectangular stone-block mosaic (a 2D Voronoi in an L_3.6 metric, blocks 1.7× wider than tall, about 15 per
       metre), each block and each plate its own value;
     - painted value planes: front faces a step lighter than side faces, up-facing faces (what the 55° camera sees)
       lifted a little, undersides sunk toward the warm shadow;
     - a lit upper bevel and a dark lower bevel on every block, dark joint cavities and a few thin cracks;
     - the plates' hard edges chipped and lighter where convex (the edge bake; convexity is measured against each
       mesh's median Cycles pointiness), darker in the inner corners.
   - **Glowing seams (emissive).** Lava veins run through the block joints: iso-bands of a low-frequency field
     evaluated at each block's seed light whole chains of block joints, with white-hot dots at the block corners.
     They are broken into runs, denser in the glow regions (the anvil's flanks, the chest, the knees, the greave
     fronts, around the pauldron slots, the forearms) and kept off the up-facing tops. **Lava joints** (new) glow
     where one plate meets another, from a 3 cm ambient-occlusion bake (`edge_bake.joint_ao_distance`) limited to
     faces open to the view. Together they cover 1.4 % of the plate texels, against 0.41 % in the first build. The
     first build had tried a dense crack network and dropped it as orange noise; the veins here follow the block
     joints and the plate structure, and they stay thin lines on dark plate at game size (§7).
   - **Anvil.** Its top face is one value step lighter (the light bar across his chest from above), with a hardy
     hole and a pritchel hole.
   - **Gold and steel.** Forge Gold is painted metal: a highlight band on top, a dark underside, worn streaks. The
     braid caps are light steel.
   - **Cape.** Deep War Red `#7A1F1F` with fold streaks, a darker charred hem and a few ember specks. The **forge
     sigil** is on the back: a blade with three pairs of up-swept branches and a three-point crown, in emblem gold
     with a dark outline.
   - **Skin.** Warm weathered planes, deep eye sockets and heavy painted brows. The **scalp scar** is jagged lines
     across the forehead and scalp in a faint ember (Reforged Flesh).
   - **Beard.** Iron-grey value planes with downward streaks, lighter lock tips and braid-lobe crowns.
   - **Under-suit.** Dark mail with a dim ember glow at the joints: the backs of the knees, the elbows, the waist
     and the armpits.
   - **Other glows.** Eyes, the pauldron slots and the buckle core glow solid.

## 4. Budget and topology

| Object | Tris | Pieces | What | Rigid bone (suggested, `parts.json` `piece_table`) |
|---|---|---|---|---|
| BODY | 7,894 | body + 2 eyeballs | the under-suit: hm08 topology, 87 % quads, symmetric | skinned |
| BEARD | 2,178 | 44 | lofted beard block over the jaw and a bib in front of the gorget; 6 pairs + 1 chunky locks; a two-lock moustache drooping past the mouth corners; **five braids** of plait lobes, each with a gold ring and a steel cap resting on the anvil's top face | head; braids `x_beard_1..5_01/02` |
| PAULDRONS | 1,408 | 30 | per side: **three top lames stepping up** from the front (2.21) to the back (2.296), each lying over the back of the lame in front, with a thin gold rim facet on each step edge, gold outer-end chamfers and chipped outer corners; the cap block under them; the **glowing ember slot** (visible from the front and the side); the lower block and the arm lame stepping down over the upper arm; the **upright plate** at the inner edge with a rounded, gold-edged top 3 cm above the crown; 7 gold rivets | clavicle; lower lame upperarm |
| ANVIL | 354 | 3 | **flat top face at the arm line** (0.88 m wide, 0.65 m in front of the spine line), square heel on his right, horn tapering (in outline and depth) to his left, chipped edges; the strongly waisted body with **two feet** above the belt; the **lava gasket** behind its outline, glowing round its waist | spine_03 |
| CUIRASS | 2,152 | 8 | shingled bands around the under-suit barrel, each upper band outside the lower so the spine can bend: chest (gold collar rim, the arm scye dips at the sides), ribs, belly, the leather belt with gold rims and a gold buckle with an ember core (it shows between the anvil's feet), a two-lame gorget | spine_03 / 02 / 01, pelvis, neck |
| HIPS | 504 | 8 | tassets (two gold-rimmed lames per hip, slanted lower outside, one body radius per column so their edges hang straight), the **chevron fauld** (four V lames, the last one pointed) | pelvis; lower tasset thigh; fauld 3–4 `x_fauld_01` |
| LOINCLOTH | 248 | 1 | war-red cloth behind the fauld with tattered strips to the knees | `x_loin_*` |
| ARMS | 3,108 | 20 | **massive layered plate arms** (12-sided boxy superellipse tubes, thick-walled): two rerebrace lames (r 0.15–0.16, the second with a gold rim), the glowing elbow ring (zone lava), the couter with a raised gold band and an octagonal cop on the elbow point, two vambrace segments (r 0.12–0.126; the second with a raised gold band), the raised gold wrist cuff, the gauntlet cuff narrowing onto the hand | upperarm, lowerarm, hand |
| GAUNTLETS | 1,924 | 42 | **chunky plate fist**: a thick back-of-hand plate, a heavy knuckle guard with four gold studs, **one box-section lame per finger phalanx** (15 per hand), each as wide as its finger's share of the hand so the four fingers close into one plated block, on the finger joints of the same landmark warp | hand, finger bones |
| LEGS | 2,228 | 14 | two shingled cuisse lames with gold lower rims; a big faceted **poleyn** (a 12 cm boss, side wings bulging past the greave, gold top rim, gold sides and gold "smile"); the glowing **knee smile** (zone lava) under it; a boxy **greave**; a raised **shin plate** with gold edges over a **lava gasket**, which gives glowing seams down both sides of the shin | thigh, calf |
| SABATONS | 1,960 | 12 | huge blocky boots, 0.68 m long and 0.40 m wide: a closed foot shell, three shingled toe lames with gold rims, a thick sole slab, and a flared ankle cuff with a raised gold band and a gold top rim (the greave sinks into it) | foot, ball |
| CAPE | 1,000 | 2 | the cape (25 × 9 grid, 1.2 cm thick, folds growing toward a tattered hem, clear of the legs, flaring to 1.7 m) and the **high collar** behind the head with gold edges | `x_cape_*`; collar spine_03 |
| **Total** | **24,958** | 168 rigid pieces | within 15–25k (the first build: 20,866, 141 pieces) | |

Checks (`mesh_stats`, `reports/stage2/texture.json`):
- every object has 0 boundary edges, 0 non-manifold edges, 0 loose vertices, 0 degenerate faces and 0 n-gons;
- rigid pieces are separate closed pieces.

The body keeps hm08's deformation loops:
- **shoulders:** radial loops into the deltoid;
- **elbows and wrists:** 3 added elbow loops and 2 added wrist loops;
- **fingers:** 3 knuckle rings;
- **hips:** hm08 loops;
- **knees:** 3 added loops;
- **neck and face:** the eye and mouth loops.

The torso is a smooth barrel under the cuirass.

## 5. UVs, texel density, textures

| | Value |
|---|---|
| Atlas | one material `M_valdris`: base colour, emissive and tangent normal, 2048² each |
| Texel density | **every visible surface, 300–315 px/m** on every part (330–340 before the polish added armour area): faces with open sky along their normal, the face included. Hidden faces (under-suit under plates, inner walls, undersides) are packed at 0.3×, so the median over all faces is 169 px/m |
| Atlas coverage | 52 %, 4 px margins, 12 px dilated gutters |
| Zero-area UV faces | 2, on the under-suit soles hidden under the sabatons; none on a visible surface |
| Normal bake | 291k texels with sculpt detail; 21 % of the target zones pass the hit-distance and tilt filters. The blockout's plates are not where this build's plates are everywhere, and elsewhere the bake stays flat on purpose |
| glTF check | `reports/stage2/gltf_check.json` **ok**: `M_valdris` has `baseColorTexture`, `emissiveTexture` (with `KHR_materials_emissive_strength` 3) and `normalTexture`; all 12 primitives carry NORMAL, TANGENT and TEXCOORD_0; `extensionsRequired` is empty; 8.0 MB scratch GLB |

At 22 m, 1 m is about 49 px on screen. The atlas is sized for the portrait, the codex and Mountainfall's ×1.8.

## 6. The cannon: attach frame and fit

- **Frame.** The shared fit records the palm centre as the mean of the hand's vertices. For Valdris that mean
  sits 2 cm below the forearm axis (the thumb hangs below the palm), and the cannon's sleeve axis runs through
  its grip. So `s2_valdris_body.py` records `hand_frames` **on the forearm axis**: origin (±0.995, 0.0, 1.78),
  +Y along the fingers, +Z out of the back of the hand. The vertex mean is kept as `hand_frames_vertex_mean` in
  `reports/stage2/body_fit.json`. The origin still lies inside the hand (its vertical span is 1.726–1.795), so
  GF_Hero_v1's "socket on its hand" check holds.
- **Measured fit** (grip frame, T-pose rest; `review.json` `sleeve_fit`). Ray casts on `colossus_cannon.glb`
  measured the cannon's inside and outside:
  - **bore** (free radius): 9.8 cm in the sleeve, 9.4 cm at its rear cuff, 18 cm in the drum;
  - **outer skin**: 13.4–16.6 cm over the forearm, 16.6–16.9 cm at the rear cuff.

  **The polished arm is wider than the bore on purpose.** The orchestrator asked for the concept's massive fist
  arm (about 29 cm across) instead of a forearm thinned to fit the sleeve. So the vambrace (24–27 cm across) is
  sized to stay inside the sleeve's **outer skin**. When armed, the right forearm plates lie inside the sleeve
  wall, hidden, and nothing pokes out. The review now checks both surfaces:

  | Object | Vertices in the cannon's span | Inside the wall (hidden) | Out of the outer skin (visible) |
  |---|---|---|---|
  | ARMS (vambrace, cuffs, couter) | 348 | 240 (max 4.3 cm deep) | **0**; the smallest margin is 0.7 mm |
  | BODY | 533 | 77 | 0, apart from 11 vertices of the open rest-pose thumb |
  | GAUNTLETS | 523 | 86 | 0, apart from 17 vertices of the open rest-pose thumb lames |

  The open rest-pose thumb points 12 cm forward and down in front of the palm; in the grip it folds over the
  fingers. See the section renders in `stage2_armed.png`.

  **For the weapon track (colossus_cannon owner):** the sleeve's 19.6 cm bore is too narrow for a proper
  massive arm. Widening the bore to about 15 cm radius (outer skin about 19 cm) would take the concept's 29 cm fist
  arm with clearance, instead of the arm sitting inside the wall. Until then the fit is correct only visually:
  the cannon hides the forearm.
- **Elbow.** The elbow joint sits 5.5 cm behind the sleeve's rear end. That is more room than the gauntlets have:
  their cuff overlaps the elbow (`docs/art/GF_HERO_SKELETON.md` §7).
- **Grip bar (for the weapon track).** The cannon's inner handle bar runs along the grip frame's **Z**. A
  palm-down fist on this hand frame closes around a bar along **X**, so the fist and the bar intersect inside the
  sleeve, where nobody can see them. Two ways out:
  - rotate the bar 90° in the weapon;
  - make the cannon hold a thumb-up fist, which turns the socket 90° about Y.

  The weapon track and stage 3 decide. Nothing on Valdris's side depends on it.

## 7. Review against the concept (honest)

**Silhouette.** Front IoU against the resolved concept:

| Pose | IoU |
|---|---|
| bare T-pose | **0.823** (0.809 before the polish) |
| armed T-pose | 0.672 (0.671) |
| armed pose45 (the concept's 3/4-drawn arms) | 0.691 (0.690) |

The blockout scored 0.848; it is TRELLIS output conditioned on exactly that silhouette. The armed values are low
because the weapon track built the cannon deliberately large (1.16 m from the elbow cuff to the muzzle, where
the concept has ~0.65 m; its README, "Size"). The cannon's length dominates the normalised overlay. Other
differences:
- the concept's stance is still ~10 % wider than ours;
- the concept's fist forearm is still a little chunkier (0.29 m against 0.24–0.27 m; the sleeve's outer skin, §6);
- the cape reaches out further on the cannon side in the concept (its painted perspective).

**Close-ups and turnarounds.** The concept's hierarchy holds:
- huge layered pauldrons (the stepped top lames, the cap block, the glowing slot, the lower lames) with gold only
  on edges and a rounded upright plate;
- massive gold-banded fist arms ending in chunky plate fists;
- the protruding anvil with a light top face, horn left and heel right, and the lava gasket round its waist;
- the head sunk between the pauldrons, with a stern face, glowing eyes and the scalp scar;
- the beard with its moustache, and five thick braids with gold rings and steel caps resting on the anvil top;
- dark cracked stone-like plate with a lava network in the joints;
- segmented legs: gold-rimmed cuisses, big knee cops over a glowing smile, gold-edged shin plates over lava
  gaskets, blocky gold-banded sabatons;
- the chevron fauld over red cloth;
- the tattered war-red cape with the forge sigil on the back.

**At the in-game camera** (the polish bar: the armed read must beat the blockout column). The polished read
**beats both the first build and the blockout column** (`stage2_ingame.png`, `stage2_before_after.png`):
- a dark mass; the plate is darker and less lavender than the first build's, not the flat grey-violet of it;
- the pauldrons read as gold-framed dark blocks, with the stepped lames and a glowing ember slot at their front;
- the massive arms carry gold bands and end in fists;
- the anvil's top is the light bar across the chest (brief pillar 3), framed by the glowing gasket;
- ember points sit at the knees, the pauldron slots and the anvil flanks: thin lines and points on dark plate, not
  noise;
- the red loincloth marks the centre, and the red collar and cape flanks show beside the arms;
- the cannon carries the aim with its gold hoops and glowing muzzle.

The blockout column is muddier: a near-black mass with scattered gold specks, where the stage-2 read separates
pauldrons, anvil, arms, legs and cape.

How the first build got to its read (still true): a dense lava crack network made the plate orange noise at 22 m,
so its glow became sparse, and gold stays thin (brief §5). The polish keeps both rules. The glow follows the block
joints and the plate structure, so it stays thin at 1.4 % of the plate, and the gold stays on edges and bands.

Caveat: the blockout column comes from the stage-1 renderer (EEVEE, lit albedo with baked light, no rim), and the
stage-2 column from the Cycles emission toon review. The engine's `ToonMaterial` has the final word.

**What still falls short**, for the user's review:
- **The right forearm lies inside the cannon's sleeve wall** (§6): hidden when armed, but the sleeve should be
  widened by the weapon track. The vambrace is 24–27 cm across against the concept's ~29 cm.
- **The gauntlet fist is posed at stage 3.** In the rest pose the hand is open and flat. The box-section lames read
  as a plated block from above, but the thumb hangs as a long, thin box below the palm.
- **The stone-block mosaic** follows the concept's tiled crack pattern. Up close it can read as masonry more than
  as cracked metal slabs; at game size it is a dark speckle, as in the concept.
- **The pauldron tops are large flat areas** from the 55° camera. The steps and gold rims break them up at 3x;
  at 1:1 they read as gold-framed dark blocks.
- **The face** is a fitted MakeHuman face with CC0 stern targets and painted brows and scar: good at portrait
  size, but simpler than the painted concept. There is no facial rig.
- **The braids are stacked plait lobes**: readable, but stylised rather than woven.
- **The stance** is widened to 0.46 H, against the brief's 0.52 H (the blockout's is 0.40 H).
- **The T-pose deformation is untested.** That is stage 3: weights, validation poses, and cloth on the helper
  chains.

## 8. Plan for stage 3 (GF_Hero_v1)

- **Landmarks.** The stage-2 chain matches `s3_landmarks.py`'s expectations:
  - hm08 topology and the same thin-plate spline (`stage2_fit.json` landmarks);
  - the hand scale (`limb_radial.hand_scale` 1.6 since the polish; 1.22 in the first build);
  - `hand_frames` for `weapon_R` / `weapon_L` (on the forearm axis, §6).

  `s2_valdris_parts.py` also records the warped finger joints (`parts.json` `finger_joints_L`).
- **Rigid pieces.** Every armour piece is a separate closed piece. Its suggested bone is in `parts.json`
  `piece_table`, indexed by the face attribute `gf_piece`:
  - the pauldron blocks, slots, upper lames and upright plates go on `clavicle_*` (they must not dig into the chest
    when the arms rise); the lowest lame goes on `upperarm_*`, and a 70/30 clavicle/upperarm blend on the block is
    worth trying for the Bulwark Slam overhead;
  - the anvil and the chest band go on `spine_03`;
  - the ribs, belly and belt go on `spine_02`, `spine_01` and `pelvis`;
  - the plates of the arms and legs go to their segments;
  - one lame per finger phalanx goes on its finger bone (the box-section lames of neighbouring fingers overlap by
    a few mm, so a spread pose may need a little finger-spread limit or lame shrink at stage 3);
  - the boot shell and ankle cuff go on `foot_*`, the toe lames on `ball_*`.
- **The body** takes the MakeHuman seed weights (hm08 topology). The torso barrel is hidden under the cuirass;
  only the joints show.
- **Cloth and hair helper chains** (`x_` extras, never keyed by shared clips; spring-driven in the engine or keyed
  by his unique clips):

  | Chain | Bones | Parent | Rest (m) | Weighting |
  |---|---|---|---|---|
  | `x_cape_{R2,R1,C,L1,L2}_01..05` | 5 × 5 | `spine_03` | columns at u = −1, −½, 0, ½, 1 across the cape's row arcs; joints at z 2.03, 1.70, 1.35, 1.00, 0.65, 0.30 | a column blends linearly between its two nearest chains and a row between its two nearest bones; the top row stays 100 % on `spine_03` (pinned under the pauldrons); the collar is rigid on `spine_03` |
  | `x_loin_{R,C,L}_01..03` | 3 × 3 | `pelvis` | the belt (1.27) down to 0.46 | the same blend; the top row pinned to `pelvis` |
  | `x_fauld_01` | 1 | `pelvis` | from the belt front to the fauld point | fauld lames 3–4; drive it from the average of both thighs (50/50) so it swings clear |
  | `x_tasset_L/R` (optional) | 1 each | `pelvis` | the belt side to the lower tasset | lower tasset lame; 60 % follows `thigh_*` |
  | `x_beard_{1..5}_01..02` | 5 × 2 | `head` | braid root (chin, z 2.0–2.04) → mid → cap | the lobes on `_01` / `_02`, the ring and cap on `_02`; the beard block and moustache are rigid on `head` |

- **Siege Stance anchor spikes** (brief Q6) are not built. They belong with the Siege Stance clip work (rigid, one
  bone each, hidden in the normal pose).

## 9. Shared tool changes (backwards compatible)

Every change is a default-preserving option; Brax's configs set none of the new keys.

| File | Change |
|---|---|
| `s2_prepare_blockout.py` | `--concept-fig crown,sole,centre` (default: Brax's concept) |
| `s2_body_fit.py` | `rigid.feet.mode: landmarks_only` skips the rigid-foot fit; a guard when every band has weight 0 (the report then records 0 fitted vertices instead of crashing) |
| `s2_texture.py` | config hooks `zones` (the material-slot zone list), `painter` (the paint module), `bake_device: CPU`, `normal_max_tilt_deg` (the bad-bake filter), `uv.hidden_reach`, `uv.hidden_start` |
| `s2_uv.py` | `unwrap_all(..., hidden_reach=0.03, hidden_start=1e-4)`, and `face_hidden(..., start=1e-4)` |

**Brax regression check** (`reports/stage2/brax_regression.json`). Brax's stage-2 chain (prepare → base → fit →
parts → texture) was run twice in scratch, once with the HEAD scripts and once with the changed ones, both with
the bakes forced to the CPU. Nothing under `art/characters/brax/` was written.

- **Identical:** every JSON report (prepare, landmarks, fit, parts, texture) and the emissive and normal maps.
  The emissive map is byte-identical to the committed one.
- **Different:** 7 of 4.19M base-colour pixels, by one 8-bit level.

The HEAD `s2_texture.py`, run on the changed chain's intermediates, reproduces the changed result exactly. The
cause is a **pre-existing** nondeterminism in `s2_body_fit.py`: three runs of the unmodified HEAD script gave
identical positions but two different face-corner orders, which nudge the UV unwrap. The changes are
output-neutral for Brax. Strictly byte-identical rebuilds need that fixed; it is flagged as its own task.
The `hidden_start` option was added after this run. Its default is the same literal the code used before (1e-4),
so it cannot change Brax's output.

Valdris-only files:
- `s2_valdris_run.py`, `s2_valdris_body.py`, `s2_valdris_parts.py`, `s2_valdris_geom.py`, `s2_valdris_paint.py`,
  `s2_valdris_review.py`, `s2_valdris_sheets.py`, `s2_valdris_repaint.py` (the polish's look-development aid);
- the sheets are composed without touching `tools/comfy/`.

**The polish pass (2026-09-26) changed no shared file.** Everything it needed is in the Valdris files and configs:
- the joint AO bake and the paint cache live in `s2_valdris_paint.bake_extra`, reached through the painter hook;
- the before / after sheet is in `s2_valdris_sheets.py`;
- the outer-skin check is in `s2_valdris_review.py`.

So Brax's chain is untouched by it.

## 10. Acceptance checklist

| # | Check | Result |
|---|---|---|
| 1 | 15–25k tris | ✔ 24,958 |
| 2 | Deformation loops at shoulders, elbows, wrists, hips, knees, neck; mostly quads | ✔ hm08 loops + 3 knee, 3 elbow, 2 wrist loops; body 87 % quads |
| 3 | No non-manifold geometry, holes, loose parts, n-gons | ✔ 0 / 0 / 0 / 0 on all 12 objects |
| 4 | Armour as rigid plate pieces with bevels, chunky shapes, overlaps, under-layer at the joints | ✔ 168 closed pieces; shingled bands and lames; mail under-suit (dim ember at the joints) |
| 5 | Pauldrons: huge, blocky, layered, upright back plates, glowing slots, chipped heavy edges, gold only on edges | ✔ three stepped top lames + cap block + slot + two lower lames; rounded upright plate |
| 6 | Anvil chest plate: flat top face, horn, waisted body | ✔ plus two feet and the belt buckle core between them |
| 7 | Faulds, tassets, massive layered arm plates, chunky plate-gauntlet fists, segmented legs (cuisses, knee cops with glowing seams, greaves), huge gold-trimmed sabatons | ✔ fist-ready = per-phalanx box lames on the finger bones; the fist itself is a stage-3 pose |
| 8 | Head: bald, scalp scar, stern face; long iron-grey beard in five braids with gold rings and steel caps | ✔ |
| 9 | Cape: war-red, tattered hem, attached at the shoulders / collar, separate, thick, clear of the legs, planned for helper bones | ✔ §8 |
| 10 | One UV atlas; 2048 base colour (NPR, palette, no baked light), 2048 emissive, 2048 tangent normal from the s202 blockout (bad areas filtered), AO / cavity folded in | ✔ |
| 11 | Right forearm and gauntlet fit the colossus_cannon sleeve, checked with its GLB at the recorded palm frame | ✔ visually: 0 plate vertices out of the sleeve's outer skin. The massive arm lies inside the sleeve wall on purpose; the weapon track is asked to widen the sleeve (§6) |
| 12 | Review renders: vs concept armed and unarmed, turnaround, in-game at 22 / 28 m next to the blockout, wireframe, textures | ✔ `reports/stage2/` |
| 13 | Armed in-game read beats the blockout column (polish bar) | ✔ (§7, `stage2_before_after.png`, with the renderer caveat) |
| 14 | The user's final visual approval | **pending_human** |

## 11. Open items

- **User approval** of the look (`status.json` → `2_production_mesh.items.user_visual_approval`), and the two
  stage-0 defaults: the cannon on the right with the anvil kept, and the head size.
- **Stage 3:** weights, the helper chains of §8, validation poses with the cannon (a straight wrist, the elbow
  range), and the grip / fist question of §6.
- **Weapon track:** widen the colossus_cannon sleeve for the massive arm (§6).
- **In-engine check** with `ToonMaterial`: the plate value, the glow balance and the P1 rim at 22–28 m.
- **The DINOv3 licence gate** from stage 1 still applies to the sculpt reference's provenance.

## 12. Reproduce

```sh
python tools/blender/gf_hero/s2_valdris_run.py                 # all steps, ~4-9 min, CPU only
python tools/blender/gf_hero/s2_valdris_run.py --from texture  # repaint + review + sheets
```
