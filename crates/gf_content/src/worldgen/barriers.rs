//! Pipeline step 7 (§3.2): barriers between adjacent regions. Each region pair rolls
//! `barriers.chance` and picks a kind by weight. Chasms (`Void`, 2 tiles thick) and rivers
//! (`Liquid`, 2–3 thick) are pit bands along the shared border; wherever a road or spur crosses one
//! it keeps a pass `roads.pass_width` wide of `Bridge` tiles. Walls and ridges are obstacle lines
//! laid by the composer (roads breach them under an arch).
//!
//! A band never strands land: POI clearings, the Landing and crossroads hubs are kept whole, and a
//! band that would cut land off from the Landing either swallows a small pocket (a lake by the
//! coast) or is not cut at all.

use super::regions::MIN_BORDER;
use super::tiles::{self, around, disc};
use super::{Gen, HUB_R, LANDING_R};
use crate::procgen::{point_seg, q, qv, rot_of};
use crate::schema::*;
use glam::Vec2;

/// Largest pocket of land a band may swallow instead of being dropped.
const POCKET: usize = 16;

pub(crate) fn lay(g: &mut Gen) {
    let mut rng = g.root.fork(1).fork(4);
    let chance = g.x.barriers.chance;
    let kinds = g.x.barriers.kinds.clone();
    let weights: Vec<f32> = kinds.iter().map(|k| k.1.max(0.0)).collect();
    let lanes = g.lanes();
    let pw = g.x.roads.pass_width.max(g.x.roads.width);
    let n = g.tiles.kind.len();
    // Tiles a road crosses are bridged instead of cut.
    let mut bridge = vec![false; n];
    for l in &lanes {
        for i in tiles::along(&g.tiles, l.from, l.to, pw * 0.5) {
            bridge[i] = true;
        }
    }
    // Clearings, the Landing and crossroads hubs stay whole.
    let mut protect = vec![false; n];
    let mut zones: Vec<(Vec2, f32)> = vec![(g.landing, LANDING_R + 8.0)];
    zones.extend(g.pois.iter().map(|p| (p.site.at, p.plaza + 4.0)));
    zones.extend(g.regions.iter().filter(|r| r.landmark.is_some()).map(|r| (r.site, HUB_R + 4.0)));
    for (c, r) in zones {
        for i in disc(&g.tiles, c, r) {
            protect[i] = true;
        }
    }
    let start = tiles::tile_at(&g.tiles, g.landing);
    for k in 0..g.adj.len() {
        // Every pair draws the same numbers whatever it rolls, so one pair's kind never shifts another's.
        let roll = rng.f32();
        let pick = rng.weighted_index(&weights);
        let (wide, side) = (rng.chance(0.5), rng.chance(0.5));
        if roll >= chance || g.adj[k].border < MIN_BORDER {
            continue;
        }
        let Some(kind) = pick.map(|i| kinds[i].0) else { continue };
        match kind {
            BarrierKind::Wall | BarrierKind::Ridge => {
                g.adj[k].barrier = Some(kind);
                g.walls.push(k);
            }
            BarrierKind::Chasm | BarrierKind::River => {
                let wide = wide && kind == BarrierKind::River;
                if cut(g, k, kind, wide, side, &bridge, &protect, start) {
                    g.adj[k].barrier = Some(kind);
                }
            }
        }
    }
    passes(g, &lanes, pw);
}

/// Cut the pit band of pair `k`; `false` (and nothing changed) when it would strand land.
#[allow(clippy::too_many_arguments)]
fn cut(
    g: &mut Gen,
    k: usize,
    kind: BarrierKind,
    wide: bool,
    side: bool,
    bridge: &[bool],
    protect: &[bool],
    start: usize,
) -> bool {
    let (a, b) = (g.adj[k].a, g.adj[k].b);
    let t = &g.tiles;
    let n = t.kind.len();
    let facing = |i: usize, r: usize, o: usize| {
        t.kind[i].is_land()
            && t.region[i] as usize == r
            && around(t, i).any(|j| t.kind[j].is_land() && t.region[j] as usize == o)
    };
    let mut band: Vec<usize> = (0..n).filter(|&i| facing(i, a, b) || facing(i, b, a)).collect();
    if wide {
        let s = if side { a } else { b };
        let inner: Vec<usize> = (0..n)
            .filter(|&i| {
                t.kind[i].is_land()
                    && t.region[i] as usize == s
                    && band.binary_search(&i).is_err()
                    && around(t, i).any(|j| t.region[j] as usize == s && band.binary_search(&j).is_ok())
            })
            .collect();
        band.extend(inner);
        band.sort_unstable();
    }
    let band = chamfer(t, &band, a, b);
    let pit = if kind == BarrierKind::Chasm { TileKind::Void } else { TileKind::Liquid };
    let mut changed: Vec<(usize, TileKind)> = Vec::new();
    for i in band {
        let old = g.tiles.kind[i];
        if protect[i] || !matches!(old, TileKind::Ground | TileKind::Road) {
            continue;
        }
        g.tiles.kind[i] = if bridge[i] { TileKind::Bridge } else { pit };
        changed.push((i, old));
    }
    // Land the band cut off from the Landing: swallow small pockets, else undo the band.
    let t = &g.tiles;
    let reach = tiles::flood(t, start, |j| t.kind[j].is_land());
    let mut seen = reach.clone();
    let mut swallow: Vec<usize> = Vec::new();
    for i in 0..n {
        if seen[i] || !t.kind[i].is_land() {
            continue;
        }
        let pocket: Vec<usize> =
            tiles::flood(t, i, |j| t.kind[j].is_land()).into_iter().enumerate().filter(|p| p.1).map(|p| p.0).collect();
        for &j in &pocket {
            seen[j] = true;
        }
        if pocket.len() > POCKET || pocket.iter().any(|&j| protect[j] || bridge[j]) {
            for (i, old) in changed {
                g.tiles.kind[i] = old;
            }
            return false;
        }
        swallow.extend(pocket);
    }
    for i in swallow {
        g.tiles.kind[i] = pit;
    }
    true
}

/// Chamfer a band's staircase: a land tile of the pair's two regions with at least five of its
/// eight neighbours in the band joins it (the inner corner of every step), and a band tile with
/// at most two band neighbours leaves it (spurs), so a river or chasm runs in 45° reaches instead
/// of tile-sized L shapes. Integer counts only; the result is sorted.
fn chamfer(t: &TileGrid, band: &[usize], a: usize, b: usize) -> Vec<usize> {
    let n = t.kind.len();
    let (w, h) = (t.w as i32, t.h as i32);
    let mut inb = vec![false; n];
    for &i in band {
        inb[i] = true;
    }
    let count = |inb: &[bool], i: usize| {
        let (x, y) = ((i % w as usize) as i32, (i / w as usize) as i32);
        let mut c = 0;
        for dy in -1..=1 {
            for dx in -1..=1 {
                let (nx, ny) = (x + dx, y + dy);
                if (dx, dy) != (0, 0) && nx >= 0 && ny >= 0 && nx < w && ny < h && inb[(ny * w + nx) as usize] {
                    c += 1;
                }
            }
        }
        c
    };
    let add: Vec<usize> = (0..n)
        .filter(|&i| {
            !inb[i]
                && t.kind[i].is_land()
                && (t.region[i] as usize == a || t.region[i] as usize == b)
                && count(&inb, i) >= 5
        })
        .collect();
    let drop: Vec<usize> = band.iter().copied().filter(|&i| count(&inb, i) <= 2).collect();
    for i in add {
        inb[i] = true;
    }
    for i in drop {
        inb[i] = false;
    }
    (0..n).filter(|&i| inb[i]).collect()
}

/// One pass per bridged crossing (a connected run of `Bridge` tiles) with its deck from bank to
/// bank along the road, and one per road through a wall or ridge.
fn passes(g: &mut Gen, lanes: &[Lane], pw: f32) {
    let t = &g.tiles;
    let n = t.kind.len();
    let w = t.w as usize;
    let centre = |i: usize| t.center((i % w) as u16, (i / w) as u16);
    let mut seen = vec![false; n];
    let mut out: Vec<(Pass, Lane)> = Vec::new();
    for i in 0..n {
        if seen[i] || t.kind[i] != TileKind::Bridge {
            continue;
        }
        let run: Vec<usize> = tiles::flood(t, i, |j| t.kind[j] == TileKind::Bridge)
            .into_iter()
            .enumerate()
            .filter(|p| p.1)
            .map(|p| p.0)
            .collect();
        for &j in &run {
            seen[j] = true;
        }
        let mid = run.iter().map(|&j| centre(j)).sum::<Vec2>() / run.len() as f32;
        let Some(l) = lanes.iter().min_by(|x, y| point_seg(mid, x.from, x.to).total_cmp(&point_seg(mid, y.from, y.to)))
        else {
            continue;
        };
        let dir = (l.to - l.from).normalize_or(Vec2::X);
        let s: Vec<f32> = run.iter().map(|&j| (centre(j) - l.from).dot(dir)).collect();
        let (s0, s1) = (s.iter().copied().fold(f32::MAX, f32::min), s.iter().copied().fold(f32::MIN, f32::max));
        let liquid = run.iter().any(|&j| around(t, j).any(|o| t.kind[o] == TileKind::Liquid));
        let kind = if liquid { BarrierKind::River } else { BarrierKind::Chasm };
        let at = qv(l.from + dir * ((s0 + s1) * 0.5));
        let pass = Pass { at, along: rot_of(dir), width: q(pw), kind };
        let deck = Lane { from: qv(l.from + dir * (s0 - 3.0)), to: qv(l.from + dir * (s1 + 3.0)), width: q(pw) };
        out.push((pass, deck));
    }
    for (pass, deck) in out {
        g.passes.push(pass);
        g.bridges.push(deck);
    }
    for &k in &g.walls {
        let (a, b, kind) = (g.adj[k].a, g.adj[k].b, g.adj[k].barrier.unwrap_or(BarrierKind::Wall));
        for road in g.roads.iter().filter(|r| (r.a, r.b) == (a, b) || (r.a, r.b) == (b, a)) {
            let dir = road_dir(&road.lanes, road.pass);
            g.passes.push(Pass { at: road.pass, along: rot_of(dir), width: q(pw), kind });
        }
    }
}

/// Direction a road runs through the point `at` on it.
pub(crate) fn road_dir(lanes: &[Lane], at: Vec2) -> Vec2 {
    let mut d = Vec2::ZERO;
    for l in lanes {
        if l.to == at || l.from == at {
            d += (l.to - l.from).normalize_or(Vec2::ZERO);
        }
    }
    d.normalize_or(Vec2::X)
}
