# Emberwisp: the Cinder Wastes spark wisp (Fallen Godworks)

The emberwisp is the Cinder Wastes swarm wisp. It is built, painted, rigged on GF_Swarm_v1, animated,
exported and reviewed from code. **Status: `ai_final_pending_user_approval`.** The user gives the final
visual approval.

| | |
|---|---|
| Content row | `emberwisp` in `content/sheets/enemies.csv`: Swarm, P0, hp 20, speed 4.2, radius 0.34 × scale 1.0, `Swarmer(jitter: 1.4)`, packs of 2-3, colour `#FFD27A`, greybox shape Wisp, `death_burst` (radius 1.6, damage 16) |
| Brief | "Erratic sparks that burst when snuffed." A floating ember spirit with a flickering tail. It hovers with no legs, drifts in an erratic loop and dies in a spark burst. It is mostly emissive but keeps a dark core, so it reads on bright floors |
| Verb | **FLICKER**: one shape verb that reads in under a second at about 35 px |
| Also used by | The Bellows (the Cinder Wastes mini-boss) summons four in its Blaze phase (`assets/content/bosses.ron`) |
| Build | `tools/blender/gf_assets/enemies/emberwisp.py`: model, heat-band flame paint, rig, clips, export, both review sheets |

## The look

The emberwisp is the last spark of a dead god-forge. It still wears a scrap of its war-machine: a small
god-mask head of soot-blackened bronze, the dark core. The head sits in a cup of flame, and a ring of flame
tongues rises and curls around it. The flame is cold gold near the core and cools through rust to dead
ember at the tips. A forked tail streams behind, with two sparks in its wake.

* **The face.** The face carries one slanted, angry eye slit in cold gold. The mask's upper-left corner is
  broken away, and the break is the burning inside of the head. It gives one big glowing gap that the
  camera sees, and an asymmetry that survives 35 px. A low war-helm crest runs over the crown, with an
  old-gold edge. Two bold glowing cracks run from the break over the crown.
* **The flame.** The flame is open over the face and the crown. No tongue rises in front, and the tongues
  start low on the core's sides and back. The 55° camera therefore sees the dark core in the middle of the
  fire from every facing, including from behind, where the tongues are too shallow to hide the crown.
* **Lopsided on purpose.** The left side carries one big hooked tongue that curls over the crown. The right
  side has two lower licks. The back is a tall crest of three tongues.

## Design decisions

* **Faction: the Fallen Godworks.** ENEMIES.md defines the Godworks glow as cold gold `#D4B45A` fading to
  dead ember `#8A3A1E`, which is this creature. The row colour `#FFD27A` is a pale gold that matches the
  faction's own cold-gold light and core (`#F4E6B0`, `#FFF4D0`). The Unmade glow is teal, which is also the
  clinker's colour, so a teal ember would neither read as an ember nor stand apart from the clinkers.
* **Player gold stays out.** The flame's dominant band is faded cold gold, and the tips cool to rust and
  dead ember rather than to a saturated warm gold. The emissive gains are set so the review preview (emission
  × 1.6) does not clip the gold into a saturated yellow. Measured on the 40-copy horde render (24,000 flame
  pixels):
  - the median flame colour is `#E8BA66`, at hue 39°, saturation 0.56 and value 0.91;
  - the player gold `#FFC940` is at hue 43°, saturation 0.75 and value 1.0;
  - 0.8 % of the flame pixels fall within ±8° of hue and ±0.12 of saturation of the player gold at full
    value.

  There is no red-white anywhere: the hot core is a white-gold `#FFF4D0`, and only the glow near the dark
  mask reaches it.
* **Value plan at game size.** Three values do the work:
  - the dark core. The soot bronze is about 12 % sRGB luma, against 65 % for the bright test floor
    `#B4A68C`;
  - the hottest, palest band hugging the core, so the dark mask pops on the dark `#3A2C24` Cinder floor too;
  - the dead-ember tips, which give the bright mass a dark painted edge on bright floors.

  The bright-floor rows of the review sheet show the read holding.
* **Painted fire, not a CG gradient.** `flame_paint()` wraps `gfa_paint.paint` for this build only, so the
  shared module is untouched. It repaints the flame zones as flat heat bands:
  - heat runs along each lick's own centreline, by arc length on the swept curve;
  - the blade edges run cooler than the centre, which puts a hot stripe up every tongue;
  - smooth waves across the flame bend the band borders into flame fingers;
  - a faint low-frequency brush drift and a small wobble keep the borders painterly without speckle.

  Each band carries its own emission.

  Two early passes failed. Lick noise sampled on a straight base-to-tip axis turned into camouflage blotches
  on the curved tongues. Emission scaled in sRGB space made the fire read as brown leather, because the PNG
  is linearised by the engine. The mask-head uses the standard gf_assets NPR painter: dark bronze value
  planes, verdigris cavities, dull old-gold edge strokes and one gradient that sinks the chin into shadow.
* **Mostly emissive.** 69 % of the atlas texels glow. That is the brief, and it is affordable, because the
  emberwisp comes in packs of 2-3 (and four from the Bellows), not in hordes of 40. The horde review is a
  stress test.
* **Engine-faithful review.** The engine's toon shader adds emission after its ink edge, so glowing faces
  carry no ink line. The review preview therefore trims its ink hull off every face whose emissive texel is
  lit. Every in-game crop also draws the client's blob shadow (`scene.rs` `Kit::shadow`), because the hover
  gap reads through the shadow.
* **Size.** The core centre hovers at 0.60 m. The flame spans 0.38-1.07 m, so the top is at 0.49 × the
  hero, just under the 1.1 m waist line (the swarm ceiling); the flare in `windup` briefly rises above it. The
  footprint is 0.53 m wide by 0.88 m long, face to tail tip, inside the 0.75-1.0 m target for radius
  0.34 × scale 1.0. The mesh itself is 0.69 m tall.

## Rig and clips (GF_Swarm_v1, rigid skin)

| Bone | Drives |
|---|---|
| `root` | hover bob, banking tilts and small jinks |
| `body` | the mask-head core. It is the centre of mass, and it persists and tumbles to the ground in the death |
| `head` | the flame hood that cups the core |
| `legs_a` | tongue group A (front-left, back-left, back-right and front-right licks) |
| `legs_b` | tongue group B (the big hooked left tongue, the back crest and the right lick) |
| `tail` | the forked tail and its two sparks |

All flame bones pivot at the core, so scaling a tongue group grows or gutters its tongues out of the core.
The body carries the core, so the fire can burst and vanish while the mask falls on alone.

| Clip | Length | Notes |
|---|---|---|
| `idle@loop` | 1.6 s | FLICKER: the two tongue groups flare and gutter out of phase on integer harmonics, so the loop is seamless and the shape snaps rather than breathes. Each group collapses once per loop. The hood pulses, the tail whips, and the wisp makes two small erratic darts while hovering |
| `move@loop` | 0.6 s | The erratic drift: it leans into the dart, banks side to side, and the tongues stream back while flickering faster. The tail stretches and whips. `move_cycle_m` is 2.52, so the clip plays at 1x at the row speed of 4.2 m/s |
| `windup` | 0.5 s | The flame gutters inward (it draws breath), then flares wide as the wisp rears back. It ends on the loaded pose |
| `attack` | 0.5 s | A 0.3 m dart forward with the flame streaming back, a head-butt of fire, then recoil (in place overall) |
| `hit` | 0.3 s | Knocked back: the flame is blown sideways and gutters, then flares back up |
| `death` | 0.83 s | Spark burst. The flame gutters, the core swells, and at frame 11 the fire bursts outward (spawn the `death_burst` VFX at `fx_core` here). The fire is gone by frame 14, and the blackened mask tumbles to the ground and crumbles. It holds at 2 % |

* **Sockets** (all on `body`): `hit_center` and `fx_core` at the core centre (0.60 m), `fx_mouth` on the
  face, and `head_top` 0.16 m above the flame.
* **Facing.** The wisp faces glTF +Z, and its origin is on the ground under the core. The engine turns it
  with `yaw(angle) * rot_y(PI)` (ENEMIES.md section 2).

## Metrics

| | |
|---|---|
| Triangles | 868 (swarm budget 600-1,500) |
| Textures | 512 base colour + 512 emissive, one material, no Draco or meshopt |
| Texel density | 214 px/m median, up to 430 px/m on the mask-head, whose UV islands are scaled 1.5-1.7× (`uv_zone_scale`). The game camera shows about 49 px/m |
| GLB | 0.46 MB. `gfa_validate.py` reports OK with no warnings |
| Vertices per bone | body 127, head 52, legs_a 132, legs_b 99, tail 82. No vertex is unweighted or weighted to two bones |

## Files

```text
art/enemies/emberwisp/
  README.md, status.json, .gitignore (work/)
  source/emberwisp.blend             model + rig + clips + final material (Git LFS)
  textures/emberwisp_basecolor.png, emberwisp_emissive.png   (Git LFS)
  reports/emberwisp_review.png       turnaround, size vs the hero (waist line), in-game 1x / 3x facing and moving
                                     away, bright floor, silhouette, key poses at true pixel size (Cinder and
                                     bright floor), FLICKER every 0.2 s at game size, clip key frames, textures
  reports/emberwisp_crowd_review.png 40 emberwisps + 24 clinkers (all four looks) around two heroes at true 1080p
                                     size: silhouette, 28 m four-player view, bright floor, 2x
  reports/emberwisp_crowd.png        the horde, 2x nearest
  reports/emberwisp_build_report.json
  work/                              local renders (git-ignored)
assets/models/enemies/emberwisp.glb + emberwisp.meta.json
tools/blender/gf_assets/enemies/emberwisp.py
```

## Rebuild

```text
set BL="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
%BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/emberwisp.py
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/emberwisp.glb
```

The build takes about 1-2 minutes on the CPU; most of it is the UV pack. The command takes these flags:

* `--preview` renders flat zone colours in about 10 s, for silhouette iterations.
* `--no-review` skips the review sheets.
* `--no-crowd` skips the horde review.
* `--crowd-only` runs only the horde review. It imports the shipped GLBs, so it also proves that they load,
  skin and animate in a glTF importer.

## Open items

* The user's visual approval.
* Engine work (in `crates/`, not done here):
  - load the GLB for the key;
  - map sim state to clips: `move@loop` at speed / `move_cycle_m`, and `death` with the `death_burst` VFX at
    `fx_core` at 0.37 s;
  - keep the blob shadow under the hovering model.

  The Swarmer behaviour has no windup state yet, so `windup` and `attack` are ready for a contact dart.
