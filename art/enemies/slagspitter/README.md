# Slagspitter: the Cinder Wastes swarm spire (The Unmade)

A leaning chimney of cooled slag on a narrow skirt. A molten maw sits in its off-centre mortar muzzle, and
it lobs molten slag where you are about to be. It is built, painted, rigged on GF_Swarm_v1, animated,
exported and reviewed from code.
**Status: `ai_final_pending_user_approval`.** The user gives the final visual approval.

| | |
|---|---|
| Content row | `slagspitter` in `content/sheets/enemies.csv`: Swarm, P0, hp 40, speed 2.6, radius 0.48 × scale 1.0, `Lobber(range 11, windup 1.1, radius 1.4, damage 18, cooldown 3.2, keep_distance 7)`, packs of 1-2, colour `#C24A1C`, greybox shape Spire |
| Brief | Swarm Spire, "Lobs molten slag where you are about to be." A spire or turret of cooled slag with a molten maw on top. It stays mostly in place and has a clear wind-up and lob pose |
| Verb | **LOB**: one shape verb that reads in under a second at game size |
| Faction | The Unmade: slag, molten, obsidian and the teal fissure glow ([docs/art/ENEMIES.md](../../../docs/art/ENEMIES.md) section 4) |
| Build | `tools/blender/gf_assets/enemies/slagspitter.py` (build + review), then the same script with `-- --crowd` (horde review from the shipped GLBs) |

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/slagspitter.py -- [--size 512] [--no-review] [--preview] [--lite]
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/slagspitter.py -- --crowd
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/slagspitter_fix_sheet.py -- --before BEFORE_DIR
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/slagspitter.glb
```

* `--preview` renders flat zone colours (Workbench) in a few seconds, for silhouette iterations.
* `--lite` paints and exports, then renders only the in-game pair and the close-ups, for paint iterations.
* `--crowd` needs the built `slagspitter.glb` and the four clinker GLBs.
* The fix sheet needs the pre-fix GLB of commit `eae8522` in `BEFORE_DIR`
  (`git show eae8522:assets/models/enemies/slagspitter.glb | git lfs smudge > BEFORE_DIR/slagspitter.glb`).

The whole build (paint, rig, clips, export, review sheets) takes under a minute. The crowd and the fix
sheet take about 10 s each.

## Art review fixes (2026-09-26, score 6/10)

Before and after: `reports/slagspitter_review_fix.png`. It shows both GLBs through the game camera at true
1080p pixel size, at four facings and in the wind-up, with their silhouettes. It also shows the cinderling's
wind-up beside them, 3/4 close-ups at one scale, and the same seeded horde.

1. **The outline was a round mound, the cinderling's silhouette class.** The first build was a squat cone,
   0.845 m tall on a 1.11 m skirt, with a thick 0.58 m neck. From the 55° camera it was a round mound. A
   cinderling in its wind-up, with the lid open over its white-hot maw, read like the slagspitter's crater.
   * **Spire.** The skirt narrows (radius 0.555 → 0.41 m) and pinches, on a concave flank, into a slim
     chimney (radius 0.165 m).
   * **Lean.** The chimney curves like a horn, 0.30 m off-centre to the creature's right, and flares into
     a mortar muzzle. The lip is at 0.9 m and the crown of teeth reaches 1.05 m, under the hero's waist.
   * **Shards.** The obsidian shards lean out low from the back left, a counter-diagonal. They are shorter
     than before, so the chimney stays the one tall shape.
   * **Measured.** On the 1x silhouettes (4 facings) the silhouette fill (area / bounding box) drops from
     0.64 to 0.55, and height / width rises from 0.93 to 1.11. The cinderling's wind-up fills 0.74.
2. **The slag body melted into the floor.** The review measured a body median L\* of 22.6 against floors
   of 17-27, with 36 % of the pixels within ±7 L\* of the floor. Only the crater read. `value_pass()`
   repaints the base colour after the broad painter and before the decals. It wraps
   `gfa_brush.apply_decals` for this build's one paint call, so the shared toolkit is unchanged, as in the
   Slag King and clinker fixes.
   * **Top planes.** The up-facing slag planes are lifted toward `#654838`, and the crust toward
     `#704F3E`. The side planes are lifted part of the way, so the toon ramp still gives every form a lit
     plane and a dark plane. The painted darks (cavities, contact) stay proportionally dark, and already-
     light texels (the brush strokes) are skipped. After AO and cavity, the base colour the camera sees
     has a median of `#423027` to `#5D4234` across four facings. That is the review's requested
     `#4E3A30`-`#5E4434`, a little darker on the facing that shows the most shadow side.
   * **Value steps.** Each crust plate takes its own share of the lift, so neighbouring slabs differ by a
     value step. One even lift read as a glazed clay pot.
   * **Flow streaks.** Long, soft cooled-flow streaks run down the spire. They are 8 cm wide, 4 game px:
     a grain, not noise.
   * **Lip strokes.** A bold light lip stroke, `#C8A07A`, about one game pixel wide over a `#8A6650` halo,
     runs along the top edge of every plate. It follows the mesh's own lip vertices, with one break per
     lip, so a broken light ring frames the muzzle.
   * **Edge strokes.** The broad painter's edge strokes are brighter: `#8E6656` on the slag, `#B88E74` on
     the crust.
   * **Measured.** On the 1x game-camera renders (4 facings) the body median L\* rises from 20.0 to 34.8
     (the floor is 19.3). The body pixels within ±7 L\* of the floor drop from 41 % to 24 %. Those left are
     mostly the shadow planes, the ink edge, the black obsidian and the dark toes. The body pixels brighter
     than that band rise from 39 % to 70 %; the approved clinker had 66 %.
3. **Found while fixing.** The crowd review's `spawn()` set `rotation_euler` on the imported GLB copies.
   The glTF importer leaves them in QUATERNION mode, so every copy in the horde faced the same way. It now
   turns the imported rest rotation about world Z, as the ashrunner fix does. The horde is factored into
   `horde_render()`, so the fix sheet can render the pre-fix GLB in the same seeded layout.

Also changed: the toes sit a little further out (`TOE_OUT` 1.05), so the narrower tripod keeps the
collider's footprint. The wind-up and lob follow the chimney's lean: the glob tilts with the muzzle and
leaves along it. The move roll is ±7° (was ±9°, for the taller body). The `hit_center` socket follows the
spire's axis.

## Design decisions

* **Silhouette: a leaning slag spire.** The shape was reached in three steps:
  * The first blockout was a stack of concentric tiers with a tidy crown of fangs. It read as a beehive
    or a cake: symmetric and a little cute.
  * The first build was a squat lava cone. It read as a round mound (see the review fixes above).
  * The model is now six thick slag **crust plates** over a molten core. They rise from a narrow skirt on
    three toes into a chimney that curves off-centre and flares into a mortar muzzle.
  * Each plate bows out and winds slightly round the spire. The seams between the plates widen toward the
    top, so the core glows through as cracks running up to the maw.
  * Each plate's top edge rises into one jagged tooth over the muzzle: low in front, a crown at the back.

  From the 55° camera it is a leaning chimney with a glowing muzzle. A mortar that lobs molten slag should
  look like that.
* **Limit of a swarm spire at 55°.** At about 3 of 8 facings the chimney leans toward the camera. There
  the neck overlaps the skirt, and the outline is a crowned clump with the muzzle glow on top. A
  silhouette sweep tried smaller leans (0.15-0.25 m) and lower or narrower skirts. None of them changed
  those facings, and all of them weakened the diagonal at the others. So the lean keeps its 0.30 m. The
  swarm tier's waist-height ceiling caps the height at about 1.05 m.
* **The maw is the LOB read.** The molten glob in the muzzle is the `head` bone.
  * **Wind-up:** the spire squats and tilts back to aim. The glob swells up and out of the muzzle into a
    cracked molten ball, tilted with the chimney. That is the one bright shape at game size that says
    "about to throw".
  * **Attack:** the spire springs up and the glob leaves the muzzle on frame 2 (`attack_origin`), along
    the lean. It shrinks away and the engine's projectile takes over. Then the spire recoils and the maw
    refills.
  * **Glob shape:** it swells mostly upward (scale Y > X/Z). A uniform swell flattened the dome into a
    mushroom cap.
* **Unmade asymmetry.**
  * The chimney curves off-centre to the right.
  * The front plate is low: the maw breaches there, and a flat tongue of molten slag spills down the
    chimney.
  * A slag blister bulges from the right front of the skirt.
  * A cluster of black obsidian shards erupts from the back left, the mineral breaking through, as on the
    clinker's back.
  * There are three stubby toes: two on the left and one big one on the right (the 2 + 1 limb rule). They
    are low wedges tucked under the skirt, and only their blunt tips and obsidian claws show.
* **Value plan** (the clinker and Slag King review lessons, and this asset's own review):
  * The planes the camera sees are lifted above the `#3A2C24` Cinder floor. Each plate is a value step
    apart from its neighbours.
  * Bold light lip strokes frame the muzzle, and light brush strokes run along each plate's own edges.
  * The hot seams glow between the plates.
  * The glob is the brightest spot. Its hot centre is small, and a band of dark cooling crust rings its
    base.
* **Palette** (The Unmade only; see the swatches on the review sheet):
  * Slag: `#0C0908 / #231A17`, top planes lifted toward `#654838`, strokes `#8E6656`.
  * Crust: `#3E2E25`, lifted toward `#704F3E`, strokes `#B88E74`. Lip strokes are `#C8A07A` over a
    `#8A6650` halo.
  * Hot slag near the maw is `#5A2412`. This is the row colour `#C24A1C` pulled into the slag shadow, and
    its only use.
  * The seam glow runs from `#4A1204` low down, through `#9A2A08`, to `#E0600F` at the lip.
  * The glob uses the Slag King's molten ramp (`#C23C0C` rim, `#FF6B1A` hot) with a small pale-peach hot
    spot, `#FFC88A`, not gold.
  * Obsidian is `#1A1720` with `#6A6680` edges. The two teal fissures are `#2FBFA8` with a `#B8FFE8` core.
  * Colour audit of both textures: no texel lies within 45 RGB units of any player colour (`#FFC940`,
    `#3FD8FF`, `#B06CFF`, `#5BE37D`), of the telegraph red `#FF2A2A` or of white. The closest is 46 from
    the player gold, in the emissive.
* **Paint.**
  * The slag and crust plates use the broad-plane painter (`gfa_brush`): a few broad value planes per plate
    and tapered brush strokes on each plate's own edges. The first pass with `gfa_paint`'s per-facet
    planes read as milk-chocolate clay with a faint triangle web.
  * `value_pass()` then lifts the planes the camera sees and paints the lip strokes (review fix 2).
  * The seams get a painted heat spill: a `#5A2412` halo line decal along every seam, faintly emissive.
  * The glowing parts (glob, core lip, spill) get a cooling-crust pass (`crust_pass`, a local wrapper
    around `gfa_paint.paint`). Voronoi crust plates about 10 cm across, with glowing cracks between them,
    cover the glob's base band, the crater lip and the tongue's cooling tip.
  * A first crust at 6 cm cells turned to dark speckle at game size. A 13 cm version left one dark patch
    on the glob that read like an eye. The final crust stays in a band round the glob's base.
  * Emissive: the first pass blew the whole crater out to white-yellow. The glow is now orange, and the
    seams are dim red low down, hotter near the maw.
* **Size.** The model is 1.05 m tall (0.48 × the 2.2 m hero, under the 1.1 m waist) with a
  1.09 × 1.06 m footprint across the toes. That is inside the 2.2-3 × 0.48 m = 1.06-1.44 m target.

## Rig and clips (GF_Swarm_v1, rigid skin)

| Bone | Drives |
|---|---|
| `root` | the move hop and the whole body (unused by the one-shots) |
| `body` | the spire: six crust plates, the core, the crater lip, the overflow tongue. Pivot 0.24 m up (the centre of mass of the spire) |
| `head` | the molten glob. Pivot on the crater floor in the muzzle, so scaling it grows the glob up out of the maw |
| `legs_a` | the two left toes (front left, back) |
| `legs_b` | the big right toe |
| `tail` | the obsidian back shards (they flare in the wind-up, snap on the recoil and blow off in the death) |

* **Grounding.** Every body pose is solved so that the lowest skirt point stays on the ground: a tilt
  rocks the spire on its skirt edge, and a squash sinks it without floating.
* **Toes.** In `idle@loop` and `move@loop` the toes are planted: the leg groups share the body pivot, and
  their basis is body⁻¹ @ own motion. In the one-shots they ride with the body, so a rearing spire lifts
  its front toe. Planted toes hung in the air under the lifted skirt.

| Clip | Length | Notes |
|---|---|---|
| `idle@loop` | 1.6 s | slow breathing squash; the glob bubbles and burps once. Sampled every frame, so it is seamless |
| `move@loop` | 0.47 s | a rocking tripod waddle: the spire rolls ±7° onto one side, the other side's toes lift and step, with a small hop and a sloshing glob. `move_cycle_m` 1.0 (2.6 cycles/s at the row speed) |
| `windup` | 0.6 s | a small dip, then squat (scale 0.84) and a 12° tilt back to aim. The glob swells to 1.38 × 1.95, tilts with the muzzle and rises out of the maw, and the shards flare back. It ends on the loaded pose, so the client can time-stretch it |
| `attack` | 0.6 s | the spire springs up (scale 1.13) and the glob leaves the muzzle along its lean at frame 2 (`attack_origin`, meta.json `lob.attack_release_frame`) and is gone by frame 4. Then a recoil nod, a refill from frame 11, and rest at frame 18 |
| `hit` | 0.33 s | flinch back and to the side; the glob squashes and the shards rattle |
| `death` | 0.93 s | the glob swells to 1.7 × 2.5 and bursts at frame 10 (the burst is engine VFX at `fx_core`), the shards blow off, and the spire slumps into a puddle and shrinks away (a held final pose) |

**Lobber timing.** The sim's Lobber keeps moving and puts a 1.1 s circle telegraph on the target. A
natural mapping is to play `windup` over the first ~0.5 s of the telegraph, then `attack`, so the thrown
glob flies for the rest of the telegraph and lands with the damage (meta.json `lob.note`).

**Sockets:**
* `hit_center` (body, 0.42 m up on the spire's axis);
* `fx_core` (body, the glob centre in the muzzle: the death burst);
* `fx_mouth` (body, at the maw);
* `attack_origin` (head, on top of the glob: it rides up with the swelling glob);
* `head_top` (body, 1.35 m).

**Facing.** The creature faces glTF +Z and stands on y = 0. The engine turns it with
`yaw(angle) * rot_y(PI)` (ENEMIES.md section 2).

## Metrics

| File | Tris | Height | Footprint | Textures | Texel density (median) | GLB |
|---|---|---|---|---|---|---|
| `assets/models/enemies/slagspitter.glb` | 1,230 (budget 600-1,500) | 1.05 m (0.48 × hero) | 1.09 × 1.06 m | 512 base colour + 512 emissive | 169 px/m (p10 127, p90 180) | 0.57 MB |

It has one mesh and one material, with UV coverage of 39 %. The skin is 771 vertices, each on exactly one
bone. `gfa_validate.py` prints OK.

## Review images (`reports/`)

| File | What |
|---|---|
| `slagspitter_review.png` | turnaround; close-ups at rest and loaded; size beside the 2.2 m hero with the waist line; the in-game camera at true 1080p size (1x, 3x, facing and turned away); the game-size silhouette; key poses through the game camera; clip key frames; textures and palette |
| `slagspitter_clips.png` | the clip key-frame sheet: every clip's key poses at 3/4 front, plus the six key poses at true game size |
| `slagspitter_crowd_review.png` | a lineup (slagspitter, the four clinker looks, the hero) through the game camera at 1x and 3x; the horde read at true pixel size; its silhouette; the four-player view (28 m) |
| `slagspitter_crowd.png` | the horde, 2x nearest |
| `slagspitter_review_fix.png` | the art review fixes, before and after (see above) |

**The horde read.** Forty slagspitters are ringed at lob range round two heroes (21 idle, 10 moving, 5
loaded, 4 throwing), with 24 clinkers of all four looks swarming the heroes. Every copy is posed from the
actions inside the shipped GLBs and turned to face its nearest hero. Each slagspitter stays countable: a
warm slag chimney, lighter than the floor, with a glowing muzzle and hot seams. It never reads as a
clinker, which is a black shell with teal slits and a pale bone club. In silhouette, the slagspitters are
leaning chimneys on a tripod skirt, or crowned clumps where they lean toward the camera. The clinkers are
spiky crawlers.

## Open points for the user review

* The toward-camera facings (about 3 of 8) still read as a crowned clump. See "Limit of a swarm spire at
  55°" above. If this matters in play, the remaining lever is height, which the swarm tier caps at the
  hero's waist.
* The maw is the enemy's one focal glow. Forty on screen make a lot of orange, but the row's packs are 1-2.
  If it is too hot in the engine, lower the glob's emissive strength or the `core` zone's `hot`.
* The lifted slag reads as warm clay-brown at game size. That is lighter than the Unmade's obsidian, but
  the obsidian stays on the shards and claws. If the user wants a darker spire, lower `TOP_LIFT` in the
  build script. The review asked for `#4E3A30`-`#5E4434`. The base colour the game camera sees (flat and
  unlit, 4 facings, slag and crust only) has a median of `#423027` to `#5D4234`: that range, a little
  darker on one facing. The toon key light and rim make it read lighter in the renders.
