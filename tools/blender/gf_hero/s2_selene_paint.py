"""Procedural hand-painted NPR textures for Selene (numpy; driven by the shared s2_texture.py through its "painter" hook).

Same contract as s2_paint.py (Brax) and s2_valdris_paint.py: per-texel maps baked from the production mesh into its UV
atlas (world position, world normal, paint zone, object index, the gf_mask R / G channels, the parts' self-AO, the
blockout's cavity / AO / hit weight) in, an sRGB base-colour and an sRGB emissive atlas out. The zones are
s2_selene_parts.ZONES. The cloth sheets carry R = v (0 at the attachment .. 1 at the hem) and G = u (across) in
gf_mask, so the storm-blue gradients follow the cloth, not the world.

Painting rules (art/characters/selene/brief.md sections 4-6, palette.json):
  * three value groups: DARK (suit, leggings, plate, gauntlets), MID (gold, the cloth gradient), LIGHT (skin, hair);
    painted value planes from the measured swatches, no light direction (the toon shader lights her); faces that look
    up (what the 55-degree camera sees) lifted toward the measured highlight, undersides sunk toward the shadow;
  * the suit is never flat black: #1E252B lifted toward #36435B on the up-facing planes; a gold spine line on the back;
    the leggings one step bluer with fine gold seams down the outer thighs;
  * skin pale and cool (never grey) above the sweetheart neckline, on the shoulders and arms; the face: soft cool
    sockets, dark cat-eye liner, silver brows, muted rose lips;
  * the LIGHTNING VEINS are emissive (Static Charge scales them at runtime): jagged bolts with forks down both arms
    from the shoulder to the gauntlet, and one down her left cheek (the concept), a pale blue line in the base colour
    under the glow;
  * the cloth: the capes deep storm blue (#213F6F) at the top fading to the pale storm-cloud (#7788A8) at the ragged
    hem through watercolour cloud blotches; the hip panels and the shoulder drapes a lighter cyan-blue (#40648D) to
    the same pale edge, with gold side trims; the tabard pale storm blue with a gold vein tree down its centre;
  * gold is painted metal, a touch warmer and lighter than the measured dull gold so it reads at game size: a lit band
    on up-facing trim, dark undersides, thin rims only;
  * the plate (greaves, sabatons, armlets, hip plates) dark navy with lit tops and light-catching outlines; the
    cyan V slots on the greaves and the sabaton insteps are emissive;
  * the glows (eyes, collar gem, veins, greave slots, crystal shards, claws, the bun band) stay small: the P2 player
    cyan must not dominate (brief finding 3); AO (the parts' own, the blockout's) folded in as darker painted planes,
    never on an emissive zone.
"""
import math

import numpy as np

from s2_paint import anisotropic, dilate, fbm, hex3, mix, smoothstep, value_noise  # noqa: F401


def _seg_dist(q, a, b):
    ab = b - a
    t = np.clip(((q - a) @ ab) / (ab @ ab + 1e-12), 0, 1)
    return np.linalg.norm(q - (a + t[:, None] * ab), axis=1)


def bolt_polylines(seed, s0, s1, phi0, amp, step, branches, rng_scale=1.0):
    """A jagged lightning bolt from s0 to s1 (metres along the limb) around phi0 (radians around the limb), with
    forks. Returns a list of (N, 2) polylines in (s, phi) space."""
    rs = np.random.RandomState(seed)
    n = max(2, int((s1 - s0) / step))
    s = np.linspace(s0, s1, n + 1)
    phi = phi0 + np.cumsum(np.concatenate([[0.0], rs.uniform(-amp, amp, n)])) * 0.6
    phi = phi0 + (phi - phi0) * 0.8 + rs.uniform(-amp * 0.4, amp * 0.4, n + 1) * rng_scale
    lines = [np.stack([s, phi], 1)]
    for _ in range(branches):
        k = rs.randint(1, n)
        L = rs.uniform(0.03, 0.07)
        d = rs.choice([-1, 1])
        m = 3
        bs = s[k] + np.linspace(0, L, m + 1)
        bp = phi[k] + d * np.linspace(0, rs.uniform(0.5, 1.0), m + 1) + rs.uniform(-0.15, 0.15, m + 1) * np.r_[0, np.ones(m)]
        lines.append(np.stack([bs, bp], 1))
    return lines


def paint(maps, zones, pal, cfg, log=print):
    P, Nn, Z = maps["pos"], maps["nrm"], maps["zone"]
    N = len(P)
    OBJ = maps["obj"]
    objs = cfg["objects"]
    oi = {n: objs.index(n) + 1 for n in objs}
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    T = {k: {t: hex3(h) for t, h in v.items()} for k, v in pal.items()}
    C = {k: hex3(v) for k, v in cfg["colours"].items() if not k.startswith("_")}
    MR = maps["mask"] if "mask" in maps else np.full(N, 0.6, dtype=np.float32)
    MG = maps["prand"] if "prand" in maps else np.full(N, 0.5, dtype=np.float32)
    brush = (fbm(P, 5.0, 3, seed=1) - 0.5) * 2
    fine = (fbm(P, 40.0, 2, seed=2) - 0.5) * 2
    up = Nn[:, 2]

    def zm(*names):
        return np.isin(Z, [zones[n] for n in names if n in zones])

    def planes(m, tones, lift=0.45, sink=0.5, lift_to=None, sink_to=None):
        """Painted value planes: base, lifted on up-facing faces, sunk on undersides."""
        c = np.repeat(tones["base"][None], m.sum(), 0)
        c = mix(c, tones["highlight"] if lift_to is None else lift_to, smoothstep(0.25, 0.85, up[m]) * lift)
        c = mix(c, tones["shadow"] if sink_to is None else sink_to, smoothstep(-0.1, -0.75, up[m]) * sink)
        return c

    glow_line = np.zeros(N, dtype=np.float32)       # emissive line strength (veins, slots), coloured below
    glow_halo = np.zeros(N, dtype=np.float32)

    # ---- BODY: skin / suit (neckline, armholes), legging, glove -------------------------------------------------
    bodym = OBJ == oi["BODY"]
    ax = np.abs(P[:, 0])
    nl = np.array(cfg["neckline"], dtype=np.float64)
    nl = nl[np.argsort(nl[:, 0])]
    z_front = np.interp(ax, nl[:, 0], nl[:, 1], right=cfg["armhole_z"])
    z_back = np.where(ax < 0.12, cfg["back_neckline_z"], np.interp(ax, [0.12, 0.16], [cfg["back_neckline_z"], cfg["armhole_z"]]))
    front_w = smoothstep(0.25, -0.25, Nn[:, 1])
    z_line = z_front * front_w + z_back * (1 - front_w)
    skin_w = smoothstep(z_line - 0.003, z_line + 0.003, P[:, 2])
    skin_w = np.maximum(skin_w, (ax > cfg["arm_x"]).astype(np.float32))
    skin_w = np.where(zm("skin") & (P[:, 2] > 1.8), 1.0, skin_w)
    m_skin = bodym & zm("skin", "suit") & (skin_w > 0.5)
    m_suit = bodym & zm("suit", "skin") & ~m_skin
    m_skin |= zm("skin") & ~bodym
    m_suit |= zm("suit") & ~bodym

    # SUIT
    m = m_suit
    if m.any():
        sw = T["bodysuit"]
        c = planes(m, sw, lift=0.55, sink=0.45)
        p = P[m]
        # a faint tonal panel pattern (seams) and the gold spine line on the back
        seam = smoothstep(0.004, 0.0015, np.abs(np.abs(p[:, 0]) - 0.075)) * smoothstep(1.64, 1.6, p[:, 2]) * (Nn[m, 1] < 0)
        c = mix(c, sw["shadow"] * 0.8, seam * 0.6)
        spine = smoothstep(0.0035, 0.0015, np.abs(p[:, 0])) * (Nn[m, 1] > 0.3) * smoothstep(1.36, 1.4, p[:, 2]) * smoothstep(1.67, 1.63, p[:, 2])
        c = mix(c, C["gold_hi"], spine * 0.9)
        base[m] = c * (1 + 0.05 * brush[m][:, None])
    # LEGGING
    m = zm("legging")
    if m.any():
        lt = T["leggings"]
        p = P[m]
        c = planes(m, lt, lift=0.6, sink=0.4)
        # the hip line: the suit's value above z ~1.16 blends into the bluer leggings
        c = mix(c, planes(m, T["bodysuit"], 0.55, 0.45), smoothstep(1.1, 1.18, p[:, 2]))
        # fine gold seams down the outer thighs and a darker scale pattern on the thigh sides
        sd = np.sign(p[:, 0])
        la = np.arctan2(np.abs(p[:, 0]) - 0.065, -(p[:, 1] + 0.005))           # 0 = front of the leg, + = outside
        seam = smoothstep(0.05, 0.02, np.abs(la - 1.45)) * smoothstep(0.62, 0.7, p[:, 2]) * smoothstep(1.16, 1.1, p[:, 2])
        c = mix(c, C["gold"], seam * 0.85)
        scale = np.abs(np.sin(p[:, 2] * 70.0 + np.abs(la) * 3.0))
        sc_m = smoothstep(0.4, 1.3, np.abs(la)) * smoothstep(0.66, 0.72, p[:, 2]) * smoothstep(1.1, 1.0, p[:, 2])
        c = mix(c, lt["shadow"] * 0.85, smoothstep(0.85, 0.97, scale) * sc_m * 0.6)
        base[m] = c * (1 + 0.05 * brush[m][:, None])
        del sd
    # GLOVE (the gauntlet leather + the fingerless glove on the hand)
    m = zm("glove")
    if m.any():
        gl = T["gauntlets"]
        c = planes(m, gl, lift=0.45, sink=0.55)
        c = mix(c, gl["shadow"], smoothstep(0.3, 0.05, MR[m]) * 0.35 * (OBJ[m] != oi["BODY"]))
        base[m] = c * (1 + 0.06 * brush[m][:, None])
    # SKIN (+ face, veins)
    m = m_skin
    if m.any():
        sk = T["skin"]
        p, n = P[m], Nn[m]
        cool = C["skin_cool"]
        c = np.repeat(sk["base"][None], m.sum(), 0)
        c = mix(c, sk["highlight"] * 1.03, smoothstep(0.35, 0.9, n[:, 2]) * 0.55)
        c = mix(c, mix(sk["shadow"], cool, 0.45), smoothstep(-0.05, -0.7, n[:, 2]) * 0.55)
        # face
        ex, ey, ez = cfg["eye_x"], cfg["eye_y"], cfg["eye_z"]
        axm = np.abs(p[:, 0])
        face = (p[:, 2] > 1.82) & (p[:, 1] < ey + 0.05)
        for sx in (1, -1):
            e = np.array([sx * ex, ey, ez])
            d = np.linalg.norm((p - e) * [1.0, 0.7, 1.35], axis=1)
            c = mix(c, mix(sk["shadow"], cool, 0.6), smoothstep(0.03, 0.012, d) * 0.5 * face)
            # cat-eye liner: the upper lid line and a wing swept up and out
            dz = p[:, 2] - (ez + 0.0045 + 0.004 * np.clip((axm - ex) / 0.02, 0, 1.5))
            lid = smoothstep(0.0025, 0.0008, np.abs(dz)) * smoothstep(0.024, 0.016, np.abs(p[:, 0] - sx * ex) - 0.004 * (axm > ex))
            c = mix(c, C["liner"], lid * face * (p[:, 0] * sx > 0) * 0.9)
        brow_c = ez + 0.0165 + (axm - 0.012) * 0.22
        brow = (smoothstep(brow_c - 0.0055, brow_c - 0.0025, p[:, 2]) * smoothstep(brow_c + 0.004, brow_c + 0.0015, p[:, 2])
                * smoothstep(0.008, 0.015, axm) * smoothstep(0.058, 0.048, axm) * smoothstep(-0.2, -0.45, n[:, 1]))
        c = mix(c, T["hair"]["shadow"] * 0.85, brow * face * 0.85)
        mo = cfg.get("mouth")
        if mo:
            lip_c = mo["slit_z"]
            dl = np.abs(p[:, 2] - lip_c) / 0.009 + (axm / (mo["half_w"] * 1.05)) ** 2
            lips = smoothstep(1.05, 0.8, dl) * (p[:, 1] < mo["y_inner"] + 0.012)
            c = mix(c, C["lips"], lips * 0.85 * face)
            c = mix(c, C["lips"] * 0.55, smoothstep(0.0016, 0.0004, np.abs(p[:, 2] - lip_c)) * smoothstep(mo["half_w"], mo["half_w"] * 0.7, axm) * face * 0.8)
        # arm veins: bolts in (s along the arm, phi around it) -> arc metres
        arm = (axm > 0.2) & (axm < 0.62) & (p[:, 2] > 1.6)
        vein = np.zeros(m.sum(), dtype=np.float32)
        if arm.any():
            pa = p[arm]
            s_ = np.abs(pa[:, 0])
            phi = np.arctan2(-(pa[:, 1] - cfg["arm_axis"][0]), pa[:, 2] - cfg["arm_axis"][1])     # 0 = top, + = front
            R_ = 0.04
            dmin = np.full(len(pa), 9.0)
            for sdn in (1, -1):
                side = (pa[:, 0] * sdn) > 0
                if not side.any():
                    continue
                for bk, bv in enumerate(cfg["veins"]["bolts"]):
                    for pl in bolt_polylines(bv["seed"] + (0 if sdn > 0 else 100), bv["s"][0], bv["s"][1], math.radians(bv["phi"]),
                                             bv["amp"], bv["step"], bv["branches"]):
                        q = np.stack([s_[side], phi[side] * R_], 1)
                        for a, b in zip(pl[:-1], pl[1:]):
                            dmin[side] = np.minimum(dmin[side], _seg_dist(q, np.array([a[0], a[1] * R_]), np.array([b[0], b[1] * R_])))
            vw = cfg["veins"]["width"]
            fade = smoothstep(0.2, 0.25, s_) * smoothstep(0.62, 0.58, s_)
            vein[arm] = smoothstep(vw, vw * 0.35, dmin) * fade
            halo = smoothstep(vw * 3.2, vw, dmin) * fade
            tmp = np.zeros(m.sum(), dtype=np.float32)
            tmp[arm] = halo
            c = mix(c, T["lightning_veins"]["rim"] * 0.9 + sk["base"] * 0.1, tmp * 0.35)
        # the cheek vein (her left cheek, the concept): a short jagged bolt under the left eye
        ck = cfg["veins"]["cheek"]
        pts = np.array(ck, dtype=np.float64)
        q = np.stack([p[:, 0], p[:, 2]], 1)
        dck = np.full(m.sum(), 9.0)
        for a, b in zip(pts[:-1], pts[1:]):
            dck = np.minimum(dck, _seg_dist(q, a, b))
        cheek = smoothstep(cfg["veins"]["width"] * 0.8, cfg["veins"]["width"] * 0.3, dck) * face * (p[:, 1] < ey + 0.03)
        vein = np.maximum(vein, cheek)
        c = mix(c, T["lightning_veins"]["hot"], vein * 0.8)
        base[m] = c * (1 + 0.025 * brush[m][:, None])
        glow_line[m] = np.maximum(glow_line[m], vein)
    # ---- HAIR ------------------------------------------------------------------------------------------------------
    m = zm("hair")
    if m.any():
        hr = T["hair"]
        p, n = P[m], Nn[m]
        bun = np.array(cfg["bun_centre"], dtype=np.float32)
        flow = bun[None] - p
        flow = np.where((p[:, 2] < 1.96)[:, None] & (p[:, 1] < 0.0)[:, None], np.array([[0.0, 0.0, -1.0]], dtype=np.float32), flow)
        flow = flow - n * (flow * n).sum(1, keepdims=True)
        st = anisotropic(p, flow, 190.0, 14.0, seed=53)
        c = np.repeat(hr["base"][None], m.sum(), 0)
        c = mix(c, hr["highlight"], smoothstep(0.2, 0.85, n[:, 2]) * 0.6)
        c = mix(c, hr["shadow"], smoothstep(0.0, -0.6, n[:, 2]) * 0.6)
        c = mix(c, hr["highlight"], smoothstep(0.75, 0.98, MR[m]) * 0.25)
        c = mix(c, hr["shadow"] * 0.9, smoothstep(0.35, 0.1, MR[m]) * 0.35)
        # swept strands: stronger value streaks along the flow and dark grooves between the locks (the toon shader
        # shades the smooth shell as one mass; the paint has to break it up)
        st2 = anisotropic(p, flow, 70.0, 6.0, seed=57)
        c = c * (1 + 0.32 * (st[:, None] - 0.5))
        c = mix(c, hr["shadow"] * 0.8, smoothstep(0.34, 0.2, st2) * 0.55)
        c = mix(c, hr["highlight"], smoothstep(0.68, 0.82, st2) * smoothstep(-0.1, 0.5, n[:, 2]) * 0.45)
        # the centre ridge the concept draws from the forehead to the bun
        ridge = smoothstep(0.004, 0.0015, np.abs(p[:, 0])) * (p[:, 1] < bun[1]) * (p[:, 2] > 1.99)
        c = mix(c, hr["shadow"] * 0.85, ridge * 0.5)
        base[m] = c
    # ---- GOLD ------------------------------------------------------------------------------------------------------
    m = zm("gold")
    if m.any():
        n = Nn[m]
        c = np.repeat(C["gold"][None], m.sum(), 0)
        c = mix(c, C["gold_hi"], smoothstep(0.2, 0.75, n[:, 2]) * 0.8)
        c = mix(c, C["gold_lo"], smoothstep(0.0, -0.6, n[:, 2]) * 0.7)
        c = mix(c, C["gold_hi"] * 1.08, smoothstep(0.55, 0.95, -n[:, 1]) * smoothstep(-0.2, 0.3, n[:, 2]) * 0.25)
        base[m] = c * (1 + 0.06 * brush[m][:, None] + 0.04 * (MG[m][:, None] - 0.5))
    # ---- PLATE (+ greave / sabaton glow slots) -----------------------------------------------------------------
    m = zm("plate")
    if m.any():
        pl = T["sabatons"]
        p, n = P[m], Nn[m]
        c = planes(m, pl, lift=0.55, sink=0.5)
        c = mix(c, pl["highlight"] * 1.15, smoothstep(0.3, 0.05, MR[m]) * 0.35)                 # light-catching outline
        c = c * (1 + 0.1 * (MG[m][:, None] - 0.5))
        base[m] = c * (1 + 0.04 * brush[m][:, None])
        gs = cfg["glow_slots"]
        slot = np.zeros(m.sum(), dtype=np.float32)
        on_g = OBJ[m] == oi["GREAVES"]
        on_s = OBJ[m] == oi["SABATONS"]
        lx = np.abs(p[:, 0]) - gs["leg_x"]
        la = np.arctan2(lx, -(p[:, 1] - gs["leg_y"]))
        for v in gs["greave_v"]:
            # a V pointing down on the greave front: two strokes in (azimuth * r, z)
            q = np.stack([la * 0.06, p[:, 2]], 1)
            for sx in (1, -1):
                d = _seg_dist(q, np.array([sx * v["half"] * 0.06, v["top"]]), np.array([0.0, v["bottom"]]))
                slot = np.maximum(slot, smoothstep(gs["width"], gs["width"] * 0.35, d) * on_g * (n[:, 1] < -0.1))
        for v in gs["sabaton_v"]:
            q = np.stack([p[:, 0] - np.sign(p[:, 0]) * gs["foot_x"], p[:, 1]], 1)
            for sx in (1, -1):
                d = _seg_dist(q, np.array([sx * v["half"], v["back"]]), np.array([0.0, v["tip"]]))
                slot = np.maximum(slot, smoothstep(gs["width"], gs["width"] * 0.35, d) * on_s * (n[:, 2] > 0.35))
        base[m] = mix(base[m], T["armour_glow"]["hot"], slot * 0.85)
        glow_line[m] = np.maximum(glow_line[m], slot)
        glow_halo[m] = np.maximum(glow_halo[m], slot * 0.5)
    # ---- CLOTH -----------------------------------------------------------------------------------------------------
    cc = cfg["cloth"]
    for zname in ("cape", "panel", "tabard"):
        m = zm(zname)
        if not m.any():
            continue
        p, n = P[m], Nn[m]
        v = MR[m]
        u = MG[m]
        top = {"cape": T["cape_deep"], "panel": T["panel_blue"], "tabard": T["tabard"]}[zname]
        pale = T["cape_pale"]
        cloud = fbm(p * [1.0, 1.0, 0.7], cc["cloud_freq"], 4, seed=71 + len(zname))
        t = smoothstep(cc["fade"][zname][0], cc["fade"][zname][1], v + (cloud - 0.5) * cc["cloud_amp"])
        c = mix(np.repeat(top["base"][None], m.sum(), 0), pale["base"], t)
        # watercolour blotches: deep cloud shapes inside the pale, pale wisps inside the deep
        blot = smoothstep(0.52, 0.62, fbm(p, cc["cloud_freq"] * 2.2, 3, seed=91))
        c = mix(c, top["shadow"] * 1.05, blot * t * (1 - t) * 2.2 * cc["blot"])
        c = mix(c, pale["highlight"], smoothstep(0.6, 0.72, cloud) * t * 0.5)
        # the ragged hem and the free edges pale out
        edge = np.maximum(smoothstep(0.86, 1.0, v), 0.6 * np.maximum(smoothstep(0.08, 0.0, u), smoothstep(0.92, 1.0, u)) * smoothstep(0.3, 0.7, v))
        c = mix(c, pale["highlight"], edge * 0.5)
        c = mix(c, top["shadow"], smoothstep(0.12, 0.0, v) * 0.5)                  # darker at the attachment
        # the side of the sheet facing the body is a shade deeper
        back = {"cape": (OBJ[m] == oi["TABARD"]) & (n[:, 1] < -0.2), "panel": n[:, 1] > 0.2, "tabard": n[:, 1] > 0.2}[zname]
        c = np.where(back[:, None], mix(c, top["shadow"], 0.4), c)
        c = mix(c, c * 1.12, smoothstep(0.3, 0.9, n[:, 2]) * 0.5)                    # lifted up-facing folds
        if zname in ("panel",):
            gold_edge = np.maximum(smoothstep(0.06, 0.03, u), smoothstep(0.94, 0.97, u)) * smoothstep(0.75, 0.55, v)
            gold_edge = np.maximum(gold_edge, smoothstep(0.035, 0.015, v))
            c = mix(c, C["gold"], gold_edge * 0.9)
        if zname == "tabard":
            tb = cc["tabard_veins"]
            x = p[:, 0]
            z = p[:, 2]
            d = np.abs(x) + np.where(z < tb["z"][0], 9.0, 0.0) + np.where(z > tb["z"][1], 9.0, 0.0)
            for bz in tb["branches"]:
                for sx in (1, -1):
                    d = np.minimum(d, _seg_dist(np.stack([x, z], 1), np.array([0.0, bz]), np.array([sx * tb["reach"], bz - tb["drop"]])))
            front = n[:, 1] < 0
            vein_g = smoothstep(tb["width"], tb["width"] * 0.4, d) * front
            c = mix(c, C["gold_hi"], vein_g * 0.85)
            c = mix(c, C["gold"], smoothstep(0.035, 0.015, v) * 0.9)
        base[m] = c * (1 + 0.05 * brush[m][:, None])
    # ---- EMISSIVE ZONES ----------------------------------------------------------------------------------------------
    m = zm("eye")
    if m.any():
        fwd = smoothstep(0.4, 0.95, -Nn[m, 1])
        eg = T["eye_glow"]
        ice = mix(T["collar_gem"]["hot"][None], eg["core"][None], 0.35)          # ice-blue, not white (the concept)
        c = mix(np.repeat(mix(T["collar_gem"]["rim"][None], ice, 0.5), m.sum(), 0), np.repeat(ice, m.sum(), 0), fwd)
        base[m] = c
        emis[m] = c * cfg["glow_gain"]["eye"]
    m = zm("gem")
    if m.any():
        gm = T["collar_gem"]
        f = np.abs((Nn[m] * np.array([0.3, -1.0, 0.4])).sum(1)) / 1.12
        c = mix(np.repeat(gm["rim"][None], m.sum(), 0), gm["hot"], smoothstep(0.2, 0.7, f))
        c = mix(c, gm["core"], smoothstep(0.75, 0.97, f))
        base[m] = c
        emis[m] = c * cfg["glow_gain"]["gem"]
    m = zm("crystal")
    if m.any():
        cr = T["collar_gem"]
        c = mix(np.repeat(cr["hot"][None], m.sum(), 0), cr["core"], smoothstep(0.4, 0.95, MR[m]))
        c = mix(c, np.ones(3, dtype=np.float32), smoothstep(0.85, 1.0, MR[m]) * 0.35)
        base[m] = c
        emis[m] = c * cfg["glow_gain"]["crystal"] * (0.55 + 0.45 * MR[m][:, None])
    m = zm("claw")
    if m.any():
        cw = T["lightning_veins"]
        c = mix(np.repeat(cw["hot"][None], m.sum(), 0), cw["core"], smoothstep(0.3, 0.9, MR[m]))
        base[m] = c
        emis[m] = c * cfg["glow_gain"]["claw"]

    # ---- AO folded in as darker painted planes (never on emissive zones) ---------------------------------------------
    ao = cfg.get("ao", {})
    skip = zm("eye", "gem", "crystal", "claw")
    if "self" in ao and "ao_self" in maps:
        a = ao["self"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_self"]))
        base = base * np.where(skip, 1.0, f)[:, None]
    if "hi" in ao and "ao_hi" in maps and "hi_w" in maps:
        a = ao["hi"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_hi"])) * maps["hi_w"]
        base = base * np.where(skip, 1.0, f)[:, None]
    if "cav" in maps:
        base = base * (1 - 0.18 * smoothstep(0.62, 0.95, maps["cav"]))[:, None]
    # ---- the vein / slot glow into the emissive map ------------------------------------------------------------------
    lv = T["lightning_veins"]
    gcol = mix(np.repeat(lv["rim"][None], N, 0), lv["hot"], smoothstep(0.2, 0.7, glow_line))
    gcol = mix(gcol, lv["core"], smoothstep(0.7, 1.0, glow_line))
    e_line = np.maximum(glow_line, glow_halo * 0.3) * cfg["glow_gain"]["veins"]
    emis = np.maximum(emis, gcol * e_line[:, None])
    base = np.clip(base * (1 + 0.02 * fine[:, None]), 0, 1)
    lit = (emis.max(1) > 0.25)
    log("painted: emissive texels %d (%.2f %% of the atlas texels), vein/slot line texels %d" % (
        int(lit.sum()), 100.0 * float(lit.mean()), int((glow_line > 0.5).sum())))
    return base, np.clip(emis, 0, 1)
