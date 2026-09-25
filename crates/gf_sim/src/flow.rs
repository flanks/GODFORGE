//! Horde flow fields over a biome map's 4 u tiles (OPEN_WORLD.md §5.6), host only: integer
//! 8-neighbour Dijkstra from each player's tile, one slot per refresh (round robin), so the horde
//! funnels over bridges instead of piling up at chasm banks. State: [`crate::resources::Flow`].
//!
//! Tile costs: Road 8, Plaza and Bridge 9, Ground 10, +40 where obstacles cover more than half the
//! tile, and Void / Liquid impassable. A step costs `10` (straight) or `14` (diagonal) × the cost of
//! the tile it enters / 10, and a diagonal step never cuts the corner of an impassable tile. It is
//! all integer (shortest distances are unique), so a field is the same on every run.
//!
//! A field reaches `hard_cull` (+16 u) along the ground from its player, which keeps a refresh near
//! 0.07 ms on Cinder: enemies farther away are culled soon anyway, and spawns are tested well
//! inside it. `enemy_ai` chases directly along a short clear tile line and follows the field
//! otherwise; the horde director rejects spawn points the field reaches only by a long detour.

use crate::components::*;
use crate::resources::*;
use gf_content::schema::{TileGrid, TileKind};
use gf_core::movement::Arena;
use gf_engine::prelude::*;

/// Step cost of an impassable tile (`Void`, `Liquid`).
pub const BLOCKED: u8 = u8::MAX;
/// Field distance of a tile the source cannot reach.
pub const UNREACHED: u16 = u16::MAX;
/// World units per unit of field distance on open ground (a 4 u Ground tile costs 10 straight).
pub const DIST_UNIT: f32 = TileGrid::TILE / 10.0;

const COST_ROAD: u8 = 8;
const COST_PLAZA: u8 = 9;
const COST_GROUND: u8 = 10;
/// Added where obstacles cover more than half of a tile (3 of its 4 sample points).
const COST_COVERED: u8 = 40;
/// Tiles at least this costly count as blocked for the direct-chase line test.
const COVERED_AT: u8 = COST_COVERED;

/// The 8 neighbours in expansion order (E, W, N, S, NE, NW, SE, SW) with their step weight.
const NEIGHBOURS: [(i32, i32, u32); 8] =
    [(1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10), (1, 1, 14), (-1, 1, 14), (1, -1, 14), (-1, -1, 14)];

impl Flow {
    /// A flow grid for `tiles`, costed against the arena's obstacles (no fields built yet).
    pub fn for_map(tiles: &TileGrid, arena: &Arena) -> Self {
        let n = tiles.w as usize * tiles.h as usize;
        let mut cost = Vec::with_capacity(n);
        for y in 0..tiles.h {
            for x in 0..tiles.w {
                let base = match tiles.kind[tiles.index(x, y)] {
                    TileKind::Void | TileKind::Liquid => BLOCKED,
                    TileKind::Road => COST_ROAD,
                    TileKind::Plaza | TileKind::Bridge => COST_PLAZA,
                    TileKind::Ground => COST_GROUND,
                };
                if base == BLOCKED {
                    cost.push(BLOCKED);
                    continue;
                }
                // Obstacle coverage from 4 sample points, one per tile quarter.
                let c = tiles.center(x, y);
                let q = tiles.size * 0.25;
                let covered = [Vec2::new(-q, -q), Vec2::new(q, -q), Vec2::new(-q, q), Vec2::new(q, q)]
                    .into_iter()
                    .filter(|d| arena.blocks_shot(c + *d))
                    .count();
                cost.push(if covered >= 3 { base + COST_COVERED } else { base });
            }
        }
        Self { w: tiles.w, h: tiles.h, origin: tiles.origin, cost, dist: Default::default(), src: [None; 4], next: 0 }
    }

    /// Is this the grid of `tiles`? (Guards against a field left over from the previous room.)
    pub fn matches(&self, tiles: &TileGrid) -> bool {
        self.w == tiles.w && self.h == tiles.h && self.origin == tiles.origin && !self.cost.is_empty()
    }

    /// The tile containing `p`, if it is on the grid.
    pub fn tile(&self, p: Vec2) -> Option<(i32, i32)> {
        let t = ((p - self.origin) / TileGrid::TILE).floor();
        (t.x >= 0.0 && t.y >= 0.0 && t.x < self.w as f32 && t.y < self.h as f32).then_some((t.x as i32, t.y as i32))
    }

    #[inline]
    fn index(&self, x: i32, y: i32) -> usize {
        y as usize * self.w as usize + x as usize
    }

    #[inline]
    fn on_grid(&self, x: i32, y: i32) -> bool {
        x >= 0 && y >= 0 && x < self.w as i32 && y < self.h as i32
    }

    /// Centre of tile (`x`, `y`) in world units.
    pub fn center(&self, x: i32, y: i32) -> Vec2 {
        self.origin + (Vec2::new(x as f32, y as f32) + Vec2::splat(0.5)) * TileGrid::TILE
    }

    /// Can walkers enter tile (`x`, `y`)? (Off the grid is impassable.)
    pub fn passable(&self, x: i32, y: i32) -> bool {
        self.on_grid(x, y) && self.cost[self.index(x, y)] != BLOCKED
    }

    /// Is the terrain under `p` walkable land?
    pub fn passable_at(&self, p: Vec2) -> bool {
        self.tile(p).is_some_and(|(x, y)| self.passable(x, y))
    }

    /// Path length (world units, ≈ straight-line on open ground) from `slot`'s player to `p`
    /// along its field. `None` without a field or when the field never reaches `p`.
    pub fn distance(&self, slot: u8, p: Vec2) -> Option<f32> {
        let s = slot as usize % 4;
        self.src[s]?;
        let (x, y) = self.tile(p)?;
        let d = *self.dist[s].get(self.index(x, y))?;
        (d != UNREACHED).then_some(d as f32 * DIST_UNIT)
    }

    /// The way to `slot`'s player from `from`: toward the centre of the neighbour tile closest to
    /// it along the field. `None` without a field, at the player's tile, or with no way closer.
    pub fn steer(&self, slot: u8, from: Vec2) -> Option<Vec2> {
        let s = slot as usize % 4;
        self.src[s]?;
        let dist = &self.dist[s];
        let (x, y) = self.tile(from)?;
        let here = *dist.get(self.index(x, y))?;
        let mut best: Option<(u16, i32, i32)> = None;
        for (dx, dy, _) in NEIGHBOURS {
            let (nx, ny) = (x + dx, y + dy);
            if !self.passable(nx, ny) || (dx != 0 && dy != 0 && !(self.passable(x + dx, y) && self.passable(x, y + dy)))
            {
                continue;
            }
            let d = dist[self.index(nx, ny)];
            if d < here && best.is_none_or(|(b, ..)| d < b) {
                best = Some((d, nx, ny));
            }
        }
        best.map(|(_, nx, ny)| (self.center(nx, ny) - from).normalize_or_zero()).filter(|v| *v != Vec2::ZERO)
    }

    /// Is `b` within `max_tiles` tiles of `a` along a clear tile line (Bresenham)? The tiles in
    /// between must be passable and not mostly covered by obstacles; the end tiles may be anything.
    pub fn line_clear(&self, a: Vec2, b: Vec2, max_tiles: i32) -> bool {
        let (Some((mut x, mut y)), Some((x1, y1))) = (self.tile(a), self.tile(b)) else { return false };
        let (dx, dy) = ((x1 - x).abs(), -(y1 - y).abs());
        if dx.max(-dy) > max_tiles {
            return false;
        }
        let (sx, sy) = ((x1 - x).signum(), (y1 - y).signum());
        let mut err = dx + dy;
        loop {
            if x == x1 && y == y1 {
                return true;
            }
            let e2 = 2 * err;
            if e2 >= dy {
                err += dy;
                x += sx;
            }
            if e2 <= dx {
                err += dx;
                y += sy;
            }
            if (x != x1 || y != y1) && self.cost[self.index(x, y)] >= COVERED_AT {
                return false;
            }
        }
    }

    /// Rebuild `slot`'s field from the tile under `from` out to `limit` (field distance; tiles
    /// beyond stay unreached), skipped when the source tile is unchanged (obstacles never move).
    ///
    /// Dijkstra with a bucket queue (Dial's algorithm): every step weighs a small integer, so
    /// tiles are settled in distance order from a ring of `BUCKETS` lists. Shortest distances are
    /// unique, so the field does not depend on the order ties are popped in.
    pub fn refresh(&mut self, slot: u8, from: Vec2, limit: u32, scratch: &mut FlowScratch) {
        let s = slot as usize % 4;
        let Some((sx, sy)) = self.tile(from) else {
            self.src[s] = None;
            return;
        };
        let n = self.cost.len();
        let source = self.index(sx, sy);
        if self.src[s] == Some(source as u32) && self.dist[s].len() == n {
            return;
        }
        let mut dist = std::mem::take(&mut self.dist[s]);
        dist.clear();
        dist.resize(n, UNREACHED);
        let buckets = &mut scratch.buckets;
        buckets.resize_with(BUCKETS, Vec::new);
        buckets.iter_mut().for_each(Vec::clear);
        dist[source] = 0;
        buckets[0].push(source as u32);
        let mut pending = 1usize;
        let mut d = 0u32;
        while pending > 0 {
            let b = d as usize % BUCKETS;
            while let Some(i) = buckets[b].pop() {
                pending -= 1;
                if dist[i as usize] as u32 != d {
                    continue; // settled earlier at a shorter distance
                }
                let (x, y) = ((i % self.w as u32) as i32, (i / self.w as u32) as i32);
                for (dx, dy, step) in NEIGHBOURS {
                    let (nx, ny) = (x + dx, y + dy);
                    if !self.passable(nx, ny)
                        || (dx != 0 && dy != 0 && !(self.passable(x + dx, y) && self.passable(x, y + dy)))
                    {
                        continue;
                    }
                    let ni = self.index(nx, ny);
                    let nd = d + step * self.cost[ni] as u32 / 10;
                    if nd < dist[ni] as u32 && nd <= limit.min(UNREACHED as u32 - 1) {
                        dist[ni] = nd as u16;
                        buckets[nd as usize % BUCKETS].push(ni as u32);
                        pending += 1;
                    }
                }
            }
            d += 1;
        }
        self.dist[s] = dist;
        self.src[s] = Some(source as u32);
    }
}

/// Bucket lists in the ring (more than the heaviest step, `14 × (10 + 40) / 10 = 70`).
const BUCKETS: usize = 128;

/// Reused bucket-queue storage for [`Flow::refresh`].
#[derive(Default)]
pub struct FlowScratch {
    buckets: Vec<Vec<u32>>,
}

/// How far a field reaches (field distance): the hard-cull range and a little more. Enemies farther
/// along the ground are culled soon anyway, and spawns are tested well inside it.
fn field_limit(content: &Content) -> u32 {
    let horde = &content.game.expedition.horde;
    ((horde.hard_cull.max(horde.cull_distance) + 16.0) / DIST_UNIT) as u32
}

/// Keep the fields current: rebuild the grid when the room changes (every living player's field at
/// once), then refresh one player slot every `flow_refresh_ticks / 4` ticks, round robin.
pub fn refresh_flow(
    clock: Res<SimClock>,
    content: Res<Content>,
    run: Res<RunState>,
    layout: Res<RoomLayout>,
    arena: Res<ArenaRes>,
    mut flow: ResMut<Flow>,
    mut built_for: Local<Option<u32>>,
    mut scratch: Local<FlowScratch>,
    players: Query<(&Player, &Pos, &Life)>,
) {
    if *built_for != Some(run.room_serial) {
        *built_for = Some(run.room_serial);
        *flow = match layout.0.map.as_deref() {
            Some(map) => Flow::for_map(&map.tiles, &arena.0),
            None => Flow::default(),
        };
        let limit = field_limit(&content);
        if flow.w > 0 {
            for (p, pos, life) in &players {
                if life.state.is_alive() {
                    flow.refresh(p.slot, pos.0, limit, &mut scratch);
                }
            }
        }
        return;
    }
    if flow.w == 0 {
        return;
    }
    let every = (content.game.expedition.horde.flow_refresh_ticks / 4).max(1) as u32;
    if !clock.tick.is_multiple_of(every) {
        return;
    }
    let slot = flow.next % 4;
    flow.next = (slot + 1) % 4;
    match players.iter().find(|(p, _, life)| p.slot % 4 == slot && life.state.is_alive()) {
        Some((_, pos, _)) => flow.refresh(slot, pos.0, field_limit(&content), &mut scratch),
        None => flow.src[slot as usize] = None,
    }
}
