//! Simulation resources: content, clock, RNG streams, per-tick queues, run state.

use crate::spatial::SpatialGrid;
use gf_content::ContentDb;
use gf_content::schema::{Phase, RoomKind};
use gf_core::damage::DamageType;
use gf_core::ids::{BiomeId, BoonId, EnemyId, NetId, RoomId, SourceId};
use gf_core::movement::Arena;
use gf_core::overdrive::TeamOverdrive;
use gf_core::rarity::Rarity;
use gf_core::rng::GfRng;
use gf_core::scaling::EnemyTuning;
use gf_core::status::StatusKind;
use gf_core::weapon::WeaponProfile;
use gf_engine::prelude::*;
use gf_net::{DoorReward, GameEvent, RunPhase};
use std::sync::Arc;

#[derive(Resource, Clone)]
pub struct Content(pub Arc<ContentDb>);

impl std::ops::Deref for Content {
    type Target = ContentDb;
    fn deref(&self) -> &ContentDb {
        &self.0
    }
}

/// Run-level settings chosen by the host.
#[derive(Resource, Clone, Debug)]
pub struct SimSettings {
    pub seed: u64,
    /// Content phase this build plays (P0 prototype, P1 vertical slice, EA…).
    pub phase: Phase,
    pub chaos_tier: u8,
    /// QA override for the opening room (content key).
    pub start_room: Option<String>,
}

#[derive(Resource, Debug)]
pub struct SimClock {
    pub tick: u32,
    pub dt: f32,
    /// Forge-focus time scale (1.0 normally).
    pub scale: f32,
    pub time: f32,
    /// Stolen Second: enemies frozen for this many seconds.
    pub freeze: f32,
    /// Reset every ally's cooldowns when the freeze ends.
    pub freeze_resets_cooldowns: bool,
    /// Set for one tick when a freeze ends with a cooldown reset.
    pub reset_cooldowns: bool,
}

impl SimClock {
    /// Gameplay delta time (scaled).
    #[inline]
    pub fn gdt(&self) -> f32 {
        self.dt * self.scale
    }
}

/// Independent RNG streams so adding a roll in one system never perturbs another.
#[derive(Resource, Debug)]
pub struct Rngs {
    pub combat: GfRng,
    pub loot: GfRng,
    pub director: GfRng,
    pub ai: GfRng,
    pub boons: GfRng,
}

impl Rngs {
    pub fn new(seed: u64) -> Self {
        let base = GfRng::new(seed);
        Self { combat: base.fork(1), loot: base.fork(2), director: base.fork(3), ai: base.fork(4), boons: base.fork(5) }
    }
}

#[derive(Resource, Debug)]
pub struct NetIds {
    next: u32,
}

impl Default for NetIds {
    fn default() -> Self {
        Self { next: 100 }
    }
}

impl NetIds {
    pub fn alloc(&mut self) -> NetId {
        self.next += 1;
        NetId(self.next)
    }
}

/// Cosmetic events emitted this tick (shipped in the next snapshot).
#[derive(Resource, Debug, Default)]
pub struct Events(pub Vec<GameEvent>);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HitKind {
    /// A weapon projectile / beam / melee strike (on-hit effects, synergies, Deadeye).
    Weapon,
    /// Chain arcs, forks, splash and explosions from a weapon (on-hit statuses, no synergy).
    Secondary,
    Ability,
    Dot,
    Synergy,
    Hazard,
}

/// Damage headed for an enemy.
#[derive(Clone, Debug)]
pub struct Hit {
    pub target: Entity,
    pub source: SourceId,
    pub source_entity: Option<Entity>,
    pub base: f32,
    pub element: DamageType,
    pub crit_chance: f32,
    pub crit_mult: f32,
    pub bonus: f32,
    pub precision: bool,
    pub precision_crit_bonus: f32,
    pub knockback: Vec2,
    pub weapon: Option<Arc<WeaponProfile>>,
    pub kind: HitKind,
    pub status: Option<(StatusKind, u8, f32)>,
    pub stun: f32,
    pub pos: Vec2,
}

impl Hit {
    pub fn simple(target: Entity, source: SourceId, base: f32, element: DamageType, kind: HitKind, pos: Vec2) -> Self {
        Self {
            target,
            source,
            source_entity: None,
            base,
            element,
            crit_chance: 0.0,
            crit_mult: 1.0,
            bonus: 1.0,
            precision: false,
            precision_crit_bonus: 0.0,
            knockback: Vec2::ZERO,
            weapon: None,
            kind,
            status: None,
            stun: 0.0,
            pos,
        }
    }
}

#[derive(Resource, Debug, Default)]
pub struct DamageQueue(pub Vec<Hit>);

/// Damage headed for a player.
#[derive(Clone, Copy, Debug)]
pub struct PlayerHit {
    pub target: Entity,
    pub amount: f32,
    pub element: DamageType,
    pub from: Vec2,
}

#[derive(Resource, Debug, Default)]
pub struct PlayerHits(pub Vec<PlayerHit>);

#[derive(Clone, Debug)]
pub struct KillRecord {
    pub entity: Entity,
    pub net: NetId,
    pub def: EnemyId,
    pub class: gf_content::schema::EnemyClass,
    pub pos: Vec2,
    pub killer: SourceId,
    pub weapon: Option<Arc<WeaponProfile>>,
    pub bonus_drops: bool,
    pub volatile: bool,
}

#[derive(Resource, Debug, Default)]
pub struct Kills(pub Vec<KillRecord>);

#[derive(Resource, Debug, Default)]
pub struct ArenaRes(pub Arena);

#[derive(Resource, Debug, Default)]
pub struct Grid(pub SpatialGrid);

#[derive(Resource, Debug)]
pub struct Tuning {
    pub enemy: EnemyTuning,
    pub party: u8,
}

#[derive(Resource, Debug, Default)]
pub struct Overdrive(pub TeamOverdrive);

/// Team boons (co-op): applied to every player.
#[derive(Resource, Debug, Default)]
pub struct TeamBoons(pub Vec<(BoonId, Rarity)>);

#[derive(Resource, Debug)]
pub struct RunState {
    pub started: bool,
    pub biomes: Vec<BiomeId>,
    pub biome_idx: usize,
    pub step: usize,
    pub depth: u16,
    pub room: RoomId,
    pub room_kind: RoomKind,
    pub room_serial: u32,
    pub phase: RunPhase,
    /// Reward granted when the current room is cleared.
    pub reward: Option<DoorReward>,
    pub cleared_timer: f32,
    pub doors_spawned: bool,
    pub kills: u32,
    pub ember: f32,
    pub anvils_offered: u8,
    pub rooms_in_biome: u8,
    pub pending_door: Option<DoorReward>,
    pub transition: f32,
}

impl Default for RunState {
    fn default() -> Self {
        Self {
            started: false,
            biomes: Vec::new(),
            biome_idx: 0,
            step: 0,
            depth: 0,
            room: RoomId(0),
            room_kind: RoomKind::Combat,
            room_serial: 0,
            phase: RunPhase::Combat,
            reward: None,
            cleared_timer: 0.0,
            doors_spawned: false,
            kills: 0,
            ember: 0.0,
            anvils_offered: 0,
            rooms_in_biome: 0,
            pending_door: None,
            transition: 0.0,
        }
    }
}

impl RunState {
    pub fn is_over(&self) -> bool {
        matches!(self.phase, RunPhase::Victory | RunPhase::Defeat)
    }
}

/// The spawn director's view of the current room's encounter.
#[derive(Resource, Debug, Default)]
pub struct Encounter {
    pub budget_left: f32,
    pub budget_total: f32,
    pub elapsed: f32,
    pub duration: f32,
    pub rate_start: f32,
    pub rate_end: f32,
    pub max_alive: u32,
    pub elite_chance: f32,
    pub accum: f32,
    pub hp_mult: f32,
    /// Anvil rooms spawn only while the anvil is kindling/hot.
    pub anvil_gated: bool,
    pub alive: u32,
    /// Anti-stall: kills seen and seconds since the last one.
    pub last_kills: u32,
    pub stall: f32,
}
