"""Procedural hand-painted NPR textures for the stage-2 hero (numpy only; driven by s2_texture.py).

Input: per-texel maps baked from the production mesh into its UV atlas - world position, world normal,
paint zone, object index, coverage - plus (optionally) the sculpt's concavity transferred onto the body.
Output: an sRGB base-colour atlas and an sRGB emissive atlas.

Painting rules (art/characters/brax/brief.md sections 4 and 6, palette.json):
  * flat painted value planes from the measured palette (shadow / base / highlight tones); no light
    direction, no ambient occlusion - the in-game toon shader does the lighting;
  * form comes from the tangent-space normal map (baked from the sculpt) through the game's toon bands; the
    paint adds art-directed cues only: top faces of the gauntlet rock lifted toward the highlight tone (they
    face the 55-degree camera), a painted highlight band on bronze, the sculpt's cavity and AO folded in as
    darker planes (polish pass 2026-09-25), darker hems, value planes on hair and beard;
  * brush variation is low-frequency value noise (+-4 %), never grunge (reads as mud at 6-8 % screen height);
  * emissive is a separate map: lava seams, joints and plate feet on the gauntlets, the chest sigil (bold
    ring, vertical bar, radiating rays, white-hot centre lines), a domain-warped lava crack network over the
    chest, shoulders, forearms and back with a soft halo band that feeds bloom, the spine crack, the eyes.
    Heat / Meltdown scale it at runtime.
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
        c = mix(np.repeat(sk["base"][None], m.sum(), 0), sk["highlight"], np.clip(brush[m] * 0.35 + 0.1, 0, 1) * 0.3)
        c = mix(c, sk["shadow"], np.clip(-brush[m], 0, 1) * 0.2 + cfg.get("skin_depth", 0.0))
        warm = np.array([0.72, 0.36, 0.25], dtype=np.float32)
        head = smoothstep(1.95, 2.0, p[:, 2])
        c = mix(c, warm, head * np.clip(fbm(p, 14.0, 2, seed=9) - 0.35, 0, 1) * 0.35)
        # the sculpt's creases folded into the paint as darker skin planes (form comes from the normal map)
        cv_cfg = cfg.get("cavity")
        if "cav" in maps and cv_cfg:
            cav = maps["cav"][m]
            c = mix(c, sk["shadow"] * 0.85, smoothstep(cv_cfg["range"][0], cv_cfg["range"][1], cav) * cv_cfg["strength"])
        soot = smoothstep(0.82, 0.87, fbm(p, 55.0, 2, seed=21)) * smoothstep(1.55, 1.7, p[:, 2])
        c = mix(c, np.array([0.30, 0.16, 0.12], dtype=np.float32), soot * 0.25)
        # painted brows: a heavy dark shape above each eye, thick at the inner end
        ez = cfg["eye_z"]
        ax = np.abs(p[:, 0])
        brow_top = ez + 0.03 - (ax - 0.012) * 0.16
        brow = ((p[:, 2] > ez + 0.008) & (p[:, 2] < brow_top) & (ax > 0.006) & (ax < 0.06) & (n[:, 1] < -0.3)).astype(np.float32)
        brow *= smoothstep(0.3, 0.5, fbm(p, 120.0, 1, seed=31) + 0.4)
        c = mix(c, T["hair_beard"]["base"], brow * 0.95)
        for sx in (1, -1):
            e = np.array([sx * cfg["eye_x"], cfg["eye_y"], ez])
            d = np.linalg.norm((p - e) * [1.0, 0.6, 1.4], axis=1)
            c = mix(c, sk["shadow"] * 0.65, smoothstep(0.032, 0.012, d) * 0.65)
        lip = ((np.abs(p[:, 2] - cfg["mouth_z"]) < 0.01) & (np.abs(p[:, 0]) < 0.034) & (n[:, 1] < -0.3)).astype(np.float32)
        c = mix(c, np.array([0.45, 0.22, 0.17], dtype=np.float32), lip * 0.6)
        mo = cfg.get("mouth")
        if mo:
            inside = ((p[:, 1] > mo["y_inner"] + 0.001) & (np.abs(p[:, 0]) < mo["half_w"] * 1.15)
                      & (np.abs(p[:, 2] - mo["slit_z"]) < 0.016)).astype(np.float32)
            c = mix(c, np.array([0.20, 0.07, 0.06], dtype=np.float32), inside)
        base[m] = c

        # -- glow: chest sigil, lava crack network (chest, shoulders, forearms, back), spine crack ----------------
        core = np.zeros(m.sum(), dtype=np.float32)       # the bright crack
        hot = np.zeros(m.sum(), dtype=np.float32)        # its white-hot centre line
        halo = np.zeros(m.sum(), dtype=np.float32)       # the soft glow band around it (feeds bloom)

        def add(dist, width, weight, hotness=0.35, halo_mult=3.0, halo_w=1.0):
            nonlocal core, hot, halo
            core = np.maximum(core, smoothstep(width, width * 0.35, dist) * weight)
            hot = np.maximum(hot, smoothstep(width * hotness, width * hotness * 0.3, dist) * weight)
            halo = np.maximum(halo, smoothstep(width * halo_mult, width, dist) * weight * halo_w)

        sg = cfg["sigil"]
        front = smoothstep(-0.15, -0.45, n[:, 1])
        dx = p[:, 0]
        dz = p[:, 2] - sg["centre_z"]
        r = np.sqrt(dx * dx + dz * dz)
        add(np.abs(r - sg["radius"]), sg["width"], front, sg["hot"], sg["halo"])
        add(np.where((p[:, 2] > sg["line_z"][0]) & (p[:, 2] < sg["line_z"][1]), np.abs(dx), 9.0), sg["width"] * 0.85, front,
            sg["hot"], sg["halo"])
        rays = sg.get("rays")
        if rays:
            for k in range(rays["count"]):
                a = (k + 0.5) * 2 * np.pi / rays["count"]
                u = dx * np.cos(a) + dz * np.sin(a)
                v = np.abs(-dx * np.sin(a) + dz * np.cos(a))
                t = np.clip((u - rays["inner"]) / (rays["outer"] - rays["inner"]), 0, 1)
                seg = np.where((u > rays["inner"]) & (u < rays["outer"]), v / np.maximum(1 - 0.7 * t, 0.2), 9.0)
                add(seg, rays["width"], front, 0.3, 2.6, 0.7)
        # the crack network: domain-warped Voronoi edges, gated into patches, thicker near the sigil
        nc = cfg.get("network")
        if nc:
            w = nc["warp"]
            q = p + (np.stack([fbm(p, 7.0, 2, seed=211), fbm(p, 7.0, 2, seed=223), fbm(p, 7.0, 2, seed=227)], 1) - 0.5) * w
            _, edge, _ = voronoi(q, nc["freq"], seed=229)
            dnet = edge / (2 * nc["freq"])
            gate = smoothstep(nc["gate"][0], nc["gate"][1], fbm(p, 4.5, 2, seed=231))
            near = np.sqrt((p[:, 0] / 0.3) ** 2 + ((p[:, 2] - sg["centre_z"]) / 0.24) ** 2)
            prox = smoothstep(1.3, 0.35, near) * front
            for rg in nc["regions"]:
                box = (smoothstep(rg["z"][0] - 0.02, rg["z"][0] + 0.02, p[:, 2]) * (1 - smoothstep(rg["z"][1] - 0.02, rg["z"][1] + 0.02, p[:, 2]))
                       * smoothstep(rg["abs_x"][0] - 0.02, rg["abs_x"][0] + 0.02, ax) * (1 - smoothstep(rg["abs_x"][1] - 0.02, rg["abs_x"][1] + 0.02, ax)))
                if rg["abs_x"][0] <= 0.0:
                    box = (smoothstep(rg["z"][0] - 0.02, rg["z"][0] + 0.02, p[:, 2]) * (1 - smoothstep(rg["z"][1] - 0.02, rg["z"][1] + 0.02, p[:, 2]))
                           * (1 - smoothstep(rg["abs_x"][1] - 0.02, rg["abs_x"][1] + 0.02, ax)))
                face = {"front": front, "back": smoothstep(0.1, 0.4, n[:, 1]), "up": smoothstep(-0.5, 0.15, n[:, 2]),
                        "any": np.ones_like(front)}[rg["facing"]]
                g0 = smoothstep(rg["gate"][0], rg["gate"][1], fbm(p, 4.5, 2, seed=231)) if "gate" in rg else gate
                g = np.maximum(g0, prox * rg.get("near_gate", 0.0))
                width = rg["width"][1] + (rg["width"][0] - rg["width"][1]) * prox
                add(dnet, width, box * face * g * rg.get("strength", 1.0), 0.3, 2.6, nc.get("halo_w", 0.3))
        # the deepest anatomy creases of the sculpt glow where they cross the chest (abs and pec lines)
        if "cav" in maps and cv_cfg and cv_cfg.get("glow_range"):
            cav = maps["cav"][m]
            zr = cv_cfg["glow_region_z"]
            reg = front * smoothstep(zr[0] - 0.02, zr[0] + 0.02, p[:, 2]) * (1 - smoothstep(zr[1] - 0.02, zr[1] + 0.02, p[:, 2])) * (ax < 0.3)
            gl = smoothstep(cv_cfg["glow_range"][0], cv_cfg["glow_range"][1], cav) * reg
            core = np.maximum(core, gl * 0.8)
            halo = np.maximum(halo, smoothstep(cv_cfg["glow_range"][0] - 0.06, cv_cfg["glow_range"][0], cav) * reg * 0.25)
        sp = cfg.get("spine")
        if sp:
            back = smoothstep(0.1, 0.45, n[:, 1])
            wob = np.sin(p[:, 2] * 38.0) * sp["wobble"] + np.sin(p[:, 2] * 97.0) * sp["wobble"] * 0.4
            d_sp = np.where((p[:, 2] > sp["z"][0]) & (p[:, 2] < sp["z"][1]), np.abs(p[:, 0] - wob), 9.0)
            for bz, bl, bd in ((sp["branch_z"], sp["branch_len"], sp["branch_drop"]), (sp["branch_z"] - 0.12, sp["branch_len"] * 0.8, sp["branch_drop"] * 0.6)):
                for sx in (1, -1):
                    a = np.array([0.0, bz])
                    b = np.array([sx * bl, bz + bd])
                    qq = np.stack([p[:, 0], p[:, 2]], 1)
                    t = np.clip(((qq - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
                    proj = a + t[:, None] * (b - a)
                    d_b = np.linalg.norm(qq - proj, axis=1)
                    d_sp = np.minimum(d_sp, np.where(t < 0.999, d_b / (1.0 - 0.55 * t), 9.0))
            add(d_sp, sp["width"], back, 0.35, 3.0, 0.7)
        burnt = np.array([0.30, 0.12, 0.07], dtype=np.float32)
        base[m] = mix(base[m], burnt, halo * 0.6)
        base[m] = mix(base[m], lava["hot"], core)
        base[m] = mix(base[m], lava["core"], hot)
        glow = mix(lava["rim"][None] * 0.9, lava["hot"], core)
        glow = mix(glow, lava["core"], hot)
        emis[m] = glow * np.maximum(core, halo * cfg.get("halo_emission", 0.3))[:, None]
    # -- hair / beard: painted value planes (a light plane on top, a dark plane underneath, lighter tips) ----------
    for zn in ("hair", "beard"):
        m = zm(zn)
        if not m.any():
            continue
        p, n = P[m], Nn[m]
        hb = T["hair_beard"]
        L = np.array([0.0, -0.35, 0.94] if zn == "hair" else [0.0, -0.8, 0.6], dtype=np.float32)
        L /= np.linalg.norm(L)
        ndl = n @ L
        c = np.repeat(hb["shadow"][None], m.sum(), 0)
        c = mix(c, hb["base"], smoothstep(-0.2, -0.08, ndl))
        c = mix(c, hb["highlight"], smoothstep(0.48, 0.56, ndl) * 0.9)
        if "mask" in maps:
            c = mix(c, hb["highlight"], smoothstep(0.78, 0.96, maps["mask"][m]) * 0.45)
        comb = np.tile(np.array([[0.0, 0.45, 1.0]] if zn == "hair" else [[0.0, 0.0, -1.0]], dtype=np.float32), (m.sum(), 1))
        comb = comb - n * (comb * n).sum(1, keepdims=True)
        st = anisotropic(p, comb, 160.0, 20.0, seed=51 if zn == "hair" else 53)
        base[m] = c * (1 + 0.12 * (st[:, None] - 0.5))
    # -- teeth (the grin) ----------------------------------------------------------------------------------
    m = zm("teeth") if "teeth" in zones else np.zeros(N, bool)
    if m.any():
        p = P[m]
        mo = cfg.get("mouth", {"slit_z": float(np.median(p[:, 2])), "half_w": 0.03})
        c = np.repeat(np.array([[0.90, 0.85, 0.76]], dtype=np.float32), m.sum(), 0)
        c = mix(c, np.array([0.35, 0.22, 0.2], dtype=np.float32), smoothstep(0.0016, 0.0005, np.abs(p[:, 2] - mo["slit_z"])))
        c = mix(c, np.array([0.55, 0.45, 0.4], dtype=np.float32), smoothstep(0.35, 0.05, np.abs(((p[:, 0] / 0.0075) % 1.0) - 0.5)) * 0.35)
        c = mix(c, np.array([0.3, 0.2, 0.18], dtype=np.float32), smoothstep(0.5, 1.0, np.abs(p[:, 0]) / mo["half_w"]) * 0.8)
        base[m] = c
    # -- eyes ------------------------------------------------------------------------------------------
    m = zm("eye")
    if m.any():
        n = Nn[m]
        ey = T["eye_glow"]
        fwd = smoothstep(0.55, 0.95, -n[:, 1])
        base[m] = mix(np.repeat(ey["hot"][None], m.sum(), 0), ey["core"], fwd)
        emis[m] = mix(np.repeat(ey["hot"][None], m.sum(), 0), ey["core"], fwd)
    # -- gauntlet rock: dark basalt chunks, per-plate tone, lit tops, glowing seams at the plate feet ---------
    m = zm("rock")
    if m.any():
        p, n = P[m], Nn[m]
        rk = T["gauntlet_rock"]
        pr = maps["prand"][m] if "prand" in maps else voronoi(p, 11.0, seed=61)[2]
        c = np.repeat(rk["base"][None], m.sum(), 0) * (0.85 + 0.3 * pr[:, None])
        c = mix(c, np.array([0.24, 0.2, 0.26], dtype=np.float32), (pr > 0.7).astype(np.float32)[:, None] * 0.25)   # cool purple-grey chunks
        c = mix(c, rk["highlight"], smoothstep(0.2, 0.85, n[:, 2]) * 0.22)         # top faces face the 55-deg camera
        mk = maps["mask"][m] if "mask" in maps else np.full(m.sum(), 0.5, dtype=np.float32)
        c = mix(c, rk["highlight"] * 1.1, (smoothstep(0.2, 0.3, mk) * smoothstep(0.8, 0.7, mk)) * 0.2)   # chamfers catch light
        c = mix(c, rk["shadow"], smoothstep(-0.2, -0.8, n[:, 2]) * 0.6)
        c = c * (1 + 0.05 * brush[m][:, None])
        # the lava light bleeds up the plate feet: the seams read thick and glowing at game size
        feet = smoothstep(cfg.get("rock_feet", 0.14), 0.0, mk)
        c = mix(c, lava["rim"] * 0.8, feet * 0.7)
        f1, edge, _ = voronoi(p, 26.0, seed=63)
        crack = smoothstep(0.045, 0.014, edge) * smoothstep(0.55, 0.66, fbm(p, 7.0, 2, seed=65)) * smoothstep(0.3, 0.6, mk)
        c = mix(c, lava["rim"] * 0.55, crack * 0.85)
        base[m] = c
        emis[m] = np.maximum(lava["rim"][None] * crack[:, None] * 0.65, mix(lava["rim"][None] * 0.5, lava["hot"], feet ** 2)[:, :] * feet[:, None] * 0.75)
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
    # AO folded into the painted colour: the assembled parts' own occlusion (under the belt, between plates),
    # and on the skin the sculpt's occlusion (muscle separations); stylised through a smoothstep
    ao = cfg.get("ao")
    if ao and "self" in ao and "ao_self" in maps:
        a = ao["self"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_self"]))
        f = np.where(np.isin(Z, [zones[z] for z in a["skip"] if z in zones]), 1.0, f)
        base = base * f[:, None]
    if ao and "hi" in ao and "ao_hi" in maps and "hi_w" in maps:
        a = ao["hi"]
        sk_ = (Z == zones["skin"]).astype(np.float32) * maps["hi_w"]
        f = 1 - a["strength"] * (1 - smoothstep(a["range"][0], a["range"][1], maps["ao_hi"])) * sk_
        base = base * f[:, None]
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
