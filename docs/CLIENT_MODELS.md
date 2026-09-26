# GODFORGE: authored models in the client

How `gf_client` turns the art track's GLBs (docs/ART_PIPELINE.md, docs/art/*.md) into the heroes,
weapons and enemies on screen. The simulation never sees any of this: a missing file, a slow load or
`--greybox` only changes what is drawn.

| File | What |
|---|---|
| `crates/gf_client/src/models.rs` | asset lookup by key, sidecar parsing, loading, one animation graph per asset, toon skins, weapon attach |
| `crates/gf_client/src/anim.rs` | the `Animator` (base + upper layer) and the hero state machine (`HeroAnim`) |
| `crates/gf_client/src/scene.rs` | the rigs: spawns the model under the greybox rig, hides the greybox once it is ready |
| `crates/gf_engine/src/client.rs` | `find_asset_dir` / `asset_plugin`: where the asset server reads from |

## 1. Where assets load from

`gf_engine::client::default_plugins` roots Bevy's asset server at `find_asset_dir()`, searched in order:

1. `GODFORGE_ASSETS` (an explicit path);
2. `./assets` when it holds the game's content or models (running from the repository root, or from a worktree);
3. `assets/` next to the executable, then beside each of its parents up to four levels up
   (`target/release/godforge.exe`, or a copy of it inside the repository);
4. the repository's `assets/` as `gf_engine` was compiled from it (a copied exe run from anywhere on the dev machine).

A packaged build ships `godforge.exe` beside `assets/` (`assets/content`, `assets/models`, `assets/fonts`, …);
`gf_content::find_content_dir` finds `assets/content` the same way. The first log lines say which root won:
`models: asset root D:\GODFORGE\assets`.

## 2. Lookup, fallback, `--greybox`

* A key maps to `models/<kind>/<key>.glb` + `<key>.meta.json`: `characters/<CharacterDef.key>`,
  `weapons/<ChassisDef.key>`, `enemies/<EnemyDef.key>`.
* `Models::get(kind, key, server)` reads the sidecar and starts the glTF load on the first call, and answers
  `None` until the file and all its dependencies are in (about 0.4 s for a hero). `Models::missing` tells a key
  without a file (or a failed load) from one still loading. Until then the caller keeps its greybox.
* `--greybox` (or `GODFORGE_GREYBOX=1`) turns every model off: the QA view of the greybox look.
* The sidecar gives the clip info the GLB cannot: loop, layer (`full` / `upper`), design speed, events (frame and
  time), the gauntlet fist / open swap frames, the default weapon, a weapon's variant node names.

## 3. Materials: toon skins

Every mesh of a spawned instance swaps its glTF `StandardMaterial` for a `ToonMaterial`
(`materials::toon_from_standard`: the painted textures, the normal map and the emissive stay; the toon ramp,
the rim, the ink edge and the brush noise are added). The toon materials are cached per
(source material, `Skin`), so every hero in slot 2 shares one handle and a horde of one enemy shares a few:

| Skin | Look |
|---|---|
| `Hero(slot)` | the hero style with a rim in the player's colour, narrower than the greybox's (a sculpted body has far more silhouette), a painted ink edge (a skinned mesh cannot take the greybox's inverted hull) |
| `Ghost(slot)` | downed (the Soul-Tether wraith): translucent, glowing in the player's colour; the weapon wears it too |
| `Gear(slot)` | the hero's weapon: a quieter rim in the player's colour |
| `Foe` | enemies: the warm red rim |

## 4. Heroes

* The model spawns under the rig root once loaded (the greybox shows meanwhile), hidden until its materials are
  swapped and its first pose is set; then the greybox body, head, ink hulls and belt hide. The rings, chevron,
  shield, aura, tether, x-ray, name plates and the aim pivot stay.
* Scale 1:1 (the art is authored at game size, 2.2-2.33 m); the root stands on the rig origin (the sim position,
  `PlayerView.height` for leaps) and the rig scale carries the avatars (Meltdown 1.25, Mountainfall 1.8).
* Facing: glTF heroes face +Z, the engine's meshes -Z, so the model turns by `yaw(facing) * rot_y(PI)`. The
  facing eases toward the aim (14/s; the dash direction at 30/s during a dash, the leap or charge direction
  during those clips, the drift direction while downed).
* The x-ray proxies (the hero's silhouette through a boss or a monument) slide 1.25 m toward the lens: the camera
  is orthographic, so they stay put on screen, but the hero's own mesh no longer hides them. An occluder closer
  than that in front of the hero does not trigger the x-ray.

## 5. Weapons

* The equipped chassis (`PlayerView.weapon.chassis`) spawns as an **identity child of the `weapon_R` socket**
  (docs/art/GF_HERO_SKELETON.md §3: no correction rotation).
* A pair (the anvil_gauntlets) re-parents its `offhand` node to `weapon_L`, identity again. Its open-hand meshes
  start hidden and swap per hand at the frames of the clip in charge of the arms (`ping` opens the right hand).
* A chassis without a model keeps the rig's greybox gun on the aim pivot. A chassis change swaps the model.
* Each `GameEvent::Shot` flashes at the weapon's `muzzle` node (`vfx.rs`), or at the greybox gun's muzzle.
* Not done: the left hand's IK to a two-handed weapon's `grip_L`; recoil and aim offsets (procedural, ARCHITECTURE §9).

## 6. Animation

**The graph.** One `AnimationGraph` per asset, shared by its instances: full-body clips under a base blend node,
upper-layer clips beside it on the root with the lower body masked out (mask group 0 = every animation target
that is neither `spine_01` nor below it, filled from the first instance). Bevy blends siblings by normalised
weight, so an upper clip at fade `a` gets the weight `a / (1 - a)` against the base's 1: at `a = 1` the upper
body is the clip's, the legs keep the base (the run, a stance).

**The hero state machine** (`HeroAnim`, reads the snapshot and `GameEvent`s):

| Sim state | Clip |
|---|---|
| ground speed ≥ 0.6 m/s, within 45° of the facing | `run` (`walk` below ~55 % of move speed), playback = speed / (design speed × rig scale) |
| 45-135° left / right, beyond 135° | `strafe_left` / `strafe_right`, `backpedal` (10° hysteresis, 0.14 s dwell) |
| standing, an enemy within 13 m or a shot / hit in the last 2.5 s | `idle_combat` (the avatar loop under Meltdown / Mountainfall) |
| standing, out of combat | `idle`, `idle_signature` after 6 s |
| `MoverState.dash_left > 0` | `dash` (faces the dash), then `dash_recover` if the hero stops |
| `GameEvent::Shot` (auto / charge chassis) | `fire_light`, `fire_heavy` (charge, or < 1 shot/s); Valdris in Siege Stance: `siege_fire` |
| a melee swing (`PlayerView.firing` on a melee chassis) | Brax: `jab_l`, `jab_r`, every third `hook` |
| charging (`PlayerView.charge`), a beam burning | `fire_charge@loop` (upper) |
| `GameEvent::PlayerHurt` | `hit_light` (upper), `hit_heavy` at ≥ 10 % of max HP |
| `GameEvent::Ping`, `ArmorBreak` | `ping`, `armor_break` (upper) |
| `GameEvent::Ability` | Brax: `uppercut`; `furnace_rush@loop` for 0.4 s then `furnace_rush_end`. Valdris: `bulwark_slam` from its `launch` event (the sim's leap starts on cast) |
| `PlayerFlags::STANCE` rises / falls | `siege_stance_enter`, `siege_stance@loop` (replaces idles and locomotion), `siege_stance_exit` |
| `PlayerFlags::AVATAR` rises | `meltdown_start` / `mountainfall_start`; Mountainfall layers `mountainfall_pound` every 1.1 s, its `pound` event on the sim's pulse |
| `LifeState::Downed` begins | `death`, then `downed@loop` with the ghost skin |
| Downed → Alive, Reforging → Alive | `revive`, `reforge_in` |
| `GameEvent::PoiStarted` (standing) | `interact` |
| `PlayerView.forge_open`, standing (Siege Stance wins) | `forge_hammer@loop` |
| `RunPhase::Victory` | `victory` (holds its last frame) |

Full-body one-shots hand the body back to locomotion when the hero moves on after a short while (the sim never
roots a cast), so a long clip never slides. Unused for now: `knockdown` / `get_up` (the snapshot carries no
player stun), `heat_vent` (Brax's Heat Gauge is not replicated).

## 7. QA

```sh
godforge --autoplay --bots 3 --phase ea --character brax --anim-log   # the clip-state log: every base change, every upper clip
godforge --phase ea --character valdris --anim-gallery 0              # the local hero plays every clip, 2.5 s each (one-shots held on their key frame), facing the camera
godforge --greybox                                                    # no models
```
