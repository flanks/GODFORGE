//! Interactive panels: the Forge (equip / fuse / reroll / salvage with a live DPS preview), god
//! boon offers, door choice (a touch-friendly alternative to walking into a door) and the
//! end-of-run screen. Every button carries a [`UiAction`]; one global `Activate` observer turns
//! clicks into the same reliable `PlayerAction`s the bots send.
//!
//! The preview runs `gf_core::forge::apply_action` on a copy of the build — the exact function the
//! host applies — so what the panel promises is what the anvil does.

use crate::input::InputState;
use crate::net::{Link, Prediction, start_link};
use crate::palette::{element_color, hex, rarity_color};
use crate::scene::{SceneIndex, door_label};
use crate::{ClientConfig, ClientSet, Connect, UiFonts};
use gf_content::{BoonKind, ContentDb};
use gf_core::forge::{ForgeAction, ForgeWallet, PartBag, PartCatalog, PartInstance, Slot, WeaponBuild, apply_action};
use gf_core::ids::PartId;
use gf_core::rarity::Rarity;
use gf_core::weapon::{DpsEnv, compile, estimate_dps};
use gf_engine::bevy::ui::InteractionDisabled;
use gf_engine::client::{Activate, Hovered, UiButton, button, is_hovered, text, text_in};
use gf_engine::prelude::*;
use gf_net::*;
use std::hash::{DefaultHasher, Hash, Hasher};

const INK: Color = Color::srgba(0.05, 0.035, 0.03, 0.92);
const EDGE: Color = Color::srgba(0.78, 0.6, 0.32, 0.7);
const PARCHMENT: Color = Color::srgb(0.96, 0.9, 0.78);
const DIM: Color = Color::srgb(0.66, 0.6, 0.52);
const BTN: Color = Color::srgb(0.2, 0.13, 0.08);
const BTN_HOVER: Color = Color::srgb(0.36, 0.24, 0.12);
const BTN_OFF: Color = Color::srgb(0.12, 0.1, 0.09);

/// What a button does.
#[derive(Component, Clone, Copy, Debug, PartialEq)]
pub enum UiAction {
    Player(PlayerAction),
    CloseForge,
    Restart,
    Quit,
}

#[derive(Component, Clone, Copy, PartialEq, Eq, Debug)]
enum Panel {
    Forge,
    Boons,
    Doors,
    End,
}

/// The forge panel's wallet + cooldown line, refreshed in place every frame.
#[derive(Component)]
struct ForgeTimer;

fn wallet_line(wallet: &ForgeWallet, time_left: f32) -> String {
    format!(
        "Godshards {} · Charges {} · Free {} · cools in {:.0}s",
        wallet.godshards, wallet.charges, wallet.free_actions, time_left
    )
}

fn update_forge_timer(link: Res<Link>, mut q: Query<&mut Text, With<ForgeTimer>>) {
    let Some(w) = link.latest.as_deref() else { return };
    let line = wallet_line(&w.private.wallet, w.run.anvil.map_or(0.0, |a| a.time_left));
    for mut t in &mut q {
        if t.0 != line {
            t.0 = line.clone();
        }
    }
}

#[derive(Resource, Default)]
struct PanelKeys {
    keys: [Option<u64>; 4],
}

#[derive(Resource, Default)]
struct UiRequests {
    restart: bool,
    quit: bool,
}

pub fn build(app: &mut App) {
    app.init_resource::<PanelKeys>()
        .init_resource::<UiRequests>()
        .add_observer(on_activate)
        .add_systems(Update, (toggle_forge, ui_capture).chain().in_set(ClientSet::Net))
        .add_systems(
            Update,
            (rebuild_panels, update_forge_timer, style_buttons, apply_requests).chain().in_set(ClientSet::Presentation),
        );
}

fn toggle_forge(keys: Res<ButtonInput<KeyCode>>, link: Res<Link>, mut input: ResMut<InputState>) {
    let at_anvil = link.latest.as_ref().is_some_and(|w| w.private.at_anvil);
    if keys.just_pressed(KeyCode::Tab) && at_anvil {
        input.forge_open = !input.forge_open;
    }
    if keys.just_pressed(KeyCode::Escape) || !at_anvil {
        input.forge_open = false;
    }
}

fn ui_capture(buttons: Query<&Hovered, With<UiButton>>, mut input: ResMut<InputState>) {
    input.ui_captures = buttons.iter().any(is_hovered);
}

fn on_activate(
    ev: On<Activate>,
    actions: Query<&UiAction>,
    mut input: ResMut<InputState>,
    mut req: ResMut<UiRequests>,
) {
    let Ok(action) = actions.get(ev.entity) else { return };
    match *action {
        UiAction::Player(a) => input.actions.push(a),
        UiAction::CloseForge => input.forge_open = false,
        UiAction::Restart => req.restart = true,
        UiAction::Quit => req.quit = true,
    }
}

fn style_buttons(
    mut q: Query<(&Hovered, &mut BackgroundColor, Has<InteractionDisabled>), (With<UiButton>, Changed<Hovered>)>,
) {
    for (h, mut bg, disabled) in &mut q {
        bg.0 = if disabled {
            BTN_OFF
        } else if is_hovered(h) {
            BTN_HOVER
        } else {
            BTN
        };
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
    mut keys: ResMut<PanelKeys>,
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
        *keys = PanelKeys::default();
    }
}

// ───────────────────────────── panel building ─────────────────────────────

fn key_of(parts: impl std::fmt::Debug) -> u64 {
    let mut h = DefaultHasher::new();
    format!("{parts:?}").hash(&mut h);
    h.finish()
}

fn node_button(p: &mut ChildSpawnerCommands, label: impl Into<String>, action: UiAction, enabled: bool) {
    let mut e = p.spawn((
        button(
            Node {
                padding: UiRect::axes(Val::Px(10.0), Val::Px(6.0)),
                min_height: Val::Px(40.0),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                border: UiRect::all(Val::Px(1.0)),
                border_radius: BorderRadius::all(Val::Px(5.0)),
                ..default()
            },
            if enabled { BTN } else { BTN_OFF },
            EDGE,
        ),
        action,
    ));
    if !enabled {
        e.insert(InteractionDisabled);
    }
    let label = label.into();
    e.with_children(|b| {
        b.spawn(text(label, 14.0, if enabled { PARCHMENT } else { DIM }));
    });
}

fn panel_root(commands: &mut Commands, which: Panel, node: Node) -> Entity {
    commands
        .spawn((
            which,
            Node {
                padding: UiRect::all(Val::Px(12.0)),
                border: UiRect::all(Val::Px(1.0)),
                border_radius: BorderRadius::all(Val::Px(8.0)),
                flex_direction: FlexDirection::Column,
                row_gap: Val::Px(6.0),
                ..node
            },
            BackgroundColor(INK),
            BorderColor::all(EDGE),
            GlobalZIndex(10),
        ))
        .id()
}

#[allow(clippy::too_many_arguments)]
fn rebuild_panels(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    input: Res<InputState>,
    fonts: Res<UiFonts>,
    mut keys: ResMut<PanelKeys>,
    panels: Query<(Entity, &Panel)>,
) {
    let display = &fonts.display;
    let db = &cfg.content;
    let world = link.latest.as_deref();
    let me = link.me();
    let wanted: [Option<u64>; 4] = [
        match (world, me) {
            (Some(w), Some(p)) if input.forge_open && w.private.at_anvil => {
                let t = w.run.anvil.map_or(0, |a| a.time_left as u32);
                Some(key_of((&w.private.bag, &w.private.wallet, &p.weapon, t)))
            }
            _ => None,
        },
        match world {
            Some(w) if !w.private.boon_offer.is_empty() => {
                Some(key_of((&w.private.boon_offer, w.private.boon_rerolls)))
            }
            _ => None,
        },
        match world {
            Some(w) if w.run.phase == RunPhase::Cleared => {
                let doors: Vec<_> =
                    w.entities.iter().filter(|e| matches!(e.kind, EntityKind::Door { .. })).map(|e| e.kind).collect();
                (!doors.is_empty()).then(|| key_of(doors))
            }
            _ => None,
        },
        match world {
            Some(w) if matches!(w.run.phase, RunPhase::Victory | RunPhase::Defeat) => {
                Some(key_of((w.run.phase, w.run.kills)))
            }
            _ => None,
        },
    ];
    for (i, which) in [Panel::Forge, Panel::Boons, Panel::Doors, Panel::End].into_iter().enumerate() {
        if keys.keys[i] == wanted[i] {
            continue;
        }
        keys.keys[i] = wanted[i];
        for (e, p) in &panels {
            if *p == which {
                commands.entity(e).despawn();
            }
        }
        if wanted[i].is_none() {
            continue;
        }
        let (Some(w), Some(p)) = (world, me) else { continue };
        match which {
            Panel::Forge => forge_panel(&mut commands, db, w, p, display),
            Panel::Boons => boon_panel(&mut commands, db, w, display),
            Panel::Doors => door_panel(&mut commands, db, w, display),
            Panel::End => end_panel(&mut commands, db, &link, w, display),
        }
    }
}

/// Content-backed catalog for forge previews (reroll is random, so it previews nothing).
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

fn build_dps(db: &ContentDb, build: &WeaponBuild) -> f32 {
    let chassis = db.chassis_def(build.chassis);
    let mut mods = chassis.mods.clone();
    for (_, part) in build.equipped() {
        mods.extend(db.part_mods(part.part, part.rarity));
    }
    let profile = compile(&chassis.stats, &mods);
    let env = DpsEnv { status: db.game.status.clone(), ..default() };
    estimate_dps(&profile, &env).single_target
}

/// Preview an anvil action on copies: Ok(new DPS) or the error the host would return.
fn preview(
    db: &ContentDb,
    action: ForgeAction,
    build: &WeaponBuild,
    bag: &PartBag,
    wallet: &ForgeWallet,
) -> Result<f32, String> {
    let (mut b, mut g, mut w) = (build.clone(), bag.clone(), *wallet);
    let mut uid = 0;
    apply_action(action, &mut b, &mut g, &mut w, &db.game.forge, &mut PreviewCatalog(db), &mut uid)
        .map_err(|e| e.to_string())?;
    Ok(build_dps(db, &b))
}

fn part_line(db: &ContentDb, part: PartInstance) -> (String, String, Color) {
    let def = db.parts.try_get(part.part.0);
    let name = def.map_or("?".to_string(), |d| d.name.clone());
    let slot = db.part_slot(part.part).map_or("?", |s| s.name());
    (
        format!("{name} · {} {slot}", part.rarity.name()),
        def.map_or(String::new(), |d| d.desc.clone()),
        rarity_color(part.rarity),
    )
}

fn delta(before: f32, after: f32) -> String {
    let pct = (after / before.max(1e-3) - 1.0) * 100.0;
    if pct.abs() < 0.5 { "±0%".into() } else { format!("{pct:+.0}%") }
}

fn forge_panel(commands: &mut Commands, db: &ContentDb, w: &WorldSnapshot, p: &PlayerView, display: &Handle<Font>) {
    let root = panel_root(
        commands,
        Panel::Forge,
        Node {
            position_type: PositionType::Absolute,
            right: Val::Px(14.0),
            top: Val::Px(120.0),
            width: Val::Px(470.0),
            max_height: Val::Percent(78.0),
            overflow: Overflow::clip_y(),
            ..default()
        },
    );
    let wallet = w.private.wallet;
    let bag = &w.private.bag;
    let rules = &db.game.forge;
    let now = build_dps(db, &p.weapon);
    let chassis = db.chassis.try_get(p.weapon.chassis.0).map_or("?", |c| c.name.as_str());
    let time_left = w.run.anvil.map_or(0.0, |a| a.time_left);
    let prof = gf_sim::bot::weapon_for(db, p);
    let recipes: Vec<String> = db
        .recipes
        .enumerate()
        .filter(|(id, _)| {
            db.recipe_ingredients
                .get(*id as usize)
                .is_some_and(|ings| gf_core::forge::recipe_satisfied(ings, &p.weapon, prof.element))
        })
        .map(|(_, r)| r.name.clone())
        .collect();
    commands.entity(root).with_children(|c| {
        c.spawn(Node {
            flex_direction: FlexDirection::Row,
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            ..default()
        })
        .with_children(|row| {
            row.spawn(text_in(format!("THE FORGE — {chassis}"), 21.0, hex("#FFC940"), display));
            node_button(row, "Close [Tab]", UiAction::CloseForge, true);
        });
        c.spawn((ForgeTimer, text(wallet_line(&wallet, time_left), 13.0, DIM)));
        c.spawn(text(
            format!("Estimated DPS {now:.0} · {}", gf_core::weapon::describe(&prof).join(" · ")),
            13.0,
            element_color(prof.element),
        ));
        if !recipes.is_empty() {
            c.spawn(text(format!("Named combo active: {}", recipes.join(", ")), 13.0, hex("#FFB82E")));
        }
        c.spawn(text("— Equipped —", 14.0, PARCHMENT));
        for slot in Slot::ALL {
            let locked = rules.locked_slots.contains(&slot);
            c.spawn(Node {
                flex_direction: FlexDirection::Row,
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::Center,
                column_gap: Val::Px(8.0),
                ..default()
            })
            .with_children(|row| match p.weapon.get(slot) {
                Some(part) => {
                    let (name, desc, color) = part_line(db, part);
                    row.spawn(Node { flex_direction: FlexDirection::Column, width: Val::Px(300.0), ..default() })
                        .with_children(|col| {
                            col.spawn(text(name, 14.0, color));
                            col.spawn(text(desc, 11.0, DIM));
                        });
                    if locked {
                        row.spawn(text("locked", 12.0, DIM));
                    } else {
                        let cost = if wallet.free_actions > 0 {
                            "free".to_string()
                        } else {
                            format!("{}◆", rules.reroll_cost)
                        };
                        let ok =
                            wallet.free_actions > 0 || (wallet.charges > 0 && wallet.godshards >= rules.reroll_cost);
                        node_button(
                            row,
                            format!("Reroll · {cost}"),
                            UiAction::Player(PlayerAction::Forge(ForgeAction::Reroll { slot })),
                            ok,
                        );
                    }
                }
                None => {
                    row.spawn(text(format!("{}: — empty —", slot.name()), 14.0, DIM));
                }
            });
        }
        c.spawn(text(format!("— Bag ({}/{}) —", bag.items.len(), bag.capacity), 14.0, PARCHMENT));
        if bag.items.is_empty() {
            c.spawn(text("Kill elites and open caches to find parts.", 12.0, DIM));
        }
        for part in &bag.items {
            let (name, desc, color) = part_line(db, *part);
            let uid = part.uid;
            let equip = preview(db, ForgeAction::Equip { uid }, &p.weapon, bag, &wallet);
            let fuse = preview(db, ForgeAction::Fuse { uid }, &p.weapon, bag, &wallet);
            let salvage = db.game.rarity.salvage_shards[part.rarity.index()];
            c.spawn(Node {
                flex_direction: FlexDirection::Column,
                row_gap: Val::Px(3.0),
                margin: UiRect::top(Val::Px(4.0)),
                ..default()
            })
            .with_children(|col| {
                col.spawn(text(name, 14.0, color));
                col.spawn(text(desc, 11.0, DIM));
                col.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(6.0), ..default() })
                    .with_children(|row| {
                        match &equip {
                            Ok(dps) => node_button(
                                row,
                                format!("Equip {}", delta(now, *dps)),
                                UiAction::Player(PlayerAction::Forge(ForgeAction::Equip { uid })),
                                true,
                            ),
                            Err(e) => node_button(
                                row,
                                format!("Equip ({e})"),
                                UiAction::Player(PlayerAction::Forge(ForgeAction::Equip { uid })),
                                false,
                            ),
                        }
                        match &fuse {
                            Ok(dps) => node_button(
                                row,
                                format!("Fuse {}", delta(now, *dps)),
                                UiAction::Player(PlayerAction::Forge(ForgeAction::Fuse { uid })),
                                true,
                            ),
                            Err(_) => node_button(
                                row,
                                "Fuse",
                                UiAction::Player(PlayerAction::Forge(ForgeAction::Fuse { uid })),
                                false,
                            ),
                        }
                        node_button(
                            row,
                            format!("Salvage +{salvage}◆"),
                            UiAction::Player(PlayerAction::Forge(ForgeAction::Salvage { uid })),
                            true,
                        );
                    });
            });
        }
    });
}

fn boon_panel(commands: &mut Commands, db: &ContentDb, w: &WorldSnapshot, display: &Handle<Font>) {
    let root = panel_root(
        commands,
        Panel::Boons,
        Node {
            position_type: PositionType::Absolute,
            left: Val::Percent(50.0),
            top: Val::Percent(24.0),
            margin: UiRect::left(Val::Px(-400.0)),
            width: Val::Px(800.0),
            align_items: AlignItems::Center,
            ..default()
        },
    );
    commands.entity(root).with_children(|c| {
        c.spawn(text_in("The gods answer — choose a boon", 22.0, hex("#FFC940"), display));
        c.spawn(Node { flex_direction: FlexDirection::Row, column_gap: Val::Px(12.0), ..default() }).with_children(
            |row| {
                for (i, offer) in w.private.boon_offer.iter().enumerate() {
                    let def = db.boons.try_get(offer.boon);
                    let gods: Vec<&gf_content::GodDef> =
                        def.map_or(Vec::new(), |d| d.gods.iter().filter_map(|g| db.gods.by_key(g)).collect());
                    let god_color = gods.first().map_or(hex("#FFC940"), |g| hex(&g.color));
                    let kind = def.map_or("", |d| match d.kind {
                        BoonKind::Standard => "",
                        BoonKind::Legendary => " · LEGENDARY",
                        BoonKind::Duo => " · DUO",
                        BoonKind::Team => " · TEAM",
                    });
                    let god_names = gods.iter().map(|g| g.name.as_str()).collect::<Vec<_>>().join(" & ");
                    row.spawn((
                        button(
                            Node {
                                width: Val::Px(240.0),
                                min_height: Val::Px(170.0),
                                padding: UiRect::all(Val::Px(10.0)),
                                flex_direction: FlexDirection::Column,
                                row_gap: Val::Px(6.0),
                                border: UiRect::all(Val::Px(2.0)),
                                border_radius: BorderRadius::all(Val::Px(8.0)),
                                ..default()
                            },
                            BTN,
                            god_color,
                        ),
                        UiAction::Player(PlayerAction::PickBoon(i as u8)),
                    ))
                    .with_children(|card| {
                        card.spawn(text(format!("{god_names}{kind}"), 12.0, god_color));
                        card.spawn(text_in(
                            def.map_or("?", |d| d.name.as_str()),
                            18.0,
                            rarity_color(offer.rarity),
                            display,
                        ));
                        card.spawn(text(offer.rarity.name(), 11.0, rarity_color(offer.rarity)));
                        card.spawn(text(def.map_or("", |d| d.desc.as_str()), 12.0, PARCHMENT));
                    });
                }
            },
        );
        if w.private.boon_rerolls > 0 {
            node_button(
                c,
                format!("Reroll offer ({} left)", w.private.boon_rerolls),
                UiAction::Player(PlayerAction::RerollBoons),
                true,
            );
        }
    });
}

fn door_panel(commands: &mut Commands, db: &ContentDb, w: &WorldSnapshot, display: &Handle<Font>) {
    let root = panel_root(
        commands,
        Panel::Doors,
        Node { position_type: PositionType::Absolute, left: Val::Px(14.0), bottom: Val::Px(120.0), ..default() },
    );
    let mut doors: Vec<(u8, DoorReward)> = w
        .entities
        .iter()
        .filter_map(|e| match e.kind {
            EntityKind::Door { reward, index } => Some((index, reward)),
            _ => None,
        })
        .collect();
    doors.sort_by_key(|(i, _)| *i);
    commands.entity(root).with_children(|c| {
        c.spawn(text_in("Choose the next chamber", 16.0, hex("#FFC940"), display));
        for (index, reward) in doors {
            node_button(c, door_label(db, reward), UiAction::Player(PlayerAction::ChooseDoor(index)), true);
        }
    });
}

fn end_panel(commands: &mut Commands, db: &ContentDb, link: &Link, w: &WorldSnapshot, display: &Handle<Font>) {
    let victory = w.run.phase == RunPhase::Victory;
    let root = panel_root(
        commands,
        Panel::End,
        Node {
            position_type: PositionType::Absolute,
            left: Val::Percent(50.0),
            top: Val::Percent(26.0),
            margin: UiRect::left(Val::Px(-260.0)),
            width: Val::Px(520.0),
            align_items: AlignItems::Center,
            ..default()
        },
    );
    let mins = (w.run.time / 60.0) as u32;
    let secs = w.run.time as u32 % 60;
    commands.entity(root).with_children(|c| {
        c.spawn(text_in(
            if victory { "VICTORY" } else { "DEFEAT" },
            44.0,
            if victory { hex("#FFC940") } else { hex("#FF6A5A") },
            display,
        ));
        c.spawn(text(
            format!(
                "Rooms cleared {} · Kills {} · Time {mins}:{secs:02} · Ember earned {}",
                w.run.depth, w.run.kills, w.run.ember
            ),
            15.0,
            PARCHMENT,
        ));
        for p in &w.players {
            let name =
                link.roster.iter().find(|r| r.slot == p.slot).map_or(format!("P{}", p.slot + 1), |r| r.name.clone());
            let ch = db.characters.try_get(p.character).map_or("?", |c| c.name.as_str());
            c.spawn(text(
                format!("P{} {name} ({ch}) — {} kills · {:.0} damage", p.slot + 1, p.kills, p.damage),
                13.0,
                DIM,
            ));
        }
        c.spawn(Node {
            flex_direction: FlexDirection::Row,
            column_gap: Val::Px(12.0),
            margin: UiRect::top(Val::Px(8.0)),
            ..default()
        })
        .with_children(|row| {
            node_button(row, "Forge again", UiAction::Restart, true);
            node_button(row, "Quit", UiAction::Quit, true);
        });
    });
}
