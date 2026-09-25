//! Biome maps (OPEN_WORLD.md §3): one huge generated map per biome, built as a room of kind
//! [`RoomKind::Expedition`] from `(template, seed)` exactly like a procedural arena. The host
//! replicates `(room, room_seed, room_serial)` and every client and bot rebuilds the same map with
//! [`crate::procgen::resolve_room`].
//!
//! **Phase 1 stub.** The full pipeline (regions, coast, roads, barriers, POIs, the room grammar in
//! region slots, camps, pits and reachability repair, §3.2) lands in phase 2. Until then
//! [`generate`] returns a flat map: open ground in one region, the Landing plaza near the south
//! edge and the Boss Gate near the north edge, joined by one road. It already runs the room
//! grammar's [`Builder`] in map mode (tile mask, keep-outs, lanes) for the Landing's dressing.
//!
//! **Determinism** (§3.1, enforced in review): integer `GfRng` output and `+ − × ÷ √` only (no
//! trigonometry, `exp`, `powf` or `mul_add`; facings are `Rot16`), no `HashMap`/`HashSet`
//! iteration, integer sort keys, and every coordinate written into obstacles, pits, POIs or camps
//! quantized to 1/8 u. Generation reads only content, never the build phase.

use crate::db::ContentDb;
use crate::procgen::{Biome, Builder, TileMask, key_hash, q, qv};
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
const LANDING_R: f32 = 10.0;
/// Distance of the Landing and the gate from their map edges.
const EDGE_INSET: f32 = 24.0;

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

/// Mark every tile whose centre lies within `r` of `c` as `kind`.
fn stamp_disc(tiles: &mut TileGrid, c: Vec2, r: f32, kind: TileKind) {
    for y in 0..tiles.h {
        for x in 0..tiles.w {
            if tiles.center(x, y).distance_squared(c) <= r * r {
                let i = tiles.index(x, y);
                tiles.kind[i] = kind;
            }
        }
    }
}

/// Mark every `Ground` tile whose centre lies within `lane.width / 2` of the lane as `Road`.
fn stamp_road(tiles: &mut TileGrid, lane: &Lane) {
    let (a, b, hw) = (lane.from, lane.to, lane.width * 0.5);
    let ab = b - a;
    for y in 0..tiles.h {
        for x in 0..tiles.w {
            let p = tiles.center(x, y);
            let t = ((p - a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
            let i = tiles.index(x, y);
            if tiles.kind[i] == TileKind::Ground && p.distance_squared(a + ab * t) <= hw * hw {
                tiles.kind[i] = TileKind::Road;
            }
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
    let mut tiles = TileGrid::new(-half, w, h, TileKind::Ground);

    // One region: the start theme's.
    let theme = x.theme(&x.start_theme).unwrap_or(0) as u8;
    let regions = vec![Region { theme, site: Vec2::ZERO, landmark: None }];

    // The Landing (south) and the Boss Gate (north), joined by a road.
    let landing = qv(Vec2::new(0.0, -half.y + EDGE_INSET));
    let gate_at = qv(Vec2::new(0.0, half.y - EDGE_INSET));
    let gate_tuning = db.game.expedition.poi(PoiKind::Gate).copied();
    let (gate_r, gate_plaza) = gate_tuning.map_or((7.0, 14.0), |g| (g.radius, g.plaza));
    let road = Lane { from: landing, to: gate_at, width: q(x.roads.width) };
    stamp_disc(&mut tiles, landing, LANDING_R, TileKind::Plaza);
    stamp_disc(&mut tiles, gate_at, gate_plaza, TileKind::Plaza);
    stamp_road(&mut tiles, &road);
    let pois = vec![PoiSite {
        kind: PoiKind::Gate,
        at: gate_at,
        radius: q(gate_r),
        seals: 0,
        region: 0,
        god: None,
        guard: None,
    }];

    // Map-mode builder: dress the Landing (region 0's dressing stream).
    let mut b = Builder {
        keep: vec![(landing, LANDING_R), (gate_at, gate_plaza)],
        lanes: vec![road],
        spawn: landing,
        exits: vec![gate_at],
        mask: Some(TileMask::of(&tiles)),
        ..Builder::new(half, Biome::of(&t.biome), 1.0, root.fork(100), root.fork(200))
    };
    let rot = b.vd(16);
    b.decal(Decor::FloorInlay { at: landing, radius: q(LANDING_R - 0.9), rot, variant: 0, god: 0 });
    b.decal(Decor::FloorInlay { at: gate_at, radius: q(gate_r), rot, variant: 1, god: 0 });
    for k in [2u8, 6, 10, 14] {
        b.brazier(landing + rot16_dir(k) * (LANDING_R + 0.3));
    }

    let obstacles = b.obstacles;
    let pits: Vec<Obstacle> = Vec::new();
    let gate = 0u8;
    let hash = layout_hash(&obstacles, &pits, &pois, landing, gate);
    let map = MapLayout {
        seed,
        hash,
        tiles,
        regions,
        roads: vec![road],
        passes: Vec::new(),
        pits,
        pois,
        gate,
        camps: Vec::new(),
        relaxed: 0,
        repairs: 0,
    };
    let plaza = Vec2::splat(LANDING_R);
    RoomDef {
        key: format!("{}~{seed:08x}", t.key),
        biome: t.biome.clone(),
        kind: RoomKind::Expedition,
        phase: t.phase,
        half_extents: half,
        obstacles,
        player_spawn: landing,
        anvil: None,
        exits: vec![gate_at],
        // Stress mode only: the horde director v2 spawns around each player cluster on maps.
        spawn_zones: vec![SpawnZone::Around { min: 27.0, max: 34.0 }],
        encounter: t.encounter.clone(),
        decor: b.decor,
        motifs: t.motifs.clone(),
        rim: t.rim,
        districts: vec![District { kind: DistrictKind::Plaza, min: landing - plaza, max: landing + plaza }],
        lanes: vec![road],
        expedition: Some(Box::new(x)),
        map: Some(Arc::new(map)),
    }
}
