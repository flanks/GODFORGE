//! Bots and the headless runner. Bots play through the *real* network path: each is a `NetClient`
//! on the loopback transport that sees only replicated snapshots and sends commands — so the
//! nightly bot run (§14, §20.7) exercises exactly what players do.

use crate::enemies::shape_contains;
use crate::nav::NavGrid;
use crate::server::{SimConfig, SimServer};
use gf_content::schema::{AbilityDef, AbilityStep, RoomDef, TelegraphShape};
use gf_content::{ContentDb, procgen};
use gf_core::aim::{AimMode, TargetBias};
use gf_core::forge::{ForgeAction, Slot};
use gf_core::ids::{CharacterId, EnemyId, PartId};
use gf_core::math::lead_point;
use gf_core::movement::{Arena, Obstacle};
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::quant::{angle_to_u16, stick_to_i8, u16_to_dir};
use gf_net::transport::loopback;
use gf_net::*;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

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
    /// The current room's layout, rebuilt from its seed once per room (never per tick).
    room: Option<RoomCache>,
    /// Route to the current goal around the ruins (waypoints; the first is the next target).
    path: Vec<Vec2>,
    path_goal: Vec2,
    path_tick: u32,
}

/// One room as a bot sees it: the layout every peer derives from (template, seed) and a
/// walkability grid for routing.
struct RoomCache {
    /// (room serial, template, seed)
    key: (u32, u16, u32),
    def: Arc<RoomDef>,
    nav: Arc<NavGrid>,
}

impl BotBrain {
    pub fn new(slot: u8, mode: AimMode, seed: u64) -> Self {
        Self {
            slot,
            mode,
            presses: Presses::default(),
            rng: GfRng::new(seed),
            next_action_tick: 0,
            strafe: 1.0,
            room: None,
            path: Vec::new(),
            path_goal: Vec2::ZERO,
            path_tick: 0,
        }
    }

    /// The layout every peer derives from the replicated template + seed, and its nav grid.
    fn room(&mut self, w: &WorldSnapshot, db: &ContentDb, radius: f32) -> (Arc<RoomDef>, Arc<NavGrid>) {
        let key = (w.run.room_serial, w.run.room, w.run.room_seed);
        if let Some(c) = self.room.as_ref().filter(|c| c.key == key) {
            return (c.def.clone(), c.nav.clone());
        }
        let def = Arc::new(procgen::resolve_room(db, w.run.room, w.run.room_seed));
        let arena = Arena::new(def.half_extents, def.obstacles.clone(), Vec::new());
        let nav = Arc::new(NavGrid::new(&arena, radius + 0.15));
        self.room = Some(RoomCache { key, def: def.clone(), nav: nav.clone() });
        self.path.clear();
        (def, nav)
    }

    /// Direction toward `goal`: straight when the way is clear, otherwise along an A* route
    /// around the ruins, aiming at the farthest waypoint in sight.
    fn route(&mut self, nav: &NavGrid, pos: Vec2, goal: Vec2, tick: u32) -> Vec2 {
        if nav.clear_line(pos, goal) {
            self.path.clear();
            return (goal - pos).normalize_or_zero();
        }
        let moved = self.path_goal.distance(goal) > 1.5 && tick >= self.path_tick + 10;
        if self.path.is_empty() || moved || tick >= self.path_tick + 90 {
            self.path = nav.path(pos, goal).unwrap_or_default();
            self.path_goal = goal;
            self.path_tick = tick;
        }
        let next = self.path.iter().take(16).rposition(|p| nav.clear_line(pos, *p)).unwrap_or(0);
        self.path.drain(..next);
        let target = self.path.first().copied().unwrap_or(goal);
        (target - pos).normalize_or_zero()
    }

    /// Decide this tick's command (and at most one reliable action) from a snapshot.
    pub fn think(&mut self, w: &WorldSnapshot, db: &ContentDb) -> (PlayerCommand, Option<PlayerAction>) {
        let mut cmd = PlayerCommand { aim_mode: self.mode, bias: TargetBias::Balanced, ..Default::default() };
        let Some(me) = w.players.iter().find(|p| p.slot == self.slot) else { return (cmd, None) };
        let pos = me.mover.pos;
        let tick = w.tick;
        let (room, nav) = self.room(w, db, me.radius);
        let half = room.half_extents;

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
        // Mop-up: once the spawns are spent, close in on the last few (ranged casters keep their
        // distance behind ruins that eat shots from afar). Bosses are fought at range.
        if goal.is_none()
            && w.run.phase == RunPhase::Combat
            && w.run.encounter_left <= 0.0
            && foes.len() <= 3
            && let Some(f) = foes
                .iter()
                .filter(|f| !f.boss)
                .min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos)))
        {
            goal = Some((f.pos, f.radius + 2.5));
        }

        // Line of fire, by the host's rule: shots die on the ruins, so a foe behind one is not a
        // target (the server's AUTO aim skips it too).
        let chassis = &db.chassis_def(me.weapon.chassis).stats;
        let fire_range = chassis.range * 1.05;
        let occluders: Vec<Obstacle> = room
            .obstacles
            .iter()
            .filter(|o| {
                let (c, r) = o.bounding_circle();
                c.distance(pos) < fire_range + r
            })
            .copied()
            .collect();
        let in_sight = |p: Vec2| p.distance(pos) < fire_range && !occluders.iter().any(|o| o.blocks_segment(pos, p));
        let any_in_sight = foes.iter().any(|f| in_sight(f.pos));

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
        // Travelling somewhere (a door, the anvil, loot, a straggler) routes around the ruins.
        let mut routing = false;
        if let Some((g, tol)) = goal
            && g.distance(pos) > tol
        {
            dir += self.route(&nav, pos, g, tick) * if in_danger { 0.5 } else { 2.0 };
            routing = true;
        }
        if (near_count == 0 || !any_in_sight)
            && goal.is_none()
            && let Some(f) =
                foes.iter().min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos)))
        {
            // Hunt stragglers, or work around the ruins to a clear shot.
            dir += self.route(&nav, pos, f.pos, tick) * 1.5;
            routing = true;
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
        // Whisker steering around room obstacles while fighting (slide past pillars instead of
        // pushing into them); routes already keep clear of them.
        if move_dir != Vec2::ZERO && !(routing && near_count == 0 && !in_danger) {
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
        let target = foes.iter().filter(|f| in_sight(f.pos)).min_by(|a, b| {
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
            // Abilities that plant you (Siege Stance) are suicide next to a boss that drops pools
            // and slam trails on your head: plant only against the horde, and never mid-dodge.
            let kit = db.kit(CharacterId(me.character));
            let plants =
                |a: &AbilityDef| a.steps.iter().any(|s| matches!(s, AbilityStep::Buff { root_self: true, .. }));
            let may_plant = !boss_near && !in_danger;
            let usable = |a: Option<&AbilityDef>| may_plant || !a.is_some_and(plants);
            if me.cooldowns[0] <= 0.0 && (near_count >= 3 || boss_near) && usable(kit.map(|k| &k.active1)) {
                self.presses.active1 = self.presses.active1.wrapping_add(1);
            } else if me.cooldowns[1] <= 0.0 && (near_count >= 2 || boss_near) && usable(kit.map(|k| &k.active2)) {
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
    // Simulated latency is wall-clock time, so a lossy/latent link must run in real time;
    // an ideal link fast-forwards (a 25-minute run takes seconds).
    let paced = !net.latency.is_zero() || !net.jitter.is_zero();
    let step = Duration::from_secs_f64(1.0 / gf_core::SIM_HZ as f64);
    let mut next_tick = Instant::now();
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
        if paced {
            next_tick += step;
            let now = Instant::now();
            if next_tick > now {
                std::thread::sleep(next_tick - now);
            } else {
                next_tick = now;
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
                let key = world.resource::<crate::resources::RoomLayout>().0.key.clone();
                room_start = (run.room_serial, time, run.kills, key);
            }
        }
        if trace {
            // Parts left to expire on the floor (bots should collect their loot on big fields).
            let world = server.world_mut();
            let dt = world.resource::<crate::resources::SimClock>().gdt();
            let players: Vec<Vec2> = world
                .query::<(&crate::components::Pos, &crate::components::Player)>()
                .iter(world)
                .map(|(p, _)| p.0)
                .collect();
            let mut q = world.query::<(&crate::components::Pos, &crate::components::Pickup)>();
            for (pos, pickup) in q.iter(world) {
                if matches!(pickup.loot, crate::components::Loot::Part(_)) && pickup.life > 0.0 && pickup.life <= dt {
                    let d = players.iter().map(|p| p.distance(pos.0)).fold(f32::INFINITY, f32::min);
                    eprintln!("    part expired at ({:.1},{:.1}), {d:.1} from the nearest player", pos.0.x, pos.0.y);
                }
            }
        }
        if trace && ticks % (60 * 10) == 0 {
            let world = server.world_mut();
            let run = crate::snapshot::run_view(world);
            let players = crate::snapshot::player_views(world);
            let room_key = world.resource::<crate::resources::RoomLayout>().0.key.clone();
            let enc = world.resource::<crate::resources::Encounter>();
            eprintln!(
                "[{:>5.1}s] phase={:?} biome={} step={}/{} room={} depth={} kills={} alive={} budget={:.0}/{:.0} anvil={:?} hp={:?} pos={:?} build={:?}",
                run.time,
                run.phase,
                run.biome,
                run.step,
                run.steps,
                room_key,
                run.depth,
                run.kills,
                enc.alive,
                enc.budget_left,
                enc.budget_total,
                run.anvil.map(|a| (a.state, (a.progress * 100.0) as u32)),
                players.iter().map(|p| p.hp as i32).collect::<Vec<_>>(),
                players.iter().map(|p| (p.mover.pos.x as i32, p.mover.pos.y as i32)).collect::<Vec<_>>(),
                players
                    .iter()
                    .map(|p| p.weapon.equipped().map(|(_, part)| &part.rarity.name()[..1]).collect::<String>())
                    .collect::<Vec<_>>(),
            );
            if enc.alive <= 3 {
                let mut q =
                    world.query::<(&crate::components::Pos, &crate::components::Enemy, &crate::components::Brain)>();
                {
                    let mut pq = world.query::<(
                        &crate::components::Pos,
                        &crate::components::RunStats,
                        &crate::components::Aim,
                        &crate::components::Gun,
                    )>();
                    for (pp, st, aim, gun) in pq.iter(world) {
                        eprintln!(
                            "    PROBE player ({:.1},{:.1}) shots={} dmg={:.0} target={:?} dir={:?} firing={}",
                            pp.0.x, pp.0.y, st.shots, st.damage, aim.target, aim.dir, gun.firing
                        );
                    }
                }
                for (pos, e, brain) in q.iter(world) {
                    eprintln!("    PROBE shield={:.0}", e.shield);
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

/// Bot teammates on their own thread, each connected through its transport like any other
/// client. Fills a co-op party for play-testing, attract mode and screenshots. Returns the stop
/// flag and the thread handle; bots leave the session when stopped.
pub fn spawn_bot_party(
    content: Arc<ContentDb>,
    members: Vec<(Box<dyn ClientTransport>, Loadout, AimMode)>,
    seed: u64,
) -> (Arc<AtomicBool>, std::thread::JoinHandle<()>) {
    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    let handle = std::thread::Builder::new()
        .name("gf-bot-party".into())
        .spawn(move || {
            let mut clients: Vec<(NetClient<Box<dyn ClientTransport>>, BotBrain, Option<Box<WorldSnapshot>>)> = members
                .into_iter()
                .enumerate()
                .map(|(i, (transport, loadout, mode))| {
                    let brain = BotBrain::new(0, mode, seed ^ ((i as u64 + 11) * 0x9E37_79B9));
                    (NetClient::new(transport, format!("Bot {}", i + 2), loadout, content.hash), brain, None)
                })
                .collect();
            let step = Duration::from_secs_f64(1.0 / gf_core::SIM_HZ as f64);
            let mut next = Instant::now();
            while !flag.load(Ordering::Relaxed) {
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
                next += step;
                let now = Instant::now();
                if next > now {
                    std::thread::sleep(next - now);
                } else {
                    next = now;
                }
            }
            for (client, _, _) in &mut clients {
                client.leave();
            }
        })
        .expect("spawn bot party thread");
    (stop, handle)
}

/// Recompile a replicated player's weapon for reporting (chassis + equipped parts).
pub fn weapon_for(db: &ContentDb, p: &PlayerView) -> gf_core::weapon::WeaponProfile {
    let mut mods: Vec<gf_core::modifier::Modifier> = db.chassis_def(p.weapon.chassis).mods.clone();
    for (_, part) in p.weapon.equipped() {
        mods.extend(db.part_mods(part.part, part.rarity));
    }
    gf_core::weapon::compile(&db.chassis_def(p.weapon.chassis).stats, &mods)
}
