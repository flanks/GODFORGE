//! Uniform spatial grid over the arena for enemy queries (400+ enemies, hundreds of projectiles).
//! Rebuilt every tick; queries visit cells in a fixed order so results are deterministic.

use gf_engine::prelude::*;

#[derive(Clone, Copy, Debug)]
pub struct GridEntry {
    pub entity: Entity,
    pub pos: Vec2,
    pub radius: f32,
}

#[derive(Debug, Default)]
pub struct SpatialGrid {
    cell: f32,
    origin: Vec2,
    w: i32,
    h: i32,
    cells: Vec<Vec<u32>>,
    pub entries: Vec<GridEntry>,
    max_radius: f32,
}

impl SpatialGrid {
    /// Reset for an arena with the given half extents.
    pub fn reset(&mut self, half_extents: Vec2, cell: f32) {
        self.cell = cell.max(0.5);
        self.origin = -half_extents - Vec2::splat(4.0);
        let size = half_extents * 2.0 + Vec2::splat(8.0);
        self.w = (size.x / self.cell).ceil() as i32 + 1;
        self.h = (size.y / self.cell).ceil() as i32 + 1;
        let n = (self.w * self.h) as usize;
        if self.cells.len() != n {
            self.cells = vec![Vec::new(); n];
        } else {
            for c in &mut self.cells {
                c.clear();
            }
        }
        self.entries.clear();
        self.max_radius = 0.0;
    }

    #[inline]
    fn coord(&self, p: Vec2) -> (i32, i32) {
        let local = (p - self.origin) / self.cell;
        ((local.x.floor() as i32).clamp(0, self.w - 1), (local.y.floor() as i32).clamp(0, self.h - 1))
    }

    pub fn insert(&mut self, entity: Entity, pos: Vec2, radius: f32) {
        if self.cells.is_empty() {
            return;
        }
        let idx = self.entries.len() as u32;
        self.entries.push(GridEntry { entity, pos, radius });
        self.max_radius = self.max_radius.max(radius);
        let (x, y) = self.coord(pos);
        self.cells[(y * self.w + x) as usize].push(idx);
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Visit every entry whose circle overlaps the query circle.
    pub fn for_each_in_circle(&self, center: Vec2, radius: f32, mut f: impl FnMut(&GridEntry)) {
        if self.cells.is_empty() {
            return;
        }
        let reach = radius + self.max_radius;
        let (x0, y0) = self.coord(center - Vec2::splat(reach));
        let (x1, y1) = self.coord(center + Vec2::splat(reach));
        for y in y0..=y1 {
            for x in x0..=x1 {
                for &i in &self.cells[(y * self.w + x) as usize] {
                    let e = &self.entries[i as usize];
                    let r = radius + e.radius;
                    if e.pos.distance_squared(center) <= r * r {
                        f(e);
                    }
                }
            }
        }
    }

    /// Entries overlapping the circle, collected (deterministic order).
    pub fn in_circle(&self, center: Vec2, radius: f32) -> Vec<GridEntry> {
        let mut out = Vec::new();
        self.for_each_in_circle(center, radius, |e| out.push(*e));
        out
    }

    /// Nearest entry to `p` within `max_dist` that passes `filter`.
    pub fn nearest(&self, p: Vec2, max_dist: f32, mut filter: impl FnMut(&GridEntry) -> bool) -> Option<GridEntry> {
        let mut best: Option<(f32, GridEntry)> = None;
        self.for_each_in_circle(p, max_dist, |e| {
            if filter(e) {
                let d = e.pos.distance_squared(p);
                if best.is_none_or(|(bd, be)| d < bd || (d == bd && e.entity < be.entity)) {
                    best = Some((d, *e));
                }
            }
        });
        best.map(|(_, e)| e)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn queries_find_overlaps_only() {
        let mut g = SpatialGrid::default();
        g.reset(Vec2::new(20.0, 15.0), 2.0);
        let mut world = World::new();
        let a = world.spawn_empty().id();
        let b = world.spawn_empty().id();
        let c = world.spawn_empty().id();
        g.insert(a, Vec2::new(0.0, 0.0), 0.5);
        g.insert(b, Vec2::new(3.0, 0.0), 0.5);
        g.insert(c, Vec2::new(15.0, 10.0), 0.5);
        let hits: Vec<Entity> = g.in_circle(Vec2::new(1.0, 0.0), 1.0).iter().map(|e| e.entity).collect();
        assert_eq!(hits, vec![a]);
        assert_eq!(g.nearest(Vec2::new(2.6, 0.0), 5.0, |_| true).unwrap().entity, b);
        assert_eq!(g.nearest(Vec2::new(2.6, 0.0), 5.0, |e| e.entity != b).unwrap().entity, a);
        assert!(g.nearest(Vec2::new(-19.0, -14.0), 2.0, |_| true).is_none());
        // Out-of-bounds positions clamp into edge cells instead of panicking.
        g.insert(a, Vec2::new(500.0, -500.0), 0.5);
    }
}
