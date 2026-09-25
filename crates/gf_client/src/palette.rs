//! Shared render resources and the colour language (§12): element hues, rarity colours, P1–P4
//! player colours, danger red-white telegraphs. Greybox primitives stand in for authored glTF
//! until the Blender pipeline delivers models; every mesh and material goes through this cache so
//! swapping in real assets touches one module.
//!
//! Lit looks are painterly toon materials ([`ToonMaterial`]); glows, decals, additive light and
//! ink hulls stay `StandardMaterial`. Materials are cached per (colour, look), so 400 enemies of
//! a handful of kinds share a handful of handles and batch.

use crate::ClientConfig;
use crate::materials::{ToonMaterial, ToonStyle, toon, toon_from_standard};
use gf_core::damage::DamageType;
use gf_core::rarity::Rarity;
use gf_engine::client::{Face, rgba_image};
use gf_engine::prelude::*;
use std::collections::HashMap;
use std::f32::consts::FRAC_PI_2;

/// Material families.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Look {
    /// Painted matte prop (toon, soft gold rim, world-space brushwork).
    Matte,
    /// Worked metal: anvils, weapons, gold trim (toon).
    Metal,
    /// Emissive: blooms in HDR (projectiles, ichor, embers).
    Glow,
    /// Enemy body with a faint inner glow: status tints (toon, foe rim).
    Smolder,
    /// Flat unlit translucent decal on the ground (telegraphs, hazards, rings).
    Decal,
    /// Additive light (particles, flashes).
    Additive,
    /// Translucent lit: echoes, downed wraiths (toon).
    Ghost,
    /// Inverted-hull ink outline: unlit, front faces culled (painterly silhouettes, §12).
    Ink,
    /// Player character in slot n: toon with a rim in the player's colour.
    Hero(u8),
    /// Enemy body: toon with a warm red rim.
    Foe,
    /// Glowing-hot body: hit flash, wind-up blink, heated metal (toon, blooms).
    Hot,
}

impl Look {
    /// Painterly toon material (as opposed to a plain `StandardMaterial`).
    pub fn is_toon(self) -> bool {
        !matches!(self, Look::Glow | Look::Decal | Look::Additive | Look::Ink)
    }
}

/// A cached material of either kind.
#[derive(Clone, Debug, PartialEq)]
pub enum Mat {
    Std(Handle<StandardMaterial>),
    Toon(Handle<ToonMaterial>),
}

impl Mat {
    /// Insert the matching `MeshMaterial3d` on an entity.
    pub fn insert(self, entity: &mut EntityCommands) {
        match self {
            Mat::Std(h) => entity.insert(MeshMaterial3d(h)),
            Mat::Toon(h) => entity.insert(MeshMaterial3d(h)),
        };
    }

    /// The toon handle (tint swaps, downed swap).
    pub fn toon(&self) -> Option<Handle<ToonMaterial>> {
        match self {
            Mat::Toon(h) => Some(h.clone()),
            Mat::Std(_) => None,
        }
    }
}

#[derive(Resource)]
pub struct Palette {
    pub sphere: Handle<Mesh>,
    pub low_sphere: Handle<Mesh>,
    pub capsule: Handle<Mesh>,
    pub cube: Handle<Mesh>,
    pub cylinder: Handle<Mesh>,
    pub cone: Handle<Mesh>,
    pub torus: Handle<Mesh>,
    /// Flat unit disc (radius 1) in the 2D XY plane; lay it on the ground with [`flat`].
    pub disc: Handle<Mesh>,
    /// Flat ring, outer radius 1, inner 0.86.
    pub ring: Handle<Mesh>,
    /// Flat 1×1 quad, centred.
    pub quad: Handle<Mesh>,
    /// Tileable painted cliff strata (greyscale-warm; the toon material tints it per biome).
    pub rock_texture: Handle<Image>,
    /// Soft radial blob (alpha) for contact shadows.
    pub blob_texture: Handle<Image>,
    /// Hand-painted block face (ink border, bevel light, brushwork) for architecture primitives.
    pub block_texture: Handle<Image>,
    /// The env kit's stone atlas: a painted block face on the left half (u < 0.5), borderless
    /// brushed stone on the right half (lathes, bevels, cloth).
    pub env_texture: Handle<Image>,
    pub players: [Color; 4],
    pub danger: Color,
    sectors: HashMap<u8, Handle<Mesh>>,
    annuli: HashMap<u16, Handle<Mesh>>,
    cache: HashMap<(u32, Look), Handle<StandardMaterial>>,
    toon_cache: HashMap<(u32, Look), Handle<ToonMaterial>>,
    blob_cache: HashMap<u8, Handle<StandardMaterial>>,
}

impl Palette {
    /// Cached `StandardMaterial` for a colour and one of the plain looks (glow, decal, additive,
    /// ink). Lit looks go through [`Palette::toon`] / [`Palette::look`].
    pub fn mat(&mut self, mats: &mut Assets<StandardMaterial>, color: Color, look: Look) -> Handle<StandardMaterial> {
        debug_assert!(!look.is_toon(), "{look:?} is a toon look: use Palette::look");
        let key = (color_key(color), look);
        if let Some(h) = self.cache.get(&key) {
            return h.clone();
        }
        let h = mats.add(make_material(color, look));
        self.cache.insert(key, h.clone());
        h
    }

    /// Cached toon material for a colour and a lit look.
    pub fn toon(&mut self, toons: &mut Assets<ToonMaterial>, color: Color, look: Look) -> Handle<ToonMaterial> {
        let key = (color_key(color), look);
        if let Some(h) = self.toon_cache.get(&key) {
            return h.clone();
        }
        let h = toons.add(make_toon(color, look, &self.players, &self.block_texture));
        self.toon_cache.insert(key, h.clone());
        h
    }

    /// Cached material of the right kind for any look.
    pub fn look(
        &mut self,
        mats: &mut Assets<StandardMaterial>,
        toons: &mut Assets<ToonMaterial>,
        color: Color,
        look: Look,
    ) -> Mat {
        if look.is_toon() { Mat::Toon(self.toon(toons, color, look)) } else { Mat::Std(self.mat(mats, color, look)) }
    }

    /// Shared soft contact-shadow material (`strength` 0..1 quantized, so a few handles total).
    pub fn blob_shadow(&mut self, mats: &mut Assets<StandardMaterial>, strength: f32) -> Handle<StandardMaterial> {
        let q = (strength.clamp(0.0, 1.0) * 10.0).round() as u8;
        let texture = self.blob_texture.clone();
        self.blob_cache
            .entry(q)
            .or_insert_with(|| {
                mats.add(StandardMaterial {
                    base_color: Color::srgba(0.02, 0.015, 0.04, q as f32 / 10.0),
                    base_color_texture: Some(texture),
                    unlit: true,
                    alpha_mode: AlphaMode::Blend,
                    fog_enabled: false,
                    ..default()
                })
            })
            .clone()
    }

    /// Flat circular sector of radius 1 and total angle `angle_deg`, symmetric about the mesh's +Y.
    pub fn sector(&mut self, meshes: &mut Assets<Mesh>, angle_deg: u8) -> Handle<Mesh> {
        self.sectors
            .entry(angle_deg)
            .or_insert_with(|| {
                meshes.add(CircularSector::new(1.0, (angle_deg.max(1) as f32).to_radians() * 0.5).mesh().resolution(40))
            })
            .clone()
    }

    /// Flat annulus with outer radius 1 and the given inner radius fraction.
    pub fn annulus(&mut self, meshes: &mut Assets<Mesh>, inner_frac: f32) -> Handle<Mesh> {
        let key = (inner_frac.clamp(0.0, 0.999) * 1000.0) as u16;
        self.annuli
            .entry(key)
            .or_insert_with(|| meshes.add(Annulus::new(key as f32 / 1000.0, 1.0).mesh().resolution(48)))
            .clone()
    }

    pub fn player(&self, slot: u8) -> Color {
        self.players[slot as usize % 4]
    }
}

fn color_key(c: Color) -> u32 {
    // HDR colours (> 1.0) keep distinct keys: quantize in linear space with headroom.
    let l = c.to_linear();
    let q = |v: f32| ((v / 8.0).clamp(0.0, 1.0) * 255.0).round() as u32;
    let a = (l.alpha.clamp(0.0, 1.0) * 255.0).round() as u32;
    q(l.red) | (q(l.green) << 8) | (q(l.blue) << 16) | (a << 24)
}

fn make_toon(color: Color, look: Look, players: &[Color; 4], block: &Handle<Image>) -> ToonMaterial {
    let lin = color.to_linear();
    let emissive = |gain: f32| LinearRgba::rgb(lin.red * gain, lin.green * gain, lin.blue * gain);
    match look {
        Look::Metal => toon_from_standard(
            StandardMaterial {
                base_color: color,
                base_color_texture: Some(block.clone()),
                perceptual_roughness: 0.38,
                metallic: 0.55,
                ..default()
            },
            &ToonStyle::metal(),
        ),
        Look::Matte => toon(color, Some(block.clone()), LinearRgba::BLACK, &ToonStyle::prop()),
        Look::Hero(slot) => toon(color, None, LinearRgba::BLACK, &ToonStyle::hero(players[slot as usize % 4])),
        Look::Foe => toon(color, None, LinearRgba::BLACK, &ToonStyle::foe()),
        Look::Smolder => toon(color, None, emissive(0.6), &ToonStyle::foe()),
        Look::Hot => toon(color, None, emissive(2.4), &ToonStyle::foe()),
        Look::Ghost => {
            let mut m = toon(color, None, emissive(0.5), &ToonStyle::hero(color.with_alpha(1.0)));
            m.base.alpha_mode = AlphaMode::Blend;
            m
        }
        _ => toon(color, None, LinearRgba::BLACK, &ToonStyle::prop()),
    }
}

/// Plain `StandardMaterial` looks. Lit looks only land here as a fallback: they normally go
/// through [`make_toon`].
fn make_material(color: Color, look: Look) -> StandardMaterial {
    let lin = color.to_linear();
    let emissive = |gain: f32| LinearRgba::rgb(lin.red * gain, lin.green * gain, lin.blue * gain);
    match look {
        Look::Matte | Look::Hero(_) | Look::Foe => {
            StandardMaterial { base_color: color, perceptual_roughness: 0.88, reflectance: 0.25, ..default() }
        }
        Look::Metal => StandardMaterial { base_color: color, perceptual_roughness: 0.36, metallic: 0.85, ..default() },
        Look::Glow => StandardMaterial { base_color: color, emissive: emissive(4.0), ..default() },
        Look::Smolder | Look::Hot => {
            StandardMaterial { base_color: color, emissive: emissive(0.8), perceptual_roughness: 0.7, ..default() }
        }
        Look::Decal => StandardMaterial {
            base_color: color,
            unlit: true,
            alpha_mode: AlphaMode::Blend,
            double_sided: true,
            cull_mode: None,
            ..default()
        },
        Look::Additive => StandardMaterial {
            base_color: color,
            unlit: true,
            alpha_mode: AlphaMode::Add,
            double_sided: true,
            cull_mode: None,
            ..default()
        },
        Look::Ink => StandardMaterial {
            base_color: color,
            unlit: true,
            cull_mode: Some(Face::Front),
            fog_enabled: false,
            ..default()
        },
        Look::Ghost => StandardMaterial {
            base_color: color,
            emissive: emissive(0.5),
            alpha_mode: AlphaMode::Blend,
            perceptual_roughness: 0.6,
            ..default()
        },
    }
}

/// Rotation that lays a 2D (XY-plane) mesh flat on the ground and turns its +Y axis to `angle`
/// (sim radians, counter-clockwise from +x). Sim (x, y) maps to world (x, 0, −y).
#[inline]
pub fn flat(angle: f32) -> Quat {
    Quat::from_rotation_y(angle - FRAC_PI_2) * Quat::from_rotation_x(-FRAC_PI_2)
}

/// Rotation about world up matching a sim-plane direction angle for 3D meshes whose "forward" is
/// world −Z (sim +y).
#[inline]
pub fn yaw(angle: f32) -> Quat {
    Quat::from_rotation_y(angle - FRAC_PI_2)
}

/// Scale an sRGB colour's brightness into HDR (drives bloom on unlit decals).
pub fn hdr(color: Color, gain: f32) -> Color {
    let l = color.to_linear();
    Color::LinearRgba(LinearRgba::new(l.red * gain, l.green * gain, l.blue * gain, l.alpha))
}

/// Linear blend in sRGB space (`t` = 0 → `a`).
pub fn mix(a: Color, b: Color, t: f32) -> Color {
    let (a, b) = (a.to_srgba(), b.to_srgba());
    let l = |x: f32, y: f32| x + (y - x) * t;
    Color::srgba(l(a.red, b.red), l(a.green, b.green), l(a.blue, b.blue), l(a.alpha, b.alpha))
}

/// Multiply an sRGB colour's channels (clamped), keeping alpha.
pub fn lighten(c: Color, k: f32) -> Color {
    let s = c.to_srgba();
    Color::srgba((s.red * k).min(1.0), (s.green * k).min(1.0), (s.blue * k).min(1.0), s.alpha)
}

/// `#RRGGBB` / `#RRGGBBAA` → colour (magenta when malformed, so bad data is loud).
pub fn hex(s: &str) -> Color {
    let s = s.trim_start_matches('#');
    let byte = |i: usize| s.get(i..i + 2).and_then(|h| u8::from_str_radix(h, 16).ok());
    match (byte(0), byte(2), byte(4)) {
        (Some(r), Some(g), Some(b)) => {
            let a = byte(6).unwrap_or(255);
            Color::srgba_u8(r, g, b, a)
        }
        _ => Color::srgb(1.0, 0.0, 1.0),
    }
}

/// Element hues: warm metals for the player's arsenal, one saturated hue per element.
pub fn element_color(e: DamageType) -> Color {
    match e {
        DamageType::Kinetic => hex("#F4E3C1"),
        DamageType::Flame => hex("#FF7A1A"),
        DamageType::Storm => hex("#3FD8FF"),
        DamageType::Void => hex("#A45CFF"),
        DamageType::Plague => hex("#86E03A"),
        DamageType::Radiant => hex("#FFE27A"),
    }
}

pub fn rarity_color(r: Rarity) -> Color {
    match r {
        Rarity::Common => hex("#CFC6B4"),
        Rarity::Rare => hex("#4FA3FF"),
        Rarity::Epic => hex("#B865FF"),
        Rarity::Godforged => hex("#FFB82E"),
    }
}

pub fn build(app: &mut App) {
    app.add_systems(PreStartup, setup);
}

fn setup(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut images: ResMut<Assets<Image>>,
) {
    let game = &cfg.content.game;
    let palette = Palette {
        sphere: meshes.add(Sphere::new(1.0).mesh().uv(24, 14)),
        low_sphere: meshes.add(Sphere::new(1.0).mesh().uv(8, 6)),
        capsule: meshes.add(Capsule3d::new(0.5, 1.0)),
        cube: meshes.add(Cuboid::new(1.0, 1.0, 1.0)),
        cylinder: meshes.add(Cylinder::new(1.0, 1.0)),
        cone: meshes.add(Cone::new(1.0, 1.0)),
        torus: meshes.add(Torus::new(0.9, 1.0)),
        disc: meshes.add(Circle::new(1.0).mesh().resolution(40)),
        ring: meshes.add(Annulus::new(0.86, 1.0).mesh().resolution(48)),
        quad: meshes.add(Rectangle::new(1.0, 1.0)),
        rock_texture: images.add(rgba_image(ROCK_SIZE, ROCK_SIZE, rock_pixels(ROCK_SIZE), true)),
        blob_texture: images.add(rgba_image(BLOB_SIZE, BLOB_SIZE, blob_pixels(BLOB_SIZE), false)),
        block_texture: images.add(rgba_image(BLOCK_SIZE, BLOCK_SIZE, block_pixels(BLOCK_SIZE), false)),
        env_texture: images.add(rgba_image(BLOCK_SIZE * 2, BLOCK_SIZE, env_pixels(BLOCK_SIZE), false)),
        players: [
            hex(&game.player_colors[0]),
            hex(&game.player_colors[1]),
            hex(&game.player_colors[2]),
            hex(&game.player_colors[3]),
        ],
        danger: hex(&game.telegraph_color),
        sectors: HashMap::new(),
        annuli: HashMap::new(),
        cache: HashMap::new(),
        toon_cache: HashMap::new(),
        blob_cache: HashMap::new(),
    };
    commands.insert_resource(palette);
}

const ROCK_SIZE: u32 = 256;
const BLOB_SIZE: u32 = 64;
const BLOCK_SIZE: u32 = 128;

fn hash(x: i32, y: i32, k: u32) -> f32 {
    let mut h =
        (x as u32).wrapping_mul(0x8da6_b343) ^ (y as u32).wrapping_mul(0xd816_3841) ^ k.wrapping_mul(0xcb1a_b31f);
    h ^= h >> 13;
    h = h.wrapping_mul(0x5bd1_e995);
    h ^= h >> 15;
    (h & 0xffff) as f32 / 65535.0
}

/// Tileable value noise with integer `period`.
fn vnoise(x: f32, y: f32, period: i32) -> f32 {
    let (xi, yi) = (x.floor() as i32, y.floor() as i32);
    let (fx, fy) = (x - xi as f32, y - yi as f32);
    let s = |t: f32| t * t * (3.0 - 2.0 * t);
    let at = |i: i32, j: i32| hash(i.rem_euclid(period), j.rem_euclid(period), 7);
    let a = at(xi, yi) + (at(xi + 1, yi) - at(xi, yi)) * s(fx);
    let b = at(xi, yi + 1) + (at(xi + 1, yi + 1) - at(xi, yi + 1)) * s(fx);
    a + (b - a) * s(fy)
}

/// Painted cliff strata: ledged rock courses of uneven height, split by vertical joints. Each
/// block catches light on its top lip and falls into shadow under it, so a flat cliff face reads
/// as stacked, broken rock. Greyscale-warm (the toon material tints it) and tiles seamlessly.
fn rock_pixels(size: u32) -> Vec<u8> {
    const COURSES: i32 = 5;
    let mut out = Vec::with_capacity((size * size * 4) as usize);
    for py in 0..size {
        for px in 0..size {
            let u = px as f32 / size as f32;
            let v = py as f32 / size as f32;
            // Wavy course boundaries (periodic in u).
            let wob = (vnoise(u * 6.0, 3.0, 6) - 0.5) * 0.5 + (vnoise(u * 13.0, 7.0, 13) - 0.5) * 0.2;
            let cv = v * COURSES as f32 + wob;
            let course = cv.floor() as i32;
            let fv = cv - cv.floor();
            let ci = course.rem_euclid(COURSES);
            // Vertical joints: 2-4 blocks per course, staggered.
            let blocks = 2 + (hash(ci, 0, 11) * 3.0) as i32;
            let jw = (vnoise(v * 9.0, ci as f32 * 3.1, 9) - 0.5) * 0.12;
            let cu = u * blocks as f32 + hash(ci, 1, 12) + jw * blocks as f32;
            let block = cu.floor() as i32;
            let fu = cu - cu.floor();
            let id = hash(ci, block.rem_euclid(blocks), 13);
            let n = 0.5 * vnoise(u * 16.0, v * 16.0, 16)
                + 0.3 * vnoise(u * 32.0, v * 32.0, 32)
                + 0.2 * vnoise(u * 64.0, v * 64.0, 64);
            // Lit top lip, shadowed underside, dark joints.
            let lip = (1.0 - (fv / 0.12).clamp(0.0, 1.0)).powf(1.5);
            let under = ((fv - 0.78) / 0.22).clamp(0.0, 1.0).powf(1.4);
            let joint = 1.0 - (fu.min(1.0 - fu) * blocks as f32 * 10.0).clamp(0.0, 1.0);
            let seam = 1.0 - (fv.min(1.0 - fv) * 26.0).clamp(0.0, 1.0);
            let mut lum = 0.5 + 0.2 * (id - 0.5) + 0.26 * (n - 0.5);
            lum += 0.2 * lip - 0.24 * under;
            lum *= 1.0 - 0.75 * joint.max(seam);
            let to8 = |f: f32| (f.clamp(0.0, 1.0) * 255.0) as u8;
            out.extend_from_slice(&[to8(lum), to8(lum * 0.95), to8(lum * 0.9), 255]);
        }
    }
    out
}

/// A hand-painted block face: a dark ink border, a light bevel on the upper/left lips and a
/// shadowed lower/right lip, brushwork and a few chips inside. Every face of a cube (and the band
/// of a cylinder) maps the whole image, so each face gets its own painted edges.
fn block_pixels(size: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity((size * size * 4) as usize);
    for py in 0..size {
        for px in 0..size {
            let u = (px as f32 + 0.5) / size as f32;
            let v = (py as f32 + 0.5) / size as f32;
            let edge = u.min(1.0 - u).min(v.min(1.0 - v));
            let n = 0.55 * vnoise(u * 6.0, v * 6.0, 6)
                + 0.3 * vnoise(u * 14.0 + 3.0, v * 5.0, 14)
                + 0.15 * vnoise(u * 32.0, v * 32.0, 32);
            // Brush strokes: blotchy value with a faint drag, like a loaded brush across the face.
            let stroke = vnoise(u * 4.0, v * 12.0, 12);
            let mut lum = 0.78 + 0.28 * (n - 0.5) + 0.05 * (stroke - 0.5);
            // Bevel: light catches the top/left lips, the bottom/right lips turn away.
            let lip = (1.0 - ((edge - 0.035) / 0.07).clamp(0.0, 1.0)).powf(1.3);
            let lit_side = if u.min(v) < (1.0 - u).min(1.0 - v) { 1.0 } else { -0.8 };
            lum += 0.2 * lip * lit_side;
            // Chips knocked out of the edges.
            let chip = vnoise(u * 11.0 + 7.0, v * 11.0 + 2.0, 11);
            if edge < 0.09 && chip > 0.7 {
                lum *= 0.6;
            }
            // Ink border.
            let ink = 1.0 - ((edge - 0.012) / 0.016).clamp(0.0, 1.0);
            lum *= 1.0 - 0.85 * ink;
            let to8 = |f: f32| (f.clamp(0.0, 1.0) * 255.0) as u8;
            out.extend_from_slice(&[to8(lum), to8(lum * 0.97), to8(lum * 0.93), 255]);
        }
    }
    out
}

/// The env kit's stone atlas, `2 × size` wide: the painted block face on the left, and on the
/// right borderless stone with vertical brush drags and a few chisel marks (lathes and bevels map
/// it, so turned and bevelled stone reads painted without a border on every facet).
fn env_pixels(size: u32) -> Vec<u8> {
    let block = block_pixels(size);
    let mut out = Vec::with_capacity((size * size * 8) as usize);
    for py in 0..size {
        let row = (py * size * 4) as usize;
        out.extend_from_slice(&block[row..row + (size * 4) as usize]);
        for px in 0..size {
            let u = (px as f32 + 0.5) / size as f32;
            let v = (py as f32 + 0.5) / size as f32;
            let n = 0.5 * vnoise(u * 5.0, v * 5.0, 5)
                + 0.3 * vnoise(u * 13.0 + 2.0, v * 13.0, 13)
                + 0.2 * vnoise(u * 29.0, v * 29.0, 29);
            // Vertical drags of a loaded brush.
            let drag = vnoise(u * 16.0, v * 2.0 + 5.0, 16);
            let mut lum = 0.8 + 0.24 * (n - 0.5) + 0.1 * (drag - 0.5);
            // Sparse chisel nicks.
            let nick = vnoise(u * 21.0 + 4.0, v * 21.0 + 9.0, 21);
            if nick > 0.8 {
                lum *= 0.82;
            }
            let to8 = |f: f32| (f.clamp(0.0, 1.0) * 255.0) as u8;
            out.extend_from_slice(&[to8(lum), to8(lum * 0.97), to8(lum * 0.93), 255]);
        }
    }
    out
}

/// Soft radial falloff in alpha (contact shadows).
fn blob_pixels(size: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity((size * size * 4) as usize);
    for py in 0..size {
        for px in 0..size {
            let x = (px as f32 + 0.5) / size as f32 * 2.0 - 1.0;
            let y = (py as f32 + 0.5) / size as f32 * 2.0 - 1.0;
            let r2 = (x * x + y * y).min(1.0);
            let a = (1.0 - r2).powf(1.6);
            out.extend_from_slice(&[255, 255, 255, (a * 255.0) as u8]);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_parses() {
        let c = hex("#FF8000").to_srgba();
        assert!((c.red - 1.0).abs() < 1e-3 && (c.green - 128.0 / 255.0).abs() < 1e-3 && c.blue.abs() < 1e-3);
        assert_eq!(hex("nope").to_srgba(), Color::srgb(1.0, 0.0, 1.0).to_srgba());
    }

    #[test]
    fn rock_tiles_seamlessly() {
        // The noise lattice wraps, so opposite edges sample the same field.
        assert!((vnoise(0.0, 3.3, 8) - vnoise(8.0, 3.3, 8)).abs() < 1e-5);
        assert_eq!(rock_pixels(16).len(), 16 * 16 * 4);
    }

    #[test]
    fn flat_maps_sim_to_world() {
        // Mesh +Y (sim +y) turned to angle 0 must point at sim +x = world +x.
        let v = flat(0.0) * Vec3::Y;
        assert!((v - Vec3::X).length() < 1e-5, "{v}");
        // Unrotated flat: 2D (x, y) → world (x, 0, −y).
        let p = flat(FRAC_PI_2) * Vec3::new(1.0, 2.0, 0.0);
        assert!((p - Vec3::new(1.0, 0.0, -2.0)).length() < 1e-5, "{p}");
    }
}
