//! QA: `--vfx-gallery` plays every VFX primitive and recipe in a labelled grid around the view
//! centre, re-firing every [`CYCLE`] seconds, for art review at game scale over a real room.
//! `--vfx-bench` instead holds the frame-time scenario of the VFX budget: 2000 live particles,
//! 200 trails and 50 smears, logging the live counts once a second (pair it with `--fps`).
//!
//! `GF_VFX_FREEZE=<seconds>` freezes the VFX clock that long after each gallery cycle starts, so a
//! screenshot catches a chosen frame of every effect at once. `GF_VFX_ZOOM=<view height>` narrows
//! the camera (22 = game scale) and `GF_VFX_CELL=<index>` centres it on one cell, for close-ups.

use super::api::{F, Fx, Hit, HitKind, Smear, trail_style};
use super::library::{Decal, Glyph, Ramp, seq, strip};
use super::ribbon::RibbonStyle;
use super::{BodyMesh, Class, FxBody, FxSprite, FxTrail, Layer, Owner, RibbonId};
use crate::camera::MainCamera;
use crate::net::Link;
use crate::scene::SceneIndex;
use gf_core::damage::DamageType;
use gf_core::weapon::ProjectileStyle;
use gf_engine::client::{font_px, set_view_height, world_to_screen};
use gf_engine::prelude::*;

/// Seconds between gallery re-fires.
pub const CYCLE: f32 = 2.4;
const COLS: usize = 8;
const ROWS: usize = 6;
const DX: f32 = 4.7;
const DZ: f32 = 3.9;

#[derive(Resource, Default)]
struct Gallery {
    zoom: Option<f32>,
    cell: Option<usize>,
    clock: f32,
    fired: bool,
    freeze_at: Option<f32>,
    shots: bool,
    center: Option<Vec3>,
}

#[derive(Resource, Default)]
struct Bench {
    /// Load multiplier (`--vfx-bench 0` = no load: the baseline for an A/B).
    scale: f32,
    trails: Vec<Option<RibbonId>>,
    clock: f32,
    log: f32,
}

#[derive(Component)]
struct Label(usize);

const LABELS: [&str; COLS * ROWS] = [
    // row 0: hit punctuation
    "hit kinetic",
    "hit flame",
    "hit storm",
    "hit void",
    "hit plague",
    "hit radiant",
    "crit",
    "precision",
    // row 1: layered bursts, deaths
    "burst kinetic",
    "burst flame",
    "burst storm",
    "burst void",
    "burst plague",
    "burst radiant",
    "death unmade",
    "death godworks",
    // row 2: muzzle flashes
    "muzzle needle",
    "muzzle slug",
    "muzzle shell",
    "muzzle pellet",
    "muzzle orb",
    "muzzle arc",
    "muzzle coin",
    "bolt chain",
    // row 3: arcs
    "smear heavy",
    "smear flame",
    "smear void",
    "smear storm",
    "slash",
    "ring shock",
    "dust wall",
    "ring tick",
    // row 4: ribbons
    "body + trail slug",
    "body + trail arrow",
    "body + trail shell",
    "body + trail orb",
    "enemy shot",
    "beam",
    "pillar",
    "tether",
    // row 5: particles, decals, allies
    "smoke",
    "sparks + shards",
    "embers + tongues",
    "motes",
    "decals",
    "ground fx",
    "ally burst 0.55",
    "light flash",
];

pub fn build(app: &mut App) {
    let args: Vec<String> = std::env::args().collect();
    let flag = |f: &str| args.iter().any(|a| a == f);
    if flag("--vfx-gallery") {
        let env = |k: &str| std::env::var(k).ok();
        let freeze_at = env("GF_VFX_FREEZE").and_then(|v| v.parse().ok());
        let zoom = env("GF_VFX_ZOOM").and_then(|v| v.parse().ok());
        let cell = env("GF_VFX_CELL").and_then(|v| v.parse().ok());
        app.insert_resource(Gallery { freeze_at, zoom, cell, ..default() })
            .add_systems(Startup, spawn_labels)
            .add_systems(
                Update,
                (run_gallery, move_shots, close_up, place_labels).chain().after(crate::ClientSet::Presentation),
            );
    }
    if flag("--vfx-bench") {
        let scale = args
            .iter()
            .position(|a| a == "--vfx-bench")
            .and_then(|i| args.get(i + 1))
            .and_then(|v| v.parse().ok())
            .unwrap_or(1.0);
        // GPU time per render pass (timestamp queries), logged with the bench counters.
        app.add_plugins(gf_engine::bevy::render::diagnostic::RenderDiagnosticsPlugin)
            .insert_resource(Bench { scale, ..default() })
            .add_systems(Update, run_bench.after(crate::ClientSet::Presentation));
    }
}

fn spawn_labels(mut commands: Commands) {
    for (i, text) in LABELS.iter().enumerate() {
        commands.spawn((
            Label(i),
            Text::new(*text),
            font_px(12.0),
            TextColor(Color::srgba(1.0, 0.95, 0.85, 0.85)),
            TextShadow { offset: Vec2::new(1.0, 1.0), color: Color::srgba(0.0, 0.0, 0.0, 0.9) },
            Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
            GlobalZIndex(6),
        ));
    }
}

/// QA close-ups: override the camera's view height and centre it on one cell.
fn close_up(gallery: Res<Gallery>, mut cameras: Query<(&mut Transform, &mut Projection), With<MainCamera>>) {
    let Ok((mut tf, mut projection)) = cameras.single_mut() else { return };
    if let Some(h) = gallery.zoom {
        set_view_height(&mut projection, h);
    }
    if let (Some(i), Some(center)) = (gallery.cell, gallery.center) {
        let fwd = tf.forward().as_vec3();
        let t = if fwd.y.abs() > 1e-3 { -tf.translation.y / fwd.y } else { 60.0 };
        let focus = tf.translation + fwd * t;
        tf.translation += cell_pos(center, i) - focus;
    }
}

fn cell_pos(center: Vec3, i: usize) -> Vec3 {
    let (c, r) = (i % COLS, i / COLS);
    let x = (c as f32 - (COLS as f32 - 1.0) * 0.5) * DX;
    let z = (r as f32 - (ROWS as f32 - 1.0) * 0.5) * DZ;
    Vec3::new(center.x + x, 0.0, center.z + z)
}

fn place_labels(
    gallery: Res<Gallery>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut labels: Query<(&Label, &mut Node)>,
) {
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let Some(center) = gallery.center else { return };
    for (label, mut node) in &mut labels {
        let at = cell_pos(center, label.0) + Vec3::new(0.0, 0.0, DZ * 0.42);
        match world_to_screen(camera, cam_tf, at) {
            Some(p) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - 40.0);
                node.top = Val::Px(p.y - 6.0);
            }
            None => node.display = Display::None,
        }
    }
}

fn run_gallery(
    mut commands: Commands,
    time: Res<Time>,
    mut gallery: ResMut<Gallery>,
    mut fx: Fx,
    link: Res<Link>,
    index: Res<SceneIndex>,
    globals: Query<&GlobalTransform>,
) {
    let dt = time.delta_secs();
    // Wait for the world and the camera to settle, then hold the grid still where the view is.
    if gallery.center.is_none() {
        if time.elapsed_secs() < 2.0 || link.latest.is_none() {
            return;
        }
        let focus = fx.store.cam.focus;
        gallery.center = Some(Vec3::new(focus.x, 0.0, focus.z));
    }
    let Some(center) = gallery.center else { return };
    gallery.clock += dt;
    if let Some(at) = gallery.freeze_at {
        fx.store.frozen = gallery.clock >= at && gallery.clock < at + 0.9;
    }
    if gallery.clock >= CYCLE || !gallery.fired {
        gallery.clock = 0.0;
        gallery.fired = true;
        fx.store.frozen = false;
        let me = link.slot.and_then(|s| index.players.get(s as usize).copied().flatten());
        let s = fx.store.stats;
        info!(
            "vfx gallery at {center}: {} particles, {} ribbons, {} arcs, {} decals · {} draws, {} vertices · cpu {:.2} ms",
            s.particles, s.ribbons, s.arcs, s.decals, s.draws, s.vertices, s.build_ms
        );
        fire_all(&mut fx, center, me);
        // A burst right on the local hero: effects thin out over characters (the hero reveal).
        if let Some(p) = me.and_then(|e| globals.get(e).ok()) {
            fx.burst(Ramp::Kinetic, p.translation(), 1.5, Owner::Mine);
        }
    }
    if !gallery.shots {
        gallery.shots = true;
        spawn_shots(&mut commands, center);
    }
    continuous(&mut fx, center, time.elapsed_secs());
}

fn fire_all(fx: &mut Fx, center: Vec3, me: Option<Entity>) {
    let at = |i: usize| cell_pos(center, i);
    let mine = Owner::Mine;
    // Row 0: hits.
    let ramps = [Ramp::Kinetic, Ramp::Flame, Ramp::Storm, Ramp::Void, Ramp::Plague, Ramp::Radiant];
    for (i, ramp) in ramps.iter().enumerate() {
        fx.impact(Hit::new(at(i) + Vec3::Y * 0.9, *ramp, 0.55, mine).dir(Vec3::X));
    }
    fx.impact(Hit::new(at(6) + Vec3::Y * 0.9, Ramp::Kinetic, 0.5, mine).kind(HitKind::Crit).dir(Vec3::X));
    fx.impact(Hit::new(at(7) + Vec3::Y * 0.9, Ramp::Storm, 0.45, mine).kind(HitKind::Precision));
    // Row 1: bursts and deaths.
    for (i, ramp) in ramps.iter().enumerate() {
        fx.burst(*ramp, at(8 + i), 1.6, mine);
    }
    fx.death(Ramp::Unmade, at(14), 0.6, mine);
    fx.death(Ramp::GodworksGold, at(15), 0.6, mine);
    // Row 2: muzzle flashes, aimed right.
    let styles = [
        (ProjectileStyle::Needle, DamageType::Kinetic),
        (ProjectileStyle::Slug, DamageType::Radiant),
        (ProjectileStyle::Shell, DamageType::Kinetic),
        (ProjectileStyle::Pellet, DamageType::Radiant),
        (ProjectileStyle::Orb, DamageType::Storm),
        (ProjectileStyle::Arc, DamageType::Storm),
        (ProjectileStyle::Coin, DamageType::Kinetic),
    ];
    for (i, (style, e)) in styles.iter().enumerate() {
        fx.muzzle(*style, *e, at(16 + i) + Vec3::new(-1.2, 1.0, 0.0), Vec3::X, mine);
    }
    let b = at(23);
    let nodes = [b + Vec3::new(-2.0, 0.9, 0.8), b + Vec3::new(0.0, 0.9, -0.9), b + Vec3::new(1.8, 0.9, 0.6)];
    fx.bolt(nodes[0], nodes[1], Ramp::Storm, 0.55, 10.0 * F, mine);
    fx.bolt(nodes[1], nodes[2], Ramp::Storm, 0.55, 10.0 * F, mine);
    for n in nodes {
        fx.sprite(seq::STAR4, n).radius(0.35).ramp(Ramp::Storm).play(super::Play::Life).life(6.0 * F).emit();
    }
    // Row 3: smears, a slash, rings.
    let swing = |fx: &mut Fx, i: usize, st: super::Strip, ramp: Ramp, sweep: f32| {
        let mut s = Smear::new(at(i) + Vec3::new(-0.8, 0.9, 0.0), Vec3::X, 2.0, ramp, Owner::Mine);
        s.strip = st;
        s.sweep = sweep;
        s.life = 14.0 * F;
        fx.smear(s);
    };
    swing(fx, 24, strip::MELEE_HEAVY, Ramp::Kinetic, 1.9);
    swing(fx, 25, strip::FLAME_SMEAR, Ramp::Flame, -2.2);
    swing(fx, 26, strip::VOID_SMEAR, Ramp::Void, 1.9);
    swing(fx, 27, strip::STORM_SMEAR, Ramp::Storm, -1.9);
    fx.slash(at(28) + Vec3::Y * 0.9, Vec3::new(1.0, 0.0, -0.5), 2.8, Ramp::ZoneGold, mine);
    fx.ring(at(29), 0.3, 1.9, 14.0 * F, strip::SHOCK_FRONT, Ramp::Kinetic, mine);
    fx.dust_wall(at(30), 0.4, 1.9, 0.6, 30.0 * F, Ramp::Dust, mine);
    fx.ring(at(31), 0.4, 1.8, 30.0 * F, strip::TICK_RING, Ramp::Time, mine);
    // Row 4: pillar (the continuous ones run every frame).
    fx.pillar(at(38), 4.5, 0.5, Ramp::Radiant, CYCLE, Owner::World);
    // Row 5: particles, decals, allies, lights.
    fx.smoke(at(40) + Vec3::Y * 0.4, 6, 0.7, Ramp::Kinetic, mine);
    fx.sparks(at(41) + Vec3::Y * 0.8, Vec3::ZERO, 10, 7.0, Ramp::Kinetic, mine);
    fx.shards(at(41) + Vec3::Y * 0.8, 6, 5.0, Ramp::Kinetic, 0.2, mine);
    fx.embers(at(42) + Vec3::Y * 0.3, 10, 0.8, mine);
    fx.tongues(at(42), 5, 0.7, 1.4, CYCLE * 0.9, mine);
    if let Some(me) = me {
        fx.motes(at(43) + Vec3::Y * 0.5, me, 3, Ramp::Radiant, mine);
    }
    let d = at(44);
    fx.decal(Decal::ScorchA, d + Vec3::new(-1.0, 0.0, 0.0), 0.9, Ramp::Kinetic, CYCLE, mine);
    fx.decal(Decal::CrackStarA, d + Vec3::new(1.0, 0.0, 0.0), 0.9, Ramp::Flame, CYCLE, mine);
    fx.decal(Decal::IchorStainA, d + Vec3::new(0.0, 0.0, 0.9), 0.8, Ramp::Unmade, CYCLE, mine);
    let g = at(45);
    fx.decal_seq(seq::VOID_SWIRL, g + Vec3::new(-1.1, 0.0, 0.0), 1.0, 0.0, Ramp::Void, CYCLE, mine);
    fx.decal_seq(seq::STORM_LICHTENBERG.nth(1), g + Vec3::new(1.1, 0.0, 0.0), 1.0, 0.0, Ramp::Storm, CYCLE, mine);
    fx.decal_seq(Glyph::Hexagram.seq(), g + Vec3::new(0.0, 0.0, 1.0), 0.8, 0.0, Ramp::Radiant, CYCLE, mine);
    fx.burst(Ramp::Flame, at(46), 1.6, Owner::Ally);
    fx.light(at(47) + Vec3::Y * 1.0, Ramp::Flame.light(), 400_000.0, 7.0, 1.2, mine);
    fx.sprite(seq::STAR7, at(47) + Vec3::Y * 1.0).radius(0.6).ramp(Ramp::Flame).ink_backed().emit();
}

/// A stand-in projectile circling a gallery cell: it carries an [`FxSprite`] body and an
/// [`FxTrail`], the way `scene.rs` projectiles will.
#[derive(Component)]
struct GalleryShot {
    cell: usize,
    speed: f32,
    phase: f32,
}

const SHOTS: [(usize, ProjectileStyle, Ramp, f32); 5] = [
    (32, ProjectileStyle::Slug, Ramp::Radiant, 20.0),
    (33, ProjectileStyle::Arrow, Ramp::Void, 16.0),
    (34, ProjectileStyle::Shell, Ramp::Kinetic, 11.0),
    (35, ProjectileStyle::Orb, Ramp::Storm, 9.0),
    (36, ProjectileStyle::Needle, Ramp::EnemyShot, 10.0),
];

fn spawn_shots(commands: &mut Commands, center: Vec3) {
    for (k, (cell, style, ramp, speed)) in SHOTS.iter().enumerate() {
        let (sprite, trail) = if *ramp == Ramp::EnemyShot {
            (
                FxSprite::enemy_shot(0.18),
                RibbonStyle {
                    layer: Layer::Danger,
                    ..RibbonStyle::new(strip::NEEDLE_STREAK, Ramp::EnemyShot, 0.45, 1.0)
                },
            )
        } else {
            let t = trail_style(*style, *ramp, *speed).unwrap_or(RibbonStyle::new(strip::TRACER, *ramp, 0.5, 1.5));
            (FxSprite::body(*style, *ramp, 0.14, Owner::Mine), t)
        };
        let owner = if *ramp == Ramp::EnemyShot { Owner::Enemy } else { Owner::Mine };
        let mut shot = commands.spawn((
            Name::new("vfx gallery shot"),
            GalleryShot { cell: *cell, speed: *speed, phase: k as f32 },
            Transform::from_translation(cell_pos(center, *cell) + Vec3::Y),
            Visibility::default(),
            FxTrail::new(trail, owner),
        ));
        // Mesh bodies where the library has them, billboards elsewhere.
        match style {
            ProjectileStyle::Shell => {
                shot.insert(FxBody::new(BodyMesh::Shell, *ramp, owner, 1.6).spin(Vec3::new(1.6, 0.0, 0.0)));
            }
            ProjectileStyle::Arrow => {
                shot.insert(FxBody::new(BodyMesh::Arrow, *ramp, owner, 1.4));
            }
            _ => {
                shot.insert(sprite);
            }
        }
    }
}

fn move_shots(time: Res<Time>, gallery: Res<Gallery>, mut shots: Query<(&GalleryShot, &mut Transform)>) {
    let Some(center) = gallery.center else { return };
    let t = time.elapsed_secs();
    for (s, mut tf) in &mut shots {
        let r = 1.5;
        let a = t * s.speed / r * 0.35 + s.phase;
        tf.translation = cell_pos(center, s.cell) + Vec3::new(a.cos() * r, 1.0, a.sin() * r * 0.8);
    }
}

/// The emitters that live across cycles: a beam and a tether (immediate mode, every frame).
fn continuous(fx: &mut Fx, center: Vec3, t: f32) {
    let at = |i: usize| cell_pos(center, i);
    let b = at(37);
    let wob = (t * 3.0).sin() * 0.3;
    fx.beam(90, b + Vec3::new(-2.0, 1.0, 0.0), b + Vec3::new(2.0, 1.0, wob), 0.5, Ramp::Flame, Owner::Mine);
    let e = at(39);
    fx.tether(91, e + Vec3::new(-1.8, 1.0, 0.3), e + Vec3::new(1.8, 1.0, -0.3), 0.35, Ramp::ZoneGold, Owner::Mine);
}

/// The VFX budget scenario: 2000 particles, 200 trails, 50 smears kept alive around the view.
fn run_bench(
    time: Res<Time>,
    mut bench: ResMut<Bench>,
    mut fx: Fx,
    diagnostics: Res<gf_engine::bevy::diagnostic::DiagnosticsStore>,
) {
    let dt = time.delta_secs();
    bench.clock += dt;
    let focus = fx.store.cam.focus;
    let t = time.elapsed_secs();
    let scale = bench.scale;
    // Particles: top up to 2000 with a mix of sheets (stars, smoke, sparks, bursts).
    let want = (2000.0 * scale) as usize;
    let mut n = fx.store.particles.len();
    let mut k = 0u32;
    while n < want {
        let p = focus + Vec3::new(fx.range(-16.0, 16.0), fx.range(0.3, 2.0), fx.range(-11.0, 11.0));
        let ramp = [Ramp::Kinetic, Ramp::Flame, Ramp::Storm, Ramp::Void][k as usize % 4];
        let life = fx.range(0.8, 1.6);
        let v = Vec3::new(fx.range(-2.0, 2.0), fx.range(0.0, 3.0), fx.range(-2.0, 2.0));
        let sq = match k % 5 {
            0 => seq::STAR5,
            1 => seq::SMOKE.in_column(k as u16 % 8),
            2 => seq::SPARK.nth(k as u16 % 8),
            3 => seq::BURST_FLAME,
            _ => seq::GLINT.nth(0),
        };
        fx.sprite(sq, p)
            .size(0.8)
            .ramp(ramp)
            .vel(v)
            .gravity(2.0)
            .life(life)
            .play(super::Play::Life)
            .class(Class::Danger)
            .emit();
        n += 1;
        k += 1;
    }
    // Trails: 200 on circles.
    let trails = (200.0 * scale) as usize;
    bench.trails.resize(trails, None);
    for i in 0..trails {
        let r = 1.0 + (i % 7) as f32 * 0.6;
        let a = t * (2.0 + (i % 5) as f32) + i as f32;
        let c = focus + Vec3::new(((i % 20) as f32 - 9.5) * 1.7, 0.0, ((i / 20) as f32 - 4.5) * 2.2);
        let p = c + Vec3::new(a.cos() * r, 1.0, a.sin() * r);
        match bench.trails[i].filter(|id| fx.ribbon_alive(*id)) {
            Some(id) => fx.ribbon_to(id, p),
            None => {
                let st = RibbonStyle::new(strip::GHOST_SMEAR, Ramp::Void, 0.3, 2.0);
                bench.trails[i] = fx.ribbon(p, st, Owner::Mine);
            }
        }
    }
    // Smears: keep 50 alive.
    let arcs = fx.store.arcs.len();
    for i in arcs..(50.0 * scale) as usize {
        let p = focus + Vec3::new(fx.range(-15.0, 15.0), 0.9, fx.range(-10.0, 10.0));
        let d = fx.rand_dir();
        let mut s = Smear::new(p, d, 2.0, Ramp::Flame, Owner::Mine);
        s.life = 0.4 + (i % 5) as f32 * 0.05;
        fx.smear(s);
    }
    bench.log += dt;
    if bench.log >= 1.0 {
        bench.log = 0.0;
        let s = fx.store.stats;
        let gpu = |pass: &str| {
            diagnostics
                .iter()
                .filter(|d| {
                    let p = d.path().as_str();
                    p.contains(pass) && p.ends_with("elapsed_gpu")
                })
                .filter_map(|d| d.average())
                .sum::<f64>()
        };
        info!(
            "vfx bench x{scale}: {} particles, {} ribbons, {} arcs, {} decals · {} draws, {} vertices · cpu {:.2} ms · gpu transparent {:.2} ms, opaque {:.2} ms",
            s.particles,
            s.ribbons,
            s.arcs,
            s.decals,
            s.draws,
            s.vertices,
            s.build_ms,
            gpu("transparent"),
            gpu("opaque")
        );
    }
}
