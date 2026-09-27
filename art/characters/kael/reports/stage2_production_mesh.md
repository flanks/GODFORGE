# Kael — stage 2 production mesh (made by AI, 2026-09-27)

> **Made by AI, not a stand-in.** The user decided on 2026-09-25 that there is no human artist: the AI pipeline
> makes stage 2 at production quality and the user gives the final visual approval (`status.json`, stage 2 item
> `user_visual_approval`, `pending_human`).
>
> **Weapons are separate models.** Both hands are empty. The concept's two serpent revolvers are not on the body;
> the shipped chassis `serpent_smg` (`assets/models/weapons/serpent_smg.glb`, the weapon track's file) rides the
> recorded right-hand frame (`weapon_R`) in the review renders, with an identity transform.
>
> **The ghost arm is his LEFT arm**, as the approved concept paints it (`decisions[ghost_arm_side]`, still
> `pending_human`). Swapping sides means re-running stage 1 on a mirrored input.

Review sheets (all in [`stage2/`](stage2/)):

| Sheet | What |
|---|---|
| [`stage2_vs_concept.png`](stage2/stage2_vs_concept.png) | The concept beside stage 2, armed and bare, the back, silhouette overlays and IoU |
| [`stage2_turnaround.png`](stage2/stage2_turnaround.png) | Without the weapon: toon review shading (6 views), clay (4), flat albedo (2) |
| [`stage2_armed.png`](stage2/stage2_armed.png) | With the serpent_smg GLB on the right-hand frame: turnaround and close-ups |
| [`stage2_ingame.png`](stage2/stage2_ingame.png) | The client camera (orthographic 55°, 22 m / 28 m, true 1080p pixels), bare and armed; toon, toon + P1 rim, silhouette, yaw 35; the stage-1 blockout beside each row, 3x zooms |
| [`stage2_closeups.png`](stage2/stage2_closeups.png) | Face (front, both 3/4s, profile), collar, torso, ghost arm and hand, gloved gun hand, hips, hem with the ghost-flame tatters, boot, coat back |
| [`stage2_wireframe.png`](stage2/stage2_wireframe.png) | Joint topology on the body alone (shoulder, elbow, hand, hip, knee, face) and the parts |
| [`stage2_textures.png`](stage2/stage2_textures.png) | Base colour, emissive, tangent normal map, UV layout |

**Review shading.** The GPU is shared with ComfyUI, so nothing renders in EEVEE: the toon review is the Cycles-CPU
emission shader of Valdris's review (key + fill N·L through the normal map, constant bands with a lifted cool shadow
band, × base colour, + rim, + emissive). `toonP1` adds the client's hero rim in the P1 colour. The real look is judged
in the engine with `ToonMaterial` at stage 5.

## 1. Deliverables

| Path | What | Git |
|---|---|---|
| `production/kael_stage2.blend` | 8 objects (§4), one material `M_kael` (base colour, emissive at strength 3, tangent normal map); the face attribute `gf_zone` (paint zone), the vertex colour `gf_mask` (outline / hem distance, per-piece random), and on the parts the face attribute `gf_piece` (piece id → `reports/stage2/parts.json` `piece_table`, with the suggested bone) | LFS |
| `textures/kael_basecolor.png`, `kael_emissive.png` | 2048², sRGB | LFS |
| `textures/kael_normal.png` | 2048², Non-Color, tangent space, OpenGL +Y (glTF / Bevy), baked from the s202 blockout | LFS |
| `stage2_fit.json`, `stage2_parts.json`, `stage2_texture.json` | every hand-set number of the build (landmarks, part sizes, paint settings), each with its `_doc` | yes |
| `reports/stage2/*.json` | measured results: prepare + recentre, fit, parts and pieces, UV / bake / texture stats, glTF check, review metrics | yes |
| `work/…` | the recentred sculpt reference (`kael_retopo_start.blend`), intermediate blends, full-size renders, logs | local (regenerated) |

Rebuild everything with `python tools/blender/gf_hero/s2_kael_run.py [--from <step>]`: prepare → recentre → base →
fit → parts → texture → gltf_check → review → sheets, about 2.5 min on the dev machine, CPU only.

## 2. Height and proportions

- **2.10 m** to the crown (the brief's proposal); the swept-back hair locks reach **2.158 m**. The head follows the
  concept: eyes 1.964 (concept 1.952), chin 1.85, skull 2.075, about 8.5 heads under the hair.
- **Arms.** The blockout's arm line z 1.695 (the concept draws it at 1.726; the blockout drives the sleeve normal
  bake). Shoulder |x| 0.215 (lean), elbow 0.565, wrist 0.89, fingertips 1.095; T-pose span 2.19 m (0.99 × height with
  the sleeves' cuffs, concept 0.98). Hands ×1.05, lean forearms (mean radius 0.058 → 0.035 m).
- **Legs and stance** from the blockout's wide A stance: hip 1.175, knee |x| 0.235 at z 0.582, ankle |x| 0.31, feet
  splayed 10°. Outer boot to outer boot ≈ 0.84 m (the concept's).
- **The coat's flare** (brief pillar 1): half-width 0.33 m at z 1.07, 0.42 at 0.86, 0.53 at 0.65, 0.59 at the hem —
  the concept's 0.84 / 1.01 / 1.21 m widths at 51 / 41 / 31 % of his height. It hangs 0.45 m behind his heels at the
  hem; the lowest tatter points reach 0.30 m (brief: hem at mid-shin, 20-25 % of the height; tears below).
- **In game** (bare T-pose): **73 × 107 px at 22 m, 57 × 84 px at 28 m** (the blockout measured 70 × 102 and 55 × 80);
  armed 73 × 127 px at 22 m.

## 3. How it was made

1. **Sculpt reference** (shared `s2_prepare_blockout.py`, `--concept-fig 27,998,752`): s202 at 2.1 m, welded,
   crumbs dropped. **Recentred** (`s2_kael_recentre.py`, new): the shared step centres the bounding box, but the duster
   trails 0.7 m behind his heels and his ghost arm is 4 cm longer than his gun arm, so the body's centre line (measured
   on horizontal sections of the legs, torso, head and arms) sat at x −0.03, y −0.225. The reference moves by
   (0.03, 0.225, 0) so the symmetric body stands on the origin, the rig's root.
2. **Base topology** (shared `s2_body_base.py`): MakeHuman hm08 (CC0) through MPFB as a tool only, a lean athletic
   macro (muscle 0.9, weight 0.5, age 0.45) and CC0 face targets toward the concept's rugged gunslinger (a strong
   narrow jaw and chin, high cheekbones with hollow cheeks, brows set forward and down, the mouth corners slightly up),
   reduced 4× with its joint loops, symmetric: 3,858 faces, 90 % quads.
3. **Landmark warp** (shared `s2_body_fit.py`, 37 landmarks): MakeHuman's own proportions scaled ×0.913 (its macro
   stands 2.30 m) so the girths stay in proportion, then the head, arms and legs above. A first try with landmarks
   placed from scratch compressed the body's depth and width (the affine part of the spline follows the landmark
   spread); scaling MakeHuman's own landmarks fixed it. Every surface-fit band is at weight 0 (as Valdris's): the
   blockout's torso is coat and bandolier, its shins are boots, its thighs carry the holster, straps and coat panels
   (a thigh fit pulled fins out of them), its face is soft. Extra loops at the knees (3), elbows (3), wrists (2); the
   weapon attach frames at the palm centres (`hand_frames` in `reports/stage2/body_fit.json`); low-poly eyeballs.
4. **Parts** (`s2_kael_parts.py` + `s2_kael_geom.py`, from `stage2_parts.json`), all closed meshes built around the
   fitted body and measured on the reference, never copied from it (§4).
5. **UVs, bakes, textures** (shared `s2_texture.py` through its `zones` / `painter` / `bake_device` hooks, CPU bakes):
   one 2048² atlas at ≈ 430 px/m on the visible parts; faces that find another part within 4.5 cm along their
   normal (the body under the coat, the boots, the belts) are packed at 0.3 density. A tangent normal map from the
   blockout onto the coat, boots, gear, hair and loin cloth, with a 4 cm cage, faded to flat where the hit lies more
   than 1.2-3 cm off the low poly and where the baked normal tilts past 32-52° (the blockout's coat is thick and flares
   wider than this build's, so 28 % of the target texels keep blockout detail: its folds where the two agree). The
   blockout's cavity and AO and a self-AO bake of the parts fold into the paint (`s2_kael_paint.py`, §5).
6. **Review** (`s2_kael_review.py`, a copy of Valdris's review without the sleeve check and the pose) and **sheets**
   (`s2_kael_sheets.py`).

## 4. Parts and the stage-3 plan

24,114 triangles in 8 objects (budget 15-25k; the weapon is separate), 110 registered pieces, every object closed
(0 boundary edges, 0 non-manifold edges).

| Object | Tris | What | Suggested bones (`parts.json` `piece_table`) |
|---|---|---|---|
| BODY | 7,846 | the under-layer: skin on the head, neck and the right hand's fingers; the fingerless glove; the **ghost flesh on the left arm below the bicep strap** (a zone of the body, the same topology as the right arm); black cloth (shirt, trousers, 1 cm of trouser volume on the thighs); the eyeballs; the soles lifted 2.2 cm inside the boots | the GF_Hero_v1 core |
| COAT | 4,684 | **yoke and sleeves**: the body's own quads from the waist up, pushed 1.5-3 cm out along the normals, 8 mm thick (a maroon-violet lining inside, a worn bronze-grey rim on every edge), open at the front in a V and round the neck; the right sleeve ends at the elbow, the left one is **rolled up above the ghost arm**; **skirt**: an A-line from the waist (tucked into the yoke's wall) to a torn hem, never closer than 2-3 cm to the body, belts, holster, pouch, loin cloth and boots; open at the front, a **centre back vent** from z 1.03, long / short tear points with slits between the last rows; **high collar** with two flared points framing the head; **lapels**; **rolled cuffs** | yoke skinned (spine, clavicles, upper arms); skirt `x_coat_L_*` / `x_coat_R_*` chains by angle (front, side, back per side); collar `neck_01`; lapels `spine_03`; cuffs on the arm bones |
| WISPS | 780 | **five ghost-flame tatters** (brief swatch 12): chunky emissive cloth tongues lying on the hem (two at each front corner, one at the back, off centre), falling 0.19-0.26 m past it and curling outward | one 3-bone `x_wisp_<n>_01..03` chain each |
| GEAR | 4,316 | upper belt with the oval bronze buckle and the **ghost gem**; lower slung belt (lower on his right) with a buckle; **bandolier** from the right shoulder to the left hip with six cartridges (gun-metal cases, bronze caps); the long **holster** on the front-outer right thigh with two thigh straps; the left hip **pouch**; the left thigh strap with a buckle; the right **bracer** with two straps and the glove cuff; the left bicep and wrist straps | rigid: `spine_01` / `pelvis` / `spine_03` / `thigh_*` / arm bones |
| BOOTS | 3,432 | tall boots: a shaft round the calf, a lofted foot shell with a flat sole at z 0, a flared knee cuff pointed over the knee, three strap bands with buckles (the concept's overlapping strap plates) | `calf_*`, `foot_*` |
| HAIR | 2,408 | the swept hair (Brax's shell method on the body's scalp quads, pushed out to the blockout's hair) with 52 flat locks swept back along the skull, a fringe of four locks over the brow, and the short chin beard | `head` |
| SCARF | 336 | the black scarf round the neck inside the collar, with a short drape | `neck_01`, `spine_03` |
| LOINCLOTH | 312 | the maroon torn cloth from the lower belt to 0.6 m, draping over the most forward surface above it, three torn strips | `x_loin_C_01` chain |

## 5. Textures (hand-painted NPR, no baked light)

- palette.json's measured tones are the colours; three value groups stay apart (DARK: coat, hair, black cloth,
  maroon, leather, boots · MID: bronze, skin · EMISSIVE: the ghost green).
- **Coat**: violet, not black: up-facing faces (what the 55° camera sees) lifted toward the highlight tone
  (brief §5), vertical fold streaks, low-frequency worn patches, darker toward the hem, the lining a darker
  maroon-violet, the rims a worn bronze-grey trim (the concept's light edge lines). **The torn hem dissolves into ghost
  flame**: the lowest 13 cm take a teal tint and a soft emissive, flickering, strongest at the hem edge.
- **Ghost arm**: mottled teal-mint ghost flesh with a network of bright veins, emissive (0.6 of the flesh, 1.0 in the
  veins), never multiplied by AO. **Wisps**: from a dim root on the coat to a bright tip with flame streaks.
  **Gem** and the **left eye** glow; green veins creep from the left eye over the temple and the cheek.
  The ghost green is declared teal-mint (`#62E0B2` hot, `#C4FFE6` core, `#2A8A74` rim): brighter than the concept's
  sage `#80B290`, leaning teal, clear of the P4 ring green `#5BE37D` (brief §4).
- Skin: warm planes, painted brows, the shaved jaw and chin (a cool stubble overlay), the scar over his right brow;
  the right eye amber-brown. Hair: dark value planes, lighter lock tops, the light grey streak over the ghost side.
  Black cloth: a cool weave, lifted up-facing planes. Leather and boots: warm browns, darker strap edges, lighter
  scuffs, dark soles. Bronze: a painted highlight band. Cartridges: dark gun-metal cases.
- AO (the parts' own, the blockout's on the coat and gear) and the blockout's cavity fold into the non-emissive zones;
  the skin skips the self-AO (16 samples speckled the neck under the collar).

## 6. Numbers

| | |
|---|---|
| Triangles | 24,114 (BODY 7,846 · COAT 4,684 · GEAR 4,316 · BOOTS 3,432 · HAIR 2,408 · WISPS 780 · SCARF 336 · LOINCLOTH 312) |
| Topology | 0 boundary, 0 non-manifold edges on every object; body 90 % quads; 110 pieces |
| Texel density | ≈ 430 px/m median over all faces, 460-470 on the coat, boots, gear and wisps; hidden faces at 0.3 |
| Normal bake | 394k texels with blockout detail, 28 % of the target zones valid |
| glTF check | base colour, emissive and normal textures, tangents on all 8 primitives, no required extensions (`reports/stage2/gltf_check.json`) |
| Front IoU vs the stage-1 cut-out | 0.574 bare, 0.392 armed (§7) |
| In game | 73 × 107 px (22 m), 57 × 84 px (28 m) |

## 7. Known limits and open items

- **The concept IoU is low (0.57)** and says little: the sheet aligns bounding boxes, and the concept's figure is
  not centred in its own box (his ghost arm reaches 4 cm further than his gun arm, so the whole silhouette shifts),
  its arm line is 3 cm higher, and its coat and tatters are drawn blown out to the sides. The shapes match by eye
  (`stage2_vs_concept.png`).
- **102 hidden UV faces are degenerate** on the body's toes inside the boots (the foot lift squeezes the toes);
  nobody sees them.
- The hair is a stylised swept-back mane of flat locks (the concept's hair is softer); the collar's two flared points
  read as flat panels in the 3/4 close-ups.
- The ghost arm's veins read as a cracked network rather than the concept's soft glow bands; the emissive level is the
  same everywhere on the arm, so it never goes dark (brief §5).
- The coat's back is the brief's §7 proposal (one violet panel, centre vent, torn hem with a ghost-flame tatter);
  the optional back sheet is still `pending_human`.
- Stage 3 must hang the skirt on `x_coat_*` chains, the tatters on `x_wisp_*` chains and the loin cloth on `x_loin`; the
  yoke's inner wall sits 0.7 cm (sleeves) to 2.2 cm (torso) off the body, so shoulder and elbow bends need the helper bones or corrective
  weights to keep the body inside.
