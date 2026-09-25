//! Wire protocol. Host-authoritative: clients send *intent* (commands), the host simulates and
//! streams *state* (delta snapshots). The host's own local player is just another client on a
//! loopback transport — there is no single-player code path (§20.3).

use crate::quant::{QPos, QVel};
use gf_core::aim::{AimMode, TargetBias};
use gf_core::damage::DamageType;
use gf_core::forge::{ForgeAction, ForgeError, ForgeOutcome, ForgeWallet, PartBag, WeaponBuild};
use gf_core::ids::NetId;
use gf_core::movement::MoverState;
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_core::weapon::ProjectileStyle;
use serde::{Deserialize, Serialize};

/// Bump on any wire-incompatible change.
pub const PROTOCOL_VERSION: u16 = 1;
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

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum AnvilState {
    #[default]
    Dormant,
    /// Hold-the-anvil wave in progress.
    Kindling,
    /// Forging window open.
    Hot,
    Spent,
}

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
    pub anvil: Option<AnvilView>,
    pub boss: Option<BossView>,
    pub chaos_tier: u8,
    pub ember: u32,
    pub party: u8,
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
}
