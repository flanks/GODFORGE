//! World-anchored UI (UI_STYLE §6.11): the one prompt plate at the nearest interactable, the
//! personal state banner under the hero, ally tags, elite bars, POI labels and downed markers;
//! and the touch overlay (§6.15). Everything projects world → UI px and keeps out of `HudRects`.

use super::wayfinder::poi_tint;
use super::{FadeGroup, HudFocus, Ui, View, db, drawer_open, player_name};
use crate::ClientConfig;
use crate::input::{Device, InputState};
use crate::net::{CurrentRoom, Link};
use crate::scene::{PlayerRig, SceneIndex, Visual, door_label, poi_label};
use crate::theme::{HudRects, Ty, hx, player_color, region, tok, z};
use crate::uikit::{self, AllyTagParts, BarFill, BarSpec, Key, RingStyle, SlotShape, SlotSpec, SlotState, UiKit, ik};
use gf_core::poi::{PoiKind, PoiState};
use gf_core::revive::LifeState;
use gf_engine::client::Pickable;
use gf_engine::prelude::*;
use gf_net::{AnvilState, DoorReward, EntityFlags, EntityKind, GateView, RunPhase};

const TAGS: usize = 3;
const ELITES: usize = 16;
const LABELS: usize = 6;
const DOWNED: usize = 3;

/// What the prompt plate says. Rebuilt only when this changes.
#[derive(Clone, Debug, PartialEq)]
struct PromptSpec {
    key: Option<PromptKey>,
    verb: String,
    subject: String,
    ring: Option<Color>,
    pause: bool,
    scale: f32,
    verb_color: Color,
}

#[derive(Clone, Debug, PartialEq)]
enum PromptKey {
    Interact,
    Forge,
    Icon(&'static str),
}

struct Plate {
    root: Entity,
    body: Entity,
    spec: Option<PromptSpec>,
    ring: Option<Entity>,
    t: f32,
}

struct Label {
    root: Entity,
    glyph: Entity,
    name: Entity,
    line: Entity,
}

struct Marker {
    root: Entity,
    ring: Entity,
    secs: Entity,
}

struct Touch {
    root: Entity,
    slot: Entity,
    which: u8,
}

#[derive(Resource)]
pub(super) struct WorldUi {
    prompt: Plate,
    state: Plate,
    tags_box: Entity,
    tags: Vec<(u8, Entity, Entity)>,
    tags_key: Vec<(u8, String)>,
    elites: Vec<(Entity, Entity)>,
    labels: Vec<Label>,
    markers: Vec<Marker>,
    touch: Vec<Touch>,
    touch_key: Option<u16>,
    sticks: [Entity; 2],
    /// Where the prompt plate points (UI px): the POI label there steps aside for it.
    prompt_at: Option<Vec2>,
}

fn plate_root(commands: &mut Commands) -> Plate {
    let mut body = Entity::PLACEHOLDER;
    let root = commands
        .spawn((
            Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
            GlobalZIndex(z::WORLD + 1),
            UiTransform::default(),
            Pickable::IGNORE,
        ))
        .with_children(|c| {
            body = c.spawn((Node::default(), FadeGroup::new(0.0), Pickable::IGNORE)).id();
        })
        .id();
    Plate { root, body, spec: None, ring: None, t: 0.0 }
}

pub(super) fn spawn(mut commands: Commands, kit: Res<UiKit>) {
    let kit = &*kit;
    let prompt = plate_root(&mut commands);
    let state = plate_root(&mut commands);
    let tags_box = commands.spawn((uikit::fill(), GlobalZIndex(z::WORLD), Pickable::IGNORE)).id();
    let mut elites = Vec::new();
    let mut labels = Vec::new();
    let mut markers = Vec::new();
    commands.spawn((uikit::fill(), GlobalZIndex(z::WORLD), Pickable::IGNORE)).with_children(|c| {
        for _ in 0..ELITES {
            let mut bar = Entity::PLACEHOLDER;
            let root = c
                .spawn((
                    Node { display: Display::None, padding: UiRect::left(px(6.0)), ..uikit::abs(0.0, 0.0, 60.0, 8.0) },
                    Pickable::IGNORE,
                ))
                .with_children(|b| {
                    bar =
                        uikit::bar(b, kit, BarSpec { edge: false, ..BarSpec::new(54.0, 6.0, BarFill::Elite).no_rim() });
                    // The elite crown tick: a small danger gem at the bar's left end.
                    b.spawn((
                        uikit::abs(-1.0, -2.0, 9.0, 9.0),
                        kit.tex_tinted("ornaments/gem_white@2x.png", tok::DANGER),
                        Pickable::IGNORE,
                    ));
                })
                .id();
            elites.push((root, bar));
        }
        for _ in 0..LABELS {
            let mut l = Label {
                root: Entity::PLACEHOLDER,
                glyph: Entity::PLACEHOLDER,
                name: Entity::PLACEHOLDER,
                line: Entity::PLACEHOLDER,
            };
            l.root = c
                .spawn((
                    Node {
                        display: Display::None,
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        column_gap: px(7.0),
                        ..uikit::abs(0.0, 0.0, 360.0, 40.0)
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|r| {
                    l.glyph = r
                        .spawn((
                            Node { width: px(28.0), height: px(28.0), ..default() },
                            uikit::icon_bundle("poi/anvil", 28.0, tok::BONE),
                        ))
                        .id();
                    r.spawn((uikit::column(0.0), Pickable::IGNORE)).with_children(|t| {
                        l.name = t
                            .spawn(kit.text_tracked(Ty::LabelS, 15.0, 0.12, "", tok::PARCH))
                            .insert(crate::theme::ink_shadow())
                            .id();
                        l.line = t.spawn(kit.text_px(Ty::BodyS, 16.0, "", tok::PARCH_DIM)).id();
                    });
                })
                .id();
            labels.push(l);
        }
        for _ in 0..DOWNED {
            let mut m = Marker { root: Entity::PLACEHOLDER, ring: Entity::PLACEHOLDER, secs: Entity::PLACEHOLDER };
            m.root = c
                .spawn((
                    Node {
                        display: Display::None,
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        ..uikit::abs(0.0, 0.0, 60.0, 72.0)
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|d| {
                    d.spawn((
                        Node {
                            width: px(44.0),
                            height: px(44.0),
                            border: UiRect::all(px(3.0)),
                            border_radius: BorderRadius::MAX,
                            ..default()
                        },
                        BackgroundColor(hx(0x1A0806).with_alpha(0.85)),
                        BorderColor::all(hx(0x5A1410)),
                        uikit::glow(tok::DANGER.with_alpha(0.5), 10.0, 0.0),
                        Pickable::IGNORE,
                    ))
                    .with_children(|disc| {
                        m.ring = uikit::ring_meter(
                            disc,
                            uikit::centered(44.0, 44.0),
                            3.0,
                            RingStyle::Tint(tok::DANGER_WHITE),
                            1.0,
                        );
                        disc.spawn((
                            uikit::centered(26.0, 26.0),
                            uikit::icon_bundle("states/tether", 26.0, tok::DANGER_WHITE),
                        ));
                    });
                    m.secs = d.spawn(kit.text_px(Ty::Alert, 18.0, "", tok::DANGER_WHITE)).id();
                })
                .id();
            markers.push(m);
        }
    });

    // The touch overlay: 72 px medallion buttons with the cooldown language, and stick rings.
    let mut touch = Vec::new();
    let mut sticks = [Entity::PLACEHOLDER; 2];
    commands.spawn((uikit::fill(), GlobalZIndex(z::HUD + 1), Pickable::IGNORE)).with_children(|c| {
        for (zone, which) in super::TOUCH_BUTTONS {
            let mut slot = Entity::PLACEHOLDER;
            let root = c
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: percent(zone.x * 100.0),
                        top: percent(zone.y * 100.0),
                        width: px(72.0),
                        height: px(72.0),
                        margin: UiRect { left: px(-36.0), top: px(-36.0), ..default() },
                        display: Display::None,
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|b| {
                    slot = uikit::slot(
                        b,
                        kit,
                        SlotSpec::new(SlotShape::Round, 72.0).icon("ui/confirm").icon_frac(0.6).glow(true),
                    );
                })
                .id();
            touch.push(Touch { root, slot, which });
        }
        for s in &mut sticks {
            *s = c
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        width: px(120.0),
                        height: px(120.0),
                        border: UiRect::all(px(1.5)),
                        border_radius: BorderRadius::MAX,
                        display: Display::None,
                        ..default()
                    },
                    BorderColor::all(tok::GOLD_LT.with_alpha(0.4)),
                    Pickable::IGNORE,
                ))
                .id();
        }
    });
    commands.insert_resource(WorldUi {
        prompt,
        state,
        tags_box,
        tags: Vec::new(),
        tags_key: Vec::new(),
        elites,
        labels,
        markers,
        touch,
        touch_key: None,
        sticks,
        prompt_at: None,
    });
}

// ───────────────────────────── prompts ─────────────────────────────

fn build_plate(c: &mut ChildSpawnerCommands, kit: &UiKit, spec: &PromptSpec, pad: bool) -> Option<Entity> {
    let mut ring = None;
    let plate = uikit::quiet_plate(
        c,
        Node {
            height: px(44.0),
            padding: UiRect { left: px(10.0), right: px(16.0), ..default() },
            align_items: AlignItems::Center,
            column_gap: px(10.0),
            flex_shrink: 0.0,
            ..default()
        },
        0.8,
        |p| {
            if spec.key.is_some() || spec.ring.is_some() || spec.pause {
                p.spawn((
                    Node {
                        width: px(30.0),
                        height: px(30.0),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    Pickable::IGNORE,
                ))
                .with_children(|k| {
                    if let Some(col) = spec.ring {
                        ring = Some(uikit::ring_meter(k, uikit::centered(30.0, 30.0), 2.5, RingStyle::Tint(col), 0.0));
                    }
                    match &spec.key {
                        Some(PromptKey::Interact) => {
                            if pad {
                                uikit::key_chip(k, kit, Key::Icon("input/pad_west"), 18.0);
                            } else {
                                uikit::keycap(k, kit, "F", 20.0);
                            }
                        }
                        Some(PromptKey::Forge) => {
                            if pad {
                                uikit::key_chip(k, kit, Key::Icon("input/pad_view"), 18.0);
                            } else {
                                uikit::keycap(k, kit, "Tab", 20.0);
                            }
                        }
                        Some(PromptKey::Icon(key)) => {
                            uikit::icon(k, key, 20.0, tok::GOLD_LT);
                        }
                        None if spec.pause => {
                            uikit::icon(k, "ui/pause", 18.0, tok::PARCH_MUTE);
                        }
                        None => {}
                    }
                });
            }
            p.spawn((uikit::column(0.0), Pickable::IGNORE)).with_children(|t| {
                t.spawn(kit.text_tracked(Ty::LabelS, 16.0, 0.08, spec.verb.to_uppercase(), spec.verb_color));
                if !spec.subject.is_empty() {
                    t.spawn(kit.text_flat(Ty::BodyS, 14.0, spec.subject.as_str(), tok::PARCH_DIM));
                }
            });
        },
    );
    c.commands_mut().entity(plate).with_children(|p| {
        p.spawn((
            Node {
                position_type: PositionType::Absolute,
                left: percent(50.0),
                bottom: px(-8.0),
                width: px(14.0),
                height: px(9.0),
                margin: UiRect::left(px(-7.0)),
                ..default()
            },
            kit.tex("markers/prompt_tail@2x.png"),
            Pickable::IGNORE,
        ));
    });
    ring
}

/// Keep a plate of `size` centred at `p` (bottom at p.y) out of the HUD rects and the south lane.
fn clear_of_hud(mut p: Vec2, size: Vec2, rects: &HudRects, view_size: Vec2) -> Vec2 {
    let south = Rect::new(
        view_size.x / 2.0 - (region::SOUTH_LANE[2] - region::SOUTH_LANE[0]) / 2.0,
        view_size.y - (region::SOUTH_LANE[3] - region::SOUTH_LANE[1]),
        view_size.x / 2.0 + (region::SOUTH_LANE[2] - region::SOUTH_LANE[0]) / 2.0,
        view_size.y,
    );
    for _ in 0..40 {
        let r = Rect::from_corners(Vec2::new(p.x - size.x / 2.0, p.y - size.y), Vec2::new(p.x + size.x / 2.0, p.y));
        let hit = rects.rects.iter().chain(std::iter::once(&south)).any(|h| !h.inflate(6.0).intersect(r).is_empty());
        if !hit {
            break;
        }
        p.y -= 16.0;
    }
    p.x = p.x.clamp(size.x / 2.0 + 8.0, view_size.x - size.x / 2.0 - 8.0);
    p.y = p.y.max(size.y + 8.0);
    p
}

/// Run one plate: rebuild on a new spec, fade over 120 ms, and place it.
#[allow(clippy::too_many_arguments)]
fn run_plate(
    commands: &mut Commands,
    kit: &UiKit,
    ui: &mut Ui,
    plate: &mut Plate,
    want: Option<(PromptSpec, Vec2, f32)>,
    pad: bool,
    dt: f32,
    rects: &HudRects,
    view_size: Vec2,
    bottom_anchor: bool,
) {
    match want {
        Some((spec, at, ring_value)) => {
            if plate.spec.as_ref() != Some(&spec) {
                let fresh = plate.spec.is_none();
                let body = plate.body;
                commands.entity(body).despawn_children();
                commands.entity(body).insert(FadeGroup::new(if fresh { 0.0 } else { 1.0 }));
                let mut ring = None;
                commands.entity(body).with_children(|c| ring = build_plate(c, kit, &spec, pad));
                plate.ring = ring;
                if fresh {
                    plate.t = 0.0;
                }
                ui.transform(plate.root, Vec2::ZERO, spec.scale);
                plate.spec = Some(spec);
            }
            plate.t += dt;
            if let Some(r) = plate.ring {
                ui.ring(r, ring_value, ring_value >= 1.0);
            }
            ui.show(plate.root, true);
            ui.fade(plate.body, (plate.t / 0.12).min(1.0));
            let size = ui.size(plate.root).max(Vec2::new(120.0, 44.0));
            let scale = plate.spec.as_ref().map_or(1.0, |s| s.scale);
            let (x, y) = if bottom_anchor {
                let p = clear_of_hud(at, size * scale, rects, view_size);
                (p.x - size.x / 2.0, p.y - size.y)
            } else {
                (at.x - size.x / 2.0, at.y)
            };
            ui.place(plate.root, x, y);
        }
        None => {
            if plate.spec.is_some() {
                plate.spec = None;
            }
            ui.show(plate.root, false);
        }
    }
}

fn spec(key: Option<PromptKey>, verb: &str, subject: impl Into<String>) -> PromptSpec {
    PromptSpec {
        key,
        verb: verb.to_string(),
        subject: subject.into(),
        ring: None,
        pause: false,
        scale: 1.0,
        verb_color: tok::GOLD_LT,
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn prompts(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    input: Res<InputState>,
    focus: Res<HudFocus>,
    rects: Res<HudRects>,
    kit: Res<UiKit>,
    index: Res<SceneIndex>,
    rigs: Query<&PlayerRig>,
    view: View,
    mut w: ResMut<WorldUi>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let dt = time.delta_secs();
    let pad = input.device == Device::Gamepad;
    let Some(view_size) = view.size() else { return };
    let (Some(world), Some(me)) = (link.latest.as_deref(), link.me()) else {
        run_plate(&mut commands, &kit, &mut ui, &mut w.prompt, None, pad, dt, &rects, view_size, true);
        run_plate(&mut commands, &kit, &mut ui, &mut w.state, None, pad, dt, &rects, view_size, false);
        return;
    };
    let pos = |slot: u8, fallback: Vec2| {
        index.players[slot as usize].and_then(|e| rigs.get(e).ok()).map_or(fallback, |r| r.shown)
    };
    let here = pos(me.slot, me.mover.pos);

    // The personal state banner: 1.2 scale, 120 px under the hero, with a timer ring.
    let revive = &db.game.revive;
    let state = match me.life {
        LifeState::Downed { remaining, .. } => Some((
            PromptSpec {
                key: None,
                verb: "DOWNED".into(),
                subject: if world.private.hopeless {
                    "no ally in reach · the Forge will remake you".into()
                } else {
                    "allies can revive you".into()
                },
                ring: Some(tok::DANGER_WHITE),
                pause: false,
                scale: 1.2,
                verb_color: tok::DANGER_WHITE,
            },
            remaining / revive.downed_duration.max(0.1),
        )),
        LifeState::Reforging { remaining } => Some((
            PromptSpec {
                key: None,
                verb: if world.private.rekindles > 0 && world.players.len() == 1 {
                    "REKINDLE".into()
                } else {
                    "REFORGING".into()
                },
                subject: format!("the Forge remakes you · {:.0} s", remaining.ceil()),
                ring: Some(tok::GOLD_LT),
                pause: false,
                scale: 1.2,
                verb_color: tok::GOLD_LT,
            },
            1.0 - remaining / revive.reforge_delay.max(0.1),
        )),
        LifeState::Alive => None,
    };
    let hero = view.project(crate::camera::w3(here, 0.0));
    let state_want = state.zip(hero).map(|((s, v), h)| (s, h + Vec2::new(0.0, 120.0), v));
    run_plate(&mut commands, &kit, &mut ui, &mut w.state, state_want, pad, dt, &rects, view_size, false);

    // The one prompt: the nearest valid interactable.
    let mut best: Option<(f32, PromptSpec, Vec3, f32)> = None;
    let mut offer = |d: f32, s: PromptSpec, at: Vec3, v: f32| {
        if best.as_ref().is_none_or(|b| d < b.0) {
            best = Some((d, s, at, v));
        }
    };
    let alive = me.life.is_alive();
    let drawer = drawer_open(&focus, &input);
    // Legacy anvils (rooms) and the map anvil I am tied to.
    if alive && let Some(a) = world.private.anvil {
        let at = world.entities.iter().find(|e| e.id == a.id).map(|e| e.pos.to_vec2());
        if let Some(at) = at {
            let d = here.distance(at);
            let seals = room.def.map.as_deref().and_then(|m| {
                world.entities.iter().find(|e| e.id == a.id).and_then(|e| match e.kind {
                    EntityKind::Poi { index } => m.pois.get(index as usize).map(|s| s.seals),
                    _ => None,
                })
            });
            let near = d < 7.5;
            match a.state {
                AnvilState::Dormant if near => {
                    let sub = match seals {
                        Some(n) if n > 0 => format!("Anvil · {n} Seal"),
                        _ => "Anvil".to_string(),
                    };
                    offer(d, spec(Some(PromptKey::Interact), "Kindle the anvil", sub), crate::camera::w3(at, 2.6), 0.0);
                }
                AnvilState::Kindling if near && a.contested => {
                    let mut s = spec(None, "Paused", "step inside the ring");
                    s.pause = true;
                    s.verb_color = tok::PARCH_MUTE;
                    offer(d, s, crate::camera::w3(at, 2.6), a.progress);
                }
                AnvilState::Kindling if near => {
                    let mut s = spec(None, "Hold the ring", format!("{:.0}%", a.progress * 100.0));
                    s.ring = Some(tok::GOLD_LT);
                    offer(d, s, crate::camera::w3(at, 2.6), a.progress);
                }
                AnvilState::Hot if world.private.at_anvil => {
                    let s = if drawer {
                        spec(None, "Forging", format!("hot for {:.0} s", a.time_left.ceil()))
                    } else {
                        spec(Some(PromptKey::Forge), "Forge", format!("hot for {:.0} s", a.time_left.ceil()))
                    };
                    offer(d, s, crate::camera::w3(at, 2.6), 0.0);
                }
                _ => {}
            }
        }
    }
    // Map POIs.
    if alive && let Some(map) = room.def.map.as_deref() {
        for e in &world.entities {
            let EntityKind::Poi { index } = e.kind else { continue };
            let Some(site) = map.pois.get(index as usize) else { continue };
            if site.kind == PoiKind::Anvil {
                continue;
            }
            let d = here.distance(site.at);
            if d > site.radius + 1.5 {
                continue;
            }
            let state = PoiState::from_u8(e.status);
            let progress = gf_net::quant::u8_to_frac(e.hp);
            let contested = e.flags.contains(EntityFlags::CONTESTED);
            let at = crate::camera::w3(site.at, 2.6);
            let name = poi_label(db, site);
            let ring = if site.kind == PoiKind::Shrine { poi_tint(db, site) } else { tok::GOLD_LT };
            let s = match (site.kind, state) {
                (PoiKind::Shrine | PoiKind::Reliquary | PoiKind::Vein | PoiKind::Watchfire, PoiState::Active)
                    if contested =>
                {
                    let mut s = spec(None, "Paused", "step inside the ring");
                    s.pause = true;
                    s.verb_color = tok::PARCH_MUTE;
                    Some(s)
                }
                (PoiKind::Shrine | PoiKind::Reliquary | PoiKind::Vein | PoiKind::Watchfire, PoiState::Active) => {
                    let mut s = spec(None, "Hold the ring", format!("{name} · {:.0}%", progress * 100.0));
                    s.ring = Some(ring);
                    Some(s)
                }
                (PoiKind::Shrine, PoiState::Dormant) => {
                    let mut s = spec(Some(PromptKey::Interact), "Pray", name);
                    s.ring = Some(ring);
                    Some(s)
                }
                (PoiKind::Reliquary, PoiState::Dormant) => {
                    Some(spec(Some(PromptKey::Interact), "Open the reliquary", "hold the ring · parts"))
                }
                (PoiKind::Vein, PoiState::Dormant) => {
                    Some(spec(Some(PromptKey::Interact), "Tap the vein", "hold the ring · shards for all"))
                }
                (PoiKind::Spring, s) if s != PoiState::Done => {
                    Some(spec(Some(PromptKey::Interact), "Drink", "heals 40 %, once"))
                }
                (PoiKind::Watchfire, PoiState::Dormant) => {
                    Some(spec(Some(PromptKey::Interact), "Light the watchfire", "reveals the land around it"))
                }
                (PoiKind::Gate, _) => match world.run.stage.map(|s| (s.gate, s.seals, s.required)) {
                    Some((GateView::Sealed, seals, req)) => {
                        let mut s = spec(None, "Sealed", format!("{seals}/{req} Seals"));
                        s.verb_color = tok::PARCH_MUTE;
                        Some(s)
                    }
                    Some((GateView::Open, ..)) => Some(spec(Some(PromptKey::Interact), "Gather", "the Boss Gate")),
                    Some((GateView::Gathering { left_ds }, ..)) => {
                        let mut s = spec(
                            Some(PromptKey::Icon("run/gathering")),
                            &format!("Gathering {:.0} s", (left_ds as f32 / 10.0).ceil()),
                            "every hero inside the ring",
                        );
                        s.verb_color = tok::ICHOR;
                        Some(s)
                    }
                    None => None,
                },
                _ => None,
            };
            if let Some(s) = s {
                offer(d, s, at, progress);
            }
        }
    }
    // A downed ally in tether range: stay close to revive.
    for p in &world.players {
        if Some(p.slot) == link.slot || !alive {
            continue;
        }
        if let LifeState::Downed { progress, .. } = p.life {
            let ap = pos(p.slot, p.mover.pos);
            let d = here.distance(ap);
            if d < revive.tether_range + 2.0 {
                let mut s = spec(
                    Some(PromptKey::Icon("states/tether")),
                    "Revive",
                    format!("stay close · {}", player_name(&link, p.slot)),
                );
                s.ring = Some(tok::GOLD_LT);
                offer(d - 100.0, s, crate::camera::w3(ap, 3.6), progress / revive.revive_time.max(0.1));
            }
        }
    }
    // Legacy doors once the room is cleared.
    if alive && world.run.phase == RunPhase::Cleared {
        for e in &world.entities {
            if let EntityKind::Door { reward, .. } = e.kind {
                let d = here.distance(e.pos.to_vec2());
                if d < 2.4 {
                    offer(
                        d,
                        spec(Some(PromptKey::Interact), "Take the door", door_label(db, reward)),
                        crate::camera::w3(e.pos.to_vec2(), 4.0),
                        0.0,
                    );
                }
            }
        }
    }
    let want = best.and_then(|(_, s, at, v)| view.project(at).map(|p| (s, p, v)));
    w.prompt_at = want.as_ref().map(|(_, p, _)| *p);
    run_plate(&mut commands, &kit, &mut ui, &mut w.prompt, want, pad, dt, &rects, view_size, true);
}

// ───────────────────────────── ally tags and elite bars ─────────────────────────────

#[allow(clippy::too_many_arguments)]
pub(super) fn tags(
    mut commands: Commands,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    kit: Res<UiKit>,
    rects: Res<HudRects>,
    index: Res<SceneIndex>,
    rigs: Query<&PlayerRig>,
    visuals: Query<&Visual>,
    tag_parts: Query<&AllyTagParts>,
    view: View,
    mut w: ResMut<WorldUi>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let Some(world) = link.latest.as_deref() else { return };
    let others: Vec<_> = world.players.iter().filter(|p| Some(p.slot) != link.slot).take(TAGS).collect();
    let key: Vec<(u8, String)> = others.iter().map(|p| (p.slot, player_name(&link, p.slot))).collect();
    if key != w.tags_key {
        w.tags_key = key.clone();
        let bx = w.tags_box;
        commands.entity(bx).despawn_children();
        let mut tags = Vec::new();
        commands.entity(bx).with_children(|c| {
            for (slot, name) in &key {
                let mut tag = Entity::PLACEHOLDER;
                let root = c
                    .spawn((
                        Node {
                            display: Display::None,
                            justify_content: JustifyContent::Center,
                            align_items: AlignItems::FlexEnd,
                            ..uikit::abs(0.0, 0.0, 200.0, 40.0)
                        },
                        Pickable::IGNORE,
                    ))
                    .with_children(|t| {
                        tag = uikit::ally_tag(t, &kit, name, player_color(db, *slot as usize));
                    })
                    .id();
                tags.push((*slot, root, tag));
            }
        });
        w.tags = tags;
        return;
    }
    let pos = |slot: u8, fallback: Vec2| {
        index.players[slot as usize].and_then(|e| rigs.get(e).ok()).map_or(fallback, |r| r.shown)
    };
    let boss_band = Rect::new(0.0, 0.0, 99999.0, 160.0);
    let (view_w, view_h) = view.size().map_or((0.0, 0.0), |s| (s.x, s.y));
    let mut placed: Vec<Vec2> = Vec::new();
    for (slot, root, tag) in &w.tags {
        let Some(p) = world.players.iter().find(|p| p.slot == *slot) else {
            ui.show(*root, false);
            continue;
        };
        let at = view.project(crate::camera::w3(pos(p.slot, p.mover.pos), 2.4));
        let Some(mut s) = at else {
            ui.show(*root, false);
            continue;
        };
        // Tags that would overprint stack upward.
        for _ in 0..4 {
            if !placed.iter().any(|q| (q.y - s.y).abs() < 22.0 && (q.x - s.x).abs() < 70.0) {
                break;
            }
            s.y -= 24.0;
        }
        let hidden = rects.hits(s, 8.0) || boss_band.contains(s);
        ui.show(*root, !hidden);
        if hidden {
            continue;
        }
        placed.push(s);
        ui.place(*root, s.x - 100.0, s.y - 40.0);
        let frac = p.hp.max(0.0) / p.max_hp.max(1.0);
        if let Ok(parts) = tag_parts.get(*tag) {
            ui.bar(parts.bar, frac, p.shield / p.max_hp.max(1.0));
            ui.show(parts.capsule, frac < 0.6 || !p.life.is_alive());
        }
    }

    // Elite bars (bosses and the Warlord have none).
    let mut bars = w.elites.iter();
    for v in &visuals {
        if !matches!(v.kind, EntityKind::Enemy { .. })
            || !v.flags.contains(EntityFlags::ELITE)
            || v.flags.contains(EntityFlags::BOSS)
        {
            continue;
        }
        let Some(s) = view.project(crate::camera::w3(v.shown, v.lift + v.radius * 3.2 + 0.4)) else { continue };
        if rects.hits(s, 4.0) || s.x < 0.0 || s.y < 0.0 || s.x > view_w || s.y > view_h {
            continue;
        }
        let Some((root, bar)) = bars.next() else { break };
        ui.show(*root, true);
        ui.place(*root, s.x - 30.0, s.y);
        ui.bar(*bar, v.hp, 0.0);
    }
    for (root, _) in bars {
        ui.show(*root, false);
    }
}

// ───────────────────────────── POI labels and downed markers ─────────────────────────────

/// A POI's state line under its name.
fn poi_line(
    db: &gf_content::ContentDb,
    site: &gf_content::PoiSite,
    state: PoiState,
    progress: f32,
    stage: Option<gf_net::StageView>,
) -> String {
    let seals = match site.seals {
        0 => String::new(),
        1 => " · 1 Seal".to_string(),
        n => format!(" · {n} Seals"),
    };
    if state == PoiState::Done {
        return match site.kind {
            PoiKind::Anvil => "spent".into(),
            PoiKind::Watchfire => "lit".into(),
            _ => "done".into(),
        };
    }
    match (site.kind, state) {
        (PoiKind::Anvil, PoiState::Active) => format!("kindling · {:.0}%", progress * 100.0),
        (PoiKind::Anvil, PoiState::Hot) => "hot · forge now".into(),
        (PoiKind::Anvil, _) => format!("kindle it{seals}"),
        (PoiKind::Shrine, _) => {
            let god = site.god.and_then(|g| db.gods.try_get(g as u16)).map_or("a god".to_string(), |g| g.name.clone());
            format!("a boon of {god}{seals}")
        }
        (PoiKind::Reliquary, _) => format!("a cache of parts{seals}"),
        (PoiKind::Vein, _) => format!("godshards for all{seals}"),
        (PoiKind::Spring, _) => "heals 40 %, once".into(),
        (PoiKind::Watchfire, _) => "reveals the land".into(),
        (PoiKind::Lair, PoiState::Active) => format!("in battle · {:.0}%", progress * 100.0),
        (PoiKind::Lair, _) => format!("elites{seals}"),
        (PoiKind::Warlord, _) => format!("the Warlord{seals}"),
        (PoiKind::Gate, _) => match stage {
            Some(s) if s.gate == GateView::Sealed => format!("{}/{} Seals", s.seals, s.required),
            Some(_) => "open · gather".into(),
            None => String::new(),
        },
    }
}

/// The reward glyph of a legacy door.
fn door_icon(db: &gf_content::ContentDb, reward: DoorReward) -> (String, Color) {
    match reward {
        DoorReward::PartCache => ("slots/core".into(), tok::BONE),
        DoorReward::ShardCache => ("currency/godshard".into(), Color::WHITE),
        DoorReward::Anvil => ("poi/anvil".into(), tok::BONE),
        DoorReward::Healing => ("poi/spring".into(), tok::BONE),
        DoorReward::Boon { god } => match db.gods.try_get(god) {
            Some(g) => (
                ik::god(&g.key),
                crate::theme::god_colors(db, &g.key)
                    .map_or(tok::BONE, |(c, c2)| if matches!(g.key.as_str(), "pyra" | "umbra_rex") { c2 } else { c }),
            ),
            None => ("run/named_combo".into(), tok::BONE),
        },
        DoorReward::EliteChallenge => ("run/threat".into(), tok::THREAT[0]),
        DoorReward::Onward => ("run/gate_open".into(), tok::GOLD_LT),
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn markers(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    room: Res<CurrentRoom>,
    rects: Res<HudRects>,
    index: Res<SceneIndex>,
    rigs: Query<&PlayerRig>,
    view: View,
    w: Res<WorldUi>,
    mut ui: Ui,
) {
    let db = db(&cfg);
    let Some(world) = link.latest.as_deref() else { return };
    let Some(size) = view.size() else { return };
    let me = link.me().map(|p| p.mover.pos);
    // POI labels: the nearest on-screen POIs and doors, no box (a shadow and the world behind).
    let mut items: Vec<(f32, Vec2, String, Color, String, String)> = Vec::new();
    if let Some(map) = room.def.map.as_deref() {
        for e in &world.entities {
            let EntityKind::Poi { index } = e.kind else { continue };
            let Some(site) = map.pois.get(index as usize) else { continue };
            let state = PoiState::from_u8(e.status);
            let d = me.map_or(0.0, |m| m.distance(site.at));
            // Standing at it, the prompt plate speaks for it.
            if d < site.radius + 2.0 || d > 70.0 {
                continue;
            }
            let Some(s) = view.project(crate::camera::w3(site.at, 3.6)) else { continue };
            if s.x < 40.0 || s.y < 40.0 || s.x > size.x - 40.0 || s.y > size.y - 40.0 {
                continue;
            }
            let line = poi_line(db, site, state, gf_net::quant::u8_to_frac(e.hp), world.run.stage);
            let tint = if state == PoiState::Done { tok::PARCH_MUTE } else { poi_tint(db, site) };
            items.push((d, s, ik::poi(site.kind), tint, poi_label(db, site).to_uppercase(), line));
        }
    }
    for e in &world.entities {
        if let EntityKind::Door { reward, .. } = e.kind {
            let at = e.pos.to_vec2();
            let Some(s) = view.project(crate::camera::w3(at, 4.3)) else { continue };
            let (icon, tint) = door_icon(db, reward);
            let d = me.map_or(0.0, |m| m.distance(at));
            items.push((d, s, icon, tint, door_label(db, reward).to_uppercase(), String::new()));
        }
    }
    items.sort_by(|a, b| a.0.total_cmp(&b.0));
    // The label under the prompt plate steps aside: the plate already names it.
    let prompt_at = w.prompt_at;
    let mut it = items.into_iter().filter(|i| {
        !rects.hits(i.1, 20.0) && prompt_at.is_none_or(|p| (p.x - i.1.x).abs() > 160.0 || (p.y - i.1.y).abs() > 90.0)
    });
    for l in &w.labels {
        match it.next() {
            Some((_, s, icon, tint, name, line)) => {
                ui.show(l.root, true);
                ui.place(l.root, s.x - 180.0, s.y - 20.0);
                ui.icon(l.glyph, &icon);
                ui.tint(l.glyph, tint);
                ui.text(l.name, name);
                ui.show(l.line, !line.is_empty());
                ui.text(l.line, line);
            }
            None => ui.show(l.root, false),
        }
    }

    // Downed markers over downed allies: a white countdown on a danger ring.
    let revive = &db.game.revive;
    let pos = |slot: u8, fallback: Vec2| {
        index.players[slot as usize].and_then(|e| rigs.get(e).ok()).map_or(fallback, |r| r.shown)
    };
    let mut downed = world.players.iter().filter(|p| Some(p.slot) != link.slot).filter_map(|p| match p.life {
        LifeState::Downed { remaining, .. } => Some((pos(p.slot, p.mover.pos), remaining)),
        _ => None,
    });
    for m in &w.markers {
        match downed.next().and_then(|(at, rem)| view.project(crate::camera::w3(at, 3.2)).map(|s| (s, rem))) {
            Some((s, rem)) => {
                ui.show(m.root, true);
                ui.place(m.root, s.x - 30.0, s.y - 72.0);
                ui.ring(m.ring, rem / revive.downed_duration.max(0.1), false);
                ui.text(m.secs, format!("{:.0}", rem.ceil()));
            }
            None => ui.show(m.root, false),
        }
    }
}

// ───────────────────────────── touch ─────────────────────────────

pub(super) fn touch_overlay(
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    input: Res<InputState>,
    view: View,
    mut w: ResMut<WorldUi>,
    mut ui: Ui,
) {
    let on = input.device == Device::Touch;
    for t in &w.touch {
        ui.show(t.root, on);
    }
    let s = view.scale().max(0.01);
    for (i, stick) in w.sticks.iter().enumerate() {
        let st = if i == 1 { input.touch_aim } else { input.touch_move };
        match st {
            Some((origin, _)) if on => {
                ui.show(*stick, true);
                ui.place(*stick, origin.x / s - 60.0, origin.y / s - 60.0);
            }
            _ => ui.show(*stick, false),
        }
    }
    if !on {
        return;
    }
    let Some(me) = link.me() else { return };
    let key = db(&cfg).characters.try_get(me.character).map(|c| c.key.clone());
    if w.touch_key != Some(me.character) {
        w.touch_key = Some(me.character);
        for t in &w.touch {
            let icon = match (t.which, key.as_deref()) {
                (0, _) => "states/infinite_dash".to_string(),
                (1, Some(k)) => ik::kit(k, "q"),
                (2, Some(k)) => ik::kit(k, "e"),
                (3, Some(k)) => ik::kit(k, "r"),
                _ => "ui/confirm".to_string(),
            };
            ui.slot_icon(t.slot, Some(icon));
        }
    }
    let alive = me.life.is_alive();
    for t in &w.touch {
        let state = if !alive {
            SlotState::DISABLED
        } else {
            match t.which {
                0 if me.mover.dash_charges == 0 && me.dash_recharge > 0.0 => {
                    SlotState::cooling(me.mover.dash_recharge_left / me.dash_recharge, me.mover.dash_recharge_left)
                }
                1 | 2 if me.cooldowns[(t.which - 1) as usize] > 0.0 => {
                    let i = (t.which - 1) as usize;
                    SlotState::cooling(me.cooldowns[i] / me.cooldowns_max[i].max(0.01), me.cooldowns[i])
                }
                3 if me.ult < 1.0 => SlotState::cooling(1.0 - me.ult, 0.0),
                _ => SlotState::READY,
            }
        };
        ui.slot(t.slot, state);
    }
}
