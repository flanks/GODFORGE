//! The environment kit (OPEN_WORLD.md §7.2): every [`Decor`] variant of the layout grammar becomes
//! a list of procedural, faceted, toon-shaded parts, merged per material family ([`Key`]) and per
//! 32 u chunk, so a whole biome map draws in a handful of calls per visible chunk.
//!
//! * Parts are built in world space from a few primitive generators: chamfered blocks, lathes
//!   (columns with entasis and flutes, urns, bowls), noise rocks, crystal prisms, swept tubes
//!   (roots, trunks, chains), extruded outlines (blades, steps, voussoirs) and cloth quads.
//! * Colour rides on vertex colours, so one material per family serves the whole biome
//!   (stone courses, god banners, gold trim, ember glow).
//! * Silhouettes get inverted-hull ink ([`Key::Ink`]): the part is emitted a second time, grown by
//!   the ink width, into an unlit front-culled mesh.
//! * Glowing parts ([`Key::Glow`]) carry HDR vertex colours and bloom. Braziers also register a
//!   [`Flame`] for the pooled point lights (`world.rs`).
//!
//! Presentation only: every variation comes from hashing positions, never from the sim RNG.

use crate::camera::w3;
use crate::materials::{AbyssKind, BiomeLook};
use crate::palette::{hdr, hex, lighten, mix, poi_kind_color};
use gf_content::schema::{ClutterKind, Decor, MapLayout, RimEdge, RimStyle, TileKind, WallStyle, rot16_dir};
use gf_core::poi::PoiKind;
use gf_engine::client::triangle_mesh;
use gf_engine::prelude::*;
use std::collections::BTreeMap;
use std::f32::consts::{FRAC_PI_2, PI, TAU};

/// Side of a render chunk (world units): the unit of mesh merging and frustum culling.
pub const CHUNK: f32 = 32.0;

/// Material family a part merges into (one draw per family per chunk).
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Key {
    /// Worked stone, plaster and wood: toon, painted block atlas.
    Stone,
    /// Iron, bronze and gold: toon metal.
    Metal,
    /// Natural rock and cliffs: toon rock, world-space strata.
    Rock,
    /// Banners, foliage and ground cover: toon, double-sided.
    Cloth,
    /// Fire, embers, crystals, runes: unlit HDR vertex colour (blooms).
    Glow,
    /// Inverted-hull ink outlines: unlit, front faces culled.
    Ink,
    /// Slag, water, star-sea, chaos: the biome liquid.
    Liquid,
}

pub const KEYS: [Key; 7] = [Key::Stone, Key::Metal, Key::Rock, Key::Cloth, Key::Glow, Key::Ink, Key::Liquid];

impl Key {
    /// Does this family cast shadows from the key light?
    pub fn casts_shadow(self) -> bool {
        matches!(self, Key::Stone | Key::Metal | Key::Rock | Key::Cloth)
    }
}

/// One merged mesh under construction.
#[derive(Default)]
pub struct MeshBuf {
    pub pos: Vec<[f32; 3]>,
    pub nor: Vec<[f32; 3]>,
    pub uv: Vec<[f32; 2]>,
    pub col: Vec<[f32; 4]>,
    pub idx: Vec<u32>,
}

impl MeshBuf {
    #[inline]
    pub fn vert(&mut self, p: Vec3, n: Vec3, uv: [f32; 2], c: [f32; 4]) -> u32 {
        let i = self.pos.len() as u32;
        self.pos.push(p.to_array());
        self.nor.push(n.to_array());
        self.uv.push(uv);
        self.col.push(c);
        i
    }

    #[inline]
    pub fn tri(&mut self, a: u32, b: u32, c: u32) {
        self.idx.extend_from_slice(&[a, b, c]);
    }

    #[inline]
    pub fn quad(&mut self, a: u32, b: u32, c: u32, d: u32) {
        self.idx.extend_from_slice(&[a, b, c, a, c, d]);
    }

    pub fn is_empty(&self) -> bool {
        self.idx.is_empty()
    }

    pub fn into_mesh(self) -> Mesh {
        triangle_mesh(self.pos, self.nor, self.uv, self.idx).with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, self.col)
    }
}

/// A light the pooled point lights may pick (braziers, great braziers, crucibles, lanterns).
#[derive(Clone, Copy, Debug)]
pub struct Flame {
    pub at: Vec3,
    pub color: Color,
    /// Relative strength (1 = a brazier).
    pub power: f32,
    pub range: f32,
}

/// How a part is painted.
#[derive(Clone, Copy, Debug)]
pub struct Paint {
    pub key: Key,
    pub color: [f32; 4],
    /// Ink hull width (world units); 0 = no outline.
    pub ink: f32,
}

impl Paint {
    pub fn new(key: Key, color: Color) -> Self {
        Paint { key, color: lin(color), ink: 0.0 }
    }

    pub fn ink(mut self, w: f32) -> Self {
        self.ink = w;
        self
    }
}

/// Linear RGBA of a colour (HDR kept).
pub fn lin(c: Color) -> [f32; 4] {
    let l = c.to_linear();
    [l.red, l.green, l.blue, l.alpha]
}

/// Visual hash in 0..1 (positions, indices), for variety that never touches the sim.
pub fn h01(a: u32, b: u32) -> f32 {
    let mut h = a.wrapping_mul(0x9E37_79B9) ^ b.wrapping_mul(0x85EB_CA6B) ^ 0x27d4_eb2d;
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    h = h.wrapping_mul(0x297A_2D39);
    h ^= h >> 15;
    (h & 0xffff) as f32 / 65535.0
}

/// Hash of a world position (quantized to 1/8 u).
pub fn hp(p: Vec2, k: u32) -> f32 {
    let x = (p.x * 8.0).round() as i32 as u32;
    let y = (p.y * 8.0).round() as i32 as u32;
    h01(x.wrapping_mul(0x632B_E5AB) ^ y, k)
}

/// World rotation turning local +Z (a part's front) toward the sim-plane direction `d`.
pub fn face(d: Vec2) -> Quat {
    Quat::from_rotation_y(d.x.atan2(-d.y))
}

/// Sim-plane direction → world horizontal vector.
pub fn wd(d: Vec2) -> Vec3 {
    Vec3::new(d.x, 0.0, -d.y)
}

/// Palette of one biome's environment (all derived from its [`BiomeLook`]).
#[derive(Clone, Debug)]
pub struct Colors {
    pub abyss: AbyssKind,
    pub stone: Color,
    pub trim: Color,
    pub dark: Color,
    pub rock: Color,
    pub iron: Color,
    pub bronze: Color,
    pub gold: Color,
    pub wood: Color,
    pub bone: Color,
    pub cloth: Color,
    pub leaf: Color,
    pub leaf_dark: Color,
    pub bark: Color,
    /// Fire (HDR).
    pub flame: Color,
    pub flame_core: Color,
    /// Accent glow of runes, veins and cracks (HDR).
    pub glow: Color,
    /// Crystals (HDR, moderate).
    pub crystal: Color,
    /// Molten / liquid surface glow (HDR).
    pub molten: Color,
}

impl Colors {
    pub fn of(look: &BiomeLook) -> Self {
        // Worked stone reads lighter and cooler than the floor, so architecture stands off the
        // ground under the warm key light; each biome leans it toward its own ground colour.
        let (stone, trim, rock) = match look.abyss {
            AbyssKind::Magma => (hex("#767078"), hex("#A89C94"), hex("#45404A")),
            AbyssKind::Water => (hex("#7F8C7C"), hex("#B8C0A6"), hex("#4C5A50")),
            AbyssKind::Sky => (hex("#8E94AE"), hex("#D6D2C6"), hex("#545A78")),
            AbyssKind::Chaos => (hex("#766886"), hex("#AA9EBE"), hex("#4A3E5A")),
        };
        // A shade under the characters on the value ladder: lit tops of pale stone otherwise
        // outshine the heroes under the warm key.
        let stone = lighten(mix(stone, look.base, 0.12), 0.9);
        let trim = lighten(trim, 0.92);
        let (leaf, leaf_dark, bark, crystal) = match look.abyss {
            AbyssKind::Magma => (hex("#4A3A2E"), hex("#2A1E18"), hex("#3A2A22"), hex("#FF9A4A")),
            AbyssKind::Water => (hex("#3F7A3A"), hex("#1F4A2A"), hex("#4A3A2C"), hex("#7FFFD0")),
            AbyssKind::Sky => (hex("#5A7A8A"), hex("#2E4458"), hex("#4A4450"), hex("#9FD8FF")),
            AbyssKind::Chaos => (hex("#6A3A7A"), hex("#341A44"), hex("#3A2A44"), hex("#E070FF")),
        };
        Colors {
            abyss: look.abyss,
            stone,
            trim: mix(trim, look.base, 0.1),
            dark: lighten(mix(stone, hex("#1A1420"), 0.45), 0.7),
            rock: mix(rock, look.base, 0.15),
            iron: hex("#5C5652"),
            bronze: hex("#8A6232"),
            gold: hex("#D9A441"),
            wood: hex("#5E4230"),
            bone: hex("#D8CDB4"),
            cloth: mix(look.accent, hex("#6A1A14"), 0.55),
            leaf,
            leaf_dark,
            bark,
            flame: hdr(mix(look.accent, hex("#FF9A2A"), 0.45), 5.0),
            flame_core: hdr(hex("#FFE7A8"), 7.0),
            glow: hdr(look.accent, 3.2),
            crystal: hdr(crystal, 1.8),
            molten: hdr(mix(look.accent, hex("#FF5A10"), 0.35), 4.0),
        }
    }
}

/// Everything a decor builder needs to know besides the decor itself.
pub struct Ctx<'a> {
    pub colors: &'a Colors,
    /// Colours of the gods in table order (banners, statue trim, sigils).
    pub gods: &'a [(Color, Color)],
    /// Solid wall blocks (sim centre, half, top height): props whose anchor lies inside one stand on
    /// its top.
    pub tops: &'a [(Vec2, Vec2, f32)],
    /// Arena half extents (the north rim hangs banners from the backdrop).
    pub half: Vec2,
    /// The biome map, if this is one (bridges over chasms hang piers into the abyss).
    pub map: Option<&'a MapLayout>,
}

impl Ctx<'_> {
    fn god(&self, g: u8) -> (Color, Color) {
        self.gods.get(g as usize).copied().unwrap_or((hex("#B8322A"), hex("#FFC940")))
    }

    /// Floor height under a visual prop: the top of a wall block it stands on, else 0.
    fn ground(&self, p: Vec2) -> f32 {
        self.tops
            .iter()
            .filter(|(c, h, _)| (p - *c).abs().cmple(*h + Vec2::splat(0.02)).all())
            .map(|t| t.2)
            .fold(0.0, f32::max)
    }
}

/// Accumulates merged meshes per (chunk, key).
pub struct Env {
    bufs: BTreeMap<(u32, Key), MeshBuf>,
    chunk: u32,
    /// Chunk grid origin (world xz) and width in chunks.
    origin: Vec2,
    cols: u32,
    pub flames: Vec<Flame>,
    pub verts: usize,
}

impl Env {
    /// A builder whose chunk grid starts at world xz `origin` (the map's north-west corner).
    pub fn new(origin: Vec2, cols: u32) -> Self {
        Env { bufs: BTreeMap::new(), chunk: 0, origin, cols: cols.max(1), flames: Vec::new(), verts: 0 }
    }

    /// Chunk index of a world xz position.
    pub fn chunk_of(&self, x: f32, z: f32) -> u32 {
        let cx = ((x - self.origin.x) / CHUNK).floor().max(0.0) as u32;
        let cz = ((z - self.origin.y) / CHUNK).floor().max(0.0) as u32;
        cz * self.cols + cx.min(self.cols - 1)
    }

    /// Route the following parts to the chunk containing sim point `p`.
    pub fn at(&mut self, p: Vec2) {
        self.chunk = self.chunk_of(p.x, -p.y);
    }

    /// Chunk grid origin (world xz of its north-west corner) and width in chunks.
    pub fn grid(&self) -> (Vec2, u32) {
        (self.origin, self.cols)
    }

    pub fn buf(&mut self, key: Key) -> &mut MeshBuf {
        self.bufs.entry((self.chunk, key)).or_default()
    }

    pub fn into_buffers(self) -> BTreeMap<(u32, Key), MeshBuf> {
        self.bufs
    }

    /// Where the current chunk's stone and ink buffers end (for [`jag_top`]).
    fn mark(&mut self) -> (usize, usize) {
        (self.buf(Key::Stone).pos.len(), self.buf(Key::Ink).pos.len())
    }

    /// Vertices emitted so far (all chunks and families).
    pub fn total_verts(&self) -> usize {
        self.bufs.values().map(|b| b.pos.len()).sum()
    }

    // ───────────────────────────── primitives ─────────────────────────────

    /// A box of half extents `half` (local), turned by `rot`, bevelled by `bevel` (world units).
    /// Faces map the block half of the atlas (painted border); bevels the plain half.
    pub fn block(&mut self, pos: Vec3, rot: Quat, half: Vec3, bevel: f32, p: Paint) {
        self.block_raw(pos, rot, half, bevel, p.key, p.color, true);
        if p.ink > 0.0 {
            self.block_raw(pos, rot, half + Vec3::splat(p.ink), bevel, Key::Ink, [1.0; 4], false);
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn block_raw(&mut self, pos: Vec3, rot: Quat, half: Vec3, bevel: f32, key: Key, c: [f32; 4], faces_uv: bool) {
        // Bevels only where they read (a bevelled box costs four times the vertices).
        let b = if half.min_element() < 0.22 { 0.0 } else { bevel.min(half.min_element() * 0.45).max(0.0) };
        let seed = ((pos.x * 7.0).round() as i32 as u32).wrapping_mul(0x9E37_79B9)
            ^ ((pos.z * 7.0).round() as i32 as u32).wrapping_mul(0x85EB_CA6B)
            ^ ((pos.y * 7.0).round() as i32 as u32);
        let buf = self.buf(key);
        let inner = half - Vec3::splat(b);
        // Six faces (inset by the bevel), each one of the atlas's four painted block faces.
        for axis in 0..3 {
            for sign in [-1.0f32, 1.0] {
                let mut n = Vec3::ZERO;
                n[axis] = sign;
                let (u_ax, v_ax) = match axis {
                    0 => (2, 1),
                    1 => (0, 2),
                    _ => (0, 1),
                };
                let variant = (h01(seed, axis as u32 * 2 + (sign > 0.0) as u32) * 4.0) as u32 % 4;
                let (cu, cv) = ((variant % 2) as f32 * 0.25, (variant / 2) as f32 * 0.5);
                let mut corner = |su: f32, sv: f32| {
                    let mut l = Vec3::ZERO;
                    l[axis] = sign * half[axis];
                    l[u_ax] = su * inner[u_ax];
                    l[v_ax] = sv * inner[v_ax];
                    let uv = if faces_uv { [cu + 0.125 + su * 0.12, cv + 0.25 - sv * 0.245] } else { [0.75, 0.5] };
                    buf.vert(pos + rot * l, rot * n, uv, c)
                };
                let (a, bb, cc, d) = (corner(-1.0, -1.0), corner(1.0, -1.0), corner(1.0, 1.0), corner(-1.0, 1.0));
                // Counter-clockwise seen from outside.
                let cross = {
                    let mut eu = Vec3::ZERO;
                    eu[u_ax] = 1.0;
                    let mut ev = Vec3::ZERO;
                    ev[v_ax] = 1.0;
                    eu.cross(ev).dot(n)
                };
                if cross > 0.0 {
                    buf.quad(a, bb, cc, d);
                } else {
                    buf.quad(a, d, cc, bb);
                }
            }
        }
        if b <= 1e-4 {
            return;
        }
        // Bevel strips along the 12 edges, and 8 corner triangles.
        let pt = |sx: f32, sy: f32, sz: f32, axis: usize| {
            // Point on the face `axis` at corner (sx, sy, sz) of the inner box.
            let mut l = Vec3::new(sx * inner.x, sy * inner.y, sz * inner.z);
            l[axis] = [sx, sy, sz][axis] * half[axis];
            l
        };
        for e in 0..3 {
            // Edge along axis e; the two other axes a1, a2.
            let (a1, a2) = ((e + 1) % 3, (e + 2) % 3);
            for s1 in [-1.0f32, 1.0] {
                for s2 in [-1.0f32, 1.0] {
                    let mut ends = [[Vec3::ZERO; 2]; 2];
                    for (k, se) in [-1.0f32, 1.0].into_iter().enumerate() {
                        let mut s = [0.0f32; 3];
                        s[e] = se;
                        s[a1] = s1;
                        s[a2] = s2;
                        ends[k][0] = pt(s[0], s[1], s[2], a1);
                        ends[k][1] = pt(s[0], s[1], s[2], a2);
                    }
                    let mut n = Vec3::ZERO;
                    n[a1] = s1;
                    n[a2] = s2;
                    let n = (rot * n).normalize();
                    let v: Vec<u32> = [ends[0][0], ends[1][0], ends[1][1], ends[0][1]]
                        .iter()
                        .map(|l| buf.vert(pos + rot * *l, n, [0.75, 0.5], c))
                        .collect();
                    let face_n = (rot * (ends[1][0] - ends[0][0])).cross(rot * (ends[0][1] - ends[0][0]));
                    if face_n.dot(n) > 0.0 {
                        buf.quad(v[0], v[1], v[2], v[3]);
                    } else {
                        buf.quad(v[0], v[3], v[2], v[1]);
                    }
                }
            }
        }
        for sx in [-1.0f32, 1.0] {
            for sy in [-1.0f32, 1.0] {
                for sz in [-1.0f32, 1.0] {
                    let n = (rot * Vec3::new(sx, sy, sz)).normalize();
                    let ls = [pt(sx, sy, sz, 0), pt(sx, sy, sz, 1), pt(sx, sy, sz, 2)];
                    let v: Vec<u32> = ls.iter().map(|l| buf.vert(pos + rot * *l, n, [0.75, 0.5], c)).collect();
                    let fn_ = (rot * (ls[1] - ls[0])).cross(rot * (ls[2] - ls[0]));
                    if fn_.dot(n) > 0.0 {
                        buf.tri(v[0], v[1], v[2]);
                    } else {
                        buf.tri(v[0], v[2], v[1]);
                    }
                }
            }
        }
    }

    /// Axis-aligned world box from its sim footprint (`at ± half`) between heights `y0..y1`.
    pub fn slab(&mut self, at: Vec2, half: Vec2, y0: f32, y1: f32, bevel: f32, p: Paint) {
        let pos = w3(at, (y0 + y1) * 0.5);
        self.block(pos, Quat::IDENTITY, Vec3::new(half.x, (y1 - y0) * 0.5, half.y), bevel, p);
    }

    /// A surface of revolution around local +Y: `profile` lists (radius, height) from bottom to
    /// top. `seg` facets around; `flutes` = (count, depth fraction) carves vertical flutes. Open
    /// ends with a non-zero radius are capped.
    pub fn lathe(&mut self, pos: Vec3, rot: Quat, profile: &[(f32, f32)], seg: u32, flutes: (u32, f32), p: Paint) {
        self.lathe_raw(pos, rot, profile, seg, flutes, p.key, p.color, 0.0);
        if p.ink > 0.0 {
            self.lathe_raw(pos, rot, profile, seg, flutes, Key::Ink, [1.0; 4], p.ink);
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn lathe_raw(
        &mut self,
        pos: Vec3,
        rot: Quat,
        profile: &[(f32, f32)],
        seg: u32,
        (flutes, depth): (u32, f32),
        key: Key,
        c: [f32; 4],
        grow: f32,
    ) {
        let n = profile.len();
        if n < 2 {
            return;
        }
        let seg = seg.max(3);
        let prof: Vec<(f32, f32)> = profile
            .iter()
            .enumerate()
            .map(|(i, &(r, y))| {
                let y = if i == 0 {
                    y - grow
                } else if i == n - 1 {
                    y + grow
                } else {
                    y
                };
                (if r > 0.0 { r + grow } else { r }, y)
            })
            .collect();
        let closed = profile.first() == profile.last();
        let buf = self.buf(key);
        // Ring point and its planar surface normal (flutes tilt the normal so they catch light).
        let radial = |k: u32, r: f32| {
            let a = k as f32 / seg as f32 * TAU;
            let fl = flutes as f32;
            let (f, df) = if flutes > 0 && r > 0.0 {
                let c = (a * fl).cos();
                (1.0 - depth * (0.5 + 0.5 * c), depth * 0.5 * fl * (a * fl).sin())
            } else {
                (1.0, 0.0)
            };
            let (s, co) = a.sin_cos();
            let d = Vec3::new(co, 0.0, s);
            let t = Vec3::new(-s, 0.0, co);
            (d * r * f, (d - t * (df / f.max(0.1))).normalize_or(d))
        };
        let height = (prof[n - 1].1 - prof[0].1).abs().max(1e-3);
        for i in 0..n - 1 {
            let (r0, y0) = prof[i];
            let (r1, y1) = prof[i + 1];
            // Slope normal of this band in the (radial, up) plane.
            let dr = r1 - r0;
            let dy = y1 - y0;
            let len = (dr * dr + dy * dy).sqrt().max(1e-5);
            let (nr, ny) = (dy / len, -dr / len);
            let base = buf.pos.len() as u32;
            for k in 0..=seg {
                let (p0, d) = radial(k % seg, r0);
                let (p1, _) = radial(k % seg, r1);
                let nn = rot * (d * nr + Vec3::Y * ny).normalize_or(Vec3::Y);
                let u = 0.52 + 0.46 * (k as f32 / seg as f32);
                buf.vert(pos + rot * (p0 + Vec3::Y * y0), nn, [u, 1.0 - (y0 - prof[0].1) / height], c);
                buf.vert(pos + rot * (p1 + Vec3::Y * y1), nn, [u, 1.0 - (y1 - prof[0].1) / height], c);
            }
            for k in 0..seg {
                let a = base + k * 2;
                // The front is on the right of the profile's direction of travel, which is the
                // side (a, a+1, a+3, a+2) winds counter-clockwise toward.
                buf.quad(a, a + 1, a + 3, a + 2);
            }
        }
        // Caps (a closed profile is its own cap).
        for (end, up) in [(0usize, -1.0f32), (n - 1, 1.0)] {
            let (r, y) = prof[end];
            if r <= 1e-4 || closed {
                continue;
            }
            let nn = rot * Vec3::Y * up;
            let centre = buf.vert(pos + rot * Vec3::Y * y, nn, [0.75, 0.5], c);
            let base = buf.pos.len() as u32;
            for k in 0..seg {
                let (p0, _) = radial(k, r);
                buf.vert(pos + rot * (p0 + Vec3::Y * y), nn, [0.75, 0.5], c);
            }
            for k in 0..seg {
                let (a, b) = (base + k, base + (k + 1) % seg);
                if up > 0.0 {
                    buf.tri(centre, b, a);
                } else {
                    buf.tri(centre, a, b);
                }
            }
        }
    }

    /// A cylinder or frustum standing on `pos` (local +Y up).
    pub fn cylinder(&mut self, pos: Vec3, rot: Quat, r0: f32, r1: f32, h: f32, seg: u32, p: Paint) {
        self.lathe(pos, rot, &[(r0, 0.0), (r1, h)], seg, (0, 0.0), p);
    }

    /// A faceted ellipsoid centred on `pos`.
    pub fn ball(&mut self, pos: Vec3, rot: Quat, radius: Vec3, seg: u32, p: Paint) {
        let rings = (seg / 2).max(2);
        let prof: Vec<(f32, f32)> = (0..=rings)
            .map(|i| {
                let a = -FRAC_PI_2 + PI * i as f32 / rings as f32;
                (a.cos().max(0.0), a.sin())
            })
            .collect();
        // Unit sphere lathe, then squash by the radii through the rotation.
        let start = self.buf(p.key).pos.len();
        self.lathe_raw(Vec3::ZERO, Quat::IDENTITY, &prof, seg, (0, 0.0), p.key, p.color, 0.0);
        self.squash(p.key, start, pos, rot, radius);
        if p.ink > 0.0 {
            let start = self.buf(Key::Ink).pos.len();
            self.lathe_raw(Vec3::ZERO, Quat::IDENTITY, &prof, seg, (0, 0.0), Key::Ink, [1.0; 4], 0.0);
            self.squash(Key::Ink, start, pos, rot, radius + Vec3::splat(p.ink));
        }
    }

    /// Scale vertices `start..` of `key` by `s` (local), then rotate and move them.
    fn squash(&mut self, key: Key, start: usize, pos: Vec3, rot: Quat, s: Vec3) {
        let buf = self.buf(key);
        let inv = Vec3::new(1.0 / s.x.max(1e-4), 1.0 / s.y.max(1e-4), 1.0 / s.z.max(1e-4));
        for i in start..buf.pos.len() {
            let l = Vec3::from(buf.pos[i]) * s;
            buf.pos[i] = (pos + rot * l).to_array();
            let n = (Vec3::from(buf.nor[i]) * inv).normalize_or(Vec3::Y);
            buf.nor[i] = (rot * n).to_array();
        }
    }

    /// A noise-displaced faceted rock (icosphere), `radius` per local axis, varied by `seed`.
    pub fn rock(&mut self, pos: Vec3, rot: Quat, radius: Vec3, seed: u32, rough: f32, p: Paint) {
        // Small stones use the bare icosahedron (20 facets), big ones the subdivided one.
        let (verts, faces) =
            if radius.max_element() < 0.65 { &ICO.get_or_init(icospheres).0 } else { &ICO.get_or_init(icospheres).1 };
        // Tiny stones need no ink hull.
        let p = if radius.max_element() < 0.3 { Paint { ink: 0.0, ..p } } else { p };
        let disp: Vec<Vec3> = verts
            .iter()
            .enumerate()
            .map(|(i, v)| {
                let n = h01(i as u32, seed) - 0.5;
                let m = h01(i as u32 / 3, seed ^ 0x55) - 0.5;
                *v * (1.0 + rough * (n * 0.9 + m * 0.5))
            })
            .collect();
        for (key, c, grow) in [(p.key, p.color, 0.0), (Key::Ink, [1.0; 4], p.ink)] {
            if key == Key::Ink && p.ink <= 0.0 {
                continue;
            }
            let s = radius + Vec3::splat(grow);
            let buf = self.buf(key);
            for f in faces {
                let [a, mut b, mut cc] = f.map(|i| pos + rot * (disp[i] * s));
                // Wind outward (the rock is star-shaped around its centre).
                if (b - a).cross(cc - a).dot((a + b + cc) / 3.0 - pos) < 0.0 {
                    std::mem::swap(&mut b, &mut cc);
                }
                let n = (b - a).cross(cc - a).normalize_or(Vec3::Y);
                // A little facet-to-facet value jitter reads as chiselled planes.
                let k = 0.9 + 0.2 * h01(f[0] as u32 * 31 + f[1] as u32, seed);
                let cf = [c[0] * k, c[1] * k, c[2] * k, c[3]];
                let uv = |q: Vec3| [q.x * 0.22 + q.y * 0.05, -q.y * 0.22 + q.z * 0.07];
                let ia = buf.vert(a, n, uv(a), cf);
                let ib = buf.vert(b, n, uv(b), cf);
                let ic = buf.vert(cc, n, uv(cc), cf);
                buf.tri(ia, ib, ic);
            }
        }
    }

    /// A lump of foliage: a noise-displaced icosphere with smooth normals, dark underneath and
    /// lit on the crown (vertex colours), with an ink hull. Several make a canopy with a
    /// scalloped silhouette instead of faceted balls.
    #[allow(clippy::too_many_arguments)]
    pub fn foliage(&mut self, pos: Vec3, rot: Quat, radius: Vec3, seed: u32, under: Color, crown: Color, ink: f32) {
        let (verts, faces) = &ICO.get_or_init(icospheres).1;
        let disp: Vec<Vec3> = verts
            .iter()
            .enumerate()
            .map(|(i, v)| {
                let n = h01(i as u32, seed) - 0.5;
                let m = h01(i as u32 / 4, seed ^ 0x3C) - 0.5;
                *v * (1.0 + 0.3 * n + 0.18 * m)
            })
            .collect();
        let (under, crown) = (lin(under), lin(crown));
        for (key, grow) in [(Key::Cloth, 0.0), (Key::Ink, ink)] {
            if key == Key::Ink && ink <= 0.0 {
                continue;
            }
            let s = radius + Vec3::splat(grow);
            let buf = self.buf(key);
            let base = buf.pos.len() as u32;
            for (i, v) in disp.iter().enumerate() {
                let unit = verts[i];
                let n = rot * (unit / radius).normalize_or(Vec3::Y);
                let t = (unit.y * 0.55 + 0.45).clamp(0.0, 1.0);
                let t = t * t * (3.0 - 2.0 * t);
                let j = 0.92 + 0.16 * h01(i as u32, seed ^ 0x77);
                let c = if key == Key::Ink {
                    [1.0; 4]
                } else {
                    [
                        (under[0] + (crown[0] - under[0]) * t) * j,
                        (under[1] + (crown[1] - under[1]) * t) * j,
                        (under[2] + (crown[2] - under[2]) * t) * j,
                        1.0,
                    ]
                };
                buf.vert(pos + rot * (*v * s), n, [0.75, 0.5], c);
            }
            for f in faces {
                let [a, b, cc] = f.map(|i| pos + rot * (disp[i] * s));
                let out = (b - a).cross(cc - a).dot((a + b + cc) / 3.0 - pos) >= 0.0;
                let [ia, ib, ic] = f.map(|i| base + i as u32);
                if out {
                    buf.tri(ia, ib, ic);
                } else {
                    buf.tri(ia, ic, ib);
                }
            }
        }
    }

    /// A crystal: an n-sided prism of `radius` rising `height` to a pointed tip (`tip` tall),
    /// standing at `pos` and tilted by `rot`. Facets get baked light (it is unlit glow).
    #[allow(clippy::too_many_arguments)]
    pub fn crystal_spike(&mut self, pos: Vec3, rot: Quat, radius: f32, height: f32, tip: f32, sides: u32, p: Paint) {
        let sides = sides.max(3);
        let light = Vec3::new(-0.45, 0.8, 0.4).normalize();
        for (key, c, g) in [(p.key, p.color, 0.0), (Key::Ink, [1.0; 4], p.ink)] {
            if key == Key::Ink && p.ink <= 0.0 {
                continue;
            }
            let r = radius + g;
            let ring = |k: u32, y: f32, rr: f32| {
                let a = k as f32 / sides as f32 * TAU;
                pos + rot * Vec3::new(a.cos() * rr, y, a.sin() * rr)
            };
            let apex = pos + rot * Vec3::Y * (height + tip + g);
            let axis = rot * Vec3::Y;
            let buf = self.buf(key);
            for k in 0..sides {
                let (a0, a1) = (ring(k, -g, r * 0.9), ring(k + 1, -g, r * 0.9));
                let (b0, b1) = (ring(k, height, r), ring(k + 1, height, r));
                // Outward: away from the crystal's axis.
                let mid = (a0 + a1) * 0.5 - pos;
                let out = mid - axis * mid.dot(axis);
                let geo = (a1 - a0).cross(b0 - a0);
                let flip = geo.dot(out) < 0.0;
                let n = if flip { -geo } else { geo }.normalize_or(Vec3::Y);
                let shade = |base: f32| {
                    let k = base + 0.35 * n.dot(light).max(0.0);
                    [c[0] * k, c[1] * k, c[2] * k, c[3]]
                };
                let (cl, ch) = (shade(0.35), shade(0.85));
                let v = [
                    buf.vert(a0, n, [0.6, 1.0], cl),
                    buf.vert(a1, n, [0.9, 1.0], cl),
                    buf.vert(b1, n, [0.9, 0.2], ch),
                    buf.vert(b0, n, [0.6, 0.2], ch),
                ];
                if flip {
                    buf.quad(v[0], v[3], v[2], v[1]);
                } else {
                    buf.quad(v[0], v[1], v[2], v[3]);
                }
                let tgeo = (b1 - b0).cross(apex - b0);
                let tmid = (b0 + b1) * 0.5 - pos;
                let tout = tmid - axis * tmid.dot(axis) + axis * 0.2;
                let tflip = tgeo.dot(tout) < 0.0;
                let tn = if tflip { -tgeo } else { tgeo }.normalize_or(Vec3::Y);
                let top = |base: f32| {
                    let k = base + 0.45 * tn.dot(light).max(0.0);
                    [c[0] * k, c[1] * k, c[2] * k, c[3]]
                };
                let t = [
                    buf.vert(b0, tn, [0.6, 0.2], top(0.8)),
                    buf.vert(b1, tn, [0.9, 0.2], top(0.8)),
                    buf.vert(apex, tn, [0.75, 0.0], top(1.25)),
                ];
                if tflip {
                    buf.tri(t[0], t[2], t[1]);
                } else {
                    buf.tri(t[0], t[1], t[2]);
                }
            }
        }
    }

    /// A tube swept through `pts` (world) with per-point radii; ends capped.
    pub fn tube(&mut self, pts: &[Vec3], radii: &[f32], sides: u32, p: Paint) {
        self.tube_raw(pts, radii, sides, p.key, p.color, 0.0);
        if p.ink > 0.0 {
            self.tube_raw(pts, radii, sides, Key::Ink, [1.0; 4], p.ink);
        }
    }

    fn tube_raw(&mut self, pts: &[Vec3], radii: &[f32], sides: u32, key: Key, c: [f32; 4], grow: f32) {
        let n = pts.len();
        if n < 2 {
            return;
        }
        let sides = sides.max(3);
        // Parallel-transport frames.
        let mut frames = Vec::with_capacity(n);
        let t0 = (pts[1] - pts[0]).normalize_or(Vec3::X);
        let mut u = if t0.y.abs() < 0.9 { t0.cross(Vec3::Y).normalize() } else { t0.cross(Vec3::X).normalize() };
        for i in 0..n {
            let t = if i == 0 {
                t0
            } else if i == n - 1 {
                (pts[i] - pts[i - 1]).normalize_or(t0)
            } else {
                (pts[i + 1] - pts[i - 1]).normalize_or(t0)
            };
            u = (u - t * u.dot(t)).normalize_or(u);
            frames.push((t, u, t.cross(u)));
        }
        let buf = self.buf(key);
        let base = buf.pos.len() as u32;
        for i in 0..n {
            let (_, u, v) = frames[i];
            let r = radii[i.min(radii.len() - 1)] + grow;
            let g = if i == 0 {
                -grow
            } else if i == n - 1 {
                grow
            } else {
                0.0
            };
            let centre = pts[i] + frames[i].0 * g;
            for k in 0..=sides {
                let a = k as f32 / sides as f32 * TAU;
                let d = u * a.cos() + v * a.sin();
                buf.vert(centre + d * r, d, [0.52 + 0.46 * k as f32 / sides as f32, i as f32 * 0.25], c);
            }
        }
        let row = sides + 1;
        for i in 0..n as u32 - 1 {
            for k in 0..sides {
                let a = base + i * row + k;
                buf.quad(a, a + 1, a + row + 1, a + row);
            }
        }
        for (i, sign) in [(0usize, -1.0f32), (n - 1, 1.0)] {
            let (t, u, v) = frames[i];
            let r = radii[i.min(radii.len() - 1)] + grow;
            let centre = pts[i] + t * (sign * grow);
            let nn = t * sign;
            let ci = buf.vert(centre, nn, [0.75, 0.5], c);
            let b = buf.pos.len() as u32;
            for k in 0..sides {
                let a = k as f32 / sides as f32 * TAU;
                buf.vert(centre + (u * a.cos() + v * a.sin()) * r, nn, [0.75, 0.5], c);
            }
            for k in 0..sides {
                let (a, bb) = (b + k, b + (k + 1) % sides);
                if sign > 0.0 {
                    buf.tri(ci, a, bb);
                } else {
                    buf.tri(ci, bb, a);
                }
            }
        }
    }

    /// A flat outline (local xz, convex or star-shaped around its centroid) extruded along local
    /// +Y from `y0` to `y1`, then placed by `pos`/`rot`.
    #[allow(clippy::too_many_arguments)]
    pub fn extrude(&mut self, pos: Vec3, rot: Quat, outline: &[Vec2], y0: f32, y1: f32, p: Paint) {
        self.extrude_raw(pos, rot, outline, y0, y1, p.key, p.color, 0.0);
        if p.ink > 0.0 {
            self.extrude_raw(pos, rot, outline, y0, y1, Key::Ink, [1.0; 4], p.ink);
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn extrude_raw(
        &mut self,
        pos: Vec3,
        rot: Quat,
        outline: &[Vec2],
        y0: f32,
        y1: f32,
        key: Key,
        c: [f32; 4],
        grow: f32,
    ) {
        let n = outline.len();
        if n < 3 {
            return;
        }
        let centroid = outline.iter().copied().sum::<Vec2>() / n as f32;
        let pts: Vec<Vec2> = outline
            .iter()
            .map(|q| {
                let d = *q - centroid;
                *q + d.normalize_or_zero() * grow
            })
            .collect();
        // Orientation of the outline (counter-clockwise in local x, z → faces point outward).
        let area: f32 = (0..n).map(|i| pts[i].perp_dot(pts[(i + 1) % n])).sum();
        let ccw = area > 0.0;
        let (y0, y1) = (y0 - grow, y1 + grow);
        let buf = self.buf(key);
        let at = |q: Vec2, y: f32| pos + rot * Vec3::new(q.x, y, q.y);
        for i in 0..n {
            let (a, b) = (pts[i], pts[(i + 1) % n]);
            let e = b - a;
            // Outward normal in local xz (x, z): for a ccw polygon (in x→z) the outward normal is (e.y, -e.x).
            let mut nl = Vec2::new(e.y, -e.x).normalize_or_zero();
            if !ccw {
                nl = -nl;
            }
            let nn = rot * Vec3::new(nl.x, 0.0, nl.y);
            let v = [
                buf.vert(at(a, y0), nn, [0.52, 1.0], c),
                buf.vert(at(b, y0), nn, [0.98, 1.0], c),
                buf.vert(at(b, y1), nn, [0.98, 0.0], c),
                buf.vert(at(a, y1), nn, [0.52, 0.0], c),
            ];
            let geo = (at(b, y0) - at(a, y0)).cross(at(a, y1) - at(a, y0));
            if geo.dot(nn) >= 0.0 {
                buf.quad(v[0], v[1], v[2], v[3]);
            } else {
                buf.quad(v[0], v[3], v[2], v[1]);
            }
        }
        for (y, up) in [(y1, 1.0f32), (y0, -1.0)] {
            let nn = rot * Vec3::Y * up;
            let c0 = buf.vert(at(centroid, y), nn, [0.75, 0.5], c);
            let base = buf.pos.len() as u32;
            for q in &pts {
                buf.vert(at(*q, y), nn, [0.75, 0.5], c);
            }
            for i in 0..n as u32 {
                let (a, b) = (base + i, base + (i + 1) % n as u32);
                let geo = (at(pts[((b - base) as usize) % n], y) - at(centroid, y))
                    .cross(at(pts[(a - base) as usize], y) - at(centroid, y));
                if geo.dot(nn) >= 0.0 {
                    buf.tri(c0, b, a);
                } else {
                    buf.tri(c0, a, b);
                }
            }
        }
    }

    /// A single quad (cloth, leaves, flat glyphs). Double-sided families (cloth, glow) show both
    /// faces; `corners` wind counter-clockwise seen from the front.
    pub fn sheet(&mut self, corners: [Vec3; 4], colors: [[f32; 4]; 4], key: Key) {
        let n = (corners[1] - corners[0]).cross(corners[3] - corners[0]).normalize_or(Vec3::Y);
        let buf = self.buf(key);
        let uvs = [[0.52, 1.0], [0.98, 1.0], [0.98, 0.0], [0.52, 0.0]];
        let v: Vec<u32> = (0..4).map(|i| buf.vert(corners[i], n, uvs[i], colors[i])).collect();
        buf.quad(v[0], v[1], v[2], v[3]);
    }

    /// A ground-hugging flat polygon fan at height `y` (glyph glow, ash drifts, puddles).
    pub fn disc(&mut self, centre: Vec3, radius: f32, seg: u32, inner: [f32; 4], outer: [f32; 4], key: Key) {
        let buf = self.buf(key);
        let c = buf.vert(centre, Vec3::Y, [0.75, 0.5], inner);
        let base = buf.pos.len() as u32;
        for k in 0..seg {
            let a = k as f32 / seg as f32 * TAU;
            buf.vert(centre + Vec3::new(a.cos() * radius, 0.0, a.sin() * radius), Vec3::Y, [0.75, 0.5], outer);
        }
        for k in 0..seg {
            buf.tri(c, base + (k + 1) % seg, base + k);
        }
    }

    /// A glowing flame: stacked teardrops, white-hot core to coloured tips. `size` ≈ height.
    pub fn flame(&mut self, base: Vec3, size: f32, colors: &Colors, seed: u32) {
        let hot = lin(colors.flame_core);
        let body = lin(colors.flame);
        let tips = 3 + (h01(seed, 3) * 2.0) as u32;
        for i in 0..tips {
            let a = i as f32 / tips as f32 * TAU + h01(seed, i) * 1.3;
            let off = Vec3::new(a.cos(), 0.0, a.sin()) * size * 0.16;
            let h = size * (0.65 + 0.45 * h01(seed, i + 9));
            let lean = Quat::from_rotation_z((h01(seed, i + 20) - 0.5) * 0.4)
                * Quat::from_rotation_x((h01(seed, i + 30) - 0.5) * 0.4);
            let prof = [(0.0, 0.0), (0.2 * size, 0.18 * h), (0.16 * size, 0.5 * h), (0.0, h)];
            let start = self.buf(Key::Glow).pos.len();
            self.lathe_raw(base + off, lean, &prof, 6, (0, 0.0), Key::Glow, body, 0.0);
            // Hot at the root, coloured at the tip.
            let buf = self.buf(Key::Glow);
            for vi in start..buf.pos.len() {
                let y = ((buf.pos[vi][1] - base.y) / h).clamp(0.0, 1.0);
                let t = (1.0 - y * 1.6).clamp(0.0, 1.0);
                buf.col[vi] = [
                    body[0] + (hot[0] - body[0]) * t,
                    body[1] + (hot[1] - body[1]) * t,
                    body[2] + (hot[2] - body[2]) * t,
                    1.0,
                ];
            }
        }
    }
}

type Ico = (Vec<Vec3>, Vec<[usize; 3]>);

/// The unit icosahedron and the once-subdivided icosphere, built once for every rock.
static ICO: std::sync::OnceLock<(Ico, Ico)> = std::sync::OnceLock::new();

fn icospheres() -> (Ico, Ico) {
    let fine = icosphere();
    let coarse = (fine.0[..12].to_vec(), ICO_FACES.to_vec());
    (coarse, fine)
}

const ICO_FACES: [[usize; 3]; 20] = [
    [0, 11, 5],
    [0, 5, 1],
    [0, 1, 7],
    [0, 7, 10],
    [0, 10, 11],
    [1, 5, 9],
    [5, 11, 4],
    [11, 10, 2],
    [10, 7, 6],
    [7, 1, 8],
    [3, 9, 4],
    [3, 4, 2],
    [3, 2, 6],
    [3, 6, 8],
    [3, 8, 9],
    [4, 9, 5],
    [2, 4, 11],
    [6, 2, 10],
    [8, 6, 7],
    [9, 8, 1],
];

/// Unit icosphere subdivided once (42 vertices, 80 faces).
fn icosphere() -> Ico {
    let t = (1.0 + 5f32.sqrt()) * 0.5;
    let mut v: Vec<Vec3> = [
        (-1.0, t, 0.0),
        (1.0, t, 0.0),
        (-1.0, -t, 0.0),
        (1.0, -t, 0.0),
        (0.0, -1.0, t),
        (0.0, 1.0, t),
        (0.0, -1.0, -t),
        (0.0, 1.0, -t),
        (t, 0.0, -1.0),
        (t, 0.0, 1.0),
        (-t, 0.0, -1.0),
        (-t, 0.0, 1.0),
    ]
    .iter()
    .map(|&(x, y, z)| Vec3::new(x, y, z).normalize())
    .collect();
    let mut mid = BTreeMap::new();
    let mut midpoint = |a: usize, b: usize, v: &mut Vec<Vec3>| -> usize {
        let key = (a.min(b), a.max(b));
        *mid.entry(key).or_insert_with(|| {
            v.push(((v[a] + v[b]) * 0.5).normalize());
            v.len() - 1
        })
    };
    let mut faces = Vec::with_capacity(80);
    for [a, b, c] in ICO_FACES {
        let ab = midpoint(a, b, &mut v);
        let bc = midpoint(b, c, &mut v);
        let ca = midpoint(c, a, &mut v);
        // The base table winds clockwise seen from outside; flip to counter-clockwise.
        faces.extend_from_slice(&[[a, ca, ab], [b, ab, bc], [c, bc, ca], [ab, ca, bc]]);
    }
    (v, faces)
}

// ───────────────────────────── decor ─────────────────────────────

/// Ink width of architecture and of small props (world units).
const INK: f32 = 0.055;
const INK_S: f32 = 0.032;

/// Per-decor variety stream (hashed from the decor's position; presentation only).
struct Vr {
    seed: u32,
    n: u32,
}

impl Vr {
    fn new(p: Vec2, k: u32) -> Self {
        Vr { seed: (hp(p, k) * 65535.0) as u32 ^ k.wrapping_mul(0x9E37), n: 0 }
    }

    fn f(&mut self) -> f32 {
        self.n += 1;
        h01(self.seed, self.n)
    }

    fn r(&mut self, lo: f32, hi: f32) -> f32 {
        lo + (hi - lo) * self.f()
    }

    fn i(&mut self, n: u32) -> u32 {
        ((self.f() * n as f32) as u32).min(n.saturating_sub(1))
    }

    fn sign(&mut self) -> f32 {
        if self.f() < 0.5 { -1.0 } else { 1.0 }
    }
}

/// A sim-plane unit vector at angle `a` (radians, counter-clockwise from +x).
fn dir(a: f32) -> Vec2 {
    Vec2::new(a.cos(), a.sin())
}

/// Colour of a stone part, varied around `base` by `k` ∈ 0..1.
fn vary(base: Color, k: f32, amount: f32) -> Color {
    lighten(base, 1.0 + (k - 0.5) * 2.0 * amount)
}

/// Render one decor entry into the kit (its chunk is its anchor's).
pub fn decor(env: &mut Env, ctx: &Ctx, d: &Decor) {
    env.at(d.anchor());
    let c = ctx.colors;
    match *d {
        // Painted into the floor as glowing rifts (floor.wesl).
        Decor::LavaCrack { .. } | Decor::Paving { .. } | Decor::FloorInlay { .. } => {}
        Decor::BrokenAnvil { at, scale } => broken_anvil(env, ctx, at, scale),
        Decor::Brazier { at } => brazier(env, ctx, at),
        Decor::Pillar { at, radius, height } => {
            let mut v = Vr::new(at, 1);
            let stone = vary(c.stone, v.f(), 0.06);
            column(env, c, w3(at, 0.0), Quat::IDENTITY, radius, height, stone, height < 2.5, &mut v);
        }
        Decor::Wall { at, half, height, style, variant } => wall(env, ctx, at, half, height, style, variant),
        Decor::Boulder { at, radius, variant } => boulder(env, c, at, radius, variant),
        Decor::Statue { at, radius, height, rot, god, variant } => {
            statue(env, ctx, at, radius, height, rot16_dir(rot), god, variant)
        }
        Decor::ColossusHead { at, radius, rot, variant } => colossus_head(env, c, at, radius, rot16_dir(rot), variant),
        Decor::FallenColumn { from, to, radius } => fallen_column(env, c, from, to, radius),
        Decor::GreatAnvil { at, radius, rot } => great_anvil(env, c, at, radius, rot16_dir(rot)),
        Decor::Crucible { at, radius } => crucible(env, c, at, radius),
        Decor::GreatBrazier { at, radius } => great_brazier(env, c, at, radius),
        Decor::SealedGate { at, half, height } => sealed_gate(env, c, at, half, height),
        Decor::Arch { from, to, pier, height, variant } => arch(env, c, from, to, pier, height, variant),
        Decor::Tree { at, radius, height, variant } => tree(env, c, at, radius, height, variant),
        Decor::FallenTree { from, to, radius } => fallen_tree(env, c, from, to, radius),
        Decor::Crystal { at, radius, height, rot, variant } => {
            crystal(env, c, at, radius, height, rot16_dir(rot), variant)
        }
        Decor::SpiralStair { at, radius, height, rot } => spiral_stair(env, c, at, radius, height, rot16_dir(rot)),
        Decor::InvertedColumn { at, radius, height } => inverted_column(env, c, at, radius, height),
        Decor::Rift { at, radius, height, rot } => rift(env, c, at, radius, height, rot16_dir(rot)),
        Decor::Channel { from, to, width } => channel(env, c, from, to, width),
        Decor::FallenWeapon { at, radius, height, rot, variant } => {
            fallen_weapon(env, c, at, radius, height, rot16_dir(rot), variant)
        }
        Decor::Bridge { from, to, width } => {
            // Over a chasm the deck stands on piers that drop into the abyss.
            let d = (to - from).normalize_or(Vec2::X);
            let n = Vec2::new(-d.y, d.x);
            let mid = (from + to) * 0.5;
            let void = ctx.map.is_some_and(|m| {
                (1..5).any(|k| {
                    let off = n * (width * 0.5 + k as f32 * 2.0);
                    m.tiles.kind_at(mid + off) == TileKind::Void || m.tiles.kind_at(mid - off) == TileKind::Void
                })
            });
            bridge(env, c, from, to, width, if void { 9.0 } else { 0.0 })
        }
        Decor::Pool { at, half } => pool(env, c, at, half),
        Decor::Overgrowth { at, radius, variant } => overgrowth(env, c, at, radius, variant),
        Decor::Roots { from, to, width } => roots(env, c, from, to, width),
        Decor::Rubble { at, radius, variant } => rubble(env, c, at, radius, variant),
        Decor::Clutter { at, radius, kind, count, rot } => {
            let y = ctx.ground(at);
            clutter(env, ctx, at, y, radius, kind, count, rot16_dir(rot))
        }
        Decor::Banner { at, height, rot, god } => banner(env, ctx, at, height, rot16_dir(rot), god),
        Decor::Chains { from, to, height } => chains(env, c, w3(from, height), w3(to, height), 0.12),
        Decor::Waymark { at, rot, kind } => waymark(env, c, at, rot16_dir(rot), kind),
        Decor::Debris { at, radius, height, variant } => debris(env, c, at, radius, height, variant),
    }
}

/// A classical column standing at `base` (world), turned by `rot`: square plinth, torus, fluted
/// shaft with entasis, echinus and abacus. `broken` snaps it into a jagged stump.
#[allow(clippy::too_many_arguments)]
fn column(env: &mut Env, c: &Colors, base: Vec3, rot: Quat, r: f32, h: f32, stone: Color, broken: bool, v: &mut Vr) {
    let p = Paint::new(Key::Stone, stone).ink(INK);
    let trim = Paint::new(Key::Stone, lighten(stone, 1.22)).ink(INK);
    let plinth_h = (0.16 * h).clamp(0.22, 0.42);
    env.block(base + rot * Vec3::Y * (plinth_h * 0.5), rot, Vec3::new(r * 1.28, plinth_h * 0.5, r * 1.28), 0.04, trim);
    let torus =
        [(r * 1.14, plinth_h), (r * 1.18, plinth_h + 0.08), (r * 1.1, plinth_h + 0.18), (r * 0.98, plinth_h + 0.26)];
    env.lathe(base, rot, &torus, 10, (0, 0.0), Paint { ink: 0.0, ..trim });
    let shaft0 = plinth_h + 0.24;
    let (cap_h, top) = if broken { (0.0, h) } else { ((0.1 * h).clamp(0.35, 0.7), h) };
    let shaft1 = top - cap_h;
    if shaft1 <= shaft0 + 0.1 {
        return;
    }
    // Entasis: the shaft swells a little a third of the way up, then tapers.
    let prof: Vec<(f32, f32)> = (0..=4)
        .map(|i| {
            let t = i as f32 / 4.0;
            let swell = 1.0 + 0.035 * (1.0 - ((t - 0.33) * 2.2).powi(2)).max(0.0);
            (r * (1.0 - 0.12 * t) * swell, shaft0 + (shaft1 - shaft0) * t)
        })
        .collect();
    let flutes = if c.abyss == AbyssKind::Chaos { (0, 0.0) } else { (8, 0.1) };
    let start = env.mark();
    env.lathe(base, rot, &prof, 16, flutes, p);
    if broken {
        jag_top(env, start, shaft1, 0.4 * r.min(1.0), v.seed);
        // Its fallen drum lies beside it.
        let d = dir(v.r(0.0, TAU));
        let at = base + wd(d) * (r * 2.2) + Vec3::Y * (r * 0.62);
        let lie = face(d) * Quat::from_rotation_x(FRAC_PI_2);
        env.lathe(at - lie * Vec3::Y * (r * 0.55), lie, &[(r * 0.85, 0.0), (r * 0.82, r * 1.1)], 14, (12, 0.1), p);
        return;
    }
    // Capital: a necking ring, the echinus flaring out, the abacus slab.
    let e0 = shaft1;
    let echinus = [(r * 0.9, e0), (r * 0.98, e0 + 0.06), (r * 0.92, e0 + 0.1), (r * 1.16, e0 + cap_h * 0.62)];
    env.lathe(base, rot, &echinus, 12, (0, 0.0), trim);
    let ab = cap_h * 0.38;
    env.block(base + rot * Vec3::Y * (top - ab * 0.5), rot, Vec3::new(r * 1.22, ab * 0.5, r * 1.22), 0.03, trim);
    if c.abyss == AbyssKind::Sky || c.abyss == AbyssKind::Magma {
        // A gilded band at the necking (Spire) / iron collar (Cinder).
        let (col, key) = if c.abyss == AbyssKind::Sky { (c.gold, Key::Metal) } else { (c.iron, Key::Metal) };
        env.lathe(base, rot, &[(r * 0.96, e0 - 0.16), (r * 0.96, e0 - 0.02)], 16, (0, 0.0), Paint::new(key, col));
    }
}

/// Break the top of the stone emitted since `mark` (see [`Env::mark`]): vertices at height `y`
/// (± 0.03) drop by up to `amp`, and the part's ink hull is cut down below the break so it
/// never shows above the jagged edge.
fn jag_top(env: &mut Env, mark: (usize, usize), y: f32, amp: f32, seed: u32) {
    let buf = env.buf(Key::Stone);
    for i in mark.0..buf.pos.len() {
        let p = buf.pos[i];
        if (p[1] - y).abs() < 0.03 {
            let k =
                h01((p[0] * 16.0).round() as i32 as u32 ^ ((p[2] * 16.0).round() as i32 as u32).rotate_left(11), seed);
            buf.pos[i][1] = y - amp * k;
        }
    }
    let ink = env.buf(Key::Ink);
    for i in mark.1..ink.pos.len() {
        if ink.pos[i][1] > y - 0.03 {
            ink.pos[i][1] = y - amp;
        }
    }
}

fn broken_anvil(env: &mut Env, ctx: &Ctx, at: Vec2, scale: f32) {
    let c = ctx.colors;
    let y = ctx.ground(at);
    let mut v = Vr::new(at, 2);
    let iron = Paint::new(Key::Metal, c.iron).ink(INK_S);
    let yaw = Quat::from_rotation_y(v.r(0.0, TAU));
    let s = scale;
    let base = w3(at, y);
    // The body lies tipped on its side, the horn snapped off beside it.
    let tip = yaw * Quat::from_rotation_z(0.25);
    env.block(base + Vec3::Y * 0.3 * s, tip, Vec3::new(0.7, 0.26, 0.34) * s, 0.04 * s, iron);
    env.block(base + yaw * Vec3::new(-0.2, 0.62, 0.0) * s, tip, Vec3::new(0.8, 0.12, 0.38) * s, 0.03 * s, iron);
    let horn = yaw * Quat::from_rotation_z(-FRAC_PI_2 - 0.3);
    env.cylinder(base + yaw * Vec3::new(1.05, 0.22, 0.3) * s, horn, 0.22 * s, 0.02, 0.8 * s, 8, iron);
    env.block(
        base + yaw * Vec3::new(-0.9, 0.12, -0.5) * s,
        yaw * Quat::from_rotation_x(0.5),
        Vec3::new(0.26, 0.12, 0.2) * s,
        0.03,
        iron,
    );
    // A faint ember in the crack.
    env.block(
        base + yaw * Vec3::new(0.1, 0.57, 0.0) * s,
        tip,
        Vec3::new(0.5, 0.012, 0.3) * s,
        0.0,
        Paint::new(Key::Glow, hdr(c.molten, 0.25)),
    );
}

fn brazier(env: &mut Env, ctx: &Ctx, at: Vec2) {
    let c = ctx.colors;
    let y = ctx.ground(at);
    let base = w3(at, y);
    let bronze = Paint::new(Key::Metal, c.bronze).ink(INK_S);
    // Three splayed legs, a waist ring, the bowl, glowing coals and the fire.
    for k in 0..3 {
        let a = k as f32 / 3.0 * TAU + 0.4;
        let foot = base + Vec3::new(a.cos() * 0.38, 0.0, a.sin() * 0.38);
        let knee = base + Vec3::new(a.cos() * 0.16, 0.5, a.sin() * 0.16);
        let top = base + Vec3::new(a.cos() * 0.3, 0.86, a.sin() * 0.3);
        env.tube(&[foot, knee, top], &[0.05, 0.04, 0.045], 5, bronze);
    }
    env.lathe(base, Quat::IDENTITY, &[(0.2, 0.48), (0.22, 0.54), (0.2, 0.6)], 10, (0, 0.0), bronze);
    let bowl = [(0.12, 0.78), (0.3, 0.84), (0.44, 0.98), (0.47, 1.06), (0.41, 1.06), (0.39, 1.0)];
    env.lathe(base, Quat::IDENTITY, &bowl, 12, (0, 0.0), bronze);
    env.disc(base + Vec3::Y * 1.0, 0.39, 10, lin(hdr(c.molten, 0.9)), lin(hdr(c.molten, 0.35)), Key::Glow);
    env.flame(base + Vec3::Y * 0.98, 0.95, c, hp(at, 5).to_bits());
    env.flames.push(Flame { at: base + Vec3::Y * 1.6, color: c.flame, power: 1.0, range: 11.0 });
}

#[allow(clippy::too_many_arguments)]
fn wall(env: &mut Env, ctx: &Ctx, at: Vec2, half: Vec2, height: f32, style: WallStyle, variant: u8) {
    let c = ctx.colors;
    let mut v = Vr::new(at, 3 + variant as u32);
    let along_x = half.x >= half.y;
    let (hl, ht) = if along_x { (half.x, half.y) } else { (half.y, half.x) };
    // Local frame: u along the wall (world x or −z), t across it.
    let (u, t) = if along_x { (Vec3::X, Vec3::Z) } else { (Vec3::Z, Vec3::X) };
    let rot = if along_x { Quat::IDENTITY } else { Quat::from_rotation_y(FRAC_PI_2) };
    let base = w3(at, 0.0);
    match style {
        WallStyle::Ruin | WallStyle::Forge => {
            masonry(env, c, base, rot, u, hl, ht, height, style == WallStyle::Ruin, &mut v);
            if style == WallStyle::Forge {
                forge_trim(env, c, base, rot, u, t, hl, ht, height, &mut v);
            }
        }
        WallStyle::Parapet => parapet(env, c, base, rot, hl, ht, height),
        WallStyle::Plinth => {
            let stone = vary(c.stone, v.f(), 0.06);
            let trim = Paint::new(Key::Stone, lighten(stone, 1.25)).ink(INK);
            let die = Paint::new(Key::Stone, stone).ink(INK);
            let step = 0.2f32.min(height * 0.2);
            let corn = 0.22f32.min(height * 0.2);
            env.block(base + Vec3::Y * step * 0.5, rot, Vec3::new(hl + 0.08, step * 0.5, ht + 0.08), 0.03, trim);
            let die_h = height - step - corn;
            env.block(
                base + Vec3::Y * (step + die_h * 0.5),
                rot,
                Vec3::new(hl - 0.04, die_h * 0.5, ht - 0.04),
                0.05,
                die,
            );
            env.block(
                base + Vec3::Y * (height - corn * 0.5),
                rot,
                Vec3::new(hl + 0.1, corn * 0.5, ht + 0.1),
                0.03,
                trim,
            );
            // A carved panel on the long faces.
            if die_h > 0.5 {
                let panel = Paint::new(Key::Stone, lighten(stone, 0.78));
                for s in [-1.0f32, 1.0] {
                    env.block(
                        base + Vec3::Y * (step + die_h * 0.5) + rot * Vec3::Z * (s * (ht - 0.02)),
                        rot,
                        Vec3::new(hl * 0.62, die_h * 0.32, 0.03),
                        0.0,
                        panel,
                    );
                }
            }
            if c.abyss == AbyssKind::Sky {
                env.block(
                    base + Vec3::Y * (height - corn - 0.05),
                    rot,
                    Vec3::new(hl + 0.02, 0.05, ht + 0.02),
                    0.0,
                    Paint::new(Key::Metal, c.gold),
                );
            }
        }
        WallStyle::Hedge => hedge(env, c, base, u, t, hl, ht, height, &mut v),
        WallStyle::Monolith => {
            let tilt = Quat::from_rotation_z(v.r(-0.08, 0.08)) * Quat::from_rotation_x(v.r(-0.06, 0.06));
            let lift = 0.35 + 0.25 * v.f();
            let r = rot * tilt;
            let stone = mix(c.dark, hex("#2A1E3A"), 0.4);
            let centre = base + Vec3::Y * (lift + height * 0.5);
            env.block(centre, r, Vec3::new(hl, height * 0.5, ht), 0.08, Paint::new(Key::Stone, stone).ink(INK));
            // Glowing seams and a rune band.
            let glow = Paint::new(Key::Glow, c.glow);
            for k in 0..3 {
                let y = (k as f32 + 0.5) / 3.0 * height - height * 0.5 + v.r(-0.2, 0.2);
                env.block(centre + r * Vec3::new(0.0, y, 0.0), r, Vec3::new(hl + 0.012, 0.025, ht + 0.012), 0.0, glow);
            }
            env.disc(base + Vec3::Y * 0.02, hl.max(ht) * 1.1, 12, lin(hdr(c.glow, 0.15)), [0.0; 4], Key::Glow);
        }
    }
}

/// Coursed masonry: blocks of varied length, staggered per course; `ruined` breaks the top.
#[allow(clippy::too_many_arguments)]
fn masonry(
    env: &mut Env,
    c: &Colors,
    base: Vec3,
    rot: Quat,
    u: Vec3,
    hl: f32,
    ht: f32,
    height: f32,
    ruined: bool,
    v: &mut Vr,
) {
    // Large, monumental courses; an intact wall is closed by a projecting coping.
    let coping = if ruined { 0.0 } else { 0.18f32.min(height * 0.15) };
    let body = height - coping;
    let course = v.r(0.72, 0.95);
    let n = ((body / course).round() as u32).max(1);
    let ch = body / n as f32;
    let stone = vary(c.stone, v.f(), 0.05);
    // Silhouette ink: one hull for the solid lower courses; a ruin's broken top course (which
    // may have gaps) inks block by block.
    let solid_top = if ruined { ch * (n - 1) as f32 } else { height };
    if solid_top > 0.0 {
        env.block_raw(
            base + Vec3::Y * (solid_top * 0.5),
            rot,
            Vec3::new(hl, solid_top * 0.5, ht) + Vec3::splat(INK),
            0.0,
            Key::Ink,
            [1.0; 4],
            false,
        );
    }
    for k in 0..n {
        let y0 = ch * k as f32;
        let last = k == n - 1;
        // Courses alternate long stretchers with a staggered start.
        let mut s = -hl + if k % 2 == 1 { v.r(0.3, 0.8) } else { 0.0 };
        if s > -hl {
            let len = s + hl;
            masonry_block(env, stone, base, rot, u, -hl, len, y0, ch, ht, ruined && last, ruined && last, v);
        }
        while s < hl - 0.05 {
            let len = v.r(1.1, 2.1).min(hl - s);
            let len = if hl - s - len < 0.45 { hl - s } else { len };
            masonry_block(env, stone, base, rot, u, s, len, y0, ch, ht, ruined && last, ruined && last, v);
            s += len;
        }
    }
    if coping > 0.0 {
        let trim = Paint::new(Key::Stone, lighten(stone, 1.2)).ink(INK);
        env.block(
            base + Vec3::Y * (body + coping * 0.5),
            rot,
            Vec3::new(hl + 0.06, coping * 0.5, ht + 0.08),
            0.03,
            trim,
        );
    } else if height > 1.0 {
        // Fallen blocks and scree at the foot of a ruin.
        for _ in 0..(1 + (hl * 0.6) as u32) {
            let side = if v.f() < 0.5 { -1.0 } else { 1.0 };
            let along = v.r(-hl, hl);
            let across = rot * Vec3::Z * (side * (ht + v.r(0.3, 0.8)));
            let s = v.r(0.18, 0.32);
            env.block(
                base + u * along + across + Vec3::Y * s * 0.8,
                rot * Quat::from_rotation_y(v.r(-0.6, 0.6)) * Quat::from_rotation_z(v.r(-0.3, 0.3)),
                Vec3::new(s * 1.5, s * 0.8, s),
                0.0,
                Paint::new(Key::Stone, vary(stone, v.f(), 0.1)).ink(INK_S),
            );
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn masonry_block(
    env: &mut Env,
    stone: Color,
    base: Vec3,
    rot: Quat,
    u: Vec3,
    s: f32,
    len: f32,
    y0: f32,
    ch: f32,
    ht: f32,
    broken: bool,
    inked: bool,
    v: &mut Vr,
) {
    let mut h = ch;
    if broken {
        if v.f() < 0.3 {
            return;
        }
        h *= v.r(0.35, 1.0);
    }
    let inset = v.r(-0.03, 0.05);
    let col = vary(stone, v.f(), 0.1);
    let centre = base + u * (s + len * 0.5) + Vec3::Y * (y0 + h * 0.5);
    let mut p = Paint::new(Key::Stone, col);
    if inked {
        p = p.ink(INK);
    }
    let wobble = if broken { Quat::from_rotation_y(v.r(-0.06, 0.06)) } else { Quat::IDENTITY };
    env.block(centre, rot * wobble, Vec3::new(len * 0.5 - 0.015, h * 0.5 - 0.01, ht - inset.max(0.0)), 0.0, p);
}

/// Iron bands, rivets and a forge fitting (a quench trough on a low block, bellows on a tall one).
#[allow(clippy::too_many_arguments)]
fn forge_trim(
    env: &mut Env,
    c: &Colors,
    base: Vec3,
    rot: Quat,
    u: Vec3,
    t: Vec3,
    hl: f32,
    ht: f32,
    height: f32,
    v: &mut Vr,
) {
    let iron = Paint::new(Key::Metal, c.iron);
    let bands = if height > 2.0 { [0.3, 0.72] } else { [0.5, 2.0] };
    for f in bands {
        if f > 1.0 {
            continue;
        }
        env.block(base + Vec3::Y * (height * f), rot, Vec3::new(hl + 0.03, 0.07, ht + 0.03), 0.0, iron);
    }
    let studs = ((hl * 2.0) / 0.9) as i32;
    for i in 0..=studs {
        let x = -hl + 0.2 + i as f32 * ((hl * 2.0 - 0.4) / studs.max(1) as f32);
        for s in [-1.0f32, 1.0] {
            env.block(
                base + u * x + t * (s * (ht + 0.05)) + Vec3::Y * (height * bands[0]),
                rot,
                Vec3::splat(0.05),
                0.0,
                Paint::new(Key::Metal, c.bronze),
            );
        }
    }
    if height < 1.6 && v.f() < 0.6 {
        // A quench trough: the top sunk and filled with glowing slag.
        env.block(
            base + Vec3::Y * (height - 0.06),
            rot,
            Vec3::new(hl - 0.15, 0.02, ht - 0.15),
            0.0,
            Paint::new(Key::Glow, hdr(c.molten, 0.6)),
        );
    }
}

/// A balustrade: a stepped plinth over the whole footprint, pedestals every bay, turned
/// balusters and a slim top rail, so the camera looks down between the balusters instead of
/// onto one slab.
fn parapet(env: &mut Env, c: &Colors, base: Vec3, rot: Quat, hl: f32, ht: f32, height: f32) {
    let trim = Paint::new(Key::Stone, c.trim).ink(INK);
    let stone = Paint::new(Key::Stone, c.stone).ink(INK_S);
    let h = height.max(0.7);
    let rail = (ht * 0.6).clamp(0.14, 0.28);
    let at = |x: f32, y: f32| base + rot * Vec3::new(x, y, 0.0);
    env.block(at(0.0, 0.12), rot, Vec3::new(hl, 0.12, ht), 0.03, trim);
    env.block(at(0.0, 0.3), rot, Vec3::new(hl - 0.06, 0.06, rail + 0.05), 0.02, stone);
    env.block(at(0.0, h - 0.08), rot, Vec3::new(hl - 0.02, 0.08, rail + 0.06), 0.03, trim);
    let bays = ((hl * 2.0) / 2.6).ceil().max(1.0) as i32;
    let bay = (hl * 2.0 - 0.44) / bays as f32;
    let post = Vec3::new(0.2, (h - 0.24) * 0.5, rail + 0.09);
    for i in 0..=bays {
        let x = -hl + 0.22 + bay * i as f32;
        env.block(at(x, 0.24 + post.y), rot, post, 0.03, stone);
        env.block(at(x, h + 0.04), rot, Vec3::new(0.25, 0.06, rail + 0.13), 0.02, trim);
    }
    let bh = h - 0.52;
    let k = rail / 0.28;
    let prof = [
        (0.07 * k, 0.0),
        (0.1 * k, bh * 0.08),
        (0.07 * k, bh * 0.2),
        (0.13 * k, bh * 0.45),
        (0.06 * k, bh * 0.8),
        (0.09 * k, bh * 0.92),
        (0.09 * k, bh),
    ];
    let per = ((bay - 0.4) / 0.36).floor().max(1.0) as i32;
    let gap = (bay - 0.4) / per as f32;
    for i in 0..bays {
        for j in 0..per {
            let x = -hl + 0.22 + bay * i as f32 + 0.2 + gap * (j as f32 + 0.5);
            env.lathe(at(x, 0.36), rot, &prof, 8, (0, 0.0), Paint::new(Key::Stone, c.stone));
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn hedge(env: &mut Env, c: &Colors, base: Vec3, u: Vec3, t: Vec3, hl: f32, ht: f32, height: f32, v: &mut Vr) {
    let rock = Paint::new(Key::Rock, c.rock).ink(INK);
    let bark = Paint::new(Key::Stone, c.bark).ink(INK_S);
    let n = ((hl * 2.0) / 1.4).ceil().max(1.0) as u32;
    for i in 0..n {
        let x = -hl + (i as f32 + 0.5) * (hl * 2.0 / n as f32);
        let r = Vec3::new(hl / n as f32 + 0.25, height * 0.45, ht + 0.1);
        let r = if u == Vec3::X { r } else { Vec3::new(r.z, r.y, r.x) };
        env.rock(base + u * x + Vec3::Y * (height * 0.35), Quat::IDENTITY, r, v.seed ^ i, 0.35, rock);
    }
    // Roots crawling over it, leaves heaped on top.
    for _ in 0..(n + 1) {
        let x = -hl + v.r(0.0, hl * 2.0);
        let s = v.sign();
        let pts = [
            base + u * x + t * (s * (ht + 0.4)),
            base + u * (x + v.r(-0.4, 0.4)) + t * (s * (ht + 0.1)) + Vec3::Y * (height * 0.5),
            base + u * (x + v.r(-0.5, 0.5)) + Vec3::Y * (height * 0.95),
        ];
        env.tube(&pts, &[0.16, 0.12, 0.08], 6, bark);
    }
    let under = mix(c.leaf_dark, hex("#0A0E12"), 0.25);
    for i in 0..n * 2 {
        let x = -hl + (i as f32 + 0.5) * (hl / n as f32);
        let rr = v.r(0.5, 0.8);
        let crown = if i % 3 == 0 {
            mix(c.leaf, c.leaf_dark, 0.4)
        } else {
            lighten(vary(mix(c.leaf, c.leaf_dark, 0.15), v.f(), 0.1), 1.04)
        };
        env.foliage(
            base + u * x + t * v.r(-ht, ht) + Vec3::Y * (height * 0.8 + rr * 0.4),
            Quat::from_rotation_y(v.r(0.0, TAU)),
            Vec3::new(rr, rr * 0.7, rr),
            v.seed ^ (i * 97 + 3),
            under,
            crown,
            INK_S,
        );
    }
}

fn boulder(env: &mut Env, c: &Colors, at: Vec2, r: f32, variant: u8) {
    let mut v = Vr::new(at, 7);
    let base = w3(at, 0.0);
    let rock = Paint::new(Key::Rock, vary(c.rock, v.f(), 0.08)).ink(INK);
    let yaw = Quat::from_rotation_y(v.r(0.0, TAU));
    match (c.abyss, variant % 4) {
        (AbyssKind::Chaos, _) => {
            // Impossible polyhedron: a hovering faceted solid with glowing edges beneath.
            let lift = 0.4 + 0.3 * v.f();
            let tilt = yaw * Quat::from_rotation_x(v.r(0.3, 0.7));
            env.rock(base + Vec3::Y * (r * 0.8 + lift), tilt, Vec3::splat(r * 0.92), v.seed, 0.0, rock);
            env.disc(base + Vec3::Y * 0.03, r * 1.1, 12, lin(hdr(c.glow, 0.35)), [0.0; 4], Key::Glow);
            env.crystal_spike(
                base + Vec3::Y * (r * 0.8 + lift) - Vec3::Y * r * 1.2,
                Quat::from_rotation_x(PI),
                r * 0.25,
                0.1,
                r * 0.5,
                5,
                Paint::new(Key::Glow, c.crystal),
            );
        }
        (AbyssKind::Magma, 1) | (_, 3) => {
            // Rubble mound: a heap of smaller stones.
            for k in 0..5 {
                let d = dir(k as f32 * 1.3 + v.f());
                let rr = r * v.r(0.4, 0.6);
                let off = wd(d) * (r - rr) * v.r(0.4, 0.9);
                env.rock(base + off + Vec3::Y * rr * 0.4, yaw, Vec3::new(rr, rr * 0.7, rr), v.seed + k, 0.4, rock);
            }
        }
        (AbyssKind::Water, 1) => {
            // Root knot: a mossy stone bound by roots.
            env.rock(base + Vec3::Y * r * 0.3, yaw, Vec3::new(r * 0.85, r * 0.7, r * 0.85), v.seed, 0.3, rock);
            let bark = Paint::new(Key::Stone, c.bark).ink(INK_S);
            for k in 0..4 {
                let a = k as f32 / 4.0 * TAU + v.f();
                let d = Vec3::new(a.cos(), 0.0, a.sin());
                let pts = [
                    base + d * r * 1.25,
                    base + d * r * 0.8 + Vec3::Y * r * 0.6,
                    base + d * r * 0.2 + Vec3::Y * r * 0.95,
                ];
                env.tube(&pts, &[r * 0.16, r * 0.13, r * 0.09], 6, bark);
            }
            moss_cap(env, c, base + Vec3::Y * r * 0.85, r * 0.7, &mut v);
        }
        _ => {
            let sq = if c.abyss == AbyssKind::Sky { 0.2 } else { 0.42 };
            env.rock(base + Vec3::Y * r * 0.3, yaw, Vec3::new(r, r * 0.78, r * 0.92), v.seed, sq, rock);
            // A smaller stone leaning against it.
            let d = dir(v.r(0.0, TAU));
            let rr = r * 0.45;
            env.rock(base + wd(d) * (r * 0.95) + Vec3::Y * rr * 0.3, yaw, Vec3::splat(rr), v.seed ^ 9, sq, rock);
            if c.abyss == AbyssKind::Water {
                moss_cap(env, c, base + Vec3::Y * r * 0.95, r * 0.75, &mut v);
            } else if c.abyss == AbyssKind::Magma && v.f() < 0.5 {
                // Ember seams glowing through the charred crust.
                for _ in 0..3 {
                    let d = dir(v.r(0.0, TAU));
                    let p0 = base + wd(d) * r * 0.9 + Vec3::Y * r * 0.2;
                    env.tube(
                        &[p0, p0 + Vec3::Y * r * 0.5 + wd(d) * 0.1],
                        &[0.04, 0.02],
                        4,
                        Paint::new(Key::Glow, c.molten),
                    );
                }
            }
        }
    }
}

fn moss_cap(env: &mut Env, c: &Colors, top: Vec3, r: f32, v: &mut Vr) {
    let leaf = Paint::new(Key::Cloth, c.leaf);
    env.ball(top, Quat::from_rotation_y(v.r(0.0, TAU)), Vec3::new(r, r * 0.25, r * 0.9), 8, leaf);
}

#[allow(clippy::too_many_arguments)]
fn statue(env: &mut Env, ctx: &Ctx, at: Vec2, r: f32, h: f32, facing: Vec2, god: u8, variant: u8) {
    let c = ctx.colors;
    let mut v = Vr::new(at, 11);
    let base = w3(at, 0.0);
    let rot = face(facing);
    let marble = lighten(mix(c.stone, hex("#E8E0D0"), 0.35), 1.05);
    let trim = Paint::new(Key::Stone, lighten(c.stone, 1.3)).ink(INK);
    let body = Paint::new(Key::Stone, marble).ink(INK);
    let (god_c, god_2) = ctx.god(god);
    // Stepped round plinth.
    let ph = (h * 0.14).clamp(0.6, 1.3);
    let plinth = [
        (r, 0.0),
        (r, ph * 0.3),
        (r * 0.88, ph * 0.34),
        (r * 0.8, ph * 0.4),
        (r * 0.8, ph * 0.88),
        (r * 0.9, ph * 0.9),
        (r * 0.9, ph),
    ];
    env.lathe(base, rot, &plinth, 16, (0, 0.0), trim);
    // God-coloured inlay band on the plinth.
    env.lathe(base, rot, &[(r * 0.81, ph * 0.55), (r * 0.81, ph * 0.7)], 16, (0, 0.0), Paint::new(Key::Metal, c.gold));
    let fig = h - ph;
    let s = fig / 7.5;
    let foot = base + Vec3::Y * ph;
    let at3 = |x: f32, y: f32, z: f32| foot + rot * Vec3::new(x * s, y * s, z * s);
    let kneel = variant % 4 == 1;
    let robe_h = if kneel { 2.2 } else { 3.6 };
    // Robe: a fluted, flared skirt.
    let robe = [(1.3 * s, 0.0), (1.2 * s, robe_h * 0.3 * s), (0.95 * s, robe_h * 0.75 * s), (0.8 * s, robe_h * s)];
    env.lathe(foot, rot, &robe, 14, (7, 0.12), body);
    if kneel {
        // One knee forward.
        env.ball(at3(0.4, 0.8, 0.9), rot, Vec3::new(0.55, 0.5, 0.9) * s, 8, body);
    }
    let waist = robe_h;
    // Sash in the god's colour and a gold belt.
    env.lathe(
        foot,
        rot,
        &[(0.84 * s, (waist - 0.35) * s), (0.84 * s, (waist - 0.05) * s)],
        14,
        (0, 0.0),
        Paint::new(Key::Metal, c.gold),
    );
    env.sheet(
        [
            at3(0.3, waist - 0.3, 0.82),
            at3(0.62, waist - 0.3, 0.72),
            at3(0.72, waist - 2.2, 0.95),
            at3(0.35, waist - 2.3, 1.05),
        ],
        [lin(god_c), lin(god_c), lin(lighten(god_c, 0.6)), lin(lighten(god_c, 0.6))],
        Key::Cloth,
    );
    // Torso and shoulders.
    let chest = waist + 1.3;
    env.lathe(
        at3(0.0, waist, 0.0),
        rot,
        &[(0.78 * s, 0.0), (1.0 * s, 1.1 * s), (0.95 * s, 1.5 * s), (0.5 * s, 1.75 * s)],
        12,
        (0, 0.0),
        body,
    );
    let headless = variant % 4 == 2;
    if !headless {
        env.cylinder(at3(0.0, chest + 0.35, 0.0), rot, 0.28 * s, 0.26 * s, 0.4 * s, 8, body);
        env.ball(at3(0.0, chest + 1.05, 0.05), rot, Vec3::new(0.46, 0.56, 0.5) * s, 10, body);
        // A laurel / crown in gold.
        env.lathe(
            at3(0.0, chest + 1.2, 0.05),
            rot,
            &[(0.5 * s, 0.0), (0.54 * s, 0.12 * s), (0.5 * s, 0.24 * s)],
            12,
            (0, 0.0),
            Paint::new(Key::Metal, c.gold),
        );
    } else {
        // Broken neck: a jagged stump.
        let start = env.mark();
        env.cylinder(at3(0.0, chest + 0.35, 0.0), rot, 0.3 * s, 0.3 * s, 0.25 * s, 8, body);
        jag_top(env, start, (foot + rot * Vec3::Y * ((chest + 0.6) * s)).y, 0.15 * s, v.seed);
    }
    let sh = chest + 0.15;
    for side in [-1.0f32, 1.0] {
        env.ball(at3(side * 1.0, sh, 0.0), rot, Vec3::splat(0.42 * s), 8, body);
    }
    // Arms by pose.
    let arm = |env: &mut Env, pts: [(f32, f32, f32); 3], p: Paint| {
        let w: Vec<Vec3> = pts.iter().map(|&(x, y, z)| at3(x, y, z)).collect();
        env.tube(&w, &[0.3 * s, 0.26 * s, 0.22 * s], 7, p);
    };
    match variant % 4 {
        0 => {
            // Raised blade.
            arm(env, [(1.05, sh, 0.0), (1.5, sh + 1.1, 0.2), (1.3, sh + 2.1, 0.3)], body);
            arm(env, [(-1.05, sh, 0.0), (-1.2, sh - 1.1, 0.4), (-0.9, sh - 1.9, 0.8)], body);
            let hilt = at3(1.3, sh + 2.2, 0.3);
            let steel = Paint::new(Key::Metal, lighten(c.iron, 2.4)).ink(INK_S);
            let up = rot * Vec3::new(0.08, 1.0, 0.1).normalize();
            let brot = Quat::from_rotation_arc(Vec3::Y, up) * Quat::from_rotation_y(v.r(-0.3, 0.3));
            env.block(hilt + up * (2.2 * s), brot, Vec3::new(0.2 * s, 2.0 * s, 0.05 * s), 0.02, steel);
            env.block(hilt, brot, Vec3::new(0.6 * s, 0.08 * s, 0.12 * s), 0.02, Paint::new(Key::Metal, c.gold));
        }
        1 => {
            arm(env, [(1.05, sh, 0.0), (1.2, sh - 0.9, 0.7), (0.5, sh - 1.1, 1.3)], body);
            arm(env, [(-1.05, sh, 0.0), (-1.1, sh - 1.0, 0.6), (-0.4, sh - 1.2, 1.2)], body);
            // A votive bowl held in both hands, softly lit.
            let bowl = at3(0.0, sh - 1.2, 1.35);
            env.lathe(
                bowl,
                rot,
                &[(0.1 * s, 0.0), (0.5 * s, 0.25 * s), (0.55 * s, 0.35 * s)],
                10,
                (0, 0.0),
                Paint::new(Key::Metal, c.bronze),
            );
            env.flame(bowl + Vec3::Y * 0.3 * s, 0.7 * s, c, v.seed);
        }
        2 => {
            arm(env, [(1.05, sh, 0.0), (1.3, sh - 1.2, 0.2), (1.2, sh - 2.2, 0.3)], body);
        }
        _ => {
            arm(env, [(1.05, sh, 0.0), (2.1, sh + 0.3, 0.3), (3.0, sh + 0.8, 0.4)], body);
            arm(env, [(-1.05, sh, 0.0), (-2.1, sh + 0.3, 0.3), (-3.0, sh + 0.8, 0.4)], body);
        }
    }
    // A glowing sigil of the god on the plinth front.
    let sig = base + rot * Vec3::new(0.0, ph * 0.62, r * 0.82);
    let fwd = rot * Vec3::Z;
    let right = rot * Vec3::X;
    let g2 = lin(hdr(god_2, 2.2));
    let q = 0.18 * ph.min(1.0);
    env.sheet(
        [
            sig - right * q + fwd * 0.01,
            sig - Vec3::Y * q + fwd * 0.01,
            sig + right * q + fwd * 0.01,
            sig + Vec3::Y * q + fwd * 0.01,
        ],
        [g2; 4],
        Key::Glow,
    );
}

fn colossus_head(env: &mut Env, c: &Colors, at: Vec2, r: f32, facing: Vec2, variant: u8) {
    let mut v = Vr::new(at, 13);
    let base = w3(at, 0.0);
    // Toppled onto the back of its skull and half sunk: the face looks up at the sky, tipped
    // toward `facing` and rolled a little, so the camera above reads brow, eyes, nose and mouth.
    let tip = 0.95 + 0.15 * v.f();
    let rot = face(facing) * Quat::from_rotation_z(v.r(-0.25, 0.25)) * Quat::from_rotation_x(-tip);
    let stone = vary(mix(c.stone, hex("#9A9080"), 0.3), v.f(), 0.05);
    let p = Paint::new(Key::Stone, stone).ink(INK);
    let pale = Paint::new(Key::Stone, lighten(stone, 1.12)).ink(INK_S);
    let hollow = Paint::new(Key::Stone, lighten(stone, 0.32));
    let centre = base + Vec3::Y * (r * 0.28);
    let at3 = |x: f32, y: f32, z: f32| centre + rot * Vec3::new(x * r, y * r, z * r);
    // Skull (local +y = crown, +z = the face).
    env.ball(centre, rot, Vec3::new(r * 0.86, r * 1.02, r * 0.9), 14, p);
    // Jaw and cheeks bulk out the lower face.
    env.ball(at3(0.0, -0.42, 0.28), rot, Vec3::new(0.66, 0.5, 0.62) * r, 12, p);
    // Brow ridge over deep sockets, with ember eyes deep inside.
    env.ball(at3(0.0, 0.26, 0.74), rot, Vec3::new(0.62, 0.13, 0.22) * r, 10, pale);
    let eye = match c.abyss {
        AbyssKind::Magma => c.molten,
        _ => c.glow,
    };
    for side in [-1.0f32, 1.0] {
        env.ball(at3(side * 0.28, 0.1, 0.76), rot, Vec3::new(0.19, 0.12, 0.1) * r, 8, hollow);
        env.ball(at3(side * 0.28, 0.1, 0.83), rot, Vec3::new(0.09, 0.06, 0.05) * r, 6, Paint::new(Key::Glow, eye));
        // Cheekbones.
        env.ball(at3(side * 0.44, -0.12, 0.66), rot, Vec3::new(0.2, 0.13, 0.16) * r, 8, pale);
    }
    // The nose: a ridge from the brow to a heavy tip, nostrils beneath.
    env.tube(
        &[at3(0.0, 0.2, 0.86), at3(0.0, 0.02, 0.96), at3(0.0, -0.14, 1.02)],
        &[0.07 * r, 0.1 * r, 0.13 * r],
        6,
        pale,
    );
    for side in [-1.0f32, 1.0] {
        env.ball(at3(side * 0.07, -0.19, 0.97), rot, Vec3::new(0.05, 0.035, 0.03) * r, 5, hollow);
    }
    // Lips and a cleft chin.
    env.ball(at3(0.0, -0.33, 0.86), rot, Vec3::new(0.24, 0.05, 0.08) * r, 8, pale);
    env.ball(at3(0.0, -0.41, 0.84), rot, Vec3::new(0.21, 0.045, 0.07) * r, 8, p);
    env.ball(at3(0.0, -0.37, 0.87), rot, Vec3::new(0.2, 0.012, 0.04) * r, 6, hollow);
    env.ball(at3(0.0, -0.6, 0.72), rot, Vec3::new(0.24, 0.16, 0.16) * r, 8, p);
    // The broken neck, jagged, sunk into the ground.
    let start = env.mark();
    env.lathe(
        at3(0.0, -0.75, -0.05),
        rot * Quat::from_rotation_x(PI),
        &[(0.42 * r, 0.0), (0.4 * r, 0.35 * r)],
        10,
        (0, 0.0),
        p,
    );
    let neck_end = (at3(0.0, -0.75, -0.05) - rot * Vec3::Y * (0.35 * r)).y;
    jag_top(env, start, neck_end, 0.12 * r, v.seed);
    match variant % 4 {
        0 | 2 => {
            // A crown of rays around the crown of the head (gilded on 2).
            let crown = if variant % 4 == 2 { Paint::new(Key::Metal, c.gold).ink(INK_S) } else { pale };
            let band = at3(0.0, 0.66, 0.1);
            let brot = rot * Quat::from_rotation_x(0.35);
            env.lathe(band, brot, &[(0.62 * r, 0.0), (0.66 * r, 0.12 * r), (0.62 * r, 0.2 * r)], 14, (0, 0.0), crown);
            for k in 0..9 {
                let a = -1.3 + k as f32 * (2.6 / 8.0);
                let d = Vec3::new(a.sin(), 0.0, a.cos());
                let p0 = band + brot * (d * 0.62 * r + Vec3::Y * 0.1 * r);
                let ray = brot * (d * 0.55 + Vec3::Y).normalize();
                env.cylinder(
                    p0,
                    Quat::from_rotation_arc(Vec3::Y, ray),
                    0.09 * r,
                    0.0,
                    (0.4 + 0.12 * ((k % 2) as f32)) * r,
                    5,
                    crown,
                );
            }
        }
        1 => {
            // A braided beard spilling from the chin.
            for k in 0..7 {
                let x = -0.36 + k as f32 * 0.12;
                let len = (0.5 + 0.18 * v.f()) * r;
                let root = at3(x, -0.52, 0.66);
                let dir = rot * Vec3::new(x * 0.4, -1.0, 0.35).normalize();
                env.tube(&[root, root + dir * len * 0.5, root + dir * len], &[0.08 * r, 0.07 * r, 0.02 * r], 5, p);
            }
        }
        _ => {
            // A great crack across the face, glowing from inside.
            let glow = Paint::new(Key::Glow, c.molten);
            env.tube(
                &[
                    at3(-0.36, 0.8, 0.45),
                    at3(-0.12, 0.4, 0.84),
                    at3(0.08, 0.02, 1.0),
                    at3(0.3, -0.4, 0.86),
                    at3(0.42, -0.62, 0.6),
                ],
                &[0.02 * r, 0.035 * r, 0.03 * r, 0.03 * r, 0.015 * r],
                4,
                glow,
            );
        }
    }
    // Rubble heaped where it struck, a crater of cracks.
    for k in 0..5 {
        let d = dir(k as f32 * 1.4 + v.f());
        let rr = r * v.r(0.12, 0.22);
        env.rock(
            base + wd(d) * r * v.r(0.9, 1.25) + Vec3::Y * rr * 0.3,
            Quat::IDENTITY,
            Vec3::splat(rr),
            v.seed + k,
            0.4,
            Paint::new(Key::Rock, c.rock).ink(INK_S),
        );
    }
}

fn fallen_column(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, r: f32) {
    let mut v = Vr::new(from, 17);
    let d = (to - from).normalize_or(Vec2::X);
    let len = from.distance(to);
    let stone = vary(c.stone, v.f(), 0.06);
    let p = Paint::new(Key::Stone, stone).ink(INK);
    let lie = face(d) * Quat::from_rotation_x(FRAC_PI_2);
    let base = w3(from, r * 0.92);
    // Base drum with its torus, then the shaft to the broken end.
    env.lathe(
        base,
        lie,
        &[(r * 1.15, -0.25), (r * 1.18, -0.1), (r * 1.05, 0.05), (r * 0.98, 0.18)],
        14,
        (0, 0.0),
        Paint::new(Key::Stone, lighten(stone, 1.2)).ink(INK),
    );
    let shaft_len = (len - r * 0.4).max(0.5);
    let start = env.mark();
    env.lathe(base, lie, &[(r * 0.98, 0.1), (r * 0.94, shaft_len * 0.5), (r * 0.88, shaft_len)], 16, (8, 0.1), p);
    // Jag the far end, and pull its ink hull back behind the break.
    let tip = base + lie * Vec3::Y * shaft_len;
    let axis = lie * Vec3::Y;
    let buf = env.buf(Key::Stone);
    for i in start.0..buf.pos.len() {
        let q = Vec3::from(buf.pos[i]);
        if (q - tip).dot(axis).abs() < 0.03 {
            let k = h01((q.x * 16.0) as i32 as u32 ^ ((q.y * 16.0) as i32 as u32).rotate_left(7), v.seed);
            buf.pos[i] = (q - axis * (k * r * 0.5)).to_array();
        }
    }
    let ink = env.buf(Key::Ink);
    for i in start.1..ink.pos.len() {
        let q = Vec3::from(ink.pos[i]);
        let over = (q - tip).dot(axis) + r * 0.5;
        if over > 0.0 {
            ink.pos[i] = (q - axis * over).to_array();
        }
    }
    // A drum rolled off the end.
    let dd = Vec2::new(-d.y, d.x) * v.sign();
    let drum = w3(to + d * (r * 0.9) + dd * (r * 0.8), r * 0.86);
    let rrot = face(dd.lerp(d, 0.3)) * Quat::from_rotation_x(FRAC_PI_2);
    env.lathe(drum - rrot * Vec3::Y * (r * 0.5), rrot, &[(r * 0.86, 0.0), (r * 0.84, r * 1.0)], 14, (12, 0.1), p);
}

fn great_anvil(env: &mut Env, c: &Colors, at: Vec2, r: f32, horn: Vec2) {
    let base = w3(at, 0.0);
    // Local +x runs toward the horn, +z across the face.
    let rot = face(Vec2::new(horn.y, -horn.x));
    let iron = Paint::new(Key::Metal, c.iron).ink(INK);
    let dark_iron = Paint::new(Key::Metal, lighten(c.iron, 0.7)).ink(INK);
    let stone = Paint::new(Key::Stone, lighten(c.stone, 0.92)).ink(INK);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK_S);
    // Stepped stone footing with a trim course.
    env.block(base + Vec3::Y * 0.22, rot, Vec3::new(r * 1.0, 0.22, r * 0.72), 0.06, stone);
    env.block(base + Vec3::Y * 0.5, rot, Vec3::new(r * 0.84, 0.08, r * 0.6), 0.03, trim);
    env.block(base + Vec3::Y * 0.78, rot, Vec3::new(r * 0.7, 0.2, r * 0.5), 0.05, stone);
    let s = r / 1.75;
    let y0 = 0.98;
    // The anvil, split through its waist: each half is extruded from the side profile and leans
    // a little apart, molten light in the crack between them.
    let feet = [Vec2::new(-0.95, 0.0), Vec2::new(0.85, 0.0), Vec2::new(0.4, 0.7), Vec2::new(-0.55, 0.7)];
    let waist = [Vec2::new(-0.5, 0.68), Vec2::new(0.35, 0.68), Vec2::new(0.6, 1.2), Vec2::new(-0.8, 1.2)];
    let face_slab = [Vec2::new(-1.35, 1.18), Vec2::new(0.9, 1.18), Vec2::new(0.9, 1.58), Vec2::new(-1.35, 1.58)];
    for (side, shift) in [(-1.0f32, -0.07f32), (1.0, 0.07)] {
        let lean = rot * Quat::from_rotation_z(-side * 0.03);
        let origin = base + Vec3::Y * y0 + rot * Vec3::X * (shift * s);
        let clip = |poly: &[Vec2]| -> Vec<Vec2> {
            // Keep the half on this side of x = 0 (a vertical split through the waist).
            let mut out = Vec::new();
            for i in 0..poly.len() {
                let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
                let (ia, ib) = (a.x * side >= 0.0, b.x * side >= 0.0);
                if ia {
                    out.push(a);
                }
                if ia != ib {
                    let t = a.x / (a.x - b.x);
                    out.push(a + (b - a) * t);
                }
            }
            out.iter().map(|p| *p * s).collect()
        };
        // Profiles live in the local x–y plane; extrude through ±z.
        let stand = lean * Quat::from_rotation_x(FRAC_PI_2);
        for (poly, depth, paint) in
            [(&feet[..], 0.62, dark_iron), (&waist[..], 0.42, iron), (&face_slab[..], 0.5, iron)]
        {
            let pts: Vec<Vec2> = clip(poly).iter().map(|p| Vec2::new(p.x, -p.y)).collect();
            if pts.len() >= 3 {
                env.extrude(origin, stand, &pts, -depth * s, depth * s, paint);
            }
        }
        if side > 0.0 {
            // The horn: a tapering cone off the face.
            let root = origin + lean * Vec3::new(0.9 * s, 1.4 * s, 0.0);
            env.lathe(
                root,
                lean * Quat::from_rotation_z(-FRAC_PI_2),
                &[(0.26 * s, 0.0), (0.2 * s, 0.5 * s), (0.02 * s, 1.15 * s)],
                10,
                (0, 0.0),
                iron,
            );
        } else {
            // The heel's hardy and pritchel holes.
            for x in [-1.1f32, -0.8] {
                env.block(
                    origin + lean * Vec3::new(x * s, 1.585 * s, 0.0),
                    lean,
                    Vec3::new(0.07, 0.01, 0.07) * s,
                    0.0,
                    Paint::new(Key::Stone, hex("#140C08")),
                );
            }
        }
    }
    // Molten light in the split, and gold runes along the face.
    let glow = Paint::new(Key::Glow, c.molten);
    env.block(base + Vec3::Y * (y0 + 0.8 * s), rot, Vec3::new(0.05 * s, 0.8 * s, 0.4 * s), 0.0, glow);
    env.disc(base + Vec3::Y * 0.9, r * 0.55, 12, lin(hdr(c.molten, 0.35)), [0.0; 4], Key::Glow);
    for k in 0..4 {
        let x = -1.1 + k as f32 * 0.6;
        if x.abs() < 0.15 {
            continue;
        }
        env.block(
            base + Vec3::Y * y0 + rot * Vec3::new(x * s, 1.38 * s, 0.505 * s),
            rot,
            Vec3::new(0.1, 0.1, 0.01) * s,
            0.0,
            Paint::new(Key::Glow, hdr(c.gold, 1.6)),
        );
    }
    // A god's hammer stands on its head behind the anvil, the haft raised to the sky: the tall
    // mark that finds a great forge from across the map (the fixed camera sees heights, not plans).
    let foot = base + rot * Vec3::new(-0.7 * s, 0.0, -s);
    let head = Vec3::new(0.55 * s, 0.45 * s, 0.42 * s);
    let tilt = rot * Quat::from_rotation_x(0.08) * Quat::from_rotation_z(0.06);
    env.block(foot + Vec3::Y * head.y, tilt, head, 0.06, dark_iron);
    env.block(
        foot + Vec3::Y * (head.y * 2.0 + 0.04),
        tilt,
        Vec3::new(head.x * 0.8, 0.06, head.z * 0.8),
        0.02,
        Paint::new(Key::Metal, c.bronze).ink(INK_S),
    );
    let haft = 3.4 * r;
    let root = foot + Vec3::Y * (head.y * 2.0);
    env.cylinder(root, tilt, 0.17 * s, 0.14 * s, haft, 8, Paint::new(Key::Metal, lighten(c.bronze, 0.8)).ink(INK));
    let up = tilt * Vec3::Y;
    for k in 0..3 {
        let at = root + up * (haft * (0.72 + 0.07 * k as f32));
        env.cylinder(at, tilt, 0.2 * s, 0.2 * s, 0.12 * s, 8, Paint::new(Key::Metal, c.gold).ink(INK_S));
    }
    env.ball(root + up * (haft + 0.12 * s), tilt, Vec3::splat(0.26 * s), 8, Paint::new(Key::Metal, c.gold).ink(INK_S));
    env.flames.push(Flame { at: base + Vec3::Y * (y0 + 1.6 * s), color: c.molten, power: 0.8, range: 9.0 });
}

fn crucible(env: &mut Env, c: &Colors, at: Vec2, r: f32) {
    let base = w3(at, 0.0);
    let stone = Paint::new(Key::Stone, c.stone).ink(INK);
    let iron = Paint::new(Key::Metal, c.iron).ink(INK);
    // The pit: a curb ring around a molten pool.
    let curb = [(r - 0.1, 0.4), (r - 0.1, -0.5), (r + 0.45, -0.5), (r + 0.45, 0.3), (r + 0.3, 0.4), (r - 0.1, 0.4)];
    env.lathe(base, Quat::IDENTITY, &curb, 18, (0, 0.0), stone);
    // A slag pool crusting over, the heat showing in the cracks.
    coal_bed(env, c, base + Vec3::Y * 0.12, r - 0.05, hp(at, 19).to_bits());
    // The crucible hangs above it, brimming.
    let hang = 2.6;
    let bowl = [
        (0.25 * r, hang),
        (0.55 * r, hang + 0.3),
        (0.72 * r, hang + 0.9),
        (0.74 * r, hang + 1.5),
        (0.66 * r, hang + 1.52),
    ];
    env.lathe(base, Quat::IDENTITY, &bowl, 16, (0, 0.0), iron);
    env.lathe(
        base,
        Quat::IDENTITY,
        &[(0.76 * r, hang + 1.1), (0.76 * r, hang + 1.3)],
        16,
        (0, 0.0),
        Paint::new(Key::Metal, c.bronze),
    );
    coal_bed(env, c, base + Vec3::Y * (hang + 1.42), 0.64 * r, hp(at, 20).to_bits());
    // A pour spout dribbling into the pit.
    let lip = base + Vec3::new(0.72 * r, hang + 1.45, 0.0);
    env.tube(
        &[lip, lip + Vec3::new(0.3, -0.4, 0.0), base + Vec3::new(0.95 * r, 0.1, 0.0)],
        &[0.1, 0.07, 0.05],
        5,
        Paint::new(Key::Glow, c.molten),
    );
    for k in 0..4 {
        let a = k as f32 / 4.0 * TAU + 0.4;
        let rim = base + Vec3::new(a.cos() * 0.7 * r, hang + 1.4, a.sin() * 0.7 * r);
        chains(env, c, rim, base + Vec3::new(a.cos() * 0.3 * r, hang + 12.0, a.sin() * 0.3 * r), 0.0);
    }
    env.flames.push(Flame { at: base + Vec3::Y * 1.2, color: c.molten, power: 2.2, range: 14.0 });
}

fn great_brazier(env: &mut Env, c: &Colors, at: Vec2, r: f32) {
    let base = w3(at, 0.0);
    let bronze = Paint::new(Key::Metal, c.bronze).ink(INK);
    let stone = Paint::new(Key::Stone, c.trim).ink(INK);
    env.lathe(
        base,
        Quat::IDENTITY,
        &[(r * 0.95, 0.0), (r * 0.95, 0.3), (r * 0.8, 0.36), (r * 0.8, 0.5)],
        16,
        (0, 0.0),
        stone,
    );
    let bowl_y = 2.3 + r * 0.3;
    for k in 0..3 {
        let a = k as f32 / 3.0 * TAU + 0.3;
        let d = Vec3::new(a.cos(), 0.0, a.sin());
        let pts = [
            base + d * r * 0.72 + Vec3::Y * 0.5,
            base + d * r * 0.35 + Vec3::Y * (bowl_y * 0.55),
            base + d * r * 0.55 + Vec3::Y * bowl_y,
        ];
        env.tube(&pts, &[0.16, 0.12, 0.14], 6, bronze);
        // Lion-paw foot.
        env.ball(pts[0], Quat::IDENTITY, Vec3::new(0.24, 0.16, 0.24), 6, bronze);
    }
    let bowl = [
        (r * 0.3, bowl_y - 0.2),
        (r * 0.8, bowl_y + 0.2),
        (r * 1.05, bowl_y + 0.75),
        (r * 1.1, bowl_y + 0.9),
        (r * 1.0, bowl_y + 0.9),
        (r * 0.97, bowl_y + 0.8),
    ];
    env.lathe(base, Quat::IDENTITY, &bowl, 18, (0, 0.0), bronze);
    env.lathe(
        base,
        Quat::IDENTITY,
        &[(r * 1.08, bowl_y + 0.5), (r * 1.08, bowl_y + 0.62)],
        18,
        (0, 0.0),
        Paint::new(Key::Metal, c.gold),
    );
    coal_bed(env, c, base + Vec3::Y * (bowl_y + 0.78), r * 0.95, hp(at, 22).to_bits());
    let seed = hp(at, 21).to_bits();
    env.flame(base + Vec3::Y * (bowl_y + 0.7), 2.0 + r * 0.45, c, seed);
    for k in 0..3u32 {
        let a = k as f32 / 3.0 * TAU + h01(seed, k) * 0.8;
        let off = Vec3::new(a.cos(), 0.0, a.sin()) * (r * 0.5);
        env.flame(base + off + Vec3::Y * (bowl_y + 0.72), 1.1 + r * 0.3, c, seed ^ ((k + 1) * 0x9E37));
    }
    env.flames.push(Flame { at: base + Vec3::Y * (bowl_y + 2.0), color: c.flame, power: 2.6, range: 18.0 });
}

/// Burning coals filling a bowl of radius `r` at `top`: a molten bed glowing hot at the heart and
/// dull at the rim, broken by dark clinker lumps, so it reads as fire and not as a lit plate.
fn coal_bed(env: &mut Env, c: &Colors, top: Vec3, r: f32, seed: u32) {
    env.disc(top, r, 14, lin(hdr(c.flame_core, 0.45)), lin(hdr(c.molten, 0.3)), Key::Glow);
    // Crust plates cover most of the bed, so the fire shows in the cracks between them
    // (spread by the golden angle for an even cover without a pattern).
    let n = 14;
    for k in 0..n {
        let a = k as f32 * 2.399 + h01(seed, k) * 0.5;
        let d = r * 0.88 * ((k as f32 + 0.5) / n as f32).sqrt();
        let s = r * (0.2 + 0.1 * h01(seed, k + 80));
        let col = mix(c.dark, hex("#140C0A"), 0.35 + 0.3 * h01(seed, k + 9));
        env.rock(
            top + Vec3::new(a.cos() * d, 0.02, a.sin() * d),
            Quat::from_rotation_y(a),
            Vec3::new(s, s * 0.28, s * 0.85),
            seed ^ k,
            0.3,
            Paint::new(Key::Rock, col),
        );
    }
}

fn sealed_gate(env: &mut Env, c: &Colors, at: Vec2, half: Vec2, height: f32) {
    let along_x = half.x >= half.y;
    let (hl, ht) = if along_x { (half.x, half.y) } else { (half.y, half.x) };
    let rot = if along_x { Quat::IDENTITY } else { Quat::from_rotation_y(FRAC_PI_2) };
    let base = w3(at, 0.0);
    let stone = Paint::new(Key::Stone, c.stone).ink(INK);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK);
    let bronze = Paint::new(Key::Metal, c.bronze).ink(INK_S);
    let at3 = |x: f32, y: f32, z: f32| base + rot * Vec3::new(x, y, z);
    let pier = (hl * 0.2).clamp(0.6, 1.0);
    let lintel_y = height * 0.78;
    // Steps before and behind.
    env.block(at3(0.0, 0.1, 0.0), rot, Vec3::new(hl + 0.3, 0.1, ht + 0.6), 0.03, trim);
    for s in [-1.0f32, 1.0] {
        let x = s * (hl - pier);
        env.block(at3(x, lintel_y * 0.5, 0.0), rot, Vec3::new(pier, lintel_y * 0.5, ht + 0.1), 0.06, stone);
        env.block(at3(x, 0.45, 0.0), rot, Vec3::new(pier + 0.12, 0.25, ht + 0.22), 0.04, trim);
    }
    env.block(at3(0.0, lintel_y + 0.45, 0.0), rot, Vec3::new(hl + 0.2, 0.45, ht + 0.25), 0.06, trim);
    // Pediment.
    let ped_h = (height - lintel_y - 0.9).max(0.8);
    env.extrude(
        at3(0.0, lintel_y + 0.9, 0.0),
        rot * Quat::from_rotation_x(-FRAC_PI_2),
        &[Vec2::new(-hl - 0.1, 0.0), Vec2::new(hl + 0.1, 0.0), Vec2::new(0.0, ped_h)],
        -(ht + 0.1),
        ht + 0.1,
        stone,
    );
    // The shut doors: bronze leaves with studs, a glowing seal down the seam.
    let dw = hl - pier * 2.0;
    for s in [-1.0f32, 1.0] {
        env.block(
            at3(s * dw * 0.5, lintel_y * 0.5, 0.0),
            rot,
            Vec3::new(dw * 0.5 - 0.03, lintel_y * 0.5, ht * 0.5),
            0.03,
            bronze,
        );
        for i in 0..3 {
            for j in 0..4 {
                let x = s * dw * (0.15 + 0.23 * i as f32);
                let y = lintel_y * (0.15 + 0.22 * j as f32);
                for z in [-1.0f32, 1.0] {
                    env.ball(at3(x, y, z * ht * 0.52), rot, Vec3::splat(0.07), 5, Paint::new(Key::Metal, c.gold));
                }
            }
        }
    }
    let seal = Paint::new(Key::Glow, c.glow);
    for z in [-1.0f32, 1.0] {
        env.block(at3(0.0, lintel_y * 0.5, z * ht * 0.52), rot, Vec3::new(0.035, lintel_y * 0.45, 0.01), 0.0, seal);
        let sig = at3(0.0, lintel_y * 0.55, z * (ht * 0.52 + 0.02));
        let r = (dw * 0.35).min(1.1);
        env.lathe(
            sig,
            rot * Quat::from_rotation_x(FRAC_PI_2 * z),
            &[(r, 0.0), (r * 0.82, 0.0), (r * 0.82, 0.02), (r, 0.02), (r, 0.0)],
            20,
            (0, 0.0),
            seal,
        );
    }
}

/// A gateway arch spanning `from`–`to` (the pier centres): piers on plinths with impost
/// capitals, a round (or, when the height is short, segmental) arch of voussoirs with a raised
/// keystone, spandrels and an entablature of three stones under a projecting cornice.
/// Variant 1 is broken; 2 adds a pediment; 3 hangs a caged lamp from the keystone.
fn arch(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, pier: f32, height: f32, variant: u8) {
    let mut v = Vr::new(from, 23);
    let d = (to - from).normalize_or(Vec2::X);
    let span = from.distance(to);
    let rot = face(Vec2::new(-d.y, d.x));
    let stone = vary(c.stone, v.f(), 0.05);
    let p = Paint::new(Key::Stone, stone).ink(INK);
    let trim = Paint::new(Key::Stone, lighten(stone, 1.22)).ink(INK);
    let mid = w3((from + to) * 0.5, 0.0);
    let at3 = |x: f32, y: f32, z: f32| mid + rot * Vec3::new(x, y, z);
    let variant = variant % 4;
    let broken = variant == 1;
    // Half depth of the arch body: a little thinner than the piers, which step out.
    let depth = pier * 0.82;
    let inner = (span * 0.5 - pier).max(0.6);
    let attic = (0.3 + 0.06 * height).min(0.75);
    let ring = (0.34 + inner * 0.07).min(0.6);
    let crown = height - attic;
    // A semicircle needs `inner` of rise; short arches go segmental (never flatter than a third).
    let rise = (crown - ring - 1.9).clamp(inner * 0.34, inner);
    let spring = crown - ring - rise;
    for (i, s) in [-1.0f32, 1.0].into_iter().enumerate() {
        let x = s * (inner + pier);
        let h = if broken && i == 1 { spring * v.r(0.45, 0.7) } else { spring };
        env.block(at3(x, 0.18, 0.0), rot, Vec3::new(pier + 0.12, 0.18, pier + 0.12), 0.04, trim);
        let start = env.mark();
        env.block(at3(x, 0.36 + (h - 0.36) * 0.5, 0.0), rot, Vec3::new(pier, (h - 0.36) * 0.5, pier), 0.05, p);
        if broken && i == 1 {
            jag_top(env, start, h, 0.45, v.seed);
            continue;
        }
        // Impost capital where the arch springs.
        env.block(at3(x, h - 0.12, 0.0), rot, Vec3::new(pier + 0.1, 0.12, pier + 0.1), 0.03, trim);
    }
    // The arch circle through both springers and the crown: centre height `cy`, radius `rr`.
    let rr = (inner * inner + rise * rise) / (2.0 * rise);
    let cy = spring + rise - rr;
    let th = ((spring - cy) / rr).clamp(-1.0, 1.0).asin();
    let sweep = PI - 2.0 * th;
    let arc_len = sweep * (rr + ring * 0.5);
    let n = (((arc_len / 0.62).round() as u32) | 1).clamp(7, 17);
    let q = |a: f32, r: f32| Vec2::new(a.cos() * r, cy + a.sin() * r);
    let stand = rot * Quat::from_rotation_x(-FRAC_PI_2);
    let keep = if broken { n / 3 } else { n };
    for k in 0..keep {
        let a0 = PI - th - sweep * k as f32 / n as f32;
        let a1 = PI - th - sweep * (k + 1) as f32 / n as f32;
        let key = k == n / 2;
        let out = if key { ring * 1.35 } else { ring };
        let outline = [q(a0, rr), q(a1, rr), q(a1, rr + out), q(a0, rr + out)];
        let tint = if key { lighten(stone, 1.3) } else { vary(stone, h01(k, v.seed), 0.07) };
        let dz = if key { depth + 0.06 } else { depth };
        env.extrude(mid, stand, &outline, -dz, dz, Paint::new(Key::Stone, tint).ink(INK_S));
    }
    if broken {
        // The rest of the arch and its attic fell outward: one stretch leans on the standing
        // pier, the rest lies broken beyond the stump (never across the lane the arch spans).
        let x = wd(d);
        let lean = rot * Quat::from_rotation_z(-0.9);
        env.block(w3(from, 0.0) - x * (pier + 0.9) + Vec3::Y * 1.3, lean, Vec3::new(span * 0.24, 0.32, depth), 0.05, p);
        env.block(
            w3(to, 0.0) + x * (pier + span * 0.25 + 0.4) + Vec3::Y * 0.3,
            rot * Quat::from_rotation_y(v.r(-0.4, 0.4)) * Quat::from_rotation_z(0.08),
            Vec3::new(span * 0.22, 0.3, depth),
            0.05,
            p,
        );
        rubble(env, c, to + d * (pier + 1.0), 1.0, 0);
        return;
    }
    // Spandrels: vertical strips from the extrados up to the attic, and the block over each pier.
    let fill = Paint::new(Key::Stone, lighten(stone, 0.9)).ink(INK_S);
    let strips = (n / 2) as usize;
    let half_w = inner + pier * 2.0;
    let x_spring = (rr + ring) * th.cos();
    for s in [-1.0f32, 1.0] {
        let over = [
            Vec2::new(s * half_w, spring),
            Vec2::new(s * x_spring, spring),
            Vec2::new(s * x_spring, crown),
            Vec2::new(s * half_w, crown),
        ];
        env.extrude(mid, stand, &over, -depth, depth, fill);
        for k in 0..strips {
            let a0 = th + (PI * 0.5 - th) * k as f32 / strips as f32;
            let a1 = th + (PI * 0.5 - th) * (k + 1) as f32 / strips as f32;
            let (p0, p1) = (q(a0, rr + ring), q(a1, rr + ring));
            if crown - p0.y.min(p1.y) < 0.04 {
                continue;
            }
            let (x0, x1) = (s * p0.x, s * p1.x);
            let strip = [Vec2::new(x0, p0.y), Vec2::new(x1, p1.y), Vec2::new(x1, crown), Vec2::new(x0, crown)];
            env.extrude(mid, stand, &strip, -depth * 0.97, depth * 0.97, Paint { ink: 0.0, ..fill });
        }
    }
    // Entablature: three stones with a raised keystone plaque, under a projecting cornice.
    let third = half_w * 2.0 / 3.0;
    for k in 0..3u32 {
        let x = -half_w + third * (k as f32 + 0.5);
        let tint = vary(stone, h01(k + 7, v.seed), 0.06);
        env.block(
            at3(x, crown + attic * 0.35, 0.0),
            rot,
            Vec3::new(third * 0.5 - 0.02, attic * 0.35, depth + 0.02),
            0.03,
            Paint::new(Key::Stone, tint).ink(INK),
        );
    }
    // The cornice stays close to the wall's value (a pale plank would glare from above), and
    // pedestals at its ends break the long top line.
    let cornice = Paint::new(Key::Stone, lighten(stone, 1.06)).ink(INK);
    env.block(
        at3(0.0, crown + attic * 0.85, 0.0),
        rot,
        Vec3::new(half_w + 0.14, attic * 0.15, depth + 0.12),
        0.03,
        cornice,
    );
    env.block(at3(0.0, crown + attic * 0.4, 0.0), rot, Vec3::new(0.42, attic * 0.42, depth + 0.1), 0.03, trim);
    if variant != 2 {
        for s in [-1.0f32, 1.0] {
            env.block(
                at3(s * (half_w - 0.4), height + 0.16, 0.0),
                rot,
                Vec3::new(0.38, 0.16, depth * 0.85),
                0.03,
                trim,
            );
        }
    }
    match variant {
        2 => {
            // A shallow pediment with an acroterion.
            let ped = (half_w * 0.36).min(1.4);
            env.extrude(
                at3(0.0, height, 0.0),
                stand,
                &[Vec2::new(-half_w, 0.0), Vec2::new(half_w, 0.0), Vec2::new(0.0, ped)],
                -depth,
                depth,
                p,
            );
            env.lathe(
                at3(0.0, height + ped - 0.1, 0.0),
                rot,
                &[(0.22, 0.0), (0.3, 0.2), (0.12, 0.45), (0.0, 0.55)],
                8,
                (0, 0.0),
                trim,
            );
        }
        3 => {
            // A caged lamp on a chain from the keystone.
            let top = at3(0.0, rr + cy, 0.0);
            let lamp = top - Vec3::Y * (rise * 0.45 + 0.5);
            env.tube(&[top, lamp + Vec3::Y * 0.35], &[0.03], 4, Paint::new(Key::Metal, c.iron));
            let iron = Paint::new(Key::Metal, c.iron).ink(INK_S);
            env.lathe(
                lamp,
                Quat::IDENTITY,
                &[(0.12, 0.35), (0.26, 0.3), (0.26, -0.2), (0.1, -0.32)],
                6,
                (0, 0.0),
                iron,
            );
            env.ball(lamp, Quat::IDENTITY, Vec3::splat(0.18), 6, Paint::new(Key::Glow, c.flame));
            env.flames.push(Flame { at: lamp, color: c.flame, power: 0.5, range: 8.0 });
        }
        _ => {}
    }
}

fn tree(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32, variant: u8) {
    let mut v = Vr::new(at, 29);
    let base = w3(at, 0.0);
    let bark = Paint::new(Key::Stone, vary(c.bark, v.f(), 0.1)).ink(INK);
    if variant % 2 == 1 {
        if c.abyss == AbyssKind::Water {
            // A giant mushroom: pale stalk, broad cap with glowing spots.
            let stalk = [(r * 0.55, 0.0), (r * 0.4, h * 0.4), (r * 0.34, h * 0.85), (r * 0.36, h)];
            env.lathe(base, Quat::IDENTITY, &stalk, 12, (0, 0.0), Paint::new(Key::Stone, hex("#CFC2A8")).ink(INK));
            let cr = r * 1.9;
            let cap =
                [(0.0, h - 0.1), (cr * 0.8, h - 0.05), (cr, h + 0.25), (cr * 0.7, h + cr * 0.45), (0.0, h + cr * 0.55)];
            env.lathe(base, Quat::IDENTITY, &cap, 16, (0, 0.0), Paint::new(Key::Cloth, hex("#7A3A6A")).ink(INK));
            for k in 0..7 {
                let a = k as f32 * 0.9 + v.f();
                let rr = cr * v.r(0.3, 0.75);
                let p = base + Vec3::new(a.cos() * rr, h + cr * 0.5 * (1.0 - rr / cr) + 0.28, a.sin() * rr);
                env.ball(p, Quat::IDENTITY, Vec3::new(0.12, 0.05, 0.12) * cr, 6, Paint::new(Key::Glow, c.crystal));
            }
            env.flames.push(Flame { at: base + Vec3::Y * (h + 0.6), color: c.crystal, power: 0.5, range: 8.0 });
        } else {
            // A broken stump.
            let start = env.mark();
            env.lathe(base, Quat::IDENTITY, &[(r * 1.1, 0.0), (r * 0.9, 0.35), (r * 0.82, h)], 12, (0, 0.0), bark);
            jag_top(env, start, h, 0.5, v.seed);
            tree_roots(env, base, r, 5, bark, &mut v);
        }
        return;
    }
    // Trunk: a leaning, tapering tube over a flared root plate.
    let lean = wd(dir(v.r(0.0, TAU))) * (h * 0.06);
    let pts: Vec<Vec3> = (0..=5)
        .map(|i| {
            let t = i as f32 / 5.0;
            base + Vec3::Y * (h * 0.62 * t) + lean * t * t + wd(dir(t * 3.0 + v.f())) * (r * 0.12 * t)
        })
        .collect();
    let radii: Vec<f32> = (0..=5).map(|i| r * (1.0 - 0.45 * i as f32 / 5.0)).collect();
    env.tube(&pts, &radii, 10, bark);
    tree_roots(env, base, r, 6, bark, &mut v);
    let top = pts[5];
    let charred = c.abyss == AbyssKind::Magma;
    // Branches and the canopy (a dead, ember-veined crown in the Cinder).
    let nb = 4 + v.i(2);
    for k in 0..nb {
        let a = k as f32 / nb as f32 * TAU + v.f();
        let d = Vec3::new(a.cos(), 0.0, a.sin());
        let from = pts[3 + (k % 2) as usize];
        let end = from + d * (h * v.r(0.22, 0.34)) + Vec3::Y * (h * v.r(0.12, 0.3));
        let midp = (from + end) * 0.5 + Vec3::Y * 0.4;
        env.tube(&[from, midp, end], &[r * 0.42, r * 0.26, r * 0.1], 6, bark);
        if charred {
            env.tube(&[midp, end + d * 0.5 + Vec3::Y * 0.6], &[r * 0.08, r * 0.02], 4, bark);
        } else {
            leaf_clump(env, c, end, h * v.r(0.13, 0.18), &mut v);
        }
    }
    if charred {
        env.tube(
            &[pts[1] + Vec3::X * r * 0.9, pts[3] + Vec3::X * r * 0.7],
            &[0.06, 0.03],
            4,
            Paint::new(Key::Glow, c.molten),
        );
    } else {
        leaf_clump(env, c, top + Vec3::Y * (h * 0.12), h * 0.22, &mut v);
    }
}

fn tree_roots(env: &mut Env, base: Vec3, r: f32, n: u32, bark: Paint, v: &mut Vr) {
    for k in 0..n {
        let a = k as f32 / n as f32 * TAU + v.f() * 0.6;
        let d = Vec3::new(a.cos(), 0.0, a.sin());
        let pts = [
            base + d * (r * 0.6) + Vec3::Y * (r * 0.9),
            base + d * (r * 1.3) + Vec3::Y * 0.25,
            base + d * (r * 2.1) - Vec3::Y * 0.1,
        ];
        env.tube(&pts, &[r * 0.35, r * 0.22, r * 0.06], 6, bark);
    }
}

fn leaf_clump(env: &mut Env, c: &Colors, at: Vec3, s: f32, v: &mut Vr) {
    let n = 3 + v.i(3);
    let under = mix(c.leaf_dark, hex("#0A0E12"), 0.25);
    for k in 0..n {
        let off = Vec3::new(v.r(-1.0, 1.0), v.r(-0.3, 0.6), v.r(-1.0, 1.0)) * s * 0.7;
        let rr = s * v.r(0.6, 1.0);
        let crown = lighten(vary(mix(c.leaf, c.leaf_dark, 0.15), v.f(), 0.1), 1.04);
        env.foliage(
            at + off,
            Quat::from_rotation_y(v.r(0.0, TAU)),
            Vec3::new(rr, rr * 0.72, rr),
            v.seed ^ (k * 131 + 7),
            under,
            crown,
            INK_S,
        );
    }
}

fn fallen_tree(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, r: f32) {
    let mut v = Vr::new(from, 31);
    let d = (to - from).normalize_or(Vec2::X);
    let n = Vec2::new(-d.y, d.x);
    let bark = Paint::new(Key::Stone, vary(c.bark, v.f(), 0.1)).ink(INK);
    let pts: Vec<Vec3> = (0..=6)
        .map(|i| {
            let t = i as f32 / 6.0;
            w3(from.lerp(to, t) + n * ((t * 5.0).sin() * r * 0.15), r * (0.85 - 0.25 * t))
        })
        .collect();
    let radii: Vec<f32> = (0..=6).map(|i| r * (1.0 - 0.4 * i as f32 / 6.0)).collect();
    env.tube(&pts, &radii, 10, bark);
    // The root plate stands on edge at the base, roots radiating.
    let plate = w3(from - d * (r * 0.4), r * 1.1);
    let rot = face(d);
    env.rock(
        plate,
        rot,
        Vec3::new(r * 1.9, r * 1.6, r * 0.45),
        v.seed,
        0.35,
        Paint::new(Key::Rock, mix(c.rock, c.bark, 0.5)).ink(INK),
    );
    for k in 0..7 {
        let a = k as f32 / 7.0 * TAU;
        let e = rot * Vec3::new(a.cos(), a.sin(), 0.0);
        env.tube(&[plate + e * r * 1.2, plate + e * r * 2.4 - rot * Vec3::Z * 0.3], &[r * 0.22, r * 0.05], 5, bark);
    }
    // The broken crown.
    let end = *pts.last().unwrap_or(&plate);
    for k in 0..4 {
        let a = k as f32 * 1.4 + v.f();
        let bd = wd(d) * 0.8 + Vec3::new(a.cos() * 0.6, a.sin().abs() * 0.8, a.sin() * 0.6);
        let tip = end + bd * (r * 2.5);
        env.tube(&[end, tip], &[r * 0.4, r * 0.1], 5, bark);
        if c.abyss == AbyssKind::Water {
            leaf_clump(env, c, tip, r * 1.1, &mut v);
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn crystal(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32, lean_to: Vec2, variant: u8) {
    let mut v = Vr::new(at, 37 + variant as u32);
    let base = w3(at, 0.0);
    let glow = Paint::new(Key::Glow, c.crystal).ink(INK_S);
    let lean = Quat::from_rotation_arc(Vec3::Y, (Vec3::Y + wd(lean_to) * 0.3).normalize());
    env.crystal_spike(base, lean * Quat::from_rotation_y(v.r(0.0, 1.0)), r * 0.5, h * 0.72, h * 0.28, 6, glow);
    let n = 3 + v.i(3);
    for k in 0..n {
        let a = k as f32 / n as f32 * TAU + v.f();
        let d = Vec3::new(a.cos(), 0.0, a.sin());
        let tilt = Quat::from_rotation_arc(Vec3::Y, (Vec3::Y + d * v.r(0.5, 1.0)).normalize());
        let s = v.r(0.3, 0.6);
        env.crystal_spike(base + d * r * 0.55, tilt, r * 0.28 * s * 1.6, h * s * 0.55, h * s * 0.2, 5, glow);
    }
    for k in 0..3 {
        let d = dir(k as f32 * 2.1 + v.f());
        let rr = r * v.r(0.3, 0.45);
        env.rock(
            base + wd(d) * r * 0.8,
            Quat::IDENTITY,
            Vec3::new(rr, rr * 0.6, rr),
            v.seed + k,
            0.4,
            Paint::new(Key::Rock, c.dark).ink(INK_S),
        );
    }
    env.disc(base + Vec3::Y * 0.03, r * 1.6, 12, lin(hdr(c.crystal, 0.35)), [0.0; 4], Key::Glow);
    env.flames.push(Flame { at: base + Vec3::Y * (h * 0.6), color: c.crystal, power: 0.6, range: 9.0 });
}

fn spiral_stair(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32, brk: Vec2) {
    let mut v = Vr::new(at, 41);
    let base = w3(at, 0.0);
    let stone = Paint::new(Key::Stone, c.stone).ink(INK);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK_S);
    let newel = r * 0.28;
    let start = env.mark();
    env.lathe(base, Quat::IDENTITY, &[(newel * 1.3, 0.0), (newel, 0.4), (newel, h)], 12, (0, 0.0), stone);
    jag_top(env, start, h, 0.6, v.seed);
    let rise = 0.36;
    let steps = ((h - 0.5) / rise) as u32;
    let a_break = brk.y.atan2(brk.x);
    let per = 0.42;
    for k in 0..steps {
        let a = k as f32 * per + a_break + 0.8;
        // Near the top the stair breaks off toward `brk`.
        if k > steps * 7 / 10 && v.f() < 0.55 {
            continue;
        }
        let a0 = a - per * 0.55;
        let a1 = a + per * 0.55;
        let q = |a: f32, rr: f32| Vec2::new(a.cos() * rr, -a.sin() * rr);
        let outline = [q(a0, newel * 0.9), q(a0, r), q(a1, r), q(a1, newel * 0.9)];
        let y = 0.25 + k as f32 * rise;
        env.extrude(base, Quat::IDENTITY, &outline, y, y + 0.2, if k % 4 == 0 { trim } else { stone });
    }
    // Fallen steps at its foot.
    for k in 0..3 {
        let d = wd(brk) + wd(dir(k as f32)) * 0.6;
        env.block(
            base + d.normalize() * (r * 1.3 + k as f32 * 0.6) + Vec3::Y * 0.12,
            Quat::from_rotation_y(v.r(0.0, TAU)),
            Vec3::new(0.7, 0.12, 0.3),
            0.03,
            stone,
        );
    }
}

fn inverted_column(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32) {
    let mut v = Vr::new(at, 43);
    let base = w3(at, 0.0);
    let tilt = Quat::from_rotation_z(v.r(-0.05, 0.05)) * Quat::from_rotation_x(v.r(-0.05, 0.05));
    let stone = Paint::new(Key::Stone, mix(c.stone, hex("#5A4A70"), 0.3)).ink(INK);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK);
    // Abacus on the ground, the echinus flaring down to it, the shaft rising to a broken base.
    env.block(base + Vec3::Y * 0.2, tilt, Vec3::new(r * 1.35, 0.2, r * 1.35), 0.04, trim);
    env.lathe(base, tilt, &[(r * 1.25, 0.4), (r * 0.92, 0.9), (r * 0.98, 0.98), (r * 0.9, 1.05)], 16, (0, 0.0), trim);
    let start = env.mark();
    env.lathe(base, tilt, &[(r * 0.9, 1.05), (r * 0.96, h * 0.5), (r, h)], 18, (12, 0.1), stone);
    jag_top(env, start, (base + tilt * Vec3::Y * h).y, 0.5, v.seed);
    // Fragments orbiting its top, a faint ring of light.
    let top = base + Vec3::Y * h;
    for k in 0..5 {
        let a = k as f32 / 5.0 * TAU + v.f();
        let p = top + Vec3::new(a.cos(), v.r(-0.4, 0.8), a.sin()) * (r * 1.8);
        env.block(
            p,
            Quat::from_rotation_y(a) * Quat::from_rotation_x(v.r(0.0, 1.0)),
            Vec3::new(0.3, 0.2, 0.25) * r.max(0.6),
            0.03,
            stone,
        );
    }
    env.lathe(
        top + Vec3::Y * 0.3,
        Quat::from_rotation_x(0.15),
        &[(r * 1.8, 0.0), (r * 1.72, 0.0), (r * 1.72, 0.03), (r * 1.8, 0.03), (r * 1.8, 0.0)],
        24,
        (0, 0.0),
        Paint::new(Key::Glow, hdr(c.glow, 0.6)),
    );
}

fn rift(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32, facing: Vec2) {
    let mut v = Vr::new(at, 47);
    let base = w3(at, 0.0);
    let rot = face(facing);
    let right = rot * Vec3::X;
    // A tear in the world standing on its edge: a jagged rim of light around a lightless
    // void, a white-hot seam down its middle, torn stone orbiting it.
    let n = 11;
    let fwd = rot * Vec3::Z;
    let jag: Vec<f32> = (0..=n).map(|_| 0.75 + 0.5 * v.f()).collect();
    let lens = |k: usize, w: f32| {
        let t = k as f32 / n as f32;
        (0.2 + (h - 0.2) * t, (t * PI).sin().powf(0.8) * w * jag[k])
    };
    let void = lin(mix(hex("#05020A"), c.dark, 0.15));
    for (w, col, off) in [
        (r * 1.05, lin(hdr(c.glow, 1.1)), 0.0f32),
        (r * 0.82, void, 0.025),
        (r * 0.82, void, -0.025),
        (r * 0.07, lin(c.flame_core), 0.05),
        (r * 0.07, lin(c.flame_core), -0.05),
    ] {
        for k in 1..=n {
            let ((y0, w0), (y1, w1)) = (lens(k - 1, w), lens(k, w));
            let o = fwd * off;
            env.sheet(
                [
                    base + o + Vec3::Y * y0 - right * w0,
                    base + o + Vec3::Y * y0 + right * w0,
                    base + o + Vec3::Y * y1 + right * w1,
                    base + o + Vec3::Y * y1 - right * w1,
                ],
                [col; 4],
                Key::Glow,
            );
        }
    }
    // Scorched ground with cracks of light under it.
    env.disc(base + Vec3::Y * 0.02, r * 1.6, 12, lin(mix(c.dark, hex("#0A0608"), 0.5)), lin(c.dark), Key::Stone);
    env.disc(base + Vec3::Y * 0.04, r * 0.9, 12, lin(hdr(c.glow, 0.3)), [0.0; 4], Key::Glow);
    let glow = Paint::new(Key::Glow, hdr(c.glow, 0.7));
    for k in 0..4 {
        let a = k as f32 / 4.0 * TAU + v.r(-0.5, 0.5);
        let p0 = base + wd(dir(a)) * (r * 0.3) + Vec3::Y * 0.04;
        let p1 = p0 + wd(dir(a + v.r(-0.4, 0.4))) * (r * v.r(0.8, 1.4));
        env.tube(&[p0, p1], &[0.06, 0.015], 4, glow);
    }
    for k in 0..7 {
        let a = k as f32 / 7.0 * TAU + v.f();
        let p = base + Vec3::new(a.cos(), 0.0, a.sin()) * (r * v.r(1.1, 1.8)) + Vec3::Y * v.r(0.5, h * 0.85);
        let spin = Quat::from_rotation_x(v.r(0.0, TAU)) * Quat::from_rotation_z(v.r(0.0, TAU));
        if k % 3 == 0 {
            env.crystal_spike(p, spin, 0.12, 0.3, 0.25, 4, Paint::new(Key::Glow, c.crystal));
        } else {
            let s = v.r(0.18, 0.4);
            env.rock(
                p,
                spin,
                Vec3::new(s, s * 0.6, s * 0.8),
                v.seed ^ k,
                0.4,
                Paint::new(Key::Rock, c.rock).ink(INK_S),
            );
        }
    }
    env.flames.push(Flame { at: base + Vec3::Y * (h * 0.5), color: c.glow, power: 1.2, range: 12.0 });
}

fn channel(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, width: f32) {
    let d = (to - from).normalize_or(Vec2::X);
    let len = from.distance(to);
    let n = Vec2::new(-d.y, d.x);
    let rot = face(n);
    let mid = (from + to) * 0.5;
    let dark = Paint::new(Key::Stone, c.dark);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK_S);
    let hw = width * 0.5;
    // Trench walls and floor, the liquid surface, curbstones along both banks.
    for s in [-1.0f32, 1.0] {
        env.block(w3(mid + n * (s * (hw + 0.1)), -0.55), rot, Vec3::new(len * 0.5, 0.55, 0.1), 0.0, dark);
    }
    for e in [from - d * 0.1, to + d * 0.1] {
        env.block(w3(e, -0.55), rot, Vec3::new(0.1, 0.55, hw + 0.2), 0.0, dark);
    }
    liquid_rect(env, w3(mid, -0.45), rot, Vec2::new(len * 0.5 + 0.1, hw + 0.15));
    // Curbstones: one ink hull per bank, painted blocks along it.
    for side in [-1.0f32, 1.0] {
        let at = mid + n * (side * (hw + 0.28));
        env.block_raw(
            w3(at, 0.06),
            rot,
            Vec3::new(len * 0.5 + 0.3 + INK_S, 0.1 + INK_S, 0.3 + INK_S),
            0.0,
            Key::Ink,
            [1.0; 4],
            false,
        );
    }
    let mut s = -len * 0.5 - 0.3;
    let mut k = 0u32;
    while s < len * 0.5 + 0.25 {
        let l = (1.2 + 0.6 * h01(k, 5)).min(len * 0.5 + 0.3 - s);
        for side in [-1.0f32, 1.0] {
            let at = mid + d * (s + l * 0.5) + n * (side * (hw + 0.28));
            let col = lin(vary(c.trim, h01(k * 2 + (side > 0.0) as u32, 9), 0.1));
            env.block(
                w3(at, 0.06),
                rot,
                Vec3::new(l * 0.5 - 0.02, 0.1, 0.3),
                0.0,
                Paint { color: col, ink: 0.0, ..trim },
            );
        }
        s += l;
        k += 1;
    }
    if c.abyss == AbyssKind::Magma {
        env.flames.push(Flame { at: w3(mid, 0.8), color: c.molten, power: 0.9, range: len.max(8.0) * 0.6 });
    }
}

/// A liquid surface rectangle (local x/z half extents) at `centre`.
fn liquid_rect(env: &mut Env, centre: Vec3, rot: Quat, half: Vec2) {
    let q = |x: f32, z: f32| centre + rot * Vec3::new(x, 0.0, z);
    let w = [1.0; 4];
    env.sheet([q(-half.x, half.y), q(half.x, half.y), q(half.x, -half.y), q(-half.x, -half.y)], [w; 4], Key::Liquid);
}

/// A stone bridge from bank to bank; `deep` > 0 hangs piers that far down into a chasm.
pub fn bridge(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, width: f32, deep: f32) {
    let d = (to - from).normalize_or(Vec2::X);
    let n = Vec2::new(-d.y, d.x);
    let len = from.distance(to) + 1.2;
    let mid = (from + to) * 0.5;
    // Local +Z runs along the span, +X across it.
    let rot = face(d);
    let stone = Paint::new(Key::Stone, c.stone).ink(INK);
    let trim = Paint::new(Key::Stone, c.trim).ink(INK_S);
    let hw = width * 0.5;
    let mut v = Vr::new(from, 53);
    // Deck: courses of setts across the span, staggered like a laid road and slightly humped;
    // a curb along each edge.
    let courses = (len / 1.1).ceil().max(1.0) as u32;
    let lane = hw - 0.3;
    for k in 0..courses {
        let t = (k as f32 + 0.5) / courses as f32;
        let s = -len * 0.5 + len * t;
        let hump = 0.12 * (1.0 - (2.0 * t - 1.0).powi(2));
        let piece = len / courses as f32 * 0.5 - 0.025;
        let mut x = -lane;
        let mut first = true;
        while x < lane - 0.05 {
            let w = if first { v.r(0.4, 1.3) } else { v.r(0.9, 1.6) }.min(lane - x);
            let w = if lane - x - w < 0.4 { lane - x } else { w };
            first = false;
            // Worn, soot-dark setts: the deck sits under the heroes' value, like the roads.
            let col = vary(lighten(mix(c.stone, c.dark, 0.35), 0.8), v.f(), 0.12);
            env.block(
                w3(mid + d * s + n * (x + w * 0.5), -0.14 + hump),
                rot,
                Vec3::new(w * 0.5 - 0.025, 0.2, piece),
                0.0,
                Paint::new(Key::Stone, col),
            );
            x += w;
        }
    }
    // Under-structure: a beam under the deck, and over a chasm two piers dropping into it.
    env.block(w3(mid, -0.62), rot, Vec3::new(hw - 0.3, 0.3, len * 0.5 - 0.2), 0.04, stone);
    // The deck's thickness shows: an inked fascia down each side, so the span reads as a slab
    // standing over the pit, not a carpet on it.
    for side in [-1.0f32, 1.0] {
        let edge = mid + n * (side * (hw + 0.02));
        env.block(w3(edge, -0.42), rot, Vec3::new(0.16, 0.5, len * 0.5 - 0.05), 0.03, trim);
        // Corbels under the fascia.
        let corbels = (len / 2.2).ceil() as u32;
        for k in 0..=corbels {
            let s = -len * 0.5 + 0.4 + (len - 0.8) * k as f32 / corbels.max(1) as f32;
            env.block(w3(edge + d * s, -1.0), rot, Vec3::new(0.2, 0.2, 0.22), 0.02, stone);
        }
    }
    // A painted shadow on the pit below, thrown away from the key light.
    let shade = [0.02, 0.012, 0.01, 1.0];
    let off = Vec2::new(0.45, 0.35);
    let q = |s: f32, x: f32| {
        let p = mid + d * s + n * x + off;
        Vec3::new(p.x, crate::world::LIQUID_Y + 0.03, -p.y)
    };
    let (hl, hx) = (len * 0.5 - 0.3, hw + 0.35);
    env.sheet([q(-hl, -hx), q(hl, -hx), q(hl, hx), q(-hl, hx)], [shade; 4], Key::Stone);
    env.sheet([q(-hl, -hx), q(-hl, hx), q(hl, hx), q(hl, -hx)], [shade; 4], Key::Stone);
    if deep > 0.0 {
        for s in [-0.28f32, 0.28] {
            let at = mid + d * (s * len);
            env.block(
                w3(at, -0.6 - deep * 0.5),
                rot,
                Vec3::new(hw - 0.6, deep * 0.5, 0.55),
                0.06,
                Paint::new(Key::Rock, c.rock).ink(INK),
            );
        }
    }
    // Balustrades: a solid parapet with a coping rail, taller end posts with a finial.
    for side in [-1.0f32, 1.0] {
        let rail = mid + n * (side * (hw - 0.18));
        env.block(w3(rail, 0.3), rot, Vec3::new(0.2, 0.4, len * 0.5), 0.02, trim);
        env.block(w3(rail, 0.76), rot, Vec3::new(0.26, 0.07, len * 0.5 - 0.1), 0.0, trim);
        let posts = (len / 1.9).ceil() as u32;
        for k in 0..=posts {
            let s = -len * 0.5 + 0.2 + (len - 0.4) * k as f32 / posts as f32;
            let big = k == 0 || k == posts;
            if big {
                env.block(w3(rail + d * s, 0.48), rot, Vec3::new(0.24, 0.48, 0.24), 0.04, trim);
                env.ball(w3(rail + d * s, 1.05), Quat::IDENTITY, Vec3::splat(0.16), 6, trim);
            } else {
                env.block(w3(rail + d * s, 0.36), rot, Vec3::new(0.09, 0.26, 0.09), 0.0, stone);
            }
        }
    }
}

fn pool(env: &mut Env, c: &Colors, at: Vec2, half: Vec2) {
    let trim = Paint::new(Key::Stone, c.trim).ink(INK_S);
    let dark = Paint::new(Key::Stone, c.dark);
    liquid_rect(env, w3(at, -0.18), Quat::IDENTITY, half + Vec2::splat(0.1));
    // Inner walls and the stone lip.
    for (o, h) in [(Vec2::new(0.0, half.y), Vec2::new(half.x, 0.06)), (Vec2::new(half.x, 0.0), Vec2::new(0.06, half.y))]
    {
        for s in [-1.0f32, 1.0] {
            env.slab(at + o * s, h, -0.3, 0.0, 0.0, dark);
            env.slab(at + o * s + o.normalize() * s * 0.18, h + Vec2::splat(0.2), 0.0, 0.12, 0.03, trim);
        }
    }
}

fn overgrowth(env: &mut Env, c: &Colors, at: Vec2, r: f32, variant: u8) {
    let mut v = Vr::new(at, 59 + variant as u32);
    let base = w3(at, 0.0);
    let n = ((r * r * 2.2) as u32).clamp(3, 18);
    match c.abyss {
        AbyssKind::Magma => {
            // Ash drifts and cinders with ember specks, a few dead tufts.
            for k in 0..(n / 2).max(2) {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt() * 0.8);
                let rr = v.r(0.4, 0.9);
                env.rock(
                    p,
                    Quat::from_rotation_y(v.r(0.0, TAU)),
                    Vec3::new(rr, rr * 0.22, rr * 0.8),
                    v.seed + k,
                    0.3,
                    Paint::new(Key::Rock, lighten(c.rock, 0.75)),
                );
            }
            for _ in 0..n {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt()) + Vec3::Y * 0.06;
                env.block(
                    p,
                    Quat::from_rotation_y(v.r(0.0, TAU)),
                    Vec3::splat(0.035),
                    0.0,
                    Paint::new(Key::Glow, c.molten),
                );
            }
            grass(env, base, r, n / 3, hex("#6A5A48"), hex("#2A2018"), 0.45, &mut v);
        }
        AbyssKind::Water => {
            grass(env, base, r, n, c.leaf, c.leaf_dark, 0.7, &mut v);
            // Ferns and a few glowing flowers.
            for _ in 0..(n / 4).max(1) {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt() * 0.8);
                fern(env, c, p, v.r(0.6, 1.0), &mut v);
            }
            for _ in 0..(n / 5) {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt()) + Vec3::Y * 0.35;
                env.ball(p, Quat::IDENTITY, Vec3::splat(0.07), 5, Paint::new(Key::Glow, c.crystal));
            }
        }
        AbyssKind::Sky => {
            // Lichen crusts and star-glass flecks.
            for _ in 0..(n / 2).max(2) {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt() * 0.8) + Vec3::Y * 0.015;
                env.disc(p, v.r(0.3, 0.7), 7, lin(c.leaf), lin(lighten(c.leaf, 0.7)), Key::Cloth);
            }
            for _ in 0..n {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt());
                env.crystal_spike(
                    p,
                    Quat::from_rotation_z(v.r(-0.4, 0.4)),
                    0.05,
                    0.12,
                    0.1,
                    4,
                    Paint::new(Key::Glow, c.crystal),
                );
            }
            grass(env, base, r, n / 3, c.leaf, c.leaf_dark, 0.4, &mut v);
        }
        AbyssKind::Chaos => {
            grass(env, base, r, n / 2, c.leaf, c.leaf_dark, 0.55, &mut v);
            for _ in 0..n {
                let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt()) + Vec3::Y * v.r(0.2, 1.2);
                env.block(
                    p,
                    Quat::from_rotation_x(v.r(0.0, 3.0)) * Quat::from_rotation_y(v.r(0.0, 3.0)),
                    Vec3::splat(0.05),
                    0.0,
                    Paint::new(Key::Glow, c.glow),
                );
            }
        }
    }
}

/// Grass tufts: crossed blades, dark at the root, light at the tips.
#[allow(clippy::too_many_arguments)]
fn grass(env: &mut Env, base: Vec3, r: f32, n: u32, tip: Color, root: Color, h: f32, v: &mut Vr) {
    for _ in 0..n {
        let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt());
        let hh = h * v.r(0.6, 1.2);
        let blades = 3 + v.i(3);
        for b in 0..blades {
            let a = b as f32 / blades as f32 * PI + v.f();
            let side = Vec3::new(a.cos(), 0.0, a.sin()) * 0.09;
            let bend = Vec3::new(v.r(-0.2, 0.2), 0.0, v.r(-0.2, 0.2));
            let top = p + Vec3::Y * hh + bend + Vec3::new(a.sin(), 0.0, -a.cos()) * v.r(-0.15, 0.15);
            let cr = lin(root);
            let ct = lin(vary(tip, v.f(), 0.15));
            env.sheet([p - side, p + side, top + side * 0.15, top - side * 0.15], [cr, cr, ct, ct], Key::Cloth);
        }
    }
}

fn fern(env: &mut Env, c: &Colors, p: Vec3, s: f32, v: &mut Vr) {
    let fronds = 5 + v.i(3);
    for f in 0..fronds {
        let a = f as f32 / fronds as f32 * TAU + v.f();
        let d = Vec3::new(a.cos(), 0.0, a.sin());
        let side = Vec3::new(-a.sin(), 0.0, a.cos()) * 0.16 * s;
        let mid = p + d * 0.45 * s + Vec3::Y * 0.42 * s;
        let tip = p + d * 0.95 * s + Vec3::Y * 0.2 * s;
        let (cr, cm, ct) = (lin(c.leaf_dark), lin(c.leaf), lin(lighten(c.leaf, 1.3)));
        env.sheet([p, p + side * 0.2, mid + side, mid - side], [cr, cr, cm, cm], Key::Cloth);
        env.sheet([mid - side, mid + side, tip + side * 0.1, tip - side * 0.1], [cm, cm, ct, ct], Key::Cloth);
    }
}

fn roots(env: &mut Env, c: &Colors, from: Vec2, to: Vec2, width: f32) {
    let mut v = Vr::new(from, 61);
    let d = (to - from).normalize_or(Vec2::X);
    let n = Vec2::new(-d.y, d.x);
    let bark = Paint::new(Key::Stone, c.bark).ink(INK_S);
    let k = 6;
    let pts: Vec<Vec3> = (0..=k)
        .map(|i| {
            let t = i as f32 / k as f32;
            w3(from.lerp(to, t) + n * v.r(-0.3, 0.3) * width, width * 0.25 * (1.0 - t * 0.5))
        })
        .collect();
    let radii: Vec<f32> = (0..=k).map(|i| width * 0.5 * (1.0 - 0.7 * i as f32 / k as f32)).collect();
    env.tube(&pts, &radii, 6, bark);
    if c.abyss == AbyssKind::Water {
        let vein: Vec<Vec3> = pts.iter().map(|p| *p + Vec3::Y * width * 0.22).collect();
        let vr: Vec<f32> = radii.iter().map(|r| r * 0.12).collect();
        env.tube(&vein, &vr, 4, Paint::new(Key::Glow, hdr(c.crystal, 0.6)));
    }
}

fn rubble(env: &mut Env, c: &Colors, at: Vec2, r: f32, variant: u8) {
    let mut v = Vr::new(at, 67 + variant as u32);
    let base = w3(at, 0.0);
    let n = 4 + v.i(4);
    for k in 0..n {
        let p = base + wd(dir(v.r(0.0, TAU))) * (r * v.f().sqrt() * 0.85);
        let s = v.r(0.18, 0.42) * (0.6 + r * 0.35);
        match (variant + k as u8) % 3 {
            0 => env.block(
                p + Vec3::Y * s * 0.5,
                Quat::from_rotation_y(v.r(0.0, TAU)) * Quat::from_rotation_x(v.r(-0.4, 0.4)),
                Vec3::new(s * 1.3, s * 0.7, s),
                0.03,
                Paint::new(Key::Stone, vary(c.stone, v.f(), 0.12)).ink(INK_S),
            ),
            1 => env.rock(
                p + Vec3::Y * s * 0.3,
                Quat::IDENTITY,
                Vec3::new(s, s * 0.7, s),
                v.seed + k,
                0.45,
                Paint::new(Key::Rock, vary(c.rock, v.f(), 0.1)).ink(INK_S),
            ),
            _ if c.abyss == AbyssKind::Magma => env.rock(
                p + Vec3::Y * s * 0.2,
                Quat::IDENTITY,
                Vec3::new(s, s * 0.5, s),
                v.seed + k,
                0.5,
                Paint::new(Key::Rock, hex("#2A1C18")).ink(INK_S),
            ),
            _ => {
                let lie = Quat::from_rotation_y(v.r(0.0, TAU)) * Quat::from_rotation_z(FRAC_PI_2);
                env.lathe(
                    p + Vec3::Y * s * 0.7,
                    lie,
                    &[(s * 0.7, -s * 0.6), (s * 0.7, s * 0.6)],
                    10,
                    (8, 0.1),
                    Paint::new(Key::Stone, c.stone).ink(INK_S),
                );
            }
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn clutter(env: &mut Env, ctx: &Ctx, at: Vec2, y: f32, r: f32, kind: ClutterKind, count: u8, facing: Vec2) {
    let c = ctx.colors;
    let mut v = Vr::new(at, 71 + kind as u32);
    let count = count.clamp(2, 8) as u32;
    let rot = face(facing);
    let spot = |v: &mut Vr, k: u32| {
        let a = k as f32 / count as f32 * TAU + v.r(-0.4, 0.4);
        w3(at, y) + rot * (Vec3::new(a.cos(), 0.0, a.sin()) * (r * v.r(0.25, 0.85)))
    };
    for k in 0..count {
        let p = spot(&mut v, k);
        let yaw = Quat::from_rotation_y(v.r(0.0, TAU));
        match kind {
            ClutterKind::Urns => {
                let s = v.r(0.7, 1.1);
                let terra = vary(hex("#9A5A38"), v.f(), 0.12);
                let prof = [
                    (0.12 * s, 0.0),
                    (0.26 * s, 0.12 * s),
                    (0.34 * s, 0.4 * s),
                    (0.28 * s, 0.68 * s),
                    (0.12 * s, 0.82 * s),
                    (0.11 * s, 0.95 * s),
                    (0.17 * s, 1.0 * s),
                ];
                let toppled = v.f() < 0.2;
                let r2 = if toppled { yaw * Quat::from_rotation_z(FRAC_PI_2) } else { yaw };
                let pos = if toppled { p + Vec3::Y * 0.3 * s } else { p };
                env.lathe(pos, r2, &prof, 10, (0, 0.0), Paint::new(Key::Stone, terra).ink(INK_S));
                env.lathe(
                    pos,
                    r2,
                    &[(0.345 * s, 0.34 * s), (0.345 * s, 0.46 * s)],
                    10,
                    (0, 0.0),
                    Paint::new(Key::Stone, hex("#2A1A14")),
                );
            }
            ClutterKind::Crates => {
                if k % 3 == 2 {
                    // A barrel with iron hoops.
                    let prof = [(0.28, 0.0), (0.34, 0.4), (0.28, 0.8)];
                    env.lathe(p, yaw, &prof, 10, (0, 0.0), Paint::new(Key::Stone, c.wood).ink(INK_S));
                    for hy in [0.12, 0.68] {
                        env.lathe(
                            p,
                            yaw,
                            &[(0.32, hy), (0.32, hy + 0.06)],
                            10,
                            (0, 0.0),
                            Paint::new(Key::Metal, c.iron),
                        );
                    }
                } else if k % 3 == 1 {
                    env.ball(
                        p + Vec3::Y * 0.2,
                        yaw,
                        Vec3::new(0.32, 0.22, 0.28),
                        7,
                        Paint::new(Key::Cloth, hex("#8A7A5A")).ink(INK_S),
                    );
                } else {
                    let s = v.r(0.3, 0.45);
                    env.block(
                        p + Vec3::Y * s,
                        yaw,
                        Vec3::splat(s),
                        0.03,
                        Paint::new(Key::Stone, vary(c.wood, v.f(), 0.15)).ink(INK_S),
                    );
                    if v.f() < 0.4 {
                        let s2 = s * 0.7;
                        env.block(
                            p + Vec3::Y * (s * 2.0 + s2),
                            yaw * Quat::from_rotation_y(0.5),
                            Vec3::splat(s2),
                            0.03,
                            Paint::new(Key::Stone, c.wood).ink(INK_S),
                        );
                    }
                }
            }
            ClutterKind::WeaponRack => {
                if k == 0 {
                    let wood = Paint::new(Key::Stone, c.wood).ink(INK_S);
                    for s in [-0.6f32, 0.6] {
                        env.block(p + rot * Vec3::new(s, 0.6, 0.0), rot, Vec3::new(0.06, 0.6, 0.06), 0.0, wood);
                    }
                    env.block(p + rot * Vec3::new(0.0, 1.05, 0.0), rot, Vec3::new(0.7, 0.05, 0.06), 0.0, wood);
                    for i in 0..4 {
                        let x = -0.45 + i as f32 * 0.3;
                        let lean = rot * Quat::from_rotation_x(-0.25);
                        env.block(
                            p + rot * Vec3::new(x, 0.6, 0.18),
                            lean,
                            Vec3::new(0.05, 0.55, 0.012),
                            0.0,
                            Paint::new(Key::Metal, lighten(c.iron, 2.2)),
                        );
                        env.block(
                            p + rot * Vec3::new(x, 1.2, 0.02),
                            lean,
                            Vec3::new(0.12, 0.02, 0.03),
                            0.0,
                            Paint::new(Key::Metal, c.bronze),
                        );
                    }
                } else {
                    // Discarded blades on the floor.
                    env.block(
                        p + Vec3::Y * 0.02,
                        yaw,
                        Vec3::new(0.05, 0.012, 0.6),
                        0.0,
                        Paint::new(Key::Metal, lighten(c.iron, 2.0)).ink(INK_S),
                    );
                    env.block(
                        p + yaw * Vec3::new(0.0, 0.03, 0.62),
                        yaw,
                        Vec3::new(0.14, 0.03, 0.03),
                        0.0,
                        Paint::new(Key::Metal, c.bronze),
                    );
                }
            }
            ClutterKind::Ingots => {
                let metal = [c.gold, c.bronze, c.iron][(k % 3) as usize];
                let bar =
                    [Vec2::new(-0.2, -0.08), Vec2::new(0.2, -0.08), Vec2::new(0.16, 0.08), Vec2::new(-0.16, 0.08)];
                // A cross-stacked pile of trapezoid bars.
                for i in 0..(2 + v.i(3)) {
                    let lay = yaw * Quat::from_rotation_y(if i % 2 == 0 { 0.0 } else { FRAC_PI_2 });
                    let lift = Vec3::Y * (0.08 + i as f32 * 0.16);
                    for j in [-0.12f32, 0.12] {
                        env.extrude(
                            p + lift + lay * Vec3::new(0.0, 0.0, j),
                            lay * Quat::from_rotation_x(-FRAC_PI_2),
                            &bar,
                            -0.05,
                            0.05,
                            Paint::new(Key::Metal, metal).ink(INK_S),
                        );
                    }
                }
                if k == 0 {
                    // Tongs and a hammer.
                    env.block(
                        p + rot * Vec3::new(0.5, 0.04, 0.2),
                        yaw,
                        Vec3::new(0.03, 0.03, 0.4),
                        0.0,
                        Paint::new(Key::Metal, c.iron),
                    );
                    env.block(
                        p + rot * Vec3::new(-0.5, 0.1, 0.1),
                        yaw,
                        Vec3::new(0.14, 0.1, 0.09),
                        0.02,
                        Paint::new(Key::Metal, c.iron).ink(INK_S),
                    );
                    env.block(
                        p + rot * Vec3::new(-0.5, 0.05, 0.45),
                        yaw,
                        Vec3::new(0.03, 0.03, 0.35),
                        0.0,
                        Paint::new(Key::Stone, c.wood),
                    );
                }
            }
            ClutterKind::Bones => {
                let bone = Paint::new(Key::Stone, c.bone).ink(INK_S);
                if k % 2 == 0 {
                    env.ball(p + Vec3::Y * 0.16, yaw, Vec3::new(0.17, 0.16, 0.2), 7, bone);
                    for s in [-1.0f32, 1.0] {
                        env.ball(
                            p + yaw * Vec3::new(s * 0.07, 0.19, 0.16),
                            yaw,
                            Vec3::splat(0.045),
                            4,
                            Paint::new(Key::Stone, hex("#1A1210")),
                        );
                    }
                } else {
                    let d = yaw * Vec3::X;
                    env.tube(&[p + Vec3::Y * 0.05 - d * 0.35, p + Vec3::Y * 0.05 + d * 0.35], &[0.045, 0.04], 5, bone);
                    for e in [-0.35f32, 0.35] {
                        env.ball(p + Vec3::Y * 0.06 + d * e, yaw, Vec3::splat(0.07), 5, bone);
                    }
                }
            }
            ClutterKind::Candles => {
                let n = 2 + v.i(3);
                for _ in 0..n {
                    let q = p + Vec3::new(v.r(-0.2, 0.2), 0.0, v.r(-0.2, 0.2));
                    let h = v.r(0.15, 0.5);
                    env.cylinder(q, Quat::IDENTITY, 0.05, 0.045, h, 6, Paint::new(Key::Stone, hex("#E8DCC0")));
                    env.ball(
                        q + Vec3::Y * (h + 0.06),
                        Quat::IDENTITY,
                        Vec3::new(0.03, 0.07, 0.03),
                        4,
                        Paint::new(Key::Glow, c.flame),
                    );
                }
                if k == 0 {
                    env.lathe(
                        p,
                        yaw,
                        &[(0.1, 0.0), (0.25, 0.1), (0.3, 0.16)],
                        10,
                        (0, 0.0),
                        Paint::new(Key::Metal, c.bronze).ink(INK_S),
                    );
                    env.flames.push(Flame { at: p + Vec3::Y * 0.8, color: c.flame, power: 0.3, range: 5.0 });
                }
            }
            ClutterKind::Tomes => {
                let n = 2 + v.i(3);
                let mut yy = 0.0;
                for i in 0..n {
                    let col = [hex("#6A2A22"), hex("#2A3A5A"), hex("#4A5A2A"), hex("#5A3A5A")][((k + i) % 4) as usize];
                    let t = v.r(0.05, 0.09);
                    env.block(
                        p + Vec3::Y * (yy + t),
                        yaw * Quat::from_rotation_y(v.r(-0.3, 0.3)),
                        Vec3::new(0.22, t, 0.16),
                        0.01,
                        Paint::new(Key::Cloth, col).ink(INK_S),
                    );
                    yy += t * 2.0;
                }
                if k == 0 {
                    // A lectern.
                    let wood = Paint::new(Key::Stone, c.wood).ink(INK_S);
                    env.block(p + rot * Vec3::new(0.0, 0.5, -0.4), rot, Vec3::new(0.08, 0.5, 0.08), 0.0, wood);
                    env.block(
                        p + rot * Vec3::new(0.0, 1.02, -0.4),
                        rot * Quat::from_rotation_x(0.4),
                        Vec3::new(0.32, 0.03, 0.24),
                        0.01,
                        wood,
                    );
                }
            }
            ClutterKind::Mushrooms => {
                let n = 2 + v.i(3);
                for _ in 0..n {
                    let q = p + Vec3::new(v.r(-0.25, 0.25), 0.0, v.r(-0.25, 0.25));
                    let h = v.r(0.15, 0.45);
                    env.cylinder(q, Quat::IDENTITY, 0.04, 0.03, h, 5, Paint::new(Key::Stone, hex("#D8CCB0")));
                    env.lathe(
                        q,
                        Quat::IDENTITY,
                        &[(0.0, h - 0.02), (0.12 + h * 0.2, h), (0.0, h + 0.08 + h * 0.1)],
                        7,
                        (0, 0.0),
                        Paint::new(Key::Glow, hdr(c.crystal, 0.7)),
                    );
                }
                if k == 0 {
                    env.flames.push(Flame { at: p + Vec3::Y * 0.6, color: c.crystal, power: 0.25, range: 4.5 });
                }
            }
            ClutterKind::Lanterns => {
                let post = Paint::new(Key::Metal, c.iron).ink(INK_S);
                let h = v.r(1.0, 1.6);
                env.cylinder(p, Quat::IDENTITY, 0.04, 0.03, h, 5, post);
                env.block(
                    p + Vec3::Y * (h + 0.12),
                    yaw,
                    Vec3::new(0.12, 0.16, 0.12),
                    0.0,
                    Paint::new(Key::Glow, hdr(c.flame, 0.6)),
                );
                env.block(p + Vec3::Y * (h + 0.32), yaw, Vec3::new(0.15, 0.04, 0.15), 0.01, post);
                if k % 2 == 0 {
                    env.flames.push(Flame { at: p + Vec3::Y * (h + 0.2), color: c.flame, power: 0.35, range: 6.0 });
                }
            }
            ClutterKind::Shards => {
                let tilt = Quat::from_rotation_z(v.r(-0.6, 0.6)) * Quat::from_rotation_x(v.r(-0.6, 0.6));
                env.crystal_spike(
                    p,
                    tilt,
                    v.r(0.06, 0.12),
                    v.r(0.2, 0.4),
                    0.15,
                    4,
                    Paint::new(Key::Glow, c.crystal).ink(INK_S),
                );
            }
            ClutterKind::Offerings => {
                let gold = Paint::new(Key::Metal, c.gold).ink(INK_S);
                if k % 2 == 0 {
                    let s = v.r(0.3, 0.55);
                    env.lathe(p, Quat::IDENTITY, &[(s, 0.0), (s * 0.6, s * 0.25), (0.0, s * 0.4)], 9, (0, 0.0), gold);
                } else {
                    env.lathe(
                        p,
                        yaw,
                        &[(0.1, 0.0), (0.03, 0.12), (0.03, 0.24), (0.14, 0.34), (0.15, 0.42)],
                        8,
                        (0, 0.0),
                        gold,
                    );
                    env.ball(
                        p + Vec3::new(0.2, 0.06, 0.1),
                        yaw,
                        Vec3::splat(0.06),
                        4,
                        Paint::new(Key::Glow, c.crystal),
                    );
                }
            }
        }
    }
}

fn banner(env: &mut Env, ctx: &Ctx, at: Vec2, height: f32, facing: Vec2, god: u8) {
    let c = ctx.colors;
    let (col, col2) = ctx.god(god);
    let mut v = Vr::new(at, 73);
    let rot = face(facing);
    let right = rot * Vec3::X;
    let fwd = rot * Vec3::Z;
    let on_rim = at.y >= ctx.half.y - 0.5;
    let base = w3(at, 0.0) + if on_rim { Vec3::NEG_Z * 0.45 } else { Vec3::ZERO };
    let w = if on_rim { 0.75 } else { 0.55 };
    let top = height;
    let len = (height * 0.55).clamp(1.4, 3.6);
    let bronze = Paint::new(Key::Metal, c.bronze).ink(INK_S);
    if !on_rim {
        env.cylinder(base, Quat::IDENTITY, 0.06, 0.05, top + 0.25, 6, bronze);
        env.ball(base + Vec3::Y * (top + 0.32), Quat::IDENTITY, Vec3::splat(0.1), 6, Paint::new(Key::Metal, c.gold));
        env.block(base + Vec3::Y * top + fwd * 0.05, rot, Vec3::new(w + 0.12, 0.035, 0.035), 0.0, bronze);
    } else {
        env.block(base + Vec3::Y * top, rot, Vec3::new(w + 0.1, 0.04, 0.04), 0.0, bronze);
    }
    // Cloth: gathered folds (alternating depth), a swallowtail hem, gold trim, the god's emblem.
    let o = base + fwd * 0.08;
    let folds = 4;
    let dark = lin(lighten(col, 0.55));
    let light = lin(col);
    let sway = v.r(-0.1, 0.1);
    for i in 0..folds {
        let x0 = -w + 2.0 * w * i as f32 / folds as f32;
        let x1 = -w + 2.0 * w * (i + 1) as f32 / folds as f32;
        let z0 = if i % 2 == 0 { 0.0 } else { 0.06 };
        let z1 = if i % 2 == 0 { 0.06 } else { 0.0 };
        let hem = |x: f32| {
            let t = (x / w).abs();
            len - 0.35 * (1.0 - t)
        };
        let q = |x: f32, y: f32, z: f32| o + right * (x + sway * y / len) + Vec3::Y * (top - y) + fwd * z;
        env.sheet(
            [q(x0, hem(x0), z0), q(x1, hem(x1), z1), q(x1, 0.0, z1), q(x0, 0.0, z0)],
            [dark, dark, light, light],
            Key::Cloth,
        );
    }
    let gold = lin(c.gold);
    let q = |x: f32, y: f32| o + right * x + Vec3::Y * (top - y) + fwd * 0.1;
    env.sheet([q(-w, 0.22), q(w, 0.22), q(w, 0.08), q(-w, 0.08)], [gold; 4], Key::Cloth);
    let e = lin(hdr(col2, 1.6));
    let cy = len * 0.45;
    let s = w * 0.45;
    env.sheet([q(0.0, cy + s), q(s, cy), q(0.0, cy - s), q(-s, cy)], [e; 4], Key::Glow);
}

/// A waymark: a stone post with an iron cap, a pennant in the colour of the objective the road
/// leads to streaming along the road (`along`), and a glowing lamp of the same colour on top that
/// reads from across the screen.
fn waymark(env: &mut Env, c: &Colors, at: Vec2, along: Vec2, kind: PoiKind) {
    let col = poi_kind_color(kind);
    let mut v = Vr::new(at, 91);
    let base = w3(at, 0.0);
    let h = 3.6 + v.r(-0.2, 0.3);
    let stone = Paint::new(Key::Stone, vary(c.stone, v.f(), 0.06)).ink(INK_S);
    let iron = Paint::new(Key::Metal, c.iron).ink(INK_S);
    // Stepped foot, square post, cap.
    env.block(base + Vec3::Y * 0.14, Quat::IDENTITY, Vec3::new(0.48, 0.14, 0.48), 0.04, stone);
    env.block(
        base + Vec3::Y * (0.28 + h * 0.5),
        Quat::from_rotation_y(v.r(-0.1, 0.1)),
        Vec3::new(0.17, h * 0.5, 0.17),
        0.03,
        stone,
    );
    env.block(base + Vec3::Y * (h + 0.34), Quat::IDENTITY, Vec3::new(0.26, 0.07, 0.26), 0.02, iron);
    // The pennant: a long swallow-tailed flag from the top of the post, streaming along the road.
    let d = Vec3::new(along.x, 0.0, -along.y).normalize_or(Vec3::X);
    let top = base + Vec3::Y * (h + 0.1);
    let len = 1.9;
    let drop = 0.75;
    let (light, dark) = (lin(col), lin(lighten(col, 0.55)));
    let p = |s: f32, y: f32| top + d * s - Vec3::Y * y;
    env.sheet(
        [p(0.12, 0.0), p(len, 0.18), p(len * 0.78, drop * 0.5), p(0.12, drop)],
        [light, light, dark, dark],
        Key::Cloth,
    );
    env.sheet(
        [p(len * 0.78, drop * 0.5), p(len, 0.18), p(len * 1.02, drop * 0.95), p(0.12, drop)],
        [dark, light, dark, dark],
        Key::Cloth,
    );
    // The lamp.
    let glow = Paint::new(Key::Glow, hdr(col, 2.4));
    env.ball(base + Vec3::Y * (h + 0.62), Quat::IDENTITY, Vec3::splat(0.22), 8, glow);
}

/// A sagging chain of links from `a` to `b` (world); `sag` as a fraction of the length.
fn chains(env: &mut Env, c: &Colors, a: Vec3, b: Vec3, sag: f32) {
    let len = a.distance(b);
    let n = ((len / 0.46).round() as u32).clamp(2, 60);
    let iron = Paint::new(Key::Metal, c.iron);
    let at = |t: f32| a.lerp(b, t) - Vec3::Y * (sag * len * 4.0 * t * (1.0 - t));
    for i in 0..n {
        let t0 = i as f32 / n as f32;
        let t1 = (i + 1) as f32 / n as f32;
        let (p0, p1) = (at(t0), at(t1));
        let d = (p1 - p0).normalize_or(Vec3::X);
        let r = Quat::from_rotation_arc(Vec3::Z, d) * Quat::from_rotation_z(if i % 2 == 0 { 0.0 } else { FRAC_PI_2 });
        env.block((p0 + p1) * 0.5, r, Vec3::new(0.07, 0.025, 0.2), 0.0, iron);
    }
}

fn debris(env: &mut Env, c: &Colors, at: Vec2, r: f32, height: f32, variant: u8) {
    let mut v = Vr::new(at, 79);
    let p = w3(at, height + r);
    let rot = Quat::from_rotation_y(v.r(0.0, TAU)) * Quat::from_rotation_x(v.r(-0.5, 0.5));
    if variant.is_multiple_of(2) {
        env.rock(p, rot, Vec3::new(r, r * 0.6, r * 0.9), v.seed, 0.4, Paint::new(Key::Rock, c.rock).ink(INK_S));
    } else {
        env.block(p, rot, Vec3::new(r, r * 0.5, r * 0.7), 0.04, Paint::new(Key::Stone, c.stone).ink(INK_S));
    }
    if matches!(c.abyss, AbyssKind::Sky | AbyssKind::Chaos) {
        env.disc(p - Vec3::Y * (r * 0.55), r * 0.6, 8, lin(hdr(c.glow, 0.6)), [0.0; 4], Key::Glow);
    }
}

#[allow(clippy::too_many_arguments)]
fn fallen_weapon(env: &mut Env, c: &Colors, at: Vec2, r: f32, h: f32, lean_to: Vec2, variant: u8) {
    let mut v = Vr::new(at, 83);
    let base = w3(at, 0.0);
    let lean = Quat::from_rotation_arc(Vec3::Y, (Vec3::Y + wd(lean_to) * 0.38).normalize())
        * Quat::from_rotation_y(v.r(-0.3, 0.3));
    let steel = Paint::new(Key::Metal, lighten(c.iron, 2.0)).ink(INK);
    let gold = Paint::new(Key::Metal, c.gold).ink(INK);
    let up = |y: f32| base + lean * Vec3::Y * y;
    let s = h / 16.0;
    match variant % 5 {
        0 => {
            // Sword: the blade buried point-first, snapped a third of the way up.
            let blade = [
                Vec2::new(-1.1 * s, 0.0),
                Vec2::new(0.0, -0.25 * s),
                Vec2::new(1.1 * s, 0.0),
                Vec2::new(0.0, 0.25 * s),
            ];
            env.extrude(base - Vec3::Y * 1.0, lean, &blade, 0.0, h * 0.62, steel);
            env.block(up(h * 0.62 + 0.4 * s), lean, Vec3::new(3.2, 0.4, 0.55) * s, 0.06, gold);
            env.tube(
                &[up(h * 0.62 + 0.8 * s), up(h * 0.93)],
                &[0.45 * s, 0.4 * s],
                8,
                Paint::new(Key::Stone, hex("#4A2A1E")).ink(INK),
            );
            env.ball(up(h * 0.97), lean, Vec3::splat(0.85 * s), 8, gold);
            env.block(
                up(h * 0.3),
                lean,
                Vec3::new(0.15 * s, h * 0.25, 0.3 * s),
                0.0,
                Paint::new(Key::Glow, hdr(c.glow, 0.5)),
            );
        }
        1 => {
            // Hammer: haft planted, head canted over.
            env.tube(
                &[base - Vec3::Y * 0.5, up(h * 0.8)],
                &[0.55 * s, 0.5 * s],
                8,
                Paint::new(Key::Stone, c.wood).ink(INK),
            );
            let head = lean * Quat::from_rotation_z(FRAC_PI_2);
            env.block(up(h * 0.85), head, Vec3::new(1.6, 3.4, 1.6) * s, 0.2 * s, steel);
            for y in [-2.2f32, 2.2] {
                env.lathe(
                    up(h * 0.85) + head * Vec3::Y * (y * s),
                    head,
                    &[(1.75 * s, -0.3 * s), (1.75 * s, 0.3 * s)],
                    12,
                    (0, 0.0),
                    gold,
                );
            }
        }
        2 => {
            // Spear: a long shaft and a leaf blade.
            env.tube(
                &[base - Vec3::Y * 0.5, up(h * 0.8)],
                &[0.3 * s, 0.26 * s],
                7,
                Paint::new(Key::Stone, c.wood).ink(INK),
            );
            let leaf =
                [Vec2::new(-0.9 * s, 0.0), Vec2::new(0.0, -0.2 * s), Vec2::new(0.9 * s, 0.0), Vec2::new(0.0, 0.2 * s)];
            env.extrude(up(h * 0.8), lean, &leaf, 0.0, h * 0.2, steel);
            env.lathe(up(h * 0.78), lean, &[(0.45 * s, 0.0), (0.45 * s, 0.6 * s)], 10, (0, 0.0), gold);
        }
        3 => {
            // Bow: a great arc half buried, its string snapped.
            let n = 10;
            let pts: Vec<Vec3> = (0..=n)
                .map(|i| {
                    let t = i as f32 / n as f32;
                    let a = -1.2 + 2.4 * t;
                    base + lean * Vec3::new(a.sin() * h * 0.5, a.cos() * h * 0.7 - h * 0.1, 0.0)
                })
                .collect();
            let radii: Vec<f32> = (0..=n).map(|i| s * (0.9 - 0.4 * ((i as f32 / n as f32) - 0.5).abs())).collect();
            env.tube(&pts, &radii, 7, Paint::new(Key::Stone, c.wood).ink(INK));
            env.tube(
                &[pts[n], pts[n] + Vec3::new(0.0, -h * 0.35, 0.3)],
                &[0.08, 0.08],
                4,
                Paint::new(Key::Stone, c.bone),
            );
            env.block(pts[n / 2], lean, Vec3::new(0.6, 1.2, 0.7) * s, 0.05, gold);
        }
        _ => {
            // Cannon: a ringed barrel propped on its broken carriage.
            let barrel_rot = lean * Quat::from_rotation_x(1.0);
            let prof =
                [(1.3 * s, 0.0), (1.2 * s, 0.4 * s), (1.0 * s, h * 0.55), (1.15 * s, h * 0.58), (1.15 * s, h * 0.62)];
            env.lathe(
                base + Vec3::Y * (1.2 * s),
                barrel_rot,
                &prof,
                12,
                (0, 0.0),
                Paint::new(Key::Metal, c.bronze).ink(INK),
            );
            for y in [0.15, 0.3, 0.45] {
                env.lathe(
                    base + Vec3::Y * (1.2 * s) + barrel_rot * Vec3::Y * (h * y),
                    barrel_rot,
                    &[(1.2 * s, 0.0), (1.2 * s, 0.35 * s)],
                    12,
                    (0, 0.0),
                    gold,
                );
            }
            env.lathe(
                base + Vec3::Y * (1.8 * s),
                Quat::from_rotation_z(FRAC_PI_2) * lean,
                &[(2.2 * s, -0.25 * s), (2.2 * s, 0.25 * s)],
                12,
                (0, 0.0),
                Paint::new(Key::Stone, c.wood).ink(INK),
            );
        }
    }
    // The crater: a ring of heaved slabs and stones, scorched ground, and cracks of light
    // running out from the wound.
    env.disc(base + Vec3::Y * 0.02, r * 1.5, 14, lin(mix(c.dark, hex("#0C0808"), 0.5)), lin(c.dark), Key::Stone);
    for k in 0..7 {
        let d = dir(k as f32 / 7.0 * TAU + v.f() * 0.6);
        let rr = r * v.r(0.22, 0.38);
        let at = base + wd(d) * r * v.r(0.8, 1.15);
        if k % 2 == 0 {
            // A slab of the old floor, heaved up and tilted away from the impact.
            let tilt = face(d) * Quat::from_rotation_x(-v.r(0.35, 0.7));
            env.block(at + Vec3::Y * rr * 0.35, tilt, Vec3::new(rr * 1.1, rr * 0.22, rr * 0.8), 0.03, {
                Paint::new(Key::Stone, vary(c.stone, v.f(), 0.08)).ink(INK_S)
            });
        } else {
            env.rock(
                at + Vec3::Y * rr * 0.2,
                Quat::IDENTITY,
                Vec3::new(rr, rr * 0.6, rr),
                v.seed + k,
                0.45,
                Paint::new(Key::Rock, c.rock).ink(INK_S),
            );
        }
    }
    let glow = Paint::new(Key::Glow, hdr(c.glow, 0.8));
    for k in 0..5 {
        let a = k as f32 / 5.0 * TAU + v.r(-0.4, 0.4);
        let d = dir(a);
        let len = r * v.r(1.0, 1.7);
        let bend = dir(a + v.r(-0.5, 0.5));
        let p0 = base + wd(d) * (r * 0.25) + Vec3::Y * 0.03;
        let p1 = p0 + wd(d) * (len * 0.5);
        let p2 = p1 + wd(bend) * (len * 0.5);
        env.tube(&[p0, p1, p2], &[0.07, 0.05, 0.015], 4, glow);
    }
    env.disc(base + Vec3::Y * 0.04, r * 0.55, 10, lin(hdr(c.glow, 0.35)), [0.0; 4], Key::Glow);
}

// ───────────────────────────── room rim ─────────────────────────────

/// The border of a legacy / generated room by its [`RimStyle`]: backdrop to the north, flanks,
/// and a low south edge that never hides a character. `exits` get gate arches cut in.
pub fn rim(env: &mut Env, c: &Colors, half: Vec2, style: &RimStyle, exits: &[Vec2]) {
    let mut v = Vr::new(half, 97 + style.variant as u32);
    let north = half.y + 0.7;
    let tall = style.height.clamp(3.0, 10.0);
    // North (backdrop).
    edge(env, c, style.north, Side::North, half, tall, exits, &mut v);
    edge(env, c, style.east, Side::East, half, tall, exits, &mut v);
    edge(env, c, style.west, Side::West, half, tall, exits, &mut v);
    edge(env, c, style.south, Side::South, half, tall, exits, &mut v);
    // Gate arches at the exits on the north wall.
    for e in exits.iter().filter(|e| e.y > half.y - 3.0) {
        env.at(*e);
        let from = Vec2::new(e.x - 2.3, north);
        let to = Vec2::new(e.x + 2.3, north);
        arch(env, c, from, to, 0.7, (tall * 0.8).max(4.6), 0);
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Side {
    North,
    East,
    South,
    West,
}

#[allow(clippy::too_many_arguments)]
fn edge(env: &mut Env, c: &Colors, kind: RimEdge, side: Side, half: Vec2, tall: f32, exits: &[Vec2], v: &mut Vr) {
    // Walk the side in steps; `at(t)` is the rim line point at t ∈ [0, len], `out` points away.
    let (a, b, out) = match side {
        Side::North => (Vec2::new(-half.x - 1.2, half.y + 0.7), Vec2::new(half.x + 1.2, half.y + 0.7), Vec2::Y),
        Side::South => (Vec2::new(-half.x - 1.2, -half.y - 0.6), Vec2::new(half.x + 1.2, -half.y - 0.6), Vec2::NEG_Y),
        Side::East => (Vec2::new(half.x + 0.7, -half.y), Vec2::new(half.x + 0.7, half.y), Vec2::X),
        Side::West => (Vec2::new(-half.x - 0.7, -half.y), Vec2::new(-half.x - 0.7, half.y), Vec2::NEG_X),
    };
    let len = a.distance(b);
    let d = (b - a) / len;
    let gap = |p: Vec2| exits.iter().any(|e| e.distance(p) < 2.4);
    // Height ramp: flanks rise toward the north backdrop, the south stays low.
    let hgt = |p: Vec2, full: f32| match side {
        Side::North => full,
        Side::South => (full * 0.12).min(0.55),
        _ => {
            let t = ((p.y + half.y) / (half.y * 2.0)).clamp(0.0, 1.0);
            full * (0.3 + 0.7 * t)
        }
    };
    let low = side == Side::South;
    match kind {
        RimEdge::Wall | RimEdge::BrokenWall => {
            let broken = kind == RimEdge::BrokenWall || low;
            let step = 3.0;
            let n = (len / step).ceil() as u32;
            for i in 0..n {
                let t = (i as f32 + 0.5) * len / n as f32;
                let p = a + d * t;
                if gap(p) {
                    continue;
                }
                env.at(p);
                let full = if broken { tall * v.r(0.3, 0.7) } else { tall * v.r(0.85, 1.0) };
                let h = hgt(p, full).max(0.35);
                if broken && !low && v.f() < 0.18 {
                    // A breach with rubble spilling through.
                    rubble(env, c, p - out * 1.2, 1.1, v.i(3) as u8);
                    continue;
                }
                let (hl, ht) = (len / n as f32 * 0.5 + 0.02, 0.7);
                let mut vv = Vr::new(p, 5);
                let along_x = d.x.abs() > 0.5;
                let rot = if along_x { Quat::IDENTITY } else { Quat::from_rotation_y(FRAC_PI_2) };
                let u = if along_x { Vec3::X } else { Vec3::Z };
                masonry(env, c, w3(p, 0.0), rot, u, hl, ht, h, broken, &mut vv);
                if !broken && side == Side::North && i % 2 == 0 {
                    // Pilasters and a cornice give the backdrop its order.
                    env.block(
                        w3(p - out * 0.72, h * 0.5),
                        rot,
                        Vec3::new(0.35, h * 0.5, 0.12),
                        0.03,
                        Paint::new(Key::Stone, c.trim).ink(INK),
                    );
                }
                if !broken {
                    env.block(
                        w3(p, h + 0.12),
                        rot,
                        Vec3::new(hl + 0.06, 0.12, ht + 0.12),
                        0.03,
                        Paint::new(Key::Stone, c.trim).ink(INK),
                    );
                }
            }
        }
        RimEdge::Colonnade => {
            let step = 3.4;
            let n = (len / step).floor().max(1.0) as u32;
            let h = hgt(a, tall.max(6.0));
            let mut bases = Vec::new();
            for i in 0..=n {
                let p = a + d * (len * i as f32 / n as f32);
                if gap(p) {
                    continue;
                }
                env.at(p);
                let mut vv = Vr::new(p, 9);
                let hh = hgt(p, h);
                let stump = v.f() < 0.12;
                column(
                    env,
                    c,
                    w3(p, 0.0),
                    Quat::IDENTITY,
                    0.55,
                    if stump { hh * 0.3 } else { hh },
                    c.stone,
                    stump,
                    &mut vv,
                );
                if !stump {
                    bases.push((p, hh));
                }
            }
            // Architrave spans between standing neighbours.
            for w in bases.windows(2) {
                let (p0, h0) = w[0];
                let (p1, h1) = w[1];
                if p0.distance(p1) > step * 1.6 {
                    continue;
                }
                env.at((p0 + p1) * 0.5);
                let hh = h0.min(h1);
                let mid = (p0 + p1) * 0.5;
                let rot = face(Vec2::new(-d.y, d.x));
                env.block(
                    w3(mid, hh + 0.28),
                    rot,
                    Vec3::new(p0.distance(p1) * 0.5 + 0.7, 0.28, 0.7),
                    0.04,
                    Paint::new(Key::Stone, c.trim).ink(INK),
                );
            }
        }
        RimEdge::Balustrade | RimEdge::Open | RimEdge::Terrace => {
            let n = (len / 2.4).ceil() as u32;
            for i in 0..n {
                let t = (i as f32 + 0.5) * len / n as f32;
                let p = a + d * t;
                if gap(p) {
                    continue;
                }
                env.at(p);
                let along_x = d.x.abs() > 0.5;
                let rot = if along_x { Quat::IDENTITY } else { Quat::from_rotation_y(FRAC_PI_2) };
                let hl = len / n as f32 * 0.5;
                match kind {
                    RimEdge::Balustrade => parapet(env, c, w3(p, 0.0), rot, hl, 0.25, if low { 0.55 } else { 1.05 }),
                    RimEdge::Terrace => {
                        for s in 0..3 {
                            let q = p + out * (0.6 + s as f32 * 0.9);
                            let hh = if low { 0.15 } else { 0.35 * (s + 1) as f32 };
                            let hw = if along_x { Vec2::new(hl, 0.45) } else { Vec2::new(0.45, hl) };
                            env.slab(
                                q,
                                hw,
                                0.0,
                                hh,
                                0.03,
                                Paint::new(Key::Stone, vary(c.stone, h01(i, s), 0.06)).ink(INK_S),
                            );
                        }
                    }
                    _ => {
                        // Carved lip with a glowing rune band.
                        let hw = if along_x { Vec2::new(hl, 0.28) } else { Vec2::new(0.28, hl) };
                        env.slab(p, hw, 0.0, 0.16, 0.04, Paint::new(Key::Stone, c.trim).ink(INK_S));
                        let rw = if along_x { Vec2::new(hl * 0.8, 0.05) } else { Vec2::new(0.05, hl * 0.8) };
                        env.slab(p - out * 0.1, rw, 0.16, 0.18, 0.0, Paint::new(Key::Glow, hdr(c.glow, 0.7)));
                    }
                }
            }
        }
        RimEdge::Cliff => {
            let n = (len / 2.6).ceil() as u32;
            for i in 0..n {
                let p = a + d * ((i as f32 + 0.5) * len / n as f32) + out * 0.8;
                if gap(p) {
                    continue;
                }
                env.at(p);
                let h = if side == Side::North { tall * v.r(0.7, 1.2) } else { hgt(p, tall * 0.35) };
                let r = Vec3::new(1.8, h.max(0.4), 1.4);
                env.rock(
                    w3(p, h * 0.35),
                    Quat::from_rotation_y(v.r(0.0, TAU)),
                    r,
                    v.seed + i,
                    0.35,
                    Paint::new(Key::Rock, c.rock).ink(INK),
                );
            }
        }
        RimEdge::Thicket => {
            let n = (len / 2.2).ceil() as u32;
            for i in 0..n {
                let p = a + d * ((i as f32 + 0.5) * len / n as f32) + out * 0.6;
                if gap(p) {
                    continue;
                }
                env.at(p);
                let h = if low { 0.5 } else { hgt(p, tall * 0.8) };
                if !low && i % 3 == 0 {
                    tree(env, c, p + out * 0.8, 0.5, h + 2.0, 0);
                } else {
                    let mut vv = Vr::new(p, 3);
                    leaf_clump(env, c, w3(p, h * 0.4), (h * 0.45).max(0.45), &mut vv);
                    grass(env, w3(p - out * 0.5, 0.0), 1.0, 3, c.leaf, c.leaf_dark, 0.6, &mut vv);
                }
            }
        }
        RimEdge::Shattered => {
            // Islands of floor drifting off into the void.
            let n = (len / 3.0).ceil() as u32;
            for i in 0..n {
                let p = a + d * ((i as f32 + 0.5) * len / n as f32) + out * v.r(2.0, 5.0);
                env.at(p);
                let s = v.r(0.8, 1.8);
                let y = if low { v.r(-1.8, -0.8) } else { v.r(-1.0, 1.5) };
                env.slab(p, Vec2::new(s, s * 0.8), y - 0.25, y, 0.05, Paint::new(Key::Stone, c.stone).ink(INK_S));
                // The rocky underside hangs below the paving (its top stays under the slab).
                env.rock(
                    w3(p, y - 0.3 - 0.85),
                    Quat::IDENTITY,
                    Vec3::new(s * 0.85, 0.8, s * 0.7),
                    v.seed + i,
                    0.3,
                    Paint::new(Key::Rock, c.rock).ink(INK_S),
                );
            }
        }
    }
}
