//! QA: `--vfx-kit <page>` plays lane A's set pieces in a labelled grid around the view centre,
//! re-firing every [`CYCLE`] seconds, for art review at game scale over a real room.
//!
//! Pages: `abilities` (every kit ability with its follow-up), `synergies` (the 12 set pieces),
//! `zones` (every painted zone look, enemy telegraphs mid-fill, an ally telegraph, an enemy pool),
//! `moments` (deaths, boss death, hit feedback, telegraph resolves, the forge, team moments).
//!
//! `GF_KIT_FREEZE=<seconds>` freezes the VFX clock that long after each fire, so a screenshot
//! catches one frame of every effect; `GF_KIT_VIEW=<view height>` sets the camera's view height.

use super::kit::{self, Caster, Hero, ZoneLook};
use super::zone::{ZoneMaterial, ZoneMesh, ZoneParams};
use crate::camera::{MainCamera, w3};
use crate::fx::api::F;
use crate::fx::{Fx, Owner, Ramp};
use crate::net::Link;
use crate::palette::{flat, hex};
use gf_engine::client::{NotShadowCaster, font_px, set_view_height, world_to_screen};
use gf_engine::prelude::*;
use std::f32::consts::FRAC_PI_2;

pub const CYCLE: f32 = 3.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Page {
    Abilities,
    Synergies,
    Zones,
    Moments,
}

impl Page {
    fn grid(self) -> (usize, usize, f32, f32) {
        match self {
            Page::Abilities => (6, 4, 8.5, 7.0),
            Page::Synergies => (4, 3, 12.0, 9.0),
            Page::Zones => (5, 4, 7.5, 6.5),
            Page::Moments => (6, 3, 8.5, 8.0),
        }
    }

    fn labels(self) -> &'static [&'static str] {
        match self {
            Page::Abilities => &[
                "valdris bulwark slam",
                "valdris siege stance",
                "valdris mountainfall",
                "selene arc nova",
                "selene blink",
                "selene heaven's verdict",
                "kael fan of blades",
                "kael shadow roll",
                "kael bullet ballet",
                "thessaly forge turret",
                "thessaly binding hex",
                "thessaly sabbath",
                "brax cinder uppercut",
                "brax furnace rush",
                "brax meltdown + wave",
                "ossian piercing comet",
                "ossian skyhook mortar",
                "ossian rain of the hunt",
                "mirren gilded decoy pop",
                "mirren snatch",
                "mirren grand heist",
                "epoch still field",
                "epoch rewind wounds",
                "epoch stolen second",
            ],
            Page::Synergies => &[
                "blightburn",
                "gravity chain",
                "firestorm",
                "collapsing star",
                "solar flare",
                "toxic conduit",
                "judgment bolt",
                "entropy bloom",
                "eclipse",
                "purge",
                "shrapnel blaze",
                "railshock",
            ],
            Page::Zones => &[
                "well (enemy)",
                "field kinetic",
                "field flame",
                "field storm",
                "field void",
                "field plague",
                "field radiant",
                "pool (enemy)",
                "puddle",
                "ground (ult)",
                "firestorm",
                "entropy bloom",
                "heaven's verdict",
                "binding hex",
                "still field",
                "gilded decoy",
                "cinder geysers",
                "tele circle",
                "tele line + cone",
                "tele ring / ally",
            ],
            Page::Moments => &[
                "death unmade",
                "death godworks",
                "boss death",
                "plated glance",
                "shield ripple",
                "status motes",
                "resolve circle",
                "resolve line",
                "resolve cone",
                "resolve ring",
                "barricade rise",
                "turret rise",
                "forge strike",
                "recipe sunburst",
                "mountain pound",
                "meltdown wave",
                "time resume",
                "comet + marks",
            ],
        }
    }
}

#[derive(Resource)]
struct KitGallery {
    page: Page,
    center: Option<Vec3>,
    clock: f32,
    fired: bool,
    freeze_at: Option<f32>,
    view: Option<f32>,
    zones: Vec<(Entity, ZoneLook, Ramp, f32, f32)>,
    teles: Vec<Handle<ZoneMaterial>>,
    strikes: Vec<f32>,
}

#[derive(Component)]
struct KitLabel(usize);

pub fn build(app: &mut App) {
    let args: Vec<String> = std::env::args().collect();
    let Some(i) = args.iter().position(|a| a == "--vfx-kit") else { return };
    let page = match args.get(i + 1).map(String::as_str) {
        Some("synergies") => Page::Synergies,
        Some("zones") => Page::Zones,
        Some("moments") => Page::Moments,
        _ => Page::Abilities,
    };
    let env = |k: &str| std::env::var(k).ok();
    let freeze_at = env("GF_KIT_FREEZE").and_then(|v| v.parse().ok());
    let view = env("GF_KIT_VIEW").and_then(|v| v.parse().ok());
    app.insert_resource(KitGallery {
        page,
        center: None,
        clock: 0.0,
        fired: false,
        freeze_at,
        view,
        zones: Vec::new(),
        teles: Vec::new(),
        strikes: Vec::new(),
    })
    .add_systems(Startup, spawn_labels)
    .add_systems(Update, (run, place_labels, frame_view).chain().after(crate::ClientSet::Presentation));
}

fn spawn_labels(mut commands: Commands, g: Res<KitGallery>) {
    for (i, text) in g.page.labels().iter().enumerate() {
        commands.spawn((
            KitLabel(i),
            Text::new(*text),
            font_px(12.0),
            TextColor(Color::srgba(1.0, 0.95, 0.85, 0.9)),
            TextShadow { offset: Vec2::new(1.0, 1.0), color: Color::srgba(0.0, 0.0, 0.0, 0.9) },
            Node { position_type: PositionType::Absolute, display: Display::None, ..default() },
            GlobalZIndex(6),
        ));
    }
}

fn cell(page: Page, center: Vec3, i: usize) -> Vec3 {
    let (cols, rows, dx, dz) = page.grid();
    let (c, r) = (i % cols, i / cols);
    let x = (c as f32 - (cols as f32 - 1.0) * 0.5) * dx;
    let z = (r as f32 - (rows as f32 - 1.0) * 0.5) * dz;
    Vec3::new(center.x + x, 0.0, center.z + z)
}

/// Hold the camera on the grid (or on one cell with `GF_KIT_CELL`) at the page's view height.
fn frame_view(g: Res<KitGallery>, mut cameras: Query<(&mut Transform, &mut Projection), With<MainCamera>>) {
    let Ok((mut tf, mut projection)) = cameras.single_mut() else { return };
    let (cols, rows, dx, dz) = g.page.grid();
    let h = g.view.unwrap_or(((rows as f32) * dz * 1.25).max(cols as f32 * dx * 0.62));
    set_view_height(&mut projection, h);
    let Some(center) = g.center else { return };
    let target = match std::env::var("GF_KIT_CELL").ok().and_then(|v| v.parse::<usize>().ok()) {
        Some(i) => cell(g.page, center, i),
        None => center,
    };
    let fwd = tf.forward().as_vec3();
    let t = if fwd.y.abs() > 1e-3 { -tf.translation.y / fwd.y } else { 60.0 };
    let focus = tf.translation + fwd * t;
    tf.translation += target - focus;
}

fn place_labels(
    g: Res<KitGallery>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    mut labels: Query<(&KitLabel, &mut Node)>,
) {
    let Ok((camera, cam_tf)) = cameras.single() else { return };
    let Some(center) = g.center else { return };
    let (_, _, _, dz) = g.page.grid();
    for (label, mut node) in &mut labels {
        let at = cell(g.page, center, label.0) + Vec3::new(0.0, 0.0, dz * 0.45);
        match world_to_screen(camera, cam_tf, at) {
            Some(p) => {
                node.display = Display::Flex;
                node.left = Val::Px(p.x - 50.0);
                node.top = Val::Px(p.y - 6.0);
            }
            None => node.display = Display::None,
        }
    }
}

fn lin(c: Color) -> Vec4 {
    let l = c.to_linear();
    Vec4::new(l.red, l.green, l.blue, 1.0)
}

fn tones(ramp: Ramp) -> [Vec4; 4] {
    let t = ramp.tones();
    [lin(hex(t[0])), lin(hex(t[1])), lin(hex(t[2])), lin(hex(t[3]))]
}

/// A standalone zone quad for the zones page.
#[allow(clippy::too_many_arguments)]
fn zone_quad(
    commands: &mut Commands,
    mats: &mut Assets<ZoneMaterial>,
    mesh: &ZoneMesh,
    at: Vec3,
    angle: f32,
    params: ZoneParams,
    bias: f32,
) -> (Entity, Handle<ZoneMaterial>) {
    let rot = flat(angle);
    let q = params.quad;
    let tf = Transform {
        translation: at + Vec3::Y * 0.03 + rot * Vec3::new(q.x, q.y, 0.0),
        rotation: rot,
        scale: Vec3::new(q.z, q.w, 1.0),
    };
    let h = mats.add(ZoneMaterial { params, bias });
    let e = commands.spawn((Mesh3d(mesh.0.clone()), MeshMaterial3d(h.clone()), tf, NotShadowCaster)).id();
    (e, h)
}

#[allow(clippy::too_many_arguments)]
fn run(
    mut commands: Commands,
    time: Res<Time>,
    link: Res<Link>,
    mut g: ResMut<KitGallery>,
    mesh: Option<Res<ZoneMesh>>,
    mut mats: ResMut<Assets<ZoneMaterial>>,
    mut fx: Fx,
) {
    let dt = time.delta_secs();
    if g.center.is_none() {
        if time.elapsed_secs() < 2.5 || link.latest.is_none() {
            return;
        }
        let focus = fx.store.cam.focus;
        g.center = Some(Vec3::new(focus.x, 0.0, focus.z));
        if g.page == Page::Zones
            && let Some(mesh) = mesh.as_deref()
        {
            spawn_zones(&mut commands, &mut mats, mesh, &mut g, time.elapsed_secs_wrapped());
        }
    }
    let Some(center) = g.center else { return };
    g.clock += dt;
    if let Some(at) = g.freeze_at {
        fx.store.frozen = g.clock >= at && g.clock < at + 1.0;
    }
    // Zone ambience.
    if g.page == Page::Zones {
        let age = time.elapsed_secs();
        let zones = g.zones.clone();
        g.strikes.resize(zones.len(), 0.0);
        for (k, (_, look, ramp, radius, seed)) in zones.iter().enumerate() {
            let owner = if matches!(look, ZoneLook::Well | ZoneLook::Pool) { Owner::Enemy } else { Owner::Mine };
            let mut s = g.strikes[k];
            let at = cell(g.page, center, zone_cell(k));
            kit::zone_tick(&mut fx, *look, *ramp, at, *radius, owner, dt, age, *seed, &mut s, &[]);
            g.strikes[k] = s;
        }
    }
    if g.clock < CYCLE && g.fired {
        return;
    }
    g.clock = 0.0;
    g.fired = true;
    fx.store.frozen = false;
    let at = |i: usize| cell(g.page, center, i);
    let o = Owner::Mine;
    let caster = |hero: Hero, i: usize| Caster {
        slot: 0,
        hero,
        at: at(i) - Vec3::X * 1.5,
        aim: Vec3::X,
        owner: o,
        entity: None,
    };
    match g.page {
        Page::Abilities => {
            let heroes = [
                Hero::Valdris,
                Hero::Selene,
                Hero::Kael,
                Hero::Thessaly,
                Hero::Brax,
                Hero::Ossian,
                Hero::Mirren,
                Hero::Epoch,
            ];
            for (h, hero) in heroes.iter().enumerate() {
                for which in 0..3u8 {
                    let i = h * 3 + which as usize;
                    let c = caster(*hero, i);
                    let targets = [at(i) + Vec3::new(2.0, 0.9, -0.8), at(i) + Vec3::new(2.6, 0.9, 0.9)];
                    kit::ability(&mut fx, &c, which, &targets);
                    let p = at(i);
                    match (*hero, which) {
                        (Hero::Valdris, 0) => {
                            kit::bulwark_landing(&mut fx, p + Vec3::X * 1.0, 2.6, Vec3::X, o, &targets)
                        }
                        (Hero::Valdris, 2) => kit::mountain_pound(&mut fx, c.at, 3.0, o),
                        (Hero::Selene, 0) => {
                            for t in targets {
                                fx.bolt(c.at + Vec3::Y, t, Ramp::Storm, 0.55, 8.0 * F, o);
                            }
                        }
                        (Hero::Selene, 1) => kit::blink_arrive(&mut fx, c.at, c.at + Vec3::X * 4.0, o),
                        (Hero::Selene, 2) => {
                            kit::zone_open(&mut fx, ZoneLook::Verdict, p + Vec3::X * 1.5, 2.5, Ramp::Storm, o, &[])
                        }
                        (Hero::Thessaly, 0) => kit::turret_rise(&mut fx, p + Vec3::X * 1.2, o),
                        (Hero::Thessaly, 1) => {
                            kit::zone_open(&mut fx, ZoneLook::BindingHex, p + Vec3::X, 2.2, Ramp::Void, o, &targets)
                        }
                        (Hero::Brax, 0) => kit::uppercut(&mut fx, c.at, Vec3::X, 2.6, o),
                        (Hero::Brax, 2) => kit::meltdown_wave(&mut fx, c.at, c.at + Vec3::X * 1.6, 2.0, o),
                        (Hero::Ossian, 0) => kit::comet(&mut fx, c.at, c.at + Vec3::X * 6.5, o, &targets),
                        (Hero::Ossian, 1) => {
                            kit::mortar_lob(&mut fx, c.at, p + Vec3::X * 2.0, 0.7, o);
                            fx.burst(Ramp::Kinetic, p + Vec3::X * 2.0 + Vec3::Y * 0.0, 2.0, o);
                            kit::bomblets(&mut fx, p + Vec3::X * 2.0, 2.2, o);
                        }
                        (Hero::Mirren, 0) => {
                            kit::decoy_pop(&mut fx, p + Vec3::X * 1.0, o);
                            fx.burst(Ramp::Kinetic, p + Vec3::X, 2.2, o);
                        }
                        (Hero::Mirren, 1) => kit::snatch(&mut fx, c.at, c.at + Vec3::X * 4.0, o),
                        (Hero::Epoch, 2) => kit::time_resume(&mut fx, p, o),
                        _ => {}
                    }
                }
            }
        }
        Page::Synergies => {
            let list = [
                ("blightburn", Ramp::Plague, Ramp::Flame, Some(3.2)),
                ("gravity_chain", Ramp::Storm, Ramp::Void, None),
                ("firestorm", Ramp::Flame, Ramp::Storm, Some(3.0)),
                ("collapsing_star", Ramp::Flame, Ramp::Void, Some(3.6)),
                ("solar_flare", Ramp::Flame, Ramp::Radiant, Some(3.0)),
                ("toxic_conduit", Ramp::Storm, Ramp::Plague, Some(3.0)),
                ("judgment_bolt", Ramp::Storm, Ramp::Radiant, None),
                ("entropy_bloom", Ramp::Void, Ramp::Plague, Some(3.2)),
                ("eclipse", Ramp::Void, Ramp::Radiant, Some(4.0)),
                ("purge", Ramp::Plague, Ramp::Radiant, Some(4.0)),
                ("shrapnel_blaze", Ramp::Kinetic, Ramp::Flame, Some(2.6)),
                ("railshock", Ramp::Kinetic, Ramp::Storm, None),
            ];
            for (i, (key, ea, eb, r)) in list.iter().enumerate() {
                let p = at(i);
                let hops = [
                    (p, p + Vec3::new(2.5, 0.0, -1.5)),
                    (p + Vec3::new(2.5, 0.0, -1.5), p + Vec3::new(4.0, 0.0, 1.5)),
                    (p + Vec3::new(4.0, 0.0, 1.5), p + Vec3::new(1.0, 0.0, 2.5)),
                ];
                let chain = r.is_none();
                let targets =
                    [p + Vec3::new(1.5, 0.9, 1.0), p + Vec3::new(-1.4, 0.9, -0.6), p + Vec3::new(0.4, 0.9, -1.8)];
                kit::synergy(&mut fx, key, p, *ea, *eb, *r, if chain { &hops } else { &[] }, &targets, &[], o);
            }
        }
        Page::Zones => {
            // Re-arm the telegraphs' fill.
            let now = time.elapsed_secs_wrapped();
            let handles = g.teles.clone();
            for h in handles {
                if let Some(mut m) = mats.get_mut(&h) {
                    m.params.timing.x = now;
                }
            }
        }
        Page::Moments => {
            fx.death(Ramp::Unmade, at(0), 0.6, o);
            kit::death_extras(&mut fx, Ramp::Unmade, at(0), 0.6, o);
            fx.death(Ramp::GodworksGold, at(1), 0.6, o);
            kit::death_extras(&mut fx, Ramp::GodworksGold, at(1), 0.6, o);
            kit::boss_death(&mut fx, Ramp::Unmade, at(2), 1.6);
            for k in 0..3 {
                kit::glance(&mut fx, at(3) + Vec3::new(0.0, 1.0 + k as f32 * 0.3, 0.0), Vec3::X, o);
            }
            kit::shield_ripple(&mut fx, at(4) + Vec3::Y * 1.0, 1.0, Ramp::GodworksGold, o);
            for kind in [0u8, 1, 2, 3, 4, kit::FROZEN, kit::STUNNED, 5] {
                for _ in 0..3 {
                    let d = fx.rand_dir();
                    kit::status_mote(&mut fx, kind, at(5) + d * 0.8 + Vec3::Y * 1.2, d, o);
                }
            }
            use gf_content::TelegraphShape as T;
            kit::telegraph_punch(&mut fx, T::Circle { radius: 2.5 }, at(6), Vec3::X, Ramp::Unmade);
            kit::telegraph_punch(
                &mut fx,
                T::Line { length: 6.0, width: 1.6 },
                at(7) - Vec3::X * 3.0,
                Vec3::X,
                Ramp::Unmade,
            );
            kit::telegraph_punch(
                &mut fx,
                T::Cone { range: 3.5, angle_deg: 70.0 },
                at(8) - Vec3::X * 1.5,
                Vec3::X,
                Ramp::GodworksGold,
            );
            kit::telegraph_punch(&mut fx, T::Ring { inner: 1.6, outer: 2.8 }, at(9), Vec3::X, Ramp::Unmade);
            kit::barricade_rise(&mut fx, at(10), Vec3::Z, 2.5, o);
            kit::turret_rise(&mut fx, at(11), o);
            kit::forge_strike(&mut fx, at(12), false, o);
            kit::forge_strike(&mut fx, at(13), true, o);
            kit::mountain_pound(&mut fx, at(14), 3.2, o);
            kit::meltdown_wave(&mut fx, at(15) - Vec3::X * 1.5, at(15) + Vec3::X * 0.5, 2.0, o);
            kit::time_resume(&mut fx, at(16), o);
            let t = [at(17) + Vec3::new(1.0, 0.9, 0.0), at(17) + Vec3::new(3.0, 0.9, 0.0)];
            kit::comet(&mut fx, at(17) - Vec3::X * 3.5, at(17) + Vec3::X * 3.5, o, &t);
        }
    }
    let _ = FRAC_PI_2;
}

/// The zones page: cells 0-16 hold zone looks, 17-19 telegraphs.
fn zone_cell(k: usize) -> usize {
    k
}

fn spawn_zones(
    commands: &mut Commands,
    mats: &mut Assets<ZoneMaterial>,
    mesh: &ZoneMesh,
    g: &mut KitGallery,
    now: f32,
) {
    let Some(center) = g.center else { return };
    let looks: [(ZoneLook, Ramp, f32, bool); 17] = [
        (ZoneLook::Well, Ramp::Void, 0.0, false),
        (ZoneLook::Field, Ramp::Kinetic, 0.0, true),
        (ZoneLook::Field, Ramp::Flame, 1.0, true),
        (ZoneLook::Field, Ramp::Storm, 2.0, true),
        (ZoneLook::Field, Ramp::Void, 3.0, true),
        (ZoneLook::Field, Ramp::Plague, 4.0, true),
        (ZoneLook::Field, Ramp::Radiant, 5.0, true),
        (ZoneLook::Pool, Ramp::Flame, 1.0, false),
        (ZoneLook::Puddle, Ramp::Plague, 4.0, true),
        (ZoneLook::Ground, Ramp::Flame, 1.0, true),
        (ZoneLook::Firestorm, Ramp::Storm, 2.0, true),
        (ZoneLook::EntropyBloom, Ramp::Void, 3.0, true),
        (ZoneLook::Verdict, Ramp::Storm, 2.0, true),
        (ZoneLook::BindingHex, Ramp::Void, 3.0, true),
        (ZoneLook::StillField, Ramp::Time, 0.0, true),
        (ZoneLook::Decoy, Ramp::ZoneGold, 0.0, true),
        (ZoneLook::Geysers, Ramp::Flame, 1.0, true),
    ];
    let radius = 2.5;
    for (k, (look, ramp, variant, ally)) in looks.iter().enumerate() {
        let at = cell(g.page, center, k);
        let [ink, deep, body, light] = tones(*ramp);
        let size = 2.0 * radius * 1.12 + 0.4;
        let alt = match look {
            ZoneLook::Firestorm => lin(hex("#FF9A3A")),
            ZoneLook::EntropyBloom | ZoneLook::BindingHex => lin(hex("#9BE84A")),
            _ => lin(Ramp::ZoneGold.body()),
        };
        let danger = hex("#FF3B30");
        let alpha = if !ally {
            0.85
        } else if look.set_piece() {
            0.85
        } else {
            0.5
        };
        let params = ZoneParams {
            mode: Vec4::new(look.mode(), *variant, if *ally { 1.0 } else { 4.0 }, k as f32 * 0.137),
            quad: Vec4::new(0.0, 0.0, size, size),
            shape: Vec4::new(radius, 0.0, if *ally { 0.08 } else { 0.09 }, 0.0),
            timing: Vec4::new(now, 4.0, alpha, 1.15),
            ink,
            deep,
            body,
            light,
            hem: if *ally { lin(Ramp::ZoneGold.body()).with_w(0.85) } else { lin(danger).with_w(0.95) },
            alt,
        };
        let (e, _) = zone_quad(commands, mats, mesh, at, FRAC_PI_2, params, -120.0);
        if !ally {
            let mut hem = params;
            hem.mode.z = 2.0;
            zone_quad(commands, mats, mesh, at, FRAC_PI_2, hem, 950.0);
        }
        g.zones.push((e, *look, *ramp, radius, k as f32 * 0.137));
    }
    // Telegraphs: circle, line + cone, ring + ally circle.
    let red = lin(hex("#FF3B30"));
    let tele = |mode: f32, quad: Vec4, shape: Vec4, ally: bool| ZoneParams {
        mode: Vec4::new(mode, 0.0, if ally { 1.0 } else { 0.0 }, 0.4),
        quad,
        shape,
        timing: Vec4::new(now, 2.4, 1.0, 1.0),
        ink: lin(hex("#1A0606")),
        body: if ally { lin(hex("#FFC940")) } else { red },
        light: if ally { lin(hex("#FFF4C8")) } else { Vec4::ONE },
        ..default()
    };
    let m = 0.45;
    let r = 2.4;
    let c17 = cell(g.page, center, 17);
    let (_, h) = zone_quad(
        commands,
        mats,
        mesh,
        c17,
        FRAC_PI_2,
        tele(20.0, Vec4::new(0.0, 0.0, 2.0 * (r + m), 2.0 * (r + m)), Vec4::new(r, 0.0, 0.0, 0.0), false),
        crate::fx::TELEGRAPH_BIAS,
    );
    g.teles.push(h);
    let c18 = cell(g.page, center, 18);
    let (_, h) = zone_quad(
        commands,
        mats,
        mesh,
        c18 - Vec3::X * 3.0 + Vec3::Z * 1.2,
        0.0,
        tele(21.0, Vec4::new(0.0, 3.0, 1.4 + 2.0 * m, 6.0 + 2.0 * m), Vec4::new(6.0, 1.4, 0.0, 0.0), false),
        crate::fx::TELEGRAPH_BIAS,
    );
    g.teles.push(h);
    let (_, h) = zone_quad(
        commands,
        mats,
        mesh,
        c18 - Vec3::X * 2.0 - Vec3::Z * 1.0,
        0.0,
        tele(
            22.0,
            Vec4::new(0.0, 0.0, 2.0 * (3.0 + m), 2.0 * (3.0 + m)),
            Vec4::new(3.0, 35f32.to_radians(), 0.0, 0.0),
            false,
        ),
        crate::fx::TELEGRAPH_BIAS,
    );
    g.teles.push(h);
    let c19 = cell(g.page, center, 19);
    let (_, h) = zone_quad(
        commands,
        mats,
        mesh,
        c19 - Vec3::X * 1.4,
        FRAC_PI_2,
        tele(23.0, Vec4::new(0.0, 0.0, 2.0 * (2.2 + m), 2.0 * (2.2 + m)), Vec4::new(2.2, 1.2, 0.0, 0.0), false),
        crate::fx::TELEGRAPH_BIAS,
    );
    g.teles.push(h);
    let (_, h) = zone_quad(
        commands,
        mats,
        mesh,
        c19 + Vec3::X * 2.2,
        FRAC_PI_2,
        tele(20.0, Vec4::new(0.0, 0.0, 2.0 * (1.4 + m), 2.0 * (1.4 + m)), Vec4::new(1.4, 0.0, 0.0, 0.0), true),
        crate::fx::TELEGRAPH_BIAS,
    );
    g.teles.push(h);
    let _ = w3;
}
