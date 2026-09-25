//! Actives, ultimates and passives. Kits are data (`kits.ron`): each ability is a list of
//! [`AbilityStep`] primitives implemented once here — the 8 → 12 roster expansion is content work.

use crate::components::*;
use crate::resources::*;
use gf_content::schema::{AbilityStep, Anchor, PassiveDef, StatusOnHit, TelegraphShape};
use gf_core::damage::DamageType;
use gf_core::ids::SourceId;
use gf_core::math::{dist_sq_point_segment, in_cone};
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{GameEvent, HazardKind};

pub fn update_kits(
    mut clock: ResMut<SimClock>,
    content: Res<Content>,
    grid: Res<Grid>,
    mut queue: ResMut<DamageQueue>,
    mut q: Query<(&Player, &Pos, &Stats, &mut Kit)>,
) {
    let dt = clock.gdt();
    let reset = std::mem::take(&mut clock.reset_cooldowns);
    for (player, pos, stats, mut kit) in &mut q {
        let rate = stats.0.cooldown_rate;
        for cd in kit.cooldowns.iter_mut() {
            *cd = if reset { 0.0 } else { (*cd - dt * rate).max(0.0) };
        }
        let source = SourceId::player(player.slot);
        let mut expired = false;
        for buff in kit.buffs.iter_mut() {
            buff.remaining -= dt;
            if let Some(pulse) = buff.pulse {
                buff.pulse_timer -= dt;
                if buff.pulse_timer <= 0.0 {
                    buff.pulse_timer += pulse.interval;
                    for e in grid.0.in_circle(pos.0, pulse.radius) {
                        let mut h = Hit::simple(
                            e.entity,
                            source,
                            pulse.damage * stats.0.active_damage,
                            pulse.element,
                            HitKind::Ability,
                            e.pos,
                        );
                        h.knockback = (e.pos - pos.0).normalize_or_zero() * pulse.knockback;
                        queue.0.push(h);
                    }
                }
            }
            expired |= buff.remaining <= 0.0;
        }
        if expired {
            kit.buffs.retain(|b| b.remaining > 0.0);
            kit.dirty = true;
        }
        match &mut kit.passive {
            PassiveState::Armor { break_cd, .. } => *break_cd = (*break_cd - dt).max(0.0),
            PassiveState::Ghost { crit } => {
                if let Some(PassiveDef::GhostStep { decay_per_s, .. }) =
                    content.kit(player.character).map(|k| &k.passive)
                {
                    *crit = (*crit - decay_per_s * dt).max(0.0);
                }
            }
            _ => {}
        }
    }
}

/// Everything a step needs to know about its caster.
struct Caster {
    entity: Entity,
    slot: u8,
    pos: Vec2,
    aim_dir: Vec2,
    aim_point: Vec2,
    damage_mult: f32,
    fire_rate: f32,
    weapon: std::sync::Arc<gf_core::weapon::WeaponProfile>,
}

fn anchor(c: &Caster, at: Anchor) -> Vec2 {
    match at {
        Anchor::SelfPos => c.pos,
        Anchor::AimPoint { range } => {
            let d = c.aim_point - c.pos;
            c.pos + d.clamp_length_max(range)
        }
    }
}

fn status_tuple(s: Option<StatusOnHit>) -> Option<(gf_core::status::StatusKind, u8, f32)> {
    s.map(|s| (s.status, s.stacks, s.duration))
}

/// Side effects on other entities, applied after the caster loop.
#[derive(Default)]
struct Deferred {
    shields: Vec<(Vec2, f32, f32)>,
    rewinds: Vec<(Vec2, f32, f32)>,
    taunts: Vec<(Vec2, f32, f32, Entity)>,
}

#[allow(clippy::too_many_arguments)]
fn run_steps(
    steps: &[AbilityStep],
    which: u8,
    c: &Caster,
    kit: &mut Kit,
    mover: &mut Mover,
    vitals: &mut Vitals,
    gun: &mut Gun,
    stats: &Stats,
    ctx: &mut CastCtx,
    deferred: &mut Deferred,
) {
    let source = SourceId::player(c.slot);
    for (i, step) in steps.iter().enumerate() {
        match step {
            AbilityStep::Leap { range, time } => {
                let to = ctx.arena.0.resolve(c.pos + (c.aim_point - c.pos).clamp_length_max(*range), stats.0.radius);
                kit.airborne = Some(Airborne { from: c.pos, to, t: 0.0, total: time.max(0.05) });
                queue_rest(kit, which, &steps[i + 1..], c);
                return;
            }
            AbilityStep::Rush { distance, time, damage, element, drag } => {
                kit.rush = Some(Rush {
                    dir: c.aim_dir,
                    speed: distance / time.max(0.05),
                    remaining: *time,
                    damage: damage * c.damage_mult,
                    element: *element,
                    drag: *drag,
                    hit: Vec::new(),
                });
                queue_rest(kit, which, &steps[i + 1..], c);
                return;
            }
            AbilityStep::Blink { range, trail_damage, element } => {
                let to = ctx.arena.0.resolve(c.pos + c.aim_dir * *range, stats.0.radius);
                if *trail_damage > 0.0 {
                    let mut hit = Vec::new();
                    let samples = (c.pos.distance(to) / 0.8).ceil().max(1.0) as usize;
                    for s in 0..=samples {
                        let p = c.pos.lerp(to, s as f32 / samples as f32);
                        for e in ctx.grid.0.in_circle(p, 0.9) {
                            if !hit.contains(&e.entity) {
                                hit.push(e.entity);
                                ctx.queue.0.push(Hit::simple(
                                    e.entity,
                                    source,
                                    trail_damage * c.damage_mult,
                                    *element,
                                    HitKind::Ability,
                                    e.pos,
                                ));
                            }
                        }
                    }
                    ctx.events.0.push(GameEvent::Arc {
                        from: QPos::from_vec2(c.pos),
                        to: QPos::from_vec2(to),
                        element: *element,
                    });
                }
                mover.0.pos = to;
                mover.0.iframes = mover.0.iframes.max(0.25);
            }
            AbilityStep::Nova { radius, damage, element, at, stun, knockback, status, delay } => {
                let center =
                    if kit.airborne.is_none() && matches!(at, Anchor::SelfPos) { mover.0.pos } else { anchor(c, *at) };
                if *delay > 0.0 {
                    ctx.commands.spawn((
                        Replicated(ctx.ids.alloc()),
                        Pos(center),
                        RoomScoped,
                        Telegraph {
                            team: Team::Players,
                            shape: TelegraphShape::Circle { radius: *radius },
                            dir: c.aim_dir,
                            total: *delay,
                            remaining: *delay,
                            damage: damage * c.damage_mult,
                            element: *element,
                            start_tick: ctx.tick,
                            effect: TeleEffect::PlayerNova {
                                stun: *stun,
                                knockback: *knockback,
                                status: status_tuple(*status),
                                source,
                            },
                            owner: Some(c.entity),
                        },
                    ));
                } else {
                    nova(
                        ctx,
                        source,
                        center,
                        *radius,
                        damage * c.damage_mult,
                        *element,
                        *stun,
                        *knockback,
                        status_tuple(*status),
                    );
                }
            }
            AbilityStep::Line { length, width, damage, element, status } => {
                let a = mover.0.pos;
                let b = a + c.aim_dir * *length;
                for e in ctx.grid.0.in_circle(a.lerp(b, 0.5), length * 0.5 + width) {
                    let r = width * 0.5 + e.radius;
                    if dist_sq_point_segment(e.pos, a, b) <= r * r {
                        let mut h =
                            Hit::simple(e.entity, source, damage * c.damage_mult, *element, HitKind::Ability, e.pos);
                        h.status = status_tuple(*status);
                        ctx.queue.0.push(h);
                    }
                }
                ctx.events.0.push(GameEvent::Arc {
                    from: QPos::from_vec2(a),
                    to: QPos::from_vec2(b),
                    element: *element,
                });
            }
            AbilityStep::Cone { range, angle_deg, damage, element, status } => {
                let half = angle_deg.to_radians() * 0.5;
                for e in ctx.grid.0.in_circle(mover.0.pos, *range) {
                    if in_cone(e.pos, mover.0.pos, c.aim_dir, half, range + e.radius) {
                        let mut h =
                            Hit::simple(e.entity, source, damage * c.damage_mult, *element, HitKind::Ability, e.pos);
                        h.status = status_tuple(*status);
                        h.knockback = (e.pos - mover.0.pos).normalize_or_zero() * 3.0;
                        ctx.queue.0.push(h);
                    }
                }
            }
            AbilityStep::ChainBurst { targets, range, damage, element, scale_with_fire_rate } => {
                let scale = if *scale_with_fire_rate { (c.fire_rate / 3.0).clamp(0.6, 3.0) } else { 1.0 };
                let mut from = mover.0.pos;
                let mut hit: Vec<Entity> = Vec::new();
                for _ in 0..*targets {
                    let Some(next) = ctx.grid.0.nearest(from, *range, |e| !hit.contains(&e.entity)) else { break };
                    hit.push(next.entity);
                    let mut h = Hit::simple(
                        next.entity,
                        source,
                        damage * c.damage_mult * scale,
                        *element,
                        HitKind::Ability,
                        next.pos,
                    );
                    h.status = Some((gf_core::status::StatusKind::Shock, 1, 2.0));
                    ctx.queue.0.push(h);
                    ctx.events.0.push(GameEvent::Arc {
                        from: QPos::from_vec2(from),
                        to: QPos::from_vec2(next.pos),
                        element: *element,
                    });
                    from = next.pos;
                }
            }
            AbilityStep::Barricade { length, hp, duration, offset } => {
                let center = ctx.arena.0.resolve(mover.0.pos + c.aim_dir * *offset, 0.3);
                ctx.commands.spawn((
                    Replicated(ctx.ids.alloc()),
                    Pos(center),
                    RoomScoped,
                    Barricade { half_len: length * 0.5, along: c.aim_dir.perp(), hp: *hp, remaining: *duration },
                ));
            }
            AbilityStep::Turret { power, duration, count } => {
                for k in 0..*count {
                    let offset = gf_core::math::from_angle(k as f32 * 2.1 + 0.6) * 1.4;
                    ctx.commands.spawn((
                        Replicated(ctx.ids.alloc()),
                        Pos(ctx.arena.0.resolve(mover.0.pos + offset, 0.4)),
                        RoomScoped,
                        Turret {
                            owner: SourceId::turret(c.slot),
                            owner_slot: c.slot,
                            weapon: c.weapon.clone(),
                            power: *power,
                            remaining: *duration,
                            cooldown: 0.2 * k as f32,
                        },
                    ));
                }
            }
            AbilityStep::Buff { duration, mods, root_self, taunt, scale, pulse, infinite_dash } => {
                kit.buffs.push(ActiveBuff {
                    remaining: *duration,
                    mods: mods.clone(),
                    root_self: *root_self,
                    taunt: *taunt,
                    scale: *scale,
                    pulse: *pulse,
                    pulse_timer: pulse.map_or(0.0, |p| p.interval * 0.5),
                    infinite_dash: *infinite_dash,
                    source: which,
                });
                kit.dirty = true;
                if *taunt {
                    deferred.taunts.push((mover.0.pos, 14.0, *duration, c.entity));
                }
            }
            AbilityStep::Field {
                radius,
                duration,
                at,
                dps,
                element,
                slow,
                root,
                status,
                ally_mods,
                travel_speed,
                bonus_drops,
                taunt,
            } => {
                let center = anchor(c, *at);
                ctx.commands.spawn((
                    Replicated(ctx.ids.alloc()),
                    Pos(center),
                    RoomScoped,
                    Hazard {
                        team: Team::Players,
                        kind: HazardKind::Field,
                        radius: *radius,
                        remaining: *duration,
                        dps: dps * c.damage_mult,
                        element: *element,
                        status: status_tuple(*status),
                        slow: *slow,
                        root: *root,
                        pull: 0.0,
                        owner: source,
                        tick_timer: 0.0,
                        ally_mods: ally_mods.clone(),
                        taunt: *taunt,
                        bonus_drops: *bonus_drops,
                        vel: c.aim_dir * *travel_speed,
                        origin: center,
                        t0: ctx.tick,
                    },
                ));
            }
            AbilityStep::Taunt { radius, duration } => {
                deferred.taunts.push((mover.0.pos, *radius, *duration, c.entity));
            }
            AbilityStep::Shield { amount, radius } => {
                if *radius <= 0.0 {
                    vitals.bonus_shield += amount;
                } else {
                    deferred.shields.push((mover.0.pos, *radius, *amount));
                }
            }
            AbilityStep::RewindWounds { seconds, range } => {
                deferred.rewinds.push((mover.0.pos, *range, *seconds));
            }
            AbilityStep::TimeStop { duration, reset_ally_cooldowns } => {
                ctx.freeze = Some((*duration, *reset_ally_cooldowns));
            }
            AbilityStep::RefillDash => {
                mover.0.dash_charges = stats.0.dash_charges;
            }
            AbilityStep::NextShots { count, mods } => {
                gun.next_shots = Some((*count, mods.clone()));
                kit.dirty = true;
            }
        }
    }
}

fn queue_rest(kit: &mut Kit, which: u8, rest: &[AbilityStep], c: &Caster) {
    kit.pending = (!rest.is_empty()).then(|| PendingSteps {
        which,
        steps: rest.to_vec(),
        damage_mult: c.damage_mult,
        aim_dir: c.aim_dir,
        aim_point: c.aim_point,
    });
}

#[allow(clippy::too_many_arguments)]
fn nova(
    ctx: &mut CastCtx,
    source: SourceId,
    center: Vec2,
    radius: f32,
    damage: f32,
    element: DamageType,
    stun: f32,
    knockback: f32,
    status: Option<(gf_core::status::StatusKind, u8, f32)>,
) {
    for e in ctx.grid.0.in_circle(center, radius) {
        let mut h = Hit::simple(e.entity, source, damage, element, HitKind::Ability, e.pos);
        h.knockback = (e.pos - center).normalize_or_zero() * knockback;
        h.stun = stun;
        h.status = status;
        ctx.queue.0.push(h);
    }
    ctx.events.0.push(GameEvent::Explosion { pos: QPos::from_vec2(center), radius_q: (radius * 32.0) as u16, element });
}

struct CastCtx<'a, 'w, 's> {
    commands: Commands<'w, 's>,
    ids: &'a mut NetIds,
    queue: &'a mut DamageQueue,
    events: &'a mut Events,
    grid: &'a Grid,
    arena: &'a ArenaRes,
    tick: u32,
    freeze: Option<(f32, bool)>,
}

#[allow(clippy::type_complexity)]
pub fn cast_abilities(
    commands: Commands,
    mut clock: ResMut<SimClock>,
    content: Res<Content>,
    arena: Res<ArenaRes>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    mut queue: ResMut<DamageQueue>,
    mut events: ResMut<Events>,
    mut enemies: Query<(&Pos, &mut Enemy), Without<Player>>,
    mut q: Query<
        (
            Entity,
            &Player,
            &PlayerInput,
            &Stats,
            &mut Kit,
            &Life,
            &mut Mover,
            &mut Vitals,
            &mut Gun,
            &DamageHistory,
            &mut Pos,
        ),
        Without<Enemy>,
    >,
) {
    let mut ctx = CastCtx {
        commands,
        ids: &mut ids,
        queue: &mut queue,
        events: &mut events,
        grid: &grid,
        arena: &arena,
        tick: clock.tick,
        freeze: None,
    };
    let mut deferred = Deferred::default();
    for (entity, player, input, stats, mut kit, life, mut mover, mut vitals, mut gun, _, mut pos) in &mut q {
        if !life.state.is_alive() {
            kit.pending = None;
            continue;
        }
        let Some(kitdef) = content.kit(player.character) else { continue };
        let busy = kit.airborne.is_some() || kit.rush.is_some();
        // Continue a leap/rush follow-up once landed.
        if !busy && let Some(pending) = kit.pending.take() {
            let c = Caster {
                entity,
                slot: player.slot,
                pos: mover.0.pos,
                aim_dir: pending.aim_dir,
                aim_point: pending.aim_point,
                damage_mult: pending.damage_mult,
                fire_rate: gun.profile.fire_rate,
                weapon: gun.profile.clone(),
            };
            run_steps(
                &pending.steps,
                pending.which,
                &c,
                &mut kit,
                &mut mover,
                &mut vitals,
                &mut gun,
                stats,
                &mut ctx,
                &mut deferred,
            );
            pos.0 = mover.0.pos;
            continue;
        }
        if busy || kit.pending.is_some() {
            continue;
        }
        let which = if input.new.ult > 0 && kit.ult >= 1.0 {
            Some(2u8)
        } else if input.new.active1 > 0 && kit.cooldowns[0] <= 0.0 {
            Some(0)
        } else if input.new.active2 > 0 && kit.cooldowns[1] <= 0.0 {
            Some(1)
        } else {
            None
        };
        let Some(which) = which else { continue };
        let ability = match which {
            0 => &kitdef.active1,
            1 => &kitdef.active2,
            _ => &kitdef.ultimate,
        };
        match which {
            2 => kit.ult = 0.0,
            w => kit.cooldowns[w as usize] = ability.cooldown,
        }
        let mut damage_mult = stats.0.active_damage;
        if let PassiveState::Static { charge } = &mut kit.passive {
            damage_mult *= 1.0 + *charge;
            *charge = 0.0;
        }
        let aim_dir = if input.aim_dir.length_squared() > 0.0 { input.aim_dir } else { Vec2::Y };
        let c = Caster {
            entity,
            slot: player.slot,
            pos: mover.0.pos,
            aim_dir,
            aim_point: input.aim_point,
            damage_mult,
            fire_rate: gun.profile.fire_rate,
            weapon: gun.profile.clone(),
        };
        ctx.events.0.push(GameEvent::Ability { slot: player.slot, which, pos: QPos::from_vec2(mover.0.pos) });
        if which == 2
            && let Some(g) = stats.0.ult_ground
        {
            ctx.commands.spawn((
                Replicated(ctx.ids.alloc()),
                Pos(mover.0.pos),
                RoomScoped,
                Hazard {
                    team: Team::Players,
                    kind: HazardKind::Ground,
                    radius: g.radius,
                    remaining: g.duration,
                    dps: g.dps,
                    element: g.element,
                    status: None,
                    slow: 0.0,
                    root: false,
                    pull: 0.0,
                    owner: SourceId::player(player.slot),
                    tick_timer: 0.0,
                    ally_mods: Vec::new(),
                    taunt: false,
                    bonus_drops: false,
                    vel: Vec2::ZERO,
                    origin: mover.0.pos,
                    t0: ctx.tick,
                },
            ));
        }
        run_steps(
            &ability.steps,
            which,
            &c,
            &mut kit,
            &mut mover,
            &mut vitals,
            &mut gun,
            stats,
            &mut ctx,
            &mut deferred,
        );
        pos.0 = mover.0.pos;
    }
    if let Some((duration, reset)) = ctx.freeze {
        clock.freeze = clock.freeze.max(duration);
        clock.freeze_resets_cooldowns |= reset;
    }
    // Deferred effects on allies and enemies.
    for (center, radius, duration, taunter) in deferred.taunts {
        for (pos, mut enemy) in &mut enemies {
            if pos.0.distance(center) <= radius {
                enemy.taunt = Some((taunter, duration));
            }
        }
    }
    for (center, radius, amount) in deferred.shields {
        for (.., mut vitals, _, _, pos) in &mut q {
            if pos.0.distance(center) <= radius {
                vitals.bonus_shield += amount;
            }
        }
    }
    for (center, range, seconds) in deferred.rewinds {
        let now = clock.tick;
        let window = (seconds / clock.dt) as u32;
        let best = q
            .iter()
            .filter(|(.., pos)| pos.0.distance(center) <= range)
            .map(|(e, _, _, _, _, _, _, _, _, hist, _)| {
                let taken: f32 = hist.0.iter().filter(|(t, _)| now.saturating_sub(*t) <= window).map(|(_, a)| a).sum();
                (e, taken)
            })
            .max_by(|a, b| a.1.total_cmp(&b.1));
        if let Some((target, amount)) = best
            && let Ok((.., stats, _, life, _, mut vitals, _, _, _)) = q.get_mut(target)
            && life.state.is_alive()
        {
            vitals.hp = (vitals.hp + amount).min(stats.0.max_hp);
        }
    }
}

/// Valdris — Reforged Flesh. Returns damage that reaches HP and whether armor broke this hit.
pub fn armor_conversion(passive: &mut PassiveState, def: &PassiveDef, incoming: f32) -> (f32, bool) {
    let (
        PassiveState::Armor { armor, break_cd },
        PassiveDef::ArmorConversion { conversion, max_armor, max_mitigation, .. },
    ) = (passive, def)
    else {
        return (incoming, false);
    };
    let had = *armor > 0.0;
    let absorb = (incoming * max_mitigation).min(*armor);
    *armor -= absorb;
    let to_hp = incoming - absorb;
    let broke = had && *armor <= 0.0 && *break_cd <= 0.0;
    *armor = (*armor + to_hp * conversion).min(*max_armor);
    (to_hp, broke)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valdris() -> PassiveDef {
        PassiveDef::ArmorConversion {
            conversion: 0.5,
            max_armor: 90.0,
            max_mitigation: 0.5,
            break_radius: 5.0,
            break_damage: 60.0,
            break_knockback: 8.0,
            break_taunt: 3.0,
            break_cooldown: 6.0,
        }
    }

    #[test]
    fn reforged_flesh_builds_mitigates_and_breaks() {
        let def = valdris();
        let mut p = PassiveState::Armor { armor: 0.0, break_cd: 0.0 };
        // First hit: no armor yet, full damage, half converts to armor.
        let (hp, broke) = armor_conversion(&mut p, &def, 40.0);
        assert_eq!(hp, 40.0);
        assert!(!broke);
        assert!(matches!(p, PassiveState::Armor { armor, .. } if (armor - 20.0).abs() < 1e-4));
        // Second hit: armor absorbs up to 50% (capped by armor pool) and breaks.
        let (hp, broke) = armor_conversion(&mut p, &def, 60.0);
        assert!((hp - 40.0).abs() < 1e-4, "{hp}");
        assert!(broke, "armor emptied → shockwave taunt");
    }
}
