//! The Wayfinder (UI_STYLE §6.6), top-right: the minimap frame (hidden until OPEN_WORLD phase 3
//! fills it; see `uikit::MinimapFrame`) and the objective tracker under it. The tracker shows
//! state: time, Seals, the Warlord and the gate, threat, the surge, live events and the next
//! objectives; edge pins show direction. Legacy rooms get a short room tracker instead.

use super::{HudFocus, HudRect, Ui, View, db, drawer_open, roman, top::SurgeClock};
use crate::ClientConfig;
use crate::input::InputState;
use crate::net::{CurrentRoom, Link};
use crate::theme::{Ty, hx, region, tok, z};
use crate::uikit::{self, BarFill, BarSpec, MinimapFrame, UiKit, ik};
use gf_core::poi::{PoiKind, PoiState};
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::{EntityKind, GateView};

/// Right edge of the tracker (and of the minimap), from the canvas's right.
const RIGHT: f32 = 1920.0 - region::TRACKER_X1;
const WIDTH: f32 = 300.0;

struct EventRow {
    root: Entity,
    glyph: Entity,
    label: Entity,
    pct: Entity,
    pause: Entity,
    note: Entity,
    bar_box: Entity,
    bar: Entity,
}

struct NextRow {
    root: Entity,
    glyph: Entity,
    name: Entity,
    bearing: Entity,
    dist: Entity,
}

#[derive(Resource)]
pub(super) struct Wayfinder {
    /// The minimap's anchored root: shown (and so in `HudRects`) only while phase 3 shows the
    /// frame inside it.
    minimap_root: Entity,
    minimap: Entity,
    root: Entity,
    biome: Entity,
    timer: Entity,
    seals_row: Entity,
    sockets_box: Entity,
    sockets: Vec<(Entity, Entity)>,
    seals_n: u8,
    seals_text: Entity,
    last_seals: u8,
    wg_row: Entity,
    warlord: Entity,
    warlord_glyph: Entity,
    warlord_text: Entity,
    warlord_check: Entity,
    gate_glyph: Entity,
    gate_text: Entity,
    gate_ring: Entity,
    threat_row: Entity,
    threat_text: Entity,
    pips: Vec<Entity>,
    surge_row: Entity,
    surge_text: Entity,
    surge_secs: Entity,
    surge_bar: Entity,
    events: Vec<EventRow>,
    next: Vec<NextRow>,
    room_row: Entity,
    room_text: Entity,
    room_bar_box: Entity,
    room_bar: Entity,
}

fn text_row(p: &mut ChildSpawnerCommands, height: f32) -> Entity {
    p.spawn((
        Node {
            height: px(height),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::FlexEnd,
            column_gap: px(7.0),
            ..default()
        },
        Pickable::IGNORE,
    ))
    .id()
}

pub(super) fn spawn(mut commands: Commands, kit: Res<UiKit>) {
    let kit = &*kit;
    let ph = Entity::PLACEHOLDER;
    let mut w = Wayfinder {
        minimap_root: ph,
        minimap: ph,
        root: ph,
        biome: ph,
        timer: ph,
        seals_row: ph,
        sockets_box: ph,
        sockets: Vec::new(),
        seals_n: 0,
        seals_text: ph,
        last_seals: 0,
        wg_row: ph,
        warlord: ph,
        warlord_glyph: ph,
        warlord_text: ph,
        warlord_check: ph,
        gate_glyph: ph,
        gate_text: ph,
        gate_ring: ph,
        threat_row: ph,
        threat_text: ph,
        pips: Vec::new(),
        surge_row: ph,
        surge_text: ph,
        surge_secs: ph,
        surge_bar: ph,
        events: Vec::new(),
        next: Vec::new(),
        room_row: ph,
        room_text: ph,
        room_bar_box: ph,
        room_bar: ph,
    };
    // The phase-3 minimap hook: 280×176 at (1616, 24), hidden until phase 3 shows it.
    w.minimap_root = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                right: px(RIGHT - 3.0),
                top: px(region::MINIMAP[1] - 3.0),
                width: px(286.0),
                height: px(182.0),
                ..default()
            },
            GlobalZIndex(z::HUD),
            HudRect,
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            w.minimap = uikit::minimap_frame(c, kit, uikit::fill());
        })
        .id();

    w.root = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                right: px(RIGHT),
                top: px(region::TRACKER_Y0),
                width: px(WIDTH),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::FlexEnd,
                ..default()
            },
            GlobalZIndex(z::HUD),
            HudRect,
            Pickable::IGNORE,
        ))
        .with_children(|t| {
            // Header: BIOME · hourglass · 07:32, and the ember-knot rule.
            t.spawn((
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::FlexEnd,
                    height: px(46.0),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|h| {
                let r = text_row(h, 32.0);
                h.commands_mut().entity(r).with_children(|r| {
                    w.biome = r.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.16, "", tok::PARCH_DIM)).id();
                    r.commands_mut().entity(w.biome).insert(crate::theme::ink_shadow());
                    uikit::icon(r, "run/hourglass", 18.0, tok::GOLD_LT);
                    w.timer = r.spawn(kit.text_px(Ty::NumM, 24.0, "00:00", tok::NUMERAL)).id();
                });
                uikit::ember_knot(h, kit, 280.0, uikit::Gem::None, 0.85);
            });
            // Seals: one socket per required Seal, then 3/7.
            w.seals_row = text_row(t, 34.0);
            t.commands_mut().entity(w.seals_row).with_children(|r| {
                w.sockets_box = r.spawn((uikit::row(-2.0), Pickable::IGNORE)).id();
                w.seals_text = r.spawn(kit.text_px(Ty::NumS, 19.0, "0/0", tok::GOLD_LT)).id();
            });
            // Warlord · Gate.
            w.wg_row = text_row(t, 32.0);
            t.commands_mut().entity(w.wg_row).with_children(|r| {
                w.warlord =
                    r.spawn((Node { margin: UiRect::right(px(12.0)), ..uikit::row(6.0) }, Pickable::IGNORE)).id();
                r.commands_mut().entity(w.warlord).with_children(|x| {
                    w.warlord_glyph = x
                        .spawn((
                            Node { width: px(24.0), height: px(24.0), ..default() },
                            uikit::icon_bundle("poi/warlord", 24.0, tok::WARLORD_GLYPH),
                        ))
                        .id();
                    w.warlord_text = x.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "WARLORD", tok::PARCH)).id();
                    x.commands_mut().entity(w.warlord_text).insert(crate::theme::ink_shadow());
                    w.warlord_check = x
                        .spawn((
                            Node { width: px(16.0), height: px(16.0), display: Display::None, ..default() },
                            uikit::icon_bundle("ui/check", 16.0, tok::PARCH_MUTE),
                        ))
                        .id();
                });
                r.spawn((Node { width: px(26.0), height: px(26.0), ..default() }, Pickable::IGNORE)).with_children(
                    |g| {
                        w.gate_glyph = g
                            .spawn((
                                uikit::centered(22.0, 22.0),
                                uikit::icon_bundle("run/gate_sealed", 22.0, tok::BONE),
                            ))
                            .id();
                        w.gate_ring =
                            uikit::ring_meter(g, uikit::centered(28.0, 28.0), 2.0, uikit::RingStyle::Gold, 0.0);
                    },
                );
                w.gate_text = r.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "SEALED", tok::PARCH_MUTE)).id();
                r.commands_mut().entity(w.gate_text).insert(crate::theme::ink_shadow());
            });
            // Threat: THREAT III and five chevron pips.
            w.threat_row = text_row(t, 32.0);
            t.commands_mut().entity(w.threat_row).with_children(|r| {
                w.threat_text = r.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "THREAT I", tok::PARCH)).id();
                r.commands_mut().entity(w.threat_text).insert(crate::theme::ink_shadow());
                r.spawn((uikit::row(1.0), Pickable::IGNORE)).with_children(|p| {
                    for _ in 0..5 {
                        w.pips.push(
                            p.spawn((
                                Node { width: px(15.0), height: px(11.0), ..default() },
                                kit.tex("markers/threat_pip_dark@2x.png"),
                                Pickable::IGNORE,
                            ))
                            .id(),
                        );
                    }
                });
            });
            // Surge (only during a warning or a surge).
            w.surge_row = t
                .spawn((
                    Node {
                        display: Display::None,
                        height: px(38.0),
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::FlexEnd,
                        justify_content: JustifyContent::Center,
                        row_gap: px(4.0),
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|s| {
                    let r = text_row(s, 20.0);
                    s.commands_mut().entity(r).with_children(|r| {
                        w.surge_text = r.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "SURGE", hx(0xFFD2C0))).id();
                        r.commands_mut().entity(w.surge_text).insert(crate::theme::ink_shadow());
                        w.surge_secs = r.spawn(kit.text_px(Ty::Num, 16.0, "", hx(0xFFD2C0))).id();
                    });
                    w.surge_bar = uikit::bar(
                        s,
                        kit,
                        BarSpec { edge: false, ..BarSpec::new(262.0, 6.0, BarFill::Surge).no_rim() },
                    );
                })
                .id();
            // Live events (0–2).
            for _ in 0..2 {
                let mut e =
                    EventRow { root: ph, glyph: ph, label: ph, pct: ph, pause: ph, note: ph, bar_box: ph, bar: ph };
                e.root = t
                    .spawn((
                        Node {
                            display: Display::None,
                            height: px(40.0),
                            flex_direction: FlexDirection::Column,
                            align_items: AlignItems::FlexEnd,
                            justify_content: JustifyContent::Center,
                            row_gap: px(4.0),
                            ..default()
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|s| {
                        let r = text_row(s, 22.0);
                        s.commands_mut().entity(r).with_children(|r| {
                            e.pause = r
                                .spawn((
                                    Node { width: px(16.0), height: px(16.0), display: Display::None, ..default() },
                                    uikit::icon_bundle("ui/pause", 16.0, tok::PARCH_MUTE),
                                ))
                                .id();
                            e.glyph = r
                                .spawn((
                                    Node { width: px(22.0), height: px(22.0), ..default() },
                                    uikit::icon_bundle("poi/anvil", 22.0, tok::BONE),
                                ))
                                .id();
                            e.label = r.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "", tok::PARCH)).id();
                            r.commands_mut().entity(e.label).insert(crate::theme::ink_shadow());
                            e.note = r
                                .spawn((
                                    Node { display: Display::None, ..default() },
                                    kit.text_px(Ty::Flavour, 15.0, "(step inside)", tok::PARCH_DIM),
                                ))
                                .id();
                            e.pct = r.spawn(kit.text_px(Ty::Num, 16.0, "", tok::ICHOR)).id();
                        });
                        e.bar_box = s
                            .spawn((
                                Node { width: px(262.0), height: px(6.0), ..default() },
                                super::FadeGroup::new(1.0),
                                Pickable::IGNORE,
                            ))
                            .id();
                        s.commands_mut().entity(e.bar_box).with_children(|b| {
                            e.bar = uikit::bar(
                                b,
                                kit,
                                BarSpec {
                                    edge: true,
                                    ghost: false,
                                    ..BarSpec::new(262.0, 6.0, BarFill::Molten).no_rim()
                                },
                            );
                        });
                    })
                    .id();
                w.events.push(e);
            }
            // Next objectives (1–2).
            for _ in 0..2 {
                let mut n = NextRow { root: ph, glyph: ph, name: ph, bearing: ph, dist: ph };
                n.root = text_row(t, 28.0);
                t.commands_mut().entity(n.root).insert(Node {
                    display: Display::None,
                    height: px(28.0),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::FlexEnd,
                    column_gap: px(7.0),
                    ..default()
                });
                t.commands_mut().entity(n.root).with_children(|r| {
                    n.glyph = r
                        .spawn((
                            Node { width: px(22.0), height: px(22.0), ..default() },
                            uikit::icon_bundle("poi/shrine", 22.0, tok::BONE),
                        ))
                        .id();
                    n.name = r.spawn(kit.text_px(Ty::Body, 17.0, "", tok::PARCH_DIM)).id();
                    n.bearing = r
                        .spawn((
                            Node { width: px(16.0), height: px(16.0), margin: UiRect::left(px(4.0)), ..default() },
                            uikit::icon_bundle("ui/bearing", 16.0, tok::GOLD_LT),
                            UiTransform::default(),
                        ))
                        .id();
                    n.dist = r.spawn(kit.text_px(Ty::Num, 16.0, "", tok::PARCH)).id();
                });
                w.next.push(n);
            }
            // Legacy rooms: ROOM 3 / 8 · Elite, and the encounter bar.
            w.room_row = t
                .spawn((
                    Node {
                        display: Display::None,
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::FlexEnd,
                        row_gap: px(6.0),
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|s| {
                    w.room_text = s.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.14, "", tok::PARCH)).id();
                    s.commands_mut().entity(w.room_text).insert(crate::theme::ink_shadow());
                    w.room_bar_box =
                        s.spawn((Node { width: px(262.0), height: px(6.0), ..default() }, Pickable::IGNORE)).id();
                    s.commands_mut().entity(w.room_bar_box).with_children(|b| {
                        w.room_bar = uikit::bar(
                            b,
                            kit,
                            BarSpec { ghost: false, ..BarSpec::new(262.0, 6.0, BarFill::Molten).no_rim() },
                        );
                    });
                })
                .id();
        })
        .id();
    commands.insert_resource(w);
}

/// The words of a live POI event.
fn event_words(kind: PoiKind, state: PoiState) -> &'static str {
    match (kind, state) {
        (PoiKind::Anvil, PoiState::Hot) => "HOT",
        (PoiKind::Anvil, _) => "KINDLING",
        (PoiKind::Shrine, _) => "PRAYER",
        (PoiKind::Reliquary, _) => "OPENING",
        (PoiKind::Vein, _) => "TAPPING",
        (PoiKind::Watchfire, _) => "KINDLING",
        (PoiKind::Lair, _) => "IN BATTLE",
        _ => "ACTIVE",
    }
}

/// A POI glyph's tint: bone, or the god colour for a shrine (the secondary for red gods, §3.4).
pub(crate) fn poi_tint(db: &gf_content::ContentDb, site: &gf_content::PoiSite) -> Color {
    match (site.kind, site.god.and_then(|g| db.gods.try_get(g as u16))) {
        (PoiKind::Shrine, Some(g)) => {
            let hex = if matches!(g.key.as_str(), "pyra" | "umbra_rex") { &g.color_secondary } else { &g.color };
            crate::palette::hex(hex)
        }
        (PoiKind::Warlord, _) => tok::WARLORD_GLYPH,
        _ => tok::BONE,
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn update(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    input: Res<InputState>,
    focus: Res<HudFocus>,
    surge: Res<SurgeClock>,
    kit: Res<UiKit>,
    view: View,
    minimaps: Query<&MinimapFrame>,
    mut w: ResMut<Wayfinder>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let now = time.elapsed_secs();
    let Some(world) = link.latest.as_deref() else { return };
    let me = link.me().map(|p| p.mover.pos);

    // Dock under the minimap once phase 3 shows it, else at the top.
    let minimap_on = minimaps.get(w.minimap).is_ok() && ui.shown(w.minimap);
    ui.show(w.minimap_root, minimap_on);
    if let Ok(mut n) = ui.nodes.get_mut(w.root) {
        let top = px(if minimap_on { region::TRACKER_Y0 } else { region::MINIMAP[1] });
        if n.top != top {
            n.top = top;
        }
    }
    ui.show(w.root, !drawer_open(&focus, &input) && !focus.boon_spread);

    let biome = db.biomes.try_get(world.run.biome).map_or("", |b| b.name.as_str());
    ui.text(w.biome, biome.to_uppercase());
    let st = world.run.stage;
    let t = st.map_or(world.run.time, |s| s.time) as u32;
    ui.text(w.timer, format!("{:02}:{:02}", t / 60, t % 60));

    let map = room.def.map.as_deref();
    let on_map = st.is_some() && map.is_some();
    for e in [w.seals_row, w.wg_row, w.threat_row] {
        ui.show(e, on_map);
    }
    ui.show(w.room_row, !on_map);
    let (Some(st), Some(map)) = (st, map) else {
        // Legacy room tracker.
        let kind = match room.def.kind {
            gf_content::RoomKind::Combat => "",
            gf_content::RoomKind::Elite => " · ELITE",
            gf_content::RoomKind::Anvil => " · ANVIL",
            gf_content::RoomKind::MiniBoss => " · MINI-BOSS",
            gf_content::RoomKind::Boss => " · BOSS",
            gf_content::RoomKind::Treasure => " · TREASURE",
            gf_content::RoomKind::Expedition => "",
        };
        let chaos = if world.run.chaos_tier > 0 {
            format!(" · CHAOS {}", roman(world.run.chaos_tier as u32))
        } else {
            String::new()
        };
        ui.text(w.room_text, format!("ROOM {} / {}{kind}{chaos}", world.run.step as u32 + 1, world.run.steps));
        ui.bar(w.room_bar, 1.0 - world.run.encounter_left.clamp(0.0, 1.0), 0.0);
        for e in &w.events {
            ui.show(e.root, false);
        }
        for n in &w.next {
            ui.show(n.root, false);
        }
        ui.show(w.surge_row, false);
        return;
    };

    // Seals: rebuild the sockets when the requirement changes; flash the row on reaching it.
    if w.seals_n != st.required {
        w.seals_n = st.required;
        let bx = w.sockets_box;
        commands.entity(bx).despawn_children();
        let mut sockets = Vec::new();
        commands.entity(bx).with_children(|b| {
            for _ in 0..st.required {
                let mut pair = (Entity::PLACEHOLDER, Entity::PLACEHOLDER);
                b.spawn((Node { width: px(26.0), height: px(26.0), ..default() }, Pickable::IGNORE)).with_children(
                    |s| {
                        pair.1 = s
                            .spawn((
                                Node {
                                    border: UiRect::all(px(1.2)),
                                    border_radius: BorderRadius::MAX,
                                    ..uikit::centered(17.0, 17.0)
                                },
                                BackgroundColor(tok::LAC0.with_alpha(0.85)),
                                BorderColor::all(tok::GOLD_DK),
                                Pickable::IGNORE,
                            ))
                            .id();
                        pair.0 = s
                            .spawn((
                                Node { display: Display::None, ..uikit::fill() },
                                uikit::icon_bundle("currency/seal", 26.0, Color::WHITE),
                            ))
                            .id();
                    },
                );
                sockets.push(pair);
            }
        });
        w.sockets = sockets;
    }
    for (i, (full, empty)) in w.sockets.iter().enumerate() {
        let claimed = (i as u8) < st.seals;
        ui.show(*full, claimed);
        ui.show(*empty, !claimed);
    }
    ui.text(w.seals_text, format!("{}/{}", st.seals, st.required));
    if st.seals != w.last_seals {
        if st.seals >= st.required && w.last_seals < st.required {
            commands.entity(w.seals_row).insert((UiTransform::default(), uikit::pop(0.12, 0.3)));
        }
        w.last_seals = st.seals;
    }

    // Warlord · Gate.
    let warlord_poi = world.entities.iter().find_map(|e| match e.kind {
        EntityKind::Poi { index } => {
            map.pois.get(index as usize).filter(|s| s.kind == PoiKind::Warlord).map(|_| PoiState::from_u8(e.status))
        }
        _ => None,
    });
    let has_warlord = warlord_poi.is_some() || map.pois.iter().any(|s| s.kind == PoiKind::Warlord);
    ui.show(w.warlord, has_warlord);
    let (wtext, wcol) = if st.warlord {
        ("SLAIN", tok::PARCH_MUTE)
    } else if warlord_poi == Some(PoiState::Active) || world.private.boss.is_some() {
        ("IN BATTLE", tok::ENEMY_PHASE.with_alpha(0.7 + 0.3 * (now * 5.0).sin().abs()))
    } else {
        ("WARLORD", tok::PARCH)
    };
    ui.text(w.warlord_text, wtext);
    ui.color(w.warlord_text, wcol);
    ui.show(w.warlord_check, st.warlord);
    ui.tint(w.warlord_glyph, if st.warlord { tok::PARCH_MUTE } else { tok::WARLORD_GLYPH });
    let solo = world.players.len() <= 1;
    let gate_tune = &db.game.expedition.gate;
    let gather = if solo { gate_tune.gather_solo } else { gate_tune.gather };
    let (gkey, gtext, gcol, ring) = match st.gate {
        GateView::Sealed => ("run/gate_sealed", "SEALED".to_string(), tok::PARCH_MUTE, None),
        GateView::Open => ("run/gate_open", "GATE OPEN".to_string(), tok::GOLD_LT, None),
        GateView::Gathering { left_ds } => {
            let left = left_ds as f32 / 10.0;
            ("run/gathering", format!("GATHER {:.0}", left.ceil()), tok::ICHOR, Some(left / gather.max(0.1)))
        }
    };
    ui.icon(w.gate_glyph, gkey);
    ui.tint(w.gate_glyph, if st.gate == GateView::Sealed { tok::PARCH_MUTE } else { tok::GOLD_LT });
    ui.text(w.gate_text, gtext);
    ui.color(w.gate_text, gcol);
    ui.show(w.gate_ring, ring.is_some());
    ui.ring(w.gate_ring, ring.unwrap_or(0.0), false);

    // Threat.
    let level = st.threat_level() as u32 + 1;
    ui.text(w.threat_text, format!("THREAT {}", roman(level)));
    for (i, p) in w.pips.iter().enumerate() {
        let lit = (i as u32) < level.min(5);
        let path = if lit { "markers/threat_pip_lit@2x.png" } else { "markers/threat_pip_dark@2x.png" };
        if let Ok(mut img) = ui.images.get_mut(*p) {
            let want = kit.tex(path).image;
            if img.image != want {
                img.image = want;
            }
        }
    }

    // Surge: SURGE · EAST, seconds, and the countdown bar.
    let surge_on = st.surge.is_some() && surge.started.is_some();
    ui.show(w.surge_row, surge_on);
    if surge_on && let Some(started) = surge.started {
        let tune = &db.game.expedition.horde.surge;
        let (total, word) = if surge.warn { (tune.warn, "SURGE INCOMING") } else { (tune.duration, "SURGE") };
        let left = (total - (now - started)).max(0.0);
        ui.text(w.surge_text, format!("{word} · {}", surge.side_name.to_uppercase()));
        ui.text(w.surge_secs, format!("{:.0} s", left.ceil()));
        ui.bar(w.surge_bar, left / total.max(0.1), 0.0);
    }

    // Live events and the next objectives.
    let mut live: Vec<(f32, PoiKind, PoiState, f32, bool, Color)> = Vec::new();
    let mut todo: Vec<(f32, &gf_content::PoiSite)> = Vec::new();
    for e in &world.entities {
        let EntityKind::Poi { index } = e.kind else { continue };
        let Some(site) = map.pois.get(index as usize) else { continue };
        let state = PoiState::from_u8(e.status);
        let d = me.map_or(0.0, |m| m.distance(site.at));
        let hold = matches!(
            site.kind,
            PoiKind::Anvil | PoiKind::Shrine | PoiKind::Reliquary | PoiKind::Vein | PoiKind::Watchfire | PoiKind::Lair
        );
        if hold && (state == PoiState::Active || (site.kind == PoiKind::Anvil && state == PoiState::Hot)) {
            let frac = gf_net::quant::u8_to_frac(e.hp);
            let contested = e.flags.contains(gf_net::EntityFlags::CONTESTED);
            live.push((d, site.kind, state, frac, contested, poi_tint(db, site)));
        } else if site.seals > 0 && state != PoiState::Done && site.kind != PoiKind::Warlord {
            todo.push((d, site));
        }
    }
    live.sort_by(|a, b| a.0.total_cmp(&b.0));
    todo.sort_by(|a, b| a.0.total_cmp(&b.0));
    // The floor at y 486: drop next 2, then event 2, then next 1 when rows would cross it.
    let y0 = if minimap_on { region::TRACKER_Y0 } else { region::MINIMAP[1] };
    let budget = region::TRACKER_FLOOR - y0 - 46.0 - 34.0 - 32.0 - 32.0 - if surge_on { 38.0 } else { 0.0 };
    let n_live = live.len().min(2);
    let n_next = todo.len().min(2);
    let mut show_live = [n_live > 0, n_live > 1];
    let mut show_next = [n_next > 0, n_next > 1];
    let need = |l: &[bool; 2], n: &[bool; 2]| {
        l.iter().filter(|b| **b).count() as f32 * 40.0 + n.iter().filter(|b| **b).count() as f32 * 28.0
    };
    for drop in 0..3 {
        if need(&show_live, &show_next) <= budget {
            break;
        }
        match drop {
            0 => show_next[1] = false,
            1 => show_live[1] = false,
            _ => show_next[0] = false,
        }
    }
    for (i, row) in w.events.iter().enumerate() {
        let Some(&(_, kind, state, frac, contested, tint)) = live.get(i).filter(|_| show_live[i]) else {
            ui.show(row.root, false);
            continue;
        };
        ui.show(row.root, true);
        ui.icon(row.glyph, &ik::poi(kind));
        ui.tint(row.glyph, tint);
        ui.text(row.label, format!("{} · {}", kind.name().to_uppercase(), event_words(kind, state)));
        let hot = state == PoiState::Hot;
        let pct = if hot {
            world
                .private
                .anvil
                .filter(|a| a.state == gf_net::AnvilState::Hot)
                .map_or(String::new(), |a| format!("{:.0} s", a.time_left.ceil()))
        } else {
            format!("{:.0}%", frac * 100.0)
        };
        ui.text(row.pct, pct);
        ui.show(row.pause, contested && !hot);
        ui.show(row.note, contested && !hot);
        ui.bar(row.bar, if hot { 1.0 } else { frac }, 0.0);
        // Contested: the bar at half strength.
        ui.fade(row.bar_box, if contested && !hot { 0.5 } else { 1.0 });
    }
    for (i, row) in w.next.iter().enumerate() {
        let Some(&(d, site)) = todo.get(i).filter(|_| show_next[i]) else {
            ui.show(row.root, false);
            continue;
        };
        ui.show(row.root, true);
        ui.icon(row.glyph, &ik::poi(site.kind));
        ui.tint(row.glyph, poi_tint(db, site));
        ui.text(row.name, crate::scene::poi_label(db, site));
        ui.text(row.dist, format!("{d:.0} m"));
        // The bearing chevron points along the screen direction to the objective.
        if let (Some(a), Some(b)) =
            (me.and_then(|m| view.project(crate::camera::w3(m, 0.0))), view.project(crate::camera::w3(site.at, 0.0)))
        {
            let v = b - a;
            if v.length_squared() > 1.0 {
                ui.rotate(row.bearing, v.x.atan2(-v.y));
            }
        }
    }
}
