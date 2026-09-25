//! Procedural arenas: every run composes fresh layouts from the run seed, so no two runs share a
//! map (§9 "procedural room composition"). Arenas are sized for horde play: open NIMRODS-scale
//! fields where the camera follows you and the swarm pours in from off-screen, broken up by ruins
//! that create lanes and chokepoints instead of corridors.
//!
//! **Deterministic across machines.** The host replicates only a 32-bit seed per room and every
//! client and bot rebuilds the identical layout. Geometry is fed exclusively by integer RNG output
//! and IEEE-exact arithmetic (+ − × ÷ √, no trigonometry: facings are [`Rot16`] steps read from a
//! literal table), and every coordinate is quantized to 1/8 unit, so a Windows host and a Linux
//! client always agree.
//!
//! ## Layout grammar
//!
//! A generated arena is composed, not scattered:
//!
//! 1. **Skeleton.** The entrance (south), the central plaza (mosaic, or the anvil's forge circle)
//!    and the reward gates (north rim) are joined by processional [`Lane`]s that stay clear of
//!    ruins. A cross lane on each flank splits the field into quadrant slots, or the flank stays
//!    one tall wing.
//! 2. **Landmarks** frame the plaza: a monument on the axis between the plaza and the gates (two
//!    gates) or a pair flanking the central lane (a central gate), arches spanning the processional
//!    lanes, and often a fallen colossus head beside the plaza.
//! 3. **Districts.** Each slot receives a themed composition from the biome's pool, template
//!    `motifs` first: a colonnade court, a collapsed forge hall around a great anvil, a slag channel
//!    crossed by bridges, a cloister, a fallen giant tree, a broken spiral stair, a rift field...
//!    Compositions put their backs to the rim and open toward the fight; in a four-slot room one
//!    slot stays an open killing field.
//! 4. **Density.** Compact ruin clusters along the north and flank bands and at the skirts of the
//!    districts top the floor cover up to the pre-grammar density, so pacing holds while the middle
//!    of the field stays open.
//! 5. **Dressing** (visual only, its own RNG stream, so re-dressing never moves an obstacle):
//!    banners, clutter and rubble along the rim, braziers at the gates and the plaza, floor inlays,
//!    paving, ground cover and fissures.
//!
//! Guarantees: the spawn, plaza and gates stay clear; separate features keep ≥ 2.8 u lanes between
//! them (pieces of one composition may squeeze closer: colonnade gaps are chokepoints for the
//! swarm); a 3 u rim margin stays clear; and every obstacle is dressed by exactly one solid
//! [`Decor`].
//!
//! Authored templates still matter: a template supplies the room kind, biome, encounter tuning,
//! door count and motifs; boss and mini-boss arenas stay hand-built (seed 0).
//!
//! ## Map mode
//!
//! Biome maps ([`RoomKind::Expedition`], built by [`crate::worldgen`]) reuse this grammar at map
//! scale: the [`Builder`] runs over the whole map with a [`TileMask`], so compositions stand only on
//! open ground (never on roads, plazas, bridges, liquid or void) and props only on land, and its
//! obstacle queries go through a bucket index. Rooms have no mask and generate exactly as before.

use crate::db::ContentDb;
use crate::schema::*;
use gf_core::movement::Obstacle;
use gf_core::rng::GfRng;
use glam::Vec2;

/// Rooms of these kinds are generated; the rest use their authored template verbatim.
pub fn is_generated_kind(kind: RoomKind) -> bool {
    matches!(kind, RoomKind::Combat | RoomKind::Elite | RoomKind::Anvil | RoomKind::Treasure | RoomKind::Expedition)
}

/// The layout the host and every client use for `template` + `seed` (seed 0 = authored as-is).
/// Biome maps are always generated: seed 0 on an Expedition template means seed 1.
pub fn resolve_room(db: &ContentDb, template: u16, seed: u32) -> RoomDef {
    let Some(t) = db.rooms.try_get(template).or_else(|| db.rooms.try_get(0)) else {
        return RoomDef::placeholder();
    };
    if t.kind == RoomKind::Expedition {
        return crate::worldgen::generate(db, t, seed.max(1));
    }
    if seed == 0 || !is_generated_kind(t.kind) { t.clone() } else { generate(t, seed) }
}

/// Mix the run seed and the room counter into a non-zero room seed.
pub fn room_seed(run_seed: u64, serial: u32) -> u32 {
    let mut z = run_seed ^ (serial as u64 + 1).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^= z >> 31;
    (z as u32) | 1
}

pub(crate) fn key_hash(s: &str) -> u64 {
    s.bytes().fold(0xcbf2_9ce4_8422_2325u64, |h, b| (h ^ b as u64).wrapping_mul(0x0000_0100_0000_01b3))
}

#[inline]
pub(crate) fn q(v: f32) -> f32 {
    (v * 8.0).round() / 8.0
}

#[inline]
pub(crate) fn qv(v: Vec2) -> Vec2 {
    Vec2::new(q(v.x), q(v.y))
}

/// Conservative bounding circle of an obstacle.
pub(crate) fn bounds(o: &Obstacle) -> (Vec2, f32) {
    match *o {
        Obstacle::Circle { center, radius } => (center, radius),
        Obstacle::Box { center, half } => (center, half.length()),
    }
}

/// Centre and axis-aligned half extents of an obstacle.
pub(crate) fn extent(o: &Obstacle) -> (Vec2, Vec2) {
    match *o {
        Obstacle::Circle { center, radius } => (center, Vec2::splat(radius)),
        Obstacle::Box { center, half } => (center, half),
    }
}

pub(crate) fn point_seg(p: Vec2, a: Vec2, b: Vec2) -> f32 {
    let ab = b - a;
    let t = ((p - a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
    p.distance(a + ab * t)
}

/// Signed distance from `p` to the box `c ± h`.
pub(crate) fn point_box(p: Vec2, c: Vec2, h: Vec2) -> f32 {
    let d = (p - c).abs() - h;
    d.max(Vec2::ZERO).length() + d.x.max(d.y).min(0.0)
}

/// Signed distance from `p` to an obstacle's surface.
pub(crate) fn sd(o: &Obstacle, p: Vec2) -> f32 {
    match *o {
        Obstacle::Circle { center, radius } => p.distance(center) - radius,
        Obstacle::Box { center, half } => point_box(p, center, half),
    }
}

fn seg_hits_box(a: Vec2, b: Vec2, c: Vec2, h: Vec2) -> bool {
    let (lo, hi, d) = (c - h, c + h, b - a);
    let (mut t0, mut t1) = (0.0f32, 1.0f32);
    for (ai, di, l, u) in [(a.x, d.x, lo.x, hi.x), (a.y, d.y, lo.y, hi.y)] {
        if di.abs() < 1e-9 {
            if ai < l || ai > u {
                return false;
            }
        } else {
            let (ta, tb) = ((l - ai) / di, (u - ai) / di);
            t0 = t0.max(ta.min(tb));
            t1 = t1.min(ta.max(tb));
            if t0 > t1 {
                return false;
            }
        }
    }
    true
}

/// Clear distance from an obstacle's surface to the segment a–b (negative when they touch).
pub(crate) fn seg_dist(o: &Obstacle, a: Vec2, b: Vec2) -> f32 {
    match *o {
        Obstacle::Circle { center, radius } => point_seg(center, a, b) - radius,
        Obstacle::Box { center, half } => {
            if seg_hits_box(a, b, center, half) {
                return -1.0;
            }
            let corners = [
                center + half,
                center - half,
                center + Vec2::new(half.x, -half.y),
                center + Vec2::new(-half.x, half.y),
            ];
            let ends = point_box(a, center, half).min(point_box(b, center, half));
            corners.iter().map(|k| point_seg(*k, a, b)).fold(ends, f32::min)
        }
    }
}

/// Exact clear distance between two obstacles' surfaces (negative when they overlap).
pub fn gap(a: &Obstacle, b: &Obstacle) -> f32 {
    match (*a, *b) {
        (Obstacle::Circle { center: c1, radius: r1 }, Obstacle::Circle { center: c2, radius: r2 }) => {
            c1.distance(c2) - r1 - r2
        }
        (Obstacle::Circle { center, radius }, Obstacle::Box { center: bc, half })
        | (Obstacle::Box { center: bc, half }, Obstacle::Circle { center, radius }) => {
            point_box(center, bc, half) - radius
        }
        (Obstacle::Box { center: c1, half: h1 }, Obstacle::Box { center: c2, half: h2 }) => {
            let d = (c1 - c2).abs() - (h1 + h2);
            d.max(Vec2::ZERO).length() + d.x.max(d.y).min(0.0)
        }
    }
}

/// The [`Rot16`] step closest to direction `d` (dot products only: exact everywhere).
pub(crate) fn rot_of(d: Vec2) -> Rot16 {
    let mut best = 0;
    let mut best_dot = f32::MIN;
    for k in 0..16u8 {
        let v = rot16_dir(k).dot(d);
        if v > best_dot {
            best_dot = v;
            best = k;
        }
    }
    best
}

/// Clear floor kept between features so the horde flows and players can always kite.
pub const LANE: f32 = 2.8;
/// Pieces of one composition either touch (a hairline gap no enemy fits into) ...
pub(crate) const TOUCH: f32 = 0.3;
/// ... or leave a squeeze: the swarm and elites slip through, heroes weave, bosses cannot.
pub(crate) const SQUEEZE: f32 = 2.1;
/// Clear margin inside the arena rim.
pub(crate) const RIM: f32 = 3.0;
/// Breathing room between a district slot and the lanes around it.
pub(crate) const PAD: f32 = 1.0;
/// Width of the processional axis (entrance → plaza → central gate).
pub(crate) const AXIS_W: f32 = 4.5;
/// Width of the side-gate and cross lanes.
pub(crate) const LANE_W: f32 = 4.0;
/// Resolution of the floor-cover budget grid.
pub(crate) const CELL: f32 = 0.5;

/// Share of the floor ruins cover, by room kind: the pre-grammar scatter's density, so the new
/// layouts pace like the old ones (measured with `gf-content layout-stats`).
fn cover_target(kind: RoomKind) -> f32 {
    match kind {
        RoomKind::Combat | RoomKind::Elite => 0.050,
        RoomKind::Anvil => 0.044,
        _ => 0.031,
    }
}

/// Composition scale by room kind: smaller rooms get smaller districts.
fn kind_scale(kind: RoomKind) -> f32 {
    match kind {
        RoomKind::Combat | RoomKind::Elite => 1.0,
        RoomKind::Anvil => 0.82,
        _ => 0.66,
    }
}

// ───────────────────────────── frames ─────────────────────────────

#[derive(Clone, Copy, Debug)]
pub(crate) struct Rect {
    pub(crate) min: Vec2,
    pub(crate) max: Vec2,
}

impl Rect {
    pub(crate) fn new(a: Vec2, b: Vec2) -> Self {
        Rect { min: a.min(b), max: a.max(b) }
    }
    pub(crate) fn size(&self) -> Vec2 {
        self.max - self.min
    }
    pub(crate) fn center(&self) -> Vec2 {
        (self.min + self.max) * 0.5
    }
    pub(crate) fn contains(&self, p: Vec2, margin: f32) -> bool {
        p.x >= self.min.x - margin
            && p.x <= self.max.x + margin
            && p.y >= self.min.y - margin
            && p.y <= self.max.y + margin
    }
}

/// A district's local frame: `u` runs along `ax`, `v` along `ay`, and `+v` is the composition's
/// back (toward the rim), so courts open toward the fight.
#[derive(Clone, Copy, Debug)]
pub(crate) struct Frame {
    pub(crate) o: Vec2,
    pub(crate) ax: Vec2,
    pub(crate) ay: Vec2,
    pub(crate) hl: f32,
    pub(crate) hw: f32,
    /// How strongly sub-frames slide toward `+u` (away from a gate's keep-out), 0..1.
    pub(crate) slide: f32,
}

impl Frame {
    /// Frame over `r` whose back faces `back` (an axis direction); `+u` points along `away` when
    /// that lies on the `u` axis, else `flip_u` picks the sign.
    pub(crate) fn of(r: Rect, back: Vec2, away: Vec2, flip_u: bool) -> Frame {
        let s = r.size() * 0.5;
        let (ax, hl, hw) = if back.x != 0.0 { (Vec2::Y, s.y, s.x) } else { (Vec2::X, s.x, s.y) };
        let along = ax.dot(away);
        let ax = if along != 0.0 {
            ax * along.signum()
        } else if flip_u {
            -ax
        } else {
            ax
        };
        Frame { o: r.center(), ax, ay: back, hl, hw, slide: 0.0 }
    }
    pub(crate) fn p(&self, u: f32, v: f32) -> Vec2 {
        self.o + self.ax * u + self.ay * v
    }
    /// World half extents of a local box.
    pub(crate) fn h(&self, hu: f32, hv: f32) -> Vec2 {
        if self.ax.x != 0.0 { Vec2::new(hu, hv) } else { Vec2::new(hv, hu) }
    }
    pub(crate) fn dir(&self, du: f32, dv: f32) -> Vec2 {
        self.ax * du + self.ay * dv
    }
    pub(crate) fn rot(&self, du: f32, dv: f32) -> Rot16 {
        rot_of(self.dir(du, dv))
    }
    /// The same frame turned so `u` runs along the longer side (for linear compositions).
    pub(crate) fn long(&self) -> Frame {
        if self.hl >= self.hw {
            *self
        } else {
            Frame { o: self.o, ax: self.ay, ay: self.ax, hl: self.hw, hw: self.hl, slide: 0.0 }
        }
    }
    /// A sub-frame of half size (`hl`, `hw`), slid along `u` (biased toward `+u` by the frame's
    /// `slide`) and pushed `outward` (0 = anywhere, 1 = flush) toward the back.
    pub(crate) fn sub(&self, hl: f32, hw: f32, rng: &mut GfRng, outward: f32) -> Frame {
        let (hl, hw) = (hl.min(self.hl), hw.min(self.hw));
        let su = self.hl - hl;
        let u = su * (self.slide + (1.0 - self.slide) * rng.range_f32(-0.8, 0.8));
        let v = (self.hw - hw) * (outward + (1.0 - outward) * rng.f32());
        Frame { o: self.p(u, v), ax: self.ax, ay: self.ay, hl, hw, slide: self.slide }
    }
    pub(crate) fn rect(&self) -> Rect {
        let e = self.h(self.hl, self.hw);
        Rect::new(self.o - e, self.o + e)
    }
}

// ───────────────────────────── biome grammar ─────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Biome {
    Cinder,
    Verdant,
    Spire,
    Unmaking,
}

impl Biome {
    pub(crate) fn of(key: &str) -> Biome {
        match key {
            "verdant_ruin" => Biome::Verdant,
            "hollow_spire" => Biome::Spire,
            "the_unmaking" => Biome::Unmaking,
            _ => Biome::Cinder,
        }
    }

    /// Themed districts this biome builds, with pick weights.
    pub(crate) fn pool(self) -> &'static [(DistrictKind, f32)] {
        use DistrictKind::*;
        match self {
            Biome::Cinder => &[(ColonnadeCourt, 1.0), (ForgeHall, 1.2), (SlagChannel, 1.2), (CrucibleYard, 1.0)],
            Biome::Verdant => {
                &[(Cloister, 1.2), (RootTerrace, 1.0), (ReflectingPool, 1.0), (FallenGiant, 1.1), (ColonnadeCourt, 0.4)]
            }
            Biome::Spire => {
                &[(ColonnadeCourt, 0.8), (BrokenStair, 1.1), (CrystalGarden, 1.0), (DebrisRing, 1.0), (VoidChasm, 1.0)]
            }
            Biome::Unmaking => &[
                (ShatteredIslands, 1.2),
                (RiftField, 1.0),
                (InvertedNave, 1.1),
                (VoidChasm, 0.8),
                (CrystalGarden, 0.6),
            ],
        }
    }

    /// Gods (index into the gods table) whose banners and statues this biome shows.
    pub(crate) fn gods(self) -> &'static [u8] {
        match self {
            Biome::Cinder => &[0, 7, 6],
            Biome::Verdant => &[4, 5, 6],
            Biome::Spire => &[3, 1, 2],
            Biome::Unmaking => &[2, 7, 3],
        }
    }

    pub(crate) fn clutter(self) -> &'static [ClutterKind] {
        use ClutterKind::*;
        match self {
            Biome::Cinder => &[Urns, Ingots, WeaponRack, Crates, Bones],
            Biome::Verdant => &[Urns, Mushrooms, Candles, Bones],
            Biome::Spire => &[Tomes, Lanterns, Urns, Shards, Candles],
            Biome::Unmaking => &[Shards, Bones, Candles, Offerings],
        }
    }

    pub(crate) fn paving(self) -> u8 {
        match self {
            Biome::Cinder => 0,
            Biome::Verdant => 3,
            Biome::Spire => 2,
            Biome::Unmaking => 3,
        }
    }

    pub(crate) fn column(self, rng: &mut GfRng) -> f32 {
        q(match self {
            Biome::Cinder => rng.range_f32(4.5, 6.0),
            Biome::Verdant => rng.range_f32(5.0, 7.0),
            Biome::Spire => rng.range_f32(6.0, 8.5),
            Biome::Unmaking => rng.range_f32(6.0, 9.0),
        })
    }

    /// Monument on the axis between the plaza and the gates.
    pub(crate) fn axis_marks(self) -> &'static [(MapMark, f32)] {
        match self {
            Biome::Cinder => &[(MapMark::Statue, 0.45), (MapMark::GreatBrazier, 0.35), (MapMark::SealedGate, 0.2)],
            Biome::Verdant => &[(MapMark::Statue, 0.35), (MapMark::Tree, 0.4), (MapMark::SealedGate, 0.25)],
            Biome::Spire => &[(MapMark::Statue, 0.4), (MapMark::SpiralStair, 0.25), (MapMark::SealedGate, 0.35)],
            Biome::Unmaking => &[(MapMark::InvertedColumn, 0.35), (MapMark::Rift, 0.35), (MapMark::Statue, 0.3)],
        }
    }

    /// Mirrored pair flanking the central lane.
    pub(crate) fn pair_marks(self) -> &'static [(MapMark, f32)] {
        match self {
            Biome::Cinder => &[(MapMark::Statue, 0.6), (MapMark::GreatBrazier, 0.4)],
            Biome::Verdant => &[(MapMark::Statue, 0.5), (MapMark::Tree, 0.5)],
            Biome::Spire => &[(MapMark::Statue, 0.6), (MapMark::Crystal, 0.4)],
            Biome::Unmaking => &[(MapMark::InvertedColumn, 0.5), (MapMark::Rift, 0.3), (MapMark::Statue, 0.2)],
        }
    }

    pub(crate) fn rim(self, rng: &mut GfRng) -> RimStyle {
        use RimEdge::*;
        fn pick(rng: &mut GfRng, opts: &[(RimEdge, f32)]) -> RimEdge {
            let w: Vec<f32> = opts.iter().map(|o| o.1).collect();
            opts[rng.weighted_index(&w).unwrap_or(0)].0
        }
        let (north, flank, south, height): (&[(RimEdge, f32)], &[(RimEdge, f32)], &[(RimEdge, f32)], (f32, f32)) =
            match self {
                Biome::Cinder => {
                    (&[(Wall, 0.55), (Colonnade, 0.45)], &[(BrokenWall, 0.6), (Cliff, 0.4)], &[(Open, 1.0)], (5.0, 7.0))
                }
                Biome::Verdant => (
                    &[(Colonnade, 0.4), (Thicket, 0.35), (Terrace, 0.25)],
                    &[(Thicket, 0.45), (Balustrade, 0.3), (BrokenWall, 0.25)],
                    &[(Open, 0.7), (Thicket, 0.3)],
                    (6.0, 9.0),
                ),
                Biome::Spire => (
                    &[(Colonnade, 0.5), (Terrace, 0.5)],
                    &[(Balustrade, 0.6), (Shattered, 0.4)],
                    &[(Open, 0.6), (Shattered, 0.4)],
                    (7.0, 10.0),
                ),
                Biome::Unmaking => (
                    &[(Shattered, 0.45), (Colonnade, 0.3), (Cliff, 0.25)],
                    &[(Shattered, 0.8), (BrokenWall, 0.2)],
                    &[(Shattered, 0.6), (Open, 0.4)],
                    (6.0, 9.0),
                ),
            };
        let north = pick(rng, north);
        let east = pick(rng, flank);
        let west = if rng.chance(0.5) { east } else { pick(rng, flank) };
        let south = pick(rng, south);
        let height = q(rng.range_f32(height.0, height.1));
        RimStyle { north, east, south, west, height, variant: rng.range_u32(0, 4) as u8 }
    }
}

// ───────────────────────────── builder ─────────────────────────────

/// Side of a [`Buckets`] cell (world units).
const BUCKET: f32 = 4.0;
/// Float slack on bucket queries. A candidate set that is a little too large changes no answer.
const SLACK: f32 = 1.0;

/// The builder's obstacles bucketed by centre in 4 u cells, so `fits` and `clearance` look only at
/// the obstacles that can change their answer (a biome map holds thousands).
///
/// A query for the box `c ± e` widened by `reach` visits every cell a centre within
/// `e + reach + max_extent (+ SLACK)` can fall in. Every obstacle it skips is farther than `reach`
/// from the box on some axis, so its exact gap (or signed distance) is too, and the answer equals a
/// scan of every obstacle bit for bit.
#[derive(Clone, Debug)]
pub(crate) struct Buckets {
    origin: Vec2,
    w: usize,
    h: usize,
    cells: Vec<Vec<u32>>,
    /// The largest half extent (either axis) of any obstacle inserted so far.
    max_extent: f32,
}

impl Buckets {
    pub(crate) fn new(half: Vec2) -> Self {
        let w = ((half.x * 2.0) / BUCKET).ceil().max(0.0) as usize + 1;
        let h = ((half.y * 2.0) / BUCKET).ceil().max(0.0) as usize + 1;
        Self { origin: -half, w, h, cells: vec![Vec::new(); w * h], max_extent: 0.0 }
    }

    /// Cell of `p`, clamped into the grid (an off-grid centre lands in an edge cell, which every
    /// query reaching past that edge visits).
    fn cell(&self, p: Vec2) -> (usize, usize) {
        let x = ((p.x - self.origin.x) / BUCKET).floor().clamp(0.0, (self.w - 1) as f32) as usize;
        let y = ((p.y - self.origin.y) / BUCKET).floor().clamp(0.0, (self.h - 1) as f32) as usize;
        (x, y)
    }

    pub(crate) fn insert(&mut self, index: usize, o: &Obstacle) {
        let (c, e) = extent(o);
        self.max_extent = self.max_extent.max(e.x).max(e.y);
        let (x, y) = self.cell(c);
        self.cells[y * self.w + x].push(index as u32);
    }

    /// Indices of every obstacle whose extent may come within `reach` of the box `c ± e` (a
    /// superset, in no meaningful order: callers only fold order-independent answers over it).
    pub(crate) fn near(&self, c: Vec2, e: Vec2, reach: f32) -> impl Iterator<Item = usize> + '_ {
        let r = e + Vec2::splat(reach + self.max_extent + SLACK);
        let (x0, y0) = self.cell(c - r);
        let (x1, y1) = self.cell(c + r);
        (y0..=y1).flat_map(move |y| (x0..=x1).flat_map(move |x| self.cells[y * self.w + x].iter().map(|&i| i as usize)))
    }
}

/// Map mode: a pad around a piece's extent that must also be `Ground`.
pub(crate) const MASK_PAD: f32 = 0.5;

/// Map mode's view of the biome map's tile raster (4 u tiles). Compositions stand only on
/// `Ground` tiles (never on roads, plazas, bridges, liquid or void); visual props only on land.
/// Rooms have no mask, and every check below is skipped for them.
#[derive(Clone, Debug)]
pub(crate) struct TileMask {
    pub(crate) origin: Vec2,
    pub(crate) size: f32,
    pub(crate) w: usize,
    pub(crate) h: usize,
    pub(crate) kind: Vec<TileKind>,
}

impl TileMask {
    pub(crate) fn of(grid: &TileGrid) -> Self {
        Self { origin: grid.origin, size: grid.size, w: grid.w as usize, h: grid.h as usize, kind: grid.kind.clone() }
    }

    /// Tile column / row of a world coordinate (may be off the grid).
    fn tile(&self, v: f32, origin: f32) -> i64 {
        ((v - origin) / self.size).floor() as i64
    }

    /// Is every tile the box `c ± e` overlaps `Ground`? (Off the grid is not.)
    pub(crate) fn ground(&self, c: Vec2, e: Vec2) -> bool {
        let (x0, x1) = (self.tile(c.x - e.x, self.origin.x), self.tile(c.x + e.x, self.origin.x));
        let (y0, y1) = (self.tile(c.y - e.y, self.origin.y), self.tile(c.y + e.y, self.origin.y));
        if x0 < 0 || y0 < 0 || x1 >= self.w as i64 || y1 >= self.h as i64 {
            return false;
        }
        (y0..=y1).all(|y| (x0..=x1).all(|x| self.kind[y as usize * self.w + x as usize] == TileKind::Ground))
    }

    /// Is the tile under `p` land?
    pub(crate) fn land(&self, p: Vec2) -> bool {
        let (x, y) = (self.tile(p.x, self.origin.x), self.tile(p.y, self.origin.y));
        (0..self.w as i64).contains(&x)
            && (0..self.h as i64).contains(&y)
            && self.kind[y as usize * self.w + x as usize].is_land()
    }
}

pub(crate) struct Builder {
    pub(crate) half: Vec2,
    pub(crate) biome: Biome,
    pub(crate) scale: f32,
    /// Obstacle-shaping stream.
    pub(crate) lay: GfRng,
    /// Visual-only stream: changing the dressing never moves an obstacle.
    pub(crate) dress: GfRng,
    pub(crate) keep: Vec<(Vec2, f32)>,
    pub(crate) lanes: Vec<Lane>,
    pub(crate) obstacles: Vec<Obstacle>,
    pub(crate) owner: Vec<u16>,
    /// Bucket index over `obstacles` (kept in step by [`Builder::solid`], the only writer).
    pub(crate) buckets: Buckets,
    pub(crate) decor: Vec<Decor>,
    pub(crate) groups: u16,
    pub(crate) cover: Vec<bool>,
    pub(crate) covered: usize,
    pub(crate) cells: (usize, usize),
    /// Footprints of the themed compositions (the density top-up keeps out of them).
    pub(crate) comps: Vec<Rect>,
    pub(crate) spawn: Vec2,
    pub(crate) exits: Vec<Vec2>,
    /// Map mode: the tiles pieces and props may stand on (`None` in rooms).
    pub(crate) mask: Option<TileMask>,
}

impl Builder {
    /// An empty builder over the rectangle `±half` (a room, or a whole biome map), with no
    /// keep-outs, lanes, spawn point or exits yet.
    pub(crate) fn new(half: Vec2, biome: Biome, scale: f32, lay: GfRng, dress: GfRng) -> Builder {
        let cells = (((half.x * 2.0) / CELL).ceil() as usize, ((half.y * 2.0) / CELL).ceil() as usize);
        Builder {
            half,
            biome,
            scale,
            lay,
            dress,
            keep: Vec::new(),
            lanes: Vec::new(),
            obstacles: Vec::new(),
            owner: Vec::new(),
            buckets: Buckets::new(half),
            decor: Vec::new(),
            groups: 0,
            cover: vec![false; cells.0 * cells.1],
            covered: 0,
            cells,
            comps: Vec::new(),
            spawn: Vec2::ZERO,
            exits: Vec::new(),
            mask: None,
        }
    }

    pub(crate) fn rl(&mut self, lo: f32, hi: f32) -> f32 {
        self.lay.range_f32(lo, hi)
    }
    pub(crate) fn rd(&mut self, lo: f32, hi: f32) -> f32 {
        self.dress.range_f32(lo, hi)
    }
    pub(crate) fn vd(&mut self, n: u32) -> u8 {
        self.dress.range_u32(0, n) as u8
    }
    pub(crate) fn god(&mut self) -> u8 {
        let gods = self.biome.gods();
        gods[self.dress.range_u32(0, gods.len() as u32) as usize]
    }
    pub(crate) fn clutter_kind(&mut self) -> ClutterKind {
        let kinds = self.biome.clutter();
        kinds[self.dress.range_u32(0, kinds.len() as u32) as usize]
    }
    pub(crate) fn group(&mut self) -> u16 {
        self.groups += 1;
        self.groups
    }

    /// Inside the rim margin, out of the keep-outs and lanes, a lane away from other groups, and
    /// either touching or a squeeze apart from its own group (no slivers that trap an elite). In
    /// map mode, also only on `Ground` tiles.
    pub(crate) fn fits(&self, o: &Obstacle, g: u16) -> bool {
        let (c, e) = extent(o);
        if c.x.abs() + e.x > self.half.x - RIM || c.y.abs() + e.y > self.half.y - RIM {
            return false;
        }
        if let Some(mask) = &self.mask
            && !mask.ground(c, e + Vec2::splat(MASK_PAD))
        {
            return false;
        }
        let (bc, br) = bounds(o);
        if self.keep.iter().any(|(k, kr)| bc.distance(*k) < br + kr) {
            return false;
        }
        if self.lanes.iter().any(|l| seg_dist(o, l.from, l.to) < l.width * 0.5) {
            return false;
        }
        // Anything a lane or more away passes either rule, so only the neighbours can refuse.
        self.buckets.near(c, e, LANE).all(|i| {
            let gap = gap(o, &self.obstacles[i]);
            if self.owner[i] == g { gap <= TOUCH || gap >= SQUEEZE } else { gap >= LANE }
        })
    }

    pub(crate) fn mark(&mut self, o: &Obstacle) {
        let (c, e) = extent(o);
        let (w, h) = self.cells;
        let x0 = ((c.x - e.x + self.half.x) / CELL).floor().max(0.0) as usize;
        let x1 = (((c.x + e.x + self.half.x) / CELL).ceil().max(0.0) as usize).min(w);
        let y0 = ((c.y - e.y + self.half.y) / CELL).floor().max(0.0) as usize;
        let y1 = (((c.y + e.y + self.half.y) / CELL).ceil().max(0.0) as usize).min(h);
        for y in y0..y1 {
            for x in x0..x1 {
                let p = Vec2::new(-self.half.x + (x as f32 + 0.5) * CELL, -self.half.y + (y as f32 + 0.5) * CELL);
                let i = y * w + x;
                if !self.cover[i] && sd(o, p) <= 0.0 {
                    self.cover[i] = true;
                    self.covered += 1;
                }
            }
        }
    }

    pub(crate) fn covered_area(&self) -> f32 {
        self.covered as f32 * CELL * CELL
    }

    /// Place obstacles atomically together with the one decor that dresses them.
    pub(crate) fn solid(&mut self, g: u16, pieces: &[Obstacle], d: Decor) -> bool {
        if pieces.is_empty() || !pieces.iter().all(|o| self.fits(o, g)) {
            return false;
        }
        for o in pieces {
            self.mark(o);
            self.buckets.insert(self.obstacles.len(), o);
            self.obstacles.push(*o);
            self.owner.push(g);
        }
        self.decor.push(d);
        true
    }

    pub(crate) fn circle(&mut self, g: u16, at: Vec2, r: f32, make: impl FnOnce(Vec2, f32) -> Decor) -> bool {
        let (at, r) = (qv(at), q(r));
        self.solid(g, &[Obstacle::Circle { center: at, radius: r }], make(at, r))
    }

    pub(crate) fn block(&mut self, g: u16, at: Vec2, half: Vec2, make: impl FnOnce(Vec2, Vec2) -> Decor) -> bool {
        let (at, half) = (qv(at), qv(half));
        self.solid(g, &[Obstacle::Box { center: at, half }], make(at, half))
    }

    /// A chain of overlapping circles from `a` (radius `r0`) to `b` (radius `r1`): fallen columns
    /// and trunks, dressed by `make(a, b)`.
    pub(crate) fn chain(
        &mut self,
        g: u16,
        a: Vec2,
        b: Vec2,
        r0: f32,
        r1: f32,
        make: impl FnOnce(Vec2, Vec2) -> Decor,
    ) -> bool {
        let (a, b) = (qv(a), qv(b));
        let n = ((a.distance(b) / (r0.min(r1) * 0.9)).ceil() as usize).max(1);
        let pieces: Vec<Obstacle> = (0..=n)
            .map(|i| {
                let t = i as f32 / n as f32;
                Obstacle::Circle { center: qv(a + (b - a) * t), radius: q(r0 + (r1 - r0) * t) }
            })
            .collect();
        self.solid(g, &pieces, make(a, b))
    }

    /// Distance from `p` to the nearest obstacle surface when that is below `reach`; otherwise
    /// some value ≥ `reach` (so `clearance(p, c) >= c` answers exactly as a full scan would).
    pub(crate) fn clearance(&self, p: Vec2, reach: f32) -> f32 {
        self.buckets.near(p, Vec2::ZERO, reach).map(|i| sd(&self.obstacles[i], p)).fold(f32::MAX, f32::min)
    }

    pub(crate) fn off_lanes(&self, p: Vec2, margin: f32) -> bool {
        self.lanes.iter().all(|l| point_seg(p, l.from, l.to) >= l.width * 0.5 + margin)
    }

    /// Visual prop standing on free floor: inside the arena (on land, in map mode), `clear` from
    /// obstacles and off the lanes, the spawn point and the gate mouths.
    pub(crate) fn prop(&mut self, d: Decor, clear: f32) -> bool {
        let p = d.anchor();
        let ok = p.x.abs() <= self.half.x - 0.3
            && p.y.abs() <= self.half.y - 0.2
            && self.mask.as_ref().is_none_or(|m| m.land(p))
            && self.clearance(p, clear) >= clear
            && self.off_lanes(p, clear.min(0.5))
            && p.distance(self.spawn) >= 3.0
            && self.exits.iter().all(|e| p.distance(*e) >= 2.6);
        if ok {
            self.decor.push(d);
        }
        ok
    }

    /// Floor decal (paving, inlays, cover, fissures, bridges, wall banners): no clearance needed.
    pub(crate) fn decal(&mut self, d: Decor) {
        self.decor.push(d);
    }

    pub(crate) fn rubble(&mut self, at: Vec2, lo: f32, hi: f32) {
        let (radius, variant) = (q(self.rd(lo, hi)), self.vd(4));
        self.prop(Decor::Rubble { at: qv(at), radius, variant }, 0.0);
    }

    pub(crate) fn cover_patch(&mut self, at: Vec2, lo: f32, hi: f32) {
        let (radius, variant) = (q(self.rd(lo, hi)), self.vd(4));
        self.prop(Decor::Overgrowth { at: qv(at), radius, variant }, 0.0);
    }

    pub(crate) fn clutter(&mut self, at: Vec2, lo: f32, hi: f32, kind: Option<ClutterKind>) {
        let kind = kind.unwrap_or_else(|| self.clutter_kind());
        let (radius, count, rot) = (q(self.rd(lo, hi)), self.dress.range_u32(3, 7) as u8, self.vd(16));
        self.prop(Decor::Clutter { at: qv(at), radius, kind, count, rot }, 0.2);
    }

    pub(crate) fn brazier(&mut self, at: Vec2) {
        self.prop(Decor::Brazier { at: qv(at) }, 0.5);
    }

    /// A glowing fissure wandering from `start` roughly along `dir`.
    pub(crate) fn fissure(&mut self, start: Vec2, dir: Vec2, segs: u32, width: f32) {
        let mut p = start;
        let mut d = dir.normalize_or(Vec2::X);
        let limit = self.half - Vec2::splat(0.8);
        for _ in 0..segs {
            let jitter = Vec2::new(self.rd(-0.6, 0.6), self.rd(-0.6, 0.6));
            d = (d + jitter).normalize_or(d);
            let len = self.rd(2.5, 5.5);
            let next = (p + d * len).clamp(-limit, limit);
            if next.distance(p) < 0.5 {
                break;
            }
            self.decal(Decor::LavaCrack { from: qv(p), to: qv(next), width: q(width) });
            p = next;
        }
    }
}

// ───────────────────────────── shared pieces ─────────────────────────────

/// A straight run of columns from `a` to `z` about `spacing` apart. `door` drops the middle column,
/// leaving a gap of at least a lane; `missing` topples columns at random (a drum lies where one stood).
/// Returns the bases placed.
pub(crate) fn colonnade(
    b: &mut Builder,
    g: u16,
    (a, z): (Vec2, Vec2),
    spacing: f32,
    r: f32,
    h: f32,
    door: bool,
    missing: f32,
    (first, last): (bool, bool),
) -> Vec<Vec2> {
    let n = ((a.distance(z) / spacing).round() as usize).max(1);
    let mid = n / 2;
    let mut bases = Vec::new();
    for i in 0..=n {
        if (i == 0 && !first) || (i == n && !last) {
            continue;
        }
        if door && i == mid {
            continue;
        }
        let at = a + (z - a) * (i as f32 / n as f32);
        if i != 0 && i != n && b.lay.chance(missing) {
            if b.lay.chance(0.5) {
                let dir = rot16_dir(b.lay.range_u32(0, 16) as u8);
                let len = b.rl(2.6, 4.0);
                let fr = q(r * 0.85);
                b.chain(g, at, at + dir * len, fr, fr, |from, to| Decor::FallenColumn { from, to, radius: fr });
            } else {
                b.rubble(at, 0.8, 1.3);
            }
            continue;
        }
        let stump = b.dress.chance(0.2);
        let height = if stump { q(h * b.rd(0.22, 0.45)) } else { q(h * b.rd(0.92, 1.05)) };
        if b.circle(g, at, r, |at, radius| Decor::Pillar { at, radius, height }) {
            bases.push(qv(at));
            if stump {
                let off = rot16_dir(b.vd(16)) * (r + 0.7);
                b.rubble(at + off, 0.6, 1.0);
            }
        }
    }
    bases
}

/// A wall line along `u` (or `v`) at the fixed cross coordinate `at`, from `lo` to `hi`, broken by
/// `breaches` lane-wide gaps. Each run is its own [`Decor::Wall`].
pub(crate) fn wall_line(
    b: &mut Builder,
    g: u16,
    f: &Frame,
    (lo, hi): (f32, f32),
    at: f32,
    along_u: bool,
    t: f32,
    breaches: usize,
    style: WallStyle,
    (hmin, hmax): (f32, f32),
) {
    let (lo, hi) = (lo.min(hi), lo.max(hi));
    let len = hi - lo;
    let mut cuts: Vec<(f32, f32)> = Vec::new();
    for k in 0..breaches {
        let fr = (k as f32 + 0.5 + b.rl(-0.2, 0.2)) / breaches as f32;
        let w = b.rl(3.3, 4.4);
        let m = lo + len * fr;
        cuts.push((m - w * 0.5, m + w * 0.5));
    }
    cuts.push((hi, hi));
    let mut s0 = lo;
    for (c0, c1) in cuts {
        if c0 - s0 >= 1.2 {
            // Each run is laid as touching blocks of their own height: a ruined silhouette, and
            // short blocks still fit where a long run would clip a keep-out.
            let n = ((c0 - s0) / 3.0).ceil().max(1.0);
            let step = (c0 - s0) / n;
            for k in 0..n as usize {
                let a = s0 + step * k as f32;
                // A hair of overlap so 1/8-unit quantization never opens a sliver between blocks.
                let (m, hlen) = (a + step * 0.5, step * 0.5 + 0.07);
                let (center, half) = if along_u { (f.p(m, at), f.h(hlen, t)) } else { (f.p(at, m), f.h(t, hlen)) };
                let (height, variant) = (q(b.rd(hmin, hmax)), b.vd(4));
                b.block(g, center, half, |at, half| Decor::Wall { at, half, height, style, variant });
            }
        }
        if c1 > c0 {
            // Collapsed masonry spills through the breach.
            let m = (c0 + c1) * 0.5;
            let p = if along_u { f.p(m, at) } else { f.p(at, m) };
            b.rubble(p, 0.7, 1.2);
        }
        s0 = c1;
    }
}

/// Solitary ruin at `at` in the biome's vocabulary (its own group: a lane from everything), with up
/// to `satellites` smaller pieces heaped against it.
pub(crate) fn ruin(b: &mut Builder, at: Vec2, satellites: u32) -> bool {
    let g = b.group();
    let roll = b.lay.f32();
    let biome = b.biome;
    let placed = match biome {
        Biome::Cinder if roll < 0.4 => boulder(b, g, at, 1.2, 2.2),
        Biome::Cinder if roll < 0.65 => stump_pair(b, g, at),
        Biome::Cinder if roll < 0.85 => plinth(b, g, at, WallStyle::Plinth),
        Biome::Cinder => short_column(b, g, at),
        Biome::Verdant if roll < 0.3 => boulder(b, g, at, 1.2, 2.0),
        Biome::Verdant if roll < 0.55 => {
            // A living ancient tree: the canopy frames the field from the edges.
            let (r, height) = (b.rl(1.3, 1.7), q(b.rd(8.0, 11.0)));
            b.circle(g, at, r, |at, radius| Decor::Tree { at, radius, height, variant: 0 })
        }
        Biome::Verdant if roll < 0.75 => {
            let (r, height) = (b.rl(1.1, 1.5), q(b.rd(1.2, 2.6)));
            b.circle(g, at, r, |at, radius| Decor::Tree { at, radius, height, variant: 1 })
        }
        Biome::Verdant if roll < 0.9 => stump_pair(b, g, at),
        Biome::Verdant => plinth(b, g, at, WallStyle::Hedge),
        Biome::Spire if roll < 0.3 => boulder(b, g, at, 1.2, 2.0),
        Biome::Spire if roll < 0.6 => crystal(b, g, at, 1.0, 1.8),
        Biome::Spire if roll < 0.8 => stump_pair(b, g, at),
        Biome::Spire => plinth(b, g, at, WallStyle::Plinth),
        Biome::Unmaking if roll < 0.3 => crystal(b, g, at, 1.0, 1.8),
        Biome::Unmaking if roll < 0.6 => plinth(b, g, at, WallStyle::Monolith),
        Biome::Unmaking if roll < 0.8 => {
            let (r, height) = (b.rl(0.8, 1.1), q(b.rd(4.0, 6.5)));
            b.circle(g, at, r, |at, radius| Decor::InvertedColumn { at, radius, height })
        }
        Biome::Unmaking => boulder(b, g, at, 1.2, 2.0),
    };
    if placed {
        // Smaller pieces heaped against it: one compact ruin reads as a place, many pebbles as noise.
        let main = b.obstacles.last().map_or((at, 1.0), |o| {
            let (c, e) = extent(o);
            (c, e.max_element())
        });
        for _ in 0..satellites {
            satellite(b, g, main);
        }
        let off = rot16_dir(b.vd(16)) * b.rd(1.8, 2.8);
        if b.dress.chance(0.5) {
            b.rubble(at + off, 0.7, 1.3);
        } else {
            b.cover_patch(at + off, 1.2, 2.2);
        }
    }
    placed
}

/// A smaller piece leaning against the ruin `(centre, radius)` (same group: it may touch).
pub(crate) fn satellite(b: &mut Builder, g: u16, (c, r): (Vec2, f32)) -> bool {
    let d = rot16_dir(b.lay.range_u32(0, 16) as u8);
    let rs = b.rl(0.6, 1.0);
    let at = c + d * (r + rs - 0.2);
    let biome = b.biome;
    let roll = b.lay.f32();
    match biome {
        Biome::Unmaking if roll < 0.4 => {
            let (height, rot, variant) = (q(rs * b.rd(2.0, 3.0)), b.vd(16), b.vd(4));
            b.circle(g, at, rs, |at, radius| Decor::Crystal { at, radius, height, rot, variant })
        }
        Biome::Spire if roll < 0.25 => {
            let (height, rot, variant) = (q(rs * b.rd(2.0, 3.0)), b.vd(16), b.vd(4));
            b.circle(g, at, rs, |at, radius| Decor::Crystal { at, radius, height, rot, variant })
        }
        _ if roll < 0.55 => {
            let variant = if biome == Biome::Verdant { 1 } else { b.vd(4) };
            b.circle(g, at, rs, |at, radius| Decor::Boulder { at, radius, variant })
        }
        _ => {
            let height = q(b.rd(0.8, 2.2));
            b.circle(g, at, rs, |at, radius| Decor::Pillar { at, radius, height })
        }
    }
}

pub(crate) fn boulder(b: &mut Builder, g: u16, at: Vec2, lo: f32, hi: f32) -> bool {
    let (r, variant) = (b.rl(lo, hi), b.vd(4));
    b.circle(g, at, r, |at, radius| Decor::Boulder { at, radius, variant })
}

pub(crate) fn crystal(b: &mut Builder, g: u16, at: Vec2, lo: f32, hi: f32) -> bool {
    let r = b.rl(lo, hi);
    let (height, rot, variant) = (q(r * b.rd(2.2, 3.2)), b.vd(16), b.vd(4));
    b.circle(g, at, r, |at, radius| Decor::Crystal { at, radius, height, rot, variant })
}

pub(crate) fn plinth(b: &mut Builder, g: u16, at: Vec2, style: WallStyle) -> bool {
    let s = b.rl(0.9, 1.4);
    let half = Vec2::new(s, s * b.rl(0.7, 1.0));
    let (height, variant) = (q(b.rd(0.8, 1.6) * if style == WallStyle::Monolith { 2.5 } else { 1.0 }), b.vd(4));
    let ok = b.block(g, at, half, |at, half| Decor::Wall { at, half, height, style, variant });
    if ok && style == WallStyle::Plinth && b.biome == Biome::Cinder {
        let scale = q(b.rd(0.6, 0.9));
        b.decal(Decor::BrokenAnvil { at: qv(at), scale });
    }
    ok
}

/// Two broken column stumps leaning together.
pub(crate) fn stump_pair(b: &mut Builder, g: u16, at: Vec2) -> bool {
    let (r1, r2) = (q(b.rl(0.7, 0.95)), q(b.rl(0.6, 0.85)));
    let dir = rot16_dir(b.lay.range_u32(0, 16) as u8);
    let (h1, h2) = (q(b.rd(1.2, 2.4)), q(b.rd(0.8, 1.8)));
    let (a, z) = (qv(at), qv(at + dir * (r1 + r2 - 0.1)));
    let pieces = [Obstacle::Circle { center: a, radius: r1 }, Obstacle::Circle { center: z, radius: r2 }];
    if !pieces.iter().all(|o| b.fits(o, g)) {
        return false;
    }
    b.solid(g, &pieces[..1], Decor::Pillar { at: a, radius: r1, height: h1 });
    b.solid(g, &pieces[1..], Decor::Pillar { at: z, radius: r2, height: h2 });
    true
}

/// A short toppled column lying on the floor.
pub(crate) fn short_column(b: &mut Builder, g: u16, at: Vec2) -> bool {
    let r = q(b.rl(0.7, 0.9));
    let dir = rot16_dir(b.lay.range_u32(0, 16) as u8);
    let len = b.rl(3.0, 5.0);
    b.chain(g, at, at + dir * len, r, r, |from, to| Decor::FallenColumn { from, to, radius: r })
}

// ───────────────────────────── districts ─────────────────────────────

/// Colonnade court (every biome) or, with `cloister`, the Verdant cloister square.
fn court(b: &mut Builder, f: Frame, cloister: bool) -> Option<Rect> {
    let s = b.scale;
    let (hl, hw) = (b.rl(10.0, 13.0) * s, b.rl(7.0, 9.0) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.7);
    if c.hl < 5.5 || c.hw < 4.5 {
        return None;
    }
    let g = b.group();
    let r = q(b.rl(0.75, 0.95));
    let h = b.biome.column(&mut b.dress);
    let sp = b.rl(4.1, 4.6);
    let e = r + 0.25;
    let sides = if cloister {
        4
    } else if b.lay.chance(0.75) {
        3
    } else {
        2
    };
    let left = b.lay.chance(0.5);
    let back_door = cloister || b.lay.chance(0.3);
    let before = b.obstacles.len();
    // Courts often back onto a ruined wall, their back columns engaged in it.
    let wall_t = 0.5;
    let walled = !cloister && c.hw >= 6.0 && b.lay.chance(0.55);
    let (cl, cw) = (c.hl - e, if walled { c.hw - 2.0 * wall_t - r * 0.6 } else { c.hw - e });
    if walled {
        wall_line(b, g, &c, (-c.hl, c.hl), c.hw - wall_t, true, wall_t, 1, WallStyle::Ruin, (2.0, 4.0));
    }
    // Cloister corners are square piers instead of columns.
    let piers = cloister;
    let back = colonnade(b, g, (c.p(-cl, cw), c.p(cl, cw)), sp, r, h, back_door, 0.08, (!piers, !piers));
    let v_end = if sides == 4 { -cw } else { -cw * b.rl(0.1, 0.5) };
    for (u, on) in [(-cl, sides >= 3 || left), (cl, sides >= 3 || !left)] {
        if on {
            colonnade(b, g, (c.p(u, cw), c.p(u, v_end)), sp, r, h, cloister, 0.1, (false, sides != 4));
        }
    }
    if sides == 4 {
        colonnade(b, g, (c.p(-cl, -cw), c.p(cl, -cw)), sp, r, h, true, 0.1, (!piers, !piers));
    }
    if piers {
        let hs = q(r * 1.3);
        for (su, sv) in [(-1.0f32, -1.0f32), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)] {
            let (height, variant) = (q(h * b.rd(0.45, 0.7)), b.vd(4));
            b.block(g, c.p(su * cl, sv * cw), Vec2::splat(hs), |at, half| Decor::Wall {
                at,
                half,
                height,
                style: WallStyle::Plinth,
                variant,
            });
        }
    }
    if b.obstacles.len() == before {
        return None;
    }
    // The court floor and its centrepiece.
    let variant = b.biome.paving();
    b.decal(Decor::Paving { at: qv(c.o), half: qv(c.h(c.hl, c.hw)), variant });
    let (ir, rot) = (q((cw * 0.45).min(3.5)), b.vd(16));
    if cloister {
        let garden = q(cw * 0.6);
        b.decal(Decor::Overgrowth { at: qv(c.o), radius: garden, variant: 0 });
        let tr = b.rl(1.0, 1.25);
        let tree = cw >= 5.4 && b.lay.chance(0.6) && {
            let height = q(b.rd(7.0, 9.5));
            b.circle(g, c.o, tr, |at, radius| Decor::Tree { at, radius, height, variant: 0 })
        };
        if !tree {
            let ph = q(cw * 0.42);
            b.decal(Decor::Pool { at: qv(c.o), half: Vec2::splat(ph) });
        }
        for k in [2u8, 6, 10, 14] {
            let at = c.o + rot16_dir(k) * (cw * 0.55);
            b.clutter(at, 0.6, 1.0, Some(ClutterKind::Mushrooms));
        }
    } else {
        b.decal(Decor::FloorInlay { at: qv(c.p(0.0, -cw * 0.15)), radius: ir, rot, variant: 1, god: 0 });
        if cw >= 5.0 && b.lay.chance(0.5) {
            let sr = 1.1;
            // A lane clear of the back row: no niche behind it.
            let at = c.p(b.rl(-cl * 0.3, cl * 0.3), cw - r - sr - LANE);
            let (height, rot, god, variant) = (q(b.rd(3.2, 4.2)), c.rot(0.0, -1.0), b.god(), b.vd(4));
            b.circle(g, at, sr, |at, radius| Decor::Statue { at, radius, height, rot, god, variant });
        }
    }
    // Banners hung between the back columns, facing into the court.
    let (bh, face, god) = (q(h * 0.72), c.rot(0.0, -1.0), b.god());
    for pair in back.windows(2).step_by(2) {
        let at = qv((pair[0] + pair[1]) * 0.5);
        b.prop(Decor::Banner { at, height: bh, rot: face, god }, 0.0);
    }
    // Braziers mark the open mouth, clutter gathers in the back corners.
    for u in [-cl + 0.4, cl - 0.4] {
        b.brazier(c.p(u, -cw + 0.9));
        b.clutter(c.p(u * 0.82, cw - e - 1.3), 0.8, 1.3, None);
    }
    if b.biome == Biome::Verdant {
        for _ in 0..3 {
            let at = c.p(b.rd(-cl, cl), b.rd(-cw, cw));
            b.cover_patch(at, 1.2, 2.4);
        }
    }
    Some(c.rect())
}

/// Cinder: a collapsed forge hall around a great broken anvil.
fn forge_hall(b: &mut Builder, f: Frame) -> Option<Rect> {
    let s = b.scale;
    let (hl, hw) = (b.rl(9.5, 12.0) * s, b.rl(7.2, 8.8) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.8);
    if c.hl < 7.0 || c.hw < 6.0 {
        return None;
    }
    let g = b.group();
    let t = q(b.rl(0.55, 0.7));
    let (cl, cw) = (c.hl, c.hw);
    let before = b.obstacles.len();
    let nb = if cl > 9.0 { 2 } else { 1 };
    wall_line(b, g, &c, (-cl, cl), cw - t, true, t, nb, WallStyle::Forge, (2.2, 3.6));
    let v_end = -cw * b.rl(0.05, 0.5);
    for side in [-1.0f32, 1.0] {
        let breach = usize::from(b.lay.chance(0.45));
        wall_line(b, g, &c, (cw - 2.0 * t, v_end), side * (cl - t), false, t, breach, WallStyle::Ruin, (1.2, 3.0));
    }
    // Corner stubs at the open front.
    for side in [-1.0f32, 1.0] {
        if b.lay.chance(0.55) {
            let len = b.rl(1.6, 2.6);
            let (height, variant) = (q(b.rd(0.8, 1.8)), b.vd(4));
            b.block(g, c.p(side * (cl - len), -cw + t), c.h(len, t), |at, half| Decor::Wall {
                at,
                half,
                height,
                style: WallStyle::Ruin,
                variant,
            });
        }
    }
    if b.obstacles.len() == before {
        return None;
    }
    // The great anvil, a lane clear of the walls.
    let ra = b.rl(1.9, 2.4);
    let room_u = cl - 2.0 * t - LANE - ra;
    let room_v = cw - 2.0 * t - LANE - ra;
    let mut anvil = None;
    if room_u > 0.0 && room_v > 0.0 {
        let at = c.p(b.rl(-room_u, room_u) * 0.4, b.rl(-room_v, room_v * 0.3));
        let rot = c.rot(1.0, 0.0);
        if b.circle(g, at, ra, |at, radius| Decor::GreatAnvil { at, radius, rot }) {
            anvil = Some((qv(at), ra));
        }
    }
    // A quench trough against the back wall, clear of the anvil.
    let side = if b.lay.chance(0.5) { -1.0 } else { 1.0 };
    let trough = Obstacle::Box { center: qv(c.p(side * cl * 0.55, cw - 2.0 * t - 0.7)), half: qv(c.h(1.3, 0.7)) };
    let clear_of_anvil = anvil.is_none_or(|(at, r)| gap(&trough, &Obstacle::Circle { center: at, radius: r }) >= LANE);
    if clear_of_anvil && let Obstacle::Box { center, half } = trough {
        let (height, variant) = (q(b.rd(1.0, 1.4)), b.vd(4));
        b.solid(g, &[trough], Decor::Wall { at: center, half, height, style: WallStyle::Forge, variant });
    }
    // Dressing: slag veins from the anvil, forge clutter along the walls, fire at the mouth.
    let variant = 3;
    b.decal(Decor::Paving { at: qv(c.o), half: qv(c.h(cl - t, cw - t)), variant });
    if let Some((at, r)) = anvil {
        let k0 = b.vd(16);
        for k in 0..3u8 {
            let d = rot16_dir(k0.wrapping_add(k * 5));
            let segs = b.dress.range_u32(2, 4);
            b.fissure(at + d * (r + 0.3), d, segs, 0.35);
        }
        let off = rot16_dir(b.vd(16)) * (r + 1.6);
        let scale = q(b.rd(0.8, 1.2));
        b.prop(Decor::BrokenAnvil { at: qv(at + off), scale }, 0.3);
    }
    for u in [-cl * 0.6, cl * 0.1, cl * 0.7] {
        let kind = if b.dress.chance(0.5) { ClutterKind::Ingots } else { ClutterKind::WeaponRack };
        b.clutter(c.p(u, cw - 2.0 * t - 1.2), 0.7, 1.1, Some(kind));
    }
    b.brazier(c.p(-cl + 1.2, -cw + 1.4));
    b.brazier(c.p(cl - 1.2, -cw + 1.4));
    let chains_h = q(b.rd(4.5, 6.0));
    b.decal(Decor::Chains { from: qv(c.p(-cl + t, cw - t)), to: qv(c.p(cl - t, cw - t)), height: chains_h });
    Some(c.rect())
}

/// Cinder: a crucible hung over a molten pit, ringed by chain posts.
fn crucible_yard(b: &mut Builder, f: Frame) -> Option<Rect> {
    let rp = b.rl(2.4, 3.0) * b.scale.max(0.85);
    let post_r = q(b.rl(0.55, 0.7));
    let ring = rp + LANE + post_r + 0.3;
    let ext = ring + post_r + 0.8;
    let c = f.sub(ext, ext, &mut b.lay, 0.6);
    if c.hl < ext - 0.01 || c.hw < ext - 0.01 {
        return None;
    }
    let g = b.group();
    if !b.circle(g, c.o, rp, |at, radius| Decor::Crucible { at, radius }) {
        return None;
    }
    let base = b.lay.range_u32(0, 4) as u8;
    let skip = if b.lay.chance(0.4) { b.lay.range_u32(0, 4) as u8 } else { 9 };
    let chain_h = q(b.rd(5.0, 6.0));
    for k in 0..4u8 {
        if k == skip {
            continue;
        }
        let at = qv(c.o + rot16_dir(base + k * 4) * ring);
        let height = q(b.rd(5.0, 6.2));
        if b.circle(g, at, post_r, |at, radius| Decor::Pillar { at, radius, height }) {
            b.decal(Decor::Chains { from: at, to: qv(c.o), height: chain_h });
            if b.dress.chance(0.5) {
                let off = rot16_dir(base + k * 4 + 2) * (post_r + 1.2);
                b.clutter(at + off, 0.6, 1.0, Some(ClutterKind::Ingots));
            }
        }
    }
    // Anvil stations in the yard's back corners, between the chain posts.
    for su in [-1.0f32, 1.0] {
        if b.lay.chance(0.75) {
            let at = c.p(su * (ext - 1.6), ext - 1.4);
            let sg = b.group();
            let half = c.h(b.rl(1.0, 1.4), b.rl(0.6, 0.8));
            let (height, variant) = (q(b.rd(1.0, 1.4)), b.vd(4));
            if b.block(sg, at, half, |at, half| Decor::Wall { at, half, height, style: WallStyle::Forge, variant }) {
                let scale = q(b.rd(0.6, 0.8));
                b.decal(Decor::BrokenAnvil { at: qv(at), scale });
            }
        }
    }
    let inlay = q(rp + 1.1);
    let rot = b.vd(16);
    b.decal(Decor::FloorInlay { at: qv(c.o), radius: inlay, rot, variant: 1, god: 0 });
    b.decal(Decor::Paving { at: qv(c.o), half: qv(Vec2::splat(ext - 0.5)), variant: 3 });
    for k in 0..3u8 {
        let d = rot16_dir(base + k * 5 + 2);
        let segs = b.dress.range_u32(2, 4);
        b.fissure(c.o + d * (rp + 0.2), d, segs, 0.3);
    }
    let off = rot16_dir(b.vd(16)) * (ring + 1.8);
    let scale = q(b.rd(0.8, 1.2));
    b.prop(Decor::BrokenAnvil { at: qv(c.o + off), scale }, 0.3);
    Some(c.rect())
}

/// Cinder slag channel / Spire-Unmaking void chasm: a trench crossed by bridges (chokepoints).
fn channel(b: &mut Builder, f: Frame, void: bool) -> Option<Rect> {
    let f = f.long();
    let s = b.scale;
    let w = q(if void { b.rl(2.4, 3.0) } else { b.rl(2.0, 2.6) });
    let hl = (b.rl(14.0, 19.0) * s).min(f.hl - 0.5);
    if hl < 7.0 {
        return None;
    }
    for _attempt in 0..2 {
        let c = f.sub(hl, w * 0.5 + 3.0, &mut b.lay, 0.3);
        let nb = if hl > 10.0 { 2 } else { 1 };
        let mut gaps: Vec<(f32, f32)> = Vec::new();
        for k in 0..nb {
            let m = if nb == 1 { b.rl(-0.3, 0.3) * hl } else { (k as f32 * 2.0 - 1.0) * b.rl(0.3, 0.6) * hl };
            let gw = b.rl(3.6, 4.4);
            gaps.push((m - gw * 0.5, m + gw * 0.5));
        }
        let mut pieces = Vec::new();
        let mut s0 = -hl;
        for &(g0, g1) in gaps.iter().chain(std::iter::once(&(hl, hl))) {
            if g0 - s0 >= 1.5 {
                pieces.push(Obstacle::Box {
                    center: qv(c.p((s0 + g0) * 0.5, 0.0)),
                    half: qv(c.h((g0 - s0) * 0.5, w * 0.5)),
                });
            }
            s0 = g1;
        }
        let (from, to) = (qv(c.p(-hl, 0.0)), qv(c.p(hl, 0.0)));
        let g = b.group();
        if !b.solid(g, &pieces, Decor::Channel { from, to, width: w }) {
            continue;
        }
        for &(g0, g1) in &gaps {
            let m = (g0 + g1) * 0.5;
            let bw = q(g1 - g0 - 0.5);
            let (from, to) = (qv(c.p(m, -(w * 0.5 + 0.8))), qv(c.p(m, w * 0.5 + 0.8)));
            b.decal(Decor::Bridge { from, to, width: bw });
            b.brazier(c.p(g0 - 0.3, -(w * 0.5 + 1.3)));
            b.brazier(c.p(g1 + 0.3, w * 0.5 + 1.3));
        }
        // Banks: rubble, and slag veins (or drifting debris over the void) at the ends.
        let mut u = -hl + 1.5;
        let mut bank = 1.0;
        while u < hl - 1.0 {
            if gaps.iter().all(|&(g0, g1)| u < g0 - 1.0 || u > g1 + 1.0) {
                b.rubble(c.p(u, bank * (w * 0.5 + 1.0)), 0.5, 0.9);
            }
            bank = -bank;
            u += b.rd(3.5, 5.5);
        }
        if void {
            for _ in 0..b.dress.range_u32(4, 8) {
                let at = c.p(b.rd(-hl, hl), b.rd(-w * 0.4, w * 0.4));
                let (radius, height, variant) = (q(b.rd(0.4, 0.9)), q(b.rd(0.4, 2.0)), b.vd(4));
                b.decal(Decor::Debris { at: qv(at), radius, height, variant });
            }
        } else {
            for end in [-1.0f32, 1.0] {
                let d = c.dir(end, 0.0);
                let segs = b.dress.range_u32(2, 4);
                b.fissure(c.p(end * hl, 0.0), d, segs, 0.4);
            }
        }
        return Some(c.rect());
    }
    None
}

/// Verdant: a shallow reflecting pool between two open colonnades, a statue at its head.
fn reflecting_pool(b: &mut Builder, f: Frame) -> Option<Rect> {
    let f = f.long();
    let s = b.scale;
    let pw = b.rl(1.8, 2.5);
    let r = q(b.rl(0.8, 0.95));
    let vr = pw + 1.4 + r;
    let hl = b.rl(11.0, 15.0) * s;
    let c = f.sub(hl, vr + r + 0.5, &mut b.lay, 0.5);
    if c.hl < 7.0 || c.hw < vr + r {
        return None;
    }
    let g = b.group();
    let h = b.biome.column(&mut b.dress);
    let sp = b.rl(5.0, 5.8);
    let mut rows = Vec::new();
    for side in [-1.0f32, 1.0] {
        let a = c.p(-c.hl + 1.0, side * vr);
        let z = c.p(c.hl - 1.0, side * vr);
        rows.push((side, colonnade(b, g, (a, z), sp, r, h, false, 0.15, (true, true))));
    }
    if rows.iter().all(|(_, r)| r.is_empty()) {
        return None;
    }
    let ph = qv(c.h(c.hl - 2.2, pw));
    b.decal(Decor::Pool { at: qv(c.o), half: ph });
    let head = if b.lay.chance(0.5) { 1.0 } else { -1.0 };
    let (height, rot, god, variant) = (q(b.rd(3.5, 4.6)), c.rot(-head, 0.0), b.god(), b.vd(4));
    b.circle(g, c.p(head * (c.hl - 0.9), 0.0), 1.1, |at, radius| Decor::Statue {
        at,
        radius,
        height,
        rot,
        god,
        variant,
    });
    // The foot of the pool: two low plinths carrying fire bowls.
    for side in [-1.0f32, 1.0] {
        let hs = q(b.rl(0.55, 0.75));
        let at = c.p(-head * (c.hl - 0.9), side * (pw * 0.5 + hs + 0.9));
        let (height, variant) = (q(b.rd(0.9, 1.3)), b.vd(4));
        if b.block(g, at, Vec2::splat(hs), |at, half| Decor::Wall {
            at,
            half,
            height,
            style: WallStyle::Plinth,
            variant,
        }) {
            b.decal(Decor::Brazier { at: qv(at) });
        }
    }
    for (side, bases) in &rows {
        let (bh, face, god) = (q(h * 0.7), c.rot(0.0, -side), b.god());
        for (i, at) in bases.iter().enumerate() {
            if i % 2 == 1 {
                let at = qv(*at + c.dir(0.0, -side * (r + 0.3)));
                b.prop(Decor::Banner { at, height: bh, rot: face, god }, 0.0);
            }
        }
    }
    for _ in 0..4 {
        let at = c.p(b.rd(-c.hl + 2.5, c.hl - 2.5), b.rd(-pw, pw));
        let radius = q(b.rd(0.6, 1.1));
        b.decal(Decor::Overgrowth { at: qv(at), radius, variant: 3 });
    }
    Some(c.rect())
}

/// Verdant: a giant tree fallen across the district, its stump still standing.
fn fallen_giant(b: &mut Builder, f: Frame) -> Option<Rect> {
    let f = f.long();
    let s = b.scale;
    let rt = b.rl(1.15, 1.45);
    let len = (b.rl(15.0, 21.0) * s).min(f.hl * 2.0 - 4.0 * rt - 2.0);
    if len < 9.0 {
        return None;
    }
    // It lies across the district at a slant: steeper in squarish slots.
    let squarish = f.hl < f.hw * 1.4;
    let tilts: [u8; 2] = if squarish { [2, 14] } else { [1, 15] };
    let tilt = tilts[b.lay.range_u32(0, 2) as usize];
    let root_first = b.lay.chance(0.5);
    let knot = q(rt * 1.7);
    let g = b.group();
    let mut placed = None;
    for shrink in [1.0f32, 0.8, 0.65] {
        let len = len * shrink;
        let c = f.sub(len * 0.5 + rt * 2.0, rt * 3.0 + 1.5, &mut b.lay, 0.45);
        let dir = rot16_dir(rot_of(c.ax).wrapping_add(tilt));
        let dir = if root_first { dir } else { -dir };
        let (from, to) = (qv(c.o - dir * (len * 0.5)), qv(c.o + dir * (len * 0.5)));
        let mut pieces = vec![Obstacle::Circle { center: from, radius: knot }];
        let start = from + dir * (knot * 0.8);
        let n = ((start.distance(to) / (rt * 0.8)).ceil() as usize).max(1);
        for i in 0..=n {
            let t = i as f32 / n as f32;
            pieces.push(Obstacle::Circle { center: qv(start + (to - start) * t), radius: q(rt * (1.0 - 0.3 * t)) });
        }
        if b.solid(g, &pieces, Decor::FallenTree { from, to, radius: q(rt) }) {
            placed = Some((c, dir, from, to));
            break;
        }
    }
    let (c, dir, from, to) = placed?;
    // The stump it broke from: behind the root plate, or beside it when that is a lane.
    let sr = b.rl(1.2, 1.5);
    let height = q(b.rd(1.4, 2.4));
    for d in [-dir, dir.perp(), -dir.perp()] {
        let stump = from + d * (knot + LANE + sr + 0.4);
        if b.circle(g, stump, sr, |at, radius| Decor::Tree { at, radius, height, variant: 1 }) {
            break;
        }
    }
    // Root knots torn up where it fell, and a boulder the crown crushed.
    for (at, lo, hi) in [
        (from + dir.perp() * (knot + LANE + 1.6) + dir * 2.0, 1.1, 1.5),
        (from - dir.perp() * (knot + LANE + 1.4) + dir * 3.5, 1.0, 1.4),
        (to + dir.perp() * (rt + LANE + 1.6), 1.2, 1.8),
    ] {
        if b.lay.chance(0.7) {
            let kg = b.group();
            let (r, variant) = (b.rl(lo, hi), 1);
            b.circle(kg, at, r, |at, radius| Decor::Boulder { at, radius, variant });
        }
    }
    // Crown: ferns, broken branches, glowing fungus. Root plate: veins and surface roots.
    let radius = q(b.rd(2.8, 3.8));
    b.decal(Decor::Overgrowth { at: qv(to + dir * 1.2), radius, variant: 1 });
    for k in 0..3 {
        let off = rot16_dir(b.vd(16)) * b.rd(1.5, 3.0);
        if k == 0 {
            b.clutter(to + off, 0.7, 1.1, Some(ClutterKind::Mushrooms));
        } else {
            b.rubble(to + off, 0.7, 1.2);
        }
    }
    let k0 = b.vd(16);
    for k in 0..3u8 {
        let d = rot16_dir(k0.wrapping_add(k * 5));
        let (w, l) = (q(b.rd(0.35, 0.6)), b.rd(3.0, 5.5));
        b.decal(Decor::Roots { from: qv(from + d * knot), to: qv(from + d * (knot + l)), width: w });
        let segs = b.dress.range_u32(1, 3);
        b.fissure(from + d * (knot + l), d, segs, 0.25);
    }
    let side = c.dir(0.0, 1.0);
    for t in [0.3f32, 0.65] {
        let at = from + (to - from) * t + side * (rt + 1.4);
        b.cover_patch(at, 1.0, 1.8);
    }
    Some(c.rect())
}

/// Verdant: a root-cracked terrace edged by low root walls, an ancient tree at its corner.
fn root_terrace(b: &mut Builder, f: Frame) -> Option<Rect> {
    let s = b.scale;
    let (hl, hw) = (b.rl(9.0, 12.0) * s, b.rl(6.0, 7.5) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.85);
    if c.hl < 6.0 || c.hw < 4.5 {
        return None;
    }
    let g = b.group();
    let t = 0.45;
    let before = b.obstacles.len();
    wall_line(b, g, &c, (-c.hl, c.hl), -c.hw + t, true, t, 2, WallStyle::Hedge, (0.9, 1.4));
    let side = if b.lay.chance(0.5) { -1.0 } else { 1.0 };
    wall_line(b, g, &c, (-c.hw + 2.0 * t + LANE, c.hw), side * (c.hl - t), false, t, 1, WallStyle::Hedge, (0.9, 1.4));
    let short_end = c.hw * b.rl(-0.1, 0.3);
    wall_line(b, g, &c, (short_end, c.hw), -side * (c.hl - t), false, t, 0, WallStyle::Hedge, (0.9, 1.4));
    let tr = b.rl(1.1, 1.45);
    let tree_at = c.p(-side * (c.hl - 2.0 * t - tr - 1.2), c.hw - tr - 1.0);
    let height = q(b.rd(8.0, 11.0));
    let tree = b.circle(g, tree_at, tr, |at, radius| Decor::Tree { at, radius, height, variant: 0 });
    // A second, younger tree in the other back corner, and the altar the terrace was built for.
    let tr2 = b.rl(0.9, 1.2);
    let height2 = q(b.rd(6.5, 9.0));
    b.circle(g, c.p(side * (c.hl - 2.0 * t - tr2 - 1.2), c.hw - tr2 - 1.0), tr2, |at, radius| Decor::Tree {
        at,
        radius,
        height: height2,
        variant: 0,
    });
    let altar = c.p(b.rl(-c.hl * 0.2, c.hl * 0.2), c.hw * 0.35);
    let altar_half = c.h(b.rl(1.1, 1.5), b.rl(0.8, 1.0));
    let (altar_h, altar_v) = (q(b.rd(0.9, 1.3)), b.vd(4));
    if b.block(g, altar, altar_half, |at, half| Decor::Wall {
        at,
        half,
        height: altar_h,
        style: WallStyle::Plinth,
        variant: altar_v,
    }) {
        b.clutter(altar + c.dir(0.0, -1.0) * (altar_half.min_element() + 1.2), 0.5, 0.8, Some(ClutterKind::Candles));
    }
    if b.obstacles.len() == before {
        return None;
    }
    // Root knots heave the paving: lane-spaced from everything.
    for _ in 0..b.lay.range_u32(2, 4) {
        let at = c.p(b.rl(-c.hl * 0.6, c.hl * 0.6), b.rl(-c.hw * 0.5, c.hw * 0.2));
        let kg = b.group();
        let (r, variant) = (b.rl(1.2, 1.7), 1);
        b.circle(kg, at, r, |at, radius| Decor::Boulder { at, radius, variant });
    }
    b.decal(Decor::Paving { at: qv(c.o), half: qv(c.h(c.hl, c.hw)), variant: 3 });
    if tree {
        let k0 = b.vd(16);
        for k in 0..4u8 {
            let d = rot16_dir(k0.wrapping_add(k * 4));
            let (w, l) = (q(b.rd(0.3, 0.55)), b.rd(3.5, 7.0));
            b.decal(Decor::Roots { from: qv(tree_at + d * tr), to: qv(tree_at + d * (tr + l)), width: w });
        }
    }
    for _ in 0..3 {
        let at = c.p(b.rd(-c.hl, c.hl), b.rd(-c.hw, c.hw));
        let segs = b.dress.range_u32(2, 4);
        let d = rot16_dir(b.vd(16));
        b.fissure(at, d, segs, 0.2);
    }
    b.clutter(c.p(side * (c.hl - 1.6), c.hw - 1.6), 0.8, 1.3, Some(ClutterKind::Urns));
    let u = b.rd(-c.hl * 0.6, c.hl * 0.6);
    b.clutter(c.p(u, -c.hw + 1.6), 0.6, 1.0, Some(ClutterKind::Mushrooms));
    b.brazier(c.p(-side * (c.hl - 1.2), -c.hw + 1.6));
    for _ in 0..3 {
        let at = c.p(b.rd(-c.hl, c.hl), b.rd(-c.hw, c.hw));
        b.cover_patch(at, 1.2, 2.2);
    }
    Some(c.rect())
}

/// Spire: a broken spiral stair, its steps scattered in a spiral around it.
fn broken_stair(b: &mut Builder, f: Frame) -> Option<Rect> {
    let rs = b.rl(2.3, 2.9) * b.scale.max(0.85);
    let ext = rs + LANE + 4.5;
    let c = f.sub(ext, ext, &mut b.lay, 0.6);
    if c.hw < rs + LANE + 2.0 || c.hl < rs + LANE + 2.0 {
        return None;
    }
    let g = b.group();
    let (height, rot) = (q(b.rd(7.0, 10.0)), b.vd(16));
    if !b.circle(g, c.o, rs, |at, radius| Decor::SpiralStair { at, radius, height, rot }) {
        return None;
    }
    let k0 = b.lay.range_u32(0, 16) as u8;
    for i in 0..5u8 {
        let d = rs + LANE + 1.5 + i as f32 * 1.2;
        let at = c.o + rot16_dir(k0.wrapping_add(i * 3)) * d;
        let hs = b.rl(0.7, 1.0);
        let sg = b.group();
        let (height, variant) = (q(b.rd(0.5, 1.2)), b.vd(4));
        b.block(sg, at, Vec2::splat(hs), |at, half| Decor::Wall {
            at,
            half,
            height,
            style: WallStyle::Plinth,
            variant,
        });
    }
    let inlay = q(rs + 1.8);
    b.decal(Decor::FloorInlay { at: qv(c.o), radius: inlay, rot, variant: 2, god: 0 });
    for _ in 0..b.dress.range_u32(5, 9) {
        let at = c.o + rot16_dir(b.vd(16)) * b.rd(rs + 0.8, rs + 4.5);
        let (radius, height, variant) = (q(b.rd(0.4, 0.9)), q(b.rd(2.5, 7.5)), b.vd(4));
        b.decal(Decor::Debris { at: qv(at), radius, height, variant });
    }
    for k in [3u8, 11] {
        let at = c.o + rot16_dir(k0.wrapping_add(k)) * (rs + 2.0);
        b.clutter(at, 0.6, 1.0, Some(ClutterKind::Tomes));
    }
    b.brazier(c.o + rot16_dir(k0.wrapping_add(7)) * (rs + 1.6));
    Some(c.rect())
}

/// Spire / Unmaking: crystal outcrops, some with smaller companions leaning on them.
fn crystal_garden(b: &mut Builder, f: Frame) -> Option<Rect> {
    let s = b.scale;
    let (hl, hw) = (b.rl(8.0, 11.0) * s, b.rl(6.0, 8.0) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.6);
    if c.hl < 5.0 || c.hw < 4.0 {
        return None;
    }
    let n = b.lay.range_u32(4, 7);
    let mut placed = Vec::new();
    for _ in 0..n * 6 {
        if placed.len() as u32 >= n {
            break;
        }
        let at = c.p(b.rl(-c.hl + 1.5, c.hl - 1.5), b.rl(-c.hw + 1.5, c.hw - 1.5));
        let g = b.group();
        if crystal(b, g, at, 1.1, 2.0) {
            let r = match b.obstacles.last() {
                Some(Obstacle::Circle { radius, .. }) => *radius,
                _ => 1.0,
            };
            placed.push((qv(at), r));
            if b.lay.chance(0.4) {
                let d = rot16_dir(b.lay.range_u32(0, 16) as u8);
                let r2 = r * 0.55;
                let (height, rot, variant) = (q(r2 * b.rd(2.0, 3.0)), b.vd(16), b.vd(4));
                b.circle(g, at + d * (r + r2 - 0.25), r2, |at, radius| Decor::Crystal {
                    at,
                    radius,
                    height,
                    rot,
                    variant,
                });
            }
        }
    }
    if placed.is_empty() {
        return None;
    }
    for &(at, r) in &placed {
        let off = rot16_dir(b.vd(16)) * (r + 1.1);
        b.clutter(at + off, 0.5, 0.9, Some(ClutterKind::Shards));
        let d = rot16_dir(b.vd(16));
        let segs = b.dress.range_u32(1, 3);
        b.fissure(at + d * r, d, segs, 0.2);
        if b.biome == Biome::Spire {
            let (radius, height, variant) = (q(b.rd(0.3, 0.6)), q(b.rd(2.0, 4.5)), b.vd(4));
            let at = at + rot16_dir(b.vd(16)) * (r + 0.6);
            b.decal(Decor::Debris { at: qv(at), radius, height, variant });
        }
    }
    for _ in 0..3 {
        let at = c.p(b.rd(-c.hl, c.hl), b.rd(-c.hw, c.hw));
        b.cover_patch(at, 1.4, 2.6);
    }
    Some(c.rect())
}

/// Spire: a ring of plinths and floating debris around an orrery inlay; the centre stays open.
fn debris_ring(b: &mut Builder, f: Frame) -> Option<Rect> {
    let rr = (b.rl(6.0, 8.5) * b.scale).min(f.hw - 1.2).min(f.hl - 1.2);
    if rr < 4.5 {
        return None;
    }
    let c = f.sub(rr + 1.2, rr + 1.2, &mut b.lay, 0.5);
    let base = b.lay.range_u32(0, 4) as u8;
    let mut solid = 0;
    for k in 0..8u8 {
        let at = c.o + rot16_dir(base + k * 2) * rr;
        if k % 2 == 0 {
            let hs = b.rl(0.95, 1.3);
            let g = b.group();
            let (height, variant) = (q(b.rd(0.8, 1.4)), b.vd(4));
            if b.block(g, at, Vec2::splat(hs), |at, half| Decor::Wall {
                at,
                half,
                height,
                style: WallStyle::Plinth,
                variant,
            }) {
                solid += 1;
                if k % 4 == 0 {
                    let d = rot16_dir(base + k * 2);
                    b.brazier(at - d * (hs + 0.9));
                }
            }
        } else {
            let (radius, height, variant) = (q(b.rd(0.7, 1.2)), q(b.rd(2.5, 5.0)), b.vd(4));
            b.decal(Decor::Debris { at: qv(at), radius, height, variant });
        }
    }
    if solid == 0 {
        return None;
    }
    let inlay = q(rr - 1.5);
    let rot = b.vd(16);
    b.decal(Decor::FloorInlay { at: qv(c.o), radius: inlay, rot, variant: 2, god: 0 });
    for _ in 0..b.dress.range_u32(4, 7) {
        let at = c.o + rot16_dir(b.vd(16)) * b.rd(rr - 1.0, rr + 1.0);
        let (radius, height, variant) = (q(b.rd(0.3, 0.8)), q(b.rd(4.0, 8.0)), b.vd(4));
        b.decal(Decor::Debris { at: qv(at), radius, height, variant });
    }
    Some(c.rect())
}

/// Unmaking: the floor shattered into islands by crossing void cracks.
fn shattered_islands(b: &mut Builder, f: Frame) -> Option<Rect> {
    let f = f.long();
    let s = b.scale;
    let (hl, hw) = (b.rl(10.0, 13.0) * s, b.rl(7.0, 9.0) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.5);
    if c.hl < 7.0 || c.hw < 5.0 {
        return None;
    }
    let w = q(b.rl(1.4, 1.9));
    let va = b.rl(-0.3, 0.3) * c.hw;
    let ub = b.rl(-0.35, 0.35) * c.hl;
    // The crossing stays an open isthmus: its diagonal gaps are full lanes, never a sealed pocket.
    let cross = w * 0.5 + 2.6;
    let extra = b.rl(-0.7, 0.7) * c.hl;
    let mut placed = 0;
    // Crack along u (gaps at the crossing and one isthmus), then across it: one composition.
    let g = b.group();
    for along_u in [true, false] {
        let (lo, hi, at) = if along_u { (-c.hl + 1.0, c.hl - 1.0, va) } else { (-c.hw + 1.0, c.hw - 1.0, ub) };
        let mut gaps = vec![if along_u { (ub - cross, ub + cross) } else { (va - cross, va + cross) }];
        if along_u && (extra - ub).abs() > cross + 4.0 {
            let gw = b.rl(1.7, 2.1);
            gaps.push((extra - gw, extra + gw));
        }
        gaps.sort_by(|a, z| a.0.total_cmp(&z.0));
        let mut s0 = lo;
        for (g0, g1) in gaps.iter().copied().chain(std::iter::once((hi, hi))) {
            if g0 - s0 >= 1.5 {
                let (a, z) = if along_u { (c.p(s0, at), c.p(g0, at)) } else { (c.p(at, s0), c.p(at, g0)) };
                let m = (s0 + g0) * 0.5;
                let (center, half) = if along_u {
                    (c.p(m, at), c.h((g0 - s0) * 0.5, w * 0.5))
                } else {
                    (c.p(at, m), c.h(w * 0.5, (g0 - s0) * 0.5))
                };
                let piece = Obstacle::Box { center: qv(center), half: qv(half) };
                if b.solid(g, &[piece], Decor::Channel { from: qv(a), to: qv(z), width: w }) {
                    placed += 1;
                    for _ in 0..2 {
                        let t = b.rd(0.1, 0.9);
                        let at = a + (z - a) * t;
                        let (radius, height, variant) = (q(b.rd(0.4, 0.9)), q(b.rd(0.5, 3.0)), b.vd(4));
                        b.decal(Decor::Debris { at: qv(at), radius, height, variant });
                    }
                }
            }
            s0 = g1;
        }
    }
    if placed == 0 {
        return None;
    }
    // Monoliths drift over the larger islands.
    for _ in 0..b.lay.range_u32(2, 4) {
        let at = c.p(b.rl(-c.hl * 0.7, c.hl * 0.7), b.rl(-c.hw * 0.7, c.hw * 0.7));
        let g = b.group();
        plinth(b, g, at, WallStyle::Monolith);
    }
    let rot = b.vd(16);
    let inlay_at =
        c.p(if ub > 0.0 { -c.hl * 0.5 } else { c.hl * 0.5 }, if va > 0.0 { -c.hw * 0.5 } else { c.hw * 0.5 });
    b.decal(Decor::FloorInlay { at: qv(inlay_at), radius: 2.5, rot, variant: 4, god: 2 });
    for _ in 0..3 {
        let at = c.p(b.rd(-c.hl, c.hl), b.rd(-c.hw, c.hw));
        b.cover_patch(at, 1.2, 2.4);
    }
    Some(c.rect())
}

/// Unmaking: standing tears in reality, each bleeding chaos cracks.
fn rift_field(b: &mut Builder, f: Frame) -> Option<Rect> {
    let s = b.scale;
    let (hl, hw) = (b.rl(9.0, 12.0) * s, b.rl(6.0, 8.0) * s);
    let c = f.sub(hl, hw, &mut b.lay, 0.5);
    if c.hl < 5.0 || c.hw < 4.0 {
        return None;
    }
    let n = b.lay.range_u32(4, 7);
    let mut rifts = Vec::new();
    for _ in 0..n * 6 {
        if rifts.len() as u32 >= n {
            break;
        }
        let at = c.p(b.rl(-c.hl + 1.5, c.hl - 1.5), b.rl(-c.hw + 1.5, c.hw - 1.5));
        let g = b.group();
        let r = b.rl(0.9, 1.3);
        let (height, rot) = (q(b.rd(4.0, 7.0)), b.vd(16));
        if b.circle(g, at, r, |at, radius| Decor::Rift { at, radius, height, rot }) {
            rifts.push((qv(at), r));
        }
    }
    if rifts.is_empty() {
        return None;
    }
    let g = b.group();
    let at = c.p(b.rl(-c.hl * 0.6, c.hl * 0.6), b.rl(-c.hw * 0.6, c.hw * 0.6));
    plinth(b, g, at, WallStyle::Monolith);
    for &(at, r) in &rifts {
        let k0 = b.vd(16);
        for k in 0..b.dress.range_u32(1, 3) as u8 {
            let d = rot16_dir(k0.wrapping_add(k * 7));
            b.fissure(at + d * (r + 0.2), d, 1, 0.25);
        }
        for _ in 0..2 {
            let p = at + rot16_dir(b.vd(16)) * b.rd(r + 0.8, r + 2.2);
            let (radius, height, variant) = (q(b.rd(0.3, 0.7)), q(b.rd(1.5, 5.0)), b.vd(4));
            b.decal(Decor::Debris { at: qv(p), radius, height, variant });
        }
    }
    let (at, r) = rifts[0];
    let d = rot16_dir(b.vd(16));
    b.clutter(at + d * (r + 1.4), 0.6, 1.0, Some(ClutterKind::Shards));
    Some(c.rect())
}

/// Unmaking: a nave of columns standing on their capitals at irregular spacings.
fn inverted_nave(b: &mut Builder, f: Frame) -> Option<Rect> {
    let f = f.long();
    let s = b.scale;
    let hl = b.rl(10.0, 14.0) * s;
    let vr = b.rl(3.8, 5.0);
    let r = q(b.rl(1.0, 1.25));
    let c = f.sub(hl, vr + r + 1.0, &mut b.lay, 0.5);
    if c.hl < 7.0 || c.hw < vr + r {
        return None;
    }
    let g = b.group();
    let mut placed = 0;
    let mut tops = Vec::new();
    for side in [-1.0f32, 1.0] {
        let stagger = if side > 0.0 { b.rl(0.0, 2.5) } else { 0.0 };
        let mut u = -c.hl + r + 0.5 + stagger;
        while u <= c.hl - r - 0.5 {
            let v = side * (vr + b.rl(-0.5, 0.5));
            let at = c.p(u, v);
            if b.lay.chance(0.18) {
                let (radius, height, variant) = (q(r * 1.1), q(b.rd(5.0, 8.0)), b.vd(4));
                b.decal(Decor::Debris { at: qv(at), radius, height, variant });
            } else {
                let height = q(b.rd(6.0, 9.0));
                if b.circle(g, at, r, |at, radius| Decor::InvertedColumn { at, radius, height }) {
                    placed += 1;
                    tops.push((qv(at), side));
                }
            }
            u += b.rl(5.0, 6.8);
        }
    }
    if placed == 0 {
        return None;
    }
    let rot = b.vd(16);
    b.decal(Decor::FloorInlay { at: qv(c.o), radius: q(vr - 1.2), rot, variant: 4, god: 2 });
    b.fissure(c.p(-c.hl * 0.85, 0.0), c.dir(1.0, 0.0), 5, 0.3);
    let god = b.god();
    for (i, (at, side)) in tops.iter().enumerate() {
        if i % 3 == 0 {
            let height = q(b.rd(4.0, 6.0));
            let at = qv(*at + c.dir(0.0, -side * (r + 0.3)));
            b.prop(Decor::Banner { at, height, rot: c.rot(0.0, -side), god }, 0.0);
        }
    }
    Some(c.rect())
}

/// An open killing field: a few solitary ruins, ground cover and fissures.
pub(crate) fn field(b: &mut Builder, f: Frame) -> Option<Rect> {
    let area = f.hl * f.hw * 4.0;
    let n = if area > 600.0 { 2 } else { 1 };
    let mut placed = 0;
    for _ in 0..n * 5 {
        if placed >= n {
            break;
        }
        let at = f.p(b.rl(-f.hl + 2.0, f.hl - 2.0), b.rl(-f.hw + 2.0, f.hw - 2.0));
        let sat = b.lay.range_u32(0, 2);
        if ruin(b, at, sat) {
            placed += 1;
        }
    }
    for _ in 0..b.dress.range_u32(2, 5) {
        let at = f.p(b.rd(-f.hl, f.hl), b.rd(-f.hw, f.hw));
        b.cover_patch(at, 1.5, 3.2);
    }
    for _ in 0..b.dress.range_u32(1, 3) {
        let at = f.p(b.rd(-f.hl, f.hl), b.rd(-f.hw, f.hw));
        b.rubble(at, 0.8, 1.5);
    }
    let at = f.p(b.rd(-f.hl, f.hl), b.rd(-f.hw, f.hw));
    let d = rot16_dir(b.vd(16));
    let segs = b.dress.range_u32(2, 5);
    b.fissure(at, d, segs, 0.3);
    if b.dress.chance(0.5) {
        let at = f.p(b.rd(-f.hl, f.hl), b.rd(-f.hw, f.hw));
        b.clutter(at, 0.6, 1.0, Some(ClutterKind::Bones));
    }
    Some(f.rect())
}

/// Build district `kind` in frame `f`; on failure nothing it tried is left behind.
pub(crate) fn stamp(b: &mut Builder, kind: DistrictKind, f: Frame) -> Option<Rect> {
    use DistrictKind::*;
    let (obstacles, decor) = (b.obstacles.len(), b.decor.len());
    let built = match kind {
        ColonnadeCourt => court(b, f, false),
        Cloister => court(b, f, true),
        ForgeHall => forge_hall(b, f),
        SlagChannel => channel(b, f, false),
        VoidChasm => channel(b, f, true),
        CrucibleYard => crucible_yard(b, f),
        RootTerrace => root_terrace(b, f),
        ReflectingPool => reflecting_pool(b, f),
        FallenGiant => fallen_giant(b, f),
        BrokenStair => broken_stair(b, f),
        CrystalGarden => crystal_garden(b, f),
        DebrisRing => debris_ring(b, f),
        ShatteredIslands => shattered_islands(b, f),
        RiftField => rift_field(b, f),
        InvertedNave => inverted_nave(b, f),
        Field | Plaza => field(b, f),
    };
    if built.is_none() {
        // Stamps only fail before laying a solid; drop any dressing they scattered first.
        debug_assert_eq!(b.obstacles.len(), obstacles, "{kind:?} failed after placing solids");
        b.decor.truncate(decor);
    }
    built
}

// ───────────────────────────── landmarks ─────────────────────────────

/// Obstacle and decor of a monument at `at` facing `rot`; `grand` monuments stand on the axis.
pub(crate) fn monument(b: &mut Builder, m: MapMark, at: Vec2, rot: Rot16, grand: bool) -> (Obstacle, Decor) {
    let at = qv(at);
    let k = if grand { 1.0 } else { 0.8 };
    let circle = |r: f32| Obstacle::Circle { center: at, radius: q(r) };
    match m {
        MapMark::Statue => {
            let r = q(b.rl(2.1, 2.5) * k);
            let (height, god, variant) = (q(b.rd(7.0, 9.0) * k), b.god(), b.vd(4));
            let variant = if b.biome == Biome::Unmaking { 2 } else { variant };
            (circle(r), Decor::Statue { at, radius: r, height, rot, god, variant })
        }
        MapMark::GreatBrazier => {
            let r = q(b.rl(1.6, 2.0) * k.max(0.9));
            (circle(r), Decor::GreatBrazier { at, radius: r })
        }
        MapMark::SealedGate => {
            let half = qv(Vec2::new(b.rl(3.0, 3.8), b.rl(0.9, 1.1)));
            let height = q(b.rd(7.0, 9.0));
            (Obstacle::Box { center: at, half }, Decor::SealedGate { at, half, height })
        }
        MapMark::Tree => {
            let r = q(b.rl(1.4, 1.8) * k.max(0.85));
            let height = q(b.rd(10.0, 13.0) * k);
            (circle(r), Decor::Tree { at, radius: r, height, variant: 0 })
        }
        MapMark::SpiralStair => {
            let r = q(b.rl(2.4, 2.9));
            let height = q(b.rd(8.0, 11.0));
            (circle(r), Decor::SpiralStair { at, radius: r, height, rot })
        }
        MapMark::InvertedColumn => {
            let r = q(b.rl(1.5, 1.9) * k.max(0.8));
            let height = q(b.rd(9.0, 12.0) * k);
            (circle(r), Decor::InvertedColumn { at, radius: r, height })
        }
        MapMark::Rift => {
            let r = q(b.rl(1.1, 1.4));
            let height = q(b.rd(6.0, 8.0) * k);
            (circle(r), Decor::Rift { at, radius: r, height, rot: rot.wrapping_add(4) })
        }
        MapMark::Crystal => {
            let r = q(b.rl(1.6, 2.0) * k);
            let (height, variant) = (q(b.rd(5.0, 7.0)), b.vd(4));
            (circle(r), Decor::Crystal { at, radius: r, height, rot, variant })
        }
        // Map-scale landmarks (region sites on biome maps); rooms never pick these.
        MapMark::ColossusHead => {
            let r = q(b.rl(2.6, 3.3) * k);
            let variant = b.vd(4);
            (circle(r), Decor::ColossusHead { at, radius: r, rot, variant })
        }
        MapMark::GreatAnvil => {
            let r = q(b.rl(2.2, 2.8) * k);
            (circle(r), Decor::GreatAnvil { at, radius: r, rot })
        }
        MapMark::Crucible => {
            let r = q(b.rl(2.4, 3.0) * k.max(0.85));
            (circle(r), Decor::Crucible { at, radius: r })
        }
        MapMark::FallenWeapon => {
            let r = q(b.rl(2.2, 3.0) * k);
            let (height, variant) = (q(b.rd(14.0, 20.0) * k), b.vd(5));
            (circle(r), Decor::FallenWeapon { at, radius: r, height, rot, variant })
        }
    }
}

pub(crate) fn pick_mark(b: &mut Builder, opts: &[(MapMark, f32)]) -> MapMark {
    let w: Vec<f32> = opts.iter().map(|o| o.1).collect();
    opts[b.lay.weighted_index(&w).unwrap_or(0)].0
}

/// Monuments framing the plaza: one on the axis toward the gates, or a pair flanking the central
/// lane. Placed before the districts so the districts build around them.
fn frame_plaza(b: &mut Builder, plaza: f32, center_gate: bool) {
    let top = b.half.y - RIM;
    if !center_gate {
        let marks = b.biome.axis_marks();
        let m = pick_mark(b, marks);
        let jitter = b.rl(0.0, 3.0);
        for step in 0..10 {
            let y = plaza + 4.2 + jitter + step as f32;
            let (o, d) = monument(b, m, Vec2::new(0.0, y), 12, true);
            let (_, e) = extent(&o);
            if y + e.y > top {
                break;
            }
            let g = b.group();
            if b.solid(g, &[o], d) {
                let (c, e) = extent(&o);
                forecourt(b, plaza, c, e);
                break;
            }
        }
        return;
    }
    let marks = b.biome.pair_marks();
    let m = pick_mark(b, marks);
    let dx = b.rl(1.0, 2.5);
    for step in 0..12 {
        let y = plaza * 0.6 + step as f32;
        let (ol, dl) = monument(b, m, Vec2::ZERO, 0, false);
        let r = extent(&ol).1.x;
        let x = AXIS_W * 0.5 + r + dx;
        let left = monument_at(ol, dl, Vec2::new(-x, y), 14);
        let right = monument_at(ol, dl, Vec2::new(x, y), 10);
        let (gl, gr) = (b.group(), b.group());
        if b.fits(&left.0, gl) && b.fits(&right.0, gr) {
            b.solid(gl, &[left.0], left.1);
            b.solid(gr, &[right.0], right.1);
            for (side, (o, _)) in [(-1.0f32, left), (1.0, right)] {
                let (c, e) = extent(&o);
                b.brazier(c + Vec2::new(side * (e.x + 1.2), -e.y * 0.6));
                let rot = b.vd(16);
                b.decal(Decor::FloorInlay {
                    at: qv(c + Vec2::new(0.0, -e.y - 1.4)),
                    radius: 1.2,
                    rot,
                    variant: 3,
                    god: b.biome.gods()[0],
                });
            }
            break;
        }
    }
}

/// Arches spanning the processional lanes: a triumphal arch between the entrance and the plaza,
/// and matching arches on the side-gate lanes. Their piers stand just outside the lane.
fn arches(b: &mut Builder, plaza: f32, kind: RoomKind) {
    let p_axis = match kind {
        RoomKind::Combat | RoomKind::Elite => 0.65,
        RoomKind::Anvil => 0.4,
        _ => 0.25,
    };
    if b.lay.chance(p_axis) {
        let pier = q(b.rl(0.7, 0.9));
        let x = AXIS_W * 0.5 + pier + 0.25;
        let mid = (b.spawn.y + 7.0 - plaza) * 0.5;
        for dy in [0.0f32, -1.0, 1.0, -2.0, 2.0, -3.0] {
            if arch(b, Vec2::new(-x, mid + dy), Vec2::new(x, mid + dy), pier) {
                break;
            }
        }
    }
    let side: Vec<Vec2> = b.exits.iter().filter(|e| e.x != 0.0).copied().collect();
    if !side.is_empty() && b.lay.chance(0.5) {
        let pier = q(b.rl(0.65, 0.85));
        let x = LANE_W * 0.5 + pier + 0.25;
        for e in side {
            for dy in [7.5f32, 8.5, 9.5, 11.0] {
                if arch(b, Vec2::new(e.x - x, e.y - dy), Vec2::new(e.x + x, e.y - dy), pier) {
                    break;
                }
            }
        }
    }
}

pub(crate) fn arch(b: &mut Builder, from: Vec2, to: Vec2, pier: f32) -> bool {
    let (from, to, pier) = (qv(from), qv(to), q(pier));
    let half = Vec2::splat(pier);
    let pieces = [Obstacle::Box { center: from, half }, Obstacle::Box { center: to, half }];
    let (height, variant) = (q(b.rd(5.0, 7.0)), u8::from(b.dress.chance(0.25)));
    let g = b.group();
    if !b.solid(g, &pieces, Decor::Arch { from, to, pier, height, variant }) {
        return false;
    }
    let mid = qv((from + to) * 0.5);
    if variant == 1 {
        let radius = q(b.rd(0.9, 1.3));
        b.decal(Decor::Rubble { at: mid, radius, variant: 0 });
    } else {
        // A banner hangs from the lintel over the lane.
        let god = b.god();
        b.decal(Decor::Banner { at: mid, height: q(height - 0.4), rot: 12, god });
    }
    true
}

/// Move a monument built at the origin to `at`, facing `rot`.
pub(crate) fn monument_at(o: Obstacle, d: Decor, at: Vec2, rot: Rot16) -> (Obstacle, Decor) {
    let at = qv(at);
    let o = match o {
        Obstacle::Circle { radius, .. } => Obstacle::Circle { center: at, radius },
        Obstacle::Box { half, .. } => Obstacle::Box { center: at, half },
    };
    let d = match d {
        Decor::Statue { radius, height, god, variant, .. } => Decor::Statue { at, radius, height, rot, god, variant },
        Decor::GreatBrazier { radius, .. } => Decor::GreatBrazier { at, radius },
        Decor::Tree { radius, height, variant, .. } => Decor::Tree { at, radius, height, variant },
        Decor::InvertedColumn { radius, height, .. } => Decor::InvertedColumn { at, radius, height },
        Decor::Rift { radius, height, .. } => Decor::Rift { at, radius, height, rot: rot.wrapping_add(4) },
        Decor::Crystal { radius, height, variant, .. } => Decor::Crystal { at, radius, height, rot, variant },
        Decor::SpiralStair { radius, height, .. } => Decor::SpiralStair { at, radius, height, rot },
        Decor::SealedGate { half, height, .. } => Decor::SealedGate { at, half, height },
        Decor::ColossusHead { radius, variant, .. } => Decor::ColossusHead { at, radius, rot, variant },
        Decor::GreatAnvil { radius, .. } => Decor::GreatAnvil { at, radius, rot },
        Decor::Crucible { radius, .. } => Decor::Crucible { at, radius },
        Decor::FallenWeapon { radius, height, variant, .. } => Decor::FallenWeapon { at, radius, height, rot, variant },
        other => other,
    };
    (o, d)
}

/// Paved approach from the plaza to the axis monument, braziers and offerings at its foot.
fn forecourt(b: &mut Builder, plaza: f32, at: Vec2, e: Vec2) {
    let front = at.y - e.y;
    if front > plaza {
        let half = qv(Vec2::new(e.x + 2.0, (front - plaza) * 0.5 + 0.5));
        let variant = b.biome.paving();
        b.decal(Decor::Paving { at: qv(Vec2::new(0.0, (front + plaza) * 0.5)), half, variant });
    }
    let (god, rot) = (b.god(), b.vd(16));
    b.decal(Decor::FloorInlay { at: qv(Vec2::new(0.0, front - 1.8)), radius: 1.4, rot, variant: 3, god });
    for side in [-1.0f32, 1.0] {
        b.brazier(Vec2::new(side * (e.x + 1.6), at.y - e.y * 0.3));
        let kind = if b.dress.chance(0.5) { ClutterKind::Candles } else { ClutterKind::Offerings };
        b.clutter(Vec2::new(side * (e.x * 0.7 + 0.4), front - 0.9), 0.5, 0.8, Some(kind));
        let height = q(b.rd(4.0, 5.5));
        b.prop(Decor::Banner { at: qv(Vec2::new(side * (e.x + 0.9), at.y + e.y * 0.5)), height, rot: 12, god }, 0.0);
    }
}

/// A fallen colossus head lying beside the plaza, gazing at it.
fn colossus(b: &mut Builder, plaza: f32) {
    let r = q(b.rl(2.6, 3.3));
    let dirs = [10u8, 14, 9, 15, 11, 13, 6, 2];
    let start = b.lay.range_u32(0, dirs.len() as u32) as usize;
    for i in 0..dirs.len() {
        let k = dirs[(start + i) % dirs.len()];
        for extra in [3.0f32, 5.0, 7.5] {
            let at = qv(rot16_dir(k) * (plaza + r + extra));
            let rot = rot_of(-at);
            let variant = b.vd(4);
            let g = b.group();
            if b.circle(g, at, r, |at, radius| Decor::ColossusHead { at, radius, rot, variant }) {
                for _ in 0..2 {
                    let off = rot16_dir(b.vd(16)) * b.rd(r + 1.0, r + 2.2);
                    b.rubble(at + off, 0.8, 1.4);
                }
                let d = rot16_dir(rot.wrapping_add(8));
                let segs = b.dress.range_u32(2, 4);
                b.fissure(at + d * r, d, segs, 0.3);
                let d = rot16_dir(b.vd(16));
                b.cover_patch(at + d * (r + 0.8), 1.4, 2.4);
                return;
            }
        }
    }
}

// ───────────────────────────── skeleton ─────────────────────────────

struct Slot {
    rect: Rect,
    /// Direction the composition turns its back to (the rim it hugs).
    back: Vec2,
    /// Direction compositions slide toward (away from a gate), and how strongly.
    away: Vec2,
    slide: f32,
    south: bool,
    /// Leftover strip: only ever an open field.
    strip: bool,
}

impl Slot {
    fn frame(&self, flip_u: bool) -> Frame {
        Frame { slide: self.slide, ..Frame::of(self.rect, self.back, self.away, flip_u) }
    }
}

/// Lay the processional lanes and cut the field into district slots.
fn skeleton(b: &mut Builder, exits: &[Vec2], spawn: Vec2, kind: RoomKind) -> Vec<Slot> {
    let (hx, hy) = (b.half.x, b.half.y);
    let p_merge = match kind {
        RoomKind::Treasure => 1.0,
        RoomKind::Anvil => 0.45,
        _ => 0.3,
    };
    b.lanes.push(Lane { from: Vec2::new(0.0, spawn.y), to: Vec2::ZERO, width: AXIS_W });
    if let Some(e) = exits.iter().find(|e| e.x == 0.0) {
        b.lanes.push(Lane { from: Vec2::ZERO, to: *e, width: AXIS_W });
    }
    let out = hx - RIM;
    let (top, bot) = (hy - RIM, -(hy - RIM));
    let s_in = AXIS_W * 0.5 + PAD;
    let mut slots = Vec::new();
    for sign in [-1.0f32, 1.0] {
        let cy = q(b.rl(-2.0, 3.0));
        let merge = b.lay.chance(p_merge);
        let gate = exits.iter().find(|e| e.x * sign > 0.0).copied();
        if let Some(e) = gate {
            b.lanes.push(Lane { from: e, to: Vec2::new(e.x, cy), width: LANE_W });
            b.lanes.push(Lane { from: Vec2::new(e.x, cy), to: Vec2::new(0.0, cy), width: LANE_W });
        }
        if !merge {
            let inner = gate.map_or(0.0, |e| e.x);
            b.lanes.push(Lane { from: Vec2::new(sign * hx, cy), to: Vec2::new(inner, cy), width: LANE_W });
        }
        let n_in = gate.map_or(s_in, |e| e.x.abs() + LANE_W * 0.5 + PAD);
        let rect = |x0: f32, x1: f32, y0: f32, y1: f32| Rect::new(Vec2::new(sign * x0, y0), Vec2::new(sign * x1, y1));
        let (y_n, y_s) = (cy + LANE_W * 0.5 + PAD, cy - LANE_W * 0.5 - PAD);
        let flank = Vec2::new(sign, 0.0);
        let none = Vec2::ZERO;
        if merge {
            slots.push(Slot {
                rect: rect(n_in, out, bot, top),
                back: flank,
                away: none,
                slide: 0.0,
                south: false,
                strip: false,
            });
            if n_in - PAD - s_in >= 8.0 {
                let r = rect(s_in, n_in - PAD, bot, y_s);
                slots.push(Slot { rect: r, back: flank, away: none, slide: 0.0, south: true, strip: true });
            }
        } else {
            // North slots hug the backdrop when wide, the flank when narrow; either way their
            // compositions slide away from the gate standing at their inner top corner.
            let r = rect(n_in, out, y_n, top);
            let slot = if r.size().x >= r.size().y * 0.9 {
                Slot { rect: r, back: Vec2::Y, away: flank, slide: 0.55, south: false, strip: false }
            } else {
                Slot { rect: r, back: flank, away: Vec2::NEG_Y, slide: 0.45, south: false, strip: false }
            };
            slots.push(slot);
            slots.push(Slot {
                rect: rect(s_in, out, bot, y_s),
                back: flank,
                away: none,
                slide: 0.0,
                south: true,
                strip: false,
            });
        }
    }
    slots.retain(|s| s.rect.size().x >= 8.0 && s.rect.size().y >= 8.0);
    slots
}

// ───────────────────────────── dressing ─────────────────────────────

/// Plaza mosaic, entrance pad, gate framing and the braziers that light them; a treasure room's
/// hoard spills around its plaza.
fn dress_heart(b: &mut Builder, plaza: f32, kind: RoomKind) {
    let rot = b.vd(16);
    if kind == RoomKind::Treasure {
        for k in 0..6u8 {
            let at = rot16_dir(rot.wrapping_add(k * 3)) * (plaza + b.rd(0.8, 2.2));
            b.clutter(at, 0.7, 1.2, Some(ClutterKind::Offerings));
        }
    }
    if kind == RoomKind::Anvil {
        b.decal(Decor::FloorInlay { at: Vec2::ZERO, radius: 4.5, rot, variant: 1, god: 0 });
        b.decal(Decor::FloorInlay { at: Vec2::ZERO, radius: q(plaza - 0.8), rot, variant: 0, god: 0 });
    } else {
        b.decal(Decor::FloorInlay { at: Vec2::ZERO, radius: q(plaza - 0.9), rot, variant: 0, god: 0 });
        // The heart of the mosaic speaks the biome: a forge god's sigil, a rune ring, a clockface,
        // a chaos glyph.
        let (variant, god) = match b.biome {
            Biome::Cinder => (3, 0),
            Biome::Verdant => (1, 4),
            Biome::Spire => (2, 3),
            Biome::Unmaking => (4, 2),
        };
        b.decal(Decor::FloorInlay { at: Vec2::ZERO, radius: 2.5, rot: rot.wrapping_add(2), variant, god });
    }
    for k in [2u8, 6, 10, 14] {
        b.brazier(rot16_dir(k) * (plaza + 0.3));
    }
    let spawn = b.spawn;
    let variant = b.biome.paving();
    b.decal(Decor::Paving { at: qv(spawn + Vec2::new(0.0, -0.5)), half: Vec2::new(3.5, 2.5), variant });
    for side in [-1.0f32, 1.0] {
        b.brazier(spawn + Vec2::new(side * 3.4, 2.4));
    }
    let hy = b.half.y;
    for e in b.exits.clone() {
        let god = b.god();
        let rot = b.vd(16);
        b.decal(Decor::FloorInlay { at: qv(e + Vec2::new(0.0, -0.8)), radius: 2.2, rot, variant: 1, god });
        for side in [-1.0f32, 1.0] {
            b.prop(Decor::Brazier { at: qv(e + Vec2::new(side * 3.2, -1.0)) }, 0.5);
            let height = q(b.rd(4.5, 5.5));
            b.decal(Decor::Banner { at: qv(Vec2::new(e.x + side * 2.4, hy - 0.15)), height, rot: 12, god });
        }
    }
}

/// Dense, purposeful dressing along the rim: banners and clutter at the foot of the north wall,
/// rubble and cover on the flanks, rich clusters in the back corners, a low south edge.
fn dress_rim(b: &mut Builder, rim: RimStyle) {
    let (hx, hy) = (b.half.x, b.half.y);
    let exits = b.exits.clone();
    let mut x = -hx + 2.0 + b.rd(0.0, 2.0);
    let mut k = 0;
    while x < hx - 2.0 {
        if exits.iter().all(|e| (e.x - x).abs() > 4.8) {
            if k % 2 == 0 {
                let (height, god) = (q(b.rd(4.0, 5.5)), b.god());
                b.decal(Decor::Banner { at: qv(Vec2::new(x, hy - 0.15)), height, rot: 12, god });
            }
            let at = Vec2::new(x + b.rd(-0.8, 0.8), hy - b.rd(0.9, 1.6));
            if b.dress.chance(0.7) {
                b.clutter(at, 0.9, 1.4, None);
            } else {
                b.rubble(at, 0.9, 1.4);
            }
            k += 1;
        }
        x += b.rd(5.0, 8.0);
    }
    for side in [-1.0f32, 1.0] {
        let edge = if side < 0.0 { rim.west } else { rim.east };
        let mut y = -hy + 3.0 + b.rd(0.0, 2.0);
        let mut k = 0;
        while y < hy - 3.0 {
            let at = Vec2::new(side * (hx - b.rd(0.8, 1.6)), y);
            match edge {
                RimEdge::Thicket => b.cover_patch(at, 1.6, 2.8),
                RimEdge::Balustrade if k % 2 == 0 => b.clutter(at, 0.7, 1.1, Some(ClutterKind::Urns)),
                RimEdge::Shattered => {
                    let (radius, height, variant) = (q(b.rd(0.5, 1.2)), q(b.rd(0.5, 3.0)), b.vd(4));
                    b.decal(Decor::Debris { at: qv(at + Vec2::new(side * 1.2, 0.0)), radius, height, variant });
                }
                _ if k % 3 == 1 => b.clutter(at, 0.8, 1.2, None),
                _ => b.rubble(at, 0.8, 1.5),
            }
            k += 1;
            y += b.rd(4.5, 7.5);
        }
        // Back corner: the richest cluster, lit.
        let corner = Vec2::new(side * (hx - 2.2), hy - 2.2);
        let kind = if b.dress.chance(0.5) { ClutterKind::Crates } else { ClutterKind::Urns };
        b.clutter(corner, 1.3, 1.8, Some(kind));
        b.brazier(Vec2::new(side * (hx - 1.2), hy - 4.2));
        b.rubble(Vec2::new(side * (hx - 4.2), hy - 1.2), 0.8, 1.3);
        // Front corner: low.
        b.rubble(Vec2::new(side * (hx - 1.8), -hy + 1.8), 1.0, 1.6);
        b.cover_patch(Vec2::new(side * (hx - 4.0), -hy + 1.2), 1.4, 2.4);
    }
    let mut x = -hx + 3.0 + b.rd(0.0, 3.0);
    while x < hx - 3.0 {
        if x.abs() > 6.0 {
            let at = Vec2::new(x, -hy + b.rd(0.6, 1.2));
            if b.dress.chance(0.5) {
                b.rubble(at, 0.6, 1.1);
            } else {
                b.cover_patch(at, 1.0, 2.0);
            }
        }
        x += b.rd(7.0, 11.0);
    }
}

/// Floor life: fissures seeping in from the abyss, cover and rubble at the feet of the ruins.
fn dress_floor(b: &mut Builder, plaza: f32) {
    let (hx, hy) = (b.half.x, b.half.y);
    let n = b.dress.range_u32(3, 6);
    for _ in 0..n {
        let (start, dir) = match b.dress.range_u32(0, 3) {
            0 => (Vec2::new(b.rd(-hx + 4.0, hx - 4.0), -hy + 0.5), Vec2::Y),
            1 => (Vec2::new(-hx + 0.5, b.rd(-hy + 4.0, hy - 4.0)), Vec2::X),
            _ => (Vec2::new(hx - 0.5, b.rd(-hy + 4.0, hy - 4.0)), Vec2::NEG_X),
        };
        if start.length() < plaza + 4.0 {
            continue;
        }
        let segs = b.dress.range_u32(2, 5);
        let width = b.rd(0.25, 0.5);
        b.fissure(start, dir, segs, width);
    }
    let bases: Vec<(Vec2, f32)> = b
        .obstacles
        .iter()
        .map(|o| {
            let (c, e) = extent(o);
            (c, e.max_element())
        })
        .collect();
    for (i, (c, r)) in bases.into_iter().enumerate() {
        if i % 3 != 0 {
            continue;
        }
        let at = c + rot16_dir(b.vd(16)) * (r + b.rd(0.6, 1.4));
        if b.dress.chance(0.5) {
            b.cover_patch(at, 0.9, 1.8);
        } else {
            b.rubble(at, 0.5, 1.0);
        }
    }
}

// ───────────────────────────── generate ─────────────────────────────

/// Generate a layout from a template. Pure and deterministic in (`template`, `seed`).
pub fn generate(t: &RoomDef, seed: u32) -> RoomDef {
    let root = GfRng::new(seed as u64 ^ key_hash(&t.key).rotate_left(17));
    let mut lay = root.fork(1);
    let dress = root.fork(2);
    let (hx, hy) = match t.kind {
        RoomKind::Combat | RoomKind::Elite => (lay.range_f32(40.0, 52.0), lay.range_f32(27.0, 34.0)),
        RoomKind::Anvil => (lay.range_f32(30.0, 36.0), lay.range_f32(21.0, 25.0)),
        _ => (lay.range_f32(24.0, 30.0), lay.range_f32(17.0, 21.0)),
    };
    let half = qv(Vec2::new(hx, hy));
    let player_spawn = qv(Vec2::new(0.0, -half.y + 6.0));
    let gate_y = half.y - 1.5;
    let spread = lay.range_f32(0.36, 0.48);
    // The template decides how many reward doors the room offers (a pacing knob: more doors
    // means more choice), the generator where the gates stand on the north rim.
    let exits: Vec<Vec2> = match t.exits.len() {
        0 | 1 => vec![qv(Vec2::new(0.0, gate_y))],
        2 => vec![qv(Vec2::new(-half.x * spread, gate_y)), qv(Vec2::new(half.x * spread, gate_y))],
        _ => vec![
            qv(Vec2::new(-half.x * spread, gate_y)),
            qv(Vec2::new(0.0, gate_y)),
            qv(Vec2::new(half.x * spread, gate_y)),
        ],
    };
    let anvil = (t.kind == RoomKind::Anvil).then_some(Vec2::ZERO);
    let plaza = if anvil.is_some() { 9.0 } else { 7.5 };
    let biome = Biome::of(&t.biome);
    let mut b = Builder {
        // Keep-out: the entrance, the central plaza (mosaic / anvil) and the gates.
        keep: [(player_spawn, 7.0), (Vec2::ZERO, plaza)].into_iter().chain(exits.iter().map(|e| (*e, 5.0))).collect(),
        spawn: player_spawn,
        exits: exits.clone(),
        ..Builder::new(half, biome, kind_scale(t.kind), lay, dress)
    };

    // 1. Skeleton: lanes and slots.
    let slots = skeleton(&mut b, &exits, player_spawn, t.kind);
    // 2. Monuments framing the plaza. The stage they stand on (the approach to the gates) is kept
    //    free of top-up ruins.
    let center_gate = exits.iter().any(|e| e.x == 0.0);
    frame_plaza(&mut b, plaza, center_gate);
    arches(&mut b, plaza, t.kind);
    let side_x = exits.iter().map(|e| e.x.abs()).fold(0.0f32, f32::max);
    let court_x = if side_x > 0.0 { side_x - LANE_W * 0.5 - PAD } else { AXIS_W * 0.5 + 7.0 };
    let reserve = [Rect::new(Vec2::new(-court_x, plaza * 0.6), Vec2::new(court_x, half.y))];
    // 3. Districts: the signature motif, usually one open field, the rest from the biome pool.
    let mut pool: Vec<(DistrictKind, f32)> = b.biome.pool().to_vec();
    for m in &t.motifs {
        match pool.iter_mut().find(|(k, _)| k == m) {
            Some(entry) => entry.1 *= 3.0,
            None if *m != DistrictKind::Field && *m != DistrictKind::Plaza => pool.push((*m, 3.0)),
            None => {}
        }
    }
    let themed: Vec<usize> = (0..slots.len()).filter(|&i| !slots[i].strip).collect();
    // A leftover strip is already an open field and counts against the quota.
    let strips = slots.len() - themed.len();
    let n_fields = match themed.len() {
        0..=2 => 0,
        3 => usize::from(b.lay.chance(0.25)),
        _ => 1,
    }
    .saturating_sub(strips);
    let mut is_field: Vec<bool> = slots.iter().map(|s| s.strip).collect();
    for _ in 0..n_fields {
        let w: Vec<f32> = themed
            .iter()
            .map(|&i| {
                if is_field[i] {
                    0.0
                } else if slots[i].south {
                    2.0
                } else {
                    1.0
                }
            })
            .collect();
        if let Some(k) = b.lay.weighted_index(&w) {
            is_field[themed[k]] = true;
        }
    }
    // The template's signature motif takes the roomiest themed slot.
    let motifs: Vec<DistrictKind> =
        t.motifs.iter().copied().filter(|m| !matches!(m, DistrictKind::Field | DistrictKind::Plaza)).collect();
    let signature = themed
        .iter()
        .copied()
        .filter(|&i| !is_field[i])
        .max_by(|&a, &z| {
            let (sa, sz) = (slots[a].rect.size(), slots[z].rect.size());
            (sa.x * sa.y).total_cmp(&(sz.x * sz.y))
        })
        .filter(|_| !motifs.is_empty());
    let mut used: Vec<DistrictKind> = Vec::new();
    let mut districts = vec![District { kind: DistrictKind::Plaza, min: Vec2::splat(-plaza), max: Vec2::splat(plaza) }];
    // The signature slot builds first, so the other slots see its motif as used.
    let mut order: Vec<usize> = (0..slots.len()).collect();
    if let Some(sig) = signature {
        order.retain(|&i| i != sig);
        order.insert(0, sig);
    }
    for i in order {
        let slot = &slots[i];
        let flip = b.lay.chance(0.5);
        let f = slot.frame(flip);
        let mut kind = DistrictKind::Field;
        if !is_field[i] {
            // Two tries (the signature motif or a pool pick, then another pick) before an open field.
            let mut failed = DistrictKind::Field;
            for attempt in 0..2 {
                kind = if attempt == 0 && Some(i) == signature {
                    motifs[b.lay.range_u32(0, motifs.len() as u32) as usize]
                } else {
                    // Never repeat a district while an unused one remains.
                    let spent = |k: &DistrictKind| used.contains(k) || *k == failed;
                    let fresh = pool.iter().any(|(k, _)| !spent(k));
                    let w: Vec<f32> = pool
                        .iter()
                        .map(|(k, w)| {
                            if !spent(k) {
                                *w
                            } else if fresh {
                                0.0
                            } else {
                                w * 0.5
                            }
                        })
                        .collect();
                    pool[b.lay.weighted_index(&w).unwrap_or(0)].0
                };
                if let Some(r) = stamp(&mut b, kind, f) {
                    used.push(kind);
                    b.comps.push(r);
                    break;
                }
                failed = kind;
                kind = DistrictKind::Field;
            }
        }
        if kind == DistrictKind::Field {
            field(&mut b, f);
        }
        districts.push(District { kind, min: qv(slot.rect.min), max: qv(slot.rect.max) });
    }
    // 4. A fallen colossus beside the plaza, then solitary ruins up to the density budget.
    let p_colossus = match t.kind {
        RoomKind::Combat | RoomKind::Elite => 0.4,
        RoomKind::Anvil => 0.25,
        _ => 0.0,
    };
    if b.lay.chance(p_colossus) {
        colossus(&mut b, plaza);
    }
    // The rest of the budget crowds the rim band and the skirts of the districts, so the middle of
    // the field stays open for the fight.
    let target = cover_target(t.kind) * half.x * half.y * 4.0;
    let comps = b.comps.clone();
    let mut tries = 0;
    while b.covered_area() < target && tries < 900 {
        tries += 1;
        let roll = b.lay.f32();
        let at = if roll < 0.4 && !comps.is_empty() {
            let r = comps[b.lay.range_u32(0, comps.len() as u32) as usize];
            let m = b.rl(1.5, 4.5);
            match b.lay.range_u32(0, 4) {
                0 => Vec2::new(b.rl(r.min.x, r.max.x), r.max.y + m),
                1 => Vec2::new(b.rl(r.min.x, r.max.x), r.min.y - m),
                2 => Vec2::new(r.min.x - m, b.rl(r.min.y, r.max.y)),
                _ => Vec2::new(r.max.x + m, b.rl(r.min.y, r.max.y)),
            }
        } else {
            // The north and flank bands only: the south edge stands between the camera and the fight.
            let d = b.rl(RIM + 2.0, RIM + 7.0);
            match b.lay.range_u32(0, 3) {
                0 => Vec2::new(b.rl(-half.x + d, half.x - d), half.y - d),
                1 => Vec2::new(-half.x + d, b.rl(-half.y + d * 2.0, half.y - d)),
                _ => Vec2::new(half.x - d, b.rl(-half.y + d * 2.0, half.y - d)),
            }
        };
        if b.comps.iter().chain(&reserve).any(|r| r.contains(at, 1.0)) {
            continue;
        }
        let sat = b.lay.range_u32(1, 3);
        ruin(&mut b, at, sat);
    }
    // 5. Dressing (visual stream only).
    let rim = b.biome.rim(&mut b.dress);
    dress_heart(&mut b, plaza, t.kind);
    dress_rim(&mut b, rim);
    dress_floor(&mut b, plaza);

    // ── encounter: bigger fields hold bigger hordes ──
    let mut encounter = t.encounter.clone();
    if matches!(t.kind, RoomKind::Combat | RoomKind::Elite) {
        encounter.budget *= 1.2;
        encounter.duration *= 1.05;
        encounter.rate_start *= 1.2;
        encounter.rate_end *= 1.2;
        encounter.max_alive = ((encounter.max_alive as f32) * 1.3).min(360.0) as u32;
    }
    // The swarm arrives from just off-screen around the party, with some pouring over the rim.
    let spawn_zones = vec![
        SpawnZone::Around { min: 23.0, max: 31.0 },
        SpawnZone::Around { min: 23.0, max: 31.0 },
        SpawnZone::Edges { margin: 1.5 },
    ];

    RoomDef {
        key: format!("{}~{seed:08x}", t.key),
        biome: t.biome.clone(),
        kind: t.kind,
        phase: t.phase,
        half_extents: half,
        obstacles: b.obstacles,
        player_spawn,
        anvil,
        exits,
        spawn_zones,
        encounter,
        decor: b.decor,
        motifs: t.motifs.clone(),
        rim,
        districts,
        lanes: b.lanes,
        expedition: None,
        map: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn template(kind: RoomKind) -> RoomDef {
        RoomDef { key: "test_room".into(), kind, ..RoomDef::placeholder() }
    }

    #[test]
    fn same_seed_same_room_different_seed_different_room() {
        let t = template(RoomKind::Combat);
        assert_eq!(generate(&t, 42), generate(&t, 42));
        assert_ne!(generate(&t, 42).obstacles, generate(&t, 43).obstacles);
    }

    #[test]
    fn arenas_are_horde_sized_and_open() {
        for seed in 1..60u32 {
            let r = generate(&template(RoomKind::Combat), seed);
            assert!(r.half_extents.x >= 40.0 && r.half_extents.y >= 27.0, "{:?}", r.half_extents);
            assert!(r.obstacles.len() >= 15, "seed {seed}: only {} features", r.obstacles.len());
            for o in &r.obstacles {
                let (c, rad) = bounds(o);
                // Entrance, plaza and gates stay clear.
                assert!(c.distance(r.player_spawn) >= rad + 7.0 - 1e-3, "seed {seed}: spawn blocked");
                assert!(c.length() >= rad + 7.5 - 1e-3, "seed {seed}: plaza blocked");
                for e in &r.exits {
                    assert!(c.distance(*e) >= rad + 5.0 - 1e-3, "seed {seed}: gate blocked");
                }
                // Inside the rim.
                assert!(c.x.abs() < r.half_extents.x && c.y.abs() < r.half_extents.y);
            }
        }
    }

    #[test]
    fn coordinates_are_quantized_for_cross_platform_agreement() {
        let r = generate(&template(RoomKind::Anvil), 7);
        assert_eq!(r.anvil, Some(Vec2::ZERO));
        for o in &r.obstacles {
            let (c, rad) = bounds(o);
            for v in [c.x, c.y] {
                assert_eq!(v * 8.0, (v * 8.0).round(), "{v} not on the 1/8 grid");
            }
            if let Obstacle::Circle { .. } = o {
                assert_eq!(rad * 8.0, (rad * 8.0).round());
            }
        }
    }

    #[test]
    fn room_seeds_are_nonzero_and_vary() {
        let a: Vec<u32> = (0..32).map(|i| room_seed(7, i)).collect();
        assert!(a.iter().all(|s| *s != 0));
        let mut b = a.clone();
        b.sort_unstable();
        b.dedup();
        assert_eq!(a.len(), b.len());
    }
}
