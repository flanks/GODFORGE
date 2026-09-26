//! # The combat HUD (UI_STYLE §6)
//!
//! Four corner clusters and a thin top band, built once at startup on the UI kit
//! ([`crate::uikit`]) and updated in place:
//!
//! * [`hearth`]: bottom-left, me: the portrait medallion with the ultimate ring, HP with a drain
//!   ghost and ward hatch, armour plates, dash lozenges, Q / E / Team Overdrive, the aim chip,
//!   buffs, the low-HP vignette.
//! * [`arsenal`]: bottom-right: the chassis hex, the four part slots with rarity gems, the wallet,
//!   and the boon chip above it.
//! * [`party`]: top-left: ally medallions with P chips, names and bars; the toast rail below.
//! * [`wayfinder`]: top-right: the hidden minimap frame (phase-3 hook) and the objective tracker.
//! * [`top`]: top-centre transients: the boss and Warlord bar, the callout lane, the region
//!   banner; the surge edge flash.
//! * [`world`]: world-anchored UI: prompt plates, the personal state banner, ally tags, elite
//!   bars, POI labels, downed markers, and the touch overlay.
//!
//! Edge pins live in `offscreen.rs`, damage numbers in `vfx.rs`. After layout, every visible
//! cluster writes its rect into [`HudRects`] so pins, prompts, tags and numbers keep out.
//!
//! Hooks for other lanes: [`HudFocus`] (the panels lane hides clusters under the Forge drawer and
//! the boon spread) and `uikit::MinimapFrame` (phase 3 fills the minimap).

mod arsenal;
mod hearth;
mod party;
mod top;
mod wayfinder;
mod world;

use crate::camera::MainCamera;
use crate::input::Settings;
use crate::net::{Link, Prediction};
use crate::theme::{HudRects, Ty, tok, z};
use crate::uikit::{self, KitBar, KitRing, Pulse, SlotIcon, SlotState, UiIcon, UiKit};
use crate::{ClientConfig, ClientSet};
use gf_engine::client::{Pickable, SystemParam, world_to_screen};
use gf_engine::prelude::*;

/// Touch hit zones in normalized window coordinates (x right, y down) → button index
/// (0 dash, 1 active 1, 2 active 2, 3 ultimate, 4 interact). ≥ 44 px targets at phone sizes.
pub const TOUCH_BUTTONS: [(Vec2, u8); 5] = [
    (Vec2::new(0.91, 0.80), 0),
    (Vec2::new(0.80, 0.88), 1),
    (Vec2::new(0.79, 0.70), 2),
    (Vec2::new(0.91, 0.60), 3),
    (Vec2::new(0.68, 0.88), 4),
];

/// What the panels lane tells the HUD (UI_STYLE §7.1, §7.2). While the Forge drawer is open the
/// Tracker, the Arsenal and the boon chip hide; while the boon spread is open the Tracker and the
/// chip hide. `InputState.forge_open` counts as the drawer too.
#[derive(Resource, Default, Clone, Copy, Debug)]
pub struct HudFocus {
    pub forge_drawer: bool,
    pub boon_spread: bool,
}

/// A persistent cluster whose rect is written into [`HudRects`] after layout (§11.8).
#[derive(Component)]
struct HudRect;

pub fn build(app: &mut App) {
    app.init_resource::<HudFocus>()
        .init_resource::<DebugFps>()
        .init_resource::<top::SurgeClock>()
        .add_systems(
            Startup,
            (spawn_frame, hearth::spawn, arsenal::spawn, party::spawn, wayfinder::spawn, top::spawn, world::spawn),
        )
        .add_systems(
            Update,
            (
                top::track_surge,
                (
                    hearth::update,
                    arsenal::update,
                    party::update,
                    party::toasts,
                    wayfinder::update,
                    top::boss_bar,
                    top::callouts,
                    top::region_banner,
                    top::surge,
                ),
                (world::prompts, world::tags, world::markers, world::touch_overlay, debug_strip),
                apply_fades,
            )
                .chain()
                .in_set(ClientSet::Presentation),
        )
        .add_systems(PostUpdate, fill_hud_rects.after(gf_engine::bevy::ui::UiSystems::Layout));
}

// ───────────────────────────── canvas placement ─────────────────────────────

/// A cluster root anchored to its screen corner with the size of its §5.3 region `[x0, y0, x1,
/// y1]` (1920×1080 logical px). Children place themselves in region-local px.
fn anchored(corner: uikit::Corner, r: [f32; 4]) -> Node {
    let (w, h) = (r[2] - r[0], r[3] - r[1]);
    let mut n = Node { position_type: PositionType::Absolute, width: px(w), height: px(h), ..default() };
    match corner {
        uikit::Corner::TopLeft => (n.left, n.top) = (px(r[0]), px(r[1])),
        uikit::Corner::TopRight => (n.right, n.top) = (px(theme_w() - r[2]), px(r[1])),
        uikit::Corner::BottomLeft => (n.left, n.bottom) = (px(r[0]), px(theme_h() - r[3])),
        uikit::Corner::BottomRight => (n.right, n.bottom) = (px(theme_w() - r[2]), px(theme_h() - r[3])),
    }
    n
}

/// A root centred horizontally on the screen, spanning `[x0, x1]` of the 1920 canvas, at `y0`.
fn top_centred(x0: f32, x1: f32, y0: f32, h: f32) -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: percent(50.0),
        top: px(y0),
        width: px(x1 - x0),
        height: px(h),
        margin: UiRect::left(px(x0 - theme_w() / 2.0)),
        ..default()
    }
}

const fn theme_w() -> f32 {
    crate::theme::CANVAS.x
}

const fn theme_h() -> f32 {
    crate::theme::CANVAS.y
}

/// A world point → UI logical px (the space `Node.left/top` use): the viewport point divided by
/// UiScale.
pub(crate) fn to_ui(camera: &Camera, cam_tf: &GlobalTransform, at: Vec3, ui_scale: f32) -> Option<Vec2> {
    world_to_screen(camera, cam_tf, at).map(|p| p / ui_scale.max(0.01))
}

/// The viewport size in UI logical px.
pub(crate) fn ui_viewport(camera: &Camera, ui_scale: f32) -> Option<Vec2> {
    camera.logical_viewport_size().map(|s| s / ui_scale.max(0.01))
}

/// Roman numerals for threat levels and boss phases (1..=20).
pub(crate) fn roman(n: u32) -> &'static str {
    const R: [&str; 21] = [
        "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
        "XVII", "XVIII", "XIX", "XX",
    ];
    R[(n as usize).min(20)]
}

/// A player's display name from the roster.
pub(crate) fn player_name(link: &Link, slot: u8) -> String {
    link.roster.iter().find(|r| r.slot == slot).map_or(format!("P{}", slot + 1), |r| r.name.clone())
}

// ───────────────────────────── in-place writes ─────────────────────────────

/// Every component the HUD writes, with change-only setters (§11.10: write only on change).
#[derive(SystemParam)]
pub(crate) struct Ui<'w, 's> {
    pub texts: Query<'w, 's, &'static mut Text>,
    pub colors: Query<'w, 's, &'static mut TextColor>,
    pub nodes: Query<'w, 's, &'static mut Node>,
    pub images: Query<'w, 's, &'static mut ImageNode>,
    pub icons: Query<'w, 's, &'static mut UiIcon>,
    pub bars: Query<'w, 's, &'static mut KitBar>,
    pub slots: Query<'w, 's, (&'static mut SlotState, &'static mut SlotIcon)>,
    pub rings: Query<'w, 's, &'static mut KitRing>,
    pub tfs: Query<'w, 's, &'static mut UiTransform>,
    pub bgs: Query<'w, 's, &'static mut BackgroundColor>,
    pub grads: Query<'w, 's, &'static mut BackgroundGradient>,
    pub fades: Query<'w, 's, &'static mut FadeGroup>,
    pub pulses: Query<'w, 's, &'static mut Pulse>,
    pub computed: Query<'w, 's, &'static ComputedNode>,
}

impl Ui<'_, '_> {
    pub fn text(&mut self, e: Entity, s: impl AsRef<str>) {
        if let Ok(mut t) = self.texts.get_mut(e)
            && t.0 != s.as_ref()
        {
            t.0 = s.as_ref().to_string();
        }
    }

    pub fn color(&mut self, e: Entity, c: Color) {
        if let Ok(mut t) = self.colors.get_mut(e)
            && t.0 != c
        {
            t.0 = c;
        }
    }

    pub fn show(&mut self, e: Entity, on: bool) {
        let d = if on { Display::Flex } else { Display::None };
        if let Ok(mut n) = self.nodes.get_mut(e)
            && n.display != d
        {
            n.display = d;
        }
    }

    pub fn shown(&self, e: Entity) -> bool {
        self.nodes.get(e).is_ok_and(|n| n.display != Display::None)
    }

    /// Move an absolute node (UI px).
    pub fn place(&mut self, e: Entity, left: f32, top: f32) {
        if let Ok(mut n) = self.nodes.get_mut(e) {
            let (l, t) = (Val::Px(left.round()), Val::Px(top.round()));
            if n.left != l {
                n.left = l;
            }
            if n.top != t {
                n.top = t;
            }
        }
    }

    pub fn icon(&mut self, e: Entity, key: &str) {
        if let Ok(mut i) = self.icons.get_mut(e)
            && i.key != key
        {
            i.key = key.to_string();
        }
    }

    pub fn tint(&mut self, e: Entity, c: Color) {
        if let Ok(mut i) = self.images.get_mut(e)
            && i.color != c
        {
            i.color = c;
        }
    }

    pub fn bar(&mut self, e: Entity, value: f32, ward: f32) {
        let v = KitBar { value: (value * 1000.0).round() / 1000.0, ward: (ward * 1000.0).round() / 1000.0 };
        if let Ok(mut b) = self.bars.get_mut(e)
            && *b != v
        {
            *b = v;
        }
    }

    pub fn slot(&mut self, e: Entity, state: SlotState) {
        if let Ok((mut s, _)) = self.slots.get_mut(e)
            && *s != state
        {
            *s = state;
        }
    }

    pub fn slot_icon(&mut self, e: Entity, key: Option<String>) {
        if let Ok((_, mut i)) = self.slots.get_mut(e)
            && i.0 != key
        {
            i.0 = key;
        }
    }

    pub fn ring(&mut self, e: Entity, value: f32, ready: bool) {
        if let Ok(mut r) = self.rings.get_mut(e) {
            let v = (value.clamp(0.0, 1.0) * 360.0).round() / 360.0;
            if r.value != v {
                r.value = v;
            }
            if r.ready != ready {
                r.ready = ready;
            }
        }
    }

    pub fn fade(&mut self, e: Entity, alpha: f32) {
        let a = (alpha.clamp(0.0, 1.0) * 100.0).round() / 100.0;
        if let Ok(mut f) = self.fades.get_mut(e)
            && f.alpha != a
        {
            f.alpha = a;
        }
    }

    pub fn transform(&mut self, e: Entity, translate: Vec2, scale: f32) {
        if let Ok(mut tf) = self.tfs.get_mut(e) {
            let t = Val2::px(translate.x, translate.y);
            if tf.translation != t {
                tf.translation = t;
            }
            let s = Vec2::splat(scale);
            if tf.scale != s {
                tf.scale = s;
            }
        }
    }

    pub fn rotate(&mut self, e: Entity, radians: f32) {
        if let Ok(mut tf) = self.tfs.get_mut(e) {
            let r = Rot2::radians(radians);
            if (tf.rotation.as_radians() - radians).abs() > 1e-3 {
                tf.rotation = r;
            }
        }
    }

    pub fn pulse(&mut self, e: Entity, on: bool) {
        if let Ok(mut p) = self.pulses.get_mut(e)
            && p.on != on
        {
            p.on = on;
        }
    }

    /// The laid-out size of a node (UI px), zero before its first layout.
    pub fn size(&self, e: Entity) -> Vec2 {
        self.computed.get(e).map_or(Vec2::ZERO, |c| c.size() * c.inverse_scale_factor())
    }
}

// ───────────────────────────── fading groups ─────────────────────────────

/// Fades a whole subtree (texts, their shadows, images, colours and gradients) to `alpha`.
/// Colours are captured the first time the group applies, so spawn content at full colour.
/// Never put kit widgets that animate their own colours (pulses, slots) inside one.
#[derive(Component, Clone, Copy, Debug)]
pub(crate) struct FadeGroup {
    pub alpha: f32,
    applied: f32,
}

impl FadeGroup {
    pub fn new(alpha: f32) -> Self {
        Self { alpha, applied: -1.0 }
    }
}

/// A faded node's base colours.
#[derive(Component, Clone, Debug)]
struct FadeBase {
    text: Option<Color>,
    image: Option<Color>,
    bg: Option<Color>,
    shadow: Option<Color>,
    grad: Option<Vec<Gradient>>,
}

fn scale_alpha(c: Color, a: f32) -> Color {
    c.with_alpha(c.alpha() * a)
}

fn fade_gradient(base: &[Gradient], a: f32) -> Vec<Gradient> {
    base.iter()
        .map(|g| {
            let mut g = g.clone();
            match &mut g {
                Gradient::Linear(l) => l.stops.iter_mut().for_each(|s| s.color = scale_alpha(s.color, a)),
                Gradient::Radial(r) => r.stops.iter_mut().for_each(|s| s.color = scale_alpha(s.color, a)),
                Gradient::Conic(c) => c.stops.iter_mut().for_each(|s| s.color = scale_alpha(s.color, a)),
            }
            g
        })
        .collect()
}

#[allow(clippy::type_complexity)]
fn apply_fades(
    mut commands: Commands,
    mut groups: Query<(Entity, &mut FadeGroup)>,
    children: Query<&Children>,
    live_slots: Query<(), With<SlotState>>,
    mut items: Query<(
        Option<&FadeBase>,
        Option<&mut TextColor>,
        Option<&mut ImageNode>,
        Option<&mut BackgroundColor>,
        Option<&mut TextShadow>,
        Option<&mut BackgroundGradient>,
    )>,
) {
    for (root, mut g) in &mut groups {
        if (g.alpha - g.applied).abs() < 1e-3 {
            continue;
        }
        g.applied = g.alpha;
        let a = g.alpha;
        let mut stack = vec![root];
        while let Some(e) = stack.pop() {
            // Kit slots own their tints (their state machine captures the icon's base tint).
            if live_slots.contains(e) {
                continue;
            }
            if let Ok(kids) = children.get(e) {
                stack.extend(kids.iter());
            }
            let Ok((base, text, image, bg, shadow, grad)) = items.get_mut(e) else { continue };
            let base = match base {
                Some(b) => b.clone(),
                None => {
                    let b = FadeBase {
                        text: text.as_ref().map(|t| t.0),
                        image: image.as_ref().map(|i| i.color),
                        bg: bg.as_ref().map(|b| b.0),
                        shadow: shadow.as_ref().map(|s| s.color),
                        grad: grad.as_ref().map(|g| g.0.clone()),
                    };
                    commands.entity(e).insert(b.clone());
                    b
                }
            };
            if let (Some(mut t), Some(c)) = (text, base.text) {
                t.0 = scale_alpha(c, a);
            }
            if let (Some(mut i), Some(c)) = (image, base.image) {
                i.color = scale_alpha(c, a);
            }
            if let (Some(mut b), Some(c)) = (bg, base.bg) {
                b.0 = scale_alpha(c, a);
            }
            if let (Some(mut s), Some(c)) = (shadow, base.shadow) {
                s.color = scale_alpha(c, a);
            }
            if let (Some(mut gr), Some(gb)) = (grad, base.grad.as_ref()) {
                gr.0 = fade_gradient(gb, a);
            }
        }
    }
}

// ───────────────────────────── rects, pools, debug strip ─────────────────────────────

/// §11.8: the logical rects of the visible persistent clusters, after layout.
fn fill_hud_rects(
    q: Query<(&ComputedNode, &UiGlobalTransform, &InheritedVisibility), With<HudRect>>,
    mut rects: ResMut<HudRects>,
) {
    let mut v = Vec::with_capacity(12);
    for (node, gt, vis) in &q {
        if !vis.get() {
            continue;
        }
        let k = node.inverse_scale_factor();
        let size = node.size() * k;
        if size.x < 1.0 || size.y < 1.0 {
            continue;
        }
        v.push(Rect::from_center_size(gt.translation * k, size));
    }
    if rects.rects != v {
        rects.rects = v;
    }
}

/// The debug strip's text node (§6.14).
#[derive(Component)]
struct DebugStrip;

/// Smoothed frames per second for the debug strip.
#[derive(Resource, Default)]
struct DebugFps(f32);

/// The corner shadow pools under the clusters (§6.1, §6.2, §6.6) and the debug strip.
fn spawn_frame(mut commands: Commands, kit: Res<UiKit>) {
    commands.spawn((uikit::fill(), GlobalZIndex(z::POOLS), Pickable::IGNORE)).with_children(|p| {
        uikit::corner_pool(p, uikit::Corner::BottomLeft, 1280.0, 500.0, 0.62);
        uikit::corner_pool(p, uikit::Corner::BottomRight, 1040.0, 420.0, 0.6);
        uikit::corner_pool(p, uikit::Corner::TopRight, 940.0, 1000.0, 0.58);
        uikit::corner_pool(p, uikit::Corner::TopLeft, 820.0, 560.0, 0.5);
    });
    commands.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: px(24.0),
            top: px(4.0),
            display: Display::None,
            ..default()
        },
        kit.text_px(Ty::Debug, 12.0, "", tok::PARCH_MUTE),
        DebugStrip,
        GlobalZIndex(z::DEBUG),
    ));
}

/// §6.14: the net line and FPS in one muted line at the top-left, only with `--fps` or F10.
fn debug_strip(
    time: Res<Time>,
    link: Res<Link>,
    pred: Res<Prediction>,
    settings: Res<Settings>,
    mut fps: ResMut<DebugFps>,
    mut q: Query<(&mut Node, &mut Text), With<DebugStrip>>,
) {
    let dt = time.delta_secs().max(1e-4);
    fps.0 = if fps.0 <= 0.0 { 1.0 / dt } else { fps.0 + (1.0 / dt - fps.0) * 0.05 };
    let Ok((mut node, mut text)) = q.single_mut() else { return };
    let d = if settings.debug_strip { Display::Flex } else { Display::None };
    if node.display != d {
        node.display = d;
    }
    if !settings.debug_strip {
        return;
    }
    let s = format!(
        "{} · {:.1} KB/s · corrections {} · {:.0} fps",
        link.host_label,
        link.bytes_per_sec / 1024.0,
        pred.corrections,
        fps.0
    );
    if text.0 != s {
        text.0 = s;
    }
}

/// A POI glyph's tint for pins and labels: bone, a shrine's god colour, the Warlord's ember.
pub(crate) use wayfinder::poi_tint as poi_glyph_tint;

/// Is the Forge drawer (or the legacy forge panel) open?
fn drawer_open(focus: &HudFocus, input: &crate::input::InputState) -> bool {
    focus.forge_drawer || input.forge_open
}

/// The main camera and UiScale, for world-anchored systems.
#[derive(SystemParam)]
pub(crate) struct View<'w, 's> {
    cameras: Query<'w, 's, (&'static Camera, &'static GlobalTransform), With<MainCamera>>,
    scale: Res<'w, UiScale>,
}

impl View<'_, '_> {
    /// World → UI px.
    pub fn project(&self, at: Vec3) -> Option<Vec2> {
        let (camera, tf) = self.cameras.single().ok()?;
        to_ui(camera, tf, at, self.scale.0)
    }

    /// The viewport in UI px.
    pub fn size(&self) -> Option<Vec2> {
        let (camera, _) = self.cameras.single().ok()?;
        ui_viewport(camera, self.scale.0)
    }

    pub fn scale(&self) -> f32 {
        self.scale.0
    }
}

/// `ClientConfig` shortcut for submodules.
fn db(cfg: &ClientConfig) -> &gf_content::ContentDb {
    &cfg.content
}
