//! Content schema — every row type the game loads.
//!
//! Rows reference each other by string `key`. [`crate::ContentDb`] resolves keys to compact ids
//! at load time and [`crate::validate`] checks every reference, so a typo in a spreadsheet fails CI
//! instead of crashing a run.

use gf_core::aim::AimModeParams;
use gf_core::damage::{DamageType, Plating, Resistances};
use gf_core::forge::{ForgeRules, Slot};
use gf_core::modifier::Modifier;
use gf_core::movement::{MoveTuning, Obstacle};
use gf_core::overdrive::OverdriveTuning;
use gf_core::rarity::RarityTable;
use gf_core::revive::ReviveTuning;
use gf_core::scaling::{ChaosTierDef, PartyScaling};
use gf_core::stats::CharacterBaseStats;
use gf_core::status::{StatusKind, StatusTuning};
use gf_core::synergy::{SynergyEffect, SynergyTuning};
use gf_core::weapon::ChassisStats;
use glam::Vec2;
use serde::{Deserialize, Serialize};

/// Production phase a row ships in (roadmap §16). Builds pick a maximum phase.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum Phase {
    /// Prototype: the forge loop.
    #[default]
    P0,
    /// Vertical slice.
    P1,
    /// Early Access launch.
    EA,
    /// 1.0 and post-launch.
    V1,
}

impl Phase {
    pub const ALL: [Phase; 4] = [Phase::P0, Phase::P1, Phase::EA, Phase::V1];

    pub fn parse(s: &str) -> Option<Phase> {
        match s.to_ascii_lowercase().as_str() {
            "p0" => Some(Phase::P0),
            "p1" => Some(Phase::P1),
            "ea" => Some(Phase::EA),
            "v1" | "1.0" => Some(Phase::V1),
            _ => None,
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Phase::P0 => "P0",
            Phase::P1 => "P1",
            Phase::EA => "EA",
            Phase::V1 => "1.0",
        }
    }
}

// ───────────────────────────── game.ron ─────────────────────────────

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AnvilTuning {
    /// Seconds a player must hold the anvil ring (hold-the-anvil wave).
    pub hold_time: f32,
    pub radius: f32,
    /// Seconds the anvil stays hot for forging after the hold completes.
    pub forge_window: f32,
    /// Spawn-rate multiplier during the hold wave.
    pub wave_intensity: f32,
    /// Sim time scale while *every* connected player has the forge UI open (solo = forge focus).
    pub forge_focus_time_scale: f32,
}

impl Default for AnvilTuning {
    fn default() -> Self {
        Self { hold_time: 30.0, radius: 4.5, forge_window: 25.0, wave_intensity: 1.5, forge_focus_time_scale: 0.3 }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct DropTuning {
    /// Part drop chance by enemy class: [Swarm, Elite, MiniBoss, Boss].
    pub part_chance: [f32; 4],
    /// Parts dropped on a guaranteed drop (mini-boss / boss chests).
    pub part_count: [u8; 4],
    /// Godshard drop chance and amount by class.
    pub shard_chance: [f32; 4],
    pub shard_amount: [u32; 4],
    /// Health orb chance by class and heal amount.
    pub health_chance: [f32; 4],
    pub health_amount: f32,
    /// Parts in a Part Cache room reward.
    pub cache_parts: u8,
    /// Godshards in a Godshard Cache room reward.
    pub cache_shards: u32,
    pub pickup_lifetime: f32,
}

impl Default for DropTuning {
    fn default() -> Self {
        Self {
            part_chance: [0.006, 0.3, 1.0, 1.0],
            part_count: [1, 1, 2, 3],
            shard_chance: [0.04, 0.6, 1.0, 1.0],
            shard_amount: [1, 3, 12, 30],
            health_chance: [0.004, 0.08, 1.0, 0.0],
            health_amount: 25.0,
            cache_parts: 2,
            cache_shards: 18,
            pickup_lifetime: 40.0,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RunTuning {
    /// Ember per kill by class [Swarm, Elite, MiniBoss, Boss].
    pub ember_per_kill: [u32; 4],
    pub ember_per_room: u32,
    pub ember_victory_bonus: u32,
    /// Fraction of godshards kept on death (§4: ~40%).
    pub death_shard_keep: f32,
    /// Starting godshards.
    pub start_shards: u32,
    /// Seconds between clearing a room and the doors opening.
    pub door_delay: f32,
    /// Boon rerolls per run (base).
    pub boon_rerolls: u8,
    /// Escalation per room cleared in a biome ("beautiful madness by minute 15").
    pub budget_growth_per_room: f32,
    pub rate_growth_per_room: f32,
    pub hp_growth_per_room: f32,
    /// Additional enemy HP multiplier per biome depth.
    pub hp_growth_per_biome: f32,
}

impl Default for RunTuning {
    fn default() -> Self {
        Self {
            ember_per_kill: [1, 6, 40, 150],
            ember_per_room: 15,
            ember_victory_bonus: 250,
            death_shard_keep: 0.4,
            start_shards: 6,
            door_delay: 1.2,
            boon_rerolls: 1,
            budget_growth_per_room: 0.14,
            rate_growth_per_room: 0.1,
            hp_growth_per_room: 0.05,
            hp_growth_per_biome: 0.6,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EchoTuning {
    /// Echo drones fight at ~35% effectiveness (§6).
    pub effectiveness: f32,
    pub orbit_radius: f32,
    pub leash: f32,
}

impl Default for EchoTuning {
    fn default() -> Self {
        Self { effectiveness: 0.35, orbit_radius: 2.2, leash: 9.0 }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CameraTuning {
    /// Camera pitch below horizontal (degrees).
    pub pitch_deg: f32,
    /// Camera yaw around the vertical axis (degrees). 0 = screen-up is world −Z.
    pub yaw_deg: f32,
    /// Vertical world units visible, by player count 1..=4 (co-op pulls back).
    pub view_height: [f32; 4],
    /// Minimum character height as a fraction of screen height (readability rule §12: ≥ 6%).
    pub min_character_screen_frac: f32,
}

impl Default for CameraTuning {
    fn default() -> Self {
        Self { pitch_deg: 55.0, yaw_deg: 0.0, view_height: [22.0, 24.0, 26.0, 28.0], min_character_screen_frac: 0.06 }
    }
}

/// Effect LOD tiers: "Every effect must stay readable at 4-player peak chaos".
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum VfxTier {
    #[default]
    Full,
    Reduced,
    Silhouette,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct VfxBudget {
    /// Live projectile+effect count at which the client drops to `Reduced`.
    pub reduced_at: u32,
    /// … and to `Silhouette`.
    pub silhouette_at: u32,
    /// Max transient particles alive per tier [Full, Reduced, Silhouette].
    pub particles: [u32; 3],
    /// Other players' effects render at this alpha so your own stay readable.
    pub ally_effect_alpha: f32,
}

impl Default for VfxBudget {
    fn default() -> Self {
        Self { reduced_at: 450, silhouette_at: 900, particles: [1600, 700, 200], ally_effect_alpha: 0.55 }
    }
}

/// `game.ron` — global tuning knobs.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GameTuning {
    pub movement: MoveTuning,
    pub revive: ReviveTuning,
    pub overdrive: OverdriveTuning,
    pub synergy: SynergyTuning,
    pub forge: ForgeRules,
    pub rarity: RarityTable,
    pub status: StatusTuning,
    pub anvil: AnvilTuning,
    pub drops: DropTuning,
    pub run: RunTuning,
    pub echo: EchoTuning,
    pub camera: CameraTuning,
    pub vfx: VfxBudget,
    /// Player color code: P1..P4 outline/aura (gold, cyan, violet, green).
    pub player_colors: [String; 4],
    /// Enemy telegraph color (danger red-white, always).
    pub telegraph_color: String,
}

// ───────────────────────────── gods ─────────────────────────────

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct GodDef {
    pub key: String,
    pub name: String,
    pub domain: String,
    pub color: String,
    pub color_secondary: String,
    pub playstyle: String,
    #[serde(default)]
    pub phase: Phase,
}

// ───────────────────────────── characters & kits ─────────────────────────────

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct CharacterDef {
    pub key: String,
    pub name: String,
    pub title: String,
    pub role: String,
    #[serde(default)]
    pub phase: Phase,
    pub fantasy: String,
    pub color: String,
    pub stats: CharacterBaseStats,
    pub signature_chassis: String,
    pub passive: String,
    pub active1: String,
    pub active2: String,
    pub ultimate: String,
    pub coop_role: String,
    #[serde(default)]
    pub skins: Vec<String>,
    /// Sigil part keys this character unlocks (3 per character).
    #[serde(default)]
    pub sigils: Vec<String>,
}

/// Where an ability is centred.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub enum Anchor {
    #[default]
    SelfPos,
    /// The aim point, clamped to `range`.
    AimPoint { range: f32 },
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct StatusOnHit {
    pub status: StatusKind,
    pub stacks: u8,
    pub duration: f32,
}

/// A periodic ground pound while a buff is active (Mountainfall).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Pulse {
    pub interval: f32,
    pub radius: f32,
    pub damage: f32,
    pub element: DamageType,
    #[serde(default)]
    pub knockback: f32,
}

/// Ability script primitives. A kit is a sequence of these; the simulation implements each once.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum AbilityStep {
    /// Leap toward the aim point (clamped to `range`) over `time`, untargetable while airborne.
    Leap {
        range: f32,
        time: f32,
    },
    /// Instant teleport along the aim direction, leaving an optional damaging trail.
    Blink {
        range: f32,
        #[serde(default)]
        trail_damage: f32,
        #[serde(default)]
        element: DamageType,
    },
    /// Charge forward, damaging and optionally dragging enemies along.
    Rush {
        distance: f32,
        time: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
        #[serde(default)]
        drag: bool,
    },
    /// Instant area damage.
    Nova {
        radius: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
        #[serde(default)]
        at: Anchor,
        #[serde(default)]
        stun: f32,
        #[serde(default)]
        knockback: f32,
        #[serde(default)]
        status: Option<StatusOnHit>,
        /// Seconds before it lands (mortars); telegraphed to allies.
        #[serde(default)]
        delay: f32,
    },
    /// Piercing line in the aim direction (hits every enemy along it).
    Line {
        length: f32,
        width: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
        #[serde(default)]
        status: Option<StatusOnHit>,
    },
    /// Cone burst in the aim direction.
    Cone {
        range: f32,
        angle_deg: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
        #[serde(default)]
        status: Option<StatusOnHit>,
    },
    /// Chain lightning from the caster through up to `targets` enemies.
    ChainBurst {
        targets: u8,
        range: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
        /// Damage scales with the equipped weapon's fire rate (Arc Nova).
        #[serde(default)]
        scale_with_fire_rate: bool,
    },
    /// Projectile-blocking forge barricade perpendicular to the aim.
    Barricade {
        length: f32,
        hp: f32,
        duration: f32,
        offset: f32,
    },
    /// Deploy turrets that copy the caster's weapon at `power`.
    Turret {
        power: f32,
        duration: f32,
        count: u8,
    },
    /// Timed self-buff.
    Buff {
        duration: f32,
        #[serde(default)]
        mods: Vec<Modifier>,
        #[serde(default)]
        root_self: bool,
        #[serde(default)]
        taunt: bool,
        /// Visual/size scale while active (Mountainfall avatar).
        #[serde(default = "one_f32")]
        scale: f32,
        #[serde(default)]
        pulse: Option<Pulse>,
        #[serde(default)]
        infinite_dash: bool,
    },
    /// Persistent area (Still Field, Binding Hex, storm fronts, decoys).
    Field {
        radius: f32,
        duration: f32,
        #[serde(default)]
        at: Anchor,
        #[serde(default)]
        dps: f32,
        #[serde(default)]
        element: DamageType,
        #[serde(default)]
        slow: f32,
        #[serde(default)]
        root: bool,
        #[serde(default)]
        status: Option<StatusOnHit>,
        /// Modifiers granted to allies standing inside.
        #[serde(default)]
        ally_mods: Vec<Modifier>,
        /// Field travels along the aim direction at this speed.
        #[serde(default)]
        travel_speed: f32,
        /// Enemies killed inside drop extra parts.
        #[serde(default)]
        bonus_drops: bool,
        #[serde(default)]
        taunt: bool,
    },
    Taunt {
        radius: f32,
        duration: f32,
    },
    /// Shield self (radius 0) or allies in radius.
    Shield {
        amount: f32,
        radius: f32,
    },
    /// Revert damage taken over the last `seconds` (self or most-hurt ally in range).
    RewindWounds {
        seconds: f32,
        range: f32,
    },
    /// Freeze all enemies; optionally reset ally cooldowns when it ends.
    TimeStop {
        duration: f32,
        reset_ally_cooldowns: bool,
    },
    /// Refill dash charges.
    RefillDash,
    /// Next `count` shots gain `mods`.
    NextShots {
        count: u8,
        mods: Vec<Modifier>,
    },
}

fn one_f32() -> f32 {
    1.0
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AbilityDef {
    pub name: String,
    #[serde(default)]
    pub desc: String,
    /// Seconds (actives). Ultimates charge instead.
    #[serde(default)]
    pub cooldown: f32,
    pub steps: Vec<AbilityStep>,
}

/// Character passives. Each variant is implemented once in the simulation.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum PassiveDef {
    /// Valdris — Reforged Flesh: damage taken converts to Armor (≤50% mitigation);
    /// when armor breaks, emit a shockwave taunt.
    ArmorConversion {
        conversion: f32,
        max_armor: f32,
        max_mitigation: f32,
        break_radius: f32,
        break_damage: f32,
        break_knockback: f32,
        break_taunt: f32,
        break_cooldown: f32,
    },
    /// Selene — Static Charge: movement builds charge; the next active deals bonus damage.
    StaticCharge { per_meter: f32, max_bonus: f32 },
    /// Kael — Ghost Step: kills refund dash and grant decaying crit chance.
    GhostStep { crit_per_kill: f32, max_crit: f32, decay_per_s: f32, dash_refund_chance: f32 },
    /// Always-on modifiers (fallback for simple passives).
    Mods(Vec<Modifier>),
}

/// `kits.ron` — the playable implementation of a character. A character is playable iff it has a kit.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct KitDef {
    pub character: String,
    pub passive: PassiveDef,
    pub active1: AbilityDef,
    pub active2: AbilityDef,
    pub ultimate: AbilityDef,
}

// ───────────────────────────── forge content ─────────────────────────────

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct ChassisDef {
    pub key: String,
    pub name: String,
    #[serde(default)]
    pub desc: String,
    #[serde(default)]
    pub phase: Phase,
    #[serde(default)]
    pub unlock_forge_level: u8,
    pub stats: ChassisStats,
    /// Innate behaviour compiled before any part (e.g. Coinshooter's built-in ricochet).
    #[serde(default)]
    pub mods: Vec<Modifier>,
    #[serde(default)]
    pub tags: Vec<String>,
}

fn default_weight() -> f32 {
    1.0
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct PartDef {
    pub key: String,
    pub name: String,
    pub slot: Slot,
    #[serde(default)]
    pub phase: Phase,
    #[serde(default)]
    pub desc: String,
    pub mods: Vec<Modifier>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default = "default_weight")]
    pub weight: f32,
    /// Sigils carry a god-soul.
    #[serde(default)]
    pub god: Option<String>,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BoonKind {
    #[default]
    Standard,
    /// One per god; requires boons from that god.
    Legendary,
    /// Two gods; unlocks when holding boons from both.
    Duo,
    /// Co-op only; applies to every player.
    Team,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum BoonReq {
    /// Hold at least `count` boons from `god`.
    FromGod { god: String, count: u8 },
    /// Hold a specific boon.
    Boon(String),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BoonDef {
    pub key: String,
    pub name: String,
    pub kind: BoonKind,
    /// Owning god(s): 1 for Standard/Legendary, 2 for Duo, 0–1 for Team.
    pub gods: Vec<String>,
    #[serde(default)]
    pub phase: Phase,
    #[serde(default)]
    pub desc: String,
    pub mods: Vec<Modifier>,
    #[serde(default)]
    pub requires: Vec<BoonReq>,
    #[serde(default = "default_weight")]
    pub weight: f32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum IngredientKey {
    Chassis(String),
    Part(String),
    Element(DamageType),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RecipeDef {
    pub key: String,
    pub name: String,
    #[serde(default)]
    pub phase: Phase,
    pub ingredients: Vec<IngredientKey>,
    #[serde(default)]
    pub bonus: Vec<Modifier>,
    #[serde(default)]
    pub codex: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct SynergyDef {
    pub key: String,
    pub name: String,
    pub a: DamageType,
    pub b: DamageType,
    #[serde(default)]
    pub phase: Phase,
    #[serde(default)]
    pub desc: String,
    pub effect: SynergyEffect,
}

// ───────────────────────────── enemies ─────────────────────────────

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum EnemyClass {
    #[default]
    Swarm,
    Elite,
    MiniBoss,
    Boss,
}

impl EnemyClass {
    #[inline]
    pub const fn index(self) -> usize {
        self as usize
    }
}

/// Presentation hint for greybox meshes until authored models exist.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EnemyShape {
    #[default]
    Blob,
    Hound,
    Wisp,
    Brute,
    Spire,
    Crawler,
    Colossus,
}

/// Telegraph shapes. All enemy damage except contact resolves through a visible telegraph.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum TelegraphShape {
    Circle { radius: f32 },
    Line { length: f32, width: f32 },
    Cone { range: f32, angle_deg: f32 },
    Ring { inner: f32, outer: f32 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum BossAttack {
    /// Telegraphed shape at the target (or self), resolving after `windup`.
    Strike {
        shape: TelegraphShape,
        #[serde(default)]
        at_self: bool,
        windup: f32,
        damage: f32,
        #[serde(default)]
        element: DamageType,
    },
    /// A trail of `count` circles marching toward the target.
    SlamTrail { count: u8, spacing: f32, radius: f32, windup: f32, stagger: f32, damage: f32 },
    /// Ring of slow, readable projectiles.
    Radial { projectiles: u8, speed: f32, damage: f32, radius: f32 },
    /// Summon adds.
    Summon { enemy: String, count: u8 },
    /// Leave hazard pools at random points near players.
    Pools { count: u8, radius: f32, duration: f32, dps: f32, windup: f32 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BossPhase {
    /// Phase becomes active when HP fraction drops below this.
    pub below: f32,
    pub name: String,
    pub attacks: Vec<BossAttack>,
    /// Seconds between attacks.
    pub cadence: f32,
    #[serde(default = "one_f32")]
    pub speed_mult: f32,
}

/// `bosses.ron` — boss & mini-boss scripts.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BossScript {
    pub key: String,
    pub phases: Vec<BossPhase>,
    /// Preferred distance from the target.
    #[serde(default)]
    pub keep_distance: f32,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum EnemyBehavior {
    /// Walk straight at the target; contact damage.
    Chaser,
    /// Chaser with lateral jitter (packs feel alive).
    Swarmer { jitter: f32 },
    /// Wind up (line telegraph), then charge.
    Charger { range: f32, windup: f32, speed: f32, duration: f32, cooldown: f32, damage: f32, width: f32 },
    /// Lob at the target: circle telegraph where it lands.
    Lobber { range: f32, windup: f32, radius: f32, damage: f32, cooldown: f32, keep_distance: f32 },
    /// Line beam telegraph then resolve.
    Caster { range: f32, windup: f32, width: f32, length: f32, damage: f32, cooldown: f32, keep_distance: f32 },
    /// Run in and detonate after a fuse (ring telegraph).
    Bomber { trigger_range: f32, fuse: f32, radius: f32, damage: f32 },
    /// Shield nearby allies periodically; keep distance.
    Support { range: f32, shield: f32, interval: f32, keep_distance: f32 },
    /// Scripted multi-phase fight (see `bosses.ron`).
    Boss { script: String },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct EnemyDef {
    pub key: String,
    pub name: String,
    /// Biome key, or "any".
    pub biome: String,
    pub class: EnemyClass,
    #[serde(default)]
    pub phase: Phase,
    #[serde(default)]
    pub desc: String,
    pub hp: f32,
    pub speed: f32,
    pub radius: f32,
    #[serde(default)]
    pub contact_damage: f32,
    /// Knockback resistance (higher = heavier).
    #[serde(default = "one_f32")]
    pub mass: f32,
    #[serde(default)]
    pub resist: Resistances,
    #[serde(default)]
    pub plating: Option<Plating>,
    #[serde(default)]
    pub shield: f32,
    pub behavior: EnemyBehavior,
    pub color: String,
    #[serde(default)]
    pub shape: EnemyShape,
    #[serde(default = "one_f32")]
    pub scale: f32,
    /// Spawn pack size range.
    #[serde(default = "default_pack")]
    pub pack: (u8, u8),
    /// Explodes on death (Emberwisp).
    #[serde(default)]
    pub death_burst: Option<(f32, f32)>,
}

fn default_pack() -> (u8, u8) {
    (1, 1)
}

// ───────────────────────────── world ─────────────────────────────

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RoomKind {
    #[default]
    Combat,
    Elite,
    Anvil,
    MiniBoss,
    Boss,
    Treasure,
}

/// Where enemies enter a room.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum SpawnZone {
    /// Along the arena edges (outside the player's comfort radius).
    Edges { margin: f32 },
    /// Around a point.
    Point { at: Vec2, radius: f32 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct EncounterDef {
    /// Total enemy "weight" spawned (swarm = 1, elite = 6).
    pub budget: f32,
    /// Seconds over which the budget is released (ramps from `rate_start` to `rate_end`).
    pub duration: f32,
    pub rate_start: f32,
    pub rate_end: f32,
    pub max_alive: u32,
    pub elite_chance: f32,
    /// Explicit spawns at room start (mini-boss/boss rooms).
    pub fixed: Vec<String>,
}

impl Default for EncounterDef {
    fn default() -> Self {
        Self {
            budget: 80.0,
            duration: 60.0,
            rate_start: 1.0,
            rate_end: 3.5,
            max_alive: 220,
            elite_chance: 0.04,
            fixed: Vec::new(),
        }
    }
}

/// Presentation-only set dressing (painted-world hooks).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum Decor {
    LavaCrack { from: Vec2, to: Vec2, width: f32 },
    BrokenAnvil { at: Vec2, scale: f32 },
    Brazier { at: Vec2 },
    Pillar { at: Vec2, radius: f32, height: f32 },
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RoomDef {
    pub key: String,
    pub biome: String,
    pub kind: RoomKind,
    #[serde(default)]
    pub phase: Phase,
    pub half_extents: Vec2,
    #[serde(default)]
    pub obstacles: Vec<Obstacle>,
    pub player_spawn: Vec2,
    #[serde(default)]
    pub anvil: Option<Vec2>,
    #[serde(default)]
    pub exits: Vec<Vec2>,
    pub spawn_zones: Vec<SpawnZone>,
    #[serde(default)]
    pub encounter: EncounterDef,
    #[serde(default)]
    pub decor: Vec<Decor>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct WeightedKey {
    pub key: String,
    pub weight: f32,
}

/// A step in a biome's room sequence.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum RunStep {
    /// A room whose kind follows the chosen door reward.
    Door,
    Fixed(RoomKind),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BiomeDef {
    pub key: String,
    pub name: String,
    #[serde(default)]
    pub phase: Phase,
    pub theme: String,
    /// Ground, accent (glow) and fog/background colors.
    pub palette: [String; 3],
    pub swarm: Vec<WeightedKey>,
    pub elites: Vec<WeightedKey>,
    pub minibosses: Vec<String>,
    pub boss: String,
    pub sequence: Vec<RunStep>,
    /// Guarantee at least this many Anvil door options per biome visit.
    #[serde(default)]
    pub min_anvils: u8,
}

// ───────────────────────────── meta & tracking ─────────────────────────────

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AltarTree {
    #[default]
    Arsenal,
    Flesh,
    Fate,
    Bond,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub enum AltarEffect {
    /// Permanent modifiers applied to every run.
    Mods(Vec<Modifier>),
    /// Unlock a content row (chassis, part, character, sigil) by key.
    Unlock(String),
    /// + boon rerolls per run.
    BoonRerolls(u8),
    /// + starting godshards.
    StartShards(u32),
    /// + forge charges per anvil.
    AnvilCharges(u8),
    /// + Echo effectiveness (fraction).
    EchoPower(f32),
    /// + solo Rekindles.
    Rekindles(u8),
    /// + part bag capacity.
    BagCapacity(u8),
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AltarNode {
    pub key: String,
    pub tree: AltarTree,
    pub tier: u8,
    pub name: String,
    #[serde(default)]
    pub desc: String,
    pub cost: u32,
    #[serde(default)]
    pub requires: Vec<String>,
    pub effect: AltarEffect,
    #[serde(default)]
    pub phase: Phase,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct TreeNode {
    pub key: String,
    pub character: String,
    pub index: u8,
    pub branch: String,
    pub name: String,
    #[serde(default)]
    pub desc: String,
    pub cost: u32,
    #[serde(default)]
    pub requires: Vec<String>,
    #[serde(default)]
    pub mods: Vec<Modifier>,
    #[serde(default)]
    pub unlock: Option<String>,
    #[serde(default)]
    pub phase: Phase,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AchievementDef {
    pub key: String,
    pub name: String,
    pub desc: String,
    pub category: String,
    /// Telemetry stat that drives it and its target value.
    pub stat: String,
    pub target: u32,
    #[serde(default)]
    pub phase: Phase,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct BarkDef {
    pub key: String,
    /// Character key or hub cast ("smithshade", "vessa", "hound9").
    pub speaker: String,
    /// Trigger id ("run_start", "low_hp", "forge", "synergy", "kill_streak", …).
    pub trigger: String,
    pub line: String,
    #[serde(default = "default_weight")]
    pub weight: f32,
}

/// All shipped aim-mode tuning rows (`aim_modes.ron`).
pub type AimModeTable = Vec<AimModeParams>;
/// Party scaling rows (`party_scaling.ron`).
pub type PartyScalingTable = Vec<PartyScaling>;
/// Chaos tier rows (`chaos_tiers.ron`).
pub type ChaosTierTable = Vec<ChaosTierDef>;
