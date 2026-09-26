//! Top-down layout previews of generated arenas and biome maps, so level design can be judged by
//! looking:
//!
//! ```text
//! gf-content preview-room <template_key> <seed> <out.png> [--scale PX]
//! gf-content preview-sheet <out.png> [--biome KEY] [--templates a,b] [--kinds combat,elite,anvil,treasure]
//!                          [--seeds N] [--seed0 S] [--scale PX]
//! gf-content layout-stats [--biome KEY] [--seeds N]
//! gf-content layout-stats --maps [--biome KEY] [--seeds N]
//! ```
//!
//! A pure software raster (signed-distance shapes with 1 px anti-aliasing and a 5×7 bitmap font),
//! drawn in a readable map language rather than the game's look: obstacles in ink, decor by family,
//! lanes as pale stripes, spawn green, plaza gold, gates cyan, landmarks labelled. Biome maps add
//! their tiles (region colours, roads, plazas, bridges, liquid, void, land cut off from the
//! Landing in red), cliffs and region borders, passes, POIs by kind and camps.

use gf_content::ContentDb;
use gf_content::procgen;
use gf_content::schema::*;
use gf_core::movement::Obstacle;
use gf_core::poi::PoiKind;
use glam::Vec2;
use std::collections::BTreeMap;
use std::path::Path;
use std::time::Instant;

// ───────────────────────────── raster ─────────────────────────────

#[derive(Clone, Copy, Debug)]
struct Rgb(f32, f32, f32);

impl Rgb {
    fn mix(self, o: Rgb, t: f32) -> Rgb {
        Rgb(self.0 + (o.0 - self.0) * t, self.1 + (o.1 - self.1) * t, self.2 + (o.2 - self.2) * t)
    }
    fn scale(self, k: f32) -> Rgb {
        Rgb((self.0 * k).min(1.0), (self.1 * k).min(1.0), (self.2 * k).min(1.0))
    }
}

fn hex(s: &str) -> Rgb {
    let s = s.trim_start_matches('#');
    let v = u32::from_str_radix(s, 16).unwrap_or(0x808080);
    Rgb(((v >> 16) & 255) as f32 / 255.0, ((v >> 8) & 255) as f32 / 255.0, (v & 255) as f32 / 255.0)
}

const INK: Rgb = Rgb(0.06, 0.05, 0.05);
const WHITE: Rgb = Rgb(1.0, 1.0, 1.0);
const TEXT: Rgb = Rgb(0.93, 0.90, 0.84);
const DIM: Rgb = Rgb(0.62, 0.60, 0.56);

struct Canvas {
    w: usize,
    h: usize,
    px: Vec<[f32; 3]>,
}

impl Canvas {
    fn new(w: usize, h: usize, bg: Rgb) -> Self {
        Self { w, h, px: vec![[bg.0, bg.1, bg.2]; w * h] }
    }

    fn blend(&mut self, x: i64, y: i64, c: Rgb, a: f32) {
        if x < 0 || y < 0 || x >= self.w as i64 || y >= self.h as i64 || a <= 0.0 {
            return;
        }
        let p = &mut self.px[y as usize * self.w + x as usize];
        let a = a.min(1.0);
        p[0] += (c.0 - p[0]) * a;
        p[1] += (c.1 - p[1]) * a;
        p[2] += (c.2 - p[2]) * a;
    }

    fn rect(&mut self, x0: i64, y0: i64, x1: i64, y1: i64, c: Rgb, a: f32) {
        for y in y0.max(0)..y1.min(self.h as i64) {
            for x in x0.max(0)..x1.min(self.w as i64) {
                self.blend(x, y, c, a);
            }
        }
    }

    /// 5×7 bitmap text at integer `scale`; returns the advance width in pixels.
    fn text(&mut self, x: i64, y: i64, s: &str, scale: i64, c: Rgb) -> i64 {
        let mut cx = x;
        for ch in s.chars() {
            let g = glyph(ch.to_ascii_uppercase());
            for (row, bits) in g.iter().enumerate() {
                for col in 0..5 {
                    if bits & (0x10 >> col) != 0 {
                        let px = cx + col * scale;
                        let py = y + row as i64 * scale;
                        self.rect(px, py, px + scale, py + scale, c, 1.0);
                    }
                }
            }
            cx += 6 * scale;
        }
        cx - x
    }

    /// Text with a dark halo so it reads over any map colour.
    fn label(&mut self, x: i64, y: i64, s: &str, scale: i64, c: Rgb) {
        for (dx, dy) in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)] {
            self.text(x + dx, y + dy, s, scale, INK);
        }
        self.text(x, y, s, scale, c);
    }

    fn blit(&mut self, o: &Canvas, x: usize, y: usize) {
        for row in 0..o.h {
            if y + row >= self.h {
                break;
            }
            let n = o.w.min(self.w.saturating_sub(x));
            let dst = (y + row) * self.w + x;
            self.px[dst..dst + n].copy_from_slice(&o.px[row * o.w..row * o.w + n]);
        }
    }

    fn save_png(&self, path: &Path) -> Result<(), String> {
        if let Some(parent) = path.parent()
            && !parent.as_os_str().is_empty()
        {
            std::fs::create_dir_all(parent).map_err(|e| format!("{}: {e}", parent.display()))?;
        }
        let file = std::fs::File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let mut enc = png::Encoder::new(std::io::BufWriter::new(file), self.w as u32, self.h as u32);
        enc.set_color(png::ColorType::Rgb);
        enc.set_depth(png::BitDepth::Eight);
        let mut writer = enc.write_header().map_err(|e| e.to_string())?;
        let bytes: Vec<u8> = self.px.iter().flat_map(|p| p.map(|v| (v.clamp(0.0, 1.0) * 255.0 + 0.5) as u8)).collect();
        writer.write_image_data(&bytes).map_err(|e| e.to_string())?;
        writer.finish().map_err(|e| e.to_string())
    }
}

fn glyph(c: char) -> [u8; 7] {
    match c {
        '0' => [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
        '1' => [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
        '2' => [0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F],
        '3' => [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
        '4' => [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
        '5' => [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
        '6' => [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
        '7' => [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
        '8' => [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
        '9' => [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
        'A' => [0x0E, 0x11, 0x11, 0x11, 0x1F, 0x11, 0x11],
        'B' => [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
        'C' => [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
        'D' => [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
        'E' => [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
        'F' => [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
        'G' => [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
        'H' => [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
        'I' => [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
        'J' => [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
        'K' => [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
        'L' => [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
        'M' => [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
        'N' => [0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11],
        'O' => [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
        'P' => [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
        'Q' => [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
        'R' => [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
        'S' => [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
        'T' => [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
        'U' => [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
        'V' => [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
        'W' => [0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A],
        'X' => [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
        'Y' => [0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04],
        'Z' => [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
        '.' => [0, 0, 0, 0, 0, 0x0C, 0x0C],
        ',' => [0, 0, 0, 0, 0x0C, 0x04, 0x08],
        ':' => [0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0],
        '-' => [0, 0, 0, 0x1F, 0, 0, 0],
        '_' => [0, 0, 0, 0, 0, 0, 0x1F],
        '~' => [0, 0, 0x08, 0x15, 0x02, 0, 0],
        '/' => [0, 0x01, 0x02, 0x04, 0x08, 0x10, 0],
        '%' => [0x18, 0x19, 0x02, 0x04, 0x08, 0x13, 0x03],
        '(' => [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
        ')' => [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
        '#' => [0x0A, 0x0A, 0x1F, 0x0A, 0x1F, 0x0A, 0x0A],
        '+' => [0, 0x04, 0x04, 0x1F, 0x04, 0x04, 0],
        '=' => [0, 0, 0x1F, 0, 0x1F, 0, 0],
        '<' => [0x02, 0x04, 0x08, 0x10, 0x08, 0x04, 0x02],
        '>' => [0x08, 0x04, 0x02, 0x01, 0x02, 0x04, 0x08],
        '!' => [0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04],
        '?' => [0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04],
        '*' => [0, 0x04, 0x15, 0x0E, 0x15, 0x04, 0],
        '\'' => [0x04, 0x04, 0, 0, 0, 0, 0],
        _ => [0; 7],
    }
}

// ───────────────────────────── signed distance shapes ─────────────────────────────

fn sd_circle(p: Vec2, c: Vec2, r: f32) -> f32 {
    p.distance(c) - r
}

fn sd_box(p: Vec2, c: Vec2, h: Vec2) -> f32 {
    let d = (p - c).abs() - h;
    d.max(Vec2::ZERO).length() + d.x.max(d.y).min(0.0)
}

fn sd_segment(p: Vec2, a: Vec2, b: Vec2, r: f32) -> f32 {
    let ab = b - a;
    let t = ((p - a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
    p.distance(a + ab * t) - r
}

/// World → pixel mapping of one room view.
#[derive(Clone, Copy)]
struct View {
    cx: f32,
    cy: f32,
    s: f32,
}

impl View {
    fn px(&self, p: Vec2) -> Vec2 {
        Vec2::new(self.cx + p.x * self.s, self.cy - p.y * self.s)
    }
    fn world(&self, x: f32, y: f32) -> Vec2 {
        Vec2::new((x - self.cx) / self.s, (self.cy - y) / self.s)
    }
}

/// Fill the region where `sdf` (world units) is negative, anti-aliased, inside the world bbox.
fn fill(cv: &mut Canvas, v: &View, min: Vec2, max: Vec2, c: Rgb, a: f32, sdf: impl Fn(Vec2) -> f32) {
    let p0 = v.px(Vec2::new(min.x, max.y));
    let p1 = v.px(Vec2::new(max.x, min.y));
    let (x0, y0) = ((p0.x - 2.0).floor() as i64, (p0.y - 2.0).floor() as i64);
    let (x1, y1) = ((p1.x + 2.0).ceil() as i64, (p1.y + 2.0).ceil() as i64);
    for y in y0.max(0)..y1.min(cv.h as i64) {
        for x in x0.max(0)..x1.min(cv.w as i64) {
            let d = sdf(v.world(x as f32 + 0.5, y as f32 + 0.5)) * v.s;
            let cov = (0.5 - d).clamp(0.0, 1.0);
            if cov > 0.0 {
                cv.blend(x, y, c, a * cov);
            }
        }
    }
}

fn circle(cv: &mut Canvas, v: &View, c: Vec2, r: f32, col: Rgb, a: f32) {
    fill(cv, v, c - Vec2::splat(r), c + Vec2::splat(r), col, a, |p| sd_circle(p, c, r));
}

fn ring(cv: &mut Canvas, v: &View, c: Vec2, r: f32, w: f32, col: Rgb, a: f32) {
    let e = r + w;
    fill(cv, v, c - Vec2::splat(e), c + Vec2::splat(e), col, a, |p| (p.distance(c) - r).abs() - w * 0.5);
}

fn boxf(cv: &mut Canvas, v: &View, c: Vec2, h: Vec2, col: Rgb, a: f32) {
    fill(cv, v, c - h, c + h, col, a, |p| sd_box(p, c, h));
}

fn box_outline(cv: &mut Canvas, v: &View, c: Vec2, h: Vec2, w: f32, col: Rgb, a: f32) {
    let e = h + Vec2::splat(w);
    fill(cv, v, c - e, c + e, col, a, |p| sd_box(p, c, h).abs() - w * 0.5);
}

fn segment(cv: &mut Canvas, v: &View, a: Vec2, b: Vec2, r: f32, col: Rgb, al: f32) {
    let min = a.min(b) - Vec2::splat(r);
    let max = a.max(b) + Vec2::splat(r);
    fill(cv, v, min, max, col, al, |p| sd_segment(p, a, b, r));
}

/// Dashed line (dash and gap in world units).
fn dashed(cv: &mut Canvas, v: &View, a: Vec2, b: Vec2, r: f32, dash: f32, col: Rgb, al: f32) {
    let len = a.distance(b);
    if len < 1e-3 {
        return;
    }
    let dir = (b - a) / len;
    let mut t = 0.0;
    while t < len {
        let e = (t + dash).min(len);
        segment(cv, v, a + dir * t, a + dir * e, r, col, al);
        t += dash * 2.0;
    }
}

/// Small facing tick from `c` toward `rot`.
fn facing(cv: &mut Canvas, v: &View, c: Vec2, r: f32, rot: Rot16, col: Rgb) {
    let d = rot16_dir(rot);
    segment(cv, v, c, c + d * (r + 0.9), 0.16, col, 1.0);
}

fn hash(i: usize, k: u32) -> f32 {
    let mut h = (i as u32).wrapping_mul(0x9E37_79B9) ^ k.wrapping_mul(0x85EB_CA6B);
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    (h & 0xffff) as f32 / 65535.0
}

// ───────────────────────────── the map language ─────────────────────────────

struct Palette {
    ground: Rgb,
    accent: Rgb,
    deep: Rgb,
    liquid: Rgb,
    cover: Rgb,
    gods: Vec<Rgb>,
}

fn palette(db: &ContentDb, room: &RoomDef) -> Palette {
    let (ground, accent, deep) = db
        .biomes
        .by_key(&room.biome)
        .map(|b| (hex(&b.palette[0]), hex(&b.palette[1]), hex(&b.palette[2])))
        .unwrap_or((hex("#2B1B15"), hex("#FF8A2A"), hex("#140D0A")));
    let (liquid, cover) = match room.biome.as_str() {
        "verdant_ruin" => (hex("#2E7F8C"), hex("#4F8F3A")),
        "hollow_spire" => (hex("#1A2266"), hex("#8C87C9")),
        "the_unmaking" => (hex("#B02CD6"), hex("#5A2A7A")),
        _ => (hex("#FF6A1A"), hex("#6B635C")),
    };
    Palette { ground, accent, deep, liquid, cover, gods: db.gods.iter().map(|g| hex(&g.color)).collect() }
}

fn god_color(p: &Palette, god: u8) -> Rgb {
    p.gods.get(god as usize).copied().unwrap_or(Rgb(0.8, 0.2, 0.2))
}

fn district_color(k: DistrictKind) -> Rgb {
    match k {
        DistrictKind::Plaza => hex("#FFD36B"),
        DistrictKind::Field => hex("#9C9C9C"),
        DistrictKind::ColonnadeCourt => hex("#E8DCC0"),
        DistrictKind::ForgeHall => hex("#FF7A3A"),
        DistrictKind::SlagChannel => hex("#FF4A1A"),
        DistrictKind::CrucibleYard => hex("#FFB02A"),
        DistrictKind::Cloister => hex("#9FE0A0"),
        DistrictKind::RootTerrace => hex("#6FBF5A"),
        DistrictKind::ReflectingPool => hex("#6FD8E8"),
        DistrictKind::FallenGiant => hex("#C79A5A"),
        DistrictKind::BrokenStair => hex("#B8C8FF"),
        DistrictKind::CrystalGarden => hex("#9FF0FF"),
        DistrictKind::DebrisRing => hex("#D0B8FF"),
        DistrictKind::VoidChasm => hex("#7A6BFF"),
        DistrictKind::ShatteredIslands => hex("#E07AFF"),
        DistrictKind::RiftField => hex("#FF5AD0"),
        DistrictKind::InvertedNave => hex("#C0A0FF"),
    }
}

fn rim_color(e: RimEdge, p: &Palette) -> Rgb {
    match e {
        RimEdge::Wall => hex("#5A5048"),
        RimEdge::BrokenWall => hex("#4A423C"),
        RimEdge::Colonnade => hex("#CFC4B0"),
        RimEdge::Balustrade => hex("#9A9080"),
        RimEdge::Cliff => hex("#3A2E28"),
        RimEdge::Thicket => hex("#1F3A22"),
        RimEdge::Terrace => hex("#7A6E62"),
        RimEdge::Shattered => p.deep.mix(p.accent, 0.35),
        RimEdge::Open => p.accent,
    }
}

/// Short legend name and swatch colour for a decor variant.
fn decor_key(d: &Decor, p: &Palette) -> (&'static str, Rgb) {
    match d {
        Decor::LavaCrack { .. } => ("FISSURE", p.accent.scale(1.2)),
        Decor::BrokenAnvil { .. } => ("BROKEN ANVIL", hex("#3C3C44")),
        Decor::Brazier { .. } => ("BRAZIER", hex("#FFB040")),
        Decor::Pillar { .. } => ("PILLAR", hex("#E6DDCB")),
        Decor::Wall { style, .. } => match style {
            WallStyle::Ruin => ("WALL", hex("#A89A88")),
            WallStyle::Parapet => ("PARAPET", hex("#C9BFAE")),
            WallStyle::Plinth => ("PLINTH", hex("#BFAF94")),
            WallStyle::Hedge => ("ROOT WALL", hex("#4F7A45")),
            WallStyle::Monolith => ("MONOLITH", hex("#8A5BD6")),
            WallStyle::Forge => ("FORGE WALL", hex("#7A6456")),
        },
        Decor::Boulder { .. } => ("BOULDER", hex("#8C7F73")),
        Decor::Statue { .. } => ("STATUE *", hex("#F0C850")),
        Decor::ColossusHead { .. } => ("COLOSSUS HEAD *", hex("#C08850")),
        Decor::FallenColumn { .. } => ("FALLEN COLUMN", hex("#D6CCB8")),
        Decor::GreatAnvil { .. } => ("GREAT ANVIL *", hex("#55555F")),
        Decor::Crucible { .. } => ("CRUCIBLE *", hex("#FF9A30")),
        Decor::GreatBrazier { .. } => ("GREAT BRAZIER *", hex("#FFCF50")),
        Decor::SealedGate { .. } => ("SEALED GATE *", hex("#3FA08A")),
        Decor::Arch { .. } => ("ARCH", hex("#E0C89A")),
        Decor::Tree { .. } => ("TREE", hex("#7A5232")),
        Decor::FallenTree { .. } => ("FALLEN TREE", hex("#8A6038")),
        Decor::Crystal { .. } => ("CRYSTAL", hex("#A8F0FF")),
        Decor::SpiralStair { .. } => ("SPIRAL STAIR *", hex("#B8C4E8")),
        Decor::InvertedColumn { .. } => ("INVERTED COLUMN", hex("#B89AE8")),
        Decor::Rift { .. } => ("RIFT", hex("#FF4AD8")),
        Decor::Channel { .. } => ("CHANNEL", p.liquid),
        Decor::FallenWeapon { .. } => ("FALLEN WEAPON *", hex("#C9B98E")),
        Decor::Bridge { .. } => ("BRIDGE", hex("#D8C8A8")),
        Decor::Pool { .. } => ("POOL", hex("#4A9AC8")),
        Decor::Paving { .. } => ("PAVING", p.ground.scale(3.2).mix(WHITE, 0.15)),
        Decor::FloorInlay { .. } => ("FLOOR INLAY", hex("#E8C060")),
        Decor::Overgrowth { .. } => ("OVERGROWTH", p.cover),
        Decor::Roots { .. } => ("ROOTS", hex("#5A6A2E")),
        Decor::Rubble { .. } => ("RUBBLE", hex("#9A9088")),
        Decor::Clutter { .. } => ("CLUTTER", hex("#D8A868")),
        Decor::Banner { .. } => ("BANNER", hex("#D04040")),
        Decor::Chains { .. } => ("CHAINS", hex("#6A6A74")),
        Decor::Debris { .. } => ("FLOATING DEBRIS", hex("#B0A8C8")),
    }
}

/// Draw order: floor-level decals first, then solids, then props and markers.
fn layer(d: &Decor) -> u8 {
    match d {
        Decor::Paving { .. } => 0,
        Decor::Overgrowth { .. } | Decor::Pool { .. } | Decor::FloorInlay { .. } => 1,
        Decor::LavaCrack { .. } | Decor::Roots { .. } | Decor::Channel { .. } => 2,
        Decor::Bridge { .. } => 3,
        Decor::Rubble { .. } | Decor::Clutter { .. } | Decor::BrokenAnvil { .. } => 4,
        d if d.is_solid() => 5,
        _ => 6,
    }
}

fn draw_decor(cv: &mut Canvas, v: &View, d: &Decor, p: &Palette, i: usize) {
    let (_, col) = decor_key(d, p);
    let ink = INK;
    match *d {
        Decor::Paving { at, half, variant } => {
            boxf(cv, v, at, half, col, 0.55);
            // Joint lines.
            let step = if variant == 2 { 0.75 } else { 1.5 };
            let mut x = at.x - half.x + step;
            while x < at.x + half.x {
                segment(cv, v, Vec2::new(x, at.y - half.y), Vec2::new(x, at.y + half.y), 0.03, ink, 0.18);
                x += step;
            }
            let mut y = at.y - half.y + step;
            while y < at.y + half.y {
                segment(cv, v, Vec2::new(at.x - half.x, y), Vec2::new(at.x + half.x, y), 0.03, ink, 0.18);
                y += step;
            }
        }
        Decor::Overgrowth { at, radius, .. } => {
            circle(cv, v, at, radius, col, 0.22);
            for k in 0..6 {
                let o = Vec2::new(hash(i, k) - 0.5, hash(i, k + 7) - 0.5) * radius * 1.4;
                circle(cv, v, at + o, radius * 0.3, col.scale(1.2), 0.22);
            }
        }
        Decor::Pool { at, half } => {
            fill(cv, v, at - half - Vec2::splat(0.5), at + half + Vec2::splat(0.5), hex("#8A8070"), 1.0, |q| {
                sd_box(q, at, half - Vec2::splat(0.6)) - 0.9
            });
            fill(cv, v, at - half, at + half, col, 1.0, |q| sd_box(q, at, half - Vec2::splat(0.9)) - 0.6);
        }
        Decor::FloorInlay { at, radius, rot, variant, god } => {
            let c = match variant {
                0 => hex("#F0C860"),
                1 => p.accent,
                2 => hex("#DDE6FF"),
                3 => god_color(p, god),
                _ => hex("#E050FF"),
            };
            ring(cv, v, at, radius, 0.3, c, 0.9);
            ring(cv, v, at, radius * 0.62, 0.18, c, 0.7);
            for k in 0..8u8 {
                let dir = rot16_dir(rot.wrapping_add(k * 2));
                segment(cv, v, at + dir * radius * 0.62, at + dir * radius, 0.08, c, 0.7);
            }
        }
        Decor::LavaCrack { from, to, width } => {
            segment(cv, v, from, to, width * 1.6, col, 0.25);
            segment(cv, v, from, to, width * 0.5, col.mix(WHITE, 0.3), 1.0);
        }
        Decor::Roots { from, to, width } => {
            segment(cv, v, from, to, width * 0.5, col, 0.95);
            segment(cv, v, from, to, width * 0.12, hex("#9FF0A0"), 0.6);
        }
        Decor::Channel { from, to, width } => {
            segment(cv, v, from, to, width * 0.5 + 0.35, hex("#2A2420"), 1.0);
            segment(cv, v, from, to, width * 0.5, col, 1.0);
            segment(cv, v, from, to, width * 0.15, col.mix(WHITE, 0.45), 0.7);
        }
        Decor::Bridge { from, to, width } => {
            segment(cv, v, from, to, width * 0.5, col, 1.0);
            let side = (to - from).normalize_or(Vec2::Y).perp() * (width * 0.5);
            for s in [side, -side] {
                segment(cv, v, from + s, to + s, 0.14, hex("#6A5A48"), 1.0);
            }
        }
        Decor::Rubble { at, radius, .. } => {
            for k in 0..7 {
                let o = Vec2::new(hash(i, k) - 0.5, hash(i, k + 11) - 0.5) * radius * 1.8;
                circle(cv, v, at + o, 0.14 + 0.2 * hash(i, k + 23), col, 0.55);
            }
        }
        Decor::Clutter { at, radius, count, .. } => {
            for k in 0..count.max(1) as u32 {
                let o = Vec2::new(hash(i, k) - 0.5, hash(i, k + 13) - 0.5) * radius * 1.7;
                circle(cv, v, at + o, 0.28, col, 1.0);
                ring(cv, v, at + o, 0.28, 0.07, ink, 0.8);
            }
        }
        Decor::BrokenAnvil { at, scale } => {
            boxf(cv, v, at, Vec2::new(0.75, 0.35) * scale, col, 1.0);
            box_outline(cv, v, at, Vec2::new(0.75, 0.35) * scale, 0.08, p.accent, 0.7);
        }
        Decor::Pillar { at, radius, height } => {
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius, 0.14, ink, 1.0);
            if height < 2.5 {
                ring(cv, v, at, radius * 0.45, 0.1, ink, 0.6);
            }
        }
        Decor::Wall { at, half, style, .. } => {
            boxf(cv, v, at, half, col, 1.0);
            box_outline(cv, v, at, half, 0.14, ink, 1.0);
            if style == WallStyle::Forge {
                box_outline(cv, v, at, half * 0.55, 0.1, p.accent, 0.8);
            }
        }
        Decor::Boulder { at, radius, .. } => {
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius, 0.14, ink, 1.0);
            circle(cv, v, at + Vec2::new(-0.25, 0.25) * radius, radius * 0.35, col.scale(1.25), 0.6);
        }
        Decor::Statue { at, radius, rot, god, .. } => {
            circle(cv, v, at, radius, hex("#8A7E6A"), 1.0);
            circle(cv, v, at, radius * 0.62, col, 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
            ring(cv, v, at, radius * 0.62, 0.12, god_color(p, god), 1.0);
            facing(cv, v, at, radius, rot, ink);
        }
        Decor::ColossusHead { at, radius, rot, .. } => {
            circle(cv, v, at, radius * 1.25, col.scale(0.7), 0.5);
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
            facing(cv, v, at, radius, rot, ink);
        }
        Decor::FallenColumn { from, to, radius } => {
            segment(cv, v, from, to, radius, col, 1.0);
            fill(
                cv,
                v,
                from.min(to) - Vec2::splat(radius + 0.2),
                from.max(to) + Vec2::splat(radius + 0.2),
                ink,
                1.0,
                |q| sd_segment(q, from, to, radius).abs() - 0.07,
            );
            circle(cv, v, from, radius * 1.15, col.scale(0.85), 1.0);
            ring(cv, v, from, radius * 1.15, 0.12, ink, 1.0);
        }
        Decor::FallenTree { from, to, radius } => {
            circle(cv, v, from, radius * 2.0, hex("#5A4028"), 0.8);
            segment(cv, v, from, to, radius, col, 1.0);
            fill(
                cv,
                v,
                from.min(to) - Vec2::splat(radius + 0.2),
                from.max(to) + Vec2::splat(radius + 0.2),
                ink,
                1.0,
                |q| sd_segment(q, from, to, radius).abs() - 0.07,
            );
            circle(cv, v, to, radius * 1.6, p.cover, 0.35);
        }
        Decor::GreatAnvil { at, radius, rot } => {
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius, 0.2, p.accent, 1.0);
            let d = rot16_dir(rot);
            segment(cv, v, at - d * radius * 0.8, at + d * radius * 0.8, 0.12, p.accent, 1.0);
        }
        Decor::Crucible { at, radius } => {
            circle(cv, v, at, radius, p.accent.scale(1.1), 1.0);
            circle(cv, v, at, radius * 0.55, hex("#2A2020"), 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
            for k in 0..4u8 {
                let d = rot16_dir(k * 4 + 2);
                segment(cv, v, at + d * radius * 0.55, at + d * (radius + 0.8), 0.07, hex("#6A6A74"), 1.0);
            }
        }
        Decor::GreatBrazier { at, radius } => {
            circle(cv, v, at, radius + 1.5, col, 0.18);
            circle(cv, v, at, radius, hex("#8A6A3A"), 1.0);
            circle(cv, v, at, radius * 0.6, col, 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
        }
        Decor::Arch { from, to, pier, variant, .. } => {
            if variant == 0 {
                segment(cv, v, from, to, pier * 0.55, col.scale(0.8), 0.9);
            } else {
                dashed(cv, v, from, to, pier * 0.3, 0.5, col.scale(0.8), 0.9);
            }
            for p in [from, to] {
                boxf(cv, v, p, Vec2::splat(pier), col, 1.0);
                box_outline(cv, v, p, Vec2::splat(pier), 0.14, ink, 1.0);
            }
        }
        Decor::SealedGate { at, half, .. } => {
            boxf(cv, v, at, half, col, 1.0);
            box_outline(cv, v, at, half, 0.16, ink, 1.0);
            box_outline(cv, v, at, half * 0.6, 0.1, hex("#F0C860"), 1.0);
        }
        Decor::Tree { at, radius, .. } => {
            circle(cv, v, at, radius * 2.6, p.cover, 0.22);
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
        }
        Decor::Crystal { at, radius, rot, .. } => {
            circle(cv, v, at, radius, col.scale(0.8), 1.0);
            for k in 0..3u8 {
                let d = rot16_dir(rot.wrapping_add(k * 5));
                segment(cv, v, at, at + d * radius * 0.9, radius * 0.28, col, 1.0);
            }
            ring(cv, v, at, radius, 0.12, ink, 1.0);
        }
        Decor::SpiralStair { at, radius, rot, .. } => {
            circle(cv, v, at, radius, col, 1.0);
            ring(cv, v, at, radius * 0.7, 0.12, INK, 0.7);
            ring(cv, v, at, radius * 0.35, 0.12, INK, 0.7);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
            facing(cv, v, at, radius, rot, ink);
        }
        Decor::InvertedColumn { at, radius, .. } => {
            boxf(cv, v, at, Vec2::splat(radius * 1.05), col.scale(0.8), 1.0);
            circle(cv, v, at, radius * 0.7, col, 1.0);
            box_outline(cv, v, at, Vec2::splat(radius * 1.05), 0.12, ink, 1.0);
        }
        Decor::Rift { at, radius, rot, .. } => {
            circle(cv, v, at, radius + 1.0, col, 0.2);
            let d = rot16_dir(rot).perp();
            segment(cv, v, at - d * (radius + 0.6), at + d * (radius + 0.6), 0.28, col, 1.0);
            segment(cv, v, at - d * (radius + 0.3), at + d * (radius + 0.3), 0.1, WHITE, 1.0);
        }
        Decor::FallenWeapon { at, radius, height, rot, variant } => {
            // The impact crater, then the weapon lying back along its lean (length ~ its height).
            circle(cv, v, at, radius * 1.3, hex("#2A2420"), 0.6);
            circle(cv, v, at, radius, col.scale(0.75), 1.0);
            ring(cv, v, at, radius, 0.16, ink, 1.0);
            let d = rot16_dir(rot);
            let tip = at + d * (height * 0.45).max(radius + 1.0);
            let w = match variant % 5 {
                1 => 0.35,
                2 => 0.18,
                4 => 0.55,
                _ => 0.28,
            } * radius;
            segment(cv, v, at, tip, w, col, 1.0);
            let head = match variant % 5 {
                1 => 0.9,
                4 => 0.7,
                _ => 0.45,
            } * radius;
            circle(cv, v, tip, head, col.scale(1.1), 1.0);
            ring(cv, v, tip, head, 0.12, ink, 1.0);
        }
        Decor::Brazier { at } => {
            circle(cv, v, at, 1.2, col, 0.2);
            circle(cv, v, at, 0.42, col, 1.0);
            ring(cv, v, at, 0.42, 0.08, ink, 1.0);
        }
        Decor::Banner { at, rot, god, .. } => {
            let d = rot16_dir(rot).perp();
            segment(cv, v, at - d * 0.55, at + d * 0.55, 0.22, god_color(p, god), 1.0);
            segment(cv, v, at - d * 0.55, at + d * 0.55, 0.06, hex("#F0C860"), 1.0);
        }
        Decor::Chains { from, to, .. } => dashed(cv, v, from, to, 0.07, 0.3, col, 1.0),
        Decor::Debris { at, radius, .. } => {
            circle(cv, v, at + Vec2::new(0.4, -0.4), radius, INK, 0.25);
            circle(cv, v, at, radius, col, 0.85);
            ring(cv, v, at, radius, 0.07, ink, 0.8);
        }
    }
}

/// Human label for landmarks drawn next to them.
fn landmark_label(d: &Decor) -> Option<&'static str> {
    match d {
        Decor::Statue { .. } => Some("STATUE"),
        Decor::ColossusHead { .. } => Some("COLOSSUS"),
        Decor::GreatAnvil { .. } => Some("GREAT ANVIL"),
        Decor::Crucible { .. } => Some("CRUCIBLE"),
        Decor::GreatBrazier { .. } => Some("FORGE FIRE"),
        Decor::SealedGate { .. } => Some("SEALED GATE"),
        Decor::SpiralStair { .. } => Some("SPIRAL STAIR"),
        Decor::FallenWeapon { .. } => Some("FALLEN ARMS"),
        _ => None,
    }
}

/// Label of a grand monument (a map's skyline).
fn mark_name(m: MapMark) -> String {
    let s = match m {
        MapMark::GreatBrazier => "ForgeFire".to_string(),
        MapMark::FallenWeapon => "FallenArms".to_string(),
        other => format!("{other:?}"),
    };
    s.chars().fold(String::new(), |mut out, c| {
        if c.is_ascii_uppercase() && !out.is_empty() && !out.ends_with(' ') {
            out.push(' ');
        }
        out.push(c.to_ascii_uppercase());
        out
    })
}

fn district_name(k: DistrictKind) -> String {
    format!("{k:?}").chars().fold(String::new(), |mut s, c| {
        if c.is_ascii_uppercase() && !s.is_empty() {
            s.push(' ');
        }
        s.push(c.to_ascii_uppercase());
        s
    })
}

/// Border band around the arena (outside the playable rectangle).
const PAD: f32 = 4.0;

/// Decor floor layers, then obstacles, then solids and props. Undressed obstacles are flagged
/// magenta: every generated obstacle should carry a solid decor.
fn draw_layout(cv: &mut Canvas, v: &View, room: &RoomDef, p: &Palette) {
    let mut order: Vec<usize> = (0..room.decor.len()).collect();
    order.sort_by_key(|&i| layer(&room.decor[i]));
    let (floor_decor, rest): (Vec<usize>, Vec<usize>) = order.iter().partition(|&&i| layer(&room.decor[i]) < 4);
    for &i in &floor_decor {
        draw_decor(cv, v, &room.decor[i], p, i);
    }
    let solid: Vec<&Decor> = room.decor.iter().filter(|d| d.is_solid()).collect();
    for o in &room.obstacles {
        let c = match *o {
            Obstacle::Circle { center, .. } | Obstacle::Box { center, .. } => center,
        };
        let col = if solid.iter().any(|d| d.covers(c)) { hex("#3A322C") } else { hex("#FF00FF") };
        match *o {
            Obstacle::Circle { center, radius } => circle(cv, v, center, radius, col, 1.0),
            Obstacle::Box { center, half } => boxf(cv, v, center, half, col, 1.0),
        }
    }
    for &i in &rest {
        draw_decor(cv, v, &room.decor[i], p, i);
    }
}

/// Render one room into a new canvas (map only, no legend).
fn render_room(db: &ContentDb, room: &RoomDef, s: f32, labels: bool) -> Canvas {
    let p = palette(db, room);
    let half = room.half_extents;
    let w = ((half.x + PAD) * 2.0 * s).ceil() as usize;
    let h = ((half.y + PAD) * 2.0 * s).ceil() as usize;
    let mut cv = Canvas::new(w, h, p.deep.scale(0.8));
    let v = View { cx: w as f32 * 0.5, cy: h as f32 * 0.5, s };
    // Rim bands.
    let band = 1.6;
    let rim = room.rim;
    let sides = [
        (rim.north, Vec2::new(0.0, half.y + band * 0.5), Vec2::new(half.x + band, band * 0.5)),
        (rim.south, Vec2::new(0.0, -half.y - band * 0.5), Vec2::new(half.x + band, band * 0.5)),
        (rim.west, Vec2::new(-half.x - band * 0.5, 0.0), Vec2::new(band * 0.5, half.y)),
        (rim.east, Vec2::new(half.x + band * 0.5, 0.0), Vec2::new(band * 0.5, half.y)),
    ];
    for (edge, c, hb) in sides {
        let col = rim_color(edge, &p);
        match edge {
            RimEdge::Open => boxf(&mut cv, &v, c, hb * Vec2::new(1.0, 0.35), col, 0.9),
            RimEdge::Colonnade | RimEdge::Balustrade => {
                boxf(&mut cv, &v, c, hb * 0.5, col.scale(0.7), 1.0);
                let along_x = hb.x > hb.y;
                let n = ((if along_x { hb.x } else { hb.y }) / 1.6) as i32;
                for k in -n..=n {
                    let o = k as f32 * 1.6;
                    let q = if along_x { c + Vec2::new(o, 0.0) } else { c + Vec2::new(0.0, o) };
                    circle(&mut cv, &v, q, if edge == RimEdge::Colonnade { 0.55 } else { 0.3 }, col, 1.0);
                }
            }
            RimEdge::Shattered => {
                for k in 0..40 {
                    let o = Vec2::new(hash(k, 3) * 2.0 - 1.0, hash(k, 5) * 2.0 - 1.0) * hb;
                    circle(&mut cv, &v, c + o, 0.3 + 0.5 * hash(k, 9), col, 0.9);
                }
            }
            RimEdge::Thicket => {
                boxf(&mut cv, &v, c, hb, col, 1.0);
                for k in 0..50 {
                    let o = Vec2::new(hash(k, 3) * 2.0 - 1.0, hash(k, 5) * 2.0 - 1.0) * hb;
                    circle(&mut cv, &v, c + o, 0.6 + 0.6 * hash(k, 9), col.scale(1.4), 0.9);
                }
            }
            _ => boxf(&mut cv, &v, c, hb, col, 1.0),
        }
    }
    // Floor.
    let floor = p.ground.scale(2.4).mix(Rgb(0.45, 0.42, 0.4), 0.2);
    boxf(&mut cv, &v, Vec2::ZERO, half, floor, 1.0);
    // Districts.
    for d in &room.districts {
        let c = (d.min + d.max) * 0.5;
        let hh = (d.max - d.min) * 0.5;
        boxf(&mut cv, &v, c, hh, district_color(d.kind), 0.07);
        box_outline(&mut cv, &v, c, hh, 0.12, district_color(d.kind), 0.55);
    }
    // Lanes (under everything that stands).
    for l in &room.lanes {
        segment(&mut cv, &v, l.from, l.to, l.width * 0.5, WHITE, 0.10);
        dashed(&mut cv, &v, l.from, l.to, 0.08, 0.6, WHITE, 0.35);
    }
    draw_layout(&mut cv, &v, room, &p);
    // Floor an elite cannot reach from the spawn (should be none): flagged red.
    for p in Grid::new(room).sealed(room.player_spawn, 1.0) {
        boxf(&mut cv, &v, p, Vec2::splat(Grid::CELL * 0.5), hex("#FF2020"), 0.85);
    }
    // Markers.
    ring(&mut cv, &v, room.player_spawn, 1.2, 0.3, hex("#40E070"), 1.0);
    circle(&mut cv, &v, room.player_spawn, 0.5, hex("#40E070"), 1.0);
    if let Some(a) = room.anvil {
        circle(&mut cv, &v, a, 1.6, hex("#FF8A2A"), 1.0);
        ring(&mut cv, &v, a, 4.5, 0.2, hex("#FF8A2A"), 0.8);
    } else {
        ring(&mut cv, &v, Vec2::ZERO, 1.0, 0.25, hex("#FFD36B"), 0.9);
    }
    for e in &room.exits {
        boxf(&mut cv, &v, *e, Vec2::new(1.6, 0.9), hex("#40D8FF"), 1.0);
        box_outline(&mut cv, &v, *e, Vec2::new(1.6, 0.9), 0.14, INK, 1.0);
    }
    if labels {
        let ls = if s >= 8.0 { 2 } else { 1 };
        for d in &room.districts {
            if d.kind == DistrictKind::Plaza {
                continue;
            }
            let q = v.px(Vec2::new(d.min.x, d.max.y));
            cv.label(q.x as i64 + 4, q.y as i64 + 4, &district_name(d.kind), ls, district_color(d.kind));
        }
        let mut named: Vec<(&str, Vec2)> = Vec::new();
        for d in &room.decor {
            if let Some(name) = landmark_label(d) {
                // Mirrored pairs share one label.
                if named.iter().any(|(n, p)| *n == name && p.distance(d.anchor()) < 16.0) {
                    continue;
                }
                named.push((name, d.anchor()));
                let q = v.px(d.anchor());
                let wpx = name.len() as i64 * 6 * ls;
                cv.label(q.x as i64 - wpx / 2, q.y as i64 + (2.6 * s) as i64, name, ls, hex("#FFE8A0"));
            }
        }
        let q = v.px(room.player_spawn);
        cv.label(q.x as i64 - 15 * ls, q.y as i64 + (1.8 * s) as i64, "SPAWN", ls, hex("#40E070"));
    }
    cv
}

// ───────────────────────────── biome maps ─────────────────────────────

fn poi_color(p: &Palette, poi: &PoiSite) -> Rgb {
    match poi.kind {
        PoiKind::Anvil => hex("#FF8A2A"),
        PoiKind::Warlord => hex("#FF3B30"),
        PoiKind::Lair => hex("#B0303A"),
        PoiKind::Shrine => poi.god.map_or(hex("#FFD36B"), |g| god_color(p, g)),
        PoiKind::Reliquary => hex("#F0C040"),
        PoiKind::Vein => hex("#40E8E0"),
        PoiKind::Spring => hex("#5AA8FF"),
        PoiKind::Watchfire => hex("#FFB040"),
        PoiKind::Gate => hex("#40D8FF"),
    }
}

const LANDING: Rgb = Rgb(0.25, 0.88, 0.44);
const CAMP: Rgb = Rgb(0.55, 0.12, 0.12);
const ELITE_RING: Rgb = Rgb(0.94, 0.75, 0.25);
const UNREACHED: Rgb = Rgb(1.0, 0.12, 0.12);

fn tile_color(kind: TileKind, region: Rgb, p: &Palette, abyss: Rgb) -> Rgb {
    match kind {
        TileKind::Void => abyss,
        TileKind::Ground => region,
        TileKind::Road => region.mix(hex("#D8B070"), 0.55),
        TileKind::Plaza => region.mix(hex("#F0D8A0"), 0.6),
        TileKind::Bridge => hex("#B89A70"),
        TileKind::Liquid => p.liquid.scale(0.85),
    }
}

/// Land tiles a walker reaches from `from` over land (4-neighbour; obstacles ignored): what a
/// river or chasm without a bridge cuts off.
fn reachable_tiles(t: &TileGrid, from: Vec2) -> Vec<bool> {
    let mut seen = vec![false; t.kind.len()];
    let Some(start) = t.tile_of(from) else { return seen };
    let mut stack = vec![start];
    while let Some((x, y)) = stack.pop() {
        let i = t.index(x, y);
        if seen[i] || !t.kind[i].is_land() {
            continue;
        }
        seen[i] = true;
        if x > 0 {
            stack.push((x - 1, y));
        }
        if y > 0 {
            stack.push((x, y - 1));
        }
        if x + 1 < t.w {
            stack.push((x + 1, y));
        }
        if y + 1 < t.h {
            stack.push((x, y + 1));
        }
    }
    seen
}

/// A biome map's design readout (not a test).
#[derive(Clone, Debug, Default)]
pub struct MapStats {
    pub ms: f32,
    pub land: f32,
    pub road: f32,
    pub pit: f32,
    /// Share of land tiles not reachable from the Landing over land.
    pub unreached: f32,
    pub regions: usize,
    pub roads: usize,
    pub passes: usize,
    pub pois: usize,
    pub seals: u32,
    /// POIs the template's quotas ask for (plus the gate).
    pub pois_wanted: usize,
    /// Room-grammar compositions stamped into region slots (open fields excluded).
    pub comps: usize,
    /// Grand monuments standing on crossroads hubs (the skyline).
    pub monuments: usize,
    pub camps: usize,
    pub obstacles: usize,
    pub pits: usize,
    pub decor: usize,
    pub relaxed: u8,
    pub repairs: u8,
    pub hash: u64,
}

pub fn map_stats(room: &RoomDef, map: &MapLayout, ms: f32) -> MapStats {
    let t = &map.tiles;
    let n = t.kind.len().max(1) as f32;
    let count = |f: &dyn Fn(TileKind) -> bool| t.kind.iter().filter(|k| f(**k)).count();
    let land = count(&|k| k.is_land());
    let reach = reachable_tiles(t, room.player_spawn);
    let reached = reach.iter().filter(|r| **r).count();
    MapStats {
        ms,
        land: land as f32 / n,
        road: count(&|k| k == TileKind::Road) as f32 / n,
        pit: count(&|k| k.is_pit()) as f32 / n,
        unreached: 1.0 - reached as f32 / land.max(1) as f32,
        regions: map.regions.len(),
        roads: map.roads.len(),
        passes: map.passes.len(),
        pois: map.pois.len(),
        seals: map.pois.iter().map(|p| p.seals as u32).sum(),
        pois_wanted: 1 + room.expedition.as_ref().map_or(0, |x| x.pois.iter().map(|q| q.count as usize).sum()),
        comps: room.districts.iter().filter(|d| !matches!(d.kind, DistrictKind::Field | DistrictKind::Plaza)).count(),
        monuments: map.regions.iter().filter(|r| r.landmark.is_some()).count(),
        camps: map.camps.len(),
        obstacles: room.obstacles.len(),
        pits: map.pits.len(),
        decor: room.decor.len(),
        relaxed: map.relaxed,
        repairs: map.repairs,
        hash: map.hash,
    }
}

fn map_stats_line(s: &MapStats) -> String {
    format!(
        "GEN {:.1}MS  LAND {:.0}%  ROAD {:.0}%  PIT {:.0}%  UNREACHED {:.1}%  REGIONS {}  ROADS {}  PASSES {}  POIS {}/{}  SEALS {}  COMPS {}  MONUMENTS {}  CAMPS {}  OBST {}  PITS {}  DECOR {}  RELAXED {}  REPAIRS {}  HASH {:016X}",
        s.ms,
        s.land * 100.0,
        s.road * 100.0,
        s.pit * 100.0,
        s.unreached * 100.0,
        s.regions,
        s.roads,
        s.passes,
        s.pois,
        s.pois_wanted,
        s.seals,
        s.comps,
        s.monuments,
        s.camps,
        s.obstacles,
        s.pits,
        s.decor,
        s.relaxed,
        s.repairs,
        s.hash
    )
}

/// Render a biome map: tiles by region and kind, coast and region borders, pits, roads and passes,
/// the room-grammar layout, camps, POIs and the Landing. Markers keep a fixed pixel size, so the
/// map reads at any scale.
fn render_map(db: &ContentDb, room: &RoomDef, map: &MapLayout, s: f32, labels: bool) -> Canvas {
    let p = palette(db, room);
    let half = room.half_extents;
    let w = ((half.x + PAD) * 2.0 * s).ceil() as usize;
    let h = ((half.y + PAD) * 2.0 * s).ceil() as usize;
    let abyss = p.deep.scale(0.45);
    let mut cv = Canvas::new(w, h, abyss);
    let v = View { cx: w as f32 * 0.5, cy: h as f32 * 0.5, s };
    let px = 1.0 / s;
    let themes: &[RegionTheme] = room.expedition.as_ref().map_or(&[], |x| &x.themes);
    let theme_of = |r: u8| map.regions.get(r as usize).and_then(|reg| themes.get(reg.theme as usize));
    let region_color = |r: u8| theme_of(r).map_or(p.ground.scale(2.4), |t| hex(&t.map_color).scale(1.25));
    let t = &map.tiles;
    let reach = reachable_tiles(t, room.player_spawn);
    let hs = t.size * 0.5;
    for y in 0..t.h {
        for x in 0..t.w {
            let i = t.index(x, y);
            let c = t.center(x, y);
            let (a, b) = (v.px(c + Vec2::new(-hs, hs)), v.px(c + Vec2::new(hs, -hs)));
            let (x0, y0, x1, y1) = (a.x.round() as i64, a.y.round() as i64, b.x.round() as i64, b.y.round() as i64);
            cv.rect(x0, y0, x1, y1, tile_color(t.kind[i], region_color(t.region[i]), &p, abyss), 1.0);
            if t.kind[i].is_land() && !reach[i] {
                cv.rect(x0, y0, x1, y1, UNREACHED, 0.45);
            }
        }
    }
    // Cliffs where land meets void or liquid (the grid edge counts as void), region borders.
    let land = |x: i32, y: i32| {
        x >= 0 && y >= 0 && x < t.w as i32 && y < t.h as i32 && t.kind[t.index(x as u16, y as u16)].is_land()
    };
    for y in 0..t.h as i32 {
        for x in 0..t.w as i32 {
            let c = t.center(x as u16, y as u16);
            for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                let (nx, ny) = (x + dx, y + dy);
                let d = Vec2::new(dx as f32, dy as f32);
                let (e0, e1) = (c + (d + d.perp()) * hs, c + (d - d.perp()) * hs);
                if land(x, y) && !land(nx, ny) {
                    segment(&mut cv, &v, e0, e1, 0.9 * px + 0.1, INK, 0.9);
                } else if (dx, dy) > (0, 0) && land(x, y) && land(nx, ny) {
                    let (i, j) = (t.index(x as u16, y as u16), t.index(nx as u16, ny as u16));
                    if t.region[i] != t.region[j] {
                        segment(&mut cv, &v, e0, e1, 0.6 * px, INK, 0.35);
                    }
                }
            }
        }
    }
    // Pit boxes as merged by the generator.
    for o in &map.pits {
        if let Obstacle::Box { center, half } = *o {
            box_outline(&mut cv, &v, center, half, 0.8 * px, p.accent, 0.35);
        }
    }
    for l in &map.roads {
        segment(&mut cv, &v, l.from, l.to, l.width * 0.5, hex("#F0D8A0"), 0.12);
        dashed(&mut cv, &v, l.from, l.to, 0.7 * px, 2.0, hex("#F0D8A0"), 0.8);
    }
    for ps in &map.passes {
        let n = rot16_dir(ps.along).perp() * (ps.width * 0.5);
        let col = match ps.kind {
            BarrierKind::Chasm | BarrierKind::River => hex("#D8C8A8"),
            BarrierKind::Wall | BarrierKind::Ridge => hex("#E0C89A"),
        };
        segment(&mut cv, &v, ps.at - n, ps.at + n, 2.0 * px, INK, 1.0);
        segment(&mut cv, &v, ps.at - n, ps.at + n, 1.2 * px, col, 1.0);
    }
    // Room-grammar compositions in their region slots (open fields stay unmarked).
    for d in &room.districts {
        if matches!(d.kind, DistrictKind::Field | DistrictKind::Plaza) {
            continue;
        }
        let (c, hh) = ((d.min + d.max) * 0.5, (d.max - d.min) * 0.5);
        boxf(&mut cv, &v, c, hh, district_color(d.kind), 0.06);
        box_outline(&mut cv, &v, c, hh, 1.0 * px, district_color(d.kind), 0.45);
    }
    draw_layout(&mut cv, &v, room, &p);
    for c in &map.camps {
        if c.elite.is_some() {
            ring(&mut cv, &v, c.at, 6.5 * px, 1.4 * px, ELITE_RING, 1.0);
        }
        circle(&mut cv, &v, c.at, 4.5 * px, CAMP, 1.0);
        ring(&mut cv, &v, c.at, 4.5 * px, 1.2 * px, INK, 1.0);
    }
    for poi in &map.pois {
        let col = poi_color(&p, poi);
        ring(&mut cv, &v, poi.at, poi.radius, 1.5 * px, col, 0.9);
        if poi.kind == PoiKind::Gate {
            boxf(&mut cv, &v, poi.at, Vec2::splat(6.0 * px), col, 1.0);
            box_outline(&mut cv, &v, poi.at, Vec2::splat(6.0 * px), 1.2 * px, INK, 1.0);
        } else {
            circle(&mut cv, &v, poi.at, 5.5 * px, col, 1.0);
            ring(&mut cv, &v, poi.at, 5.5 * px, 1.2 * px, INK, 1.0);
        }
    }
    ring(&mut cv, &v, room.player_spawn, 8.0 * px, 2.0 * px, LANDING, 1.0);
    circle(&mut cv, &v, room.player_spawn, 4.0 * px, LANDING, 1.0);
    if labels {
        let ls = if s >= 5.0 { 2 } else { 1 };
        let centred = |cv: &mut Canvas, at: Vec2, dy: i64, text: &str, c: Rgb| {
            let q = v.px(at);
            cv.label(q.x as i64 - (text.len() as i64 * 6 * ls) / 2, q.y as i64 + dy, text, ls, c);
        };
        if s >= 3.0 {
            for d in &room.districts {
                if matches!(d.kind, DistrictKind::Field | DistrictKind::Plaza) {
                    continue;
                }
                let q = v.px(Vec2::new(d.min.x, d.max.y));
                cv.label(q.x as i64 + 3, q.y as i64 + 3, &district_name(d.kind), 1, district_color(d.kind));
            }
        }
        for (r, reg) in map.regions.iter().enumerate() {
            let name = theme_of(r as u8)
                .map_or_else(|| format!("REGION {r}"), |t| t.region_name(reg.name).to_ascii_uppercase());
            let dy = if reg.landmark.is_some() { -(9 + 8 * ls) } else { -3 * ls };
            centred(&mut cv, reg.site, dy, &name, TEXT);
            if let Some(m) = reg.landmark {
                centred(&mut cv, reg.site, 9, &mark_name(m), hex("#FFE8A0"));
            }
        }
        for poi in &map.pois {
            let mut text = poi.kind.name().to_ascii_uppercase();
            if poi.kind == PoiKind::Shrine
                && let Some(g) = poi.god.and_then(|g| db.gods.try_get(g as u16))
            {
                text = format!("{text} {}", g.name.to_ascii_uppercase());
            }
            if poi.seals > 0 {
                text = format!("{text} +{}", poi.seals);
            }
            centred(&mut cv, poi.at, -(9 + 8 * ls), &text, poi_color(&p, poi));
        }
        centred(&mut cv, room.player_spawn, 11, "LANDING", LANDING);
    }
    cv
}

/// Width of one column of a biome map's legend.
const MAP_LEGEND_COL: usize = 215;

fn map_legend(db: &ContentDb, room: &RoomDef, map: &MapLayout, width: usize, height: usize) -> Canvas {
    let mut cv = Canvas::new(width, height, Rgb(0.09, 0.08, 0.08));
    let p = palette(db, room);
    let mut y = 12i64;
    cv.text(12, y, "LEGEND", 2, TEXT);
    y += 26;
    let row = |cv: &mut Canvas, col: Rgb, name: &str, y: &mut i64| {
        cv.rect(12, *y, 30, *y + 12, col, 1.0);
        cv.text(38, *y + 2, name, 1, TEXT);
        *y += 17;
    };
    let ground = p.ground.scale(2.4);
    row(&mut cv, LANDING, "LANDING (SPAWN)", &mut y);
    for (kind, name) in [
        (TileKind::Road, "ROAD"),
        (TileKind::Plaza, "PLAZA (POI CLEARING)"),
        (TileKind::Bridge, "BRIDGE"),
        (TileKind::Liquid, "LIQUID (PIT)"),
        (TileKind::Void, "VOID (PIT)"),
    ] {
        row(&mut cv, tile_color(kind, ground, &p, p.deep.scale(0.7)), name, &mut y);
    }
    row(&mut cv, UNREACHED, "LAND CUT OFF FROM LANDING", &mut y);
    row(&mut cv, CAMP, "CAMP (GOLD RING: ELITE)", &mut y);
    row(&mut cv, hex("#3A322C"), "OBSTACLE", &mut y);
    row(&mut cv, hex("#FF00FF"), "UNDRESSED OBSTACLE", &mut y);
    y += 8;
    cv.text(12, y, "POIS", 1, DIM);
    y += 16;
    let mut kinds: Vec<PoiKind> = map.pois.iter().map(|q| q.kind).collect();
    kinds.sort();
    kinds.dedup();
    for k in kinds {
        let n = map.pois.iter().filter(|q| q.kind == k).count();
        let sample = map.pois.iter().find(|q| q.kind == k).copied();
        let col = sample.map_or(TEXT, |q| poi_color(&p, &q));
        row(&mut cv, col, &format!("{}  {n}", k.name().to_ascii_uppercase()), &mut y);
    }
    y += 8;
    if let Some(x) = &room.expedition {
        cv.text(12, y, "REGIONS", 1, DIM);
        y += 16;
        for (i, t) in x.themes.iter().enumerate() {
            let n = map.regions.iter().filter(|r| r.theme as usize == i).count();
            if n > 0 {
                row(&mut cv, hex(&t.map_color).scale(1.25), &format!("{}  {n}", t.name.to_ascii_uppercase()), &mut y);
            }
        }
    }
    // Second column: the compositions, then the decor vocabulary.
    let (x2, mut y) = (MAP_LEGEND_COL as i64 + 12, 38i64);
    let row2 = |cv: &mut Canvas, col: Rgb, name: &str, y: &mut i64| {
        cv.rect(x2, *y, x2 + 14, *y + 10, col, 1.0);
        cv.text(x2 + 20, *y + 1, name, 1, TEXT);
        *y += 14;
    };
    let mut comps: BTreeMap<String, (Rgb, usize)> = BTreeMap::new();
    for d in &room.districts {
        if !matches!(d.kind, DistrictKind::Field | DistrictKind::Plaza) {
            comps.entry(district_name(d.kind)).or_insert((district_color(d.kind), 0)).1 += 1;
        }
    }
    let fields = room.districts.iter().filter(|d| d.kind == DistrictKind::Field).count();
    cv.text(x2, y, "COMPOSITIONS", 1, DIM);
    y += 16;
    for (name, (col, n)) in &comps {
        row2(&mut cv, *col, &format!("{name}  {n}"), &mut y);
    }
    row2(&mut cv, district_color(DistrictKind::Field), &format!("OPEN FIELD  {fields}"), &mut y);
    y += 8;
    let mut seen: BTreeMap<&'static str, (Rgb, usize)> = BTreeMap::new();
    for d in &room.decor {
        let (name, col) = decor_key(d, &p);
        seen.entry(name).or_insert((col, 0)).1 += 1;
    }
    if !seen.is_empty() && y < height as i64 - 40 {
        cv.text(x2, y, "DECOR  (* LANDMARK)", 1, DIM);
        y += 16;
        for (name, (col, n)) in &seen {
            row2(&mut cv, *col, &format!("{name}  {n}"), &mut y);
            if y > height as i64 - 16 {
                break;
            }
        }
    }
    cv
}

/// Render any generated layout: a biome map or a room.
fn render(db: &ContentDb, room: &RoomDef, s: f32, labels: bool) -> Canvas {
    match &room.map {
        Some(map) => render_map(db, room, map, s, labels),
        None => render_room(db, room, s, labels),
    }
}

// ───────────────────────────── stats ─────────────────────────────

/// Layout metrics for judging density and flow (not a test: a design readout).
#[derive(Clone, Copy, Debug, Default)]
pub struct Stats {
    pub obstacles: usize,
    /// Fraction of the floor covered by obstacles.
    pub blocked: f32,
    /// Obstacle pairs with a clear gap below the lane width (squeezes / chokepoints).
    pub squeezes: usize,
    /// Free floor a hero (clearance 0.7) cannot reach from the spawn.
    pub sealed_hero: f32,
    /// Free floor an elite (clearance 1.0) cannot reach from the spawn.
    pub sealed_elite: f32,
    /// Obstacles no solid decor dresses.
    pub undressed: usize,
    /// Fraction of free floor at least 5 u from any obstacle (killing-field openness).
    pub open: f32,
    pub decor: usize,
}

fn sd_obstacle(o: &Obstacle, p: Vec2) -> f32 {
    match *o {
        Obstacle::Circle { center, radius } => sd_circle(p, center, radius),
        Obstacle::Box { center, half } => sd_box(p, center, half),
    }
}

/// Floor grid at 0.5 u with each cell's distance to the nearest obstacle surface.
struct Grid {
    w: usize,
    h: usize,
    half: Vec2,
    dist: Vec<f32>,
}

impl Grid {
    const CELL: f32 = 0.5;

    fn new(room: &RoomDef) -> Grid {
        let half = room.half_extents;
        let (w, h) = (((half.x * 2.0) / Self::CELL) as usize, ((half.y * 2.0) / Self::CELL) as usize);
        let mut g = Grid { w, h, half, dist: vec![f32::MAX; w * h] };
        for y in 0..h {
            for x in 0..w {
                let p = g.at(x, y);
                g.dist[y * w + x] = room.obstacles.iter().map(|o| sd_obstacle(o, p)).fold(f32::MAX, f32::min);
            }
        }
        g
    }

    fn at(&self, x: usize, y: usize) -> Vec2 {
        Vec2::new(-self.half.x + (x as f32 + 0.5) * Self::CELL, -self.half.y + (y as f32 + 0.5) * Self::CELL)
    }

    /// Cells a mover of `clearance` can stand on, and which of them it can reach from `from`.
    fn reach(&self, from: Vec2, clearance: f32) -> (Vec<bool>, Vec<bool>) {
        let (w, h) = (self.w, self.h);
        let ok: Vec<bool> = (0..w * h)
            .map(|i| {
                let p = self.at(i % w, i / w);
                self.dist[i] >= clearance
                    && p.x.abs() <= self.half.x - clearance
                    && p.y.abs() <= self.half.y - clearance
            })
            .collect();
        let sx = (((from.x + self.half.x) / Self::CELL) as usize).min(w - 1);
        let sy = (((from.y + self.half.y) / Self::CELL) as usize).min(h - 1);
        let mut seen = vec![false; w * h];
        let mut stack = vec![(sx, sy)];
        while let Some((x, y)) = stack.pop() {
            let i = y * w + x;
            if seen[i] || !ok[i] {
                continue;
            }
            seen[i] = true;
            if x > 0 {
                stack.push((x - 1, y));
            }
            if y > 0 {
                stack.push((x, y - 1));
            }
            if x + 1 < w {
                stack.push((x + 1, y));
            }
            if y + 1 < h {
                stack.push((x, y + 1));
            }
        }
        (ok, seen)
    }

    /// Standable cells a mover of `clearance` cannot reach from `from`.
    fn sealed(&self, from: Vec2, clearance: f32) -> Vec<Vec2> {
        let (ok, seen) = self.reach(from, clearance);
        (0..self.w * self.h).filter(|&i| ok[i] && !seen[i]).map(|i| self.at(i % self.w, i / self.w)).collect()
    }
}

pub fn stats(room: &RoomDef) -> Stats {
    let grid = Grid::new(room);
    let dist = &grid.dist;
    let (w, h) = (grid.w, grid.h);
    let n_free = dist.iter().filter(|d| **d > 0.0).count().max(1);
    let blocked = 1.0 - n_free as f32 / (w * h) as f32;
    let open = dist.iter().filter(|d| **d >= 5.0).count() as f32 / n_free as f32;
    let sealed = |clearance: f32| {
        let (ok, seen) = grid.reach(room.player_spawn, clearance);
        let total = ok.iter().filter(|o| **o).count().max(1);
        let reached = seen.iter().filter(|s| **s).count();
        1.0 - reached as f32 / total as f32
    };
    let mut squeezes = 0;
    for (i, a) in room.obstacles.iter().enumerate() {
        for b in &room.obstacles[i + 1..] {
            let g = procgen::gap(a, b);
            if g > 0.05 && g < procgen::LANE {
                squeezes += 1;
            }
        }
    }
    let solid: Vec<&Decor> = room.decor.iter().filter(|d| d.is_solid()).collect();
    let undressed = room
        .obstacles
        .iter()
        .filter(|o| {
            let c = match **o {
                Obstacle::Circle { center, .. } | Obstacle::Box { center, .. } => center,
            };
            !solid.iter().any(|d| d.covers(c))
        })
        .count();
    Stats {
        obstacles: room.obstacles.len(),
        blocked,
        squeezes,
        sealed_hero: sealed(0.7),
        sealed_elite: sealed(1.0),
        undressed,
        open,
        decor: room.decor.len(),
    }
}

fn stats_line(s: &Stats) -> String {
    format!(
        "OBST {}  BLOCK {:.1}%  OPEN {:.0}%  SQZ {}  SEAL {:.2}/{:.2}%  UNDR {}  DECOR {}",
        s.obstacles,
        s.blocked * 100.0,
        s.open * 100.0,
        s.squeezes,
        s.sealed_hero * 100.0,
        s.sealed_elite * 100.0,
        s.undressed,
        s.decor
    )
}

// ───────────────────────────── legend ─────────────────────────────

fn legend(db: &ContentDb, rooms: &[&RoomDef], width: usize, height: usize) -> Canvas {
    let mut cv = Canvas::new(width, height, Rgb(0.09, 0.08, 0.08));
    let p = rooms.first().map(|r| palette(db, r)).unwrap_or_else(|| palette(db, &RoomDef::placeholder()));
    let mut seen: BTreeMap<&'static str, (Rgb, usize)> = BTreeMap::new();
    for r in rooms {
        for d in &r.decor {
            let (name, col) = decor_key(d, &p);
            seen.entry(name).or_insert((col, 0)).1 += 1;
        }
    }
    let mut y = 12i64;
    cv.text(12, y, "LEGEND", 2, TEXT);
    y += 26;
    let row = |cv: &mut Canvas, col: Rgb, name: &str, y: &mut i64| {
        cv.rect(12, *y, 30, *y + 12, col, 1.0);
        cv.text(38, *y + 2, name, 1, TEXT);
        *y += 17;
    };
    row(&mut cv, hex("#40E070"), "SPAWN (KEEP 7)", &mut y);
    row(&mut cv, hex("#FFD36B"), "PLAZA (KEEP 7.5 / 9)", &mut y);
    row(&mut cv, hex("#40D8FF"), "GATE (KEEP 5)", &mut y);
    row(&mut cv, hex("#FF8A2A"), "ANVIL", &mut y);
    row(&mut cv, Rgb(0.85, 0.85, 0.85), "LANE (CLEAR)", &mut y);
    row(&mut cv, hex("#3A322C"), "OBSTACLE", &mut y);
    row(&mut cv, hex("#FF00FF"), "UNDRESSED OBSTACLE", &mut y);
    y += 8;
    cv.text(12, y, "DECOR  (* LANDMARK)", 1, DIM);
    y += 16;
    for (name, (col, n)) in &seen {
        row(&mut cv, *col, &format!("{name}  {n}"), &mut y);
        if y > height as i64 - 20 {
            break;
        }
    }
    y += 8;
    if y < height as i64 - 40 {
        cv.text(12, y, "DISTRICTS", 1, DIM);
        y += 16;
        let mut kinds: Vec<DistrictKind> = rooms.iter().flat_map(|r| r.districts.iter().map(|d| d.kind)).collect();
        kinds.sort_by_key(|k| *k as u8);
        kinds.dedup();
        for k in kinds {
            row(&mut cv, district_color(k), &district_name(k), &mut y);
            if y > height as i64 - 20 {
                break;
            }
        }
    }
    cv
}

// ───────────────────────────── commands ─────────────────────────────

fn resolve(db: &ContentDb, key: &str, seed: u32) -> Result<RoomDef, String> {
    let id = db.rooms.id(key).ok_or_else(|| format!("unknown room template `{key}`"))?;
    Ok(procgen::resolve_room(db, id, seed))
}

/// Resolve and time one layout (milliseconds).
fn resolve_timed(db: &ContentDb, key: &str, seed: u32) -> Result<(RoomDef, f32), String> {
    let t0 = Instant::now();
    let room = resolve(db, key, seed)?;
    Ok((room, t0.elapsed().as_secs_f32() * 1000.0))
}

/// Default pixels per world unit: rooms fill a screen at 10, a whole biome map at 3.
pub fn default_scale(db: &ContentDb, key: &str) -> f32 {
    if db.rooms.by_key(key).is_some_and(|t| t.kind == RoomKind::Expedition) { 3.0 } else { 10.0 }
}

/// Render one generated room or biome map; `ron_dump` also writes the full [`RoomDef`] next to
/// the PNG (a map's tiles, POIs and camps are generated state and are not part of it).
pub fn preview_room(
    db: &ContentDb,
    key: &str,
    seed: u32,
    out: &Path,
    scale: f32,
    ron_dump: bool,
) -> Result<(), String> {
    let (room, ms) = resolve_timed(db, key, seed)?;
    let (img, line) = match &room.map {
        Some(map) => (render_map(db, &room, map, scale, true), map_stats_line(&map_stats(&room, map, ms))),
        None => (render_room(db, &room, scale, true), stats_line(&stats(&room))),
    };
    let title_h = 34;
    let legend_w = if room.map.is_some() { MAP_LEGEND_COL * 2 } else { 250 };
    let mut cv = Canvas::new(img.w + legend_w, img.h + title_h, Rgb(0.09, 0.08, 0.08));
    cv.text(10, 8, &format!("{}  SEED {seed}", room.key), 2, TEXT);
    cv.text(
        10,
        24,
        &format!(
            "{} {:?}  {}X{} U   {line}",
            room.biome,
            room.kind,
            room.half_extents.x * 2.0,
            room.half_extents.y * 2.0
        ),
        1,
        DIM,
    );
    cv.blit(&img, 0, title_h);
    let lg = match &room.map {
        Some(map) => map_legend(db, &room, map, legend_w, img.h),
        None => legend(db, &[&room], legend_w, img.h),
    };
    cv.blit(&lg, img.w, title_h);
    cv.save_png(out)?;
    println!("{}  {line}", room.key);
    println!("wrote {}", out.display());
    if ron_dump {
        let path = out.with_extension("ron");
        let text = ron::ser::to_string_pretty(&room, ron::ser::PrettyConfig::default()).map_err(|e| e.to_string())?;
        std::fs::write(&path, text).map_err(|e| format!("{}: {e}", path.display()))?;
        println!("wrote {}", path.display());
    }
    Ok(())
}

pub struct SheetOptions {
    pub biome: Option<String>,
    pub templates: Vec<String>,
    pub kinds: Vec<RoomKind>,
    pub seeds: u32,
    pub seed0: u32,
    pub scale: f32,
}

/// Generated templates to show. Biome maps join only when asked for by kind or key: a sheet of
/// rooms stays a sheet of rooms.
fn pick_templates(db: &ContentDb, biome: Option<&str>, templates: &[String], kinds: &[RoomKind]) -> Vec<String> {
    if !templates.is_empty() {
        return templates.to_vec();
    }
    db.rooms
        .iter()
        .filter(|r| procgen::is_generated_kind(r.kind))
        .filter(|r| biome.is_none_or(|b| r.biome == b))
        .filter(|r| if kinds.is_empty() { r.kind != RoomKind::Expedition } else { kinds.contains(&r.kind) })
        .map(|r| r.key.clone())
        .collect()
}

pub fn preview_sheet(db: &ContentDb, o: &SheetOptions, out: &Path) -> Result<(), String> {
    let keys = pick_templates(db, o.biome.as_deref(), &o.templates, &o.kinds);
    if keys.is_empty() {
        return Err("no templates match".into());
    }
    let mut rooms: Vec<Vec<RoomDef>> = Vec::new();
    for k in &keys {
        let mut row = Vec::new();
        for i in 0..o.seeds {
            row.push(resolve(db, k, o.seed0 + i)?);
        }
        rooms.push(row);
    }
    // Cells share the largest room's size so the grid lines up.
    let max_half = rooms.iter().flatten().fold(Vec2::ZERO, |m, r| m.max(r.half_extents));
    let cell_w = ((max_half.x + PAD) * 2.0 * o.scale).ceil() as usize;
    let cell_h = ((max_half.y + PAD) * 2.0 * o.scale).ceil() as usize + 30;
    let legend_w = 250;
    let title_h = 30;
    let w = cell_w * o.seeds as usize + legend_w;
    let h = cell_h * rooms.len() + title_h;
    let mut cv = Canvas::new(w, h, Rgb(0.07, 0.06, 0.06));
    let title = match (&o.biome, keys.len()) {
        (Some(b), _) => format!("GENERATED ARENAS - {b} - SEEDS {}..{}", o.seed0, o.seed0 + o.seeds - 1),
        _ => format!("GENERATED ARENAS - SEEDS {}..{}", o.seed0, o.seed0 + o.seeds - 1),
    };
    cv.text(10, 8, &title, 2, TEXT);
    let mut all = Vec::new();
    for (ri, row) in rooms.iter().enumerate() {
        for (ci, room) in row.iter().enumerate() {
            let map = render(db, room, o.scale, true);
            let x = ci * cell_w + (cell_w - map.w) / 2;
            let y = title_h + ri * cell_h + 26 + (cell_h - 30 - map.h) / 2;
            cv.blit(&map, x, y);
            cv.text((ci * cell_w + 6) as i64, (title_h + ri * cell_h + 4) as i64, &room.key, 1, TEXT);
            let (short, line) = match &room.map {
                Some(m) => {
                    let st = map_stats(room, m, 0.0);
                    let short = format!(
                        "POIS {}  CAMPS {}  OBST {}  UNREACHED {:.1}%  REPAIRS {}",
                        st.pois,
                        st.camps,
                        st.obstacles,
                        st.unreached * 100.0,
                        st.repairs
                    );
                    (short, map_stats_line(&st))
                }
                None => {
                    let st = stats(room);
                    let short = format!(
                        "OBST {}  BLOCK {:.1}%  OPEN {:.0}%  SEAL {:.1}%",
                        st.obstacles,
                        st.blocked * 100.0,
                        st.open * 100.0,
                        st.sealed_elite * 100.0
                    );
                    (short, stats_line(&st))
                }
            };
            cv.text((ci * cell_w + 6) as i64, (title_h + ri * cell_h + 14) as i64, &short, 1, DIM);
            println!("{:<40} {line}", room.key);
            all.push(room);
        }
    }
    let lg = legend(db, &all, legend_w, h - title_h);
    cv.blit(&lg, w - legend_w, title_h);
    cv.save_png(out)?;
    println!("wrote {}", out.display());
    Ok(())
}

pub fn layout_stats(db: &ContentDb, biome: Option<&str>, seeds: u32) -> Result<(), String> {
    let keys = pick_templates(db, biome, &[], &[]);
    let mut by_kind: BTreeMap<String, Vec<Stats>> = BTreeMap::new();
    for k in &keys {
        let t = db.rooms.by_key(k).ok_or("template")?;
        for s in 1..=seeds {
            let room = resolve(db, k, s)?;
            by_kind.entry(format!("{}/{:?}", t.biome, t.kind)).or_default().push(stats(&room));
        }
    }
    println!(
        "{:<30} {:>5} {:>7} {:>7} {:>6} {:>6} {:>7} {:>7} {:>5} {:>6}",
        "biome/kind", "n", "obst", "block%", "open%", "sqz", "sealH%", "sealE%", "undr", "decor"
    );
    for (k, v) in &by_kind {
        let n = v.len() as f32;
        let mean = |f: &dyn Fn(&Stats) -> f32| v.iter().map(f).sum::<f32>() / n;
        let worst = |f: &dyn Fn(&Stats) -> f32| v.iter().map(f).fold(0.0f32, f32::max);
        println!(
            "{:<30} {:>5} {:>7.1} {:>7.2} {:>6.1} {:>6.1} {:>7.2} {:>7.2} {:>5} {:>6.0}",
            k,
            v.len(),
            mean(&|s| s.obstacles as f32),
            mean(&|s| s.blocked * 100.0),
            mean(&|s| s.open * 100.0),
            mean(&|s| s.squeezes as f32),
            worst(&|s| s.sealed_hero * 100.0),
            worst(&|s| s.sealed_elite * 100.0),
            worst(&|s| s.undressed as f32) as u32,
            mean(&|s| s.decor as f32),
        );
    }
    Ok(())
}

/// Worldgen budget per map (OPEN_WORLD.md §3.2): 400 ms in a debug build, 60 ms in release.
const MAP_BUDGET_MS: f32 = if cfg!(debug_assertions) { 400.0 } else { 60.0 };

/// `layout-stats --maps`: every shipped Expedition template × `seeds`, one row per map. Fails on
/// any reachability repair, any relaxed POI placement, or a map over the generation budget.
pub fn layout_stats_maps(db: &ContentDb, biome: Option<&str>, seeds: u32) -> Result<(), String> {
    let keys = pick_templates(db, biome, &[], &[RoomKind::Expedition]);
    if keys.is_empty() {
        println!("no Expedition templates{}", biome.map_or(String::new(), |b| format!(" in {b}")));
        return Ok(());
    }
    println!(
        "{:<22} {:>9} {:>8} {:>6} {:>5} {:>7} {:>5} {:>7} {:>6} {:>6} {:>5} {:>6} {:>5} {:>6} {:>7} {:>7}  hash",
        "template",
        "seed",
        "gen ms",
        "land%",
        "pit%",
        "unrch%",
        "regs",
        "pois",
        "seals",
        "comps",
        "mons",
        "camps",
        "obst",
        "pits",
        "relaxed",
        "repairs"
    );
    let mut failures = Vec::new();
    for k in &keys {
        for seed in 1..=seeds {
            let (room, ms) = resolve_timed(db, k, seed)?;
            let Some(map) = room.map.as_deref() else {
                failures.push(format!("{k} seed {seed}: generated no map"));
                continue;
            };
            let s = map_stats(&room, map, ms);
            println!(
                "{:<22} {:>9} {:>8.1} {:>6.1} {:>5.1} {:>7.2} {:>5} {:>7} {:>6} {:>6} {:>5} {:>6} {:>5} {:>6} {:>7} {:>7}  {:016x}",
                k,
                seed,
                s.ms,
                s.land * 100.0,
                s.pit * 100.0,
                s.unreached * 100.0,
                s.regions,
                format!("{}/{}", s.pois, s.pois_wanted),
                s.seals,
                s.comps,
                s.monuments,
                s.camps,
                s.obstacles,
                s.pits,
                s.relaxed,
                s.repairs,
                s.hash
            );
            if s.repairs > 0 {
                failures.push(format!("{k} seed {seed}: {} reachability repairs", s.repairs));
            }
            if s.pois < s.pois_wanted {
                failures.push(format!("{k} seed {seed}: placed {} of {} POIs", s.pois, s.pois_wanted));
            }
            if s.relaxed > 0 {
                failures.push(format!("{k} seed {seed}: {} relaxed POI placements", s.relaxed));
            }
            if s.ms > MAP_BUDGET_MS {
                failures.push(format!("{k} seed {seed}: generated in {:.0} ms (budget {MAP_BUDGET_MS} ms)", s.ms));
            }
        }
    }
    if failures.is_empty() {
        println!("\n{} map(s): 0 repairs, 0 relaxed, all within {MAP_BUDGET_MS} ms", keys.len() as u32 * seeds);
        Ok(())
    } else {
        for f in &failures {
            eprintln!("  {f}");
        }
        Err(format!("{} map check(s) failed", failures.len()))
    }
}
