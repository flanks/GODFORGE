# GODFORGE — Architecture

> Rust 1.96 · Bevy **=0.20.0-rc.1** (pinned) · host-authoritative 4-player co-op · data-driven content.
> This document is the contract every contributor codes against. Section references (§n) point at
> the master creation prompt.

## 1. Principles → mechanisms

| Principle (source) | Mechanism in this codebase |
|---|---|
| Engine isolation; Bevy churn is the #1 schedule risk (§14, §18) | Bevy is named in **one line** of the workspace manifest. Only `gf_engine` uses Bevy APIs directly; the rules, content and netcode crates don't depend on Bevy at all. |
| Co-op from day one; no single-player code paths (§20.3) | The host's own player connects to the sim over a **loopback transport**. Solo, listen server and dedicated bot runs all go through `NetServer` / `NetClient`. |
| Data-driven everything (§20.2, §20.9) | Every number lives in `assets/content/*.ron`, most of it generated from `content/sheets/*.csv`. It is validated at import and on load, and its hash is exchanged in the handshake. |
| One aim abstraction (§20.11) | `gf_core::aim`: target selection → aim solution → fire. AUTO, ASSISTED and MANUAL are three parameter sets (`aim_modes.ron`) over one pipeline. Weapon code never branches on the mode. |
| Readability budget (§5, §20.4) | VFX tiers (`Full → Reduced → Silhouette`) are driven by the live effect count (`game.ron: vfx`). Ally effects render at reduced alpha. Telegraphs are always danger red-white; player-side zones are always gold. |
| Test rigs (§20.7) | Headless bots play real runs through the real netcode (`--bot-run`). A stress scene holds 4 bots against 400 enemies (`--stress`). Both run as CI gates. |
| Roster scalability (§20.10) | A character is rows in `characters.csv` + `character_trees.csv` + a kit in `kits.ron` (ability steps are data). Adding one needs no code changes. |
| Determinism (weekly seeds, §11.5) | Single-threaded fixed-order `SimTick` schedule, `gf_core::rng` (xoshiro256++ seeded through SplitMix64, fully specified in-tree and pinned by golden-value tests), fixed 60 Hz step. Same seed + inputs ⇒ bit-identical run (tested). |

## 2. Crate graph

```mermaid
graph TD
  core[gf_core<br/><i>rules, pure Rust</i>]
  content[gf_content<br/><i>schema · loader · validator</i>]
  net[gf_net<br/><i>protocol · delta · transports</i>]
  engine[gf_engine<br/><i>the only Bevy consumer</i>]
  sim[gf_sim<br/><i>authoritative ECS sim + bots</i>]
  client[gf_client<br/><i>presentation · input · prediction · UI</i>]
  game[gf_game<br/><i>binary: play / host / join / bot-run / stress</i>]
  tools[gf_tools<br/><i>gf-content CLI: import · validate · audit</i>]
  content --> core
  net --> core
  sim --> core & content & net & engine
  client --> core & content & net & sim & engine
  game --> client & sim & content & engine
  tools --> content & core
```

| Crate | Depends on Bevy? | Responsibility |
|---|---|---|
| `gf_core` | no | Forge (chassis + Core/Mechanism/Relic/Sigil; equip/fuse/reroll/salvage; recipes), modifier vocabulary + rarity scaling, weapon compilation, DPS preview, aim policies, damage/status model, elemental synergies, party scaling + Chaos Tiers, Team Overdrive, Soul-Tether revive, shared movement step, deterministic RNG. 85 unit tests. |
| `gf_content` | no | Typed schema for every table, RON loader, cross-reference validation, phase gating (P0/P1/EA/V1), content hash. |
| `gf_net` | no | Wire protocol, entity-level delta snapshots against acked baselines, quantization, loopback transport with simulated latency/jitter/loss, UDP transport, `CompositeServer` (loopback host player + UDP remotes). |
| `gf_engine` | **yes** | Bevy re-export (`prelude`), the deterministic schedule helper, and (feature `client`) window/camera/UI/screenshot adapters that absorb API churn. |
| `gf_sim` | via `gf_engine` | Headless 60 Hz ECS simulation: players, kits, weapons, projectiles, enemies + bosses, director, anvils, boons, drops, run flow, snapshots. Includes `SimServer` (host loop) and `bot` (bot brains + `run_headless`). |
| `gf_client` | via `gf_engine` | Input devices → intent, prediction + reconciliation, scene proxies, VFX, HUD, forge/boon/door/end panels. It never simulates the game. |
| `gf_game` | via `gf_engine` | The `godforge` executable (CLI modes below). |
| `gf_tools` | no | `gf-content`: CSV → RON import (`--check` for CI), validation report, 100-hour audit. |

Bevy features: the sim needs only `std` + `bevy_log` (plus the ECS/app core). The client adds
`3d`, `ui`, input devices, `default_font` and `png` through `gf_engine/client`. A headless host
therefore links no renderer, windowing or audio.

## 3. Runtime topology

```text
            ┌──────────────────────────── host process ────────────────────────────┐
            │  SimServer thread (60 Hz, fixed)                                      │
            │   NetServer ── CompositeServer ─┬─ loopback  ◄──► local NetClient ────┼─► gf_client (render, input)
            │   SimTick schedule              └─ UdpServer ◄──► remote NetClient ───┼─► remote gf_client
            └──────────────────────────────────────────────────────────────────────┘
```

* **Solo** = `Connect::Local`: the sim thread uses a loopback listener, and the client connects to it.
* **Host** = `Connect::Host`: a `CompositeServer` fans in loopback (even peer ids) and UDP (odd peer ids).
* **Join** = `Connect::Join`: a UDP client to a remote host. If the host can't be reached it falls back to solo.
* **Bots / CI** = `bot::run_headless`: the same `SimServer` plus N `NetClient`s driven by `BotBrain`.
  Over an ideal link it fast-forwards (a 25-minute run takes seconds). With `--rtt` / `--loss` it
  runs in real time over a lossy loopback that counts as *remote*, so it exercises the 20 Hz path.
* **Bot teammates** (`--bots N` in a windowed session) = `bot::spawn_bot_party`: extra loopback clients of
  your own host on a separate thread. They fill a co-op party for play-testing and capture.

Steam Datagram Relay plugs in as a third `ServerTransport` / `ClientTransport` implementation
(steamworks-rs `NetworkingSockets`). Lobbies, invites and rich presence live in the client shell.
Nothing in the protocol or sim changes.

## 4. The tick (host)

`SimServer::step` runs these steps each tick:

1. Poll the transport and apply joins and leaves (join-in-progress is allowed by default).
2. Feed each client's newest commands into `PlayerInput`. Edge inputs are **press counters**,
   so they are never lost or doubled, and actions arrive **reliably** over the unreliable stream.
3. Run `SimTick` in fixed order: `Input → Players → Enemies → Spatial → Weapons → Combat → Damage → World → Cleanup`.
4. Stream snapshots at a **per-client rate**. The host's own loopback player gets 60 Hz
   (`snapshot_every: 1`) and remote peers get 20 Hz (`remote_snapshot_every: 3`, §14). Cosmetic events
   are buffered per client until its next snapshot, so the slower stream never drops one. A due
   client gets a `WorldSnapshot`.
   Each client gets public state plus its private view (bag, wallet, boon offers: personal loot streams).
   The world is encoded as an entity-level delta against that client's last acked baseline.
   Projectiles carry a **motion descriptor** (`pos₀, vel, t₀`), so after their first appearance they cost 0 bytes.

Measured on this container (`--stress 400 --bots 4`, dev profile): **0.61 ms mean / 0.97 ms p99** host
tick against a 16.67 ms budget. That is roughly 17× headroom for the PC-min target and the mobile tiers.

## 5. The client frame

| Set | Systems |
|---|---|
| `Net` | `poll_link` (snapshots, roster, events; reconcile prediction) · forge toggle · UI hover capture |
| `Input` | keyboard/mouse, gamepad, touch (floating twin-stick + ≥44 px buttons) and autopilot. All of them fill one `InputState`. |
| `FixedUpdate` (60 Hz) | `send_command`: queue actions, send the command, predict the local mover with **the same `gf_core::movement::step_mover` the host runs**, and keep unacked inputs for replay. |
| `Scene` | rebuild room on `room_serial` · match `NetId → proxy` (spawn/update/despawn) · extrapolate motion-descriptor entities at the fractional render tick · ease others · telegraph fill · hit flash / status tint · player rigs at the predicted position |
| `Presentation` | camera (co-op centroid framing, room clamp, trauma² shake) · VFX (tiered particle budget) · HUD · panels · scripted screenshots |

Reconciliation replays the unacked inputs from the authoritative mover state. The correction is
kept as a decaying visual offset, so the player never sees a snap. `Link::render_tick` gives the
fractional server tick used for extrapolation.

## 6. Signature systems

### The Forge (§6)
* `WeaponBuild = chassis + [Core, Mechanism, Relic, Sigil]`. The Sigil is locked for the run (`forge.locked_slots`).
* Anvil event: an anvil room (or anvil door) spawns a **Dormant** anvil. Interacting starts **Kindling**,
  a hold-the-ring wave where progress pauses while the ring is empty. Then comes **Hot**, a forge window
  with charges; forge-focus time scale applies when every player has the panel open. Finally the anvil goes **Spent**.
* Actions: equip (free), fuse (charge; two parts → higher rarity, and a weaker donor is refused),
  reroll (charge + shards), salvage (shards). They are pure functions in `gf_core::forge::apply_action`,
  shared by the host, the bots and the **UI preview** (the panel runs the real function on a copy and shows the DPS delta).
* Named combos (`recipes.csv`) are detected from the build + element and feed the codex (72 authored).

### Boons (§7)
There are 8 gods. The Standard/Legendary/Duo/Team kinds with requirement gating are data, and
offers roll per player. Picking a boon or rerolling is a reliable `PlayerAction`.

### Aim (§5, §20.11)
One pipeline, three parameter sets. AUTO pays a damage tax (`damage_mult 0.9`) for perfect uptime.
ASSISTED adds magnetism cones and soft-lock. MANUAL enables precision hits and **Deadeye** (+2%/hit, up to +20%).
The mode can be switched live, and the HUD shows the tax or the current Deadeye bonus.
Per-weapon quirks (beam sweep, charge-to-lock) are fields in the weapon profile.

### Co-op (§10)
* Elemental synergies fire when two elements from **different sources** meet on one target within
  2.5 s (12 rules, 1.5 s per-target cooldown). Solo, your own two elements can combo at half power,
  so the system is learnable before co-op.
* Team Overdrive uses one shared meter, and any player can trigger it.
* Soul-Tether revive: a downed player drifts as a wraith for up to 20 s while any ally within 3.5 u
  channels a 3 s revive. Otherwise the Forge reforges them 10 s later, so **no one is out for more than
  30 s**. Solo runs get one Rekindle.
* Party scaling (HP, count, elites) and Chaos Tiers 1–20 are content tables.

## 7. Presentation language (§12)

Authored glTF models replace the greybox primitives wherever a file exists (§9). The primitives stay
as the fallback. The colour and readability rules are final:

* Element hues: Kinetic bone-brass, Flame orange, Storm cyan, Void violet, Plague green, Radiant gold.
* Rarity: Common parchment → Rare blue → Epic violet → **Godforged gold**. Rare+ loot gets a light beam.
* Players: P1 gold, P2 cyan, P3 violet, P4 green ground rings (`game.ron: player_colors`).
* Enemy danger: telegraphs fill red-white from the centre until they resolve, and winding-up enemies blink red.
  Enemy shots are magenta-cored so they never read as player projectiles.
* Look: a warm shadow-casting key light against a cool ambient (per biome), HDR + bloom
  (TonyMcMapface), a painterly colour grade and a UI vignette. Inverted-hull ink outlines sit on
  characters, enemies and architecture.
* NPR materials (`gf_client::materials`, embedded WESL in `src/shaders`): every lit surface is an
  `ExtendedMaterial<StandardMaterial, _>`, so Bevy's lights, shadows and fog still apply.
  - `ToonMaterial` posterizes light into flat bands with saturated cool shadows, a coloured rim and
    an ink edge. The rim is the player colour on heroes, warm red on foes and soft gold on props.
    Build new ones with `toon()` / `toon_from_standard()` and a `ToonStyle` preset.
  - `FloorMaterial` paints the floor in world space: plaza pavers around a gold mosaic, broken
    flagstones over bare ground, worn paths, soot at the walls, and the room's lava cracks as rifts.
  - `AbyssMaterial` animates the sea at y = -7 below the thick platform (`terrain.rs`): magma,
    deep water, night sky or chaos, chosen by `BiomeLook`.
  Glow, decal, additive and ink looks stay `StandardMaterial`. `palette` caches every material per
  (colour, look), so a 400-enemy horde shares a handful of handles and batches. The room seed may
  vary the paint; it never feeds the simulation.
* Type: Cinzel (variable, SIL OFL) for display capitals, titles, names and big numerals; Alegreya
  Sans Regular / Medium / Bold / Italic (SIL OFL) for body text and small numerals, with tabular
  lining figures on live numbers. DejaVu Sans / Serif Bold stay bundled only as the per-glyph
  fallback at the end of every `FontSource::List` stack. All faces are embedded with
  `include_bytes!` (`assets/fonts`), and Alegreya Sans Medium replaces Bevy's default font. The
  colour tokens and the closed type ramp live in `gf_client::theme`; the widgets, their motion and
  the embedded UI art in `gf_client::uikit` (spec: `docs/art/UI_STYLE.md`).
* Combat HUD (`gf_client::hud`, UI_STYLE §6): four corner clusters and a thin top band, built
  once on the kit and updated in place with change-only writes.
  - `hud/hearth.rs` (bottom-left): the portrait medallion with the ult ring, HP with a drain ghost
    and ward hatch, armour plates, dash lozenges, Q / E with the cooldown sweep, the Team
    Overdrive hex, the aim chip and the low-HP vignette.
  - `hud/arsenal.rs` (bottom-right): the forged weapon as a chassis hex and four part slots with
    rarity gems, the wallet and the boon chip. Nothing persistent sits in the south lane.
  - `hud/party.rs` (top-left): ally frames and the toast rail.
  - `hud/wayfinder.rs` (top-right): the objective tracker (timer, Seals, Warlord and gate, threat,
    surge, live events, next objectives; a room line on legacy rooms) under the hidden
    `uikit::MinimapFrame`, the hook OPEN_WORLD phase 3 fills.
  - `hud/top.rs`: the boss / Warlord bar, the callout lane, the region banner, the surge flash.
  - `hud/world.rs`: world-anchored prompt plates, the state banner, ally tags, elite bars, POI
    labels, downed markers and the touch overlay.
  - Edge pins are in `offscreen.rs`, damage numbers in `vfx.rs`. Every visible cluster writes its
    rect to `theme::HudRects` after layout, and pins, prompts, tags and numbers keep out of it.
  - `hud::HudFocus` is how panels hide the tracker, the Arsenal and the boon chip. The net line
    and FPS live in the debug strip (F10 or `--fps`).

## 8. Performance and LOD budgets

| Budget | Where | Default |
|---|---|---|
| Host tick | `--stress` CI gate | p99 < 16.67 ms (measured 0.97 ms @ 400 enemies) |
| Snapshot size | `RunReport.max_snapshot_bytes` | delta + motion descriptors; printed per run |
| VFX tier thresholds | `game.ron: vfx.reduced_at / silhouette_at` | 450 / 900 live effects |
| Particles per tier | `vfx.particles` | 1600 / 700 / 200 |
| Damage numbers | `vfx.rs` | own damage only, aggregated per target, ≤ 40 alive |
| Ally effect alpha | `vfx.ally_effect_alpha` | 0.55 |

Mobile tiers reuse the same knobs with different values: a separate tuning pass, same content pipeline (§14).

## 9. Art pipeline hook (Blender 5.x → glTF)

The hook is live: Brax, Valdris, seven weapon chassis and the eleven Cinder Wastes enemies play as authored,
animated GLBs. docs/CLIENT_MODELS.md has the details; the contracts are docs/art/GF_HERO_SKELETON.md,
docs/art/WEAPONS.md and docs/art/ENEMIES.md.

1. **Files.** The art track exports `assets/models/{characters,weapons,enemies}/<key>.glb` plus a
   `<key>.meta.json` sidecar (clip loop / layer / design speed / event frames, sockets, variant sets,
   `move_cycle_m`, boss phases). Keys are `CharacterDef.key`, `ChassisDef.key` and `EnemyDef.key`; clips are
   `{char}_{clip}` (`@loop` for loops) on the master skeletons `GF_Hero_v1` and `GF_Swarm_v1` (elites and bosses
   have their own rigs).
2. **Asset root.** `gf_engine::client::find_asset_dir()` roots Bevy's asset server: `GODFORGE_ASSETS`, then
   `./assets`, then `assets/` beside the exe or its parents, then the repo's `assets/` from compile time. A packaged
   build ships `assets/` beside `godforge.exe`.
3. **Lookup and fallback** (`gf_client::models`). `Models::get(kind, key)` reads the sidecar, starts the glTF
   load and answers `None` until the file and its dependencies are in. The proxy keeps its greybox while a
   file is missing, loading or failed, and always under `--greybox` / `GODFORGE_GREYBOX=1`. Once the model
   is up, the greybox body hides. Gameplay reads stay: rings, chevrons, shields, auras, tethers, telegraphs,
   name plates and x-ray. The sim never sees any of this.
4. **Materials.** Every glTF material becomes a `ToonMaterial` (`toon_from_standard`), cached per (source
   material, skin): `Hero(slot)` has the player-colour rim, `Ghost(slot)` is used while downed, `Gear(slot)` is
   for weapons, and `Foe{tint, hot}` has the warm red rim. Hit flash, wind-up blink, frozen, stunned and status
   tints are a few cached variants per enemy look, so a flashing horde still batches. Skinned meshes use the toon
   shader's painted ink edge instead of the inverted hull.
5. **Sockets.** The equipped chassis spawns as an identity child of the skeleton's `weapon_R` bone. A gauntlet
   pair re-parents its offhand to `weapon_L`. A chassis without a model keeps the greybox gun. Shots flash at
   the weapon's `muzzle` node.
6. **Animation** (`gf_client::anim`). There is one `AnimationGraph` per asset: full-body clips form the base,
   and upper-body clips sit beside it with everything below `spine_01` masked out, so a hero fires while
   running.
   * `HeroAnim` picks run, walk, strafe, backpedal or idle from the velocity versus the facing, at speed ÷
     design speed. One-shots and kit clips come from `GameEvent`s. Stance and avatar loops follow the
     `PlayerFlags`. Downed, revive, reforge_in, forge_hammer and victory follow the life and run state.
   * `EnemyAnim` plays move or idle by speed, and windup / attack from WINDUP, PRIMED and CHARGING plus the
     enemy's telegraphs. Hits flinch on throttled `Hit` events, spawn plays on EMERGING, and death plays on a
     lingering corpse proxy. Boss phases follow the HP fraction, and boss attacks are matched from their
     telegraphs.
   * Off-screen swarm enemies stop evaluating their skeletons; `GODFORGE_ENEMY_LOD=0` turns this off.
7. Recoil, aim offsets and the left hand's IK to `grip_L` stay procedural, and are still to do.

## 10. Testing

| Rig | Command | Gate |
|---|---|---|
| Unit tests | `cargo test --workspace` | rules, content, netcode, sim determinism |
| Content | `cargo run -p gf_tools -- import --check` | sheets ↔ generated RON in sync, 0 errors |
| Nightly bot run | `godforge --bot-run --bots 4 --phase ea` | no crash, no stall (must end in victory/defeat), p99 tick in budget |
| WAN soak | `godforge --bot-run --bots 4 --phase ea --rtt 100 --loss 0.02 --minutes 5` | real time, 20 Hz snapshots: clears rooms without a wipe |
| Chaos stress | `godforge --stress 400 --bots 4` | p99 tick < 16.67 ms |
| Attack-mode parity | `godforge --bot-run --aim auto --seed 7` vs `--aim manual --seed 7` | both complete (acceptance #8) |
| Client smoke | `godforge --autoplay --screenshot shot.png --shots 4` | renders under Xvfb/lavapipe |
| Peak-horde look | `godforge --autoplay --bots 3 --horde 400 --fps` | holds 400 enemies in a windowed session; logs FPS and worst frame |

## 11. Known gaps (tracked for P2)

* Steamworks glue (SDR transport, lobbies, achievements, cloud saves): the transport traits and the
  achievement table are ready, but the SDK integration isn't written yet.
* Lag compensation for hitscan and beams. Projectile hits already resolve on the host.
* Meta hub (Altar of Ember, character trees), Echo drones and barks: fully authored and validated
  as data, but not yet wired into systems. Their P2 hooks are `gf_content::{AltarNode, TreeNode, EchoTuning, BarkDef}`.
* Audio.
* Authored glTF art for Selene, Kael, Thessaly, the remaining chassis and the other biomes' enemies. These
  keep the greybox until their files land (§9).
