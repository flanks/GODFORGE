//! Heads-up display (§12, §20.6): vitals, kit cooldowns, the forged weapon, party frames, boss
//! bar, contextual prompts, event toasts, world-anchored labels and the touch overlay. Built with
//! mobile in mind: large glyphs, thumb-reachable hit targets, nothing load-bearing on hover.

use crate::camera::{MainCamera, w3};
use crate::input::{Device, InputState, Settings};
use crate::net::{Link, Prediction};
use crate::palette::{element_color, hex, rarity_color};
use crate::scene::{SceneIndex, Visual, door_label};
use crate::{ClientConfig, ClientSet, UiFonts};
use gf_content::ContentDb;
use gf_core::aim::AimMode;
use gf_core::forge::{ForgeOutcome, Slot};
use gf_core::revive::LifeState;
use gf_engine::client::{font_px, text, text_in, world_to_screen};
use gf_engine::prelude::*;
use gf_net::*;

/// Touch hit zones in normalized window coordinates (x right, y down) → button index
/// (0 dash, 1 active 1, 2 active 2, 3 ultimate, 4 interact). ≥ 44 px targets at phone sizes.
pub const TOUCH_BUTTONS: [(Vec2, u8); 5] = [
    (Vec2::new(0.91, 0.80), 0),
    (Vec2::new(0.80, 0.88), 1),
    (Vec2::new(0.79, 0.70), 2),
    (Vec2::new(0.91, 0.60), 3),
    (Vec2::new(0.68, 0.88), 4),
];

const INK: Color = Color::srgba(0.05, 0.035, 0.03, 0.82);
const EDGE: Color = Color::srgba(0.78, 0.6, 0.32, 0.55);
const PARCHMENT: Color = Color::srgb(0.96, 0.9, 0.78);
const DIM: Color = Color::srgb(0.7, 0.64, 0.56);

#[derive(Component, Clone, Copy, PartialEq, Eq, Debug)]
enum Bar {
    Hp,
    Shield,
    Armor,
    Passive,
    Cooldown(u8),
    Ult,
    Overdrive,
    Encounter,
    Boss,
    Party(u8),
    Charge,
}

/// Fill node of a bar (width = fraction).
#[derive(Component)]
struct Fill(Bar);

#[derive(Component, Clone, Copy, PartialEq, Eq, Debug)]
enum Label {
    Name,
    Vitals,
    Dash,
    Key(u8),
    Room,
    Boss,
    Weapon,
    Slot(u8),
    Traits,
    Aim,
    Stats,
    Net,
    Prompt,
    Party(u8),
    Help,
    OverdriveHint,
}

#[derive(Component)]
struct PartyRow(u8);

#[derive(Component)]
struct ToastList;

#[derive(Component)]
struct Toast {
    life: f32,
    key: String,
    count: u32,
}

/// Pooled world-anchored label (door names, ally tags, elite bars).
#[derive(Component)]
struct WorldLabel;

#[derive(Component)]
struct WorldBar;

#[derive(Component)]
struct TouchOverlay;

#[derive(Component)]
struct TouchStick(bool);

const LABEL_POOL: usize = 12;
const BAR_POOL: usize = 16;

pub fn build(app: &mut App) {
    app.add_systems(Startup, spawn_hud).add_systems(
        Update,
        (update_labels, update_bars, update_party, toasts, world_labels, touch_overlay).in_set(ClientSet::Presentation),
    );
}

fn panel(node: Node) -> impl Bundle {
    (
        Node {
            padding: UiRect::all(Val::Px(8.0)),
            border: UiRect::all(Val::Px(1.0)),
            border_radius: BorderRadius::all(Val::Px(6.0)),
            ..node
        },
        BackgroundColor(INK),
        BorderColor::all(EDGE),
    )
}

fn bar(parent: &mut ChildSpawnerCommands, which: Bar, width: f32, height: f32, color: Color) {
    parent
        .spawn((
            which,
            Node {
                width: Val::Px(width),
                height: Val::Px(height),
                border: UiRect::all(Val::Px(1.0)),
                border_radius: BorderRadius::all(Val::Px(3.0)),
                overflow: Overflow::clip(),
                ..default()
            },
            BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.6)),
            BorderColor::all(Color::srgba(1.0, 0.9, 0.7, 0.25)),
        ))
        .with_children(|b| {
            b.spawn((
                Fill(which),
                Node { width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() },
                BackgroundColor(color),
            ));
        });
}

fn spawn_hud(mut commands: Commands, fonts: Res<UiFonts>) {
    let display = fonts.display.clone();
    // Top-left: vitals and kit.
    commands
        .spawn(panel(Node {
            position_type: PositionType::Absolute,
            left: Val::Px(14.0),
            top: Val::Px(14.0),
            flex_direction: FlexDirection::Column,
            row_gap: Val::Px(4.0),
            ..default()
        }))
        .with_children(|p| {
            p.spawn((Label::Name, text_in("", 18.0, PARCHMENT, &display)));
            bar(p, Bar::Hp, 260.0, 16.0, hex("#D8363A"));
            bar(p, Bar::Shield, 260.0, 6.0, hex("#BFEFFF"));
            bar(p, Bar::Armor, 260.0, 8.0, hex("#A8A29A"));
            p.spawn((Label::Vitals, text("", 13.0, DIM)));
            p.spawn((Label::Dash, text("", 14.0, PARCHMENT)));
            p.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(6.0), ..default() }).with_children(
                |row| {
                    for (i, (which, color)) in [
                        (Bar::Cooldown(0), hex("#FFC940")),
                        (Bar::Cooldown(1), hex("#FFC940")),
                        (Bar::Ult, hex("#FF8A2A")),
                    ]
                    .into_iter()
                    .enumerate()
                    {
                        row.spawn(Node { flex_direction: FlexDirection::Column, row_gap: Val::Px(2.0), ..default() })
                            .with_children(|c| {
                                c.spawn((Label::Key(i as u8), text("", 12.0, PARCHMENT)));
                                bar(c, which, 82.0, 8.0, color);
                            });
                    }
                },
            );
            bar(p, Bar::Passive, 260.0, 5.0, hex("#7FF6FF"));
            bar(p, Bar::Charge, 260.0, 5.0, hex("#FFFFFF"));
        });

    // Top-center: run banner, encounter progress, boss bar, toasts.
    commands
        .spawn(Node {
            position_type: PositionType::Absolute,
            top: Val::Px(12.0),
            width: Val::Percent(100.0),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: Val::Px(6.0),
            ..default()
        })
        .with_children(|c| {
            c.spawn(panel(Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: Val::Px(4.0),
                ..default()
            }))
            .with_children(|p| {
                p.spawn((Label::Room, text_in("", 17.0, PARCHMENT, &display)));
                bar(p, Bar::Encounter, 300.0, 5.0, hex("#FF8A2A"));
            });
            c.spawn((
                Bar::Boss,
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    row_gap: Val::Px(3.0),
                    ..default()
                },
            ))
            .with_children(|p| {
                p.spawn((Label::Boss, text_in("", 22.0, hex("#FFD27A"), &display), TextShadow::default()));
                bar(p, Bar::Boss, 520.0, 14.0, hex("#C0262B"));
            });
            c.spawn((
                ToastList,
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    row_gap: Val::Px(2.0),
                    ..default()
                },
            ));
        });

    // Top-right: party frames + net.
    commands
        .spawn(panel(Node {
            position_type: PositionType::Absolute,
            right: Val::Px(14.0),
            top: Val::Px(14.0),
            flex_direction: FlexDirection::Column,
            row_gap: Val::Px(5.0),
            min_width: Val::Px(200.0),
            ..default()
        }))
        .with_children(|p| {
            for i in 0..3u8 {
                p.spawn((
                    PartyRow(i),
                    Node {
                        flex_direction: FlexDirection::Column,
                        row_gap: Val::Px(2.0),
                        display: Display::None,
                        ..default()
                    },
                ))
                .with_children(|r| {
                    r.spawn((Label::Party(i), text("", 13.0, PARCHMENT)));
                    bar(r, Bar::Party(i), 190.0, 7.0, hex("#D8363A"));
                });
            }
            p.spawn((Label::Net, text("", 11.0, DIM)));
        });

    // Bottom-center: prompt + the forged weapon.
    commands
        .spawn(Node {
            position_type: PositionType::Absolute,
            bottom: Val::Px(12.0),
            width: Val::Percent(100.0),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: Val::Px(8.0),
            ..default()
        })
        .with_children(|c| {
            c.spawn((Label::Prompt, text_in("", 21.0, hex("#FFE3A3"), &display), TextShadow::default()));
            c.spawn(panel(Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: Val::Px(4.0),
                ..default()
            }))
            .with_children(|p| {
                p.spawn((Label::Weapon, text_in("", 17.0, PARCHMENT, &display)));
                p.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(10.0), ..default() })
                    .with_children(|row| {
                        for s in 0..4u8 {
                            row.spawn(Node {
                                flex_direction: FlexDirection::Column,
                                align_items: AlignItems::Center,
                                min_width: Val::Px(118.0),
                                ..default()
                            })
                            .with_children(|chip| {
                                chip.spawn(text(Slot::ALL[s as usize].name().to_uppercase(), 10.0, DIM));
                                chip.spawn((Label::Slot(s), text("", 14.0, DIM)));
                            });
                        }
                    });
                p.spawn((Label::Traits, text("", 12.0, DIM)));
            });
        });

    // Bottom-left: aim mode + overdrive.
    commands
        .spawn(panel(Node {
            position_type: PositionType::Absolute,
            left: Val::Px(14.0),
            bottom: Val::Px(14.0),
            flex_direction: FlexDirection::Column,
            row_gap: Val::Px(4.0),
            ..default()
        }))
        .with_children(|p| {
            p.spawn((Label::Aim, text("", 15.0, PARCHMENT)));
            p.spawn((Label::OverdriveHint, text("", 13.0, hex("#FFC940"))));
            bar(p, Bar::Overdrive, 220.0, 8.0, hex("#FFC940"));
        });

    // Bottom-right: run stats.
    commands
        .spawn(panel(Node {
            position_type: PositionType::Absolute,
            right: Val::Px(14.0),
            bottom: Val::Px(14.0),
            ..default()
        }))
        .with_children(|p| {
            p.spawn((Label::Stats, text("", 14.0, PARCHMENT)));
        });

    // Help overlay.
    commands
        .spawn((
            Label::Help,
            panel(Node {
                position_type: PositionType::Absolute,
                left: Val::Percent(30.0),
                top: Val::Percent(22.0),
                display: Display::None,
                ..default()
            }),
            GlobalZIndex(20),
        ))
        .with_children(|p| {
            p.spawn(text(HELP, 15.0, PARCHMENT));
        });

    // World-anchored label and bar pools.
    for _ in 0..LABEL_POOL {
        commands.spawn((
            WorldLabel,
            text("", 14.0, PARCHMENT),
            TextShadow { offset: Vec2::new(1.0, 1.0), color: Color::srgba(0.0, 0.0, 0.0, 0.9) },
            Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
        ));
    }
    for _ in 0..BAR_POOL {
        commands
            .spawn((
                WorldBar,
                Node {
                    position_type: PositionType::Absolute,
                    width: Val::Px(46.0),
                    height: Val::Px(5.0),
                    display: Display::None,
                    border: UiRect::all(Val::Px(1.0)),
                    ..default()
                },
                BackgroundColor(Color::srgba(0.0, 0.0, 0.0, 0.7)),
                BorderColor::all(Color::srgba(0.0, 0.0, 0.0, 0.9)),
            ))
            .with_children(|b| {
                b.spawn((
                    Node { width: Val::Percent(100.0), height: Val::Percent(100.0), ..default() },
                    BackgroundColor(hex("#E0312B")),
                ));
            });
    }

    // Touch overlay (shown only when the last input came from touch).
    for (zone, which) in TOUCH_BUTTONS {
        let glyph = ["DASH", "Q", "E", "ULT", "USE"][which as usize];
        commands
            .spawn((
                TouchOverlay,
                Node {
                    position_type: PositionType::Absolute,
                    left: Val::Percent(zone.x * 100.0 - 3.5),
                    top: Val::Percent(zone.y * 100.0 - 5.5),
                    width: Val::Px(72.0),
                    height: Val::Px(72.0),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    border: UiRect::all(Val::Px(2.0)),
                    border_radius: BorderRadius::MAX,
                    display: Display::None,
                    ..default()
                },
                BackgroundColor(Color::srgba(0.1, 0.07, 0.05, 0.45)),
                BorderColor::all(EDGE),
            ))
            .with_children(|b| {
                b.spawn(text(glyph, 14.0, PARCHMENT));
            });
    }
    for aim in [false, true] {
        commands.spawn((
            TouchStick(aim),
            Node {
                position_type: PositionType::Absolute,
                width: Val::Px(120.0),
                height: Val::Px(120.0),
                border: UiRect::all(Val::Px(2.0)),
                border_radius: BorderRadius::MAX,
                display: Display::None,
                ..default()
            },
            BorderColor::all(Color::srgba(1.0, 0.9, 0.7, 0.4)),
        ));
    }
}

const HELP: &str = "GODFORGE — controls\n\n\
WASD move · Mouse aim · LMB fire · Space dash\n\
Q / E(RMB) abilities · R ultimate · V Team Overdrive\n\
F interact (doors, revive, anvil) · Tab forge panel\n\
T force-target · G / MMB ping · B target bias\n\
F1 AUTO · F2 ASSISTED · F3 MANUAL · M cycle aim mode\n\
N damage numbers · K screen shake · H this help\n\n\
Gamepad: sticks move/aim, RT fire, RB/A dash, LB/LT abilities,\n\
Y ultimate, X interact, B overdrive, D-pad up aim mode.";

fn player_name(link: &Link, slot: u8) -> String {
    link.roster.iter().find(|r| r.slot == slot).map_or(format!("P{}", slot + 1), |r| r.name.clone())
}

fn character_name(db: &ContentDb, id: u16) -> String {
    db.characters.try_get(id).map_or("?".into(), |c| c.name.clone())
}

fn part_name(db: &ContentDb, part: gf_core::ids::PartId) -> String {
    db.parts.try_get(part.0).map_or("?".into(), |p| p.name.clone())
}

#[allow(clippy::too_many_arguments)]
fn update_labels(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pred: Res<Prediction>,
    input: Res<InputState>,
    settings: Res<Settings>,
    mut q: Query<(&Label, &mut Text, &mut TextColor)>,
    mut help: Query<(&Label, &mut Node)>,
) {
    let db = &cfg.content;
    for (l, mut node) in &mut help {
        if *l == Label::Help {
            node.display = if settings.help { Display::Flex } else { Display::None };
        }
    }
    let world = link.latest.as_deref();
    let me = link.me();
    for (label, mut t, mut color) in &mut q {
        if matches!(label, Label::Party(_) | Label::Help) {
            continue;
        }
        let s: String = match (*label, world, me) {
            (Label::Name, _, Some(p)) => {
                let ch = db.characters.try_get(p.character);
                format!(
                    "{} — {}",
                    player_name(&link, p.slot),
                    ch.map_or(String::new(), |c| format!("{}, {}", c.name, c.title))
                )
            }
            (Label::Name, _, None) => match link.rejected {
                Some(r) => format!("Rejected by host: {r:?}"),
                None => format!("Connecting… ({})", link.host_label),
            },
            (Label::Vitals, _, Some(p)) => {
                let mut s = format!("HP {:.0}/{:.0}", p.hp.max(0.0), p.max_hp);
                if p.shield > 0.0 {
                    s += &format!("  Shield {:.0}", p.shield);
                }
                if p.armor_max > 0.0 {
                    s += &format!("  Armor {:.0}", p.armor);
                }
                s
            }
            (Label::Dash, _, Some(p)) => {
                let full = p.mover.dash_charges as usize;
                let max = p.max_dash as usize;
                let pips: String = (0..max).map(|i| if i < full { '◆' } else { '◇' }).collect();
                if p.flags.contains(PlayerFlags::INFINITE_DASH) { "Dash ∞".into() } else { format!("Dash {pips}") }
            }
            (Label::Key(i), _, Some(p)) => {
                let kit = db.kit(gf_core::ids::CharacterId(p.character));
                let (key, name) = match i {
                    0 => ("Q", kit.map(|k| k.active1.name.as_str())),
                    1 => ("E", kit.map(|k| k.active2.name.as_str())),
                    _ => ("R", kit.map(|k| k.ultimate.name.as_str())),
                };
                let ready = if i < 2 { p.cooldowns[i as usize] <= 0.0 } else { p.ult >= 1.0 };
                color.0 = if ready { PARCHMENT } else { DIM };
                format!("[{key}] {}", name.unwrap_or("—"))
            }
            (Label::Room, Some(w), _) => {
                let biome = db.biomes.try_get(w.run.biome).map_or("?", |b| b.name.as_str());
                let kind = db.rooms.try_get(w.run.room).map_or("", |r| match r.kind {
                    gf_content::RoomKind::Combat => "",
                    gf_content::RoomKind::Elite => " · Elite",
                    gf_content::RoomKind::Anvil => " · Anvil",
                    gf_content::RoomKind::MiniBoss => " · Mini-boss",
                    gf_content::RoomKind::Boss => " · BOSS",
                    gf_content::RoomKind::Treasure => " · Treasure",
                });
                let chaos =
                    if w.run.chaos_tier > 0 { format!(" · Chaos {}", w.run.chaos_tier) } else { String::new() };
                format!("{biome}{kind} — room {}/{}{chaos}", w.run.step as u32 + 1, w.run.steps)
            }
            (Label::Boss, Some(w), _) => w.run.boss.map_or(String::new(), |b| {
                let def = db.enemies.try_get(b.enemy);
                let phase = def
                    .and_then(|d| db.bosses.by_key(&d.key))
                    .and_then(|s| s.phases.get(b.phase as usize))
                    .map_or(String::new(), |ph| format!(" — {}", ph.name));
                format!("{}{phase}", def.map_or("Boss", |d| d.name.as_str()))
            }),
            (Label::Weapon, _, Some(p)) => {
                let ch = db.chassis.try_get(p.weapon.chassis.0);
                let prof = gf_sim::bot::weapon_for(db, p);
                color.0 = element_color(prof.element);
                format!("{} · {}", ch.map_or("?", |c| c.name.as_str()), prof.element.name())
            }
            (Label::Slot(i), _, Some(p)) => {
                let slot = Slot::ALL[i as usize];
                // Rarity is carried by colour (Common → Rare → Epic → Godforged gold).
                match p.weapon.get(slot) {
                    Some(part) => {
                        color.0 = rarity_color(part.rarity);
                        part_name(db, part.part)
                    }
                    None => {
                        color.0 = DIM;
                        "—".into()
                    }
                }
            }
            (Label::Traits, _, Some(p)) => {
                let prof = gf_sim::bot::weapon_for(db, p);
                gf_core::weapon::describe(&prof).into_iter().skip(1).collect::<Vec<_>>().join(" · ")
            }
            (Label::Aim, _, Some(p)) => {
                let params = db.aim_params(input.aim_mode);
                let extra = match input.aim_mode {
                    AimMode::Auto => format!(" (−{:.0}% dmg)", (1.0 - params.damage_mult) * 100.0),
                    AimMode::Assisted => String::new(),
                    AimMode::Manual => format!(" · Deadeye +{:.0}%", p.deadeye as f32 * params.deadeye_per_hit * 100.0),
                };
                let device = match input.device {
                    Device::KeyboardMouse => "KB/M",
                    Device::Gamepad => "Pad",
                    Device::Touch => "Touch",
                };
                format!("Aim {}{extra} · Bias {} · {device}", input.aim_mode.name(), input.bias.name())
            }
            (Label::OverdriveHint, Some(w), _) => {
                if w.run.overdrive_active > 0.0 {
                    format!("TEAM OVERDRIVE {:.1}s", w.run.overdrive_active)
                } else if w.run.overdrive_meter >= 1.0 {
                    "Team Overdrive READY — [V]".into()
                } else {
                    format!("Team Overdrive {:.0}%", w.run.overdrive_meter * 100.0)
                }
            }
            (Label::Stats, Some(w), me) => {
                let shards = w.private.wallet.godshards;
                let kills = me.map_or(0, |p| p.kills);
                let mins = (w.run.time / 60.0) as u32;
                let secs = w.run.time as u32 % 60;
                format!("Godshards {shards} · Ember {} · Kills {kills} · {mins}:{secs:02}", w.run.ember)
            }
            (Label::Net, _, _) => format!(
                "{} · {:.1} KB/s · corrections {}",
                link.host_label,
                link.bytes_per_sec / 1024.0,
                pred.corrections
            ),
            (Label::Prompt, Some(w), Some(p)) => prompt(db, w, p, &input),
            _ => String::new(),
        };
        if t.0 != s {
            t.0 = s;
        }
    }
}

fn prompt(db: &ContentDb, w: &WorldSnapshot, p: &PlayerView, input: &InputState) -> String {
    match p.life {
        LifeState::Downed { remaining, .. } => {
            return format!("DOWNED — allies can revive you · Soul-Tether {remaining:.0}s");
        }
        LifeState::Reforging { remaining } => return format!("The Forge is reforging you… {remaining:.0}s"),
        LifeState::Alive => {}
    }
    match w.run.phase {
        RunPhase::Victory => return "VICTORY — the Last Arsenal holds".into(),
        RunPhase::Defeat => return "DEFEAT — the forge-fires gutter out".into(),
        RunPhase::Cleared => {
            let near = w.entities.iter().find_map(|e| match e.kind {
                EntityKind::Door { reward, .. } if e.pos.to_vec2().distance(p.mover.pos) < 2.4 => Some(reward),
                _ => None,
            });
            return match near {
                Some(r) => format!("[F] Take the door: {}", door_label(db, r)),
                None => "Room cleared — choose a door".into(),
            };
        }
        RunPhase::Combat => {}
    }
    if !w.private.boon_offer.is_empty() {
        return "A god offers a boon — choose below".into();
    }
    if let Some(a) = w.run.anvil {
        match a.state {
            AnvilState::Dormant => return "[F] at the anvil to kindle it".into(),
            AnvilState::Kindling if a.contested => {
                return format!("Hold the anvil ring! {:.0}% (paused — step inside)", a.progress * 100.0);
            }
            AnvilState::Kindling => return format!("Hold the anvil ring! {:.0}%", a.progress * 100.0),
            AnvilState::Hot if w.private.at_anvil && !input.forge_open => {
                return format!("FORGE HOT — [Tab] open the forge ({:.0}s)", a.time_left);
            }
            AnvilState::Hot if !w.private.at_anvil => {
                return format!("The anvil is HOT — go forge! ({:.0}s)", a.time_left);
            }
            _ => {}
        }
    }
    if w.run.overdrive_meter >= 1.0 && w.run.overdrive_active <= 0.0 {
        return "Team Overdrive ready — [V]".into();
    }
    String::new()
}

#[allow(clippy::type_complexity)]
fn update_bars(
    link: Res<Link>,
    mut fills: Query<(&Fill, &mut Node, &mut BackgroundColor), Without<Bar>>,
    mut boxes: Query<(&Bar, &mut Node), Without<Fill>>,
) {
    let world = link.latest.as_deref();
    let me = link.me();
    let others: Vec<&PlayerView> =
        world.map_or(Vec::new(), |w| w.players.iter().filter(|p| Some(p.slot) != link.slot).collect());
    let frac = |b: Bar| -> Option<f32> {
        let w = world?;
        Some(match b {
            Bar::Hp => {
                let p = me?;
                p.hp / p.max_hp.max(1.0)
            }
            Bar::Shield => {
                let p = me?;
                if p.shield <= 0.0 {
                    return None;
                }
                (p.shield / p.max_hp.max(1.0)).min(1.0)
            }
            Bar::Armor => {
                let p = me?;
                if p.armor_max <= 0.0 {
                    return None;
                }
                p.armor / p.armor_max
            }
            Bar::Passive => {
                let p = me?;
                if p.passive_meter <= 0.0 {
                    return None;
                }
                p.passive_meter
            }
            Bar::Charge => {
                let p = me?;
                if p.charge <= 0.0 {
                    return None;
                }
                p.charge
            }
            Bar::Cooldown(i) => {
                let p = me?;
                let max = p.cooldowns_max[i as usize].max(0.01);
                1.0 - p.cooldowns[i as usize] / max
            }
            Bar::Ult => me?.ult,
            Bar::Overdrive => {
                if w.run.overdrive_active > 0.0 {
                    w.run.overdrive_active / 5.0
                } else {
                    w.run.overdrive_meter
                }
            }
            Bar::Encounter => w.run.encounter_left,
            Bar::Boss => w.run.boss?.hp_frac,
            Bar::Party(i) => {
                let p = others.get(i as usize)?;
                p.hp / p.max_hp.max(1.0)
            }
        })
    };
    for (b, mut node) in &mut boxes {
        let show = frac(*b).is_some();
        let d = if show { Display::Flex } else { Display::None };
        if node.display != d {
            node.display = d;
        }
    }
    for (Fill(b), mut node, mut bg) in &mut fills {
        let f = frac(*b).unwrap_or(0.0).clamp(0.0, 1.0);
        node.width = Val::Percent(f * 100.0);
        if matches!(b, Bar::Cooldown(_) | Bar::Ult) {
            bg.0 = if f >= 1.0 { hex("#FFC940") } else { Color::srgb(0.55, 0.45, 0.3) };
        }
    }
}

fn update_party(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut rows: Query<(&PartyRow, &mut Node)>,
    mut labels: Query<(&Label, &mut Text)>,
) {
    let others: Vec<&PlayerView> =
        link.latest.as_deref().map_or(Vec::new(), |w| w.players.iter().filter(|p| Some(p.slot) != link.slot).collect());
    for (PartyRow(i), mut node) in &mut rows {
        let d = if (*i as usize) < others.len() { Display::Flex } else { Display::None };
        if node.display != d {
            node.display = d;
        }
    }
    for (label, mut t) in &mut labels {
        if let Label::Party(i) = *label
            && let Some(p) = others.get(i as usize)
        {
            let state = match p.life {
                LifeState::Alive => String::new(),
                LifeState::Downed { remaining, .. } => format!(" — DOWNED {remaining:.0}s"),
                LifeState::Reforging { remaining } => format!(" — reforging {remaining:.0}s"),
            };
            let s = format!(
                "P{} {} ({}){state}",
                p.slot + 1,
                player_name(&link, p.slot),
                character_name(&cfg.content, p.character)
            );
            if t.0 != s {
                t.0 = s;
            }
        }
    }
}

fn toast_text(db: &ContentDb, link: &Link, ev: &GameEvent) -> Option<(String, Color)> {
    let me = link.slot;
    let who = |slot: u8| if Some(slot) == me { "You".to_string() } else { player_name(link, slot) };
    let gold = hex("#FFC940");
    Some(match *ev {
        GameEvent::Synergy { synergy, .. } => {
            let name = db.synergies.try_get(synergy).map_or("Synergy", |s| s.name.as_str());
            (format!("{}!", name.to_uppercase()), gold)
        }
        GameEvent::RecipeDiscovered { slot, recipe } => {
            let name = db.recipes.try_get(recipe).map_or("?", |r| r.name.as_str());
            (format!("{} forged a named combo: {name}", who(slot)), hex("#FFB82E"))
        }
        GameEvent::BoonTaken { slot, boon } => {
            let name = db.boons.try_get(boon).map_or("?", |b| b.name.as_str());
            (format!("{} took {name}", who(slot)), hex("#F4E3C1"))
        }
        GameEvent::Forged { slot, outcome } if Some(slot) == me => (
            match outcome {
                ForgeOutcome::Equipped { slot, part, .. } => {
                    format!("Equipped {} in {}", part_name(db, part.part), slot.name())
                }
                ForgeOutcome::Fused { part, .. } => {
                    format!("Fused → {} {}", part.rarity.name(), part_name(db, part.part))
                }
                ForgeOutcome::Rerolled { part, .. } => format!("Rerolled → {}", part_name(db, part.part)),
                ForgeOutcome::Salvaged { shards } => format!("Salvaged for {shards} godshards"),
            },
            hex("#FFB82E"),
        ),
        GameEvent::ForgeFailed { slot, error } if Some(slot) == me => (format!("Forge: {error}"), hex("#FF6A5A")),
        GameEvent::Downed { slot } => (format!("{} went down!", who(slot)), hex("#FF6A5A")),
        GameEvent::Revived { slot, .. } => (format!("{} is back in the fight", who(slot)), gold),
        GameEvent::Overdrive { slot } => (format!("TEAM OVERDRIVE — {}", who(slot)), gold),
        GameEvent::ArmorBreak { slot } if Some(slot) == me => ("Armor broken!".into(), hex("#C9D2DC")),
        GameEvent::RoomCleared => ("Room cleared".into(), hex("#F4E3C1")),
        GameEvent::AnvilLit => ("The anvil kindles — hold the ring!".into(), hex("#FFB82E")),
        GameEvent::AnvilHot => ("The anvil is HOT — forge now!".into(), hex("#FFB82E")),
        GameEvent::BossPhase { phase, .. } if phase > 0 => ("The boss enrages!".into(), hex("#FF6A5A")),
        _ => return None,
    })
}

fn toasts(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    fonts: Res<UiFonts>,
    link: Res<Link>,
    list: Query<Entity, With<ToastList>>,
    mut live: Query<(Entity, &mut Toast, &mut TextColor, &mut Text)>,
) {
    let dt = time.delta_secs();
    let mut count = 0;
    for (e, mut t, mut c, _) in &mut live {
        t.life -= dt;
        if t.life <= 0.0 {
            commands.entity(e).despawn();
        } else {
            count += 1;
            c.0 = c.0.with_alpha(t.life.min(1.0));
        }
    }
    let Ok(parent) = list.single() else { return };
    // Repeats stack into one line ("RAILSHOCK! ×4") instead of flooding the screen — both across
    // frames (live toasts) and within this frame's batch of events.
    let mut batch: Vec<(String, Color, u32)> = Vec::new();
    for ev in &link.fresh_events {
        let Some((s, color)) = toast_text(&cfg.content, &link, ev) else { continue };
        match batch.iter_mut().find(|(k, _, _)| *k == s) {
            Some((_, _, n)) => *n += 1,
            None => batch.push((s, color, 1)),
        }
    }
    for (s, color, n) in batch {
        if let Some((_, mut t, _, mut text)) = live.iter_mut().find(|(_, t, _, _)| t.key == s && t.life > 0.0) {
            t.count += n;
            t.life = 2.8;
            text.0 = format!("{s} ×{}", t.count);
            continue;
        }
        if count >= 5 {
            continue;
        }
        count += 1;
        let label = if n > 1 { format!("{s} ×{n}") } else { s.clone() };
        commands.spawn((
            Toast { life: 2.8, key: s, count: n },
            text_in(label, 18.0, color, &fonts.display),
            TextShadow::default(),
            ChildOf(parent),
        ));
    }
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn world_labels(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    index: Res<SceneIndex>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    visuals: Query<&Visual>,
    rigs: Query<&crate::scene::PlayerRig>,
    mut labels: Query<(&WorldLabel, &mut Node, &mut Text, &mut TextColor, &mut TextFont), Without<WorldBar>>,
    mut bars: Query<(&WorldBar, &mut Node, &Children), Without<WorldLabel>>,
    mut fills: Query<&mut Node, (Without<WorldBar>, Without<WorldLabel>)>,
) {
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let Some(world) = link.latest.as_deref() else { return };
    let db = &cfg.content;
    let mut texts: Vec<(Vec3, String, Color, f32)> = Vec::new();
    let mut hp_bars: Vec<(Vec3, f32)> = Vec::new();
    // Doors.
    for e in &world.entities {
        if let EntityKind::Door { reward, .. } = e.kind {
            texts.push((w3(e.pos.to_vec2(), 4.3), door_label(db, reward), hex("#FFE3A3"), 15.0));
        }
    }
    // Allies: name tags above heads.
    for p in &world.players {
        if Some(p.slot) == link.slot {
            continue;
        }
        let pos = index.players[p.slot as usize].and_then(|e| rigs.get(e).ok()).map_or(p.mover.pos, |r| r.shown);
        texts.push((
            w3(pos, 2.6),
            format!("P{} {}", p.slot + 1, player_name(&link, p.slot)),
            crate::palette::hex(&db.game.player_colors[p.slot as usize % 4]),
            13.0,
        ));
        hp_bars.push((w3(pos, 2.35), p.hp / p.max_hp.max(1.0)));
    }
    // Elites and bosses: HP bars.
    for e in &world.entities {
        if let EntityKind::Enemy { .. } = e.kind
            && e.flags.intersects(EntityFlags::ELITE | EntityFlags::BOSS)
            && let Some(v) = index.entity(e.id).and_then(|ent| visuals.get(ent).ok())
        {
            hp_bars.push((w3(v.shown, v.lift + v.radius * 3.2 + 0.4), v.hp));
        }
    }
    let mut ti = texts.into_iter();
    for (_, mut node, mut t, mut color, mut font) in &mut labels {
        match ti.next().and_then(|(at, s, c, px)| world_to_screen(camera, cam_tf, at).map(|p| (p, s, c, px))) {
            Some((p, s, c, px)) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - s.chars().count() as f32 * px * 0.27);
                node.top = Val::Px(p.y - px);
                if t.0 != s {
                    t.0 = s;
                }
                color.0 = c;
                *font = font_px(px);
            }
            None => node.display = Display::None,
        }
    }
    let mut bi = hp_bars.into_iter();
    for (_, mut node, children) in &mut bars {
        match bi.next().and_then(|(at, f)| world_to_screen(camera, cam_tf, at).map(|p| (p, f))) {
            Some((p, f)) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - 23.0);
                node.top = Val::Px(p.y);
                if let Some(&child) = children.first()
                    && let Ok(mut fill) = fills.get_mut(child)
                {
                    fill.width = Val::Percent(f.clamp(0.0, 1.0) * 100.0);
                }
            }
            None => node.display = Display::None,
        }
    }
}

fn touch_overlay(
    input: Res<InputState>,
    mut buttons: Query<&mut Node, (With<TouchOverlay>, Without<TouchStick>)>,
    mut sticks: Query<(&TouchStick, &mut Node), Without<TouchOverlay>>,
) {
    let on = input.device == Device::Touch;
    for mut n in &mut buttons {
        let d = if on { Display::Flex } else { Display::None };
        if n.display != d {
            n.display = d;
        }
    }
    for (TouchStick(aim), mut n) in &mut sticks {
        let stick = if *aim { input.touch_aim } else { input.touch_move };
        match stick {
            Some((origin, _)) if on => {
                n.display = Display::Flex;
                n.left = Val::Px(origin.x - 60.0);
                n.top = Val::Px(origin.y - 60.0);
            }
            _ => n.display = Display::None,
        }
    }
}
