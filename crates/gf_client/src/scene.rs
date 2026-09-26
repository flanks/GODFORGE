//! Replicated world → render entities (§12 art direction on greybox primitives).
//!
//! * Room geometry rebuilds whenever `room_serial` changes (ground, walls, obstacles, decor).
//! * Replicated entities are matched by `NetId`: spawned on first sight, updated from every
//!   snapshot, despawned when they leave it.
//! * Straight-line movers extrapolate from their motion descriptor at the fractional render tick;
//!   everything else eases toward its latest authoritative position.
//! * The local player renders at its predicted position (see `net::Prediction`).

use crate::camera::{KeyLight, w3};
use crate::input::InputState;
use crate::materials::{AbyssMaterial, BiomeLook, FloorMaterial, ToonMaterial, XRayMaterial, xray};
use crate::net::{CurrentRoom, Link, Prediction};
use crate::palette::{
    Look, Mat, Palette, element_color, flat, hdr, hex, lighten, mix, poi_kind_color, rarity_color, yaw,
};
use crate::world::{self, EnvLights, WorldStores};
use crate::{ClientConfig, ClientSet};
use gf_content::schema::{MapLayout, PoiSite};
use gf_content::{ContentDb, EnemyShape};
use gf_core::aim::AimMode;
use gf_core::ids::NetId;
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_engine::client::{NotShadowCaster, SystemParam};
use gf_engine::prelude::*;
use gf_net::quant::{u8_to_dir, u8_to_frac, u16_to_dir};
use gf_net::*;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, FRAC_PI_4};

const PROJECTILE_HEIGHT: f32 = 0.9;
/// Hit flash length and the shortest time between two flashes of one body.
const FLASH_TIME: f32 = 0.07;
const FLASH_COOLDOWN: f32 = 0.2;
/// POI beacon shaft height: tall enough that, seen by the fixed 55° camera, a shaft standing up
/// to ~28 u beyond the bottom edge of the view still reaches into it.
const BEACON_H: f32 = 40.0;
/// World width of an interaction ring's band (every radius reads with the same line weight).
const RING_BAND: f32 = 0.3;
/// Interaction rings are the POI language, never the danger language: one gold for every kind.
const RING_GOLD: &str = "#E3B95C";
const GOLD: &str = "#FFC940";
const BRONZE: &str = "#7E5E36";
const IRON: &str = "#3B3633";
const INK: &str = "#140C08";

#[derive(Component)]
pub struct RoomGeometry;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Tint {
    Base,
    Flash,
    /// Bosses and elites: a warm lift of their own colour instead of the white-hot swap.
    SoftFlash,
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
    /// Hit-flash cooldown: a stream of hits (beams, DoTs, multi-hits) re-arms the flash at most
    /// every [`FLASH_COOLDOWN`] s, so a big body never locks white.
    flash_cool: f32,
    pub lift: f32,
    fresh: bool,
    body: Option<Entity>,
    /// Animated children: telegraph fill / hold progress, ring, anvil hot glow, dim beacon (an
    /// incomplete objective), bright beacon (a live one).
    parts: [Option<Entity>; 5],
    tint: Tint,
    base_mat: Option<Handle<ToonMaterial>>,
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
            flash_cool: 0.0,
            lift,
            fresh: true,
            body: None,
            parts: [None; 5],
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
    body_mat: Handle<ToonMaterial>,
    ghost_mat: Handle<ToonMaterial>,
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
    room_generation: Option<u32>,
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

/// Each slot's x-ray silhouette material (heroes seen through whatever hides them).
#[derive(Resource)]
struct XRayMats([Handle<XRayMaterial>; 4]);

fn setup_xray(mut commands: Commands, pal: Res<Palette>, mut xrays: ResMut<Assets<XRayMaterial>>) {
    let m = |slot: u8, xrays: &mut Assets<XRayMaterial>| xrays.add(xray(pal.player(slot).with_alpha(0.55)));
    let mats = [m(0, &mut xrays), m(1, &mut xrays), m(2, &mut xrays), m(3, &mut xrays)];
    commands.insert_resource(XRayMats(mats));
}

pub fn build(app: &mut App) {
    app.init_resource::<SceneIndex>().add_systems(Startup, (spawn_markers, setup_xray)).add_systems(
        Update,
        (
            rebuild_room,
            sync_entities,
            hit_flash,
            animate_entities,
            cap_ally_fields,
            tint_entities,
            animate_anvils,
            sync_players,
            update_markers,
        )
            .chain()
            .in_set(ClientSet::Scene),
    );
}

/// The mesh and material stores every spawner needs.
#[derive(SystemParam)]
pub struct Stores<'w> {
    pub meshes: ResMut<'w, Assets<Mesh>>,
    pub mats: ResMut<'w, Assets<StandardMaterial>>,
    pub toons: ResMut<'w, Assets<ToonMaterial>>,
}

/// Spawning helper bundling the asset stores.
struct Kit<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    pal: &'a mut Palette,
    mats: &'a mut Assets<StandardMaterial>,
    toons: &'a mut Assets<ToonMaterial>,
    meshes: &'a mut Assets<Mesh>,
}

impl<'a, 'w, 's> Kit<'a, 'w, 's> {
    fn new(commands: &'a mut Commands<'w, 's>, pal: &'a mut Palette, stores: &'a mut Stores) -> Self {
        Kit { commands, pal, mats: stores.mats.as_mut(), toons: stores.toons.as_mut(), meshes: stores.meshes.as_mut() }
    }

    fn mat(&mut self, c: Color, look: Look) -> Mat {
        self.pal.look(self.mats, self.toons, c, look)
    }

    fn child(&mut self, parent: Entity, mesh: &Handle<Mesh>, mat: Mat, tf: Transform) -> Entity {
        let mut e = self.commands.spawn((Mesh3d(mesh.clone()), tf, ChildOf(parent)));
        mat.insert(&mut e);
        e.id()
    }

    fn hidden_child(&mut self, parent: Entity, mesh: &Handle<Mesh>, mat: Mat, tf: Transform) -> Entity {
        let mut e = self.commands.spawn((Mesh3d(mesh.clone()), tf, Visibility::Hidden, ChildOf(parent)));
        mat.insert(&mut e);
        e.id()
    }

    /// Soft contact shadow (no shadow maps: cheap and readable at 400 enemies).
    fn shadow(&mut self, parent: Entity, radius: f32, lift: f32) {
        let m = Mat::Std(self.pal.blob_shadow(self.mats, 0.6));
        let disc = self.pal.disc.clone();
        let e = self.child(
            parent,
            &disc,
            m,
            Transform {
                translation: Vec3::new(0.0, 0.012 - lift, 0.0),
                rotation: flat(FRAC_PI_2),
                scale: Vec3::splat(radius * 1.25),
            },
        );
        self.commands.entity(e).insert(NotShadowCaster);
    }
}

// ───────────────────────────── room ─────────────────────────────

#[allow(clippy::too_many_arguments)]
fn rebuild_room(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    current: Res<CurrentRoom>,
    pal: Res<Palette>,
    mut stores: Stores,
    mut floors: ResMut<Assets<FloorMaterial>>,
    mut abysses: ResMut<Assets<AbyssMaterial>>,
    mut index: ResMut<SceneIndex>,
    mut ambient: ResMut<GlobalAmbientLight>,
    mut lights: ResMut<EnvLights>,
    mut keys: Query<&mut DirectionalLight, With<KeyLight>>,
    old: Query<Entity, With<RoomGeometry>>,
) {
    let Some(world) = &link.latest else { return };
    if current.generation == 0 || index.room_generation == Some(current.generation) {
        return;
    }
    index.room_generation = Some(current.generation);
    for e in &old {
        commands.entity(e).despawn();
    }
    let room = current.def.as_ref();
    let biome = cfg.content.biomes.try_get(world.run.biome);
    let colors = biome.map(|b| [hex(&b.palette[0]), hex(&b.palette[1]), hex(&b.palette[2])]).unwrap_or([
        hex("#2B1B15"),
        hex("#FF8A2A"),
        hex("#140D0A"),
    ]);
    let look = BiomeLook::new(biome.map_or("", |b| b.key.as_str()), colors);
    // Lighting: warm key against a cool ambient (saturated cool shadows, warm light pools). A
    // biome map is a dusk field: a cooler, dimmer key and a lifted violet fill, so the braziers,
    // the lava and the lit roads make the pools of warmth and the shadows never read as holes.
    let on_map = room_is_map(&current);
    ambient.color = look.ambient;
    ambient.brightness = look.ambient_brightness * if on_map { 2.2 } else { 1.0 };
    for mut key in &mut keys {
        key.color = if on_map { mix(look.key, hex("#C4CCE6"), 0.4) } else { look.key };
        key.illuminance = look.key_lux * if on_map { 0.8 } else { 1.0 };
    }
    // Visual variety from the replicated room seed (authored rooms: their key).
    let seed = match world.run.room_seed {
        0 => room.key.bytes().fold(0x811C_9DC5u32, |h, b| (h ^ b as u32).wrapping_mul(0x0100_0193)),
        s => s,
    };
    // Rooms and biome maps both go through the world builder (env kit, merged chunks).
    let world_stores = WorldStores {
        meshes: stores.meshes.as_mut(),
        mats: stores.mats.as_mut(),
        toons: stores.toons.as_mut(),
        floors: floors.as_mut(),
        abysses: abysses.as_mut(),
    };
    world::build(&mut commands, world_stores, &pal, &cfg.content, room, &look, seed, &mut lights);
}

fn room_is_map(current: &CurrentRoom) -> bool {
    current.def.map.is_some()
}

// ───────────────────────────── replicated entities ─────────────────────────────

#[allow(clippy::too_many_arguments)]
fn sync_entities(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut pal: ResMut<Palette>,
    mut stores: Stores,
    mut index: ResMut<SceneIndex>,
    room: Res<CurrentRoom>,
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
    let mut kit = Kit::new(&mut commands, &mut pal, &mut stores);
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
        let ent = spawn_visual(&mut kit, &cfg.content, room.def.map.as_deref(), e, me, ally_alpha);
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

fn spawn_visual(
    kit: &mut Kit,
    db: &ContentDb,
    map: Option<&MapLayout>,
    e: &EntityView,
    me: Option<u8>,
    ally_alpha: f32,
) -> Entity {
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
            // Readability budget: player-made zones stay quiet (no bloom, low alpha) so enemy
            // danger and the characters read first; at 4P they can cover a third of the screen.
            let (alpha, edge_alpha, fill_gain, edge_gain) =
                if ally { (alpha * 0.35, 0.3, 1.0, 1.1) } else { (alpha, 0.75, 1.3, 2.6) };
            let fill = kit.mat(hdr(c, fill_gain).with_alpha(alpha), Look::Decal);
            let edge = kit.mat(hdr(c, edge_gain).with_alpha(edge_alpha), Look::Decal);
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
                let swirl_mat =
                    kit.mat(hdr(c, if ally { 1.2 } else { 3.0 }).with_alpha(if ally { 0.3 } else { 0.5 }), Look::Decal);
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
        EntityKind::Anvil => spawn_anvil(kit, db, parent, e, false),
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
        EntityKind::Poi { index } => {
            let site = map.and_then(|m| m.pois.get(index as usize));
            match site {
                Some(s) if s.kind == PoiKind::Anvil => spawn_anvil(kit, db, parent, e, true),
                _ => spawn_poi(kit, db, parent, e, site),
            }
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
    let base = kit.mat(color, Look::Foe);
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
        // The ink hull grows with the body, so a big foe keeps a bold outline against the ground.
        let hull = Vec3::splat(0.1 + 0.07 * r);
        let outline = kit.child(parent, body_mesh, ink, Transform { scale: body_tf.scale + hull, ..body_tf });
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
    let dark = kit.mat(lighten(color, 0.55), Look::Foe);
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
    v.base_mat = base.toon();
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

/// A flat interaction ring of `radius` whose band is [`RING_BAND`] wide at any radius.
fn ring_mesh(kit: &mut Kit, radius: f32) -> Handle<Mesh> {
    kit.pal.annulus(kit.meshes, (1.0 - RING_BAND / radius.max(0.5)).clamp(0.4, 0.97))
}

/// The dim (an objective still to do) and bright (live) beacon shafts of a POI, both hidden.
fn beacons(kit: &mut Kit, parent: Entity, c: Color) -> [Entity; 2] {
    let cyl = kit.pal.cylinder.clone();
    let dim = kit.mat(hdr(c, 1.2).with_alpha(0.12), Look::Decal);
    let bright = kit.mat(hdr(c, 1.5).with_alpha(0.2), Look::Decal);
    let shaft = |r: f32| Transform::from_xyz(0.0, BEACON_H * 0.5, 0.0).with_scale(Vec3::new(r, BEACON_H, r));
    let a = kit.hidden_child(parent, &cyl, dim, shaft(0.35));
    let b = kit.hidden_child(parent, &cyl, bright, shaft(0.42));
    kit.commands.entity(a).insert(NotShadowCaster);
    kit.commands.entity(b).insert(NotShadowCaster);
    [a, b]
}

/// An anvil: the legacy room anvil, or a map Anvil POI (`poi`), which stands larger on a stepped
/// plinth and carries a beacon so it reads from across the map.
fn spawn_anvil(kit: &mut Kit, db: &ContentDb, parent: Entity, e: &EntityView, poi: bool) -> Visual {
    let iron = kit.mat(hex(IRON), Look::Metal);
    let bronze = kit.mat(hex(BRONZE), Look::Metal);
    let stone = kit.mat(hex("#4A403A"), Look::Matte);
    let hot = kit.mat(hdr(hex("#FFB347"), 1.4), Look::Glow);
    let gold_ring = kit.mat(hex(RING_GOLD).with_alpha(0.55), Look::Decal);
    let gold_fill = kit.mat(hdr(hex(GOLD), 1.2).with_alpha(0.2), Look::Decal);
    let (cube, cone, disc) = (kit.pal.cube.clone(), kit.pal.cone.clone(), kit.pal.disc.clone());
    // The Forge is the game's core verb: on a map the anvil is the size of a hero and a half.
    let (s, base) = if poi { (1.75, 0.5) } else { (1.0, 0.0) };
    if poi {
        kit.child(
            parent,
            &cube,
            stone.clone(),
            Transform::from_xyz(0.0, 0.15, 0.0).with_scale(Vec3::new(4.4, 0.3, 3.4)),
        );
        kit.child(parent, &cube, stone, Transform::from_xyz(0.0, 0.4, 0.0).with_scale(Vec3::new(3.5, 0.22, 2.5)));
    }
    let at = |x: f32, y: f32, z: f32| Vec3::new(x * s, base + y * s, z * s);
    kit.child(
        parent,
        &cube,
        bronze.clone(),
        Transform::from_translation(at(0.0, 0.08, 0.0)).with_scale(Vec3::new(1.6, 0.16, 1.1) * s),
    );
    kit.child(
        parent,
        &cube,
        iron.clone(),
        Transform::from_translation(at(0.0, 0.4, 0.0)).with_scale(Vec3::new(0.8, 0.5, 0.6) * s),
    );
    let body = kit.child(
        parent,
        &cube,
        iron.clone(),
        Transform::from_translation(at(0.0, 0.85, 0.0)).with_scale(Vec3::new(1.9, 0.42, 0.9) * s),
    );
    kit.child(
        parent,
        &cone,
        iron,
        Transform {
            translation: at(1.25, 0.9, 0.0),
            rotation: Quat::from_rotation_z(-FRAC_PI_2),
            scale: Vec3::new(0.3, 0.7, 0.3) * s,
        },
    );
    let glow = kit.hidden_child(
        parent,
        &cube,
        hot,
        Transform::from_translation(at(0.0, 1.07, 0.0)).with_scale(Vec3::new(1.8, 0.05, 0.8) * s),
    );
    let radius = db.game.anvil.radius;
    let ring = ring_mesh(kit, radius);
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
    kit.shadow(parent, 1.2 * s, 0.0);
    let mut v = Visual::new(e, hex(GOLD), radius, 0.0);
    v.body = Some(body);
    v.parts = [Some(fill), Some(ring_ent), Some(glow), None, None];
    if poi {
        let [dim, bright] = beacons(kit, parent, poi_color(db, None, PoiKind::Anvil));
        v.parts[3] = Some(dim);
        v.parts[4] = Some(bright);
    }
    v
}

/// Beacon and marker colour of a POI kind (a shrine takes its god's colour).
pub fn poi_color(db: &ContentDb, god: Option<u8>, kind: PoiKind) -> Color {
    match (kind, god.and_then(|g| db.gods.try_get(g as u16))) {
        (PoiKind::Shrine, Some(g)) => hex(&g.color),
        _ => poi_kind_color(kind),
    }
}

/// What a POI is called on markers and prompts ("Shrine of Pyra").
pub fn poi_label(db: &ContentDb, site: &PoiSite) -> String {
    match (site.kind, site.god.and_then(|g| db.gods.try_get(g as u16))) {
        (PoiKind::Shrine, Some(g)) => format!("Shrine of {}", g.name),
        (PoiKind::Gate, _) => "Boss Gate".into(),
        (k, _) => k.name().into(),
    }
}

/// A POI's own silhouette at its heart (the clearing's set piece stands around it, from worldgen):
/// a shrine's altar with a fire in its god's colour, a reliquary's gilded chest, a vein's crystal
/// lode, a spring's basin, a watchfire's pyre, a lair's skull stakes, the Warlord's war totem, the
/// gate's seal pedestal. Plus the gold interaction ring with its hold fill (hold POIs only: a Lair
/// or the Warlord is an arena, not a ring) and its beacons.
fn spawn_poi(kit: &mut Kit, db: &ContentDb, parent: Entity, e: &EntityView, site: Option<&PoiSite>) -> Visual {
    let kind = site.map_or(PoiKind::Shrine, |s| s.kind);
    let c = site.map_or(hex(GOLD), |s| poi_color(db, s.god, s.kind));
    let radius = site.map_or(4.0, |s| s.radius).max(1.0);
    let stone = kit.mat(hex("#4A403A"), Look::Matte);
    let dark_stone = kit.mat(hex("#2E2622"), Look::Matte);
    let bronze = kit.mat(hex(BRONZE), Look::Metal);
    let gold = kit.mat(hex(GOLD), Look::Metal);
    let bone = kit.mat(hex("#D8CDB4"), Look::Matte);
    let glow = kit.mat(hdr(c, 1.6), Look::Glow);
    let ink = kit.mat(hex(INK), Look::Ink);
    let ring_mat = kit.mat(hex(RING_GOLD).with_alpha(0.45), Look::Decal);
    let fill_mat = kit.mat(hex(RING_GOLD).with_alpha(0.18), Look::Decal);
    let (cyl, sphere, disc, cube, cone) = (
        kit.pal.cylinder.clone(),
        kit.pal.sphere.clone(),
        kit.pal.disc.clone(),
        kit.pal.cube.clone(),
        kit.pal.cone.clone(),
    );
    // A piece with an inverted-hull ink outline (the painterly silhouette every prop carries).
    let inked = |kit: &mut Kit, mesh: &Handle<Mesh>, m: Mat, tf: Transform| -> Entity {
        let e = kit.child(parent, mesh, m, tf);
        let hull = kit.child(parent, mesh, ink.clone(), Transform { scale: tf.scale + Vec3::splat(0.09), ..tf });
        kit.commands.entity(hull).insert(NotShadowCaster);
        e
    };
    let at = |x: f32, y: f32, z: f32| Transform::from_xyz(x, y, z);
    let body = match kind {
        PoiKind::Shrine => {
            let b = inked(kit, &cube, stone.clone(), at(0.0, 0.45, 0.0).with_scale(Vec3::new(1.5, 0.9, 1.0)));
            kit.child(parent, &cube, bronze.clone(), at(0.0, 0.96, 0.0).with_scale(Vec3::new(1.7, 0.12, 1.2)));
            kit.child(parent, &cyl, bronze.clone(), at(0.0, 1.15, 0.0).with_scale(Vec3::new(0.48, 0.26, 0.48)));
            let f = kit.child(parent, &cone, glow.clone(), at(0.0, 1.75, 0.0).with_scale(Vec3::new(0.34, 0.95, 0.34)));
            kit.commands.entity(f).insert(NotShadowCaster);
            b
        }
        PoiKind::Reliquary => {
            kit.child(parent, &cube, dark_stone.clone(), at(0.0, 0.22, 0.0).with_scale(Vec3::new(1.6, 0.44, 1.2)));
            let b = inked(kit, &cube, gold.clone(), at(0.0, 0.78, 0.0).with_scale(Vec3::new(1.15, 0.62, 0.72)));
            let lid = Transform {
                translation: Vec3::new(0.0, 1.1, 0.0),
                rotation: Quat::from_rotation_z(FRAC_PI_2),
                scale: Vec3::new(0.36, 1.15, 0.36),
            };
            inked(kit, &cyl, gold.clone(), lid);
            let seam =
                kit.child(parent, &cube, glow.clone(), at(0.0, 1.1, 0.0).with_scale(Vec3::new(1.18, 0.06, 0.76)));
            kit.commands.entity(seam).insert(NotShadowCaster);
            b
        }
        PoiKind::Vein => {
            kit.child(parent, &sphere, dark_stone.clone(), at(0.0, 0.1, 0.0).with_scale(Vec3::new(1.2, 0.45, 1.0)));
            let mut first = None;
            for (x, z, h, r, lean) in
                [(0.0f32, 0.0f32, 2.2f32, 0.4f32, 0.0f32), (0.55, 0.25, 1.5, 0.3, -0.35), (-0.5, 0.3, 1.2, 0.26, 0.4)]
            {
                let tf = Transform {
                    translation: Vec3::new(x, h * 0.5, z),
                    rotation: Quat::from_rotation_z(lean) * Quat::from_rotation_x(lean * 0.4),
                    scale: Vec3::new(r, h, r),
                };
                let e = inked(kit, &cone, glow.clone(), tf);
                first.get_or_insert(e);
            }
            first.unwrap_or(parent)
        }
        PoiKind::Spring => {
            let b = inked(kit, &cyl, stone.clone(), at(0.0, 0.25, 0.0).with_scale(Vec3::new(1.3, 0.5, 1.3)));
            let water = kit.child(
                parent,
                &disc,
                glow.clone(),
                Transform { translation: Vec3::Y * 0.52, rotation: flat(FRAC_PI_2), scale: Vec3::splat(1.08) },
            );
            kit.commands.entity(water).insert(NotShadowCaster);
            b
        }
        PoiKind::Watchfire => {
            let wood = kit.mat(hex("#4A3020"), Look::Matte);
            for (k, y) in [0.15f32, 0.45, 0.75].into_iter().enumerate() {
                let r = if k % 2 == 0 { 0.0 } else { FRAC_PI_2 };
                let tf = Transform {
                    translation: Vec3::Y * y,
                    rotation: Quat::from_rotation_y(r),
                    scale: Vec3::new(1.5, 0.22, 0.22),
                };
                kit.child(parent, &cube, wood.clone(), tf);
            }
            let f = kit.child(parent, &cone, glow.clone(), at(0.0, 1.5, 0.0).with_scale(Vec3::new(0.5, 1.2, 0.5)));
            kit.commands.entity(f).insert(NotShadowCaster);
            f
        }
        PoiKind::Lair => {
            let mut first = None;
            for k in 0..3 {
                let a = k as f32 * std::f32::consts::TAU / 3.0;
                let (x, z) = (a.cos() * 0.9, a.sin() * 0.9);
                let h = 1.9 + 0.3 * k as f32;
                let e = inked(kit, &cyl, bone.clone(), at(x, h * 0.5, z).with_scale(Vec3::new(0.08, h, 0.08)));
                inked(kit, &sphere, bone.clone(), at(x, h + 0.2, z).with_scale(Vec3::new(0.24, 0.26, 0.27)));
                first.get_or_insert(e);
            }
            first.unwrap_or(parent)
        }
        PoiKind::Warlord => {
            let cloth = kit.mat(mix(c, hex("#2A0E0A"), 0.35), Look::Matte);
            let b = inked(kit, &cyl, bronze.clone(), at(0.0, 2.2, 0.0).with_scale(Vec3::new(0.1, 4.4, 0.1)));
            kit.child(parent, &cube, bronze.clone(), at(0.0, 4.1, 0.0).with_scale(Vec3::new(1.6, 0.1, 0.1)));
            inked(kit, &cube, cloth, at(0.0, 3.2, 0.06).with_scale(Vec3::new(1.4, 1.7, 0.05)));
            inked(kit, &sphere, bone.clone(), at(0.0, 4.55, 0.0).with_scale(Vec3::new(0.3, 0.32, 0.34)));
            b
        }
        PoiKind::Gate | PoiKind::Anvil => {
            let b = inked(kit, &cube, stone.clone(), at(0.0, 0.5, 0.0).with_scale(Vec3::new(1.2, 1.0, 1.2)));
            kit.child(parent, &cube, bronze.clone(), at(0.0, 1.04, 0.0).with_scale(Vec3::new(1.4, 0.1, 1.4)));
            let orb = kit.child(parent, &sphere, glow.clone(), at(0.0, 1.5, 0.0).with_scale(Vec3::splat(0.36)));
            kit.commands.entity(orb).insert(NotShadowCaster);
            b
        }
    };
    let arena = matches!(kind, PoiKind::Lair | PoiKind::Warlord);
    let (ring_ent, fill) = if arena {
        (None, None)
    } else {
        let ring = ring_mesh(kit, radius);
        let r = kit.hidden_child(
            parent,
            &ring,
            ring_mat,
            Transform { translation: Vec3::Y * 0.025, rotation: flat(FRAC_PI_2), scale: Vec3::splat(radius) },
        );
        let f = kit.hidden_child(
            parent,
            &disc,
            fill_mat,
            Transform { translation: Vec3::Y * 0.02, rotation: flat(FRAC_PI_2), scale: Vec3::splat(0.001) },
        );
        (Some(r), Some(f))
    };
    let [dim, bright] = beacons(kit, parent, c);
    kit.shadow(parent, 1.3, 0.0);
    let mut v = Visual::new(e, c, radius, 0.0);
    v.body = Some(body);
    v.parts = [fill, ring_ent, None, Some(dim), Some(bright)];
    v
}

fn hit_flash(link: Res<Link>, index: Res<SceneIndex>, mut visuals: Query<&mut Visual>) {
    for ev in &link.fresh_events {
        if let GameEvent::Hit { target, .. } = *ev
            && let Some(ent) = index.entity(target)
            && let Ok(mut v) = visuals.get_mut(ent)
            && v.flash_cool <= 0.0
        {
            v.flash = FLASH_TIME;
            v.flash_cool = FLASH_COOLDOWN;
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
        v.flash_cool = (v.flash_cool - dt).max(0.0);
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
                // Big bodies barely squash: a hit reads on their rim, not as a jelly wobble.
                let squash = v.flash * if v.radius > 1.0 { 0.8 } else { 2.2 };
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

/// Ally ground fields drawn at once: at 4P peak the players' zones could cover a third of the
/// screen; the nearest ones to the local player stay, the rest hide (presentation only).
const ALLY_FIELD_CAP: usize = 10;

fn cap_ally_fields(link: Res<Link>, mut q: Query<(&Visual, &mut Visibility)>) {
    let me = link.me().map_or(Vec2::ZERO, |p| p.mover.pos);
    let ally_field = |v: &Visual| matches!(v.kind, EntityKind::Hazard { .. }) && v.flags.contains(EntityFlags::ALLY);
    let mut near: Vec<f32> =
        q.iter().filter(|(v, _)| ally_field(v)).map(|(v, _)| v.shown.distance_squared(me)).collect();
    // Past the cap, only fields as near as the cap-th nearest one stay.
    let cut = if near.len() > ALLY_FIELD_CAP {
        near.sort_by(|a, b| a.total_cmp(b));
        near[ALLY_FIELD_CAP - 1]
    } else {
        f32::INFINITY
    };
    for (v, mut vis) in &mut q {
        if !ally_field(v) {
            continue;
        }
        let want = if v.shown.distance_squared(me) <= cut { Visibility::Inherited } else { Visibility::Hidden };
        if *vis != want {
            *vis = want;
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
    mut toons: ResMut<Assets<ToonMaterial>>,
    mut q: Query<&mut Visual>,
    mut bodies: Query<&mut MeshMaterial3d<ToonMaterial>>,
) {
    let blink = (time.elapsed_secs() * 14.0).sin() > 0.0;
    for mut v in &mut q {
        if !matches!(v.kind, EntityKind::Enemy { .. }) {
            continue;
        }
        let big = v.flags.intersects(EntityFlags::BOSS | EntityFlags::ELITE) || v.radius > 1.0;
        let tint = if v.flash > 0.0 {
            if big { Tint::SoftFlash } else { Tint::Flash }
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
            Tint::Flash => pal.toon(&mut toons, Color::srgb(1.0, 0.96, 0.9), Look::Hot),
            // Big bodies take a lot of hits: a slight warm lift reads as impact without washing
            // out the silhouette.
            Tint::SoftFlash => pal.toon(&mut toons, lighten(mix(v.color, hex("#FFE6C0"), 0.18), 1.06), Look::Foe),
            Tint::Warn => pal.toon(&mut toons, mix(v.color, danger, 0.7), Look::Hot),
            Tint::Frozen => pal.toon(&mut toons, mix(v.color, hex("#BFE8FF"), 0.6), Look::Smolder),
            Tint::Stunned => pal.toon(&mut toons, mix(v.color, hex("#FFE27A"), 0.45), Look::Smolder),
            Tint::Status(bit) => pal.toon(&mut toons, mix(v.color, status_color(bit), 0.5), Look::Smolder),
        };
    }
}

/// Anvils and POIs animate from their own replicated state (`status`, `hp` = progress and the
/// CONTESTED flag): the ring while it can be used, the hold fill while active, the hot plate while
/// an anvil's forge window is open. Every objective still to do (a Seal POI or the gate) keeps a
/// dim beacon shaft, turned bright while it is live, so the map always shows where to go.
fn animate_anvils(
    time: Res<Time>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    q: Query<&Visual>,
    mut parts: Query<(&mut Transform, &mut Visibility), Without<Visual>>,
) {
    let t = time.elapsed_secs();
    let me = link.me().map(|p| p.mover.pos);
    for v in &q {
        // Standing at a POI, its beacon would only wall off the screen.
        let here = me.is_some_and(|m| m.distance(v.pos) < v.radius + 7.0);
        let (ring_on, fill_on, glow_on, dim_on, bright_on) = match v.kind {
            EntityKind::Anvil => {
                let s = AnvilState::from_u8(v.status);
                (s != AnvilState::Spent, s == AnvilState::Kindling, s == AnvilState::Hot, false, false)
            }
            EntityKind::Poi { index } => {
                let s = PoiState::from_u8(v.status);
                let site = room.def.map.as_ref().and_then(|m| m.pois.get(index as usize));
                let anvil = site.map(|p| p.kind) == Some(PoiKind::Anvil);
                let live = matches!(s, PoiState::Hot | PoiState::Open | PoiState::Gathering)
                    || (!anvil && s == PoiState::Active);
                let objective = site.is_some_and(|p| p.seals > 0 || p.kind == PoiKind::Gate);
                let todo = objective && s != PoiState::Done;
                // A Lair or the Warlord in a fight needs no beacon: its guards are the marker.
                let fight =
                    s == PoiState::Active && site.is_some_and(|p| matches!(p.kind, PoiKind::Lair | PoiKind::Warlord));
                let (dim, bright) = if fight { (false, false) } else { (todo && !live, live) };
                (s != PoiState::Done, s == PoiState::Active, anvil && s == PoiState::Hot, dim, bright)
            }
            _ => continue,
        };
        let [fill, ring, glow, dim, bright] = v.parts;
        let show =
            |parts: &mut Query<(&mut Transform, &mut Visibility), Without<Visual>>, e: Option<Entity>, on: bool| {
                if let Some(e) = e
                    && let Ok((_, mut vis)) = parts.get_mut(e)
                {
                    let want = if on { Visibility::Inherited } else { Visibility::Hidden };
                    if *vis != want {
                        *vis = want;
                    }
                }
            };
        show(&mut parts, ring, ring_on);
        show(&mut parts, fill, fill_on);
        show(&mut parts, glow, glow_on);
        show(&mut parts, dim, dim_on && !here);
        show(&mut parts, bright, bright_on && !here);
        if let Some(f) = fill
            && let Ok((mut tf, _)) = parts.get_mut(f)
        {
            tf.scale = Vec3::splat((v.radius * v.hp).max(0.001));
        }
        if let Some(r) = ring
            && let Ok((mut tf, _)) = parts.get_mut(r)
        {
            let contested = v.flags.contains(EntityFlags::CONTESTED);
            let pulse = if contested { 1.0 + 0.03 * (t * 10.0).sin() } else { 1.0 };
            tf.scale = Vec3::splat(v.radius * pulse);
        }
        if let Some(b) = bright
            && let Ok((mut tf, _)) = parts.get_mut(b)
        {
            let w = 0.42 * (1.0 + 0.12 * (t * 3.0).sin());
            tf.scale = Vec3::new(w, BEACON_H, w);
        }
    }
}

// ───────────────────────────── players ─────────────────────────────

fn spawn_rig(kit: &mut Kit, db: &ContentDb, p: &PlayerView, xray_mat: &Handle<XRayMaterial>) -> Entity {
    let color = db.characters.try_get(p.character).map_or(Color::srgb(0.8, 0.8, 0.8), |c| hex(&c.color));
    let pc = kit.pal.player(p.slot);
    let r = p.radius.max(0.3);
    let root = kit.commands.spawn((Transform::from_translation(w3(p.mover.pos, 0.0)), Visibility::default())).id();
    let body_mat = kit.mat(color, Look::Hero(p.slot));
    let ghost_mat = kit.mat(color.with_alpha(0.35), Look::Ghost);
    let head = kit.mat(lighten(color, 1.3), Look::Hero(p.slot));
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
    let (Some(body_mat), Some(ghost_mat)) = (body_mat.toon(), ghost_mat.toon()) else {
        unreachable!("hero and ghost looks are toon materials")
    };
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
    // The x-ray silhouette: the hero in their colour wherever a foe or a monument hides them
    // (raised a hair so the floor never counts as hiding the feet).
    for (mesh, tf) in [
        (&capsule, Transform::from_xyz(0.0, 0.93, 0.0).with_scale(Vec3::new(r * 2.0 + 0.04, 0.84, r * 2.0 + 0.04))),
        (&sphere, Transform::from_xyz(0.0, 1.82, 0.0).with_scale(Vec3::splat(r * 0.62 + 0.02))),
    ] {
        kit.commands.spawn((
            Mesh3d(mesh.clone()),
            MeshMaterial3d(xray_mat.clone()),
            tf,
            NotShadowCaster,
            ChildOf(root),
        ));
    }
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
    mut stores: Stores,
    mut index: ResMut<SceneIndex>,
    xrays: Res<XRayMats>,
    mut rigs: Query<(&mut PlayerRig, &mut Transform, &mut Visibility)>,
    mut parts: Query<(&mut Transform, &mut Visibility), Without<PlayerRig>>,
    mut bodies: Query<&mut MeshMaterial3d<ToonMaterial>>,
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
                let mut kit = Kit::new(&mut commands, &mut pal, &mut stores);
                index.players[slot as usize] = Some(spawn_rig(&mut kit, &cfg.content, p, &xrays.0[slot as usize]));
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
