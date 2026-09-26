# GODFORGE: Open Biomes (NIMRODS-style exploration)

> **Status: decided, 2026-09-25. Phases 1 and 2 are done (2026-09-26). The composition pass
> (§3.6) comes next, then phase 3.** This is the single design for replacing the Hades-style room
> run with one huge generated map per biome.
> It merges two competing proposals (see §1) and is written against the code at `c0bddae` (the
> room-scale layout grammar merge). Implementation agents execute it phase by phase (§10) without
> re-deciding anything. Every number here is a data default in `assets/content/*.ron` and is tuned
> from bot telemetry, not changed in code.
>
> **Progress.**
> * **Phase 1 (done):** 1A collision index and pits (`55b6b63`), 1B map-scale bot nav (`23333c8`),
>   1C schema, worldgen stub and previews (`9c3c435`).
> * **Phase 2 (done):** step 2.0 protocol v3 (`4e77e6f`), lanes 2A–2F (`dae3374`, `dccf911`,
>   `7ce1937`, `165ad4e`, `7a37331`, `ca93cda`), and Cinder flipped to its map with 7 Seals
>   (`cc7d736`). `layout-stats --maps --seeds 8`: 0 repairs, 0 relaxed.
> * **Post-phase-2 art and readability pass (done):** an art critique of the Cinder map (3.5/10)
>   was acted on in `2f47f8f`…`1c41630`. It pulled a few later items forward, so the phase 3 and 4
>   lanes should build on them instead of redoing them:
>   - 3F: off-screen markers already show the Boss Gate and the 3 nearest Seal POIs (pool 16); every
>     incomplete Seal POI keeps a dim 40 u beacon (bright while live); the "room x/y" banner is
>     the stage line on maps; the region banner shows the name of each region entered; the
>     arsenal is a slim strip that fades over fights; toasts live on a left rail (2 lines); ally
>     tags show names only when hurt; heroes show an x-ray silhouette through whatever hides them;
>     at most 10 ally ground fields draw at once; each POI kind has a stand-in silhouette at its
>     heart (altar, chest, crystal lode, basin, pyre, skull stakes, war totem, seal pedestal).
>     Still open for 3F: POIs where an ally is present, pings and surges in the marker priority,
>     the final `poi_visuals.rs` models, the fade, emerge.
>   - 4A: POI set pieces (shrine statue, anvil chain posts, reliquary plinths, vein crystals, lair
>     walls, spring stones), waymarks at crossroads (`Decor::Waymark`, the objective's colour), a
>     tall piece every ~25 u along roads, theme story clusters in the density top-up, road braziers
>     30–40 u apart, hub monuments on the hub's north rim. §3.6 supersedes three of these: the tall
>     road pieces are off by default, the story clusters move onto the frame (one per region), and
>     the spring stones become a painted ring. It also drops the clearing entry arches (§3.2 step
>     10).
>   - 4B / 4C: `FallenWeapon` joins Cinder's landmarks (0.7× height); region themes gained
>     `names` (a pool the regions of one theme take in turn) and `ground` (paving offset, ash
>     drifts) for the floor; the rim-lit coast lip, hot river banks and thick bridge decks landed.
>   - 2A follow-up: river and chasm bands take one integer chamfer pass (45° reaches, not L
>     shapes). The golden hash is `0xca3521382f4a6edd` (re-pinned for the new dressing streams
>     and the chamfer).
> * **Composition pass (specified 2026-09-26 in §3.6; next, before the phase 3 lanes):** the user
>   found the map cluttered with pillars and walls and pointed at Hades II. The density top-up
>   goes. Compositions back onto the coast and region borders, the shore gets a mostly visual
>   frame, open fields keep at most one kiting anchor, and floor detail becomes paint. The EA room
>   grammar follows the same rules. Targets are in §3.6.2 and acceptance in §3.6.12.

## 0. The decision in one page

**Backbone: a biome map is one generated room.** A new room kind, `Expedition`, is laid out by a new
generator (`gf_content::worldgen`) from `(template, seed)`, exactly like today's procedural arenas.
Everything already keyed on "the current room" keeps working unchanged:

* the host replicates `(room, room_seed, room_serial)`; every client and bot rebuilds the same map
  with `procgen::resolve_room` (`CurrentRoom::sync`, the bot `RoomCache`);
* `load_room` / `RoomScoped` / `room_transition`, the `Onward` door, the authored boss arenas (seed 0);
* `RunPhase` (the map is played in `Combat`), `--room key~seed` QA, and the headless test that checks
  every peer rebuilds the host's layout.

The run becomes `biomes.ron: sequence: [Fixed(Expedition), Fixed(Boss)]`. Legacy door sequences stay
valid data (QA, EA biomes until phase 4), so there is **no dual-mode switch** to maintain.

**Grafted on top** (the parts that make it NIMRODS and AAA):

| Topic | Decision |
|---|---|
| Map | ~10×10 screens: Cinder 432×272 u, EA 448×280/288 u, Unmaking 480×304 u. Fits `QPos` (±256 u) with no wire change. |
| Terrain | A 4 u **tile land mask**: coast bays, chasms and liquid rivers are *pits* (walkers blocked, shots fly over), with bridges at road crossings. The client draws real cliffs to the abyss. |
| Places | Voronoi **regions** with themes. Each region's slots are filled with the **existing room-grammar compositions** (`procgen::stamp`: forge halls, slag channels, cloisters, broken stairs…), POI clearings reuse the plaza/arch/monument pieces, and grand monuments form a skyline. |
| Objectives | **Seals** from Anvils, Lairs, Shrines, Reliquaries, Veins and the **Warlord** (the biome mini-boss, worth 2 and required). The Boss Gate opens at `seals_required`. Springs, Watchfires and Camps give no Seals. |
| Horde | Director v2 runs **per player cluster**. Spawns land on a rectangle ring just outside *every* player's view footprint. Density and HP scale with cluster size. A **threat clock** (time + heat) drives escalation, plus surges and gate frenzy. Far stragglers are culled and refunded. **Flow fields** route the horde over bridges. The hard cap stays at **400 alive**. |
| Co-op split | Reforge next to the nearest ally. A "hopeless" tether shortens the wait. A Hot anvil is a sanctuary (Forge Aegis). Loot drops only for players near the kill, and parts don't rot while their owner is near. Forge-focus slow-mo keeps today's rule. |
| Netcode | Protocol v3: `EntityKind::Poi`, `RunView.stage`, `PrivateView.anvil/boss`. **Per-client interest management** with event compaction arrives in phase 3. |
| Client | 32 u chunks, **merged meshes per material**, and an env kit that renders the whole `Decor` vocabulary. Plus a fog-of-war mist layer, a minimap, a full map with pings, POI beacons, off-screen markers and an objective tracker. |
| Bots | Tile A* for long hauls plus the existing fine A*, and a utility planner with `group` (default) and `split` policies. |
| Phases | 1 Foundations → 2 The Cinder map end to end (flip Cinder) → 3 Co-op on a big map + exploration UX → 4 AAA map pass + EA biomes → 5 Hardening. |

---

## 1. How the two designs were judged

Both proposals were checked against the code. Both were written before `c0bddae` landed, which
turned `procgen.rs` into a 2,600-line composition grammar with a rich `Decor` vocabulary and a PNG
preview tool. The final design reuses that work at map scale instead of inventing parallel content
tables.

**Why B's backbone.** Every piece of replication and room plumbing already works generically on
`(template, seed, serial)`: `snapshot::run_view`, `CurrentRoom::sync` (`net.rs:158`), `BotBrain::room`
(`bot.rs:86`), `parse_room_request` (`run.rs:103`) and `every_peer_rebuilds_the_hosts_procedural_arenas`
(`tests/headless.rs:99`). Design A would rename `RunPhase`, restructure `RunView`, add a `StageDef`
path through every client system, and carry a `Rooms | OpenWorld` mode switch for three phases.
That is churn with no player-visible gain.

**Why A's map, horde, netcode and split-party ideas.** B's own trap table is right about the
hotspots, but its answers are too thin for AAA maps and split co-op:

| Claim | Verdict (checked in code) |
|---|---|
| Obstacle queries are O(all obstacles): `Arena::resolve` (`movement.rs:109`), shot blocking (`projectiles.rs:124, 361`), AUTO occluders (`weapons.rs:96`), bot whiskers (`bot.rs:255, 319`) | **True** (both). Fixed by `ObstacleIndex` (§4.1). |
| `NavGrid::new` tests every cell against every obstacle (`nav.rs:36`); A* has no cap | **True** (B). Rasterize by AABB, cap expansions. |
| Parts never age during `Combat` (`players.rs:480`), so they pile up on a map | **True** (both). |
| Single-anvil assumptions: `run_view` takes the first anvil (`snapshot.rs:267`), Spent zeroes *everyone's* charges (`anvil.rs:92`), the client animates only `run.anvil.id` (`scene.rs:1287`) | **True** (both). |
| `BoonChoice` holds one offer (`components.rs:234`) | **True** (B). Add a queue. |
| `send_command` clones the prediction arena every fixed tick (`net.rs`, `let arena = pred.arena.clone()`) | **True** (B). Use `Arc<Arena>`. |
| Every player rolls a part on every kill at the kill position (`damage.rs`, "Personal loot") | **True**, and missed by B: a split partner 300 u away gets parts they can never reach. Loot-share radius (§5.9). |
| `Around { 27, 34 }` spawns "just off-screen" (B) | **False.** At 4P the ground footprint is ≈ 49.8 × 34.2 u (view height 28 at 16:9, pitch 55°), so a point 27 u away toward a corner is on screen. Also the camera leans toward allies (`camera.rs:118`). A's view-footprint rectangle ring is used. |
| Coast as ~500 rock circles, ridges as ~650 circles (B) | **Rejected.** It bloats collision and draw calls. The tile land mask gives the existing cliff and abyss look for free, and chasms and rivers from day one. |
| Stamps from authored rooms (B) | **Superseded.** Authored rooms hold 2–5 obstacles. The new grammar's `stamp(kind, frame)` compositions are the real prefabs. |
| "Commit the in-flight NPR edits first" (B); "pending floor.wesl work, NEXT_SESSION §3b" (A) | **Stale** in both. The NPR materials are committed (`69fa94b`, `63d2f3d`) and registered, and `git status` shows the client clean. |
| `SpatialGrid` cell is 2.5 u and needs a CSR rewrite (A) | **False.** The cell is 2.0 u (`enemies.rs:632`), and clearing 31k cells costs about 30 µs. It is kept as is. |
| "36 non-boss templates" (A) | rooms.ron has 42 templates: 4 Boss and 38 others. |
| Bandwidth "60–110 KB/s at 4P peak, like today" (A) | **Optimistic.** The measured max snapshot is 15.0 KB at 400 enemies (VERTICAL_SLICE §4), which is up to ~300 KB/s at 20 Hz. Events (Hit spam) are a large share. Adopted: interest management **plus** event compaction (§6.3). |
| "same_seed_same_run baselines must be regenerated" (A and B) | **False.** The test compares two runs of one seed, and no values are stored. |
| No interest management until measured (B) | **Rejected.** 15 KB × 20 Hz × 3 remote peers is ~0.9 MB/s host upload at peak, and a split party gets nothing from the global cap. It is scheduled in phase 3. |
| Party-wide objective rewards (B) | **Rejected.** B itself notes that splitting becomes optimal. Rewards use scopes instead (§2.4). |

---

## 2. Player-facing loop

### 2.1 Beat sheet (one biome)

1. **Landfall.** The party arrives at the *Landing*, a plaza on a seed-chosen map edge with a Healing
   Spring nearby. A banner names the region ("THE SLAG FLATS"). Fog covers the map, and the tall
   silhouettes of grand monuments rise above it.
2. **The pull.** Paved roads lead out of the Landing, and every road ends at a POI, a pass or another
   region. The first anvil stands in a region adjacent to the Landing, so the Forge loop starts
   within about 90 s.
3. **Spread or stick.** Seals come from any seal-bearing POI. The Warlord is mandatory and sits on the
   route toward the gate. Optional power (more shrines and reliquaries) costs time and **heat**. Co-op
   parties choose between splitting to cover the map and grouping for safety, synergies and tether
   revives (§5.9).
4. **The gate opens** at `seals_required` (Warlord included), or is forced open as *Unworthy* at
   `gate_force_minute`. A map-wide beacon lights, and *Gate Frenzy* raises the horde.
5. **Gathering.** Anyone interacts inside the gate ring, which starts a 10 s countdown (2 s solo). The
   countdown ends early if every living player is inside the ring. At zero, downed players are revived
   at 50 %, owned pickups are granted ("spoils carried through"), and the whole party moves to the
   boss arena.
6. **The boss** is today's authored arena, `load_room` path and `boss_ai`. Then comes the existing
   `Cleared` → `Onward` door → the next biome's map, or Victory.

### 2.2 Pacing targets

| Biome | Phase | Size (u) | Screens | Regions | Anvil / Warlord / Lair / Shrine / Reliquary / Vein | Spring / Watchfire | Seals avail / req | Gate force | Camps | Target (humans) |
|---|---|---|---|---|---|---|---|---|---|---|
| Cinder Wastes | P0/P1 | 432 × 272 | 9.6 × 9.7 | 5 × 3 | 3 / 1 / 2 / 3 / 2 / 2 | 3 / 4 | 14 / 7 | 12:00 | ~29 | 8–10 min + boss 2–3 |
| Verdant Ruin | EA | 448 × 280 | 10 × 10 | 5 × 3 | 3 / 1 / 3 / 3 / 2 / 2 | 3 / 4 | 15 / 7 | 13:00 | ~31 | 9–11 + 3 |
| Hollow Spire | EA | 448 × 288 | 10 × 10.3 | 5 × 4 | 3 / 1 / 3 / 3 / 3 / 2 | 3 / 4 | 16 / 7 | 13:00 | ~32 | 9–11 + 3 |
| The Unmaking | V1 | 480 × 304 | 10.7 × 10.9 | 6 × 4 | 4 / 1 / 3 / 3 / 3 / 3 | 3 / 4 | 18 / 8 | 14:00 | ~36 | 10–12 + 3–4 |

* **Cinder's `seals_required` is 7**, raised from 6 by the phase-2 bot run: with 6 the seed-7 bot
  cleared the map in 5.4 sim-min, under the 6–10 band of §11, because the Warlord and the boss die
  in seconds to bot builds. With 7 it takes 6.1 sim-min (367.2 s). The composition pass (§3.6)
  opens the map and speeds the run up, so its pacing check (§3.6.12) retunes this number or the
  threat rows. Record the result here.
* **Slice** (Cinder plus boss): 10–13 min for humans, 7–9 for bots. Acceptance #5 ("finish run 1 or
  die at boss 1 within 25 min") holds.
* **EA run** (3 biomes): 33–40 min for humans, 25–30 for bots. This is the top of NEXT_SESSION's 20–35
  min band, so the user needs to sign off (§13). The data levers are `seals_required − 1`
  (about −1.5 min per biome) or smaller `size`.
* **Travel.** Move speed is 5.6–7.0 u/s (×1.25 with Stride, §5.9). A straight crossing takes 60–75 s,
  and POI spacing (≥ 36 u) keeps legs at 10–30 s.

### 2.3 POI roster

| POI (`PoiKind`) | Activation | Time | Pressure while active | Reward (scope, §2.4) | Seals |
|---|---|---|---|---|---|
| `Anvil` | Interact, then **Hold** the ring (r 4.5; pauses when empty: today's Kindling) | 30 s | wave ×1.5; one biome elite at 60 % ("Breaker") | **Forge**: 25 s Hot window, charges per claimant, Forge Aegis | 1 |
| `Warlord` | **Clear**: `biome.minibosses[rng]` (existing `BossBrain`) wakes within 34 u | 60–90 s | wave ×0.6 (the fight is the pressure) | mini-boss kill drops (existing) + `cache_parts` + 20 shards (present) | 2, required |
| `Lair` | **Clear**: 2 biome elites + a pack, idle until woken | 30–45 s | wave ×0.8 | `cache_parts + 1` parts + 10 shards (present) | 1 |
| `Shrine` | Interact, then **Hold** (r 4.0, decays 5 %/s when empty) | 12 s | wave ×1.2 | **Boon** from the shrine's fixed god (present; late claim) | 1 |
| `Reliquary` | Interact, then **Hold** (r 4.0, decays 5 %/s) | 15 s | wave ×1.3 | `cache_parts` parts (present) | 1 |
| `Vein` | Interact, then **Hold** (r 4.0, decays 3 %/s) | 20 s | wave ×1.4; one elite at 50 % | `cache_shards` (18) to **every** player | 1 |
| `Spring` | **Use** (once per player) | instant | — | heal 40 % × `healing_received` (per player) | 0 |
| `Watchfire` | **Touch** (1 s channel) | 1 s | — | reveals an 80 u radius and shows POIs in it | 0 |
| `Gate` | Sealed → Open → interact → **Gathering** | 10 s (2 s solo) | Gate Frenzy | enter the boss arena | — |
| Camps (not POIs) | a dormant pack wakes within 34 u | 10–20 s | — | a shard pile (8–15) | 0 |

The biome's quota list (§4.3) sets the POI counts. The Warlord replaces the MiniBoss room: The
Bellows is still met in every slice run, on the way to the gate.

### 2.4 Reward scopes (fixed rules, not data)

* **Present** means living players within `radius + coop.present_pad` (8 u) when the POI completes.
  Parts: each present player rolls their own, as owner-bound pickups. This reuses the `PartCache`
  branch of `room_flow`, extracted as `run::grant_reward`.
* **Party**: Seals, and Vein shards, go to every player wherever they are.
* **Late claim**: a Shrine's players present at completion get their offer at once. Any other player
  may interact at the Done shrine once to get their own (a `claimed` slot mask). Springs are per-player
  `Use`. Anvil charges are claimed by each player who enters the ring while it is Hot.
* Every completion does: `run.depth += 1`, `ember += ember_per_objective × ember_mult`,
  `GameEvent::PoiCompleted`, and it vacuums pickups within 40 u to present players.

### 2.5 Escalation ("beautiful madness by minute 15")

**Threat clock.** `T = threat_start_minute + stage_minutes + heat_per_objective × objectives_done`.
Each `ThreatKey` row gives density, rate, elite chance and HP multiplier, interpolated linearly
between rows. Past the last row, the last segment's slope continues, and density is capped by
`global_max_alive`. The numbers are for **one solo cluster**. A cluster of `n` players multiplies
density and rate by `party_scaling(n).enemy_count` (1.0 / 1.5 / 1.9 / 2.3).

Cinder defaults:

| minute | density (alive) | rate (weight/s) | elite chance | HP mult |
|---|---|---|---|---|
| 0 | 30 | 3.0 | 0.01 | 1.00 |
| 3 | 60 | 5.0 | 0.03 | 1.10 |
| 6 | 100 | 7.5 | 0.05 | 1.25 |
| 9 | 140 | 10.0 | 0.07 | 1.45 |
| 12 | 175 | 12.5 | 0.08 | 1.65 |
| 15 | 200 | 14.0 | 0.09 | 1.90 |

* A grouped 4P party reaches 230 alive at minute 6, 320 at minute 9, and the 400 cap by about
  minute 11.
* `threat_start_minute` carries the madness forward: Verdant 4, Spire 7, Unmaking 9. The existing
  `hp_growth_per_biome` (0.6) still applies. Run minute 15 (early in biome 2) therefore starts at or
  above biome 1's peak pressure.
* **Hold waves.** While a Hold POI is Active with players inside, its cluster's rate × `wave`, and 50 %
  of that cluster's spawns land on an 18–26 u ring around the POI, converging on the holders.
* **Surges.** From minute 3, every 85–115 s: a 3 s warning (`GameEvent::Surge { warn: true }`, horn,
  edge flash), then 15 s at rate ×2 with spawns confined to a 90° arc on one side.
* **Gate Frenzy.** From `GateOpened` until the arena: rate ×1.4, density +25.
* **Unworthy.** A forced gate multiplies the boss's HP by `1 + min(0.25 × missing, 0.75)`, where
  `missing = required − seals` (+2 if the Warlord is alive).

---

## 3. Map generation: `gf_content::worldgen`

### 3.1 Grids, streams and determinism

* **Tile** = 4 u. The land mask, regions, flow fields, bot coarse nav and the minimap raster all share
  it. Cinder is 108 × 68 = 7,344 tiles.
* **Chunk** = 32 u (8 × 8 tiles). This is the client render unit only.
* **RNG.** `root = GfRng::new(seed as u64 ^ key_hash(template.key).rotate_left(17))`, the same mixer
  as `procgen::generate`.
  - Macro stages use `root.fork(1)`.
  - Region `i` uses `root.fork(100 + i)` for layout and `root.fork(200 + i)` for dressing, so
    re-dressing never moves an obstacle and one region's changes never shift another's.
* **Rules** (the procgen rules, enforced in review):
  - integer `GfRng` output only, plus `+ − × ÷ √`;
  - no `sin/cos/atan2/exp/powf/mul_add`, and no `unit_vec2`;
  - facings as `Rot16`;
  - no `HashMap`/`HashSet` iteration;
  - sorts use integer keys;
  - every coordinate written into obstacles, pits, POIs or camps is quantized with `qv` (1/8 u).
* **Generation reads only content, never the build phase.** Any phase filter uses
  `max(template.phase, P1)`, so the host, the clients and the bots always agree.
* `MapLayout.hash` = FNV-64 over the quantized ints of obstacles, pits, POI sites, `player_spawn` and
  the gate. The golden test pins `(cinder_expedition, 7)`. Clients compare it with `RunView.layout_hash`
  at runtime (§6.1).

### 3.2 Pipeline: `worldgen::generate(db, template, seed) -> RoomDef`

1. **Size.** `size` comes from the template, as a multiple of 8. `half = size / 2`, and the tile grid
   origin is `-half`.
2. **Regions.** Use a jittered grid of `regions.x × regions.y` sites (cell centre ± 30 %, snapped to
   tile centres). Each tile goes to the nearest site by integer squared distance on **domain-warped**
   tile coordinates. The warp is integer value noise (lattice hash, bilinear in 1/256 fixed point,
   amplitude 3 tiles, period 6 tiles), and ties go to the lower index.
3. **Themes.** Pick weighted from `themes`, deterministically. Two constraints: the Landing region
   takes an `open` theme (`start_theme`), and adjacent regions avoid sharing a theme where possible.
4. **Coast.** A tile is `Void` when its distance to the rectangle border is ≤ `coast.depth` +
   `noise × coast.amp` tiles. That gives bays and headlands up to ~20 u deep. The Landing edge's
   middle third is forced to `depth` only, so arrival is never cramped.
5. **Landing and gate.** A seed pick of the N/E/S/W edge chooses the Landing region: the region
   nearest that edge's midpoint whose theme is `open`. The gate region has the maximum BFS hop depth
   from the Landing in region adjacency (ties go to the larger Euclidean distance). The route must
   cross at least 3 regions.
6. **Roads.** Region adjacency comes from shared border tiles.
   - Kruskal MST, sorted by `(q8(dist²) as i64, a, b)`, then each non-MST edge is added with
     `loop_chance`.
   - Each road runs site → border midpoint (the **pass**) → site, with one jittered bend per leg.
   - Roads are stored as `Lane { width: roads.width }` and rasterized to `Road` tiles.
7. **Barriers.** Each adjacent region pair rolls `barriers.chance`, and the kind is picked from
   `barriers.kinds`:
   - `Chasm` (Void tiles, 2 thick) and `River` (Liquid tiles, 2–3 thick): pits.
   - `Wall`: box obstacles 3–5 u tall along the border, `Decor::Wall` in the biome's style.
   - `Ridge`: boulder chains, `Decor::Boulder`.

   A road-connected pair keeps a **pass** where the road crosses, `roads.pass_width` (8 u) wide:
   `Bridge` tiles plus `Decor::Bridge` over pits, or a breach with `Decor::Arch` in walls. Passes are
   the designed chokepoints. The MST guarantees connectivity.
8. **POI sites** (§3.3). Each site stamps its plaza (`Plaza` tiles, radius from game.ron `pois[].plaza`)
   and a spur road to the nearest `Road` tile.
9. **Regions are composed with the room grammar**, under the composition rules of §3.6. The procgen
   `Builder` gets map mode (§3.4). For each region:
   - a) Push roads, spurs and bridge decks as `Lane`s. Nothing colliding may stand within half a
     lane's width + `road_clear` of it. POI plazas, the Landing and hubs become `keep` disks, and
     every pass a `pass_clear` keep-out.
   - b) Cut up to `compose.slots` (5) **slots**: greedy maximal axis-aligned rectangles of `Ground`
     tiles (histogram method, deterministic), shrunk by `PAD`, at least 16 × 12 u. **Edge slots**
     come first: their back lies on the coast, a pit or a region border, never the south edge.
     Open fields are cut from what is left (§3.6.4).
   - c) Fill up to the theme's `comps` edge slots from its `districts` pool with
     `procgen::stamp(kind, frame)`, never repeating within a region. Every other slot is an open
     field: painted, and holding one kiting anchor unless the theme's `fields` share leaves it bare
     (§3.6.3).
   - d) A grand monument (`monument(.., grand: true)`) at the region site when the region has no
     major POI, picked from `landmarks`.
   - e) Up to the theme's `story` clusters on the region's frame band (§3.6.4). The density top-up
     is gone.
   - f) The frame: coast anchors on the lay stream, then lip pieces and silhouettes on the dress
     stream (§3.6.4, §3.6.5). Floor dressing follows on the dress stream: fissures only near heat,
     and cobble islands (§3.6.7).
10. **POI clearings.**
    - Every POI gets a heart `FloorInlay` (variant by kind), a ring of braziers, and its kind's set
      pieces. Arches where roads enter are off by default (`compose.entry_arches`, §3.6.3).
    - The Gate gets a `SealedGate` monument with one socket per Seal.
    - The Warlord gets a `Crucible` or biome set piece at the plaza edge.
    - Map-wide dressing runs last:
      - road braziers 30–40 u apart;
      - a brazier pair at every pass arch. The arches themselves go up before the regions compose,
        wherever a road crosses a wall, ridge or open border; a bridge carries its own deck;
      - waymarks, bridge decks, hubs and the Landing;
      - then vignettes and light gaps (§3.6.6, §3.6.8).
11. **Camps.** Rejection-sample land tiles at least 35 u from the Landing, 20 u from POIs and 6 u off
    roads, one camp per `camps.per_area` u². Each camp's pack comes from the theme's `camp_pool` (else
    the biome swarm), with `camps.elite_chance` of an elite leader.
12. **Pits.** Merge horizontal runs of `Void`/`Liquid` tiles into boxes, then merge identical runs on
    consecutive rows. The result is `MapLayout.pits`.
13. **Reachability and repair.**
    - Tiles are passable when `Ground | Road | Plaza | Bridge` and less than 50 % covered by
      obstacles (coverage from the Builder's 0.5 u cover grid).
    - Run a BFS from the Landing. Every POI plaza, camp and the gate must be reached.
    - For each unreachable target, in site order: find the cheapest path treating blocked tiles as
      cost 50, remove the obstacles (and their decor) overlapping it, and turn pits on it into
      `Bridge`.
    - Repeat at most 3 times. `MapLayout.repairs` counts the carves.
14. **Output.** A `RoomDef` with:
    - `key: "{template}~{seed:08x}"`, `kind: Expedition`, `half_extents`, `obstacles`, `decor`;
    - `player_spawn` = the Landing, `exits = vec![gate]` (existing exit fallbacks keep working);
    - `spawn_zones = [Around { 27, 34 }]` (stress mode only);
    - `encounter` from the template, `expedition = template's` (cloned), `map = Some(Arc<MapLayout>)`,
      `districts` (room-grammar footprints, for the preview) and `lanes` (the roads).

Budget: **≤ 60 ms release and ≤ 400 ms debug** per map. It runs once on the host (inside `load_room`,
under the 0.8 s transition), once per client, and once per bot process (shared cache, §8.1).

### 3.3 POI placement

Placement uses `d`, the road-graph path distance from the Landing normalized to 0..1. Major POIs take
a region site (at most one per region, never the Landing region). Minor POIs take **secondary sites**:
points on roads inside a region at least 25 u from its site, offset 8–14 u off the road for
Reliquaries and Veins.

1. **Gate**: the gate region's site.
2. **Warlord**: the region on the Landing→gate route at 50–75 % of the route length, so the path runs
   past it. If the route is too short, any region with `d ∈ [0.5, 0.8]`.
3. **Anvils**: #1 in a region adjacent to the Landing, #2 at `d ∈ [0.35, 0.7]`, #3 (and #4) at
   `d ∈ [0.6, 1.0]`. All major.
4. **Lairs**: leaf regions (road degree 1) with `d ≥ 0.3` first, then `d ∈ [0.3, 0.9]`. Major.
5. **Shrines**: secondary sites, `d ∈ [0.2, 0.9]`. Each takes a distinct god drawn without replacement
   from the gods with `phase ≤ max(template.phase, P1)`. A Cinder shrine is one of Pyra, Zephyros or
   Nyctia.
6. **Reliquaries and Veins**: secondary sites, `d ∈ [0.3, 0.9]`.
7. **Springs**: one 15–25 u from the Landing, one at `d ∈ [0.4, 0.6]`, one in a gate-adjacent region.
8. **Watchfires**: one per map quadrant, on the road tile nearest the quadrant centre.

Spacing: POIs at least 36 u apart (Springs and Watchfires 20 u) and at least 30 u from the Landing
(except Spring #1). If a site fails, relax spacing by 10 % per pass for up to 3 passes, then take any
road tile in the band. `MapLayout.relaxed` counts relaxations, and the preview tool and `--check`
print it.

### 3.4 Changes to the room grammar (`procgen.rs`, kept small)

`procgen.rs` stays the room generator. Map mode touches only `Builder` and visibility:

* `Builder.fits` and `Builder.clearance` query a 4 u bucket index instead of scanning every obstacle.
  The query reaches `extent + LANE + max_extent`, so results are **identical**, and room layouts stay
  byte-for-byte the same (the procgen tests and a before/after `preview-sheet` prove it).
* `Builder.mask: Option<TileMask>`. In map mode a piece fits only if every tile its extent (+0.5 u)
  overlaps is `Ground`. Compositions never sit on roads, plazas, bridges, liquid or void. The rim check
  uses the map `half`.
* `Builder`, `Frame`, `Rect`, `stamp`, `field`, `monument`, `arch` and the dressing helpers become
  `pub(crate)`, so `worldgen` builds with them.
* `resolve_room` routes `RoomKind::Expedition` to `worldgen::generate(db, t, seed)`. `is_generated_kind`
  includes `Expedition`. Seed 0 on an Expedition template means seed 1 (a map is never "authored").
* The composition pass (§3.6) adds map-mode switches:
  - `Builder.lane_pad` (`road_clear` on maps, 0 in rooms);
  - `field()` lays paint only, and a new `anchor()` places the kiting anchor;
  - `court()` spaces its columns wider and drops a side row;
  - `fissure()` needs heat nearby.

  `lane_pad` and the fissure rule stay map-only. The `field()`, `anchor()` and `court()` rules key
  on `b.mask.is_some()` until the room pass (§3.6.10) makes them the room behaviour too. At that
  point room layouts change on purpose, and the before/after `preview-sheet` is the check.

### 3.5 Biome identity (initial content)

| Biome | Barriers (`kinds`, chance) | Region themes (`districts` pools from the grammar) | Grand monuments |
|---|---|---|---|
| Cinder | River (slag) 0.30, Wall (Forge) 0.15; chance 0.45 | Slag Flats (open; SlagChannel, CrucibleYard), Foundry Ruins (ForgeHall, CrucibleYard, ColonnadeCourt), Colonnade of Oaths (ColonnadeCourt), Cinder Dunes (open; fields), Chainyard (CrucibleYard, ForgeHall) | GreatAnvil, Statue, ColossusHead, GreatBrazier, SealedGate; phase 4 adds FallenWeapon |
| Verdant | Chasm (sinkholes) 0.25, Wall (Hedge) 0.20 | Drowned Cloister, Glowgrove, Temple Steps, Root Maze, Idol Court | Tree, Statue, ColossusHead, SealedGate |
| Spire | Chasm 0.55 (islands and star bridges) | Star Bridge, Clock Gallery, Drift Terraces, Broken Stair, Observatory Plaza | SpiralStair, Statue, Crystal, SealedGate |
| Unmaking | Chasm 0.45, Wall (Monolith) 0.10 | Shattered Plane, Tessellation, Inverted Nave, Fracture Fields, Proof Halls | InvertedColumn, Rift, Statue |

**The "Fallen Arms" motif (phase 4).** Colossal broken god-weapons are driven into the ground: a
tower-sized sword, hammer, spear, bow or cannon. They give every map a navigable skyline and
*The Last Arsenal* its battlefield. It is one new `Decor::FallenWeapon`.

### 3.6 Composition and negative space

> Specified 2026-09-26 after user feedback on the Cinder map: "lots of clutter … pillars and
> walls … look at HADES II". Two read-only passes on `cinder_expedition` (an audit of where the
> clutter comes from, and a study that applied these rules by hand to the real layouts) supply
> every number here. This section supersedes the density top-up (§3.2 step 9e), the ruins inside
> open fields, the road silhouettes and the clearing entry arches. §3.6.10 applies the same rules to
> the EA room grammar.

**The problem in numbers.**

* The run-7 map has 1,508 colliding shapes and 3,106 decor pieces. That includes 520 pillars,
  384 rubble heaps, 237 boulders, 235 forge walls and 428 glowing fissure segments.
* About two thirds of the colliding shapes (≈ 950 of ≈ 1,430 per map) come from the density
  top-up (`compose.rs::region` step e). The top-up exists only to reach the old room generator's
  ~5 % floor cover.
* Another 7 % are ruins inside "open" fields. The 28 fields on the run-7 map hold 244 colliding
  pieces.
* The land between roads, where kiting happens, is the densest: 6.5–7.4 % cover, against 5.1 %
  overall.
* Walkable floor is cramped:
  - median clearance is 3.2–3.8 u;
  - only 48 % of it lies inside a blocker-free disk of r 10;
  - the largest open disk per region is r 10–18 (terrain alone allows r 30–78).

**The reference.** We take qualities only; nothing is traced or copied. The sources are three
local Hades II screenshots (`docs/media/reference/1–3.png`) and Hades 1 and 2 level art in general.
Each quality becomes a generator rule:

| # | Hades quality | Our rule | § |
|---|---|---|---|
| 1 | The combat floor is open. Its detail is painted (cobble patches, stains, cracks, tufts). | No fill. An open field keeps at most one kiting anchor. Rubble, ash and cracks become floor paint. | 3.6.3, 3.6.7 |
| 2 | Density lives at the edges. Buildings, cliffs and foliage frame the space, with dark silhouettes along the camera-near edge. | Compositions back onto the coast or a region border. A visual frame stands on the cliff lip, with silhouettes in the void beyond. | 3.6.4, 3.6.5 |
| 3 | Props sit in a few purposeful vignettes against walls. | Props appear only in vignettes, at set pieces, at wall bases and on road shoulders. | 3.6.6 |
| 4 | Obstacles in the play space are rare and meaningful. | POI set pieces, hub monuments, one kiting anchor per field and one story cluster per region. | 3.6.3, 3.6.4 |
| 5 | Warm light pools mark paths and interactables against a dark, cool surround. | Every screen has a warm pool. Flames sit on the frame or at interactables. POIs get a key light. The dusk between is cooler. | 3.6.8 |
| 6 | The walkable boundary is an organic shape that reads clearly. | The coast stays as it is (already good). Barrier walls become broken runs, not tile staircases. | 3.6.4 |

**Scale.** At our camera a hero is about 6 % of screen height, against 10–13 % in Hades II, so one
of our screens covers about 4× the area of a Hades room. Hades rooms hold 0–2 interior obstacles per
screen for 5–15 enemies. We fight up to 400 enemies and kiting matters, so we take the sparse end:
**at most 2 interior colliding clusters per screen (median) and at most 4 (p90).**

#### 3.6.1 Measurement

Every number in §3.6 uses these definitions. They are implemented once, in `layout-stats --maps`
(step 0 of §3.6.12), on a 0.5 u raster with exact distance transforms.

* **Land** is `Ground | Road | Plaza | Bridge` tiles.
* A **blocker** is an obstacle, a pit tile or the map rim.
* **Walkable floor** is land that is not inside an obstacle.
* **Clearance** of a floor point is its distance to the nearest blocker.
* **Clear-disk share at r R** is the share of walkable floor covered by some blocker-free disk of
  radius R.
* **Interior** is land more than 6 u from every pit tile and every tile of another region.
* **Cover** is obstacle area / land area. Interior cover is obstacle area / interior land area.
* A **screen** is a 45 × 28 u window (the 4P view footprint at 55°, rounded down), stepped 9 × 7 u.
  A window counts when ≥ 60 % of it is land. (The audit also used 50 × 34 u windows at half
  overlap; its "per screen" figures are marked.)
* A **cluster** is a connected group of obstacles whose gaps are ≤ `TOUCH` (0.3 u), so a wall run
  counts once.
  - It is in a screen when any of its shape centres is inside the screen.
  - It is **interior** when its centroid is interior.
* **Props** are `Rubble`, `Brazier`, `Clutter`, `Chains`, `BrokenAnvil`, `Banner` and `Waymark`.
* A **warm source** is a `Brazier`, `GreatBrazier` or `Crucible` decor, a `Liquid` tile or a POI
  heart.
* **Frame mass** is a `Scenery` piece, a barrier wall or a composition footprint.
* **Seeds.** The game's `--seed N` builds map seed `procgen::room_seed(N, 0)`:

  | Run seed | Map seed |
  |---|---|
  | 3 | 2298633409 |
  | 7 | 3047268829 |
  | 11 | 3195035749 |

  So `preview-room cinder_expedition 3047268829` shows the map that `--seed 7` plays.
  `layout-stats --maps --seeds 8` uses map seeds 1–8.

#### 3.6.2 Targets

* **Before** is the mean over map seeds 1–8, with the run-7 map in brackets.
* **Gate** means `layout-stats --maps` fails on a miss, the same way it fails on a repair.
* **Report** means the value is printed and checked by eye in the acceptance (§3.6.12).

| Metric | Before | Target | |
|---|---|---|---|
| Colliding obstacle shapes per map | 1,443 (1,508) | ≤ 550 | gate |
| Colliding cover of land | 5.1 % (5.27 %) | ≤ 2.5 % | gate |
| Interior cover | 4.3 % | ≤ 2.0 % overall. Each theme stays under its `cover` ceiling: slag flats and dunes 1.0 %, colonnade and chainyard 1.8 %, foundry 2.2 %. | gate |
| Clusters per screen: median / p90 / max | 8.1 / 13.8 / 21.1 | ≤ 3 / ≤ 8 / ≤ 14. The edge screens carry the mass. | gate (median, p90) |
| Interior clusters per screen: median / p90 | 4.4 / 8.4 | ≤ 2 / ≤ 4 | gate |
| Median clearance of walkable floor | 3.8 u (audit raster: 3.2–3.5 u) | ≥ 7 u | gate |
| Floor inside a clear disk of r 10 / r 16 | 48 % / 16 % | ≥ 80 % / ≥ 60 % | gate (r 10) |
| Largest clear disk in the smallest region | r 12.3 (audit: r 10–18 per region) | ≥ r 15 in every region | gate |
| Colliding shapes within road half-width + 4 u | 7.5 per 100 u of road | 0, except pass arches | gate |
| Colliding shapes within a POI's plaza + 6 u | mixed | Only that POI's own set pieces. Its approach arcs (±30° around each way in, out to plaza + 10 u) are clear. | gate |
| Props per map | 985 (1,088) | ≤ 650. Each one stands in a vignette, at a set piece or wall base, or on a road shoulder. | report |
| Glowing fissure segments per screen, p90 | 11–12 | ≤ 6, and none farther than 9 u from heat | report |
| Screens without a warm pool | 13–15 % | 0 % | report |
| Screens with frame mass | — | ≥ 70 % | report |
| Barren screens (no solid and no POI) | — | ≤ 10 % | report |
| Obstacles per 50 × 34 u audit window, median | 22–25 | ≤ 9 | report |
| Generation | 9–11 ms, 0 repairs, 0 relaxed, 17/17 POIs | ≤ 60 ms release, 0 repairs, 0 relaxed, every POI placed | gate (existing) |

The study applied the rules by hand to the eight layouts. It reached every gate:

* 484 shapes (361–544);
* 2.3 % cover, 1.7 % interior;
* clusters 3.1 / 7.5 / 14.1, interior 1.3 / 4.1;
* 7.4 u median clearance;
* 85 % / 68 % clear-disk shares;
* r 17.6 in the smallest region.

**Per kind** counts come from the preview legend for run maps 3 / 7 / 11. Each ceiling is loose on
its own; the shape total (≤ 550) is the one that binds.

| Kind | Before | After ≤ | What stays |
|---|---|---|---|
| Pillar | 522 / 520 / 472 | 100 | Colonnade columns in compositions, anvil and crucible chain posts, chainyard story posts |
| Boulder | 240 / 237 / 244 | 110 | Coast anchors, field anchors, slag-heap stories |
| Wall (Forge) | 182 / 235 / 155 | 100 | Barrier runs, forge-hall walls, crucible stations, foundry story chimneys (north frame only) |
| Wall (Ruin) | 72 / 73 / 84 | 55 | Composition walls, lair rims |
| Wall (Plinth) | 67 / 67 / 66 | 25 | Reliquary plinths, plinth anchors |
| FallenColumn | 30 / 32 / 22 | 12 | At most one per composition, and column anchors |
| Arch | 61 / 49 / 51 | 22 | One per road pass, and colonnade stories |
| Landmarks (Statue, GreatAnvil, Crucible, ColossusHead, FallenWeapon, GreatBrazier, SealedGate, Crystal) | as mapped | ≤ before | All of them |
| Rubble | 364 / 384 / 361 | 110 | Wall bases and breaches, vignettes |
| Overgrowth | 236 / 230 / 232 | 30 | Vignette bases only. The ash drifts are paint. |
| LavaCrack (fissure) | 408 / 428 / 406 | 260 | Within 9 u of heat |
| Brazier | 193 / 199 / 195 | 220 | Roads, clearings, hubs, composition mouths, passes, lit vignettes, light gaps |
| Chains | 110 / 135 / 92 | 50 | Between set-piece posts |
| Clutter | 182 / 189 / 152 | 120 | Vignettes, compositions, clearings |
| BrokenAnvil | 75 / 80 / 77 | 35 | Vignettes, plinth anchors, forge halls |
| Banner | 73 / 69 / 63 | 70 | Walls, POIs, hubs, vignettes |
| Waymark | 28–35 | unchanged | — |
| Paving / FloorInlay | 29–32 / 52–56 | 80 / 60 | Adds cobble islands and spring rings (painted) |
| Scenery (new, visual) | 0 | 500–900 | The frame |

#### 3.6.3 What gets cut

Items 1–4 and 6–10 change obstacles. They are on the lay stream and move the hash (step A of
§3.6.12). Item 5, and item 4's rune ring, are dressing (step B).

**`crates/gf_content/src/worldgen/compose.rs`:**

1. **`region()` step e, the density top-up, is deleted.** This removes:
   - the `while covered < target && tries < 400` loop;
   - its composition-skirt and `BAND` branches (`BAND` goes with them);
   - its `ruin()` calls with 1–2 satellites.

   `RegionTheme.cover` becomes the interior ceiling (§3.6.9). `story()` survives as the region's
   frame piece (§3.6.4).
2. **`road_silhouettes()`** runs only when `compose.road_silhouettes > 0`. The default is 0.0, the
   chance per 22–28 u slot. The vertical rhythm now comes from compositions at the edges, backdrop
   silhouettes and hub monuments.
3. **`clearing()`'s entry-arch loop** (`road_arch` at plaza + 1.5 or + 3.0 u for every way in) runs
   only when `compose.entry_arches` is true (default false). That is about 19 fewer arches per map.
   The heart inlay, the brazier ring, the key light (§3.6.8) and the waymark already signpost the way
   in.
4. **`clearing()`, `PoiKind::Spring`:** the four standing-stone pillars go. The spring's rim becomes
   a `FloorInlay { variant: 1 }` rune ring of radius `radius + 1.0`, laid on the dress stream by
   `dress_clearing`.
5. **`region()` step f, the floor dressing:** no `cover_patch`, no `rubble` and no `Bones` clutter on
   open ground. `fissure()` obeys the heat rule (§3.6.7).

**`crates/gf_content/src/procgen.rs`**. These apply in map mode (`b.mask.is_some()`). The room pass
of §3.6.10 later extends items 6–8 to rooms:

6. **`field()`** lays paint only:
   - one broken-paving island (`Paving { variant: 3 }`, half 2.5–4 u, off-centre);
   - no ruins, satellites, cover patches, rubble, fissure or bones.

   `region()` decides per field whether it also gets an anchor: `lay.chance(1 − theme.fields)`,
   then `anchor()`.
7. **`anchor(b, f, x) -> bool`** is new. It lays one chunky kiting anchor near a field's middle:
   - It tries up to 6 spots `f.p(±0.35 hl, ±0.35 hw)`.
   - A spot is accepted when:
     - `b.clearance(at, r + x.anchor_clear) ≥ r + x.anchor_clear`;
     - the tile mask is `Ground` within `r + x.road_clear`;
     - it is ≥ 6 u beyond every `keep` disk.
   - It has no satellites.
   - Cinder roll:
     - `Boulder`, radius `x.anchor_radius` (1.6–2.6): 55 %;
     - `FallenColumn`, r 0.8–0.95, 4–5.5 u long: 25 %;
     - `Wall { style: Plinth }`, half 1.3–1.8 × 0.9–1.3, height 1.0–1.6, with a `BrokenAnvil` on top:
       20 %.
   - Other biomes (phase 4 maps, and rooms from §3.6.10):
     - Verdant: an ancient tree (`ruin()`'s tree), a boulder or a hedge plinth;
     - Spire: a crystal, a boulder or a plinth;
     - Unmaking: a monolith, a crystal or an inverted column.
8. **`court()`:**
   - Column spacing becomes 5.5–6.2 u (was 4.1–4.6).
   - Sides: the back row, plus one side row at 60 % (was 3 sides at 75 %).
   - The walled back (55 %), the statue, the banners and the mouth braziers are unchanged.
   - The Verdant cloister keeps its square of piers, spaced ≥ 5.5 u.
9. **`Builder.lane_pad: f32`** is new. It is `compose.road_clear` on maps and 0 in rooms. `fits()`
   refuses a piece within `lane width / 2 + lane_pad` of a lane. `unmasked()` lifts it, so pass
   arches, POI set pieces and hub monuments may still stand on a road's shoulder.
10. **`fissure()`** checks heat in map mode (§3.6.7).

#### 3.6.4 What moves to the edges

Lay stream; these change the hash.

1. **Edge slots** (`compose.rs::slots` splits into `edge_slots` and `field_slots`).
   - **Edge flags.** For region `r`, a free tile is a `Ground` tile of `r`. Flag a free tile
     toward direction `d` when one of its tiles 1 to 1 + `compose.edge_band` steps along `d`
     (`edge_band` defaults to 1) is:
     - a coast edge: a `Void` or `Liquid` tile, or off the grid;
     - a border edge: land of another region.

     A road, plaza or bridge tile is not an edge.
   - **Search.** The histogram search of `largest()` stays, capped at `SLOT_CAP`, with the minimum
     `SLOT_MIN`. A crop is eligible when one of its north, east or west sides has at least
     `edge_share` (0.75) of its tiles flagged toward that side, using the integer test
     4 × flagged ≥ 3 × side length. **A composition never backs onto the south edge**: that edge
     stands between the camera and the fight, as in rooms.
   - **Choice.** Take the largest eligible crop. Ties go to a coast edge before a border edge, then
     north before east before west, then the first one found. `Slot.back` is that side's outward
     axis, and `Slot.edge` records coast or border.
   - Spend the slot plus a one-tile margin, **plus a `slot_clear` band (8 u, 2 tiles) on its three
     open sides**, so no later piece pinches the floor in front of a composition.
   - Stop after `theme.comps` edge slots, or when no crop is eligible.
   - **Fields.** `field_slots` then cuts open fields from the remaining free tiles with today's
     `largest()`, until `compose.slots` (5) slots in total.
   - **Composition.** Only edge slots take compositions, from the theme's `districts` pool, never
     repeating in a region. A failed stamp turns its slot into a field. `Frame::of(rect, back, …)`
     already turns a composition's back toward the edge. Most compositions sub-frame with `outward`
     0.6–0.8 (channels 0.3), which pushes them toward that back, so the strip behind a court, hall
     or yard is at most about `edge_band` tiles + `PAD` wide.
2. **Passes are keep-outs.** Just before the region loop, `build()` pushes `(pass.at,
   compose.pass_clear)` (10 u) for every `g.passes` into `b.keep`. This comes after `wall()` and
   `pass_arch()`, which the keep-outs must not refuse. So no composition, story or anchor pinches a
   pass, and no corridor beside a barrier closes.
3. **Story on the frame** (region step e, new form). Up to `theme.story` clusters (default 1) per
   region, on the lay stream after the slots.
   - **Candidates:** tiles of `r` with a pit tile, or a barrier-wall border, within one tile, and
     outside every composition's `slot_clear` band. Candidates are tried in a seeded order, at most
     40 tries.
   - **Placement:** the recipe stands at the tile centre + 1 u toward that edge. It needs
     `off_lanes(.., road_clear)`.
   - **Tall recipes** (the foundry chimney at 6–8 u, the chainyard anchor post at 4.5–6 u, the
     colonnade arch) stand only where that edge lies north of the tile. Elsewhere the slag-heap
     recipe is used.
   - A story is skipped when it would push the region's interior cover past `theme.cover`.
4. **Coast anchors** (new step `frame(g, b)`, after the regions, on `root.fork(2000 + r)`). Colliding
   frame pieces only (the visual frame is in §3.6.5):
   - **Framed runs.** Walk each connected void shoreline of region `r`, ordered by BFS steps from its
     lowest tile index. A shore tile is a land tile of `r` with a `Void` 4-neighbour; liquid banks
     are excluded because rivers keep their hot banks clean. Framed runs of `frame_run` (8–24 u)
     alternate with gaps until `theme.frame` (default 0.5) of the shore length is framed.
   - **Unframed zones.** A run never comes within:
     - `frame_gap` (10 u) of a `Road`, `Bridge` or `Plaza` tile or a pass;
     - a POI plaza + 5 u;
     - 16 u of the Landing.
   - **Anchors.** At most one per `coast_anchor_every` (12 u) of framed shore. Each is a `Boulder`
     of r 0.8–1.4 whose centre stands at the shore tile centre + outward × 1.4, so it reaches at most
     2 u inland and overhangs the lip. It is placed through `unmasked()`, with `fits()` (lanes, LANE
     spacing) and a `Ground` centre tile. Anchors make nooks along the coast without narrowing the
     walkable band by more than 2 u.
   - Open region borders get nothing colliding beyond their pass arch. The ground tint blend marks
     them.
5. **Barrier walls become broken runs** (`compose.rs::wall`). Tile faces facing region `b` merge into
   straight runs, one per direction and line.
   - A run is laid as blocks of up to 2 faces (≈ 8.2 u, a hair of overlap), heights 2.4–4.0 u (was
     one 4.2 u block of 3–5 u per face). Each block has a 20 % chance of being a low ruined course of
     1.2–1.8 u.
   - Where a run turns (the staircase step), one square corner pier (half 0.8, height of its taller
     neighbour + 0.6) replaces the overlapping block ends.
   - Rubble lies only at run ends and at the pass breach.
   - The barrier still holds: blocks touch within `TOUCH`, and roads breach it under the pass arch.
   - This takes about half the blocks off, and the step reads as a buttressed corner instead of
     stacked slabs. `Ridge` barriers are unchanged.
6. **Passes are the doors** (`pass_arch`). An arch over each road crossing of a region border, with
   these chances:
   - walls and ridges: always;
   - open borders: `compose.pass_arches` (default 1.0, was 0.6);
   - over a bridge: never.

   On its own dress fork, each pass arch gets a brazier pair on the road shoulder just outside its
   piers.

#### 3.6.5 What becomes visual-only

**A new visual variant in `crates/gf_content/src/schema.rs`.** A Boulder with no obstacle would
break the `is_solid()` contract ("solid decor dresses an obstacle"), so the frame gets its own
variant:

```rust
/// Visual (biome maps): framing mass that never blocks. `Lip`: a rock or ruin fragment on the cliff
/// lip, past the walkable edge. `Backdrop`: a tall silhouette rising from the void beyond a far
/// (north, east or west) shore. `Foreground`: a low dark shape in the void off a camera-side
/// (south) shore.
Scenery {
    at: Vec2,
    radius: f32,
    height: f32,
    #[serde(default)] kind: SceneryKind,
    #[serde(default)] rot: Rot16,
    #[serde(default)] variant: u8,
},
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum SceneryKind { #[default] Lip, Backdrop, Foreground }
```

* `is_solid()` is false. `anchor()` returns `at`. `covers()` is false.
* `preview.rs` draws and counts it ("SCENERY").
* `world.rs::gallery` gets a row.
* `envkit.rs` renders it, reskinned by `AbyssKind`:
  - **Lip:** Cinder slag and basalt chunks (1 in 3 with an ember seam), and toppled forge blocks.
    ≤ 300 vertices each.
  - **Backdrop:** a basalt spire, a ruined chimney stack or the stump of a colossal column. Dark
    top, base rim-lit by the abyss glow. ≤ 900 vertices each.
  - **Foreground:** a low humped rock, near-black with an ink hull and no rim light. ≤ 300
    vertices each.
  - The heroes' x-ray silhouette already reads through a foreground shape, so no fade shader is
    needed.

**The visual frame** is laid by `frame()` on `root.fork(2100 + r)` over the same framed runs as the
coast anchors. All pieces are `decal`s over the void, never over a road, bridge or plaza tile.

| Piece | Where | Size | Spacing |
|---|---|---|---|
| Lip | 1–2 per framed shore tile, at tile centre + outward × 2.3–3.6 u, ± 1.5 u along the shore | r 0.8–1.8, h 0.6–2.6 | — |
| Backdrop, north shores (outward y ≥ 0.7) | 5–11 u out, only where the 3 × 3 tiles around it are `Void` | h 9–16 | ≥ 8 u apart |
| Backdrop, east and west shores (\|outward x\| ≥ 0.7) | 5–9 u out | h 6–10 | ≥ 10 u apart |
| Foreground, south shores (outward y ≤ −0.7) | 3–6 u out | h 1.5–5; it hides at most ~3.5 u of the lip | ≥ 6 u apart |

**Decor policy on biome maps.**

| Kind | Stays colliding (purposeful) | Goes |
|---|---|---|
| Pillar | Composition colonnades (≥ 5.5 u spacing, back row plus at most one side row), anvil and crucible chain posts, chainyard story posts | Stump pairs, satellites, field ruins, road silhouettes, spring stones |
| Wall | Barrier runs, composition walls, lair rims, reliquary plinths, the sealed gate, foundry story chimneys (north frame only), plinth anchors | Top-up plinths and chimneys |
| Boulder | Ridge barriers, coast anchors, field anchors, slag-heap stories | Satellites, top-up singles |
| FallenColumn | At most one per composition, column anchors, the foundry story's fallen courses | Top-up copies, field copies |
| Arch | One per road pass (with its brazier pair), colonnade stories | Clearing entry arches |
| Landmarks, Channel | All: at most one per composition, hub or POI. Channels are terrain. | — |

The visual props follow the same policy:

* **Brazier:** road braziers 30–40 u apart (unchanged), pass pairs, clearing rings, hubs,
  composition mouths, lit vignettes and light gaps. Nowhere else.
* **Banner:** on walls and composition backs, flanking a POI or hub back piece, or in a vignette
  against a wall.
* **Chains:** only between set-piece posts.
* **Clutter and BrokenAnvil:** in vignettes, compositions and clearings, on plinth anchors, or within
  3.5 u of a kept solid.
* **Rubble:** only within 1.5 u of a `Wall` or `Arch` (bases and breaches), in vignettes, and under a
  fallen lintel.
* **Overgrowth:** only as a vignette base on Cinder maps; ash drifts are paint. Verdant maps (phase 4)
  keep grass at the edges.
* **Waymark:** unchanged.

#### 3.6.6 Vignettes

A vignette is a small set of props backed against something solid. They are laid by a new
`vignettes(g, b)` step on `root.fork(2200 + r)`, after `frame()`, and they are dress only.

**Candidate backs**, per region, in this order. Within each group they are sorted by integer key,
and candidates whose open side faces south come first, so the props stand in front of their back
piece as the camera sees it:

* a composition's two inner back corners, 1.5 u off its back wall, open side `−back`;
* the midpoint of each barrier run face on this region's side;
* the land point 2.5 u inland of each framed shore run's middle tile;
* 2.5 u beside each story cluster, open side toward the region site.

**Acceptance.** A candidate is accepted when all of these hold:

* it is on `Ground`;
* it is ≥ road half-width + 1.5 u off every road;
* it is outside every POI plaza + 2 u and every approach arc;
* it is ≥ `LANDING_R` + 6 u from the Landing;
* it is ≥ `vignette_spacing` (18 u) from other vignettes;
* its fixed 45 × 28 u grid cell (origin `−half`) holds fewer than 2 vignettes;
* the region holds fewer than ⌈land area / `vignette_area`⌉ (2,000 u²) vignettes.

**Content.** 3–6 props within 2.5–4 u, all on the open side:

* 1–2 `Clutter` (Urns, Crates, Ingots, WeaponRack);
* 0–1 `BrokenAnvil`;
* 1 `Rubble` at the back piece's base;
* 0–1 `Banner`, only against a wall or composition;
* with 60 % chance, a `Brazier` (a lit vignette).

No Shards or Offerings, because gold and cyan belong to the objectives.

#### 3.6.7 Floor paint instead of meshes

The client changes are shader-only (`floor.wesl`) plus parameter packing in `world.rs`. They reuse
the existing `FloorParams` slots, so `materials.rs` does not change.

1. **Debris skirt.** In map mode, `floor.wesl` computes the footing distance before the bare-ground
   block.
   - Within 0.5–2.2 u of a footing, the pebble drift rises to 1 and the pebble threshold drops from
     0.84 to 0.70.
   - The rubble that used to be meshes becomes painted scree around each solid.
   - Fewer solids free the 32 footing slots per chunk for the ones that remain.
2. **Ash drifts replace Overgrowth.** This is data: `RegionTheme.ground.ash` rises to:
   - slag flats 0.2;
   - foundry 0.25;
   - colonnade 0.15;
   - chainyard 0.2;
   - dunes stay at 0.9.

   The shader already paints `recipe.y` drifts.
3. **Cobble islands.** `Paving { variant: 3 }` (broken paving) is laid on the dress streams, and the
   existing paving path paints it (12 per chunk). Islands go:
   - one in each open field (§3.6.3);
   - one at each composition's open mouth, half 3–5 × 2–3 u;
   - along road shoulders every 40–60 u on alternating sides, 2–4 u off the edge, half 2–3.5 u, on
     `root.fork(2400 + k)`.

   Islands keep ≥ 14 u apart, so a chunk never overflows.
4. **Hot fissures only near heat.** In map mode, `Builder.fissure()` returns early unless its start
   lies within `compose.heat_reach` (9 u) of heat:
   - a `Crucible`, `GreatAnvil` or `Channel` solid;
   - a `Liquid` tile (`TileMask`);
   - a POI heart (seeded into a `Builder.heat` list at `build()`).

   Compositions lay their heat piece before their veins, so their fissures survive. Open ground
   shows the shader's existing cold, scorched cracked earth.
5. **Cooler dusk.** In map mode, the falloff away from roads and clearings goes from
   `mix(0.84, 1.0, near_way)` to `mix(0.78, 1.0, near_way)`, with a 0.2 lean toward `fp.cool`. On
   maps, `world.rs` lowers the fissure glow `p.accent.w` from 1.3 to 1.0, so floor glow stays under
   the orange enemies.

#### 3.6.8 Light pools

**Rules** (all reported by the §3.6.1 readout):

* Every screen with ≥ 60 % land has a warm pool.
* **Coverage.** Warm pools cover 15–35 % of a screen's land (median). A pool is:
  - land within 7 u of a brazier;
  - within 10 u of a great brazier or crucible;
  - within 3 u of a liquid tile;
  - or a POI plaza.
* **Placement.** At least 70 % of non-road flames stand within 4 u of a composition, barrier, story
  or frame solid, or inside a POI plaza + 2 u.
* **Budget.** At most 6 flames per screen outside clearings (p90), which is what the 16-light pool
  can cover.

**How the generator meets them:**

1. **Light gaps** (new step, `root.fork(2300)`, after the vignettes). Lattice points run every
   11 × 7 u over land. Each point needs a warm source inside the `light_box` (30 × 18 u) centred on
   it. Every 45 × 28 u screen contains one whole such box, so every screen gets a pool. Points
   without one are visited in a seeded order, and each tries, inside its box:
   1. an unlit vignette, which gets its brazier;
   2. else a brazier 1.2 u off the nearest composition, barrier, story or coast-anchor solid, on the
      side facing the point;
   3. else a brazier on the nearest road shoulder;
   4. else nothing, and the metric reports it.
2. **POI key lights** (`world.rs`). One `Flame { power: 1.8, range: 14 }`, 2 u above each POI heart,
   in the flame colour. It is pushed after `soften_clusters`, so the brazier ring never dims it.
   It is the brightest light on its screen, ≥ 1.5× a road brazier.
3. **Objective hues.** Gold (Anvil, Reliquary) and cyan (Vein) never appear on decoration.
4. **Value ladder.** The floor stays under the characters (§7.2): the dusk and fissure changes in
   §3.6.7 only lower it.

#### 3.6.9 Data

These are tuning fields with serde defaults. **The defaults are the new composition**, so the golden
fixture and the phase-4 EA maps inherit it.

```rust
pub struct RegionTheme {
    /* key, name, weight, districts, tint, map_color, open, camp_pool, names, ground: unchanged */
    /// Share of the region's open fields left bare; every other field holds one kiting anchor.
    pub fields: f32,                              // 0..=1 (meaning changed: was "share of slots left open")
    /// Ceiling on colliding cover of the region's interior land: anchors and story clusters that
    /// would push past it are skipped.
    pub cover: f32,                               // 0..=0.08 (meaning changed: was the top-up target)
    /// Compositions per region, on edge slots only.
    #[serde(default = "two")] pub comps: u8,      // 2
    /// Story clusters per region, on the frame band.
    #[serde(default = "one")] pub story: u8,      // 1
    /// Share of the region's void shore that is framed (lip, anchors, silhouettes).
    #[serde(default = "half")] pub frame: f32,    // 0.5
}

/// `ExpeditionDef.compose` (the struct is `#[serde(default)]`, so templates may omit it).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ComposeDef {
    pub slots: u8,                 // 5: slots per region, edge slots first, then open fields (was const SLOTS)
    pub edge_band: u8,             // 1 tile: an edge slot's back lies this close to the coast or a border
    pub edge_share: f32,           // 0.75: share of the back side's tiles that must touch the edge
    pub slot_clear: f32,           // 8.0 u of free floor kept on a composition's open sides
    pub pass_clear: f32,           // 10.0 u: compositions, stories and anchors keep off passes
    pub road_clear: f32,           // 4.0 u: nothing colliding within road half-width + this (Builder.lane_pad)
    pub anchor_radius: (f32, f32), // (1.6, 2.6): a boulder anchor's radius
    pub anchor_clear: f32,         // 8.0 u of obstacle-free floor around a field anchor
    pub pass_arches: f32,          // 1.0: chance of an arch at an open-border pass (walls, ridges: always)
    pub entry_arches: bool,        // false: arches where roads enter POI clearings
    pub road_silhouettes: f32,     // 0.0: chance per 22–28 u road slot of a tall shoulder piece
    pub frame_run: (f32, f32),     // (8.0, 24.0) u: framed runs of shore
    pub frame_gap: f32,            // 10.0 u: shore left unframed around roads, bridges, passes (plazas +5 u)
    pub coast_anchor_every: f32,   // 12.0 u of framed shore per colliding coast anchor, at most
    pub vignette_area: f32,        // 2000.0 u² of land per vignette, at most
    pub vignette_spacing: f32,     // 18.0 u between vignettes
    pub heat_reach: f32,           // 9.0 u: glowing fissures only this close to heat
    pub light_box: (f32, f32),     // (30.0, 18.0) u: every land lattice point (11 × 7 u) has a warm source in this box
}
```

**Cinder values** in `rooms.ron`. `fields` keeps today's values: under the new meaning they still
rank the themes from open to dense.

| Theme | `fields` | `cover` (ceiling) | `comps` | `story` | `frame` | `ground.ash` |
|---|---|---|---|---|---|---|
| slag_flats | 0.6 | 0.035 → 0.010 | 1 | 1 | 0.5 | 0.0 → 0.2 |
| foundry_ruins | 0.2 | 0.07 → 0.022 | 2 | 1 | 0.55 | 0.1 → 0.25 |
| colonnade_of_oaths | 0.25 | 0.07 → 0.018 | 2 | 1 | 0.5 | 0.0 → 0.15 |
| cinder_dunes | 0.75 | 0.03 → 0.010 | 1 | 1 | 0.45 | 0.9 |
| chainyard | 0.3 | 0.07 → 0.018 | 2 | 1 | 0.55 | 0.0 → 0.2 |

`barriers`, `roads`, `coast`, the POI quotas and `landmarks` are unchanged.

**`validate.rs`** checks:

* `comps ≤ compose.slots`, and `story ≤ 3`;
* `frame` is in 0..=1;
* `slots` is in 1..=8, `edge_band ≤ 2`, and `edge_share` is in 0.5..=1;
* `slot_clear ≥ LANE`;
* `anchor_radius.0 ≤ anchor_radius.1 ≤ 3.0`, and `frame_run.0 ≤ frame_run.1`;
* `vignette_area ≥ 500`;
* `light_box` is at least 8 u on each side and at most (34, 21), so a screen still contains a whole
  box.

#### 3.6.10 The EA rooms (`procgen::generate`, per room until phase 4)

The same principles apply at room scale. A room is 80–104 × 54–68 u, about 2 × 2 screens. Its
guarantees stay:

* the spawn, plaza and gate keep-outs, and the lanes;
* `arenas_are_horde_sized_and_open` passes, including ≥ 15 obstacles in every Combat seed;
* sealed floor is 0.00 for heroes and ≤ 0.01 % for elites;
* no obstacle is undressed.

**Before** (`layout-stats --seeds 20`, all four biomes):

* block 4.3–4.9 % (Treasure 3.5–3.8 %);
* open (free floor ≥ 5 u from any obstacle) 42–46 % (Anvil 38–43 %);
* Combat rooms hold 58–75 obstacles;
* squeezes per room: Cinder 23, Verdant 35, Spire and Unmaking 1–4.

**Changes:**

1. **Step 4, the top-up.** `cover_target` goes down:
   - Combat and Elite: 0.050 → 0.032;
   - Anvil: 0.044 → 0.028;
   - others: 0.031 → 0.022.

   The composition-skirt branch (40 % of candidates) goes, so every top-up ruin stands in the north
   and flank rim band (RIM + 2 to RIM + 7 u in), which is the room's frame. Satellites go from 1–2
   to 0–1. The south edge stays open, because it stands between the camera and the fight.
2. **`field()`, `anchor()` and `court()`** take the map behaviour. Their `b.mask.is_some()` gates
   from §3.6.3 go, leaving one code path. In rooms the field's anchor chance is 0.7. `lane_pad` and
   the fissure heat rule stay map-only.
3. **`dress_floor()`.** Base dressing lies only at `Wall` bases (rubble). Verdant keeps its cover
   patches, because grass is its identity. The fissures seeping in from the rim are unchanged.
4. **Unchanged:** `dress_rim()`, `dress_heart()`, `frame_plaza()`, `arches()` and `colossus()`. They
   are the room's frame, its lights and its meaningful pieces.

**Targets** (`layout-stats --seeds 40`, means per biome and kind):

* block ≤ 3.4 % for Combat, Elite and Anvil;
* open ≥ 52 %;
* squeezes at most half of before;
* sealed and undressed as above;
* ≥ 15 obstacles in every Combat seed (the existing test).

If a biome's rooms cannot meet the open target with composition cover alone, the rim band takes
more. The interior never does.

The phase-4 EA **maps** inherit §3.6 through the `RegionTheme` and `ComposeDef` defaults. Each
biome picks its own `Scenery` reskin, and Verdant keeps grass at its edges.

#### 3.6.11 Determinism, streams and the hash

* **Rules.** Every new step follows §3.1:
  - integer `GfRng` draws;
  - `+ − × ÷ √` only;
  - integer sort keys;
  - `qv` on every obstacle coordinate and on new decor too (decor is not hashed, but peers should
    look alike).
* **Shore order and outward directions** come from tile BFS steps and sums of axis neighbours,
  normalized with `√`.
* **New forks** use bases ≥ 2000, clear of today's forks (all below 1200):

  | Fork | Stream | Use |
  |---|---|---|
  | `2000 + r` | lay | coast anchors |
  | `2100 + r` | dress | visual frame |
  | `2200 + r` | dress | vignettes |
  | `2300` | dress | light gaps |
  | `2400 + k` | dress | road-shoulder paving |

  The story and the field anchors stay on the region's lay stream `100 + r`. Changing one region's
  pieces never shifts another region.
* **The hash.** `MapLayout.hash` covers obstacles, pits, POIs, the spawn and the gate, never decor.
  - Every lay-stream change above moves it: re-pin `cinder_expedition_seed_7_golden_hash` once, in
    the commit that lands them.
  - The dress-stream steps (Scenery, vignettes, light gaps, paving, pass braziers, spring rings,
    floor dressing, fissure heat) leave it alone.
  - POI sites are placed before composition, so they do not move and the `--start-at` spots stay
    comparable. Camps may shift.
* **Guarantees kept.**
  - Reachability: the BFS and repair run unchanged; fewer obstacles only help.
  - 0 repairs, 0 relaxed, every POI placed.
  - Lanes, and the spawn, plaza and gate keep-outs.
  - `every_peer_rebuilds_the_hosts_procedural_arenas`.

#### 3.6.12 Work order and acceptance

**Concurrency.** Other workflows own these files, and nothing in §3.6 edits them:

* the UI workflow: `crates/gf_client/src/{hud, ui, offscreen, theme, uikit}.rs` and `assets/ui/`;
* the model-integration workflow: `crates/gf_client/src/{scene, palette, materials, models, anim,
  vfx}.rs`;
* the art agents: `art/` and `assets/models/`.

The floor paint uses existing `FloorParams` slots, `Scenery` renders in `envkit.rs`, and key lights
live in `world.rs`. If a floor parameter ever becomes unavoidable, the `materials.rs` change must be
minimal and additive, and reported.

**Every commit:**

* `cargo fmt`, then `cargo clippy --workspace --all-targets --release -- -D warnings`;
* `cargo test -p gf_content` (the full workspace for steps A and E);
* explicit pathspecs, no push.
* No new tests: the golden hash is re-pinned, never added to.

| Step | Files | Work | Proof |
|---|---|---|---|
| 0. Readout | `tools/gf_tools/src/preview.rs` | The §3.6.1 metrics as a second `layout-stats --maps` table (per map, plus the mean row), report-only. Record the before table (map seeds 1–8 and run maps 3 / 7 / 11). | The before numbers are within ±10 % of §3.6.2. Otherwise, the tool's numbers become the recorded baseline and the targets stay. |
| A. Lay rules | `worldgen/{compose, tiles, mod}.rs`, `procgen.rs` (map mode), `schema.rs` (theme fields, `ComposeDef`), `validate.rs`, `rooms.ron` (the Cinder values), `preview.rs` (gates on) | §3.6.3–3.6.4. Re-pin the golden hash. | Every gate in §3.6.2 passes on `layout-stats --maps --seeds 8`: 0 repairs, 0 relaxed, all POIs. |
| B. Frame and dressing | `schema.rs` (`Scenery`), `compose.rs` (`frame`, `vignettes`, light gaps, paving, pass braziers, floor dressing), `procgen.rs` (`fissure` heat), `envkit.rs`, `world.rs` (gallery, key lights, `accent.w`), `shaders/floor.wesl`, `preview.rs` (`Scenery` legend) | §3.6.5–3.6.8. The hash does not move. | The report rows of §3.6.2 hold. |
| C. Pacing | `assets/content/rooms.ron` (`seals_required`, `threat`), §2.2 of this doc | The bot run below, then retune. | Victory in the band. |
| D. Look | — | The before/after previews and screenshots below; send the user the 2–3 best pairs. | By eye. |
| E. EA rooms | `procgen.rs` (rooms), `tools/gf_tools/src/preview.rs` if a column is needed | §3.6.10 | Room targets, `preview-sheet` before/after, the `--phase ea` run. |

**Acceptance checks.**

1. **Previews**, before and after, of the maps the game plays for run seeds 7, 3 and 11:

   ```text
   cargo run --release -p gf_tools -- preview-room cinder_expedition 3047268829 shots/dc_after_map_run7.png --scale 2
   cargo run --release -p gf_tools -- preview-room cinder_expedition 2298633409 shots/dc_after_map_run3.png --scale 2
   cargo run --release -p gf_tools -- preview-room cinder_expedition 3195035749 shots/dc_after_map_run11.png --scale 2
   ```

   Compare them against `shots/dc_before_map_run{3,7,11}.png`, and against the audit's 150 × 100 u
   foundry and shrine crops at scale 6. Look at every image.
2. **Readout.** Paste the `layout-stats --maps --seeds 8` composition table (all gates green) and
   the per-kind table of §3.6.2 (run maps 3 / 7 / 11, before → after) into the step-A and step-B
   commit bodies.
3. **In game**, at the same spots as the audit's `dc_before_*` shots. Copy the release exe and run
   the copy, never `target/release` itself:

   ```text
   <copy> --autoplay --bots 3 --seed 7 --window 1600x900 --screenshot shots/dc_after_<spot>.png <extra flags>
   ```

   with these extra flags:

   | Spot | Extra flags |
   |---|---|
   | landing | `--screenshot-after 8 --shots 2 --shot-interval 12 --exit-after 24` (no `--start-at`) |
   | roadleg | `--screenshot-after 30 --shots 2 --shot-interval 10 --exit-after 44` |
   | road | `--start-at spring` |
   | anvil, lair, shrine, warlord, gate | `--start-at <kind>` |
   | horde300 | `--horde 300 --fps` |

   Unless listed, a spot uses `--screenshot-after 15 --shots 3 --shot-interval 6 --exit-after 40`.
   Look at every image. A minimized window writes 1 × 1 px images: re-run those.
4. **Pacing.** One `--bot-run --seed 7` (a copy of the release exe) must end in **Victory** with the
   Cinder stage in **6–10 sim-min**. Aim for 6.3–8.5 sim-min to keep margin on both sides.
   - **Before:** 367.2 s (6.12 min). The audit's data-only declutter already fell below the band:
     `cover` 0 gave 327.5 s.
   - **Retune ladder**, one rung at a time, re-running after each:
     1. `seals_required` 7 → 8 (6 → 7 added ≈ 42 s in phase 2; 14 Seals on offer still satisfy
        `≥ required + 2`);
     2. then all `threat` `hp_mult` rows +10 %;
     3. if the stage goes over 9 min, step back.
   - Update §2.2 (the seals note and the table) to the result.
5. **Frame rate and build.** From the `--horde 300 --fps` run (the audit measured the before on an
   RTX 4070 laptop):

   | Measure | Before | After |
   |---|---|---|
   | Mean fps at `--horde 300` | 90–105 | no lower |
   | Worst frame | 18.6 ms | ≤ 20 ms |
   | World build | 113–154 ms | ≤ 150 ms (§7.2) |
   | Vertices | 2.03 M | ≤ 2.03 M |
   | Draws | 827 | ≤ 827 |
   | Lights (flames) | 296 | reported |

   `GF_ENV_STATS=1` prints the per-variant vertex cost. `Scenery` must stay ≤ 300 k vertices per
   map.
6. **EA rooms** (step E):
   - `preview-sheet shots/dc_rooms_{before,after}_<biome>.png --biome <biome> --seeds 6` for
     `cinder_wastes`, `verdant_ruin`, `hollow_spire` and `the_unmaking`;
   - the `layout-stats --seeds 40` table against §3.6.10;
   - `cargo test --workspace`;
   - `--bot-run --phase ea --seed 7`, once before step E and once after: Victory, comparing the
     report's `rooms[]` clear times. Retune a biome's `encounter` data in `rooms.ron` only if its
     rooms move by more than 15 %.

---

## 4. Data model

### 4.1 `gf_core`

```rust
// crates/gf_core/src/poi.rs (new; re-exported in lib.rs). Shared by content, sim and wire.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum PoiKind { Anvil, Warlord, Lair, Shrine, Reliquary, Vein, Spring, Watchfire, Gate }

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum PoiState { #[default] Dormant, Active, Hot, Done, Sealed, Open, Gathering }
impl PoiState { pub fn to_u8(self) -> u8; pub fn from_u8(v: u8) -> Self } // EntityView.status
```

```rust
// crates/gf_core/src/movement.rs
pub struct Arena {
    pub half_extents: Vec2,
    pub obstacles: Vec<Obstacle>,
    /// Walker-only blockers (void and liquid tiles on biome maps). Movers are pushed out;
    /// projectiles, beams, telegraphs and line of fire pass over them.
    #[serde(default)] pub pits: Vec<Obstacle>,
    #[serde(skip)] index: ObstacleIndex,  // private: construct with Arena::new
}
// PartialEq is hand-written: half_extents, obstacles, pits.
impl Arena {
    pub fn new(half_extents: Vec2, obstacles: Vec<Obstacle>, pits: Vec<Obstacle>) -> Self;
    pub fn rect(half_extents: Vec2) -> Self;
    /// Two passes. Each pass gathers candidates (obstacles, then pits) from the cells overlapping
    /// p ± (r + 0.05), sorts and dedups them ascending, applies push_out in that order, then clamps.
    pub fn resolve(&self, p: Vec2, r: f32) -> Vec2;
    pub fn blocks_shot(&self, p: Vec2) -> bool;                            // obstacles only
    pub fn occluders(&self, c: Vec2, reach: f32, out: &mut Vec<Obstacle>);  // obstacles only, ascending
    pub fn walkable(&self, p: Vec2, r: f32) -> bool;                        // no obstacle or pit overlaps
    pub fn segment_blocked(&self, a: Vec2, b: Vec2, r: f32) -> bool;        // obstacles only
    pub fn in_bounds(&self, p: Vec2) -> bool;
}
/// CSR uniform grid, 4 u cells. Each obstacle is inserted into every cell its AABB overlaps.
/// Items index `obstacles`, with pits offset by `obstacles.len()`.
struct ObstacleIndex { origin: Vec2, w: u32, h: u32, start: Vec<u32>, items: Vec<u32> }
```

An empty index (from `rect`, `Default` or serde) falls back to the linear scan. Host and client
prediction share the code, so they agree bit for bit. Legacy rooms may differ from the old full scan
in rare corner pushes, which is accepted.

### 4.2 `gf_content::schema`

```rust
pub enum RoomKind { Combat, Elite, Anvil, MiniBoss, Boss, Treasure, Expedition }

pub struct RoomDef {
    /* …existing fields, including motifs / rim / districts / lanes… */
    /// Expedition templates only: the biome map's configuration.
    #[serde(default)] pub expedition: Option<Box<ExpeditionDef>>,
    /// Generated biome maps only (never authored; not serialized).
    #[serde(skip)] pub map: Option<Arc<MapLayout>>,
}
impl RoomDef {
    /// The collision world every peer uses: Arena::new(half, obstacles, map.pits or []).
    pub fn arena(&self) -> Arena;
}

pub struct ExpeditionDef {
    pub size: Vec2,                        // (432, 272); multiples of 8; size/2 ≤ (240, 240)
    pub regions: (u8, u8),                 // (5, 3)
    pub themes: Vec<RegionTheme>,
    pub start_theme: String,               // an `open` theme key
    pub coast: CoastDef,                   // { depth: u8 = 2, amp: u8 = 3, period: u8 = 6 } (tiles)
    pub barriers: BarrierDef,              // { chance: f32 = 0.45, kinds: Vec<(BarrierKind, f32)> }
    pub roads: RoadDef,                    // { width: 6.0, loop_chance: 0.3, pass_width: 8.0 }
    pub pois: Vec<PoiQuota>,               // { kind: PoiKind, count: u8, seals: u8 }
    pub camps: CampDef,                    // { per_area: 4000.0, pack: (6, 12), elite_chance: 0.2, shards: (8, 15) }
    pub landmarks: Vec<(MapMark, f32)>,
    pub seals_required: u8,                // 7 (Cinder)
    pub gate_requires_warlord: bool,       // true
    pub gate_force_minute: f32,            // 12.0
    pub boss_hp_mult: f32,                 // 1.35 = today's boss after 7 rooms (hp_growth_per_room 0.05 × 7)
    pub threat_start_minute: f32,          // 0 / 4 / 7 / 9
    pub threat: Vec<ThreatKey>,            // { minute, density, rate, elite_chance, hp_mult }
    pub compose: ComposeDef,               // §3.6.9: slots, edge band, clearances, frame, vignettes, light
}
pub struct RegionTheme {
    pub key: String, pub name: String, pub weight: f32,
    pub districts: Vec<(DistrictKind, f32)>,   // room-grammar composition pool for this region's edge slots
    pub fields: f32,                           // share of open fields left bare; the rest hold one anchor (0..=1)
    pub cover: f32,                            // ceiling on interior colliding cover (0.0..=0.08)
    pub tint: String, pub map_color: String,   // "#RRGGBB": floor vertex tint, minimap land colour
    #[serde(default)] pub open: bool,          // may host the Landing
    #[serde(default)] pub camp_pool: Vec<WeightedKey>,
    #[serde(default)] pub names: Vec<String>,  // banner names the regions of this theme take in turn
    #[serde(default)] pub ground: GroundRecipe, // { paving, ash }: floor paint (presentation only)
    #[serde(default = "two")] pub comps: u8,   // compositions per region, edge slots only (§3.6.4)
    #[serde(default = "one")] pub story: u8,   // story clusters per region, on the frame band
    #[serde(default = "half")] pub frame: f32, // share of the void shore that is framed (§3.6.5)
}
pub enum BarrierKind { Chasm, River, Wall, Ridge }
pub enum MapMark { Statue, GreatBrazier, SealedGate, Tree, SpiralStair, InvertedColumn, Rift, Crystal,
                   ColossusHead, GreatAnvil, Crucible, FallenWeapon }

/// Generated. Shared as Arc by the sim, the client and bots.
#[derive(Clone, Debug, PartialEq)]
pub struct MapLayout {
    pub seed: u32,
    pub hash: u64,
    pub tiles: TileGrid,                 // { w: u16, h: u16, size: f32 = 4.0, origin: Vec2, kind: Vec<TileKind>, region: Vec<u8> }
    pub regions: Vec<Region>,            // { theme: u8, site: Vec2, landmark: Option<MapMark> }
    pub roads: Vec<Lane>,                // also copied to RoomDef.lanes
    pub passes: Vec<Pass>,               // { at: Vec2, along: Rot16, width: f32, kind: BarrierKind }
    pub pits: Vec<Obstacle>,
    pub pois: Vec<PoiSite>,              // { kind, at, radius, seals, region: u8, god: Option<u8>, guard: Option<u16> }
    pub gate: u8,                        // index into pois
    pub camps: Vec<CampSite>,            // { at, enemy: u16, count: u8, elite: Option<u16>, shards: u16 }
    pub relaxed: u8, pub repairs: u8,
}
pub enum TileKind { Void, Ground, Road, Plaza, Bridge, Liquid }
```

`Decor` gains one variant in phase 1 and uses it in phase 4:
`FallenWeapon { at: Vec2, radius: f32, height: f32, rot: Rot16, variant: u8 }`. It is solid, and the
variants are 0 sword, 1 hammer, 2 spear, 3 bow, 4 cannon. `is_solid`, `anchor` and `covers` extend
accordingly.

The composition pass adds a second variant, `Scenery { at, radius, height, kind: SceneryKind, rot,
variant }`, with `SceneryKind { Lip, Backdrop, Foreground }`. It is visual framing on the cliff lip
and in the void, and it never blocks (§3.6.5). Everything else reuses the existing vocabulary.

`GameTuning` gains `expedition: ExpeditionTuning` (all `#[serde(default)]`). The block below is its
game.ron form with the defaults:

```ron
expedition: (
    horde: (
        global_max_alive: 400, cluster_link: 30.0, census_bubble: 36.0, rate_mult: 1.0,
        view_pad: 4.0, view_aspect: 2.0, ring_margin: (3.0, 9.0), spawn_clear: 20.0, flow_detour: 1.6,
        emerge_time: 0.4, cull_distance: 56.0, cull_after: 5.0, hard_cull: 90.0, refund: 1.0,
        flow_refresh_ticks: 16, direct_chase_tiles: 12, event_ring: (18.0, 26.0), event_share: 0.5,
        surge: (from_minute: 3.0, interval: (85.0, 115.0), warn: 3.0, duration: 15.0, rate_mult: 2.0, arc_deg: 90.0),
        frenzy_rate: 1.4, frenzy_density: 25.0, heat_per_objective: 0.5,
    ),
    guards: (wake: 34.0, aggro: 16.0, leash: 45.0, reset_after: 6.0, regen: 0.1, sleep: 70.0,
             hunt_after: 20.0, hunt_radius: 25.0),
    gate: (radius: 7.0, gather: 10.0, gather_solo: 2.0, revive_frac: 0.5,
           unworthy_hp_per_seal: 0.25, unworthy_cap: 0.75),
    pois: [
        (kind: Anvil,     radius: 4.5,  plaza: 10.0, activation: Hold(time: 0.0, decay: 0.0, wave: 1.5, breaker_at: Some(0.6)), reward: Forge),
        (kind: Shrine,    radius: 4.0,  plaza: 8.0,  activation: Hold(time: 12.0, decay: 0.05, wave: 1.2, breaker_at: None), reward: Boon),
        (kind: Reliquary, radius: 4.0,  plaza: 8.0,  activation: Hold(time: 15.0, decay: 0.05, wave: 1.3, breaker_at: None), reward: Parts(extra: 0, min_rarity: Common, shards: 0)),
        (kind: Vein,      radius: 4.0,  plaza: 8.0,  activation: Hold(time: 20.0, decay: 0.03, wave: 1.4, breaker_at: Some(0.5)), reward: Shards(amount: 18)),
        (kind: Lair,      radius: 14.0, plaza: 14.0, activation: Clear(elites: 2, wave: 0.8), reward: Parts(extra: 1, min_rarity: Common, shards: 10)),
        (kind: Warlord,   radius: 18.0, plaza: 18.0, activation: Clear(elites: 0, wave: 0.6), reward: Parts(extra: 0, min_rarity: Rare, shards: 20)),
        (kind: Spring,    radius: 3.0,  plaza: 6.0,  activation: Use, reward: Heal(frac: 0.4)),
        (kind: Watchfire, radius: 2.5,  plaza: 5.0,  activation: Touch(channel: 1.0), reward: Reveal(radius: 80.0)),
        (kind: Gate,      radius: 7.0,  plaza: 14.0, activation: Gate, reward: Onward),
    ],
    stall_hint_secs: 150.0, ember_per_objective: 3.0,
    coop: (present_pad: 8.0, loot_share_radius: 36.0, tether_hopeless: 45.0, hopeless_downed: 3.0,
           reforge_offset: 2.0, part_owner_near: 40.0, vacuum_radius: 40.0, aegis_pad: 1.0),
    stride: (delay: 2.5, mult: 1.25, calm_radius: 12.0),
    fog: (cell: 2.0, reveal: 32.0, feather: 6.0, beacon_sight: 45.0),
    interest: (radius_in: 44.0, radius_out: 52.0, event_radius: 50.0, far_lod: 30.0),
),
```

```rust
pub struct PoiTuning { pub kind: PoiKind, pub radius: f32, pub plaza: f32, pub activation: PoiActivation, pub reward: PoiReward }
pub enum PoiActivation {
    Hold { time: f32 /*0 = anvil.hold_time*/, decay: f32, wave: f32, breaker_at: Option<f32> },
    Clear { elites: u8, wave: f32 },
    Use,
    Touch { channel: f32 },
    Gate,
}
pub enum PoiReward { Forge, Parts { extra: u8, min_rarity: Rarity, shards: u32 }, Shards { amount: u32 },
                     Boon, Heal { frac: f32 }, Reveal { radius: f32 }, Onward }
```

Anvil hold time, radius and forge window stay in the existing `anvil` block. `CameraTuning` gains
`look_ahead: f32 = 2.5`.

### 4.3 Content files

* **`rooms.ron`**: one Expedition template per biome, appended at the end of the file.
  - Phase 2 adds `cinder_expedition`.
  - Phase 4 kickoff adds placeholder entries for the other three, so each biome agent edits only
    its own block.
  - Existing rooms stay: boss arenas, QA rooms, and legacy door sequences until a biome flips.

  Cinder example (threat rows as in §2.5). It shows the composition values of §3.6.9;
  `names`, `ground` and `camp_pool` are left out:

  ```ron
  (
      key: "cinder_expedition", biome: "cinder_wastes", kind: Expedition, phase: P0,
      half_extents: (216.0, 136.0), player_spawn: (0.0, 0.0),
      spawn_zones: [Around(min: 27.0, max: 34.0)],
      encounter: (budget: 0.0, duration: 1.0, rate_start: 0.0, rate_end: 0.0, max_alive: 400, elite_chance: 0.0),
      expedition: (
          size: (432.0, 272.0), regions: (5, 3), start_theme: "slag_flats",
          themes: [
              (key: "slag_flats", name: "The Slag Flats", weight: 1.3, open: true, fields: 0.6, cover: 0.010,
               comps: 1, districts: [(SlagChannel, 1.0), (CrucibleYard, 0.6)], tint: "#737173", map_color: "#3C2A24"),
              (key: "foundry_ruins", name: "Foundry Ruins", weight: 1.0, fields: 0.2, cover: 0.022, frame: 0.55,
               districts: [(ForgeHall, 1.4), (CrucibleYard, 0.8), (ColonnadeCourt, 0.5)], tint: "#7A7777", map_color: "#4A403C"),
              (key: "colonnade_of_oaths", name: "Colonnade of Oaths", weight: 0.9, fields: 0.25, cover: 0.018,
               districts: [(ColonnadeCourt, 1.5), (ForgeHall, 0.4)], tint: "#8B867D", map_color: "#6E6252"),
              (key: "cinder_dunes", name: "Cinder Dunes", weight: 0.8, open: true, fields: 0.75, cover: 0.010,
               comps: 1, frame: 0.45, districts: [(SlagChannel, 0.6)], tint: "#8E8C8B", map_color: "#66625E"),
              (key: "chainyard", name: "The Chainyard", weight: 0.7, fields: 0.3, cover: 0.018, frame: 0.55,
               districts: [(CrucibleYard, 1.4), (ForgeHall, 0.6)], tint: "#8B796E", map_color: "#6A3826"),
          ],
          compose: (),   // §3.6.9 defaults
          coast: (depth: 2, amp: 6, period: 10),
          barriers: (chance: 0.45, kinds: [(River, 0.30), (Wall, 0.15)]),
          roads: (width: 6.0, loop_chance: 0.3, pass_width: 8.0),
          pois: [(kind: Anvil, count: 3, seals: 1), (kind: Warlord, count: 1, seals: 2), (kind: Lair, count: 2, seals: 1),
                 (kind: Shrine, count: 3, seals: 1), (kind: Reliquary, count: 2, seals: 1), (kind: Vein, count: 2, seals: 1),
                 (kind: Spring, count: 3, seals: 0)],          // Watchfire quota added in phase 3
          camps: (per_area: 4000.0, pack: (6, 12), elite_chance: 0.2, shards: (8, 15)),
          landmarks: [(FallenWeapon, 1.2), (GreatAnvil, 1.0), (Statue, 1.0), (ColossusHead, 0.5), (GreatBrazier, 0.7)],
          seals_required: 7,   // the §3.6.12 pacing check may raise it to 8
          gate_requires_warlord: true, gate_force_minute: 12.0, boss_hp_mult: 1.35,
          threat_start_minute: 0.0,
          threat: [ /* §2.5 */ ],
      ),
  ),
  ```

* **`biomes.ron`**: a biome flips to `sequence: [Fixed(Expedition), Fixed(Boss)]` when its template
  lands (Cinder at the end of phase 2, the rest in phase 4). `min_anvils` is ignored for Expedition
  sequences.
* **`game.ron`**: the `expedition` block above, and `camera.look_ahead`.

### 4.4 Validation (`validate.rs`)

* **Expedition templates.**
  - `expedition` is `Some` iff the kind is `Expedition`. `half_extents == size / 2` and `size / 2 ≤ (240, 240)`.
  - `regions` each in 2..=8, with cells ≥ 48 u.
  - Themes non-empty, weights > 0, `start_theme` exists and is `open`, colours are hex, `camp_pool`
    keys are the biome's swarm/elite enemies, district weights > 0.
  - Composition knobs (§3.6.9): `fields` in 0..=1, `cover` in 0..=0.08, `comps ≤ compose.slots`,
    `story ≤ 3`, `frame` in 0..=1, plus the `ComposeDef` ranges listed there.
  - Quotas: anvils ≥ 2 (the slice's "≥ 2 anvils"). Exactly one Warlord quota if
    `gate_requires_warlord`, and `biome.minibosses` non-empty. Shrines ≤ gods with
    `phase ≤ max(template.phase, P1)`. `Σ seals × count ≥ seals_required + 2`. No `Gate` quota (the
    gate is implicit).
  - `threat`: non-empty, the first row at minute 0, minutes strictly increasing, density ≤
    `global_max_alive`, rate > 0.
  - The "non-boss rooms need an exit" rule is waived.
* **game.ron.** Every `PoiKind` except `Gate` appears once in `expedition.pois`. `Forge` only on Anvil,
  `Boon` only on Shrine, and `Gate` activation only on Gate. `plaza ≥ radius`, `leash > wake`.
* **Biomes.** A sequence containing `Fixed(Expedition)` needs that template in the biome, and the boss
  room exists.
* **Tools only**, never at load: `gf-content layout-stats --maps --seeds 8` generates every shipped
  template × 8 seeds. It fails on:
  - repairs > 0 for POIs or the gate;
  - `relaxed > 0`;
  - gen time > 400 ms in debug;
  - any composition gate of §3.6.2, once step A of §3.6.12 has landed.

---

## 5. Simulation (`gf_sim`)

### 5.1 Run flow

```text
start_run → load_room(<biome>_expedition, room_seed)            [kind Expedition, RunPhase::Combat]
  poi_update: POIs → Seals ─► expedition_flow: Sealed → Open (seals ≥ req ∧ warlord, or forced) → Gathering
                              → revive, spoils, run.next_boss_hp, run.pending_door = Some(Onward)
room_transition (unchanged) → step 1 = Fixed(Boss) → load_room(boss, seed 0) → existing Cleared → Onward door
room_transition (unchanged) → next biome, step 0 = Fixed(Expedition) → new map … last boss → Victory
```

* **`load_room`** (run.rs):
  - Builds the arena with `room.arena()`.
  - When `room.map` is set: calls `poi::spawn_pois(world, &map)`, inserts `Expedition` from the
    template, sizes `Flow` to the tile grid, and sets `Encounter { budget_left: 1.0, budget_total: 1.0 }`,
    which keeps `encounter_left = 1.0`, so the bot mop-up never fires.
  - Fixed spawns of a `Boss` room multiply `hp_mult` by `run.next_boss_hp`, then reset it to 1.0.
* **`room_flow`** returns before its clear check when `run.room_kind == Expedition`.
* **`run_director`** computes `enc.alive`, runs the stress branch (unchanged, any room kind), then
  returns early for Expedition.
* **`players::spawn_player`** (join in progress): on a map, spawns beside the nearest living player,
  offset and resolved. Otherwise it uses `player_spawn` as today.
* **QA.** `SimConfig.start_at: Option<PoiKind>` (and `--start-at <kind>`) places the party beside the
  first POI of that kind at run start.

### 5.2 Components and resources

```rust
// components.rs
#[derive(Component)] pub struct Poi {
    pub index: u8, pub kind: PoiKind, pub state: PoiState, pub progress: f32, pub timer: f32,
    pub contested: bool, pub claimed: u8 /*slot mask*/, pub guards: u8, pub seals: u8, pub god: Option<u8>,
}
#[derive(Component)] pub struct Guard {          // lair elites, the warlord, camp members
    pub home: Vec2, pub poi: Option<u8>, pub camp: Option<u16>,
    pub awake: bool, pub away: f32, pub untouched: f32, pub hunt: bool,
}
#[derive(Component)] pub struct Roaming { pub cluster: u8, pub far: f32, pub cost: f32 } // director spawns (cullable)
#[derive(Component)] pub struct Born(pub u32);   // spawn tick → EntityFlags::EMERGING for emerge_time
// AnvilStation gains `granted: u8` (slot mask). Arsenal gains `charges_from: Option<Entity>`.
// BoonChoice gains `queue: Vec<u8>` (gods waiting to offer). Life gains `hopeless: bool`.
```

```rust
// resources.rs
#[derive(Resource, Default)] pub struct Expedition {
    pub active: bool, pub time: f32, pub seals: u8, pub required: u8, pub warlord_done: bool,
    pub gate: GateState /* Sealed | Open | Gathering { left: f32 } */, pub forced: bool,
    pub objectives: u8, pub last_progress: f32, pub threat_level: u8,
    pub surge: Option<Surge /* { dir: Vec2, warn: f32, left: f32 } */>, pub next_surge: f32,
    pub clusters: Vec<Cluster /* { members: u8 mask, n: u8, centroid: Vec2, count: u32 } */>,
    pub accum: [f32; 4],                  // per cluster id = lowest slot
    pub camps: Vec<CampRuntime /* { state: Asleep|Awake|Cleared, left: u8 } */>,
    pub explored: Vec<u64>,               // host-side 4 u tile bits (join-in-progress fog, phase 3)
}
#[derive(Resource)] pub struct ClusterTuning(pub [EnemyTuning; 4]); // retune_party: k = 1..=4
#[derive(Resource, Default)] pub struct Flow { pub w: u16, pub h: u16, pub cost: Vec<u8>, pub dist: [Vec<u16>; 4], pub next: u8 }
// RunState gains `next_boss_hp: f32` (default 1.0). Rngs gains `world: GfRng` (fork 6: camps, surges).
```

### 5.3 POI lifecycles (`poi.rs`, new)

* **Anvil**: the existing `AnvilStation` state machine (`anvil_update`) plus a `Poi` component. The
  snapshot maps `AnvilState` to `PoiState`. The fixes:
  - **Per-anvil charges.** On Kindling → Hot, and for every living player who enters `radius + 1`
    while Hot, a bit is set in `granted`: `wallet.charges = charges_per_anvil`,
    `charges_from = Some(anvil)`. On Spent, only players with `charges_from == anvil` lose charges.
  - `+seals` on Kindling → Hot.
  - The **Breaker**: one biome elite on the ring at `breaker_at`.
  - The forge-focus rule is unchanged.
* **Hold** (Shrine, Reliquary, Vein):
  - Dormant → interact inside `radius` → Active.
  - Progress grows by `dt / time` while a living player is inside. When the ring is empty it decays by
    `decay·dt` (`contested`).
  - The breaker elite spawns at `breaker_at`.
  - At 1.0 the POI goes Done and pays its reward (§2.4).
  - If contested continuously for 30 s, its wave stops (progress is kept).
* **Clear** (Lair, Warlord):
  - Guards spawn when any player comes within `guards.wake`: the lair's `elites` biome elites plus a
    pack, or the Warlord's mini-boss. They stand `Idle` at `home`.
  - They wake (`Guard.awake`, POI Active) when a player is within `aggro` or on damage.
  - Done when all guards are dead. `PoiSite.guard` fixes the Warlord's (or lead elite's) enemy at
    generation.
  - Guards and the Warlord get **cluster HP** from the waking player's cluster.
* **Use** (Spring): interact inside `radius` → heal, and set the player's `claimed` bit. The POI is
  Done when every connected player has claimed it.
* **Touch** (Watchfire, phase 3): a `channel` s stand → Done (Lit). The client reveals fog around lit
  watchfires.
* **Gate** (in `expedition_flow`):
  - Sealed → Open when `seals ≥ required ∧ (warlord_done ∨ !requires)`, or when
    `time ≥ gate_force_minute` (`forced`).
  - Open → interact inside `gate.radius` → Gathering (`gather`, or `gather_solo` with one player). It
    finishes early when every living player is inside.
  - At zero: revive downed and reforging players at `revive_frac`, grant every owned pickup to its owner
    (`players::grant_pickup`), set `run.next_boss_hp = boss_hp_mult × unworthy`, `run.depth += 1`, and
    `pending_door = Some(Onward)`.
* **Guard leash.** An awake guard is sent home when every player has been beyond `leash` from its home
  for `reset_after`. It regenerates `regen` of max HP per second, and its POI goes back to Dormant.
  **Anti-hide**: a guard that takes no damage for `hunt_after` while a player is within `hunt_radius`
  sets `hunt`, so keep-distance behaviours chase instead.

### 5.4 Reward mapping (reuse)

`run::grant_reward(reward, …)` is extracted from `room_flow`'s Combat → Cleared branch, and both
`room_flow` (legacy and boss rooms) and `poi.rs` call it:

| Old `DoorReward` path | POI | Scope |
|---|---|---|
| `PartCache` / `EliteChallenge` (`cache_parts` / `+1`) | Reliquary / Lair / Warlord (`Parts { extra, min_rarity }`, rolled with `roll_part(.., min)`) | present |
| `ShardCache` (`cache_shards × loot`) | Vein | party |
| `Boon { god }` (`make_offer`) | Shrine (god from `PoiSite.god`) into `BoonChoice.queue`, then the next offer when one is picked | present + late claim |
| `Healing` (40 %) | Spring | per player |
| `Anvil` | Anvil | per claimant |
| `Onward` | Gate | party |

### 5.5 Horde director v2 (`horde.rs`, new; runs only on Expedition)

1. **Clusters** (every 15 ticks). Group living players by single linkage within `cluster_link`.
   Clusters are identified by their lowest slot.
2. **Census** (every tick, one pass over enemies). For each living enemy, take the nearest living
   player (O(400 × 4)). If it is within `census_bubble`, add 1 to that player's cluster count. Update
   the `Roaming` far timer (§5.6).
3. **Sample threat** at `T`. `hp = key.hp_mult × (1 + hp_growth_per_biome × biome_idx)`.
4. **Per cluster `c`** of size `n`, with `ct = ClusterTuning[n-1]`:
   - `target_c = key.density × ct.count (+ frenzy_density)`
   - `rate_c = key.rate × ct.count × ct.spawn_rate × horde.rate_mult × surge × frenzy × hold_wave`
   - `accum_c += rate_c × dt`
   - While `accum_c ≥ 1 ∧ count_c < target_c ∧ alive < global_max_alive`: spawn a pack with today's
     rules (elite roll `key.elite_chance + ct.elite_chance_add`, swarm cost 1, elite cost 6, pack size
     × `√ct.count`), using `spawn_enemy(.., &Tuning { enemy: ct, party: n }, hp, ..)`. Add
     `Roaming { cluster, cost }` and `Born(tick)`.
5. **Spawn point** (rejection, 12 tries, else skip and keep the accumulator):
   - Pick a random member `m` of the cluster. The host estimates a view footprint of
     `half = (vh × view_aspect / 2, vh / (2 × sin 55°))`, where `vh = camera.view_height[party-1] + view_pad`.
     `sin 55°` is a literal constant (0.819152).
   - The candidate is uniform on the rectangle ring `half + ring_margin` around `m`. During a surge
     it is limited to the surge arc (a dot-product test). With a Hold wave, `event_share` of spawns
     take a point on `event_ring` around the POI instead.
   - Accept when all of these hold:
     - the tile is walkable and `arena.walkable(p, radius)`;
     - p is outside **every** living player's footprint (+1 u);
     - p is at least `spawn_clear` from every player;
     - `flow_dist(m, p) ≤ flow_detour × |p − m| + 8 u`, so no spawns across a chasm.
6. **Camps** (`horde::guards`):
   - A sleeping camp wakes when a player comes within `guards.wake` (if the global cap allows): its
     remaining members spawn as idle `Guard`s.
   - An awake camp sleeps (despawn, store what is left) when every player is beyond `guards.sleep`.
   - When cleared, the camp drops its shard pile and never returns. `GameEvent::CampCleared`.
7. **Stress mode** (`--stress`) stays in `run_director` and works on maps unchanged.

### 5.6 Far cull, leash and flow fields

* **Far cull.** A `Roaming` enemy's `far` grows while its nearest living player is beyond
  `cull_distance`. It is despawned silently (no drops, no kill credit) when `far > cull_after` or the
  distance exceeds `hard_cull`, and `cost × refund` goes back to its cluster's accumulator. Bosses,
  Warlords and guards are never culled (guards leash). A lone downed player's cluster dissolves, so
  its horde culls, and the reforged player returns to a calmer spot.
* **Flow fields** (`flow.rs`, host only, integer, deterministic).
  - `Flow.cost` per tile: Road 8, Plaza/Bridge 9, Ground 10, +40 when obstacle coverage exceeds 50 %
    (sampled from the arena index at 4 points per tile at load), and impassable for Void/Liquid.
  - One slot's field refreshes every `flow_refresh_ticks / 4` ticks (round robin): 8-neighbour
    Dijkstra with 10/14 × cost and a fixed neighbour order, from that player's tile.
  - In `enemy_ai`, before behaviour logic: if the tile line (Bresenham) to the target is at most
    `direct_chase_tiles` long and fully passable, chase directly (today). Otherwise `dir_to` points to
    the centre of the lowest-`dist` neighbour tile in the target's field.
  - This fixes hordes piling at chasm banks and behind long walls, and it funnels them over bridges.

### 5.7 Anti-stall ladder

1. Hold POIs pause (anvil) or decay (others) when empty. Contested for 30 s, the wave stops.
2. Guards leash home and regenerate. The anti-hide `hunt` applies.
3. Far cull with refund, so stragglers never stall pressure. The straggler teleport stays arena-only.
4. No objective progress for `stall_hint_secs` while `seals < required`: `GameEvent::PoiHint` for the
   nearest incomplete seal POI (HUD: "The Forge whispers…").
5. The gate is forced open at `gate_force_minute` (Unworthy). A map can't soft-lock.
6. The headless runner fails a run with no objective progress for 5 sim-minutes and prints the POI and
   bot trace (`GODFORGE_TRACE`).

### 5.8 Schedule (`lib.rs`)

* **Spatial**: `enemies::rebuild_grid` → `flow::refresh_flow`.
* **World**:
  1. `collect_pickups`
  2. `anvil_update`
  3. `poi::poi_update` (new)
  4. `forge_actions`
  5. `boon_actions`
  6. `run_director` (stress + legacy)
  7. `horde::run_horde` (new)
  8. `horde::guards` (new)
  9. `horde::far_cull` (new)
  10. `life_update`
  11. `room_flow`
  12. `poi::expedition_flow` (new)
  13. `door_choice`
  14. `room_transition`
* **Cleanup**: unchanged.

The order is fixed and single-threaded, so replays stay deterministic.

### 5.9 Split-party rules

| System | Rule |
|---|---|
| Spawning and aggro | Per cluster (§5.5). `pick_target` stays nearest-player (your own cluster in practice), and Siege Stance taunt is unchanged. Telegraphs matter only locally. |
| Soul-Tether | Unchanged (3.5 u, 3 s). **Hopeless**: while no living ally is within `tether_hopeless`, `life_update` clamps `Downed.remaining` to `hopeless_downed` (3 s), so out time is ≤ 13 s. `PrivateView.hopeless` drives the HUD line "Too far to revive: the Forge will reforge you beside P2". The 30 s rule still holds. No gf_core change. |
| Reforge | `LifeEvent::Reforged` teleports to the nearest living ally + `reforge_offset` (resolved), with the existing 2 s iframes. With no ally (solo Rekindle), in place. |
| Team Overdrive | Unchanged: shared meter, buffs everyone everywhere. The toast names the trigger and their direction. |
| Forge focus | Unchanged rule: slow-mo only when **every** living player is at a Hot anvil with the forge open. |
| Forge Aegis | While an anvil is Hot, enemies are pushed out of `radius + aegis_pad` (`enemy_motion`), and hits on players inside the ring are dropped (`resolve_player_hits`). A lone forger in split co-op is safe without global slow-mo. |
| Loot | Personal part rolls in `process_kills` only for players within `loot_share_radius` of the kill. On maps, parts age only while no eligible owner is within `part_owner_near` (lifetime `pickup_lifetime`), and shards and health age as today. POI completion vacuums pickups within `vacuum_radius`. |
| Stride | A self-buff (`ActiveBuff`, `Modifier::MoveSpeed(mult)`, source 5) after `delay` s with no damage taken, no firing and no enemy within `calm_radius`. It drops instantly. It flows into `PlayerView.move_speed`, so prediction replays it like any buff. |
| Pings | `PlayerAction::MapPing(QPos)` from the full map becomes the existing `GameEvent::Ping`. |
| Boss bars | `RunView.boss` excludes `Guard`ed enemies (arena bosses only). `PrivateView.boss` is the nearest awake guarded boss-like within 40 u of *me*. |

---

## 6. Protocol and netcode

### 6.1 Protocol v3 (`gf_net/src/protocol.rs`, one bump in phase 2 step 0)

```rust
pub const PROTOCOL_VERSION: u16 = 3;
pub enum PlayerAction { Forge(ForgeAction), ChooseDoor(u8), PickBoon(u8), RerollBoons, MapPing(QPos) }
pub struct RunView {
    /* existing fields, minus `anvil` */
    pub layout_hash: u32,                 // MapLayout.hash as u32 (0 for rooms); clients compare
    pub stage: Option<StageView>,         // Some on maps
}
pub struct StageView { pub seals: u8, pub required: u8, pub warlord: bool, pub gate: GateView, pub time: f32,
                       pub threat: u8 /*level×16 + frac*/, pub surge: Option<u16> /*arc dir*/, pub objectives: u8, pub forced: bool }
pub enum GateView { Sealed, Open, Gathering { left_ds: u8 } }
pub struct PrivateView { /* existing */ pub anvil: Option<AnvilView>, pub boss: Option<BossView>,
                         pub boon_queue: u8, pub hopeless: bool }
pub enum EntityKind { /* existing */ Poi { index: u8 } }  // status = PoiState, hp = progress; kind and position from MapLayout
// EntityFlags: CONTESTED = 4096, EMERGING = 8192
pub enum GameEvent { /* existing */ PoiStarted { index: u8, slot: u8 }, PoiCompleted { index: u8 }, PoiReset { index: u8 },
    PoiHint { index: u8 }, SealGained { seals: u8, required: u8 }, GateOpened { forced: bool }, GateGathering { slot: u8 },
    Surge { dir: u16, warn: bool }, ThreatRose { level: u8 }, CampCleared { at: QPos } }
pub struct SnapshotPacket { /* existing */ pub fog: Option<Vec<u8>> } // RLE explored tiles on full snapshots (phase 3)
```

* **`PrivateView.anvil`** is the anvil my charges come from, else the nearest non-Spent anvil within
  40 u. It replaces `RunView.anvil` everywhere (HUD prompt, forge panel, bot, `animate_anvils`).
  Legacy anvil rooms use the same rule. `EntityKind::Anvil` stays (legacy rooms), with `status` =
  `AnvilState`, so `animate_anvils` reads per-entity state.
* **Map desync check.** When `layout_hash` differs from the local map's hash, the client logs both,
  shows "Map desync (host X / local Y)" and leaves the session.

### 6.2 Bandwidth

| Case | Estimate per remote at 20 Hz | Gate |
|---|---|---|
| POIs (~20, delta-free unless active), `StageView` +~16 B, `PrivateView` +~24 B | < 1.5 KB/s | — |
| 4P grouped peak (400 relevant) after event compaction | 80–150 KB/s | p99 ≤ 160 KB/s |
| 4P split into 4 clusters (~100 relevant each) | 20–45 KB/s | p99 ≤ 60 KB/s |
| Fog RLE on full snapshots | ≤ 1 KB once | — |

### 6.3 Interest management and event compaction (phase 3, `gf_net/src/server.rs`)

* `broadcast(.., interest: &Interest)` with `Interest { centre: [Option<Vec2>; 4] /*by slot*/, r_in, r_out, far_lod, event_r }`.
  `SimServer::tick` fills it from the players' positions.
* **Relevance.**
  - Always relevant: `Poi`, `Anvil`, `Door`, `BOSS`-flagged enemies, and a client's own turrets and
    blades.
  - Otherwise an entity is relevant within `r_in` of the client's player, or within `r_out` if it was
    in that client's last set (hysteresis).
  - Motion entities are tested at their extrapolated position.
* **Per-client baselines.** `history` moves into `Client` (a 64-deep `VecDeque<(u32, Vec<EntityView>)>`
  of what that client was sent), and deltas diff against it. Client code is unchanged: an entity
  leaving relevance is a normal removal.
* **LOD.** Enemies beyond `far_lod` go into `changed` only on even snapshots.
* **Event filter.** Positional events (`Hit`, `Kill`, `Explosion`, `Arc`, `Synergy`, `Ability`,
  `TelegraphResolved`, and `Shot` via its slot's position) are dropped beyond `event_r`.
* **Event compaction.** `Hit` events whose source is not this client's slot are merged per target per
  snapshot (amounts summed, flags OR-ed). Damage numbers are own-damage only, so nothing visible is lost.
* `PlayerView` is still sent for everyone. The minimap, off-screen arrows and fog need it.
* `ServerStats` gains `bytes_per_client_p99` and `max_relevant`, and the bot-run report prints both.

---

## 7. Client (`gf_client`)

### 7.1 Stage load

* `CurrentRoom::sync` is unchanged: it calls `resolve_room`, which now generates the map (≤ 60 ms
  release).
* `pred.arena = Arc::new(room.def.arena())`.
* `rebuild_room` branches: `room.def.map.is_some()` → `world::build_map`, otherwise today's `build_room`.
* A 0.35 s fade overlay covers every `generation` change (phase 3).

### 7.2 World rendering (`world.rs` + `envkit.rs`, new)

* **Env kit** (`envkit.rs`). Each `Decor` variant becomes a list of primitive parts: shape, transform
  and look key (stone, cap, metal, bronze, glow, rock, liquid, ink hull), reskinned per `BiomeLook`.
  - It covers the grammar's whole vocabulary: walls by `WallStyle`, boulders, statues, colossus heads,
    fallen columns and trees, great anvil, crucible, great brazier, sealed gate, arches, trees,
    crystals, spiral stairs, inverted columns, rifts, channels, bridges, pools, paving, inlays, ground
    cover, roots, rubble, clutter, banners, chains, debris, and `FallenWeapon` in phase 4. The
    composition pass adds `Scenery`: lip fragments, backdrop silhouettes and foreground shapes
    (§3.6.5).
  - Solid decor replaces the greybox for the obstacles it `covers`, and undressed obstacles keep the
    greybox.
  - Rooms use the same kit, which retires the `_ => {}` arm in `scene.rs`. If a room env kit lands
    first from the layout-grammar work, 2F adopts it and only adds chunk merging.
  - Environment primitives are faceted (cylinders and spheres at 8–12 segments), which suits the toon
    look and keeps vertex counts low.
* **Chunks.** All chunks are built at map load, under the fade: ≤ 150 ms release. If that budget is
  missed, the 3 × 3 chunks around the Landing are built synchronously and the rest at ≤ 4 per frame.
  - Each chunk is `ChunkRoot { cx, cy }` with **one merged mesh per look key** (≤ 8 draws), inverted
    ink hulls merged into the ink mesh.
  - Bevy's per-mesh frustum culling does the culling. There is no streaming and no despawn.
* **Land.**
  - **Floor**: per chunk, quads over land tiles, with `ATTRIBUTE_COLOR` = the region `tint` (averaged
    at vertices, so borders blend). Boundary vertices next to Void/Liquid are jittered **outward only**
    (0–0.6 u, hashed on world position), so the visible lip always covers the walkable area.
  - **Cliffs**: along every land→Void edge, the existing `PROFILE` down to −9.5 (shared helpers moved
    out of `terrain.rs`). Along land→Liquid edges, a shallow bank to −0.6 and a liquid surface quad at
    −0.45 per Liquid tile with the biome's `AbyssMaterial` (slag, black water, star-sea, chaos).
  - **Abyss**: one plane under the whole map (+90 u).
  - **Bridges** are deck meshes with inked rails from `Decor::Bridge`.
* **Floor paint** (`materials.rs`, `floor.wesl`):
  - `FloorMaterial` is per chunk, and `shape` carries map half extents plus a map-mode flag that turns
    off the centre mosaic and rim vignette.
  - Per chunk: ≤ 48 lava cracks intersecting it (`FLOOR_CRACKS`, unchanged), roads intersecting it as
    worn paths (`FLOOR_PATHS` 6 → 8), and `plazas: [Vec4; 4]` (x, z, radius, style) for POI hearts.
  - The shader multiplies its painted albedo by the vertex colour (`@if(VERTEX_COLORS)`).
  - The composition pass (§3.6.7) adds, with no new uniforms:
    - painted scree around every footing, which replaces the rubble meshes;
    - a cooler dusk away from the roads and clearings;
    - a lower fissure glow on maps (`accent.w` 1.0);
    - cobble islands laid as `Paving` variant 3.
* **Lights.** Brazier flames are merged glow meshes (bloom). A pool of **16 `PointLight`s** is
  re-assigned every 0.25 s to the braziers nearest the camera focus. The key light's shadow cascade is
  capped at 60 u. Each POI heart adds an unsoftened key flame (power 1.8, range 14), so the
  objective is the brightest light on its screen (§3.6.8).
* **Grand monuments** are ordinary decor, just large. Their tall silhouettes stand above the fog layer.

### 7.3 Fog of war (`fog.rs`, new, phase 3)

* `FogOfWar { cell: 2 u, w, h, alpha: Vec<u8>, image: Handle<Image> (R8), dirty }` resets on a map load.
  Rooms are fully revealed.
* **Reveal.** Each snapshot, for every `PlayerView` that moved ≥ 1 u, stamp a disc of `fog.reveal`
  (32 u, larger than the screen's half-diagonal) with a `feather` edge, max-blended. Lit Watchfires
  stamp 80 u. Party-shared, zero bandwidth.
* **Join in progress.** `SnapshotPacket.fog` (host `Expedition.explored`, RLE) seeds the grid.
* **Look.** One **mist plane** at y = 3.5 over the whole map, with a small `FogMaterial` (`fog.wesl`):
  alpha = (1 − explored) × 0.85 and drifting ink-wash noise. Unexplored ground is hidden, and grand
  monuments poke through as silhouettes.
* The texture uploads at most at 10 Hz (29 KB for Cinder), only when dirty.

### 7.4 Minimap, full map and markers (phase 3)

* **Minimap** (`minimap.rs`, new):
  - Top right, 256 × 161 px, gold frame. Shows a 120 × 80 u window around me: a CPU raster of the map
    at 1 px per 2 u (region `map_color`, gold roads, near-black void, biome liquid colour, dark walls,
    monument dots), composited with fog at ≤ 5 Hz and cropped with `Overflow::clip`.
  - Icons are absolutely positioned nodes: players (colour and facing wedge), revealed POIs (kind
    icon, pulsing when Active, dim when Done, gold progress ring), the **gate always** (sealed grey /
    open gold, Seal count), pings and downed allies. Off-window icons pin to the rim.
* **Full map**: `M`, pad Select, or a touch button. A 70 % overlay with region names (revealed only), a
  legend, the Seal tracker and player markers. RMB or A sends `MapPing`. The game does not pause.
* **Off-screen markers** (`offscreen.rs`): the pool grows from 10 to 16. Priority:
  1. downed allies
  2. the open gate
  3. POIs where an ally is present ("P2 · Anvil 45 %")
  4. allies
  5. pings
  6. the 3 nearest revealed, incomplete POIs within 120 u
  7. a surge edge flash

### 7.5 POI visuals, HUD and panels (phase 3)

* **`poi_visuals.rs`**: one silhouette per kind.
  - Anvil: today's `spawn_anvil`. Shrine: a god-coloured obelisk and banners. Reliquary: a gilded
    chest (the `Chest` look). Vein: a cyan crystal cluster. Lair: skull stakes and a red ring. Warlord:
    a great rune circle. Spring: a basin with a glowing disc. Watchfire: a pyre, lit when Done. Gate:
    an arch with Seal sockets and a portal.
  - A **beacon shaft** (additive cylinder, 30 u tall) in the kind colour (the god's colour for
    shrines) marks sighted POIs, dimmed when Done.
  - Hold progress reuses the anvil ring fill.
* **HUD** (`hud.rs`):
  - The "room x/y" line becomes "CINDER WASTES · SEALS ◆◆◆◇◇◇ 3/6 · ☠ WARLORD · 07:32 · THREAT ▮▮▮▯▯".
  - Under the minimap: the nearest objectives with bearing and distance, active events with progress
    bars, and the gate state.
  - Banners: the region name on entering a region, "THE HORDE SURGES FROM THE EAST", "The Forge
    whispers…".
  - `prompt()` covers every POI, the gate and "Gathering… 6 s". The boss bar comes from
    `PrivateView.boss` or `RunView.boss`.
* **Panels** (`ui.rs`):
  - The door panel is used only in `Cleared`.
  - New `poi_panel`: a large touch "Interact: <POI name>" button.
  - New gate/regroup banner with each missing player's name and distance.
  - The boon panel shows "+N queued", and the forge panel reads `private.anvil`.
  - The end panel adds objectives, Seals and explored %.
* **Camera and VFX**:
  - `camera.look_ahead` 2.5 u in the move direction. Shake from `Explosion`/`Synergy` only within
    30 u of the focus.
  - The VFX tier counts effects within 40 u, and bursts outside the view + 8 u are skipped.
  - `EMERGING` enemies rise from the ground over `emerge_time`.

---

## 8. Bots (`bot.rs`, `nav.rs`)

### 8.1 Map knowledge and navigation

* **`MapCache`**: a process-wide `Mutex<Option<(key, Arc<RoomDef>, Arc<NavGrid>, Arc<TileNav>)>>`, so
  every bot in a process builds a map once.
* Bots are **omniscient about POIs**: they know the map from the seed and POI states from the
  always-relevant `Poi` entities. Fog is presentation only.
* **Fine grid.** `NavGrid` at 0.5 u over the whole map (864 × 544 for Cinder), rasterized by obstacle
  and pit AABB (~2 ms). `path()` is capped at 25,000 expansions.
* **Coarse nav.** `TileNav` runs A* on map tiles, 8-neighbour: Road 7, Plaza/Bridge 8, Ground 10,
  +20 × blocked fraction, and Void/Liquid impassable.
  - Paths are cached per goal and re-planned every 3 s or when the goal moves more than 8 u.
  - The bot steers with today's `route()` toward the farthest coarse waypoint within 24 u that has a
    clear fine line.
* Whiskers and line of fire use `arena.occluders` and the index instead of full scans.

### 8.2 Planner

Re-evaluated every 30 ticks or when a goal completes:

1. **Revive** a downed ally within 45 u.
2. **Gate** when it is Open or Gathering (interact inside the ring, then wait inside), or when
   `seals ≥ required ∧ warlord done`.
3. **Join** an Active POI within 60 u where an ally is present (Hold: stand at 0.55 × radius, today's
   anvil logic; Clear: fight).
4. **Leader choice.** Maximize `value / (8 + travel_secs)` over incomplete POIs:
   - Anvil: 10 + 4 per bag item (cap 26).
   - Warlord: 12 once an anvil is done or 4 min have passed (else 3), ×2 when `seals ≥ required − 2`.
   - Lair 8, Shrine 7, Reliquary 6, Vein 5.
   - Spring: 14 if HP < 50 %, else 0. Watchfire 2.
   - +6 for seal-bearing POIs while short.
   - `travel_secs` = coarse path length / move speed.
5. **Policies.**
   - `group` (default, and whenever a human is present): the lowest living slot leads (a human if
     there is one). Others stay within 15 u, regroup beyond 22 u outside combat, and help at the
     leader's POI.
   - `split` (`--bot-split`): slots 0 and 2 lead their pairs. Leader 2 halves the value of POIs
     within 60 u of leader 0.
6. **Watchdog.** A goal with no progress for 20 s is blacklisted for 30 s.

The mop-up rule stays for rooms and never fires on maps (`encounter_left` is 1.0).

### 8.3 Reporting

`RunReport` gains `stages: Vec<StageTiming { biome, seconds, seals, objectives, downs, peak_alive }>`,
`objectives: Vec<(u16 /*biome*/, PoiKind, f32 /*at s*/)>`, `bytes_per_client_p99` and `max_relevant`.
The `--bot-run` default cap goes from 40 to 75 minutes.

---

## 9. Performance budget

| Item | Budget | Mechanism |
|---|---|---|
| Host tick p99 | ≤ 2.5 ms release at 400 enemies with 4 split bots on Cinder (CI gate < 16.67 ms) | `ObstacleIndex`, census O(400 × 4), flow round robin |
| `Arena::resolve` | ~1,800 calls per tick at 1–4 candidates (a linear scan over ~2.5k obstacles would be ~9 M ops) | index |
| Flow fields | 1 Dijkstra over ~7.5k tiles every 4 ticks: ≤ 0.1 ms | `flow.rs` |
| Spatial grid | 31k cells cleared per tick: ~30 µs | unchanged |
| Worldgen | ≤ 60 ms release / ≤ 400 ms debug per peer | Builder index, per-region streams |
| Chunk build | ≤ 150 ms release under the fade (fallback ≤ 4 chunks per frame) | merged meshes |
| Client draws | ≤ 600 at 4P peak, environment ≤ 160 (≤ 20 visible chunks × 8) | merging + frustum culling |
| Lights | ≤ 16 point lights, shadows ≤ 60 u | pooled lights |
| Fog / minimap | 29 KB upload ≤ 10 Hz; raster composite ≤ 5 Hz | CPU |
| Bandwidth | §6.2 | interest + compaction |
| Min spec | GTX 950 ≥ 55 fps at 4P peak (the slice exit gate, unchanged) | — |

---

## 10. Phase plan and work packages

The rules for every phase:

* Each phase compiles and keeps `cargo fmt`, `cargo clippy --workspace --all-targets -D warnings` and
  `cargo test --workspace` green. Each ends with its §11 check.
* Lanes run in parallel. **Owned files** are edited only by their lane. A lane that needs a change in
  another lane's file asks that lane (or the lead) instead of editing it.
* **Serial steps** land first and freeze the shared types for the rest of the phase.
* `procgen.rs` belongs to the layout-grammar work. This plan touches it only in 1C (§3.4), and must
  keep room layouts identical.

### Phase 1: Scale foundations (no gameplay change) — done

| Lane | Owns | Work |
|---|---|---|
| **1A Collision** (its first commit is the `movement.rs` API; 1B and 1C rebase on it) | `gf_core/src/movement.rs`; `gf_sim/src/{projectiles.rs, weapons.rs, resources.rs}`; the `Arena` construction line in `gf_sim/src/run.rs` (`load_room`); `gf_client/src/net.rs`; the `Arena` line in `gf_content/src/validate.rs` | `ObstacleIndex`, `Arena::new/rect/blocks_shot/occluders/walkable`, pits, the empty-index fallback. `ArenaRes(Arc<Arena>)`. Shot blocking uses `blocks_shot`, AUTO occluders use `occluders`. `Prediction.arena: Arc<Arena>` (no per-tick clone). |
| **1B Bot scale** | `gf_sim/src/{nav.rs, bot.rs}` | AABB rasterization (+ pits) in `NavGrid::new`, the A* expansion cap, the process-wide `MapCache` (keyed like `RoomCache`), whiskers and occluders via `arena.occluders`. |
| **1C Content scaffold** | `gf_core/src/{poi.rs (new), lib.rs}`; `gf_content/src/{schema.rs, validate.rs (except 1A's line), lib.rs, worldgen/mod.rs (new, stub)}`; `procgen.rs` (§3.4 only); `tools/gf_tools/src/{main.rs, preview.rs}`; `gf_client/src/hud.rs` (the `RoomKind` arm only) | `PoiKind`/`PoiState`. The schema of §4.2 (`Expedition`, `ExpeditionDef`, `MapLayout`, `ExpeditionTuning` with defaults, `Decor::FallenWeapon`, `RoomDef::expedition/map`). Validation §4.4. Builder index, mask and `pub(crate)`. A `worldgen::generate` stub that returns a flat map (the Landing only). `preview-room` draws `MapLayout` (tiles, roads, POIs, camps), and `layout-stats --maps`. |

### Phase 2: The Cinder map, end to end (bots finish the slice on it) — done

**2.0 Serial, one agent, first.** It owns these files:

* `gf_net/src/protocol.rs` (v3 §6.1) and `gf_net/tests/session.rs`;
* `gf_sim/src/{components.rs, resources.rs, lib.rs, snapshot.rs}`;
* new stubs `gf_sim/src/{poi.rs, horde.rs, flow.rs}` registered in the schedule;
* `RoomDef::arena()` and its use in `run.rs` `load_room`, `net.rs`, `bot.rs` and `validate.rs`;
* `SimConfig/SimSettings.start_at` (`server.rs`, `resources.rs`);
* client compile fixes: `hud.rs` prompt, `ui.rs` forge panel, and `scene.rs` (`animate_anvils`
  per-entity status, a generic ring and pillar for `EntityKind::Poi`), plus `bot.rs` reading
  `private.anvil`.

`snapshot.rs` computes every new view field from components and resources in this step:
`PrivateView.anvil` (`Arsenal.charges_from`, anvil positions), `PrivateView.boss` (nearest awake
`Guard` boss-like), `boon_queue`, `hopeless` (`Life.hopeless`), `RunView.stage` (`Expedition`),
`layout_hash`, `EntityKind::Poi` views and the `CONTESTED`/`EMERGING` flags. Later lanes only fill
those components.

After 2.0 lands, `protocol.rs`, `components.rs`, `resources.rs`, `lib.rs` and `snapshot.rs` are frozen.

| Lane | Owns | Work |
|---|---|---|
| **2A Worldgen** | `gf_content/src/worldgen/{mod, tiles, regions, roads, barriers, pois, compose, camps, repair}.rs`; `gf_content/src/{schema.rs, validate.rs}` (any content-type follow-ups this phase); `tools/gf_tools/src/preview.rs` | The full pipeline §3.2–3.4. The golden hash test (one test, in `worldgen/mod.rs`). Preview images. |
| **2B Expedition loop** | `gf_sim/src/{poi.rs, run.rs, anvil.rs, boons.rs, players.rs}` | §5.1, §5.3, §5.4 and the gate. Per-anvil charges, the boon queue, pickup aging, spoils, reforge-to-ally, `start_at`. |
| **2C Horde** | `gf_sim/src/{horde.rs, flow.rs, director.rs, enemies.rs, server.rs}` | §5.5–5.6: clusters, threat, rectangle ring, camps, far cull, guard idle/leash/hunt in `enemy_ai` and `boss_ai`, flow steering, `ClusterTuning` in `retune_party`. |
| **2D Bots and rig** | `gf_sim/src/{bot.rs, nav.rs}`; `gf_game/src/main.rs`; `gf_sim/tests/headless.rs` | §8 (group policy), `TileNav`, `--start-at`, the 75 min default. Headless tests: the peers-rebuild test counts ≥ 2 rooms and ≥ 1 generated; `depth ≥ 2` keeps its meaning (objectives add depth). |
| **2E Content** | `assets/content/{rooms.ron, game.ron, biomes.ron}` | The `cinder_expedition` template and the `expedition` block. **Flip Cinder's sequence last**, once 2A–2D are green. |
| **2F Client world** | `gf_client/src/{world.rs (new), envkit.rs (new), terrain.rs, materials.rs, palette.rs, shaders/floor.wesl}`; `scene.rs` (`rebuild_room` branch and the decor match only) | §7.1–7.2: chunks, merged meshes, the env kit for the full `Decor` vocabulary, land, cliffs, liquid, bridges, abyss, per-chunk floor, pooled lights. |

### Composition pass (§3.6): after phase 2, before the phase 3 lanes

One agent at a time, in the steps of §3.6.12 (0 readout, A lay rules, B frame and dressing,
C pacing, D look, E EA rooms). Each step is its own commit.

**Owned files:**

* `gf_content/src/worldgen/{compose, tiles, mod}.rs`;
* `gf_content/src/{procgen, schema, validate}.rs`;
* `assets/content/rooms.ron` (the Cinder block);
* `tools/gf_tools/src/preview.rs`;
* `gf_client/src/{envkit, world}.rs` and `shaders/floor.wesl`.

It never edits the files the UI and model-integration workflows hold (§3.6.12). Phase 3 needs none
of these files except 3G's `rooms.ron` quota line, so 3G lands after step C. Phase 4's 4A takes
over `compose.rs` from the final state of the pass.

### Phase 3: Co-op on a big map and exploration UX (no protocol change)

| Lane | Owns | Work |
|---|---|---|
| **3A Escalation and objectives** | `gf_sim/src/{horde.rs, poi.rs, run.rs}` | Surges, frenzy, Unworthy, Watchfires (Touch), the stall hint, host `explored` bits. |
| **3B Co-op rules** | `gf_sim/src/{players.rs, damage.rs, enemies.rs, anvil.rs}` | Hopeless tether (sets `Life.hopeless`), Stride, `MapPing`, loot-share radius, Forge Aegis (push-out + hit drop). |
| **3C Netcode** | `gf_net/src/server.rs`; `gf_sim/src/server.rs`; `gf_net/tests/session.rs` | §6.3: interest, per-client history, LOD, event filter and compaction, fog RLE on full snapshots, bandwidth stats. |
| **3D Bots split** | `gf_sim/src/{bot.rs, nav.rs}`; `gf_game/src/main.rs` | The `split` policy, `--bot-split`, the watchdog, stage and objective reports. |
| **3E Fog and maps** | `gf_client/src/{fog.rs (new), minimap.rs (new), input.rs, lib.rs, materials.rs, shaders/fog.wesl (new)}` | §7.3, §7.4 minimap and full map, map ping input. |
| **3F HUD and POI visuals** | `gf_client/src/{poi_visuals.rs (new), scene.rs, hud.rs, ui.rs, offscreen.rs, vfx.rs, camera.rs}` | §7.4 markers, §7.5, the fade, emerge. |
| **3G Content** | `assets/content/{rooms.ron, game.ron}` | The Watchfire quota and co-op/escalation defaults. |

### Phase 4: AAA map pass and the EA biomes (content first)

**4.0 Serial.** The lead adds placeholder Expedition entries for Verdant, Spire and Unmaking at the end
of `rooms.ron`, so each biome lane edits one block.

| Lane | Owns | Work |
|---|---|---|
| **4A Composition rules** | `gf_content/src/worldgen/{compose, pois, roads, barriers}.rs` | POI set pieces (Warlord crucible arena, shrine court, reliquary vault, vein quarry), `FallenWeapon` monuments, pass arches, road braziers and banners, camp dressing, barrier tuning per biome. |
| **4B Set-piece rendering** | `gf_client/src/{envkit.rs, world.rs, palette.rs, vfx.rs}`; `shaders/*.wesl` | Detailed env-kit silhouettes, region ambient blend and name banners, ambient particles (embers, spores, stardust, chaos motes), liquid and bridge polish, glTF key lookup (`palette`, ARCHITECTURE §9). |
| **4C Verdant**, **4D Spire**, **4E Unmaking** | their own `rooms.ron` block + their own `sequence:` line in `biomes.ron` | Themes, quotas, threat curves and landmark picks. Each flips its biome when its §11 run is green. |
| **4F Pacing and economy** | `assets/content/game.ron`; `tools/gf_tools/src/audit.rs`; `docs/HUNDRED_HOUR_AUDIT.md` | Retune from `stages[]` telemetry. The audit's Ember estimate counts objectives per biome instead of `sequence.len()`. Regenerate the audit. |

### Phase 5: Hardening and cleanup

| Lane | Owns | Work |
|---|---|---|
| **5A Perf and WAN** | hotspots as found | A GTX 950 capture, `--stress 400 --bots 4 --bot-split`, and a 4P WAN soak on maps. Fix what the numbers show. |
| **5B Docs** | `docs/{ARCHITECTURE.md, VERTICAL_SLICE.md, CONTENT_PIPELINE.md}`, `README.md`, `docs/media/*` | Procgen maps, POIs, director v2, interest management. Re-capture media (the README "choose your next chamber" image goes). |
| **5C Legacy trim** | `run.rs`, `schema.rs`, `biomes.ron` | Delete `BiomeDef.min_anvils`. Keep the legacy door path only for QA `--room` and a test fixture (§12). |

---

## 11. How we'll know it works

Tests stay lean. The existing suite keeps passing (with the headless assertions adapted in 2D), plus
one worldgen golden-hash test. There are no test sweeps. Each phase is proven by looking and by one
bot run:

| Phase | Proof |
|---|---|
| 1 | `cargo run --release -- --stress 400 --bots 4`: p99 no worse than before (0.97 ms dev). `cargo run -p gf_tools -- preview-sheet shots/rooms_after.png --biome cinder_wastes` is identical to the pre-phase sheet. |
| 2 | `cargo run -p gf_tools -- preview-room cinder_expedition 7 shots/cinder_map_7.png --scale 2` reads as a place (roads, regions, compositions, coast, rivers and bridges, POIs, camps). `layout-stats --maps --seeds 8` shows 0 repairs and 0 relaxations. **`cargo run --release -- --bot-run --seed 7` ends in Victory**: the report shows the Cinder stage at 6–10 sim-min, seals ≥ 6, the warlord done, and p99 tick in budget. `cargo run --release -- --autoplay --bots 3 --screenshot shots/p2_map.png --shots 6 --shot-interval 20` shows the map rendering. |
| §3.6 | `layout-stats --maps --seeds 8` passes every composition gate of §3.6.2, with 0 repairs and 0 relaxed. Before/after previews of run maps 3, 7 and 11, and before/after screenshots at the same `--start-at` spots, show open, painted ground framed at the edges. `--bot-run --seed 7` ends in Victory with the Cinder stage at 6–10 sim-min. `--horde 300 --fps` is no slower. The EA rooms meet §3.6.10. |
| 3 | `cargo run --release -- --bot-run --bots 4 --bot-split --seed 7`: Victory. The WAN soak `--bot-run --bots 4 --rtt 100 --loss 0.02 --minutes 5` meets the §6.2 gates. Screenshots show fog, the minimap, beacons, the tracker and a surge banner. |
| 4 | `cargo run --release -- --bot-run --phase ea --seed 7`: Victory across 3 map biomes. One preview image and one in-game screenshot per biome. |
| 5 | `--autoplay --bots 3 --horde 400 --fps` holds ≥ 55 fps on the GTX 950. |

---

## 12. What stays, what goes

* **Stays:**
  - `DoorReward` as the reward vocabulary, `PlayerAction::ChooseDoor`, the door panel (`Cleared` only);
  - authored boss arenas;
  - legacy room templates and door sequences as QA (`--room key~seed`) and as a test fixture;
  - `procgen::generate`;
  - `RunPhase` unchanged, and `RunView.step/steps` (2 per map biome: map, boss).
* **Goes:**
  - `RunView.anvil` (phase 2; replaced by `PrivateView.anvil`);
  - `BiomeDef.min_anvils` (phase 5);
  - the "room x/y" HUD label on maps;
  - `Encounter.anvil_gated` and the straggler teleport on maps (they stay for rooms);
  - `run.budget_growth_per_room`, `rate_growth_per_room` and `hp_growth_per_room` matter only to
    legacy rooms (kept for QA).
* **Not doing:**
  - streamed or multi-room sims, a `QPos` change (maps ≤ 480 u), fast travel, the chaos-altar brand
    POIs (a V1 idea);
  - authored prop/landmark data tables. The env kit renders the `Decor` vocabulary, and art arrives
    through `palette` glTF keys.

---

## 13. Risks and sign-offs

1. **Run length (needs the user's sign-off).** The EA run grows from ~22 to ~33–40 min for humans.
   Levers: `seals_required`, `size`, Stride `mult`.
2. **Cross-platform worldgen determinism.** One stray trig or unsorted float breaks Windows/Linux
   agreement. Mitigations: the golden hash in CI on both OSes, the runtime `layout_hash` check, and
   review against §3.1.
3. **Composition at scale.** The room grammar was tuned for 90 × 60 u rooms. Stamped into region
   slots it repeated and crowded, which the user saw: pillars and walls everywhere. §3.6 answers
   with edge slots, no fill, a visual frame, painted detail and measured gates in `layout-stats`.
   Three risks remain:
   - **Pacing:** fewer blockers let the horde flow and shots fly, so the pacing check and retune
     ladder are part of the pass.
   - **Pinches:** a composition backed onto a barrier could pinch a corridor. The `slot_clear` band
     and the pass keep-outs prevent it, and the reachability BFS and 0-repairs gate prove it.
   - **Emptiness:** an over-cleared region could read as empty. The frame-mass and barren-screen
     rows of §3.6.2 catch it.
4. **Pathing.** A flow-field or bridge bug strands the horde. Far cull with refund keeps pressure up.
   Bots have the watchdog and the forced gate.
5. **Interest-management baselines** under loss could make entities pop. The WAN soak in phase 3 is
   the gate, and a relevance radius well beyond the screen (44 u against a ~30 u half-diagonal) hides
   pops.
6. **Client performance at min spec.** Merged meshes, per-chunk floors, the fog plane and shadows are
   all unmeasured on a GTX 950. Phase 5A measures, and the fallbacks are chunk streaming (§7.2) and a
   lower light count.
7. **Split-party balance.** Cluster scaling, Aegis, the hopeless tether and loot sharing may favour
   always splitting or always grouping. Tune with `group` versus `split` bot runs and human playtests.
8. **Parallel work on `procgen.rs`.** The layout-grammar session is still active. 1C's Builder change
   must be a separate, identity-preserving commit, checked with before/after previews.
