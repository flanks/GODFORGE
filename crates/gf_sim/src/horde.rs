//! Horde director v2 for biome maps (OPEN_WORLD.md §5.5–5.6): player clusters and the census,
//! the threat clock, packs spawned on a ring just outside every player's view, hold waves,
//! surges and Gate Frenzy, sleeping camps and guards, and the far cull with refund.
//!
//! State lives in the [`crate::resources::Expedition`] resource (clusters, accumulators, camps,
//! surge) and on enemies ([`crate::components::Roaming`], [`crate::components::Guard`],
//! [`crate::components::Born`]). The systems run only on Expedition maps; the legacy director
//! (and its stress mode) keeps rooms.
//!
//! * **Clusters.** Living players within `horde.cluster_link` of each other (single linkage) form a
//!   cluster, identified by its lowest slot. Each cluster gets its own spawn accumulator, density
//!   target and enemy tuning ([`crate::resources::ClusterTuning`]), so a split party faces one
//!   horde per group, each scaled to the group's size.
//! * **Threat clock.** `T = threat_start_minute + stage minutes + heat_per_objective × objectives`
//!   samples the template's `threat` rows (linear between rows, the last slope continuing past the
//!   end) for density, rate, elite chance and HP.
//! * **Spawn points** land on a rectangle ring just outside the view footprint of a random cluster
//!   member, outside every player's footprint, clear of every player, on walkable land and
//!   reachable along the member's flow field without a long detour (never across a chasm).
//!
//! Everything here is host-only and single-threaded. Spawn rolls use `rngs.director`, camps
//! `rngs.world`, and no trigonometry is used (literal constants and dot-product tests instead).

use crate::components::*;
use crate::director::{StressMode, pick_weighted};
use crate::enemies::spawn_enemy;
use crate::resources::*;
use gf_content::schema::{CampSite, PoiActivation, ThreatKey};
use gf_core::ids::EnemyId;
use gf_core::poi::PoiState;
use gf_core::rng::GfRng;
use gf_engine::bevy::ecs::system::SystemParam;
use gf_engine::prelude::*;
use gf_net::quant::QPos;
use gf_net::{GameEvent, RunPhase};

/// sin 55°: the camera pitch the view footprint assumes (a literal, no trig in the sim).
const SIN_PITCH: f32 = 0.819_152;
/// Clusters are re-formed every this many ticks (and at once when a player goes down or returns).
const CLUSTER_EVERY: u32 = 15;
/// Spawn-point tries per pack; a pack that finds no point waits for the next tick.
const SPAWN_TRIES: u32 = 12;
/// Spawn weight a cluster may bank, and owe after a large pack.
const ACCUM_MAX: f32 = 8.0;
const ACCUM_MIN: f32 = -12.0;
/// Spawn weight of a swarm enemy and of an elite (the legacy director's costs).
const SWARM_COST: f32 = 1.0;
const ELITE_COST: f32 = 6.0;
/// Spacing (u) of pack members and of camp members around their spawn point.
const PACK_SPACING: f32 = 1.0;
const CAMP_SPACING: f32 = 1.4;
/// A camp member this close to home counts as settled (its camp may fall asleep).
const HOME_SETTLED: f32 = 6.0;
/// … and so does one at least this far from every player (off screen).
const OFF_SCREEN: f32 = 45.0;
/// The threat row a template without `threat` rows plays at (§2.5, Cinder minute 0).
const FALLBACK_THREAT: ThreatKey =
    ThreatKey { minute: 0.0, density: 30.0, rate: 3.0, elite_chance: 0.01, hp_mult: 1.0 };

/// A hex lattice (unit spacing): the centre, then rings of 6 and 12. Packs and camps stand on it.
const HEX: [Vec2; 19] = [
    Vec2::new(0.0, 0.0),
    Vec2::new(1.0, 0.0),
    Vec2::new(0.5, 0.866_025),
    Vec2::new(-0.5, 0.866_025),
    Vec2::new(-1.0, 0.0),
    Vec2::new(-0.5, -0.866_025),
    Vec2::new(0.5, -0.866_025),
    Vec2::new(2.0, 0.0),
    Vec2::new(1.5, 0.866_025),
    Vec2::new(1.0, 1.732_051),
    Vec2::new(0.0, 1.732_051),
    Vec2::new(-1.0, 1.732_051),
    Vec2::new(-1.5, 0.866_025),
    Vec2::new(-2.0, 0.0),
    Vec2::new(-1.5, -0.866_025),
    Vec2::new(-1.0, -1.732_051),
    Vec2::new(0.0, -1.732_051),
    Vec2::new(1.0, -1.732_051),
    Vec2::new(1.5, -0.866_025),
];

/// Offset of member `i` of a group spawned at one point (a hex spiral, then further rows).
fn formation(i: usize, spacing: f32) -> Vec2 {
    (HEX[i % HEX.len()] + Vec2::new(0.0, 4.5 * (i / HEX.len()) as f32)) * spacing
}

/// Player slot as a cluster bit.
#[inline]
fn bit(slot: u8) -> u8 {
    1 << (slot % 4)
}

/// cos of an angle in degrees without trig (Bhaskara I; |error| < 0.002). Surge arc test only.
fn cos_deg(deg: f32) -> f32 {
    let d = deg.abs() % 360.0;
    let d = if d > 180.0 { 360.0 - d } else { d };
    if d > 90.0 {
        return -cos_deg(180.0 - d);
    }
    (32_400.0 - 4.0 * d * d) / (32_400.0 + d * d)
}

/// The threat clock at minute `t`: the interpolated row, its level (segment index) and the
/// fraction toward the next level. Past the last row the last segment's slope continues, one level
/// per segment length. Rows are validated: minutes strictly increasing from 0.
pub fn sample_threat(rows: &[ThreatKey], t: f32) -> (ThreatKey, u8, f32) {
    let lerp = |a: &ThreatKey, b: &ThreatKey, f: f32| ThreatKey {
        minute: a.minute + (b.minute - a.minute) * f,
        density: (a.density + (b.density - a.density) * f).max(0.0),
        rate: (a.rate + (b.rate - a.rate) * f).max(0.0),
        elite_chance: (a.elite_chance + (b.elite_chance - a.elite_chance) * f).clamp(0.0, 1.0),
        hp_mult: (a.hp_mult + (b.hp_mult - a.hp_mult) * f).max(0.1),
    };
    let Some(first) = rows.first() else { return (FALLBACK_THREAT, 0, 0.0) };
    if rows.len() == 1 || t <= first.minute {
        return (*first, 0, 0.0);
    }
    for (i, pair) in rows.windows(2).enumerate() {
        if t < pair[1].minute {
            let f = (t - pair[0].minute) / (pair[1].minute - pair[0].minute).max(1e-3);
            return (lerp(&pair[0], &pair[1], f), i.min(255) as u8, f);
        }
    }
    let (a, b) = (&rows[rows.len() - 2], &rows[rows.len() - 1]);
    let past = (t - b.minute) / (b.minute - a.minute).max(1e-3);
    let whole = past.floor();
    let level = (rows.len() - 1) as f32 + whole;
    (lerp(a, b, 1.0 + past), level.min(255.0) as u8, past - whole)
}

/// The resources every horde system reads.
#[derive(SystemParam)]
pub struct HordeCtx<'w> {
    clock: Res<'w, SimClock>,
    content: Res<'w, Content>,
    settings: Res<'w, SimSettings>,
    tuning: Res<'w, Tuning>,
    clusters: Res<'w, ClusterTuning>,
    run: Res<'w, RunState>,
    arena: Res<'w, ArenaRes>,
    layout: Res<'w, RoomLayout>,
    flow: Res<'w, Flow>,
}

impl HordeCtx<'_> {
    /// A run is on and the current room is a biome map with a live stage.
    fn live(&self, ex: &Expedition) -> bool {
        ex.active && self.layout.0.map.is_some() && self.run.started && !self.run.is_over()
    }

    /// The threat row, level and fraction at the stage's current minute.
    fn threat(&self, ex: &Expedition) -> (ThreatKey, u8, f32) {
        let horde = &self.content.game.expedition.horde;
        let (rows, start) =
            self.layout.0.expedition.as_deref().map_or((&[][..], 0.0), |x| (&x.threat[..], x.threat_start_minute));
        let t = start + ex.time / 60.0 + horde.heat_per_objective * ex.objectives as f32;
        sample_threat(rows, t)
    }

    /// HP multiplier for enemies spawned at threat row `key` (the biome growth still applies).
    fn threat_hp(&self, key: &ThreatKey) -> f32 {
        key.hp_mult * (1.0 + self.content.game.run.hp_growth_per_biome * self.run.biome_idx as f32)
    }

    /// Half extents of one player's estimated view footprint on the ground (§5.5).
    fn footprint(&self) -> Vec2 {
        let horde = &self.content.game.expedition.horde;
        let party = self.tuning.party.clamp(1, 4) as usize;
        let vh = self.content.game.camera.view_height[party - 1] + horde.view_pad;
        Vec2::new(vh * horde.view_aspect * 0.5, vh / (2.0 * SIN_PITCH))
    }

    /// The flow fields belong to the current map.
    fn flow_ready(&self) -> bool {
        self.layout.0.map.as_ref().is_some_and(|m| self.flow.matches(&m.tiles))
    }
}

/// Living players as `(slot, position)`, by slot.
fn living_players(players: &Query<(&Player, &Pos, &Life)>) -> Vec<(u8, Vec2)> {
    let mut out: Vec<(u8, Vec2)> =
        players.iter().filter(|(_, _, life)| life.state.is_alive()).map(|(p, pos, _)| (p.slot, pos.0)).collect();
    out.sort_by_key(|(slot, _)| *slot);
    out
}

/// Index into `living` of the player nearest `p` (ties to the lower slot) and the squared distance.
fn nearest(living: &[(u8, Vec2)], p: Vec2) -> Option<(usize, f32)> {
    let mut best: Option<(usize, f32)> = None;
    for (i, (_, q)) in living.iter().enumerate() {
        let d = q.distance_squared(p);
        if best.is_none_or(|(_, b)| d < b) {
            best = Some((i, d));
        }
    }
    best
}

/// Single-linkage clusters of living players (sorted by slot), in id order.
fn form_clusters(living: &[(u8, Vec2)], link: f32) -> Vec<Cluster> {
    let n = living.len();
    // Each player's group label is the lowest index in its group (at most 4 players).
    let mut group: Vec<usize> = (0..n).collect();
    for i in 0..n {
        for j in i + 1..n {
            if living[i].1.distance_squared(living[j].1) <= link * link && group[i] != group[j] {
                let (keep, drop) = (group[i].min(group[j]), group[i].max(group[j]));
                group.iter_mut().filter(|g| **g == drop).for_each(|g| *g = keep);
            }
        }
    }
    (0..n)
        .filter_map(|g| {
            let idx: Vec<usize> = (0..n).filter(|&i| group[i] == g).collect();
            (!idx.is_empty()).then(|| Cluster {
                members: idx.iter().fold(0, |m, &i| m | bit(living[i].0)),
                n: idx.len() as u8,
                centroid: idx.iter().fold(Vec2::ZERO, |s, &i| s + living[i].1) / idx.len() as f32,
                count: 0,
            })
        })
        .collect()
}

/// A uniform point on the rectangle ring between `inner` and `outer` half extents around `c`.
fn rect_ring_point(c: Vec2, inner: Vec2, outer: Vec2, rng: &mut GfRng) -> Vec2 {
    let (band_x, band_y) = (outer.x - inner.x, outer.y - inner.y);
    // Top and bottom strips span the outer width; left and right strips the inner height.
    let cap = 2.0 * outer.x * band_y;
    let side = band_x * 2.0 * inner.y;
    let r = rng.f32() * 2.0 * (cap + side);
    let (u, v) = (rng.f32(), rng.f32());
    let off = if r < cap {
        Vec2::new(-outer.x + 2.0 * outer.x * u, inner.y + band_y * v)
    } else if r < 2.0 * cap {
        Vec2::new(-outer.x + 2.0 * outer.x * u, -inner.y - band_y * v)
    } else if r < 2.0 * cap + side {
        Vec2::new(-inner.x - band_x * u, -inner.y + 2.0 * inner.y * v)
    } else {
        Vec2::new(inner.x + band_x * u, -inner.y + 2.0 * inner.y * v)
    };
    c + off
}

/// A uniform point on the ring `min..max` around `c` (rejection in the square, no trig).
fn disc_ring_point(c: Vec2, (min, max): (f32, f32), rng: &mut GfRng) -> Option<Vec2> {
    for _ in 0..8 {
        let d = Vec2::new(rng.range_f32(-max, max), rng.range_f32(-max, max));
        let l = d.length_squared();
        if l >= min * min && l <= max * max {
            return Some(c + d);
        }
    }
    None
}

/// Where a pack is aimed and the rules it must pass (§5.5 step 5).
struct SpawnAim {
    /// The cluster member it spawns around: slot and position.
    slot: u8,
    at: Vec2,
    /// Half extents of one view footprint.
    half: Vec2,
    radius: f32,
    /// A hold wave's POI: spawn on the event ring around it instead.
    ring: Option<Vec2>,
    /// An active surge's direction: rect-ring points stay within its arc.
    surge: Option<Vec2>,
}

/// A spawn point for a pack, or `None` after every try failed (the pack waits for the next tick).
fn spawn_point(ctx: &HordeCtx, aim: &SpawnAim, living: &[(u8, Vec2)], rng: &mut GfRng) -> Option<Vec2> {
    let horde = &ctx.content.game.expedition.horde;
    let inner = aim.half + Vec2::splat(horde.ring_margin.0);
    let outer = aim.half + Vec2::splat(horde.ring_margin.1.max(horde.ring_margin.0 + 0.5));
    let min_dot = cos_deg(horde.surge.arc_deg * 0.5);
    let bound = ctx.arena.0.half_extents - Vec2::splat(aim.radius + 0.5);
    let flow = ctx.flow_ready().then_some(&*ctx.flow);
    let has_field = flow.is_some_and(|f| f.src[aim.slot as usize % 4].is_some());
    let clear2 = horde.spawn_clear * horde.spawn_clear;
    // An event-ring spawn falls back to the rect ring when the ring around the POI is all on screen.
    let tries = if aim.ring.is_some() { SPAWN_TRIES * 2 } else { SPAWN_TRIES };
    for attempt in 0..tries {
        let p = match aim.ring {
            Some(c) if attempt < SPAWN_TRIES => match disc_ring_point(c, horde.event_ring, rng) {
                Some(p) => p,
                None => continue,
            },
            _ => {
                let p = rect_ring_point(aim.at, inner, outer, rng);
                if let Some(dir) = aim.surge
                    && (p - aim.at).normalize_or_zero().dot(dir) < min_dot
                {
                    continue;
                }
                p
            }
        };
        if p.x.abs() > bound.x || p.y.abs() > bound.y {
            continue;
        }
        if flow.is_some_and(|f| !f.passable_at(p)) || !ctx.arena.0.walkable(p, aim.radius) {
            continue;
        }
        let seen = living.iter().any(|(_, q)| {
            let d = p - *q;
            (d.x.abs() <= aim.half.x + 1.0 && d.y.abs() <= aim.half.y + 1.0) || d.length_squared() < clear2
        });
        if seen {
            continue;
        }
        // Reachable from the member without a long detour: never across a chasm or a long wall.
        if has_field && let Some(f) = flow {
            match f.distance(aim.slot, p) {
                Some(d) if d <= horde.flow_detour * p.distance(aim.at) + 8.0 => {}
                _ => continue,
            }
        }
        return Some(p);
    }
    None
}

/// The pressure a POI puts on a cluster (§2.3, §5.5): a Hold POI being held (with its event ring),
/// else an awake Clear POI's fight.
#[derive(Clone, Copy)]
struct Wave {
    mult: f32,
    ring: Option<Vec2>,
}

/// Per cluster id: the rate multiplier and event ring of the POIs its players are working.
fn poi_waves(
    ctx: &HordeCtx,
    clusters: &[Cluster],
    living: &[(u8, Vec2)],
    pois: &Query<(&Pos, &Poi, Option<&AnvilStation>)>,
) -> [Wave; 4] {
    let mut hold: [Option<(f32, Vec2)>; 4] = [None; 4];
    let mut fight: [Option<f32>; 4] = [None; 4];
    let mut sites: Vec<(u8, Vec2, &Poi, Option<&AnvilStation>)> =
        pois.iter().map(|(pos, poi, anvil)| (poi.index, pos.0, poi, anvil)).collect();
    sites.sort_by_key(|s| s.0);
    for (_, at, poi, anvil) in sites {
        // A map anvil's station is the source of truth for its lifecycle.
        let (state, contested) = match anvil {
            Some(a) => (a.state.poi_state(), a.contested),
            None => (poi.state, poi.contested),
        };
        if state != PoiState::Active {
            continue;
        }
        let Some(row) = ctx.content.game.expedition.poi(poi.kind) else { continue };
        let reach = poi.radius + 1.0;
        for c in clusters {
            let working =
                living.iter().any(|(s, p)| c.members & bit(*s) != 0 && p.distance_squared(at) <= reach * reach);
            if !working {
                continue;
            }
            let id = c.id() as usize;
            match row.activation {
                PoiActivation::Hold { wave, .. } if !contested => {
                    if hold[id].is_none_or(|(w, _)| wave > w) {
                        hold[id] = Some((wave, at));
                    }
                }
                PoiActivation::Clear { wave, .. } => fight[id] = Some(fight[id].map_or(wave, |w| w.min(wave))),
                _ => {}
            }
        }
    }
    std::array::from_fn(|i| match (hold[i], fight[i]) {
        (Some((mult, at)), _) => Wave { mult, ring: Some(at) },
        (None, Some(mult)) => Wave { mult, ring: None },
        (None, None) => Wave { mult: 1.0, ring: None },
    })
}

/// What `run_horde` remembers between ticks.
#[derive(Default)]
pub struct StageWatch {
    /// `room_serial` of the map being watched.
    serial: u32,
    /// `Expedition.time` as this system last left it (`None` on a new map).
    time_seen: Option<f32>,
    /// Another system advances `Expedition.time`: stop advancing it here.
    time_elsewhere: bool,
}

/// Advance the stage clock unless another system does. `Expedition.time` belongs to the stage
/// flow; until that system advances it, the horde keeps it running so the threat clock and the
/// forced gate still move. The first time it sees the clock moved by someone else it stops for good.
fn advance_stage_clock(watch: &mut StageWatch, ex: &mut Expedition, dt: f32) {
    if watch.time_elsewhere {
        return;
    }
    if watch.time_seen.is_some_and(|t| t.to_bits() != ex.time.to_bits()) {
        watch.time_elsewhere = true;
        return;
    }
    ex.time += dt;
    watch.time_seen = Some(ex.time);
}

/// Clusters, census, threat and spawning (§5.5 steps 1–5).
#[allow(clippy::too_many_arguments)]
pub fn run_horde(
    mut commands: Commands,
    ctx: HordeCtx,
    stress: Res<StressMode>,
    mut ex: ResMut<Expedition>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    mut watch: Local<StageWatch>,
    players: Query<(&Player, &Pos, &Life)>,
    enemies: Query<(&Pos, &Enemy)>,
    pois: Query<(&Pos, &Poi, Option<&AnvilStation>)>,
) {
    if !ctx.live(&ex) {
        return;
    }
    let horde = &ctx.content.game.expedition.horde;
    let dt = ctx.clock.gdt();
    let arrived = watch.serial != ctx.run.room_serial;
    if arrived {
        watch.serial = ctx.run.room_serial;
        watch.time_seen = None;
    }
    advance_stage_clock(&mut watch, &mut ex, dt);

    // 3. The threat clock (sampled first: the HUD shows it even while nothing spawns).
    let (key, level, frac) = ctx.threat(&ex);
    if level > ex.threat_level && !arrived {
        events.0.push(GameEvent::ThreatRose { level });
    }
    ex.threat_level = level;
    ex.threat_frac = frac;

    // 1. Clusters: every 15 ticks, and at once when someone goes down or comes back.
    let living = living_players(&players);
    let alive_mask = living.iter().fold(0u8, |m, (s, _)| m | bit(*s));
    let formed = ex.clusters.iter().fold(0u8, |m, c| m | c.members);
    if alive_mask != formed || ctx.clock.tick.is_multiple_of(CLUSTER_EVERY) {
        ex.clusters = form_clusters(&living, horde.cluster_link);
        for id in 0..4u8 {
            if !ex.clusters.iter().any(|c| c.id() == id) {
                ex.accum[id as usize] = 0.0;
            }
        }
    }

    // 2. Census: each living enemy counts toward the cluster of its nearest living player.
    let mut alive = 0u32;
    let mut near = [0u32; 4];
    let bubble2 = horde.census_bubble * horde.census_bubble;
    for (pos, e) in &enemies {
        if e.hp <= 0.0 {
            continue;
        }
        alive += 1;
        if let Some((i, d2)) = nearest(&living, pos.0)
            && d2 <= bubble2
        {
            near[living[i].0 as usize % 4] += 1;
        }
    }
    for c in ex.clusters.iter_mut() {
        c.count = (0..4u8).filter(|s| c.members & bit(*s) != 0).map(|s| near[s as usize]).sum();
    }

    // The stress rig holds its own count; nothing spawns between rooms or once the map is won.
    if stress.0.is_some() || ctx.run.phase != RunPhase::Combat || ctx.run.transition > 0.0 {
        return;
    }
    let Some(biome) = ctx.run.biomes.get(ctx.run.biome_idx).map(|b| ctx.content.biome(*b)) else { return };

    // 4. Per cluster: density target, spawn rate (surge, Gate Frenzy, POI waves) and packs.
    let clusters = ex.clusters.clone();
    let waves = poi_waves(&ctx, &clusters, &living, &pois);
    let frenzy = matches!(ex.gate, GateState::Open | GateState::Gathering { .. });
    let surge = ex.surge.filter(|s| s.warn <= 0.0 && s.left > 0.0).map(|s| s.dir.normalize_or_zero());
    let density = key.density.min(horde.global_max_alive as f32);
    let hp = ctx.threat_hp(&key);
    let half = ctx.footprint();
    for c in &clusters {
        let ct = *ctx.clusters.get(c.n);
        let id = c.id() as usize;
        let wave = waves[id];
        let target = density * ct.count + if frenzy { horde.frenzy_density } else { 0.0 };
        let rate = key.rate
            * ct.count
            * ct.spawn_rate
            * horde.rate_mult
            * if surge.is_some() { horde.surge.rate_mult } else { 1.0 }
            * if frenzy { horde.frenzy_rate } else { 1.0 }
            * wave.mult;
        ex.accum[id] = (ex.accum[id] + rate * dt).min(ACCUM_MAX);
        let members: Vec<(u8, Vec2)> = living.iter().filter(|(s, _)| c.members & bit(*s) != 0).copied().collect();
        let mut count = c.count;
        while ex.accum[id] >= 1.0 && (count as f32) < target && alive < horde.global_max_alive {
            let elite = !biome.elites.is_empty() && rngs.director.chance(key.elite_chance + ct.elite_chance_add);
            let pool = if elite { &biome.elites } else { &biome.swarm };
            let Some(def) = pick_weighted(pool, &ctx.content, ctx.settings.phase, &mut rngs.director) else { break };
            let d = ctx.content.enemy(def);
            let size = rngs.director.range_u32(d.pack.0 as u32, d.pack.1 as u32 + 1);
            let n = if elite { 1 } else { ((size as f32) * ct.count.sqrt()).round().max(1.0) as u32 }
                .min(horde.global_max_alive - alive);
            let Some(&(slot, at)) = rngs.director.pick(&members) else { break };
            let ring = wave.ring.filter(|_| rngs.director.chance(horde.event_share));
            let radius = d.radius * d.scale.max(0.5);
            let aim = SpawnAim { slot, at, half, radius, ring, surge };
            let Some(p) = spawn_point(&ctx, &aim, &living, &mut rngs.director) else { break };
            let cost = if elite { ELITE_COST } else { SWARM_COST };
            let tuning = Tuning { enemy: ct, party: c.n };
            for i in 0..n as usize {
                let q = ctx.arena.0.resolve(p + formation(i, PACK_SPACING), radius);
                let e = spawn_enemy(&mut commands, &mut ids, &ctx.content, &tuning, hp, def, q, &mut rngs.director);
                commands.entity(e).insert((Roaming { cluster: id as u8, far: 0.0, cost }, Born(ctx.clock.tick)));
            }
            alive += n;
            count += n;
            ex.accum[id] -= cost * n as f32;
        }
        ex.accum[id] = ex.accum[id].max(ACCUM_MIN);
    }
}

/// Camp members in spawn order: the leader (if the camp has one) always survives a sleep, then
/// the pack. `left` members in all.
fn camp_roster(site: &CampSite, left: u8) -> impl Iterator<Item = u16> {
    let lead = site.elite.filter(|_| left > 0);
    let pack = left.saturating_sub(lead.is_some() as u8) as usize;
    lead.into_iter().chain(std::iter::repeat_n(site.enemy, pack))
}

/// Camps and guards (§5.3, §5.5 step 6):
///
/// * An idle guard wakes (with its whole lair, court or camp) when a living player comes within
///   `guards.aggro` or it takes damage. Idle guards regenerate `regen` of max HP per second.
/// * An awake guard goes home (idle) once every living player has been beyond `guards.leash` from
///   its home for `reset_after` seconds. Anti-hide: untouched for `hunt_after` seconds with a player
///   within `hunt_radius`, it hunts (chases instead of keeping its distance) until hit again.
/// * A sleeping camp wakes when a living player comes within `guards.wake` (if the global cap
///   allows): its members spawn as idle guards. An awake camp whose members are all idle and
///   settled falls asleep (despawns, keeping its head count) with every player beyond
///   `guards.sleep`. A camp with no members left is cleared: it drops its shard pile for good.
///
/// Lair and Warlord guards are spawned by `poi.rs`; this system runs their wake, leash and hunt.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn guards(
    mut commands: Commands,
    ctx: HordeCtx,
    mut ex: ResMut<Expedition>,
    mut ids: ResMut<NetIds>,
    mut rngs: ResMut<Rngs>,
    mut events: ResMut<Events>,
    players: Query<(&Player, &Pos, &Life)>,
    others: Query<&Enemy, Without<Guard>>,
    mut guards: Query<(Entity, &Pos, &mut Enemy, &mut Guard)>,
) {
    if !ctx.live(&ex) {
        return;
    }
    let Some(map) = ctx.layout.0.map.clone() else { return };
    let gt = &ctx.content.game.expedition.guards;
    let dt = ctx.clock.gdt();
    let living = living_players(&players);
    let near = |p: Vec2, r: f32| living.iter().any(|(_, q)| q.distance_squared(p) <= r * r);

    // Wake, leash, regenerate and hunt.
    let mut woken: Vec<(Entity, Option<u8>, Option<u16>)> = Vec::new();
    for (entity, pos, mut enemy, mut g) in &mut guards {
        if enemy.hp <= 0.0 {
            continue;
        }
        let hurt = enemy.hit_flash > 0.0;
        if !g.awake {
            enemy.hp = (enemy.hp + gt.regen * enemy.max_hp * dt).min(enemy.max_hp);
            if hurt || near(pos.0, gt.aggro) {
                woken.push((entity, g.poi, g.camp));
            }
            continue;
        }
        if near(g.home, gt.leash) {
            g.away = 0.0;
        } else {
            g.away += dt;
        }
        if g.away >= gt.reset_after {
            *g = Guard { home: g.home, poi: g.poi, camp: g.camp, ..Default::default() };
            continue;
        }
        if hurt {
            g.untouched = 0.0;
            g.hunt = false;
        } else if near(pos.0, gt.hunt_radius) {
            g.untouched += dt;
            g.hunt |= g.untouched >= gt.hunt_after;
        }
    }
    if !woken.is_empty() {
        for (entity, _, _, mut g) in &mut guards {
            let group = woken.iter().any(|(e, poi, camp)| {
                *e == entity || (poi.is_some() && *poi == g.poi) || (camp.is_some() && *camp == g.camp)
            });
            if group && !g.awake {
                g.awake = true;
                g.away = 0.0;
                g.untouched = 0.0;
            }
        }
    }

    // Camps.
    if map.camps.is_empty() {
        return;
    }
    if ex.camps.len() != map.camps.len() {
        ex.camps = map
            .camps
            .iter()
            .map(|c| CampRuntime { state: CampState::Asleep, left: c.count.saturating_add(c.elite.is_some() as u8) })
            .collect();
    }
    // Living members per camp, and whether all of them are idle and settled.
    let mut members: Vec<(Vec<Entity>, bool)> = vec![(Vec::new(), true); map.camps.len()];
    let mut alive = others.iter().filter(|e| e.hp > 0.0).count() as u32;
    for (entity, pos, enemy, g) in guards.iter() {
        if enemy.hp <= 0.0 {
            continue;
        }
        alive += 1;
        if let Some(m) = g.camp.and_then(|i| members.get_mut(i as usize)) {
            let home = pos.0.distance_squared(g.home) <= HOME_SETTLED * HOME_SETTLED;
            m.0.push(entity);
            m.1 &= !g.awake && (home || !near(pos.0, OFF_SCREEN));
        }
    }
    let everyone: Vec<Vec2> = players.iter().map(|(_, p, _)| p.0).collect();
    let horde = &ctx.content.game.expedition.horde;
    for (i, site) in map.camps.iter().enumerate() {
        let camp = ex.camps[i];
        match camp.state {
            CampState::Cleared => {}
            CampState::Awake => {
                let (list, settled) = &members[i];
                if list.is_empty() {
                    ex.camps[i] = CampRuntime { state: CampState::Cleared, left: 0 };
                    let shards = (site.shards as f32 * ctx.tuning.enemy.loot).round().max(1.0) as u32;
                    commands.spawn((
                        Replicated(ids.alloc()),
                        Pos(ctx.arena.0.resolve(site.at, 0.3)),
                        RoomScoped,
                        Pickup {
                            loot: Loot::Shards(shards),
                            owner: None,
                            life: ctx.content.game.drops.pickup_lifetime,
                        },
                    ));
                    events.0.push(GameEvent::CampCleared { at: QPos::from_vec2(site.at) });
                } else if *settled && everyone.iter().all(|q| q.distance_squared(site.at) > gt.sleep * gt.sleep) {
                    for e in list {
                        commands.entity(*e).despawn();
                    }
                    alive = alive.saturating_sub(list.len() as u32);
                    ex.camps[i] = CampRuntime { state: CampState::Asleep, left: list.len().min(255) as u8 };
                }
            }
            CampState::Asleep => {
                let Some(&(slot, _)) = living.iter().find(|(_, q)| q.distance_squared(site.at) <= gt.wake * gt.wake)
                else {
                    continue;
                };
                if camp.left == 0 {
                    ex.camps[i] = CampRuntime { state: CampState::Cleared, left: 0 };
                    continue;
                }
                if alive + camp.left as u32 > horde.global_max_alive {
                    continue;
                }
                // Scaled to the waking player's cluster, at the current threat.
                let n = ex.clusters.iter().find(|c| c.members & bit(slot) != 0).map_or(1, |c| c.n);
                let tuning = Tuning { enemy: *ctx.clusters.get(n), party: n };
                let hp = ctx.threat_hp(&ctx.threat(&ex).0);
                for (k, def) in camp_roster(site, camp.left).enumerate() {
                    let def = EnemyId(def);
                    let d = ctx.content.enemy(def);
                    let p = ctx.arena.0.resolve(site.at + formation(k, CAMP_SPACING), d.radius * d.scale.max(0.5));
                    let e = spawn_enemy(&mut commands, &mut ids, &ctx.content, &tuning, hp, def, p, &mut rngs.world);
                    let guard = Guard { home: p, poi: None, camp: Some(i as u16), ..Default::default() };
                    commands.entity(e).insert((guard, Born(ctx.clock.tick)));
                }
                alive += camp.left as u32;
                ex.camps[i].state = CampState::Awake;
            }
        }
    }
}

/// Despawn roaming enemies left far behind and refund their cost to their cluster (§5.6): a
/// straggler whose nearest living player has been beyond `cull_distance` for `cull_after` seconds,
/// or is beyond `hard_cull` at all. Silent (no drops, no kill credit). Guards, bosses and anything
/// the director did not spawn are never culled. Nothing is culled while no player is alive.
pub fn far_cull(
    mut commands: Commands,
    ctx: HordeCtx,
    mut ex: ResMut<Expedition>,
    players: Query<(&Player, &Pos, &Life)>,
    mut roaming: Query<(Entity, &Pos, &Enemy, &mut Roaming)>,
) {
    if !ctx.live(&ex) {
        return;
    }
    let living = living_players(&players);
    if living.is_empty() {
        return;
    }
    let horde = &ctx.content.game.expedition.horde;
    let dt = ctx.clock.gdt();
    let (cull2, hard2) = (horde.cull_distance * horde.cull_distance, horde.hard_cull * horde.hard_cull);
    for (entity, pos, enemy, mut r) in &mut roaming {
        if enemy.hp <= 0.0 {
            continue;
        }
        let d2 = nearest(&living, pos.0).map_or(f32::INFINITY, |(_, d)| d);
        r.far = if d2 > cull2 { r.far + dt } else { 0.0 };
        if r.far <= horde.cull_after && d2 <= hard2 {
            continue;
        }
        commands.entity(entity).despawn();
        if let Some(c) = ex.clusters.iter().find(|c| c.members & bit(r.cluster) != 0) {
            let id = c.id() as usize;
            ex.accum[id] = (ex.accum[id] + r.cost * horde.refund).min(ACCUM_MAX);
        }
    }
}
