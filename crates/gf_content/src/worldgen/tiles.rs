//! Tile-grid helpers shared by the worldgen stages (§3.1): integer value noise, disc and lane
//! rasters, flood fills, the road/plaza stamp and the pit merge. Everything here is integer or
//! IEEE-exact (`+ − × ÷ √`, floor and compares).

use super::{Gen, HUB_R, LANDING_R};
use crate::procgen::point_seg;
use crate::schema::{Lane, TileGrid, TileKind};
use gf_core::movement::Obstacle;
use glam::Vec2;
use std::collections::VecDeque;

/// One lattice point of the value noise: a 64-bit mix of `(seed, x, y)`, 0..=255.
fn lattice(seed: u64, x: i32, y: i32) -> i32 {
    let mut h = seed
        ^ (x as i64 as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15)
        ^ (y as i64 as u64).wrapping_mul(0xC2B2_AE3D_27D4_EB4F);
    h = (h ^ (h >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    h = (h ^ (h >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    ((h ^ (h >> 31)) & 0xFF) as i32
}

/// Smoothstep of a 1/256 fraction (0..=256), in 1/256.
fn fade(t: i32) -> i32 {
    (t * t * (768 - 2 * t)) >> 16
}

/// Value noise at integer tile coordinates with `period` tiles per lattice cell, bilinear (with a
/// smoothstep fade) in 1/256 fixed point: 0..=255.
pub(crate) fn noise(seed: u64, x: i32, y: i32, period: i32) -> i32 {
    let p = period.max(1);
    let (gx, gy) = (x.div_euclid(p), y.div_euclid(p));
    let fx = fade(x.rem_euclid(p) * 256 / p);
    let fy = fade(y.rem_euclid(p) * 256 / p);
    let (a, b) = (lattice(seed, gx, gy), lattice(seed, gx + 1, gy));
    let (c, d) = (lattice(seed, gx, gy + 1), lattice(seed, gx + 1, gy + 1));
    let low = a * (256 - fx) + b * fx;
    let high = c * (256 - fx) + d * fx;
    (low * (256 - fy) + high * fy) >> 16
}

/// Inclusive tile range covering the world box `lo..=hi` (clamped to the grid), or `None` when it
/// misses the grid.
pub(crate) fn span(t: &TileGrid, lo: Vec2, hi: Vec2) -> Option<(u16, u16, u16, u16)> {
    let a = ((lo - t.origin) / t.size).floor();
    let b = ((hi - t.origin) / t.size).floor();
    if b.x < 0.0 || b.y < 0.0 || a.x >= t.w as f32 || a.y >= t.h as f32 {
        return None;
    }
    let cx = |v: f32| v.clamp(0.0, (t.w - 1) as f32) as u16;
    let cy = |v: f32| v.clamp(0.0, (t.h - 1) as f32) as u16;
    Some((cx(a.x), cy(a.y), cx(b.x), cy(b.y)))
}

/// Tiles whose centre lies within `r` of `c`, in index order.
pub(crate) fn disc(t: &TileGrid, c: Vec2, r: f32) -> Vec<usize> {
    let mut out = Vec::new();
    if let Some((x0, y0, x1, y1)) = span(t, c - Vec2::splat(r), c + Vec2::splat(r)) {
        for y in y0..=y1 {
            for x in x0..=x1 {
                if t.center(x, y).distance_squared(c) <= r * r {
                    out.push(t.index(x, y));
                }
            }
        }
    }
    out
}

/// Tiles whose centre lies within `r` of the segment `a`–`b`, in index order.
pub(crate) fn along(t: &TileGrid, a: Vec2, b: Vec2, r: f32) -> Vec<usize> {
    let mut out = Vec::new();
    if let Some((x0, y0, x1, y1)) = span(t, a.min(b) - Vec2::splat(r), a.max(b) + Vec2::splat(r)) {
        for y in y0..=y1 {
            for x in x0..=x1 {
                if point_seg(t.center(x, y), a, b) <= r {
                    out.push(t.index(x, y));
                }
            }
        }
    }
    out
}

/// Is every tile under the box `c ± e` land (off the grid is not)?
pub(crate) fn land_box(t: &TileGrid, c: Vec2, e: Vec2) -> bool {
    let a = ((c - e - t.origin) / t.size).floor();
    let b = ((c + e - t.origin) / t.size).floor();
    if a.x < 0.0 || a.y < 0.0 || b.x >= t.w as f32 || b.y >= t.h as f32 {
        return false;
    }
    (a.y as u16..=b.y as u16).all(|y| (a.x as u16..=b.x as u16).all(|x| t.kind[t.index(x, y)].is_land()))
}

/// The 4-neighbours of tile `i`, in a fixed order (west, east, south, north).
pub(crate) fn around(t: &TileGrid, i: usize) -> impl Iterator<Item = usize> {
    let (w, h) = (t.w as usize, t.h as usize);
    let (x, y) = (i % w, i / w);
    [(x > 0).then(|| i - 1), (x + 1 < w).then(|| i + 1), (y > 0).then(|| i - w), (y + 1 < h).then(|| i + w)]
        .into_iter()
        .flatten()
}

/// Is tile `i` on the grid's outer ring?
pub(crate) fn on_rim(t: &TileGrid, i: usize) -> bool {
    let (w, h) = (t.w as usize, t.h as usize);
    let (x, y) = (i % w, i / w);
    x == 0 || y == 0 || x + 1 == w || y + 1 == h
}

/// Breadth-first flood from `start` over tiles `pass` accepts (4-neighbour).
pub(crate) fn flood(t: &TileGrid, start: usize, pass: impl Fn(usize) -> bool) -> Vec<bool> {
    let mut seen = vec![false; t.kind.len()];
    if start >= seen.len() || !pass(start) {
        return seen;
    }
    let mut queue = VecDeque::from([start]);
    seen[start] = true;
    while let Some(i) = queue.pop_front() {
        for j in around(t, i) {
            if !seen[j] && pass(j) {
                seen[j] = true;
                queue.push_back(j);
            }
        }
    }
    seen
}

/// Tile steps (4-neighbour) from every tile to the nearest tile `from` accepts (`u16::MAX` where
/// none is reachable), treating the grid's outside as matching when `rim` is set.
pub(crate) fn steps_to(t: &TileGrid, from: impl Fn(usize) -> bool, rim: bool) -> Vec<u16> {
    let mut dist = vec![u16::MAX; t.kind.len()];
    let mut queue = VecDeque::new();
    for (i, d) in dist.iter_mut().enumerate() {
        if from(i) {
            *d = 0;
            queue.push_back(i);
        } else if rim && on_rim(t, i) {
            *d = 1;
            queue.push_back(i);
        }
    }
    while let Some(i) = queue.pop_front() {
        for j in around(t, i) {
            if dist[j] == u16::MAX {
                dist[j] = dist[i] + 1;
                queue.push_back(j);
            }
        }
    }
    dist
}

/// Steps (4-neighbour, inside its own region) from every land tile to its region's edge: 0 on a
/// tile touching another region, a pit or the grid's rim (`u16::MAX` off land).
pub(crate) fn edge_steps(t: &TileGrid) -> Vec<u16> {
    let n = t.kind.len();
    let edge = |i: usize| on_rim(t, i) || around(t, i).any(|j| !t.kind[j].is_land() || t.region[j] != t.region[i]);
    let mut dist = vec![u16::MAX; n];
    let mut queue = VecDeque::new();
    for (i, d) in dist.iter_mut().enumerate() {
        if t.kind[i].is_land() && edge(i) {
            *d = 0;
            queue.push_back(i);
        }
    }
    while let Some(i) = queue.pop_front() {
        for j in around(t, i) {
            if dist[j] == u16::MAX && t.kind[j].is_land() && t.region[j] == t.region[i] {
                dist[j] = dist[i] + 1;
                queue.push_back(j);
            }
        }
    }
    dist
}

/// Index of the tile under `p` (clamped onto the grid).
pub(crate) fn tile_at(t: &TileGrid, p: Vec2) -> usize {
    let c = ((p - t.origin) / t.size).floor();
    let x = c.x.clamp(0.0, (t.w - 1) as f32) as u16;
    let y = c.y.clamp(0.0, (t.h - 1) as f32) as u16;
    t.index(x, y)
}

/// Stamp the ways onto the land mask once the barriers stand: roads and spurs as `Road` tiles
/// (`Bridge` where one crosses the coast), then the Landing, POI clearings and crossroads hubs as
/// `Plaza` tiles.
pub(crate) fn stamp_ways(g: &mut Gen) {
    let lanes: Vec<Lane> = g.lanes();
    for l in &lanes {
        for i in along(&g.tiles, l.from, l.to, l.width * 0.5 + 0.5) {
            g.tiles.kind[i] = match g.tiles.kind[i] {
                TileKind::Ground => TileKind::Road,
                TileKind::Void | TileKind::Liquid => TileKind::Bridge,
                k => k,
            };
        }
    }
    let mut plazas: Vec<(Vec2, f32)> = vec![(g.landing, LANDING_R)];
    plazas.extend(g.pois.iter().map(|p| (p.site.at, p.plaza)));
    plazas.extend(g.regions.iter().filter(|r| r.landmark.is_some()).map(|r| (r.site, HUB_R)));
    for (c, r) in plazas {
        for i in disc(&g.tiles, c, r) {
            if g.tiles.kind[i].is_land() {
                g.tiles.kind[i] = TileKind::Plaza;
            }
        }
    }
}

/// Merge the pit tiles (`Void` and `Liquid`) into boxes: horizontal runs first, then identical runs
/// on consecutive rows (§3.2 step 12). Corners land on the 4 u grid, so every box is exact.
pub(crate) fn merge_pits(t: &TileGrid) -> Vec<Obstacle> {
    let (w, h) = (t.w as usize, t.h as usize);
    // Open boxes: (x0, x1, y0), x1 exclusive, sorted by x0.
    let mut open: Vec<(usize, usize, usize)> = Vec::new();
    let mut done: Vec<(usize, usize, usize, usize)> = Vec::new();
    for y in 0..=h {
        let mut runs: Vec<(usize, usize)> = Vec::new();
        if y < h {
            let mut x = 0;
            while x < w {
                if t.kind[y * w + x].is_pit() {
                    let x0 = x;
                    while x < w && t.kind[y * w + x].is_pit() {
                        x += 1;
                    }
                    runs.push((x0, x));
                } else {
                    x += 1;
                }
            }
        }
        let mut next = Vec::with_capacity(runs.len());
        for &(x0, x1) in &runs {
            match open.iter().find(|o| o.0 == x0 && o.1 == x1) {
                Some(o) => next.push(*o),
                None => next.push((x0, x1, y)),
            }
        }
        for o in &open {
            if !next.contains(o) {
                done.push((o.0, o.1, o.2, y));
            }
        }
        open = next;
    }
    done.sort_by_key(|&(x0, _, y0, _)| (y0, x0));
    done.into_iter()
        .map(|(x0, x1, y0, y1)| {
            let lo = t.origin + Vec2::new(x0 as f32, y0 as f32) * t.size;
            let hi = t.origin + Vec2::new(x1 as f32, y1 as f32) * t.size;
            Obstacle::Box { center: (lo + hi) * 0.5, half: (hi - lo) * 0.5 }
        })
        .collect()
}
