//! Bot path-finding over a room layout. Generated arenas are open fields broken up by colonnades,
//! ruined walls and plinths, so greedy steering gets caught in pockets (a door straight behind a
//! row of pillars). Bots build one walkability grid per room and route around the ruins with A*.
//!
//! Bot-only: the host never path-finds, so this has no bearing on determinism across machines
//! (it is still deterministic in-process, which the same-seed replay test relies on).

use gf_core::movement::{Arena, Obstacle};
use gf_engine::prelude::*;
use std::cell::RefCell;
use std::cmp::Reverse;
use std::collections::BinaryHeap;

/// Grid resolution (world units per cell).
const CELL: f32 = 0.5;

/// A* gives up after this many expansions. A whole biome map is ~470k cells at 0.5 u; a room is
/// under 30k, so only long hauls on a map hit the cap (they route through coarse waypoints).
pub const MAX_EXPANSIONS: u32 = 25_000;

/// Walkable cells of one room for a mover of a given clearance radius.
pub struct NavGrid {
    origin: Vec2,
    w: i32,
    h: i32,
    blocked: Vec<bool>,
}

impl NavGrid {
    /// Rasterize `arena` (bounds, obstacles and pits) for a circle of `clearance` radius (hero
    /// radius plus a margin). Each shape tests only the cells under its bounds grown by the
    /// clearance, so a whole biome map rasterizes in milliseconds.
    pub fn new(arena: &Arena, clearance: f32) -> Self {
        let half = arena.half_extents;
        let w = ((half.x * 2.0) / CELL).ceil().max(1.0) as i32;
        let h = ((half.y * 2.0) / CELL).ceil().max(1.0) as i32;
        let mut grid = Self { origin: -half, w, h, blocked: vec![false; (w * h) as usize] };
        let limit = half - Vec2::splat(clearance);
        for y in 0..h {
            for x in 0..w {
                let c = grid.center(x, y);
                grid.blocked[(y * w + x) as usize] = c.x.abs() > limit.x || c.y.abs() > limit.y;
            }
        }
        for o in arena.obstacles.iter().chain(&arena.pits) {
            grid.stamp(o, clearance);
        }
        grid
    }

    /// Block the cells where a circle of `clearance` would overlap `o`. The span is the shape's
    /// bounds grown by the clearance plus one cell, so rounding never skips a cell the exact test
    /// blocks: the result is the same as testing every cell.
    fn stamp(&mut self, o: &Obstacle, clearance: f32) {
        let (lo, hi) = o.aabb();
        let reach = Vec2::splat(clearance.max(0.0));
        let (x0, y0) = self.span_cell(lo - reach, -1);
        let (x1, y1) = self.span_cell(hi + reach, 1);
        for y in y0..=y1 {
            for x in x0..=x1 {
                let i = (y * self.w + x) as usize;
                if !self.blocked[i] && o.contains(self.center(x, y), clearance) {
                    self.blocked[i] = true;
                }
            }
        }
    }

    /// The cell holding `p`, moved by `pad` cells and clamped to the grid.
    fn span_cell(&self, p: Vec2, pad: i32) -> (i32, i32) {
        let c = ((p - self.origin) / CELL).floor();
        ((c.x as i32).saturating_add(pad).clamp(0, self.w - 1), (c.y as i32).saturating_add(pad).clamp(0, self.h - 1))
    }

    fn center(&self, x: i32, y: i32) -> Vec2 {
        self.origin + Vec2::new((x as f32 + 0.5) * CELL, (y as f32 + 0.5) * CELL)
    }

    fn cell(&self, p: Vec2) -> (i32, i32) {
        let c = ((p - self.origin) / CELL).floor();
        ((c.x as i32).clamp(0, self.w - 1), (c.y as i32).clamp(0, self.h - 1))
    }

    fn free(&self, x: i32, y: i32) -> bool {
        x >= 0 && y >= 0 && x < self.w && y < self.h && !self.blocked[(y * self.w + x) as usize]
    }

    /// Is `p` on a walkable cell?
    pub fn walkable(&self, p: Vec2) -> bool {
        let (x, y) = self.cell(p);
        self.free(x, y)
    }

    /// Nearest walkable cell to `p` (spiral search), for starts pressed against a wall and goals
    /// sitting inside an obstacle's clearance.
    fn nearest_free(&self, p: Vec2) -> Option<(i32, i32)> {
        let (cx, cy) = self.cell(p);
        if self.free(cx, cy) {
            return Some((cx, cy));
        }
        for r in 1..12 {
            let mut best: Option<((i32, i32), f32)> = None;
            for y in cy - r..=cy + r {
                for x in cx - r..=cx + r {
                    if (x - cx).abs() != r && (y - cy).abs() != r {
                        continue;
                    }
                    if self.free(x, y) {
                        let d = self.center(x, y).distance_squared(p);
                        if best.is_none_or(|(_, bd)| d < bd) {
                            best = Some(((x, y), d));
                        }
                    }
                }
            }
            if let Some((c, _)) = best {
                return Some(c);
            }
        }
        None
    }

    /// Straight walk from `a` to `b` stays on walkable cells.
    pub fn clear_line(&self, a: Vec2, b: Vec2) -> bool {
        let d = b - a;
        let steps = (d.length() / (CELL * 0.5)).ceil().max(1.0) as i32;
        (0..=steps).all(|i| self.walkable(a + d * (i as f32 / steps as f32)))
    }

    /// A* (8-connected, no corner cutting) from `from` to `to`. Returns waypoints after the start,
    /// ending at `to` when it is walkable. `None` when no route exists.
    ///
    /// After [`MAX_EXPANSIONS`] the search stops and returns the route to the explored cell
    /// nearest the goal, so a bot still makes headway (`None` if that is the start cell).
    pub fn path(&self, from: Vec2, to: Vec2) -> Option<Vec<Vec2>> {
        let start = self.nearest_free(from)?;
        let goal = self.nearest_free(to)?;
        let w = self.w;
        let idx = |(x, y): (i32, i32)| (y * w + x) as usize;
        // Costs in 1/10 cell: straight 10, diagonal 14.
        let heuristic = |(x, y): (i32, i32)| {
            let (dx, dy) = ((x - goal.0).abs(), (y - goal.1).abs());
            (10 * dx.max(dy) + 4 * dx.min(dy)) as u32
        };
        let cells = SEARCH.with_borrow_mut(|s| {
            s.begin((self.w * self.h) as usize);
            s.visit(idx(start), 0, u32::MAX);
            s.open.push(Reverse((heuristic(start), idx(start) as u32)));
            // The explored cell nearest the goal (by heuristic), for a capped search.
            let mut nearest = (heuristic(start), idx(start));
            let mut expansions = 0u32;
            let mut end = None;
            while let Some(Reverse((f, i))) = s.open.pop() {
                let i = i as usize;
                let (x, y) = ((i as i32) % w, (i as i32) / w);
                let (gi, hi) = (s.g(i), heuristic((x, y)));
                if f > gi + hi {
                    continue; // stale: `i` was already expanded by a shorter route
                }
                if (x, y) == goal {
                    end = Some(i);
                    break;
                }
                if hi < nearest.0 {
                    nearest = (hi, i);
                }
                expansions += 1;
                if expansions > MAX_EXPANSIONS {
                    end = (nearest.1 != idx(start)).then_some(nearest.1);
                    break;
                }
                for (dx, dy, cost) in [
                    (1, 0, 10),
                    (-1, 0, 10),
                    (0, 1, 10),
                    (0, -1, 10),
                    (1, 1, 14),
                    (1, -1, 14),
                    (-1, 1, 14),
                    (-1, -1, 14),
                ] {
                    let (nx, ny) = (x + dx, y + dy);
                    if !self.free(nx, ny) || (dx != 0 && dy != 0 && (!self.free(x + dx, y) || !self.free(x, y + dy))) {
                        continue;
                    }
                    let j = idx((nx, ny));
                    let ng = gi + cost;
                    if ng < s.g(j) {
                        s.visit(j, ng, i as u32);
                        s.open.push(Reverse((ng + heuristic((nx, ny)), j as u32)));
                    }
                }
            }
            let end = end?;
            let mut cells = vec![end];
            let mut at = end;
            while at != idx(start) {
                at = s.came[at] as usize;
                cells.push(at);
            }
            cells.pop();
            cells.reverse();
            Some((cells, end == idx(goal)))
        });
        let (cells, reached) = cells?;
        let mut points: Vec<Vec2> = cells.into_iter().map(|i| self.center(i as i32 % w, i as i32 / w)).collect();
        if reached && self.walkable(to) {
            if let Some(last) = points.last_mut() {
                *last = to;
            } else {
                points.push(to);
            }
        }
        Some(points)
    }
}

thread_local! {
    /// A* buffers reused by every search on this thread: a biome map's grid is ~470k cells, and
    /// clearing fresh arrays for each search would cost more than a short search itself.
    static SEARCH: RefCell<Search> = RefCell::new(Search::default());
}

#[derive(Default)]
struct Search {
    /// The search that last wrote each cell's `g` and `came`; any other value means unvisited.
    stamp: Vec<u32>,
    g: Vec<u32>,
    came: Vec<u32>,
    current: u32,
    open: BinaryHeap<Reverse<(u32, u32)>>,
}

impl Search {
    /// Start a search over `cells` cells (every cell unvisited, the open list empty).
    fn begin(&mut self, cells: usize) {
        if self.stamp.len() < cells {
            self.stamp.resize(cells, 0);
            self.g.resize(cells, u32::MAX);
            self.came.resize(cells, u32::MAX);
        }
        self.current = self.current.wrapping_add(1);
        if self.current == 0 {
            self.stamp.fill(0);
            self.current = 1;
        }
        self.open.clear();
    }

    /// Best known cost to cell `i` in this search (`u32::MAX` when unvisited).
    fn g(&self, i: usize) -> u32 {
        if self.stamp[i] == self.current { self.g[i] } else { u32::MAX }
    }

    fn visit(&mut self, i: usize, g: u32, came: u32) {
        self.stamp[i] = self.current;
        self.g[i] = g;
        self.came[i] = came;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arena(obstacles: Vec<Obstacle>) -> Arena {
        Arena::new(Vec2::new(20.0, 14.0), obstacles, Vec::new())
    }

    #[test]
    fn routes_around_a_colonnade_too_tight_to_squeeze_through() {
        // A row of pillars with 1.0-unit gaps: a 0.55-radius hero cannot pass between them.
        let pillars =
            (-6..=6).map(|i| Obstacle::Circle { center: Vec2::new(i as f32 * 2.0, 0.0), radius: 0.5 }).collect();
        let nav = NavGrid::new(&arena(pillars), 0.65);
        let (from, to) = (Vec2::new(0.5, -3.0), Vec2::new(0.5, 5.0));
        assert!(!nav.clear_line(from, to));
        let path = nav.path(from, to).expect("a route around the row");
        assert_eq!(*path.last().unwrap(), to);
        // The route leaves the row's span to get around it, and never crosses a blocked cell.
        assert!(path.iter().any(|p| p.x.abs() > 12.0), "{path:?}");
        let mut prev = from;
        for p in &path {
            assert!(p.distance(prev) < 1.2);
            prev = *p;
        }
        assert!(path.iter().all(|p| nav.walkable(*p)));
    }

    #[test]
    fn open_ground_is_a_clear_line_and_walled_off_goals_have_no_route() {
        let nav = NavGrid::new(&arena(vec![]), 0.65);
        assert!(nav.clear_line(Vec2::new(-10.0, -5.0), Vec2::new(12.0, 6.0)));
        // A box sealing the whole width: nothing gets from south to north.
        let wall = vec![Obstacle::Box { center: Vec2::ZERO, half: Vec2::new(20.0, 0.5) }];
        let nav = NavGrid::new(&arena(wall), 0.65);
        assert!(nav.path(Vec2::new(0.0, -5.0), Vec2::new(0.0, 5.0)).is_none());
    }
}
