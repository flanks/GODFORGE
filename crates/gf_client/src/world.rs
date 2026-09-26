//! World rendering for rooms and biome maps (OPEN_WORLD.md §7.1–7.2).
//!
//! * [`build`] runs on every `room_serial` change. Rooms keep their platform (`terrain.rs`) and get
//!   their rim from [`RimStyle`]; biome maps get land, cliffs, banks, liquid and bridges from the
//!   map's tile mask. Both render their whole `Decor` list through the env kit (`envkit.rs`).
//! * Everything is merged per 32 u chunk and per material family (≤ 8 draws a chunk), so Bevy's
//!   per-mesh frustum culling is the only streaming a 432 × 272 u map needs.
//! * **Land.** The visible shore is a smooth field over a 1 u lattice: the tile land mask, filleted
//!   in its notches (smooth union) and dilated by 0.3–0.85 u of noise, so the lip always covers the
//!   walkable tiles and never cuts into them. Marching squares turns it into the floor; its contour
//!   hangs cliffs to the abyss (void) or a shallow bank into the liquid.
//! * **Floor paint.** One `FloorMaterial` per chunk carries the fissures, roads, inlays, paving and
//!   holes (channels, pools) that touch the chunk; the region tint rides on vertex colours.
//! * **Lights.** Braziers, great braziers, crucibles and lanterns register a [`Flame`]; a pool of
//!   [`LIGHT_POOL`] point lights follows the camera focus every 0.25 s and flickers.
//!
//! Presentation only: nothing here feeds the simulation.

use crate::ClientSet;
use crate::camera::{KEY_LIGHT_FROM, KeyLight, Shake, w3};
use crate::envkit::{self, CHUNK, Colors, Ctx, Env, Flame, Key, MeshBuf, Paint, h01, lin};
use crate::materials::{
    ABYSS_Y, Abyss, AbyssMaterial, BiomeLook, FLOOR_CRACKS, FLOOR_FOOTINGS, FLOOR_HOLES, FLOOR_INLAYS, FLOOR_PATHS,
    FLOOR_PAVING, Floor, FloorMaterial, FloorParams, ToonMaterial, ToonStyle, toon, toon_from_standard,
};
use crate::palette::{Palette, hdr, hex, lighten, mix};
use crate::scene::RoomGeometry;
use crate::terrain;
use gf_content::schema::{Decor, MapLayout, SceneryKind, TileKind};
use gf_content::{ContentDb, RoomDef};
use gf_core::movement::Obstacle;
use gf_core::poi::PoiKind;
use gf_engine::client::{Face, NotShadowCaster, NotShadowReceiver};
use gf_engine::prelude::*;
use std::collections::{BTreeMap, HashMap};

/// Point lights shared by every brazier on the map (re-assigned to the nearest ones).
pub const LIGHT_POOL: usize = 16;
/// Lattice step of the land field (world units).
const LAT: f32 = 1.0;
/// Cliff profile below a void shore: (depth below the floor, outward offset, per-vertex jitter).
const CLIFF: [(f32, f32, f32); 6] =
    [(0.0, 0.0, 0.0), (0.26, 0.14, 0.0), (0.6, -0.08, 0.06), (2.4, -0.05, 0.35), (5.5, -0.35, 0.55), (10.5, -0.9, 0.8)];
/// Bank profile into a liquid: down to below the liquid surface.
const BANK: [(f32, f32, f32); 3] = [(0.0, 0.0, 0.0), (0.2, 0.16, 0.0), (0.75, 0.5, 0.12)];
/// Height of liquid surfaces (rivers, channels) below the floor.
pub const LIQUID_Y: f32 = -0.45;
/// World units per cliff texture tile.
const ROCK_TILE: f32 = 4.5;

pub fn build_plugin(app: &mut App) {
    app.init_resource::<EnvLights>()
        .add_systems(Startup, spawn_light_pool)
        .add_systems(Update, (tighten_key_shadows, pool_lights).in_set(ClientSet::Presentation));
}

/// The fixed iso camera sees ground 50–70 u deep and monuments a little nearer, so the key
/// light's single cascade spans 20–80 u (60 u) instead of 130: sharper shadows for free.
fn tighten_key_shadows(
    mut q: Query<&mut gf_engine::bevy::light::CascadeShadowConfig, (With<KeyLight>, Added<DirectionalLight>)>,
) {
    for mut c in &mut q {
        *c = gf_engine::bevy::light::CascadeShadowConfigBuilder {
            num_cascades: 1,
            minimum_distance: 20.0,
            maximum_distance: 80.0,
            first_cascade_far_bound: 80.0,
            ..default()
        }
        .build();
    }
}

/// A 32 u render chunk of the world (one entity per material family; `cx`, `cy` count from the
/// map's north-west corner).
#[derive(Component, Clone, Copy, Debug)]
pub struct ChunkRoot {
    pub cx: u32,
    pub cy: u32,
}

/// The environment's light sources and the pooled point lights that follow the camera.
#[derive(Resource, Default)]
pub struct EnvLights {
    pub flames: Vec<Flame>,
    /// Brazier luminous power (lumens) for this biome.
    pub lumens: f32,
    pool: Vec<Entity>,
    assigned: Vec<usize>,
    timer: f32,
}

#[derive(Component)]
struct PooledLight(usize);

fn spawn_light_pool(mut commands: Commands, mut lights: ResMut<EnvLights>) {
    for i in 0..LIGHT_POOL {
        let e = commands
            .spawn((
                PooledLight(i),
                PointLight { intensity: 0.0, range: 10.0, shadow_maps_enabled: false, ..default() },
                Transform::default(),
                Visibility::Hidden,
            ))
            .id();
        lights.pool.push(e);
    }
}

fn pool_lights(
    time: Res<Time>,
    shake: Res<Shake>,
    mut lights: ResMut<EnvLights>,
    mut q: Query<(&PooledLight, &mut PointLight, &mut Transform, &mut Visibility)>,
) {
    let dt = time.delta_secs();
    lights.timer -= dt;
    if lights.timer <= 0.0 {
        lights.timer = 0.25;
        let focus = w3(shake.focus, 0.0);
        let mut order: Vec<(f32, usize)> = lights
            .flames
            .iter()
            .enumerate()
            .map(|(i, f)| ((f.at - focus).length_squared() / f.power.max(0.1), i))
            .collect();
        order.sort_by(|a, b| a.0.total_cmp(&b.0));
        lights.assigned = order.iter().take(LIGHT_POOL).map(|o| o.1).collect();
    }
    let t = time.elapsed_secs();
    for (slot, mut light, mut tf, mut vis) in &mut q {
        match lights.assigned.get(slot.0).and_then(|&i| lights.flames.get(i)) {
            Some(f) => {
                let k = slot.0 as f32 * 1.7;
                let flicker = 0.86 + 0.08 * (t * 9.0 + k).sin() + 0.06 * (t * 23.0 + k * 3.1).sin();
                light.color = f.color;
                light.intensity = lights.lumens * f.power * flicker;
                light.range = f.range;
                tf.translation = f.at + Vec3::new(0.0, 0.05 * (t * 13.0 + k).sin(), 0.0);
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
}

/// Asset stores the world builder writes into.
pub struct WorldStores<'a> {
    pub meshes: &'a mut Assets<Mesh>,
    pub mats: &'a mut Assets<StandardMaterial>,
    pub toons: &'a mut Assets<ToonMaterial>,
    pub floors: &'a mut Assets<FloorMaterial>,
    pub abysses: &'a mut Assets<AbyssMaterial>,
}

/// Build the whole world of `room` (a legacy / generated room or a biome map).
#[allow(clippy::too_many_arguments)]
pub fn build(
    commands: &mut Commands,
    stores: WorldStores,
    pal: &Palette,
    db: &ContentDb,
    room: &RoomDef,
    look: &BiomeLook,
    seed: u32,
    lights: &mut EnvLights,
) {
    let started = std::time::Instant::now();
    // QA: GF_ENV_GALLERY=1 with a generated room (`--room cinder_foundry~5`) swaps its decor for
    // one of every env-kit piece and variant, laid out in rows (and drops its obstacles).
    let gallery_room;
    let room = if room.map.is_none() && std::env::var_os("GF_ENV_GALLERY").is_some() {
        gallery_room = RoomDef { decor: gallery(), obstacles: Vec::new(), ..room.clone() };
        &gallery_room
    } else {
        room
    };
    let colors = Colors::of(look);
    let gods: Vec<(Color, Color)> = db.gods.iter().map(|g| (hex(&g.color), hex(&g.color_secondary))).collect();
    let tops: Vec<(Vec2, Vec2, f32)> = room
        .decor
        .iter()
        .filter_map(|d| match *d {
            Decor::Wall { at, half, height, .. } => Some((at, half, height)),
            _ => None,
        })
        .collect();
    let half = room.half_extents;
    let origin = Vec2::new(-half.x - CHUNK, -half.y - CHUNK);
    let cols = ((half.x * 2.0 + CHUNK * 2.0) / CHUNK).ceil() as u32;
    let mut env = Env::new(origin, cols);
    let map = room.map.as_deref();
    let ctx = Ctx { colors: &colors, gods: &gods, tops: &tops, half, map };

    let mut floors: BTreeMap<u32, FloorBuf> = BTreeMap::new();
    match map {
        Some(map) => land(&mut env, &mut floors, map, room, &colors),
        None => {
            // The room platform, and its rim by style.
            terrain::build(
                commands,
                terrain::TerrainStores {
                    meshes: stores.meshes,
                    toons: stores.toons,
                    floors: stores.floors,
                    abysses: stores.abysses,
                },
                pal,
                db,
                room,
                look,
                seed,
            );
            envkit::rim(&mut env, &colors, half, &room.rim, &room.exits);
        }
    }
    let t_land = started.elapsed().as_secs_f64() * 1000.0;
    if std::env::var_os("GF_ENV_STATS").is_some() {
        // Per-variant vertex cost (tuning aid).
        let mut stats: BTreeMap<String, (usize, usize)> = BTreeMap::new();
        for d in &room.decor {
            let before = env.total_verts();
            envkit::decor(&mut env, &ctx, d);
            let name = format!("{d:?}");
            let name = name.split([' ', '(', '{']).next().unwrap_or("").to_string();
            let e = stats.entry(name).or_default();
            e.0 += 1;
            e.1 += env.total_verts() - before;
        }
        let mut top: Vec<_> = stats.into_iter().collect();
        top.sort_by_key(|(_, (_, v))| std::cmp::Reverse(*v));
        for (name, (n, v)) in top.iter().take(16) {
            info!("world: decor {name}: {n} × {} verts = {v}", v / n.max(&1));
        }
    } else {
        for d in &room.decor {
            envkit::decor(&mut env, &ctx, d);
        }
    }
    let t_decor = started.elapsed().as_secs_f64() * 1000.0;
    greybox(&mut env, &ctx, room);

    // Materials, one per family.
    let rock = stores.toons.add(toon(
        Color::WHITE,
        Some(pal.rock_texture.clone()),
        LinearRgba::BLACK,
        &ToonStyle::rock(look.cliff_heat().0, look.cliff_heat().1),
    ));
    let stone =
        stores.toons.add(toon(Color::WHITE, Some(pal.env_texture.clone()), LinearRgba::BLACK, &ToonStyle::prop()));
    let metal = stores.toons.add(toon_from_standard(
        StandardMaterial {
            base_color: Color::WHITE,
            base_color_texture: Some(pal.env_texture.clone()),
            perceptual_roughness: 0.38,
            metallic: 0.55,
            ..default()
        },
        &ToonStyle::metal(),
    ));
    let cloth = {
        let mut m =
            toon(Color::WHITE, None, LinearRgba::BLACK, &ToonStyle { ink: 0.0, ink_width: 0.0, ..ToonStyle::prop() });
        m.base.cull_mode = None;
        m.base.double_sided = true;
        stores.toons.add(m)
    };
    let glow = stores.mats.add(StandardMaterial {
        base_color: Color::WHITE,
        unlit: true,
        cull_mode: None,
        double_sided: true,
        fog_enabled: false,
        ..default()
    });
    let ink = stores.mats.add(StandardMaterial {
        base_color: hex("#140C08"),
        unlit: true,
        cull_mode: Some(Face::Front),
        fog_enabled: false,
        ..default()
    });
    let liquid = stores.abysses.add(AbyssMaterial {
        base: StandardMaterial { base_color: Color::WHITE, unlit: true, fog_enabled: false, ..default() },
        extension: Abyss { params: look.liquid_params((seed % 997) as f32) },
    });

    lights.flames = std::mem::take(&mut env.flames);
    soften_clusters(&mut lights.flames);
    if let Some(map) = map {
        // POI key lights (§3.6.8): each heart gets the brightest light on its screen, pushed after
        // the softening so its brazier ring never dims it.
        for poi in &map.pois {
            lights.flames.push(envkit::Flame { at: w3(poi.at, 2.0), color: colors.flame, power: 1.8, range: 14.0 });
        }
    }
    lights.lumens = look.brazier;
    lights.timer = 0.0;
    let verts: usize;
    let mut draws = 0;
    let (_, cols) = env.grid();
    {
        let bufs = env.into_buffers();
        verts = bufs.values().map(|b| b.pos.len()).sum::<usize>();
        for ((chunk, key), buf) in bufs {
            if buf.is_empty() {
                continue;
            }
            let mesh = stores.meshes.add(buf.into_mesh());
            let root = ChunkRoot { cx: chunk % cols, cy: chunk / cols };
            let mut e = commands.spawn((RoomGeometry, root, Mesh3d(mesh), Transform::default()));
            match key {
                Key::Stone => e.insert(MeshMaterial3d(stone.clone())),
                Key::Metal => e.insert(MeshMaterial3d(metal.clone())),
                Key::Rock => e.insert(MeshMaterial3d(rock.clone())),
                Key::Cloth => e.insert(MeshMaterial3d(cloth.clone())),
                Key::Glow => e.insert(MeshMaterial3d(glow.clone())),
                Key::Ink => e.insert(MeshMaterial3d(ink.clone())),
                Key::Liquid => e.insert((MeshMaterial3d(liquid.clone()), NotShadowReceiver)),
            };
            if !key.casts_shadow() {
                e.insert(NotShadowCaster);
            }
            draws += 1;
        }
    }

    // Map floors: one painted material per chunk.
    if let Some(map) = map {
        for (chunk, (buf, rect, heat)) in floors {
            if buf.is_empty() {
                continue;
            }
            let root = ChunkRoot { cx: chunk % cols, cy: chunk / cols };
            let params = map_floor_params(room, map, db, look, seed, rect);
            let mat = stores.floors.add(FloorMaterial {
                base: StandardMaterial {
                    base_color: Color::WHITE,
                    perceptual_roughness: 0.92,
                    reflectance: 0.18,
                    ..default()
                },
                extension: Floor { params },
            });
            // Second UV set: (liquid heat, glassy slag) per vertex, for the hot banks and the
            // slag sheets.
            let mesh = stores.meshes.add(buf.into_mesh().with_inserted_attribute(Mesh::ATTRIBUTE_UV_1, heat));
            commands.spawn((
                RoomGeometry,
                root,
                Mesh3d(mesh),
                MeshMaterial3d(mat),
                Transform::default(),
                NotShadowCaster,
            ));
            draws += 1;
        }
        // The abyss under the whole map.
        let reach = half + Vec2::splat(90.0);
        let plane = stores.meshes.add(Plane3d::new(Vec3::Y, reach));
        // Seen through bays and chasms, far below the rivers: dimmer than the surface liquid so
        // the hazards at floor level read first.
        let inner = (half - Vec2::splat(10.0)).max(Vec2::ONE);
        let mut params = look.abyss_params(inner, (seed % 997) as f32);
        // The bottom of the value ladder: the sea glows far below, dimmer than the ground.
        params.glow.w *= 0.3;
        params.mist.w *= 0.6;
        let abyss = stores.abysses.add(AbyssMaterial {
            base: StandardMaterial { base_color: Color::WHITE, unlit: true, fog_enabled: false, ..default() },
            extension: Abyss { params },
        });
        commands.spawn((
            RoomGeometry,
            Mesh3d(plane),
            MeshMaterial3d(abyss),
            Transform::from_xyz(0.0, ABYSS_Y, 0.0),
            NotShadowCaster,
            NotShadowReceiver,
        ));
    }

    info!(
        "world: {} ({}), {} decor, {} verts, {} draws, {} lights, built in {:.1} ms (land {t_land:.1}, decor {:.1})",
        room.key,
        if map.is_some() { "map" } else { "room" },
        room.decor.len(),
        verts,
        draws,
        lights.flames.len(),
        started.elapsed().as_secs_f64() * 1000.0,
        t_decor - t_land
    );
}

/// Braziers that stand in rings and rows (POI clearings, roads) would add up to a flood of
/// warm light; each flame's power drops with the flames around it, so a cluster reads as one
/// pool with a falloff and the dark between pools survives.
fn soften_clusters(flames: &mut [Flame]) {
    const NEAR: f32 = 11.0;
    let mut cells: HashMap<(i32, i32), Vec<usize>> = HashMap::new();
    let cell = |p: Vec3| ((p.x / NEAR).floor() as i32, (p.z / NEAR).floor() as i32);
    for (i, f) in flames.iter().enumerate() {
        cells.entry(cell(f.at)).or_default().push(i);
    }
    let weights: Vec<f32> = flames
        .iter()
        .enumerate()
        .map(|(i, f)| {
            let (cx, cz) = cell(f.at);
            let mut near = 0.0;
            for dx in -1..=1 {
                for dz in -1..=1 {
                    for &j in cells.get(&(cx + dx, cz + dz)).map_or(&[][..], |v| v.as_slice()) {
                        let d = flames[j].at.distance(f.at);
                        if j != i && d < NEAR {
                            near += flames[j].power.min(1.0) * (1.0 - d / NEAR);
                        }
                    }
                }
            }
            1.0 / (1.0 + 0.55 * near)
        })
        .collect();
    for (f, w) in flames.iter_mut().zip(weights) {
        f.power *= w;
    }
}

/// Obstacles no solid decor dresses keep a stone stand-in (authored rooms, repairs).
fn greybox(env: &mut Env, ctx: &Ctx, room: &RoomDef) {
    // Bucket the solid decor by 8 u cells so maps with thousands of pieces stay linear.
    const CELL: f32 = 8.0;
    let mut cells: HashMap<(i32, i32), Vec<usize>> = HashMap::new();
    let key = |p: Vec2| ((p.x / CELL).floor() as i32, (p.y / CELL).floor() as i32);
    for (i, d) in room.decor.iter().enumerate() {
        if !d.is_solid() {
            continue;
        }
        let (lo, hi) = decor_bounds(d);
        let (a, b) = (key(lo), key(hi));
        for x in a.0..=b.0 {
            for y in a.1..=b.1 {
                cells.entry((x, y)).or_default().push(i);
            }
        }
    }
    for o in &room.obstacles {
        let c = match *o {
            Obstacle::Circle { center, .. } | Obstacle::Box { center, .. } => center,
        };
        let dressed = cells.get(&key(c)).is_some_and(|l| l.iter().any(|&i| room.decor[i].covers(c)));
        if dressed {
            continue;
        }
        let stand_in = match *o {
            Obstacle::Circle { center, radius } => Decor::Pillar { at: center, radius, height: 2.6 },
            Obstacle::Box { center, half } => {
                Decor::Wall { at: center, half, height: 1.5, style: gf_content::schema::WallStyle::Ruin, variant: 0 }
            }
        };
        envkit::decor(env, ctx, &stand_in);
    }
}

/// Sim-plane bounds of a decor entry.
fn decor_bounds(d: &Decor) -> (Vec2, Vec2) {
    match *d {
        Decor::FallenColumn { from, to, radius }
        | Decor::FallenTree { from, to, radius }
        | Decor::Channel { from, to, width: radius } => {
            (from.min(to) - Vec2::splat(radius), from.max(to) + Vec2::splat(radius))
        }
        Decor::Arch { from, to, pier, .. } => (from.min(to) - Vec2::splat(pier), from.max(to) + Vec2::splat(pier)),
        Decor::Wall { at, half, .. } | Decor::SealedGate { at, half, .. } => (at - half, at + half),
        _ => {
            let a = d.anchor();
            (a - Vec2::splat(4.0), a + Vec2::splat(4.0))
        }
    }
}

/// Every env-kit piece and its variants in rows (north to south: walls; columns, arches and
/// set pieces; statues and heads; monuments and nature; fallen arms and props; clutter; floor
/// paint), for looking at the kit up close (`GF_ENV_GALLERY`).
fn gallery() -> Vec<Decor> {
    use gf_content::schema::{ClutterKind as C, WallStyle as W};
    let v = Vec2::new;
    let mut out = Vec::new();
    let mut row = |y: f32, step: f32, items: Vec<Box<dyn Fn(Vec2) -> Decor>>| {
        let x0 = -step * (items.len() as f32 - 1.0) * 0.5;
        for (i, f) in items.iter().enumerate() {
            out.push(f(v(x0 + i as f32 * step, y)));
        }
    };
    let wall = |style: W, half: Vec2, height: f32, variant: u8| -> Box<dyn Fn(Vec2) -> Decor> {
        Box::new(move |at| Decor::Wall { at, half, height, style, variant })
    };
    row(
        25.0,
        10.0,
        vec![
            wall(W::Ruin, v(3.5, 0.6), 3.0, 0),
            wall(W::Ruin, v(3.5, 0.6), 2.2, 1),
            wall(W::Parapet, v(3.5, 0.5), 1.4, 0),
            wall(W::Plinth, v(1.6, 1.6), 1.2, 0),
            wall(W::Hedge, v(3.5, 0.8), 2.2, 0),
            wall(W::Monolith, v(1.3, 0.8), 5.0, 0),
            wall(W::Forge, v(3.5, 0.8), 3.5, 0),
            wall(W::Forge, v(0.8, 3.0), 3.0, 1),
        ],
    );
    let arch = |variant: u8| -> Box<dyn Fn(Vec2) -> Decor> {
        Box::new(move |at| Decor::Arch {
            from: at - v(3.2, 0.0),
            to: at + v(3.2, 0.0),
            pier: 0.7,
            height: 4.5,
            variant,
        })
    };
    row(
        16.0,
        9.0,
        vec![
            Box::new(|at| Decor::Pillar { at, radius: 0.7, height: 4.5 }),
            Box::new(|at| Decor::Pillar { at, radius: 0.7, height: 2.0 }),
            arch(0),
            arch(1),
            arch(2),
            arch(3),
            Box::new(|at| Decor::SealedGate { at, half: v(3.4, 1.0), height: 5.0 }),
            Box::new(|at| Decor::SpiralStair { at, radius: 2.5, height: 6.0, rot: 3 }),
            Box::new(|at| Decor::InvertedColumn { at, radius: 0.8, height: 5.0 }),
        ],
    );
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = Vec::new();
    for k in 0..4u8 {
        items.push(Box::new(move |at| Decor::Statue { at, radius: 1.1, height: 3.6, rot: 12, god: k, variant: k }));
    }
    for k in 0..4u8 {
        items.push(Box::new(move |at| Decor::ColossusHead { at, radius: 2.6, rot: 12 + k, variant: k }));
    }
    row(7.0, 8.0, items);
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = vec![
        Box::new(|at| Decor::GreatAnvil { at, radius: 2.2, rot: 0 }),
        Box::new(|at| Decor::Crucible { at, radius: 2.7 }),
        Box::new(|at| Decor::GreatBrazier { at, radius: 1.8 }),
        Box::new(|at| Decor::Rift { at, radius: 2.0, height: 4.0, rot: 4 }),
    ];
    for k in 0..3u8 {
        items.push(Box::new(move |at| Decor::Boulder { at, radius: 1.5, variant: k }));
    }
    for k in 0..3u8 {
        items.push(Box::new(move |at| Decor::Crystal { at, radius: 1.0, height: 3.0, rot: 5 * k, variant: k }));
    }
    row(-2.0, 7.5, items);
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = Vec::new();
    for k in 0..5u8 {
        items.push(Box::new(move |at| Decor::FallenWeapon { at, radius: 1.4, height: 8.0, rot: 5 + k, variant: k }));
    }
    for k in 0..3u8 {
        items.push(Box::new(move |at| Decor::Tree { at, radius: 0.8, height: 5.0, variant: k }));
    }
    items.push(Box::new(|at| Decor::FallenTree { from: at - v(2.5, 0.8), to: at + v(2.5, 0.8), radius: 0.6 }));
    items.push(Box::new(|at| Decor::FallenColumn { from: at - v(2.5, -0.8), to: at + v(2.5, -0.8), radius: 0.7 }));
    row(-10.5, 7.5, items);
    let kinds = [
        C::Urns,
        C::Crates,
        C::WeaponRack,
        C::Ingots,
        C::Bones,
        C::Candles,
        C::Tomes,
        C::Mushrooms,
        C::Lanterns,
        C::Shards,
        C::Offerings,
    ];
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = kinds
        .iter()
        .map(|&kind| -> Box<dyn Fn(Vec2) -> Decor> {
            Box::new(move |at| Decor::Clutter { at, radius: 1.2, kind, count: 5, rot: 8 })
        })
        .collect();
    items.push(Box::new(|at| Decor::Brazier { at }));
    items.push(Box::new(|at| Decor::BrokenAnvil { at, scale: 1.2 }));
    items.push(Box::new(|at| Decor::Banner { at, height: 3.5, rot: 12, god: 1 }));
    row(-17.5, 5.2, items);
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = vec![
        Box::new(|at| Decor::Channel { from: at - v(0.0, 2.5), to: at + v(0.0, 2.5), width: 1.6 }),
        Box::new(|at| Decor::Pool { at, half: v(1.6, 1.2) }),
        Box::new(|at| Decor::Bridge { from: at - v(2.2, 0.0), to: at + v(2.2, 0.0), width: 2.4 }),
        Box::new(|at| Decor::Chains { from: at - v(2.0, 0.0), to: at + v(2.0, 0.0), height: 2.5 }),
        Box::new(|at| Decor::Roots { from: at - v(2.0, 1.0), to: at + v(2.0, 1.0), width: 0.8 }),
    ];
    for k in 0..3u8 {
        items.push(Box::new(move |at| Decor::Rubble { at, radius: 1.3, variant: k }));
        items.push(Box::new(move |at| Decor::Overgrowth { at, radius: 1.4, variant: k }));
        items.push(Box::new(move |at| Decor::Debris { at, radius: 1.0, height: 1.2, variant: k }));
    }
    row(-23.5, 5.4, items);
    // The map frame (Scenery): lip pieces, backdrop silhouettes, foreground humps.
    let mut items: Vec<Box<dyn Fn(Vec2) -> Decor>> = Vec::new();
    for k in 0..4u8 {
        items.push(Box::new(move |at| Decor::Scenery {
            at,
            radius: 1.3,
            height: 1.6,
            kind: gf_content::schema::SceneryKind::Lip,
            rot: 4 * k,
            variant: k,
        }));
    }
    for k in 0..4u8 {
        items.push(Box::new(move |at| Decor::Scenery {
            at,
            radius: 2.0,
            height: 9.0,
            kind: gf_content::schema::SceneryKind::Backdrop,
            rot: 3 * k,
            variant: k,
        }));
    }
    for k in 0..2u8 {
        items.push(Box::new(move |at| Decor::Scenery {
            at,
            radius: 2.0,
            height: 3.0,
            kind: gf_content::schema::SceneryKind::Foreground,
            rot: 5 * k,
            variant: k,
        }));
    }
    row(-30.0, 6.5, items);
    // The floor paint pieces sit along the east and west edges.
    for (k, y) in [-8.0f32, 0.0, 8.0, 16.0].into_iter().enumerate() {
        out.push(Decor::Paving { at: v(-37.0, y), half: v(2.5, 3.0), variant: k as u8 });
        out.push(Decor::FloorInlay { at: v(37.0, y), radius: 2.6, rot: 0, variant: k as u8 + 1, god: k as u8 });
    }
    out.push(Decor::LavaCrack { from: v(-38.0, -20.0), to: v(-34.0, -12.0), width: 0.5 });
    out
}

// ───────────────────────────── biome-map land ─────────────────────────────

/// What a tile shows: land (incl. bridges without a deck), void or liquid.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Ground {
    Land,
    Void,
    Liquid,
}

struct Field {
    /// Lattice origin (sim), size in lattice points.
    origin: Vec2,
    w: usize,
    h: usize,
    f: Vec<f32>,
}

impl Field {
    fn at(&self, i: usize, j: usize) -> f32 {
        self.f[j * self.w + i]
    }

    fn grad(&self, i: usize, j: usize) -> Vec2 {
        let (i0, i1) = (i.saturating_sub(1), (i + 1).min(self.w - 1));
        let (j0, j1) = (j.saturating_sub(1), (j + 1).min(self.h - 1));
        Vec2::new(
            (self.at(i1, j) - self.at(i0, j)) / ((i1 - i0).max(1) as f32),
            (self.at(i, j1) - self.at(i, j0)) / ((j1 - j0).max(1) as f32),
        )
    }

    fn point(&self, i: usize, j: usize) -> Vec2 {
        self.origin + Vec2::new(i as f32, j as f32) * LAT
    }
}

/// Smooth minimum (polynomial, `k` = blend width).
fn smin(a: f32, b: f32, k: f32) -> f32 {
    let h = (k - (a - b).abs()).max(0.0) / k;
    a.min(b) - h * h * k * 0.25
}

fn vnoise(p: Vec2, k: u32) -> f32 {
    let (x0, y0) = (p.x.floor(), p.y.floor());
    let (fx, fy) = (p.x - x0, p.y - y0);
    let s = |t: f32| t * t * (3.0 - 2.0 * t);
    let at = |x: f32, y: f32| h01((x as i32 as u32).wrapping_mul(0x632B_E5AB) ^ (y as i32 as u32), k);
    let a = at(x0, y0) + (at(x0 + 1.0, y0) - at(x0, y0)) * s(fx);
    let b = at(x0, y0 + 1.0) + (at(x0 + 1.0, y0 + 1.0) - at(x0, y0 + 1.0)) * s(fx);
    a + (b - a) * s(fy)
}

/// Classify every tile for rendering: a `Bridge` tile under a `Decor::Bridge` deck shows the pit
/// beneath (void or liquid, from its neighbours); an undecked one is drawn as land.
fn ground_mask(map: &MapLayout, room: &RoomDef) -> Vec<Ground> {
    let t = &map.tiles;
    let decks: Vec<(Vec2, Vec2, f32)> = room
        .decor
        .iter()
        .filter_map(|d| match *d {
            Decor::Bridge { from, to, width } => Some((from, to, width)),
            _ => None,
        })
        .collect();
    let covered = |p: Vec2| {
        decks.iter().any(|&(a, b, w)| {
            let ab = b - a;
            let s = ((p - a).dot(ab) / ab.length_squared().max(1e-4)).clamp(-0.1, 1.1);
            p.distance(a + ab * s) <= w * 0.5 + 0.5
        })
    };
    let mut out = vec![Ground::Land; t.kind.len()];
    for y in 0..t.h {
        for x in 0..t.w {
            let i = t.index(x, y);
            out[i] = match t.kind[i] {
                TileKind::Ground | TileKind::Road | TileKind::Plaza => Ground::Land,
                TileKind::Void => Ground::Void,
                TileKind::Liquid => Ground::Liquid,
                TileKind::Bridge if covered(t.center(x, y)) => {
                    // The pit under the deck: liquid if any neighbour is liquid.
                    let mut liquid = false;
                    for (dx, dy) in [(-1i32, 0i32), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2)] {
                        let (nx, ny) = (x as i32 + dx, y as i32 + dy);
                        if nx >= 0 && ny >= 0 && (nx as u16) < t.w && (ny as u16) < t.h {
                            liquid |= t.kind[t.index(nx as u16, ny as u16)] == TileKind::Liquid;
                        }
                    }
                    if liquid { Ground::Liquid } else { Ground::Void }
                }
                TileKind::Bridge => Ground::Land,
            };
        }
    }
    out
}

/// The visible-land field on a 1 u lattice (negative on land).
fn land_field(map: &MapLayout, mask: &[Ground]) -> Field {
    let t = &map.tiles;
    let per = (t.size / LAT).round() as usize;
    let (w, h) = (t.w as usize * per + 1, t.h as usize * per + 1);
    let mut f = vec![8.0f32; w * h];
    let land = |x: i32, y: i32| {
        x >= 0 && y >= 0 && (x as u16) < t.w && (y as u16) < t.h && mask[t.index(x as u16, y as u16)] == Ground::Land
    };
    for j in 0..h {
        for i in 0..w {
            let p = t.origin + Vec2::new(i as f32, j as f32) * LAT;
            // Tiles around the point (it may sit on a tile corner).
            let (tx, ty) = (((i as f32 * LAT) / t.size).floor() as i32, ((j as f32 * LAT) / t.size).floor() as i32);
            let (mut any_land, mut any_pit) = (false, false);
            for dy in -1..=1 {
                for dx in -1..=1 {
                    if land(tx + dx, ty + dy) {
                        any_land = true;
                    } else {
                        any_pit = true;
                    }
                }
            }
            if !any_land {
                continue;
            }
            if !any_pit {
                f[j * w + i] = -4.0;
                continue;
            }
            let mut d = 8.0f32;
            for dy in -2..=2 {
                for dx in -2..=2 {
                    let (x, y) = (tx + dx, ty + dy);
                    if !land(x, y) {
                        continue;
                    }
                    let c = t.center(x as u16, y as u16);
                    let q = (p - c).abs() - Vec2::splat(t.size * 0.5);
                    let sd = q.max(Vec2::ZERO).length() + q.x.max(q.y).min(0.0);
                    d = smin(d, sd, 2.6);
                }
            }
            // Outward only: the lip meanders 0.35–1.5 u past the walkable tiles, at two scales.
            let r = 0.35 + 0.75 * vnoise(p / 6.0, 0x5EA) + 0.4 * vnoise(p / 2.2, 0x5EB);
            f[j * w + i] = d - r;
        }
    }
    Field { origin: t.origin, w, h, f }
}

/// Linear value of the neutral region tint (`#808080`): a tint is a multiplier relative to it.
const TINT_NEUTRAL: f32 = 0.2158;

/// Region look per tile: the tint as a vertex-colour multiplier (`#808080` = 1: hue *and* value,
/// so black slag and pale ash read apart) and the theme's ground recipe (paving offset, ash,
/// glassy slag).
fn tile_looks(map: &MapLayout, room: &RoomDef) -> Vec<(Vec3, Vec3)> {
    let themes = room.expedition.as_ref().map(|x| &x.themes);
    let looks: Vec<(Vec3, Vec3)> = map
        .regions
        .iter()
        .map(|r| {
            let theme = themes.and_then(|t| t.get(r.theme as usize));
            let l = hex(theme.map_or("#808080", |t| t.tint.as_str())).to_linear();
            let v = Vec3::new(l.red, l.green, l.blue) / TINT_NEUTRAL;
            let recipe = theme.map_or(Vec3::ZERO, |t| Vec3::new(t.ground.paving, t.ground.ash, t.ground.glass));
            (v.clamp(Vec3::splat(0.3), Vec3::splat(1.6)), recipe)
        })
        .collect();
    map.tiles.region.iter().map(|&r| looks.get(r as usize).copied().unwrap_or((Vec3::ONE, Vec3::ZERO))).collect()
}

/// One map chunk's floor: its mesh, its sim rect and each vertex's liquid heat (second UV set).
type FloorBuf = (MeshBuf, Rect, Vec<[f32; 2]>);

fn land(env: &mut Env, floors: &mut BTreeMap<u32, FloorBuf>, map: &MapLayout, room: &RoomDef, c: &Colors) {
    let t0 = std::time::Instant::now();
    let mask = ground_mask(map, room);
    let field = land_field(map, &mask);
    let looks = tile_looks(map, room);
    let t = &map.tiles;
    // Seams along open region borders: the ground under their courses sinks into a darker band
    // of scree (vertex alpha, like the cliffs' lip; the floor shader drifts pebbles there).
    const SEAM_CELL: f32 = 8.0;
    let mut seam_cells: HashMap<(i32, i32), Vec<(Vec2, f32)>> = HashMap::new();
    for d in &room.decor {
        if let Decor::Scenery { at, radius, kind: SceneryKind::Seam, .. } = *d {
            let key = ((at.x / SEAM_CELL).floor() as i32, (at.y / SEAM_CELL).floor() as i32);
            seam_cells.entry(key).or_default().push((at, radius));
        }
    }
    let seam_band = |p: Vec2| -> f32 {
        let (cx, cy) = ((p.x / SEAM_CELL).floor() as i32, (p.y / SEAM_CELL).floor() as i32);
        let mut d = f32::MAX;
        for dy in -1..=1 {
            for dx in -1..=1 {
                for &(at, r) in seam_cells.get(&(cx + dx, cy + dy)).map_or(&[][..], |v| v.as_slice()) {
                    d = d.min(p.distance(at) - r * 0.8);
                }
            }
        }
        let k = ((d - 0.3) / 2.6).clamp(0.0, 1.0);
        0.42 + 0.58 * k * k * (3.0 - 2.0 * k)
    };
    // Bilinear over tile centres: (vertex colour, ground recipe: paving and ash as the first UV
    // set, glass as the second set's y).
    let look_at = |p: Vec2| -> ([f32; 4], Vec3) {
        let q = (p - t.origin) / t.size - Vec2::splat(0.5);
        let (x0, y0) = (q.x.floor(), q.y.floor());
        let (fx, fy) = (q.x - x0, q.y - y0);
        let at = |x: f32, y: f32| {
            let (x, y) = ((x as i32).clamp(0, t.w as i32 - 1), (y as i32).clamp(0, t.h as i32 - 1));
            looks[t.index(x as u16, y as u16)]
        };
        let lerp = |a: (Vec3, Vec3), b: (Vec3, Vec3), k: f32| (a.0.lerp(b.0, k), a.1.lerp(b.1, k));
        let a = lerp(at(x0, y0), at(x0 + 1.0, y0), fx);
        let b = lerp(at(x0, y0 + 1.0), at(x0 + 1.0, y0 + 1.0), fx);
        let (v, r) = lerp(a, b, fy);
        ([v.x, v.y, v.z, 1.0], r)
    };
    let pit_at = |p: Vec2| -> Ground {
        match t.tile_of(p) {
            Some((x, y)) => mask[t.index(x, y)],
            None => Ground::Void,
        }
    };
    // Liquid heat at a point: 1 on a liquid's edge, fading to 0 three units inland (the floor
    // beside a molten river glows with it instead of darkening toward the bank).
    let heat_at = |p: Vec2| -> f32 {
        let q = (p - t.origin) / t.size;
        let (tx, ty) = (q.x.floor() as i32, q.y.floor() as i32);
        let mut d = f32::MAX;
        for dy in -1..=1 {
            for dx in -1..=1 {
                let (x, y) = (tx + dx, ty + dy);
                if x < 0 || y < 0 || x >= t.w as i32 || y >= t.h as i32 {
                    continue;
                }
                if mask[t.index(x as u16, y as u16)] != Ground::Liquid {
                    continue;
                }
                let c = t.center(x as u16, y as u16);
                let e = ((p - c).abs() - Vec2::splat(t.size * 0.5)).max(Vec2::ZERO);
                d = d.min(e.length());
            }
        }
        let k = (1.0 - d / 3.0).clamp(0.0, 1.0);
        k * k * (3.0 - 2.0 * k)
    };

    let t_field = t0.elapsed().as_secs_f64() * 1000.0;
    // ── floor (marching squares) and shore contour ──
    // Dense vertex dedup: (chunk, vertex) per lattice corner and per crossed lattice edge. A
    // vertex shared across a chunk border is simply emitted once per chunk.
    let (fw, fh) = (field.w, field.h);
    let mut seen: Vec<(u32, u32)> = vec![(u32::MAX, 0); fw * fh * 3];
    let slot = |key: u64| -> usize {
        let tag = key >> 62;
        let j = ((key >> 32) & 0x3FFF_FFFF) as usize;
        let i = ((key >> 1) & 0x7FFF_FFFF) as usize;
        match tag {
            2 => j * fw + i,
            _ if key & 1 == 1 => fw * fh + j * fw + i,
            _ => 2 * fw * fh + j * fw + i,
        }
    };
    // Contour points: key → (position, outward direction).
    let edge_point = |i: usize, j: usize, horizontal: bool| -> (Vec2, Vec2, u64) {
        let (i1, j1) = if horizontal { (i + 1, j) } else { (i, j + 1) };
        let (a, b) = (field.at(i, j), field.at(i1, j1));
        let s = (a / (a - b)).clamp(0.0, 1.0);
        let p = field.point(i, j).lerp(field.point(i1, j1), s);
        let g = field.grad(i, j).lerp(field.grad(i1, j1), s).normalize_or(Vec2::Y);
        let key = ((j as u64) << 32) | ((i as u64) << 1) | u64::from(horizontal);
        (p, g, key)
    };
    let mut cliffs: Vec<(Vec2, Vec2, u64, Vec2, Vec2, u64)> = Vec::new();
    let (_, cols) = env.grid();
    let mut chunk_bufs: Vec<Option<FloorBuf>> = Vec::new();
    let corner_key = |ci: usize, cj: usize| (2u64 << 62) | ((cj as u64) << 32) | ((ci as u64) << 1);
    for j in 0..field.h - 1 {
        let mut run_chunk = u32::MAX;
        let mut run_end = 0usize;
        for i in 0..field.w - 1 {
            let f = [field.at(i, j), field.at(i + 1, j), field.at(i + 1, j + 1), field.at(i, j + 1)];
            let inside = [f[0] < 0.0, f[1] < 0.0, f[2] < 0.0, f[3] < 0.0];
            if !(inside[0] || inside[1] || inside[2] || inside[3]) {
                continue;
            }
            if i >= run_end || run_chunk == u32::MAX {
                let centre = field.point(i, j) + Vec2::splat(LAT * 0.5);
                run_chunk = env.chunk_of(centre.x, -centre.y);
                // The chunk's column ends at the next multiple of CHUNK in x.
                let (origin, _) = env.grid();
                let cx = run_chunk % cols;
                let x_end = origin.x + (cx + 1) as f32 * CHUNK;
                run_end = (((x_end - field.origin.x) / LAT).ceil() as usize).max(i + 1);
                if chunk_bufs.len() <= run_chunk as usize {
                    chunk_bufs.resize_with(run_chunk as usize + 1, || None);
                }
            }
            let chunk = run_chunk;
            let entry = chunk_bufs[chunk as usize].get_or_insert_with(|| {
                let x0 = env_chunk_min(env, chunk);
                (MeshBuf::default(), Rect::from_corners(x0, x0 + Vec2::splat(CHUNK)), Vec::new())
            });
            let (buf, _, heat) = entry;
            // Polygon around the cell, counter-clockwise (sim): corner, crossing, corner, …
            let corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)];
            let mut poly = [(Vec2::ZERO, 0u64, Vec2::ZERO, false, 0.0f32); 8];
            let mut n = 0;
            for k in 0..4 {
                let (ci, cj) = corners[k];
                if inside[k] {
                    poly[n] = (field.point(ci, cj), corner_key(ci, cj), Vec2::ZERO, false, field.at(ci, cj));
                    n += 1;
                }
                let next = (k + 1) % 4;
                if inside[k] != inside[next] {
                    let (p, g, key) = match k {
                        0 => edge_point(i, j, true),
                        1 => edge_point(i + 1, j, false),
                        2 => edge_point(i, j + 1, true),
                        _ => edge_point(i, j, false),
                    };
                    poly[n] = (p, key, g, true, 0.0);
                    n += 1;
                }
            }
            if n < 3 {
                continue;
            }
            let mut idx = [0u32; 8];
            for (k, (p, key, _, _, f)) in poly[..n].iter().enumerate() {
                let s = &mut seen[slot(*key)];
                if s.0 != chunk {
                    // Alpha carries how far inland the vertex is (0 on the shore, 1 from 3 u in):
                    // the floor darkens toward cliffs and banks.
                    let (mut col, recipe) = look_at(*p);
                    // Alpha: how far inland (0 on the shore, 1 from 3 u in), lower along a seam.
                    col[3] = (-f / 3.0).clamp(0.0, 1.0).min(seam_band(*p));
                    *s = (chunk, buf.vert(w3(*p, 0.0), Vec3::Y, [recipe.x, recipe.y], col));
                    heat.push([heat_at(*p), recipe.z]);
                }
                idx[k] = s.1;
            }
            for k in 1..n - 1 {
                buf.tri(idx[0], idx[k], idx[k + 1]);
            }
            // Contour segments: consecutive crossings (land on their left).
            for k in 0..n {
                let (a, b) = (poly[k], poly[(k + 1) % n]);
                if a.3 && b.3 {
                    cliffs.push((a.0, a.2, a.1, b.0, b.2, b.1));
                }
            }
        }
    }
    for (chunk, entry) in chunk_bufs.into_iter().enumerate() {
        if let Some(e) = entry {
            floors.insert(chunk as u32, e);
        }
    }

    let t_floor = t0.elapsed().as_secs_f64() * 1000.0;
    // ── cliffs and banks ──
    for (pa, ga, ka, pb, gb, kb) in cliffs {
        let mid = (pa + pb) * 0.5;
        let out = (ga + gb).normalize_or(Vec2::Y);
        env.at(mid);
        let liquid = pit_at(mid + out * 1.2) == Ground::Liquid;
        let profile: &[(f32, f32, f32)] = if liquid { &BANK } else { &CLIFF };
        let ring = |l: usize, p: Vec2, g: Vec2, key: u64| -> Vec3 {
            let (depth, off, jit) = profile[l];
            let j = (h01((key as u32) ^ (key >> 32) as u32, l as u32 * 7 + 3) - 0.5) * 2.0 * jit;
            let q = p + g * (off + j);
            Vec3::new(q.x, -depth, -q.y)
        };
        let color = if liquid { lin(mix(c.rock, c.dark, 0.35)) } else { lin(c.rock) };
        let buf = env.buf(Key::Rock);
        let u = |p: Vec2| (p.x - p.y) / ROCK_TILE;
        let outward = Vec3::new(out.x, 0.0, -out.y);
        for l in 0..profile.len() - 1 {
            let quad = [ring(l, pa, ga, ka), ring(l, pb, gb, kb), ring(l + 1, pb, gb, kb), ring(l + 1, pa, ga, ka)];
            let us = [u(pa), u(pb), u(pb), u(pa)];
            let mut n = (quad[1] - quad[0]).cross(quad[3] - quad[0]).normalize_or(outward);
            let flip = n.dot(outward) < 0.0;
            if flip {
                n = -n;
            }
            let base = buf.pos.len() as u32;
            for (v, uu) in quad.iter().zip(us) {
                buf.vert(*v, n, [uu, -v.y / ROCK_TILE], color);
            }
            if flip {
                buf.quad(base, base + 3, base + 2, base + 1);
            } else {
                buf.quad(base, base + 1, base + 2, base + 3);
            }
        }
        if !liquid {
            // Rim light: the heat of the abyss catches the lip, a thin glowing ribbon hanging just
            // past the edge, so every shore reads as a lit edge, not a straight cut into black.
            let heat = 0.55 + 0.45 * h01((ka as u32) ^ 0x51A, 0xED70);
            let glow = lin(hdr(c.molten, 0.16 * heat));
            let (oa, ob) = (Vec3::new(ga.x, 0.0, -ga.y), Vec3::new(gb.x, 0.0, -gb.y));
            let (a3, b3) = (Vec3::new(pa.x, -0.05, -pa.y), Vec3::new(pb.x, -0.05, -pb.y));
            let buf = env.buf(Key::Glow);
            let base = buf.pos.len() as u32;
            for v in [a3 + oa * 0.12, b3 + ob * 0.12, b3 + ob * 0.42, a3 + oa * 0.42] {
                buf.vert(v, Vec3::Y, [0.0, 0.0], glow);
            }
            buf.quad(base, base + 1, base + 2, base + 3);
            buf.quad(base, base + 3, base + 2, base + 1);
        }
        // Crumbling edges: loose stones on the lip, half over the drop; more of them on the north
        // shores, where the camera never sees a cliff face and the stones are the edge.
        let pick = h01((ka as u32) ^ (ka >> 32) as u32, 0xED6E);
        let north = out.y > 0.5;
        if !liquid && pick < if north { 0.5 } else { 0.22 } {
            let rr = if north { 0.3 + 0.5 * h01(ka as u32, 0xED6F) } else { 0.22 + 0.4 * h01(ka as u32, 0xED6F) };
            let at = mid - out * (rr * 0.4);
            env.rock(
                Vec3::new(at.x, rr * 0.15, -at.y),
                Quat::from_rotation_y(pick * 70.0),
                Vec3::new(rr, rr * 0.6, rr * 0.85),
                ka as u32,
                0.45,
                Paint::new(Key::Rock, mix(c.rock, c.dark, 0.2)).ink(0.032),
            );
        }
    }

    // ── liquid surfaces and falls ──
    let liquidish = |x: i32, y: i32| {
        x >= 0 && y >= 0 && (x as u16) < t.w && (y as u16) < t.h && mask[t.index(x as u16, y as u16)] == Ground::Liquid
    };
    // One quad per liquid tile, reaching under the banks (never out over the void).
    let voidish = |x: i32, y: i32| {
        x < 0 || y < 0 || x >= t.w as i32 || y >= t.h as i32 || mask[t.index(x as u16, y as u16)] == Ground::Void
    };
    for y in 0..t.h as i32 {
        for x in 0..t.w as i32 {
            if !liquidish(x, y) {
                continue;
            }
            let reach = |dx: i32, dy: i32| if voidish(x + dx, y + dy) { 0.0 } else { 0.8 };
            let lo = t.origin + Vec2::new(x as f32, y as f32) * t.size - Vec2::new(reach(-1, 0), reach(0, -1));
            let hi =
                t.origin + Vec2::new(x as f32 + 1.0, y as f32 + 1.0) * t.size + Vec2::new(reach(1, 0), reach(0, 1));
            env.at((lo + hi) * 0.5);
            let q = |x: f32, y: f32| Vec3::new(x, LIQUID_Y, -y);
            // Red channel: bank heat at each corner (1 where a land tile meets it), which the
            // liquid shader turns into a hot band along the banks.
            let bank = |cx: i32, cy: i32| {
                let land = [(cx - 1, cy - 1), (cx, cy - 1), (cx - 1, cy), (cx, cy)].iter().any(|&(tx, ty)| {
                    tx >= 0
                        && ty >= 0
                        && tx < t.w as i32
                        && ty < t.h as i32
                        && mask[t.index(tx as u16, ty as u16)] == Ground::Land
                });
                if land { [1.0, 1.0, 1.0, 1.0] } else { [0.0, 1.0, 1.0, 1.0] }
            };
            env.sheet(
                [q(lo.x, lo.y), q(hi.x, lo.y), q(hi.x, hi.y), q(lo.x, hi.y)],
                [bank(x, y), bank(x + 1, y), bank(x + 1, y + 1), bank(x, y + 1)],
                Key::Liquid,
            );
            // Rivers light their banks: a low molten light every few tiles (the pool picks the
            // ones near the camera).
            if h01((x as u32).wrapping_mul(0x9E37_79B9) ^ (y as u32), 0x71C3) < 0.3 {
                let c3 = t.center(x as u16, y as u16);
                env.flames.push(Flame {
                    at: Vec3::new(c3.x, LIQUID_Y + 0.9, -c3.y),
                    color: c.molten,
                    power: 0.45,
                    range: 7.5,
                });
            }
        }
    }
    for y in 0..t.h as i32 {
        for x in 0..t.w as i32 {
            if !liquidish(x, y) {
                continue;
            }
            let c = t.center(x as u16, y as u16);
            for (dx, dy) in [(1i32, 0i32), (-1, 0), (0, 1), (0, -1)] {
                let (nx, ny) = (x + dx, y + dy);
                let off_map = nx < 0 || ny < 0 || nx >= t.w as i32 || ny >= t.h as i32;
                if !off_map && mask[t.index(nx as u16, ny as u16)] != Ground::Void {
                    continue;
                }
                // A liquid fall pouring into the abyss.
                let d = Vec2::new(dx as f32, dy as f32);
                let side = Vec2::new(-d.y, d.x) * (t.size * 0.5);
                let edge = c + d * (t.size * 0.5);
                env.at(edge);
                let (a, b) = (edge - side, edge + side);
                let top = |p: Vec2| Vec3::new(p.x, LIQUID_Y, -p.y);
                let bot = |p: Vec2| Vec3::new(p.x + d.x * 0.8, ABYSS_Y - 0.5, -(p.y + d.y * 0.8));
                let (mut q0, mut q1) = (a, b);
                if (b - a).perp_dot(d) > 0.0 {
                    std::mem::swap(&mut q0, &mut q1);
                }
                env.sheet([top(q0), top(q1), bot(q1), bot(q0)], [[1.0; 4]; 4], Key::Liquid);
            }
        }
    }
    info!(
        "world: land {}×{}: field {t_field:.1} ms, floor {t_floor:.1} ms, total {:.1} ms",
        field.w,
        field.h,
        t0.elapsed().as_secs_f64() * 1000.0
    );
}

/// Sim-plane minimum corner (south-west) of a chunk.
fn env_chunk_min(env: &Env, chunk: u32) -> Vec2 {
    let (origin, cols) = env.grid();
    let (cx, cz) = (chunk % cols, chunk / cols);
    // World x/z of the chunk's min corner → sim (x, −z); the sim south edge is world z max.
    let wx = origin.x + cx as f32 * CHUNK;
    let wz_max = origin.y + (cz + 1) as f32 * CHUNK;
    Vec2::new(wx, -wz_max)
}

// ───────────────────────────── floor paint ─────────────────────────────

fn lin4(c: Color, a: f32) -> Vec4 {
    let l = c.to_linear();
    Vec4::new(l.red, l.green, l.blue, a)
}

/// Floor paint shared by rooms and map chunks: palette and lighting direction.
pub fn floor_base(look: &BiomeLook, seed: u32) -> FloorParams {
    let stone = look.stone();
    let dirt = look.dirt();
    let mortar = mix(look.deep, hex("#050308"), 0.35);
    let light = Vec2::new(KEY_LIGHT_FROM.x, KEY_LIGHT_FROM.z).normalize();
    FloorParams {
        stone: lin4(stone, 0.35),
        dirt: lin4(dirt, 0.52),
        mortar: lin4(mortar, 0.8),
        accent: lin4(look.accent, if look.cracks >= 1.0 { 3.0 } else { 1.0 }),
        gold: lin4(hex("#C9A24E"), 0.0),
        cool: lin4(mix(look.ambient, hex("#4A5CB0"), 0.5), 0.4),
        shape: Vec4::new(0.0, 0.0, 1.6, look.cracks),
        style: Vec4::new((seed % 1000) as f32, look.moss, look.veins, 0.0),
        misc: Vec4::new(0.0, light.x, light.y, 0.0),
        counts: Vec4::ZERO,
        paths: [Vec4::ZERO; FLOOR_PATHS],
        paths_w: [Vec4::ZERO; FLOOR_PATHS / 4],
        cracks: [Vec4::ZERO; FLOOR_CRACKS],
        cracks_w: [Vec4::ZERO; FLOOR_CRACKS / 4],
        inlays: [Vec4::ZERO; FLOOR_INLAYS],
        inlays_c: [Vec4::ZERO; FLOOR_INLAYS],
        paving: [Vec4::ZERO; FLOOR_PAVING],
        paving_v: [Vec4::ZERO; FLOOR_PAVING / 4],
        holes: [Vec4::ZERO; FLOOR_HOLES],
        footings: [Vec4::ZERO; FLOOR_FOOTINGS],
    }
}

fn set4(arr: &mut [Vec4], i: usize, v: f32) {
    arr[i / 4][i % 4] = v;
}

/// Add the decor painted into the floor (fissures, inlays, paving, channel and pool holes) that
/// touches `area` (sim rect; `None` = everything).
pub fn paint_decor(p: &mut FloorParams, db: &ContentDb, decor: &[Decor], area: Option<Rect>) {
    let touches = |lo: Vec2, hi: Vec2| {
        area.is_none_or(|a| lo.x <= a.max.x && hi.x >= a.min.x && lo.y <= a.max.y && hi.y >= a.min.y)
    };
    let (mut nc, mut ni, mut np, mut nh) =
        (p.misc.x as usize, p.counts.x as usize, p.counts.y as usize, p.counts.z as usize);
    for d in decor {
        match *d {
            Decor::LavaCrack { from, to, width } if nc < FLOOR_CRACKS => {
                let m = Vec2::splat(width + 4.0);
                if touches(from.min(to) - m, from.max(to) + m) {
                    let (a, b) = (w3(from, 0.0), w3(to, 0.0));
                    p.cracks[nc] = Vec4::new(a.x, a.z, b.x, b.z);
                    set4(&mut p.cracks_w, nc, width);
                    nc += 1;
                }
            }
            Decor::FloorInlay { at, radius, rot, variant, god } if ni < FLOOR_INLAYS => {
                if touches(at - Vec2::splat(radius * 1.3), at + Vec2::splat(radius * 1.3)) {
                    let a = w3(at, 0.0);
                    let angle = gf_content::schema::rot16_dir(rot);
                    let col = db.gods.try_get(god as u16).map_or(hex("#C9A24E"), |g| hex(&g.color));
                    p.inlays[ni] = Vec4::new(a.x, a.z, radius, angle.y.atan2(angle.x));
                    p.inlays_c[ni] = lin4(col, variant as f32);
                    ni += 1;
                }
            }
            Decor::Paving { at, half, variant } if np < FLOOR_PAVING && touches(at - half, at + half) => {
                let (lo, hi) = (w3(at - half, 0.0), w3(at + half, 0.0));
                p.paving[np] = Vec4::new(lo.x, hi.z, hi.x, lo.z);
                set4(&mut p.paving_v, np, variant.min(3) as f32);
                np += 1;
            }
            // A floor-story mark shares the paving slots: (centre x, centre z, half along, half
            // across), variant 4 + its kind, the facing in the fraction (Rot16 / 32).
            Decor::FloorMark { at, half, rot, kind } if np < FLOOR_PAVING => {
                let r = Vec2::splat(half.max_element() * 1.3);
                if touches(at - r, at + r) {
                    let a = w3(at, 0.0);
                    p.paving[np] = Vec4::new(a.x, a.z, half.x, half.y);
                    set4(&mut p.paving_v, np, (4 + kind.index()) as f32 + f32::from(rot % 16) / 32.0);
                    np += 1;
                }
            }
            Decor::Channel { from, to, width } if nh < FLOOR_HOLES => {
                let (lo, hi) = (from.min(to) - Vec2::splat(width * 0.5), from.max(to) + Vec2::splat(width * 0.5));
                let pad =
                    if (to - from).x.abs() > (to - from).y.abs() { Vec2::new(0.1, 0.0) } else { Vec2::new(0.0, 0.1) };
                let (lo, hi) = (lo - pad, hi + pad);
                if touches(lo, hi) {
                    let (a, b) = (w3(lo, 0.0), w3(hi, 0.0));
                    p.holes[nh] = Vec4::new(a.x, b.z, b.x, a.z);
                    nh += 1;
                }
            }
            Decor::Pool { at, half } if nh < FLOOR_HOLES && touches(at - half, at + half) => {
                let (a, b) = (w3(at - half, 0.0), w3(at + half, 0.0));
                p.holes[nh] = Vec4::new(a.x, b.z, b.x, a.z);
                nh += 1;
            }
            _ => {}
        }
    }
    p.misc.x = nc as f32;
    p.counts.x = ni as f32;
    p.counts.y = np as f32;
    p.counts.z = nh as f32;
}

/// Floor paint of one map chunk (`rect` in sim units).
fn map_floor_params(
    room: &RoomDef,
    map: &MapLayout,
    db: &ContentDb,
    look: &BiomeLook,
    seed: u32,
    rect: Rect,
) -> FloorParams {
    let mut p = floor_base(look, seed);
    p.shape.x = room.half_extents.x;
    p.shape.y = room.half_extents.y;
    p.counts.w = 1.0;
    // The ground is the bottom of the value ladder on a map (characters > telegraphs > POIs >
    // props > ground > abyss): darker stone and earth, low paving contrast, hand-sized slabs.
    // Open country is bare ground with old paving in patches; roads and clearings are paved.
    p.stone = lin4(lighten(look.stone(), 0.85), 0.2);
    // The bare ground carries the open country's painted detail (ash drifts, scree, cracked
    // earth, the floor-story marks), so it sits well above the stones' mortar, near the old
    // paving's value: the field reads as ground at about a quarter of the value range, never
    // as a hole (the characters, telegraphs and pools stay on top).
    p.dirt = lin4(lighten(look.dirt(), 1.5), 0.14);
    // Big old slabs: at enemy scale the joints read as ground texture, not as a grid.
    p.shape.z = 1.45;
    // Fissures glow, but under the characters and under the orange of the swarm (§3.6.7).
    if look.cracks >= 1.0 {
        p.accent.w = 1.0;
    }
    // POI clearings, first so they win the slots: the Anvil's gold mosaic (variant 0), every other
    // kind a paved disc with a curb (variant 5) laid in its kind's pattern (the rotation slot).
    let mut ni = 0;
    for poi in &map.pois {
        let plaza = db.game.expedition.poi(poi.kind).map_or(poi.radius + 3.0, |t| t.plaza).max(poi.radius);
        let r = Vec2::splat(plaza + 1.0);
        let (lo, hi) = (poi.at - r, poi.at + r);
        if ni < FLOOR_INLAYS && lo.x <= rect.max.x && hi.x >= rect.min.x && lo.y <= rect.max.y && hi.y >= rect.min.y {
            let a = w3(poi.at, 0.0);
            let col = if poi.kind == PoiKind::Gate { hex("#F4E3C1") } else { hex("#C9A24E") };
            let (variant, pattern) = match poi.kind {
                PoiKind::Anvil => (0.0, 0.0),
                PoiKind::Warlord | PoiKind::Gate => (5.0, 1.0),
                PoiKind::Reliquary | PoiKind::Vein | PoiKind::Spring => (5.0, 2.0),
                PoiKind::Lair => (5.0, 3.0),
                PoiKind::Shrine | PoiKind::Watchfire => (5.0, 0.0),
            };
            p.inlays[ni] = Vec4::new(a.x, a.z, plaza, pattern);
            p.inlays_c[ni] = lin4(col, variant);
            ni += 1;
        }
    }
    p.counts.x = ni as f32;
    // Roads.
    let mut n = 0;
    for lane in &map.roads {
        let m = Vec2::splat(lane.width + 2.0);
        let (lo, hi) = (lane.from.min(lane.to) - m, lane.from.max(lane.to) + m);
        if n < FLOOR_PATHS && lo.x <= rect.max.x && hi.x >= rect.min.x && lo.y <= rect.max.y && hi.y >= rect.min.y {
            let (a, b) = (w3(lane.from, 0.0), w3(lane.to, 0.0));
            p.paths[n] = Vec4::new(a.x, a.z, b.x, b.z);
            set4(&mut p.paths_w, n, lane.width);
            n += 1;
        }
    }
    p.style.w = n as f32;
    let grown = Rect::from_corners(rect.min - Vec2::splat(2.0), rect.max + Vec2::splat(2.0));
    paint_decor(&mut p, db, &room.decor, Some(grown));
    paint_footings(&mut p, &room.obstacles, grown);
    p
}

/// Soot and contact darkness under the solid pieces standing on a chunk (largest first), so
/// props sit in the ground instead of on it.
fn paint_footings(p: &mut FloorParams, obstacles: &[Obstacle], area: Rect) {
    let mut near: Vec<(f32, Vec4)> = obstacles
        .iter()
        .filter_map(|o| {
            let (c, h) = match *o {
                Obstacle::Circle { center, radius } => (center, Vec2::splat(radius)),
                Obstacle::Box { center, half } => (center, half),
            };
            let m = h * 1.6;
            let (lo, hi) = (c - m, c + m);
            let touches = lo.x <= area.max.x && hi.x >= area.min.x && lo.y <= area.max.y && hi.y >= area.min.y;
            let a = w3(c, 0.0);
            // A circle travels as (x, z, radius, −1).
            let v = match *o {
                Obstacle::Circle { radius, .. } => Vec4::new(a.x, a.z, radius, -1.0),
                Obstacle::Box { .. } => Vec4::new(a.x, a.z, h.x, h.y),
            };
            touches.then_some((h.x * h.y, v))
        })
        .collect();
    near.sort_by(|a, b| b.0.total_cmp(&a.0));
    let n = near.len().min(FLOOR_FOOTINGS);
    for (i, (_, v)) in near.into_iter().take(n).enumerate() {
        p.footings[i] = v;
    }
    p.misc.w = n as f32;
}
