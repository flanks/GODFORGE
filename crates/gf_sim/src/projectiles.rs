//! Projectiles and the behaviours parts give them (ricochet, fork, chain, pierce, splash, wells,
//! puddles, trails, homing), enemy shots, hazards and barricades.

use crate::components::*;
use crate::resources::*;
use gf_core::aim::is_precision_hit;
use gf_core::ids::SourceId;
use gf_core::math::{dist_sq_point_segment, rotate, turn_toward};
use gf_core::weapon::WeaponProfile;
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{GameEvent, HazardKind};
use std::sync::Arc;

/// Cap on live player-made hazards (VFX budget and perf, §12).
const MAX_PLAYER_HAZARDS: usize = 90;

#[allow(clippy::too_many_arguments)]
fn spawn_hazard(
    commands: &mut Commands,
    ids: &mut NetIds,
    tick: u32,
    pos: Vec2,
    kind: HazardKind,
    radius: f32,
    duration: f32,
    dps: f32,
    element: gf_core::damage::DamageType,
    status: Option<(gf_core::status::StatusKind, u8, f32)>,
    slow: f32,
    pull: f32,
    owner: SourceId,
) {
    commands.spawn((
        Replicated(ids.alloc()),
        Pos(pos),
        RoomScoped,
        Hazard {
            team: Team::Players,
            kind,
            radius,
            remaining: duration,
            dps,
            element,
            status,
            slow,
            root: false,
            pull,
            owner,
            tick_timer: 0.0,
            ally_mods: Vec::new(),
            taunt: false,
            bonus_drops: false,
            vel: Vec2::ZERO,
            origin: pos,
            t0: tick,
        },
    ));
}

/// Weapon-hit context shared by direct and secondary hits.
fn weapon_hit(
    target: Entity,
    at: Vec2,
    base: f32,
    kind: HitKind,
    p: &Projectile,
    w: &Arc<WeaponProfile>,
    precision: bool,
    precision_bonus: f32,
) -> Hit {
    Hit {
        target,
        source: p.owner,
        source_entity: p.owner_entity,
        base,
        element: w.element,
        crit_chance: w.crit_chance + p.crit_bonus,
        crit_mult: w.crit_mult,
        bonus: p.bonus,
        precision,
        precision_crit_bonus: precision_bonus,
        knockback: p.dir * w.knockback * if kind == HitKind::Weapon { 1.0 } else { 0.3 },
        weapon: Some(w.clone()),
        kind,
        status: None,
        stun: 0.0,
        pos: at,
    }
}

#[allow(clippy::type_complexity)]
pub fn move_projectiles(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    arena: Res<ArenaRes>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    mut queue: ResMut<DamageQueue>,
    mut events: ResMut<Events>,
    hazards: Query<&Hazard>,
    mut aims: Query<(&Player, &mut Aim)>,
    mut projectiles: Query<(Entity, &mut Projectile, &mut Pos)>,
) {
    let dt = clock.gdt();
    let tick = clock.tick;
    let manual = content.aim_params(gf_core::aim::AimMode::Manual);
    let mut hazard_budget =
        MAX_PLAYER_HAZARDS.saturating_sub(hazards.iter().filter(|h| h.team == Team::Players).count());
    let mut misses: Vec<u8> = Vec::new();
    for (entity, mut p, mut pos) in &mut projectiles {
        let w = p.weapon.clone();
        // Homing.
        if w.homing > 0.0
            && let Some(t) = grid.0.nearest(pos.0, 7.0, |e| !p.hits.contains(&e.entity))
        {
            p.dir = turn_toward(p.dir, t.pos - pos.0, w.homing * dt);
            p.steered = true;
        }
        let prev = pos.0;
        let next = prev + p.dir * p.speed * dt;
        p.life -= dt;
        let blocked = arena.0.obstacles.iter().any(|o| o.contains(next, 0.0));
        if p.life <= 0.0 || blocked || !arena.0.in_bounds(next) {
            if !p.any_hit
                && p.precision_enabled
                && let Some(slot) = p.owner.owner_slot()
            {
                misses.push(slot);
            }
            commands.entity(entity).despawn();
            continue;
        }
        pos.0 = next;

        // Trails (Frostwake).
        if let Some(trail) = w.trail {
            p.trail_timer -= dt;
            if p.trail_timer <= 0.0 && hazard_budget > 0 {
                p.trail_timer = 0.15;
                hazard_budget -= 1;
                spawn_hazard(
                    &mut commands,
                    &mut ids,
                    tick,
                    pos.0,
                    HazardKind::Trail,
                    0.8,
                    trail.duration,
                    w.damage * trail.dps,
                    w.element,
                    None,
                    trail.slow,
                    0.0,
                    p.owner,
                );
            }
        }

        // Swept collision: every enemy whose circle meets the segment this tick, nearest first.
        let mut candidates: Vec<(f32, crate::spatial::GridEntry)> = Vec::new();
        grid.0.for_each_in_circle(prev.lerp(next, 0.5), prev.distance(next) * 0.5 + p.radius, |e| {
            let r = e.radius + p.radius;
            if !p.hits.contains(&e.entity) && dist_sq_point_segment(e.pos, prev, next) <= r * r {
                candidates.push((e.pos.distance_squared(prev), *e));
            }
        });
        candidates.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.entity.cmp(&b.1.entity)));
        let mut despawn = false;
        for (_, e) in candidates {
            p.hits.push(e.entity);
            let first_hit = !p.any_hit;
            p.any_hit = true;
            let precision = p.precision_enabled && is_precision_hit(prev, p.dir, e.pos, e.radius, w.precision_zone);
            queue.0.push(weapon_hit(
                e.entity,
                e.pos,
                p.damage,
                HitKind::Weapon,
                &p,
                &w,
                precision,
                manual.precision_crit_bonus,
            ));

            // Splash / explode.
            for s in [w.splash, w.explode].into_iter().flatten() {
                for o in grid.0.in_circle(e.pos, s.radius) {
                    if o.entity != e.entity {
                        queue.0.push(weapon_hit(
                            o.entity,
                            o.pos,
                            p.damage * s.damage,
                            HitKind::Secondary,
                            &p,
                            &w,
                            false,
                            0.0,
                        ));
                    }
                }
                events.0.push(GameEvent::Explosion {
                    pos: QPos::from_vec2(e.pos),
                    radius_q: (s.radius * 32.0) as u16,
                    element: w.element,
                });
            }
            // Chain arcs.
            if let Some(c) = w.chain {
                let mut from = e.pos;
                let mut chained = vec![e.entity];
                let mut dmg = p.damage;
                for _ in 0..c.jumps {
                    let Some(n) = grid.0.nearest(from, c.range, |x| !chained.contains(&x.entity)) else { break };
                    dmg *= c.falloff;
                    chained.push(n.entity);
                    queue.0.push(weapon_hit(n.entity, n.pos, dmg, HitKind::Secondary, &p, &w, false, 0.0));
                    events.0.push(GameEvent::Arc {
                        from: QPos::from_vec2(from),
                        to: QPos::from_vec2(n.pos),
                        element: w.element,
                    });
                    from = n.pos;
                }
            }
            // Wells and puddles on the first impact.
            if first_hit && hazard_budget > 0 {
                if let Some(well) = w.gravity_well {
                    hazard_budget -= 1;
                    spawn_hazard(
                        &mut commands,
                        &mut ids,
                        tick,
                        e.pos,
                        HazardKind::Well,
                        well.radius,
                        well.duration,
                        w.damage * well.dps,
                        w.element,
                        None,
                        0.0,
                        well.pull,
                        p.owner,
                    );
                }
                if let Some(pd) = w.puddle
                    && hazard_budget > 0
                {
                    hazard_budget -= 1;
                    spawn_hazard(
                        &mut commands,
                        &mut ids,
                        tick,
                        e.pos,
                        HazardKind::Puddle,
                        pd.radius,
                        pd.duration,
                        w.damage * pd.dps,
                        w.element,
                        pd.status.map(|s| (s, 1, 2.0)),
                        0.15,
                        0.0,
                        p.owner,
                    );
                }
            }
            // Fork (first hit only).
            if let Some(f) = w.fork
                && !p.forked
            {
                p.forked = true;
                for k in 0..f.count {
                    let t = if f.count == 1 { 0.0 } else { -0.5 + k as f32 / (f.count - 1) as f32 };
                    let dir = rotate(p.dir, (t * f.angle).to_radians());
                    commands.spawn((
                        Replicated(ids.alloc()),
                        Pos(e.pos + dir * (e.radius + 0.2)),
                        RoomScoped,
                        Projectile {
                            owner: p.owner,
                            owner_entity: p.owner_entity,
                            weapon: w.clone(),
                            damage: p.damage * f.damage,
                            dir,
                            speed: p.speed,
                            radius: p.radius * 0.8,
                            life: (p.life * 0.6).max(0.25),
                            pierce: 0,
                            bounces: 0,
                            forked: true,
                            hits: vec![e.entity],
                            shot: p.shot,
                            any_hit: true,
                            trail_timer: 1.0,
                            bonus: p.bonus,
                            crit_bonus: p.crit_bonus,
                            precision_enabled: false,
                            origin: e.pos,
                            t0: tick,
                            steered: false,
                        },
                    ));
                }
            }
            // Ricochet redirects; pierce continues; otherwise the projectile is spent.
            if p.bounces > 0
                && let Some(r) = w.ricochet
                && let Some(n) = grid.0.nearest(e.pos, r.range, |x| !p.hits.contains(&x.entity))
            {
                p.bounces -= 1;
                p.dir = (n.pos - e.pos).normalize_or(p.dir);
                pos.0 = e.pos + p.dir * (e.radius + p.radius + 0.05);
                p.life = p.life.max(r.range / p.speed.max(1.0) + 0.1);
                p.steered = true;
                break;
            }
            if p.pierce > 0 {
                p.pierce -= 1;
                continue;
            }
            despawn = true;
            break;
        }
        if despawn {
            commands.entity(entity).despawn();
            continue;
        }
        if p.steered {
            p.steered = false;
            p.origin = pos.0;
            p.t0 = tick;
        }
    }
    if !misses.is_empty() {
        for (player, mut aim) in &mut aims {
            if misses.contains(&player.slot) && aim.mode == gf_core::aim::AimMode::Manual {
                aim.deadeye.on_miss();
            }
        }
    }
}

pub fn move_enemy_shots(
    mut commands: Commands,
    clock: Res<SimClock>,
    arena: Res<ArenaRes>,
    mut hits: ResMut<PlayerHits>,
    players: Query<(Entity, &Pos, &Life, &Stats), With<Player>>,
    mut barricades: Query<(&Pos, &mut Barricade), Without<EnemyShot>>,
    mut shots: Query<(Entity, &mut Pos, &mut EnemyShot), (Without<Player>, Without<Barricade>)>,
) {
    let dt = clock.gdt();
    let frozen = clock.freeze > 0.0;
    for (entity, mut pos, mut s) in &mut shots {
        if frozen {
            continue;
        }
        s.life -= dt;
        let next = pos.0 + s.dir * s.speed * dt;
        if s.life <= 0.0 || !arena.0.in_bounds(next) || arena.0.obstacles.iter().any(|o| o.contains(next, 0.0)) {
            commands.entity(entity).despawn();
            continue;
        }
        pos.0 = next;
        let mut gone = false;
        for (bpos, mut b) in &mut barricades {
            let a = bpos.0 - b.along * b.half_len;
            let c = bpos.0 + b.along * b.half_len;
            if dist_sq_point_segment(pos.0, a, c) <= (s.radius + 0.35).powi(2) {
                b.hp -= s.damage;
                gone = true;
                break;
            }
        }
        if !gone {
            for (pe, ppos, life, stats) in &players {
                if life.state.is_alive() && ppos.0.distance(pos.0) <= s.radius + stats.0.radius {
                    hits.0.push(PlayerHit {
                        target: pe,
                        amount: s.damage,
                        element: gf_core::damage::DamageType::Flame,
                        from: pos.0,
                    });
                    gone = true;
                    break;
                }
            }
        }
        if gone {
            commands.entity(entity).despawn();
        }
    }
}

/// Hazard ticks: damage/slow/root/pull/taunt for player hazards, damage for enemy pools, and
/// ally buffs inside fields (Heaven's Verdict supercharges projectiles fired from inside it).
#[allow(clippy::type_complexity)]
pub fn update_hazards(
    mut commands: Commands,
    clock: Res<SimClock>,
    arena: Res<ArenaRes>,
    grid: Res<Grid>,
    mut queue: ResMut<DamageQueue>,
    mut phits: ResMut<PlayerHits>,
    mut hazards: Query<(Entity, &mut Pos, &mut Hazard), (Without<Enemy>, Without<Player>)>,
    mut enemies: Query<(&Pos, &mut Enemy), (Without<Hazard>, Without<Player>)>,
    mut players: Query<(Entity, &Pos, &Life, &mut Kit), (With<Player>, Without<Hazard>, Without<Enemy>)>,
) {
    let dt = clock.gdt();
    for (_, mut e) in &mut enemies {
        e.slow = 0.0;
        e.rooted_by_field = false;
    }
    let mut field_mods: Vec<(Entity, Vec<gf_core::modifier::Modifier>)> = Vec::new();
    for (entity, mut pos, mut h) in &mut hazards {
        h.remaining -= dt;
        if h.remaining <= 0.0 {
            commands.entity(entity).despawn();
            continue;
        }
        if h.vel != Vec2::ZERO {
            pos.0 = arena.0.resolve(pos.0 + h.vel * dt, 0.1);
        }
        h.tick_timer -= dt;
        let pulse = h.tick_timer <= 0.0;
        if pulse {
            h.tick_timer += 0.25;
        }
        match h.team {
            Team::Players => {
                for g in grid.0.in_circle(pos.0, h.radius) {
                    if let Ok((_, mut enemy)) = enemies.get_mut(g.entity) {
                        enemy.slow = enemy.slow.max(h.slow);
                        enemy.rooted_by_field |= h.root;
                        enemy.bonus_drops |= h.bonus_drops;
                        if h.pull > 0.0 {
                            let to = pos.0 - g.pos;
                            if to.length() > 0.3 {
                                let mass = enemy.mass.max(0.5);
                                enemy.knock += to.normalize() * h.pull * dt * 6.0 / mass;
                            }
                        }
                    }
                    if pulse && (h.dps > 0.0 || h.status.is_some()) {
                        let mut hit = Hit::simple(g.entity, h.owner, h.dps * 0.25, h.element, HitKind::Hazard, g.pos);
                        hit.status = h.status;
                        queue.0.push(hit);
                    }
                }
                if h.taunt {
                    for g in grid.0.in_circle(pos.0, 9.0) {
                        if let Ok((_, mut enemy)) = enemies.get_mut(g.entity) {
                            enemy.taunt = Some((entity, 0.3));
                        }
                    }
                }
                if !h.ally_mods.is_empty() {
                    for (pe, ppos, life, _) in &players {
                        if life.state.is_alive() && ppos.0.distance(pos.0) <= h.radius {
                            field_mods.push((pe, h.ally_mods.clone()));
                        }
                    }
                }
            }
            Team::Enemies => {
                if pulse {
                    for (pe, ppos, life, _) in &players {
                        if life.state.is_alive() && ppos.0.distance(pos.0) <= h.radius {
                            phits.0.push(PlayerHit {
                                target: pe,
                                amount: h.dps * 0.25,
                                element: h.element,
                                from: pos.0,
                            });
                        }
                    }
                }
            }
        }
    }
    for (pe, _, _, mut kit) in &mut players {
        let mods: Vec<_> = field_mods.iter().filter(|(e, _)| *e == pe).flat_map(|(_, m)| m.iter().cloned()).collect();
        if mods != kit.in_field_mods {
            kit.in_field_mods = mods;
            kit.dirty = true;
        }
    }
}

pub fn update_barricades(mut commands: Commands, clock: Res<SimClock>, mut q: Query<(Entity, &mut Barricade)>) {
    for (e, mut b) in &mut q {
        b.remaining -= clock.gdt();
        if b.remaining <= 0.0 || b.hp <= 0.0 {
            commands.entity(e).despawn();
        }
    }
}
