//! Run structure (§4): biomes × rooms, reward doors, room rewards, the boss, victory and defeat.
//!
//! A biome map (OPEN_WORLD.md §5.1) is a room of kind `Expedition`: `load_room` spawns its POIs
//! and objective state, `room_flow` leaves it alone (it never "clears"), and the party leaves it
//! through the Boss Gate (`poi::expedition_flow`), which queues the `Onward` door into the next
//! step, the biome's authored boss arena. Rewards for cleared rooms and completed POIs share one
//! payout path, [`grant_reward`].

use crate::boons::offer_boon;
use crate::components::*;
use crate::damage::roll_part;
use crate::enemies::spawn_enemy;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::procgen;
use gf_content::schema::{MapLayout, Phase, RoomDef, RoomKind, RunStep};
use gf_core::ids::{BiomeId, EnemyId, RoomId};
use gf_core::movement::Arena;
use gf_core::poi::PoiKind;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_core::stats::PlayerStats;
use gf_engine::prelude::*;
use gf_net::{AnvilState, DoorReward, GameEvent, PlayerAction, RunPhase};
use std::sync::Arc;

/// Where the party enters the current room: the template's `player_spawn`, or, on the run's first
/// room when it is a biome map and `--start-at <kind>` is set, beside the first POI of that kind.
/// `load_room` sets it; `players::spawn_player` reads it.
#[derive(Resource, Clone, Copy, Debug, Default)]
pub struct RoomEntry(pub Vec2);

/// The entry of `room`, beside the first POI of kind `start_at` when that is given (QA).
fn entry_point(room: &RoomDef, start_at: Option<PoiKind>) -> Vec2 {
    let site = start_at.and_then(|kind| room.map.as_ref()?.pois.iter().find(|p| p.kind == kind).copied());
    match site {
        // Just outside its ring, on the side facing the Landing.
        Some(site) => site.at + (room.player_spawn - site.at).normalize_or(Vec2::NEG_Y) * (site.radius + 2.5),
        None => room.player_spawn,
    }
}

/// One player's share of a reward (OPEN_WORLD.md §5.4): the payout paths of today's door rewards,
/// shared by cleared rooms (`room_flow`) and completed POIs (`poi::poi_update`).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Payout {
    /// `count` owner-bound part pickups beside the player, each at least `min` rarity (the
    /// `PartCache` / `EliteChallenge` path; Reliquary, Lair and Warlord caches).
    Parts { count: u32, min: Rarity },
    /// Godshards straight into the wallet (the `ShardCache` path; Veins and cache bonuses).
    Shards(u32),
    /// Heal this fraction of max HP × healing received (the `Healing` path; Springs).
    Heal(f32),
    /// A boon offer from this god, queued behind an open one (the `Boon` path; Shrines).
    Boon(u16),
}

impl Payout {
    /// What a cleared room pays each player for the door that led to it.
    pub fn of_door(reward: DoorReward, db: &ContentDb, tuning: &Tuning) -> Option<Payout> {
        let drops = &db.game.drops;
        match reward {
            DoorReward::PartCache => Some(Payout::Parts { count: drops.cache_parts as u32, min: Rarity::Common }),
            DoorReward::EliteChallenge => {
                Some(Payout::Parts { count: drops.cache_parts as u32 + 1, min: Rarity::Common })
            }
            DoorReward::ShardCache => Some(Payout::Shards((drops.cache_shards as f32 * tuning.enemy.loot) as u32)),
            DoorReward::Healing => Some(Payout::Heal(0.4)),
            DoorReward::Boon { god } => Some(Payout::Boon(god)),
            DoorReward::Anvil | DoorReward::Onward => None,
        }
    }
}

/// What a reward grant rolls with and spawns through.
pub struct RewardCtx<'a> {
    pub content: &'a ContentDb,
    pub phase: Phase,
    pub tuning: &'a Tuning,
    pub rngs: &'a mut Rngs,
    pub ids: &'a mut NetIds,
    pub arena: &'a Arena,
}

/// The player receiving a payout.
pub struct Recipient<'a> {
    pub slot: u8,
    pub at: Vec2,
    pub stats: &'a PlayerStats,
    pub vitals: &'a mut Vitals,
    pub choice: &'a mut BoonChoice,
    pub arsenal: &'a mut Arsenal,
}

/// Pay one player their share of a reward.
pub fn grant_reward(ctx: &mut RewardCtx, commands: &mut Commands, payout: Payout, to: Recipient) {
    match payout {
        Payout::Parts { count, min } => {
            for _ in 0..count {
                let (part, rarity) = roll_part(ctx.content, ctx.phase, &mut ctx.rngs.loot, to.stats.luck, min);
                let inst = to.arsenal.instance(part, rarity);
                commands.spawn((
                    Replicated(ctx.ids.alloc()),
                    Pos(ctx.arena.resolve(to.at + ctx.rngs.loot.unit_vec2() * 1.5, 0.3)),
                    RoomScoped,
                    Pickup { loot: Loot::Part(inst), owner: Some(to.slot), life: 120.0 },
                ));
            }
        }
        Payout::Shards(n) => to.arsenal.wallet.godshards += n,
        Payout::Heal(frac) => {
            to.vitals.hp =
                (to.vitals.hp + to.stats.max_hp * frac * ctx.tuning.enemy.healing_received).min(to.stats.max_hp);
        }
        Payout::Boon(god) => offer_boon(
            ctx.content,
            ctx.phase,
            &mut ctx.rngs.boons,
            god,
            to.choice,
            &to.arsenal.boons,
            ctx.tuning.party,
            to.stats.luck,
        ),
    }
}

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
    let authored = db
        .rooms
        .enumerate()
        .find(|(_, r)| r.biome == key && r.kind == kind && r.phase <= phase)
        .map(|(i, _)| RoomId(i))
        .unwrap_or(RoomId(0));
    // QA override: open in a named room (its biome becomes the current biome). `key` lays it out
    // from the run seed like any other room; `key~seed` (hex, as reports print layout keys)
    // reproduces one exact layout, and `key~0` loads the authored template verbatim.
    let requested = world.resource::<SimSettings>().start_room.clone();
    let (room, biome_idx, fixed_seed) = match requested.as_deref().and_then(|k| parse_room_request(&db, k)) {
        Some((r, seed)) => (r, biomes.iter().position(|b| db.biome(*b).key == db.room(r).biome).unwrap_or(0), seed),
        None => {
            if let Some(k) = requested {
                warn!("unknown start room '{k}', using the authored opening");
            }
            (authored, 0, None)
        }
    };
    {
        let mut run = world.resource_mut::<RunState>();
        run.biomes = biomes;
        run.biome_idx = biome_idx;
        run.step = 0;
        run.started = true;
        run.reward = Some(DoorReward::PartCache);
    }
    let seed = fixed_seed.unwrap_or_else(|| next_room_seed(world));
    load_room(world, room, seed);
}

/// `key` or `key~seed` (hex) → (template, fixed layout seed). `None` for an unknown key.
pub fn parse_room_request(db: &ContentDb, request: &str) -> Option<(RoomId, Option<u32>)> {
    let (key, seed) = match request.split_once('~') {
        Some((key, seed)) => (key, Some(u32::from_str_radix(seed.trim_start_matches("0x"), 16).ok()?)),
        None => (request, None),
    };
    Some((RoomId(db.rooms.id(key)?), seed))
}

/// Layout seed for the next room: derived from the run seed and the room counter, so a run's
/// maps are reproducible from its seed yet never repeat.
fn next_room_seed(world: &World) -> u32 {
    procgen::room_seed(world.resource::<SimSettings>().seed, world.resource::<RunState>().room_serial)
}

/// Tear down the current room and build `room_id`, laid out from `seed` (0 = authored as-is).
/// Hand-built kinds (bosses, mini-bosses) always use their template and replicate seed 0.
pub fn load_room(world: &mut World, room_id: RoomId, seed: u32) {
    let db = world.resource::<Content>().0.clone();
    let generated = db.rooms.try_get(room_id.0).is_some_and(|r| procgen::is_generated_kind(r.kind));
    let seed = if generated { seed } else { 0 };
    let room = Arc::new(procgen::resolve_room(&db, room_id.0, seed));
    world.insert_resource(RoomLayout(room.clone()));
    // Despawn everything room-scoped.
    let scoped: Vec<Entity> = world.query_filtered::<Entity, With<RoomScoped>>().iter(world).collect();
    for e in scoped {
        world.despawn(e);
    }
    let arena = Arc::new(room.arena());
    world.resource_mut::<Grid>().0.reset(room.half_extents, 2.0);
    world.insert_resource(ArenaRes(arena.clone()));
    // `--start-at` applies to the run's first room only.
    let first = world.resource::<RunState>().room_serial == 0;
    let start_at = if first { world.resource::<SimSettings>().start_at } else { None };
    let entry = entry_point(&room, start_at);
    world.insert_resource(RoomEntry(entry));

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
    // A biome map's horde is the horde director's (per player cluster): its encounter holds a
    // token budget that is never spent, so `encounter_left` stays 1.0 and the bots' room mop-up
    // never fires there.
    let budget = if room.map.is_some() { 1.0 } else { e.budget * growth * count };
    world.insert_resource(Encounter {
        budget_left: budget,
        budget_total: budget.max(1.0),
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

    // Fixed spawns (mini-bosses, bosses, elite challenges). A boss arena reached through a biome
    // map's gate applies the gate's HP multiplier (`boss_hp_mult` × Unworthy), once.
    let boss_hp = if room.kind == RoomKind::Boss {
        std::mem::replace(&mut world.resource_mut::<RunState>().next_boss_hp, 1.0)
    } else {
        1.0
    };
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
                spawn_enemy(&mut commands, &mut ids, &db, &tuning, hp_mult * boss_hp, *def, p, &mut rngs.director);
            }
        }
        world.flush();
        world.insert_resource(ids);
        world.insert_resource(rngs);
    }

    // The anvil.
    if let Some(at) = room.anvil {
        let net = world.resource_mut::<NetIds>().alloc();
        world.spawn((Replicated(net), Pos(at), RoomScoped, AnvilStation::dormant()));
    }

    // A biome map: its points of interest and objective state (rooms keep an inactive stage).
    // The horde's flow grid is rebuilt by `flow::refresh_flow` when `room_serial` changes.
    match room.map.as_ref() {
        Some(map) => {
            crate::poi::spawn_pois(world, map);
            world.insert_resource(expedition_for(&room, map));
        }
        None => world.insert_resource(Expedition::default()),
    }
    world.insert_resource(Flow::default());

    // Move the party to the entrance.
    let mut players = world.query::<(&Player, &mut Pos, &mut Mover, &mut Kit, &mut Arsenal, &Stats)>();
    for (player, mut pos, mut mover, mut kit, mut arsenal, stats) in players.iter_mut(world) {
        let offset = crate::players::SPAWN_OFFSETS[player.slot as usize % 4];
        let p = arena.resolve(entry + offset, stats.0.radius);
        pos.0 = p;
        mover.0.pos = p;
        mover.0.vel = Vec2::ZERO;
        mover.0.dash_left = 0.0;
        kit.airborne = None;
        kit.rush = None;
        kit.pending = None;
        arsenal.wallet.charges = 0;
        arsenal.charges_from = None;
    }
    let mut run = world.resource_mut::<RunState>();
    run.room = room_id;
    run.room_kind = room.kind;
    run.room_seed = seed;
    run.room_serial += 1;
    run.phase = RunPhase::Combat;
    run.doors_spawned = false;
    run.cleared_timer = 0.0;
    run.transition = 0.8;
}

/// A fresh objective state for biome map `map` of template `room` (§5.2): the Seals the gate
/// needs, one sleeping camp per `map.camps` (each holding its pack plus its elite leader), and an
/// empty explored-tile bitset.
fn expedition_for(room: &RoomDef, map: &MapLayout) -> Expedition {
    let tiles = map.tiles.w as usize * map.tiles.h as usize;
    Expedition {
        active: true,
        required: room.expedition.as_ref().map_or(0, |x| x.seals_required),
        camps: map
            .camps
            .iter()
            .map(|c| CampRuntime { state: CampState::Asleep, left: c.count.saturating_add(c.elite.is_some() as u8) })
            .collect(),
        explored: vec![0; tiles.div_ceil(64)],
        ..Default::default()
    }
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
    layout: Res<RoomLayout>,
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
        // A biome map never clears: the party leaves it through its gate (`poi::expedition_flow`).
        RunPhase::Combat if run.room_kind == RoomKind::Expedition => {}
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
            if let Some(payout) = run.reward.take().and_then(|r| Payout::of_door(r, &content, &tuning)) {
                let mut ctx = RewardCtx {
                    content: &content,
                    phase: settings.phase,
                    tuning: &tuning,
                    rngs: &mut rngs,
                    ids: &mut ids,
                    arena: &arena.0,
                };
                for (p, pos, stats, mut vitals, mut choice, mut arsenal, _) in &mut players {
                    let to = Recipient {
                        slot: p.slot,
                        at: pos.0,
                        stats: &stats.0,
                        vitals: &mut vitals,
                        choice: &mut choice,
                        arsenal: &mut arsenal,
                    };
                    grant_reward(&mut ctx, &mut commands, payout, to);
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
            let room = &layout.0;
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
    let seed = next_room_seed(world);
    load_room(world, room, seed);
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
