// GODFORGE hand-painted arena floor.
//
// World-space procedural flagstones (no tiling repeats) painted in the biome palette:
// per-slab value/temperature shifts, directional brush strokes, a light-catching bevel, grime
// in the mortar, a gold mosaic ring at the arena heart and pulsing lava cracks. The result still
// goes through Bevy's lighting (shadows, brazier light pools) and is gently posterized like the
// toon material so the whole frame reads as one painting.

import bevy_pbr::render::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
    forward_io::{VertexOutput, FragmentOutput},
    mesh_view_bindings::globals,
};

struct FloorParams {
    /// slab base colour (linear)
    stone: vec4<f32>,
    /// mortar and grime colour (linear)
    mortar: vec4<f32>,
    /// crack glow colour (linear); a = glow strength (HDR)
    accent: vec4<f32>,
    /// inlay metal colour (linear); a = mosaic ring radius (0 = none)
    gold: vec4<f32>,
    /// xy = arena half extents (world x, z), z = slab size, w = crack density
    shape: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> fp: FloorParams;

const TAU: f32 = 6.2831853;

fn hash21(p: vec2<f32>) -> f32 {
    var p3 = fract(vec3(p.x, p.y, p.x) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

fn hash22(p: vec2<f32>) -> vec2<f32> {
    var p3 = fract(vec3(p.x, p.y, p.x) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

fn noise2(p: vec2<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let u = f * f * (3.0 - 2.0 * f);
    let a = hash21(i);
    let b = hash21(i + vec2(1.0, 0.0));
    let c = hash21(i + vec2(0.0, 1.0));
    let d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

fn fbm(p: vec2<f32>) -> f32 {
    var sum = 0.0;
    var amp = 0.5;
    var q = p;
    for (var i = 0; i < 4; i++) {
        sum += amp * noise2(q);
        q = q * 2.03 + vec2(1.7, 9.2);
        amp *= 0.5;
    }
    return sum;
}

struct Cell {
    d1: f32,
    d2: f32,
    id: vec2<f32>,
}

fn voronoi(p: vec2<f32>) -> Cell {
    let i = floor(p);
    let f = fract(p);
    var d1 = 8.0;
    var d2 = 8.0;
    var id = vec2(0.0);
    for (var y = -1; y <= 1; y++) {
        for (var x = -1; x <= 1; x++) {
            let g = vec2(f32(x), f32(y));
            let o = hash22(i + g) * 0.7 + 0.15;
            let r = g + o - f;
            let d = dot(r, r);
            if d < d1 {
                d2 = d1;
                d1 = d;
                id = i + g;
            } else if d < d2 {
                d2 = d;
            }
        }
    }
    return Cell(sqrt(d1), sqrt(d2), id);
}

fn luma(c: vec3<f32>) -> f32 {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let w = vec2(in.world_position.x, in.world_position.z);
    let t = globals.time;

    // ── flagstones ──
    let slab = max(fp.shape.z, 0.3);
    let c = voronoi(w / slab);
    let edge = c.d2 - c.d1;
    let mortar = 1.0 - smoothstep(0.03, 0.1, edge);
    let v = hash21(c.id);
    let v2 = hash21(c.id + vec2(17.3, 3.1));

    // Brush strokes: stretched fbm reads as a loaded brush dragged across each slab.
    let strokes = fbm(vec2(w.x * 0.7 + w.y * 0.3, w.y * 1.6) * 1.1 + c.id * 3.7);
    let grain = noise2(w * 11.0);
    var stone = fp.stone.rgb * (0.74 + 0.4 * v) * (0.82 + 0.36 * strokes) * (0.94 + 0.12 * grain);
    stone = mix(stone, stone * vec3(1.12, 0.98, 0.86), v2 * 0.6);

    // Light-catching bevel on the edges that face the key light (upper left), shadowed opposite.
    let c2 = voronoi((w + vec2(-0.07, -0.07)) / slab);
    let slope = (c2.d2 - c2.d1) - edge;
    stone *= 1.0 + clamp(slope * 6.0, -0.35, 0.45) * (1.0 - mortar);

    // Grime pools in the mortar and in low noise valleys.
    let grime = smoothstep(0.35, 0.75, fbm(w * 0.33 + vec2(5.0, 1.0)));
    var color = mix(stone, fp.mortar.rgb, clamp(mortar * 0.9 + grime * 0.25, 0.0, 1.0));

    // ── gold mosaic at the arena heart ──
    var gold_mask = 0.0;
    let ring_r = fp.gold.a;
    if ring_r > 0.0 {
        let r = length(w);
        let ang = atan2(w.y, w.x);
        let outer = 1.0 - smoothstep(0.03, 0.09, abs(r - ring_r));
        let inner = 1.0 - smoothstep(0.02, 0.07, abs(r - ring_r * 0.8));
        let seg = fract(ang / TAU * 32.0);
        let band = step(ring_r * 0.82, r) * step(r, ring_r * 0.98);
        let tesserae = band * smoothstep(0.08, 0.2, seg) * (1.0 - smoothstep(0.8, 0.92, seg));
        // Eight-pointed star rosette in the centre.
        let star_r = ring_r * (0.28 + 0.12 * pow(abs(cos(ang * 4.0)), 3.0));
        let star = (1.0 - smoothstep(star_r - 0.06, star_r, r)) * step(ring_r * 0.12, r);
        let hub = 1.0 - smoothstep(0.02, 0.06, abs(r - ring_r * 0.12));
        gold_mask = clamp(outer + inner + tesserae * 0.55 + star * 0.8 + hub, 0.0, 1.0);
        gold_mask *= 0.75 + 0.25 * strokes;
    }
    color = mix(color, fp.gold.rgb * (0.8 + 0.4 * strokes), gold_mask);

    // ── lava cracks ──
    let field = fbm(w * 0.28 + vec2(3.1, 7.7));
    let crack_line = 1.0 - smoothstep(0.0, 0.016, abs(field - 0.5));
    let crack_zone = smoothstep(0.48, 0.64, fbm(w * 0.09 + vec2(11.0, 2.0)));
    let crack = crack_line * crack_zone * fp.shape.w * (1.0 - gold_mask);
    let pulse = 0.7 + 0.3 * sin(t * 1.6 + field * 14.0);
    color = mix(color, fp.mortar.rgb * 0.4, crack);
    let glow = fp.accent.rgb * fp.accent.a * crack * pulse;
    // Heat haze: warm the stone around the cracks.
    color += fp.accent.rgb * 0.12 * crack_zone * fp.shape.w * (1.0 - smoothstep(0.0, 0.12, abs(field - 0.5)));

    // ── vignette toward the platform rim ──
    let half = fp.shape.xy;
    let to_edge = min(half.x - abs(w.x), half.y - abs(w.y));
    color *= 1.0 - 0.5 * (1.0 - smoothstep(0.0, 5.0, to_edge));

    pbr_input.material.base_color = vec4(color, 1.0);
    pbr_input.material.emissive = vec4(glow, 1.0);
    pbr_input.material.perceptual_roughness = mix(0.94, 0.42, gold_mask);
    pbr_input.material.metallic = gold_mask * 0.7;

    let lit = apply_pbr_lighting(pbr_input);

    // Gentle posterization so brazier light pools and shadows land as painted bands.
    let received = max(luma(lit.rgb) / max(luma(color), 0.002), 1.0e-4);
    let ev = log2(received);
    let stepped = (floor(ev) + smoothstep(0.3, 0.7, fract(ev)));
    let toon = lit.rgb * exp2(stepped - ev);
    let final_color = mix(lit.rgb, toon, 0.55) + glow;

    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(pbr_input, vec4(final_color, 1.0));
    return out;
}
