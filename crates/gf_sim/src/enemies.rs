//! Enemies: spawning from content, behaviour AI, boss scripts, motion & separation, contact damage
//! and telegraphs. Every enemy attack except contact resolves through a visible telegraph with a
//! wind-up — "no invisible damage" (§5).

use crate::components::*;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::{BossAttack, EnemyBehavior, EnemyClass, TelegraphShape};
use gf_core::ids::{EnemyId, SourceId};
use gf_core::math::{dist_sq_point_segment, from_angle, in_cone, rotate};
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{GameEvent, HazardKind};

#[allow(clippy::too_many_arguments)]
pub fn spawn_enemy(
    commands: &mut Commands,
    ids: &mut NetIds,
    db: &ContentDb,
    tuning: &Tuning,
    hp_mult: f32,
    def: EnemyId,
    pos: Vec2,
    rng: &mut GfRng,
) -> Entity {
    let d = db.enemy(def);
    let boss_like = matches!(d.class, EnemyClass::MiniBoss | EnemyClass::Boss);
    let mult = if boss_like { tuning.enemy.boss_hp } else { tuning.enemy.hp } * hp_mult;
    let hp = d.hp * mult;
    let elite = d.class == EnemyClass::Elite;
    let shield = d.shield * mult + if elite { hp * tuning.enemy.elite_shield } else { 0.0 };
    let enemy = Enemy {
        def,
        class: d.class,
        hp,
        max_hp: hp,
        shield,
        plating: d.plating.clone(),
        resist: d.resist,
        speed: d.speed,
        radius: d.radius * d.scale.max(0.5),
        mass: d.mass,
        contact: d.contact_damage,
        damage_mult: 1.0,
        elite,
        doom: 0,
        stun: 0.0,
        slow: 0.0,
        rooted_by_field: false,
        taunt: None,
        knock: Vec2::ZERO,
        contact_cd: 0.5,
        volatile: false,
        bonus_drops: false,
        pinged: 0.0,
        last_hit_by: SourceId::ENVIRONMENT,
        hit_flash: 0.0,
    };
    let brain = Brain {
        cooldown: rng.range_f32(0.8, 2.2),
        phase: rng.range_f32(0.0, std::f32::consts::TAU),
        ..Default::default()
    };
    let mut e = commands.spawn((
        Replicated(ids.alloc()),
        Pos(pos),
        Vel(Vec2::ZERO),
        Facing(Vec2::NEG_Y),
        RoomScoped,
        enemy,
        Statuses::default(),
        Marks::default(),
        brain,
    ));
    if let EnemyBehavior::Boss { script } = &d.behavior
        && let Some(id) = db.bosses.id(script)
    {
        e.insert(BossBrain { script: id, phase: 0, timer: 2.0, next_attack: 0, queue: Vec::new() });
    }
    e.id()
}

/// Is a circle at `p` (radius `r`) inside a telegraph shape at `origin` facing `dir`?
pub fn shape_contains(shape: &TelegraphShape, origin: Vec2, dir: Vec2, p: Vec2, r: f32) -> bool {
    match *shape {
        TelegraphShape::Circle { radius } => p.distance(origin) <= radius + r,
        TelegraphShape::Line { length, width } => {
            let w = width * 0.5 + r;
            dist_sq_point_segment(p, origin, origin + dir * length) <= w * w
        }
        TelegraphShape::Cone { range, angle_deg } => in_cone(p, origin, dir, angle_deg.to_radians() * 0.5, range + r),
        TelegraphShape::Ring { inner, outer } => {
            let d = p.distance(origin);
            d + r >= inner && d - r <= outer
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn telegraph(
    commands: &mut Commands,
    ids: &mut NetIds,
    tick: u32,
    at: Vec2,
    dir: Vec2,
    shape: TelegraphShape,
    windup: f32,
    damage: f32,
    element: gf_core::damage::DamageType,
    effect: TeleEffect,
    owner: Option<Entity>,
) {
    commands.spawn((
        Replicated(ids.alloc()),
        Pos(at),
        RoomScoped,
        Telegraph {
            team: Team::Enemies,
            shape,
            dir: dir.normalize_or(Vec2::X),
            total: windup,
            remaining: windup,
            damage,
            element,
            start_tick: tick,
            effect,
            owner,
        },
    ));
}

struct Target {
    entity: Entity,
    pos: Vec2,
    taunting: bool,
}

fn pick_target(targets: &[Target], pos: Vec2, taunt: Option<Vec2>) -> Option<Vec2> {
    if let Some(t) = taunt {
        return Some(t);
    }
    // Siege Stance: taunting players pull aggro from 16 units.
    if let Some(t) = targets
        .iter()
        .filter(|t| t.taunting && t.pos.distance(pos) < 16.0)
        .min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos)))
    {
        return Some(t.pos);
    }
    targets.iter().min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos))).map(|t| t.pos)
}

fn keep_distance_dir(pos: Vec2, target: Vec2, keep: f32, phase: f32, t: f32) -> Vec2 {
    let to = target - pos;
    let d = to.length();
    let n = to.normalize_or_zero();
    if d > keep * 1.15 {
        n
    } else if d < keep * 0.75 {
        -n
    } else {
        n.perp() * (t * 0.7 + phase).sin().signum() * 0.6
    }
}

#[allow(clippy::type_complexity)]
pub fn enemy_ai(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    mut ids: ResMut<NetIds>,
    mut hits: ResMut<PlayerHits>,
    players: Query<(Entity, &Pos, &Life, &Kit, &Stats), With<Player>>,
    others: Query<&Pos, Without<Enemy>>,
    mut enemies: Query<(Entity, &Pos, &mut Enemy, &mut Brain, &Statuses, &mut Facing), Without<BossBrain>>,
) {
    let dt = clock.gdt();
    let frozen = clock.freeze > 0.0;
    let tele = tuning.enemy.telegraph_time;
    let targets: Vec<Target> = players
        .iter()
        .filter(|(_, _, life, ..)| life.state.is_alive())
        .map(|(e, pos, _, kit, _)| Target { entity: e, pos: pos.0, taunting: kit.taunting() })
        .collect();
    let mut shields: Vec<(Vec2, f32, f32)> = Vec::new();
    for (entity, pos, mut enemy, mut brain, statuses, mut facing) in &mut enemies {
        if frozen || enemy.hp <= 0.0 {
            brain.dir = Vec2::ZERO;
            continue;
        }
        let taunt_pos = enemy.taunt.and_then(|(e, _)| others.get(e).ok().map(|p| p.0));
        let Some(target) = pick_target(&targets, pos.0, taunt_pos) else {
            brain.dir = Vec2::ZERO;
            continue;
        };
        let to = target - pos.0;
        let dist = to.length();
        let dir_to = to.normalize_or(Vec2::X);
        if enemy.stun > 0.0 {
            brain.dir = Vec2::ZERO;
            if brain.state == BrainState::Windup || brain.state == BrainState::Charging {
                brain.state = BrainState::Recover;
                brain.timer = 0.3;
            }
            continue;
        }
        brain.cooldown -= dt;
        let def = content.enemy(enemy.def);
        let t = clock.time;
        match &def.behavior {
            EnemyBehavior::Chaser => {
                brain.dir = dir_to;
            }
            EnemyBehavior::Swarmer { jitter } => {
                let wobble = (t * 3.0 + brain.phase).sin() * jitter;
                brain.dir = (dir_to + dir_to.perp() * wobble).normalize_or(dir_to);
            }
            EnemyBehavior::Charger { range, windup, speed, duration, cooldown, damage, width } => match brain.state {
                BrainState::Approach => {
                    brain.dir = dir_to;
                    if dist < *range && brain.cooldown <= 0.0 {
                        brain.state = BrainState::Windup;
                        brain.timer = windup * tele;
                        brain.dir = Vec2::ZERO;
                        facing.0 = dir_to;
                        brain.hit_players = 0;
                        telegraph(
                            &mut commands,
                            &mut ids,
                            clock.tick,
                            pos.0,
                            dir_to,
                            TelegraphShape::Line { length: speed * duration, width: *width },
                            windup * tele,
                            0.0,
                            gf_core::damage::DamageType::Kinetic,
                            TeleEffect::Damage,
                            Some(entity),
                        );
                    }
                }
                BrainState::Windup => {
                    brain.dir = Vec2::ZERO;
                    brain.timer -= dt;
                    if brain.timer <= 0.0 {
                        brain.state = BrainState::Charging;
                        brain.timer = *duration;
                    }
                }
                BrainState::Charging => {
                    brain.dir = facing.0 * (speed / enemy.speed.max(0.1));
                    brain.timer -= dt;
                    for (i, tg) in targets.iter().enumerate() {
                        let bit = 1u8 << (i.min(7));
                        if brain.hit_players & bit == 0 && tg.pos.distance(pos.0) < enemy.radius + width * 0.5 + 0.4 {
                            brain.hit_players |= bit;
                            hits.0.push(PlayerHit {
                                target: tg.entity,
                                amount: *damage,
                                element: gf_core::damage::DamageType::Kinetic,
                                from: pos.0,
                            });
                        }
                    }
                    if brain.timer <= 0.0 {
                        brain.state = BrainState::Recover;
                        brain.timer = 0.6;
                    }
                }
                _ => {
                    brain.dir = Vec2::ZERO;
                    brain.timer -= dt;
                    if brain.timer <= 0.0 {
                        brain.state = BrainState::Approach;
                        brain.cooldown = *cooldown;
                    }
                }
            },
            EnemyBehavior::Lobber { range, windup, radius, damage, cooldown, keep_distance } => {
                brain.dir = keep_distance_dir(pos.0, target, *keep_distance, brain.phase, t);
                if dist < *range && brain.cooldown <= 0.0 {
                    brain.cooldown = *cooldown;
                    telegraph(
                        &mut commands,
                        &mut ids,
                        clock.tick,
                        target,
                        dir_to,
                        TelegraphShape::Circle { radius: *radius },
                        windup * tele,
                        *damage,
                        gf_core::damage::DamageType::Flame,
                        TeleEffect::Damage,
                        Some(entity),
                    );
                }
            }
            EnemyBehavior::Caster { range, windup, width, length, damage, cooldown, keep_distance } => {
                match brain.state {
                    BrainState::Windup => {
                        brain.dir = Vec2::ZERO;
                        brain.timer -= dt;
                        if brain.timer <= 0.0 {
                            brain.state = BrainState::Approach;
                        }
                    }
                    _ => {
                        brain.dir = keep_distance_dir(pos.0, target, *keep_distance, brain.phase, t);
                        if dist < *range && brain.cooldown <= 0.0 {
                            brain.cooldown = *cooldown;
                            brain.state = BrainState::Windup;
                            brain.timer = windup * tele;
                            facing.0 = dir_to;
                            telegraph(
                                &mut commands,
                                &mut ids,
                                clock.tick,
                                pos.0,
                                dir_to,
                                TelegraphShape::Line { length: *length, width: *width },
                                windup * tele,
                                *damage,
                                gf_core::damage::DamageType::Flame,
                                TeleEffect::Damage,
                                Some(entity),
                            );
                        }
                    }
                }
            }
            EnemyBehavior::Bomber { trigger_range, fuse, radius, damage } => match brain.state {
                BrainState::Primed => {
                    brain.dir = Vec2::ZERO;
                    brain.timer -= dt;
                    if brain.timer <= 0.0 {
                        enemy.hp = 0.0;
                        commands.entity(entity).despawn();
                    }
                }
                _ => {
                    brain.dir = dir_to * 1.1;
                    if dist < *trigger_range {
                        brain.state = BrainState::Primed;
                        brain.timer = fuse * tele;
                        telegraph(
                            &mut commands,
                            &mut ids,
                            clock.tick,
                            pos.0,
                            dir_to,
                            TelegraphShape::Circle { radius: *radius },
                            fuse * tele,
                            *damage,
                            gf_core::damage::DamageType::Flame,
                            TeleEffect::Damage,
                            None,
                        );
                    }
                }
            },
            EnemyBehavior::Support { range, shield, interval, keep_distance } => {
                brain.dir = keep_distance_dir(pos.0, target, *keep_distance, brain.phase, t);
                if brain.cooldown <= 0.0 {
                    brain.cooldown = *interval;
                    shields.push((pos.0, *range, *shield * tuning.enemy.hp));
                }
            }
            EnemyBehavior::Boss { .. } => {}
        }
        if statuses.0.rooted() || enemy.rooted_by_field {
            brain.dir = Vec2::ZERO;
        }
        if brain.dir.length_squared() > 0.01 && brain.state != BrainState::Charging {
            facing.0 = brain.dir.normalize();
        }
        enemy.pinged = enemy.pinged.max(0.0);
    }
    for (center, range, amount) in shields {
        for (_, pos, mut enemy, ..) in &mut enemies {
            if pos.0.distance(center) <= range && enemy.hp > 0.0 {
                enemy.shield = (enemy.shield + amount).min(enemy.max_hp * 0.5);
            }
        }
    }
}

#[allow(clippy::type_complexity)]
pub fn boss_ai(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    encounter: Res<Encounter>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    players: Query<(&Pos, &Life), With<Player>>,
    mut bosses: Query<(Entity, &Pos, &Enemy, &mut Brain, &mut BossBrain, &Replicated)>,
) {
    let dt = clock.gdt();
    if clock.freeze > 0.0 {
        return;
    }
    let tele = tuning.enemy.telegraph_time;
    let alive: Vec<Vec2> = players.iter().filter(|(_, l)| l.state.is_alive()).map(|(p, _)| p.0).collect();
    for (entity, pos, enemy, mut brain, mut boss, rep) in &mut bosses {
        if enemy.hp <= 0.0 {
            continue;
        }
        let script = content.bosses.get(boss.script);
        let frac = enemy.hp / enemy.max_hp.max(1.0);
        let phase_idx = script.phases.iter().rposition(|p| frac <= p.below).unwrap_or(0);
        if phase_idx != boss.phase {
            boss.phase = phase_idx;
            boss.timer = 1.2;
            boss.next_attack = 0;
            events.0.push(GameEvent::BossPhase { boss: rep.0, phase: phase_idx as u8 });
        }
        let phase = &script.phases[boss.phase];
        let Some(target) =
            alive.iter().min_by(|a, b| a.distance_squared(pos.0).total_cmp(&b.distance_squared(pos.0))).copied()
        else {
            brain.dir = Vec2::ZERO;
            continue;
        };
        let dir_to = (target - pos.0).normalize_or(Vec2::NEG_Y);
        brain.dir = if enemy.stun > 0.0 {
            Vec2::ZERO
        } else {
            keep_distance_dir(pos.0, target, script.keep_distance.max(2.0), brain.phase, clock.time) * phase.speed_mult
        };

        // Delayed slam-trail telegraphs.
        let mut ready = Vec::new();
        for q in boss.queue.iter_mut() {
            q.0 -= dt;
            if q.0 <= 0.0 {
                ready.push((q.1, q.2));
            }
        }
        boss.queue.retain(|q| q.0 > 0.0);
        let windup_trail = phase
            .attacks
            .iter()
            .find_map(|a| match a {
                BossAttack::SlamTrail { windup, damage, .. } => Some((*windup, *damage)),
                _ => None,
            })
            .unwrap_or((0.9, 40.0));
        for (at, radius) in ready {
            telegraph(
                &mut commands,
                &mut ids,
                clock.tick,
                at,
                dir_to,
                TelegraphShape::Circle { radius },
                windup_trail.0 * tele,
                windup_trail.1,
                gf_core::damage::DamageType::Kinetic,
                TeleEffect::Damage,
                Some(entity),
            );
        }

        boss.timer -= dt;
        if boss.timer > 0.0 || enemy.stun > 0.0 || phase.attacks.is_empty() {
            continue;
        }
        boss.timer = phase.cadence;
        let attack = &phase.attacks[boss.next_attack % phase.attacks.len()];
        boss.next_attack += 1;
        match attack {
            BossAttack::Strike { shape, at_self, windup, damage, element } => {
                let at = if *at_self { pos.0 } else { target };
                let origin =
                    if matches!(shape, TelegraphShape::Line { .. } | TelegraphShape::Cone { .. }) { pos.0 } else { at };
                telegraph(
                    &mut commands,
                    &mut ids,
                    clock.tick,
                    origin,
                    dir_to,
                    *shape,
                    windup * tele,
                    *damage,
                    *element,
                    TeleEffect::Damage,
                    Some(entity),
                );
            }
            BossAttack::SlamTrail { count, spacing, radius, stagger, .. } => {
                for i in 0..*count {
                    let at = pos.0 + dir_to * spacing * (i as f32 + 1.0);
                    boss.queue.push((i as f32 * stagger, at, *radius));
                }
            }
            BossAttack::Radial { projectiles, speed, damage, radius } => {
                let offset = rngs.ai.range_f32(0.0, std::f32::consts::TAU);
                for i in 0..*projectiles {
                    let dir = from_angle(offset + i as f32 * std::f32::consts::TAU / *projectiles as f32);
                    let origin = pos.0 + dir * (enemy.radius + 0.3);
                    commands.spawn((
                        Replicated(ids.alloc()),
                        Pos(origin),
                        RoomScoped,
                        EnemyShot {
                            dir,
                            speed: *speed,
                            damage: *damage,
                            radius: *radius,
                            life: 6.0,
                            origin,
                            t0: clock.tick,
                        },
                    ));
                }
            }
            BossAttack::Summon { enemy: key, count } => {
                if let Some(id) = content.enemies.id(key) {
                    let n = ((*count as f32) * tuning.enemy.count).round().max(1.0) as u32;
                    for i in 0..n {
                        let at = pos.0 + from_angle(i as f32 * 1.7 + rngs.ai.f32()) * (enemy.radius + 1.5);
                        spawn_enemy(
                            &mut commands,
                            &mut ids,
                            &content,
                            &tuning,
                            encounter.hp_mult.max(1.0),
                            gf_core::ids::EnemyId(id),
                            at,
                            &mut rngs.ai,
                        );
                    }
                }
            }
            BossAttack::Pools { count, radius, duration, dps, windup } => {
                for i in 0..*count {
                    let around = alive[i as usize % alive.len()];
                    let at = around + rngs.ai.unit_vec2() * rngs.ai.range_f32(0.0, 3.0);
                    telegraph(
                        &mut commands,
                        &mut ids,
                        clock.tick,
                        at,
                        dir_to,
                        TelegraphShape::Circle { radius: *radius },
                        windup * tele,
                        dps * 0.5,
                        gf_core::damage::DamageType::Plague,
                        TeleEffect::Pool { radius: *radius, duration: *duration, dps: *dps },
                        Some(entity),
                    );
                }
            }
        }
    }
}

#[allow(clippy::type_complexity)]
pub fn enemy_motion(
    clock: Res<SimClock>,
    tuning: Res<Tuning>,
    arena: Res<ArenaRes>,
    grid: Res<Grid>,
    barricades: Query<(&Pos, &Barricade), Without<Enemy>>,
    mut enemies: Query<(Entity, &mut Pos, &mut Vel, &mut Enemy, &Brain, &Statuses)>,
) {
    let dt = clock.gdt();
    let frozen = clock.freeze > 0.0;
    let speed_mult = tuning.enemy.speed;
    let walls: Vec<(Vec2, Vec2, f32)> =
        barricades.iter().map(|(p, b)| (p.0 - b.along * b.half_len, p.0 + b.along * b.half_len, 0.35)).collect();
    for (entity, mut pos, mut vel, mut enemy, brain, statuses) in &mut enemies {
        if frozen {
            vel.0 = Vec2::ZERO;
            continue;
        }
        let rooted = statuses.0.rooted() || enemy.rooted_by_field;
        let mut v = if rooted || enemy.stun > 0.0 {
            Vec2::ZERO
        } else {
            brain.dir * enemy.speed * speed_mult * (1.0 - enemy.slow)
        };
        // Separation: push out of overlapping neighbours (keeps hordes readable instead of stacked).
        let mut push = Vec2::ZERO;
        let r = enemy.radius;
        grid.0.for_each_in_circle(pos.0, r, |o| {
            if o.entity != entity {
                let d = pos.0 - o.pos;
                let overlap = r + o.radius - d.length();
                if overlap > 0.0 {
                    let n =
                        if d.length_squared() > 1e-6 { d.normalize() } else { from_angle(entity.index_u32() as f32) };
                    push += n * overlap;
                }
            }
        });
        v += push.clamp_length_max(2.0) * 6.0 / enemy.mass.max(0.5).sqrt();
        // Slide along obstacles instead of pushing into them (chasers flow around pillars).
        let want = pos.0 + v * dt;
        let resolved = arena.0.resolve(want, enemy.radius);
        let pushed = resolved - want;
        if pushed.length_squared() > 1e-6 && v.length_squared() > 1e-4 {
            let n = pushed.normalize();
            let tangent = n.perp();
            let t = if tangent.dot(v) >= 0.0 { tangent } else { -tangent };
            v = t * v.length();
        }
        v += enemy.knock;
        enemy.knock *= (-8.0 * dt).exp();
        let mut next = arena.0.resolve(pos.0 + v * dt, enemy.radius);
        for (a, b, half) in &walls {
            let min = half + enemy.radius;
            let d2 = dist_sq_point_segment(next, *a, *b);
            if d2 < min * min {
                let ab = *b - *a;
                let t = ((next - *a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
                let closest = *a + ab * t;
                let n = (next - closest).normalize_or(rotate(ab.normalize_or(Vec2::X), std::f32::consts::FRAC_PI_2));
                next = closest + n * min;
            }
        }
        vel.0 = (next - pos.0) / dt.max(1e-6);
        pos.0 = next;
    }
}

pub fn rebuild_grid(arena: Res<ArenaRes>, mut grid: ResMut<Grid>, enemies: Query<(Entity, &Pos, &Enemy)>) {
    grid.0.reset(arena.0.half_extents, 2.0);
    for (e, pos, enemy) in &enemies {
        if enemy.hp > 0.0 {
            grid.0.insert(e, pos.0, enemy.radius);
        }
    }
}

#[allow(clippy::type_complexity)]
pub fn update_telegraphs(
    mut commands: Commands,
    clock: Res<SimClock>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    mut hits: ResMut<PlayerHits>,
    mut queue: ResMut<DamageQueue>,
    mut events: ResMut<Events>,
    players: Query<(Entity, &Pos, &Life, &Stats), With<Player>>,
    mut telegraphs: Query<(Entity, &Pos, &mut Telegraph, &Replicated)>,
) {
    let dt = clock.gdt();
    for (entity, pos, mut t, rep) in &mut telegraphs {
        if clock.freeze > 0.0 && t.team == Team::Enemies {
            continue;
        }
        t.remaining -= dt;
        if t.remaining > 0.0 {
            continue;
        }
        match t.team {
            Team::Enemies => {
                if t.damage > 0.0 {
                    for (pe, ppos, life, stats) in &players {
                        if life.state.is_alive() && shape_contains(&t.shape, pos.0, t.dir, ppos.0, stats.0.radius) {
                            hits.0.push(PlayerHit { target: pe, amount: t.damage, element: t.element, from: pos.0 });
                        }
                    }
                }
                if let TeleEffect::Pool { radius, duration, dps } = t.effect {
                    commands.spawn((
                        Replicated(ids.alloc()),
                        Pos(pos.0),
                        RoomScoped,
                        Hazard {
                            team: Team::Enemies,
                            kind: HazardKind::Pool,
                            radius,
                            remaining: duration,
                            dps,
                            element: t.element,
                            status: None,
                            slow: 0.0,
                            root: false,
                            pull: 0.0,
                            owner: SourceId::ENEMY,
                            tick_timer: 0.25,
                            ally_mods: Vec::new(),
                            taunt: false,
                            bonus_drops: false,
                            vel: Vec2::ZERO,
                            origin: pos.0,
                            t0: clock.tick,
                        },
                    ));
                }
            }
            Team::Players => {
                if let TeleEffect::PlayerNova { stun, knockback, status, source } = t.effect.clone() {
                    let radius = match t.shape {
                        TelegraphShape::Circle { radius } => radius,
                        _ => 2.0,
                    };
                    for g in grid.0.in_circle(pos.0, radius) {
                        let mut h = Hit::simple(g.entity, source, t.damage, t.element, HitKind::Ability, g.pos);
                        h.stun = stun;
                        h.knockback = (g.pos - pos.0).normalize_or_zero() * knockback;
                        h.status = status;
                        queue.0.push(h);
                    }
                }
            }
        }
        if t.damage > 0.0 {
            let radius = match t.shape {
                TelegraphShape::Circle { radius } => radius,
                TelegraphShape::Ring { outer, .. } => outer,
                TelegraphShape::Line { width, .. } => width,
                TelegraphShape::Cone { range, .. } => range * 0.5,
            };
            events.0.push(GameEvent::Explosion {
                pos: QPos::from_vec2(pos.0),
                radius_q: (radius * 32.0) as u16,
                element: t.element,
            });
        }
        events.0.push(GameEvent::TelegraphResolved { id: rep.0 });
        commands.entity(entity).despawn();
    }
}

pub fn contact_damage(
    clock: Res<SimClock>,
    mut hits: ResMut<PlayerHits>,
    players: Query<(Entity, &Pos, &Life, &Stats), With<Player>>,
    mut enemies: Query<(&Pos, &mut Enemy)>,
) {
    if clock.freeze > 0.0 {
        return;
    }
    for (pos, mut enemy) in &mut enemies {
        if enemy.contact <= 0.0 || enemy.contact_cd > 0.0 || enemy.stun > 0.0 || enemy.hp <= 0.0 {
            continue;
        }
        for (pe, ppos, life, stats) in &players {
            if life.state.is_alive() && ppos.0.distance(pos.0) < enemy.radius + stats.0.radius {
                hits.0.push(PlayerHit {
                    target: pe,
                    amount: enemy.contact * enemy.damage_mult,
                    element: gf_core::damage::DamageType::Kinetic,
                    from: pos.0,
                });
                enemy.contact_cd = 0.8;
                break;
            }
        }
    }
}
