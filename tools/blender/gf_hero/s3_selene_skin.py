"""Stage 3, Selene: the skinning hook the shared s3_skin.py imports (art/characters/selene/stage3_skin.json "hook").

Not run on its own. s3_skin.py builds GF_Hero_v1 from work/selene_landmarks.json (the contract bones + her x_ extras),
weights the bodysuit BODY exactly as it weights Brax's and Valdris's (MakeHuman CC0 seed + bone heat + twist split + joint
fixes), and calls:

  after_armature(arm, ctx)  x_knee_L/R: a Copy Rotation of the shin (local, mixed AFTER) at rig.helpers.knee.follow, so
      the pointed knee cop and the knee fin turn half the knee bend. Blender evaluates it; the stage-5 glTF export samples
      every bone, so clips carry it baked, like the twist bones (the Valdris x_knee pattern, copied, not imported).
  part_weights(name, ob, pc, ctx)  every part (mode "hook"), per stage-2 piece (face attribute gf_piece ->
      reports/stage2/parts.json piece_table):
      cloth   the sheets on chains (stage3_skin.json rig.chains): by the sheet's own v (gf_mask R), the pin row above
              v_pin, then hat functions along the chain (s3_valdris_skin.grid_weights, one column);
      pieces  rig.pieces: a bone or a blended row (rigid: every vertex of the piece the same row), "copy" (each vertex
              copies the body's weights at its closest body point: straps, trims, belt band, bracers, the foot shell) or
              "copy_rigid" (the mean of those copies as one row: belt rings, hip plates).
  after_bind(arm, ctx)  the signature weapon on its socket: assets/models/weapons/thundercoil_launcher.glb imported and
      baked into ONE local object PREVIEW_thundercoil_launcher whose mesh coordinates are the weapon's grip frame, held
      on weapon_R by a Child Of constraint whose inverse is SOCKET_TO_GRIP (the Blender form of the identity attach),
      its sockets (grip_L, muzzle, glow_core) kept as a custom property; the rest attach is checked against the grip frame.
      PREVIEW: never exported with the hero.
"""
import os
import re

import bpy
import numpy as np
from mathutils import Matrix

import gf_hero_rig as R
from s2lib import log, read_json, rel
from s3lib import components

MH_TO_GF = {"neck_01": "neck", "calf": "shin", "ball": "toe"}


def gf_bone(name):
    """A stage-2 piece_table bone (MakeHuman names: clavicle_l, calf_r, ball_l, neck_01, index_03_l) -> GF_Hero_v1."""
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
    for s in ("L", "R"):
        pb = arm.pose.bones["x_knee_" + s]
        c = pb.constraints.new("COPY_ROTATION")
        c.name = "follow_shin_" + s
        c.target = arm
        c.subtarget = "shin_" + s
        c.mix_mode = "AFTER"
        c.owner_space = "LOCAL"
        c.target_space = "LOCAL"
        c.influence = H["knee"]["follow"]
        out["x_knee_" + s] = "Copy Rotation of shin_%s (local), influence %.2f" % (s, H["knee"]["follow"])
    bpy.context.view_layer.update()
    log("helpers driven:", out)
    return out


# ---- weights ------------------------------------------------------------------------------------------------------------
def _table(ctx):
    return ctx.setdefault("_piece_table", read_json(os.path.join(ctx["paths"]["A"], "reports", "stage2", "parts.json"))["piece_table"])


def _pieces(ob, ctx):
    """(component label per vertex, piece name per component) from gf_piece."""
    names_by_id = {p["id"]: p["name"] for p in _table(ctx)}
    me = ob.data
    fp = np.empty(len(me.polygons), dtype=np.int32)
    me.attributes["gf_piece"].data.foreach_get("value", fp)
    vp = np.full(len(me.vertices), -1)
    for poly, pid in zip(me.polygons, fp):
        vp[list(poly.vertices)] = pid
    lab = components(me)
    names = [names_by_id[int(vp[np.nonzero(lab == k)[0][0]])] for k in range(int(lab.max()) + 1)]
    return lab, names


def _suggested(pname, ctx):
    for p in _table(ctx):
        if p["name"] == pname:
            return gf_bone(p["bone"])
    raise SystemExit("piece %s has no stage-2 suggestion" % pname)


def piece_rule(pname, ctx):
    """A bone name, {bone: share}, 'copy' or 'copy_rigid' for a piece: stage3_skin.json rig.pieces (with <S>), else the
    stage-2 suggestion."""
    rules = ctx["cfg"]["rig"]["pieces"]
    rule = rules.get(pname)
    if rule is None and pname[-2:] in ("_L", "_R"):
        s = pname[-1]
        rule = rules.get(pname[:-1] + "<S>")
        if rule is not None:
            rule = {k.replace("<S>", s): v for k, v in rule.items()} if isinstance(rule, dict) else rule.replace("<S>", s)
    if rule is None:
        rule = _suggested(pname, ctx)
    return rule


def _row(rule, ctx):
    r = np.zeros(len(ctx["BONES"]))
    for b, w in rule.items():
        if b not in ctx["C"]:
            raise SystemExit("piece rule names %s, which is not a weight bone" % b)
        r[ctx["C"][b]] += w
    return r / r.sum()


def _hat_rows(v, nodes):
    """Linear blend along a chain: nodes = [(v_node, bone)] in ascending v. Returns [(bone, weight)] per vertex."""
    vs = np.array([n[0] for n in nodes])
    out = []
    for vv in v:
        if vv <= vs[0]:
            out.append([(nodes[0][1], 1.0)])
            continue
        if vv >= vs[-1]:
            out.append([(nodes[-1][1], 1.0)])
            continue
        i = int(np.nonzero(vs <= vv)[0][-1])
        t = (vv - vs[i]) / (vs[i + 1] - vs[i])
        out.append([(nodes[i][1], 1.0 - t), (nodes[i + 1][1], t)])
    return out


def cloth_weights(ob, idx, prefix, ctx):
    rig = ctx["cfg"]["rig"]
    kind = prefix.split("_")[1]
    n = rig["chain_bones"][kind]
    side = prefix[-1] if prefix[-2:] in ("_L", "_R") else None
    pin = rig["pin"][kind]
    pin_row = {k.replace("<S>", side or ""): w for k, w in pin["row"].items()}
    a = ob.data.attributes["gf_mask"]
    col = np.empty(len(a.data) * 4, dtype=np.float64)
    a.data.foreach_get("color", col)
    v = col.reshape(-1, 4)[idx, 0]
    nodes = [(pin["v_pin"], "__pin__")] + [((j + 0.5) / n, "%s_%02d" % (prefix, j + 1)) for j in range(n)]
    W = np.zeros((len(idx), len(ctx["BONES"])))
    prow = _row(pin_row, ctx)
    for i, r in enumerate(_hat_rows(v, nodes)):
        for bone, w in r:
            if bone == "__pin__":
                W[i] += w * prow
            else:
                W[i, ctx["C"][bone]] += w
    return W


def part_weights(name, ob, pc, ctx):
    co = np.array([tuple(v.co) for v in ob.data.vertices])
    lab, pnames = _pieces(ob, ctx)
    W = np.zeros((len(co), len(ctx["BONES"])))
    rig = ctx["cfg"]["rig"]
    report = ctx.setdefault("_hook_parts", {})
    rows_rep = {}
    done = np.zeros(len(co), bool)
    for obname, piece, prefix, _parent in rig["chains"]:
        if obname != name:
            continue
        m = np.isin(lab, [k for k, n in enumerate(pnames) if n == piece])
        idx = np.nonzero(m)[0]
        W[idx] = cloth_weights(ob, idx, prefix, ctx)
        done |= m
        rows_rep[piece] = "cloth chain %s_01..%02d, pinned %s" % (prefix, rig["chain_bones"][prefix.split("_")[1]],
                                                                  rig["pin"][prefix.split("_")[1]]["row"])
    for k, pn in enumerate(pnames):
        m = (lab == k) & ~done
        if not m.any():
            continue
        rule = piece_rule(pn, ctx)
        if rule == "copy":
            W[m] = ctx["copy_from_body"](co[m])
            rows_rep[pn] = "copy from the body per vertex"
        elif rule == "copy_rigid":
            W[m] = ctx["copy_from_body"](co[m]).mean(axis=0)
            rows_rep[pn] = "copy from the body, one rigid row"
        else:
            rule = {rule: 1.0} if isinstance(rule, str) else dict(rule)
            W[m] = _row(rule, ctx)
            rows_rep[pn] = {b: round(w, 3) for b, w in rule.items()}
        done |= m
    if (W.sum(axis=1) <= 0).any():
        raise SystemExit("%s: %d vertices left unweighted by the hook" % (name, int((W.sum(axis=1) <= 0).sum())))
    report[name] = {"pieces": len(pnames), "rows": rows_rep}
    log("hook weights %s: %d pieces" % (name, len(pnames)))
    return W


# ---- the signature weapon from its shipped GLB (the Valdris after_bind pattern, copied) --------------------------------
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
    # no "_R" suffix: s4_anim.build_keepout takes a PREVIEW object ending in _R/_L as a SLEEVE weapon (a star-shaped
    # volume round the forearm axis); the launcher is a carried two-handed weapon, so the right hand keeps its own
    # forearm / hand volume and the launcher's clearance is audited in the stage-4 renders instead
    ob.name = "PREVIEW_%s" % wkey
    ob.data.name = "PREVIEW_%s" % wkey
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
