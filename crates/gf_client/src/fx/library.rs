//! The VFX asset library (`assets/vfx/`, built by `tools/vfx/build_all.py`): every texture sheet,
//! every flipbook sequence and every strip row, as typed constants.
//!
//! The table mirrors `assets/vfx/vfx_assets.json`. Grids and rows are stable across rebuilds of the
//! art; when a sheet gains a row, add its constant here (the painter prints the manifest).
//!
//! Packed sheets store shape and value, not colour (manifest `conventions`): **R** = the shape as a
//! signed distance field (0.5 = the edge), **G** = the value on the ramp (ink 0.06, deep 0.29, body
//! 0.50, light 0.70, hot 0.93), **B** = the erosion order (low texels erode first). A [`Ramp`] row
//! colours them, so one painted grey flipbook serves every element.

use gf_core::damage::DamageType;
use gf_engine::prelude::*;

/// One texture of the library.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Sheet {
    Bodies,
    BoltStrips,
    BurstFlame,
    BurstGodworks,
    BurstKinetic,
    BurstPlague,
    BurstRadiant,
    BurstStorm,
    BurstUnmade,
    BurstVoid,
    Decals,
    FlameTongue,
    Glyphs,
    ImpactStar,
    MuzzleDirectional,
    PetalFlash,
    Pips,
    Plague,
    Radiant,
    SmokePuff,
    Sparkfx,
    SparksShards,
    Storm,
    VoidSwirl,
    Smears,
    Bands,
    Trails,
}

/// Where a sheet lives and how it is cut.
#[derive(Clone, Copy, Debug)]
pub struct SheetInfo {
    /// Path under `assets/vfx/`.
    pub file: &'static str,
    /// Texture size in pixels.
    pub size: (u32, u32),
    /// Columns × rows of cells.
    pub grid: (u16, u16),
    /// A strip sheet (trails, smears, bands): one row per strip, `u` runs tail → head.
    pub strip: bool,
}

impl Sheet {
    pub const COUNT: usize = 27;

    pub const ALL: [Sheet; Sheet::COUNT] = [
        Sheet::Bodies,
        Sheet::BoltStrips,
        Sheet::BurstFlame,
        Sheet::BurstGodworks,
        Sheet::BurstKinetic,
        Sheet::BurstPlague,
        Sheet::BurstRadiant,
        Sheet::BurstStorm,
        Sheet::BurstUnmade,
        Sheet::BurstVoid,
        Sheet::Decals,
        Sheet::FlameTongue,
        Sheet::Glyphs,
        Sheet::ImpactStar,
        Sheet::MuzzleDirectional,
        Sheet::PetalFlash,
        Sheet::Pips,
        Sheet::Plague,
        Sheet::Radiant,
        Sheet::SmokePuff,
        Sheet::Sparkfx,
        Sheet::SparksShards,
        Sheet::Storm,
        Sheet::VoidSwirl,
        Sheet::Smears,
        Sheet::Bands,
        Sheet::Trails,
    ];

    pub fn info(self) -> &'static SheetInfo {
        &SHEETS[self as usize]
    }

    /// Size of one cell in UV units.
    pub fn cell_uv(self) -> Vec2 {
        let i = self.info();
        Vec2::new(1.0 / i.grid.0 as f32, 1.0 / i.grid.1 as f32)
    }

    /// Width / height of one cell in pixels.
    pub fn cell_aspect(self) -> f32 {
        let i = self.info();
        (i.size.0 as f32 / i.grid.0 as f32) / (i.size.1 as f32 / i.grid.1 as f32)
    }

    /// Tile-safe sheets repeat along `u` (the tileable strip rows: beams, bands, rings).
    pub fn repeats(self) -> bool {
        matches!(self, Sheet::Trails | Sheet::Bands | Sheet::Smears)
    }
}

pub const SHEETS: [SheetInfo; Sheet::COUNT] = [
    SheetInfo { file: "atlas/vfx_bodies.png", size: (1024, 512), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_bolt_strips.png", size: (1024, 512), grid: (1, 8), strip: false },
    SheetInfo { file: "atlas/vfx_burst_flame.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_godworks.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_kinetic.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_plague.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_radiant.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_storm.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_unmade.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_burst_void.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_decals.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_flame_tongue.png", size: (1024, 1024), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_glyphs.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_impact_star.png", size: (2048, 1024), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_muzzle_directional.png", size: (1024, 512), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_petal_flash.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_pips.png", size: (512, 512), grid: (4, 4), strip: false },
    SheetInfo { file: "atlas/vfx_plague.png", size: (1024, 512), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_radiant.png", size: (2048, 1024), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_smoke_puff.png", size: (2048, 1024), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_sparkfx.png", size: (2048, 1024), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_sparks_shards.png", size: (1024, 512), grid: (8, 4), strip: false },
    SheetInfo { file: "atlas/vfx_storm.png", size: (1024, 512), grid: (4, 2), strip: false },
    SheetInfo { file: "atlas/vfx_void_swirl.png", size: (1024, 1024), grid: (4, 4), strip: false },
    SheetInfo { file: "smears/vfx_smears.png", size: (1024, 1024), grid: (1, 8), strip: true },
    SheetInfo { file: "trails/vfx_bands.png", size: (1024, 256), grid: (1, 4), strip: true },
    SheetInfo { file: "trails/vfx_trails.png", size: (1024, 1024), grid: (1, 16), strip: true },
];

/// A flipbook sequence (or a set of still sprites) inside a sheet.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Seq {
    pub sheet: Sheet,
    pub row: u16,
    pub col0: u16,
    pub frames: u16,
    /// Painted playback rate (0 = stills: pick one with [`Seq::nth`]).
    pub fps: f32,
    pub looped: bool,
    /// The effect origin inside the cell (0..1, v down).
    pub pivot: Vec2,
    /// The gameplay radius as a fraction of the half cell (0 = not authored to a radius).
    pub radius_in_cell: f32,
    /// Frames run down a column (row = frame) instead of along a row.
    pub column: bool,
}

impl Seq {
    #[allow(clippy::too_many_arguments)]
    pub const fn new(
        sheet: Sheet,
        row: u16,
        col0: u16,
        frames: u16,
        fps: f32,
        looped: bool,
        pivot: [f32; 2],
        radius_in_cell: f32,
        column: bool,
    ) -> Seq {
        Seq { sheet, row, col0, frames, fps, looped, pivot: Vec2::new(pivot[0], pivot[1]), radius_in_cell, column }
    }

    /// Still `i` of a set of stills (decals, glyphs, pips, spark variants), or a flipbook
    /// restricted to its frame `i`.
    pub const fn nth(self, i: u16) -> Seq {
        let i = if self.frames == 0 { 0 } else { i % self.frames };
        if self.column {
            Seq { row: self.row + i, frames: 1, fps: 0.0, ..self }
        } else {
            let cols = SHEETS[self.sheet as usize].grid.0;
            let k = self.col0 + i;
            Seq { row: self.row + k / cols, col0: k % cols, frames: 1, fps: 0.0, ..self }
        }
    }

    /// A column-axis sequence moved to column `col` (smoke: one silhouette aged down its column).
    pub const fn in_column(self, col: u16) -> Seq {
        Seq { col0: col, ..self }
    }

    /// The same frames played at another rate.
    pub const fn at_fps(self, fps: f32) -> Seq {
        Seq { fps, ..self }
    }

    /// A sub-range of `n` frames starting at frame `first` (bolt strobes swap 2 of 8 strips).
    pub const fn frames_from(self, first: u16, n: u16) -> Seq {
        if self.column {
            Seq { row: self.row + first, frames: n, ..self }
        } else {
            Seq { col0: self.col0 + first, frames: n, ..self }
        }
    }

    /// The cell of frame `i` (column, row).
    pub fn cell(&self, i: u16) -> (u16, u16) {
        if self.column {
            (self.col0, self.row + i)
        } else {
            let cols = self.sheet.info().grid.0;
            let k = self.col0 + i;
            (k % cols, self.row + k / cols)
        }
    }

    /// UV rectangle (u0, v0, u1, v1) of frame `i`.
    pub fn uv_rect(&self, i: u16) -> Vec4 {
        let (c, r) = self.cell(i);
        let cell = self.sheet.cell_uv();
        Vec4::new(c as f32 * cell.x, r as f32 * cell.y, (c + 1) as f32 * cell.x, (r + 1) as f32 * cell.y)
    }

    /// Quad height (world units) that makes the painted radius `r` metres.
    pub fn height_for_radius(&self, r: f32) -> f32 {
        let k = if self.radius_in_cell > 0.0 { self.radius_in_cell } else { 0.8 };
        2.0 * r / k
    }

    /// Playback length at the painted rate (0 for stills).
    pub fn duration(&self) -> f32 {
        if self.fps > 0.0 { self.frames as f32 / self.fps } else { 0.0 }
    }
}

/// One strip row of a strip sheet (`u` = 0 tail … 1 head, `v` = 0 inner / left … 1 outer / right).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Strip {
    pub sheet: Sheet,
    pub row: u16,
    /// The row tiles seamlessly along `u` (beams, bands, rings).
    pub tileable: bool,
}

impl Strip {
    pub const fn new(sheet: Sheet, row: u16, tileable: bool) -> Strip {
        Strip { sheet, row, tileable }
    }

    /// `v` range of the row, inset half a texel so filtering never reads the neighbour row.
    pub fn v_range(&self) -> (f32, f32) {
        let info = self.sheet.info();
        let rows = info.grid.1 as f32;
        let texel = 0.5 / info.size.1 as f32;
        (self.row as f32 / rows + texel, (self.row + 1) as f32 / rows - texel)
    }
}

/// Flipbook sequences and still sets (generated from `vfx_assets.json`).
pub mod seq {
    use super::{Seq, Sheet};

    pub const BODY_ORB: Seq = Seq::new(Sheet::Bodies, 0, 0, 8, 12.0, true, [0.5, 0.5], 0.6, false);
    pub const BODY_GLOBE: Seq = Seq::new(Sheet::Bodies, 1, 0, 8, 10.0, true, [0.5, 0.46], 0.6, false);
    /// EnemyShot / boss Radial teardrop, head at +u; never an element colour.
    pub const BODY_ENEMY_SHOT: Seq = Seq::new(Sheet::Bodies, 2, 0, 4, 15.0, true, [0.6, 0.5], 0.0, false);
    /// Stills: needle, pellet, bolt, slug (head at +u).
    pub const BODY_SMALL: Seq = Seq::new(Sheet::Bodies, 2, 4, 4, 0.0, false, [0.6, 0.5], 0.0, false);
    /// Stills: ink dot, body disc, hot pin, release glint (charge 0..1).
    pub const BODY_CHARGE_CORE: Seq = Seq::new(Sheet::Bodies, 3, 0, 4, 0.0, false, [0.5, 0.5], 0.0, false);
    /// Stills: the broken charge ring tightening; the last flashes white at full charge.
    pub const BODY_CHARGE_RING: Seq = Seq::new(Sheet::Bodies, 3, 4, 4, 0.0, false, [0.5, 0.5], 0.0, false);
    /// 8 lightning strips down a column (6-7 thinner: branches, micro-arcs); stretch `u` between nodes.
    pub const BOLT: Seq = Seq::new(Sheet::BoltStrips, 0, 0, 8, 30.0, true, [0.0, 0.5], 0.0, true);
    pub const BURST_FLAME: Seq = Seq::new(Sheet::BurstFlame, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_GODWORKS: Seq = Seq::new(Sheet::BurstGodworks, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_KINETIC: Seq = Seq::new(Sheet::BurstKinetic, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_PLAGUE: Seq = Seq::new(Sheet::BurstPlague, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_RADIANT: Seq = Seq::new(Sheet::BurstRadiant, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_STORM: Seq = Seq::new(Sheet::BurstStorm, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_UNMADE: Seq = Seq::new(Sheet::BurstUnmade, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    pub const BURST_VOID: Seq = Seq::new(Sheet::BurstVoid, 0, 0, 16, 24.0, false, [0.5, 0.56], 0.55, false);
    /// Ground stills, see [`super::Decal`].
    pub const DECAL: Seq = Seq::new(Sheet::Decals, 0, 0, 16, 0.0, false, [0.5, 0.5], 0.72, false);
    pub const FLAME_NARROW: Seq = Seq::new(Sheet::FlameTongue, 0, 0, 8, 12.0, true, [0.5, 0.96], 0.0, false);
    pub const FLAME_MEDIUM: Seq = Seq::new(Sheet::FlameTongue, 1, 0, 8, 12.0, true, [0.5, 0.96], 0.0, false);
    pub const FLAME_CLUMP: Seq = Seq::new(Sheet::FlameTongue, 2, 0, 8, 12.0, true, [0.5, 0.96], 0.0, false);
    pub const FLAME_LICKS: Seq = Seq::new(Sheet::FlameTongue, 3, 0, 8, 16.0, true, [0.5, 0.96], 0.0, false);
    /// Stills, see [`super::Glyph`].
    pub const GLYPH: Seq = Seq::new(Sheet::Glyphs, 0, 0, 16, 0.0, false, [0.5, 0.5], 0.0, false);
    pub const STAR4: Seq = Seq::new(Sheet::ImpactStar, 0, 0, 8, 30.0, false, [0.5, 0.5], 0.78, false);
    pub const STAR5: Seq = Seq::new(Sheet::ImpactStar, 1, 0, 8, 30.0, false, [0.5, 0.5], 0.78, false);
    pub const STAR7: Seq = Seq::new(Sheet::ImpactStar, 2, 0, 8, 30.0, false, [0.5, 0.5], 0.78, false);
    pub const STAR9: Seq = Seq::new(Sheet::ImpactStar, 3, 0, 8, 30.0, false, [0.5, 0.5], 0.78, false);
    /// Directional muzzle flashes: pivot at the muzzle, the flash points along +u.
    pub const MUZZLE_FLICKER3: Seq = Seq::new(Sheet::MuzzleDirectional, 0, 0, 4, 60.0, false, [0.06, 0.5], 0.0, false);
    pub const MUZZLE_SPIKE: Seq = Seq::new(Sheet::MuzzleDirectional, 1, 0, 4, 60.0, false, [0.05, 0.5], 0.0, false);
    pub const MUZZLE_RAIL: Seq = Seq::new(Sheet::MuzzleDirectional, 2, 0, 4, 60.0, false, [0.05, 0.5], 0.0, false);
    pub const MUZZLE_PETAL_BLOOM: Seq =
        Seq::new(Sheet::MuzzleDirectional, 3, 0, 4, 30.0, false, [0.06, 0.5], 0.0, false);
    pub const PETAL_FORWARD_FAN: Seq = Seq::new(Sheet::PetalFlash, 0, 0, 4, 60.0, false, [0.3, 0.5], 0.0, false);
    pub const PETAL_SUNBURST: Seq = Seq::new(Sheet::PetalFlash, 1, 0, 4, 60.0, false, [0.18, 0.5], 0.0, false);
    pub const PETAL_CROSS: Seq = Seq::new(Sheet::PetalFlash, 2, 0, 4, 60.0, false, [0.42, 0.5], 0.0, false);
    pub const PETAL_INWARD_STAR: Seq = Seq::new(Sheet::PetalFlash, 3, 0, 4, 60.0, false, [0.5, 0.5], 0.0, false);
    /// Stills, see [`super::Pip`].
    pub const PIP: Seq = Seq::new(Sheet::Pips, 0, 0, 16, 0.0, false, [0.5, 0.5], 0.0, false);
    pub const PLAGUE_BUBBLE: Seq = Seq::new(Sheet::Plague, 0, 0, 8, 15.0, false, [0.5, 0.6], 0.0, false);
    pub const PLAGUE_DRIP: Seq = Seq::new(Sheet::Plague, 1, 0, 8, 15.0, false, [0.5, 0.12], 0.0, false);
    pub const PLAGUE_SPLAT: Seq = Seq::new(Sheet::Plague, 2, 0, 8, 20.0, false, [0.5, 0.62], 0.0, false);
    pub const PLAGUE_SPORES: Seq = Seq::new(Sheet::Plague, 3, 0, 8, 8.0, true, [0.5, 0.5], 0.0, false);
    pub const RADIANT_CROSS_FLARE: Seq = Seq::new(Sheet::Radiant, 0, 0, 8, 30.0, false, [0.5, 0.5], 0.0, false);
    pub const RADIANT_RAY_FAN: Seq = Seq::new(Sheet::Radiant, 1, 0, 8, 30.0, false, [0.5, 0.5], 0.0, false);
    pub const RADIANT_HALO_ARCS: Seq = Seq::new(Sheet::Radiant, 2, 0, 8, 20.0, false, [0.5, 0.5], 0.0, false);
    /// Ground plane loop.
    pub const RADIANT_SUNBURST: Seq = Seq::new(Sheet::Radiant, 3, 0, 8, 8.0, true, [0.5, 0.5], 0.0, false);
    /// A smoke puff aged down its column (4 ages); columns are silhouettes: round, wide, column,
    /// lean_left, lean_right, tight, billow, wisp. Pick one with [`Seq::in_column`].
    pub const SMOKE: Seq = Seq::new(Sheet::SmokePuff, 0, 0, 4, 0.0, false, [0.5, 0.53], 0.68, true);
    pub const SPARKFX_RADIAL_BURST: Seq = Seq::new(Sheet::Sparkfx, 0, 0, 8, 24.0, false, [0.5, 0.5], 0.0, false);
    pub const SPARKFX_CONE_SPRAY: Seq = Seq::new(Sheet::Sparkfx, 1, 0, 8, 24.0, false, [0.12, 0.5], 0.0, false);
    pub const SPARKFX_SHOWER: Seq = Seq::new(Sheet::Sparkfx, 2, 0, 8, 20.0, false, [0.5, 0.78], 0.0, false);
    pub const SPARKFX_EMBER_DRIFT: Seq = Seq::new(Sheet::Sparkfx, 3, 0, 8, 10.0, true, [0.5, 0.9], 0.0, false);
    /// 8 spark streak stills, pivot at the head (+u).
    pub const SPARK: Seq = Seq::new(Sheet::SparksShards, 0, 0, 8, 0.0, false, [0.9, 0.5], 0.0, false);
    /// 8 shard kite stills.
    pub const SHARD: Seq = Seq::new(Sheet::SparksShards, 1, 0, 8, 0.0, false, [0.5, 0.5], 0.0, false);
    /// 4 teardrop stills, head at +u.
    pub const TEARDROP: Seq = Seq::new(Sheet::SparksShards, 2, 0, 4, 0.0, false, [0.62, 0.5], 0.0, false);
    pub const COIN: Seq = Seq::new(Sheet::SparksShards, 2, 4, 4, 15.0, true, [0.5, 0.5], 0.0, false);
    /// 4 four-point glint stills.
    pub const GLINT: Seq = Seq::new(Sheet::SparksShards, 3, 0, 4, 0.0, false, [0.5, 0.5], 0.0, false);
    /// Stills: ember, spore, hex, ash.
    pub const MOTE: Seq = Seq::new(Sheet::SparksShards, 3, 4, 4, 0.0, false, [0.5, 0.5], 0.0, false);
    /// Ground stills.
    pub const STORM_LICHTENBERG: Seq = Seq::new(Sheet::Storm, 0, 0, 4, 0.0, false, [0.5, 0.5], 0.88, false);
    pub const STORM_CRACKLE: Seq = Seq::new(Sheet::Storm, 1, 0, 4, 20.0, false, [0.5, 0.5], 0.0, false);
    /// Ground plane loop.
    pub const VOID_SWIRL: Seq = Seq::new(Sheet::VoidSwirl, 0, 0, 16, 16.0, true, [0.5, 0.5], 0.88, false);
}

/// Strip rows (generated from `vfx_assets.json`).
pub mod strip {
    use super::{Sheet, Strip};

    // Smears (8 frames: f0-2 the blade leads, f3-5 the body holds, f6-8 the tail erodes).
    pub const MELEE_HEAVY: Strip = Strip::new(Sheet::Smears, 0, false);
    pub const SLASH_THIN: Strip = Strip::new(Sheet::Smears, 1, false);
    pub const DASH_DRYBRUSH: Strip = Strip::new(Sheet::Smears, 2, false);
    pub const FLAME_SMEAR: Strip = Strip::new(Sheet::Smears, 3, false);
    pub const VOID_SMEAR: Strip = Strip::new(Sheet::Smears, 4, false);
    pub const STORM_SMEAR: Strip = Strip::new(Sheet::Smears, 5, false);
    pub const WHIP: Strip = Strip::new(Sheet::Smears, 6, false);
    pub const SPIN_DISC: Strip = Strip::new(Sheet::Smears, 7, true);
    // Bands (rings: tile along u).
    pub const DUST_WALL: Strip = Strip::new(Sheet::Bands, 0, true);
    pub const SHOCK_FRONT: Strip = Strip::new(Sheet::Bands, 1, true);
    pub const TICK_RING: Strip = Strip::new(Sheet::Bands, 2, true);
    pub const HEX_BAND: Strip = Strip::new(Sheet::Bands, 3, true);
    // Trails, beams, tethers.
    pub const TRACER: Strip = Strip::new(Sheet::Trails, 0, false);
    pub const DRY_BRUSH: Strip = Strip::new(Sheet::Trails, 1, false);
    pub const GHOST_SMEAR: Strip = Strip::new(Sheet::Trails, 2, false);
    pub const SMOKE_TRAIL: Strip = Strip::new(Sheet::Trails, 3, false);
    pub const HELIX: Strip = Strip::new(Sheet::Trails, 4, false);
    pub const DUST_RIBBON: Strip = Strip::new(Sheet::Trails, 5, false);
    pub const ZIGZAG: Strip = Strip::new(Sheet::Trails, 6, false);
    pub const FLAME_TRAIL: Strip = Strip::new(Sheet::Trails, 7, false);
    pub const DRIP_TRAIL: Strip = Strip::new(Sheet::Trails, 8, false);
    pub const GLINT_TRAIL: Strip = Strip::new(Sheet::Trails, 9, false);
    pub const NEEDLE_STREAK: Strip = Strip::new(Sheet::Trails, 10, false);
    pub const BEAM_CORE: Strip = Strip::new(Sheet::Trails, 11, true);
    pub const BEAM_BODY: Strip = Strip::new(Sheet::Trails, 12, true);
    pub const LOOT_BEAM: Strip = Strip::new(Sheet::Trails, 13, true);
    pub const TETHER_BRAID: Strip = Strip::new(Sheet::Trails, 14, true);
    pub const ACCENT_RING: Strip = Strip::new(Sheet::Trails, 15, true);
}

/// Ground decal stills (`vfx_decals.png`, one per cell, row-major).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Decal {
    ScorchA,
    ScorchB,
    ScorchC,
    CrackStarA,
    CrackStarB,
    Soot,
    BurnPatch,
    IchorStainA,
    IchorStainB,
    PlagueStainA,
    PlagueStainB,
    InkStainA,
    InkStainB,
    RotScar,
    Crater,
    MoltenGashes,
}

impl Decal {
    pub fn seq(self) -> Seq {
        seq::DECAL.nth(self as u16)
    }
}

/// Glyph stills (`vfx_glyphs.png`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Glyph {
    Curse,
    Mark,
    BindingHex,
    RootChain,
    Hexagram,
    SunWheel,
    ClockDial,
    Bullseye,
    GodPyra,
    GodZephyros,
    GodNyctia,
    GodAeon,
    GodGaiaa,
    GodMorwenn,
    GodSeraphel,
    GodUmbraRex,
}

impl Glyph {
    pub fn seq(self) -> Seq {
        seq::GLYPH.nth(self as u16)
    }
}

/// Status and loot pips (`vfx_pips.png`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Pip {
    Burn,
    Shock,
    Curse,
    Root,
    Bleed,
    Mark,
    Stun,
    Doom,
    Note,
    Heart,
    Shard,
    Part,
    Coin,
    Ping,
    Heal,
    Tick,
}

impl Pip {
    pub fn seq(self) -> Seq {
        seq::PIP.nth(self as u16)
    }
}

/// Mote stills (`vfx_sparks_shards.png` row 3).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mote {
    Ember,
    Spore,
    Hex,
    Ash,
}

impl Mote {
    pub fn seq(self) -> Seq {
        seq::MOTE.nth(self as u16)
    }
}

/// A colour ramp row of `ramps/vfx_ramps.png` (VFX_STYLE §3.3): value → ink / deep / body / light /
/// hot, posterized, with the HDR gain of each band in the texture's alpha.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Default)]
pub enum Ramp {
    #[default]
    Kinetic,
    Flame,
    Storm,
    Void,
    Plague,
    Radiant,
    /// Unmade ichor (enemy faction).
    Unmade,
    /// Godworks cold gold (enemy faction).
    GodworksGold,
    /// Godworks dead ember (enemy faction).
    GodworksEmber,
    /// Enemy shots: magenta-cored, never an element.
    EnemyShot,
    /// Player-side zone hems.
    ZoneGold,
    /// Heal, revive.
    Heal,
    /// Bleed: dark crimson on ink, never red-white.
    Bleed,
    /// Epoch's time accents: pale steel.
    Time,
    Dust,
    /// Neutral ink → white.
    Mono,
}

impl Ramp {
    pub const ROWS: f32 = 16.0;

    pub fn of(element: DamageType) -> Ramp {
        match element {
            DamageType::Kinetic => Ramp::Kinetic,
            DamageType::Flame => Ramp::Flame,
            DamageType::Storm => Ramp::Storm,
            DamageType::Void => Ramp::Void,
            DamageType::Plague => Ramp::Plague,
            DamageType::Radiant => Ramp::Radiant,
        }
    }

    /// `v` of the row centre in the ramp texture.
    pub fn v(self) -> f32 {
        (self as u8 as f32 + 0.5) / Self::ROWS
    }

    /// The five tones (ink, deep, body, light, hot) as sRGB hex, for lights and UI accents.
    pub fn tones(self) -> [&'static str; 5] {
        match self {
            Ramp::Kinetic => ["#1A120C", "#8A4A16", "#E3A64A", "#F4E3C1", "#FFFBF0"],
            Ramp::Flame => ["#240A06", "#A8300A", "#FF7A1A", "#FFC24B", "#FFF3D6"],
            Ramp::Storm => ["#06101E", "#1B4E9B", "#3FD8FF", "#BDF6FF", "#FFFFFF"],
            Ramp::Void => ["#0C0416", "#3B1675", "#A45CFF", "#E2CCFF", "#FFF6FF"],
            Ramp::Plague => ["#0D1507", "#3A6414", "#86E03A", "#D9FF8C", "#F6FFE0"],
            Ramp::Radiant => ["#241703", "#B07A12", "#FFE27A", "#FFF3BE", "#FFFFFF"],
            Ramp::Unmade => ["#07060A", "#0D3B35", "#2FBFA8", "#8FF2D8", "#B8FFE8"],
            Ramp::GodworksGold => ["#1E1408", "#5A4A20", "#D4B45A", "#F4E6B0", "#FFF4D0"],
            Ramp::GodworksEmber => ["#2A0E08", "#4A1A0C", "#8A3A1E", "#C8663A", "#E08A50"],
            Ramp::EnemyShot => ["#1A0610", "#7A1040", "#FF5AA8", "#FFC0E0", "#FFFFFF"],
            Ramp::ZoneGold => ["#241703", "#8A6A20", "#FFC940", "#FFE6A0", "#FFF8E0"],
            Ramp::Heal => ["#1A1406", "#6A5A20", "#FFE9A8", "#FFF4D0", "#FFFFFF"],
            Ramp::Bleed => ["#12040A", "#4A0A16", "#8A1020", "#B8404E", "#E07A84"],
            Ramp::Time => ["#0C1016", "#3C5064", "#9FB6C8", "#DCE8F0", "#FFFFFF"],
            Ramp::Dust => ["#141012", "#3A3034", "#6E6064", "#B3A69C", "#E8DED2"],
            Ramp::Mono => ["#0C080C", "#4A4448", "#B8B2B4", "#F2EEEC", "#FFFFFF"],
        }
    }

    /// The body tone.
    pub fn body(self) -> Color {
        crate::palette::hex(self.tones()[2])
    }

    /// The light tone.
    pub fn light(self) -> Color {
        crate::palette::hex(self.tones()[3])
    }
}

/// Values on the ramp (the G channel's bands), for value overrides.
pub mod value {
    pub const INK: f32 = 0.06;
    pub const DEEP: f32 = 0.29;
    pub const BODY: f32 = 0.50;
    pub const LIGHT: f32 = 0.70;
    pub const HOT: f32 = 0.93;
}
