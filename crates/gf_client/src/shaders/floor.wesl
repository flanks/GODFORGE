// GODFORGE hand-painted floor (rooms, and every 32 u chunk of a biome map).
//
// Painted procedurally in world space (no tiling repeats) from the biome palette, in layers:
//
// * plazas: concentric cut pavers around a gold mosaic star (inlay variant 0, a room's heart) or
//   around a centre stone (variant 5, a map POI clearing), closed by a bold curb ring;
// * laid paving areas (`Decor::Paving`): flagstones, herringbone, tesserae or broken paving;
// * irregular flagstones of mixed size elsewhere that thin out into bare ground (stones drop out
//   one by one at the edge of the paving, so it reads as old and broken, not as a pattern);
// * roads (biome maps): fully paved, polished, with scattered stones along their shoulders; worn
//   paths (rooms) from the spawn to the exits;
// * per-stone value, temperature and tilt (the tilt goes through the real lights, so brazier
//   pools and the key light pick out stone faces), painted bevels, cracks and shattered stones;
// * soot toward the room walls, moss (Verdant), glinting veins (Spire, Unmaking);
// * overlay inlays: rune rings, clockfaces, god sigils, chaos glyphs;
// * fissures ("lava cracks") as jagged glowing rifts with scorched lips and a heat halo;
// * holes where channels and pools sink below the floor;
// * the region tint of a biome map, carried on vertex colours.
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
    /// rgb inlay metal; a = unused
    gold: vec4<f32>,
    /// rgb cool temperature tint; a = temperature variation amount
    cool: vec4<f32>,
    /// xy = arena half extents (world x, z), z = slab size, w = fissure heat (1 molten … 0 cold)
    shape: vec4<f32>,
    /// x = paint seed, y = moss amount, z = vein sparkle, w = path count
    style: vec4<f32>,
    /// x = fissure segment count, yz = key light direction (world xz, toward the light), w = footing count
    misc: vec4<f32>,
    /// x = inlay count, y = paving count, z = hole count, w = 1 on biome maps
    counts: vec4<f32>,
    /// paths: segments (ax, az, bx, bz) in world xz
    paths: array<vec4<f32>, 8>,
    /// path widths, four per vec4 (0 = a narrow worn path)
    paths_w: array<vec4<f32>, 2>,
    /// fissures: segments (ax, az, bx, bz) in world xz
    cracks: array<vec4<f32>, 48>,
    /// fissure widths, four per vec4 (segment i → cracks_w[i / 4][i % 4])
    cracks_w: array<vec4<f32>, 12>,
    /// inlays: (x, z, radius, rotation)
    inlays: array<vec4<f32>, 12>,
    /// inlay colour (rgb) and variant (a)
    inlays_c: array<vec4<f32>, 12>,
    /// paving areas: (min x, min z, max x, max z)
    paving: array<vec4<f32>, 12>,
    /// paving variants, four per vec4
    paving_v: array<vec4<f32>, 3>,
    /// holes: (min x, min z, max x, max z)
    holes: array<vec4<f32>, 8>,
    /// footings of solid pieces: (centre x, centre z, half x, half z); half z < 0 = a circle of radius half x
    footings: array<vec4<f32>, 32>,
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

fn lane4(v: vec4<f32>, lane: i32) -> f32 {
    var out = v.x;
    if lane == 1 {
        out = v.y;
    } else if lane == 2 {
        out = v.z;
    } else if lane == 3 {
        out = v.w;
    }
    return out;
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

/// Rectangular stones in a local frame: `q` in stone units, `size` the stone size.
fn rect_stone(q: vec2<f32>, size: vec2<f32>, seed: vec2<f32>) -> Stone {
    var st: Stone;
    let c = floor(q / size);
    let f = q / size - c;
    st.edge = min(min(f.x, 1.0 - f.x) * size.x, min(f.y, 1.0 - f.y) * size.y);
    st.id = vec2(hash21(c + seed), hash21(c + seed + vec2(7.7, 3.1)));
    st.offset = (f - 0.5) * size;
    st.present = 1.0;
    return st;
}

@fragment
fn fragment(in: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var pbr_input = pbr_input_from_standard_material(in, is_front);
    let w = vec2(in.world_position.x, in.world_position.z);

    // ── holes: channels and pools sink below the floor ──
    let n_holes = i32(fp.counts.z);
    for (var i = 0; i < 8; i++) {
        if i < n_holes {
            let h = fp.holes[i];
            if w.x > h.x && w.x < h.z && w.y > h.y && w.y < h.w {
                discard;
            }
        }
    }

    let t = globals.time;
    let seed = vec2(fp.style.x * 0.137, fp.style.x * 0.071);
    let half = fp.shape.xy;
    let light_xz = fp.misc.yz;
    let map_mode = fp.counts.w > 0.5;
    // Biome maps: the region's ground recipe rides on the first UV set (interpolated, so region
    // borders blend): x = paving coverage offset, y = ash drifts.
    var recipe = vec2(0.0);
    @if(VERTEX_UVS_A) {
        if map_mode {
            recipe = in.uv;
        }
    }

    // ── large-scale fields ──
    let macro_v = fbm(w * 0.04 + seed);                        // slow value drift
    let temp = fbm(w * 0.028 + seed * 1.7 + vec2(7.0, 3.0));   // colour temperature drift
    let to_edge = min(half.x - abs(w.x), half.y - abs(w.y));
    let wobble = (fbm2(w * 0.35 + seed) - 0.5) * 2.5;

    // Worn paths (rooms) and roads (maps).
    var path_d = 99.0;
    var road = 0.0;
    var shoulder = 0.0;
    let n_paths = i32(fp.style.w);
    for (var i = 0; i < 8; i++) {
        if i < n_paths {
            let s = fp.paths[i];
            let pw = lane4(fp.paths_w[i / 4], i % 4);
            let d = seg_dist(w, s.xy, s.zw);
            if pw > 0.0 {
                let hw = pw * 0.5;
                // Map roads: a hand-laid edge that wanders (not a ruler line), paving thinning out
                // over the shoulder.
                let edge = select(d + wobble * 0.35, d + wobble * 1.05, map_mode);
                let fade = select(0.5, 1.6, map_mode);
                road = max(road, 1.0 - smoothstep(hw - 0.9, hw + fade, edge));
                shoulder = max(shoulder, 1.0 - smoothstep(hw, hw + 3.0, edge));
                path_d = min(path_d, max(d - hw + 1.5, 0.0));
            } else {
                path_d = min(path_d, d);
            }
        }
    }
    let worn = max(1.0 - smoothstep(0.5, 3.0, path_d + wobble * 0.6), road * 0.6);

    // Fissures: nearest segment, measured with a jagged wobble so the rift edges break up.
    var rift = 99.0;
    var rift_len = 0.0;
    let n_cracks = i32(fp.misc.x);
    let jag = (noise2(w * 2.3 + seed) - 0.5) * 0.5 + (noise2(w * 6.1) - 0.5) * 0.18;
    for (var i = 0; i < 48; i++) {
        if i < n_cracks {
            let s = fp.cracks[i];
            let cw = lane4(fp.cracks_w[i / 4], i % 4);
            let d = seg_dist(w, s.xy, s.zw) / max(cw, 0.05);
            if d < rift {
                rift = d;
                rift_len = dot(w - s.xy, normalize(s.zw - s.xy + vec2(1.0e-4)));
            }
        }
    }
    rift += jag * 1.6;

    // ── plaza: the variant 0 / 5 inlay covering this point ──
    let n_inlays = i32(fp.counts.x);
    var plaza_c = vec2(0.0);
    var plaza_r = 0.0;
    var plaza_pat = 0;
    var mosaic = false;
    let curb_w = 0.75;
    for (var i = 0; i < 12; i++) {
        if i < n_inlays && plaza_r <= 0.0 {
            let a = fp.inlays[i];
            let v = i32(fp.inlays_c[i].w + 0.5);
            if (v == 0 || v == 5) && length(w - a.xy) < a.z + curb_w {
                plaza_c = a.xy;
                plaza_r = a.z;
                mosaic = v == 0;
                // A clearing's paver pattern (its kind): 0 courses, 1 arena, 2 vault, 3 broken.
                plaza_pat = select(0, i32(a.w + 0.5), v == 5);
            }
        }
    }
    // Distance past the rim of the nearest clearing (biome maps: POI clearings are lit pools).
    var clearing_d = 99.0;
    for (var i = 0; i < 12; i++) {
        if i < n_inlays {
            let a = fp.inlays[i];
            if i32(fp.inlays_c[i].w + 0.5) == 5 {
                clearing_d = min(clearing_d, length(w - a.xy) - a.z);
            }
        }
    }
    let rp = w - plaza_c;
    let r = length(rp);
    let ang = atan2(rp.y, rp.x);
    let ring_r = select(0.0, plaza_r * 0.45, mosaic);
    let inner_r = select(0.7, ring_r * 1.04, mosaic);

    // ── paving area covering this point ──
    let n_paving = i32(fp.counts.y);
    var pave = -1;
    var pave_lo = vec2(0.0);
    for (var i = 0; i < 12; i++) {
        if i < n_paving && pave < 0 {
            let p = fp.paving[i];
            if w.x > p.x && w.x < p.z && w.y > p.y && w.y < p.w {
                pave = i32(lane4(fp.paving_v[i / 4], i % 4) + 0.5);
                pave_lo = p.xy;
            }
        }
    }

    // ── layout: mosaic disc, plaza pavers, curb, paving, flagstones ──
    var st: Stone;
    var region = 0; // 0 flagstones, 1 plaza pavers, 2 curb, 3 mosaic disc, 4 laid paving
    if plaza_r > 0.0 && mosaic && r < ring_r * 1.04 {
        region = 3;
        st.edge = 1.0;
        st.id = vec2(0.37, 0.61);
        st.offset = vec2(0.0);
        st.present = 1.0;
    } else if plaza_r > 0.0 && r < inner_r {
        // The centre stone of a clearing.
        region = 1;
        st.edge = inner_r - r;
        st.id = vec2(0.52, 0.48);
        st.offset = rp;
        st.present = 1.0;
    } else if plaza_r > 0.0 && r < plaza_r && plaza_pat == 2 {
        region = 1;
        // A vault floor: square flags laid on the diagonal.
        let dq = vec2(rp.x + rp.y, rp.y - rp.x) * 0.70710678;
        st = rect_stone(dq + vec2(40.0), vec2(1.15, 1.15), seed + plaza_c * 0.01);
    } else if plaza_r > 0.0 && r < plaza_r {
        region = 1;
        // Concentric courses of cut pavers; an arena lays wide courses with aligned radial joints
        // (a sundial of spokes), a lair's pavers are torn up.
        let arena = plaza_pat == 1;
        let course_w = select(1.2, 1.9, arena);
        let rr = (r - inner_r) / course_w;
        let k = floor(rr);
        let r_mid = inner_r + (k + 0.5) * course_w;
        let count = select(max(8.0, floor(TAU * r_mid / (fp.shape.z * 1.1))), 16.0 * max(1.0, floor(r_mid / 5.0)), arena);
        let aa = ang / TAU * count + select(hash21(vec2(k, 3.0)) * count, 0.0, arena);
        let j = floor(aa);
        let fr = fract(rr);
        let fa = fract(aa);
        let arc = TAU * r_mid / count;
        st.edge = min(min(fr, 1.0 - fr) * course_w, min(fa, 1.0 - fa) * arc);
        st.id = vec2(hash21(vec2(k, j) + seed + plaza_c), hash21(vec2(j, k) + seed + vec2(9.1, 2.3)));
        if arena && k - 2.0 * floor(k * 0.5) > 0.5 {
            st.id.x *= 0.45;
        }
        let radial = rp / max(r, 1.0e-3);
        let tangent = vec2(-radial.y, radial.x);
        st.offset = radial * (fr - 0.5) * course_w + tangent * (fa - 0.5) * arc;
        // A few pavers have lifted out near the outer courses (most of them in a lair).
        st.present = 1.0 - step(select(0.93, 0.55, plaza_pat == 3), st.id.x) * step(1.0, k);
    } else if plaza_r > 0.0 && r < plaza_r + curb_w {
        region = 2;
        let count = floor(TAU * (plaza_r + curb_w * 0.5) / 2.4);
        let aa = ang / TAU * count;
        let fa = fract(aa);
        let fr = (r - plaza_r) / curb_w;
        let arc = TAU * (plaza_r + curb_w * 0.5) / count;
        st.edge = min(min(fr, 1.0 - fr) * curb_w, min(fa, 1.0 - fa) * arc);
        st.id = vec2(hash21(vec2(floor(aa), 7.0) + seed + plaza_c), 0.5);
        let radial = rp / max(r, 1.0e-3);
        st.offset = radial * (fr - 0.5) * curb_w;
        st.present = 1.0;
    } else if pave >= 0 {
        region = 4;
        let q = w - pave_lo;
        if pave == 1 {
            // Herringbone / basket weave: pairs of bricks turning every cell.
            let cell = floor(q / 1.0);
            let odd = (cell.x + cell.y) - 2.0 * floor((cell.x + cell.y) * 0.5);
            let local = select(q, q.yx, odd > 0.5);
            st = rect_stone(local, vec2(0.5, 1.0), seed + cell * 0.1);
        } else if pave == 2 {
            // Tesserae: small tiles laid in wavering running courses (opus tessellatum).
            let row = floor(q.y / 0.34);
            let shift = hash21(vec2(row, 11.0) + seed) * 0.34;
            let wav = (noise2(vec2(q.x * 0.35, row * 0.5) + seed) - 0.5) * 0.12;
            st = rect_stone(q + vec2(shift + wav, 0.0), vec2(0.37, 0.34), seed + vec2(row * 0.013, 0.0));
        } else {
            // Flagstones (0) or broken paving (3): running bond of large slabs.
            let row = floor(q.y / 0.9);
            let shift = hash21(vec2(row, 5.0) + seed) * 1.3;
            st = rect_stone(q + vec2(shift, 0.0), vec2(1.3, 0.9), seed + vec2(row * 0.01, 0.0));
            if pave == 3 {
                st.present = step(0.2, st.id.y);
            }
        }
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
        // Paving thins out into bare ground: whole stones drop out near the paving's edge. Roads
        // are fully paved, their shoulders scattered.
        let centre = w - st.offset;
        let edge_c = min(half.x - abs(centre.x), half.y - abs(centre.y));
        let rim_drop = select((1.0 - smoothstep(-1.0, 7.0, edge_c)) * 0.25, 0.0, map_mode);
        let cover = fbm(centre * 0.055 + seed * 2.3) + (fp.dirt.a + recipe.x - 0.5) * 0.6 + worn * 0.12 + road * 0.9
            + shoulder * 0.22 - rim_drop;
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
    } else if region == 4 {
        stone *= 1.05;
        if pave == 2 {
            // Tesserae mix in the accent and gold.
            stone = mix(stone, fp.gold.rgb * 0.75, step(0.93, st.id.y) * 0.6);
            stone = mix(stone, fp.accent.rgb * 0.3, step(0.97, st.id.x) * 0.5);
        }
    }

    // Worn paths and roads: lighter, smoother, dustier stone.
    // Worn paths (rooms) polish lighter; map roads read by their laid texture and a warmer hue,
    // not by brightness (the characters own the top of the value range).
    let polish = select(fp.stone.rgb * 1.16 + vec3(0.006), fp.stone.rgb * vec3(1.08, 1.0, 0.86), map_mode);
    let polished = polish * (0.94 + 0.12 * strokes);
    stone = mix(stone, polished, worn * select(0.55, 0.45, map_mode));

    // Painted bevel: the lip facing the key light catches it, the far lip falls into shadow.
    let off_n = st.offset / max(length(st.offset), 1.0e-3);
    let gap_w = mix(0.018, 0.032, 1.0 - worn) * select(1.0, 1.1, region == 0) * select(1.0, 0.7, pave == 2)
        * select(1.0, 0.75, map_mode);
    let lip = 1.0 - smoothstep(gap_w, gap_w + 0.17, st.edge);
    let facing = dot(off_n, light_xz);
    stone *= 1.0 + lip * (0.4 * max(facing, 0.0) - 0.28 * max(-facing, 0.0));

    // Cracks across some stones, and a few shattered ones.
    let crack_n = normalize(hash22(st.id * 31.0) - 0.5 + vec2(1.0e-3));
    let crack_line = abs(dot(st.offset, crack_n) + (noise2(w * 3.0) - 0.5) * 0.25);
    let cracked = step(0.74, st.id.y) * select(0.0, 1.0, region <= 1 || region == 4);
    let crack = cracked * (1.0 - smoothstep(0.012, 0.035, crack_line)) * smoothstep(0.02, 0.12, st.edge);
    let shattered = step(st.id.x, 0.06) * select(0.0, 1.0, region == 0 || pave == 3);
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
    // Layered earth: big patches of pale ash and dark scorched ground, brushy mid-tones, faint
    // networks of cracked earth in some patches, a sparse scatter of stones and a fine grit.
    let dirt_n = fbm(w * 1.3 + seed * 3.0);
    let terr = fbm(w * 0.055 + seed * 0.3 + vec2(11.0, 4.0));
    let mid_n = fbm2(w * 0.4 + seed);
    var ground = fp.dirt.rgb * (0.72 + 0.5 * dirt_n) * (0.86 + 0.28 * mid_n);
    let ash = max(smoothstep(0.52, 0.72, terr), recipe.y * smoothstep(0.2, 0.55, terr));
    ground = mix(ground, vec3(luma(ground)) * 1.55 + fp.cool.rgb * 0.02, ash * 0.55);
    // Ash country (Cinder Dunes): wind ripples drawn across the drifts.
    let ripple_p = w.x * 0.8 + w.y * 1.9 + (fbm2(w * 0.18 + seed) - 0.5) * 6.0;
    let ripples = smoothstep(0.55, 0.95, sin(ripple_p * 2.2) * 0.5 + 0.5) * recipe.y * ash;
    ground = mix(ground, ground * 0.72, ripples * 0.6);
    let scorch = smoothstep(0.42, 0.24, terr);
    ground = mix(ground, ground * vec3(0.62, 0.52, 0.5), scorch * 0.6);
    // Brush drags across the ground (a painter's texture, not noise).
    let drag = fbm(vec2(w.x * 0.9 + w.y * 0.35, w.y * 2.6 - w.x * 0.2) + seed * 1.3);
    ground *= 0.9 + 0.2 * drag;
    let ce = voronoi(w * 0.75 + seed * 1.7);
    // Cracked earth only where the ground is scorched (maps), so it reads as a burn, not a tiling.
    let crack_mask = smoothstep(0.5, 0.66, fbm(w * 0.11 + seed * 2.0 + vec2(3.0, 9.0))) * select(1.0, scorch, map_mode);
    let earth_cracks = (1.0 - smoothstep(0.015, 0.06, ce.d2 - ce.d1)) * crack_mask;
    ground = mix(ground, fp.mortar.rgb * 0.45, earth_cracks * 0.75);
    let pebble = voronoi(w * 1.25 + seed);
    let pick = hash21(pebble.id);
    let pebble_r = 0.1 + 0.2 * hash21(pebble.id + 5.0);
    // Stones gather in drifts (under walls, around rubble, along the shoulders) instead of an even
    // polka-dot scatter.
    let drift = smoothstep(0.5, 0.72, fbm(w * 0.12 + seed * 1.1 + vec2(2.0, 7.0)) + shoulder * 0.25);
    let is_pebble = step(0.84, pick) * select(1.0, drift, map_mode);
    let pebbles = (1.0 - smoothstep(pebble_r - 0.04, pebble_r, pebble.d1)) * is_pebble;
    let pebble_rim = (1.0 - smoothstep(pebble_r, pebble_r + 0.06, pebble.d1)) * is_pebble;
    ground = mix(ground, fp.mortar.rgb * 0.35, pebble_rim * select(0.8, 0.4, map_mode));
    let pebble_lit = 0.75 + 0.5 * max(dot(normalize(-pebble.r + vec2(1.0e-4)), light_xz), 0.0);
    ground = mix(ground, fp.stone.rgb * (0.55 + 0.4 * hash21(pebble.id + 1.0)) * pebble_lit, pebbles);
    let grit = hash21(floor(w * 14.0) + seed);
    ground *= 0.94 + 0.12 * grit;
    // Dirt sits lower: darker right against the stone lips.
    ground *= 0.6 + 0.4 * smoothstep(0.0, 0.6, st.edge + 0.15);

    var color = stone * mix(0.72, 1.0, ao);
    color = mix(color, fp.mortar.rgb * select(0.3, 0.55, map_mode), max(gap, max(crack, shard_gap * 0.9)));
    color = mix(ground, color, st.present);

    // ── gold mosaic at a plaza's heart ──
    var gold_mask = 0.0;
    var glow = vec3(0.0);
    if mosaic && r < ring_r * 1.1 {
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
        color = mix(color, fp.gold.rgb * (0.75 + 0.45 * strokes), gold_mask);
    }

    // ── overlay inlays: rune rings, clockfaces, god sigils, chaos glyphs ──
    for (var i = 0; i < 12; i++) {
        if i < n_inlays {
            let a = fp.inlays[i];
            let ci = fp.inlays_c[i];
            let v = i32(ci.w + 0.5);
            let d = w - a.xy;
            let R = max(a.z, 0.3);
            let ri = length(d);
            if v >= 1 && v <= 4 && ri < R * 1.12 {
                let an = atan2(d.y, d.x) - a.w;
                let line = 0.045 + R * 0.006;
                var ink = 0.0;
                var metal = 0.0;
                var fill = 0.0;
                var shine = 0.0;
                let rim = 1.0 - smoothstep(line * 0.6, line * 1.6, abs(ri - R));
                let rim2 = 1.0 - smoothstep(line * 0.5, line * 1.3, abs(ri - R * 0.8));
                if v == 1 {
                    // Rune ring: two gold rings, glyph ticks between them, a faint glow.
                    let seg = fract(an / TAU * 18.0 + 0.5);
                    let band = step(R * 0.83, ri) * step(ri, R * 0.97);
                    let glyph = band * (step(abs(seg - 0.5), 0.06) + step(abs(seg - 0.28), 0.03) * step(ri, R * 0.9)
                        + step(abs(seg - 0.72), 0.03) * step(R * 0.9, ri));
                    metal = max(rim, rim2);
                    shine = clamp(glyph, 0.0, 1.0);
                    ink = (1.0 - smoothstep(0.0, line, abs(abs(ri - R) - line * 2.0))) * 0.7;
                } else if v == 2 {
                    // Clockface / orrery: ring, twelve hours, an inner ring and two hands.
                    let seg = fract(an / TAU * 12.0 + 0.5);
                    let long_tick = step(abs(seg - 0.5), 0.02) * step(R * 0.72, ri) * step(ri, R * 0.97);
                    let inner = 1.0 - smoothstep(line * 0.5, line * 1.3, abs(ri - R * 0.35));
                    let dir1 = vec2(cos(a.w), sin(a.w));
                    let dir2 = vec2(cos(a.w + 2.1), sin(a.w + 2.1));
                    let hand1 = (1.0 - smoothstep(line * 0.6, line * 1.4, seg_dist(d, vec2(0.0), dir1 * R * 0.8)));
                    let hand2 = (1.0 - smoothstep(line * 0.6, line * 1.4, seg_dist(d, vec2(0.0), dir2 * R * 0.55)));
                    metal = clamp(rim + rim2 * 0.6 + long_tick + inner + hand1 + hand2, 0.0, 1.0);
                    shine = long_tick * 0.4;
                } else if v == 3 {
                    // God sigil: a dark disc, a star of rays in the god's colour, a gold rim.
                    fill = 1.0 - smoothstep(R * 0.96, R, ri);
                    let rays = pow(abs(cos(an * 4.0)), 8.0) * (1.0 - smoothstep(R * 0.2, R * 0.85, ri))
                        + (1.0 - smoothstep(R * 0.18, R * 0.24, ri));
                    shine = clamp(rays, 0.0, 1.0);
                    metal = rim;
                } else {
                    // Chaos glyph: a burning spiral.
                    let spiral = fract(an / TAU * 2.0 + ri / R * 1.6 + t * 0.05);
                    let arm = (1.0 - smoothstep(0.0, 0.08, abs(spiral - 0.5))) * step(ri, R * 0.95) * step(R * 0.1, ri);
                    shine = arm;
                    metal = rim * 0.6;
                }
                color = mix(color, fp.mortar.rgb * 0.25, clamp(fill * 0.75 + ink, 0.0, 1.0));
                color = mix(color, fp.gold.rgb * (0.75 + 0.45 * strokes), metal * 0.9);
                gold_mask = max(gold_mask, metal * 0.9);
                let hue = select(fp.accent.rgb, ci.rgb, v == 3);
                color = mix(color, hue * 0.8, clamp(shine, 0.0, 1.0) * 0.8);
                glow += hue * shine * (0.35 + 0.25 * sin(t * 1.4 + f32(i)));
            }
        }
    }

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

    // Soot and grime pooling toward the room walls (and under them).
    if !map_mode {
        let soot = (1.0 - smoothstep(-1.5, 9.0, to_edge + wobble)) * fp.mortar.a;
        color = mix(color, fp.mortar.rgb * (0.55 + 0.45 * dirt_n), clamp(soot, 0.0, 0.88));
    }
    let grime = smoothstep(0.55, 0.8, fbm(w * 0.2 + seed + vec2(5.0, 1.0))) * (1.0 - worn);
    color = mix(color, fp.mortar.rgb, grime * 0.4);
    // Biome maps: the ways (roads and clearings) are lit pools; the country between them falls
    // off into dusk, so paths read at a glance and the frame gets its darks.
    if map_mode {
        let near_way = max(1.0 - smoothstep(1.5, 13.0, path_d), 1.0 - smoothstep(1.0, 10.0, clearing_d));
        color *= mix(0.84, 1.0, near_way);
    }
    // Soot and contact shade under the solid pieces (they sit in the ground, not on it).
    let n_foot = i32(fp.misc.w);
    var foot = 0.0;
    for (var i = 0; i < 32; i++) {
        if i < n_foot {
            let f = fp.footings[i];
            var d = 0.0;
            if f.w < 0.0 {
                d = length(w - f.xy) - f.z;
            } else {
                d = length(max(abs(w - f.xy) - f.zw, vec2(0.0)));
            }
            foot = max(foot, 1.0 - smoothstep(-0.2, 1.5 + (fbm2(w * 0.9) - 0.5) * 0.8, d));
        }
    }
    color = mix(color, color * 0.45, foot * 0.8);

    // Region tint (biome maps): a hue lean carried on vertex colours; alpha is the distance inland,
    // so the ground darkens toward cliffs. The second UV set carries the liquid heat: the bank of
    // a molten river glows instead of darkening.
    var bank_heat = 0.0;
    @if(VERTEX_UVS_B) {
        bank_heat = in.uv_b.x;
    }
    @if(VERTEX_COLORS) {
        let shade = max(mix(0.5, 1.0, smoothstep(0.0, 0.85, in.color.a)), bank_heat);
        color = color * in.color.rgb * shade;
    }

    // ── fissures ──
    let heat = fp.shape.w;
    let core = 1.0 - smoothstep(0.12, 0.38, rift);
    let lips = 1.0 - smoothstep(0.3, 1.3, rift);
    let halo = 1.0 - smoothstep(0.8, select(4.5, 2.6, map_mode), rift);
    let flow = 0.65 + 0.35 * sin(t * 1.3 - rift_len * 1.7 + noise2(w * 0.7) * 5.0);
    // Scorched, broken lips; the stone around a rift is darker and cracked.
    color = mix(color, fp.mortar.rgb * 0.22, clamp(lips * 0.85 + core, 0.0, 1.0) * (1.0 - gold_mask));
    glow += fp.accent.rgb * fp.accent.a * core * flow * (0.35 + 0.65 * heat);
    // The white-hot centre of the rift.
    glow += vec3(1.0, 0.85, 0.55) * fp.accent.a * 0.5 * heat * (1.0 - smoothstep(0.0, 0.14, rift)) * flow;
    // Heat halo: warms the stone around it (lit by the rift).
    color += fp.accent.rgb * (0.02 + select(0.13, 0.07, map_mode) * heat) * halo * (1.0 - core);
    // Hot banks: the stone beside a molten river is lit from below by it.
    glow += fp.accent.rgb * bank_heat * bank_heat * 0.1 * heat * (0.8 + 0.2 * sin(t * 1.1 + w.x * 0.3));

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
    toon = max(vec3(l) + (toon - vec3(l)) * (1.0 + 0.25 * darkness), vec3(0.0));
    toon = mix(toon, toon * fp.cool.rgb * 2.0, 0.12 * darkness);
    let final_color = mix(lit.rgb, toon, 0.7) + glow;

    var out: FragmentOutput;
    out.color = main_pass_post_lighting_processing(pbr_input, vec4(final_color, 1.0));
    return out;
}
