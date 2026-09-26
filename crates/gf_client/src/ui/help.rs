//! Help (UI_STYLE §7.4): THE ARSENAL'S LAW, a centred gilt tome over a 0.55 scrim. The world keeps
//! running. Rows pair an action icon and verb with its key and its pad button; the footer's
//! switches toggle damage numbers, shake, the debug strip, the HUD size and reduced motion.

use super::{CapturesPointer, Fit, Nav, PanelKind, PanelState, PanelWorld, UiAction, key_of, layer, me_in};
use crate::ClientConfig;
use crate::input::Settings;
use crate::net::Link;
use crate::theme::{HudScale, Ty, hx, tok, z};
use crate::uikit::{
    Gem, Key, PanelStyle, UiKit, abs, chip, ember_knot, gilt_panel, gradient_text, icon, ik, key_chip, row,
};
use gf_core::aim::AimMode;
use gf_engine::client::{Hovered, Pickable};
use gf_engine::prelude::*;

const W: f32 = 1040.0;
const H: f32 = 640.0;

/// A footer switch.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Switch {
    DamageNumbers,
    Shake,
    DebugStrip,
    HudSize,
    ReducedMotion,
}

/// Flip a switch (the HUD size steps 85 % → 100 % → 115 %).
pub(super) fn toggle(s: Switch, settings: &mut Settings, hud: &mut HudScale) {
    match s {
        Switch::DamageNumbers => settings.damage_numbers = !settings.damage_numbers,
        Switch::Shake => settings.screen_shake = if settings.screen_shake > 0.0 { 0.0 } else { 1.0 },
        Switch::DebugStrip => settings.debug_strip = !settings.debug_strip,
        Switch::ReducedMotion => settings.reduced_motion = !settings.reduced_motion,
        Switch::HudSize => {
            hud.0 = if hud.0 < 0.95 {
                1.0
            } else if hud.0 < 1.1 {
                1.15
            } else {
                0.85
            }
        }
    }
}

#[derive(Default)]
pub(super) struct HelpUi {
    root: Option<Entity>,
    key: u64,
}

#[allow(clippy::too_many_arguments)]
pub(super) fn sync(
    mut commands: Commands,
    kit: Res<UiKit>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pw: Res<PanelWorld>,
    state: Res<PanelState>,
    settings: Res<Settings>,
    hud: Res<HudScale>,
    mut ui: Local<HelpUi>,
) {
    if !state.help {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.key = 0;
        return;
    }
    let character =
        pw.get(&link).and_then(|w| me_in(w, link.slot)).and_then(|p| cfg.content.characters.try_get(p.character)).map(
            |c| {
                // Kit strings read "Name: what it does"; the law lists the names.
                let name = |s: &str| s.split(':').next().unwrap_or(s).trim().to_string();
                (c.key.clone(), name(&c.active1), name(&c.active2), name(&c.ultimate))
            },
        );
    let key = key_of(format!(
        "{}{}{}{}{}{:?}",
        settings.damage_numbers,
        settings.screen_shake > 0.0,
        settings.debug_strip,
        settings.reduced_motion,
        hud.0,
        character
    ));
    if ui.key == key && ui.root.is_some() {
        return;
    }
    let entrance = ui.root.is_none();
    if let Some(r) = ui.root.take() {
        commands.entity(r).despawn();
    }
    ui.key = key;
    let auto_tax = (1.0 - cfg.content.aim_params(AimMode::Auto).damage_mult) * 100.0;
    ui.root = Some(spawn_help(&mut commands, &kit, character, auto_tax, &settings, hud.0, entrance));
}

/// A help row: icon, verb, keyboard keys, pad button.
struct Line {
    icon: String,
    verb: String,
    keys: Vec<Key<'static>>,
    pad: Option<&'static str>,
}

fn line(icon: &str, verb: impl Into<String>, keys: Vec<Key<'static>>, pad: Option<&'static str>) -> Line {
    Line { icon: icon.to_string(), verb: verb.into(), keys, pad }
}

fn spawn_help(
    commands: &mut Commands,
    kit: &UiKit,
    character: Option<(String, String, String, String)>,
    auto_tax: f32,
    settings: &Settings,
    hud_scale: f32,
    entrance: bool,
) -> Entity {
    use Key::{Icon, Text};
    let (ck, q, e, r) =
        character.unwrap_or_else(|| ("valdris".into(), "Ability I".into(), "Ability II".into(), "Ultimate".into()));
    let groups: [(&str, Vec<Line>); 4] = [
        (
            "MOVE & FIGHT",
            vec![
                line("ui/bearing", "Move", vec![Text("W"), Text("A"), Text("S"), Text("D")], Some("input/pad_ls")),
                line("aim/manual", "Aim", vec![Text("Mouse")], Some("input/pad_rs")),
                line("ui/spark4", "Fire", vec![Icon("input/mouse_lmb")], Some("input/pad_rt")),
                line("states/infinite_dash", "Dash", vec![Text("Space")], Some("input/pad_rb")),
            ],
        ),
        (
            "KIT",
            vec![
                line(&ik::kit(&ck, "q"), q, vec![Text("Q")], Some("input/pad_lb")),
                line(&ik::kit(&ck, "e"), e, vec![Text("E"), Icon("input/mouse_rmb")], Some("input/pad_lt")),
                line(&ik::kit(&ck, "r"), r, vec![Text("R")], Some("input/pad_north")),
                line("team/overdrive", "Team Overdrive", vec![Text("V")], Some("input/pad_east")),
            ],
        ),
        (
            "WORLD",
            vec![
                line("ui/confirm", "Interact · revive", vec![Text("F")], Some("input/pad_west")),
                line("poi/anvil", "Forge or boons", vec![Text("Tab")], Some("input/pad_view")),
                line("team/ping", "Ping", vec![Text("G"), Icon("input/mouse_mmb")], Some("input/pad_rs_click")),
                line("aim/bias_pinned", "Force the target", vec![Text("T")], None),
                line("aim/bias_balanced", "Target bias", vec![Text("B")], Some("input/pad_dpad_right")),
            ],
        ),
        (
            "AIM",
            vec![
                line("aim/auto", format!("Auto · −{auto_tax:.0}% damage"), vec![Text("F1")], None),
                line("aim/assisted", "Assisted · a magnetism cone", vec![Text("F2")], None),
                line("aim/manual", "Manual · precision and Deadeye", vec![Text("F3")], None),
                line("ui/reroll", "Cycle the aim mode", vec![Text("M")], Some("input/pad_dpad_up")),
            ],
        ),
    ];
    commands
        .spawn(layer(z::HELP))
        .with_children(|l| {
            l.spawn((crate::uikit::fill(), BackgroundColor(tok::SCRIM.with_alpha(0.55)), Pickable::IGNORE));
            let mut cv = l.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: percent(50.0),
                    top: percent(50.0),
                    width: px(W),
                    height: px(H),
                    margin: UiRect { left: px(-W / 2.0), top: px(-H / 2.0 + 10.0), ..default() },
                    ..default()
                },
                Fit { size: Vec2::new(W, H + 40.0), pivot: Vec2::ZERO, pad: Vec2::new(24.0, 24.0) },
                CapturesPointer,
                Hovered::default(),
            ));
            if entrance {
                cv.insert(crate::uikit::Tween::new(
                    crate::uikit::TweenTarget::Translate(Vec2::new(0.0, 16.0), Vec2::ZERO),
                    0.2,
                ));
            }
            cv.with_children(|cv| {
                // An opaque backing so nothing under the tome ghosts through its lacquer.
                cv.spawn((abs(6.0, 6.0, W - 12.0, H - 12.0), BackgroundColor(hx(0x120D0A)), Pickable::IGNORE));
                gilt_panel(cv, kit, abs(0.0, 0.0, W, H), PanelStyle::horns(64).crest(62), |d| {
                    d.spawn((
                        Node {
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::Center,
                            row_gap: px(8.0),
                            ..abs(0.0, 30.0, W, 60.0)
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|t| {
                        gradient_text(
                            t,
                            kit,
                            Ty::Title,
                            30.0,
                            "THE ARSENAL'S LAW",
                            &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                            false,
                        );
                        ember_knot(t, kit, 440.0, Gem::Ivory, 1.0);
                    });
                    // Close, top right.
                    d.spawn((abs(W - 76.0, 26.0, 40.0, 30.0), Pickable::IGNORE)).with_children(|c| {
                        let x = chip(c, kit, "", Some("ui/close"), 40.0, |_| {});
                        c.commands_mut().entity(x).insert((UiAction::CloseHelp, Nav(PanelKind::Help)));
                    });
                    let [g0, g1, g2, g3] = groups;
                    column(d, kit, 48.0, [g0, g1]);
                    column(d, kit, W / 2.0 + 16.0, [g2, g3]);
                    d.spawn((
                        Node { justify_content: JustifyContent::Center, ..abs(0.0, 512.0, W, 14.0) },
                        Pickable::IGNORE,
                    ))
                    .with_children(|k| {
                        ember_knot(k, kit, W - 200.0, Gem::None, 0.7);
                    });
                    switches(d, kit, settings, hud_scale);
                    d.spawn((
                        Node {
                            justify_content: JustifyContent::Center,
                            column_gap: px(8.0),
                            ..abs(0.0, 592.0, W, 24.0)
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|f| {
                        key_chip(f, kit, Key::Text("H"), 20.0);
                        f.spawn(kit.text_flat(
                            Ty::Flavour,
                            15.0,
                            "or Esc closes the law · the world keeps moving",
                            tok::PARCH_MUTE,
                        ));
                    });
                });
            });
        })
        .id()
}

fn column(d: &mut ChildSpawnerCommands, kit: &UiKit, x: f32, groups: [(&str, Vec<Line>); 2]) {
    d.spawn((
        Node { flex_direction: FlexDirection::Column, row_gap: px(0.0), ..abs(x, 104.0, W / 2.0 - 64.0, 400.0) },
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        for (gi, (title, lines)) in groups.iter().enumerate() {
            c.spawn((
                Node {
                    height: px(30.0),
                    align_items: AlignItems::Center,
                    margin: UiRect::top(px(if gi > 0 { 14.0 } else { 0.0 })),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|h| {
                h.spawn((Node { flex_grow: 1.0, ..default() }, Pickable::IGNORE)).with_children(|t| {
                    t.spawn(kit.text_flat(Ty::Label, 15.0, *title, tok::GOLD_LT));
                });
                if gi == 0 {
                    h.spawn((
                        Node { width: px(150.0), justify_content: JustifyContent::FlexEnd, ..default() },
                        Pickable::IGNORE,
                    ))
                    .with_children(|t| {
                        t.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "KEYS", tok::PARCH_DIM));
                    });
                    h.spawn((
                        Node { width: px(56.0), justify_content: JustifyContent::Center, ..default() },
                        Pickable::IGNORE,
                    ))
                    .with_children(|t| {
                        t.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "PAD", tok::PARCH_DIM));
                    });
                }
            });
            // A hairline under the group title.
            c.spawn((
                Node { height: px(1.0), margin: UiRect::bottom(px(4.0)), ..default() },
                BackgroundGradient(vec![
                    LinearGradient::to_right(vec![
                        ColorStop::auto(tok::GOLD_MD.with_alpha(0.6)),
                        ColorStop::auto(tok::GOLD_DK.with_alpha(0.0)),
                    ])
                    .into(),
                ]),
                Pickable::IGNORE,
            ));
            for l in lines {
                c.spawn((
                    Node { height: px(30.0), align_items: AlignItems::Center, column_gap: px(10.0), ..default() },
                    Pickable::IGNORE,
                ))
                .with_children(|r| {
                    icon(r, &l.icon, 22.0, tok::BONE);
                    r.spawn((Node { flex_grow: 1.0, ..default() }, Pickable::IGNORE)).with_children(|t| {
                        t.spawn(kit.text_flat(Ty::BodyS, 16.0, l.verb.clone(), tok::PARCH));
                    });
                    r.spawn((
                        Node {
                            width: px(150.0),
                            justify_content: JustifyContent::FlexEnd,
                            column_gap: px(4.0),
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|k| {
                        for key in &l.keys {
                            key_chip(k, kit, *key, 20.0);
                        }
                    });
                    r.spawn((
                        Node { width: px(56.0), justify_content: JustifyContent::Center, ..default() },
                        Pickable::IGNORE,
                    ))
                    .with_children(|k| match l.pad {
                        Some(p) => {
                            icon(k, p, 24.0, Color::WHITE);
                        }
                        None => {
                            k.spawn(kit.text_flat(Ty::Micro, 12.0, "–", tok::PARCH_MUTE));
                        }
                    });
                });
            }
        }
    });
}

fn switches(d: &mut ChildSpawnerCommands, kit: &UiKit, settings: &Settings, hud_scale: f32) {
    let items: [(Switch, &str, Option<&str>, Option<bool>, f32); 5] = [
        (Switch::DamageNumbers, "Damage numbers", Some("N"), Some(settings.damage_numbers), 196.0),
        (Switch::Shake, "Screen shake", Some("K"), Some(settings.screen_shake > 0.0), 176.0),
        (Switch::DebugStrip, "Debug strip", Some("F10"), Some(settings.debug_strip), 186.0),
        (Switch::HudSize, "HUD size", None, None, 164.0),
        (Switch::ReducedMotion, "Reduced motion", None, Some(settings.reduced_motion), 180.0),
    ];
    d.spawn((Node { justify_content: JustifyContent::Center, ..abs(0.0, 544.0, W, 30.0) }, Pickable::IGNORE))
        .with_children(|r| {
            r.spawn((row(10.0), Pickable::IGNORE)).with_children(|r| {
                for (s, label, key, on, width) in items {
                    let e = chip(r, kit, label, None, width, |t| {
                        match on {
                            Some(on) => {
                                // A lozenge switch: the dot sits right and glows when on.
                                t.spawn((
                                    Node {
                                        width: px(24.0),
                                        height: px(12.0),
                                        border: UiRect::all(px(1.0)),
                                        border_radius: BorderRadius::MAX,
                                        justify_content: if on {
                                            JustifyContent::FlexEnd
                                        } else {
                                            JustifyContent::FlexStart
                                        },
                                        align_items: AlignItems::Center,
                                        padding: UiRect::horizontal(px(1.0)),
                                        ..default()
                                    },
                                    BackgroundColor(tok::LAC0),
                                    BorderColor::all(if on { tok::GOLD_MD } else { tok::GOLD_DK.with_alpha(0.7) }),
                                    Pickable::IGNORE,
                                ))
                                .with_children(|sw| {
                                    sw.spawn((
                                        Node {
                                            width: px(8.0),
                                            height: px(8.0),
                                            border_radius: BorderRadius::MAX,
                                            ..default()
                                        },
                                        BackgroundColor(if on { tok::ICHOR } else { tok::PARCH_MUTE }),
                                        if on {
                                            crate::uikit::glow(tok::ICHOR_GLOW.with_alpha(0.6), 5.0, 0.0)
                                        } else {
                                            BoxShadow::default()
                                        },
                                        Pickable::IGNORE,
                                    ));
                                });
                            }
                            None => {
                                t.spawn(kit.text_flat(Ty::Num, 14.0, format!("{:.0}%", hud_scale * 100.0), tok::ICHOR));
                            }
                        }
                        if let Some(k) = key {
                            key_chip(t, kit, Key::Text(k), 18.0);
                        }
                    });
                    r.commands_mut().entity(e).insert((UiAction::Toggle(s), Nav(PanelKind::Help)));
                }
            });
        });
}
