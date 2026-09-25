//! # gf_core — the rules of GODFORGE
//!
//! Engine-agnostic, deterministic, unit-tested game rules. Nothing in this crate may depend on
//! Bevy: the simulation (`gf_sim`), the client predictor (`gf_client`) and offline tools
//! (`gf_tools`) all call into these functions, and they must survive an engine migration.
//!
//! Module map:
//! - [`modifier`] — the single effect vocabulary shared by parts, boons, sigils, trees and recipes.
//! - [`weapon`] / [`forge`] — chassis + 4 slots compiled into a [`weapon::WeaponProfile`], anvil actions.
//! - [`aim`] — AUTO / ASSISTED / MANUAL as three policies over one targeting pipeline.
//! - [`damage`] / [`status`] / [`synergy`] — the damage model, 6 statuses, elemental combos.
//! - [`scaling`] — party-size scaling and Chaos Tier (Trials of the Forge) mutators.
//! - [`movement`] — the shared kinematic step used by the host sim *and* client prediction.
//! - [`overdrive`] / [`revive`] — co-op team meter and Soul-Tether revive state machine.

pub mod aim;
pub mod damage;
pub mod forge;
pub mod ids;
pub mod math;
pub mod modifier;
pub mod movement;
pub mod overdrive;
pub mod rarity;
pub mod revive;
pub mod rng;
pub mod scaling;
pub mod stats;
pub mod status;
pub mod synergy;
pub mod weapon;

pub use glam::{Vec2, vec2};

/// Fixed simulation rate. Everything time-based in the rules is expressed in seconds, but the
/// authoritative sim and client prediction both step at exactly this rate.
pub const SIM_HZ: u32 = 60;
/// Seconds per simulation tick.
pub const SIM_DT: f32 = 1.0 / SIM_HZ as f32;
