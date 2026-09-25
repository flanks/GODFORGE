//! Shared render resources and the colour language (§12): element hues, rarity colours, P1–P4
//! player colours, danger red-white telegraphs. Greybox primitives stand in for authored glTF
//! until the Blender pipeline delivers models; every mesh and material goes through this cache so
//! swapping in real assets touches one module.

use crate::ClientConfig;
use gf_core::damage::DamageType;
use gf_core::rarity::Rarity;
use gf_engine::client::{Face, rgba_image};
use gf_engine::prelude::*;
use std::collections::HashMap;
use std::f32::consts::FRAC_PI_2;

/// Material families.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Look {
    /// Painted matte surface.
    Matte,
    /// Worked metal (anvils, weapons, gold trim).
    Metal,
    /// Emissive: blooms in HDR (projectiles, ichor, embers).
    Glow,
    /// Matte with a faint inner glow (status-afflicted enemies, hot metal).
    Smolder,
    /// Flat unlit translucent decal on the ground (telegraphs, hazards, rings).
    Decal,
    /// Additive light (particles, flashes).
    Additive,
    /// Translucent lit (echoes, downed wraiths).
    Ghost,
    /// Inverted-hull ink outline: unlit, front faces culled (painterly silhouettes, §12).
    Ink,
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
    pub ground_texture: Handle<Image>,
    pub players: [Color; 4],
    pub danger: Color,
    sectors: HashMap<u8, Handle<Mesh>>,
    annuli: HashMap<u16, Handle<Mesh>>,
    cache: HashMap<(u32, Look), Handle<StandardMaterial>>,
}

impl Palette {
    /// Cached material for a colour and look.
    pub fn mat(&mut self, mats: &mut Assets<StandardMaterial>, color: Color, look: Look) -> Handle<StandardMaterial> {
        let key = (color_key(color), look);
        if let Some(h) = self.cache.get(&key) {
            return h.clone();
        }
        let h = mats.add(make_material(color, look));
        self.cache.insert(key, h.clone());
        h
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

fn make_material(color: Color, look: Look) -> StandardMaterial {
    let lin = color.to_linear();
    let emissive = |gain: f32| LinearRgba::rgb(lin.red * gain, lin.green * gain, lin.blue * gain);
    match look {
        Look::Matte => {
            StandardMaterial { base_color: color, perceptual_roughness: 0.88, reflectance: 0.25, ..default() }
        }
        Look::Metal => StandardMaterial { base_color: color, perceptual_roughness: 0.36, metallic: 0.85, ..default() },
        Look::Glow => StandardMaterial { base_color: color, emissive: emissive(4.0), ..default() },
        Look::Smolder => {
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
        ground_texture: images.add(rgba_image(GROUND_SIZE, GROUND_SIZE, ground_pixels(GROUND_SIZE), true)),
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
    };
    commands.insert_resource(palette);
}

const GROUND_SIZE: u32 = 256;

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

/// Painted flagstones: jittered slabs with dark mortar and brush-like value noise. Greyscale-warm
/// so the per-biome material tint carries the palette. Tiles seamlessly.
fn ground_pixels(size: u32) -> Vec<u8> {
    const CELLS: i32 = 6;
    let mut out = Vec::with_capacity((size * size * 4) as usize);
    for py in 0..size {
        for px in 0..size {
            let u = px as f32 / size as f32 * CELLS as f32;
            let v = py as f32 / size as f32 * CELLS as f32;
            let (ci, cj) = (u.floor() as i32, v.floor() as i32);
            let (mut d1, mut d2, mut id) = (f32::MAX, f32::MAX, 0.0);
            for dj in -1..=1 {
                for di in -1..=1 {
                    let (x, y) = (ci + di, cj + dj);
                    let (wx, wy) = (x.rem_euclid(CELLS), y.rem_euclid(CELLS));
                    let c = Vec2::new(x as f32 + 0.15 + 0.7 * hash(wx, wy, 1), y as f32 + 0.15 + 0.7 * hash(wx, wy, 2));
                    let d = c.distance(Vec2::new(u, v));
                    if d < d1 {
                        d2 = d1;
                        d1 = d;
                        id = hash(wx, wy, 3);
                    } else if d < d2 {
                        d2 = d;
                    }
                }
            }
            let fu = px as f32 / size as f32;
            let fv = py as f32 / size as f32;
            let n = 0.55 * vnoise(fu * 8.0, fv * 8.0, 8)
                + 0.3 * vnoise(fu * 16.0, fv * 16.0, 16)
                + 0.15 * vnoise(fu * 32.0, fv * 32.0, 32);
            let edge = ((d2 - d1) * 7.0).clamp(0.0, 1.0).powf(0.5);
            let slab = 0.64 + 0.12 * id + 0.2 * (n - 0.5);
            let lum = (0.36 + (slab - 0.36) * edge).clamp(0.0, 1.0);
            let to8 = |f: f32| (f.clamp(0.0, 1.0) * 255.0) as u8;
            out.extend_from_slice(&[to8(lum), to8(lum * 0.94), to8(lum * 0.86), 255]);
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
    fn ground_tiles_seamlessly() {
        // The noise lattice wraps, so opposite edges sample the same field.
        assert!((vnoise(0.0, 3.3, 8) - vnoise(8.0, 3.3, 8)).abs() < 1e-5);
        assert_eq!(ground_pixels(16).len(), 16 * 16 * 4);
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
