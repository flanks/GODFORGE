//! Transient effects driven by cosmetic events: hit marks, kill bursts and motes, layered
//! explosions, chain bolts, synergy detonations, team moments, pings and damage numbers.
//!
//! The effects themselves are drawn by the batched VFX engine in [`crate::fx`] (painted flipbooks,
//! ribbons, smears, decals, light flashes); this module routes `GameEvent`s to its recipes, picks
//! the readability tier from the live load (`game.ron vfx`, VFX_STYLE §20: every effect must stay
//! readable at 4-player peak chaos) and owns the damage numbers.

use crate::camera::{MainCamera, w3};
use crate::fx::api::{F, burst_seq, faction_ramp};
use crate::fx::{self, Fx, FxStore, Glyph, Owner, Ramp};
use crate::input::Settings;
use crate::net::Link;
use crate::palette::{Look, Palette, element_color, flat, hdr, hex};
use crate::scene::{SceneIndex, Visual};
use crate::{ClientConfig, ClientSet};
use gf_content::VfxTier;
use gf_core::damage::DamageType;
use gf_core::ids::NetId;
use gf_core::synergy::SynergyEffect;
use gf_engine::client::{SystemParam, world_to_screen};
use gf_engine::prelude::*;
use gf_net::quant::{QPos, u16_to_dir};
use gf_net::{EntityFlags, EntityKind, GameEvent, PlayerFlags};
use kit::{Caster, Hero};
use live::{CastLog, CastRec, SynRec};
use std::collections::HashMap;
use std::f32::consts::FRAC_PI_2;
use zone::{ZoneMaterial, ZoneMesh};

mod gallery;
pub mod kit;
pub mod live;
pub mod zone;

/// A short-lived additive mote.
#[derive(Component)]
pub struct Particle {
    vel: Vec3,
    life: f32,
    max: f32,
    size: Vec3,
    gravity: f32,
    drag: f32,
}

/// An expanding flat ring (explosions, synergies, overdrive).
#[derive(Component)]
struct Shockwave {
    life: f32,
    max: f32,
    from: f32,
    to: f32,
    color: Color,
    alpha_q: u8,
}

/// A vertical light column (revive, anvil lit) or a lingering marker (ping).
#[derive(Component)]
struct Fade {
    life: f32,
    max: f32,
    base_scale: Vec3,
    shrink_xz: bool,
}

/// A damage number (UI_STYLE §6.12): `Dmg` 21 in the element hue, crits 28 in `ichor` with a
/// spark. Pops with `UiTransform.scale` (never the font size), rises 18 px, fades at the end.
#[derive(Component)]
pub struct DamageNumber {
    world: Vec3,
    life: f32,
    max: f32,
    target: NetId,
    amount: u32,
    px: f32,
    crit: bool,
    color: Color,
    /// The pop restarts when hits merge into this number.
    pop: f32,
    fresh: bool,
    spark: Option<Entity>,
}

#[derive(Resource, Default)]
pub struct VfxState {
    pub tier: VfxTier,
    pub particles: u32,
    pub numbers: u32,
    /// Latest number per target (aggregates rapid hits into one rising number).
    recent: HashMap<NetId, Entity>,
}

pub fn build(app: &mut App) {
    zone::build(app);
    gallery::build(app);
    // QA A/B: `GF_VFX_ZONES=0` leaves the painted zones and the auras out (frame-time checks).
    let zones = std::env::var("GF_VFX_ZONES").map_or(true, |v| v != "0");
    app.init_resource::<VfxState>().init_resource::<CastLog>().init_resource::<EventClaims>().add_systems(
        Update,
        (zone::resolve, zone::dress, zone::cache_telegraphs, live::auras)
            .chain()
            .run_if(move || zones)
            .after(spawn_from_events)
            .before(status_motes)
            .in_set(ClientSet::Presentation),
    );
    // `--fps`: log the CPU cost of lane A (the event router, zones and auras) every 2 s.
    let log_cost = std::env::args().any(|a| a == "--fps");
    app.init_resource::<LaneClock>().add_systems(
        Update,
        lane_end.run_if(move || log_cost).after(live::auras).before(status_motes).in_set(ClientSet::Presentation),
    );
    app.add_systems(
        Update,
        (
            choose_tier,
            lane_begin,
            spawn_from_events,
            status_motes,
            update_particles,
            update_shockwaves,
            update_fades,
            update_numbers,
        )
            .chain()
            .in_set(ClientSet::Presentation),
    );
}

/// CPU time of lane A per frame (`--fps` logs it).
#[derive(Resource, Default)]
struct LaneClock {
    start: Option<std::time::Instant>,
    ms: f32,
    worst: f32,
    frames: u32,
    since: f32,
}

fn lane_begin(mut c: ResMut<LaneClock>) {
    c.start = Some(std::time::Instant::now());
}

fn lane_end(time: Res<Time>, mut c: ResMut<LaneClock>, store: Res<FxStore>) {
    if let Some(s) = c.start.take() {
        let ms = s.elapsed().as_secs_f32() * 1000.0;
        c.ms += ms;
        c.worst = c.worst.max(ms);
        c.frames += 1;
    }
    c.since += time.delta_secs();
    if c.since >= 2.0 && c.frames > 0 {
        let s = store.stats;
        info!(
            "vfx lane A: {:.3} ms/frame avg, {:.2} worst (events, zones, auras) · fx {} particles, {} ribbons, {} arcs, {} decals, {} draws, build {:.2} ms",
            c.ms / c.frames as f32,
            c.worst,
            s.particles,
            s.ribbons,
            s.arcs,
            s.decals,
            s.draws,
            s.build_ms
        );
        *c = LaneClock::default();
    }
}

/// A big body's statuses show as motes around its hit centre, since its paint stays its own (the
/// rim takes the status colour, `models::skin_material`): embers rise off a burning boss, sparks
/// jump off a shocked one, hex motes drip off a cursed one, frost drifts off a frozen one
/// (VFX_STYLE §12.3). Drawn by the batched engine as secondaries, so the tier thins them.
fn status_motes(time: Res<Time>, visuals: Query<&Visual>, mut fx: Fx) {
    let dt = time.delta_secs();
    if dt <= 0.0 || fx.store().tier == VfxTier::Silhouette {
        return;
    }
    for v in &visuals {
        if !matches!(v.kind, EntityKind::Enemy { .. }) || !(v.big() || v.flags.contains(gf_net::EntityFlags::ELITE)) {
            continue;
        }
        let mut kinds: [Option<u8>; 3] = [None; 3];
        let mut n = 0;
        if v.flags.contains(gf_net::EntityFlags::FROZEN) {
            kinds[n] = Some(kit::FROZEN);
            n += 1;
        }
        if v.flags.contains(gf_net::EntityFlags::STUNNED) {
            kinds[n] = Some(kit::STUNNED);
            n += 1;
        }
        let mut bits = v.status;
        while bits != 0 && n < 3 {
            let bit = bits.trailing_zeros() as u8;
            bits &= bits - 1;
            kinds[n] = Some(bit);
            n += 1;
        }
        for kind in kinds.into_iter().flatten() {
            // About 9 motes a second per status, more on a bigger body.
            if fx.rand() > dt * (7.0 + 2.0 * v.radius) {
                continue;
            }
            let d = fx.rand_dir();
            let r = v.radius * fx.range(0.4, 0.9);
            let at = w3(v.shown, v.hit_height * fx.range(0.6, 1.3)) + d * r;
            kit::status_mote(&mut fx, kind, at, d, Owner::World);
        }
    }
}

/// The readability tier from the live effect load (VFX_STYLE §20.1): replicated projectiles,
/// hazards and telegraphs, legacy particle entities, and the batched fx store (ribbons and arcs
/// count as effects, particles at a quarter). It steps up at once and back down only after the
/// load has stayed 15 % under the threshold for half a second, so it never flickers.
fn choose_tier(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    index: Res<SceneIndex>,
    mut state: ResMut<VfxState>,
    mut store: ResMut<FxStore>,
    mut calm: Local<f32>,
) {
    let b = &cfg.content.game.vfx;
    let load = index.effect_count + state.particles + store.load();
    let wanted = if load >= b.silhouette_at {
        VfxTier::Silhouette
    } else if load >= b.reduced_at {
        VfxTier::Reduced
    } else {
        VfxTier::Full
    };
    let below = |at: u32| (load as f32) < at as f32 * 0.85;
    let can_drop = match state.tier {
        VfxTier::Silhouette => below(b.silhouette_at),
        VfxTier::Reduced => below(b.reduced_at),
        VfxTier::Full => true,
    };
    if (wanted as u8) >= (state.tier as u8) {
        state.tier = wanted;
        *calm = 0.0;
    } else if can_drop {
        *calm += time.delta_secs();
        if *calm >= 0.5 {
            state.tier = wanted;
            *calm = 0.0;
        }
    } else {
        *calm = 0.0;
    }
    store.tier = state.tier;
    store.caps = b.particles;
    store.ally_alpha = b.ally_effect_alpha;
}

/// The last legacy mesh effects: the ping marker (a player-colour ownership mark: the fx ramps
/// carry no player colours) and its ring.
struct Legacy<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    pal: &'a mut Palette,
    mats: &'a mut Assets<StandardMaterial>,
}

impl Legacy<'_, '_, '_> {
    fn shockwave(&mut self, at: Vec2, color: Color, from: f32, to: f32, life: f32) {
        let mat = self.pal.mat(self.mats, hdr(color, 2.5).with_alpha(0.8), Look::Decal);
        let ring = self.pal.ring.clone();
        self.commands.spawn((
            Shockwave { life, max: life, from, to, color, alpha_q: 4 },
            Mesh3d(ring),
            MeshMaterial3d(mat),
            Transform { translation: w3(at, 0.06), rotation: flat(FRAC_PI_2), scale: Vec3::splat(from.max(0.01)) },
        ));
    }

    fn ping(&mut self, at: Vec2, color: Color) {
        let mat = self.pal.mat(self.mats, hdr(color, 2.5).with_alpha(0.85), Look::Decal);
        let cube = self.pal.cube.clone();
        let scale = Vec3::splat(0.35);
        self.commands.spawn((
            Fade { life: 3.0, max: 3.0, base_scale: scale, shrink_xz: false },
            Mesh3d(cube),
            MeshMaterial3d(mat),
            Transform {
                translation: w3(at, 2.2),
                rotation: Quat::from_rotation_z(std::f32::consts::FRAC_PI_4)
                    * Quat::from_rotation_x(std::f32::consts::FRAC_PI_4),
                scale,
            },
        ));
        self.shockwave(at, color, 0.3, 1.6, 0.6);
    }
}

fn pos3(q: QPos, h: f32) -> Vec3 {
    w3(q.to_vec2(), h)
}

/// The ramp of a god's boon pillar and sigil (VFX_STYLE §19).
fn god_look(key: &str) -> (Ramp, Glyph) {
    match key {
        "pyra" => (Ramp::Flame, Glyph::GodPyra),
        "zephyros" => (Ramp::Storm, Glyph::GodZephyros),
        "nyctia" => (Ramp::Void, Glyph::GodNyctia),
        "aeon" => (Ramp::Time, Glyph::GodAeon),
        "gaiaa" => (Ramp::Kinetic, Glyph::GodGaiaa),
        "morwenn" => (Ramp::Plague, Glyph::GodMorwenn),
        "seraphel" => (Ramp::Radiant, Glyph::GodSeraphel),
        "umbra_rex" => (Ramp::Void, Glyph::GodUmbraRex),
        _ => (Ramp::ZoneGold, Glyph::SunWheel),
    }
}

/// Lane A's shared state for the event router.
#[derive(SystemParam)]
pub struct LaneA<'w> {
    log: ResMut<'w, CastLog>,
    zone_mats: ResMut<'w, Assets<ZoneMaterial>>,
    zone_mesh: Option<Res<'w, ZoneMesh>>,
    claims: ResMut<'w, EventClaims>,
}

/// The fresh events lane A drew as set pieces this frame (a synergy's own blast and hops, an
/// ability's own hops and landing): the weapon effects (`arms::events`) skip them so nothing
/// draws twice.
#[derive(Resource, Default)]
pub struct EventClaims(pub Vec<bool>);

impl EventClaims {
    pub fn claimed(&self, i: usize) -> bool {
        self.0.get(i).copied().unwrap_or(false)
    }
}

/// The heroes whose cast beat needs the enemy bodies around them (marks, reticles).
fn cast_needs_targets(hero: Hero, which: u8) -> bool {
    matches!((hero, which), (Hero::Kael, 0) | (Hero::Ossian, 2))
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_from_events(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    settings: Res<Settings>,
    index: Res<SceneIndex>,
    visuals: Query<&Visual>,
    mut pal: ResMut<Palette>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut state: ResMut<VfxState>,
    mut numbers: Query<&mut DamageNumber>,
    kit: Res<crate::uikit::UiKit>,
    mut fx: Fx,
    mut lane: LaneA,
    mut last_ripple: Local<HashMap<NetId, f32>>,
) {
    lane.claims.0.clear();
    if link.fresh_events.is_empty() {
        return;
    }
    let Some(world) = link.latest.clone() else { return };
    let me = link.slot;
    let now = time.elapsed_secs();
    let events = &link.fresh_events;
    let mut legacy = Legacy { commands: &mut commands, pal: &mut pal, mats: &mut mats };
    let visual_of = |id: NetId| index.entity(id).and_then(|e| visuals.get(e).ok().map(|v| (e, v)));
    let visual_pos = |id: NetId| visual_of(id).map(|(_, v)| (v.shown, v.radius, v.color));
    let player_pos = |slot: u8| world.players.iter().find(|p| p.slot == slot).map(|p| p.mover.pos);
    let player_entity = |slot: u8| index.players.get(slot as usize).copied().flatten();
    let hero_of_slot = |slot: u8| {
        world.players.iter().find(|p| p.slot == slot).map_or(Hero::Other, |p| live::hero_of(&cfg, p.character))
    };
    let enemies_near = |at: Vec2, r: f32| -> Vec<Vec3> {
        visuals
            .iter()
            .filter(|v| matches!(v.kind, EntityKind::Enemy { .. }) && v.shown.distance(at) <= r + v.radius)
            .take(32)
            .map(|v| w3(v.shown, v.hit_height))
            .collect()
    };
    let mut new_numbers: Vec<(NetId, Vec3, u32, Color, f32)> = Vec::new();
    if last_ripple.len() > 256 {
        last_ripple.retain(|_, t| now - *t < 0.5);
    }
    // Events the sim pushes just before a synergy belong to its set piece: a Burst synergy's
    // Explosion, a chain synergy's Arc hops (VFX_STYLE §13).
    let mut claimed = vec![false; events.len()];
    let mut syn_parts: HashMap<usize, (Option<f32>, Vec<(Vec3, Vec3)>)> = HashMap::new();
    for (i, ev) in events.iter().enumerate() {
        let GameEvent::Synergy { synergy, pos, .. } = *ev else { continue };
        let Some(def) = cfg.content.synergies.try_get(synergy) else { continue };
        let p = pos.to_vec2();
        let mut radius = None;
        let mut hops = Vec::new();
        let mut j = i;
        match def.effect {
            SynergyEffect::Burst { .. } => {
                while j > 0 {
                    j -= 1;
                    match events[j] {
                        GameEvent::Explosion { pos: e, radius_q, .. }
                            if !claimed[j] && e.to_vec2().distance(p) < 0.3 =>
                        {
                            radius = Some(radius_q as f32 / 32.0);
                            claimed[j] = true;
                            break;
                        }
                        GameEvent::Explosion { .. } | GameEvent::Arc { .. } => continue,
                        _ => break,
                    }
                }
            }
            SynergyEffect::GravityChain { .. } => {
                while j > 0 {
                    j -= 1;
                    let GameEvent::Arc { from, to, .. } = events[j] else { break };
                    if claimed[j] {
                        break;
                    }
                    claimed[j] = true;
                    hops.push((pos3(from, 0.0), pos3(to, 0.0)));
                    if from.to_vec2().distance(p) < 0.3 {
                        break;
                    }
                }
                hops.reverse();
            }
            SynergyEffect::Field { radius: r, .. } | SynergyEffect::AllyHeal { radius: r, .. } => radius = Some(r),
        }
        syn_parts.insert(i, (radius, hops));
    }
    // Arcs and explosions right after an Ability event are that cast's steps (same sim tick).
    let mut cast_of: Vec<Option<usize>> = vec![None; events.len()];
    for (i, ev) in events.iter().enumerate() {
        if !matches!(ev, GameEvent::Ability { .. }) {
            continue;
        }
        let mut j = i + 1;
        while j < events.len()
            && matches!(events[j], GameEvent::Arc { .. } | GameEvent::Explosion { .. })
            && !claimed[j]
        {
            cast_of[j] = Some(i);
            j += 1;
        }
    }
    // The weapon effects (`arms::events`, which runs after this) skip whatever lane A draws as a
    // set piece, so a synergy's blast or an ability's hop never draws twice.
    lane.claims.0.clone_from(&claimed);
    for (i, ev) in events.iter().enumerate() {
        if claimed[i] {
            continue;
        }
        match *ev {
            GameEvent::Hit { target, amount, crit, precision, element, source } => {
                let Some((_, v)) = visual_of(target) else { continue };
                let (p, r) = (v.shown, v.radius);
                let mine = me.is_some() && Some(source % 4) == me && source < 12;
                // The hit punctuation is the weapon's (`arms::recipes::contact`, which also glances
                // hits off plated elites); lane A adds the shield ripple.
                let owner = Owner::of_source(source, me);
                // A shield ripples a hex band over the body (at most every 0.15 s).
                if v.flags.contains(EntityFlags::SHIELDED)
                    && owner != Owner::Enemy
                    && !last_ripple.get(&target).is_some_and(|t| now - *t < 0.15)
                    && let EntityKind::Enemy { def } = v.kind
                {
                    last_ripple.insert(target, now);
                    let faction = cfg.content.enemies.try_get(def).map_or(Ramp::Unmade, |d| faction_ramp(&d.key));
                    kit::shield_ripple(&mut fx, w3(p, v.hit_height), r, faction, owner);
                }
                if settings.damage_numbers && mine && amount > 0 {
                    // Element hue for normal hits (Kinetic reads as bone); crits and precision
                    // hits in ichor at 28 (§6.12). Never red-white: that is danger only.
                    let big = crit || precision;
                    let color = if big { crate::theme::tok::ICHOR } else { element_color(element) };
                    let px = if big { 28.0 } else { 21.0 };
                    new_numbers.push((target, w3(p, 1.4 + r), amount as u32, color, px));
                }
            }
            GameEvent::Kill { target, pos, elite, source } => {
                let owner = Owner::of_source(source, me);
                let seen = visual_of(target);
                let r = seen.map_or(0.5, |(_, v)| v.radius);
                let boss = seen.is_some_and(|(_, v)| v.flags.contains(EntityFlags::BOSS));
                let ramp = seen
                    .and_then(|(_, v)| match v.kind {
                        EntityKind::Enemy { def } => cfg.content.enemies.try_get(def).map(|d| faction_ramp(&d.key)),
                        _ => None,
                    })
                    .unwrap_or(Ramp::Unmade);
                if boss {
                    kit::boss_death(&mut fx, ramp, pos3(pos, 0.0), r);
                } else {
                    let scale = if elite { 2.0 } else { 1.0 };
                    fx.death(ramp, pos3(pos, 0.0), r * scale, owner);
                    kit::death_extras(&mut fx, ramp, pos3(pos, 0.0), r * scale, owner);
                    if elite {
                        // The second beat, 6 frames later.
                        fx.sprite(burst_seq(ramp), pos3(pos, 0.9)).radius(r * 1.6).delay(6.0 * F).owner(owner).emit();
                    }
                }
                // Kill motes fly to the killer (VFX_STYLE §12.2).
                if source < 12
                    && let Some(killer) = player_entity(source % 4)
                {
                    let n = match (owner, elite || boss) {
                        (_, true) => 6,
                        (Owner::Mine, false) => 3,
                        _ => 1,
                    };
                    fx.motes(pos3(pos, 0.6), killer, n, Ramp::Radiant, owner);
                    // Grand Heist: every kill spurts coins.
                    if lane.log.active(source % 4, Hero::Mirren, 2, now, 6.0).is_some() {
                        kit::coins(&mut fx, pos3(pos, 0.0), 4, 3.0, owner);
                    }
                }
            }
            GameEvent::Explosion { pos, radius_q, element } => {
                let r = radius_q as f32 / 32.0;
                let at = pos3(pos, 0.0);
                let p2 = pos.to_vec2();
                // Cinder Uppercut: its Nova is the uppercut.
                if let Some(ai) = cast_of[i]
                    && let GameEvent::Ability { slot, which: 0, .. } = events[ai]
                    && hero_of_slot(slot) == Hero::Brax
                {
                    let aim = world.players.iter().find(|p| p.slot == slot).map_or(Vec2::Y, |p| u16_to_dir(p.aim));
                    kit::uppercut(&mut fx, at, w3(aim, 0.0).normalize_or(Vec3::NEG_Z), r, Owner::of_slot(slot, me));
                    lane.claims.0[i] = true;
                    continue;
                }
                // Bulwark Slam lands: its Nova arrives after the leap.
                if (r - 3.4).abs() < 0.4
                    && element == DamageType::Kinetic
                    && let Some(c) = lane
                        .log
                        .casts
                        .iter()
                        .rev()
                        .find(|c| c.hero == Hero::Valdris && c.which == 0 && now - c.t < 1.6 && c.at.distance(p2) < 9.0)
                        .cloned()
                {
                    let stunned = enemies_near(p2, r);
                    kit::bulwark_landing(
                        &mut fx,
                        at,
                        r,
                        w3(c.aim, 0.0).normalize_or(Vec3::NEG_Z),
                        Owner::of_slot(c.slot, me),
                        &stunned,
                    );
                    lane.claims.0[i] = true;
                    continue;
                }
                // Meltdown: every strike's explode runs forward as a flame shockwave.
                if element == DamageType::Flame
                    && (r - 2.0).abs() < 0.35
                    && let Some(b) = world.players.iter().find(|p| {
                        p.flags.contains(PlayerFlags::AVATAR)
                            && live::hero_of(&cfg, p.character) == Hero::Brax
                            && p.mover.pos.distance(p2) < r + 3.5
                    })
                {
                    kit::meltdown_wave(&mut fx, w3(b.mover.pos, 0.0), at, r, Owner::of_slot(b.slot, me));
                    lane.claims.0[i] = true;
                    continue;
                }
                // The blast itself is the weapon lane's (`arms::recipes::explosion`, which traces
                // it back to its shot); these casts add their scatter on top.
                if element == DamageType::Kinetic
                    && (r - 3.0).abs() < 0.3
                    && let Some(c) = lane.log.any(Hero::Ossian, 1, now, 1.6)
                {
                    kit::bomblets(&mut fx, at, 3.6, Owner::of_slot(c.slot, me));
                }
                if element == DamageType::Kinetic
                    && (r - 3.2).abs() < 0.3
                    && let Some(c) = lane.log.any(Hero::Mirren, 0, now, 3.8)
                    && now - c.t > 2.0
                {
                    kit::decoy_pop(&mut fx, at, Owner::of_slot(c.slot, me));
                }
            }
            GameEvent::Arc { from, to, .. } => {
                // A plain chain hop is the weapon lane's (`arms::recipes::chain`); lane A draws
                // the hops that are an ability's own steps.
                let Some(ai) = cast_of[i] else { continue };
                let GameEvent::Ability { slot, which, .. } = events[ai] else { continue };
                let owner = Owner::of_slot(slot, me);
                match (hero_of_slot(slot), which) {
                    (Hero::Selene, 1) => kit::blink_arrive(&mut fx, pos3(from, 0.0), pos3(to, 0.0), owner),
                    (Hero::Ossian, 0) => {
                        let (a, b) = (from.to_vec2(), to.to_vec2());
                        let pierced: Vec<Vec3> = visuals
                            .iter()
                            .filter(|v| matches!(v.kind, EntityKind::Enemy { .. }))
                            .filter(|v| {
                                let ab = b - a;
                                let t = ((v.shown - a).dot(ab) / ab.length_squared().max(1e-4)).clamp(0.0, 1.0);
                                v.shown.distance(a + ab * t) <= 0.6 + v.radius
                            })
                            .take(20)
                            .map(|v| w3(v.shown, v.hit_height))
                            .collect();
                        kit::comet(&mut fx, pos3(from, 0.0), pos3(to, 0.0), owner, &pierced);
                        if let Some(mesh) = lane.zone_mesh.as_deref() {
                            zone::spawn_scar(
                                legacy.commands,
                                &mut lane.zone_mats,
                                mesh,
                                time.elapsed_secs_wrapped(),
                                now,
                                a,
                                b,
                                0.55,
                                1.5,
                            );
                        }
                    }
                    (Hero::Mirren, 1) => kit::snatch(&mut fx, pos3(from, 0.0), pos3(to, 0.0), owner),
                    _ => continue,
                }
                lane.claims.0[i] = true;
            }
            GameEvent::Synergy { synergy, pos, a, b } => {
                let def = cfg.content.synergies.try_get(synergy);
                let key = def.map_or("", |s| s.key.as_str());
                let (ea, eb) = def.map_or((DamageType::Radiant, DamageType::Flame), |s| (s.a, s.b));
                let owner = if Owner::of_source(a, me) == Owner::Mine || Owner::of_source(b, me) == Owner::Mine {
                    Owner::Mine
                } else {
                    Owner::Ally
                };
                let (radius, hops) = syn_parts.remove(&i).unwrap_or_default();
                let p2 = pos.to_vec2();
                let targets = enemies_near(p2, radius.unwrap_or(3.0).max(3.0) + 1.0);
                let allies: Vec<Entity> = world
                    .players
                    .iter()
                    .filter(|p| p.life.is_alive() && p.mover.pos.distance(p2) <= radius.unwrap_or(6.0))
                    .filter_map(|p| player_entity(p.slot))
                    .collect();
                kit::synergy(
                    &mut fx,
                    key,
                    pos3(pos, 0.0),
                    Ramp::of(ea),
                    Ramp::of(eb),
                    radius,
                    &hops,
                    &targets,
                    &allies,
                    owner,
                );
                lane.log.record_synergy(SynRec { t: now, key: key.to_string(), at: p2, owner });
            }
            GameEvent::Ability { slot, which, pos } => {
                let pv = world.players.iter().find(|p| p.slot == slot);
                let hero = hero_of_slot(slot);
                let aim2 = pv.map_or(Vec2::Y, |p| u16_to_dir(p.aim));
                let at2 = pos.to_vec2();
                lane.log.record(CastRec { t: now, slot, hero, which, at: at2, aim: aim2 });
                let caster = Caster {
                    slot,
                    hero,
                    at: w3(at2, 0.0),
                    aim: w3(aim2, 0.0).normalize_or(Vec3::NEG_Z),
                    owner: Owner::of_slot(slot, me),
                    entity: player_entity(slot),
                };
                let targets = if cast_needs_targets(hero, which) { enemies_near(at2, 18.0) } else { Vec::new() };
                kit::ability(&mut fx, &caster, which, &targets);
                if hero == Hero::Epoch && which == 2 {
                    lane.log.freeze = Some((now + 2.0, caster.at, caster.owner));
                }
            }
            GameEvent::Overdrive { slot } => {
                for p in &world.players {
                    let owner = Owner::of_slot(p.slot, me);
                    let at = w3(p.mover.pos, 0.0);
                    fx.pillar(at, 7.0, 1.1, Ramp::ZoneGold, 0.9, Owner::World);
                    if p.slot == slot {
                        fx.ring(at, 0.5, 12.0, 0.8, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
                        fx.dust_wall(at, 0.5, 9.0, 0.5, 0.7, Ramp::ZoneGold, owner);
                        fx.impact_frame(at + Vec3::Y * 1.2, 1.2, 0.5, owner);
                    }
                }
            }
            GameEvent::Downed { slot } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.smoke(w3(p, 0.5), 6, 0.8, Ramp::Mono, owner);
                    fx.ring(w3(p, 0.0), 0.3, 2.5, 0.6, fx::strip::SHOCK_FRONT, Ramp::Dust, owner);
                }
            }
            GameEvent::Revived { slot, by } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.pillar(w3(p, 0.0), 8.0, 1.0, Ramp::Heal, 0.9, Owner::World);
                    fx.burst(Ramp::Radiant, w3(p, 0.0), 1.4, owner);
                    fx.ring(w3(p, 0.0), 0.4, 3.0, 0.5, fx::strip::HEX_BAND, Ramp::Heal, owner);
                    // The reviver gets a shield bubble (hex ripple).
                    if let Some(q) = by.and_then(player_pos) {
                        kit::shield_ripple(
                            &mut fx,
                            w3(q, 1.0),
                            0.9,
                            Ramp::ZoneGold,
                            Owner::of_slot(by.unwrap_or(slot), me),
                        );
                    }
                }
            }
            GameEvent::ArmorBreak { slot } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.shards(w3(p, 1.1), 10, 6.5, Ramp::Kinetic, 0.26, owner);
                    fx.ring(w3(p, 0.0), 0.5, 5.0, 0.45, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
                    fx.dust_wall(w3(p, 0.0), 0.5, 5.0, 0.5, 0.5, Ramp::ZoneGold, owner);
                    fx.impact_frame(w3(p, 1.2), 1.0, 0.5, owner);
                    // A 1-frame gold glint on every taunted enemy.
                    for v in visuals.iter().filter(|v| {
                        matches!(v.kind, EntityKind::Enemy { .. })
                            && v.flags.contains(EntityFlags::TAUNTED)
                            && v.shown.distance(p) < 5.5
                    }) {
                        fx.sprite(fx::seq::GLINT.nth(0), w3(v.shown, v.hit_height + 0.4))
                            .size(0.6)
                            .ramp(Ramp::ZoneGold)
                            .life(3.0 * F)
                            .owner(owner)
                            .emit();
                    }
                }
            }
            GameEvent::PlatesShattered { target } => {
                if let Some((_, v)) = visual_of(target) {
                    let (p, r) = (v.shown, v.radius);
                    let faction = match v.kind {
                        EntityKind::Enemy { def } => {
                            cfg.content.enemies.try_get(def).map_or(Ramp::GodworksGold, |d| faction_ramp(&d.key))
                        }
                        _ => Ramp::GodworksGold,
                    };
                    fx.shards(w3(p, 1.0 + r * 0.5), 12, 7.5, faction, 0.3 + r * 0.1, Owner::Mine);
                    fx.shards(w3(p, 1.0 + r * 0.5), 4, 5.0, Ramp::Mono, 0.22 + r * 0.08, Owner::Mine);
                    fx.smoke(w3(p, 0.3), 5, 0.6 + r * 0.3, Ramp::Dust, Owner::Mine);
                    fx.impact_frame(w3(p, 1.0 + r * 0.5), r + 0.6, r, Owner::Mine);
                    fx.ring(w3(p, 0.0), r, r + 2.0, 0.3, fx::strip::SHOCK_FRONT, Ramp::Mono, Owner::Mine);
                }
            }
            GameEvent::Pickup { slot, kind } => {
                if Some(slot) == me
                    && let Some(p) = player_pos(slot)
                {
                    let ramp = match kind {
                        gf_net::PickupKind::Part { .. } => Ramp::ZoneGold,
                        gf_net::PickupKind::Shards(_) => Ramp::Storm,
                        gf_net::PickupKind::Health => Ramp::Heal,
                    };
                    fx.sprite(fx::seq::GLINT.nth(0), w3(p, 1.0)).radius(0.5).ramp(ramp).life(10.0 * F).emit();
                    fx.sprite(fx::seq::STAR4.nth(1), w3(p, 0.2))
                        .radius(0.45)
                        .ramp(ramp)
                        .life(6.0 * F)
                        .ink_backed()
                        .emit();
                    fx.ring(w3(p, 0.0), 0.2, 1.1, 12.0 * F, fx::strip::ACCENT_RING, ramp, Owner::Mine);
                }
            }
            GameEvent::Ping { slot, pos, .. } => {
                let c = legacy.pal.player(slot);
                legacy.ping(pos.to_vec2(), c);
            }
            GameEvent::BossPhase { boss, .. } => {
                if let Some((_, v)) = visual_of(boss) {
                    let (p, r) = (v.shown, v.radius);
                    let faction = match v.kind {
                        EntityKind::Enemy { def } => {
                            cfg.content.enemies.try_get(def).map_or(Ramp::Unmade, |d| faction_ramp(&d.key))
                        }
                        _ => Ramp::Unmade,
                    };
                    // A faction burst from the boss's core; never red-white (a phase change deals no
                    // damage).
                    fx.burst(faction, w3(p, 0.0), r + 1.5, Owner::World);
                    fx.ring(w3(p, 0.0), r, r + 10.0, 0.9, fx::strip::SHOCK_FRONT, Ramp::Mono, Owner::World);
                    fx.impact_frame(w3(p, 1.5), r * 1.2, r, Owner::World);
                    fx.pillar(w3(p, 0.0), 12.0, r * 0.9, faction, 0.8, Owner::World);
                    fx.shards(w3(p, v.hit_height), 10, 7.0, faction, 0.35, Owner::World);
                }
            }
            GameEvent::AnvilLit | GameEvent::AnvilHot => {
                if let Some(a) = world.private.anvil
                    && let Some((p, _, _)) = visual_pos(a.id)
                {
                    let at = w3(p, 0.0);
                    let hot = matches!(ev, GameEvent::AnvilHot);
                    fx.pillar(at, 9.0, 1.3, Ramp::Flame, 1.2, Owner::World);
                    fx.ring(at, 1.0, 6.0, 0.7, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, Owner::World);
                    fx.sprite(fx::seq::SPARKFX_SHOWER, at + Vec3::Y * 1.0)
                        .size(3.0)
                        .ramp(Ramp::Flame)
                        .owner(Owner::World)
                        .emit();
                    fx.light(at + Vec3::Y * 1.5, Ramp::Flame.light(), 400_000.0, 9.0, 1.0, Owner::World);
                    if hot {
                        fx.tongues(at, 8, 1.2, 1.4, 0.8, Owner::World);
                        fx.embers(at + Vec3::Y * 1.0, 16, 0.8, Owner::World);
                    }
                }
            }
            GameEvent::Forged { slot, .. } | GameEvent::RecipeDiscovered { slot, .. } => {
                let recipe = matches!(ev, GameEvent::RecipeDiscovered { .. });
                let owner = Owner::of_slot(slot, me);
                // The hammer strike lands on the anvil when there is one in reach.
                let anvil = world.private.anvil.and_then(|a| visual_pos(a.id)).map(|(p, _, _)| p);
                let at = match (anvil, player_pos(slot)) {
                    (Some(a), Some(p)) if a.distance(p) < 8.0 => Some(a),
                    (_, p) => p,
                };
                if let Some(p) = at {
                    kit::forge_strike(&mut fx, w3(p, 0.0), recipe, owner);
                }
            }
            GameEvent::BoonTaken { slot, boon } => {
                if let Some(p) = player_pos(slot) {
                    let god = cfg.content.boons.try_get(boon).and_then(|b| b.gods.first()).cloned().unwrap_or_default();
                    let (ramp, glyph) = god_look(&god);
                    let owner = Owner::of_slot(slot, me);
                    fx.pillar(w3(p, 0.0), 6.0, 0.9, ramp, 0.8, Owner::World);
                    fx.decal_seq(glyph.seq(), w3(p, 0.0), 1.1, 0.0, ramp, 1.2, owner);
                }
            }
            _ => {}
        }
    }
    // Damage numbers: aggregate rapid hits on one target into a single rising number.
    for (target, at, amount, color, px) in new_numbers {
        if let Some(&e) = state.recent.get(&target)
            && let Ok(mut n) = numbers.get_mut(e)
            && n.max - n.life < 0.25
        {
            n.amount += amount;
            n.life = n.max;
            n.world = at;
            n.pop = 0.0;
            // A crit merging into a normal number does not restyle it (fixed atlas sizes).
            continue;
        }
        if state.numbers >= 40 {
            continue;
        }
        state.numbers += 1;
        let crit = px > 24.0;
        // A 16 px radiant spark at a crit's upper right.
        let spark = crit.then(|| {
            commands
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        right: px_val(-14.0),
                        top: px_val(-6.0),
                        width: px_val(16.0),
                        height: px_val(16.0),
                        ..default()
                    },
                    kit.tex_tinted("fx/spark4@2x.png", hex("#FFB347")),
                    gf_engine::client::Pickable::IGNORE,
                ))
                .id()
        });
        let e = commands
            .spawn((
                DamageNumber {
                    world: at,
                    life: 0.8,
                    max: 0.8,
                    target,
                    amount,
                    px,
                    crit,
                    color,
                    pop: 0.0,
                    fresh: true,
                    spark,
                },
                kit.text_px(crate::theme::Ty::Dmg, px, amount.to_string(), color),
                // Hidden until `update_numbers` projects it (no one-frame flash at the origin).
                Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
                UiTransform::default(),
                GlobalZIndex(crate::theme::z::WORLD),
            ))
            .id();
        if let Some(sp) = spark {
            commands.entity(e).add_child(sp);
        }
        state.recent.insert(target, e);
    }
}

fn update_particles(
    mut commands: Commands,
    time: Res<Time>,
    mut state: ResMut<VfxState>,
    mut q: Query<(Entity, &mut Particle, &mut Transform)>,
) {
    let dt = time.delta_secs();
    let mut alive = 0;
    for (e, mut p, mut tf) in &mut q {
        p.life -= dt;
        if p.life <= 0.0 {
            commands.entity(e).despawn();
            continue;
        }
        alive += 1;
        let g = p.gravity;
        p.vel.y -= g * dt;
        let drag = (1.0 - p.drag * dt).max(0.0);
        p.vel *= drag;
        tf.translation += p.vel * dt;
        if tf.translation.y < 0.05 {
            tf.translation.y = 0.05;
            p.vel.y = p.vel.y.abs() * 0.3;
        }
        tf.scale = p.size * (p.life / p.max).max(0.05);
    }
    state.particles = alive;
}

fn update_shockwaves(
    mut commands: Commands,
    time: Res<Time>,
    mut pal: ResMut<Palette>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut q: Query<(Entity, &mut Shockwave, &mut Transform, &mut MeshMaterial3d<StandardMaterial>)>,
) {
    let dt = time.delta_secs();
    for (e, mut s, mut tf, mut mat) in &mut q {
        s.life -= dt;
        if s.life <= 0.0 {
            commands.entity(e).despawn();
            continue;
        }
        let k = 1.0 - s.life / s.max;
        let eased = 1.0 - (1.0 - k) * (1.0 - k);
        tf.scale = Vec3::splat(s.from + (s.to - s.from) * eased);
        let q = ((1.0 - k) * 4.0).ceil() as u8;
        if q != s.alpha_q {
            s.alpha_q = q;
            mat.0 = pal.mat(&mut mats, hdr(s.color, 2.5).with_alpha(0.2 * q as f32), Look::Decal);
        }
    }
}

fn update_fades(mut commands: Commands, time: Res<Time>, mut q: Query<(Entity, &mut Fade, &mut Transform)>) {
    let dt = time.delta_secs();
    for (e, mut f, mut tf) in &mut q {
        f.life -= dt;
        if f.life <= 0.0 {
            commands.entity(e).despawn();
            continue;
        }
        let k = f.life / f.max;
        tf.scale = if f.shrink_xz {
            Vec3::new(f.base_scale.x * k, f.base_scale.y, f.base_scale.z * k.max(0.3))
        } else {
            f.base_scale * (0.4 + 0.6 * k)
        };
    }
}

fn px_val(v: f32) -> Val {
    Val::Px(v)
}

/// §6.12: pop 1.4 → 1.0 over 120 ms (crit 1.5), rise 18 px over 0.7 s, fade over the last
/// 0.25 s. Only targets within 480 px of the hero show numbers (crits always); a number never
/// sits inside the HUD clusters or the callout band.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_numbers(
    mut commands: Commands,
    time: Res<Time>,
    link: Res<Link>,
    scale: Res<UiScale>,
    rects: Res<crate::theme::HudRects>,
    mut state: ResMut<VfxState>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut q: Query<(Entity, &mut DamageNumber, &mut Node, &mut Text, &mut TextColor, &mut TextShadow, &mut UiTransform)>,
    mut images: Query<&mut ImageNode>,
) {
    let dt = time.delta_secs();
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let s = scale.0.max(0.01);
    let hero = link.me().and_then(|p| world_to_screen(camera, cam_tf, w3(p.mover.pos, 1.0))).map(|p| p / s);
    let mut alive = 0;
    for (e, mut n, mut node, mut text, mut color, mut shadow, mut tf) in &mut q {
        n.life -= dt;
        let Some(p) = world_to_screen(camera, cam_tf, n.world).map(|p| p / s) else {
            node.display = Display::None;
            continue;
        };
        // Far from the hero: only crits are worth a number.
        if n.fresh {
            n.fresh = false;
            if !n.crit && hero.is_some_and(|h| h.distance(p) > 480.0) {
                n.life = 0.0;
            }
        }
        if n.life <= 0.0 {
            if state.recent.get(&n.target) == Some(&e) {
                state.recent.remove(&n.target);
            }
            commands.entity(e).despawn();
            continue;
        }
        alive += 1;
        let label = n.amount.to_string();
        let w = label.len() as f32 * n.px * 0.52;
        if text.0 != label {
            text.0 = label;
        }
        let age = n.max - n.life;
        n.pop += dt;
        let k = (n.pop / 0.12).min(1.0);
        let from = if n.crit { 1.5 } else { 1.4 };
        let pop = from + (1.0 - from) * (1.0 - (1.0 - k).powi(3));
        let sc = Vec2::splat(pop);
        if tf.scale != sc {
            tf.scale = sc;
        }
        let rise = 18.0 * (1.0 - (1.0 - (age / 0.7).min(1.0)).powi(2));
        let alpha = (n.life / 0.25).min(1.0);
        color.0 = n.color.with_alpha(alpha);
        shadow.color = crate::theme::tok::INK.with_alpha(0.9 * alpha);
        if let Some(sp) = n.spark
            && let Ok(mut img) = images.get_mut(sp)
        {
            img.color = hex("#FFB347").with_alpha(alpha);
        }
        let at = Vec2::new(p.x, p.y - rise);
        let blocked = rects.hits(at, 6.0) || at.y < 200.0;
        node.display = if blocked { Display::None } else { Display::Flex };
        node.left = Val::Px((at.x - w * 0.5).round());
        node.top = Val::Px((at.y - n.px).round());
    }
    state.numbers = alive;
}
