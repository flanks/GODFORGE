//! Mesh projectile bodies (VFX_STYLE §6: Shell, Arrow, Boulder, Coin, Blade, Javelin, Harpoon, …):
//! the Blender-built meshes in `assets/vfx/meshes/`, drawn with [`FxBodyMaterial`] (`body.wesl`).
//!
//! The meshes carry the same packing as the atlases in their vertex colours (G = the value band,
//! B = the erosion order), so the element ramp colours them and one mesh serves every element.
//! Light only nudges the value by a band (painted planes, not shading), the ink stays ink and the
//! hot parts stay hot.
//!
//! Put an [`FxBody`] on an entity (a projectile's visual): the body spawns as its child once the
//! mesh has loaded, points along the entity's flight and tumbles if asked.

use super::library::Ramp;
use super::textures::FxTextures;
use super::{FxStore, Owner};
use crate::camera::KEY_LIGHT_FROM;
use gf_engine::bevy::asset::io::embedded::EmbeddedAssetRegistry;
use gf_engine::bevy::gltf::GltfAssetLabel;
use gf_engine::bevy::mesh::MeshVertexBufferLayoutRef;
use gf_engine::bevy::pbr::{MaterialPipeline, MaterialPipelineKey};
use gf_engine::bevy::render::render_resource::{AsBindGroup, RenderPipelineDescriptor, SpecializedMeshPipelineError};
use gf_engine::bevy::shader::ShaderRef;
use gf_engine::client::{NotShadowCaster, NotShadowReceiver};
use gf_engine::prelude::*;
use std::collections::HashMap;

pub const SHADER: &str = "embedded://gf_client/fx/body.wesl";

/// The body meshes of the library.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum BodyMesh {
    Shell,
    Arrow,
    Bolt,
    Needle,
    Pellet,
    Shard,
    Coin,
    DiscBlade,
    Javelin,
    Harpoon,
    BoulderA,
    BoulderB,
    BoulderC,
}

impl BodyMesh {
    pub const ALL: [BodyMesh; 13] = [
        BodyMesh::Shell,
        BodyMesh::Arrow,
        BodyMesh::Bolt,
        BodyMesh::Needle,
        BodyMesh::Pellet,
        BodyMesh::Shard,
        BodyMesh::Coin,
        BodyMesh::DiscBlade,
        BodyMesh::Javelin,
        BodyMesh::Harpoon,
        BodyMesh::BoulderA,
        BodyMesh::BoulderB,
        BodyMesh::BoulderC,
    ];

    pub fn file(self) -> &'static str {
        match self {
            BodyMesh::Shell => "vfx_shell.glb",
            BodyMesh::Arrow => "vfx_arrow.glb",
            BodyMesh::Bolt => "vfx_bolt.glb",
            BodyMesh::Needle => "vfx_needle.glb",
            BodyMesh::Pellet => "vfx_pellet.glb",
            BodyMesh::Shard => "vfx_shard.glb",
            BodyMesh::Coin => "vfx_coin.glb",
            BodyMesh::DiscBlade => "vfx_disc_blade.glb",
            BodyMesh::Javelin => "vfx_javelin.glb",
            BodyMesh::Harpoon => "vfx_harpoon.glb",
            BodyMesh::BoulderA => "vfx_boulder_a.glb",
            BodyMesh::BoulderB => "vfx_boulder_b.glb",
            BodyMesh::BoulderC => "vfx_boulder_c.glb",
        }
    }
}

/// A mesh body carried by this entity.
#[derive(Component, Clone, Debug)]
pub struct FxBody {
    pub mesh: BodyMesh,
    pub ramp: Ramp,
    pub owner: Owner,
    /// Uniform scale of the authored mesh (metres as modelled).
    pub scale: f32,
    /// Point the mesh's nose (−Z) along the entity's motion.
    pub align: bool,
    /// Tumble: angular velocity about the body's own axes (radians per second).
    pub spin: Vec3,
    /// Offset from the entity (world axes).
    pub offset: Vec3,
    pub(crate) child: Option<Entity>,
    pub(crate) last: Option<Vec3>,
    pub(crate) heading: Vec3,
    pub(crate) turn: Quat,
}

impl FxBody {
    pub fn new(mesh: BodyMesh, ramp: Ramp, owner: Owner, scale: f32) -> FxBody {
        FxBody {
            mesh,
            ramp,
            owner,
            scale,
            align: true,
            spin: Vec3::ZERO,
            offset: Vec3::ZERO,
            child: None,
            last: None,
            heading: Vec3::NEG_Z,
            turn: Quat::IDENTITY,
        }
    }

    pub fn spin(mut self, s: Vec3) -> Self {
        self.spin = s;
        self
    }
}

/// Marks the spawned mesh child of an [`FxBody`].
#[derive(Component)]
pub struct FxBodyMesh;

/// Unlit packed-mesh material (`body.wesl`).
#[derive(Asset, AsBindGroup, Reflect, Clone, Debug)]
pub struct FxBodyMaterial {
    /// x = alpha, y = gain multiplier, z = gain cap, w = ramp row v.
    #[uniform(0)]
    pub tint: Vec4,
    /// xyz = toward the key light (world), w = how many bands the light moves the value.
    #[uniform(1)]
    pub light: Vec4,
    #[texture(2)]
    #[sampler(3)]
    pub ramp: Handle<Image>,
    #[reflect(ignore)]
    pub blend: bool,
}

impl Material for FxBodyMaterial {
    fn vertex_shader() -> ShaderRef {
        SHADER.into()
    }

    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }

    fn alpha_mode(&self) -> AlphaMode {
        if self.blend { AlphaMode::Premultiplied } else { AlphaMode::Opaque }
    }

    fn enable_prepass() -> bool {
        false
    }

    fn enable_shadows() -> bool {
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
            Mesh::ATTRIBUTE_NORMAL.at_shader_location(1),
            Mesh::ATTRIBUTE_COLOR.at_shader_location(2),
        ])?;
        descriptor.vertex.buffers = vec![vertex_layout];
        descriptor.primitive.cull_mode = None;
        Ok(())
    }
}

/// Mesh handles and cached materials.
#[derive(Resource, Default)]
pub struct FxBodies {
    meshes: HashMap<BodyMesh, Handle<Mesh>>,
    materials: HashMap<(Ramp, u8), Handle<FxBodyMaterial>>,
}

/// Register the meshes' bytes with the embedded asset source (read from `assets/vfx/meshes/` at
/// startup, like the textures), so they load through Bevy's glTF loader from any working
/// directory.
pub(super) fn register(app: &mut App) {
    let dir = super::textures::vfx_dir().join("meshes");
    let registry = app.world_mut().resource_mut::<EmbeddedAssetRegistry>();
    for m in BodyMesh::ALL {
        let path = dir.join(m.file());
        match std::fs::read(&path) {
            Ok(bytes) if bytes.len() > 200 => {
                registry.insert_asset(path.clone(), &std::path::Path::new("gf_client/vfx").join(m.file()), bytes);
            }
            Ok(_) => warn!("vfx: {} is a Git LFS pointer (run git lfs pull); that body draws nothing", path.display()),
            Err(e) => warn!("vfx: {} missing ({e}); that body draws nothing", path.display()),
        }
    }
}

pub(super) fn load(server: Res<AssetServer>, mut bodies: ResMut<FxBodies>) {
    for m in BodyMesh::ALL {
        let path = format!("embedded://gf_client/vfx/{}", m.file());
        let handle = server.load(GltfAssetLabel::Primitive { mesh: 0, primitive: 0 }.from_asset(path));
        bodies.meshes.insert(m, handle);
    }
}

/// Spawn the mesh child of new bodies; aim and tumble every body.
#[allow(clippy::too_many_arguments)]
pub(super) fn update(
    mut commands: Commands,
    time: Res<Time>,
    store: Res<FxStore>,
    textures: Option<Res<FxTextures>>,
    mut bodies: ResMut<FxBodies>,
    mut materials: ResMut<Assets<FxBodyMaterial>>,
    mut carriers: Query<(Entity, &GlobalTransform, &mut FxBody)>,
    mut meshes: Query<&mut Transform, With<FxBodyMesh>>,
) {
    let Some(textures) = textures else { return };
    let dt = time.delta_secs() * store.time_scale;
    for (e, g, mut body) in &mut carriers {
        let pos = g.translation();
        if let Some(last) = body.last {
            let d = pos - last;
            if d.length_squared() > 1e-6 {
                body.heading = d.normalize();
            }
        }
        body.last = Some(pos);
        let spin = body.spin * dt;
        body.turn = (body.turn * Quat::from_euler(EulerRot::XYZ, spin.x, spin.y, spin.z)).normalize();
        // The mesh child inherits the carrier's transform: undo its rotation and scale, aim in
        // world space.
        let (carrier_scale, carrier_rot, _) = g.to_scale_rotation_translation();
        let aim =
            if body.align { Transform::default().looking_to(body.heading, Vec3::Y).rotation } else { Quat::IDENTITY };
        let local = Transform {
            translation: carrier_rot.inverse() * body.offset / carrier_scale.max(Vec3::splat(1e-4)),
            rotation: carrier_rot.inverse() * aim * body.turn,
            scale: Vec3::splat(body.scale) / carrier_scale.max(Vec3::splat(1e-4)),
        };
        match body.child {
            Some(child) => {
                if let Ok(mut tf) = meshes.get_mut(child) {
                    *tf = local;
                }
            }
            None => {
                let Some(grant) = store.grant(body.owner, super::Class::Core) else { continue };
                let Some(mesh) = bodies.meshes.get(&body.mesh).cloned() else { continue };
                let alpha_q = (grant.alpha * 20.0).round() as u8;
                let ramp = body.ramp;
                let material = bodies
                    .materials
                    .entry((ramp, alpha_q))
                    .or_insert_with(|| {
                        let light = KEY_LIGHT_FROM.normalize();
                        materials.add(FxBodyMaterial {
                            tint: Vec4::new(alpha_q as f32 / 20.0, 1.0, grant.cap, ramp.v()),
                            light: light.extend(1.0),
                            ramp: textures.ramp.clone(),
                            blend: alpha_q < 20,
                        })
                    })
                    .clone();
                let child = commands
                    .spawn((
                        FxBodyMesh,
                        Mesh3d(mesh),
                        MeshMaterial3d(material),
                        local,
                        NotShadowCaster,
                        NotShadowReceiver,
                        ChildOf(e),
                    ))
                    .id();
                body.child = Some(child);
            }
        }
    }
}
