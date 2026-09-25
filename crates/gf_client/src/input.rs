//! Devices → intent. Keyboard/mouse, gamepad and touch (virtual twin-stick, designed in for the
//! mobile port) all fill one [`InputState`]; aim-mode switching is live and free (§5).

use crate::camera::MainCamera;
use crate::net::{Link, Prediction};
use crate::{ClientConfig, ClientSet};
use gf_core::aim::{AimMode, TargetBias};
use gf_engine::client::{Touches, cursor_to_ground};
use gf_engine::prelude::*;
use gf_net::quant::{angle_to_u16, stick_to_i8};
use gf_net::{PlayerAction, PlayerCommand, Presses};
use gf_sim::bot::BotBrain;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Device {
    #[default]
    KeyboardMouse,
    Gamepad,
    Touch,
}

#[derive(Resource)]
pub struct InputState {
    pub move_dir: Vec2,
    pub aim_dir: Vec2,
    pub aim_dist: f32,
    pub fire: bool,
    pub presses: Presses,
    pub aim_mode: AimMode,
    pub bias: TargetBias,
    pub forge_open: bool,
    pub actions: Vec<PlayerAction>,
    pub device: Device,
    /// Cursor on the ground plane (sim coordinates), for the reticle.
    pub cursor_ground: Option<Vec2>,
    /// UI panel has focus: gameplay mouse buttons are ignored.
    pub ui_captures: bool,
    /// Touch sticks (origin, current) for the on-screen overlay.
    pub touch_move: Option<(Vec2, Vec2)>,
    pub touch_aim: Option<(Vec2, Vec2)>,
}

impl InputState {
    pub fn command(&self) -> PlayerCommand {
        PlayerCommand {
            seq: 0,
            move_dir: stick_to_i8(self.move_dir),
            aim: angle_to_u16(self.aim_dir),
            aim_dist: (self.aim_dist * 64.0).clamp(0.0, 60000.0) as u16,
            fire: self.fire,
            presses: self.presses,
            aim_mode: self.aim_mode,
            bias: self.bias,
            forge_open: self.forge_open,
            action: None,
        }
    }

    fn press(counter: &mut u8) {
        *counter = counter.wrapping_add(1);
    }
}

#[derive(Resource)]
pub struct Autopilot(pub Option<BotBrain>);

/// Accessibility / feel toggles.
#[derive(Resource)]
pub struct Settings {
    pub damage_numbers: bool,
    pub screen_shake: f32,
    pub help: bool,
}

pub fn build(app: &mut App) {
    let cfg = app.world().resource::<ClientConfig>().clone();
    app.insert_resource(InputState {
        move_dir: Vec2::ZERO,
        aim_dir: Vec2::Y,
        aim_dist: 6.0,
        fire: false,
        presses: Presses::default(),
        aim_mode: cfg.aim_mode,
        bias: TargetBias::Balanced,
        forge_open: false,
        actions: Vec::new(),
        device: Device::KeyboardMouse,
        cursor_ground: None,
        ui_captures: false,
        touch_move: None,
        touch_aim: None,
    })
    .insert_resource(Autopilot(cfg.autoplay.then(|| BotBrain::new(0, cfg.aim_mode, 0xB0B))))
    .insert_resource(Settings { damage_numbers: cfg.damage_numbers, screen_shake: cfg.screen_shake, help: false })
    .add_systems(Update, (read_keyboard_mouse, read_gamepad, read_touch, autopilot).chain().in_set(ClientSet::Input));
}

fn player_pos(link: &Link, pred: &Prediction) -> Option<Vec2> {
    pred.state.map(|s| s.pos).or_else(|| link.me().map(|m| m.mover.pos))
}

#[allow(clippy::too_many_arguments)]
fn read_keyboard_mouse(
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    windows: Query<&Window>,
    cameras: Query<(&Camera, &GlobalTransform), With<MainCamera>>,
    link: Res<Link>,
    pred: Res<Prediction>,
    auto: Res<Autopilot>,
    mut settings: ResMut<Settings>,
    mut input: ResMut<InputState>,
) {
    // Toggles work even under autopilot.
    if keys.just_pressed(KeyCode::F1) {
        input.aim_mode = AimMode::Auto;
    }
    if keys.just_pressed(KeyCode::F2) {
        input.aim_mode = AimMode::Assisted;
    }
    if keys.just_pressed(KeyCode::F3) {
        input.aim_mode = AimMode::Manual;
    }
    if keys.just_pressed(KeyCode::KeyM) {
        input.aim_mode = input.aim_mode.next();
    }
    if keys.just_pressed(KeyCode::KeyB) {
        input.bias = input.bias.next();
    }
    if keys.just_pressed(KeyCode::KeyN) {
        settings.damage_numbers = !settings.damage_numbers;
    }
    if keys.just_pressed(KeyCode::KeyK) {
        settings.screen_shake = if settings.screen_shake > 0.0 { 0.0 } else { 1.0 };
    }
    if keys.just_pressed(KeyCode::KeyH) {
        settings.help = !settings.help;
    }
    if auto.0.is_some() {
        return;
    }
    let mut dir = Vec2::ZERO;
    if keys.pressed(KeyCode::KeyW) || keys.pressed(KeyCode::ArrowUp) {
        dir.y += 1.0;
    }
    if keys.pressed(KeyCode::KeyS) || keys.pressed(KeyCode::ArrowDown) {
        dir.y -= 1.0;
    }
    if keys.pressed(KeyCode::KeyD) || keys.pressed(KeyCode::ArrowRight) {
        dir.x += 1.0;
    }
    if keys.pressed(KeyCode::KeyA) || keys.pressed(KeyCode::ArrowLeft) {
        dir.x -= 1.0;
    }
    let any_key = keys.get_just_pressed().next().is_some();
    if any_key || mouse.get_just_pressed().next().is_some() {
        input.device = Device::KeyboardMouse;
    }
    if input.device != Device::KeyboardMouse {
        return;
    }
    input.move_dir = dir.normalize_or_zero();

    // Mouse aim: cursor ray onto the ground, relative to the (predicted) player.
    if let (Ok(window), Ok((camera, cam_tf)), Some(me)) = (windows.single(), cameras.single(), player_pos(&link, &pred))
        && let Some(cursor) = window.cursor_position()
        && let Some(ground) = cursor_to_ground(camera, cam_tf, cursor)
    {
        let g = Vec2::new(ground.x, -ground.z);
        input.cursor_ground = Some(g);
        let to = g - me;
        if to.length() > 0.2 {
            input.aim_dir = to.normalize();
            input.aim_dist = to.length();
        }
    }
    let ui = input.ui_captures;
    input.fire = !ui && mouse.pressed(MouseButton::Left);
    let presses = &mut input.presses;
    if keys.just_pressed(KeyCode::Space) {
        InputState::press(&mut presses.dash);
    }
    if keys.just_pressed(KeyCode::KeyQ) {
        InputState::press(&mut presses.active1);
    }
    if keys.just_pressed(KeyCode::KeyE) || (!ui && mouse.just_pressed(MouseButton::Right)) {
        InputState::press(&mut presses.active2);
    }
    if keys.just_pressed(KeyCode::KeyR) {
        InputState::press(&mut presses.ult);
    }
    if keys.just_pressed(KeyCode::KeyF) {
        InputState::press(&mut presses.interact);
    }
    if keys.just_pressed(KeyCode::KeyV) {
        InputState::press(&mut presses.overdrive);
    }
    if keys.just_pressed(KeyCode::KeyT) {
        InputState::press(&mut presses.force_target);
    }
    if keys.just_pressed(KeyCode::KeyG) || mouse.just_pressed(MouseButton::Middle) {
        InputState::press(&mut presses.ping);
    }
}

fn read_gamepad(gamepads: Query<&Gamepad>, auto: Res<Autopilot>, mut input: ResMut<InputState>) {
    if auto.0.is_some() {
        return;
    }
    let Some(pad) = gamepads.iter().next() else { return };
    let stick = |x: GamepadAxis, y: GamepadAxis| Vec2::new(pad.get(x).unwrap_or(0.0), pad.get(y).unwrap_or(0.0));
    let left = stick(GamepadAxis::LeftStickX, GamepadAxis::LeftStickY);
    let right = stick(GamepadAxis::RightStickX, GamepadAxis::RightStickY);
    let active = left.length() > 0.2 || right.length() > 0.2 || pad.get_just_pressed().next().is_some();
    if active {
        input.device = Device::Gamepad;
    }
    if input.device != Device::Gamepad {
        return;
    }
    input.move_dir = if left.length() > 0.15 { left.clamp_length_max(1.0) } else { Vec2::ZERO };
    if right.length() > 0.3 {
        input.aim_dir = right.normalize();
        input.aim_dist = 8.0;
    } else if input.move_dir != Vec2::ZERO && input.aim_mode != AimMode::Manual {
        input.aim_dir = input.move_dir.normalize();
    }
    input.fire = pad.get(GamepadButton::RightTrigger2).unwrap_or(0.0) > 0.35;
    let presses = &mut input.presses;
    if pad.just_pressed(GamepadButton::RightTrigger) || pad.just_pressed(GamepadButton::South) {
        InputState::press(&mut presses.dash);
    }
    if pad.just_pressed(GamepadButton::LeftTrigger) {
        InputState::press(&mut presses.active1);
    }
    if pad.just_pressed(GamepadButton::LeftTrigger2) {
        InputState::press(&mut presses.active2);
    }
    if pad.just_pressed(GamepadButton::North) {
        InputState::press(&mut presses.ult);
    }
    if pad.just_pressed(GamepadButton::West) {
        InputState::press(&mut presses.interact);
    }
    if pad.just_pressed(GamepadButton::East) {
        InputState::press(&mut presses.overdrive);
    }
    if pad.just_pressed(GamepadButton::RightThumb) {
        InputState::press(&mut presses.ping);
    }
    if pad.just_pressed(GamepadButton::DPadUp) {
        input.aim_mode = input.aim_mode.next();
    }
    if pad.just_pressed(GamepadButton::DPadRight) {
        input.bias = input.bias.next();
    }
}

/// Touch layer: left half is a floating move stick, right half a floating aim-and-fire stick,
/// bottom-right corner zones are ability buttons (hit targets ≥ 44 px, §20.6).
fn read_touch(touches: Res<Touches>, windows: Query<&Window>, auto: Res<Autopilot>, mut input: ResMut<InputState>) {
    if auto.0.is_some() {
        return;
    }
    let Ok(window) = windows.single() else { return };
    let size = Vec2::new(window.width(), window.height());
    if touches.iter().next().is_some() && input.device != Device::Touch {
        input.device = Device::Touch;
        input.aim_mode = AimMode::Auto;
    }
    if input.device != Device::Touch {
        return;
    }
    let mut move_touch = None;
    let mut aim_touch = None;
    for t in touches.iter() {
        let start = t.start_position();
        let n = start / size;
        if touches.just_pressed(t.id()) {
            for (zone, which) in crate::hud::TOUCH_BUTTONS {
                if (n - zone).length() < 0.06 {
                    let p = &mut input.presses;
                    match which {
                        0 => InputState::press(&mut p.dash),
                        1 => InputState::press(&mut p.active1),
                        2 => InputState::press(&mut p.active2),
                        3 => InputState::press(&mut p.ult),
                        _ => InputState::press(&mut p.interact),
                    }
                }
            }
        }
        if crate::hud::TOUCH_BUTTONS.iter().any(|(z, _)| (n - *z).length() < 0.06) {
            continue;
        }
        if n.x < 0.5 {
            move_touch = Some((start, t.position()));
        } else {
            aim_touch = Some((start, t.position()));
        }
    }
    input.touch_move = move_touch;
    input.touch_aim = aim_touch;
    input.move_dir = move_touch.map_or(Vec2::ZERO, |(a, b)| {
        let d = b - a;
        Vec2::new(d.x, -d.y).clamp_length_max(70.0) / 70.0
    });
    input.fire = false;
    if let Some((a, b)) = aim_touch {
        let d = b - a;
        if d.length() > 12.0 {
            input.aim_dir = Vec2::new(d.x, -d.y).normalize();
            input.aim_dist = 8.0;
            input.fire = true;
        }
    }
}

fn autopilot(cfg: Res<ClientConfig>, link: Res<Link>, mut auto: ResMut<Autopilot>, mut input: ResMut<InputState>) {
    let Some(brain) = auto.0.as_mut() else { return };
    let (Some(slot), Some(world)) = (link.slot, link.latest.as_ref()) else { return };
    brain.slot = slot;
    brain.mode = input.aim_mode;
    let (cmd, action) = brain.think(world, &cfg.content);
    input.move_dir = gf_net::quant::i8_to_stick(cmd.move_dir);
    input.aim_dir = gf_net::quant::u16_to_dir(cmd.aim);
    input.aim_dist = cmd.aim_dist as f32 / 64.0;
    input.fire = cmd.fire;
    input.presses = cmd.presses;
    input.forge_open = cmd.forge_open;
    if let Some(a) = action {
        input.actions.push(a);
    }
}
