"""Procedural hand-painted NPR textures for the stage-2 hero (numpy only; driven by s2_texture.py).

Input: per-texel maps baked from the production mesh into its UV atlas - world position, world normal,
paint zone, object index, coverage - plus (optionally) the sculpt's concavity transferred onto the body.
Output: an sRGB base-colour atlas and an sRGB emissive atlas.

Painting rules (art/characters/brax/brief.md sections 4 and 6, palette.json):
  * flat painted value planes from the measured palette (shadow / base / highlight tones); no light
    direction, no ambient occlusion - the in-game toon shader does the lighting;
  * the only "form" cues are art-directed: top faces of the gauntlet rock lifted toward the highlight tone
    (they face the 55-degree camera), a painted highlight band on bronze, dark ink lines in the deepest
    anatomy creases of the sculpt, darker hems;
  * brush variation is low-frequency value noise (+-4 %), never grunge (reads as mud at 6-8 % screen height);
  * emissive is a separate map: lava grooves and joints, fine lava cracks in the rock, the chest sigil
    (ring + vertical line), skin veins around the sigil, the eyes. Heat / Meltdown scale it at runtime.
"""
import numpy as np


def hex3(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


# ---- noise -------------------------------------------------------------------------------------------

def _hash(ix, iy, iz, seed=0):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = h & 0xFFFFFFFF
    h = (h ^ (h >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    h = (h ^ (h >> 16)) * 0x45D9F3B & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def value_noise(p, freq, seed=0):
    q = p * freq
    i = np.floor(q)
    f = q - i
    u = f * f * (3 - 2 * f)
    ix, iy, iz = i[:, 0], i[:, 1], i[:, 2]
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (u[:, 0] if dx else 1 - u[:, 0]) * (u[:, 1] if dy else 1 - u[:, 1]) * (u[:, 2] if dz else 1 - u[:, 2])
                out = out + w * _hash(ix + dx, iy + dy, iz + dz, seed)
    return out


def fbm(p, freq, octaves=3, seed=0):
    out = 0.0
    amp = 0.5
    tot = 0.0
    for o in range(octaves):
        out = out + amp * value_noise(p, freq * (2.0 ** o), seed + o * 17)
        tot += amp
        amp *= 0.5
    return out / tot


def voronoi(p, freq, seed=0, jitter=0.9):
    """F1 distance, edge distance (F2 - F1, both in cell units) and a cell hash."""
    q = p * freq
    i = np.floor(q)
    f1 = np.full(len(q), 9.0, dtype=np.float32)
    f2 = np.full(len(q), 9.0, dtype=np.float32)
    cid = np.zeros(len(q), dtype=np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cx, cy, cz = i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz
                fx = cx + 0.5 + (_hash(cx, cy, cz, seed) - 0.5) * jitter
                fy = cy + 0.5 + (_hash(cx, cy, cz, seed + 1) - 0.5) * jitter
                fz = cz + 0.5 + (_hash(cx, cy, cz, seed + 2) - 0.5) * jitter
                d = np.sqrt((q[:, 0] - fx) ** 2 + (q[:, 1] - fy) ** 2 + (q[:, 2] - fz) ** 2).astype(np.float32)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                cid = np.where(closer, _hash(cx, cy, cz, seed + 3), cid)
                f1 = np.where(closer, d, f1)
    return f1, f2 - f1, cid


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    t = np.asarray(t, dtype=np.float32)
    if t.ndim == 1:
        t = t[:, None]
    return a * (1 - t) + b * t


def anisotropic(p, direction, f_across, f_along, seed=0):
    """Noise stretched along `direction` (per-texel unit vectors): streaks for hair and cloth."""
    d = direction / (np.linalg.norm(direction, axis=1, keepdims=True) + 1e-9)
    along = (p * d).sum(1, keepdims=True)
    q = (p - d * along) * f_across + d * along * f_along
    return value_noise(q, 1.0, seed) * 0.65 + value_noise(q * 2.3 + 11.0, 1.0, seed + 5) * 0.35


# Greek-key band (1 = gold), 12x12 tile, repeated along the sash tails
_KEY = np.array([[int(c) for c in row] for row in (
    "111111111111",
    "100000000001",
    "101111111101",
    "101000000101",
    "101011110101",
    "101010010101",
    "101010110101",
    "101010000101",
    "101011111101",
    "101000000001",
    "101111111111",
    "100000000000")], dtype=np.float32)


def greek_key(u, v):
    iu = (np.floor(u * 12).astype(np.int64)) % 12
    iv = (np.floor(v * 12).astype(np.int64)) % 12
    return _KEY[iv, iu]


# ---- the painter --------------------------------------------------------------------------------------

def paint(maps, zones, pal, cfg, log=print):
    """maps: dict of flat arrays over covered texels: pos (N,3), nrm (N,3), zone (N,), obj (N,), cav (N,) optional.
    Returns base (N,3) and emissive (N,3), sRGB 0..1."""
    P, Nn, Z, O = maps["pos"], maps["nrm"], maps["zone"], maps["obj"]
    N = len(P)
    base = np.zeros((N, 3), dtype=np.float32)
    emis = np.zeros((N, 3), dtype=np.float32)
    T = {k: {t: hex3(h) for t, h in v.items()} for k, v in pal.items()}
    lava = T["lava_glow"]
    brush = (fbm(P, 6.0, 3, seed=1) - 0.5) * 2          # -1..1, low frequency
    fine = (fbm(P, 38.0, 2, seed=2) - 0.5) * 2

    def zm(name):
        return Z == zones[name]

    # -- skin -----------------------------------------------------------------------------------------
    m = zm("skin")
    if m.any():
        p, n = P[m], Nn[m]
        sk = T["skin"]
        c = mix(np.repeat(sk["base"][None], m.sum(), 0), sk["highlight"], np.clip(brush[m] * 0.35 + 0.1, 0, 1) * 0.5)
        c = mix(c, sk["shadow"], np.clip(-brush[m], 0, 1) * 0.25)
        # warmer flush on cheeks/nose/ears/knuckle-like extremities: redder where the surface is thin
        warm = np.array([0.72, 0.36, 0.25], dtype=np.float32)
        head = smoothstep(1.95, 2.0, p[:, 2])
        c = mix(c, warm, head * np.clip(fbm(p, 14.0, 2, seed=9) - 0.35, 0, 1) * 0.35)
        # ink lines in the sculpt's deepest creases (abs, pecs, deltoids, knees) - painted anatomy
        if "cav" in maps:
            cav = maps["cav"][m]
            # only where the body follows the sculpt (the sculpt's forearms/hands are gauntlet rock)
            ex = cfg.get("cav_exclude_arms_abs_x")
            if ex:
                cav = cav * (1 - smoothstep(ex - 0.04, ex, np.abs(p[:, 0])) * (p[:, 2] > 1.45))
            line = smoothstep(cfg["cav_line"][0], cfg["cav_line"][1], cav)
            c = mix(c, sk["shadow"] * 0.78, line * 0.85)
        # soot flecks on the arms and shoulders
        soot = smoothstep(0.8, 0.85, fbm(p, 55.0, 2, seed=21)) * smoothstep(1.55, 1.7, p[:, 2])
        c = mix(c, np.array([0.30, 0.16, 0.12], dtype=np.float32), soot * 0.3)
        # painted brows: a heavy dark shape above each eye
        ez = cfg["eye_z"]
        ax = np.abs(p[:, 0])
        brow_top = ez + 0.024 - (ax - 0.012) * 0.12
        brow = ((p[:, 2] > ez + 0.009) & (p[:, 2] < brow_top) & (ax > 0.008) & (ax < 0.058) & (n[:, 1] < -0.3)).astype(np.float32)
        brow *= smoothstep(0.3, 0.5, fbm(p, 120.0, 1, seed=31) + 0.35)
        c = mix(c, T["hair_beard"]["base"], brow * 0.95)
        # eye sockets: a darker painted plane around the glowing eyes
        for sx in (1, -1):
            e = np.array([sx * cfg["eye_x"], cfg["eye_y"], ez])
            d = np.linalg.norm((p - e) * [1.0, 0.6, 1.4], axis=1)
            c = mix(c, sk["shadow"] * 0.7, smoothstep(0.03, 0.012, d) * 0.6)
        # lips a touch darker and redder
        lip = ((np.abs(p[:, 2] - cfg["mouth_z"]) < 0.009) & (np.abs(p[:, 0]) < 0.03) & (n[:, 1] < -0.3)).astype(np.float32)
        c = mix(c, np.array([0.45, 0.22, 0.17], dtype=np.float32), lip * 0.6)
        base[m] = c
        # -- chest sigil: ring + vertical line (emissive, burnt rim on the base colour) --------------------
        sg = cfg["sigil"]
        front = smoothstep(-0.15, -0.45, n[:, 1])
        dx = p[:, 0]
        dz = p[:, 2] - sg["centre_z"]
        r = np.sqrt(dx * dx + dz * dz)
        ring = np.abs(r - sg["radius"])
        line = np.where((p[:, 2] > sg["line_z"][0]) & (p[:, 2] < sg["line_z"][1]), np.abs(dx), 9.0)
        dist = np.minimum(ring, line)
        rays = sg.get("rays")
        if rays:
            ang = np.arctan2(dz, dx)
            for k in range(rays["count"]):
                a = k * 2 * np.pi / rays["count"]
                if abs(np.cos(a)) < 1e-3:
                    continue                                   # the vertical line already covers these
                u = dx * np.cos(a) + dz * np.sin(a)
                v = np.abs(-dx * np.sin(a) + dz * np.cos(a))
                seg = np.where((u > rays["inner"]) & (u < rays["outer"]), v * sg["width"] / rays["width"], 9.0)
                dist = np.minimum(dist, seg)
        core = smoothstep(sg["width"], sg["width"] * 0.35, dist) * front
        halo = smoothstep(sg["width"] * 3.2, sg["width"], dist) * front
        base[m] = mix(base[m], np.array([0.30, 0.12, 0.07], dtype=np.float32), halo * 0.7)
        base[m] = mix(base[m], lava["hot"], core)
        em = mix(lava["rim"] * 0.6, lava["core"], core)
        # skin veins: thin cracks spreading from the sigil over chest and shoulders, fading with distance
        f1, edge, _ = voronoi(p, 34.0, seed=41)
        near = np.sqrt((p[:, 0] / 0.35) ** 2 + ((p[:, 2] - sg["centre_z"]) / 0.26) ** 2)
        vein = smoothstep(0.07, 0.02, edge) * smoothstep(1.0, 0.25, near) * smoothstep(0.45, 0.6, fbm(p, 9.0, 2, seed=43))
        vein *= smoothstep(1.45, 1.55, p[:, 2]) * (1 - smoothstep(1.9, 1.95, p[:, 2]))
        base[m] = mix(base[m], lava["rim"] * 0.75, vein * 0.8)
        emis[m] = np.maximum(em * np.maximum(core, halo * 0.25)[:, None], lava["rim"] * vein[:, None] * 0.85)
        # back: a glowing crack down the spine from the nape to the belt, branching across the shoulder blades
        sp = cfg.get("spine")
        if sp:
            back = smoothstep(0.1, 0.45, n[:, 1])
            wob = np.sin(p[:, 2] * 38.0) * sp["wobble"] + np.sin(p[:, 2] * 97.0) * sp["wobble"] * 0.4
            d_sp = np.where((p[:, 2] > sp["z"][0]) & (p[:, 2] < sp["z"][1]), np.abs(p[:, 0] - wob), 9.0)
            for bz, bl, bd in ((sp["branch_z"], sp["branch_len"], sp["branch_drop"]), (sp["branch_z"] - 0.12, sp["branch_len"] * 0.8, sp["branch_drop"] * 0.6)):
                for sx in (1, -1):
                    a = np.array([0.0, bz])
                    b = np.array([sx * bl, bz + bd])
                    q = np.stack([p[:, 0], p[:, 2]], 1)
                    t = np.clip(((q - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
                    proj = a + t[:, None] * (b - a)
                    zig = np.sin(t * 23.0 + sx) * 0.006
                    d_b = np.linalg.norm(q - proj, axis=1) + np.abs(zig) * 0.3
                    d_sp = np.minimum(d_sp, np.where(t < 0.999, d_b / (1.0 - 0.55 * t), 9.0))
            sc_ = smoothstep(sp["width"], sp["width"] * 0.3, d_sp) * back
            sh_ = smoothstep(sp["width"] * 3.0, sp["width"], d_sp) * back
            base[m] = mix(base[m], np.array([0.30, 0.12, 0.07], dtype=np.float32), sh_ * 0.6)
            base[m] = mix(base[m], lava["hot"], sc_)
            emis[m] = np.maximum(emis[m], mix(lava["rim"][None] * 0.6, lava["core"], sc_)[:, :] * np.maximum(sc_, sh_ * 0.25)[:, None])
        # lava cracks running down the forearms to the backs of the hands (his identity without the gauntlets)
        ac = cfg.get("arm_cracks")
        if ac:
            _, aedge, _ = voronoi(p, ac["freq"], seed=47)
            reach = smoothstep(ac["abs_x"][0], ac["abs_x"][1], np.abs(p[:, 0])) * (p[:, 2] > 1.5)
            patch = smoothstep(ac["patch"][0], ac["patch"][1], fbm(p, 6.0, 2, seed=49))
            back = smoothstep(-0.4, 0.3, n[:, 2])        # mostly on the top/outside of the arm (faces the camera)
            crack = smoothstep(ac["width"], ac["width"] * 0.3, aedge) * reach * np.maximum(patch, 0.35) * back
            base[m] = mix(base[m], lava["rim"] * 0.7, crack * 0.85)
            emis[m] = np.maximum(emis[m], mix(lava["rim"][None] * 0.7, lava["hot"], smoothstep(ac["width"] * 0.6, 0.0, aedge))[:, :] * (crack * ac["strength"])[:, None])
    # -- hair / beard ------------------------------------------------------------------------------------
    for zn in ("hair", "beard"):
        m = zm(zn)
        if not m.any():
            continue
        p, n = P[m], Nn[m]
        hb = T["hair_beard"]
        comb = np.tile(np.array([[0.0, 0.45, 1.0]], dtype=np.float32), (m.sum(), 1)) if zn == "hair" else \
            np.tile(np.array([[0.0, 0.0, -1.0]], dtype=np.float32), (m.sum(), 1))
        comb = comb - n * (comb * n).sum(1, keepdims=True)
        st = anisotropic(p, comb, 260.0, 30.0, seed=51 if zn == "hair" else 53)
        c = mix(np.repeat(hb["base"][None], m.sum(), 0), hb["highlight"], smoothstep(0.55, 0.85, st) * 0.8)
        c = mix(c, hb["shadow"], smoothstep(0.45, 0.2, st) * 0.6)
        base[m] = c
    # -- eyes ------------------------------------------------------------------------------------------
    m = zm("eye")
    if m.any():
        n = Nn[m]
        ey = T["eye_glow"]
        fwd = smoothstep(0.55, 0.95, -n[:, 1])
        base[m] = mix(np.repeat(ey["hot"][None], m.sum(), 0), ey["core"], fwd)
        emis[m] = mix(np.repeat(ey["hot"][None], m.sum(), 0), ey["core"], fwd)
    # -- gauntlet rock ---------------------------------------------------------------------------------
    m = zm("rock")
    if m.any():
        p, n = P[m], Nn[m]
        rk = T["gauntlet_rock"]
        _, _, cid = voronoi(p, 11.0, seed=61)
        c = np.repeat(rk["base"][None], m.sum(), 0) * (0.9 + 0.2 * cid[:, None])
        c = mix(c, rk["highlight"], smoothstep(0.15, 0.85, n[:, 2]) * 0.35)      # top faces face the 55-deg camera
        if "mask" in maps:
            mk = maps["mask"][m]
            bevel = smoothstep(0.1, 0.25, mk) * smoothstep(0.75, 0.5, mk)          # plate chamfers catch a little light
            c = mix(c, rk["highlight"], bevel * 0.35)
        c = mix(c, rk["shadow"], smoothstep(-0.2, -0.8, n[:, 2]) * 0.6)
        c = c * (1 + 0.05 * brush[m][:, None])
        # fine lava cracks in patches (hand block, fingers, plate faces)
        f1, edge, _ = voronoi(p, 30.0, seed=63)
        crack = smoothstep(0.04, 0.012, edge) * smoothstep(0.6, 0.7, fbm(p, 7.0, 2, seed=65))
        c = mix(c, lava["rim"] * 0.5, crack * 0.8)
        base[m] = c
        emis[m] = lava["rim"][None] * crack[:, None] * 0.55
    # -- lava (core under the plates, finger joints) -----------------------------------------------------
    m = zm("lava")
    if m.any():
        p = P[m]
        t = fbm(p, 14.0, 3, seed=71)
        base[m] = mix(np.repeat(lava["hot"][None], m.sum(), 0), lava["core"], smoothstep(0.45, 0.75, t) * 0.6)
        emis[m] = mix(mix(np.repeat(lava["rim"][None], m.sum(), 0), lava["hot"], smoothstep(0.3, 0.55, t)), lava["core"], smoothstep(0.6, 0.8, t))
    # -- bronze (rings, cog, buckle) ---------------------------------------------------------------------
    m = zm("bronze")
    if m.any():
        p, n = P[m], Nn[m]
        br = T["bronze"]
        c = np.repeat(br["base"][None], m.sum(), 0) * (1 + 0.05 * brush[m][:, None])
        c = mix(c, br["shadow"], 0.25)
        c = mix(c, br["highlight"], smoothstep(0.45, 0.85, n[:, 2]) * 0.55)      # painted highlight band
        c = mix(c, br["shadow"] * 0.8, smoothstep(-0.2, -0.7, n[:, 2]) * 0.7)
        # worn edges: slightly lighter streaks
        c = mix(c, br["highlight"], smoothstep(0.62, 0.75, fbm(p, 40.0, 2, seed=81)) * 0.35)
        base[m] = c
    # -- skirt plates -----------------------------------------------------------------------------------
    m = zm("plates")
    if m.any():
        p, n = P[m], Nn[m]
        pl = T["scale_plates"]
        _, _, cid = voronoi(p, 10.0, seed=91)
        c = mix(np.repeat(pl["base"][None], m.sum(), 0), pl["highlight"], 0.25) * (0.92 + 0.16 * cid[:, None])
        mk = maps["mask"][m] if "mask" in maps else np.full(m.sum(), 0.5, dtype=np.float32)
        c = mix(pl["shadow"][None] * 0.45, c, smoothstep(0.05, 0.42, mk))                 # deep painted outline
        c = mix(c, pl["highlight"] * 1.12, smoothstep(0.55, 0.95, mk) * 0.9)             # golden centre ridge
        c = mix(c, pl["highlight"], smoothstep(0.7, 0.82, fbm(p, 30.0, 2, seed=93)) * 0.2)
        c = mix(c, pl["shadow"], smoothstep(-0.1, -0.6, n[:, 2]) * 0.6)
        base[m] = c
    # -- belt leather with bronze rivets -----------------------------------------------------------------
    m = zm("leather")
    if m.any():
        p = P[m]
        lt = T["belt_leather"]
        ang = np.arctan2(p[:, 0], -(p[:, 1] - cfg["axis_y"]))
        rv = np.abs(((ang / (2 * np.pi)) * cfg["belt_rivets"]) % 1.0 - 0.5) * 2 * np.pi * 0.25
        rz = np.abs(p[:, 2] - cfg["belt_mid_z"])
        rivet = smoothstep(0.009, 0.005, np.sqrt((rv * 0.5) ** 2 + rz ** 2)) * (np.abs(ang) > 0.35)
        c = mix(np.repeat(lt["base"][None], m.sum(), 0), lt["highlight"], smoothstep(0.6, 0.85, anisotropic(p, np.tile([[1.0, 0, 0]], (m.sum(), 1)), 30, 200, seed=101)) * 0.5)
        c = mix(c, T["bronze"]["highlight"], rivet)
        base[m] = c
    # -- torn cloth ------------------------------------------------------------------------------------
    m = zm("cloth")
    if m.any():
        p = P[m]
        cl = T["torn_cloth"]
        st = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 90.0, 8.0, seed=111)
        c = mix(np.repeat(cl["base"][None], m.sum(), 0), cl["highlight"], smoothstep(0.55, 0.8, st) * 0.7)
        c = mix(c, cl["shadow"], smoothstep(0.4, 0.2, st) * 0.6)
        c = mix(c, cl["shadow"] * 0.8, smoothstep(0.84, 0.74, p[:, 2]) * 0.6)      # darker, frayed hem
        base[m] = c
    # -- teal sash with the gold key band on the tails ------------------------------------------------------
    m = zm("sash")
    if m.any():
        p, n = P[m], Nn[m]
        ts = T["teal_sash"]
        st = anisotropic(p, np.tile([[0.0, 0.0, 1.0]], (m.sum(), 1)), 70.0, 9.0, seed=121)
        c = mix(np.repeat(ts["base"][None], m.sum(), 0), ts["highlight"], smoothstep(0.55, 0.8, st) * 0.8)
        c = mix(c, ts["shadow"], smoothstep(0.42, 0.2, st) * 0.7)
        sk = cfg["sash_key"]
        u = (p[:, 0] - sk["x0"]) / sk["cell"]
        v = p[:, 2] / sk["cell"]
        band = ((p[:, 2] < sk["z_top"]) & (p[:, 2] > sk["z_bottom"]) & (np.abs(p[:, 0] - sk["x_centre"]) < sk["half_width"])
                & (n[:, 1] < -0.2)).astype(np.float32)
        key = greek_key(u, v) * band
        edge_line = band * (np.abs(np.abs(p[:, 0] - sk["x_centre"]) - sk["half_width"] + 0.004) < 0.0035)
        gold = np.clip(key + edge_line, 0, 1)
        c = mix(c, T["gold_pattern"]["base"], gold * 0.9)
        base[m] = c
    # -- ankle wraps: criss-cross teal bands over linen --------------------------------------------------
    m = zm("wraps")
    if m.any():
        p = P[m]
        wr, ln = T["ankle_wraps"], T["wrap_linen"]
        sd = np.sign(p[:, 0])
        phi = np.arctan2(p[:, 1] - cfg["leg_axis_y"], (p[:, 0] - sd * cfg["leg_axis_x"]) * sd) / (2 * np.pi)
        a = (p[:, 2] / cfg["wrap_pitch"] + phi * 2.0) % 1.0
        b = (p[:, 2] / cfg["wrap_pitch"] - phi * 2.0) % 1.0
        band = np.maximum(smoothstep(0.0, 0.06, a) * smoothstep(0.7, 0.62, a), smoothstep(0.0, 0.06, b) * smoothstep(0.7, 0.62, b))
        c = mix(np.repeat(ln["base"][None], m.sum(), 0), wr["base"], band)
        edge = np.maximum(smoothstep(0.1, 0.0, np.abs(a - 0.66)), smoothstep(0.1, 0.0, np.abs(b - 0.66)))
        c = mix(c, wr["shadow"], edge * 0.6)
        c = c * (1 + 0.05 * brush[m][:, None])
        base[m] = c
    # -- linen (unused zone, kept for repaints) -----------------------------------------------------------
    m = zm("linen")
    if m.any():
        base[m] = T["wrap_linen"]["base"]
    # every zone gets the same faint brush variation on top
    base = np.clip(base * (1 + 0.025 * fine[:, None]), 0, 1)
    return base, np.clip(emis, 0, 1)


def dilate(img, valid, iters=16):
    """Grow painted texels into the empty gutter (so mips and bilinear filtering never pick up black)."""
    img = img.copy()
    v = valid.copy()
    for _ in range(iters):
        acc = np.zeros_like(img)
        cnt = np.zeros(v.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            sv = np.roll(np.roll(v, dy, 0), dx, 1)
            si = np.roll(np.roll(img, dy, 0), dx, 1)
            acc += si * sv[..., None]
            cnt += sv
        grow = (~v) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        v = v | grow
    return img
