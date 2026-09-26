//! The boon spread (UI_STYLE §7.2): the gods' offer as shrine-niche cards.
//!
//! The offer waits on the HUD's boon chip; Tab (pad: View) opens the spread, and it opens on its
//! own once no enemy has been within 12 u of the hero for 1.5 s. It never opens over the Forge.
//! The world dims except a soft spotlight around the hero, so incoming danger stays visible, and
//! the camera eases the hero low under the cards.

use super::{Fit, Nav, PanelKind, PanelState, PanelWorld, UiAction, god_text_color, key_of, layer, me_in, rules_text};
use crate::ClientConfig;
use crate::camera::{MainCamera, w3};
use crate::input::{Device, InputState};
use crate::net::{Link, Prediction};
use crate::palette::{mix, rarity_color};
use crate::theme::{Ty, god_colors, hx, tok, z};
use crate::uikit::{
    ButtonKind, Gem, Key, KitHover, NICHE, NicheSpec, PillKind, Tween, TweenTarget, UiKit, abs, button, ember_knot,
    gradient_text, ik, key_chip, niche_card, pill, ribbon, row,
};
use gf_content::{BoonKind, BoonReq, ContentDb};
use gf_core::rarity::Rarity;
use gf_engine::client::{InputFocus, Pickable, world_to_screen};
use gf_engine::prelude::*;
use gf_net::{EntityKind, PlayerAction, WorldSnapshot};

/// Whether the spread is open, and the auto-open bookkeeping.
#[derive(Resource, Default, Debug)]
pub struct BoonSpread {
    pub open: bool,
    /// Seconds the hero has been clear of enemies (auto-open at 1.5 s).
    safe: f32,
    /// The offer the player set aside with LATER: it waits for Tab.
    dismissed: u64,
}

impl BoonSpread {
    /// Close the spread and leave the offer on the chip.
    pub(super) fn later(&mut self, w: Option<&WorldSnapshot>) {
        self.open = false;
        self.safe = 0.0;
        self.dismissed = w.map_or(0, offer_key);
    }
}

fn offer_key(w: &WorldSnapshot) -> u64 {
    key_of(format!("{:?}", w.private.boon_offer))
}

#[derive(Resource, Default)]
pub(super) struct BoonUi {
    root: Option<Entity>,
    key: u64,
    spot: Option<Entity>,
    spot_at: Vec2,
    cards: Vec<Entity>,
    focused: Option<Entity>,
}

pub(super) fn build(app: &mut App) {
    app.init_resource::<BoonSpread>().init_resource::<BoonUi>();
}

/// Open on its own when the hero is safe (§7.2); close when the offer is gone.
#[allow(clippy::too_many_arguments)]
pub(super) fn auto_open(
    time: Res<Time>,
    link: Res<Link>,
    pw: Res<PanelWorld>,
    pred: Res<Prediction>,
    input: Res<InputState>,
    mut spread: ResMut<BoonSpread>,
) {
    let Some(w) = pw.get(&link) else { return };
    if w.private.boon_offer.is_empty() {
        spread.open = false;
        spread.safe = 0.0;
        return;
    }
    if pw.shot == super::qa::Shot::Boon {
        spread.open = true;
        return;
    }
    if spread.open || input.forge_open || offer_key(w) == spread.dismissed {
        spread.safe = 0.0;
        return;
    }
    let Some(me) = pred.state.map(|s| s.pos).or_else(|| link.me().map(|m| m.mover.pos)) else { return };
    let near = w
        .entities
        .iter()
        .any(|e| matches!(e.kind, EntityKind::Enemy { .. }) && e.pos.to_vec2().distance_squared(me) < 144.0);
    spread.safe = if near { 0.0 } else { spread.safe + time.delta_secs() };
    if spread.safe >= 1.5 {
        spread.open = true;
    }
}

/// A god's card colour: red gods lean toward their secondary, so the ivory apex glyph never sits
/// on red (§3.4).
fn card_color(key: &str, primary: Color, secondary: Color) -> Color {
    if matches!(key, "pyra" | "umbra_rex") { mix(primary, secondary, 0.45) } else { primary }
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
    pred: Res<Prediction>,
    focus: Res<InputFocus>,
    scale: Res<UiScale>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut ui: ResMut<BoonUi>,
    mut grads: Query<&mut BackgroundGradient>,
    mut cards: Query<(&KitHover, &mut UiTransform, &mut BoxShadow)>,
) {
    let w = pw.get(&link);
    if !state.boons || w.is_none() {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.key = 0;
        ui.cards.clear();
        ui.focused = None;
        return;
    }
    let w = w.expect("checked");
    let db = &cfg.content;
    let me = me_in(w, link.slot);
    let key = key_of(format!(
        "{:?}{}{}{:?}{:?}",
        w.private.boon_offer,
        w.private.boon_rerolls,
        w.private.boon_queue,
        me.map(|p| &p.boons),
        input.device
    ));
    // The hero's spot on screen (logical px), for the spotlight.
    let hero = me
        .map(|p| pred.state.map_or(p.mover.pos, |s| s.pos + pred.error))
        .and_then(|pos| cameras.single().ok().and_then(|(c, t)| world_to_screen(c, t, w3(pos, 1.0))))
        .map(|s| s / scale.0.max(0.01));
    if ui.key != key || ui.root.is_none() {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        let at = hero.unwrap_or(Vec2::new(960.0, 740.0));
        let (root, spot, cards) =
            spawn_spread(&mut commands, &kit, db, w, me.map(|p| p.boons.as_slice()), input.device, at);
        ui.root = Some(root);
        ui.spot = Some(spot);
        ui.spot_at = at;
        ui.cards = cards;
        ui.key = key;
        ui.focused = None;
    } else if let (Some(at), Some(spot)) = (hero, ui.spot)
        && at.distance(ui.spot_at) > 1.5
        && let Ok(mut g) = grads.get_mut(spot)
    {
        *g = spotlight(at);
        ui.spot_at = at;
    }
    // Pad focus lifts a card like hover does (the kit's hover lift only follows the pointer).
    let focused = focus.get().filter(|f| ui.cards.contains(f));
    if focused != ui.focused {
        for (e, lift) in [(ui.focused, false), (focused, true)] {
            if let Some(e) = e
                && let Ok((h, mut tf, mut shadow)) = cards.get_mut(e)
                && h.t == 0.0
            {
                tf.translation = Val2::px(0.0, if lift { -h.lift } else { 0.0 });
                if let Some(s) = shadow.0.first_mut() {
                    s.color.set_alpha(if lift { h.glow_alpha } else { 0.0 });
                }
            }
        }
        ui.focused = focused;
    }
}

/// The spotlight dim: 0.64 everywhere except a soft hole of radius ~170 around the hero.
fn spotlight(at: Vec2) -> BackgroundGradient {
    let c = tok::SCRIM;
    BackgroundGradient(vec![
        RadialGradient::new(
            UiPosition::TOP_LEFT.at_px(at.x, at.y),
            RadialGradientShape::FarthestCorner,
            vec![
                ColorStop::px(c.with_alpha(0.0), 0.0),
                ColorStop::px(c.with_alpha(0.0), 110.0),
                ColorStop::px(c.with_alpha(0.5), 200.0),
                ColorStop::px(c.with_alpha(0.64), 280.0),
                ColorStop::percent(c.with_alpha(0.64), 100.0),
            ],
        )
        .into(),
    ])
}

/// One offered boon, resolved from content.
struct Offer<'a> {
    name: String,
    kind: BoonKind,
    desc: &'a str,
    rarity: Rarity,
    /// (key, name, card colour, text colour)
    gods: Vec<(String, String, Color, Color)>,
    icon: String,
    owned: usize,
    requires: String,
}

fn resolve<'a>(db: &'a ContentDb, boon: u16, rarity: Rarity, mine: &[u16]) -> Offer<'a> {
    let def = db.boons.try_get(boon);
    let gods = def.map_or(Vec::new(), |d| {
        d.gods
            .iter()
            .filter_map(|g| {
                let def = db.gods.by_key(g)?;
                let (p, s) = god_colors(db, g)?;
                Some((g.clone(), def.name.clone(), card_color(g, p, s), god_text_color(g, p, s)))
            })
            .collect()
    });
    let requires = def.map_or(String::new(), |d| {
        d.requires
            .iter()
            .map(|r| match r {
                BoonReq::FromGod { god, count } => {
                    let n = db.gods.by_key(god).map_or(god.as_str(), |g| g.name.as_str());
                    format!("{count} {n} boon{}", if *count == 1 { "" } else { "s" })
                }
                BoonReq::Boon(k) => db.boons.by_key(k).map_or(k.clone(), |b| b.name.clone()),
            })
            .collect::<Vec<_>>()
            .join(" · ")
    });
    Offer {
        name: def.map_or("?".into(), |d| d.name.to_uppercase()),
        kind: def.map_or(BoonKind::Standard, |d| d.kind),
        desc: def.map_or("", |d| d.desc.as_str()),
        rarity,
        gods,
        icon: ik::boon(def.map_or("?", |d| d.key.as_str())),
        owned: mine.iter().filter(|b| **b == boon).count(),
        requires,
    }
}

/// The largest card-name size (26 → 20) whose line fits the card (§7.2 auto-fit).
fn fit_name(name: &str) -> f32 {
    [26.0, 24.0, 22.0, 20.0].into_iter().find(|s| name.chars().count() as f32 * s * 0.8 <= 256.0).unwrap_or(20.0)
}

#[allow(clippy::too_many_arguments)]
fn spawn_spread(
    commands: &mut Commands,
    kit: &UiKit,
    db: &ContentDb,
    w: &WorldSnapshot,
    mine: Option<&[u16]>,
    device: Device,
    hero: Vec2,
) -> (Entity, Entity, Vec<Entity>) {
    let mine = mine.unwrap_or(&[]);
    let offers: Vec<Offer> = w.private.boon_offer.iter().map(|o| resolve(db, o.boon, o.rarity, mine)).collect();
    let n = offers.len().max(1) as f32;
    let cw = n * NICHE.x + (n - 1.0) * 34.0;
    let ch = 660.0;
    let pad = device == Device::Gamepad;
    // One god across the offer: its name and colours head the spread.
    let first = offers.first().and_then(|o| o.gods.first()).cloned();
    // One god answers when every card carries them (a duo that includes them still counts, §7.2).
    let single = first.as_ref().filter(|g| offers.iter().all(|o| o.gods.iter().any(|x| x.0 == g.0))).cloned();
    let mut spot = Entity::PLACEHOLDER;
    let mut cards = Vec::new();
    let root = commands
        .spawn((layer(z::PANEL), BoonRoot))
        .with_children(|l| {
            spot = l.spawn((crate::uikit::fill(), spotlight(hero), Pickable::IGNORE)).id();
            l.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: percent(50.0),
                    top: px(0.0),
                    width: px(cw),
                    height: px(ch),
                    margin: UiRect::left(px(-cw / 2.0)),
                    ..default()
                },
                Fit { size: Vec2::new(cw, ch), pivot: Vec2::new(0.0, -0.5), pad: Vec2::new(40.0, 0.0) },
                Pickable::IGNORE,
            ))
            .with_children(|cv| {
                // Title, knot and sub-line (§7.2).
                cv.spawn((
                    Node {
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        row_gap: px(6.0),
                        ..abs(0.0, 20.0, cw, 100.0)
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|t| {
                    match &single {
                        Some((_, name, _, text)) => {
                            gradient_text(
                                t,
                                kit,
                                Ty::Title,
                                32.0,
                                &format!("{} ANSWERS", name.to_uppercase()),
                                &[hx(0xFFFFFF), mix(*text, Color::WHITE, 0.55), *text],
                                true,
                            );
                            ember_knot(t, kit, 560.0, Gem::Tint(*text), 1.0);
                        }
                        None => {
                            gradient_text(
                                t,
                                kit,
                                Ty::Title,
                                32.0,
                                "THE GODS ANSWER",
                                &[tok::GOLD_HI, tok::GOLD_LT, tok::GOLD_MD, hx(0xB07A30)],
                                true,
                            );
                            ember_knot(t, kit, 560.0, Gem::Ivory, 1.0);
                        }
                    }
                    let whose =
                        single.as_ref().map_or("The gods' favour".to_string(), |g| format!("Shrine of {}", g.1));
                    t.spawn(kit.text_px(Ty::Flavour, 17.0, format!("{whose} · choose one"), tok::PARCH_DIM));
                });
                for (i, o) in offers.iter().enumerate() {
                    let x = i as f32 * (NICHE.x + 34.0);
                    cv.spawn((
                        abs(x, 150.0, NICHE.x, NICHE.y),
                        Tween::new(TweenTarget::Translate(Vec2::new(0.0, 40.0), Vec2::ZERO), 0.26)
                            .delay(i as f32 * 0.07)
                            .ease(crate::uikit::fx::Ease::OutBack),
                        Pickable::IGNORE,
                    ))
                    .with_children(|c| {
                        let card = boon_card(c, kit, o, i, pad);
                        cards.push(card);
                    });
                }
                // REROLL under the left card, LATER under the right one; the middle stays clear.
                let rerolls = w.private.boon_rerolls;
                if rerolls > 0 {
                    cv.spawn((abs(NICHE.x / 2.0 - 118.0, 600.0, 236.0, 46.0), Pickable::IGNORE)).with_children(|b| {
                        let e = button(b, kit, ButtonKind::Secondary, "Reroll", 236.0, 46.0, |t| {
                            t.spawn((row(6.0), Pickable::IGNORE)).with_children(|r| {
                                key_chip(r, kit, if pad { Key::Icon("input/pad_west") } else { Key::Text("X") }, 22.0);
                                r.spawn(kit.text_flat(Ty::BodyS, 15.0, format!("{rerolls} left"), tok::PARCH_DIM));
                            });
                        });
                        b.commands_mut()
                            .entity(e)
                            .insert((UiAction::Player(PlayerAction::RerollBoons), Nav(PanelKind::Boons)));
                    });
                }
                cv.spawn((abs(cw - NICHE.x / 2.0 - 118.0, 600.0, 236.0, 46.0), Pickable::IGNORE)).with_children(|b| {
                    let queued = w.private.boon_queue;
                    let e = button(b, kit, ButtonKind::Secondary, "Later", 236.0, 46.0, |t| {
                        t.spawn((row(6.0), Pickable::IGNORE)).with_children(|r| {
                            key_chip(r, kit, if pad { Key::Icon("input/pad_view") } else { Key::Text("Tab") }, 22.0);
                            if queued > 0 {
                                r.spawn(kit.text_flat(Ty::BodyS, 15.0, format!("+{queued} queued"), tok::PARCH_DIM));
                            }
                        });
                    });
                    b.commands_mut().entity(e).insert((UiAction::BoonLater, Nav(PanelKind::Boons)));
                });
            });
        })
        .id();
    (root, spot, cards)
}

/// Marks the spread's root layer.
#[derive(Component)]
struct BoonRoot;

fn boon_card(c: &mut ChildSpawnerCommands, kit: &UiKit, o: &Offer, i: usize, pad: bool) -> Entity {
    let spec = NicheSpec {
        rarity: o.rarity,
        gods: o.gods.iter().map(|g| (g.0.clone(), g.2)).collect(),
        icon: o.icon.clone(),
        crest: o.kind == BoonKind::Legendary,
    };
    let card = niche_card(c, kit, &spec, |card| {
        let full = |top: f32| Node {
            position_type: PositionType::Absolute,
            left: px(0.0),
            top: px(top),
            width: px(NICHE.x),
            justify_content: JustifyContent::Center,
            ..default()
        };
        // The god line (§7.2): one god in its colour lifted toward white, a Duo in parchment.
        let (line, line_color) = match o.gods.as_slice() {
            [] => ("EVERY FORGEBEARER".to_string(), tok::PARCH),
            [g] => (g.1.to_uppercase(), mix(g.3, Color::WHITE, 0.45)),
            gs => (gs.iter().map(|g| g.1.to_uppercase()).collect::<Vec<_>>().join(" & "), tok::PARCH),
        };
        card.spawn((full(134.0), Pickable::IGNORE)).with_children(|l| {
            l.spawn(kit.text_tracked(Ty::LabelS, 13.0, 0.23, line, line_color));
        });
        let mut y = 162.0;
        let kind = match o.kind {
            BoonKind::Duo => Some(("Duo", "boon_kind/duo")),
            BoonKind::Legendary => Some(("Legendary", "boon_kind/legendary")),
            BoonKind::Team => Some(("Team", "boon_kind/team")),
            BoonKind::Standard => None,
        };
        if let Some((k, key)) = kind {
            card.spawn((full(y - 4.0), Pickable::IGNORE)).with_children(|l| {
                pill(l, kit, PillKind::Gold, k, Some(key));
            });
            y += 22.0;
        }
        card.spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(8.0),
                ..full(y)
            },
            Pickable::IGNORE,
        ))
        .with_children(|nb| {
            let size = fit_name(&o.name);
            let long = o.name.chars().count() as f32 * size * 0.8 > 256.0;
            if o.rarity == Rarity::Godforged && !long {
                gradient_text(nb, kit, Ty::CardName, size, &o.name, &[hx(0xFFF6D8), hx(0xFFD36B), hx(0xFFB82E)], false);
            } else {
                let color = if o.rarity == Rarity::Common { tok::PARCH } else { rarity_color(o.rarity) };
                let mut e = nb.spawn(kit.text_px(Ty::CardName, size, o.name.clone(), color));
                if long {
                    e.insert((TextLayout::justify(Justify::Center), Node { max_width: px(256.0), ..default() }));
                }
            }
            ribbon(nb, kit, o.rarity);
            ember_knot(nb, kit, 204.0, Gem::Tint(rarity_color(o.rarity)), 0.9);
            rules_text(nb, kit, 18.0, o.desc, tok::PARCH, 248.0, Justify::Center);
            if !o.requires.is_empty() && o.kind != BoonKind::Standard {
                nb.spawn(kit.text_px(Ty::BodyS, 14.0, format!("Needs {}", o.requires), tok::PARCH_MUTE));
            }
        });
        // Footer: NEW / UPGRADE, level pips, the pick key on the plinth.
        card.spawn((abs(26.0, 378.0, 90.0, 16.0), Pickable::IGNORE)).with_children(|f| {
            let (s, c) = if o.owned == 0 { ("NEW", tok::ICHOR) } else { ("UPGRADE", tok::PARCH_DIM) };
            f.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.2, s, c));
        });
        let level = (o.owned + 1).min(3);
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
                let lit = lv < level;
                f.spawn((
                    Node { width: px(10.0), height: px(10.0), border_radius: BorderRadius::MAX, ..default() },
                    BackgroundColor(if lit { tok::ICHOR } else { hx(0x3A2A1C) }),
                    if lit {
                        crate::uikit::glow(tok::ICHOR_GLOW.with_alpha(0.5), 5.0, 0.0)
                    } else {
                        BoxShadow::default()
                    },
                    Pickable::IGNORE,
                ));
            }
        });
        card.spawn((full(390.0), Pickable::IGNORE)).with_children(|k| {
            if pad {
                key_chip(k, kit, Key::Icon("input/pad_south"), 26.0);
            } else {
                crate::uikit::keycap(k, kit, &(i + 1).to_string(), 30.0);
            }
        });
    });
    c.commands_mut().entity(card).insert((UiAction::Player(PlayerAction::PickBoon(i as u8)), Nav(PanelKind::Boons)));
    card
}
