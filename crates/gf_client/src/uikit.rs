//! # The UI kit: GODFORGE's widgets (UI_STYLE §8, §10, §11)
//!
//! Spawn helpers for every piece the HUD and panels are built from, on top of [`crate::theme`].
//! Data goes in through small state components; the kit's systems ([`fx`]) do the motion: bars
//! drain behind a ghost, slots sweep and pop when ready, rings pour, buttons swap textures,
//! glows breathe. Widget code never writes layout every frame.
//!
//! ## Using it
//!
//! Every builder takes the parent's `ChildSpawnerCommands` and the read-only [`UiKit`] resource
//! (fonts, kit textures, icons) and returns the widget's root entity:
//!
//! ```ignore
//! fn spawn_hearth(mut commands: Commands, kit: Res<UiKit>) {
//!     commands.spawn((uikit::abs(170.0, 1012.0 - 30.0, 60.0, 60.0), GlobalZIndex(theme::z::HUD)))
//!         .with_children(|p| {
//!             let q = uikit::slot(p, &kit, SlotSpec::ability("kits/valdris_q", 60.0).key("Q"));
//!             // later, every frame: *states.get_mut(q)? = SlotState::cooling(remaining, secs);
//!         });
//! }
//! ```
//!
//! | Builder | State component (write it; the kit animates) |
//! |---|---|
//! | [`quiet_plate`], [`gilt_panel`], [`gilt_card`], [`tooltip`], [`dashed_plate`] | [`KitCard`] (selection ring on cards) |
//! | [`corner_pool`], [`halo`], [`scrim`] | – |
//! | [`label`]/[`UiKit::text`], [`rich`], [`outlined_text`], [`gradient_text`] | – |
//! | [`ember_knot`], [`horn_corners`], [`sun_crest`] | – |
//! | [`icon`], [`rarity_gem`], [`element_cabochon`] | [`UiIcon`] (swap key or size) |
//! | [`keycap`], [`key_chip`] | – |
//! | [`button`], [`chip`] | `InteractionDisabled` (disable); hover and press are automatic |
//! | [`pill`], [`ribbon`], [`pchip`], [`delta_chip`] | – |
//! | [`slot`] | [`SlotState`] (cooldown fraction and seconds, disabled) |
//! | [`medallion`], [`hearth_medallion`] | [`KitRing`] on the ult ring ([`HearthParts`]) |
//! | [`niche_card`] (boon card shell) | [`KitHover`] (lift and aura on hover), [`NicheParts`] |
//! | [`ring_meter`] | [`KitRing`] |
//! | [`bar`] | [`KitBar`] (value and ward, 0..1) |
//! | [`plates`], [`dash_pips`] | [`KitPlates`], [`KitPips`] |
//! | [`overdrive_hex`] | [`MoltenFill`] |
//! | [`pin`] | `UiTransform.rotation` of [`PinParts::frame`] aims the nub |
//! | [`prompt_plate`] | – |
//! | [`ally_tag`] | [`AllyTagParts`] (the bar's [`KitBar`], the capsule's display) |
//! | [`minimap_frame`] (phase-3 hook, hidden) | [`MinimapFrame`] (`content`, `icons`) |
//! | [`toast`] (one row of the toast rail) | – (the HUD pools three and tweens them) |
//! | icons inside text: [`UiKit::inline_icon`] as a child of the `Text` | – |
//!
//! Icon keys for content live in [`ik`] (`ik::part(key)`, `ik::element(e)`, `ik::poi(kind)`…).
//!
//! Motion helpers for anything else: [`Tween`], [`Pulse`], [`pop`].
//!
//! ## Rules the builders already follow
//!
//! * Sizes are logical px at 1920×1080 (UiScale 1). `theme` sets UiScale from the window height.
//! * @2x textures slice with `max_corner_scale: 0.5`; keep sliced nodes at least the manifest's
//!   logical size on each axis.
//! * Chamfered cooldown sweeps sit on a child with `border_radius = 1.71 × chamfer` (§8.1).
//! * Decorative nodes carry `Pickable::IGNORE`, so they never block buttons.
//! * No symbol glyphs in strings: keys, currencies and deltas are icons.

pub mod assets;
pub mod fx;
pub mod gallery;

pub use assets::{KitEntry, KitMode, UiDecode, UiIcon, UiKit};
pub use fx::{
    BarParts, KitBar, KitButton, KitCard, KitPips, KitPlates, KitRing, MoltenFill, MoltenMaterial, PinParts, Pulse,
    RingStyle, SlotParts, SlotState, Tween, TweenTarget, pop,
};

use crate::palette::rarity_color;
use crate::theme::{Ty, UiFonts, hx, ink_shadow, tok};
use gf_core::rarity::Rarity;
use gf_engine::client::{Hovered, InteractionDisabled, Pickable, UiButton, embedded_asset};
use gf_engine::prelude::*;

/// Install the kit: fonts, embedded art, the motion systems and the QA boards.
pub fn build(app: &mut App, fonts: UiFonts) {
    embedded_asset!(app, "shaders/ui_molten.wesl");
    assets::install(app, fonts);
    fx::build(app);
    gallery::build(app);
}

// ───────────────────────────── node helpers ─────────────────────────────

/// An absolute node at (x, y) with size (w, h), in logical px relative to its parent.
pub fn abs(x: f32, y: f32, w: f32, h: f32) -> Node {
    Node { position_type: PositionType::Absolute, left: px(x), top: px(y), width: px(w), height: px(h), ..default() }
}

/// An absolute node filling its parent.
pub fn fill() -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: px(0.0),
        top: px(0.0),
        width: percent(100.0),
        height: percent(100.0),
        ..default()
    }
}

/// An absolute node inset by `d` on every side of its parent.
pub fn inset(d: f32) -> Node {
    Node { position_type: PositionType::Absolute, left: px(d), top: px(d), right: px(d), bottom: px(d), ..default() }
}

/// An absolute node of size (w, h) centred on its parent.
pub fn centered(w: f32, h: f32) -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: percent(50.0),
        top: percent(50.0),
        width: px(w),
        height: px(h),
        margin: UiRect { left: px(-w / 2.0), top: px(-h / 2.0), ..default() },
        ..default()
    }
}

/// An absolute node of size (w, h) centred on the point (x, y) of its parent.
pub fn centered_at(x: f32, y: f32, w: f32, h: f32) -> Node {
    abs(x - w / 2.0, y - h / 2.0, w, h)
}

/// A flex row with a gap, children centred on the cross axis.
pub fn row(gap: f32) -> Node {
    Node { flex_direction: FlexDirection::Row, align_items: AlignItems::Center, column_gap: px(gap), ..default() }
}

/// A flex column with a gap.
pub fn column(gap: f32) -> Node {
    Node { flex_direction: FlexDirection::Column, row_gap: px(gap), ..default() }
}

/// A two-stop vertical gradient.
pub fn v_gradient(top: Color, bottom: Color) -> BackgroundGradient {
    BackgroundGradient(vec![LinearGradient::to_bottom(vec![ColorStop::auto(top), ColorStop::auto(bottom)]).into()])
}

/// The soft gold hairline ramp (lt → md → dk) as a border gradient.
pub fn gold_hairline(alpha: f32) -> BorderGradient {
    BorderGradient(vec![
        LinearGradient::to_bottom(vec![
            ColorStop::auto(tok::GOLD_LT.with_alpha(alpha)),
            ColorStop::auto(tok::GOLD_MD.with_alpha(alpha)),
            ColorStop::auto(tok::GOLD_DK.with_alpha(alpha)),
        ])
        .into(),
    ])
}

/// A drop shadow (§8.3): combat plates `(0.55, 3, 9)`, slots `(0.75, 2.5, 5)`, premium panels
/// `(0.75, 8, 18)`, cards `(0.85, 12, 14)`.
pub fn drop_shadow(alpha: f32, y: f32, blur: f32) -> BoxShadow {
    BoxShadow::new(Color::BLACK.with_alpha(alpha), px(0.0), px(y), px(0.0), px(blur))
}

/// A glow: a zero-offset coloured shadow.
pub fn glow(color: Color, blur: f32, spread: f32) -> BoxShadow {
    BoxShadow::new(color, px(0.0), px(0.0), px(spread), px(blur))
}

/// The key of a rarity in texture and icon names.
pub fn rarity_key(r: Rarity) -> &'static str {
    match r {
        Rarity::Common => "common",
        Rarity::Rare => "rare",
        Rarity::Epic => "epic",
        Rarity::Godforged => "godforged",
    }
}

// ───────────────────────────── text ─────────────────────────────

impl UiKit {
    /// A text node in a ramp style at its default size, with the ink legibility shadow.
    pub fn text(&self, ty: Ty, s: impl Into<String>, color: Color) -> impl Bundle {
        self.text_px(ty, ty.size(), s, color)
    }

    /// A text node in a ramp style at one of its listed sizes, with the ink legibility shadow.
    pub fn text_px(&self, ty: Ty, px: f32, s: impl Into<String>, color: Color) -> impl Bundle {
        let (font, spacing, line) = self.fonts.style(ty, px);
        (Text::new(s), font, spacing, line, TextColor(color), ink_shadow(), TextLayout::no_wrap(), Pickable::IGNORE)
    }

    /// Text without a shadow (on plates and panels, where the lacquer already gives contrast).
    pub fn text_flat(&self, ty: Ty, px: f32, s: impl Into<String>, color: Color) -> impl Bundle {
        let (font, spacing, line) = self.fonts.style(ty, px);
        (Text::new(s), font, spacing, line, TextColor(color), Pickable::IGNORE)
    }

    /// Flat text with its own tracking (em), for tight captions under icons.
    pub fn text_tracked(&self, ty: Ty, px: f32, em: f32, s: impl Into<String>, color: Color) -> impl Bundle {
        let (font, _, line) = self.fonts.style(ty, px);
        (Text::new(s), font, gf_engine::client::LetterSpacing::Px(px * em), line, TextColor(color), Pickable::IGNORE)
    }

    /// A span inside a [`rich`] text.
    pub fn span(&self, ty: Ty, px: f32, s: impl Into<String>, color: Color) -> impl Bundle {
        let (font, spacing, line) = self.fonts.style(ty, px);
        (TextSpan::new(s), font, spacing, line, TextColor(color))
    }
}

/// A label: ramp text with the ink shadow, as a child of `p`.
pub fn label(p: &mut ChildSpawnerCommands, kit: &UiKit, ty: Ty, px: f32, s: impl Into<String>, color: Color) -> Entity {
    p.spawn(kit.text_px(ty, px, s, color)).id()
}

/// Rich text: spans of (style, text, colour) at one size, e.g. numbers in `ichor` and element
/// keywords in their hue inside rules text (§7.2). Wraps at `max_width` when given.
pub fn rich(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    px: f32,
    spans: &[(Ty, &str, Color)],
    max_width: Option<f32>,
    justify: Justify,
) -> Entity {
    let Some(((ty0, s0, c0), rest)) = spans.split_first() else { return p.spawn(Node::default()).id() };
    let (font, spacing, line) = kit.fonts.style(*ty0, px);
    let mut e = p.spawn((
        Text::new(*s0),
        font,
        spacing,
        line,
        TextColor(*c0),
        ink_shadow(),
        TextLayout::justify(justify),
        Pickable::IGNORE,
    ));
    if let Some(w) = max_width {
        e.insert(Node { max_width: px_val(w), ..default() });
    }
    e.with_children(|t| {
        for (ty, s, c) in rest {
            t.spawn(kit.span(*ty, px, *s, *c));
        }
    });
    e.id()
}

fn px_val(v: f32) -> Val {
    Val::Px(v)
}

/// Single-instance display text with a real ink outline: four copies offset ±1 px behind it
/// (§11.2). Never for pooled texts.
pub fn outlined_text(p: &mut ChildSpawnerCommands, kit: &UiKit, ty: Ty, px: f32, s: &str, color: Color) -> Entity {
    let (font, spacing, line) = kit.fonts.style(ty, px);
    p.spawn((Node::default(), Pickable::IGNORE))
        .with_children(|c| {
            for (dx, dy) in [(-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)] {
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: Val::Px(dx),
                        top: Val::Px(dy + 1.0),
                        ..default()
                    },
                    Text::new(s),
                    font.clone(),
                    spacing,
                    line,
                    TextColor(tok::INK.with_alpha(0.9)),
                    TextLayout::no_wrap(),
                    Pickable::IGNORE,
                ));
            }
            c.spawn((
                Text::new(s),
                font.clone(),
                spacing,
                line,
                TextColor(color),
                TextLayout::no_wrap(),
                Pickable::IGNORE,
            ));
        })
        .id()
}

/// Where Cinzel's capitals sit in its line box (fractions of the height), for gradient bands.
const CAP_TOP: f32 = 0.2;
const CAP_BOTTOM: f32 = 0.8;

/// Display text in a vertical gradient (top colour first), built from clipped copies: the base
/// copy in the last colour and `stops.len() - 1` bands over it. With `outline`, the §11.2 ink
/// outline sits behind. For VICTORY, THE FORGE, the region banner, boss names.
pub fn gradient_text(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    ty: Ty,
    px: f32,
    s: &str,
    stops: &[Color],
    outline: bool,
) -> Entity {
    let (font, spacing, line) = kit.fonts.style(ty, px);
    let n = stops.len().max(1);
    let base = *stops.last().unwrap_or(&tok::GOLD_LT);
    let text = |color: Color| {
        (Text::new(s), font.clone(), spacing, line, TextColor(color), TextLayout::no_wrap(), Pickable::IGNORE)
    };
    p.spawn((Node::default(), Pickable::IGNORE))
        .with_children(|c| {
            if outline {
                for (dx, dy) in [(-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (0.0, 2.0)] {
                    c.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: Val::Px(dx),
                            top: Val::Px(dy),
                            ..default()
                        },
                        text(tok::INK.with_alpha(if dy > 1.5 { 0.6 } else { 0.9 })),
                    ));
                }
            }
            c.spawn(text(base));
            // Bands from the bottom up: band i covers the top (n - i) / n of the glyph box.
            for (i, color) in stops.iter().enumerate().take(n - 1).rev() {
                let frac = (i + 1) as f32 / n as f32;
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: Val::Px(0.0),
                        top: Val::Px(0.0),
                        width: percent(100.0),
                        height: percent((CAP_TOP + frac * (CAP_BOTTOM - CAP_TOP)) * 100.0),
                        overflow: Overflow::clip(),
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|b| {
                    b.spawn(text(*color));
                });
            }
        })
        .id()
}

// ───────────────────────────── surfaces ─────────────────────────────

/// Which corner of the screen or parent.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Corner {
    TopLeft,
    TopRight,
    BottomLeft,
    BottomRight,
}

impl Corner {
    pub const ALL: [Corner; 4] = [Corner::TopLeft, Corner::TopRight, Corner::BottomLeft, Corner::BottomRight];

    fn key(self) -> &'static str {
        match self {
            Corner::TopLeft => "tl",
            Corner::TopRight => "tr",
            Corner::BottomLeft => "bl",
            Corner::BottomRight => "br",
        }
    }
}

/// Radial `pool` stops with a power-1.6 falloff from `alpha` at the centre to 0.
fn pool_stops(color: Color, alpha: f32) -> Vec<ColorStop> {
    (0..=6)
        .map(|i| {
            let t = i as f32 / 6.0;
            ColorStop::percent(color.with_alpha(alpha * (1.0 - t).powf(1.6)), t * 100.0)
        })
        .collect()
}

/// A corner shadow pool (§6.1): an elliptical radial `pool` gradient of radii (w/2, h/2)
/// centred on a screen corner, under a HUD cluster. Never hit-tests.
pub fn corner_pool(p: &mut ChildSpawnerCommands, corner: Corner, w: f32, h: f32, alpha: f32) -> Entity {
    let (hw, hh) = (w / 2.0, h / 2.0);
    let mut node = Node { position_type: PositionType::Absolute, width: px(w), height: px(h), ..default() };
    match corner {
        Corner::TopLeft => (node.left, node.top) = (px(-hw), px(-hh)),
        Corner::TopRight => (node.right, node.top) = (px(-hw), px(-hh)),
        Corner::BottomLeft => (node.left, node.bottom) = (px(-hw), px(-hh)),
        Corner::BottomRight => (node.right, node.bottom) = (px(-hw), px(-hh)),
    }
    p.spawn((
        node,
        BackgroundGradient(vec![
            RadialGradient::new(
                UiPosition::CENTER,
                RadialGradientShape::Ellipse(px(hw), px(hh)),
                pool_stops(tok::POOL, alpha),
            )
            .into(),
        ]),
        Pickable::IGNORE,
    ))
    .id()
}

/// A soft elliptical halo behind display text or a cluster (`pool` by default).
pub fn halo(p: &mut ChildSpawnerCommands, node: Node, color: Color, alpha: f32) -> Entity {
    p.spawn((
        node,
        BackgroundGradient(vec![
            RadialGradient::new(UiPosition::CENTER, RadialGradientShape::ClosestSide, pool_stops(color, alpha)).into(),
        ]),
        Pickable::IGNORE,
    ))
    .id()
}

/// A full-parent modal dim in `scrim` (§3.1: 0.18 Forge, 0.55 help, 0.64 boons, 0.68 end).
pub fn scrim(p: &mut ChildSpawnerCommands, alpha: f32) -> Entity {
    p.spawn((fill(), BackgroundColor(tok::SCRIM.with_alpha(alpha)))).id()
}

/// A quiet plate (§8.1): the combat-HUD surface. Lacquer gradient at `alpha`, a 1.1 px soft gold
/// hairline, a combat drop shadow and a faint top sheen. `node` sets size, position and padding.
pub fn quiet_plate(
    p: &mut ChildSpawnerCommands,
    mut node: Node,
    alpha: f32,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    node.border = UiRect::all(px(1.1));
    if node.border_radius == BorderRadius::ZERO {
        node.border_radius = BorderRadius::all(px(6.0));
    }
    let radius = node.border_radius;
    p.spawn((
        node,
        v_gradient(tok::LAC2.with_alpha(alpha), tok::LAC1.with_alpha(alpha)),
        gold_hairline(0.85 * alpha.max(0.6)),
        drop_shadow(0.55, 3.0, 9.0),
    ))
    .with_children(|c| {
        sheen_layer(c, radius, 0.10);
        content(c);
    })
    .id()
}

/// A top-down warm sheen over a surface's upper 35 %, with a 1 px highlight line.
fn sheen_layer(c: &mut ChildSpawnerCommands, radius: BorderRadius, alpha: f32) {
    c.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: px(0.0),
            right: px(0.0),
            top: px(0.0),
            height: percent(35.0),
            border_radius: BorderRadius { bottom_left: CornerRadius::ZERO, bottom_right: CornerRadius::ZERO, ..radius },
            ..default()
        },
        v_gradient(tok::GOLD_HI.with_alpha(alpha), tok::GOLD_HI.with_alpha(0.0)),
        Pickable::IGNORE,
    ));
    c.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: px(8.0),
            right: px(8.0),
            top: px(0.0),
            height: px(1.0),
            ..default()
        },
        BackgroundGradient(vec![
            LinearGradient::to_right(vec![
                ColorStop::auto(tok::GOLD_HI.with_alpha(0.0)),
                ColorStop::auto(tok::GOLD_HI.with_alpha(0.28)),
                ColorStop::auto(tok::GOLD_HI.with_alpha(0.0)),
            ])
            .into(),
        ]),
        Pickable::IGNORE,
    ));
}

/// Ornament of a premium panel.
#[derive(Clone, Copy, Debug, Default)]
pub struct PanelStyle {
    /// Forge-horn corners at this size (30, 40, 44, 60, 64 or 76).
    pub horns: Option<u32>,
    /// Sun-crest on the top edge at this height (62 or 50).
    pub crest: Option<u32>,
    /// Bronze frame and horns (non-MVP end cards).
    pub bronze: bool,
    /// Body opacity (0.95 by default).
    pub alpha: Option<f32>,
}

impl PanelStyle {
    pub fn horns(size: u32) -> Self {
        Self { horns: Some(size), ..default() }
    }

    pub fn crest(mut self, height: u32) -> Self {
        self.crest = Some(height);
        self
    }

    pub fn bronze(mut self) -> Self {
        self.bronze = true;
        self
    }
}

/// A premium gilt panel (§7): lacquer body, the 9-slice gilt frame, optional forge-horn corners
/// and sun-crest, and the premium drop shadow. Content goes inside `node`'s padding.
pub fn gilt_panel(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    mut node: Node,
    style: PanelStyle,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    node.border_radius = BorderRadius::all(px(10.0));
    let a = style.alpha.unwrap_or(0.95);
    p.spawn((node, drop_shadow(0.75, 8.0, 18.0)))
        .with_children(|c| {
            lacquer_body(c, BorderRadius::all(px(10.0)), a);
            content(c);
            let frame = if style.bronze { "frames/gilt_panel_bronze@2x.png" } else { "frames/gilt_panel@2x.png" };
            c.spawn((fill(), kit.tex(frame), ZIndex(2), Pickable::IGNORE));
            if let Some(size) = style.horns {
                horn_corners(c, kit, size, style.bronze);
            }
            if let Some(h) = style.crest {
                sun_crest(c, kit, h);
            }
        })
        .id()
}

/// The lacquer body of premium surfaces: `lac2 → lac1`, a warm top sheen and an inner edge
/// darkening (Bevy has no inset shadows; a radial vignette stands in).
fn lacquer_body(c: &mut ChildSpawnerCommands, radius: BorderRadius, alpha: f32) {
    c.spawn((
        Node { border_radius: radius, ..fill() },
        v_gradient(tok::LAC2.with_alpha(alpha), tok::LAC1.with_alpha(alpha)),
        Pickable::IGNORE,
    ))
    .with_children(|b| {
        b.spawn((
            Node { border_radius: radius, ..fill() },
            BackgroundGradient(vec![
                RadialGradient::new(
                    UiPosition::CENTER,
                    RadialGradientShape::FarthestCorner,
                    vec![
                        ColorStop::percent(Color::BLACK.with_alpha(0.0), 62.0),
                        ColorStop::percent(Color::BLACK.with_alpha(0.32 * alpha), 100.0),
                    ],
                )
                .into(),
            ]),
            Pickable::IGNORE,
        ));
        sheen_layer(b, radius, 0.06);
    });
}

/// Forge-horn corners (pre-sized textures, gem baked) on the four corners of the parent. The
/// panel corner sits 10 % inside each image, so the spurs overhang.
pub fn horn_corners(p: &mut ChildSpawnerCommands, kit: &UiKit, size: u32, bronze: bool) {
    let size = if bronze {
        40
    } else {
        [30u32, 40, 44, 60, 64, 76].into_iter().min_by_key(|s: &u32| s.abs_diff(size)).unwrap_or(44)
    };
    let s = size as f32;
    let o = -s * 0.1;
    for corner in Corner::ALL {
        let path = if bronze {
            format!("ornaments/forgehorn_bronze_40_{}@2x.png", corner.key())
        } else {
            format!("ornaments/forgehorn_{size}_{}@2x.png", corner.key())
        };
        let mut node = Node { position_type: PositionType::Absolute, width: px(s), height: px(s), ..default() };
        match corner {
            Corner::TopLeft => (node.left, node.top) = (px(o), px(o)),
            Corner::TopRight => (node.right, node.top) = (px(o), px(o)),
            Corner::BottomLeft => (node.left, node.bottom) = (px(o), px(o)),
            Corner::BottomRight => (node.right, node.bottom) = (px(o), px(o)),
        }
        p.spawn((node, kit.tex(&path), ZIndex(3), Pickable::IGNORE));
    }
}

/// The sun-crest centred on the parent's top edge, 62 % of it above the edge (§7.1).
pub fn sun_crest(p: &mut ChildSpawnerCommands, kit: &UiKit, height: u32) -> Entity {
    let (path, w, h) = if height <= 56 {
        ("ornaments/suncrest_50@2x.png", 130.0, 50.0)
    } else {
        ("ornaments/suncrest_62@2x.png", 161.0, 62.0)
    };
    p.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: percent(50.0),
            top: px(-0.62 * h),
            width: px(w),
            height: px(h),
            margin: UiRect::left(px(-w / 2.0)),
            ..default()
        },
        kit.tex(path),
        ZIndex(3),
        Pickable::IGNORE,
    ))
    .id()
}

/// Lacquer body with a rarity top wash under a 9-slice rarity rim (§8.1: sockets, bag cards,
/// end cards). Carries a [`KitCard`] whose `selected` flag shows the metal-gold selection ring.
pub fn gilt_card(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    rarity: Rarity,
    mut node: Node,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    node.border_radius = BorderRadius::all(px(8.0));
    let wash = rarity_color(rarity);
    let root = p.spawn((node, drop_shadow(0.7, 8.0, 12.0))).id();
    let mut ring = Entity::PLACEHOLDER;
    p.commands_mut().entity(root).with_children(|c| {
        // The selection ring sits 5 px outside the card, under everything else.
        ring = c
            .spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(-5.0),
                    top: px(-5.0),
                    right: px(-5.0),
                    bottom: px(-5.0),
                    display: Display::None,
                    border_radius: BorderRadius::all(px(13.0)),
                    ..default()
                },
                kit.tex("frames/card_selected@2x.png"),
                glow(tok::READY_GLOW.with_alpha(0.55), 14.0, 1.0),
                Pickable::IGNORE,
            ))
            .id();
        c.spawn((
            Node { border_radius: BorderRadius::all(px(8.0)), ..fill() },
            v_gradient(tok::LAC2.with_alpha(0.96), tok::LAC1.with_alpha(0.96)),
            Pickable::IGNORE,
        ))
        .with_children(|b| {
            b.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0.0),
                    right: px(0.0),
                    top: px(0.0),
                    height: percent(45.0),
                    border_radius: BorderRadius::top(px(8.0)),
                    ..default()
                },
                v_gradient(wash.with_alpha(0.09), wash.with_alpha(0.0)),
                Pickable::IGNORE,
            ));
        });
        content(c);
        c.spawn((
            fill(),
            kit.tex(&format!("frames/gilt_card_{}@2x.png", rarity_key(rarity))),
            ZIndex(2),
            Pickable::IGNORE,
        ));
    });
    p.commands_mut().entity(root).insert(KitCard { selected: false, ring });
    root
}

/// A hover tooltip card: light gilt frame over lacquer, radius 6 (§6.2).
pub fn tooltip(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    mut node: Node,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    node.border_radius = BorderRadius::all(px(6.0));
    p.spawn((node, drop_shadow(0.75, 6.0, 14.0)))
        .with_children(|c| {
            lacquer_body(c, BorderRadius::all(px(6.0)), 0.96);
            content(c);
            c.spawn((fill(), kit.tex("frames/tooltip@2x.png"), ZIndex(2), Pickable::IGNORE));
        })
        .id()
}

/// A quiet plate with a dashed `ichor` outline (the ONE PART AWAY recipe hint, §7.1).
pub fn dashed_plate(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    mut node: Node,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    node.border_radius = BorderRadius::all(px(6.0));
    p.spawn((node, v_gradient(tok::LAC2.with_alpha(0.7), tok::LAC1.with_alpha(0.7))))
        .with_children(|c| {
            content(c);
            c.spawn((fill(), kit.tex_tinted("frames/dashed_outline@2x.png", tok::ICHOR), ZIndex(2), Pickable::IGNORE));
        })
        .id()
}

// ───────────────────────────── ornaments ─────────────────────────────

/// The gem set in an ember-knot or on an ornament.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Gem {
    None,
    /// `#FFE7A6` chrome: banners, boss notches.
    Ivory,
    /// Amber chrome: horn bosses, crests.
    Amber,
    /// A tinted gem (a god colour on the boon title).
    Tint(Color),
}

fn gem_image(kit: &UiKit, gem: Gem) -> Option<ImageNode> {
    match gem {
        Gem::None => None,
        Gem::Ivory => Some(kit.tex("ornaments/gem_ivory@2x.png")),
        Gem::Amber => Some(kit.tex("ornaments/gem_amber@2x.png")),
        Gem::Tint(c) => Some(kit.tex_tinted("ornaments/gem_white@2x.png", c)),
    }
}

/// The ember-knot divider (§8): two tapering half-rules and the twin-curl knot, `width` wide and
/// 14 tall, with an optional centre gem. `alpha` fades it (the Forge's lower divider uses 0.8).
pub fn ember_knot(p: &mut ChildSpawnerCommands, kit: &UiKit, width: f32, gem: Gem, alpha: f32) -> Entity {
    let half = ((width - 56.0) / 2.0).max(16.0);
    let tint = Color::WHITE.with_alpha(alpha);
    p.spawn((Node { width: px(half * 2.0 + 56.0), height: px(14.0), flex_shrink: 0.0, ..row(0.0) }, Pickable::IGNORE))
        .with_children(|c| {
            let mut left = kit.tex_tinted("ornaments/emberknot_rule@2x.png", tint);
            left.flip_x = true;
            c.spawn((Node { width: px(half), height: px(14.0), ..default() }, left, Pickable::IGNORE));
            c.spawn((
                Node { width: px(56.0), height: px(14.0), ..default() },
                kit.tex_tinted("ornaments/emberknot_knot@2x.png", tint),
                Pickable::IGNORE,
            ))
            .with_children(|k| {
                if let Some(img) = gem_image(kit, gem) {
                    k.spawn((centered_at(28.0, 7.0, 10.0, 10.0), img, Pickable::IGNORE));
                }
            });
            c.spawn((
                Node { width: px(half), height: px(14.0), ..default() },
                kit.tex_tinted("ornaments/emberknot_rule@2x.png", tint),
                Pickable::IGNORE,
            ));
        })
        .id()
}

// ───────────────────────────── icons, gems, keys ─────────────────────────────

/// An icon by key (`<group>/<name>`, see `assets/ui/icons/icons.json`) at `size` logical px,
/// tinted by `tint` (white = as drawn). The image level follows UiScale.
pub fn icon(p: &mut ChildSpawnerCommands, key: &str, size: f32, tint: Color) -> Entity {
    p.spawn((
        Node { width: px(size), height: px(size), flex_shrink: 0.0, ..default() },
        UiIcon::new(key, size),
        ImageNode { color: tint, image_mode: NodeImageMode::Stretch, ..default() },
        Pickable::IGNORE,
    ))
    .id()
}

/// An icon bundle for custom nodes (put your own `Node` next to it).
pub fn icon_bundle(key: &str, size: f32, tint: Color) -> impl Bundle {
    (
        UiIcon::new(key, size),
        ImageNode { color: tint, image_mode: NodeImageMode::Stretch, ..default() },
        Pickable::IGNORE,
    )
}

/// A cut rarity gem of radius `r` (§8: round cabochon, lozenge, hex step-cut, star). The only
/// icons with baked colour.
pub fn rarity_gem(p: &mut ChildSpawnerCommands, rarity: Rarity, r: f32) -> Entity {
    // The gem glyph fills ~84 % of its icon cell.
    icon(p, &format!("rarity/gem_{}", rarity_key(rarity)), (2.0 * r / 0.84).round(), Color::WHITE)
}

/// An element cabochon: a round slot with the element icon (callouts, the chassis card).
pub fn element_cabochon(p: &mut ChildSpawnerCommands, kit: &UiKit, element: &str, size: f32) -> Entity {
    slot(
        p,
        kit,
        SlotSpec::new(SlotShape::Round, size).icon(&format!("elements/{element}")).icon_frac(0.7).shadow(false),
    )
}

/// A keyboard keycap (§8.2): the 9-sliced cap with its label 1.5 px above centre. Digits use
/// Alegreya Bold (Cinzel's `1` reads as `I`); letters and names use Cinzel small caps.
pub fn keycap(p: &mut ChildSpawnerCommands, kit: &UiKit, label: &str, height: f32) -> Entity {
    let digits = label.chars().all(|c| c.is_ascii_digit());
    let (ty, size) =
        if digits { (Ty::Num, (height * 0.62).round()) } else { (Ty::Micro, (height * 0.5).round().max(11.0)) };
    let pad = (height * 0.3).round();
    p.spawn((
        Node {
            height: px(height),
            min_width: px(height),
            padding: UiRect { left: px(pad), right: px(pad), bottom: px(3.0), ..default() },
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            flex_shrink: 0.0,
            ..default()
        },
        kit.tex("frames/keycap@2x.png"),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        let (font, _, line) = kit.fonts.style(ty, size);
        c.spawn((
            Text::new(label),
            font,
            gf_engine::client::LetterSpacing::Px(if digits { 0.0 } else { size * 0.06 }),
            line,
            TextColor(tok::PARCH),
            TextLayout::no_wrap(),
            Pickable::IGNORE,
        ));
    })
    .id()
}

/// What a key hint shows.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Key<'a> {
    /// A keyboard key: a keycap with this label.
    Text(&'a str),
    /// An input icon (`input/mouse_lmb`, `input/pad_south`…): mouse buttons and pad studs.
    Icon(&'a str),
}

/// A key hint: a keycap for keys, an icon for mouse buttons and pad studs (§7.6).
pub fn key_chip(p: &mut ChildSpawnerCommands, kit: &UiKit, key: Key, height: f32) -> Entity {
    match key {
        Key::Text(s) => keycap(p, kit, s, height),
        Key::Icon(k) => icon(p, k, height * 1.15, Color::WHITE),
    }
}

// ───────────────────────────── buttons, chips, pills ─────────────────────────────

/// Button look.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ButtonKind {
    /// Gold (EQUIP, FORGE AGAIN): `ink_text` label.
    Primary,
    /// Lacquer with a soft gold rim (SALVAGE, LEAVE): `parch` label.
    Secondary,
    /// The small chamfer-6 chip (REROLL, filters).
    Chip,
}

/// A 9-sliced button (§8.2) with a Cinzel label and room on the right for a sub-line, cost or
/// delta chip (`trailing`). Hover and press swap textures automatically; insert
/// `InteractionDisabled` to disable it. Activate with the global `On<Activate>` observer.
pub fn button(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    kind: ButtonKind,
    text: &str,
    width: f32,
    height: f32,
    trailing: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    button_impl(p, kit, kind, text, width, height, None, trailing)
}

fn button_impl(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    kind: ButtonKind,
    text: &str,
    width: f32,
    height: f32,
    leading_icon: Option<&str>,
    trailing: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    let (ty, size, color) = match kind {
        ButtonKind::Primary => (Ty::Label, (height * 0.4).clamp(13.0, 20.0), tok::INK_TEXT),
        ButtonKind::Secondary => (Ty::Label, (height * 0.4).clamp(13.0, 20.0), tok::PARCH),
        ButtonKind::Chip => (Ty::Micro, 11.0, tok::PARCH),
    };
    let tex = fx::button_texture(kind, false, false, false);
    let mut label = Entity::PLACEHOLDER;
    let root = p
        .spawn((
            Node {
                width: px(width),
                height: px(height),
                padding: UiRect::horizontal(px(if kind == ButtonKind::Chip { 8.0 } else { 16.0 })),
                justify_content: if kind == ButtonKind::Chip {
                    JustifyContent::Center
                } else {
                    JustifyContent::SpaceBetween
                },
                align_items: AlignItems::Center,
                column_gap: px(6.0),
                flex_shrink: 0.0,
                ..default()
            },
            UiButton,
            Hovered::default(),
            kit.tex(tex),
        ))
        .with_children(|c| {
            if let Some(k) = leading_icon {
                icon(c, k, 16.0, Color::WHITE);
            }
            let (font, _, line) = kit.fonts.style(ty, size);
            label = c
                .spawn((
                    Text::new(text.to_uppercase()),
                    font,
                    gf_engine::client::LetterSpacing::Px(size * 0.1),
                    line,
                    TextColor(color),
                    TextLayout::no_wrap(),
                    Pickable::IGNORE,
                ))
                .id();
            trailing(c);
        })
        .id();
    p.commands_mut().entity(root).insert(KitButton { kind, label });
    root
}

/// A chip: the small 26-tall chamfer-6 button with an optional leading icon (REROLL, filters).
pub fn chip(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    text: &str,
    leading_icon: Option<&str>,
    width: f32,
    trailing: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    button_impl(p, kit, ButtonKind::Chip, text, width, 26.0, leading_icon, trailing)
}

/// Pill look.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PillKind {
    /// Gold with `ink_text` (kind pills, REPLACE).
    Gold,
    /// Lacquer with a soft gold rim (bag filters).
    Outline,
}

/// An 18-tall pill with `Micro` 11 text and an optional leading icon.
pub fn pill(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    kind: PillKind,
    text: &str,
    leading_icon: Option<&str>,
) -> Entity {
    let (tex, color) = match kind {
        PillKind::Gold => ("frames/pill@2x.png", tok::INK_TEXT),
        PillKind::Outline => ("frames/pill_outline@2x.png", tok::PARCH_DIM),
    };
    p.spawn((
        Node {
            height: px(18.0),
            min_width: px(32.0),
            padding: UiRect::horizontal(px(9.0)),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            column_gap: px(4.0),
            flex_shrink: 0.0,
            ..default()
        },
        kit.tex(tex),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        if let Some(k) = leading_icon {
            icon(c, k, 13.0, if kind == PillKind::Gold { tok::INK_TEXT } else { Color::WHITE });
        }
        c.spawn(kit.text_flat(Ty::Micro, 11.0, text.to_uppercase(), color));
    })
    .id()
}

/// The 22-tall rarity ribbon: gilt (bronze for Common) with the cut gem and the rarity word in
/// its colour (§7.2).
pub fn ribbon(p: &mut ChildSpawnerCommands, kit: &UiKit, rarity: Rarity) -> Entity {
    let tex = if rarity == Rarity::Common { "frames/ribbon_bronze@2x.png" } else { "frames/ribbon_gilt@2x.png" };
    p.spawn((
        Node {
            height: px(22.0),
            min_width: px(32.0),
            padding: UiRect::horizontal(px(10.0)),
            align_items: AlignItems::Center,
            column_gap: px(5.0),
            flex_shrink: 0.0,
            ..default()
        },
        kit.tex(tex),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        if rarity != Rarity::Common {
            rarity_gem(c, rarity, 5.0);
        }
        let (font, _, line) = kit.fonts.style(Ty::Micro, 11.0);
        c.spawn((
            Text::new(rarity_key(rarity).to_uppercase()),
            font,
            gf_engine::client::LetterSpacing::Px(2.4),
            line,
            TextColor(rarity_color(rarity)),
            Pickable::IGNORE,
        ));
    })
    .id()
}

/// The P chip under an ally medallion: `P2`…`P4` in the player colour on the lozenge plaque.
pub fn pchip(p: &mut ChildSpawnerCommands, kit: &UiKit, slot: usize, color: Color) -> Entity {
    p.spawn((
        Node {
            width: px(30.0),
            height: px(18.0),
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            flex_shrink: 0.0,
            ..default()
        },
        kit.tex("frames/pchip@2x.png"),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        c.spawn(kit.text_flat(Ty::Micro, 11.0, format!("P{}", slot + 1), color));
    })
    .id()
}

/// A delta chip (§2): a gain is `ichor` with an up-chevron, a loss is `loss` with a
/// down-chevron, no change is `parch_mute ±0%`. Never green or red.
pub fn delta_chip(p: &mut ChildSpawnerCommands, kit: &UiKit, pct: f32, size: f32) -> Entity {
    delta_chip_in(p, kit, pct, size, None)
}

/// A delta chip in one colour (`ink_text` inside a primary button, §7.1).
pub fn delta_chip_in(p: &mut ChildSpawnerCommands, kit: &UiKit, pct: f32, size: f32, color: Option<Color>) -> Entity {
    let rounded = pct.round();
    let (key, hue, s) = if rounded > 0.0 {
        (Some("ui/delta_up"), tok::ICHOR, format!("{rounded:.0}%"))
    } else if rounded < 0.0 {
        (Some("ui/delta_down"), tok::LOSS, format!("{:.0}%", -rounded))
    } else {
        (None, tok::PARCH_MUTE, "±0%".to_string())
    };
    let color = color.unwrap_or(hue);
    p.spawn((row(2.0), Pickable::IGNORE))
        .with_children(|c| {
            if let Some(k) = key {
                icon(c, k, (size * 0.78).round(), color);
            }
            if color == hue {
                c.spawn(kit.text_px(Ty::Strong, size, s, color));
            } else {
                c.spawn(kit.text_flat(Ty::Strong, size, s, color));
            }
        })
        .id()
}

// ───────────────────────────── slots ─────────────────────────────

/// Slot shape = category (§0): the shape carries meaning without words or colour.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum SlotShape {
    /// Core parts, buffs, element cabochons, touch buttons.
    Round,
    /// Mechanism parts.
    Octagon,
    /// Relic parts.
    Arch,
    /// Sigil parts.
    Lozenge,
    /// Abilities Q / E (chamfer 12 at 60).
    Chamfer,
    /// Team Overdrive V.
    HexPointy,
    /// The chassis.
    HexFlat,
}

impl SlotShape {
    pub const ALL: [SlotShape; 7] = [
        SlotShape::Round,
        SlotShape::Octagon,
        SlotShape::Arch,
        SlotShape::Lozenge,
        SlotShape::Chamfer,
        SlotShape::HexPointy,
        SlotShape::HexFlat,
    ];

    pub fn key(self) -> &'static str {
        match self {
            SlotShape::Round => "round",
            SlotShape::Octagon => "octagon",
            SlotShape::Arch => "arch",
            SlotShape::Lozenge => "lozenge",
            SlotShape::Chamfer => "chamfer",
            SlotShape::HexPointy => "hex_pointy",
            SlotShape::HexFlat => "hex_flat",
        }
    }

    /// The shape of a weapon part slot.
    pub fn for_part(slot: gf_core::forge::Slot) -> Self {
        use gf_core::forge::Slot;
        match slot {
            Slot::Core => SlotShape::Round,
            Slot::Mechanism => SlotShape::Octagon,
            Slot::Relic => SlotShape::Arch,
            Slot::Sigil => SlotShape::Lozenge,
        }
    }

    /// Radius of the cooldown-sweep child (§8.1 radius rule), as a fraction of the slot size.
    fn sweep_radius(self, size: f32) -> BorderRadius {
        match self {
            // chamfer c = 0.2 × size; r = 1.71 c.
            SlotShape::Chamfer => BorderRadius::all(px(1.71 * 0.2 * size)),
            _ => BorderRadius::MAX,
        }
    }

    /// Inset of the sweep inside the rim, as a fraction of the size.
    fn sweep_inset(self) -> f32 {
        match self {
            SlotShape::Round | SlotShape::Chamfer | SlotShape::Octagon => 0.045,
            SlotShape::Arch | SlotShape::HexFlat => 0.12,
            SlotShape::Lozenge | SlotShape::HexPointy => 0.2,
        }
    }
}

/// What a [`slot`] shows.
#[derive(Clone, Debug)]
pub struct SlotSpec {
    pub shape: SlotShape,
    pub size: f32,
    pub icon: Option<String>,
    /// Icon size as a fraction of the slot (0.74 for kit icons, §6.1).
    pub icon_frac: f32,
    pub icon_tint: Color,
    /// A keycap straddling the bottom edge.
    pub key: Option<String>,
    /// Ready halo and sheen (ability slots).
    pub ready_glow: bool,
    /// Slot drop shadow.
    pub shadow: bool,
    /// The empty-slot ghost glyph at 35 % when there is no icon.
    pub ghost: Option<String>,
}

impl SlotSpec {
    pub fn new(shape: SlotShape, size: f32) -> Self {
        Self {
            shape,
            size,
            icon: None,
            icon_frac: 0.7,
            icon_tint: Color::WHITE,
            key: None,
            ready_glow: false,
            shadow: true,
            ghost: None,
        }
    }

    /// A Q / E ability slot: chamfered, the kit icon at 74 %, ready glow.
    pub fn ability(icon: &str, size: f32) -> Self {
        Self { icon: Some(icon.to_string()), icon_frac: 0.74, ready_glow: true, ..Self::new(SlotShape::Chamfer, size) }
    }

    pub fn icon(mut self, key: &str) -> Self {
        self.icon = Some(key.to_string());
        self
    }

    pub fn icon_frac(mut self, f: f32) -> Self {
        self.icon_frac = f;
        self
    }

    pub fn tint(mut self, c: Color) -> Self {
        self.icon_tint = c;
        self
    }

    pub fn key(mut self, k: &str) -> Self {
        self.key = Some(k.to_string());
        self
    }

    pub fn glow(mut self, on: bool) -> Self {
        self.ready_glow = on;
        self
    }

    pub fn shadow(mut self, on: bool) -> Self {
        self.shadow = on;
        self
    }

    /// An empty slot showing this ghost glyph (`slots/core`…) at 35 %.
    pub fn ghost(mut self, key: &str) -> Self {
        self.ghost = Some(key.to_string());
        self
    }
}

/// A shaped slot (§8.1): fill, icon, cooldown sweep and edge, ready glow and sheen, rim, the
/// seconds numeral, the ready flash and ring burst, and an optional keycap. Drive it with
/// [`SlotState`]; the kit handles the cooldown language of §6.1a.
pub fn slot(p: &mut ChildSpawnerCommands, kit: &UiKit, spec: SlotSpec) -> Entity {
    let s = spec.size;
    let shape = spec.shape.key();
    let mut parts = SlotParts { size: s, ..default() };
    let root = p
        .spawn((
            Node { width: px(s), height: px(s), flex_shrink: 0.0, ..default() },
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            if spec.ready_glow {
                parts.glow = c
                    .spawn((
                        centered(s * 1.5, s * 1.5),
                        kit.tex_tinted(&format!("slots/slot_{shape}_glow@2x.png"), tok::READY_GLOW.with_alpha(0.0)),
                        Pickable::IGNORE,
                    ))
                    .id();
            }
            let mut fill_node =
                c.spawn((fill(), kit.tex(&format!("slots/slot_{shape}_fill@2x.png")), Pickable::IGNORE));
            // A soft contact shadow under the slot where a rounded box matches the shape.
            if spec.shadow && matches!(spec.shape, SlotShape::Round | SlotShape::Chamfer | SlotShape::Octagon) {
                fill_node.insert((
                    Node { border_radius: spec.shape.sweep_radius(s), ..fill() },
                    drop_shadow(0.75, 2.5, 5.0),
                ));
            }
            let isz = (s * spec.icon_frac).round();
            if let Some(key) = spec.icon.as_deref() {
                parts.icon = c
                    .spawn((
                        centered(isz, isz),
                        UiIcon::new(key, isz),
                        ImageNode { color: spec.icon_tint, image_mode: NodeImageMode::Stretch, ..default() },
                        Pickable::IGNORE,
                    ))
                    .id();
            } else if let Some(key) = spec.ghost.as_deref() {
                c.spawn((
                    centered(isz, isz),
                    UiIcon::new(key, isz),
                    ImageNode { color: tok::BONE.with_alpha(0.35), image_mode: NodeImageMode::Stretch, ..default() },
                    Pickable::IGNORE,
                ));
            }
            let ins = (s * spec.shape.sweep_inset()).round();
            parts.sweep = c
                .spawn((
                    Node {
                        border_radius: spec.shape.sweep_radius(s - 2.0 * ins),
                        display: Display::None,
                        ..inset(ins)
                    },
                    BackgroundGradient::default(),
                    Pickable::IGNORE,
                ))
                .with_children(|sw| {
                    parts.edge = sw
                        .spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: percent(50.0),
                                top: px(0.0),
                                width: px(1.4),
                                height: percent(100.0),
                                margin: UiRect::left(px(-0.7)),
                                ..default()
                            },
                            BackgroundGradient(vec![
                                LinearGradient::to_bottom(vec![
                                    ColorStop::percent(tok::GOLD_LT, 0.0),
                                    ColorStop::percent(tok::GOLD_LT.with_alpha(0.6), 48.0),
                                    ColorStop::percent(Color::NONE, 50.0),
                                ])
                                .into(),
                            ]),
                            UiTransform::default(),
                            fx::SlotChild,
                            Pickable::IGNORE,
                        ))
                        .id();
                })
                .id();
            if spec.ready_glow {
                parts.sheen =
                    c.spawn((fill(), kit.tex(&format!("slots/slot_{shape}_sheen@2x.png")), Pickable::IGNORE)).id();
            }
            parts.flash = c
                .spawn((
                    fill(),
                    kit.tex_tinted(&format!("slots/slot_{shape}_mask@2x.png"), hx(0xFFF3C8).with_alpha(0.0)),
                    Pickable::IGNORE,
                ))
                .id();
            parts.rim = c.spawn((fill(), kit.tex(&format!("slots/slot_{shape}_rim@2x.png")), Pickable::IGNORE)).id();
            parts.burst = c
                .spawn((
                    fill(),
                    kit.tex_tinted(&format!("slots/slot_{shape}_rim@2x.png"), tok::GOLD_HI.with_alpha(0.0)),
                    UiTransform::default(),
                    fx::SlotChild,
                    Pickable::IGNORE,
                ))
                .id();
            let secs_px = (0.36 * s).round().clamp(12.0, 40.0);
            parts.secs = c
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(0.0),
                        right: px(0.0),
                        top: px(0.0),
                        bottom: px(0.0),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        display: Display::None,
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|t| {
                    let (font, spacing, line) = kit.fonts.style(Ty::NumM, secs_px);
                    t.spawn((
                        Text::new(""),
                        font,
                        spacing,
                        line,
                        TextColor(tok::NUMERAL),
                        TextShadow { offset: Vec2::new(0.0, 1.5), color: tok::INK.with_alpha(0.95) },
                        TextLayout::no_wrap(),
                        Pickable::IGNORE,
                    ));
                })
                .id();
            if let Some(k) = spec.key.as_deref() {
                let kh = (s / 3.0).clamp(18.0, 22.0).round();
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(-20.0),
                        right: px(-20.0),
                        bottom: px(-kh / 2.0 - 1.0),
                        justify_content: JustifyContent::Center,
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|kc| {
                    keycap(kc, kit, k, kh);
                });
            }
        })
        .id();
    p.commands_mut().entity(root).insert((parts, SlotState::READY, fx::SlotAnim::default()));
    root
}

// ───────────────────────────── medallions and rings ─────────────────────────────

/// What a [`medallion`] holds.
#[derive(Clone, Debug)]
pub struct MedallionSpec {
    /// Ø: 34 (pins, badges), 46 (party), 60 (boon chip), 68 (end cards), 100 (boon apex), 116
    /// (end crest, studded).
    pub size: f32,
    /// A bust from `portraits/`, or any icon, filling the window.
    pub portrait: Option<String>,
    /// The player-colour enamel band (2.6 px) inside the rim.
    pub band: Option<Color>,
    /// God-colour enamel behind the glyph (boon chip, apex, badges).
    pub enamel: Option<Color>,
    /// A glyph over the enamel (a god sigil, a boon icon) at this fraction of the size.
    pub glyph: Option<(String, f32, Color)>,
}

impl MedallionSpec {
    pub fn new(size: f32) -> Self {
        Self { size, portrait: None, band: None, enamel: None, glyph: None }
    }

    pub fn portrait(mut self, key: &str) -> Self {
        self.portrait = Some(key.to_string());
        self
    }

    pub fn band(mut self, c: Color) -> Self {
        self.band = Some(c);
        self
    }

    pub fn enamel(mut self, c: Color) -> Self {
        self.enamel = Some(c);
        self
    }

    pub fn glyph(mut self, key: &str, frac: f32, tint: Color) -> Self {
        self.glyph = Some((key.to_string(), frac, tint));
        self
    }
}

/// A gilt medallion (§6.4, §6.13, §7.2, §7.3): rim, optional player band, lacquer window with
/// a bust, or god enamel with a glyph.
pub fn medallion(p: &mut ChildSpawnerCommands, kit: &UiKit, spec: MedallionSpec) -> Entity {
    let s = spec.size;
    let (rim, rim_w) = match s.round() as u32 {
        34 => ("slots/medallion_rim_34@2x.png", 2.0),
        46 => ("slots/medallion_rim_46@2x.png", 2.2),
        60 => ("slots/medallion_rim_60@2x.png", 2.6),
        68 => ("slots/medallion_rim_68@2x.png", 2.8),
        100 => ("slots/medallion_rim_100@2x.png", 5.0),
        116 => ("slots/medallion_rim_116_studded@2x.png", 4.5),
        _ => ("slots/medallion_rim@2x.png", s * 3.0 / 64.0),
    };
    p.spawn((
        Node { width: px(s), height: px(s), border_radius: BorderRadius::MAX, flex_shrink: 0.0, ..default() },
        glow(Color::BLACK.with_alpha(0.55), 6.0, 0.0),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        let mut d = rim_w * 0.7;
        if let Some(band) = spec.band {
            c.spawn((Node { border_radius: BorderRadius::MAX, ..inset(d) }, BackgroundColor(band), Pickable::IGNORE));
            d += 2.6;
            c.spawn((
                Node { border_radius: BorderRadius::MAX, ..inset(d) },
                BackgroundColor(hx(0x140B06)),
                Pickable::IGNORE,
            ));
            d += 0.9;
        }
        let window = s - 2.0 * d;
        if let Some(enamel) = spec.enamel {
            c.spawn((inset(d), kit.tex_tinted("slots/enamel_disc@2x.png", enamel), Pickable::IGNORE));
        } else {
            c.spawn((
                Node { border_radius: BorderRadius::MAX, ..inset(d) },
                BackgroundGradient(vec![
                    RadialGradient::new(
                        UiPosition::CENTER.at_percent(0.0, -12.0),
                        RadialGradientShape::FarthestSide,
                        vec![ColorStop::auto(hx(0x3A291C)), ColorStop::auto(hx(0x0D0806))],
                    )
                    .into(),
                ]),
                Pickable::IGNORE,
            ));
        }
        if let Some(key) = spec.portrait.as_deref() {
            c.spawn((centered(window, window), icon_bundle(key, window, Color::WHITE)));
        }
        if let Some((key, frac, tint)) = spec.glyph.as_ref() {
            let g = (s * frac).round();
            c.spawn((centered(g, g), icon_bundle(key, g, *tint)));
        }
        c.spawn((fill(), kit.tex(rim), Pickable::IGNORE));
    })
    .id()
}

/// A ring meter (§11.4): a border ring whose conic gradient pours clockwise from 12 o'clock.
/// Drive it with [`KitRing`]. `thickness` is the ring width; the centre stays clear. Molten rings
/// carry the 1.6 px `#FFFBEA` meniscus at the pour front. `node` must set a px width.
pub fn ring_meter(p: &mut ChildSpawnerCommands, node: Node, thickness: f32, style: RingStyle, value: f32) -> Entity {
    let outer = match node.width {
        Val::Px(w) => w,
        _ => 0.0,
    };
    let mut meniscus = None;
    let root = p
        .spawn((
            Node { border: UiRect::all(px(thickness)), border_radius: BorderRadius::MAX, ..node },
            BorderGradient::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            if style == RingStyle::Molten && outer > 0.0 {
                // Spans the whole diameter through the centre (so it rotates about it) and is lit
                // only across the ring's width at the top.
                meniscus = Some(
                    c.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: percent(50.0),
                            top: px(-thickness),
                            width: px(1.8),
                            height: px(outer),
                            margin: UiRect::left(px(-0.9)),
                            display: Display::None,
                            ..default()
                        },
                        BackgroundGradient(vec![
                            LinearGradient::to_bottom(vec![
                                ColorStop::px(tok::MOLTEN[0], 0.0),
                                ColorStop::px(tok::MOLTEN[0], thickness),
                                ColorStop::px(Color::NONE, thickness),
                            ])
                            .into(),
                        ]),
                        UiTransform::default(),
                        ZIndex(1),
                        Pickable::IGNORE,
                    ))
                    .id(),
                );
            }
        })
        .id();
    p.commands_mut().entity(root).insert((KitRing { value, style, ready: false }, fx::RingAnim::new(meniscus)));
    root
}

/// Parts of the Hearth medallion.
#[derive(Component, Clone, Copy, Debug)]
pub struct HearthParts {
    /// The ult trough ring: set its [`KitRing`] value (and `ready`).
    pub ult: Entity,
    /// The outer ready glow (breathes while the ult is ready).
    pub glow: Entity,
}

/// The Hearth medallion (§6.1), Ø128: the portrait bust and the ultimate in one. Ult trough ring
/// (molten, clockwise from 12), the player band, the window, the studded bezel, and the R keycap.
pub fn hearth_medallion(p: &mut ChildSpawnerCommands, kit: &UiKit, portrait: &str, band: Color, key: &str) -> Entity {
    let s = 128.0;
    let mut parts = HearthParts { ult: Entity::PLACEHOLDER, glow: Entity::PLACEHOLDER };
    let root = p
        .spawn((Node { width: px(s), height: px(s), flex_shrink: 0.0, ..default() }, Pickable::IGNORE))
        .with_children(|c| {
            parts.glow = c
                .spawn((
                    Node { border_radius: BorderRadius::MAX, ..inset(4.0) },
                    glow(hx(0xFFB23A).with_alpha(0.0), 14.0, 3.0),
                    Pulse::shadow(1.0 / 1.6, 0.45, 0.85).off(),
                    Pickable::IGNORE,
                ))
                .id();
            // Trough r 54.5–59.5 → a 5 px ring of Ø119.
            c.spawn((
                Node { border_radius: BorderRadius::MAX, ..inset(64.0 - 59.5) },
                BackgroundColor(hx(0x140C08)),
                Pickable::IGNORE,
            ));
            parts.ult = ring_meter(c, centered(119.0, 119.0), 5.0, RingStyle::Molten, 0.0);
            // Band r 49.7..52.7, separator, window Ø98.
            c.spawn((
                Node { border_radius: BorderRadius::MAX, ..inset(64.0 - 52.7) },
                BackgroundColor(band),
                Pickable::IGNORE,
            ));
            c.spawn((
                Node { border_radius: BorderRadius::MAX, ..inset(64.0 - 50.1) },
                BackgroundColor(hx(0x140B06)),
                Pickable::IGNORE,
            ));
            c.spawn((centered(98.0, 98.0), icon_bundle(portrait, 98.0, Color::WHITE)));
            c.spawn((fill(), kit.tex("slots/medallion_hearth@2x.png"), Pickable::IGNORE));
            c.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0.0),
                    right: px(0.0),
                    bottom: px(-11.5),
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|k| {
                keycap(k, kit, key, 21.0);
            });
        })
        .id();
    p.commands_mut().entity(root).insert(parts);
    root
}

/// The Team Overdrive hex (§6.1): molten metal fills it bottom-up under a wavy meniscus
/// ([`MoltenMaterial`]); the emblem is stamped dark while charging and lights gold when ready.
/// Drive it with [`MoltenFill`].
pub fn overdrive_hex(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    materials: &mut Assets<MoltenMaterial>,
    decode: &mut UiDecode,
    size: f32,
    key: &str,
) -> Entity {
    let mask = kit.tex_handle("slots/slot_hex_pointy_mask@2x.png");
    decode.request(&mask);
    let material = materials.add(MoltenMaterial { p: Vec4::new(0.0, 0.0, 0.0, 0.0), mask });
    let mut emblem = Entity::PLACEHOLDER;
    let mut glow_e = Entity::PLACEHOLDER;
    let root = p
        .spawn((
            Node { width: px(size), height: px(size), flex_shrink: 0.0, ..default() },
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            glow_e = c
                .spawn((
                    centered(size * 1.5, size * 1.5),
                    kit.tex_tinted("slots/slot_hex_pointy_glow@2x.png", hx(0xFFC940).with_alpha(0.0)),
                    Pickable::IGNORE,
                ))
                .id();
            c.spawn((fill(), gf_engine::client::MaterialNode(material.clone()), Pickable::IGNORE));
            let e = (size * 0.56).round();
            emblem = c.spawn((centered(e, e), icon_bundle("team/overdrive", e, hx(0x2A1608)))).id();
            c.spawn((fill(), kit.tex("slots/slot_hex_pointy_rim@2x.png"), Pickable::IGNORE));
            c.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(-20.0),
                    right: px(-20.0),
                    bottom: px(-11.0),
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|k| {
                keycap(k, kit, key, 20.0);
            });
        })
        .id();
    p.commands_mut().entity(root).insert(MoltenFill {
        value: 0.0,
        ready: false,
        active: false,
        material,
        emblem,
        glow: glow_e,
        shown: 0.0,
    });
    root
}

// ───────────────────────────── bars and meters ─────────────────────────────

/// Bar fill material.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum BarFill {
    /// The player HP crimson with its pale-amber ghost.
    Hp,
    /// Boss and Warlord.
    Boss,
    /// Elite world bars.
    Elite,
    /// Molten: event bars, heat.
    Molten,
    /// Surge countdown.
    Surge,
    /// White fill tinted (player colour for share bars, gold for reforge).
    Tint(Color),
}

impl BarFill {
    fn textures(self) -> (&'static str, &'static str, Color) {
        match self {
            BarFill::Hp => ("bars/fill_hp@2x.png", "bars/fill_ghost_hp@2x.png", Color::WHITE),
            BarFill::Boss => ("bars/fill_boss@2x.png", "bars/fill_ghost_boss@2x.png", Color::WHITE),
            BarFill::Elite => ("bars/fill_elite@2x.png", "bars/fill_ghost_hp@2x.png", Color::WHITE),
            BarFill::Molten => ("bars/fill_molten@2x.png", "bars/fill_ghost_hp@2x.png", Color::WHITE),
            BarFill::Surge => ("bars/fill_surge@2x.png", "bars/fill_ghost_hp@2x.png", Color::WHITE),
            BarFill::Tint(c) => ("bars/fill_white@2x.png", "bars/fill_ghost_hp@2x.png", c),
        }
    }
}

/// A [`bar`]'s look.
#[derive(Clone, Copy, Debug)]
pub struct BarSpec {
    pub w: f32,
    pub h: f32,
    pub fill: BarFill,
    /// A drain ghost (§10: holds 0.35 s, eases 0.45 s).
    pub ghost: bool,
    /// The diagonal ward hatch from the fill end to fill + ward.
    pub ward: bool,
    /// The gilt rim (thin under 11 px). Off for world bars.
    pub rim: bool,
    /// Tick notches at k / n (armour steps, boss phases: see `notches`).
    pub segments: u32,
    /// The leaf finial on the right end (the Hearth HP bar).
    pub finial: bool,
    /// The bright leading edge.
    pub edge: bool,
    /// Iron-horn finials at both ends (boss and Warlord bar, §6.7).
    pub horns: bool,
}

impl BarSpec {
    pub fn new(w: f32, h: f32, fill: BarFill) -> Self {
        Self { w, h, fill, ghost: true, ward: false, rim: true, segments: 0, finial: false, edge: true, horns: false }
    }

    pub fn ward(mut self) -> Self {
        self.ward = true;
        self
    }

    pub fn no_rim(mut self) -> Self {
        self.rim = false;
        self
    }

    pub fn segments(mut self, n: u32) -> Self {
        self.segments = n;
        self
    }

    pub fn finial(mut self) -> Self {
        self.finial = true;
        self
    }

    pub fn horns(mut self) -> Self {
        self.horns = true;
        self
    }
}

/// A bar (§8.1, §10): trough, ghost, fill, ward hatch, leading edge, notches and rim. Drive it
/// with [`KitBar`] (`value`, `ward` in 0..1); the ghost and heal motion are automatic.
pub fn bar(p: &mut ChildSpawnerCommands, kit: &UiKit, spec: BarSpec) -> Entity {
    let thin = spec.h < 11.0;
    let (fill_tex, ghost_tex, tint) = spec.fill.textures();
    let radius = if thin { (spec.h / 2.0).min(3.0) } else { 4.0 };
    let pad = if spec.rim { if thin { 1.0 } else { 2.0 } } else { 0.0 };
    let mut parts = BarParts::default();
    let root = p
        .spawn((Node { width: px(spec.w), height: px(spec.h), flex_shrink: 0.0, ..default() }, Pickable::IGNORE))
        .with_children(|c| {
            if spec.rim {
                c.spawn((
                    fill(),
                    kit.tex(if thin { "bars/trough_thin@2x.png" } else { "bars/trough@2x.png" }),
                    Pickable::IGNORE,
                ));
            } else {
                c.spawn((
                    Node { border_radius: BorderRadius::all(px(radius)), ..fill() },
                    BackgroundColor(hx(0x0B0706).with_alpha(0.85)),
                    Pickable::IGNORE,
                ));
            }
            c.spawn((
                Node {
                    overflow: Overflow::clip(),
                    border_radius: BorderRadius::all(px((radius - pad).max(1.0))),
                    ..inset(pad)
                },
                Pickable::IGNORE,
            ))
            .with_children(|b| {
                let layer = |w: f32| Node {
                    position_type: PositionType::Absolute,
                    left: px(0.0),
                    top: px(0.0),
                    bottom: px(0.0),
                    width: percent(w * 100.0),
                    ..default()
                };
                if spec.ghost {
                    parts.ghost = b.spawn((layer(1.0), kit.tex(ghost_tex), Pickable::IGNORE)).id();
                }
                parts.fill = b.spawn((layer(1.0), kit.tex_tinted(fill_tex, tint), Pickable::IGNORE)).id();
                if spec.ward {
                    parts.ward = b
                        .spawn((
                            Node { display: Display::None, ..layer(0.0) },
                            kit.tex_tinted("fx/hatch_ward@2x.png", tok::WARD.with_alpha(0.9)),
                            Pickable::IGNORE,
                        ))
                        .id();
                }
                if spec.edge {
                    parts.edge = b
                        .spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: percent(100.0),
                                top: px(0.0),
                                bottom: px(0.0),
                                width: px(3.0),
                                margin: UiRect::left(px(-2.4)),
                                ..default()
                            },
                            kit.tex("bars/meniscus@2x.png"),
                            Pickable::IGNORE,
                        ))
                        .id();
                }
                for k in 1..spec.segments {
                    b.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: percent(k as f32 / spec.segments as f32 * 100.0),
                            top: px(0.0),
                            bottom: px(0.0),
                            width: px(1.5),
                            margin: UiRect::left(px(-0.75)),
                            ..default()
                        },
                        BackgroundColor(hx(0x140C08).with_alpha(0.85)),
                        Pickable::IGNORE,
                    ));
                }
            });
            if spec.rim {
                c.spawn((
                    fill(),
                    kit.tex(if thin { "bars/rim_thin@2x.png" } else { "bars/rim@2x.png" }),
                    ZIndex(2),
                    Pickable::IGNORE,
                ));
            }
            if spec.finial {
                c.spawn((
                    abs(spec.w - 5.0, spec.h / 2.0 - 11.0, 22.0, 22.0),
                    kit.tex("ornaments/finial_leaf@2x.png"),
                    ZIndex(3),
                    Pickable::IGNORE,
                ));
            }
            if spec.horns {
                // The collar (x 26–34 of the horn) clasps the bar end.
                let y = spec.h / 2.0 - 15.0;
                c.spawn((
                    abs(-28.0, y, 34.0, 30.0),
                    kit.tex("ornaments/boss_horn@2x.png"),
                    ZIndex(3),
                    Pickable::IGNORE,
                ));
                let mut right = kit.tex("ornaments/boss_horn@2x.png");
                right.flip_x = true;
                c.spawn((abs(spec.w - 6.0, y, 34.0, 30.0), right, ZIndex(3), Pickable::IGNORE));
            }
        })
        .id();
    p.commands_mut().entity(root).insert((parts, KitBar { value: 1.0, ward: 0.0 }, fx::BarAnim::new(1.0)));
    root
}

/// Phase notch gems on a boss bar's top edge at each threshold (`bosses.ron phases[i].below`).
pub fn notches(p: &mut ChildSpawnerCommands, kit: &UiKit, bar_w: f32, thresholds: &[f32]) {
    for t in thresholds {
        p.spawn((
            centered_at(bar_w * t.clamp(0.0, 1.0), 0.0, 10.0, 10.0),
            kit.tex("ornaments/gem_ivory@2x.png"),
            ZIndex(4),
            Pickable::IGNORE,
        ));
    }
}

/// Armour plates (§6.1): `n` steel parallelograms over `w` px with 3 px gaps; drive with
/// [`KitPlates`] (`value` in plates, partial plates fill from the left).
pub fn plates(p: &mut ChildSpawnerCommands, kit: &UiKit, w: f32, n: u32) -> Entity {
    let n = n.max(1);
    let pw = (w - 3.0 * (n - 1) as f32) / n as f32;
    let mut full = Vec::with_capacity(n as usize);
    let root = p
        .spawn((
            Node { width: px(w), height: px(9.0), column_gap: px(3.0), flex_shrink: 0.0, ..default() },
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            for _ in 0..n {
                c.spawn((
                    Node { width: px(pw), height: px(9.0), flex_shrink: 0.0, ..default() },
                    kit.tex("slots/armor_plate_empty@2x.png"),
                    Pickable::IGNORE,
                ))
                .with_children(|pl| {
                    full.push(
                        pl.spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: px(0.0),
                                top: px(0.0),
                                bottom: px(0.0),
                                width: percent(100.0),
                                overflow: Overflow::clip(),
                                ..default()
                            },
                            Pickable::IGNORE,
                        ))
                        .with_children(|clip| {
                            clip.spawn((
                                Node { width: px(pw), height: px(9.0), ..default() },
                                kit.tex("slots/armor_plate_full@2x.png"),
                                Pickable::IGNORE,
                            ));
                        })
                        .id(),
                    );
                });
            }
        })
        .id();
    p.commands_mut().entity(root).insert(KitPlates { value: n as f32, clips: full, shown: -1.0 });
    root
}

/// Dash charges (§6.1): cut lozenges 26 px apart; drive with [`KitPips`] (`full` charges, and the
/// `refill` fraction of the next one, drawn as a bottom-up reveal).
pub fn dash_pips(p: &mut ChildSpawnerCommands, kit: &UiKit, n: u32) -> Entity {
    let mut clips = Vec::new();
    let mut pips = Vec::new();
    let root = p
        .spawn((row(8.0), Pickable::IGNORE))
        .with_children(|c| {
            for _ in 0..n {
                let pip = c
                    .spawn((
                        Node { width: px(18.0), height: px(18.0), flex_shrink: 0.0, ..default() },
                        kit.tex("slots/dash_empty@2x.png"),
                        UiTransform::default(),
                        Pickable::IGNORE,
                    ))
                    .with_children(|d| {
                        clips.push(
                            d.spawn((
                                Node {
                                    position_type: PositionType::Absolute,
                                    left: px(0.0),
                                    right: px(0.0),
                                    bottom: px(0.0),
                                    height: percent(100.0),
                                    overflow: Overflow::clip(),
                                    flex_direction: FlexDirection::ColumnReverse,
                                    ..default()
                                },
                                Pickable::IGNORE,
                            ))
                            .with_children(|clip| {
                                clip.spawn((
                                    Node { width: px(18.0), height: px(18.0), flex_shrink: 0.0, ..default() },
                                    kit.tex("slots/dash_full@2x.png"),
                                    Pickable::IGNORE,
                                ));
                            })
                            .id(),
                        );
                    })
                    .id();
                pips.push(pip);
            }
        })
        .id();
    p.commands_mut().entity(root).insert(KitPips { full: n, refill: 0.0, clips, pips, shown: (u32::MAX, -1.0) });
    root
}

// ───────────────────────────── boon niche card ─────────────────────────────

/// A boon card's gods and rarity (§7.2).
#[derive(Clone, Debug)]
pub struct NicheSpec {
    pub rarity: Rarity,
    /// (god key, colour for enamel and hairline). A second entry makes it a Duo card.
    pub gods: Vec<(String, Color)>,
    /// The boon icon in the apex medallion (`boons/<key>`).
    pub icon: String,
    /// A sun-crest over the medallion (Legendary boons).
    pub crest: bool,
}

/// Parts of a niche card.
#[derive(Component, Clone, Copy, Debug)]
pub struct NicheParts {
    /// The apex medallion (flares on reveal).
    pub medallion: Entity,
}

/// The card size (fixed-size textures, §8.1).
pub const NICHE: Vec2 = Vec2::new(300.0, 420.0);

/// The shrine-niche boon card shell (§7.2): god-tinted lacquer body, arch glow and enamel
/// hairline, the rarity frame with foot horns, springer gems, the apex medallion with the boon
/// icon and the god badges. Hovering lifts it 12 px with a god-colour aura. Put the text in
/// `content` using card-local coordinates (`abs`), e.g. the god line at baseline 146.
pub fn niche_card(
    p: &mut ChildSpawnerCommands,
    kit: &UiKit,
    spec: &NicheSpec,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    let god1 = spec.gods.first().map_or(tok::GOLD_LT, |g| g.1);
    let god2 = spec.gods.get(1).map(|g| g.1);
    // The greyscale body (59 → 7 grey, top to foot) is tinted toward the god colour, held back
    // toward a warm grey so the lacquer stays dark and never saturates (§7.2: the god colour
    // mixed 80 % toward #140E0B at the top, #090605 at the foot).
    let body_tint = crate::palette::mix(god1, hx(0x8C8272), 0.55);
    let mut medallion_e = Entity::PLACEHOLDER;
    let root = p
        .spawn((
            Node {
                width: px(NICHE.x),
                height: px(NICHE.y),
                flex_shrink: 0.0,
                // The arch as elliptical top corners, so the hover aura follows the niche.
                border_radius: BorderRadius {
                    top_left: CornerRadius { x: px(150.0), y: px(112.0) },
                    top_right: CornerRadius { x: px(150.0), y: px(112.0) },
                    bottom_left: CornerRadius::from(px(14.0)),
                    bottom_right: CornerRadius::from(px(14.0)),
                },
                ..default()
            },
            glow(god1.with_alpha(0.0), 24.0, 2.0),
            UiButton,
            Hovered::default(),
            KitHover { lift: 12.0, glow_alpha: 0.55, t: 0.0 },
        ))
        .with_children(|c| {
            c.spawn((fill(), kit.tex_tinted("frames/niche_body@2x.png", body_tint), Pickable::IGNORE));
            c.spawn((
                fill(),
                kit.tex_tinted(
                    "frames/niche_glow@2x.png",
                    crate::palette::mix(god1, hx(0x8C8272), 0.35).with_alpha(0.2),
                ),
                Pickable::IGNORE,
            ));
            // The god sigil as a 6 % watermark in the lower half.
            if let Some((key, _)) = spec.gods.first() {
                c.spawn((
                    centered_at(150.0, 318.0, 186.0, 186.0),
                    icon_bundle(&format!("gods/{key}"), 186.0, god1.with_alpha(0.055)),
                ));
            }
            match god2 {
                None => {
                    c.spawn((fill(), kit.tex_tinted("frames/niche_hairline@2x.png", god1), Pickable::IGNORE));
                }
                Some(g2) => {
                    // Duo: the hairline in two halves, god 1 left and god 2 right.
                    for (left, color) in [(true, god1), (false, g2)] {
                        c.spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: px(if left { 0.0 } else { NICHE.x / 2.0 }),
                                top: px(0.0),
                                width: px(NICHE.x / 2.0),
                                height: px(NICHE.y),
                                overflow: Overflow::clip(),
                                ..default()
                            },
                            Pickable::IGNORE,
                        ))
                        .with_children(|h| {
                            h.spawn((
                                abs(if left { 0.0 } else { -NICHE.x / 2.0 }, 0.0, NICHE.x, NICHE.y),
                                kit.tex_tinted("frames/niche_hairline@2x.png", color),
                                Pickable::IGNORE,
                            ));
                        });
                    }
                }
            }
            c.spawn((
                fill(),
                kit.tex(&format!("frames/niche_frame_{}@2x.png", rarity_key(spec.rarity))),
                Pickable::IGNORE,
            ));
            if spec.rarity != Rarity::Common {
                for x in [0.0, NICHE.x] {
                    c.spawn((centered_at(x, 112.0, 20.0, 20.0), Pickable::IGNORE)).with_children(|g| {
                        rarity_gem(g, spec.rarity, 8.0);
                    });
                }
            }
            // Apex medallion Ø100 at (150, 56).
            medallion_e = c
                .spawn((
                    Node { border_radius: BorderRadius::MAX, ..centered_at(150.0, 56.0, 100.0, 100.0) },
                    glow(god1.with_alpha(0.22), 12.0, 1.0),
                    Pickable::IGNORE,
                ))
                .with_children(|m| {
                    match god2 {
                        None => {
                            m.spawn((inset(5.0), kit.tex_tinted("slots/enamel_disc@2x.png", god1), Pickable::IGNORE));
                        }
                        Some(g2) => {
                            for (left, color) in [(true, god1), (false, g2)] {
                                m.spawn((
                                    Node {
                                        position_type: PositionType::Absolute,
                                        left: px(if left { 0.0 } else { 50.0 }),
                                        top: px(0.0),
                                        width: px(50.0),
                                        height: px(100.0),
                                        overflow: Overflow::clip(),
                                        ..default()
                                    },
                                    Pickable::IGNORE,
                                ))
                                .with_children(|h| {
                                    h.spawn((
                                        abs(if left { 5.0 } else { -45.0 }, 5.0, 90.0, 90.0),
                                        kit.tex_tinted("slots/enamel_disc@2x.png", color),
                                        Pickable::IGNORE,
                                    ));
                                });
                            }
                        }
                    }
                    m.spawn((centered(64.0, 64.0), icon_bundle(&spec.icon, 64.0, hx(0xFFF7E6))));
                    m.spawn((fill(), kit.tex("slots/medallion_rim_100@2x.png"), Pickable::IGNORE));
                })
                .id();
            if spec.crest {
                c.spawn((
                    centered_at(150.0, 0.0, 130.0, 50.0),
                    kit.tex("ornaments/suncrest_50@2x.png"),
                    Pickable::IGNORE,
                ));
            }
            // God badges on the medallion's shoulder.
            let badges: Vec<(f32, f32, &(String, Color))> = if spec.gods.len() > 1 {
                vec![(104.0, 94.0, &spec.gods[0]), (196.0, 94.0, &spec.gods[1])]
            } else {
                spec.gods.first().map(|g| vec![(197.0, 93.0, g)]).unwrap_or_default()
            };
            for (x, y, (key, color)) in badges {
                c.spawn((centered_at(x, y, 34.0, 34.0), Pickable::IGNORE)).with_children(|b| {
                    medallion(
                        b,
                        kit,
                        MedallionSpec::new(34.0).enamel(*color).glyph(&format!("gods/{key}"), 0.62, hx(0xFFF7E6)),
                    );
                });
            }
            content(c);
        })
        .id();
    p.commands_mut().entity(root).insert(NicheParts { medallion: medallion_e });
    root
}

/// Hover lift and aura (§7.2 boon cards; any card): lifts `lift` px over 120 ms and raises the
/// root's first `BoxShadow` to `glow_alpha`.
#[derive(Component, Clone, Copy, Debug)]
pub struct KitHover {
    pub lift: f32,
    pub glow_alpha: f32,
    pub t: f32,
}

// ───────────────────────────── markers ─────────────────────────────

/// Edge-pin ring (§6.13).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum PinRing {
    /// POIs and shrines.
    Gilt,
    /// Allies (player colour), pings, and the downed ally (`danger`).
    Tint(Color),
}

/// An edge pin (§6.13): the Ø34 medallion, a 24 px glyph, and the ring with its outward nub.
/// Rotate [`PinParts::frame`] (`UiTransform.rotation`, radians clockwise from up) to aim the nub.
pub fn pin(p: &mut ChildSpawnerCommands, kit: &UiKit, ring: PinRing, glyph: &str, glyph_tint: Color) -> Entity {
    let mut frame = Entity::PLACEHOLDER;
    let root = p
        .spawn((
            Node { width: px(34.0), height: px(34.0), flex_shrink: 0.0, border_radius: BorderRadius::MAX, ..default() },
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            c.spawn((fill(), kit.tex("markers/pin_disc@2x.png"), Pickable::IGNORE));
            c.spawn((centered(24.0, 24.0), icon_bundle(glyph, 24.0, glyph_tint)));
            let tex = match ring {
                PinRing::Gilt => kit.tex("markers/pin_frame_gilt@2x.png"),
                PinRing::Tint(col) => kit.tex_tinted("markers/pin_frame_tint@2x.png", col),
            };
            frame = c.spawn((centered(56.0, 56.0), tex, UiTransform::default(), Pickable::IGNORE)).id();
        })
        .id();
    p.commands_mut().entity(root).insert(PinParts { frame });
    root
}

/// Parts of an ally tag.
#[derive(Component, Clone, Copy, Debug)]
pub struct AllyTagParts {
    /// The HP bar: write its [`KitBar`].
    pub bar: Entity,
    /// The name capsule: show it under 60 % HP or when downed (`Node.display`).
    pub capsule: Entity,
}

/// An ally's world tag (§6.11): the name capsule (a player pip and the name in `Body` Bold 14),
/// a 46×6 rimless HP bar and the player-colour chevron under it. The capsule starts hidden.
pub fn ally_tag(p: &mut ChildSpawnerCommands, kit: &UiKit, name: &str, color: Color) -> Entity {
    let mut parts = AllyTagParts { bar: Entity::PLACEHOLDER, capsule: Entity::PLACEHOLDER };
    let root = p
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(3.0),
                ..default()
            },
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            parts.capsule = c
                .spawn((
                    Node {
                        height: px(19.0),
                        padding: UiRect::horizontal(px(7.0)),
                        column_gap: px(5.0),
                        align_items: AlignItems::Center,
                        border_radius: BorderRadius::all(px(9.5)),
                        display: Display::None,
                        ..default()
                    },
                    BackgroundColor(hx(0x0C0806).with_alpha(0.72)),
                    Pickable::IGNORE,
                ))
                .with_children(|cap| {
                    cap.spawn((
                        Node { width: px(7.0), height: px(7.0), border_radius: BorderRadius::MAX, ..default() },
                        BackgroundColor(color),
                    ));
                    cap.spawn(kit.text_flat(Ty::Strong, 14.0, name, tok::PARCH));
                })
                .id();
            parts.bar = bar(c, kit, BarSpec { edge: false, ..BarSpec::new(46.0, 6.0, BarFill::Hp).no_rim() });
            c.spawn((
                Node { width: px(8.0), height: px(5.0), ..default() },
                kit.tex_tinted("markers/ally_chevron@2x.png", color),
                Pickable::IGNORE,
            ));
        })
        .id();
    p.commands_mut().entity(root).insert(parts);
    root
}

/// A world prompt plate (§6.11): quiet plate 44 tall with a tail, the key, the verb in
/// `LabelS` 16 `gold_lt` and the subject in `BodyS` 14 dim.
pub fn prompt_plate(p: &mut ChildSpawnerCommands, kit: &UiKit, key: Key, verb: &str, subject: &str) -> Entity {
    let root = quiet_plate(
        p,
        Node {
            height: px(44.0),
            padding: UiRect { left: px(12.0), right: px(16.0), ..default() },
            align_items: AlignItems::Center,
            column_gap: px(10.0),
            flex_shrink: 0.0,
            ..default()
        },
        0.8,
        |c| {
            key_chip(c, kit, key, 20.0);
            c.spawn((column(0.0), Pickable::IGNORE)).with_children(|t| {
                t.spawn(kit.text_px(Ty::LabelS, 16.0, verb.to_uppercase(), tok::GOLD_LT));
                if !subject.is_empty() {
                    t.spawn(kit.text_px(Ty::BodyS, 14.0, subject, tok::PARCH_DIM));
                }
            });
        },
    );
    p.commands_mut().entity(root).with_children(|c| {
        c.spawn((
            Node {
                position_type: PositionType::Absolute,
                left: percent(50.0),
                bottom: px(-8.0),
                width: px(14.0),
                height: px(9.0),
                margin: UiRect::left(px(-7.0)),
                ..default()
            },
            kit.tex("markers/prompt_tail@2x.png"),
            Pickable::IGNORE,
        ));
    });
    root
}

/// A damage number's text bundle (§6.12): `Dmg` 21 in the element hue, crit 28 in `ichor`. Pop
/// it with `UiTransform.scale`, never the font size.
pub fn damage_text(kit: &UiKit, value: u32, hue: Color, crit: bool) -> impl Bundle {
    let (px_size, color) = if crit { (28.0, tok::ICHOR) } else { (21.0, hue) };
    kit.text_px(Ty::Dmg, px_size, value.to_string(), color)
}

/// A button bundle for callers that build their own layout: the headless button plus hover
/// tracking and a kit texture.
pub fn button_bundle(kit: &UiKit, kind: ButtonKind) -> impl Bundle {
    (UiButton, Hovered::default(), kit.tex(fx::button_texture(kind, false, false, false)))
}

/// Disable or enable a kit button.
pub fn set_disabled(commands: &mut Commands, button: Entity, disabled: bool) {
    if disabled {
        commands.entity(button).insert(InteractionDisabled);
    } else {
        commands.entity(button).remove::<InteractionDisabled>();
    }
}

// ───────────────────────────── toasts ─────────────────────────────

/// One toast row (§6.5): an ink smear fading right, a gilt accent bar, a 20 px icon and rich
/// text in `Body` 17 (names bold in their reserved colours, the rest `parch_dim`). The HUD lane
/// owns the pool of three and the motion; this is the row.
pub fn toast(p: &mut ChildSpawnerCommands, kit: &UiKit, icon_key: &str, spans: &[(Ty, &str, Color)]) -> Entity {
    p.spawn((
        Node { width: px(440.0), height: px(30.0), align_items: AlignItems::Center, flex_shrink: 0.0, ..default() },
        BackgroundGradient(vec![
            LinearGradient::to_right(vec![
                ColorStop::percent(tok::POOL.with_alpha(0.62), 0.0),
                ColorStop::percent(tok::POOL.with_alpha(0.45), 55.0),
                ColorStop::percent(tok::POOL.with_alpha(0.0), 100.0),
            ])
            .into(),
        ]),
        UiTransform::default(),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        c.spawn((
            abs(16.0, 4.0, 2.0, 22.0),
            BackgroundGradient(vec![
                LinearGradient::to_bottom(vec![
                    ColorStop::auto(tok::GOLD_HI),
                    ColorStop::auto(tok::GOLD_MD),
                    ColorStop::auto(tok::GOLD_DK),
                ])
                .into(),
            ]),
            Pickable::IGNORE,
        ));
        c.spawn((abs(34.0, 5.0, 20.0, 20.0), icon_bundle(icon_key, 20.0, Color::WHITE)));
        c.spawn((
            Node { position_type: PositionType::Absolute, left: px(62.0), top: px(4.0), ..default() },
            Pickable::IGNORE,
        ))
        .with_children(|t| {
            rich(t, kit, 17.0, spans, None, Justify::Left);
        });
    })
    .id()
}

// ───────────────────────────── wayfinder hook ─────────────────────────────

/// The minimap frame (§6.6, OPEN_WORLD phase 3 hook). Spawned hidden (`Display::None`).
#[derive(Component, Clone, Copy, Debug)]
pub struct MinimapFrame {
    /// Clipped content (inset 3): phase 3 writes its map `ImageNode` here.
    pub content: Entity,
    /// Absolute pins over the map (players, POIs, the gate).
    pub icons: Entity,
}

/// Marks the minimap's clipped content node.
#[derive(Component, Clone, Copy, Debug, Default)]
pub struct MinimapContent;

/// Marks the minimap's pin layer.
#[derive(Component, Clone, Copy, Debug, Default)]
pub struct MinimapIcons;

/// The 280×176 minimap frame with its gilt rim, horns and north gem baked (`frames/minimap_frame`),
/// a clipped `MinimapContent` node and a `MinimapIcons` layer. It starts hidden; phase 3 sets
/// `Display::Flex` on the returned root once it has a map to show. Place it with `node`
/// (`left`/`top`, e.g. the frame at (1616, 24) means the texture at (1613, 21)).
pub fn minimap_frame(p: &mut ChildSpawnerCommands, kit: &UiKit, node: Node) -> Entity {
    let mut content = Entity::PLACEHOLDER;
    let mut icons = Entity::PLACEHOLDER;
    let root = p
        .spawn((
            Node { width: px(286.0), height: px(182.0), display: Display::None, ..node },
            drop_shadow(0.6, 4.0, 12.0),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            content = c
                .spawn((
                    Node { overflow: Overflow::clip(), border_radius: BorderRadius::all(px(8.0)), ..inset(6.0) },
                    BackgroundColor(hx(0x140E0A)),
                    MinimapContent,
                    Pickable::IGNORE,
                ))
                .id();
            icons = c.spawn((inset(6.0), MinimapIcons, Pickable::IGNORE)).id();
            c.spawn((fill(), kit.tex("frames/minimap_frame@2x.png"), ZIndex(2), Pickable::IGNORE));
        })
        .id();
    p.commands_mut().entity(root).insert(MinimapFrame { content, icons });
    root
}

// ───────────────────────────── icon keys ─────────────────────────────

/// Typed icon keys (§9.2): map content to `<group>/<name>` keys of `assets/ui/icons/icons.json`.
/// A key with no master falls back to its group's generic glyph at runtime.
pub mod ik {
    use gf_core::aim::{AimMode, TargetBias};
    use gf_core::damage::DamageType;
    use gf_core::poi::PoiKind;
    use gf_core::rarity::Rarity;
    use gf_core::status::StatusKind;

    /// A weapon part by its `parts.ron` key.
    pub fn part(key: &str) -> String {
        format!("parts/{key}")
    }

    /// A boon by its `boons.ron` key.
    pub fn boon(key: &str) -> String {
        format!("boons/{key}")
    }

    /// A chassis by its `chassis.ron` key.
    pub fn chassis(key: &str) -> String {
        format!("chassis/{key}")
    }

    /// A god sigil by its `gods.ron` key.
    pub fn god(key: &str) -> String {
        format!("gods/{key}")
    }

    /// A character's bust crest by its `characters.ron` key.
    pub fn portrait(character: &str) -> String {
        format!("portraits/{character}")
    }

    /// A kit ability: `slot` is `q`, `e`, `r` or `passive`.
    pub fn kit(character: &str, slot: &str) -> String {
        format!("kits/{character}_{slot}")
    }

    pub fn element(e: DamageType) -> &'static str {
        match e {
            DamageType::Kinetic => "elements/kinetic",
            DamageType::Flame => "elements/flame",
            DamageType::Storm => "elements/storm",
            DamageType::Void => "elements/void",
            DamageType::Plague => "elements/plague",
            DamageType::Radiant => "elements/radiant",
        }
    }

    pub fn status(s: StatusKind) -> String {
        format!("status/{}", s.name().to_lowercase())
    }

    pub fn poi(kind: PoiKind) -> String {
        format!("poi/{}", kind.name().to_lowercase())
    }

    /// The empty-slot ghost glyph of a weapon part slot.
    pub fn slot_ghost(slot: gf_core::forge::Slot) -> &'static str {
        use gf_core::forge::Slot;
        match slot {
            Slot::Core => "slots/core",
            Slot::Mechanism => "slots/mechanism",
            Slot::Relic => "slots/relic",
            Slot::Sigil => "slots/sigil",
        }
    }

    /// The cut rarity gem (the only icons with baked colour).
    pub fn rarity_gem(r: Rarity) -> &'static str {
        match r {
            Rarity::Common => "rarity/gem_common",
            Rarity::Rare => "rarity/gem_rare",
            Rarity::Epic => "rarity/gem_epic",
            Rarity::Godforged => "rarity/gem_godforged",
        }
    }

    pub fn aim(mode: AimMode) -> &'static str {
        match mode {
            AimMode::Auto => "aim/auto",
            AimMode::Assisted => "aim/assisted",
            AimMode::Manual => "aim/manual",
        }
    }

    pub fn bias(bias: TargetBias) -> &'static str {
        match bias {
            TargetBias::Balanced => "aim/bias_balanced",
            TargetBias::Nearest => "aim/bias_nearest",
            TargetBias::Strongest => "aim/bias_strongest",
            TargetBias::LowestHp => "aim/bias_lowest_hp",
            TargetBias::Pinned => "aim/bias_pinned",
        }
    }
}
