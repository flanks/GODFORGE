//! Painterly NPR materials (§12, §14: "stylized NPR shading (toon-ramp + rim light), not
//! realistic PBR").
//!
//! Every material here is an `ExtendedMaterial<StandardMaterial, X>`: Bevy's own lighting,
//! shadows and fog stay in charge, and a WESL fragment shader (embedded in the binary) repaints
//! the result.
//!
//! * [`ToonMaterial`]: characters, enemies and props. Light is posterized into flat painted
//!   bands, dark bands lean saturated and cool, a coloured rim picks out silhouettes and a dark
//!   ink edge closes them. Build one with [`toon`] / [`toon_from_standard`] and a [`ToonStyle`].
//! * [`FloorMaterial`]: the arena floor, painted procedurally in world space from the biome
//!   palette (plaza pavers, flagstones, dirt, worn paths and roads, soot, lava cracks, inlays,
//!   laid paving, holes for sunken channels). One per room, one per 32 u chunk on biome maps,
//!   where the region tint rides on vertex colours.
//! * [`AbyssMaterial`]: the animated sea far below the platform (magma, deep water, night sky or
//!   raw chaos, per biome).
//!
//! Presentation only: nothing here feeds the simulation. The room seed only varies the paint.

use crate::palette::{hdr, hex, lighten, mix};
use gf_engine::client::{
    AsBindGroup, ExtendedMaterial, MaterialExtension, MaterialPlugin, ShaderRef, ShaderType, embedded_asset,
};
use gf_engine::prelude::*;

pub type ToonMaterial = ExtendedMaterial<StandardMaterial, Toon>;
pub type FloorMaterial = ExtendedMaterial<StandardMaterial, Floor>;
pub type AbyssMaterial = ExtendedMaterial<StandardMaterial, Abyss>;

/// World height of the abyss surface below the arena floor (y = 0).
pub const ABYSS_Y: f32 = -7.0;

pub fn build(app: &mut App) {
    embedded_asset!(app, "shaders/toon.wesl");
    embedded_asset!(app, "shaders/floor.wesl");
    embedded_asset!(app, "shaders/abyss.wesl");
    app.add_plugins((
        MaterialPlugin::<ToonMaterial>::default(),
        MaterialPlugin::<FloorMaterial>::default(),
        MaterialPlugin::<AbyssMaterial>::default(),
    ));
}

// ───────────────────────────── toon ─────────────────────────────

/// GPU layout of `ToonParams` in `toon.wesl` (field order matters).
#[derive(Clone, Copy, Debug, Default, ShaderType, Reflect)]
pub struct ToonParams {
    /// rgb rim colour (linear, HDR allowed), a = rim strength.
    pub rim: Vec4,
    /// rgb colour the dark bands lean toward, a = amount.
    pub shade: Vec4,
    /// x = toon amount (0 PBR … 1 full ramp), y = rim width, z = paint strength,
    /// w = paint space (0 = object normal, 1 = world position).
    pub settings: Vec4,
    /// x = band size in stops, y = terminator softness, z = shadow saturation boost,
    /// w = shadow lift (keeps the darkest band readable).
    pub ramp: Vec4,
    /// rgb colour low parts fade into (linear, HDR allowed: abyss glow / mist), a = strength.
    pub heat: Vec4,
    /// x = heat base height (world y), y = heat fade height, z = ink edge width, w = ink strength.
    pub extra: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct Toon {
    #[uniform(100)]
    pub params: ToonParams,
}

impl MaterialExtension for Toon {
    fn fragment_shader() -> ShaderRef {
        "embedded://gf_client/shaders/toon.wesl".into()
    }
}

/// Art-direction knobs of one toon surface. Presets: [`ToonStyle::prop`], [`ToonStyle::hero`],
/// [`ToonStyle::foe`], [`ToonStyle::rock`].
#[derive(Clone, Copy, Debug)]
pub struct ToonStyle {
    pub rim: Color,
    pub rim_strength: f32,
    pub rim_width: f32,
    /// Hue the shadow bands lean toward (saturated cool by default).
    pub shade: Color,
    pub shade_amount: f32,
    pub toon: f32,
    /// Brush-texture value variation (0 = flat).
    pub paint: f32,
    /// Paint in world space (static scenery) instead of normal space (moving characters).
    pub world_paint: bool,
    /// Band size in stops of received light.
    pub band: f32,
    pub softness: f32,
    pub shadow_saturation: f32,
    /// Lifts the darkest band (0..1) so heroes never sink into shadow.
    pub lift: f32,
    /// Colour the lower parts fade into and its strength (cliffs over the abyss).
    pub heat: Color,
    pub heat_strength: f32,
    pub heat_base: f32,
    pub heat_height: f32,
    /// Dark ink edge at grazing angles (painted outline on props without an ink hull).
    pub ink_width: f32,
    pub ink: f32,
}

/// Soft gold: the rim every prop shares.
const PROP_RIM: &str = "#FFD58A";
/// Warm red: the rim every enemy shares (reads as hostile at a glance).
const FOE_RIM: &str = "#FF5A3C";
/// Saturated cool shadow.
const SHADE: &str = "#3A4FA8";

impl ToonStyle {
    /// Static scenery: world-space brushwork, soft gold rim, painted ink edge.
    pub fn prop() -> Self {
        ToonStyle {
            rim: hex(PROP_RIM),
            rim_strength: 0.35,
            rim_width: 0.3,
            shade: hex(SHADE),
            shade_amount: 0.36,
            toon: 1.0,
            paint: 0.2,
            world_paint: true,
            band: 1.1,
            softness: 0.12,
            shadow_saturation: 0.6,
            lift: 0.0,
            heat: Color::BLACK,
            heat_strength: 0.0,
            heat_base: ABYSS_Y,
            heat_height: 1.0,
            ink_width: 0.22,
            ink: 0.55,
        }
    }

    /// Player characters: the brightest, cleanest read on screen. Rim in the player's colour.
    pub fn hero(player: Color) -> Self {
        ToonStyle {
            rim: hdr(player, 2.6),
            rim_strength: 1.0,
            rim_width: 0.42,
            shade_amount: 0.35,
            paint: 0.07,
            world_paint: false,
            band: 1.4,
            softness: 0.1,
            shadow_saturation: 0.35,
            lift: 0.35,
            ink_width: 0.0,
            ink: 0.0,
            ..Self::prop()
        }
    }

    /// Enemies: warm red rim, a little more shadow so heroes stay on top of the value ladder.
    pub fn foe() -> Self {
        ToonStyle {
            rim: hdr(hex(FOE_RIM), 2.2),
            rim_strength: 1.0,
            rim_width: 0.38,
            shade_amount: 0.45,
            paint: 0.1,
            world_paint: false,
            band: 1.2,
            softness: 0.1,
            shadow_saturation: 0.5,
            lift: 0.15,
            ink_width: 0.0,
            ink: 0.0,
            ..Self::prop()
        }
    }

    /// Worked metal: a softer ramp so specular glints survive the posterization.
    pub fn metal() -> Self {
        ToonStyle { toon: 0.6, band: 1.4, paint: 0.08, rim_strength: 0.5, ink: 0.4, ..Self::prop() }
    }

    /// Cliff rock: strong world brushwork, and the lower cliff fades into the abyss colour.
    pub fn rock(heat: Color, heat_strength: f32) -> Self {
        ToonStyle {
            rim_strength: 0.12,
            paint: 0.22,
            shade_amount: 0.65,
            heat,
            heat_strength,
            heat_base: ABYSS_Y,
            heat_height: 3.6,
            ink_width: 0.0,
            ink: 0.0,
            ..Self::prop()
        }
    }

    pub fn params(&self) -> ToonParams {
        let v = |c: Color, a: f32| {
            let l = c.to_linear();
            Vec4::new(l.red, l.green, l.blue, a)
        };
        ToonParams {
            rim: v(self.rim, self.rim_strength),
            shade: v(self.shade, self.shade_amount),
            settings: Vec4::new(self.toon, self.rim_width, self.paint, if self.world_paint { 1.0 } else { 0.0 }),
            ramp: Vec4::new(self.band, self.softness, self.shadow_saturation, self.lift),
            heat: v(self.heat, self.heat_strength),
            extra: Vec4::new(self.heat_base, self.heat_height, self.ink_width, self.ink),
        }
    }
}

/// Wrap any `StandardMaterial` (a glTF import, a textured prop) in the toon look.
pub fn toon_from_standard(base: StandardMaterial, style: &ToonStyle) -> ToonMaterial {
    ExtendedMaterial { base, extension: Toon { params: style.params() } }
}

/// A toon material from a base colour, an optional albedo texture and an emissive colour
/// (linear, HDR allowed). The environment kit and glTF characters build on this.
pub fn toon(color: Color, texture: Option<Handle<Image>>, emissive: LinearRgba, style: &ToonStyle) -> ToonMaterial {
    let base = StandardMaterial {
        base_color: color,
        base_color_texture: texture,
        emissive,
        perceptual_roughness: 0.85,
        reflectance: 0.2,
        alpha_mode: if color.alpha() < 1.0 { AlphaMode::Blend } else { AlphaMode::Opaque },
        ..default()
    };
    toon_from_standard(base, style)
}

// ───────────────────────────── floor ─────────────────────────────

/// Roads / worn paths a floor paints (rooms: spawn → exits; maps: the roads crossing the chunk).
pub const FLOOR_PATHS: usize = 8;
/// Fissure segments a floor paints (`Decor::LavaCrack`).
pub const FLOOR_CRACKS: usize = 48;
/// Circular inlays a floor paints (`Decor::FloorInlay`, map POI clearings).
pub const FLOOR_INLAYS: usize = 12;
/// Laid paving areas a floor paints (`Decor::Paving`).
pub const FLOOR_PAVING: usize = 12;
/// Holes cut into a floor (channels and pools sink below it).
pub const FLOOR_HOLES: usize = 8;
/// Solid footprints a map chunk darkens the ground under (soot and contact shade).
pub const FLOOR_FOOTINGS: usize = 32;

/// GPU layout of `FloorParams` in `floor.wesl` (field order matters).
#[derive(Clone, Copy, Debug, ShaderType, Reflect)]
pub struct FloorParams {
    /// rgb slab colour (linear), a = slab value contrast.
    pub stone: Vec4,
    /// rgb bare-ground colour, a = paving coverage (0 = mostly dirt … 1 = fully paved).
    pub dirt: Vec4,
    /// rgb gap / soot colour, a = soot strength toward the walls.
    pub mortar: Vec4,
    /// rgb crack glow (linear, HDR), a = glow strength.
    pub accent: Vec4,
    /// rgb inlay metal, a = unused.
    pub gold: Vec4,
    /// rgb cool temperature tint, a = temperature variation.
    pub cool: Vec4,
    /// xy = arena half extents (world x, z), z = slab size, w = fissure heat (1 molten … 0 cold).
    pub shape: Vec4,
    /// x = paint seed, y = moss / growth, z = vein sparkle, w = path count.
    pub style: Vec4,
    /// x = fissure count, yz = key light direction (world xz, toward the light), w = footing count.
    pub misc: Vec4,
    /// x = inlay count, y = paving count, z = hole count, w = 1 on biome maps (no rim soot).
    pub counts: Vec4,
    /// Paths: segments (ax, az, bx, bz) in world xz.
    pub paths: [Vec4; FLOOR_PATHS],
    /// Path widths, four per `Vec4` (0 = a narrow worn path).
    pub paths_w: [Vec4; FLOOR_PATHS / 4],
    /// Fissures: segments (ax, az, bx, bz) in world xz.
    pub cracks: [Vec4; FLOOR_CRACKS],
    /// Fissure widths, four per `Vec4`.
    pub cracks_w: [Vec4; FLOOR_CRACKS / 4],
    /// Inlays: (x, z, radius, rotation) in world xz.
    pub inlays: [Vec4; FLOOR_INLAYS],
    /// Inlay colour (linear) and variant: 0 plaza with a gold mosaic star, 1 rune ring,
    /// 2 clockface, 3 god sigil, 4 chaos glyph, 5 paved clearing (map POIs).
    pub inlays_c: [Vec4; FLOOR_INLAYS],
    /// Paving: (min x, min z, max x, max z) in world xz.
    pub paving: [Vec4; FLOOR_PAVING],
    /// Paving variants, four per `Vec4`: 0 flagstones, 1 herringbone, 2 tesserae, 3 broken.
    pub paving_v: [Vec4; FLOOR_PAVING / 4],
    /// Holes: (min x, min z, max x, max z) in world xz.
    pub holes: [Vec4; FLOOR_HOLES],
    /// Footings: (centre x, centre z, half x, half z) in world xz.
    pub footings: [Vec4; FLOOR_FOOTINGS],
}

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct Floor {
    #[uniform(100)]
    pub params: FloorParams,
}

impl MaterialExtension for Floor {
    fn fragment_shader() -> ShaderRef {
        "embedded://gf_client/shaders/floor.wesl".into()
    }
}

// ───────────────────────────── abyss ─────────────────────────────

/// GPU layout of `AbyssParams` in `abyss.wesl`.
#[derive(Clone, Copy, Debug, Default, ShaderType, Reflect)]
pub struct AbyssParams {
    /// rgb far / darkest colour.
    pub deep: Vec4,
    /// rgb body colour (crust, water, sky).
    pub mid: Vec4,
    /// rgb hot / luminous colour (linear, HDR), a = intensity.
    pub glow: Vec4,
    /// rgb haze hugging the cliffs, a = haze strength.
    pub mist: Vec4,
    /// xy = platform half extents (world x, z), z = style (0 magma, 1 water, 2 sky, 3 chaos),
    /// w = seed.
    pub shape: Vec4,
    /// x = flow speed, y = pattern scale, z = cliff glow width, w = far fade distance.
    pub flow: Vec4,
}

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct Abyss {
    #[uniform(100)]
    pub params: AbyssParams,
}

impl MaterialExtension for Abyss {
    fn fragment_shader() -> ShaderRef {
        "embedded://gf_client/shaders/abyss.wesl".into()
    }
}

// ───────────────────────────── biome looks ─────────────────────────────

/// What lies below a biome's arenas.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AbyssKind {
    Magma,
    Water,
    Sky,
    Chaos,
}

/// Presentation of one biome, derived from its palette (ground, accent, deep) and key.
#[derive(Clone, Copy, Debug)]
pub struct BiomeLook {
    pub abyss: AbyssKind,
    pub base: Color,
    pub accent: Color,
    pub deep: Color,
    /// Floor lava-crack density.
    pub cracks: f32,
    /// Moss / growth in the floor gaps.
    pub moss: f32,
    /// Glinting veins in the stone (night-sky marble, chaos seams).
    pub veins: f32,
    /// Key light colour and illuminance (lux).
    pub key: Color,
    pub key_lux: f32,
    /// Ambient (cool) colour and brightness.
    pub ambient: Color,
    pub ambient_brightness: f32,
    /// Brazier light intensity (lumens).
    pub brazier: f32,
}

impl BiomeLook {
    pub fn new(key: &str, [base, accent, deep]: [Color; 3]) -> Self {
        let abyss = if key.starts_with("verdant") {
            AbyssKind::Water
        } else if key.contains("spire") {
            AbyssKind::Sky
        } else if key.contains("unmaking") {
            AbyssKind::Chaos
        } else {
            AbyssKind::Magma
        };
        // (fissure heat, moss, veins, key colour, key lux, ambient colour, ambient brightness)
        let (cracks, moss, veins, key, key_lux, ambient, ambient_brightness) = match abyss {
            AbyssKind::Magma => (1.0, 0.0, 0.0, hex("#FFDDB8"), 8_000.0, hex("#6A5CB8"), 250.0),
            AbyssKind::Water => (0.4, 1.0, 0.0, hex("#E8F0D0"), 7_000.0, hex("#3C8090"), 260.0),
            AbyssKind::Sky => (0.4, 0.0, 1.0, hex("#FFE2C0"), 7_500.0, hex("#5060D0"), 250.0),
            AbyssKind::Chaos => (0.4, 0.0, 0.6, hex("#FFD0E8"), 7_000.0, hex("#7050C0"), 240.0),
        };
        BiomeLook {
            abyss,
            base,
            accent,
            deep,
            cracks,
            moss,
            veins,
            key,
            key_lux,
            ambient,
            ambient_brightness,
            brazier: 320_000.0,
        }
    }

    /// Painted-stone colour of the arena floor: a near-neutral stone leaning toward the biome's
    /// ground colour, so the glowing accents and the characters own the saturation.
    pub fn stone(&self) -> Color {
        let neutral = match self.abyss {
            AbyssKind::Magma => hex("#5E5A60"),
            AbyssKind::Water => hex("#56646A"),
            AbyssKind::Sky => hex("#5C5F78"),
            AbyssKind::Chaos => hex("#5A4C68"),
        };
        mix(neutral, self.base, 0.25)
    }

    /// Bare ground between the stones: dark, low-saturation earth (ash in the Cinder).
    pub fn dirt(&self) -> Color {
        let earth = match self.abyss {
            AbyssKind::Magma => hex("#332D30"),
            AbyssKind::Water => hex("#2E3A2C"),
            AbyssKind::Sky => hex("#34364A"),
            AbyssKind::Chaos => hex("#322A3C"),
        };
        mix(earth, self.base, 0.3)
    }

    /// Cliff rock colour (a shade cooler than the floor).
    pub fn rock(&self) -> Color {
        lighten(mix(self.stone(), hex("#2A2C3C"), 0.3), 1.25)
    }

    /// Worked stone of the room's architecture (walls, columns, plinths): darker than the floor
    /// so the fighting lanes and the characters stay on top of the value ladder.
    pub fn masonry(&self) -> Color {
        lighten(mix(self.stone(), hex("#34303A"), 0.3), 0.85)
    }

    /// The colour the lower cliffs fade into, and how strongly.
    pub fn cliff_heat(&self) -> (Color, f32) {
        match self.abyss {
            AbyssKind::Magma => (hdr(mix(self.accent, hex("#FF4A10"), 0.4), 1.25), 0.8),
            AbyssKind::Water => (hdr(mix(self.deep, self.accent, 0.25), 1.0), 0.9),
            AbyssKind::Sky => (mix(self.deep, self.accent, 0.3), 0.9),
            AbyssKind::Chaos => (hdr(mix(self.deep, self.accent, 0.45), 1.2), 0.9),
        }
    }

    pub fn abyss_params(&self, half: Vec2, seed: f32) -> AbyssParams {
        let v = |c: Color, a: f32| {
            let l = c.to_linear();
            Vec4::new(l.red, l.green, l.blue, a)
        };
        let (style, deep, mid, glow, mist, flow) = match self.abyss {
            AbyssKind::Magma => (
                0.0,
                v(mix(self.deep, hex("#060202"), 0.5), 0.0),
                v(mix(self.deep, hex("#2A0E08"), 0.6), 0.0),
                v(mix(self.accent, hex("#FF5A10"), 0.35), 2.2),
                v(mix(self.deep, hex("#B8380C"), 0.45), 0.3),
                Vec4::new(1.0, 0.2, 3.0, 26.0),
            ),
            AbyssKind::Water => (
                1.0,
                v(mix(self.deep, hex("#020A0C"), 0.5), 0.0),
                v(mix(self.deep, hex("#16585A"), 0.6), 0.0),
                v(self.accent, 1.6),
                v(mix(self.deep, self.accent, 0.35), 0.7),
                Vec4::new(0.6, 0.2, 4.0, 34.0),
            ),
            AbyssKind::Sky => (
                2.0,
                v(mix(self.deep, hex("#020310"), 0.5), 0.0),
                v(mix(self.deep, hex("#1C2458"), 0.5), 0.0),
                v(self.accent, 1.8),
                v(mix(self.base, self.accent, 0.4), 0.55),
                Vec4::new(0.4, 0.14, 6.0, 40.0),
            ),
            AbyssKind::Chaos => (
                3.0,
                v(mix(self.deep, hex("#050008"), 0.4), 0.0),
                v(mix(self.deep, hex("#2A0A3C"), 0.6), 0.0),
                v(self.accent, 2.4),
                v(mix(self.deep, self.accent, 0.5), 0.7),
                Vec4::new(0.8, 0.18, 5.0, 36.0),
            ),
        };
        AbyssParams { deep, mid, glow, mist, shape: Vec4::new(half.x, half.y, style, seed), flow }
    }

    /// The biome liquid at the surface (rivers, channels, pools, quench troughs): the abyss
    /// shader with its heat everywhere and no distance fade, at a finer pattern scale.
    pub fn liquid_params(&self, seed: f32) -> AbyssParams {
        let mut p = self.abyss_params(Vec2::ZERO, seed + 17.0);
        p.flow.y *= 2.2;
        p.flow.z = 1.0e5;
        p.flow.w = 1.0e6;
        p.mist.w = 0.0;
        // Rivers and channels read as molten, not as black crust with a few blobs.
        if self.abyss == AbyssKind::Magma {
            p.mid.w = 0.12;
        }
        p.glow.w *= match self.abyss {
            AbyssKind::Magma => 1.15,
            _ => 1.0,
        };
        p
    }
}
