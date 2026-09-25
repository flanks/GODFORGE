//! Wire protocol. Host-authoritative: clients send *intent* (commands), the host simulates and
//! streams *state* (delta snapshots). The host's own local player is just another client on a
//! loopback transport — there is no single-player code path (§20.3).

use crate::quant::{QPos, QVel};
use gf_core::aim::{AimMode, TargetBias};
use gf_core::damage::DamageType;
use gf_core::forge::{ForgeAction, ForgeError, ForgeOutcome, ForgeWallet, PartBag, WeaponBuild};
use gf_core::ids::NetId;
use gf_core::movement::MoverState;
pub use gf_core::poi::{PoiKind, PoiState};
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_core::weapon::ProjectileStyle;
use serde::{Deserialize, Serialize};

/// Bump on any wire-incompatible change. v3: biome maps (POIs, the stage view, per-player anvil
/// and boss views, map pings; OPEN_WORLD.md §6.1).
pub const PROTOCOL_VERSION: u16 = 3;
/// Maximum players per session.
pub const MAX_PLAYERS: usize = 4;
/// Commands carried redundantly in every input packet (loss resilience).
pub const INPUT_REDUNDANCY: usize = 4;

// ───────────────────────────── client → host ─────────────────────────────

/// Edge-triggered inputs as wrapping counters: a press is never lost even if packets are, and a
/// repeated command never double-fires.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Presses {
    pub dash: u8,
    pub active1: u8,
    pub active2: u8,
    pub ult: u8,
    pub interact: u8,
    pub overdrive: u8,
    pub force_target: u8,
    pub ping: u8,
}

impl Presses {
    /// Number of new presses of each button since `prev` (wrapping-safe).
    pub fn since(&self, prev: &Presses) -> Presses {
        Presses {
            dash: self.dash.wrapping_sub(prev.dash),
            active1: self.active1.wrapping_sub(prev.active1),
            active2: self.active2.wrapping_sub(prev.active2),
            ult: self.ult.wrapping_sub(prev.ult),
            interact: self.interact.wrapping_sub(prev.interact),
            overdrive: self.overdrive.wrapping_sub(prev.overdrive),
            force_target: self.force_target.wrapping_sub(prev.force_target),
            ping: self.ping.wrapping_sub(prev.ping),
        }
    }
}

/// Discrete, must-happen-once requests. Delivered reliably over the unreliable input stream:
/// the client repeats the oldest un-acked action (by `id`) until the host acks it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PlayerAction {
    Forge(ForgeAction),
    /// Pick one of the room-reward doors.
    ChooseDoor(u8),
    /// Pick one of the offered boons.
    PickBoon(u8),
    RerollBoons,
    /// A ping placed on the full map (becomes a `GameEvent::Ping` at that spot).
    MapPing(QPos),
}

/// One simulation tick of player intent.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct PlayerCommand {
    pub seq: u32,
    pub move_dir: (i8, i8),
    /// Aim direction (16-bit angle) and distance to the aim point (1/64 units).
    pub aim: u16,
    pub aim_dist: u16,
    pub fire: bool,
    pub presses: Presses,
    pub aim_mode: AimMode,
    pub bias: TargetBias,
    /// Forge UI open (when every player has it open the host applies forge-focus time scale).
    pub forge_open: bool,
    pub action: Option<(u16, PlayerAction)>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct InputFrame {
    /// Newest snapshot tick the client has fully reconstructed (delta baseline).
    pub ack_tick: u32,
    /// Most recent commands, oldest first (≤ INPUT_REDUNDANCY).
    pub commands: Vec<PlayerCommand>,
}

/// Pre-run loadout chosen in the hub.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Loadout {
    pub character: u16,
    pub chassis: u16,
    pub sigil: Option<u16>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum ClientMsg {
    Hello { protocol: u16, content_hash: u64, name: String, loadout: Loadout, nonce: u32 },
    Input(InputFrame),
    Leave,
}

// ───────────────────────────── host → client ─────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum RejectReason {
    ProtocolMismatch { host: u16 },
    ContentMismatch { host: u64 },
    Full,
    RunInProgress,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct RosterEntry {
    pub slot: u8,
    pub name: String,
    pub loadout: Loadout,
    pub connected: bool,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum ServerMsg {
    Welcome { slot: u8, nonce: u32, tick: u32, tick_hz: u16, snapshot_every: u8, seed: u64 },
    Reject { nonce: u32, reason: RejectReason },
    Snapshot(Box<SnapshotPacket>),
    Roster(Vec<RosterEntry>),
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum RunPhase {
    #[default]
    Combat,
    /// Room cleared; reward doors are open.
    Cleared,
    Victory,
    Defeat,
}

/// Lifecycle of an anvil. Legacy anvil rooms replicate it as `EntityView.status` of
/// `EntityKind::Anvil`; on biome maps an anvil is a POI and its state maps to [`PoiState`]
/// (Dormant → Dormant, Kindling → Active, Hot → Hot, Spent → Done).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum AnvilState {
    #[default]
    Dormant,
    /// Hold-the-anvil wave in progress.
    Kindling,
    /// Forging window open.
    Hot,
    Spent,
}

impl AnvilState {
    #[inline]
    pub const fn to_u8(self) -> u8 {
        self as u8
    }

    /// The state a wire byte encodes (unknown values read as `Dormant`).
    pub const fn from_u8(v: u8) -> Self {
        match v {
            1 => AnvilState::Kindling,
            2 => AnvilState::Hot,
            3 => AnvilState::Spent,
            _ => AnvilState::Dormant,
        }
    }

    /// The POI state a map anvil shows as.
    pub const fn poi_state(self) -> PoiState {
        match self {
            AnvilState::Dormant => PoiState::Dormant,
            AnvilState::Kindling => PoiState::Active,
            AnvilState::Hot => PoiState::Hot,
            AnvilState::Spent => PoiState::Done,
        }
    }

    /// The anvil state a map anvil's POI state stands for (the inverse of [`Self::poi_state`]).
    pub const fn from_poi_state(s: PoiState) -> Self {
        match s {
            PoiState::Active => AnvilState::Kindling,
            PoiState::Hot => AnvilState::Hot,
            PoiState::Done => AnvilState::Spent,
            _ => AnvilState::Dormant,
        }
    }
}

/// An anvil as one player sees it (`PrivateView.anvil`): the anvil their forge charges come from,
/// else the nearest one that is not Spent.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct AnvilView {
    pub id: NetId,
    pub state: AnvilState,
    /// 0..=1 hold progress while kindling.
    pub progress: f32,
    /// Seconds left of the forge window while hot.
    pub time_left: f32,
    /// No player is inside the ring (progress paused).
    pub contested: bool,
}

/// A boss health bar: the arena boss (`RunView.boss`) or the nearest awake guard boss, such as a
/// Warlord (`PrivateView.boss`).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct BossView {
    pub id: NetId,
    pub enemy: u16,
    pub hp_frac: f32,
    pub phase: u8,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct RunView {
    pub phase: RunPhase,
    pub biome: u16,
    pub room: u16,
    /// Changes whenever a new room loads (clients rebuild room geometry on change).
    pub room_serial: u32,
    /// Layout seed of the current room: every peer rebuilds the identical arena with
    /// `gf_content::procgen::resolve_room(db, room, room_seed)` (0 = the authored template).
    pub room_seed: u32,
    /// Rooms cleared this run.
    pub depth: u16,
    pub step: u8,
    pub steps: u8,
    pub time: f32,
    pub time_scale: f32,
    pub kills: u32,
    /// Remaining encounter fraction (0 = spawns exhausted).
    pub encounter_left: f32,
    pub overdrive_meter: f32,
    pub overdrive_active: f32,
    /// The arena boss (never a guard such as a Warlord: see `PrivateView.boss`).
    pub boss: Option<BossView>,
    pub chaos_tier: u8,
    pub ember: u32,
    pub party: u8,
    /// `MapLayout.hash as u32` of the current biome map (0 for rooms). Clients compare it with the
    /// map they rebuilt from `(room, room_seed)`.
    pub layout_hash: u32,
    /// The biome map's objective state (`Some` on maps only).
    pub stage: Option<StageView>,
}

/// The Boss Gate as the HUD shows it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum GateView {
    /// Short of Seals (or the Warlord).
    #[default]
    Sealed,
    /// Open: interact inside the ring to start the gathering.
    Open,
    /// The countdown into the boss arena, in deciseconds.
    Gathering { left_ds: u8 },
}

/// Objective state of a biome map (OPEN_WORLD.md §2, §6.1).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct StageView {
    pub seals: u8,
    pub required: u8,
    /// The Warlord is dead.
    pub warlord: bool,
    pub gate: GateView,
    /// Seconds since the party made landfall.
    pub time: f32,
    /// Threat clock: `level × 16 + sixteenths` of the way to the next level.
    pub threat: u8,
    /// A horde surge (its warning or the surge itself): the direction it comes from (16-bit angle).
    pub surge: Option<u16>,
    /// POIs completed on this map.
    pub objectives: u8,
    /// The gate was forced open short of Seals (Unworthy).
    pub forced: bool,
}

impl StageView {
    /// Pack a threat level (saturating at 15) and the fraction (0..1) toward the next one.
    pub fn pack_threat(level: u8, frac: f32) -> u8 {
        level.min(15) * 16 + (frac.clamp(0.0, 1.0) * 16.0).min(15.0) as u8
    }

    /// Threat level (0..=15).
    pub fn threat_level(&self) -> u8 {
        self.threat / 16
    }

    /// Fraction (0..1) of the way to the next threat level.
    pub fn threat_frac(&self) -> f32 {
        (self.threat % 16) as f32 / 16.0
    }
}

bitflags_lite! {
    /// Player buff/state flags.
    pub struct PlayerFlags: u16 {
        const STANCE = 1;
        const AVATAR = 2;
        const OVERDRIVE = 4;
        const AIRBORNE = 8;
        const TAUNTING = 16;
        const INFINITE_DASH = 32;
        const HIT = 64;
        const IN_FIELD = 128;
        const SHIELDED = 256;
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct BeamView {
    pub len: f32,
    pub width: f32,
}

/// Full-precision public state for each player (≤ 4, sent every snapshot).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PlayerView {
    pub slot: u8,
    pub id: NetId,
    pub character: u16,
    /// Exact mover state: client prediction replays inputs from here.
    pub mover: MoverState,
    /// Movement stats the predictor needs to replay inputs exactly.
    pub move_speed: f32,
    pub dash_recharge: f32,
    pub max_dash: u8,
    pub radius: f32,
    pub height: f32,
    pub hp: f32,
    pub max_hp: f32,
    pub shield: f32,
    pub armor: f32,
    pub armor_max: f32,
    pub life: LifeState,
    pub aim: u16,
    pub target: Option<NetId>,
    pub aim_mode: AimMode,
    pub cooldowns: [f32; 2],
    pub cooldowns_max: [f32; 2],
    pub ult: f32,
    pub flags: PlayerFlags,
    pub scale: f32,
    pub deadeye: u8,
    pub passive_meter: f32,
    pub weapon: WeaponBuild,
    pub firing: bool,
    pub charge: f32,
    pub beam: Option<BeamView>,
    pub shards: u32,
    pub kills: u32,
    pub damage: f32,
    pub boons: Vec<u16>,
    pub forge_open: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct BoonOffer {
    pub boon: u16,
    pub rarity: Rarity,
}

/// State only the owning player receives (personal loot streams, §10.7).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct PrivateView {
    pub bag: PartBag,
    pub wallet: ForgeWallet,
    pub at_anvil: bool,
    pub boon_offer: Vec<BoonOffer>,
    pub boon_rerolls: u8,
    pub rekindles: u8,
    /// The anvil my forge charges come from, else the nearest anvil that is not Spent (within
    /// 40 u on biome maps). Drives the anvil prompt, the forge panel and bots.
    pub anvil: Option<AnvilView>,
    /// The nearest awake guard boss (a Warlord) within 40 u of me.
    pub boss: Option<BossView>,
    /// Boon offers waiting behind the current one (shrines claimed while an offer is open).
    pub boon_queue: u8,
    /// Downed with no living ally in reach: the Forge will reforge me beside the nearest ally.
    pub hopeless: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum TeleShape {
    /// Dimensions in 1/32 world units.
    Circle {
        r: u16,
    },
    Line {
        len: u16,
        width: u16,
    },
    Cone {
        range: u16,
        angle_deg: u8,
    },
    Ring {
        inner: u16,
        outer: u16,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum HazardKind {
    Puddle,
    Well,
    Field,
    Pool,
    Trail,
    Ground,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum PickupKind {
    Part { rarity: Rarity },
    Shards(u16),
    Health,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DoorReward {
    PartCache,
    ShardCache,
    Anvil,
    Healing,
    Boon {
        god: u16,
    },
    EliteChallenge,
    /// Leads onward to the mini-boss / boss / next biome (no choice).
    Onward,
}

/// What a replicated entity is.
///
/// `Poi { index }` is a point of interest on a biome map: `MapLayout.pois[index]` gives its kind and
/// site, `EntityView.status` is its [`PoiState`] (`to_u8`) and `hp` its progress (the hold fill, or
/// the share of its guards slain). A legacy room's `Anvil` carries its [`AnvilState`] in `status`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum EntityKind {
    Enemy { def: u16 },
    Projectile { style: ProjectileStyle, element: DamageType, owner: u8, radius_q: u8 },
    EnemyShot { radius_q: u8 },
    Telegraph { shape: TeleShape, dir: u16, windup_ticks: u16, start: u32 },
    Hazard { kind: HazardKind, element: DamageType, radius_q: u16 },
    Pickup { kind: PickupKind, owner: Option<u8> },
    Anvil,
    Door { reward: DoorReward, index: u8 },
    Barricade { half_len_q: u16, dir: u16 },
    Turret { owner: u8 },
    Echo { owner: u8 },
    Blade { owner: u8 },
    Chest,
    Poi { index: u8 },
}

bitflags_lite! {
    /// Entity state flags.
    pub struct EntityFlags: u16 {
        const ELITE = 1;
        const BOSS = 2;
        const SHIELDED = 4;
        const STUNNED = 8;
        const PLATED = 16;
        const WINDUP = 32;
        const FROZEN = 64;
        const TAUNTED = 128;
        const CHARGING = 256;
        const PINGED = 512;
        const PRIMED = 1024;
        /// Player-side effect (ally telegraphs, player hazards): drawn gold, never red.
        const ALLY = 2048;
        /// A hold POI or anvil ring with no living player inside (progress paused or decaying).
        const CONTESTED = 4096;
        /// An enemy the horde director just spawned, still rising from the ground.
        const EMERGING = 8192;
    }
}

/// Straight-line motion: clients extrapolate `pos + vel × (t − t0)`, so an unchanged projectile
/// costs nothing after its first snapshot (entity-level delta skips it).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Motion {
    pub vel: QVel,
    pub t0: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct EntityView {
    pub id: NetId,
    pub kind: EntityKind,
    pub pos: QPos,
    pub motion: Option<Motion>,
    pub facing: u8,
    pub hp: u8,
    pub flags: EntityFlags,
    pub status: u8,
}

/// Cosmetic, fire-and-forget events (lossy is fine; gameplay state is in the snapshot).
///
/// Biome maps (POI `index` into `MapLayout.pois`):
/// * `PoiStarted`: `slot` activated it (hold ring started, guards woken, spring used).
/// * `PoiCompleted`: it paid its reward. `PoiReset`: it went back to Dormant (guards leashed home).
/// * `PoiHint`: "The Forge whispers…", the nearest incomplete seal-bearing POI after a long stall.
/// * `GateGathering`: `slot` started the gathering at the open gate.
/// * `Surge`: a horde surge from direction `dir` (16-bit angle), first the warning (`warn`), then
///   the surge itself.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum GameEvent {
    Hit { target: NetId, amount: u16, crit: bool, precision: bool, element: DamageType, source: u8 },
    Kill { target: NetId, pos: QPos, source: u8, elite: bool },
    PlayerHurt { slot: u8, amount: u16 },
    Shot { slot: u8, dir: u16, element: DamageType },
    Explosion { pos: QPos, radius_q: u16, element: DamageType },
    Arc { from: QPos, to: QPos, element: DamageType },
    Synergy { synergy: u16, pos: QPos, a: u8, b: u8 },
    Ability { slot: u8, which: u8, pos: QPos },
    Forged { slot: u8, outcome: ForgeOutcome },
    ForgeFailed { slot: u8, error: ForgeError },
    RecipeDiscovered { slot: u8, recipe: u16 },
    BoonTaken { slot: u8, boon: u16 },
    Overdrive { slot: u8 },
    Downed { slot: u8 },
    Revived { slot: u8, by: Option<u8> },
    ArmorBreak { slot: u8 },
    PlatesShattered { target: NetId },
    Pickup { slot: u8, kind: PickupKind },
    Ping { slot: u8, pos: QPos, target: Option<NetId> },
    TelegraphResolved { id: NetId },
    BossPhase { boss: NetId, phase: u8 },
    RoomCleared,
    AnvilLit,
    AnvilHot,
    PoiStarted { index: u8, slot: u8 },
    PoiCompleted { index: u8 },
    PoiReset { index: u8 },
    PoiHint { index: u8 },
    SealGained { seals: u8, required: u8 },
    GateOpened { forced: bool },
    GateGathering { slot: u8 },
    Surge { dir: u16, warn: bool },
    ThreatRose { level: u8 },
    CampCleared { at: QPos },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SnapshotPacket {
    pub tick: u32,
    /// Tick of the snapshot this delta is relative to (`None` = full snapshot).
    pub baseline: Option<u32>,
    /// Last command `seq` the host processed for this client (prediction reconciliation).
    pub ack_seq: u32,
    /// Last action id the host applied for this client.
    pub ack_action: u16,
    pub run: RunView,
    pub players: Vec<PlayerView>,
    pub private: PrivateView,
    pub changed: Vec<EntityView>,
    pub removed: Vec<NetId>,
    pub events: Vec<GameEvent>,
    /// Biome maps, full snapshots only: the party's explored 4 u tiles, run-length encoded (seeds
    /// a joining client's fog of war).
    pub fog: Option<Vec<u8>>,
}

/// A fully reconstructed world snapshot (client side, after applying deltas).
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct WorldSnapshot {
    pub tick: u32,
    pub ack_seq: u32,
    pub run: RunView,
    pub players: Vec<PlayerView>,
    pub private: PrivateView,
    /// Sorted by id.
    pub entities: Vec<EntityView>,
    pub events: Vec<GameEvent>,
    /// Explored-tile RLE from a full snapshot (see `SnapshotPacket.fog`).
    pub fog: Option<Vec<u8>>,
}
