//! ECS → wire views. Runs after each tick on the host.

use crate::components::*;
use crate::resources::*;
use gf_content::schema::{EnemyClass, TelegraphShape};
use gf_engine::prelude::*;
use gf_net::quant::{QPos, QVel, angle_to_u8, angle_to_u16, frac_to_u8};
use gf_net::*;

fn q32(v: f32) -> u16 {
    (v * 32.0).round().clamp(0.0, u16::MAX as f32) as u16
}

fn tele_shape(s: &TelegraphShape) -> TeleShape {
    match *s {
        TelegraphShape::Circle { radius } => TeleShape::Circle { r: q32(radius) },
        TelegraphShape::Line { length, width } => TeleShape::Line { len: q32(length), width: q32(width) },
        TelegraphShape::Cone { range, angle_deg } => {
            TeleShape::Cone { range: q32(range), angle_deg: angle_deg.clamp(0.0, 255.0) as u8 }
        }
        TelegraphShape::Ring { inner, outer } => TeleShape::Ring { inner: q32(inner), outer: q32(outer) },
    }
}

fn base(id: gf_core::ids::NetId, kind: EntityKind, pos: Vec2) -> EntityView {
    EntityView {
        id,
        kind,
        pos: QPos::from_vec2(pos),
        motion: None,
        facing: 0,
        hp: 255,
        flags: EntityFlags::empty(),
        status: 0,
    }
}

/// Every replicated non-player entity.
pub fn entity_views(world: &mut World) -> Vec<EntityView> {
    let frozen = world.resource::<SimClock>().freeze > 0.0;
    let dt = world.resource::<SimClock>().dt;
    let mut out = Vec::with_capacity(512);

    let mut q = world.query::<(&Replicated, &Pos, &Enemy, &Brain, &Statuses, &Facing, Option<&BossBrain>)>();
    for (rep, pos, e, brain, statuses, facing, boss) in q.iter(world) {
        let mut v = base(rep.0, EntityKind::Enemy { def: e.def.0 }, pos.0);
        v.facing = angle_to_u8(facing.0);
        v.hp = frac_to_u8(e.hp / e.max_hp.max(1.0));
        let mut f = EntityFlags::empty();
        f.set(EntityFlags::ELITE, e.elite);
        f.set(EntityFlags::BOSS, boss.is_some() || matches!(e.class, EnemyClass::MiniBoss | EnemyClass::Boss));
        f.set(EntityFlags::SHIELDED, e.shield > 0.0);
        f.set(EntityFlags::STUNNED, e.stun > 0.0);
        f.set(EntityFlags::PLATED, e.plating.is_some());
        f.set(EntityFlags::WINDUP, brain.state == BrainState::Windup);
        f.set(EntityFlags::CHARGING, brain.state == BrainState::Charging);
        f.set(EntityFlags::PRIMED, brain.state == BrainState::Primed);
        f.set(EntityFlags::FROZEN, frozen);
        f.set(EntityFlags::TAUNTED, e.taunt.is_some());
        f.set(EntityFlags::PINGED, e.pinged > 0.0);
        v.flags = f;
        v.status = statuses.0.bits();
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Projectile)>();
    for (rep, p) in q.iter(world) {
        let mut v = base(
            rep.0,
            EntityKind::Projectile {
                style: p.weapon.style,
                element: p.weapon.element,
                owner: p.owner.0,
                radius_q: (p.radius * 32.0).clamp(1.0, 255.0) as u8,
            },
            p.origin,
        );
        v.motion = Some(Motion { vel: QVel::from_vec2(p.dir * p.speed), t0: p.t0 });
        v.facing = angle_to_u8(p.dir);
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &EnemyShot)>();
    for (rep, s) in q.iter(world) {
        let mut v =
            base(rep.0, EntityKind::EnemyShot { radius_q: (s.radius * 32.0).clamp(1.0, 255.0) as u8 }, s.origin);
        v.motion = Some(Motion { vel: QVel::from_vec2(if frozen { Vec2::ZERO } else { s.dir * s.speed }), t0: s.t0 });
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Pos, &Telegraph)>();
    for (rep, pos, t) in q.iter(world) {
        let mut v = base(
            rep.0,
            EntityKind::Telegraph {
                shape: tele_shape(&t.shape),
                dir: angle_to_u16(t.dir),
                windup_ticks: (t.total / dt).round().clamp(1.0, u16::MAX as f32) as u16,
                start: t.start_tick,
            },
            pos.0,
        );
        v.flags.set(EntityFlags::ALLY, t.team == Team::Players);
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Hazard)>();
    for (rep, h) in q.iter(world) {
        let mut v =
            base(rep.0, EntityKind::Hazard { kind: h.kind, element: h.element, radius_q: q32(h.radius) }, h.origin);
        if h.vel != Vec2::ZERO {
            v.motion = Some(Motion { vel: QVel::from_vec2(h.vel), t0: h.t0 });
        }
        v.flags.set(EntityFlags::ALLY, h.team == Team::Players);
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Pos, &Pickup)>();
    for (rep, pos, p) in q.iter(world) {
        let kind = match p.loot {
            Loot::Part(part) => PickupKind::Part { rarity: part.rarity },
            Loot::Shards(n) => PickupKind::Shards(n.min(u16::MAX as u32) as u16),
            Loot::Health(_) => PickupKind::Health,
        };
        out.push(base(rep.0, EntityKind::Pickup { kind, owner: p.owner }, pos.0));
    }

    let mut q = world.query::<(&Replicated, &Pos, &AnvilStation)>();
    for (rep, pos, a) in q.iter(world) {
        let mut v = base(rep.0, EntityKind::Anvil, pos.0);
        v.hp = frac_to_u8(a.progress);
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Pos, &Door)>();
    for (rep, pos, d) in q.iter(world) {
        out.push(base(rep.0, EntityKind::Door { reward: d.reward, index: d.index }, pos.0));
    }

    let mut q = world.query::<(&Replicated, &Pos, &Barricade)>();
    for (rep, pos, b) in q.iter(world) {
        let mut v =
            base(rep.0, EntityKind::Barricade { half_len_q: q32(b.half_len), dir: angle_to_u16(b.along) }, pos.0);
        v.hp = frac_to_u8(b.hp / 260.0);
        out.push(v);
    }

    let mut q = world.query::<(&Replicated, &Pos, &Turret)>();
    for (rep, pos, t) in q.iter(world) {
        out.push(base(rep.0, EntityKind::Turret { owner: t.owner_slot }, pos.0));
    }

    let mut q = world.query::<(&Replicated, &Pos, &Blade)>();
    for (rep, pos, b) in q.iter(world) {
        out.push(base(rep.0, EntityKind::Blade { owner: b.owner_slot }, pos.0));
    }
    out
}

pub fn player_views(world: &mut World) -> Vec<PlayerView> {
    let mut q = world.query::<(
        &Player,
        &Replicated,
        &Mover,
        &Vitals,
        &Stats,
        &Life,
        &Aim,
        &Kit,
        &Gun,
        &Arsenal,
        &RunStats,
        &PlayerInput,
    )>();
    let od_active = world.resource::<Overdrive>().0.is_active();
    let mut out: Vec<PlayerView> = q
        .iter(world)
        .map(|(p, rep, mover, vitals, stats, life, aim, kit, gun, arsenal, run_stats, input)| {
            let mut flags = PlayerFlags::empty();
            flags.set(PlayerFlags::STANCE, kit.buffs.iter().any(|b| b.root_self));
            flags.set(PlayerFlags::AVATAR, kit.buffs.iter().any(|b| b.source == 2 && b.scale > 1.0));
            flags.set(PlayerFlags::OVERDRIVE, od_active);
            flags.set(PlayerFlags::AIRBORNE, kit.airborne.is_some());
            flags.set(PlayerFlags::TAUNTING, kit.taunting());
            flags.set(PlayerFlags::INFINITE_DASH, kit.infinite_dash());
            flags.set(PlayerFlags::IN_FIELD, !kit.in_field_mods.is_empty());
            flags.set(PlayerFlags::SHIELDED, vitals.shield + vitals.bonus_shield > 0.0);
            let (armor, armor_max) = match kit.passive {
                PassiveState::Armor { armor, .. } => (armor, 90.0),
                _ => (0.0, 0.0),
            };
            let passive_meter = match kit.passive {
                PassiveState::Armor { armor, .. } => armor / 90.0,
                PassiveState::Static { charge } => charge,
                PassiveState::Ghost { crit } => crit,
                PassiveState::None => 0.0,
            };
            let height = kit.airborne.map_or(0.0, |a| {
                let f = (a.t / a.total).clamp(0.0, 1.0);
                4.0 * f * (1.0 - f) * 2.5
            });
            PlayerView {
                slot: p.slot,
                id: rep.0,
                character: p.character.0,
                mover: mover.0,
                height,
                hp: vitals.hp,
                max_hp: stats.0.max_hp,
                shield: vitals.shield + vitals.bonus_shield,
                armor,
                armor_max,
                life: life.state,
                aim: angle_to_u16(aim.dir),
                target: aim.target,
                aim_mode: aim.mode,
                cooldowns: kit.cooldowns,
                cooldowns_max: kit.cooldowns_max,
                ult: kit.ult,
                flags,
                scale: kit.scale(),
                deadeye: aim.deadeye.stacks,
                passive_meter,
                weapon: arsenal.build.clone(),
                firing: gun.firing,
                charge: gun.charge,
                beam: gun.beam.map(|(len, width)| BeamView { len, width }),
                shards: arsenal.wallet.godshards,
                kills: run_stats.kills,
                damage: run_stats.damage,
                boons: arsenal.boons.iter().map(|(b, _)| b.0).collect(),
                forge_open: input.cmd.forge_open,
            }
        })
        .collect();
    out.sort_by_key(|p| p.slot);
    out
}

pub fn private_views(world: &mut World) -> Vec<(u8, PrivateView)> {
    let radius = world.resource::<Content>().game.anvil.radius;
    let hot: Vec<(Vec2, AnvilState)> =
        world.query::<(&Pos, &AnvilStation)>().iter(world).map(|(p, a)| (p.0, a.state)).collect();
    let mut q = world.query::<(&Player, &Pos, &Arsenal, &BoonChoice, &Life)>();
    q.iter(world)
        .map(|(p, pos, arsenal, choice, life)| {
            (
                p.slot,
                PrivateView {
                    bag: arsenal.bag.clone(),
                    wallet: arsenal.wallet,
                    at_anvil: crate::anvil::at_hot_anvil(&hot, pos.0, radius),
                    boon_offer: choice.offer.iter().map(|(b, r)| BoonOffer { boon: b.0, rarity: *r }).collect(),
                    boon_rerolls: choice.rerolls,
                    rekindles: life.rekindles,
                },
            )
        })
        .collect()
}

pub fn run_view(world: &mut World) -> RunView {
    let anvil = world.query::<(&Replicated, &AnvilStation)>().iter(world).next().map(|(rep, a)| AnvilView {
        id: rep.0,
        state: a.state,
        progress: a.progress,
        time_left: a.forge_left,
        contested: a.contested,
    });
    let boss = world.query::<(&Replicated, &Enemy, &BossBrain)>().iter(world).max_by_key(|(_, e, _)| e.class).map(
        |(rep, e, b)| BossView {
            id: rep.0,
            enemy: e.def.0,
            hp_frac: (e.hp / e.max_hp.max(1.0)).max(0.0),
            phase: b.phase as u8,
        },
    );
    let party = world.query::<&Player>().iter(world).count() as u8;
    let clock = world.resource::<SimClock>();
    let (time, time_scale) = (clock.time, clock.scale);
    let run = world.resource::<RunState>();
    let enc = world.resource::<Encounter>();
    let od = world.resource::<Overdrive>().0;
    let settings = world.resource::<SimSettings>();
    let steps = if run.biomes.is_empty() {
        0
    } else {
        world.resource::<Content>().biome(run.biomes[run.biome_idx]).sequence.len() as u8
    };
    RunView {
        phase: run.phase,
        biome: run.biomes.get(run.biome_idx).map_or(0, |b| b.0),
        room: run.room.0,
        room_serial: run.room_serial,
        depth: run.depth,
        step: run.step as u8,
        steps,
        time,
        time_scale,
        kills: run.kills,
        encounter_left: (enc.budget_left / enc.budget_total.max(1.0)).clamp(0.0, 1.0),
        overdrive_meter: od.meter,
        overdrive_active: od.active,
        anvil,
        boss,
        chaos_tier: settings.chaos_tier,
        ember: run.ember.round() as u32,
        party,
    }
}
