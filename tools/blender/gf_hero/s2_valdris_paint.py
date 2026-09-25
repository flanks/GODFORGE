"""Procedural hand-painted NPR textures for Valdris (numpy only; driven by s2_texture.py through its "painter" hook).

Same contract as s2_paint.py (Brax): per-texel maps baked from the production mesh into its UV atlas (world
position, world normal, paint zone, object index, the gf_mask outline mask and per-piece random, the parts' self-AO,
the blockout's cavity / AO / hit weight) in, an sRGB base-colour and an sRGB emissive atlas out. Reuses s2_paint's
noise, Voronoi and dilate helpers.

Painting rules (art/characters/valdris/brief.md sections 4-6, palette.json, the sheet's declared colour script):
  * the declared hexes are the base colours (Gunmetal #2A242E, Forge Gold #FFC24B, Ember Amber #FF6B1A, Deep War
    Red #7A1F1F, white-hot #FFF5CE); the measured tones shade them. Flat painted value planes, no light direction:
    the toon shader lights him. Art-directed cues only: faces that look up (the pauldron tops, the anvil's top face,
    the boot tops: what the 55-degree camera sees) are lifted toward the plate highlight; undersides sink toward the
    warm shadow; every plate outline gets a dark painted edge and a thin lighter wear line on its chamfer;
  * the plate is cracked (a domain-warped Voronoi crack mosaic, dark lines with a lighter lip, fine enough to average
    out at game size); the glowing seams are a sparser network of long jagged crack paths (the edges of large warped
    Voronoi cells) broken into runs, with short glowing branches into the mosaic: EMISSIVE thin lines with white-hot
    cores, denser on the anvil's flanks, the chest, the knees, the greave fronts and around the pauldron slots (brief
    section 4, item 5) and kept sparse everywhere, because at game size a dense network turns the dark plate into
    orange noise;
    the seam zone (pauldron slots, buckle core) glows solid; the under-suit glows dimly at the joints;
  * gold is painted metal: a flat base, a painted highlight band on up-facing trim, a dark underside, worn streaks;
  * the anvil's top face is one value step lighter than the plate (the light bar across his chest from 55 degrees),
    with a hardy hole and a pritchel hole near the heel;
  * the cape is Deep War Red with vertical fold streaks, a darker charred hem and the forge sigil on its back (a
    vertical blade with three pairs of up-swept branches and a three-point crown, the turnaround's back view), in
    emblem gold;
  * skin: warm weathered planes, heavy painted brows, deep eye sockets, the cracked scar across the scalp and
    forehead with a faint ember glow (Reforged Flesh); beard: iron-grey value planes with downward streaks, lighter
    lock tips and braid lobes; the braid caps are light steel;
  * brush variation is low-frequency value noise (+-5 %), never grunge; AO (the parts' own and the blockout's) and
    the blockout's cavity are folded in as darker painted planes.
"""
import numpy as np

from s2_paint import anisotropic, dilate, fbm, hex3, mix, smoothstep, value_noise, voronoi  # noqa: F401


def paint(maps, zones, pal, cfg, log=print):
    P, Nn, Z = maps["pos"], maps["nrm"], maps["zone"]
    N = len(P)
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    T = {k: {t: hex3(h) for t, h in v.items()} for k, v in pal.items()}
    D = {k: hex3(v) for k, v in cfg["declared"].items()}
    mk_all = maps["mask"] if "mask" in maps else np.full(N, 0.6, dtype=np.float32)
    pr_all = maps["prand"] if "prand" in maps else np.full(N, 0.5, dtype=np.float32)
    brush = (fbm(P, 5.0, 3, seed=1) - 0.5) * 2
    fine = (fbm(P, 36.0, 2, seed=2) - 0.5) * 2
    ember_rim, ember_hot, ember_core = T["ember_seams"]["rim"], D["ember"], D["white_hot"]
    glow_core = np.zeros(N, dtype=np.float32)       # bright seam line strength (0..1)
    glow_hot = np.zeros(N, dtype=np.float32)        # its white-hot centre
    glow_halo = np.zeros(N, dtype=np.float32)       # the soft band around it (feeds bloom)

    def zm(*names):
        return np.isin(Z, [zones[n] for n in names if n in zones])

    def add_glow(m, dist, width, weight, hotness=0.35, halo_mult=2.6, halo_w=0.45):
        """A glowing line at distance `dist` (m) from its centre line, half-width `width`, on texels m."""
        c = smoothstep(width, width * 0.35, dist) * weight
        h = smoothstep(width * hotness, width * hotness * 0.3, dist) * weight
        hl = smoothstep(width * halo_mult, width, dist) * weight * halo_w
        glow_core[m] = np.maximum(glow_core[m], c)
        glow_hot[m] = np.maximum(glow_hot[m], h)
        glow_halo[m] = np.maximum(glow_halo[m], hl)

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

    # ---- the crack mosaic shared by the plates and the anvil ------------------------------------------------
    cc = cfg["cracks"]
    hard = zm("plate", "anvil", "iron")
    ph = P[hard]
    warp = (np.stack([fbm(ph, 9.0, 2, seed=301), fbm(ph, 9.0, 2, seed=302), fbm(ph, 9.0, 2, seed=303)], 1) - 0.5) * cc["warp"]
    _, edge, cid = voronoi(ph + warp, cc["freq"], seed=311)
    crack_d = np.full(N, 9.0, dtype=np.float32)
    crack_d[hard] = edge / (2 * cc["freq"])                       # metres to the nearest crack line
    cell = np.zeros(N, dtype=np.float32)
    cell[hard] = cid
    crack_line = smoothstep(cc["width"], cc["width"] * 0.3, crack_d)            # dark crack
    crack_lip = smoothstep(cc["width"] * 2.4, cc["width"] * 1.2, crack_d) * (1 - crack_line)   # lighter lip beside it
    # the glowing seams: long wiggly crack lines (iso-lines of a warped low-frequency noise) broken into runs, denser
    # in the glow regions, plus short branches where the crack mosaic touches a glowing line. Sparse on purpose: at
    # game size a dense network turns the dark plate into orange noise (brief section 5: the darkness is his pop)
    gl = cfg["glow_lines"]
    reg = region_w(P, cfg["glow_regions"])
    run_gate = smoothstep(gl["run"][0] - reg * gl["region_boost"], gl["run"][1] - reg * gl["region_boost"], fbm(P, gl["run_freq"], 2, seed=321))
    gline_d = np.full(N, 9.0, dtype=np.float32)
    _, gedge, _ = voronoi(ph + warp * gl["warp_mult"], gl["freq"], seed=331)   # big cells: long jagged crack paths
    gline_d[hard] = gedge / (2 * gl["freq"])                                  # metres to the nearest path
    near_line = smoothstep(gl["branch_reach"], 0.0, gline_d)
    br_gate = (cell > 0.55).astype(np.float32) * near_line                      # some mosaic cracks next to a line glow
    glow_gate = run_gate * (gl["base"] + (1 - gl["base"]) * reg)

    # ---- PLATE (gunmetal) -----------------------------------------------------------------------------------
    def plate_paint(m, tones, base_col, lift_top, top_col):
        p, n = P[m], Nn[m]
        mk, pr = mk_all[m], pr_all[m]
        c = np.repeat(base_col[None], m.sum(), 0) * (0.9 + 0.2 * pr[:, None])
        c = mix(c, top_col, smoothstep(0.3, 0.85, n[:, 2]) * lift_top)                  # up-facing value plane
        c = mix(c, tones["shadow"] * 0.9, smoothstep(-0.15, -0.75, n[:, 2]) * 0.65)     # undersides
        c = c * (1 + 0.05 * brush[m][:, None])
        # the sculpt's surface: cracks of the blockout, where it coincides with the plate (cavity from the bake)
        if "cav" in maps:
            c = mix(c, tones["shadow"] * 0.7, smoothstep(0.62, 0.9, maps["cav"][m]) * 0.5)
        # crack mosaic: dark line, lighter lip, the cells slightly varied
        c = c * (0.94 + 0.12 * cell[m][:, None])
        c = mix(c, tones["highlight"] * 0.95, crack_lip[m] * cc["lip"])
        c = mix(c, tones["shadow"] * 0.5, crack_line[m] * cc["dark"])
        # painted outline (dark) and wear line on the chamfer (light)
        c = mix(c, tones["shadow"] * 0.55, smoothstep(0.14, 0.02, mk) * 0.8)
        c = mix(c, tones["highlight"] * 1.05, smoothstep(0.16, 0.26, mk) * smoothstep(0.42, 0.3, mk) * 0.35)
        return c

    m = zm("plate")
    if m.any():
        base[m] = plate_paint(m, T["gunmetal_plate"], D["gunmetal"], cfg["plate_lift_top"], T["gunmetal_plate"]["highlight"])
        g = glow_gate[m] * smoothstep(0.25, 0.5, mk_all[m])        # no glow on the chamfers
        add_glow(m, gline_d[m], gl["width"], g)
        add_glow(m, crack_d[m], gl["branch_width"], g * br_gate[m] * gl["branch"], hotness=0.25, halo_w=0.25)
    # ---- ANVIL (the same iron; top face a value step lighter, hardy and pritchel holes) ----------------------
    m = zm("anvil")
    if m.any():
        p, n = P[m], Nn[m]
        an = T["anvil_iron"]
        c = plate_paint(m, an, D["gunmetal"] * 1.05, 0.0, an["highlight"])
        top = smoothstep(0.7, 0.9, n[:, 2])
        ac = cfg["anvil"]
        c = mix(c, an["highlight"] * (0.95 + 0.1 * brush[m][:, None]), top * ac["top_lift"])
        # the top face's worn edge: lighter along the front edge of the face
        c = mix(c, an["highlight"] * 1.25, top * smoothstep(ac["front_edge_y"] + 0.03, ac["front_edge_y"], p[:, 1]) * 0.5)
        hh = ac["hardy"]
        dh = np.maximum(np.abs(p[:, 0] - hh[0]), np.abs(p[:, 1] - hh[1]))
        c = mix(c, an["shadow"] * 0.4, top * smoothstep(hh[2] + 0.004, hh[2], dh))
        pp = ac["pritchel"]
        dp = np.hypot(p[:, 0] - pp[0], p[:, 1] - pp[1])
        c = mix(c, an["shadow"] * 0.4, top * smoothstep(pp[2] + 0.003, pp[2], dp))
        base[m] = c
        g = glow_gate[m] * smoothstep(0.25, 0.5, mk_all[m]) * (1 - top)
        add_glow(m, gline_d[m], gl["width"] * 1.15, g)
        add_glow(m, crack_d[m], gl["branch_width"], g * br_gate[m] * gl["branch"], hotness=0.25, halo_w=0.25)
    # ---- IRON (inner walls, undersides, plate side walls) ---------------------------------------------------
    m = zm("iron")
    if m.any():
        ir = T["gunmetal_plate"]
        c = np.repeat(ir["shadow"][None], m.sum(), 0) * (0.85 + 0.25 * pr_all[m][:, None])
        c = mix(c, D["gunmetal"], smoothstep(0.2, 0.8, Nn[m][:, 2]) * 0.4)
        base[m] = c * (1 + 0.04 * brush[m][:, None])
    # ---- GOLD trim ---------------------------------------------------------------------------------------------
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
        base[m] = mix(np.repeat(ember_hot[None], m.sum(), 0), ember_core, smoothstep(0.45, 0.75, t) * 0.7)
        emis[m] = mix(mix(np.repeat(ember_hot[None], m.sum(), 0), ember_core, 0.45), ember_core, smoothstep(0.5, 0.7, t))
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
    skip = np.isin(Z, [zones[z] for z in ("seam", "eye") if z in zones])
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
    log("painted: glow texels %d (%.2f %% of the plate / anvil texels), crack texels %d" % (
        int((glow_core > 0.5).sum()), 100.0 * float((glow_core[hard] > 0.5).mean()), int((crack_line > 0.5).sum())))
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
