//! Points of interest on biome maps (OPEN_WORLD.md §5.3–5.4): hold rings (anvils, shrines,
//! reliquaries, veins), guarded clears (lairs, the Warlord), springs, watchfires and the Boss Gate.
//!
//! Every POI is a replicated, room-scoped entity with a [`Poi`] component (a map anvil also
//! carries its [`AnvilStation`]); `snapshot` turns them into `EntityKind::Poi` views and the
//! [`Expedition`] resource into `RunView.stage`. The lifecycles, Seals, rewards and the gate
//! land with lane 2B; until then the systems are registered as no-ops.

use crate::components::*;
use crate::resources::*;
use gf_content::schema::MapLayout;
use gf_core::poi::PoiKind;
use gf_engine::prelude::*;

/// Spawn one entity per `map.pois`, in site order (`Poi.index` = its index in `map.pois`).
pub fn spawn_pois(world: &mut World, map: &MapLayout) {
    for (i, site) in map.pois.iter().enumerate() {
        let net = world.resource_mut::<NetIds>().alloc();
        let mut e = world.spawn((Replicated(net), Pos(site.at), RoomScoped, Poi::from_site(i as u8, site)));
        if site.kind == PoiKind::Anvil {
            e.insert(AnvilStation::dormant());
        }
    }
}

/// POI lifecycles (Hold, Clear, Use, Touch), Seals and rewards (§5.3). Runs after
/// `anvil_update`. No-op until lane 2B.
pub fn poi_update() {}

/// The Boss Gate: Sealed → Open → Gathering → the boss arena (§5.1, §5.3). Runs after
/// `room_flow`. No-op until lane 2B.
pub fn expedition_flow() {}
