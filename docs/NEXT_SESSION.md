# Next session: handoff (continue locally in `D:\GODFORGE`)

## 0. Set up the machine (Windows)

```powershell
# Once: Rust (rustup-init.exe from rustup.rs) + Visual Studio Build Tools with "Desktop development with C++".
git clone https://github.com/flanks/GODFORGE D:\GODFORGE
cd D:\GODFORGE
git checkout claude/new-session-hzpewk
cargo run --release -- --bots 3          # first build compiles Bevy (~10-20 min), then you + 3 bot teammates
cargo test --workspace                   # 130+ tests, all green at handoff
```

`rust-toolchain.toml` pins Rust 1.96.0, so rustup installs it automatically. The engine is
**Bevy `=0.20.0-rc.1`, exactly**. Don't bump it: the user insisted on this version.

## 1. Where the project stands

Read `README.md` and `docs/ARCHITECTURE.md` first. In short:

* **Crates:**
  - `gf_core` (rules)
  - `gf_content` (data + validation + procgen)
  - `gf_net` (host-authoritative netcode)
  - `gf_engine` (only Bevy consumer)
  - `gf_sim` (60 Hz headless sim + bots)
  - `gf_client` (rendering/HUD/UI)
  - `gf_game` (`godforge` binary)
  - `tools/gf_tools` (`gf-content` CLI)
* **Playable vertical slice:**
  - 3 characters, 6 chassis, full Forge loop with UI, Cinder Wastes + boss.
  - EA content behind `--phase ea`.
  - 4-player co-op (solo = loopback host), bots, stress rig.
* **CLI flags:**
  - `--bots N`, `--host [port]`, `--join ip:port`
  - `--autoplay`, `--room <key>`
  - `--screenshot path --shots N --shot-interval S`
  - `--bot-run`, `--stress 400`
* **Verified at handoff:**
  - fmt and clippy `-D warnings` clean.
  - All tests pass.
  - EA solo run: victory in 21.8 min.
  - 4P WAN soak at 100 ms / 2 % loss / 20 Hz passes.
  - 400-enemy stress: p99 host tick 0.97 ms.

## 2. What the user asked for (open requests, in priority order)

1. **Hades II-quality look.** The master prompt (§12, §14) asks for "stylized NPR shading
   (toon-ramp + rim light), not realistic PBR", hand-painted environments, a gold/ichor VFX
   language, bold silhouettes and ornate UI. The current look is greybox primitives with ink
   outlines, bloom, shadows and a vignette.
2. **Bigger maps, NIMRODS-scale.** Open fields where the camera follows you and the horde pours in
   from off-screen. Current rooms are ~44×30 units; the target is ~80-104 × 54-68.
3. **Auto-generated maps so no run is the same.**

## 3. Work in progress (half-done, committed, compiles)

### 3a. Procedural arenas (requests 2 and 3)

Done:
* `crates/gf_content/src/procgen.rs`: `generate(template, seed)`, `resolve_room(db, template_id, seed)`,
  `room_seed(run_seed, serial)`, `is_generated_kind`. It is deterministic across machines: no trig,
  and coordinates are quantized to 1/8 unit. It generates colonnades, ruined walls, boulders,
  plinths, braziers, lava cracks and broken anvils, keeps the spawn/plaza/gates clear with
  ≥ 2.8-unit lanes, and grows the encounter (budget ×1.35, rate ×1.3, max_alive ×1.4). 4 unit tests pass.
* `SpawnZone::Around { min, max }` is in the schema and in `gf_sim::director::spawn_point`: a ring
  just off-screen around a random player.
* `RoomDef::placeholder()`.

To do (wire it in):
1. **Protocol:** add `room_seed: u32` to `gf_net::RunView`, bump `PROTOCOL_VERSION` to 2, and fill it
   in `gf_sim::snapshot::run_view`.
2. **Sim:** add a `RoomLayout(Arc<RoomDef>)` resource (with a Default placeholder) and `RunState.room_seed`.
   * `run::load_room(world, room_id, seed)` resolves via `procgen::resolve_room` and stores the layout.
   * `start_run` / `room_transition` pass `procgen::room_seed(settings.seed, serial)`. Use seed 0 for
     boss/mini-boss kinds and for the QA `--room` override.
   * Replace every `content.room(run.room)` with the layout. The known sites are
     `director.rs:91`, `players.rs:159` and `run.rs:288` (door spawn uses `exits`).
3. **Bots (`gf_sim/src/bot.rs:63` and `:224`):** cache the resolved `RoomDef` per `room_serial` in
   `BotBrain`. Don't regenerate every tick.
4. **Client:** add a `CurrentRoom { serial, def }` resource updated in `net::poll_link` when
   `room_serial` changes. Use it instead of `content.rooms.try_get(run.room)` in `camera.rs:103`,
   `hud.rs:509` (kind label), `net.rs:216` (prediction arena) and `scene.rs:255` (room build).
5. **Camera for big maps:** centre on the local player. Pull toward allies only when they're
   within ~12 units, since every client has its own screen. Add HUD off-screen arrows for allies,
   doors, the anvil and pings.
6. **Check pacing with bots:**
   * `godforge --bot-run --seed 7`: the slice should still finish (~6-9 min).
   * `godforge --bot-run --phase ea --seed 7`: EA runs should land in 20-35 min.
   * `--stress 400 --bots 4`: must stay under budget.
   * Retune the encounter multipliers in `procgen.rs` if pacing drifts.

### 3b. NPR materials (request 1)

Done: `crates/gf_client/src/shaders/toon.wesl` and `floor.wesl` are written but **not yet registered
or compiled**.
* `toon.wesl`: Bevy PBR lighting, posterized in log2 space (bands independent of exposure, hue
  kept), a coloured fresnel rim, brush-noise value variation and saturated cool shadows.
  Uniform struct `ToonParams { rim, shade, settings, ramp }` at binding 100.
* `floor.wesl`: world-space Voronoi flagstones, brush strokes, a bevel highlight, mortar grime, a
  gold mosaic ring and star at the arena centre, pulsing lava cracks and a rim vignette. It keeps
  lighting and shadows. `FloorParams { stone, mortar, accent, gold, shape }`.

To do:
1. Create `crates/gf_client/src/materials.rs`:
   * `type ToonMaterial = ExtendedMaterial<StandardMaterial, Toon>` (plus `FloorMaterial`, `AbyssMaterial`).
   * Each extension is `#[derive(Asset, AsBindGroup, Reflect, Clone)]` with `#[uniform(100)] params: XParams`,
     where `XParams` is `#[derive(ShaderType)]` and holds `Vec4` fields in the same order as the WESL struct.
   * `impl MaterialExtension { fn fragment_shader() -> ShaderRef { "embedded://gf_client/shaders/toon.wesl".into() } }`.
   * In the plugin: `embedded_asset!(app, "shaders/toon.wesl")` (the path is relative to `materials.rs`)
     and `MaterialPlugin::<ToonMaterial>::default()`.
2. Write `shaders/abyss.wesl`: an unlit animated lava sea below the arena, using
   `bevy_pbr::render::mesh_view_bindings::globals.time`. Put it at y≈-7, under a thick platform
   whose cliff sides use the toon rock material.
3. In `palette.rs`, add `enum Mat { Std(Handle<StandardMaterial>), Toon(Handle<ToonMaterial>) }`.
   * Matte/Metal/Smolder/Ghost plus new `Hero(slot)`, `Foe` and `Hot` looks become toon materials.
     Rim colours: player colour for heroes, warm red for foes, soft gold for props.
   * Glow/Decal/Additive/Ink stay `StandardMaterial`.
   * `scene.rs` `Kit::child` inserts the right `MeshMaterial3d<_>`.
   * The enemy tint system and player downed swap must query `MeshMaterial3d<ToonMaterial>`.
4. Floor: replace the textured `Plane3d` in `scene.rs::build_room` with `FloorMaterial`. Pass the
   biome palette, half extents, slab size ≈1.6, crack density (Cinder 1.0, others 0.4) and a
   mosaic radius of 6.
5. Run it and look at it: `godforge --autoplay --bots 3 --screenshot shots/a.png --shots 4`. Shader
   compile errors appear in the log at runtime (WESL), not at `cargo build`.

### 3c. Still to do after that (requests 1 and 2)

* **Environment dressing per generated room (visual only, derived from the layout + seed):**
  - Colonnades with capitals and architraves on the north rim.
  - Low balustrades east/west; the south rim open to the abyss with a glowing rune edge.
  - Banners in god colours, rubble, brazier flames with point lights.
  - Ambient embers rising from the abyss.
  - `ColorGrading` on the camera (warmer highlights, richer saturation).
* **Characters:**
  - Per-character silhouettes from primitives: Valdris bulky with pauldrons and a cannon,
    Selene slender with a floating storm orb, Kael cloaked with a bow.
  - Weapon mesh by chassis family.
  - Walk bob/lean, dash afterimages, fire recoil.
* **VFX:**
  - Projectile trails, muzzle flashes (budgeted).
  - Kill motes flying to the killer.
  - Layered explosions (flash, ring, sparks, smoke).
* **UI:**
  - Gold-framed gradient panels (`BackgroundGradient`, `BoxShadow`) and better bars and boon cards.
  - A classical display font (e.g. Cinzel, OFL) if you can download it. DejaVu is bundled now.
* **Docs:** update `docs/ARCHITECTURE.md` (procgen, materials) and re-capture `docs/media/*.jpg`.

## 4. Bevy 0.20 notes that cost time to find

* **Shaders are WESL.** Import syntax is `import bevy_pbr::render::{pbr_fragment::pbr_input_from_standard_material, pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing, alpha_discard}, forward_io::{VertexOutput, FragmentOutput}};`.
  Material uniforms bind as `@group(constants::MATERIAL_BIND_GROUP) @binding(100)`: `constants` is
  injected, no import needed. Conditionals are `@if(DEF)`.
* **Embedded shader path:** `embedded://gf_client/shaders/<file>.wesl` becomes module `gf_client::shaders::<file>`.
* **UI:**
  - `ui_widgets::{Button, Activate}` plus a global `On<Activate>` observer (`ui::Button` is deprecated).
  - `Node.border_radius`, `BorderColor::all`, `FontSize::Px`, `TextShadow`, `BackgroundGradient`.
  - `Node` has `display` for show/hide.
* **Fonts:** `TextFont.font` is a `FontSource`. Replacing `AssetId::<Font>::default()` swaps the
  default font (done in `gf_engine::client::install_fonts`).
* **Lights:** `DirectionalLight.shadow_maps_enabled` (not `shadows_enabled`), `bevy::light::{NotShadowCaster, CascadeShadowConfigBuilder}`.
* **Pick one aim abstraction.** Never branch weapon code per aim mode. Content is data (CSV →
  `gf-content import` → RON). No stats in code.

## 5. Rules of the road

* Commit messages end with the co-author/session lines used in `git log`. Keep `cargo fmt`,
  `cargo clippy --workspace --all-targets -- -D warnings` and `cargo test --workspace` green.
* After content edits run `cargo run -p gf_tools -- import` and then `validate --strict`.
* Anything replicated must stay deterministic: the host owns the simulation, and clients only render and predict.
