//! The end of the run (UI_STYLE §7.3): VICTORY or THE FORGE GOES COLD over the dimmed world, the
//! run's stats counting up, one gilt card per player (the MVP in gold, the rest in bronze) and
//! FORGE AGAIN / LEAVE. Defeat is cold iron, never red.

use super::{CountUp, Fit, Nav, NumFmt, PanelKind, PanelState, PanelWorld, UiAction, key_of, layer};
use crate::ClientConfig;
use crate::input::{Device, InputState};
use crate::net::Link;
use crate::palette::rarity_color;
use crate::theme::{Ty, god_colors, hx, player_color, tok, z};
use crate::uikit::{
    BarFill, BarSpec, ButtonKind, Gem, Key, KitBar, MedallionSpec, PanelStyle, SlotShape, SlotSpec, Tween, TweenTarget,
    UiKit, abs, bar, button, centered_at, ember_knot, gilt_panel, gradient_text, halo, icon, ik, key_chip, medallion,
    pchip, rarity_gem, slot,
};
use gf_content::ContentDb;
use gf_core::forge::Slot;
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::{PlayerView, RunPhase, WorldSnapshot};

/// The canvas: the spec's 1920 layout minus 240 px on each side.
const CW: f32 = 1440.0;
const CH: f32 = 950.0;
const CX: f32 = CW / 2.0;

#[derive(Default)]
pub(super) struct EndUi {
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
    input: Res<InputState>,
    mut ui: Local<EndUi>,
) {
    let w = pw.get(&link).filter(|_| state.end);
    let Some(w) = w else {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.key = 0;
        return;
    };
    let key = key_of(format!(
        "{:?}{}{:?}{:?}",
        w.run.phase,
        w.run.kills,
        w.players.iter().map(|p| (p.slot, p.kills, p.damage as u32)).collect::<Vec<_>>(),
        input.device
    ));
    if ui.key == key && ui.root.is_some() {
        return;
    }
    if let Some(r) = ui.root.take() {
        commands.entity(r).despawn();
    }
    ui.key = key;
    ui.root = Some(spawn_end(&mut commands, &kit, &cfg.content, &link, w, input.device));
}

/// One number in the stat row.
struct Stat {
    icon: &'static str,
    label: &'static str,
    value: f64,
    fmt: NumFmt,
    /// Shown as is, without counting (`7 / 7`).
    fixed: Option<String>,
}

fn stats(w: &WorldSnapshot) -> Vec<Stat> {
    let damage: f64 = w.players.iter().map(|p| p.damage as f64).sum();
    let mut out = Vec::new();
    let time = w.run.stage.map_or(w.run.time, |s| s.time.max(w.run.time));
    out.push(Stat { icon: "run/hourglass", label: "TIME", value: time as f64, fmt: NumFmt::Clock, fixed: None });
    out.push(Stat {
        icon: "run/kills",
        label: "KILLS",
        value: w.run.kills as f64,
        fmt: NumFmt::Thousands,
        fixed: None,
    });
    match w.run.stage {
        Some(s) => {
            out.push(Stat {
                icon: "currency/seal",
                label: "SEALS",
                value: s.seals as f64,
                fmt: NumFmt::Thousands,
                fixed: Some(format!("{} / {}", s.seals, s.required)),
            });
            out.push(Stat {
                icon: "ui/check",
                label: "OBJECTIVES",
                value: s.objectives as f64,
                fmt: NumFmt::Thousands,
                fixed: None,
            });
        }
        None => {
            out.push(Stat {
                icon: "run/gate_open",
                label: "CHAMBERS",
                value: w.run.depth as f64,
                fmt: NumFmt::Thousands,
                fixed: None,
            });
        }
    }
    out.push(Stat { icon: "ui/spark4", label: "DAMAGE", value: damage, fmt: NumFmt::Thousands, fixed: None });
    out.push(Stat {
        icon: "currency/ember",
        label: "EMBER",
        value: w.run.ember as f64,
        fmt: NumFmt::Signed,
        fixed: None,
    });
    out
}

fn spawn_end(
    commands: &mut Commands,
    kit: &UiKit,
    db: &ContentDb,
    link: &Link,
    w: &WorldSnapshot,
    device: Device,
) -> Entity {
    let victory = w.run.phase == RunPhase::Victory;
    let biome = db.biomes.try_get(w.run.biome).map_or("the Shatterlands".to_string(), |b| b.name.clone());
    let pad = device == Device::Gamepad;
    commands
        .spawn(layer(z::END))
        .with_children(|l| {
            // The world, dimmed with a vignette (§7.3).
            l.spawn((crate::uikit::fill(), BackgroundColor(hx(0x080508).with_alpha(0.8))));
            l.spawn((
                crate::uikit::fill(),
                BackgroundGradient(vec![
                    RadialGradient::new(
                        UiPosition::CENTER,
                        RadialGradientShape::FarthestCorner,
                        vec![
                            ColorStop::percent(Color::BLACK.with_alpha(0.0), 45.0),
                            ColorStop::percent(Color::BLACK.with_alpha(0.7), 100.0),
                        ],
                    )
                    .into(),
                ]),
                Pickable::IGNORE,
            ));
            l.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: percent(50.0),
                    top: percent(50.0),
                    width: px(CW),
                    height: px(CH),
                    margin: UiRect { left: px(-CW / 2.0), top: px(-CH / 2.0), ..default() },
                    ..default()
                },
                Fit { size: Vec2::new(CW, CH), pivot: Vec2::ZERO, pad: Vec2::new(24.0, 16.0) },
                Pickable::IGNORE,
            ))
            .with_children(|cv| {
                crest(cv, kit, victory);
                title(cv, kit, victory);
                cv.spawn((
                    Node { justify_content: JustifyContent::Center, ..abs(0.0, 323.0, CW, 14.0) },
                    Pickable::IGNORE,
                ))
                .with_children(|k| {
                    ember_knot(
                        k,
                        kit,
                        660.0,
                        if victory { Gem::Amber } else { Gem::None },
                        if victory { 1.0 } else { 0.6 },
                    );
                });
                let line = if victory {
                    format!("The Last Arsenal holds. {biome} is quiet again.")
                } else {
                    format!("The horde keeps {biome}. The anvils will wake again.")
                };
                cv.spawn((
                    Node { justify_content: JustifyContent::Center, ..abs(0.0, 340.0, CW, 32.0) },
                    Pickable::IGNORE,
                ))
                .with_children(|t| {
                    t.spawn(kit.text_px(Ty::Flavour, 24.0, line, tok::PARCH));
                });
                stat_row(cv, kit, &stats(w), victory);
                party_cards(cv, kit, db, link, w, victory);
                buttons(cv, kit, pad);
            });
        })
        .id()
}

fn crest(cv: &mut ChildSpawnerCommands, kit: &UiKit, victory: bool) {
    cv.spawn((
        centered_at(CX, 122.0, 300.0, 300.0),
        Tween::new(TweenTarget::Translate(Vec2::new(0.0, -30.0), Vec2::ZERO), 0.3),
        Pickable::IGNORE,
    ))
    .with_children(|c| {
        if victory {
            halo(c, centered_at(150.0, 150.0, 300.0, 300.0), hx(0xFFB23A), 0.35);
        }
        let rays = if victory { Color::WHITE.with_alpha(0.9) } else { hx(0x8A847A).with_alpha(0.35) };
        c.spawn((
            centered_at(150.0, 150.0, 260.0, 260.0),
            kit.tex_tinted("ornaments/sunburst16@2x.png", rays),
            Pickable::IGNORE,
        ));
        c.spawn((centered_at(150.0, 150.0, 116.0, 116.0), Pickable::IGNORE)).with_children(|m| {
            let tint = if victory { tok::GOLD_LT } else { tok::PARCH_MUTE };
            medallion(m, kit, MedallionSpec::new(116.0).glyph("poi/anvil", 0.62, tint));
            if !victory {
                // The crack across a cold crest.
                m.spawn((
                    centered_at(58.0, 58.0, 3.0, 96.0),
                    BackgroundColor(tok::INK.with_alpha(0.85)),
                    UiTransform::from_rotation(Rot2::radians(0.5)),
                    Pickable::IGNORE,
                ));
            }
        });
    });
}

fn title(cv: &mut ChildSpawnerCommands, kit: &UiKit, victory: bool) {
    let (text, size, stops): (&str, f32, Vec<Color>) = if victory {
        ("VICTORY", 96.0, vec![hx(0xFFFBEA), hx(0xF7CE6A), hx(0xD9A441), hx(0xA86A22)])
    } else {
        ("THE FORGE GOES COLD", 64.0, vec![hx(0xE8E2D6), hx(0xB5AC9C), hx(0x7D705E)])
    };
    let top = 300.0 - size * 1.02;
    cv.spawn((
        Node { justify_content: JustifyContent::Center, ..abs(0.0, top, CW, size * 1.3) },
        UiTransform::default(),
        Tween::new(TweenTarget::Scale(1.12, 1.0), 0.6).delay(0.15),
        Pickable::IGNORE,
    ))
    .with_children(|t| {
        if victory {
            halo(
                t,
                Node {
                    position_type: PositionType::Absolute,
                    left: px(CX - 360.0),
                    top: px(-10.0),
                    width: px(720.0),
                    height: px(size * 1.4),
                    ..default()
                },
                hx(0xFFB23A),
                0.16,
            );
        }
        gradient_text(t, kit, Ty::DisplayXl, size, text, &stops, true);
    });
}

fn stat_row(cv: &mut ChildSpawnerCommands, kit: &UiKit, stats: &[Stat], victory: bool) {
    let n = stats.len() as f32;
    let col = 196.0;
    let x0 = CX - n * col / 2.0;
    for (i, s) in stats.iter().enumerate() {
        let x = x0 + i as f32 * col;
        if i > 0 {
            cv.spawn((
                abs(x, 410.0, 1.0, 70.0),
                BackgroundGradient(vec![
                    LinearGradient::to_bottom(vec![
                        ColorStop::auto(tok::GOLD_LT.with_alpha(0.0)),
                        ColorStop::auto(tok::GOLD_MD.with_alpha(0.55)),
                        ColorStop::auto(tok::GOLD_DK.with_alpha(0.0)),
                    ])
                    .into(),
                ]),
                Pickable::IGNORE,
            ));
        }
        cv.spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                ..abs(x, 399.0, col, 100.0)
            },
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            icon(c, s.icon, 34.0, if victory { tok::BONE } else { tok::PARCH_DIM });
            let shown = s.fixed.clone().unwrap_or_else(|| s.fmt.format(0.0));
            let mut v = c.spawn(kit.text_px(Ty::NumL, 30.0, shown, tok::NUMERAL));
            if s.fixed.is_none() {
                v.insert(CountUp { from: 0.0, to: s.value, t: 0.0, dur: 0.8, delay: 0.3, fmt: s.fmt });
            }
            c.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.24, s.label, tok::PARCH_DIM));
        });
    }
}

fn party_cards(
    cv: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    link: &Link,
    w: &WorldSnapshot,
    victory: bool,
) {
    let mut players: Vec<&PlayerView> = w.players.iter().collect();
    players.sort_by_key(|p| p.slot);
    let total: f32 = players.iter().map(|p| p.damage).sum::<f32>().max(1.0);
    let top = players.iter().map(|p| p.damage).fold(0.0, f32::max).max(1.0);
    let mvp = players.iter().max_by(|a, b| a.damage.total_cmp(&b.damage)).map(|p| p.slot).filter(|_| players.len() > 1);
    let n = players.len() as f32;
    let x0 = CX - (n * 330.0 + (n - 1.0) * 24.0) / 2.0;
    for (i, p) in players.iter().enumerate() {
        let x = x0 + i as f32 * 354.0;
        cv.spawn((
            abs(x, 530.0, 330.0, 314.0),
            Tween::new(TweenTarget::Translate(Vec2::new(0.0, 30.0), Vec2::ZERO), 0.3).delay(0.45 + i as f32 * 0.08),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            party_card(c, kit, db, link, p, mvp == Some(p.slot) && victory, p.damage / total, p.damage / top);
        });
    }
}

#[allow(clippy::too_many_arguments)]
fn party_card(
    c: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &ContentDb,
    link: &Link,
    p: &PlayerView,
    mvp: bool,
    share: f32,
    rel: f32,
) {
    let color = player_color(db, p.slot as usize);
    let name = link.roster.iter().find(|r| r.slot == p.slot).map_or(format!("P{}", p.slot + 1), |r| r.name.clone());
    let ch = db.characters.try_get(p.character);
    let style = if mvp { PanelStyle::horns(40) } else { PanelStyle::horns(40).bronze() };
    let card = gilt_panel(c, kit, abs(0.0, 0.0, 330.0, 314.0), style, |g| {
        g.spawn((abs(14.0, 14.0, 302.0, 4.0), BackgroundColor(color), Pickable::IGNORE));
        g.spawn((abs(22.0, 30.0, 68.0, 68.0), Pickable::IGNORE)).with_children(|m| {
            medallion(
                m,
                kit,
                MedallionSpec::new(68.0).portrait(&ik::portrait(ch.map_or("?", |c| c.key.as_str()))).band(color),
            );
        });
        g.spawn((centered_at(56.0, 98.0, 30.0, 18.0), Pickable::IGNORE)).with_children(|m| {
            pchip(m, kit, p.slot as usize, color);
        });
        g.spawn((
            Node { flex_direction: FlexDirection::Column, row_gap: px(2.0), ..abs(104.0, 42.0, 160.0, 50.0) },
            Pickable::IGNORE,
        ))
        .with_children(|t| {
            t.spawn(kit.text_flat(Ty::Strong, 22.0, name, tok::PARCH));
            t.spawn(kit.text_tracked(Ty::LabelS, 13.0, 0.2, ch.map_or("?".into(), |c| c.name.to_uppercase()), color));
        });
        if mvp {
            g.spawn((
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    ..abs(264.0, 26.0, 44.0, 60.0)
                },
                Pickable::IGNORE,
            ))
            .with_children(|m| {
                medallion(m, kit, MedallionSpec::new(34.0).enamel(hx(0x6A4A1A)).glyph("team/mvp", 0.8, Color::WHITE));
                m.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "MVP", tok::GOLD_LT));
            });
        }
        // Kills and the share of the damage.
        g.spawn((
            Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::FlexEnd,
                ..abs(24.0, 112.0, 282.0, 52.0)
            },
            Pickable::IGNORE,
        ))
        .with_children(|r| {
            r.spawn((Node { flex_direction: FlexDirection::Column, ..default() }, Pickable::IGNORE)).with_children(
                |k| {
                    k.spawn((
                        kit.text_flat(Ty::NumM, 26.0, "0", tok::NUMERAL),
                        CountUp { from: 0.0, to: p.kills as f64, t: 0.0, dur: 0.8, delay: 0.5, fmt: NumFmt::Thousands },
                    ));
                    k.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "KILLS", tok::PARCH_DIM));
                },
            );
            r.spawn((
                Node { flex_direction: FlexDirection::Column, align_items: AlignItems::FlexEnd, ..default() },
                Pickable::IGNORE,
            ))
            .with_children(|k| {
                k.spawn((
                    kit.text_flat(Ty::NumM, 26.0, "0%", tok::NUMERAL),
                    CountUp {
                        from: 0.0,
                        to: (share * 100.0).round() as f64,
                        t: 0.0,
                        dur: 0.8,
                        delay: 0.5,
                        fmt: NumFmt::Percent,
                    },
                ));
                k.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "OF THE DAMAGE", tok::PARCH_DIM));
            });
        });
        g.spawn((abs(24.0, 170.0, 282.0, 8.0), Pickable::IGNORE)).with_children(|b| {
            let e = bar(b, kit, BarSpec::new(282.0, 8.0, BarFill::Tint(color)));
            b.commands_mut().entity(e).insert(KitBar { value: (rel * 0.95).clamp(0.02, 1.0), ward: 0.0 });
        });
        // The weapon: the chassis hex and the four part slots with their cut gems.
        g.spawn((abs(24.0, 190.0, 200.0, 14.0), Pickable::IGNORE)).with_children(|t| {
            t.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "THE WEAPON", tok::GOLD_LT));
        });
        g.spawn((Node { column_gap: px(10.0), ..abs(24.0, 208.0, 282.0, 58.0) }, Pickable::IGNORE)).with_children(
            |r| {
                let chassis = db.chassis.try_get(p.weapon.chassis.0).map_or("?", |c| c.key.as_str());
                r.spawn((Node { width: px(44.0), height: px(44.0), ..default() }, Pickable::IGNORE)).with_children(
                    |s| {
                        slot(
                            s,
                            kit,
                            SlotSpec::new(SlotShape::HexFlat, 44.0)
                                .icon(&ik::chassis(chassis))
                                .icon_frac(0.7)
                                .shadow(false),
                        );
                    },
                );
                for s in Slot::ALL {
                    r.spawn((
                        Node {
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::Center,
                            width: px(44.0),
                            row_gap: px(2.0),
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|col| {
                        let spec = SlotSpec::new(SlotShape::for_part(s), 40.0)
                            .icon_frac(0.64)
                            .shadow(false)
                            .ghost(ik::slot_ghost(s));
                        match p.weapon.get(s) {
                            Some(it) => {
                                let key = ik::part(db.parts.try_get(it.part.0).map_or("?", |d| d.key.as_str()));
                                let e = slot(col, kit, spec.icon(&key));
                                let def = db.parts.try_get(it.part.0);
                                col.commands_mut().entity(e).insert((
                                    gf_engine::client::Hovered::default(),
                                    Pickable::default(),
                                    super::Tip::new(
                                        def.map_or("?".into(), |d| d.name.clone()),
                                        rarity_color(it.rarity),
                                    )
                                    .sub(format!("{} {}", it.rarity.name(), s.name()).to_uppercase())
                                    .body(def.map_or("", |d| d.desc.as_str())),
                                ));
                                rarity_gem(col, it.rarity, 4.0);
                            }
                            None => {
                                slot(col, kit, spec);
                            }
                        }
                    });
                }
            },
        );
        // Boons: the god sigils in pick order.
        g.spawn((
            Node { column_gap: px(8.0), align_items: AlignItems::Center, ..abs(24.0, 272.0, 282.0, 26.0) },
            Pickable::IGNORE,
        ))
        .with_children(|r| {
            r.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, "BOONS", tok::GOLD_LT));
            let max = 9;
            for b in p.boons.iter().take(max) {
                let god = db.boons.try_get(*b).and_then(|d| d.gods.first().cloned());
                match god {
                    Some(g) => {
                        let tint = god_colors(db, &g).map_or(tok::BONE, |(p, s)| super::god_text_color(&g, p, s));
                        icon(r, &ik::god(&g), 22.0, tint);
                    }
                    None => {
                        icon(r, "boon_kind/team", 22.0, tok::GOLD_LT);
                    }
                }
            }
            if p.boons.len() > max {
                r.spawn(kit.text_flat(Ty::Micro, 11.0, format!("+{}", p.boons.len() - max), tok::PARCH_DIM));
            }
            if p.boons.is_empty() {
                r.spawn(kit.text_flat(Ty::BodyS, 14.0, "none taken", tok::PARCH_MUTE));
            }
        });
    });
    if mvp {
        c.commands_mut().entity(card).insert(crate::uikit::glow(hx(0xFFB23A).with_alpha(0.35), 18.0, 1.0));
    }
}

fn buttons(cv: &mut ChildSpawnerCommands, kit: &UiKit, pad: bool) {
    cv.spawn((
        Node { justify_content: JustifyContent::Center, column_gap: px(40.0), ..abs(0.0, 884.0, CW, 52.0) },
        Tween::new(TweenTarget::Translate(Vec2::new(0.0, 20.0), Vec2::ZERO), 0.3).delay(1.0),
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        let again = button(r, kit, ButtonKind::Primary, "Forge again", 260.0, 52.0, |t| {
            if !pad {
                key_chip(t, kit, Key::Text("Enter"), 22.0);
            }
        });
        r.commands_mut().entity(again).insert((UiAction::Restart, Nav(PanelKind::End)));
        let leave = button(r, kit, ButtonKind::Secondary, "Leave", 260.0, 52.0, |t| {
            if !pad {
                key_chip(t, kit, Key::Text("Esc"), 22.0);
            }
        });
        r.commands_mut().entity(leave).insert((UiAction::Quit, Nav(PanelKind::End)));
    });
}
