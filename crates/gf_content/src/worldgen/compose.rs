//! Pipeline steps 9–10 (§3.2, §3.6): the room grammar at map scale. One [`Builder`] runs over the
//! whole map in map mode (the tile mask keeps compositions on open ground; roads, spurs and bridge
//! decks are its lanes, with `compose.road_clear` of open shoulder; clearings, hubs, the Landing
//! and the passes its keep-outs). The map follows the Hades rule of negative space (§3.6): the
//! fight has open ground whose detail is painted, and the mass stands at the edges.
//!
//! **Lay** (obstacles; these move the layout hash), in order:
//!
//! 1. **POI clearings**: each kind's set pieces (the gate's sealed-gate monument, the Warlord's
//!    crucible, anvil chain posts, relic plinths, vein crystals, lair walls).
//! 2. **Barriers**: forge walls as broken runs with buttressed corners, boulder ridges; an arch
//!    over every road where it crosses a region border (a bridge carries its own deck).
//! 3. **Regions**, each on its own streams (`root.fork(100 + i)` lays, `root.fork(200 + i)`
//!    dresses): the hub's grand monument; up to `theme.comps` **edge slots** whose backs lie on
//!    the coast or a border, filled from the theme's composition pool; the rest of the ground cut
//!    into **open fields**, painted and holding at most one kiting anchor; `theme.story` story
//!    clusters on the region's frame band. The region's interior cover stays under `theme.cover`.
//! 4. **The frame**: colliding coast anchors along framed runs of the void shore
//!    (`root.fork(2000 + i)`).
//!
//! **Dress** (visual only; the hash never moves): lip pieces, backdrop spires and foreground
//! silhouettes along the same runs (`2100 + i`), braziers along the roads (30–40 u apart), a
//! brazier pair at every pass arch, waymarks, bridge decks, clearing hearts, hubs and the Landing,
//! then **vignettes** of props backed against walls, compositions, shores and stories (`2200 + i`),
//! **light gaps** so every screen holds a warm pool (`2300`) and cobble islands along the road
//! shoulders (`2400 + k`).

use super::barriers::road_dir;
use super::tiles::{self, land_box};
use super::{Gen, HUB_R, LANDING_R};
use crate::procgen::{
    Biome, Builder, CELL, Frame, ISLAND_APART, PAD, Rect, TileMask, anchor, arch, boulder, bounds, extent, monument,
    monument_at, point_seg, q, qv, rot_of, satellite, stamp,
};
use crate::schema::*;
use gf_core::movement::Obstacle;
use gf_core::poi::PoiKind;
use glam::Vec2;
use std::collections::BTreeMap;

/// Largest slot side (tiles): bigger open ground is split over several slots.
const SLOT_CAP: usize = 10;
/// Smallest slot (tiles, either orientation): 16 × 12 u once shrunk by `PAD`.
const SLOT_MIN: (usize, usize) = (5, 4);
/// Reach of a region's pieces beyond its land's bounding box (lanes and keep-outs farther away
/// cannot refuse a piece, so each region pass only looks at the nearby ones).
const NEAR: f32 = 24.0;
/// Interior land (the cover ceiling's measure): at least this many tile steps from its region's
/// edge (a pit, another region or the rim).
const INTERIOR_STEPS: u16 = 1;
/// Screen footprint (u) of the 4P view: vignettes and light pools are budgeted per screen.
const SCREEN: Vec2 = Vec2::new(45.0, 28.0);
/// Lattice step (u) of the light-gap check (§3.6.8).
const LATTICE: Vec2 = Vec2::new(11.0, 7.0);

/// The composed map: the builder (obstacles, decor, cover grid) and where each composition landed.
pub(crate) struct Built {
    pub(crate) builder: Builder,
    pub(crate) districts: Vec<District>,
}

/// What the lay steps leave for the dressing steps: where the frame, the compositions and the
/// stories stand.
#[derive(Default)]
struct Plan {
    /// Compositions: region, footprint, back direction.
    comps: Vec<(usize, Rect, Vec2)>,
    /// Floor kept clear in front of each composition (its `slot_clear` band, slot included).
    clear: Vec<Rect>,
    /// Story clusters: region, centre, reach.
    stories: Vec<(usize, Vec2, f32)>,
    /// Barrier wall runs and seam runs: regions (a, b), the line's midpoint, the direction from
    /// a to b.
    runs: Vec<(usize, usize, Vec2, Vec2)>,
    /// Framed runs of void shore: region, tiles with their outward directions.
    shores: Vec<(usize, Vec<(usize, Vec2)>)>,
    /// Obstacles (indices into the builder's) that frame the play space: composition, barrier,
    /// story and coast-anchor pieces.
    solids: Vec<usize>,
    /// Vignettes: centre, open side, lit.
    vignettes: Vec<(Vec2, Vec2, bool)>,
    /// The POI clearings' wider keep-outs and approach arcs (disks), obeyed by every region piece
    /// after the hub monument.
    approach: Vec<(Vec2, f32)>,
}

pub(crate) fn build(g: &mut Gen) -> Built {
    let x = g.x.compose.clone();
    let mut lanes = g.lanes();
    lanes.extend(g.bridges.iter().copied());
    let gate_at = g.pois[0].site.at;
    let mut keep: Vec<(Vec2, f32)> = vec![(g.landing, LANDING_R + 1.0)];
    keep.extend(g.pois.iter().map(|p| (p.site.at, p.plaza)));
    keep.extend(g.regions.iter().filter(|r| r.landmark.is_some()).map(|r| (r.site, HUB_R)));
    let mut b = Builder {
        keep,
        lanes,
        spawn: g.landing,
        exits: vec![gate_at],
        mask: Some(TileMask::of(&g.tiles)),
        lane_pad: x.road_clear.max(0.0),
        heat: g.pois.iter().map(|p| (p.site.at, p.site.at)).collect(),
        heat_reach: x.heat_reach.max(0.0),
        ..Builder::new(g.half, g.biome, 1.0, g.root.fork(98), g.root.fork(99))
    };
    let mut plan = Plan::default();
    let mut districts = Vec::new();

    for k in 0..g.pois.len() {
        clearing(g, &mut b, &x, k);
    }
    let approach = approaches(g, &b.lanes);
    for n in 0..g.walls.len() {
        wall(g, &mut b, &x, &approach, &mut plan, n);
    }
    for k in 0..g.roads.len() {
        pass_arch(g, &mut b, &x, k);
    }
    // The keep-outs that only the region pieces obey (the set pieces and arches above stand where
    // they must): nothing pinches a pass, and (past the hub monuments, see `region`) the clearings
    // widen by 6 u and their approaches stay open.
    plan.approach = approach;
    for p in &g.passes {
        b.keep.push((p.at, x.pass_clear.max(0.0)));
    }
    let steps = tiles::edge_steps(&g.tiles);
    for r in 0..g.regions.len() {
        region(g, &mut b, &x, r, &steps, &mut plan, &mut districts);
    }
    for r in 0..g.regions.len() {
        frame(g, &mut b, &x, r, &mut plan);
    }
    seams(g, &mut b, &x, &mut plan);
    if x.road_silhouettes > 0.0 {
        road_silhouettes(g, &mut b, x.road_silhouettes);
    }
    waymarks(g, &mut b);
    for k in 0..g.pois.len() {
        dress_clearing(g, &mut b, k);
    }
    dress_hubs(g, &mut b);
    dress_landing(g, &mut b);
    // The road fires come after the clearings, hubs and passes, so a road never adds a bowl
    // beside the ring it runs into (the dusk between pools survives, §3.6.8).
    dress_roads(g, &mut b);
    for r in 0..g.regions.len() {
        vignettes(g, &mut b, &x, r, &mut plan);
    }
    let fires = |b: &Builder| b.decor.iter().filter(|d| matches!(d, Decor::Brazier { .. })).count();
    let before = fires(&b);
    light_gaps(g, &mut b, &x, &mut plan);
    g.trace(|| format!("braziers: {before} before the light gaps, {} after", fires(&b)));
    road_paving(g, &mut b);
    for r in 0..g.regions.len() {
        floor_marks(g, &mut b, &x, r, &plan);
    }
    districts.extend(g.pois.iter().map(|p| District {
        kind: DistrictKind::Plaza,
        min: qv(p.site.at - Vec2::splat(p.plaza)),
        max: qv(p.site.at + Vec2::splat(p.plaza)),
    }));
    Built { builder: b, districts }
}

// ───────────────────────────── forced pieces ─────────────────────────────

/// Run `f` with the builder's keep-outs, tile mask and lane pad lifted (pieces standing inside a
/// clearing or on a road's shoulder); the lanes themselves, the rim and the spacing rules still
/// apply.
fn unmasked<R>(b: &mut Builder, f: impl FnOnce(&mut Builder) -> R) -> R {
    let keep = std::mem::take(&mut b.keep);
    let mask = b.mask.take();
    let pad = std::mem::replace(&mut b.lane_pad, 0.0);
    let out = f(b);
    b.keep = keep;
    b.mask = mask;
    b.lane_pad = pad;
    out
}

/// Run `f` with only the lane pad lifted (barriers run right up to the road they are breached by).
fn padless<R>(b: &mut Builder, f: impl FnOnce(&mut Builder) -> R) -> R {
    let pad = std::mem::replace(&mut b.lane_pad, 0.0);
    let out = f(b);
    b.lane_pad = pad;
    out
}

/// May `o` stand here ignoring the mask: on land, and out of every keep-out except the ones at
/// `own` (the clearing it dresses)?
fn open_ground(g: &Gen, b: &Builder, o: &Obstacle, own: Option<Vec2>) -> bool {
    let (c, e) = extent(o);
    let (bc, br) = bounds(o);
    land_box(&g.tiles, c, e + Vec2::splat(0.5))
        && b.keep.iter().all(|(k, kr)| Some(*k) == own || bc.distance(*k) >= br + kr)
}

/// Place `pieces` dressed by `d` inside a clearing or hub (see [`open_ground`]).
fn force(g: &Gen, b: &mut Builder, pieces: &[Obstacle], d: Decor, own: Option<Vec2>) -> bool {
    if !pieces.iter().all(|o| open_ground(g, b, o, own)) {
        return false;
    }
    let grp = b.group();
    unmasked(b, |b| b.solid(grp, pieces, d))
}

/// An arch spanning the road through `at` running along `dir`, its piers just off the road; the
/// offset of its piers from the road's centre line when it stands.
fn road_arch(g: &Gen, b: &mut Builder, at: Vec2, dir: Vec2, width: f32, own: Option<Vec2>) -> Option<f32> {
    let pier = q(b.rl(0.7, 0.9));
    let n = Vec2::new(-dir.y, dir.x);
    let off = width * 0.5 + pier * 1.42 + 0.15;
    let (from, to) = (qv(at + n * off), qv(at - n * off));
    let half = Vec2::splat(pier);
    let pieces = [Obstacle::Box { center: from, half }, Obstacle::Box { center: to, half }];
    if !pieces.iter().all(|o| open_ground(g, b, o, own)) {
        return None;
    }
    unmasked(b, |b| arch(b, from, to, pier)).then_some(off + pier)
}

/// The unit direction among the 16 [`Rot16`] steps that points most away from every direction in
/// `ways` (ties to the lower step).
fn open_dir(ways: &[Vec2], only_axes: bool) -> Vec2 {
    let mut best = (f32::MAX, Vec2::Y);
    for k in 0..16u8 {
        if only_axes && k % 4 != 0 {
            continue;
        }
        let d = rot16_dir(k);
        let worst = ways.iter().map(|w| d.dot(*w)).fold(-1.0f32, f32::max);
        if worst < best.0 {
            best = (worst, d);
        }
    }
    best.1
}

/// Directions in which lanes leave `at` within `r`.
fn ways_out(lanes: &[Lane], at: Vec2, r: f32) -> Vec<Vec2> {
    let mut out = Vec::new();
    for l in lanes {
        if point_seg(at, l.from, l.to) >= r {
            continue;
        }
        let dir = (l.to - l.from).normalize_or(Vec2::ZERO);
        if l.from.distance(at) > 0.5 {
            out.push(-dir);
        }
        if l.to.distance(at) > 0.5 {
            out.push(dir);
        }
    }
    out
}

/// The clearings' wider keep-outs (§3.6.2): plaza + 6 u holds only the POI's own set pieces, and
/// the approach arc along each way in (±30°) stays open out to plaza + 10 u, covered by two disks
/// along the way.
fn approaches(g: &Gen, lanes: &[Lane]) -> Vec<(Vec2, f32)> {
    let mut out = Vec::new();
    for p in &g.pois {
        let (at, plaza) = (p.site.at, p.plaza);
        out.push((at, plaza + 6.0));
        for d in ways_out(lanes, at, plaza) {
            out.push((at + d * (plaza + 4.0), (plaza + 4.0) * 0.5 + 1.0));
            out.push((at + d * (plaza + 9.0), (plaza + 9.0) * 0.55));
        }
    }
    out
}

/// Area (u²) of an obstacle.
fn area(o: &Obstacle) -> f32 {
    match *o {
        Obstacle::Circle { radius, .. } => std::f32::consts::PI * radius * radius,
        Obstacle::Box { half, .. } => 4.0 * half.x * half.y,
    }
}

// ───────────────────────────── clearings ─────────────────────────────

/// Solid set pieces of POI `k`'s clearing (§3.2 step 10).
fn clearing(g: &Gen, b: &mut Builder, x: &ComposeDef, k: usize) {
    let p = g.pois[k];
    let (at, radius, plaza) = (p.site.at, p.site.radius, p.plaza);
    b.lay = g.root.fork(300 + k as u64);
    b.dress = g.root.fork(400 + k as u64);
    let lanes = b.lanes.clone();
    let ways = ways_out(&lanes, at, plaza);
    match p.site.kind {
        PoiKind::Gate => {
            // The sealed gate stands behind the ring, doors toward it (one socket per Seal).
            let d = open_dir(&ways, true);
            let half = qv(Vec2::new(b.rl(3.0, 3.8), b.rl(0.9, 1.1)));
            let half = if d.x != 0.0 { Vec2::new(half.y, half.x) } else { half };
            let height = q(b.rd(8.0, 10.0));
            for extra in [3.5f32, 4.5, 5.5] {
                let c = qv(at + d * (radius + half.min_element() + extra));
                let o = Obstacle::Box { center: c, half };
                if force(g, b, &[o], Decor::SealedGate { at: c, half, height }, Some(at)) {
                    break;
                }
            }
        }
        PoiKind::Warlord => {
            // A crucible over its pit at the arena's edge.
            let d = open_dir(&ways, false);
            let r = b.rl(2.4, 3.0);
            for extra in [2.0f32, 3.5, 5.0] {
                let (o, dec) = monument(b, MapMark::Crucible, at + d * (plaza - r - extra), 0, true);
                if force(g, b, &[o], dec, Some(at)) {
                    break;
                }
            }
        }
        PoiKind::Shrine => {
            // The shrine's god stands behind the ring, facing it.
            let d = open_dir(&ways, false);
            let (r, height) = (q(b.rl(1.0, 1.2)), q(b.rd(4.4, 5.4)));
            let god = p.site.god.unwrap_or(0);
            for extra in [1.4f32, 2.2] {
                let c = qv(at + d * (radius + r + extra));
                let o = Obstacle::Circle { center: c, radius: r };
                let statue = Decor::Statue { at: c, radius: r, height, rot: rot_of(-d), god, variant: 1 };
                if force(g, b, &[o], statue, Some(at)) {
                    break;
                }
            }
        }
        PoiKind::Anvil => {
            // Two chain posts flank the anvil ring; the chains hang over it (dressing).
            let e = open_dir(&ways, true);
            let side = Vec2::new(-e.y, e.x);
            let r = q(b.rl(0.5, 0.6));
            let height = q(b.rd(4.2, 5.0));
            let posts = [qv(at + side * (radius + 1.6)), qv(at - side * (radius + 1.6))];
            let pieces: Vec<Obstacle> = posts.iter().map(|&c| Obstacle::Circle { center: c, radius: r }).collect();
            if pieces.iter().all(|o| open_ground(g, b, o, Some(at))) {
                let grp = b.group();
                let placed = unmasked(b, |b| {
                    b.solid(grp, &pieces[..1], Decor::Pillar { at: posts[0], radius: r, height })
                        && b.solid(grp, &pieces[1..], Decor::Pillar { at: posts[1], radius: r, height })
                });
                if placed {
                    b.decal(Decor::Chains { from: posts[0], to: posts[1], height: q(height - 0.3) });
                }
            }
        }
        PoiKind::Reliquary => {
            // Relic plinths around the ring, clear of the ways in.
            for i in 0..4u8 {
                let d = rot16_dir(i * 4 + 2);
                if ways.iter().any(|w| w.dot(d) > 0.75) {
                    continue;
                }
                let c = qv(at + d * (radius + 1.7));
                let half = qv(Vec2::splat(b.rl(0.55, 0.7)));
                let (height, variant) = (q(b.rd(0.9, 1.4)), b.vd(4));
                let o = Obstacle::Box { center: c, half };
                force(g, b, &[o], Decor::Wall { at: c, half, height, style: WallStyle::Plinth, variant }, Some(at));
            }
        }
        PoiKind::Vein => {
            // The lode breaks the ground: a crystal cluster at the rim, clear of the ways in.
            let base = b.vd(16);
            for i in 0..3u8 {
                let d = rot16_dir(base.wrapping_add(i * 5));
                if ways.iter().any(|w| w.dot(d) > 0.75) {
                    continue;
                }
                let r = q(b.rl(0.7, 1.0));
                let c = qv(at + d * (radius + r + 0.9));
                let (height, variant) = (q(b.rd(2.6, 4.0)), b.vd(4));
                let o = Obstacle::Circle { center: c, radius: r };
                force(g, b, &[o], Decor::Crystal { at: c, radius: r, height, rot: rot_of(d), variant }, Some(at));
            }
        }
        PoiKind::Lair => {
            // Broken walls at the den's rim.
            let base = b.vd(16);
            for i in 0..4u8 {
                let d = rot16_dir(base.wrapping_add(i * 4 + 1));
                if ways.iter().any(|w| w.dot(d) > 0.7) {
                    continue;
                }
                let c = qv(at + d * (plaza - 2.2));
                let long = b.rl(1.6, 2.4);
                let half = qv(if d.x.abs() > d.y.abs() { Vec2::new(0.55, long) } else { Vec2::new(long, 0.55) });
                let (height, variant) = (q(b.rd(1.6, 3.2)), b.vd(4));
                let o = Obstacle::Box { center: c, half };
                if force(g, b, &[o], Decor::Wall { at: c, half, height, style: WallStyle::Ruin, variant }, Some(at)) {
                    b.rubble(c - d * 1.6, 0.6, 1.1);
                }
            }
        }
        // The spring's basin is marked by a painted rune ring (dressing), not by standing stones.
        _ => {}
    }
    // Arches where the roads (and spurs) enter the clearing: off by default, the heart, the
    // brazier ring, the key light and the waymarks already signpost the ways in.
    if x.entry_arches {
        let width = q(g.x.roads.width);
        for d in &ways {
            for extra in [1.5f32, 3.0] {
                if road_arch(g, b, at + *d * (plaza + extra), *d, width, Some(at)).is_some() {
                    break;
                }
            }
        }
    }
}

// ───────────────────────────── barriers ─────────────────────────────

/// Wall style of the biome's barrier walls.
fn wall_style(biome: Biome) -> WallStyle {
    match biome {
        Biome::Cinder => WallStyle::Forge,
        Biome::Verdant => WallStyle::Hedge,
        Biome::Spire => WallStyle::Parapet,
        Biome::Unmaking => WallStyle::Monolith,
    }
}

/// The four face directions of a tile, in a fixed order: west, east, south, north.
const DIRS: [Vec2; 4] = [Vec2::NEG_X, Vec2::X, Vec2::NEG_Y, Vec2::Y];

/// One straight run of barrier wall: the faces of consecutive tiles looking the same way.
struct Run {
    /// Index into [`DIRS`]: the side of region a's tiles the wall stands on (toward region b).
    dir: usize,
    /// The wall line's fixed coordinate (x for west/east faces, y for south/north).
    line: f32,
    /// Its extent along the line (world units).
    lo: f32,
    hi: f32,
    /// Tile faces it spans.
    faces: usize,
    /// Corners (the staircase steps) found at either end.
    corner: [Option<Vec2>; 2],
}

impl Run {
    fn along_x(&self) -> bool {
        self.dir >= 2
    }
    /// The point on the wall line at `s` along it.
    fn at(&self, s: f32) -> Vec2 {
        if self.along_x() { Vec2::new(s, self.line) } else { Vec2::new(self.line, s) }
    }
}

/// Wall or ridge `n` (`g.walls[n]`) along its region pair's border, on region `a`'s side. Walls
/// are laid as broken runs (§3.6.4): the tile faces merge into straight runs, laid as blocks of up
/// to two faces with a low ruined course now and then, a square pier buttresses every step of the
/// staircase, and rubble lies only at run ends and in the breaches roads cut.
fn wall(g: &Gen, b: &mut Builder, x: &ComposeDef, approach: &[(Vec2, f32)], plan: &mut Plan, n: usize) {
    let adj = &g.adj[g.walls[n]];
    let kind = adj.barrier.unwrap_or(BarrierKind::Wall);
    b.lay = g.root.fork(500 + n as u64);
    b.dress = g.root.fork(550 + n as u64);
    let t = &g.tiles;
    let w = t.w as usize;
    let grp = b.group();
    let n0 = b.obstacles.len();
    if kind == BarrierKind::Ridge {
        for i in 0..t.kind.len() {
            if !t.kind[i].is_land() || t.region[i] as usize != adj.a {
                continue;
            }
            let (x, y) = (i % w, i / w);
            let faces: Vec<Vec2> = tiles::around(t, i)
                .filter(|&j| t.kind[j].is_land() && t.region[j] as usize == adj.b)
                .map(|j| (t.center((j % w) as u16, (j / w) as u16) - t.center(x as u16, y as u16)) / t.size)
                .collect();
            if faces.is_empty() || (x + y) % 2 != 0 {
                continue;
            }
            let c = t.center(x as u16, y as u16);
            let d = faces.iter().copied().sum::<Vec2>().normalize_or(faces[0]);
            let (r, variant) = (b.rl(1.3, 2.0), b.vd(4));
            b.circle(grp, c + d * 1.2, r, |at, radius| Decor::Boulder { at, radius, variant });
        }
        plan.solids.extend(n0..b.obstacles.len());
        return;
    }
    // Faces as (direction, line, position along it), sorted, merged into runs.
    let mut faces: Vec<(usize, u16, u16)> = Vec::new();
    for i in 0..t.kind.len() {
        if !t.kind[i].is_land() || t.region[i] as usize != adj.a {
            continue;
        }
        let (x, y) = (i % w, i / w);
        let near = [
            (0usize, i.wrapping_sub(1), x > 0),
            (1, i + 1, x + 1 < w),
            (2, i.wrapping_sub(w), y > 0),
            (3, i + w, y + 1 < t.h as usize),
        ];
        for (k, j, ok) in near {
            if ok && t.kind[j].is_land() && t.region[j] as usize == adj.b {
                let (line, pos) = if k < 2 { (x as u16, y as u16) } else { (y as u16, x as u16) };
                faces.push((k, line, pos));
            }
        }
    }
    faces.sort_unstable();
    let mut spans: Vec<(usize, u16, u16, u16)> = Vec::new();
    for &(k, line, pos) in &faces {
        match spans.last_mut() {
            Some(s) if s.0 == k && s.1 == line && s.3 + 1 == pos => s.3 = pos,
            _ => spans.push((k, line, pos, pos)),
        }
    }
    let hs = t.size * 0.5;
    let mut runs: Vec<Run> = spans
        .iter()
        .map(|&(k, line, p0, p1)| {
            let d = DIRS[k];
            let (c0, c1) =
                if k < 2 { (t.center(line, p0), t.center(line, p1)) } else { (t.center(p0, line), t.center(p1, line)) };
            let across = if k < 2 { c0.x + d.x * 1.4 } else { c0.y + d.y * 1.4 };
            let (lo, hi) =
                if k < 2 { (c0.y - hs - 0.05, c1.y + hs + 0.05) } else { (c0.x - hs - 0.05, c1.x + hs + 0.05) };
            Run { dir: k, line: across, lo, hi, faces: (p1 - p0 + 1) as usize, corner: [None, None] }
        })
        .collect();
    // Corners: an end of a run and an end of a perpendicular run within a unit of each other meet
    // at the crossing of their lines, where a pier stands and both blocks stop short of it.
    for a in 0..runs.len() {
        for c in 0..runs.len() {
            if runs[a].along_x() == runs[c].along_x() || !runs[a].along_x() {
                continue;
            }
            for ea in 0..2 {
                for ec in 0..2 {
                    let pa = runs[a].at(if ea == 0 { runs[a].lo } else { runs[a].hi });
                    let pc = runs[c].at(if ec == 0 { runs[c].lo } else { runs[c].hi });
                    if pa.distance(pc) < 1.0 {
                        let corner = Vec2::new(runs[c].line, runs[a].line);
                        runs[a].corner[ea] = Some(corner);
                        runs[c].corner[ec] = Some(corner);
                    }
                }
            }
        }
    }
    let style = wall_style(g.biome);
    // The passes of this pair: the wall runs right up to the road there (the breach); elsewhere it
    // keeps the road shoulders open like every other piece. It stays out of the POI clearings and
    // their approaches.
    let passes: Vec<Vec2> = g
        .roads
        .iter()
        .filter(|r| (r.a, r.b) == (adj.a, adj.b) || (r.a, r.b) == (adj.b, adj.a))
        .map(|r| r.pass)
        .collect();
    let lay_block = |b: &mut Builder, m: Vec2, half: Vec2, height: f32, variant: u8| {
        let o = Obstacle::Box { center: qv(m), half: qv(half) };
        let (bc, br) = bounds(&o);
        if approach.iter().any(|(k, kr)| bc.distance(*k) < br + kr) {
            return false;
        }
        let make = |at, half| Decor::Wall { at, half, height, style, variant };
        if passes.iter().any(|p| p.distance(m) < x.pass_clear + half.max_element()) {
            padless(b, |b| b.block(grp, m, half, make))
        } else {
            b.block(grp, m, half, make)
        }
    };
    let mut piers: BTreeMap<(i32, i32), (Vec2, f32)> = BTreeMap::new();
    for run in &mut runs {
        let along_x = run.along_x();
        let cv = |c: Vec2| if along_x { c.x } else { c.y };
        if let Some(c) = run.corner[0] {
            run.lo = cv(c) + 0.7;
        }
        if let Some(c) = run.corner[1] {
            run.hi = cv(c) - 0.7;
        }
        let d = DIRS[run.dir];
        let mid = run.at((run.lo + run.hi) * 0.5);
        plan.runs.push((adj.a, adj.b, mid, d));
        if run.hi - run.lo < 0.6 {
            continue;
        }
        let blocks = run.faces.div_ceil(2).max(1);
        let step = (run.hi - run.lo) / blocks as f32;
        let mut heights = [0.0f32; 2];
        for k in 0..blocks {
            let (a, z) = (run.lo + step * k as f32 - 0.05, run.lo + step * (k + 1) as f32 + 0.05);
            let a = a.max(run.lo);
            let z = z.min(run.hi);
            let height = if b.lay.chance(0.2) { q(b.rd(1.2, 1.8)) } else { q(b.rd(2.4, 4.0)) };
            let variant = b.vd(4);
            let block = |a: f32, z: f32| {
                let m = run.at((a + z) * 0.5);
                let hl = (z - a) * 0.5;
                let half = if run.along_x() { Vec2::new(hl, 0.6) } else { Vec2::new(0.6, hl) };
                (m, half)
            };
            let (m, half) = block(a, z);
            let mut placed = lay_block(b, m, half, height, variant);
            if !placed && z - a > 5.0 {
                // A road breaches it: lay its faces one at a time and leave only the breach open.
                let c = (a + z) * 0.5;
                for (a2, z2) in [(a, c + 0.05), (c - 0.05, z)] {
                    let (m, half) = block(a2, z2);
                    let ok = lay_block(b, m, half, height, variant);
                    placed |= ok;
                    if !ok {
                        b.rubble(m - d * 1.8, 0.7, 1.2);
                    }
                }
            } else if !placed {
                b.rubble(m - d * 1.8, 0.7, 1.2);
            }
            if placed {
                if k == 0 {
                    heights[0] = height;
                }
                if k + 1 == blocks {
                    heights[1] = height;
                }
            }
        }
        for (end, corner) in run.corner.iter().enumerate() {
            match corner {
                Some(c) => {
                    let key = ((c.x * 8.0).round() as i32, (c.y * 8.0).round() as i32);
                    let e = piers.entry(key).or_insert((*c, 0.0));
                    e.1 = e.1.max(heights[end]);
                }
                None => {
                    // Masonry spilled where the run gives out.
                    let s = if end == 0 { run.lo + 0.8 } else { run.hi - 0.8 };
                    b.rubble(run.at(s) - d * 1.7, 0.6, 1.0);
                }
            }
        }
    }
    for (_, (c, h)) in piers {
        if h <= 0.0 {
            continue;
        }
        let height = q(h + 0.6);
        let variant = b.vd(4);
        lay_block(b, c, Vec2::splat(0.8), height, variant);
    }
    g.trace(|| format!("wall {n}: {} runs, {} blocks", runs.len(), b.obstacles.len() - n0));
    plan.solids.extend(n0..b.obstacles.len());
}

/// Two standing pylons flanking the road through `at` running along `dir`, just off its
/// shoulders, each hung with a banner: the door of an open border (a lintel with no wall on
/// either side read as a plank lying across the road from the fixed camera). The offset of their
/// outer faces from the road's centre line when they stand.
fn road_pylons(g: &Gen, b: &mut Builder, at: Vec2, dir: Vec2, width: f32) -> Option<f32> {
    let r = q(b.rl(0.55, 0.7));
    let n = Vec2::new(-dir.y, dir.x);
    let off = width * 0.5 + r + 0.6;
    let posts = [qv(at + n * off), qv(at - n * off)];
    let pieces: Vec<Obstacle> = posts.iter().map(|&c| Obstacle::Circle { center: c, radius: r }).collect();
    if !pieces.iter().all(|o| open_ground(g, b, o, None)) {
        return None;
    }
    let grp = b.group();
    let height = q(b.rd(4.8, 5.8));
    let placed = unmasked(b, |b| {
        b.solid(grp, &pieces[..1], Decor::Pillar { at: posts[0], radius: r, height })
            && b.solid(grp, &pieces[1..], Decor::Pillar { at: posts[1], radius: r, height })
    });
    if !placed {
        return None;
    }
    let god = b.god();
    for (k, p) in posts.iter().enumerate() {
        let side = if k == 0 { n } else { -n };
        let bh = q(height - b.rd(0.6, 1.2));
        b.decal(Decor::Banner { at: qv(*p + side * (r + 0.15)), height: bh, rot: rot_of(side), god });
    }
    Some(off + r)
}

/// The door where road `k` crosses its regions' border (the pass, §3.6.4): an arch through a
/// wall or ridge (always), at an open border by `compose.pass_arches` (else two bannered pylons
/// when `compose.pass_pylons`), nothing over a bridge (the deck is the landmark there). A
/// brazier pair lights it from the road's shoulders.
fn pass_arch(g: &Gen, b: &mut Builder, x: &ComposeDef, k: usize) {
    let road = &g.roads[k];
    b.lay = g.root.fork(600 + k as u64);
    b.dress = g.root.fork(650 + k as u64);
    let barrier = g.adj.iter().find(|a| (a.a, a.b) == (road.a.min(road.b), road.a.max(road.b))).and_then(|a| a.barrier);
    let chance = match barrier {
        Some(BarrierKind::Wall | BarrierKind::Ridge) => 1.0,
        Some(_) => 0.0,
        None => x.pass_arches.clamp(0.0, 1.0),
    };
    let arch = b.lay.chance(chance);
    if !arch && !(barrier.is_none() && x.pass_pylons) {
        return;
    }
    let dir = road_dir(&road.lanes, road.pass);
    let width = q(g.x.roads.width);
    for s in [0.0f32, -2.5, 2.5, -5.0, 5.0] {
        let at = road.pass + dir * s;
        let door = if arch { road_arch(g, b, at, dir, width, None) } else { road_pylons(g, b, at, dir, width) };
        if let Some(reach) = door {
            let n = Vec2::new(-dir.y, dir.x);
            for side in [1.0f32, -1.0] {
                b.brazier(at + n * (side * (reach + 1.0)) - dir * 0.9);
            }
            break;
        }
    }
}

// ───────────────────────────── regions ─────────────────────────────

/// A slot: ground for one composition or one open field.
struct Slot {
    rect: Rect,
    /// The direction its back turns to (an edge slot's: the coast or border behind it).
    back: Vec2,
    /// The floor kept clear in front of it (edge slots): the slot and its `slot_clear` band.
    clear: Rect,
}

/// The largest axis-aligned rectangle of `free` cells (w × h grid) at least `SLOT_MIN` in either
/// orientation, each side capped at [`SLOT_CAP`]: `(x, y, w, h)` of its capped, centred crop.
/// Ties go to the first found (bottom row, then left column).
fn largest(free: &[bool], w: usize, h: usize) -> Option<(usize, usize, usize, usize)> {
    let mut heights = vec![0usize; w];
    let mut best: Option<(usize, (usize, usize, usize, usize))> = None;
    for y in 0..h {
        for x in 0..w {
            heights[x] = if free[y * w + x] { heights[x] + 1 } else { 0 };
        }
        for x0 in 0..w {
            let mut minh = usize::MAX;
            for (x1, &hx) in heights.iter().enumerate().skip(x0) {
                minh = minh.min(hx);
                if minh == 0 {
                    break;
                }
                let (rw, rh) = (x1 - x0 + 1, minh);
                let (cw, ch) = (rw.min(SLOT_CAP), rh.min(SLOT_CAP));
                let fits = (cw >= SLOT_MIN.0 && ch >= SLOT_MIN.1) || (cw >= SLOT_MIN.1 && ch >= SLOT_MIN.0);
                if !fits {
                    continue;
                }
                let area = cw * ch;
                if best.is_none_or(|(a, _)| area > a) {
                    let (cx, cy) = (x0 + (rw - cw) / 2, y + 1 - rh + (rh - ch) / 2);
                    best = Some((area, (cx, cy, cw, ch)));
                }
            }
        }
    }
    best.map(|b| b.1)
}

/// Inclusive 2D prefix sums of `v` (w × h), one row and column of padding.
fn prefix(v: &[bool], w: usize, h: usize) -> Vec<u32> {
    let mut p = vec![0u32; (w + 1) * (h + 1)];
    for y in 0..h {
        for x in 0..w {
            p[(y + 1) * (w + 1) + x + 1] =
                u32::from(v[y * w + x]) + p[y * (w + 1) + x + 1] + p[(y + 1) * (w + 1) + x] - p[y * (w + 1) + x];
        }
    }
    p
}

/// Sum of the prefix table `p` (width `w + 1`) over the cells `x..x + cw`, `y..y + ch`.
fn rect_sum(p: &[u32], w: usize, (x, y, cw, ch): (usize, usize, usize, usize)) -> u32 {
    let s = w + 1;
    p[(y + ch) * s + x + cw] + p[y * s + x] - p[y * s + x + cw] - p[(y + ch) * s + x]
}

/// Cut region `r`'s slots (§3.6.4): up to `comps` **edge slots** first, the largest crops whose
/// north, east or west side lies (for `edge_share` of its tiles) within `edge_band + 1` tiles of
/// the coast or another region's land, never the south side, each spending a `slot_clear` band in
/// front of it; then **open fields** from what is left, up to `compose.slots` in all.
fn cut_slots(g: &Gen, r: usize, x: &ComposeDef, comps: usize) -> (Vec<Slot>, Vec<Slot>) {
    let t = &g.tiles;
    let reg = &g.regions[r];
    let (x0, y0) = (reg.lo.0 as usize, reg.lo.1 as usize);
    let (w, h) = (reg.hi.0 as usize + 1 - x0, reg.hi.1 as usize + 1 - y0);
    let mut free: Vec<bool> = (0..w * h)
        .map(|k| {
            let i = t.index((x0 + k % w) as u16, (y0 + k / w) as u16);
            t.kind[i] == TileKind::Ground && t.region[i] as usize == r
        })
        .collect();
    // Edge flags toward north, east and west: Some(coast?) when the edge is within reach.
    const SIDES: [(i32, i32); 3] = [(0, 1), (1, 0), (-1, 0)];
    let reach = 1 + x.edge_band.min(2) as i32;
    let edge = |lx: usize, ly: usize, (dx, dy): (i32, i32)| -> Option<bool> {
        let (gx, gy) = ((x0 + lx) as i32, (y0 + ly) as i32);
        for s in 1..=reach {
            let (nx, ny) = (gx + dx * s, gy + dy * s);
            if nx < 0 || ny < 0 || nx >= t.w as i32 || ny >= t.h as i32 {
                return Some(true);
            }
            let j = t.index(nx as u16, ny as u16);
            match t.kind[j] {
                TileKind::Void | TileKind::Liquid => return Some(true),
                TileKind::Ground if t.region[j] as usize != r => return Some(false),
                TileKind::Ground => {}
                _ => return None,
            }
        }
        None
    };
    // Per side: flagged tiles and coast-flagged tiles, as prefix tables along the side's line.
    let flags: Vec<(Vec<bool>, Vec<bool>)> = SIDES
        .iter()
        .map(|&d| {
            let f: Vec<Option<bool>> = (0..w * h).map(|k| if free[k] { edge(k % w, k / w, d) } else { None }).collect();
            (f.iter().map(|e| e.is_some()).collect(), f.iter().map(|e| *e == Some(true)).collect())
        })
        .collect();
    let tables: Vec<(Vec<u32>, Vec<u32>)> = flags.iter().map(|(a, c)| (prefix(a, w, h), prefix(c, w, h))).collect();
    let share = (x.edge_share.clamp(0.0, 1.0) * 100.0).round() as u32;
    let hs = Vec2::splat(t.size * 0.5);
    let world = |cx: usize, cy: usize, cw: usize, ch: usize| {
        let lo = t.center((x0 + cx) as u16, (y0 + cy) as u16) - hs;
        let hi = t.center((x0 + cx + cw - 1) as u16, (y0 + cy + ch - 1) as u16) + hs;
        (lo, hi)
    };
    let band = (x.slot_clear.max(0.0) / t.size).ceil() as usize;
    let mut edges = Vec::new();
    for _ in 0..comps.min(x.slots as usize) {
        let pre = prefix(&free, w, h);
        // (area, coast, side rank) of the best eligible crop, and the crop and its side.
        let mut best: Option<((usize, bool, usize), (usize, usize, usize, usize), usize)> = None;
        for cy in 0..h {
            for cx in 0..w {
                for ch in SLOT_MIN.1..=SLOT_CAP.min(h - cy) {
                    for cw in SLOT_MIN.1..=SLOT_CAP.min(w - cx) {
                        let fits = (cw >= SLOT_MIN.0 && ch >= SLOT_MIN.1) || (cw >= SLOT_MIN.1 && ch >= SLOT_MIN.0);
                        if !fits || rect_sum(&pre, w, (cx, cy, cw, ch)) != (cw * ch) as u32 {
                            continue;
                        }
                        for (s, (all, coast)) in tables.iter().enumerate() {
                            let line = match s {
                                0 => (cx, cy + ch - 1, cw, 1),
                                1 => (cx + cw - 1, cy, 1, ch),
                                _ => (cx, cy, 1, ch),
                            };
                            let len = (line.2 * line.3) as u32;
                            let n = rect_sum(all, w, line);
                            if n * 100 < share * len {
                                continue;
                            }
                            let key = (cw * ch, rect_sum(coast, w, line) * 2 >= n, 2 - s);
                            if best.as_ref().is_none_or(|b| key > b.0) {
                                best = Some((key, (cx, cy, cw, ch), s));
                            }
                        }
                    }
                }
            }
        }
        let Some((_, (cx, cy, cw, ch), s)) = best else { break };
        let (dx, dy) = SIDES[s];
        let back = Vec2::new(dx as f32, dy as f32);
        // The slot, a one-tile margin, and the clear band on its three open sides are spent.
        let grow = |open: bool| if open { 1 + band } else { 1 };
        let (gw, ge, gs, gn) = (grow(s != 2), grow(s != 1), grow(true), grow(s != 0));
        for y in cy.saturating_sub(gs)..(cy + ch + gn).min(h) {
            for x in cx.saturating_sub(gw)..(cx + cw + ge).min(w) {
                free[y * w + x] = false;
            }
        }
        let (lo, hi) = world(cx, cy, cw, ch);
        let rect = Rect::new(qv(lo + Vec2::splat(PAD)), qv(hi - Vec2::splat(PAD)));
        let c = x.slot_clear.max(0.0);
        let open = |on: bool| if on { c } else { 0.0 };
        let clear = Rect::new(lo - Vec2::new(open(s != 2), c), hi + Vec2::new(open(s != 1), open(s != 0)));
        edges.push(Slot { rect, back, clear });
    }
    let mut fields = Vec::new();
    while edges.len() + fields.len() < x.slots as usize {
        let Some((sx, sy, sw, sh)) = largest(&free, w, h) else { break };
        for y in sy.saturating_sub(1)..(sy + sh + 1).min(h) {
            for x in sx.saturating_sub(1)..(sx + sw + 1).min(w) {
                free[y * w + x] = false;
            }
        }
        let (lo, hi) = world(sx, sy, sw, sh);
        let rect = Rect::new(qv(lo + Vec2::splat(PAD)), qv(hi - Vec2::splat(PAD)));
        fields.push(Slot { rect, back: Vec2::Y, clear: rect });
    }
    (edges, fields)
}

/// Compose region `r` (§3.2 step 9, §3.6).
fn region(
    g: &mut Gen,
    b: &mut Builder,
    x: &ComposeDef,
    r: usize,
    steps: &[u16],
    plan: &mut Plan,
    districts: &mut Vec<District>,
) {
    if g.regions[r].area == 0 {
        return;
    }
    b.lay = g.root.fork(100 + r as u64);
    b.dress = g.root.fork(200 + r as u64);
    let (lo, hi) = g.regions[r].bounds(&g.tiles);
    let (nlo, nhi) = (lo - Vec2::splat(NEAR), hi + Vec2::splat(NEAR));
    let all_lanes = std::mem::take(&mut b.lanes);
    let all_keep = std::mem::take(&mut b.keep);
    let near_box = |a: Vec2, z: Vec2| a.x <= nhi.x && z.x >= nlo.x && a.y <= nhi.y && z.y >= nlo.y;
    b.lanes = all_lanes
        .iter()
        .filter(|l| {
            let hw = Vec2::splat(l.width * 0.5);
            near_box(l.from.min(l.to) - hw, l.from.max(l.to) + hw)
        })
        .copied()
        .collect();
    b.keep =
        all_keep.iter().filter(|(c, kr)| near_box(*c - Vec2::splat(*kr), *c + Vec2::splat(*kr))).copied().collect();
    let theme = g.x.themes.get(g.regions[r].theme as usize).cloned();

    // d) The hub's grand monument, facing the Landing (the skyline greets arrivals). It stands at
    //    the hub's rim on an open side, leaning north: seen by the fixed camera its height then
    //    rises away from the crossroads instead of hanging over the ways and the fights there. A
    //    hub with no such room keeps a low great brazier on its site instead.
    if let Some(mark) = g.regions[r].landmark {
        let site = g.regions[r].site;
        let ways = ways_out(&all_lanes, site, HUB_R + 4.0);
        // Sides by openness (the nearest way's alignment), leaning north; integer sort keys.
        let mut sides: Vec<(i32, u8)> = (0..16u8)
            .map(|k| {
                let d = rot16_dir(k);
                let worst = ways.iter().map(|w| d.dot(*w)).fold(-1.0f32, f32::max);
                (((worst - 0.6 * d.y) * 1024.0).round() as i32, k)
            })
            .collect();
        sides.sort_unstable();
        let rot = rot_of(g.landing - site);
        let (o, d) = monument(b, mark, site, rot, true);
        let mut placed = false;
        'sides: for &(_, k) in sides.iter().take(4) {
            let side = rot16_dir(k);
            // A grand statue stands half as tall again (its head clears the screen edge from well
            // beyond it); a fallen god-weapon leans out, away from the hub.
            let d = match d {
                Decor::Statue { at, radius, height, rot, god, variant } => {
                    Decor::Statue { at, radius, height: q(height * 1.5), rot, god, variant }
                }
                Decor::FallenWeapon { at, radius, height, variant, .. } => {
                    Decor::FallenWeapon { at, radius, height: q(height * 0.7), rot: rot_of(side), variant }
                }
                other => other,
            };
            for reach in [0.75f32, 0.6] {
                let (o, d) = monument_at(o, d, site + side * (HUB_R * reach), decor_rot(&d, rot));
                if force(g, b, &[o], d, Some(site)) {
                    placed = true;
                    break 'sides;
                }
            }
        }
        if !placed {
            let (o, d) = monument(b, MapMark::GreatBrazier, site, rot, true);
            if force(g, b, &[o], d, Some(site)) {
                g.regions[r].landmark = Some(MapMark::GreatBrazier);
            } else {
                g.trace(|| format!("region {r}: no room for its {mark:?} at {site}"));
                g.regions[r].landmark = None;
            }
        }
    }

    // The clearings' approaches keep clear of everything from here on.
    b.keep.extend(plan.approach.iter().filter(|(c, kr)| near_box(*c - Vec2::splat(*kr), *c + Vec2::splat(*kr))));

    // b–c) Edge slots take the theme's compositions (never repeating); a stamp that fails leaves
    //      an open field. Every other slot is an open field.
    let n_comps = theme.as_ref().map_or(2, |t| t.comps as usize);
    let (edges, mut fields) = cut_slots(g, r, x, n_comps);
    let pool: Vec<(DistrictKind, f32)> = theme.as_ref().map_or_else(Vec::new, |t| t.districts.clone());
    let mut used: Vec<DistrictKind> = Vec::new();
    for slot in edges {
        let flip = b.lay.chance(0.5);
        let f = Frame::of(slot.rect, slot.back, Vec2::ZERO, flip);
        let n0 = b.obstacles.len();
        let mut built: Option<(DistrictKind, Rect)> = None;
        let mut failed: Option<DistrictKind> = None;
        for _attempt in 0..2 {
            let w: Vec<f32> = pool
                .iter()
                .map(|(k, w)| if used.contains(k) || failed == Some(*k) { 0.0 } else { w.max(0.0) })
                .collect();
            let Some(p) = b.lay.weighted_index(&w) else { break };
            if let Some(rect) = stamp(b, pool[p].0, f) {
                built = Some((pool[p].0, rect));
                break;
            }
            failed = Some(pool[p].0);
        }
        match built {
            Some((kind, rect)) => {
                used.push(kind);
                plan.comps.push((r, rect, slot.back));
                plan.clear.push(slot.clear);
                plan.solids.extend(n0..b.obstacles.len());
                mouth_island(g, b, rect, slot.back);
                districts.push(District { kind, min: qv(rect.min), max: qv(rect.max) });
            }
            None => fields.push(slot),
        }
    }

    // The interior cover ceiling (§3.6.9): what the anchors and stories may still add.
    let t = &g.tiles;
    let interior = |i: usize| t.region[i] as usize == r && t.kind[i].is_land() && steps[i] >= INTERIOR_STEPS;
    let inner_area = (0..t.kind.len()).filter(|&i| interior(i)).count() as f32 * t.size * t.size;
    let standing: f32 = b.obstacles.iter().filter(|o| interior(tiles::tile_at(t, extent(o).0))).map(area).sum();
    let ceiling = theme.as_ref().map_or(0.02, |t| t.cover.clamp(0.0, 0.08)) * inner_area;
    let mut budget = ceiling - standing;
    let bare = theme.as_ref().map_or(0.5, |t| t.fields.clamp(0.0, 1.0));
    for slot in fields {
        let flip = b.lay.chance(0.5);
        let f = Frame::of(slot.rect, slot.back, Vec2::ZERO, flip);
        if b.lay.chance(1.0 - bare) {
            let c0 = b.covered;
            let n0 = b.obstacles.len();
            let ok = budget > 0.0 && anchor(b, f, x, budget);
            if ok {
                budget -= (b.covered - c0) as f32 * CELL * CELL;
                // The anchor stands on what is left of an old paving: a broken island around its
                // foot (§3.6.7), never a lone rug in the open (the open field gets floor marks).
                if let Some(o) = b.obstacles.get(n0) {
                    let (c, e) = extent(o);
                    let d = rot16_dir(b.vd(16));
                    let at = qv(c + d * (e.max_element() * 0.6 + b.rd(0.5, 1.5)));
                    let half = qv(Vec2::new(b.rd(2.8, 4.2), b.rd(2.2, 3.4)));
                    if g.tiles.kind_at(at) == TileKind::Ground && b.island_ok(at, ISLAND_APART) {
                        b.decal(Decor::Paving { at, half, variant: 3 });
                    }
                }
            }
            g.trace(|| {
                format!(
                    "region {r}: field anchor {} (budget {budget:.1} u² of {ceiling:.1})",
                    if ok { "stands" } else { "skipped" }
                )
            });
        }
        districts.push(District { kind: DistrictKind::Field, min: qv(slot.rect.min), max: qv(slot.rect.max) });
    }

    // e) Story clusters on the region's frame band.
    let key = theme.as_ref().map_or(String::new(), |t| t.key.clone());
    let n_story = theme.as_ref().map_or(1, |t| t.story);
    stories(g, b, x, r, &key, n_story, plan);

    // f) Floor dressing: glowing fissures, only near heat (the rest of the ground shows cold
    //    cracked earth, painted by the floor shader).
    let (x0, y0, x1, y1) = (g.regions[r].lo.0, g.regions[r].lo.1, g.regions[r].hi.0, g.regions[r].hi.1);
    let land = g.regions[r].area as f32 * g.tiles.size * g.tiles.size;
    let per = (land / 1500.0).max(2.0) as u32;
    for _ in 0..per {
        let tx = b.dress.range_u32(x0 as u32, x1 as u32 + 1) as u16;
        let ty = b.dress.range_u32(y0 as u32, y1 as u32 + 1) as u16;
        let i = g.tiles.index(tx, ty);
        if g.tiles.kind[i] == TileKind::Ground && g.tiles.region[i] as usize == r {
            let at = g.tiles.center(tx, ty);
            let d = rot16_dir(b.vd(16));
            let segs = b.dress.range_u32(2, 5);
            let width = if g.biome == Biome::Cinder { b.rd(0.3, 0.55) } else { b.rd(0.2, 0.4) };
            b.fissure(at, d, segs, width);
        }
    }

    b.lanes = all_lanes;
    b.keep = all_keep;
}

/// A cobble island at a composition's open mouth (§3.6.7): the floor it opens onto was paved once.
fn mouth_island(g: &Gen, b: &mut Builder, rect: Rect, back: Vec2) {
    let depth = (if back.x != 0.0 { rect.size().x } else { rect.size().y }) * 0.5;
    let at = qv(rect.center() - back * (depth + b.rd(1.5, 3.0)));
    let (long, short) = (b.rd(3.0, 5.0), b.rd(2.0, 3.0));
    let half = qv(if back.x != 0.0 { Vec2::new(short, long) } else { Vec2::new(long, short) });
    if g.tiles.kind_at(at) == TileKind::Ground && b.island_ok(at, ISLAND_APART) {
        b.decal(Decor::Paving { at, half, variant: 3 });
    }
}

/// Up to `n` story clusters on region `r`'s frame band (§3.6.4): tiles with a pit or a barrier
/// wall beside them, outside every composition's clear band, tried in a seeded order (at most 40
/// tries). The tall recipes (a foundry chimney, a chainyard anchor post, a colonnade arch) stand
/// only where that edge lies to the north; elsewhere a slag heap.
fn stories(g: &Gen, b: &mut Builder, x: &ComposeDef, r: usize, key: &str, n: u8, plan: &mut Plan) {
    if n == 0 {
        return;
    }
    let t = &g.tiles;
    let reg = &g.regions[r];
    let walled: Vec<usize> = g
        .walls
        .iter()
        .filter_map(|&k| {
            let a = &g.adj[k];
            (a.barrier == Some(BarrierKind::Wall) && (a.a == r || a.b == r)).then_some(if a.a == r { a.b } else { a.a })
        })
        .collect();
    let mut cands: Vec<(Vec2, Vec2)> = Vec::new();
    for y in reg.lo.1..=reg.hi.1 {
        for xx in reg.lo.0..=reg.hi.0 {
            let i = t.index(xx, y);
            if t.kind[i] != TileKind::Ground || t.region[i] as usize != r {
                continue;
            }
            let c = t.center(xx, y);
            if plan.clear.iter().any(|rc| rc.contains(c, 0.0)) {
                continue;
            }
            for (dx, dy) in [(0i32, 1i32), (1, 0), (-1, 0), (0, -1)] {
                let (nx, ny) = (xx as i32 + dx, y as i32 + dy);
                let edge = if nx < 0 || ny < 0 || nx >= t.w as i32 || ny >= t.h as i32 {
                    true
                } else {
                    let j = t.index(nx as u16, ny as u16);
                    t.kind[j].is_pit() || (t.kind[j].is_land() && walled.contains(&(t.region[j] as usize)))
                };
                if edge {
                    cands.push((c, Vec2::new(dx as f32, dy as f32)));
                    break;
                }
            }
        }
    }
    // A seeded order (Fisher–Yates on the lay stream).
    for i in (1..cands.len()).rev() {
        let j = b.lay.range_u32(0, i as u32 + 1) as usize;
        cands.swap(i, j);
    }
    let mut placed = 0u8;
    for &(c, d) in cands.iter().take(40) {
        if placed >= n {
            break;
        }
        let recipe = if d.y > 0.5 { key } else { "slag_flats" };
        for off in [1.0f32, 0.0, -1.0] {
            let at = qv(c + d * off);
            if !b.off_lanes(at, x.road_clear + 2.5) || b.keep.iter().any(|(k, kr)| at.distance(*k) < kr + 3.0) {
                continue;
            }
            let n0 = b.obstacles.len();
            if story(b, at, recipe) {
                let reach = b.obstacles[n0..]
                    .iter()
                    .map(|o| {
                        let (oc, e) = extent(o);
                        oc.distance(at) + e.max_element()
                    })
                    .fold(1.0f32, f32::max);
                plan.stories.push((r, at, reach));
                plan.solids.extend(n0..b.obstacles.len());
                placed += 1;
                break;
            }
        }
    }
}

/// A story cluster (instead of a generic ruin), by theme: slag heaps on the flats and dunes, a
/// collapsed chimney in the foundries, a chained anchor post in the chainyard, a broken standing
/// arch in the colonnades. False when it did not fit.
fn story(b: &mut Builder, at: Vec2, theme: &str) -> bool {
    let g = b.group();
    match theme {
        "foundry_ruins" => {
            let half = Vec2::splat(b.rl(0.8, 1.0));
            let (height, variant) = (q(b.rd(6.0, 8.0)), b.vd(4));
            let style = WallStyle::Forge;
            if !b.block(g, at, half, |at, half| Decor::Wall { at, half, height, style, variant }) {
                return false;
            }
            // Its fallen upper courses lie beside it.
            let d = rot16_dir(b.lay.range_u32(0, 16) as u8);
            let r = q(b.rl(0.55, 0.7));
            let from = at + d * (half.x + r + 0.6);
            let len = b.rl(3.0, 4.5);
            b.chain(g, from, from + d * len, r, r, |from, to| Decor::FallenColumn { from, to, radius: r });
            b.rubble(at - d * 1.8, 0.7, 1.2);
            true
        }
        "chainyard" => {
            let r = q(b.rl(0.55, 0.7));
            let height = q(b.rd(4.5, 6.0));
            if !b.circle(g, at, r, |at, radius| Decor::Pillar { at, radius, height }) {
                return false;
            }
            // Chains run from the anchor post to two stakes (colliding: laid on the lay stream,
            // so the dressing never moves them).
            for k in 0..2u32 {
                let d = rot16_dir(b.lay.range_u32(0, 16) as u8);
                let stake = qv(at + d * b.rl(3.0, 4.2));
                let sr = 0.3;
                let sh = q(b.rd(1.1, 1.5));
                if b.circle(g, stake, sr, |at, radius| Decor::Pillar { at, radius, height: sh }) {
                    b.decal(Decor::Chains { from: qv(at), to: stake, height: q(sh - 0.1) });
                }
                if k == 0 {
                    let off = rot16_dir(b.vd(16)) * 2.0;
                    b.clutter(at + off, 0.6, 1.0, Some(ClutterKind::WeaponRack));
                }
            }
            true
        }
        "colonnade_of_oaths" => {
            let d = rot16_dir(b.lay.range_u32(0, 8) as u8 * 2);
            let pier = b.rl(0.6, 0.75);
            let span = b.rl(2.6, 3.4);
            arch(b, at - d * span, at + d * span, pier)
        }
        _ => {
            if !boulder(b, g, at, 1.5, 2.3) {
                return false;
            }
            let main = b.obstacles.last().map_or((at, 1.5), |o| {
                let (c, e) = extent(o);
                (c, e.max_element())
            });
            for _ in 0..2 {
                satellite(b, g, main);
            }
            let d = rot16_dir(b.vd(16));
            let segs = b.dress.range_u32(2, 4);
            let width = b.rd(0.3, 0.45);
            b.fissure(at + d * (main.1 + 0.6), d, segs, width);
            true
        }
    }
}

// ───────────────────────────── the frame ─────────────────────────────

/// Region `r`'s void shore in walking order: chains of shore tiles (land of `r` with a `Void`
/// 4-neighbour or off the grid), each walked from its lowest-index end to the next unvisited
/// 8-neighbour (the lowest index first), with the tile's outward direction.
fn shore_chains(g: &Gen, r: usize) -> Vec<Vec<(usize, Vec2)>> {
    let t = &g.tiles;
    let reg = &g.regions[r];
    let (w, h) = (t.w as i32, t.h as i32);
    let void =
        |x: i32, y: i32| x < 0 || y < 0 || x >= w || y >= h || t.kind[t.index(x as u16, y as u16)] == TileKind::Void;
    let mut out_dir: BTreeMap<usize, Vec2> = BTreeMap::new();
    for y in reg.lo.1..=reg.hi.1 {
        for x in reg.lo.0..=reg.hi.0 {
            let i = t.index(x, y);
            if t.kind[i] != TileKind::Ground || t.region[i] as usize != r {
                continue;
            }
            let (xi, yi) = (x as i32, y as i32);
            let mut o = Vec2::ZERO;
            for (dx, dy) in [(1i32, 0i32), (-1, 0), (0, 1), (0, -1)] {
                if void(xi + dx, yi + dy) {
                    o += Vec2::new(dx as f32, dy as f32);
                }
            }
            if o != Vec2::ZERO {
                out_dir.insert(i, o / o.length());
            } else if [(1i32, 0i32), (-1, 0), (0, 1), (0, -1)].iter().any(|&(dx, dy)| void(xi + dx, yi + dy)) {
                // Void on opposite sides (a spit): face north, then east.
                out_dir.insert(i, Vec2::Y);
            }
        }
    }
    let neighbours = |i: usize| -> Vec<usize> {
        let (x, y) = ((i % t.w as usize) as i32, (i / t.w as usize) as i32);
        let mut v = Vec::new();
        for dy in -1..=1 {
            for dx in -1..=1 {
                let (nx, ny) = (x + dx, y + dy);
                if (dx, dy) != (0, 0) && nx >= 0 && ny >= 0 && nx < w && ny < h {
                    let j = t.index(nx as u16, ny as u16);
                    if out_dir.contains_key(&j) {
                        v.push(j);
                    }
                }
            }
        }
        v.sort_unstable();
        v
    };
    let mut seen: BTreeMap<usize, bool> = out_dir.keys().map(|&i| (i, false)).collect();
    let mut chains = Vec::new();
    loop {
        // Start at the lowest unvisited tile with the fewest unvisited neighbours (a chain's end).
        let open: Vec<usize> = seen.iter().filter(|(_, v)| !**v).map(|(i, _)| *i).collect();
        let Some(&start) = open.iter().min_by_key(|&&i| (neighbours(i).iter().filter(|j| !seen[*j]).count(), i)) else {
            break;
        };
        let mut chain = Vec::new();
        let mut cur = start;
        loop {
            seen.insert(cur, true);
            chain.push((cur, out_dir[&cur]));
            match neighbours(cur).into_iter().find(|j| !seen[j]) {
                Some(j) => cur = j,
                None => break,
            }
        }
        chains.push(chain);
    }
    chains
}

/// Region `r`'s frame (§3.6.4, §3.6.5): framed runs of its void shore (never near a road, bridge,
/// plaza, pass or the Landing), colliding coast anchors along them on the lay stream
/// (`2000 + r`), and the visual frame on the dress stream (`2100 + r`): lip pieces on the cliff
/// edge, tall backdrop silhouettes rising beyond the far shores and low dark foreground shapes off
/// the camera-side ones.
fn frame(g: &Gen, b: &mut Builder, x: &ComposeDef, r: usize, plan: &mut Plan) {
    let share = g.x.themes.get(g.regions[r].theme as usize).map_or(0.5, |t| t.frame.clamp(0.0, 1.0));
    if share <= 0.0 || g.regions[r].area == 0 {
        return;
    }
    let t = &g.tiles;
    b.lay = g.root.fork(2000 + r as u64);
    b.dress = g.root.fork(2100 + r as u64);
    let gap = x.frame_gap.max(0.0);
    let reach = (gap / t.size).ceil() as i32 + 1;
    let hs = Vec2::splat(t.size * 0.5);
    let unframed = |i: usize| -> bool {
        let c = t.center((i % t.w as usize) as u16, (i / t.w as usize) as u16);
        if c.distance(g.landing) < 16.0
            || g.pois.iter().any(|p| c.distance(p.site.at) < p.plaza + 5.0)
            || g.passes.iter().any(|p| c.distance(p.at) < gap)
        {
            return true;
        }
        let (x, y) = ((i % t.w as usize) as i32, (i / t.w as usize) as i32);
        for dy in -reach..=reach {
            for dx in -reach..=reach {
                let (nx, ny) = (x + dx, y + dy);
                if nx < 0 || ny < 0 || nx >= t.w as i32 || ny >= t.h as i32 {
                    continue;
                }
                let j = t.index(nx as u16, ny as u16);
                let way = matches!(t.kind[j], TileKind::Road | TileKind::Bridge | TileKind::Plaza);
                if way && crate::procgen::point_box(c, t.center(nx as u16, ny as u16), hs) < gap {
                    return true;
                }
            }
        }
        false
    };
    let (run_lo, run_hi) = (x.frame_run.0.min(x.frame_run.1).max(4.0), x.frame_run.1.max(x.frame_run.0).max(4.0));
    let ratio = (1.0 - share) / share.max(0.05);
    let mut runs: Vec<Vec<(usize, Vec2)>> = Vec::new();
    for chain in shore_chains(g, r) {
        let mut framing = false;
        let mut left = b.rl(0.0, run_hi * ratio);
        let mut cur: Vec<(usize, Vec2)> = Vec::new();
        let mut prev: Option<Vec2> = None;
        for &(i, out) in &chain {
            let c = t.center((i % t.w as usize) as u16, (i / t.w as usize) as u16);
            let step = prev.map_or(t.size, |p| p.distance(c));
            prev = Some(c);
            if step > t.size * 1.5 || unframed(i) {
                if !cur.is_empty() {
                    runs.push(std::mem::take(&mut cur));
                }
                if framing {
                    framing = false;
                    left = b.rl(run_lo, run_hi) * ratio;
                }
                continue;
            }
            left -= step;
            if left <= 0.0 {
                framing = !framing;
                if framing {
                    left = b.rl(run_lo, run_hi);
                } else {
                    if !cur.is_empty() {
                        runs.push(std::mem::take(&mut cur));
                    }
                    left = b.rl(run_lo, run_hi) * ratio;
                }
            }
            if framing {
                cur.push((i, out));
            }
        }
        if !cur.is_empty() {
            runs.push(cur);
        }
    }
    // Coast anchors: a boulder at most every `coast_anchor_every` u of framed shore, its centre
    // just short of the tile's outer edge, so it overhangs the lip and makes a nook without
    // narrowing the walkable band by more than 2 u.
    let every = ((x.coast_anchor_every.max(t.size) / t.size).round() as usize).max(1);
    for run in &runs {
        let mut k = b.lay.range_u32(0, every as u32) as usize;
        while k < run.len() {
            let (i, out) = run[k];
            let c = t.center((i % t.w as usize) as u16, (i / t.w as usize) as u16);
            let rr = q(b.rl(0.8, 1.4));
            let at = qv(c + out * 1.4);
            let variant = b.vd(4);
            let grp = b.group();
            let n0 = b.obstacles.len();
            if t.kind_at(at) == TileKind::Ground
                && unmasked(b, |b| b.circle(grp, at, rr, |at, radius| Decor::Boulder { at, radius, variant }))
            {
                plan.solids.extend(n0..b.obstacles.len());
            }
            k += every;
        }
    }
    // The visual frame.
    let void3 = |p: Vec2| {
        (-1..=1).all(|dy| (-1..=1).all(|dx| t.kind_at(p + Vec2::new(dx as f32, dy as f32) * t.size) == TileKind::Void))
    };
    let behind_void = |p: Vec2, r: f32, reach: f32| {
        let mut y = 0.0;
        while y <= reach {
            for dx in [-r, 0.0, r] {
                if t.kind_at(p + Vec2::new(dx, y)) != TileKind::Void {
                    return false;
                }
            }
            y += 2.0;
        }
        true
    };
    let mut backs: Vec<Vec2> = Vec::new();
    let mut fores: Vec<Vec2> = Vec::new();
    for run in &runs {
        for &(i, out) in run {
            let c = t.center((i % t.w as usize) as u16, (i / t.w as usize) as u16);
            let along = out.perp();
            // Two or three lip pieces per framed tile: the edge reads as a crumbling rim, dense
            // where the play space stops.
            for _ in 0..b.dress.range_u32(2, 4) {
                let at = qv(c + out * b.rd(2.3, 3.6) + along * b.rd(-1.8, 1.8));
                let (radius, height, rot, variant) = (q(b.rd(0.8, 1.8)), q(b.rd(0.6, 2.6)), b.vd(16), b.vd(4));
                if t.kind_at(at) == TileKind::Void {
                    b.decal(Decor::Scenery { at, radius, height, kind: SceneryKind::Lip, rot, variant });
                }
            }
            let (lo, hi, h, apart, kind) = if out.y >= 0.7 {
                (5.0, 11.0, (9.0, 16.0), 8.0, SceneryKind::Backdrop)
            } else if out.x.abs() >= 0.7 {
                (5.0, 9.0, (6.0, 10.0), 10.0, SceneryKind::Backdrop)
            } else if out.y <= -0.7 {
                (3.0, 6.0, (1.5, 5.0), 6.0, SceneryKind::Foreground)
            } else {
                continue;
            };
            let at = qv(c + out * (t.size * 0.5 + b.rd(lo, hi)) + along * b.rd(-1.5, 1.5));
            let (height, rot, variant) = (q(b.rd(h.0, h.1)), b.vd(16), b.vd(4));
            let radius = q(if kind == SceneryKind::Backdrop { b.rd(1.6, 3.0) } else { b.rd(1.4, 2.8) });
            let list = if kind == SceneryKind::Backdrop { &mut backs } else { &mut fores };
            // Seen by the fixed camera a tall piece hides the ground north of it (about 0.7 u per
            // unit of height): a backdrop only stands where that is all void, so it frames the
            // land from beyond and never looms over it.
            // And it rises behind land, as the camera sees it: some land lies within 20 u to
            // its south (a backdrop alone in the void at the map's south edge would stand in the
            // foreground instead).
            let backed = (1..=5).any(|k| t.kind_at(at - Vec2::Y * (k as f32 * t.size)).is_land());
            let open = if kind == SceneryKind::Backdrop {
                void3(at) && behind_void(at, radius, height * 0.75 + radius) && backed
            } else {
                t.kind_at(at) == TileKind::Void
            };
            if open && list.iter().all(|p| p.distance(at) >= apart) {
                list.push(at);
                b.decal(Decor::Scenery { at, radius, height, kind, rot, variant });
            }
        }
    }
    for run in runs {
        plan.shores.push((r, run));
    }
}

/// Open region borders (no wall, ridge or river) as seams (the critique of §3.6.4: an open
/// border was only a tint blend, so the map read as one plain): chains of the border's tile
/// faces on region a's side are walked in order, and `compose.seam` of their length is laid as
/// runs of `seam_run` u with gaps of at least `seam_gap`, never within `seam_pass_clear` of a
/// road crossing it, a POI clearing, a hub or the Landing. Each run gets low `Scenery::Seam`
/// courses every 2.6–4.2 u (dress, `2700 + k`; the client paints a dark scree band under them) and
/// one colliding ruined pier at an end (lay, `2600 + k`): the frame mass the eye reads as the
/// edge of a place, while the border stays open to walk across.
fn seams(g: &Gen, b: &mut Builder, x: &ComposeDef, plan: &mut Plan) {
    let share = x.seam.clamp(0.0, 1.0);
    if share <= 0.0 {
        return;
    }
    let t = &g.tiles;
    let w = t.w as usize;
    let lanes = g.lanes();
    let (run_lo, run_hi) = (x.seam_run.0.min(x.seam_run.1).max(4.0), x.seam_run.1.max(x.seam_run.0).max(4.0));
    let ratio = ((1.0 - share) / share.max(0.05)).max(0.0);
    let hubs: Vec<Vec2> = g.regions.iter().filter(|r| r.landmark.is_some()).map(|r| r.site).collect();
    for (k, adj) in g.adj.iter().enumerate() {
        if adj.barrier.is_some() || adj.border == 0 {
            continue;
        }
        let (ra, rb) = (adj.a, adj.b);
        b.lay = g.root.fork(2600 + k as u64);
        b.dress = g.root.fork(2700 + k as u64);
        // Region a's border tiles: the point on the border line and the normal toward b.
        let mut faces: BTreeMap<usize, (Vec2, Vec2)> = BTreeMap::new();
        for i in 0..t.kind.len() {
            if t.region[i] as usize != ra || !t.kind[i].is_land() {
                continue;
            }
            let (xx, yy) = ((i % w) as i32, (i / w) as i32);
            let mut n = Vec2::ZERO;
            for (dx, dy) in [(1i32, 0i32), (-1, 0), (0, 1), (0, -1)] {
                let (nx, ny) = (xx + dx, yy + dy);
                if nx < 0 || ny < 0 || nx >= t.w as i32 || ny >= t.h as i32 {
                    continue;
                }
                let j = t.index(nx as u16, ny as u16);
                if t.kind[j].is_land() && t.region[j] as usize == rb {
                    n += Vec2::new(dx as f32, dy as f32);
                }
            }
            if n != Vec2::ZERO {
                let n = n / n.length();
                faces.insert(i, (t.center(xx as u16, yy as u16) + n * (t.size * 0.5), n));
            }
        }
        if faces.is_empty() {
            continue;
        }
        let crossings: Vec<Vec2> =
            g.roads.iter().filter(|r| (r.a, r.b) == (ra, rb) || (r.a, r.b) == (rb, ra)).map(|r| r.pass).collect();
        let open = |q: Vec2| -> bool {
            t.kind_at(q) == TileKind::Ground
                && crossings.iter().all(|c| c.distance(q) >= x.seam_pass_clear)
                && lanes.iter().all(|l| point_seg(q, l.from, l.to) >= l.width * 0.5 + 3.0)
                && g.pois.iter().all(|poi| q.distance(poi.site.at) >= poi.plaza + 5.0)
                && q.distance(g.landing) >= LANDING_R + 6.0
                && hubs.iter().all(|h| q.distance(*h) >= HUB_R + 3.0)
        };
        // Chains in walking order (8-neighbours, lowest index first), as in `shore_chains`.
        let neighbours = |i: usize| -> Vec<usize> {
            let (xx, yy) = ((i % w) as i32, (i / w) as i32);
            let mut v = Vec::new();
            for dy in -1..=1 {
                for dx in -1..=1 {
                    let (nx, ny) = (xx + dx, yy + dy);
                    if (dx, dy) != (0, 0) && nx >= 0 && ny >= 0 && nx < t.w as i32 && ny < t.h as i32 {
                        let j = t.index(nx as u16, ny as u16);
                        if faces.contains_key(&j) {
                            v.push(j);
                        }
                    }
                }
            }
            v
        };
        let mut seen: BTreeMap<usize, bool> = faces.keys().map(|&i| (i, false)).collect();
        let mut runs: Vec<Vec<(Vec2, Vec2)>> = Vec::new();
        loop {
            let open_tiles: Vec<usize> = seen.iter().filter(|(_, v)| !**v).map(|(i, _)| *i).collect();
            let Some(&start) =
                open_tiles.iter().min_by_key(|&&i| (neighbours(i).iter().filter(|j| !seen[*j]).count(), i))
            else {
                break;
            };
            let mut cur = start;
            let mut framing = false;
            let mut left = b.rd(0.0, run_hi * ratio);
            let mut run: Vec<(Vec2, Vec2)> = Vec::new();
            let mut prev: Option<Vec2> = None;
            loop {
                seen.insert(cur, true);
                let (p, n) = faces[&cur];
                let step = prev.map_or(t.size, |q| q.distance(p));
                prev = Some(p);
                if step > t.size * 1.6 || !open(p) {
                    if run.len() > 1 {
                        runs.push(std::mem::take(&mut run));
                    }
                    run.clear();
                    if framing {
                        framing = false;
                        left = (b.rd(run_lo, run_hi) * ratio).max(x.seam_gap);
                    }
                } else {
                    left -= step;
                    if left <= 0.0 {
                        framing = !framing;
                        if framing {
                            left = b.rd(run_lo, run_hi);
                        } else {
                            if run.len() > 1 {
                                runs.push(std::mem::take(&mut run));
                            }
                            run.clear();
                            left = (b.rd(run_lo, run_hi) * ratio).max(x.seam_gap);
                        }
                    }
                    if framing {
                        run.push((p, n));
                    }
                }
                match neighbours(cur).into_iter().find(|j| !seen[j]) {
                    Some(j) => cur = j,
                    None => break,
                }
            }
            if run.len() > 1 {
                runs.push(run);
            }
        }
        // The seam's look by the themes on either side: a ruined wall course (foundry,
        // colonnade), a scrap heap (chainyard), else a slag berm; variants 4–7 are the second form.
        let style = |r: usize| match g.x.themes.get(g.regions[r].theme as usize).map_or("", |th| th.key.as_str()) {
            "foundry_ruins" | "colonnade_of_oaths" => 0u8,
            "chainyard" => 3,
            _ => 2,
        };
        let styles = [style(ra), style(rb)];
        for run in runs {
            // Courses every 2.6–4.2 u along the run's polyline.
            let mut s_next = b.rd(0.5, 2.0);
            let mut s = 0.0;
            for i in 1..run.len() {
                let ((p0, _), (p, n)) = (run[i - 1], run[i]);
                let len = p0.distance(p);
                while s_next <= s + len {
                    let along = (p - p0).normalize_or(n.perp());
                    let on = p0.lerp(p, ((s_next - s) / len.max(1e-3)).clamp(0.0, 1.0));
                    let at = qv(on + n * b.rd(-0.5, 0.5));
                    let variant = styles[b.dress.range_u32(0, 2) as usize] + if b.dress.chance(0.5) { 0 } else { 4 };
                    let (radius, height) = (q(b.rd(1.1, 1.8)), q(b.rd(0.45, 1.15)));
                    if t.kind_at(at) == TileKind::Ground {
                        let rot = rot_of(along);
                        b.decal(Decor::Scenery { at, radius, height, kind: SceneryKind::Seam, rot, variant });
                    }
                    s_next += b.rd(2.6, 4.2);
                }
                s += len;
            }
            // One ruined pier at an end of the run: the frame's vertical note, a kiting nook.
            let end = if b.lay.chance(0.5) { run[0] } else { run[run.len() - 1] };
            let at = qv(end.0 - end.1 * 0.6);
            let half = qv(Vec2::splat(b.rl(0.6, 0.85)));
            let height = q(b.rd(1.8, 3.0));
            let variant = b.vd(4);
            let grp = b.group();
            let n0 = b.obstacles.len();
            if b.block(grp, at, half, |at, half| Decor::Wall { at, half, height, style: WallStyle::Ruin, variant }) {
                plan.solids.extend(n0..b.obstacles.len());
                b.rubble(at - end.1.perp() * 1.4, 0.5, 0.9);
            }
            let mid = run[run.len() / 2];
            plan.runs.push((ra, rb, mid.0, mid.1));
        }
    }
}

// ───────────────────────────── dressing ─────────────────────────────

/// Braziers along every road, 36–48 u apart on alternating sides (pools of warm light with dusk
/// between them), skipped where another fire already burns within 16 u or a lit POI clearing
/// lies within 14 u of its rim; bridge decks with fire at their heads.
fn dress_roads(g: &Gen, b: &mut Builder) {
    let lanes = g.lanes();
    let mut fires: Vec<Vec2> = b
        .decor
        .iter()
        .filter_map(|d| match *d {
            Decor::Brazier { at } | Decor::GreatBrazier { at, .. } => Some(at),
            _ => None,
        })
        .collect();
    for (k, l) in lanes.iter().enumerate() {
        b.dress = g.root.fork(700 + k as u64);
        let len = l.from.distance(l.to);
        if len < 6.0 {
            continue;
        }
        let dir = (l.to - l.from) / len;
        let n = Vec2::new(-dir.y, dir.x);
        let mut s = b.rd(6.0, 16.0);
        let mut side = if b.dress.chance(0.5) { 1.0 } else { -1.0 };
        while s < len - 3.0 {
            let at = l.from + dir * s + n * (side * (l.width * 0.5 + 1.3));
            // A lit clearing already carries the road past it (its ring and key light).
            let lit = g.pois.iter().any(|p| p.site.at.distance(at) < p.plaza + 14.0);
            if !lit && fires.iter().all(|f| f.distance(at) >= 16.0) {
                b.brazier(at);
                fires.push(at);
            }
            side = -side;
            s += b.rd(36.0, 48.0);
        }
    }
    for (k, deck) in g.bridges.iter().enumerate() {
        b.dress = g.root.fork(760 + k as u64);
        b.decal(Decor::Bridge { from: deck.from, to: deck.to, width: deck.width });
        let dir = (deck.to - deck.from).normalize_or(Vec2::X);
        // One fire at each head, on opposite sides: the deck reads lit end to end without a
        // pair of pools at both.
        let n = Vec2::new(-dir.y, dir.x) * (deck.width * 0.5 + 0.9);
        for (end, s) in [(deck.from, -1.0f32), (deck.to, 1.0)] {
            b.brazier(end + dir * (s * 1.2) + n * s);
        }
    }
}

/// A tall standing piece every 22–28 u along each road, off its shoulder on alternating sides,
/// with `chance` per slot: a column, or in the forge biome now and then a chimney stack. Off by
/// default (§3.6.3): the vertical rhythm comes from the frame and the hub monuments.
fn road_silhouettes(g: &Gen, b: &mut Builder, chance: f32) {
    for (k, l) in g.lanes().iter().enumerate() {
        b.lay = g.root.fork(1000 + k as u64);
        b.dress = g.root.fork(1100 + k as u64);
        let len = l.from.distance(l.to);
        if len < 14.0 {
            continue;
        }
        let dir = (l.to - l.from) / len;
        let n = Vec2::new(-dir.y, dir.x);
        let mut s = b.rl(8.0, 14.0);
        let mut side = if b.lay.chance(0.5) { 1.0 } else { -1.0 };
        while s < len - 6.0 {
            if b.lay.chance(chance) {
                for try_side in [side, -side] {
                    let at = l.from + dir * s + n * (try_side * (l.width * 0.5 + b.lane_pad + b.rl(2.4, 3.4)));
                    let grp = b.group();
                    let chimney = b.biome == Biome::Cinder && b.lay.chance(0.3);
                    let placed = if chimney {
                        let half = Vec2::splat(b.rl(0.7, 0.9));
                        let (height, variant) = (q(b.rd(6.5, 8.5)), b.vd(4));
                        let style = WallStyle::Forge;
                        b.block(grp, at, half, |at, half| Decor::Wall { at, half, height, style, variant })
                    } else {
                        let r = b.rl(0.55, 0.75);
                        let height = q(b.rd(5.5, 8.0));
                        b.circle(grp, at, r, |at, radius| Decor::Pillar { at, radius, height })
                    };
                    if placed {
                        let off = dir * b.rd(1.2, 2.0);
                        b.rubble(at + off, 0.5, 0.9);
                        break;
                    }
                }
            }
            side = -side;
            s += b.rl(22.0, 28.0);
        }
    }
}

/// The facing a monument decor carries (for moving it with [`monument_at`]).
fn decor_rot(d: &Decor, fallback: Rot16) -> Rot16 {
    match *d {
        Decor::Statue { rot, .. }
        | Decor::ColossusHead { rot, .. }
        | Decor::GreatAnvil { rot, .. }
        | Decor::Crystal { rot, .. }
        | Decor::SpiralStair { rot, .. }
        | Decor::FallenWeapon { rot, .. } => rot,
        Decor::Rift { rot, .. } => rot.wrapping_sub(4),
        _ => fallback,
    }
}

/// What a road leading into region `r` is for: the region's major POI, else its first Seal POI.
fn destination(g: &Gen, r: usize) -> Option<PoiKind> {
    if let Some(m) = g.regions[r].major {
        return Some(g.pois[m].site.kind);
    }
    g.pois.iter().find(|p| p.site.region as usize == r && p.site.seals > 0).map(|p| p.site.kind)
}

/// A waymark at each end of every road, just outside the crossroads it leaves (its hub or POI
/// clearing), its pennant in the colour of what waits at the road's other end.
fn waymarks(g: &Gen, b: &mut Builder) {
    let width = q(g.x.roads.width);
    for (k, road) in g.roads.iter().enumerate() {
        let (Some(first), Some(last)) = (road.lanes.first(), road.lanes.last()) else { continue };
        for (end, from, toward, dest) in [(road.a, first.from, first.to, road.b), (road.b, last.to, last.from, road.a)]
        {
            let Some(kind) = destination(g, dest) else { continue };
            let reg = &g.regions[end];
            let clear = match reg.major {
                Some(m) => g.pois[m].plaza,
                None if reg.landmark.is_some() => HUB_R,
                None => 4.0,
            };
            let len = from.distance(toward);
            if len < 1.0 {
                continue;
            }
            let dir = (toward - from) / len;
            // Walk out along the lane until clear of the crossroads.
            let mut s = 0.0;
            while s < len && (from + dir * s).distance(reg.site) < clear + 2.5 {
                s += 1.0;
            }
            if s >= len {
                continue;
            }
            let n = Vec2::new(-dir.y, dir.x);
            let side = if k % 2 == 0 { 1.0 } else { -1.0 };
            let at = qv(from + dir * s + n * (side * (width * 0.5 + 0.9)));
            b.decal(Decor::Waymark { at, rot: rot_of(dir), kind });
        }
    }
}

/// A clearing's heart inlay, its ring of braziers and its kind's props.
fn dress_clearing(g: &Gen, b: &mut Builder, k: usize) {
    let p = g.pois[k];
    let (at, radius, plaza) = (p.site.at, p.site.radius, p.plaza);
    b.dress = g.root.fork(420 + k as u64);
    let rot = b.vd(16);
    let god = p.site.god.unwrap_or(0);
    let (variant, heart) = match p.site.kind {
        PoiKind::Anvil => (1, radius),
        PoiKind::Warlord => (4, 4.0),
        PoiKind::Lair => (4, 3.0),
        PoiKind::Shrine => (3, radius),
        PoiKind::Reliquary => (2, radius),
        PoiKind::Vein => (1, radius),
        PoiKind::Spring => (0, radius),
        PoiKind::Watchfire => (1, radius),
        PoiKind::Gate => (1, radius),
    };
    b.decal(Decor::FloorInlay { at, radius: q(heart), rot, variant, god });
    if plaza >= radius + 3.0 {
        b.decal(Decor::FloorInlay { at, radius: q(plaza - 0.8), rot: rot.wrapping_add(2), variant: 0, god });
    }
    // A ring of braziers at the clearing's rim.
    let n = if plaza >= 12.0 { 8u8 } else { 4 };
    let r = plaza - 0.8;
    for i in 0..n {
        b.brazier(at + rot16_dir(rot.wrapping_add(i * (16 / n) + 1)) * r);
    }
    match p.site.kind {
        PoiKind::Shrine => {
            for i in 0..4u8 {
                let d = rot16_dir(rot.wrapping_add(i * 4 + 3));
                let height = q(b.rd(4.0, 5.5));
                b.prop(Decor::Banner { at: qv(at + d * (plaza - 1.6)), height, rot: rot_of(-d), god }, 0.3);
            }
            b.clutter(at + rot16_dir(rot.wrapping_add(8)) * (radius + 1.5), 0.6, 1.0, Some(ClutterKind::Candles));
        }
        PoiKind::Reliquary => {
            for i in 0..3u8 {
                let d = rot16_dir(rot.wrapping_add(i * 5 + 2));
                b.clutter(at + d * (radius + 1.6), 0.6, 1.0, Some(ClutterKind::Offerings));
            }
        }
        PoiKind::Vein => {
            for i in 0..4u8 {
                let d = rot16_dir(rot.wrapping_add(i * 4));
                b.clutter(at + d * (radius + 1.4), 0.6, 1.0, Some(ClutterKind::Shards));
                let segs = b.dress.range_u32(2, 4);
                b.fissure(at + d * radius, d, segs, 0.35);
            }
        }
        PoiKind::Lair => {
            for i in 0..6u8 {
                let d = rot16_dir(rot.wrapping_add(i * 3 + 1));
                let s = b.rd(radius * 0.5, radius - 1.5);
                b.clutter(at + d * s, 0.6, 1.1, Some(ClutterKind::Bones));
            }
        }
        PoiKind::Warlord => {
            for i in 0..5u8 {
                let d = rot16_dir(rot.wrapping_add(i * 3));
                let segs = b.dress.range_u32(2, 5);
                b.fissure(at + d * 4.5, d, segs, 0.4);
            }
        }
        PoiKind::Spring => {
            // The basin's rim: a painted rune ring (no standing stones in the way).
            b.decal(Decor::FloorInlay { at, radius: q(radius + 1.0), rot: rot.wrapping_add(4), variant: 1, god });
        }
        PoiKind::Anvil => {
            for i in 0..2u8 {
                let d = rot16_dir(rot.wrapping_add(i * 8 + 4));
                let kind = if i == 0 { ClutterKind::Ingots } else { ClutterKind::WeaponRack };
                b.clutter(at + d * (radius + 2.0), 0.7, 1.1, Some(kind));
            }
        }
        PoiKind::Gate => {
            for i in 0..2u8 {
                let d = rot16_dir(rot.wrapping_add(i * 8 + 2));
                let height = q(b.rd(5.0, 6.5));
                b.prop(Decor::Banner { at: qv(at + d * (radius + 1.8)), height, rot: rot_of(-d), god: 0 }, 0.3);
            }
        }
        PoiKind::Watchfire => {}
    }
}

/// Crossroads hubs: a mosaic around the monument, fire bowls and banners at the rim.
fn dress_hubs(g: &Gen, b: &mut Builder) {
    for (r, reg) in g.regions.iter().enumerate() {
        if reg.landmark.is_none() {
            continue;
        }
        b.dress = g.root.fork(800 + r as u64);
        let rot = b.vd(16);
        let variant = b.biome.paving();
        b.decal(Decor::Paving { at: reg.site, half: Vec2::splat(q(HUB_R * 0.72)), variant });
        b.decal(Decor::FloorInlay { at: reg.site, radius: q(HUB_R - 1.0), rot, variant: 0, god: 0 });
        for i in 0..4u8 {
            let d = rot16_dir(rot.wrapping_add(i * 4 + 2));
            b.brazier(reg.site + d * (HUB_R - 0.6));
            if i % 2 == 0 {
                let god = b.god();
                let height = q(b.rd(4.0, 5.5));
                b.prop(Decor::Banner { at: qv(reg.site + d * (HUB_R + 0.8)), height, rot: rot_of(-d), god }, 0.3);
            }
        }
    }
}

/// The Landing: the gold mosaic and its fire bowls.
fn dress_landing(g: &Gen, b: &mut Builder) {
    b.dress = g.root.fork(900);
    let rot = b.vd(16);
    let at = g.landing;
    b.decal(Decor::FloorInlay { at, radius: q(LANDING_R - 0.9), rot, variant: 0, god: 0 });
    b.decal(Decor::FloorInlay { at, radius: 2.5, rot: rot.wrapping_add(2), variant: 3, god: 0 });
    for k in [2u8, 6, 10, 14] {
        b.brazier(at + rot16_dir(k) * (LANDING_R + 0.3));
    }
}

/// Is `p` inside POI `k`'s plaza + `pad` or one of its approach arcs (±30° around each way in,
/// out to plaza + 10 u)?
fn in_clearing(g: &Gen, lanes: &[Lane], p: Vec2, pad: f32) -> bool {
    g.pois.iter().any(|poi| {
        let (at, plaza) = (poi.site.at, poi.plaza);
        let d = p.distance(at);
        if d < plaza + pad {
            return true;
        }
        if d >= plaza + 10.0 {
            return false;
        }
        let v = (p - at) / d.max(1e-3);
        ways_out(lanes, at, plaza).iter().any(|w| w.dot(v) >= 0.866)
    })
}

/// Region `r`'s vignettes (§3.6.6): a few props backed against something solid, on the dress
/// stream (`2200 + r`). Backs, in order: a composition's inner back corners, the barrier runs,
/// the middle of each framed shore run, beside each story; within each group the ones opening
/// south come first (the props then stand in front of their back as the camera sees them).
fn vignettes(g: &Gen, b: &mut Builder, x: &ComposeDef, r: usize, plan: &mut Plan) {
    b.dress = g.root.fork(2200 + r as u64);
    let t = &g.tiles;
    let land = g.regions[r].area as f32 * t.size * t.size;
    let cap = (land / x.vignette_area.max(500.0)).ceil() as usize;
    let key = |p: Vec2, o: Vec2| (i32::from(o.y > -0.5), (p.x * 8.0).round() as i32, (p.y * 8.0).round() as i32);
    let mut groups: Vec<Vec<((i32, i32, i32), Vec2, Vec2, bool)>> = vec![Vec::new(); 4];
    for &(cr, rect, back) in &plan.comps {
        if cr != r {
            continue;
        }
        let o = -back;
        let side = back.perp();
        let (c, s) = (rect.center(), rect.size() * 0.5);
        let (depth, width) = if back.x != 0.0 { (s.x, s.y) } else { (s.y, s.x) };
        for k in [-1.0f32, 1.0] {
            let p = c + back * (depth - 1.5) + side * (k * (width - 1.5));
            groups[0].push((key(p, o), p, o, true));
        }
    }
    for &(a, bb, mid, d) in &plan.runs {
        if a == r {
            let p = mid - d * 2.1;
            groups[1].push((key(p, -d), p, -d, true));
        } else if bb == r {
            let p = mid + d * 2.1;
            groups[1].push((key(p, d), p, d, true));
        }
    }
    for (sr, run) in &plan.shores {
        if *sr != r || run.is_empty() {
            continue;
        }
        let (i, out) = run[run.len() / 2];
        let p = t.center((i % t.w as usize) as u16, (i / t.w as usize) as u16) - out * 0.5;
        groups[2].push((key(p, -out), p, -out, false));
    }
    for &(sr, at, reach) in &plan.stories {
        if sr != r {
            continue;
        }
        let o = (g.regions[r].site - at).normalize_or(Vec2::NEG_Y);
        let p = at + o * (reach + 1.0);
        groups[3].push((key(p, o), p, o, false));
    }
    let lanes = g.lanes();
    let mut placed = plan.vignettes.len();
    let start = placed;
    for group in &mut groups {
        group.sort_by_key(|c| c.0);
        for &(_, p, o, wall) in group.iter() {
            if placed - start >= cap {
                return;
            }
            let p = qv(p);
            let cell =
                |q: Vec2| (((q.x + g.half.x) / SCREEN.x).floor() as i32, ((q.y + g.half.y) / SCREEN.y).floor() as i32);
            let ok = t.kind_at(p) == TileKind::Ground
                && lanes.iter().all(|l| point_seg(p, l.from, l.to) >= l.width * 0.5 + 1.5)
                && !in_clearing(g, &lanes, p, 2.0)
                && p.distance(g.landing) >= LANDING_R + 6.0
                && plan.vignettes.iter().all(|v| v.0.distance(p) >= x.vignette_spacing)
                && plan.vignettes.iter().filter(|v| cell(v.0) == cell(p)).count() < 2;
            if !ok {
                continue;
            }
            let lit = b.dress.chance(0.45);
            vignette(b, p, o, wall, lit);
            plan.vignettes.push((p, o, lit));
            placed += 1;
        }
    }
}

/// One vignette at `p` opening to `o`: rubble at the back's base, one or two clusters of goods, a
/// broken anvil now and then, a banner against a wall, and often a fire bowl (a lit vignette).
fn vignette(b: &mut Builder, p: Vec2, o: Vec2, wall: bool, lit: bool) {
    const GOODS: [ClutterKind; 4] =
        [ClutterKind::Urns, ClutterKind::Crates, ClutterKind::Ingots, ClutterKind::WeaponRack];
    let side = o.perp();
    let base = p - o * 0.2 + side * b.rd(-1.0, 1.0);
    b.rubble(base, 0.6, 1.0);
    for _ in 0..b.dress.range_u32(1, 3) {
        let at = p + o * b.rd(0.8, 2.4) + side * b.rd(-2.4, 2.4);
        let kind = GOODS[b.dress.range_u32(0, 4) as usize];
        b.clutter(at, 0.7, 1.2, Some(kind));
    }
    if b.dress.chance(0.45) {
        let at = qv(p + o * b.rd(1.6, 3.2) + side * b.rd(-2.0, 2.0));
        let scale = q(b.rd(0.7, 1.0));
        b.prop(Decor::BrokenAnvil { at, scale }, 0.3);
    }
    if wall && b.dress.chance(0.6) {
        let (height, god) = (q(b.rd(3.5, 4.8)), b.god());
        let at = qv(p + side * b.rd(-1.2, 1.2));
        b.prop(Decor::Banner { at, height, rot: rot_of(o), god }, 0.0);
    }
    if b.dress.chance(0.3) {
        let radius = q(b.rd(1.5, 2.3));
        let variant = b.vd(4);
        b.prop(Decor::Overgrowth { at: qv(p + o * 1.4), radius, variant }, 0.0);
    }
    if lit {
        let s = if b.dress.chance(0.5) { 1.0 } else { -1.0 };
        b.brazier(p + side * (s * 2.6) + o * 0.7);
    }
}

/// Light gaps (§3.6.8): every land lattice point (11 × 7 u) needs a warm source (a brazier, great
/// brazier or crucible, a liquid tile or a POI heart) inside the `light_box` centred on it, so
/// every screen holds a warm pool. Points without one, in a seeded order, light an unlit vignette
/// in the box, else set a fire bowl against a frame solid (within 3 u, on the side facing the
/// point); a point with neither stays dark (a lone bowl on open floor is scatter). Among the
/// candidates of a kind, the one that lights the most dark points goes first (then the nearest),
/// so the pools stay few and far between.
fn light_gaps(g: &Gen, b: &mut Builder, x: &ComposeDef, plan: &mut Plan) {
    b.dress = g.root.fork(2300);
    let t = &g.tiles;
    let half_box = Vec2::new(x.light_box.0.clamp(8.0, 34.0), x.light_box.1.clamp(8.0, 21.0)) * 0.5;
    let mut warm: Vec<Vec2> = b
        .decor
        .iter()
        .filter_map(|d| match *d {
            Decor::Brazier { at } | Decor::GreatBrazier { at, .. } | Decor::Crucible { at, .. } => Some(at),
            _ => None,
        })
        .collect();
    warm.extend(g.pois.iter().map(|p| p.site.at));
    for y in 0..t.h {
        for xx in 0..t.w {
            if t.kind[t.index(xx, y)] == TileKind::Liquid {
                warm.push(t.center(xx, y));
            }
        }
    }
    let inside = |q: Vec2, p: Vec2| (q - p).abs().cmple(half_box).all();
    let mut points: Vec<Vec2> = Vec::new();
    let (nx, ny) = ((g.half.x * 2.0 / LATTICE.x) as i32, (g.half.y * 2.0 / LATTICE.y) as i32);
    for j in 0..=ny {
        for i in 0..=nx {
            let p = -g.half + Vec2::new(i as f32 * LATTICE.x, j as f32 * LATTICE.y) + LATTICE * 0.5;
            if t.kind_at(p).is_land() && !warm.iter().any(|w| inside(*w, p)) {
                points.push(p);
            }
        }
    }
    for i in (1..points.len()).rev() {
        let j = b.dress.range_u32(0, i as u32 + 1) as usize;
        points.swap(i, j);
    }
    let mut dark = vec![true; points.len()];
    for k in 0..points.len() {
        if !dark[k] {
            continue;
        }
        let p = points[k];
        // Integer sort key: most dark points lit first, then nearest to the point.
        let rank = |q: Vec2| {
            let gain = points.iter().zip(&dark).filter(|(u, d)| **d && inside(q, **u)).count() as i64;
            (-gain, (q.distance(p) * 8.0).round() as i64)
        };
        let mut placed: Option<Vec2> = None;
        // 1. An unlit vignette in the box gets its fire bowl.
        let mut cands: Vec<((i64, i64), usize, Vec2)> = plan
            .vignettes
            .iter()
            .enumerate()
            .filter(|(_, v)| !v.2 && inside(v.0, p))
            .map(|(i, v)| {
                let at = qv(v.0 + v.1.perp() * 2.6 + v.1 * 0.7);
                (rank(at), i, at)
            })
            .collect();
        cands.sort_by_key(|c| (c.0, c.1));
        for (_, i, at) in cands {
            plan.vignettes[i].2 = true;
            if b.prop(Decor::Brazier { at }, 0.5) {
                placed = Some(at);
                break;
            }
        }
        // 2. A fire bowl against a frame solid in the box (within 3 u of it), on the side facing
        //    the point.
        if placed.is_none() {
            let mut cands: Vec<((i64, i64), usize, Vec2)> = plan
                .solids
                .iter()
                .map(|&i| (i, extent(&b.obstacles[i])))
                .filter(|(_, (c, _))| inside(*c, p))
                .map(|(i, (c, e))| {
                    let d = (p - c).normalize_or(Vec2::NEG_Y);
                    let at = qv(c + d * (e.min_element() + 1.2));
                    (rank(at), i, at)
                })
                .filter(|(_, i, at)| crate::procgen::sd(&b.obstacles[*i], *at) <= 3.0)
                .collect();
            cands.sort_by_key(|c| (c.0, c.1));
            for (_, _, at) in cands.into_iter().take(8) {
                if b.prop(Decor::Brazier { at }, 0.5) {
                    placed = Some(at);
                    break;
                }
            }
        }
        // (No third rung: a lone fire bowl on a road shoulder or open floor is random scatter;
        // a point with no solid to set one against stays in the dusk.)
        if let Some(at) = placed {
            for (u, d) in points.iter().zip(dark.iter_mut()) {
                if inside(at, *u) {
                    *d = false;
                }
            }
        }
    }
}

/// Cobble islands along the road shoulders (§3.6.7): every 40–60 u on alternating sides, 2–4 u
/// off the edge, on `root.fork(2400 + k)`; islands keep 14 u apart.
fn road_paving(g: &Gen, b: &mut Builder) {
    for (k, l) in g.lanes().iter().enumerate() {
        b.dress = g.root.fork(2400 + k as u64);
        let len = l.from.distance(l.to);
        if len < 20.0 {
            continue;
        }
        let dir = (l.to - l.from) / len;
        let n = Vec2::new(-dir.y, dir.x);
        let mut s = b.rd(10.0, 30.0);
        let mut side = if b.dress.chance(0.5) { 1.0 } else { -1.0 };
        while s < len - 8.0 {
            let at = qv(l.from + dir * s + n * (side * (l.width * 0.5 + b.rd(2.0, 4.0))));
            let half = qv(Vec2::new(b.rd(2.0, 3.5), b.rd(2.0, 3.5)));
            if g.tiles.kind_at(at) == TileKind::Ground && b.island_ok(at, ISLAND_APART) {
                b.decal(Decor::Paving { at, half, variant: 3 });
            }
            side = -side;
            s += b.rd(40.0, 60.0);
        }
    }
}

/// Region `r`'s floor-story marks (§3.6.7), on the dress stream `2500 + r`: big painted shapes
/// (burn scars, slag spills, ash drifts, collapsed floors, rust drags, soot fans) on a jittered
/// lattice of `compose.mark_spacing` over its open ground, off the roads, clearings, hubs, the
/// Landing and the compositions' floors. The theme's `marks` pool picks each kind; a soot fan
/// only stands against a solid (it sprays away from it), a rust drag leads toward the nearest
/// way, and the ash drifts all lie across the map's one wind.
fn floor_marks(g: &Gen, b: &mut Builder, x: &ComposeDef, r: usize, plan: &Plan) {
    let Some(theme) = g.x.themes.get(g.regions[r].theme as usize) else { return };
    let step = x.mark_spacing;
    if theme.marks.is_empty() || step < 6.0 || g.regions[r].area == 0 {
        return;
    }
    let wind = g.root.fork(2599).range_u32(0, 16) as u8;
    b.dress = g.root.fork(2500 + r as u64);
    let t = &g.tiles;
    let (lo, hi) = g.regions[r].bounds(&t);
    let (size_lo, size_hi) = (x.mark_size.0.min(x.mark_size.1).max(1.0), x.mark_size.1.max(x.mark_size.0).max(1.0));
    let lanes = g.lanes();
    let weights: Vec<f32> = theme.marks.iter().map(|(_, w)| *w).collect();
    let comps: Vec<Rect> = plan.comps.iter().filter(|c| c.0 == r).map(|c| c.1).collect();
    let (nx, ny) = (((hi.x - lo.x) / step).ceil() as i32, ((hi.y - lo.y) / step).ceil() as i32);
    let mut placed: Vec<Vec2> = b
        .decor
        .iter()
        .filter_map(|d| match *d {
            Decor::FloorMark { at, .. } => Some(at),
            _ => None,
        })
        .collect();
    for j in 0..ny {
        for i in 0..nx {
            let jitter = Vec2::new(b.rd(-0.3, 0.3), b.rd(-0.3, 0.3));
            let at = qv(lo + (Vec2::new(i as f32, j as f32) + Vec2::splat(0.5) + jitter) * step);
            let Some(p) = b.dress.weighted_index(&weights) else { return };
            let mut kind = theme.marks[p].0;
            let along = b.rd(size_lo, size_hi);
            let spin = b.vd(16);
            let ti = tiles::tile_at(t, at);
            if t.kind[ti] != TileKind::Ground || t.region[ti] as usize != r {
                continue;
            }
            let reach = along * 0.8;
            let clear = lanes.iter().all(|l| point_seg(at, l.from, l.to) >= l.width * 0.5 + reach * 0.6 + 0.5)
                && g.pois.iter().all(|poi| at.distance(poi.site.at) >= poi.plaza + reach + 1.0)
                && at.distance(g.landing) >= LANDING_R + reach + 2.0
                && g.regions.iter().filter(|rg| rg.landmark.is_some()).all(|rg| at.distance(rg.site) >= HUB_R + reach)
                && comps.iter().all(|c| !c.contains(at, reach * 0.5))
                && placed.iter().all(|m| m.distance(at) >= step * 0.7);
            if !clear {
                continue;
            }
            let mut at = at;
            let rot = match kind {
                FloorMarkKind::Soot => {
                    // Against the nearest solid within 8 u, spraying away from it.
                    let near = b
                        .obstacles
                        .iter()
                        .map(|o| {
                            let (c, e) = extent(o);
                            (c, e.max_element(), c.distance(at))
                        })
                        .filter(|(_, e, d)| *d < 8.0 + e)
                        .min_by(|a, z| a.2.total_cmp(&z.2));
                    match near {
                        Some((c, e, _)) => {
                            let d = (at - c).normalize_or(Vec2::NEG_Y);
                            at = qv(c + d * (e + along * 0.9));
                            rot_of(d)
                        }
                        None => {
                            kind = FloorMarkKind::Burn;
                            spin
                        }
                    }
                }
                FloorMarkKind::Rust => {
                    // The ruts lead toward the nearest way.
                    let q = lanes
                        .iter()
                        .map(|l| {
                            let ab = l.to - l.from;
                            let s = ((at - l.from).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
                            l.from + ab * s
                        })
                        .min_by(|a, z| a.distance_squared(at).total_cmp(&z.distance_squared(at)));
                    q.map_or(spin, |q| rot_of(q - at))
                }
                FloorMarkKind::Ash => wind.wrapping_add(spin % 3).wrapping_sub(1) % 16,
                _ => spin,
            };
            let ratio = match kind {
                FloorMarkKind::Burn => b.rd(0.85, 1.0),
                FloorMarkKind::Collapse => b.rd(0.75, 1.0),
                FloorMarkKind::Slag => b.rd(0.6, 0.9),
                FloorMarkKind::Soot => b.rd(0.55, 0.8),
                FloorMarkKind::Ash => b.rd(0.45, 0.7),
                FloorMarkKind::Rust => b.rd(0.4, 0.6),
            };
            let along = if kind == FloorMarkKind::Burn { along.min(size_hi * 0.75) } else { along };
            let half = qv(Vec2::new(along, along * ratio).max(Vec2::splat(1.0)));
            if t.kind_at(at) != TileKind::Ground {
                continue;
            }
            placed.push(at);
            b.decal(Decor::FloorMark { at, half, rot, kind });
        }
    }
}
