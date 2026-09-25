# Clinker: E1 Shardling (The Unmade)

The Cinder Wastes swarm crawler. There is one base look and three shell variants, and each is a
separate GLB. They are built, painted, rigged on GF_Swarm_v1, animated, exported and reviewed from
code. **Status: `ai_final_pending_user_approval`.** The user gives the final visual approval.

| | |
|---|---|
| Content row | `clinker` in `content/sheets/enemies.csv`: Swarm, P0, hp 9, speed 3.8, radius 0.26 × scale 0.8 (collider ≈ 0.21 m), `Swarmer(jitter: 1.0)`, packs of 6-10, colour `#9A5B3C`, greybox shape Crawler |
| Concept | E1 SHARDLING in the user's enemy pack, mapped in [docs/art/ENEMIES.md](../../../docs/art/ENEMIES.md) section 7 |
| Verb | **SKITTER**: one shape verb that reads in under a second at about 35 px |
| Build | `tools/blender/gf_assets/enemies/clinker.py -- --variant base\|v1\|v2\|v3`, then `enemies/clinker_crowd.py` |

## The four looks (one file each)

| File | Look | What changes |
|---|---|---|
| `assets/models/enemies/clinker.glb` | **Shardling** (base) | three scutes, a few back crystals, a web of fissures, the three legs on the LEFT |
| `assets/models/enemies/clinker_v1.glb` | **Crested** | a tall crystal crest along the spine, longer and thinner legs, fissures along the spine, **mirrored** (three legs on the right) |
| `assets/models/enemies/clinker_v2.glb` | **Brood-back** | squat and broad with four scutes, a bigger skull and claw, star cracks, a heavier limp (a 0.4 s gait) |
| `assets/models/enemies/clinker_v3.glb` | **Split-back** | the scutes split along the spine over a glowing rift, a jittery 0.3 s gait, **mirrored** |

**Why separate files and not four meshes in one GLB.** If the client spawns `clinker.glb` and does
nothing else, it gets exactly one complete creature. Four meshes in one scene would all draw on top of
each other until the engine learns to hide three of them. Each file also passes `gfa_validate.py` and the
swarm budget unchanged, because the validator counts every mesh in a file.

**How the client uses them.** Every file has the identical `GF_Swarm_v1` skeleton, the same socket
names and the same clip suffixes. Clips are named `{file_stem}_{clip}`: `clinker_move@loop`,
`clinker_v1_move@loop`, and so on. To add roster width, pick one of the four stems per spawn (meta.json
`variant_set`) and look clips up with `format!("{stem}_{clip}")`. `clinker.glb` alone is complete. These
four are looks of the one content key `clinker`. `rotmite`, `ticker` and `nullmite` are separate content
keys (the crawler-family rule in ENEMIES.md), and none of them are built here.

## Design decisions

* **Silhouette.** The creature is a hunched, eyeless infant figure fused into an obsidian carapace. The
  big skull is bowed low in front, the back is a row of overlapping scutes, and the limbs are wrong: three
  thin dark shard legs on one side and one huge **pale bone** clawed arm on the other. The arm is a fat
  upper arm, a forearm that swells and flattens into a paddle toward the knuckles (widest in the ground
  plane, where the 55° camera sees it), a knuckle-walking fist and four heavy talons, with two small
  obsidian crystals breaking through the forearm. From the game camera it reads as a dark framed shell
  with one pale club on one side: lopsided by value and by mass, not only by outline. The 40-copy crowd
  render proves that each one stays countable at horde density rather than merging into one mass.
* **The jaw is the wind-up read.** The skull is split down its flat, pale, eyeless face. The `head` bone
  is the hinged front half of the skull (the left half, or the right half on mirrored looks), and a yaw
  swings it open like a door on a vertical hinge. At rest a thin teal seam shows. In `windup` the
  creature rears up and the face splits into a wide glowing wedge, the one bright shape that shows
  "about to bite" at game size before the engine's red-white decal. In `attack` the jaw snaps shut on the
  lunge.
* **Value plan.** Three values do the work at 35 px: the violet-black obsidian mass (darker than the
  `#3A2C24` Cinder floor), a light violet-grey lip stroke that frames every scute (so the dark body
  separates from the floor instead of melting into it) and the one pale bone arm. The teal slits between
  the scutes, a few bold fissures and the split face are the glow accent, not the mass. An early pass with
  big teal panels read as "a teal thing", and a dense crack web turned to speckle at 35 px. The final
  version has 2-5 bold fissures per look, each with a painted teal glow spill.
* **Palette** (The Unmade only). Obsidian `#07060A / #1A1720`. The light plane is `#4B4658` warmed
  28 % toward the row colour `#9A5B3C` (`#614C50`): the only use of the row colour, as ENEMIES.md asks.
  The scute edges and lip strokes use obsidian light pushed brighter, `#7F7278` (`#4B4658` 26 % toward
  white, 16 % toward the row colour). The skull gets a wet-sheen light (`#7FA7A0` mixed in). Bone is
  `#6E6152 / #BDB09A / #EDE4CF`, and the big arm is the faction bone a step darker, `#AFA28D`, so a horde
  of pale fists does not outshine the heroes. Its upper arm darkens to bone shadow toward the shoulder, so
  the pale mass stays joined to the shell. The glow is ichor `#1F8F7E` rim, `#2FBFA8` hot and `#B8FFE8`
  core, with the core only right at `fx_core`. There are no player colours, no `#7CFF6B` and no red-white.
* **Paint.** This is the gf_assets NPR painter: flat value planes per facet and per part, cavity darks,
  broken brushy edge strokes and low-frequency brush value shifts, with no baked light direction. Each
  scute's flared rear lip also carries a painted crest stroke (a line decal, `Build._lip_strokes`): it
  follows the jagged lip, wobbles a few mm, stops short of the low flanks and breaks once per scute, with a
  `#614C50` halo, so it reads as a brush stroke rather than an outline. The emissive texture is separate.
  UV islands are importance-weighted (scutes 1.35×, skull 1.3×, arm 1.1×, belly and drips smaller), with
  a 3 px margin at 512 px: coverage is about 40 % instead of 24 %.
* **Size.** The body (hull and skull) is about 0.45 m wide by 0.75 m long, in line with the
  collider's 2.2-3 × 0.21 m target. The legs and the big arm reach 0.86-0.98 m across and 0.94-0.98 m
  long, and they overlap neighbours at horde density, which is allowed for swarms. The heights are
  0.46-0.74 m, or 0.21-0.34 × the 2.2 m hero: always below the knee-to-waist band.

## Art review fixes (2026-09-25, review score 7.5/10)

| Must-fix | What changed |
|---|---|
| The asymmetry did not read at game size: the legs were about 1 px and the creature read as a generic symmetric tick | The lone arm was a thin obsidian tube that read as a fourth leg. It is now a massive pale bone club (radius 0.062-0.084 m against the legs' 0.024-0.044 m, the forearm flattened 1.3× in the ground plane, a 0.21 m fist, four 0.03 m talons) in its own `arm` paint zone. At 35 px one side is a pale club and the other three thin dark legs |
| The obsidian body was nearly the floor value; only the teal seam carried the read | The scutes' edge light went from `#614C50` to `#7F7278`, and every scute's rear lip got a bold crest stroke about one game pixel wide. The teal slit spill was narrowed from 30 to 17 mm so it no longer paints over the lips. In the 1x in-game render (teal glow pixels excluded), the share of shell pixels brighter than the floor went from 30 % to 55 %, and the share of clearly light ones (luminance above 70) went from 8 % to 34 %. They form light arcs that frame each scute |

The fixes live in the shared build code, so all four looks were rebuilt, re-exported, re-validated and
re-reviewed. The skeleton, clips, sockets and file names did not change.

## Rig and clips (GF_Swarm_v1, rigid skin)

| Bone | Drives |
|---|---|
| `root` | whole-body wag (the skitter undulation), dips and the death sink |
| `body` | hull, belly, the fixed skull half, the back of the skull, the glowing maw slab, ichor drips |
| `head` | the hinged jaw half and its teeth (yaw opens it) |
| `legs_a` | front and rear leg of the three-leg side |
| `legs_b` | the middle leg **and the lone big arm**, so the arm limps with the middle leg |
| `tail` | the scutes and back crystals (they rattle and blow off in the death) |

| Clip | Length | Notes |
|---|---|---|
| `idle@loop` | 1.33-1.8 s | hunched breathing; the scutes lift and show more glow; two jaw chatters and a body twitch. Sampled every frame, so it is seamless |
| `move@loop` | 0.3-0.4 s | tripod-style skitter: the two leg groups swap with a lift, the body wags and rolls toward the unsupported side (the limp), and the jaw chatters. `move_cycle_m` is 0.55-0.65 |
| `windup` | 0.5 s | a small dip, then it rears up, the jaw splits wide and the scutes flare. Ends on the loaded pose, so the client can time-stretch it |
| `attack` | 0.5 s | a lunge of about 0.22 m and back (in place overall): the jaw snaps shut, chomps once more, then recovers |
| `hit` | 0.3 s | a flinch back: the jaw pops open, the scutes jolt, then it settles |
| `death` | 0.9 s | convulse, then the scutes blow off and the jaw half flies aside (the ichor burst is engine VFX at `fx_core`). Pieces fall and crumble, and everything shrinks to 2 % and sinks: a held final pose |

* The legs counter-rotate against body roll, pitch and bob, so the feet stay planted while the shell
  rocks over them.
* **Playback rate.** The rigid-group gait cannot plant its feet at 3.8 m/s. `move_cycle_m` in meta.json
  (0.6 m for the base) gives about 6 gait cycles per second at the row speed. That frantic flicker is
  what reads as SKITTER.
* **Sockets** (all on `body`): `hit_center`, `fx_core` (the glowing core under the scutes; the death
  burst), `fx_mouth` (in the split face) and `head_top` (status icons).
* **Facing.** The creature faces glTF +Z and stands on y = 0, so the engine turns it with
  `yaw(angle) * rot_y(PI)` (ENEMIES.md section 2).

## Metrics

| File | Tris | Height | Length × width | Textures | Texel density (median) | GLB |
|---|---|---|---|---|---|---|
| clinker | 1,004 | 0.55 m | 0.94 × 0.89 m | 512 + 512 | 205 px/m | 0.52 MB |
| clinker_v1 | 1,008 | 0.74 m | 0.94 × 0.86 m | 512 + 512 | 204 px/m | 0.54 MB |
| clinker_v2 | 1,080 | 0.46 m | 0.98 × 0.98 m | 512 + 512 | 197 px/m | 0.54 MB |
| clinker_v3 | 1,036 | 0.57 m | 0.96 × 0.89 m | 512 + 512 | 200 px/m | 0.52 MB |

The swarm budget is 600-1,500 tris (the brief asks for 600-1,200 per look). There is one material with
base colour and emissive, no Draco or meshopt, and every file passes `gfa_validate.py`. The game camera
shows about 49 px/m, so the textures are oversampled roughly 4×.

## Files

```text
art/enemies/clinker/
  README.md, status.json, .gitignore (work/)
  source/<key>.blend          model + rig + clips + final material (Git LFS)
  textures/<key>_basecolor.png, <key>_emissive.png   (Git LFS)
  reports/<key>_review.png    per look: turnaround, size vs hero, in-game 1x/3x, silhouette, key poses at
                              game size, clip key frames, textures
  reports/<key>_build_report.json
  reports/clinker_family_review.png   lineup, in-game lineup, 40-copy horde at true 1080p size (+ silhouette,
                              + the 4-player 28 m view), skitter cycle at game size
  reports/clinker_crowd.png, clinker_lineup.png
  reports/clinker_review_fix_before_after.png   the art-review fix at true game size (a one-off, kept
                              as a record; the build scripts do not regenerate it)
  work/                       local renders (git-ignored)
assets/models/enemies/<key>.glb + <key>.meta.json
tools/blender/gf_assets/enemies/clinker.py, clinker_crowd.py
```

## Rebuild

```text
set BL="C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
for %v in (base v1 v2 v3) do %BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/clinker.py -- --variant %v
%BL% -b --factory-startup --python-exit-code 1 -P tools/blender/gf_assets/enemies/clinker_crowd.py
python tools/blender/gf_assets/gfa_validate.py assets/models/enemies/clinker.glb
```

One look builds in about 20-40 s on the CPU. The crowd script imports the shipped GLBs, so it also checks
that they load, skin and animate in a glTF importer.

## Open items

* The user's visual approval of all four looks.
* Engine work (in `crates/`, not done here): load the GLB per key, pick a variant per spawn, map sim
  state to clips (`move@loop` at speed / `move_cycle_m`; `windup` time-stretched to the telegraph; `death`
  plus the ichor-burst VFX at `fx_core`). The sim's Swarmer has no wind-up state yet, so `windup` and
  `attack` are ready for a contact-bite or lunge behaviour.
