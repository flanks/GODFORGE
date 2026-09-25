# Slagspitter: the Cinder Wastes swarm spire (The Unmade)

A squat cone of cooled slag with a molten maw on top, which lobs molten slag where you are about to be. It
is built, painted, rigged on GF_Swarm_v1, animated, exported and reviewed from code.
**Status: `ai_final_pending_user_approval`.** The user gives the final visual approval.

| | |
|---|---|
| Content row | `slagspitter` in `content/sheets/enemies.csv`: Swarm, P0, hp 40, speed 2.6, radius 0.48 × scale 1.0, `Lobber(range 11, windup 1.1, radius 1.4, damage 18, cooldown 3.2, keep_distance 7)`, packs of 1-2, colour `#C24A1C`, greybox shape Spire |
| Brief | Swarm Spire, "Lobs molten slag where you are about to be." A squat cone or turret of cooled slag with a molten maw on top. It stays mostly in place and has a clear wind-up and lob pose |
| Verb | **LOB**: one shape verb that reads in under a second at game size |
| Faction | The Unmade: slag, molten, obsidian and the teal fissure glow ([docs/art/ENEMIES.md](../../../docs/art/ENEMIES.md) section 4) |
| Build | `tools/blender/gf_assets/enemies/slagspitter.py` (build + review), then the same script with `-- --crowd` (horde review from the shipped GLBs) |

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/slagspitter.py -- [--size 512] [--no-review] [--preview]
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/slagspitter.py -- --crowd
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/slagspitter.glb
```

`--preview` renders flat zone colours (Workbench) in about 10 s, for silhouette iterations. `--crowd` needs
the built `slagspitter.glb` and the four clinker GLBs.

## Design decisions

* **Silhouette: a lava cone, not a pot.** The first blockout was a stack of concentric tiers with a tidy
  crown of fangs. It read as a beehive or a cake: symmetric and a little cute. The model is now six
  thick slag **crust plates** over a molten core:
  * each plate bows out and winds slightly round the cone;
  * the seams between the plates widen toward the top, so the core glows through as cracks radiating from
    the maw;
  * each plate's top edge rises into one jagged tooth that curls in over the maw. The teeth are low in
    front and form a tall jagged crown at the back, which frames the glow and breaks the top of the
    outline.

  From the 55° camera it is a dark mound with a glowing crater: a little volcano, which is exactly what a
  thing that lobs molten slag should look like.
* **The maw is the LOB read.** The molten glob in the crater is the `head` bone.
  * **Wind-up:** the cone squats and tilts back to aim, while the glob swells up and out of the maw into a
    cracked molten ball, 0.3 m above the teeth. That is the one bright shape at game size that says
    "about to throw".
  * **Attack:** the cone springs up, the glob leaves the maw on frame 2 (`attack_origin`) and shrinks
    away, and the engine's projectile takes over. Then the cone recoils and the maw refills.
  * **Glob shape:** it swells mostly upward (scale Y > X/Z). A uniform swell flattened the dome into a
    mushroom cap.
* **Unmade asymmetry.**
  * The neck leans forward (the mortar muzzle points at its target) and to the right.
  * The front plate is low: the maw breaches there, and a flat tongue of molten slag spills down the
    front.
  * A slag blister bulges from the right front.
  * A cluster of black obsidian shards erupts from the back-left, the mineral breaking through, as on the
    clinker's back.
  * There are three stubby toes: two on the left and one big one on the right (the 2 + 1 limb rule). They
    are low wedges tucked under the skirt, and only their blunt tips and obsidian claws show.
* **Value plan** (the clinker and Slag King review lessons):
  * The slag plates are darker than the `#3A2C24` Cinder floor. Each plate is framed by light brush
    strokes on its own edges, and the seams glow between them, so the body separates from the floor as a
    dark mass with light and hot edges, not as a floor-value blob.
  * The crust at the plate tops and teeth is a value step lighter, so it frames the glow.
  * The glob is the brightest spot. Its hot centre is small and a band of dark cooling crust rings its
    base.
* **Palette** (The Unmade only; see the swatches on the review sheet):
  * Slag is `#0C0908 / #231A17`, with strokes of `#7A5A48`. Crust is `#3E2E25`, with strokes of
    `#B08A68`.
  * Hot slag near the maw is `#5A2412`. This is the row colour `#C24A1C` pulled into the slag shadow, and
    its only use.
  * The seam glow runs from `#4A1204` low down, through `#9A2A08`, to `#E0600F` at the lip.
  * The glob uses the Slag King's molten ramp (`#C23C0C` rim, `#FF6B1A` hot) with a small pale-peach hot
    spot, `#FFC88A`, not gold.
  * Obsidian is `#1A1720` with `#6A6680` edges. The two teal fissures are `#2FBFA8` with a `#B8FFE8` core.
  * Colour audit of both textures: no texel lies within 45 RGB units of any player colour (`#FFC940`,
    `#3FD8FF`, `#B06CFF`, `#5BE37D`), of the telegraph red `#FF2A2A` or of white. The closest is 47 from
    the player gold, in the emissive.
* **Paint.**
  * The slag and crust plates use the broad-plane painter (`gfa_brush`): a few broad value planes per plate
    and tapered brush strokes on each plate's own edges. The first pass with `gfa_paint`'s per-facet
    planes read as milk-chocolate clay with a faint triangle web.
  * Seams get a painted heat spill: a `#5A2412` halo line decal along every seam, faintly emissive.
  * The glowing parts (glob, core lip, spill) get a cooling-crust pass (`crust_pass`, a local wrapper
    around `gfa_paint.paint`). Voronoi crust plates about 10 cm across, with glowing cracks between
    them, cover the glob's base band, the crater lip and the tongue's cooling tip.
  * A first crust at 6 cm cells turned to dark speckle at game size. A 13 cm version left one dark patch
    on the glob that read like an eye. The final crust stays in a band round the glob's base.
  * Emissive: the first pass blew the whole crater out to white-yellow. The glow is now orange, and the
    seams are dim red low down, hotter near the maw.
* **Size.** The model is 0.845 m tall (0.38 × the 2.2 m hero, well under the waist) and has a
  1.20 × 1.28 m footprint. That is inside the 2.2-3 × 0.48 m = 1.06-1.44 m target. On a 1080p screen at the
  one-hero view it is about 60 px wide.

## Rig and clips (GF_Swarm_v1, rigid skin)

| Bone | Drives |
|---|---|
| `root` | the move hop and the whole body (unused by the one-shots) |
| `body` | the cone: six crust plates, the core, the crater lip, the overflow tongue. Pivot 0.2 m up (the centre of mass of a squat cone) |
| `head` | the molten glob. Pivot on the crater floor, so scaling it grows the glob up out of the maw |
| `legs_a` | the two left toes (front left, back) |
| `legs_b` | the big right toe |
| `tail` | the obsidian back shards (they flare in the wind-up, snap on the recoil and blow off in the death) |

* **Grounding.** Every body pose is solved so that the lowest skirt point stays on the ground: a tilt
  rocks the cone on its edge, and a squash sinks it without floating.
* **Toes.** In `idle@loop` and `move@loop` the toes are planted: the leg groups share the body pivot, and
  their basis is body⁻¹ @ own motion. In the one-shots they ride with the body, so a rearing cone lifts
  its front toe. Planted toes hung in the air under the lifted skirt.

| Clip | Length | Notes |
|---|---|---|
| `idle@loop` | 1.6 s | slow breathing squash; the glob bubbles and burps once. Sampled every frame, so it is seamless |
| `move@loop` | 0.47 s | a rocking tripod waddle: the cone rolls ±9° onto one side, the other side's toes lift and step, with a small hop and a sloshing glob. `move_cycle_m` 1.0 (2.6 cycles/s at the row speed) |
| `windup` | 0.6 s | a small dip, then squat (scale 0.84) and a 12° tilt back to aim. The glob swells to 1.4 × 1.95 and rises out of the maw, and the shards flare back. It ends on the loaded pose, so the client can time-stretch it |
| `attack` | 0.6 s | the cone springs up (scale 1.13) and the glob leaves the maw at frame 2 (`attack_origin`, meta.json `lob.attack_release_frame`) and is gone by frame 4. Then a recoil nod, a refill from frame 11, and rest at frame 18 |
| `hit` | 0.33 s | flinch back and to the side; the glob squashes and the shards rattle |
| `death` | 0.93 s | the glob swells to 1.7 × 2.5 and bursts at frame 10 (the burst is engine VFX at `fx_core`), the shards blow off, and the cone slumps into a puddle and shrinks away (a held final pose) |

**Lobber timing.** The sim's Lobber keeps moving and puts a 1.1 s circle telegraph on the target. A
natural mapping is to play `windup` over the first ~0.5 s of the telegraph, then `attack`, so the thrown
glob flies for the rest of the telegraph and lands with the damage (meta.json `lob.note`).

**Sockets:**
* `hit_center` (body, 0.40 m);
* `fx_core` (body, the glob centre: the death burst);
* `fx_mouth` (body, at the maw);
* `attack_origin` (head, on top of the glob: it rides up with the swelling glob);
* `head_top` (body, 1.2 m).

**Facing.** The creature faces glTF +Z and stands on y = 0. The engine turns it with
`yaw(angle) * rot_y(PI)` (ENEMIES.md section 2).

## Metrics

| File | Tris | Height | Footprint | Textures | Texel density (median) | GLB |
|---|---|---|---|---|---|---|
| `assets/models/enemies/slagspitter.glb` | 942 (budget 600-1,500) | 0.845 m (0.38 × hero) | 1.20 × 1.28 m | 512 base colour + 512 emissive | 166 px/m (p10 123, p90 175) | 0.49 MB |

It has one mesh and one material, with UV coverage of 46 %. The skin is 603 vertices, each on exactly one
bone. `gfa_validate.py` prints OK.

## Review images (`reports/`)

| File | What |
|---|---|
| `slagspitter_review.png` | turnaround; close-ups at rest and loaded; size beside the 2.2 m hero with the waist line; the in-game camera at true 1080p size (1x, 3x, facing and turned away); the game-size silhouette; key poses through the game camera; clip key frames; textures and palette |
| `slagspitter_clips.png` | the clip key-frame sheet: every clip's key poses at 3/4 front, plus the six key poses at true game size |
| `slagspitter_crowd_review.png` | a lineup (slagspitter, the four clinker looks, the hero) through the game camera at 1x and 3x; the horde read at true pixel size; its silhouette; the four-player view (28 m) |
| `slagspitter_crowd.png` | the horde, 2x nearest |

**The horde read.** Forty slagspitters are ringed at lob range round two heroes (21 idle, 10 moving, 5
loaded, 4 throwing), with 24 clinkers of all four looks swarming the heroes. Every copy is posed from the
actions inside the shipped GLBs. Each slagspitter stays countable: a dark cone with a glowing crater and
radiating hot seams. It never reads as a clinker, which is a black shell with teal slits and a pale bone
club. In silhouette, the slagspitters are mounds with one spike and the clinkers are spiky crawlers.

## Open points for the user review

* At the 55° camera the outline is a rounded mound with a jagged back crown and one shard spike. The LOB
  read rests on the glowing maw and the swelling glob, not on a distinctive outline. If the user wants a
  stronger silhouette, the next step is a taller, off-centre mortar neck.
* The maw is the enemy's one focal glow. Forty on screen make a lot of orange, but the row's packs are 1-2.
  If it is too hot in the engine, lower the glob's emissive strength or the `core` zone's `hot`.
