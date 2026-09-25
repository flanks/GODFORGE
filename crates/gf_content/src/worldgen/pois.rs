//! POI placement (§3.3). Placement reads `depth`: the road distance from the Landing, normalized to
//! 0..=1. Major POIs take a region's site (one per region, never the Landing's). Minor POIs take
//! secondary sites on the roads, at least 25 u from their region's site; Reliquaries, Veins and
//! Springs stand off the road at the end of a spur. POIs keep 36 u apart (Springs and Watchfires
//! 20 u) and 30 u from the Landing. A site that cannot be met relaxes the spacing by 10 % per pass
//! for up to 3 passes, then takes any road point in its band; every relaxation is counted in
//! `MapLayout.relaxed`. Finally every site without a major POI becomes a crossroads hub with a
//! grand monument, and the roads stop at its rim.

use super::regions::neighbours;
use super::tiles;
use super::{Gen, HUB_R, LANDING_R, PoiGen};
use crate::procgen::{point_seg, q, qv};
use crate::schema::*;
use gf_core::poi::PoiKind;
use gf_core::rng::GfRng;
use glam::Vec2;

/// Minors keep this far from their region's site.
const FROM_SITE: f32 = 25.0;
/// POIs keep this far from the Landing (all but the first Spring).
const FROM_LANDING: f32 = 30.0;
/// Random slack (u) on a candidate's distance to its nearest POI when picking the farthest.
const JITTER: f32 = 14.0;
/// Spacing between road samples.
const STEP: f32 = 2.0;

/// A point on a road where a minor POI may stand.
#[derive(Clone, Copy, Debug)]
struct Cand {
    at: Vec2,
    /// Unit direction of the road there.
    dir: Vec2,
    depth: f32,
    region: usize,
    /// The road it lies on (`usize::MAX`: the Landing road).
    road: usize,
}

/// Every [`STEP`] u along every road and the Landing road.
fn candidates(g: &Gen) -> Vec<Cand> {
    let mut out = Vec::new();
    let mut walk = |road: usize, lanes: &[Lane], depth: &dyn Fn(f32) -> f32| {
        let mut s0 = 0.0;
        for l in lanes {
            let len = l.from.distance(l.to);
            if len < 1e-3 {
                continue;
            }
            let dir = (l.to - l.from) / len;
            let mut s = STEP;
            while s < len {
                let at = qv(l.from + dir * s);
                let i = tiles::tile_at(&g.tiles, at);
                if g.tiles.kind[i].is_land() {
                    out.push(Cand { at, dir, depth: depth(s0 + s), region: g.tiles.region[i] as usize, road });
                }
                s += STEP;
            }
            s0 += len;
        }
    };
    for (k, road) in g.roads.iter().enumerate() {
        walk(k, &road.lanes, &|s| g.road_depth(k, s));
    }
    walk(usize::MAX, &g.landing_road, &|s| g.landing_depth(s));
    out
}

/// Spacing two POI kinds keep.
fn spacing(a: PoiKind, b: PoiKind) -> f32 {
    let small = |k: PoiKind| matches!(k, PoiKind::Spring | PoiKind::Watchfire);
    if small(a) || small(b) { 20.0 } else { 36.0 }
}

/// How a minor POI is placed.
#[derive(Clone, Copy)]
struct Want<'a> {
    kind: PoiKind,
    band: (f32, f32),
    /// Off the road: (min, max) distance from the road's centreline.
    offset: Option<(f32, f32)>,
    /// Only these regions (empty: any).
    only: &'a [usize],
    near_landing: bool,
}

/// Minor POI placement: the road samples, every lane, and the placement stream.
struct Placer {
    cands: Vec<Cand>,
    /// Every lane with its road (`usize::MAX`: the Landing road and spurs).
    lanes: Vec<(usize, Lane)>,
    rng: GfRng,
}

impl Placer {
    /// Is `at` a legal clearing of `plaza` for `kind` in region `region`, with every spacing
    /// scaled by `scale`?
    fn legal(&self, g: &Gen, kind: PoiKind, at: Vec2, plaza: f32, region: usize, scale: f32, w: &Want) -> bool {
        // Cheap distance checks first; the tile scan last.
        if !w.near_landing && at.distance(g.landing) < FROM_LANDING * scale {
            return false;
        }
        if w.near_landing && at.distance(g.landing) < LANDING_R + plaza + 1.0 {
            return false;
        }
        if !w.near_landing && at.distance(g.regions[region].site) < FROM_SITE {
            return false;
        }
        if !g.pois.iter().all(|p| p.site.at.distance(at) >= spacing(kind, p.site.kind) * scale) {
            return false;
        }
        // Every site still without a major becomes a crossroads hub: keep its plaza whole.
        if g.regions.iter().any(|r| r.major.is_none() && r.area > 0 && at.distance(r.site) < plaza + HUB_R + 4.0) {
            return false;
        }
        if g.roads.iter().any(|r| r.pass.distance(at) < plaza + 2.0) {
            return false;
        }
        let t = &g.tiles;
        let zone = tiles::disc(t, at, plaza + 2.0);
        !zone.is_empty() && zone.iter().all(|&i| t.kind[i].is_land() && t.region[i] as usize == region)
    }

    /// Place one minor POI; returns its position and the road point its spur leaves from.
    fn pick(&mut self, g: &mut Gen, w: Want) -> Option<(Vec2, usize)> {
        let (_, plaza) = g.poi_size(w.kind);
        let side = if self.rng.chance(0.5) { 1.0 } else { -1.0 };
        let off = w.offset.map_or(0.0, |(lo, hi)| q(self.rng.range_f32(lo, hi)));
        for pass in 0..5u8 {
            let scale = if pass < 4 { 1.0 - 0.1 * pass as f32 } else { 0.0 };
            let mut ok: Vec<(Vec2, usize)> = Vec::new();
            for c in &self.cands {
                if c.depth < w.band.0 || c.depth > w.band.1 || (!w.only.is_empty() && !w.only.contains(&c.region)) {
                    continue;
                }
                let perp = Vec2::new(-c.dir.y, c.dir.x);
                // On the road, or beside it: the drawn offset on either side, then the nearest one.
                let tries: Vec<f32> = match w.offset {
                    None => vec![0.0],
                    Some((lo, _)) => vec![off * side, -off * side, q(lo) * side, -q(lo) * side],
                };
                for o in tries {
                    let at = qv(c.at + perp * o);
                    let i = tiles::tile_at(&g.tiles, at);
                    let region = g.tiles.region[i] as usize;
                    if region != c.region {
                        continue;
                    }
                    if !self.legal(g, w.kind, at, plaza, region, scale, &w) {
                        continue;
                    }
                    // Off-road clearings stand beside their own road and clear of every other.
                    let crowded = o != 0.0
                        && self.lanes.iter().any(|&(road, l)| {
                            let d = point_seg(at, l.from, l.to);
                            if road == c.road { d < o.abs() - 0.5 } else { d < plaza + l.width * 0.5 - 0.5 }
                        });
                    if !crowded {
                        ok.push((at, region));
                        break;
                    }
                }
            }
            if ok.is_empty() {
                continue;
            }
            if pass > 0 {
                g.relax(|| format!("{:?} spacing (pass {pass}, band {:?})", w.kind, w.band));
            }
            // The farthest from every placed POI and the Landing, give or take a jitter (so maps
            // vary); spreading the early POIs leaves room for the later ones.
            let mut best: Option<(f32, usize)> = None;
            for (k, &(at, _)) in ok.iter().enumerate() {
                let near = g.pois.iter().map(|p| p.site.at.distance(at)).fold(at.distance(g.landing), f32::min);
                let score = near + self.rng.range_f32(0.0, JITTER);
                if best.is_none_or(|(s, _)| score > s) {
                    best = Some((score, k));
                }
            }
            return best.map(|(_, k)| ok[k]);
        }
        None
    }
}

/// Every POI the quotas ask for, as `(kind, seals)`, in quota order.
fn wanted(g: &Gen, kind: PoiKind) -> Vec<u8> {
    g.x.pois.iter().filter(|q| q.kind == kind).flat_map(|q| std::iter::repeat_n(q.seals, q.count as usize)).collect()
}

/// Push a POI at `at` (quantized) in `region`.
fn push(g: &mut Gen, kind: PoiKind, at: Vec2, region: usize, seals: u8, god: Option<u8>, guard: Option<u16>) -> usize {
    let (radius, plaza) = g.poi_size(kind);
    let site = PoiSite { kind, at: qv(at), radius, seals, region: region as u8, god, guard };
    g.pois.push(PoiGen { site, plaza, spur: None });
    g.pois.len() - 1
}

/// A free region for a major POI: not the Landing's, without a major yet.
fn free(g: &Gen, r: usize) -> bool {
    r != g.landing_region && g.regions[r].major.is_none() && g.regions[r].area > 0
}

/// Pick a free region satisfying `ok` whose depth lies in `band`, widening the band by 0.1 per
/// pass (each widening counts as a relaxation), then any free region.
fn pick_region(g: &mut Gen, rng: &mut GfRng, band: (f32, f32), ok: &dyn Fn(&Gen, usize) -> bool) -> Option<usize> {
    let n = g.regions.len();
    for pass in 0..4 {
        let w = 0.1 * pass as f32;
        let c: Vec<usize> = (0..n)
            .filter(|&r| free(g, r) && ok(g, r) && g.regions[r].depth >= band.0 - w && g.regions[r].depth <= band.1 + w)
            .collect();
        if !c.is_empty() {
            if pass > 0 {
                g.relax(|| format!("major band {band:?} widened by {w}"));
            }
            return Some(c[rng.range_u32(0, c.len() as u32) as usize]);
        }
    }
    let c: Vec<usize> = (0..n).filter(|&r| free(g, r)).collect();
    if c.is_empty() {
        return None;
    }
    g.relax(|| format!("major band {band:?} dropped"));
    Some(c[rng.range_u32(0, c.len() as u32) as usize])
}

/// Regions on the road route from the Landing to the gate, each with its share of the route.
fn route(g: &Gen) -> Vec<(usize, f32)> {
    let n = g.regions.len();
    let mut dist = vec![f32::INFINITY; n];
    let mut prev = vec![usize::MAX; n];
    let mut done = vec![false; n];
    dist[g.landing_region] = 0.0;
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
            let alt = dist[u] + road.lanes.iter().map(|l| l.from.distance(l.to)).sum::<f32>();
            if alt < dist[v] {
                dist[v] = alt;
                prev[v] = u;
            }
        }
    }
    let total = dist[g.gate_region];
    if !total.is_finite() || total <= 0.0 {
        return Vec::new();
    }
    let mut path = vec![g.gate_region];
    while let Some(&r) = path.last() {
        if prev[r] == usize::MAX {
            break;
        }
        path.push(prev[r]);
    }
    path.reverse();
    path.into_iter().map(|r| (r, dist[r] / total)).collect()
}

fn weighted_enemy(g: &Gen, rng: &mut GfRng, pool: &[WeightedKey]) -> Option<u16> {
    let usable: Vec<(u16, f32)> =
        pool.iter().filter_map(|w| g.db.enemies.id(&w.key).map(|id| (id, w.weight.max(0.0)))).collect();
    let weights: Vec<f32> = usable.iter().map(|u| u.1).collect();
    rng.weighted_index(&weights).map(|i| usable[i].0)
}

pub(crate) fn place(g: &mut Gen) {
    let mut rng = g.root.fork(1).fork(3);
    let biome = g.biome_def().cloned();

    // 1. The gate on the gate region's site.
    let gr = g.gate_region;
    let k = push(g, PoiKind::Gate, g.regions[gr].site, gr, 0, None, None);
    g.regions[gr].major = Some(k);

    // 2. The Warlord on the route to the gate, 50–75 % of the way.
    let route = route(g);
    for seals in wanted(g, PoiKind::Warlord) {
        let on_route: Vec<usize> =
            route.iter().filter(|&&(r, s)| (0.5..=0.75).contains(&s) && free(g, r)).map(|&(r, _)| r).collect();
        let r = if on_route.is_empty() {
            pick_region(g, &mut rng, (0.5, 0.8), &|_, _| true)
        } else {
            Some(on_route[rng.range_u32(0, on_route.len() as u32) as usize])
        };
        let bosses = biome.as_ref().map_or(&[][..], |b| &b.minibosses[..]);
        let guard = (!bosses.is_empty())
            .then(|| bosses[rng.range_u32(0, bosses.len() as u32) as usize].as_str())
            .and_then(|k| g.db.enemies.id(k));
        match r {
            Some(r) => g.regions[r].major = Some(push(g, PoiKind::Warlord, g.regions[r].site, r, seals, None, guard)),
            None => g.relax(|| "a major POI found no region".into()),
        }
    }

    // 3. Anvils: the first beside the Landing region, then deeper.
    let lr = g.landing_region;
    let beside = neighbours(g, lr);
    let roads_from_landing: Vec<usize> = g
        .roads
        .iter()
        .filter_map(|r| {
            if r.a == lr {
                Some(r.b)
            } else if r.b == lr {
                Some(r.a)
            } else {
                None
            }
        })
        .collect();
    for (i, seals) in wanted(g, PoiKind::Anvil).into_iter().enumerate() {
        let r = match i {
            0 => pick_region(g, &mut rng, (0.0, 1.0), &|_, r| roads_from_landing.contains(&r) || beside.contains(&r)),
            1 => pick_region(g, &mut rng, (0.35, 0.7), &|_, _| true),
            _ => pick_region(g, &mut rng, (0.6, 1.0), &|_, _| true),
        };
        match r {
            Some(r) => g.regions[r].major = Some(push(g, PoiKind::Anvil, g.regions[r].site, r, seals, None, None)),
            None => g.relax(|| "a major POI found no region".into()),
        }
    }

    // 4. Lairs: dead ends first.
    let elites = biome.as_ref().map_or_else(Vec::new, |b| b.elites.clone());
    for seals in wanted(g, PoiKind::Lair) {
        let leaves: Vec<usize> = (0..g.regions.len())
            .filter(|&r| free(g, r) && g.regions[r].degree == 1 && g.regions[r].depth >= 0.3)
            .collect();
        let r = if leaves.is_empty() {
            pick_region(g, &mut rng, (0.3, 0.9), &|_, _| true)
        } else {
            Some(leaves[rng.range_u32(0, leaves.len() as u32) as usize])
        };
        let guard = weighted_enemy(g, &mut rng, &elites);
        match r {
            Some(r) => g.regions[r].major = Some(push(g, PoiKind::Lair, g.regions[r].site, r, seals, None, guard)),
            None => g.relax(|| "a major POI found no region".into()),
        }
    }

    // 5–8. Minors along the roads.
    let mut lanes: Vec<(usize, Lane)> =
        g.roads.iter().enumerate().flat_map(|(k, r)| r.lanes.iter().map(move |l| (k, *l))).collect();
    lanes.extend(g.landing_road.iter().map(|l| (usize::MAX, *l)));
    let mut placer = Placer { cands: candidates(g), lanes, rng: g.root.fork(1).fork(5) };
    let mut gods: Vec<u8> = g.db.gods.enumerate().filter(|(_, d)| d.phase <= g.phase).map(|(i, _)| i as u8).collect();
    let minor = |g: &mut Gen, placer: &mut Placer, w: Want, seals: u8, god: Option<u8>| {
        match placer.pick(g, w) {
            Some((at, region)) => {
                push(g, w.kind, at, region, seals, god, None);
            }
            // A POI the map could not place at all counts as a relaxation (layout-stats fails it).
            None => g.relax(|| format!("{:?} not placed", w.kind)),
        }
    };
    let on_road = |kind, band| Want { kind, band, offset: None, only: &[], near_landing: false };
    let off_road = |kind, band| Want { kind, band, offset: Some((8.0, 14.0)), only: &[], near_landing: false };
    let by_gate = neighbours(g, g.gate_region);
    for seals in wanted(g, PoiKind::Shrine) {
        let god = (!gods.is_empty()).then(|| gods.remove(placer.rng.range_u32(0, gods.len() as u32) as usize));
        minor(g, &mut placer, on_road(PoiKind::Shrine, (0.2, 0.9)), seals, god);
    }
    for kind in [PoiKind::Reliquary, PoiKind::Vein] {
        for seals in wanted(g, kind) {
            minor(g, &mut placer, off_road(kind, (0.3, 0.9)), seals, None);
        }
    }
    for (i, seals) in wanted(g, PoiKind::Spring).into_iter().enumerate() {
        match i {
            0 => first_spring(g, &mut placer, seals),
            1 => minor(
                g,
                &mut placer,
                Want { offset: Some((7.0, 10.0)), ..on_road(PoiKind::Spring, (0.4, 0.6)) },
                seals,
                None,
            ),
            _ => {
                let w = Want { offset: Some((7.0, 10.0)), only: &by_gate, ..on_road(PoiKind::Spring, (0.0, 1.0)) };
                minor(g, &mut placer, w, seals, None);
            }
        }
    }
    for (i, seals) in wanted(g, PoiKind::Watchfire).into_iter().enumerate() {
        watchfire(g, &placer, i, seals);
    }

    // Spurs: off-road clearings connect to the nearest road point.
    let lanes = g.lanes();
    for p in g.pois.iter_mut() {
        if p.site.kind.is_major() {
            continue;
        }
        let nearest = lanes
            .iter()
            .map(|l| {
                let ab = l.to - l.from;
                let t = ((p.site.at - l.from).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
                l.from + ab * t
            })
            .min_by(|a, b| a.distance_squared(p.site.at).total_cmp(&b.distance_squared(p.site.at)));
        if let Some(s) = nearest
            && s.distance(p.site.at) > 1.0
        {
            p.spur = Some(qv(s));
        }
    }

    hubs(g, &mut rng);
}

/// The first Spring: 17–23 u from the Landing, on open land beside it.
fn first_spring(g: &mut Gen, placer: &mut Placer, seals: u8) {
    let (_, plaza) = g.poi_size(PoiKind::Spring);
    let w = Want { kind: PoiKind::Spring, band: (0.0, 1.0), offset: None, only: &[], near_landing: true };
    let mut ok = Vec::new();
    for d in [17.0f32, 20.0, 23.0] {
        for k in 0..16u8 {
            let at = qv(g.landing + rot16_dir(k) * d);
            let i = tiles::tile_at(&g.tiles, at);
            let region = g.tiles.region[i] as usize;
            let clear_of_road = g.landing_road.iter().all(|l| point_seg(at, l.from, l.to) >= plaza + l.width * 0.5);
            if clear_of_road && placer.legal(g, PoiKind::Spring, at, plaza, region, 1.0, &w) {
                ok.push((at, region));
            }
        }
    }
    if ok.is_empty() {
        if let Some((at, region)) = placer.pick(g, Want { near_landing: false, ..w }) {
            push(g, PoiKind::Spring, at, region, seals, None, None);
        }
        g.relax(|| "the first Spring left the Landing".into());
        return;
    }
    let (at, region) = ok[placer.rng.range_u32(0, ok.len() as u32) as usize];
    push(g, PoiKind::Spring, at, region, seals, None, None);
}

/// Watchfire `i`: on the road point nearest the centre of map quadrant `i % 4`.
fn watchfire(g: &mut Gen, placer: &Placer, i: usize, seals: u8) {
    let (_, plaza) = g.poi_size(PoiKind::Watchfire);
    let target = Vec2::new(
        if i.is_multiple_of(2) { -g.half.x * 0.5 } else { g.half.x * 0.5 },
        if (i / 2).is_multiple_of(2) { -g.half.y * 0.5 } else { g.half.y * 0.5 },
    );
    let w = Want { kind: PoiKind::Watchfire, band: (0.0, 1.0), offset: None, only: &[], near_landing: false };
    for (pass, scale) in [1.0f32, 0.9, 0.8, 0.7, 0.0].into_iter().enumerate() {
        let best = placer
            .cands
            .iter()
            .filter(|c| placer.legal(g, PoiKind::Watchfire, c.at, plaza, c.region, scale, &w))
            .min_by(|a, b| a.at.distance_squared(target).total_cmp(&b.at.distance_squared(target)))
            .copied();
        if let Some(c) = best {
            if pass > 0 {
                g.relax(|| format!("Watchfire {i} spacing (pass {pass})"));
            }
            push(g, PoiKind::Watchfire, c.at, c.region, seals, None, None);
            return;
        }
    }
    g.relax(|| format!("Watchfire {i} not placed"));
}

/// Every site without a major POI (the Landing region's included) becomes a crossroads hub around
/// a grand monument picked from the template's `landmarks`; roads stop at the hub's inner rim.
fn hubs(g: &mut Gen, rng: &mut GfRng) {
    if g.x.landmarks.is_empty() {
        return;
    }
    let base: Vec<f32> = g.x.landmarks.iter().map(|l| l.1.max(0.0)).collect();
    let mut used: Vec<MapMark> = Vec::new();
    for r in 0..g.regions.len() {
        if g.regions[r].major.is_some() || g.regions[r].area == 0 {
            continue;
        }
        // Clear of every POI clearing.
        let site = g.regions[r].site;
        if g.pois.iter().any(|p| p.site.at.distance(site) < p.plaza + HUB_R + 4.0) {
            g.trace(|| format!("region {r}: a POI clearing crowds its hub"));
            continue;
        }
        let w: Vec<f32> =
            g.x.landmarks.iter().zip(&base).map(|(l, w)| if used.contains(&l.0) { w * 0.25 } else { *w }).collect();
        let Some(k) = rng.weighted_index(&w) else { continue };
        let mark = g.x.landmarks[k].0;
        used.push(mark);
        g.regions[r].landmark = Some(mark);
        let stop = HUB_R * 0.75;
        // A stub ending inside the hub collapses onto its outer end (the plaza carries the way).
        let trim = |l: &mut Lane| {
            for (end, other) in [(true, l.to), (false, l.from)] {
                let p = if end { l.from } else { l.to };
                if p != site {
                    continue;
                }
                let moved = if p.distance(other) > stop + 2.0 {
                    qv(site + (other - site) * (stop / p.distance(other)))
                } else {
                    other
                };
                if end {
                    l.from = moved;
                } else {
                    l.to = moved;
                }
            }
        };
        for road in g.roads.iter_mut() {
            road.lanes.iter_mut().for_each(trim);
        }
        g.landing_road.iter_mut().for_each(trim);
    }
}
