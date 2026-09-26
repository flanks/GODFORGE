//! Loads the VFX textures from `assets/vfx/` at startup (decoded in parallel, ~0.1 s) and builds
//! their mip chains, which the PNGs do not carry: small hit stars and thin strips would shimmer
//! without them.
//!
//! Packed sheets, strips and noise are **linear data** (`is_srgb = false`); only the ramp is sRGB
//! colour (its alpha stays linear: HDR gain / 4). A missing file logs a warning and loads as an
//! empty sheet, so the game still runs without the art.

use super::library::{SHEETS, Sheet};
use gf_engine::bevy::asset::RenderAssetUsages;
use gf_engine::bevy::image::{
    CompressedImageFormats, ImageAddressMode, ImageFilterMode, ImageSampler, ImageSamplerDescriptor, ImageType,
};
use gf_engine::bevy::render::render_resource::{Extent3d, TextureDimension, TextureFormat};
use gf_engine::prelude::*;
use std::path::{Path, PathBuf};

/// Every VFX texture handle.
#[derive(Resource, Clone)]
pub struct FxTextures {
    pub sheets: Vec<Handle<Image>>,
    /// `ramps/vfx_ramps.png`: 16 posterized rows (sRGB, alpha = HDR gain / 4).
    pub ramp: Handle<Image>,
    /// Anisotropic brush streaks: smears and ribbons multiply it into their erosion.
    pub streak: Handle<Image>,
    /// Tiling fractal value noise (a dissolve threshold).
    pub erode: Handle<Image>,
}

impl FxTextures {
    pub fn sheet(&self, s: Sheet) -> Handle<Image> {
        self.sheets[s as usize].clone()
    }
}

/// `assets/vfx`: beside the content directory (`GODFORGE_ASSETS` overrides the asset root).
pub fn vfx_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("GODFORGE_ASSETS") {
        return PathBuf::from(dir).join("vfx");
    }
    let content = gf_content::find_content_dir();
    content.parent().map_or_else(|| PathBuf::from("assets/vfx"), |p| p.join("vfx"))
}

#[derive(Clone, Copy)]
struct Spec {
    srgb: bool,
    repeat_u: bool,
    repeat_v: bool,
    /// Smallest cell edge in texels (the mip chain stops at 8 texels per cell).
    cell: u32,
    mips: bool,
}

pub(super) fn load(mut commands: Commands, mut images: ResMut<Assets<Image>>) {
    let dir = vfx_dir();
    let started = std::time::Instant::now();
    let mut jobs: Vec<(PathBuf, Spec)> = SHEETS
        .iter()
        .map(|s| {
            let cell = (s.size.0 / s.grid.0 as u32).min(s.size.1 / s.grid.1 as u32);
            let repeat = s.strip;
            (dir.join(s.file), Spec { srgb: false, repeat_u: repeat, repeat_v: false, cell, mips: true })
        })
        .collect();
    jobs.push((
        dir.join("ramps/vfx_ramps.png"),
        Spec { srgb: true, repeat_u: false, repeat_v: false, cell: 1, mips: false },
    ));
    let noise = Spec { srgb: false, repeat_u: true, repeat_v: true, cell: 256, mips: true };
    jobs.push((dir.join("noise/noise_streak_256.png"), noise));
    jobs.push((dir.join("noise/noise_erode_256.png"), noise));

    let decoded: Vec<Image> = std::thread::scope(|scope| {
        let handles: Vec<_> = jobs.iter().map(|(path, spec)| scope.spawn(move || decode(path, *spec))).collect();
        handles.into_iter().map(|h| h.join().unwrap_or_else(|_| empty())).collect()
    });
    let mut handles: Vec<Handle<Image>> = decoded.into_iter().map(|img| images.add(img)).collect();
    let erode = handles.pop().unwrap_or_default();
    let streak = handles.pop().unwrap_or_default();
    let ramp = handles.pop().unwrap_or_default();
    info!("vfx: {} textures from {} in {:.0} ms", jobs.len(), dir.display(), started.elapsed().as_secs_f32() * 1000.0);
    commands.insert_resource(FxTextures { sheets: handles, ramp, streak, erode });
}

fn decode(path: &Path, spec: Spec) -> Image {
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(e) => {
            warn!("vfx: {} missing ({e}); its effects draw nothing", path.display());
            return empty();
        }
    };
    let sampler = ImageSampler::Descriptor(ImageSamplerDescriptor {
        address_mode_u: if spec.repeat_u { ImageAddressMode::Repeat } else { ImageAddressMode::ClampToEdge },
        address_mode_v: if spec.repeat_v { ImageAddressMode::Repeat } else { ImageAddressMode::ClampToEdge },
        mag_filter: ImageFilterMode::Linear,
        min_filter: ImageFilterMode::Linear,
        mipmap_filter: ImageFilterMode::Linear,
        ..default()
    });
    let mut image = match Image::from_buffer(
        &bytes,
        ImageType::Extension("png"),
        CompressedImageFormats::NONE,
        spec.srgb,
        sampler,
        RenderAssetUsages::RENDER_WORLD,
    ) {
        Ok(i) => i,
        Err(e) => {
            warn!("vfx: {} failed to decode ({e})", path.display());
            return empty();
        }
    };
    if spec.mips {
        build_mips(&mut image, spec.cell);
    }
    image
}

/// Box-filtered mip chain down to 8 texels per cell (packed data is linear, so a plain average is
/// right; the SDF edge stays at 0.5).
fn build_mips(image: &mut Image, cell: u32) {
    let bpp = match image.texture_descriptor.format {
        TextureFormat::Rgba8Unorm | TextureFormat::Rgba8UnormSrgb => 4,
        TextureFormat::R8Unorm => 1,
        _ => return,
    };
    let Some(base) = image.data.take() else { return };
    let (mut w, mut h) = (image.width() as usize, image.height() as usize);
    let levels = (cell.max(1).ilog2().saturating_sub(3) + 1).min(7);
    let mut prev = base.clone();
    let mut data = base;
    let mut made = 1;
    for _ in 1..levels {
        if w < 2 || h < 2 {
            break;
        }
        let (nw, nh) = (w / 2, h / 2);
        let mut next = Vec::with_capacity(nw * nh * bpp);
        for y in 0..nh {
            let (r0, r1) = (2 * y * w, (2 * y + 1) * w);
            for x in 0..nw {
                for c in 0..bpp {
                    let at = |i: usize| prev[i * bpp + c] as u32;
                    let s = at(r0 + 2 * x) + at(r0 + 2 * x + 1) + at(r1 + 2 * x) + at(r1 + 2 * x + 1);
                    next.push(((s + 2) / 4) as u8);
                }
            }
        }
        data.extend_from_slice(&next);
        prev = next;
        w = nw;
        h = nh;
        made += 1;
    }
    image.data = Some(data);
    image.texture_descriptor.mip_level_count = made;
}

/// A 1×1 transparent stand-in for a missing texture.
fn empty() -> Image {
    Image::new(
        Extent3d { width: 1, height: 1, depth_or_array_layers: 1 },
        TextureDimension::D2,
        vec![0, 0, 0, 0],
        TextureFormat::Rgba8Unorm,
        RenderAssetUsages::RENDER_WORLD,
    )
}
