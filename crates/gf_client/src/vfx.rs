//! Transient effects driven by cosmetic events: hit marks, kill bursts and motes, layered
//! explosions, chain bolts, synergy detonations, team moments, pings and damage numbers.
//!
//! The effects themselves are drawn by the batched VFX engine in [`crate::fx`] (painted flipbooks,
//! ribbons, smears, decals, light flashes); this module routes `GameEvent`s to its recipes, picks
//! the readability tier from the live load (`game.ron vfx`, VFX_STYLE §20: every effect must stay
//! readable at 4-player peak chaos) and owns the damage numbers.

use crate::camera::{MainCamera, w3};
use crate::fx::api::{F, burst_seq, faction_ramp};
use crate::fx::{self, Fx, FxStore, Glyph, Mote, Owner, Ramp};
use crate::input::Settings;
use crate::net::Link;
use crate::palette::{Look, Palette, element_color, flat, hdr, hex, mix};
use crate::scene::{SceneIndex, Visual};
use crate::{ClientConfig, ClientSet};
use gf_content::VfxTier;
use gf_core::damage::DamageType;
use gf_core::ids::NetId;
use gf_engine::client::{font_px, world_to_screen};
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{EntityKind, GameEvent};
use std::collections::HashMap;
use std::f32::consts::FRAC_PI_2;

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

#[derive(Component)]
pub struct DamageNumber {
    world: Vec3,
    life: f32,
    max: f32,
    target: NetId,
    amount: u32,
    rise: f32,
    px: f32,
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
    app.init_resource::<VfxState>().add_systems(
        Update,
        (
            choose_tier,
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

/// A big body's statuses show as motes around its hit centre, since its paint stays its own (the
/// rim takes the status colour, `models::skin_material`): embers rise off a burning boss, sparks
/// jump off a shocked one, frost drifts off a frozen one.
fn status_motes(time: Res<Time>, visuals: Query<&Visual>, state: Res<VfxState>, mut fx: Fx) {
    let dt = time.delta_secs();
    if dt <= 0.0 || state.tier == VfxTier::Silhouette {
        return;
    }
    for v in &visuals {
        if !matches!(v.kind, gf_net::EntityKind::Enemy { .. }) || !v.big() {
            continue;
        }
        let mut kinds: Vec<(Ramp, Mote, f32)> = Vec::new();
        if v.flags.contains(gf_net::EntityFlags::FROZEN) {
            kinds.push((Ramp::Time, Mote::Hex, 1.2));
        }
        if v.flags.contains(gf_net::EntityFlags::STUNNED) {
            kinds.push((Ramp::Radiant, Mote::Hex, 0.0));
        }
        let mut bits = v.status;
        while bits != 0 && kinds.len() < 2 {
            let bit = bits.trailing_zeros() as u8;
            bits &= bits - 1;
            // Burn rises, shock and the rest hang.
            kinds.push(match bit {
                0 => (Ramp::Flame, Mote::Ember, -3.0),
                1 => (Ramp::Storm, Mote::Hex, 0.0),
                2 => (Ramp::Void, Mote::Hex, 0.0),
                3 => (Ramp::Plague, Mote::Spore, 0.0),
                4 => (Ramp::Bleed, Mote::Ash, 2.0),
                _ => (Ramp::Radiant, Mote::Hex, 0.0),
            });
        }
        for (ramp, mote, gravity) in kinds {
            // About 9 motes a second per status, more on a bigger body.
            if fx.rand() > dt * (7.0 + 2.0 * v.radius) {
                continue;
            }
            let dir = fx.rand_dir();
            let r = v.radius * fx.range(0.4, 0.9);
            let at = w3(v.shown, v.hit_height * fx.range(0.6, 1.3)) + dir * r;
            let vel = dir * 0.5 + Vec3::Y * fx.range(0.6, 1.4);
            let life = fx.range(0.45, 0.75);
            let size = fx.range(0.14, 0.22);
            fx.sprite(mote.seq(), at)
                .size(size)
                .ramp(ramp)
                .gain(1.3)
                .vel(vel)
                .gravity(gravity)
                .drag(1.5)
                .life(life)
                .erode(0.6, 1.0)
                .layer(fx::Layer::Front)
                .class(fx::Class::Secondary)
                .owner(Owner::World)
                .emit();
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

#[allow(clippy::too_many_arguments)]
fn spawn_from_events(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    settings: Res<Settings>,
    index: Res<SceneIndex>,
    visuals: Query<&Visual>,
    mut pal: ResMut<Palette>,
    mut mats: ResMut<Assets<StandardMaterial>>,
    mut state: ResMut<VfxState>,
    mut numbers: Query<&mut DamageNumber>,
    mut fx: Fx,
) {
    if link.fresh_events.is_empty() {
        return;
    }
    let Some(world) = link.latest.clone() else { return };
    let me = link.slot;
    let mut legacy = Legacy { commands: &mut commands, pal: &mut pal, mats: &mut mats };
    let visual_of = |id: NetId| index.entity(id).and_then(|e| visuals.get(e).ok().map(|v| (e, v)));
    let visual_pos = |id: NetId| visual_of(id).map(|(_, v)| (v.shown, v.radius, v.color));
    let player_pos = |slot: u8| world.players.iter().find(|p| p.slot == slot).map(|p| p.mover.pos);
    let player_entity = |slot: u8| index.players.get(slot as usize).copied().flatten();
    let mut new_numbers: Vec<(NetId, Vec3, u32, Color, f32)> = Vec::new();
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::Hit { target, amount, crit, precision, element, source } => {
                let Some((p, r, _)) = visual_pos(target) else { continue };
                let mine = me.is_some() && Some(source % 4) == me && source < 12;
                // The hit punctuation is the weapon's (`arms::recipes::contact`).
                if settings.damage_numbers && mine && amount > 0 {
                    let color = if precision {
                        hex("#7FF6FF")
                    } else if crit {
                        hex("#FFC940")
                    } else if element == DamageType::Kinetic {
                        Color::srgb(1.0, 0.97, 0.9)
                    } else {
                        mix(element_color(element), Color::WHITE, 0.35)
                    };
                    let px = if crit || precision { 21.0 } else { 14.0 };
                    new_numbers.push((target, w3(p, 1.4 + r), amount as u32, color, px));
                }
            }
            GameEvent::Kill { target, pos, elite, source } => {
                let owner = Owner::of_source(source, me);
                let seen = visual_of(target);
                let r = seen.map_or(0.5, |(_, v)| v.radius);
                let ramp = seen
                    .and_then(|(_, v)| match v.kind {
                        EntityKind::Enemy { def } => cfg.content.enemies.try_get(def).map(|d| faction_ramp(&d.key)),
                        _ => None,
                    })
                    .unwrap_or(Ramp::Unmade);
                let scale = if elite { 2.0 } else { 1.0 };
                fx.death(ramp, pos3(pos, 0.0), r * scale, owner);
                if elite {
                    // The second beat, 6 frames later.
                    fx.sprite(burst_seq(ramp), pos3(pos, 0.9)).radius(r * 1.6).delay(6.0 * F).owner(owner).emit();
                }
                // Kill motes fly to the killer (VFX_STYLE §12.2).
                if source < 12
                    && let Some(killer) = player_entity(source % 4)
                {
                    let n = match (owner, elite) {
                        (_, true) => 6,
                        (Owner::Mine, false) => 3,
                        _ => 1,
                    };
                    fx.motes(pos3(pos, 0.6), killer, n, Ramp::Radiant, owner);
                }
            }
            GameEvent::Synergy { synergy, pos, a, b } => {
                let (ea, eb) = cfg
                    .content
                    .synergies
                    .try_get(synergy)
                    .map_or((DamageType::Radiant, DamageType::Flame), |s| (s.a, s.b));
                let owner = if Some(a) == me || Some(b) == me { Owner::Mine } else { Owner::Ally };
                let at = pos3(pos, 0.0);
                // The trigger beat: both elements' rings wind in and snap into a white frame.
                fx.ring(at, 4.2, 0.6, 10.0 * F, fx::strip::ACCENT_RING, Ramp::of(ea), owner);
                fx.ring(at, 3.6, 0.4, 8.0 * F, fx::strip::ACCENT_RING, Ramp::of(eb), owner);
                fx.burst(Ramp::of(eb), at, 3.0, owner);
                fx.sprite(burst_seq(Ramp::of(ea)), at + Vec3::Y * 0.3).radius(2.4).delay(4.0 * F).owner(owner).emit();
                fx.ring(at, 0.5, 3.2, 20.0 * F, fx::strip::ACCENT_RING, Ramp::ZoneGold, owner);
            }
            GameEvent::Ability { slot, pos, .. } => {
                let owner = Owner::of_slot(slot, me);
                fx.ring(pos3(pos, 0.0), 0.4, 2.8, 20.0 * F, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
                fx.smoke(pos3(pos, 0.2), 4, 0.6, Ramp::Dust, owner);
            }
            GameEvent::Overdrive { slot } => {
                for p in &world.players {
                    let owner = Owner::of_slot(p.slot, me);
                    let at = w3(p.mover.pos, 0.0);
                    fx.pillar(at, 7.0, 1.1, Ramp::ZoneGold, 0.9, Owner::World);
                    if p.slot == slot {
                        fx.ring(at, 0.5, 12.0, 0.8, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
                        fx.dust_wall(at, 0.5, 9.0, 0.5, 0.7, Ramp::ZoneGold, owner);
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
            GameEvent::Revived { slot, .. } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.pillar(w3(p, 0.0), 8.0, 1.0, Ramp::Heal, 0.9, Owner::World);
                    fx.burst(Ramp::Radiant, w3(p, 0.0), 1.4, owner);
                    fx.ring(w3(p, 0.0), 0.4, 3.0, 0.5, fx::strip::HEX_BAND, Ramp::Heal, owner);
                }
            }
            GameEvent::ArmorBreak { slot } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.shards(w3(p, 1.1), 10, 6.5, Ramp::Kinetic, 0.26, owner);
                    fx.ring(w3(p, 0.0), 0.5, 5.0, 0.45, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, owner);
                    fx.dust_wall(w3(p, 0.0), 0.5, 5.0, 0.5, 0.5, Ramp::ZoneGold, owner);
                }
            }
            GameEvent::PlatesShattered { target } => {
                if let Some((p, r, _)) = visual_pos(target) {
                    fx.shards(w3(p, 1.0 + r * 0.5), 11, 7.5, Ramp::GodworksGold, 0.3 + r * 0.1, Owner::Mine);
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
                    fx.ring(w3(p, 0.0), 0.2, 1.1, 12.0 * F, fx::strip::ACCENT_RING, ramp, Owner::Mine);
                }
            }
            GameEvent::Ping { slot, pos, .. } => {
                let c = legacy.pal.player(slot);
                legacy.ping(pos.to_vec2(), c);
            }
            GameEvent::BossPhase { boss, .. } => {
                if let Some((p, r, _)) = visual_pos(boss) {
                    // A faction burst from the boss's core; never red-white (a phase change deals no
                    // damage).
                    fx.burst(Ramp::Unmade, w3(p, 0.0), r + 1.5, Owner::World);
                    fx.ring(w3(p, 0.0), r, r + 10.0, 0.9, fx::strip::SHOCK_FRONT, Ramp::Mono, Owner::World);
                    fx.impact_frame(w3(p, 1.5), r * 1.2, r, Owner::World);
                }
            }
            GameEvent::AnvilLit | GameEvent::AnvilHot => {
                if let Some(a) = world.private.anvil
                    && let Some((p, _, _)) = visual_pos(a.id)
                {
                    let at = w3(p, 0.0);
                    fx.pillar(at, 9.0, 1.3, Ramp::Flame, 1.2, Owner::World);
                    fx.ring(at, 1.0, 6.0, 0.7, fx::strip::SHOCK_FRONT, Ramp::ZoneGold, Owner::World);
                    fx.sprite(fx::seq::SPARKFX_SHOWER, at + Vec3::Y * 1.0)
                        .size(3.0)
                        .ramp(Ramp::Flame)
                        .owner(Owner::World)
                        .emit();
                    fx.light(at + Vec3::Y * 1.5, Ramp::Flame.light(), 400_000.0, 9.0, 1.0, Owner::World);
                }
            }
            GameEvent::Forged { slot, .. } | GameEvent::RecipeDiscovered { slot, .. } => {
                if let Some(p) = player_pos(slot) {
                    let owner = Owner::of_slot(slot, me);
                    fx.impact_frame(w3(p, 1.2), 0.8, 0.5, owner);
                    fx.sprite(fx::seq::SPARKFX_SHOWER, w3(p, 1.2)).size(2.4).ramp(Ramp::Flame).owner(owner).emit();
                    fx.embers(w3(p, 0.5), 8, 0.6, owner);
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
            n.px = n.px.max(px);
            continue;
        }
        if state.numbers >= 40 {
            continue;
        }
        state.numbers += 1;
        let e = commands
            .spawn((
                DamageNumber { world: at, life: 0.8, max: 0.8, target, amount, rise: 0.0, px },
                Text::new(amount.to_string()),
                font_px(px),
                TextColor(color),
                TextShadow { offset: Vec2::new(1.5, 1.5), color: Color::srgba(0.0, 0.0, 0.0, 0.85) },
                // Hidden until `update_numbers` projects it (no one-frame flash at the origin).
                Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
                GlobalZIndex(5),
            ))
            .id();
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

fn update_numbers(
    mut commands: Commands,
    time: Res<Time>,
    mut state: ResMut<VfxState>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut q: Query<(Entity, &mut DamageNumber, &mut Node, &mut Text, &mut TextFont, &mut TextColor)>,
) {
    let dt = time.delta_secs();
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let mut alive = 0;
    for (e, mut n, mut node, mut text, mut font, mut color) in &mut q {
        n.life -= dt;
        if n.life <= 0.0 {
            if state.recent.get(&n.target) == Some(&e) {
                state.recent.remove(&n.target);
            }
            commands.entity(e).despawn();
            continue;
        }
        alive += 1;
        n.rise += dt * 1.6;
        let label = n.amount.to_string();
        if text.0 != label {
            text.0 = label;
        }
        let k = n.life / n.max;
        let pop = if k > 0.85 { 1.0 + (k - 0.85) * 3.0 } else { 1.0 };
        *font = font_px(n.px * pop);
        color.0 = color.0.with_alpha((k * 2.0).min(1.0));
        match world_to_screen(camera, cam_tf, n.world + Vec3::Y * n.rise) {
            Some(p) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - n.px * 0.3 * text.0.len() as f32);
                node.top = Val::Px(p.y - n.px);
            }
            None => node.display = Display::None,
        }
    }
    state.numbers = alive;
}
