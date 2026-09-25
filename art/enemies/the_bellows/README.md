# The Bellows (`the_bellows`)

**Status: AI build done, user approval pending.** meta.json says `ai_final_pending_user_approval`,
and `status.json` has stage `2_user_approval` set to `pending_human`.

This is the Cinder Wastes mini-boss, which is also the biome's **Warlord** POI in the open world
(docs/OPEN_WORLD.md: mandatory, worth 2 Seals, on the route to the gate). It was built end to end from
code, with no concept art and no hand edits:

```text
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup --python-exit-code 1 ^
    -P tools/blender/gf_assets/enemies/the_bellows.py -- [--preview] [--no-review] [--lite] [--size 2048]
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/the_bellows.glb
```

A run takes 1-4 minutes on the CPU, depending on load. It covers the model, the paint, the rig, 19
clips, the export, validation and five review sheets. The flags:

* `--preview` builds only the mesh and renders flat zone colours in about 30 s.
* `--lite` renders only the 3/4 hero shots and the game-camera frames, into `work/review/`.

![Stoke and Blaze, 3/4 front](reports/the_bellows_34.png)

| Sheet | What |
|---|---|
| [reports/the_bellows_34.png](reports/the_bellows_34.png) | the first look: Stoke (phase 1) and Blaze (phase 2), 3/4 front |
| [reports/the_bellows_ingame.png](reports/the_bellows_ingame.png) | the game camera (orthographic, 55°, yaw 0) at true 1080p pixels with four 2.2 m heroes at the fight distance: Stoke at 22 m, Blaze turned 35° at 22 m, Stoke at 28 m, and the game-size silhouettes |
| [reports/the_bellows_verb.png](reports/the_bellows_verb.png) | the verb BREATHE at true pixels: rest, inhale, breathe and the summon bow, facing the camera and side-on |
| [reports/the_bellows_review.png](reports/the_bellows_review.png) | the Stoke turnaround, the Blaze views, size against the 2.2 m hero and a 6 m pole, the textures and the palette |
| [reports/the_bellows_clips.png](reports/the_bellows_clips.png) | key frames of all 19 clips |

## Brief

The row in `content/sheets/enemies.csv` is:

| Field | Value |
|---|---|
| Class, biome, phase | MiniBoss, Cinder Wastes, P1 |
| hp, speed | 7,000, 1.8 |
| radius, scale | 1.6, 1.6 (sim collider radius 2.56 m) |
| mass | 12 |
| behaviour | `Boss(script: "the_bellows")` |
| colour, greybox | `#B5532A`, Colossus |

Its line is "A furnace-lung the size of a house. It breathes fire and cinderlings." The mini-boss tier
asks for 2 × the hero's height, a unique verb, 10-20k tris, up to 2048 px and a dedicated rig.

## Design decisions

* **Faction: Fallen Godworks.** A bellows is forge equipment, so this is the great bellows of the gods'
  forge, walked off its hearth when the pantheon fell: a corrupted divine machine. The Cinder Wastes now
  has Unmade swarms (clinker) and an Unmade boss (slag_king), plus a Godworks elite (forge_warden) and this
  Godworks mini-boss.
* **Verb: BREATHE.** The body is a real bellows, with the lid hinged at the front:
  - Five pleated hide folds (open V strips with a sharp ridge) sit between a god-bronze lid and a bottom
    board. Each fold rides its own bone at its share of the lid's opening.
  - On the inhale the lid heaves up, the folds fan apart and swell (the middle ones most), and the lung
    balloons.
  - On the breath the lid slams, the folds crush flat and the mask thrusts forward.
  - The deep valley of every fold is painted with a dim dead-ember glow. It is hidden while the lung is
    crushed and bared when it swells, so the furnace inside shows on every inhale.
  - The idle loop breathes too (the lid rises 6.5°), so the verb reads even at rest.
* **Game-camera read.** The first build read as a tortoise from the 55° camera: splayed legs, a domed
  shell and a round face. The redesign keeps only bellows cues in the outline:
  - a teardrop board;
  - a narrow bronze nozzle bell out of the hinge;
  - the mask at the tip;
  - a flat ring-grip handle behind (the lower handle opens under it into a V from the side);
  - the fold ruff all round;
  - cabriole lion legs tucked under the body, so only the paws peek out.
* **The mask** is a cracked porcelain wind god, in the tradition of the blowing wind faces on old maps:
  - puffed cheeks and pursed O-lips around a bronze nozzle (the furnace glows in it);
  - heavy V brows over hollow near-black almond sockets, each with a small cold-gold pupil. This keeps it
    stern, never a baby face;
  - a full sun of swept bronze rays (mane and beard) framing it.

  The face is tilted up 18° so the 55° camera sees it, and it is 1.93 m wide, about the hero's height. It
  is the one bright value on the model.
* **Lid and vents.**
  - The lid is one dark god-bronze plane with verdigris patina, an old-gold rim with rivets, a slim
    old-gold spine and two raised bronze fan straps.
  - Three vents: a tall and a short chimney with crowns of spikes, and a snapped stub. They are
    asymmetric, and their mouths glow hot cold-gold at the centre, fading to dead ember.
  - Two fire hatches sit over glowing grates.
  - Earlier glowing cracks on the lid read as glyphs at 1x and were removed.
* **Broken runes.** Each whole chimney carries one big two-stroke glyph in cold gold (`#C9AA56`, a dim glow),
  on the side the camera sees. None sit on the lid (it faces the camera) or on the hide: runes across the
  folds broke into speckle.
* **Phases (Stoke → Blaze).** In `phase2` the lung heaves and the left cheek of the mask cracks off and
  falls (bone `mask_shard`), showing the white-gold furnace behind it. At the same time the two fire hatches
  blow open (bones `hatch_L/R`) over their glowing grates. Blaze clips hold that body.
* **Palette** (Fallen Godworks, `gfa_spec.FACTIONS`):

  | Part | Colour |
  |---|---|
  | god-bronze | `#5E5034`, verdigris shadows `#1B3029`, patina `#3D5E50`, light plane `#8E7B4E` |
  | bottom board, hips, claws, grate bars | `#3E3627` |
  | old-gold trim (rim, spine, rays, bands, ring handles) | `#86703F` → `#B49A5A` |
  | hide | `#542D20`, light plane `#A84E2A` (the row colour's hue, toned down), fold shadows `#1A0C0A` |
  | porcelain | `#DCD6C9`, dark hairline cracks `#4E463E` |
  | glows | cold gold `#D4B45A` → core `#FFF4D0`, dead ember `#8A3A1E` at the rims, fold valleys `#4A1A0C` → `#A8481E` |

  A texture scan finds no player colours and no telegraph red in the base colour. In the emissive, the
  furnace core's hot tone was cooled to `#E2CA7C` to stay clear of the player gold `#FFC940`. The engine
  draws the fire, the embers and the red-white telegraphs.

## Size and footprint

| | |
|---|---|
| Height | 5.23 m to the tallest chimney crown (2.38 × the hero; the tier allows 1.7-2.4 ×). The lid's rear is at about 4.1 m, and the mask's centre at 2.6 m. |
| Footprint | 5.46 m wide × 9.0 m long, from the mask's lips to the ring handle. The collider radius is 2.56 m, and the body without the mask and handle is about 5.5 × 6.3 m, which is 2.2-2.5 × the radius. |
| Triangles | 15,576 (mini-boss budget 10,000-20,000) |
| Textures | base colour and emissive, 2048² each, embedded PNG. Painted at 1/4 scale; texel density median 47 px/m (the game camera shows 39-49 px/m); UV coverage 43 %. |
| Material | one, `M_the_bellows`: base colour + emissive, roughness 0.85, single-sided |
| GLB | 4.9 MB, uncompressed (bevy_gltf 0.20 safe) |

## Rig `GF_Bellows_v1`

There are 27 deform joints with rigid skinning (each part rides one joint):

| Joints | What they carry |
|---|---|
| `root`, `pelvis` | the chassis and the bottom board |
| `lid` | the top board, hinged at the front |
| `pleat_1..5` | the folds, all pivoting on the lid hinge |
| `head` | the nozzle bell and the mask |
| `mask_shard` | the left cheek, which breaks off in Blaze |
| `hatch_L/R` | the fire hatches |
| `chimney_1..3` | the vents |
| `front_thigh/shin/paw_L/R`, `hind_thigh/shin/paw_L/R` | the four legs |

Every joint points up with roll 0, so the rest rotations are identity and the local frame is the
creature frame: X left, Y up, Z forward. The exception is `hatch_L/R`, which point along the lid normal, so
that their local Z is the hatch hinge line.

Sockets (empties under the joints; glTF positions are in meta.json `boss_sockets`):

| Socket | Joint | Use |
|---|---|---|
| `hit_center` | pelvis | hit VFX and damage numbers |
| `fx_core` | head | the furnace behind the mask (phase-2 burst, death) |
| `fx_mouth`, `attack_origin` | head | the O-mouth: the fire breath, the lobbed gout, spawned cinderlings and emberwisps |
| `head_top` | lid | status icons |
| `vent_1`, `vent_2`, `vent_3` | chimney_1..3 | radial ember spray and smoke |
| `hatch_vent_L`, `hatch_vent_R` | lid | the Blaze fire hatches |
| `paw_fx_front_L/R`, `paw_fx_hind_L/R` | the paws | footfall dust and slam cracks |

## Clips (30 fps, all in place)

Every clip keys every joint, so each clip carries its phase:

* Stoke clips hold the hatches shut and the shard at scale 1.
* Blaze clips hold the hatches open and `mask_shard` at scale 0.001.
* In Blaze the client plays `<clip>_p2` when it exists, else `<clip>`.

| Clip | s | Events (s) | Notes |
|---|---|---|---|
| `idle@loop` / `idle_p2@loop` | 3.2 | | one breath a loop in Stoke, two deeper ones in Blaze; the open hatches flutter |
| `move@loop` / `move_p2@loop` | 1.6 / 1.33 | | lateral-sequence walk (LH, LF, RH, RF). Planted paws fold at the knee so they stay down. `move_cycle_m` 1.96 / 2.23 |
| `windup` / `_p2` | 1.0 | loaded 1.0 | **the inhale**: brace, the lid heaves open, the folds swell, the face lifts. Ends loaded; time-stretch it to the sim windup |
| `attack` / `_p2` | 1.13 | release 0.13, breath_end 0.67 | **the breath**: the lid slams and the folds crush; the mask thrusts and pours fire (VFX at `fx_mouth`) |
| `hit` / `_p2` | 0.5 | | a flinch; the lid jolts open |
| `radial` / `_p2` | 1.6 | release 0.5, second 0.77 | squat and suck, then two hard pumps; every vent barks embers |
| `summon` / `_p2` | 2.07 | spawn 0.63, 1.0, 1.37 | the face bows to the ground and the lung heaves three times; a coal is born out of the O on each heave (cinderlings in Stoke, emberwisps in Blaze) |
| `strike_ring` / `_p2` | 2.07 / 1.97 | impact 1.0 / 0.9 | rears on the hind legs with a full breath, slams the front paws down; the lid slams and the bag blasts a ring round the body |
| `strike_circle` | 1.8 | release 0.73, impact 0.9 | Blaze only: inhale, aim, lob a gout of fire that lands on the target |
| `phase2` | 2.6 | crack 1.2, burst 1.33 | Stoke → Blaze: heaving, a breath too big, the cheek cracks off and falls, the hatches blow open |
| `death` | 3.0 | collapse 1.93 | always in Blaze: a last gasp, the legs buckle front first, the lung sags and the lid slams, the tall chimney topples, the face plants. Ends held |

The impact frames match the `bosses.ron` windups: Ring 1.0 s (Stoke), 0.9 s (Blaze), Circle 0.9 s. The
brief's names are exported as aliases of the same actions, listed in meta.json `clip_aliases`:

| Alias | Clip |
|---|---|
| `inhale` | `windup` |
| `breathe` | `attack` |
| `inhale_p2`, `breathe_p2` | the `_p2` twins |
| `walk@loop` | `move@loop` |
| `blaze_idle@loop` | `idle_p2@loop` |
| `phase_transition` | `phase2` |

The attack-to-clip map per phase is in meta.json `phases`.

## How it is painted

`paint_bellows()` in the build script composes the shared toolkit and changes nothing in it:

1. `gfa_paint`'s unwrap, Cycles bakes and zone painter run at **1/4 scale**, so the brush features become
   0.1-0.4 m strokes.
2. `gfa_brush`'s broad value planes and tapered edge strokes repaint the two bronze zones. Their lathes and
   tubes would streak under per-facet values.
3. This build's own passes follow:
   - up-facing planes lifted, and the hide's down-facing fold faces darkened, which gives the stripes;
   - verdigris patina in the bronze contact shadows;
   - a per-part radial glow for every vent, grate and the O-mouth (hot centre, dead-ember rim);
   - the fold-valley ember.
4. The decals go on last.

Buried faces are culled: 350 faces inside closed parts, plus the lid's underside and the board's top,
which lie inside the bag. The folds are open strips, so hidden faces take no texels.

## Files

| Path | In git |
|---|---|
| `assets/models/enemies/the_bellows.glb` + `.meta.json` | yes (GLB through LFS) |
| `art/enemies/the_bellows/source/the_bellows.blend` | yes (LFS); textures are referenced relatively, and the NLA tracks are the clips |
| `art/enemies/the_bellows/textures/*.png` | yes (LFS) |
| `art/enemies/the_bellows/reports/*` | yes (each PNG < 2 MB) |
| `art/enemies/the_bellows/work/` | no (previews, per-view renders, sheet layouts) |
| `tools/blender/gf_assets/enemies/the_bellows.py` | the build script (no shared toolkit module was changed) |

## Open points

* The user's visual approval.
* Engine work (not done here; `crates/` is off limits):
  - load the GLB for `the_bellows`, turned with `yaw(angle) * rot_y(PI)`;
  - pick the `_p2` clips in Blaze;
  - spawn the fire, ember and summon VFX at the sockets on the clip events;
  - optionally push the emissive a little in Blaze.
* docs/art/ENEMIES.md has no section for this mini-boss yet. That file is outside this build's working
  area, so a docs pass should add one, pointing here.
* The model is longer than the collider (9 m with the mask and the ring handle). That is intended: the
  fire breath and the ring slam are telegraphed around it.
