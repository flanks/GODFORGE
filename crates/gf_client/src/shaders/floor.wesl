// GODFORGE hand-painted arena floor.
//
// Painted procedurally in world space (no tiling repeats) from the biome palette, in layers:
//
// * a paved plaza of concentric cut pavers around a gold mosaic at the arena heart, closed by a
//   bold curb ring;
// * irregular flagstones of mixed size beyond it that thin out into bare ground (stones drop out
//   one by one at the edge of the paving, so it reads as old and broken, not as a pattern);
// * per-stone value, temperature and tilt (the tilt goes through the real lights, so brazier
//   pools and the key light pick out stone faces), painted bevels that catch the key light,
//   cracks and a few shattered stones, all separated by dark ink-like gaps;
// * worn paths from the spawn to the exits (lighter, smoother, dusty), soot and grime pooling
//   toward the walls, moss (Verdant) and glinting veins (Spire, Unmaking);
// * the room's fissures (procgen "lava cracks") as jagged glowing rifts with scorched lips and a
//   heat halo, tinted by the biome accent;
// * large, slow value and temperature shifts across the whole arena.
//
// The result still goes through Bevy's lighting (shadows, light pools) and is posterized like
// the toon material so the whole frame reads as one painting.

import bevy_pbr::render::{
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
    forward_io::{VertexOutput, FragmentOutput},
    mesh_view_bindings::globals,
};

struct FloorParams {
    /// rgb slab colour (linear); a = slab value contrast
    stone: vec4<f32>,
    /// rgb bare ground colour; a = paving coverage (0 mostly dirt … 1 fully paved)
    dirt: vec4<f32>,
    /// rgb gap / soot colour; a = soot strength toward the walls
    mortar: vec4<f32>,
    /// rgb fissure glow colour (linear, HDR); a = glow strength
    accent: vec4<f32>,
    /// rgb inlay metal; a = mosaic ring radius (0 = none)
    gold: vec4<f32>,
    /// rgb cool temperature tint; a = temperature variation amount
    cool: vec4<f32>,
    /// xy = arena half extents (world x, z), z = slab size, w = fissure heat (1 molten … 0 cold)
    shape: vec4<f32>,
    /// x = paint seed, y = moss amount, z = vein sparkle, w = worn path count
    style: vec4<f32>,
    /// x = fissure segment count, yz = key light direction (world xz, toward the light), w = unused
    misc: vec4<f32>,
    /// worn paths: segments (ax, az, bx, bz) in world xz
    paths: array<vec4<f32>, 6>,
    /// fissures: segments (ax, az, bx, bz) in world xz
    cracks: array<vec4<f32>, 48>,
    /// fissure widths, four per vec4 (segment i → cracks_w[i / 4][i % 4])
    cracks_w: array<vec4<f32>, 12>,
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

fn fbm2(p: vec2<f32>) -> f32 {
    return 0.65 * noise2(p) + 0.35 * noise2(p * 2.07 + vec2(4.1, 1.3));
}

struct Cell {
    /// distance to the nearest feature point / second / third nearest (cell units)
    d1: f32,
    d2: f32,
    d3: f32,
    /// lattice ids of the nearest and second nearest cells
    id: vec2<f32>,
    id2: vec2<f32>,
    /// offset from the nearest feature point to the sample (cell units)
    r: vec2<f32>,
}

fn voronoi(p: vec2<f32>) -> Cell {
    let i = floor(p);
    let f = fract(p);
    var d1 = 8.0;
    var d2 = 8.0;
    var d3 = 8.0;
    var id = vec2(0.0);
    var id2 = vec2(0.0);
    var r1 = vec2(0.0);
    for (var y = -1; y <= 1; y++) {
        for (var x = -1; x <= 1; x++) {
            let g = vec2(f32(x), f32(y));
            let o = hash22(i + g) * 0.72 + 0.14;
            let r = g + o - f;
            let d = dot(r, r);
            if d < d1 {
                d3 = d2;
                d2 = d1;
                id2 = id;
                d1 = d;
                id = i + g;
                r1 = r;
            } else if d < d2 {
                d3 = d2;
                d2 = d;
                id2 = i + g;
            } else if d < d3 {
                d3 = d;
            }
        }
    }
    return Cell(sqrt(d1), sqrt(d2), sqrt(d3), id, id2, -r1);
}

/// Lattice cells pair up (along x, staggered per row); some pairs are laid as one big stone.
fn stone_group(c: vec2<f32>) -> vec2<f32> {
    let stagger = c.y - 2.0 * floor(c.y * 0.5);
    return vec2(floor((c.x + stagger) * 0.5), c.y);
}

fn is_big(g: vec2<f32>) -> bool {
    return hash21(g * 1.37 + vec2(3.3, 8.1)) < 0.35;
}

fn luma(c: vec3<f32>) -> f32 {
    return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

fn seg_dist(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let ab = b - a;
    let t = clamp(dot(p - a, ab) / max(dot(ab, ab), 1.0e-4), 0.0, 1.0);
    return length(p - (a + ab * t));
}

/// One paved stone as the painter sees it.
struct Stone {
    /// distance to the stone's border (world units)
    edge: f32,
    /// per-stone random values
    id: vec2<f32>,
    /// offset from the stone centre (world units), for bevel direction
    offset: vec2<f32>,
    /// 1 = present, 0 = missing (bare ground shows)
    present: f32,
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let w = vec2(in.world_position.x, in.world_position.z);
    let t = globals.time;
    let seed = vec2(fp.style.x * 0.137, fp.style.x * 0.071);
    let half = fp.shape.xy;
    let light_xz = fp.misc.yz;

    // ── large-scale fields ──
    let macro_v = fbm(w * 0.04 + seed);                        // slow value drift across the arena
    let temp = fbm(w * 0.028 + seed * 1.7 + vec2(7.0, 3.0));   // colour temperature drift
    let to_edge = min(half.x - abs(w.x), half.y - abs(w.y));
    let wobble = (fbm2(w * 0.35 + seed) - 0.5) * 2.5;

    // Worn paths (spawn → exits, anvil).
    var path_d = 99.0;
    let n_paths = i32(fp.style.w);
    for (var i = 0; i < 6; i++) {
        if i < n_paths {
            let s = fp.paths[i];
            path_d = min(path_d, seg_dist(w, s.xy, s.zw));
        }
    }
    let worn = 1.0 - smoothstep(0.5, 3.0, path_d + wobble * 0.6);

    // Fissures: nearest segment, measured with a jagged wobble so the rift edges break up.
    var rift = 99.0;
    var rift_w = 0.3;
    var rift_len = 0.0;
    let n_cracks = i32(fp.misc.x);
    let jag = (noise2(w * 2.3 + seed) - 0.5) * 0.5 + (noise2(w * 6.1) - 0.5) * 0.18;
    for (var i = 0; i < 48; i++) {
        if i < n_cracks {
            let s = fp.cracks[i];
            let wv = fp.cracks_w[i / 4];
            let lane = i % 4;
            var cw = wv.x;
            if lane == 1 {
                cw = wv.y;
            } else if lane == 2 {
                cw = wv.z;
            } else if lane == 3 {
                cw = wv.w;
            }
            let d = seg_dist(w, s.xy, s.zw) / max(cw, 0.05);
            if d < rift {
                rift = d;
                rift_w = cw;
                rift_len = dot(w - s.xy, normalize(s.zw - s.xy + vec2(1.0e-4)));
            }
        }
    }
    rift += jag * 1.6;

    // ── layout: mosaic disc, plaza pavers, curb, flagstones ──
    let ring_r = fp.gold.a;
    let r = length(w);
    let ang = atan2(w.y, w.x);
    let plaza_r = select(0.0, ring_r * 2.25, ring_r > 0.0);
    let curb_w = 0.75;

    var st: Stone;
    var region = 0; // 0 flagstones, 1 plaza pavers, 2 curb, 3 mosaic disc
    if ring_r > 0.0 && r < ring_r * 1.04 {
        region = 3;
        st.edge = 1.0;
        st.id = vec2(0.37, 0.61);
        st.offset = vec2(0.0);
        st.present = 1.0;
    } else if ring_r > 0.0 && r < plaza_r {
        region = 1;
        // Concentric courses of cut pavers.
        let course_w = 1.2;
        let rr = (r - ring_r * 1.04) / course_w;
        let k = floor(rr);
        let r_mid = ring_r * 1.04 + (k + 0.5) * course_w;
        let count = max(8.0, floor(TAU * r_mid / (fp.shape.z * 1.1)));
        let aa = ang / TAU * count + hash21(vec2(k, 3.0)) * count;
        let j = floor(aa);
        let fr = fract(rr);
        let fa = fract(aa);
        let arc = TAU * r_mid / count;
        st.edge = min(min(fr, 1.0 - fr) * course_w, min(fa, 1.0 - fa) * arc);
        st.id = vec2(hash21(vec2(k, j) + seed), hash21(vec2(j, k) + seed + vec2(9.1, 2.3)));
        let radial = w / max(r, 1.0e-3);
        let tangent = vec2(-radial.y, radial.x);
        st.offset = radial * (fr - 0.5) * course_w + tangent * (fa - 0.5) * arc;
        // A few pavers have lifted out near the outer courses.
        st.present = 1.0 - step(0.93, st.id.x) * step(1.0, k);
    } else if ring_r > 0.0 && r < plaza_r + curb_w {
        region = 2;
        let count = floor(TAU * (plaza_r + curb_w * 0.5) / 2.4);
        let aa = ang / TAU * count;
        let fa = fract(aa);
        let fr = (r - plaza_r) / curb_w;
        let arc = TAU * (plaza_r + curb_w * 0.5) / count;
        st.edge = min(min(fr, 1.0 - fr) * curb_w, min(fa, 1.0 - fa) * arc);
        st.id = vec2(hash21(vec2(floor(aa), 7.0) + seed), 0.5);
        let radial = w / max(r, 1.0e-3);
        st.offset = radial * (fr - 0.5) * curb_w;
        st.present = 1.0;
    } else {
        // Irregular flagstones with a hand-drawn wobble on the grid. Some neighbours are laid as
        // one big stone (their shared joint disappears), so sizes vary without a pattern.
        let slab = max(fp.shape.z, 0.3);
        let warp = vec2(noise2(w * 0.8 + seed), noise2(w * 0.8 + seed + vec2(5.2, 1.3))) - 0.5;
        let c = voronoi((w + warp * 0.3) / slab);
        let g1 = stone_group(c.id);
        let big = is_big(g1);
        let cid = select(c.id, g1 + vec2(0.5, 0.25), big);
        var edge_u = c.d2 - c.d1;
        if big && all(g1 == stone_group(c.id2)) {
            edge_u = c.d3 - c.d1;
        }
        st.edge = edge_u * 0.5 * slab;
        st.id = vec2(hash21(cid + seed), hash21(cid + seed + vec2(17.3, 3.1)));
        st.offset = c.r * slab;
        // Paving thins out into bare ground: whole stones drop out near the paving's edge.
        let centre = w - st.offset;
        let edge_c = min(half.x - abs(centre.x), half.y - abs(centre.y));
        let cover = fbm(centre * 0.055 + seed * 2.3) + (fp.dirt.a - 0.5) * 0.6 + worn * 0.12
            - (1.0 - smoothstep(-1.0, 7.0, edge_c)) * 0.25;
        st.present = step(0.45, cover + (st.id.x - 0.5) * 0.2);
    }

    // ── paint the stone ──
    let strokes = fbm(vec2(w.x * 0.7 + w.y * 0.3, w.y * 1.6) * 1.1 + st.id * 13.0);
    let grain = noise2(w * 9.0 + seed);
    let contrast = fp.stone.a;
    var stone = fp.stone.rgb * (1.0 + contrast * (st.id.x - 0.5) * 2.0) * (0.84 + 0.3 * strokes) * (0.95 + 0.1 * grain);
    // Per-stone temperature: some lean warm (sun-baked), some cool (shadow-stained).
    stone = mix(stone, stone * vec3(1.14, 1.0, 0.82), smoothstep(0.6, 0.92, st.id.y) * 0.8);
    stone = mix(stone, stone * fp.cool.rgb * 1.8, smoothstep(0.4, 0.08, st.id.y) * 0.5);
    if region == 1 {
        stone *= 1.08;
    } else if region == 2 {
        stone = stone * 1.25 + vec3(0.015);
    } else if region == 3 {
        stone = fp.stone.rgb * 0.5 * (0.85 + 0.3 * strokes);
    }

    // Worn paths: lighter, smoother, dustier stone.
    let polished = fp.stone.rgb * 1.3 * (0.94 + 0.12 * strokes) + vec3(0.01);
    stone = mix(stone, polished, worn * 0.55);

    // Painted bevel: the lip facing the key light catches it, the far lip falls into shadow.
    let off_n = st.offset / max(length(st.offset), 1.0e-3);
    let gap_w = mix(0.02, 0.038, 1.0 - worn) * select(1.0, 1.25, region == 0);
    let lip = 1.0 - smoothstep(gap_w, gap_w + 0.17, st.edge);
    let facing = dot(off_n, light_xz);
    stone *= 1.0 + lip * (0.45 * max(facing, 0.0) - 0.4 * max(-facing, 0.0));

    // Cracks across some stones, and a few shattered ones.
    let crack_n = normalize(hash22(st.id * 31.0) - 0.5 + vec2(1.0e-3));
    let crack_line = abs(dot(st.offset, crack_n) + (noise2(w * 3.0) - 0.5) * 0.25);
    let cracked = step(0.74, st.id.y) * select(0.0, 1.0, region <= 1);
    let crack = cracked * (1.0 - smoothstep(0.012, 0.035, crack_line)) * smoothstep(0.02, 0.12, st.edge);
    let shattered = step(st.id.x, 0.06) * select(0.0, 1.0, region == 0);
    var shard_gap = 0.0;
    if shattered > 0.5 {
        let sc = voronoi(w * 2.8 + seed);
        shard_gap = 1.0 - smoothstep(0.02, 0.06, sc.d2 - sc.d1);
        stone *= 0.72 + 0.32 * hash21(sc.id);
    }

    // Gaps: dark, ink-like.
    let gap = 1.0 - smoothstep(gap_w, gap_w + 0.03, st.edge);
    // Soft occlusion bleeding into the stone next to the gap.
    let ao = smoothstep(gap_w, gap_w + 0.3, st.edge);

    // ── bare ground where stones are missing ──
    let dirt_n = fbm(w * 1.3 + seed * 3.0);
    let pebble = voronoi(w * 1.9 + seed);
    let pebble_r = 0.16 + 0.14 * hash21(pebble.id + 5.0);
    let pebbles = (1.0 - smoothstep(pebble_r - 0.05, pebble_r, pebble.d1)) * step(0.7, hash21(pebble.id));
    let pebble_rim = (1.0 - smoothstep(pebble_r, pebble_r + 0.07, pebble.d1)) * step(0.7, hash21(pebble.id));
    var ground = fp.dirt.rgb * (0.6 + 0.7 * dirt_n) * (0.85 + 0.3 * fbm2(w * 0.4 + seed));
    ground = mix(ground, fp.mortar.rgb * 0.4, pebble_rim * 0.8);
    let pebble_lit = 0.8 + 0.4 * max(dot(normalize(-pebble.r + vec2(1.0e-4)), light_xz), 0.0);
    ground = mix(ground, fp.stone.rgb * (0.55 + 0.4 * hash21(pebble.id + 1.0)) * pebble_lit, pebbles);
    // Dirt sits lower: darker right against the stone lips.
    ground *= 0.6 + 0.4 * smoothstep(0.0, 0.6, st.edge + 0.15);

    var color = stone * mix(0.6, 1.0, ao);
    color = mix(color, fp.mortar.rgb * 0.3, max(gap, max(crack, shard_gap * 0.9)));
    color = mix(ground, color, st.present);

    // ── gold mosaic at the arena heart ──
    var gold_mask = 0.0;
    if ring_r > 0.0 && r < ring_r * 1.1 {
        let outer = 1.0 - smoothstep(0.06, 0.12, abs(r - ring_r));
        let inner = 1.0 - smoothstep(0.03, 0.08, abs(r - ring_r * 0.8));
        let seg = fract(ang / TAU * 32.0);
        let band = step(ring_r * 0.83, r) * step(r, ring_r * 0.97);
        let tesserae = band * smoothstep(0.1, 0.22, seg) * (1.0 - smoothstep(0.78, 0.9, seg));
        // Eight-pointed star rosette.
        let star_r = ring_r * (0.3 + 0.14 * pow(abs(cos(ang * 4.0)), 3.0));
        let star = (1.0 - smoothstep(star_r - 0.08, star_r, r)) * step(ring_r * 0.13, r);
        let star_edge = 1.0 - smoothstep(0.03, 0.08, abs(r - star_r));
        let hub = 1.0 - smoothstep(0.03, 0.08, abs(r - ring_r * 0.13));
        gold_mask = clamp(outer + inner + tesserae * 0.6 + star * 0.55 + hub, 0.0, 1.0);
        gold_mask *= 0.72 + 0.28 * strokes;
        // Ink keylines around the gold.
        let key = (1.0 - smoothstep(0.0, 0.05, abs(abs(r - ring_r) - 0.13)))
            + (1.0 - smoothstep(0.0, 0.04, abs(abs(r - ring_r * 0.8) - 0.09))) + star_edge * 0.8;
        color = mix(color, fp.mortar.rgb * 0.3, clamp(key, 0.0, 1.0) * 0.85);
    }
    color = mix(color, fp.gold.rgb * (0.75 + 0.45 * strokes), gold_mask);

    // ── moss in the gaps and on the ground (Verdant) ──
    let moss_field = smoothstep(0.42, 0.72, fbm(w * 0.16 + seed * 0.7 + vec2(3.0, 8.0)));
    let moss = fp.style.y * moss_field * clamp(gap * 1.3 + (1.0 - st.present) * 0.9 + (1.0 - ao) * 0.4 + lip * 0.2, 0.0, 1.0);
    let moss_col = mix(fp.dirt.rgb * vec3(0.7, 1.6, 0.9), vec3(0.06, 0.16, 0.08), 0.35) * (0.7 + 0.6 * grain);
    color = mix(color, moss_col, clamp(moss, 0.0, 1.0) * (1.0 - gold_mask));

    // ── large-scale value and temperature ──
    color *= 0.62 + 0.76 * macro_v;
    let cool_amt = fp.cool.a * smoothstep(0.62, 0.32, temp);
    color = mix(color, color * fp.cool.rgb * 1.9, cool_amt);
    color = mix(color, color * vec3(1.12, 1.0, 0.84), fp.cool.a * smoothstep(0.55, 0.8, temp) * 0.8);

    // Soot and grime pooling toward the walls (and under them).
    let soot = (1.0 - smoothstep(-1.5, 9.0, to_edge + wobble)) * fp.mortar.a;
    color = mix(color, fp.mortar.rgb * (0.55 + 0.45 * dirt_n), clamp(soot, 0.0, 0.88));
    let grime = smoothstep(0.55, 0.8, fbm(w * 0.2 + seed + vec2(5.0, 1.0))) * (1.0 - worn);
    color = mix(color, fp.mortar.rgb, grime * 0.4);

    // ── fissures ──
    let heat = fp.shape.w;
    let core = 1.0 - smoothstep(0.12, 0.38, rift);
    let lips = 1.0 - smoothstep(0.3, 1.3, rift);
    let halo = 1.0 - smoothstep(0.8, 4.5, rift);
    let flow = 0.65 + 0.35 * sin(t * 1.3 - rift_len * 1.7 + noise2(w * 0.7) * 5.0);
    // Scorched, broken lips; the stone around a rift is darker and cracked.
    color = mix(color, fp.mortar.rgb * 0.22, clamp(lips * 0.85 + core, 0.0, 1.0) * (1.0 - gold_mask));
    var glow = fp.accent.rgb * fp.accent.a * core * flow * (0.35 + 0.65 * heat);
    // The white-hot centre of the rift.
    glow += vec3(1.0, 0.85, 0.55) * fp.accent.a * 0.5 * heat * (1.0 - smoothstep(0.0, 0.14, rift)) * flow;
    // Heat halo: warms the stone around it (lit by the rift).
    color += fp.accent.rgb * (0.02 + 0.13 * heat) * halo * (1.0 - core);

    // ── veins (Spire starlit marble, Unmaking seams) ──
    let vein_f = fbm(w * 0.45 + seed * 1.9);
    let vein = (1.0 - smoothstep(0.0, 0.009, abs(vein_f - 0.52))) * fp.style.z * st.present * (1.0 - gap);
    let cellp = floor(w * 9.0);
    let sparkle = step(0.988, hash21(cellp + seed)) * fp.style.z * st.present
        * (0.5 + 0.5 * sin(t * 2.0 + hash21(cellp) * 30.0));
    glow += fp.accent.rgb * (vein * 0.5 + sparkle * 0.8);

    // ── lighting: per-stone tilt and bevel go through the real lights ──
    let tilt = (hash22(st.id * 7.3) - 0.5) * 0.24 * st.present;
    let slope = tilt + off_n * lip * st.present * (1.0 - gap) * 0.7;
    pbr_input.N = normalize(vec3(slope.x, 1.0, slope.y));

    pbr_input.material.base_color = vec4(color, 1.0);
    pbr_input.material.emissive = vec4(0.0, 0.0, 0.0, 1.0);
    pbr_input.material.perceptual_roughness = mix(0.92, 0.45, gold_mask);
    pbr_input.material.metallic = gold_mask * 0.65;

    let lit = apply_pbr_lighting(pbr_input);

    // Painted bands: posterize the received light so pools and shadows land as flat shapes.
    let received = max(luma(lit.rgb) / max(luma(color), 0.002), 1.0e-4);
    let ev = log2(received);
    let tb = ev;
    let stepped = floor(tb) + smoothstep(0.3, 0.7, fract(tb));
    var toon = lit.rgb * exp2(stepped - ev);
    // Cool, saturated shadow bands.
    let darkness = clamp(-stepped * 0.3, 0.0, 1.0);
    let l = luma(toon);
    toon = max(vec3(l) + (toon - vec3(l)) * (1.0 + 0.5 * darkness), vec3(0.0));
    toon = mix(toon, toon * fp.cool.rgb * 2.0, 0.45 * darkness);
    let final_color = mix(lit.rgb, toon, 0.7) + glow;

    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(pbr_input, vec4(final_color, 1.0));
    return out;
}
