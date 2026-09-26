//! # Panels (UI_STYLE §7): the Forge drawer, the boon spread, the end of the run, help, the door
//! panel and tooltips, all built from the kit ([`crate::uikit`]).
//!
//! * Every button carries a [`UiAction`]; one global `On<Activate>` observer turns clicks, pad
//!   presses and keys into the same reliable `PlayerAction`s the bots send.
//! * The Forge previews run `gf_core::forge::apply_action` on a copy of the build (the function the
//!   host applies), so what the drawer promises is what the anvil does.
//! * Panels rebuild only when their content changes; hover, selection, the heat ring and the
//!   camera framing update in place (§7.1 "Behaviour fix", §11.10).
//! * [`PanelState`], [`BoonSpread`] and [`PanelFraming`] are public so the HUD can hide the
//!   Tracker, the Arsenal and the boon chip under a panel and the camera can ease aside.
//!
//! | Module | Panel |
//! |---|---|
//! | [`forge`] | the Forge drawer at a Hot anvil (Tab) |
//! | [`boons`] | the boon spread (Tab from the chip, or on its own when the hero is safe) |
//! | [`end`] | victory and defeat |
//! | [`help`] | the help tome (H) |
//! | [`doors`] | the legacy door panel (`--room`, boss transitions) |
//! | [`tips`] | hover tooltips |
//! | [`qa`] | `--ui-shot forge|boon|end|defeat|help|doors`: sample data for screenshots |

mod boons;
mod doors;
mod end;
mod forge;
mod help;
mod qa;
mod tips;

pub use boons::BoonSpread;
pub use forge::{BagFilter, ForgeSelection};
pub use tips::Tip;

use crate::input::{Device, InputState, Settings};
use crate::net::{Link, Prediction, start_link};
use crate::palette::element_color;
use crate::scene::SceneIndex;
use crate::theme::{HudScale, Ty};
use crate::{ClientConfig, ClientSet, Connect};
use gf_core::damage::DamageType;
use gf_core::forge::ForgeAction;
use gf_engine::client::{Activate, Hovered, InputFocus, InteractionDisabled, UiButton};
use gf_engine::prelude::*;
use gf_net::*;
use std::hash::{DefaultHasher, Hash, Hasher};

// ───────────────────────────── shared state ─────────────────────────────

/// Which panels are open this frame. The HUD hides the Tracker, the Arsenal and the boon chip
/// under the Forge drawer and the Tracker under the boon spread (§7.1, §7.2).
#[derive(Resource, Default, Clone, Copy, Debug, PartialEq, Eq)]
pub struct PanelState {
    pub forge: bool,
    pub boons: bool,
    pub doors: bool,
    pub end: bool,
    pub help: bool,
}

impl PanelState {
    /// A panel that owns the pad (D-pad focus, South to activate, §7.6).
    pub fn captures_pad(&self) -> bool {
        self.forge || self.boons || self.end || self.help || self.doors
    }

    /// A panel that owns the view (the Forge, the boon spread, the end screen, the help tome):
    /// edge pins, the callout lane and the region banner wait until it closes.
    pub fn covers_view(&self) -> bool {
        self.forge || self.boons || self.end || self.help
    }
}

/// PanelFraming (§7.1, §7.2): the camera's look offset while a panel is open, in fractions of the
/// window height. `x > 0` moves the view right, so the hero sits left of centre (the Forge);
/// `y > 0` moves the hero down (the boon spread). Eased over 350 ms (cubic out); `camera.rs` adds
/// `current` to its target.
#[derive(Resource, Default, Clone, Copy, Debug)]
pub struct PanelFraming {
    pub target: Vec2,
    pub current: Vec2,
    from: Vec2,
    t: f32,
}

/// What a button does.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub enum UiAction {
    /// A reliable player action, sent as is (boon picks, door choices).
    Player(PlayerAction),
    /// A Forge action. With `confirm`, the first press arms the button and the second one sends
    /// it (fuse, reroll, salvage of Rare or better; §7.1).
    Forge {
        action: ForgeAction,
        confirm: bool,
    },
    /// Select a bag card (it drives the detail pane and the preview).
    SelectPart(u32),
    /// A bag filter chip.
    Filter(BagFilter),
    CloseForge,
    /// Close the boon spread; the offer waits on the chip.
    BoonLater,
    Restart,
    Quit,
    /// A help footer switch.
    Toggle(help::Switch),
    CloseHelp,
}

/// Focusable with the pad's D-pad while its panel is on top (§7.6).
#[derive(Component, Clone, Copy, Debug, PartialEq, Eq)]
pub struct Nav(pub PanelKind);

/// The panels, top-most last.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum PanelKind {
    Doors,
    Forge,
    Boons,
    End,
    Help,
}

/// A panel surface that swallows the pointer: hovering it stops the weapon from firing.
#[derive(Component)]
struct CapturesPointer;

/// A fixed-size panel canvas scaled down to fit small windows. `pivot` (−0.5..0.5 from the
/// centre) is the point that stays put; `pad` is the total margin kept free on each axis.
#[derive(Component, Clone, Copy, Debug)]
struct Fit {
    size: Vec2,
    pivot: Vec2,
    pad: Vec2,
}

/// A number that counts up to its value (DPS 400 ms, end stats 0.8 s; §10).
#[derive(Component, Clone, Copy, Debug)]
struct CountUp {
    from: f64,
    to: f64,
    t: f32,
    dur: f32,
    delay: f32,
    fmt: NumFmt,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NumFmt {
    /// `1,284`
    Thousands,
    /// `+312`
    Signed,
    /// `64%`
    Percent,
    /// `21:48`
    Clock,
}

impl NumFmt {
    fn format(self, v: f64) -> String {
        match self {
            NumFmt::Thousands => thousands(v.round() as u64),
            NumFmt::Signed => format!("+{}", thousands(v.round().max(0.0) as u64)),
            NumFmt::Percent => format!("{:.0}%", v),
            NumFmt::Clock => clock(v as f32),
        }
    }
}

#[derive(Resource, Default)]
struct UiRequests {
    restart: bool,
    quit: bool,
}

/// The world the panels show: the live snapshot, or the QA sample under `--ui-shot`.
#[derive(Resource, Default)]
pub(crate) struct PanelWorld {
    qa: Option<WorldSnapshot>,
    shot: qa::Shot,
}

impl PanelWorld {
    fn get<'a>(&'a self, link: &'a Link) -> Option<&'a WorldSnapshot> {
        self.qa.as_ref().or(link.latest.as_deref())
    }
}

fn me_in(w: &WorldSnapshot, slot: Option<u8>) -> Option<&PlayerView> {
    let slot = slot?;
    w.players.iter().find(|p| p.slot == slot)
}

pub fn build(app: &mut App) {
    app.init_resource::<UiRequests>()
        .init_resource::<PanelState>()
        .init_resource::<PanelFraming>()
        .init_resource::<PanelWorld>()
        .init_resource::<InputFocus>()
        .add_observer(on_activate)
        .add_systems(
            Update,
            (qa::fill, update_state, boons::auto_open, panel_keys, pad_nav, ui_capture).chain().in_set(ClientSet::Net),
        )
        .add_systems(
            Update,
            (
                forge::sync,
                boons::sync,
                doors::sync,
                end::sync,
                help::sync,
                tips::sync,
                (framing, fit_panels, count_up),
                apply_requests,
            )
                .chain()
                .in_set(ClientSet::Presentation),
        );
    forge::build(app);
    boons::build(app);
    qa::build(app);
}

// ───────────────────────────── state, keys, focus ─────────────────────────────

fn update_state(
    link: Res<Link>,
    pw: Res<PanelWorld>,
    input: Res<InputState>,
    settings: Res<Settings>,
    spread: Res<BoonSpread>,
    mut state: ResMut<PanelState>,
    mut focus: ResMut<crate::hud::HudFocus>,
) {
    let w = pw.get(&link);
    let end = w.is_some_and(|w| matches!(w.run.phase, RunPhase::Victory | RunPhase::Defeat));
    let next = PanelState {
        forge: !end && forge::is_open(&pw, &input, w),
        boons: !end && spread.open && w.is_some_and(|w| !w.private.boon_offer.is_empty()),
        doors: !end && w.is_some_and(doors::has_doors),
        end,
        help: settings.help,
    };
    if *state != next {
        *state = next;
    }
    // The HUD steps aside under the Forge drawer and the boon spread (§7.1, §7.2).
    if focus.forge_drawer != next.forge || focus.boon_spread != next.boons {
        focus.forge_drawer = next.forge;
        focus.boon_spread = next.boons;
    }
}

/// Panel keys (§7.6): Tab / View opens the pending choice (the Forge at a hot anvil, else the
/// boon spread) and closes it; Esc closes; 1–4 pick a boon; X / West rerolls; Enter / Esc on the
/// end screen. While a panel is up it owns the pad's D-pad and South / West.
#[allow(clippy::too_many_arguments)]
fn panel_keys(
    keys: Res<ButtonInput<KeyCode>>,
    pads: Query<&Gamepad>,
    link: Res<Link>,
    pw: Res<PanelWorld>,
    state: Res<PanelState>,
    mut input: ResMut<InputState>,
    mut spread: ResMut<BoonSpread>,
    mut settings: ResMut<Settings>,
    mut req: ResMut<UiRequests>,
) {
    let w = pw.get(&link);
    let at_anvil = w.is_some_and(|w| w.private.at_anvil);
    let offers = w.map_or(0, |w| w.private.boon_offer.len());
    let rerolls = w.map_or(0, |w| w.private.boon_rerolls);
    let pad = |b: GamepadButton| pads.iter().any(|p| p.just_pressed(b));
    let tab = keys.just_pressed(KeyCode::Tab) || pad(GamepadButton::Select);
    let esc = keys.just_pressed(KeyCode::Escape);

    if state.end {
        if keys.just_pressed(KeyCode::Enter) || keys.just_pressed(KeyCode::NumpadEnter) {
            req.restart = true;
        } else if esc {
            req.quit = true;
        }
    } else if esc && settings.help {
        settings.help = false;
    } else if tab || esc {
        if input.forge_open {
            input.forge_open = false;
        } else if spread.open {
            spread.later(w);
        } else if tab && at_anvil {
            input.forge_open = true;
        } else if tab && offers > 0 {
            spread.open = true;
        }
    }
    if !at_anvil {
        input.forge_open = false;
    }
    if state.boons && spread.open {
        for (i, k) in [KeyCode::Digit1, KeyCode::Digit2, KeyCode::Digit3, KeyCode::Digit4].into_iter().enumerate() {
            if keys.just_pressed(k) && i < offers {
                input.actions.push(PlayerAction::PickBoon(i as u8));
            }
        }
        if (keys.just_pressed(KeyCode::KeyX) || pad(GamepadButton::West)) && rerolls > 0 {
            input.actions.push(PlayerAction::RerollBoons);
        }
    }
    let capture = state.captures_pad();
    if input.panel_pad_capture != capture {
        input.panel_pad_capture = capture;
    }
}

/// Pad focus (§7.6): the D-pad walks the focusable buttons of the top panel by screen position,
/// South activates the focused one. The kit draws pad focus as hover. Keyboard and mouse clear
/// it, so Space and Enter never press a panel button by accident.
#[allow(clippy::too_many_arguments)]
fn pad_nav(
    mut commands: Commands,
    pads: Query<&Gamepad>,
    input: Res<InputState>,
    state: Res<PanelState>,
    navs: Query<(Entity, &Nav, &UiGlobalTransform, &ComputedNode, &InheritedVisibility, Has<InteractionDisabled>)>,
    mut focus: ResMut<InputFocus>,
) {
    let top = [
        (state.help, PanelKind::Help),
        (state.end, PanelKind::End),
        (state.boons, PanelKind::Boons),
        (state.forge, PanelKind::Forge),
        (state.doors, PanelKind::Doors),
    ]
    .into_iter()
    .find_map(|(open, k)| open.then_some(k));
    let (Some(top), Device::Gamepad) = (top, input.device) else {
        if focus.get().is_some() {
            focus.clear();
        }
        return;
    };
    let items: Vec<(Entity, Vec2, bool)> = navs
        .iter()
        .filter(|(_, n, _, node, vis, _)| n.0 == top && vis.get() && node.size().x > 0.0)
        .map(|(e, _, tf, _, _, disabled)| (e, tf.translation, disabled))
        .collect();
    if items.is_empty() {
        return;
    }
    let current = focus.get().and_then(|f| items.iter().find(|(e, ..)| *e == f).copied());
    let Some((cur, at, disabled)) = current else {
        // First focus: the middle item of the panel's first row (the middle boon card, EQUIP).
        let mut sorted = items.clone();
        sorted.sort_by(|a, b| (a.1.y, a.1.x).partial_cmp(&(b.1.y, b.1.x)).unwrap_or(std::cmp::Ordering::Equal));
        let first_row: Vec<_> = sorted.iter().filter(|i| (i.1.y - sorted[0].1.y).abs() < 20.0).collect();
        *focus = InputFocus::from_entity(first_row[first_row.len() / 2].0);
        return;
    };
    let pad = |b: GamepadButton| pads.iter().any(|p| p.just_pressed(b));
    let dir = if pad(GamepadButton::DPadUp) {
        Some(Vec2::NEG_Y)
    } else if pad(GamepadButton::DPadDown) {
        Some(Vec2::Y)
    } else if pad(GamepadButton::DPadLeft) {
        Some(Vec2::NEG_X)
    } else if pad(GamepadButton::DPadRight) {
        Some(Vec2::X)
    } else {
        None
    };
    if let Some(d) = dir {
        // The nearest item in the pressed direction, favouring those straight ahead.
        let best = items
            .iter()
            .filter(|(e, ..)| *e != cur)
            .filter_map(|(e, p, _)| {
                let v = *p - at;
                let ahead = v.dot(d);
                (ahead > 4.0).then(|| (*e, ahead + (v - d * ahead).length() * 2.5))
            })
            .min_by(|a, b| a.1.total_cmp(&b.1));
        if let Some((e, _)) = best {
            *focus = InputFocus::from_entity(e);
        }
    }
    if pad(GamepadButton::South) && !disabled {
        commands.trigger(Activate { entity: cur });
    }
}

/// Hovering a button or a panel surface stops the weapon from firing.
fn ui_capture(
    buttons: Query<&Hovered, With<UiButton>>,
    surfaces: Query<&Hovered, With<CapturesPointer>>,
    mut input: ResMut<InputState>,
) {
    let capture = buttons.iter().chain(surfaces.iter()).any(|h| h.get());
    if input.ui_captures != capture {
        input.ui_captures = capture;
    }
}

#[allow(clippy::too_many_arguments)]
fn on_activate(
    ev: On<Activate>,
    actions: Query<&UiAction>,
    disabled: Query<(), With<InteractionDisabled>>,
    time: Res<Time>,
    mut input: ResMut<InputState>,
    mut req: ResMut<UiRequests>,
    mut sel: ResMut<ForgeSelection>,
    mut spread: ResMut<BoonSpread>,
    mut settings: ResMut<Settings>,
    mut hud_scale: ResMut<HudScale>,
    link: Res<Link>,
    pw: Res<PanelWorld>,
) {
    let Ok(action) = actions.get(ev.entity) else { return };
    if disabled.contains(ev.entity) {
        return;
    }
    match *action {
        UiAction::Player(a) => input.actions.push(a),
        UiAction::Forge { action, confirm } => {
            if confirm && sel.armed != Some(action) {
                sel.arm(action, time.elapsed_secs());
            } else {
                sel.disarm();
                input.actions.push(PlayerAction::Forge(action));
            }
        }
        UiAction::SelectPart(uid) => {
            if sel.selected != Some(uid) {
                sel.selected = Some(uid);
                sel.disarm();
            }
        }
        UiAction::Filter(f) => {
            sel.filter = f;
            sel.disarm();
        }
        UiAction::CloseForge => input.forge_open = false,
        UiAction::BoonLater => spread.later(pw.get(&link)),
        UiAction::Restart => req.restart = true,
        UiAction::Quit => req.quit = true,
        UiAction::Toggle(s) => help::toggle(s, &mut settings, &mut hud_scale),
        UiAction::CloseHelp => settings.help = false,
    }
}

// ───────────────────────────── motion helpers ─────────────────────────────

/// Ease the camera framing toward the open panel's offset (§7.1: 420 px right for the Forge,
/// §7.2: 200 px down for the boon spread; 350 ms, cubic out).
fn framing(time: Res<Time>, state: Res<PanelState>, mut f: ResMut<PanelFraming>) {
    let target = if state.end {
        Vec2::ZERO
    } else if state.forge {
        Vec2::new(420.0 / 1080.0, 0.0)
    } else if state.boons {
        Vec2::new(0.0, 200.0 / 1080.0)
    } else {
        Vec2::ZERO
    };
    if f.target != target {
        f.from = f.current;
        f.target = target;
        f.t = 0.0;
    }
    if f.t < 1.0 {
        f.t = (f.t + time.delta_secs() / 0.35).min(1.0);
        let k = 1.0 - (1.0 - f.t).powi(3);
        f.current = f.from + (f.target - f.from) * k;
    }
}

/// Scale fixed-size canvases down to fit the window (logical px after UiScale).
fn fit_panels(
    windows: Query<&Window, With<gf_engine::client::PrimaryWindow>>,
    scale: Res<UiScale>,
    mut q: Query<(&Fit, &mut UiTransform)>,
) {
    let Ok(w) = windows.single() else { return };
    let logical = Vec2::new(w.width(), w.height()) / scale.0.max(0.01);
    for (fit, mut tf) in &mut q {
        let k = ((logical.x - fit.pad.x) / fit.size.x).min((logical.y - fit.pad.y) / fit.size.y).clamp(0.3, 1.0);
        let shift = fit.pivot * fit.size * (1.0 - k);
        let translation = Val2::px(shift.x, shift.y);
        if (tf.scale.x - k).abs() > 1e-3 || tf.translation != translation {
            tf.scale = Vec2::splat(k);
            tf.translation = translation;
        }
    }
}

fn count_up(
    mut commands: Commands,
    time: Res<Time>,
    settings: Res<Settings>,
    mut q: Query<(Entity, &mut CountUp, &mut Text)>,
) {
    for (e, mut c, mut text) in &mut q {
        c.t += time.delta_secs();
        let raw = if settings.reduced_motion { 1.0 } else { ((c.t - c.delay) / c.dur.max(1e-3)).clamp(0.0, 1.0) };
        let k = 1.0 - (1.0 - raw as f64).powi(3);
        let s = c.fmt.format(c.from + (c.to - c.from) * k);
        if text.0 != s {
            text.0 = s;
        }
        if raw >= 1.0 {
            commands.entity(e).remove::<CountUp>();
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn apply_requests(
    mut commands: Commands,
    mut req: ResMut<UiRequests>,
    mut cfg: ResMut<ClientConfig>,
    mut link: ResMut<Link>,
    mut pred: ResMut<Prediction>,
    mut index: ResMut<SceneIndex>,
    mut sel: ResMut<ForgeSelection>,
    mut exits: MessageWriter<AppExit>,
) {
    if req.quit {
        req.quit = false;
        exits.write(AppExit::Success);
    }
    if req.restart {
        req.restart = false;
        // A fresh run: new seed on our own host; a joined client simply reconnects.
        if let Connect::Local(sim) | Connect::Host(sim, _) = &mut cfg.connect {
            sim.seed = sim.seed.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
        }
        link.shutdown();
        *link = start_link(&cfg);
        *pred = Prediction::default();
        index.reset(&mut commands);
        *sel = ForgeSelection::default();
    }
}

// ───────────────────────────── shared helpers ─────────────────────────────

fn key_of(parts: impl Hash) -> u64 {
    // Callers hash a `format!("{:?}")` of the content they show.
    let mut h = DefaultHasher::new();
    parts.hash(&mut h);
    h.finish()
}

/// `1284` → `1,284`.
pub(crate) fn thousands(n: u64) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, c) in s.chars().enumerate() {
        if i > 0 && (s.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(c);
    }
    out
}

/// Seconds → `21:48` (or `1:02:03`).
pub(crate) fn clock(secs: f32) -> String {
    let s = secs.max(0.0) as u32;
    if s >= 3600 {
        format!("{}:{:02}:{:02}", s / 3600, s / 60 % 60, s % 60)
    } else {
        format!("{}:{:02}", s / 60, s % 60)
    }
}

/// A full-window root node for a panel layer at `z`.
fn layer(z: i32) -> impl Bundle {
    (
        Node {
            position_type: PositionType::Absolute,
            left: px(0.0),
            top: px(0.0),
            width: percent(100.0),
            height: percent(100.0),
            ..default()
        },
        GlobalZIndex(z),
        gf_engine::client::Pickable::IGNORE,
    )
}

/// The element a rules-text keyword names (status keywords count as their element, §3.4).
fn keyword_element(word: &str) -> Option<Option<DamageType>> {
    let w = word.to_ascii_lowercase();
    let starts = |p: &[&str]| p.iter().any(|k| w.starts_with(k));
    Some(if starts(&["burn", "flame", "ignite", "scorch"]) {
        Some(DamageType::Flame)
    } else if starts(&["shock", "storm", "lightning"]) {
        Some(DamageType::Storm)
    } else if starts(&["curse", "void"]) {
        Some(DamageType::Void)
    } else if starts(&["bleed", "kinetic"]) {
        Some(DamageType::Kinetic)
    } else if starts(&["plague", "poison", "blight"]) {
        Some(DamageType::Plague)
    } else if starts(&["radiant", "smite"]) {
        Some(DamageType::Radiant)
    } else if starts(&["doom", "root", "mark", "execute", "crit"]) {
        None
    } else {
        return None;
    })
}

/// Rules text as rich spans (§7.2): numbers in `ichor`, element and status keywords in their hue,
/// other keywords bold, the rest `base`. Punctuation stays glued to its word.
fn rules_spans(text: &str, base: Color) -> Vec<(Ty, String, Color)> {
    use crate::theme::tok;
    let mut out: Vec<(Ty, String, Color)> = Vec::new();
    let push = |out: &mut Vec<(Ty, String, Color)>, ty: Ty, s: &str, c: Color| {
        if let Some(last) = out.last_mut()
            && last.0 == ty
            && last.2 == c
        {
            last.1.push_str(s);
            return;
        }
        out.push((ty, s.to_string(), c));
    };
    for (i, word) in text.split(' ').enumerate() {
        if i > 0 {
            push(&mut out, Ty::Body, " ", base);
        }
        let lead = word.len() - word.trim_start_matches(['(', '"']).len();
        let core_end = word.trim_end_matches([',', '.', ';', ':', '!', '?', ')', '"']).len().max(lead);
        let (pre, core, post) = (&word[..lead], &word[lead..core_end], &word[core_end..]);
        push(&mut out, Ty::Body, pre, base);
        if core.chars().any(|c| c.is_ascii_digit()) {
            push(&mut out, Ty::Strong, core, tok::ICHOR);
        } else if let Some(el) = keyword_element(core) {
            let c = el.map_or(tok::PARCH, element_color);
            push(&mut out, Ty::Strong, core, c);
        } else {
            push(&mut out, Ty::Body, core, base);
        }
        push(&mut out, Ty::Body, post, base);
    }
    out.retain(|s| !s.1.is_empty());
    out
}

/// Spawn [`rules_spans`] as one wrapped rich text.
fn rules_text(
    p: &mut ChildSpawnerCommands,
    kit: &crate::uikit::UiKit,
    size: f32,
    text: &str,
    base: Color,
    max_width: f32,
    justify: Justify,
) -> Entity {
    let spans = rules_spans(text, base);
    let refs: Vec<(Ty, &str, Color)> = spans.iter().map(|(t, s, c)| (*t, s.as_str(), *c)).collect();
    crate::uikit::rich(p, kit, size, &refs, Some(max_width), justify)
}

/// A god's text colour: the secondary for the red gods, so red never sits beside white (§3.4).
fn god_text_color(key: &str, primary: Color, secondary: Color) -> Color {
    if matches!(key, "pyra" | "umbra_rex") { secondary } else { primary }
}
