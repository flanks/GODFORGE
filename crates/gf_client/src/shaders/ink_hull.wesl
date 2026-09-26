// GODFORGE ink hull: the painted contour of a skinned (or rigid) glTF hero.
//
// The greybox closes a silhouette with an inverted hull (the same primitive grown, front faces
// culled). A skinned mesh cannot be grown by its transform, so this vertex shader grows it after
// skinning: every vertex moves out along its skinned normal by a width in metres (the camera is
// orthographic, so metres are pixels). Back faces only (the pipeline culls front faces): what shows
// is a band just outside the body's outline, plus the inner contours where a limb crosses the torso.
// A halo hull (wider, pushed back along the view so the ink stays on top) rings the ink in the
// player's colour.

import bevy_pbr::render::{
    mesh_functions,
    skinning,
    mesh_view_bindings::view,
    forward_io::{Vertex, VertexOutput, decompress_vertex},
    view_transformations::position_world_to_clip,
};

struct InkHullParams {
    /// rgb colour (linear, HDR allowed), a = unused (opaque)
    color: vec4<f32>,
    /// x = width (m) along the normal, y = push away from the camera (m), zw = unused
    shape: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(0) var<uniform> hull: InkHullParams;

@vertex
fn vertex(vertex_in: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let vertex = decompress_vertex(vertex_in, vertex_in.instance_index);
@if(SKINNED)
    let world_from_local = skinning::skin_model(vertex.joint_indices, vertex.joint_weights, vertex_in.instance_index);
@else
    let world_from_local = mesh_functions::get_world_from_local(vertex_in.instance_index);
@if(SKINNED)
    let normal = skinning::skin_normals(world_from_local, vertex.normal);
@else
    let normal = mesh_functions::mesh_normal_local_to_world(vertex.normal, vertex_in.instance_index);
    let world = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(vertex.position, 1.0));
    // Toward the camera (the view's +Z in world space).
    let back = normalize(view.world_from_view[2].xyz);
    let n = normal / max(length(normal), 1.0e-5);
    let grown = world.xyz + n * hull.shape.x - back * hull.shape.y;
    out.world_position = vec4<f32>(grown, 1.0);
    out.world_normal = n;
    out.position = position_world_to_clip(grown);
    return out;
}

@fragment
fn fragment(in: VertexOutput) -> @location(0) vec4<f32> {
    return vec4<f32>(hull.color.rgb, 1.0);
}
