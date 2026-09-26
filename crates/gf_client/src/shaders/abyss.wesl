// GODFORGE abyss: the animated sea far below the arena platform.
//
// Unlit and painted: every biome has its own depth.
//
// * 0 magma (Cinder Wastes): slow-flowing crust plates split by glowing veins, a heat bloom
//   hugging the cliff feet, dark cooled crust far out;
// * 1 deep water (Verdant Ruin): dark still water with drifting caustic light, bioluminescent
//   motes and a mist bank at the cliffs;
// * 2 night sky (Hollow Spire): a void of stars and slow nebula wisps with cloud banks below the
//   platform;
// * 3 chaos (The Unmaking): a churning violet vortex cut by bright fractures.
//
// Everything fades toward the deep colour with distance from the platform (a fog-like falloff)
// and the value is gently banded so it reads as paint rather than as a render.

import bevy_pbr::render::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::main_pass_post_lighting_processing,
    forward_io::{VertexOutput, FragmentOutput},
    mesh_view_bindings::globals,
};

struct AbyssParams {
    /// rgb far / darkest colour
    deep: vec4<f32>,
    /// rgb body colour
    mid: vec4<f32>,
    /// rgb hot / luminous colour (linear, HDR); a = intensity
    glow: vec4<f32>,
    /// rgb haze hugging the cliffs; a = haze strength
    mist: vec4<f32>,
    /// xy = platform half extents (world x, z), z = style, w = seed
    shape: vec4<f32>,
    /// x = flow speed, y = pattern scale, z = cliff glow width, w = far fade distance
    flow: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(100) var<uniform> ab: AbyssParams;

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
    for (var i = 0; i < 5; i++) {
        sum += amp * noise2(q);
        q = q * 2.02 + vec2(1.7, 9.2);
        amp *= 0.5;
    }
    return sum;
}

struct Cell {
    d1: f32,
    d2: f32,
    id: vec2<f32>,
}

/// Voronoi whose feature points orbit slowly (drifting crust plates, caustics).
fn voronoi_t(p: vec2<f32>, t: f32) -> Cell {
    let i = floor(p);
    let f = fract(p);
    var d1 = 8.0;
    var d2 = 8.0;
    var id = vec2(0.0);
    for (var y = -1; y <= 1; y++) {
        for (var x = -1; x <= 1; x++) {
            let g = vec2(f32(x), f32(y));
            let h = hash22(i + g);
            let o = 0.5 + 0.38 * sin(t + h * 6.2831);
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

fn sd_box(p: vec2<f32>, b: vec2<f32>) -> f32 {
    let d = abs(p) - b;
    return length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0);
}

/// Soft value banding: flat painted shapes with feathered edges.
fn band(v: f32, steps: f32) -> f32 {
    let s = v * steps;
    return (floor(s) + smoothstep(0.3, 0.7, fract(s))) / steps;
}

/// `map` is 1 under a biome map (the platform box is map-sized): the sea there is seen through
/// bays and chasms right beside the play space, so it keeps to the bottom of the value ladder,
/// mostly dark cooled crust with thin, dim channels (the cliffs' own heat marks the edge).
fn magma(w: vec2<f32>, d: f32, t: f32, near: f32, bank: f32, map: f32) -> vec3<f32> {
    let sc = ab.flow.y;
    let q = w * sc + ab.shape.w * 0.37;
    // Domain warp: the whole sea creeps and folds.
    let warp = vec2(fbm(q * 0.5 + vec2(t * 0.015, -t * 0.01)), fbm(q * 0.5 + vec2(5.2, 1.3) - vec2(t * 0.012, t * 0.016)));
    let p = q + (warp - 0.5) * 2.4;
    // Liquid channels between cooled crust islands; the lava licks right up to the cliff feet.
    let m = fbm(p * 0.55 + vec2(t * 0.01, 0.0));
    // `mid.a` raises the molten share (surface rivers); banks run hotter still.
    let level = 0.36 + 0.06 * near + 0.22 * exp(-d / 0.6) * (1.0 - map) + ab.mid.a + 0.2 * bank - 0.1 * map;
    let liquid = 1.0 - smoothstep(level - 0.015, level + 0.015, m);
    // The hottest line is where the crust meets the liquid.
    let rim = 1.0 - smoothstep(0.0, 0.028, abs(m - level - 0.02));
    // Crust: dark, brushy, cooling toward the island interiors, split by thin glowing cracks.
    let c = voronoi_t(p * 1.7, t * 0.05);
    let crack = 1.0 - smoothstep(0.012, 0.05, c.d2 - c.d1);
    let brush = fbm(vec2(p.x * 2.2, p.y * 0.7) + 11.0);
    let interior = smoothstep(level, level + 0.16, m);
    var crust = mix(ab.deep.rgb, ab.mid.rgb, band(0.25 + 0.75 * brush, 3.0) * (1.0 - 0.4 * map));
    crust *= 1.0 - 0.5 * interior;
    // Liquid: slow streaks drawn along the flow.
    let streak = fbm(vec2(p.x * 1.4 - t * 0.05, p.y * 4.2));
    let pulse = 0.82 + 0.18 * sin(t * 0.8 + m * 20.0);
    // Far from the cliffs the channels cool and dim; the heat lives at the cliff feet.
    let heat = (0.45 + 0.55 * near) * (1.0 - 0.45 * map);
    let lava = ab.glow.rgb * ab.glow.a * (0.3 + 0.4 * streak) * pulse * heat;
    var col = mix(crust, lava, liquid);
    col += ab.glow.rgb * ab.glow.a * crack * (1.0 - liquid) * (0.06 + 0.22 * (1.0 - interior)) * pulse * heat;
    col += mix(ab.glow.rgb, vec3(1.0, 0.72, 0.3), 0.3) * ab.glow.a * rim * 0.65 * pulse * heat;
    // The bank band: where the liquid licks the stone it runs white-hot.
    col += mix(ab.glow.rgb, vec3(1.0, 0.8, 0.45), 0.35) * ab.glow.a * bank * bank * 0.55 * pulse;
    // Smoke hanging over the sea: it reads as far below.
    let smoke = fbm(vec2(w.x * 0.08 + t * 0.02, w.y * 0.12 - t * 0.015));
    col = mix(col, ab.mid.rgb * 0.8, smoothstep(0.35, 0.75, smoke) * 0.45);
    return col;
}

fn water(w: vec2<f32>, d: f32, t: f32, near: f32) -> vec3<f32> {
    let sc = ab.flow.y;
    let q = w * sc + ab.shape.w * 0.29;
    let warp = vec2(fbm(q * 0.5 + t * 0.01), fbm(q * 0.5 + vec2(3.7, 8.1) - t * 0.012));
    let p = q + (warp - 0.5) * 2.0;
    let body = fbm(vec2(p.x * 0.9, p.y * 2.2) + vec2(t * 0.02, 0.0));
    var col = mix(ab.deep.rgb, ab.mid.rgb, band(body, 3.0));
    // Drifting caustic light, in patches.
    let c = voronoi_t(p * 1.6, t * 0.25);
    let caustic = pow(1.0 - smoothstep(0.0, 0.2, c.d2 - c.d1), 3.0) * smoothstep(0.52, 0.75, fbm(p * 0.35 + 3.0 + t * 0.02));
    col += ab.glow.rgb * caustic * 0.16 * ab.glow.a * (0.3 + 0.7 * near);
    // Bioluminescent motes.
    let cell = floor(w * 1.3);
    let h = hash22(cell + ab.shape.w);
    let mote_p = (cell + 0.2 + h * 0.6) / 1.3;
    let md = length(w - mote_p);
    let blink = 0.5 + 0.5 * sin(t * (0.6 + h.x) + h.y * 40.0);
    let mote = (1.0 - smoothstep(0.02, 0.09, md)) * step(0.86, hash21(cell + 7.0)) * blink;
    col += ab.glow.rgb * mote * ab.glow.a * 1.4;
    // Ripple foam line and glow where the water meets the cliffs.
    let foam = (1.0 - smoothstep(0.0, 0.5, abs(d - 0.35 - 0.2 * sin(t * 0.7 + w.x * 0.5 + w.y * 0.5))));
    col += ab.glow.rgb * foam * 0.25 * ab.glow.a;
    return col;
}

fn sky(w: vec2<f32>, d: f32, t: f32, near: f32) -> vec3<f32> {
    let sc = ab.flow.y;
    let q = w * sc + ab.shape.w * 0.41;
    var col = mix(ab.deep.rgb, ab.mid.rgb, band(fbm(q * 0.5 + vec2(t * 0.004, 0.0)), 3.0));
    // Nebula wisps.
    let neb = fbm(vec2(q.x * 0.7 + t * 0.01, q.y * 1.4) + fbm(q * 0.3) * 2.0);
    col = mix(col, ab.glow.rgb * 0.22, smoothstep(0.55, 0.85, neb) * 0.6);
    // Stars: one candidate per cell, a few brighter with a cross glint.
    let cell = floor(w * 1.6);
    let h = hash22(cell + ab.shape.w);
    let sp = (cell + 0.15 + h * 0.7) / 1.6;
    let sd = w - sp;
    let bright = hash21(cell + 3.3);
    let tw = 0.6 + 0.4 * sin(t * (1.0 + h.x * 2.0) + h.y * 50.0);
    let star = (1.0 - smoothstep(0.0, 0.05 + 0.05 * bright, length(sd))) * step(0.55, bright) * tw;
    let glint = (1.0 - smoothstep(0.0, 0.015, abs(sd.x))) * (1.0 - smoothstep(0.0, 0.25, abs(sd.y)))
        + (1.0 - smoothstep(0.0, 0.015, abs(sd.y))) * (1.0 - smoothstep(0.0, 0.25, abs(sd.x)));
    col += ab.glow.rgb * ab.glow.a * (star * 1.2 + glint * step(0.93, bright) * tw * 0.6);
    return col;
}

fn chaos(w: vec2<f32>, d: f32, t: f32, near: f32) -> vec3<f32> {
    let sc = ab.flow.y;
    let q = w * sc + ab.shape.w * 0.23;
    // Vortex: rotate the domain more strongly toward a slowly wandering eye.
    let eye = vec2(sin(t * 0.05), cos(t * 0.04)) * 6.0;
    let rel = q - eye;
    let rad = length(rel);
    let a = t * 0.06 + 2.2 / (1.0 + rad * 0.35);
    let rot = vec2(rel.x * cos(a) - rel.y * sin(a), rel.x * sin(a) + rel.y * cos(a));
    let p = rot + eye;
    let swirl = fbm(p * 0.6 + fbm(p * 0.3 + t * 0.02) * 3.0);
    var col = mix(ab.deep.rgb, ab.mid.rgb * 1.6, band(swirl, 3.0));
    // Nebula ribbons wound into the vortex.
    let ribbon = pow(1.0 - abs(fbm(p * 0.45 - t * 0.015) * 2.0 - 1.0), 6.0);
    col += ab.glow.rgb * ab.glow.a * ribbon * 0.22;
    // Fractures: sharp seams that open in patches and flicker, never a uniform web.
    let c = voronoi_t(p * 0.7, t * 0.15);
    let seam = 1.0 - smoothstep(0.0, 0.04, c.d2 - c.d1);
    let open = smoothstep(0.52, 0.72, fbm(p * 0.25 + vec2(t * 0.03, 4.0)));
    let flick = step(0.3, hash21(c.id + floor(t * 1.5)));
    col += ab.glow.rgb * ab.glow.a * seam * open * (0.25 + 0.75 * flick) * 0.8;
    col += ab.glow.rgb * smoothstep(0.62, 0.9, swirl) * 0.2 * ab.glow.a;
    return col;
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    let pbr_input = pbr_input_from_standard_material(in, is_front);
    let w = vec2(in.world_position.x, in.world_position.z);
    let t = globals.time * ab.flow.x;
    let d = max(sd_box(w, ab.shape.xy), 0.0);
    // Heat / haze hugging the cliff feet, and the fog-like fade with distance.
    let near = exp(-d / max(ab.flow.z, 0.1));
    let far = smoothstep(0.0, max(ab.flow.w, 1.0), d + (fbm(w * 0.05) - 0.5) * 8.0);

    let style = i32(ab.shape.z + 0.5);
    var col: vec3<f32>;
    if style == 1 {
        col = water(w, d, t, near);
    } else if style == 2 {
        col = sky(w, d, t, near);
    } else if style == 3 {
        col = chaos(w, d, t, near);
    } else {
        // Surface liquids carry bank heat on their vertex colours (red channel).
        var bank = 0.0;
        @if(VERTEX_COLORS) {
            bank = in.color.r;
        }
        col = magma(w, d, t, near, bank, select(0.0, 1.0, ab.shape.x > 120.0));
    }

    // Haze bank at the cliffs: brushy, drifting.
    let haze_n = fbm(vec2(w.x * 0.18 + t * 0.03, w.y * 0.18 - t * 0.02));
    let haze = ab.mist.a * near * (0.55 + 0.45 * haze_n);
    col = mix(col, ab.mist.rgb, clamp(haze, 0.0, 0.9));
    // Far away everything sinks into the deep colour.
    col = mix(col, ab.deep.rgb * 0.8, far * 0.85);

    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(pbr_input, vec4(col, 1.0));
    return out;
}
