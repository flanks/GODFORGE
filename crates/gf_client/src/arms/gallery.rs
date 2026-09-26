//! QA: `--weapon-gallery` fires every chassis in a labelled grid around the view centre, over a
//! live room, re-firing every [`CYCLE`] seconds: auto weapons shoot a burst of stand-in shots
//! (dressed exactly like replicated ones) that land in their hit and burst, charge weapons draw,
//! hold and release, beams burn, melee weapons swing a combo; then enemy shots, chains, a
//! ricochet, a fork and orbiting blades. Stand-ins fly slower than the sim's shots so a capture
//! catches them. `GF_VFX_FREEZE`, `GF_VFX_ZOOM` and `GF_VFX_CELL` work as for `--vfx-gallery`.

use super::look_of;
use super::recipes::{self, Blast, Contact, Look, Shot, Strike};
use super::shots::{self, ShotSpec, Variant};
use crate::ClientConfig;
use crate::camera::MainCamera;
use crate::fx::api::F;
use crate::fx::{Arc, BodyMesh, Class, Fx, FxBody, Layer, Owner, Profile, Ramp, Sweep, strip};
use crate::net::Link;
use gf_core::damage::DamageType;
use gf_core::forge::WeaponBuild;
use gf_core::ids::ChassisId;
use gf_core::weapon::{FireKind, ProjectileStyle};
use gf_engine::client::{font_px, set_view_height, world_to_screen};
use gf_engine::prelude::*;
use std::f32::consts::TAU;

/// Seconds between re-fires.
pub const CYCLE: f32 = 2.4;
const COLS: usize = 6;
const ROWS: usize = 5;
const DX: f32 = 5.9;
const DZ: f32 = 3.9;
/// Half the flight of a stand-in shot.
const HALF: f32 = 2.3;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Demo {
    Chassis,
    EnemyShot,
    Chain,
    Ricochet,
    Fork,
    Orbit,
}

struct Cell {
    label: String,
    demo: Demo,
    look: Look,
    /// Shots or strikes fired this cycle.
    n: u32,
    next: f32,
    released: bool,
    beam: [f32; 3],
    motes: f32,
}

#[derive(Resource, Default)]
struct WeaponGallery {
    center: Option<Vec3>,
    clock: f32,
    cells: Vec<Cell>,
    freeze_at: Option<f32>,
    zoom: Option<f32>,
    focus: Option<usize>,
    labels: bool,
}

#[derive(Component)]
struct Label(usize);

/// A stand-in shot flying across its cell (the carrier of a dressed [`ShotSpec`]).
#[derive(Component)]
struct StandIn {
    cell: usize,
    from: Vec3,
    to: Vec3,
    /// A ricochet's bounce point (the flight kinks there).
    kink: Option<Vec3>,
    t: f32,
    dur: f32,
    /// Split into two children halfway (a fork).
    fork: bool,
}

/// An orbiting stand-in blade.
#[derive(Component)]
struct Orbiter {
    cell: usize,
    phase: f32,
    last: Option<f32>,
}

pub fn build(app: &mut App) {
    if !std::env::args().any(|a| a == "--weapon-gallery") {
        return;
    }
    let env = |k: &str| std::env::var(k).ok();
    app.insert_resource(WeaponGallery {
        freeze_at: env("GF_VFX_FREEZE").and_then(|v| v.parse().ok()),
        zoom: env("GF_VFX_ZOOM").and_then(|v| v.parse().ok()),
        focus: env("GF_VFX_CELL").and_then(|v| v.parse().ok()),
        ..default()
    })
    .add_systems(Update, (run, fly, orbiters, close_up, place_labels).chain().after(crate::ClientSet::Presentation));
}

fn cell_pos(center: Vec3, i: usize) -> Vec3 {
    let (c, r) = (i % COLS, i / COLS);
    let x = (c as f32 - (COLS as f32 - 1.0) * 0.5) * DX;
    let z = (r as f32 - (ROWS as f32 - 1.0) * 0.5) * DZ;
    Vec3::new(center.x + x, 0.0, center.z + z)
}

fn cells(cfg: &ClientConfig) -> Vec<Cell> {
    let db = &cfg.content;
    let mut out: Vec<Cell> = db
        .chassis
        .enumerate()
        .map(|(i, def)| Cell {
            label: def.name.clone(),
            demo: Demo::Chassis,
            look: look_of(db, &WeaponBuild::new(ChassisId(i))),
            n: 0,
            next: 0.0,
            released: false,
            beam: [0.0; 3],
            motes: 0.0,
        })
        .take(COLS * ROWS - 6)
        .collect();
    let extra = |label: &str, demo: Demo, look: Look| Cell {
        label: label.into(),
        demo,
        look,
        n: 0,
        next: 0.0,
        released: false,
        beam: [0.0; 3],
        motes: 0.0,
    };
    let coin = out.iter().find(|c| c.look.key == "coinshooter").map_or_else(Look::fallback, |c| c.look.clone());
    let mut fork =
        out.iter().find(|c| c.look.key == "thundercoil_launcher").map_or_else(Look::fallback, |c| c.look.clone());
    fork.fork = true;
    let mut orbit = Look::fallback();
    orbit.element = DamageType::Void;
    out.push(extra("enemy shots", Demo::EnemyShot, Look::fallback()));
    out.push(extra("chain storm / void", Demo::Chain, Look::fallback()));
    out.push(extra("ricochet (coin)", Demo::Ricochet, coin));
    out.push(extra("fork split", Demo::Fork, fork));
    out.push(extra("orbit blades", Demo::Orbit, orbit));
    out
}

#[allow(clippy::too_many_arguments)]
fn run(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    mut g: ResMut<WeaponGallery>,
    mut fx: Fx,
) {
    let dt = time.delta_secs();
    if g.center.is_none() {
        if time.elapsed_secs() < 2.0 || link.latest.is_none() {
            return;
        }
        let focus = fx.store.cam.focus;
        g.center = Some(Vec3::new(focus.x, 0.0, focus.z));
        g.cells = cells(&cfg);
        for i in 0..g.cells.len() {
            commands.spawn((
                Label(i),
                Text::new(g.cells[i].label.clone()),
                font_px(12.0),
                TextColor(Color::srgba(1.0, 0.95, 0.85, 0.9)),
                TextShadow { offset: Vec2::new(1.0, 1.0), color: Color::srgba(0.0, 0.0, 0.0, 0.9) },
                Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
                GlobalZIndex(6),
            ));
        }
        g.labels = true;
        for i in 0..g.cells.len() {
            if g.cells[i].demo == Demo::Orbit {
                for k in 0..3 {
                    let mut b = FxBody::new(BodyMesh::DiscBlade, Ramp::Void, Owner::Mine, 1.2).spin(Vec3::Y * 18.0);
                    b.align = false;
                    commands.spawn((
                        Orbiter { cell: i, phase: k as f32 * TAU / 3.0, last: None },
                        b,
                        Transform::default(),
                        Visibility::default(),
                    ));
                }
            }
        }
    }
    let Some(center) = g.center else { return };
    g.clock += dt;
    if let Some(at) = g.freeze_at {
        fx.store.frozen = g.clock >= at && g.clock < at + 0.9;
    }
    if g.clock >= CYCLE {
        g.clock = 0.0;
        fx.store.frozen = false;
        for c in &mut g.cells {
            c.n = 0;
            c.next = 0.0;
            c.released = false;
        }
    }
    let t = g.clock;
    let now = time.elapsed_secs();
    for i in 0..g.cells.len() {
        let base = cell_pos(center, i);
        let c = &mut g.cells[i];
        let dir = Vec3::X;
        let from = base + Vec3::new(-HALF, 1.0, 0.0);
        let feet = base + Vec3::new(-HALF - 0.4, 0.0, 0.0);
        match c.demo {
            Demo::Chassis => match c.look.fire {
                FireKind::Auto => {
                    let interval = 1.0 / c.look.rate.max(0.5);
                    let burst = (c.look.rate * 0.6).clamp(1.0, 6.0) as u32;
                    if c.n < burst && t >= c.next {
                        c.next = t + interval;
                        let shot = Shot {
                            look: &c.look,
                            at: from,
                            feet,
                            dir,
                            owner: Owner::Mine,
                            charge: 0.0,
                            n: c.n,
                            since: interval,
                        };
                        recipes::muzzle(&mut fx, &shot);
                        let look = c.look.clone();
                        c.n += 1;
                        volley(&mut commands, i, &look, from, 0.0);
                    }
                }
                FireKind::Charge => {
                    let ct = c.look.charge_time.max(0.4);
                    if t < ct + 0.35 {
                        let charge = (t / ct).min(1.0);
                        let full_for = (t >= ct).then_some(t - ct);
                        recipes::charge_cue(&mut fx, &c.look, from, dir, charge, full_for, now, Owner::Mine);
                        c.motes += dt * 8.0 / ct;
                        while c.motes >= 1.0 {
                            c.motes -= 1.0;
                            if charge < 1.0 {
                                recipes::charge_mote(&mut fx, &c.look, from, Owner::Mine);
                            }
                        }
                    } else if !c.released {
                        c.released = true;
                        let shot = Shot {
                            look: &c.look,
                            at: from,
                            feet,
                            dir,
                            owner: Owner::Mine,
                            charge: 1.0,
                            n: 0,
                            since: 1.0,
                        };
                        recipes::muzzle(&mut fx, &shot);
                        let look = c.look.clone();
                        volley(&mut commands, i, &look, from, 1.0);
                    }
                }
                FireKind::Beam => {
                    if t < 1.9 {
                        let len = c.look.range.min(2.0 * HALF + 0.3);
                        let w = c.look.beam_width;
                        let look = c.look.clone();
                        recipes::beam(
                            &mut fx,
                            20 + i as u32,
                            &look,
                            from,
                            dir,
                            len,
                            w,
                            now,
                            dt,
                            &mut c.beam,
                            Owner::Mine,
                        );
                    }
                }
                FireKind::Melee => {
                    let interval = 1.0 / c.look.base_rate.max(0.5);
                    if t < 1.9 && t >= c.next {
                        c.next = t + interval;
                        let n = c.n;
                        c.n += 1;
                        let foot = base + Vec3::new(-1.2, 0.0, 0.0);
                        recipes::strike(
                            &mut fx,
                            &Strike { look: &c.look, feet: foot, dir, n, owner: Owner::Mine, fist: None },
                        );
                        let target = foot + dir * c.look.range * 0.7 + Vec3::Y * 0.9;
                        let contact = Contact {
                            at: target,
                            dir,
                            ramp: c.look.ramp(),
                            owner: Owner::Mine,
                            body: 0.5,
                            crit: n % 4 == 3,
                            precision: false,
                            look: Some(&c.look),
                            plated: false,
                            repeat: false,
                        };
                        recipes::contact(&mut fx, &contact);
                    }
                }
            },
            Demo::EnemyShot => {
                if t >= c.next && c.n < 4 {
                    c.next = t + 0.45;
                    c.n += 1;
                    let a = base + Vec3::new(HALF, 0.8, (c.n as f32 - 2.5) * 0.5);
                    let b = base + Vec3::new(-HALF, 0.8, (c.n as f32 - 2.5) * 0.3);
                    recipes::enemy_spawn_flash(&mut fx, a, 0.2);
                    let spec = ShotSpec::enemy(0.25, 12.0, (b - a).normalize());
                    stand_in(&mut commands, i, &spec, a, b, None, false);
                }
            }
            Demo::Chain => {
                if t >= c.next && c.n < 2 {
                    c.next = t + 1.0;
                    let ramp = if c.n == 0 { Ramp::Storm } else { Ramp::Void };
                    c.n += 1;
                    let nodes = [
                        base + Vec3::new(-2.2, 1.0, 0.7),
                        base + Vec3::new(-0.4, 1.0, -0.8),
                        base + Vec3::new(1.2, 1.0, 0.6),
                        base + Vec3::new(2.4, 1.0, -0.5),
                    ];
                    for k in 0..3 {
                        recipes::chain(&mut fx, nodes[k], nodes[k + 1], ramp, Owner::Mine);
                    }
                }
            }
            Demo::Ricochet => {
                if t >= c.next && c.n < 2 {
                    c.next = t + 0.9;
                    c.n += 1;
                    let a = from;
                    let kink = base + Vec3::new(0.0, 1.0, 1.2);
                    let b = base + Vec3::new(HALF, 1.0, -1.0);
                    let spec = spec_of(&c.look, (kink - a).normalize(), 0.0);
                    stand_in(&mut commands, i, &spec, a, b, Some(kink), false);
                }
            }
            Demo::Fork => {
                if t >= c.next && c.n < 1 {
                    c.n += 1;
                    let spec = spec_of(&c.look, dir, 0.0);
                    stand_in(&mut commands, i, &spec, from, from + dir * HALF, None, true);
                }
            }
            Demo::Orbit => {}
        }
    }
}

fn spec_of(look: &Look, heading: Vec3, charged: f32) -> ShotSpec {
    let mut spec = ShotSpec::new(look.style, look.ramp(), Owner::Mine, 0.2, look.speed, heading);
    spec.variant = Variant::of(look.style, &look.key, look.ramp());
    spec.homing = look.homing;
    spec.charged = charged;
    spec.range = 2.0 * HALF;
    if spec.variant == Variant::Iron {
        spec.lob = 1.4;
    }
    spec
}

/// A volley of stand-ins across the cell (a shotgun's pellets fan out by its spread).
fn volley(commands: &mut Commands, cell: usize, look: &Look, from: Vec3, charged: f32) {
    let n = look.projectiles.clamp(1, 7);
    let half = look.spread.to_radians() * 0.5;
    for k in 0..n {
        let a = if n > 1 { -half + 2.0 * half * k as f32 / (n - 1) as f32 } else { 0.0 };
        let d = Quat::from_rotation_y(a) * Vec3::X;
        let spec = spec_of(look, d, charged);
        let to = from + d * (2.0 * HALF);
        let homing = look.homing.then(|| from + Vec3::new(HALF, 0.0, 1.3));
        stand_in(commands, cell, &spec, from, to, homing, false);
    }
}

fn stand_in(
    commands: &mut Commands,
    cell: usize,
    spec: &ShotSpec,
    from: Vec3,
    to: Vec3,
    kink: Option<Vec3>,
    fork: bool,
) {
    let dist = from.distance(to) + kink.map_or(0.0, |k| from.distance(k) + k.distance(to) - from.distance(to));
    let speed = spec.speed.clamp(6.0, 11.0);
    let e = commands
        .spawn((
            StandIn { cell, from, to, kink, t: 0.0, dur: dist / speed, fork },
            Transform::from_translation(from),
            Visibility::default(),
        ))
        .id();
    shots::dress(commands, e, spec, None);
}

/// Move the stand-ins; on arrival, the hit and the burst.
fn fly(
    mut commands: Commands,
    time: Res<Time>,
    g: Res<WeaponGallery>,
    mut q: Query<(Entity, &mut StandIn, &mut Transform, &shots::ShotFx)>,
    mut fx: Fx,
) {
    let dt = time.delta_secs() * fx.store.time_scale * if fx.store.frozen { 0.0 } else { 1.0 };
    for (e, mut s, mut tf, shot) in &mut q {
        s.t += dt;
        let k = (s.t / s.dur).min(1.0);
        let p = match s.kink {
            // A ricochet: two straight legs. A homing shot: a curve through the kink.
            Some(kink) if shot.spec.homing => {
                let a = s.from.lerp(kink, k);
                let b = kink.lerp(s.to, k);
                a.lerp(b, k)
            }
            Some(kink) => {
                let l1 = s.from.distance(kink);
                let l2 = kink.distance(s.to);
                let d = k * (l1 + l2);
                if d < l1 { s.from.lerp(kink, d / l1) } else { kink.lerp(s.to, (d - l1) / l2.max(1e-3)) }
            }
            None => s.from.lerp(s.to, k),
        };
        tf.translation = p + Vec3::Y * lob_height(shot, k);
        if s.fork && k >= 0.5 {
            // The parent flashes a split star and peels into two children, 80 % as large.
            s.fork = false;
            let at = tf.translation;
            fx.sprite(crate::fx::seq::PETAL_CROSS, at)
                .radius(0.45)
                .ramp(shot.spec.ramp)
                .play(crate::fx::Play::Life)
                .life(5.0 * F)
                .ink_backed()
                .layer(Layer::Front)
                .emit();
            for sgn in [1.0, -1.0] {
                let d = Quat::from_rotation_y(0.45 * sgn) * Vec3::X;
                let mut child = shot.spec;
                child.scale = 0.8;
                child.heading = d;
                stand_in(&mut commands, s.cell, &child, at, at + d * HALF, None, false);
            }
            commands.entity(e).despawn();
            continue;
        }
        if k >= 1.0 {
            let spec = shot.spec;
            let to = tf.translation;
            if spec.enemy {
                recipes::enemy_impact(&mut fx, to, shot.heading, true);
            } else {
                let look = g.cells.get(s.cell).map(|c| &c.look);
                let contact = Contact {
                    at: to,
                    dir: shot.heading,
                    ramp: spec.ramp,
                    owner: Owner::Mine,
                    body: 0.5,
                    crit: s.cell % 5 == 1,
                    precision: s.cell % 7 == 3,
                    look,
                    plated: false,
                    repeat: false,
                };
                recipes::contact(&mut fx, &contact);
                if let Some(l) = look {
                    if l.splash > 0.0 {
                        let blast = match (spec.style, spec.variant) {
                            (_, Variant::VoidHeart) => Blast::Singularity,
                            (_, Variant::Dial) => Blast::Dial,
                            (ProjectileStyle::Shell, _) | (_, Variant::Iron) => Blast::Shell,
                            _ => Blast::Plain,
                        };
                        recipes::explosion(&mut fx, spec.ramp, to, l.splash, blast, Owner::Mine);
                    }
                    if l.chain {
                        let a = to + Vec3::new(0.2, 0.0, 1.2);
                        recipes::chain(&mut fx, to, a, spec.ramp, Owner::Mine);
                        recipes::chain(&mut fx, a, a + Vec3::new(1.0, 0.0, -0.4), spec.ramp, Owner::Mine);
                    }
                }
            }
            commands.entity(e).despawn();
        }
    }
}

fn lob_height(shot: &shots::ShotFx, k: f32) -> f32 {
    if shot.spec.lob > 0.0 { 4.0 * shot.spec.lob * k * (1.0 - k) } else { 0.0 }
}

/// Stand-in blades orbit their cell; the same trailing smear as a replicated blade.
fn orbiters(time: Res<Time>, g: Res<WeaponGallery>, mut q: Query<(&mut Orbiter, &mut Transform)>, mut fx: Fx) {
    let Some(center) = g.center else { return };
    let t = time.elapsed_secs();
    for (mut o, mut tf) in &mut q {
        let c = cell_pos(center, o.cell) + Vec3::Y * 0.8;
        let a = t * 3.2 + o.phase;
        let r = 1.6;
        let pos = c + Vec3::new(a.cos() * r, 0.0, a.sin() * r);
        tf.translation = pos;
        let rel = pos - c;
        let arc_a = (-rel.x).atan2(-rel.z);
        let sign = match o.last {
            Some(last) => {
                let mut d = arc_a - last;
                if d > std::f32::consts::PI {
                    d -= TAU;
                }
                if d < -std::f32::consts::PI {
                    d += TAU;
                }
                d.signum()
            }
            None => 1.0,
        };
        o.last = Some(arc_a);
        let mut arc = Arc::new(strip::SPIN_DISC, c, r + 0.25, 0.5, 1.0);
        arc.start = arc_a - sign * 1.2;
        arc.sweep = sign * 1.2;
        arc.sweep_anim = Sweep::Static;
        arc.profile = Profile::Crescent { peak: 0.85 };
        arc.ramp = Ramp::Void;
        arc.gain = 1.1;
        arc.erode = Vec2::new(1.0, 0.0);
        arc.segments = 18;
        arc.pull = 0.2;
        fx.arc_now(arc, Owner::Mine, Class::Core);
    }
}

fn close_up(g: Res<WeaponGallery>, mut cameras: Query<(&mut Transform, &mut Projection), With<MainCamera>>) {
    let Ok((mut tf, mut projection)) = cameras.single_mut() else { return };
    if let Some(h) = g.zoom {
        set_view_height(&mut projection, h);
    }
    if let (Some(i), Some(center)) = (g.focus, g.center) {
        let fwd = tf.forward().as_vec3();
        let t = if fwd.y.abs() > 1e-3 { -tf.translation.y / fwd.y } else { 60.0 };
        let focus = tf.translation + fwd * t;
        tf.translation += cell_pos(center, i) - focus;
    }
}

fn place_labels(
    g: Res<WeaponGallery>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut labels: Query<(&Label, &mut Node)>,
) {
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let Some(center) = g.center else { return };
    for (label, mut node) in &mut labels {
        let at = cell_pos(center, label.0) + Vec3::new(-HALF, 0.0, DZ * 0.4);
        match world_to_screen(camera, cam_tf, at) {
            Some(p) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - 10.0);
                node.top = Val::Px(p.y - 6.0);
            }
            None => node.display = Display::None,
        }
    }
}
