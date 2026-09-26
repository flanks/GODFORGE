//! The Arsenal (UI_STYLE §6.2), bottom-right: the forged weapon as shapes and gems (chassis hex,
//! Core / Mechanism / Relic / Sigil slots), the wallet above it, the boon chip above that
//! (§6.3), and a hover card with the names.

use super::{FadeGroup, HudFocus, HudRect, Ui, anchored, db, drawer_open};
use crate::ClientConfig;
use crate::input::{Device, InputState};
use crate::net::Link;
use crate::palette::{element_color, rarity_color};
use crate::theme::{Ty, hx, region, tok, z};
use crate::uikit::{self, MedallionSpec, RingStyle, SlotShape, SlotSpec, UiKit, ik, pop};
use gf_core::forge::{Slot, matching_recipes};
use gf_core::ids::RecipeId;
use gf_engine::client::{Pickable, PrimaryWindow};
use gf_engine::prelude::*;
use gf_net::AnvilState;

const O: Vec2 = Vec2::new(region::ARSENAL[0], region::ARSENAL[1]);
const PART_X: [f32; 4] = [1578.0, 1638.0, 1698.0, 1758.0];

fn at(x: f32, y: f32, w: f32, h: f32) -> Node {
    uikit::abs(x - O.x, y - O.y, w, h)
}

fn centred(cx: f32, cy: f32, w: f32, h: f32) -> Node {
    at(cx - w / 2.0, cy - h / 2.0, w, h)
}

#[derive(Resource)]
pub(super) struct Arsenal {
    root: Entity,
    glow: Entity,
    chassis: Entity,
    charge: Entity,
    element: Entity,
    parts: [Entity; 4],
    gems: [Entity; 4],
    lock: Entity,
    charges: Entity,
    hammers: Vec<Entity>,
    shards_icon: Entity,
    shards: Entity,
    ember_icon: Entity,
    ember: Entity,
    shown: (f32, f32),
    target: (u32, u32),
    element_key: Option<gf_core::damage::DamageType>,
    chip_root: Entity,
    chip_body: Entity,
    chip_key: Option<(String, u8, bool)>,
    chip_t: f32,
    tip: Entity,
    tip_key: Option<String>,
    hover: f32,
}

pub(super) fn spawn(mut commands: Commands, kit: Res<UiKit>) {
    let kit = &*kit;
    let mut a = Arsenal {
        root: Entity::PLACEHOLDER,
        glow: Entity::PLACEHOLDER,
        chassis: Entity::PLACEHOLDER,
        charge: Entity::PLACEHOLDER,
        element: Entity::PLACEHOLDER,
        parts: [Entity::PLACEHOLDER; 4],
        gems: [Entity::PLACEHOLDER; 4],
        lock: Entity::PLACEHOLDER,
        charges: Entity::PLACEHOLDER,
        hammers: Vec::new(),
        shards_icon: Entity::PLACEHOLDER,
        shards: Entity::PLACEHOLDER,
        ember_icon: Entity::PLACEHOLDER,
        ember: Entity::PLACEHOLDER,
        shown: (-1.0, -1.0),
        target: (0, 0),
        element_key: None,
        chip_root: Entity::PLACEHOLDER,
        chip_body: Entity::PLACEHOLDER,
        chip_key: None,
        chip_t: 0.0,
        tip: Entity::PLACEHOLDER,
        tip_key: None,
        hover: 0.0,
    };
    a.root = commands
        .spawn((anchored(uikit::Corner::BottomRight, region::ARSENAL), GlobalZIndex(z::HUD), HudRect, Pickable::IGNORE))
        .with_children(|p| {
            // The chassis: a flat hex over a radial glow in the element hue.
            a.glow =
                p.spawn((centred(1846.0, 1006.0, 150.0, 150.0), BackgroundGradient::default(), Pickable::IGNORE)).id();
            p.spawn((centred(1846.0, 1006.0, 100.0, 100.0), Pickable::IGNORE)).with_children(|s| {
                a.chassis =
                    uikit::slot(s, kit, SlotSpec::new(SlotShape::HexFlat, 100.0).icon("ui/info").icon_frac(0.66));
            });
            // The weapon's charge (charged chassis) as a thin gold ring.
            a.charge = uikit::ring_meter(p, centred(1846.0, 1006.0, 112.0, 112.0), 2.0, RingStyle::Gold, 0.0);
            p.spawn((centred(1808.0, 1040.0, 30.0, 30.0), ZIndex(2), Pickable::IGNORE)).with_children(|s| {
                a.element = uikit::element_cabochon(s, kit, "kinetic", 30.0);
            });

            // The four part slots: the shape is the slot; a cut rarity gem under each.
            for (i, slot) in Slot::ALL.into_iter().enumerate() {
                let x = PART_X[i];
                p.spawn((centred(x, 1014.0, 52.0, 52.0), Pickable::IGNORE)).with_children(|s| {
                    a.parts[i] = uikit::slot(
                        s,
                        kit,
                        SlotSpec::new(SlotShape::for_part(slot), 52.0).ghost(ik::slot_ghost(slot)).icon_frac(0.7),
                    );
                });
                a.gems[i] = p
                    .spawn((
                        Node { display: Display::None, ..centred(x, 1046.0, 13.0, 13.0) },
                        uikit::icon_bundle("rarity/gem_common", 13.0, Color::WHITE),
                    ))
                    .id();
            }
            a.lock = p
                .spawn((
                    Node { display: Display::None, ..centred(1778.0, 993.0, 16.0, 16.0) },
                    uikit::icon_bundle("ui/lock", 16.0, tok::BONE),
                    ZIndex(3),
                ))
                .id();

            // The wallet: forge charges (while an anvil is hot), godshards, ember.
            p.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    right: px(0.0),
                    top: px(930.0 - O.y),
                    height: px(28.0),
                    align_items: AlignItems::Center,
                    column_gap: px(5.0),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|w| {
                a.charges = w
                    .spawn((
                        Node { display: Display::None, margin: UiRect::right(px(10.0)), ..uikit::row(2.0) },
                        Pickable::IGNORE,
                    ))
                    .with_children(|c| {
                        for _ in 0..3 {
                            a.hammers.push(
                                c.spawn((
                                    Node { width: px(20.0), height: px(20.0), ..default() },
                                    uikit::icon_bundle("currency/forge_charge", 20.0, Color::WHITE),
                                ))
                                .id(),
                            );
                        }
                    })
                    .id();
                a.shards_icon = w
                    .spawn((
                        Node { width: px(28.0), height: px(28.0), ..default() },
                        uikit::icon_bundle("currency/godshard", 28.0, Color::WHITE),
                        UiTransform::default(),
                    ))
                    .id();
                a.shards = w.spawn(kit.text_px(Ty::NumS, 20.0, "0", tok::NUMERAL)).id();
                w.spawn(Node { width: px(10.0), ..default() });
                a.ember_icon = w
                    .spawn((
                        Node { width: px(26.0), height: px(26.0), ..default() },
                        uikit::icon_bundle("currency/ember", 26.0, Color::WHITE),
                        UiTransform::default(),
                    ))
                    .id();
                a.ember = w.spawn(kit.text_px(Ty::NumS, 20.0, "0", tok::NUMERAL)).id();
            });

            // The hover card (§6.2), rebuilt when shown.
            a.tip = p
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        right: px(0.0),
                        bottom: px(region::ARSENAL[3] - region::ARSENAL[1] + 8.0),
                        display: Display::None,
                        ..default()
                    },
                    GlobalZIndex(z::BOON_CHIP + 1),
                    Pickable::IGNORE,
                ))
                .id();
        })
        .id();

    // The boon chip: its own root so it joins HudRects only while an offer waits.
    a.chip_root = commands
        .spawn((
            Node { display: Display::None, ..anchored(uikit::Corner::BottomRight, region::BOON_CHIP) },
            GlobalZIndex(z::BOON_CHIP),
            HudRect,
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            a.chip_body = c.spawn((uikit::fill(), FadeGroup::new(1.0), Pickable::IGNORE)).id();
        })
        .id();
    commands.insert_resource(a);
}

/// Pyra and Umbra-Rex are red: their secondary colour stands next to text (§3.4).
fn god_text_color(db: &gf_content::ContentDb, key: &str) -> Color {
    let (c, c2) = crate::theme::god_colors(db, key).unwrap_or((tok::GOLD_LT, tok::GOLD_LT));
    if matches!(key, "pyra" | "umbra_rex") { c2 } else { c }
}

fn build_chip(
    c: &mut ChildSpawnerCommands,
    kit: &UiKit,
    db: &gf_content::ContentDb,
    god: &str,
    waiting: u8,
    pad: bool,
) {
    let (enamel, _) = crate::theme::god_colors(db, god).unwrap_or((tok::GOLD_MD, tok::GOLD_MD));
    let text_c = god_text_color(db, god);
    let name = db.gods.by_key(god).map_or("THE GODS".to_string(), |g| g.name.to_uppercase());
    let w = region::BOON_CHIP[2] - region::BOON_CHIP[0];
    // The ink smear, fading left.
    c.spawn((
        Node {
            position_type: PositionType::Absolute,
            right: px(-6.0),
            top: px(6.0),
            width: px(340.0),
            height: px(60.0),
            ..default()
        },
        BackgroundGradient(vec![
            LinearGradient::to_right(vec![
                ColorStop::percent(tok::POOL.with_alpha(0.0), 0.0),
                ColorStop::percent(tok::POOL.with_alpha(0.5), 45.0),
                ColorStop::percent(tok::POOL.with_alpha(0.66), 100.0),
            ])
            .into(),
        ]),
        Pickable::IGNORE,
    ));
    // The god medallion with its breathing glow.
    c.spawn((
        Node {
            position_type: PositionType::Absolute,
            left: px(w - 60.0),
            top: px(6.0),
            width: px(60.0),
            height: px(60.0),
            border_radius: BorderRadius::MAX,
            ..default()
        },
        uikit::glow(enamel.with_alpha(0.0), 16.0, 2.0),
        uikit::Pulse::shadow(0.5, 0.15, 0.55),
        Pickable::IGNORE,
    ))
    .with_children(|m| {
        uikit::medallion(
            m,
            kit,
            MedallionSpec::new(60.0).enamel(enamel.with_alpha(0.9)).glyph(&ik::god(god), 0.62, Color::WHITE),
        );
    });
    c.spawn((
        Node {
            position_type: PositionType::Absolute,
            right: px(region::BOON_CHIP[2] - 1822.0),
            top: px(10.0),
            height: px(52.0),
            align_items: AlignItems::Center,
            column_gap: px(10.0),
            ..default()
        },
        Pickable::IGNORE,
    ))
    .with_children(|r| {
        if pad {
            uikit::key_chip(r, kit, uikit::Key::Icon("input/pad_view"), 22.0);
        } else {
            uikit::keycap(r, kit, "Tab", 22.0);
        }
        r.spawn((
            Node { flex_direction: FlexDirection::Column, align_items: AlignItems::FlexEnd, ..default() },
            Pickable::IGNORE,
        ))
        .with_children(|t| {
            t.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.16, format!("{name} OFFERS"), text_c));
            let sub = if waiting > 0 { format!("a boon · {waiting} waiting") } else { "a boon".to_string() };
            t.spawn(kit.text_px(Ty::BodyS, 16.0, sub, tok::PARCH_DIM));
        });
    });
}

#[allow(clippy::too_many_arguments)]
pub(super) fn update(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    input: Res<InputState>,
    focus: Res<HudFocus>,
    kit: Res<UiKit>,
    windows: Query<&Window, With<PrimaryWindow>>,
    scale: Res<UiScale>,
    globals: Query<&UiGlobalTransform>,
    mut a: ResMut<Arsenal>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let dt = time.delta_secs();
    let Some(world) = link.latest.as_deref() else { return };
    let Some(me) = link.me() else { return };
    let drawer = drawer_open(&focus, &input);
    ui.show(a.root, !drawer);

    // The chassis, its element glow and cabochon.
    let chassis = db.chassis.try_get(me.weapon.chassis.0);
    ui.slot_icon(a.chassis, chassis.map(|c| ik::chassis(&c.key)));
    let prof = gf_sim::bot::weapon_for(db, me);
    if a.element_key != Some(prof.element) {
        a.element_key = Some(prof.element);
        ui.slot_icon(a.element, Some(ik::element(prof.element).to_string()));
        if let Ok(mut g) = ui.grads.get_mut(a.glow) {
            let hue = element_color(prof.element);
            g.0 = vec![
                RadialGradient::new(
                    UiPosition::CENTER,
                    RadialGradientShape::ClosestSide,
                    vec![
                        ColorStop::percent(hue.with_alpha(0.32), 0.0),
                        ColorStop::percent(hue.with_alpha(0.12), 55.0),
                        ColorStop::percent(hue.with_alpha(0.0), 100.0),
                    ],
                )
                .into(),
            ];
        }
    }
    ui.show(a.charge, me.charge > 0.01);
    ui.ring(a.charge, me.charge, me.charge >= 1.0);

    // Parts and gems; the locked Sigil wears its lock.
    for (i, slot) in Slot::ALL.into_iter().enumerate() {
        let part = me.weapon.get(slot);
        let key = part.and_then(|p| db.parts.try_get(p.part.0)).map(|d| ik::part(&d.key));
        ui.slot_icon(a.parts[i], key);
        ui.show(a.gems[i], part.is_some());
        if let Some(p) = part {
            ui.icon(a.gems[i], ik::rarity_gem(p.rarity));
        }
    }
    ui.show(a.lock, db.game.forge.locked_slots.contains(&Slot::Sigil));

    // The wallet counts up over ~250 ms and pops its icon on a change.
    let target = (world.private.wallet.godshards, world.run.ember);
    if target != a.target {
        if target.0 != a.target.0 && a.shown.0 >= 0.0 {
            commands.entity(a.shards_icon).insert(pop(0.18, 0.25));
        }
        if target.1 != a.target.1 && a.shown.1 >= 0.0 {
            commands.entity(a.ember_icon).insert(pop(0.18, 0.25));
        }
        a.target = target;
    }
    let k = (dt / 0.08).min(1.0);
    let ease = |shown: f32, to: u32| {
        if shown < 0.0 || (shown - to as f32).abs() < 0.6 { to as f32 } else { shown + (to as f32 - shown) * k }
    };
    a.shown = (ease(a.shown.0, target.0), ease(a.shown.1, target.1));
    ui.text(a.shards, format!("{:.0}", a.shown.0));
    ui.text(a.ember, format!("{:.0}", a.shown.1));
    let hot = world.private.anvil.is_some_and(|an| an.state == AnvilState::Hot);
    ui.show(a.charges, hot);
    if hot {
        let lit = world.private.wallet.charges as usize;
        for (i, e) in a.hammers.iter().enumerate() {
            ui.tint(*e, if i < lit { Color::WHITE } else { hx(0x5A4A3A).with_alpha(0.7) });
        }
    }

    // The boon chip: shows while an offer waits and no panel covers it.
    let offer = &world.private.boon_offer;
    let chip_on = !offer.is_empty() && !drawer && !focus.boon_spread;
    ui.show(a.chip_root, chip_on);
    if chip_on {
        let god = offer
            .first()
            .and_then(|o| db.boons.try_get(o.boon))
            .and_then(|b| b.gods.first().cloned())
            .unwrap_or_default();
        let pad = input.device == Device::Gamepad;
        let key = (god.clone(), world.private.boon_queue, pad);
        if a.chip_key.as_ref() != Some(&key) {
            let fresh = a.chip_key.is_none();
            a.chip_key = Some(key);
            let body = a.chip_body;
            commands.entity(body).despawn_children();
            commands.entity(body).insert(FadeGroup::new(1.0));
            commands.entity(body).with_children(|c| build_chip(c, &kit, db, &god, world.private.boon_queue, pad));
            if fresh {
                a.chip_t = 0.0;
            }
        }
        // Slide in 24 px from the right over 200 ms.
        a.chip_t = (a.chip_t + dt).min(1.0);
        let k = 1.0 - (1.0 - (a.chip_t / 0.2).min(1.0)).powi(3);
        ui.transform(a.chip_root, Vec2::new(24.0 * (1.0 - k), 0.0), 1.0);
    } else if a.chip_key.is_some() {
        a.chip_key = None;
    }

    // The hover card after 0.4 s over the Arsenal.
    let cursor = windows.single().ok().and_then(|w| w.cursor_position()).map(|c| c / scale.0.max(0.01));
    let rect = match (ui.computed.get(a.root), globals.get(a.root)) {
        (Ok(c), Ok(g)) => {
            let k = c.inverse_scale_factor();
            Some(Rect::from_center_size(g.translation * k, c.size() * k))
        }
        _ => None,
    };
    let over = !drawer && cursor.zip(rect).is_some_and(|(c, r)| r.contains(c)) && input.device == Device::KeyboardMouse;
    a.hover = if over { a.hover + dt } else { 0.0 };
    let show_tip = a.hover > 0.4;
    ui.show(a.tip, show_tip);
    if show_tip {
        let recipes = matching_recipes(
            db.recipe_ingredients.iter().enumerate().map(|(i, ing)| (RecipeId(i as u16), ing.as_slice())),
            &me.weapon,
            prof.element,
        );
        let combo = recipes.first().and_then(|r| db.recipes.try_get(r.0)).map(|r| r.name.clone());
        let parts: Vec<(String, Color)> = Slot::ALL
            .iter()
            .map(|s| match me.weapon.get(*s).and_then(|p| db.parts.try_get(p.part.0).map(|d| (d, p.rarity))) {
                Some((d, r)) => {
                    (d.name.clone(), if r == gf_core::rarity::Rarity::Common { tok::PARCH } else { rarity_color(r) })
                }
                None => (format!("{} · empty", s.name()), tok::PARCH_MUTE),
            })
            .collect();
        let key = format!("{:?}{:?}{parts:?}{combo:?}", me.weapon.chassis, prof.element);
        if a.tip_key.as_ref() != Some(&key) {
            a.tip_key = Some(key);
            let tip = a.tip;
            let name = chassis.map_or("Weapon".to_string(), |c| c.name.clone());
            let el = prof.element;
            commands.entity(tip).despawn_children();
            commands.entity(tip).with_children(|t| {
                uikit::tooltip(
                    t,
                    &kit,
                    Node {
                        width: px(300.0),
                        padding: UiRect::axes(px(18.0), px(14.0)),
                        flex_direction: FlexDirection::Column,
                        row_gap: px(4.0),
                        ..default()
                    },
                    |c| {
                        c.spawn(kit.text_flat(Ty::Label, 16.0, name.to_uppercase(), tok::GOLD_LT));
                        c.spawn((uikit::row(6.0), Pickable::IGNORE)).with_children(|r| {
                            uikit::icon(r, ik::element(el), 16.0, Color::WHITE);
                            r.spawn(kit.text_flat(Ty::LabelS, 13.0, el.name().to_uppercase(), element_color(el)));
                        });
                        uikit::ember_knot(c, &kit, 264.0, uikit::Gem::None, 0.7);
                        for (s, (n, col)) in Slot::ALL.iter().zip(&parts) {
                            c.spawn((uikit::row(8.0), Pickable::IGNORE)).with_children(|r| {
                                r.spawn(kit.text_tracked(
                                    Ty::Micro,
                                    11.0,
                                    0.14,
                                    s.name().to_uppercase(),
                                    tok::PARCH_DIM,
                                ));
                                r.spawn(kit.text_flat(Ty::Strong, 16.0, n.as_str(), *col));
                            });
                        }
                        if let Some(combo) = &combo {
                            c.spawn((Node { margin: UiRect::top(px(4.0)), ..uikit::row(6.0) }, Pickable::IGNORE))
                                .with_children(|r| {
                                    uikit::icon(r, "run/named_combo", 18.0, Color::WHITE);
                                    r.spawn(kit.text_flat(
                                        Ty::LabelS,
                                        13.0,
                                        format!("NAMED COMBO · {}", combo.to_uppercase()),
                                        tok::ICHOR,
                                    ));
                                });
                        }
                    },
                );
            });
        }
    }
}
