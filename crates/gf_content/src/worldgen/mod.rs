//! Biome maps (OPEN_WORLD.md §3): one huge generated map per biome, built as a room of kind
//! [`RoomKind::Expedition`] from `(template, seed)` exactly like a procedural arena. The host
//! replicates `(room, room_seed, room_serial)` and every client and bot rebuilds the same map with
//! [`crate::procgen::resolve_room`].
//!
//! ## Pipeline (§3.2)
//!
//! 1. **Regions** ([`regions`]): a jittered grid of sites, domain-warped Voronoi on the 4 u tile
//!    grid, the coast eaten in from the rectangle (bays and headlands, a calm Landing edge), region
//!    adjacency, each region's site at its most interior tile, the Landing, themes and the gate
//!    region (the most hops from the Landing).
//! 2. **Roads** ([`roads`]): a Kruskal tree over region adjacency plus loops, each road running
//!    site → pass → site with one jittered bend per leg, and the road distance of every region
//!    from the Landing.
//! 3. **POIs** ([`pois`]): majors on region sites by road distance band, minors on secondary sites
//!    along the roads (Reliquaries and Veins off the road with a spur), Springs, Watchfires, and a
//!    crossroads hub with a grand monument on every other site.
//! 4. **Barriers** ([`barriers`]): chasms and rivers as pit bands along region borders, bridged
//!    wherever a road crosses; walls and ridges are laid by the composer.
//! 5. **Composition** ([`compose`]): the room grammar's [`crate::procgen::Builder`] in map mode:
//!    POI clearings, barrier walls and ridges, arches at passes, then every region's slots filled
//!    with its theme's compositions, a density top-up and dressing.
//! 6. **Camps** ([`camps`]), **reachability repair** ([`repair`]) and the merged **pits**.
//!
//! **Determinism** (§3.1, enforced in review): integer `GfRng` output and `+ − × ÷ √` only (no
//! trigonometry, `exp`, `powf` or `mul_add`; facings are `Rot16`), integer value noise, no
//! `HashMap`/`HashSet` iteration, integer sort keys, and every coordinate written into obstacles,
//! pits, POIs or camps quantized to 1/8 u. Generation reads only content, never the build phase.

mod barriers;
mod camps;
mod compose;
mod pois;
mod regions;
mod repair;
mod roads;
mod tiles;

use crate::db::ContentDb;
use crate::procgen::{Biome, key_hash, q};
use crate::schema::*;
use gf_core::movement::Obstacle;
use gf_core::poi::PoiKind;
use gf_core::rng::GfRng;
use glam::Vec2;
use std::sync::Arc;

/// Side of a map tile (world units).
pub const TILE: f32 = TileGrid::TILE;
/// Largest map half extent (`QPos` reaches ±256 u; validation holds maps to ±240).
const MAX_HALF: f32 = 240.0;
/// Radius of the Landing plaza.
pub(crate) const LANDING_R: f32 = 10.0;
/// Radius of a crossroads hub (a region site without a major POI, around its grand monument).
pub(crate) const HUB_R: f32 = 10.0;

const FNV_OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

/// FNV-64 over the quantized ints (1/8 u) of the obstacles, pits, POI sites, player spawn and gate
/// index: the value `RunView.layout_hash` carries so every peer can check it rebuilt the host's map.
pub fn layout_hash(obstacles: &[Obstacle], pits: &[Obstacle], pois: &[PoiSite], spawn: Vec2, gate: u8) -> u64 {
    let mut h = FNV_OFFSET;
    let mut put = |v: i64| {
        for b in v.to_le_bytes() {
            h = (h ^ b as u64).wrapping_mul(FNV_PRIME);
        }
    };
    let q8 = |v: f32| (v * 8.0).round() as i64;
    for list in [obstacles, pits] {
        put(list.len() as i64);
        for o in list {
            match *o {
                Obstacle::Circle { center, radius } => {
                    put(0);
                    put(q8(center.x));
                    put(q8(center.y));
                    put(q8(radius));
                }
                Obstacle::Box { center, half } => {
                    put(1);
                    put(q8(center.x));
                    put(q8(center.y));
                    put(q8(half.x));
                    put(q8(half.y));
                }
            }
        }
    }
    put(pois.len() as i64);
    for p in pois {
        put(p.kind as i64);
        put(q8(p.at.x));
        put(q8(p.at.y));
        put(q8(p.radius));
        put(p.seals as i64);
        put(p.region as i64);
        put(p.god.map_or(-1, i64::from));
        put(p.guard.map_or(-1, i64::from));
    }
    put(q8(spawn.x));
    put(q8(spawn.y));
    put(gate as i64);
    h
}

// ───────────────────────────── generator state ─────────────────────────────

/// One region while the map is being generated.
#[derive(Clone, Debug)]
pub(crate) struct RegionGen {
    /// The Voronoi seed (tile coordinates).
    pub(crate) seed: (i32, i32),
    /// The region's site: its most interior tile's centre (roads meet here, majors stand here).
    pub(crate) site: Vec2,
    pub(crate) theme: u8,
    /// Land tiles and their bounding box (inclusive tile coordinates).
    pub(crate) area: u32,
    pub(crate) lo: (u16, u16),
    pub(crate) hi: (u16, u16),
    /// Road distance of the site from the Landing, normalized to 0..=1.
    pub(crate) depth: f32,
    /// Roads meeting at the site.
    pub(crate) degree: u8,
    /// The major POI standing on the site (index into `Gen::pois`).
    pub(crate) major: Option<usize>,
    /// The grand monument of a crossroads hub (regions without a major POI).
    pub(crate) landmark: Option<MapMark>,
}

impl RegionGen {
    /// World-space bounding box of the region's land.
    pub(crate) fn bounds(&self, t: &TileGrid) -> (Vec2, Vec2) {
        let hs = Vec2::splat(t.size * 0.5);
        (t.center(self.lo.0, self.lo.1) - hs, t.center(self.hi.0, self.hi.1) + hs)
    }
}

/// Two regions sharing a border.
#[derive(Clone, Debug)]
pub(crate) struct Adj {
    pub(crate) a: usize,
    pub(crate) b: usize,
    /// Shared tile edges (land on both sides).
    pub(crate) border: u32,
    pub(crate) barrier: Option<BarrierKind>,
}

/// A road between two region sites: site → bend → pass → bend → site.
#[derive(Clone, Debug)]
pub(crate) struct Road {
    pub(crate) a: usize,
    pub(crate) b: usize,
    /// Where the road crosses the regions' shared border.
    pub(crate) pass: Vec2,
    pub(crate) lanes: Vec<Lane>,
}

/// A placed POI and its clearing.
#[derive(Clone, Copy, Debug)]
pub(crate) struct PoiGen {
    pub(crate) site: PoiSite,
    /// Clearing radius (`Plaza` tiles, a keep-out for compositions).
    pub(crate) plaza: f32,
    /// Off-road POIs: the road point their spur leaves from.
    pub(crate) spur: Option<Vec2>,
}

/// Everything the stages share while one map is generated.
pub(crate) struct Gen<'a> {
    pub(crate) db: &'a ContentDb,
    pub(crate) x: ExpeditionDef,
    pub(crate) biome_key: String,
    pub(crate) biome: Biome,
    /// `max(template.phase, P1)`: the content phase generation filters by (§3.1).
    pub(crate) phase: Phase,
    pub(crate) root: GfRng,
    pub(crate) half: Vec2,
    pub(crate) tiles: TileGrid,
    pub(crate) regions: Vec<RegionGen>,
    pub(crate) adj: Vec<Adj>,
    /// 0 south, 1 north, 2 west, 3 east.
    pub(crate) landing_edge: u8,
    pub(crate) landing: Vec2,
    pub(crate) landing_region: usize,
    pub(crate) gate_region: usize,
    pub(crate) roads: Vec<Road>,
    /// The road from the Landing to its region's site.
    pub(crate) landing_road: Vec<Lane>,
    pub(crate) pois: Vec<PoiGen>,
    pub(crate) passes: Vec<Pass>,
    /// Bridge decks (bank → bank) over pit barriers.
    pub(crate) bridges: Vec<Lane>,
    /// Region pairs separated by a wall or a ridge (index into `adj`).
    pub(crate) walls: Vec<usize>,
    /// Road distance of each site from the Landing (world units), and the farthest one.
    pub(crate) site_dist: Vec<f32>,
    pub(crate) depth_scale: f32,
    pub(crate) relaxed: u8,
}

impl Gen<'_> {
    /// Every road-like lane: roads, the Landing road and POI spurs (compositions keep off them).
    pub(crate) fn lanes(&self) -> Vec<Lane> {
        let mut out: Vec<Lane> = self.roads.iter().flat_map(|r| r.lanes.iter().copied()).collect();
        out.extend(self.landing_road.iter().copied());
        out.extend(self.spurs());
        out
    }

    /// Spur roads from off-road POIs to the road they sit beside.
    pub(crate) fn spurs(&self) -> Vec<Lane> {
        let width = q(self.x.roads.width);
        self.pois.iter().filter_map(|p| p.spur.map(|s| Lane { from: s, to: p.site.at, width })).collect()
    }

    /// Tuning row of a POI kind: (ring radius, clearing radius).
    pub(crate) fn poi_size(&self, kind: PoiKind) -> (f32, f32) {
        let t = self.db.game.expedition.poi(kind).copied();
        let (r, plaza) = t.map_or((4.0, 8.0), |t| (t.radius, t.plaza));
        (q(r), q(plaza.max(r)))
    }

    /// The biome's content row.
    pub(crate) fn biome_def(&self) -> Option<&BiomeDef> {
        self.db.biomes.by_key(&self.biome_key)
    }

    /// Say what the generator gave up on when `GODFORGE_WORLDGEN_TRACE` is set (output-neutral).
    pub(crate) fn trace(&self, what: impl FnOnce() -> String) {
        if std::env::var_os("GODFORGE_WORLDGEN_TRACE").is_some() {
            eprintln!("worldgen: {}", what());
        }
    }

    /// Count one relaxed placement; `GODFORGE_WORLDGEN_TRACE=1` says which (output-neutral).
    pub(crate) fn relax(&mut self, what: impl FnOnce() -> String) {
        self.relaxed = self.relaxed.saturating_add(1);
        if std::env::var_os("GODFORGE_WORLDGEN_TRACE").is_some() {
            eprintln!("worldgen: relaxed {}", what());
        }
    }
}

/// Generate the biome map of Expedition template `t` (pure and deterministic in `t`, `seed` and
/// the content database). A template without an `expedition` block uses the defaults.
pub fn generate(db: &ContentDb, t: &RoomDef, seed: u32) -> RoomDef {
    let seed = seed.max(1);
    let x = t.expedition.as_deref().cloned().unwrap_or_default();
    let root = GfRng::new(seed as u64 ^ key_hash(&t.key).rotate_left(17));
    // Size: whole tiles and multiples of 8, within QPos reach.
    let size = (x.size / 8.0).round().max(Vec2::splat(12.0)) * 8.0;
    let half = size.min(Vec2::splat(MAX_HALF * 2.0)) * 0.5;
    let (w, h) = ((half.x * 2.0 / TILE) as u16, (half.y * 2.0 / TILE) as u16);
    let mut g = Gen {
        db,
        biome_key: t.biome.clone(),
        biome: Biome::of(&t.biome),
        phase: t.phase.max(Phase::P1),
        x,
        root,
        half,
        tiles: TileGrid::new(-half, w, h, TileKind::Ground),
        regions: Vec::new(),
        adj: Vec::new(),
        landing_edge: 0,
        landing: Vec2::ZERO,
        landing_region: 0,
        gate_region: 0,
        roads: Vec::new(),
        landing_road: Vec::new(),
        pois: Vec::new(),
        passes: Vec::new(),
        bridges: Vec::new(),
        walls: Vec::new(),
        site_dist: Vec::new(),
        depth_scale: 1.0,
        relaxed: 0,
    };

    regions::lay(&mut g);
    roads::lay(&mut g);
    pois::place(&mut g);
    barriers::lay(&mut g);
    tiles::stamp_ways(&mut g);
    let mut built = compose::build(&mut g);
    let camps = camps::place(&g, &built.builder);
    let repairs = repair::run(&mut g, &mut built, &camps);

    let obstacles = built.builder.obstacles;
    let pits = tiles::merge_pits(&g.tiles);
    let pois: Vec<PoiSite> = g.pois.iter().map(|p| p.site).collect();
    let gate = 0u8;
    let gate_at = pois[gate as usize].at;
    let hash = layout_hash(&obstacles, &pits, &pois, g.landing, gate);
    let mut roads = g.lanes();
    roads.retain(|l| l.from != l.to);
    let regions = g.regions.iter().map(|r| Region { theme: r.theme, site: r.site, landmark: r.landmark }).collect();
    let map = MapLayout {
        seed,
        hash,
        tiles: g.tiles,
        regions,
        roads: roads.clone(),
        passes: g.passes,
        pits,
        pois,
        gate,
        camps,
        relaxed: g.relaxed,
        repairs,
    };
    RoomDef {
        key: format!("{}~{seed:08x}", t.key),
        biome: t.biome.clone(),
        kind: RoomKind::Expedition,
        phase: t.phase,
        half_extents: half,
        obstacles,
        player_spawn: g.landing,
        anvil: None,
        exits: vec![gate_at],
        // Stress mode only: the horde director v2 spawns around each player cluster on maps.
        spawn_zones: vec![SpawnZone::Around { min: 27.0, max: 34.0 }],
        encounter: t.encounter.clone(),
        decor: built.builder.decor,
        motifs: t.motifs.clone(),
        rim: t.rim,
        districts: built.districts,
        lanes: roads,
        expedition: Some(Box::new(g.x)),
        map: Some(Arc::new(map)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ron_options;

    /// The Cinder Wastes template as OPEN_WORLD.md §4.3 specifies it. A fixture, so tuning the
    /// shipped `rooms.ron` never moves the golden hash: only a change to the generator does.
    const CINDER: &str = r##"(
        key: "cinder_expedition", biome: "cinder_wastes", kind: Expedition, phase: P0,
        half_extents: (216.0, 136.0), player_spawn: (0.0, 0.0),
        spawn_zones: [Around(min: 27.0, max: 34.0)],
        encounter: (budget: 0.0, duration: 1.0, rate_start: 0.0, rate_end: 0.0, max_alive: 400, elite_chance: 0.0),
        expedition: (
            size: (432.0, 272.0), regions: (5, 3), start_theme: "slag_flats",
            themes: [
                (key: "slag_flats", name: "The Slag Flats", weight: 1.3, open: true, fields: 0.6, cover: 0.025,
                 districts: [(SlagChannel, 1.0), (CrucibleYard, 0.6)], tint: "#3A2418", map_color: "#5A3A28"),
                (key: "foundry_ruins", name: "Foundry Ruins", weight: 1.0, fields: 0.2, cover: 0.055,
                 districts: [(ForgeHall, 1.4), (CrucibleYard, 0.8), (ColonnadeCourt, 0.5)], tint: "#2E1E17", map_color: "#4A3226"),
                (key: "colonnade_of_oaths", name: "Colonnade of Oaths", weight: 0.9, fields: 0.25, cover: 0.05,
                 districts: [(ColonnadeCourt, 1.5), (ForgeHall, 0.4)], tint: "#34261E", map_color: "#56443A"),
                (key: "cinder_dunes", name: "Cinder Dunes", weight: 0.8, open: true, fields: 0.75, cover: 0.02,
                 districts: [(SlagChannel, 0.6)], tint: "#2A1E1A", map_color: "#3E302A"),
                (key: "chainyard", name: "The Chainyard", weight: 0.7, fields: 0.3, cover: 0.045,
                 districts: [(CrucibleYard, 1.4), (ForgeHall, 0.6)], tint: "#301C14", map_color: "#4E2E22"),
            ],
            coast: (depth: 2, amp: 3, period: 6),
            barriers: (chance: 0.45, kinds: [(River, 0.30), (Wall, 0.15)]),
            roads: (width: 6.0, loop_chance: 0.3, pass_width: 8.0),
            pois: [(kind: Anvil, count: 3, seals: 1), (kind: Warlord, count: 1, seals: 2), (kind: Lair, count: 2, seals: 1),
                   (kind: Shrine, count: 3, seals: 1), (kind: Reliquary, count: 2, seals: 1), (kind: Vein, count: 2, seals: 1),
                   (kind: Spring, count: 3, seals: 0)],
            camps: (per_area: 4000.0, pack: (6, 12), elite_chance: 0.2, shards: (8, 15)),
            landmarks: [(GreatAnvil, 1.0), (Statue, 1.0), (ColossusHead, 0.8), (GreatBrazier, 0.8), (SealedGate, 0.5)],
            seals_required: 6, gate_requires_warlord: true, gate_force_minute: 12.0, boss_hp_mult: 1.35,
            threat_start_minute: 0.0,
            threat: [(minute: 0.0, density: 30.0, rate: 3.0, elite_chance: 0.01, hp_mult: 1.0)],
        ),
    )"##;

    /// The golden map (§3.1): `(cinder_expedition, 7)` must hash the same on every platform and
    /// every build. A deliberate generator change re-pins it; an accidental one fails here first.
    #[test]
    fn cinder_expedition_seed_7_golden_hash() {
        let db = ContentDb::load_dir(&crate::find_content_dir()).expect("shipped content loads");
        let t: RoomDef = ron_options().from_str(CINDER).expect("fixture parses");
        let map = generate(&db, &t, 7);
        let layout = map.map.as_ref().expect("a biome map");
        assert_eq!(layout.hash, layout_hash(&map.obstacles, &layout.pits, &layout.pois, map.player_spawn, layout.gate));
        assert_eq!(generate(&db, &t, 7).map.as_ref().map(|m| m.hash), Some(layout.hash), "not deterministic");
        assert_eq!(layout.hash, 0x1e23_89a1_8dcf_a64a, "golden hash moved: {:#018x}", layout.hash);
    }
}
