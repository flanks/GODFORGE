// GODFORGE UI: the molten fill of the Team Overdrive hex (UI_STYLE §11.5).
//
// The mask texture gives the shape. Below a wavy level the shape is poured metal, graded by
// depth through the molten ramp (#7A3E12 deep, #E8942E, #FFC95A, #FFF6DA at the surface) with a
// slow heat shimmer; a 1.4 px #FFFBEA meniscus rides the level; above it sits a #2B1F16 → #0E0907
// lacquer. Ready: the metal runs white-hot at the top and breathes. Active: the level drains
// from the top and the surface glows.

import bevy_ui_render::ui_vertex_output::UiVertexOutput;

struct MoltenParams {
    // x fill 0..1, y time (s), z ready 0/1, w active 0/1
    p: vec4<f32>,
}

@group(1) @binding(0) var<uniform> molten: MoltenParams;
@group(1) @binding(1) var mask_texture: texture_2d<f32>;
@group(1) @binding(2) var mask_sampler: sampler;

const PI: f32 = 3.14159265;

fn lin(c: vec3<f32>) -> vec3<f32> {
    return pow(c, vec3<f32>(2.2));
}

fn hexc(r: f32, g: f32, b: f32) -> vec3<f32> {
    return lin(vec3<f32>(r, g, b) / 255.0);
}

// t = 0 at the bottom of the pour, 1 at its surface.
fn molten_ramp(t: f32) -> vec3<f32> {
    let deep = hexc(122.0, 62.0, 18.0);
    let orange = hexc(232.0, 148.0, 46.0);
    let gold = hexc(255.0, 201.0, 90.0);
    let pale = hexc(255.0, 246.0, 218.0);
    if t < 0.45 {
        return mix(deep, orange, t / 0.45);
    }
    if t < 0.85 {
        return mix(orange, gold, (t - 0.45) / 0.4);
    }
    return mix(gold, pale, (t - 0.85) / 0.15);
}

@fragment
fn fragment(in: UiVertexOutput) -> @location(0) vec4<f32> {
    let m = textureSample(mask_texture, mask_sampler, in.uv).a;
    let fill = clamp(molten.p.x, 0.0, 1.0);
    let time = molten.p.y;
    let ready = molten.p.z;
    let drain = molten.p.w;

    let y = 1.0 - in.uv.y;
    let px1 = 1.0 / max(in.size.y, 1.0);
    let partial = step(0.002, fill) * step(fill, 0.998);
    let level = fill + partial * 0.012 * sin(in.uv.x * 3.0 * PI + time * 2.4);

    // Lacquer above the level.
    var col = mix(hexc(14.0, 9.0, 7.0), hexc(43.0, 31.0, 22.0), clamp(y * 1.2, 0.0, 1.0));
    if y < level {
        let depth = clamp(y / max(level, 0.08), 0.0, 1.0);
        var metal = molten_ramp(depth * 0.92 + 0.04);
        // Slow convection bands in the pour.
        metal = metal * (1.0 + 0.06 * sin(y * 38.0 - time * 1.7 + sin(in.uv.x * 9.0 + time) * 1.2));
        // Ready: white-hot crown that breathes; active: the whole pour glows.
        let breathe = 0.5 + 0.5 * sin(time * 2.0 * PI / 1.6);
        metal = mix(metal, hexc(255.0, 251.0, 234.0), ready * smoothstep(0.55, 1.0, depth) * (0.25 + 0.2 * breathe));
        metal = metal * (1.0 + drain * 0.25);
        col = metal;
    }
    // The meniscus line at the pour front.
    let d = abs(y - level) / px1;
    let meniscus = (1.0 - smoothstep(0.2, 1.4, d)) * partial;
    col = mix(col, hexc(255.0, 251.0, 234.0), meniscus);
    return vec4<f32>(col, m);
}
