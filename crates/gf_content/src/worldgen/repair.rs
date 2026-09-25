//! Pipeline step 13 (§3.2): reachability and repair. A tile is passable when it is land and less
//! than half covered by obstacles (sampled on the builder's 0.5 u cover grid). A flood from the
//! Landing must reach every POI, camp and the gate. Each target it misses, in site order, gets the
//! cheapest path (blocked tiles cost 50): the obstacles on it are removed with the decor that
//! dresses them, and pits on it become `Bridge`. At most 3 rounds; every carve counts in
//! `MapLayout.repairs` (the shipped templates must need none).

use super::Gen;
use super::compose::Built;
use super::tiles::{self, around};
use crate::procgen::{CELL, extent, sd};
use crate::schema::*;
use gf_core::movement::Obstacle;
use glam::Vec2;
use std::cmp::Reverse;
use std::collections::BinaryHeap;

/// Cost of stepping onto a blocked tile or a pit while carving.
const BLOCKED: u32 = 50;

/// Per tile: is at least half of it covered by obstacles?
fn blocked(t: &TileGrid, obstacles: &[Obstacle]) -> Vec<bool> {
    let per = (t.size / CELL).round() as usize;
    let (cw, ch) = (t.w as usize * per, t.h as usize * per);
    let mut cell = vec![false; cw * ch];
    for o in obstacles {
        let (c, e) = extent(o);
        let lo = ((c - e - t.origin) / CELL).floor().max(Vec2::ZERO);
        let hi = ((c + e - t.origin) / CELL).ceil();
        let (x0, y0) = (lo.x as usize, lo.y as usize);
        let (x1, y1) = ((hi.x.max(0.0) as usize).min(cw), (hi.y.max(0.0) as usize).min(ch));
        for y in y0..y1 {
            for x in x0..x1 {
                let p = t.origin + (Vec2::new(x as f32, y as f32) + Vec2::splat(0.5)) * CELL;
                if sd(o, p) <= 0.0 {
                    cell[y * cw + x] = true;
                }
            }
        }
    }
    let mut out = vec![false; t.kind.len()];
    for (i, b) in out.iter_mut().enumerate() {
        let (tx, ty) = (i % t.w as usize, i / t.w as usize);
        let n = (0..per)
            .flat_map(|dy| (0..per).map(move |dx| (tx * per + dx, ty * per + dy)))
            .filter(|&(x, y)| cell[y * cw + x])
            .count();
        *b = n * 2 >= per * per;
    }
    out
}

/// The cheapest tile path from `start` to `goal` (4-neighbour; passable tiles cost 1, blocked
/// tiles and inland pits [`BLOCKED`]); ties settle on the lower tile index.
fn cheapest(t: &TileGrid, blocked: &[bool], start: usize, goal: usize) -> Vec<usize> {
    let n = t.kind.len();
    let mut dist = vec![u32::MAX; n];
    let mut prev = vec![usize::MAX; n];
    let mut heap = BinaryHeap::from([Reverse((0u32, start))]);
    dist[start] = 0;
    while let Some(Reverse((d, i))) = heap.pop() {
        if d > dist[i] {
            continue;
        }
        if i == goal {
            break;
        }
        for j in around(t, i) {
            if tiles::on_rim(t, j) {
                continue;
            }
            let step = if t.kind[j].is_land() && !blocked[j] { 1 } else { BLOCKED };
            let alt = d + step;
            if alt < dist[j] {
                dist[j] = alt;
                prev[j] = i;
                heap.push(Reverse((alt, j)));
            }
        }
    }
    let mut path = Vec::new();
    let mut i = goal;
    while i != usize::MAX && dist[goal] != u32::MAX {
        path.push(i);
        if i == start {
            break;
        }
        i = prev[i];
    }
    path.reverse();
    path
}

/// Clear the tiles of `path`: pits become bridges, and every obstacle overlapping a blocked tile
/// goes, together with the decor dressing it (and the decor's other obstacles).
fn carve(g: &mut Gen, built: &mut Built, path: &[usize], blocked: &[bool]) {
    let t = &mut g.tiles;
    let hs = Vec2::splat(t.size * 0.5);
    let mut boxes = Vec::new();
    for &i in path {
        if t.kind[i].is_pit() {
            t.kind[i] = TileKind::Bridge;
        }
        if blocked[i] {
            let w = t.w as usize;
            boxes.push(t.center((i % w) as u16, (i / w) as u16));
        }
    }
    let b = &mut built.builder;
    let centre = |o: &Obstacle| extent(o).0;
    let hit: Vec<bool> = b
        .obstacles
        .iter()
        .map(|o| {
            let (c, e) = extent(o);
            boxes.iter().any(|p| ((c - *p).abs() - e - hs).max_element() < 0.0)
        })
        .collect();
    let gone_decor: Vec<bool> = b
        .decor
        .iter()
        .map(|d| d.is_solid() && b.obstacles.iter().zip(&hit).any(|(o, h)| *h && d.covers(centre(o))))
        .collect();
    let keep_obstacle: Vec<bool> = b
        .obstacles
        .iter()
        .zip(&hit)
        .map(|(o, h)| !*h && !b.decor.iter().zip(&gone_decor).any(|(d, gone)| *gone && d.covers(centre(o))))
        .collect();
    let mut k = keep_obstacle.iter();
    b.obstacles.retain(|_| *k.next().unwrap_or(&true));
    let mut k = gone_decor.iter();
    b.decor.retain(|_| !*k.next().unwrap_or(&false));
}

pub(crate) fn run(g: &mut Gen, built: &mut Built, camps: &[CampSite]) -> u8 {
    let mut repairs = 0u8;
    let start = tiles::tile_at(&g.tiles, g.landing);
    let mut targets: Vec<usize> = g.pois.iter().map(|p| tiles::tile_at(&g.tiles, p.site.at)).collect();
    targets.extend(camps.iter().map(|c| tiles::tile_at(&g.tiles, c.at)));
    let survey = |g: &Gen, built: &Built| {
        let blocked = blocked(&g.tiles, &built.builder.obstacles);
        let t = &g.tiles;
        let reach = tiles::flood(t, start, |j| t.kind[j].is_land() && !blocked[j]);
        (blocked, reach)
    };
    for _round in 0..3 {
        let mut carved = false;
        let (mut blocked, mut reach) = survey(g, built);
        for &goal in &targets {
            if reach[goal] {
                continue;
            }
            let path = cheapest(&g.tiles, &blocked, start, goal);
            carve(g, built, &path, &blocked);
            repairs = repairs.saturating_add(1);
            carved = true;
            (blocked, reach) = survey(g, built);
        }
        if !carved {
            break;
        }
    }
    repairs
}
