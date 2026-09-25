//! Transient effects driven by cosmetic events: sparks, death bursts, explosion rings, chain
//! arcs, synergy detonations, pings and damage numbers. Everything is budgeted by the readability
//! tiers in `game.ron` (§5: every effect must stay readable at 4-player peak chaos) — as the
//! screen fills, particle counts drop and finally only silhouettes remain.

use crate::camera::{MainCamera, w3};
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
use gf_net::GameEvent;
use gf_net::quant::QPos;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, TAU};

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
        (choose_tier, spawn_from_events, update_particles, update_shockwaves, update_fades, update_numbers)
            .chain()
            .in_set(ClientSet::Presentation),
    );
}

fn choose_tier(cfg: Res<ClientConfig>, index: Res<SceneIndex>, mut state: ResMut<VfxState>) {
    let b = &cfg.content.game.vfx;
    let load = index.effect_count + state.particles;
    state.tier = if load >= b.silhouette_at {
        VfxTier::Silhouette
    } else if load >= b.reduced_at {
        VfxTier::Reduced
    } else {
        VfxTier::Full
    };
}

struct Fx<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    pal: &'a mut Palette,
    mats: &'a mut Assets<StandardMaterial>,
    budget: u32,
    alive: u32,
    rng: u32,
}

impl Fx<'_, '_, '_> {
    fn rand(&mut self) -> f32 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 17;
        self.rng ^= self.rng << 5;
        (self.rng & 0xffff) as f32 / 65535.0
    }

    #[allow(clippy::too_many_arguments)]
    fn burst(&mut self, at: Vec3, color: Color, count: u32, speed: f32, size: f32, life: f32, gravity: f32) {
        let mat = self.pal.mat(self.mats, hdr(color, 2.5), Look::Additive);
        let mesh = self.pal.low_sphere.clone();
        for _ in 0..count {
            if self.alive >= self.budget {
                return;
            }
            self.alive += 1;
            let a = self.rand() * TAU;
            let up = 0.3 + self.rand() * 0.9;
            let s = speed * (0.4 + self.rand() * 0.8);
            let vel = Vec3::new(a.cos() * s, up * s * 0.8, a.sin() * s);
            let sz = size * (0.6 + self.rand() * 0.8);
            let l = life * (0.6 + self.rand() * 0.6);
            self.commands.spawn((
                Particle { vel, life: l, max: l, size: Vec3::splat(sz), gravity, drag: 2.5 },
                Mesh3d(mesh.clone()),
                MeshMaterial3d(mat.clone()),
                Transform::from_translation(at).with_scale(Vec3::splat(sz)),
            ));
        }
    }

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

    fn flash(&mut self, at: Vec3, color: Color, radius: f32, life: f32) {
        let mat = self.pal.mat(self.mats, hdr(color, 2.0), Look::Additive);
        let mesh = self.pal.sphere.clone();
        let scale = Vec3::splat(radius);
        self.commands.spawn((
            Fade { life, max: life, base_scale: scale, shrink_xz: false },
            Mesh3d(mesh),
            MeshMaterial3d(mat),
            Transform::from_translation(at).with_scale(scale),
        ));
    }

    fn pillar(&mut self, at: Vec2, color: Color, height: f32, life: f32) {
        let mat = self.pal.mat(self.mats, hdr(color, 2.2).with_alpha(0.5), Look::Decal);
        let mesh = self.pal.cylinder.clone();
        let scale = Vec3::new(0.8, height, 0.8);
        self.commands.spawn((
            Fade { life, max: life, base_scale: scale, shrink_xz: true },
            Mesh3d(mesh),
            MeshMaterial3d(mat),
            Transform::from_translation(w3(at, height * 0.5)).with_scale(scale),
        ));
    }

    fn arc(&mut self, from: Vec2, to: Vec2, color: Color) {
        let mat = self.pal.mat(self.mats, hdr(color, 3.5), Look::Additive);
        let mesh = self.pal.cube.clone();
        let segments = 4;
        let mut prev = w3(from, 0.9);
        let perp = (to - from).perp().normalize_or_zero();
        for i in 1..=segments {
            let t = i as f32 / segments as f32;
            let jitter = if i == segments { 0.0 } else { (self.rand() - 0.5) * 0.9 };
            let p = w3(from.lerp(to, t) + perp * jitter, 0.9 + (self.rand() - 0.5) * 0.3);
            let mid = (prev + p) * 0.5;
            let len = prev.distance(p);
            if len > 1e-3 {
                let rot = Quat::from_rotation_arc(Vec3::Z, (p - prev) / len);
                let scale = Vec3::new(0.06, 0.06, len);
                self.commands.spawn((
                    Fade { life: 0.14, max: 0.14, base_scale: scale, shrink_xz: true },
                    Mesh3d(mesh.clone()),
                    MeshMaterial3d(mat.clone()),
                    Transform { translation: mid, rotation: rot, scale },
                ));
            }
            prev = p;
        }
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

#[allow(clippy::too_many_arguments)]
fn spawn_from_events(
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
) {
    if link.fresh_events.is_empty() {
        return;
    }
    let Some(world) = link.latest.clone() else { return };
    let b = &cfg.content.game.vfx;
    let tier = state.tier;
    let budget = b.particles[tier as usize];
    let me = link.slot;
    let scale_count = |n: u32| match tier {
        VfxTier::Full => n,
        VfxTier::Reduced => n.div_ceil(2),
        VfxTier::Silhouette => n / 4,
    };
    let seed = (time.elapsed_secs() * 1000.0) as u32 | 1;
    let mut fx =
        Fx { commands: &mut commands, pal: &mut pal, mats: &mut mats, budget, alive: state.particles, rng: seed };
    let visual_pos =
        |id: NetId| index.entity(id).and_then(|e| visuals.get(e).ok()).map(|v| (v.shown, v.radius, v.color));
    let player_pos = |slot: u8| world.players.iter().find(|p| p.slot == slot).map(|p| p.mover.pos);
    let mut new_numbers: Vec<(NetId, Vec3, u32, Color, f32)> = Vec::new();
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::Hit { target, amount, crit, precision, element, source } => {
                let Some((p, r, _)) = visual_pos(target) else { continue };
                let mine = me.is_some() && Some(source % 4) == me && source < 12;
                if mine || tier == VfxTier::Full {
                    let n = scale_count(if crit { 4 } else { 2 });
                    fx.burst(w3(p, 0.8), element_color(element), n, 4.0, 0.06, 0.25, 6.0);
                }
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
            GameEvent::Kill { pos, elite, .. } => {
                let c = if elite { hex("#FFC940") } else { hex("#FF9A3C") };
                fx.burst(
                    pos3(pos, 0.6),
                    c,
                    scale_count(if elite { 22 } else { 8 }),
                    if elite { 7.0 } else { 5.0 },
                    0.09,
                    0.5,
                    9.0,
                );
                if elite {
                    fx.shockwave(pos.to_vec2(), c, 0.5, 3.5, 0.45);
                }
            }
            GameEvent::Explosion { pos, radius_q, element } => {
                let r = radius_q as f32 / 32.0;
                let c = element_color(element);
                fx.shockwave(pos.to_vec2(), c, r * 0.3, r, 0.3);
                if tier != VfxTier::Silhouette {
                    fx.flash(pos3(pos, 0.5), c, r * 0.55, 0.16);
                }
                fx.burst(pos3(pos, 0.5), c, scale_count(10), 7.0, 0.08, 0.45, 8.0);
            }
            GameEvent::Arc { from, to, element } => fx.arc(from.to_vec2(), to.to_vec2(), element_color(element)),
            GameEvent::Synergy { synergy, pos, .. } => {
                let (a, b2) = cfg
                    .content
                    .synergies
                    .try_get(synergy)
                    .map_or((DamageType::Radiant, DamageType::Flame), |s| (s.a, s.b));
                fx.shockwave(pos.to_vec2(), element_color(a), 0.5, 5.0, 0.55);
                fx.shockwave(pos.to_vec2(), element_color(b2), 0.2, 3.6, 0.45);
                fx.flash(pos3(pos, 0.8), mix(element_color(a), element_color(b2), 0.5), 1.4, 0.22);
                fx.burst(pos3(pos, 0.8), element_color(b2), scale_count(18), 9.0, 0.1, 0.6, 6.0);
            }
            GameEvent::Ability { slot, pos, .. } => {
                let c = fx.pal.player(slot);
                fx.shockwave(pos.to_vec2(), c, 0.4, 2.8, 0.35);
            }
            GameEvent::Overdrive { .. } => {
                for p in &world.players {
                    fx.shockwave(p.mover.pos, hex("#FFC940"), 0.5, 9.0, 0.8);
                    fx.pillar(p.mover.pos, hex("#FFC940"), 7.0, 0.7);
                }
            }
            GameEvent::Downed { slot } => {
                if let Some(p) = player_pos(slot) {
                    fx.burst(w3(p, 1.0), Color::srgb(0.6, 0.6, 0.7), 14, 4.0, 0.1, 0.8, 2.0);
                    fx.shockwave(p, fx.pal.player(slot), 0.3, 2.5, 0.6);
                }
            }
            GameEvent::Revived { slot, .. } => {
                if let Some(p) = player_pos(slot) {
                    fx.pillar(p, hex("#FFE9A8"), 8.0, 0.9);
                    fx.burst(w3(p, 1.0), hex("#FFC940"), 20, 6.0, 0.1, 0.7, 4.0);
                }
            }
            GameEvent::ArmorBreak { slot } => {
                if let Some(p) = player_pos(slot) {
                    fx.burst(w3(p, 1.1), Color::srgb(0.75, 0.75, 0.8), 16, 6.0, 0.1, 0.5, 12.0);
                }
            }
            GameEvent::PlatesShattered { target } => {
                if let Some((p, r, _)) = visual_pos(target) {
                    fx.burst(w3(p, 1.0 + r), Color::srgb(0.8, 0.78, 0.72), 18, 7.0, 0.12, 0.6, 14.0);
                    fx.shockwave(p, Color::srgb(0.9, 0.9, 1.0), r, r + 2.0, 0.3);
                }
            }
            GameEvent::Pickup { slot, kind } => {
                if Some(slot) == me
                    && let Some(p) = player_pos(slot)
                {
                    let c = match kind {
                        gf_net::PickupKind::Part { rarity } => crate::palette::rarity_color(rarity),
                        gf_net::PickupKind::Shards(_) => hex("#8FF7FF"),
                        gf_net::PickupKind::Health => hex("#FF4D6D"),
                    };
                    fx.burst(w3(p, 1.0), c, 8, 3.0, 0.07, 0.4, -2.0);
                }
            }
            GameEvent::Ping { slot, pos, .. } => {
                let c = fx.pal.player(slot);
                fx.ping(pos.to_vec2(), c);
            }
            GameEvent::BossPhase { boss, .. } => {
                if let Some((p, r, _)) = visual_pos(boss) {
                    let danger = fx.pal.danger;
                    fx.shockwave(p, danger, r, r + 10.0, 0.9);
                    fx.flash(w3(p, 1.5), Color::WHITE, r * 1.5, 0.25);
                }
            }
            GameEvent::AnvilLit | GameEvent::AnvilHot => {
                if let Some(a) = world.run.anvil
                    && let Some((p, _, _)) = visual_pos(a.id)
                {
                    fx.pillar(p, hex("#FFB82E"), 9.0, 1.2);
                    fx.shockwave(p, hex("#FFC940"), 1.0, 6.0, 0.7);
                }
            }
            GameEvent::Forged { slot, .. } | GameEvent::RecipeDiscovered { slot, .. } => {
                if let Some(p) = player_pos(slot) {
                    fx.burst(w3(p, 1.2), hex("#FFB82E"), 16, 5.0, 0.08, 0.6, 3.0);
                }
            }
            GameEvent::BoonTaken { slot, boon } => {
                if let Some(p) = player_pos(slot) {
                    let c = cfg
                        .content
                        .boons
                        .try_get(boon)
                        .and_then(|b| b.gods.first())
                        .and_then(|g| cfg.content.gods.by_key(g))
                        .map_or(hex("#FFC940"), |g| crate::palette::hex(&g.color));
                    fx.pillar(p, c, 6.0, 0.6);
                }
            }
            _ => {}
        }
    }
    state.particles = fx.alive;
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
