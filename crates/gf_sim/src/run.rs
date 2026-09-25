//! Run structure (§4): biomes × rooms, reward doors, room rewards, the boss, victory and defeat.

use crate::boons::make_offer;
use crate::components::*;
use crate::damage::roll_part;
use crate::enemies::spawn_enemy;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::{RoomKind, RunStep};
use gf_core::ids::{BiomeId, EnemyId, RoomId};
use gf_core::movement::Arena;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::{AnvilState, DoorReward, GameEvent, PlayerAction, RunPhase};

/// Room kind a door reward leads to.
pub fn kind_for_reward(reward: DoorReward) -> RoomKind {
    match reward {
        DoorReward::Anvil => RoomKind::Anvil,
        DoorReward::EliteChallenge => RoomKind::Elite,
        DoorReward::ShardCache | DoorReward::Healing => RoomKind::Treasure,
        DoorReward::PartCache | DoorReward::Boon { .. } | DoorReward::Onward => RoomKind::Combat,
    }
}

/// Pick a room of `kind` in `biome` (falls back to Combat), avoiding an immediate repeat.
pub fn pick_room(
    db: &ContentDb,
    biome: BiomeId,
    kind: RoomKind,
    phase: gf_content::Phase,
    avoid: Option<RoomId>,
    rng: &mut GfRng,
) -> RoomId {
    let key = &db.biome(biome).key;
    let pool = |k: RoomKind| -> Vec<u16> {
        db.rooms
            .enumerate()
            .filter(|(_, r)| &r.biome == key && r.kind == k && r.phase <= phase)
            .map(|(i, _)| i)
            .collect()
    };
    let mut rooms = pool(kind);
    if rooms.is_empty() {
        rooms = pool(RoomKind::Combat);
    }
    if rooms.len() > 1
        && let Some(a) = avoid
    {
        rooms.retain(|r| *r != a.0);
    }
    RoomId(*rng.pick(&rooms).unwrap_or(&0))
}

/// Begin a run in the first biome of the build's content phase.
pub fn start_run(world: &mut World) {
    let db = world.resource::<Content>().0.clone();
    let phase = world.resource::<SimSettings>().phase;
    let biomes: Vec<BiomeId> =
        db.biomes.enumerate().filter(|(_, b)| b.phase <= phase).map(|(i, _)| BiomeId(i)).collect();
    let Some(first) = biomes.first().copied() else { return };
    let kind = match db.biome(first).sequence.first() {
        Some(RunStep::Fixed(k)) => *k,
        _ => RoomKind::Combat,
    };
    // The opening room is the biome's first matching template (a stable, authored start).
    let key = db.biome(first).key.clone();
    let room = db
        .rooms
        .enumerate()
        .find(|(_, r)| r.biome == key && r.kind == kind && r.phase <= phase)
        .map(|(i, _)| RoomId(i))
        .unwrap_or(RoomId(0));
    {
        let mut run = world.resource_mut::<RunState>();
        run.biomes = biomes;
        run.biome_idx = 0;
        run.step = 0;
        run.started = true;
        run.reward = Some(DoorReward::PartCache);
    }
    load_room(world, room);
}

/// Tear down the current room and build `room`.
pub fn load_room(world: &mut World, room_id: RoomId) {
    let db = world.resource::<Content>().0.clone();
    let room = db.room(room_id).clone();
    // Despawn everything room-scoped.
    let scoped: Vec<Entity> = world.query_filtered::<Entity, With<RoomScoped>>().iter(world).collect();
    for e in scoped {
        world.despawn(e);
    }
    let arena = Arena { half_extents: room.half_extents, obstacles: room.obstacles.clone() };
    world.resource_mut::<Grid>().0.reset(room.half_extents, 2.0);
    world.insert_resource(ArenaRes(arena.clone()));

    let (rooms_in_biome, biome_idx) = {
        let run = world.resource::<RunState>();
        (run.rooms_in_biome, run.biome_idx)
    };
    let rt = &db.game.run;
    let count = world.resource::<Tuning>().enemy.count;
    let e = &room.encounter;
    let growth = (1.0 + rt.budget_growth_per_room * rooms_in_biome as f32) * rt.budget_mult;
    let hp_mult =
        (1.0 + rt.hp_growth_per_room * rooms_in_biome as f32) * (1.0 + rt.hp_growth_per_biome * biome_idx as f32);
    world.insert_resource(Encounter {
        budget_left: e.budget * growth * count,
        budget_total: (e.budget * growth * count).max(1.0),
        elapsed: 0.0,
        duration: e.duration,
        rate_start: e.rate_start,
        rate_end: e.rate_end,
        max_alive: e.max_alive,
        elite_chance: e.elite_chance,
        accum: 0.0,
        hp_mult,
        anvil_gated: room.kind == RoomKind::Anvil,
        alive: 0,
        last_kills: world.resource::<RunState>().kills,
        stall: 0.0,
    });

    // Fixed spawns (mini-bosses, bosses, elite challenges).
    let fixed: Vec<EnemyId> = e.fixed.iter().filter_map(|k| db.enemies.id(k)).map(EnemyId).collect();
    if !fixed.is_empty() {
        let tuning = {
            let t = world.resource::<Tuning>();
            Tuning { enemy: t.enemy, party: t.party }
        };
        let mut ids = world.remove_resource::<NetIds>().unwrap_or_default();
        let mut rngs = world.remove_resource::<Rngs>().expect("Rngs resource");
        let at = Vec2::new(0.0, room.half_extents.y * 0.35);
        {
            let mut commands = world.commands();
            for (i, def) in fixed.iter().enumerate() {
                let p = arena.resolve(at + Vec2::new(i as f32 * 3.0 - (fixed.len() - 1) as f32 * 1.5, 0.0), 1.0);
                spawn_enemy(&mut commands, &mut ids, &db, &tuning, hp_mult, *def, p, &mut rngs.director);
            }
        }
        world.flush();
        world.insert_resource(ids);
        world.insert_resource(rngs);
    }

    // The anvil.
    if let Some(at) = room.anvil {
        let net = world.resource_mut::<NetIds>().alloc();
        world.spawn((
            Replicated(net),
            Pos(at),
            RoomScoped,
            AnvilStation { state: AnvilState::Dormant, progress: 0.0, forge_left: 0.0, contested: false },
        ));
    }

    // Move the party to the entrance.
    let mut players = world.query::<(&Player, &mut Pos, &mut Mover, &mut Kit, &mut Arsenal, &Stats)>();
    for (player, mut pos, mut mover, mut kit, mut arsenal, stats) in players.iter_mut(world) {
        let offset =
            [Vec2::ZERO, Vec2::new(-1.6, 0.0), Vec2::new(1.6, 0.0), Vec2::new(0.0, -1.6)][player.slot as usize % 4];
        let p = arena.resolve(room.player_spawn + offset, stats.0.radius);
        pos.0 = p;
        mover.0.pos = p;
        mover.0.vel = Vec2::ZERO;
        mover.0.dash_left = 0.0;
        kit.airborne = None;
        kit.rush = None;
        kit.pending = None;
        arsenal.wallet.charges = 0;
    }
    let mut run = world.resource_mut::<RunState>();
    run.room = room_id;
    run.room_kind = room.kind;
    run.room_serial += 1;
    run.phase = RunPhase::Combat;
    run.doors_spawned = false;
    run.cleared_timer = 0.0;
    run.transition = 0.8;
}

/// Room cleared → rewards → doors; the final boss → victory.
#[allow(clippy::type_complexity)]
pub fn room_flow(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    settings: Res<SimSettings>,
    tuning: Res<Tuning>,
    enc: Res<Encounter>,
    arena: Res<ArenaRes>,
    mut run: ResMut<RunState>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    anvils: Query<&AnvilStation>,
    enemies: Query<&Enemy>,
    mut players: Query<(&Player, &Pos, &Stats, &mut Vitals, &mut BoonChoice, &mut Arsenal, &Life)>,
) {
    if !run.started || run.is_over() {
        return;
    }
    let dt = clock.gdt();
    run.transition = (run.transition - dt).max(0.0);
    let rt = &content.game.run;
    match run.phase {
        RunPhase::Combat => {
            let anvil_done = anvils.iter().all(|a| !matches!(a.state, AnvilState::Dormant | AnvilState::Kindling));
            let alive = enemies.iter().any(|e| e.hp > 0.0);
            if run.transition > 0.0 || enc.budget_left > 0.0 || alive || !anvil_done {
                return;
            }
            run.phase = RunPhase::Cleared;
            run.cleared_timer = rt.door_delay;
            run.depth += 1;
            run.rooms_in_biome += 1;
            run.ember += rt.ember_per_room * tuning.enemy.ember_mult;
            events.0.push(GameEvent::RoomCleared);
            let drops = &content.game.drops;
            let reward = run.reward.take();
            for (p, pos, stats, mut vitals, mut choice, mut arsenal, _) in &mut players {
                match reward {
                    Some(DoorReward::PartCache) | Some(DoorReward::EliteChallenge) => {
                        let n = drops.cache_parts + if reward == Some(DoorReward::EliteChallenge) { 1 } else { 0 };
                        for _ in 0..n {
                            let (part, rarity) =
                                roll_part(&content, settings.phase, &mut rngs.loot, stats.0.luck, Rarity::Common);
                            let inst = arsenal.instance(part, rarity);
                            commands.spawn((
                                Replicated(ids.alloc()),
                                Pos(arena.0.resolve(pos.0 + rngs.loot.unit_vec2() * 1.5, 0.3)),
                                RoomScoped,
                                Pickup { loot: Loot::Part(inst), owner: Some(p.slot), life: 120.0 },
                            ));
                        }
                    }
                    Some(DoorReward::ShardCache) => {
                        arsenal.wallet.godshards += (drops.cache_shards as f32 * tuning.enemy.loot) as u32;
                    }
                    Some(DoorReward::Healing) => {
                        vitals.hp =
                            (vitals.hp + stats.0.max_hp * 0.4 * tuning.enemy.healing_received).min(stats.0.max_hp);
                    }
                    Some(DoorReward::Boon { god }) => {
                        choice.god = Some(god);
                        choice.offer = make_offer(
                            &content,
                            settings.phase,
                            &mut rngs.boons,
                            god,
                            &arsenal.boons,
                            tuning.party,
                            stats.0.luck,
                        );
                    }
                    _ => {}
                }
            }
            // Last room of the biome: onward to the next biome, or victory.
            let biome = content.biome(run.biomes[run.biome_idx]);
            if run.step + 1 >= biome.sequence.len() && run.biome_idx + 1 >= run.biomes.len() {
                run.phase = RunPhase::Victory;
                run.ember += rt.ember_victory_bonus * tuning.enemy.ember_mult;
            }
        }
        RunPhase::Cleared => {
            if run.doors_spawned {
                return;
            }
            run.cleared_timer -= dt;
            if run.cleared_timer > 0.0 {
                return;
            }
            run.doors_spawned = true;
            let room = content.room(run.room);
            let biome = content.biome(run.biomes[run.biome_idx]);
            let next = biome.sequence.get(run.step + 1).copied();
            let rewards: Vec<DoorReward> = match next {
                Some(RunStep::Door) => {
                    let remaining_doors =
                        biome.sequence[run.step + 1..].iter().filter(|s| **s == RunStep::Door).count();
                    let need_anvils = (biome.min_anvils as usize).saturating_sub(run.anvils_offered as usize);
                    let n = room.exits.len().clamp(1, 3);
                    let mut pool = vec![
                        DoorReward::PartCache,
                        DoorReward::ShardCache,
                        DoorReward::Anvil,
                        DoorReward::Healing,
                        DoorReward::EliteChallenge,
                    ];
                    let gods: Vec<u16> =
                        content.gods.enumerate().filter(|(_, g)| g.phase <= settings.phase).map(|(i, _)| i).collect();
                    for _ in 0..2 {
                        if let Some(g) = rngs.director.pick(&gods) {
                            pool.push(DoorReward::Boon { god: *g });
                        }
                    }
                    let mut picked: Vec<DoorReward> = Vec::new();
                    if need_anvils >= remaining_doors || rngs.director.chance(0.35) {
                        picked.push(DoorReward::Anvil);
                    }
                    while picked.len() < n && !pool.is_empty() {
                        let i = rngs.director.range_u32(0, pool.len() as u32) as usize;
                        let r = pool.swap_remove(i);
                        if !picked.contains(&r) {
                            picked.push(r);
                        }
                    }
                    if picked.contains(&DoorReward::Anvil) {
                        run.anvils_offered += 1;
                    }
                    picked
                }
                _ => vec![DoorReward::Onward],
            };
            let exits: Vec<Vec2> = if room.exits.is_empty() {
                vec![Vec2::new(0.0, room.half_extents.y - 1.0)]
            } else {
                room.exits.clone()
            };
            for (i, reward) in rewards.into_iter().enumerate() {
                let at = exits[i % exits.len()];
                commands.spawn((Replicated(ids.alloc()), Pos(at), RoomScoped, Door { reward, index: i as u8 }));
            }
        }
        _ => {}
    }
}

/// A player picks a door: interact while standing on it, or the ChooseDoor action (UI).
pub fn door_choice(
    mut run: ResMut<RunState>,
    players: Query<(&Pos, &PlayerInput, &Life), With<Player>>,
    doors: Query<(&Pos, &Door)>,
) {
    if run.phase != RunPhase::Cleared || !run.doors_spawned || run.pending_door.is_some() {
        return;
    }
    for (pos, input, life) in &players {
        if !life.state.is_alive() {
            continue;
        }
        let by_action = match input.cmd.action {
            Some((_, PlayerAction::ChooseDoor(i))) => doors.iter().find(|(_, d)| d.index == i).map(|(_, d)| d.reward),
            _ => None,
        };
        let by_interact = (input.new.interact > 0)
            .then(|| doors.iter().find(|(dp, _)| dp.0.distance(pos.0) < 2.2).map(|(_, d)| d.reward))
            .flatten();
        if let Some(reward) = by_action.or(by_interact) {
            run.pending_door = Some(reward);
            return;
        }
    }
}

/// Exclusive: perform a pending room change.
pub fn room_transition(world: &mut World) {
    let Some(reward) = world.resource_mut::<RunState>().pending_door.take() else { return };
    let db = world.resource::<Content>().0.clone();
    let phase = world.resource::<SimSettings>().phase;
    let (biome, kind, avoid) = {
        let mut run = world.resource_mut::<RunState>();
        let seq_len = db.biome(run.biomes[run.biome_idx]).sequence.len();
        if run.step + 1 >= seq_len {
            if run.biome_idx + 1 >= run.biomes.len() {
                return;
            }
            run.biome_idx += 1;
            run.step = 0;
            run.rooms_in_biome = 0;
            run.anvils_offered = 0;
        } else {
            run.step += 1;
        }
        let biome = run.biomes[run.biome_idx];
        let step = db.biome(biome).sequence[run.step];
        let kind = match step {
            RunStep::Fixed(k) => k,
            RunStep::Door => kind_for_reward(reward),
        };
        run.reward = match step {
            RunStep::Door => Some(reward),
            RunStep::Fixed(RoomKind::MiniBoss) => Some(DoorReward::PartCache),
            _ => None,
        };
        (biome, kind, Some(run.room))
    };
    let room =
        world.resource_scope(|_, mut rngs: Mut<Rngs>| pick_room(&db, biome, kind, phase, avoid, &mut rngs.director));
    load_room(world, room);
}

/// Safety net: anything that escaped the arena or went non-finite is removed.
pub fn cleanup_expired(mut commands: Commands, arena: Res<ArenaRes>, enemies: Query<(Entity, &Pos, &Enemy)>) {
    let limit = arena.0.half_extents + Vec2::splat(12.0);
    for (e, pos, enemy) in &enemies {
        if pos.0.x.abs() > limit.x
            || pos.0.y.abs() > limit.y
            || !pos.0.is_finite()
            || (enemy.hp <= 0.0 && enemy.max_hp > 0.0 && enemy.hp < -1e6)
        {
            commands.entity(e).despawn();
        }
    }
}

pub fn advance_clock(mut clock: ResMut<SimClock>) {
    let dt = clock.gdt();
    clock.tick += 1;
    clock.time += dt;
    if clock.freeze > 0.0 {
        clock.freeze = (clock.freeze - dt).max(0.0);
        if clock.freeze == 0.0 && clock.freeze_resets_cooldowns {
            clock.freeze_resets_cooldowns = false;
            clock.reset_cooldowns = true;
        }
    }
}
