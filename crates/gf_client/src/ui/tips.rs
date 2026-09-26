//! Hover tooltips (§6.2, §7.1): any entity with a [`Tip`] and `Hovered` shows a small gilt card
//! by the cursor after 0.3 s. One card at a time, rebuilt only when the target changes.

use super::rules_text;
use crate::theme::{Ty, tok};
use crate::uikit::{UiKit, tooltip};
use gf_engine::client::{Hovered, Pickable, PrimaryWindow};
use gf_engine::prelude::*;

/// Tooltip text: a title in its colour, an optional small-caps line and rules text.
#[derive(Component, Clone, Debug, PartialEq)]
pub struct Tip {
    pub title: String,
    pub color: Color,
    pub sub: String,
    pub body: String,
}

impl Tip {
    pub fn new(title: impl Into<String>, color: Color) -> Self {
        Self { title: title.into(), color, sub: String::new(), body: String::new() }
    }

    pub fn sub(mut self, s: impl Into<String>) -> Self {
        self.sub = s.into();
        self
    }

    pub fn body(mut self, s: impl Into<String>) -> Self {
        self.body = s.into();
        self
    }
}

#[derive(Default)]
pub(super) struct TipUi {
    root: Option<Entity>,
    target: Option<Entity>,
    t: f32,
}

/// Tooltips sit above every panel.
const Z_TIP: i32 = crate::theme::z::HELP + 5;
const WIDTH: f32 = 300.0;

#[allow(clippy::too_many_arguments)]
pub(super) fn sync(
    mut commands: Commands,
    kit: Res<UiKit>,
    time: Res<Time>,
    scale: Res<UiScale>,
    windows: Query<&Window, With<PrimaryWindow>>,
    tips: Query<(Entity, &Tip, &Hovered)>,
    mut nodes: Query<&mut Node>,
    mut ui: Local<TipUi>,
) {
    let target = tips.iter().find(|(_, _, h)| h.get()).map(|(e, ..)| e);
    if target != ui.target {
        if let Some(r) = ui.root.take() {
            commands.entity(r).despawn();
        }
        ui.target = target;
        ui.t = 0.0;
    }
    let Some(target) = target else { return };
    ui.t += time.delta_secs();
    let Ok(window) = windows.single() else { return };
    let Some(cursor) = window.cursor_position() else { return };
    let k = scale.0.max(0.01);
    let logical = Vec2::new(window.width(), window.height()) / k;
    let at = cursor / k + Vec2::new(18.0, 22.0);
    let at = Vec2::new(at.x.min(logical.x - WIDTH - 12.0), at.y.min(logical.y - 140.0));
    if ui.root.is_none() && ui.t > 0.3 {
        let Ok((_, tip, _)) = tips.get(target) else { return };
        let tip = tip.clone();
        let kit = &*kit;
        let root = commands
            .spawn((
                Node { position_type: PositionType::Absolute, left: px(at.x), top: px(at.y), ..default() },
                GlobalZIndex(Z_TIP),
                Pickable::IGNORE,
            ))
            .with_children(|c| {
                tooltip(
                    c,
                    kit,
                    Node {
                        width: px(WIDTH),
                        padding: UiRect::axes(px(14.0), px(12.0)),
                        flex_direction: FlexDirection::Column,
                        row_gap: px(4.0),
                        ..default()
                    },
                    |t| {
                        t.spawn(kit.text_flat(Ty::Strong, 17.0, tip.title.clone(), tip.color));
                        if !tip.sub.is_empty() {
                            t.spawn(kit.text_tracked(Ty::Micro, 11.0, 0.16, tip.sub.clone(), tok::PARCH_DIM));
                        }
                        if !tip.body.is_empty() {
                            rules_text(t, kit, 15.0, &tip.body, tok::PARCH, WIDTH - 28.0, Justify::Left);
                        }
                    },
                );
            })
            .id();
        ui.root = Some(root);
    } else if let Some(r) = ui.root
        && let Ok(mut n) = nodes.get_mut(r)
        && (n.left != px(at.x) || n.top != px(at.y))
    {
        n.left = px(at.x);
        n.top = px(at.y);
    }
}
