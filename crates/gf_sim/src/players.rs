//! Players: spawning from a loadout, input, movement (shared `gf_core` step), stat & weapon
//! compilation, pickups, and the Soul-Tether life cycle.

use crate::components::*;
use crate::resources::*;
use gf_content::ContentDb;
use gf_content::schema::{BoonKind, PassiveDef, Phase};
use gf_core::forge::{ForgeWallet, PartBag, Slot, WeaponBuild, matching_recipes};
use gf_core::ids::{CharacterId, ChassisId, PartId, RecipeId, SourceId};
use gf_core::modifier::Modifier;
use gf_core::movement::{MoveInput, MoverState, step_mover};
use gf_core::rarity::Rarity;
use gf_core::revive::{LifeEvent, LifeState, step_life};
use gf_core::stats::{PlayerStats, compile_player_stats};
use gf_core::weapon::{WeaponProfile, compile};
use gf_engine::prelude::*;
use gf_net::quant::{QPos, i8_to_stick, u16_to_dir};
use gf_net::{GameEvent, Loadout, PickupKind};
use std::sync::Arc;

/// Resolve a requested character to a playable one (falls back to the first playable).
pub fn resolve_character(db: &ContentDb, requested: u16, phase: Phase) -> CharacterId {
    let ok = |id: u16| db.kits.get(id as usize).is_some_and(|k| k.is_some()) && db.characters.get(id).phase <= phase;
    if ok(requested) {
        return CharacterId(requested);
    }
    db.characters.enumerate().find(|(i, _)| ok(*i)).map(|(i, _)| CharacterId(i)).unwrap_or(CharacterId(0))
}

/// Collect every modifier affecting a player, in canonical order.
pub fn collect_mods(
    db: &ContentDb,
    character: CharacterId,
    arsenal: &Arsenal,
    kit: &Kit,
    next_shots: Option<&Vec<Modifier>>,
    team: &[(gf_core::ids::BoonId, Rarity)],
    chaos_dash: i8,
) -> Vec<Modifier> {
    let mut mods: Vec<Modifier> = db.chassis_def(arsenal.build.chassis).mods.clone();
    for (_, part) in arsenal.build.equipped() {
        mods.extend(db.part_mods(part.part, part.rarity));
    }
    if let Some(k) = db.kit(character)
        && let PassiveDef::Mods(m) = &k.passive
    {
        mods.extend(m.iter().cloned());
    }
    for (boon, rarity) in arsenal.boons.iter().chain(team.iter()) {
        let def = db.boon(*boon);
        let m = if def.kind == BoonKind::Standard { db.game.rarity.magnitude(*rarity) } else { 1.0 };
        mods.extend(def.mods.iter().map(|x| x.scaled(m)));
    }
    for b in &kit.buffs {
        mods.extend(b.mods.iter().cloned());
    }
    mods.extend(kit.in_field_mods.iter().cloned());
    if chaos_dash != 0 {
        mods.push(Modifier::DashCharges(chaos_dash));
    }
    if let Some(extra) = next_shots {
        mods.extend(extra.iter().cloned());
    }
    mods
}

/// Compile stats + weapon, including named-combo (recipe) bonuses.
pub fn compile_loadout(
    db: &ContentDb,
    character: CharacterId,
    arsenal: &Arsenal,
    kit: &Kit,
    next_shots: Option<&Vec<Modifier>>,
    team: &[(gf_core::ids::BoonId, Rarity)],
    chaos_dash: i8,
) -> (PlayerStats, WeaponProfile, Vec<RecipeId>) {
    let mut mods = collect_mods(db, character, arsenal, kit, next_shots, team, chaos_dash);
    let chassis = &db.chassis_def(arsenal.build.chassis).stats;
    let first = compile(chassis, &mods);
    let recipes = matching_recipes(
        db.recipe_ingredients.iter().enumerate().map(|(i, ing)| (RecipeId(i as u16), ing.as_slice())),
        &arsenal.build,
        first.element,
    );
    let profile = if recipes.is_empty() {
        first
    } else {
        for r in &recipes {
            mods.extend(db.recipes.get(r.0).bonus.iter().cloned());
        }
        compile(chassis, &mods)
    };
    let stats = compile_player_stats(&db.character(character).stats, &mods);
    (stats, profile, recipes)
}

fn new_kit(db: &ContentDb, character: CharacterId) -> Kit {
    let kit = db.kit(character);
    let passive = match kit.map(|k| &k.passive) {
        Some(PassiveDef::ArmorConversion { .. }) => PassiveState::Armor { armor: 0.0, break_cd: 0.0 },
        Some(PassiveDef::StaticCharge { .. }) => PassiveState::Static { charge: 0.0 },
        Some(PassiveDef::GhostStep { .. }) => PassiveState::Ghost { crit: 0.0 },
        _ => PassiveState::None,
    };
    let cds = kit.map_or([8.0, 12.0], |k| [k.active1.cooldown, k.active2.cooldown]);
    Kit {
        cooldowns: [0.0; 2],
        cooldowns_max: cds,
        ult: 0.0,
        buffs: Vec::new(),
        pending: None,
        airborne: None,
        rush: None,
        passive,
        dirty: false,
        in_field_mods: Vec::new(),
    }
}

/// Spawn a player entity from a hub loadout.
pub fn spawn_player(world: &mut World, slot: u8, name: &str, loadout: Loadout) -> Entity {
    let db = world.resource::<Content>().0.clone();
    let phase = world.resource::<SimSettings>().phase;
    let chaos_dash = world.resource::<Tuning>().enemy.player_dash_charges;
    let team: Vec<_> = world.resource::<TeamBoons>().0.clone();
    let character = resolve_character(&db, loadout.character, phase);
    let cdef = db.character(character);
    let chassis = db
        .chassis
        .try_get(loadout.chassis)
        .filter(|c| c.phase <= phase)
        .map(|_| ChassisId(loadout.chassis))
        .or_else(|| db.chassis.id(&cdef.signature_chassis).map(ChassisId))
        .unwrap_or(ChassisId(0));
    let sigil = loadout.sigil.filter(|s| db.part_slot(PartId(*s)) == Some(Slot::Sigil)).map(PartId).or_else(|| {
        cdef.sigils.iter().filter_map(|k| db.parts.id(k)).find(|i| db.parts.get(*i).phase <= phase).map(PartId)
    });

    let rules = &db.game.forge;
    let mut arsenal = Arsenal {
        build: WeaponBuild::new(chassis),
        bag: PartBag::with_capacity(rules.bag_capacity),
        wallet: ForgeWallet { godshards: db.game.run.start_shards, charges: 0, free_actions: 0 },
        next_uid: 0,
        boons: Vec::new(),
        discovered: Vec::new(),
        active_recipes: Vec::new(),
    };
    if let Some(s) = sigil {
        let inst = arsenal.instance(s, Rarity::Common);
        arsenal.build.set(Slot::Sigil, Some(inst));
    }
    let kit = new_kit(&db, character);
    let (stats, profile, recipes) = compile_loadout(&db, character, &arsenal, &kit, None, &team, chaos_dash);
    arsenal.active_recipes = recipes.clone();
    arsenal.discovered = recipes;

    let spawn = world.resource::<RunState>().room;
    let room = db.room(spawn);
    let offset = [Vec2::ZERO, Vec2::new(-1.6, 0.0), Vec2::new(1.6, 0.0), Vec2::new(0.0, -1.6)][slot as usize % 4];
    let pos = world.resource::<ArenaRes>().0.resolve(room.player_spawn + offset, stats.radius);
    let net = world.resource_mut::<NetIds>().alloc();
    let rekindles = db.game.revive.solo_rekindles;
    world
        .spawn((
            Player { slot, character, name: name.to_string() },
            Replicated(net),
            Pos(pos),
            Facing(Vec2::Y),
            PlayerInput::default(),
            Mover(MoverState { pos, dash_charges: stats.dash_charges, ..Default::default() }),
            Vitals { hp: stats.max_hp, shield: stats.max_shield, shield_delay: 0.0, bonus_shield: 0.0 },
            Life { state: LifeState::Alive, rekindles },
            Gun {
                profile: Arc::new(profile),
                cooldown: 0.0,
                ramp_time: 0.0,
                shots: 0,
                charge: 0.0,
                prev_trigger: false,
                firing: false,
                beam: None,
                beam_tick: 0.0,
                next_shots: None,
                melee_swing: 0.0,
                fire_button_prev: false,
            },
            Aim {
                mode: Default::default(),
                bias: Default::default(),
                state: Default::default(),
                deadeye: Default::default(),
                dir: Vec2::Y,
                target: None,
            },
            (
                Stats(stats),
                arsenal,
                kit,
                RunStats::default(),
                DamageHistory::default(),
                BoonChoice { rerolls: db.game.run.boon_rerolls, ..Default::default() },
            ),
        ))
        .id()
}

/// Commands → per-tick intent.
pub fn apply_inputs(mut q: Query<(&mut PlayerInput, &mut Aim, &Pos)>) {
    for (mut input, mut aim, pos) in &mut q {
        let cmd = input.cmd;
        input.new = cmd.presses.since(&input.prev);
        input.prev = cmd.presses;
        input.move_dir = i8_to_stick(cmd.move_dir);
        let dir = u16_to_dir(cmd.aim);
        input.aim_dir = dir;
        input.aim_point = pos.0 + dir * (cmd.aim_dist as f32 / 64.0);
        input.fire = cmd.fire;
        aim.mode = cmd.aim_mode;
        aim.bias = cmd.bias;
    }
}

pub fn trigger_overdrive(
    clock: Res<SimClock>,
    content: Res<Content>,
    mut od: ResMut<Overdrive>,
    mut events: ResMut<Events>,
    mut players: Query<(&Player, &PlayerInput, &Life, &mut Kit)>,
) {
    let t = content.game.overdrive;
    let mut by = None;
    for (p, input, life, _) in &players {
        if input.new.overdrive > 0 && life.state.is_alive() && od.0.ready() {
            by = Some(p.slot);
            break;
        }
    }
    if let Some(slot) = by
        && od.0.trigger(slot, &t)
    {
        for (_, _, _, mut kit) in &mut players {
            kit.buffs.push(ActiveBuff {
                remaining: t.duration,
                mods: vec![Modifier::FireRate(1.0 + t.fire_rate_bonus), Modifier::DashCharges(t.extra_dashes as i8)],
                root_self: false,
                taunt: false,
                scale: 1.0,
                pulse: None,
                pulse_timer: 0.0,
                infinite_dash: false,
                source: 3,
            });
            kit.dirty = true;
        }
        events.0.push(GameEvent::Overdrive { slot });
    }
    od.0.tick(clock.gdt());
}

/// Co-op pings mark enemies for focus fire (AUTO target priority honours them).
pub fn pings(
    players: Query<(&Player, &PlayerInput)>,
    mut enemies: Query<(&Pos, &mut Enemy, &Replicated)>,
    mut events: ResMut<Events>,
) {
    for (p, input) in &players {
        if input.new.ping == 0 {
            continue;
        }
        let mut best: Option<(f32, Mut<Enemy>, gf_core::ids::NetId)> = None;
        for (pos, enemy, rep) in &mut enemies {
            let d = pos.0.distance(input.aim_point);
            if d < 3.0 + enemy.radius && best.as_ref().is_none_or(|(bd, _, _)| d < *bd) {
                best = Some((d, enemy, rep.0));
            }
        }
        let target = best.map(|(_, mut e, id)| {
            e.pinged = 8.0;
            id
        });
        events.0.push(GameEvent::Ping { slot: p.slot, pos: QPos::from_vec2(input.aim_point), target });
    }
}

pub fn player_movement(
    clock: Res<SimClock>,
    content: Res<Content>,
    arena: Res<ArenaRes>,
    grid: Res<Grid>,
    mut queue: ResMut<DamageQueue>,
    mut q: Query<(&Player, &mut Mover, &mut Pos, &mut Facing, &PlayerInput, &Stats, &Life, &mut Kit, &Aim)>,
) {
    let dt = clock.gdt();
    let tuning = content.game.movement;
    for (player, mut mover, mut pos, mut facing, input, stats, life, mut kit, aim) in &mut q {
        if aim.dir.length_squared() > 0.0 {
            facing.0 = aim.dir;
        }
        if matches!(life.state, LifeState::Reforging { .. }) {
            mover.0.vel = Vec2::ZERO;
            continue;
        }
        let source = SourceId::player(player.slot);
        if let Some(mut a) = kit.airborne {
            a.t += dt;
            let f = (a.t / a.total).min(1.0);
            mover.0.pos = arena.0.resolve(a.from.lerp(a.to, f), stats.0.radius);
            mover.0.vel = Vec2::ZERO;
            mover.0.iframes = mover.0.iframes.max(0.05);
            kit.airborne = if f >= 1.0 { None } else { Some(a) };
        } else if let Some(mut r) = kit.rush.take() {
            let step = r.dir * r.speed * dt;
            mover.0.pos = arena.0.resolve(mover.0.pos + step, stats.0.radius);
            mover.0.vel = r.dir * r.speed;
            mover.0.iframes = mover.0.iframes.max(0.05);
            if r.damage > 0.0 || r.drag {
                for e in grid.0.in_circle(mover.0.pos, stats.0.radius + 0.6) {
                    if !r.hit.contains(&e.entity) {
                        r.hit.push(e.entity);
                        let mut h = Hit::simple(e.entity, source, r.damage, r.element, HitKind::Ability, e.pos);
                        h.knockback = r.dir * if r.drag { 14.0 } else { 4.0 };
                        h.stun = if r.drag { 0.4 } else { 0.0 };
                        queue.0.push(h);
                    }
                }
            }
            r.remaining -= dt;
            if r.remaining > 0.0 {
                kit.rush = Some(r);
            }
        } else {
            let before = mover.0.pos;
            let infinite = kit.infinite_dash();
            let move_input = MoveInput {
                dir: input.move_dir,
                dash: input.new.dash > 0,
                speed: stats.0.move_speed,
                max_dash_charges: stats.0.dash_charges,
                dash_recharge: stats.0.dash_recharge,
                can_move: !kit.rooted(),
                can_dash: !kit.rooted(),
                wraith: matches!(life.state, LifeState::Downed { .. }),
            };
            let ev = step_mover(&mut mover.0, &move_input, &tuning, dt, &arena.0, stats.0.radius);
            if ev.dashed {
                if infinite {
                    mover.0.dash_charges = stats.0.dash_charges;
                }
                if let Some(nova) = stats.0.dash_nova {
                    for e in grid.0.in_circle(mover.0.pos, nova.radius) {
                        let mut h = Hit::simple(e.entity, source, nova.damage, nova.element, HitKind::Ability, e.pos);
                        h.status = nova.status.map(|s| (s, 1, 3.0));
                        queue.0.push(h);
                    }
                }
            }
            if let PassiveState::Static { charge } = &mut kit.passive
                && let Some(PassiveDef::StaticCharge { per_meter, max_bonus }) =
                    content.kit(player.character).map(|k| &k.passive)
            {
                *charge = (*charge + before.distance(mover.0.pos) * per_meter).min(*max_bonus);
            }
        }
        pos.0 = mover.0.pos;
    }
}

pub fn recompile_players(
    content: Res<Content>,
    team: Res<TeamBoons>,
    tuning: Res<Tuning>,
    mut events: ResMut<Events>,
    mut q: Query<(&Player, &mut Kit, &mut Arsenal, &mut Stats, &mut Gun, &mut Vitals, &mut Mover)>,
) {
    for (player, mut kit, mut arsenal, mut stats, mut gun, mut vitals, mut mover) in &mut q {
        if !kit.dirty {
            continue;
        }
        kit.dirty = false;
        let next = gun.next_shots.as_ref().map(|(_, m)| m);
        let (new_stats, profile, recipes) = compile_loadout(
            &content,
            player.character,
            &arsenal,
            &kit,
            next,
            &team.0,
            tuning.enemy.player_dash_charges,
        );
        for r in &recipes {
            if !arsenal.discovered.contains(r) {
                arsenal.discovered.push(*r);
                events.0.push(GameEvent::RecipeDiscovered { slot: player.slot, recipe: r.0 });
            }
        }
        arsenal.active_recipes = recipes;
        let gained = new_stats.max_hp - stats.0.max_hp;
        if gained > 0.0 {
            vitals.hp += gained;
        }
        vitals.hp = vitals.hp.min(new_stats.max_hp);
        vitals.shield = vitals.shield.min(new_stats.max_shield);
        mover.0.dash_charges = mover.0.dash_charges.min(new_stats.dash_charges);
        stats.0 = new_stats;
        if *gun.profile != profile {
            gun.profile = Arc::new(profile);
        }
    }
}

/// Keep orbiting sawblades in sync with each weapon's `Orbit` behaviour.
pub fn sync_blades(
    mut commands: Commands,
    mut ids: ResMut<NetIds>,
    players: Query<(Entity, &Player, &Gun, &Pos)>,
    blades: Query<(Entity, &Blade)>,
) {
    for (owner, player, gun, pos) in &players {
        let want = gun.profile.orbit;
        let have: Vec<(Entity, &Blade)> = blades.iter().filter(|(_, b)| b.owner == owner).collect();
        let matches = match want {
            Some(o) => {
                have.len() == o.count as usize
                    && have.first().is_some_and(|(_, b)| {
                        b.radius == o.radius && b.damage == o.damage * gun.profile.damage && b.speed == o.speed
                    })
            }
            None => have.is_empty(),
        };
        if matches {
            continue;
        }
        for (e, _) in have {
            commands.entity(e).despawn();
        }
        if let Some(o) = want {
            for i in 0..o.count {
                commands.spawn((
                    Replicated(ids.alloc()),
                    Pos(pos.0),
                    Blade {
                        owner,
                        owner_slot: player.slot,
                        index: i,
                        count: o.count,
                        radius: o.radius,
                        speed: o.speed,
                        damage: o.damage * gun.profile.damage,
                        hit_cd: Vec::new(),
                    },
                ));
            }
        }
    }
}

fn heal(vitals: &mut Vitals, max_hp: f32, amount: f32) {
    vitals.hp = (vitals.hp + amount).min(max_hp);
}

pub fn collect_pickups(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    mut events: ResMut<Events>,
    mut pickups: Query<(Entity, &mut Pos, &mut Pickup), Without<Player>>,
    mut players: Query<
        (&Player, &Pos, &Stats, &Life, &mut Vitals, &mut Arsenal, &mut RunStats, &mut Kit),
        Without<Pickup>,
    >,
) {
    let dt = clock.gdt();
    let rules = &content.game.forge;
    for (entity, mut pos, mut pickup) in &mut pickups {
        pickup.life -= dt;
        if pickup.life <= 0.0 {
            commands.entity(entity).despawn();
            continue;
        }
        // Nearest eligible, living player within their magnet radius.
        let mut best: Option<(f32, u8)> = None;
        for (p, ppos, stats, life, ..) in &players {
            if !life.state.is_alive() || pickup.owner.is_some_and(|o| o != p.slot) {
                continue;
            }
            let d = ppos.0.distance(pos.0);
            if d <= stats.0.pickup_radius && best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, p.slot));
            }
        }
        let Some((dist, slot)) = best else { continue };
        let Some((p, ppos, stats, _, mut vitals, mut arsenal, mut run_stats, mut kit)) =
            players.iter_mut().find(|(p, ..)| p.slot == slot)
        else {
            continue;
        };
        if dist > 0.7 {
            let dir = (ppos.0 - pos.0).normalize_or_zero();
            pos.0 += dir * (14.0 * dt).min(dist);
            continue;
        }
        let kind = match pickup.loot {
            Loot::Part(part) => {
                let slot_kind = content.part_slot(part.part).unwrap_or(Slot::Relic);
                if arsenal.build.get(slot_kind).is_none() && !rules.locked_slots.contains(&slot_kind) {
                    arsenal.build.set(slot_kind, Some(part));
                    kit.dirty = true;
                } else if let Err(part) = arsenal.bag.push(part) {
                    let shards = content.game.rarity.salvage_shards[part.rarity.index()];
                    arsenal.wallet.godshards += shards;
                }
                PickupKind::Part { rarity: part.rarity }
            }
            Loot::Shards(n) => {
                arsenal.wallet.godshards += n;
                run_stats.shards += n;
                PickupKind::Shards(n.min(u16::MAX as u32) as u16)
            }
            Loot::Health(amount) => {
                heal(&mut vitals, stats.0.max_hp, amount * tuning.enemy.healing_received);
                PickupKind::Health
            }
        };
        events.0.push(GameEvent::Pickup { slot: p.slot, kind });
        commands.entity(entity).despawn();
    }
}

/// Downed → tether revive / reforge; team wipe → defeat.
pub fn life_update(
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    mut run: ResMut<RunState>,
    mut events: ResMut<Events>,
    mut q: Query<(&Player, &Pos, &mut Life, &mut Vitals, &Stats, &mut Mover)>,
) {
    let dt = clock.gdt();
    let t = content.game.revive;
    let alive: Vec<(u8, Vec2)> =
        q.iter().filter(|(_, _, l, ..)| l.state.is_alive()).map(|(p, pos, ..)| (p.slot, pos.0)).collect();
    let mut shield_for: Vec<u8> = Vec::new();
    for (player, pos, mut life, mut vitals, stats, mut mover) in &mut q {
        if life.state.is_alive() {
            continue;
        }
        let tethering: Vec<u8> = alive
            .iter()
            .filter(|(s, p)| *s != player.slot && p.distance(pos.0) <= t.tether_range)
            .map(|(s, _)| *s)
            .collect();
        match step_life(&mut life.state, dt, tethering.len() as u32, &t) {
            LifeEvent::Revived => {
                vitals.hp = stats.0.max_hp * t.revive_hp_frac;
                mover.0.iframes = 1.5;
                events.0.push(GameEvent::Revived { slot: player.slot, by: tethering.first().copied() });
                shield_for.extend(tethering);
            }
            LifeEvent::Reforged => {
                vitals.hp = stats.0.max_hp * t.reforge_hp_frac * tuning.enemy.healing_received.max(0.5);
                mover.0.iframes = 2.0;
                events.0.push(GameEvent::Revived { slot: player.slot, by: None });
            }
            LifeEvent::StartedReforge | LifeEvent::None => {}
        }
    }
    for (player, _, _, mut vitals, ..) in &mut q {
        if shield_for.contains(&player.slot) {
            vitals.bonus_shield += t.reviver_shield;
        }
    }
    if run.started
        && !run.is_over()
        && !q.is_empty()
        && gf_core::revive::is_wipe(q.iter().map(|(_, _, l, ..)| &l.state))
    {
        run.phase = gf_net::RunPhase::Defeat;
    }
}
