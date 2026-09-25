//! Firing. Every player runs the single aim pipeline from `gf_core::aim` (target selection → aim
//! solution → trigger), then the weapon's `FireKind` turns trigger edges into volleys, charge
//! releases, beam ticks or melee swings. AUTO/ASSISTED/MANUAL never fork weapon code.

use crate::components::*;
use crate::resources::*;
use gf_core::aim::{AimInput, AimWeapon, TargetCandidate, solve};
use gf_core::ids::SourceId;
use gf_core::math::{dist_sq_point_segment, in_cone, lead_point, rotate};
use gf_core::weapon::{FireKind, WeaponProfile};
use gf_engine::prelude::*;
use gf_net::GameEvent;
use gf_net::quant::angle_to_u16;
use std::sync::Arc;

/// Shared projectile spawn parameters.
pub struct Volley<'a> {
    pub profile: &'a Arc<WeaponProfile>,
    pub origin: Vec2,
    pub dir: Vec2,
    pub damage_scale: f32,
    pub owner: SourceId,
    pub owner_entity: Option<Entity>,
    pub bonus: f32,
    pub crit_bonus: f32,
    pub precision_enabled: bool,
    pub shot: u32,
    pub angle_offset_deg: f32,
}

pub fn spawn_volley(commands: &mut Commands, ids: &mut NetIds, tick: u32, v: Volley) {
    let p = v.profile;
    let n = p.projectiles.max(1);
    for i in 0..n {
        let off = if n == 1 { 0.0 } else { -p.spread_deg + 2.0 * p.spread_deg * i as f32 / (n - 1) as f32 };
        let dir = rotate(v.dir, (off + v.angle_offset_deg).to_radians());
        let pos = v.origin + dir * 0.6;
        commands.spawn((
            Replicated(ids.alloc()),
            Pos(pos),
            RoomScoped,
            Projectile {
                owner: v.owner,
                owner_entity: v.owner_entity,
                weapon: p.clone(),
                damage: p.damage * v.damage_scale,
                dir,
                speed: p.speed,
                radius: p.radius,
                life: p.lifetime(),
                pierce: p.pierce,
                bounces: p.ricochet.map_or(0, |r| r.bounces),
                forked: false,
                hits: Vec::new(),
                shot: v.shot,
                any_hit: false,
                trail_timer: 0.0,
                bonus: v.bonus,
                crit_bonus: v.crit_bonus,
                precision_enabled: v.precision_enabled,
                origin: pos,
                t0: tick,
                steered: false,
            },
        ));
    }
}

#[allow(clippy::type_complexity)]
pub fn aim_and_fire(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    mut queue: ResMut<DamageQueue>,
    mut events: ResMut<Events>,
    enemies: Query<(&Enemy, &Vel, &Replicated)>,
    mut players: Query<(Entity, &Player, &PlayerInput, &Life, &Pos, &mut Aim, &mut Gun, &mut Kit, &mut RunStats)>,
) {
    let dt = clock.gdt();
    for (entity, player, input, life, pos, mut aim, mut gun, mut kit, mut stats) in &mut players {
        let params = content.aim_params(aim.mode);
        aim.deadeye.tick(dt, &params);
        let can_fire = life.state.is_alive() && kit.airborne.is_none();
        let profile = gun.profile.clone();
        let fire = profile.effective_fire();

        // ── target selection → aim solution → trigger ──
        let reach = profile.range * 1.15 + 1.0;
        let mut candidates: Vec<TargetCandidate> = Vec::new();
        grid.0.for_each_in_circle(pos.0, reach, |e| {
            if let Ok((enemy, vel, rep)) = enemies.get(e.entity)
                && enemy.hp > 0.0
            {
                candidates.push(TargetCandidate {
                    id: rep.0,
                    pos: e.pos,
                    vel: vel.0,
                    radius: e.radius,
                    hp: enemy.hp + enemy.shield,
                    hp_frac: enemy.hp / enemy.max_hp.max(1.0),
                    elite: enemy.elite,
                    boss: enemy.is_boss_like(),
                    pinged: enemy.pinged > 0.0,
                });
            }
        });
        let fire_edge = input.fire && !gun.fire_button_prev;
        gun.fire_button_prev = input.fire;
        let aim_input = AimInput {
            origin: pos.0,
            raw_aim: input.aim_dir,
            move_dir: input.move_dir,
            fire_held: input.fire,
            force_next: input.new.force_target > 0 || (params.auto_fire && fire_edge),
            bias: aim.bias,
        };
        let weapon = AimWeapon {
            range: profile.range,
            projectile_speed: if matches!(fire, FireKind::Beam | FireKind::Melee) { 0.0 } else { profile.speed },
            fire,
            charge: gun.charge,
        };
        let mut state = aim.state;
        let solution = solve(&params, &aim_input, &weapon, &candidates, &mut state, dt);
        aim.state = state;
        aim.dir = solution.dir;
        aim.target = solution.target;
        let trigger = solution.trigger && can_fire;

        // Attacker-side multipliers.
        let bonus = params.damage_mult * aim.deadeye.mult(&params);
        let crit_bonus = match kit.passive {
            PassiveState::Ghost { crit } => crit,
            _ => 0.0,
        };
        let source = SourceId::player(player.slot);
        let ramp = profile.ramp.map_or(1.0, |r| 1.0 + (r.max_mult - 1.0) * (gun.ramp_time / r.time_to_max).min(1.0));
        let interval = profile.shot_interval() / ramp;
        gun.cooldown -= dt;
        gun.beam = None;
        gun.firing = false;
        let mut volleys = 0u32;
        match fire {
            FireKind::Auto => {
                if trigger {
                    while gun.cooldown <= 0.0 {
                        gun.cooldown += interval;
                        volleys += 1;
                    }
                } else {
                    gun.cooldown = gun.cooldown.max(0.0);
                }
            }
            FireKind::Charge => {
                if trigger {
                    gun.charge = (gun.charge + dt / profile.charge_time.max(0.05)).min(1.0);
                } else if gun.prev_trigger && gun.charge >= 0.2 && gun.cooldown <= 0.0 {
                    volleys = 1;
                    gun.cooldown = interval;
                }
                if !trigger && volleys == 0 {
                    gun.charge = 0.0;
                }
            }
            FireKind::Beam => {
                if trigger {
                    let width = profile.beam_width.unwrap_or(0.5);
                    gun.beam = Some((profile.range, width));
                    gun.firing = true;
                    gun.beam_tick -= dt;
                    while gun.beam_tick <= 0.0 {
                        gun.beam_tick += interval;
                        beam_tick(
                            &grid, &mut queue, &profile, pos.0, aim.dir, width, source, entity, bonus, crit_bonus,
                        );
                    }
                } else {
                    gun.beam_tick = gun.beam_tick.max(0.0);
                }
            }
            FireKind::Melee => {
                if trigger {
                    while gun.cooldown <= 0.0 {
                        gun.cooldown += interval;
                        melee_swing(
                            &grid,
                            &mut queue,
                            &mut events,
                            &profile,
                            pos.0,
                            aim.dir,
                            source,
                            entity,
                            bonus,
                            crit_bonus,
                        );
                        gun.melee_swing = 0.2;
                        gun.firing = true;
                    }
                } else {
                    gun.cooldown = gun.cooldown.max(0.0);
                }
                gun.melee_swing = (gun.melee_swing - dt).max(0.0);
            }
        }
        gun.ramp_time = if trigger { gun.ramp_time + dt } else { (gun.ramp_time - dt * 2.0).max(0.0) };

        for _ in 0..volleys {
            gun.shots += 1;
            stats.shots += 1;
            gun.firing = true;
            let charge_scale =
                if fire == FireKind::Charge { 1.0 + (profile.charge_mult - 1.0) * gun.charge } else { 1.0 };
            let v = Volley {
                profile: &profile,
                origin: pos.0,
                dir: aim.dir,
                damage_scale: charge_scale,
                owner: source,
                owner_entity: Some(entity),
                bonus,
                crit_bonus,
                precision_enabled: params.precision_enabled,
                shot: gun.shots,
                angle_offset_deg: 0.0,
            };
            spawn_volley(&mut commands, &mut ids, clock.tick, v);
            if let Some(echo) = profile.echo_shot
                && gun.shots.is_multiple_of(echo.every.max(2) as u32)
            {
                let v = Volley {
                    profile: &profile,
                    origin: pos.0,
                    dir: aim.dir,
                    damage_scale: charge_scale * echo.damage,
                    owner: source,
                    owner_entity: Some(entity),
                    bonus,
                    crit_bonus,
                    precision_enabled: false,
                    shot: gun.shots,
                    angle_offset_deg: 4.0,
                };
                spawn_volley(&mut commands, &mut ids, clock.tick, v);
            }
            events.0.push(GameEvent::Shot { slot: player.slot, dir: angle_to_u16(aim.dir), element: profile.element });
            if let Some((left, _)) = gun.next_shots.as_mut() {
                *left = left.saturating_sub(1);
                if *left == 0 {
                    gun.next_shots = None;
                    kit.dirty = true;
                }
            }
            gun.charge = 0.0;
        }
        gun.prev_trigger = trigger;
    }
}

#[allow(clippy::too_many_arguments)]
fn beam_tick(
    grid: &Grid,
    queue: &mut DamageQueue,
    p: &Arc<WeaponProfile>,
    origin: Vec2,
    dir: Vec2,
    width: f32,
    source: SourceId,
    owner: Entity,
    bonus: f32,
    crit_bonus: f32,
) {
    let end = origin + dir * p.range;
    for e in grid.0.in_circle(origin.lerp(end, 0.5), p.range * 0.5 + width) {
        let r = width * 0.5 + e.radius;
        if dist_sq_point_segment(e.pos, origin, end) <= r * r {
            let mut h = Hit::simple(e.entity, source, p.damage, p.element, HitKind::Weapon, e.pos);
            h.crit_chance = p.crit_chance + crit_bonus;
            h.crit_mult = p.crit_mult;
            h.bonus = bonus;
            h.weapon = Some(p.clone());
            h.source_entity = Some(owner);
            h.knockback = dir * p.knockback * 0.2;
            queue.0.push(h);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn melee_swing(
    grid: &Grid,
    queue: &mut DamageQueue,
    events: &mut Events,
    p: &Arc<WeaponProfile>,
    origin: Vec2,
    dir: Vec2,
    source: SourceId,
    owner: Entity,
    bonus: f32,
    crit_bonus: f32,
) {
    let half = p.spread_deg.to_radians().max(0.5);
    for e in grid.0.in_circle(origin, p.range + 0.5) {
        if in_cone(e.pos, origin, dir, half, p.range + e.radius) {
            let mut h = Hit::simple(e.entity, source, p.damage, p.element, HitKind::Weapon, e.pos);
            h.crit_chance = p.crit_chance + crit_bonus;
            h.crit_mult = p.crit_mult;
            h.bonus = bonus;
            h.weapon = Some(p.clone());
            h.source_entity = Some(owner);
            h.knockback = (e.pos - origin).normalize_or_zero() * p.knockback;
            queue.0.push(h);
        }
    }
    if let Some(s) = p.splash.or(p.explode) {
        let center = origin + dir * p.range * 0.7;
        for e in grid.0.in_circle(center, s.radius) {
            let mut h = Hit::simple(e.entity, source, p.damage * s.damage, p.element, HitKind::Secondary, e.pos);
            h.weapon = Some(p.clone());
            queue.0.push(h);
        }
        events.0.push(GameEvent::Explosion {
            pos: gf_net::quant::QPos::from_vec2(center),
            radius_q: (s.radius * 32.0) as u16,
            element: p.element,
        });
    }
}

pub fn update_turrets(
    mut commands: Commands,
    clock: Res<SimClock>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    enemies: Query<&Vel, With<Enemy>>,
    mut turrets: Query<(Entity, &Pos, &mut Turret)>,
) {
    let dt = clock.gdt();
    for (entity, pos, mut t) in &mut turrets {
        t.remaining -= dt;
        if t.remaining <= 0.0 {
            commands.entity(entity).despawn();
            continue;
        }
        t.cooldown -= dt;
        if t.cooldown > 0.0 {
            continue;
        }
        let Some(target) = grid.0.nearest(pos.0, t.weapon.range, |_| true) else { continue };
        let vel = enemies.get(target.entity).map_or(Vec2::ZERO, |v| v.0);
        let aim = lead_point(pos.0, target.pos, vel, t.weapon.speed).unwrap_or(target.pos);
        let dir = (aim - pos.0).normalize_or(Vec2::X);
        t.cooldown += t.weapon.shot_interval().max(0.08);
        let profile = t.weapon.clone();
        spawn_volley(
            &mut commands,
            &mut ids,
            clock.tick,
            Volley {
                profile: &profile,
                origin: pos.0,
                dir,
                damage_scale: t.power,
                owner: t.owner,
                owner_entity: None,
                bonus: 1.0,
                crit_bonus: 0.0,
                precision_enabled: false,
                shot: 0,
                angle_offset_deg: 0.0,
            },
        );
    }
}

pub fn update_blades(
    clock: Res<SimClock>,
    grid: Res<Grid>,
    mut queue: ResMut<DamageQueue>,
    owners: Query<(&Pos, &Gun, &Life), (With<Player>, Without<Blade>)>,
    mut blades: Query<(&mut Pos, &mut Blade), Without<Player>>,
) {
    let dt = clock.gdt();
    let t = clock.time;
    for (mut pos, mut blade) in &mut blades {
        let Ok((owner_pos, gun, life)) = owners.get(blade.owner) else { continue };
        let angle = t * blade.speed * std::f32::consts::TAU
            + blade.index as f32 * std::f32::consts::TAU / blade.count.max(1) as f32;
        pos.0 = owner_pos.0 + gf_core::math::from_angle(angle) * blade.radius;
        for cd in blade.hit_cd.iter_mut() {
            cd.1 -= dt;
        }
        blade.hit_cd.retain(|(_, cd)| *cd > 0.0);
        if !life.state.is_alive() {
            continue;
        }
        let source = SourceId::player(blade.owner_slot);
        for e in grid.0.in_circle(pos.0, 0.55) {
            if blade.hit_cd.iter().any(|(h, _)| *h == e.entity) {
                continue;
            }
            blade.hit_cd.push((e.entity, 0.3));
            let mut h = Hit::simple(e.entity, source, blade.damage, gun.profile.element, HitKind::Secondary, e.pos);
            h.weapon = Some(gun.profile.clone());
            h.knockback = (e.pos - owner_pos.0).normalize_or_zero() * 2.0;
            queue.0.push(h);
        }
    }
}
