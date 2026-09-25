//! Horde director v2 for biome maps (OPEN_WORLD.md §5.5–5.6): player clusters and the census,
//! the threat clock, packs spawned on a ring just outside every player's view, hold waves,
//! surges and Gate Frenzy, sleeping camps and guards, and the far cull with refund.
//!
//! State lives in the [`crate::resources::Expedition`] resource (clusters, accumulators, camps,
//! surge) and on enemies ([`crate::components::Roaming`], [`crate::components::Guard`],
//! [`crate::components::Born`]). The systems run only on Expedition maps; the legacy director
//! (and its stress mode) keeps rooms. They are registered as no-ops until lane 2C.

/// Clusters, census, threat and spawning (§5.5 steps 1–5). No-op until lane 2C.
pub fn run_horde() {}

/// Camps and guards: wake, sleep, leash home, anti-hide (§5.3, §5.5 step 6). No-op until lane 2C.
pub fn guards() {}

/// Despawn roaming enemies left far behind and refund their cost (§5.6). No-op until lane 2C.
pub fn far_cull() {}
