//! Painted zones (`zone.wesl`): hazards, ability and synergy fields and telegraphs drawn as one
//! animated shader quad each instead of flat discs and rings (VFX_STYLE §13-16).
//!
//! * [`dress`] gives every new hazard, telegraph, barricade and turret proxy its look, the moment
//!   `scene.rs` spawns it: a zone quad under the parent (so it rides the proxy's transform, its
//!   visibility and despawn), the zone's identity from the cast log (Firestorm, Heaven's Verdict,
//!   Binding Hex, ...) and its opening beat.
//! * Telegraphs keep their red-white language, drawn above every VFX layer
//!   ([`crate::fx::TELEGRAPH_BIAS`]); their fill progress runs on the GPU clock, so a telegraph
//!   costs no per-frame uploads. [`resolve`] plays the resolve punch and a flash of the shape.
//! * Enemy zones get a second quad with the red-white hem drawn above every player effect.

use super::kit::{self, Hero, ZoneLook};
use super::live::CastLog;
use crate::ClientConfig;
use crate::camera::w3;
use crate::fx::api::faction_ramp;
use crate::fx::{Fx, Owner, Ramp, TELEGRAPH_BIAS};
use crate::net::Link;
use crate::palette::{flat, hex};
use crate::scene::Visual;
use gf_core::damage::DamageType;
use gf_core::ids::NetId;
use gf_engine::bevy::mesh::MeshVertexBufferLayoutRef;
use gf_engine::bevy::pbr::{MaterialPipeline, MaterialPipelineKey};
use gf_engine::bevy::render::render_resource::{
    AsBindGroup, RenderPipelineDescriptor, ShaderType, SpecializedMeshPipelineError,
};
use gf_engine::bevy::shader::ShaderRef;
use gf_engine::client::{NotShadowCaster, embedded_asset};
use gf_engine::prelude::*;
use gf_net::{EntityFlags, EntityKind, GameEvent, HazardKind};
use std::collections::HashMap;

pub const SHADER: &str = "embedded://gf_client/vfx/zone.wesl";

/// Draw order of player zones: with the ground VFX, under shadows and every effect.
const ZONE_BIAS: f32 = -120.0;
/// Draw order of enemy zone hems: above every player effect (danger), under telegraphs.
const DANGER_HEM_BIAS: f32 = 950.0;

const FLAG_ALLY: f32 = 1.0;
const FLAG_HEM_ONLY: f32 = 2.0;
const FLAG_NO_HEM: f32 = 4.0;
const FLAG_RESOLVE: f32 = 8.0;

/// GPU layout of `ZoneParams` in `zone.wesl` (field order matters).
#[derive(Clone, Copy, Debug, Default, PartialEq, ShaderType, Reflect)]
pub struct ZoneParams {
    /// x = mode, y = element / variant, z = flags, w = seed.
    pub mode: Vec4,
    /// The quad in the local plane: centre (x, y), size (z, w).
    pub quad: Vec4,
    /// x = radius / length, y = width / inner / half angle, z = hem width.
    pub shape: Vec4,
    /// x = the GPU clock at progress 0, y = duration, z = interior alpha, w = gain.
    pub timing: Vec4,
    pub ink: Vec4,
    pub deep: Vec4,
    pub body: Vec4,
    pub light: Vec4,
    pub hem: Vec4,
    pub alt: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct ZoneMaterial {
    #[uniform(0)]
    pub params: ZoneParams,
    #[reflect(ignore)]
    pub bias: f32,
}

impl Material for ZoneMaterial {
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }

    fn alpha_mode(&self) -> AlphaMode {
        AlphaMode::Premultiplied
    }

    fn depth_bias(&self) -> f32 {
        self.bias
    }

    fn enable_prepass() -> bool {
        false
    }

    fn enable_shadows() -> bool {
        false
    }

    fn specialize(
        _pipeline: &MaterialPipeline,
        descriptor: &mut RenderPipelineDescriptor,
        _layout: &MeshVertexBufferLayoutRef,
        _key: MaterialPipelineKey<Self>,
    ) -> Result<(), SpecializedMeshPipelineError> {
        descriptor.primitive.cull_mode = None;
        Ok(())
    }
}

/// The unit quad every zone draws on.
#[derive(Resource)]
pub struct ZoneMesh(pub Handle<Mesh>);

/// A zone's live identity and ambience state (on the proxy entity).
#[derive(Component, Clone, Debug)]
pub struct ZoneFx {
    pub look: ZoneLook,
    pub ramp: Ramp,
    pub radius: f32,
    pub owner: Owner,
    pub seed: f32,
    pub strike: f32,
}

/// A resolve flash or a scar: a zone quad with a lifetime.
#[derive(Component)]
pub struct ZoneGhost {
    pub until: f32,
}

/// The shape of every live telegraph, kept for its resolve punch (the proxy is gone by then).
#[derive(Resource, Default)]
pub struct TeleCache {
    pub live: HashMap<NetId, Tele>,
}

#[derive(Clone, Copy, Debug)]
pub struct Tele {
    pub at: Vec2,
    pub angle: f32,
    pub lift: f32,
    pub shape: gf_content::TelegraphShape,
    pub ally: bool,
}

pub fn build(app: &mut App) {
    embedded_asset!(app, "zone.wesl");
    app.add_plugins(MaterialPlugin::<ZoneMaterial>::default()).init_resource::<TeleCache>().add_systems(Startup, setup);
}

fn setup(mut commands: Commands, mut meshes: ResMut<Assets<Mesh>>) {
    commands.insert_resource(ZoneMesh(meshes.add(Rectangle::new(1.0, 1.0))));
}

fn lin(c: Color) -> Vec4 {
    let l = c.to_linear();
    Vec4::new(l.red, l.green, l.blue, 1.0)
}

/// The five tones of a ramp as linear colours (ink, deep, body, light).
fn tones(ramp: Ramp) -> [Vec4; 4] {
    let t = ramp.tones();
    [lin(hex(t[0])), lin(hex(t[1])), lin(hex(t[2])), lin(hex(t[3]))]
}

fn element_variant(e: DamageType) -> f32 {
    match e {
        DamageType::Kinetic => 0.0,
        DamageType::Flame => 1.0,
        DamageType::Storm => 2.0,
        DamageType::Void => 3.0,
        DamageType::Plague => 4.0,
        DamageType::Radiant => 5.0,
    }
}

fn seed_of(id: NetId) -> f32 {
    let mut x = id.0.wrapping_mul(0x9E37_79B9);
    x ^= x >> 15;
    (x % 1000) as f32 / 1000.0
}

/// A zone quad's params before the colours.
fn base(mode: f32, variant: f32, flags: f32, seed: f32, quad: Vec4, shape: Vec4, timing: Vec4) -> ZoneParams {
    ZoneParams { mode: Vec4::new(mode, variant, flags, seed), quad, shape, timing, ..default() }
}

fn with_ramp(mut p: ZoneParams, ramp: Ramp) -> ZoneParams {
    let [ink, deep, body, light] = tones(ramp);
    p.ink = ink;
    p.deep = deep;
    p.body = body;
    p.light = light;
    p
}

/// The telegraph colours: danger red and white, or gold for player-side telegraphs.
fn tele_colors(mut p: ZoneParams, ally: bool, danger: Color) -> ZoneParams {
    if ally {
        p.body = lin(hex("#FFC940"));
        p.light = lin(hex("#FFF4C8"));
    } else {
        p.body = lin(danger);
        p.light = lin(Color::WHITE);
    }
    p.ink = lin(hex("#1A0606"));
    p
}

/// The local quad (centre, size) and shape vector of a telegraph.
fn tele_quad(shape: gf_content::TelegraphShape) -> (f32, Vec4, Vec4) {
    use gf_content::TelegraphShape as T;
    let m = 0.45;
    match shape {
        T::Circle { radius } => {
            (20.0, Vec4::new(0.0, 0.0, 2.0 * (radius + m), 2.0 * (radius + m)), Vec4::new(radius, 0.0, 0.0, 0.0))
        }
        T::Line { length, width } => {
            (21.0, Vec4::new(0.0, length * 0.5, width + 2.0 * m, length + 2.0 * m), Vec4::new(length, width, 0.0, 0.0))
        }
        T::Cone { range, angle_deg } => (
            22.0,
            Vec4::new(0.0, 0.0, 2.0 * (range + m), 2.0 * (range + m)),
            Vec4::new(range, (angle_deg * 0.5).to_radians(), 0.0, 0.0),
        ),
        T::Ring { inner, outer } => {
            (23.0, Vec4::new(0.0, 0.0, 2.0 * (outer + m), 2.0 * (outer + m)), Vec4::new(outer, inner, 0.0, 0.0))
        }
    }
}

fn quad_transform(quad: Vec4, z: f32) -> Transform {
    Transform { translation: Vec3::new(quad.x, quad.y, z), scale: Vec3::new(quad.z, quad.w, 1.0), ..default() }
}

/// Zones in the cast log: which ability or synergy made this field, and whose it is.
fn identify(log: &CastLog, now: f32, at: Vec2, radius: f32, element: DamageType, me: Option<u8>) -> (ZoneLook, Owner) {
    let near = |p: Vec2, d: f32| p.distance(at) <= d;
    for s in log.synergies.iter().rev() {
        if now - s.t < 1.0 && near(s.at, 1.2) {
            match s.key.as_str() {
                "firestorm" => return (ZoneLook::Firestorm, s.owner),
                "entropy_bloom" => return (ZoneLook::EntropyBloom, s.owner),
                _ => {}
            }
        }
    }
    let close = |r: f32| (radius - r).abs() < 0.35;
    for c in log.casts.iter().rev() {
        if now - c.t > 1.0 {
            continue;
        }
        let owner = Owner::of_slot(c.slot, me);
        let look = match (c.hero, c.which) {
            (Hero::Selene, 2) if close(5.0) => Some(ZoneLook::Verdict),
            (Hero::Thessaly, 1) if close(3.5) => Some(ZoneLook::BindingHex),
            (Hero::Epoch, 0) if close(4.0) => Some(ZoneLook::StillField),
            (Hero::Mirren, 0) if close(1.6) => Some(ZoneLook::Decoy),
            (Hero::Brax, 0) if close(2.8) => Some(ZoneLook::Geysers),
            (Hero::Ossian, 1) if close(3.6) => Some(ZoneLook::Mortar),
            _ => None,
        };
        if let Some(l) = look {
            return (l, owner);
        }
    }
    // Signatures when the cast was missed (a late joiner, a lost event).
    let look = match element {
        DamageType::Storm if close(5.0) => ZoneLook::Verdict,
        DamageType::Storm if close(3.0) => ZoneLook::Firestorm,
        DamageType::Void if close(3.2) => ZoneLook::EntropyBloom,
        _ => ZoneLook::Field,
    };
    (look, Owner::Ally)
}

/// Dress new proxies: zone quads for hazards and telegraphs, the rise of barricades and turrets.
#[allow(clippy::too_many_arguments)]
pub fn dress(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    log: Res<CastLog>,
    mesh: Option<Res<ZoneMesh>>,
    mut mats: ResMut<Assets<ZoneMaterial>>,
    added: Query<(Entity, &Visual), Added<Visual>>,
    visuals: Query<&Visual>,
    mut fx: Fx,
) {
    let Some(mesh) = mesh else { return };
    if added.is_empty() {
        return;
    }
    let gpu_now = time.elapsed_secs_wrapped();
    let now = time.elapsed_secs();
    let me = link.slot;
    let rt = link.render_tick(time.elapsed_secs_f64());
    let danger = hex(&cfg.content.game.telegraph_color);
    let enemies_in = |at: Vec2, r: f32| -> Vec<Vec3> {
        visuals
            .iter()
            .filter(|v| matches!(v.kind, EntityKind::Enemy { .. }) && v.shown.distance(at) <= r + v.radius)
            .map(|v| w3(v.shown, v.hit_height))
            .collect()
    };
    for (entity, v) in &added {
        match v.kind {
            EntityKind::Telegraph { shape, windup_ticks, start, .. } => {
                let ally = v.flags.contains(EntityFlags::ALLY);
                let shape = gf_sim::bot::tele_shape(shape);
                let dur = windup_ticks.max(1) as f32 * gf_core::SIM_DT;
                let p = ((rt - start as f64) / windup_ticks.max(1) as f64).clamp(0.0, 1.0) as f32;
                let (mode, quad, shape_v) = tele_quad(shape);
                let flags = if ally { FLAG_ALLY } else { 0.0 };
                let params = tele_colors(
                    base(mode, 0.0, flags, seed_of(v.id), quad, shape_v, Vec4::new(gpu_now - p * dur, dur, 1.0, 1.0)),
                    ally,
                    danger,
                );
                let mat = mats.add(ZoneMaterial { params, bias: TELEGRAPH_BIAS });
                let child = commands
                    .spawn((Mesh3d(mesh.0.clone()), MeshMaterial3d(mat), quad_transform(quad, 0.0), NotShadowCaster))
                    .id();
                commands.entity(entity).add_child(child);
                // A player-side circle from Skyhook Mortar: the shell lobs onto it.
                if ally
                    && let gf_content::TelegraphShape::Circle { radius } = shape
                    && let Some(c) =
                        log.casts.iter().rev().find(|c| now - c.t < 0.5 && c.hero == Hero::Ossian && c.which == 1)
                    && (radius - 3.0).abs() < 0.5
                {
                    let owner = Owner::of_slot(c.slot, me);
                    kit::mortar_lob(&mut fx, w3(c.at, 0.0), w3(v.shown, 0.0), dur * (1.0 - p), owner);
                }
            }
            EntityKind::Hazard { kind, element, radius_q } => {
                let r = (radius_q as f32 / 32.0).max(0.3);
                let ally = v.flags.contains(EntityFlags::ALLY);
                let (look, owner) = if ally {
                    match kind {
                        HazardKind::Field => identify(&log, now, v.shown, r, element, me),
                        HazardKind::Well => (ZoneLook::Well, Owner::Ally),
                        HazardKind::Pool => (ZoneLook::Pool, Owner::Ally),
                        HazardKind::Puddle => (ZoneLook::Puddle, Owner::Ally),
                        HazardKind::Trail => (ZoneLook::Trail, Owner::Ally),
                        HazardKind::Ground => {
                            let o = log
                                .casts
                                .iter()
                                .rev()
                                .find(|c| now - c.t < 0.5 && c.which == 2 && c.at.distance(v.shown) < 1.5)
                                .map_or(Owner::Ally, |c| Owner::of_slot(c.slot, me));
                            (ZoneLook::Ground, o)
                        }
                    }
                } else {
                    let look = match kind {
                        HazardKind::Well => ZoneLook::Well,
                        HazardKind::Pool => ZoneLook::Pool,
                        HazardKind::Puddle => ZoneLook::Puddle,
                        HazardKind::Trail => ZoneLook::Trail,
                        HazardKind::Ground => ZoneLook::Ground,
                        HazardKind::Field => ZoneLook::Field,
                    };
                    (look, Owner::Enemy)
                };
                let ramp = match look {
                    ZoneLook::Firestorm | ZoneLook::Verdict => Ramp::Storm,
                    ZoneLook::EntropyBloom => Ramp::Void,
                    ZoneLook::BindingHex => Ramp::Void,
                    ZoneLook::StillField => Ramp::Time,
                    ZoneLook::Decoy => Ramp::ZoneGold,
                    ZoneLook::Geysers | ZoneLook::Mortar => Ramp::Flame,
                    _ => Ramp::of(element),
                };
                let alt = match look {
                    ZoneLook::Firestorm => lin(hex("#FF9A3A")),
                    ZoneLook::EntropyBloom => lin(hex("#9BE84A")),
                    ZoneLook::BindingHex => lin(hex("#9BE84A")),
                    _ => lin(Ramp::ZoneGold.body()),
                };
                let seed = seed_of(v.id);
                let size = 2.0 * r * 1.12 + 0.4;
                let quad = Vec4::new(0.0, 0.0, size, size);
                let set_piece = look.set_piece();
                // Readability budget: player zones stay quiet (their interiors ≤ 0.35 of a
                // danger fill); set pieces carry a little more; enemies' read fully.
                let (alpha, gain, hem_a) = match owner {
                    Owner::Enemy => (0.85, 1.2, 0.95),
                    Owner::Mine => (if set_piece { 0.85 } else { 0.5 }, 1.15, 0.85),
                    _ => (if set_piece { 0.55 } else { 0.32 }, 1.0, 0.5),
                };
                let hem_w = if owner == Owner::Enemy { 0.09 } else { (0.05 + 0.012 * r).min(0.12) };
                let dur = match look {
                    ZoneLook::EntropyBloom => 4.0,
                    ZoneLook::Firestorm => 3.0,
                    _ => 3.0,
                };
                let mut params = with_ramp(
                    base(
                        look.mode(),
                        element_variant(element),
                        if ally { FLAG_ALLY } else { FLAG_NO_HEM },
                        seed,
                        quad,
                        Vec4::new(r, 0.0, hem_w, 0.0),
                        Vec4::new(gpu_now, dur, alpha, gain),
                    ),
                    ramp,
                );
                params.alt = alt;
                params.hem = if ally { lin(Ramp::ZoneGold.body()).with_w(hem_a) } else { lin(danger).with_w(hem_a) };
                let fill = mats.add(ZoneMaterial { params, bias: ZONE_BIAS });
                let child = commands
                    .spawn((Mesh3d(mesh.0.clone()), MeshMaterial3d(fill), quad_transform(quad, 0.0), NotShadowCaster))
                    .id();
                commands.entity(entity).add_child(child);
                if !ally {
                    // The red-white hem on the danger layer.
                    let mut hem = params;
                    hem.mode.z = FLAG_HEM_ONLY;
                    let hem_mat = mats.add(ZoneMaterial { params: hem, bias: DANGER_HEM_BIAS });
                    let child = commands
                        .spawn((
                            Mesh3d(mesh.0.clone()),
                            MeshMaterial3d(hem_mat),
                            quad_transform(quad, 0.001),
                            NotShadowCaster,
                        ))
                        .id();
                    commands.entity(entity).add_child(child);
                }
                let inside = if matches!(look, ZoneLook::BindingHex) { enemies_in(v.shown, r) } else { Vec::new() };
                kit::zone_open(&mut fx, look, w3(v.shown, 0.0), r, ramp, owner, &inside);
                commands.entity(entity).insert(ZoneFx { look, ramp, radius: r, owner, seed, strike: 0.15 });
            }
            EntityKind::Barricade { half_len_q, dir } => {
                // The wall runs along its replicated direction (scene.rs yaws its long side there).
                let d = gf_net::quant::u16_to_dir(dir);
                let along = w3(d, 0.0).normalize_or(Vec3::X);
                let owner = log
                    .casts
                    .iter()
                    .rev()
                    .find(|c| now - c.t < 2.0 && c.hero == Hero::Valdris && c.which == 0)
                    .map_or(Owner::Ally, |c| Owner::of_slot(c.slot, me));
                kit::barricade_rise(&mut fx, w3(v.shown, 0.0), along, half_len_q as f32 / 32.0, owner);
            }
            EntityKind::Turret { owner } => {
                kit::turret_rise(&mut fx, w3(v.shown, 0.0), Owner::of_slot(owner % 4, me));
            }
            _ => {}
        }
    }
}

/// Keep the shape of every live telegraph for its resolve punch.
pub fn cache_telegraphs(mut cache: ResMut<TeleCache>, visuals: Query<&Visual>) {
    cache.live.clear();
    for v in &visuals {
        if let EntityKind::Telegraph { shape, dir, .. } = v.kind {
            let d = gf_net::quant::u16_to_dir(dir);
            cache.live.insert(
                v.id,
                Tele {
                    at: v.shown,
                    angle: d.y.atan2(d.x),
                    lift: v.lift,
                    shape: gf_sim::bot::tele_shape(shape),
                    ally: v.flags.contains(EntityFlags::ALLY),
                },
            );
        }
    }
}

/// `TelegraphResolved`: a flash of the whole shape and the resolve punch in the attacker's
/// faction style (VFX_STYLE §15.1). Player-side telegraphs (Skyhook, the decoy) only flash.
#[allow(clippy::too_many_arguments)]
pub fn resolve(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    cache: Res<TeleCache>,
    mesh: Option<Res<ZoneMesh>>,
    mut mats: ResMut<Assets<ZoneMaterial>>,
    visuals: Query<&Visual>,
    ghosts: Query<(Entity, &ZoneGhost)>,
    mut fx: Fx,
) {
    let now = time.elapsed_secs();
    for (e, g) in &ghosts {
        if now >= g.until {
            commands.entity(e).despawn();
        }
    }
    let Some(mesh) = mesh else { return };
    let danger = hex(&cfg.content.game.telegraph_color);
    let gpu_now = time.elapsed_secs_wrapped();
    for ev in &link.fresh_events {
        let GameEvent::TelegraphResolved { id } = *ev else { continue };
        let Some(t) = cache.live.get(&id) else { continue };
        let (mode, quad, shape_v) = tele_quad(t.shape);
        let flags = FLAG_RESOLVE + if t.ally { FLAG_ALLY } else { 0.0 };
        let params = tele_colors(
            base(mode, 0.0, flags, seed_of(id), quad, shape_v, Vec4::new(gpu_now, 0.18, 1.0, 1.0)),
            t.ally,
            danger,
        );
        let rot = flat(t.angle);
        let local = quad_transform(quad, 0.0);
        let tf = Transform {
            translation: w3(t.at, t.lift + 0.01) + rot * local.translation,
            rotation: rot,
            scale: local.scale,
        };
        let mat = mats.add(ZoneMaterial { params, bias: TELEGRAPH_BIAS });
        commands.spawn((
            Mesh3d(mesh.0.clone()),
            MeshMaterial3d(mat),
            tf,
            NotShadowCaster,
            ZoneGhost { until: now + 0.25 },
        ));
        if t.ally {
            continue;
        }
        // The attacker's faction: the nearest enemy's.
        let ramp = visuals
            .iter()
            .filter(|v| matches!(v.kind, EntityKind::Enemy { .. }))
            .min_by(|a, b| a.shown.distance_squared(t.at).total_cmp(&b.shown.distance_squared(t.at)))
            .and_then(|v| match v.kind {
                EntityKind::Enemy { def } => cfg.content.enemies.try_get(def).map(|d| faction_ramp(&d.key)),
                _ => None,
            })
            .unwrap_or(Ramp::Unmade);
        let fwd = w3(Vec2::new(t.angle.cos(), t.angle.sin()), 0.0).normalize_or(Vec3::NEG_Z);
        kit::telegraph_punch(&mut fx, t.shape, w3(t.at, 0.0), fwd, ramp);
    }
}

/// A straight hard-edged scar along a line that cools over `life` (Piercing Comet).
#[allow(clippy::too_many_arguments)]
pub fn spawn_scar(
    commands: &mut Commands,
    mats: &mut Assets<ZoneMaterial>,
    mesh: &ZoneMesh,
    gpu_now: f32,
    now: f32,
    from: Vec2,
    to: Vec2,
    width: f32,
    life: f32,
) {
    let d = to - from;
    let len = d.length().max(0.1);
    let quad = Vec4::new(0.0, len * 0.5, width * 2.0 + 0.4, len + 0.4);
    let params = with_ramp(
        base(30.0, 0.0, 0.0, 0.3, quad, Vec4::new(len, width, 0.0, 0.0), Vec4::new(gpu_now, life, 1.0, 1.2)),
        Ramp::Radiant,
    );
    let rot = flat(d.y.atan2(d.x));
    let local = quad_transform(quad, 0.0);
    let tf = Transform { translation: w3(from, 0.03) + rot * local.translation, rotation: rot, scale: local.scale };
    let mat = mats.add(ZoneMaterial { params, bias: ZONE_BIAS + 10.0 });
    commands.spawn((Mesh3d(mesh.0.clone()), MeshMaterial3d(mat), tf, NotShadowCaster, ZoneGhost { until: now + life }));
}
