//! Pipeline steps 9–10 (§3.2, §3.4): the room grammar at map scale. One [`Builder`] runs over the
//! whole map in map mode (the tile mask keeps compositions on open ground; roads, spurs and bridge
//! decks are its lanes; clearings, hubs and the Landing its keep-outs). In order:
//!
//! 1. **POI clearings**: the gate's sealed-gate monument, the Warlord's crucible, arches where roads
//!    enter the major clearings.
//! 2. **Barriers**: forge walls and boulder ridges along region borders, arches where roads breach
//!    them (and over roads at other region borders).
//! 3. **Regions**, each on its own streams (`root.fork(100 + i)` lays, `root.fork(200 + i)` dresses):
//!    the hub's grand monument, up to four slots cut from open ground and filled from the theme's
//!    composition pool (never repeating, a `fields` share left open), a density top-up at the slot
//!    skirts up to the theme's `cover`, and floor dressing.
//! 4. **Dressing** (visual only): braziers along the roads, bridge decks, clearing hearts, hubs and
//!    the Landing.

use super::barriers::road_dir;
use super::tiles::{self, land_box};
use super::{Gen, HUB_R, LANDING_R};
use crate::procgen::{
    Biome, Builder, CELL, Frame, PAD, Rect, TileMask, arch, bounds, extent, field, monument, point_seg, q, qv, rot_of,
    ruin, stamp,
};
use crate::schema::*;
use gf_core::movement::Obstacle;
use gf_core::poi::PoiKind;
use glam::Vec2;

/// Slots cut per region.
const SLOTS: usize = 5;
/// Largest slot side (tiles): bigger open ground is split over several slots.
const SLOT_CAP: usize = 10;
/// Smallest slot (tiles, either orientation): 16 × 12 u once shrunk by `PAD`.
const SLOT_MIN: (usize, usize) = (5, 4);
/// Region border band (tile steps from its edge) where the density top-up crowds its ruins.
const BAND: u16 = 2;
/// Reach of a region's pieces beyond its land's bounding box (lanes and keep-outs farther away
/// cannot refuse a piece, so each region pass only looks at the nearby ones).
const NEAR: f32 = 24.0;

/// The composed map: the builder (obstacles, decor, cover grid) and where each composition landed.
pub(crate) struct Built {
    pub(crate) builder: Builder,
    pub(crate) districts: Vec<District>,
}

pub(crate) fn build(g: &mut Gen) -> Built {
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
        ..Builder::new(g.half, g.biome, 1.0, g.root.fork(98), g.root.fork(99))
    };
    let mut districts = Vec::new();

    for k in 0..g.pois.len() {
        clearing(g, &mut b, k);
    }
    for n in 0..g.walls.len() {
        wall(g, &mut b, n);
    }
    for k in 0..g.roads.len() {
        pass_arch(g, &mut b, k);
    }
    let steps = tiles::edge_steps(&g.tiles);
    for r in 0..g.regions.len() {
        region(g, &mut b, r, &steps, &mut districts);
    }
    dress_roads(g, &mut b);
    for k in 0..g.pois.len() {
        dress_clearing(g, &mut b, k);
    }
    dress_hubs(g, &mut b);
    dress_landing(g, &mut b);
    districts.extend(g.pois.iter().map(|p| District {
        kind: DistrictKind::Plaza,
        min: qv(p.site.at - Vec2::splat(p.plaza)),
        max: qv(p.site.at + Vec2::splat(p.plaza)),
    }));
    Built { builder: b, districts }
}

// ───────────────────────────── forced pieces ─────────────────────────────

/// Run `f` with the builder's keep-outs and tile mask lifted (pieces standing inside a clearing or
/// on a road's shoulder); lanes, the rim and the spacing rules still apply.
fn unmasked<R>(b: &mut Builder, f: impl FnOnce(&mut Builder) -> R) -> R {
    let keep = std::mem::take(&mut b.keep);
    let mask = b.mask.take();
    let out = f(b);
    b.keep = keep;
    b.mask = mask;
    out
}

/// May `o` stand here ignoring the mask: on land, and out of every keep-out except the one at
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

/// An arch spanning the road through `at` running along `dir`, its piers just off the road.
fn road_arch(g: &Gen, b: &mut Builder, at: Vec2, dir: Vec2, width: f32, own: Option<Vec2>) -> bool {
    let pier = q(b.rl(0.7, 0.9));
    let n = Vec2::new(-dir.y, dir.x);
    let off = width * 0.5 + pier * 1.42 + 0.15;
    let (from, to) = (qv(at + n * off), qv(at - n * off));
    let half = Vec2::splat(pier);
    let pieces = [Obstacle::Box { center: from, half }, Obstacle::Box { center: to, half }];
    if !pieces.iter().all(|o| open_ground(g, b, o, own)) {
        return false;
    }
    unmasked(b, |b| arch(b, from, to, pier))
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

// ───────────────────────────── clearings ─────────────────────────────

/// Solid set pieces of POI `k`'s clearing (§3.2 step 10).
fn clearing(g: &Gen, b: &mut Builder, k: usize) {
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
        _ => {}
    }
    // Arches where the roads (and spurs) enter the clearing.
    {
        let width = q(g.x.roads.width);
        for d in &ways {
            for extra in [1.5f32, 3.0] {
                if road_arch(g, b, at + *d * (plaza + extra), *d, width, Some(at)) {
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

/// Wall or ridge `n` (`g.walls[n]`) along its region pair's border, on region `a`'s side.
fn wall(g: &Gen, b: &mut Builder, n: usize) {
    let adj = &g.adj[g.walls[n]];
    let kind = adj.barrier.unwrap_or(BarrierKind::Wall);
    b.lay = g.root.fork(500 + n as u64);
    b.dress = g.root.fork(550 + n as u64);
    let t = &g.tiles;
    let w = t.w as usize;
    let grp = b.group();
    let style = wall_style(g.biome);
    for i in 0..t.kind.len() {
        if !t.kind[i].is_land() || t.region[i] as usize != adj.a {
            continue;
        }
        let (x, y) = (i % w, i / w);
        let c = t.center(x as u16, y as u16);
        let faces: Vec<Vec2> = [(i.wrapping_sub(1), -Vec2::X, x > 0), (i + 1, Vec2::X, x + 1 < w)]
            .into_iter()
            .chain([(i.wrapping_sub(w), -Vec2::Y, y > 0), (i + w, Vec2::Y, y + 1 < t.h as usize)])
            .filter(|&(j, _, ok)| ok && t.kind[j].is_land() && t.region[j] as usize == adj.b)
            .map(|(_, d, _)| d)
            .collect();
        if faces.is_empty() {
            continue;
        }
        match kind {
            BarrierKind::Ridge => {
                if (x + y) % 2 == 0 {
                    let d = faces.iter().copied().sum::<Vec2>().normalize_or(faces[0]);
                    let (r, variant) = (b.rl(1.3, 2.0), b.vd(4));
                    b.circle(grp, c + d * 1.2, r, |at, radius| Decor::Boulder { at, radius, variant });
                }
            }
            _ => {
                for d in faces {
                    let half = if d.x != 0.0 { Vec2::new(0.6, 2.1) } else { Vec2::new(2.1, 0.6) };
                    let (height, variant) = (q(b.rd(3.0, 5.0)), b.vd(4));
                    let placed =
                        b.block(grp, c + d * 1.4, half, |at, half| Decor::Wall { at, half, height, style, variant });
                    if placed && b.dress.chance(0.2) {
                        let off = -d * b.rd(2.2, 3.0) + Vec2::new(d.y, d.x) * b.rd(-1.5, 1.5);
                        b.rubble(c + d * 1.4 + off, 0.6, 1.1);
                    }
                }
            }
        }
    }
}

/// An arch over road `k` where it crosses its regions' border: always through a wall or ridge,
/// often at an open border; never over a bridge (the deck is the landmark there).
fn pass_arch(g: &Gen, b: &mut Builder, k: usize) {
    let road = &g.roads[k];
    b.lay = g.root.fork(600 + k as u64);
    b.dress = g.root.fork(650 + k as u64);
    let barrier = g.adj.iter().find(|a| (a.a, a.b) == (road.a.min(road.b), road.a.max(road.b))).and_then(|a| a.barrier);
    let chance = match barrier {
        Some(BarrierKind::Wall | BarrierKind::Ridge) => 1.0,
        Some(_) => 0.0,
        None => 0.6,
    };
    if !b.lay.chance(chance) {
        return;
    }
    let dir = road_dir(&road.lanes, road.pass);
    let width = q(g.x.roads.width);
    for s in [0.0f32, -2.5, 2.5, -5.0, 5.0] {
        if road_arch(g, b, road.pass + dir * s, dir, width, None) {
            break;
        }
    }
}

// ───────────────────────────── regions ─────────────────────────────

/// A slot: open ground for one composition, and the direction its back turns to.
struct Slot {
    rect: Rect,
    back: Vec2,
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

/// Cut up to [`SLOTS`] slots from region `r`'s open ground, largest first. Each slot's back turns
/// away from its nearest road, so its composition opens toward the fight.
fn slots(g: &Gen, r: usize, lanes: &[Lane]) -> Vec<Slot> {
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
    let mut out = Vec::new();
    for _ in 0..SLOTS {
        let Some((sx, sy, sw, sh)) = largest(&free, w, h) else { break };
        // The slot and a one-tile margin are spent.
        for y in sy.saturating_sub(1)..(sy + sh + 1).min(h) {
            for x in sx.saturating_sub(1)..(sx + sw + 1).min(w) {
                free[y * w + x] = false;
            }
        }
        let hs = Vec2::splat(t.size * 0.5);
        let lo = t.center((x0 + sx) as u16, (y0 + sy) as u16) - hs + Vec2::splat(PAD);
        let hi = t.center((x0 + sx + sw - 1) as u16, (y0 + sy + sh - 1) as u16) + hs - Vec2::splat(PAD);
        let rect = Rect::new(qv(lo), qv(hi));
        let c = rect.center();
        let near = lanes
            .iter()
            .map(|l| {
                let ab = l.to - l.from;
                let s = ((c - l.from).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
                l.from + ab * s
            })
            .min_by(|a, b| a.distance_squared(c).total_cmp(&b.distance_squared(c)))
            .unwrap_or(c - Vec2::Y);
        let v = c - near;
        let back = if v.x.abs() > v.y.abs() {
            Vec2::new(v.x.signum(), 0.0)
        } else if v.y != 0.0 {
            Vec2::new(0.0, v.y.signum())
        } else {
            Vec2::Y
        };
        out.push(Slot { rect, back });
    }
    out
}

/// Compose region `r` (§3.2 step 9).
fn region(g: &mut Gen, b: &mut Builder, r: usize, steps: &[u16], districts: &mut Vec<District>) {
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
    let covered0 = b.covered;

    // d) The hub's grand monument, facing the Landing (the skyline greets arrivals).
    if let Some(mark) = g.regions[r].landmark {
        let site = g.regions[r].site;
        let rot = rot_of(g.landing - site);
        let (o, d) = monument(b, mark, site, rot, true);
        if !force(g, b, &[o], d, Some(site)) {
            g.trace(|| format!("region {r}: no room for its {mark:?} at {site}"));
            g.regions[r].landmark = None;
        }
    }

    // b–c) Slots filled from the theme's pool, never repeating; a `fields` share stays open.
    let slots = slots(g, r, &all_lanes);
    let pool: Vec<(DistrictKind, f32)> = theme.as_ref().map_or_else(Vec::new, |t| t.districts.clone());
    let fields = theme.as_ref().map_or(0.5, |t| t.fields.clamp(0.0, 1.0)) * slots.len() as f32;
    let n_fields = fields.floor() as usize + usize::from(b.lay.chance(fields.fract()));
    let mut is_field = vec![false; slots.len()];
    for _ in 0..n_fields.min(slots.len()) {
        let open: Vec<usize> = (0..slots.len()).filter(|&i| !is_field[i]).collect();
        is_field[open[b.lay.range_u32(0, open.len() as u32) as usize]] = true;
    }
    let mut used: Vec<DistrictKind> = Vec::new();
    let mut comps: Vec<Rect> = Vec::new();
    for (i, slot) in slots.iter().enumerate() {
        let flip = b.lay.chance(0.5);
        let f = Frame::of(slot.rect, slot.back, Vec2::ZERO, flip);
        let mut kind = DistrictKind::Field;
        let mut footprint = slot.rect;
        if !is_field[i] {
            let mut failed: Option<DistrictKind> = None;
            for _attempt in 0..2 {
                let w: Vec<f32> = pool
                    .iter()
                    .map(|(k, w)| if used.contains(k) || failed == Some(*k) { 0.0 } else { w.max(0.0) })
                    .collect();
                let Some(p) = b.lay.weighted_index(&w) else { break };
                if let Some(rect) = stamp(b, pool[p].0, f) {
                    kind = pool[p].0;
                    used.push(kind);
                    comps.push(rect);
                    footprint = rect;
                    break;
                }
                failed = Some(pool[p].0);
            }
        }
        if kind == DistrictKind::Field {
            field(b, f);
        }
        districts.push(District { kind, min: qv(footprint.min), max: qv(footprint.max) });
    }

    // e) Density top-up: compact ruins at the composition skirts and along the region's border band
    //    (the map-scale rim: it frames the region and leaves its middle open for the fight).
    let area = g.regions[r].area as f32 * g.tiles.size * g.tiles.size;
    let target = theme.as_ref().map_or(0.03, |t| t.cover.clamp(0.0, 0.08)) * area;
    let (x0, y0, x1, y1) = (g.regions[r].lo.0, g.regions[r].lo.1, g.regions[r].hi.0, g.regions[r].hi.1);
    let band: Vec<usize> = (y0..=y1)
        .flat_map(|y| (x0..=x1).map(move |x| (x, y)))
        .map(|(x, y)| g.tiles.index(x, y))
        .filter(|&i| g.tiles.kind[i] == TileKind::Ground && g.tiles.region[i] as usize == r && steps[i] <= BAND)
        .collect();
    let mut tries = 0;
    while ((b.covered - covered0) as f32) * CELL * CELL < target && tries < 400 {
        tries += 1;
        let at = if (b.lay.chance(0.5) || band.is_empty()) && !comps.is_empty() {
            let c = comps[b.lay.range_u32(0, comps.len() as u32) as usize];
            let m = b.rl(1.5, 4.5);
            match b.lay.range_u32(0, 4) {
                0 => Vec2::new(b.rl(c.min.x, c.max.x), c.max.y + m),
                1 => Vec2::new(b.rl(c.min.x, c.max.x), c.min.y - m),
                2 => Vec2::new(c.min.x - m, b.rl(c.min.y, c.max.y)),
                _ => Vec2::new(c.max.x + m, b.rl(c.min.y, c.max.y)),
            }
        } else if !band.is_empty() {
            let i = band[b.lay.range_u32(0, band.len() as u32) as usize];
            let w = g.tiles.w as usize;
            g.tiles.center((i % w) as u16, (i / w) as u16) + Vec2::new(b.rl(-1.5, 1.5), b.rl(-1.5, 1.5))
        } else {
            break;
        };
        let i = tiles::tile_at(&g.tiles, at);
        if g.tiles.region[i] as usize != r || comps.iter().any(|c| c.contains(at, 1.0)) {
            continue;
        }
        let sat = b.lay.range_u32(1, 3);
        ruin(b, at, sat);
    }

    // f) Floor dressing: fissures, ground cover, rubble and bones on open ground.
    let open = |b: &mut Builder| {
        let x = b.dress.range_u32(x0 as u32, x1 as u32 + 1) as u16;
        let y = b.dress.range_u32(y0 as u32, y1 as u32 + 1) as u16;
        let i = g.tiles.index(x, y);
        (g.tiles.kind[i] == TileKind::Ground && g.tiles.region[i] as usize == r).then(|| g.tiles.center(x, y))
    };
    let per = (area / 1500.0).max(2.0) as u32;
    for _ in 0..per {
        if let Some(at) = open(b) {
            let d = rot16_dir(b.vd(16));
            let segs = b.dress.range_u32(2, 5);
            let width = if g.biome == Biome::Cinder { b.rd(0.3, 0.55) } else { b.rd(0.2, 0.4) };
            b.fissure(at, d, segs, width);
        }
        if let Some(at) = open(b) {
            b.cover_patch(at, 1.6, 3.4);
        }
        if let Some(at) = open(b) {
            if b.dress.chance(0.6) {
                b.rubble(at, 0.8, 1.5);
            } else {
                b.clutter(at, 0.6, 1.0, Some(ClutterKind::Bones));
            }
        }
    }

    b.lanes = all_lanes;
    b.keep = all_keep;
}

// ───────────────────────────── dressing ─────────────────────────────

/// Braziers along every road, 16–22 u apart on alternating sides; bridge decks with fire at their
/// heads.
fn dress_roads(g: &Gen, b: &mut Builder) {
    let lanes = g.lanes();
    for (k, l) in lanes.iter().enumerate() {
        b.dress = g.root.fork(700 + k as u64);
        let len = l.from.distance(l.to);
        if len < 6.0 {
            continue;
        }
        let dir = (l.to - l.from) / len;
        let n = Vec2::new(-dir.y, dir.x);
        let mut s = b.rd(4.0, 12.0);
        let mut side = if b.dress.chance(0.5) { 1.0 } else { -1.0 };
        while s < len - 3.0 {
            b.brazier(l.from + dir * s + n * (side * (l.width * 0.5 + 1.3)));
            side = -side;
            s += b.rd(16.0, 22.0);
        }
    }
    for (k, deck) in g.bridges.iter().enumerate() {
        b.dress = g.root.fork(760 + k as u64);
        b.decal(Decor::Bridge { from: deck.from, to: deck.to, width: deck.width });
        let dir = (deck.to - deck.from).normalize_or(Vec2::X);
        let n = Vec2::new(-dir.y, dir.x) * (deck.width * 0.5 + 0.9);
        for (end, s) in [(deck.from, -1.0f32), (deck.to, 1.0)] {
            b.brazier(end + dir * (s * 1.2) + n);
            b.brazier(end + dir * (s * 1.2) - n);
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
            b.cover_patch(at + rot16_dir(rot.wrapping_add(5)) * (radius + 1.5), 1.2, 2.0);
            b.cover_patch(at + rot16_dir(rot.wrapping_add(12)) * (radius + 1.5), 1.2, 2.0);
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
