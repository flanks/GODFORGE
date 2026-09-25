//! Bot path-finding over a room layout. Generated arenas are open fields broken up by colonnades,
//! ruined walls and plinths, so greedy steering gets caught in pockets (a door straight behind a
//! row of pillars). Bots build one walkability grid per room and route around the ruins with A*.
//!
//! Bot-only: the host never path-finds, so this has no bearing on determinism across machines
//! (it is still deterministic in-process, which the same-seed replay test relies on).

use gf_content::schema::RoomDef;
use gf_engine::prelude::*;
use std::cmp::Reverse;
use std::collections::BinaryHeap;

/// Grid resolution (world units per cell).
const CELL: f32 = 0.5;

/// Walkable cells of one room for a mover of a given clearance radius.
pub struct NavGrid {
    origin: Vec2,
    w: i32,
    h: i32,
    blocked: Vec<bool>,
}

impl NavGrid {
    /// Rasterize `room` for a circle of `clearance` radius (hero radius plus a margin).
    pub fn new(room: &RoomDef, clearance: f32) -> Self {
        let half = room.half_extents;
        let w = ((half.x * 2.0) / CELL).ceil().max(1.0) as i32;
        let h = ((half.y * 2.0) / CELL).ceil().max(1.0) as i32;
        let mut grid = Self { origin: -half, w, h, blocked: vec![false; (w * h) as usize] };
        let limit = half - Vec2::splat(clearance);
        for y in 0..h {
            for x in 0..w {
                let c = grid.center(x, y);
                let out = c.x.abs() > limit.x || c.y.abs() > limit.y;
                grid.blocked[(y * w + x) as usize] = out || room.obstacles.iter().any(|o| o.contains(c, clearance));
            }
        }
        grid
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
    pub fn path(&self, from: Vec2, to: Vec2) -> Option<Vec<Vec2>> {
        let start = self.nearest_free(from)?;
        let goal = self.nearest_free(to)?;
        let n = (self.w * self.h) as usize;
        let idx = |(x, y): (i32, i32)| (y * self.w + x) as usize;
        // Costs in 1/10 cell: straight 10, diagonal 14.
        let heuristic = |(x, y): (i32, i32)| {
            let (dx, dy) = ((x - goal.0).abs(), (y - goal.1).abs());
            (10 * dx.max(dy) + 4 * dx.min(dy)) as u32
        };
        let mut g = vec![u32::MAX; n];
        let mut came = vec![u32::MAX; n];
        let mut open = BinaryHeap::new();
        g[idx(start)] = 0;
        open.push(Reverse((heuristic(start), idx(start) as u32)));
        let mut found = false;
        while let Some(Reverse((_, i))) = open.pop() {
            let i = i as usize;
            let (x, y) = ((i as i32) % self.w, (i as i32) / self.w);
            if (x, y) == goal {
                found = true;
                break;
            }
            let gi = g[i];
            for (dx, dy, cost) in
                [(1, 0, 10), (-1, 0, 10), (0, 1, 10), (0, -1, 10), (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14)]
            {
                let (nx, ny) = (x + dx, y + dy);
                if !self.free(nx, ny) || (dx != 0 && dy != 0 && (!self.free(x + dx, y) || !self.free(x, y + dy))) {
                    continue;
                }
                let j = idx((nx, ny));
                let ng = gi + cost;
                if ng < g[j] {
                    g[j] = ng;
                    came[j] = i as u32;
                    open.push(Reverse((ng + heuristic((nx, ny)), j as u32)));
                }
            }
        }
        if !found {
            return None;
        }
        let mut cells = vec![idx(goal)];
        let mut at = idx(goal);
        while at != idx(start) {
            at = came[at] as usize;
            cells.push(at);
        }
        cells.pop();
        cells.reverse();
        let mut points: Vec<Vec2> =
            cells.into_iter().map(|i| self.center(i as i32 % self.w, i as i32 / self.w)).collect();
        if self.walkable(to) {
            if let Some(last) = points.last_mut() {
                *last = to;
            } else {
                points.push(to);
            }
        }
        Some(points)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use gf_core::movement::Obstacle;

    fn room(obstacles: Vec<Obstacle>) -> RoomDef {
        RoomDef { half_extents: Vec2::new(20.0, 14.0), obstacles, ..RoomDef::placeholder() }
    }

    #[test]
    fn routes_around_a_colonnade_too_tight_to_squeeze_through() {
        // A row of pillars with 1.0-unit gaps: a 0.55-radius hero cannot pass between them.
        let pillars =
            (-6..=6).map(|i| Obstacle::Circle { center: Vec2::new(i as f32 * 2.0, 0.0), radius: 0.5 }).collect();
        let nav = NavGrid::new(&room(pillars), 0.65);
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
        let nav = NavGrid::new(&room(vec![]), 0.65);
        assert!(nav.clear_line(Vec2::new(-10.0, -5.0), Vec2::new(12.0, 6.0)));
        // A box sealing the whole width: nothing gets from south to north.
        let wall = vec![Obstacle::Box { center: Vec2::ZERO, half: Vec2::new(20.0, 0.5) }];
        let nav = NavGrid::new(&room(wall), 0.65);
        assert!(nav.path(Vec2::new(0.0, -5.0), Vec2::new(0.0, 5.0)).is_none());
    }
}
