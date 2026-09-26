//! Content schema — every row type the game loads.
//!
//! Rows reference each other by string `key`. [`crate::ContentDb`] resolves keys to compact ids
//! at load time and [`crate::validate`] checks every reference, so a typo in a spreadsheet fails CI
//! instead of crashing a run.

use gf_core::aim::AimModeParams;
use gf_core::damage::{DamageType, Plating, Resistances};
use gf_core::forge::{ForgeRules, Slot};
use gf_core::modifier::Modifier;
use gf_core::movement::{Arena, MoveTuning, Obstacle};
use gf_core::overdrive::OverdriveTuning;
use gf_core::poi::PoiKind;
use gf_core::rarity::{Rarity, RarityTable};
use gf_core::revive::ReviveTuning;
use gf_core::scaling::{ChaosTierDef, PartyScaling};
use gf_core::stats::CharacterBaseStats;
use gf_core::status::{StatusKind, StatusTuning};
use gf_core::synergy::{SynergyEffect, SynergyTuning};
use gf_core::weapon::ChassisStats;
use glam::Vec2;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

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
    /// World units the camera leads the local player's move direction by (biome maps).
    pub look_ahead: f32,
}

impl Default for CameraTuning {
    fn default() -> Self {
        Self {
            pitch_deg: 55.0,
            yaw_deg: 0.0,
            view_height: [22.0, 24.0, 26.0, 28.0],
            min_character_screen_frac: 0.06,
            look_ahead: 2.5,
        }
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

// ───────────────────────────── game.ron: biome maps ─────────────────────────────

/// Horde surges (OPEN_WORLD.md §2.5): a warning, then a burst of spawns from one side.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SurgeTuning {
    /// Stage minute of the first surge.
    pub from_minute: f32,
    /// Seconds between surges (uniform in the range).
    pub interval: (f32, f32),
    /// Seconds of warning (horn, edge flash) before the surge.
    pub warn: f32,
    pub duration: f32,
    pub rate_mult: f32,
    /// Width of the arc the surge spawns in (degrees; a dot-product test, never trig).
    pub arc_deg: f32,
}

impl Default for SurgeTuning {
    fn default() -> Self {
        Self { from_minute: 3.0, interval: (85.0, 115.0), warn: 3.0, duration: 15.0, rate_mult: 2.0, arc_deg: 90.0 }
    }
}

/// Horde director v2 (§5.5–5.6): per-cluster spawning around the party, far cull, flow fields.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct HordeTuning {
    /// Hard cap on living enemies, map-wide.
    pub global_max_alive: u32,
    /// Players within this distance (single linkage) form one cluster.
    pub cluster_link: f32,
    /// Enemies within this distance of a cluster member count toward that cluster.
    pub census_bubble: f32,
    pub rate_mult: f32,
    /// Added to the camera's view height when estimating a player's view footprint.
    pub view_pad: f32,
    /// Footprint width over height.
    pub view_aspect: f32,
    /// Spawn ring: this far beyond the view footprint (min, max).
    pub ring_margin: (f32, f32),
    /// Spawns stay at least this far from every player.
    pub spawn_clear: f32,
    /// A spawn is refused when the flow distance to it exceeds this × the straight distance (+8 u).
    pub flow_detour: f32,
    /// Seconds a spawned enemy rises from the ground.
    pub emerge_time: f32,
    /// A roaming enemy farther than this from every player starts its cull timer…
    pub cull_distance: f32,
    /// … and is culled after this many seconds out there,
    pub cull_after: f32,
    /// … or at once beyond this distance.
    pub hard_cull: f32,
    /// Fraction of a culled enemy's cost refunded to its cluster.
    pub refund: f32,
    /// Ticks for one full round of flow-field refreshes (one player slot per quarter).
    pub flow_refresh_ticks: u16,
    /// A target within this many clear tiles is chased directly instead of along the flow field.
    pub direct_chase_tiles: u16,
    /// Hold-wave spawns land on this ring around the POI (min, max).
    pub event_ring: (f32, f32),
    /// Share of a hold wave's spawns that use the event ring.
    pub event_share: f32,
    pub surge: SurgeTuning,
    /// Gate Frenzy: rate multiplier and extra density once the gate opens.
    pub frenzy_rate: f32,
    pub frenzy_density: f32,
    /// Threat-clock minutes added per completed objective.
    pub heat_per_objective: f32,
}

impl Default for HordeTuning {
    fn default() -> Self {
        Self {
            global_max_alive: 400,
            cluster_link: 30.0,
            census_bubble: 36.0,
            rate_mult: 1.0,
            view_pad: 4.0,
            view_aspect: 2.0,
            ring_margin: (3.0, 9.0),
            spawn_clear: 20.0,
            flow_detour: 1.6,
            emerge_time: 0.4,
            cull_distance: 56.0,
            cull_after: 5.0,
            hard_cull: 90.0,
            refund: 1.0,
            flow_refresh_ticks: 16,
            direct_chase_tiles: 12,
            event_ring: (18.0, 26.0),
            event_share: 0.5,
            surge: SurgeTuning::default(),
            frenzy_rate: 1.4,
            frenzy_density: 25.0,
            heat_per_objective: 0.5,
        }
    }
}

/// Guards of lairs, the Warlord and camps (§5.3, §5.5): wake, aggro, leash, anti-hide.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GuardTuning {
    /// Guards spawn (idle) when a player comes this close to their home.
    pub wake: f32,
    /// Idle guards attack a player this close (or when hit).
    pub aggro: f32,
    /// An awake guard goes home when every player has been beyond this for `reset_after` s.
    pub leash: f32,
    pub reset_after: f32,
    /// Fraction of max HP regenerated per second while leashed home.
    pub regen: f32,
    /// An awake camp falls asleep (despawns, keeping what is left) with every player beyond this.
    pub sleep: f32,
    /// A guard untouched this many seconds while a player is within `hunt_radius` starts hunting.
    pub hunt_after: f32,
    pub hunt_radius: f32,
}

impl Default for GuardTuning {
    fn default() -> Self {
        Self {
            wake: 34.0,
            aggro: 16.0,
            leash: 45.0,
            reset_after: 6.0,
            regen: 0.1,
            sleep: 70.0,
            hunt_after: 20.0,
            hunt_radius: 25.0,
        }
    }
}

/// The Boss Gate (§5.3).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GateTuning {
    /// Interact and gather inside this ring.
    pub radius: f32,
    /// Seconds of Gathering (party) and with a single player.
    pub gather: f32,
    pub gather_solo: f32,
    /// Downed and reforging players are revived at this HP fraction when the party leaves.
    pub revive_frac: f32,
    /// Unworthy (forced gate): boss HP + this per missing Seal, capped at `unworthy_cap`.
    pub unworthy_hp_per_seal: f32,
    pub unworthy_cap: f32,
}

impl Default for GateTuning {
    fn default() -> Self {
        Self {
            radius: 7.0,
            gather: 10.0,
            gather_solo: 2.0,
            revive_frac: 0.5,
            unworthy_hp_per_seal: 0.25,
            unworthy_cap: 0.75,
        }
    }
}

/// How a POI is activated (§2.3).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum PoiActivation {
    /// Interact, then hold the ring: progress grows by `dt / time` while a living player is
    /// inside and decays by `decay` per second while it is empty. `time` 0 = `anvil.hold_time`.
    /// The breaker elite spawns at progress `breaker_at`.
    Hold {
        time: f32,
        decay: f32,
        wave: f32,
        #[serde(default)]
        breaker_at: Option<f32>,
    },
    /// Guards (`elites` biome elites and a pack, or the Warlord) must all die.
    Clear { elites: u8, wave: f32 },
    /// Interact once per player.
    Use,
    /// Stand in the ring for `channel` seconds.
    Touch { channel: f32 },
    /// Sealed → Open → Gathering (the Boss Gate only).
    Gate,
}

/// What completing a POI pays (§2.4, §5.4).
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum PoiReward {
    /// The anvil's forge window (charges per claimant).
    Forge,
    /// `cache_parts + extra` parts of at least `min_rarity` per present player, plus shards.
    Parts { extra: u8, min_rarity: Rarity, shards: u32 },
    /// Godshards to every player.
    Shards { amount: u32 },
    /// A boon offer from the shrine's god.
    Boon,
    /// Heal this fraction of max HP (× healing received).
    Heal { frac: f32 },
    /// Reveal the map within `radius`.
    Reveal { radius: f32 },
    /// Into the boss arena.
    Onward,
}

/// One row of `expedition.pois`: how a POI kind plays.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct PoiTuning {
    pub kind: PoiKind,
    /// Interaction / hold ring radius.
    pub radius: f32,
    /// Radius of the clearing (plaza tiles) generated around it.
    pub plaza: f32,
    pub activation: PoiActivation,
    pub reward: PoiReward,
}

impl PoiTuning {
    /// The shipped POI rows (OPEN_WORLD.md §4.2).
    pub fn defaults() -> Vec<PoiTuning> {
        use PoiActivation::*;
        let row = |kind, radius, plaza, activation, reward| PoiTuning { kind, radius, plaza, activation, reward };
        vec![
            row(
                PoiKind::Anvil,
                4.5,
                10.0,
                Hold { time: 0.0, decay: 0.0, wave: 1.5, breaker_at: Some(0.6) },
                PoiReward::Forge,
            ),
            row(
                PoiKind::Shrine,
                4.0,
                8.0,
                Hold { time: 12.0, decay: 0.05, wave: 1.2, breaker_at: None },
                PoiReward::Boon,
            ),
            row(
                PoiKind::Reliquary,
                4.0,
                8.0,
                Hold { time: 15.0, decay: 0.05, wave: 1.3, breaker_at: None },
                PoiReward::Parts { extra: 0, min_rarity: Rarity::Common, shards: 0 },
            ),
            row(
                PoiKind::Vein,
                4.0,
                8.0,
                Hold { time: 20.0, decay: 0.03, wave: 1.4, breaker_at: Some(0.5) },
                PoiReward::Shards { amount: 18 },
            ),
            row(
                PoiKind::Lair,
                14.0,
                14.0,
                Clear { elites: 2, wave: 0.8 },
                PoiReward::Parts { extra: 1, min_rarity: Rarity::Common, shards: 10 },
            ),
            row(
                PoiKind::Warlord,
                18.0,
                18.0,
                Clear { elites: 0, wave: 0.6 },
                PoiReward::Parts { extra: 0, min_rarity: Rarity::Rare, shards: 20 },
            ),
            row(PoiKind::Spring, 3.0, 6.0, Use, PoiReward::Heal { frac: 0.4 }),
            row(PoiKind::Watchfire, 2.5, 5.0, Touch { channel: 1.0 }, PoiReward::Reveal { radius: 80.0 }),
            row(PoiKind::Gate, 7.0, 14.0, Gate, PoiReward::Onward),
        ]
    }
}

/// Split-party rules (§5.9).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CoopTuning {
    /// "Present" at a POI's completion: within its radius + this.
    pub present_pad: f32,
    /// Personal part rolls only for players this close to the kill.
    pub loot_share_radius: f32,
    /// With no living ally this close, a downed player's timer is clamped to `hopeless_downed`.
    pub tether_hopeless: f32,
    pub hopeless_downed: f32,
    /// A reforged player appears this far from the nearest living ally.
    pub reforge_offset: f32,
    /// Parts do not age while their owner is this close.
    pub part_owner_near: f32,
    /// POI completion pulls pickups within this radius to present players.
    pub vacuum_radius: f32,
    /// Forge Aegis: enemies are pushed out of a Hot anvil's radius + this.
    pub aegis_pad: f32,
}

impl Default for CoopTuning {
    fn default() -> Self {
        Self {
            present_pad: 8.0,
            loot_share_radius: 36.0,
            tether_hopeless: 45.0,
            hopeless_downed: 3.0,
            reforge_offset: 2.0,
            part_owner_near: 40.0,
            vacuum_radius: 40.0,
            aegis_pad: 1.0,
        }
    }
}

/// Stride: a travel speed self-buff out of combat (§5.9).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct StrideTuning {
    /// Seconds without taking damage, firing or an enemy within `calm_radius`.
    pub delay: f32,
    pub mult: f32,
    pub calm_radius: f32,
}

impl Default for StrideTuning {
    fn default() -> Self {
        Self { delay: 2.5, mult: 1.25, calm_radius: 12.0 }
    }
}

/// Fog of war (client presentation, §7.3).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct FogTuning {
    /// Fog grid cell (world units).
    pub cell: f32,
    /// Radius revealed around each player, and its soft edge.
    pub reveal: f32,
    pub feather: f32,
    /// POI beacons are sighted from this far through the fog.
    pub beacon_sight: f32,
}

impl Default for FogTuning {
    fn default() -> Self {
        Self { cell: 2.0, reveal: 32.0, feather: 6.0, beacon_sight: 45.0 }
    }
}

/// Per-client interest management (§6.3).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct InterestTuning {
    /// Entities become relevant within `radius_in` and stay relevant until beyond `radius_out`.
    pub radius_in: f32,
    pub radius_out: f32,
    /// Positional events farther than this are not sent.
    pub event_radius: f32,
    /// Enemies beyond this update every other snapshot.
    pub far_lod: f32,
}

impl Default for InterestTuning {
    fn default() -> Self {
        Self { radius_in: 44.0, radius_out: 52.0, event_radius: 50.0, far_lod: 30.0 }
    }
}

/// `game.ron: expedition` — how biome maps play (OPEN_WORLD.md §4.2). Every field has a default.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ExpeditionTuning {
    pub horde: HordeTuning,
    pub guards: GuardTuning,
    pub gate: GateTuning,
    /// One row per POI kind.
    pub pois: Vec<PoiTuning>,
    /// Seconds without objective progress (short of the required Seals) before the Forge whispers
    /// a hint toward the nearest seal-bearing POI.
    pub stall_hint_secs: f32,
    pub ember_per_objective: f32,
    pub coop: CoopTuning,
    pub stride: StrideTuning,
    pub fog: FogTuning,
    pub interest: InterestTuning,
}

impl Default for ExpeditionTuning {
    fn default() -> Self {
        Self {
            horde: HordeTuning::default(),
            guards: GuardTuning::default(),
            gate: GateTuning::default(),
            pois: PoiTuning::defaults(),
            stall_hint_secs: 150.0,
            ember_per_objective: 3.0,
            coop: CoopTuning::default(),
            stride: StrideTuning::default(),
            fog: FogTuning::default(),
            interest: InterestTuning::default(),
        }
    }
}

impl ExpeditionTuning {
    /// The tuning row of POI `kind` (validation guarantees one per kind in shipped content).
    pub fn poi(&self, kind: PoiKind) -> Option<&PoiTuning> {
        self.pois.iter().find(|p| p.kind == kind)
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
    /// Biome maps: horde director v2, POIs, the gate, split-party rules, fog and interest.
    pub expedition: ExpeditionTuning,
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
    /// A whole biome map (OPEN_WORLD.md): generated by `worldgen` from the template's
    /// [`ExpeditionDef`], explored for Seals until the Boss Gate opens.
    Expedition,
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
///
/// A visual prop (`Brazier`, `BrokenAnvil`, `Clutter`) whose anchor lies inside a solid `Wall`
/// stands on top of that block (fire bowls on plinths, anvils on forge stations). A `Banner` on
/// the north rim hangs from the backdrop wall, one at an `Arch`'s midpoint hangs from its lintel.
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
    /// Solid: a freestanding arch spanning a lane. Its two square piers are the obstacles
    /// `Obstacle::Box { center: from | to, half: (pier, pier) }`; the lintel joins them `height`
    /// above the floor and the passage between them stays walkable. `variant`: 0 intact, 1 broken
    /// (lintel fallen, one pier shorter).
    Arch {
        from: Vec2,
        to: Vec2,
        pier: f32,
        height: f32,
        #[serde(default)]
        variant: u8,
    },
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
    /// Solid landmark ("Fallen Arms", biome maps): a colossal broken god-weapon driven into the
    /// ground, `height` tall, leaning toward `rot`, its impact crater on `Obstacle::Circle { at, radius }`.
    /// `variant`: 0 sword, 1 hammer, 2 spear, 3 bow, 4 cannon.
    FallenWeapon {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        variant: u8,
    },

    // ── visual only ──
    /// Visual: a walkable stone span over a channel from bank (`from`) to bank (`to`), `width` wide.
    Bridge { from: Vec2, to: Vec2, width: f32 },
    /// Visual: a shallow walkable pool (reflecting water, star-mirror, cooled slag glass) with a low
    /// stone lip, axis-aligned `at ± half`, rounded corners.
    Pool { at: Vec2, half: Vec2 },
    /// Visual: laid floor area, axis-aligned `at ± half`. `variant`: 0 flagstones, 1 herringbone,
    /// 2 mosaic tesserae, 3 broken paving (an island of at most 5 u half is painted as a frayed
    /// oval, its courses turned by its own angle).
    Paving {
        at: Vec2,
        half: Vec2,
        #[serde(default)]
        variant: u8,
    },
    /// Visual (biome maps): a floor-story mark painted into the open ground, never a mesh: an
    /// fbm-warped oval of `half` (along `rot`, across it), e.g. an old fire's burn scar, a cooled
    /// slag spill or a soot fan (OPEN_WORLD.md §3.6.7).
    FloorMark {
        at: Vec2,
        half: Vec2,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        kind: FloorMarkKind,
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
    /// Visual (biome maps): a waymark where a road leaves a crossroads or a clearing: a post whose
    /// pennant, in the colour of the objective the road leads to (`kind`), points along the road
    /// (`rot`), so every junction says where its ways go.
    Waymark { at: Vec2, rot: Rot16, kind: PoiKind },
    /// Visual: a floating fragment of `radius` hovering `height` above the floor (bobbing, casts a
    /// shadow).
    Debris {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        variant: u8,
    },
    /// Visual (biome maps): framing mass that never blocks (OPEN_WORLD.md §3.6.5). `Lip`: a rock
    /// or ruin fragment on the cliff lip, past the walkable edge. `Backdrop`: a tall silhouette
    /// rising from the void beyond a far (north, east or west) shore. `Foreground`: a low dark
    /// shape in the void off a camera-side (south) shore. `radius` is its footprint, `height` its
    /// top above the floor; `rot` turns it and `variant` picks its shape.
    Scenery {
        at: Vec2,
        radius: f32,
        height: f32,
        #[serde(default)]
        kind: SceneryKind,
        #[serde(default)]
        rot: Rot16,
        #[serde(default)]
        variant: u8,
    },
}

/// What a [`Decor::FloorMark`] shows (painted by the floor shader; the index is its paint slot).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FloorMarkKind {
    /// An old fire: a charred heart, a ring of pale ash, soot streaks and a few embers.
    #[default]
    Burn,
    /// A cooled slag spill: glossy black plates, pale seams, a crust ridge at its edge.
    Slag,
    /// An ash drift, rippled across the wind (`rot`).
    Ash,
    /// A collapsed floor: a sunken heart, a crack web and scattered masonry chips.
    Collapse,
    /// Rust stains and two drag ruts along `rot`.
    Rust,
    /// A soot fan sprayed along `rot` from its back end (below a chimney or a wall).
    Soot,
}

impl FloorMarkKind {
    /// Paint slot index (0..=5), in declaration order.
    pub fn index(self) -> u8 {
        self as u8
    }
}

/// Where a [`Decor::Scenery`] piece frames the map.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SceneryKind {
    /// On the cliff lip, half over the drop.
    #[default]
    Lip,
    /// A tall silhouette rising from the abyss beyond a far shore.
    Backdrop,
    /// A low, near-black shape in the void between the camera and a south shore.
    Foreground,
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
                | Decor::Arch { .. }
                | Decor::Tree { .. }
                | Decor::FallenTree { .. }
                | Decor::Crystal { .. }
                | Decor::SpiralStair { .. }
                | Decor::InvertedColumn { .. }
                | Decor::Rift { .. }
                | Decor::Channel { .. }
                | Decor::FallenWeapon { .. }
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
            | Decor::Arch { from, to, .. }
            | Decor::Chains { from, to, .. } => (from + to) * 0.5,
            Decor::Waymark { at, .. } => at,
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
            | Decor::FallenWeapon { at, .. }
            | Decor::Pool { at, .. }
            | Decor::Paving { at, .. }
            | Decor::FloorMark { at, .. }
            | Decor::FloorInlay { at, .. }
            | Decor::Overgrowth { at, .. }
            | Decor::Rubble { at, .. }
            | Decor::Clutter { at, .. }
            | Decor::Banner { at, .. }
            | Decor::Debris { at, .. }
            | Decor::Scenery { at, .. } => at,
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
            Decor::Arch { from, to, .. } => p.distance(from) < 0.05 || p.distance(to) < 0.05,
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
            | Decor::Rift { at, .. }
            | Decor::FallenWeapon { at, .. } => p.distance(at) < 0.05,
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
    /// Biome maps: the roads.
    #[serde(default)]
    pub lanes: Vec<Lane>,
    /// Expedition templates only: the biome map's configuration.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expedition: Option<Box<ExpeditionDef>>,
    /// Generated biome maps only (never authored; not serialized): tiles, regions, roads, POIs,
    /// camps and pits, shared as one `Arc` by the sim, the client and bots.
    #[serde(skip)]
    pub map: Option<Arc<MapLayout>>,
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
            expedition: None,
            map: None,
        }
    }

    /// The collision world every peer (host, client prediction, bots, validation) derives from
    /// this layout: its obstacles, plus a biome map's pits (void and liquid tiles).
    pub fn arena(&self) -> Arena {
        let pits = self.map.as_ref().map_or_else(Vec::new, |m| m.pits.clone());
        Arena::new(self.half_extents, self.obstacles.clone(), pits)
    }
}

// ───────────────────────────── biome maps ─────────────────────────────

/// Terrain barrier between two adjacent regions (§3.2 step 7).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BarrierKind {
    /// Void tiles, 2 thick: a drop into the abyss (a pit; shots fly over).
    Chasm,
    /// Liquid tiles, 2–3 thick: slag, black water, star-sea, chaos (a pit; shots fly over).
    River,
    /// A line of solid wall blocks in the biome's style.
    Wall,
    /// A chain of boulders.
    Ridge,
}

/// Grand monuments that give a map its skyline (§3.5), in the room grammar's vocabulary.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MapMark {
    Statue,
    GreatBrazier,
    SealedGate,
    Tree,
    SpiralStair,
    InvertedColumn,
    Rift,
    Crystal,
    ColossusHead,
    GreatAnvil,
    Crucible,
    /// A colossal broken god-weapon ([`Decor::FallenWeapon`]).
    FallenWeapon,
}

/// A region theme: what one Voronoi region of the map looks like and is built from.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct RegionTheme {
    pub key: String,
    /// Shown in the region banner ("The Slag Flats").
    pub name: String,
    pub weight: f32,
    /// Room-grammar composition pool for this region's edge slots (pick weights).
    pub districts: Vec<(DistrictKind, f32)>,
    /// Share of the region's open fields left bare (0..=1); every other field holds one kiting
    /// anchor (OPEN_WORLD.md §3.6.3).
    pub fields: f32,
    /// Ceiling on colliding cover of the region's interior land (0.0..=0.08): anchors and story
    /// clusters that would push past it are skipped (§3.6.9).
    pub cover: f32,
    /// Compositions per region, on edge slots only (their backs to the coast or a border).
    #[serde(default = "RegionTheme::default_comps")]
    pub comps: u8,
    /// Story clusters per region, on its frame band (a pit or barrier-wall edge).
    #[serde(default = "RegionTheme::default_story")]
    pub story: u8,
    /// Share of the region's void shore that is framed (lip pieces, coast anchors, silhouettes).
    #[serde(default = "RegionTheme::default_frame")]
    pub frame: f32,
    /// `#RRGGBB`: the floor vertex tint and the minimap land colour.
    pub tint: String,
    pub map_color: String,
    /// May host the Landing.
    #[serde(default)]
    pub open: bool,
    /// Camp packs in this region (the biome's swarm when empty).
    #[serde(default)]
    pub camp_pool: Vec<WeightedKey>,
    /// Names the regions of this theme take on one map, in turn (`name` when empty), so a map
    /// with four slag flats never shows the same banner twice.
    #[serde(default)]
    pub names: Vec<String>,
    /// How the region's open ground is painted (presentation only: generation never reads it).
    #[serde(default)]
    pub ground: GroundRecipe,
    /// Floor-story marks painted over the region's open ground (pick weights; none when empty):
    /// what happened there, told in paint instead of meshes (§3.6.7).
    #[serde(default)]
    pub marks: Vec<(FloorMarkKind, f32)>,
}

impl RegionTheme {
    fn default_comps() -> u8 {
        2
    }
    fn default_story() -> u8 {
        1
    }
    fn default_frame() -> f32 {
        0.5
    }

    /// The name of the `k`-th region of this theme on a map.
    pub fn region_name(&self, k: u8) -> &str {
        match self.names.len() {
            0 => &self.name,
            n => &self.names[k as usize % n],
        }
    }
}

/// A region theme's ground paint (the client blends it across region borders).
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct GroundRecipe {
    /// Paving coverage offset: −0.5 bare earth … +0.5 fully paved.
    pub paving: f32,
    /// Ash drifts with wind ripples (0..=1).
    pub ash: f32,
    /// Black glassy slag sheets with pale seams over the bare ground (0..=1).
    pub glass: f32,
}

/// The coastline: void tiles eaten in from the map rectangle (tile units).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CoastDef {
    /// Tiles that are always void along the border.
    pub depth: u8,
    /// Noise amplitude on top of `depth` (bays and headlands).
    pub amp: u8,
    /// Noise lattice period.
    pub period: u8,
}

impl Default for CoastDef {
    fn default() -> Self {
        Self { depth: 2, amp: 3, period: 6 }
    }
}

/// Barriers between adjacent regions.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BarrierDef {
    /// Chance a pair of adjacent regions is separated by a barrier.
    pub chance: f32,
    /// Barrier kinds and pick weights.
    pub kinds: Vec<(BarrierKind, f32)>,
}

impl Default for BarrierDef {
    fn default() -> Self {
        Self { chance: 0.45, kinds: Vec::new() }
    }
}

/// The road network between region sites.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RoadDef {
    pub width: f32,
    /// Chance each non-tree region adjacency also gets a road (loops).
    pub loop_chance: f32,
    /// Width of the pass (bridge or breach) where a road crosses a barrier.
    pub pass_width: f32,
}

impl Default for RoadDef {
    fn default() -> Self {
        Self { width: 6.0, loop_chance: 0.3, pass_width: 8.0 }
    }
}

/// How a biome map is composed (OPEN_WORLD.md §3.6): where compositions stand, what keeps clear,
/// how the frame, vignettes and light pools are dressed. Every field defaults to the shipped
/// composition, so templates may omit the block.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ComposeDef {
    /// Slots per region: edge slots first (compositions), then open fields.
    pub slots: u8,
    /// Tiles: an edge slot's back lies within this many tiles (+1) of the coast or a border.
    pub edge_band: u8,
    /// Share of the back side's tiles that must touch that edge.
    pub edge_share: f32,
    /// Free floor (u) kept on a composition's three open sides.
    pub slot_clear: f32,
    /// Compositions, stories and anchors keep this far (u) from every pass.
    pub pass_clear: f32,
    /// Nothing colliding within road half-width + this (u) (`Builder.lane_pad`), except the
    /// pieces laid with the mask lifted (pass arches, POI set pieces, hub monuments).
    pub road_clear: f32,
    /// A boulder anchor's radius range (u).
    pub anchor_radius: (f32, f32),
    /// Obstacle-free floor (u) around a field anchor.
    pub anchor_clear: f32,
    /// Chance of an arch where a road crosses an open region border (walls and ridges: always;
    /// bridges: never).
    pub pass_arches: f32,
    /// Arches where roads enter POI clearings.
    pub entry_arches: bool,
    /// Chance per 22–28 u road slot of a tall shoulder piece (0 = none).
    pub road_silhouettes: f32,
    /// Length range (u) of a framed run of shore.
    pub frame_run: (f32, f32),
    /// Shore left unframed (u) around roads, bridges, plazas and passes.
    pub frame_gap: f32,
    /// Framed shore (u) per colliding coast anchor, at most.
    pub coast_anchor_every: f32,
    /// Land (u²) per vignette, at most.
    pub vignette_area: f32,
    /// Distance (u) between vignettes, at least.
    pub vignette_spacing: f32,
    /// Glowing fissures only this close (u) to heat (a crucible, great anvil, channel, liquid or a
    /// POI heart).
    pub heat_reach: f32,
    /// Every land lattice point (11 × 7 u) has a warm source inside this box (u), centred on it.
    pub light_box: (f32, f32),
    /// Floor-story marks stand on a jittered lattice of this step (u) over each region's open
    /// ground (0 = none).
    pub mark_spacing: f32,
    /// A mark's half length along its facing (u); across it is 55–100 % of that.
    pub mark_size: (f32, f32),
}

impl Default for ComposeDef {
    fn default() -> Self {
        Self {
            slots: 5,
            edge_band: 1,
            edge_share: 0.75,
            slot_clear: 8.0,
            pass_clear: 10.0,
            road_clear: 4.0,
            anchor_radius: (1.6, 2.6),
            anchor_clear: 8.0,
            pass_arches: 1.0,
            entry_arches: false,
            road_silhouettes: 0.0,
            frame_run: (8.0, 24.0),
            frame_gap: 10.0,
            coast_anchor_every: 12.0,
            vignette_area: 2000.0,
            vignette_spacing: 18.0,
            heat_reach: 9.0,
            light_box: (30.0, 18.0),
            mark_spacing: 16.5,
            mark_size: (2.2, 5.5),
        }
    }
}

/// How many POIs of a kind the map places, and the Seals each is worth.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct PoiQuota {
    pub kind: PoiKind,
    pub count: u8,
    #[serde(default)]
    pub seals: u8,
}

/// Dormant enemy camps scattered over the map.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct CampDef {
    /// One camp per this many square units of land.
    pub per_area: f32,
    /// Pack size range.
    pub pack: (u8, u8),
    /// Chance of an elite leader.
    pub elite_chance: f32,
    /// Shard pile dropped when cleared (range).
    pub shards: (u16, u16),
}

impl Default for CampDef {
    fn default() -> Self {
        Self { per_area: 4000.0, pack: (6, 12), elite_chance: 0.2, shards: (8, 15) }
    }
}

/// One row of the threat clock (§2.5), for one solo cluster. Rows interpolate linearly.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct ThreatKey {
    pub minute: f32,
    /// Living enemies the director keeps around the cluster.
    pub density: f32,
    /// Spawn weight per second.
    pub rate: f32,
    pub elite_chance: f32,
    pub hp_mult: f32,
}

/// An Expedition template's biome-map configuration (`rooms.ron`, OPEN_WORLD.md §4.3).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ExpeditionDef {
    /// Map size in world units: multiples of 8, at most 480 × 480 (`QPos` reaches ±256 u).
    pub size: Vec2,
    /// Region grid (jittered sites), columns × rows.
    pub regions: (u8, u8),
    pub themes: Vec<RegionTheme>,
    /// The Landing region's theme (an `open` one).
    pub start_theme: String,
    pub coast: CoastDef,
    pub barriers: BarrierDef,
    pub roads: RoadDef,
    pub pois: Vec<PoiQuota>,
    pub camps: CampDef,
    /// Composition and negative space (§3.6).
    pub compose: ComposeDef,
    /// Grand monuments for regions without a major POI (pick weights).
    pub landmarks: Vec<(MapMark, f32)>,
    /// Seals that open the Boss Gate (the Warlord counts its own).
    pub seals_required: u8,
    pub gate_requires_warlord: bool,
    /// Stage minute at which the gate is forced open (Unworthy).
    pub gate_force_minute: f32,
    /// The biome boss's HP multiplier when the party walks through the gate.
    pub boss_hp_mult: f32,
    /// Threat-clock minute the biome starts at (carries the madness forward across biomes).
    pub threat_start_minute: f32,
    pub threat: Vec<ThreatKey>,
}

impl Default for ExpeditionDef {
    fn default() -> Self {
        Self {
            size: Vec2::new(432.0, 272.0),
            regions: (5, 3),
            themes: Vec::new(),
            start_theme: String::new(),
            coast: CoastDef::default(),
            barriers: BarrierDef::default(),
            roads: RoadDef::default(),
            pois: Vec::new(),
            camps: CampDef::default(),
            compose: ComposeDef::default(),
            landmarks: Vec::new(),
            seals_required: 6,
            gate_requires_warlord: true,
            gate_force_minute: 12.0,
            boss_hp_mult: 1.35,
            threat_start_minute: 0.0,
            threat: Vec::new(),
        }
    }
}

impl ExpeditionDef {
    /// Total POIs of `kind` the quotas ask for.
    pub fn quota(&self, kind: PoiKind) -> u32 {
        self.pois.iter().filter(|q| q.kind == kind).map(|q| q.count as u32).sum()
    }

    /// Seals the quotas make available on the map.
    pub fn seals_available(&self) -> u32 {
        self.pois.iter().map(|q| q.seals as u32 * q.count as u32).sum()
    }

    /// Index of the theme with `key`.
    pub fn theme(&self, key: &str) -> Option<usize> {
        self.themes.iter().position(|t| t.key == key)
    }
}

/// What a map tile is. Land is `Ground | Road | Plaza | Bridge`; `Void` and `Liquid` are pits
/// (walkers are blocked, shots fly over).
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TileKind {
    /// Off the map or a chasm: a drop into the abyss.
    Void,
    /// Open land, where room-grammar compositions may stand.
    #[default]
    Ground,
    /// A paved road (kept clear of obstacles).
    Road,
    /// A POI clearing or the Landing.
    Plaza,
    /// A span over a pit where a road crosses it.
    Bridge,
    /// A river of the biome liquid.
    Liquid,
}

impl TileKind {
    /// Walkable terrain (obstacles aside).
    pub const fn is_land(self) -> bool {
        matches!(self, TileKind::Ground | TileKind::Road | TileKind::Plaza | TileKind::Bridge)
    }

    /// Blocks walkers: `Void` and `Liquid`.
    pub const fn is_pit(self) -> bool {
        !self.is_land()
    }
}

/// The map's 4 u tile raster: land mask and region ownership, row-major from `origin` (the map's
/// south-west corner), `x` east and `y` north.
#[derive(Clone, Debug, PartialEq)]
pub struct TileGrid {
    pub w: u16,
    pub h: u16,
    /// Tile side (world units, 4.0).
    pub size: f32,
    pub origin: Vec2,
    pub kind: Vec<TileKind>,
    /// Owning region per tile.
    pub region: Vec<u8>,
}

impl TileGrid {
    /// Side of a map tile (world units).
    pub const TILE: f32 = 4.0;

    /// A `w × h` grid of `fill` tiles, all in region 0.
    pub fn new(origin: Vec2, w: u16, h: u16, fill: TileKind) -> Self {
        let n = w as usize * h as usize;
        Self { w, h, size: Self::TILE, origin, kind: vec![fill; n], region: vec![0; n] }
    }

    #[inline]
    pub fn index(&self, x: u16, y: u16) -> usize {
        y as usize * self.w as usize + x as usize
    }

    /// Tile containing `p`, if it is on the grid.
    pub fn tile_of(&self, p: Vec2) -> Option<(u16, u16)> {
        let t = ((p - self.origin) / self.size).floor();
        (t.x >= 0.0 && t.y >= 0.0 && t.x < self.w as f32 && t.y < self.h as f32).then_some((t.x as u16, t.y as u16))
    }

    /// Centre of tile (`x`, `y`) in world units.
    pub fn center(&self, x: u16, y: u16) -> Vec2 {
        self.origin + (Vec2::new(x as f32, y as f32) + Vec2::splat(0.5)) * self.size
    }

    /// Terrain under `p` (`Void` off the grid).
    pub fn kind_at(&self, p: Vec2) -> TileKind {
        self.tile_of(p).map_or(TileKind::Void, |(x, y)| self.kind[self.index(x, y)])
    }
}

/// One Voronoi region of the map.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Region {
    /// Index into the template's `themes`.
    pub theme: u8,
    /// The region's site (its centre of gravity for roads and major POIs).
    pub site: Vec2,
    /// The grand monument standing at the site, if any.
    pub landmark: Option<MapMark>,
    /// Which of its theme's names this region carries ([`RegionTheme::region_name`]).
    pub name: u8,
}

/// Where a road crosses a barrier: a bridge over a pit or a breach in a wall (a chokepoint).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Pass {
    pub at: Vec2,
    /// Direction the road runs through it.
    pub along: Rot16,
    pub width: f32,
    pub kind: BarrierKind,
}

/// A generated POI.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct PoiSite {
    pub kind: PoiKind,
    pub at: Vec2,
    /// Interaction ring radius (from `expedition.pois`).
    pub radius: f32,
    pub seals: u8,
    pub region: u8,
    /// Shrines: the god (index into the gods table) whose boon it grants.
    pub god: Option<u8>,
    /// Warlords and lairs: the guard enemy fixed at generation (index into the enemies table).
    pub guard: Option<u16>,
}

/// A dormant enemy camp.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CampSite {
    pub at: Vec2,
    /// Pack enemy (index into the enemies table).
    pub enemy: u16,
    pub count: u8,
    /// Elite leader, if any (index into the enemies table).
    pub elite: Option<u16>,
    /// Shard pile dropped when cleared.
    pub shards: u16,
}

/// A generated biome map (`gf_content::worldgen`). Shared as `Arc` by the sim, the client and bots.
#[derive(Clone, Debug, PartialEq)]
pub struct MapLayout {
    pub seed: u32,
    /// FNV-64 over the quantized obstacles, pits, POI sites, player spawn and gate: every peer
    /// compares it with the host's (`RunView.layout_hash`).
    pub hash: u64,
    pub tiles: TileGrid,
    pub regions: Vec<Region>,
    /// The road network (also copied to `RoomDef.lanes`).
    pub roads: Vec<Lane>,
    pub passes: Vec<Pass>,
    /// Walker-only blockers merged from `Void` / `Liquid` tile runs.
    pub pits: Vec<Obstacle>,
    pub pois: Vec<PoiSite>,
    /// Index of the Boss Gate in `pois`.
    pub gate: u8,
    pub camps: Vec<CampSite>,
    /// POI placements that needed relaxed spacing.
    pub relaxed: u8,
    /// Reachability carves (obstacles removed or pits bridged) the generator had to make.
    pub repairs: u8,
}

impl MapLayout {
    /// The Boss Gate's site.
    pub fn gate_site(&self) -> Option<&PoiSite> {
        self.pois.get(self.gate as usize)
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
