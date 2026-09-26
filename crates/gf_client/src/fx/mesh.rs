//! The batched layer meshes: one dynamic mesh (and one [`FxMaterial`]) per (sheet, layer) that has
//! something to draw, rebuilt every frame from the particle store, the ribbons and the arcs.
//!
//! Draw order between layers comes from the material's `depth_bias`, not from where the effects
//! are: every layer mesh carries two unreferenced anchor vertices around the camera's focus, so
//! Bevy's sort point (the mesh AABB centre) is the same for every layer, every frame.

use super::Layer;
use super::library::{Sheet, Strip};
use super::material::{ATTRIBUTE_FX, FxMaterial};
use super::textures::FxTextures;
use gf_engine::bevy::asset::RenderAssetUsages;
use gf_engine::bevy::camera::visibility::NoFrustumCulling;
use gf_engine::bevy::mesh::{Indices, PrimitiveTopology, VertexAttributeValues};
use gf_engine::client::{NotShadowCaster, NotShadowReceiver};
use gf_engine::prelude::*;

/// The fixed orthographic camera's basis this frame.
#[derive(Clone, Copy, Debug)]
pub struct CamBasis {
    pub right: Vec3,
    pub up: Vec3,
    /// Toward the scene.
    pub fwd: Vec3,
    /// Toward the camera.
    pub back: Vec3,
    /// The ground point at the centre of the view.
    pub focus: Vec3,
}

impl Default for CamBasis {
    fn default() -> Self {
        let pitch = 55f32.to_radians();
        let fwd = Vec3::new(0.0, -pitch.sin(), -pitch.cos());
        let right = Vec3::X;
        CamBasis { right, up: right.cross(fwd).normalize(), fwd, back: -fwd, focus: Vec3::ZERO }
    }
}

impl CamBasis {
    pub fn from_transform(tf: &Transform) -> CamBasis {
        let fwd = tf.forward().as_vec3();
        let right = tf.right().as_vec3();
        let up = tf.up().as_vec3();
        // The ground point under the view centre.
        let t = if fwd.y.abs() > 1e-3 { -tf.translation.y / fwd.y } else { 60.0 };
        CamBasis { right, up, fwd, back: -fwd, focus: tf.translation + fwd * t }
    }

    /// Distance along the view direction (larger = farther).
    #[inline]
    pub fn depth(&self, p: Vec3) -> f32 {
        p.dot(self.fwd)
    }
}

/// CPU vertex staging for one layer mesh.
#[derive(Default)]
pub struct LayerBuf {
    pub pos: Vec<[f32; 3]>,
    pub uv: Vec<[f32; 2]>,
    pub tint: Vec<[f32; 4]>,
    pub fx: Vec<[f32; 4]>,
    pub uvn: Vec<[f32; 2]>,
    pub idx: Vec<u32>,
}

impl LayerBuf {
    pub fn clear(&mut self) {
        self.pos.clear();
        self.uv.clear();
        self.tint.clear();
        self.fx.clear();
        self.uvn.clear();
        self.idx.clear();
    }

    pub fn is_empty(&self) -> bool {
        self.idx.is_empty()
    }

    /// Corners clockwise from the top-left: (u0, v0), (u1, v0), (u1, v1), (u0, v1).
    pub fn quad(&mut self, p: [Vec3; 4], uv: [[f32; 2]; 4], tint: [f32; 4], fx: [f32; 4]) {
        let base = self.pos.len() as u32;
        for i in 0..4 {
            self.pos.push(p[i].to_array());
            self.uv.push(uv[i]);
            self.tint.push(tint);
            self.fx.push(fx);
            self.uvn.push(uv[i]);
        }
        self.idx.extend_from_slice(&[base, base + 1, base + 2, base, base + 2, base + 3]);
    }

    /// One cross-section of a strip: the `v = 0` and `v = 1` edge points at `u`. Call
    /// [`LayerBuf::end_strip`] with the index [`LayerBuf::begin_strip`] returned.
    #[allow(clippy::too_many_arguments)]
    pub fn strip_pair(
        &mut self,
        strip: &Strip,
        a: Vec3,
        b: Vec3,
        u: f32,
        tint: [f32; 4],
        fx: [f32; 4],
        noise: [f32; 2],
    ) {
        let (v0, v1) = strip.v_range();
        self.pos.push(a.to_array());
        self.pos.push(b.to_array());
        self.uv.push([u, v0]);
        self.uv.push([u, v1]);
        self.tint.push(tint);
        self.tint.push(tint);
        self.fx.push(fx);
        self.fx.push(fx);
        self.uvn.push(noise);
        self.uvn.push([noise[0], noise[1] + 0.5]);
    }

    pub fn begin_strip(&self) -> u32 {
        self.pos.len() as u32
    }

    /// Triangles between consecutive pairs pushed since `base`.
    pub fn end_strip(&mut self, base: u32) {
        let pairs = (self.pos.len() as u32 - base) / 2;
        for i in 0..pairs.saturating_sub(1) {
            let a = base + 2 * i;
            self.idx.extend_from_slice(&[a, a + 1, a + 3, a, a + 3, a + 2]);
        }
    }

    pub fn vertex_count(&self) -> usize {
        self.pos.len()
    }
}

/// Marks a layer draw entity.
#[derive(Component)]
pub struct FxLayerDraw;

/// The layer draws' visibility (disjoint from the light pool's).
pub type LayerVisibility<'w, 's> =
    Query<'w, 's, &'static mut Visibility, (With<FxLayerDraw>, Without<super::light::PooledLight>)>;

/// One (sheet, layer) draw.
pub struct Slot {
    pub buf: LayerBuf,
    entity: Option<Entity>,
    mesh: Handle<Mesh>,
    visible: bool,
}

/// Every layer draw, indexed by `sheet × Layer::COUNT + layer`.
#[derive(Resource)]
pub struct Layers {
    pub slots: Vec<Slot>,
}

impl Default for Layers {
    fn default() -> Self {
        Layers {
            slots: (0..Sheet::COUNT * Layer::COUNT)
                .map(|_| Slot { buf: LayerBuf::default(), entity: None, mesh: Handle::default(), visible: false })
                .collect(),
        }
    }
}

impl Layers {
    #[inline]
    pub fn index(sheet: Sheet, layer: Layer) -> usize {
        sheet as usize * Layer::COUNT + layer as usize
    }

    pub fn buf(&mut self, sheet: Sheet, layer: Layer) -> &mut LayerBuf {
        &mut self.slots[Self::index(sheet, layer)].buf
    }

    pub fn clear(&mut self) {
        for s in &mut self.slots {
            s.buf.clear();
        }
    }
}

/// Streak-noise strength of a sheet: strips break into brush streaks along their length.
fn streak_of(sheet: Sheet) -> f32 {
    match sheet {
        Sheet::Smears => 0.8,
        Sheet::Trails => 0.3,
        Sheet::Bands => 0.5,
        _ => 0.0,
    }
}

/// Upload every layer's staging buffer (creating the draw on first use) and hide empty ones.
pub(super) fn upload(
    commands: &mut Commands,
    layers: &mut Layers,
    textures: &FxTextures,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<FxMaterial>,
    visibility: &mut LayerVisibility,
    cam: &CamBasis,
) -> (u32, u32) {
    let (mut draws, mut verts) = (0, 0);
    for (i, slot) in layers.slots.iter_mut().enumerate() {
        let has = !slot.buf.is_empty();
        if has && slot.entity.is_none() {
            let sheet = Sheet::ALL[i / Layer::COUNT];
            let layer = Layer::ALL[i % Layer::COUNT];
            let material = materials.add(FxMaterial::new(
                textures.sheet(sheet),
                textures.ramp.clone(),
                textures.streak.clone(),
                streak_of(sheet),
                layer.bias() + sheet as usize as f32 * 0.5,
            ));
            slot.mesh = meshes.add(empty_mesh());
            slot.entity = Some(
                commands
                    .spawn((
                        Name::new(format!("fx {sheet:?} {layer:?}")),
                        FxLayerDraw,
                        Mesh3d(slot.mesh.clone()),
                        MeshMaterial3d(material),
                        Transform::IDENTITY,
                        Visibility::Hidden,
                        NoFrustumCulling,
                        NotShadowCaster,
                        NotShadowReceiver,
                    ))
                    .id(),
            );
        }
        let Some(entity) = slot.entity else { continue };
        if has {
            draws += 1;
            verts += slot.buf.vertex_count() as u32;
            if let Some(mut mesh) = meshes.get_mut(&slot.mesh) {
                write_mesh(&mut mesh, &slot.buf, cam.focus);
            }
        }
        if has != slot.visible {
            // A just-spawned entity is not queryable until the commands apply: retry next frame.
            if let Ok(mut vis) = visibility.get_mut(entity) {
                *vis = if has { Visibility::Inherited } else { Visibility::Hidden };
                slot.visible = has;
            }
        }
    }
    (draws, verts)
}

fn empty_mesh() -> Mesh {
    let mut buf = LayerBuf::default();
    buf.quad([Vec3::ZERO; 4], [[0.0; 2]; 4], [0.0; 4], [0.0; 4]);
    let mut mesh =
        Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::MAIN_WORLD | RenderAssetUsages::RENDER_WORLD)
            .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, Vec::<[f32; 3]>::new())
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, Vec::<[f32; 2]>::new())
            .with_inserted_attribute(Mesh::ATTRIBUTE_COLOR, Vec::<[f32; 4]>::new())
            .with_inserted_attribute(ATTRIBUTE_FX, Vec::<[f32; 4]>::new())
            .with_inserted_attribute(Mesh::ATTRIBUTE_UV_1, Vec::<[f32; 2]>::new())
            .with_inserted_indices(Indices::U32(Vec::new()));
    write_mesh(&mut mesh, &buf, Vec3::ZERO);
    mesh
}

/// Copy a staging buffer into the mesh, reusing the mesh's allocations. Two unreferenced vertices
/// pin the AABB centre on `anchor` (see the module docs).
fn write_mesh(mesh: &mut Mesh, buf: &LayerBuf, anchor: Vec3) {
    const FAR: f32 = 4096.0;
    if let Some(VertexAttributeValues::Float32x3(v)) = mesh.attribute_mut(Mesh::ATTRIBUTE_POSITION) {
        v.clear();
        v.extend_from_slice(&buf.pos);
        v.push((anchor - Vec3::splat(FAR)).to_array());
        v.push((anchor + Vec3::splat(FAR)).to_array());
    }
    let extra2 = |v: &mut Vec<[f32; 2]>, src: &[[f32; 2]]| {
        v.clear();
        v.extend_from_slice(src);
        v.extend_from_slice(&[[0.0; 2]; 2]);
    };
    let extra4 = |v: &mut Vec<[f32; 4]>, src: &[[f32; 4]]| {
        v.clear();
        v.extend_from_slice(src);
        v.extend_from_slice(&[[0.0; 4]; 2]);
    };
    if let Some(VertexAttributeValues::Float32x2(v)) = mesh.attribute_mut(Mesh::ATTRIBUTE_UV_0) {
        extra2(v, &buf.uv);
    }
    if let Some(VertexAttributeValues::Float32x4(v)) = mesh.attribute_mut(Mesh::ATTRIBUTE_COLOR) {
        extra4(v, &buf.tint);
    }
    if let Some(VertexAttributeValues::Float32x4(v)) = mesh.attribute_mut(ATTRIBUTE_FX) {
        extra4(v, &buf.fx);
    }
    if let Some(VertexAttributeValues::Float32x2(v)) = mesh.attribute_mut(Mesh::ATTRIBUTE_UV_1) {
        extra2(v, &buf.uvn);
    }
    if let Some(Indices::U32(i)) = mesh.indices_mut() {
        i.clear();
        i.extend_from_slice(&buf.idx);
    }
}
