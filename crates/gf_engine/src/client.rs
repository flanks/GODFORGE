//! Client-side engine adapters: window, camera, UI widgets, screenshots.
//!
//! UI and rendering APIs churn the most between Bevy releases (0.20 deprecated `ui::Button`,
//! changed font sizes to rem, moved tonemapping…). Every such call goes through here.

use bevy::prelude::*;

pub use bevy::camera::{Hdr, ScalingMode};
pub use bevy::core_pipeline::tonemapping::Tonemapping;
pub use bevy::diagnostic::{Diagnostic, DiagnosticPath, Diagnostics, RegisterDiagnostic};
pub use bevy::input::touch::Touches;
pub use bevy::light::{NotShadowCaster, NotShadowReceiver};
// Custom materials (NPR shading, §12): `ExtendedMaterial<StandardMaterial, X>` + embedded WESL.
pub use bevy::asset::embedded_asset;
pub use bevy::ecs::system::SystemParam;
pub use bevy::pbr::{ExtendedMaterial, MaterialExtension, MaterialPlugin};
pub use bevy::picking::hover::Hovered;
pub use bevy::post_process::bloom::Bloom;
pub use bevy::render::render_resource::Face;
pub use bevy::render::render_resource::{AsBindGroup, ShaderType};
pub use bevy::render::view::screenshot::{Screenshot, save_to_disk};
pub use bevy::shader::ShaderRef;
pub use bevy::ui_widgets::{Activate, Button as UiButton};
pub use bevy::window::{PresentMode, PrimaryWindow, WindowResolution};

/// Default plugins configured for GODFORGE's window.
pub fn default_plugins(title: &str, width: u32, height: u32, vsync: bool) -> bevy::app::PluginGroupBuilder {
    DefaultPlugins.set(WindowPlugin {
        primary_window: Some(Window {
            title: title.into(),
            name: Some("godforge".into()),
            resolution: (width, height).into(),
            present_mode: if vsync { PresentMode::AutoVsync } else { PresentMode::AutoNoVsync },
            ..default()
        }),
        ..default()
    })
}

/// Longest frame of the last second (ms): the number a frame budget is judged by.
const WORST_FRAME: DiagnosticPath = DiagnosticPath::const_new("frame_time_worst");

/// `--fps`: log FPS, the mean frame time, the worst frame of each second and any `extra` custom
/// diagnostics once a second (frame-budget checks at peak horde).
pub fn log_frame_times(app: &mut App, extra: &[DiagnosticPath]) {
    use bevy::diagnostic::{FrameTimeDiagnosticsPlugin, LogDiagnosticsPlugin};
    let filter = [FrameTimeDiagnosticsPlugin::FPS, FrameTimeDiagnosticsPlugin::FRAME_TIME, WORST_FRAME]
        .into_iter()
        .chain(extra.iter().cloned())
        .collect();
    app.register_diagnostic(
        Diagnostic::new(WORST_FRAME).with_suffix("ms").with_max_history_length(1).with_smoothing_factor(0.0),
    )
    .add_plugins((FrameTimeDiagnosticsPlugin::default(), LogDiagnosticsPlugin::filtered(filter)))
    .add_systems(Update, measure_worst_frame);
}

fn measure_worst_frame(time: Res<Time<Real>>, mut diagnostics: Diagnostics, mut window: Local<(f32, f32)>) {
    let dt = time.delta_secs();
    window.0 += dt;
    window.1 = window.1.max(dt);
    if window.0 >= 1.0 {
        let worst = f64::from(window.1) * 1000.0;
        diagnostics.add_measurement(&WORST_FRAME, || worst);
        *window = (0.0, 0.0);
    }
}

/// Fixed-angle isometric 3/4 camera (§12): orthographic, HDR, bloom for gold/ichor emissives.
pub fn iso_camera(view_height: f32, clear: Color) -> impl Bundle {
    (
        Camera3d::default(),
        Camera { clear_color: ClearColorConfig::Custom(clear), ..default() },
        Projection::from(OrthographicProjection {
            scaling_mode: ScalingMode::FixedVertical { viewport_height: view_height },
            ..OrthographicProjection::default_3d()
        }),
        Hdr,
        Tonemapping::TonyMcMapface,
        Bloom { intensity: 0.22, ..Bloom::NATURAL },
        painterly_grade(),
    )
}

/// Painterly colour grade: richer saturation in the shadows and midtones (Hades-style colour
/// shadows instead of grey ones), a touch of midtone contrast, highlights left clean.
fn painterly_grade() -> bevy::render::view::ColorGrading {
    use bevy::render::view::{ColorGrading, ColorGradingGlobal, ColorGradingSection};
    ColorGrading {
        global: ColorGradingGlobal { post_saturation: 1.06, ..default() },
        shadows: ColorGradingSection { saturation: 1.2, contrast: 1.04, ..default() },
        midtones: ColorGradingSection { saturation: 1.12, contrast: 1.06, ..default() },
        highlights: ColorGradingSection { saturation: 1.02, ..default() },
    }
}

/// Directional key light. With `shadows`, one cascade sized for the fixed iso camera (the whole
/// arena sits 40–100 units from the lens), which is cheap enough for PC-min and Deck.
pub fn key_light(color: Color, illuminance: f32, shadows: bool) -> impl Bundle {
    use bevy::light::CascadeShadowConfigBuilder;
    (
        DirectionalLight { illuminance, color, shadow_maps_enabled: shadows, ..default() },
        CascadeShadowConfigBuilder {
            num_cascades: 1,
            minimum_distance: 20.0,
            maximum_distance: 130.0,
            first_cascade_far_bound: 130.0,
            ..default()
        }
        .build(),
    )
}

/// Full-screen radial vignette drawn under the HUD (focus toward the fight, §12).
pub fn vignette(strength: f32) -> impl Bundle {
    use bevy::ui::{ColorStop, Gradient, RadialGradient, RadialGradientShape, UiPosition};
    (
        Node {
            position_type: PositionType::Absolute,
            width: Val::Percent(100.0),
            height: Val::Percent(100.0),
            ..default()
        },
        BackgroundGradient(vec![Gradient::Radial(RadialGradient::new(
            UiPosition::CENTER,
            RadialGradientShape::FarthestCorner,
            vec![
                ColorStop::percent(Color::NONE, 52.0),
                ColorStop::percent(Color::srgba(0.0, 0.0, 0.0, strength), 100.0),
            ],
        ))]),
        GlobalZIndex(-10),
    )
}

/// Change an orthographic camera's visible height (co-op zoom-out).
pub fn set_view_height(projection: &mut Projection, view_height: f32) {
    if let Projection::Orthographic(ortho) = projection {
        ortho.scaling_mode = ScalingMode::FixedVertical { viewport_height: view_height };
    }
}

/// A text bundle with a fixed pixel size.
pub fn text(s: impl Into<String>, px: f32, color: Color) -> impl Bundle {
    (Text::new(s), TextFont { font_size: bevy::text::FontSize::Px(px), ..default() }, TextColor(color))
}

/// Text in a specific font face (headings use the display face).
pub fn text_in(s: impl Into<String>, px: f32, color: Color, font: &Handle<Font>) -> impl Bundle {
    (
        Text::new(s),
        TextFont { font: font.clone().into(), font_size: bevy::text::FontSize::Px(px), ..default() },
        TextColor(color),
    )
}

/// Install the UI fonts. `body` replaces Bevy's built-in ASCII-only default font, so every
/// `TextFont::default()` renders full punctuation (· — → ◆ ∞). `display` is returned for headings.
pub fn install_fonts(app: &mut App, body: &'static [u8], display: &'static [u8]) -> Handle<Font> {
    let mut fonts = app.world_mut().resource_mut::<Assets<Font>>();
    let _ = fonts.insert(AssetId::default(), Font::from_bytes(body.to_vec()));
    fonts.add(Font::from_bytes(display.to_vec()))
}

/// Set a text node's font size in pixels.
pub fn font_px(px: f32) -> TextFont {
    TextFont { font_size: bevy::text::FontSize::Px(px), ..default() }
}

/// A clickable button (headless widget + our styling). Pair with a global `On<Activate>` observer.
pub fn button(node: Node, background: Color, border: Color) -> impl Bundle {
    (UiButton, Hovered::default(), node, BackgroundColor(background), BorderColor::all(border))
}

/// Is a button currently hovered?
pub fn is_hovered(h: &Hovered) -> bool {
    h.get()
}

/// Queue a screenshot of the primary window to `path`.
pub fn take_screenshot(commands: &mut Commands, path: std::path::PathBuf) {
    commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path));
}

/// Project a world point to viewport pixels.
pub fn world_to_screen(camera: &Camera, cam_tf: &GlobalTransform, world: Vec3) -> Option<Vec2> {
    camera.world_to_viewport(cam_tf, world).ok()
}

/// Ray from the cursor onto the y = 0 ground plane.
pub fn cursor_to_ground(camera: &Camera, cam_tf: &GlobalTransform, cursor: Vec2) -> Option<Vec3> {
    let ray = camera.viewport_to_world(cam_tf, cursor).ok()?;
    ray.plane_intersection_point(Vec3::ZERO, InfinitePlane3d::new(Vec3::Y))
}

/// Indexed triangle-list mesh from raw attributes (procedural platforms, cliffs).
pub fn triangle_mesh(positions: Vec<[f32; 3]>, normals: Vec<[f32; 3]>, uvs: Vec<[f32; 2]>, indices: Vec<u32>) -> Mesh {
    use bevy::asset::RenderAssetUsages;
    use bevy::mesh::{Indices, PrimitiveTopology};
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, uvs)
        .with_inserted_indices(Indices::U32(indices))
}

/// Build an sRGB RGBA8 texture from raw pixels (procedural painterly ground, VFX sprites).
pub fn rgba_image(width: u32, height: u32, data: Vec<u8>, repeat: bool) -> Image {
    use bevy::asset::RenderAssetUsages;
    use bevy::image::{ImageAddressMode, ImageFilterMode};
    use bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
    let mut image = Image::new(
        Extent3d { width, height, depth_or_array_layers: 1 },
        TextureDimension::D2,
        data,
        TextureFormat::Rgba8UnormSrgb,
        RenderAssetUsages::RENDER_WORLD | RenderAssetUsages::MAIN_WORLD,
    );
    if repeat {
        image
            .sampler
            .get_or_init_descriptor()
            .set_address_mode(ImageAddressMode::Repeat)
            .set_filter(ImageFilterMode::Linear);
    }
    image
}
