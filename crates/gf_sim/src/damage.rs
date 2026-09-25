//! Damage resolution. Every hit on an enemy — weapon, chain, splash, ability, DoT, synergy — goes
//! through [`resolve_damage`]; every hit on a player through [`resolve_player_hits`].

use crate::abilities::armor_conversion;
use crate::components::*;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::{EnemyClass, PassiveDef, Phase};
use gf_core::damage::{HitParams, Resistances, apply_plating, roll_hit};
use gf_core::forge::Slot;
use gf_core::ids::{PartId, SourceId};
use gf_core::rarity::Rarity;
use gf_core::revive::on_downed;
use gf_core::rng::GfRng;
use gf_core::status::ApplyOutcome;
use gf_core::synergy::SynergyEffect;
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{GameEvent, HazardKind};

/// Roll a random forge part (weighted by content `weight`, never a Sigil).
pub fn roll_part(db: &ContentDb, phase: Phase, rng: &mut GfRng, luck: f32, min: Rarity) -> (PartId, Rarity) {
    let pool: Vec<(PartId, f32)> = db
        .parts
        .enumerate()
        .filter(|(_, p)| p.slot != Slot::Sigil && p.phase <= phase)
        .map(|(i, p)| (PartId(i), p.weight))
        .collect();
    let weights: Vec<f32> = pool.iter().map(|(_, w)| *w).collect();
    let idx = rng.weighted_index(&weights).unwrap_or(0);
    let rarity = db.game.rarity.roll(rng, luck).max(min);
    (pool.get(idx).map_or(PartId(0), |p| p.0), rarity)
}

pub fn tick_statuses(
    clock: Res<SimClock>,
    content: Res<Content>,
    mut queue: ResMut<DamageQueue>,
    mut q: Query<(Entity, &Pos, &Vel, &mut Enemy, &mut Statuses, &mut Marks)>,
) {
    let dt = clock.gdt();
    let st = &content.game.status;
    for (entity, pos, vel, mut enemy, mut statuses, mut marks) in &mut q {
        let tick = statuses.0.tick(dt, vel.0.length_squared() > 0.04, st);
        if tick.burn > 0.0 {
            queue.0.push(Hit::simple(
                entity,
                tick.burn_source,
                tick.burn,
                gf_core::damage::DamageType::Flame,
                HitKind::Dot,
                pos.0,
            ));
        }
        if tick.bleed > 0.0 {
            queue.0.push(Hit::simple(
                entity,
                tick.bleed_source,
                tick.bleed,
                gf_core::damage::DamageType::Kinetic,
                HitKind::Dot,
                pos.0,
            ));
        }
        marks.0.tick(dt);
        enemy.stun = (enemy.stun - dt).max(0.0);
        enemy.pinged = (enemy.pinged - dt).max(0.0);
        enemy.hit_flash = (enemy.hit_flash - dt).max(0.0);
        enemy.contact_cd = (enemy.contact_cd - dt).max(0.0);
        if let Some((e, t)) = enemy.taunt {
            enemy.taunt = (t - dt > 0.0).then_some((e, t - dt));
        }
    }
}

#[derive(Default, Clone, Copy)]
struct Credit {
    damage: f32,
    heal: f32,
    precision: u32,
    synergies: u32,
}

#[allow(clippy::type_complexity)]
pub fn resolve_damage(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    grid: Res<Grid>,
    mut ids: ResMut<NetIds>,
    mut queue: ResMut<DamageQueue>,
    mut kills: ResMut<Kills>,
    mut events: ResMut<Events>,
    mut rngs: ResMut<Rngs>,
    mut od: ResMut<Overdrive>,
    mut enemies: Query<(&mut Enemy, &mut Statuses, &mut Marks, &Pos, &Replicated), Without<Player>>,
    mut players: Query<(&Player, &Pos, &mut Vitals, &Stats, &mut Kit, &mut RunStats, &mut Aim, &Life), Without<Enemy>>,
) {
    let st = &content.game.status;
    let syn = content.game.synergy;
    let od_t = content.game.overdrive;
    let party = tuning.party;
    let mut hp_frac = [1.0f32; 4];
    for (p, _, v, s, ..) in &players {
        hp_frac[p.slot as usize % 4] = v.hp / s.0.max_hp.max(1.0);
    }
    let mut credit = [Credit::default(); 4];
    let mut ally_heals: Vec<(Vec2, f32, f32)> = Vec::new();
    let mut i = 0;
    while i < queue.0.len() && i < 60_000 {
        let hit = queue.0[i].clone();
        i += 1;
        let Ok((mut enemy, mut statuses, mut marks, pos, rep)) = enemies.get_mut(hit.target) else { continue };
        if enemy.hp <= 0.0 {
            continue;
        }
        let weapon = hit.weapon.clone();
        let slot = hit.source.owner_slot();
        let full_hp = enemy.hp >= enemy.max_hp - 0.01;
        let mut bonus = hit.bonus * statuses.0.damage_taken_mult(st);
        if let Some(w) = &weapon {
            bonus *= w.conditional_mult(
                full_hp,
                enemy.elite || enemy.is_boss_like(),
                statuses.0.bits(),
                slot.map_or(1.0, |s| hp_frac[s as usize % 4]),
            );
        }
        let crits = !matches!(hit.kind, HitKind::Dot | HitKind::Hazard);
        let params = HitParams {
            base: hit.base,
            damage_type: hit.element,
            crit_chance: if crits { hit.crit_chance + statuses.0.crit_chance_bonus(st) } else { 0.0 },
            crit_mult: hit.crit_mult,
            bonus_mult: bonus,
            precision: hit.precision,
            precision_crit_bonus: hit.precision_crit_bonus,
            forced_crit: false,
        };
        let roll = rngs.combat.f32();
        let plated = enemy.plating.is_some();
        let res = roll_hit(&params, if plated { &Resistances::NONE } else { &enemy.resist }, roll);
        let mut amount = res.amount;
        if plated {
            let (after, shattered) = apply_plating(amount, hit.element, &mut enemy.plating);
            amount = after;
            if shattered {
                events.0.push(GameEvent::PlatesShattered { target: rep.0 });
            }
        }
        let shown = amount;
        if enemy.shield > 0.0 {
            let absorbed = amount.min(enemy.shield);
            enemy.shield -= absorbed;
            amount -= absorbed;
        }
        if let Some(w) = &weapon
            && w.execute > 0.0
            && !enemy.is_boss_like()
            && (enemy.hp - amount) / enemy.max_hp < w.execute
        {
            amount = enemy.hp;
        }
        let dealt = amount.min(enemy.hp).max(0.0);
        enemy.hp -= amount;
        enemy.hit_flash = 0.06;
        enemy.last_hit_by = hit.source;
        let mass = enemy.mass.max(0.3);
        enemy.knock += hit.knockback / mass;
        if hit.stun > 0.0 {
            let f = match enemy.control_class() {
                gf_core::status::ControlClass::Normal => 1.0,
                gf_core::status::ControlClass::Elite => st.control_resist_elite,
                gf_core::status::ControlClass::Boss => st.control_resist_boss,
            };
            enemy.stun = enemy.stun.max(hit.stun * f);
        }
        if !matches!(hit.kind, HitKind::Dot | HitKind::Hazard) {
            events.0.push(GameEvent::Hit {
                target: rep.0,
                amount: shown.round().clamp(0.0, 65535.0) as u16,
                crit: res.crit,
                precision: hit.precision,
                element: hit.element,
                source: hit.source.0,
            });
        }
        if let Some(s) = slot {
            let c = &mut credit[s as usize % 4];
            c.damage += dealt;
            if let Some(w) = &weapon
                && matches!(hit.kind, HitKind::Weapon | HitKind::Secondary)
            {
                c.heal += dealt * w.lifesteal;
            }
            if hit.precision && hit.kind == HitKind::Weapon {
                c.precision += 1;
            }
            od.0.add_damage(dealt, party, &od_t);
        }

        // ── statuses ──
        let mut outcomes: Vec<ApplyOutcome> = Vec::new();
        if let Some(w) = &weapon
            && matches!(hit.kind, HitKind::Weapon | HitKind::Secondary)
        {
            for s in &w.on_hit {
                if rngs.combat.chance(s.chance) {
                    outcomes.push(statuses.0.apply(
                        s.status,
                        s.stacks,
                        s.duration,
                        hit.base.max(dealt),
                        hit.source,
                        enemy.control_class(),
                        st,
                    ));
                }
            }
        }
        if let Some((kind, stacks, duration)) = hit.status {
            outcomes.push(statuses.0.apply(
                kind,
                stacks,
                duration,
                hit.base.max(10.0),
                hit.source,
                enemy.control_class(),
                st,
            ));
        }
        for o in outcomes {
            if let ApplyOutcome::ShockDischarge { damage, radius, stun, source } = o {
                for g in grid.0.in_circle(pos.0, radius) {
                    let mut h = Hit::simple(
                        g.entity,
                        source,
                        damage,
                        gf_core::damage::DamageType::Storm,
                        HitKind::Synergy,
                        g.pos,
                    );
                    h.stun = stun;
                    queue.0.push(h);
                    events.0.push(GameEvent::Arc {
                        from: QPos::from_vec2(pos.0),
                        to: QPos::from_vec2(g.pos),
                        element: gf_core::damage::DamageType::Storm,
                    });
                }
            }
        }

        // ── elemental synergy ──
        if matches!(hit.kind, HitKind::Weapon | HitKind::Ability)
            && hit.source.is_player_side()
            && let Some(trig) = marks.0.on_hit(hit.element, hit.source, &content.synergy_rules, &syn, party)
        {
            let rule = &content.synergy_rules[trig.synergy.index()];
            let base = hit.base.max(dealt) * trig.power;
            match rule.effect {
                SynergyEffect::Burst { radius, damage_mult, element, status } => {
                    for g in grid.0.in_circle(pos.0, radius) {
                        let mut h = Hit::simple(
                            g.entity,
                            trig.trigger_source,
                            base * damage_mult,
                            element,
                            HitKind::Synergy,
                            g.pos,
                        );
                        h.status = status.map(|s| (s, 1, 3.0));
                        h.knockback = (g.pos - pos.0).normalize_or_zero() * 3.0;
                        queue.0.push(h);
                    }
                    events.0.push(GameEvent::Explosion {
                        pos: QPos::from_vec2(pos.0),
                        radius_q: (radius * 32.0) as u16,
                        element,
                    });
                }
                SynergyEffect::GravityChain { jumps, range, damage_mult, pull } => {
                    let mut from = pos.0;
                    let mut chained = vec![hit.target];
                    for _ in 0..jumps {
                        let Some(n) = grid.0.nearest(from, range, |x| !chained.contains(&x.entity)) else { break };
                        chained.push(n.entity);
                        let mut h = Hit::simple(
                            n.entity,
                            trig.trigger_source,
                            base * damage_mult,
                            hit.element,
                            HitKind::Synergy,
                            n.pos,
                        );
                        h.knockback = (pos.0 - n.pos).normalize_or_zero() * pull;
                        queue.0.push(h);
                        events.0.push(GameEvent::Arc {
                            from: QPos::from_vec2(from),
                            to: QPos::from_vec2(n.pos),
                            element: hit.element,
                        });
                        from = n.pos;
                    }
                }
                SynergyEffect::AllyHeal { radius, amount, damage_mult } => {
                    for g in grid.0.in_circle(pos.0, radius * 0.6) {
                        queue.0.push(Hit::simple(
                            g.entity,
                            trig.trigger_source,
                            base * damage_mult,
                            gf_core::damage::DamageType::Radiant,
                            HitKind::Synergy,
                            g.pos,
                        ));
                    }
                    ally_heals.push((pos.0, radius, amount * trig.power));
                }
                SynergyEffect::Field { radius, duration, dps_mult, element, slow } => {
                    commands.spawn((
                        Replicated(ids.alloc()),
                        Pos(pos.0),
                        RoomScoped,
                        Hazard {
                            team: Team::Players,
                            kind: HazardKind::Field,
                            radius,
                            remaining: duration,
                            dps: base * dps_mult,
                            element,
                            status: None,
                            slow,
                            root: false,
                            pull: 0.0,
                            owner: trig.trigger_source,
                            tick_timer: 0.0,
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
            events.0.push(GameEvent::Synergy {
                synergy: trig.synergy.0,
                pos: QPos::from_vec2(pos.0),
                a: trig.partner.0,
                b: trig.trigger_source.0,
            });
            for s in [trig.trigger_source.owner_slot(), trig.partner.owner_slot()].into_iter().flatten() {
                credit[s as usize % 4].synergies += 1;
            }
        }

        // ── relic triggers ──
        if hit.kind == HitKind::Weapon
            && let Some(w) = &weapon
        {
            if let Some(d) = w.doomstack {
                enemy.doom += 1;
                if enemy.doom >= d.stacks.max(2) {
                    enemy.doom = 0;
                    let mut h =
                        Hit::simple(hit.target, hit.source, w.damage * d.burst, w.element, HitKind::Secondary, pos.0);
                    h.crit_chance = w.crit_chance;
                    h.crit_mult = w.crit_mult;
                    queue.0.push(h);
                    events.0.push(GameEvent::Explosion {
                        pos: QPos::from_vec2(pos.0),
                        radius_q: 40,
                        element: w.element,
                    });
                }
            }
            // Only the wielder's own shots spawn turrets (turret shots never spawn turrets).
            if res.crit
                && hit.source.0 < 4
                && let Some(t) = w.turret_on_crit
                && let Some(s) = slot
                && rngs.combat.chance(t.chance)
            {
                commands.spawn((
                    Replicated(ids.alloc()),
                    Pos(pos.0 + rngs.combat.unit_vec2() * 1.2),
                    RoomScoped,
                    Turret {
                        owner: SourceId::turret(s),
                        owner_slot: s,
                        weapon: w.clone(),
                        power: t.power,
                        remaining: t.duration,
                        cooldown: 0.1,
                    },
                ));
            }
        }

        if enemy.hp <= 0.0 {
            kills.0.push(KillRecord {
                entity: hit.target,
                net: rep.0,
                def: enemy.def,
                class: enemy.class,
                pos: pos.0,
                killer: hit.source,
                weapon: weapon.clone(),
                bonus_drops: enemy.bonus_drops,
                volatile: enemy.volatile,
            });
        }
    }
    queue.0.clear();

    let heal_mult = tuning.enemy.healing_received;
    let manual = content.aim_params(gf_core::aim::AimMode::Manual);
    for (p, ppos, mut vitals, stats, mut kit, mut run_stats, mut aim, life) in &mut players {
        let c = credit[p.slot as usize % 4];
        run_stats.damage += c.damage;
        run_stats.synergies += c.synergies;
        if !life.state.is_alive() {
            continue;
        }
        kit.ult = (kit.ult + c.damage * stats.0.ult_per_damage).min(1.0);
        let mut heal = c.heal;
        for (at, radius, amount) in &ally_heals {
            if ppos.0.distance(*at) <= *radius {
                heal += amount;
            }
        }
        vitals.hp = (vitals.hp + heal * heal_mult).min(stats.0.max_hp);
        for _ in 0..c.precision {
            if aim.mode == gf_core::aim::AimMode::Manual {
                aim.deadeye.on_precision_hit(&manual);
            }
        }
        run_stats.precision_hits += c.precision;
    }
}

#[allow(clippy::type_complexity)]
pub fn resolve_player_hits(
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    grid: Res<Grid>,
    mut hits: ResMut<PlayerHits>,
    mut queue: ResMut<DamageQueue>,
    mut events: ResMut<Events>,
    mut enemies: Query<(&Pos, &mut Enemy), Without<Player>>,
    mut players: Query<
        (Entity, &Player, &Pos, &mut Vitals, &Stats, &mut Kit, &mut Life, &Mover, &mut DamageHistory),
        Without<Enemy>,
    >,
) {
    let dt = clock.gdt();
    let revive = content.game.revive;
    let mut taunts: Vec<(Vec2, f32, f32, Entity)> = Vec::new();
    for hit in hits.0.drain(..) {
        let Ok((entity, player, pos, mut vitals, stats, mut kit, mut life, mover, mut history)) =
            players.get_mut(hit.target)
        else {
            continue;
        };
        if !life.state.is_alive() || mover.0.iframes > 0.0 || kit.airborne.is_some() {
            continue;
        }
        let mut amount = hit.amount * tuning.enemy.damage * stats.0.damage_taken;
        vitals.shield_delay = 4.0;
        let from_bonus = amount.min(vitals.bonus_shield);
        vitals.bonus_shield -= from_bonus;
        amount -= from_bonus;
        let from_shield = amount.min(vitals.shield);
        vitals.shield -= from_shield;
        amount -= from_shield;
        if let Some(def) = content.kit(player.character).map(|k| &k.passive) {
            let (to_hp, broke) = armor_conversion(&mut kit.passive, def, amount);
            amount = to_hp;
            if broke
                && let PassiveDef::ArmorConversion {
                    break_radius,
                    break_damage,
                    break_knockback,
                    break_taunt,
                    break_cooldown,
                    ..
                } = def
            {
                if let PassiveState::Armor { break_cd, .. } = &mut kit.passive {
                    *break_cd = *break_cooldown;
                }
                for g in grid.0.in_circle(pos.0, *break_radius) {
                    let mut h = Hit::simple(
                        g.entity,
                        SourceId::player(player.slot),
                        *break_damage,
                        gf_core::damage::DamageType::Kinetic,
                        HitKind::Ability,
                        g.pos,
                    );
                    h.knockback = (g.pos - pos.0).normalize_or_zero() * *break_knockback;
                    queue.0.push(h);
                }
                taunts.push((pos.0, *break_radius * 1.6, *break_taunt, entity));
                events.0.push(GameEvent::ArmorBreak { slot: player.slot });
            }
        }
        if amount <= 0.0 {
            continue;
        }
        vitals.hp -= amount;
        history.0.push_back((clock.tick, amount));
        events.0.push(GameEvent::PlayerHurt { slot: player.slot, amount: amount.round() as u16 });
        if vitals.hp <= 0.0 {
            vitals.hp = 0.0;
            let mut rekindles = life.rekindles;
            life.state = on_downed(tuning.party, &mut rekindles, &revive);
            life.rekindles = rekindles;
            kit.pending = None;
            kit.rush = None;
            events.0.push(GameEvent::Downed { slot: player.slot });
        }
    }
    for (center, radius, duration, taunter) in taunts {
        for (pos, mut enemy) in &mut enemies {
            if pos.0.distance(center) <= radius {
                enemy.taunt = Some((taunter, duration));
            }
        }
    }
    // Regeneration and shields.
    let window = (6.0 / clock.dt) as u32;
    for (.., mut vitals, stats, _, life, _, mut history) in &mut players {
        while history.0.front().is_some_and(|(t, _)| clock.tick.saturating_sub(*t) > window) {
            history.0.pop_front();
        }
        if !life.state.is_alive() {
            continue;
        }
        vitals.shield_delay = (vitals.shield_delay - dt).max(0.0);
        if vitals.shield_delay <= 0.0 {
            vitals.shield = (vitals.shield + stats.0.max_shield * 0.25 * dt).min(stats.0.max_shield);
        }
        if stats.0.regen > 0.0 {
            vitals.hp = (vitals.hp + stats.0.regen * dt * tuning.enemy.healing_received).min(stats.0.max_hp);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn drop_loot(
    commands: &mut Commands,
    ids: &mut NetIds,
    rng: &mut GfRng,
    at: Vec2,
    loot: Loot,
    owner: Option<u8>,
    life: f32,
) {
    let offset = rng.unit_vec2() * rng.range_f32(0.3, 1.2);
    commands.spawn((Replicated(ids.alloc()), Pos(at + offset), RoomScoped, Pickup { loot, owner, life }));
}

#[allow(clippy::type_complexity)]
pub fn process_kills(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    settings: Res<SimSettings>,
    tuning: Res<Tuning>,
    grid: Res<Grid>,
    mut kills: ResMut<Kills>,
    mut rngs: ResMut<Rngs>,
    mut run: ResMut<RunState>,
    mut events: ResMut<Events>,
    mut ids: ResMut<NetIds>,
    mut queue: ResMut<DamageQueue>,
    mut players: Query<(&Player, &mut Kit, &mut RunStats, &mut Mover, &Stats, &mut Arsenal)>,
) {
    let drops = &content.game.drops;
    let rt = &content.game.run;
    let slots: Vec<(u8, f32)> = players.iter().map(|(p, _, _, _, s, _)| (p.slot, s.0.luck)).collect();
    for k in std::mem::take(&mut kills.0) {
        commands.entity(k.entity).despawn();
        let class = k.class.index();
        let elite = matches!(k.class, EnemyClass::Elite | EnemyClass::MiniBoss | EnemyClass::Boss);
        run.kills += 1;
        run.ember += rt.ember_per_kill[class] * tuning.enemy.ember_mult;
        events.0.push(GameEvent::Kill { target: k.net, pos: QPos::from_vec2(k.pos), source: k.killer.0, elite });

        if let Some(slot) = k.killer.owner_slot()
            && let Some((player, mut kit, mut stats, mut mover, pstats, mut arsenal)) =
                players.iter_mut().find(|(p, ..)| p.slot == slot)
        {
            stats.kills += 1;
            if let Some(PassiveDef::GhostStep { crit_per_kill, max_crit, dash_refund_chance, .. }) =
                content.kit(player.character).map(|k| &k.passive)
                && let PassiveState::Ghost { crit } = &mut kit.passive
            {
                *crit = (*crit + crit_per_kill).min(*max_crit);
                if rngs.combat.chance(*dash_refund_chance) {
                    mover.0.dash_charges = (mover.0.dash_charges + 1).min(pstats.0.dash_charges);
                }
            }
            if let Some(w) = &k.weapon {
                if let Some(blast) = w.explode_on_kill
                    && rngs.combat.chance(blast.chance)
                {
                    for g in grid.0.in_circle(k.pos, blast.radius) {
                        if g.entity != k.entity {
                            queue.0.push(Hit::simple(
                                g.entity,
                                k.killer,
                                w.damage * blast.damage,
                                w.element,
                                HitKind::Secondary,
                                g.pos,
                            ));
                        }
                    }
                    events.0.push(GameEvent::Explosion {
                        pos: QPos::from_vec2(k.pos),
                        radius_q: (blast.radius * 32.0) as u16,
                        element: w.element,
                    });
                }
                if w.shards_on_kill > 0.0 && rngs.loot.chance(w.shards_on_kill) {
                    arsenal.wallet.godshards += 1;
                }
            }
        }

        // Volatile deaths (Chaos Tier mutator) and innate death bursts are telegraphed.
        let def = content.enemy(k.def);
        let mut burst = def.death_burst;
        if let Some(v) = tuning.enemy.volatile
            && rngs.ai.chance(v.chance)
        {
            burst = Some((v.radius, v.damage));
        }
        if let Some((radius, damage)) = burst {
            let fuse = tuning.enemy.volatile.map_or(0.45, |v| v.fuse).max(0.45);
            commands.spawn((
                Replicated(ids.alloc()),
                Pos(k.pos),
                RoomScoped,
                Telegraph {
                    team: Team::Enemies,
                    shape: gf_content::schema::TelegraphShape::Circle { radius },
                    dir: Vec2::X,
                    total: fuse,
                    remaining: fuse,
                    damage,
                    element: gf_core::damage::DamageType::Flame,
                    start_tick: clock.tick,
                    effect: TeleEffect::Damage,
                    owner: None,
                },
            ));
        }

        // Personal loot: every player rolls their own part drop.
        let loot_mult = tuning.enemy.loot * if k.bonus_drops { 2.0 } else { 1.0 };
        for (slot, luck) in &slots {
            let guaranteed = matches!(k.class, EnemyClass::MiniBoss | EnemyClass::Boss);
            let rolls = if guaranteed { drops.part_count[class] as u32 } else { 1 };
            for _ in 0..rolls {
                if guaranteed || rngs.loot.chance(drops.part_chance[class] * loot_mult * (1.0 + luck * 0.25)) {
                    let min = if guaranteed { Rarity::Rare } else { Rarity::Common };
                    let (part, rarity) = roll_part(&content, settings.phase, &mut rngs.loot, *luck, min);
                    let inst = players
                        .iter_mut()
                        .find(|(p, ..)| p.slot == *slot)
                        .map(|(.., mut a)| a.instance(part, rarity))
                        .unwrap_or(gf_core::forge::PartInstance { uid: 0, part, rarity });
                    drop_loot(
                        &mut commands,
                        &mut ids,
                        &mut rngs.loot,
                        k.pos,
                        Loot::Part(inst),
                        Some(*slot),
                        drops.pickup_lifetime,
                    );
                }
            }
        }
        if rngs.loot.chance(drops.shard_chance[class] * loot_mult) {
            let n = (drops.shard_amount[class] as f32 * tuning.enemy.loot).round().max(1.0) as u32;
            drop_loot(&mut commands, &mut ids, &mut rngs.loot, k.pos, Loot::Shards(n), None, drops.pickup_lifetime);
        }
        if rngs.loot.chance(drops.health_chance[class]) {
            drop_loot(
                &mut commands,
                &mut ids,
                &mut rngs.loot,
                k.pos,
                Loot::Health(drops.health_amount),
                None,
                drops.pickup_lifetime,
            );
        }
    }
}
