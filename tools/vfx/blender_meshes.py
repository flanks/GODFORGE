"""GODFORGE VFX meshes: slash arcs, shockwave ring profiles, projectile bodies, beam strips.

Run (Blender 5.2, no scene needed; writes assets/vfx/meshes/*.glb and a preview render):
    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" -b --factory-startup \\
        -P tools/vfx/blender_meshes.py -- [--preview OUT.png]

Conventions (glTF, what Bevy loads): +Y up, forward = -Z (Transform::looking_to points -Z at the
target), metres, origin at the effect origin (the swing pivot, the ring centre, the projectile's
simulated position). In Blender that is +Z up and forward = +Y.

Every mesh carries COLOR_0 as packed data, like the atlases: R = 1 (mask), G = value band (ink 0.06,
deep 0.29, body 0.50, light 0.70, hot 0.93), B = erosion order (0 erodes first). Colour through the
element ramp in vfx.wesl, exactly as for sprites. UV0 is documented per mesh in MESHES. Normals are
flat on faceted bodies (crystal, rock, blade) and split at hard edges elsewhere.

MESHES below is plain data so tools/vfx/build_all.py can import it without Blender.
"""
import math
import os
import sys

V_INK, V_DEEP, V_BODY, V_LIGHT, V_HOT = 0.06, 0.29, 0.50, 0.70, 0.93

ARC_SWEEPS = [60, 90, 120, 180, 270, 360]
MESHES = {}
for _s in ARC_SWEEPS:
    MESHES[f"vfx_arc_{_s:03d}"] = dict(
        group="smear", intended=f"crescent smear strip, {_s} deg sweep: melee strikes, slashes, spins, whips "
        "(texture smears/vfx_smears.png)", uv="u = 0 tail .. 1 head along the sweep; v = 0 inner .. 1 outer",
        pivot="the swing pivot (the character); outer radius 1 m, max width 0.36 m (scale to reach)",
        orient="lies in the ground plane (XZ), centred on forward (-Z), sweeps counter-clockwise seen from "
        "above (from the right of forward to the left); mirror X for the other hand; rotate about X for "
        "overhead swings")
MESHES.update({
    "vfx_ring_flat": dict(group="ring", intended="flat shock band on the ground: shock fronts, zone hems, charge rings",
                          uv="u = 0..1 once round (multiply by the gap count, trails row accent_ring); v = 0 inner .. 1 outer",
                          pivot="ring centre; outer radius 1 m, inner 0.82 m", orient="ground plane"),
    "vfx_ring_wall": dict(group="ring", intended="a dust wall leaning outward: the painterly shockwave front, "
                          "Mountainfall / Bulwark Slam dust walls", uv="u = 0..1 round; v = 0 foot .. 1 top",
                          pivot="ring centre; foot radius 0.9 m, top 1.0 m at 0.35 m height", orient="+Y up"),
    "vfx_ring_crown": dict(group="ring", intended="a curling crown lip: synergy shock fronts, the Overdrive and "
                           "AnvilLit gold shock fronts, Stolen Second tick front", uv="u = 0..1 round; v = 0 inner foot .. 1 lip",
                           pivot="ring centre; radius 0.85 -> 1.05 m, 0.24 m high", orient="+Y up"),
    "vfx_bolt": dict(group="body", intended="Bolt (pendulum_repeater): a short thick crossbow-bolt kite, hot tip, ink shaft",
                     uv="u along the length (0 tail .. 1 tip)", pivot="body centre, 0.5 m long", orient="tip at -Z"),
    "vfx_arrow": dict(group="body", intended="Arrow (wraith_bow, echoing_greatbow): arrowhead, ink shaft, fletching",
                      uv="u along the length", pivot="body centre, 0.8 m long", orient="tip at -Z"),
    "vfx_needle": dict(group="body", intended="Needle (serpent_smg): a hot sliver", uv="u along the length",
                       pivot="body centre, 0.55 m long", orient="tip at -Z"),
    "vfx_shell": dict(group="body", intended="Shell (colossus_cannon, Skyhook): brass capsule with a hot base; tumble 90 deg/s",
                      uv="u along the length (0 base .. 1 nose), v round", pivot="body centre, 0.46 m long", orient="nose at -Z"),
    "vfx_shard": dict(group="body", intended="Shard (Style(Shard)): a crystal kite; spin 720 deg/s", uv="u along the length",
                      pivot="body centre, 0.42 m long", orient="tip at -Z"),
    "vfx_disc_blade": dict(group="body", intended="Blade disc (orrery_discs, Orbit blades): a disc with 3 hooked blades; "
                           "spin about Y", uv="planar top view (u, v = x, z mapped to 0..1)", pivot="disc centre, radius 0.36 m",
                           orient="lies in the XZ plane"),
    "vfx_coin": dict(group="body", intended="Coin (coinshooter, Grand Heist): a 12-sided coin; spin about its diameter",
                     uv="planar face mapping", pivot="coin centre, radius 0.13 m", orient="faces +-Z"),
    "vfx_boulder_a": dict(group="body", intended="Boulder (Mountainfall): faceted rock, three value planes, molten seams",
                          uv="spherical", pivot="rock centre, ~0.6 m", orient="any; tumble"),
    "vfx_boulder_b": dict(group="body", intended="Boulder variant b", uv="spherical", pivot="rock centre", orient="any"),
    "vfx_boulder_c": dict(group="body", intended="Boulder variant c", uv="spherical", pivot="rock centre", orient="any"),
    "vfx_javelin": dict(group="body", intended="Javelin (huntmother_javelins): a barbed shaft with a feather tail",
                        uv="u along the length", pivot="body centre, 1.4 m long", orient="tip at -Z"),
    "vfx_harpoon": dict(group="body", intended="Harpoon (tidecaller_harpoon): barbed hooks, a rope ring at the back",
                        uv="u along the length", pivot="body centre, 1.2 m long; rope anchor at +Z end", orient="tip at -Z"),
    "vfx_pellet": dict(group="body", intended="Pellet (sunspike_shotgun) and small generic bodies: a diamond",
                       uv="u along the length", pivot="centre, 0.14 m", orient="tip at -Z"),
    "vfx_beam_ribbon": dict(group="beam", intended="beam strip: 32 segments for the wobble; texture trails rows beam_core / "
                            "beam_body / loot_beam", uv="u = 0 at the muzzle .. 1 at the far end (scale u by length for "
                            "tiling), v across", pivot="the muzzle; 1 m long along -Z, 1 m wide along X (scale to len, width)",
                            orient="lies in the XZ plane; billboard it about its axis"),
    "vfx_beam_cross": dict(group="beam", intended="two crossed beam strips (XZ and YZ planes) for thick beams and loot beams",
                           uv="as vfx_beam_ribbon", pivot="the muzzle; 1 m long along -Z", orient="axis along -Z"),
})


# ------------------------------------------------------------------------------------------------
# Blender side
# ------------------------------------------------------------------------------------------------
def _run():
    import bpy
    import bmesh
    from mathutils import Vector

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", ".."))
    out_dir = os.path.join(root, "assets", "vfx", "meshes")
    os.makedirs(out_dir, exist_ok=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None

    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    mat = bpy.data.materials.new("vfx_packed")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "vfx"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])

    def build(name, verts, faces, g, b, uvs=None, flat=True, sharp_deg=None, face_g=None):
        """verts [(x,y,z)] Blender coords; faces [[i..]]; g/b per vertex; uvs per vertex (u, v down) or None;
        face_g: optional per-face value override."""
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update()
        col = me.color_attributes.new(name="vfx", type="FLOAT_COLOR", domain="CORNER")
        me.color_attributes.active_color = col
        me.color_attributes.render_color_index = 0
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                gv = face_g[poly.index] if face_g is not None and face_g[poly.index] is not None else g[vi]
                col.data[li].color = (1.0, gv, b[vi], 1.0)
                if uvs is not None:
                    u, v = uvs[vi]
                    uvl.data[li].uv = (u, 1.0 - v)  # glTF flips v: store "v down" as 1 - v
        for poly in me.polygons:
            poly.use_smooth = not flat
        if sharp_deg is not None and not flat:
            bm = bmesh.new()
            bm.from_mesh(me)
            for e in bm.edges:
                if len(e.link_faces) == 2 and e.calc_face_angle() > math.radians(sharp_deg):
                    e.smooth = False
            bm.to_mesh(me)
            bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob

    def lathe(profile, n, name, g_of, b_of, u_of, cap_ends=True, flat=False, sharp=35):
        """Revolve a (radius, y) profile about +Y (forward). g_of/b_of/u_of(index along profile)."""
        verts, faces, g, b, uvs = [], [], [], [], []
        m = len(profile)
        for i, (r, y) in enumerate(profile):
            for k in range(n):
                a = k / n * math.tau
                verts.append((r * math.cos(a), y, r * math.sin(a)))
                g.append(g_of(i))
                b.append(b_of(i))
                uvs.append((u_of(i), k / n))
        for i in range(m - 1):
            for k in range(n):
                a0 = i * n + k
                a1 = i * n + (k + 1) % n
                b0 = (i + 1) * n + k
                b1 = (i + 1) * n + (k + 1) % n
                if profile[i][0] < 1e-6:
                    faces.append([a0, b1, b0])
                elif profile[i + 1][0] < 1e-6:
                    faces.append([a0, a1, b0])
                else:
                    faces.append([a0, a1, b1, b0])
        return build(name, verts, faces, g, b, uvs, flat=flat, sharp_deg=sharp)

    objs = []

    # ---- slash arcs ----------------------------------------------------------------------------
    for sweep in ARC_SWEEPS:
        n = max(16, int(sweep / 5))
        S = math.radians(sweep)
        a_tail = math.pi / 2 - S / 2
        verts, faces, g, b, uvs = [], [], [], [], []
        Wmax, peak = 0.36, 0.72
        full = sweep == 360
        for i in range(n + 1):
            t = i / n
            if full:
                w = Wmax * 0.6
            else:
                if t < peak:
                    w = Wmax * math.sin(t / peak * math.pi / 2) ** 1.3
                else:
                    k = (t - peak) / (1 - peak)
                    w = Wmax * math.sqrt(max(0.0, 1 - k * k))
                w = max(w, 0.012)
            a = a_tail + S * t
            ro, ri = 1.0, 1.0 - w
            verts.append((ri * math.cos(a), ri * math.sin(a), 0.0))
            verts.append((ro * math.cos(a), ro * math.sin(a), 0.0))
            g += [V_BODY, V_BODY]
            b += [t, t]
            uvs += [(t, 0.0), (t, 1.0)]
        for i in range(n):
            faces.append([2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1])
        objs.append(build(f"vfx_arc_{sweep:03d}", verts, faces, g, b, uvs, flat=False))

    # ---- shock rings ---------------------------------------------------------------------------
    def ring(name, profile, n=64):
        verts, faces, g, b, uvs = [], [], [], [], []
        m = len(profile)
        for k in range(n + 1):  # duplicate the seam for clean UVs
            a = k / n * math.tau
            for i, (r, h) in enumerate(profile):
                verts.append((r * math.cos(a), r * math.sin(a), h))
                t = i / (m - 1)
                g.append(V_BODY)
                b.append(0.5)
                uvs.append((k / n, t))
        for k in range(n):
            for i in range(m - 1):
                a0 = k * m + i
                a1 = (k + 1) * m + i
                faces.append([a0, a1, a1 + 1, a0 + 1])
        return build(name, verts, faces, g, b, uvs, flat=False)

    objs.append(ring("vfx_ring_flat", [(0.82, 0.0), (0.91, 0.0), (1.0, 0.0)]))
    objs.append(ring("vfx_ring_wall", [(0.9, 0.0), (0.94, 0.12), (0.97, 0.24), (1.0, 0.35)]))
    objs.append(ring("vfx_ring_crown", [(0.85, 0.0), (0.93, 0.14), (0.99, 0.22), (1.04, 0.24), (1.06, 0.16)]))

    # ---- projectile bodies (forward = +Y in Blender) -------------------------------------------
    def body_lathe(name, prof, n, vals, flat=False, sharp=35):
        """prof [(radius, y)] from the tail (min y) to the tip; vals[i] = value per profile ring."""
        ys = [p[1] for p in prof]
        y0, y1 = min(ys), max(ys)
        return lathe(prof, n, name, lambda i: vals[i], lambda i: (prof[i][1] - y0) / (y1 - y0 + 1e-9),
                     lambda i: (prof[i][1] - y0) / (y1 - y0 + 1e-9), flat=flat, sharp=sharp)

    # Bolt: 0.5 m kite head + thick shaft, 4 sides
    objs.append(body_lathe("vfx_bolt", [(0.0, -0.25), (0.045, -0.24), (0.045, 0.05), (0.075, 0.1), (0.02, 0.25), (0.0, 0.25)],
                           4, [V_INK, V_INK, V_INK, V_LIGHT, V_HOT, V_HOT], flat=True))
    # Needle: bicone sliver, 6 sides
    objs.append(body_lathe("vfx_needle", [(0.0, -0.275), (0.026, -0.05), (0.03, 0.08), (0.0, 0.275)], 6,
                           [V_DEEP, V_BODY, V_LIGHT, V_HOT], flat=False, sharp=30))
    # Shell: base, band, body, ogive nose
    shell = [(0.0, -0.23), (0.07, -0.23), (0.085, -0.2), (0.085, -0.16), (0.08, 0.05),
             (0.07, 0.14), (0.045, 0.2), (0.0, 0.23)]
    objs.append(body_lathe("vfx_shell", shell, 8, [V_HOT, V_HOT, V_DEEP, V_BODY, V_BODY, V_LIGHT, V_LIGHT, V_HOT],
                           flat=False, sharp=28))
    # Pellet: octahedron diamond
    objs.append(body_lathe("vfx_pellet", [(0.0, -0.07), (0.035, 0.0), (0.0, 0.07)], 4, [V_BODY, V_LIGHT, V_HOT], flat=True))

    # Arrow: head (flattened diamond) + shaft + 3 fletching fins
    def arrow():
        verts, faces, g, b, uvs = [], [], [], [], []

        def add(vs, fs, gv, bv):
            o = len(verts)
            verts.extend(vs)
            faces.extend([[o + i for i in f] for f in fs])
            g.extend(gv)
            b.extend(bv)
            uvs.extend([((v[1] + 0.4) / 0.8, 0.5) for v in vs])
        # head: 4 verts round the waist + tip + back point
        add([(0.0, 0.4, 0.0), (0.07, 0.24, 0.0), (0.0, 0.24, 0.02), (-0.07, 0.24, 0.0), (0.0, 0.24, -0.02), (0.0, 0.2, 0.0)],
            [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 1], [5, 2, 1], [5, 3, 2], [5, 4, 3], [5, 1, 4]],
            [V_HOT, V_BODY, V_LIGHT, V_BODY, V_LIGHT, V_DEEP], [1, 0.9, 0.9, 0.9, 0.9, 0.85])
        # shaft: square prism
        s = 0.012
        ring0 = [(s, -0.36, 0), (0, -0.36, s), (-s, -0.36, 0), (0, -0.36, -s)]
        ring1 = [(s, 0.22, 0), (0, 0.22, s), (-s, 0.22, 0), (0, 0.22, -s)]
        add(ring0 + ring1, [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], [V_INK] * 8, [0.1] * 4 + [0.7] * 4)
        # fletching: 3 fins
        for k in range(3):
            a = k * math.tau / 3 + math.pi / 2
            ca, sa = math.cos(a), math.sin(a)
            fin = [(0, -0.4, 0), (0.07 * ca, -0.36, 0.07 * sa), (0.05 * ca, -0.22, 0.05 * sa), (0, -0.2, 0)]
            add(fin, [[0, 1, 2, 3], [3, 2, 1, 0]], [V_DEEP, V_LIGHT, V_BODY, V_DEEP], [0.0, 0.05, 0.2, 0.25])
        return build("vfx_arrow", verts, faces, g, b, uvs, flat=True)
    objs.append(arrow())

    # Shard: an asymmetric crystal (6 facets front, 5 back), flat shaded, one lit facet
    def shard():
        verts = [(0.0, 0.21, 0.0), (0.06, 0.02, 0.01), (0.0, 0.0, 0.05), (-0.055, 0.03, 0.0), (0.0, 0.01, -0.045),
                 (0.0, -0.21, 0.0)]
        faces = [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 1], [5, 2, 1], [5, 3, 2], [5, 4, 3], [5, 1, 4]]
        g = [V_HOT, V_BODY, V_LIGHT, V_DEEP, V_BODY, V_DEEP]
        b = [1.0, 0.6, 0.6, 0.6, 0.6, 0.1]
        face_g = [V_LIGHT, V_BODY, V_DEEP, V_BODY, V_BODY, V_DEEP, V_INK, V_DEEP]
        uvs = [((v[1] + 0.21) / 0.42, 0.5) for v in verts]
        return build("vfx_shard", verts, faces, g, b, uvs, flat=True, face_g=face_g)
    objs.append(shard())

    # Disc blade: 3 hooked blades round a hub, extruded thin; lies in the XY plane of Blender (ground)
    def disc():
        outline = []
        for k in range(3):
            base = k * math.tau / 3
            for r, da in ((0.15, 0.0), (0.22, 0.3), (0.3, 0.55), (0.37, 0.95), (0.27, 0.78), (0.19, 0.88)):
                a = base + da
                outline.append((r * math.cos(a), r * math.sin(a)))
        n = len(outline)
        verts, faces, g, b, uvs = [], [], [], [], []
        for z in (0.012, -0.012):
            verts.append((0.0, 0.0, z))
            for x, y in outline:
                verts.append((x, y, z))
        m = n + 1
        for i in range(n):
            j = (i + 1) % n
            faces.append([0, 1 + i, 1 + j])
            faces.append([m, m + 1 + j, m + 1 + i])
            faces.append([1 + i, m + 1 + i, m + 1 + j, 1 + j])
        for idx, v in enumerate(verts):
            r = math.hypot(v[0], v[1])
            tip = (idx % m) % 5 == 4 if idx % m else False
            g.append(V_INK if r < 0.01 else (V_HOT if r > 0.34 else (V_LIGHT if r > 0.25 else V_BODY)))
            b.append(min(1.0, r / 0.36))
            uvs.append((v[0] / 0.72 + 0.5, 0.5 - v[1] / 0.72))
        return build("vfx_disc_blade", verts, faces, g, b, uvs, flat=True)
    objs.append(disc())

    # Coin: 12-sided, faces +-Y in Blender (-> +-Z in glTF)
    def coin():
        n, r, h = 12, 0.13, 0.012
        verts, faces, g, b, uvs = [], [], [], [], []
        for y in (h, -h):
            verts.append((0.0, y, 0.0))
            for k in range(n):
                a = k / n * math.tau
                verts.append((r * math.cos(a), y, r * math.sin(a)))
        m = n + 1
        for k in range(n):
            j = (k + 1) % n
            faces.append([0, 1 + j, 1 + k])
            faces.append([m, m + 1 + k, m + 1 + j])
            faces.append([1 + k, 1 + j, m + 1 + j, m + 1 + k])
        for v in verts:
            rr = math.hypot(v[0], v[2])
            g.append(V_LIGHT if rr < 0.01 else V_BODY)
            b.append(0.5)
            uvs.append((v[0] / (2 * r) + 0.5, 0.5 - v[2] / (2 * r)))
        return build("vfx_coin", verts, faces, g, b, uvs, flat=False, sharp_deg=40)
    objs.append(coin())

    # Boulders: jittered icospheres (80 faces), three value planes by facing, a band of molten seams
    import random
    for key, seed in (("a", 3), ("b", 7), ("c", 11)):
        rnd = random.Random(seed)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.3)
        for v in bm.verts:
            k = 1 + rnd.uniform(-0.18, 0.18)
            v.co = Vector((v.co.x * k * rnd.uniform(0.9, 1.15), v.co.y * k, v.co.z * k * rnd.uniform(0.8, 1.0)))
        verts = [tuple(v.co) for v in bm.verts]
        faces = [[v.index for v in f.verts] for f in bm.faces]
        face_g = []
        seam_axis = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.3, 0.3))).normalized()
        for f in bm.faces:
            nrm = f.normal
            c = f.calc_center_median()
            if abs(c.normalized().dot(seam_axis)) < 0.1:
                face_g.append(V_HOT if rnd.random() < 0.6 else V_LIGHT)
            elif nrm.z > 0.62:
                face_g.append(V_LIGHT if rnd.random() < 0.3 else V_BODY)
            elif nrm.z > -0.2:
                face_g.append(V_DEEP)
            else:
                face_g.append(V_INK)
        bm.free()
        g = [V_BODY] * len(verts)
        b = [0.5] * len(verts)
        uvs = [(0.5 + math.atan2(v[1], v[0]) / math.tau, 0.5 - math.asin(max(-1, min(1, v[2] / 0.35))) / math.pi) for v in verts]
        objs.append(build(f"vfx_boulder_{key}", verts, faces, g, b, uvs, flat=True, face_g=face_g))

    # Javelin: shaft, barbed diamond head, feather tail
    def javelin(name, L, head_len, barbs, ring_back=False):
        verts, faces, g, b, uvs = [], [], [], [], []

        def add(vs, fs, gv, bv):
            o = len(verts)
            verts.extend(vs)
            faces.extend([[o + i for i in f] for f in fs])
            g.extend(gv)
            b.extend(bv)
            uvs.extend([((v[1] + L / 2) / L, 0.5) for v in vs])
        s = 0.016
        y0, y1 = -L / 2, L / 2 - head_len
        ring0 = [(s, y0, 0), (0, y0, s), (-s, y0, 0), (0, y0, -s)]
        ring1 = [(s, y1, 0), (0, y1, s), (-s, y1, 0), (0, y1, -s)]
        add(ring0 + ring1, [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7], [3, 2, 1, 0]], [V_DEEP] * 4 + [V_BODY] * 4,
            [0.1] * 4 + [0.6] * 4)
        tip = L / 2
        hw = 0.05
        add([(0, tip, 0), (hw, y1 + head_len * 0.3, 0), (0, y1 + head_len * 0.3, 0.018), (-hw, y1 + head_len * 0.3, 0),
             (0, y1 + head_len * 0.3, -0.018), (0, y1, 0)],
            [[0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 1], [5, 2, 1], [5, 3, 2], [5, 4, 3], [5, 1, 4]],
            [V_HOT, V_LIGHT, V_LIGHT, V_LIGHT, V_LIGHT, V_BODY], [1, 0.9, 0.9, 0.9, 0.9, 0.8])
        for k in range(barbs):
            sgn = 1 if k % 2 == 0 else -1
            yb = y1 + 0.02 - 0.06 * (k // 2)
            add([(sgn * 0.012, yb + 0.05, 0), (sgn * 0.075, yb - 0.06, 0), (sgn * 0.012, yb, 0)], [[0, 1, 2], [2, 1, 0]],
                [V_LIGHT, V_HOT, V_BODY], [0.8, 0.9, 0.8])
        if ring_back:
            n = 8
            vs = []
            for k in range(n):
                a = k / n * math.tau
                vs.append((0.045 * math.cos(a), y0 - 0.02, 0.045 * math.sin(a)))
                vs.append((0.03 * math.cos(a), y0 - 0.02, 0.03 * math.sin(a)))
            fs = []
            for k in range(n):
                j = (k + 1) % n
                fs.append([2 * k, 2 * j, 2 * j + 1, 2 * k + 1])
                fs.append([2 * k + 1, 2 * j + 1, 2 * j, 2 * k])
            add(vs, fs, [V_BODY] * (2 * n), [0.2] * (2 * n))
        else:
            for k in range(2):
                a = k * math.pi / 2
                ca, sa = math.cos(a), math.sin(a)
                add([(0, y0, 0), (0.06 * ca, y0 + 0.02, 0.06 * sa), (0.04 * ca, y0 + 0.2, 0.04 * sa), (0, y0 + 0.24, 0),
                     (-0.06 * ca, y0 + 0.02, -0.06 * sa), (-0.04 * ca, y0 + 0.2, -0.04 * sa)],
                    [[0, 1, 2, 3], [3, 2, 1, 0], [0, 3, 5, 4], [4, 5, 3, 0]], [V_DEEP, V_LIGHT, V_BODY, V_DEEP, V_LIGHT, V_BODY],
                    [0.0, 0.05, 0.2, 0.25, 0.05, 0.2])
        return build(name, verts, faces, g, b, uvs, flat=True)
    objs.append(javelin("vfx_javelin", 1.4, 0.24, 2))
    objs.append(javelin("vfx_harpoon", 1.2, 0.3, 4, ring_back=True))

    # ---- beams -------------------------------------------------------------------------------
    def strip(name, planes):
        verts, faces, g, b, uvs = [], [], [], [], []
        n = 32
        for plane in planes:
            o = len(verts)
            for i in range(n + 1):
                t = i / n
                for s in (-0.5, 0.5):
                    if plane == "x":
                        verts.append((s, t, 0.0))
                    else:
                        verts.append((0.0, t, s))
                    g.append(V_BODY)
                    b.append(0.5)
                    uvs.append((t, s + 0.5))
            for i in range(n):
                faces.append([o + 2 * i, o + 2 * i + 1, o + 2 * i + 3, o + 2 * i + 2])
        return build(name, verts, faces, g, b, uvs, flat=False)
    objs.append(strip("vfx_beam_ribbon", ["x"]))
    objs.append(strip("vfx_beam_cross", ["x", "z"]))

    # ---- export --------------------------------------------------------------------------------
    props = bpy.ops.export_scene.gltf.get_rna_type().properties
    report = []
    for ob in objs:
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        path = os.path.join(out_dir, ob.name + ".glb")
        kw = dict(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=True,
                  export_texcoords=True, export_normals=True, export_tangents=False, export_materials="EXPORT",
                  export_vertex_color="ACTIVE", export_all_vertex_colors=False,
                  export_active_vertex_color_when_no_material=True, export_attributes=False,
                  export_draco_mesh_compression_enable=False, export_extras=False, export_cameras=False,
                  export_lights=False, export_skins=False, export_animations=False)
        if "export_meshopt_compression_enable" in props:
            kw["export_meshopt_compression_enable"] = False
        bpy.ops.export_scene.gltf(**{k: v for k, v in kw.items() if k in props})
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        report.append((ob.name, tris, os.path.getsize(path)))
        print("VFXMESH", ob.name, tris, os.path.getsize(path))

    if preview:
        render_preview(bpy, objs, preview)


def render_preview(bpy, objs, path):
    """Lay the meshes out in a grid and render them the way the game shades them: value -> kinetic ramp,
    a two-step toon light, ink outlines (inverted hull)."""
    from mathutils import Vector
    import bmesh
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.022, 0.025, 1)
    sc.world = world

    ramp = [(0.0, "#1A120C"), (0.18, "#8A4A16"), (0.40, "#E3A64A"), (0.60, "#F4E3C1"), (0.81, "#FFFBF0")]

    def srgb(h):
        h = h.lstrip("#")
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1.0]

    pm = bpy.data.materials.new("preview")
    pm.use_nodes = True
    nt = pm.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    va = nt.nodes.new("ShaderNodeVertexColor")
    va.layer_name = "vfx"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.interpolation = "CONSTANT"
    els = cr.color_ramp.elements
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position = 0.0
    els[0].color = srgb(ramp[0][1])
    for pos, col in ramp[1:]:
        e = els.new(pos)
        e.color = srgb(col)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = Vector((-0.4, -0.5, 0.77)).normalized()
    step = nt.nodes.new("ShaderNodeMapRange")
    step.inputs[1].default_value = -0.05
    step.inputs[2].default_value = 0.05
    step.inputs[3].default_value = 0.62
    step.inputs[4].default_value = 1.0
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(va.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs[1], cr.inputs[0])
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    nt.links.new(dot.outputs["Value"], step.inputs[0])
    nt.links.new(cr.outputs["Color"], mul.inputs[6])
    nt.links.new(step.outputs[0], mul.inputs[7])
    nt.links.new(mul.outputs[2], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs[0])
    ink = bpy.data.materials.new("ink")
    ink.use_nodes = True
    ink.use_backface_culling = True
    n2 = ink.node_tree
    for n in list(n2.nodes):
        n2.nodes.remove(n)
    o2 = n2.nodes.new("ShaderNodeOutputMaterial")
    e2 = n2.nodes.new("ShaderNodeEmission")
    e2.inputs["Color"].default_value = (0.008, 0.005, 0.006, 1)
    n2.links.new(e2.outputs[0], o2.inputs[0])

    def packed_mat(name, rel, rows, row, rep=1.0, ramp_key=None):
        """Decode a packed strip atlas like vfx.wesl: R (SDF) -> alpha, G -> posterized ramp."""
        root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        img = bpy.data.images.load(os.path.join(root, "assets", "vfx", rel), check_existing=True)
        img.colorspace_settings.name = "Non-Color"
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        t = m.node_tree
        for n in list(t.nodes):
            t.nodes.remove(n)
        o = t.nodes.new("ShaderNodeOutputMaterial")
        tc = t.nodes.new("ShaderNodeTexCoord")
        mp = t.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (rep, 1.0 / rows, 1.0)
        mp.inputs["Location"].default_value = (0.0, (rows - row - 1) / rows, 0.0)
        tx = t.nodes.new("ShaderNodeTexImage")
        tx.image = img
        tx.extension = "REPEAT"
        sp_ = t.nodes.new("ShaderNodeSeparateColor")
        a = t.nodes.new("ShaderNodeMapRange")
        a.inputs[1].default_value = 0.44
        a.inputs[2].default_value = 0.56
        c2 = t.nodes.new("ShaderNodeValToRGB")
        c2.color_ramp.interpolation = "CONSTANT"
        el = c2.color_ramp.elements
        while len(el) > 1:
            el.remove(el[-1])
        rp = ramp if ramp_key is None else ramp_key
        el[0].color = srgb(rp[0][1])
        for pos, colr in rp[1:]:
            e = el.new(pos)
            e.color = srgb(colr)
        e3 = t.nodes.new("ShaderNodeEmission")
        e3.inputs["Strength"].default_value = 1.2
        tr = t.nodes.new("ShaderNodeBsdfTransparent")
        mx = t.nodes.new("ShaderNodeMixShader")
        t.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        t.links.new(mp.outputs["Vector"], tx.inputs["Vector"])
        t.links.new(tx.outputs["Color"], sp_.inputs[0])
        t.links.new(sp_.outputs[0], a.inputs[0])
        t.links.new(sp_.outputs[1], c2.inputs[0])
        t.links.new(c2.outputs["Color"], e3.inputs["Color"])
        t.links.new(a.outputs[0], mx.inputs[0])
        t.links.new(tr.outputs[0], mx.inputs[1])
        t.links.new(e3.outputs[0], mx.inputs[2])
        t.links.new(mx.outputs[0], o.inputs[0])
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
        return m

    flame_r = [(0.0, "#240A06"), (0.18, "#A8300A"), (0.40, "#FF7A1A"), (0.60, "#FFC24B"), (0.81, "#FFF3D6")]
    storm_r = [(0.0, "#06101E"), (0.18, "#1B4E9B"), (0.40, "#3FD8FF"), (0.60, "#BDF6FF"), (0.81, "#FFFFFF")]
    void_r = [(0.0, "#0C0416"), (0.18, "#3B1675"), (0.40, "#A45CFF"), (0.60, "#E2CCFF"), (0.81, "#FFF6FF")]
    gold_r = [(0.0, "#241703"), (0.18, "#8A6A20"), (0.40, "#FFC940"), (0.60, "#FFE6A0"), (0.81, "#FFF8E0")]
    strip_mats = {
        "vfx_arc_060": packed_mat("m60", "smears/vfx_smears.png", 8, 1, 1.0, storm_r),
        "vfx_arc_090": packed_mat("m90", "smears/vfx_smears.png", 8, 0, 1.0),
        "vfx_arc_120": packed_mat("m120", "smears/vfx_smears.png", 8, 3, 1.0, flame_r),
        "vfx_arc_180": packed_mat("m180", "smears/vfx_smears.png", 8, 4, 1.0, void_r),
        "vfx_arc_270": packed_mat("m270", "smears/vfx_smears.png", 8, 5, 1.0, storm_r),
        "vfx_arc_360": packed_mat("m360", "smears/vfx_smears.png", 8, 7, 3.0),
        "vfx_ring_flat": packed_mat("rf", "trails/vfx_trails.png", 16, 15, 4.0, gold_r),
        "vfx_ring_wall": packed_mat("rw", "trails/vfx_trails.png", 16, 12, 2.0),
        "vfx_ring_crown": packed_mat("rc", "trails/vfx_trails.png", 16, 15, 3.0, gold_r),
        "vfx_beam_ribbon": packed_mat("br", "trails/vfx_trails.png", 16, 12, 2.0, flame_r),
        "vfx_beam_cross": packed_mat("bc", "trails/vfx_trails.png", 16, 13, 2.0, gold_r),
    }
    layout = {
        "vfx_arc_060": (0, 0, 1.0), "vfx_arc_090": (1, 0, 1.0), "vfx_arc_120": (2, 0, 1.0), "vfx_arc_180": (3, 0, 1.0),
        "vfx_arc_270": (4, 0, 1.0), "vfx_arc_360": (5, 0, 1.0),
        "vfx_ring_flat": (0, 1, 0.9), "vfx_ring_wall": (1, 1, 0.9), "vfx_ring_crown": (2, 1, 0.9),
        "vfx_beam_ribbon": (3, 1, 1.4), "vfx_beam_cross": (4, 1, 1.4), "vfx_disc_blade": (5, 1, 2.2),
        "vfx_bolt": (0, 2, 3.0), "vfx_arrow": (1, 2, 2.0), "vfx_needle": (2, 2, 3.0), "vfx_shell": (3, 2, 3.0),
        "vfx_shard": (4, 2, 3.2), "vfx_pellet": (5, 2, 6.0),
        "vfx_coin": (0, 3, 5.0), "vfx_boulder_a": (1, 3, 2.3), "vfx_boulder_b": (2, 3, 2.3), "vfx_boulder_c": (3, 3, 2.3),
        "vfx_javelin": (4, 3, 1.1), "vfx_harpoon": (5, 3, 1.25),
    }
    sp = 2.6
    for ob in objs:
        col, row, sc_ = layout[ob.name]
        ob.data.materials.clear()
        ob.data.materials.append(strip_mats.get(ob.name, pm))
        ob.data.materials.append(ink)
        ob.location = (col * sp, -row * sp * 0.82, 0.0)
        ob.scale = (sc_, sc_, sc_)
        if ob.name in ("vfx_bolt", "vfx_arrow", "vfx_needle", "vfx_shell", "vfx_shard", "vfx_pellet", "vfx_javelin",
                       "vfx_harpoon"):
            ob.rotation_euler = (0.35, 0.0, -0.75)
        elif ob.name == "vfx_coin":
            ob.rotation_euler = (0.2, 0.0, 0.6)
        elif ob.name.startswith("vfx_boulder"):
            ob.rotation_euler = (0.4, 0.3, 0.5)
        elif ob.name in ("vfx_beam_ribbon", "vfx_beam_cross"):
            ob.rotation_euler = (0.0, 0.0, -0.9)
            ob.location.x -= 0.4
        if not ob.name.startswith(("vfx_arc", "vfx_ring", "vfx_beam")):
            sol = ob.modifiers.new("ink", "SOLIDIFY")
            sol.thickness = 0.012
            sol.offset = 1.0
            sol.use_flip_normals = True
            sol.material_offset = 1
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 16.5
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    cx, cy = 2.5 * sp, -1.5 * sp * 0.82
    ang = math.radians(55)
    d = 30
    cam.location = (cx, cy - d * math.cos(ang), d * math.sin(ang))
    cam.rotation_euler = (math.radians(90 - 55), 0, 0)
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    from bpy_extras.object_utils import world_to_camera_view
    import json
    labels = {}
    bpy.context.view_layer.update()
    for ob in objs:
        p = world_to_camera_view(sc, cam, ob.matrix_world.translation)
        labels[ob.name] = [p.x * sc.render.resolution_x, (1 - p.y) * sc.render.resolution_y]
    with open(path + ".json", "w") as f:
        json.dump(labels, f)
    print("VFXPREVIEW", path)


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        _run()
    except ImportError:
        print("run inside Blender: blender -b --factory-startup -P tools/vfx/blender_meshes.py")
