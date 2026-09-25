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
    /// Seconds a dropped pickup lasts. Parts don't age while the room is still being fought.
    pub pickup_lifetime: f32,
    /// On a room clear, leftover parts and godshards fly to the party at this speed (u/s):
    /// NIMRODS-scale fields scatter loot far off-screen.
    pub clear_vacuum_speed: f32,
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
            clear_vacuum_speed: 28.0,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RunTuning {
    /// Ember per kill by class [Swarm, Elite, MiniBoss, Boss] (fractional: swarm kills trickle).
    pub ember_per_kill: [f32; 4],
    pub ember_per_room: f32,
    pub ember_victory_bonus: f32,
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
    /// Global multiplier on every room's encounter budget (pacing lever).
    pub budget_mult: f32,
    /// Global multiplier on spawn rates (density lever).
    pub rate_mult: f32,
}

impl Default for RunTuning {
    fn default() -> Self {
        Self {
            ember_per_kill: [0.05, 1.0, 15.0, 60.0],
            ember_per_room: 4.0,
            ember_victory_bonus: 100.0,
            death_shard_keep: 0.4,
            start_shards: 6,
            door_delay: 1.2,
            boon_rerolls: 1,
            budget_growth_per_room: 0.14,
            rate_growth_per_room: 0.1,
            hp_growth_per_room: 0.05,
            hp_growth_per_biome: 0.6,
            budget_mult: 1.0,
            rate_mult: 1.0,
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
    /// A ring around a random living player, just beyond the screen edge: the horde converges
    /// from every side on big open fields (survivor-style).
    Around { min: f32, max: f32 },
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

/// Facing as an integer step of 1/16 turn (22.5°), counter-clockwise from +x on the ground plane:
/// 0 = east, 4 = north (screen-up, toward the gates), 8 = west, 12 = south (toward the camera).
/// Procgen stays trig-free by working in these steps; see [`rot16_dir`].
pub type Rot16 = u8;

/// Unit ground vector of a [`Rot16`] step (a literal table, so it is IEEE-exact everywhere).
pub fn rot16_dir(rot: Rot16) -> Vec2 {
    const S1: f32 = 0.382_683_43; // sin 22.5°
    const S2: f32 = std::f32::consts::FRAC_1_SQRT_2; // sin 45°
    const S3: f32 = 0.923_879_5; // sin 67.5°
    const T: [(f32, f32); 16] = [
        (1.0, 0.0),
        (S3, S1),
        (S2, S2),
        (S1, S3),
        (0.0, 1.0),
        (-S1, S3),
        (-S2, S2),
        (-S3, S1),
        (-1.0, 0.0),
        (-S3, -S1),
        (-S2, -S2),
        (-S1, -S3),
        (0.0, -1.0),
        (S1, -S3),
        (S2, -S2),
        (S3, -S1),
    ];
    let (x, y) = T[(rot & 15) as usize];
    Vec2::new(x, y)
}

/// Architectural finish of a [`Decor::Wall`] block (the env kit picks the mesh family).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum WallStyle {
    /// Ruined masonry run with a jagged, broken top.
    #[default]
    Ruin,
    /// Low parapet / balustrade segment (waist height, posts and a rail).
    Parapet,
    /// Square pedestal or toppled altar block, often carrying a small prop on top.
    Plinth,
    /// Root-bound wall or hedge of roots (Verdant).
    Hedge,
    /// Impossible geometry: a floating, slightly tilted monolith (Unmaking).
    Monolith,
    /// Iron-banded forge masonry with a quench trough or bellows (Cinder).
    Forge,
}

/// Small-prop families for [`Decor::Clutter`] clusters.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ClutterKind {
    /// Pots, urns and amphorae.
    #[default]
    Urns,
    /// Crates, sacks and barrels.
    Crates,
    /// Weapon racks and discarded blades.
    WeaponRack,
    /// Ingot stacks, tongs and hammers (forge props).
    Ingots,
    /// Bones and skulls of fallen forgebearers.
    Bones,
    /// Votive candles and offering bowls.
    Candles,
    /// Stacked tomes, scrolls and a lectern.
    Tomes,
    /// Glowing mushroom clumps (Verdant).
    Mushrooms,
    /// Hanging or standing lanterns.
    Lanterns,
    /// Crystal shards and glass splinters.
    Shards,
    /// Coin heaps and chalices (treasure rooms).
    Offerings,
}

/// Presentation-only set dressing (painted-world hooks).
///
/// Units are world units on the ground plane (x east, y north); heights are world units above the
/// floor; `rot` is a [`Rot16`] facing; `variant` picks a mesh variant (the env kit takes it modulo
/// its variant count); `god` indexes `ContentDb::gods` in table order (colour of banners and trim).
///
/// **Solid** variants (see [`Decor::is_solid`]) dress gameplay obstacles: in a generated room every
/// obstacle is covered by exactly one solid decor ([`Decor::covers`] its centre), so the env kit can
/// render the decor and skip the greybox. Every other variant is visual-only and never blocks.
/// The biome reskins every variant (lava / glowing roots / starlight / raw chaos).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum Decor {
    /// Visual: glowing fissure in the floor (lava, root vein, void crack, chaos rift) from → to.
    LavaCrack { from: Vec2, to: Vec2, width: f32 },
    /// Visual: small toppled anvil / idol debris, ~1.5 u × `scale`.
    BrokenAnvil { at: Vec2, scale: f32 },
    /// Visual: light source on a short stand (fire bowl, glow-bulb cluster, star lamp, chaos flame).
    Brazier { at: Vec2 },
    /// Solid: standing column on `Obstacle::Circle { at, radius }`; `height` < 2.5 reads as a stump.
    Pillar { at: Vec2, radius: f32, height: f32 },

    // ── solid: dresses obstacles ──
    /// Solid: axis-aligned masonry block on `Obstacle::Box { center: at, half }`, `height` tall.
    Wall {
        at: Vec2,
        half: Vec2,
        height: f32,
        #[serde(default)]
        style: WallStyle,
        #[serde(default)]
        variant: u8,
    },
    /// Solid: rock / rubble mound / root knot / moon-rock / impossible polyhedron on
    /// `Obstacle::Circle { at, radius }`.
    Boulder {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        variant: u8,
    },
    /// Solid landmark: a god's statue, `height` tall, on the round plinth `Obstacle::Circle { at, radius }`,
    /// facing `rot`. `variant` is the pose (0 raised blade, 1 kneeling, 2 headless, 3 arms outstretched).
    Statue {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        god: u8,
        #[serde(default)]
        variant: u8,
    },
    /// Solid landmark: a fallen colossus head half-sunk in the floor, face turned to `rot`, on
    /// `Obstacle::Circle { at, radius }` (crown/beard spikes may overhang to ~1.3 × radius).
    ColossusHead {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        variant: u8,
    },
    /// Solid: toppled column lying from its base drum (`from`) to its broken end (`to`), `radius`
    /// thick; covers the chain of `Obstacle::Circle`s laid along the segment.
    FallenColumn { from: Vec2, to: Vec2, radius: f32 },
    /// Solid landmark (Cinder): a colossal god-forge anvil, split in two, on
    /// `Obstacle::Circle { at, radius }`, horn pointing `rot`.
    GreatAnvil {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        rot: Rot16,
    },
    /// Solid landmark (Cinder): a crucible hung on chains over the molten pit
    /// `Obstacle::Circle { at, radius }`; chains rise off-screen, the pit glows from below.
    Crucible { at: Vec2, radius: f32 },
    /// Solid landmark: a great fire bowl on a tripod (strong light) on `Obstacle::Circle { at, radius }`.
    GreatBrazier { at: Vec2, radius: f32 },
    /// Solid landmark: a monumental sealed temple gate (frame + shut doors) on
    /// `Obstacle::Box { center: at, half }`; the doors face along the box's short axis, `height` tall.
    SealedGate { at: Vec2, half: Vec2, height: f32 },
    /// Solid (Verdant): an ancient tree trunk / giant mushroom stalk on `Obstacle::Circle { at, radius }`.
    /// The canopy is presentation-only and should fade over characters.
    Tree {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        variant: u8,
    },
    /// Solid (Verdant): a fallen giant tree with its root plate at `from` and broken crown at `to`,
    /// trunk `radius` thick; covers the chain of `Obstacle::Circle`s along the segment.
    FallenTree { from: Vec2, to: Vec2, radius: f32 },
    /// Solid (Spire, Unmaking): crystal outcrop cluster `height` tall on `Obstacle::Circle { at, radius }`,
    /// leaning toward `rot`.
    Crystal {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        variant: u8,
    },
    /// Solid landmark (Spire): a broken spiral stair winding up a newel to `height`, on
    /// `Obstacle::Circle { at, radius }`; the break faces `rot`.
    SpiralStair {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        rot: Rot16,
    },
    /// Solid (Unmaking): a column standing on its capital, broken base toward the sky, `height`
    /// tall, with fragments orbiting its top; on `Obstacle::Circle { at, radius }`.
    InvertedColumn { at: Vec2, radius: f32, height: f32 },
    /// Solid (Unmaking): a standing tear in reality (vertical glowing slash, `height` tall) whose
    /// plane faces `rot`; its core is `Obstacle::Circle { at, radius }`.
    Rift {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        rot: Rot16,
    },
    /// Solid: a sunken trench of the biome liquid (slag, water, void, chaos) along the axis-aligned
    /// segment from → to, `width` wide. Covers the `Obstacle::Box`es laid along it; the gaps between
    /// them are spanned by [`Decor::Bridge`]s.
    Channel { from: Vec2, to: Vec2, width: f32 },

    // ── visual only ──
    /// Visual: a walkable stone span over a channel from bank (`from`) to bank (`to`), `width` wide.
    Bridge { from: Vec2, to: Vec2, width: f32 },
    /// Visual: a shallow walkable pool (reflecting water, star-mirror, cooled slag glass) with a low
    /// stone lip, axis-aligned `at ± half`, rounded corners.
    Pool { at: Vec2, half: Vec2 },
    /// Visual: laid floor area, axis-aligned `at ± half`. `variant`: 0 flagstones, 1 herringbone,
    /// 2 mosaic tesserae, 3 broken paving.
    Paving {
        at: Vec2,
        half: Vec2,
        #[serde(default)]
        variant: u8,
    },
    /// Visual: circular floor decal of `radius`, rotated `rot`. `variant`: 0 plaza mosaic star (gold),
    /// 1 rune ring, 2 clockface / orrery, 3 god sigil (uses `god`), 4 chaos glyph.
    FloorInlay {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        variant: u8,
        #[serde(default)]
        god: u8,
    },
    /// Visual: ground cover patch of `radius` (grass, moss, ferns, ash drifts, lichen, stardust) with
    /// tufts; `variant` picks the cover within the biome's set.
    Overgrowth {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        variant: u8,
    },
    /// Visual: a thick root or vine crawling over the floor from → to (walkable, faint glow veins).
    Roots { from: Vec2, to: Vec2, width: f32 },
    /// Visual: low scattered debris cluster of `radius` (masonry chunks, slag lumps, shards).
    Rubble {
        at: Vec2,
        radius: f32,
        #[serde(default)]
        variant: u8,
    },
    /// Visual: a cluster of `count` small props of one family within `radius`, turned `rot`.
    Clutter {
        at: Vec2,
        radius: f32,
        kind: ClutterKind,
        #[serde(default)]
        count: u8,
        #[serde(default)]
        rot: Rot16,
    },
    /// Visual: a banner in the colours of `god`, `height` tall, cloth facing `rot` (wall-hung when it
    /// stands on the rim, on a pole otherwise).
    Banner {
        at: Vec2,
        height: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        god: u8,
    },
    /// Visual: chain (or vine garland / star-string) strung between two points `height` above the floor.
    Chains { from: Vec2, to: Vec2, height: f32 },
    /// Visual: a floating fragment of `radius` hovering `height` above the floor (bobbing, casts a
    /// shadow).
    Debris {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        variant: u8,
    },
}

impl Decor {
    /// Does this decor dress a gameplay obstacle (see the type docs)?
    pub fn is_solid(&self) -> bool {
        matches!(
            self,
            Decor::Pillar { .. }
                | Decor::Wall { .. }
                | Decor::Boulder { .. }
                | Decor::Statue { .. }
                | Decor::ColossusHead { .. }
                | Decor::FallenColumn { .. }
                | Decor::GreatAnvil { .. }
                | Decor::Crucible { .. }
                | Decor::GreatBrazier { .. }
                | Decor::SealedGate { .. }
                | Decor::Tree { .. }
                | Decor::FallenTree { .. }
                | Decor::Crystal { .. }
                | Decor::SpiralStair { .. }
                | Decor::InvertedColumn { .. }
                | Decor::Rift { .. }
                | Decor::Channel { .. }
        )
    }

    /// Anchor point: `at`, or the midpoint of a from → to variant.
    pub fn anchor(&self) -> Vec2 {
        match *self {
            Decor::LavaCrack { from, to, .. }
            | Decor::FallenColumn { from, to, .. }
            | Decor::FallenTree { from, to, .. }
            | Decor::Channel { from, to, .. }
            | Decor::Roots { from, to, .. }
            | Decor::Bridge { from, to, .. }
            | Decor::Chains { from, to, .. } => (from + to) * 0.5,
            Decor::BrokenAnvil { at, .. }
            | Decor::Brazier { at }
            | Decor::Pillar { at, .. }
            | Decor::Wall { at, .. }
            | Decor::Boulder { at, .. }
            | Decor::Statue { at, .. }
            | Decor::ColossusHead { at, .. }
            | Decor::GreatAnvil { at, .. }
            | Decor::Crucible { at, .. }
            | Decor::GreatBrazier { at, .. }
            | Decor::SealedGate { at, .. }
            | Decor::Tree { at, .. }
            | Decor::Crystal { at, .. }
            | Decor::SpiralStair { at, .. }
            | Decor::InvertedColumn { at, .. }
            | Decor::Rift { at, .. }
            | Decor::Pool { at, .. }
            | Decor::Paving { at, .. }
            | Decor::FloorInlay { at, .. }
            | Decor::Overgrowth { at, .. }
            | Decor::Rubble { at, .. }
            | Decor::Clutter { at, .. }
            | Decor::Banner { at, .. }
            | Decor::Debris { at, .. } => at,
        }
    }

    /// Does this solid decor dress an obstacle centred at `p`? (Always false for visual decor.)
    pub fn covers(&self, p: Vec2) -> bool {
        let near_segment = |a: Vec2, b: Vec2, r: f32| {
            let ab = b - a;
            let t = ((p - a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
            p.distance(a + ab * t) <= r
        };
        match *self {
            Decor::Wall { at, half, .. } | Decor::SealedGate { at, half, .. } => {
                (p - at).abs().cmple(half + Vec2::splat(0.01)).all()
            }
            Decor::FallenColumn { from, to, radius } | Decor::FallenTree { from, to, radius } => {
                near_segment(from, to, radius * 0.5 + 0.01)
            }
            Decor::Channel { from, to, width } => near_segment(from, to, width * 0.5 + 0.01),
            Decor::Pillar { at, .. }
            | Decor::Boulder { at, .. }
            | Decor::Statue { at, .. }
            | Decor::ColossusHead { at, .. }
            | Decor::GreatAnvil { at, .. }
            | Decor::Crucible { at, .. }
            | Decor::GreatBrazier { at, .. }
            | Decor::Tree { at, .. }
            | Decor::Crystal { at, .. }
            | Decor::SpiralStair { at, .. }
            | Decor::InvertedColumn { at, .. }
            | Decor::Rift { at, .. } => p.distance(at) < 0.05,
            _ => false,
        }
    }
}

/// How one side of the arena border is built (presentation; the playable rectangle never changes).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RimEdge {
    /// Tall solid masonry (north backdrop 5-8 u) with gate arches cut at the exits.
    #[default]
    Wall,
    /// Ruined wall 1.5-4 u with breaches the horde pours through, rubble at its foot.
    BrokenWall,
    /// Row of columns under an architrave (6-9 u); the sky / abyss shows between them.
    Colonnade,
    /// Waist-high railing with posts and urns; the abyss drops away beyond it.
    Balustrade,
    /// Natural rock face: rising behind the north rim, dropping away on the flanks.
    Cliff,
    /// Dense roots, ferns and trunks (Verdant): dark foliage silhouettes.
    Thicket,
    /// Two or three terrace steps (~0.6 u each) rising outward, props on the landings.
    Terrace,
    /// The floor breaks into floating islands drifting into the void (Spire, Unmaking).
    Shattered,
    /// Carved edge with a glowing rune lip and a sheer drop into the abyss (the south default).
    Open,
}

/// Arena border per side. `height` scales the north backdrop (world units); `variant` picks trim.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RimStyle {
    pub north: RimEdge,
    pub east: RimEdge,
    pub south: RimEdge,
    pub west: RimEdge,
    pub height: f32,
    pub variant: u8,
}

impl Default for RimStyle {
    fn default() -> Self {
        Self {
            north: RimEdge::Wall,
            east: RimEdge::BrokenWall,
            south: RimEdge::Open,
            west: RimEdge::BrokenWall,
            height: 4.0,
            variant: 0,
        }
    }
}

/// Themed zones of a generated arena. Templates list preferred ones as `motifs`; generated rooms
/// report where each one landed in `districts` (floor material and ambient props for the env kit).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DistrictKind {
    /// The central plaza: mosaic ring, or the anvil's forge circle.
    Plaza,
    /// Open killing field: sparse boulders, ground cover, fissures.
    #[default]
    Field,
    /// A paved court framed by colonnades on two or three sides.
    ColonnadeCourt,
    /// Cinder: a collapsed forge hall around a great broken anvil.
    ForgeHall,
    /// Cinder: a slag channel crossed by stone bridges (chokepoints).
    SlagChannel,
    /// Cinder: a chain-hung crucible over a molten pit, ringed by anchor posts.
    CrucibleYard,
    /// Verdant: an overgrown cloister (colonnade square around a garden).
    Cloister,
    /// Verdant: a root-cracked terrace edged by low broken walls.
    RootTerrace,
    /// Verdant: a shallow reflecting pool flanked by columns.
    ReflectingPool,
    /// Verdant: a fallen giant tree across the district.
    FallenGiant,
    /// Spire: a broken spiral stair and its scattered steps.
    BrokenStair,
    /// Spire, Unmaking: crystal outcrops.
    CrystalGarden,
    /// Spire: a ring of floating debris around an orrery inlay.
    DebrisRing,
    /// Spire, Unmaking: a void chasm crossed by bridges.
    VoidChasm,
    /// Unmaking: the floor shattered into islands between void cracks.
    ShatteredIslands,
    /// Unmaking: standing reality rifts.
    RiftField,
    /// Unmaking: a colonnade of inverted columns at impossible spacings.
    InvertedNave,
}

/// Where a district landed: axis-aligned `min..max` in world units.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct District {
    pub kind: DistrictKind,
    pub min: Vec2,
    pub max: Vec2,
}

/// A processional lane kept free of obstacles: the capsule from → to of total `width`.
/// Presentation paves it (the path from the entrance through the plaza to each gate).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Lane {
    pub from: Vec2,
    pub to: Vec2,
    pub width: f32,
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
    /// Templates: district motifs the generator favours for this room (its signature places).
    #[serde(default)]
    pub motifs: Vec<DistrictKind>,
    /// Arena border dressing (presentation).
    #[serde(default)]
    pub rim: RimStyle,
    /// Generated rooms: the themed zones and where they landed (presentation).
    #[serde(default)]
    pub districts: Vec<District>,
    /// Generated rooms: processional lanes kept clear of obstacles (presentation paves them).
    #[serde(default)]
    pub lanes: Vec<Lane>,
}

impl RoomDef {
    /// An empty open room (used before a run starts and as a last-resort fallback).
    pub fn placeholder() -> Self {
        RoomDef {
            key: "placeholder".into(),
            biome: String::new(),
            kind: RoomKind::Combat,
            phase: Phase::P0,
            half_extents: Vec2::new(22.0, 15.0),
            obstacles: Vec::new(),
            player_spawn: Vec2::new(0.0, -10.0),
            anvil: None,
            exits: vec![Vec2::new(0.0, 14.0)],
            spawn_zones: vec![SpawnZone::Edges { margin: 1.0 }],
            encounter: EncounterDef::default(),
            decor: Vec::new(),
            motifs: Vec::new(),
            rim: RimStyle::default(),
            districts: Vec::new(),
            lanes: Vec::new(),
        }
    }
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
