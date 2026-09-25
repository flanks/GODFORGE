//! Pipeline step 6 (§3.2): the road network. A Kruskal tree over region adjacency (sorted by
//! `(q8(dist²), a, b)`) guarantees every region is reachable; each other adjacency adds a loop road
//! with `loop_chance`. A road runs site → pass → site, the pass being the point on the shared border
//! nearest the line between the sites, with one jittered bend per leg. The Landing joins its
//! region's site the same way. Then every site's road distance from the Landing.

use super::regions::MIN_BORDER;
use super::tiles::{self, steps_to};
use super::{Gen, Road};
use crate::procgen::{point_seg, q, qv};
use crate::schema::Lane;
use gf_core::rng::GfRng;
use glam::Vec2;

/// Largest sideways bend of a leg, as a share of its length.
const BEND: f32 = 0.18;
/// Passes keep this many tiles from the coast where the border allows it.
const PASS_COAST: u16 = 3;

fn find(parent: &mut [usize], mut i: usize) -> usize {
    while parent[i] != i {
        parent[i] = parent[parent[i]];
        i = parent[i];
    }
    i
}

pub(crate) fn lay(g: &mut Gen) {
    let mut rng = g.root.fork(1).fork(2);
    let n = g.regions.len();
    let q8 = |v: f32| (v * 8.0).round() as i64;
    let key = |g: &Gen, a: usize, b: usize| (q8(g.regions[a].site.distance_squared(g.regions[b].site)), a, b);
    let mut cand: Vec<(i64, usize, usize)> =
        g.adj.iter().filter(|a| a.border >= MIN_BORDER).map(|a| key(g, a.a, a.b)).collect();
    cand.sort_unstable();
    let mut parent: Vec<usize> = (0..n).collect();
    let mut chosen: Vec<(usize, usize)> = Vec::new();
    let mut rest: Vec<(usize, usize)> = Vec::new();
    for &(_, a, b) in &cand {
        let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
        if ra != rb {
            parent[ra] = rb;
            chosen.push((a, b));
        } else {
            rest.push((a, b));
        }
    }
    // Regions joined only by a sliver of border still get a road rather than none.
    let mut thin: Vec<(i64, usize, usize)> =
        g.adj.iter().filter(|a| a.border < MIN_BORDER).map(|a| key(g, a.a, a.b)).collect();
    thin.sort_unstable();
    for &(_, a, b) in &thin {
        let (ra, rb) = (find(&mut parent, a), find(&mut parent, b));
        if ra != rb && g.regions[a].area > 0 && g.regions[b].area > 0 {
            parent[ra] = rb;
            chosen.push((a, b));
        }
    }
    for &(a, b) in &rest {
        if rng.chance(g.x.roads.loop_chance) {
            chosen.push((a, b));
        }
    }
    let coast = steps_to(&g.tiles, |i| !g.tiles.kind[i].is_land(), true);
    let width = q(g.x.roads.width);
    for (a, b) in chosen {
        let pass = pass_point(g, a, b, &coast);
        let (sa, sb) = (g.regions[a].site, g.regions[b].site);
        let mut lanes = leg(g, sa, pass, [a, b], width, &mut rng);
        lanes.extend(leg(g, pass, sb, [a, b], width, &mut rng));
        g.regions[a].degree += 1;
        g.regions[b].degree += 1;
        g.roads.push(Road { a, b, pass, lanes });
    }
    let lr = g.landing_region;
    g.landing_road = leg(g, g.landing, g.regions[lr].site, [lr, lr], width, &mut rng);
    depth(g);
}

/// The point on the border of regions `a` and `b` nearest the line between their sites (ties to
/// its middle), kept off the coast where the border allows.
fn pass_point(g: &Gen, a: usize, b: usize, coast: &[u16]) -> Vec2 {
    let t = &g.tiles;
    let (sa, sb) = (g.regions[a].site, g.regions[b].site);
    let mid = (sa + sb) * 0.5;
    let q8 = |v: f32| (v * 8.0).round() as i64;
    let mut best: Option<((i64, i64, usize, usize), Vec2)> = None;
    for pass in [PASS_COAST, 1] {
        for i in 0..t.kind.len() {
            if !t.kind[i].is_land() || t.region[i] as usize != a || coast[i] < pass {
                continue;
            }
            for j in tiles::around(t, i) {
                if !t.kind[j].is_land() || t.region[j] as usize != b || coast[j] < pass {
                    continue;
                }
                let w = t.w as usize;
                let ci = t.center((i % w) as u16, (i / w) as u16);
                let cj = t.center((j % w) as u16, (j / w) as u16);
                let p = (ci + cj) * 0.5;
                let k = (q8(point_seg(p, sa, sb)), q8(p.distance(mid)), i, j);
                if best.is_none_or(|(bk, _)| k < bk) {
                    best = Some((k, p));
                }
            }
        }
        if best.is_some() {
            break;
        }
    }
    qv(best.map_or(mid, |(_, p)| p))
}

/// A road leg from `a` to `z` with one jittered bend at its middle, pushed sideways by up to
/// [`BEND`] of its length. The bend shrinks (then straightens) until the leg stays on land inside
/// `regions`.
fn leg(g: &Gen, a: Vec2, z: Vec2, regions: [usize; 2], width: f32, rng: &mut GfRng) -> Vec<Lane> {
    let d = z - a;
    let len = d.length();
    let side = rng.range_f32(-BEND, BEND);
    if len < 8.0 {
        return vec![Lane { from: a, to: z, width }];
    }
    let perp = Vec2::new(-d.y, d.x) / len;
    let clear = |p: Vec2, r: Vec2| {
        let n = ((p.distance(r) / 2.0).ceil() as usize).max(1);
        (0..=n).all(|k| {
            let s = p + (r - p) * (k as f32 / n as f32);
            let i = tiles::tile_at(&g.tiles, s);
            g.tiles.kind[i].is_land() && regions.contains(&(g.tiles.region[i] as usize))
        })
    };
    for k in [1.0f32, 0.5] {
        let m = qv((a + z) * 0.5 + perp * (side * len * k));
        if clear(a, m) && clear(m, z) {
            return vec![Lane { from: a, to: m, width }, Lane { from: m, to: z, width }];
        }
    }
    let m = qv((a + z) * 0.5);
    vec![Lane { from: a, to: m, width }, Lane { from: m, to: z, width }]
}

fn length(lanes: &[Lane]) -> f32 {
    lanes.iter().map(|l| l.from.distance(l.to)).sum()
}

/// Road distance of every region's site from the Landing (Dijkstra over the road graph, ties to
/// the lower index), normalized so the farthest site is 1.
fn depth(g: &mut Gen) {
    let n = g.regions.len();
    let mut dist = vec![f32::INFINITY; n];
    let mut done = vec![false; n];
    dist[g.landing_region] = length(&g.landing_road);
    loop {
        let mut u = None;
        for r in 0..n {
            if !done[r] && dist[r].is_finite() && u.is_none_or(|v: usize| dist[r] < dist[v]) {
                u = Some(r);
            }
        }
        let Some(u) = u else { break };
        done[u] = true;
        for road in &g.roads {
            let v = if road.a == u {
                road.b
            } else if road.b == u {
                road.a
            } else {
                continue;
            };
            let alt = dist[u] + length(&road.lanes);
            if alt < dist[v] {
                dist[v] = alt;
            }
        }
    }
    let max = dist.iter().copied().filter(|d| d.is_finite()).fold(1.0f32, f32::max);
    for (r, reg) in g.regions.iter_mut().enumerate() {
        reg.depth = if dist[r].is_finite() { dist[r] / max } else { 1.0 };
    }
    g.depth_scale = max;
    g.site_dist = dist;
}

impl Gen<'_> {
    /// Road distance of a point `s` u along road `k` (from its `a` end), normalized like
    /// [`RegionGen::depth`](super::RegionGen::depth).
    pub(crate) fn road_depth(&self, k: usize, s: f32) -> f32 {
        let road = &self.roads[k];
        let total = length(&road.lanes);
        let (da, db) = (self.site_dist[road.a], self.site_dist[road.b]);
        ((da + s).min(db + total - s) / self.depth_scale).min(1.0)
    }

    /// Road distance of a point `s` u along the Landing road, normalized.
    pub(crate) fn landing_depth(&self, s: f32) -> f32 {
        (s / self.depth_scale).min(1.0)
    }
}
