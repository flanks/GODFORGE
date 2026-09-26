//! QA boards for the kit (UI_STYLE §11.11), never reachable in normal play.
//!
//! * `--ui-shot kit`: every widget and state on one board, the in-engine twin of
//!   `docs/art/ui_mockups/ui_visual_language_1920.png`. Cooldowns, drains, pours and pops loop so
//!   screenshots catch motion states.
//! * `--ui-shot icons`: every icon master in manifest order at 32 px, plus a size ladder.
//! * `--ui-shot cards`: the premium pieces (boon niche cards, banner, callout, boss bar, end
//!   card, a Forge strip) assembled from kit widgets.
//! * `--hud-off`: hides every root UI node (clean plates for mockups).
//!
//! Both boards are laid out on a 1760×990 logical canvas so they fit at 900p (UiScale 0.9 gives
//! 1778×1000 logical) and scale down to fit smaller windows.

use super::*;
use crate::ClientConfig;
use crate::theme::{god_colors, player_color, z};
use gf_core::damage::DamageType;
use gf_core::rarity::Rarity;
use std::f32::consts::PI;

/// The board canvas in logical px.
const BOARD: Vec2 = Vec2::new(1760.0, 990.0);

pub fn build(app: &mut App) {
    let cfg = app.world().resource::<ClientConfig>().clone();
    match cfg.ui_shot.as_deref() {
        Some("kit") => {
            app.add_systems(Startup, spawn_kit_board).add_systems(Update, (animate_board, fit_board));
        }
        Some("icons") => {
            app.add_systems(Startup, spawn_icon_board).add_systems(Update, fit_board);
        }
        Some("cards") => {
            app.add_systems(Startup, spawn_cards_board).add_systems(Update, fit_board);
        }
        _ => {}
    }
    if cfg.hud_off {
        app.add_systems(PostUpdate, hide_ui_roots.before(gf_engine::bevy::ui::UiSystems::Prepare));
    }
}

/// `--hud-off`: every root UI node stays hidden.
fn hide_ui_roots(mut roots: Query<&mut Visibility, (With<Node>, Without<ChildOf>)>) {
    for mut v in &mut roots {
        if *v != Visibility::Hidden {
            *v = Visibility::Hidden;
        }
    }
}

/// The board node: fixed 1760×990, centred, scaled down when the window is smaller.
#[derive(Component)]
struct Board;

fn fit_board(
    windows: Query<&Window, With<gf_engine::client::PrimaryWindow>>,
    scale: Res<UiScale>,
    mut boards: Query<&mut UiTransform, With<Board>>,
) {
    let Ok(w) = windows.single() else { return };
    let logical = Vec2::new(w.width(), w.height()) / scale.0.max(0.01);
    let k = (logical.x / (BOARD.x + 40.0)).min(logical.y / (BOARD.y + 30.0)).min(1.0);
    for mut tf in &mut boards {
        if (tf.scale.x - k).abs() > 1e-3 {
            tf.scale = Vec2::splat(k);
        }
    }
}

/// The backdrop and the centred board canvas.
fn board_root(commands: &mut Commands, content: impl FnOnce(&mut ChildSpawnerCommands)) {
    commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                width: percent(100.0),
                height: percent(100.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundGradient(vec![
                RadialGradient::new(
                    UiPosition::CENTER.at_percent(0.0, -20.0),
                    RadialGradientShape::FarthestCorner,
                    vec![ColorStop::auto(hx(0x1E1510)), ColorStop::auto(hx(0x0C0907))],
                )
                .into(),
            ]),
            GlobalZIndex(z::QA),
        ))
        .with_children(|r| {
            r.spawn((Node { width: px(BOARD.x), height: px(BOARD.y), flex_shrink: 0.0, ..default() }, Board))
                .with_children(content);
        });
}

/// A section heading at (x, y): `Label` caps in `gold_lt`.
fn heading(p: &mut ChildSpawnerCommands, kit: &UiKit, x: f32, y: f32, title: &str) {
    p.spawn((Node { position_type: PositionType::Absolute, left: px(x), top: px(y), ..default() }, Pickable::IGNORE))
        .with_children(|c| {
            c.spawn(kit.text_flat(Ty::Label, 15.0, title, tok::GOLD_LT));
        });
}

/// An absolutely placed container at (x, y) whose children flow.
fn at(
    p: &mut ChildSpawnerCommands,
    x: f32,
    y: f32,
    node: Node,
    content: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    p.spawn((Node { position_type: PositionType::Absolute, left: px(x), top: px(y), ..node }, Pickable::IGNORE))
        .with_children(content)
        .id()
}

/// A small caption in `BodyS` 14 dim.
fn caption(c: &mut ChildSpawnerCommands, kit: &UiKit, s: &str) {
    c.spawn(kit.text_flat(Ty::BodyS, 14.0, s, tok::PARCH_DIM));
}

/// Looping demo drivers on the kit board.
#[derive(Component, Clone, Copy)]
enum Demo {
    /// A cooldown of this many seconds, repeating with a 1.2 s ready hold.
    Cooldown(f32),
    /// A bar losing chunks and healing back.
    Drain,
    /// A ward bar.
    Ward,
    /// The ult ring filling, then ready.
    Ult,
    /// The Overdrive hex pouring.
    Overdrive,
    /// Dash pips refilling.
    Dash,
    /// Armour plates breaking and regrowing.
    Armor,
    /// A heat ring counting down.
    Heat,
}

#[allow(clippy::too_many_arguments)]
fn spawn_kit_board(
    mut commands: Commands,
    kit: Res<UiKit>,
    cfg: Res<ClientConfig>,
    mut materials: ResMut<Assets<MoltenMaterial>>,
    mut decode: ResMut<UiDecode>,
) {
    let kit = &*kit;
    let db = cfg.content.clone();
    let players: Vec<Color> = (0..4).map(|i| player_color(&db, i)).collect();
    let pyra = god_colors(&db, "pyra").unwrap_or((hx(0xE0312B), hx(0xFFC23D)));
    let zephyros = god_colors(&db, "zephyros").unwrap_or((hx(0x7FE3FF), hx(0xFFFFFF)));
    board_root(&mut commands, |b| {
        // ── header ──
        at(b, 0.0, 0.0, row(26.0), |c| {
            gradient_text(
                c,
                kit,
                Ty::Title,
                32.0,
                "GODFORGE UI KIT",
                &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                true,
            );
            c.spawn(kit.text_flat(
                Ty::Flavour,
                17.0,
                "in-engine board · 1920×1080 logical px · every shape original to GODFORGE",
                tok::PARCH_DIM,
            ));
        });
        at(b, 0.0, 48.0, Node::default(), |c| {
            ember_knot(c, kit, BOARD.x, Gem::Ivory, 0.9);
        });

        // ── tokens ──
        heading(b, kit, 0.0, 72.0, "TOKENS");
        let tokens: [(&str, Color, &str); 24] = [
            ("lac0", tok::LAC0, "#0B0807"),
            ("lac1", tok::LAC1, "#130D0A"),
            ("lac2", tok::LAC2, "#2A1E16"),
            ("lac3", tok::LAC3, "#4A3624"),
            ("gold_hi", tok::GOLD_HI, "#FFECB0"),
            ("gold_lt", tok::GOLD_LT, "#F2C667"),
            ("gold_md", tok::GOLD_MD, "#C9933E"),
            ("gold_dk", tok::GOLD_DK, "#7A5424"),
            ("gold_sh", tok::GOLD_SH, "#3B2610"),
            ("parch", tok::PARCH, "#F4E6C8"),
            ("parch_dim", tok::PARCH_DIM, "#B9A98C"),
            ("parch_mute", tok::PARCH_MUTE, "#7D705E"),
            ("ink_text", tok::INK_TEXT, "#1A120B"),
            ("ichor", tok::ICHOR, "#FFE9B0"),
            ("ichor_glow", tok::ICHOR_GLOW, "#FFC873"),
            ("loss", tok::LOSS, "#A58C86"),
            ("hp_lt", tok::HP_LT, "#E8574C"),
            ("hp", tok::HP, "#C8323A"),
            ("hp_dk", tok::HP_DK, "#7E1420"),
            ("hp_ghost", tok::HP_GHOST, "#F0B37A"),
            ("ward", tok::WARD, "#DCE6EA"),
            ("steel", tok::STEEL[1], "#9AA4AE"),
            ("molten", tok::MOLTEN[2], "#FFC95A"),
            ("danger", tok::DANGER, "#FF3B30"),
        ];
        for (i, (name, color, hexs)) in tokens.iter().enumerate() {
            let (col, rowi) = (i % 12, i / 12);
            at(b, col as f32 * 71.0, 98.0 + rowi as f32 * 74.0, column(3.0), |c| {
                c.spawn((
                    Node {
                        width: px(40.0),
                        height: px(26.0),
                        border: UiRect::all(px(1.0)),
                        border_radius: BorderRadius::all(px(4.0)),
                        ..default()
                    },
                    BackgroundColor(*color),
                    BorderColor::all(tok::GOLD_SH),
                ));
                c.spawn(kit.text_flat(Ty::BodyS, 14.0, *name, tok::PARCH));
                c.spawn(kit.text_flat(Ty::Debug, 12.0, *hexs, tok::PARCH_MUTE));
            });
        }

        // ── reserved hues ──
        heading(b, kit, 900.0, 72.0, "RESERVED HUES · ONLY IN THEIR DOMAIN");
        let rarities = [Rarity::Common, Rarity::Rare, Rarity::Epic, Rarity::Godforged];
        let elements = [
            DamageType::Kinetic,
            DamageType::Flame,
            DamageType::Storm,
            DamageType::Void,
            DamageType::Plague,
            DamageType::Radiant,
        ];
        let rows: [(&str, Vec<(String, Color)>); 3] = [
            ("RARITY", rarities.iter().map(|r| (rarity_key(*r).to_string(), rarity_color(*r))).collect()),
            (
                "ELEMENT",
                elements.iter().map(|e| (format!("{e:?}").to_lowercase(), crate::palette::element_color(*e))).collect(),
            ),
            ("PLAYER", players.iter().enumerate().map(|(i, c)| (format!("P{}", i + 1), *c)).collect()),
        ];
        for (ri, (name, hues)) in rows.iter().enumerate() {
            let y = 100.0 + ri as f32 * 44.0;
            at(b, 900.0, y + 4.0, Node::default(), |c| {
                c.spawn(kit.text_flat(Ty::Micro, 12.0, *name, tok::PARCH_DIM));
            });
            for (hi, (label_s, color)) in hues.iter().enumerate() {
                at(b, 990.0 + hi as f32 * 128.0, y, row(8.0), |c| {
                    c.spawn((
                        Node { width: px(22.0), height: px(22.0), border_radius: BorderRadius::MAX, ..default() },
                        BackgroundColor(*color),
                        drop_shadow(0.6, 1.0, 3.0),
                    ));
                    c.spawn(kit.text_flat(Ty::BodyS, 15.0, label_s.clone(), tok::PARCH));
                });
            }
        }

        // ── type ──
        heading(b, kit, 0.0, 252.0, "TYPE");
        at(b, 0.0, 276.0, column(4.0), |c| {
            gradient_text(
                c,
                kit,
                Ty::DisplayXl,
                52.0,
                "VICTORY",
                &[hx(0xFFFBEA), hx(0xF7CE6A), hx(0xD49A40), hx(0xA86A22)],
                true,
            );
            gradient_text(
                c,
                kit,
                Ty::Title,
                36.0,
                "THE FORGE",
                &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                true,
            );
            c.spawn(kit.text_flat(Ty::CardName, 26.0, "LEAPING ARC", rarity_color(Rarity::Rare)));
            c.spawn(kit.text_flat(Ty::Label, 15.0, "THE WEAPON", tok::GOLD_LT));
            c.spawn(kit.text_flat(Ty::Micro, 12.0, "EPIC RELIC · REPLACES NYCTIAN EYE", tok::PARCH_DIM));
            c.spawn(row(22.0)).with_children(|r| {
                r.spawn(kit.text_flat(Ty::NumXl, 38.0, "1,284", tok::NUMERAL));
                r.spawn(kit.text_flat(Ty::NumM, 24.0, "07:32", tok::NUMERAL));
                r.spawn(kit.text_flat(Ty::Num, 19.0, "307 / 380", tok::NUMERAL));
            });
            rich(
                c,
                kit,
                18.0,
                &[
                    (Ty::Body, "Hits have a ", tok::PARCH),
                    (Ty::Strong, "25%", tok::ICHOR),
                    (Ty::Body, " chance to ", tok::PARCH),
                    (Ty::Strong, "Shock", crate::palette::element_color(DamageType::Storm)),
                    (Ty::Body, ".", tok::PARCH),
                ],
                None,
                Justify::Left,
            );
            c.spawn(kit.text_flat(Ty::Flavour, 17.0, "The Chainyard anvil burns hot", tok::PARCH_DIM));
        });
        at(b, 360.0, 290.0, column(19.0), |c| {
            for s in [
                "display_xl · Cinzel 900 · 96 (shown at 52)",
                "title · Cinzel 800 · 32–36 · banded gold",
                "card name · Cinzel 800 · 26 · rarity colour",
                "label · Cinzel 800 · 15 · +18 %",
                "micro · Cinzel 800 · 12 · +16 %",
                "numerals · Cinzel 800 · Alegreya Bold tnum",
                "body · Alegreya Sans Medium 18",
                "flavour · Alegreya Sans Italic 17",
            ] {
                caption(c, kit, s);
            }
        });

        // ── frames & ornament ──
        heading(b, kit, 690.0, 252.0, "FRAMES & ORNAMENT");
        at(b, 700.0, 300.0, Node::default(), |c| {
            gilt_panel(
                c,
                kit,
                Node {
                    width: px(290.0),
                    height: px(176.0),
                    padding: UiRect::all(px(26.0)),
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    row_gap: px(8.0),
                    ..default()
                },
                PanelStyle::horns(44).crest(50),
                |g| {
                    g.spawn(kit.text_flat(Ty::Label, 15.0, "ORNATE PANEL", tok::GOLD_LT));
                    ember_knot(g, kit, 180.0, Gem::Amber, 1.0);
                    g.spawn(kit.text_flat(Ty::BodyS, 14.0, "gilt 9-slice · forge-horns · sun-crest", tok::PARCH_DIM));
                },
            );
        });
        at(b, 1020.0, 296.0, column(10.0), |c| {
            quiet_plate(
                c,
                Node {
                    width: px(230.0),
                    height: px(64.0),
                    padding: UiRect::axes(px(14.0), px(10.0)),
                    flex_direction: FlexDirection::Column,
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                0.9,
                |q| {
                    q.spawn(kit.text_flat(Ty::LabelS, 14.0, "QUIET PLATE", tok::GOLD_LT));
                    q.spawn(kit.text_flat(Ty::BodyS, 14.0, "combat HUD · 1.1 px gold rim", tok::PARCH_DIM));
                },
            );
            c.spawn(Node { height: px(6.0), ..default() });
            ember_knot(c, kit, 230.0, Gem::Ivory, 1.0);
            caption(c, kit, "ember-knot divider");
            tooltip(
                c,
                kit,
                Node {
                    width: px(230.0),
                    height: px(62.0),
                    padding: UiRect::axes(px(14.0), px(10.0)),
                    flex_direction: FlexDirection::Column,
                    ..default()
                },
                |t| {
                    t.spawn(kit.text_flat(Ty::LabelS, 13.0, "COLOSSUS CANNON", tok::GOLD_LT));
                    t.spawn(kit.text_flat(Ty::BodyS, 14.0, "Stormcore · Ricochet · Nyctian Eye", tok::PARCH_DIM));
                },
            );
        });
        at(b, 700.0, 500.0, row(6.0), |c| {
            keycap(c, kit, "Q", 22.0);
            keycap(c, kit, "Tab", 22.0);
            keycap(c, kit, "Esc", 22.0);
            keycap(c, kit, "F", 22.0);
            keycap(c, kit, "1", 22.0);
            key_chip(c, kit, Key::Icon("input/mouse_lmb"), 22.0);
            key_chip(c, kit, Key::Icon("input/mouse_rmb"), 22.0);
            c.spawn(Node { width: px(8.0), ..default() });
            for k in ["input/pad_south", "input/pad_east", "input/pad_west", "input/pad_north", "input/pad_view"] {
                key_chip(c, kit, Key::Icon(k), 22.0);
            }
        });
        at(b, 700.0, 530.0, Node::default(), |c| {
            caption(c, kit, "keycaps · mouse · pad studs by position (no colours, no letters)")
        });

        // ── slot shapes ──
        heading(b, kit, 1280.0, 252.0, "SLOT SHAPE = CATEGORY");
        let shapes: [(SlotShape, &str, &str); 7] = [
            (SlotShape::Round, "parts/stormcore", "CORE"),
            (SlotShape::Octagon, "parts/mech_ricochet", "MECH"),
            (SlotShape::Arch, "parts/relic_nyctian_eye", "RELIC"),
            (SlotShape::Lozenge, "parts/sigil_anvilheart", "SIGIL"),
            (SlotShape::Chamfer, "kits/valdris_q", "ABILITY"),
            (SlotShape::HexPointy, "team/overdrive", "OVERDRIVE"),
            (SlotShape::HexFlat, "chassis/colossus_cannon", "CHASSIS"),
        ];
        for (i, (shape, icon_key, name)) in shapes.iter().enumerate() {
            at(
                b,
                1266.0 + i as f32 * 70.0,
                282.0,
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    row_gap: px(6.0),
                    width: px(70.0),
                    ..default()
                },
                |c| {
                    slot(c, kit, SlotSpec::new(*shape, 56.0).icon(icon_key).icon_frac(0.66));
                    c.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.06, *name, tok::PARCH_DIM));
                },
            );
        }
        heading(b, kit, 1280.0, 376.0, "RARITY GEM CUT");
        at(b, 1280.0, 402.0, row(22.0), |c| {
            for r in rarities {
                c.spawn(row(6.0)).with_children(|g| {
                    rarity_gem(g, r, 7.0);
                    g.spawn(kit.text_flat(Ty::Micro, 12.0, rarity_key(r).to_uppercase(), rarity_color(r)));
                });
            }
        });
        at(b, 1280.0, 440.0, row(8.0), |c| {
            pill(c, kit, PillKind::Gold, "Duo", Some("boon_kind/duo"));
            pill(c, kit, PillKind::Gold, "Legendary", Some("boon_kind/legendary"));
            pill(c, kit, PillKind::Gold, "Team", Some("boon_kind/team"));
            pill(c, kit, PillKind::Outline, "All", None);
            pill(c, kit, PillKind::Outline, "Core", None);
        });
        at(b, 1280.0, 472.0, row(8.0), |c| {
            ribbon(c, kit, Rarity::Common);
            ribbon(c, kit, Rarity::Rare);
            ribbon(c, kit, Rarity::Epic);
            ribbon(c, kit, Rarity::Godforged);
        });
        at(b, 1280.0, 506.0, row(8.0), |c| {
            for (i, color) in players.iter().enumerate().skip(1) {
                pchip(c, kit, i, *color);
            }
            chip(c, kit, "Reroll", Some("ui/reroll"), 112.0, |t| {
                t.spawn(kit.text_flat(Ty::Num, 14.0, "6", tok::PARCH));
                icon(t, "currency/godshard", 14.0, Color::WHITE);
            });
        });

        // ── states ──
        heading(b, kit, 0.0, 574.0, "STATES");
        at(b, 6.0, 606.0, row(26.0), |c| {
            for (name, demo, state, key) in [
                ("ready", None, SlotState::READY, "Q"),
                ("cooling", Some(Demo::Cooldown(6.0)), SlotState::cooling(0.6, 3.4), "E"),
                ("disabled", None, SlotState::DISABLED, "R"),
            ] {
                c.spawn(Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    row_gap: px(16.0),
                    ..default()
                })
                .with_children(|s| {
                    let e = slot(s, kit, SlotSpec::ability("kits/valdris_e", 60.0).key(key));
                    s.commands_mut().entity(e).insert(state);
                    if let Some(d) = demo {
                        s.commands_mut().entity(e).insert(d);
                    }
                    caption(s, kit, name);
                });
            }
        });
        at(b, 280.0, 600.0, column(10.0), |c| {
            button(c, kit, ButtonKind::Primary, "Equip", 214.0, 46.0, |t| {
                delta_chip_in(t, kit, 24.0, 16.0, Some(tok::INK_TEXT));
            });
            button(c, kit, ButtonKind::Secondary, "Salvage", 214.0, 40.0, |t| {
                t.spawn(row(4.0)).with_children(|r| {
                    icon(r, "currency/godshard", 16.0, Color::WHITE);
                    r.spawn(kit.text_flat(Ty::Num, 15.0, "+12", tok::PARCH));
                });
            });
            let fuse = button(c, kit, ButtonKind::Secondary, "Fuse", 214.0, 40.0, |t| {
                t.spawn(kit.text_flat(Ty::Flavour, 14.0, "no twin", tok::PARCH_MUTE));
            });
            c.commands_mut().entity(fuse).insert(InteractionDisabled);
        });
        at(b, 516.0, 604.0, column(10.0), |c| {
            delta_chip(c, kit, 24.0, 18.0);
            delta_chip(c, kit, -6.0, 18.0);
            delta_chip(c, kit, 0.0, 18.0);
        });
        at(b, 0.0, 754.0, Node::default(), |c| {
            caption(c, kit, "cooldown: conic sweep + edge + numeral · ready: halo, sheen, flash, pop, ring burst")
        });
        at(b, 610.0, 600.0, column(8.0), |c| {
            let card = gilt_card(
                c,
                kit,
                Rarity::Epic,
                Node {
                    width: px(194.0),
                    height: px(82.0),
                    padding: UiRect::all(px(12.0)),
                    column_gap: px(12.0),
                    align_items: AlignItems::Center,
                    ..default()
                },
                |g| {
                    slot(
                        g,
                        kit,
                        SlotSpec::new(SlotShape::Arch, 52.0)
                            .icon("parts/relic_doomstack")
                            .icon_frac(0.68)
                            .shadow(false),
                    );
                    g.spawn(column(2.0)).with_children(|t| {
                        t.spawn(kit.text_flat(Ty::Strong, 17.0, "Doomstack", tok::PARCH));
                        t.spawn(kit.text_flat(Ty::Micro, 12.0, "EPIC", rarity_color(Rarity::Epic)));
                    });
                },
            );
            c.commands_mut().queue(move |w: &mut World| {
                if let Some(mut k) = w.get_mut::<KitCard>(card) {
                    k.selected = true;
                }
            });
            caption(c, kit, "selected: metal ring + glow");
        });

        // ── bars & meters ──
        heading(b, kit, 850.0, 574.0, "BARS & METERS");
        let bars_x = 850.0;
        at(b, bars_x, 604.0, row(12.0), |c| {
            let e = bar(c, kit, BarSpec::new(300.0, 22.0, BarFill::Hp).finial());
            c.commands_mut().entity(e).insert(Demo::Drain);
            c.spawn(Node { width: px(8.0), ..default() });
            caption(c, kit, "HP + ghost");
        });
        at(b, bars_x, 640.0, row(12.0), |c| {
            let e = bar(c, kit, BarSpec::new(300.0, 22.0, BarFill::Hp).ward());
            c.commands_mut().entity(e).insert(Demo::Ward);
            caption(c, kit, "ward hatch");
        });
        at(b, bars_x, 678.0, row(18.0), |c| {
            let e = plates(c, kit, 230.0, 4);
            c.commands_mut().entity(e).insert(Demo::Armor);
            let d = dash_pips(c, kit, 3);
            c.commands_mut().entity(d).insert(Demo::Dash);
            caption(c, kit, "armour · dash");
        });
        at(b, bars_x, 712.0, row(12.0), |c| {
            c.spawn(Node::default()).with_children(|w| {
                let e = bar(w, kit, BarSpec::new(300.0, 18.0, BarFill::Boss));
                w.commands_mut().entity(e).insert(KitBar { value: 0.62, ward: 0.0 });
                notches(w, kit, 300.0, &[0.66, 0.33]);
            });
            caption(c, kit, "boss · phase notches");
        });
        at(b, bars_x, 744.0, row(12.0), |c| {
            let e = bar(c, kit, BarSpec::new(262.0, 6.0, BarFill::Molten));
            c.commands_mut().entity(e).insert(KitBar { value: 0.92, ward: 0.0 });
            let p2 = bar(c, kit, BarSpec::new(120.0, 8.0, BarFill::Tint(players[1])).no_rim());
            c.commands_mut().entity(p2).insert(KitBar { value: 0.7, ward: 0.0 });
            caption(c, kit, "event · share");
        });

        // ── medallions & markers ──
        heading(b, kit, 1280.0, 574.0, "MEDALLIONS & MARKERS");
        at(b, 1282.0, 604.0, Node::default(), |c| {
            let h = hearth_medallion(c, kit, "portraits/valdris", players[0], "R");
            c.commands_mut().entity(h).insert(Demo::Ult);
        });
        at(b, 1426.0, 606.0, column(6.0), |c| {
            c.spawn(row(10.0)).with_children(|r| {
                r.spawn(Node { flex_direction: FlexDirection::Column, align_items: AlignItems::Center, ..default() })
                    .with_children(|m| {
                        medallion(m, kit, MedallionSpec::new(46.0).portrait("portraits/selene").band(players[1]));
                        let chip_e = pchip(m, kit, 1, players[1]);
                        m.commands_mut().entity(chip_e).insert(Node {
                            width: px(30.0),
                            height: px(18.0),
                            margin: UiRect::top(px(-8.0)),
                            justify_content: JustifyContent::Center,
                            align_items: AlignItems::Center,
                            ..default()
                        });
                    });
                medallion(r, kit, MedallionSpec::new(60.0).enamel(pyra.0).glyph("gods/pyra", 0.62, Color::WHITE));
                let od = overdrive_hex(r, kit, &mut materials, &mut decode, 62.0, "V");
                r.commands_mut().entity(od).insert(Demo::Overdrive);
            });
        });
        at(b, 1426.0, 690.0, row(14.0), |c| {
            let heat = ring_meter(
                c,
                Node {
                    width: px(46.0),
                    height: px(46.0),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    ..default()
                },
                5.0,
                RingStyle::Molten,
                0.7,
            );
            c.commands_mut().entity(heat).insert(Demo::Heat).with_children(|h| {
                h.spawn(kit.text_flat(Ty::NumM, 18.0, "19", tok::NUMERAL));
            });
            let e = pin(c, kit, PinRing::Gilt, "poi/anvil", tok::BONE);
            let pin_rot = |c: &mut ChildSpawnerCommands, e: Entity, a: f32| {
                c.commands_mut().queue(move |w: &mut World| {
                    if let Some(parts) = w.get::<PinParts>(e).copied()
                        && let Some(mut tf) = w.get_mut::<UiTransform>(parts.frame)
                    {
                        tf.rotation = Rot2::radians(a);
                    }
                });
            };
            pin_rot(c, e, -1.2);
            let s = pin(c, kit, PinRing::Gilt, "gods/zephyros", zephyros.0);
            pin_rot(c, s, 2.4);
            let d = pin(c, kit, PinRing::Tint(tok::DANGER), "states/downed", Color::WHITE);
            pin_rot(c, d, 0.9);
            c.commands_mut()
                .entity(d)
                .insert((glow(tok::DANGER.with_alpha(0.6), 10.0, 1.0), Pulse::shadow(1.25, 0.25, 0.8)));
        });
        at(b, 1282.0, 770.0, row(18.0), |c| {
            c.spawn(damage_text(kit, 31, crate::palette::element_color(DamageType::Kinetic), false));
            c.spawn(damage_text(kit, 44, crate::palette::element_color(DamageType::Storm), false));
            c.spawn(row(0.0)).with_children(|r| {
                r.spawn(damage_text(kit, 412, tok::ICHOR, true));
                icon(r, "ui/spark4", 16.0, hx(0xFFE27A));
            });
            prompt_plate(c, kit, Key::Text("F"), "Kindle the anvil", "Anvil · 1 Seal");
        });

        // ── icons strip ──
        heading(b, kit, 0.0, 800.0, "ICONS · SILHOUETTE FIRST · IVORY TO CATEGORY TINT · INK OUTLINE");
        let strip = [
            "elements/kinetic",
            "elements/flame",
            "elements/storm",
            "elements/void",
            "elements/plague",
            "elements/radiant",
            "status/burn",
            "status/shock",
            "status/curse",
            "status/root",
            "status/bleed",
            "status/mark",
            "poi/anvil",
            "poi/warlord",
            "poi/lair",
            "poi/shrine",
            "poi/reliquary",
            "poi/vein",
            "poi/spring",
            "poi/watchfire",
            "poi/gate",
            "currency/godshard",
            "currency/ember",
            "currency/seal",
            "gods/pyra",
            "gods/zephyros",
            "gods/nyctia",
            "gods/aeon",
            "gods/gaiaa",
            "gods/morwenn",
            "gods/seraphel",
            "gods/umbra_rex",
            "portraits/valdris",
            "portraits/selene",
            "portraits/kael",
            "kits/valdris_q",
            "kits/valdris_e",
            "kits/valdris_r",
            "chassis/colossus_cannon",
            "aim/auto",
            "aim/assisted",
            "aim/manual",
            "ui/reroll",
            "ui/fuse",
            "ui/salvage",
            "ui/lock",
            "states/downed",
            "run/hourglass",
        ];
        for (i, key) in strip.iter().enumerate() {
            let (col, rowi) = (i % 24, i / 24);
            at(
                b,
                col as f32 * 73.3,
                828.0 + rowi as f32 * 82.0,
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    width: px(70.0),
                    row_gap: px(4.0),
                    ..default()
                },
                |c| {
                    icon(c, key, 44.0, Color::WHITE);
                    let name = key.split('/').nth(1).unwrap_or(key);
                    c.spawn(kit.text_flat(Ty::BodyS, 14.0, name, tok::PARCH_DIM));
                },
            );
        }
    });
}

/// Loop the demo widgets so screenshots catch every motion state.
#[allow(clippy::type_complexity)]
fn animate_board(
    time: Res<Time>,
    mut q: Query<(
        &Demo,
        Option<&mut SlotState>,
        Option<&mut KitBar>,
        Option<&HearthParts>,
        Option<&mut MoltenFill>,
        Option<&mut KitPips>,
        Option<&mut KitPlates>,
        Option<&mut KitRing>,
    )>,
    mut rings: Query<&mut KitRing, Without<Demo>>,
    mut pulses: Query<&mut Pulse>,
) {
    let t = time.elapsed_secs();
    for (demo, slot, bar, hearth, molten, pips, plates, ring) in &mut q {
        match *demo {
            Demo::Cooldown(cd) => {
                if let Some(mut s) = slot {
                    let period = cd + 1.2;
                    let k = (t + 2.6) % period;
                    *s = if k < cd { SlotState::cooling(1.0 - k / cd, cd - k) } else { SlotState::READY };
                }
            }
            Demo::Drain => {
                if let Some(mut b) = bar {
                    // 0.81 → hits at 2 s steps → heal back.
                    let k = t % 8.0;
                    let v = if k < 2.0 {
                        0.81
                    } else if k < 4.0 {
                        0.62
                    } else if k < 6.0 {
                        0.44
                    } else {
                        0.44 + (k - 6.0) / 2.0 * 0.37
                    };
                    b.value = v;
                }
            }
            Demo::Ward => {
                if let Some(mut b) = bar {
                    b.value = 0.58;
                    b.ward = 0.14 + 0.06 * (t * 0.8).sin();
                }
            }
            Demo::Ult => {
                if let Some(h) = hearth {
                    let k = t % 9.0;
                    let (v, ready) = if k < 6.0 { (k / 6.0, false) } else { (1.0, true) };
                    if let Ok(mut r) = rings.get_mut(h.ult) {
                        r.value = v.max(0.08);
                        r.ready = ready;
                    }
                    if let Ok(mut p) = pulses.get_mut(h.glow) {
                        p.on = ready;
                    }
                }
            }
            Demo::Overdrive => {
                if let Some(mut m) = molten {
                    let k = t % 10.0;
                    m.value = (0.35 + k / 7.0).min(1.0);
                    m.ready = m.value >= 1.0;
                }
            }
            Demo::Dash => {
                if let Some(mut p) = pips {
                    let k = t % 3.0;
                    p.full = 1 + (k / 1.5) as u32;
                    p.refill = (k % 1.5) / 1.5;
                }
            }
            Demo::Armor => {
                if let Some(mut p) = plates {
                    let k = t % 6.0;
                    p.value = if k < 3.0 { 2.6 } else { 2.6 + (k - 3.0) / 3.0 * 1.4 };
                }
            }
            Demo::Heat => {
                if let Some(mut r) = ring {
                    r.value = 1.0 - (t % 12.0) / 12.0;
                }
            }
        }
    }
}

/// The icon board: every master at 32 px on slot recesses, grouped, then a size ladder.
fn spawn_icon_board(mut commands: Commands, kit: Res<UiKit>) {
    let kit = &*kit;
    board_root(&mut commands, |b| {
        at(b, 0.0, 0.0, row(26.0), |c| {
            gradient_text(
                c,
                kit,
                Ty::Title,
                30.0,
                "ICON MASTERS",
                &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                true,
            );
            c.spawn(kit.text_flat(
                Ty::Flavour,
                17.0,
                format!(
                    "{} icons · 128 / 64 / 32 levels · premultiplied box filter · shown at 38 px",
                    kit.icon_keys.len()
                ),
                tok::PARCH_DIM,
            ));
        });
        at(b, 0.0, 44.0, Node::default(), |c| {
            ember_knot(c, kit, BOARD.x, Gem::Ivory, 0.9);
        });
        at(
            b,
            0.0,
            70.0,
            Node {
                width: px(BOARD.x),
                flex_wrap: FlexWrap::Wrap,
                column_gap: px(4.0),
                row_gap: px(4.0),
                align_items: AlignItems::Center,
                ..default()
            },
            |c| {
                let mut group = "";
                for key in &kit.icon_keys {
                    let g = key.split('/').next().unwrap_or("");
                    if g != group {
                        group = g;
                        c.spawn((
                            Node {
                                height: px(42.0),
                                padding: UiRect::horizontal(px(6.0)),
                                align_items: AlignItems::Center,
                                border_radius: BorderRadius::all(px(4.0)),
                                ..default()
                            },
                            BackgroundColor(tok::GOLD_SH.with_alpha(0.55)),
                        ))
                        .with_children(|h| {
                            h.spawn(kit.text_flat(Ty::Micro, 11.0, g.to_uppercase(), tok::GOLD_LT));
                        });
                    }
                    c.spawn((
                        Node {
                            width: px(42.0),
                            height: px(42.0),
                            justify_content: JustifyContent::Center,
                            align_items: AlignItems::Center,
                            border_radius: BorderRadius::all(px(5.0)),
                            ..default()
                        },
                        v_gradient(hx(0x2A1E16), hx(0x100B08)),
                    ))
                    .with_children(|cell| {
                        icon(cell, key, 38.0, Color::WHITE);
                    });
                }
            },
        );
        // Size ladder: the same icons at 64, 48, 32 and 24 (checks the level pick).
        heading(b, kit, 0.0, 858.0, "SIZE LADDER · 64 · 48 · 32 · 24");
        let ladder = [
            "portraits/valdris",
            "kits/selene_q",
            "chassis/colossus_cannon",
            "parts/stormcore",
            "gods/pyra",
            "boons/zephyros_leaping_arc",
            "poi/anvil",
            "status/shock",
        ];
        at(b, 0.0, 886.0, row(34.0), |c| {
            for key in ladder {
                c.spawn(row(6.0)).with_children(|r| {
                    for s in [64.0, 48.0, 32.0, 24.0] {
                        icon(r, key, s, Color::WHITE);
                    }
                });
            }
        });
    });
}

/// One boon card of the specimen spread.
struct BoonSample {
    rarity: Rarity,
    gods: Vec<(&'static str, Color)>,
    icon: &'static str,
    kind: Option<(&'static str, &'static str)>,
    name: &'static str,
    desc: Vec<(Ty, &'static str, Color)>,
    new: bool,
    level: u32,
}

/// The premium pieces board (`--ui-shot cards`): the boon spread on niche cards, the region
/// banner, a callout, the boss bar, an end-screen party card and a Forge strip, all built from
/// kit widgets. Specimens for lanes H and P, not their final layouts.
fn spawn_cards_board(mut commands: Commands, kit: Res<UiKit>, cfg: Res<ClientConfig>) {
    let kit = &*kit;
    let db = cfg.content.clone();
    let players: Vec<Color> = (0..4).map(|i| player_color(&db, i)).collect();
    let god = |k: &str| god_colors(&db, k).map_or(tok::GOLD_LT, |c| c.0);
    let zeph = god("zephyros");
    let nyctia = god("nyctia");
    let seraphel = god("seraphel");
    let storm = crate::palette::element_color(DamageType::Storm);
    let body = tok::PARCH;
    let samples = vec![
        BoonSample {
            rarity: Rarity::Common,
            gods: vec![("zephyros", zeph)],
            icon: "boons/zephyros_stormbrand",
            kind: None,
            name: "STORMBRAND",
            desc: vec![
                (Ty::Strong, "+15%", tok::ICHOR),
                (Ty::Body, " damage; hits have a ", body),
                (Ty::Strong, "25%", tok::ICHOR),
                (Ty::Body, " chance to ", body),
                (Ty::Strong, "Shock", storm),
                (Ty::Body, ".", body),
            ],
            new: true,
            level: 1,
        },
        BoonSample {
            rarity: Rarity::Rare,
            gods: vec![("zephyros", zeph)],
            icon: "boons/zephyros_leaping_arc",
            kind: None,
            name: "LEAPING ARC",
            desc: vec![
                (Ty::Body, "Hits arc to ", body),
                (Ty::Strong, "2", tok::ICHOR),
                (Ty::Body, " more enemies; each jump deals half the damage of the last.", body),
            ],
            new: false,
            level: 2,
        },
        BoonSample {
            rarity: Rarity::Epic,
            gods: vec![("zephyros", zeph), ("nyctia", nyctia)],
            icon: "boons/silent_thunder",
            kind: Some(("Duo", "boon_kind/duo")),
            name: "SILENT THUNDER",
            desc: vec![
                (Ty::Strong, "+12%", tok::ICHOR),
                (Ty::Body, " crit chance; ", body),
                (Ty::Strong, "+30%", tok::ICHOR),
                (Ty::Body, " damage to ", body),
                (Ty::Strong, "Shocked", storm),
                (Ty::Body, " enemies.", body),
            ],
            new: true,
            level: 1,
        },
        BoonSample {
            rarity: Rarity::Godforged,
            gods: vec![("zephyros", zeph)],
            icon: "boons/zephyros_thousandfold_thunder",
            kind: Some(("Legendary", "boon_kind/legendary")),
            name: "THOUSANDFOLD",
            desc: vec![
                (Ty::Body, "Hits arc to ", body),
                (Ty::Strong, "4", tok::ICHOR),
                (Ty::Body, " more enemies, losing only ", body),
                (Ty::Strong, "15%", tok::ICHOR),
                (Ty::Body, " per jump.", body),
            ],
            new: true,
            level: 1,
        },
    ];
    board_root(&mut commands, |b| {
        at(b, 0.0, 0.0, row(26.0), |c| {
            gradient_text(
                c,
                kit,
                Ty::Title,
                30.0,
                "PREMIUM PIECES",
                &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                true,
            );
            c.spawn(kit.text_flat(
                Ty::Flavour,
                17.0,
                "kit widgets assembled into panel specimens · §6–§7",
                tok::PARCH_DIM,
            ));
        });
        at(b, 0.0, 44.0, Node::default(), |c| {
            ember_knot(c, kit, BOARD.x, Gem::Ivory, 0.9);
        });

        // ── the boon spread ──
        let spread_w = 4.0 * NICHE.x + 3.0 * 34.0;
        at(
            b,
            0.0,
            66.0,
            Node {
                width: px(spread_w),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(6.0),
                ..default()
            },
            |c| {
                gradient_text(c, kit, Ty::Title, 32.0, "ZEPHYROS ANSWERS", &[hx(0xFFFFFF), hx(0xBDF2FF), zeph], true);
                ember_knot(c, kit, 520.0, Gem::Tint(zeph), 1.0);
                c.spawn(kit.text_flat(Ty::Flavour, 17.0, "Shrine of Zephyros · choose one", tok::PARCH_DIM));
            },
        );
        for (i, s) in samples.iter().enumerate() {
            let x = i as f32 * (NICHE.x + 34.0);
            at(b, x, 170.0, Node::default(), |c| {
                let spec = NicheSpec {
                    rarity: s.rarity,
                    gods: s.gods.iter().map(|(k, c)| (k.to_string(), *c)).collect(),
                    icon: s.icon.to_string(),
                    crest: s.kind.is_some_and(|k| k.0 == "Legendary"),
                };
                niche_card(c, kit, &spec, |card| {
                    let god_line = s.gods.iter().map(|(k, _)| k.to_uppercase()).collect::<Vec<_>>().join(" & ");
                    let line_color = crate::palette::mix(s.gods[0].1, Color::WHITE, 0.45);
                    let mut y = 132.0;
                    card.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(0.0),
                            top: px(y),
                            width: px(NICHE.x),
                            justify_content: JustifyContent::Center,
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|l| {
                        l.spawn(kit.text_tracked(Ty::LabelS, 13.0, 0.23, god_line, line_color));
                    });
                    if let Some((kind, key)) = s.kind {
                        card.spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: px(0.0),
                                top: px(y + 22.0),
                                width: px(NICHE.x),
                                justify_content: JustifyContent::Center,
                                ..default()
                            },
                            Pickable::IGNORE,
                        ))
                        .with_children(|l| {
                            pill(l, kit, PillKind::Gold, kind, Some(key));
                        });
                        y += 22.0;
                    }
                    let name_color = rarity_color(s.rarity);
                    let name_color = if s.rarity == Rarity::Common { tok::PARCH } else { name_color };
                    card.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(0.0),
                            top: px(y + 30.0),
                            width: px(NICHE.x),
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::Center,
                            row_gap: px(8.0),
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|n| {
                        if s.rarity == Rarity::Godforged {
                            gradient_text(
                                n,
                                kit,
                                Ty::CardName,
                                24.0,
                                s.name,
                                &[hx(0xFFF6D8), hx(0xFFD36B), hx(0xFFB82E)],
                                false,
                            );
                        } else {
                            n.spawn(kit.text_px(Ty::CardName, 24.0, s.name, name_color));
                        }
                        ribbon(n, kit, s.rarity);
                        ember_knot(n, kit, 204.0, Gem::None, 0.9);
                        rich(n, kit, 18.0, &s.desc, Some(248.0), Justify::Center);
                    });
                    // Footer: NEW / UPGRADE, level pips, the pick keycap on the plinth.
                    card.spawn((abs(26.0, 378.0, 80.0, 16.0), Pickable::IGNORE)).with_children(|f| {
                        let (w, c) = if s.new { ("NEW", tok::ICHOR) } else { ("UPGRADE", tok::PARCH_DIM) };
                        f.spawn(kit.text_flat(Ty::Micro, 11.0, w, c));
                    });
                    card.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            right: px(34.0),
                            top: px(381.0),
                            column_gap: px(5.0),
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|f| {
                        for lv in 0..3 {
                            f.spawn((
                                Node {
                                    width: px(10.0),
                                    height: px(10.0),
                                    border_radius: BorderRadius::MAX,
                                    ..default()
                                },
                                BackgroundColor(if lv < s.level { tok::ICHOR } else { hx(0x3A2A1C) }),
                                if lv < s.level {
                                    glow(tok::ICHOR_GLOW.with_alpha(0.5), 5.0, 0.0)
                                } else {
                                    BoxShadow::default()
                                },
                            ));
                        }
                    });
                    card.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(0.0),
                            top: px(390.0),
                            width: px(NICHE.x),
                            justify_content: JustifyContent::Center,
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|k| {
                        keycap(k, kit, &(i + 1).to_string(), 30.0);
                    });
                });
            });
        }
        at(b, 32.0, 612.0, Node::default(), |c| {
            button(c, kit, ButtonKind::Secondary, "Reroll", 236.0, 46.0, |t| {
                t.spawn(row(6.0)).with_children(|r| {
                    keycap(r, kit, "X", 22.0);
                    r.spawn(kit.text_flat(Ty::BodyS, 15.0, "1 left", tok::PARCH_DIM));
                });
            });
        });
        at(b, spread_w - 268.0, 612.0, Node::default(), |c| {
            button(c, kit, ButtonKind::Secondary, "Later", 236.0, 46.0, |t| {
                t.spawn(row(6.0)).with_children(|r| {
                    keycap(r, kit, "Tab", 22.0);
                    r.spawn(kit.text_flat(Ty::BodyS, 15.0, "+1 queued", tok::PARCH_DIM));
                });
            });
        });

        // ── right column: banner, callout, boss bar ──
        let rx = spread_w + 50.0;
        let rw = BOARD.x - rx;
        at(
            b,
            rx,
            70.0,
            Node {
                width: px(rw),
                height: px(120.0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(4.0),
                ..default()
            },
            |c| {
                halo(
                    c,
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(-40.0),
                        right: px(-40.0),
                        top: px(-10.0),
                        bottom: px(-10.0),
                        ..default()
                    },
                    tok::POOL,
                    0.7,
                );
                ember_knot(c, kit, 300.0, Gem::Ivory, 1.0);
                gradient_text(c, kit, Ty::Banner, 44.0, "EMBERFALL", &[hx(0xFFF4D0), tok::GOLD_LT, hx(0xB07A30)], true);
                c.spawn(kit.text_px(Ty::Flavour, 18.0, "Cinder Wastes · the anvils still remember", tok::PARCH_DIM));
            },
        );
        at(
            b,
            rx,
            222.0,
            Node {
                width: px(rw),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(6.0),
                ..default()
            },
            |c| {
                c.spawn(row(12.0)).with_children(|r| {
                    element_cabochon(r, kit, "kinetic", 30.0);
                    gradient_text(
                        r,
                        kit,
                        Ty::Callout,
                        38.0,
                        "RAILSHOCK",
                        &[hx(0xFFF8E6), crate::palette::element_color(DamageType::Kinetic), storm],
                        true,
                    );
                    element_cabochon(r, kit, "storm", 30.0);
                    r.spawn(kit.text_px(Ty::Num, 26.0, "×6", tok::GOLD_LT));
                });
                ember_knot(c, kit, 330.0, Gem::None, 0.9);
            },
        );
        at(
            b,
            rx,
            318.0,
            Node {
                width: px(rw),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(4.0),
                ..default()
            },
            |c| {
                c.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.4, "WARLORD", tok::ENEMY_LABEL));
                gradient_text(
                    c,
                    kit,
                    Ty::BossName,
                    30.0,
                    "THE BELLOWS",
                    &[hx(0xFFF4E0), hx(0xFFD2A0), hx(0xE8783A)],
                    true,
                );
                c.spawn(Node { width: px(360.0), height: px(22.0), margin: UiRect::vertical(px(6.0)), ..default() })
                    .with_children(|w| {
                        let e = bar(w, kit, BarSpec::new(340.0, 18.0, BarFill::Boss).horns());
                        w.commands_mut().entity(e).insert((
                            KitBar { value: 0.58, ward: 0.0 },
                            Node { margin: UiRect::left(px(10.0)), width: px(340.0), height: px(18.0), ..default() },
                        ));
                        w.spawn(Node {
                            position_type: PositionType::Absolute,
                            left: px(10.0),
                            top: px(0.0),
                            ..default()
                        })
                        .with_children(|n| {
                            notches(n, kit, 340.0, &[0.66, 0.33]);
                        });
                    });
                c.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.24, "II · BLAZE", tok::ENEMY_PHASE));
            },
        );

        // ── end-screen party card (MVP) ──
        at(b, rx + (rw - 330.0) / 2.0, 470.0, Node::default(), |c| {
            gilt_panel(
                c,
                kit,
                Node {
                    width: px(330.0),
                    height: px(314.0),
                    padding: UiRect::all(px(24.0)),
                    flex_direction: FlexDirection::Column,
                    row_gap: px(8.0),
                    ..default()
                },
                PanelStyle::horns(40),
                |p| {
                    p.spawn((abs(14.0, 14.0, 302.0, 4.0), BackgroundColor(players[0]), Pickable::IGNORE));
                    p.spawn(row(14.0)).with_children(|r| {
                        r.spawn(Node {
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::Center,
                            ..default()
                        })
                        .with_children(|m| {
                            medallion(m, kit, MedallionSpec::new(68.0).portrait("portraits/valdris").band(players[0]));
                            let pc = pchip(m, kit, 0, players[0]);
                            m.commands_mut().entity(pc).insert(Node {
                                width: px(30.0),
                                height: px(18.0),
                                margin: UiRect::top(px(-9.0)),
                                justify_content: JustifyContent::Center,
                                align_items: AlignItems::Center,
                                ..default()
                            });
                        });
                        r.spawn(column(2.0)).with_children(|t| {
                            t.spawn(kit.text_flat(Ty::Strong, 22.0, "Host", tok::PARCH));
                            t.spawn(kit.text_tracked(Ty::LabelS, 13.0, 0.2, "VALDRIS", players[0]));
                        });
                    });
                    p.spawn((abs(262.0, 18.0, 44.0, 44.0), Pickable::IGNORE)).with_children(|m| {
                        medallion(
                            m,
                            kit,
                            MedallionSpec::new(34.0).enamel(hx(0x6A4A1A)).glyph("team/mvp", 0.8, Color::WHITE),
                        );
                    });
                    p.spawn(Node {
                        justify_content: JustifyContent::SpaceBetween,
                        align_items: AlignItems::FlexEnd,
                        margin: UiRect::top(px(6.0)),
                        ..default()
                    })
                    .with_children(|r| {
                        r.spawn(column(0.0)).with_children(|k| {
                            k.spawn(kit.text_flat(Ty::NumM, 26.0, "1,204", tok::NUMERAL));
                            k.spawn(kit.text_flat(Ty::Micro, 11.0, "KILLS", tok::PARCH_DIM));
                        });
                        r.spawn(Node {
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::FlexEnd,
                            ..default()
                        })
                        .with_children(|k| {
                            k.spawn(kit.text_flat(Ty::NumM, 26.0, "44%", tok::NUMERAL));
                            k.spawn(kit.text_flat(Ty::Micro, 11.0, "OF THE DAMAGE", tok::PARCH_DIM));
                        });
                    });
                    let share = bar(p, kit, BarSpec::new(282.0, 8.0, BarFill::Tint(players[0])));
                    p.commands_mut().entity(share).insert(KitBar { value: 0.95, ward: 0.0 });
                    p.spawn(kit.text_flat(Ty::Micro, 11.0, "THE WEAPON", tok::GOLD_LT));
                    p.spawn(row(10.0)).with_children(|r| {
                        slot(
                            r,
                            kit,
                            SlotSpec::new(SlotShape::HexFlat, 44.0)
                                .icon("chassis/colossus_cannon")
                                .icon_frac(0.7)
                                .shadow(false),
                        );
                        for (shape, key) in [
                            (SlotShape::Round, "parts/stormcore"),
                            (SlotShape::Octagon, "parts/mech_ricochet"),
                            (SlotShape::Arch, "parts/relic_nyctian_eye"),
                            (SlotShape::Lozenge, "parts/sigil_anvilheart"),
                        ] {
                            slot(r, kit, SlotSpec::new(shape, 40.0).icon(key).icon_frac(0.68).shadow(false));
                        }
                    });
                    p.spawn(row(8.0)).with_children(|r| {
                        r.spawn(kit.text_flat(Ty::Micro, 11.0, "BOONS", tok::GOLD_LT));
                        for g in ["zephyros", "nyctia", "aeon", "seraphel"] {
                            icon(r, &format!("gods/{g}"), 24.0, Color::WHITE);
                        }
                    });
                },
            );
            let _ = seraphel;
        });

        // ── the minimap hook (phase 3 fills it; shown here with a stand-in map) ──
        at(b, rx + (rw - 286.0) / 2.0, 800.0, Node::default(), |c| {
            let frame = minimap_frame(c, kit, Node::default());
            let dots: Vec<(f32, f32, Color)> = vec![
                (120.0, 80.0, players[0]),
                (140.0, 92.0, players[1]),
                (98.0, 70.0, players[2]),
                (150.0, 60.0, players[3]),
            ];
            c.commands_mut().queue(move |w: &mut World| {
                let Some(parts) = w.get::<MinimapFrame>(frame).copied() else { return };
                if let Some(mut n) = w.get_mut::<Node>(frame) {
                    n.display = Display::Flex;
                }
                // A sepia stand-in for the phase-3 map texture.
                w.entity_mut(parts.content).insert(BackgroundGradient(vec![
                    RadialGradient::new(
                        UiPosition::CENTER.at_percent(-10.0, 5.0),
                        RadialGradientShape::FarthestCorner,
                        vec![
                            ColorStop::percent(hx(0x967650), 0.0),
                            ColorStop::percent(hx(0x463424), 38.0),
                            ColorStop::percent(hx(0x140E0A), 100.0),
                        ],
                    )
                    .into(),
                ]));
                for (x, y, color) in dots {
                    let dot = w
                        .spawn((
                            Node {
                                border_radius: BorderRadius::MAX,
                                border: UiRect::all(px(1.0)),
                                ..centered_at(x, y, 8.0, 8.0)
                            },
                            BackgroundColor(color),
                            BorderColor::all(tok::INK),
                        ))
                        .id();
                    w.entity_mut(parts.icons).add_child(dot);
                }
            });
        });

        // ── a Forge strip ──
        at(b, 0.0, 700.0, Node::default(), |c| {
            gilt_panel(
                c,
                kit,
                Node {
                    width: px(spread_w),
                    height: px(280.0),
                    padding: UiRect::axes(px(34.0), px(26.0)),
                    column_gap: px(36.0),
                    ..default()
                },
                PanelStyle::horns(64).crest(62),
                |p| {
                    p.spawn(Node {
                        flex_direction: FlexDirection::Column,
                        row_gap: px(10.0),
                        width: px(560.0),
                        ..default()
                    })
                    .with_children(|l| {
                        l.spawn(row(18.0)).with_children(|r| {
                            let ring = ring_meter(
                                r,
                                Node {
                                    width: px(56.0),
                                    height: px(56.0),
                                    justify_content: JustifyContent::Center,
                                    align_items: AlignItems::Center,
                                    ..default()
                                },
                                6.0,
                                RingStyle::Molten,
                                0.63,
                            );
                            r.commands_mut().entity(ring).with_children(|h| {
                                h.spawn(kit.text_flat(Ty::NumM, 22.0, "19", tok::NUMERAL));
                            });
                            r.spawn(row(2.0)).with_children(|h| {
                                for lit in [true, true, false] {
                                    icon(
                                        h,
                                        "currency/forge_charge",
                                        28.0,
                                        if lit { Color::WHITE } else { hx(0x5A5048) },
                                    );
                                }
                            });
                            r.spawn(column(0.0)).with_children(|t| {
                                gradient_text(
                                    t,
                                    kit,
                                    Ty::Title,
                                    36.0,
                                    "THE FORGE",
                                    &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                                    true,
                                );
                                t.spawn(kit.text_flat(
                                    Ty::Flavour,
                                    17.0,
                                    "The Chainyard anvil burns hot",
                                    tok::PARCH_DIM,
                                ));
                            });
                        });
                        ember_knot(l, kit, 520.0, Gem::Ivory, 1.0);
                        l.spawn(row(12.0)).with_children(|r| {
                            r.spawn(kit.text_flat(Ty::NumXl, 38.0, "1,284", tok::NUMERAL));
                            r.spawn(kit.text_flat(Ty::Label, 15.0, "DPS", tok::PARCH_DIM));
                            let arrow = icon(r, "ui/bearing", 22.0, tok::GOLD_LT);
                            r.commands_mut().entity(arrow).insert(UiTransform::from_rotation(Rot2::radians(PI / 2.0)));
                            r.spawn(kit.text_flat(Ty::NumXl, 38.0, "1,592", tok::ICHOR));
                            delta_chip(r, kit, 24.0, 20.0);
                        });
                        dashed_plate(
                            l,
                            kit,
                            Node {
                                width: px(520.0),
                                height: px(58.0),
                                padding: UiRect::horizontal(px(14.0)),
                                column_gap: px(12.0),
                                align_items: AlignItems::Center,
                                ..default()
                            },
                            |d| {
                                icon(d, "currency/seal", 34.0, Color::WHITE);
                                d.spawn(column(0.0)).with_children(|t| {
                                    t.spawn(kit.text_flat(Ty::Micro, 11.0, "ONE PART AWAY", tok::ICHOR));
                                    t.spawn(kit.text_flat(Ty::Label, 16.0, "THE ENDLESS ARGUMENT", tok::GOLD_LT));
                                    t.spawn(kit.text_flat(
                                        Ty::BodyS,
                                        14.0,
                                        "+1 chain, +10% damage · Doomstack is in your bag",
                                        tok::PARCH_DIM,
                                    ));
                                });
                            },
                        );
                    });
                    p.spawn(row(12.0)).with_children(|r| {
                        for (label, shape, key, name, rarity, replace) in [
                            ("CORE", SlotShape::Round, "parts/stormcore", "Stormcore", Rarity::Rare, false),
                            ("MECHANISM", SlotShape::Octagon, "parts/mech_ricochet", "Ricochet", Rarity::Epic, false),
                            ("RELIC", SlotShape::Arch, "parts/relic_nyctian_eye", "Nyctian Eye", Rarity::Rare, true),
                            (
                                "SIGIL",
                                SlotShape::Lozenge,
                                "parts/sigil_anvilheart",
                                "Anvilheart",
                                Rarity::Godforged,
                                false,
                            ),
                        ] {
                            let card = gilt_card(
                                r,
                                kit,
                                rarity,
                                Node {
                                    width: px(138.0),
                                    height: px(200.0),
                                    padding: UiRect::top(px(14.0)),
                                    flex_direction: FlexDirection::Column,
                                    align_items: AlignItems::Center,
                                    row_gap: px(8.0),
                                    ..default()
                                },
                                |s| {
                                    s.spawn(kit.text_tracked(Ty::Micro, 12.0, 0.16, label, tok::PARCH_DIM));
                                    slot(s, kit, SlotSpec::new(shape, 74.0).icon(key).icon_frac(0.66));
                                    s.spawn(kit.text_flat(Ty::Strong, 16.0, name, rarity_color(rarity)));
                                    chip(s, kit, "Reroll", Some("ui/reroll"), 112.0, |t| {
                                        t.spawn(kit.text_flat(Ty::Num, 14.0, "6", tok::PARCH));
                                    });
                                },
                            );
                            if replace {
                                r.commands_mut().queue(move |w: &mut World| {
                                    if let Some(mut k) = w.get_mut::<KitCard>(card) {
                                        k.selected = true;
                                    }
                                });
                                r.commands_mut().entity(card).with_children(|t| {
                                    t.spawn((
                                        Node {
                                            position_type: PositionType::Absolute,
                                            left: px(0.0),
                                            right: px(0.0),
                                            top: px(-10.0),
                                            justify_content: JustifyContent::Center,
                                            ..default()
                                        },
                                        ZIndex(5),
                                        Pickable::IGNORE,
                                    ))
                                    .with_children(|pt| {
                                        pill(pt, kit, PillKind::Gold, "Replace", None);
                                    });
                                });
                            }
                        }
                    });
                },
            );
        });
    });
}
