// GODFORGE mesh projectile bodies (docs/art/VFX_STYLE.md §6): packed vertex colours through the
// element ramp. G = the painted value band, B = the erosion order. The key light only moves the
// value by up to one band (painted planes, not shading); ink stays ink and hot stays hot.

import bevy_pbr::render::mesh_functions::{get_world_from_local, mesh_position_local_to_clip, mesh_normal_local_to_world};

struct BodyTint {
    /// x = alpha, y = gain multiplier, z = gain cap, w = ramp row v
    tint: vec4<f32>,
}

struct BodyLight {
    /// xyz = toward the key light (world), w = band shift strength
    light: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(0) var<uniform> tint: BodyTint;
@group(constants::MATERIAL_BIND_GROUP) @binding(1) var<uniform> light: BodyLight;
@group(constants::MATERIAL_BIND_GROUP) @binding(2) var ramp: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(3) var ramp_sampler: sampler;

struct Vertex {
    @builtin(instance_index) instance_index: u32,
    @location(0) position: vec3<f32>,
    @location(1) normal: vec3<f32>,
    @location(2) color: vec4<f32>,
};

struct VertexOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) normal: vec3<f32>,
    @location(1) color: vec4<f32>,
};

@vertex
fn vertex(v: Vertex) -> VertexOut {
    var out: VertexOut;
    out.clip = mesh_position_local_to_clip(get_world_from_local(v.instance_index), vec4(v.position, 1.0));
    out.normal = mesh_normal_local_to_world(v.normal, v.instance_index);
    out.color = v.color;
    return out;
}

@fragment
fn fragment(i: VertexOut) -> @location(0) vec4<f32> {
    let n = normalize(i.normal);
    let lit = dot(n, normalize(light.light.xyz)) * 0.5 + 0.5;
    var v = i.color.g;
    // Body bands take the light (± one band); ink and hot are fixed.
    if (v > 0.18 && v < 0.8) {
        v = clamp(v + (lit - 0.55) * 0.42 * light.light.w, 0.19, 0.79);
    }
    let r = textureSample(ramp, ramp_sampler, vec2((v * 255.0 + 0.5) / 256.0, tint.tint.w));
    let gain = min(r.a * 4.0 * tint.tint.y, tint.tint.z);
    let a = tint.tint.x;
    let additive = smoothstep(0.80, 0.90, v);
    return vec4(r.rgb * gain * a, a * (1.0 - additive * (1.0 - a)));
}
