"""The anvil_gauntlets chassis weapon: one rigid forge-gauntlet (left or right), built procedurally.

Used by s2_weapon.py (the model lives in art/weapons/anvil_gauntlets/). It is authored around the hero it
was designed for (Brax, T-pose, arm along +-X) and then re-expressed in the hand's weapon socket frame, so any
hero on the master skeleton can wear it from the weapon_L / weapon_R socket.

Pieces (every one a closed mesh, faces tagged with paint zones):
  bronze elbow ring (sized to clear the wearer's forearm) + cog boss; lava core tube under faceted basalt
  plates (Voronoi tessellation: the grooves between the plates show the glowing core); bronze wrist band;
  tapered hand block with rock plates on its back and knuckle plates; 4 fingers x 3 + thumb x 3 chunky rock
  segments with glowing joint faces. variant "open" follows the approved concept (fingers extended),
  variant "fist" curls the same segments into a closed fist with the thumb across the front, for punches
  (same topology and vertex order, so both variants share one UV layout and texture).
"""
import math

import numpy as np
from mathutils import Vector

import s2_geom as G


def build(bm, gc, side, arm_radius_fn, rng, report, variant="open", arm_extent_fn=None):
    """arm_radius_fn(x0, x1) -> the wearer's largest arm radius about the gauntlet axis between |x| = x0..x1;
    arm_extent_fn(x0, x1) -> (half-extent along Y, half-extent along Z) there: the core grows to clear it."""
    s = side
    YC, ZC = gc["axis_y"], gc["axis_z"]
    U = np.array([0.0, 1.0, 0.0])
    V = np.array([0.0, 0.0, 1.0])
    kx = np.array(gc["core"]["x"], dtype=np.float64)
    kry = np.array(gc["core"]["ry"], dtype=np.float64)
    krz = np.array(gc["core"]["rz"], dtype=np.float64)
    if arm_extent_fn is not None:
        cl = gc["core"].get("clearance", 0.015)
        for k, x in enumerate(kx):
            ey, ez = arm_extent_fn(x - 0.025, x + 0.025)
            kry[k] = max(kry[k], ey + cl)
            krz[k] = max(krz[k], ez + cl)
    report["core_ry_rz_after_clearance"] = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(kry, krz)]

    def interp(x, knots, vals):
        return float(np.interp(x, knots, vals))

    def core_r(x):
        return interp(x, kx, kry), interp(x, kx, krz)

    def C(x):
        return np.array([s * x, YC, ZC])

    def frame(x):
        return C(x), U, V
    # -- elbow ring: sized to clear the wearer's forearm
    er = gc["elbow_ring"]
    r_arm = arm_radius_fn(er["x"][0] - 0.02, er["x"][1] + 0.02)
    flat = 1.0 / math.cos(math.pi / er["segments"])     # a polygonal band's flats sit at cos(pi/n) of its radius
    r_in = max(er["r_in_min"], r_arm + 0.008) * flat
    r_out = max(er["r_out"], r_in + 0.03)
    x0, x1 = er["x"]
    xm = (x0 + x1) / 2
    prof = [(x0, r_in), (x0, r_out - 0.014), (x0 + 0.014, r_out), (xm - 0.014, r_out), (xm, r_out + 0.011),
            (xm + 0.014, r_out), (x1 - 0.014, r_out), (x1, r_out - 0.014), (x1, r_in)]
    if s < 0:
        prof = list(reversed(prof))
    G.revolve_profile(bm, prof, None, frame, er["segments"], "bronze", ey=er["ey"], ez=er["ez"], phase=math.radians(er.get("phase_deg", 0.0)))
    report["elbow_ring_r_in_out"] = [round(r_in, 4), round(r_out, 4)]
    report["wearer_forearm_radius_in_ring"] = round(r_arm, 4)
    # -- cog boss under the ring, facing forward-down
    cg = gc["cog"]
    ang = math.radians(cg["angle_deg"])
    dirv = np.cos(ang) * U * er["ey"] + np.sin(ang) * V * er["ez"]
    dirv /= np.linalg.norm(dirv)
    cen = C(xm) + dirv * (r_out + 0.004)
    G.gear(bm, cen + dirv * cg["thick"], dirv, cg["r_out"], cg["r_in"], cg["teeth"], cg["thick"], "bronze")
    ax_u = np.cross(dirv, [1, 0, 0])
    ax_u /= max(1e-9, np.linalg.norm(ax_u))
    hub_c = cen + dirv * (cg["thick"] + 0.012)
    G.loft(bm, [G.ring_points(cen + dirv * cg["thick"] * 0.5, ax_u, [s, 0, 0], cg["hub"], cg["hub"], 8),
                G.ring_points(hub_c, ax_u, [s, 0, 0], cg["hub"] * 0.8, cg["hub"] * 0.8, 8)], "bronze")
    # -- lava core, checked against the wearer's forearm
    cx = gc["core"]
    xs = np.linspace(cx["x"][0], cx["x"][-1], cx["rings"])
    rings = []
    clear = []
    for x in xs:
        ry, rz = core_r(x)
        if arm_extent_fn is not None:
            ey, ez = arm_extent_fn(x - 0.02, x + 0.02)
            clear.append(round(min(ry - ey, rz - ez), 4))
        rings.append(G.ring_points(C(x), U, V, ry, rz, cx["segments"]))
    G.loft(bm, rings, "lava")
    report["core_clearance_over_wearer_m"] = clear
    # -- rock plates on the core
    pl = gc["plates"]
    Rref = pl["r_ref"]
    period = 2 * math.pi * Rref
    na, nl = pl["around"], pl["along"]
    px0, px1 = pl["x"]
    seeds = []
    for j in range(nl):
        for i in range(na):
            js, jx = rng.uniform(-pl["jitter"], pl["jitter"]), rng.uniform(-pl["jitter"], pl["jitter"])
            seeds.append(((i + 0.5 + 0.5 * (j % 2) + js) * period / na, px0 + (j + 0.5 + jx) * (px1 - px0) / nl))
    cells = G.voronoi_cells_periodic(seeds, period, (px0, px1))

    def surf(sv, x):
        th = sv / Rref
        ry, rz = core_r(x)
        p = C(x) + math.cos(th) * ry * U + math.sin(th) * rz * V
        n = math.cos(th) / ry * U + math.sin(th) / rz * V
        return p, n / np.linalg.norm(n)
    nplates = 0
    for poly in cells:
        if len(poly) < 3:
            continue
        P2 = np.array(poly)
        area = 0.5 * abs(np.dot(P2[:, 0], np.roll(P2[:, 1], 1)) - np.dot(P2[:, 1], np.roll(P2[:, 0], 1)))
        if area < pl["min_area"]:
            continue
        base2 = G.inset_polygon(poly, pl["gap"] / 2)
        h = pl["height"] * rng.uniform(0.8, 1.2)
        tilt = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1)]) * pl["tilt"]
        cc = np.mean(base2, axis=0)
        inner2 = G.inset_polygon(base2, pl["chamfer"])
        base, top, inner = [], [], []
        for (sv, x), (si, xi) in zip(base2, inner2):
            p, n = surf(sv, x)
            dh = tilt @ (np.array([sv, x]) - cc)
            base.append(p - n * 0.004)
            top.append(p + n * (h * 0.7 + dh))
            pi, ni = surf(si, xi)
            inner.append(pi + ni * (h + dh + pl["dome"]))
        if s < 0:
            base, top, inner = base[::-1], top[::-1], inner[::-1]
        G.prism_plate(bm, base, top, inner, "rock", "rock")
        nplates += 1
    report["forearm_plates"] = nplates
    # -- wrist band
    wb = gc["wrist_band"]
    w0, w1 = wb["x"]
    wflat = 1.0 / math.cos(math.pi / wb["segments"])
    ri = max(wb["r_in"], max(arm_extent_fn(w0, w1)) + 0.006 if arm_extent_fn else 0.0) * wflat
    ro = max(wb["r_out"], ri + 0.03)
    prof = [(w0, ri), (w0, ro - 0.01), (w0 + 0.01, ro), (w1 - 0.01, ro), (w1, ro - 0.01), (w1, ri)]
    if s < 0:
        prof = list(reversed(prof))
    G.revolve_profile(bm, prof, None, frame, wb["segments"], "bronze", ey=wb["ey"], ez=wb["ez"], phase=math.radians(wb.get("phase_deg", 0.0)))
    # -- angular bronze strap frame along the back of the forearm, ending in a ring on the back of the wrist
    sf = gc.get("strap_frame")
    if sf:
        pl_h = gc["plates"]["height"] * 1.2 + gc["plates"]["dome"]

        def top(x, yo):
            ry, rz = core_r(x)
            f = max(0.0, 1.0 - (yo / ry) ** 2)
            return np.array([s * x, YC + yo, ZC + rz * math.sqrt(f) + pl_h + sf["lift"]])
        xa, xb = sf["x"]
        w, dx = sf["half_width"], sf["corner_dx"]
        hexp = [(xa, 0.0), (xa + dx, -w), (xb - dx, -w), (xb, 0.0), (xb - dx, w), (xa + dx, w)]
        for k in range(6):
            (x0_, y0_), (x1_, y1_) = hexp[k], hexp[(k + 1) % 6]
            p0, p1 = top(x0_, y0_), top(x1_, y1_)
            d = Vector((p1 - p0).tolist())
            L = d.length
            xa_, ya_, za_ = G.frame_from(d, up_hint=(0, 0, 1))
            M = G.matrix(Vector(((p0 + p1) / 2).tolist()), xa_, ya_, za_)
            G.box(bm, M, (L / 2 + sf["bar_width"] * 0.45, sf["bar_width"] / 2, sf["bar_height"] / 2), "bronze", bevel=0.004)
        wr = sf["wrist_ring"]
        c = top(wr["x"], 0.0) + np.array([0.0, 0.0, wr["thick"] * 0.3])
        prof = [(-wr["thick"] / 2, wr["r_in"]), (wr["thick"] / 2, wr["r_in"]), (wr["thick"] / 2, wr["r_out"]), (-wr["thick"] / 2, wr["r_out"])]

        def up_frame(h):
            return c + np.array([0.0, 0.0, h]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
        G.revolve_profile(bm, prof if s > 0 else prof[::-1], None, up_frame, wr["segments"], "bronze")
    # -- hand block (rounded-rect loft) with rock plates on its back
    hb = gc["hand"]
    rings = []
    for x, hy, hz in hb["sections"]:
        c = C(x)
        ch = hb["chamfer"]
        pts2 = [(hy, hz - ch), (hy, -hz + ch), (hy - ch, -hz), (-hy + ch, -hz), (-hy, -hz + ch), (-hy, hz - ch), (-hy + ch, hz), (hy - ch, hz)]
        rings.append([c + U * a + V * b for a, b in pts2])
    if s < 0:
        rings = [r[::-1] for r in rings]
    G.loft(bm, rings, "rock")
    tp = hb.get("top_plates")
    if tp:
        secs = np.array(hb["sections"])
        seeds2 = []
        for j in range(tp["rows"]):
            for i in range(tp["cols"]):
                seeds2.append((tp["y"][0] + (i + 0.5 + rng.uniform(-tp["jitter"], tp["jitter"])) * (tp["y"][1] - tp["y"][0]) / tp["cols"],
                               tp["x"][0] + (j + 0.5 + rng.uniform(-tp["jitter"], tp["jitter"])) * (tp["x"][1] - tp["x"][0]) / tp["rows"]))
        span = tp["y"][1] - tp["y"][0]
        polys = G.voronoi_cells_periodic([(c[0] - tp["y"][0], c[1]) for c in seeds2], span * 3, tuple(tp["x"]))
        for poly in polys:
            poly = [(max(0.0, min(span, a)), b) for a, b in poly]
            if len(poly) < 3:
                continue
            base2 = G.inset_polygon(poly, tp["gap"] / 2)
            inner2 = G.inset_polygon(base2, tp["chamfer"])
            h = tp["height"] * rng.uniform(0.85, 1.15)

            def top_pt(a, b, lift):
                hz = float(np.interp(b, secs[:, 0], secs[:, 2]))
                return np.array([s * b, YC + tp["y"][0] + a, ZC + hz + lift])
            base = [top_pt(a, b, -0.004) for a, b in base2]
            top = [top_pt(a, b, h * 0.7) for a, b in base2]
            inner = [top_pt(a, b, h) for a, b in inner2]
            if s < 0:
                base, top, inner = base[::-1], top[::-1], inner[::-1]
            G.prism_plate(bm, base, top, inner, "rock", "rock")
    # -- fingers (rigid segments), knuckle plates and thumb
    fg = gc["fingers"]
    fist = gc.get("fist", {}) if variant == "fist" else {}
    curl = fist.get("curl_deg", fg["curl_deg"])
    for fi, (fy, lens, fw) in enumerate(zip(fg["y"], fg["lengths"], fg["width"])):
        pos = Vector((s * fg["x0"], YC + fy, ZC + fg["z_offset"]))
        pitch = 0.0
        hgt = fg["height"]
        for k, L in enumerate(lens):
            pitch += math.radians(curl[k])
            d = Vector((s * math.cos(pitch), 0.0, -math.sin(pitch)))
            x_ax, y_ax, z_ax = G.frame_from(d, up_hint=(0, 0, 1) if abs(d.z) < 0.9 else (-s, 0, 0))
            cen = pos + d * (L / 2)
            M = G.matrix(cen, x_ax, y_ax, z_ax)
            G.box(bm, M, (L / 2, fw / 2, hgt / 2), "rock", bevel=fg["bevel"], taper_end=fg["taper"],
                  start_zone="lava" if k > 0 else None, end_zone="lava" if k < len(lens) - 1 else None)
            pos = pos + d * (L + fg["gap"])
            hgt *= fg["taper"]
        kn = gc["knuckle"]
        M = G.matrix(Vector((s * kn["x"], YC + fy, ZC + kn["z"])), Vector((s, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        G.box(bm, M, (kn["half"][0], fw / 2 * kn["width_scale"], kn["half"][2]), "rock", bevel=kn["bevel"])
    th = gc["thumb"]
    pos = Vector((s * th["base"][0], YC + th["base"][1], ZC + th["base"][2]))
    dirs = fist.get("thumb_dirs")
    d0 = Vector((s * th["dir"][0], th["dir"][1], th["dir"][2])).normalized()
    hgt = th["height"]
    for k, L in enumerate(th["lengths"]):
        if dirs:
            d = Vector((s * dirs[k][0], dirs[k][1], dirs[k][2])).normalized()
        else:
            d = d0.lerp(Vector((s, 0, -0.2)).normalized(), th["bend"] * k).normalized()
        x_ax, y_ax, z_ax = G.frame_from(d)
        M = G.matrix(pos + d * (L / 2), x_ax, y_ax, z_ax)
        G.box(bm, M, (L / 2, th["width"] / 2, hgt / 2), "rock", bevel=fg["bevel"], taper_end=fg["taper"],
              start_zone="lava" if k > 0 else None, end_zone="lava" if k < len(th["lengths"]) - 1 else None)
        pos = pos + d * (L + fg["gap"])
        hgt *= fg["taper"]
    return report
