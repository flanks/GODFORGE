//! Points of interest on biome maps (OPEN_WORLD.md §5.3–5.4): hold rings (anvils, shrines,
//! reliquaries, veins), guarded clears (lairs, the Warlord), springs, watchfires and the Boss Gate.
//!
//! Every POI is a replicated, room-scoped entity with a [`Poi`] component (a map anvil also
//! carries its [`AnvilStation`]); `snapshot` turns them into `EntityKind::Poi` views and the
//! [`Expedition`] resource into `RunView.stage`.
//!
//! * [`poi_update`] runs each POI's lifecycle by its `expedition.pois` tuning row:
//!   - **Hold** (Shrine, Reliquary, Vein): interact inside the ring → Active; progress fills while a
//!     living player stands inside and decays while it is empty (`contested`); empty for
//!     [`HOLD_ABANDON_SECS`] in a row it goes back to Dormant (its wave stops, progress is kept).
//!     The breaker elite joins at `breaker_at`. Full → Done.
//!   - **Anvil**: the station's own state machine (`anvil::anvil_update`) is mirrored into the POI;
//!     Kindling → Hot completes it (its Seal), and its breaker joins at `breaker_at`.
//!   - **Clear** (Lair, Warlord): guards spawn idle at home when a player comes within
//!     `guards.wake`, with the HP and pack size of that player's cluster; they wake when a player
//!     comes within `guards.aggro` or hits them (POI Active); leashed home (by the horde) the POI
//!     is Dormant again; all dead → Done.
//!   - **Use** (Spring): each player heals once by interacting inside the ring (when hurt); Done
//!     once every connected player has.
//!   - **Touch** (Watchfire): stand in the ring for `channel` seconds → Done (lit).
//!
//!   Completion (§2.4): `run.depth += 1`, Ember, `PoiCompleted`, the POI's Seals, its reward by
//!   scope (present players, the party, or per claimant), and a vacuum that pulls the loot lying
//!   within `coop.vacuum_radius` to present players.
//! * [`expedition_flow`] runs the Boss Gate: Sealed → Open (enough Seals and the Warlord, or forced
//!   at `gate_force_minute`, Unworthy) → Gathering on an interact → the party (revived, spoils in
//!   hand) walks through the `Onward` door into the boss arena.

use crate::components::*;
use crate::enemies::spawn_enemy;
use crate::players::grant_pickup;
use crate::resources::*;
use crate::run::{Payout, Recipient, RewardCtx, grant_reward};
use gf_content::ContentDb;
use gf_content::schema::{BiomeDef, MapLayout, Phase, PoiActivation, PoiReward, PoiSite, PoiTuning, WeightedKey};
use gf_core::ids::EnemyId;
use gf_core::movement::Arena;
use gf_core::poi::{PoiKind, PoiState};
use gf_core::revive::LifeState;
use gf_core::rng::GfRng;
use gf_engine::bevy::ecs::system::SystemParam;
use gf_engine::prelude::*;
use gf_net::{AnvilState, DoorReward, GameEvent};

/// A Hold POI left empty this many seconds in a row stops its wave: it falls back to Dormant,
/// keeping its progress, until someone interacts again (§5.3, §5.7).
pub const HOLD_ABANDON_SECS: f32 = 30.0;

/// The breaker elite spawns this far outside the ring it attacks.
const BREAKER_OUTSIDE: f32 = 3.0;

/// A pickup vacuumed toward player `to` when a POI completed near it (§2.4).
/// `players::collect_pickups` flies it to that player wherever they stand.
#[derive(Component, Clone, Copy, Debug)]
pub struct Vacuum {
    pub to: u8,
}

/// Spawn one entity per `map.pois`, in site order (`Poi.index` = its index in `map.pois`).
pub fn spawn_pois(world: &mut World, map: &MapLayout) {
    for (i, site) in map.pois.iter().enumerate() {
        let net = world.resource_mut::<NetIds>().alloc();
        let mut e = world.spawn((Replicated(net), Pos(site.at), RoomScoped, Poi::from_site(i as u8, site)));
        if site.kind == PoiKind::Anvil {
            e.insert(AnvilStation::dormant());
        }
    }
}

/// The tuning row of POI `kind` (the shipped default when content lacks one).
pub fn poi_tuning(db: &ContentDb, kind: PoiKind) -> PoiTuning {
    db.game.expedition.poi(kind).copied().unwrap_or_else(|| {
        PoiTuning::defaults().into_iter().find(|p| p.kind == kind).expect("a default tuning row for every POI kind")
    })
}

#[inline]
fn bit(slot: u8) -> u8 {
    1 << (slot & 7)
}

/// One player as the POIs see them this tick.
#[derive(Clone, Copy, Debug)]
struct Hero {
    slot: u8,
    pos: Vec2,
    alive: bool,
    /// Pressed interact this tick.
    interact: bool,
    /// Below max HP (a spring refuses the unhurt).
    hurt: bool,
}

impl Hero {
    fn within(&self, at: Vec2, r: f32) -> bool {
        self.alive && self.pos.distance_squared(at) <= r * r
    }
}

/// Index of the living hero nearest `at` within `r`.
fn nearest(heroes: &[Hero], at: Vec2, r: f32) -> Option<usize> {
    (0..heroes.len())
        .filter(|&i| heroes[i].within(at, r))
        .min_by(|&a, &b| heroes[a].pos.distance_squared(at).total_cmp(&heroes[b].pos.distance_squared(at)))
}

/// Living players linked to `heroes[seed]` within `link` (single linkage, like the horde's
/// clusters): the size of its cluster, 1..=4.
fn cluster_size(heroes: &[Hero], seed: usize, link: f32) -> u8 {
    let mut member: Vec<bool> = heroes.iter().enumerate().map(|(i, _)| i == seed).collect();
    loop {
        let mut grew = false;
        for i in 0..heroes.len() {
            if member[i] || !heroes[i].alive {
                continue;
            }
            if (0..heroes.len()).any(|j| member[j] && heroes[j].pos.distance_squared(heroes[i].pos) <= link * link) {
                member[i] = true;
                grew = true;
            }
        }
        if !grew {
            break;
        }
    }
    member.iter().filter(|m| **m).count().clamp(1, 4) as u8
}

/// A weighted enemy pick from `pool`, limited to the build's content phase.
fn pick_enemy(db: &ContentDb, pool: &[WeightedKey], phase: Phase, rng: &mut GfRng) -> Option<EnemyId> {
    let usable: Vec<(u16, f32)> = pool
        .iter()
        .filter_map(|w| db.enemies.id(&w.key).map(|id| (id, w.weight)))
        .filter(|(id, _)| db.enemies.get(*id).phase <= phase)
        .collect();
    let weights: Vec<f32> = usable.iter().map(|(_, w)| *w).collect();
    rng.weighted_index(&weights).map(|i| EnemyId(usable[i].0))
}

/// Spawns POI enemies (guards and breakers) on the world RNG stream.
struct Spawner<'a, 'w, 's> {
    commands: &'a mut Commands<'w, 's>,
    ids: &'a mut NetIds,
    rng: &'a mut GfRng,
    db: &'a ContentDb,
    phase: Phase,
    arena: &'a Arena,
    biome: Option<&'a BiomeDef>,
    clusters: &'a ClusterTuning,
    /// The map's enemy HP growth (per biome).
    hp_mult: f32,
    cluster_link: f32,
}

impl Spawner<'_, '_, '_> {
    /// Enemy tuning for the cluster of living players around `heroes[hero]`: guards and breakers
    /// get the HP, elites and pack size of the players who woke them (§5.3).
    fn tuning_near(&self, heroes: &[Hero], hero: usize) -> Tuning {
        let n = cluster_size(heroes, hero, self.cluster_link);
        Tuning { enemy: *self.clusters.get(n), party: n }
    }

    /// One biome elite just outside the ring of radius `radius` around `at`.
    fn breaker(&mut self, tuning: &Tuning, at: Vec2, radius: f32) {
        let Some(biome) = self.biome else { return };
        let Some(def) = pick_enemy(self.db, &biome.elites, self.phase, self.rng) else { return };
        let dir = self.rng.unit_vec2();
        let p = self.arena.resolve(at + dir * (radius + BREAKER_OUTSIDE), self.db.enemy(def).radius);
        spawn_enemy(self.commands, self.ids, self.db, tuning, self.hp_mult, def, p, self.rng);
    }

    /// A Clear POI's guards, idle at home around its site: the Warlord's mini-boss, or a lair's
    /// `elites` biome elites (the first is the site's fixed guard) and a swarm pack scaled like a
    /// horde pack. Returns how many spawned.
    fn guards(&mut self, tuning: &Tuning, poi: &Poi, site: &PoiSite, at: Vec2, elites: u8) -> u8 {
        let mut defs: Vec<EnemyId> = Vec::new();
        let fixed = site.guard.filter(|g| (*g as usize) < self.db.enemies.len()).map(EnemyId);
        if poi.kind == PoiKind::Warlord {
            let boss = fixed.or_else(|| {
                let pool: Vec<u16> = self.biome?.minibosses.iter().filter_map(|k| self.db.enemies.id(k)).collect();
                self.rng.pick(&pool).copied().map(EnemyId)
            });
            defs.extend(boss);
        } else if let Some(biome) = self.biome {
            for i in 0..elites {
                let lead = if i == 0 { fixed } else { None };
                defs.extend(lead.or_else(|| pick_enemy(self.db, &biome.elites, self.phase, self.rng)));
            }
            if let Some(swarm) = pick_enemy(self.db, &biome.swarm, self.phase, self.rng) {
                let d = self.db.enemy(swarm);
                let base = self.rng.range_u32(d.pack.0 as u32, d.pack.1 as u32 + 1);
                let n = ((base as f32) * tuning.enemy.count.sqrt()).round().max(1.0) as usize;
                defs.extend(std::iter::repeat_n(swarm, n));
            }
        }
        let defs = &defs[..defs.len().min(u8::MAX as usize)];
        for (i, def) in defs.iter().enumerate() {
            // A sunflower spiral around the site: the leader in the middle, the pack around it.
            let offset = gf_core::math::from_angle(i as f32 * 2.39996) * (1.6 * (i as f32).sqrt());
            let home = self.arena.resolve(at + offset, self.db.enemy(*def).radius);
            let e = spawn_enemy(self.commands, self.ids, self.db, tuning, self.hp_mult, *def, home, self.rng);
            self.commands.entity(e).insert(Guard { home, poi: Some(poi.index), ..Default::default() });
        }
        defs.len() as u8
    }
}

/// A POI completed this tick, waiting for its rewards.
#[derive(Clone, Copy, Debug)]
struct Completed {
    index: u8,
    kind: PoiKind,
    at: Vec2,
    seals: u8,
    god: Option<u8>,
    reward: PoiReward,
    /// Player slots (bits) present at completion (`radius + coop.present_pad`).
    present: u8,
}

/// The read-only world a POI tick works from.
#[derive(SystemParam)]
pub struct PoiWorld<'w> {
    clock: Res<'w, SimClock>,
    content: Res<'w, Content>,
    settings: Res<'w, SimSettings>,
    tuning: Res<'w, Tuning>,
    clusters: Res<'w, ClusterTuning>,
    layout: Res<'w, RoomLayout>,
    arena: Res<'w, ArenaRes>,
    enc: Res<'w, Encounter>,
}

/// POI lifecycles (Hold, Clear, Use, Touch), Seals and rewards (§5.3–5.4). Runs after
/// `anvil_update`; biome maps only. It also advances the stage clock (`Expedition.time`).
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn poi_update(
    mut commands: Commands,
    w: PoiWorld,
    mut run: ResMut<RunState>,
    mut ex: ResMut<Expedition>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    mut pois: Query<(&Pos, &mut Poi, Option<&AnvilStation>)>,
    mut players: Query<(&Player, &Pos, &PlayerInput, &Life, &Stats, &mut Vitals, &mut BoonChoice, &mut Arsenal)>,
    mut guards: Query<(&Enemy, &mut Guard)>,
    pickups: Query<(Entity, &Pos, &Pickup), Without<Vacuum>>,
) {
    if !ex.active || !run.started || run.is_over() {
        return;
    }
    let Some(map) = w.layout.0.map.clone() else { return };
    let dt = w.clock.gdt();
    ex.time += dt;
    let db: &ContentDb = &w.content;
    let xt = &db.game.expedition;
    let heroes: Vec<Hero> = players
        .iter()
        .map(|(p, pos, input, life, stats, vitals, ..)| Hero {
            slot: p.slot,
            pos: pos.0,
            alive: life.state.is_alive(),
            interact: input.new.interact > 0,
            hurt: vitals.hp < stats.0.max_hp,
        })
        .collect();
    let connected = heroes.iter().fold(0u8, |m, h| m | bit(h.slot));

    // Guards: wake the idle ones a player walked up to or hit, and count the living per POI.
    let aggro = xt.guards.aggro;
    let mut guard_counts: Vec<(u8, bool)> = vec![(0, false); map.pois.len()];
    for (enemy, mut guard) in &mut guards {
        let Some(count) = guard.poi.and_then(|i| guard_counts.get_mut(i as usize)) else { continue };
        if enemy.hp <= 0.0 {
            continue;
        }
        if !guard.awake && (enemy.hit_flash > 0.0 || heroes.iter().any(|h| h.within(guard.home, aggro))) {
            guard.awake = true;
        }
        count.0 = count.0.saturating_add(1);
        count.1 |= guard.awake;
    }

    let mut done: Vec<Completed> = Vec::new();
    let mut grants: Vec<(u8, Payout)> = Vec::new();
    let biome = run.biomes.get(run.biome_idx).map(|b| db.biome(*b));
    let mut sp = Spawner {
        commands: &mut commands,
        ids: &mut ids,
        rng: &mut rngs.world,
        db,
        phase: w.settings.phase,
        arena: &w.arena.0,
        biome,
        clusters: &w.clusters,
        hp_mult: w.enc.hp_mult,
        cluster_link: xt.horde.cluster_link,
    };
    for (pos, mut poi, anvil) in &mut pois {
        let at = pos.0;
        let row = poi_tuning(db, poi.kind);
        let completed = match (anvil, row.activation) {
            (Some(station), activation) => {
                let breaker_at = match activation {
                    PoiActivation::Hold { breaker_at, .. } => breaker_at,
                    _ => None,
                };
                anvil_poi(&mut poi, station, at, db.game.anvil.radius, breaker_at, &heroes, &mut sp, &mut events.0)
            }
            (None, PoiActivation::Hold { time, decay, breaker_at, .. }) => {
                let time = (if time > 0.0 { time } else { db.game.anvil.hold_time }) * w.tuning.enemy.anvil_hold_time;
                let finished = hold(&mut poi, at, time, decay, breaker_at, dt, &heroes, &mut sp, &mut events.0);
                if poi.kind == PoiKind::Shrine && poi.state == PoiState::Done && !finished {
                    late_claim(&mut poi, at, &heroes, &mut grants);
                }
                finished
            }
            (None, PoiActivation::Clear { elites, .. }) => {
                let Some(site) = map.pois.get(poi.index as usize) else { continue };
                let counts = guard_counts.get(poi.index as usize).copied().unwrap_or_default();
                clear(&mut poi, site, at, elites, xt.guards.wake, counts, &heroes, &mut sp, &mut events.0)
            }
            (None, PoiActivation::Use) => {
                let frac = match row.reward {
                    PoiReward::Heal { frac } => frac,
                    _ => 0.0,
                };
                spring(&mut poi, at, frac, connected, &heroes, &mut grants, &mut events.0)
            }
            (None, PoiActivation::Touch { channel }) => touch(&mut poi, at, channel, dt, &heroes, &mut events.0),
            (None, PoiActivation::Gate) => false,
        };
        if completed {
            let reach = poi.radius + xt.coop.present_pad;
            let present = heroes.iter().filter(|h| h.within(at, reach)).fold(0u8, |m, h| m | bit(h.slot));
            if row.reward == PoiReward::Boon {
                // Present players take their offer now; anyone else may claim theirs later.
                poi.claimed |= present;
            }
            done.push(Completed {
                index: poi.index,
                kind: poi.kind,
                at,
                seals: poi.seals,
                god: poi.god,
                reward: row.reward,
                present,
            });
        }
    }

    // Completions: Seals, depth, Ember, rewards by scope, and the loot vacuum.
    let drops = &db.game.drops;
    let loot = w.tuning.enemy.loot;
    for c in &done {
        run.depth += 1;
        run.ember += xt.ember_per_objective * w.tuning.enemy.ember_mult;
        ex.objectives = ex.objectives.saturating_add(1);
        ex.last_progress = ex.time;
        events.0.push(GameEvent::PoiCompleted { index: c.index });
        if c.seals > 0 {
            ex.seals = ex.seals.saturating_add(c.seals);
            events.0.push(GameEvent::SealGained { seals: ex.seals, required: ex.required });
        }
        if c.kind == PoiKind::Warlord {
            ex.warlord_done = true;
        }
        let present = heroes.iter().filter(|h| c.present & bit(h.slot) != 0);
        match c.reward {
            PoiReward::Parts { extra, min_rarity, shards } => {
                for h in present {
                    grants.push((
                        h.slot,
                        Payout::Parts { count: drops.cache_parts as u32 + extra as u32, min: min_rarity },
                    ));
                    if shards > 0 {
                        grants.push((h.slot, Payout::Shards((shards as f32 * loot) as u32)));
                    }
                }
            }
            PoiReward::Shards { amount } => {
                // The party's share, wherever they stand.
                for h in &heroes {
                    grants.push((h.slot, Payout::Shards((amount as f32 * loot) as u32)));
                }
            }
            PoiReward::Boon => {
                if let Some(god) = c.god {
                    grants.extend(present.map(|h| (h.slot, Payout::Boon(god as u16))));
                }
            }
            // Forge charges are the anvil's (per claimant), a spring heals per use, a watchfire's
            // reveal is the client's fog, and the gate is `expedition_flow`'s.
            PoiReward::Forge | PoiReward::Heal { .. } | PoiReward::Reveal { .. } | PoiReward::Onward => {}
        }
        vacuum(&mut commands, c, xt.coop.vacuum_radius, &heroes, &pickups);
    }

    if grants.is_empty() {
        return;
    }
    let mut ctx = RewardCtx {
        content: db,
        phase: w.settings.phase,
        tuning: &w.tuning,
        rngs: &mut rngs,
        ids: &mut ids,
        arena: &w.arena.0,
    };
    for (p, pos, _, _, stats, mut vitals, mut choice, mut arsenal) in &mut players {
        for (_, payout) in grants.iter().filter(|(s, _)| *s == p.slot) {
            let to = Recipient {
                slot: p.slot,
                at: pos.0,
                stats: &stats.0,
                vitals: &mut vitals,
                choice: &mut choice,
                arsenal: &mut arsenal,
            };
            grant_reward(&mut ctx, &mut commands, *payout, to);
        }
    }
}

/// A map anvil: mirror its station into the POI, announce the lighting, send in the breaker, and
/// complete it when it runs Hot (its Seal; the station grants the forge charges).
#[allow(clippy::too_many_arguments)]
fn anvil_poi(
    poi: &mut Poi,
    station: &AnvilStation,
    at: Vec2,
    radius: f32,
    breaker_at: Option<f32>,
    heroes: &[Hero],
    sp: &mut Spawner,
    events: &mut Vec<GameEvent>,
) -> bool {
    let state = station.state.poi_state();
    let holder = nearest(heroes, at, radius);
    if poi.state == PoiState::Dormant && state != PoiState::Dormant {
        let slot = holder.map_or(0, |h| heroes[h].slot);
        events.push(GameEvent::PoiStarted { index: poi.index, slot });
    }
    if station.state == AnvilState::Kindling
        && !poi.breaker
        && breaker_at.is_some_and(|b| station.progress >= b)
        && let Some(h) = holder
    {
        poi.breaker = true;
        let tuning = sp.tuning_near(heroes, h);
        sp.breaker(&tuning, at, radius);
    }
    let completed =
        matches!(poi.state, PoiState::Dormant | PoiState::Active) && matches!(state, PoiState::Hot | PoiState::Done);
    poi.state = state;
    poi.progress = station.progress;
    poi.contested = station.state == AnvilState::Kindling && station.contested;
    completed
}

/// A hold ring (Shrine, Reliquary, Vein). Returns true on the tick it completes.
#[allow(clippy::too_many_arguments)]
fn hold(
    poi: &mut Poi,
    at: Vec2,
    time: f32,
    decay: f32,
    breaker_at: Option<f32>,
    dt: f32,
    heroes: &[Hero],
    sp: &mut Spawner,
    events: &mut Vec<GameEvent>,
) -> bool {
    let radius = poi.radius;
    match poi.state {
        PoiState::Dormant => {
            if let Some(h) = heroes.iter().find(|h| h.interact && h.within(at, radius)) {
                poi.state = PoiState::Active;
                poi.contested = false;
                poi.timer = 0.0;
                events.push(GameEvent::PoiStarted { index: poi.index, slot: h.slot });
            }
            false
        }
        PoiState::Active => {
            let holder = nearest(heroes, at, radius);
            if holder.is_some() {
                poi.progress += dt / time.max(1.0);
                poi.contested = false;
                poi.timer = 0.0;
            } else {
                poi.progress = (poi.progress - decay * dt).max(0.0);
                poi.contested = true;
                poi.timer += dt;
                if poi.timer >= HOLD_ABANDON_SECS {
                    poi.state = PoiState::Dormant;
                    poi.contested = false;
                    poi.timer = 0.0;
                    events.push(GameEvent::PoiReset { index: poi.index });
                    return false;
                }
            }
            if let (Some(b), Some(h)) = (breaker_at, holder)
                && !poi.breaker
                && poi.progress >= b
            {
                poi.breaker = true;
                let tuning = sp.tuning_near(heroes, h);
                sp.breaker(&tuning, at, radius);
            }
            if poi.progress >= 1.0 {
                poi.progress = 1.0;
                poi.contested = false;
                poi.state = PoiState::Done;
                return true;
            }
            false
        }
        _ => false,
    }
}

/// A Done shrine: a player who was not there when it completed interacts inside the ring once to
/// take their own offer from its god (the late claim, §2.4).
fn late_claim(poi: &mut Poi, at: Vec2, heroes: &[Hero], grants: &mut Vec<(u8, Payout)>) {
    let Some(god) = poi.god else { return };
    for h in heroes {
        if h.interact && poi.claimed & bit(h.slot) == 0 && h.within(at, poi.radius) {
            poi.claimed |= bit(h.slot);
            grants.push((h.slot, Payout::Boon(god as u16)));
        }
    }
}

/// A guarded clear (Lair, Warlord). Returns true on the tick its last guard falls.
#[allow(clippy::too_many_arguments)]
fn clear(
    poi: &mut Poi,
    site: &PoiSite,
    at: Vec2,
    elites: u8,
    wake: f32,
    (alive, awake): (u8, bool),
    heroes: &[Hero],
    sp: &mut Spawner,
    events: &mut Vec<GameEvent>,
) -> bool {
    if poi.state == PoiState::Done {
        return false;
    }
    if poi.guards_total == 0 {
        // Nobody has come near yet: the guards spawn, idle, for the first player within `wake`.
        let Some(h) = nearest(heroes, at, wake) else { return false };
        let tuning = sp.tuning_near(heroes, h);
        let n = sp.guards(&tuning, poi, site, at, elites);
        if n == 0 {
            // No guard this biome can field: the POI is free for the taking.
            poi.state = PoiState::Done;
            poi.progress = 1.0;
            return true;
        }
        poi.guards_total = n;
        poi.guards = n;
        return false;
    }
    poi.guards = alive;
    poi.progress = 1.0 - alive as f32 / poi.guards_total as f32;
    if alive == 0 {
        poi.state = PoiState::Done;
        poi.progress = 1.0;
        return true;
    }
    match (poi.state, awake) {
        (PoiState::Dormant, true) => {
            poi.state = PoiState::Active;
            let slot = nearest(heroes, at, f32::MAX).map_or(0, |h| heroes[h].slot);
            events.push(GameEvent::PoiStarted { index: poi.index, slot });
        }
        // Every guard went back to sleep (leashed home): the fight resets.
        (PoiState::Active, false) => {
            poi.state = PoiState::Dormant;
            events.push(GameEvent::PoiReset { index: poi.index });
        }
        _ => {}
    }
    false
}

/// A healing spring: each hurt player who interacts inside the ring heals once. Returns true on
/// the tick the last connected player has used it.
fn spring(
    poi: &mut Poi,
    at: Vec2,
    frac: f32,
    connected: u8,
    heroes: &[Hero],
    grants: &mut Vec<(u8, Payout)>,
    events: &mut Vec<GameEvent>,
) -> bool {
    if poi.state == PoiState::Done {
        return false;
    }
    for h in heroes {
        if h.interact && h.hurt && poi.claimed & bit(h.slot) == 0 && h.within(at, poi.radius) {
            poi.claimed |= bit(h.slot);
            grants.push((h.slot, Payout::Heal(frac)));
            events.push(GameEvent::PoiStarted { index: poi.index, slot: h.slot });
        }
    }
    let used = poi.claimed & connected;
    poi.progress = used.count_ones() as f32 / connected.count_ones().max(1) as f32;
    if connected != 0 && used == connected {
        poi.state = PoiState::Done;
        return true;
    }
    false
}

/// A watchfire: stand in the ring for `channel` seconds to light it. Returns true when lit.
fn touch(poi: &mut Poi, at: Vec2, channel: f32, dt: f32, heroes: &[Hero], events: &mut Vec<GameEvent>) -> bool {
    if poi.state == PoiState::Done {
        return false;
    }
    match nearest(heroes, at, poi.radius) {
        Some(h) => {
            if poi.state == PoiState::Dormant {
                poi.state = PoiState::Active;
                events.push(GameEvent::PoiStarted { index: poi.index, slot: heroes[h].slot });
            }
            poi.timer += dt;
            poi.progress = (poi.timer / channel.max(0.01)).min(1.0);
            if poi.timer >= channel {
                poi.state = PoiState::Done;
                poi.progress = 1.0;
                return true;
            }
        }
        None => {
            poi.state = PoiState::Dormant;
            poi.timer = 0.0;
            poi.progress = 0.0;
        }
    }
    false
}

/// Pull the loot lying within `radius` of a completed POI to the players present: owner-bound
/// parts to their owner (when present), shards to the nearest present player. Health stays put.
fn vacuum(
    commands: &mut Commands,
    c: &Completed,
    radius: f32,
    heroes: &[Hero],
    pickups: &Query<(Entity, &Pos, &Pickup), Without<Vacuum>>,
) {
    if c.present == 0 {
        return;
    }
    for (e, pos, pickup) in pickups {
        if pos.0.distance_squared(c.at) > radius * radius {
            continue;
        }
        let to = match (pickup.owner, pickup.loot) {
            (Some(owner), _) => (c.present & bit(owner) != 0).then_some(owner),
            (None, Loot::Health(_)) => None,
            (None, _) => heroes
                .iter()
                .filter(|h| c.present & bit(h.slot) != 0 && h.alive)
                .min_by(|a, b| a.pos.distance_squared(pos.0).total_cmp(&b.pos.distance_squared(pos.0)))
                .map(|h| h.slot),
        };
        if let Some(to) = to {
            commands.entity(e).insert(Vacuum { to });
        }
    }
}

/// The Boss Gate (§5.1, §5.3): Sealed → Open → Gathering → the boss arena. Runs after
/// `room_flow`; biome maps only.
///
/// * Sealed → Open once `seals ≥ required` and the Warlord is down (when the template requires
///   it), or forced at `gate_force_minute` (Unworthy).
/// * Open → Gathering when a living player interacts inside `gate.radius`: `gate.gather` seconds
///   (`gate.gather_solo` alone). It ends early once every living player stands inside the ring
///   and at least `gather_solo` seconds have passed.
/// * At zero: downed and reforging players rise at `revive_frac`, every owned pickup goes to its
///   owner (spoils carried through), the next boss's HP is set (`boss_hp_mult` × Unworthy),
///   `depth` rises, and the `Onward` door is queued for `room_transition`.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn expedition_flow(
    mut commands: Commands,
    clock: Res<SimClock>,
    content: Res<Content>,
    tuning: Res<Tuning>,
    layout: Res<RoomLayout>,
    mut run: ResMut<RunState>,
    mut ex: ResMut<Expedition>,
    mut events: ResMut<Events>,
    mut gates: Query<(&Pos, &mut Poi)>,
    mut players: Query<(
        &Player,
        &Pos,
        &PlayerInput,
        &Stats,
        &mut Life,
        &mut Vitals,
        &mut Mover,
        &mut Arsenal,
        &mut RunStats,
        &mut Kit,
    )>,
    pickups: Query<(Entity, &Pickup)>,
) {
    if !ex.active || !run.started || run.is_over() || run.pending_door.is_some() {
        return;
    }
    let Some(map) = layout.0.map.as_ref() else { return };
    let def = layout.0.expedition.as_deref();
    let gt = &content.game.expedition.gate;
    let dt = clock.gdt();
    let Some((gate_pos, mut gate)) = gates.iter_mut().find(|(_, p)| p.kind == PoiKind::Gate) else { return };
    let at = gate_pos.0;
    let inside = |p: Vec2| p.distance_squared(at) <= gt.radius * gt.radius;
    let party = players.iter().count();
    let gather_total = if party <= 1 { gt.gather_solo } else { gt.gather };

    match ex.gate {
        GateState::Sealed => {
            let requires = def.is_none_or(|d| d.gate_requires_warlord);
            let earned = ex.seals >= ex.required && (ex.warlord_done || !requires);
            let force_at = def.map_or(12.0, |d| d.gate_force_minute) * 60.0;
            if earned || ex.time >= force_at {
                ex.gate = GateState::Open;
                ex.forced = !earned;
                ex.last_progress = ex.time;
                events.0.push(GameEvent::GateOpened { forced: ex.forced });
            }
        }
        GateState::Open => {
            let opener = players
                .iter()
                .find(|(_, pos, input, _, life, ..)| life.state.is_alive() && input.new.interact > 0 && inside(pos.0))
                .map(|(p, ..)| p.slot);
            if let Some(slot) = opener {
                ex.gate = GateState::Gathering { left: gather_total };
                events.0.push(GameEvent::GateGathering { slot });
            }
        }
        GateState::Gathering { left } => {
            let left = left - dt;
            let mut living = players.iter().filter(|(.., life, _, _, _, _, _)| life.state.is_alive()).peekable();
            let all_in = living.peek().is_some() && living.all(|(_, pos, ..)| inside(pos.0));
            let early = all_in && gather_total - left >= gt.gather_solo;
            ex.gate = GateState::Gathering { left: left.max(0.0) };
            if left <= 0.0 || early {
                // Unworthy: a forced gate hardens the boss by the Seals still missing (+2 while the
                // Warlord lives).
                let warlord_alive = !ex.warlord_done && map.pois.iter().any(|p| p.kind == PoiKind::Warlord);
                let missing = ex.required.saturating_sub(ex.seals) as f32 + if warlord_alive { 2.0 } else { 0.0 };
                let unworthy =
                    if ex.forced { 1.0 + (gt.unworthy_hp_per_seal * missing).min(gt.unworthy_cap) } else { 1.0 };
                run.next_boss_hp = def.map_or(1.0, |d| d.boss_hp_mult) * unworthy;
                run.depth += 1;
                run.pending_door = Some(DoorReward::Onward);
                for (p, _, _, stats, mut life, mut vitals, mut mover, mut arsenal, mut run_stats, mut kit) in
                    &mut players
                {
                    if !life.state.is_alive() {
                        life.state = LifeState::Alive;
                        vitals.hp = stats.0.max_hp * gt.revive_frac;
                        mover.0.iframes = mover.0.iframes.max(2.0);
                        events.0.push(GameEvent::Revived { slot: p.slot, by: None });
                    }
                    life.hopeless = false;
                    // Spoils carried through: everything that is mine and still on the ground.
                    for (e, pickup) in &pickups {
                        if pickup.owner != Some(p.slot) {
                            continue;
                        }
                        let kind = grant_pickup(
                            &content,
                            &tuning,
                            pickup.loot,
                            &stats.0,
                            &mut vitals,
                            &mut arsenal,
                            &mut run_stats,
                            &mut kit,
                        );
                        events.0.push(GameEvent::Pickup { slot: p.slot, kind });
                        commands.entity(e).despawn();
                    }
                }
            }
        }
    }

    // The gate's POI shows the stage: Seals toward the requirement, then the gathering.
    gate.state = match ex.gate {
        GateState::Sealed => PoiState::Sealed,
        GateState::Open => PoiState::Open,
        GateState::Gathering { .. } => PoiState::Gathering,
    };
    gate.progress = match ex.gate {
        GateState::Sealed => (ex.seals as f32 / ex.required.max(1) as f32).min(1.0),
        GateState::Open => 1.0,
        GateState::Gathering { left } => (1.0 - left / gather_total.max(0.01)).clamp(0.0, 1.0),
    };
}
