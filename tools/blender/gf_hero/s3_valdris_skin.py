"""Stage 3, Valdris: the skinning hook the shared s3_skin.py imports (art/characters/valdris/stage3_skin.json "hook").

Not run on its own. s3_skin.py builds GF_Hero_v1 from work/valdris_landmarks.json (the contract bones + his x_ extras),
weights the under-suit BODY exactly as it weights Brax's body (MakeHuman CC0 seed + bone heat + twist split + joint
fixes), and calls:

  after_armature(arm, ctx)  drives the x_ helpers (stage3_skin.json rig.helpers):
      x_pauldron_L/R  a Transformation of the upper arm's elevation (swing Z, upward only) x `follow`, about the
                      pauldron's inner hinge by the neck
      x_elbow_L/R     Copy Rotation of lowerarm: the elbow ring and couter turn half the bend (1.0 on the cannon arm)
      x_knee_L/R      Copy Rotation of shin at 0.5: the poleyn and the knee smile turn half the bend
      x_tasset_L/R    Copy Rotation of thigh at `follow`, about the tasset hinge on the belt
      x_fauld_01      a driver (simple expression, no Python): max(thigh_L, thigh_R flexion, 0) x follow
    Each helper has the rest orientation of the bone it follows, so the local rotation turns it about the same axes.
    Blender evaluates them; the stage-5 glTF export samples every bone, so clips carry them baked, like the twist bones.
  part_weights(name, ob, pc, ctx)  every armour, beard and cloth part (mode "hook"):
      armour  rigid per piece: the face attribute gf_piece names the piece (reports/stage2/parts.json piece_table) and
              stage3_skin.json rig.pieces gives its bone or blended row; every vertex of a piece gets the same row;
      beard   the block is hair on the head, its bib blending toward the neck; locks and the moustache rigid on the
              head; each braid's plait lobes, ring and cap rigid on x_beard_<k>_01 / _02;
      cape    the x_cape grid: linear between the two nearest chains across, between the bones either side along a
              chain, the top row pinned to spine_03; the collar rigid on spine_03;
      loin    the x_loin grid, the same rule, pinned to pelvis at the belt.
  after_bind(arm, ctx)  the signature weapon on its socket: assets/models/weapons/colossus_cannon.glb imported and baked
      into ONE local object PREVIEW_colossus_cannon_R whose mesh coordinates are the weapon's grip frame (so stage 4's
      keep-out reads it as a sleeve weapon), held on weapon_R by a Child Of constraint whose inverse is SOCKET_TO_GRIP
      (the Blender form of the identity attach). Its sockets (grip_L, muzzle, ...) are kept as a custom property.
      It is PREVIEW: never exported with the hero.
"""
import math
import os
import re

import bpy
import numpy as np
from mathutils import Matrix

import gf_hero_rig as R
from s2lib import log, read_json, rel
from s3lib import components, smoothstep

MH_TO_GF = {"neck_01": "neck", "calf": "shin", "ball": "toe"}


def gf_bone(name):
    """A stage-2 piece_table bone (MakeHuman names: clavicle_l, calf_r, ball_l, neck_01, index_02_l) -> GF_Hero_v1."""
    if name.startswith("x_") or name in ("pelvis", "spine_01", "spine_02", "spine_03", "head"):
        return name
    if name in MH_TO_GF:
        return MH_TO_GF[name]
    m = re.match(r"^(.*)_([lr])$", name)
    if not m:
        return name
    base, s = m.group(1), m.group(2).upper()
    return "%s_%s" % (MH_TO_GF.get(base, base), s)


# ---- helpers ------------------------------------------------------------------------------------------------------------
def after_armature(arm, ctx):
    H = ctx["cfg"]["rig"]["helpers"]
    out = {}

    def copy_rot(owner, target, influence):
        pb = arm.pose.bones[owner]
        c = pb.constraints.new("COPY_ROTATION")
        c.name = "follow_" + target
        c.target = arm
        c.subtarget = target
        c.mix_mode = "AFTER"               # additive: a unique clip may key the helper, the follow comes on top
        c.owner_space = "LOCAL"
        c.target_space = "LOCAL"
        c.influence = influence
        out[owner] = "Copy Rotation of %s (local), influence %.2f" % (target, influence)

    def lift(owner, target, follow, side):
        """Only the ELEVATION of the upper arm (the Z part of its swing, twist about the arm removed; raising the left arm
        is +Z, the right -Z) turns the pauldron, by follow, and only upward: a forward swing or a lowered arm leaves it."""
        pb = arm.pose.bones[owner]
        c = pb.constraints.new("TRANSFORM")
        c.name = "lift_from_" + target
        c.target = arm
        c.subtarget = target
        c.owner_space = "LOCAL"
        c.target_space = "LOCAL"
        c.map_from = "ROTATION"
        c.from_rotation_mode = "SWING_TWIST_Y"
        c.map_to = "ROTATION"
        c.map_to_x_from, c.map_to_y_from, c.map_to_z_from = "X", "Y", "Z"
        c.to_euler_order = "XYZ"
        lim = math.radians(150.0)
        c.from_min_x_rot, c.from_max_x_rot = -lim, lim          # X and Y map to nothing (output range 0..0)
        c.from_min_y_rot, c.from_max_y_rot = -lim, lim
        c.to_min_x_rot = c.to_max_x_rot = 0.0
        c.to_min_y_rot = c.to_max_y_rot = 0.0
        if side == "L":
            c.from_min_z_rot, c.from_max_z_rot = 0.0, lim
            c.to_min_z_rot, c.to_max_z_rot = 0.0, lim * follow
        else:
            c.from_min_z_rot, c.from_max_z_rot = -lim, 0.0
            c.to_min_z_rot, c.to_max_z_rot = -lim * follow, 0.0
        c.use_motion_extrapolate = False                       # clamped: a lowered arm (the other sign) maps to 0
        c.mix_mode_rot = "AFTER"           # additive, as the Copy Rotations
        out[owner] = "Transformation from %s: swing-Z (elevation) x %.2f, upward only" % (target, follow)

    for s in ("L", "R"):
        lift("x_pauldron_" + s, "upperarm_" + s, H["pauldron"]["follow"], s)
        copy_rot("x_elbow_" + s, "lowerarm_" + s, H["elbow"].get("follow_" + s, H["elbow"]["follow"]))
        copy_rot("x_knee_" + s, "shin_" + s, H["knee"]["follow"])
        copy_rot("x_tasset_" + s, "thigh_" + s, H["tasset"]["follow"])
    pb = arm.pose.bones["x_fauld_01"]
    pb.rotation_mode = "XYZ"
    fc = pb.driver_add("rotation_euler", 0)
    drv = fc.driver
    drv.type = "SCRIPTED"
    for vn, bn in (("l", "thigh_L"), ("r", "thigh_R")):
        v = drv.variables.new()
        v.name = vn
        v.type = "TRANSFORMS"
        t = v.targets[0]
        t.id = arm
        t.bone_target = bn
        t.transform_type = "ROT_X"
        t.rotation_mode = "XYZ"
        t.transform_space = "LOCAL_SPACE"
    drv.expression = "max(max(l, r), 0.0) * %.3f" % H["fauld"]["follow"]
    for m in fc.modifiers:
        fc.modifiers.remove(m)
    bpy.context.view_layer.update()
    if not drv.is_simple_expression:
        raise SystemExit("x_fauld_01 driver is not a simple expression (it would need Python auto-run)")
    out["x_fauld_01"] = "driver rotation_euler.x = %s (thigh_L / thigh_R local ROT_X; a simple expression, no Python)" % drv.expression
    log("helpers driven:", out)
    return out


# ---- weights ------------------------------------------------------------------------------------------------------------
def _pieces(ob, ctx):
    """(component label per vertex, piece name per component) from gf_piece."""
    table = ctx.setdefault("_piece_names", {p["id"]: p["name"] for p in read_json(
        os.path.join(ctx["paths"]["A"], "reports", "stage2", "parts.json"))["piece_table"]})
    me = ob.data
    fp = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["gf_piece"].data.foreach_get("value", fp)
    vp = np.full(len(me.vertices), -1)
    for poly, pid in zip(me.polygons, fp):
        vp[list(poly.vertices)] = pid
    lab = components(me)
    names = [table[int(vp[np.nonzero(lab == k)[0][0]])] for k in range(int(lab.max()) + 1)]
    return lab, names


def _suggested(ctx):
    return ctx.setdefault("_suggested", {p["name"]: gf_bone(p["bone"]) for p in read_json(
        os.path.join(ctx["paths"]["A"], "reports", "stage2", "parts.json"))["piece_table"]})


def piece_rule(pname, ctx):
    """{bone: share} for an armour piece: stage3_skin.json rig.pieces (with <S>), else the stage-2 suggestion."""
    rules = ctx["cfg"]["rig"]["pieces"]
    rule = rules.get(pname)
    if rule is None and pname[-2:] in ("_L", "_R"):
        s = pname[-1]
        rule = rules.get(pname[:-1] + "<S>")
        if rule is not None:
            rule = {k.replace("<S>", s): v for k, v in rule.items()} if isinstance(rule, dict) else rule.replace("<S>", s)
    if rule is None:
        rule = _suggested(ctx)[pname]
    return {rule: 1.0} if isinstance(rule, str) else dict(rule)


def _row(rule, ctx):
    r = np.zeros(len(ctx["BONES"]))
    for b, w in rule.items():
        if b not in ctx["C"]:
            raise SystemExit("piece rule names %s, which is not a weight bone" % b)
        r[ctx["C"][b]] += w
    return r / r.sum()


def _hat_rows(z, nodes):
    """Linear blend along a chain: nodes = [(z_node, bone)] in descending z. Returns [(bone, weight)] per vertex."""
    zs = np.array([n[0] for n in nodes])
    out = []
    for zz in z:
        if zz >= zs[0]:
            out.append([(nodes[0][1], 1.0)])
            continue
        if zz <= zs[-1]:
            out.append([(nodes[-1][1], 1.0)])
            continue
        i = int(np.nonzero(zs >= zz)[0][-1])
        t = (zs[i] - zz) / (zs[i] - zs[i + 1])
        out.append([(nodes[i][1], 1.0 - t), (nodes[i + 1][1], t)])
    return out


def grid_weights(co, ctx, prefix, names, cols_u, joints_z, pin_bone, pin_z, half_width):
    """Cloth on chains prefix_<name>_01..: across, linear between the two nearest columns; along, hat functions centred on
    each bone's middle, the top pinned to pin_bone above pin_z."""
    C = ctx["C"]
    W = np.zeros((len(co), len(ctx["BONES"])))
    hw = half_width(co[:, 2])
    u = np.clip(co[:, 0] / hw, cols_u[0], cols_u[-1])
    J = list(joints_z)
    nb = len(J) - 1
    for ci, nm in enumerate(names):
        nodes = [(pin_z, pin_bone)] + [(0.5 * (J[i] + J[i + 1]), "%s_%s_%02d" % (prefix, nm, i + 1)) for i in range(nb)]
        rows = _hat_rows(co[:, 2], nodes)
        # column share: hat over the column positions
        if ci > 0:
            a = np.clip((u - cols_u[ci - 1]) / (cols_u[ci] - cols_u[ci - 1]), 0, 1)
        else:
            a = np.ones(len(u))
        if ci < len(names) - 1:
            b = np.clip((cols_u[ci + 1] - u) / (cols_u[ci + 1] - cols_u[ci]), 0, 1)
        else:
            b = np.ones(len(u))
        share = np.where(u <= cols_u[ci], a, b)
        for i, r in enumerate(rows):
            if share[i] <= 0:
                continue
            for bone, w in r:
                W[i, C[bone]] += share[i] * w
    return W


def part_weights(name, ob, pc, ctx):
    co = np.array([tuple(v.co) for v in ob.data.vertices])
    lab, pnames = _pieces(ob, ctx)
    W = np.zeros((len(co), len(ctx["BONES"])))
    C = ctx["C"]
    rig = ctx["cfg"]["rig"]
    A = ctx["paths"]["A"]
    p2 = read_json(os.path.join(A, "stage2_parts.json"))
    report = ctx.setdefault("_hook_parts", {})
    done = np.zeros(len(co), bool)
    if name == "CAPE":
        rows = np.array(p2["cape"]["rows"], dtype=np.float64)[::-1]
        cc = rig["cape"]
        m = np.isin(lab, [k for k, n in enumerate(pnames) if n == "CAPE"])
        W[m] = grid_weights(co[m], ctx, "x_cape", cc["names"], cc["columns_u"], cc["joints_z"], "spine_03", cc["pin_top_z"],
                            lambda z: np.interp(z, rows[:, 0], rows[:, 1]))
        done |= m
    if name == "LOINCLOTH":
        lo = p2["loin"]
        lc = rig["loin"]
        m = lab >= 0

        def hwf(z):
            f = np.clip((lo["z"][0] - z) / (lo["z"][0] - lo["z"][1]), 0, 1.3)
            return lo["half_width"][0] + (lo["half_width"][1] - lo["half_width"][0]) * f
        W[m] = grid_weights(co[m], ctx, "x_loin", lc["names"], lc["columns_u"], lc["joints_z"], "pelvis", lc["pin_top_z"], hwf)
        done |= m
    if name == "BEARD":
        bd = rig["beard"]

        def block_row(z):
            h = bd["bib_head"] + (1 - bd["bib_head"]) * smoothstep(bd["z_bib"], bd["z_head"], z)
            r = np.zeros((len(z), len(ctx["BONES"])))
            r[:, C["head"]] = h
            r[:, C["neck"]] = 1 - h
            return r
        for k, pn in enumerate(pnames):
            m = lab == k
            if pn == "BEARD_BLOCK":
                W[m] = block_row(co[m, 2])
            elif pn == "BEARD_LOCK":
                W[m] = block_row(np.array([co[m, 2].max()]))[0]
            elif pn == "MOUSTACHE":
                W[m, C["head"]] = 1.0
            done |= m
        for bk in range(1, 6):
            lobes = [k for k, pn in enumerate(pnames) if pn == "BRAID%d_LOBE" % bk]
            lobes.sort(key=lambda k: -co[lab == k, 2].mean())
            for j, k in enumerate(lobes):
                W[lab == k, C["x_beard_%d_%02d" % (bk, 1 if j < 2 else 2)]] = 1.0
            for k, pn in enumerate(pnames):
                if pn == "BRAID%d_CAP" % bk:
                    W[lab == k, C["x_beard_%d_02" % bk]] = 1.0
            done |= np.isin(lab, lobes + [k for k, pn in enumerate(pnames) if pn == "BRAID%d_CAP" % bk])
    # armour: one rigid row per piece
    rigid_rows = {}
    for k, pn in enumerate(pnames):
        m = (lab == k) & ~done
        if not m.any():
            continue
        rule = piece_rule(pn, ctx)
        W[m] = _row(rule, ctx)
        rigid_rows[pn] = {b: round(w, 3) for b, w in rule.items()}
    if (W.sum(axis=1) <= 0).any():
        raise SystemExit("%s: %d vertices left unweighted by the hook" % (name, int((W.sum(axis=1) <= 0).sum())))
    report[name] = {"pieces": len(pnames), "rigid_rows": rigid_rows}
    log("hook weights %s: %d pieces" % (name, len(pnames)))
    return W


# ---- the signature weapon from its shipped GLB ---------------------------------------------------------------------------
def after_bind(arm, ctx):
    out = {"hook_parts": ctx.get("_hook_parts", {})}
    wkey = ctx["fit"].get("signature_weapon")
    root = os.path.dirname(os.path.dirname(os.path.dirname(ctx["paths"]["A"])))
    glb = os.path.join(root, "assets", "models", "weapons", "%s.glb" % wkey)
    if not wkey or not os.path.isfile(glb):
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
    for o in meshes:                                   # bake each part into the grip frame (the import root is identity)
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
