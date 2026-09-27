# Selene, The Stormcaller: character brief (stage 0)

Sources: `content/sheets/characters.csv` row `selene` · `assets/content/kits.ron` (SELENE block) ·
`content/sheets/chassis.csv` row `thundercoil_launcher` · the approved front
[`references/SELENE_front_approved.png`](references/SELENE_front_approved.png) (the user's
`docs/media/playable_characters/selene.png`, 1536x1024 T-pose on flat dark navy, sha256 `a75de828…f6e0`) ·
measured colours in [`palette.json`](palette.json) / [`color_script.png`](color_script.png) · the game-scale
check in [`reports/stage0_readability.png`](reports/stage0_readability.png).

**Design authority.** One approved concept, the front. Everything it does not show (side, back, the
hair bun from behind, the cape attachment, the soles) is a proposal in this brief until the optional
sheets in [`turnaround_prompts.md`](turnaround_prompts.md) are approved or stage 2 settles it. "Her
right" always means the character's own right, which is the **left** of the front image.

**Not body: the two floating coils.** The concept draws two coil devices floating beside her hands
(claw-tipped barrels with glowing cores, image x 224-480 and 1052-1305). They are weapon / VFX, not
body (the user's rule of 2026-09-25: weapons are separate models on the hand sockets). The body gets
empty hands; her weapon is the already-built chassis `thundercoil_launcher`
(`assets/models/weapons/thundercoil_launcher.glb`) on `weapon_R` / `weapon_L`. The coils could become a
Thundercoil skin variant later.

## 1. Who she is (from content)

| | |
|---|---|
| Key / name | `selene`: Selene, *The Stormcaller* |
| Role / phase | Glass Cannon / Blaster · P1 |
| Fantasy | "Lightning in human shape. Deletes screens, dies if touched." |
| Colour | `#6FE3FF` (ice cyan): measured as her lightning (the arm veins' hot tone `#6BB9EB` is dE 21.5, the collar gem `#5BD4F4` closer) |
| Stats | **190 HP (the lowest)** · move **7.0 (fast)** · 2 dash charges (1.0 s) · collision radius **0.42** (small) · ult charge 0.0005 per damage |
| Signature chassis | `thundercoil_launcher`: "Coiled lightning orbs that crackle on impact." Auto fire, 3.5 shots/s, Storm, style `Orb`, range 14, splash r 1.0. Shipped as a two-handed weapon GLB |
| Passive: Static Charge | movement builds charge (1.5 % per metre, up to +60 %); the next Active deals bonus damage and chains |
| Active 1: Arc Nova (6 s) | chain-lightning burst: 8 targets, range 6, 45 damage, scales with the weapon's fire rate |
| Active 2: Blink (5 s) | teleport 7 m through enemies, a storm trail (40 damage) |
| Ultimate: Heaven's Verdict | a moving thunderstorm front, r 5.0, 8 s, placed at the aim point (range 10), travels 1.5 m/s: 30 dps + Shock, and allies' projectiles inside it get ×1.35 damage and chain twice |
| Co-op role | "Wave clear, ultimate battery, the one who ends the boss phase." |
| Skins (content) | Stormcaller (base) · Eye of the Tempest · Skybreaker, all on the same rig |

Consequences for the art:
* **She dies if touched**, so the player must find her instantly in a crowd. Her silhouette is a thin dark
  vertical core inside a fan of blue cloth; the light accents (skin, silver hair, glows) sit at the top of
  the figure, which is what the 55° camera sees most.
* **She is fast (7.0) and blinks.** The cloth (capes, panels, tabard) is long and trails behind her at
  run speed; its chains must be short enough to settle within a Blink (the model is hidden for the
  teleport, so the cloth pops unless blink_out / blink_in hold it in a neutral state).
* **Three skins share one body.** Build the capes, side panels, tabard, gauntlets, greaves / sabatons and
  the crystal crown as separable parts, so a skin swaps them without touching the body or its weights.
* **The P2 ring is almost her kit colour.** `game.ron` player 2 is `#3FD8FF`, dE 8 from `#6FE3FF` and
  dE 5 from her collar gem. Keep the cyan to small emissive accents (section 5, finding 3).

## 2. Silhouette pillars (priority order)

1. **A tall, thin, dark vertical core.** Black bodysuit, leggings and pointed sabatons, feet together:
   the body is only 0.21 m wide at the waist and 0.19 m across both sabatons. Read: a needle / a
   lightning bolt standing on its point. The body never gets bulkier than the concept.
2. **The storm-blue cloth fan.** Two long outer capes hang from shoulder bows and billow out under the
   arms to ragged storm-cloud edges (2.05 m across at the widest in the T-pose), plus two hip panels and a
   long pale tabard between the legs. They are the largest colour area (about 60 % of her pixels) and fade
   from deep blue (`#213F6F`) at the top to pale storm-cloud (`#7788A8`) with ragged, torn hems. In play
   (arms down, moving) they close in and trail: the fan becomes a long tapered wake.
3. **The light top: silver hair, a high bun and the floating crystal crown.** A small pale head with a
   high bun and six small storm-crystal shards floating round it (three per side, symmetric; a ring about
   0.40 m across). From 55° the crown and hair are her brightest non-glowing mass, and the shards give the
   head a spiky "charged" outline.
4. **Bare pale arms with lightning veins.** The skin (L\* 72) and the emissive veins make the arms a light
   line against the dark body; the dark fingerless gauntlets with ice-blue claw tips end them.
5. **Small glow points, never a glow mass.** The collar gem (her centre mark), the eyes, the arm veins
   and the cyan V-glows on the greaves and sabaton edges. Together about 5 % of her pixels.

## 3. Proportions (measured on the approved front, 963 px from the top of the bun to the sabaton tips)

Proposed in-game height **2.2 m** to the top of the bun (the roster range is 2.0-2.3 m; Brax 2.2, Valdris
2.3; the stage-1 blockout is normalised to 2.2 m and stage 3 sets the final value). 1 px = 2.28 mm.

| Measure | px | at 2.2 m | Note |
|---|---|---|---|
| Height, bun top to sabaton tips | 963 | 2.20 m | the crystal shards reach the same top line |
| Head, skull top to chin | ~115 | ~0.26 m | about 8.4 heads tall (8.1 without the bun): heroic, elongated |
| Bun above the skull | ~28 | ~0.06 m | |
| Crystal crown, outer shard to outer shard | ~173 | ~0.40 m | six shards, 25-40 px long each (6-9 cm) |
| Arm line (T-pose) height | 752 above the tips | 1.72 m | 0.78 H |
| Arm span, fingertip to fingertip | 870 | 1.99 m | 0.90 H |
| Shoulder ornaments (bows), outer | ~315 | ~0.72 m | the capes hang from them |
| Waist width | ~90 | ~0.21 m | |
| Hips (legs) / with the hip plates | ~135 / ~205 | ~0.31 / ~0.47 m | |
| Crotch height (under the tabard) | ~517 | ~1.18 m | 0.54 H: long legs |
| Knee (greave top) height | ~322 | ~0.74 m | |
| Sabatons, both, outer | ~85 | ~0.19 m | feet together, toes pointed down |
| Outer capes, widest (T-pose) | 897 | 2.05 m | hems at 0.40-0.48 m above the tips |
| Tabard / hip panels hem | | ~0.29-0.43 m above the tips | ragged |

The collision radius is 0.42 m (a 0.84 m circle): the body fits well inside it and only the cloth
overhangs it.

**The feet.** The concept draws the sabatons pointed straight down with the feet together, a floating
read. Proposal: in the shared clips she stands on the GF_Hero_v1 foot contract (soles on the ground, the
pointed sabaton toe as the forefoot, heels slightly raised by the sabaton shape); only the signature idle
and the ultimate hover (a few centimetres, a light sway). The user may prefer a permanent hover
(section 7.2 Q2).

## 4. Materials and callouts

Numbers refer to the swatches in `color_script.png` / `palette.json` (measured inside the birefnet mask:
the flat navy ground `#17202A` is only 2.4 L\* below her bodysuit).

| # | Material | Measured base (shadow / highlight) | Construction and shader notes |
|---|---|---|---|
| 1 | Skin | `#C6ABA1` (`#B2958F` / `#CCB6AE`) | pale, cool; face, shoulders, bare arms. Cool shadows (never grey) |
| 2 | Silver-white hair | `#ADB1BD` (`#8B91A1` / `#DDEAF3`) | high bun, swept strands framing the face. Value planes painted, no strands as geometry beyond a few chunky clumps |
| 3 | Eye glow | rim `#90B6D6` · hot `#A6CAE2` · core `#A9F0FC` | EMISSIVE; 1-2 px at game scale |
| 4 | Collar gem | rim `#1F86C1` · hot `#5BD4F4` · core `#A4EFFA` | EMISSIVE, a diamond at the high collar: geometry (a faceted gem), glow in the texture |
| 5 | Lightning veins | rim `#3887CE` · hot `#6BB9EB` · core `#98E8FC` | EMISSIVE lines on both bare arms (shoulder to wrist); Static Charge can scale them at runtime |
| 6 | Black bodysuit | `#1E252B` (`#0D1219` / `#36435B`) | high collar, sleeveless, a bust shell with gold straps; navy-cast black |
| 7 | Leggings | `#222C3F` (`#1D2536` / `#313D55`) | dE 9.6 from the suit: **one material** with a bluer lower half; fine gold seams are texture |
| 8 | Gold filigree trim | `#635346` (`#51453C` / `#8F7D68`) | collar straps, bust edge, belt rings, hip plates, knee plates, greave and sabaton edges: **thin rims only**. Painted-metal NPR: flat base + a painted highlight band. The concept's gold is dull and greenish; paint it a touch warmer and lighter so it reads at game size |
| 9 | Fingerless gauntlets | `#303540` (`#16171B` / `#555153`) | dark leather and plate from mid-forearm to the knuckles, gold edge at the cuff; bare fingers with **ice-blue claw tips** (small, painted near the veins' hot tone) |
| 10 | Tabard centre panel | `#3F5D8D` (`#395379` / `#7B8BA1`) | long front panel between the legs, gold-veined, paler toward the hem |
| 11 | Side panels | `#40648D` (`#1C3A57` / `#6C87A9`) | two long hip panels, cyan-blue at the top fading down; ragged hems |
| 12 | Cape, deep storm blue | `#213F6F` (`#192F54` / `#355B8E`) | the outer shoulder capes: the largest area, the "deeper blues for large areas" rule |
| 13 | Cape, storm-cloud edge | `#7788A8` (`#647597` / `#91A1BA`) | the ragged pale fade at every cloth hem: a painted gradient, the torn outline is geometry |
| 14 | Greaves & sabatons | `#2C303B` (`#121721` / `#49484D`) | dark navy plate, dE 6.8 from the suit (one family), faceted, pointed toes, gold edges |
| 15 | Greave glow | rim `#3E90C1` · hot `#5CC1E9` · core `#83EAFA` | EMISSIVE V-slots on the greaves and a thin line along the sabaton edges |

**Palette rule (the brief's instruction):** black, deep navy and storm-blue gradients for the large areas,
gold for thin trim, the ice cyan only as emissive accents. The P2 player cyan must not dominate the body.

## 5. Readability at 6 to 8 % of screen height, and against 400 enemies

See [`reports/stage0_readability.png`](reports/stage0_readability.png) (the coils masked out with
[`references/selene_concept_front_mask_nocoils.png`](references/selene_concept_front_mask_nocoils.png)). A 2D check:
the front cut out, shrunk to 65 / 86 px and pasted flat, not a render through the 55° camera.

**Survives at 65 to 86 px:** the pale head + hair + crown as a light knot at the top; the pale arm line; the
blue cloth fan and its ragged outline; the dark vertical core between the panels; the collar gem as one
cyan point. **Lost:** the face, the eyes, the shards' individual shapes, the gold filigree, the veins'
pattern (they read as a light blue haze on the arm), the claws.

Findings (CIELAB, `palette.json` checks, enemies.csv, game.ron):
1. **On empty floor her body core disappears, her cloth does not.** The bodysuit is +2.4 L\* over the
   concept ground and −1.4 to +9.8 L\* over the four biome grounds; the cloth is +11 to +45 L\*, the skin and
   hair about +60. The silhouette is carried by the cloth fan, the pale top and the ink outline, so the
   outline must also run round the dark core.
2. **The Hollow Spire is her worst biome.** Its ground `#1B1D36` is blue-violet: the deep cape is only
   dE 21 from it, its glow `#A9C8FF` is dE 15 from her veins, and its Stargazer swarm (`#6FB2FF`) is dE 16
   from her veins. In the panel-4 horde she is hardest to find there. Keep the cape's value steps (deep →
   pale) and the pale top strong; do not darken the pale cloth edges.
3. **Player 2's ring is her colour.** `#3FD8FF` is dE 8 from `#6FE3FF` and dE 5 from the collar gem. As P2 the
   ring and her glows merge into one cyan; as P1/P3/P4 her glows must not be read as the P2 ring. Rule: the
   cyan stays a few small points and thin lines (under about 5 % of her pixels), never a large area.
4. **In a horde she reads by shape more than colour.** 400 swarm tokens are round blobs; she is the only
   thin vertical figure with a ragged cloth fan. Her small radius (0.42) makes the crowd close in: the cloth
   is what stays visible between tokens.
5. **Small.** At 86 px she is as tall as Brax but half as wide once the capes close in (about a third
   narrower than the T-pose plate). The stage-1 in-game render checks the real camera.

## 6. What must survive the toon shader

* **Three value groups.** DARK: suit, leggings, sabatons, gauntlets (L\* 14-22). MID: gold (36), the cloth
  gradient (27 deep → 56 pale). LIGHT: skin and hair (72). EMISSIVE: eyes, gem, veins, greave glows (L\* 72+,
  cores near white). No ramp band or rim term may merge the deep cape into the suit.
* **The suit must not go flat black.** Paint the suit from the measured base `#1E252B` with lifted lit
  faces toward `#36435B` (the bust, the thigh fronts, the greave tops), keep the ramp's shadow band at or
  above about L\* 8.
* **The cloth gradient is painted, not lit.** Deep blue near the attachment, pale storm-cloud toward the
  torn hem, a few darker cloud blotches as in the concept. It must survive a flat toon ramp.
* **Emissive bypasses the ramp.** Veins, gem, eyes and greave glows are never multiplied by shadow or AO.
  Bloom may spread them, but they stay thin.
* **Shape from geometry, surface from texture.** Geometry: the bun, the six shards, the collar and gem, the
  bust shell, the shoulder bows, the hip plates and belt rings, the capes and panels with their ragged
  hem outlines, the greave plates, the pointed sabatons, the gauntlet cuffs and claw tips. Texture: the
  filigree, the veins, the cloud blotches, the leggings' seams.

## 7. How the kit should read, and open design questions

### 7.1 The kit at game scale (proposals)

| Moment | What the player must see at 86 px | Proposal |
|---|---|---|
| **Signature idle** | "Lightning in human shape, barely touching the ground" | A slow hovering sway (a few cm up and down, the cloth breathing), the crystal shards bobbing out of phase, small crackles on the arm veins (VFX + an emissive pulse) |
| **Arc Nova** (chain burst) | the cast point and the chains leaving her | Both hands snap forward and apart, fingers spread, the veins flare, the capes blow outward; a short (≈0.5 s) upper-body cast |
| **Blink** (teleport 7 m) | where she left and where she arrived | blink_out: a crouch-and-lean into the move, the body hidden at the peak (VFX storm trail); blink_in: an arrival pose with the cloth settling. Two short clips; the cloth held neutral at the cut |
| **Heaven's Verdict** (ultimate) | "she is calling the storm" | start: both arms raised overhead, head back, the crown shards spread wide; loop: a hover with arms raised, the cloth lifted by wind, the crown spinning slowly (the shard bones) |
| **Static Charge** (passive) | how charged she is | the veins and greave glows ramp with the charge (an emissive parameter); a build-up clip (a fist clench with a crackle) for when the charge is full |
| **Firing** (3.5 shots/s, Orb) | the aim | the thundercoil_launcher on the sockets; recoil procedural; a two-handed fire pose set in the upper layer |

### 7.2 Open design questions

| # | Question | Proposal used by this pack | Settled by |
|---|---|---|---|
| Q1 | How many crown shards? The concept draws **six** (three per side); the stage brief said five | Six, as drawn (the approved concept is the authority); separate rigid pieces on `head_top`-child bones so they can bob | the user / stage 2 |
| Q2 | Does she stand or hover? | Stand in the shared clips (the sabaton toe is the forefoot); hover only in the signature idle and the ultimate | the user |
| Q3 | Where do the outer capes attach? | At the shoulder bows (upper arm root), hanging behind the arms and down the back, not sewn to the arms; x_ cloth chains | side / back sheet or stage 2 |
| Q4 | What does the back look like? | The bodysuit is closed at the back with a gold filigree spine line; the bun is a simple wrapped knot; the capes cover the back of the legs | back sheet (optional) |
| Q5 | The floating coils | Not body; the thundercoil_launcher is her weapon; the coils could become a Thundercoil skin variant | the weapon track |
| Q6 | Claw tips | Short rigid claw caps on the fingertips of the gauntlet, skinned to the last phalanx | stage 2 |

## 8. Notes for stages 1 to 4

* **Stage 1 input.** The approved front as it is. The graph's birefnet mask keeps the whole figure on the
  dark navy ground (arms, claw tips, the ragged cloth, the crown shards, the pointed sabatons; checked
  2026-09-27, [`reports/blockout/input_maskcheck.png`](reports/blockout/input_maskcheck.png)). The coils are
  kept in the input: they float clear of the hands (a 40-70 px gap), so they cannot fuse into the fingers,
  and stage 2 drops them as separate components. The conditioning background stays neutral grey
  (`#808080`).
* **Stage 2 budget (15 to 25k tris).** A proposed split: body (suit, arms, head) 40 %, capes + panels +
  tabard 30 %, greaves + sabatons + gauntlets 15 %, hair + bun + crown + gem 15 %. Empty hands with
  fist-capable loops; the forearm under the gauntlet slim enough for any chassis. Separable parts for
  the skins (section 1).
* **Stage 3.** GF_Hero_v1 unchanged; per-hero extras: `x_crown_01..06` (children of `head_top`, one rigid
  shard each), cloth chains for the two capes, the two hip panels and the tabard (`x_cape_L/R_*`,
  `x_panel_L/R_*`, `x_tabard_*`).
* **Stage 4, Selene's unique clip set (proposal):** `selene_idle_signature@loop` (hover sway, crackles),
  `selene_arc_nova`, `selene_blink_out`, `selene_blink_in`, `selene_heavens_verdict_start`,
  `selene_heavens_verdict@loop`, `selene_static_charge` (build-up) and `selene_fire_charge` /
  launcher fire poses in the upper layer. Her locomotion uses the shared set baked on her proportions; at
  move speed 7.0 her stride is long and light, the cloth trailing.
