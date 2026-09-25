//! # gf_client — presentation over the authoritative simulation
//!
//! The client never simulates the game. It samples input into commands at the sim rate,
//! predicts only its own movement (shared `gf_core::movement`), renders replicated snapshots and
//! draws the HUD / forge UI. Even solo, the host sim runs on its own thread behind a loopback
//! transport, so single-player and co-op share every code path (§20.3).

pub mod camera;
pub mod hud;
pub mod input;
pub mod net;
pub mod palette;
pub mod scene;
pub mod ui;
pub mod vfx;

use gf_content::ContentDb;
use gf_core::aim::AimMode;
use gf_engine::client::take_screenshot;
use gf_engine::prelude::*;
use gf_net::Loadout;
use gf_sim::SimConfig;
use std::path::PathBuf;
use std::sync::Arc;

/// How this client reaches a host.
#[derive(Clone, Debug)]
pub enum Connect {
    /// Solo / local: run the host sim on a thread, connect over loopback.
    Local(SimConfig),
    /// Listen server: local player over loopback + remote players over UDP on `port`.
    Host(SimConfig, u16),
    /// Join a remote host over UDP.
    Join(String),
}

#[derive(Resource, Clone)]
pub struct ClientConfig {
    pub content: Arc<ContentDb>,
    pub name: String,
    pub loadout: Loadout,
    pub aim_mode: AimMode,
    pub connect: Connect,
    /// A bot drives this client's inputs (attract mode, screenshots, soak tests).
    pub autoplay: bool,
    /// Bot teammates joining our own host over loopback (solo/host only).
    pub party: Vec<Loadout>,
    /// Save a screenshot to each `path` after `seconds` of play (marketing captures, CI smoke).
    pub screenshots: Vec<(PathBuf, f32)>,
    pub exit_after: Option<f32>,
    pub damage_numbers: bool,
    /// Screen shake strength 0..=1 (accessibility toggle, §5).
    pub screen_shake: f32,
    /// Directional shadows (off for low tiers / software rendering).
    pub shadows: bool,
}

/// Wires every client system.
pub struct ClientPlugin(pub ClientConfig);

/// Heading face (body text uses the replaced default font).
#[derive(Resource, Clone)]
pub struct UiFonts {
    pub display: Handle<Font>,
}

const BODY_FONT: &[u8] = include_bytes!("../../../assets/fonts/DejaVuSans.ttf");
const DISPLAY_FONT: &[u8] = include_bytes!("../../../assets/fonts/DejaVuSerif-Bold.ttf");

/// Frame phases, ordered.
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub enum ClientSet {
    Net,
    Input,
    Scene,
    Presentation,
}

impl Plugin for ClientPlugin {
    fn build(&self, app: &mut App) {
        let cfg = self.0.clone();
        let display = gf_engine::client::install_fonts(app, BODY_FONT, DISPLAY_FONT);
        app.insert_resource(UiFonts { display })
            .insert_resource(cfg.clone())
            .insert_resource(Time::<Fixed>::from_hz(gf_core::SIM_HZ as f64))
            .insert_resource(ClearColor(Color::srgb(0.03, 0.02, 0.018)))
            .insert_resource(GlobalAmbientLight { color: Color::srgb(1.0, 0.85, 0.7), brightness: 170.0, ..default() })
            .configure_sets(
                Update,
                (ClientSet::Net, ClientSet::Input, ClientSet::Scene, ClientSet::Presentation).chain(),
            );
        app.add_systems(Last, automation);
        net::build(app);
        input::build(app);
        palette::build(app);
        camera::build(app);
        scene::build(app);
        vfx::build(app);
        hud::build(app);
        ui::build(app);
    }
}

/// Scripted screenshots and timed exit (attract mode, CI smoke tests, store captures).
fn automation(
    mut commands: Commands,
    time: Res<Time>,
    cfg: Res<ClientConfig>,
    mut taken: Local<usize>,
    mut exits: MessageWriter<AppExit>,
) {
    let t = time.elapsed_secs();
    while let Some((path, at)) = cfg.screenshots.get(*taken)
        && t >= *at
    {
        info!("screenshot → {}", path.display());
        take_screenshot(&mut commands, path.clone());
        *taken += 1;
    }
    if cfg.exit_after.is_some_and(|limit| t >= limit) {
        exits.write(AppExit::Success);
    }
}
