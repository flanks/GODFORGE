//! [`FxMaterial`]: the unlit VFX material (`fx.wesl`). One material per (sheet, layer), so every
//! live particle, strip or ring of one sheet in one layer is a single draw.
//!
//! Vertices carry everything per effect (world position, atlas UV, alpha, gain, ramp row, erosion,
//! value override), which is what lets one material and one mesh serve every element and owner.

use gf_engine::bevy::mesh::{MeshVertexAttribute, MeshVertexBufferLayoutRef, VertexFormat};
use gf_engine::bevy::pbr::{MaterialPipeline, MaterialPipelineKey};
use gf_engine::bevy::render::render_resource::{AsBindGroup, RenderPipelineDescriptor, SpecializedMeshPipelineError};
use gf_engine::bevy::shader::ShaderRef;
use gf_engine::prelude::*;

/// Per-vertex `[erosion t, value override (< 0 = none), cooling, edge softness]`.
pub const ATTRIBUTE_FX: MeshVertexAttribute =
    MeshVertexAttribute::new("Fx_Params", 0x6f78_2d66_7801, VertexFormat::Float32x4);

pub const SHADER: &str = "embedded://gf_client/fx/fx.wesl";

/// The ink band's opacity (VFX_STYLE §3.1: ink at 80-95 %).
pub const INK_ALPHA: f32 = 0.9;
/// Values from `HOT_FROM` to `HOT_TO` fade from alpha-over to additive.
pub const HOT_FROM: f32 = 0.80;
pub const HOT_TO: f32 = 0.90;

#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct FxMaterial {
    /// x = streak-noise strength, y = ink alpha, z / w = hot → additive band.
    #[uniform(0)]
    pub look: Vec4,
    #[texture(1)]
    #[sampler(2)]
    pub atlas: Handle<Image>,
    #[texture(3)]
    #[sampler(4)]
    pub ramp: Handle<Image>,
    #[texture(5)]
    #[sampler(6)]
    pub noise: Handle<Image>,
    /// Draw order against other transparent items (larger draws later, i.e. on top).
    #[reflect(ignore)]
    pub bias: f32,
}

impl FxMaterial {
    pub fn new(atlas: Handle<Image>, ramp: Handle<Image>, noise: Handle<Image>, streak: f32, bias: f32) -> Self {
        FxMaterial { look: Vec4::new(streak, INK_ALPHA, HOT_FROM, HOT_TO), atlas, ramp, noise, bias }
    }
}

impl Material for FxMaterial {
    fn vertex_shader() -> ShaderRef {
        SHADER.into()
    }

    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }

    fn alpha_mode(&self) -> AlphaMode {
        AlphaMode::Premultiplied
    }

    fn depth_bias(&self) -> f32 {
        self.bias
    }

    fn enable_prepass() -> bool {
        false
    }

    fn enable_shadows() -> bool {
        false
    }

    fn enable_oit() -> bool {
        false
    }

    fn specialize(
        _pipeline: &MaterialPipeline,
        descriptor: &mut RenderPipelineDescriptor,
        layout: &MeshVertexBufferLayoutRef,
        _key: MaterialPipelineKey<Self>,
    ) -> Result<(), SpecializedMeshPipelineError> {
        let vertex_layout = layout.0.get_layout(&[
            Mesh::ATTRIBUTE_POSITION.at_shader_location(0),
            Mesh::ATTRIBUTE_UV_0.at_shader_location(1),
            Mesh::ATTRIBUTE_COLOR.at_shader_location(2),
            ATTRIBUTE_FX.at_shader_location(3),
            Mesh::ATTRIBUTE_UV_1.at_shader_location(4),
        ])?;
        descriptor.vertex.buffers = vec![vertex_layout];
        descriptor.primitive.cull_mode = None;
        Ok(())
    }
}
