// GODFORGE combat VFX: one shader for every VFX layer (docs/art/VFX_STYLE.md §21.5).
//
// The atlases are packed grey data, not colour: R = the shape as a signed distance field
// (0.5 = the edge), G = the value on the ramp, B = the erosion order. The ramp row turns the value
// into posterized ink / deep / body / light / hot bands with their HDR gain (in the ramp's alpha),
// so one painted flipbook serves every element. The erosion age dissolves the lowest-B texels
// first (tails before heads). Output is premultiplied: ink and body blend over, and the hot band
// fades to additive (alpha 0), so a whole effect is one draw with AlphaMode::Premultiplied.
//
// Reference: tools/vfx/vfxlib.py `shade()`, which painted every review sheet.

import bevy_pbr::render::mesh_functions::{get_world_from_local, mesh_position_local_to_clip};

struct FxParams {
    /// x = streak-noise strength (strips), y = ink band alpha, z = hot → additive start, w = end
    look: vec4<f32>,
    /// xyz = camera forward, w = the reveal radius around a hero (metres, screen plane)
    view: vec4<f32>,
    /// hero torso points (xyz), w = 1 when live
    heroes: array<vec4<f32>, 4>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(0) var<uniform> params: FxParams;
@group(constants::MATERIAL_BIND_GROUP) @binding(1) var atlas: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(2) var atlas_sampler: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(3) var ramp: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(4) var ramp_sampler: sampler;
@group(constants::MATERIAL_BIND_GROUP) @binding(5) var noise: texture_2d<f32>;
@group(constants::MATERIAL_BIND_GROUP) @binding(6) var noise_sampler: sampler;

struct Vertex {
    @builtin(instance_index) instance_index: u32,
    /// Quads and strips are expanded on the CPU in world space (their draw has an identity
    /// transform, the camera is a fixed orthographic view).
    @location(0) position: vec3<f32>,
    /// Atlas UV.
    @location(1) uv: vec2<f32>,
    /// x = alpha (fade, ally alpha, tier), y = gain multiplier, z = gain cap, w = ramp row v.
    @location(2) tint: vec4<f32>,
    /// x = erosion age t (0 = untouched), y = value override (< 0: use G), z = cooling progress,
    /// w = edge softness (1 = the painted edge; negative = fully additive).
    @location(3) fx: vec4<f32>,
    /// Streak-noise UV (strips: metres along, across).
    @location(4) uv_noise: vec2<f32>,
};

struct VertexOut {
    @builtin(position) clip: vec4<f32>,
    @location(0) uv: vec2<f32>,
    @location(1) tint: vec4<f32>,
    @location(2) fx: vec4<f32>,
    @location(3) uv_noise: vec2<f32>,
    @location(4) world: vec3<f32>,
};

/// 0..1: how much of an effect's occluding paint survives over the heroes (VFX_STYLE §20.3: a
/// character is never hidden). A fragment that passed the depth test over a hero is in front of
/// them; within the reveal radius (measured across the view) it thins to 30 %.
fn reveal(world: vec3<f32>) -> f32 {
    let fwd = params.view.xyz;
    let r = params.view.w;
    var keep = 1.0;
    for (var i = 0; i < 4; i++) {
        let h = params.heroes[i];
        if (h.w > 0.5) {
            let d = world - h.xyz;
            let across = length(d - fwd * dot(d, fwd));
            // Only paint between the hero and the camera hides them.
            if (dot(d, fwd) < 0.4) {
                keep = min(keep, mix(0.3, 1.0, smoothstep(r * 0.55, r, across)));
            }
        }
    }
    return keep;
}

@vertex
fn vertex(v: Vertex) -> VertexOut {
    var out: VertexOut;
    let world_from_local = get_world_from_local(v.instance_index);
    out.clip = mesh_position_local_to_clip(world_from_local, vec4(v.position, 1.0));
    out.world = (world_from_local * vec4(v.position, 1.0)).xyz;
    out.uv = v.uv;
    out.tint = v.tint;
    out.fx = v.fx;
    out.uv_noise = v.uv_noise;
    return out;
}

@fragment
fn fragment(i: VertexOut) -> @location(0) vec4<f32> {
    let tex = textureSample(atlas, atlas_sampler, i.uv);
    // The SDF edge, anti-aliased to about one screen pixel whatever the quad's size.
    let w = max(fwidth(tex.r) * 0.7 * abs(i.fx.w), 0.002);
    var coverage = smoothstep(0.5 - w, 0.5 + w, tex.r);
    // Erosion: low-B texels go first; strips break into brush streaks along their length.
    var threshold = tex.b;
    let streak = params.look.x;
    if (streak > 0.0) {
        let n = textureSample(noise, noise_sampler, i.uv_noise).r;
        threshold = threshold * mix(1.0, 0.35 + 1.1 * n, streak);
    }
    let t = i.fx.x;
    if (t > 0.0) {
        coverage = coverage * smoothstep(t - 0.05, t, threshold);
    }
    // Value: the painted G, or an override (the ink backing of a star is its own frame at ink).
    var v = tex.g;
    if (i.fx.y >= 0.0) {
        v = i.fx.y;
    }
    // Cooling: old, low-B texels drop a band as the effect ages (smoke rims cool, stars dim).
    if (i.fx.z > 0.0) {
        v = clamp(v - i.fx.z * (1.2 - tex.b), 0.0, 1.0);
    }
    let ramp_sample = textureSample(ramp, ramp_sampler, vec2((clamp(v, 0.0, 1.0) * 255.0 + 0.5) / 256.0, i.tint.w));
    let gain = min(ramp_sample.a * 4.0 * i.tint.y, i.tint.z);
    var alpha = coverage * i.tint.x;
    if (v < 0.18) {
        alpha = alpha * params.look.y;
    }
    if (v < params.look.z) {
        alpha = alpha * reveal(i.world);
    }
    // Hot values stop occluding and add light instead (or the whole shape, for pure glows).
    var additive = smoothstep(params.look.z, params.look.w, v);
    if (i.fx.w < 0.0) {
        additive = 1.0;
    }
    return vec4(ramp_sample.rgb * gain * alpha, alpha * (1.0 - additive));
}
