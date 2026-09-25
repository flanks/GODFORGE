// GODFORGE painterly NPR (§12, §14: "stylized NPR shading (toon-ramp + rim light), not realistic PBR").
//
// Lighting is Bevy's own (directional + point lights, shadows, ambient), then posterized in log2
// space so the bands don't depend on exposure: surfaces read as flat painted planes of light and
// shadow with a soft terminator. Light hue is kept (warm key, cool fill). A coloured rim picks out
// silhouettes, and low-frequency value noise stands in for brush texture.

import bevy_pbr::render::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{alpha_discard, apply_pbr_lighting, main_pass_post_lighting_processing},
    forward_io::{VertexOutput, FragmentOutput},
};

struct ToonParams {
    /// rgb rim colour (linear, HDR allowed), a = rim strength
    rim: vec4<f32>,
    /// rgb colour dark bands lean toward, a = amount
    shade: vec4<f32>,
    /// x = toon amount (0 PBR … 1 full ramp), y = rim width, z = paint strength, w = paint space (0 normal, 1 world)
    settings: vec4<f32>,
    /// x = band size in stops, y = terminator softness, z = saturation boost in shadow, w = unused
    ramp: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> toon: ToonParams;

fn hash31(p: vec3<f32>) -> f32 {
    var q = fract(p * 0.1031);
    q += dot(q, q.zyx + 31.32);
    return fract((q.x + q.y) * q.z);
}

fn value_noise(p: vec3<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let u = f * f * (3.0 - 2.0 * f);
    let a = mix(hash31(i + vec3(0.0, 0.0, 0.0)), hash31(i + vec3(1.0, 0.0, 0.0)), u.x);
    let b = mix(hash31(i + vec3(0.0, 1.0, 0.0)), hash31(i + vec3(1.0, 1.0, 0.0)), u.x);
    let c = mix(hash31(i + vec3(0.0, 0.0, 1.0)), hash31(i + vec3(1.0, 0.0, 1.0)), u.x);
    let d = mix(hash31(i + vec3(0.0, 1.0, 1.0)), hash31(i + vec3(1.0, 1.0, 1.0)), u.x);
    return mix(mix(a, b, u.y), mix(c, d, u.y), u.z);
}

fn luma(c: vec3<f32>) -> f32 {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

fn saturate_color(c: vec3<f32>, amount: f32) -> vec3<f32> {
    let l = luma(c);
    return max(vec3(l) + (c - vec3(l)) * amount, vec3(0.0));
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    pbr_input.material.base_color = alpha_discard(
        pbr_input.material.flags,
        pbr_input.material.alpha_cutoff,
        pbr_input.material.base_color,
    );

    // Brush texture: gentle value variation (normal space keeps it glued to moving characters).
    let paint_pos = mix(pbr_input.N * 2.6, in.world_position.xyz * 1.7, toon.settings.w);
    let n = value_noise(paint_pos) * 0.65 + value_noise(paint_pos * 2.7 + vec3(17.0)) * 0.35;
    let paint = 1.0 + toon.settings.z * (n - 0.5) * 2.0;
    let albedo = pbr_input.material.base_color.rgb * paint;
    pbr_input.material.base_color = vec4(albedo, pbr_input.material.base_color.a);

    let lit = apply_pbr_lighting(pbr_input);

    // Posterize received light in log2 space: flat painted bands with a soft terminator.
    let received = max(luma(lit.rgb) / max(luma(albedo), 0.002), 1.0e-4);
    let ev = log2(received);
    let band = max(toon.ramp.x, 0.25);
    let t = ev / band;
    let stepped = (floor(t) + smoothstep(0.5 - toon.ramp.y, 0.5 + toon.ramp.y, fract(t))) * band;
    var color = lit.rgb * exp2(stepped - ev);

    // Rich, cool-leaning shadows (Hades-style): more saturation and a hue lean in the dark bands.
    let darkness = clamp(-stepped * 0.35, 0.0, 1.0);
    color = saturate_color(color, 1.0 + toon.ramp.z * darkness);
    color = mix(color, color * toon.shade.rgb * 2.0, toon.shade.a * darkness);
    color = mix(lit.rgb, color, toon.settings.x);

    // Coloured rim on silhouettes.
    let ndv = clamp(dot(pbr_input.N, pbr_input.V), 0.0, 1.0);
    let width = clamp(toon.settings.y, 0.01, 0.95);
    let rim = smoothstep(1.0 - width, 1.0 - width * 0.55, 1.0 - ndv);
    color += toon.rim.rgb * toon.rim.a * rim;

    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(pbr_input, vec4(color, lit.a));
    return out;
}
