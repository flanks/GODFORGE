//! The Forge drawer (UI_STYLE §7.1): Tab at a Hot anvil.
//!
//! The drawer rebuilds only when the build, the bag, the wallet, the selection, the filter or an
//! armed confirmation changes. Hovering a bag card rebuilds just the three live sections (the DPS
//! preview, the recipe hint and the detail pane) and moves the REPLACE target in place; the heat
//! ring, the seconds and the sub-line tick in place every frame.

use super::{
    CapturesPointer, CountUp, Fit, Nav, NumFmt, PanelKind, PanelState, PanelWorld, Tip, UiAction, key_of, layer, me_in,
    rules_text, thousands,
};
use crate::ClientConfig;
use crate::input::{Device, InputState};
use crate::net::Link;
use crate::palette::{element_color, rarity_color};
use crate::theme::{Ty, hx, tok, z};
use crate::uikit::{
    ButtonKind, Gem, Key, KitRing, PanelStyle, PillKind, RingStyle, SlotShape, SlotSpec, Tween, TweenTarget, UiKit,
    abs, button, centered_at, chip, dashed_plate, delta_chip, delta_chip_in, ember_knot, fill, gilt_card, gilt_panel,
    gradient_text, halo, icon, ik, key_chip, pill, pop, quiet_plate, rarity_gem, ring_meter, row, slot,
};
use gf_content::ContentDb;
use gf_core::damage::DamageType;
use gf_core::forge::{
    ForgeAction, ForgeError, ForgeOutcome, ForgeWallet, Ingredient, PartBag, PartCatalog, PartInstance, Slot,
    WeaponBuild, apply_action, recipe_satisfied,
};
use gf_core::ids::PartId;
use gf_core::modifier::Modifier;
use gf_core::rarity::Rarity;
use gf_core::weapon::{DpsEnv, WeaponProfile, compile, describe, estimate_dps};
use gf_engine::client::{Hovered, InputFocus, InteractionDisabled, Pickable, UiButton};
use gf_engine::prelude::*;
use gf_net::{AnvilState, GameEvent, PlayerView, WorldSnapshot};
use std::f32::consts::{PI, TAU};

/// The drawer (§7.1): x 1008–1896, y 64–1040 at 1920×1080.
const W: f32 = 888.0;
const H: f32 = 976.0;

/// Which bag parts the grid shows.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum BagFilter {
    #[default]
    All,
    Core,
    Mech,
    Relic,
}

impl BagFilter {
    const ALL: [BagFilter; 4] = [BagFilter::All, BagFilter::Core, BagFilter::Mech, BagFilter::Relic];

    fn label(self) -> &'static str {
        match self {
            BagFilter::All => "All",
            BagFilter::Core => "Core",
            BagFilter::Mech => "Mech",
            BagFilter::Relic => "Relic",
        }
    }

    fn admits(self, slot: Option<Slot>) -> bool {
        match self {
            BagFilter::All => true,
            BagFilter::Core => slot == Some(Slot::Core),
            BagFilter::Mech => slot == Some(Slot::Mechanism),
            BagFilter::Relic => slot == Some(Slot::Relic),
        }
    }
}

/// The drawer's selection and its transient feedback (§7.1 "ForgeSelection").
#[derive(Resource, Default, Debug)]
pub struct ForgeSelection {
    /// The selected bag part (its uid).
    pub selected: Option<u32>,
    pub filter: BagFilter,
    /// A fuse, reroll or salvage waiting for its confirming second press.
    pub armed: Option<ForgeAction>,
    armed_at: f32,
    /// The host's last refusal, shown in the pane, and when it arrived.
    error: Option<(String, f32)>,
    /// A socket that just changed, flared on the next rebuild.
    flare: Option<(Slot, f32)>,
    /// When a salvage paid out (the shards number pops).
    shards_at: f32,
}

impl ForgeSelection {
    pub fn arm(&mut self, action: ForgeAction, now: f32) {
        self.armed = Some(action);
        self.armed_at = now;
    }

    pub fn disarm(&mut self) {
        self.armed = None;
    }
}

/// Entities the drawer updates in place.
#[derive(Default, Clone)]
struct Ids {
    heat_ring: Option<Entity>,
    heat_text: Option<Entity>,
    sub: Option<Entity>,
    sockets: [Option<Entity>; 4],
    replace: [Option<Entity>; 4],
    bag: Vec<(u32, Entity)>,
    dps: Option<Entity>,
    recipe: Option<Entity>,
    detail: Option<Entity>,
}

#[derive(Resource, Default)]
pub(super) struct ForgeUi {
    root: Option<Entity>,
    key: u64,
    focus_key: u64,
    ids: Ids,
    /// The DPS the numeral last showed (it counts up from here, §10).
    dps_shown: f32,
}

/// A bag card's part uid.
#[derive(Component, Clone, Copy)]
pub(super) struct BagCard(u32);

/// The error shake: 2 px × 3 over 180 ms (§7.1).
#[derive(Component)]
struct PaneShake(f32);

pub(super) fn build(app: &mut App) {
    app.init_resource::<ForgeSelection>().init_resource::<ForgeUi>().add_systems(Update, shake_panes);
}

/// The drawer is open: the player asked for it at a hot anvil (or `--ui-shot forge`).
pub(super) fn is_open(pw: &PanelWorld, input: &InputState, w: Option<&WorldSnapshot>) -> bool {
    pw.shot == super::qa::Shot::Forge || (input.forge_open && w.is_some_and(|w| w.private.at_anvil))
}

// ───────────────────────────── the forge maths ─────────────────────────────

/// Content-backed catalog for previews (a reroll is random, so it previews nothing).
struct PreviewCatalog<'a>(&'a ContentDb);

impl PartCatalog for PreviewCatalog<'_> {
    fn slot_of(&self, part: PartId) -> Option<Slot> {
        self.0.part_slot(part)
    }
    fn reroll_pick(&mut self, _slot: Slot, _exclude: PartId) -> Option<PartId> {
        None
    }
    fn salvage_value(&self, rarity: Rarity) -> u32 {
        self.0.game.rarity.salvage_shards[rarity.index()]
    }
}

fn profile(db: &ContentDb, build: &WeaponBuild) -> WeaponProfile {
    let chassis = db.chassis_def(build.chassis);
    let mut mods = chassis.mods.clone();
    for (_, part) in build.equipped() {
        mods.extend(db.part_mods(part.part, part.rarity));
    }
    compile(&chassis.stats, &mods)
}

fn build_dps(db: &ContentDb, build: &WeaponBuild) -> f32 {
    let env = DpsEnv { status: db.game.status.clone(), ..default() };
    estimate_dps(&profile(db, build), &env).single_target
}

/// Preview an anvil action on copies: the new DPS and build, or the error the host would return.
fn preview(
    db: &ContentDb,
    action: ForgeAction,
    build: &WeaponBuild,
    bag: &PartBag,
    wallet: &ForgeWallet,
) -> Result<(f32, WeaponBuild), ForgeError> {
    let (mut b, mut g, mut w) = (build.clone(), bag.clone(), *wallet);
    let mut uid = 0;
    apply_action(action, &mut b, &mut g, &mut w, &db.game.forge, &mut PreviewCatalog(db), &mut uid)?;
    Ok((build_dps(db, &b), b))
}

fn pct(before: f32, after: f32) -> f32 {
    (after / before.max(1e-3) - 1.0) * 100.0
}

/// The short refusal shown on a disabled button (§7.1: `no twin`, `too weak`).
fn short_reason(e: &ForgeError) -> String {
    match e {
        ForgeError::NotInBag => "gone".into(),
        ForgeError::NotAtAnvil => "no anvil".into(),
        ForgeError::SlotLocked(_) => "locked".into(),
        ForgeError::EmptySlot(_) => "no twin".into(),
        ForgeError::SlotMismatch { .. } => "wrong slot".into(),
        ForgeError::MaxRarity => "at its peak".into(),
        ForgeError::DonorTooWeak => "too weak".into(),
        ForgeError::NoCharges => "no charges".into(),
        ForgeError::NotEnoughShards { need, .. } => format!("need {need}"),
        ForgeError::BagFull => "bag full".into(),
        ForgeError::NoCandidates => "no candidates".into(),
    }
}

/// The long refusal for tooltips and the pane.
fn long_reason(e: &ForgeError) -> String {
    match e {
        ForgeError::EmptySlot(s) => format!("Nothing is equipped in the {} slot to fuse into.", s.name()),
        ForgeError::DonorTooWeak => "This part is too weak to raise the equipped part's rarity.".into(),
        ForgeError::MaxRarity => "The equipped part is already Godforged.".into(),
        ForgeError::NoCharges => "No forge charges left at this anvil.".into(),
        ForgeError::NotEnoughShards { need, have } => format!("Needs {need} godshards; you carry {have}."),
        ForgeError::SlotLocked(s) => format!("The {} slot is locked during a run.", s.name()),
        e => {
            let s = e.to_string();
            let mut c = s.chars();
            c.next().map_or(s.clone(), |f| f.to_uppercase().collect::<String>() + c.as_str()) + "."
        }
    }
}

/// Recipes a build satisfies, by row id.
fn satisfied(db: &ContentDb, build: &WeaponBuild) -> Vec<u16> {
    let element = profile(db, build).element;
    db.recipe_ingredients
        .iter()
        .enumerate()
        .filter(|(_, ings)| recipe_satisfied(ings, build, element))
        .map(|(i, _)| i as u16)
        .collect()
}

fn has_ingredient(ing: &Ingredient, build: &WeaponBuild, element: DamageType) -> bool {
    match *ing {
        Ingredient::Chassis(c) => build.chassis == c,
        Ingredient::Part(p) => build.slots.iter().flatten().any(|s| s.part == p),
        Ingredient::Element(e) => element == e,
    }
}

/// A recipe's bonus in words: `+1 chain, +10% damage`.
fn bonus_words(mods: &[Modifier]) -> String {
    let p = |m: f32| ((m - 1.0) * 100.0).round();
    let words: Vec<String> = mods
        .iter()
        .filter_map(|m| match *m {
            Modifier::Damage(x) => Some(format!("{:+.0}% damage", p(x))),
            Modifier::FireRate(x) => Some(format!("{:+.0}% fire rate", p(x))),
            Modifier::Area(x) => Some(format!("{:+.0}% area", p(x))),
            Modifier::Knockback(x) => Some(format!("{:+.0}% knockback", p(x))),
            Modifier::CritChance(x) => Some(format!("+{:.0}% crit", x * 100.0)),
            Modifier::CritDamage(x) => Some(format!("+{:.0}% crit damage", x * 100.0)),
            Modifier::Projectiles(n) => Some(format!("+{n} projectiles")),
            Modifier::Pierce(n) => Some(format!("+{n} pierce")),
            Modifier::Chain { jumps, .. } => Some(format!("+{jumps} chain")),
            Modifier::Ricochet { bounces, .. } => Some(format!("+{bounces} ricochet")),
            Modifier::ChargeTime(x) => Some(format!("{:.0}% faster charge", (1.0 - x) * 100.0)),
            _ => None,
        })
        .take(2)
        .collect();
    words.join(", ")
}

fn part_name(db: &ContentDb, part: PartId) -> String {
    db.parts.try_get(part.0).map_or("?".into(), |d| d.name.clone())
}

/// A socket-sized name: Sigils drop their `Sigil of (the)` prefix.
fn short_name(db: &ContentDb, part: PartId) -> String {
    let n = part_name(db, part);
    n.strip_prefix("Sigil of the ").or_else(|| n.strip_prefix("Sigil of ")).map_or(n.clone(), str::to_string)
}

fn part_key(db: &ContentDb, part: PartId) -> String {
    ik::part(db.parts.try_get(part.0).map_or("?", |d| d.key.as_str()))
}

fn name_color(r: Rarity) -> Color {
    if r == Rarity::Common { tok::PARCH } else { rarity_color(r) }
}

// ───────────────────────────── the system ─────────────────────────────

#[allow(clippy::too_many_arguments)]
pub(super) fn sync(
    mut commands: Commands,
    kit: Res<UiKit>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pw: Res<PanelWorld>,
    state: Res<PanelState>,
    input: Res<InputState>,
    time: Res<Time>,
    focus: Res<InputFocus>,
    mut sel: ResMut<ForgeSelection>,
    mut ui: ResMut<ForgeUi>,
    cards: Query<(&BagCard, &Hovered)>,
    mut rings: Query<&mut KitRing>,
    mut texts: Query<&mut Text>,
) {
    if !state.forge {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.key = 0;
        ui.focus_key = 0;
        sel.disarm();
        return;
    }
    let (Some(w), Some(p)) = (pw.get(&link), pw.get(&link).and_then(|w| me_in(w, link.slot))) else { return };
    let db = &cfg.content;
    let now = time.elapsed_secs();
    let bag = &w.private.bag;

    // Feedback from the host.
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::ForgeFailed { slot, error } if Some(slot) == link.slot => {
                sel.error = Some((long_reason(&error), now));
                if let Some(d) = ui.ids.detail {
                    commands.entity(d).insert(PaneShake(0.0));
                }
            }
            GameEvent::Forged { slot, outcome } if Some(slot) == link.slot => match outcome {
                ForgeOutcome::Equipped { slot, .. }
                | ForgeOutcome::Fused { slot, .. }
                | ForgeOutcome::Rerolled { slot, .. } => sel.flare = Some((slot, now)),
                ForgeOutcome::Salvaged { .. } => sel.shards_at = now,
            },
            _ => {}
        }
    }
    if sel.armed.is_some() && now - sel.armed_at > 3.0 {
        sel.disarm();
    }
    if sel.error.as_ref().is_some_and(|(_, at)| now - at > 4.0) {
        sel.error = None;
    }
    // Keep the selection on a part that exists, preferring what the filter shows.
    if sel.selected.is_none_or(|u| bag.find(u).is_none()) {
        let first = bag.items.iter().find(|it| sel.filter.admits(db.part_slot(it.part))).or(bag.items.first());
        sel.selected = first.map(|it| it.uid);
    }

    let key = key_of(format!(
        "{:?}{:?}{:?}{:?}{:?}{:?}{:?}{}",
        bag,
        w.private.wallet,
        p.weapon,
        sel.selected,
        sel.armed,
        sel.filter,
        input.device,
        w.players.iter().all(|q| q.forge_open)
    ));
    if ui.key != key || ui.root.is_none() {
        let entrance = ui.root.is_none();
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        let flare = sel.flare.filter(|(_, at)| now - at < 0.6).map(|(s, _)| s);
        let shards_pop = now - sel.shards_at < 0.6;
        let (root, ids) = spawn_drawer(&mut commands, &kit, db, w, p, &sel, input.device, entrance, flare, shards_pop);
        let dps = build_dps(db, &p.weapon);
        ui.root = Some(root);
        ui.ids = ids;
        ui.key = key;
        ui.focus_key = 0;
        if ui.dps_shown <= 0.0 {
            ui.dps_shown = dps;
        }
    }

    // Hover (or pad focus) on a bag card previews it; otherwise the selection does.
    let hovered = cards
        .iter()
        .find(|(_, h)| h.get())
        .map(|(c, _)| c.0)
        .or_else(|| focus.get().and_then(|f| cards.get(f).ok()).map(|(c, _)| c.0));
    let focus_uid = hovered.filter(|u| bag.find(*u).is_some()).or(sel.selected);
    let focus_key = key_of(format!("{key}{focus_uid:?}{:?}", sel.error.as_ref().map(|e| &e.0)));
    if focus_key != ui.focus_key {
        ui.focus_key = focus_key;
        let ids = ui.ids.clone();
        let mut shown = ui.dps_shown;
        rebuild_live(&mut commands, &kit, db, w, p, &sel, focus_uid, &ids, &mut shown);
        ui.dps_shown = shown;
        // Selection rings on the bag, the REPLACE target on the sockets.
        for (uid, e) in &ids.bag {
            set_card(&mut commands, *e, Some(*uid) == sel.selected);
        }
        let target = focus_uid
            .and_then(|u| bag.find(u))
            .and_then(|it| db.part_slot(it.part))
            .filter(|s| !db.game.forge.locked_slots.contains(s));
        for (i, s) in Slot::ALL.into_iter().enumerate() {
            let on = Some(s) == target;
            if let Some(e) = ids.sockets[i] {
                set_card(&mut commands, e, on);
            }
            if let Some(e) = ids.replace[i] {
                set_display(&mut commands, e, on);
            }
        }
    }

    // The heat ring and the sub-line tick in place.
    let hot = w.private.anvil.filter(|a| a.state == AnvilState::Hot);
    let left = hot.map_or(0.0, |a| a.time_left);
    let frac = (left / db.game.anvil.forge_window.max(1.0)).clamp(0.0, 1.0);
    if let Some(e) = ui.ids.heat_ring
        && let Ok(mut r) = rings.get_mut(e)
        && (r.value - frac).abs() > 0.002
    {
        r.value = frac;
    }
    let secs = format!("{:.0}", left.ceil());
    if let Some(e) = ui.ids.heat_text
        && let Ok(mut t) = texts.get_mut(e)
        && t.0 != secs
    {
        t.0 = secs;
    }
    let sub = if hot.is_none() {
        "The anvil has cooled"
    } else if left < 6.0 {
        "The anvil is cooling"
    } else {
        "The anvil burns hot"
    };
    if let Some(e) = ui.ids.sub
        && let Ok(mut t) = texts.get_mut(e)
        && t.0 != sub
    {
        t.0 = sub.into();
    }
}

fn set_card(commands: &mut Commands, e: Entity, on: bool) {
    commands.queue(move |w: &mut World| {
        if let Some(mut k) = w.get_mut::<crate::uikit::KitCard>(e)
            && k.selected != on
        {
            k.selected = on;
        }
    });
}

fn set_display(commands: &mut Commands, e: Entity, on: bool) {
    commands.queue(move |w: &mut World| {
        if let Some(mut n) = w.get_mut::<Node>(e) {
            let d = if on { Display::Flex } else { Display::None };
            if n.display != d {
                n.display = d;
            }
        }
    });
}

fn shake_panes(mut commands: Commands, time: Res<Time>, mut q: Query<(Entity, &mut PaneShake, &mut UiTransform)>) {
    for (e, mut s, mut tf) in &mut q {
        s.0 += time.delta_secs();
        let t = (s.0 / 0.18).min(1.0);
        tf.translation = Val2::px(2.0 * (t * 3.0 * TAU).sin() * (1.0 - t), 0.0);
        if t >= 1.0 {
            tf.translation = Val2::ZERO;
            commands.entity(e).remove::<PaneShake>();
        }
    }
}

// ───────────────────────────── building ─────────────────────────────

/// A text node centred on `cx`, its top at `top`.
fn centered_text(p: &mut ChildSpawnerCommands, cx: f32, top: f32, bundle: impl Bundle) -> Entity {
    let mut id = Entity::PLACEHOLDER;
    p.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: px(cx - 150.0),
            top: px(top),
            width: px(300.0),
            justify_content: JustifyContent::Center,
            ..default()
        },
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        id = c.spawn(bundle).id();
    });
    id
}

#[allow(clippy::too_many_arguments)]
fn spawn_drawer(
    commands: &mut Commands,
    kit: &UiKit,
    db: &ContentDb,
    w: &WorldSnapshot,
    p: &PlayerView,
    sel: &ForgeSelection,
    device: Device,
    entrance: bool,
    flare: Option<Slot>,
    shards_pop: bool,
) -> (Entity, Ids) {
    let mut ids = Ids::default();
    let wallet = w.private.wallet;
    let rules = &db.game.forge;
    let bag = &w.private.bag;
    let dps_now = build_dps(db, &p.weapon);
    let prof = profile(db, &p.weapon);
    let pad = device == Device::Gamepad;
    let root = commands
        .spawn((layer(z::PANEL), ForgeRootMarker))
        .with_children(|l| {
            // The world takes a cool dim and a scrim toward the drawer (§7.1 framing).
            l.spawn((fill(), BackgroundColor(hx(0x0A0610).with_alpha(0.18)), Pickable::IGNORE));
            l.spawn((
                fill(),
                BackgroundGradient(vec![
                    LinearGradient::to_right(vec![
                        ColorStop::percent(tok::SCRIM.with_alpha(0.0), 43.0),
                        ColorStop::percent(tok::SCRIM.with_alpha(0.62), 100.0),
                    ])
                    .into(),
                ]),
                Pickable::IGNORE,
            ));
            l.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    right: px(24.0),
                    top: px(64.0),
                    width: px(W),
                    height: px(H),
                    ..default()
                },
                Fit { size: Vec2::new(W, H), pivot: Vec2::new(0.5, -0.5), pad: Vec2::new(48.0, 64.0 + 20.0) },
                CapturesPointer,
                Hovered::default(),
            ))
            .with_children(|cv| {
                let mut body = cv.spawn((fill(), Pickable::IGNORE));
                if entrance {
                    body.insert(Tween::new(TweenTarget::Translate(Vec2::new(40.0, 0.0), Vec2::ZERO), 0.22));
                }
                body.with_children(|b| {
                    gilt_panel(b, kit, abs(0.0, 0.0, W, H), PanelStyle::horns(76).crest(62), |d| {
                        header(d, kit, db, w, &wallet, &mut ids, shards_pop);
                        section_label(d, kit, 40.0, 150.0, "THE WEAPON", None);
                        chassis_card(d, kit, db, p, &prof);
                        for (i, s) in Slot::ALL.into_iter().enumerate() {
                            let (card, replace) =
                                socket_card(d, kit, db, p, s, 252.0 + i as f32 * 150.0, &wallet, sel, flare == Some(s));
                            ids.sockets[i] = Some(card);
                            ids.replace[i] = Some(replace);
                        }
                        ids.dps = Some(d.spawn((abs(40.0, 360.0, W - 80.0, 58.0), Pickable::IGNORE)).id());
                        ids.recipe = Some(d.spawn((abs(40.0, 424.0, W - 80.0, 64.0), Pickable::IGNORE)).id());
                        d.spawn((
                            Node { justify_content: JustifyContent::Center, ..abs(0.0, 501.0, W, 14.0) },
                            Pickable::IGNORE,
                        ))
                        .with_children(|k| {
                            ember_knot(k, kit, W - 160.0, Gem::None, 0.8);
                        });
                        section_label(
                            d,
                            kit,
                            40.0,
                            530.0,
                            "THE BAG",
                            Some(format!("{} / {}", bag.items.len(), bag.capacity)),
                        );
                        filter_chips(d, kit, sel.filter);
                        bag_grid(d, kit, db, p, bag, &wallet, sel, dps_now, &mut ids);
                        ids.detail = Some(
                            d.spawn((
                                abs(40.0, 746.0, W - 80.0, H - 64.0 - 746.0),
                                UiTransform::default(),
                                Pickable::IGNORE,
                            ))
                            .id(),
                        );
                        footer(d, kit, pad, w.players.iter().all(|q| q.forge_open));
                    });
                });
            });
            let _ = rules;
        })
        .id();
    (root, ids)
}

/// Marks the drawer's root layer.
#[derive(Component)]
struct ForgeRootMarker;

fn section_label(p: &mut ChildSpawnerCommands, kit: &UiKit, x: f32, y: f32, s: &str, count: Option<String>) {
    p.spawn((Node { position_type: PositionType::Absolute, left: px(x), top: px(y), ..row(12.0) }, Pickable::IGNORE))
        .with_children(|r| {
            r.spawn(kit.text_flat(Ty::Label, 15.0, s, tok::GOLD_LT));
            if let Some(c) = count {
                r.spawn(kit.text_flat(Ty::Label, 15.0, c, tok::PARCH_DIM));
            }
        });
}

fn header(
    d: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    w: &WorldSnapshot,
    wallet: &ForgeWallet,
    ids: &mut Ids,
    shards_pop: bool,
) {
    // Heat: the molten ring of the forge window, whole seconds inside (§7.1).
    let left = w.private.anvil.filter(|a| a.state == AnvilState::Hot).map_or(0.0, |a| a.time_left);
    let frac = (left / db.game.anvil.forge_window.max(1.0)).clamp(0.0, 1.0);
    let ring = ring_meter(
        d,
        Node {
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            ..abs(44.0, 34.0, 56.0, 56.0)
        },
        6.0,
        RingStyle::Molten,
        frac,
    );
    d.commands_mut().entity(ring).with_children(|h| {
        ids.heat_text = Some(h.spawn(kit.text_flat(Ty::NumM, 22.0, format!("{:.0}", left.ceil()), tok::NUMERAL)).id());
    });
    ids.heat_ring = Some(ring);
    centered_text(d, 72.0, 98.0, kit.text_flat(Ty::Micro, 12.0, "HEAT", tok::PARCH_DIM));

    // Charges: three hammers, lit or spent; free actions replace the caption.
    d.spawn((
        Node { position_type: PositionType::Absolute, left: px(136.0), top: px(44.0), ..row(0.0) },
        Pickable::IGNORE,
    ))
    .with_children(|h| {
        let full = db.game.forge.charges_per_anvil.max(wallet.charges).max(1);
        for i in 0..full {
            let lit = i < wallet.charges || wallet.free_actions > 0;
            icon(h, "currency/forge_charge", 30.0, if lit { Color::WHITE } else { hx(0x5A5048).with_alpha(0.8) });
        }
    });
    let caption = if wallet.free_actions > 0 { format!("{} FREE", wallet.free_actions) } else { "CHARGES".into() };
    let caption_color = if wallet.free_actions > 0 { tok::ICHOR } else { tok::PARCH_DIM };
    centered_text(d, 181.0, 98.0, kit.text_flat(Ty::Micro, 12.0, caption, caption_color));

    // Title and sub-line.
    d.spawn((
        Node {
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: px(2.0),
            ..abs(0.0, 40.0, W, 80.0)
        },
        Pickable::IGNORE,
    ))
    .with_children(|t| {
        halo(
            t,
            Node {
                position_type: PositionType::Absolute,
                left: px(W / 2.0 - 220.0),
                top: px(-10.0),
                width: px(440.0),
                height: px(70.0),
                ..default()
            },
            hx(0xFF9A2E),
            0.12,
        );
        gradient_text(
            t,
            kit,
            Ty::Title,
            36.0,
            "THE FORGE",
            &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
            false,
        );
        ids.sub = Some(t.spawn(kit.text_flat(Ty::Flavour, 17.0, "The anvil burns hot", tok::PARCH_DIM)).id());
    });

    // Shards, right-aligned.
    d.spawn((
        Node { position_type: PositionType::Absolute, right: px(40.0), top: px(40.0), ..row(8.0) },
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        icon(r, "currency/godshard", 32.0, Color::WHITE);
        let mut n = r.spawn((
            kit.text_flat(Ty::NumM, 26.0, thousands(wallet.godshards as u64), tok::NUMERAL),
            UiTransform::default(),
        ));
        if shards_pop {
            n.insert(pop(0.18, 0.25));
        }
    });
    d.spawn((
        Node { position_type: PositionType::Absolute, right: px(40.0), top: px(98.0), ..default() },
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        r.spawn(kit.text_flat(Ty::Micro, 12.0, "SHARDS", tok::PARCH_DIM));
    });
    d.spawn((Node { justify_content: JustifyContent::Center, ..abs(0.0, 121.0, W, 14.0) }, Pickable::IGNORE))
        .with_children(|k| {
            ember_knot(k, kit, W - 120.0, Gem::Ivory, 1.0);
        });
}

fn chassis_card(d: &mut ChildSpawnerCommands, kit: &UiKit, db: &ContentDb, p: &PlayerView, prof: &WeaponProfile) {
    let def = db.chassis.try_get(p.weapon.chassis.0);
    let name = def.map_or("?".to_string(), |c| c.name.to_uppercase());
    let key = ik::chassis(def.map_or("?", |c| c.key.as_str()));
    let hue = element_color(prof.element);
    gilt_panel(d, kit, abs(40.0, 172.0, 196.0, 180.0), PanelStyle::default(), |c| {
        halo(c, centered_at(98.0, 72.0, 110.0, 110.0), hue, 0.35);
        c.spawn((centered_at(98.0, 72.0, 100.0, 100.0), Pickable::IGNORE)).with_children(|i| {
            icon(i, &key, 100.0, Color::WHITE);
        });
        let size = if name.len() > 12 { 13.0 } else { 15.0 };
        centered_text(c, 98.0, 126.0, kit.text_tracked(Ty::Label, size, 0.08, name, tok::PARCH));
        c.spawn((
            Node { justify_content: JustifyContent::Center, column_gap: px(5.0), ..abs(0.0, 150.0, 196.0, 20.0) },
            Pickable::IGNORE,
        ))
        .with_children(|r| {
            icon(r, ik::element(prof.element), 18.0, hue);
            r.spawn(kit.text_flat(Ty::LabelS, 13.0, prof.element.name().to_uppercase(), hue));
        });
    });
}

#[allow(clippy::too_many_arguments)]
fn socket_card(
    d: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    p: &PlayerView,
    s: Slot,
    x: f32,
    wallet: &ForgeWallet,
    sel: &ForgeSelection,
    flare: bool,
) -> (Entity, Entity) {
    let rules = &db.game.forge;
    let part = p.weapon.get(s);
    let locked = rules.locked_slots.contains(&s);
    let rarity = part.map_or(Rarity::Common, |it| it.rarity);
    let mut replace = Entity::PLACEHOLDER;
    let card = gilt_card(
        d,
        kit,
        rarity,
        Node {
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            padding: UiRect::top(px(12.0)),
            row_gap: px(4.0),
            ..abs(x, 172.0, 138.0, 180.0)
        },
        |c| {
            c.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.16, s.name().to_uppercase(), tok::PARCH_DIM));
            c.spawn((Node { width: px(74.0), height: px(74.0), flex_shrink: 0.0, ..default() }, Pickable::IGNORE))
                .with_children(|sl| {
                    if part.is_some_and(|it| it.rarity >= Rarity::Epic) {
                        halo(sl, centered_at(37.0, 37.0, 110.0, 110.0), rarity_color(rarity), 0.45);
                    }
                    let spec = SlotSpec::new(SlotShape::for_part(s), 74.0).icon_frac(0.62).ghost(ik::slot_ghost(s));
                    let spec = match part {
                        Some(it) => spec.icon(&part_key(db, it.part)),
                        None => spec,
                    };
                    slot(sl, kit, spec);
                });
            match part {
                Some(it) => {
                    c.spawn((Node { height: px(12.0), margin: UiRect::top(px(-8.0)), ..default() }, Pickable::IGNORE))
                        .with_children(|g| {
                            rarity_gem(g, it.rarity, 6.0);
                        });
                    let n = short_name(db, it.part);
                    let size = if n.len() > 13 { 14.0 } else { 16.0 };
                    c.spawn(kit.text_flat(Ty::Strong, size, n, name_color(it.rarity)));
                }
                None => {
                    c.spawn((Node { height: px(12.0), ..default() }, Pickable::IGNORE));
                    c.spawn(kit.text_flat(Ty::Micro, 12.0, "EMPTY", tok::PARCH_MUTE));
                }
            }
            // The REROLL chip or the lock, on the card's foot.
            c.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0.0),
                    right: px(0.0),
                    bottom: px(10.0),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    column_gap: px(4.0),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|f| {
                if locked {
                    icon(f, "ui/lock", 14.0, tok::PARCH_MUTE);
                    f.spawn(kit.text_flat(Ty::Micro, 12.0, "LOCKED", tok::PARCH_MUTE));
                } else if part.is_some() {
                    reroll_chip(f, kit, db, p, s, wallet, sel);
                }
            });
            replace = c
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(0.0),
                        right: px(0.0),
                        top: px(-10.0),
                        justify_content: JustifyContent::Center,
                        display: Display::None,
                        ..default()
                    },
                    ZIndex(4),
                    Pickable::IGNORE,
                ))
                .with_children(|r| {
                    pill(r, kit, PillKind::Gold, "Replace", None);
                })
                .id();
        },
    );
    let mut e = d.commands_mut().entity(card);
    if let Some(it) = part {
        let def = db.parts.try_get(it.part.0);
        e.insert((
            Hovered::default(),
            Tip::new(part_name(db, it.part), name_color(it.rarity))
                .sub(format!("{} {}", it.rarity.name(), s.name()).to_uppercase())
                .body(def.map_or("", |d| d.desc.as_str())),
        ));
    }
    if flare {
        e.insert(pop(0.08, 0.3));
    }
    (card, replace)
}

fn reroll_chip(
    f: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    p: &PlayerView,
    s: Slot,
    wallet: &ForgeWallet,
    sel: &ForgeSelection,
) {
    let rules = &db.game.forge;
    let action = ForgeAction::Reroll { slot: s };
    let armed = sel.armed == Some(action);
    let free = wallet.free_actions > 0;
    let refusal = if free {
        None
    } else if wallet.charges == 0 {
        Some(ForgeError::NoCharges)
    } else if wallet.godshards < rules.reroll_cost {
        Some(ForgeError::NotEnoughShards { need: rules.reroll_cost, have: wallet.godshards })
    } else {
        None
    };
    let _ = p;
    let label = if armed { "Confirm" } else { "Reroll" };
    let e = chip(f, kit, label, Some("ui/reroll"), 112.0, |t| {
        if free {
            t.spawn(kit.text_flat(Ty::Micro, 11.0, "FREE", tok::ICHOR));
        } else {
            t.spawn(kit.text_flat(Ty::Num, 14.0, rules.reroll_cost.to_string(), tok::PARCH));
            icon(t, "currency/godshard", 13.0, Color::WHITE);
        }
    });
    let mut ec = f.commands_mut().entity(e);
    ec.insert((UiAction::Forge { action, confirm: true }, Nav(PanelKind::Forge)));
    if armed {
        ec.insert(crate::uikit::glow(tok::READY_GLOW.with_alpha(0.7), 10.0, 1.0));
    }
    match refusal {
        Some(err) => {
            ec.insert((InteractionDisabled, Tip::new("Reroll", tok::PARCH).body(long_reason(&err))));
        }
        None => {
            ec.insert(
                Tip::new("Reroll", tok::GOLD_LT)
                    .body("Roll this part into another of its slot and rarity. Costs a forge charge and godshards."),
            );
        }
    }
}

fn filter_chips(d: &mut ChildSpawnerCommands, kit: &UiKit, active: BagFilter) {
    d.spawn((
        Node { position_type: PositionType::Absolute, right: px(40.0), top: px(526.0), ..row(6.0) },
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        for f in BagFilter::ALL {
            let e = chip(r, kit, f.label(), None, 64.0, |_| {});
            let mut ec = r.commands_mut().entity(e);
            ec.insert((UiAction::Filter(f), Nav(PanelKind::Forge)));
            if f == active {
                ec.insert(crate::uikit::glow(tok::READY_GLOW.with_alpha(0.55), 8.0, 0.0));
            }
        }
    });
}

#[allow(clippy::too_many_arguments)]
fn bag_grid(
    d: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    p: &PlayerView,
    bag: &PartBag,
    wallet: &ForgeWallet,
    sel: &ForgeSelection,
    dps_now: f32,
    ids: &mut Ids,
) {
    let active = satisfied(db, &p.weapon);
    let visible: Vec<PartInstance> =
        bag.items.iter().filter(|it| sel.filter.admits(db.part_slot(it.part))).copied().collect();
    let cells = 8usize;
    d.spawn((
        Node {
            flex_direction: FlexDirection::Row,
            flex_wrap: FlexWrap::Wrap,
            column_gap: px(10.0),
            row_gap: px(10.0),
            ..abs(40.0, 556.0, 808.0, 174.0)
        },
        Pickable::IGNORE,
    ))
    .with_children(|g| {
        for it in visible.iter().take(cells) {
            let equip = preview(db, ForgeAction::Equip { uid: it.uid }, &p.weapon, bag, wallet);
            let delta = equip.as_ref().ok().map(|(dps, _)| pct(dps_now, *dps));
            let completes =
                equip.as_ref().ok().is_some_and(|(_, b)| satisfied(db, b).iter().any(|r| !active.contains(r)));
            let fuses = preview(db, ForgeAction::Fuse { uid: it.uid }, &p.weapon, bag, wallet).is_ok();
            let badge = if completes {
                Some("currency/seal")
            } else if fuses {
                Some("ui/fuse")
            } else {
                None
            };
            let e = bag_card(g, kit, db, *it, delta, badge);
            ids.bag.push((it.uid, e));
        }
        let free = if sel.filter == BagFilter::All {
            (bag.capacity as usize).min(cells).saturating_sub(bag.items.len())
        } else {
            0
        };
        for i in visible.len().min(cells)..cells {
            let empty = i < visible.len() + free;
            g.spawn((
                Node {
                    width: px(194.0),
                    height: px(82.0),
                    border: UiRect::all(px(1.0)),
                    border_radius: BorderRadius::all(px(8.0)),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    ..default()
                },
                BackgroundColor(tok::LAC0.with_alpha(if empty { 0.6 } else { 0.3 })),
                BorderColor::all(tok::GOLD_SH.with_alpha(if empty { 1.0 } else { 0.5 })),
                Pickable::IGNORE,
            ))
            .with_children(|c| {
                if empty {
                    c.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.24, "EMPTY", tok::PARCH_MUTE));
                }
            });
        }
    });
}

fn bag_card(
    g: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    it: PartInstance,
    delta: Option<f32>,
    badge: Option<&str>,
) -> Entity {
    let s = db.part_slot(it.part).unwrap_or(Slot::Core);
    let name = short_name(db, it.part);
    let e =
        gilt_card(g, kit, it.rarity, Node { width: px(194.0), height: px(82.0), flex_shrink: 0.0, ..default() }, |c| {
            c.spawn((abs(12.0, 13.0, 56.0, 56.0), Pickable::IGNORE)).with_children(|sl| {
                slot(
                    sl,
                    kit,
                    SlotSpec::new(SlotShape::for_part(s), 56.0)
                        .icon(&part_key(db, it.part))
                        .icon_frac(0.62)
                        .shadow(false),
                );
            });
            let size = if name.len() > 14 {
                14.0
            } else if name.len() > 11 {
                16.0
            } else {
                17.0
            };
            c.spawn((
                Node { position_type: PositionType::Absolute, left: px(80.0), top: px(14.0), ..default() },
                Pickable::IGNORE,
            ))
            .with_children(|t| {
                t.spawn((kit.text_flat(Ty::Strong, size, name, tok::PARCH), TextLayout::no_wrap()));
            });
            c.spawn((
                Node { position_type: PositionType::Absolute, left: px(80.0), top: px(44.0), ..default() },
                Pickable::IGNORE,
            ))
            .with_children(|t| {
                t.spawn(kit.text_tracked(
                    Ty::Micro,
                    12.0,
                    0.16,
                    it.rarity.name().to_uppercase(),
                    rarity_color(it.rarity),
                ));
            });
            if let Some(pc) = delta {
                c.spawn((
                    Node { position_type: PositionType::Absolute, right: px(10.0), bottom: px(8.0), ..default() },
                    Pickable::IGNORE,
                ))
                .with_children(|t| {
                    delta_chip(t, kit, pc, 15.0);
                });
            }
            if let Some(b) = badge {
                // On the slot's shoulder, clear of the name.
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(52.0),
                        top: px(5.0),
                        width: px(24.0),
                        height: px(24.0),
                        border: UiRect::all(px(1.0)),
                        border_radius: BorderRadius::MAX,
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    BackgroundColor(tok::LAC0.with_alpha(0.85)),
                    BorderColor::all(tok::GOLD_MD.with_alpha(0.8)),
                    Pickable::IGNORE,
                ))
                .with_children(|t| {
                    icon(t, b, 16.0, tok::GOLD_LT);
                });
            }
        });
    g.commands_mut().entity(e).insert((
        UiButton,
        Hovered::default(),
        UiAction::SelectPart(it.uid),
        BagCard(it.uid),
        Nav(PanelKind::Forge),
    ));
    e
}

fn footer(d: &mut ChildSpawnerCommands, kit: &UiKit, pad: bool, focused: bool) {
    d.spawn((
        Node {
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            ..abs(40.0, H - 42.0, W - 80.0, 26.0)
        },
        Pickable::IGNORE,
    ))
    .with_children(|f| {
        f.spawn((row(8.0), Pickable::IGNORE)).with_children(|r| {
            let (sel_key, close_key) = if pad {
                (Key::Icon("input/pad_south"), Key::Icon("input/pad_view"))
            } else {
                (Key::Icon("input/mouse_lmb"), Key::Text("Tab"))
            };
            key_chip(r, kit, sel_key, 20.0);
            r.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.16, "SELECT", tok::PARCH_DIM));
            r.spawn((Node { width: px(18.0), ..default() }, Pickable::IGNORE));
            // The close hint is itself a button.
            r.spawn((row(8.0), UiButton, Hovered::default(), UiAction::CloseForge)).with_children(|b| {
                key_chip(b, kit, close_key, 20.0);
                b.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.16, "CLOSE", tok::PARCH_DIM));
            });
        });
        let (note, color) = if focused {
            ("Forge focus: time slows while you all forge", tok::ICHOR)
        } else {
            ("Forge focus: time slows while every player forges", tok::PARCH_MUTE)
        };
        f.spawn(kit.text_flat(Ty::Flavour, 15.0, note, color));
    });
}

// ───────────────────────────── the live sections ─────────────────────────────

#[allow(clippy::too_many_arguments)]
fn rebuild_live(
    commands: &mut Commands,
    kit: &UiKit,
    db: &ContentDb,
    w: &WorldSnapshot,
    p: &PlayerView,
    sel: &ForgeSelection,
    focus: Option<u32>,
    ids: &Ids,
    dps_shown: &mut f32,
) {
    let bag = &w.private.bag;
    let wallet = w.private.wallet;
    let now = build_dps(db, &p.weapon);
    let part = focus.and_then(|u| bag.find(u)).copied();
    let equip = part.map(|it| preview(db, ForgeAction::Equip { uid: it.uid }, &p.weapon, bag, &wallet));
    let previewed = equip.as_ref().and_then(|r| r.as_ref().ok()).cloned();

    // Live DPS (§7.1): now → preview with the delta, and what the preview adds.
    if let Some(row_e) = ids.dps {
        let from = *dps_shown;
        *dps_shown = now;
        commands.entity(row_e).despawn_children().with_children(|r| {
            r.spawn((
                Node { position_type: PositionType::Absolute, left: px(0.0), top: px(4.0), ..row(12.0) },
                Pickable::IGNORE,
            ))
            .with_children(|l| {
                let mut n = l.spawn(kit.text_flat(Ty::NumXl, 38.0, thousands(now.round() as u64), tok::NUMERAL));
                if (from - now).abs() > 0.5 {
                    n.insert(CountUp {
                        from: from as f64,
                        to: now as f64,
                        t: 0.0,
                        dur: 0.4,
                        delay: 0.0,
                        fmt: NumFmt::Thousands,
                    });
                }
                l.spawn(kit.text_flat(Ty::Label, 15.0, "DPS", tok::PARCH_DIM));
                if let Some((dps, _)) = &previewed {
                    let arrow = icon(l, "ui/bearing", 26.0, tok::GOLD_LT);
                    l.commands_mut().entity(arrow).insert(UiTransform::from_rotation(Rot2::radians(PI / 2.0)));
                    l.spawn((
                        kit.text_flat(Ty::NumXl, 38.0, thousands(dps.round() as u64), tok::ICHOR),
                        TextShadow { offset: Vec2::ZERO, color: tok::ICHOR_GLOW.with_alpha(0.35) },
                    ));
                    delta_chip(l, kit, pct(now, *dps), 20.0);
                }
            });
            let tags_now = describe(&profile(db, &p.weapon));
            r.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    right: px(0.0),
                    top: px(4.0),
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::FlexEnd,
                    row_gap: px(2.0),
                    max_width: px(360.0),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|t| {
                t.spawn(kit.text_flat(
                    Ty::BodyS,
                    16.0,
                    tags_now.iter().skip(1).take(4).cloned().collect::<Vec<_>>().join(" · "),
                    tok::PARCH_DIM,
                ));
                if let Some((_, b)) = &previewed {
                    let adds: Vec<String> =
                        describe(&profile(db, b)).into_iter().filter(|t| !tags_now.contains(t)).take(2).collect();
                    if !adds.is_empty() {
                        t.spawn(kit.text_flat(Ty::Strong, 16.0, format!("+ {}", adds.join(" · ")), tok::ICHOR));
                    }
                }
            });
        });
    }

    // The recipe hint (§7.1): the combo this completes, the active combo, or one part away.
    if let Some(box_e) = ids.recipe {
        let hint = recipe_hint(db, p, bag, previewed.as_ref().map(|(_, b)| b));
        commands.entity(box_e).despawn_children().with_children(|c| {
            if let Some(h) = hint {
                recipe_plate(c, kit, db, &h);
            }
        });
    }

    // The detail pane (§7.1).
    if let Some(pane) = ids.detail {
        commands.entity(pane).despawn_children().with_children(|c| {
            quiet_plate(
                c,
                Node {
                    padding: UiRect::all(px(16.0)),
                    column_gap: px(18.0),
                    align_items: AlignItems::Center,
                    ..abs(0.0, 0.0, W - 80.0, H - 64.0 - 746.0 - 8.0)
                },
                0.85,
                |q| match part {
                    Some(it) => detail(q, kit, db, p, bag, &wallet, sel, it, now, equip.as_ref()),
                    None => {
                        q.spawn((
                            Node { flex_grow: 1.0, justify_content: JustifyContent::Center, ..default() },
                            Pickable::IGNORE,
                        ))
                        .with_children(|t| {
                            t.spawn(kit.text_flat(
                                Ty::Flavour,
                                18.0,
                                "The bag is empty. Elites, caches and Warlords drop parts.",
                                tok::PARCH_DIM,
                            ));
                        });
                    }
                },
            );
        });
    }
}

/// What the recipe hint shows.
struct Hint {
    recipe: u16,
    kind: HintKind,
    /// The build the ingredient sockets are checked against.
    build: WeaponBuild,
    /// The missing part, if any.
    missing: Option<PartId>,
}

#[derive(PartialEq, Eq)]
enum HintKind {
    /// The previewed part completes it.
    Completes,
    /// The build already has it.
    Active,
    /// One part away, and that part is in the bag.
    InBag,
    /// One part away, the part not yet found.
    Missing,
}

fn recipe_hint(db: &ContentDb, p: &PlayerView, bag: &PartBag, previewed: Option<&WeaponBuild>) -> Option<Hint> {
    let active = satisfied(db, &p.weapon);
    if let Some(b) = previewed
        && let Some(r) = satisfied(db, b).into_iter().find(|r| !active.contains(r))
    {
        return Some(Hint { recipe: r, kind: HintKind::Completes, build: b.clone(), missing: None });
    }
    if let Some(&r) = active.first() {
        return Some(Hint { recipe: r, kind: HintKind::Active, build: p.weapon.clone(), missing: None });
    }
    let element = profile(db, &p.weapon).element;
    let mut best: Option<Hint> = None;
    for (i, ings) in db.recipe_ingredients.iter().enumerate() {
        let missing: Vec<&Ingredient> = ings.iter().filter(|g| !has_ingredient(g, &p.weapon, element)).collect();
        let [Ingredient::Part(pid)] = missing.as_slice() else { continue };
        if ings.len() < 2 {
            continue;
        }
        // The missing part must fit an unlocked slot.
        if db.part_slot(*pid).is_none_or(|s| db.game.forge.locked_slots.contains(&s)) {
            continue;
        }
        let in_bag = bag.items.iter().any(|it| it.part == *pid);
        let kind = if in_bag { HintKind::InBag } else { HintKind::Missing };
        if best.as_ref().is_none_or(|b| b.kind == HintKind::Missing && kind == HintKind::InBag) {
            best = Some(Hint { recipe: i as u16, kind, build: p.weapon.clone(), missing: Some(*pid) });
        }
    }
    best
}

fn recipe_plate(c: &mut ChildSpawnerCommands, kit: &UiKit, db: &ContentDb, h: &Hint) {
    let Some(def) = db.recipes.try_get(h.recipe) else { return };
    let ings = db.recipe_ingredients.get(h.recipe as usize).cloned().unwrap_or_default();
    let (status, status_color) = match h.kind {
        HintKind::Completes => ("COMPLETES A NAMED COMBO", tok::ICHOR),
        HintKind::Active => ("NAMED COMBO", tok::GOLD_LT),
        HintKind::InBag | HintKind::Missing => ("ONE PART AWAY", tok::ICHOR),
    };
    let bonus = bonus_words(&def.bonus);
    let tail = match (&h.kind, h.missing) {
        (HintKind::InBag, Some(pid)) => format!("{} is in your bag", part_name(db, pid)),
        (HintKind::Missing, Some(pid)) => format!("find {}", part_name(db, pid)),
        (HintKind::Active, _) => "active".into(),
        _ => "equip to seal it".into(),
    };
    let line = if bonus.is_empty() { tail } else { format!("{bonus} · {tail}") };
    let node = Node {
        padding: UiRect::horizontal(px(14.0)),
        column_gap: px(12.0),
        align_items: AlignItems::Center,
        ..abs(0.0, 0.0, W - 80.0, 62.0)
    };
    let content = |d: &mut ChildSpawnerCommands| {
        icon(d, "currency/seal", 36.0, if h.kind == HintKind::Missing { tok::PARCH_DIM } else { Color::WHITE });
        d.spawn((Node { flex_direction: FlexDirection::Column, flex_grow: 1.0, ..default() }, Pickable::IGNORE))
            .with_children(|t| {
                t.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, status, status_color));
                t.spawn(kit.text_flat(Ty::Label, 17.0, def.name.to_uppercase(), tok::GOLD_LT));
                t.spawn(kit.text_flat(Ty::BodyS, 15.0, line, tok::PARCH_DIM));
            });
        let element = profile(db, &h.build).element;
        d.spawn((row(8.0), Pickable::IGNORE)).with_children(|r| {
            for ing in &ings {
                let owned = has_ingredient(ing, &h.build, element);
                let (shape, key) = match *ing {
                    Ingredient::Part(pid) => {
                        (db.part_slot(pid).map_or(SlotShape::Round, SlotShape::for_part), part_key(db, pid))
                    }
                    Ingredient::Chassis(cid) => {
                        (SlotShape::HexFlat, ik::chassis(db.chassis.try_get(cid.0).map_or("?", |c| c.key.as_str())))
                    }
                    Ingredient::Element(e) => (SlotShape::Round, ik::element(e).to_string()),
                };
                let mut holder = r.spawn((
                    Node {
                        width: px(34.0),
                        height: px(34.0),
                        border_radius: BorderRadius::MAX,
                        flex_shrink: 0.0,
                        ..default()
                    },
                    Pickable::IGNORE,
                ));
                if !owned {
                    holder.insert(crate::uikit::glow(tok::ICHOR_GLOW.with_alpha(0.6), 8.0, 1.0));
                }
                holder.with_children(|s| {
                    slot(
                        s,
                        kit,
                        SlotSpec::new(shape, 34.0).icon(&key).icon_frac(0.62).shadow(false).tint(if owned {
                            Color::WHITE
                        } else {
                            tok::PARCH_DIM
                        }),
                    );
                    if owned {
                        s.spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                right: px(-4.0),
                                bottom: px(-4.0),
                                width: px(16.0),
                                height: px(16.0),
                                border_radius: BorderRadius::MAX,
                                justify_content: JustifyContent::Center,
                                align_items: AlignItems::Center,
                                ..default()
                            },
                            BackgroundColor(tok::LAC0),
                            Pickable::IGNORE,
                        ))
                        .with_children(|k| {
                            icon(k, "ui/check", 12.0, tok::GOLD_LT);
                        });
                    }
                });
            }
        });
    };
    if h.kind == HintKind::Active {
        quiet_plate(c, node, 0.75, content);
    } else {
        dashed_plate(c, kit, node, content);
    }
}

#[allow(clippy::too_many_arguments)]
fn detail(
    q: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    p: &PlayerView,
    bag: &PartBag,
    wallet: &ForgeWallet,
    sel: &ForgeSelection,
    it: PartInstance,
    now: f32,
    equip: Option<&Result<(f32, WeaponBuild), ForgeError>>,
) {
    let s = db.part_slot(it.part).unwrap_or(Slot::Core);
    let def = db.parts.try_get(it.part.0);
    // Left: the 92 px slot with its rarity glow and gem.
    q.spawn((Node { width: px(92.0), height: px(118.0), flex_shrink: 0.0, ..default() }, Pickable::IGNORE))
        .with_children(|l| {
            halo(l, centered_at(46.0, 46.0, 140.0, 140.0), rarity_color(it.rarity), 0.4);
            l.spawn((abs(0.0, 0.0, 92.0, 92.0), Pickable::IGNORE)).with_children(|sl| {
                slot(sl, kit, SlotSpec::new(SlotShape::for_part(s), 92.0).icon(&part_key(db, it.part)).icon_frac(0.64));
            });
            l.spawn((Node { justify_content: JustifyContent::Center, ..abs(0.0, 98.0, 92.0, 16.0) }, Pickable::IGNORE))
                .with_children(|g| {
                    rarity_gem(g, it.rarity, 7.0);
                });
        });
    // Middle: name, class line, rules text, refusal.
    let equipped = p.weapon.get(s);
    let class = format!("{} {}", it.rarity.name(), s.name()).to_uppercase();
    let rel = if db.game.forge.locked_slots.contains(&s) {
        "SLOT LOCKED".to_string()
    } else {
        match equipped {
            Some(e) => format!("REPLACES {}", part_name(db, e.part).to_uppercase()),
            None => "FILLS AN EMPTY SLOT".into(),
        }
    };
    q.spawn((
        Node {
            flex_direction: FlexDirection::Column,
            row_gap: px(4.0),
            flex_grow: 1.0,
            flex_basis: px(0.0),
            ..default()
        },
        Pickable::IGNORE,
    ))
    .with_children(|m| {
        let name = part_name(db, it.part).to_uppercase();
        let size = if name.len() > 22 {
            20.0
        } else if name.len() > 16 {
            22.0
        } else {
            26.0
        };
        m.spawn((
            kit.text_flat(Ty::CardName, size, name, name_color(it.rarity)),
            TextShadow { offset: Vec2::ZERO, color: rarity_color(it.rarity).with_alpha(0.25) },
        ));
        m.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.12, format!("{class} · {rel}"), tok::PARCH_DIM));
        rules_text(m, kit, 17.0, def.map_or("", |d| d.desc.as_str()), tok::PARCH, 380.0, Justify::Left);
        if let Some((e, _)) = &sel.error {
            m.spawn(kit.text_flat(Ty::Flavour, 15.0, e.clone(), tok::LOSS));
        }
    });
    // Right: EQUIP, FUSE, SALVAGE (§7.1).
    q.spawn((
        Node { flex_direction: FlexDirection::Column, row_gap: px(8.0), flex_shrink: 0.0, ..default() },
        Pickable::IGNORE,
    ))
    .with_children(|b| {
        let equip_action = ForgeAction::Equip { uid: it.uid };
        let e = button(b, kit, ButtonKind::Primary, "Equip", 214.0, 46.0, |t| {
            if let Some(Ok((dps, _))) = equip {
                delta_chip_in(t, kit, pct(now, *dps), 16.0, Some(tok::INK_TEXT));
            }
        });
        let mut ec = b.commands_mut().entity(e);
        ec.insert((UiAction::Forge { action: equip_action, confirm: false }, Nav(PanelKind::Forge)));
        if let Some(Err(err)) = equip {
            ec.insert((InteractionDisabled, Hovered::default(), Tip::new("Equip", tok::PARCH).body(long_reason(err))));
        }

        let fuse_action = ForgeAction::Fuse { uid: it.uid };
        let fuse = preview(db, fuse_action, &p.weapon, bag, wallet);
        action_button(b, kit, fuse_action, "Fuse", sel.armed == Some(fuse_action), true, fuse.as_ref().err(), |t| {
            match &fuse {
                Ok((_, nb)) => {
                    let from = p.weapon.get(s).map_or(it.rarity, |x| x.rarity);
                    let to = nb.get(s).map_or(from, |x| x.rarity);
                    t.spawn((row(5.0), Pickable::IGNORE)).with_children(|r| {
                        rarity_gem(r, from, 7.0);
                        let a = icon(r, "ui/bearing", 18.0, tok::GOLD_LT);
                        r.commands_mut().entity(a).insert(UiTransform::from_rotation(Rot2::radians(PI / 2.0)));
                        rarity_gem(r, to, 8.0);
                    });
                }
                Err(err) => {
                    t.spawn(kit.text_flat(Ty::Flavour, 15.0, short_reason(err), tok::PARCH_MUTE));
                }
            }
        });

        let salvage_action = ForgeAction::Salvage { uid: it.uid };
        let shards = db.game.rarity.salvage_shards[it.rarity.index()];
        action_button(
            b,
            kit,
            salvage_action,
            "Salvage",
            sel.armed == Some(salvage_action),
            it.rarity >= Rarity::Rare,
            None,
            |t| {
                t.spawn((row(4.0), Pickable::IGNORE)).with_children(|r| {
                    r.spawn(kit.text_flat(Ty::Num, 16.0, format!("+{shards}"), tok::PARCH));
                    icon(r, "currency/godshard", 16.0, Color::WHITE);
                });
            },
        );
    });
}

/// A secondary action button with the confirm step: armed, it turns primary and reads CONFIRM.
#[allow(clippy::too_many_arguments)]
fn action_button(
    b: &mut ChildSpawnerCommands,
    kit: &UiKit,
    action: ForgeAction,
    label: &str,
    armed: bool,
    confirm: bool,
    refusal: Option<&ForgeError>,
    trailing: impl FnOnce(&mut ChildSpawnerCommands),
) {
    let e = if armed {
        button(b, kit, ButtonKind::Primary, "Confirm", 214.0, 40.0, |t| {
            t.spawn(kit.text_flat(Ty::Flavour, 15.0, label.to_lowercase(), tok::INK_TEXT));
        })
    } else {
        button(b, kit, ButtonKind::Secondary, label, 214.0, 40.0, trailing)
    };
    let mut ec = b.commands_mut().entity(e);
    ec.insert((UiAction::Forge { action, confirm }, Nav(PanelKind::Forge)));
    if armed {
        ec.insert(crate::uikit::glow(tok::READY_GLOW.with_alpha(0.6), 12.0, 1.0));
    }
    if let Some(err) = refusal {
        ec.insert((InteractionDisabled, Tip::new(label, tok::PARCH).body(long_reason(err))));
    } else if confirm && !armed {
        ec.insert(Tip::new(label, tok::GOLD_LT).body("Press again to confirm."));
    }
}
