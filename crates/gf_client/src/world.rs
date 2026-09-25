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
use crate::camera::{KEY_LIGHT_FROM, Shake, w3};
use crate::envkit::{self, CHUNK, Colors, Ctx, Env, Flame, Key, MeshBuf, h01, lin};
use crate::materials::{
    ABYSS_Y, Abyss, AbyssMaterial, BiomeLook, FLOOR_CRACKS, FLOOR_HOLES, FLOOR_INLAYS, FLOOR_PATHS, FLOOR_PAVING,
    Floor, FloorMaterial, FloorParams, ToonMaterial, ToonStyle, toon, toon_from_standard,
};
use crate::palette::{Palette, hex, mix};
use crate::scene::RoomGeometry;
use crate::terrain;
use gf_content::schema::{Decor, MapLayout, TileKind};
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
        .add_systems(Update, pool_lights.in_set(ClientSet::Presentation));
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

    let mut floors: BTreeMap<u32, (MeshBuf, Rect)> = BTreeMap::new();
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
    lights.lumens = look.brazier;
    lights.timer = 0.0;
    let verts: usize;
    let mut draws = 0;
    {
        let bufs = env.into_buffers();
        verts = bufs.values().map(|b| b.pos.len()).sum::<usize>();
        for ((_, key), buf) in bufs {
            if buf.is_empty() {
                continue;
            }
            let mesh = stores.meshes.add(buf.into_mesh());
            let mut e = commands.spawn((RoomGeometry, Mesh3d(mesh), Transform::default()));
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
        for (buf, rect) in floors.into_values() {
            if buf.is_empty() {
                continue;
            }
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
            let mesh = stores.meshes.add(buf.into_mesh());
            commands.spawn((RoomGeometry, Mesh3d(mesh), MeshMaterial3d(mat), Transform::default(), NotShadowCaster));
            draws += 1;
        }
        // The abyss under the whole map.
        let reach = half + Vec2::splat(90.0);
        let plane = stores.meshes.add(Plane3d::new(Vec3::Y, reach));
        // Seen through bays and chasms, far below the rivers: dimmer than the surface liquid so
        // the hazards at floor level read first.
        let inner = (half - Vec2::splat(10.0)).max(Vec2::ONE);
        let mut params = look.abyss_params(inner, (seed % 997) as f32);
        params.glow.w *= 0.55;
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
                    d = smin(d, sd, 1.6);
                }
            }
            let r = 0.3 + 0.55 * vnoise(p / 3.0, 0x5EA);
            f[j * w + i] = d - r;
        }
    }
    Field { origin: t.origin, w, h, f }
}

/// Region tint per tile, as a vertex-colour multiplier around 1 (hue shift, not darkening).
fn tile_tints(map: &MapLayout, room: &RoomDef) -> Vec<Vec3> {
    let themes = room.expedition.as_ref().map(|x| &x.themes);
    let tints: Vec<Vec3> = map
        .regions
        .iter()
        .map(|r| {
            let hexs = themes.and_then(|t| t.get(r.theme as usize)).map(|t| t.tint.as_str()).unwrap_or("#808080");
            let l = hex(hexs).to_linear();
            let v = Vec3::new(l.red, l.green, l.blue);
            let m = (v.x + v.y + v.z) / 3.0;
            let n = if m > 1e-4 { v / m } else { Vec3::ONE };
            Vec3::ONE.lerp(n, 0.16).clamp(Vec3::splat(0.8), Vec3::splat(1.25))
        })
        .collect();
    map.tiles.region.iter().map(|&r| tints.get(r as usize).copied().unwrap_or(Vec3::ONE)).collect()
}

fn land(env: &mut Env, floors: &mut BTreeMap<u32, (MeshBuf, Rect)>, map: &MapLayout, room: &RoomDef, c: &Colors) {
    let t0 = std::time::Instant::now();
    let mask = ground_mask(map, room);
    let field = land_field(map, &mask);
    let tints = tile_tints(map, room);
    let t = &map.tiles;
    let tint_at = |p: Vec2| {
        // Bilinear over tile centres.
        let q = (p - t.origin) / t.size - Vec2::splat(0.5);
        let (x0, y0) = (q.x.floor(), q.y.floor());
        let (fx, fy) = (q.x - x0, q.y - y0);
        let at = |x: f32, y: f32| {
            let (x, y) = ((x as i32).clamp(0, t.w as i32 - 1), (y as i32).clamp(0, t.h as i32 - 1));
            tints[t.index(x as u16, y as u16)]
        };
        let a = at(x0, y0).lerp(at(x0 + 1.0, y0), fx);
        let b = at(x0, y0 + 1.0).lerp(at(x0 + 1.0, y0 + 1.0), fx);
        let v = a.lerp(b, fy);
        [v.x, v.y, v.z, 1.0]
    };
    let pit_at = |p: Vec2| -> Ground {
        match t.tile_of(p) {
            Some((x, y)) => mask[t.index(x, y)],
            None => Ground::Void,
        }
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
    let mut chunk_bufs: Vec<Option<(MeshBuf, Rect)>> = Vec::new();
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
                (MeshBuf::default(), Rect::from_corners(x0, x0 + Vec2::splat(CHUNK)))
            });
            let buf = &mut entry.0;
            // Polygon around the cell, counter-clockwise (sim): corner, crossing, corner, …
            let corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)];
            let mut poly = [(Vec2::ZERO, 0u64, Vec2::ZERO, false); 8];
            let mut n = 0;
            for k in 0..4 {
                let (ci, cj) = corners[k];
                if inside[k] {
                    poly[n] = (field.point(ci, cj), corner_key(ci, cj), Vec2::ZERO, false);
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
                    poly[n] = (p, key, g, true);
                    n += 1;
                }
            }
            if n < 3 {
                continue;
            }
            let mut idx = [0u32; 8];
            for (k, (p, key, _, _)) in poly[..n].iter().enumerate() {
                let s = &mut seen[slot(*key)];
                if s.0 != chunk {
                    *s = (chunk, buf.vert(w3(*p, 0.0), Vec3::Y, [p.x * 0.1, -p.y * 0.1], tint_at(*p)));
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
            env.sheet([q(lo.x, lo.y), q(hi.x, lo.y), q(hi.x, hi.y), q(lo.x, hi.y)], [[1.0; 4]; 4], Key::Liquid);
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
                set4(&mut p.paving_v, np, variant as f32);
                np += 1;
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
    // Paving thins out off the roads.
    p.dirt.w = 0.3;
    // POI clearings: a paved disc with a curb (inlay variant 5), first so they win the slots.
    let mut ni = 0;
    for poi in &map.pois {
        let plaza = db.game.expedition.poi(poi.kind).map_or(poi.radius + 3.0, |t| t.plaza).max(poi.radius);
        let r = Vec2::splat(plaza + 1.0);
        let (lo, hi) = (poi.at - r, poi.at + r);
        if ni < FLOOR_INLAYS && lo.x <= rect.max.x && hi.x >= rect.min.x && lo.y <= rect.max.y && hi.y >= rect.min.y {
            let a = w3(poi.at, 0.0);
            let col = if poi.kind == PoiKind::Gate { hex("#F4E3C1") } else { hex("#C9A24E") };
            p.inlays[ni] = Vec4::new(a.x, a.z, plaza, 0.0);
            p.inlays_c[ni] = lin4(col, 5.0);
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
    p
}
