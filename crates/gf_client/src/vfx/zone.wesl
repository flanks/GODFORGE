// GODFORGE zones: painted, animated ground shapes for hazards (docs/art/VFX_STYLE.md §16), the
// ability and synergy fields (§13-14) and enemy telegraphs (§15.1).
//
// One quad per zone in the local plane of its parent (+y = the zone's forward, metres). Every mode
// paints flat, posterized value bands through a five-tone ramp (ink / deep / body / light / hot):
// no soft gradients as the main shape, ink under light, and hot bands that add instead of occlude.
// Output is premultiplied (AlphaMode::Premultiplied).
//
// Telegraphs keep the red-white language: a faint hatched fill over the whole shape, the fill
// growing from the centre with a white-hot front, a crisp red rim with a white core, a crackle
// that runs along the rim, a faster blink in the last fifth, and a short resolve flash.

import bevy_pbr::render::{
    forward_io::VertexOutput,
    mesh_view_bindings::globals,
};

struct ZoneParams {
    /// x = mode, y = element / variant, z = flags (1 ally, 2 hem only, 4 no hem, 8 resolve), w = seed
    mode: vec4<f32>,
    /// the quad in the local plane: centre (x, y), size (z, w), metres
    quad: vec4<f32>,
    /// x = radius / length, y = width / inner radius / half angle (rad), z = hem width, w = unused
    shape: vec4<f32>,
    /// x = globals.time at progress 0, y = duration (s), z = interior alpha, w = gain
    timing: vec4<f32>,
    ink: vec4<f32>,
    deep: vec4<f32>,
    body: vec4<f32>,
    light: vec4<f32>,
    /// hem colour (rgb, linear), a = hem alpha
    hem: vec4<f32>,
    /// a second accent tone (rgb, linear): fire-lit arm heads, green petal edges, glyphs
    alt: vec4<f32>,
}

@group(constants::MATERIAL_BIND_GROUP) @binding(0) var<uniform> z: ZoneParams;

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

fn fbm3(p: vec2<f32>) -> f32 {
    var sum = 0.0;
    var amp = 0.5;
    var q = p;
    for (var i = 0; i < 3; i++) {
        sum += amp * noise2(q);
        q = q * 2.03 + vec2(1.7, 9.2);
        amp *= 0.5;
    }
    return sum / 0.875;
}

/// x = distance to the nearest cell point, y = distance to the cell border (d2 - d1), zw = cell id
fn voronoi(p: vec2<f32>) -> vec4<f32> {
    let i = floor(p);
    let f = fract(p);
    var d1 = 8.0;
    var d2 = 8.0;
    var id = vec2(0.0);
    for (var y = -1; y <= 1; y++) {
        for (var x = -1; x <= 1; x++) {
            let g = vec2(f32(x), f32(y));
            let o = hash22(i + g);
            let d = length(g + o - f);
            if (d < d1) {
                d2 = d1;
                d1 = d;
                id = i + g;
            } else if (d < d2) {
                d2 = d;
            }
        }
    }
    return vec4(d1, d2 - d1, id);
}

/// The ramp: posterized ink / deep / body / light / hot.
fn tone(v: f32) -> vec3<f32> {
    if (v < 0.18) {
        return z.ink.rgb;
    }
    if (v < 0.42) {
        return z.deep.rgb;
    }
    if (v < 0.66) {
        return z.body.rgb;
    }
    if (v < 0.86) {
        return z.light.rgb;
    }
    return mix(z.light.rgb, vec3(1.0), 0.6) * 2.0;
}

/// A premultiplied paint layer at ramp value `v`, coverage `a`. Hot values add light.
fn paint(v: f32, a: f32) -> vec4<f32> {
    let cov = clamp(a, 0.0, 1.0);
    let add = smoothstep(0.84, 0.9, v);
    let g = select(1.0, z.timing.w, v > 0.3);
    return vec4(tone(v) * g * cov, cov * (1.0 - add));
}

/// A premultiplied layer of a given colour (accents, telegraph red and white).
fn paint_rgb(c: vec3<f32>, a: f32, additive: f32) -> vec4<f32> {
    let cov = clamp(a, 0.0, 1.0);
    return vec4(c * cov, cov * (1.0 - additive));
}

fn over(top: vec4<f32>, bottom: vec4<f32>) -> vec4<f32> {
    return top + bottom * (1.0 - top.a);
}

/// Anti-aliasing widths, set once per fragment in uniform control flow (derivatives are not
/// allowed after the per-fragment early outs): metres, and units of the zone radius.
var<private> AAM: f32;
var<private> AAN: f32;

/// A band of half-width `w` around `d` = 0 (units of the radius), anti-aliased.
fn band(d: f32, w: f32) -> f32 {
    return 1.0 - smoothstep(w - AAN, w + AAN, abs(d));
}

/// Inside (d < 0, units of the radius), anti-aliased.
fn fill(d: f32) -> f32 {
    return 1.0 - smoothstep(-AAN, AAN, d);
}

/// A band in metres.
fn band_m(d: f32, w: f32) -> f32 {
    return 1.0 - smoothstep(w - AAM, w + AAM, abs(d));
}

/// Inside, in metres.
fn fill_m(d: f32) -> f32 {
    return 1.0 - smoothstep(-AAM, AAM, d);
}

// ───────────────────────────── hems ─────────────────────────────

/// The thin broken hem at the true radius: player zones gold, enemy zones red-white dashes.
fn hem(p: vec2<f32>, radius: f32, t: f32, seed: f32, enemy: bool) -> vec4<f32> {
    let r = length(p);
    let a = atan2(p.y, p.x);
    let wob = (noise2(vec2(a * 2.2 + seed, seed)) - 0.5) * 0.05 * min(radius, 3.0);
    let d = r - radius - wob;
    let segs = clamp(floor(radius * 1.6), 4.0, 22.0);
    let f = fract(a / TAU * segs + seed + t * 0.015);
    let hw = z.shape.z;
    if (enemy) {
        // Dashes: a red body with a white core, gaps between them.
        let on = step(0.16, f) * (1.0 - step(0.92, f));
        let cov = band_m(d, hw) * on;
        let core = band_m(d, hw * 0.35) * on * step(0.5, fract(f * 2.0));
        let red = paint_rgb(z.hem.rgb * 2.2, cov * z.hem.a, 0.0);
        return over(paint_rgb(vec3(3.0), core * z.hem.a, 0.5), red);
    }
    // Broken and tapered: 3-5 gaps, each dash thins at its ends.
    let taper = smoothstep(0.0, 0.2, f) * (1.0 - smoothstep(0.78, 0.96, f));
    let cov = band_m(d, hw * (0.3 + 0.7 * taper)) * step(0.02, taper);
    let ink = band_m(d - hw * 0.4, hw * 1.6 * (0.3 + 0.7 * taper)) * step(0.02, taper);
    let c = over(paint_rgb(z.hem.rgb * 1.3, cov * z.hem.a, 0.0), paint_rgb(z.ink.rgb, ink * z.hem.a * 0.45, 0.0));
    return c;
}

// ───────────────────────────── hazard looks ─────────────────────────────

/// Well: 3 ink spiral arms turning inward with bright void rims on their heads, an ink core that
/// pulses with each tick.
fn well(p: vec2<f32>, radius: f32, t: f32, seed: f32, arms: f32, speed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    let a = atan2(p.y, p.x);
    let n = noise2(p * 1.6 / max(radius * 0.3, 0.5) + vec2(t * 0.2, seed));
    let edge = r + (n - 0.5) * 0.14;
    if (edge > 1.02) {
        return vec4(0.0);
    }
    let ph = a * arms + log(max(r, 0.02)) * 4.2 + t * speed + seed * 7.0;
    let wave = 0.5 + 0.5 * cos(ph + (n - 0.5) * 1.4);
    let keep = 1.0 - smoothstep(0.82, 1.0, edge);
    var acc = paint(0.3, 0.28 * keep);
    let arm = smoothstep(0.52, 0.64, wave) * smoothstep(0.1, 0.28, r) * keep;
    acc = over(paint(0.06, arm * 0.88), acc);
    let rim = smoothstep(0.5, 0.53, wave) * (1.0 - smoothstep(0.55, 0.6, wave)) * smoothstep(0.3, 0.85, r) * keep;
    acc = over(paint(0.76, rim), acc);
    let pulse = 0.5 + 0.5 * sin(t * 6.0);
    acc = over(paint(0.06, fill(r - 0.2) * 0.95), acc);
    acc = over(paint(0.9, band(r - 0.22 - 0.03 * pulse, 0.018) * (0.5 + 0.5 * pulse)), acc);
    return acc;
}

/// Fire: a charred patch with glowing ember cracks and licks around its rim (Flame fields, burning
/// ground, the Cinder Uppercut cracks, the mortar's burning field).
fn fire(p: vec2<f32>, radius: f32, t: f32, seed: f32, cracks: f32) -> vec4<f32> {
    let r = length(p) / radius;
    let a = atan2(p.y, p.x);
    let n = fbm3(p * 0.9 + vec2(seed, -t * 0.35));
    let edge = r + (n - 0.5) * 0.32;
    if (edge > 1.0) {
        return vec4(0.0);
    }
    let keep = 1.0 - smoothstep(0.86, 1.0, edge);
    var acc = paint(0.06, 0.6 * keep);
    acc = over(paint(0.3, 0.55 * smoothstep(0.45, 0.62, n) * keep), acc);
    // Ember cracks: cell borders flicker body → light.
    let cells = voronoi(p * cracks + vec2(seed * 3.1, seed));
    let crack = 1.0 - smoothstep(0.03, 0.09, cells.y);
    let flick = noise2(cells.zw * 3.7 + vec2(t * 3.0, 0.0));
    acc = over(paint(select(0.55, 0.78, flick > 0.55), crack * keep * (0.55 + 0.45 * flick)), acc);
    // Licks: tongues of flame noise running round the rim.
    let ln = noise2(vec2(a * 5.0 + seed * 11.0, r * 5.0 - t * 4.5));
    let lick = smoothstep(0.6, 0.72, ln) * smoothstep(0.62, 0.86, edge) * keep;
    acc = over(paint(select(0.72, 0.9, ln > 0.8), lick), acc);
    return acc;
}

/// Storm eye: ink smoke arms spiralling into a bright eye, their heads lit by `alt` (the fire of
/// Firestorm) or by the ramp's light (Heaven's Verdict).
fn storm_eye(p: vec2<f32>, radius: f32, t: f32, seed: f32, lit_alt: bool) -> vec4<f32> {
    let r = length(p) / radius;
    let a = atan2(p.y, p.x);
    let n = fbm3(p * 0.7 + vec2(t * 0.15, seed));
    let edge = r + (n - 0.5) * 0.18;
    if (edge > 1.02) {
        return vec4(0.0);
    }
    let keep = 1.0 - smoothstep(0.84, 1.0, edge);
    var acc = paint(0.29, 0.3 * keep);
    let ph = a * 3.0 - log(max(r, 0.03)) * 3.4 - t * 2.2 + seed * 5.0;
    let wave = 0.5 + 0.5 * cos(ph + (n - 0.5) * 2.6);
    let arm = smoothstep(0.46, 0.6, wave) * smoothstep(0.14, 0.32, r) * keep;
    acc = over(paint(0.06, arm * 0.82), acc);
    let head = smoothstep(0.6, 0.64, wave) * (1.0 - smoothstep(0.66, 0.74, wave)) * smoothstep(0.25, 0.7, r) * keep;
    if (lit_alt) {
        acc = over(paint_rgb(z.alt.rgb * 1.6, head, 0.3), acc);
    } else {
        acc = over(paint(0.72, head), acc);
    }
    // The eye: a bright core that flickers at 12 Hz, a white-hot centre.
    let flick = 0.75 + 0.25 * step(0.5, fract(t * 12.0 + seed));
    let eye_r = 0.17 + 0.02 * sin(t * 9.0);
    acc = over(paint(0.06, band(r - eye_r - 0.03, 0.03) * 0.8), acc);
    acc = over(paint(0.62, fill(r - eye_r) * flick), acc);
    acc = over(paint(0.95, fill(r - eye_r * 0.45) * flick), acc);
    return acc;
}

/// Petals: a flower of decay opening then wilting (Entropy Bloom; Plague fields).
fn petals(p: vec2<f32>, radius: f32, t: f32, dur: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    let a = atan2(p.y, p.x) + t * 0.12 + seed;
    let open = smoothstep(0.0, 0.25, t);
    let wilt = smoothstep(dur * 0.55, dur, t);
    let k = 7.0;
    let pa = abs(fract(a * k / TAU) - 0.5) * 2.0;
    let n = noise2(p * 1.2 + vec2(seed, t * 0.1));
    let reach = open * (0.45 + 0.55 * (1.0 - pa * pa)) * (1.0 - 0.2 * wilt) + (n - 0.5) * 0.08;
    let d = r - reach;
    if (r > 1.05) {
        return vec4(0.0);
    }
    var acc = paint(0.3, 0.22 * fill(r - 0.98 * open));
    acc = over(paint(0.06, fill(d) * 0.85), acc);
    // Sickly edges on every petal and a vein down its middle.
    acc = over(paint_rgb(z.alt.rgb * (1.4 - 0.6 * wilt), band(d + 0.03, 0.025), 0.0), acc);
    acc = over(paint(0.52, band(pa - 0.02, 0.03) * fill(d + 0.1) * smoothstep(0.15, 0.3, r) * (1.0 - wilt)), acc);
    acc = over(paint(0.62, fill(r - 0.12 * open) * 0.9), acc);
    return acc;
}

/// A puddle: a noisy element blob with bubbles that swell and pop (Puddle, Plague fields, Pools).
fn puddle(p: vec2<f32>, radius: f32, t: f32, seed: f32, crust: bool) -> vec4<f32> {
    let r = length(p) / radius;
    let n = fbm3(p * 0.8 / max(radius * 0.4, 0.4) + vec2(seed, t * 0.05));
    let edge = r + (n - 0.5) * 0.3;
    if (edge > 1.0) {
        return vec4(0.0);
    }
    let keep = 1.0 - smoothstep(0.9, 1.0, edge);
    var acc = paint(0.06, band(edge - 0.93, 0.07) * 0.9);
    acc = over(paint(0.3, 0.55 * fill(edge - 0.9)), acc);
    if (crust) {
        // Cooling crust plates drifting on a glowing flow.
        let cells = voronoi(p * 0.9 + vec2(t * 0.08, seed));
        let vein = 1.0 - smoothstep(0.04, 0.14, cells.y);
        let glow = 0.5 + 0.5 * sin(t * 2.0 + cells.z * 3.0 + cells.w);
        acc = over(paint(0.29, (1.0 - vein) * 0.75 * keep), acc);
        acc = over(paint(select(0.62, 0.8, glow > 0.6), vein * keep), acc);
    } else {
        acc = over(paint(0.62, smoothstep(0.55, 0.7, n) * 0.5 * keep), acc);
    }
    // Bubbles: each cell swells a ring, then pops.
    let b = voronoi(p * 1.8 + vec2(seed * 2.0, 0.0));
    let phase = fract(t * 0.7 + hash21(b.zw) * 3.0);
    let br = 0.08 + 0.2 * phase;
    let bubble = band(b.x - br, 0.025) * step(phase, 0.85) * step(0.5, hash21(b.zw + 7.0)) * keep;
    acc = over(paint(0.8, bubble), acc);
    return acc;
}

/// Storm crackle: dark blue ground cut by cell-edge veins that strobe.
fn crackle(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    let n = noise2(p * 0.9 + vec2(seed, 0.0));
    let edge = r + (n - 0.5) * 0.2;
    if (edge > 1.0) {
        return vec4(0.0);
    }
    let keep = 1.0 - smoothstep(0.85, 1.0, edge);
    var acc = paint(0.06, 0.35 * keep);
    let step_t = floor(t * 12.0);
    let cells = voronoi(p * 1.3 + vec2(seed, step_t * 0.37));
    let vein = band(cells.y, 0.03) * step(0.45, hash21(cells.zw + step_t)) * keep;
    acc = over(paint(0.78, vein), acc);
    return acc;
}

/// Glyph wheel: straight rays and a hard ring (Radiant fields).
fn wheel(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    if (r > 1.02) {
        return vec4(0.0);
    }
    let a = atan2(p.y, p.x) + t * 0.35 + seed;
    var acc = paint(0.3, 0.2);
    let rays = band(abs(fract(a * 12.0 / TAU) - 0.5), 0.04) * smoothstep(0.25, 0.4, r) * (1.0 - smoothstep(0.7, 0.8, r));
    acc = over(paint(0.72, rays * 0.9), acc);
    acc = over(paint(0.62, band(r - 0.82, 0.025)), acc);
    acc = over(paint(0.62, band(r - 0.22, 0.02)), acc);
    return acc;
}

/// Dust: a low ring of noisy blotches (Kinetic fields).
fn dust(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    let n = fbm3(p * 1.1 + vec2(seed, t * 0.3));
    let ring = smoothstep(0.4, 0.8, r) * (1.0 - smoothstep(0.88, 1.0, r + (n - 0.5) * 0.3));
    var acc = paint(0.3, ring * smoothstep(0.45, 0.6, n) * 0.6);
    acc = over(paint(0.62, ring * smoothstep(0.66, 0.72, n) * 0.5), acc);
    return acc;
}

/// Binding Hex: a hexagon snapping shut, a turning ring of rune ticks and a hexagram inside.
fn hexes(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let snap = smoothstep(0.0, 0.18, t);
    let rr = radius * (1.25 - 0.25 * snap);
    let q = abs(p) / rr;
    // Hexagon distance (pointy top).
    let hexd = max(q.x * 0.866025 + q.y * 0.5, q.y) - 0.92;
    let r = length(p) / rr;
    if (r > 1.05) {
        return vec4(0.0);
    }
    var acc = paint(0.06, 0.3 * fill(hexd));
    let a = atan2(p.y, p.x) - t * 0.6 + seed;
    let tick = band(abs(fract(a * 18.0 / TAU) - 0.5), 0.12) * band(r - 0.72, 0.05);
    acc = over(paint(0.7, tick * snap), acc);
    // The hexagram: two triangles.
    let ang = atan2(p.y, p.x);
    var tri = 1e3;
    for (var k = 0; k < 6; k++) {
        let th = f32(k) * TAU / 6.0 + seed * 0.0;
        let n = vec2(cos(th), sin(th));
        tri = min(tri, abs(dot(p / rr, n) - 0.3));
    }
    acc = over(paint_rgb(z.alt.rgb * 1.5, band(tri, 0.012) * fill(r - 0.62) * snap, 0.2), acc);
    acc = over(paint(0.62, band(hexd, 0.02)), acc);
    return acc;
}

/// Still Field: a pale bubble with 12 tick marks and a slow clock hand.
fn still(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    if (r > 1.04) {
        return vec4(0.0);
    }
    let a = atan2(p.y, p.x);
    var acc = paint(0.7, 0.05 * fill(r - 1.0));
    acc = over(paint(0.7, band(r - 0.985, 0.012)), acc);
    let tick = band(abs(fract(a * 12.0 / TAU + 0.5) - 0.5), 0.05) * band(r - 0.93, 0.045);
    acc = over(paint(0.9, tick), acc);
    // The hand sweeps once per 4 s.
    let hand = a - (-t * TAU / 4.0 + seed);
    let hd = abs(atan2(sin(hand), cos(hand)));
    acc = over(paint(0.62, band(hd * r, 0.012) * fill(r - 0.85) * 0.8), acc);
    // A soft trailing wedge behind the hand.
    let trail = smoothstep(0.7, 0.0, atan2(sin(hand), cos(hand))) * step(0.0, atan2(sin(hand), cos(hand)));
    acc = over(paint(0.7, trail * 0.12 * fill(r - 0.85)), acc);
    return acc;
}

/// Decoy: slow gold taunt pulses rolling out (ground only).
fn taunt(p: vec2<f32>, radius: f32, t: f32, seed: f32) -> vec4<f32> {
    let r = length(p) / radius;
    var acc = vec4(0.0);
    for (var k = 0; k < 2; k++) {
        let ph = fract(t * 0.9 + f32(k) * 0.5);
        let rr = 0.25 + ph * 0.9;
        acc = over(paint(0.72, band(r - rr, 0.03) * (1.0 - ph)), acc);
    }
    acc = over(paint(0.62, fill(r - 0.25) * 0.35), acc);
    return acc;
}

/// A straight hard-edged scar that cools (Piercing Comet): ink edge, white-gold core line.
fn scar(p: vec2<f32>, len: f32, w: f32, t: f32, dur: f32, seed: f32) -> vec4<f32> {
    let k = clamp(t / max(dur, 0.05), 0.0, 1.0);
    let n = noise2(vec2(p.y * 3.0, seed));
    let along = step(0.0, p.y) * step(p.y, len);
    let dx = abs(p.x) - w * (0.5 + 0.35 * n) * (1.0 - 0.4 * k);
    let front = smoothstep(len * min(t / 0.1, 1.0) + 0.1, len * min(t / 0.1, 1.0), p.y);
    var acc = paint(0.06, fill_m(dx) * along * front * (1.0 - k) * 0.9);
    let hot = select(0.95, select(0.72, 0.52, k > 0.5), k > 0.18);
    acc = over(paint(hot, fill_m(abs(p.x) - w * 0.18 * (1.0 - k)) * along * front * (1.0 - k)), acc);
    return acc;
}

// ───────────────────────────── telegraphs ─────────────────────────────

/// Enemy telegraphs, red-white (ally telegraphs gold). `mode` 20 circle, 21 line, 22 cone, 23 ring.
fn telegraph(p: vec2<f32>, mode: i32, t: f32, resolve: bool) -> vec4<f32> {
    let dur = max(z.timing.y, 0.05);
    let prog = clamp(t / dur, 0.0, 1.0);
    let red = z.body.rgb;
    let white = z.light.rgb;
    var q = 0.0;
    var sd = 0.0;
    var along = 0.0;
    var scale = 1.0;
    if (mode == 20) {
        let r = length(p);
        let rad = z.shape.x;
        q = r / rad;
        sd = r - rad;
        along = atan2(p.y, p.x) * rad;
        scale = rad;
    } else if (mode == 21) {
        let len = z.shape.x;
        let hw = z.shape.y * 0.5;
        q = p.y / len;
        let dx = abs(p.x) - hw;
        let dy = max(-p.y, p.y - len);
        sd = max(dx, dy);
        along = p.y + sign(p.x) * 50.0;
        scale = len;
    } else if (mode == 22) {
        let rad = z.shape.x;
        let half = z.shape.y;
        let r = length(p);
        let ang = atan2(p.x, p.y);
        q = r / rad;
        let side = r * sin(clamp(abs(ang) - half, -1.5, 1.5));
        sd = max(r - rad, select(side, r, abs(ang) - half > 1.5));
        along = ang * rad + select(0.0, r, abs(ang) > half - 0.05);
        scale = rad;
    } else {
        let outer = z.shape.x;
        let inner = z.shape.y;
        let r = length(p);
        q = r / outer;
        sd = max(r - outer, inner - r);
        along = atan2(p.y, p.x) * outer;
        scale = outer;
    }
    let ew = clamp(scale * 0.018, 0.07, 0.14);
    if (sd > ew * 3.0) {
        return vec4(0.0);
    }
    if (resolve) {
        // The resolve flash: the whole shape goes white, then red, then out in ~10 frames.
        // A light wash, never an opaque slab: bodies inside stay readable through it.
        let k = clamp(t / 0.18, 0.0, 1.0);
        let c = mix(white * 1.6, red * 1.6, smoothstep(0.0, 0.5, k));
        let inside = fill_m(sd);
        let a = inside * (1.0 - k) * (1.0 - k) * 0.38;
        let rim = band_m(sd, ew * (1.0 + 2.5 * k)) * (1.0 - k);
        return over(paint_rgb(white * 3.0, rim, 0.5), paint_rgb(c, a, 0.6));
    }
    let inside = fill_m(sd);
    // Faint hatched fill over the whole shape: the danger area from the first frame.
    let hatch = step(0.5, fract((p.x + p.y) * 1.25 - t * 0.8));
    var acc = paint_rgb(red * 1.2, inside * (0.13 + 0.05 * hatch), 0.0);
    // The fill grows from the centre; the last fifth blinks.
    let late = step(0.8, prog);
    let blink = late * step(0.5, fract(t * 10.0));
    let grown = inside * (1.0 - smoothstep(prog - 0.004, prog, q));
    let deepen = smoothstep(prog - 0.35, prog, q);
    acc = over(paint_rgb(mix(red * 1.7, white * 1.6, 0.25 * blink), grown * (0.3 + 0.14 * deepen + 0.12 * blink), 0.0), acc);
    // The white-hot front of the fill.
    let front = band_m((q - prog) * scale, 0.07) * inside * step(0.02, prog) * (1.0 - step(0.999, prog));
    acc = over(paint_rgb(white * 2.6, front, 0.4), acc);
    // The rim: red body, white core, a crackle running along it.
    let crk = noise2(vec2(along * 2.2 - t * 9.0, floor(t * 20.0) * 0.37));
    let spike = smoothstep(0.62, 0.9, crk);
    let rim = band_m(sd, ew * (1.0 + 0.9 * spike));
    let core = band_m(sd, ew * 0.35) * (0.55 + 0.45 * spike + 0.4 * late);
    acc = over(paint_rgb(red * (2.2 + 0.8 * late), rim * 0.95, 0.0), acc);
    acc = over(paint_rgb(white * 3.0, core, 0.5), acc);
    // Sparks jumping off the rim.
    let spark = band_m(sd - ew * 1.8 * spike, ew * 0.4) * step(0.8, crk);
    acc = over(paint_rgb(white * 2.6, spark, 0.6), acc);
    return acc;
}

@fragment
fn fragment(in: VertexOutput) -> @location(0) vec4<f32> {
    let p = vec2((in.uv.x - 0.5) * z.quad.z + z.quad.x, (0.5 - in.uv.y) * z.quad.w + z.quad.y);
    AAM = max(length(fwidth(p)) * 0.75, 0.003);
    AAN = AAM / max(z.shape.x, 0.1);
    let t = globals.time - z.timing.x;
    let mode = i32(z.mode.x + 0.5);
    let flags = u32(z.mode.z + 0.5);
    let seed = z.mode.w;
    if (mode >= 20 && mode < 30) {
        return telegraph(p, mode, t, (flags & 8u) != 0u);
    }
    if (mode == 30) {
        return scar(p, z.shape.x, z.shape.y, t, z.timing.y, seed);
    }
    let radius = z.shape.x;
    // A zone snaps open in 7 frames (never fades in).
    let grow = 0.72 + 0.28 * smoothstep(0.0, 0.12, t);
    let pr = p / grow;
    let hem_only = (flags & 2u) != 0u;
    var acc = vec4(0.0);
    if (!hem_only) {
        let variant = i32(z.mode.y + 0.5);
        if (mode == 0) {
            acc = well(pr, radius, t, seed, 3.0, 3.2);
        } else if (mode == 1) {
            // Generic field by element: 0 kinetic dust, 1 flame, 2 storm crackle, 3 void swirl,
            // 4 plague bubbles, 5 radiant wheel.
            if (variant == 1) {
                acc = fire(pr, radius, t, seed, 1.1);
            } else if (variant == 2) {
                acc = crackle(pr, radius, t, seed);
            } else if (variant == 3) {
                acc = well(pr, radius, t, seed, 4.0, 1.4);
            } else if (variant == 4) {
                acc = puddle(pr, radius, t, seed, false);
            } else if (variant == 5) {
                acc = wheel(pr, radius, t, seed);
            } else {
                acc = dust(pr, radius, t, seed);
            }
        } else if (mode == 2) {
            acc = puddle(pr, radius, t, seed, true);
        } else if (mode == 3) {
            if (variant == 1) {
                acc = fire(pr, radius, t, seed, 1.6);
            } else {
                acc = puddle(pr, radius, t, seed, false);
            }
        } else if (mode == 4 || mode == 5 || mode == 12 || mode == 13) {
            if (variant == 1 || mode >= 12) {
                acc = fire(pr, radius, t, seed, select(1.2, 0.7, mode == 12));
            } else if (variant == 2) {
                acc = crackle(pr, radius, t, seed);
            } else {
                acc = puddle(pr, radius, t, seed, false);
            }
        } else if (mode == 6) {
            acc = storm_eye(pr, radius, t, seed, true);
        } else if (mode == 7) {
            acc = petals(pr, radius, t, z.timing.y, seed);
        } else if (mode == 8) {
            acc = storm_eye(pr, radius, t, seed, false);
        } else if (mode == 9) {
            acc = hexes(pr, radius, t, seed);
        } else if (mode == 10) {
            acc = still(pr, radius, t, seed);
        } else if (mode == 11) {
            acc = taunt(pr, radius, t, seed);
        }
        acc = acc * z.timing.z;
    }
    if ((flags & 4u) == 0u) {
        let enemy = (flags & 1u) == 0u;
        acc = over(hem(pr, radius, t, seed, enemy), acc);
    }
    return acc;
}
