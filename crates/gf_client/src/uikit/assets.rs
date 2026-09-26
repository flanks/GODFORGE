//! Embedded UI art: the texture kit (lane T) and the icon masters (lane I).
//!
//! **Loading choice.** Every PNG is compiled into the binary (`build.rs` turns
//! `assets/ui/ui_kit.json` and `assets/ui/icons/icons.json` into `include_bytes!` tables), like
//! the fonts. The game therefore runs from any working directory and from a packaged build
//! without an asset folder, and a missing file is a build error rather than a blank HUD.
//!
//! **Lazy decode.** Handles for every texture and icon level are reserved at startup, so widget
//! code can clone them freely (`Res<UiKit>` is read-only). The PNG is decoded the first time an
//! `ImageNode` or `InlineImage` using one of its handles appears ([`materialize`]); unused art
//! costs neither decode time nor GPU memory. Icons get three levels, 128/64/32, built with a
//! premultiplied 2×2 box filter in linear light (Bevy UI has no mipmaps, §9.2); [`UiIcon`] picks
//! the level from the logical size × UiScale and re-picks when the scale changes.

use crate::theme::UiFonts;
use gf_engine::client::{decode_png_rgba, ui_image};
use gf_engine::prelude::*;
use std::collections::{HashMap, HashSet};

/// How a kit texture maps onto its node (from the manifest).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum KitMode {
    /// 9-slice, corners at `max_corner_scale: 0.5` (the @2x rule, §8.2).
    NineSlice,
    /// Left/right caps with a stretched middle.
    ThreeSliceH,
    /// Stretched to the node.
    Stretch,
    /// Pre-sized: draw at `logical` (stretch to a node of exactly that size).
    Fixed,
    /// Repeats horizontally at its logical width (the ward hatch).
    Tiled,
}

/// One texture of the kit, as the manifest describes it.
#[derive(Debug)]
pub struct KitEntry {
    /// Path under `assets/ui/`, e.g. `frames/gilt_panel@2x.png`.
    pub path: &'static str,
    pub bytes: &'static [u8],
    /// Texture size in px.
    pub size: [u32; 2],
    /// Size in logical px at UiScale 1 (half the texture: every kit texture is @2x).
    pub logical: [f32; 2],
    pub mode: KitMode,
    /// Slice insets in texture px: left, top, right, bottom.
    pub slice: [f32; 4],
    /// For sliced textures whose sides tile: logical px per repeat (0 = sides stretch).
    pub side_tile: f32,
}

include!(concat!(env!("OUT_DIR"), "/ui_assets.rs"));

impl KitEntry {
    /// The `NodeImageMode` this texture wants.
    pub fn image_mode(&self) -> NodeImageMode {
        match self.mode {
            KitMode::NineSlice | KitMode::ThreeSliceH => {
                let [l, t, r, b] = self.slice;
                let sides = if self.side_tile > 0.0 {
                    let side_px = (self.size[0] as f32 - l - r).max(1.0);
                    SliceScaleMode::Tile { stretch_value: self.side_tile / side_px }
                } else {
                    SliceScaleMode::Stretch
                };
                NodeImageMode::Sliced(TextureSlicer {
                    border: BorderRect { min_inset: Vec2::new(l, t), max_inset: Vec2::new(r, b) },
                    center_scale_mode: SliceScaleMode::Stretch,
                    sides_scale_mode: sides,
                    max_corner_scale: 0.5,
                })
            }
            KitMode::Tiled => NodeImageMode::Tiled {
                tile_x: true,
                tile_y: false,
                stretch_value: self.logical[0] / self.size[0].max(1) as f32,
            },
            KitMode::Stretch | KitMode::Fixed => NodeImageMode::Stretch,
        }
    }

    pub fn logical_size(&self) -> Vec2 {
        Vec2::new(self.logical[0], self.logical[1])
    }
}

/// Icon level sizes in px (§9.2).
pub const ICON_LEVELS: [u32; 3] = [32, 64, 128];

/// Exact sizes for icons inside running text (`InlineImage` boxes take the image's pixel size as
/// logical px, §11.7).
pub const ICON_INLINE: [u32; 3] = [16, 20, 24];

struct IconEntry {
    /// Handles for the 32, 64 and 128 px levels.
    levels: [Handle<Image>; 3],
    /// Handles for the 16, 20 and 24 px inline sizes.
    inline: [Handle<Image>; 3],
    category: &'static str,
}

/// Fonts, kit textures and icons, ready for widget code. Read-only after startup.
#[derive(Resource)]
pub struct UiKit {
    pub fonts: UiFonts,
    tex: HashMap<&'static str, (Handle<Image>, &'static KitEntry)>,
    icons: HashMap<&'static str, IconEntry>,
    /// Icon keys in manifest (sorted) order: the QA icon board walks these.
    pub icon_keys: Vec<&'static str>,
}

/// Where a reserved handle's pixels come from.
#[derive(Clone, Copy)]
enum Source {
    Kit(&'static KitEntry),
    /// Index into [`ICONS`]; decoding one level decodes every level and inline size.
    Icon(usize),
}

/// Handles reserved but not decoded yet.
#[derive(Resource, Default)]
pub struct UiDecode {
    pending: HashMap<AssetId<Image>, Source>,
    icon_handles: HashMap<usize, [Handle<Image>; 6]>,
    /// Handles the next [`materialize`] must decode even if no node shows them yet (material
    /// textures).
    forced: Vec<AssetId<Image>>,
    warned: HashSet<String>,
}

impl UiDecode {
    /// Decode this handle's pixels on the next frame even if no `ImageNode` uses it (for
    /// `UiMaterial` textures).
    pub fn request(&mut self, handle: &Handle<Image>) {
        self.forced.push(handle.id());
    }
}

/// Group fallbacks for a missing icon key (§9.2): the generic glyph of its group.
fn fallback_icon(key: &str) -> &'static str {
    match key.split('/').next().unwrap_or("") {
        "parts" => "slots/core",
        "boons" | "boon_kind" => "run/named_combo",
        "chassis" => "chassis/colossus_cannon",
        "portraits" => "states/downed",
        "kits" => "team/ult_ready",
        "gods" => "run/named_combo",
        "elements" | "status" => "elements/kinetic",
        "poi" => "poi/gate",
        "input" => "input/pad_south",
        _ => "ui/info",
    }
}

impl UiKit {
    /// A kit texture as an `ImageNode` with the manifest's image mode. Unknown paths log once and
    /// draw nothing.
    pub fn tex(&self, path: &str) -> ImageNode {
        match self.tex.get(path) {
            // Kit art covers the whole border box: frames and caps sit around the padding.
            Some((handle, entry)) => ImageNode {
                image: handle.clone(),
                image_mode: entry.image_mode(),
                visual_box: VisualBox::BorderBox,
                ..default()
            },
            None => {
                warn_once!("ui kit: no texture {path}");
                ImageNode::default()
            }
        }
    }

    /// A kit texture tinted by `color` (multiply).
    pub fn tex_tinted(&self, path: &str, color: Color) -> ImageNode {
        ImageNode { color, ..self.tex(path) }
    }

    /// The manifest entry of a kit texture.
    pub fn entry(&self, path: &str) -> Option<&'static KitEntry> {
        self.tex.get(path).map(|(_, e)| *e)
    }

    /// The handle of a kit texture (for materials).
    pub fn tex_handle(&self, path: &str) -> Handle<Image> {
        self.tex.get(path).map(|(h, _)| h.clone()).unwrap_or_default()
    }

    /// Does an icon exist for this key (`<group>/<name>`)?
    pub fn has_icon(&self, key: &str) -> bool {
        self.icons.contains_key(key)
    }

    /// The icon's category from `icons.json`.
    pub fn icon_category(&self, key: &str) -> &'static str {
        self.icons.get(key).map_or("", |e| e.category)
    }

    /// The handle of the smallest icon level at least `physical_px` wide. A missing key falls back
    /// to its group's generic glyph and logs once.
    pub fn icon_handle(&self, key: &str, physical_px: f32) -> Handle<Image> {
        let entry = match self.icons.get(key) {
            Some(e) => e,
            None => {
                warn_once!("ui kit: no icon {key}; using its group fallback");
                match self.icons.get(fallback_icon(key)) {
                    Some(e) => e,
                    None => return Handle::default(),
                }
            }
        };
        let level = ICON_LEVELS.iter().position(|&l| l as f32 >= physical_px - 0.5).unwrap_or(ICON_LEVELS.len() - 1);
        entry.levels[level].clone()
    }

    /// An icon for running text (§11.7), as a child of a `Text` next to its `TextSpan`s: the
    /// nearest inline size (16, 20 or 24 logical px) to `px`, tinted by `tint`.
    pub fn inline_icon(&self, key: &str, px: f32, tint: Color) -> InlineImage {
        let entry = self.icons.get(key).or_else(|| self.icons.get(fallback_icon(key)));
        let Some(entry) = entry else { return InlineImage::default() };
        let i = ICON_INLINE
            .iter()
            .enumerate()
            .min_by(|a, b| (*a.1 as f32 - px).abs().total_cmp(&(*b.1 as f32 - px).abs()))
            .map_or(1, |(i, _)| i);
        InlineImage { image: entry.inline[i].clone(), color: tint }
    }
}

/// An icon by key at a logical size. The image level follows UiScale; tint through the node's
/// `ImageNode.color`. Size the node yourself (the builders in `uikit` do).
#[derive(Component, Clone, Debug, PartialEq)]
#[require(ImageNode)]
pub struct UiIcon {
    pub key: String,
    pub px: f32,
}

impl UiIcon {
    pub fn new(key: impl Into<String>, px: f32) -> Self {
        Self { key: key.into(), px }
    }
}

/// Reserve every handle and build the [`UiKit`] resource.
pub fn install(app: &mut App, fonts: UiFonts) {
    let mut decode = UiDecode::default();
    let world = app.world_mut();
    let images = world.resource_mut::<Assets<Image>>();
    let mut tex = HashMap::with_capacity(KIT.len());
    for entry in KIT {
        let handle = images.reserve_handle();
        decode.pending.insert(handle.id(), Source::Kit(entry));
        tex.insert(entry.path, (handle, entry));
    }
    let mut icons = HashMap::with_capacity(ICONS.len());
    let mut icon_keys = Vec::with_capacity(ICONS.len());
    for (i, (key, category, _)) in ICONS.iter().enumerate() {
        let levels = [images.reserve_handle(), images.reserve_handle(), images.reserve_handle()];
        let inline = [images.reserve_handle(), images.reserve_handle(), images.reserve_handle()];
        for h in levels.iter().chain(&inline) {
            decode.pending.insert(h.id(), Source::Icon(i));
        }
        decode.icon_handles.insert(
            i,
            [
                levels[0].clone(),
                levels[1].clone(),
                levels[2].clone(),
                inline[0].clone(),
                inline[1].clone(),
                inline[2].clone(),
            ],
        );
        icons.insert(*key, IconEntry { levels, inline, category });
        icon_keys.push(*key);
    }
    world.insert_resource(UiKit { fonts, tex, icons, icon_keys });
    world.insert_resource(decode);
}

/// Pick icon levels for new or resized icons, and re-pick everything when UiScale changes.
pub fn resolve_icons(
    kit: Res<UiKit>,
    scale: Res<UiScale>,
    windows: Query<&Window, With<gf_engine::client::PrimaryWindow>>,
    mut icons: Query<(Ref<UiIcon>, &mut ImageNode)>,
) {
    let factor = windows.single().map_or(1.0, |w| w.resolution.scale_factor());
    let rescale = scale.is_changed();
    for (icon, mut node) in &mut icons {
        if !(rescale || icon.is_changed()) {
            continue;
        }
        let handle = kit.icon_handle(&icon.key, icon.px * scale.0 * factor);
        if node.image != handle {
            node.image = handle;
        }
    }
}

/// Decode the pixels of every reserved handle a node has started to show.
pub fn materialize(
    mut decode: ResMut<UiDecode>,
    mut images: ResMut<Assets<Image>>,
    nodes: Query<&ImageNode, Changed<ImageNode>>,
    inline: Query<&InlineImage, Changed<InlineImage>>,
) {
    if decode.pending.is_empty() {
        return;
    }
    let mut wanted: Vec<AssetId<Image>> = std::mem::take(&mut decode.forced);
    wanted.extend(nodes.iter().map(|n| n.image.id()));
    wanted.extend(inline.iter().map(|n| n.image.id()));
    for id in wanted {
        let Some(source) = decode.pending.remove(&id) else { continue };
        match source {
            Source::Kit(entry) => match decode_png_rgba(entry.bytes) {
                Some((w, h, px)) => {
                    let _ = images.insert(id, ui_image(w, h, px));
                }
                None => warn_bad(&mut decode, entry.path),
            },
            Source::Icon(i) => {
                let Some(levels) = decode.icon_handles.remove(&i) else { continue };
                for h in &levels {
                    decode.pending.remove(&h.id());
                }
                let (key, _, bytes) = ICONS[i];
                let Some((w, h, px)) = decode_png_rgba(bytes) else {
                    warn_bad(&mut decode, key);
                    continue;
                };
                for (level, image) in icon_levels(w, h, px).into_iter().enumerate() {
                    let _ = images.insert(levels[level].id(), image);
                }
            }
        }
    }
}

fn warn_bad(decode: &mut UiDecode, what: &str) {
    if decode.warned.insert(what.to_string()) {
        warn!("ui kit: could not decode {what} (expected an 8-bit RGBA PNG)");
    }
}

/// sRGB byte → linear light.
fn lin_lut() -> &'static [f32; 256] {
    use std::sync::OnceLock;
    static LUT: OnceLock<[f32; 256]> = OnceLock::new();
    LUT.get_or_init(|| {
        let mut t = [0.0; 256];
        for (i, v) in t.iter_mut().enumerate() {
            let c = i as f32 / 255.0;
            *v = if c <= 0.04045 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) };
        }
        t
    })
}

fn to_srgb_byte(l: f32) -> u8 {
    let l = l.clamp(0.0, 1.0);
    let c = if l <= 0.003_130_8 { l * 12.92 } else { 1.055 * l.powf(1.0 / 2.4) - 0.055 };
    (c * 255.0 + 0.5) as u8
}

/// Halve an RGBA8 image with a premultiplied 2×2 box filter in linear light. Fully transparent
/// output keeps the ink colour the masters use under their alpha, so edges fringe to ink.
fn halve(w: u32, h: u32, src: &[u8]) -> (u32, u32, Vec<u8>) {
    let lut = lin_lut();
    let (ow, oh) = ((w / 2).max(1), (h / 2).max(1));
    let mut out = vec![0u8; (ow * oh * 4) as usize];
    for y in 0..oh {
        for x in 0..ow {
            let mut acc = [0.0f32; 4];
            for (dx, dy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
                let sx = (x * 2 + dx).min(w - 1);
                let sy = (y * 2 + dy).min(h - 1);
                let i = ((sy * w + sx) * 4) as usize;
                let a = src[i + 3] as f32 / 255.0;
                acc[0] += lut[src[i] as usize] * a;
                acc[1] += lut[src[i + 1] as usize] * a;
                acc[2] += lut[src[i + 2] as usize] * a;
                acc[3] += a;
            }
            let o = ((y * ow + x) * 4) as usize;
            if acc[3] > 1e-5 {
                out[o] = to_srgb_byte(acc[0] / acc[3]);
                out[o + 1] = to_srgb_byte(acc[1] / acc[3]);
                out[o + 2] = to_srgb_byte(acc[2] / acc[3]);
            } else {
                out[o..o + 3].copy_from_slice(&[10, 7, 6]);
            }
            out[o + 3] = (acc[3] / 4.0 * 255.0 + 0.5) as u8;
        }
    }
    (ow, oh, out)
}

/// Resample an RGBA8 image to (ow, oh) by exact area coverage, premultiplied, in linear light
/// (the inline sizes 16 / 20 / 24 are not powers of two).
fn resample(w: u32, h: u32, src: &[u8], ow: u32, oh: u32) -> Vec<u8> {
    let lut = lin_lut();
    let (sx, sy) = (w as f32 / ow as f32, h as f32 / oh as f32);
    let mut out = vec![0u8; (ow * oh * 4) as usize];
    for y in 0..oh {
        let (y0, y1) = (y as f32 * sy, (y + 1) as f32 * sy);
        for x in 0..ow {
            let (x0, x1) = (x as f32 * sx, (x + 1) as f32 * sx);
            let mut acc = [0.0f32; 4];
            let mut area = 0.0;
            for iy in y0.floor() as u32..(y1.ceil() as u32).min(h) {
                let wy = ((iy + 1) as f32).min(y1) - (iy as f32).max(y0);
                for ix in x0.floor() as u32..(x1.ceil() as u32).min(w) {
                    let wx = ((ix + 1) as f32).min(x1) - (ix as f32).max(x0);
                    let k = wx * wy;
                    let i = ((iy * w + ix) * 4) as usize;
                    let a = src[i + 3] as f32 / 255.0;
                    acc[0] += lut[src[i] as usize] * a * k;
                    acc[1] += lut[src[i + 1] as usize] * a * k;
                    acc[2] += lut[src[i + 2] as usize] * a * k;
                    acc[3] += a * k;
                    area += k;
                }
            }
            let o = ((y * ow + x) * 4) as usize;
            if acc[3] > 1e-5 {
                out[o] = to_srgb_byte(acc[0] / acc[3]);
                out[o + 1] = to_srgb_byte(acc[1] / acc[3]);
                out[o + 2] = to_srgb_byte(acc[2] / acc[3]);
            } else {
                out[o..o + 3].copy_from_slice(&[10, 7, 6]);
            }
            out[o + 3] = (acc[3] / area.max(1e-5) * 255.0 + 0.5) as u8;
        }
    }
    out
}

/// The 32 / 64 / 128 levels and the 16 / 20 / 24 inline sizes of an icon master.
fn icon_levels(w: u32, h: u32, px: Vec<u8>) -> [Image; 6] {
    let mut level = (w, h, px);
    while level.0 > ICON_LEVELS[2] {
        level = halve(level.0, level.1, &level.2);
    }
    let l128 = level.clone();
    let l64 = halve(l128.0, l128.1, &l128.2);
    let l32 = halve(l64.0, l64.1, &l64.2);
    let inline = ICON_INLINE.map(|s| resample(l64.0, l64.1, &l64.2, s, s));
    let [i16, i20, i24] = inline;
    [
        ui_image(l32.0, l32.1, l32.2),
        ui_image(l64.0, l64.1, l64.2),
        ui_image(l128.0, l128.1, l128.2),
        ui_image(16, 16, i16),
        ui_image(20, 20, i20),
        ui_image(24, 24, i24),
    ]
}
