//! Pipeline steps 2–5 (§3.2): the jittered region sites, domain-warped Voronoi regions, the coast,
//! region adjacency, each region's site (its most interior tile), the Landing, themes and the gate
//! region.

use super::tiles::{self, around, noise};
use super::{Adj, Gen, LANDING_R, RegionGen, TILE};
use crate::procgen::qv;
use crate::schema::TileKind;
use gf_core::rng::GfRng;
use glam::Vec2;
use std::collections::VecDeque;

/// Shared border (tile edges) below which two regions are not road neighbours.
pub(crate) const MIN_BORDER: u32 = 3;
/// Region border warp: amplitude and lattice period, in tiles (§3.2 step 2).
const WARP_AMP: i32 = 3;
const WARP_PERIOD: i32 = 6;

pub(crate) fn lay(g: &mut Gen) {
    let mut rng = g.root.fork(1).fork(1);
    let seeds = sites(g, &mut rng);
    voronoi(g, &seeds, &mut rng);
    g.landing_edge = rng.range_u32(0, 4) as u8;
    coast(g, &mut rng);
    keep_mainland(g);
    g.regions = seeds
        .iter()
        .map(|&seed| RegionGen {
            seed,
            site: Vec2::ZERO,
            theme: 0,
            area: 0,
            lo: (u16::MAX, u16::MAX),
            hi: (0, 0),
            depth: 0.0,
            degree: 0,
            major: None,
            landmark: None,
        })
        .collect();
    contiguous(g);
    adjacency(g);
    poles(g);
    landing(g);
    themes(g, &mut rng);
    g.gate_region = gate_region(g);
}

/// A jittered `regions.x × regions.y` grid of sites in tile coordinates (cell centre ± 30 %), kept
/// clear of the coast and apart from each other.
fn sites(g: &Gen, rng: &mut GfRng) -> Vec<(i32, i32)> {
    let (w, h) = (g.tiles.w as i32, g.tiles.h as i32);
    let (rx, ry) = (g.x.regions.0.max(1) as i32, g.x.regions.1.max(1) as i32);
    // Cell size and jitter in 1/256 tiles.
    let (cw, ch) = (w * 256 / rx, h * 256 / ry);
    let (jx, jy) = (cw * 3 / 10, ch * 3 / 10);
    let coast = g.x.coast.depth as i32 + g.x.coast.amp as i32;
    let (mx, my) = ((coast + 6).min(w / 2 - 1).max(0), (coast + 6).min(h / 2 - 1).max(0));
    let sep = (cw.min(ch) as i64 * 55 / 100).pow(2);
    let clamp = |x: i32, y: i32| ((x / 256).clamp(mx, w - 1 - mx), (y / 256).clamp(my, h - 1 - my));
    let mut out: Vec<(i32, i32)> = Vec::new();
    for cy in 0..ry {
        for cx in 0..rx {
            let (ox, oy) = (cw * cx + cw / 2, ch * cy + ch / 2);
            let mut pick = clamp(ox, oy);
            for _ in 0..8 {
                let px = ox + rng.range_u32(0, (2 * jx + 1) as u32) as i32 - jx;
                let py = oy + rng.range_u32(0, (2 * jy + 1) as u32) as i32 - jy;
                let t = clamp(px, py);
                let apart = out.iter().all(|&(sx, sy)| {
                    let (dx, dy) = (((t.0 - sx) * 256) as i64, ((t.1 - sy) * 256) as i64);
                    dx * dx + dy * dy >= sep
                });
                if apart {
                    pick = t;
                    break;
                }
            }
            out.push(pick);
        }
    }
    out
}

/// Each tile goes to the nearest site by integer squared distance on domain-warped tile
/// coordinates (1/256 fixed point); ties go to the lower index.
fn voronoi(g: &mut Gen, seeds: &[(i32, i32)], rng: &mut GfRng) {
    let (wx, wy) = (rng.next_u64(), rng.next_u64());
    let t = &mut g.tiles;
    for y in 0..t.h as i32 {
        for x in 0..t.w as i32 {
            let px = x * 256 + 128 + (noise(wx, x, y, WARP_PERIOD) - 128) * 2 * WARP_AMP;
            let py = y * 256 + 128 + (noise(wy, x, y, WARP_PERIOD) - 128) * 2 * WARP_AMP;
            let mut best = (i64::MAX, 0usize);
            for (i, &(sx, sy)) in seeds.iter().enumerate() {
                let (dx, dy) = ((px - (sx * 256 + 128)) as i64, (py - (sy * 256 + 128)) as i64);
                let d = dx * dx + dy * dy;
                if d < best.0 {
                    best = (d, i);
                }
            }
            let i = t.index(x as u16, y as u16);
            t.region[i] = best.1 as u8;
        }
    }
}

/// The coast (§3.2 step 4): a tile is `Void` when its distance to a map edge is below
/// `depth + noise × amp` tiles, the noise running along that edge. The Landing edge's middle third
/// keeps `depth` only, so arrival is never cramped.
fn coast(g: &mut Gen, rng: &mut GfRng) {
    let base = rng.next_u64();
    let (depth, amp, period) = (g.x.coast.depth as i32, g.x.coast.amp as i32, g.x.coast.period.max(1) as i32);
    let (w, h) = (g.tiles.w as i32, g.tiles.h as i32);
    let calm_edge = g.landing_edge;
    for y in 0..h {
        for x in 0..w {
            // (distance in tiles, position along the edge, edge length, edge id)
            let edges = [(y, x, w, 0u8), (h - 1 - y, x, w, 1), (x, y, h, 2), (w - 1 - x, y, h, 3)];
            let void = edges.iter().any(|&(d, pos, len, e)| {
                let calm = e == calm_edge && pos * 3 >= len && pos * 3 < len * 2;
                let n = if calm {
                    0
                } else {
                    ((noise(base ^ ((e as u64 + 1) * 0x51_7CC1), pos, 0, period) * (amp + 1)) >> 8).min(amp)
                };
                d < depth + n
            });
            if void {
                let i = g.tiles.index(x as u16, y as u16);
                g.tiles.kind[i] = TileKind::Void;
            }
        }
    }
}

/// Keep only the largest connected landmass (the coast noise can pinch off islets).
fn keep_mainland(g: &mut Gen) {
    let t = &g.tiles;
    let mut label = vec![u32::MAX; t.kind.len()];
    let mut best = (0usize, u32::MAX);
    let mut next = 0u32;
    for i in 0..t.kind.len() {
        if label[i] != u32::MAX || !t.kind[i].is_land() {
            continue;
        }
        let seen = tiles::flood(t, i, |j| t.kind[j].is_land() && label[j] == u32::MAX);
        let mut n = 0;
        for (j, s) in seen.iter().enumerate() {
            if *s {
                label[j] = next;
                n += 1;
            }
        }
        if n > best.0 {
            best = (n, next);
        }
        next += 1;
    }
    for (i, l) in label.iter().enumerate() {
        if *l != best.1 {
            g.tiles.kind[i] = TileKind::Void;
        }
    }
}

/// Every region is one piece of land: tiles cut off from their site join the region of a
/// connected neighbour. Then each region's area and bounding box.
fn contiguous(g: &mut Gen) {
    let n = g.regions.len();
    let t = &g.tiles;
    let mut ok = vec![false; t.kind.len()];
    for r in 0..n {
        let (sx, sy) = g.regions[r].seed;
        let start = t.index(sx as u16, sy as u16);
        let seen = tiles::flood(t, start, |j| t.kind[j].is_land() && t.region[j] as usize == r);
        for (i, s) in seen.into_iter().enumerate() {
            ok[i] |= s;
        }
    }
    loop {
        let mut changed = false;
        for i in 0..ok.len() {
            if ok[i] || !g.tiles.kind[i].is_land() {
                continue;
            }
            let from = around(&g.tiles, i).find(|&j| ok[j]);
            if let Some(j) = from {
                g.tiles.region[i] = g.tiles.region[j];
                ok[i] = true;
                changed = true;
            }
        }
        if !changed {
            break;
        }
    }
    let w = g.tiles.w as usize;
    for i in 0..ok.len() {
        if !g.tiles.kind[i].is_land() {
            continue;
        }
        let r = &mut g.regions[g.tiles.region[i] as usize];
        let (x, y) = ((i % w) as u16, (i / w) as u16);
        r.area += 1;
        r.lo = (r.lo.0.min(x), r.lo.1.min(y));
        r.hi = (r.hi.0.max(x), r.hi.1.max(y));
    }
}

/// Region adjacency from shared border tiles (land on both sides), in `(a, b)` order.
fn adjacency(g: &mut Gen) {
    let n = g.regions.len();
    let t = &g.tiles;
    let mut count = vec![0u32; n * n];
    let w = t.w as usize;
    for i in 0..t.kind.len() {
        if !t.kind[i].is_land() {
            continue;
        }
        let (x, y) = (i % w, i / w);
        for j in [(x + 1 < w).then(|| i + 1), (y + 1 < t.h as usize).then(|| i + w)].into_iter().flatten() {
            let (a, b) = (t.region[i] as usize, t.region[j] as usize);
            if t.kind[j].is_land() && a != b {
                count[a.min(b) * n + a.max(b)] += 1;
            }
        }
    }
    g.adj = (0..n)
        .flat_map(|a| (a + 1..n).map(move |b| (a, b)))
        .filter(|&(a, b)| count[a * n + b] > 0)
        .map(|(a, b)| Adj { a, b, border: count[a * n + b], barrier: None })
        .collect();
}

/// Each region's site: its most interior tile (the most steps from its border and the coast),
/// ties to the tile nearest its Voronoi seed. Big clearings fit there, and roads meet there.
fn poles(g: &mut Gen) {
    let t = &g.tiles;
    let dist = tiles::edge_steps(t);
    let w = t.w as i64;
    for (r, reg) in g.regions.iter_mut().enumerate() {
        let (sx, sy) = (reg.seed.0 as i64, reg.seed.1 as i64);
        let mut best: Option<(u16, i64, usize)> = None;
        for (i, &di) in dist.iter().enumerate() {
            if !t.kind[i].is_land() || t.region[i] as usize != r || di == u16::MAX {
                continue;
            }
            let (x, y) = (i as i64 % w, i as i64 / w);
            let near = (x - sx).pow(2) + (y - sy).pow(2);
            let better = match best {
                None => true,
                Some((d, s, _)) => di > d || (di == d && near < s),
            };
            if better {
                best = Some((di, near, i));
            }
        }
        if let Some((_, _, i)) = best {
            reg.site = t.center((i as i64 % w) as u16, (i as i64 / w) as u16);
        }
    }
}

/// The Landing (§3.2 step 5): on the seed-chosen edge, in the region whose site is nearest that
/// edge's midpoint, inset past the calm coast and inside the edge's middle third.
fn landing(g: &mut Gen) {
    let (hx, hy) = (g.half.x, g.half.y);
    let mid = match g.landing_edge {
        0 => Vec2::new(0.0, -hy),
        1 => Vec2::new(0.0, hy),
        2 => Vec2::new(-hx, 0.0),
        _ => Vec2::new(hx, 0.0),
    };
    let mut lr = 0;
    for (r, reg) in g.regions.iter().enumerate() {
        if reg.area > 0 && reg.site.distance_squared(mid) < g.regions[lr].site.distance_squared(mid) {
            lr = r;
        }
    }
    g.landing_region = lr;
    let site = g.regions[lr].site;
    let inset = g.x.coast.depth as f32 * TILE + LANDING_R + 8.0;
    let (sx, sy) = ((hx / 3.0 - 12.0).max(0.0), (hy / 3.0 - 12.0).max(0.0));
    let start = match g.landing_edge {
        0 => Vec2::new(site.x.clamp(-sx, sx), -hy + inset),
        1 => Vec2::new(site.x.clamp(-sx, sx), hy - inset),
        2 => Vec2::new(-hx + inset, site.y.clamp(-sy, sy)),
        _ => Vec2::new(hx - inset, site.y.clamp(-sy, sy)),
    };
    let t = &g.tiles;
    let fits = |p: Vec2| {
        let i = tiles::tile_at(t, p);
        t.kind[i].is_land()
            && t.region[i] as usize == lr
            && tiles::disc(t, p, LANDING_R + 2.0).iter().all(|&j| t.kind[j].is_land())
    };
    g.landing = (0..=40).map(|k| qv(start + (site - start) * (k as f32 / 40.0))).find(|p| fits(*p)).unwrap_or(qv(site));
}

/// Themes (§3.2 step 3): the Landing region takes `start_theme`; the rest pick by weight, avoiding
/// their already-themed neighbours' themes where possible.
fn themes(g: &mut Gen, rng: &mut GfRng) {
    let n = g.regions.len();
    let weights: Vec<f32> = g.x.themes.iter().map(|t| t.weight.max(0.0)).collect();
    let start = g.x.theme(&g.x.start_theme).unwrap_or(0) as u8;
    let mut done = vec![false; n];
    g.regions[g.landing_region].theme = start;
    done[g.landing_region] = true;
    for r in 0..n {
        if done[r] {
            continue;
        }
        let mut w = weights.clone();
        for a in &g.adj {
            let other = if a.a == r {
                a.b
            } else if a.b == r {
                a.a
            } else {
                continue;
            };
            if done[other]
                && let Some(v) = w.get_mut(g.regions[other].theme as usize)
            {
                *v = 0.0;
            }
        }
        let pick = rng.weighted_index(&w).or_else(|| rng.weighted_index(&weights)).unwrap_or(0);
        g.regions[r].theme = pick as u8;
        done[r] = true;
    }
}

/// Road neighbours of region `r` in the adjacency graph (borders of at least [`MIN_BORDER`]).
pub(crate) fn neighbours(g: &Gen, r: usize) -> Vec<usize> {
    g.adj
        .iter()
        .filter(|a| a.border >= MIN_BORDER)
        .filter_map(|a| {
            if a.a == r {
                Some(a.b)
            } else if a.b == r {
                Some(a.a)
            } else {
                None
            }
        })
        .collect()
}

/// The gate region: the most adjacency hops from the Landing region, ties to the site farthest
/// from the Landing, then the lower index.
fn gate_region(g: &Gen) -> usize {
    let n = g.regions.len();
    let mut hops = vec![u32::MAX; n];
    hops[g.landing_region] = 0;
    let mut queue = VecDeque::from([g.landing_region]);
    while let Some(r) = queue.pop_front() {
        for s in neighbours(g, r) {
            if hops[s] == u32::MAX {
                hops[s] = hops[r] + 1;
                queue.push_back(s);
            }
        }
    }
    let mut best = g.landing_region;
    for r in 0..n {
        if hops[r] == u32::MAX || r == g.landing_region || g.regions[r].area == 0 {
            continue;
        }
        let (d, bd) = (g.regions[r].site.distance_squared(g.landing), g.regions[best].site.distance_squared(g.landing));
        if best == g.landing_region || hops[r] > hops[best] || (hops[r] == hops[best] && d > bd) {
            best = r;
        }
    }
    best
}
