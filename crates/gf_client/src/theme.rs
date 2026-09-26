//! # The UI theme: tokens, type ramp, fonts, scale and layout constants (UI_STYLE §3–§5)
//!
//! Everything the HUD and panels colour, set in type or place by a fixed number lives here, so
//! one file answers "which gold?", "which size?" and "where does the Hearth sit?".
//!
//! * [`tok`]: the colour tokens (§3). Reserved hues (rarity, element, player, god) are **not**
//!   here; read them through `palette::{rarity_color, element_color}`, `game.ron` and `gods.ron`
//!   ([`player_color`], [`god_colors`]).
//! * [`Ty`]: the closed type ramp (§4.2). Every (face, weight, size) builds its own glyph atlas,
//!   so new styles are added to the enum, never inline.
//! * [`UiFonts`]: the seven embedded faces and the `FontSource::List` stacks. The default font is
//!   Alegreya Sans Medium, so a plain `Text` is already body type.
//! * UiScale by window height (§5.1), safe margins and region rects at 1920×1080 (§5.3), the
//!   z-layers (§11.9) and [`HudRects`] (§11.8).

use gf_content::ContentDb;
use gf_engine::client::{FontFeatureTag, FontFeatures, LetterSpacing, LineHeight};
use gf_engine::prelude::*;

// ───────────────────────────── colour tokens ─────────────────────────────

/// `0xRRGGBB` → an sRGB colour, usable in `const`.
pub const fn hx(rgb: u32) -> Color {
    Color::srgb_u8((rgb >> 16) as u8, (rgb >> 8) as u8, rgb as u8)
}

/// Colour tokens (UI_STYLE §3). Hex values are sRGB.
pub mod tok {
    use super::hx;
    use gf_engine::prelude::Color;

    // Surfaces and metal (§3.1).
    pub const LAC0: Color = hx(0x0B0807);
    pub const LAC1: Color = hx(0x130D0A);
    pub const LAC2: Color = hx(0x2A1E16);
    pub const LAC3: Color = hx(0x4A3624);
    pub const SCRIM: Color = hx(0x06050A);
    pub const POOL: Color = hx(0x050302);
    pub const GOLD_HI: Color = hx(0xFFECB0);
    pub const GOLD_LT: Color = hx(0xF2C667);
    pub const GOLD_MD: Color = hx(0xC9933E);
    pub const GOLD_DK: Color = hx(0x7A5424);
    pub const GOLD_SH: Color = hx(0x3B2610);
    /// The metal ramp, top to bottom: hi 0 → lt 0.22 → md 0.5 → dk 0.78 → md 1.0.
    pub const GOLD_RAMP: [(Color, f32); 5] =
        [(GOLD_HI, 0.0), (GOLD_LT, 0.22), (GOLD_MD, 0.5), (GOLD_DK, 0.78), (GOLD_MD, 1.0)];
    pub const BRONZE: [Color; 4] = [hx(0xE6CFA0), hx(0xB08A5A), hx(0x6E5234), hx(0x2E2012)];
    pub const STEEL: [Color; 3] = [hx(0xEEF2F5), hx(0x9AA4AE), hx(0x4E5660)];

    // Text, states and fills (§3.2).
    pub const PARCH: Color = hx(0xF4E6C8);
    pub const PARCH_DIM: Color = hx(0xB9A98C);
    pub const PARCH_MUTE: Color = hx(0x7D705E);
    pub const NUMERAL: Color = hx(0xFFF8EA);
    pub const INK: Color = hx(0x0A0706);
    pub const INK_TEXT: Color = hx(0x1A120B);
    pub const ICHOR: Color = hx(0xFFE9B0);
    pub const ICHOR_GLOW: Color = hx(0xFFC873);
    pub const READY_GLOW: Color = hx(0xFFC24A);
    pub const LOSS: Color = hx(0xA58C86);
    /// Molten ramp, meniscus first: ult ring, Overdrive hex, heat ring, event bars.
    pub const MOLTEN: [Color; 5] = [hx(0xFFFBEA), hx(0xFFF6DA), hx(0xFFC95A), hx(0xE8942E), hx(0x7A3E12)];
    /// The icon tint of a cooling slot (§6.1a): darkened and desaturated by the multiply.
    pub const COOLING: Color = hx(0x6E655C);
    /// Bone: POI glyphs, currencies, portraits' default tint.
    pub const BONE: Color = hx(0xE6CFA0);
    /// Bronze-ivory studs and chrome gems.
    pub const IVORY_GEM: Color = hx(0xFFE7A6);

    // Vitals and enemies (§3.3).
    pub const HP_LT: Color = hx(0xE8574C);
    pub const HP: Color = hx(0xC8323A);
    pub const HP_DK: Color = hx(0x7E1420);
    pub const HP_GHOST: Color = hx(0xF0B37A);
    pub const HP_EDGE: Color = hx(0xFFF4DC);
    pub const WARD: Color = hx(0xDCE6EA);
    pub const BOSS_FILL: [Color; 3] = [hx(0xFF7A4A), hx(0xC8261E), hx(0x5E0A08)];
    pub const BOSS_GHOST: Color = hx(0xF7C98A);
    pub const ELITE_FILL: [Color; 2] = [hx(0xF06A4A), hx(0x9A1E1A)];
    pub const ENEMY_LABEL: Color = hx(0xFF8A70);
    pub const ENEMY_PHASE: Color = hx(0xFFB08A);
    pub const THREAT: [Color; 2] = [hx(0xFFC95A), hx(0xE8602E)];
    pub const WARLORD_GLYPH: Color = hx(0xFF7A5A);
    /// Real danger only (§2): always paired with white.
    pub const DANGER: Color = hx(0xFF3B30);
    pub const DANGER_WHITE: Color = hx(0xFFFFFF);
}

/// A player's colour (`game.ron: player_colors`, slot 0 = P1). Rings, bands, pips and chevrons
/// only (§2, §3.4).
pub fn player_color(db: &ContentDb, slot: usize) -> Color {
    crate::palette::hex(db.game.player_colors.get(slot % 4).map_or("#FFFFFF", String::as_str))
}

/// A god's (primary, secondary) colours from `gods.ron`. Red gods (Pyra, Umbra-Rex) show their
/// secondary next to white text or small glyphs (§3.4, §7.2).
pub fn god_colors(db: &ContentDb, key: &str) -> Option<(Color, Color)> {
    db.gods
        .iter()
        .find(|g| g.key == key)
        .map(|g| (crate::palette::hex(&g.color), crate::palette::hex(&g.color_secondary)))
}

// ───────────────────────────── fonts ─────────────────────────────

const CINZEL: &[u8] = include_bytes!("../../../assets/fonts/Cinzel-Variable.ttf");
const ALEGREYA_REGULAR: &[u8] = include_bytes!("../../../assets/fonts/AlegreyaSans-Regular.ttf");
const ALEGREYA_MEDIUM: &[u8] = include_bytes!("../../../assets/fonts/AlegreyaSans-Medium.ttf");
const ALEGREYA_BOLD: &[u8] = include_bytes!("../../../assets/fonts/AlegreyaSans-Bold.ttf");
const ALEGREYA_ITALIC: &[u8] = include_bytes!("../../../assets/fonts/AlegreyaSans-Italic.ttf");
const DEJAVU_SANS: &[u8] = include_bytes!("../../../assets/fonts/DejaVuSans.ttf");
const DEJAVU_SERIF_BOLD: &[u8] = include_bytes!("../../../assets/fonts/DejaVuSerif-Bold.ttf");

/// The embedded faces (SIL OFL Cinzel and Alegreya Sans; DejaVu for symbols only).
///
/// Handles select faces (each `Font` asset is registered under its own alias family), so the
/// static Alegreya faces are never asked for a weight they don't have. Cinzel is variable: its
/// weight comes from `TextFont.weight`.
#[derive(Resource, Clone)]
pub struct UiFonts {
    /// Legacy heading face used by the pre-kit HUD (`text_in(.., &fonts.display)`): Cinzel.
    pub display: Handle<Font>,
    pub cinzel: Handle<Font>,
    pub regular: Handle<Font>,
    pub medium: Handle<Font>,
    pub bold: Handle<Font>,
    pub italic: Handle<Font>,
    pub dejavu_sans: Handle<Font>,
    pub dejavu_serif: Handle<Font>,
}

/// Install every UI face. The default font (plain `Text`) becomes Alegreya Sans Medium.
pub fn install_fonts(app: &mut App) -> UiFonts {
    // `install_fonts` replaces the default font and adds one more face; we pass DejaVu Serif Bold.
    let dejavu_serif = gf_engine::client::install_fonts(app, ALEGREYA_MEDIUM, DEJAVU_SERIF_BOLD);
    let faces = gf_engine::client::install_font_faces(
        app,
        &[CINZEL, ALEGREYA_REGULAR, ALEGREYA_MEDIUM, ALEGREYA_BOLD, ALEGREYA_ITALIC, DEJAVU_SANS],
    );
    let [cinzel, regular, medium, bold, italic, dejavu_sans] = <[Handle<Font>; 6]>::try_from(faces).expect("6 faces");
    UiFonts { display: cinzel.clone(), cinzel, regular, medium, bold, italic, dejavu_sans, dejavu_serif }
}

/// Font face of a [`Ty`].
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Face {
    Cinzel,
    Regular,
    Medium,
    Bold,
    Italic,
}

/// The type ramp (UI_STYLE §4.2), a closed list. Sizes are logical px at UiScale 1; a few styles
/// allow the alternative sizes the spec lists through [`UiFonts::font_px`].
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum Ty {
    /// VICTORY / THE FORGE GOES COLD. Cinzel 900 96, 0.14 em.
    DisplayXl,
    /// Region banner. Cinzel 700 44, 0.08 em.
    Banner,
    /// Combo callouts, TEAM OVERDRIVE READY. Cinzel 900 38, 0.06 em.
    Callout,
    /// THE FORGE (32 boon title, 30 help). Cinzel 800 36, 0.14 em.
    Title,
    /// Boss and Warlord name. Cinzel 800 30, 0.12 em.
    BossName,
    /// Boon name (auto-fit 26 → 20), part detail name. Cinzel 800 26, 0.04 em.
    CardName,
    /// Forge DPS. Cinzel 800 38.
    NumXl,
    /// End-screen stats. Cinzel 800 30.
    NumL,
    /// Party-card numbers and shards (26), stage timer (24), heat ring (22). Cinzel 800.
    NumM,
    /// Seals count (19), wallet (20). Cinzel 800.
    NumS,
    /// Section labels (THE WEAPON), socket labels. Cinzel 800 15, 0.18 em.
    Label,
    /// Prompt verbs (16), tracker words, aim mode, OFFERS (14), god line (13). Cinzel 800, 0.12 em.
    LabelS,
    /// SURGE (20), downed-marker seconds (18). Cinzel 900, 0.24 em.
    Alert,
    /// Rarity words, HEAT / CHARGES / SHARDS, stat labels, keycap letters, pills. Cinzel 800 12, 0.16 em.
    Micro,
    /// Rules text, toasts. Alegreya Medium 18 (17 for toasts and detail).
    Body,
    /// Sub-lines, hints, pin names (16 / 15 / 14). Alegreya Medium.
    BodyS,
    /// Numbers and keywords inside body text; names in toasts. Alegreya Bold.
    Strong,
    /// Sub-lines, flavour (24 end line / 18 banner sub / 17). Alegreya Italic.
    Flavour,
    /// Live small numerals (26 ×N / 19 HP / 15 HP max / 16 distances / 14 buff seconds). Alegreya Bold, tnum.
    Num,
    /// Damage numbers: 21, crit 28. Alegreya Bold, tnum. Pops use `UiTransform.scale`.
    Dmg,
    /// The F10 debug strip. Alegreya Medium 12, tnum.
    Debug,
}

impl Ty {
    /// (face, weight, default size, tracking in em, tabular lining figures)
    pub const fn spec(self) -> (Face, u16, f32, f32, bool) {
        use Face::*;
        match self {
            Ty::DisplayXl => (Cinzel, 900, 96.0, 0.14, false),
            Ty::Banner => (Cinzel, 700, 44.0, 0.08, false),
            Ty::Callout => (Cinzel, 900, 38.0, 0.06, false),
            Ty::Title => (Cinzel, 800, 36.0, 0.14, false),
            Ty::BossName => (Cinzel, 800, 30.0, 0.12, false),
            Ty::CardName => (Cinzel, 800, 26.0, 0.04, false),
            Ty::NumXl => (Cinzel, 800, 38.0, 0.0, false),
            Ty::NumL => (Cinzel, 800, 30.0, 0.0, false),
            Ty::NumM => (Cinzel, 800, 24.0, 0.0, false),
            Ty::NumS => (Cinzel, 800, 20.0, 0.0, false),
            Ty::Label => (Cinzel, 800, 15.0, 0.18, false),
            Ty::LabelS => (Cinzel, 800, 14.0, 0.12, false),
            Ty::Alert => (Cinzel, 900, 20.0, 0.24, false),
            Ty::Micro => (Cinzel, 800, 12.0, 0.16, false),
            Ty::Body => (Medium, 500, 18.0, 0.0, false),
            Ty::BodyS => (Medium, 500, 16.0, 0.0, false),
            Ty::Strong => (Bold, 700, 18.0, 0.0, false),
            Ty::Flavour => (Italic, 400, 17.0, 0.0, false),
            Ty::Num => (Bold, 700, 19.0, 0.0, true),
            Ty::Dmg => (Bold, 700, 21.0, 0.0, true),
            Ty::Debug => (Medium, 500, 12.0, 0.0, true),
        }
    }

    pub const fn size(self) -> f32 {
        self.spec().2
    }

    /// Body styles get a fixed line height (§4.2: 23 at 18 px).
    const fn line_height(self, px: f32) -> Option<f32> {
        match self {
            Ty::Body | Ty::BodyS | Ty::Strong | Ty::Flavour => Some((px * 1.28).round()),
            _ => None,
        }
    }
}

impl UiFonts {
    fn face(&self, face: Face) -> &Handle<Font> {
        match face {
            Face::Cinzel => &self.cinzel,
            Face::Regular => &self.regular,
            Face::Medium => &self.medium,
            Face::Bold => &self.bold,
            Face::Italic => &self.italic,
        }
    }

    /// The `TextFont` of a style at its default size.
    pub fn font(&self, ty: Ty) -> TextFont {
        self.font_px(ty, ty.size())
    }

    /// The `TextFont` of a style at one of its listed sizes. The stack ends in DejaVu, so parley
    /// falls back per cluster for symbols (UI strings should still use icons, §4.1).
    pub fn font_px(&self, ty: Ty, px: f32) -> TextFont {
        let (face, weight, _, _, tabular) = ty.spec();
        let fallback = if face == Face::Cinzel { &self.dejavu_serif } else { &self.dejavu_sans };
        let font_features = if tabular {
            FontFeatures::builder()
                .enable(FontFeatureTag::TABULAR_FIGURES)
                .enable(FontFeatureTag::LINING_FIGURES)
                .build()
        } else {
            FontFeatures::default()
        };
        TextFont {
            font: FontSource::List(vec![
                FontSource::Handle(self.face(face).clone()),
                FontSource::Handle(fallback.clone()),
            ]),
            font_size: FontSize::Px(px),
            weight: FontWeight(weight),
            style: if face == Face::Italic { FontStyle::Italic } else { FontStyle::Normal },
            font_features,
            ..default()
        }
    }

    /// Everything a text node of this style needs except the string and colour: the font, the
    /// tracking and (for body styles) the line height.
    pub fn style(&self, ty: Ty, px: f32) -> (TextFont, LetterSpacing, LineHeight) {
        let em = ty.spec().3;
        let line = ty.line_height(px).map_or(LineHeight::RelativeToFont(1.2), LineHeight::Px);
        (self.font_px(ty, px), LetterSpacing::Px(px * em), line)
    }
}

/// The legibility shadow every HUD text over the world carries (§2): (0, 2) in ink at 0.9.
pub fn ink_shadow() -> TextShadow {
    TextShadow { offset: Vec2::new(0.0, 2.0), color: tok::INK.with_alpha(0.9) }
}

// ───────────────────────────── scale, safe areas, regions ─────────────────────────────

/// Logical canvas the spec is drawn on (UiScale 1.0).
pub const CANVAS: Vec2 = Vec2::new(1920.0, 1080.0);
/// Safe margin on every side (TV-safe sets 48).
pub const MARGIN: f32 = 24.0;

/// The UiScale curve (§5.1) for a physical window height: linear above 1080, compressed below
/// so body text stays above 11 physical px.
pub fn ui_scale_for_height(physical_height: f32) -> f32 {
    let r = physical_height / CANVAS.y;
    if r < 1.0 { 1.0 - (1.0 - r) * 0.6 } else { r }
}

/// Player HUD scale option (0.85–1.15, default 1), multiplied into UiScale.
#[derive(Resource, Clone, Copy, Debug)]
pub struct HudScale(pub f32);

impl Default for HudScale {
    fn default() -> Self {
        Self(1.0)
    }
}

/// Anchored regions at 1920×1080 (§5.3): (x0, y0, x1, y1) in logical px.
pub mod region {
    pub const PARTY: [f32; 4] = [24.0, 24.0, 282.0, 190.0];
    pub const TOASTS: [f32; 4] = [16.0, 196.0, 464.0, 292.0];
    pub const MINIMAP: [f32; 4] = [1616.0, 24.0, 1896.0, 200.0];
    pub const TRACKER_X1: f32 = 1896.0;
    pub const TRACKER_Y0: f32 = 218.0;
    pub const TRACKER_FLOOR: f32 = 486.0;
    pub const BOSS_BAR: [f32; 4] = [610.0, 24.0, 1310.0, 150.0];
    pub const CALLOUT_BASELINE: f32 = 150.0;
    pub const CALLOUT_BASELINE_BOSS: f32 = 206.0;
    pub const BANNER: [f32; 4] = [560.0, 180.0, 1360.0, 280.0];
    pub const BOON_CHIP: [f32; 4] = [1566.0, 846.0, 1896.0, 918.0];
    pub const HEARTH: [f32; 4] = [24.0, 878.0, 580.0, 1056.0];
    pub const ARSENAL: [f32; 4] = [1550.0, 924.0, 1896.0, 1056.0];
    /// Clear zones (§5.4): nothing persistent inside.
    pub const SOUTH_LANE: [f32; 4] = [700.0, 880.0, 1220.0, 1080.0];
    pub const W_LANE: [f32; 4] = [0.0, 490.0, 170.0, 730.0];
    pub const E_LANE: [f32; 4] = [1750.0, 490.0, 1920.0, 730.0];
}

/// Z-order of UI roots (`GlobalZIndex`, §11.9).
pub mod z {
    pub const WORLD: i32 = 1;
    pub const PINS: i32 = 5;
    pub const POOLS: i32 = 8;
    pub const HUD: i32 = 10;
    pub const TRANSIENT: i32 = 12;
    pub const BOON_CHIP: i32 = 14;
    pub const PANEL: i32 = 20;
    pub const END: i32 = 30;
    pub const HELP: i32 = 40;
    pub const DEBUG: i32 = 50;
    /// QA boards (`--ui-shot kit|icons`), above everything.
    pub const QA: i32 = 100;
}

/// Logical rects of the persistent HUD clusters, filled after layout by the HUD lane (§11.8).
/// Edge pins, prompt clamping, ally tags and damage numbers keep out of them.
#[derive(Resource, Default, Clone, Debug)]
pub struct HudRects {
    pub rects: Vec<Rect>,
}

impl HudRects {
    /// Does `p` (logical px) fall inside any HUD rect grown by `pad`?
    pub fn hits(&self, p: Vec2, pad: f32) -> bool {
        self.rects.iter().any(|r| r.inflate(pad).contains(p))
    }
}

/// Recompute `UiScale` from the window height and the HUD scale option (§5.1).
fn update_ui_scale(
    windows: Query<&Window, With<gf_engine::client::PrimaryWindow>>,
    hud: Res<HudScale>,
    mut scale: ResMut<UiScale>,
) {
    let Ok(window) = windows.single() else { return };
    let (height, factor) = gf_engine::client::window_physical_height(window);
    if height < 1.0 {
        return;
    }
    // UiScale multiplies the window scale factor, so divide it out: the physical size of the HUD
    // then depends on the physical window height alone.
    let target = ui_scale_for_height(height) * hud.0.clamp(0.85, 1.15) / factor.max(0.01);
    if (scale.0 - target).abs() > 1e-4 {
        scale.0 = target;
    }
}

pub fn build(app: &mut App) {
    let hud_scale = app.world().resource::<crate::ClientConfig>().hud_scale;
    app.insert_resource(HudScale(hud_scale)).init_resource::<HudRects>().add_systems(PreUpdate, update_ui_scale);
}
