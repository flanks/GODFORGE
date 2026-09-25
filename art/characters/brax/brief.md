# Brax, The Furnace-Born: character brief (stage 0)

Sources: `content/sheets/characters.csv` row `brax` · `assets/content/kits.ron` (BRAX block) ·
`content/sheets/chassis.csv` row `anvil_gauntlets` · the approved front concept
[`references/BRAX_front_approved.png`](references/BRAX_front_approved.png)
(sha256 `407114e7…0b64`, the user's approval) · measured colours in [`palette.json`](palette.json) /
[`color_script.png`](color_script.png) · game-scale check in
[`reports/stage0_readability.png`](reports/stage0_readability.png).

The approved front concept is the design authority. Where this brief goes beyond it (the back,
the fist, lighting states) it proposes, and the pending sheets settle it with the approver.

## 1. Who he is (from content)

| | |
|---|---|
| Key / name | `brax`: Brax, *The Furnace-Born* |
| Role / phase | Brawler / Melee · EA |
| Fantasy | "Bare-knuckle demigod with forge-gauntlets. For Brax, punching is the build." |
| Colour | `#FF7A3D`, which sits dE 4.6 from the concept's lava "hot" tone, so the UI colour and the model's glow agree |
| Stats | 300 HP · move 6.2 · 2 dash charges (1.1 s) · collision radius 0.52 |
| Signature chassis | `anvil_gauntlets`: "Short-range shotgun-fists", Melee, Kinetic, style `Fist`, range 2.8, 3 hits/s |
| Passive: Heat Gauge | sustained fire builds Heat; at max, attacks ignite and stagger (kit approximation: 25 % Burn on hit, 10 % less damage taken) |
| Active 1: Cinder Uppercut (7 s) | launch: Nova r 2.6, stun 0.8 s, knockback; then a flame Field r 2.8 for 3 s (the "geysers") |
| Active 2: Furnace Rush (8 s) | Rush 8 m in 0.4 s, Flame damage, **drags** enemies along |
| Ultimate: Meltdown (8 s) | Buff: damage ×1.5, fire rate ×1.3, shockwave explosions r 2.0, element Flame, **model scale ×1.25** |
| Co-op role | crowd control, frontline DPS, pairs with Valdris |
| Skins (content) | Furnace-Born (base) · Slagfist · Ember Pugilist, all on the same rig |

Consequences for the art:
* **Meltdown scales him by 1.25.** At 2.2 m he becomes 2.75 m for 8 s, so shockwave and fist VFX
  must ride sockets, not world offsets.
* **Three skins share one body.** Build the gauntlets, skirt and sash as separable mesh parts so a
  skin can swap them without touching the body or its weights.
* **The chassis fires by punching.** The pipeline keeps weapon fire procedural, but a punch is a
  body motion. See section 8.

## 2. Silhouette pillars (priority order)

1. **The gauntlets dominate.** Each gauntlet (fingertip to elbow ring) is **37 %** of his height
   long and **15 %** thick. That is 1.6× the bare upper arm and about 1.6 head-widths. Both arms
   together are about **23 %** of the silhouette's area. The gauntlets must stay the biggest and
   darkest masses in every pose and at every LOD. In gameplay poses the fists are held out from the
   body (guard at chest height), never tucked into the torso's outline. Seen from the 55° camera,
   their **top faces** matter most, so the brightest cracks and the bronze rings belong there.
2. **V-taper torso.** The shoulders (deltoid to deltoid) are about 2.2× the waist, and the lats
   are 1.33× the waist (231 px against 174 px on the concept). The chest is bare with the sigil as
   its centre mark. The head is small: about 7.3 heads tall, so the body reads as heroic.
3. **Low, heavy stance.** In the T-pose his feet are 44 % of his height apart, and the skirt flares
   to 1.9× the waist. The read is an X: a wide top, a pinched waist, a flared skirt and planted
   feet. The gameplay idle keeps that X low: knees bent, feet wider than the shoulders, fists
   forward, head slightly down.
4. **One cool accent.** The teal sash is a vertical stripe down the centre, and the teal ankle
   wraps echo it. They are the only cool hue on him. They separate him from the warm floors of
   Cinder Wastes and from Valdris's gold.

## 3. Proportions (measured on the concept, 970 px crown to sole)

At the proposed in-game height of **2.2 m** (roster range 2.0 to 2.3 m; stage 3 sets the final
value), 1 px = 2.27 mm.

| Measure | px | at 2.2 m | Note |
|---|---|---|---|
| Height, crown (hair) to sole | 970 | 2.20 m | hair spikes about 1.5 cm |
| Head width at the eyes | 89 | 0.20 m | |
| Crown to beard tip | ~134 | ~0.30 m | about 7.3 heads tall |
| Gauntlet length, fingertip to elbow ring | ~358 | ~0.81 m | |
| Gauntlet max thickness (at the elbow ring) | 149 | 0.34 m | |
| Bare upper-arm thickness | ~90 | ~0.20 m | |
| Lats / waist / belt width | 231 / 174 / 197 | 0.52 / 0.39 / 0.45 m | |
| Skirt hem width | 330 | 0.75 m | |
| Stance, outer foot to outer foot | 431 | 0.98 m | T-pose reference stance |
| Arm span (T-pose) | 1161 | 2.63 m | 1.2× height, driven by the gauntlets |

These numbers are not approximations to replace later. They are what the stage 1 blockout's
front-silhouette IoU and the stage 2 retopo are checked against.

## 4. Materials and callouts

The numbers refer to the swatches in `color_script.png` / `palette.json`. Hex values are the
measured *base* tones. Shadow and highlight tones are in the JSON.

| # | Material | Base | Finish / construction | Shader and texture notes |
|---|---|---|---|---|
| 1 | Skin | `#B46746` | matte, sun-dark | Toon ramp with a **warm** shadow (`#854936`, hue shifted toward red, never greyed). Soot flecks and thin lava veins over the shoulders and chest are texture only. |
| 2 | Hair & beard | `#1C1210` | short spiky hair, short full beard | Model the beard as one mass. At game scale it is the jaw's dark shape. |
| 3 | Eye glow | `#F5A611` (core `#FAEA3C`) | emissive | 1 to 2 px at game scale. The glow under a dark brow is the read. Emissive texture, unlit. |
| 4 | Gauntlet rock | `#291F1E` | chunky bevelled basalt plates, three rigid segments per finger plus knuckle plates | Flat dark plate faces. The **grooves between plates** carry the lava. No mid-tone grunge, which reads as mud when small. Lift the top faces toward `#4A3A36`. |
| 5 | Lava glow | rim `#E7480D` · hot `#F2753B` · core `#FEE265` | emissive cracks in the gauntlets, the chest sigil (a ring plus a vertical line) and the skin veins | Unlit, with bloom. Intensity is a runtime parameter driven by Heat Gauge (low state: dim embers, **never fully off**) and Meltdown (core to white-hot). |
| 6 | Bronze bands & buckle | `#955B32` (hl `#D99452`) | big ring at the elbow with a cog knob underneath, thin band mid-forearm, round belt buckle | Painted-metal NPR: a hand-painted highlight band, not PBR reflections. |
| 7 | Scale-plate skirt | `#925832` | overlapping leaf plates in three tiers, rivets | dE 2.0 from the bronze bands, so they are **one bronze material**. The plates differ by wear and roughness only. |
| 8 | Belt leather | `#291E1B` | riveted belt | |
| 9 | Torn cloth | `#4A2B26` | ragged under-skirt under the plates | The jagged hem is close-range detail. At game scale it is part of the skirt's flare. |
| 10 | Teal sash | `#1F5A64` | knotted at the waist below the belt, two tails to mid-shin, frayed ends | Keep it saturated. It is the secondary read (pillar 4). |
| 11 | Sash gold pattern | `#7A6435` | thin meander on the tails | Texture only. It is invisible at game scale. |
| 12 | Ankle wraps | `#284244` | criss-cross bands, barefoot | |
| 13 | Wrap underlayer | `#715846` | pale linen between the bands | |

## 5. Readability at 6 to 8 % of screen height

See [`reports/stage0_readability.png`](reports/stage0_readability.png). This is a 2D check: the front
plate shrunk to 65 and 86 px and pasted into a real client frame. It is not a render through the
55° camera.

**Survives at 65 to 86 px:** the two dark fist masses at the ends of the arms, the chest sigil (a
2 to 4 px bright mark), the vertical teal sash, the teal ankle wraps and the flared skirt outline.
**Lost at 65 to 86 px:** the face, eyes, beard shape, soot flecks, rivets, cogs, the gold sash
pattern and the ragged hem. Those are close-up detail for the character select screen and the
codex.

Findings, measured in CIELAB:
1. **Skin melts into the Cinder Wastes floor.** The lit flagstone in `doors.jpg` is `#72462B`
   (L\* 34). Brax's skin shadow is `#854936` (L\* 38), almost the same hue and value. His skin
   base (L\* 52) separates by only about 17 L\*. In the pasted frame the torso and legs dissolve,
   and he is carried by the dark fists, the teal and the outline. **Therefore the inverted-hull
   ink outline, the player ground ring and a warm-white rim term are load-bearing for Brax.** Do
   not darken or desaturate the skin toward the floor to "fit the biome".
2. **The fists vanish on dark grounds.** The rock (L\* 13) is +1 L\* against The Hollow Spire's
   ground and +8 against The Unmaking's. On those biomes the gauntlets read only through the
   emissive cracks and the bronze. That is why the Heat Gauge low state must never turn the cracks
   off, and why the top faces get the lighter rock tone.
3. **Lava competes with Cinder Wastes.** His lava "hot" tone is only dE 16 from the biome's glow
   accent `#FF8A2A`. His flame VFX need a shape language (geyser columns, shockwave rings) that
   differs from the environment's lava pools. Player-side zones stay gold-rimmed
   (ARCHITECTURE §7), which covers the Cinder Uppercut field.
4. **The T-pose flatters him.** An arms-down or guard idle loses about 40 % of the plate's width.
   The stage 1 blockout renders through the real 55° orthographic camera, and the stage 3/4 idle,
   are where pillar 1 is proven.
5. **From 55° the sigil foreshortens** to about 57 % of its height, and a guard pose covers part
   of it. The sigil is the tertiary read. The gauntlets are the identity.

## 6. What must survive the toon shader

* **Three value groups.** DARK is rock L\* 13, leather 12, hair 6, wraps 26. MID is skin 52,
  bronze 44, plates 43, teal 35, linen 40. EMISSIVE is the lava and the eyes (L\* 63 to 90). No
  ramp band, rim term or bloom may merge DARK into MID. In particular, the skin's shadow band must
  stay above about L\* 35.
* **Emissive bypasses the ramp.** The cracks, sigil and eyes are never multiplied by shadow or AO.
  Bloom is allowed to spread them. Nothing else may bloom.
* **Warm hue-shifted shadows.** The measured shadows shift toward red (skin `#854936`, bronze
  `#6B3D1E`). A ramp that greys its shadows kills the look.
* **Shape from geometry, surface from texture.** The plate silhouettes, rings, skirt tiers and
  sash tails are geometry. The cracks, soot, rivets, meander and fray are texture.
* **Outline at fist scale.** Tune the ink outline so the fingers merge into one fist shape at game
  distance. Per-finger outlines turn to noise.
* **Two tones on the rock.** Flat dark plates plus emissive grooves. A third mid-tone reads as mud.

## 7. Open design questions (settled by the pending sheets)

| Question | Proposal (the approver decides) | Settled by |
|---|---|---|
| What is on his back? | Lava cracks continue thinner and dimmer over the trapezius and shoulder blades. No second sigil. The belt continues around without a buckle. The scale skirt wraps all the way around. The sash knot and tails stay at the front. | back view, 3/4 view |
| How does a gauntlet make a fist? | Rigid plates per finger segment that overlap when curled. The knuckle plates form a flat punching face. The bronze rings stay rigid. | gauntlet sheet |
| Do the skin veins grow with Heat? | Yes: dim at 0 Heat, bright at max, full body during Meltdown. | colour script |
| What does Meltdown look like? | The gauntlets turn mostly emissive (core-yellow cracks widen), the chest sigil flares, the eyes go white-hot and heat shimmer rises from the fists. The scale is 1.25. | colour script |
| Where are the sash tails and the ragged hem driven? | Short bone chains on the master skeleton's per-character extras, with spring motion at runtime. | stage 3 |

### Settled by the approved turnaround sheet (2026-09-25)

The user supplied [`references/BRAX_sheet_turnaround.png`](references/BRAX_sheet_turnaround.png). It settles most
of the table above; where it differs from a proposal, the sheet wins.

* **Back:** a glowing crack runs down the spine from the nape to the belt and branches across both shoulder
  blades, brighter than the thin dim cracks proposed above. No second sigil. The scale skirt wraps all the way
  round, and a teal sash tail also hangs at the back centre.
* **Fist:** closed fists built from basalt segments with lava in every gap. Blocky knuckle plates glow at the
  striking face. The bronze is a cuff at the elbow plus an angular (hexagonal) strap frame along the back of the
  forearm that ends in a ring on the back of the wrist.
* **Face:** a confident grin, glowing amber eyes, a full short beard and messy black hair.
* **Chest sigil:** the ring and vertical line, with cracks radiating onto the pecs and shoulders.
* **Colour swatches:** `#2A292B` rock, `#FA5F26` lava orange, `#FDA747` lava amber, `#472B23` dark brown,
  `#025D67` teal (status.json item `colour_swatches`).
* **Still open (optional):** the Heat 0 / Heat max / Meltdown looks. The sheet's action panel shows the uppercut's
  flame burst but no lighting states; a colour script would settle them.

## 8. Notes for stages 1 to 4

* **Stage 1 input.** The concept is dark basalt on a dark navy ground (rock L\* 13 against the
  background's L\* 11). Background removal must be checked for the gauntlets before any TRELLIS.2
  run, and the conditioning background must be neutral grey. The stage 1 tool already does both
  (`--mask-only`, `#808080`).
* **Stage 2 budget (per the pipeline, about 15 to 25k tris).** A proposed split: gauntlets 35 %
  (they are the silhouette), body and head 35 %, skirt and plates 20 %, sash and wraps 10 %.
  Fingers are rigid segments, so they can be low-poly with clean splits at the joints.
* **Stage 3.** On GF_Hero_v1, the gauntlet plates are weighted rigidly per bone (hand, finger
  segments, forearm twist), not blended. The elbow ring stays rigid on the lower arm.
* **Stage 4, Brax's unique clip set (proposal, 9 clips):** `brax_idle_signature@loop` (vent heat
  and roll the shoulders), `brax_punch_l` and `brax_punch_r` (additive upper-body strikes layered
  on the shared locomotion), `brax_cinder_uppercut`, `brax_cinder_slam`,
  `brax_furnace_rush_start`, `brax_furnace_rush@loop`, `brax_meltdown_start` and
  `brax_meltdown_idle@loop`. The punches are the chassis' "fire pose". A melee strike cannot be
  sold by a recoil curve, so it is authored as a short additive layer, while aim offsets,
  hit-stop, shake and recoil stay procedural as the pipeline requires.
