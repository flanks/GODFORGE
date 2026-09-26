//! Top-centre transients: the boss and Warlord bar (UI_STYLE §6.7), the callout lane (§6.8) and
//! the region banner (§6.9); and the surge edge flash (§6.10, the one screen-edge danger cue).

use super::{FadeGroup, HudRect, Ui, View, db, player_name, roman, top_centred};
use crate::ClientConfig;
use crate::net::{CurrentRoom, Link};
use crate::palette::element_color;
use crate::theme::{Ty, hx, player_color, region, tok, z};
use crate::uikit::{self, BarFill, BarSpec, Gem, UiKit, ik};
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::{BossView, GameEvent};
use std::f32::consts::{FRAC_PI_2, PI};

// ───────────────────────────── surge clock ─────────────────────────────

/// The running surge (its warning or the surge itself) and the screen side it comes from.
#[derive(Resource)]
pub(crate) struct SurgeClock {
    pub started: Option<f32>,
    pub warn: bool,
    pub dir: u16,
    /// 0 north (top), 1 east, 2 south, 3 west: the screen side.
    pub side: usize,
    pub side_name: &'static str,
}

impl Default for SurgeClock {
    fn default() -> Self {
        Self { started: None, warn: false, dir: 0, side: 1, side_name: "east" }
    }
}

pub(super) fn track_surge(time: Res<Time>, link: Res<Link>, view: View, mut clock: ResMut<SurgeClock>) {
    let now = time.elapsed_secs();
    for ev in &link.fresh_events {
        if let GameEvent::Surge { dir, warn } = *ev {
            clock.started = Some(now);
            clock.warn = warn;
            clock.dir = dir;
        }
    }
    let live = link.latest.as_deref().and_then(|w| w.run.stage).is_some_and(|s| s.surge.is_some());
    if !live {
        clock.started = None;
        return;
    }
    // A surge seen from its middle (a late join): start the clock now.
    if clock.started.is_none() {
        clock.started = Some(now);
        clock.dir = link.latest.as_deref().and_then(|w| w.run.stage).and_then(|s| s.surge).unwrap_or(0);
    }
    // The screen side it comes from (project, since the camera may turn).
    if let Some(me) = link.me() {
        let d = gf_net::quant::u16_to_dir(clock.dir);
        let a = view.project(crate::camera::w3(me.mover.pos, 0.0));
        let b = view.project(crate::camera::w3(me.mover.pos + d * 20.0, 0.0));
        if let (Some(a), Some(b)) = (a, b) {
            let v = b - a;
            clock.side = if v.x.abs() > v.y.abs() {
                if v.x > 0.0 { 1 } else { 3 }
            } else if v.y > 0.0 {
                2
            } else {
                0
            };
            clock.side_name = ["north", "east", "south", "west"][clock.side];
        }
    }
}

// ───────────────────────────── the roots ─────────────────────────────

#[derive(Clone, Copy)]
struct BossParts {
    bar: Entity,
    shake: Entity,
    phase: Entity,
}

#[derive(Resource)]
pub(super) struct Top {
    boss_root: Entity,
    boss_body: Entity,
    boss_key: Option<(u16, bool)>,
    boss: Option<BossParts>,
    boss_phase_n: u8,
    boss_t: f32,
    shake_t: f32,
    call_root: Entity,
    call: Option<Callout>,
    call_times: Option<Entity>,
    od_ready_was: bool,
    banner_root: Entity,
    banner_t: f32,
    banner_region: Option<(u32, u8)>,
    surge: [Entity; 4],
}

#[derive(Clone, Debug, PartialEq)]
enum CallKind {
    Synergy(u16),
    Combo(u16, u8),
    Overdrive(u8),
    OverdriveReady,
}

impl CallKind {
    fn prio(&self) -> u8 {
        match self {
            CallKind::Synergy(_) => 1,
            CallKind::Combo(..) => 2,
            CallKind::Overdrive(_) | CallKind::OverdriveReady => 3,
        }
    }
}

#[derive(Clone, Debug)]
struct Callout {
    kind: CallKind,
    count: u32,
    age: f32,
}

const CALL_IN: f32 = 0.16;
const CALL_HOLD: f32 = 1.0;
const CALL_OUT: f32 = 0.3;
const BANNER_LIFE: f32 = 3.5;

pub(super) fn spawn(mut commands: Commands, kit: Res<UiKit>) {
    let ph = Entity::PLACEHOLDER;
    let mut t = Top {
        boss_root: ph,
        boss_body: ph,
        boss_key: None,
        boss: None,
        boss_phase_n: 0,
        boss_t: -1.0,
        shake_t: 1.0,
        call_root: ph,
        call: None,
        call_times: None,
        od_ready_was: true,
        banner_root: ph,
        banner_t: BANNER_LIFE,
        banner_region: None,
        surge: [ph; 4],
    };
    let r = region::BOSS_BAR;
    t.boss_root = commands
        .spawn((
            Node { display: Display::None, ..top_centred(r[0], r[2], r[1], r[3] - r[1]) },
            GlobalZIndex(z::HUD),
            HudRect,
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            t.boss_body = c.spawn((uikit::fill(), FadeGroup::new(0.0), Pickable::IGNORE)).id();
        })
        .id();
    t.call_root = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                display: Display::None,
                ..top_centred(510.0, 1410.0, region::CALLOUT_BASELINE - 38.0, 80.0)
            },
            GlobalZIndex(z::TRANSIENT),
            FadeGroup::new(0.0),
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .id();
    t.banner_root = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(2.0),
                display: Display::None,
                ..top_centred(region::BANNER[0] - 200.0, region::BANNER[2] + 200.0, region::BANNER[1] - 6.0, 140.0)
            },
            GlobalZIndex(z::TRANSIENT),
            FadeGroup::new(0.0),
            Pickable::IGNORE,
        ))
        .id();
    for side in 0..4 {
        t.surge[side] = commands
            .spawn((
                Node { display: Display::None, ..uikit::fill() },
                GlobalZIndex(z::TRANSIENT),
                FadeGroup::new(0.0),
                Pickable::IGNORE,
            ))
            .with_children(|c| build_surge(c, &kit, side))
            .id();
    }
    commands.insert_resource(t);
}

/// One side's surge overlay: the edge flash, three inward chevrons, SURGE and "from the east".
fn build_surge(c: &mut ChildSpawnerCommands, kit: &UiKit, side: usize) {
    let (pos, shape) = match side {
        0 => (UiPosition::TOP, RadialGradientShape::Ellipse(percent(55.0), px(180.0))),
        1 => (UiPosition::RIGHT, RadialGradientShape::Ellipse(px(180.0), percent(55.0))),
        2 => (UiPosition::BOTTOM, RadialGradientShape::Ellipse(percent(55.0), px(180.0))),
        _ => (UiPosition::LEFT, RadialGradientShape::Ellipse(px(180.0), percent(55.0))),
    };
    let flash = hx(0xFF6A50);
    c.spawn((
        uikit::fill(),
        BackgroundGradient(vec![
            RadialGradient::new(
                pos,
                shape,
                vec![
                    ColorStop::percent(flash.with_alpha(0.55), 0.0),
                    ColorStop::percent(flash.with_alpha(0.2), 50.0),
                    ColorStop::percent(flash.with_alpha(0.0), 100.0),
                ],
            )
            .into(),
        ]),
        Pickable::IGNORE,
    ));
    let mut node = Node {
        position_type: PositionType::Absolute,
        flex_direction: FlexDirection::Column,
        align_items: AlignItems::Center,
        row_gap: px(2.0),
        width: px(200.0),
        ..default()
    };
    match side {
        0 => (node.left, node.top, node.margin) = (percent(50.0), px(96.0), UiRect::left(px(-100.0))),
        1 => (node.right, node.top, node.margin) = (px(-40.0), percent(50.0), UiRect::top(px(-50.0))),
        2 => (node.left, node.bottom, node.margin) = (percent(50.0), px(180.0), UiRect::left(px(-100.0))),
        _ => (node.left, node.top, node.margin) = (px(-40.0), percent(50.0), UiRect::top(px(-50.0))),
    }
    c.spawn((node, Pickable::IGNORE)).with_children(|t| {
        uikit::halo(
            t,
            Node {
                position_type: PositionType::Absolute,
                left: px(10.0),
                right: px(10.0),
                top: px(-12.0),
                bottom: px(-12.0),
                ..default()
            },
            tok::DANGER,
            0.3,
        );
        // The arrowhead points up; turn it toward the screen centre.
        let rot = [PI, -FRAC_PI_2, 0.0, FRAC_PI_2][side];
        t.spawn((Node { column_gap: px(-8.0), ..default() }, Pickable::IGNORE)).with_children(|r| {
            for _ in 0..3 {
                r.spawn((
                    Node { width: px(28.0), height: px(28.0), ..default() },
                    uikit::icon_bundle("ui/arrowhead", 28.0, tok::DANGER_WHITE),
                    UiTransform { rotation: Rot2::radians(rot), ..default() },
                ));
            }
        });
        t.spawn(kit.text_tracked(Ty::Alert, 20.0, 0.24, "SURGE", tok::DANGER_WHITE)).insert(crate::theme::ink_shadow());
        let from = ["from the north", "from the east", "from the south", "from the west"][side];
        t.spawn(kit.text_px(Ty::Strong, 16.0, from, hx(0xFFD8D0)));
    });
}

// ───────────────────────────── boss bar ─────────────────────────────

fn build_boss(
    c: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &gf_content::ContentDb,
    b: &BossView,
    warlord: bool,
) -> BossParts {
    let def = db.enemies.try_get(b.enemy);
    let name = def.map_or("THE UNNAMED".to_string(), |d| d.name.to_uppercase());
    let phases = def.and_then(|d| db.bosses.by_key(&d.key)).map(|s| s.phases.clone()).unwrap_or_default();
    let w = region::BOSS_BAR[2] - region::BOSS_BAR[0];
    let mut parts = BossParts { bar: Entity::PLACEHOLDER, shake: Entity::PLACEHOLDER, phase: Entity::PLACEHOLDER };
    uikit::halo(c, uikit::abs(w / 2.0 - 490.0, 60.0 - 85.0, 980.0, 170.0), tok::POOL, 0.7);
    c.spawn((Node { justify_content: JustifyContent::Center, ..uikit::abs(0.0, 2.0, w, 16.0) }, Pickable::IGNORE))
        .with_children(|k| {
            k.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.4, if warlord { "WARLORD" } else { "BOSS" }, tok::ENEMY_LABEL))
                .insert(crate::theme::ink_shadow());
        });
    c.spawn((
        Node {
            justify_content: JustifyContent::Center,
            align_items: AlignItems::Center,
            column_gap: px(14.0),
            ..uikit::abs(0.0, 18.0, w, 42.0)
        },
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        let mut left = kit.tex("ornaments/emberknot_rule@2x.png");
        left.flip_x = true;
        r.spawn((Node { width: px(92.0), height: px(14.0), ..default() }, left, Pickable::IGNORE));
        uikit::gradient_text(r, kit, Ty::BossName, 30.0, &name, &[hx(0xFFF4E0), hx(0xFFD2A0), hx(0xE8783A)], true);
        r.spawn((
            Node { width: px(92.0), height: px(14.0), ..default() },
            kit.tex("ornaments/emberknot_rule@2x.png"),
            Pickable::IGNORE,
        ));
    });
    parts.shake = c
        .spawn((uikit::abs(40.0, 62.0, 620.0, 18.0), UiTransform::default(), Pickable::IGNORE))
        .with_children(|b| {
            parts.bar = uikit::bar(b, kit, BarSpec::new(620.0, 18.0, BarFill::Boss).horns());
            let notches: Vec<f32> = phases.iter().map(|p| p.below).filter(|v| *v > 0.0 && *v < 1.0).collect();
            b.spawn((uikit::abs(0.0, 0.0, 620.0, 0.0), Pickable::IGNORE)).with_children(|n| {
                uikit::notches(n, kit, 620.0, &notches);
            });
            // The crest gem: danger, at the bottom centre.
            b.spawn((
                uikit::centered_at(310.0, 18.0, 11.0, 11.0),
                kit.tex_tinted("ornaments/gem_white@2x.png", tok::DANGER),
                ZIndex(4),
                Pickable::IGNORE,
            ));
        })
        .id();
    c.spawn((Node { justify_content: JustifyContent::Center, ..uikit::abs(0.0, 90.0, w, 22.0) }, Pickable::IGNORE))
        .with_children(|p| {
            parts.phase = p
                .spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.24, "", tok::ENEMY_PHASE))
                .insert(crate::theme::ink_shadow())
                .id();
        });
    parts
}

pub(super) fn boss_bar(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    kit: Res<UiKit>,
    mut t: ResMut<Top>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let dt = time.delta_secs();
    let Some(world) = link.latest.as_deref() else { return };
    let boss = world.run.boss.map(|b| (b, false)).or(world.private.boss.map(|b| (b, true)));
    match boss.filter(|(b, _)| b.hp_frac > 0.0) {
        Some((b, warlord)) => {
            if t.boss_key != Some((b.enemy, warlord)) {
                t.boss_key = Some((b.enemy, warlord));
                t.boss_t = 0.0;
                let body = t.boss_body;
                commands.entity(body).despawn_children();
                commands.entity(body).insert(FadeGroup::new(0.0));
                let mut parts = None;
                commands.entity(body).with_children(|c| parts = Some(build_boss(c, &kit, db, &b, warlord)));
                t.boss = parts;
                t.boss_phase_n = b.phase;
            }
            t.boss_t = (t.boss_t + dt).min(10.0);
            if let Some(p) = t.boss {
                ui.bar(p.bar, b.hp_frac, 0.0);
                let phase_name = db
                    .enemies
                    .try_get(b.enemy)
                    .and_then(|d| db.bosses.by_key(&d.key))
                    .and_then(|s| s.phases.get(b.phase as usize))
                    .map_or(String::new(), |p| p.name.to_uppercase());
                let line = if phase_name.is_empty() {
                    String::new()
                } else {
                    format!("{} · {phase_name}", roman(b.phase as u32 + 1))
                };
                ui.text(p.phase, line);
            }
            if b.phase != t.boss_phase_n {
                t.boss_phase_n = b.phase;
                t.shake_t = 0.0;
            }
        }
        None => {
            t.boss_t = -1.0;
            t.boss_key = None;
        }
    }
    // Slide down 300 ms on engage; a 2 px shake for 200 ms on a phase change.
    let on = t.boss_t >= 0.0;
    ui.show(t.boss_root, on);
    if on {
        let k = 1.0 - (1.0 - (t.boss_t / 0.3).min(1.0)).powi(3);
        ui.transform(t.boss_root, Vec2::new(0.0, -30.0 * (1.0 - k)), 1.0);
        ui.fade(t.boss_body, k);
        t.shake_t += dt;
        let shake = if t.shake_t < 0.2 { 2.0 * (t.shake_t * 90.0).sin() } else { 0.0 };
        if let Some(p) = t.boss {
            ui.transform(p.shake, Vec2::new(shake, 0.0), 1.0);
        }
    }
}

// ───────────────────────────── callouts ─────────────────────────────

/// A static element cabochon (round fill, the element icon, the gilt rim) that fades with its
/// callout. The kit's `element_cabochon` is a live slot, whose state machine owns its tints.
fn cabochon(p: &mut ChildSpawnerCommands, kit: &UiKit, icon: &str, size: f32) {
    p.spawn((Node { width: px(size), height: px(size), flex_shrink: 0.0, ..default() }, Pickable::IGNORE))
        .with_children(|c| {
            c.spawn((uikit::fill(), kit.tex("slots/slot_round_fill@2x.png"), Pickable::IGNORE));
            let i = (size * 0.7).round();
            c.spawn((uikit::centered(i, i), uikit::icon_bundle(icon, i, Color::WHITE)));
            c.spawn((uikit::fill(), kit.tex("slots/slot_round_rim@2x.png"), Pickable::IGNORE));
        });
}

/// Build a callout: the name with its gradient, element cabochons for synergies, ×N, and the
/// ember-knot underline. Returns the ×N text.
fn build_callout(
    c: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &gf_content::ContentDb,
    link: &Link,
    kind: &CallKind,
    count: u32,
) -> Entity {
    let gold = [hx(0xFFFBEA), hx(0xFFD36B), hx(0xFFB23A)];
    let (name, stops, elements, sub): (String, Vec<Color>, Option<(&str, &str)>, Option<(String, Color)>) = match kind {
        CallKind::Synergy(id) => {
            let s = db.synergies.try_get(*id);
            let (a, b) =
                s.map_or((gf_core::damage::DamageType::Kinetic, gf_core::damage::DamageType::Kinetic), |s| (s.a, s.b));
            (
                s.map_or("SYNERGY".to_string(), |s| s.name.to_uppercase()),
                vec![hx(0xFFF8E6), element_color(a), element_color(b)],
                Some((ik::element(a), ik::element(b))),
                None,
            )
        }
        CallKind::Combo(id, slot) => (
            db.recipes.try_get(*id).map_or("NAMED COMBO".to_string(), |r| r.name.to_uppercase()),
            gold.to_vec(),
            None,
            Some((
                format!("NAMED COMBO · {}", player_name(link, *slot).to_uppercase()),
                player_color(db, *slot as usize),
            )),
        ),
        CallKind::Overdrive(slot) => (
            "TEAM OVERDRIVE".to_string(),
            gold.to_vec(),
            None,
            Some((player_name(link, *slot).to_uppercase(), player_color(db, *slot as usize))),
        ),
        CallKind::OverdriveReady => ("TEAM OVERDRIVE READY".to_string(), gold.to_vec(), None, None),
    };
    let mut times = Entity::PLACEHOLDER;
    uikit::halo(
        c,
        Node {
            position_type: PositionType::Absolute,
            left: px(120.0),
            right: px(120.0),
            top: px(-18.0),
            bottom: px(-14.0),
            ..default()
        },
        tok::POOL,
        0.62,
    );
    if let Some((s, col)) = &sub {
        c.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.3, s.as_str(), *col)).insert(crate::theme::ink_shadow());
    }
    c.spawn((uikit::row(12.0), Pickable::IGNORE)).with_children(|r| {
        if let Some((a, _)) = elements {
            cabochon(r, kit, a, 30.0);
        }
        if matches!(kind, CallKind::Combo(..)) {
            uikit::icon(r, "run/named_combo", 30.0, Color::WHITE);
        }
        uikit::gradient_text(r, kit, Ty::Callout, 38.0, &name, &stops, true);
        if matches!(kind, CallKind::OverdriveReady) {
            uikit::keycap(r, kit, "V", 24.0);
        }
        if let Some((_, b)) = elements {
            cabochon(r, kit, b, 30.0);
        }
        times = r
            .spawn((
                Node { display: if count > 1 { Display::Flex } else { Display::None }, ..default() },
                kit.text_px(Ty::Num, 26.0, format!("×{count}"), tok::GOLD_LT),
                UiTransform::default(),
            ))
            .id();
    });
    let w = (name.chars().count() as f32 * 30.0 + 80.0).clamp(240.0, 860.0);
    uikit::ember_knot(c, kit, w, Gem::None, 0.9);
    times
}

#[allow(clippy::too_many_arguments)]
pub(super) fn callouts(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    kit: Res<UiKit>,
    settings: Res<crate::input::Settings>,
    mut t: ResMut<Top>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let dt = time.delta_secs();
    let Some(world) = link.latest.as_deref() else { return };
    let mut fresh: Vec<CallKind> = Vec::new();
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::Synergy { synergy, .. } => fresh.push(CallKind::Synergy(synergy)),
            GameEvent::RecipeDiscovered { slot, recipe } => fresh.push(CallKind::Combo(recipe, slot)),
            GameEvent::Overdrive { slot } => fresh.push(CallKind::Overdrive(slot)),
            _ => {}
        }
    }
    // TEAM OVERDRIVE READY plays once per charge.
    let ready = world.run.overdrive_meter >= 1.0 && world.run.overdrive_active <= 0.0;
    if ready && !t.od_ready_was {
        fresh.push(CallKind::OverdriveReady);
    }
    t.od_ready_was = ready;

    let mut rebuild = false;
    let times_e = t.call_times;
    for kind in fresh {
        match t.call.as_mut() {
            Some(c) if c.kind == kind && c.age < CALL_IN + CALL_HOLD + CALL_OUT => {
                c.count += 1;
                c.age = c.age.min(CALL_IN + 0.2);
                if let Some(e) = times_e {
                    ui.text(e, format!("×{}", c.count));
                    ui.show(e, true);
                    commands.entity(e).insert(uikit::pop(0.1, 0.1));
                }
            }
            Some(c) if c.age < CALL_IN + CALL_HOLD && kind.prio() < c.kind.prio() => {}
            _ => {
                t.call = Some(Callout { kind, count: 1, age: 0.0 });
                rebuild = true;
            }
        }
    }
    let root = t.call_root;
    if rebuild && let Some(c) = t.call.clone() {
        commands.entity(root).despawn_children();
        commands.entity(root).insert(FadeGroup::new(0.0));
        let mut times = None;
        commands.entity(root).with_children(|p| times = Some(build_callout(p, &kit, db, &link, &c.kind, c.count)));
        t.call_times = times;
    }
    // The lane drops under the boss bar while it shows.
    let baseline = if t.boss_t >= 0.0 { region::CALLOUT_BASELINE_BOSS } else { region::CALLOUT_BASELINE };
    if let Ok(mut n) = ui.nodes.get_mut(root) {
        let top = px(baseline - 38.0 - 16.0);
        if n.top != top {
            n.top = top;
        }
    }
    let Some(c) = t.call.as_mut() else {
        ui.show(root, false);
        return;
    };
    c.age += dt;
    let age = c.age;
    if age > CALL_IN + CALL_HOLD + CALL_OUT {
        t.call = None;
        ui.show(root, false);
        return;
    }
    ui.show(root, true);
    // 1.3 → 1.0 over 160 ms (back-out), alpha in over 100 ms; hold; rise 12 px and fade 300 ms.
    let calm = settings.reduced_motion;
    let k = (age / CALL_IN).min(1.0);
    let back = {
        let (c1, c3) = (1.70158, 2.70158);
        1.0 + c3 * (k - 1.0).powi(3) + c1 * (k - 1.0).powi(2)
    };
    let scale = if calm { 1.0 } else { 1.3 + (1.0 - 1.3) * back };
    let out = ((age - CALL_IN - CALL_HOLD) / CALL_OUT).clamp(0.0, 1.0);
    let alpha = (age / 0.1).min(1.0) * (1.0 - out);
    ui.transform(root, Vec2::new(0.0, -12.0 * out), scale);
    ui.fade(root, alpha);
}

// ───────────────────────────── region banner ─────────────────────────────

fn build_banner(c: &mut ChildSpawnerCommands, kit: &UiKit, name: &str, sub: &str, gate: bool) {
    let w = (name.chars().count() as f32 * 33.0 + 180.0).clamp(300.0, 900.0);
    uikit::halo(
        c,
        Node {
            position_type: PositionType::Absolute,
            left: percent(50.0),
            top: px(-20.0),
            width: px(w + 420.0),
            height: px(170.0),
            margin: UiRect::left(px(-(w + 420.0) / 2.0)),
            ..default()
        },
        tok::POOL,
        0.7,
    );
    if gate {
        uikit::icon(c, "run/gate_open", 40.0, tok::GOLD_LT);
    }
    uikit::ember_knot(c, kit, w, Gem::Ivory, 1.0);
    uikit::gradient_text(c, kit, Ty::Banner, 44.0, name, &[hx(0xFFF4D0), tok::GOLD_LT, hx(0xB07A30)], true);
    c.spawn(kit.text_px(Ty::Flavour, 18.0, sub, tok::PARCH_DIM));
}

#[allow(clippy::too_many_arguments)]
pub(super) fn region_banner(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    kit: Res<UiKit>,
    mut t: ResMut<Top>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let root = t.banner_root;
    let biome =
        link.latest.as_deref().and_then(|w| db.biomes.try_get(w.run.biome)).map_or("", |b| b.name.as_str()).to_string();
    let mut show: Option<(String, String, bool)> = None;
    // GATE OPEN uses the banner with the gate glyph.
    if link.fresh_events.iter().any(|e| matches!(e, GameEvent::GateOpened { .. })) {
        show = Some(("GATE OPEN".into(), "the Boss Gate is open · gather at it".into(), true));
    }
    let here = room.def.map.as_deref().zip(link.me()).and_then(|(map, me)| {
        let (x, y) = map.tiles.tile_of(me.mover.pos)?;
        let r = *map.tiles.region.get(map.tiles.index(x, y))?;
        let reg = map.regions.get(r as usize)?;
        let theme = room.def.expedition.as_ref()?.themes.get(reg.theme as usize)?;
        Some((r, theme.region_name(reg.name).to_uppercase(), theme.name.clone()))
    });
    if let Some((r, name, theme)) = here
        && t.banner_region != Some((room.generation, r))
    {
        t.banner_region = Some((room.generation, r));
        if show.is_none() {
            let sub = if theme.is_empty() || theme.to_uppercase() == name {
                biome.clone()
            } else {
                format!("{biome} · {theme}")
            };
            show = Some((name, sub, false));
        }
    }
    if let Some((name, sub, gate)) = show {
        commands.entity(root).despawn_children();
        commands.entity(root).insert(FadeGroup::new(0.0));
        commands.entity(root).with_children(|c| build_banner(c, &kit, &name, &sub, gate));
        t.banner_t = 0.0;
    }
    t.banner_t += time.delta_secs();
    // Suppressed while the boss bar shows.
    let on = t.banner_t < BANNER_LIFE && t.boss_t < 0.0;
    ui.show(root, on);
    if on {
        let a = (t.banner_t / 0.35).min(1.0) * (1.0 - ((t.banner_t - (BANNER_LIFE - 1.0)) / 1.0).clamp(0.0, 1.0));
        ui.fade(root, a);
    }
}

// ───────────────────────────── surge ─────────────────────────────

pub(super) fn surge(time: Res<Time>, cfg: Res<ClientConfig>, clock: Res<SurgeClock>, t: Res<Top>, mut ui: Ui) {
    let db = db(&cfg);
    let now = time.elapsed_secs();
    for (side, root) in t.surge.iter().enumerate() {
        let on = clock.started.is_some() && clock.side == side;
        ui.show(*root, on);
        if !on {
            continue;
        }
        let age = now - clock.started.unwrap_or(now);
        let tune = &db.game.expedition.horde.surge;
        // The 3 s warning pulses; during the surge the flash dims to 0.25.
        let a = if clock.warn {
            0.55 + 0.45 * (age * std::f32::consts::TAU * 1.5).sin().abs()
        } else {
            let fade_in = 1.0 - (age / 0.6).min(1.0);
            let tail = ((tune.duration - age) / 1.0).clamp(0.0, 1.0);
            (0.25 + 0.75 * fade_in) * tail
        };
        ui.fade(*root, a);
    }
}
