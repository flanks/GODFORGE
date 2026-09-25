//! Replicated world → render entities (§12 art direction on greybox primitives).
//!
//! * Room geometry rebuilds whenever `room_serial` changes (ground, walls, obstacles, decor).
//! * Replicated entities are matched by `NetId`: spawned on first sight, updated from every
//!   snapshot, despawned when they leave it.
//! * Straight-line movers extrapolate from their motion descriptor at the fractional render tick;
//!   everything else eases toward its latest authoritative position.
//! * The local player renders at its predicted position (see `net::Prediction`).

use crate::camera::w3;
use crate::input::InputState;
use crate::net::{Link, Prediction};
use crate::palette::{Look, Palette, element_color, flat, hdr, hex, lighten, mix, rarity_color, yaw};
use crate::{ClientConfig, ClientSet};
use gf_content::{ContentDb, Decor, EnemyShape, RoomDef};
use gf_core::aim::AimMode;
use gf_core::ids::NetId;
use gf_core::movement::Obstacle;
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_engine::bevy::math::Affine2;
use gf_engine::client::NotShadowCaster;
use gf_engine::prelude::*;
use gf_net::quant::{u8_to_dir, u8_to_frac, u16_to_dir};
use gf_net::*;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, FRAC_PI_4};

const PROJECTILE_HEIGHT: f32 = 0.9;
const GOLD: &str = "#FFC940";
const BRONZE: &str = "#9A7443";
const IRON: &str = "#3B3633";
const INK: &str = "#140C08";

#[derive(Component)]
pub struct RoomGeometry;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Tint {
    Base,
    Flash,
    Warn,
    Frozen,
    Stunned,
    Status(u8),
}

/// Render proxy of one replicated entity.
#[derive(Component)]
pub struct Visual {
    pub id: NetId,
    pub kind: EntityKind,
    /// Latest authoritative position (sim plane).
    pub pos: Vec2,
    /// Rendered position (sim plane).
    pub shown: Vec2,
    pub motion: Option<Motion>,
    pub facing: f32,
    pub flags: EntityFlags,
    pub hp: f32,
    pub status: u8,
    pub color: Color,
    /// Visual radius (HUD bars, VFX sizing).
    pub radius: f32,
    /// Hit-flash timer.
    pub flash: f32,
    pub lift: f32,
    fresh: bool,
    body: Option<Entity>,
    /// Animated children: telegraph fill / anvil progress, anvil ring, anvil hot glow.
    parts: [Option<Entity>; 3],
    tint: Tint,
    base_mat: Option<Handle<StandardMaterial>>,
}

impl Visual {
    fn new(e: &EntityView, color: Color, radius: f32, lift: f32) -> Self {
        let pos = e.pos.to_vec2();
        let mut v = Visual {
            id: e.id,
            kind: e.kind,
            pos,
            shown: pos,
            motion: e.motion,
            facing: 0.0,
            flags: e.flags,
            hp: 1.0,
            status: 0,
            color,
            radius,
            flash: 0.0,
            lift,
            fresh: true,
            body: None,
            parts: [None; 3],
            tint: Tint::Base,
            base_mat: None,
        };
        v.update(e);
        v
    }

    fn update(&mut self, e: &EntityView) {
        self.pos = e.pos.to_vec2();
        self.motion = e.motion;
        let d = u8_to_dir(e.facing);
        self.facing = d.y.atan2(d.x);
        self.flags = e.flags;
        self.hp = u8_to_frac(e.hp);
        self.status = e.status;
    }
}

/// Render rig of one player.
#[derive(Component)]
pub struct PlayerRig {
    pub slot: u8,
    pub shown: Vec2,
    fresh: bool,
    pivot: Entity,
    chevron: Entity,
    body: Entity,
    shield: Entity,
    aura: Entity,
    tether: Entity,
    body_mat: Handle<StandardMaterial>,
    ghost_mat: Handle<StandardMaterial>,
    downed: bool,
}

#[derive(Component)]
struct TargetMarker;

#[derive(Component)]
struct AimLine;

#[derive(Resource, Default)]
pub struct SceneIndex {
    /// NetId → (render entity, last snapshot stamp that contained it).
    visuals: HashMap<NetId, (Entity, u32)>,
    pub players: [Option<Entity>; 4],
    /// Live projectile / hazard / telegraph count (VFX LOD input).
    pub effect_count: u32,
    room_serial: Option<u32>,
    last_tick: Option<u32>,
    stamp: u32,
}

impl SceneIndex {
    pub fn entity(&self, id: NetId) -> Option<Entity> {
        self.visuals.get(&id).map(|(e, _)| *e)
    }

    /// Forget the session (new run / reconnect): despawn every proxy; the room rebuilds on the
    /// next snapshot.
    pub fn reset(&mut self, commands: &mut Commands) {
        for (e, _) in self.visuals.values() {
            commands.entity(*e).despawn();
        }
        for e in self.players.iter().flatten() {
            commands.entity(*e).despawn();
        }
        *self = SceneIndex::default();
    }
}

pub fn build(app: &mut App) {
    app.init_resource::<SceneIndex>().add_systems(Startup, spawn_markers).add_systems(
        Update,
        (
            rebuild_room,
            sync_entities,
            hit_flash,
            animate_entities,
            tint_entities,
            animate_anvils,
            sync_players,
            update_markers,
        )
            .chain()
            .in_set(ClientSet::Scene),
    );
}

/// Spawning helper bundling the asset stores.
struct Kit<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    pal: &'a mut Palette,
    mats: &'a mut Assets<StandardMaterial>,
    meshes: &'a mut Assets<Mesh>,
}

impl Kit<'_, '_, '_> {
    fn mat(&mut self, c: Color, look: Look) -> Handle<StandardMaterial> {
        self.pal.mat(self.mats, c, look)
    }

    fn child(&mut self, parent: Entity, mesh: &Handle<Mesh>, mat: Handle<StandardMaterial>, tf: Transform) -> Entity {
        self.commands.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(mat), tf, ChildOf(parent))).id()
    }

    fn hidden_child(
        &mut self,
        parent: Entity,
        mesh: &Handle<Mesh>,
        mat: Handle<StandardMaterial>,
        tf: Transform,
    ) -> Entity {
        self.commands.spawn((Mesh3d(mesh.clone()), MeshMaterial3d(mat), tf, Visibility::Hidden, ChildOf(parent))).id()
    }

    fn geometry(&mut self, mesh: &Handle<Mesh>, mat: Handle<StandardMaterial>, tf: Transform) {
        self.commands.spawn((RoomGeometry, Mesh3d(mesh.clone()), MeshMaterial3d(mat), tf));
    }

    /// Soft contact shadow (no shadow maps: cheap and readable at 400 enemies).
    fn shadow(&mut self, parent: Entity, radius: f32, lift: f32) {
        let m = self.mat(Color::srgba(0.0, 0.0, 0.0, 0.38), Look::Decal);
        let disc = self.pal.disc.clone();
        self.child(
            parent,
            &disc,
            m,
            Transform {
                translation: Vec3::new(0.0, 0.012 - lift, 0.0),
                rotation: flat(FRAC_PI_2),
                scale: Vec3::splat(radius),
            },
        );
    }
}

// ───────────────────────────── room ─────────────────────────────

#[allow(clippy::too_many_arguments)]
fn rebuild_room(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut pal: ResMut<Palette>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut index: ResMut<SceneIndex>,
    mut ambient: ResMut<GlobalAmbientLight>,
    old: Query<Entity, With<RoomGeometry>>,
) {
    let Some(world) = &link.latest else { return };
    if index.room_serial == Some(world.run.room_serial) {
        return;
    }
    index.room_serial = Some(world.run.room_serial);
    for e in &old {
        commands.entity(e).despawn();
    }
    let Some(room) = cfg.content.rooms.try_get(world.run.room) else { return };
    let colors = cfg
        .content
        .biomes
        .try_get(world.run.biome)
        .map(|b| [hex(&b.palette[0]), hex(&b.palette[1]), hex(&b.palette[2])])
        .unwrap_or([hex("#2B1B15"), hex("#FF8A2A"), hex("#140D0A")]);
    ambient.color = mix(Color::srgb(1.0, 0.88, 0.74), colors[1], 0.22);
    let mut kit = Kit { commands: &mut commands, pal: &mut pal, mats: &mut mats, meshes: &mut meshes };
    build_room(&mut kit, room, colors);
}

fn hash01(i: i32, k: u32) -> f32 {
    let mut h = (i as u32).wrapping_mul(0x9E37_79B9) ^ k.wrapping_mul(0x85EB_CA6B);
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    (h & 0xffff) as f32 / 65535.0
}

fn build_room(kit: &mut Kit, room: &RoomDef, [base, accent, deep]: [Color; 3]) {
    let half = room.half_extents;
    // Painted floor: tileable flagstones tinted by the biome palette.
    let floor = lighten(mix(mix(base, Color::srgb(0.36, 0.34, 0.33), 0.45), accent, 0.06), 1.45);
    let ground_mat = kit.mats.add(StandardMaterial {
        base_color: floor,
        base_color_texture: Some(kit.pal.ground_texture.clone()),
        uv_transform: Affine2::from_scale(half * 2.0 / 10.0),
        perceptual_roughness: 0.95,
        reflectance: 0.15,
        ..default()
    });
    let ground = kit.meshes.add(Plane3d::new(Vec3::Y, half));
    kit.geometry(&ground, ground_mat, Transform::default());
    // The abyss beyond the arena.
    let void_mesh = kit.meshes.add(Plane3d::new(Vec3::Y, half + Vec2::splat(60.0)));
    let void_mat = kit.mat(lighten(deep, 0.9), Look::Matte);
    kit.geometry(&void_mesh, void_mat, Transform::from_xyz(0.0, -0.8, 0.0));
    // Rim glow where floor meets abyss.
    let rim = kit.mat(hdr(accent, 1.6).with_alpha(0.35), Look::Decal);
    let quad = kit.pal.quad.clone();
    for (center, size) in [
        (Vec2::new(0.0, -half.y - 0.25), Vec2::new(half.x * 2.0, 0.5)),
        (Vec2::new(-half.x - 0.25, 0.0), Vec2::new(0.5, half.y * 2.0)),
        (Vec2::new(half.x + 0.25, 0.0), Vec2::new(0.5, half.y * 2.0)),
    ] {
        kit.geometry(
            &quad,
            rim.clone(),
            Transform { translation: w3(center, -0.02), rotation: flat(FRAC_PI_2), scale: size.extend(1.0) },
        );
    }

    // Walls: tall ruined backdrop to the north, medium flanks, a low ledge to the south so the
    // camera never loses a character behind geometry (§5 readability).
    let wall = kit.mat(lighten(mix(base, Color::srgb(0.2, 0.19, 0.22), 0.4), 1.25), Look::Matte);
    let cap = kit.mat(hex(BRONZE), Look::Metal);
    let cube = kit.pal.cube.clone();
    let segment = |kit: &mut Kit, center: Vec2, size: Vec2, h: f32, i: i32| {
        kit.geometry(
            &cube,
            wall.clone(),
            Transform::from_translation(w3(center, h * 0.5)).with_scale(Vec3::new(size.x, h, size.y)),
        );
        if hash01(i, 9) > 0.55 {
            kit.geometry(
                &cube,
                cap.clone(),
                Transform::from_translation(w3(center, h + 0.08)).with_scale(Vec3::new(
                    size.x + 0.15,
                    0.16,
                    size.y + 0.15,
                )),
            );
        }
    };
    let step = 3.0;
    let nx = ((half.x * 2.0 + 2.4) / step).ceil() as i32;
    for i in 0..nx {
        let x = -half.x - 1.2 + (i as f32 + 0.5) * step;
        let h = 1.8 + 1.8 * hash01(i, 1);
        segment(kit, Vec2::new(x, half.y + 0.7), Vec2::new(step - 0.1, 1.4), h, i);
        segment(kit, Vec2::new(x, -half.y - 0.6), Vec2::new(step - 0.1, 1.2), 0.35 + 0.25 * hash01(i, 2), i + 500);
    }
    let ny = ((half.y * 2.0) / step).ceil() as i32;
    for j in 0..ny {
        let y = -half.y + (j as f32 + 0.5) * step;
        let t = (y + half.y) / (half.y * 2.0);
        let h = 0.6 + 1.6 * t + 0.6 * hash01(j, 3);
        segment(kit, Vec2::new(-half.x - 0.7, y), Vec2::new(1.4, step - 0.1), h, j + 1000);
        segment(kit, Vec2::new(half.x + 0.7, y), Vec2::new(1.4, step - 0.1), h * (0.8 + 0.4 * hash01(j, 4)), j + 2000);
    }

    // Obstacles (skipping those a Decor::Pillar already dresses).
    let stone = kit.mat(lighten(mix(base, Color::srgb(0.5, 0.46, 0.42), 0.5), 1.5), Look::Matte);
    let cylinder = kit.pal.cylinder.clone();
    let dressed = |c: Vec2| room.decor.iter().any(|d| matches!(d, Decor::Pillar { at, .. } if at.distance(c) < 0.5));
    for o in &room.obstacles {
        match *o {
            Obstacle::Circle { center, radius } if !dressed(center) => {
                kit.geometry(
                    &cylinder,
                    stone.clone(),
                    Transform::from_translation(w3(center, 1.1)).with_scale(Vec3::new(radius, 2.2, radius)),
                );
                kit.geometry(
                    &cylinder,
                    cap.clone(),
                    Transform::from_translation(w3(center, 2.3)).with_scale(Vec3::new(
                        radius * 1.15,
                        0.25,
                        radius * 1.15,
                    )),
                );
            }
            Obstacle::Box { center, half } if !dressed(center) => {
                kit.geometry(
                    &cube,
                    stone.clone(),
                    Transform::from_translation(w3(center, 0.7)).with_scale(Vec3::new(half.x * 2.0, 1.4, half.y * 2.0)),
                );
                kit.geometry(
                    &cube,
                    cap.clone(),
                    Transform::from_translation(w3(center, 1.48)).with_scale(Vec3::new(
                        half.x * 2.0 + 0.2,
                        0.16,
                        half.y * 2.0 + 0.2,
                    )),
                );
            }
            _ => {}
        }
    }

    // Decor.
    let iron = kit.mat(hex(IRON), Look::Metal);
    let bronze = kit.mat(hex(BRONZE), Look::Metal);
    let lava = kit.mat(hdr(accent, 3.2).with_alpha(0.95), Look::Decal);
    let lava_halo = kit.mat(hdr(accent, 1.2).with_alpha(0.2), Look::Decal);
    let flame = kit.mat(hdr(mix(accent, Color::WHITE, 0.3), 1.0), Look::Glow);
    let sphere = kit.pal.sphere.clone();
    for d in &room.decor {
        match *d {
            Decor::LavaCrack { from, to, width } => {
                let v = to - from;
                let (mid, len, ang) = ((from + to) * 0.5, v.length(), v.y.atan2(v.x));
                kit.geometry(
                    &quad,
                    lava_halo.clone(),
                    Transform {
                        translation: w3(mid, 0.008),
                        rotation: flat(ang),
                        scale: Vec3::new(width * 4.0, len + width * 2.0, 1.0),
                    },
                );
                kit.geometry(
                    &quad,
                    lava.clone(),
                    Transform { translation: w3(mid, 0.012), rotation: flat(ang), scale: Vec3::new(width, len, 1.0) },
                );
            }
            Decor::BrokenAnvil { at, scale } => {
                kit.geometry(
                    &cube,
                    iron.clone(),
                    Transform {
                        translation: w3(at, 0.28 * scale),
                        rotation: Quat::from_rotation_y(0.6) * Quat::from_rotation_z(0.22),
                        scale: Vec3::new(1.5, 0.55, 0.7) * scale,
                    },
                );
                kit.geometry(
                    &cube,
                    iron.clone(),
                    Transform {
                        translation: w3(at + Vec2::new(1.1, -0.5) * scale, 0.18 * scale),
                        rotation: Quat::from_rotation_y(-0.4) * Quat::from_rotation_x(-0.3),
                        scale: Vec3::new(0.7, 0.4, 0.6) * scale,
                    },
                );
            }
            Decor::Brazier { at } => {
                kit.geometry(
                    &cylinder,
                    bronze.clone(),
                    Transform::from_translation(w3(at, 0.45)).with_scale(Vec3::new(0.42, 0.9, 0.42)),
                );
                kit.geometry(
                    &sphere,
                    flame.clone(),
                    Transform::from_translation(w3(at, 1.05)).with_scale(Vec3::new(0.3, 0.42, 0.3)),
                );
                kit.commands.spawn((
                    RoomGeometry,
                    PointLight { color: mix(accent, Color::WHITE, 0.2), intensity: 160_000.0, range: 9.0, ..default() },
                    Transform::from_translation(w3(at, 1.6)),
                ));
            }
            Decor::Pillar { at, radius, height } => {
                kit.geometry(
                    &cylinder,
                    stone.clone(),
                    Transform::from_translation(w3(at, height * 0.5)).with_scale(Vec3::new(radius, height, radius)),
                );
                kit.geometry(
                    &cube,
                    cap.clone(),
                    Transform::from_translation(w3(at, height + 0.15)).with_scale(Vec3::new(
                        radius * 2.3,
                        0.3,
                        radius * 2.3,
                    )),
                );
                kit.geometry(
                    &cube,
                    stone.clone(),
                    Transform::from_translation(w3(at, 0.15)).with_scale(Vec3::new(radius * 2.3, 0.3, radius * 2.3)),
                );
            }
        }
    }
}

// ───────────────────────────── replicated entities ─────────────────────────────

#[allow(clippy::too_many_arguments)]
fn sync_entities(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut pal: ResMut<Palette>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut index: ResMut<SceneIndex>,
    mut visuals: Query<&mut Visual>,
) {
    let Some(world) = link.latest.clone() else { return };
    if index.last_tick == Some(world.tick) {
        return;
    }
    index.last_tick = Some(world.tick);
    index.stamp = index.stamp.wrapping_add(1);
    let stamp = index.stamp;
    let me = link.slot;
    let ally_alpha = cfg.content.game.vfx.ally_effect_alpha;
    let mut effects = 0;
    let mut kit = Kit { commands: &mut commands, pal: &mut pal, mats: &mut mats, meshes: &mut meshes };
    for e in &world.entities {
        if matches!(
            e.kind,
            EntityKind::Projectile { .. }
                | EntityKind::EnemyShot { .. }
                | EntityKind::Hazard { .. }
                | EntityKind::Telegraph { .. }
        ) {
            effects += 1;
        }
        if let Some((ent, seen)) = index.visuals.get_mut(&e.id) {
            *seen = stamp;
            if let Ok(mut v) = visuals.get_mut(*ent) {
                v.update(e);
            }
            continue;
        }
        let ent = spawn_visual(&mut kit, &cfg.content, e, me, ally_alpha);
        index.visuals.insert(e.id, (ent, stamp));
    }
    index.effect_count = effects;
    index.visuals.retain(|_, (ent, seen)| {
        if *seen == stamp {
            true
        } else {
            commands.entity(*ent).despawn();
            false
        }
    });
}

fn door_color(db: &ContentDb, reward: DoorReward) -> Color {
    match reward {
        DoorReward::PartCache => hex("#B865FF"),
        DoorReward::ShardCache => hex("#8FF7FF"),
        DoorReward::Anvil => hex("#FFB82E"),
        DoorReward::Healing => hex("#FF4D6D"),
        DoorReward::Boon { god } => db.gods.try_get(god).map_or(hex(GOLD), |g| hex(&g.color)),
        DoorReward::EliteChallenge => hex("#FF3B30"),
        DoorReward::Onward => hex("#F4E3C1"),
    }
}

pub fn door_label(db: &ContentDb, reward: DoorReward) -> String {
    match reward {
        DoorReward::PartCache => "Part Cache".into(),
        DoorReward::ShardCache => "Godshards".into(),
        DoorReward::Anvil => "Anvil".into(),
        DoorReward::Healing => "Healing Spring".into(),
        DoorReward::Boon { god } => db.gods.try_get(god).map_or("Boon".into(), |g| format!("Boon of {}", g.name)),
        DoorReward::EliteChallenge => "Elite Challenge".into(),
        DoorReward::Onward => "Onward".into(),
    }
}

fn source_slot(owner: u8) -> Option<u8> {
    (owner < 12).then_some(owner % 4)
}

fn spawn_visual(kit: &mut Kit, db: &ContentDb, e: &EntityView, me: Option<u8>, ally_alpha: f32) -> Entity {
    let pos = e.pos.to_vec2();
    let parent = kit.commands.spawn((Transform::from_translation(w3(pos, 0.0)), Visibility::default())).id();
    let mut v = match e.kind {
        EntityKind::Enemy { def } => spawn_enemy(kit, db, parent, e, def),
        EntityKind::Projectile { style, element, owner, radius_q } => {
            let r = (radius_q as f32 / 32.0).max(0.07) * 1.5;
            let c = element_color(element);
            let mine = me.is_some() && source_slot(owner) == me;
            let mat =
                if mine { kit.mat(c, Look::Glow) } else { kit.mat(hdr(c, 2.0).with_alpha(ally_alpha), Look::Decal) };
            use gf_core::weapon::ProjectileStyle as S;
            let stretch = match style {
                S::Bolt | S::Arrow | S::Needle | S::Slug => 2.6,
                S::Shard | S::Pellet | S::Blade => 1.7,
                _ => 1.0,
            };
            let mesh = if r > 0.3 { kit.pal.sphere.clone() } else { kit.pal.low_sphere.clone() };
            let body = kit.child(parent, &mesh, mat, Transform::from_scale(Vec3::new(r, r, r * stretch)));
            kit.commands.entity(parent).insert(NotShadowCaster);
            kit.commands.entity(body).insert(NotShadowCaster);
            let mut v = Visual::new(e, c, r, PROJECTILE_HEIGHT);
            v.body = Some(body);
            v
        }
        EntityKind::EnemyShot { radius_q } => {
            let r = (radius_q as f32 / 32.0).max(0.1) * 1.3;
            let danger = kit.pal.danger;
            let shell = kit.mat(hdr(danger, 1.4).with_alpha(0.5), Look::Decal);
            let core = kit.mat(hex("#FF5AA8"), Look::Glow);
            let sphere = kit.pal.low_sphere.clone();
            kit.child(parent, &sphere, shell, Transform::from_scale(Vec3::splat(r * 1.35)));
            let body = kit.child(parent, &sphere, core, Transform::from_scale(Vec3::splat(r * 0.75)));
            let mut v = Visual::new(e, danger, r, 0.8);
            v.body = Some(body);
            v
        }
        EntityKind::Telegraph { shape, .. } => spawn_telegraph(kit, parent, e, shape),
        EntityKind::Hazard { kind, element, radius_q } => {
            let r = radius_q as f32 / 32.0;
            let ally = e.flags.contains(EntityFlags::ALLY);
            let c = if ally { element_color(element) } else { mix(kit.pal.danger, element_color(element), 0.35) };
            let alpha = match kind {
                HazardKind::Well => 0.4,
                HazardKind::Field => 0.2,
                HazardKind::Pool | HazardKind::Puddle => 0.36,
                HazardKind::Trail | HazardKind::Ground => 0.3,
            };
            // Readability budget: player-made zones stay quiet so enemy danger reads first.
            let (alpha, edge_alpha) = if ally { (alpha * 0.5, 0.4) } else { (alpha, 0.75) };
            let fill = kit.mat(hdr(c, 1.3).with_alpha(alpha), Look::Decal);
            let edge = kit.mat(hdr(c, 2.6).with_alpha(edge_alpha), Look::Decal);
            let (disc, ring) = (kit.pal.disc.clone(), kit.pal.ring.clone());
            kit.child(parent, &disc, fill, Transform::from_scale(Vec3::splat(r)));
            kit.child(
                parent,
                &ring,
                edge,
                Transform { translation: Vec3::Z * 0.002, scale: Vec3::splat(r), ..default() },
            );
            let mut v = Visual::new(e, c, r, 0.015 + (e.id.0 % 5) as f32 * 0.002);
            if kind == HazardKind::Well {
                let swirl_mat = kit.mat(hdr(c, 3.0).with_alpha(0.5), Look::Decal);
                let swirl = kit.pal.sector(kit.meshes, 70);
                v.parts[0] = Some(kit.child(
                    parent,
                    &swirl,
                    swirl_mat,
                    Transform { translation: Vec3::Z * 0.004, scale: Vec3::splat(r * 0.8), ..default() },
                ));
            }
            v
        }
        EntityKind::Pickup { kind, owner } => {
            let mine = owner.is_none() || owner == me;
            let (c, mesh, scale, rot) = match kind {
                PickupKind::Part { rarity } => (
                    rarity_color(rarity),
                    kit.pal.cube.clone(),
                    Vec3::splat(0.34),
                    Quat::from_rotation_x(FRAC_PI_4) * Quat::from_rotation_z(FRAC_PI_4),
                ),
                PickupKind::Shards(n) => {
                    let s = 0.2 + 0.05 * (n as f32).max(1.0).ln();
                    (hex("#8FF7FF"), kit.pal.cone.clone(), Vec3::new(s * 0.6, s * 1.6, s * 0.6), Quat::IDENTITY)
                }
                PickupKind::Health => (hex("#FF4D6D"), kit.pal.sphere.clone(), Vec3::splat(0.26), Quat::IDENTITY),
            };
            let mat = if mine { kit.mat(c, Look::Glow) } else { kit.mat(c.with_alpha(0.25), Look::Ghost) };
            let body = kit.child(parent, &mesh, mat, Transform { rotation: rot, scale, ..default() });
            if mine
                && let PickupKind::Part { rarity } = kind
                && rarity >= Rarity::Rare
            {
                // Loot beam: readable from across a 400-enemy room.
                let beam =
                    kit.mat(hdr(c, 2.0).with_alpha(if rarity >= Rarity::Epic { 0.45 } else { 0.28 }), Look::Decal);
                let cyl = kit.pal.cylinder.clone();
                kit.child(
                    parent,
                    &cyl,
                    beam,
                    Transform::from_xyz(0.0, 1.6, 0.0).with_scale(Vec3::new(0.07, 3.6, 0.07)),
                );
            }
            kit.shadow(parent, 0.3, 0.45);
            let mut v = Visual::new(e, c, 0.3, 0.45);
            v.body = Some(body);
            v
        }
        EntityKind::Anvil => spawn_anvil(kit, db, parent, e),
        EntityKind::Door { reward, .. } => {
            let c = door_color(db, reward);
            let stone = kit.mat(hex("#4A403A"), Look::Matte);
            let bronze = kit.mat(hex(BRONZE), Look::Metal);
            let panel = kit.mat(hdr(c, 2.2).with_alpha(0.55), Look::Decal);
            let glow = kit.mat(hdr(c, 1.6).with_alpha(0.3), Look::Decal);
            let emblem = kit.mat(c, Look::Glow);
            let (cyl, cube, quad, disc, sphere) = (
                kit.pal.cylinder.clone(),
                kit.pal.cube.clone(),
                kit.pal.quad.clone(),
                kit.pal.disc.clone(),
                kit.pal.sphere.clone(),
            );
            for x in [-1.3, 1.3] {
                kit.child(
                    parent,
                    &cyl,
                    stone.clone(),
                    Transform::from_xyz(x, 1.5, 0.0).with_scale(Vec3::new(0.32, 3.0, 0.32)),
                );
            }
            kit.child(parent, &cube, bronze, Transform::from_xyz(0.0, 3.1, 0.0).with_scale(Vec3::new(3.3, 0.45, 0.6)));
            let body = kit.child(
                parent,
                &quad,
                panel,
                Transform::from_xyz(0.0, 1.45, 0.0).with_scale(Vec3::new(2.3, 2.8, 1.0)),
            );
            kit.child(
                parent,
                &disc,
                glow,
                Transform { translation: Vec3::Y * 0.02, rotation: flat(FRAC_PI_2), scale: Vec3::splat(2.2) },
            );
            kit.child(parent, &sphere, emblem, Transform::from_xyz(0.0, 3.65, 0.0).with_scale(Vec3::splat(0.3)));
            let mut v = Visual::new(e, c, 1.5, 0.0);
            v.body = Some(body);
            v
        }
        EntityKind::Barricade { half_len_q, dir } => {
            let half = half_len_q as f32 / 32.0;
            let bronze = kit.mat(hex(BRONZE), Look::Metal);
            let cube = kit.pal.cube.clone();
            let d = u16_to_dir(dir);
            let body = kit.child(
                parent,
                &cube,
                bronze,
                Transform {
                    translation: Vec3::Y * 0.6,
                    rotation: yaw(d.y.atan2(d.x)),
                    scale: Vec3::new(0.45, 1.2, half * 2.0),
                },
            );
            let mut v = Visual::new(e, hex(BRONZE), half, 0.0);
            v.body = Some(body);
            v
        }
        EntityKind::Turret { owner } => {
            let c = kit.pal.player(owner);
            let metal = kit.mat(mix(c, hex(IRON), 0.45), Look::Metal);
            let glow = kit.mat(c, Look::Glow);
            let (cyl, sphere, cube) = (kit.pal.cylinder.clone(), kit.pal.sphere.clone(), kit.pal.cube.clone());
            kit.child(
                parent,
                &cyl,
                metal.clone(),
                Transform::from_xyz(0.0, 0.25, 0.0).with_scale(Vec3::new(0.38, 0.5, 0.38)),
            );
            let body = kit.child(
                parent,
                &sphere,
                metal.clone(),
                Transform::from_xyz(0.0, 0.72, 0.0).with_scale(Vec3::splat(0.3)),
            );
            kit.child(parent, &cube, glow, Transform::from_xyz(0.0, 0.72, -0.4).with_scale(Vec3::new(0.1, 0.1, 0.55)));
            kit.shadow(parent, 0.45, 0.0);
            let mut v = Visual::new(e, c, 0.4, 0.0);
            v.body = Some(body);
            v
        }
        EntityKind::Echo { owner } => {
            let c = kit.pal.player(owner);
            let ghost = kit.mat(c.with_alpha(0.45), Look::Ghost);
            let capsule = kit.pal.capsule.clone();
            let body = kit.child(parent, &capsule, ghost, Transform::from_scale(Vec3::splat(0.55)));
            let mut v = Visual::new(e, c, 0.3, 0.9);
            v.body = Some(body);
            v
        }
        EntityKind::Blade { owner } => {
            let c = kit.pal.player(owner);
            let glow = kit.mat(hdr(c, 1.2), Look::Glow);
            let cube = kit.pal.cube.clone();
            let body = kit.child(parent, &cube, glow, Transform::from_scale(Vec3::new(1.0, 0.05, 0.2)));
            let mut v = Visual::new(e, c, 0.5, 0.8);
            v.body = Some(body);
            v
        }
        EntityKind::Chest => {
            let gold = kit.mat(hex(GOLD), Look::Metal);
            let cube = kit.pal.cube.clone();
            let body =
                kit.child(parent, &cube, gold, Transform::from_xyz(0.0, 0.3, 0.0).with_scale(Vec3::new(0.9, 0.6, 0.6)));
            let mut v = Visual::new(e, hex(GOLD), 0.5, 0.0);
            v.body = Some(body);
            v
        }
    };
    v.fresh = true;
    kit.commands.entity(parent).insert(v);
    parent
}

fn spawn_enemy(kit: &mut Kit, db: &ContentDb, parent: Entity, e: &EntityView, def: u16) -> Visual {
    let (color, r, shape, boss) = match db.enemies.try_get(def) {
        Some(d) => (hex(&d.color), d.radius * d.scale.max(0.3), d.shape, e.flags.contains(EntityFlags::BOSS)),
        None => (Color::srgb(0.6, 0.6, 0.6), 0.5, EnemyShape::Blob, false),
    };
    let base = kit.mat(color, Look::Matte);
    let (sphere, capsule, cube, cone, torus) = (
        kit.pal.sphere.clone(),
        kit.pal.capsule.clone(),
        kit.pal.cube.clone(),
        kit.pal.cone.clone(),
        kit.pal.torus.clone(),
    );
    let eye_color = if boss {
        Color::WHITE
    } else if e.flags.contains(EntityFlags::ELITE) {
        hex(GOLD)
    } else {
        hex("#FFB347")
    };
    let eye = kit.mat(eye_color, Look::Glow);
    // Eyes sit just outside each body surface (they show facing and read at a glance).
    let (body_mesh, body_tf, lift, eye_y, eye_z) = match shape {
        EnemyShape::Blob => {
            (&sphere, Transform::from_xyz(0.0, r * 0.8, 0.0).with_scale(Vec3::new(r, r * 0.8, r)), 0.0, r, -r * 0.95)
        }
        EnemyShape::Hound => (
            &cube,
            Transform::from_xyz(0.0, r * 0.6, 0.0).with_scale(Vec3::new(r * 1.2, r * 1.1, r * 2.3)),
            0.0,
            r * 0.85,
            -r * 1.2,
        ),
        EnemyShape::Wisp => (&sphere, Transform::from_scale(Vec3::splat(r * 0.85)), 0.8, 0.1, -r * 0.85),
        EnemyShape::Brute => (
            &cube,
            Transform::from_xyz(0.0, r * 0.95, 0.0).with_scale(Vec3::new(r * 1.8, r * 1.9, r * 1.3)),
            0.0,
            r * 1.5,
            -r * 0.72,
        ),
        EnemyShape::Spire => {
            (&cone, Transform::from_xyz(0.0, r * 1.5, 0.0).with_scale(Vec3::new(r, r * 3.0, r)), 0.0, r * 1.7, -r * 0.5)
        }
        EnemyShape::Crawler => (
            &sphere,
            Transform::from_xyz(0.0, r * 0.45, 0.0).with_scale(Vec3::new(r * 1.3, r * 0.45, r * 1.3)),
            0.0,
            r * 0.6,
            -r * 1.27,
        ),
        EnemyShape::Colossus => (
            &capsule,
            Transform::from_xyz(0.0, r * 1.6, 0.0).with_scale(Vec3::new(r * 2.0, r * 1.6, r * 1.6)),
            0.0,
            r * 2.4,
            -r * 0.86,
        ),
    };
    let body = kit.child(parent, body_mesh, base.clone(), body_tf);
    if shape != EnemyShape::Wisp {
        let ink = kit.mat(hex(INK), Look::Ink);
        let outline =
            kit.child(parent, body_mesh, ink, Transform { scale: body_tf.scale + Vec3::splat(0.1), ..body_tf });
        kit.commands.entity(outline).insert(NotShadowCaster);
    }
    let eye_size = (r * 0.17).max(0.07);
    for x in [-0.3, 0.3] {
        let e = kit.child(
            parent,
            &sphere,
            eye.clone(),
            Transform::from_xyz(x * r, eye_y, eye_z).with_scale(Vec3::splat(eye_size)),
        );
        kit.commands.entity(e).insert(NotShadowCaster);
    }
    // Silhouette accents: ember crowns on blobs, ears on hounds, mandibles on crawlers.
    let accent = kit.mat(lighten(mix(color, hex("#FFD27A"), 0.55), 1.1), Look::Glow);
    let dark = kit.mat(lighten(color, 0.55), Look::Matte);
    match shape {
        EnemyShape::Blob => {
            let f = kit.child(
                parent,
                &cone,
                accent,
                Transform::from_xyz(0.0, r * 1.75, 0.0).with_scale(Vec3::new(r * 0.32, r * 0.7, r * 0.32)),
            );
            kit.commands.entity(f).insert(NotShadowCaster);
        }
        EnemyShape::Hound => {
            for x in [-0.35, 0.35] {
                kit.child(
                    parent,
                    &cone,
                    dark.clone(),
                    Transform::from_xyz(x * r, r * 1.3, -r * 0.8).with_scale(Vec3::new(r * 0.2, r * 0.55, r * 0.2)),
                );
            }
        }
        EnemyShape::Crawler => {
            for x in [-0.4, 0.4] {
                kit.child(
                    parent,
                    &cone,
                    dark.clone(),
                    Transform {
                        translation: Vec3::new(x * r, r * 0.4, -r * 1.25),
                        rotation: Quat::from_rotation_x(-FRAC_PI_2),
                        scale: Vec3::new(r * 0.16, r * 0.6, r * 0.16),
                    },
                );
            }
        }
        EnemyShape::Brute => {
            for x in [-1.0, 1.0] {
                kit.child(
                    parent,
                    &sphere,
                    dark.clone(),
                    Transform::from_xyz(x * r * 0.95, r * 1.75, 0.0).with_scale(Vec3::splat(r * 0.42)),
                );
            }
        }
        _ => {}
    }
    if shape == EnemyShape::Wisp {
        let trail = kit.mat(hdr(color, 1.5).with_alpha(0.4), Look::Decal);
        kit.child(
            parent,
            &cone,
            trail,
            Transform {
                translation: Vec3::Z * r * 0.9,
                rotation: Quat::from_rotation_x(-FRAC_PI_2),
                scale: Vec3::new(r * 0.6, r * 1.6, r * 0.6),
            },
        );
    }
    if e.flags.contains(EntityFlags::ELITE) || boss {
        let ring = kit.mat(if boss { hdr(kit.pal.danger, 1.5) } else { hex(GOLD) }, Look::Metal);
        kit.child(
            parent,
            &torus,
            ring,
            Transform::from_xyz(0.0, 0.08 - lift, 0.0).with_scale(Vec3::new(r * 1.45, 1.5, r * 1.45)),
        );
    }
    if boss {
        let crown = kit.mat(hex(GOLD), Look::Metal);
        let top = body_tf.translation.y + body_tf.scale.y * 0.5 + 0.2;
        kit.child(
            parent,
            &torus,
            crown,
            Transform::from_xyz(0.0, top, 0.0).with_scale(Vec3::new(r * 0.55, 4.0, r * 0.55)),
        );
    }
    kit.shadow(parent, r * 1.2, lift);
    let mut v = Visual::new(e, color, r, lift);
    v.body = Some(body);
    v.base_mat = Some(base);
    v
}

fn spawn_telegraph(kit: &mut Kit, parent: Entity, e: &EntityView, shape: TeleShape) -> Visual {
    let ally = e.flags.contains(EntityFlags::ALLY);
    let col = if ally { hex(GOLD) } else { kit.pal.danger };
    let outline = kit.mat(hdr(col, 1.4).with_alpha(0.2), Look::Decal);
    let fill = kit.mat(hdr(col, 2.2).with_alpha(0.42), Look::Decal);
    let edge = kit.mat(hdr(col, 3.0).with_alpha(0.9), Look::Decal);
    let (disc, ring, quad) = (kit.pal.disc.clone(), kit.pal.ring.clone(), kit.pal.quad.clone());
    let z = |k: f32| Vec3::Z * k;
    let fill_ent = match gf_sim::bot::tele_shape(shape) {
        gf_content::TelegraphShape::Circle { radius } => {
            kit.child(parent, &disc, outline, Transform::from_scale(Vec3::splat(radius)));
            kit.child(
                parent,
                &ring,
                edge,
                Transform { translation: z(0.001), scale: Vec3::splat(radius), ..default() },
            );
            kit.child(parent, &disc, fill, Transform { translation: z(0.002), scale: Vec3::splat(0.001), ..default() })
        }
        gf_content::TelegraphShape::Line { length, width } => {
            kit.child(
                parent,
                &quad,
                outline,
                Transform {
                    translation: Vec3::new(0.0, length * 0.5, 0.0),
                    scale: Vec3::new(width, length, 1.0),
                    ..default()
                },
            );
            kit.child(
                parent,
                &quad,
                edge.clone(),
                Transform {
                    translation: Vec3::new(0.0, length, 0.001),
                    scale: Vec3::new(width, 0.1, 1.0),
                    ..default()
                },
            );
            for x in [-0.5, 0.5] {
                kit.child(
                    parent,
                    &quad,
                    edge.clone(),
                    Transform {
                        translation: Vec3::new(x * width, length * 0.5, 0.001),
                        scale: Vec3::new(0.06, length, 1.0),
                        ..default()
                    },
                );
            }
            kit.child(
                parent,
                &quad,
                fill,
                Transform { translation: z(0.002), scale: Vec3::new(width, 0.001, 1.0), ..default() },
            )
        }
        gf_content::TelegraphShape::Cone { range, angle_deg } => {
            let sector = kit.pal.sector(kit.meshes, angle_deg.clamp(1.0, 255.0) as u8);
            kit.child(parent, &sector, outline, Transform::from_scale(Vec3::splat(range)));
            kit.child(
                parent,
                &sector,
                fill,
                Transform { translation: z(0.002), scale: Vec3::splat(0.001), ..default() },
            )
        }
        gf_content::TelegraphShape::Ring { inner, outer } => {
            let annulus = kit.pal.annulus(kit.meshes, inner / outer.max(0.01));
            kit.child(parent, &annulus, outline, Transform::from_scale(Vec3::splat(outer)));
            kit.child(
                parent,
                &ring,
                edge.clone(),
                Transform { translation: z(0.001), scale: Vec3::splat(outer), ..default() },
            );
            kit.child(
                parent,
                &ring,
                edge,
                Transform { translation: z(0.001), scale: Vec3::splat(inner.max(0.05)), ..default() },
            );
            kit.child(
                parent,
                &annulus,
                fill,
                Transform { translation: z(0.002), scale: Vec3::splat(0.001), ..default() },
            )
        }
    };
    let mut v = Visual::new(e, col, 1.0, 0.02 + (e.id.0 % 8) as f32 * 0.003);
    v.parts[0] = Some(fill_ent);
    v
}

fn spawn_anvil(kit: &mut Kit, db: &ContentDb, parent: Entity, e: &EntityView) -> Visual {
    let iron = kit.mat(hex(IRON), Look::Metal);
    let bronze = kit.mat(hex(BRONZE), Look::Metal);
    let hot = kit.mat(hdr(hex("#FFB347"), 1.4), Look::Glow);
    let gold_ring = kit.mat(hdr(hex(GOLD), 2.2).with_alpha(0.85), Look::Decal);
    let gold_fill = kit.mat(hdr(hex(GOLD), 1.4).with_alpha(0.22), Look::Decal);
    let (cube, cone, ring, disc) =
        (kit.pal.cube.clone(), kit.pal.cone.clone(), kit.pal.ring.clone(), kit.pal.disc.clone());
    kit.child(parent, &cube, bronze.clone(), Transform::from_xyz(0.0, 0.08, 0.0).with_scale(Vec3::new(1.6, 0.16, 1.1)));
    kit.child(parent, &cube, iron.clone(), Transform::from_xyz(0.0, 0.4, 0.0).with_scale(Vec3::new(0.8, 0.5, 0.6)));
    let body = kit.child(
        parent,
        &cube,
        iron.clone(),
        Transform::from_xyz(0.0, 0.85, 0.0).with_scale(Vec3::new(1.9, 0.42, 0.9)),
    );
    kit.child(
        parent,
        &cone,
        iron,
        Transform {
            translation: Vec3::new(1.25, 0.9, 0.0),
            rotation: Quat::from_rotation_z(-FRAC_PI_2),
            scale: Vec3::new(0.3, 0.7, 0.3),
        },
    );
    let glow =
        kit.hidden_child(parent, &cube, hot, Transform::from_xyz(0.0, 1.07, 0.0).with_scale(Vec3::new(1.8, 0.05, 0.8)));
    let radius = db.game.anvil.radius;
    let ring_ent = kit.hidden_child(
        parent,
        &ring,
        gold_ring,
        Transform { translation: Vec3::Y * 0.025, rotation: flat(FRAC_PI_2), scale: Vec3::splat(radius) },
    );
    let fill = kit.hidden_child(
        parent,
        &disc,
        gold_fill,
        Transform { translation: Vec3::Y * 0.02, rotation: flat(FRAC_PI_2), scale: Vec3::splat(0.001) },
    );
    kit.shadow(parent, 1.2, 0.0);
    let mut v = Visual::new(e, hex(GOLD), radius, 0.0);
    v.body = Some(body);
    v.parts = [Some(fill), Some(ring_ent), Some(glow)];
    v
}

fn hit_flash(link: Res<Link>, index: Res<SceneIndex>, mut visuals: Query<&mut Visual>) {
    for ev in &link.fresh_events {
        if let GameEvent::Hit { target, .. } = *ev
            && let Some(ent) = index.entity(target)
            && let Ok(mut v) = visuals.get_mut(ent)
        {
            v.flash = 0.07;
        }
    }
}

fn animate_entities(
    time: Res<Time>,
    link: Res<Link>,
    mut q: Query<(&mut Visual, &mut Transform)>,
    mut parts: Query<&mut Transform, Without<Visual>>,
) {
    let rt = link.render_tick(time.elapsed_secs_f64());
    let dt = time.delta_secs();
    let t = time.elapsed_secs();
    let ease = 1.0 - (-18.0 * dt).exp();
    for (mut v, mut tf) in &mut q {
        v.flash = (v.flash - dt).max(0.0);
        let target = match v.motion {
            Some(m) => v.pos + m.vel.to_vec2() * ((rt - m.t0 as f64).max(0.0) as f32 * gf_core::SIM_DT),
            None => v.pos,
        };
        if v.motion.is_some() || v.fresh {
            v.shown = target;
            v.fresh = false;
        } else {
            let d = target - v.shown;
            v.shown += d * ease;
        }
        let phase = (v.id.0 % 97) as f32 * 0.37;
        match v.kind {
            EntityKind::Enemy { .. } => {
                let warn = v.flags.intersects(EntityFlags::WINDUP | EntityFlags::PRIMED | EntityFlags::CHARGING);
                let pulse = if warn { 1.0 + 0.08 * (t * 24.0).sin() } else { 1.0 };
                let squash = v.flash * 2.2;
                let bob = if v.lift > 0.0 { 0.12 * (t * 3.0 + phase).sin() } else { 0.0 };
                tf.translation = w3(v.shown, v.lift + bob);
                tf.rotation = yaw(v.facing);
                tf.scale =
                    Vec3::new(pulse * (1.0 + squash * 0.5), pulse * (1.0 - squash * 0.4), pulse * (1.0 + squash * 0.5));
            }
            EntityKind::Projectile { .. } | EntityKind::EnemyShot { .. } => {
                tf.translation = w3(v.shown, v.lift);
                tf.rotation = yaw(v.facing);
            }
            EntityKind::Telegraph { shape, windup_ticks, start, dir } => {
                tf.translation = w3(v.shown, v.lift);
                let d = u16_to_dir(dir);
                tf.rotation = flat(d.y.atan2(d.x));
                let p = ((rt - start as f64) / windup_ticks.max(1) as f64).clamp(0.0, 1.0) as f32;
                if let Some(fill) = v.parts[0]
                    && let Ok(mut ftf) = parts.get_mut(fill)
                {
                    match gf_sim::bot::tele_shape(shape) {
                        gf_content::TelegraphShape::Circle { radius } => {
                            ftf.scale = Vec3::splat((radius * p).max(0.001))
                        }
                        gf_content::TelegraphShape::Cone { range, .. } => {
                            ftf.scale = Vec3::splat((range * p).max(0.001))
                        }
                        gf_content::TelegraphShape::Ring { outer, .. } => {
                            ftf.scale = Vec3::splat((outer * p).max(0.001))
                        }
                        gf_content::TelegraphShape::Line { length, width } => {
                            ftf.scale = Vec3::new(width, (length * p).max(0.001), 1.0);
                            ftf.translation = Vec3::new(0.0, length * p * 0.5, 0.002);
                        }
                    }
                }
            }
            EntityKind::Hazard { .. } => {
                tf.translation = w3(v.shown, v.lift);
                tf.rotation = flat(FRAC_PI_2);
                if let Some(swirl) = v.parts[0]
                    && let Ok(mut stf) = parts.get_mut(swirl)
                {
                    stf.rotation = Quat::from_rotation_z(t * 2.5);
                }
            }
            EntityKind::Pickup { .. } => {
                tf.translation = w3(v.shown, v.lift + 0.12 * (t * 3.0 + phase).sin());
                tf.rotation = Quat::from_rotation_y(t * 1.7 + phase);
            }
            EntityKind::Blade { .. } => {
                tf.translation = w3(v.shown, v.lift);
                tf.rotation = Quat::from_rotation_y(t * 14.0 + phase);
            }
            EntityKind::Echo { .. } => {
                tf.translation = w3(v.shown, v.lift + 0.15 * (t * 2.0 + phase).sin());
            }
            EntityKind::Door { .. } => {
                tf.translation = w3(v.shown, 0.0);
                if let Some(panel) = v.body
                    && let Ok(mut ptf) = parts.get_mut(panel)
                {
                    let s = 1.0 + 0.04 * (t * 2.2 + phase).sin();
                    ptf.scale = Vec3::new(2.3 * s, 2.8 * s, 1.0);
                }
            }
            _ => tf.translation = w3(v.shown, v.lift),
        }
    }
}

fn status_color(bit: u8) -> Color {
    match bit {
        0 => element_color(gf_core::damage::DamageType::Flame),
        1 => element_color(gf_core::damage::DamageType::Storm),
        2 => element_color(gf_core::damage::DamageType::Void),
        3 => hex("#7BAE4A"),
        4 => hex("#E0312B"),
        _ => hex(GOLD),
    }
}

fn tint_entities(
    time: Res<Time>,
    mut pal: ResMut<Palette>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut q: Query<&mut Visual>,
    mut bodies: Query<&mut MeshMaterial3d<StandardMaterial>>,
) {
    let blink = (time.elapsed_secs() * 14.0).sin() > 0.0;
    for mut v in &mut q {
        if !matches!(v.kind, EntityKind::Enemy { .. }) {
            continue;
        }
        let tint = if v.flash > 0.0 {
            Tint::Flash
        } else if blink && v.flags.intersects(EntityFlags::WINDUP | EntityFlags::PRIMED | EntityFlags::CHARGING) {
            Tint::Warn
        } else if v.flags.contains(EntityFlags::FROZEN) {
            Tint::Frozen
        } else if v.flags.contains(EntityFlags::STUNNED) {
            Tint::Stunned
        } else if v.status != 0 {
            Tint::Status(v.status.trailing_zeros() as u8)
        } else {
            Tint::Base
        };
        if tint == v.tint {
            continue;
        }
        v.tint = tint;
        let (Some(body), Some(base)) = (v.body, v.base_mat.clone()) else { continue };
        let Ok(mut m) = bodies.get_mut(body) else { continue };
        let danger = pal.danger;
        m.0 = match tint {
            Tint::Base => base,
            Tint::Flash => pal.mat(&mut mats, Color::srgb(1.0, 0.96, 0.9), Look::Glow),
            Tint::Warn => pal.mat(&mut mats, mix(v.color, danger, 0.7), Look::Glow),
            Tint::Frozen => pal.mat(&mut mats, mix(v.color, hex("#BFE8FF"), 0.6), Look::Smolder),
            Tint::Stunned => pal.mat(&mut mats, mix(v.color, hex("#FFE27A"), 0.45), Look::Smolder),
            Tint::Status(bit) => pal.mat(&mut mats, mix(v.color, status_color(bit), 0.5), Look::Smolder),
        };
    }
}

/// Anvil state comes from the run view (one anvil per room): kindling ring + fill, hot glow.
fn animate_anvils(
    time: Res<Time>,
    link: Res<Link>,
    q: Query<&Visual>,
    mut parts: Query<(&mut Transform, &mut Visibility), Without<Visual>>,
) {
    let Some(world) = &link.latest else { return };
    let Some(anvil) = world.run.anvil else { return };
    let t = time.elapsed_secs();
    for v in &q {
        if !matches!(v.kind, EntityKind::Anvil) || v.id != anvil.id {
            continue;
        }
        let [fill, ring, glow] = v.parts;
        let show =
            |parts: &mut Query<(&mut Transform, &mut Visibility), Without<Visual>>, e: Option<Entity>, on: bool| {
                if let Some(e) = e
                    && let Ok((_, mut vis)) = parts.get_mut(e)
                {
                    *vis = if on { Visibility::Inherited } else { Visibility::Hidden };
                }
            };
        let kindling = anvil.state == AnvilState::Kindling;
        let hot = anvil.state == AnvilState::Hot;
        show(&mut parts, ring, kindling || hot || anvil.state == AnvilState::Dormant);
        show(&mut parts, fill, kindling);
        show(&mut parts, glow, hot);
        if let Some(f) = fill
            && let Ok((mut tf, _)) = parts.get_mut(f)
        {
            tf.scale = Vec3::splat((v.radius * anvil.progress).max(0.001));
        }
        if let Some(r) = ring
            && let Ok((mut tf, _)) = parts.get_mut(r)
        {
            let pulse = if anvil.contested { 1.0 + 0.03 * (t * 10.0).sin() } else { 1.0 };
            tf.scale = Vec3::splat(v.radius * pulse);
        }
    }
}

// ───────────────────────────── players ─────────────────────────────

fn spawn_rig(kit: &mut Kit, db: &ContentDb, p: &PlayerView) -> Entity {
    let color = db.characters.try_get(p.character).map_or(Color::srgb(0.8, 0.8, 0.8), |c| hex(&c.color));
    let pc = kit.pal.player(p.slot);
    let r = p.radius.max(0.3);
    let root = kit.commands.spawn((Transform::from_translation(w3(p.mover.pos, 0.0)), Visibility::default())).id();
    let body_mat = kit.mat(color, Look::Matte);
    let ghost_mat = kit.mat(color.with_alpha(0.35), Look::Ghost);
    let head = kit.mat(lighten(color, 1.3), Look::Matte);
    let gold = kit.mat(hex(GOLD), Look::Metal);
    let brass = kit.mat(hex("#B8A27A"), Look::Metal);
    let muzzle = kit.mat(element_color(gf_core::damage::DamageType::Kinetic), Look::Glow);
    let ring_mat = kit.mat(hdr(pc, 2.4).with_alpha(0.95), Look::Decal);
    let chevron_mat = kit.mat(hdr(pc, 2.0).with_alpha(0.6), Look::Decal);
    let shield_mat = kit.mat(hdr(hex("#BFEFFF"), 1.2).with_alpha(0.16), Look::Ghost);
    let aura_mat = kit.mat(hdr(hex(GOLD), 2.5).with_alpha(0.5), Look::Decal);
    let tether_mat = kit.mat(hdr(pc, 2.5).with_alpha(0.8), Look::Decal);
    let (capsule, sphere, torus, cube, ring) = (
        kit.pal.capsule.clone(),
        kit.pal.sphere.clone(),
        kit.pal.torus.clone(),
        kit.pal.cube.clone(),
        kit.pal.ring.clone(),
    );
    let chevron_mesh = kit.pal.sector(kit.meshes, 50);
    kit.shadow(root, r * 1.3, 0.0);
    let ring_tf = Transform { translation: Vec3::Y * 0.03, rotation: flat(FRAC_PI_2), scale: Vec3::splat(r * 2.3) };
    kit.child(root, &ring, ring_mat, ring_tf);
    let chevron = kit.child(
        root,
        &chevron_mesh,
        chevron_mat,
        Transform { translation: Vec3::Y * 0.035, scale: Vec3::splat(r * 3.4), ..default() },
    );
    let body = kit.child(
        root,
        &capsule,
        body_mat.clone(),
        Transform::from_xyz(0.0, 0.85, 0.0).with_scale(Vec3::new(r * 2.0, 0.85, r * 2.0)),
    );
    kit.child(root, &sphere, head, Transform::from_xyz(0.0, 1.82, 0.0).with_scale(Vec3::splat(r * 0.62)));
    let ink = kit.mat(hex(INK), Look::Ink);
    let o1 = kit.child(
        root,
        &capsule,
        ink.clone(),
        Transform::from_xyz(0.0, 0.85, 0.0).with_scale(Vec3::new(r * 2.0 + 0.12, 0.91, r * 2.0 + 0.12)),
    );
    let o2 =
        kit.child(root, &sphere, ink, Transform::from_xyz(0.0, 1.82, 0.0).with_scale(Vec3::splat(r * 0.62 + 0.06)));
    kit.commands.entity(o1).insert(NotShadowCaster);
    kit.commands.entity(o2).insert(NotShadowCaster);
    kit.child(root, &torus, gold, Transform::from_xyz(0.0, 0.95, 0.0).with_scale(Vec3::new(r * 1.1, 1.6, r * 1.1)));
    let pivot = kit.commands.spawn((Transform::from_xyz(0.0, 1.05, 0.0), Visibility::default(), ChildOf(root))).id();
    kit.child(pivot, &cube, brass, Transform::from_xyz(r * 0.75, 0.0, -0.55).with_scale(Vec3::new(0.15, 0.15, 0.95)));
    kit.child(pivot, &sphere, muzzle, Transform::from_xyz(r * 0.75, 0.0, -1.05).with_scale(Vec3::splat(0.09)));
    let shield = kit.hidden_child(
        root,
        &sphere,
        shield_mat,
        Transform::from_xyz(0.0, 0.95, 0.0).with_scale(Vec3::splat(r * 2.5)),
    );
    let aura = kit.hidden_child(
        root,
        &ring,
        aura_mat,
        Transform { translation: Vec3::Y * 0.05, rotation: flat(FRAC_PI_2), scale: Vec3::splat(r * 3.2) },
    );
    let tether = kit.hidden_child(
        root,
        &ring,
        tether_mat,
        Transform { translation: Vec3::Y * 0.04, rotation: flat(FRAC_PI_2), scale: Vec3::splat(2.2) },
    );
    kit.commands.entity(root).insert(PlayerRig {
        slot: p.slot,
        shown: p.mover.pos,
        fresh: true,
        pivot,
        chevron,
        body,
        shield,
        aura,
        tether,
        body_mat,
        ghost_mat,
        downed: false,
    });
    root
}

#[allow(clippy::too_many_arguments)]
fn sync_players(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pred: Res<Prediction>,
    input: Res<InputState>,
    mut pal: ResMut<Palette>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut index: ResMut<SceneIndex>,
    mut rigs: Query<(&mut PlayerRig, &mut Transform, &mut Visibility)>,
    mut parts: Query<(&mut Transform, &mut Visibility), Without<PlayerRig>>,
    mut bodies: Query<&mut MeshMaterial3d<StandardMaterial>>,
) {
    let Some(world) = &link.latest else { return };
    let dt = time.delta_secs();
    let t = time.elapsed_secs();
    let ease = 1.0 - (-20.0 * dt).exp();
    // Spawn / despawn rigs by slot.
    for slot in 0..4u8 {
        let present = world.players.iter().find(|p| p.slot == slot);
        match (present, index.players[slot as usize]) {
            (Some(p), None) => {
                let mut kit = Kit { commands: &mut commands, pal: &mut pal, mats: &mut mats, meshes: &mut meshes };
                index.players[slot as usize] = Some(spawn_rig(&mut kit, &cfg.content, p));
            }
            (None, Some(e)) => {
                commands.entity(e).despawn();
                index.players[slot as usize] = None;
            }
            _ => {}
        }
    }
    for p in &world.players {
        let Some(ent) = index.players[p.slot as usize] else { continue };
        let Ok((mut rig, mut tf, mut vis)) = rigs.get_mut(ent) else { continue };
        let is_me = link.slot == Some(p.slot);
        let target = match (is_me, pred.state) {
            (true, Some(s)) => s.pos + pred.error,
            _ => p.mover.pos,
        };
        if is_me || rig.fresh {
            rig.shown = target;
            rig.fresh = false;
        } else {
            let d = target - rig.shown;
            rig.shown += d * ease;
        }
        tf.translation = w3(rig.shown, p.height);
        tf.scale = Vec3::splat(p.scale.max(0.2));
        let reforging = matches!(p.life, LifeState::Reforging { .. });
        *vis = if reforging { Visibility::Hidden } else { Visibility::Inherited };
        // Aim: the local MANUAL player sees their own stick/mouse with zero latency.
        let aim = if is_me && input.aim_mode == AimMode::Manual { input.aim_dir } else { u16_to_dir(p.aim) };
        let angle = aim.y.atan2(aim.x);
        if let Ok((mut ptf, _)) = parts.get_mut(rig.pivot) {
            ptf.rotation = yaw(angle);
        }
        if let Ok((mut ctf, _)) = parts.get_mut(rig.chevron) {
            ctf.rotation = flat(angle);
        }
        let downed = matches!(p.life, LifeState::Downed { .. });
        if downed != rig.downed {
            rig.downed = downed;
            if let Ok(mut m) = bodies.get_mut(rig.body) {
                m.0 = if downed { rig.ghost_mat.clone() } else { rig.body_mat.clone() };
            }
        }
        if let Ok((_, mut v)) = parts.get_mut(rig.shield) {
            *v = if p.shield > 0.0 || p.flags.contains(PlayerFlags::SHIELDED) {
                Visibility::Inherited
            } else {
                Visibility::Hidden
            };
        }
        if let Ok((mut atf, mut v)) = parts.get_mut(rig.aura) {
            let on = p.flags.intersects(PlayerFlags::OVERDRIVE | PlayerFlags::AVATAR);
            *v = if on { Visibility::Inherited } else { Visibility::Hidden };
            atf.rotation = flat(t * 1.5);
        }
        if let Ok((mut ttf, mut v)) = parts.get_mut(rig.tether) {
            if let LifeState::Downed { progress, .. } = p.life {
                *v = Visibility::Inherited;
                ttf.scale = Vec3::splat(0.6 + 1.8 * (1.0 - progress.clamp(0.0, 1.0)));
            } else {
                *v = Visibility::Hidden;
            }
        }
    }
}

// ───────────────────────────── markers ─────────────────────────────

fn spawn_markers(mut commands: Commands, mut pal: ResMut<Palette>, mut mats: ResMut<Assets<StandardMaterial>>) {
    let ring = pal.ring.clone();
    let quad = pal.quad.clone();
    let danger = pal.danger;
    let target_mat = pal.mat(&mut mats, hdr(mix(danger, hex(GOLD), 0.5), 2.5).with_alpha(0.9), Look::Decal);
    let line_mat = pal.mat(&mut mats, Color::srgba(1.0, 0.95, 0.85, 0.22), Look::Decal);
    commands.spawn((
        TargetMarker,
        Mesh3d(ring),
        MeshMaterial3d(target_mat),
        Transform { rotation: flat(FRAC_PI_2), ..default() },
        Visibility::Hidden,
    ));
    commands.spawn((AimLine, Mesh3d(quad), MeshMaterial3d(line_mat), Transform::default(), Visibility::Hidden));
}

#[allow(clippy::type_complexity)]
fn update_markers(
    time: Res<Time>,
    link: Res<Link>,
    input: Res<InputState>,
    index: Res<SceneIndex>,
    visuals: Query<&Visual>,
    rigs: Query<&PlayerRig>,
    mut target: Query<(&mut Transform, &mut Visibility), (With<TargetMarker>, Without<AimLine>)>,
    mut line: Query<(&mut Transform, &mut Visibility), (With<AimLine>, Without<TargetMarker>)>,
) {
    let me = link.me();
    let (Ok((mut ttf, mut tvis)), Ok((mut ltf, mut lvis))) = (target.single_mut(), line.single_mut()) else { return };
    *tvis = Visibility::Hidden;
    *lvis = Visibility::Hidden;
    let Some(me) = me else { return };
    if !me.life.is_alive() {
        return;
    }
    if let Some(id) = me.target
        && let Some(v) = index.entity(id).and_then(|e| visuals.get(e).ok())
    {
        *tvis = Visibility::Inherited;
        let spin = time.elapsed_secs() * 2.0;
        ttf.translation = w3(v.shown, 0.04);
        ttf.rotation = flat(spin);
        ttf.scale = Vec3::splat(v.radius * 1.5 + 0.25 + 0.05 * (spin * 3.0).sin());
    }
    // Aim line for MANUAL / ASSISTED (the skill modes show where the shot goes).
    if input.aim_mode != AimMode::Auto
        && let Some(rig) = index.players[me.slot as usize].and_then(|e| rigs.get(e).ok())
    {
        let dir = if input.aim_mode == AimMode::Manual { input.aim_dir } else { u16_to_dir(me.aim) };
        let len = input.aim_dist.clamp(1.5, 14.0);
        let angle = dir.y.atan2(dir.x);
        *lvis = Visibility::Inherited;
        ltf.translation = w3(rig.shown + dir * (len * 0.5 + 0.6), 0.045);
        ltf.rotation = flat(angle);
        ltf.scale = Vec3::new(0.07, len, 1.0);
    }
}
