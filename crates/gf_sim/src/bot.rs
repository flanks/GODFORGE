//! Bots and the headless runner. Bots play through the *real* network path: each is a `NetClient`
//! on the loopback transport that sees only replicated snapshots and sends commands — so the
//! nightly bot run (§14, §20.7) exercises exactly what players do.

use crate::enemies::shape_contains;
use crate::server::{SimConfig, SimServer};
use gf_content::ContentDb;
use gf_content::schema::TelegraphShape;
use gf_core::aim::{AimMode, TargetBias};
use gf_core::forge::{ForgeAction, Slot};
use gf_core::ids::{EnemyId, PartId, RoomId};
use gf_core::math::lead_point;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::quant::{angle_to_u16, stick_to_i8, u16_to_dir};
use gf_net::transport::loopback;
use gf_net::*;
use std::sync::Arc;
use std::time::Instant;

/// Current position of a replicated entity at `tick` (extrapolates straight-line motion).
pub fn entity_pos(e: &EntityView, tick: u32) -> Vec2 {
    let p = e.pos.to_vec2();
    match e.motion {
        Some(m) => p + m.vel.to_vec2() * (tick.saturating_sub(m.t0) as f32 * gf_core::SIM_DT),
        None => p,
    }
}

/// Decode a wire telegraph shape.
pub fn tele_shape(s: TeleShape) -> TelegraphShape {
    let f = |v: u16| v as f32 / 32.0;
    match s {
        TeleShape::Circle { r } => TelegraphShape::Circle { radius: f(r) },
        TeleShape::Line { len, width } => TelegraphShape::Line { length: f(len), width: f(width) },
        TeleShape::Cone { range, angle_deg } => TelegraphShape::Cone { range: f(range), angle_deg: angle_deg as f32 },
        TeleShape::Ring { inner, outer } => TelegraphShape::Ring { inner: f(inner), outer: f(outer) },
    }
}

pub struct BotBrain {
    pub slot: u8,
    pub mode: AimMode,
    presses: Presses,
    rng: GfRng,
    next_action_tick: u32,
    strafe: f32,
}

impl BotBrain {
    pub fn new(slot: u8, mode: AimMode, seed: u64) -> Self {
        Self { slot, mode, presses: Presses::default(), rng: GfRng::new(seed), next_action_tick: 0, strafe: 1.0 }
    }

    /// Decide this tick's command (and at most one reliable action) from a snapshot.
    pub fn think(&mut self, w: &WorldSnapshot, db: &ContentDb) -> (PlayerCommand, Option<PlayerAction>) {
        let mut cmd = PlayerCommand { aim_mode: self.mode, bias: TargetBias::Balanced, ..Default::default() };
        let Some(me) = w.players.iter().find(|p| p.slot == self.slot) else { return (cmd, None) };
        let pos = me.mover.pos;
        let tick = w.tick;
        let half = db.rooms.try_get(w.run.room).map_or(Vec2::splat(20.0), |r| r.half_extents);
        let _ = RoomId(w.run.room);

        struct Foe {
            pos: Vec2,
            vel: Vec2,
            radius: f32,
            boss: bool,
        }
        let mut foes: Vec<Foe> = Vec::new();
        let mut danger = Vec2::ZERO;
        let mut in_danger = false;
        let mut pickups: Vec<Vec2> = Vec::new();
        let mut doors: Vec<(Vec2, DoorReward, u8)> = Vec::new();
        let mut anvil_pos: Option<Vec2> = None;
        for e in &w.entities {
            let p = entity_pos(e, tick);
            match e.kind {
                EntityKind::Enemy { def } => {
                    let d = db.enemies.try_get(def).map_or(0.5, |d| d.radius * d.scale);
                    let facing = gf_net::quant::u8_to_dir(e.facing);
                    let vel = if e.flags.contains(EntityFlags::CHARGING) { facing * 10.0 } else { Vec2::ZERO };
                    foes.push(Foe { pos: p, vel, radius: d, boss: e.flags.contains(EntityFlags::BOSS) });
                    let _ = EnemyId(def);
                }
                EntityKind::Telegraph { shape, dir, .. } if !e.flags.contains(EntityFlags::ALLY) => {
                    let shape = tele_shape(shape);
                    let d = u16_to_dir(dir);
                    if shape_contains(&shape, p, d, pos, 0.8) {
                        in_danger = true;
                        let away = match shape {
                            TelegraphShape::Line { .. } => {
                                let side = d.perp().dot(pos - p).signum();
                                d.perp() * if side == 0.0 { 1.0 } else { side }
                            }
                            _ => (pos - p).normalize_or(Vec2::Y),
                        };
                        danger += away;
                    }
                }
                EntityKind::EnemyShot { .. } => {
                    if let Some(m) = e.motion {
                        let v = m.vel.to_vec2();
                        let to_me = pos - p;
                        if to_me.length() < 3.0 && v.dot(to_me) > 0.0 {
                            in_danger = true;
                            danger += v.perp().normalize_or_zero() * v.perp().dot(to_me).signum();
                        }
                    }
                }
                EntityKind::Hazard { radius_q, .. } if !e.flags.contains(EntityFlags::ALLY) => {
                    if p.distance(pos) < radius_q as f32 / 32.0 + 0.6 {
                        in_danger = true;
                        danger += (pos - p).normalize_or(Vec2::Y);
                    }
                }
                EntityKind::Pickup { owner, .. } => {
                    if owner.is_none_or(|o| o == self.slot) {
                        pickups.push(p);
                    }
                }
                EntityKind::Door { reward, index } => doors.push((p, reward, index)),
                EntityKind::Anvil => anvil_pos = Some(p),
                _ => {}
            }
        }

        // ── goal ──
        let anvil_state = w.run.anvil.map(|a| a.state);
        let radius = db.game.anvil.radius;
        let bag = &w.private.bag;
        let mut goal: Option<(Vec2, f32)> = None;
        let mut interact = false;
        if w.run.phase == RunPhase::Cleared && !doors.is_empty() {
            let wants_anvil = !bag.items.is_empty();
            let pick = doors
                .iter()
                .max_by_key(|(_, r, i)| {
                    let score = match r {
                        DoorReward::Anvil if wants_anvil => 5,
                        DoorReward::PartCache => 4,
                        DoorReward::Boon { .. } => 3,
                        DoorReward::Anvil => 3,
                        DoorReward::Healing if me.hp < me.max_hp * 0.5 => 6,
                        _ => 1,
                    };
                    (score, 255 - *i)
                })
                .copied();
            if let Some((p, _, _)) = pick {
                goal = Some((p, 0.8));
                interact = p.distance(pos) < 1.8;
            }
        } else if let (Some(a), Some(state)) = (anvil_pos, anvil_state) {
            match state {
                AnvilState::Dormant => {
                    goal = Some((a, radius * 0.5));
                    interact = a.distance(pos) < radius * 0.8;
                }
                AnvilState::Kindling => goal = Some((a, radius * 0.55)),
                AnvilState::Hot if !bag.items.is_empty() || w.private.wallet.charges > 0 => {
                    goal = Some((a, radius * 0.5))
                }
                _ => {}
            }
        }
        if goal.is_none()
            && let Some(p) = pickups
                .iter()
                .filter(|p| p.distance(pos) < 12.0)
                .min_by(|a, b| a.distance_squared(pos).total_cmp(&b.distance_squared(pos)))
        {
            goal = Some((*p, 0.3));
        }

        // ── movement: dodge telegraphs, keep distance, chase goals, stay off walls ──
        let mut repel = Vec2::ZERO;
        let mut nearest = f32::INFINITY;
        let mut near_count = 0;
        let mut boss_near = false;
        let mut centroid = Vec2::ZERO;
        for f in &foes {
            let d = f.pos.distance(pos) - f.radius;
            nearest = nearest.min(d);
            if d < 7.0 {
                near_count += 1;
                centroid += f.pos;
                repel += (pos - f.pos).normalize_or(Vec2::Y) / (d.max(0.3) * d.max(0.3)) * 4.0;
            }
            boss_near |= f.boss && d < 12.0;
        }
        let mut dir = danger * 4.0 + repel;
        if let Some((g, tol)) = goal {
            let to = g - pos;
            if to.length() > tol {
                dir += to.normalize() * if in_danger { 0.5 } else { 2.0 };
            }
        }
        if near_count == 0
            && goal.is_none()
            && let Some(f) =
                foes.iter().min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos)))
        {
            // Hunt stragglers.
            dir += (f.pos - pos).normalize_or_zero() * 1.5;
        }
        if near_count > 0 && goal.is_none() {
            centroid /= near_count as f32;
            let to_c = centroid - pos;
            dir += to_c.perp().normalize_or_zero() * self.strafe * 0.8;
            if to_c.length() > 7.0 {
                dir += to_c.normalize() * 0.6;
            }
        }
        if self.rng.chance(0.004) {
            self.strafe = -self.strafe;
        }
        let edge = (pos.abs() - (half - Vec2::splat(3.0))).max(Vec2::ZERO);
        dir -= pos.signum() * edge * 1.5;
        let mut move_dir = dir.normalize_or_zero();
        // Whisker steering around room obstacles (slide past pillars instead of pushing into them).
        if let Some(room) = db.rooms.try_get(w.run.room)
            && move_dir != Vec2::ZERO
        {
            let blocked =
                |d: Vec2| room.obstacles.iter().any(|o| (1..=3).any(|k| o.contains(pos + d * (k as f32 * 0.8), 0.6)));
            if blocked(move_dir) {
                let options = [0.6f32, -0.6, 1.2, -1.2, 1.8, -1.8];
                let pref = self.strafe.signum();
                if let Some(d) =
                    options.iter().map(|a| gf_core::math::rotate(move_dir, a * pref)).find(|d| !blocked(*d))
                {
                    move_dir = d;
                }
            }
        }
        cmd.move_dir = stick_to_i8(move_dir);

        // ── aiming ──
        let chassis = &db.chassis_def(me.weapon.chassis).stats;
        let target = foes.iter().filter(|f| f.pos.distance(pos) < chassis.range * 1.05).min_by(|a, b| {
            let sa = a.pos.distance(pos) - if a.boss { 6.0 } else { 0.0 };
            let sb = b.pos.distance(pos) - if b.boss { 6.0 } else { 0.0 };
            sa.total_cmp(&sb)
        });
        match (self.mode, target) {
            (AimMode::Auto, _) => {
                cmd.aim = angle_to_u16(if move_dir == Vec2::ZERO { Vec2::Y } else { move_dir });
                cmd.aim_dist = 64 * 6;
            }
            (_, Some(t)) => {
                let aim_at = lead_point(pos, t.pos, t.vel, chassis.speed.max(1.0)).unwrap_or(t.pos);
                let noise = if self.mode == AimMode::Manual { self.rng.range_f32(-0.06, 0.06) } else { 0.0 };
                let d = gf_core::math::rotate((aim_at - pos).normalize_or(Vec2::Y), noise);
                cmd.aim = angle_to_u16(d);
                cmd.aim_dist = ((aim_at - pos).length() * 64.0).min(60000.0) as u16;
                cmd.fire = true;
            }
            (_, None) => {
                cmd.aim = angle_to_u16(if move_dir == Vec2::ZERO { Vec2::Y } else { move_dir });
                cmd.aim_dist = 64 * 6;
            }
        }

        // ── buttons (press counters) ──
        let alive = me.life.is_alive();
        if alive {
            if (in_danger || nearest < 0.8) && me.mover.dash_charges > 0 {
                self.presses.dash = self.presses.dash.wrapping_add(1);
            }
            if interact {
                self.presses.interact = self.presses.interact.wrapping_add(1);
            }
            if me.cooldowns[0] <= 0.0 && (near_count >= 3 || boss_near) {
                self.presses.active1 = self.presses.active1.wrapping_add(1);
            } else if me.cooldowns[1] <= 0.0 && (near_count >= 2 || boss_near) {
                self.presses.active2 = self.presses.active2.wrapping_add(1);
            }
            if me.ult >= 1.0 && (near_count >= 6 || boss_near) {
                self.presses.ult = self.presses.ult.wrapping_add(1);
            }
            if w.run.overdrive_meter >= 1.0 && near_count >= 6 {
                self.presses.overdrive = self.presses.overdrive.wrapping_add(1);
            }
        }
        cmd.presses = self.presses;
        cmd.forge_open = w.private.at_anvil;

        // ── one reliable action at a time ──
        let mut action = None;
        if tick >= self.next_action_tick {
            if !w.private.boon_offer.is_empty() {
                action = Some(PlayerAction::PickBoon(0));
            } else if w.private.at_anvil {
                action = self.forge_choice(me, &w.private, db);
            } else if bag.items.len() >= bag.capacity as usize {
                action = bag
                    .items
                    .iter()
                    .min_by_key(|p| p.rarity)
                    .map(|p| PlayerAction::Forge(ForgeAction::Salvage { uid: p.uid }));
            }
            if action.is_some() {
                self.next_action_tick = tick + 12;
            }
        }
        (cmd, action)
    }

    fn forge_choice(&self, me: &PlayerView, private: &PrivateView, db: &ContentDb) -> Option<PlayerAction> {
        let slot_of = |p: PartId| db.part_slot(p).unwrap_or(Slot::Relic);
        // 1. Fill empty slots / upgrade to strictly rarer parts.
        for part in &private.bag.items {
            let slot = slot_of(part.part);
            if slot == Slot::Sigil {
                continue;
            }
            match me.weapon.get(slot) {
                None => return Some(PlayerAction::Forge(ForgeAction::Equip { uid: part.uid })),
                Some(eq) if part.rarity > eq.rarity => {
                    return Some(PlayerAction::Forge(ForgeAction::Equip { uid: part.uid }));
                }
                _ => {}
            }
        }
        // 2. Spend charges fusing into equipped parts.
        if private.wallet.charges > 0 {
            if let Some(part) = private.bag.items.iter().find(|p| {
                let slot = slot_of(p.part);
                slot != Slot::Sigil
                    && me.weapon.get(slot).is_some_and(|eq| eq.rarity < Rarity::Godforged && p.rarity >= eq.rarity)
            }) {
                return Some(PlayerAction::Forge(ForgeAction::Fuse { uid: part.uid }));
            }
            // 3. Reroll a Common part if we can afford it.
            if private.wallet.godshards >= db.game.forge.reroll_cost
                && let Some((slot, _)) =
                    me.weapon.equipped().find(|(s, p)| *s != Slot::Sigil && p.rarity == Rarity::Common)
            {
                return Some(PlayerAction::Forge(ForgeAction::Reroll { slot }));
            }
        }
        None
    }
}

#[derive(Clone, Debug)]
pub struct BotSummary {
    pub slot: u8,
    /// Forge-preview DPS of the final build (single target, crowd).
    pub dps: (f32, f32),
    pub character: String,
    pub aim_mode: AimMode,
    pub kills: u32,
    pub damage: f32,
    pub weapon: Vec<String>,
    pub parts: Vec<String>,
}

#[derive(Clone, Debug)]
pub struct RoomTiming {
    pub room: String,
    pub seconds: f32,
    pub kills: u32,
}

#[derive(Clone, Debug)]
pub struct RunReport {
    pub rooms: Vec<RoomTiming>,
    pub outcome: RunPhase,
    pub ticks: u32,
    pub sim_minutes: f32,
    pub wall_seconds: f32,
    pub depth: u16,
    pub kills: u32,
    pub ember: u32,
    pub biome_reached: u16,
    pub max_enemies: usize,
    pub max_entities: usize,
    pub mean_tick_ms: f64,
    pub p50_tick_ms: f64,
    pub p99_tick_ms: f64,
    pub max_tick_ms: f64,
    pub max_snapshot_bytes: usize,
    pub bots: Vec<BotSummary>,
}

/// Run a full game headless with bots over loopback until victory, defeat or `max_ticks`.
pub fn run_headless(
    content: Arc<ContentDb>,
    cfg: SimConfig,
    bots: &[(Loadout, AimMode)],
    max_ticks: u32,
    net: NetConditions,
) -> RunReport {
    let started = Instant::now();
    let (listener, connector) = loopback::listener(net);
    let mut server = SimServer::new(content.clone(), cfg.clone(), Box::new(listener));
    let mut clients: Vec<(NetClient<loopback::LoopbackClient>, BotBrain, Option<Box<WorldSnapshot>>)> = bots
        .iter()
        .enumerate()
        .map(|(i, (loadout, mode))| {
            let client = NetClient::new(connector.connect(), format!("bot-{i}"), *loadout, content.hash);
            (client, BotBrain::new(i as u8, *mode, cfg.seed ^ ((i as u64 + 1) * 0x9E37_79B9)), None)
        })
        .collect();
    let mut ticks = 0;
    let mut ended_at: Option<u32> = None;
    let trace = std::env::var_os("GODFORGE_TRACE").is_some();
    let mut rooms: Vec<RoomTiming> = Vec::new();
    let mut room_start = (0u32, 0.0f32, 0u32, String::new());
    while ticks < max_ticks {
        for (client, brain, latest) in &mut clients {
            for ev in client.poll() {
                match ev {
                    ClientEvent::Welcome { slot, .. } => brain.slot = slot,
                    ClientEvent::Snapshot(w) => *latest = Some(w),
                    _ => {}
                }
            }
            if let Some(w) = latest.as_deref() {
                let (cmd, action) = brain.think(w, &content);
                if let Some(a) = action {
                    client.queue_action(a);
                }
                client.send_command(cmd);
            }
        }
        server.tick();
        ticks += 1;
        {
            let world = server.world();
            let run = world.resource::<crate::resources::RunState>();
            let time = world.resource::<crate::resources::SimClock>().time;
            if run.room_serial != room_start.0 {
                if room_start.0 != 0 {
                    rooms.push(RoomTiming {
                        room: room_start.3.clone(),
                        seconds: time - room_start.1,
                        kills: run.kills - room_start.2,
                    });
                }
                room_start = (run.room_serial, time, run.kills, content.rooms.get(run.room.0).key.clone());
            }
        }
        if trace && ticks % (60 * 10) == 0 {
            let world = server.world_mut();
            let run = crate::snapshot::run_view(world);
            let players = crate::snapshot::player_views(world);
            let enc = world.resource::<crate::resources::Encounter>();
            eprintln!(
                "[{:>5.1}s] phase={:?} biome={} step={}/{} room={} depth={} kills={} alive={} budget={:.0}/{:.0} anvil={:?} hp={:?} pos={:?}",
                run.time,
                run.phase,
                run.biome,
                run.step,
                run.steps,
                content.rooms.get(run.room).key,
                run.depth,
                run.kills,
                enc.alive,
                enc.budget_left,
                enc.budget_total,
                run.anvil.map(|a| (a.state, (a.progress * 100.0) as u32)),
                players.iter().map(|p| p.hp as i32).collect::<Vec<_>>(),
                players.iter().map(|p| (p.mover.pos.x as i32, p.mover.pos.y as i32)).collect::<Vec<_>>(),
            );
            if enc.alive <= 3 {
                let mut q =
                    world.query::<(&crate::components::Pos, &crate::components::Enemy, &crate::components::Brain)>();
                for (pos, e, brain) in q.iter(world) {
                    eprintln!(
                        "    straggler {} at ({:.1},{:.1}) hp={:.0}/{:.0} state={:?} stun={:.1}",
                        content.enemy(e.def).key,
                        pos.0.x,
                        pos.0.y,
                        e.hp,
                        e.max_hp,
                        brain.state,
                        e.stun
                    );
                }
            }
        }
        let phase = server.run_phase();
        if matches!(phase, RunPhase::Victory | RunPhase::Defeat) && ended_at.is_none() {
            ended_at = Some(ticks);
        }
        if ended_at.is_some_and(|t| ticks > t + 30) {
            break;
        }
    }
    let world = server.world_mut();
    let run = crate::snapshot::run_view(world);
    let players = crate::snapshot::player_views(world);
    let bots = players
        .iter()
        .map(|p| {
            let db = &content;
            let est = gf_core::weapon::estimate_dps(&weapon_for(db, p), &Default::default());
            BotSummary {
                slot: p.slot,
                dps: (est.single_target.round(), est.crowd.round()),
                character: db.characters.get(p.character).name.clone(),
                aim_mode: p.aim_mode,
                kills: p.kills,
                damage: p.damage,
                weapon: gf_core::weapon::describe(&weapon_for(db, p)),
                parts: p
                    .weapon
                    .equipped()
                    .map(|(s, part)| format!("{} {} ({})", s.name(), db.part(part.part).name, part.rarity.name()))
                    .collect(),
            }
        })
        .collect();
    {
        let world = server.world();
        let run = world.resource::<crate::resources::RunState>();
        let time = world.resource::<crate::resources::SimClock>().time;
        rooms.push(RoomTiming {
            room: room_start.3.clone(),
            seconds: time - room_start.1,
            kills: run.kills - room_start.2,
        });
    }
    let s = &server.stats;
    RunReport {
        rooms,
        outcome: run.phase,
        ticks,
        sim_minutes: run.time / 60.0,
        wall_seconds: started.elapsed().as_secs_f32(),
        depth: run.depth,
        kills: run.kills,
        ember: run.ember,
        biome_reached: run.biome,
        max_enemies: s.max_enemies,
        max_entities: s.max_entities,
        mean_tick_ms: s.mean_tick_ms(),
        p50_tick_ms: s.percentile_ms(50.0),
        p99_tick_ms: s.percentile_ms(99.0),
        max_tick_ms: s.max_tick_us as f64 / 1000.0,
        max_snapshot_bytes: s.max_snapshot_bytes,
        bots,
    }
}

/// Recompile a replicated player's weapon for reporting (chassis + equipped parts).
pub fn weapon_for(db: &ContentDb, p: &PlayerView) -> gf_core::weapon::WeaponProfile {
    let mut mods: Vec<gf_core::modifier::Modifier> = db.chassis_def(p.weapon.chassis).mods.clone();
    for (_, part) in p.weapon.equipped() {
        mods.extend(db.part_mods(part.part, part.rarity));
    }
    gf_core::weapon::compile(&db.chassis_def(p.weapon.chassis).stats, &mods)
}
