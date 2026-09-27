"""Procedural hand-painted NPR textures for Kael (numpy; driven by s2_texture.py through its "painter" hook).

Same contract as s2_paint.py (Brax): per-texel maps baked from the production mesh into its UV atlas (world position,
world normal, paint zone, object index, the gf_mask outline mask and per-piece random, the parts' self-AO, the
blockout's cavity / AO / hit weight) in, an sRGB base-colour and an sRGB emissive atlas out. Reuses s2_paint's noise,
Voronoi and dilate helpers.

Painting rules (art/characters/kael/brief.md sections 4-6, palette.json):
  * palette.json's measured tones are the colours: flat painted value planes, no light direction (the toon shader
    lights him); three value groups kept apart: DARK (coat, hair, black cloth, maroon, leather, boots), MID (bronze,
    skin), EMISSIVE (the ghost green);
  * the COAT is violet, not black: faces that look up (what the 55-degree camera sees) lifted toward the coat's
    highlight tone, vertical fold streaks, darker toward the hem, worn lighter edges (the rims are a bronze-grey worn
    trim, the concept's light edge lines), the lining a darker maroon-violet; the torn hem DISSOLVES into ghost flame:
    a teal tint and a soft emissive rising from the hem edge;
  * the GHOST ARM (his left arm below the bicep strap) is emissive ghost flesh: mottled teal-mint with a network of
    bright veins, never multiplied by AO; the WISPS (ghost-flame tatters) glow from a dim root on the coat to a bright
    tip with flame streaks along their length; the GEM in the buckle glows; the LEFT eye glows and green veins creep from
    it over the temple and the cheek. The ghost green leans teal-mint (declared hues), clear of the P4 ring green;
  * skin: warm planes, painted brows, stubble on the jaw, the scar over the right brow; hair: dark value planes with a
    light grey streak over the ghost side; cloth: near-black with a cool weave; leather and boots: worn warm browns
    with lighter scuffed edges and darker soles; bronze: a painted highlight band; cartridges: dark gun-metal cases;
  * brush variation is low-frequency value noise, never grunge; AO (the parts' own and the blockout's) is folded into
    the non-emissive zones as darker painted planes.
"""
import numpy as np

from s2_paint import anisotropic, dilate, fbm, hex3, mix, smoothstep, voronoi  # noqa: F401


def paint(maps, zones, pal, cfg, log=print):
    P, Nn, Z = maps["pos"], maps["nrm"], maps["zone"]
    N = len(P)
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    T = {k: {t: hex3(h) for t, h in v.items()} for k, v in pal.items()}
    D = {k: hex3(v) for k, v in cfg["declared"].items()}
    brush = (fbm(P, 6.0, 3, seed=1) - 0.5) * 2
    fine = (fbm(P, 38.0, 2, seed=2) - 0.5) * 2
    mk_all = maps["mask"] if "mask" in maps else np.full(N, 0.5, dtype=np.float32)
    pr_all = maps["prand"] if "prand" in maps else np.full(N, 0.5, dtype=np.float32)
    gh_rim, gh_hot, gh_core = D["ghost_rim"], D["ghost_hot"], D["ghost_core"]

    def zm(*names):
        return np.isin(Z, [zones[n] for n in names if n in zones])

    def ones(m):
        return np.ones((m.sum(), 1), dtype=np.float32)

    # -- skin: face, neck, the right hand's fingers --------------------------------------------------------------
    m = zm("skin")
    if m.any():
        p, n = P[m], Nn[m]
        sk = T["skin"]
        c = mix(np.repeat(sk["base"][None], m.sum(), 0), sk["highlight"], np.clip(brush[m] * 0.35 + 0.15, 0, 1) * 0.35)
        c = mix(c, sk["shadow"], np.clip(-brush[m], 0, 1) * 0.2)
        ez, ex, ey = cfg["eye_z"], cfg["eye_x"], cfg["eye_y"]
        face = (p[:, 2] > 1.8) & (np.abs(p[:, 0]) < 0.12)
        ax = np.abs(p[:, 0])
        # stubble: a cool dark overlay below the cheekbones, on the jaw and the upper lip
        st = cfg["stubble"]
        jaw = face & (p[:, 2] < ez - st["below_eye"]) & (p[:, 2] > ez - st["to_below_eye"]) & (p[:, 1] < st["y_max"]) & (n[:, 1] < 0.4)
        stub = jaw.astype(np.float32) * (0.75 + 0.25 * fbm(p, 160.0, 1, seed=41))
        c = mix(c, np.array([0.30, 0.26, 0.26], dtype=np.float32), stub * st["amount"])
        # brows: dark painted shapes above each eye, thicker at the inner end
        brow_top = ez + 0.021 - (ax - 0.012) * 0.1
        brow = (face & (p[:, 2] > ez + 0.011) & (p[:, 2] < brow_top) & (ax > 0.008) & (ax < 0.05) & (n[:, 1] < -0.25)).astype(np.float32)
        c = mix(c, T["hair"]["base"], brow * 0.8)
        # eye sockets
        for sx in (1, -1):
            e = np.array([sx * ex, ey, ez])
            d = np.linalg.norm((p - e) * [1.0, 0.6, 1.4], axis=1)
            c = mix(c, sk["shadow"] * 0.7, smoothstep(0.03, 0.012, d) * 0.55)
        # lips
        mz = cfg.get("mouth_z", ez - 0.075)
        lip = ((np.abs(p[:, 2] - mz) < 0.008) & (ax < 0.03) & (n[:, 1] < -0.3) & face).astype(np.float32)
        c = mix(c, np.array([0.47, 0.30, 0.26], dtype=np.float32), lip * 0.5)
        mo = cfg.get("mouth")
        if mo:
            slit = ((np.abs(p[:, 2] - mo["slit_z"]) < 0.0022) & (ax < mo["half_w"]) & face).astype(np.float32)
            c = mix(c, np.array([0.22, 0.12, 0.11], dtype=np.float32), slit * 0.8)
        # the scar over his right brow
        sc = cfg["scar"]
        a, b = np.array(sc["a"]), np.array(sc["b"])
        q = np.stack([p[:, 0], p[:, 2]], 1)
        t = np.clip(((q - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
        dsc = np.linalg.norm(q - (a + t[:, None] * (b - a)), axis=1)
        scar = smoothstep(sc["width"], sc["width"] * 0.3, dsc) * (n[:, 1] < -0.2) * face
        c = mix(c, D["scar"], scar * 0.85)
        # the LEFT side of the face: pale ghost tint and glowing veins round the glowing eye (temple, cheek)
        fg = cfg["face_glow"]
        el = np.array([ex, ey, ez])
        dv = (p - el) * [1.0, 0.8, 1.0]
        dist = np.linalg.norm(dv, axis=1)
        reach = smoothstep(fg["radius"], fg["radius"] * 0.25, dist) * (p[:, 0] > 0.004) * face
        reach = reach * smoothstep(0.3, 0.6, fbm(p, 30.0, 2, seed=45) + 0.25 * reach)
        _, edge, _ = voronoi(p + (np.stack([fbm(p, 40.0, 2, seed=s) for s in (46, 47, 48)], 1) - 0.5) * 0.01, fg["vein_freq"], seed=49)
        vein = smoothstep(0.09, 0.02, edge) * reach
        c = mix(c, mix(np.repeat(gh_hot[None], m.sum(), 0), sk["highlight"], 0.4), reach * fg["tint"])
        c = mix(c, gh_hot, vein * 0.8)
        base[m] = c
        emis[m] = mix(gh_rim[None] * ones(m), gh_hot, vein[:, None]) * np.maximum(vein, reach * 0.22)[:, None] * fg["strength"]
    # -- eyes: the LEFT eye glows ghost green, the right is a normal amber-brown eye -------------------------------
    m = zm("eye")
    if m.any():
        p, n = P[m], Nn[m]
        ey = T["eye_glow"]
        fwd = smoothstep(0.7, 0.95, -n[:, 1])
        left = (p[:, 0] > 0).astype(np.float32)
        right_c = mix(np.repeat(D["sclera"][None], m.sum(), 0), D["iris_right"], fwd)
        right_c = mix(right_c, np.array([0.05, 0.04, 0.04], dtype=np.float32), smoothstep(0.97, 0.995, -n[:, 1]))
        left_c = mix(np.repeat(gh_hot[None], m.sum(), 0), gh_core, fwd)
        base[m] = mix(right_c, left_c, left)
        emis[m] = mix(ey["rim"][None] * ones(m), gh_core, fwd) * left[:, None]
    # -- hair: dark value planes, lighter lock tips, the grey streak over the ghost side --------------------------
    m = zm("hair")
    if m.any():
        p, n = P[m], Nn[m]
        hb = T["hair"]
        L = np.array([0.0, -0.3, 0.95], dtype=np.float32)
        L /= np.linalg.norm(L)
        ndl = n @ L
        c = np.repeat(hb["shadow"][None], m.sum(), 0)
        c = mix(c, hb["base"], smoothstep(-0.25, -0.05, ndl))
        c = mix(c, hb["highlight"], smoothstep(0.5, 0.62, ndl) * 0.8)
        c = mix(c, hb["highlight"], smoothstep(0.78, 0.96, mk_all[m]) * 0.4)
        hs = cfg["hair_streak"]
        streak = ((p[:, 0] > hs["x"][0]) & (p[:, 0] < hs["x"][1]) & (p[:, 1] < hs["y_max"]) & (p[:, 2] > hs["z_min"])).astype(np.float32)
        streak *= smoothstep(0.35, 0.6, fbm(p, 55.0, 2, seed=57))
        c = mix(c, D["hair_streak"], streak * hs["amount"])
        comb = np.tile(np.array([[0.0, 0.8, 0.5]], dtype=np.float32), (m.sum(), 1))
        comb = comb - n * (comb * n).sum(1, keepdims=True)
        stn = anisotropic(p, comb, 150.0, 18.0, seed=51)
        base[m] = c * (1 + 0.14 * (stn[:, None] - 0.5))
    # -- black cloth: shirt, trousers, scarf; the fingerless glove --------------------------------------------------
    m = zm("cloth", "glove")
    if m.any():
        p, n = P[m], Nn[m]
        bc = T["black_cloth"]
        glove = (Z[m] == zones["glove"]).astype(np.float32)
        weave = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 110.0, 14.0, seed=61)
        c = mix(np.repeat(bc["base"][None], m.sum(), 0), bc["highlight"], smoothstep(0.55, 0.8, weave) * 0.6)
        c = mix(c, bc["shadow"], smoothstep(0.42, 0.2, weave) * 0.5)
        c = mix(c, bc["highlight"] * 1.15, smoothstep(0.35, 0.85, n[:, 2]) * 0.35)          # up-facing planes lift
        c = mix(c, bc["shadow"] * 0.8, smoothstep(-0.2, -0.7, n[:, 2]) * 0.5)
        # the glove: black leather, a painted highlight on the knuckles and the back of the hand
        gl = mix(np.repeat(bc["shadow"][None], m.sum(), 0), T["leather"]["shadow"], 0.25)
        gl = mix(gl, bc["highlight"] * 1.3, smoothstep(0.4, 0.9, n[:, 2]) * 0.6)
        base[m] = mix(c, gl, glove)
    # -- the ghost arm: mottled ghost flesh, bright veins, emissive -----------------------------------------------
    m = zm("ghost")
    if m.any():
        p, n = P[m], Nn[m]
        g = cfg["ghost"]
        ga = T["ghost_arm"]
        warp = (np.stack([fbm(p, 12.0, 2, seed=s) for s in (71, 72, 73)], 1) - 0.5) * g.get("warp", 0.03)
        _, edge, _ = voronoi(p + warp, g["vein_freq"], seed=74)
        vein = smoothstep(0.05, 0.012, edge) * smoothstep(0.3, 0.55, fbm(p, 9.0, 2, seed=77))
        _, edge2, _ = voronoi(p + warp * 1.7, g["vein_freq"] * 2.4, seed=75)
        vein = np.maximum(vein, smoothstep(0.035, 0.008, edge2) * 0.3)
        mott = fbm(p, 14.0, 3, seed=76)
        c = mix(np.repeat(ga["rim"][None], m.sum(), 0), ga["hot"], smoothstep(0.3, 0.62, mott))
        c = mix(c, ga["core"], vein * 0.8)
        c = mix(c, ga["rim"] * 0.8, smoothstep(-0.2, -0.8, n[:, 2]) * 0.35)                   # a cooler underside
        base[m] = c
        e = mix(gh_rim[None] * ones(m), gh_hot, smoothstep(0.25, 0.65, mott))
        e = mix(e, gh_core, vein)
        lvl = g["emit"] * (0.75 + 0.25 * smoothstep(-0.3, 0.6, n[:, 2])) + (g["vein_emit"] - g["emit"]) * vein
        emis[m] = e * lvl[:, None]
    # -- the coat: violet cloth, lifted tops, fold streaks, worn edges, the hem dissolving into ghost flame ----------
    m = zm("coat", "lining", "coat_edge")
    if m.any():
        p, n = P[m], Nn[m]
        cv, mr = T["coat_violet"], T["tabard_maroon"]
        zz = Z[m]
        mk = mk_all[m]
        folds = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 32.0, 3.0, seed=81)
        c = mix(np.repeat(cv["base"][None], m.sum(), 0), cv["highlight"], smoothstep(0.55, 0.85, folds) * 0.55)
        c = mix(c, cv["shadow"], smoothstep(0.42, 0.18, folds) * 0.55)
        c = mix(c, cv["highlight"] * 1.12, smoothstep(0.25, 0.8, n[:, 2]) * cfg["coat_lift_top"])     # lit tops (55 deg)
        c = mix(c, cv["shadow"], smoothstep(-0.2, -0.7, n[:, 2]) * 0.5)
        c = c * (1 + 0.06 * brush[m][:, None]) * (0.94 + 0.12 * pr_all[m][:, None])
        # worn, lighter patches and scuffs (low frequency, never grunge)
        wear = smoothstep(0.66, 0.8, fbm(p, 9.0, 3, seed=83))
        c = mix(c, cv["highlight"] * 1.25, wear * 0.35)
        # darker toward the hem
        hem = 1 - smoothstep(0.0, 1.0, mk)
        low = (p[:, 2] < cfg["hem_glow"]["z_max"]).astype(np.float32)
        c = mix(c, cv["shadow"] * 0.9, hem * low * 0.35)
        # the lining: a darker maroon-violet
        lin = (zz == zones["lining"]).astype(np.float32)
        lc = mix(np.repeat(mr["shadow"][None], m.sum(), 0), cv["shadow"], 0.4) * (0.9 + 0.2 * folds[:, None])
        c = mix(c, lc, lin)
        # the rims: the worn bronze-grey edge trim
        edge = (zz == zones["coat_edge"]).astype(np.float32)
        ec = mix(np.repeat(D["coat_edge"][None], m.sum(), 0), T["bronze"]["shadow"], 0.3) * (0.85 + 0.3 * fbm(p, 60.0, 1, seed=85)[:, None])
        c = mix(c, ec, edge)
        # the hem dissolving into ghost flame: teal tint + soft emissive from the hem edge up
        hg = cfg["hem_glow"]
        gz = (1 - smoothstep(hg["range"][0], hg["range"][1], mk)) * low
        flick = smoothstep(0.35, 0.75, fbm(p * np.array([1.0, 1.0, 0.35]), 16.0, 3, seed=87))
        glow = gz * (0.35 + 0.65 * flick)
        c = mix(c, mix(np.repeat(gh_rim[None], m.sum(), 0), cv["base"], 0.35), glow * hg["tint"])
        base[m] = c
        emis[m] = mix(gh_rim[None] * ones(m), gh_hot, glow ** 2)[:, :] * (glow * hg["strength"] * (gz > 0.02))[:, None] * 1.6
    # -- maroon loin cloth -------------------------------------------------------------------------------------------
    m = zm("maroon")
    if m.any():
        p, n = P[m], Nn[m]
        mr = T["tabard_maroon"]
        st = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 80.0, 7.0, seed=91)
        c = mix(np.repeat(mr["base"][None], m.sum(), 0), mr["highlight"] * 1.15, smoothstep(0.55, 0.82, st) * 0.7)
        c = mix(c, mr["shadow"], smoothstep(0.42, 0.18, st) * 0.6)
        c = mix(c, mr["shadow"] * 0.8, smoothstep(0.8, 0.62, p[:, 2]) * 0.55)          # a darker, frayed bottom
        base[m] = c
    # -- leather: belts, bandolier, holster, pouch, straps, bracer ---------------------------------------------------
    m = zm("leather")
    if m.any():
        p, n = P[m], Nn[m]
        lt = T["leather"]
        mk = mk_all[m]
        grain = anisotropic(p, np.tile([[1.0, 0.0, 0.0]], (m.sum(), 1)), 40.0, 160.0, seed=101)
        c = mix(np.repeat(lt["base"][None], m.sum(), 0), lt["highlight"], smoothstep(0.6, 0.85, grain) * 0.45)
        c = c * (0.9 + 0.2 * pr_all[m][:, None])
        c = mix(c, lt["highlight"] * 1.1, smoothstep(0.3, 0.85, n[:, 2]) * 0.45)
        c = mix(c, lt["shadow"] * 0.75, smoothstep(0.35, 0.05, mk) * 0.5)                    # darker strap edges
        c = mix(c, lt["highlight"] * 1.25, smoothstep(0.7, 0.82, fbm(p, 45.0, 2, seed=103)) * 0.3)   # scuffs
        base[m] = c
    # -- boots -------------------------------------------------------------------------------------------------------
    m = zm("boot")
    if m.any():
        p, n = P[m], Nn[m]
        bt = T["boot_leather"]
        grain = fbm(p, 24.0, 3, seed=111)
        c = mix(np.repeat(bt["base"][None], m.sum(), 0), bt["highlight"], smoothstep(0.55, 0.8, grain) * 0.35)
        c = mix(c, bt["highlight"] * 1.15, smoothstep(0.3, 0.85, n[:, 2]) * 0.5)             # toe caps, cuff tops
        c = mix(c, bt["shadow"], smoothstep(-0.1, -0.6, n[:, 2]) * 0.6)
        c = mix(c, bt["highlight"] * 1.3, smoothstep(0.72, 0.84, fbm(p, 50.0, 2, seed=113)) * 0.3)
        c = mix(c, D["sole"], smoothstep(0.022, 0.012, p[:, 2]))                               # the sole
        base[m] = c
    # -- bronze: buckles, cartridge caps --------------------------------------------------------------------------------
    m = zm("bronze")
    if m.any():
        p, n = P[m], Nn[m]
        br = T["bronze"]
        c = np.repeat(br["base"][None], m.sum(), 0) * (1 + 0.05 * brush[m][:, None])
        c = mix(c, br["shadow"], 0.25)
        c = mix(c, br["highlight"], smoothstep(0.35, 0.85, n[:, 2]) * 0.55)
        c = mix(c, br["highlight"], smoothstep(0.5, 0.95, -n[:, 1]) * 0.25)
        c = mix(c, br["shadow"] * 0.75, smoothstep(-0.2, -0.7, n[:, 2]) * 0.6)
        base[m] = c
    # -- cartridges: dark gun-metal cases ------------------------------------------------------------------------------
    m = zm("cartridge")
    if m.any():
        n = Nn[m]
        c = np.repeat(D["cartridge"][None], m.sum(), 0)
        c = mix(c, D["cartridge"] * 1.6, smoothstep(0.3, 0.9, -n[:, 1]) * 0.4)
        base[m] = c
    # -- the ghost gem ---------------------------------------------------------------------------------------------------
    m = zm("gem")
    if m.any():
        n = Nn[m]
        gb = T["gem_buckle"]
        f = smoothstep(0.6, 0.95, -n[:, 1])
        base[m] = mix(np.repeat(gh_hot[None], m.sum(), 0), gh_core, f)
        emis[m] = mix(gh_rim[None] * ones(m), gh_core, f) * 0.95 + gb["rim"] * 0.0
    # -- the ghost-flame tatters ------------------------------------------------------------------------------------------
    m = zm("wisp")
    if m.any():
        p, n = P[m], Nn[m]
        w = cfg["wisp"]
        s = mk_all[m]                                   # 0 root .. 1 tip
        flame = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 70.0, 6.0, seed=121)
        core = smoothstep(0.5, 0.8, flame)
        c = mix(np.repeat(gh_rim[None], m.sum(), 0), gh_hot, smoothstep(0.0, 0.6, s))
        c = mix(c, gh_core, core * smoothstep(0.2, 0.8, s) * 0.7)
        base[m] = c
        lvl = w["root_emit"] + (w["tip_emit"] - w["root_emit"]) * smoothstep(0.05, 0.6, s)
        e = mix(gh_rim[None] * ones(m), gh_hot, smoothstep(0.0, 0.5, s))
        e = mix(e, gh_core, core * smoothstep(0.3, 0.9, s))
        emis[m] = e * (lvl * (0.8 + 0.2 * flame))[:, None]
    # AO folded into the painted colour of the non-emissive zones (the parts' own; the blockout's on the cloth / gear)
    glowing = zm("ghost", "gem", "wisp", "eye")
    ao = cfg.get("ao")
    if ao and "self" in ao and "ao_self" in maps:
        a = ao["self"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_self"]))
        base = base * np.where(glowing | zm(*a.get("skip", [])), 1.0, f)[:, None]
    if ao and "hi" in ao and "ao_hi" in maps and "hi_w" in maps:
        a = ao["hi"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_hi"])) * maps["hi_w"]
        base = base * np.where(glowing, 1.0, f)[:, None]
    if "cav" in maps:
        base = base * np.where(glowing, 1.0, 1 - 0.25 * smoothstep(0.55, 0.9, maps["cav"]))[:, None]
    base = np.clip(base * (1 + 0.025 * fine[:, None]), 0, 1)
    log("kael paint: %d texels, emissive texels %d" % (N, int((emis.max(1) > 0.02).sum())))
    return base, np.clip(emis, 0, 1)
