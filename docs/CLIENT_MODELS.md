# GODFORGE: authored models in the client

How `gf_client` turns the art track's GLBs (docs/ART_PIPELINE.md, docs/art/*.md) into the heroes,
weapons and enemies on screen. The simulation never sees any of this: a missing file, a slow load or
`--greybox` only changes what is drawn.

| File | What |
|---|---|
| `crates/gf_client/src/models.rs` | asset lookup by key, sidecar parsing, loading, one animation graph per asset, toon skins, weapon attach |
| `crates/gf_client/src/anim.rs` | the `Animator` (base + upper layer), the hero state machine (`HeroAnim`) and the enemy one (`EnemyAnim`) |
| `crates/gf_client/src/scene.rs` | the rigs and proxies: spawns the model under the greybox, hides the greybox once it is ready, corpses |
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
  time), the gauntlet fist / open swap frames, the default weapon, a weapon's variant node names; for enemies the
  `variant_set`, `move_cycle_m` (one number, or per loop), `events_s` / `clip_events_s`, `bounds_m` and the sockets.
* `Models::looks(kind, key, server)` answers a key's looks (its `variant_set`, the files that exist; `[key]` for a
  key with one look) and starts loading all of them.

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
| `Foe { tint, hot }` | enemies: the warm red rim. `tint` is the engine's body language over the painted material: `Flash` (a swarm hit: white-hot), `SoftFlash` (an elite or boss hit: a warm lift), `Warn` (the wind-up blink, red), `Frozen`, `Stunned`, `Status(bit)`; `hot` is the Slag King's Final Pour (every glow whiter) |

An enemy asset has one material, so a horde of one look wears at most a dozen cached handles and keeps batching
while it flashes.

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

## 7. Enemies

**Spawn.** `scene::sync_enemy_models` preloads the run biome's roster (every look of every enemy key of the
biome) when the biome changes, so a horde surge never waits on a file. Each enemy proxy (`scene::Visual`) picks
its look once: `variant_set[hash(NetId) % n]` (clinker ×4, cinderling ×3). The model spawns under the proxy
at unit scale (the art is authored at game size; `bounds_m` only rescales a model whose footprint is outside
0.7-5 × the collider's diameter, none today), turned by π (creatures face +Z), with its origin on the ground
under a hovering greybox (the emberwisp's hover is in its clips). Once its materials and first pose are in, the
greybox body, ink hull, eyes and accents hide; the elite / boss ring and the contact shadow stay. Hits spark at
the model's `hit_center`.

**The proxy** eases its facing toward the replicated one (16/s swarm, 9/s elite, 4/s boss) or toward an
attack's direction (`Visual::face_override`); a model drops the greybox's wind-up throb and bob and keeps a
third of its hit squash. A horde spawn (`EntityFlags::EMERGING`) rises out of the ground over `emerge_time`.

**Corpses.** A proxy that leaves the snapshot within 1 s of its `GameEvent::Kill` stays as a `scene::Corpse`: its
model plays `death` (held), then the proxy sinks and despawns (swarm 0.3 s after the clip, elite 1.6 s, boss 4 s;
a swarm's contact shadow goes with it). A Bomber that leaves while `PRIMED` (the fuse ran out, no kill) plays its
`attack`, the detonation. A room change takes the corpses with it.

**The state machine** (`EnemyAnim`, on the model; reads the proxy, the flags, this frame's fresh entities and
`GameEvent`s):

| Sim state | Clip |
|---|---|
| rendered ground speed ≥ 0.45 m/s (off below 0.2) | `move@loop` at `speed / move_cycle_m` cycles per second, else `idle@loop` (0.92-1.08×, each enemy starts its loops at its own offset) |
| Charger `WINDUP` / `CHARGING` | `windup` stretched to the telegraph's wind-up and held; `attack` launches the charge, then `charge@loop` while it lasts |
| Caster `WINDUP` | `windup`, `channel@loop`, then `attack` timed so its `beam_fire` key lands on the beam's resolve |
| Bomber `PRIMED` | `windup` (in half the fuse), then `primed@loop`; the corpse plays `attack` |
| Lobber: its circle telegraph appears (matched by size and range) | `windup` in the first ~45 % of the telegraph, then `attack`: the glob flies for the rest |
| Support | `cast` every `interval`, synced to its own `SHIELDED` rising |
| Chaser / Swarmer / Support touching a hero | `attack` (the bite, the shield bash after a quick `windup`), every 0.8-1.5 s |
| `GameEvent::Hit` | `hit` (swarm at most every 0.45 s, elite 1.1 s, a boss only on a crit every 7 s and only when idle) |
| `GameEvent::PlatesShattered` (anvil brute) | `plates_break` once the wind-up or charge is over |
| an enemy whose model is up within 0.35 s of its appearing (a summoned add, a horde spawn, a pack) | `spawn` first, when the model has it (the cinderlings pop from their ember) |
| `EntityFlags::FROZEN` (the time stop) | the pose holds |

**Bosses** (`Brain::Boss`, the `bosses.ron` script). The phase follows the HP fraction the way the sim computes
it (`GameEvent::BossPhase` is lossy); entering phase 2 plays `phase2`, phase 3 `phase3` (the Slag King), locked
until the burst. From phase 2 on every clip resolves to `<clip>_p2` when the model has it. Attacks are read from
what this frame's snapshot brings, since the sim does not name them:

* a telegraph whose shape and size match one of the script's attacks (`Strike` → `strike_<shape>`,
  `SlamTrail` → `slam_trail`, `Pools` → `pools`), heroes' gold telegraphs excluded;
* five or more fresh enemy shots around the boss → `radial` (started at its `release` key);
* two or more fresh adds around it → `summon` (started at its first `spawn` key).

The clip's impact key is stretched onto the telegraph's wind-up (0.6-1.8×; pools fling at 60 % of it), a cone or
a line faces its direction, the rest face the nearest hero; a boss squares up to its target between attacks. A
new attack may cut the previous one after its impact. The Slag King's `crown_spin` joint turns 75°/s in Slagfall,
150°/s in the Final Pour (twice that during `radial`), after the animation; the Final Pour wears `hot`. The
anvil brute's plate joints are set after the animation too: intact, cracked in `crack_order` as the estimated
wear (Hit amounts × 1.5 Kinetic, × 0.5 else) passes `crack_at`, stripped once `PLATED` is gone.

**LOD.** An off-screen swarm enemy (12 % margin) detaches its `AnimationGraphHandle`: Bevy then neither
advances nor evaluates its skeleton (elites and bosses always animate). `GODFORGE_ENEMY_LOD=0` turns it off to
measure it.

## 8. QA

```sh
godforge --autoplay --bots 3 --phase ea --character brax --anim-log   # the clip-state log: every base change, every upper clip, and every elite, boss, lob and fuse
godforge --phase ea --character valdris --anim-gallery 0              # the local hero plays every clip, 2.5 s each (one-shots held on their key frame), facing the camera
godforge --phase ea --enemy-gallery 0                                 # every enemy look of the biome in a row 3 m below the hero, all playing the same clip (the log names each one's sim position)
godforge --greybox                                                    # no models
godforge --autoplay --bots 3 --start-at warlord --anim-log            # The Bellows; --room cinder_throne --seed 3 for the Slag King
```

`GF_CAM_AT="x,y"` pins the camera (the enemy gallery), `GODFORGE_ENEMY_LOD=0` turns the animation LOD off.
