//! # gf_engine — engine isolation
//!
//! Bevy churn is the #1 schedule risk (§14). This crate is the **only** one that depends on
//! `bevy`; everything else imports engine types through [`prelude`] and calls version-sensitive
//! APIs through the adapters here. A Bevy bump changes one line in the workspace manifest, and
//! fallout is fixed in this crate first.
//!
//! - Always available: ECS, app, math, logging (the headless simulation needs nothing else).
//! - `client` feature: renderer, UI, input devices and the client adapters in [`client`].

pub use bevy;

/// Engine types used across the project.
pub mod prelude {
    pub use bevy::ecs::schedule::{ScheduleLabel, SingleThreadedExecutor};
    pub use bevy::prelude::*;
}

use prelude::*;

/// A schedule that runs its systems one at a time in a fixed order. The authoritative simulation
/// uses these so weekly seeds replay bit-identically (server-validated leaderboards, §11.5).
pub fn deterministic_schedule(label: impl ScheduleLabel) -> Schedule {
    let mut schedule = Schedule::new(label);
    schedule.set_executor(SingleThreadedExecutor::new());
    schedule
}

#[cfg(feature = "client")]
pub mod client;
