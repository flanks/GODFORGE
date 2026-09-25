"""Procedural hand-painted NPR textures for Valdris (numpy; driven by s2_texture.py through its "painter" hook).

Same contract as s2_paint.py (Brax): per-texel maps baked from the production mesh into its UV atlas (world
position, world normal, paint zone, object index, the gf_mask outline mask and per-piece random, the parts' self-AO,
the blockout's cavity / AO / hit weight) in, an sRGB base-colour and an sRGB emissive atlas out. Reuses s2_paint's
noise, Voronoi and dilate helpers. One extra map is baked here, inside the texture step's Blender session
(bake_extra: Cycles, the atlas' own UVs): an EDGE map from the Bevel node (1 - N_bevel . N within edge_bake.radius
of a hard edge) and Cycles pointiness (convex > 0.5), so every plate gets chipped, lighter edges and darker inner
corners wherever its geometry has them (prism side walls such as the pauldron and anvil tops carry no outline mask).

Painting rules (art/characters/valdris/brief.md sections 4-6, palette.json, the sheet's declared colour script, and
the stage-2 polish review: "dark cracked slab-armour glowing from within"):
  * the declared hexes are the base colours (Gunmetal #2A242E, Forge Gold #FFC24B, Ember Amber #FF6B1A, Deep War
    Red #7A1F1F, white-hot #FFF5CE); the measured tones shade them. Painted value planes, no light direction: the
    toon shader lights him;
  * PLATE = cracked stone-like gunmetal: a mosaic of stone blocks (a 2D Voronoi in an L_p metric, laid in the plane
    of each texel's dominant normal axis; blocks a little wider than tall), every block its own value around the
    #2A242E family, every plate its own value (the per-piece random), faces that look up (what the 55-degree camera
    sees) lifted toward the lit stone tone, undersides sunk; each block has a lit upper bevel and a dark lower one,
    the joints are dark cavities, a few thin cracks cross the blocks; the plates' hard edges (the edge bake) are
    chipped and lighter, inner corners darker;
  * the LAVA SEAMS run through the joints: long meandering veins (iso-bands of a warped low-frequency noise) light up
    the block joints they cross, emissive with a white-hot core, white-hot dots where a vein passes a block corner;
    denser in the glow regions (the anvil flanks, the chest, the knees, the shins, round the pauldron slots, the
    forearms), sparse elsewhere; a soft burnt halo in the base colour around them;
  * zone LAVA (the anvil gasket, the elbow rings, the knee smiles, the shin gaskets): small dark crust plates over
    glowing magma, emissive, white-hot where the gaps meet; zone SEAM (the pauldron slots, the buckle core) glows
    solid; the under-suit glows dimly at the joints;
  * the ANVIL is the same stone one value step lighter, with bigger blocks, light crack lips and the lightest face on
    him on its flat top (the light bar across his chest from 55 degrees), a bright worn front edge, a hardy hole and a
    pritchel hole near the heel, a few glowing veins on its flanks;
  * gold is forge gold only on the trims and rivets: painted metal, a highlight band on up-facing trim, a dark
    underside, worn dark chips on its edges;
  * the cape is Deep War Red with vertical fold streaks, a darker charred hem and the forge sigil on its back (a
    vertical blade with three pairs of up-swept branches and a three-point crown, the turnaround's back view), in
    emblem gold;
  * skin: warm weathered planes, heavy painted brows, deep eye sockets, the cracked scar across the scalp and
    forehead with a faint ember glow (Reforged Flesh); beard: iron-grey value planes with downward streaks, lighter
    lock tips and braid lobes; the braid caps are light steel;
  * brush variation is low-frequency value noise, never grunge; AO (the parts' own and the blockout's) and the
    blockout's cavity are folded in as darker painted planes.
"""
import json
import os

import numpy as np

from s2_paint import _hash, anisotropic, dilate, fbm, hex3, mix, smoothstep, value_noise, voronoi  # noqa: F401


def bake_extra(maps, cfg, log=print):
    """Bake the edge map (R: Bevel-node edge strength, G: Cycles pointiness, B: coverage) with the texture step's own
    scene, UVs and zone materials, and add maps["edge"], maps["point"] (valid texels, the same order as the other
    maps); with edge_bake.joint_ao_distance also maps["jao"], a short-range ambient occlusion (the plate joints).
    Needs bpy (inside s2_texture.py); a no-op when cfg has no edge_bake or the maps already carry the edge."""
    ec = cfg.get("edge_bake")
    if not ec or "edge" in maps:
        return maps
    import bpy
    scene = bpy.context.scene
    objs = [o for o in scene.objects if o.type == "MESH" and o.pass_index > 0 and not o.hide_render]
    size = bpy.data.images["gf_bake"].size[0] if "gf_bake" in bpy.data.images else 2048
    img = bpy.data.images.new("gf_edge", size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    cmbs = []
    for m in {s.material for o in objs for s in o.material_slots if s.material is not None}:
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        bev = nt.nodes.new("ShaderNodeBevel")
        bev.samples = ec.get("bevel_samples", 8)
        bev.inputs["Radius"].default_value = ec["radius"]
        dp = nt.nodes.new("ShaderNodeVectorMath")
        dp.operation = "DOT_PRODUCT"
        nt.links.new(bev.outputs["Normal"], dp.inputs[0])
        nt.links.new(geo.outputs["Normal"], dp.inputs[1])
        inv = nt.nodes.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        nt.links.new(dp.outputs["Value"], inv.inputs[1])
        cmb = nt.nodes.new("ShaderNodeCombineXYZ")
        nt.links.new(inv.outputs[0], cmb.inputs[0])
        nt.links.new(geo.outputs["Pointiness"], cmb.inputs[1])
        cmb.inputs[2].default_value = 1.0
        nt.links.new(cmb.outputs[0], em.inputs["Color"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
        cmbs.append((nt, cmb, tex))
    samples0 = scene.cycles.samples
    scene.cycles.samples = ec.get("samples", 16)
    for o in scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]

    def bake_px():
        bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
        px_ = np.empty(size * size * 4, dtype=np.float32)
        img.pixels.foreach_get(px_)
        return px_.reshape(size, size, 4)
    px = bake_px()
    jao = None
    if ec.get("joint_ao_distance"):
        # second pass: ambient occlusion within a few cm (any object): high only where another plate closes over the
        # surface, i.e. in the joints where one plate meets another (the painter's lava joints, s2_valdris_paint)
        for nt, cmb, tex in cmbs:
            ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
            ao.samples = ec.get("joint_ao_samples", 8)
            ao.only_local = False
            ao.inputs["Distance"].default_value = ec["joint_ao_distance"]
            nt.links.new(ao.outputs["AO"], cmb.inputs[0])
            for lk in list(nt.links):
                if lk.to_node == cmb and lk.to_socket == cmb.inputs[1]:
                    nt.links.remove(lk)
            cmb.inputs[1].default_value = 0.0
        jao = bake_px()[..., 0]
    scene.cycles.samples = samples0
    bpy.data.images.remove(img)
    valid = px[..., 2] > 0.5
    n = len(maps["pos"])
    if int(valid.sum()) != n:
        log("edge bake: coverage %d != %d texels, edge map skipped" % (int(valid.sum()), n))
        return maps
    if jao is not None:
        maps["jao"] = np.clip(jao[valid], 0, 1).astype(np.float32)
    maps["edge"] = np.clip(px[..., 0][valid], 0, 1).astype(np.float32)
    maps["point"] = px[..., 1][valid].astype(np.float32)
    log("edge bake: %d texels near a hard edge" % int((maps["edge"] > 0.1).sum()))
    cache = os.environ.get("GF_VALDRIS_PAINT_CACHE")
    if cache:
        # iteration aid (off by default): keep every per-texel map, the atlas' valid mask and the paint inputs, so
        # s2_valdris_repaint.py can repaint the atlas in ~1 min without the UV / bake steps
        np.savez_compressed(cache, _valid=valid, **{k: v for k, v in maps.items() if isinstance(v, np.ndarray)})
        log("paint cache written", cache)
    return maps


def tiles(P, Nn, freq, seed, pnorm=2.6, jitter=0.8, aspect=1.0, warp=None):
    """Stone-block mosaic on the surface: a 2D Voronoi (L_p metric, so the blocks are blocky) in the plane of each
    texel's dominant normal axis (triplanar without blending; the switch reads as a block joint), blocks `aspect`
    times wider than tall. Returns the distance to the nearest joint (m), a per-block hash (0..1), the distance to the
    nearest block corner (m), where the texel sits in its block along the plane's up axis (-0.5 .. 0.5) and the
    world position of its block's seed (so a whole block can be picked by a field evaluated at the seed)."""
    ax = np.argmax(np.abs(Nn), axis=1)
    U = np.where(ax == 0, P[:, 1], P[:, 0]).astype(np.float64)
    V = np.where(ax == 2, -P[:, 1], P[:, 2]).astype(np.float64)
    if warp is not None:
        U = U + warp[:, 0]
        V = V + warp[:, 1]
    qu, qv = U * freq / aspect, V * freq
    iu, iv = np.floor(qu), np.floor(qv)
    axi = ax.astype(np.float64)
    f1 = np.full(len(P), 9.0)
    f2 = np.full(len(P), 9.0)
    f3 = np.full(len(P), 9.0)
    cid = np.zeros(len(P), dtype=np.float32)
    rel = np.zeros(len(P))
    relu = np.zeros(len(P))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx, cy = iu + dx, iv + dy
            fx = cx + 0.5 + (_hash(cx, cy, axi, seed) - 0.5) * jitter
            fy = cy + 0.5 + (_hash(cx, cy, axi, seed + 1) - 0.5) * jitter
            ddu, ddv = qu - fx, qv - fy
            d = (np.abs(ddu) ** pnorm + np.abs(ddv) ** pnorm) ** (1.0 / pnorm)
            c1 = d < f1
            c2 = (d < f2) & ~c1
            c3 = (d < f3) & ~c1 & ~c2
            f3 = np.where(c1 | c2, f2, np.where(c3, d, f3))
            f2 = np.where(c1, f1, np.where(c2, d, f2))
            f1 = np.where(c1, d, f1)
            cid = np.where(c1, _hash(cx, cy, axi, seed + 2), cid)
            rel = np.where(c1, ddv, rel)
            relu = np.where(c1, ddu, relu)
    edge = ((f2 - f1) / (2.0 * freq)).astype(np.float32)
    vtx = ((f3 - f1) / (2.0 * freq)).astype(np.float32)
    ou, ov = relu * aspect / freq, rel / freq                     # texel - seed, metres along the plane axes
    seed_p = np.array(P, dtype=np.float64)
    seed_p[:, 0] -= np.where(ax == 0, 0.0, ou)
    seed_p[:, 1] -= np.where(ax == 0, ou, np.where(ax == 2, -ov, 0.0))
    seed_p[:, 2] -= np.where(ax == 2, 0.0, ov)
    return edge, cid, vtx, np.clip(rel, -0.5, 0.5).astype(np.float32), seed_p.astype(np.float32)


def paint(maps, zones, pal, cfg, log=print):
    maps = bake_extra(maps, cfg, log)
    cache = os.environ.get("GF_VALDRIS_PAINT_CACHE")
    if cache:
        with open(os.path.splitext(cache)[0] + ".json", "w", encoding="utf-8", newline="\n") as f:
            json.dump({"zones": zones, "pal": pal, "cfg": cfg}, f, indent=1)
    P, Nn, Z = maps["pos"], maps["nrm"], maps["zone"]
    N = len(P)
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    T = {k: {t: hex3(h) for t, h in v.items()} for k, v in pal.items()}
    D = {k: hex3(v) for k, v in cfg["declared"].items()}
    ST = {k: hex3(v) for k, v in cfg["stone"].items() if not k.startswith("_")}
    mk_all = maps["mask"] if "mask" in maps else np.full(N, 0.6, dtype=np.float32)
    pr_all = maps["prand"] if "prand" in maps else np.full(N, 0.5, dtype=np.float32)
    edge_all = maps["edge"] if "edge" in maps else np.zeros(N, dtype=np.float32)
    point_all = maps["point"] if "point" in maps else np.full(N, 0.5, dtype=np.float32)
    # Cycles pointiness is relative to each mesh: measure convexity against the median of the hard-surface texels
    _hz = np.isin(Z, [zones[n] for n in ("plate", "anvil", "gold") if n in zones])
    pmed = float(np.median(point_all[_hz])) if _hz.any() else 0.5
    ao_all = maps["ao_self"] if "ao_self" in maps else np.ones(N, dtype=np.float32)
    brush = (fbm(P, 5.0, 3, seed=1) - 0.5) * 2
    fine = (fbm(P, 36.0, 2, seed=2) - 0.5) * 2
    ember_rim, ember_hot, ember_core = T["ember_seams"]["rim"], D["ember"], D["white_hot"]
    glow_core = np.zeros(N, dtype=np.float32)       # bright seam line strength (0..1)
    glow_hot = np.zeros(N, dtype=np.float32)        # its white-hot centre
    glow_halo = np.zeros(N, dtype=np.float32)       # the soft band around it (feeds bloom)

    def zm(*names):
        return np.isin(Z, [zones[n] for n in names if n in zones])

    def region_w(p, regs):
        """Sum of soft boxes {x|abs_x, y, z, w} over the texels p."""
        w = np.zeros(len(p), dtype=np.float32)
        for r in regs:
            k = np.ones(len(p), dtype=np.float32)
            for ax, key in ((0, "x"), (1, "y"), (2, "z")):
                if key in r:
                    k *= smoothstep(r[key][0] - 0.03, r[key][0] + 0.01, p[:, ax]) * (1 - smoothstep(r[key][1] - 0.01, r[key][1] + 0.03, p[:, ax]))
            if "abs_x" in r:
                ax_ = np.abs(p[:, 0])
                k *= smoothstep(r["abs_x"][0] - 0.03, r["abs_x"][0] + 0.01, ax_) * (1 - smoothstep(r["abs_x"][1] - 0.01, r["abs_x"][1] + 0.03, ax_))
            w = np.maximum(w, k * r["w"])
        return w

    # ---- the stone mosaic, the cracks and the lava veins shared by the plates and the anvil -------------------
    tc, vc = cfg["tiles"], cfg["veins"]
    hard = zm("plate", "anvil", "iron", "lava")
    ph, nh = P[hard], Nn[hard]
    warp = (np.stack([fbm(ph, tc["warp_freq"], 2, seed=301), fbm(ph, tc["warp_freq"], 2, seed=302)], 1) - 0.5) * tc["warp"]
    is_anvil = (Z[hard] == zones["anvil"])
    is_lava = (Z[hard] == zones["lava"])
    freq_h = np.where(is_anvil, tc["freq_anvil"], np.where(is_lava, tc["freq_lava"], tc["freq"]))
    E, CID, VTX, UP = (np.zeros(N, dtype=np.float32) for _ in range(4))
    SEED = np.zeros((N, 3), dtype=np.float32)
    for fq in np.unique(freq_h):
        s = freq_h == fq
        idx = np.nonzero(hard)[0][s]
        e, c, v, u, sp = tiles(ph[s], nh[s], fq, 311, tc["pnorm"], tc["jitter"], tc["aspect"], warp[s])
        E[idx], CID[idx], VTX[idx], UP[idx], SEED[idx] = e, c, v, u, sp
    # thin cracks across the blocks (big warped 3D Voronoi cells)
    _, cedge, _ = voronoi(ph + np.concatenate([warp, warp[:, :1]], 1) * 2.0, tc["crack_freq"], seed=341)
    CR = np.full(N, 9.0, dtype=np.float32)
    CR[hard] = cedge / (2 * tc["crack_freq"])
    # veins: iso-bands of a low-frequency noise evaluated at each block's SEED, so the blocks a vein passes light up
    # all round their joints (lava in the mortar along a meandering chain of blocks); broken into runs
    reg = region_w(P, cfg["glow_regions"])
    sh = SEED[hard]
    reg_s = region_w(sh, cfg["glow_regions"])
    band = np.zeros(N, dtype=np.float32)
    for k, sd in enumerate(vc["seeds"]):
        f = fbm(sh, vc["freq"], 3, seed=sd)
        w = vc["width"] + vc["region_boost"] * reg_s
        band[hard] = np.maximum(band[hard], smoothstep(w, w * 0.6, np.abs(f - 0.5)))
    run = np.zeros(N, dtype=np.float32)
    run[hard] = smoothstep(vc["run"][0], vc["run"][1], fbm(sh, vc["run_freq"], 2, seed=361) + reg_s * vc["run_region"])
    vein = band * run * (vc["base"] + (1 - vc["base"]) * np.clip(reg, 0, 1))
    vein = vein * (1 - smoothstep(vc["up_off"][0], vc["up_off"][1], Nn[:, 2]))       # no lava on the up-facing tops
    joint_glow = smoothstep(vc["line"], vc["line"] * 0.3, E) * vein
    corner_hot = smoothstep(vc["dot"], vc["dot"] * 0.3, VTX) * smoothstep(vc["dot"] * 1.2, 0.0, E) * vein

    def add_glow(m, strength, hot, halo):
        glow_core[m] = np.maximum(glow_core[m], strength)
        glow_hot[m] = np.maximum(glow_hot[m], hot)
        glow_halo[m] = np.maximum(glow_halo[m], halo)

    def junction(m):
        """Lava in the plate JOINTS: where another plate closes over the surface within a few cm (the short-range AO
        bake, maps["jao"]) a thin ember seam glows, broken into runs; so the structure lines of the armour (a lame on
        the next, the anvil on the breastplate, a plate on the under-layer) glow from within."""
        jc = cfg.get("junction")
        if not jc:
            return
        if "jao" not in maps:
            return
        # only on surfaces that are open to the view (the parts' self-AO): faces pressed flat on another plate are hidden
        oc = smoothstep(jc["jao"][0], jc["jao"][1], maps["jao"][m]) * smoothstep(jc["open"][0], jc["open"][1], ao_all[m])
        runs = smoothstep(jc["run"][0], jc["run"][1], fbm(P[m], jc["run_freq"], 2, seed=431))
        j = oc * runs * jc["strength"]
        add_glow(m, j, j * smoothstep(0.6, 0.95, runs) * 0.5, j * 0.8)

    # ---- PLATE (cracked stone-like gunmetal) ---------------------------------------------------------------
    def stone(m, base_col, light_col, edge_col, lift_top, block_var, tones):
        p, n = P[m], Nn[m]
        e, cid, up = E[m], CID[m], UP[m]
        pr = pr_all[m]
        upf = smoothstep(0.45, 0.85, n[:, 2])                  # up-facing planes stay calm: the game camera reads them
        bv = block_var * (1 - tc["top_calm"] * upf)
        c = np.repeat(base_col[None], m.sum(), 0)
        pv = tc.get("plate_var", 0.1)
        c = c * (1 - bv + 2 * bv * cid)[:, None] * (1 - pv + 2 * pv * pr)[:, None]                 # every block, every plate
        # painted value planes: faces toward the viewer a step lighter than the side planes (no light direction)
        fp = tc.get("front_plane", 0.0)
        c = c * (1 + fp * smoothstep(0.3, 0.9, -n[:, 1]) - fp * 0.8 * smoothstep(0.5, 0.95, np.abs(n[:, 0])))[:, None]
        c = mix(c, light_col * (0.92 + 0.16 * cid)[:, None], smoothstep(0.2, 0.85, n[:, 2]) * lift_top)   # up-facing planes
        c = mix(c, tones["shadow"] * 0.8, smoothstep(-0.15, -0.8, n[:, 2]) * 0.6)                          # undersides
        c = c * (1 + 0.06 * brush[m][:, None])
        # block bevels: the upper rim of each block catches light, the lower rim falls into shadow
        near = smoothstep(tc["bevel"], tc["bevel"] * 0.35, e)
        chip = smoothstep(0.35, 0.6, fbm(p, 60.0, 2, seed=371))
        calm = 1 - tc["top_calm"] * upf
        c = mix(c, edge_col, near * smoothstep(0.05, 0.3, up) * tc["bevel_light"] * (0.5 + 0.5 * chip) * calm)
        c = mix(c, ST["cavity"] * 1.4, near * smoothstep(-0.05, -0.3, up) * tc["bevel_dark"] * calm)
        # the joints and the cracks: dark cavities with a light lip
        c = mix(c, ST["cavity"], smoothstep(tc["gap"], tc["gap"] * 0.35, e) * tc["gap_dark"] * (1 - 0.4 * tc["top_calm"] * upf))
        cr = CR[m]
        c = mix(c, edge_col * 0.9, smoothstep(tc["crack"] * 3.0, tc["crack"] * 1.4, cr) * smoothstep(tc["crack"] * 1.2, tc["crack"] * 1.4, cr) * 0.3)
        c = mix(c, ST["cavity"], smoothstep(tc["crack"], tc["crack"] * 0.3, cr) * 0.75)
        # the plate's hard edges: chipped and lighter where convex, darker in the inner corners
        ed = smoothstep(0.03, 0.2, edge_all[m])
        convex = smoothstep(pmed + 0.005, pmed + 0.05, point_all[m])
        chips = smoothstep(0.3, 0.55, fbm(p, 48.0, 2, seed=381))
        c = mix(c, edge_col * 1.08, ed * convex * (0.3 + 0.55 * chips) * tc["edge_light"])
        c = mix(c, ST["cavity"], ed * (1 - convex) * 0.5)
        if "cav" in maps:
            c = mix(c, ST["cavity"], smoothstep(0.62, 0.9, maps["cav"][m]) * 0.4)
        return c

    m = zm("plate")
    if m.any():
        # the declared Gunmetal, pulled a little toward the measured (warmer) plate tone so the violet cast of the label
        # does not turn the whole mass lavender under the cool shadow band
        gm = mix(D["gunmetal"][None], T["gunmetal_plate"]["base"][None], cfg.get("gunmetal_warm", 0.0))[0]
        base[m] = stone(m, gm, ST["light"], ST["edge"], cfg["plate_lift_top"], tc["block_var"], T["gunmetal_plate"])
        g = joint_glow[m] * smoothstep(0.05, 0.2, 1 - smoothstep(0.03, 0.2, edge_all[m]))       # no glow on the chipped edges
        add_glow(m, g, np.maximum(corner_hot[m], g * 0.25), smoothstep(vc["line"] * 3.5, vc["line"], E[m]) * vein[m] * 0.6)
        junction(m)
    # ---- ANVIL (the same stone one value step lighter; its flat top the lightest face on him) -------------------
    m = zm("anvil")
    if m.any():
        p, n = P[m], Nn[m]
        ac = cfg["anvil"]
        c = stone(m, ST["anvil"], ST["anvil_light"], ST["anvil_edge"], 0.0, tc["block_var"] * 0.8, T["anvil_iron"])
        top = smoothstep(0.7, 0.92, n[:, 2])
        c = mix(c, ST["anvil_top"] * (0.93 + 0.14 * CID[m] + 0.05 * brush[m])[:, None], top * ac["top_lift"])
        c = mix(c, ST["anvil_edge"], top * smoothstep(tc["gap"] * 2.5, tc["gap"], E[m]) * 0.35)
        # the top face's worn front edge and the chamfers round it
        front_edge = smoothstep(0.03, 0.2, edge_all[m]) * smoothstep(0.1, 0.5, n[:, 2] + 0.3 * smoothstep(-0.2, -0.8, n[:, 1]))
        c = mix(c, ST["anvil_edge"] * 1.1, front_edge * 0.55)
        hh = ac["hardy"]
        dh = np.maximum(np.abs(p[:, 0] - hh[0]), np.abs(p[:, 1] - hh[1]))
        c = mix(c, ST["cavity"], top * smoothstep(hh[2] + 0.004, hh[2], dh))
        pp = ac["pritchel"]
        dp = np.hypot(p[:, 0] - pp[0], p[:, 1] - pp[1])
        c = mix(c, ST["cavity"], top * smoothstep(pp[2] + 0.003, pp[2], dp))
        base[m] = c
        g = joint_glow[m] * (1 - top) * smoothstep(0.05, 0.2, 1 - smoothstep(0.03, 0.2, edge_all[m]))
        add_glow(m, g, np.maximum(corner_hot[m] * (1 - top), g * 0.25), smoothstep(vc["line"] * 3.5, vc["line"], E[m]) * vein[m] * (1 - top) * 0.6)
    # ---- IRON (inner walls, undersides, the sole) -----------------------------------------------------------
    m = zm("iron")
    if m.any():
        ir = T["gunmetal_plate"]
        c = np.repeat(ir["shadow"][None], m.sum(), 0) * (0.8 + 0.3 * CID[m][:, None])
        c = mix(c, D["gunmetal"], smoothstep(0.2, 0.8, Nn[m][:, 2]) * 0.4)
        c = mix(c, ST["cavity"], smoothstep(tc["gap"], tc["gap"] * 0.35, E[m]) * 0.5)
        base[m] = c * (1 + 0.04 * brush[m][:, None])
    # ---- LAVA (crust over magma: the anvil gasket, the elbow rings, the knee smiles, the shin gaskets) ----------
    m = zm("lava")
    if m.any():
        lv = cfg["lava"]
        e, v = E[m], VTX[m]
        crust = smoothstep(lv["gap"] * 0.6, lv["gap"] * 1.6, e) * (0.75 + 0.25 * CID[m])
        c = mix(np.repeat(hex3(lv["magma"])[None], m.sum(), 0), hex3(lv["crust"]) * (0.8 + 0.4 * CID[m])[:, None], crust)
        base[m] = c
        hot = smoothstep(lv["gap"] * 0.9, 0.0, e) * (1 - crust)
        corner = smoothstep(lv["gap"] * 2.2, lv["gap"] * 0.5, v) * (1 - crust * 0.7)
        add_glow(m, np.clip((1 - crust) * 0.95 + lv["crust_glow"], 0, 1), np.maximum(hot * 0.55, corner), np.ones(m.sum(), dtype=np.float32) * lv["halo"])
    # ---- GOLD trim and rivets ----------------------------------------------------------------------------------
    m = zm("gold")
    if m.any():
        p, n = P[m], Nn[m]
        fg = T["forge_gold"]
        gb = mix(fg["highlight"][None], D["gold"][None], cfg["gold"]["declared_share"])[0]
        c = np.repeat(gb[None], m.sum(), 0) * (1 + 0.05 * brush[m][:, None])
        c = mix(c, D["gold"] * 1.03, smoothstep(0.35, 0.8, n[:, 2]) * 0.55)              # painted highlight band on top
        c = mix(c, fg["base"], smoothstep(-0.1, -0.7, n[:, 2]) * 0.7)                   # dark underside
        c = mix(c, fg["shadow"], smoothstep(0.1, 0.0, mk_all[m]) * 0.5)
        c = mix(c, D["gold"] * 1.08, smoothstep(0.66, 0.78, fbm(p, 42.0, 2, seed=81)) * 0.3)   # worn bright streaks
        wear = smoothstep(0.62, 0.72, fbm(p, 70.0, 2, seed=83)) * smoothstep(0.03, 0.2, edge_all[m])
        c = mix(c, fg["shadow"] * 0.8, wear * 0.6)                                         # dark worn chips on the edges
        base[m] = np.clip(c, 0, 1)
    # ---- STEEL (braid caps) -------------------------------------------------------------------------------------
    m = zm("steel")
    if m.any():
        n = Nn[m]
        st = T["cannon_steel"]
        c = np.repeat(st["highlight"][None], m.sum(), 0)
        c = mix(c, st["highlight"] * 1.2, smoothstep(0.2, 0.7, n[:, 2]) * 0.6)
        c = mix(c, st["base"], smoothstep(0.0, -0.6, n[:, 2]) * 0.8)
        c = mix(c, st["shadow"], smoothstep(0.25, 0.1, mk_all[m]) * 0.6)
        base[m] = c
    # ---- SEAM (emissive faces: pauldron slots, buckle core) ----------------------------------------------------
    m = zm("seam")
    if m.any():
        t = fbm(P[m], 30.0, 2, seed=71)
        base[m] = mix(np.repeat(ember_hot[None], m.sum(), 0), ember_core, smoothstep(0.55, 0.78, t) * 0.5)
        emis[m] = mix(np.repeat(ember_hot[None], m.sum(), 0) * 0.95, ember_core, smoothstep(0.58, 0.78, t) * 0.55)   # ember, white-hot flecks
    # ---- CAPE (war red) + the forge sigil ------------------------------------------------------------------------
    m = zm("cape")
    if m.any():
        p, n = P[m], Nn[m]
        wr = T["war_red"]
        red = D["war_red"]
        st = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 60.0, 6.0, seed=111)
        c = np.repeat(red[None], m.sum(), 0) * (1 + 0.05 * brush[m][:, None])
        c = mix(c, red * 1.25, smoothstep(0.58, 0.82, st) * 0.5)                         # fold ridges
        c = mix(c, wr["base"], smoothstep(0.42, 0.2, st) * 0.6)                          # fold valleys
        cp = cfg["cape"]
        inner = (n[:, 1] < -0.2) & (p[:, 1] > 0.1)                                     # the side facing his back
        c = np.where(inner[:, None], mix(c, wr["shadow"] * 1.3, 0.55), c)
        hem = smoothstep(cp["hem_z"][1], cp["hem_z"][0], p[:, 2])
        c = mix(c, wr["shadow"], hem * 0.65 * (0.6 + 0.4 * fbm(p, 20.0, 2, seed=113)))   # charred hem
        # a few burnt specks near the hem glow faintly
        speck = smoothstep(0.8, 0.86, fbm(p, 45.0, 2, seed=117)) * hem
        # the forge sigil on the back (outer side, facing +Y)
        sg = cp["sigil"]
        outer = smoothstep(0.2, 0.5, n[:, 1]) * (p[:, 1] > 0.2)
        sd = sigil_distance(p[:, 0], p[:, 2], sg)
        em = smoothstep(sg["stroke"], sg["stroke"] * 0.55, sd) * outer
        eg = T["emblem_gold"]
        gcol = mix(np.repeat(eg["base"][None], m.sum(), 0), eg["highlight"], smoothstep(0.4, 0.8, fbm(p, 16.0, 2, seed=119)) * 0.6)
        c = mix(c, gcol, em)
        c = mix(c, eg["shadow"] * 0.8, smoothstep(sg["stroke"] * 1.45, sg["stroke"], sd) * (1 - em) * outer * 0.8)   # dark outline
        base[m] = c
        glow_halo[m] = np.maximum(glow_halo[m], speck * 0.5)
    # ---- MAIL (the under-suit) with dim ember glow at the joints ------------------------------------------------
    m = zm("mail")
    if m.any():
        p, n = P[m], Nn[m]
        ml = T["anvil_iron"]
        ring = np.abs(np.sin(p[:, 0] * 520.0) * np.sin(p[:, 2] * 520.0 + np.sin(p[:, 1] * 300.0)))
        c = np.repeat(ml["base"][None], m.sum(), 0) * (0.85 + 0.25 * ring[:, None])
        c = mix(c, ml["highlight"] * 0.7, smoothstep(0.4, 0.9, n[:, 2]) * 0.3)
        base[m] = c * (1 + 0.04 * brush[m][:, None])
        jw = region_w(p, cfg["joint_glow"])
        base[m] = mix(base[m], np.array([0.30, 0.12, 0.06], dtype=np.float32), jw * 0.6)
        glow_halo[m] = np.maximum(glow_halo[m], jw * 0.55)
    # ---- LEATHER (the glove, the belt) ------------------------------------------------------------------------------
    m = zm("leather")
    if m.any():
        p, n = P[m], Nn[m]
        lt = cfg["leather"]
        c = np.repeat(hex3(lt["base"])[None], m.sum(), 0)
        c = mix(c, hex3(lt["highlight"]), smoothstep(0.35, 0.85, n[:, 2]) * 0.5)
        c = mix(c, hex3(lt["shadow"]), smoothstep(-0.1, -0.7, n[:, 2]) * 0.6)
        base[m] = c * (1 + 0.06 * brush[m][:, None])
    # ---- SKIN (face, scalp) + the scalp scar --------------------------------------------------------------------------
    m = zm("skin")
    if m.any():
        p, n = P[m], Nn[m]
        sk = T["skin"]
        c = np.repeat(sk["base"][None], m.sum(), 0)
        c = mix(c, sk["highlight"], smoothstep(0.45, 0.9, n[:, 2]) * 0.35)             # the scalp's top plane
        c = mix(c, sk["shadow"], smoothstep(-0.05, -0.6, n[:, 2]) * 0.4)
        c = mix(c, np.array([0.62, 0.3, 0.24], dtype=np.float32), np.clip(fbm(p, 16.0, 2, seed=9) - 0.4, 0, 1) * 0.35)   # weathered red
        ez = cfg["eye_z"]
        ax = np.abs(p[:, 0])
        for sx in (1, -1):
            e = np.array([sx * cfg["eye_x"], cfg["eye_y"], ez])
            d = np.linalg.norm((p - e) * [1.0, 0.6, 1.3], axis=1)
            c = mix(c, sk["shadow"] * 0.6, smoothstep(0.036, 0.012, d) * 0.75)                # deep sockets
        brow_top = ez + 0.034 - (ax - 0.01) * 0.2
        brow = (smoothstep(ez + 0.009, ez + 0.015, p[:, 2]) * smoothstep(brow_top + 0.003, brow_top - 0.003, p[:, 2])
                * smoothstep(0.002, 0.008, ax) * smoothstep(0.07, 0.06, ax) * smoothstep(-0.15, -0.35, n[:, 1]))
        brow *= smoothstep(0.25, 0.5, fbm(p, 110.0, 1, seed=31) + 0.35)
        c = mix(c, T["beard"]["shadow"], brow * 0.95)
        # scar: jagged crack lines over the scalp and forehead (texture; faintly ember: Reforged Flesh)
        sc = cfg["scar"]
        # the scar is a polyline in (azimuth, elevation) degrees around the head centre, measured along the skin
        hc = np.array(sc["head_centre"])
        v = p - hc
        az = np.degrees(np.arctan2(v[:, 0], -v[:, 1]))
        el = np.degrees(np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1])))
        q2 = np.stack([az * np.cos(np.radians(el)), el], 1)
        scar_d = np.full(m.sum(), 999.0, dtype=np.float32)
        for (a, b) in sc["lines_deg"]:
            a = np.array([a[0] * np.cos(np.radians(a[1])), a[1]])
            b = np.array([b[0] * np.cos(np.radians(b[1])), b[1]])
            ab = b - a
            t = np.clip(((q2 - a) @ ab) / (ab @ ab), 0, 1)
            scar_d = np.minimum(scar_d, np.linalg.norm(q2 - (a + t[:, None] * ab), axis=1))
        scar_d = scar_d * np.radians(1.0) * sc["radius"] + (value_noise(p, 90.0, seed=41) - 0.5) * sc["jag"]
        near = np.linalg.norm(v, axis=1) < sc["radius"] * 1.4
        scar_d = np.where(near, np.abs(scar_d), 9.0)
        scar = smoothstep(sc["width"], sc["width"] * 0.3, scar_d)
        c = mix(c, np.array([0.33, 0.15, 0.11], dtype=np.float32), smoothstep(sc["width"] * 2.4, sc["width"], scar_d) * 0.55)
        c = mix(c, mix(np.array([[0.42, 0.13, 0.08]], dtype=np.float32), ember_rim, 0.35), scar * 0.75)
        base[m] = c * (1 + 0.03 * brush[m][:, None])
        glow_core[m] = np.maximum(glow_core[m], scar * sc["glow"])
        glow_halo[m] = np.maximum(glow_halo[m], smoothstep(sc["width"] * 2.5, sc["width"], scar_d) * sc["glow"] * 0.5)
    # ---- BEARD (block, locks, moustache, braid lobes) ------------------------------------------------------------------
    m = zm("beard")
    if m.any():
        p, n = P[m], Nn[m]
        bd = T["beard"]
        mk = mk_all[m]
        c = np.repeat(bd["base"][None], m.sum(), 0)
        c = mix(c, bd["highlight"], smoothstep(0.25, 0.8, n[:, 2] * 0.7 - n[:, 1] * 0.5) * 0.55)
        c = mix(c, bd["shadow"], smoothstep(0.0, -0.6, n[:, 2]) * 0.7)
        c = mix(c, bd["highlight"] * 1.1, smoothstep(0.75, 0.98, mk) * 0.4)              # lighter lock tips / lobe crowns
        c = mix(c, bd["shadow"] * 0.8, smoothstep(0.3, 0.05, mk) * 0.5)                  # lobe roots
        comb = np.tile(np.array([[0.0, -0.1, -1.0]], dtype=np.float32), (m.sum(), 1))
        comb = comb - n * (comb * n).sum(1, keepdims=True)
        st = anisotropic(p, comb, 170.0, 18.0, seed=53)
        base[m] = c * (1 + 0.16 * (st[:, None] - 0.5))
    # ---- EYES ----------------------------------------------------------------------------------------------------------------
    m = zm("eye")
    if m.any():
        n = Nn[m]
        fwd = smoothstep(0.5, 0.95, -n[:, 1])
        base[m] = mix(np.repeat(ember_hot[None], m.sum(), 0), ember_core, fwd)
        emis[m] = mix(np.repeat(ember_hot[None], m.sum(), 0), ember_core, fwd)

    # ---- AO folded in as darker painted planes -----------------------------------------------------------------------------
    ao = cfg.get("ao")
    skip = np.isin(Z, [zones[z] for z in ("seam", "eye", "lava") if z in zones])
    if ao and "self" in ao and "ao_self" in maps:
        a = ao["self"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_self"]))
        base = base * np.where(skip, 1.0, f)[:, None]
    if ao and "hi" in ao and "ao_hi" in maps and "hi_w" in maps:
        a = ao["hi"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_hi"])) * maps["hi_w"]
        base = base * np.where(skip, 1.0, f)[:, None]
    # ---- glow: burnt edge in the base colour, the emissive map -----------------------------------------------------------
    burnt = np.array([0.26, 0.1, 0.05], dtype=np.float32)
    base = mix(base, burnt, glow_halo * 0.55)
    base = mix(base, ember_hot, glow_core * 0.85)
    base = mix(base, ember_core, glow_hot)
    glow = mix(np.repeat(ember_rim[None], N, 0) * 0.85, ember_hot, glow_core)
    glow = mix(glow, ember_core, glow_hot)
    e_line = np.maximum(glow_core, glow_halo * cfg.get("halo_emission", 0.35))
    emis = np.maximum(emis, glow * e_line[:, None])
    base = np.clip(base * (1 + 0.02 * fine[:, None]), 0, 1)
    pa = zm("plate", "anvil")
    po = pa & (ao_all > 0.25)
    log("painted: glow texels %d (%.2f %% of the plate / anvil texels, %.2f %% of the open ones), white-hot %d, edge texels %d" % (
        int((glow_core > 0.5).sum()), 100.0 * float((glow_core[pa] > 0.5).mean()), 100.0 * float((glow_core[po] > 0.5).mean()),
        int((glow_hot > 0.5).sum()), int((edge_all > 0.1).sum())))
    return base, np.clip(emis, 0, 1)


def sigil_distance(x, z, sg):
    """Distance (m) to the forge sigil's strokes in the cape's back plane: a vertical blade (a bar with a pointed
    foot), three pairs of branches sweeping up and out from it, and a three-point crown on top."""
    cx, z0, z1 = sg["x"], sg["z"][0], sg["z"][1]
    xs = x - cx
    d = np.full(len(x), 9.0)

    def seg(ax, az, bx, bz):
        ab = np.array([bx - ax, bz - az])
        t = np.clip(((xs - ax) * ab[0] + (z - az) * ab[1]) / (ab @ ab), 0, 1)
        return np.hypot(xs - (ax + t * ab[0]), z - (az + t * ab[1]))
    d = np.minimum(d, seg(0.0, z0, 0.0, z1))
    # tapering blade tip below the bar
    d = np.minimum(d, seg(0.0, z0, 0.0, z0 - sg["tip"]) + (z0 - np.clip(z, z0 - sg["tip"], z0)) * 0.35)
    for (bz, blen, rise) in sg["branches"]:
        for sx in (1, -1):
            d = np.minimum(d, seg(0.0, bz, sx * blen, bz + rise))
            d = np.minimum(d, seg(sx * blen, bz + rise, sx * blen * 1.05, bz + rise + blen * 0.35))
    cr = sg["crown"]
    for sx in (-1, 0, 1):
        d = np.minimum(d, seg(sx * cr[0] * 0.6, z1, sx * cr[0], z1 + cr[1] * (0.7 if sx else 1.0)))
    d = np.minimum(d, seg(-cr[0], z1, cr[0], z1))
    return d
