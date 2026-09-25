//! The arena platform (§12): a thick slab of painted floor standing over an abyss.
//!
//! * The top is one fan-triangulated cap with an irregular, broken outline, painted by
//!   [`FloorMaterial`] in world space.
//! * The sides drop about nine units as faceted rock (a lit lip, a shadowed undercut, then a
//!   ragged cliff) in the toon rock material; their feet fade into the abyss colour.
//! * The abyss plane sits at [`ABYSS_Y`] and animates per biome ([`AbyssMaterial`]).
//!
//! Visual only: the outline jitter and the paint come from the replicated room seed, never the
//! other way round. The playable area is still `RoomDef::half_extents`.

use crate::camera::{KEY_LIGHT_FROM, w3};
use crate::materials::{
    ABYSS_Y, Abyss, AbyssMaterial, BiomeLook, FLOOR_CRACKS, FLOOR_PATHS, Floor, FloorMaterial, FloorParams,
    ToonMaterial, ToonStyle, toon,
};
use crate::palette::{Palette, hex, mix};
use crate::scene::RoomGeometry;
use gf_content::{Decor, RoomDef};
use gf_engine::client::{NotShadowCaster, NotShadowReceiver, triangle_mesh};
use gf_engine::prelude::*;

/// Floor margin past the playable half extents (the walls stand on it): x, north, south.
const MARGIN: Vec3 = Vec3::new(1.9, 1.9, 1.7);
/// Outline vertex spacing along the platform rim.
const RIM_STEP: f32 = 1.3;
/// Cliff profile: (depth below the floor, outward offset, per-vertex jitter).
const PROFILE: [(f32, f32, f32); 5] =
    [(0.0, 0.0, 0.0), (0.26, 0.12, 0.0), (0.55, -0.06, 0.05), (3.3, -0.1, 0.45), (9.5, -0.7, 0.7)];
/// World units per cliff texture tile.
const ROCK_TILE: f32 = 4.5;

pub struct TerrainStores<'a> {
    pub meshes: &'a mut Assets<Mesh>,
    pub toons: &'a mut Assets<ToonMaterial>,
    pub floors: &'a mut Assets<FloorMaterial>,
    pub abysses: &'a mut Assets<AbyssMaterial>,
}

fn hash01(i: u32, k: u32) -> f32 {
    let mut h = i.wrapping_mul(0x9E37_79B9) ^ k.wrapping_mul(0x85EB_CA6B);
    h ^= h >> 15;
    h = h.wrapping_mul(0x2C1B_3C6D);
    h ^= h >> 12;
    (h & 0xffff) as f32 / 65535.0
}

/// Spawn the floor, cliffs and abyss for `room`.
pub fn build(
    commands: &mut Commands,
    stores: TerrainStores,
    pal: &Palette,
    room: &RoomDef,
    look: &BiomeLook,
    seed: u32,
) {
    let half = room.half_extents;
    // World-space rectangle of the platform: x ∈ [-hx, hx], z ∈ [-zn, zs] (sim north = world −z).
    let hx = half.x + MARGIN.x;
    let (zn, zs) = (half.y + MARGIN.y, half.y + MARGIN.z);
    let outline = outline(hx, zn, zs, seed);

    // ── floor cap ──
    let centre = Vec3::new(0.0, 0.0, (zs - zn) * 0.5);
    let mut pos = vec![centre.to_array()];
    let mut idx = Vec::new();
    for (p, _) in &outline {
        pos.push([p.x, 0.0, p.y]);
    }
    let n = outline.len() as u32;
    for i in 0..n {
        let (a, b) = (1 + i, 1 + (i + 1) % n);
        // Counter-clockwise seen from above so the cap faces +Y.
        let (pa, pb) = (Vec3::from(pos[a as usize]), Vec3::from(pos[b as usize]));
        if (pa - centre).cross(pb - centre).y > 0.0 {
            idx.extend_from_slice(&[0, a, b]);
        } else {
            idx.extend_from_slice(&[0, b, a]);
        }
    }
    let normals = vec![[0.0, 1.0, 0.0]; pos.len()];
    let uvs = pos.iter().map(|p| [p[0] * 0.1, p[2] * 0.1]).collect();
    let cap = stores.meshes.add(triangle_mesh(pos, normals, uvs, idx));
    let floor = stores.floors.add(FloorMaterial {
        base: StandardMaterial { base_color: Color::WHITE, perceptual_roughness: 0.92, reflectance: 0.18, ..default() },
        extension: Floor { params: floor_params(room, look, seed) },
    });
    commands.spawn((RoomGeometry, Mesh3d(cap), MeshMaterial3d(floor), Transform::default(), NotShadowCaster));

    // ── cliffs ──
    let sides = stores.meshes.add(cliff_mesh(&outline, seed));
    let (heat, heat_strength) = look.cliff_heat();
    let rock = stores.toons.add(toon(
        look.rock(),
        Some(pal.rock_texture.clone()),
        LinearRgba::BLACK,
        &ToonStyle::rock(heat, heat_strength),
    ));
    commands.spawn((RoomGeometry, Mesh3d(sides), MeshMaterial3d(rock), Transform::default(), NotShadowCaster));

    // ── abyss ──
    let reach = Vec2::new(hx, zn.max(zs)) + Vec2::splat(90.0);
    let plane = stores.meshes.add(Plane3d::new(Vec3::Y, reach));
    let abyss = stores.abysses.add(AbyssMaterial {
        base: StandardMaterial { base_color: Color::WHITE, unlit: true, fog_enabled: false, ..default() },
        extension: Abyss { params: look.abyss_params(Vec2::new(hx, (zn + zs) * 0.5), (seed % 997) as f32) },
    });
    // The abyss shader measures distance from a box centred on the origin (the platform is
    // within a few tenths of that).
    commands.spawn((
        RoomGeometry,
        Mesh3d(plane),
        MeshMaterial3d(abyss),
        Transform::from_xyz(0.0, ABYSS_Y, 0.0),
        NotShadowCaster,
        NotShadowReceiver,
    ));
}

/// Rim of the platform in world xz with each point's outward direction. Every point is pushed
/// outward only, so the polygon stays star-shaped around the centre (a fan triangulates it).
fn outline(hx: f32, zn: f32, zs: f32, seed: u32) -> Vec<(Vec2, Vec2)> {
    let corners = [Vec2::new(-hx, zs), Vec2::new(hx, zs), Vec2::new(hx, -zn), Vec2::new(-hx, -zn)];
    let mut out = Vec::new();
    let mut k = 0u32;
    for side in 0..4 {
        let (a, b) = (corners[side], corners[(side + 1) % 4]);
        let along = b - a;
        let steps = (along.length() / RIM_STEP).ceil().max(1.0) as u32;
        // Outward normal of this side (the rectangle is centred on x, off-centre on z).
        let normal = match side {
            0 => Vec2::Y,
            1 => Vec2::X,
            2 => Vec2::NEG_Y,
            _ => Vec2::NEG_X,
        };
        for s in 0..steps {
            k += 1;
            let t = s as f32 / steps as f32;
            let p = a + along * t;
            let (dir, push) = if s == 0 {
                // Corner: push diagonally.
                let prev = match side {
                    0 => Vec2::NEG_X,
                    1 => Vec2::Y,
                    2 => Vec2::X,
                    _ => Vec2::NEG_Y,
                };
                ((normal + prev).normalize(), 0.25 + 0.35 * hash01(k, seed))
            } else {
                // Broken rim: mostly small bites, now and then a bigger jut.
                let r = hash01(k, seed ^ 0x51ED);
                let push = 0.1 + 0.45 * r + if r > 0.86 { 0.5 } else { 0.0 };
                (normal, push)
            };
            out.push((p + dir * push, dir));
        }
    }
    out
}

/// Faceted cliff walls hanging from the rim, flat-shaded, UVs in world units.
fn cliff_mesh(outline: &[(Vec2, Vec2)], seed: u32) -> Mesh {
    let n = outline.len();
    // Ring vertices per profile layer.
    let ring = |layer: usize, i: usize| -> Vec3 {
        let (p, dir) = outline[i % n];
        let (depth, off, jit) = PROFILE[layer];
        let j = (hash01(i as u32 * 7 + layer as u32, seed ^ 0xC11F) - 0.5) * 2.0 * jit;
        let q = p + dir * (off + j);
        Vec3::new(q.x, -depth, q.y)
    };
    let mut perimeter = vec![0.0f32; n + 1];
    for i in 0..n {
        perimeter[i + 1] = perimeter[i] + outline[i].0.distance(outline[(i + 1) % n].0);
    }
    let (mut pos, mut nor, mut uv, mut idx) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
    for i in 0..n {
        let outward = (outline[i].1 + outline[(i + 1) % n].1).normalize_or_zero();
        for layer in 0..PROFILE.len() - 1 {
            let quad = [ring(layer, i), ring(layer, i + 1), ring(layer + 1, i + 1), ring(layer + 1, i)];
            let us = [perimeter[i], perimeter[i + 1], perimeter[i + 1], perimeter[i]];
            let mut normal = (quad[1] - quad[0]).cross(quad[3] - quad[0]).normalize_or_zero();
            let flip = normal.x * outward.x + normal.z * outward.y < 0.0;
            if flip {
                normal = -normal;
            }
            let base = pos.len() as u32;
            for (v, u) in quad.iter().zip(us) {
                pos.push(v.to_array());
                nor.push(normal.to_array());
                uv.push([u / ROCK_TILE, -v.y / ROCK_TILE]);
            }
            if flip {
                idx.extend_from_slice(&[base, base + 3, base + 2, base, base + 2, base + 1]);
            } else {
                idx.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
            }
        }
    }
    triangle_mesh(pos, nor, uv, idx)
}

fn lin4(c: Color, a: f32) -> Vec4 {
    let l = c.to_linear();
    Vec4::new(l.red, l.green, l.blue, a)
}

fn floor_params(room: &RoomDef, look: &BiomeLook, seed: u32) -> FloorParams {
    let stone = look.stone();
    let dirt = mix(mix(look.base, stone, 0.35), hex("#1A1410"), 0.25);
    let mortar = mix(look.deep, hex("#050308"), 0.35);
    let mut paths = [Vec4::ZERO; FLOOR_PATHS];
    let mut count = 0;
    let from = w3(room.player_spawn, 0.0);
    let targets = room.exits.iter().copied().chain(room.anvil);
    for to in targets.take(FLOOR_PATHS) {
        let to = w3(to, 0.0);
        paths[count] = Vec4::new(from.x, from.z, to.x, to.z);
        count += 1;
    }
    let mut cracks = [Vec4::ZERO; FLOOR_CRACKS];
    let mut widths = [0.0f32; FLOOR_CRACKS];
    let mut n_cracks = 0;
    for d in &room.decor {
        if let Decor::LavaCrack { from, to, width } = *d
            && n_cracks < FLOOR_CRACKS
        {
            let (a, b) = (w3(from, 0.0), w3(to, 0.0));
            cracks[n_cracks] = Vec4::new(a.x, a.z, b.x, b.z);
            widths[n_cracks] = width;
            n_cracks += 1;
        }
    }
    let cracks_w = std::array::from_fn(|i| Vec4::from_slice(&widths[i * 4..i * 4 + 4]));
    let light = Vec2::new(KEY_LIGHT_FROM.x, KEY_LIGHT_FROM.z).normalize();
    FloorParams {
        stone: lin4(stone, 0.35),
        dirt: lin4(dirt, 0.52),
        mortar: lin4(mortar, 0.8),
        accent: lin4(look.accent, if look.cracks >= 1.0 { 3.0 } else { 1.0 }),
        gold: lin4(hex("#C9A24E"), 6.0),
        cool: lin4(mix(look.ambient, hex("#4A5CB0"), 0.5), 0.4),
        shape: Vec4::new(room.half_extents.x, room.half_extents.y, 1.6, look.cracks),
        style: Vec4::new((seed % 1000) as f32, look.moss, look.veins, count as f32),
        misc: Vec4::new(n_cracks as f32, light.x, light.y, 0.0),
        paths,
        cracks,
        cracks_w,
    }
}
