//! Party frames (UI_STYLE §6.4) and the toast rail (§6.5), top-left.

use super::{FadeGroup, HudRect, Ui, anchored, db, player_name};
use crate::ClientConfig;
use crate::input::{InputState, Settings};
use crate::net::{CurrentRoom, Link};
use crate::palette::rarity_color;
use crate::theme::{Ty, hx, player_color, region, tok, z};
use crate::uikit::{self, BarFill, BarParts, BarSpec, MedallionSpec, UiKit, ik};
use gf_core::forge::ForgeOutcome;
use gf_core::poi::{PoiKind, PoiState};
use gf_core::rarity::Rarity;
use gf_core::revive::LifeState;
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::{EntityKind, GameEvent, GateView, PlayerView};

const ROW_H: f32 = 54.0;

struct Row {
    slot: u8,
    medallion: Entity,
    downed: Entity,
    reforge: Entity,
    name: Entity,
    tag: Entity,
    state: Entity,
    bar: Entity,
    count_box: Entity,
    count_bar: Entity,
    secs: Entity,
    ult: Entity,
    forging: Entity,
    gate: Entity,
}

#[derive(Resource)]
pub(super) struct Party {
    root: Entity,
    rows_box: Entity,
    rows: Vec<Row>,
    key: Vec<(u8, u16, String)>,
    toasts_root: Entity,
    slots: Vec<Entity>,
    list: Vec<Toast>,
    shift: f32,
    last_bias: Option<gf_core::aim::TargetBias>,
    last_offer: Vec<gf_net::BoonOffer>,
}

#[derive(Clone, Debug)]
struct Toast {
    key: String,
    icon: String,
    spans: Vec<(Ty, String, Color)>,
    count: u32,
    age: f32,
    bump: bool,
}

pub(super) fn spawn(mut commands: Commands) {
    let mut p = Party {
        root: Entity::PLACEHOLDER,
        rows_box: Entity::PLACEHOLDER,
        rows: Vec::new(),
        key: Vec::new(),
        toasts_root: Entity::PLACEHOLDER,
        slots: Vec::new(),
        list: Vec::new(),
        shift: 1.0,
        last_bias: None,
        last_offer: Vec::new(),
    };
    p.root = commands
        .spawn((
            Node { display: Display::None, ..anchored(uikit::Corner::TopLeft, region::PARTY) },
            GlobalZIndex(z::HUD),
            HudRect,
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            p.rows_box = c.spawn((uikit::fill(), Pickable::IGNORE)).id();
        })
        .id();
    p.toasts_root = commands
        .spawn((anchored(uikit::Corner::TopLeft, region::TOASTS), GlobalZIndex(z::TRANSIENT), Pickable::IGNORE))
        .with_children(|c| {
            for i in 0..3 {
                p.slots.push(
                    c.spawn((
                        Node { display: Display::None, ..uikit::abs(0.0, 32.0 * i as f32, 440.0, 30.0) },
                        FadeGroup::new(1.0),
                        UiTransform::default(),
                        Pickable::IGNORE,
                    ))
                    .id(),
                );
            }
        })
        .id();
    commands.insert_resource(p);
}

fn build_row(
    c: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &gf_content::ContentDb,
    name: &str,
    v: &PlayerView,
    i: usize,
) -> Row {
    let color = player_color(db, v.slot as usize);
    let ch = db.characters.try_get(v.character);
    let ch_key = ch.map_or("valdris".to_string(), |c| c.key.clone());
    let ch_name = ch.map_or(String::new(), |c| c.name.to_uppercase());
    let mut r = Row {
        slot: v.slot,
        medallion: Entity::PLACEHOLDER,
        downed: Entity::PLACEHOLDER,
        reforge: Entity::PLACEHOLDER,
        name: Entity::PLACEHOLDER,
        tag: Entity::PLACEHOLDER,
        state: Entity::PLACEHOLDER,
        bar: Entity::PLACEHOLDER,
        count_box: Entity::PLACEHOLDER,
        count_bar: Entity::PLACEHOLDER,
        secs: Entity::PLACEHOLDER,
        ult: Entity::PLACEHOLDER,
        forging: Entity::PLACEHOLDER,
        gate: Entity::PLACEHOLDER,
    };
    c.spawn((uikit::abs(0.0, ROW_H * i as f32, 258.0, ROW_H), Pickable::IGNORE)).with_children(|row| {
        // The medallion (and its downed twin: a danger band and the skull), the P chip under it.
        row.spawn((uikit::abs(0.0, 0.0, 46.0, 46.0), Pickable::IGNORE)).with_children(|m| {
            r.medallion = m
                .spawn((uikit::fill(), Pickable::IGNORE))
                .with_children(|x| {
                    uikit::medallion(x, kit, MedallionSpec::new(46.0).portrait(&ik::portrait(&ch_key)).band(color));
                })
                .id();
            r.downed = m
                .spawn((Node { display: Display::None, ..uikit::fill() }, Pickable::IGNORE))
                .with_children(|x| {
                    uikit::medallion(
                        x,
                        kit,
                        MedallionSpec::new(46.0).band(tok::DANGER).glyph("states/downed", 0.56, tok::DANGER_WHITE),
                    );
                    x.spawn((
                        Node { border: UiRect::all(px(1.5)), border_radius: BorderRadius::MAX, ..uikit::inset(-1.0) },
                        BorderColor::all(tok::DANGER),
                        uikit::glow(tok::DANGER.with_alpha(0.55), 8.0, 0.0),
                        Pickable::IGNORE,
                    ));
                })
                .id();
            r.reforge = m
                .spawn((
                    Node { display: Display::None, border_radius: BorderRadius::MAX, ..uikit::inset(4.0) },
                    BackgroundColor(Color::BLACK.with_alpha(0.5)),
                    Pickable::IGNORE,
                ))
                .with_children(|x| {
                    x.spawn((uikit::centered(24.0, 24.0), uikit::icon_bundle("states/reforging", 24.0, tok::GOLD_LT)));
                })
                .id();
        });
        row.spawn((uikit::abs(8.0, 37.0, 30.0, 18.0), Pickable::IGNORE)).with_children(|pc| {
            uikit::pchip(pc, kit, v.slot as usize, color);
        });
        // Name · CHARACTER (· DOWNED) on one line.
        row.spawn((
            Node {
                position_type: PositionType::Absolute,
                left: px(57.0),
                top: px(1.0),
                align_items: AlignItems::Baseline,
                column_gap: px(9.0),
                ..default()
            },
            Pickable::IGNORE,
        ))
        .with_children(|t| {
            r.name = t.spawn(kit.text_px(Ty::Strong, 18.0, name, tok::PARCH)).id();
            r.tag = t.spawn(kit.text_px(Ty::Micro, 12.0, ch_name.clone(), tok::PARCH_DIM)).id();
            r.state = t
                .spawn((
                    Node { display: Display::None, ..default() },
                    kit.text_tracked(Ty::LabelS, 13.0, 0.14, "DOWNED", tok::DANGER),
                ))
                .id();
        });
        // HP (with ward), and the countdown bar that replaces it while down or reforging.
        row.spawn((uikit::abs(57.0, 28.0, 170.0, 8.0), Pickable::IGNORE)).with_children(|b| {
            r.bar = uikit::bar(b, kit, BarSpec::new(170.0, 8.0, BarFill::Hp).ward());
        });
        r.count_box = row
            .spawn((Node { display: Display::None, ..uikit::abs(57.0, 28.0, 170.0, 8.0) }, Pickable::IGNORE))
            .with_children(|b| {
                r.count_bar = uikit::bar(b, kit, BarSpec::new(170.0, 8.0, BarFill::Tint(Color::WHITE)));
            })
            .id();
        r.secs = row
            .spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(233.0),
                    top: px(21.0),
                    display: Display::None,
                    ..default()
                },
                kit.text_px(Ty::Num, 15.0, "", tok::DANGER_WHITE),
            ))
            .id();
        // Status glyphs at x 265: ult ready, forging, at the gate.
        row.spawn((
            Node {
                position_type: PositionType::Absolute,
                left: px(233.0),
                top: px(4.0),
                column_gap: px(3.0),
                ..default()
            },
            Pickable::IGNORE,
        ))
        .with_children(|g| {
            let glyph = |g: &mut ChildSpawnerCommands, key: &str, tint: Color| {
                g.spawn((
                    Node { width: px(16.0), height: px(16.0), display: Display::None, ..default() },
                    uikit::icon_bundle(key, 16.0, tint),
                ))
                .id()
            };
            r.ult = glyph(g, "team/ult_ready", tok::ICHOR);
            r.forging = glyph(g, "currency/forge_charge", Color::WHITE);
            r.gate = glyph(g, "run/gathering", tok::GOLD_LT);
        });
    });
    r
}

#[allow(clippy::too_many_arguments)]
pub(super) fn update(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    settings: Res<Settings>,
    kit: Res<UiKit>,
    mut party: ResMut<Party>,
    mut ui: Ui,
    bar_parts: Query<&BarParts>,
) {
    let db = db(&cfg);
    let Some(world) = link.latest.as_deref() else { return };
    let others: Vec<&PlayerView> = world.players.iter().filter(|p| Some(p.slot) != link.slot).take(3).collect();
    ui.show(party.root, !others.is_empty());
    // The debug strip pushes the party down 18 px.
    if let Ok(mut n) = ui.nodes.get_mut(party.root) {
        let top = px(region::PARTY[1] + if settings.debug_strip { 18.0 } else { 0.0 });
        if n.top != top {
            n.top = top;
        }
    }
    let key: Vec<(u8, u16, String)> =
        others.iter().map(|p| (p.slot, p.character, player_name(&link, p.slot))).collect();
    if key != party.key {
        party.key = key;
        let rows_box = party.rows_box;
        commands.entity(rows_box).despawn_children();
        let mut rows = Vec::new();
        commands.entity(rows_box).with_children(|c| {
            for (i, p) in others.iter().enumerate() {
                rows.push(build_row(c, &kit, db, &player_name(&link, p.slot), p, i));
            }
        });
        party.rows = rows;
        return;
    }
    let revive = &db.game.revive;
    let gate =
        room.def.map.as_deref().and_then(|m| m.pois.iter().find(|s| s.kind == PoiKind::Gate).map(|s| (s.at, s.radius)));
    let gathering = world.run.stage.is_some_and(|s| matches!(s.gate, GateView::Gathering { .. }))
        || world
            .entities
            .iter()
            .any(|e| matches!(e.kind, EntityKind::Poi { .. }) && PoiState::from_u8(e.status) == PoiState::Gathering);
    for row in &party.rows {
        let Some(p) = world.players.iter().find(|p| p.slot == row.slot) else { continue };
        let max = p.max_hp.max(1.0);
        ui.bar(row.bar, p.hp.max(0.0) / max, p.shield / max);
        let (downed, reforging, frac, secs) = match p.life {
            LifeState::Alive => (false, false, 0.0, 0.0),
            LifeState::Downed { remaining, .. } => {
                (true, false, remaining / revive.downed_duration.max(0.1), remaining)
            }
            LifeState::Reforging { remaining } => (false, true, remaining / revive.reforge_delay.max(0.1), remaining),
        };
        ui.show(row.medallion, !downed);
        ui.show(row.downed, downed);
        ui.show(row.reforge, reforging);
        ui.show(row.state, downed);
        ui.show(row.tag, !downed);
        let counting = downed || reforging;
        ui.show(row.count_box, counting);
        ui.show(row.secs, counting);
        if counting {
            // The countdown bar: white while down (danger), gold while reforging.
            ui.bar(row.count_bar, frac, 0.0);
            if let Ok(parts) = bar_parts.get(row.count_bar) {
                ui.tint(parts.fill, if downed { hx(0xFFB0A8) } else { tok::GOLD_LT });
            }
            ui.text(row.secs, format!("{:.0}s", secs.ceil()));
            ui.color(row.secs, if downed { tok::DANGER_WHITE } else { tok::GOLD_LT });
        }
        ui.show(row.ult, p.life.is_alive() && p.ult >= 1.0);
        ui.show(row.forging, p.forge_open);
        let at_gate = gathering && gate.is_some_and(|(at, r)| p.mover.pos.distance(at) <= r + 1.0);
        ui.show(row.gate, at_gate);
    }
}

// ───────────────────────────── toasts ─────────────────────────────

const HOLD: f32 = 3.0;
const IN: f32 = 0.18;
const OUT: f32 = 0.4;

/// In over 180 ms, hold 3 s, out over 400 ms.
fn toast_alpha(age: f32) -> f32 {
    (age / IN).min(1.0) * (1.0 - ((age - IN - HOLD) / OUT).clamp(0.0, 1.0))
}

fn who(link: &Link, slot: u8) -> String {
    if Some(slot) == link.slot { "You".to_string() } else { player_name(link, slot) }
}

/// One event → a toast (§6.5 voices): icon, rich spans, and the merge key.
fn toast_for(
    db: &gf_content::ContentDb,
    link: &Link,
    room: &CurrentRoom,
    offer: &[gf_net::BoonOffer],
    ev: &GameEvent,
) -> Option<(String, Vec<(Ty, String, Color)>)> {
    let pc = |slot: u8| player_color(db, slot as usize);
    let dim = |s: &str| (Ty::Body, s.to_string(), tok::PARCH_DIM);
    let strong = |s: String, c: Color| (Ty::Strong, s, c);
    let part_color = |r: Rarity| if r == Rarity::Common { tok::PARCH } else { rarity_color(r) };
    Some(match *ev {
        GameEvent::BoonTaken { slot, boon } => {
            let def = db.boons.try_get(boon)?;
            let rarity = offer.iter().find(|o| o.boon == boon).map(|o| o.rarity);
            let c = rarity.map_or(tok::PARCH, part_color);
            (ik::boon(&def.key), vec![strong(who(link, slot), pc(slot)), dim(" took "), strong(def.name.clone(), c)])
        }
        GameEvent::Forged { slot, outcome } if Some(slot) == link.slot => match outcome {
            ForgeOutcome::Equipped { slot: s, part, .. } => {
                let name = db.parts.try_get(part.part.0)?.name.clone();
                (
                    "ui/equip".into(),
                    vec![dim("Equipped "), strong(name, part_color(part.rarity)), dim(&format!(" · {}", s.name()))],
                )
            }
            ForgeOutcome::Fused { part, .. } => {
                let name = db.parts.try_get(part.part.0)?.name.clone();
                ("ui/fuse".into(), vec![dim("Fused into "), strong(name, part_color(part.rarity))])
            }
            ForgeOutcome::Rerolled { part, .. } => {
                let name = db.parts.try_get(part.part.0)?.name.clone();
                ("ui/reroll".into(), vec![dim("Rerolled into "), strong(name, part_color(part.rarity))])
            }
            ForgeOutcome::Salvaged { shards } => (
                "ui/salvage".into(),
                vec![dim("Salvaged for "), strong(format!("{shards}"), tok::ICHOR), dim(" godshards")],
            ),
        },
        GameEvent::SealGained { seals, required } => (
            "currency/seal".into(),
            vec![strong("Seal claimed".into(), tok::GOLD_LT), dim(&format!(" · {seals} of {required}"))],
        ),
        GameEvent::Downed { slot } => (
            "states/downed".into(),
            vec![
                strong(who(link, slot), pc(slot)),
                dim(" went down · "),
                strong("revive".into(), tok::PARCH),
                dim(" within 20 s"),
            ],
        ),
        GameEvent::Revived { slot, .. } => {
            ("states/tether".into(), vec![strong(who(link, slot), pc(slot)), dim(" is back in the fight")])
        }
        GameEvent::ArmorBreak { slot } if Some(slot) == link.slot => {
            ("states/armor_break".into(), vec![strong("Armour broken".into(), tok::STEEL[1])])
        }
        GameEvent::RoomCleared => {
            ("run/explored".into(), vec![strong("Room cleared".into(), tok::GOLD_LT), dim(" · choose a door")])
        }
        GameEvent::AnvilLit => {
            ("poi/anvil".into(), vec![strong("The anvil kindles".into(), tok::GOLD_LT), dim(" · hold the ring")])
        }
        GameEvent::AnvilHot => {
            ("poi/anvil".into(), vec![strong("The anvil is hot".into(), tok::ICHOR), dim(" · forge now")])
        }
        GameEvent::GateGathering { slot } => {
            ("run/gathering".into(), vec![strong(who(link, slot), pc(slot)), dim(" started the gathering")])
        }
        GameEvent::ThreatRose { level } => (
            "run/threat".into(),
            vec![strong("Threat rises".into(), tok::THREAT[0]), dim(&format!(" · {}", super::roman(level as u32 + 1)))],
        ),
        GameEvent::PoiCompleted { index } => {
            let site = room.def.map.as_deref()?.pois.get(index as usize)?;
            if site.seals > 0 || site.kind == PoiKind::Gate {
                return None;
            }
            let label = crate::scene::poi_label(db, site);
            (ik::poi(site.kind), vec![strong(label, tok::PARCH), dim(" · done")])
        }
        GameEvent::PoiHint { index } => {
            let site = room.def.map.as_deref()?.pois.get(index as usize)?;
            let label = crate::scene::poi_label(db, site);
            ("ui/info".into(), vec![dim("The Forge whispers · "), strong(label, tok::PARCH)])
        }
        _ => return None,
    })
}

pub(super) fn toasts(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    input: Res<InputState>,
    kit: Res<UiKit>,
    mut party: ResMut<Party>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let dt = time.delta_secs();
    let mut fresh: Vec<(String, String, Vec<(Ty, String, Color)>)> = Vec::new();
    let offer = party.last_offer.clone();
    for ev in &link.fresh_events {
        if let Some((icon, spans)) = toast_for(db, &link, &room, &offer, ev) {
            let key: String = spans.iter().map(|s| s.1.as_str()).collect();
            fresh.push((key, icon, spans));
        }
    }
    if let Some(w) = link.latest.as_deref()
        && !w.private.boon_offer.is_empty()
    {
        party.last_offer = w.private.boon_offer.clone();
    }
    // A bias change is a toast too (the Hearth shows the glyph only when not Balanced).
    if party.last_bias.is_some_and(|b| b != input.bias) {
        fresh.push((
            format!("bias{:?}", input.bias),
            ik::bias(input.bias).to_string(),
            vec![
                (Ty::Body, "Target bias · ".into(), tok::PARCH_DIM),
                (Ty::Strong, input.bias.name().into(), tok::PARCH),
            ],
        ));
    }
    party.last_bias = Some(input.bias);

    let mut changed = false;
    for (key, icon, spans) in fresh {
        // Identical toasts merge into ×N.
        if let Some(t) = party.list.iter_mut().find(|t| t.key == key && t.age < HOLD + IN) {
            t.count += 1;
            t.age = t.age.min(IN);
            t.bump = true;
            changed = true;
            continue;
        }
        party.list.insert(0, Toast { key, icon, spans, count: 1, age: 0.0, bump: false });
        party.shift = 0.0;
        changed = true;
    }
    for t in &mut party.list {
        t.age += dt;
    }
    let before = party.list.len();
    party.list.retain(|t| t.age < IN + HOLD + OUT);
    party.list.truncate(3);
    if party.list.len() != before {
        changed = true;
    }
    party.shift = (party.shift + dt / 0.15).min(1.0);

    if changed {
        for i in 0..3 {
            let slot = party.slots[i];
            commands.entity(slot).despawn_children();
            if let Some(t) = party.list.get(i) {
                let mut spans: Vec<(Ty, &str, Color)> =
                    t.spans.iter().map(|(ty, s, c)| (*ty, s.as_str(), *c)).collect();
                let times = format!(" ×{}", t.count);
                if t.count > 1 {
                    spans.push((Ty::Strong, times.as_str(), tok::GOLD_LT));
                }
                commands.entity(slot).insert(FadeGroup::new(toast_alpha(t.age))).with_children(|c| {
                    uikit::toast(c, &kit, &t.icon, &spans);
                });
                if t.bump {
                    commands.entity(slot).insert(uikit::pop(0.08, 0.12));
                }
            }
        }
        for t in &mut party.list {
            t.bump = false;
        }
    }
    for i in 0..3 {
        let slot = party.slots[i];
        match party.list.get(i) {
            Some(t) => {
                ui.show(slot, true);
                let a_in = (t.age / IN).min(1.0);
                ui.fade(slot, toast_alpha(t.age));
                let slide = -24.0 * (1.0 - a_in).powi(2);
                let reflow = if i > 0 && party.shift < 1.0 { -32.0 * (1.0 - party.shift).powi(3) } else { 0.0 };
                if ui.tfs.get(slot).is_ok_and(|tf| tf.scale == Vec2::ONE) {
                    ui.transform(slot, Vec2::new(slide, reflow), 1.0);
                }
            }
            None => ui.show(slot, false),
        }
    }
}
