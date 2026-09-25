//! Shared player movement. The host simulation and client-side prediction call the *same*
//! [`step_mover`] so a replayed input history reproduces the authoritative position exactly.

use glam::Vec2;
use serde::{Deserialize, Serialize};
use std::fmt;

/// Static arena geometry: an axis-aligned play area, solid obstacles and walker-only pits.
///
/// Build it with [`Arena::new`], which indexes the shapes (a 4 u grid) so every query costs
/// only the shapes near it. An arena from [`Arena::rect`], `Default` or serde has an empty index and
/// falls back to a linear scan with the same results. Rebuild with `new` after editing `obstacles`
/// or `pits` (pushing more shapes onto an indexed arena disables its index).
#[derive(Clone, Default, Serialize, Deserialize)]
pub struct Arena {
    pub half_extents: Vec2,
    pub obstacles: Vec<Obstacle>,
    /// Walker-only blockers (void and liquid tiles on biome maps). Movers are pushed out;
    /// projectiles, beams, telegraphs and line of fire pass over them.
    #[serde(default)]
    pub pits: Vec<Obstacle>,
    #[serde(skip)]
    index: ObstacleIndex,
}

impl PartialEq for Arena {
    fn eq(&self, other: &Self) -> bool {
        self.half_extents == other.half_extents && self.obstacles == other.obstacles && self.pits == other.pits
    }
}

impl fmt::Debug for Arena {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Arena")
            .field("half_extents", &self.half_extents)
            .field("obstacles", &self.obstacles)
            .field("pits", &self.pits)
            .finish_non_exhaustive()
    }
}

/// Cell size of the [`ObstacleIndex`] (world units).
const INDEX_CELL: f32 = 4.0;
/// Query padding that absorbs float rounding between a shape's bounds and the exact tests.
const INDEX_PAD: f32 = 0.05;
/// Cells per axis at most (biome maps are at most 480 u across, 120 cells).
const INDEX_MAX_CELLS: u32 = 1024;

/// CSR uniform grid of 4 u cells over the arena. Each shape is inserted into every cell its AABB
/// overlaps (shapes outside the arena land in the edge cells). Items index `obstacles`, with pits
/// offset by `obstacles.len()`, and are ascending within each cell.
#[derive(Clone, Debug, Default)]
struct ObstacleIndex {
    origin: Vec2,
    w: u32,
    h: u32,
    /// Cell `c` holds `items[start[c]..start[c + 1]]`. Empty means "no index".
    start: Vec<u32>,
    items: Vec<u32>,
    /// `obstacles.len() + pits.len()` when built. A mismatch disables the index.
    shapes: usize,
    /// How far an obstacle's bounding circle reaches past its AABB (boxes), at most. `occluders`
    /// widens its cell query by this so its bounding-circle filter sees every candidate.
    slack: f32,
}

impl ObstacleIndex {
    fn build(half: Vec2, obstacles: &[Obstacle], pits: &[Obstacle]) -> Self {
        let shapes = obstacles.len() + pits.len();
        if shapes == 0 {
            return Self::default();
        }
        let cells = |ext: f32| ((ext.abs() * 2.0 / INDEX_CELL).ceil() as u32).clamp(1, INDEX_MAX_CELLS);
        let (w, h) = (cells(half.x), cells(half.y));
        let mut index = Self { origin: -half.abs(), w, h, start: Vec::new(), items: Vec::new(), shapes, slack: 0.0 };
        // Counting sort into CSR. Shapes go in ascending order, so every cell's list is sorted.
        let mut count = vec![0u32; (w * h) as usize + 1];
        for o in obstacles.iter().chain(pits) {
            let (x0, y0, x1, y1) = index.span_of(o);
            for y in y0..=y1 {
                for x in x0..=x1 {
                    count[(y * w + x) as usize + 1] += 1;
                }
            }
        }
        for c in 1..count.len() {
            count[c] += count[c - 1];
        }
        let mut fill = count.clone();
        index.items = vec![0; count[count.len() - 1] as usize];
        for (i, o) in obstacles.iter().chain(pits).enumerate() {
            let (x0, y0, x1, y1) = index.span_of(o);
            for y in y0..=y1 {
                for x in x0..=x1 {
                    let c = (y * w + x) as usize;
                    index.items[fill[c] as usize] = i as u32;
                    fill[c] += 1;
                }
            }
        }
        index.start = count;
        index.slack = obstacles.iter().map(Obstacle::bounding_slack).fold(0.0, f32::max);
        index
    }

    fn active(&self, shapes: usize) -> bool {
        !self.start.is_empty() && self.shapes == shapes
    }

    /// The cells overlapping the square `lo..=hi`, clamped to the grid: `(x0, y0, x1, y1)`.
    fn span(&self, lo: Vec2, hi: Vec2) -> (u32, u32, u32, u32) {
        let cell =
            |v: f32, o: f32, n: u32| (((v - o) * (1.0 / INDEX_CELL)).floor() as i64).clamp(0, n as i64 - 1) as u32;
        (
            cell(lo.x, self.origin.x, self.w),
            cell(lo.y, self.origin.y, self.h),
            cell(hi.x, self.origin.x, self.w),
            cell(hi.y, self.origin.y, self.h),
        )
    }

    /// The cells around `p` that hold every shape a circle of radius `r` at `p` can overlap.
    fn around(&self, p: Vec2, r: f32) -> (u32, u32, u32, u32) {
        let reach = Vec2::splat(r.max(0.0) + INDEX_PAD);
        self.span(p - reach, p + reach)
    }

    fn span_of(&self, o: &Obstacle) -> (u32, u32, u32, u32) {
        let (lo, hi) = o.aabb();
        self.span(lo, hi)
    }

    fn cell(&self, x: u32, y: u32) -> &[u32] {
        let c = (y * self.w + x) as usize;
        &self.items[self.start[c] as usize..self.start[c + 1] as usize]
    }
}

/// Bitwise inequality, so a push that only flips the sign of a zero still counts (as it does in a
/// plain scan that assigns every result).
fn moved(a: Vec2, b: Vec2) -> bool {
    a.x.to_bits() != b.x.to_bits() || a.y.to_bits() != b.y.to_bits()
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub enum Obstacle {
    Circle { center: Vec2, radius: f32 },
    Box { center: Vec2, half: Vec2 },
}

impl Obstacle {
    /// Push a circle out of this obstacle. Returns the corrected center.
    pub fn push_out(&self, p: Vec2, r: f32) -> Vec2 {
        match *self {
            Obstacle::Circle { center, radius } => {
                let d = p - center;
                let min = radius + r;
                let len_sq = d.length_squared();
                if len_sq >= min * min {
                    return p;
                }
                let len = len_sq.sqrt();
                let n = if len > 1e-5 { d / len } else { Vec2::X };
                center + n * min
            }
            Obstacle::Box { center, half } => {
                let local = p - center;
                let clamped = local.clamp(-half, half);
                let d = local - clamped;
                let len_sq = d.length_squared();
                if len_sq > 1e-10 {
                    if len_sq >= r * r {
                        return p;
                    }
                    let len = len_sq.sqrt();
                    return center + clamped + d / len * r;
                }
                // Center is inside the box: exit along the shallowest axis.
                let pen_x = half.x - local.x.abs();
                let pen_y = half.y - local.y.abs();
                if pen_x < pen_y {
                    Vec2::new(center.x + local.x.signum() * (half.x + r), p.y)
                } else {
                    Vec2::new(p.x, center.y + local.y.signum() * (half.y + r))
                }
            }
        }
    }

    pub fn contains(&self, p: Vec2, r: f32) -> bool {
        self.push_out(p, r) != p
    }

    /// Conservative bounding circle (center, radius).
    pub fn bounding_circle(&self) -> (Vec2, f32) {
        match *self {
            Obstacle::Circle { center, radius } => (center, radius),
            Obstacle::Box { center, half } => (center, half.length()),
        }
    }

    /// Axis-aligned bounds `(min, max)`.
    pub fn aabb(&self) -> (Vec2, Vec2) {
        let (center, half) = match *self {
            Obstacle::Circle { center, radius } => (center, Vec2::splat(radius.abs())),
            Obstacle::Box { center, half } => (center, half.abs()),
        };
        (center - half, center + half)
    }

    /// How far the bounding circle reaches past the AABB along an axis (0 for circles).
    fn bounding_slack(&self) -> f32 {
        match *self {
            Obstacle::Circle { .. } => 0.0,
            Obstacle::Box { half, .. } => (half.length() - half.x.abs().min(half.y.abs())).max(0.0),
        }
    }

    /// Does the segment `a`–`b` pass through this obstacle? Exact (projectiles die the moment
    /// their center enters an obstacle, so this is line of fire for a shot).
    pub fn blocks_segment(&self, a: Vec2, b: Vec2) -> bool {
        match *self {
            Obstacle::Circle { center, radius } => crate::math::dist_sq_point_segment(center, a, b) < radius * radius,
            Obstacle::Box { center, half } => {
                // Slab test in the box's frame.
                let (a, d) = (a - center, b - a);
                let (mut t0, mut t1) = (0.0f32, 1.0f32);
                for (p, dd, h) in [(a.x, d.x, half.x), (a.y, d.y, half.y)] {
                    if dd.abs() < 1e-8 {
                        if p.abs() >= h {
                            return false;
                        }
                        continue;
                    }
                    let (mut lo, mut hi) = ((-h - p) / dd, (h - p) / dd);
                    if lo > hi {
                        std::mem::swap(&mut lo, &mut hi);
                    }
                    t0 = t0.max(lo);
                    t1 = t1.min(hi);
                    if t0 >= t1 {
                        return false;
                    }
                }
                true
            }
        }
    }
}

impl Arena {
    /// An indexed arena: `pits` block walkers only (see [`Arena::pits`]).
    pub fn new(half_extents: Vec2, obstacles: Vec<Obstacle>, pits: Vec<Obstacle>) -> Self {
        let index = ObstacleIndex::build(half_extents, &obstacles, &pits);
        Self { half_extents, obstacles, pits, index }
    }

    /// An empty play area.
    pub fn rect(half_extents: Vec2) -> Self {
        Self { half_extents, ..Self::default() }
    }

    /// The index, unless it is empty or stale.
    fn index(&self) -> Option<&ObstacleIndex> {
        self.index.active(self.obstacles.len() + self.pits.len()).then_some(&self.index)
    }

    /// Shape `i` of the index: an obstacle, or a pit past `obstacles.len()`.
    fn shape(&self, i: u32) -> &Obstacle {
        let i = i as usize;
        match self.obstacles.get(i) {
            Some(o) => o,
            None => &self.pits[i - self.obstacles.len()],
        }
    }

    /// Resolve a circle against obstacles, pits and bounds (two passes handle most corner cases).
    ///
    /// Each pass pushes the circle out of the shapes it overlaps in ascending order (obstacles,
    /// then pits) and then clamps it into bounds, exactly like a scan over every shape: the index
    /// skips only shapes that cannot overlap, and after each push it looks for the next overlapping
    /// shape (higher index) from the new position.
    pub fn resolve(&self, mut p: Vec2, r: f32) -> Vec2 {
        for _ in 0..2 {
            p = match self.index() {
                Some(index) => self.push_out_indexed(index, p, r),
                None => self.obstacles.iter().chain(&self.pits).fold(p, |p, o| o.push_out(p, r)),
            };
            p = p.clamp(-self.half_extents + Vec2::splat(r), self.half_extents - Vec2::splat(r));
        }
        p
    }

    fn push_out_indexed(&self, index: &ObstacleIndex, mut p: Vec2, r: f32) -> Vec2 {
        let mut next = 0u32;
        loop {
            // The lowest shape index ≥ `next` that moves `p` (cells are sorted, so the first hit
            // in a cell is that cell's lowest).
            let mut best: Option<(u32, Vec2)> = None;
            let (x0, y0, x1, y1) = index.around(p, r);
            for y in y0..=y1 {
                for x in x0..=x1 {
                    for &i in index.cell(x, y) {
                        if best.is_some_and(|(b, _)| i >= b) {
                            break;
                        }
                        if i < next {
                            continue;
                        }
                        let q = self.shape(i).push_out(p, r);
                        if moved(q, p) {
                            best = Some((i, q));
                            break;
                        }
                    }
                }
            }
            let Some((i, q)) = best else { return p };
            p = q;
            next = i + 1;
        }
    }

    /// Does a circle at `p` overlap an obstacle (or, with `pits`, a pit)?
    fn overlaps(&self, p: Vec2, r: f32, pits: bool) -> bool {
        let n = self.obstacles.len() + if pits { self.pits.len() } else { 0 };
        let Some(index) = self.index() else {
            return self.obstacles.iter().chain(&self.pits).take(n).any(|o| o.contains(p, r));
        };
        let (x0, y0, x1, y1) = index.around(p, r);
        (y0..=y1).any(|y| {
            (x0..=x1).any(|x| {
                index.cell(x, y).iter().take_while(|&&i| (i as usize) < n).any(|&i| self.shape(i).contains(p, r))
            })
        })
    }

    /// Does a shot at `p` hit an obstacle? Shots fly over pits.
    pub fn blocks_shot(&self, p: Vec2) -> bool {
        self.overlaps(p, 0.0, false)
    }

    /// Is a circle at `p` clear of every obstacle and pit? (Bounds are not checked: see
    /// [`Arena::in_bounds`].)
    pub fn walkable(&self, p: Vec2, r: f32) -> bool {
        !self.overlaps(p, r, true)
    }

    /// Append to `out`, in ascending order, every obstacle (never a pit) whose bounding circle
    /// comes within `reach` of `c`. These are all the obstacles that can block a line of fire from
    /// `c` to a point within `reach` of it.
    pub fn occluders(&self, c: Vec2, reach: f32, out: &mut Vec<Obstacle>) {
        let near = |o: &Obstacle| {
            let (bc, br) = o.bounding_circle();
            bc.distance_squared(c) < (reach + br) * (reach + br)
        };
        let Some(index) = self.index() else {
            out.extend(self.obstacles.iter().filter(|o| near(o)).copied());
            return;
        };
        let n = self.obstacles.len() as u32;
        let mut found: Vec<u32> = Vec::new();
        let (x0, y0, x1, y1) = index.around(c, reach + index.slack);
        for y in y0..=y1 {
            for x in x0..=x1 {
                found.extend(
                    index.cell(x, y).iter().take_while(|&&i| i < n).filter(|&&i| near(&self.obstacles[i as usize])),
                );
            }
        }
        found.sort_unstable();
        found.dedup();
        out.extend(found.into_iter().map(|i| self.obstacles[i as usize]));
    }

    /// Does a segment hit any obstacle? (Coarse sampling; pits never block it.)
    pub fn segment_blocked(&self, a: Vec2, b: Vec2, r: f32) -> bool {
        let steps = ((b - a).length() / 0.25).ceil().max(1.0) as usize;
        (0..=steps).any(|i| {
            let p = a.lerp(b, i as f32 / steps as f32);
            self.overlaps(p, r, false)
        })
    }

    pub fn in_bounds(&self, p: Vec2) -> bool {
        p.x.abs() <= self.half_extents.x && p.y.abs() <= self.half_extents.y
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct MoveTuning {
    pub dash_speed: f32,
    pub dash_time: f32,
    pub dash_iframes: f32,
    /// Fraction of move speed while downed (wraith drift).
    pub wraith_speed: f32,
    /// How quickly velocity approaches the target (1/s). High = snappy.
    pub accel: f32,
}

impl Default for MoveTuning {
    fn default() -> Self {
        Self { dash_speed: 22.0, dash_time: 0.16, dash_iframes: 0.2, wraith_speed: 0.45, accel: 30.0 }
    }
}

/// Predicted/authoritative mover state.
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct MoverState {
    pub pos: Vec2,
    pub vel: Vec2,
    pub dash_left: f32,
    pub dash_dir: Vec2,
    pub dash_charges: u8,
    pub dash_recharge_left: f32,
    pub iframes: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MoveInput {
    pub dir: Vec2,
    /// Edge-triggered dash request.
    pub dash: bool,
    pub speed: f32,
    pub max_dash_charges: u8,
    pub dash_recharge: f32,
    /// Rooted / stance / stunned.
    pub can_move: bool,
    pub can_dash: bool,
    pub wraith: bool,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct MoveEvents {
    pub dashed: bool,
}

pub fn step_mover(
    s: &mut MoverState,
    input: &MoveInput,
    t: &MoveTuning,
    dt: f32,
    arena: &Arena,
    radius: f32,
) -> MoveEvents {
    let mut ev = MoveEvents::default();

    // Dash recharge (one charge at a time).
    if s.dash_charges < input.max_dash_charges {
        s.dash_recharge_left -= dt;
        if s.dash_recharge_left <= 0.0 {
            s.dash_charges += 1;
            s.dash_recharge_left = if s.dash_charges < input.max_dash_charges { input.dash_recharge } else { 0.0 };
        }
    } else {
        s.dash_charges = input.max_dash_charges;
        s.dash_recharge_left = 0.0;
    }
    s.iframes = (s.iframes - dt).max(0.0);

    let dir = input.dir.clamp_length_max(1.0);
    if input.dash && input.can_dash && !input.wraith && s.dash_charges > 0 && s.dash_left <= 0.0 {
        let d = dir.try_normalize().or_else(|| s.vel.try_normalize()).unwrap_or(Vec2::X);
        s.dash_dir = d;
        s.dash_left = t.dash_time;
        s.iframes = s.iframes.max(t.dash_iframes);
        if s.dash_charges == input.max_dash_charges {
            s.dash_recharge_left = input.dash_recharge;
        }
        s.dash_charges -= 1;
        ev.dashed = true;
    }

    if s.dash_left > 0.0 {
        s.dash_left -= dt;
        s.vel = s.dash_dir * t.dash_speed;
    } else if input.can_move {
        let speed = if input.wraith { input.speed * t.wraith_speed } else { input.speed };
        let target = dir * speed;
        let k = 1.0 - (-t.accel * dt).exp();
        s.vel += (target - s.vel) * k;
    } else {
        s.vel = Vec2::ZERO;
    }

    s.pos = arena.resolve(s.pos + s.vel * dt, radius);
    ev
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input(dir: Vec2) -> MoveInput {
        MoveInput {
            dir,
            dash: false,
            speed: 6.0,
            max_dash_charges: 2,
            dash_recharge: 1.0,
            can_move: true,
            can_dash: true,
            wraith: false,
        }
    }

    #[test]
    fn walks_and_stops() {
        let arena = Arena::rect(Vec2::splat(50.0));
        let mut s = MoverState { dash_charges: 2, ..Default::default() };
        for _ in 0..60 {
            step_mover(&mut s, &input(Vec2::X), &MoveTuning::default(), 1.0 / 60.0, &arena, 0.5);
        }
        assert!(s.pos.x > 5.0 && s.pos.x < 6.0, "{}", s.pos.x);
        for _ in 0..60 {
            step_mover(&mut s, &input(Vec2::ZERO), &MoveTuning::default(), 1.0 / 60.0, &arena, 0.5);
        }
        assert!(s.vel.length() < 0.01);
    }

    #[test]
    fn dash_consumes_charges_and_recharges() {
        let arena = Arena::rect(Vec2::splat(50.0));
        let t = MoveTuning::default();
        let mut s = MoverState { dash_charges: 2, ..Default::default() };
        let mut i = input(Vec2::Y);
        i.dash = true;
        assert!(step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5).dashed);
        assert_eq!(s.dash_charges, 1);
        assert!(s.iframes > 0.0);
        // Can't chain while mid-dash.
        assert!(!step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5).dashed);
        i.dash = false;
        for _ in 0..70 {
            step_mover(&mut s, &i, &t, 1.0 / 60.0, &arena, 0.5);
        }
        assert_eq!(s.dash_charges, 2);
    }

    #[test]
    fn arena_blocks() {
        let arena = Arena::new(
            Vec2::splat(10.0),
            vec![
                Obstacle::Circle { center: Vec2::new(3.0, 0.0), radius: 1.0 },
                Obstacle::Box { center: Vec2::new(-3.0, 0.0), half: Vec2::splat(1.0) },
            ],
            Vec::new(),
        );
        let p = arena.resolve(Vec2::new(2.5, 0.0), 0.5);
        assert!((p - Vec2::new(1.5, 0.0)).length() < 1e-4);
        let q = arena.resolve(Vec2::new(-2.2, 0.1), 0.5);
        assert!(q.x >= -1.5 - 1e-4, "{q}");
        let r = arena.resolve(Vec2::new(40.0, -40.0), 0.5);
        assert_eq!(r, Vec2::new(9.5, -9.5));
        assert!(arena.segment_blocked(Vec2::new(0.0, 0.0), Vec2::new(6.0, 0.0), 0.1));
        assert!(!arena.segment_blocked(Vec2::new(0.0, 5.0), Vec2::new(6.0, 5.0), 0.1));
        // Exact line of fire agrees with the sampled test.
        let [circle, square] = [arena.obstacles[0], arena.obstacles[1]];
        assert!(circle.blocks_segment(Vec2::ZERO, Vec2::new(6.0, 0.5)));
        assert!(!circle.blocks_segment(Vec2::ZERO, Vec2::new(6.0, 3.0)));
        assert!(!circle.blocks_segment(Vec2::ZERO, Vec2::new(1.5, 0.0)), "stops short of it");
        assert!(square.blocks_segment(Vec2::ZERO, Vec2::new(-6.0, 0.9)));
        assert!(square.blocks_segment(Vec2::new(-3.0, 5.0), Vec2::new(-3.0, -5.0)), "straight down through it");
        assert!(!square.blocks_segment(Vec2::ZERO, Vec2::new(-6.0, 4.0)));
        assert!(!square.blocks_segment(Vec2::new(-5.0, 1.5), Vec2::new(-1.0, 1.5)), "skims past the top");
    }

    #[test]
    fn deterministic_replay() {
        // Prediction relies on bit-identical replays.
        let arena = Arena::rect(Vec2::splat(20.0));
        let t = MoveTuning::default();
        let inputs: Vec<MoveInput> = (0..120)
            .map(|i| {
                let mut m = input(crate::math::from_angle(i as f32 * 0.1));
                m.dash = i % 37 == 0;
                m
            })
            .collect();
        let run = || {
            let mut s = MoverState { dash_charges: 2, ..Default::default() };
            for i in &inputs {
                step_mover(&mut s, i, &t, 1.0 / 60.0, &arena, 0.5);
            }
            s
        };
        assert_eq!(run(), run());
    }
}
