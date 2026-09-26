//! The Hearth (UI_STYLE §6.1), bottom-left: one fixation answers "can I act?". The medallion is
//! the pommel (portrait and ultimate ring), the HP bar the blade; under it the gilt rail, armour
//! plates and dash lozenges; then Q, E and the Team Overdrive hex, and the aim chip.

use super::{HudRect, Ui, anchored, db};
use crate::ClientConfig;
use crate::input::{Device, InputState};
use crate::net::Link;
use crate::theme::{Ty, hx, region, tok, z};
use crate::uikit::{
    self, BarFill, BarSpec, HearthParts, KitPips, MoltenFill, MoltenMaterial, RingStyle, SlotShape, SlotSpec,
    SlotState, UiDecode, UiKit, ik,
};
use gf_core::aim::{AimMode, TargetBias};
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::PlayerFlags;

/// Region origin: local px = canvas px − O.
const O: Vec2 = Vec2::new(region::HEARTH[0], region::HEARTH[1]);

fn at(x: f32, y: f32, w: f32, h: f32) -> Node {
    uikit::abs(x - O.x, y - O.y, w, h)
}

fn centred(cx: f32, cy: f32, w: f32, h: f32) -> Node {
    at(cx - w / 2.0, cy - h / 2.0, w, h)
}

struct Buff {
    root: Entity,
    slot: Entity,
    ring: Entity,
    secs: Entity,
}

#[derive(Resource)]
pub(super) struct Hearth {
    medallion_box: Entity,
    built: Option<(u16, u8)>,
    medallion: Option<Entity>,
    passive: Entity,
    passive_ring: Entity,
    buffs: Vec<Buff>,
    hp: Entity,
    hp_cur: Entity,
    hp_max: Entity,
    hp_pulse: Entity,
    plates: Entity,
    plates_w: Entity,
    dash_box: Entity,
    dash: Option<(Entity, u8)>,
    dash_inf: Entity,
    kit_row: Entity,
    q: Entity,
    e: Entity,
    v: Entity,
    aim_icon: Entity,
    aim_mode: Entity,
    aim_note: Entity,
    bias: Entity,
    vignette: Entity,
}

pub(super) fn spawn(
    mut commands: Commands,
    kit: Res<UiKit>,
    mut materials: ResMut<Assets<MoltenMaterial>>,
    mut decode: ResMut<UiDecode>,
) {
    let kit = &*kit;
    // The low-HP danger vignette (§6.1): full screen, under every cluster.
    let vignette = commands
        .spawn((
            Node { display: Display::None, ..uikit::fill() },
            BackgroundGradient::default(),
            GlobalZIndex(z::POOLS - 1),
            Pickable::IGNORE,
        ))
        .id();
    let mut h = Hearth {
        medallion_box: Entity::PLACEHOLDER,
        built: None,
        medallion: None,
        passive: Entity::PLACEHOLDER,
        passive_ring: Entity::PLACEHOLDER,
        buffs: Vec::new(),
        hp: Entity::PLACEHOLDER,
        hp_cur: Entity::PLACEHOLDER,
        hp_max: Entity::PLACEHOLDER,
        hp_pulse: Entity::PLACEHOLDER,
        plates: Entity::PLACEHOLDER,
        plates_w: Entity::PLACEHOLDER,
        dash_box: Entity::PLACEHOLDER,
        dash: None,
        dash_inf: Entity::PLACEHOLDER,
        kit_row: Entity::PLACEHOLDER,
        q: Entity::PLACEHOLDER,
        e: Entity::PLACEHOLDER,
        v: Entity::PLACEHOLDER,
        aim_icon: Entity::PLACEHOLDER,
        aim_mode: Entity::PLACEHOLDER,
        aim_note: Entity::PLACEHOLDER,
        bias: Entity::PLACEHOLDER,
        vignette,
    };
    commands
        .spawn((anchored(uikit::Corner::BottomLeft, region::HEARTH), GlobalZIndex(z::HUD), HudRect, Pickable::IGNORE))
        .with_children(|p| {
            // The gilt rail (the blade's spine) and its lozenge finial, under the bar.
            p.spawn((at(146.0, 952.0, 390.0, 6.0), kit.tex("ornaments/hearth_rail@2x.png"), Pickable::IGNORE));
            p.spawn((centred(550.0, 955.0, 10.0, 10.0), kit.tex("ornaments/finial_lozenge@2x.png"), Pickable::IGNORE));

            // HP: 360×22 with the leaf finial, ghost and ward hatch; numerals over its right end.
            p.spawn((at(170.0, 928.0, 360.0, 22.0), Pickable::IGNORE)).with_children(|b| {
                h.hp = uikit::bar(b, kit, BarSpec::new(360.0, 22.0, BarFill::Hp).ward().finial());
                // Low-HP brightness pulse: a warm overlay over the bar, alpha driven below 30 %.
                h.hp_pulse = b
                    .spawn((
                        Node { border_radius: BorderRadius::all(px(4.0)), ..uikit::inset(2.0) },
                        BackgroundColor(hx(0xFFB08A).with_alpha(0.0)),
                        ZIndex(1),
                        Pickable::IGNORE,
                    ))
                    .id();
            });
            p.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    right: px(region::HEARTH[2] - 522.0),
                    top: px(928.0 - O.y),
                    height: px(22.0),
                    align_items: AlignItems::Center,
                    column_gap: px(2.0),
                    ..default()
                },
                ZIndex(2),
                Pickable::IGNORE,
            ))
            .with_children(|t| {
                h.hp_cur = t.spawn(kit.text_px(Ty::Num, 19.0, "", tok::NUMERAL)).id();
                h.hp_max = t.spawn(kit.text_px(Ty::Num, 15.0, "", tok::PARCH_DIM)).id();
            });

            // Armour plates (hidden without an armour passive).
            h.plates = p
                .spawn((at(170.0, 962.0, 230.0, 9.0), Pickable::IGNORE))
                .with_children(|c| {
                    h.plates_w = uikit::plates(c, kit, 230.0, 4);
                })
                .id();

            // Dash lozenges, right-aligned so the last sits at x 524.
            h.dash_box = p
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        right: px(region::HEARTH[2] - 533.0),
                        top: px(957.0 - O.y),
                        height: px(18.0),
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|d| {
                    h.dash_inf = d
                        .spawn((
                            Node { width: px(22.0), height: px(22.0), display: Display::None, ..default() },
                            uikit::icon_bundle("states/infinite_dash", 22.0, tok::ICHOR),
                        ))
                        .id();
                })
                .id();

            // Buff slots over the bar's left half.
            for i in 0..4 {
                let cx = 184.0 + 40.0 * i as f32;
                let mut b = Buff {
                    root: Entity::PLACEHOLDER,
                    slot: Entity::PLACEHOLDER,
                    ring: Entity::PLACEHOLDER,
                    secs: Entity::PLACEHOLDER,
                };
                b.root = p
                    .spawn((Node { display: Display::None, ..centred(cx, 906.0, 32.0, 32.0) }, Pickable::IGNORE))
                    .with_children(|c| {
                        c.spawn((uikit::centered(28.0, 28.0), Pickable::IGNORE)).with_children(|s| {
                            b.slot = uikit::slot(
                                s,
                                kit,
                                SlotSpec::new(SlotShape::Round, 28.0).icon("ui/info").shadow(false),
                            );
                        });
                        b.ring = uikit::ring_meter(c, uikit::centered(32.0, 32.0), 2.0, RingStyle::Ichor, 1.0);
                        b.secs = c
                            .spawn((
                                Node {
                                    position_type: PositionType::Absolute,
                                    left: px(26.0),
                                    top: px(-6.0),
                                    ..default()
                                },
                                kit.text_px(Ty::Num, 14.0, "", tok::PARCH),
                            ))
                            .id();
                    })
                    .id();
                h.buffs.push(b);
            }

            // The medallion (built once the character is known) and the passive badge.
            h.medallion_box = p.spawn((centred(88.0, 980.0, 128.0, 128.0), Pickable::IGNORE)).id();
            p.spawn((centred(137.0, 931.0, 40.0, 40.0), ZIndex(2), Pickable::IGNORE)).with_children(|c| {
                c.spawn((uikit::centered(34.0, 34.0), Pickable::IGNORE)).with_children(|s| {
                    h.passive =
                        uikit::slot(s, kit, SlotSpec::new(SlotShape::Round, 34.0).icon("ui/info").icon_frac(0.72));
                });
                h.passive_ring = uikit::ring_meter(c, uikit::centered(40.0, 40.0), 2.0, RingStyle::Ichor, 0.0);
            });

            // Kit row: Q, E, V.
            h.kit_row = p
                .spawn((uikit::fill(), Pickable::IGNORE))
                .with_children(|k| {
                    k.spawn((centred(200.0, 1012.0, 60.0, 60.0), Pickable::IGNORE)).with_children(|s| {
                        h.q = uikit::slot(s, kit, SlotSpec::ability("ui/info", 60.0).key("Q"));
                    });
                    k.spawn((centred(272.0, 1012.0, 60.0, 60.0), Pickable::IGNORE)).with_children(|s| {
                        h.e = uikit::slot(s, kit, SlotSpec::ability("ui/info", 60.0).key("E"));
                    });
                    k.spawn((centred(352.0, 1010.0, 68.0, 68.0), Pickable::IGNORE)).with_children(|s| {
                        h.v = uikit::overdrive_hex(s, kit, &mut materials, &mut decode, 68.0, "V");
                    });
                })
                .id();

            // The aim chip.
            h.aim_icon =
                p.spawn((centred(411.0, 1004.0, 26.0, 26.0), uikit::icon_bundle("aim/auto", 26.0, Color::WHITE))).id();
            p.spawn((
                Node {
                    position_type: PositionType::Absolute,
                    left: px(430.0 - O.x),
                    top: px(994.0 - O.y),
                    flex_direction: FlexDirection::Column,
                    row_gap: px(1.0),
                    ..default()
                },
                Pickable::IGNORE,
            ))
            .with_children(|t| {
                h.aim_mode = t.spawn(kit.text_px(Ty::LabelS, 14.0, "AUTO", tok::PARCH)).id();
                t.spawn((uikit::row(5.0), Pickable::IGNORE)).with_children(|r| {
                    h.aim_note = r.spawn(kit.text_px(Ty::BodyS, 15.0, "", tok::PARCH_DIM)).id();
                    h.bias = r
                        .spawn((
                            Node { width: px(16.0), height: px(16.0), display: Display::None, ..default() },
                            uikit::icon_bundle("aim/bias_balanced", 16.0, Color::WHITE),
                        ))
                        .id();
                });
            });
        });
    commands.insert_resource(h);
}

/// The kit icon of an ability slot of a character.
fn kit_icon(cfg: &ClientConfig, character: u16, slot: &str) -> Option<String> {
    db(cfg).characters.try_get(character).map(|c| ik::kit(&c.key, slot))
}

#[allow(clippy::too_many_arguments)]
pub(super) fn update(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    input: Res<InputState>,
    kit: Res<UiKit>,
    mut h: ResMut<Hearth>,
    mut ui: Ui,
    mut molten: Query<&mut MoltenFill>,
    mut plates: Query<&mut uikit::KitPlates>,
    mut pips: Query<&mut KitPips>,
    parts: Query<&HearthParts>,
) {
    let db = db(&cfg);
    let Some(world) = link.latest.as_deref() else { return };
    let Some(me) = link.me() else { return };
    let now = time.elapsed_secs();
    let alive = me.life.is_alive();

    // Rebuild the medallion when the character or the slot (the band colour) changes.
    if h.built != Some((me.character, me.slot)) {
        h.built = Some((me.character, me.slot));
        if let Some(old) = h.medallion.take() {
            commands.entity(old).despawn();
        }
        let key = db.characters.try_get(me.character).map_or("valdris".to_string(), |c| c.key.clone());
        let band = crate::theme::player_color(db, me.slot as usize);
        let mut m = Entity::PLACEHOLDER;
        commands.entity(h.medallion_box).with_children(|c| {
            m = uikit::hearth_medallion(c, &kit, &ik::portrait(&key), band, "R");
        });
        h.medallion = Some(m);
        ui.slot_icon(h.q, kit_icon(&cfg, me.character, "q"));
        ui.slot_icon(h.e, kit_icon(&cfg, me.character, "e"));
        ui.slot_icon(h.passive, kit_icon(&cfg, me.character, "passive"));
    }

    // Ultimate: the molten trough ring; ready breathes the outer glow.
    let ult_ready = me.ult >= 1.0 && alive;
    if let Some(m) = h.medallion
        && let Ok(p) = parts.get(m)
    {
        ui.ring(p.ult, me.ult, ult_ready);
        ui.pulse(p.glow, ult_ready);
    }

    // HP, ward and the numerals.
    let max = me.max_hp.max(1.0);
    let hp = me.hp.max(0.0);
    ui.bar(h.hp, hp / max, me.shield / max);
    ui.text(h.hp_cur, format!("{hp:.0}"));
    ui.text(h.hp_max, format!("/ {max:.0}"));
    let low = alive && hp / max < 0.3;
    let pulse = if low { 0.5 + 0.5 * (now * std::f32::consts::TAU * 1.2).sin() } else { 0.0 };
    if let Ok(mut bg) = ui.bgs.get_mut(h.hp_pulse) {
        let c = hx(0xFFB08A).with_alpha((pulse * 0.22 * 50.0).round() / 50.0);
        if bg.0 != c {
            bg.0 = c;
        }
    }
    // The danger vignette at the screen edges, 0.25 → 0.45 at 0.9 Hz.
    ui.show(h.vignette, low);
    if low && let Ok(mut g) = ui.grads.get_mut(h.vignette) {
        let a = 0.25 + 0.2 * (0.5 + 0.5 * (now * std::f32::consts::TAU * 0.9).sin());
        let a = (a * 50.0).round() / 50.0;
        let red = hx(0xB0141A);
        let want = vec![
            RadialGradient::new(
                UiPosition::CENTER,
                RadialGradientShape::FarthestCorner,
                vec![
                    ColorStop::percent(red.with_alpha(0.0), 0.0),
                    ColorStop::percent(red.with_alpha(0.0), 55.0),
                    ColorStop::percent(red.with_alpha(a * 0.5), 80.0),
                    ColorStop::percent(red.with_alpha(a), 100.0),
                ],
            )
            .into(),
        ];
        if g.0 != want {
            g.0 = want;
        }
    }

    // Armour plates.
    let armoured = me.armor_max > 0.0;
    ui.show(h.plates, armoured);
    if let Ok(mut p) = plates.get_mut(h.plates_w) {
        let v = (me.armor / me.armor_max.max(1.0) * 4.0).clamp(0.0, 4.0);
        let v = (v * 100.0).round() / 100.0;
        if p.value != v {
            p.value = v;
        }
    }

    // Dash: lozenges (rebuilt when the maximum changes) or the infinite glyph.
    let infinite = me.flags.contains(PlayerFlags::INFINITE_DASH);
    ui.show(h.dash_inf, infinite);
    let n = me.max_dash.max(1);
    if h.dash.map(|(_, k)| k) != Some(n) {
        if let Some((old, _)) = h.dash.take() {
            commands.entity(old).despawn();
        }
        let mut e = Entity::PLACEHOLDER;
        commands.entity(h.dash_box).with_children(|d| {
            e = uikit::dash_pips(d, &kit, n as u32);
        });
        h.dash = Some((e, n));
    }
    if let Some((e, _)) = h.dash {
        ui.show(e, !infinite);
        if let Ok(mut p) = pips.get_mut(e) {
            let full = me.mover.dash_charges.min(n) as u32;
            let refill = if full < n as u32 && me.dash_recharge > 0.0 {
                (1.0 - me.mover.dash_recharge_left / me.dash_recharge).clamp(0.0, 1.0)
            } else {
                0.0
            };
            let refill = (refill * 50.0).round() / 50.0;
            if p.full != full {
                p.full = full;
            }
            if p.refill != refill {
                p.refill = refill;
            }
        }
    }

    // Q and E: the cooldown language is the kit's; disabled while downed.
    for (i, e) in [(0usize, h.q), (1, h.e)] {
        let state = if !alive {
            SlotState::DISABLED
        } else if me.cooldowns[i] > 0.0 {
            let max = me.cooldowns_max[i].max(0.01);
            let secs = me.cooldowns[i];
            let secs = if secs < 10.0 { (secs * 10.0).ceil() / 10.0 } else { secs.ceil() };
            SlotState::cooling(((me.cooldowns[i] / max) * 360.0).ceil() / 360.0, secs)
        } else {
            SlotState::READY
        };
        ui.slot(e, state);
    }
    // Hide the kit row on touch: the touch buttons carry it (§6.15).
    ui.show(h.kit_row, input.device != Device::Touch);

    // Team Overdrive: the meter pours; ready lights the emblem; active drains from the top.
    let od_max = db.game.overdrive.duration.max(0.1);
    if let Ok(mut f) = molten.get_mut(h.v) {
        let active = world.run.overdrive_active > 0.0;
        let value = if active { world.run.overdrive_active / od_max } else { world.run.overdrive_meter };
        let ready = !active && world.run.overdrive_meter >= 1.0;
        let value = (value.clamp(0.0, 1.0) * 200.0).round() / 200.0;
        if f.value != value {
            f.value = value;
        }
        if f.ready != ready {
            f.ready = ready;
        }
        if f.active != active {
            f.active = active;
        }
    }

    // Passive badge: a thin ichor arc for meters (the armour passive shows as plates instead).
    let meter = if armoured { 0.0 } else { me.passive_meter.clamp(0.0, 1.0) };
    ui.show(h.passive_ring, meter > 0.001);
    ui.ring(h.passive_ring, meter, meter >= 1.0);

    // Buffs: Team Overdrive (timed), forging (Forge Aegis), the stance and avatar buffs.
    let mut buffs: Vec<(String, f32, Option<f32>)> = Vec::new();
    if world.run.overdrive_active > 0.0 {
        buffs.push((
            "states/overdrive_active".into(),
            world.run.overdrive_active / od_max,
            Some(world.run.overdrive_active),
        ));
    }
    if me.forge_open {
        buffs.push(("states/forge_aegis".into(), 1.0, None));
    }
    if me.flags.contains(PlayerFlags::STANCE)
        && let Some(k) = kit_icon(&cfg, me.character, "e")
    {
        buffs.push((k, 1.0, None));
    }
    if me.flags.contains(PlayerFlags::AVATAR)
        && let Some(k) = kit_icon(&cfg, me.character, "r")
    {
        buffs.push((k, 1.0, None));
    }
    for (i, b) in h.buffs.iter().enumerate() {
        match buffs.get(i) {
            Some((key, frac, secs)) => {
                ui.show(b.root, true);
                ui.slot_icon(b.slot, Some(key.clone()));
                ui.ring(b.ring, *frac, false);
                // The last 2 s blink at 2 Hz.
                let blink = secs.is_some_and(|s| s < 2.0) && (now * 4.0).fract() < 0.5;
                ui.tint(b.ring, Color::WHITE);
                ui.text(b.secs, secs.map_or(String::new(), |s| format!("{:.0}", s.ceil())));
                ui.color(b.secs, if blink { tok::PARCH.with_alpha(0.5) } else { tok::PARCH });
            }
            None => ui.show(b.root, false),
        }
    }

    // The aim chip: mode, note, and the bias glyph when it is not Balanced.
    let params = db.aim_params(input.aim_mode);
    ui.icon(h.aim_icon, ik::aim(input.aim_mode));
    ui.text(h.aim_mode, input.aim_mode.name().to_uppercase());
    let note = match input.aim_mode {
        AimMode::Auto => format!("−{:.0}% dmg", (1.0 - params.damage_mult) * 100.0),
        AimMode::Assisted => String::new(),
        AimMode::Manual => format!("Deadeye +{:.0}%", me.deadeye as f32 * params.deadeye_per_hit * 100.0),
    };
    ui.text(h.aim_note, note);
    ui.show(h.bias, input.bias != TargetBias::Balanced);
    ui.icon(h.bias, ik::bias(input.bias));
}
