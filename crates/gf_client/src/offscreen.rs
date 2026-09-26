//! Off-screen indicators for NIMRODS-scale arenas: the camera stays on the local player, so
//! allies, doors, the anvil, pings and (on biome maps) the objectives outside the view get an
//! arrow pinned to the screen edge (colour-coded, labelled, with distance).
//!
//! On a map the view covers under 1 % of the ground, so the objectives always point the way: the
//! Boss Gate, and the three nearest Seal POIs still to do.

use crate::camera::{MainCamera, w3};
use crate::net::{CurrentRoom, Link};
use crate::palette::hex;
use crate::scene::{SceneIndex, door_label, poi_color, poi_label};
use crate::{ClientConfig, ClientSet};
use gf_engine::client::text;
use gf_engine::prelude::*;
use gf_net::*;

/// Pool size: allies (3) + doors (3) + anvil + pings + the gate and three objectives.
const POOL: usize = 16;
/// Seal POIs still to do that get a marker (nearest first).
const OBJECTIVES: usize = 3;
/// Seconds a ping stays tracked.
const PING_LIFE: f32 = 5.0;
/// Inset from the screen edge (px).
const MARGIN: f32 = 34.0;
/// Pins closer than this (px, per axis) to an earlier pin slide along their edge.
const SPREAD: Vec2 = Vec2::new(120.0, 44.0);

#[derive(Component)]
struct Indicator;

#[derive(Component)]
struct IndicatorArrow;

#[derive(Component)]
struct IndicatorText;

/// Recent pings (world position, slot, seconds left).
#[derive(Resource, Default)]
struct Pings(Vec<(Vec2, u8, f32)>);

pub fn build(app: &mut App) {
    app.init_resource::<Pings>()
        .add_systems(Startup, spawn_pool)
        .add_systems(Update, update_indicators.in_set(ClientSet::Presentation));
}

fn spawn_pool(mut commands: Commands) {
    for _ in 0..POOL {
        commands
            .spawn((
                Indicator,
                Node {
                    position_type: PositionType::Absolute,
                    width: Val::Px(0.0),
                    height: Val::Px(0.0),
                    display: Display::None,
                    ..default()
                },
                GlobalZIndex(5),
            ))
            .with_children(|p| {
                p.spawn((
                    IndicatorArrow,
                    Node {
                        position_type: PositionType::Absolute,
                        left: Val::Px(-11.0),
                        top: Val::Px(-14.0),
                        ..default()
                    },
                    text("▲", 22.0, Color::WHITE),
                    TextShadow::default(),
                    UiTransform::IDENTITY,
                ));
                p.spawn((
                    IndicatorText,
                    Node {
                        position_type: PositionType::Absolute,
                        left: Val::Px(-40.0),
                        top: Val::Px(12.0),
                        ..default()
                    },
                    text("", 13.0, Color::WHITE),
                    TextLayout::no_wrap(),
                    TextShadow::default(),
                ));
            });
    }
}

/// Move a pin out of the HUD panels (vitals top left, party top right, run banner top centre,
/// the arsenal bottom centre, aim bottom left, stats bottom right): straight down out of a top
/// panel, straight up out of a bottom one. Logical pixels, matching `hud.rs`.
fn clear_of_hud(p: Vec2, size: Vec2) -> Vec2 {
    let cx = size.x * 0.5;
    // (min x, min y, max x, max y) of each panel, padded.
    let panels = [
        (0.0, 0.0, 440.0, 176.0),
        (size.x - 300.0, 0.0, size.x, 146.0),
        (cx - 300.0, 0.0, cx + 300.0, 96.0),
        (cx - 300.0, size.y - 124.0, cx + 300.0, size.y),
        (0.0, size.y - 100.0, 400.0, size.y),
        (size.x - 320.0, size.y - 70.0, size.x, size.y),
    ];
    let mut q = p;
    for (x0, y0, x1, y1) in panels {
        if q.x >= x0 && q.x <= x1 && q.y >= y0 && q.y <= y1 {
            q.y = if y0 <= 0.0 { y1 + 12.0 } else { y0 - 30.0 };
        }
    }
    q
}

/// Where an off-screen point pins to the viewport edge, and the arrow rotation (clockwise from
/// screen-up). `None` when the point is on screen.
pub fn edge_pin(p: Vec2, size: Vec2, margin: f32) -> Option<(Vec2, f32)> {
    let inset = margin * 0.5;
    if p.x >= inset && p.x <= size.x - inset && p.y >= inset && p.y <= size.y - inset {
        return None;
    }
    let c = size * 0.5;
    let d = p - c;
    let h = (c - Vec2::splat(margin)).max(Vec2::splat(1.0));
    let t = (h.x / d.x.abs().max(1e-3)).min(h.y / d.y.abs().max(1e-3));
    Some((c + d * t, d.x.atan2(-d.y)))
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_indicators(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    index: Res<SceneIndex>,
    mut pings: ResMut<Pings>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    rigs: Query<&crate::scene::PlayerRig>,
    mut roots: Query<(&mut Node, &Children), (With<Indicator>, Without<IndicatorText>)>,
    mut arrows: Query<(&mut UiTransform, &mut TextColor), (With<IndicatorArrow>, Without<IndicatorText>)>,
    mut labels: Query<
        (&mut Node, &mut Text, &mut TextColor),
        (With<IndicatorText>, Without<IndicatorArrow>, Without<Indicator>),
    >,
) {
    let dt = time.delta_secs();
    for ev in &link.fresh_events {
        if let GameEvent::Ping { slot, pos, .. } = *ev {
            pings.0.push((pos.to_vec2(), slot, PING_LIFE));
        }
    }
    pings.0.retain_mut(|(_, _, life)| {
        *life -= dt;
        *life > 0.0
    });
    let (Ok((camera, cam_tf)), Some(world)) = (cameras.single(), link.latest.as_deref()) else { return };
    let Some(size) = camera.logical_viewport_size() else { return };
    let db = &cfg.content;
    let me = link.me().map(|p| p.mover.pos);
    let pulse = 0.75 + 0.25 * (time.elapsed_secs() * 5.0).sin();

    // (world point, colour, label)
    let mut targets: Vec<(Vec3, Color, String)> = Vec::new();
    for p in &world.players {
        if Some(p.slot) == link.slot {
            continue;
        }
        let pos = index.players[p.slot as usize].and_then(|e| rigs.get(e).ok()).map_or(p.mover.pos, |r| r.shown);
        let c = hex(&db.game.player_colors[p.slot as usize % 4]);
        let tag = if matches!(p.life, gf_core::revive::LifeState::Downed { .. }) { " ✚ DOWN" } else { "" };
        targets.push((w3(pos, 1.0), c, format!("P{}{tag}", p.slot + 1)));
    }
    for e in &world.entities {
        match e.kind {
            EntityKind::Door { reward, .. } => {
                targets.push((w3(e.pos.to_vec2(), 1.5), hex("#FFE3A3"), door_label(db, reward)))
            }
            EntityKind::Anvil if AnvilState::from_u8(e.status) != AnvilState::Spent => {
                targets.push((w3(e.pos.to_vec2(), 1.0), hex("#FFC940"), "Anvil".into()))
            }
            _ => {}
        }
    }
    for (pos, slot, _) in &pings.0 {
        targets.push((w3(*pos, 0.5), hex(&db.game.player_colors[*slot as usize % 4]), "!".into()));
    }
    // Biome maps: the gate always, then the nearest Seal POIs still to do.
    if let Some(map) = room.def.map.as_deref() {
        let from = me.unwrap_or(room.def.player_spawn);
        let mut todo: Vec<(f32, Vec3, Color, String)> = Vec::new();
        for e in &world.entities {
            let EntityKind::Poi { index } = e.kind else { continue };
            let Some(site) = map.pois.get(index as usize) else { continue };
            let state = PoiState::from_u8(e.status);
            if state == PoiState::Done {
                continue;
            }
            let c = poi_color(db, site.god, site.kind);
            let at = w3(site.at, 1.0);
            if site.kind == PoiKind::Gate {
                let label = match (&world.run.stage, state) {
                    (_, PoiState::Open | PoiState::Gathering) => "BOSS GATE OPEN".to_string(),
                    (Some(st), _) => format!("Boss Gate {}/{}", st.seals, st.required),
                    (None, _) => poi_label(db, site),
                };
                targets.push((at, c, label));
            } else if site.seals > 0 {
                let live = matches!(state, PoiState::Active | PoiState::Hot);
                let tag = if live { " ◆" } else { "" };
                todo.push((site.at.distance(from), at, c, format!("{}{tag}", poi_label(db, site))));
            }
        }
        todo.sort_by(|a, b| a.0.total_cmp(&b.0));
        targets.extend(todo.into_iter().take(OBJECTIVES).map(|(_, at, c, s)| (at, c, s)));
    }

    // Pins in priority order; a pin landing on an earlier one slides along its edge.
    let mut placed: Vec<(Vec2, f32, Color, String, Option<f32>)> = Vec::new();
    for (at, c, s) in targets {
        let Some(screen) = gf_engine::client::world_to_screen(camera, cam_tf, at) else { continue };
        let Some((pin, angle)) = edge_pin(screen, size, MARGIN) else { continue };
        let mut pin = clear_of_hud(pin, size);
        let along_x = pin.y <= MARGIN + 1.0 || pin.y >= size.y - MARGIN - 1.0;
        let step = if along_x { Vec2::new(SPREAD.x, 0.0) } else { Vec2::new(0.0, SPREAD.y) };
        let toward_centre = if along_x { (size.x * 0.5 - pin.x).signum() } else { (size.y * 0.5 - pin.y).signum() };
        for _ in 0..6 {
            let clash = placed.iter().any(|(q, ..)| (q.x - pin.x).abs() < SPREAD.x && (q.y - pin.y).abs() < SPREAD.y);
            if !clash {
                break;
            }
            pin += step * toward_centre;
        }
        let dist = me.map(|m| m.distance(Vec2::new(at.x, -at.z)));
        placed.push((pin, angle, c, s, dist));
    }
    let mut pins = placed.into_iter();
    for (mut node, children) in &mut roots {
        let Some((pin, angle, color, label, dist)) = pins.next() else {
            if node.display != Display::None {
                node.display = Display::None;
            }
            continue;
        };
        node.display = Display::Flex;
        node.left = Val::Px(pin.x);
        node.top = Val::Px(pin.y);
        for child in children.iter() {
            if let Ok((mut tf, mut tc)) = arrows.get_mut(child) {
                tf.rotation = Rot2::radians(angle);
                tc.0 = color.with_alpha(pulse);
            }
            if let Ok((mut label_node, mut t, mut tc)) = labels.get_mut(child) {
                let s = match dist {
                    Some(d) => format!("{label} · {d:.0}m"),
                    None => label.clone(),
                };
                if t.0 != s {
                    t.0 = s;
                }
                if tc.0 != color {
                    tc.0 = color;
                }
                // Keep the label on screen: it hangs inward from pins on the right edge, and below
                // the arrow except on the bottom edge (so pins stacked down a side never overprint).
                let (left, right) = if pin.x > size.x * 0.7 {
                    (Val::Auto, Val::Px(-10.0))
                } else if pin.x < size.x * 0.3 {
                    (Val::Px(-10.0), Val::Auto)
                } else {
                    (Val::Px(-40.0), Val::Auto)
                };
                let (top, bottom) = if pin.y > size.y - MARGIN - 40.0 {
                    (Val::Auto, Val::Px(14.0))
                } else {
                    (Val::Px(12.0), Val::Auto)
                };
                if (label_node.left, label_node.right, label_node.top, label_node.bottom) != (left, right, top, bottom)
                {
                    label_node.left = left;
                    label_node.right = right;
                    label_node.top = top;
                    label_node.bottom = bottom;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn on_screen_points_get_no_pin() {
        assert!(edge_pin(Vec2::new(640.0, 360.0), Vec2::new(1280.0, 720.0), 30.0).is_none());
    }

    #[test]
    fn off_screen_points_pin_to_the_edge_and_point_at_them() {
        let size = Vec2::new(1280.0, 720.0);
        // Far to the right: pinned on the right edge, arrow turned clockwise a quarter turn.
        let (p, a) = edge_pin(Vec2::new(5000.0, 360.0), size, 30.0).unwrap();
        assert!((p.x - 1250.0).abs() < 1e-3 && (p.y - 360.0).abs() < 1e-3, "{p}");
        assert!((a - std::f32::consts::FRAC_PI_2).abs() < 1e-4, "{a}");
        // Straight up: pinned on the top edge, arrow unrotated.
        let (p, a) = edge_pin(Vec2::new(640.0, -900.0), size, 30.0).unwrap();
        assert!((p.y - 30.0).abs() < 1e-3, "{p}");
        assert!(a.abs() < 1e-4, "{a}");
    }
}
