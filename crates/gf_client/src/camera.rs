//! Fixed-angle isometric 3/4 camera (§12): follows the local player across open arenas, leans
//! toward nearby allies, stays over the arena, and shakes on big hits (budgeted and toggleable, §5).

use crate::input::Settings;
use crate::net::{CurrentRoom, Link, Prediction};
use crate::{ClientConfig, ClientSet};
use gf_engine::client::{iso_camera, key_light, set_view_height, vignette};
use gf_engine::prelude::*;
use gf_net::GameEvent;

#[derive(Component)]
pub struct MainCamera;

/// The shadow-casting key light (its colour follows the biome).
#[derive(Component)]
pub struct KeyLight;

/// Where the key light shines from (upper left of the screen), aimed at the origin. The floor
/// paints its stone bevels toward it.
pub const KEY_LIGHT_FROM: Vec3 = Vec3::new(-10.0, 22.0, 9.0);

/// Screen-shake trauma (0..1); shake = trauma².
#[derive(Resource, Default)]
pub struct Shake {
    pub trauma: f32,
    pub focus: Vec2,
    seeded: bool,
}

impl Shake {
    pub fn add(&mut self, amount: f32) {
        self.trauma = (self.trauma + amount).min(1.0);
    }
}

/// Sim ground (x, y) → world (x, height, −y). Screen-up is sim +y.
#[inline]
pub fn w3(p: Vec2, height: f32) -> Vec3 {
    Vec3::new(p.x, height, -p.y)
}

pub fn build(app: &mut App) {
    app.init_resource::<Shake>()
        .add_systems(Startup, setup)
        .add_systems(Update, (shake_from_events, follow).chain().in_set(ClientSet::Presentation));
}

fn setup(mut commands: Commands, cfg: Res<ClientConfig>) {
    let cam = &cfg.content.game.camera;
    commands.spawn((MainCamera, iso_camera(cam.view_height[0], Color::srgb(0.03, 0.02, 0.018)), Transform::default()));
    // Warm key light from the upper left, cool fill from the right: gold light against deep shadow.
    commands.spawn((
        KeyLight,
        key_light(Color::srgb(1.0, 0.84, 0.62), 11_000.0, cfg.shadows),
        Transform::from_translation(KEY_LIGHT_FROM).looking_at(Vec3::ZERO, Vec3::Y),
    ));
    commands.spawn(vignette(0.62));
    commands.spawn((
        DirectionalLight {
            illuminance: 2_200.0,
            shadow_maps_enabled: false,
            color: Color::srgb(0.5, 0.58, 1.0),
            ..default()
        },
        Transform::from_xyz(12.0, 8.0, -6.0).looking_at(Vec3::ZERO, Vec3::Y),
    ));
}

fn shake_from_events(link: Res<Link>, mut shake: ResMut<Shake>) {
    let me = link.slot;
    for ev in &link.fresh_events {
        match *ev {
            GameEvent::PlayerHurt { slot, amount } if Some(slot) == me => shake.add((amount as f32 / 80.0).min(0.35)),
            GameEvent::Explosion { radius_q, .. } if radius_q > 90 => shake.add(0.08),
            GameEvent::Synergy { .. } => shake.add(0.12),
            GameEvent::BossPhase { .. } => shake.add(0.5),
            GameEvent::ArmorBreak { .. } => shake.add(0.3),
            GameEvent::Downed { slot } if Some(slot) == me => shake.add(0.6),
            _ => {}
        }
    }
}

/// Allies closer than this pull the camera toward them; farther ones get off-screen arrows.
pub const ALLY_PULL_RADIUS: f32 = 12.0;

#[allow(clippy::too_many_arguments)]
fn follow(
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    link: Res<Link>,
    pred: Res<Prediction>,
    room: Res<CurrentRoom>,
    settings: Res<Settings>,
    mut shake: ResMut<Shake>,
    mut cams: Query<(&mut Transform, &mut Projection), With<MainCamera>>,
) {
    let Ok((mut tf, mut projection)) = cams.single_mut() else { return };
    let dt = time.delta_secs();
    let cam = &cfg.content.game.camera;
    let Some(world) = &link.latest else { return };
    let party = world.players.len().clamp(1, 4);
    let mut view_h = cam.view_height[party - 1];

    // Focus: the local player (predicted). Arenas are open fields and every client has its own
    // screen, so the camera stays on you and only leans toward allies fighting close by.
    let me = pred.state.map(|s| s.pos + pred.error).or_else(|| link.me().map(|m| m.mover.pos));
    let alive: Vec<Vec2> = world.players.iter().filter(|p| p.life.is_alive()).map(|p| p.mover.pos).collect();
    let mut focus = match me {
        Some(me) => me,
        None if !alive.is_empty() => alive.iter().copied().sum::<Vec2>() / alive.len() as f32,
        None => Vec2::ZERO,
    };
    if let Some(me) = me {
        let near: Vec<Vec2> = alive.iter().copied().filter(|p| p.distance(me) < ALLY_PULL_RADIUS).collect();
        if near.len() > 1 {
            let centroid = near.iter().copied().sum::<Vec2>() / near.len() as f32;
            focus = me.lerp(centroid, 0.35);
            let spread = near.iter().map(|p| p.distance(focus)).fold(0.0, f32::max);
            view_h = view_h.max(spread * 1.5 + 10.0).min(cam.view_height[3] + 4.0);
        }
    }
    // Keep the view over the arena, but let the rim, the cliffs and the abyss below come into
    // view at the edges (the depth is part of the look).
    let half_view = Vec2::new(view_h * 0.5 * 16.0 / 9.0, view_h * 0.5);
    let limit = (room.def.half_extents + Vec2::splat(2.0) - half_view * Vec2::new(0.62, 0.36)).max(Vec2::ZERO);
    focus = focus.clamp(-limit, limit);
    if !shake.seeded {
        shake.focus = focus;
        shake.seeded = true;
    }
    let k = 1.0 - (-8.0 * dt).exp();
    let smoothed = shake.focus + (focus - shake.focus) * k;
    shake.focus = smoothed;
    set_view_height(&mut projection, view_h);

    let pitch = cam.pitch_deg.to_radians();
    let yaw = cam.yaw_deg.to_radians();
    let back = Vec3::new(yaw.sin() * pitch.cos(), pitch.sin(), yaw.cos() * pitch.cos()) * 60.0;
    let target = w3(smoothed, 0.0);
    // Shake: trauma² jitter, budgeted by the accessibility slider.
    shake.trauma = (shake.trauma - dt * 1.6).max(0.0);
    let s = shake.trauma * shake.trauma * settings.screen_shake * 0.6;
    let t = time.elapsed_secs() * 40.0;
    let jitter = Vec3::new((t * 1.3).sin(), 0.0, (t * 1.7 + 1.0).cos()) * s;
    *tf = Transform::from_translation(target + back + jitter).looking_at(target + jitter, Vec3::Y);
}
