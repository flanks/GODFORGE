"""Stage 3, Kael: the skinning hook the shared s3_skin.py imports (art/characters/kael/stage3_skin.json "hook").

Not run on its own. s3_skin.py builds GF_Hero_v1 from work/kael_landmarks.json (the contract bones + his x_ cloth
chains), weights the BODY exactly as it weights Brax's (MakeHuman CC0 seed + bone heat + twist split + joint fixes),
weights HAIR (head), BOOTS and GEAR (copy of the body, small pieces rigid) itself, and calls:

  part_weights(name, ob, pc, ctx)  for the parts in mode "hook":
      COAT       COAT_YOKE and the lapels copy the body at the nearest body point (the yoke is the body's own quads
                 pushed out, so every yoke vertex takes the weights of the skin under it and bends with it); the rolled
                 cuffs are the mean of that copy, one row (rigid); the collar one row of rig.collar.row; the skirt
                 (COAT_SKIRT_L/R) on the x_coat grid: across, linear between the two nearest columns by theta, the
                 back pair blended above the vent and split by side below it; along, hat functions on the bones'
                 middles; the tucked top row pinned to the body's own weights (as the yoke over it);
      SCARF      the wrap one row of rig.collar.row, its drape rigid on spine_03;
      LOINCLOTH  the x_loin grid (u across 0.8 x the half-width), the top pinned to the pelvis;
      WISPS      each tatter: above its hem the coat skirt's weights at that point (its root lies on the coat), below
                 it hat functions along its x_wisp chain by arc length, blended over rig.wisps.band_m.
  after_bind(arm, ctx)  the signature weapon on its socket: assets/models/weapons/serpent_smg.glb imported and baked
      into ONE local object PREVIEW_serpent_smg_R whose mesh coordinates are the weapon's grip frame, held on
      weapon_R by a Child Of constraint whose inverse is SOCKET_TO_GRIP (the Blender form of the identity attach;
      the same code as Valdris's hook). It is PREVIEW: never exported with the hero.
"""
import os

import bpy
import numpy as np
from mathutils import Matrix

import gf_hero_rig as R
from s2lib import log, read_json, rel
from s3lib import smoothstep


def _piece_names(ob, ctx):
    table = ctx.setdefault("_piece_names", {p["id"]: p["name"] for p in read_json(
        os.path.join(ctx["paths"]["A"], "reports", "stage2", "parts.json"))["piece_table"]})
    me = ob.data
    fp = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["gf_piece"].data.foreach_get("value", fp)
    vp = np.full(len(me.vertices), -1)
    for poly, pid in zip(me.polygons, fp):
        vp[list(poly.vertices)] = pid
    return np.array([table.get(int(i), "") for i in vp])


def _row(rule, ctx):
    r = np.zeros(len(ctx["BONES"]))
    for b, w in rule.items():
        r[ctx["C"][b]] += w
    return r / r.sum()


def _hat(s, nodes):
    """Linear blend along a chain: nodes = [(param, key)] ascending in param. -> list per point of [(key, w)]."""
    ps = np.array([n[0] for n in nodes])
    out = []
    for v in s:
        if v <= ps[0]:
            out.append([(nodes[0][1], 1.0)])
            continue
        if v >= ps[-1]:
            out.append([(nodes[-1][1], 1.0)])
            continue
        i = int(np.nonzero(ps <= v)[0][-1])
        t = (v - ps[i]) / (ps[i + 1] - ps[i])
        out.append([(nodes[i][1], 1.0 - t), (nodes[i + 1][1], t)])
    return out


def _bone_mid_z(ctx, bone):
    h, t = ctx["SEG"][bone]
    return 0.5 * (h[2] + t[2])


def _chain_bones(ctx, prefix):
    out = []
    k = 1
    while "%s_%02d" % (prefix, k) in ctx["C"]:
        out.append("%s_%02d" % (prefix, k))
        k += 1
    return out


def _chain_rows(co, ctx, prefix, pin_z, pin_rows):
    """Weights along one chain by height: above pin_z the pin rows (n, nbones), below the hat over the bone middles."""
    bones = _chain_bones(ctx, prefix)
    nodes = [(-_bone_mid_z(ctx, b), b) for b in bones]
    nodes = [(-pin_z, "PIN")] + nodes                   # ascending in -z (top first)
    W = np.zeros((len(co), len(ctx["BONES"])))
    for i, r in enumerate(_hat(-co[:, 2], nodes)):
        for key, w in r:
            if key == "PIN":
                W[i] += w * pin_rows[i]
            else:
                W[i, ctx["C"][key]] += w
    return W


def theta_of(co):
    return np.degrees(np.arctan2(co[:, 0], -co[:, 1])) % 360.0


def skirt_weights(co, ctx):
    """The x_coat grid (stage3_skin.json rig.coat)."""
    cc = ctx["cfg"]["rig"]["coat"]
    T = np.array(cc["theta_deg"])
    names = cc["names"]
    th = theta_of(co)
    n = len(co)
    share = np.zeros((n, len(names)))
    for i in range(n):
        t = th[i]
        if t <= T[0]:
            share[i, 0] = 1.0
        elif t >= T[-1]:
            share[i, -1] = 1.0
        else:
            j = int(np.nonzero(T <= t)[0][-1])
            u = (t - T[j]) / (T[j + 1] - T[j])
            share[i, j], share[i, j + 1] = 1.0 - u, u
    # the back vent: between LB and RB the two sides blend above the vent and split by side below it
    jb = names.index("LB")
    back = (th > T[jb]) & (th < T[jb + 1])
    f = smoothstep(cc["vent_z"] + cc["split_band_m"], cc["vent_z"], co[:, 2])
    split = np.zeros((n, 2))
    split[:, 0] = co[:, 0] > 0.0
    split[:, 1] = 1.0 - split[:, 0]
    share[back, jb:jb + 2] = (1 - f[back, None]) * share[back, jb:jb + 2] + f[back, None] * split[back]
    pin = ctx["copy_from_body"](co)
    W = np.zeros((n, len(ctx["BONES"])))
    for j, nm in enumerate(names):
        m = share[:, j] > 0
        if m.any():
            W[m] += share[m, j, None] * _chain_rows(co[m], ctx, "x_coat_" + nm, cc["pin_top_z"], pin[m])
    return W


def loin_weights(co, ctx):
    lc = ctx["cfg"]["rig"]["loin"]
    p2 = read_json(os.path.join(ctx["paths"]["A"], "stage2_parts.json"))["loin"]
    f = np.clip((p2["z"][0] - co[:, 2]) / (p2["z"][0] - p2["z"][1]), 0.0, 1.3)
    hw = 0.8 * (p2["half_width"][0] + (p2["half_width"][1] - p2["half_width"][0]) * f)
    U = np.array(lc["columns_u"])
    u = np.clip(co[:, 0] / hw, U[0], U[-1])
    pin = np.tile(_row({"pelvis": 1.0}, ctx), (len(co), 1))
    W = np.zeros((len(co), len(ctx["BONES"])))
    for j, nm in enumerate(lc["names"]):
        a = np.clip((u - U[j - 1]) / (U[j] - U[j - 1]), 0, 1) if j > 0 else np.ones(len(u))
        b = np.clip((U[j + 1] - u) / (U[j + 1] - U[j]), 0, 1) if j < len(U) - 1 else np.ones(len(u))
        s = np.where(u <= U[j], a, b)
        m = s > 0
        if m.any():
            W[m] += s[m, None] * _chain_rows(co[m], ctx, "x_loin_" + nm, lc["pin_top_z"], pin[m])
    return W


def wisp_weights(co, k, ctx):
    bones = _chain_bones(ctx, "x_wisp_%d" % k)
    pts = [np.array(ctx["SEG"][bones[0]][0])] + [np.array(ctx["SEG"][b][1]) for b in bones]
    seg_len = [float(np.linalg.norm(b - a)) for a, b in zip(pts[:-1], pts[1:])]
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    # arc-length parameter of each vertex's closest point on the centre line
    best = np.full(len(co), np.inf)
    s = np.zeros(len(co))
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        d = b - a
        t = np.clip(((co - a) @ d) / (d @ d), 0.0, 1.0)
        dist = np.linalg.norm(co - (a + t[:, None] * d), axis=1)
        m = dist < best
        best[m] = dist[m]
        s[m] = cum[i] + t[m] * seg_len[i]
    nodes = [(0.5 * (cum[i] + cum[i + 1]), b) for i, b in enumerate(bones)]
    chainW = np.zeros((len(co), len(ctx["BONES"])))
    for i, r in enumerate(_hat(s, nodes)):
        for b, w in r:
            chainW[i, ctx["C"][b]] += w
    band = ctx["cfg"]["rig"]["wisps"]["band_m"]
    f = smoothstep(pts[0][2] + 0.5 * band, pts[0][2] - 0.5 * band, co[:, 2])
    coatW = skirt_weights(co, ctx)
    return (1 - f)[:, None] * coatW + f[:, None] * chainW


def part_weights(name, ob, pc, ctx):
    co = np.array([tuple(v.co) for v in ob.data.vertices])
    vp = _piece_names(ob, ctx)
    W = np.zeros((len(co), len(ctx["BONES"])))
    rig = ctx["cfg"]["rig"]
    done = np.zeros(len(co), bool)
    rows = {}

    def put(mask, M, label):
        W[mask] = M
        done[mask] = True
        rows[label] = int(mask.sum())

    if name == "COAT":
        m = np.isin(vp, ["COAT_YOKE", "COAT_LAPEL_L", "COAT_LAPEL_R"])
        put(m, ctx["copy_from_body"](co[m]), "yoke + lapels: copy")
        for side in ("L", "R"):
            m = vp == "COAT_CUFF_" + side
            put(m, ctx["copy_from_body"](co[m]).mean(axis=0), "cuff %s: rigid mean of the copy" % side)
        m = vp == "COAT_COLLAR"
        put(m, _row(rig["collar"]["row"], ctx), "collar: rigid spine_03 / neck")
        m = np.isin(vp, ["COAT_SKIRT_L", "COAT_SKIRT_R"])
        put(m, skirt_weights(co[m], ctx), "skirt: x_coat grid")
    elif name == "SCARF":
        m = vp == "SCARF"
        put(m, _row(rig["collar"]["row"], ctx), "wrap: rigid spine_03 / neck")
        m = vp == "SCARF_DRAPE"
        put(m, _row({"spine_03": 1.0}, ctx), "drape: rigid spine_03")
    elif name == "LOINCLOTH":
        m = np.ones(len(co), bool)
        put(m, loin_weights(co, ctx), "x_loin grid")
    elif name == "WISPS":
        for k in range(1, 6):
            m = vp == "WISP_%d" % k
            put(m, wisp_weights(co[m], k, ctx), "WISP_%d: coat above the hem, x_wisp_%d below" % (k, k))
    if not done.all() or (W.sum(axis=1) <= 0).any():
        raise SystemExit("%s: %d vertices left unweighted by the hook (pieces %s)" % (
            name, int((W.sum(axis=1) <= 0).sum()), sorted(set(vp[W.sum(axis=1) <= 0]))))
    ctx.setdefault("_hook_parts", {})[name] = rows
    log("hook weights %s: %s" % (name, rows))
    return W


# ---- the signature weapon from its shipped GLB (as s3_valdris_skin.after_bind) ------------------------------------------
def after_bind(arm, ctx):
    out = {"hook_parts": ctx.get("_hook_parts", {})}
    wkey = ctx["fit"].get("signature_weapon") or "serpent_smg"
    root = os.path.dirname(os.path.dirname(os.path.dirname(ctx["paths"]["A"])))
    glb = os.path.join(root, "assets", "models", "weapons", "%s.glb" % wkey)
    if not os.path.isfile(glb):
        out["preview_weapon"] = None
        return out
    scene = bpy.context.scene
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    roots = [o for o in new if o.parent is None]
    root_err = max(abs(a - b) for o in roots for ra, rb in zip(o.matrix_world, Matrix.Identity(4)) for a, b in zip(ra, rb))
    sockets = {}
    for o in new:
        if o.type == "EMPTY" and o.name.split(".")[0] in ("grip_R", "grip_L", "muzzle", "glow_core", "eject"):
            M = o.matrix_world
            sockets[o.name.split(".")[0]] = {"origin": [round(v, 5) for v in M.translation],
                                             "y_axis": [round(v, 5) for v in M.to_3x3().col[1].normalized()],
                                             "z_axis": [round(v, 5) for v in M.to_3x3().col[2].normalized()]}
    meshes = [o for o in new if o.type == "MESH"]
    for o in meshes:
        M = o.matrix_world.copy()
        o.parent = None
        o.data.transform(M)
        o.matrix_world = Matrix.Identity(4)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    for o in new:
        if o.name in bpy.data.objects and o != ob:
            bpy.data.objects.remove(o)
    ob.name = "PREVIEW_%s_R" % wkey
    ob.data.name = "PREVIEW_%s_R" % wkey
    pcol = bpy.data.collections.new("PREVIEW_%s (not exported)" % wkey)
    scene.collection.children.link(pcol)
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    pcol.objects.link(ob)
    c = ob.constraints.new("CHILD_OF")
    c.target = arm
    c.subtarget = "weapon_R"
    c.inverse_matrix = Matrix(R.SOCKET_TO_GRIP)
    ob["gf_weapon_glb"] = rel(glb)
    ob["gf_weapon_sockets"] = str(sockets)
    bpy.context.view_layer.update()
    want = R.grip_matrix(arm, "weapon_R", pose=False)
    err = max(abs(a - b) for ra, rb in zip(want, ob.matrix_world) for a, b in zip(ra, rb))
    out["preview_weapon"] = {"file": rel(glb), "object": ob.name, "vertices": len(ob.data.vertices),
                             "glb_root_is_identity_max_abs": root_err, "rest_attach_vs_grip_frame_max_abs": err,
                             "sockets_in_grip_frame": sockets}
    log("preview weapon %s on weapon_R: root identity %.1e, rest attach %.1e" % (ob.name, root_err, err))
    if root_err > 1e-6 or err > 1e-5:
        raise SystemExit("the weapon GLB root is not identity or the attach is off")
    return out
