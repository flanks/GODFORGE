//! Pipeline step 11 (§3.2): dormant enemy camps. Land is rejection-sampled for one camp per
//! `camps.per_area` u² of land: at least 35 u from the Landing, clear of every POI clearing by
//! 20 u (and of its centre by the same), 6 u off the roads, spread apart and on open floor. Each
//! camp's pack comes from its region theme's `camp_pool` (else the biome swarm), with
//! `camps.elite_chance` of an elite leader and a shard pile to drop when cleared.

use super::tiles;
use super::{Gen, HUB_R};
use crate::procgen::{Builder, point_seg, qv};
use crate::schema::*;
use glam::Vec2;

/// Camps keep this far from the Landing.
const FROM_LANDING: f32 = 35.0;
/// ... and from each POI (centre, and clearing edge).
const FROM_POI: f32 = 20.0;
/// ... and from each road's edge.
const OFF_ROAD: f32 = 6.0;
/// ... and from each other.
const APART: f32 = 26.0;
/// Open floor a camp needs around its centre.
const CLEAR: f32 = 3.0;

pub(crate) fn place(g: &Gen, b: &Builder) -> Vec<CampSite> {
    let mut rng = g.root.fork(1).fork(6);
    let t = &g.tiles;
    let land = t.kind.iter().filter(|k| k.is_land()).count() as f32 * t.size * t.size;
    let want = (land / g.x.camps.per_area.max(100.0)).round() as usize;
    let lanes = g.lanes();
    let biome = g.biome_def().cloned();
    let swarm = biome.as_ref().map_or_else(Vec::new, |b| b.swarm.clone());
    let elites = biome.as_ref().map_or_else(Vec::new, |b| b.elites.clone());
    let pick = |rng: &mut gf_core::rng::GfRng, pool: &[WeightedKey]| {
        let usable: Vec<(u16, f32)> =
            pool.iter().filter_map(|w| g.db.enemies.id(&w.key).map(|id| (id, w.weight.max(0.0)))).collect();
        let weights: Vec<f32> = usable.iter().map(|u| u.1).collect();
        rng.weighted_index(&weights).map(|i| usable[i].0)
    };
    let (w, h) = (t.w as u32, t.h as u32);
    let c = &g.x.camps;
    let mut out: Vec<CampSite> = Vec::new();
    let mut tries = 0;
    while out.len() < want && tries < want * 60 {
        tries += 1;
        let (x, y) = (rng.range_u32(0, w) as u16, rng.range_u32(0, h) as u16);
        let jitter = Vec2::new(rng.range_f32(-1.5, 1.5), rng.range_f32(-1.5, 1.5));
        let at = qv(t.center(x, y) + jitter);
        let i = tiles::tile_at(t, at);
        let ok = t.kind[i] == TileKind::Ground
            && tiles::land_box(t, at, Vec2::splat(CLEAR + 1.0))
            && at.distance(g.landing) >= FROM_LANDING
            && g.pois.iter().all(|p| at.distance(p.site.at) >= FROM_POI.max(p.plaza + FROM_POI * 0.6))
            && g.regions.iter().all(|r| r.landmark.is_none() || at.distance(r.site) >= HUB_R + 8.0)
            && lanes.iter().all(|l| point_seg(at, l.from, l.to) >= l.width * 0.5 + OFF_ROAD)
            && out.iter().all(|o| o.at.distance(at) >= APART)
            && b.clearance(at, CLEAR) >= CLEAR;
        if !ok {
            continue;
        }
        let region = t.region[i] as usize;
        let theme = g.x.themes.get(g.regions[region].theme as usize);
        let pool = theme.filter(|t| !t.camp_pool.is_empty()).map_or(&swarm[..], |t| &t.camp_pool[..]);
        let Some(enemy) = pick(&mut rng, pool) else { continue };
        let count = rng.range_u32(c.pack.0.max(1) as u32, c.pack.1.max(c.pack.0.max(1)) as u32 + 1) as u8;
        let elite = if rng.chance(c.elite_chance) { pick(&mut rng, &elites) } else { None };
        let shards = rng.range_u32(c.shards.0 as u32, c.shards.1.max(c.shards.0) as u32 + 1) as u16;
        out.push(CampSite { at, enemy, count, elite, shards });
    }
    out
}
