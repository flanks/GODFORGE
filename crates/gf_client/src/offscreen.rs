//! Edge pins (UI_STYLE §6.13): the camera stays on the local player, so allies, doors, the
//! anvil, pings and (on biome maps) the gate and the nearest objectives outside the view get a
//! gilt medallion pinned 40 px inside the screen edge, with an outward nub aimed at them, the
//! distance and (for the top three) a name.
//!
//! Priority: a downed ally > the open gate > a POI with an ally at it > allies > pings > the
//! three nearest incomplete objectives. Pins slide along their edge out of every `HudRects`
//! rect (critically damped) and fade in over 150 ms. Red-white is only for the downed ally.

use crate::camera::{MainCamera, w3};
use crate::hud::{player_name, to_ui, ui_viewport};
use crate::net::{CurrentRoom, Link};
use crate::scene::{PlayerRig, SceneIndex, door_label, poi_label};
use crate::theme::{HudRects, Ty, tok, z};
use crate::uikit::{self, UiIcon, UiKit, ik};
use crate::{ClientConfig, ClientSet};
use gf_core::poi::{PoiKind, PoiState};
use gf_core::revive::LifeState;
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::*;

/// Pool size: allies (3) + doors (3) + anvil + pings + the gate and three objectives.
const POOL: usize = 16;
/// Seal POIs still to do that get a pin (nearest first).
const OBJECTIVES: usize = 3;
/// Seconds a ping stays tracked.
const PING_LIFE: f32 = 5.0;
/// Pin centres sit this far inside the screen edge (UI px).
const MARGIN: f32 = 40.0;
/// Pins closer than this (px, per axis) to an earlier pin slide along their edge.
const SPREAD: Vec2 = Vec2::new(110.0, 58.0);

/// Recent pings (world position, slot, seconds left).
#[derive(Resource, Default)]
struct Pings(Vec<(Vec2, u8, f32)>);

/// One pooled pin and its motion state.
struct Pin {
    root: Entity,
    glyph: Entity,
    gilt: Entity,
    tint: Entity,
    inner: Entity,
    label: Entity,
    dist: Entity,
    name: Entity,
    key: Option<String>,
    pos: Vec2,
    age: f32,
}

#[derive(Resource, Default)]
struct PinPool(Vec<Pin>);

pub fn build(app: &mut App) {
    app.init_resource::<Pings>()
        .init_resource::<PinPool>()
        .add_systems(Startup, spawn_pool)
        .add_systems(Update, update_pins.in_set(ClientSet::Presentation));
}

fn spawn_pool(mut commands: Commands, kit: Res<UiKit>, mut pool: ResMut<PinPool>) {
    let kit = &*kit;
    commands.spawn((uikit::fill(), GlobalZIndex(z::PINS), Pickable::IGNORE)).with_children(|c| {
        for _ in 0..POOL {
            let ph = Entity::PLACEHOLDER;
            let mut p = Pin {
                root: ph,
                glyph: ph,
                gilt: ph,
                tint: ph,
                inner: ph,
                label: ph,
                dist: ph,
                name: ph,
                key: None,
                pos: Vec2::ZERO,
                age: 0.0,
            };
            p.root = c
                .spawn((Node { display: Display::None, ..uikit::abs(0.0, 0.0, 34.0, 34.0) }, Pickable::IGNORE))
                .with_children(|r| {
                    r.spawn((uikit::fill(), kit.tex("markers/pin_disc@2x.png"), Pickable::IGNORE));
                    p.inner = r
                        .spawn((
                            Node {
                                border: UiRect::all(px(1.5)),
                                border_radius: BorderRadius::MAX,
                                display: Display::None,
                                ..uikit::inset(3.0)
                            },
                            BorderColor::all(tok::DANGER_WHITE),
                            Pickable::IGNORE,
                        ))
                        .id();
                    p.glyph =
                        r.spawn((uikit::centered(24.0, 24.0), uikit::icon_bundle("poi/gate", 24.0, tok::BONE))).id();
                    p.gilt = r
                        .spawn((
                            uikit::centered(56.0, 56.0),
                            kit.tex("markers/pin_frame_gilt@2x.png"),
                            UiTransform::default(),
                            Pickable::IGNORE,
                        ))
                        .id();
                    p.tint = r
                        .spawn((
                            Node { display: Display::None, ..uikit::centered(56.0, 56.0) },
                            kit.tex_tinted("markers/pin_frame_tint@2x.png", Color::WHITE),
                            UiTransform::default(),
                            Pickable::IGNORE,
                        ))
                        .id();
                    p.label = r
                        .spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                flex_direction: FlexDirection::Column,
                                ..default()
                            },
                            Pickable::IGNORE,
                        ))
                        .with_children(|l| {
                            p.dist = l.spawn(kit.text_px(Ty::Num, 14.0, "", tok::PARCH)).id();
                            p.name = l.spawn(kit.text_px(Ty::BodyS, 14.0, "", tok::PARCH_DIM)).id();
                        })
                        .id();
                })
                .id();
            pool.0.push(p);
        }
    });
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

/// Slide a pin along its edge to the nearest spot outside every HUD rect and clear of the pins
/// already placed (alternating either way in 12 px steps).
fn place_on_edge(ideal: Vec2, size: Vec2, rects: &HudRects, placed: &[Vec2]) -> Vec2 {
    let along_x = ideal.y <= MARGIN + 1.0 || ideal.y >= size.y - MARGIN - 1.0;
    let free = |q: Vec2| {
        q.x >= MARGIN - 1.0
            && q.x <= size.x - MARGIN + 1.0
            && q.y >= MARGIN - 1.0
            && q.y <= size.y - MARGIN + 1.0
            && !rects.rects.iter().any(|r| r.inflate(26.0).contains(q))
            && !placed.iter().any(|p| (p.x - q.x).abs() < SPREAD.x && (p.y - q.y).abs() < SPREAD.y)
    };
    let step = if along_x { Vec2::new(12.0, 0.0) } else { Vec2::new(0.0, 12.0) };
    for k in 0..160 {
        for sign in [1.0, -1.0] {
            let q = ideal + step * k as f32 * sign;
            if free(q) {
                return q;
            }
            if k == 0 {
                break;
            }
        }
    }
    ideal
}

/// What a pin shows.
struct Target {
    at: Vec3,
    key: String,
    glyph: String,
    glyph_tint: Color,
    ring: Option<Color>,
    downed: bool,
    name: String,
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn update_pins(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    index: Res<SceneIndex>,
    rects: Res<HudRects>,
    scale: Res<UiScale>,
    mut pings: ResMut<Pings>,
    mut pool: ResMut<PinPool>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    rigs: Query<&PlayerRig>,
    (mut nodes, mut images, mut icons, mut tfs, mut texts, mut borders): (
        Query<&mut Node>,
        Query<&mut ImageNode>,
        Query<&mut UiIcon>,
        Query<&mut UiTransform>,
        Query<(&mut Text, &mut TextColor)>,
        Query<&mut BorderColor>,
    ),
) {
    let dt = time.delta_secs();
    let now = time.elapsed_secs();
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
    let s = scale.0;
    let Some(size) = ui_viewport(camera, s) else { return };
    let db = &cfg.content;
    let me = link.me().map(|p| p.mover.pos);
    let pos = |slot: u8, fallback: Vec2| {
        index.players[slot as usize].and_then(|e| rigs.get(e).ok()).map_or(fallback, |r| r.shown)
    };
    let pc = |slot: u8| crate::theme::player_color(db, slot as usize);

    // Targets in priority order.
    let mut downed = Vec::new();
    let mut gate_open = Vec::new();
    let mut shared = Vec::new();
    let mut allies = Vec::new();
    let mut pinged = Vec::new();
    let mut todo: Vec<(f32, Target)> = Vec::new();
    for p in &world.players {
        if Some(p.slot) == link.slot {
            continue;
        }
        let at = pos(p.slot, p.mover.pos);
        let name = player_name(&link, p.slot);
        match p.life {
            LifeState::Downed { remaining, .. } => downed.push(Target {
                at: w3(at, 1.0),
                key: format!("down{}", p.slot),
                glyph: "states/downed".into(),
                glyph_tint: tok::DANGER_WHITE,
                ring: Some(tok::DANGER),
                downed: true,
                name: format!("{name} · revive · {:.0} s", remaining.ceil()),
            }),
            _ => {
                let ch = db.characters.try_get(p.character).map_or("valdris".to_string(), |c| c.key.clone());
                allies.push(Target {
                    at: w3(at, 1.0),
                    key: format!("ally{}", p.slot),
                    glyph: ik::portrait(&ch),
                    glyph_tint: Color::WHITE,
                    ring: Some(pc(p.slot)),
                    downed: false,
                    name,
                });
            }
        }
    }
    for (i, (at, slot, _)) in pings.0.iter().enumerate() {
        pinged.push(Target {
            at: w3(*at, 0.5),
            key: format!("ping{i}"),
            glyph: "team/ping".into(),
            glyph_tint: pc(*slot),
            ring: Some(pc(*slot)),
            downed: false,
            name: format!("{}'s ping", player_name(&link, *slot)),
        });
    }
    for e in &world.entities {
        match e.kind {
            EntityKind::Door { reward, index } => todo.push((
                me.map_or(0.0, |m| m.distance(e.pos.to_vec2())) - 1000.0,
                Target {
                    at: w3(e.pos.to_vec2(), 1.5),
                    key: format!("door{index}"),
                    glyph: "run/gate_open".into(),
                    glyph_tint: tok::BONE,
                    ring: None,
                    downed: false,
                    name: door_label(db, reward),
                },
            )),
            EntityKind::Anvil if AnvilState::from_u8(e.status) != AnvilState::Spent => todo.push((
                -2000.0,
                Target {
                    at: w3(e.pos.to_vec2(), 1.0),
                    key: "anvil".into(),
                    glyph: "poi/anvil".into(),
                    glyph_tint: tok::BONE,
                    ring: None,
                    downed: false,
                    name: "Anvil".into(),
                },
            )),
            _ => {}
        }
    }
    if let Some(map) = room.def.map.as_deref() {
        let from = me.unwrap_or(room.def.player_spawn);
        for e in &world.entities {
            let EntityKind::Poi { index } = e.kind else { continue };
            let Some(site) = map.pois.get(index as usize) else { continue };
            let state = PoiState::from_u8(e.status);
            if state == PoiState::Done {
                continue;
            }
            let tint = crate::hud::poi_glyph_tint(db, site);
            let label = poi_label(db, site);
            let base = Target {
                at: w3(site.at, 1.0),
                key: format!("poi{index}"),
                glyph: ik::poi(site.kind),
                glyph_tint: tint,
                ring: None,
                downed: false,
                name: label.clone(),
            };
            if site.kind == PoiKind::Gate {
                if matches!(state, PoiState::Open | PoiState::Gathering) {
                    gate_open.push(Target {
                        glyph: "run/gate_open".into(),
                        glyph_tint: tok::GOLD_LT,
                        name: "Boss Gate · open".into(),
                        ..base
                    });
                } else {
                    let name = world.run.stage.map_or(label, |st| format!("Boss Gate · {}/{}", st.seals, st.required));
                    todo.push((-500.0, Target { name, ..base }));
                }
                continue;
            }
            // A live POI with an ally at it: "P2 · Anvil 45%".
            let live = matches!(state, PoiState::Active | PoiState::Hot);
            let ally = world
                .players
                .iter()
                .filter(|p| Some(p.slot) != link.slot)
                .find(|p| p.mover.pos.distance(site.at) <= site.radius + 1.0);
            if live && let Some(a) = ally {
                let pct = gf_net::quant::u8_to_frac(e.hp) * 100.0;
                shared.push(Target { name: format!("P{} · {label} {pct:.0}%", a.slot + 1), ..base });
                continue;
            }
            if site.seals > 0 {
                todo.push((site.at.distance(from), base));
            }
        }
    }
    todo.sort_by(|a, b| a.0.total_cmp(&b.0));
    let mut n_poi = 0;
    let objectives: Vec<Target> = todo
        .into_iter()
        .filter(|(d, _)| {
            // Doors, the anvil and the sealed gate always; then the three nearest objectives.
            if *d < 0.0 {
                return true;
            }
            n_poi += 1;
            n_poi <= OBJECTIVES
        })
        .map(|(_, t)| t)
        .collect();
    let targets = downed.into_iter().chain(gate_open).chain(shared).chain(allies).chain(pinged).chain(objectives);

    // Place: edge pin, off the HUD rects, and off earlier pins along the edge.
    let mut placed: Vec<(Vec2, f32, Target, Option<f32>)> = Vec::new();
    for t in targets {
        let Some(screen) = to_ui(camera, cam_tf, t.at, s) else { continue };
        let Some((pin, angle)) = edge_pin(screen, size, MARGIN) else { continue };
        let taken: Vec<Vec2> = placed.iter().map(|p| p.0).collect();
        let pin = place_on_edge(pin, size, &rects, &taken);
        // Re-aim the nub from where the pin ended up.
        let angle = {
            let d = screen - pin;
            if d.length_squared() > 1.0 { d.x.atan2(-d.y) } else { angle }
        };
        let dist = me.map(|m| m.distance(Vec2::new(t.at.x, -t.at.z)));
        placed.push((pin, angle, t, dist));
    }

    let mut it = placed.into_iter().enumerate();
    let pulse = 0.55 + 0.45 * (now * std::f32::consts::TAU / 0.8).sin().abs();
    for p in pool.0.iter_mut() {
        let Some((rank, (target_pos, angle, t, dist))) = it.next() else {
            if let Ok(mut n) = nodes.get_mut(p.root)
                && n.display != Display::None
            {
                n.display = Display::None;
            }
            p.key = None;
            continue;
        };
        // A new target snaps and fades in; the same one slides (critically damped, ~12 Hz).
        if p.key.as_deref() != Some(t.key.as_str()) {
            p.key = Some(t.key.clone());
            p.pos = target_pos;
            p.age = 0.0;
        } else {
            p.pos += (target_pos - p.pos) * (1.0 - (-dt * 12.0).exp());
            p.age += dt;
        }
        let a = (p.age / 0.15).min(1.0);
        if let Ok(mut n) = nodes.get_mut(p.root) {
            n.display = Display::Flex;
            let (l, top) = (Val::Px((p.pos.x - 17.0).round()), Val::Px((p.pos.y - 17.0).round()));
            if n.left != l {
                n.left = l;
            }
            if n.top != top {
                n.top = top;
            }
        }
        if let Ok(mut i) = icons.get_mut(p.glyph)
            && i.key != t.glyph
        {
            i.key = t.glyph.clone();
        }
        let set_tint = |images: &mut Query<&mut ImageNode>, e: Entity, c: Color| {
            if let Ok(mut i) = images.get_mut(e)
                && i.color != c
            {
                i.color = c;
            }
        };
        set_tint(&mut images, p.glyph, t.glyph_tint.with_alpha(a));
        let show = |nodes: &mut Query<&mut Node>, e: Entity, on: bool| {
            if let Ok(mut n) = nodes.get_mut(e) {
                let d = if on { Display::Flex } else { Display::None };
                if n.display != d {
                    n.display = d;
                }
            }
        };
        show(&mut nodes, p.gilt, t.ring.is_none());
        show(&mut nodes, p.tint, t.ring.is_some());
        show(&mut nodes, p.inner, t.downed);
        set_tint(&mut images, p.gilt, Color::WHITE.with_alpha(a));
        if let Some(ring) = t.ring {
            set_tint(&mut images, p.tint, ring.with_alpha(a * if t.downed { pulse } else { 1.0 }));
        }
        if t.downed
            && let Ok(mut b) = borders.get_mut(p.inner)
        {
            *b = BorderColor::all(tok::DANGER_WHITE.with_alpha(a * pulse));
        }
        for e in [p.gilt, p.tint] {
            if let Ok(mut tf) = tfs.get_mut(e)
                && (tf.rotation.as_radians() - angle).abs() > 1e-3
            {
                tf.rotation = Rot2::radians(angle);
            }
        }
        // The label hangs 30 px inward: right of a left-edge pin, left of a right-edge pin,
        // under a top-edge pin, over a bottom-edge pin.
        let (left, right, top, bottom, align) = if p.pos.x <= MARGIN + 1.0 {
            (Val::Px(34.0 + 12.0), Val::Auto, Val::Px(0.0), Val::Auto, AlignItems::FlexStart)
        } else if p.pos.x >= size.x - MARGIN - 1.0 {
            (Val::Auto, Val::Px(34.0 + 12.0), Val::Px(0.0), Val::Auto, AlignItems::FlexEnd)
        } else if p.pos.y <= size.y * 0.5 {
            (Val::Px(-40.0), Val::Auto, Val::Px(34.0 + 8.0), Val::Auto, AlignItems::Center)
        } else {
            (Val::Px(-40.0), Val::Auto, Val::Auto, Val::Px(34.0 + 8.0), AlignItems::Center)
        };
        if let Ok(mut n) = nodes.get_mut(p.label)
            && (n.left, n.right, n.top, n.bottom, n.align_items) != (left, right, top, bottom, align)
        {
            n.left = left;
            n.right = right;
            n.top = top;
            n.bottom = bottom;
            n.align_items = align;
            n.width = if align == AlignItems::Center { px(114.0) } else { Val::Auto };
        }
        let d = dist.map_or(String::new(), |d| format!("{d:.0} m"));
        if let Ok((mut tx, mut c)) = texts.get_mut(p.dist) {
            if tx.0 != d {
                tx.0 = d;
            }
            c.0 = if t.downed { tok::DANGER_WHITE.with_alpha(a) } else { tok::PARCH.with_alpha(a) };
        }
        // Names only for the top three priorities.
        let name = if rank < 3 { t.name.clone() } else { String::new() };
        if let Ok((mut tx, mut c)) = texts.get_mut(p.name) {
            if tx.0 != name {
                tx.0 = name;
            }
            c.0 = tok::PARCH_DIM.with_alpha(a);
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
