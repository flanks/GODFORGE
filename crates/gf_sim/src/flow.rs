//! Horde flow fields over a biome map's 4 u tiles (OPEN_WORLD.md §5.6), host only: integer
//! 8-neighbour Dijkstra from each player's tile, one slot per refresh (round robin), so the horde
//! funnels over bridges instead of piling up at chasm banks. State: [`crate::resources::Flow`].
//! Runs after `rebuild_grid` in the Spatial set. No-op until lane 2C.

/// Refresh one player slot's field. No-op until lane 2C.
pub fn refresh_flow() {}
