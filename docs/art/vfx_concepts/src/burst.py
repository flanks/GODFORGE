"""Frame-parameterised layered burst (60 fps): the anatomy of an impact."""
import math
import numpy as np
import fx
from vfxpaint import H_ISO, K_ISO, hx, up, star, blob_field, ring


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def burst(cv, c, Rm, ppm, f, ramp, seed=11, smoke_ramp=None, spill=hx("#FFD9A0"), scorch_col=None, n_spikes=7,
          spark_n=8, shard_n=7, shard_dark=None, dust=(hx("#2B1E15"), hx("#7A5E44")), crown=7, flash=True,
          ink_gain=1.0, core_lift=0.5):
    rng = np.random.default_rng(seed)
    smoke_ramp = ramp if smoke_ramp is None else smoke_ramp
    Rx = Rm * ppm
    core = up(c, core_lift, ppm)
    a0 = rng.uniform(0, 6.28)
    spikes = []
    for i in range(n_spikes):
        a = a0 + 2 * math.pi * i / n_spikes + rng.uniform(-0.25, 0.25) * 2 * math.pi / n_spikes
        spikes.append((a, (1.0 if i % 2 == 0 else 0.62) * rng.uniform(0.8, 1.15), 0.3 * rng.uniform(0.75, 1.25)))
    puffs = []
    for i in range(crown):
        a = 2 * math.pi * i / crown + rng.uniform(-0.35, 0.35)
        puffs.append((a, rng.uniform(0.75, 1.0), rng.uniform(0.34, 0.5), rng.uniform(0.6, 1.2)))
    sparks = [(rng.uniform(0, 6.28), rng.uniform(0.8, 1.4), rng.uniform(0.7, 1.3), rng.random() < 0.45)
              for _ in range(spark_n)]
    shard = [(rng.uniform(0, 6.28), rng.uniform(0.9, 1.5), rng.uniform(0.6, 1.3), rng.uniform(-0.6, 0.6))
             for _ in range(shard_n)]
    t = f / 60.0
    # 1. light spill (flash lights the floor for ~12 frames)
    k = max(0.0, 1 - f / 14.0) ** 2
    if k > 0:
        fx.light_spill(cv, c, Rx * 2.5, spill, gain=1.3 * k)
    # 2. scorch decal (fresh at f2, fades over 3 s)
    if f >= 2:
        fx.scorch(cv, c, Rx * 0.8, seed=seed + 10, alpha=0.6 * min(1.0, (f - 1) / 3) * max(0.0, 1 - t / 3.0),
                  cracks=6 if f < 40 else 0, rng=np.random.default_rng(seed + 3),
                  crack_col=(scorch_col if scorch_col is not None else hx("#E0782A")) * 0.8 * max(0.2, 1 - f / 40))
    # 3. ground dust at the true radius (reaches R at frame 8)
    if 2 <= f <= 50:
        rr = Rx * (0.55 + 0.45 * ease_out(f / 8))
        al = 0.85 * (1 if f < 14 else max(0.0, 1 - (f - 14) / 36))
        fx.ground_dust(cv, c, rr, np.random.default_rng(seed + 5), 16, Rx * 0.09, Rx * (0.14 + 0.08 * min(1, f / 20)),
                       dust[0], dust[1], core, alpha=al, seed=seed + 6)
    # 4. anime impact frame: f0-1 a white star over an ink star, plus speed lines
    if flash and f <= 1:
        s = 1.25 if f == 0 else 1.1
        sp = [(a + 0.1, L * Rx * s * 1.35, h * 1.2) for a, L, h in spikes]
        r = star(cv, core, sp, Rx * 0.4 * s)
        cv.fill(r, ramp.ink, alpha=0.95)
        sp = [(a, L * Rx * s, h) for a, L, h in spikes]
        r = star(cv, core, sp, Rx * 0.35 * s)
        cv.fill(r, ramp.hot * 2.6, bloom=0.7)
        fx.speed_lines(cv, core, np.random.default_rng(seed + 9), 18, Rx * 1.5, Rx * 2.6, ramp.light, width=2.2,
                       gain=1.3, alpha=0.8)
        return
    # smoke crown geometry (behind / in front of the blast)
    grow = ease_out(f / 10)
    shrink = 1 - min(1.0, max(0.0, (f - 14) / 26.0)) ** 1.4
    lift = Rx * (0.2 + 1.1 * t)
    smoke_a = 0.92 if f < 12 else max(0.0, 0.92 - (f - 12) / 40)
    rimk = max(0.0, 1 - f / 12)
    crown_pts = []
    for a, rf, sf, jit in puffs:
        rr = Rx * rf * (0.45 + 0.4 * grow)
        pc = (core[0] + math.cos(a) * rr, core[1] + math.sin(a) * rr * 0.72 - lift * jit * 0.5)
        crown_pts.append((pc[0], pc[1], Rx * sf * 0.8 * (0.45 + 0.6 * grow) * shrink))
    crown_pts = [p for p in crown_pts if p[2] > 1.0]
    rim = fx.mixc(fx.mixc(smoke_ramp.ink, smoke_ramp.deep, 0.7), smoke_ramp.light * 1.1, rimk)
    mid = fx.mixc(smoke_ramp.ink, smoke_ramp.deep, 0.25 + 0.3 * rimk)
    back = [p for p in crown_pts if p[1] < core[1]]
    front = [p for p in crown_pts if p[1] >= core[1]]
    if smoke_a > 0:
        fx.smoke(cv, back, smoke_ramp, core, alpha=smoke_a, rim=rim, mid=mid, seed=seed + 20, rough=0.1)
    # 5. the blast: ink-framed petal star, peak f2-3, collapses by f14
    if f <= 14:
        sz = Rx * (1.0 if f <= 3 else max(0.0, 1.0 - (f - 3) / 11.0) ** 0.8)
        if sz > 1:
            hotk = max(0.0, 1 - (f - 2) / 8.0)
            sp = [(a + 0.12, L * sz * 1.32, h * 1.25) for a, L, h in spikes]
            cv.fill(star(cv, core, sp, sz * 0.4), ramp.ink, alpha=0.93 * ink_gain)
            sp = [(a, L * sz, h) for a, L, h in spikes]
            r = star(cv, core, sp, sz * 0.32)
            if r:
                sl, cov, cr = r
                kk = cr[..., None]
                col = np.where(kk > 0.62 - 0.25 * (1 - hotk), ramp.hot * (1.2 + 1.3 * hotk),
                               np.where(kk > 0.4, ramp.light * 1.35, np.where(kk > 0.18, ramp.body * 1.25,
                                                                               ramp.deep * 1.1)))
                cv.over(sl, cov, col, bloom=0.5)
    # 6. shrapnel: flung up and out, lands by f24
    if f < 40:
        polys_d, polys_e = [], []
        for a, sp_, sz_, spin in shard:
            dist = Rx * sp_ * ease_out(t / 0.45) * 1.1
            h = max(0.0, (sp_ * 3.2) * t - 9.0 * t * t) * ppm * H_ISO
            p = (core[0] + math.cos(a) * dist, core[1] + math.sin(a) * dist * K_ISO - h + (c[1] - core[1]) * min(1, t / 0.4))
            d = fx.rot((math.cos(a), math.sin(a) * K_ISO), spin * (1 + f * 0.15))
            L = Rx * 0.26 * sz_
            kt = fx.kite(p, d, L, L * 0.38)
            polys_d.append(kt)
            polys_e.append([kt[0], kt[1], ((kt[0][0] + kt[2][0]) / 2, (kt[0][1] + kt[2][1]) / 2)])
        cv.fill(cv.raster(polys=polys_d), shard_dark if shard_dark is not None else hx("#3A2814"))
        cv.fill(cv.raster(polys=polys_e), ramp.light * (1.0 if f < 20 else 0.6))
    if smoke_a > 0 and front:
        fx.smoke(cv, front, smoke_ramp, core, alpha=smoke_a, rim=rim, mid=mid, seed=seed + 21, rough=0.1)
    # 7. chunky sparks: fast, drag, gravity; gone by f20
    if f <= 20:
        polys_h, polys_b = [], []
        for a, v, w, hot in sparks:
            dd = Rx * v * (0.5 + 0.9 * ease_out(f / 10))
            ln = Rx * 0.45 * max(0.15, 1 - f / 16) * v
            g = Rx * 0.5 * (f / 20) ** 2
            head = (core[0] + math.cos(a) * dd, core[1] + math.sin(a) * dd * 0.85 + g)
            tail = (core[0] + math.cos(a) * (dd - ln), core[1] + math.sin(a) * (dd - ln) * 0.85 + g * 0.7)
            poly = fx.streak_poly(head, tail, 4.0 * w * max(0.3, 1 - f / 24), 0.0)
            (polys_h if hot else polys_b).append(poly)
        cv.fill(cv.raster(polys=polys_b), ramp.body * 1.4, bloom=0.6)
        cv.fill(cv.raster(polys=polys_h), ramp.light * 1.8, bloom=0.8)
