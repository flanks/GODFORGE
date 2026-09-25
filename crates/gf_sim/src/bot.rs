//! Bots and the headless runner. Bots play through the *real* network path: each is a `NetClient`
//! on the loopback transport that sees only replicated snapshots and sends commands — so the
//! nightly bot run (§14, §20.7) exercises exactly what players do.
//!
//! In rooms a bot fights, takes the anvil and picks doors. On a biome map a utility planner
//! (OPEN_WORLD.md §8.2) chooses what to do every half second: revive, go through the open gate,
//! join a live objective, or (the party's leader) pick the best POI by value over travel time,
//! while the others stay with the leader and help at its POI (the `group` policy). Long hauls
//! are planned over the map's tiles ([`TileNav`]) and walked with the fine grid.

use crate::enemies::shape_contains;
use crate::nav::{NavGrid, TileNav};
use crate::server::{SimConfig, SimServer};
use gf_content::schema::{AbilityDef, AbilityStep, MapLayout, PoiActivation, RoomDef, TelegraphShape};
use gf_content::{ContentDb, procgen};
use gf_core::aim::{AimMode, TargetBias};
use gf_core::forge::{ForgeAction, Slot};
use gf_core::ids::{CharacterId, PartId};
use gf_core::math::lead_point;
use gf_core::movement::{Arena, Obstacle};
use gf_core::poi::{PoiKind, PoiState};
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_core::rng::GfRng;
use gf_engine::prelude::*;
use gf_net::quant::{angle_to_u16, stick_to_i8, u16_to_dir};
use gf_net::transport::loopback;
use gf_net::*;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, PoisonError};
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

/// Goals farther than this are long hauls on a biome map: planned over the tiles first.
const LONG_HAUL: f32 = 24.0;
/// A bot heads straight for the farthest coarse waypoint this close that it has a clear line to.
const COARSE_SIGHT: f32 = 24.0;
/// A coarse route is re-planned this often (ticks), or when its goal moves more than 8 u.
const COARSE_REPLAN: u32 = 180;
/// The planner re-evaluates this often (ticks), or as soon as its objective is settled.
const PLAN_EVERY: u32 = 30;
/// Planner reach (§8.2): revive allies this close, join live objectives this close.
const REVIVE_REACH: f32 = 45.0;
const JOIN_REACH: f32 = 60.0;
/// Group policy: followers stay this close to the leader, and regroup (outside combat) beyond
/// the second distance.
const FOLLOW_NEAR: f32 = 15.0;
const FOLLOW_REGROUP: f32 = 22.0;
/// On a map, loot this close is picked up on the way (the planner's goal waits).
const LOOT_REACH: f32 = 8.0;
/// On a map, the bot hunts foes this close when it has nothing else to do.
const HUNT_REACH: f32 = 40.0;

/// What the planner is after on a biome map.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Plan {
    /// Nothing to go for: fight whatever is near.
    Idle,
    /// Tether a downed ally (slot).
    Revive(u8),
    /// The Boss Gate: interact while it is open, then wait inside the ring.
    Gate,
    /// Work a POI (index into `MapLayout.pois`).
    Poi(u8),
    /// Stay with the party's leader (slot).
    Follow(u8),
}

/// A replicated foe as the bot tracks it.
struct Foe {
    pos: Vec2,
    vel: Vec2,
    radius: f32,
    boss: bool,
}

/// How a POI kind is worked (from the POI tuning rows, with the shipped behaviour as fallback).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Work {
    Hold,
    Clear,
    Use,
    Touch,
    Gate,
}

fn work_of(db: &ContentDb, kind: PoiKind) -> Work {
    match db.game.expedition.poi(kind).map(|t| t.activation) {
        Some(PoiActivation::Hold { .. }) => Work::Hold,
        Some(PoiActivation::Clear { .. }) => Work::Clear,
        Some(PoiActivation::Use) => Work::Use,
        Some(PoiActivation::Touch { .. }) => Work::Touch,
        Some(PoiActivation::Gate) => Work::Gate,
        None => match kind {
            PoiKind::Anvil | PoiKind::Shrine | PoiKind::Reliquary | PoiKind::Vein => Work::Hold,
            PoiKind::Warlord | PoiKind::Lair => Work::Clear,
            PoiKind::Spring => Work::Use,
            PoiKind::Watchfire => Work::Touch,
            PoiKind::Gate => Work::Gate,
        },
    }
}

/// Everything the map planner reads in one tick.
struct MapScene<'a> {
    w: &'a WorldSnapshot,
    db: &'a ContentDb,
    me: &'a PlayerView,
    room: &'a RoomDef,
    map: &'a MapLayout,
    tiles: Option<&'a TileNav>,
    /// Replicated state of each `map.pois[i]` (unseen POIs read as Dormant, the gate as Sealed).
    pois: &'a [PoiState],
    pickups: &'a [Vec2],
    /// Foes within 7 u (in combat).
    near_count: usize,
}

impl MapScene<'_> {
    fn pos(&self) -> Vec2 {
        self.me.mover.pos
    }

    fn player(&self, slot: u8) -> Option<&PlayerView> {
        self.w.players.iter().find(|p| p.slot == slot)
    }

    /// The Boss Gate is open or gathering, or the Seals and the Warlord are in (it opens next).
    fn gate_wanted(&self) -> bool {
        let Some(stage) = self.w.run.stage else { return false };
        let warlord = stage.warlord || !self.room.expedition.as_ref().is_some_and(|x| x.gate_requires_warlord);
        stage.gate != GateView::Sealed || (stage.seals >= stage.required && warlord)
    }

    /// Slack around a POI's ring within which a player counts as present at it.
    fn pad(&self, i: usize) -> f32 {
        if work_of(self.db, self.map.pois[i].kind) == Work::Clear { 8.0 } else { 2.0 }
    }

    /// Something to fight for or claim at the forge, as opposed to a finished site.
    fn live(&self, i: usize) -> bool {
        let site = &self.map.pois[i];
        matches!((site.kind, self.pois[i]), (PoiKind::Anvil, PoiState::Hot) | (_, PoiState::Active))
    }

    /// Living players (me included) within `i`'s ring, give or take its pad.
    fn present(&self, i: usize) -> bool {
        let site = &self.map.pois[i];
        let reach = site.radius + self.pad(i);
        self.w.players.iter().any(|p| p.life.is_alive() && p.mover.pos.distance(site.at) <= reach)
    }
}

pub struct BotBrain {
    pub slot: u8,
    pub mode: AimMode,
    /// Player slots (bits) driven by people. In the group policy a person leads when there is
    /// one: a windowed session's bot teammates mark every slot but their own; a headless party
    /// (and the attract-mode autopilot) is all bots, and its lowest living slot leads.
    pub humans: u8,
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
    /// Biome maps: the tile route to a far goal (waypoints; the first is the next one).
    coarse: Vec<Vec2>,
    coarse_goal: Vec2,
    coarse_tick: u32,
    /// Biome maps: the planner's objective, and the tick it is next re-evaluated.
    plan: Plan,
    plan_due: u32,
    /// Springs (POI indices) this bot has drunk from on the current map.
    springs: Vec<u8>,
    /// The hot anvil (POI index) this bot last stood at: its charges are already granted.
    forged_at: Option<u8>,
    /// Scratch for this tick's line-of-fire blockers (kept to reuse its allocation).
    occluders: Vec<Obstacle>,
}

/// (room serial, template, seed): one room instance, as the host replicates it.
type RoomKey = (u32, u16, u32);

/// One room as a bot sees it: the layout every peer derives from (template, seed), its
/// collision arena, a walkability grid for routing and, on biome maps, the coarse tile grid.
#[derive(Clone)]
struct RoomCache {
    key: RoomKey,
    def: Arc<RoomDef>,
    arena: Arc<Arena>,
    nav: Arc<NavGrid>,
    tiles: Option<Arc<TileNav>>,
}

/// The last room any bot in this process resolved, shared so a party (a headless run's bots, or
/// the windowed game's teammates and autopilot) generates and rasterizes each layout once. That
/// matters on biome maps, where generation and the whole-map nav grid are the expensive part.
static MAP_CACHE: Mutex<Option<MapEntry>> = Mutex::new(None);

struct MapEntry {
    /// The content set (address and hash) and the room, keyed like [`RoomCache`].
    key: (usize, u64, RoomKey),
    def: Arc<RoomDef>,
    arena: Arc<Arena>,
    /// One grid (and on maps one tile grid) per clearance, as bits: heroes differ in radius.
    navs: Vec<(u32, Arc<NavGrid>, Option<Arc<TileNav>>)>,
}

/// The shared layout, arena, nav grid and tile grid (for `clearance`) of `room`, building what
/// is missing.
fn shared_room(db: &ContentDb, room: RoomKey, clearance: f32) -> RoomCache {
    let key = (std::ptr::from_ref(db) as usize, db.hash, room);
    // Held while building, so a bot on another thread waits for the layout instead of repeating it.
    let mut cache = MAP_CACHE.lock().unwrap_or_else(PoisonError::into_inner);
    let entry = match cache.take() {
        Some(entry) if entry.key == key => entry,
        _ => {
            let def = Arc::new(procgen::resolve_room(db, room.1, room.2));
            let arena = Arc::new(def.arena());
            MapEntry { key, def, arena, navs: Vec::new() }
        }
    };
    let entry = cache.insert(entry);
    let bits = clearance.to_bits();
    let (nav, tiles) = match entry.navs.iter().find(|(b, ..)| *b == bits) {
        Some((_, nav, tiles)) => (nav.clone(), tiles.clone()),
        None => {
            let nav = Arc::new(NavGrid::new(&entry.arena, clearance));
            let tiles = entry.def.map.as_ref().map(|m| Arc::new(TileNav::new(m, &nav)));
            entry.navs.push((bits, nav.clone(), tiles.clone()));
            (nav, tiles)
        }
    };
    RoomCache { key: room, def: entry.def.clone(), arena: entry.arena.clone(), nav, tiles }
}

impl BotBrain {
    pub fn new(slot: u8, mode: AimMode, seed: u64) -> Self {
        Self {
            slot,
            mode,
            humans: 0,
            presses: Presses::default(),
            rng: GfRng::new(seed),
            next_action_tick: 0,
            strafe: 1.0,
            room: None,
            path: Vec::new(),
            path_goal: Vec2::ZERO,
            path_tick: 0,
            coarse: Vec::new(),
            coarse_goal: Vec2::ZERO,
            coarse_tick: 0,
            plan: Plan::Idle,
            plan_due: 0,
            springs: Vec::new(),
            forged_at: None,
            occluders: Vec::new(),
        }
    }

    /// The planner's current objective on a biome map (`Idle` in rooms).
    pub fn plan(&self) -> Plan {
        self.plan
    }

    /// The layout every peer derives from the replicated template + seed, its arena and grids.
    fn room(&mut self, w: &WorldSnapshot, db: &ContentDb, radius: f32) -> RoomCache {
        let key = (w.run.room_serial, w.run.room, w.run.room_seed);
        if let Some(c) = self.room.as_ref().filter(|c| c.key == key) {
            return c.clone();
        }
        let cache = shared_room(db, key, radius + 0.15);
        self.room = Some(cache.clone());
        self.path.clear();
        self.coarse.clear();
        self.plan = Plan::Idle;
        self.plan_due = 0;
        self.springs.clear();
        self.forged_at = None;
        cache
    }

    /// Direction toward `goal`: straight when the way is clear, otherwise along an A* route
    /// around the ruins, aiming at the farthest waypoint in sight. On a biome map a far goal is
    /// first routed over the tiles (roads, bridges, passes), and the bot walks toward the
    /// farthest coarse waypoint within [`COARSE_SIGHT`] it has a clear line to, or finds its way
    /// to the next one with the fine grid when a ruin stands in between.
    fn route(&mut self, room: &RoomCache, pos: Vec2, goal: Vec2, tick: u32) -> Vec2 {
        let nav = &room.nav;
        if nav.clear_line(pos, goal) {
            self.path.clear();
            self.coarse.clear();
            return (goal - pos).normalize_or_zero();
        }
        let mut target = goal;
        match room.tiles.as_deref().filter(|_| pos.distance(goal) > LONG_HAUL) {
            Some(tiles) => {
                let stale = self.coarse.is_empty()
                    || self.coarse_goal.distance(goal) > 8.0
                    || tick >= self.coarse_tick + COARSE_REPLAN;
                if stale {
                    self.coarse = tiles.path(pos, goal).unwrap_or_default();
                    self.coarse_goal = goal;
                    self.coarse_tick = tick;
                }
                // Waypoints already reached drop off (the last one is the goal itself).
                while self.coarse.len() > 1 && self.coarse[0].distance(pos) < 2.0 {
                    self.coarse.remove(0);
                }
                let mut sight = None;
                for (i, p) in self.coarse.iter().enumerate().take(12) {
                    if p.distance(pos) <= COARSE_SIGHT && nav.clear_line(pos, *p) {
                        sight = Some(i);
                    }
                }
                if let Some(i) = sight {
                    self.coarse.drain(..i);
                    self.path.clear();
                    return (self.coarse[0] - pos).normalize_or_zero();
                }
                if let Some(p) = self.coarse.first() {
                    target = *p;
                }
            }
            None => self.coarse.clear(),
        }
        let moved = self.path_goal.distance(target) > 1.5 && tick >= self.path_tick + 10;
        if self.path.is_empty() || moved || tick >= self.path_tick + 90 {
            self.path = nav.path(pos, target).unwrap_or_default();
            self.path_goal = target;
            self.path_tick = tick;
        }
        let next = self.path.iter().take(16).rposition(|p| nav.clear_line(pos, *p)).unwrap_or(0);
        self.path.drain(..next);
        let step = self.path.first().copied().unwrap_or(target);
        (step - pos).normalize_or_zero()
    }

    /// Decide this tick's command (and at most one reliable action) from a snapshot.
    pub fn think(&mut self, w: &WorldSnapshot, db: &ContentDb) -> (PlayerCommand, Option<PlayerAction>) {
        let mut cmd = PlayerCommand { aim_mode: self.mode, bias: TargetBias::Balanced, ..Default::default() };
        let Some(me) = w.players.iter().find(|p| p.slot == self.slot) else { return (cmd, None) };
        let pos = me.mover.pos;
        let tick = w.tick;
        let cache = self.room(w, db, me.radius);
        let (room, arena) = (cache.def.clone(), cache.arena.clone());
        let map = room.map.clone();
        let half = room.half_extents;

        let mut foes: Vec<Foe> = Vec::new();
        let mut danger = Vec2::ZERO;
        let mut in_danger = false;
        let mut pickups: Vec<Vec2> = Vec::new();
        let mut doors: Vec<(Vec2, DoorReward, u8)> = Vec::new();
        let mut pois: Vec<PoiState> = map.as_ref().map_or_else(Vec::new, |m| {
            m.pois.iter().map(|s| if s.kind == PoiKind::Gate { PoiState::Sealed } else { PoiState::Dormant }).collect()
        });
        for e in &w.entities {
            let p = entity_pos(e, tick);
            match e.kind {
                EntityKind::Enemy { def } => {
                    let d = db.enemies.try_get(def).map_or(0.5, |d| d.radius * d.scale);
                    let facing = gf_net::quant::u8_to_dir(e.facing);
                    let vel = if e.flags.contains(EntityFlags::CHARGING) { facing * 10.0 } else { Vec2::ZERO };
                    foes.push(Foe { pos: p, vel, radius: d, boss: e.flags.contains(EntityFlags::BOSS) });
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
                EntityKind::Poi { index } => {
                    if let Some(s) = pois.get_mut(index as usize) {
                        *s = PoiState::from_u8(e.status);
                    }
                }
                _ => {}
            }
        }

        // ── the fight around me ──
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

        // ── goal ──
        let (goal, interact) = match map.as_deref() {
            Some(map) => self.map_goal(&MapScene {
                w,
                db,
                me,
                room: &room,
                map,
                tiles: cache.tiles.as_deref(),
                pois: &pois,
                pickups: &pickups,
                near_count,
            }),
            None => room_goal(w, db, me, &doors, &pickups, &foes),
        };
        let bag = &w.private.bag;

        // Line of fire, by the host's rule: shots die on the ruins (and fly over pits), so a foe
        // behind one is not a target (the server's AUTO aim skips it too).
        let chassis = &db.chassis_def(me.weapon.chassis).stats;
        let fire_range = chassis.range * 1.05;
        let mut occluders = std::mem::take(&mut self.occluders);
        occluders.clear();
        arena.occluders(pos, fire_range, &mut occluders);
        let in_sight = |p: Vec2| p.distance(pos) < fire_range && !occluders.iter().any(|o| o.blocks_segment(pos, p));
        let any_in_sight = foes.iter().any(|f| in_sight(f.pos));

        // ── movement: dodge telegraphs, keep distance, chase goals, stay off walls ──
        let mut dir = danger * 4.0 + repel;
        // Travelling somewhere (a door, the anvil, loot, a straggler, an objective) routes around
        // the ruins.
        let mut routing = false;
        if let Some((g, tol)) = goal
            && g.distance(pos) > tol
        {
            dir += self.route(&cache, pos, g, tick) * if in_danger { 0.5 } else { 2.0 };
            routing = true;
        }
        // On a map the horde is everywhere: hunt only what is near, never a camp across the map.
        let hunt_reach = if map.is_some() { HUNT_REACH } else { f32::INFINITY };
        if (near_count == 0 || !any_in_sight)
            && goal.is_none()
            && let Some(f) = foes
                .iter()
                .filter(|f| f.pos.distance(pos) < hunt_reach)
                .min_by(|a, b| a.pos.distance_squared(pos).total_cmp(&b.pos.distance_squared(pos)))
        {
            // Hunt stragglers, or work around the ruins to a clear shot.
            dir += self.route(&cache, pos, f.pos, tick) * 1.5;
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
        // Whisker steering around obstacles and pits while fighting (slide past pillars and along
        // chasm banks instead of pushing into them); routes already keep clear of them.
        if move_dir != Vec2::ZERO && !(routing && near_count == 0 && !in_danger) {
            let blocked = |d: Vec2| (1..=3).any(|k| !arena.walkable(pos + d * (k as f32 * 0.8), 0.6));
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
        self.occluders = occluders;

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

    /// The party's leader under the group policy: the lowest person's slot when a person plays
    /// (downed or not: a downed leader is revived, not replaced), else the lowest living slot.
    fn leader(&self, w: &WorldSnapshot) -> Option<u8> {
        let human = w.players.iter().filter(|p| self.humans & (1 << p.slot) != 0).map(|p| p.slot).min();
        human.or_else(|| w.players.iter().filter(|p| p.life.is_alive()).map(|p| p.slot).min())
    }

    /// Biome map: the planner's goal this tick (where to be, within what tolerance) and whether
    /// to interact.
    fn map_goal(&mut self, s: &MapScene) -> (Option<(Vec2, f32)>, bool) {
        let pos = s.pos();
        let tick = s.w.tick;
        // Downed: drift toward the nearest living ally, so a tether can reach me.
        if !s.me.life.is_alive() {
            let ally =
                s.w.players
                    .iter()
                    .filter(|p| p.slot != self.slot && p.life.is_alive())
                    .map(|p| p.mover.pos)
                    .min_by(|a, b| a.distance_squared(pos).total_cmp(&b.distance_squared(pos)));
            return (ally.map(|p| (p, 1.5)), false);
        }
        if tick >= self.plan_due || !self.plan_holds(s) {
            self.plan = self.choose_plan(s);
            self.plan_due = tick + PLAN_EVERY;
        }
        let (mut goal, mut interact, ring) = self.work_plan(s);
        // Loot close by is picked up on the way; while holding a ring only loot inside it. A
        // revive or the gate come first.
        if !matches!(self.plan, Plan::Revive(_) | Plan::Gate)
            && let Some(p) = s
                .pickups
                .iter()
                .filter(|p| p.distance(pos) < LOOT_REACH && ring.is_none_or(|(c, r)| p.distance(c) <= r + 1.0))
                .min_by(|a, b| a.distance_squared(pos).total_cmp(&b.distance_squared(pos)))
        {
            goal = Some((*p, 0.3));
            interact = false;
        }
        (goal, interact)
    }

    /// Is the current plan still worth pursuing? (Otherwise re-plan now.)
    fn plan_holds(&self, s: &MapScene) -> bool {
        match self.plan {
            Plan::Idle => true,
            Plan::Revive(slot) => s.player(slot).is_some_and(|p| matches!(p.life, LifeState::Downed { .. })),
            Plan::Gate => s.gate_wanted(),
            Plan::Poi(i) => self.poi_wanted(s, i as usize),
            Plan::Follow(slot) => self.leader(s.w) == Some(slot),
        }
    }

    /// Is POI `i` still something for me to do? Finished sites are not; a hot anvil only while
    /// I have something to forge there; a spring only until I have used it.
    fn poi_wanted(&self, s: &MapScene, i: usize) -> bool {
        let (Some(site), Some(&state)) = (s.map.pois.get(i), s.pois.get(i)) else { return false };
        match (site.kind, state) {
            (PoiKind::Gate, _) | (_, PoiState::Done) => false,
            (PoiKind::Anvil, PoiState::Hot) => self.forge_work(s, i),
            (PoiKind::Spring, _) => !self.springs.contains(&(i as u8)) && s.me.hp < s.me.max_hp,
            _ => true,
        }
    }

    /// Would I forge anything at hot anvil `i`? An anvil grants its charges to each player who
    /// reaches it while hot, so before I get there I count on a charge; once there, only on the
    /// charges I hold.
    fn forge_work(&self, s: &MapScene, i: usize) -> bool {
        let private = &s.w.private;
        if self.forged_at == Some(i as u8) || private.wallet.charges > 0 {
            return self.forge_choice(s.me, private, s.db).is_some();
        }
        let mut hoped = private.clone();
        hoped.wallet.charges = 1;
        self.forge_choice(s.me, &hoped, s.db).is_some()
    }

    /// §8.2: revive, the gate, join a live objective, then the group policy (the leader picks
    /// the best POI; the others help at the leader's POI or stay with the leader).
    fn choose_plan(&self, s: &MapScene) -> Plan {
        let pos = s.pos();
        let dist = |p: Vec2| p.distance_squared(pos);
        // 1. A downed ally within reach.
        if let Some(p) = s
            .w
            .players
            .iter()
            .filter(|p| p.slot != self.slot && matches!(p.life, LifeState::Downed { remaining, .. } if remaining > 0.0))
            .filter(|p| p.mover.pos.distance(pos) <= REVIVE_REACH)
            .min_by(|a, b| dist(a.mover.pos).total_cmp(&dist(b.mover.pos)))
        {
            return Plan::Revive(p.slot);
        }
        // 2. The gate.
        if s.gate_wanted() {
            return Plan::Gate;
        }
        // 3. A live objective within reach with a player at it (an ally, or me: I finish what
        //    I start).
        if let Some(i) = (0..s.map.pois.len())
            .filter(|&i| s.live(i) && self.poi_wanted(s, i) && s.present(i))
            .filter(|&i| s.map.pois[i].at.distance(pos) <= JOIN_REACH)
            .min_by(|&a, &b| dist(s.map.pois[a].at).total_cmp(&dist(s.map.pois[b].at)))
        {
            return Plan::Poi(i as u8);
        }
        // 4. The group policy.
        match self.leader(s.w).filter(|l| *l != self.slot).and_then(|l| s.player(l)) {
            Some(leader) => {
                // Help at the leader's POI, else stay with the leader.
                let at = leader.mover.pos;
                (0..s.map.pois.len())
                    .filter(|&i| self.poi_wanted(s, i))
                    .filter(|&i| at.distance(s.map.pois[i].at) <= s.map.pois[i].radius + s.pad(i))
                    .min_by(|&a, &b| {
                        at.distance_squared(s.map.pois[a].at).total_cmp(&at.distance_squared(s.map.pois[b].at))
                    })
                    .map_or(Plan::Follow(leader.slot), |i| Plan::Poi(i as u8))
            }
            None => self.leader_choice(s),
        }
    }

    /// The leader's pick: the incomplete POI with the best value per second of travel,
    /// `value / (8 + travel_secs)`, travel measured over the tiles.
    fn leader_choice(&self, s: &MapScene) -> Plan {
        let Some(stage) = s.w.run.stage else { return Plan::Idle };
        let pos = s.pos();
        let field = s.tiles.map(|t| t.flood(pos));
        let speed = s.me.move_speed.max(1.0);
        let bag = s.w.private.bag.items.len() as f32;
        let short = stage.seals < stage.required;
        let forged = (0..s.map.pois.len())
            .any(|i| s.map.pois[i].kind == PoiKind::Anvil && matches!(s.pois[i], PoiState::Hot | PoiState::Done));
        let mut best: Option<(usize, f32)> = None;
        for (i, site) in s.map.pois.iter().enumerate() {
            if !self.poi_wanted(s, i) {
                continue;
            }
            let mut value = match site.kind {
                PoiKind::Anvil => (10.0 + 4.0 * bag).min(26.0),
                PoiKind::Warlord => {
                    let v = if forged || stage.time >= 240.0 { 12.0 } else { 3.0 };
                    if stage.seals + 2 >= stage.required { v * 2.0 } else { v }
                }
                PoiKind::Lair => 8.0,
                PoiKind::Shrine => 7.0,
                PoiKind::Reliquary => 6.0,
                PoiKind::Vein => 5.0,
                PoiKind::Spring if s.me.hp < s.me.max_hp * 0.5 => 14.0,
                PoiKind::Watchfire => 2.0,
                PoiKind::Spring | PoiKind::Gate => 0.0,
            };
            if value <= 0.0 {
                continue;
            }
            if site.seals > 0 && short {
                value += 6.0;
            }
            let travel = match (s.tiles, &field) {
                (Some(tiles), Some(field)) => match tiles.travel(field, site.at) {
                    Some(d) => d,
                    None => continue,
                },
                _ => pos.distance(site.at),
            };
            let mut score = value / (8.0 + travel / speed);
            // Stick with the current pick unless another is clearly better.
            if self.plan == Plan::Poi(i as u8) {
                score *= 1.2;
            }
            if best.is_none_or(|(_, b)| score > b) {
                best = Some((i, score));
            }
        }
        best.map_or(Plan::Idle, |(i, _)| Plan::Poi(i as u8))
    }

    /// Carry out the plan: the goal (point, tolerance), whether to interact, and the ring being
    /// held (loot outside it waits).
    fn work_plan(&mut self, s: &MapScene) -> (Option<(Vec2, f32)>, bool, Option<(Vec2, f32)>) {
        let pos = s.pos();
        match self.plan {
            Plan::Idle => (None, false, None),
            Plan::Revive(slot) => (s.player(slot).map(|p| (p.mover.pos, 1.5)), false, None),
            Plan::Gate => {
                let Some(site) = s.map.gate_site() else { return (None, false, None) };
                let r = site.radius;
                let open = s.w.run.stage.is_some_and(|st| st.gate == GateView::Open);
                (Some((site.at, r * 0.5)), open && site.at.distance(pos) < r * 0.8, Some((site.at, r)))
            }
            Plan::Follow(slot) => {
                let Some(leader) = s.player(slot) else { return (None, false, None) };
                let d = leader.mover.pos.distance(pos);
                let goal = if d > FOLLOW_REGROUP && s.near_count == 0 {
                    Some((leader.mover.pos, 8.0))
                } else if d > FOLLOW_NEAR {
                    Some((leader.mover.pos, FOLLOW_NEAR - 3.0))
                } else {
                    None
                };
                (goal, false, None)
            }
            Plan::Poi(i) => {
                let i = i as usize;
                let (site, state) = (&s.map.pois[i], s.pois[i]);
                let d = site.at.distance(pos);
                // Anvils hold the anvil ring (the tuning the host's anvil uses).
                let r = if site.kind == PoiKind::Anvil { s.db.game.anvil.radius } else { site.radius };
                let ring = Some((site.at, r));
                // The leader starts hold rings; a follower passing one with the leader never
                // sets off its wave.
                let leading = self.leader(s.w).is_none_or(|l| l == self.slot);
                match (work_of(s.db, site.kind), state) {
                    (Work::Hold, PoiState::Dormant) => (Some((site.at, r * 0.5)), leading && d < r * 0.8, None),
                    (Work::Hold, PoiState::Active) => (Some((site.at, r * 0.55)), false, ring),
                    (Work::Hold, PoiState::Hot) => {
                        if s.w.private.at_anvil && d <= r + 1.0 {
                            self.forged_at = Some(i as u8);
                        }
                        (Some((site.at, r * 0.5)), false, ring)
                    }
                    // Guards awake: fight them like a boss room, drifting back when pulled away.
                    (Work::Clear, PoiState::Active) if d <= r + 6.0 => (None, false, None),
                    (Work::Clear, PoiState::Active) => (Some((site.at, r)), false, None),
                    // Walk in to wake the guards.
                    (Work::Clear, _) => (Some((site.at, (r * 0.5).min(6.0))), false, None),
                    (Work::Use, _) => {
                        let drink = d < r * 0.8;
                        if drink {
                            self.springs.push(i as u8);
                        }
                        (Some((site.at, r * 0.5)), drink, None)
                    }
                    (Work::Touch, _) => (Some((site.at, r * 0.5)), false, ring),
                    _ => (None, false, None),
                }
            }
        }
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

/// A room's goal (legacy door sequences and boss arenas): the chosen door once the room is
/// cleared, my anvil, loot nearby, and the last stragglers once the spawns are spent.
fn room_goal(
    w: &WorldSnapshot,
    db: &ContentDb,
    me: &PlayerView,
    doors: &[(Vec2, DoorReward, u8)],
    pickups: &[Vec2],
    foes: &[Foe],
) -> (Option<(Vec2, f32)>, bool) {
    let pos = me.mover.pos;
    // My anvil (the one my charges come from, else the nearest that still burns).
    let anvil = w.private.anvil.and_then(|a| {
        let i = w.entities.binary_search_by_key(&a.id, |e| e.id).ok()?;
        Some((w.entities[i].pos.to_vec2(), a.state))
    });
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
    } else if let Some((a, state)) = anvil {
        match state {
            AnvilState::Dormant => {
                goal = Some((a, radius * 0.5));
                interact = a.distance(pos) < radius * 0.8;
            }
            AnvilState::Kindling => goal = Some((a, radius * 0.55)),
            AnvilState::Hot if !bag.items.is_empty() || w.private.wallet.charges > 0 => goal = Some((a, radius * 0.5)),
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
    (goal, interact)
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
    /// Biome maps only: the objective state when the party left the map.
    pub stage: Option<StageSummary>,
}

/// How a biome map ended (the phase-2 proof reads it from the bot-run report).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct StageSummary {
    pub seals: u8,
    pub required: u8,
    pub warlord: bool,
    pub objectives: u8,
    /// The gate was forced open (Unworthy).
    pub forced: bool,
}

impl StageSummary {
    fn of(ex: &crate::resources::Expedition) -> Option<Self> {
        ex.active.then_some(Self {
            seals: ex.seals,
            required: ex.required,
            warlord: ex.warlord_done,
            objectives: ex.objectives,
            forced: ex.forced,
        })
    }
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
    /// The run was stopped on a biome map with no objective progress for [`STALL_MINUTES`]
    /// (OPEN_WORLD.md §5.7; the POI and bot trace went to stderr).
    pub stalled: bool,
}

/// A biome map with no objective progress (a POI completed, a Seal, the gate or the Warlord) for
/// this many sim-minutes fails the headless run.
pub const STALL_MINUTES: f32 = 5.0;

/// What counts as objective progress on a biome map: (room, objectives, Seals, gate, Warlord).
fn stage_progress(world: &World) -> Option<(u32, u8, u8, u8, bool)> {
    let ex = world.resource::<crate::resources::Expedition>();
    if !ex.active {
        return None;
    }
    let gate = match ex.gate {
        crate::resources::GateState::Sealed => 0,
        crate::resources::GateState::Open => 1,
        crate::resources::GateState::Gathering { .. } => 2,
    };
    let serial = world.resource::<crate::resources::RunState>().room_serial;
    Some((serial, ex.objectives, ex.seals, gate, ex.warlord_done))
}

/// One line per POI of the current map (host state), for traces and stall reports.
fn poi_trace(world: &mut World) -> Vec<String> {
    let mut q =
        world.query::<(&crate::components::Poi, &crate::components::Pos, Option<&crate::components::AnvilStation>)>();
    let mut lines: Vec<(u8, String)> = q
        .iter(world)
        .map(|(poi, pos, anvil)| {
            let state = anvil.map_or(poi.state, |a| a.state.poi_state());
            let progress = anvil.map_or(poi.progress, |a| a.progress);
            let line = format!(
                "    poi {:>2} {:<9} {:<9} {:>3}% seals {} guards {}/{} at ({:.0},{:.0})",
                poi.index,
                poi.kind.name(),
                format!("{state:?}"),
                (progress * 100.0) as u32,
                poi.seals,
                poi.guards,
                poi.guards_total,
                pos.0.x,
                pos.0.y
            );
            (poi.index, line)
        })
        .collect();
    lines.sort_by_key(|(i, _)| *i);
    lines.into_iter().map(|(_, l)| l).collect()
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
    // The current room's objective state as of the last tick (biome maps only).
    let mut stage: Option<StageSummary> = None;
    // Objective progress on a biome map, and the sim time it last changed.
    let mut progress: (Option<(u32, u8, u8, u8, bool)>, f32) = (None, 0.0);
    let mut stalled = false;
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
                        stage: stage.take(),
                    });
                }
                let key = world.resource::<crate::resources::RoomLayout>().0.key.clone();
                room_start = (run.room_serial, time, run.kills, key);
            }
            stage = StageSummary::of(world.resource::<crate::resources::Expedition>());
            let now = stage_progress(world);
            if now != progress.0 {
                if trace {
                    eprintln!("    [{time:>5.1}s] objective progress (room, objectives, seals, gate, warlord) {now:?}");
                }
                progress = (now, time);
            } else if now.is_some() && time - progress.1 >= STALL_MINUTES * 60.0 && !run.is_over() {
                stalled = true;
            }
        }
        if stalled {
            let world = server.world_mut();
            let room_key = world.resource::<crate::resources::RoomLayout>().0.key.clone();
            eprintln!("STALL: no objective progress for {STALL_MINUTES} sim-minutes on {room_key}");
            for line in poi_trace(world) {
                eprintln!("{line}");
            }
            let players = crate::snapshot::player_views(world);
            for (_, brain, _) in &clients {
                let me = players.iter().find(|p| p.slot == brain.slot);
                eprintln!(
                    "    bot P{} plan {:?} at {:?} life {:?}",
                    brain.slot + 1,
                    brain.plan(),
                    me.map(|p| (p.mover.pos.x as i32, p.mover.pos.y as i32)),
                    me.map(|p| p.life)
                );
            }
            break;
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
            let anvils: Vec<(AnvilState, u32)> = world
                .query::<&crate::components::AnvilStation>()
                .iter(world)
                .map(|a| (a.state, (a.progress * 100.0) as u32))
                .collect();
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
                anvils,
                players.iter().map(|p| p.hp as i32).collect::<Vec<_>>(),
                players.iter().map(|p| (p.mover.pos.x as i32, p.mover.pos.y as i32)).collect::<Vec<_>>(),
                players
                    .iter()
                    .map(|p| p.weapon.equipped().map(|(_, part)| &part.rarity.name()[..1]).collect::<String>())
                    .collect::<Vec<_>>(),
            );
            if let Some(stage) = run.stage {
                let plans: Vec<Plan> = clients.iter().map(|(_, b, _)| b.plan()).collect();
                eprintln!(
                    "    stage {:.0}s seals {}/{} warlord {} gate {:?} objectives {} threat {} plans {plans:?}",
                    stage.time,
                    stage.seals,
                    stage.required,
                    stage.warlord,
                    stage.gate,
                    stage.objectives,
                    stage.threat_level(),
                );
                if ticks % (60 * 60) == 0 {
                    for line in poi_trace(world) {
                        eprintln!("{line}");
                    }
                }
            }
            let enc = world.resource::<crate::resources::Encounter>();
            if enc.alive <= 3 && run.stage.is_none() {
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
            stage,
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
        stalled,
    }
}

/// Bot teammates on their own thread, each connected through its transport like any other
/// client. Fills a co-op party for play-testing, attract mode and screenshots. Returns the stop
/// flag and the thread handle; bots leave the session when stopped.
///
/// Every player who is not one of these bots is a person, and in the group policy a person
/// leads: the bots follow the host's player (or its autopilot) and help at its objectives.
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
            struct Member {
                client: NetClient<Box<dyn ClientTransport>>,
                brain: BotBrain,
                latest: Option<Box<WorldSnapshot>>,
                /// The slot the host gave this bot (`None` until welcomed).
                slot: Option<u8>,
            }
            let mut party: Vec<Member> = members
                .into_iter()
                .enumerate()
                .map(|(i, (transport, loadout, mode))| Member {
                    client: NetClient::new(transport, format!("Bot {}", i + 2), loadout, content.hash),
                    brain: BotBrain::new(0, mode, seed ^ ((i as u64 + 11) * 0x9E37_79B9)),
                    latest: None,
                    slot: None,
                })
                .collect();
            let all_slots = ((1u16 << MAX_PLAYERS) - 1) as u8;
            let step = Duration::from_secs_f64(1.0 / gf_core::SIM_HZ as f64);
            let mut next = Instant::now();
            while !flag.load(Ordering::Relaxed) {
                let bots = party.iter().filter_map(|m| m.slot).fold(0u8, |mask, s| mask | 1 << s);
                for m in &mut party {
                    for ev in m.client.poll() {
                        match ev {
                            ClientEvent::Welcome { slot, .. } => {
                                m.brain.slot = slot;
                                m.slot = Some(slot);
                            }
                            ClientEvent::Snapshot(w) => m.latest = Some(w),
                            _ => {}
                        }
                    }
                    m.brain.humans = all_slots & !bots;
                    if let Some(w) = m.latest.as_deref() {
                        let (cmd, action) = m.brain.think(w, &content);
                        if let Some(a) = action {
                            m.client.queue_action(a);
                        }
                        m.client.send_command(cmd);
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
            for m in &mut party {
                m.client.leave();
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
