//! The door panel (UI_STYLE §7.5): legacy rooms (`--room`) and boss transitions. A small gilt panel
//! above the Hearth; each door is a button carrying its reward icon (walking into a door works
//! too, this is the touch- and pad-friendly way).

use super::{CapturesPointer, Nav, PanelKind, PanelState, PanelWorld, UiAction, god_text_color, key_of};
use crate::ClientConfig;
use crate::net::Link;
use crate::scene::door_label;
use crate::theme::{Ty, god_colors, tok, z};
use crate::uikit::{ButtonKind, Gem, PanelStyle, UiKit, button, ember_knot, gilt_panel, icon, ik};
use gf_content::ContentDb;
use gf_engine::client::Hovered;
use gf_engine::prelude::*;
use gf_net::{DoorReward, EntityKind, PlayerAction, RunPhase, WorldSnapshot};

/// A cleared legacy room with reward doors.
pub(super) fn has_doors(w: &WorldSnapshot) -> bool {
    w.run.phase == RunPhase::Cleared && w.entities.iter().any(|e| matches!(e.kind, EntityKind::Door { .. }))
}

fn doors(w: &WorldSnapshot) -> Vec<(u8, DoorReward)> {
    let mut d: Vec<(u8, DoorReward)> = w
        .entities
        .iter()
        .filter_map(|e| match e.kind {
            EntityKind::Door { reward, index } => Some((index, reward)),
            _ => None,
        })
        .collect();
    d.sort_by_key(|(i, _)| *i);
    d
}

/// A door reward's icon and tint.
fn reward_icon(db: &ContentDb, r: DoorReward) -> (String, Color) {
    match r {
        DoorReward::PartCache => ("poi/reliquary".into(), tok::BONE),
        DoorReward::ShardCache => ("currency/godshard".into(), Color::WHITE),
        DoorReward::Anvil => ("poi/anvil".into(), tok::BONE),
        DoorReward::Healing => ("poi/spring".into(), tok::BONE),
        DoorReward::Boon { god } => {
            let g = db.gods.try_get(god);
            let key = g.map_or("?", |g| g.key.as_str());
            let tint = god_colors(db, key).map_or(tok::BONE, |(p, s)| god_text_color(key, p, s));
            (ik::god(key), tint)
        }
        DoorReward::EliteChallenge => ("run/threat".into(), tok::THREAT[0]),
        DoorReward::Onward => ("run/gate_open".into(), tok::BONE),
    }
}

#[derive(Default)]
pub(super) struct DoorUi {
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
    mut ui: Local<DoorUi>,
) {
    let list = pw.get(&link).filter(|_| state.doors).map(doors).unwrap_or_default();
    if list.is_empty() {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.key = 0;
        return;
    }
    let key = key_of(format!("{list:?}"));
    if ui.key == key && ui.root.is_some() {
        return;
    }
    if let Some(r) = ui.root.take() {
        commands.entity(r).despawn();
    }
    ui.key = key;
    let db = &cfg.content;
    let kit = &*kit;
    let root = commands
        .spawn((
            Node { position_type: PositionType::Absolute, left: px(24.0), bottom: px(214.0), ..default() },
            GlobalZIndex(z::PANEL),
            CapturesPointer,
            Hovered::default(),
        ))
        .with_children(|l| {
            gilt_panel(
                l,
                kit,
                Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    padding: UiRect { left: px(20.0), right: px(20.0), top: px(18.0), bottom: px(20.0) },
                    row_gap: px(8.0),
                    min_width: px(344.0),
                    ..default()
                },
                PanelStyle::horns(30),
                |p| {
                    p.spawn(kit.text_tracked(Ty::LabelS, 14.0, 0.16, "CHOOSE THE NEXT CHAMBER", tok::GOLD_LT));
                    ember_knot(p, kit, 280.0, Gem::Ivory, 0.9);
                    for (index, reward) in &list {
                        let (key, tint) = reward_icon(db, *reward);
                        let e = button(p, kit, ButtonKind::Secondary, &door_label(db, *reward), 304.0, 44.0, |t| {
                            icon(t, &key, 26.0, tint);
                        });
                        p.commands_mut()
                            .entity(e)
                            .insert((UiAction::Player(PlayerAction::ChooseDoor(*index)), Nav(PanelKind::Doors)));
                    }
                },
            );
        })
        .id();
    ui.root = Some(root);
}
