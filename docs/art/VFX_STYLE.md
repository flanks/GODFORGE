# GODFORGE: combat VFX style and effect catalog

This page is the art direction and the complete catalog for every combat effect in GODFORGE. It
replaces the greybox language that ships today: glowing stretched spheres for projectiles, flat
rings and discs for explosions, one `Particle` entity per mote. The target is Hades II-grade combat
VFX: bold graphic shapes, ink and light, punchy impact frames, stylized smears, and an element you
can name at a glance. All of it must stay readable with 4 players and 400 enemies on screen.

The rules come first (sections 1-5). The catalog follows (sections 6-19), then the budgets
(section 20), the Bevy 0.20 tech plan (section 21), the asset list (section 22) and the build order
(section 23).

Ten concept frames show the language painted over real in-game captures. They live in
[`vfx_concepts/`](vfx_concepts/), and the painter that made them is in
[`vfx_concepts/src/`](vfx_concepts/src/). Every frame is painted at game scale, meaning the
fixed 55° orthographic camera at 32-41 px/m. Some frames add a zoomed detail inset.

| # | Frame | Shows |
|---|---|---|
| 01 | [colossus_shell_impact](vfx_concepts/01_colossus_shell_impact.png) | muzzle, shell body, smoke trail, layered burst, plus the impact anatomy filmstrip at 60 fps |
| 02 | [serpent_smg_needle_stream](vfx_concepts/02_serpent_smg_needle_stream.png) | a rapid stream as one stitched line, casings, tick-spark hits |
| 03 | [thundercoil_orb_chain](vfx_concepts/03_thundercoil_orb_chain.png) | coiled orb, angular storm impact, Lichtenberg scorch, chain hops |
| 04 | [wraith_bow_charged_arrow](vfx_concepts/04_wraith_bow_charged_arrow.png) | charge anticipation, a void hex-bolt with a ghost trail, pierce wounds |
| 05 | [gauntlet_punch_combo](vfx_concepts/05_gauntlet_punch_combo.png) | melee smears, a finisher, a contact star, a telegraph kept on top |
| 06 | [sunspike_spread_burst](vfx_concepts/06_sunspike_spread_burst.png) | sunburst wedge muzzle, pellet fan, cross-glint hits |
| 07 | [firestorm_synergy](vfx_concepts/07_firestorm_synergy.png) | a synergy set-piece: a flame rim, a spiral storm, strikes |
| 08 | [mountainfall_ground_pound](vfx_concepts/08_mountainfall_ground_pound.png) | an ultimate: molten gashes, a dust wall, a boulder shot, the boss telegraph on top |
| 09 | [unmade_death_shatter](vfx_concepts/09_unmade_death_shatter.png) | four swarm deaths at four ages, kill motes flying to the killer |
| 10 | [crit_precision_hits](vfx_concepts/10_crit_precision_hits.png) | crit, precision and plain-hit punctuation on a boss |

---

## 1. Pillars

1. **Shape first, glow second.** Every effect is a bold, flat, graphic shape: a smear, a slash, a
   star, a shard, a tongue of flame. Glow and bloom only finish the shape. They never replace it.
   If an effect still reads when you turn bloom off, it is right.
2. **Ink under light.** Every bright shape sits on a dark ink shape that is a little bigger and a
   little behind it. The ink is the element's darkest tone, never pure black. Ink is what makes a
   gold spark read on a molten floor and a cyan bolt read on green grass (frames 01, 03).
3. **Fast in, slow out.** Impacts peak within 2-4 frames. They hold one "impact frame" (a white
   star on ink), collapse by frame 14, then dissipate gracefully: smoke lifts and thins, sparks
   fall, decals fade. Nothing fades in.
4. **One element, one silhouette.** Each element owns a shape vocabulary, a five-tone ramp, a
   motion and a secondary particle (section 4). Hue is the last clue, not the first: four of the six
   element hues sit close to a player colour (section 3.4).
5. **Tell the truth about size.** A burst covers exactly its gameplay radius. Smoke may overshoot
   by 20 % but stays dim. An effect that looks bigger or smaller than its damage area is a
   readability bug.
6. **Danger outranks spectacle.** Enemy telegraphs are red-white and always draw on top of every
   player effect (frames 05, 08). Characters are never hidden. When the screen fills, spectacle
   drops tier by tier and danger never does (section 20).
7. **Yours is loud, theirs is quiet.** Your own effects get full alpha, light spill, the impact
   frame and hit-stop. Allies' effects render at `vfx.ally_effect_alpha` (0.55), with no spill, no
   impact frame and no shake.

## 2. Shape language

| Shape | Use | Rules |
|---|---|---|
| **Smear** (crescent) | melee strikes, dashes, arc projectiles, whips, recoil | A tapered crescent. The dark ink body trails behind, and the bright blade lives only on the leading ~60 % (frame 05). It thickens to a peak at 70 % of the sweep and ends in a rounded head. The tail breaks up into dry-brush streaks as it ages. |
| **Slash** (thin cut) | crits, executes, pierce wounds | A long thin crescent, 5-10 % as wide as it is long, gold or white, over a wider ink cut (frame 10). It is on screen 3-6 frames. |
| **Star** (spiky burst) | impacts, muzzle flashes, kills | 4-9 points of uneven length, long and short alternating, never a circle. It is banded, from the outside in: deep, body, light, then a white-hot core. The ink star behind it is rotated 5-8° and 30 % larger. |
| **Petal flash** | muzzle flashes | A star whose points fan forward inside a cone (the chassis family sets the cone, section 9). It shows on frames 0-2, then the petals drift apart. |
| **Shard** (kite) | shrapnel, obsidian, crystal, coins, plate breaks | A four-point kite with one lit edge and a dark body. Shards spin, fly out, land and shrink away. |
| **Tongue** (flame) | Flame, burning ground, the Meltdown avatar | A leaf shape with an S-curve that tapers to a curled tip, in three nested layers: body, light, hot. Tongues always lean with the motion. |
| **Bolt** (jagged line) | Storm, chain, the Railshock and Judgment variants | A midpoint-displaced polyline with 1-2 branches. It has an ink sheath (2-3× the width), a coloured body (1.7×) and a white core (0.6×). It strobes between 2 shapes at 30 Hz, then vanishes. |
| **Puff** (smoke) | explosions, muzzle smoke, trails, dust | Overlapping noisy circles in three flat values: an ink shadow, a mid tone, and a **rim crescent on the side that faces the light source** (the blast core, the fire). Puffs never use soft gradients (frame 01 filmstrip). |
| **Ribbon** (trail, beam) | projectile trails, beams, tethers, motes | A tapered strip, widest at the head. Colour bands run across it (core, rim), alpha fades along it, and the tail erodes into streaks. |
| **Glyph** | status, curse, mark, hex, time | A flat sigil decal that is quick to read: 2-4 strokes, no fine detail. |
| **Ring** | ACCENTS ONLY | A ring never stands alone as an effect. It is always broken (2-5 gaps), tapered and wobbly, and it only marks a true radius (a player zone hem, the shock front of a burst, a charge ring). A full, uniform, bright ring is banned. |

What we avoid: spheres and glowing balls as bodies or flashes; lone uniform rings; soft radial
gradients as the main shape; white additive blowouts that swallow the silhouette; rainbow
effects (at most two element hues plus white per effect); an effect bigger than its gameplay
radius; red-white or telegraph red in any player effect; player colours on elemental effects.

## 3. Value, colour and ink

### 3.1 The three layers

Every effect is built from three stacked layers. In the engine they are three render layers
(section 21.3):

1. **Ink** (alpha-blended, premultiplied, never blooms): the element's `ink` tone at 80-95 %
   opacity. It is the dark silhouette: smoke shadows, smear bodies, the backing star, the sheath of
   a bolt.
2. **Body** (alpha-blended with HDR colour, may bloom a little): `deep`, `body` and `light` in flat,
   posterized bands. No gradients inside a band.
3. **Hot** (additive, blooms): the `hot` tone as a small core only, 5-15 % of the effect's area.
   This is the only part that goes well above 1.0 linear.

### 3.2 HDR intensity ladder

The camera runs HDR, TonyMcMapface tonemapping and `Bloom { intensity: 0.22, ..NATURAL }`, with no
prefilter threshold, so everything above 1.0 blooms. Keep large areas under 1.0 and let only small
cores go hot.

| Part | Linear gain (own) | Ally | Notes |
|---|---|---|---|
| Ground decals (scorch, stains, zones) | ≤ 0.9 | ≤ 0.6 | never bloom; they must not haze the floor |
| Smoke rims, dust | 0.8-1.1 | 0.6 | lit by the blast, not glowing |
| Body bands | 1.2-1.8 | ≤ 1.2 | a little bloom gives the painted glow |
| Hot cores, impact frames | 2.2-3.0 | ≤ 1.5 | small area only |
| Bolt cores, crit stars | 2.4-3.2 | ≤ 1.6 | 1-4 frames |
| Loot beams, revive pillars | 1.6-2.2 | the same | gameplay-critical, never dimmed by the tier |

### 3.3 Element ramps

Five tones per ramp: **ink / deep / body / light / hot**. The body tone is the `element_color` in
`palette.rs`. These rows become the rows of `assets/vfx/ramps/vfx_ramps.png` (section 22).

| Ramp | ink | deep | body | light | hot |
|---|---|---|---|---|---|
| Kinetic (bone-brass) | `#1A120C` | `#8A4A16` | `#E3A64A` | `#F4E3C1` | `#FFFBF0` |
| Flame | `#240A06` | `#A8300A` | `#FF7A1A` | `#FFC24B` | `#FFF3D6` |
| Storm | `#06101E` | `#1B4E9B` | `#3FD8FF` | `#BDF6FF` | `#FFFFFF` |
| Void | `#0C0416` | `#3B1675` | `#A45CFF` | `#E2CCFF` | `#FFF6FF` |
| Plague | `#0D1507` | `#3A6414` | `#86E03A` | `#D9FF8C` | `#F6FFE0` |
| Radiant | `#241703` | `#B07A12` | `#FFE27A` | `#FFF3BE` | `#FFFFFF` |
| Unmade ichor (enemy) | `#07060A` | `#0D3B35` | `#2FBFA8` | `#8FF2D8` | `#B8FFE8` |
| Godworks cold gold (enemy) | `#1E1408` | `#5A4A20` | `#D4B45A` | `#F4E6B0` | `#FFF4D0` |
| Godworks dead ember (enemy) | `#2A0E08` | `#4A1A0C` | `#8A3A1E` | `#C8663A` | `#E08A50` |
| Enemy shot | `#1A0610` | `#7A1040` | `#FF5AA8` | `#FFC0E0` | `#FFFFFF` |
| Player zone hem (gold) | `#241703` | `#8A6A20` | `#FFC940` | `#FFE6A0` | `#FFF8E0` |
| Heal / revive | `#1A1406` | `#6A5A20` | `#FFE9A8` | `#FFF4D0` | `#FFFFFF` |

The Kinetic body is a warm brass, one step more saturated than `#F4E3C1`, which stays the `light`
tone. Bone-white alone washes out on the pale Cinder flagstones (frame 01).

### 3.4 Who owns which colour

* **Telegraph red-white** (`game.ron telegraph_color #FF3B30` and white) belongs to enemy telegraphs
  only. No player effect, no enemy death burst and no hazard interior uses it. The Bleed status
  shows as dark crimson drips (`#8A1020` on ink), not red, and never as a ground fill.
* **Player colours** (P1 gold `#FFC940`, P2 cyan `#3FD8FF`, P3 violet `#B06CFF`, P4 green `#5BE37D`)
  appear only on ownership marks: the ground ring, the revive tether, turret/blade/echo accents, the
  ping, and the thin hem of an ability's zone. They never tint an elemental effect.
* **Hue collisions are expected.** Storm is P2's cyan, Void is close to P3's violet, Plague is close
  to P4's green, and Kinetic/Radiant sit near P1's gold. Ownership is therefore never read from
  hue. It comes from alpha (own 1.0, ally 0.55) and from the owner's ring. Element identity comes
  from **shape and motion first** (section 4).
* **Enemy factions** use their own glows (Unmade teal ichor, Godworks cold gold and dead ember).
  Enemy projectiles are magenta-cored so they never read as a player projectile.

## 4. Element signatures

Each element is a complete kit: a shape, a ramp, a motion and a secondary particle. A player should
name the element of an effect from its silhouette alone, in grayscale.

| Element | Signature shape | Motion | Impact | Secondary particle | Lingering mark |
|---|---|---|---|---|---|
| **Kinetic** (bone-brass) | petal stars, brass shards, ink smoke puffs | heavy and ballistic: arcs, gravity, spin, recoil | a petal star with a white core, a smoke crown lit from inside, shrapnel (frame 01) | chunky brass sparks that fall with gravity; casings | a scorch with 5-7 thin cracks, 3 s |
| **Flame** | tongues, embers, curling licks | rising and curling: everything drifts up and leans with the motion | the star breaks into 3-6 tongues that rise and curl; an ember fountain | embers: small hot motes that float up, flicker at 12 Hz and die | a burn patch that glows 1 s, then soot |
| **Storm** | jagged bolts, thin angular stars, crackle | instant and strobing: 1-2 frame strikes, 30 Hz shape swaps, no easing | a thin angular star (never round), 3-5 forked bolts (frame 03) | micro-arcs licking between nearby points | a Lichtenberg scorch, 2 s |
| **Void** | ink-dominant smears, inverted stars, hex diamonds | inward: implosion, pull, spiral-in, afterimages | an inward star (the points aim at the centre for 4 frames, then flip out), an ink slash (frame 04) | hex motes (small diamonds) that spiral inward and wink out | an ink stain that shrinks to a point |
| **Plague** | bulbous blobs, droplets, spore clouds, petals | swelling and dripping: bubbles grow, pop, droop; slow drift | a sac swells for 2 frames, then splatters: teardrop droplets arc out | spores: slow, round-ish motes with a dark core that drift sideways | a sickly puddle stain that bubbles and fades, 2 s |
| **Radiant** | straight rays, 4-point crosses, wedges, halo arcs | rigid and geometric: straight lines, snapping rotation, ordered symmetry | a 4-point cross glint and thin straight rays (frames 06, 10) | glints: tiny 4-point diamonds that drift up slowly | a hard-edged glyph decal (a hexagram or sun wheel), 1.5 s |

Radiant and Flame are both warm, so the shape keeps them apart: Flame curls, Radiant is straight.
Void and Storm can both be violet-blue in a mix, and the motion keeps them apart: Void pulls in,
Storm strikes out.

## 5. Anatomy of an attack (60 fps)

Every attack plays the same five beats. The filmstrip in [frame 01](vfx_concepts/01_colossus_shell_impact.png)
shows the impact beats at game scale.

| Beat | Frames | What happens |
|---|---|---|
| **1. Anticipation / charge** | Auto: 0 (a single 1-frame muzzle glint on the first shot of a burst). Charge: the whole `charge_time` (48-66 f). Melee: 3-4 f. Abilities: 6-12 f. | Energy gathers at the `muzzle` / `glow_core` socket: motes spiral in, a broken ring tightens, the core fills. At full charge there is a 1-frame 4-point glint and the ring flashes white. That is the "release now" cue. |
| **2. Muzzle flash** | f0 core, f1 full, f2 break-up, f3 gone. Smoke (heavy weapons only) 12-20 f. | f0: a small white core star. f1: the full petal flash in the element body with its ink backing. f2: the petals split and drift 10 % forward. f3: gone. The shape comes from the chassis family (section 9). |
| **3. Body + trail** | projectile lifetime (`range / speed`, 0.3-1.2 s) | The body keeps full brightness for its whole life. The trail length is about 3 frames of travel (`speed × 0.05 s`), clamped to the distance from the muzzle. The trail tail erodes; the head never does. |
| **4. Impact** | f0-1 impact frame; f2-5 blast peak; f6-14 collapse | f0-1: a white star over a larger ink star, plus 12-18 speed lines on heavy hits. Only for your own crits, kills and heavy/splash impacts; small hits start at f2. f2-5: the banded star at the true radius, light spill on the floor, sparks leaving. f6-14: the star shrinks, the ink erodes, shards fly. |
| **5. Dissipation** | f14-40; decals to 1-3 s | Smoke puffs shrink and lift, their rim-light cools from `light` to `deep`. Sparks fall and die. Ground dust holds at the radius, then fades. The scorch or stain decal fades last. |

**Hit-stop** (client-side and visual only, never a sim pause): a crit freezes the target's animation
for 3 frames and pops its scale to 1.12. A heavy kill freezes for 2 frames. Bosses get no
hit-stop. Ally hits get none either.

**Screen shake** keeps today's rules (trauma² from `Explosion`/`Synergy` within 30 u). Only your
own heavy impacts, your synergies and boss slams add trauma. Allies' effects never shake your
camera.

---

## 6. Projectile bodies (`ProjectileStyle`, all 14)

The style is the **shape and motion**. The weapon's element (`WeaponProfile.element`, which an
`Element` modifier can change) supplies the ramp and the secondary particle. Every style therefore
works with every ramp. Sizes are at 1.0 × `radius`. Bodies scale with `EntityKind::Projectile.radius_q`
(the current code uses `radius × 1.5`), but the silhouette never becomes a sphere.

| Style | Used by | Body | Trail | Impact accent |
|---|---|---|---|---|
| **Bolt** | pendulum_repeater | a short, thick crossbow-bolt kite, 0.5 m, with a hot tip and an ink shaft | 2 strands, 0.8 m, with a dry-brush tail | a small 5-point star; the bolt sticks for 6 f and then fades |
| **Slug** | godsbane_rifle, longstrider_rail, dawnbreaker_carbine | a long thin tracer, 1.5 m: a white core line in element rims, with almost no body | a hard, straight 3-frame streak that never wobbles | a directional spike star (one long spike along the travel); on pierce it keeps going (section 11) |
| **Shell** | colossus_cannon | a brass capsule mesh with a hot base, tumbling 90°/s (frame 01) | ink smoke puffs every 0.06 s that grow and thin with age, plus a short hot exhaust | the layered burst (section 11.7) |
| **Arc** | stormlash, chorus_harp (and beam chassis as a fallback body) | a moving mini-smear: a 0.6 m crescent across the travel direction that flickers between 2 shapes | none: the arc is its own trail | a star in the style of the element; for chain, the hop (section 11.4) |
| **Orb** | thundercoil_launcher, epochal_sundial | an ink core disc, a light-facing rim crescent in the body tone, a white pin, 3 surface crackles (frame 03) | a helix coil: 2 thin ribbons wrapped round the flight path (Storm), or a slowly rotating dial arc (the Sundial's time accent) | the full element impact |
| **Globe** | gravemaw_mortar, voidheart_singularity, plaguebloom_sprayer | a heavy 0.7 m blob that wobbles (squash 8 %) with an inner swirl: a void event horizon, a bubbling plague sac, or a kinetic iron ball with molten seams | droplets or ink drips that fall off behind | a big element burst: Void implodes, Plague splatters, Kinetic makes the layered burst |
| **Shard** | via a `Style(Shard)` part | a crystal kite that spins 720°/s, with one lit facet that flashes each half-turn | a trail of glints (4-point diamonds) | the shard shatters into 4-6 smaller kites |
| **Arrow** | wraith_bow, echoing_greatbow | an arrowhead with an ink shaft, a body-tone rim and a white tip (frame 04) | a wide ghost smear with a dark core and bright rims, 2 wisps peeling off the fletching, hex motes (Void) | pierce wounds (section 11.1); the last target gets the arrow stuck in it for 12 f |
| **Pellet** | sunspike_shotgun | a small diamond with a short straight streak (frame 06) | 0.5 m straight streaks | 4-point cross glints (Radiant) or small stars |
| **Boulder** | Mountainfall (`Style(Boulder)`) | a faceted rock mesh with three value planes and molten seams, tumbling (frame 08) | a dust ribbon and falling embers | the layered burst plus rock debris |
| **Coin** | coinshooter | a spinning gold disc: it alternates ellipse and edge-on line every 4 f and glints every 6 f | a thin gold zig-zag that kinks at every ricochet | a coin "ting" glint (a 4-point star) and a bounce spark |
| **Fist** | anvil_gauntlets, titanfall_hammer, Meltdown shockwaves | melee has no travelling body; the strike cone IS the effect: smears (section 7.4) | none | a contact star with knockback drag lines (frame 05) |
| **Needle** | serpent_smg | a hot sliver in an ink sliver, 0.55 m (frame 02) | a 1.2 m brass streak; at 11 shots/s the stream stitches into one line | a 4-point tick spark kicked back at the shooter, plus target chips |
| **Blade** | tidecaller_harpoon, orrery_discs, huntmother_javelins | a disc: a spinning crescent disc with a circular smear. A javelin: a barbed shaft with a feathered smear. A harpoon: a barbed head plus a rope ribbon back to the player | the disc's circular smear, or a straight shaft streak | a disc cuts a slash through the body; a javelin sticks for 12 f; the harpoon hooks and reels (section 11.8) |

**Enemy shots** (`EntityKind::EnemyShot`, boss `Radial`) are not player styles. See section 15.2.

## 7. Fire kinds (`FireKind`)

### 7.1 Auto

A muzzle flash per shot, 2-4 frames. The flash rotates a random ±15° per shot, so a stream never
looks stamped. Rapid chassis (≥ 8 shots/s) use a smaller 3-petal flicker and skip smoke. A ramp
(Pendulum Repeater) grows the flash from 2 to 4 petals as the rate climbs. At maximum ramp the
barrel shimmers with heat and the flywheel throws a small spark shower.

### 7.2 Charge

* **Gathering** (the whole `charge_time`): 6-9 motes spiral into the `glow_core` on tightening
  paths. A broken ring around the weapon shrinks from 1.3 m to 0.35 m (frame 04). The core grows in
  three steps: ink dot, body disc, then hot pin. `PlayerView.charge` drives it (0..1).
* **Full charge**: a 1-frame 4-point glint, the ring flashes white for 2 frames, then the core
  pulses at 4 Hz while held.
* **Release**: the muzzle flash scales with the charge (0.6× at minimum, 1.4× at full). A recoil
  smear crosses the bow limbs or the rail. A full-charge shot gets a wider trail and its own impact
  frame.
* **Per chassis**: Longstrider lights its capacitor rings along the barrel one by one; Voidheart
  lights its cage bars; Tidecaller spins its reel with droplets; the Wraith and Echoing bows draw
  their string (a bright string line that bends back).

### 7.3 Beam

`PlayerView.beam { len, width }` gives the beam's geometry. The beam is a ribbon from the `muzzle`
along the aim, with four parts:

1. **Core**: a white-hot line 25 % of the width that scrolls a streak noise at 6 m/s.
2. **Body**: element bands across the width (light at the centre, body at the edges), scrolling
   and gently wobbling (±5 % width at 3 Hz).
3. **Edge crackle**: small element-style licks along both edges: tongues for Flame, micro-bolts for
   Storm, glints for Radiant, bubbles for Plague. Each lives 4-6 f.
4. **Contact burst**: at the far end, a small impact star that swaps between 3 shapes at 20 Hz,
   plus a light spill on the floor. On a hit, the star is 1.5× larger.

The beam chassis have their own reads:

* **Bellowfire Projector** (Flame, width 0.9): a breath, not a laser. A cone of rolling flame
  tongues widens to about 1.5 × `width` at the tip. Each bellows pump sends a pulse of brighter
  tongues down the cone, and smoke puffs out of the bellows at the back.
* **Seraph Lance** (Radiant, width 0.45): a hard straight ray with parallel edges, no wobble. Three
  thin halo arcs (accents) slide along it, a 4-point cross flares at the prism tip, and a
  hard-edged glyph scorch sits at the contact point.
* **Plaguebloom Sprayer** (Plague, width 1.0): a fog cone of globules. Petals open at the nozzle,
  bubbles drift sideways and pop into droplets, and a sickly mist band marks the true width.
* **The `Beam` mechanism on any chassis**: the chassis' element ramp with the generic 4-part beam.

### 7.4 Melee

The strike cone (range, `spread_deg` half-angle) is shown with **smears**, never a sector decal.

* **Anticipation**: a 3-4 frame glint on the knuckles or the hammer face.
* **Strike**: a crescent smear in the plane of the fist, sweeping across the cone. It lives 8
  frames: f0-2 the blade leads, f3-5 the body holds, f6-8 the tail breaks into dry-brush streaks.
  Consecutive strikes alternate direction, left then right.
* **Finisher** (every third strike, or any strike with `knockback ≥ 4`): a full-reach smear 1.5×
  as thick, 3 speed streaks down the aim line, a light spill, and a dust puff at the feet (frame 05).
* **Contact**: a big ink-backed impact star at the hit, the target knocked back with 3-4 ink drag
  lines, and the element's secondary particle (Brax's Burn gives ember licks).
* **Anvil Gauntlets** (3 strikes/s, 50° half-cone, 2.8 m): jab/hook smears 0.9 m, finisher 1.4 m.
* **Titanfall Hammer** (1.2 strikes/s, 70° half-cone, splash 1.8 m): a tall overhead smear in the
  vertical plane (drawn projected, so it reads as a downward arc), then a ground crack star with
  debris and a dust wall at the 1.8 m splash.

## 8. Muzzle flashes by chassis

The chassis family comes from WEAPONS.md section 5 (melee > heavy/splash > beam > charge > spread >
precise/pierce > chain > ricochet > rapid). Sizes are the flash's length from the `muzzle` socket.

| Chassis | Family | Flash (f0-3) | Extras |
|---|---|---|---|
| colossus_cannon | heavy | a 5-petal brass star, 1.0 m, 0.55 rad cone | an ink smoke puff ring (4-5 puffs, 20 f); a steam vent from `eject`; a recoil dust puff at the feet |
| thundercoil_launcher | heavy (storm) | a 4-petal cyan star, 0.7 m | 2 micro-bolts run along the barrel coils for 6 f |
| serpent_smg | rapid | a 3-petal flicker, 0.4 m, rotating 15° per shot | brass sliver casings from `eject`; no smoke |
| godsbane_rifle | precise | one long forward spike (1.2 m) plus 2 short side spikes | 2 thin cone lines (a pressure wave) and a smoke wisp |
| wraith_bow | charge | no flash: a violet string-snap smear across the limbs, 4 f | 2 ghost wisps curl off the string |
| sunspike_shotgun | spread | a sunburst of alternating gold wedges across the full spread, 3 m (frame 06) | 7 straight rays along the pellet lines; a pointed white core |
| anvil_gauntlets | melee | none: a knuckle glint (section 7.4) | a dust puff at the feet on the finisher |
| longstrider_rail | charge / precise | a rail flash: 2 parallel lines along the barrel plus a white spike, 2 m | capacitor rings go dark in sequence after firing; a recoil dust puff |
| coinshooter | ricochet (dual) | a small 3-petal gold star, alternating L/R | a flipped coin glint spins off the magazine |
| pendulum_repeater | rapid (ramp) | 2-4 petals, growing with the ramp | a heat shimmer and flywheel sparks at maximum ramp |
| bellowfire_projector | beam | the breath cone (section 7.3) | smoke puffs from the bellows |
| gravemaw_mortar | heavy | a round upward belch of 5 petals from the maw, with tooth sparks | a thick ink smoke column, 24 f |
| stormlash | chain | a whip-crack: a thin S-curve smear from the coil tip, 2 m, 6 f | the bolt follows on the next frame |
| seraph_lance | beam / precise | a 4-point cross at the prism | the hard ray (section 7.3) |
| tidecaller_harpoon | charge (pull) | a spray of green droplets and a rope ribbon that pays out | the rope stays until the harpoon hits (section 11.8) |
| orrery_discs | ricochet | a circular spin smear around the launched disc | a small planetary ring glint on the wrist |
| huntmother_javelins | kinetic blade | an overhand throw smear at the hand | a feather-like dust puff |
| chorus_harp | homing | a string pluck: 3 thin parallel lines vibrate for 6 f | a note glyph that becomes the projectile |
| plaguebloom_sprayer | beam | the petal nozzle blooms open | the fog cone (section 7.3) |
| dawnbreaker_carbine | radiant slug | a 4-point cross, 0.5 m | a small gold halo arc at the sight (an accent) |
| titanfall_hammer | melee / heavy | none: a hammer-face glint | the overhead smear and the ground crack (section 7.4) |
| voidheart_singularity | charge (void) | an inward star: the points aim at the core for 3 f, then flip out | the cage bars flash in sequence |
| echoing_greatbow | charge / spread | 3 string snaps, 2 f apart (the echo) | 3 bone-brass wisps fan out |
| epochal_sundial | time | the gnomon sweeps a clock-hand smear through 30° | a pale gold dial arc (an accent) with tick marks |

## 9. Modifiers

| Modifier | Visual |
|---|---|
| **Pierce** (`pierce`, `Pierce(n)`) | The projectile passes through at full size. Each body it crosses gets an exit wound: an ink slash along the flight line with a bright rim, and 4-5 sparks out of the far side that lasts 6 f (frame 04). |
| **Ricochet** (`Ricochet`) | A bounce spark: a 4-point star plus 3 sparks along the new heading. The trail kinks sharply at the bounce point and keeps the old segment for its fade time. Coins "ting" with a bright glint. |
| **Fork / split** (`Fork`) | The parent flashes a 3-point split star, and the 2-3 children peel off with short V-shaped trails. The children are drawn 80 % as large. |
| **Chain** (`Chain`) | Ink-sheathed bolts in the element's style hop target to target, 1-2 frames apart. Each node gets a small star and a light spill (frame 03). The previous frame's bolt shape lingers as a dim ghost for 2 f (the strobe). Railshock and Judgment Bolt have their own bolt shapes (section 13). |
| **Homing** (`Homing`) | A seeker glint (a tiny 4-point star) rides the head. The trail is built from a position history (section 21.4), so the curve shows. With Rain of the Hunt (240°/s), the curves are big, graceful arcs. |
| **Explosive** (`Explode`, `splash`) | The layered burst (section 11.7). |
| **Gravity well** (`GravityWell`) | A `Well` hazard (section 16). |
| **Puddle** (`Puddle`) | A `Puddle` hazard (section 16). |
| **Orbit** (`Orbit`, the `Blade` entity) | Each blade is a spinning crescent smear circling the owner. It keeps a short circular trail and gives a small slash on contact. The owner's P-colour shows as a thin rim only. |
| **Trail** (`Trail`) | A `Trail` hazard (section 16). |
| **Status on hit** (`ApplyStatus`) | The status glyph lands on the target (section 12.3). |
| **Lifesteal** | 1-2 small heal motes (the heal ramp) fly from the target to the owner. Own only. |
| **Turret on crit** | A bronze spark pop and a small turret rising (section 14, Thessaly). |
| **Doomstack** | Ink glyph pips stack above the target (1 per stack). At the threshold they collapse inward and burst in the element. |
| **Echo shot** | A ghost copy of the projectile at 45 % alpha fires 0.1 s later, with no muzzle flash. |
| **Explode on kill** | The kill burst is replaced by the layered burst at the kill-blast radius. |
| **Shards on kill** | A cyan shard glint joins the kill motes. |
| **Execute** | A black slash with a white cut line across the target, 4 f, before the kill burst. |
| **Beam** | Converts the weapon to beam visuals (section 7.3). |

## 10. Hit punctuation

### 10.1 Plain hit

A small ink-backed star in the element style, 4-5 points, 0.3-0.6 m, 4 frames, with 2-3 sparks.
It is aggregated: several hits on one target within 0.1 s share one star that grows a little.

### 10.2 Critical hit

A gold anime slash across the hit, 62° off the travel direction, 3-5 frames. A 4-point white star
(two long points, two short) sits over a 45°-rotated ink star, and 4-6 gold chips fly out. The
target gets 3 frames of hit-stop and a scale pop. The damage number is a separate thing, owned by
the UI styling in `vfx.rs`. Keep the UI workflow's number styling when merging. See
[frame 10](vfx_concepts/10_crit_precision_hits.png).

### 10.3 Precision hit (Manual aim)

A cyan-white broken bullseye (an accent ring) collapses onto the hit point in 4 frames, with 4
crosshair ticks and a small 4-point glint. Deadeye stacks show as a faint ring of pips around your
own ground ring, one pip per 2 %.

### 10.4 Elites and bosses

* **Rim flash**: every hit on an elite flashes the hit edge of its silhouette for 2 frames (a
  bright crescent on the side facing the shot). This builds on today's `hit_flash`.
* **Plates** (`PLATED`, the `PlatesShattered` event): a hit on a plated elite gives a glancing
  spark that skips off the surface (element-agnostic, grey-white). When the plates shatter, 8-12
  big plate shards in the faction's material fly out with a heavy dust puff and a 2-frame white
  rim, the loudest non-boss hit in the game.
* **Bosses**: punctuation sits at the contact edge, never over the eyes, the face or a telegraph.
  Sparks spray along the surface normal. Only hits of ≥ 5 % of a phase's HP get the impact frame.
  No hit-stop on bosses.
* **Shield** (`SHIELDED`): hits ripple a hex pattern on the forge-shield (faction cold gold or teal),
  and the shield breaks as a burst of hex shards.

## 11. The layered burst (explosive, splash, synergy bursts)

This is the recipe for every explosion (`GameEvent::Explosion { radius, element }`). It is the
main replacement for today's "flat ring + sphere flash + motes". Every layer is sized to the
gameplay radius `R`. See [frame 01](vfx_concepts/01_colossus_shell_impact.png) and its filmstrip.

| Layer | Frames | Shape |
|---|---|---|
| 1. Light spill | f0-14 | A soft element-tinted light on the floor out to 2.5 R. It brightens the floor, it is not a disc. |
| 2. Impact frame | f0-1 | A white star 1.2 R on an ink star 1.6 R, plus 18 speed lines out to 2.6 R. Own and heavy only. |
| 3. Blast | f2-14 | A 7-point banded star at R: the hot core fades from white to light by f8, then the star shrinks to 0 by f14. The ink backing is rotated and 32 % larger. |
| 4. Smoke crown | f2-40 | 7 puffs in a crown around the core. The back half draws behind the blast, the front half in front. The rim-light faces the core and cools as the smoke lifts and shrinks. |
| 5. Shock front | f2-10 | Ground dust puffs pushed out to exactly R by f8. They are the painterly shockwave. A thin broken accent ring may ride the front for 4 frames. |
| 6. Shrapnel | f2-40 | 5-9 shards flung up and out, landing by f24, shrinking away by f40. |
| 7. Sparks | f2-20 | 6-10 chunky sparks with drag and gravity. |
| 8. Scorch decal | f2 to 3 s | A noisy dark patch at 0.8 R with 5-7 thin glowing cracks that cool in 40 f. |

The element changes the blast and the secondaries: Flame adds tongues and embers, Storm swaps the
star for a thin angular one with bolts and a Lichtenberg scorch, Void implodes first (4 frames) and
leaves an ink stain, Plague splatters droplets and a bubbling stain, Radiant uses a cross glint,
rays and a glyph decal.

## 12. Kills, motes and status

### 12.1 Kill bursts

The faction's death recipe (section 15.3) plays at the kill position. The killer's kills are full
size; allies' kills play at 0.55 alpha with no impact frame.

### 12.2 Kill motes

1-3 small glints fly from the corpse to the killer on a curved path (a quadratic curve that
arches up about 3 m) over 30 frames. They flash the killer's ground ring when they arrive (frame 09).
Your own kills send 3 motes; allies' kills send 1 at 0.55 alpha. Elites send 6. In the Silhouette
tier only your own elite kills send motes.

### 12.3 Status glyphs

Status shows as a small glyph at `head_top` plus a body effect. It is drawn once per enemy, not
once per hit.

| Status | Glyph | Body effect |
|---|---|---|
| Burn | a flame-tongue pip | 2-3 small tongues licking off the body; embers |
| Shock | a zig-zag pip | micro-arcs crawl over the body at 10 Hz; at the discharge threshold, a Storm star and a stun |
| Curse | a violet hex sigil | ink drips downward; a slow violet sigil turns under the feet |
| Root | a chain-link glyph | ink roots or chains wrap the legs (Thessaly's hex: green-violet) |
| Bleed | a drop glyph | dark crimson drips `#8A1020` on ink; never red-white |
| Mark | a gold reticle | a 4-tick gold reticle turns slowly around the body (Kael, Ossian) |

---

## 13. The 12 synergies

A synergy (`GameEvent::Synergy`) is a set-piece: the moment two players' elements meet. Every
synergy has the same **trigger beat**: a spiral in each element's colour winds into the target over
6 frames and snaps together into a 2-frame white impact frame. Then the synergy's own body plays.
Synergy bursts use the layered burst (section 11) with their own blast shapes. The ground hem of a
synergy field is player gold. Solo self-synergies (half power) play at 0.75 scale.

| Synergy | Elements | Effect (content) | Set-piece |
|---|---|---|---|
| **Blightburn** | Plague + Flame | Burst r 3.2, Flame, Burn | The rot swells: green sacs bloat on every body for 4 frames, then ignite from green to orange. The burst is a green-cored flame star, spores catch fire and fall as embers, and a burnt-rot scar is left behind. |
| **Gravity Chain** | Storm + Void | chain ×4, r 5, pull 6 | Violet bolts with ink cores hook from target to target. Every node implodes (an inward star), and the targets slide along the bolt's path with ink drag lines. |
| **Firestorm** | Flame + Storm | Field r 3, 3 s, Storm | A dense rim of low flame tongues leans with the swirl. Seen from above, ink smoke arms spiral into a cyan eye, lit orange only on their heads. Every 0.3 s a bolt drops from the eye into a body inside. Embers climb in. A thin broken gold hem marks the true radius. See [frame 07](vfx_concepts/07_firestorm_synergy.png). |
| **Collapsing Star** | Flame + Void | Burst r 3.6, Void | A fire that swallows itself: an orange flare sucked into a black point (an inward star, 6 frames), a 2-frame white-violet pop, then a violet-black shock front and a ring of ember sparks that fall inward. |
| **Solar Flare** | Flame + Radiant | Burst r 3.0, Radiant, Mark | A sunburst of alternating gold wedges on the ground, with 3 solar prominences (arcing flame ribbons) looping out and back. Every scorched body gets a Mark reticle. |
| **Toxic Conduit** | Storm + Plague | Burst r 3.0, Plague, Curse | Green lightning whose bolts carry spore droplets. Each body splashes green and gets a Curse sigil, and a slow spore cloud hangs for 1 s. |
| **Judgment Bolt** | Storm + Radiant | chain ×3, r 6 | The sky delivers the verdict: straight, segmented gold-white pillars strike each target from above (law, not jagged). Each strike leaves a hard-edged hexagram decal. |
| **Entropy Bloom** | Void + Plague | Field r 3.2, 4 s, slow 0.4 | A flower of decay opens on the ground: ink petals with sickly green edges unfold over 12 frames, then wilt over the field's life. Slow motes drift through at 40 % speed. |
| **Eclipse** | Void + Radiant | Burst r 4.0, Void, Curse | A black disc slides over a gold disc. The only bright thing is the corona, a broken gold arc with rays, held for 8 frames. Then comes a violet shock front, and Curse sigils. |
| **Purge** | Plague + Radiant | AllyHeal r 6, +20, dmg ×1.2 | Gold rain falls in the radius. Green motes burn out of enemy bodies as gold sparks, and heal motes (heal ramp) fly to every ally inside. |
| **Shrapnel Blaze** | Kinetic + Flame | Burst r 2.6, Kinetic, Bleed | A fan of molten brass shards with fire trails radiates out, a brass petal blast, and dark crimson Bleed drips on the bodies hit. |
| **Railshock** | Kinetic + Storm | chain ×3, r 5 | Metal conducts: straight brass rail-lines connect the targets, with cyan crackle running along them and magnetized shards snapping toward each node. |

## 14. Kit abilities (`assets/content/kits.ron`)

An ability announces itself with the `Ability { slot, which, pos }` event. It uses the character's
element and style, and the owner's P-colour only as a thin ground hem. Player-side zones are gold.
Allies' ability VFX play at 0.55 alpha.

### Valdris, The Anvil-Born (Kinetic, bronze)

* **Passive: Armor Conversion.** Armour builds as bronze plating: a bronze rim-light on his
  silhouette that thickens with `armor / armor_max`. **ArmorBreak**: the plates shatter into
  bronze kites, a gold dust shock front out to 5 m (the taunt), and a 1-frame gold glint on every
  taunted enemy.
* **Bulwark Slam.** Leap: a dust launch and a heavy downward ink smear following his arc. Landing:
  a ground-crack star with debris and a dust wall at exactly 3.4 m, and stun stars (4-point, gold)
  circling the heads of the stunned. Barricade: a molten seam opens along its line, the bronze wall
  rises through sparks in 8 frames, and projectiles blocked by it give a bronze spark.
* **Siege Stance.** Root: 3 anchor spikes punch into the ground with dust. The cannon's vents glow
  gold. The taunt is a gold broken pulse from Valdris every 1 s (player gold, ground only). His
  muzzle flashes gain a gold outer petal. Hits on him give a bronze glint (−40 % damage).
* **Mountainfall** (the avatar). Valdris grows to 1.8× scale. A forge-heat column rises behind
  him, embers climb, and molten seams glow in his silhouette. Every shot is a **Boulder** (section
  6) ending in a layered burst of 2.4 m. Every 1.1 s he ground-pounds: tapered molten gashes run
  out to the true 4.5 m radius, a gold-lit dust wall rides the shock front, a crater darkens at
  his feet, and rock debris flies. The gashes stay 1.5 s. The Warlord's red telegraph stays on top.
  See [frame 08](vfx_concepts/08_mountainfall_ground_pound.png). On exit, the heat column
  collapses into a spray of cooling embers.

### Selene, The Stormcaller (Storm)

* **Passive: Static Charge.** Moving builds crackle: micro-arcs over her body grow denser with
  `passive_meter`, and a spark trail follows her feet. When the charge is spent, one big arc jumps
  from her to the target.
* **Arc Nova.** A thin angular star at Selene, then 8 bolts to 8 targets in the same frame, each
  with a node star. The bolt width scales with her fire rate.
* **Blink.** Departure: a storm silhouette of Selene (ink body, cyan rim) breaks into 20 hex
  sparks. The storm trail is a crackling ground line (a `Trail` hazard). Arrival: a bolt strikes
  where she lands.
* **Heaven's Verdict.** A moving storm front, 5 m: a painted storm seen from above (ink smoke arms
  spiralling round a cyan eye, as in Firestorm without the fire), with a thin gold hem. Bolts drop
  into bodies inside. Ally projectiles inside gain a cyan crackle rim and chain hops. It drifts at
  the field's travel speed, with its smoke arms trailing.

### Kael, The Wraithshot (Void, Kinetic)

* **Passive: Ghost Step.** A kill sends a violet wisp to his dash pips. Crit stacks show as a faint
  violet afterimage that trails him, denser with more stacks.
* **Fan of Blades.** A spectral fan: 7 knife streaks and a cone smear across the 70° cone, 6.5 m,
  and a Mark reticle on every body hit.
* **Shadow Roll.** A roll smear (ink crescent) with 3 afterimages. The next 3 shots get a violet
  pierce edge and 3 pips over his gun.
* **Bullet Ballet.** Two spectral pistols (ghost silhouettes) float beside him, firing with violet
  muzzle flicker. Every dash leaves an afterimage that fades over 12 frames. Executes use the black
  slash.

### Thessaly, The Hexweaver (Void, Curse)

* **Passive: Curse Weaver.** Cursed enemies carry the Curse sigil (section 12.3).
* **Forge Turret.** Sparks and a bronze turret rising in 10 frames. The turret fires the weapon's
  own style in her element at 40 % size. Its ground ring is her P-colour.
* **Binding Hex.** A 3.5 m hex circle of glyphs (a gold hem, violet-green glyphs) snaps shut. Ink
  chains and roots burst up and wrap the enemies inside. Kills inside spurt gold loot motes.
* **Sabbath of Sparks.** The turrets flare and throw spark fountains, and their muzzle flashes
  double. Lifesteal against cursed targets shows as red-gold motes flowing to allies.

### Brax, The Furnace-Born (Kinetic, Flame)

* **Passive: Heat.** His strikes ignite (Burn licks). His chest sigil (`chest_sigil`) glows brighter
  with the heat.
* **Cinder Uppercut.** An upward smear in the vertical plane, enemies launched with dust, then the
  slam: 5 flame geysers (tall tongues) erupt from cracks across the 2.8 m field and burn for 3 s.
* **Furnace Rush.** A wide flame smear along the 8 m path, an ember wake, and dragged enemies
  pulled along in a molten streak.
* **Meltdown** (the avatar). Brax grows to 1.25×. His fists become molten: flame tongues stream
  back from his fists, and his chest sigil blazes white-orange. Every strike is a Flame smear
  (the Flame ramp on section 7.4's smears) that ends in a **shockwave**: a crescent of flame
  tongues and dust that runs forward out to 2.0 m (the `Explode` radius). The shockwave copies the
  weapon's mechanism visually (chains arc, forks split). Embers rain off him. On exit, his fists
  cool from white to dark iron over 20 frames.

### Ossian, The Far-Struck (Radiant, Kinetic)

* **Passive: Marked Quarry.** A small gold reticle over full-HP targets and elites he aims at.
* **Piercing Comet.** Charge: capacitor rings on the rail. Fire: a comet head races down the 22 m
  line in 6 frames, leaving a white-gold core line and a hard-edged straight scar decal (1.5 s),
  with Mark reticles on everything pierced.
* **Skyhook Mortar.** The lob is visible in the sky: a shell arcs up and falls over 0.7 s, while
  its landing zone shows as a gold (player-side) circle that fills. The Kinetic burst (3 m) is
  followed by 5 bomblets that scatter and burst into the Flame field.
* **Rain of the Hunt.** Gold reticles pulse on every Marked enemy on screen, and his shots curve in
  long homing arcs that leave gold trails.

### Mirren, The Gilded Fox (Kinetic, gold)

* **Passive: Fortune's Favor.** Kills sometimes spit a coin glint.
* **Gilded Decoy.** A shimmering gold clone of Mirren, with a slow gold taunt pulse (ground only).
  After 3 s it bursts into a coin fountain (spinning coins) plus a Kinetic layered burst at 3.2 m.
* **Snatch.** A gold silhouette streak from Mirren to the elite, a slash on arrival, then gold
  speed lines on Mirren for the buff.
* **Grand Heist.** For 6 s, every kill spurts coins and loot glints, and a gold glint runs round
  the screen edge.

### Epoch, The Unwound (time, pale steel)

* **Passive: Borrowed Time.** Clock-tick glints around the cooldown pips (UI side).
* **Still Field.** A 4 m bubble: a pale steel-blue edge with 12 tick marks (the accent ring is
  legitimate here). Inside, **VFX time runs at 0.4×**: particles, trails and flames slow down, so
  the slow reads without a label. The interior is slightly desaturated.
* **Rewind Wounds.** Red damage motes rise back out of the floor into the target, as if in
  reverse, while a counter-clockwise clock-hand smear sweeps round it.
* **Stolen Second.** For 2 s the whole screen desaturates except the players. Enemies get a
  clock-glass crack overlay, and live particles and trails freeze in place. On resume, a gold "tick"
  shock front rolls out from Epoch, the frozen particles snap back into motion, and every ally's
  cooldown pips flash.

Fenra, Lyra, Vex and Seraph have no kit in `kits.ron` yet. Their recipes follow when their kits
land, using the same rules: element ramp, player gold for zones, P-colour for ownership only.

---

## 15. Enemies

### 15.1 Telegraphs and wind-ups (unchanged language)

Telegraphs stay exactly as `scene.rs` draws them: red-white fills that grow from the centre, bright
edges, `pal.danger`. They are **the most readable signal on screen**, so:

* VFX never uses red-white, and never draws over a telegraph. Telegraphs sort after every VFX layer
  (section 21.3).
* A telegraph's resolution (`TelegraphResolved`) gets a short **resolve punch** in the attacker's
  faction style: it stays inside the telegraph's shape and lasts ≤ 10 frames. For a Circle, a
  faction burst the size of the circle. For a Line, a faction beam along the rectangle. For a Cone,
  a faction smear through the cone. For a Ring, dust and faction sparks along the band.
* Wind-ups (`WINDUP`) keep today's red blink, plus a faction glow that gathers at the
  `attack_origin` socket.

### 15.2 Enemy attacks

| Attack | VFX |
|---|---|
| **Enemy shots** (`EnemyShot`, boss `Radial`) | A magenta-cored teardrop, stretched 1.6× along its velocity: a magenta `#FF5AA8` core, a pale pink rim, a dark ink shell, and a thin red-white outer edge. The spawn flash at the boss is a 3-frame faction star. A short dark streak trails it. On impact (a player or a barricade), a small magenta star. Never an element colour. |
| **Lobber** (slagspitter, spore_censer, collapsar, comet_sling) | The telegraph circle is the danger. A cosmetic glob (molten slag, a spore sac, a collapsing star, a broken sky chunk) arcs from the lobber to the telegraph's centre, timed to land on resolve. The resolve punch is a faction burst inside the circle. |
| **Caster** (molten_hexer, rot_cantor, stargazer, geometer) | The line telegraph is the danger. The caster's `attack_origin` gathers its faction glow. The resolve is a 6-frame beam inside the rectangle (molten with teal cracks, rot green-black, starlight, straight geometry). |
| **Charger** (anvil_brute, barkhide_aurochs, nightglass_lancer, vector) | The line telegraph is the danger. The charge leaves a dust wake and faction sparks under its feet, and hitting a player gives a big dust puff. |
| **Bomber** (kindlejack, bloatbulb, knellbell, null_herald) | The circle telegraph is the danger. The fuse shows as faction sparks at the fuse and the body swelling. The resolve is a faction burst inside the circle. |
| **Support** (forge_warden, lichen_abbot, horologist, unwright) | A beam of shield glow runs to each shielded ally; the shield is a hex ripple in faction cold gold, teal or brass. |
| **Wisp death bursts** (emberwisp, glimmermoth, starmote, paradox) | Telegraphed (a Circle with a 0.45 s fuse). The body flickers faster until the resolve, then a faction burst inside the circle. |
| **Boss Strike** (Circle, Line, Cone, Ring) | The telegraph is the danger. The resolve punch is at the boss's scale: a molten slam, a rot hymn beam, a clock-hand sweep, a chaos shatter. |
| **Boss SlamTrail** | A sequence of Circle telegraphs. Each resolves into a crater star with debris. |
| **Boss Pools** | Telegraphed, then a lingering `Pool` hazard (section 16). |
| **Boss Summon** | A faction portal splash on the ground, and the new enemies rise through it (today's `EMERGING`). |
| **Boss phase** (`BossPhase`) | A faction burst from the boss's `fx_core`, a 2-frame white rim on the boss, and a screen-edge flash in the faction colour. It is not red-white, because a phase change deals no damage. |

### 15.3 Death recipes by faction

The faction comes from the enemy's art pack (docs/art/ENEMIES.md section 4, the README of each
`art/enemies/<key>/`). The Unmade are teal ichor; the Fallen Godworks are cold gold. A swarm death
is 40 frames; an elite death adds a second beat; a boss death is a set-piece.

**Unmade** (clinker, cinderling, ashrunner, slagspitter, kindlejack, anvil_brute, molten_hexer,
slag_king, rotmite, nullmite, ...). See [frame 09](vfx_concepts/09_unmade_death_shatter.png).

| Frames | Beat |
|---|---|
| f0-1 | The body flashes white over an ink star. |
| f2-10 | The obsidian shell shatters into 5-7 shards with a bone-grey edge light (`#7F7278`). A teal ichor splash star and a black-teal ink puff. |
| f3-24 | Ichor teardrops arc out and fall. |
| f3 to 2 s | A teal-black ichor stain decal grows over 10 frames and fades. |
| f10-40 | Kill motes fly to the killer. |

The Slag King's brood (cinderling, molten_hexer, the slag family) adds molten orange drips inside
the teal splash, following their material.

**Fallen Godworks** (forge_warden, emberwisp, the_bellows, ticker, and the Godworks rows as they are
built): f0-1 a cold-gold flash on an ink star; f2-12 cracked porcelain and bronze plate shards,
cold-gold sparks that fall with gravity, a dead-ember smoke puff; the mask cracks last (a porcelain
pair of shards). The stain is soot with a few cooling gold flecks.

**Elites**: the faction recipe at 2× scale, plus a second beat 6 frames later: a faction burst
from `fx_core` and 6 kill motes.

**Bosses**: a set-piece authored per boss (the Slag King's furnace door bursts, the crown blades
scatter, the core pours out). Every boss death holds one 4-frame impact frame, the only global
freeze-look in the game. All other VFX pause visually during it.

---

## 16. Hazards (`HazardKind`)

Player-side hazards (flag `ALLY`) have a thin, broken **gold** hem at the true radius and a quiet
element interior (alpha ≤ 0.35, no bloom), because at 4P they can cover a third of the screen.
Today's `cap_ally_fields` stays. Enemy hazards have a thin, broken **red-white** hem, because they
deal damage, and a faction interior.

| Kind | Made by | Look |
|---|---|---|
| **Well** | `GravityWell` (voidheart_singularity) | 3-4 ink spiral arms rotating inward at 90°/s with bright void rims on their heads, debris motes pulled in along the arms, and an ink core that pulses with each damage tick. |
| **Field** | ability and synergy fields | Each field is its own set-piece (sections 13-14). The generic fallback is element paint on the ground: tongues for Flame, crackle for Storm, petals for Plague, glyph wheels for Radiant, an ink swirl for Void, dust for Kinetic. |
| **Pool** | boss `Pools` (enemy) | A faction liquid: molten slag with a cooling crust (Cinder), rot sludge with bubbles (Verdant), liquid clockwork brass (Spire), chaos glass (Unmaking). A red-white dashed hem, and a slow surface animation. |
| **Puddle** | the `Puddle` modifier | An element puddle with small bubbles or licks, and a gold hem. Its status adds that status's body effect to enemies standing in it. |
| **Trail** | the `Trail` modifier, Selene's Blink | A burning streak decal along the path: element licks, fading from the oldest end. |
| **Ground** | `UltGround` ("ults leave burning ground") | An element fire patch: short tongues across the area, a gold hem, fading from the edge inward. |

## 17. Pickups and loot

* **Parts**: a spinning part glyph in the rarity colour. Rare+ parts get a **loot beam**: a tall,
  thin ribbon with a bright core, gently wobbling, with motes rising up it. Epic beams are wider,
  Godforged beams have gold motes and a slow gold sunburst at the base. Beams are gameplay-critical:
  no tier ever drops them.
* **Shards**: small crystal kites that bob and glint (`#8FF7FF`).
* **Health**: a pink-red heart glyph `#FF4D6D` with a soft heal-ramp halo, kept apart from the
  telegraph red by its shape and the heal halo.
* **Personal loot**: other players' pickups are ghosted (25 % alpha, no beam), as today.
* **Collection** (`Pickup` event, own only): the pickup streaks to the player in 8 frames and
  flashes a small star in its colour at the player's ring.

## 18. Team moments

* **Overdrive** (`Overdrive`, 5 s): the trigger is a gold shock front rolling out from the
  triggering player across the screen, plus a gold pillar on each player (the only time pillars
  appear on all four). During it, every player gets a gold rim-light and gold outer petals on their
  muzzle flashes, and a warm gold vignette sits at the screen edge. At the end, the rim-lights
  flicker out over 12 frames.
* **Downed** (`Downed`): the body falls, ink smoke puffs, and the player's wraith rises (ghost
  silhouette, 45 % alpha, P-colour rim). A slow gold ember drifts off it.
* **Revive tether**: a braided ribbon between the reviver and the wraith in the reviver's P-colour,
  with gold motes flowing toward the wraith. The progress fills along the tether over the 3 s
  channel (`revive.revive_time`), and the tether frays and snaps if the reviver leaves 3.5 m.
* **Revived** (`Revived`): a gold pillar, a gold burst, and a shield bubble on the reviver (hex
  ripple).
* **Reforged** (the Forge brings a player back): a molten pour from above forms the silhouette,
  which cools from white to the player's colours over 20 frames.

## 19. The Forge and the anvil

* **Dormant**: the anvil's ember glow breathes slowly; a few sparks.
* **Kindling** (`AnvilLit`): a pillar of forge light and a gold shock front. While the hold ring is
  occupied, sparks fly from the anvil to each player inside. If it is contested, the sparks die
  and the anvil dims.
* **Hot** (`AnvilHot`): the anvil glows molten white-orange, heat shimmer rises, and a forge light
  lights the players nearby.
* **Forge actions** (`Forged`, `RecipeDiscovered`): each action is a hammer strike on the anvil: a
  2-frame white impact frame, a spark fountain, and a rising ember column. Equip: the part glyph
  flies into the player. Fuse: two part glyphs spiral together and merge in a flash of the new
  rarity colour. Reroll: the glyph spins and changes. Salvage: shards spray into the player. A
  named recipe discovered gets a gold sunburst over the anvil.
* **Spent**: the anvil cools to dark iron over 1 s with a last puff of steam.
* **Boons** (`BoonTaken`): a pillar in the god's colour (`gods.csv`) with the god's sigil turning at
  the base: Pyra flame, Zephyros wind, Nyctia crescent, Aeon dial, Gaiaa stone, Morwenn wave,
  Seraphel sun, Umbra-Rex ruin.

---

## 20. Readability budget

### 20.1 Tiers

The tier comes from the live effect load (`game.ron vfx.reduced_at 450 / silhouette_at 900`), with
the particle caps `vfx.particles (1600, 700, 200)`, as today. With the batcher (section 21), one
live quad counts as one particle and one ribbon or smear counts as one effect.

| Layer | Full | Reduced | Silhouette |
|---|---|---|---|
| Enemy telegraphs, enemy shots, player rings, loot beams, revive tether, pickups | always | always | always |
| Your own muzzle flash, projectile body, impact star core | full | full | full, no secondaries |
| Your own impact frame (f0-1), hit-stop, light spill | yes | yes | impact frame on crits and kills only |
| Your own trails | full length | full length | half length |
| Allies' projectile bodies | 0.55 alpha | 0.55 alpha | 0.4 alpha, 70 % size |
| Allies' trails | full | head third only | off |
| Allies' impacts | small star, no impact frame | star only | a 2-frame dot star |
| Sparks, embers, glints (secondaries) | full count | half count | none for allies, 2 per own impact |
| Smoke puffs and dust (overdraw-heavy) | full | half count, 60 % life | off (the ink star stays as the silhouette) |
| Scorch, stain and crack decals | 3 s | 1 s | off |
| Kill motes | own 3, allies 1, elites 6 | own 2, allies 0 | own elite kills only |
| Status body effects | all | own-applied only | glyphs only |
| Synergy set-pieces | full | full body, half secondaries | trigger beat, blast, and hem only |
| Ability set-pieces | full | full body, half secondaries | the shape and the hem only |

What drops first, in order: allies' secondaries, then smoke and dust, then decals, then allies'
trails, then your own secondaries. Danger signals and ownership marks never drop.

### 20.2 Ownership and alpha

* Your own effects: alpha 1.0, light spill, impact frames, hit-stop, shake.
* Allies' effects: `vfx.ally_effect_alpha` (0.55) and their HDR gains capped (section 3.2). No
  spill, no impact frame, no hit-stop, no shake. Allies' player-side zones keep today's low-alpha
  rules and `cap_ally_fields`.
* Enemy effects: full alpha, never tier-dropped when they carry danger (shots, telegraph resolves).
  Enemy death bursts follow the "allies" column when the killer is an ally.
* Damage numbers stay as the UI workflow styles them: own damage only, aggregated per target, ≤ 40
  alive.

### 20.3 Composition rules

* An effect never covers a character's head or torso with an opaque ink layer for more than 4
  frames. Ground layers render under characters (frame 08).
* Smoke from one burst never exceeds 1.2× its radius and has lifted off the ground by frame 20.
* No two impact frames in the same 0.25 s: the second one is downgraded to a normal blast (at 11
  shots/s, only kills and crits earn an impact frame).

---

## 21. Tech plan (Bevy 0.20.0-rc.1, no third-party crates)

### 21.1 What is wrong today

* `vfx.rs` spawns **one entity per particle** with a `low_sphere` mesh. Bevy batches sorted
  transparent items only when consecutive items in the back-to-front order share the pipeline,
  mesh and material (`batching::batch_and_prepare_sorted_render_phase`). Particles of different
  colours use different cached materials and interleave by depth, so at peak most of them become
  separate draws: up to about 1600 draw calls, plus about 1600 ECS spawns and despawns a second.
* Shapes are spheres, rings and discs. Nothing uses a texture, so nothing can look painted.
* Shockwaves swap materials per frame to fade alpha (`update_shockwaves`), which is cheap but
  cannot erode or dissolve.

### 21.2 Architecture

Keep `vfx.rs` for event routing, tiering and the damage numbers (whose styling the UI workflow
owns). Move the new work into a `vfx/` module inside `gf_client`:

| File | Role |
|---|---|
| `vfx/recipes.rs` | the recipe table: `GameEvent` + context (element, style, owner, tier) → a list of emitters. The numbers live in `assets/content/vfx.ron`, because stats never go in code (ARCHITECTURE principle). |
| `vfx/batch.rs` | the particle store (a `Vec<Quad>` resource, no entities) and the per-layer dynamic meshes |
| `vfx/ribbon.rs` | trails, beams, tethers, kill-mote tails: strip meshes, batched per layer |
| `vfx/smear.rs` | crescent smear strips: melee, dashes, arc projectiles, slashes |
| `vfx/decals.rs` | ground decals (scorch, stain, crack, glyph) in a ring buffer of quads |
| `vfx/bodies.rs` | projectile bodies (billboards for most styles, small meshes for Shell, Arrow, Boulder, Coin, Blade) |
| `shaders/vfx.wesl` | one shader for all layers (section 21.5) |

A `--vfx-gallery` QA flag fires every recipe (all 14 styles × 6 elements, every synergy, every
ability, every death, every hazard) in a labelled grid for captures and art review.

### 21.3 Layers, blending and sort order

Bevy sorts transparent items back to front by `view distance + depth_bias`
(`TransparentSortingInfo3d::sort_distance`; values grow toward the camera and the sort is
ascending, so a larger `depth_bias` draws later). The batched meshes span the screen, so their
AABB centre means nothing. The layer order therefore comes from `depth_bias`, not from position:

| Order | Layer | Blend | depth_bias |
|---|---|---|---|
| 1 | ground decals (scorch, stains, zone paint) | alpha | +100 |
| 2 | ground VFX (dust, cracks, spill) | alpha / additive | +200 |
| 3 | ink (smoke shadows, smear bodies, backing stars, bolt sheaths) | premultiplied alpha | +300 |
| 4 | body bands | premultiplied alpha, HDR colour | +400 |
| 5 | hot cores | additive (`AlphaMode::Add`) | +500 |
| 6 | **enemy telegraphs** | alpha | **+1000** (so they composite over every VFX layer) |

Inside a layer, quads are ordered CPU-side (back to front along the camera's forward), which is
cheap because the camera is a fixed orthographic view.

All VFX layers keep the depth test and do not write depth, so opaque characters and walls still
occlude ground VFX. The telegraph `depth_bias` is a change to `scene.rs` / `palette.rs` (owned by
the model-integration workflow until it merges), so it lands in the integration phase.

### 21.4 Batching

* **Particles**: one dynamic `Mesh` per layer, rebuilt every frame from the particle store. Each
  quad has 4 vertices (position, UV, colour, and a packed `[age, frame, ramp_row, erode]` custom
  attribute). The camera is a fixed 55° orthographic view with yaw 0, so the billboard basis is
  constant (camera right and up). The CPU can expand quads without any per-frame camera math. At
  the Full cap, 1600 quads = 6,400 vertices, about 250 KB of upload per frame.
* **Ribbons**: projectiles move on motion descriptors (`pos0 + vel × t`), so a straight
  projectile's trail is analytic: a strip from `pos(t - L/v)` (clamped to the spawn point) to
  `pos(t)`. It needs no history. Homing and ricochet projectiles keep a ring buffer of 12 samples.
  All trails of one layer go into one strip mesh.
* **Smears**: crescent strips (24 segments × 2 vertices) generated in Rust from (centre, radius,
  start and end angle, width profile, plane). All live smears of a layer share one mesh.
* **Pooling**: the particle store and the strip buffers are pre-sized to the Full caps and reuse
  their slots. No ECS spawns per particle. The remaining per-effect entities (beams, hazards,
  bodies) come from small pools.
* **Alternative**: `bevy_render::gpu_component_array_buffer::GpuComponentArrayBuffer` with
  `MeshTag` can store per-instance data in a storage buffer (the pattern of the
  `gpu_component_array_buffer.wesl` example). It suits instanced projectile bodies that share one
  mesh and one material. For the sorted transparent layers, the CPU-built meshes stay the main
  path: they give exactly one draw per layer however the items interleave by depth.

### 21.5 `vfx.wesl`

One `Material` (not an extended `StandardMaterial`: VFX is unlit) with a `mode` constant per layer.
The fragment shader:

1. Samples the **atlas** at the flipbook frame. The atlas packs **R = shape mask, G = value, B =
   erosion threshold**. One painted grey flipbook serves every element.
2. Maps G through the **ramp** row (`vfx_ramps.png`, 256 × 16): value → ink / deep / body / light /
   hot, posterized to 4-5 flat bands with a 1-texel soft edge (the painted look of the concept
   frames).
3. Dissolves: alpha = `smoothstep(t - 0.04, t, B)` where t is the normalized age. Tails erode
   into dry-brush streaks while heads stay solid.
4. Smears and ribbons scroll a streak noise along U (`noise_streak_256.png`) and multiply it into
   the erosion threshold, so brush streaks run along the stroke.
5. Multiplies the HDR gain (section 3.2) and the ally alpha, which arrive in the vertex colour.

Embed it like the existing shaders (`embedded_asset!(app, "shaders/vfx.wesl")`, module
`gf_client::shaders::vfx`, WESL syntax as in `toon.wesl`).

### 21.6 Draw-call and particle budget at peak (400 enemies + 4 players)

| System | Draws | Load at peak |
|---|---|---|
| Particles (5 layers) | 5 | ≤ 1600 / 700 / 200 quads by tier |
| Ribbons (trails, beams, tethers, motes) | 3 | ~120 live projectiles at 4P peak (Sunspike 7 pellets × 1.6/s × 4, Serpent 11/s × 0.42 s × 4, boss Radial 30) × ≤ 12 segments ≈ 1,400 segments |
| Smears | 3 | ≤ 24 live (4 melee players × 3 strikes + dashes) |
| Decals | 1 | ≤ 256 quads (a ring buffer, the oldest recycled first) |
| Projectile bodies | ≤ 6 | billboards in the particle layers; ≤ 5 instanced mesh styles |
| Beams | ≤ 4 | 1 per beam player, all layers in one strip mesh |
| **Total VFX** | **≤ ~22** | compared with up to ~1,700 today at the Full cap (when colours interleave) |

The CPU cost is the quad rebuild (a few thousand vertices) and the recipe routing, well under 1 ms
at peak. The host tick budget (ARCHITECTURE section 8) is untouched: VFX is client-only and never
feeds the simulation.

## 22. Asset list (`assets/vfx/`)

All textures are painted by script (`tools/vfx/make_atlases.py`, PIL + numpy; the concept painter in
`docs/art/vfx_concepts/src/` is the starting point). Grey atlases hold shapes, and the ramps colour
them. Meshes that must read as 3D are built in Blender 5.2 (`tools/blender/vfx/meshes.py`) or
generated in Rust.

| File | Content | Size |
|---|---|---|
| `atlas/vfx_impact_star.png` | 8-frame banded impact stars, 4 variants (4/5/7/9 points) | 2048 × 1024, 256 px cells |
| `atlas/vfx_petal_flash.png` | 4-frame muzzle petals: forward fan, sunburst wedges, cross, inward star | 1024 × 1024 |
| `atlas/vfx_smoke_puff.png` | 16 puff silhouettes with value planes for rim-lighting (R mask, G value from a fixed light) | 1024 × 1024 |
| `atlas/vfx_sparks_shards.png` | 8 spark streaks, 8 shard kites, 4 teardrops, 4 coins, 4 glints | 1024 × 512 |
| `atlas/vfx_flame_tongue.png` | 8-frame flame tongue loop × 3 widths | 1024 × 1024 |
| `atlas/vfx_bolt.png` | 8 bolt segment variants and 4 Lichtenberg patterns | 1024 × 512 |
| `atlas/vfx_glyphs.png` | status glyphs, Curse / Mark / Hex / Root sigils, god sigils, Radiant hexagram, clock dial | 1024 × 1024 |
| `atlas/vfx_decals.png` | scorch, ichor stain, plague stain, soot, crack stars, ink stain | 1024 × 1024 |
| `ramps/vfx_ramps.png` | 16 ramp rows (section 3.3), 256 texels each | 256 × 16 |
| `noise/noise_erode_256.png` | tiling fractal value noise (the dissolve threshold) | 256² |
| `noise/noise_streak_256.png` | anisotropic brush-streak noise for smears and ribbons | 256² |
| `noise/noise_cells_256.png` | cellular noise for plague bubbles, the hex ripple and chaos glass | 256² |
| `meshes/vfx_shell.glb` | brass capsule shell, ≤ 120 tris | |
| `meshes/vfx_arrow.glb` | arrowhead and shaft, ≤ 60 tris | |
| `meshes/vfx_boulder_a/b/c.glb` | faceted rocks with molten seam UVs, ≤ 80 tris each | |
| `meshes/vfx_coin.glb` | coin disc, ≤ 48 tris | |
| `meshes/vfx_disc_blade.glb` | orrery blade disc, ≤ 64 tris | |
| `meshes/vfx_javelin.glb`, `meshes/vfx_harpoon.glb` | barbed shafts, ≤ 80 tris | |
| (generated in Rust) | crescent smear strips, ribbons, broken accent rings, beam strips | |
| `../content/vfx.ron` | the recipe table: per event / style / element / chassis: emitters, sizes, frame timings, gains | |

## 23. Build order (the following workflow phases)

1. **Effects phase** (no edits to `scene.rs` / `palette.rs` / `materials.rs` / `models.rs` /
   `anim.rs` until the model workflow merges): `vfx.wesl`, `vfx/batch.rs`, `vfx/ribbon.rs`,
   `vfx/smear.rs`, `vfx/decals.rs`, the atlases and ramps, `vfx.ron`, and the `--vfx-gallery` flag.
   Port the event-driven effects of today's `vfx.rs` (hits, kills, explosions, arcs, synergies,
   abilities, overdrive, revive, anvil, boons) to recipes. Keep the damage numbers exactly as the UI
   workflow styles them.
2. **Integration phase** (after the Gate): projectile bodies and trails replace the stretched
   spheres in `scene.rs spawn_visual` (Projectile, EnemyShot, Blade, Echo, Turret); the telegraph
   `depth_bias`; hazard interiors and hems; muzzle flashes at the weapon `muzzle` socket; `fx_core`
   and `hit_center` sockets for deaths and hits.
3. **Polish phase**: the per-chassis muzzle flashes (section 8), the kit set-pieces (section 14),
   the synergy set-pieces (section 13), per-boss deaths, a tier tuning pass at `--horde 400 --bots 3`
   with `--fps`, and the concept-versus-capture comparison.

Review each pass against this page with the concept frames next to real captures. The test is:
turn bloom off, look at the frame in grayscale, and check you can still name every element and
still see every telegraph and every character.
