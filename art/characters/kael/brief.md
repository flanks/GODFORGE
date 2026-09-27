# Kael, The Wraithshot: character brief (stage 0)

Sources: `content/sheets/characters.csv` row `kael` · `assets/content/kits.ron` (KAEL block) ·
`content/sheets/chassis.csv` row `serpent_smg` + `assets/models/weapons/serpent_smg.meta.json` · the approved front
concept [`references/KAEL_front_approved.png`](references/KAEL_front_approved.png) (the user's file
`docs/media/playable_characters/KAEL, THE WRAITHSHOT.png`, copied verbatim, sha256 `237a8187…4dce6`) · measured colours
in [`palette.json`](palette.json) / [`color_script.png`](color_script.png) · game-scale check in
[`reports/stage0_readability.png`](reports/stage0_readability.png).

The approved front concept is the design authority. Where this brief goes beyond it (the back, the sides, the
lighting states) it proposes; the optional sheets in [`turnaround_prompts.md`](turnaround_prompts.md) would settle
it with the user.

## 1. Who he is (from content)

| | |
|---|---|
| Key / name | `kael`: Kael, *The Wraithshot* |
| Role / phase | Agile Duelist / Crit · P1 |
| Fantasy | "Ghost gunslinger. Never stops moving, never misses twice." |
| Colour | `#9A7CFF` (a light lilac). It is the UI colour, not a model colour: the coat's lit violet (`#332930`) is dE 80 away. It sits dE 14 from the P3 player-ring violet `#B06CFF`, which is a UI concern, not an art one |
| Stats | 220 HP · move 7.2 (the fastest so far: Brax 6.2) · **3 dash charges** (0.9 s) · collision radius 0.44 |
| Signature chassis | `serpent_smg`: "A hissing stream of needles", Auto, Kinetic, one-handed, rapid. Already built as `assets/models/weapons/serpent_smg.glb` (2,330 tris, grip frame = palm centre) |
| Passive: Ghost Step | each kill grants crit chance (2 %, max 30 %, decays 4 %/s) and a 35 % chance to refund a dash |
| Active 1: Fan of Blades (5 s) | a spectral shotgun burst: Cone 6.5 m, 70°, 45 damage, applies Mark (crits on Marked below 15 % HP execute) |
| Active 2: Shadow Roll (6 s) | Rush 5 m in 0.22 s with i-frames, then the next 3 shots pierce (×1.25 damage) |
| Ultimate: Bullet Ballet (6 s) | infinite dash, fire rate ×1.5, +1 projectile, **twin spectral pistols** copying the current Mechanism |
| Co-op role | flanker, elite hunter, mobile reviver |
| Skins (content) | Wraithshot (base) · Midnight Duelist · Grave Dancer, all on the same rig |

Consequences for the art:
* **He is always moving.** Move 7.2, three dashes, a roll and an ultimate of infinite dashes: the run, the dash and
  the roll are his most-seen poses, so the coat's silhouette **in motion** (trailing, flaring) matters more than its
  T-pose shape. The coat and its ghost-flame tatters must ride `x_` cloth chains (stage 3).
* **One gun in the hand, a ghost gun in the other.** `serpent_smg` is one-handed and rides `weapon_R`. The concept's
  second revolver becomes the Bullet Ballet **spectral twin** on `weapon_L`: a VFX / emissive copy of the current
  chassis, not a body part. Both hands are **empty** on the body mesh (weapons decision, section 7).
* **The ghost arm is his identity.** His left arm is spectral (section 4). Fan of Blades, the ghost-twin pistol and
  the Ghost Step dash should all emit from that arm's green, so his VFX and his body share one colour.

## 2. Silhouette pillars (priority order)

1. **The long, flared duster.** From the high collar to a ragged hem at mid-shin, flaring from 0.45 m at the waist
   to about 1.0 m at 40 % of his height and 1.2 m at the tatter tips. It is the biggest and darkest mass and the
   thing that moves. The hem is torn into long points; a few of them turn into **ghost-flame tatters**: chunky,
   emissive, spectral-green cloth points (section 4, swatch 12), not particles and not smoke.
2. **One glowing arm.** His left arm below the rolled sleeve (image right) is translucent ghost flesh, emissive
   mint-green from the bicep strap to the fingertips. At 65-86 px it is the brightest thing on him and the only
   cool light: it is how a player finds Kael in a horde (section 5). Keep it a proper, full-size arm for rigging.
3. **Lean and tall.** About 7.9 heads, narrow shoulders under the coat (the coat's shoulder line about 0.68 m
   with the collar points), a narrow waist (0.45 m), long legs in dark trousers and tall buckled boots. The
   opposite of Brax's X and Valdris's block: a vertical dark line with a flared skirt.
4. **High collar + swept hair.** The collar's two points frame the head; the dark hair sweeps up and back with a
   light streak over the glowing side of the face. From the 55° camera the collar and hair are what show of the head.

## 3. Proportions (measured on the concept, 972 px crown to sole)

At the proposed in-game height of **2.1 m** (roster range 2.0 to 2.3 m; lean, smaller than Brax's 2.2 and Valdris's
2.3 m; stage 3 sets the final value), 1 px = 2.16 mm. Measured on the stage-1 cut-out without the revolvers
(`references/kael_concept_front_nogun_mask.png`).

| Measure | px | at 2.1 m | Note |
|---|---|---|---|
| Height, crown (hair) to sole | 972 | 2.10 m | the swept hair adds about 3 cm |
| Crown to chin (beard tip) | ~123 | ~0.27 m | about 7.9 heads tall |
| Head width at the eyes (with hair) | 82-91 | 0.18-0.20 m | |
| Coat shoulder line with collar points (85 % height) | 316 | 0.68 m | the collar points stand about 3 cm above the shoulders |
| Chest in the open coat (72 % height) | 231 | 0.50 m | |
| Waist / belt (68 % / 65 % height) | 208 / 230 | 0.45 / 0.50 m | |
| Coat flare at 51 % / 41 % / 31 % height | 388 / 467 / 561 | 0.84 / 1.01 / 1.21 m | the 31 % row is the tatter tips |
| Coat hem, lowest points | | 20-25 % height | mid-shin; the maroon loin cloth reaches 27 % |
| Sleeve thickness (upper arm, coat) | ~55 | ~0.12 m | the ghost forearm is bare and slimmer, about 0.09 m |
| Stance, outer boot to outer boot | 390 | 0.84 m | T-pose reference stance |
| Arm span, fist to fist (T-pose, no guns) | 952 | 2.06 m | 0.98 x height |

## 4. Materials and callouts

The numbers refer to the swatches in `color_script.png` / `palette.json`. Hex values are the measured *base* tones
(emissives: *hot*); shadow and highlight tones are in the JSON.

| # | Material | Base | Finish / construction | Shader and texture notes |
|---|---|---|---|---|
| 1 | Violet duster coat | `#241B24` (hl `#332930`) | long heavy duster, high collar with two points, wide lapels, rolled cuffs, tattered hem with long points | Keep the violet: a hue, not a value. Lit faces lift toward `#332930`; the worn edge trim is bronze (6). The hem points carry the ghost flame (12) |
| 2 | Maroon loin cloth | `#36242F` | torn cloth hanging from the belt to mid-shin between the legs | dE 7 from the coat: one cloth family, a touch redder |
| 3 | Black shirt & trousers | `#242328` | shirt and scarf at the collar, trousers, the right hand's fingerless glove | Near-black, slightly cool. Stitching and seams are texture only |
| 4 | Worn brown leather | `#402A25` (hl `#5D4235`) | two belts (the lower one slung), long holster on his right thigh, a pouch on his left hip, thigh straps, bracer on the right forearm, strap on the left bicep | The warm mid accent. Painted wear on the edges |
| 5 | Boots | `#43322F` | tall boots with overlapping strap plates, knee cuffs, buckles | dE 4.5 from the belts: one leather, the boots darker |
| 6 | Bronze buckles & cartridges | `#886F59` (hl `#BA9979`) | the belt buckle ring, strap buckles, the cartridge caps of the bandolier, the coat's worn edge trim | Painted-metal NPR: a painted highlight band, no PBR reflections |
| 7 | Skin | `#937160` | tanned face and neck; the right hand's fingers out of the glove | Warm hue-shifted shadow `#59413B`. A scar over the right brow |
| 8 | Hair & stubble | `#211D1D` | dark hair swept up and back, a light grey streak over the glowing side; short beard on the chin, stubble | One mass; the streak is texture |
| 9 | Spectral arm | hot `#80B290` (rim `#517B65`, core `#B1DEBA`) | his LEFT forearm and hand, bare below the rolled sleeve and the bicep strap, veined ghost flesh | EMISSIVE, unlit. A proper arm (full size, the same topology as the right) so it rigs like any arm |
| 10 | Eye & face glow | hot `#75AA88` (core `#9CD0AE`) | the glowing left eye; green veins creeping from the eye over the left temple and cheek | Emissive texture on the face; 1-2 px at game size |
| 11 | Ghost gem buckle | hot `#7BAB8E` | the gem in the belt buckle and the collar pin | A small bright centre mark |
| 12 | Ghost-flame wisps | hot `#476F61` (as painted: translucent over the navy) | spectral flame rising off the coat hem | Built as **4 to 6 chunky emissive cloth tatters** on the hem, skinned to cloth helper bones; take the colour from the arm's tones (9), not from this translucent measurement |

**The ghost green (user direction).** The concept paints a desaturated sage-mint (`#80B290`), well clear of the P4
player-ring green `#5BE37D` (dE 46) and of the P2 cyan `#3FD8FF` (dE 44). The emissive map may push it brighter
toward the requested `#7CFFB0`-ish mint, but **lean teal-mint, not grass-green**, and use it for emissive accents
only (the arm, the eye, the gem, the tatters): P4's ring must never be mistaken for Kael's glow. Its distance to
the Verdant Ruin biome glow `#5CF2B0` is the smallest of the four biomes (dE 37): the green-mint swarm there is the
one place the arm competes (section 5).

## 5. Readability at 6 to 8 % of screen height

See [`reports/stage0_readability.png`](reports/stage0_readability.png): the stage-1 cut-out (no revolvers, no diffuse
smoke) at 65 and 86 px, on each biome's ground, pasted into a client frame, and in a horde of 400 swarm enemies per
biome. This is a 2D check, not a render through the 55° camera (stage 1 does that).

**Survives at 65 to 86 px:** the ghost arm (a bright mint bar on one side), the dark flared coat as a triangle, the
two legs and boots below the hem, a warm fleck at the belt. **Lost:** the face, the eye glow, the bandolier, the
buckles, the holster, the stitching, the maroon of the loin cloth. Those are close-up detail for character select
and the codex.

Findings (CIELAB, `palette.json` checks):
1. **He is almost all dark.** The coat is L\* 11, the black cloth L\* 14, the leather L\* 20: on The Hollow Spire and
   The Unmaking grounds the coat is within ±7 L\* of the floor, and on Cinder Wastes it is level with it. In the horde
   panels his body disappears between the tokens on three of four biomes and **the ghost arm alone carries him**.
   Therefore: the ghost arm's emissive must never go dark (not in any state), the ink outline and the ground ring are
   load-bearing, and the toon ramp must lift the coat's lit faces to the highlight tone (`#332930` and above).
2. **The arm is on one side.** Turned with the left side away from the camera, he loses his light. The 4-6 ghost-flame
   tatters on the hem give him a second, symmetric glow low on the silhouette; the gem buckle is a third, small mark.
3. **Verdant Ruin.** The mint-green swarm and the biome glow `#5CF2B0` sit closest to his ghost green (dE 37). On
   that biome he reads by the arm's shape and the dark coat against the bright tokens, not by hue.
4. **The T-pose flatters him.** Arms out, the ghost arm is a 0.9 m bar; with the SMG raised in the right hand and the
   left arm bent, it shrinks to a short bright block. The coat's flare also collapses when he stands still: the
   gameplay idle should keep a wide stance and the coat hanging open.
5. **From 55°** the tops of the collar, the shoulders, the hair and the coat's back dominate; the bandolier and the
   belt foreshorten. The back of the coat (not shown in the concept) is what the camera sees most: see section 7.

## 6. What must survive the toon shader

* **Three value groups.** DARK is the coat L\* 11, hair 11, black cloth 14, maroon 17, leather 20, boots 23. MID is
  bronze 49 and skin 50. EMISSIVE is the ghost green (L\* 44-68 as painted, brighter in the emissive map). No ramp band
  or rim term may merge the DARK group into one blob: keep the coat's lit faces and the leather visibly apart.
* **Emissive bypasses the ramp.** The ghost arm, the eye and face glow, the gem and the ghost-flame tatters are
  never multiplied by shadow or AO. Bloom may spread them; nothing else blooms.
* **Warm shadows on the warm materials, cool on the coat.** The skin's shadow shifts toward red (`#59413B`), the
  coat's toward blue-violet (`#131118`). A ramp that greys its shadows kills the violet.
* **Shape from geometry, surface from texture.** The collar, lapels, cuffs, the hem's points and tatters, the belts,
  the holster, the boots' strap plates and the bandolier's volume are geometry. Stitching, wear, the veins in the
  ghost arm, the cartridge caps and the scar are texture.

## 7. Open design questions and decisions

| Question | Proposal (the user may override) | Settled by |
|---|---|---|
| Which arm is spectral? | **His LEFT arm** (image right), exactly as the approved concept draws it; the glowing eye and the face glow are on the same side. The task text's "right arm" / "right side of the face" describe the picture as seen, so the concept is fed as painted, **not mirrored**. His right hand (black fingerless glove, the long thigh holster on that side) is the gun hand: `serpent_smg` rides `weapon_R`. Mirroring stays a one-line change at stage 1 if the user wants the ghost arm on his right | status.json `decisions[ghost_arm_side]` |
| What is on his back? | The duster's back is one dark violet panel with a centre vent from the waist, the hem torn into long points with 2 of the ghost-flame tatters at the back; the collar stands up at the back of the neck; the belts continue round; no emblem | back view (optional sheet) |
| How many ghost-flame tatters, and where? | 4 to 6 chunky emissive cloth points at the hem (2 at each front corner, 1-2 at the back), each a short `x_` chain; the smoke in the concept is VFX, not mesh | stage 2 / 3 |
| What does Bullet Ballet look like? | The ghost arm and the tatters flare to their core tone; a spectral copy of the current chassis appears on `weapon_L` (emissive, semi-transparent, VFX); ghost afterimages on each dash | colour script (optional) |
| His face? | A faint knowing smirk, a scar over the right brow, stubble and a short chin beard, the glowing left eye | expression sheet (optional) |

### Weapons decision (2026-09-25, the user)

Weapons are **not part of hero bodies**: every chassis weapon is its own model, attached to the hand sockets.

* **Kael's body** has **empty hands**: his right hand in a black fingerless glove (skin fingers), his left hand the
  ghost hand; both with fist-capable finger loops, like Brax's.
* **The concept's two serpent revolvers are weapons** and are removed: from the stage-1 input (cut out of the
  silhouette, section 8) and from every later stage. The shipped chassis `serpent_smg` rides `weapon_R`; the
  Bullet Ballet twin is a VFX copy on `weapon_L`.
* Budgets: the body set 15 to 25k tris (the weapon is separate).

## 8. Notes for stages 1 to 4

* **Stage 1 input.** The birefnet mask keeps the whole figure but also the revolvers (collinear with the arms, the
  grips inside the fists: TRELLIS.2 would grow one arm-gun tube) and the whole translucent ghost smoke, with the
  navy showing through its holes (TRELLIS.2 would build wide opaque fins round the coat). The stage-1 input is
  therefore the verbatim concept with an edited alpha:
  [`references/kael_concept_front_nogun.png`](references/kael_concept_front_nogun.png), made by
  `tools/blender/gf_hero/kael_stage1_input.py` (the concept's own pixels, no repainting; the fists kept, the guns
  and the diffuse smoke cut away), fed with `--own-mask`. Details in `reports/blockout_report.md`.
* **Stage 2.** A MakeHuman hm08 body (lean, 2.1 m) in the shared chain; the ghost arm is a zone of the body with an
  emissive material region, the same topology as the right arm; the coat is a separate cloth part (collar, lapels,
  sleeves, a skirt split at the front and back vent, torn hem points), plus the loin cloth, the belts, holster,
  pouch, bandolier, bracer, boots and hair shells; the ghost-flame tatters are separate emissive cloth points on the
  hem.
* **Stage 3.** GF_Hero_v1; the coat skirt on `x_coat_*` chains (front L/R, side L/R, back), the loin cloth on a short
  chain, each ghost-flame tatter on a 2-3 bone `x_wisp_*` chain; the holster rigid on the right thigh.
* **Stage 4, Kael's unique clip set (proposal, 8 clips):** `kael_idle_signature@loop` (the gunslinger twirl: the
  SMG spun round the trigger finger and caught), `kael_fan_of_blades` (a fanning sweep of the ghost hand across the
  SMG's hammer, the spectral burst on the strike event), `kael_shadow_roll` (a low forward roll, 0.22 s of travel
  plus recovery, the coat wrapping), `kael_bullet_ballet_start`, `kael_bullet_ballet@loop` (twin-pistol stance, both
  arms raised, weight on the balls of the feet), `kael_ghost_step` (the dash variant: a low lean with the coat
  streaming and the ghost arm trailing), `kael_fire_r` and `kael_fire_twin` (short upper-layer fire poses: one gun,
  and both arms raised for the Bullet Ballet twin). Weapon fire itself stays procedural (recoil, aim).
