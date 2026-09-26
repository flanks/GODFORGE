//! Motion and state for the kit (UI_STYLE §6.1a, §10, §11.4–§11.6).
//!
//! Widgets carry a small state component that game code writes ([`KitBar`], [`SlotState`],
//! [`KitRing`], [`MoltenFill`], [`KitPlates`], [`KitPips`], [`KitCard`]); the systems here turn
//! it into motion and only write layout or gradients when a quantised value moves. [`Tween`] and
//! [`Pulse`] cover everything else (pops, slides, breathing glows). Reduced motion
//! (`Settings.reduced_motion`) drops pulses, pops and bursts and keeps fades.

use super::{ButtonKind, UiKit};
use crate::input::Settings;
use crate::theme::{hx, tok};
use gf_engine::client::{
    AsBindGroup, Hovered, InteractionDisabled, Pressed, ShaderRef, ShaderType, UiMaterial, UiMaterialPlugin,
};
use gf_engine::prelude::*;
use std::f32::consts::{PI, TAU};

pub fn build(app: &mut App) {
    app.add_plugins(UiMaterialPlugin::<MoltenMaterial>::default()).add_systems(
        PostUpdate,
        (
            super::assets::resolve_icons,
            (
                button_visuals,
                card_visuals,
                hover_lift,
                bar_motion,
                slot_visuals,
                ring_visuals,
                molten_visuals,
                plate_visuals,
                pip_visuals,
                tweens,
                pulses,
            ),
            super::assets::materialize,
        )
            .chain()
            .before(gf_engine::bevy::ui::UiSystems::Prepare),
    );
}

fn reduced(settings: &Option<Res<Settings>>) -> bool {
    settings.as_ref().is_some_and(|s| s.reduced_motion)
}

fn ease_out_cubic(t: f32) -> f32 {
    1.0 - (1.0 - t.clamp(0.0, 1.0)).powi(3)
}

fn ease_out_back(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    let (c1, c3) = (1.70158, 2.70158);
    1.0 + c3 * (t - 1.0).powi(3) + c1 * (t - 1.0).powi(2)
}

/// Set an ImageNode's tint only if it changed.
fn set_tint(node: &mut Mut<ImageNode>, color: Color) {
    if node.color != color {
        node.color = color;
    }
}

fn set_display(node: &mut Mut<Node>, show: bool) {
    let d = if show { Display::Flex } else { Display::None };
    if node.display != d {
        node.display = d;
    }
}

fn set_width_pct(node: &mut Mut<Node>, pct: f32) {
    if let Val::Percent(w) = node.width
        && (w - pct).abs() < 0.1
    {
        return;
    }
    node.width = Val::Percent(pct);
}

// ───────────────────────────── buttons and cards ─────────────────────────────

/// A kit button: its look and its label (for state colours).
#[derive(Component, Clone, Copy, Debug)]
pub struct KitButton {
    pub kind: ButtonKind,
    pub label: Entity,
}

/// The texture of a button in a state.
pub fn button_texture(kind: ButtonKind, hover: bool, pressed: bool, disabled: bool) -> &'static str {
    match (kind, disabled, pressed, hover) {
        (ButtonKind::Chip, true, _, _) => "frames/chip_disabled@2x.png",
        (ButtonKind::Chip, false, p, h) if p || h => "frames/chip_hover@2x.png",
        (ButtonKind::Chip, ..) => "frames/chip@2x.png",
        (_, true, _, _) => "frames/button_disabled@2x.png",
        (ButtonKind::Primary, false, true, _) => "frames/button_primary_pressed@2x.png",
        (ButtonKind::Primary, false, false, true) => "frames/button_primary_hover@2x.png",
        (ButtonKind::Primary, ..) => "frames/button_primary@2x.png",
        (ButtonKind::Secondary, false, true, _) => "frames/button_secondary_pressed@2x.png",
        (ButtonKind::Secondary, false, false, true) => "frames/button_secondary_hover@2x.png",
        (ButtonKind::Secondary, ..) => "frames/button_secondary@2x.png",
    }
}

fn button_visuals(
    kit: Res<UiKit>,
    mut buttons: Query<(&KitButton, &Hovered, Has<Pressed>, Has<InteractionDisabled>, &mut ImageNode)>,
    mut labels: Query<&mut TextColor>,
) {
    for (button, hovered, pressed, disabled, mut image) in &mut buttons {
        let hover = hovered.get() && !disabled;
        let tex = kit.tex_handle(button_texture(button.kind, hover, pressed && !disabled, disabled));
        if image.image != tex {
            image.image = tex;
        }
        let color = match (button.kind, disabled) {
            (_, true) => tok::PARCH_MUTE,
            (ButtonKind::Primary, false) => tok::INK_TEXT,
            (_, false) if hover => tok::NUMERAL,
            _ => tok::PARCH,
        };
        if let Ok(mut c) = labels.get_mut(button.label)
            && c.0 != color
        {
            c.0 = color;
        }
    }
}

/// A card's selection: the metal-gold ring with its glow, and a 2 px lift (§7.1).
#[derive(Component, Clone, Copy, Debug)]
pub struct KitCard {
    pub selected: bool,
    pub ring: Entity,
}

fn card_visuals(mut cards: Query<(Ref<KitCard>, &mut UiTransform)>, mut nodes: Query<&mut Node>) {
    for (card, mut tf) in &mut cards {
        if !card.is_changed() {
            continue;
        }
        if let Ok(mut n) = nodes.get_mut(card.ring) {
            set_display(&mut n, card.selected);
        }
        let lift = if card.selected { Val2::px(0.0, -2.0) } else { Val2::ZERO };
        if tf.translation != lift {
            tf.translation = lift;
        }
    }
}

/// Cards that lift on hover (boon niche cards): `lift` px over 120 ms plus the aura.
fn hover_lift(
    time: Res<Time>,
    settings: Option<Res<Settings>>,
    mut q: Query<(&Hovered, &mut super::KitHover, &mut UiTransform, Option<&mut BoxShadow>)>,
) {
    let dt = time.delta_secs();
    let calm = reduced(&settings);
    for (hovered, mut h, mut tf, shadow) in &mut q {
        let target = if hovered.get() { 1.0 } else { 0.0 };
        if h.t == target {
            continue;
        }
        h.t = if target > h.t { (h.t + dt / 0.12).min(1.0) } else { (h.t - dt / 0.12).max(0.0) };
        let k = ease_out_cubic(h.t);
        tf.translation = Val2::px(0.0, if calm { 0.0 } else { -h.lift * k });
        if let Some(mut s) = shadow
            && let Some(first) = s.0.first_mut()
        {
            first.color.set_alpha(h.glow_alpha * k);
        }
    }
}

// ───────────────────────────── bars ─────────────────────────────

/// A bar's value and ward (shield), both 0..1 of the maximum. Write these; the kit animates.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct KitBar {
    pub value: f32,
    pub ward: f32,
}

/// The layers of a bar.
#[derive(Component, Clone, Copy, Debug)]
pub struct BarParts {
    pub fill: Entity,
    pub ghost: Entity,
    pub ward: Entity,
    pub edge: Entity,
}

impl Default for BarParts {
    fn default() -> Self {
        Self {
            fill: Entity::PLACEHOLDER,
            ghost: Entity::PLACEHOLDER,
            ward: Entity::PLACEHOLDER,
            edge: Entity::PLACEHOLDER,
        }
    }
}

/// Internal bar motion state.
#[derive(Component, Clone, Copy, Debug)]
pub struct BarAnim {
    shown: f32,
    ghost: f32,
    hold: f32,
    from: f32,
    t: f32,
}

impl BarAnim {
    pub fn new(v: f32) -> Self {
        Self { shown: v, ghost: v, hold: 0.0, from: v, t: 1.0 }
    }
}

/// §10: the fill snaps on damage; the ghost holds 0.35 s, then eases to the fill over 0.45 s
/// (cubic out). Heals grow the fill over about 0.25 s.
fn bar_motion(time: Res<Time>, mut bars: Query<(&KitBar, &BarParts, &mut BarAnim)>, mut nodes: Query<&mut Node>) {
    let dt = time.delta_secs();
    for (bar, parts, mut a) in &mut bars {
        let target = bar.value.clamp(0.0, 1.0);
        if target < a.shown - 1e-4 {
            a.ghost = a.ghost.max(a.shown);
            a.shown = target;
            a.hold = 0.35;
            a.from = a.ghost;
            a.t = 0.0;
        } else if target > a.shown + 1e-4 {
            a.shown = target - (target - a.shown) * (-dt / 0.06).exp();
            if target - a.shown < 1e-3 {
                a.shown = target;
            }
            a.ghost = a.ghost.max(a.shown);
        }
        if a.hold > 0.0 {
            a.hold -= dt;
        } else if a.ghost > a.shown {
            a.t += dt / 0.45;
            a.ghost = a.from + (a.shown - a.from) * ease_out_cubic(a.t);
            if a.t >= 1.0 {
                a.ghost = a.shown;
            }
        }
        if let Ok(mut n) = nodes.get_mut(parts.fill) {
            set_width_pct(&mut n, a.shown * 100.0);
        }
        if let Ok(mut n) = nodes.get_mut(parts.ghost) {
            set_width_pct(&mut n, a.ghost.max(a.shown) * 100.0);
        }
        if let Ok(mut n) = nodes.get_mut(parts.ward) {
            let w = bar.ward.clamp(0.0, 1.0 - a.shown);
            set_display(&mut n, w > 0.002);
            let left = Val::Percent(a.shown * 100.0);
            if n.left != left {
                n.left = left;
            }
            set_width_pct(&mut n, w * 100.0);
        }
        if let Ok(mut n) = nodes.get_mut(parts.edge) {
            set_display(&mut n, a.shown > 0.004);
            let left = Val::Percent(a.shown * 100.0);
            if n.left != left {
                n.left = left;
            }
        }
    }
}

// ───────────────────────────── slots ─────────────────────────────

/// What a slot shows: `cooldown` is the remaining fraction (0 = ready), `secs` the remaining
/// seconds for the numeral.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct SlotState {
    pub cooldown: f32,
    pub secs: f32,
    pub disabled: bool,
}

impl SlotState {
    pub const READY: Self = Self { cooldown: 0.0, secs: 0.0, disabled: false };
    pub const DISABLED: Self = Self { cooldown: 0.0, secs: 0.0, disabled: true };

    /// Cooling down: `remaining` fraction (1 → 0) and seconds left.
    pub fn cooling(remaining: f32, secs: f32) -> Self {
        Self { cooldown: remaining.clamp(0.0, 1.0), secs: secs.max(0.0), disabled: false }
    }

    pub fn ready(&self) -> bool {
        !self.disabled && self.cooldown <= 0.0
    }
}

/// The layers of a slot (see [`super::slot`]).
#[derive(Component, Clone, Copy, Debug)]
pub struct SlotParts {
    pub glow: Entity,
    pub icon: Entity,
    pub sweep: Entity,
    pub edge: Entity,
    pub sheen: Entity,
    pub rim: Entity,
    pub secs: Entity,
    pub flash: Entity,
    pub burst: Entity,
    /// The slot size in logical px.
    pub size: f32,
}

impl Default for SlotParts {
    fn default() -> Self {
        let e = Entity::PLACEHOLDER;
        Self { glow: e, icon: e, sweep: e, edge: e, sheen: e, rim: e, secs: e, flash: e, burst: e, size: 60.0 }
    }
}

/// Internal slot motion state.
#[derive(Component, Clone, Copy, Debug, Default)]
pub struct SlotAnim {
    init: bool,
    was_ready: bool,
    /// Seconds since the slot became ready (the flash, pop and burst play in the first 0.3 s).
    since_ready: f32,
    angle_q: i32,
    secs_q: i32,
    base_tint: Option<Color>,
}

#[allow(clippy::too_many_arguments)]
fn slot_visuals(
    time: Res<Time>,
    settings: Option<Res<Settings>>,
    mut slots: Query<(&SlotState, &SlotParts, &mut SlotAnim, &mut UiTransform), Without<SlotChild>>,
    mut images: Query<&mut ImageNode>,
    mut nodes: Query<&mut Node>,
    mut gradients: Query<&mut BackgroundGradient>,
    mut transforms: Query<&mut UiTransform, With<SlotChild>>,
    children: Query<&Children>,
    mut texts: Query<&mut Text>,
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
    let calm = reduced(&settings);
    for (state, parts, mut a, mut tf) in &mut slots {
        let ready = state.ready();
        let cooling = !state.disabled && state.cooldown > 0.0;
        if !a.init {
            a.init = true;
            a.was_ready = ready;
            a.since_ready = 10.0;
            a.angle_q = -1;
            a.secs_q = -1;
            a.base_tint = images.get(parts.icon).ok().map(|i| i.color);
        }
        if ready && !a.was_ready {
            a.since_ready = 0.0;
        }
        a.was_ready = ready;
        a.since_ready += dt;

        // Icon: cooling darkens through the multiply; disabled goes further.
        if let Ok(mut icon) = images.get_mut(parts.icon) {
            let tint = if state.disabled {
                hx(0x4A423A)
            } else if cooling {
                tok::COOLING
            } else {
                a.base_tint.unwrap_or(Color::WHITE)
            };
            set_tint(&mut icon, tint);
        }

        // Sweep: the dark wedge covers the remaining fraction, its edge moving clockwise.
        if let Ok(mut n) = nodes.get_mut(parts.sweep) {
            set_display(&mut n, cooling);
        }
        if cooling {
            let q = ((1.0 - state.cooldown) * 360.0).round() as i32;
            if q != a.angle_q {
                a.angle_q = q;
                let start = q as f32 / 360.0 * TAU;
                if let Ok(mut g) = gradients.get_mut(parts.sweep) {
                    let dark = tok::POOL.with_alpha(0.7);
                    *g = BackgroundGradient(vec![
                        ConicGradient::new(
                            UiPosition::CENTER,
                            vec![
                                AngularColorStop::new(Color::NONE, 0.0),
                                AngularColorStop::new(Color::NONE, start),
                                AngularColorStop::new(dark, start),
                                AngularColorStop::new(dark, TAU),
                            ],
                        )
                        .with_start(0.0)
                        .into(),
                    ]);
                }
                if let Ok(mut t) = transforms.get_mut(parts.edge) {
                    t.rotation = Rot2::radians(start);
                }
            }
        } else {
            a.angle_q = -1;
        }

        // Seconds: one decimal under 10 s, whole seconds above; 0.1 s steps.
        if let Ok(mut n) = nodes.get_mut(parts.secs) {
            set_display(&mut n, cooling && state.secs > 0.0);
        }
        if cooling {
            let q = (state.secs * 10.0).ceil() as i32;
            if q != a.secs_q {
                a.secs_q = q;
                let s = q as f32 / 10.0;
                let label = if s < 10.0 { format!("{s:.1}") } else { format!("{:.0}", s.ceil()) };
                if let Ok(kids) = children.get(parts.secs)
                    && let Some(&t) = kids.first()
                    && let Ok(mut text) = texts.get_mut(t)
                {
                    text.0 = label;
                }
            }
        }

        // Ready halo: breathes while ready; warms in over the last 0.5 s of a cooldown.
        if let Ok(mut g) = images.get_mut(parts.glow) {
            let alpha = if ready {
                if calm { 0.6 } else { 0.5 + 0.25 * (now * TAU / 1.6).sin() }
            } else if cooling && state.secs < 0.5 {
                (0.5 - state.secs) / 0.5 * 0.45
            } else {
                0.0
            };
            set_tint(&mut g, tok::READY_GLOW.with_alpha(alpha));
        }
        if let Ok(mut n) = nodes.get_mut(parts.sheen) {
            set_display(&mut n, ready);
        }

        // Ready: a 90 ms white-gold flash, a 1.0 → 1.12 → 1.0 pop over 220 ms, a ring burst of
        // +10 px over 300 ms.
        let t = a.since_ready;
        if let Ok(mut f) = images.get_mut(parts.flash) {
            let alpha = if t < 0.09 { 0.85 * (1.0 - t / 0.09) } else { 0.0 };
            set_tint(&mut f, hx(0xFFF3C8).with_alpha(alpha));
        }
        let pop = if !calm && t < 0.22 { 1.0 + 0.12 * (PI * t / 0.22).sin() } else { 1.0 };
        if tf.scale.x != pop {
            tf.scale = Vec2::splat(pop);
        }
        if let Ok(mut b) = images.get_mut(parts.burst) {
            let alpha = if !calm && t < 0.3 { 0.9 * (1.0 - t / 0.3) } else { 0.0 };
            set_tint(&mut b, tok::GOLD_HI.with_alpha(alpha));
        }
        if let Ok(mut bt) = transforms.get_mut(parts.burst) {
            let grow = if t < 0.3 { ease_out_cubic(t / 0.3) } else { 1.0 };
            let s = 1.0 + grow * 20.0 / parts.size.max(20.0);
            if bt.scale.x != s {
                bt.scale = Vec2::splat(s);
            }
        }
    }
}

/// Marks slot children driven through `UiTransform` (sweep edge, burst) so their transforms
/// don't alias the slot root's.
#[derive(Component, Clone, Copy, Debug, Default)]
pub struct SlotChild;

// ───────────────────────────── rings ─────────────────────────────

/// Ring fill material.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum RingStyle {
    /// The ult and heat rings: the molten ramp pouring to a bright head.
    Molten,
    /// Buff timers and passive meters.
    Ichor,
    /// Hold prompts (gold on an ink trough).
    Gold,
    /// A countdown in one colour (downed marker: white; shrine holds: the god colour).
    Tint(Color),
}

/// A ring meter's value (0..1, clockwise from 12 o'clock). `ready` brightens a full molten ring.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub struct KitRing {
    pub value: f32,
    pub style: RingStyle,
    pub ready: bool,
}

/// Internal ring motion state.
#[derive(Component, Clone, Copy, Debug)]
pub struct RingAnim {
    shown: f32,
    q: i32,
}

impl Default for RingAnim {
    fn default() -> Self {
        Self { shown: -1.0, q: -1 }
    }
}

fn ring_stops(style: RingStyle, a: f32, ready: bool) -> Vec<AngularColorStop> {
    let a = a.clamp(0.0, TAU);
    let trough = match style {
        RingStyle::Molten => hx(0x140C08),
        _ => tok::INK.with_alpha(0.6),
    };
    let mut stops = Vec::with_capacity(8);
    // A full ring has no pour front: grade it symmetrically so 12 o'clock shows no seam.
    if a >= TAU - 1e-3 {
        let (edge, mid) = match style {
            RingStyle::Molten if ready => (tok::MOLTEN[1], tok::MOLTEN[0]),
            RingStyle::Molten => (tok::MOLTEN[2], tok::MOLTEN[1]),
            RingStyle::Ichor => (tok::ICHOR, tok::ICHOR),
            RingStyle::Gold => (tok::GOLD_LT, tok::GOLD_LT),
            RingStyle::Tint(c) => (c, c),
        };
        return vec![
            AngularColorStop::new(edge, 0.0),
            AngularColorStop::new(mid, PI),
            AngularColorStop::new(edge, TAU),
        ];
    }
    match style {
        RingStyle::Molten => {
            let head = if ready { tok::MOLTEN[0] } else { tok::MOLTEN[1] };
            stops.push(AngularColorStop::new(tok::MOLTEN[3], 0.0));
            stops.push(AngularColorStop::new(tok::MOLTEN[2], a * 0.7));
            stops.push(AngularColorStop::new(head, (a - 0.02).max(0.0)));
            stops.push(AngularColorStop::new(tok::MOLTEN[0], a));
        }
        RingStyle::Ichor => {
            stops.push(AngularColorStop::new(tok::ICHOR, 0.0));
            stops.push(AngularColorStop::new(tok::ICHOR, a));
        }
        RingStyle::Gold => {
            stops.push(AngularColorStop::new(tok::GOLD_MD, 0.0));
            stops.push(AngularColorStop::new(tok::GOLD_LT, a));
        }
        RingStyle::Tint(c) => {
            stops.push(AngularColorStop::new(c, 0.0));
            stops.push(AngularColorStop::new(c, a));
        }
    }
    if a < TAU - 1e-3 {
        stops.push(AngularColorStop::new(trough, a));
        stops.push(AngularColorStop::new(trough, TAU));
    }
    stops
}

/// §10: the level eases 0.2 s toward its target; the gradient is rewritten per 1/360 step.
fn ring_visuals(time: Res<Time>, mut rings: Query<(Ref<KitRing>, &mut RingAnim, &mut BorderGradient)>) {
    let dt = time.delta_secs();
    for (ring, mut a, mut g) in &mut rings {
        let target = ring.value.clamp(0.0, 1.0);
        if a.shown < 0.0 {
            a.shown = target;
        } else {
            a.shown = target - (target - a.shown) * (-dt / 0.07).exp();
        }
        let q = (a.shown * 360.0).round() as i32 + if ring.ready { 1000 } else { 0 };
        if q == a.q && !ring.is_changed() {
            continue;
        }
        a.q = q;
        *g = BorderGradient(vec![
            ConicGradient::new(UiPosition::CENTER, ring_stops(ring.style, a.shown * TAU, ring.ready))
                .with_start(0.0)
                .into(),
        ]);
    }
}

// ───────────────────────────── molten overdrive ─────────────────────────────

/// GPU layout of `MoltenParams` in `ui_molten.wesl`.
#[derive(Clone, Copy, Debug, Default, ShaderType, Reflect)]
pub struct MoltenParams {
    /// x fill 0..1, y time (s), z ready 0/1, w active 0/1.
    pub p: Vec4,
}

/// The Overdrive hex's molten fill (§11.5): the mask's shape filled bottom-up with the molten
/// ramp under a wavy meniscus, lacquer above.
#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct MoltenMaterial {
    #[uniform(0)]
    pub p: Vec4,
    #[texture(1)]
    #[sampler(2)]
    pub mask: Handle<Image>,
}

impl UiMaterial for MoltenMaterial {
    fn fragment_shader() -> ShaderRef {
        "embedded://gf_client/shaders/ui_molten.wesl".into()
    }
}

/// The Overdrive meter: `value` 0..1 (team charge), `ready` when full, `active` while it drains.
#[derive(Component, Clone, Debug)]
pub struct MoltenFill {
    pub value: f32,
    pub ready: bool,
    pub active: bool,
    pub material: Handle<MoltenMaterial>,
    pub emblem: Entity,
    pub glow: Entity,
    pub shown: f32,
}

fn molten_visuals(
    time: Res<Time>,
    settings: Option<Res<Settings>>,
    mut fills: Query<&mut MoltenFill>,
    mut materials: ResMut<Assets<MoltenMaterial>>,
    mut images: Query<&mut ImageNode>,
    mut tick: Local<f32>,
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
    *tick += dt;
    let frame30 = *tick >= 1.0 / 30.0;
    if frame30 {
        *tick = 0.0;
    }
    let calm = reduced(&settings);
    for mut f in &mut fills {
        let target = f.value.clamp(0.0, 1.0);
        let shown = target - (target - f.shown) * (-dt / 0.07).exp();
        let moved = (shown - f.shown).abs() > 1.0 / 200.0 || (shown != f.shown && (shown - target).abs() < 1e-3);
        f.shown = shown;
        if (moved || frame30)
            && let Some(mut m) = materials.get_mut(&f.material)
        {
            m.p = Vec4::new(f.shown, if calm { 0.0 } else { now }, f.ready as u8 as f32, f.active as u8 as f32);
        }
        if let Ok(mut e) = images.get_mut(f.emblem) {
            set_tint(&mut e, if f.ready || f.active { Color::WHITE } else { hx(0x2A1608) });
        }
        if let Ok(mut g) = images.get_mut(f.glow) {
            let alpha = if f.ready {
                if calm { 0.7 } else { 0.55 + 0.3 * (now * TAU / 1.6).sin() }
            } else if f.active {
                0.5
            } else {
                0.0
            };
            set_tint(&mut g, hx(0xFFC940).with_alpha(alpha));
        }
    }
}

// ───────────────────────────── plates and pips ─────────────────────────────

/// Armour plates: `value` in plates (fractional plates fill from the left).
#[derive(Component, Clone, Debug)]
pub struct KitPlates {
    pub value: f32,
    pub clips: Vec<Entity>,
    pub shown: f32,
}

fn plate_visuals(mut plates: Query<&mut KitPlates>, mut nodes: Query<&mut Node>) {
    for mut p in &mut plates {
        if (p.value - p.shown).abs() < 1e-3 {
            continue;
        }
        p.shown = p.value;
        for (i, clip) in p.clips.iter().enumerate() {
            if let Ok(mut n) = nodes.get_mut(*clip) {
                set_width_pct(&mut n, (p.value - i as f32).clamp(0.0, 1.0) * 100.0);
            }
        }
    }
}

/// Dash charges: `full` charges and the `refill` fraction of the next one.
#[derive(Component, Clone, Debug)]
pub struct KitPips {
    pub full: u32,
    pub refill: f32,
    pub clips: Vec<Entity>,
    pub pips: Vec<Entity>,
    pub shown: (u32, f32),
}

fn pip_visuals(
    mut commands: Commands,
    mut pips: Query<&mut KitPips>,
    mut nodes: Query<&mut Node>,
    settings: Option<Res<Settings>>,
) {
    let calm = reduced(&settings);
    for mut p in &mut pips {
        let now = (p.full, (p.refill * 100.0).round() / 100.0);
        if now == p.shown {
            continue;
        }
        let gained = p.shown.0 != u32::MAX && now.0 > p.shown.0;
        let before = p.shown.0;
        p.shown = now;
        for (i, clip) in p.clips.iter().enumerate() {
            let i = i as u32;
            let h = if i < p.full {
                1.0
            } else if i == p.full {
                p.refill.clamp(0.0, 1.0)
            } else {
                0.0
            };
            if let Ok(mut n) = nodes.get_mut(*clip) {
                let v = Val::Percent(h * 100.0);
                if n.height != v {
                    n.height = v;
                }
            }
        }
        // A pip that just filled pops 1.0 → 1.25 → 1.0 over 150 ms.
        if gained && !calm {
            for i in before..p.full {
                if let Some(&e) = p.pips.get(i as usize) {
                    commands.entity(e).insert(pop(0.25, 0.15));
                }
            }
        }
    }
}

// ───────────────────────────── tweens and pulses ─────────────────────────────

/// What a [`Tween`] animates.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TweenTarget {
    /// `UiTransform.scale`, uniform.
    Scale(f32, f32),
    /// `UiTransform.translation` in px.
    Translate(Vec2, Vec2),
    /// `UiTransform.rotation` in radians (clockwise).
    Rotate(f32, f32),
    /// The alpha of the node's `ImageNode`, `TextColor` or `BackgroundColor`.
    Alpha(f32, f32),
    /// A bump: scale 1 → 1 + amp → 1 (pops).
    Bump(f32),
}

/// Easing curves.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Ease {
    Linear,
    OutCubic,
    OutBack,
}

/// A one-shot animation on this entity (§11.6). Removed when done.
#[derive(Component, Clone, Copy, Debug)]
pub struct Tween {
    pub target: TweenTarget,
    pub dur: f32,
    pub delay: f32,
    pub ease: Ease,
    pub t: f32,
}

impl Tween {
    pub fn new(target: TweenTarget, dur: f32) -> Self {
        Self { target, dur, delay: 0.0, ease: Ease::OutCubic, t: 0.0 }
    }

    pub fn delay(mut self, s: f32) -> Self {
        self.delay = s;
        self
    }

    pub fn ease(mut self, e: Ease) -> Self {
        self.ease = e;
        self
    }
}

/// A pop: scale 1 → 1 + `amp` → 1 over `dur` seconds (needs a `UiTransform`).
pub fn pop(amp: f32, dur: f32) -> Tween {
    Tween::new(TweenTarget::Bump(amp), dur).ease(Ease::Linear)
}

#[allow(clippy::type_complexity)]
fn tweens(
    mut commands: Commands,
    time: Res<Time>,
    settings: Option<Res<Settings>>,
    mut q: Query<(
        Entity,
        &mut Tween,
        Option<&mut UiTransform>,
        Option<&mut ImageNode>,
        Option<&mut TextColor>,
        Option<&mut BackgroundColor>,
    )>,
) {
    let dt = time.delta_secs();
    let calm = reduced(&settings);
    for (e, mut tw, tf, img, txt, bg) in &mut q {
        tw.t += dt;
        let raw = ((tw.t - tw.delay) / tw.dur.max(1e-3)).clamp(0.0, 1.0);
        // Reduced motion keeps fades and jumps every movement to its end.
        let raw = if calm && !matches!(tw.target, TweenTarget::Alpha(..)) { 1.0 } else { raw };
        let k = match tw.ease {
            Ease::Linear => raw,
            Ease::OutCubic => ease_out_cubic(raw),
            Ease::OutBack => ease_out_back(raw),
        };
        match tw.target {
            TweenTarget::Scale(a, b) => {
                if let Some(mut tf) = tf {
                    tf.scale = Vec2::splat(a + (b - a) * k);
                }
            }
            TweenTarget::Bump(amp) => {
                if let Some(mut tf) = tf {
                    tf.scale = Vec2::splat(1.0 + amp * (PI * k).sin());
                }
            }
            TweenTarget::Translate(a, b) => {
                if let Some(mut tf) = tf {
                    let v = a + (b - a) * k;
                    tf.translation = Val2::px(v.x, v.y);
                }
            }
            TweenTarget::Rotate(a, b) => {
                if let Some(mut tf) = tf {
                    tf.rotation = Rot2::radians(a + (b - a) * k);
                }
            }
            TweenTarget::Alpha(a, b) => {
                let v = a + (b - a) * k;
                if let Some(mut i) = img {
                    i.color.set_alpha(v);
                }
                if let Some(mut t) = txt {
                    t.0.set_alpha(v);
                }
                if let Some(mut b) = bg {
                    b.0.set_alpha(v);
                }
            }
        }
        if raw >= 1.0 && tw.t >= tw.delay {
            commands.entity(e).remove::<Tween>();
        }
    }
}

/// What a [`Pulse`] breathes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PulseTarget {
    /// The alpha of the first `BoxShadow` (glows).
    Shadow,
    /// The alpha of the `ImageNode` tint.
    Image,
    /// The alpha of the `TextColor`.
    Text,
}

/// A breathing alpha between `lo` and `hi` at `hz` (§10). While `on` is false the target sits
/// at alpha 0 (hidden glow). Reduced motion holds the midpoint.
#[derive(Component, Clone, Copy, Debug)]
pub struct Pulse {
    pub hz: f32,
    pub lo: f32,
    pub hi: f32,
    pub target: PulseTarget,
    pub on: bool,
    pub phase: f32,
}

impl Pulse {
    pub fn shadow(hz: f32, lo: f32, hi: f32) -> Self {
        Self { hz, lo, hi, target: PulseTarget::Shadow, on: true, phase: 0.0 }
    }

    pub fn image(hz: f32, lo: f32, hi: f32) -> Self {
        Self { target: PulseTarget::Image, ..Self::shadow(hz, lo, hi) }
    }

    pub fn text(hz: f32, lo: f32, hi: f32) -> Self {
        Self { target: PulseTarget::Text, ..Self::shadow(hz, lo, hi) }
    }

    /// Start switched off (alpha 0 until `on`).
    pub fn off(mut self) -> Self {
        self.on = false;
        self
    }
}

fn pulses(
    time: Res<Time>,
    settings: Option<Res<Settings>>,
    mut q: Query<(&Pulse, Option<&mut BoxShadow>, Option<&mut ImageNode>, Option<&mut TextColor>)>,
) {
    let now = time.elapsed_secs();
    let calm = reduced(&settings);
    for (p, shadow, img, txt) in &mut q {
        let a = if !p.on {
            0.0
        } else if calm {
            (p.lo + p.hi) * 0.5
        } else {
            p.lo + (p.hi - p.lo) * (0.5 + 0.5 * (now * TAU * p.hz + p.phase).sin())
        };
        match p.target {
            PulseTarget::Shadow => {
                if let Some(mut s) = shadow
                    && let Some(first) = s.0.first_mut()
                    && (first.color.alpha() - a).abs() > 0.004
                {
                    first.color.set_alpha(a);
                }
            }
            PulseTarget::Image => {
                if let Some(mut i) = img
                    && (i.color.alpha() - a).abs() > 0.004
                {
                    i.color.set_alpha(a);
                }
            }
            PulseTarget::Text => {
                if let Some(mut t) = txt
                    && (t.0.alpha() - a).abs() > 0.004
                {
                    t.0.set_alpha(a);
                }
            }
        }
    }
}

/// Pin parts: rotate `frame` (`UiTransform.rotation`, radians clockwise from up) to aim the nub.
#[derive(Component, Clone, Copy, Debug)]
pub struct PinParts {
    pub frame: Entity,
}
