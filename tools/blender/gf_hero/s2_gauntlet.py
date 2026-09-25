"""The anvil_gauntlets chassis weapon: one rigid forge-gauntlet (left or right), built procedurally on the
stage-1 blockout's own gauntlet (v2, 2026-09-25 polish pass).

Used by s2_weapon.py (the model lives in art/weapons/anvil_gauntlets/). It is authored around the hero it
was designed for (Brax, T-pose, arm along +-X), on a field sampled from the s202 blockout's gauntlet:
  * the blockout radius E(theta, x) around the gauntlet axis (bolt spikes median-filtered out) gives the
    forearm's shape: the core follows its smooth base, the plate tops follow E itself (radial scale S(x));
  * the blockout's plate lumps (E minus its smooth base) give the plate centres, so the plates sit where the
    blockout's plates are and the blockout normal bake lines up with them.
Then it is re-expressed in the hand's weapon socket frame, so any hero on the master skeleton can wear it.

Pieces (every one a closed mesh, faces tagged with paint zones, per-vertex gf_mask = (edge 0 .. top 1,
per-plate random, -, 1)):
  hexagonal bronze elbow cuff with studs and a cog boss; lava core tube; chunky faceted basalt plates
  (shoulder ring + top ring + off-centre peak: stylised hand-sculpted rock) with wide seams so the core glows
  between them; hexagonal bronze strap frame + wrist ring; hexagonal wrist band with studs; a broad hand core
  with its own plates and four massive knuckle chunks; 4 fingers x 3 + thumb x 3 faceted hexagonal rock
  segments with glowing joint faces. variant "open" = the concept's relaxed open hand, variant "fist" curls
  the same segments into a fist (identical topology and vertex order: one UV layout and texture).
"""
import math

import numpy as np
from mathutils import Vector

import s2_geom as G


class Field:
    """Blockout envelope E(theta, x) (m) around the gauntlet axis; theta 0 = +Y, 90 deg = +Z."""

    def __init__(self, thetas, xs, E, B):
        self.th, self.xs, self.E, self.B = thetas, xs, E, B
        self.dth = thetas[1] - thetas[0]
        self.dx = xs[1] - xs[0]

    def _look(self, A, th, x):
        th = th % (2 * math.pi)
        fi = th / self.dth
        i0 = int(math.floor(fi)) % len(self.th)
        i1 = (i0 + 1) % len(self.th)
        ft = fi - math.floor(fi)
        fx = (min(max(x, self.xs[0]), self.xs[-1]) - self.xs[0]) / self.dx
        j0 = min(int(math.floor(fx)), len(self.xs) - 2)
        fx -= j0
        a = A[i0, j0] * (1 - ft) + A[i1, j0] * ft
        b = A[i0, j0 + 1] * (1 - ft) + A[i1, j0 + 1] * ft
        return a * (1 - fx) + b * fx

    def e(self, th, x):
        return self._look(self.E, th, x)

    def b(self, th, x):
        return self._look(self.B, th, x)


def sgnpow(v, p):
    return math.copysign(abs(v) ** p, v)


def build(bm, gc, side, field, seeds_tx, rng, report, variant="open", arm_extent_fn=None):
    """field: Field of this side's blockout gauntlet; seeds_tx: [(theta, x)] plate centres found on it."""
    s = side
    # the build axis is the blockout's gauntlet axis moved onto the wearer's forearm (build_offset): the whole
    # blockout field moves with it, so plates, core and bands keep the blockout's shape around the wearer's arm
    YC = gc["axis_y"] + gc["build_offset"][0]
    ZC = gc["axis_z"] + gc["build_offset"][1]
    U = np.array([0.0, 1.0, 0.0])
    V = np.array([0.0, 0.0, 1.0])
    S = lambda x: float(np.interp(x, gc["radial_scale"]["x"], gc["radial_scale"]["s"]))  # noqa: E731

    def C(x, cy=0.0, cz=0.0):
        return np.array([s * x, YC + cy, ZC + cz])

    # ---------------- cross-sections: forearm from the blockout, hand from the config ----------------
    fc = gc["forearm"]
    t0 = fc["plate_thickness"]
    cl = fc["clearance"]
    fxs = np.linspace(fc["x"][0], fc["x"][1], 12)
    fa, fb, fcy, fcz = [], [], [], []
    for x in fxs:
        k = S(x)
        yp, ym = field.b(0.0, x) * k, field.b(math.pi, x) * k
        zp, zm = field.b(math.pi / 2, x) * k, field.b(3 * math.pi / 2, x) * k
        a, b = (yp + ym) / 2 - t0, (zp + zm) / 2 - t0
        if arm_extent_fn is not None:
            ey, ez = arm_extent_fn(x - 0.025, x + 0.025)
            a, b = max(a, ey + cl), max(b, ez + cl)
        fa.append(a)
        fb.append(b)
        fcy.append((yp - ym) / 2 * fc["center_follow"])
        fcz.append((zp - zm) / 2 * fc["center_follow"])
    hc = gc["hand"]
    hsec = np.array(hc["sections"], dtype=np.float64)   # x, a (half-width y), b (half-height z), cz

    def section(x):
        """(cy, cz, a, b, p) of the core at x: forearm ellipse -> hand superellipse."""
        if x <= fc["x"][1]:
            return (float(np.interp(x, fxs, fcy)), float(np.interp(x, fxs, fcz)), float(np.interp(x, fxs, fa)),
                    float(np.interp(x, fxs, fb)), 2.0)
        a = float(np.interp(x, hsec[:, 0], hsec[:, 1]))
        b = float(np.interp(x, hsec[:, 0], hsec[:, 2]))
        cz = float(np.interp(x, hsec[:, 0], hsec[:, 3]))
        return 0.0, cz, a, b, hc["exponent"]

    def core_pt(t, x):
        cy, cz, a, b, p = section(x)
        ct, st = math.cos(t), math.sin(t)
        e = 2.0 / p
        y = a * sgnpow(ct, e)
        z = b * sgnpow(st, e)
        # normal of |y/a|^p + |z/b|^p = 1
        ny = sgnpow(y / a, p - 1) / a if a > 0 else 0.0
        nz = sgnpow(z / b, p - 1) / b if b > 0 else 0.0
        n = ny * U + nz * V
        n = n / (np.linalg.norm(n) + 1e-12)
        return C(x, cy, cz) + y * U + z * V, n

    # ---------------- elbow cuff (hexagonal bronze) + studs + cog -----------------------------------
    cu = gc["cuff"]
    x0, x1 = cu["x"]
    xm = (x0 + x1) / 2
    flat = 1.0 / math.cos(math.pi / 6)
    arm_r = max(arm_extent_fn(x0 - 0.01, x1 + 0.01)) if arm_extent_fn else 0.1
    r_in = (arm_r + cu["gap"]) * flat
    r_out = max(cu["r_out_flat"] * flat, r_in + cu["min_wall"])
    prof = [(x0, r_in), (x0, r_out - 0.016), (x0 + 0.016, r_out), (xm - 0.012, r_out), (xm, r_out + 0.012),
            (xm + 0.012, r_out), (x1 - 0.016, r_out), (x1, r_out - 0.016), (x1, r_in)]
    if s < 0:
        prof = list(reversed(prof))
    cyz = section(x0)
    G.revolve_profile(bm, prof, None, lambda x: (C(x, cyz[0], cyz[1]), U, V), 6, "bronze", phase=0.0)
    report["cuff_r_in_out"] = [round(r_in, 4), round(r_out, 4)]
    # studs on both rims of the cuff, on the hexagon's faces
    for xs_ in [x0 + v if v >= 0 else x1 + v for v in cu["stud_rims"]]:
        for k in range(6):
            a = (k + 0.5) * math.pi / 3
            d = math.cos(a) * U + math.sin(a) * V
            c = C(xs_, cyz[0], cyz[1]) + d * (r_out * math.cos(math.pi / 6) + 0.002)
            G.stud(bm, c, d, cu["stud_r"], cu["stud_h"], "bronze")
    cg = gc["cog"]
    ang = math.radians(cg["angle_deg"])
    dirv = math.cos(ang) * U + math.sin(ang) * V
    cen = C(xm, cyz[0], cyz[1]) + dirv * (r_out * math.cos(math.pi / 6) + 0.003)
    G.gear(bm, cen + dirv * cg["thick"], dirv, cg["r_out"], cg["r_in"], cg["teeth"], cg["thick"], "bronze")
    G.stud(bm, cen + dirv * cg["thick"], dirv, cg["hub"], cg["hub"] * 0.7, "bronze")

    # ---------------- lava core: forearm tube + hand block (one closed loft) -------------------------
    ncs = gc["core_segments"]
    core_x = list(np.linspace(fc["x"][0] - 0.02, fc["x"][1], 7)) + list(hsec[1:, 0])
    rings = []
    for x in core_x:
        rings.append([core_pt(2 * math.pi * k / ncs, x)[0] for k in range(ncs)])
    if s < 0:
        rings = [r[::-1] for r in rings]
    G.loft(bm, rings, "lava")
    clear = []
    if arm_extent_fn is not None:
        for x in np.linspace(fc["x"][0], hsec[-1, 0] - 0.02, 8):
            cy, cz, a, b, p = section(x)
            ey, ez = arm_extent_fn(x - 0.02, x + 0.02)
            clear.append(round(min(a - ey, b - ez), 4))
    report["core_clearance_over_wearer_m"] = clear

    # ---------------- plates ------------------------------------------------------------------------
    def plate_layer(cells, seeds_h, region, zone="rock"):
        n_made = 0
        for poly, hbase in zip(cells, seeds_h):
            if len(poly) < 3:
                continue
            P2 = np.array(poly)
            area = 0.5 * abs(np.dot(P2[:, 0], np.roll(P2[:, 1], 1)) - np.dot(P2[:, 1], np.roll(P2[:, 0], 1)))
            if area < region["min_area"]:
                continue
            base2 = G.inset_polygon(poly, region["gap"] / 2)
            pts, nrm, hs = [], [], []
            for (sv, x) in base2:
                t = sv / region["r_ref"]
                p, n = core_pt(t, x)
                pts.append(p)
                nrm.append(n)
                hs.append(region["height_fn"](t, x, p))
            hs = np.array(hs)
            hs = np.clip(hs * rng.uniform(0.9, 1.1), region["h_min"], region["h_max"])
            if s < 0:
                pts, nrm, hs = pts[::-1], nrm[::-1], hs[::-1]
            G.rock_chunk(bm, pts, nrm, hs, rng, region["chunk"], zone=zone, plate_rand=rng.random())
            n_made += 1
        return n_made

    # forearm: plate centres from the blockout's lumps, tops follow the blockout surface (scaled)
    fp = gc["forearm_plates"]
    Rf = fp["r_ref"]
    period = 2 * math.pi * Rf
    seeds = [(t * Rf, x) for (t, x) in seeds_tx if fp["seed_x"][0] <= x <= fp["seed_x"][1]]
    n_blockout = len(seeds)
    for ring in fp.get("extra_rings", []):      # where the blockout has rivet rows instead of plates
        for k in range(ring["count"]):
            seeds.append(((k + 0.5 + rng.uniform(-0.15, 0.15)) * period / ring["count"], ring["x"] + rng.uniform(-0.006, 0.006)))
    cells = G.voronoi_cells_periodic(seeds, period, tuple(fp["x"]))

    def h_forearm(t, x, p):
        d = p - C(x)                     # the field is sampled around the gauntlet axis
        th = math.atan2(d[2], d[1])
        top = field.e(th, x) * S(x) + fp["lift"]
        return top - np.linalg.norm(d)
    reg = dict(fp, r_ref=Rf, height_fn=h_forearm)
    report["forearm_plates"] = plate_layer(cells, [0] * len(cells), reg)
    report["forearm_plate_seeds_from_blockout"] = n_blockout

    # hand: a jittered grid of plates over the back, sides and palm of the hand core
    hp = gc["hand_plates"]
    Rh = hp["r_ref"]
    hper = 2 * math.pi * Rh
    hseeds = []
    for j in range(hp["along"]):
        for i in range(hp["around"]):
            hseeds.append(((i + 0.5 + 0.5 * (j % 2) + rng.uniform(-hp["jitter"], hp["jitter"])) * hper / hp["around"],
                           hp["x"][0] + (j + 0.5 + rng.uniform(-hp["jitter"], hp["jitter"])) * (hp["x"][1] - hp["x"][0]) / hp["along"]))
    hcells = G.voronoi_cells_periodic(hseeds, hper, tuple(hp["x"]))
    hreg = dict(hp, r_ref=Rh, height_fn=lambda t, x, p: hp["height"])
    report["hand_plates"] = plate_layer(hcells, [0] * len(hcells), hreg)

    # ---------------- strap frame (hexagonal bronze bars on the back of the forearm) + wrist ring ---------
    sf = gc["strap_frame"]

    def top_at(x, yo):
        """Top of the plate layer (the same clamped height the plates use) above the line y = axis + yo."""
        cy, cz, a, b, _ = section(x)
        t = math.acos(max(-0.98, min(0.98, (yo - cy) / a)))
        p, n = core_pt(t, x)
        h = min(max(h_forearm(t, x, p), fp["h_min"]), fp["h_max"])
        return p + n * (h * 0.9 + sf["lift"])
    xa, xb = sf["x"]
    w, dx = sf["half_width"], sf["corner_dx"]
    hexp = [(xa, 0.0), (xa + dx, -w), (xb - dx, -w), (xb, 0.0), (xb - dx, w), (xa + dx, w)]
    for k in range(6):
        (xa_, ya_), (xb_, yb_) = hexp[k], hexp[(k + 1) % 6]
        p0, p1 = top_at(xa_, ya_), top_at(xb_, yb_)
        d = Vector((p1 - p0).tolist())
        L = d.length
        ax_, ay_, az_ = G.frame_from(d, up_hint=(0, 0, 1))
        M = G.matrix(Vector(((p0 + p1) / 2).tolist()), ax_, ay_, az_)
        G.box(bm, M, (L / 2 + sf["bar_width"] * 0.45, sf["bar_width"] / 2, sf["bar_height"] / 2), "bronze", bevel=0.004)
    wr = sf["wrist_ring"]
    c = top_at(wr["x"], 0.0) + np.array([0.0, 0.0, wr["thick"] * 0.3])
    prof = [(-wr["thick"] / 2, wr["r_in"]), (wr["thick"] / 2, wr["r_in"]), (wr["thick"] / 2, wr["r_out"]), (-wr["thick"] / 2, wr["r_out"])]
    G.revolve_profile(bm, prof if s > 0 else prof[::-1], None,
                      lambda h: (c + np.array([0.0, 0.0, h]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
                      wr["segments"], "bronze")

    # ---------------- wrist band (hexagonal bronze) + studs -------------------------------------------
    wb = gc["wrist_band"]
    w0, w1 = wb["x"]
    cyw, czw, aw, bw, _ = section(w0)
    ri = (max(aw, bw) + wb["gap"]) * flat
    ro = max(wb["r_out_flat"] * flat, ri + wb["min_wall"])
    prof = [(w0, ri), (w0, ro - 0.012), (w0 + 0.012, ro), (w1 - 0.012, ro), (w1, ro - 0.012), (w1, ri)]
    if s < 0:
        prof = list(reversed(prof))
    G.revolve_profile(bm, prof, None, lambda x: (C(x, cyw, czw), U, V), 6, "bronze", phase=0.0)
    for k in range(6):
        a = (k + 0.5) * math.pi / 3
        d = math.cos(a) * U + math.sin(a) * V
        G.stud(bm, C((w0 + w1) / 2, cyw, czw) + d * (ro * math.cos(math.pi / 6) + 0.002), d, wb["stud_r"], wb["stud_h"], "bronze")
    report["wrist_band_r_in_out"] = [round(ri, 4), round(ro, 4)]

    # ---------------- knuckles, fingers, thumb ---------------------------------------------------------
    fg = gc["fingers"]
    fist = gc.get("fist", {}) if variant == "fist" else {}
    xe = hsec[-1, 0]
    cye, cze, ae, be, _ = section(xe - 1e-4)
    kn = gc["knuckle"]
    for fi, (fy, lens, fw) in enumerate(zip(fg["y"], fg["lengths"], fg["width"])):
        # knuckle chunk on the top front edge of the hand
        kc = C(xe - kn["back"], 0.0, cze) + np.array([0.0, fy, be + kn["lift"]])
        G.rock_block(bm, kc, np.array([s, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]), kn["size"][0], fw * kn["width_scale"],
                     kn["size"][2], rng, "rock", facets=kn.get("facets"))
        yaw = math.radians(fg["fan_deg"][fi]) * (1 if s > 0 else -1)
        pos = Vector((s * (xe - fg["root_back"]), YC + fy, ZC + cze + fg["z_offset"]))
        pitch = math.radians(fg["pitch_deg"])
        hgt = fg["height"]
        wid = fw
        curl = fist.get("curl_deg", fg["curl_deg"])
        for k, L in enumerate(lens):
            pitch += math.radians(curl[k])
            d = Vector((s * math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw) * s, -math.sin(pitch)))
            d.normalize()
            up = Vector((0.0, 0.0, 1.0)) if abs(d.z) < 0.9 else Vector((-s, 0.0, 0.0))
            G.rock_segment(bm, pos, d, up, L, wid, hgt, rng, "rock", joint_start=k > 0, joint_end=k < len(lens) - 1,
                           taper=fg["taper"], jitter=fg["jitter"])
            pos = pos + d * (L + fg["gap"])
            hgt *= fg["taper"]
            wid *= fg["taper"]
    th = gc["thumb"]
    pos = Vector((s * th["base"][0], YC + th["base"][1], ZC + th["base"][2]))
    dirs = fist.get("thumb_dirs", th["dirs"])
    hgt, wid = th["height"], th["width"]
    for k, L in enumerate(th["lengths"]):
        d = Vector((s * dirs[k][0], dirs[k][1], dirs[k][2])).normalized()
        G.rock_segment(bm, pos, d, Vector((0.0, 0.0, 1.0)) if abs(d.z) < 0.9 else Vector((-s, 0.0, 0.0)), L, wid, hgt, rng,
                       "rock", joint_start=k > 0, joint_end=k < len(th["lengths"]) - 1, taper=fg["taper"], jitter=fg["jitter"])
        pos = pos + d * (L + fg["gap"])
        hgt *= fg["taper"]
        wid *= fg["taper"]
    return report
