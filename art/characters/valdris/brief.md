# Valdris, The Anvil-Born: character brief (stage 0)

Sources: `content/sheets/characters.csv` row `valdris` · `assets/content/kits.ron` (VALDRIS block) ·
`content/sheets/chassis.csv` row `colossus_cannon` · the two approved concepts,
[`references/VALDRIS_sheet_turnaround.jpg`](references/VALDRIS_sheet_turnaround.jpg) (sheet, sha256 `d27bf5f3…7c17`)
and [`references/VALDRIS_front_approved.jpg`](references/VALDRIS_front_approved.jpg) (hero front, sha256 `55d018f3…2dfd`),
both the user's · the resolved front
[`references/valdris_concept_front_mirrored.png`](references/valdris_concept_front_mirrored.png) · measured colours in
[`palette.json`](palette.json) / [`color_script.png`](color_script.png) · the concept comparison in
[`reports/stage0_sheet_analysis.md`](reports/stage0_sheet_analysis.md) · the game-scale check in
[`reports/stage0_readability.png`](reports/stage0_readability.png).

**Design authority.** The two concepts disagree in places (17 findings, `reports/stage0_sheet_analysis.md`).
The resolution used everywhere in this pack: **cannon on his RIGHT arm, anvil chest plate kept**
(the orchestrator's default of 2026-09-25; the user may override it). The resolved front is the
hero front mirrored. "His right" always means the character's own right, which is the **left** of
a front-view image. Where this brief goes beyond the concepts (Siege Stance, Mountainfall, the
passive) it proposes, and the pending sheets or the user settle it.

## 1. Who he is (from content)

| | |
|---|---|
| Key / name | `valdris`: Valdris, *The Anvil-Born* |
| Role / phase | Juggernaut / Anchor · **P0: the default vertical-slice character.** He is in nearly every run and nearly every screenshot, so his look sets the roster's bar |
| Fantasy | "Walking siege engine. Slow, unkillable, hits like a collapsing temple." |
| Colour | `#C8A25A`, dE 8 from the concept's **lit** gold trim (`#CF9F66`): the kit colour is his gold |
| Stats | 320 HP · move 5.6 (the slowest) · 2 dash charges (1.2 s) · collision radius **0.55** (the largest) |
| Signature chassis | `colossus_cannon`: "Siege artillery for one. Shells burst on impact, knocking the horde back." Auto fire, 2.6 shots/s, Kinetic, style `Shell`, range 13, splash r 1.6, knockback 3.0 |
| Passive: Reforged Flesh | damage taken converts to Armor (50 %, up to 90, max 50 % mitigation); when the Armor breaks: a shockwave r 5.0 (60 damage, knockback 8) and a 3 s taunt, cooldown 6 s |
| Active 1: Bulwark Slam (9 s) | Leap 7 m in 0.45 s → Nova r 3.4, 70 damage, stun 1.2 s, knockback 7 → a forge **Barricade** 5 m long, 260 HP, 6 s, 1.8 m in front of him |
| Active 2: Siege Stance (14 s) | 6 s: **rooted**, fire rate ×2.2, damage taken ×0.6, **taunt** |
| Ultimate: Mountainfall | 8 s: **model scale ×1.8**, damage ×1.6, every shot explodes (r 2.4) as a **Boulder**, damage taken ×0.5, knockback ×1.5, and a ground pound every 1.1 s (r 4.5, 90 damage, knockback 6) |
| Co-op role | "Aggro anchor, protects forge moments, enables glass-cannon teammates." |
| Skins (content) | Anvil-Born (base) · Molten Oathkeeper · Last Bastion, all on the same rig |
| Voice (barks.csv) | "Stand behind me." "I keep being the wall." "Lift with your legs. I am heavy." The Smithshade reforges him harder after every death |

Consequences for the art:
* **Mountainfall scales him by 1.8.** At the proposed 2.3 m he becomes **4.1 m** (about 155 px at
  1080p) for 8 s. Muzzle flash, boulder shots and the ground pound ride sockets, not world
  offsets, and the textures must hold up at 1.8x on screen (texel density planned for the
  Mountainfall size, not the base size).
* **Three skins share one body.** Build the cannon, pauldrons, anvil plate, cape and fist gauntlet
  as separable parts so a skin swaps them without touching the body or its weights.
* **He fires constantly.** 2.6 shots/s, 5.7 shots/s in Siege Stance. The muzzle flash must be short
  and small, or he whites out the middle of every screenshot.
* **He is the taunt target.** Siege Stance and the passive pull the horde onto him, so he spends his
  life inside a crowd (section 5).

## 2. Silhouette pillars (priority order)

1. **A wide, low, top-heavy block with a flat top line.** The pauldron tops are level with his
   crown, so the head sits sunk between them and the silhouette's top is a flat bar. The pauldrons
   span **0.53** of his height, the arm line sits at **0.78** of his height and carries the widest
   mass (pauldrons + cannon + fist). The legs are short (crotch at **0.35**) and the stance wide
   (**0.52**). Read: a siege tower, a T on a trapezoid. From the 55° camera the **tops** of the
   pauldrons, the anvil and the cannon are what the player sees most: the brightest gold rims and
   the lightest plate faces belong there.
2. **The cannon dominates his right side.** Barrel about 0.31 m across (0.48 m with the top clamps
   and the under-bracket), about 0.65 m from the pauldron to the muzzle, **1.6x** as thick as the
   fist arm. The glowing muzzle is the hottest point on him and doubles as his aim read. The
   asymmetry is the identity: heavy right (cannon), lighter left (fist, the anvil's horn). In
   gameplay the cannon points forward, so from above its length reads along the aim; the breech
   clamps and gold bands on its **top** must read from the camera.
3. **The anvil chest plate.** A flat top face level with the arm line, 0.79 m wide (0.34 of his
   height), the horn pointing to **his left**, a waisted body and two feet above the belt. It is
   his centre mark. Keep its top face one value step lighter than the surrounding plate (measured
   highlight `#746C68` against the plate's `#312C27`); from 55° that face is a light bar across his
   chest.
4. **The red cape: the one cloth mass and the one saturated hue.** A trapezoid behind him that
   flares to 1.65 m at the hem (0.72 of his height), visible at both sides and between the legs,
   full at the back with a gold emblem. No swarm enemy's colour comes within dE 36 of it (section 5), so
   the red is his flag in every biome. Keep the mass solid: the tatters and holes live near the
   hem; holes high in the cape body (the sheet has some) would break the mass at game scale.
5. **The head is a small dark knot.** About 11 heads tall, sunk between the pauldrons, with an
   iron-grey braided beard resting on the anvil. The silhouette never relies on the head.

## 3. Proportions (measured on the resolved front, 819 px crown to sole)

Proposed in-game height **2.3 m** (the top of the roster range 2.0-2.3 m: he is the juggernaut;
the stage-1 track also normalises to 2.3 m; stage 3 sets the final value). 1 px = 2.81 mm.

| Measure | px | at 2.3 m | Note |
|---|---|---|---|
| Height, crown to sole | 819 | 2.30 m | Mountainfall: 4.14 m |
| Head, 2 x crown-to-eyes | ~74 | ~0.21 m | about 11 heads tall (the sheet: ~8.3, see §7.2 Q1) |
| Face width at the eyes | ~75 | ~0.21 m | |
| Pauldron span, outer to outer | 438 | 1.23 m | 0.53 H; tops level with the crown |
| Arm line (cannon axis) height | 639 | 1.79 m | 0.78 H |
| Cannon, pauldron to muzzle face | ~231 | ~0.65 m | replaces the forearm and hand |
| Cannon barrel diameter | ~111 | ~0.31 m | 0.48 m with clamps and bracket; bore ~0.17 m |
| Fist forearm diameter / fist height | ~105 / 83 | ~0.29 / 0.23 m | |
| Anvil plate, width x height | 282 x 160 | 0.79 x 0.45 m | top face at the arm line |
| Beard, width x length | ~100 x 110 | ~0.28 x 0.31 m | 5 braids |
| Hip tassets, outer | ~330 | ~0.93 m | |
| Crotch height | ~289 | ~0.81 m | 0.35 H |
| Stance, outer boot to outer boot | 428 | 1.20 m | 0.52 H; each boot ~0.41 m wide |
| Cape, widest (near the hem) | 588 | 1.65 m | hem ~0.26 m above the ground |
| Arm span, reference pose | 767 | 2.15 m | 0.94 H, arms level |
| Body depth (sheet side view) | — | ~0.60 m | ~0.95 m with the cape; boots ~0.67 m long |

These are the numbers the stage-1 blockout's front silhouette and the stage-2 mesh are checked
against. The collision radius (0.55 m, a 1.1 m circle) is narrower than the pauldrons (1.23 m):
the pauldrons overhang his collider, which is what makes him look like a wall.

## 4. Materials and callouts

The numbers refer to the swatches in `color_script.png` / `palette.json`. **Two sources per colour:**
the sheet's own colour script declares four hexes (the authority for the NPR base colours), and the
measured tones record how the paintings shade them. The paintings are darker than the labels: paint
the textures from the declared values and let the toon ramp shade them.

| # | Material | Declared (sheet) | Measured base (shadow / highlight) | Construction and shader notes |
|---|---|---|---|---|
| 1 | Gunmetal plate | **Gunmetal Black `#2A242E`** (painted chip `#1A1A1A`) | `#312C27` (`#1E1A17` / `#6F6862`) | The whole shell: thick faceted plates with a cracked surface, gold-rimmed edges. Plate shapes and bevels are geometry; the fine cracks are texture. The declared hex is cool (violet-grey); the painting reads warm because of the forge light. Keep the albedo cool and let the lighting warm it |
| 2 | Anvil chest plate | (same iron) | `#2A2624` (`#1F1C1A` / `#746C68`) | dE 3.6 from the plate: **one material**. Its flat top face is the lightest plate face on him |
| 3 | Siege-cannon steel | (same iron) | `#47403A` (`#201C18` / `#928579`) | dE 9 from the plate, all of it lighting (the barrel is round and catches light): **one material** |
| 4 | Forge-gold trim | **Forge Gold `#FFC24B`** (chip `#DAA537`) | `#7C5931` (`#583F23` / `#CF9F66`) | Plate rims, the three cannon bands, the two fist cuffs, the braid rings, the faulds trim. Painted-metal NPR: flat base plus a hand-painted highlight band, no PBR reflections. The measured base is the gold in shadow; the lit trim `#CF9F66` is the kit colour (dE 8) |
| 5 | Glowing seams | **Ember Amber `#FF6B1A`** (chip `#B1311B`) + **white-hot core** (painted `#FFF5CE`) | rim `#BB6A26` · hot `#C78549` · core `#F8AA5D` | EMISSIVE, unlit, bloom. The grooves between plates, the anvil flanks, the knees, the pauldron slots. Intensity is a runtime parameter (section 7). The label is redder and hotter than the painted seams; use the label for the hot tone and white-hot for the core |
| 6 | Cannon muzzle | (Ember Amber → white-hot) | rim `#A54011` · hot `#E8741C` · core `#FFF097` | EMISSIVE: the bore and the inner ring. The hottest point on him |
| 7 | War-red cape | **Deep War Red `#7A1F1F`** (chip `#6C0E08`) | `#401B19` (`#250D0C` / `#5D2B28`) | Heavy cloth, tattered hem, holes near the hem only (pillar 4). Also the red cloth behind the faulds and the collar. The measured red is darker than the label: paint from the label |
| 8 | Skin | — | `#7C5A4A` (`#493126` / `#C69D88`) | Weathered; cracked scars across the scalp and forehead (texture, faintly ember: see §7 Reforged Flesh). Warm shadows, never grey |
| 9 | Braided beard | — | `#48413C` (`#2C2722` / `#79716A`) | Iron-grey, five thick braids; model the beard as one mass with five braid lobes. The braid caps are steel (material 1) with gold rings (material 4) |
| 10 | Cape emblem | (Forge Gold) | `#A57741` (`#7B5020` / `#D5A76F`) | Measured on the sheet's back view. The same gold as the trim (dE 15 is lighting). A texture on the cape, not geometry |
| 11 | Eyes | — | not measurable (about 8 px on the concept) | Ember glow, emissive texture; 1 px at game scale |

**Lighting (the sheet's note):** a forge key light from below-left and a cool steel rim from
above-right. The game's lighting is fixed (ARCHITECTURE §7: a warm key against a cool fill), so this
becomes shader intent: warm, hue-shifted shadows; a cool rim term on the top-right edges; the seams
as the "forge light from below".

## 5. Readability at 6 to 8 % of screen height, and against 400 enemies

See [`reports/stage0_readability.png`](reports/stage0_readability.png). This is a 2D check: the
resolved front cut out with the birefnet mask, shrunk to 65 and 86 px and pasted flat; not a render
through the 55° camera. Panel 4 puts him (86 px) inside **400 swarm enemies** per biome, drawn from
`enemies.csv` (colour, radius x scale, shape), non-overlapping at their collision radii, 55 % of them
crowding him (he taunts), 1:1 crops of a 1920x1080 frame.

**Survives at 65 to 86 px:** the flat top bar of the pauldrons; the cannon block and its glowing
muzzle on his right; the fist on his left; the anvil's top edge as a light bar; the gold rims as
broken bright lines; the red cape trapezoid; the seams as a scatter of ember points.
**Lost at 65 to 86 px:** the face, eyes, beard braids, rivets, fine cracks, the emblem's shape, the
scalp scar and the breech details. Those are close-up detail (character select, codex, Mountainfall).

Findings, measured in CIELAB (`palette.json` checks and the enemy colours):
1. **In a horde he is the dark mass.** Every swarm enemy in the game is L\* 44 to 97. His plate is
   L\* 18, his cape L\* 15. In all four biomes he reads as a dark, wide, angular block among bright
   round tokens (panel 4, value row). **The darkness is his pop. Do not brighten the armour to make
   it "read as metal".** Keep the lit faces lifted (highlight tone) only enough for the facets.
2. **On empty floor he is dark on dark.** Against the biome grounds (unlit albedo, worst case) the
   plate is only +3 to +14 L\* and the cape −0.4 to +11 L\*. What carries him there: the gold rims
   (+25 to +36 L\*), the seams (+46 to +57), the muzzle, the inverted-hull ink outline and a rim
   term. **The gold trim is load-bearing:** keep it on every plate edge the camera sees, at every LOD.
3. **His glow does not identify him in the Cinder Wastes.** Ember Amber `#FF6B1A` is dE 8 from the
   Kindlejack (`#FF7A1A`) and dE 16 from the Cinderling (`#E0662B`); his muzzle is dE 9 / 11 from
   them. There the seams and muzzle separate by shape (thin lines and one point on a dark block, not
   solid blobs), so the seams must stay thin and the plate between them dark.
4. **The cape red is unique.** The nearest swarm enemy is dE 36 from the measured cape; the only
   close colour in the game is the Slag King boss (`#6B2A14`, dE 12 from Deep War Red). The cape is
   his colour flag, the one thing that says "Valdris" at a glance in a four-player crowd.
5. **Gold is shared with the UI.** The P1 ground ring (`#FFC940`, `game.ron`) is dE 7 from Forge
   Gold, and Radiant elements and Godforged loot are gold too (ARCHITECTURE §7). As P1 his ring and
   trim reinforce each other; as P2-P4 the ring colour differs, and his gold trim must not be
   mistaken for loot: keep the trim as thin rims, never as large gold areas.
6. **Size is his other read.** At 86 px he stands about 2.7x the height of a Cinderling token and
   is wider than any swarm enemy (the T-pose plate flatters him: a gameplay pose with the cannon
   forward loses about a third of the width; stage 1 renders the real camera).
7. **The 55° camera shows the tops.** The anvil's top face, the pauldron tops and the cannon's top
   are the largest surfaces the camera sees. The front faces foreshorten. Put the value contrast
   (gold rims, lighter top faces) on the tops.

## 6. What must survive the toon shader

* **Three value groups.** DARK is plate L\* 15-18, anvil 16, cape 15, cannon 28, beard 28. MID is
  gold 41-68 and skin 41. EMISSIVE is the seams and the muzzle (L\* 61 and up, cores near white).
  No ramp band, rim term or bloom may merge the gold into the plate.
* **The painting is 42 % near-black. The game model must not be.** The concept's plates sit in deep
  shadow (L\* < 8). The NPR version uses the declared Gunmetal `#2A242E` (L\* 15) as albedo, keeps
  the ramp's shadow band at or above about L\* 8 and lifts the lit faces to the plate highlight
  (`#6F6862`, L\* 44), so every facet stays visible under the outline.
* **Cape and plate have the same value** (L\* 15). They separate by hue alone, and the gold rim
  between them. A ramp that desaturates shadows turns him into one black shape: keep shadows
  saturated and warm (the measured shadows shift to warm brown, never grey).
* **Emissive bypasses the ramp.** Seams, muzzle, eyes and the scalp cracks are never multiplied by
  shadow or AO. Bloom may spread them; nothing else blooms.
* **Shape from geometry, surface from texture.** The plate silhouettes, pauldron blocks, anvil,
  cannon bands, faulds, boots and the cape's hem outline are geometry. The cracks, rivets, emblem,
  scars and braid texture are texture.
* **Outline at block scale.** Tune the ink outline so the pauldrons, cannon and anvil read as big
  blocks; an outline around every plate turns him to noise at 86 px.

## 7. How the kit should read, and open design questions

### 7.1 The kit at game scale (proposals; the pending sheets and the user settle them)

| Moment | What the player must see at 86 px (155 px in Mountainfall) | Proposal |
|---|---|---|
| **Siege Stance** (6 s, rooted, fire ×2.2, taunt) | "He has planted and is now a turret": a change of pose, of glow and on the ground | Pose: wide braced stance, knees bent, the fist arm bracing under the cannon, the cannon locked forward. Glow: the seams step up from ember to gold-white and the pauldron slots vent heat. Ground: a gold-rimmed forge-glyph decal under him (player-side zones are gold-rimmed) and two anchor spikes that fold down from each sabaton (rigid parts, one bone each, hidden in the normal pose). The taunt reads from the horde turning to him, not from a UI icon. The muzzle flash stays small at 5.7 shots/s |
| **Mountainfall** (8 s, ×1.8, boulder shots, ground pounds) | "A colossal anvil-avatar": bigger, hotter, heavier; every shot a boulder, every 1.1 s a ground pound | The same mesh at 1.8x with a material state: the seams widen to white-hot, the plates darken to a black crust between them, the anvil plate glows at its edges; molten drips from the cannon. VFX: boulder shells (rock, not energy), a ground-pound ring every 1.1 s. Optional geometry: a rock crust shell over the pauldrons (a skinnable part). The **Mountainfall concept** sheet (prompt ready) decides the avatar's look |
| **Reforged Flesh** (damage → Armor; break → shockwave + taunt) | How much Armor he has, and the moment it breaks | Armor drives the seams' intensity (dim ember at 0, bright gold-white at max 90) and the scalp cracks. The break: the seams flash, plate-shard VFX and a shockwave ring (r 5.0), then the seams drop to dim ember. Never fully dark (the seams are part of his silhouette on dark floors) |
| **Bulwark Slam** (leap 7 m, stun, barricade) | The leap arc, the landing and a wall appearing | A heavy two-arm overhead leap and a cannon-first landing. The **forge barricade** is a separate prop: a 5 m wall of the same anvil-iron plates with gold rims and ember seams, so it reads as "his" |
| **Firing** (2.6 shots/s, Shell) | The aim direction and the shells | Recoil stays procedural. The shell is a dark slug with an ember trail; its burst is Kinetic bone-brass (the element hue), knockback dust, never white |

### 7.2 Open design questions

| # | Question | Proposal used by this pack | Settled by |
|---|---|---|---|
| Q1 | Head size: the hero front (~11 heads, sunk between the pauldrons) or the sheet (~8.3 heads, half a head above them)? | The hero front (it is the TRELLIS input and gives the flat top line) | **the user** |
| Q2 | How does the cannon mount on the arm (breech, straps, the elbow)? | The forearm sits inside the cannon; the breech housing covers the elbow; no hand | weapon sheet |
| Q3 | Weapon side and anvil plate | Cannon on his RIGHT, anvil kept (orchestrator default) | the user may override |
| Q4 | What is the cape emblem? | Keep the sheet's gold blade-with-branches sigil; a detail sheet can refine it (it may become the Sigil of the Anvilheart) | cape emblem sheet |
| Q5 | What does the Mountainfall avatar look like? | §7.1 | Mountainfall concept sheet |
| Q6 | Siege Stance anchor spikes: geometry or VFX only? | Geometry (rigid, one bone each), hidden in the normal pose | stage 2/3 |
| Q7 | Where are the cape and braids driven? | Short bone chains on the master skeleton's per-character extras (`x_cape_*`, `x_beard_*`), spring motion at runtime | stage 3 |

## 8. Notes for stages 1 to 4

* **Stage 1 input.** `references/valdris_concept_front_mirrored.png` (the resolved front). Its
  background is a near-black radial gradient (RGB 12 at the corners to about 30 behind him), so a
  flat-colour cut-out fails; the graph's birefnet mask keeps the full cape tatters, cannon and fist
  (checked 2026-09-25, `references/valdris_concept_front_mirrored_mask.png`). The conditioning
  background stays neutral grey (`#808080`), as for Brax.
* **Stage 2 budget (about 15 to 25k tris).** A proposed split: cannon 25 %, pauldrons + anvil
  25 %, body and legs 25 %, cape 15 %, head, beard and fist 10 %. Separable parts for the skins:
  cannon, pauldrons, anvil plate, cape, fist gauntlet. Texel density planned for the Mountainfall
  size (1.8x).
* **Stage 3.** On GF_Hero_v1: the cannon is rigid on `lowerarm_R` (the right hand's bones exist and
  stay unweighted inside it); `weapon_socket_R` sits at the muzzle. The left hand is a normal
  five-finger gauntlet. The pauldrons are rigid on the clavicle/upper-arm pair and must not clip the
  head when the arms rise for the Bulwark Slam leap. The anvil plate is rigid on `spine_03`.
* **Stage 4, Valdris's unique clip set (proposal, 10 clips):** `valdris_idle_signature@loop` (heavy
  breathing, heat venting from the pauldron slots, the fist flexing), `valdris_bulwark_slam_leap`,
  `valdris_bulwark_slam_land`, `valdris_siege_stance_enter`, `valdris_siege_stance@loop` (braced;
  firing stays procedural recoil), `valdris_siege_stance_exit`, `valdris_mountainfall_start`,
  `valdris_mountainfall_idle@loop`, `valdris_mountainfall_pound` (every 1.1 s, additive upper body)
  and `valdris_armor_break` (the Reforged Flesh shockwave, an additive roar). His locomotion uses the
  shared set baked on his proportions; at move speed 5.6 his stride must look heavy, not slow.
